#!/usr/bin/env python3
"""独立的大区数据 pipeline：将 MGW 公司总计和大区行写入独立飞书表格。

本入口不会被节目包 pipeline 或原有每日更新器调用。它只读取数据库中的
company-level / region-level 记录，不把城市行相加，也不把大区行临时汇总成公司总计。
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

import pymysql

try:
    from galaxy_ceo_portal_raw_data import (
        BJ_TZ,
        BUSINESSES,
        DataQualityError,
        FeishuClient,
        MetricSpec,
        cell_value,
        column_name,
        date_chunks,
        feishu_date_serial,
        feishu_datetime_serial,
        is_reconciled_zero_total_placeholder,
        load_runtime_config,
        normalize_metric_value,
        required,
        values_equal,
    )
except ModuleNotFoundError:  # Supports importing this pipeline as src.galaxy_ceo_portal_region_data.
    from src.galaxy_ceo_portal_raw_data import (
        BJ_TZ,
        BUSINESSES,
        DataQualityError,
        FeishuClient,
        MetricSpec,
        cell_value,
        column_name,
        date_chunks,
        feishu_date_serial,
        feishu_datetime_serial,
        is_reconciled_zero_total_placeholder,
        load_runtime_config,
        normalize_metric_value,
        required,
        values_equal,
    )


LOG = logging.getLogger("galaxy_ceo_portal_region_data")

REGION_RAW_TITLE = "银河CEO门户大区原始数据"
REGION_REFERENCE_TITLE = "公司和大区对应表"
RATE_TITLE = "汇率税率"

REGION_HEADERS = [
    "日期",
    "业务类型",
    "国家/公司",
    "公司 ID",
    "大区 ID",
    "新增用户",
    "充值人数",
    "充值收入（USD，税前）",
    "扣费人数",
    "扣费收入（USD，税后）",
    "更新时间（北京时间，UTC+8）",
]
REGION_REFERENCE_HEADERS = [
    "公司 ID",
    "公司名称（英文）",
    "公司名称（中文）",
    "大区 ID",
    "大区名称",
]
RATE_HEADERS = [
    "生效月份（整月，YYYY-MM）",
    "公司 ID",
    "公司名称（英文）",
    "公司名称（中文）",
    "币种",
    "汇率（1 USD=当地币）",
    "增值税率（%）",
]

REGION_METRICS: tuple[MetricSpec, ...] = (
    MetricSpec(
        "new_users",
        "metric_sub_new_count_v2",
        "sub_day_new_count",
        "fta_flag IS NULL AND wct_flag IS NULL AND tv_class IS NULL",
    ),
    MetricSpec(
        "recharge_count",
        "metric_sub_recharge_count",
        "sub_recharge_count",
        "fta_flag IS NULL AND wct_flag IS NULL AND rate_flag IS NULL AND active_label IS NULL",
    ),
    MetricSpec(
        "recharge_money",
        "metric_sub_recharge_money",
        "recharge_money",
        "wct_flag IS NULL AND rate_flag IS NULL AND tv_class IS NULL AND active_label IS NULL AND load_month = LEFT(load_date, 6)",
        money=True,
    ),
    MetricSpec(
        "deduction_count",
        "metric_sub_deduction_count",
        "sub_deduction_count",
        "fta_flag IS NULL AND wct_flag IS NULL AND rate_flag IS NULL AND active_label IS NULL",
    ),
    MetricSpec(
        "deduction_money",
        "metric_sub_deduction_money",
        "deduction_money",
        "fta_flag IS NULL AND wct_flag IS NULL AND rate_flag IS NULL AND tv_class IS NULL AND active_label IS NULL AND load_month = LEFT(load_date, 6)",
        money=True,
    ),
)


def read_reference_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DataQualityError("reference JSON must be an object")
    return payload


def connect_read_only(config: Mapping[str, str]) -> Any:
    connection = pymysql.connect(
        host=required(config, "MYSQL_HOST"),
        port=int(config.get("MYSQL_PORT", "3306")),
        user=required(config, "MYSQL_USER"),
        password=required(config, "MYSQL_PASSWORD"),
        database=required(config, "JINGWEI_MYSQL_DATABASE"),
        charset="utf8mb4",
        connect_timeout=20,
        read_timeout=120,
        write_timeout=20,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    with connection.cursor() as cursor:
        cursor.execute("SET SESSION TRANSACTION READ ONLY")
    return connection


def load_date_iso(value: Any) -> str:
    text = str(value)
    if len(text) != 8 or not text.isdigit():
        raise DataQualityError(f"invalid MGW load_date: {value!r}")
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


def _recharge_package_detail_totals(
    cursor: Any,
    spec: MetricSpec,
    chunk_start: date,
    chunk_end: date,
) -> dict[tuple[str, str, int, int | None], Decimal]:
    """Read package detail totals used to verify a zero total placeholder."""

    sql = (
        f"SELECT load_date, business, company_id, region_id, package_class, "
        f"COUNT({spec.value_column}) AS populated_values, "
        f"MIN({spec.value_column}) AS min_value, MAX({spec.value_column}) AS max_value "
        f"FROM {spec.table} "
        f"WHERE load_date BETWEEN %s AND %s "
        f"AND business IN (%s, %s) "
        f"AND company_id IS NOT NULL "
        f"AND sale_area_id IS NULL "
        f"AND package_class IS NOT NULL "
        f"AND {spec.breakdown_filter} "
        f"GROUP BY load_date, business, company_id, region_id, package_class "
        f"ORDER BY load_date, business, company_id, region_id, package_class"
    )
    cursor.execute(
        sql,
        (
            chunk_start.strftime("%Y%m%d"),
            chunk_end.strftime("%Y%m%d"),
            *BUSINESSES,
        ),
    )
    totals: dict[tuple[str, str, int, int | None], Decimal] = {}
    for raw in cursor.fetchall():
        populated = int(raw["populated_values"])
        if populated and not values_equal(raw["min_value"], raw["max_value"], spec.money):
            raise DataQualityError(
                f"conflicting {spec.name} package-detail values in {spec.table}: "
                f"{raw['load_date']}/{raw['business']}/{raw['company_id']}/"
                f"{raw['region_id']}/{raw['package_class']} has "
                f"{raw['min_value']} and {raw['max_value']}"
            )
        value = normalize_metric_value(spec, raw["max_value"] if populated else None)
        if value is None:
            continue
        key = (
            str(raw["load_date"]),
            str(raw["business"]),
            int(raw["company_id"]),
            None if raw["region_id"] is None else int(raw["region_id"]),
        )
        totals[key] = totals.get(key, Decimal("0.00")) + Decimal(str(value))
    return totals


def _legacy_new_user_totals(
    cursor: Any,
    chunk_start: date,
    chunk_end: date,
) -> dict[tuple[str, str, int], int]:
    """Read legacy company totals used to verify a v2 zero placeholder."""

    sql = (
        "SELECT load_date, business, company_id, "
        "COUNT(*) AS source_rows, COUNT(`sub_day_new_count`) AS populated_values, "
        "MIN(`sub_day_new_count`) AS min_value, MAX(`sub_day_new_count`) AS max_value "
        "FROM `metric_sub_new_count` "
        "WHERE load_date BETWEEN %s AND %s "
        "AND business IN (%s, %s) "
        "AND company_id IS NOT NULL "
        "AND region_id IS NULL "
        "AND sale_area_id IS NULL "
        "AND package_class IS NULL "
        "AND fta_flag IS NULL "
        "AND wct_flag IS NULL "
        "AND tv_class IS NULL "
        "GROUP BY load_date, business, company_id "
        "ORDER BY load_date, business, company_id"
    )
    cursor.execute(
        sql,
        (
            chunk_start.strftime("%Y%m%d"),
            chunk_end.strftime("%Y%m%d"),
            *BUSINESSES,
        ),
    )
    spec = REGION_METRICS[0]
    totals: dict[tuple[str, str, int], int] = {}
    for raw in cursor.fetchall():
        populated = int(raw["populated_values"])
        if populated and not values_equal(raw["min_value"], raw["max_value"], False):
            raise DataQualityError(
                "conflicting legacy new-user values in metric_sub_new_count: "
                f"{raw['load_date']}/{raw['business']}/{raw['company_id']} has "
                f"{raw['min_value']} and {raw['max_value']}"
            )
        value = normalize_metric_value(spec, raw["max_value"] if populated else None)
        if value is None:
            continue
        key = (load_date_iso(raw["load_date"]), str(raw["business"]), int(raw["company_id"]))
        totals[key] = int(value)
    return totals


def _reconcile_new_user_placeholders(
    merged: Mapping[tuple[str, str, int, int | None], dict[str, Any]],
    legacy_totals: Mapping[tuple[str, str, int], int],
) -> None:
    """Use a legacy company total only when it exactly matches region details."""

    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for key, row in merged.items():
        grouped[key[:3]].append(row)
    for group_key, group_rows in grouped.items():
        total = next((row for row in group_rows if row["region_id"] is None), None)
        regions = [row for row in group_rows if row["region_id"] is not None]
        if total is None or total.get("new_users") != 0 or not regions:
            continue
        legacy_total = legacy_totals.get(group_key)
        region_values = [row.get("new_users") for row in regions]
        if (
            legacy_total is None
            or legacy_total <= 0
            or any(value is None for value in region_values)
            or sum(region_values) != legacy_total
        ):
            continue
        total["new_users"] = legacy_total
        LOG.warning(
            "using the legacy new-user company total after matching region details; "
            "discarding an upstream v2 zero placeholder for key %r",
            group_key,
        )


def collect_rows(
    config: Mapping[str, str],
    start: date,
    end: date,
    chunk_days: int,
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, int, int | None], dict[str, Any]] = {}
    connection = connect_read_only(config)
    try:
        with connection.cursor() as cursor:
            for chunk_start, chunk_end in date_chunks(start, end, chunk_days):
                LOG.info("querying region pipeline chunk %s through %s", chunk_start, chunk_end)
                for spec in REGION_METRICS:
                    package_detail_totals: dict[tuple[Any, ...], Decimal] = {}
                    if spec.name == "recharge_money":
                        package_detail_totals = _recharge_package_detail_totals(
                            cursor, spec, chunk_start, chunk_end
                        )
                    sql = (
                        f"SELECT load_date, business, company_id, region_id, "
                        f"COUNT(*) AS source_rows, COUNT(`{spec.value_column}`) AS populated_values, "
                        f"MIN(`{spec.value_column}`) AS min_value, MAX(`{spec.value_column}`) AS max_value "
                        f"FROM `{spec.table}` "
                        f"WHERE load_date BETWEEN %s AND %s "
                        f"AND business IN (%s, %s) "
                        f"AND company_id IS NOT NULL "
                        f"AND sale_area_id IS NULL "
                        f"AND package_class IS NULL "
                        f"AND {spec.breakdown_filter} "
                        f"GROUP BY load_date, business, company_id, region_id "
                        f"ORDER BY load_date, business, company_id, region_id"
                    )
                    cursor.execute(
                        sql,
                        (
                            chunk_start.strftime("%Y%m%d"),
                            chunk_end.strftime("%Y%m%d"),
                            *BUSINESSES,
                        ),
                    )
                    for raw in cursor.fetchall():
                        populated = int(raw["populated_values"])
                        used_zero_placeholder = False
                        if populated and not values_equal(
                            raw["min_value"], raw["max_value"], spec.money
                        ):
                            used_zero_placeholder = is_reconciled_zero_total_placeholder(
                                spec, raw, package_detail_totals
                            )
                            if not used_zero_placeholder:
                                raise DataQualityError(
                                    f"conflicting {spec.name} values in {spec.table}: "
                                    f"{raw['load_date']}/{raw['business']}/{raw['company_id']}/"
                                    f"{raw['region_id']} has {raw['min_value']} and {raw['max_value']}"
                                )
                            LOG.warning(
                                "using the non-zero recharge-money total after matching "
                                "package details; discarding an upstream zero placeholder "
                                "for region key %r",
                                (
                                    raw["load_date"],
                                    raw["business"],
                                    raw["company_id"],
                                    raw["region_id"],
                                ),
                            )
                        key = (
                            load_date_iso(raw["load_date"]),
                            str(raw["business"]),
                            int(raw["company_id"]),
                            None if raw["region_id"] is None else int(raw["region_id"]),
                        )
                        row = merged.setdefault(
                            key,
                            {
                                "date": key[0],
                                "business": key[1],
                                "company_id": key[2],
                                "region_id": key[3],
                            },
                        )
                        value = normalize_metric_value(
                            spec,
                            raw["max_value"] if populated else None,
                        )
                        if spec.name in row and row[spec.name] != value:
                            raise DataQualityError(
                                f"duplicate merged value for {key!r}, metric {spec.name}"
                            )
                        row[spec.name] = value
                if any(
                    key[3] is None and row.get("new_users") == 0
                    for key, row in merged.items()
                ):
                    _reconcile_new_user_placeholders(
                        merged,
                        _legacy_new_user_totals(cursor, chunk_start, chunk_end),
                    )
    finally:
        connection.close()

    business_order = {"DTT": 0, "DTH": 1}
    return sorted(
        merged.values(),
        key=lambda row: (
            row["date"],
            business_order.get(row["business"], 99),
            row["company_id"],
            0 if row["region_id"] is None else 1,
            -1 if row["region_id"] is None else row["region_id"],
        ),
    )


def validate_total_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Check that explicit DB total rows and region rows have the same grain.

    This is a validation only. The pipeline never creates total rows by summing
    region rows; it writes the DB rows as received.
    """

    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["date"], row["business"], row["company_id"])].append(row)

    report: dict[str, dict[str, Any]] = {}
    hard_mismatches: list[dict[str, Any]] = []
    for spec in REGION_METRICS:
        report[spec.name] = {
            "comparable": 0,
            "mismatches": 0,
            "rounding_only": 0,
            "hard_mismatches": 0,
            "max_abs_difference": "0.00" if spec.money else "0",
            "example": None,
        }

    for group_key, group_rows in groups.items():
        total = next((row for row in group_rows if row["region_id"] is None), None)
        regions = [row for row in group_rows if row["region_id"] is not None]
        if total is None or not regions:
            continue
        for spec in REGION_METRICS:
            metric = spec.name
            stats = report[metric]
            if total.get(metric) is None or any(row.get(metric) is None for row in regions):
                continue
            stats["comparable"] += 1
            total_value = total[metric]
            region_sum = sum((row[metric] for row in regions), 0)
            difference = Decimal(str(total_value)) - Decimal(str(region_sum))
            if difference == 0:
                continue
            stats["mismatches"] += 1
            absolute = abs(difference)
            if absolute > Decimal(str(stats["max_abs_difference"])):
                stats["max_abs_difference"] = str(absolute)
            example = {
                "date": group_key[0],
                "business": group_key[1],
                "company_id": group_key[2],
                "metric": metric,
                "total": str(total_value),
                "region_sum": str(region_sum),
                "difference": str(difference),
            }
            if stats["example"] is None:
                stats["example"] = example
            # Both the company row and each region row are already stored at
            # cent precision. A difference bounded by one cent per region is
            # an expected presentation-rounding effect, not a reason to
            # replace the database rows with a derived sum.
            rounding_bound = Decimal("0.01") * len(regions) if spec.money else Decimal("0")
            if spec.money and absolute <= rounding_bound:
                stats["rounding_only"] += 1
                continue
            stats["hard_mismatches"] += 1
            hard_mismatches.append(example)

    if hard_mismatches:
        raise DataQualityError(
            "database company-total and region rows differ; "
            f"first hard mismatches: {hard_mismatches[:5]}"
        )
    return {
        "groups": len(groups),
        "metrics": report,
    }


def make_references(refs: Mapping[str, Any]) -> tuple[dict[int, dict[str, str]], list[list[Any]], list[list[Any]]]:
    companies: dict[int, dict[str, str]] = {}
    for item in refs.get("companies", []):
        company_id = int(item["id"])
        if company_id in companies:
            raise DataQualityError(f"duplicate company reference: {company_id}")
        companies[company_id] = {
            "name": str(item.get("name") or ""),
            "cn_name": str(item.get("cn_name") or ""),
        }

    regions: dict[tuple[int, int], str] = {}
    for item in refs.get("regions", []):
        key = (int(item["company_id"]), int(item["region_id"]))
        name = str(item.get("region_name") or "")
        old = regions.setdefault(key, name)
        if old != name:
            raise DataQualityError(f"conflicting region reference: {key}")

    by_company: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for (company_id, region_id), name in regions.items():
        by_company[company_id].append((region_id, name))
    reference_rows: list[list[Any]] = []
    for company_id in sorted(companies):
        company = companies[company_id]
        company_regions = sorted(by_company.get(company_id, [])) or [(None, "")]
        for region_id, region_name in company_regions:
            reference_rows.append(
                [
                    company_id,
                    company["name"],
                    company["cn_name"],
                    "" if region_id is None else region_id,
                    region_name,
                ]
            )

    vat_by_key: dict[tuple[str, int, str], Any] = {}
    for item in refs.get("rates", []):
        month = str(item.get("month") or "")
        if len(month) == 6 and month.isdigit():
            month = f"{month[:4]}-{month[4:]}"
        vat_by_key[(month, int(item["company_id"]), str(item.get("currency") or ""))] = item.get("vat_rate", "")

    rate_rows: list[list[Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for item in refs.get("rates", []):
        month = str(item.get("month") or "")
        if len(month) == 6 and month.isdigit():
            month = f"{month[:4]}-{month[4:]}"
        company_id = int(item["company_id"])
        currency = str(item.get("currency") or "")
        key = (month, company_id, currency)
        if key in seen:
            continue
        seen.add(key)
        company = companies.get(company_id, {"name": "", "cn_name": ""})
        rate_rows.append(
            [
                month,
                company_id,
                company["name"] or str(item.get("company_name") or ""),
                company["cn_name"],
                currency,
                cell_value(item.get("exchange_rate", "")),
                cell_value(vat_by_key.get(key, "")),
            ]
        )
    rate_rows.sort(key=lambda row: (row[0], row[1], row[4]))
    return companies, reference_rows, rate_rows


def raw_values(
    rows: Sequence[dict[str, Any]],
    companies: Mapping[int, Mapping[str, str]],
    written_at: datetime,
) -> list[list[Any]]:
    timestamp = feishu_datetime_serial(written_at.replace(second=0, microsecond=0))
    output: list[list[Any]] = []
    for row in rows:
        company = companies[row["company_id"]]
        display_name = company["cn_name"] or company["name"] or str(row["company_id"])
        output.append(
            [
                feishu_date_serial(row["date"]),
                row["business"],
                display_name,
                row["company_id"],
                "" if row["region_id"] is None else row["region_id"],
                cell_value(row.get("new_users")),
                cell_value(row.get("recharge_count")),
                cell_value(row.get("recharge_money")),
                cell_value(row.get("deduction_count")),
                cell_value(row.get("deduction_money")),
                timestamp,
            ]
        )
    return output


def write_sheet(
    client: FeishuClient,
    token: str,
    sheet: Mapping[str, Any],
    headers: Sequence[str],
    rows: Sequence[list[Any]],
    batch_size: int,
    date_column: bool = False,
    timestamp_column: int | None = None,
) -> None:
    sheet_id = str(sheet["sheet_id"])
    client.ensure_row_capacity(token, sheet, len(rows) + 1)
    end_column = column_name(len(headers))
    client.write_range(token, f"{sheet_id}!A1:{end_column}1", [list(headers)])
    batch_size = min(max(batch_size, 1), 500)
    for offset in range(0, len(rows), batch_size):
        chunk = list(rows[offset : offset + batch_size])
        first_row = offset + 2
        last_row = first_row + len(chunk) - 1
        client.write_range(token, f"{sheet_id}!A{first_row}:{end_column}{last_row}", chunk)
        if date_column:
            client.set_formatter(token, f"{sheet_id}!A{first_row}:A{last_row}", "yyyy-MM-dd")
        if timestamp_column is not None:
            column = column_name(timestamp_column)
            client.set_formatter(token, f"{sheet_id}!{column}{first_row}:{column}{last_row}", "yyyy/MM/dd HH:mm:ss")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-env", type=Path, default=Path(".env"))
    parser.add_argument("--reference-json", type=Path, required=True)
    parser.add_argument("--folder-token", help="创建新大区表格时使用的飞书文件夹 token")
    parser.add_argument("--start-date", required=True, type=lambda value: date.fromisoformat(value))
    parser.add_argument("--end-date", type=lambda value: date.fromisoformat(value))
    parser.add_argument("--query-chunk-days", type=int, default=7)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true", help="只验证数据库和映射，不创建或写入飞书")
    return parser


def run(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if not args.dry_run and not args.folder_token:
        raise DataQualityError("--folder-token is required unless --dry-run is used")
    config = load_runtime_config(args.project_env)
    refs = read_reference_json(args.reference_json)

    try:
        from galaxy_ceo_portal_raw_data import MySQLReader
    except ModuleNotFoundError:
        from src.galaxy_ceo_portal_raw_data import MySQLReader

    with MySQLReader(config) as reader:
        latest = reader.latest_common_date()
    end = args.end_date or latest
    if end > latest:
        raise DataQualityError(f"requested end date {end} exceeds database latest common date {latest}")
    if args.start_date > end:
        raise DataQualityError(f"start date {args.start_date} is after end date {end}")

    rows = collect_rows(config, args.start_date, end, args.query_chunk_days)
    total_validation = validate_total_rows(rows)
    companies, reference_rows, rate_rows = make_references(refs)
    data_companies = {row["company_id"] for row in rows}
    missing_companies = sorted(data_companies - set(companies))
    data_regions = {
        (row["company_id"], row["region_id"])
        for row in rows
        if row["region_id"] is not None
    }
    ref_regions = {
        (int(item["company_id"]), int(item["region_id"]))
        for item in refs.get("regions", [])
    }
    missing_regions = sorted(data_regions - ref_regions)
    if missing_companies or missing_regions:
        raise DataQualityError(
            f"missing MCP mapping before Feishu write: companies={missing_companies}, "
            f"regions={missing_regions[:20]}"
        )

    expected_months = {args.start_date.strftime("%Y-%m"), end.strftime("%Y-%m")}
    rate_months = {str(row[0]) for row in rate_rows}
    if not expected_months.issubset(rate_months):
        raise DataQualityError(
            f"reference rate sheet does not cover all data months: "
            f"expected={sorted(expected_months)}, actual={sorted(rate_months)}"
        )

    summary = {
        "start_date": args.start_date.isoformat(),
        "end_date": end.isoformat(),
        "latest_common_date": latest.isoformat(),
        "raw_rows": len(rows),
        "company_total_rows": sum(row["region_id"] is None for row in rows),
        "region_rows": sum(row["region_id"] is not None for row in rows),
        "company_mapping_rows": len(reference_rows),
        "rate_rows": len(rate_rows),
        "total_validation": total_validation,
        "dry_run": bool(args.dry_run),
    }
    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    written_at = datetime.now(BJ_TZ).replace(second=0, microsecond=0)
    client = FeishuClient(config)
    title = f"{REGION_RAW_TITLE} {written_at:%Y-%m-%d %H:%M}"
    spreadsheet = client.create_spreadsheet(title, args.folder_token)
    token = str(spreadsheet["spreadsheet_token"])
    initial_sheets = client.list_sheets(token)
    if not initial_sheets:
        raise DataQualityError("new region spreadsheet has no initial sheet")
    client.rename_sheet(token, str(initial_sheets[0]["sheet_id"]), REGION_RAW_TITLE)
    client.create_sheet(token, REGION_REFERENCE_TITLE, 1)
    client.create_sheet(token, RATE_TITLE, 2)
    sheets = {str(sheet["title"]): sheet for sheet in client.list_sheets(token)}
    for expected in (REGION_RAW_TITLE, REGION_REFERENCE_TITLE, RATE_TITLE):
        if expected not in sheets:
            raise DataQualityError(f"new region spreadsheet missing sheet {expected!r}")

    values = raw_values(rows, companies, written_at)
    write_sheet(
        client,
        token,
        sheets[REGION_RAW_TITLE],
        REGION_HEADERS,
        values,
        args.batch_size,
        date_column=True,
        timestamp_column=len(REGION_HEADERS),
    )
    write_sheet(
        client,
        token,
        sheets[REGION_REFERENCE_TITLE],
        REGION_REFERENCE_HEADERS,
        reference_rows,
        args.batch_size,
    )
    write_sheet(
        client,
        token,
        sheets[RATE_TITLE],
        RATE_HEADERS,
        rate_rows,
        args.batch_size,
    )

    raw_sheet_id = str(sheets[REGION_RAW_TITLE]["sheet_id"])
    first = client.read_range(token, f"{raw_sheet_id}!A1:K2")
    last_row = len(values) + 1
    last = client.read_range(token, f"{raw_sheet_id}!A{last_row}:K{last_row}")
    if not first or first[0] != REGION_HEADERS or not last:
        raise DataQualityError("post-write verification failed for region raw sheet")

    summary.update(
        {
            "spreadsheet_url": spreadsheet.get("url"),
            "title": title,
            "verification": "header_and_first_last_raw_rows_ok",
        }
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(build_parser().parse_args(argv))
    except (DataQualityError, pymysql.MySQLError, OSError) as exc:
        LOG.error("%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
