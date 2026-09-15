#!/usr/bin/env python3
"""独立维护银河 CEO 大区原始数据飞书表格的日更 pipeline。"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import math
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple
from urllib.parse import quote

import pymysql
import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.galaxy_ceo_portal_raw_data import (  # noqa: E402
    BJ_TZ,
    DataQualityError,
    FeishuClient,
    FeishuError,
    MySQLReader,
    cell_value,
    column_name,
    feishu_datetime_serial,
    load_runtime_config,
)
from src.galaxy_ceo_portal_region_data import (  # noqa: E402
    REGION_HEADERS,
    REGION_RAW_TITLE,
    REGION_REFERENCE_HEADERS,
    REGION_REFERENCE_TITLE,
    collect_rows,
    raw_values,
    validate_total_rows,
)
from src.galaxy_ceo_portal_reporting import (  # noqa: E402
    date_coverage,
    duplicate_count,
    quality_check,
    quality_report,
    safe_send_timer_report,
    spreadsheet_url,
)


LOG = logging.getLogger("galaxy_ceo_portal_region_daily_update")
FEISHU_EPOCH = date(1899, 12, 30)
DEFAULT_RETRY_COUNT = 3
DEFAULT_RETRY_INTERVAL_SECONDS = 3_600
DEFAULT_RETENTION_DAYS = 400
DEFAULT_BATCH_SIZE = 500
DEFAULT_QUERY_CHUNK_DAYS = 7
DEFAULT_LOCK_FILE = Path("/tmp/galaxy_ceo_portal_region_daily_update.lock")
REGION_TITLE_PATTERN = re.compile(
    rf"^{re.escape(REGION_RAW_TITLE)} \d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}(?::\d{{2}})?$"
)

RegionKey = Tuple[str, str, int, Optional[int]]


class RegionUpdateError(RuntimeError):
    """Raised when the independent region update cannot safely complete."""


@dataclass(frozen=True)
class ExistingRegionRow:
    row_number: int
    business_date: date
    key: RegionKey


@dataclass(frozen=True)
class RegionSnapshot:
    rows: tuple[ExistingRegionRow, ...]
    keys: frozenset[RegionKey]
    dates: frozenset[date]

    @property
    def data_rows(self) -> int:
        return len(self.rows)

    @property
    def max_date(self) -> date | None:
        return max(self.dates) if self.dates else None


@dataclass(frozen=True)
class RegionUpdatePlan:
    target_start: date
    target_end: date
    fetch_ranges: tuple[tuple[date, date], ...]
    expired_rows: tuple[ExistingRegionRow, ...]


def parse_feishu_date(value: Any) -> date:
    if value in (None, ""):
        raise RegionUpdateError("region raw date cell is empty")
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                pass
        try:
            value = Decimal(text)
        except InvalidOperation as exc:
            raise RegionUpdateError(f"invalid region date: {value!r}") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise RegionUpdateError(f"invalid region date type: {type(value).__name__}")
    if isinstance(value, float) and not math.isfinite(value):
        raise RegionUpdateError(f"invalid region date serial: {value!r}")
    serial = Decimal(str(value))
    if serial != serial.to_integral_value():
        raise RegionUpdateError(f"region date has a time component: {value!r}")
    serial_int = int(serial)
    if serial_int < 1 or serial_int > 200_000:
        raise RegionUpdateError(f"region date serial is outside safe range: {value!r}")
    return FEISHU_EPOCH + timedelta(days=serial_int)


def parse_int(value: Any, label: str) -> int:
    if value in (None, ""):
        raise RegionUpdateError(f"{label} is empty")
    number = Decimal(str(value))
    if number != number.to_integral_value():
        raise RegionUpdateError(f"{label} is not an integer: {value!r}")
    return int(number)


def validate_metric_cells(row: Sequence[Any], row_number: int) -> None:
    """Validate existing region metric cells while preserving legitimate blanks."""

    for column_index in (5, 6, 8):
        if len(row) <= column_index or row[column_index] in (None, ""):
            continue
        label = f"metric column {column_index + 1} at row {row_number}"
        try:
            value = Decimal(str(row[column_index]))
        except (InvalidOperation, ValueError) as exc:
            raise RegionUpdateError(f"{label} is not numeric: {row[column_index]!r}") from exc
        if not value.is_finite() or value != value.to_integral_value():
            raise RegionUpdateError(f"{label} is not a finite integer: {row[column_index]!r}")

    for column_index in (7, 9):
        if len(row) <= column_index or row[column_index] in (None, ""):
            continue
        label = f"metric column {column_index + 1} at row {row_number}"
        try:
            value = Decimal(str(row[column_index]))
        except (InvalidOperation, ValueError) as exc:
            raise RegionUpdateError(f"{label} is not numeric: {row[column_index]!r}") from exc
        if not value.is_finite():
            raise RegionUpdateError(f"{label} is not a finite number: {row[column_index]!r}")


def parse_region_id(value: Any, row_number: int) -> int | None:
    if value in (None, ""):
        return None
    return parse_int(value, f"region ID at row {row_number}")


def parse_region_key(row: Sequence[Any], row_number: int) -> tuple[date, RegionKey]:
    if len(row) < 5:
        raise RegionUpdateError(f"region raw row {row_number} has fewer than five columns")
    business_date = parse_feishu_date(row[0])
    business = str(row[1]).strip() if row[1] not in (None, "") else ""
    if business not in {"DTT", "DTH"}:
        raise RegionUpdateError(f"region raw row {row_number} has invalid business {business!r}")
    company_id = parse_int(row[3], f"company ID at row {row_number}")
    region_id = parse_region_id(row[4], row_number)
    return business_date, (business_date.isoformat(), business, company_id, region_id)


def read_region_snapshot(
    client: FeishuClient,
    spreadsheet_token: str,
    sheet: Mapping[str, Any],
    batch_size: int,
) -> RegionSnapshot:
    header = client.read_range(spreadsheet_token, f"{sheet['sheet_id']}!A1:K1")
    if header != [REGION_HEADERS]:
        raise FeishuError("region raw sheet header does not match the independent layout")
    row_count = int(sheet.get("grid_properties", {}).get("row_count", 200))
    if row_count > 1_000_000:
        raise FeishuError("region raw sheet is too large to scan safely")
    batch_size = min(max(batch_size, 1), DEFAULT_BATCH_SIZE)
    rows: list[ExistingRegionRow] = []
    seen_keys: dict[RegionKey, int] = {}
    first_blank: int | None = None
    for offset in range(2, max(row_count, 2) + 1, batch_size):
        last_row = min(max(row_count, 2), offset + batch_size - 1)
        values = client.read_range(spreadsheet_token, f"{sheet['sheet_id']}!A{offset}:K{last_row}")
        for index in range(last_row - offset + 1):
            row_number = offset + index
            row = list(values[index]) if index < len(values) else []
            if not any(cell not in (None, "") for cell in row):
                if first_blank is None:
                    first_blank = row_number
                continue
            if first_blank is not None:
                raise FeishuError(
                    f"region raw sheet has a blank row before row {row_number}; refusing to update"
                )
            business_date, key = parse_region_key(row, row_number)
            validate_metric_cells(row, row_number)
            if key in seen_keys:
                raise FeishuError(
                    f"region raw sheet has duplicate business key {key!r} at rows "
                    f"{seen_keys[key]} and {row_number}"
                )
            seen_keys[key] = row_number
            rows.append(ExistingRegionRow(row_number, business_date, key))
    return RegionSnapshot(
        rows=tuple(rows),
        keys=frozenset(row.key for row in rows),
        dates=frozenset(row.business_date for row in rows),
    )


def read_company_names(
    client: FeishuClient,
    spreadsheet_token: str,
    sheets: Sequence[Mapping[str, Any]],
) -> dict[int, dict[str, str]]:
    target = next((sheet for sheet in sheets if str(sheet.get("title")) == REGION_REFERENCE_TITLE), None)
    if target is None:
        raise FeishuError(f"region spreadsheet has no {REGION_REFERENCE_TITLE!r} sheet")
    header = client.read_range(spreadsheet_token, f"{target['sheet_id']}!A1:E1")
    if header != [REGION_REFERENCE_HEADERS]:
        raise FeishuError("region reference-sheet header does not match the independent layout")
    row_count = int(target.get("grid_properties", {}).get("row_count", 200))
    values = client.read_range(spreadsheet_token, f"{target['sheet_id']}!A2:E{max(row_count, 2)}")
    companies: dict[int, dict[str, str]] = {}
    for row in values:
        if not row or row[0] in (None, ""):
            continue
        company_id = parse_int(row[0], "company ID in region reference sheet")
        value = {
            "name": str(row[1] or "") if len(row) > 1 else "",
            "cn_name": str(row[2] or "") if len(row) > 2 else "",
        }
        previous = companies.get(company_id)
        if previous is not None and previous != value:
            raise FeishuError(
                f"region reference sheet has conflicting names for company ID {company_id}"
            )
        companies[company_id] = value
    return companies


def iter_dates(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def date_ranges(dates: Iterable[date]) -> tuple[tuple[date, date], ...]:
    ordered = sorted(set(dates))
    if not ordered:
        return ()
    ranges: list[tuple[date, date]] = []
    start = previous = ordered[0]
    for current in ordered[1:]:
        if current != previous + timedelta(days=1):
            ranges.append((start, previous))
            start = current
        previous = current
    ranges.append((start, previous))
    return tuple(ranges)


def build_update_plan(
    snapshot: RegionSnapshot,
    target_end: date,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> RegionUpdatePlan:
    if retention_days < 1:
        raise ValueError("retention_days must be positive")
    target_start = target_end - timedelta(days=retention_days - 1)
    expected = set(iter_dates(target_start, target_end))
    missing = expected - set(snapshot.dates)
    # Always re-query the newest date so a partial batch is repaired.
    missing.add(target_end)
    expired = tuple(row for row in snapshot.rows if row.business_date < target_start)
    return RegionUpdatePlan(target_start, target_end, date_ranges(missing), expired)


def source_key(row: Mapping[str, Any]) -> RegionKey:
    return (
        str(row["date"]),
        str(row["business"]),
        int(row["company_id"]),
        None if row.get("region_id") is None else int(row["region_id"]),
    )


def missing_source_rows(
    source_rows: Sequence[dict[str, Any]],
    existing_keys: Iterable[RegionKey],
) -> list[dict[str, Any]]:
    seen = set(existing_keys)
    output: list[dict[str, Any]] = []
    for row in source_rows:
        key = source_key(row)
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def deletion_ranges(
    expired_rows: Sequence[ExistingRegionRow],
    max_rows_per_request: int = 5_000,
) -> tuple[tuple[int, int], ...]:
    row_numbers = sorted(row.row_number for row in expired_rows)
    if not row_numbers:
        return ()
    contiguous: list[tuple[int, int]] = []
    start = previous = row_numbers[0]
    for row_number in row_numbers[1:]:
        if row_number != previous + 1:
            contiguous.append((start, previous))
            start = row_number
        previous = row_number
    contiguous.append((start, previous))
    chunks: list[tuple[int, int]] = []
    for start, end in contiguous:
        while start <= end:
            chunk_end = min(end, start + max_rows_per_request - 1)
            chunks.append((start, chunk_end))
            start = chunk_end + 1
    return tuple(reversed(chunks))


def find_raw_sheet(client: FeishuClient, spreadsheet_token: str) -> Mapping[str, Any]:
    for sheet in client.list_sheets(spreadsheet_token):
        if str(sheet.get("title")) == REGION_RAW_TITLE:
            return sheet
    raise FeishuError(f"region spreadsheet has no {REGION_RAW_TITLE!r} sheet")


def validate_title(client: FeishuClient, spreadsheet_token: str) -> str:
    title = client.spreadsheet_title(spreadsheet_token)
    if not REGION_TITLE_PATTERN.fullmatch(title):
        raise FeishuError(f"region spreadsheet title is not recognized: {title!r}")
    return title


def rename_region_spreadsheet(
    client: FeishuClient,
    spreadsheet_token: str,
    title: str,
) -> None:
    if not REGION_TITLE_PATTERN.fullmatch(title):
        raise FeishuError(f"invalid region spreadsheet title: {title!r}")
    client.request(
        "PATCH",
        f"/open-apis/sheets/v3/spreadsheets/{quote(spreadsheet_token, safe='')}",
        json={"title": title},
    )


def write_region_rows(
    client: FeishuClient,
    spreadsheet_token: str,
    sheet_id: str,
    values: Sequence[list[Any]],
    batch_size: int,
    start_row: int,
) -> None:
    batch_size = min(max(batch_size, 1), DEFAULT_BATCH_SIZE)
    end_column = column_name(len(REGION_HEADERS))
    for offset in range(0, len(values), batch_size):
        chunk = list(values[offset : offset + batch_size])
        first_row = start_row + offset
        last_row = first_row + len(chunk) - 1
        client.write_range(
            spreadsheet_token,
            f"{sheet_id}!A{first_row}:{end_column}{last_row}",
            chunk,
        )
        client.set_formatter(
            spreadsheet_token,
            f"{sheet_id}!A{first_row}:A{last_row}",
            "yyyy-MM-dd",
        )
        timestamp_column = column_name(len(REGION_HEADERS))
        client.set_formatter(
            spreadsheet_token,
            f"{sheet_id}!{timestamp_column}{first_row}:{timestamp_column}{last_row}",
            "yyyy/MM/dd HH:mm:ss",
        )


def verify_post_write(
    client: FeishuClient,
    spreadsheet_token: str,
    batch_size: int,
    expected_keys: Iterable[RegionKey],
    expected_rows: int,
    expected_title: str,
    target_start: date,
    target_end: date,
) -> dict[str, Any]:
    """Re-scan the region target after mutation and verify its final shape."""

    refreshed_sheet = find_raw_sheet(client, spreadsheet_token)
    snapshot = read_region_snapshot(client, spreadsheet_token, refreshed_sheet, batch_size)
    actual_keys = set(snapshot.keys)
    expected_key_set = set(expected_keys)
    if actual_keys != expected_key_set:
        missing = sorted(expected_key_set - actual_keys)
        extra = sorted(actual_keys - expected_key_set)
        raise FeishuError(
            "post-write region key verification failed: "
            f"missing={missing[:5]}, extra={extra[:5]}"
        )
    if snapshot.data_rows != expected_rows:
        raise FeishuError(
            f"post-write region row-count verification failed: "
            f"expected={expected_rows}, actual={snapshot.data_rows}"
        )
    coverage = date_coverage(snapshot.dates, target_start, target_end)
    if coverage["status"] != "passed":
        raise FeishuError(
            "post-write region date coverage verification failed: "
            f"missing={coverage['missing_dates']}, extra={coverage['extra_dates']}"
        )
    actual_title = client.spreadsheet_title(spreadsheet_token)
    if actual_title != expected_title:
        raise FeishuError(
            f"post-write region spreadsheet title verification failed: "
            f"expected={expected_title!r}, actual={actual_title!r}"
        )
    return {
        "status": "passed",
        "data_rows": snapshot.data_rows,
        "max_date": snapshot.max_date.isoformat() if snapshot.max_date else None,
        "date_coverage": coverage,
        "duplicate_business_keys": 0,
        "title": actual_title,
    }


def update_once(
    config: Mapping[str, str],
    spreadsheet_token: str,
    query_chunk_days: int,
    batch_size: int,
    now: datetime | None = None,
    dry_run: bool = False,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> dict[str, Any]:
    now = (now or datetime.now(BJ_TZ)).astimezone(BJ_TZ)
    client = FeishuClient(config)
    current_title = validate_title(client, spreadsheet_token)
    sheets = client.list_sheets(spreadsheet_token)
    raw_sheet = find_raw_sheet(client, spreadsheet_token)
    # The Feishu scan intentionally happens before the database readiness check.
    snapshot = read_region_snapshot(client, spreadsheet_token, raw_sheet, batch_size)
    companies = read_company_names(client, spreadsheet_token, sheets)

    with MySQLReader(config) as reader:
        source_latest = reader.latest_common_date()
    yesterday = now.date() - timedelta(days=1)
    LOG.info(
        "region Feishu max date=%s; database latest common date=%s; Beijing yesterday=%s",
        snapshot.max_date,
        source_latest,
        yesterday,
    )
    if source_latest < yesterday:
        return {
            "ready": False,
            "feishu_max_date": snapshot.max_date.isoformat() if snapshot.max_date else None,
            "source_latest_date": source_latest.isoformat(),
            "expected_yesterday": yesterday.isoformat(),
            "document": {
                "title": current_title,
                "url": spreadsheet_url(config, spreadsheet_token),
                "status": "未更新（数据源未就绪）",
            },
            "quality": quality_report(
                [
                    quality_check(
                        "飞书目标表结构",
                        "passed",
                        f"表头、空行、日期、业务、公司 ID、大区 ID 和指标类型检查通过，共 {snapshot.data_rows} 行。",
                    ),
                    quality_check(
                        "数据库时效性",
                        "failed",
                        f"数据库最新日期 {source_latest.isoformat()} 未达到期望日期 {yesterday.isoformat()}。",
                    ),
                    quality_check("写入保护", "passed", "数据源未就绪，未执行删除、追加或改名。"),
                ]
            ),
        }

    target_end = min(source_latest, yesterday)
    plan = build_update_plan(snapshot, target_end, retention_days)
    source_rows: list[dict[str, Any]] = []
    for start, end in plan.fetch_ranges:
        source_rows.extend(
            collect_rows(
                config,
                start,
                end,
                query_chunk_days,
            )
        )
    append_rows = missing_source_rows(source_rows, snapshot.keys)
    source_duplicate_count = duplicate_count([source_key(row) for row in source_rows])
    if source_duplicate_count:
        raise DataQualityError(
            f"region database result contains {source_duplicate_count} duplicate business keys; refusing to write"
        )
    expired_keys = {row.key for row in plan.expired_rows}
    planned_dates = {row.business_date for row in snapshot.rows if row.key not in expired_keys}
    planned_dates.update(date.fromisoformat(str(row["date"])) for row in append_rows)
    planned_coverage = date_coverage(planned_dates, plan.target_start, plan.target_end)
    if planned_coverage["status"] != "passed":
        raise DataQualityError(
            "planned region date coverage is incomplete or contains out-of-window dates: "
            f"missing={planned_coverage['missing_dates']}, extra={planned_coverage['extra_dates']}"
        )
    total_validation = validate_total_rows(source_rows)
    validation_metrics = total_validation.get("metrics", {})
    comparable = sum(int(item.get("comparable", 0)) for item in validation_metrics.values())
    mismatches = sum(int(item.get("mismatches", 0)) for item in validation_metrics.values())
    rounding_only = sum(int(item.get("rounding_only", 0)) for item in validation_metrics.values())
    if comparable == 0:
        reconciliation_status = "warning"
        reconciliation_detail = "本次来源数据没有可比较的公司总计/大区行组合。"
    elif mismatches:
        reconciliation_status = "warning"
        reconciliation_detail = f"发现 {mismatches} 个差异，其中 {rounding_only} 个属于允许的金额舍入差异。"
    else:
        reconciliation_status = "passed"
        reconciliation_detail = f"可比较 {comparable} 项，公司总计与大区行均一致。"
    missing_company_mappings = sorted(
        {int(row["company_id"]) for row in append_rows} - set(companies)
    )
    checks = [
        quality_check(
            "数据库时效性",
            "passed",
            f"数据库共同最新日期 {source_latest.isoformat()} 已达到北京时间昨日 {yesterday.isoformat()}。",
        ),
        quality_check(
            "飞书目标表结构",
            "passed",
            f"表头、空行、日期、业务、公司 ID、大区 ID 和指标类型检查通过，共 {snapshot.data_rows} 行。",
        ),
        quality_check(
            "来源指标一致性",
            "passed",
            f"五项指标已按固定口径读取并完成类型/冲突检查，共 {len(source_rows)} 行。",
        ),
        quality_check("来源业务键唯一性", "passed", "数据库结果未发现重复业务键。"),
        quality_check(
            "日期覆盖与业务键不重复",
            "passed",
            f"目标窗口 {planned_coverage['expected_days']} 天全部覆盖，数据库/飞书业务键重复 0 个。",
        ),
        quality_check("公司总计/大区行核对", reconciliation_status, reconciliation_detail),
        quality_check(
            "公司名称映射",
            "warning" if missing_company_mappings else "passed",
            (
                f"{len(missing_company_mappings)} 个公司 ID 未在对应表中找到，写入时将暂以 ID 展示。"
                if missing_company_mappings
                else "本次待写入公司均已找到名称映射。"
            ),
        ),
    ]
    expected_keys = (set(snapshot.keys) - expired_keys) | {
        source_key(row) for row in append_rows
    }
    expired_ranges = deletion_ranges(plan.expired_rows)
    result: dict[str, Any] = {
        "target_start_date": plan.target_start.isoformat(),
        "target_end_date": plan.target_end.isoformat(),
        "feishu_max_date": snapshot.max_date.isoformat() if snapshot.max_date else None,
        "source_rows_read": len(source_rows),
        "rows_to_append": len(append_rows),
        "rows_to_delete": len(plan.expired_rows),
        "delete_ranges": len(expired_ranges),
        "window_policy": f"rolling_{retention_days}_natural_days_through_yesterday",
        "total_validation": total_validation,
        "missing_company_mappings": missing_company_mappings,
    }
    if dry_run:
        checks.append(quality_check("写入后回读", "skipped", "dry-run 未执行写入，因此未做回读。"))
        result.update(
            {
                "ready": True,
                "source_latest_date": source_latest.isoformat(),
                "dry_run": True,
                "quality": quality_report(checks),
            }
        )
        return result

    for start_row, end_row in expired_ranges:
        client.delete_rows(spreadsheet_token, str(raw_sheet["sheet_id"]), start_row, end_row)

    remaining_rows = snapshot.data_rows - len(plan.expired_rows)
    if append_rows:
        refreshed_sheet = find_raw_sheet(client, spreadsheet_token)
        client.ensure_row_capacity(
            spreadsheet_token,
            refreshed_sheet,
            remaining_rows + len(append_rows) + 1,
        )
        # Unknown future company IDs are displayed by ID until the separate
        # MCP reference sync adds their names to the reference sheet.
        for row in append_rows:
            companies.setdefault(int(row["company_id"]), {"name": str(row["company_id"]), "cn_name": ""})
        write_region_rows(
            client,
            spreadsheet_token,
            str(refreshed_sheet["sheet_id"]),
            raw_values(append_rows, companies, now),
            batch_size,
            start_row=remaining_rows + 2,
        )

    new_title = f"{REGION_RAW_TITLE} {now:%Y-%m-%d %H:%M}"
    rename_region_spreadsheet(client, spreadsheet_token, new_title)
    result.update(
        {
            "ready": True,
            "source_latest_date": source_latest.isoformat(),
            "title": new_title,
            "verification": verify_post_write(
                client,
                spreadsheet_token,
                batch_size,
                expected_keys,
                len(expected_keys),
                new_title,
                plan.target_start,
                plan.target_end,
            ),
        }
    )
    checks.append(
        quality_check(
            "写入后回读",
            "passed",
            f"表头、键集合、行数（{len(expected_keys)}）和标题均已复核。",
        )
    )
    coverage = result["verification"]["date_coverage"]
    checks.append(
        quality_check(
            "日期覆盖与业务键不重复",
            "passed",
            f"目标窗口 {coverage['expected_days']} 天全部存在，重复业务键 0 个。",
        )
    )
    result["quality"] = quality_report(checks)
    result["document"] = {
        "title": new_title,
        "url": spreadsheet_url(config, spreadsheet_token),
        "status": "已更新",
    }
    return result


def run_with_retries(args: argparse.Namespace) -> int:
    if args.max_retries < 0 or args.retry_interval_seconds < 0:
        raise ValueError("retry settings must be non-negative")
    config = load_runtime_config(args.project_env)
    spreadsheet_token = (args.spreadsheet_token or config.get("GALAXY_CEO_PORTAL_REGION_SPREADSHEET_TOKEN", "")).strip()
    if not spreadsheet_token:
        raise RegionUpdateError(
            "--spreadsheet-token or GALAXY_CEO_PORTAL_REGION_SPREADSHEET_TOKEN is required"
        )
    started_at = time.monotonic()
    max_attempts = args.max_retries + 1
    last_result: dict[str, Any] | None = None

    def notify(
        result: Mapping[str, Any] | None,
        attempts: int,
        error: BaseException | None = None,
    ) -> dict[str, str]:
        if args.dry_run:
            return {"status": "skipped", "reason": "dry_run"}
        report_result = dict(result or {})
        report_result.setdefault("ready", False)
        report_result.setdefault(
            "document",
            {
                "title": "目标表未确认",
                "url": spreadsheet_url(config, spreadsheet_token),
                "status": "未更新（质检或读取失败）",
            },
        )
        return safe_send_timer_report(
            config,
            "大区",
            report_result,
            attempts,
            max_attempts,
            time.monotonic() - started_at,
            error=error,
            logger=LOG,
        )

    for attempt in range(args.max_retries + 1):
        attempts_done = attempt + 1
        LOG.info("region update attempt %d/%d", attempt + 1, args.max_retries + 1)
        try:
            last_result = update_once(
                config,
                spreadsheet_token,
                args.query_chunk_days,
                args.batch_size,
                dry_run=args.dry_run,
                retention_days=args.retention_days,
            )
            if last_result.get("ready"):
                last_result = dict(last_result)
                last_result["attempts"] = attempts_done
                last_result["max_attempts"] = max_attempts
                last_result["duration_seconds"] = round(time.monotonic() - started_at, 3)
                last_result["notification"] = notify(last_result, attempts_done)
                print(json.dumps(last_result, ensure_ascii=False))
                return 0
            LOG.warning("database is not ready for yesterday: %s", last_result)
        except (FeishuError, pymysql.MySQLError, requests.RequestException) as exc:
            if attempt >= args.max_retries:
                notify(last_result, attempts_done, exc)
                raise
            LOG.warning("transient region update failure: %s", exc)
        except Exception as exc:  # noqa: BLE001 - fatal data errors must still be reported.
            notify(last_result, attempts_done, exc)
            raise
        if attempt < args.max_retries:
            LOG.info("sleeping %s seconds before the next region attempt", args.retry_interval_seconds)
            time.sleep(args.retry_interval_seconds)
    failure = RegionUpdateError(f"region source did not reach yesterday; last_result={last_result}")
    notify(last_result, max_attempts, failure)
    raise failure


@contextmanager
def process_lock(path: Path) -> Iterable[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RegionUpdateError(f"another region update is already running: {path}") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-env", type=Path, default=Path(".env"))
    parser.add_argument("--spreadsheet-token")
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    parser.add_argument("--query-chunk-days", type=int, default=DEFAULT_QUERY_CHUNK_DAYS)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-retries", type=int, default=DEFAULT_RETRY_COUNT)
    parser.add_argument("--retry-interval-seconds", type=int, default=DEFAULT_RETRY_INTERVAL_SECONDS)
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK_FILE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO", choices=("WARNING", "INFO", "DEBUG"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s")
    try:
        with process_lock(args.lock_file):
            return run_with_retries(args)
    except (
        DataQualityError,
        FeishuError,
        RegionUpdateError,
        ValueError,
        pymysql.MySQLError,
        requests.RequestException,
    ) as exc:
        LOG.error("%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
