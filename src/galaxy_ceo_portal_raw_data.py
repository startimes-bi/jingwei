#!/usr/bin/env python3
"""Load MGW company-level subscription metrics into a Feishu spreadsheet.

The program deliberately keeps the data path narrow:
  * MySQL is read-only and only five allow-listed metric tables are queried.
  * Region/city rows and metric breakdown rows are never summed.
  * Feishu credentials are loaded from a controlled env file at runtime.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pymysql
import requests


LOG = logging.getLogger("galaxy_ceo_portal_raw_data")
BJ_TZ = ZoneInfo("Asia/Shanghai")
FEISHU_BASE_URL = "https://open.feishu.cn"
BUSINESSES = ("DTT", "DTH")
MONEY_QUANT = Decimal("0.01")

RAW_SHEET_TITLE = "银河CEO门户原始数据"
SPREADSHEET_TITLE_PREFIX = RAW_SHEET_TITLE
SPREADSHEET_TITLE_PATTERN = re.compile(
    rf"^{re.escape(SPREADSHEET_TITLE_PREFIX)}(?: \d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}(?::\d{{2}})?)?$"
)
COMPANY_SHEET_TITLE = "公司对应表"
RATE_SHEET_TITLE = "汇率税率"
FEISHU_DATE_FORMAT = "yyyy-MM-dd"
FEISHU_DATETIME_FORMAT = "yyyy/MM/dd HH:mm:ss"

RAW_HEADERS = [
    "日期",
    "业务类型",
    "公司 ID",
    "节目包",
    "新增用户",
    "充值人数",
    "充值收入（USD，税前）",
    "扣费人数",
    "扣费收入（USD，税后）",
    "更新时间（北京时间，UTC+8）",
]
COMPANY_HEADERS = ["公司 ID", "公司名称（英文）", "公司名称（中文）"]
RATE_HEADERS = [
    "生效月份（整月，YYYY-MM）",
    "公司 ID",
    "公司名称（英文）",
    "公司名称（中文）",
    "币种",
    "汇率（1 USD=当地币）",
    "增值税率（%）",
]


class ConfigurationError(RuntimeError):
    """Raised when a controlled runtime configuration is incomplete."""


class DataQualityError(RuntimeError):
    """Raised when source rows cannot be safely reduced to the target grain."""


class FeishuError(RuntimeError):
    """Raised for a non-successful Feishu API response."""


@dataclass(frozen=True)
class MetricSpec:
    name: str
    table: str
    value_column: str
    breakdown_filter: str
    money: bool = False


METRICS: tuple[MetricSpec, ...] = (
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


def _strip_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def read_env_file(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE config files without expanding secrets in logs."""

    if not path.is_file():
        raise ConfigurationError(f"controlled env file is not readable: {path}")
    values: dict[str, str] = {}
    pattern = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = pattern.match(line)
        if not match:
            raise ConfigurationError(f"invalid env syntax at {path}:{line_number}")
        values[match.group(1)] = _strip_env_value(match.group(2))
    return values


def load_runtime_config(project_env_path: Path) -> dict[str, str]:
    project = read_env_file(project_env_path)
    mysql_path_value = os.environ.get("JINGWEI_MYSQL_ENV_PATH") or project.get("JINGWEI_MYSQL_ENV_PATH")
    feishu_path_value = os.environ.get("FEISHU_REPORTING_ENV_PATH") or project.get("FEISHU_REPORTING_ENV_PATH")
    if not mysql_path_value or not feishu_path_value:
        raise ConfigurationError("project env must point to both controlled runtime config files")

    merged = dict(project)
    merged.update(read_env_file(Path(mysql_path_value).expanduser()))
    merged.update(read_env_file(Path(feishu_path_value).expanduser()))
    # Explicit process environment values win, which keeps CI/runtime injection possible.
    merged.update({key: value for key, value in os.environ.items() if value})
    return merged


def required(config: Mapping[str, str], key: str) -> str:
    value = config.get(key, "").strip()
    if not value:
        raise ConfigurationError(f"missing controlled configuration: {key}")
    return value


def parse_yyyymmdd(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise DataQualityError(f"invalid MGW load_date: {value!r}") from exc


def iso_date(value: date) -> str:
    return value.isoformat()


def feishu_date_serial(value: date | str) -> int:
    """Return a date-only Feishu/Excel serial without applying a timezone."""

    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError as exc:
            raise DataQualityError(f"invalid ISO date: {value!r}") from exc
    if not isinstance(value, date) or isinstance(value, datetime):
        raise DataQualityError(f"invalid date value: {value!r}")
    return (value - date(1899, 12, 30)).days


def money_value(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise DataQualityError(f"invalid money value: {value!r}") from exc


def count_value(value: Any) -> int | None:
    if value is None:
        return None
    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation as exc:
        raise DataQualityError(f"invalid count value: {value!r}") from exc
    if decimal_value != decimal_value.to_integral_value():
        raise DataQualityError(f"non-integer count value: {value!r}")
    return int(decimal_value)


def normalize_metric_value(spec: MetricSpec, value: Any) -> Decimal | int | None:
    return money_value(value) if spec.money else count_value(value)


def values_equal(left: Any, right: Any, money: bool) -> bool:
    if left is None or right is None:
        return left is right
    if money:
        return money_value(left) == money_value(right)
    return count_value(left) == count_value(right)


def is_reconciled_zero_total_placeholder(
    spec: MetricSpec,
    raw: Mapping[str, Any],
    package_detail_totals: Mapping[tuple[Any, Any, Any], Decimal],
) -> bool:
    """Recognize the observed recharge-money zero placeholder only after reconciliation."""

    if spec.name != "recharge_money" or raw["package_class"] is not None:
        return False
    if int(raw["source_rows"]) != 2 or int(raw["populated_values"]) != 2:
        return False
    minimum = money_value(raw["min_value"])
    maximum = money_value(raw["max_value"])
    if minimum != Decimal("0.00") or maximum is None or maximum <= Decimal("0.00"):
        return False
    key = (raw["load_date"], raw["business"], raw["company_id"])
    detail_total = package_detail_totals.get(key)
    return detail_total is not None and abs(detail_total - maximum) <= MONEY_QUANT


class MySQLReader:
    """Read only the allow-listed MGW company-level metric records."""

    def __init__(self, config: Mapping[str, str]):
        self._connection = pymysql.connect(
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
        with self._connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "MySQLReader":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    @staticmethod
    def _business_placeholders() -> str:
        return ", ".join(["%s"] * len(BUSINESSES))

    @classmethod
    def _company_scope_filter(cls, spec: MetricSpec) -> str:
        return (
            f"business IN ({cls._business_placeholders()}) "
            "AND company_id IS NOT NULL "
            "AND region_id IS NULL "
            "AND sale_area_id IS NULL "
            f"AND {spec.breakdown_filter}"
        )

    def latest_common_date(self) -> date:
        latest_values: list[date] = []
        for spec in METRICS:
            sql = (
                f"SELECT load_date AS max_load_date FROM `{spec.table}` USE INDEX (`key3`) "
                f"WHERE {self._company_scope_filter(spec)} "
                "ORDER BY load_date DESC LIMIT 1"
            )
            with self._connection.cursor() as cursor:
                cursor.execute(sql, BUSINESSES)
                row = cursor.fetchone()
            raw_value = row["max_load_date"] if row else None
            if not raw_value:
                raise DataQualityError(f"no common-date data in {spec.table}")
            latest_values.append(parse_yyyymmdd(str(raw_value)))
        return min(latest_values)

    def fetch_metric(self, spec: MetricSpec, start: date, end: date) -> list[dict[str, Any]]:
        base_filter = f"load_date BETWEEN %s AND %s AND {self._company_scope_filter(spec)}"
        sql = (
            f"SELECT load_date, business, company_id, package_class, "
            f"COUNT(*) AS source_rows, COUNT(`{spec.value_column}`) AS populated_values, "
            f"MIN(`{spec.value_column}`) AS min_value, MAX(`{spec.value_column}`) AS max_value "
            f"FROM `{spec.table}` WHERE {base_filter} "
            "GROUP BY load_date, business, company_id, package_class "
            "ORDER BY load_date, business, company_id, package_class"
        )
        params: list[Any] = [start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), *BUSINESSES]
        rows: list[dict[str, Any]] = []
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            raw_rows = cursor.fetchall()
        package_detail_totals: dict[tuple[Any, Any, Any], Decimal] = {}
        if spec.money:
            for raw in raw_rows:
                if raw["package_class"] is None:
                    continue
                populated_values = int(raw["populated_values"])
                if populated_values > 1 and not values_equal(
                    raw["min_value"], raw["max_value"], spec.money
                ):
                    key = (
                        raw["load_date"],
                        raw["business"],
                        raw["company_id"],
                        raw["package_class"],
                    )
                    raise DataQualityError(
                        f"conflicting company-level values in {spec.table} for target key {key!r}"
                    )
                value = normalize_metric_value(spec, raw["max_value"] if populated_values else None)
                if value is not None:
                    company_key = (raw["load_date"], raw["business"], raw["company_id"])
                    package_detail_totals[company_key] = (
                        package_detail_totals.get(company_key, Decimal("0.00")) + value
                    )
        for raw in raw_rows:
            source_rows = int(raw["source_rows"])
            populated_values = int(raw["populated_values"])
            min_value = raw["min_value"]
            max_value = raw["max_value"]
            used_zero_placeholder = False
            if populated_values > 1 and not values_equal(min_value, max_value, spec.money):
                key = (
                    raw["load_date"],
                    raw["business"],
                    raw["company_id"],
                    raw["package_class"],
                )
                used_zero_placeholder = is_reconciled_zero_total_placeholder(
                    spec, raw, package_detail_totals
                )
                if not used_zero_placeholder:
                    raise DataQualityError(
                        f"conflicting company-level values in {spec.table} for target key {key!r}"
                    )
                LOG.warning(
                    "using the non-zero recharge-money total after matching package details; "
                    "discarding an upstream zero placeholder for target key %r",
                    key,
                )
            if source_rows > 1 and not used_zero_placeholder:
                LOG.warning(
                    "deduplicating %d identical company-level source rows in %s",
                    source_rows,
                    spec.table,
                )
            value = normalize_metric_value(spec, max_value if populated_values else None)
            raw_date = parse_yyyymmdd(str(raw["load_date"]))
            rows.append(
                {
                    "date": iso_date(raw_date),
                    "business": str(raw["business"]),
                    "company_id": int(raw["company_id"]),
                    "package_class": raw["package_class"],
                    "metric": spec.name,
                    "value": value,
                }
            )
        return rows


def merge_metric_rows(metric_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, int, Any], dict[str, Any]] = {}
    for item in metric_rows:
        key = (item["date"], item["business"], item["company_id"], item["package_class"])
        row = merged.setdefault(
            key,
            {
                "date": item["date"],
                "business": item["business"],
                "company_id": item["company_id"],
                "package_class": item["package_class"],
                "new_users": None,
                "recharge_count": None,
                "recharge_money": None,
                "deduction_count": None,
                "deduction_money": None,
            },
        )
        metric = item["metric"]
        if row[metric] is not None and row[metric] != item["value"]:
            raise DataQualityError(f"duplicate merged value for target key {key!r}, metric {metric}")
        row[metric] = item["value"]
    business_order = {"DTT": 0, "DTH": 1}
    return sorted(
        merged.values(),
        key=lambda row: (
            row["date"],
            business_order.get(row["business"], 99),
            row["company_id"],
            0 if row["package_class"] is None else 1,
            "" if row["package_class"] is None else str(row["package_class"]),
        ),
    )


def render_package(package_class: Any) -> str:
    if package_class is None:
        return "公司合计（package_class=NULL）"
    return str(package_class)


def feishu_datetime_serial(value: datetime) -> float:
    """Return an Excel/Feishu serial using Beijing wall-clock time as neutral value."""

    local = value.astimezone(BJ_TZ).replace(tzinfo=None)
    epoch = datetime(1899, 12, 30)
    delta = local - epoch
    return delta.days + (delta.seconds + delta.microseconds / 1_000_000) / 86_400


def cell_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return float(value)
    return value


def normalize_reference_month(value: Any) -> str:
    text = str(value).strip()
    if re.fullmatch(r"\d{6}", text):
        text = f"{text[:4]}-{text[4:]}"
    if not re.fullmatch(r"\d{4}-\d{2}", text):
        raise DataQualityError(f"invalid reference month: {value!r}")
    return text


def load_reference_rows(path: str) -> tuple[list[list[Any]], list[list[Any]]]:
    """Load MCP-derived reference rows without embedding them in the program."""

    raw_text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise DataQualityError(f"invalid reference JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise DataQualityError("reference JSON must be an object")

    company_rows: list[list[Any]] = []
    company_ids: set[int] = set()
    for item in payload.get("companies", []):
        if not isinstance(item, dict):
            raise DataQualityError("reference companies must be objects")
        company_id = int(item.get("id", item.get("company_id")))
        if company_id in company_ids:
            raise DataQualityError(f"duplicate reference company_id: {company_id}")
        company_ids.add(company_id)
        company_rows.append(
            [
                company_id,
                str(item.get("name", item.get("company_name")) or ""),
                str(item.get("cn_name", item.get("company_cn_name")) or ""),
            ]
        )
    company_rows.sort(key=lambda row: row[0])

    rate_by_key: dict[tuple[str, int, str], list[Any]] = {}
    for item in payload.get("rates", []):
        if not isinstance(item, dict):
            raise DataQualityError("reference rates must be objects")
        month = normalize_reference_month(item.get("month", item.get("date")))
        company_id = int(item.get("company_id"))
        currency = str(item.get("currency_code", item.get("currency", "")) or "")
        row = [
            month,
            company_id,
            str(item.get("company_name", item.get("name")) or ""),
            str(item.get("company_cn_name", item.get("cn_name")) or ""),
            currency,
            cell_value(item.get("exchange_rate", item.get("exchangerateid"))),
            cell_value(item.get("vat_rate", item.get("valueaddedtaxid"))),
        ]
        key = (month, company_id, currency)
        previous = rate_by_key.setdefault(key, row)
        if previous != row:
            raise DataQualityError(f"conflicting reference rate rows for key: {key!r}")
    rate_rows = sorted(rate_by_key.values(), key=lambda row: (row[0], row[1], row[4]))
    return company_rows, rate_rows


def rows_to_values(rows: Sequence[dict[str, Any]], written_at: datetime) -> list[list[Any]]:
    timestamp = feishu_datetime_serial(written_at.replace(second=0, microsecond=0))
    values: list[list[Any]] = []
    for row in rows:
        values.append(
            [
                feishu_date_serial(row["date"]),
                row["business"],
                row["company_id"],
                render_package(row["package_class"]),
                cell_value(row["new_users"]),
                cell_value(row["recharge_count"]),
                cell_value(row["recharge_money"]),
                cell_value(row["deduction_count"]),
                cell_value(row["deduction_money"]),
                timestamp,
            ]
        )
    return values


def column_name(number: int) -> str:
    if number < 1:
        raise ValueError("column number must be positive")
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


class FeishuClient:
    def __init__(self, config: Mapping[str, str], session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._base_url = config.get("FEISHU_BASE_URL", FEISHU_BASE_URL).rstrip("/")
        app_id = required(config, "FEISHU_APP_ID")
        app_secret = required(config, "FEISHU_APP_SECRET")
        response = self._session.post(
            f"{self._base_url}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=20,
        )
        payload = self._decode(response, "Feishu authentication")
        self._token = payload["tenant_access_token"]

    def _decode(self, response: requests.Response, operation: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise FeishuError(f"{operation} returned invalid JSON (HTTP {response.status_code})") from exc
        if response.status_code < 200 or response.status_code >= 300 or payload.get("code") != 0:
            raise FeishuError(
                f"{operation} failed: HTTP {response.status_code}, "
                f"code={payload.get('code')}, msg={payload.get('msg')}"
            )
        return payload

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}))
        headers.setdefault("Authorization", f"Bearer {self._token}")
        headers.setdefault("Content-Type", "application/json; charset=utf-8")
        attempts = 4
        for attempt in range(attempts):
            response = self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                timeout=60,
                **kwargs,
            )
            if response.status_code not in {429, 500, 502, 503, 504} or attempt == attempts - 1:
                return self._decode(response, f"Feishu {method} {path}")
            time.sleep(2**attempt)
        raise AssertionError("unreachable")

    def list_sheets(self, spreadsheet_token: str) -> list[dict[str, Any]]:
        payload = self.request(
            "GET",
            f"/open-apis/sheets/v3/spreadsheets/{quote(spreadsheet_token, safe='')}/sheets/query",
        )
        return payload.get("data", {}).get("sheets", [])

    def spreadsheet_title(self, spreadsheet_token: str) -> str:
        payload = self.request(
            "GET",
            f"/open-apis/sheets/v3/spreadsheets/{quote(spreadsheet_token, safe='')}",
        )
        data = payload.get("data", {})
        spreadsheet = data.get("spreadsheet", data)
        title = spreadsheet.get("title") if isinstance(spreadsheet, dict) else None
        if not title:
            raise FeishuError("Feishu spreadsheet metadata did not contain a title")
        return str(title)

    def validate_spreadsheet_title(self, spreadsheet_token: str) -> str:
        title = self.spreadsheet_title(spreadsheet_token)
        if not SPREADSHEET_TITLE_PATTERN.fullmatch(title):
            raise FeishuError(
                f"spreadsheet title does not match the expected prefix/time format; refusing to alter it"
            )
        return title

    def rename_spreadsheet(self, spreadsheet_token: str, title: str) -> None:
        if not SPREADSHEET_TITLE_PATTERN.fullmatch(title):
            raise FeishuError(f"invalid spreadsheet title format: {title!r}")
        self.request(
            "PATCH",
            f"/open-apis/sheets/v3/spreadsheets/{quote(spreadsheet_token, safe='')}",
            json={"title": title},
        )

    def create_spreadsheet(self, title: str, folder_token: str) -> dict[str, Any]:
        payload = self.request(
            "POST",
            "/open-apis/sheets/v3/spreadsheets",
            json={"title": title, "folder_token": folder_token},
        )
        return payload["data"]["spreadsheet"]

    def rename_sheet(self, spreadsheet_token: str, sheet_id: str, title: str) -> None:
        self.request(
            "POST",
            f"/open-apis/sheets/v2/spreadsheets/{quote(spreadsheet_token, safe='')}/sheets_batch_update",
            json={
                "requests": [
                    {
                        "updateSheet": {
                            "properties": {"sheetId": sheet_id, "title": title, "index": 0}
                        }
                    }
                ]
            },
        )

    def create_sheet(self, spreadsheet_token: str, title: str, index: int) -> None:
        self.request(
            "POST",
            f"/open-apis/sheets/v2/spreadsheets/{quote(spreadsheet_token, safe='')}/sheets_batch_update",
            json={
                "requests": [
                    {"addSheet": {"properties": {"title": title, "index": index}}}
                ]
            },
        )

    def ensure_layout(self, spreadsheet_token: str) -> dict[str, str]:
        self.validate_spreadsheet_title(spreadsheet_token)
        sheets = self.list_sheets(spreadsheet_token)
        by_title = {str(sheet["title"]): str(sheet["sheet_id"]) for sheet in sheets}
        if RAW_SHEET_TITLE not in by_title:
            if not sheets:
                raise FeishuError("spreadsheet has no initial sheet")
            self.rename_sheet(spreadsheet_token, str(sheets[0]["sheet_id"]), RAW_SHEET_TITLE)
        for index, title in enumerate((COMPANY_SHEET_TITLE, RATE_SHEET_TITLE), 1):
            sheets = self.list_sheets(spreadsheet_token)
            by_title = {str(sheet["title"]): str(sheet["sheet_id"]) for sheet in sheets}
            if title not in by_title:
                self.create_sheet(spreadsheet_token, title, index)
        sheets = self.list_sheets(spreadsheet_token)
        by_title = {str(sheet["title"]): str(sheet["sheet_id"]) for sheet in sheets}
        missing = [title for title in (RAW_SHEET_TITLE, COMPANY_SHEET_TITLE, RATE_SHEET_TITLE) if title not in by_title]
        if missing:
            raise FeishuError(f"missing expected sheets after layout setup: {missing}")
        return {title: by_title[title] for title in (RAW_SHEET_TITLE, COMPANY_SHEET_TITLE, RATE_SHEET_TITLE)}

    def read_range(self, spreadsheet_token: str, range_name: str) -> list[list[Any]]:
        encoded_range = quote(range_name, safe="!:$")
        payload = self.request(
            "GET",
            f"/open-apis/sheets/v2/spreadsheets/{quote(spreadsheet_token, safe='')}/values/{encoded_range}",
        )
        return payload.get("data", {}).get("valueRange", {}).get("values", []) or []

    def assert_sheet_empty(self, spreadsheet_token: str, sheet: Mapping[str, Any]) -> None:
        sheet_id = str(sheet["sheet_id"])
        row_count = int(sheet.get("grid_properties", {}).get("row_count", 200))
        # Reading a bounded range is enough for a newly created sheet. A larger grid
        # is treated as occupied rather than risking an append into an existing file.
        if row_count > 100_000:
            raise FeishuError("target sheet is too large to prove empty; refusing to write")
        last_row = max(200, row_count)
        last_column = column_name(len(RAW_HEADERS))
        values = self.read_range(spreadsheet_token, f"{sheet_id}!A2:{last_column}{last_row}")
        if any(cell not in (None, "") for row in values for cell in row):
            raise FeishuError("target raw sheet is not empty; refusing to overwrite or append")

    def verify_written_rows(
        self,
        spreadsheet_token: str,
        sheet_id: str,
        expected_values: Sequence[list[Any]],
    ) -> None:
        if not expected_values:
            return

        def equivalent(expected: Any, actual: Any) -> bool:
            if expected in (None, "") and actual in (None, ""):
                return True
            if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
                return abs(float(expected) - float(actual)) <= 1e-9
            return expected == actual

        last_column = column_name(len(RAW_HEADERS))
        header = self.read_range(
            spreadsheet_token,
            f"{sheet_id}!A1:{last_column}1",
        )
        if header != [RAW_HEADERS]:
            raise FeishuError("post-write header verification failed")
        sample_indexes = sorted({0, 1, len(expected_values) - 2, len(expected_values) - 1})
        for index in sample_indexes:
            first_row = index + 2
            actual = self.read_range(
                spreadsheet_token,
                f"{sheet_id}!A{first_row}:{last_column}{first_row}",
            )
            expected = expected_values[index]
            if len(actual) != 1 or len(actual[0]) < len(expected):
                raise FeishuError(f"post-write row verification failed at row {first_row}")
            if not all(equivalent(left, right) for left, right in zip(expected, actual[0])):
                raise FeishuError(f"post-write row verification failed at row {first_row}")
        next_row = len(expected_values) + 2
        trailing = self.read_range(
            spreadsheet_token,
            f"{sheet_id}!A{next_row}:{last_column}{next_row}",
        )
        if any(cell not in (None, "") for row in trailing for cell in row):
            raise FeishuError("post-write row-count verification found unexpected trailing data")

    def ensure_row_capacity(
        self,
        spreadsheet_token: str,
        sheet: Mapping[str, Any],
        required_rows: int,
    ) -> None:
        current_rows = int(sheet.get("grid_properties", {}).get("row_count", 200))
        missing_rows = max(0, required_rows - current_rows)
        while missing_rows:
            add_count = min(missing_rows, 5_000)
            self.request(
                "POST",
                f"/open-apis/sheets/v2/spreadsheets/{quote(spreadsheet_token, safe='')}/dimension_range",
                json={
                    "dimension": {
                        "sheetId": str(sheet["sheet_id"]),
                        "majorDimension": "ROWS",
                        "length": add_count,
                    }
                },
            )
            missing_rows -= add_count

    def write_range(self, spreadsheet_token: str, range_name: str, values: list[list[Any]]) -> None:
        self.request(
            "PUT",
            f"/open-apis/sheets/v2/spreadsheets/{quote(spreadsheet_token, safe='')}/values",
            json={"valueRange": {"range": range_name, "values": values}},
        )

    def set_formatter(self, spreadsheet_token: str, range_name: str, formatter: str) -> None:
        self.request(
            "PUT",
            f"/open-apis/sheets/v2/spreadsheets/{quote(spreadsheet_token, safe='')}/style",
            json={
                "range": range_name,
                "appendStyle": {"range": range_name, "style": {"formatter": formatter}},
            },
        )

    def delete_rows(
        self,
        spreadsheet_token: str,
        sheet_id: str,
        start_row: int,
        end_row: int,
    ) -> None:
        """Delete an inclusive 1-based row range from a sheet."""

        if start_row < 1 or end_row < start_row:
            raise ValueError("invalid row deletion range")
        self.request(
            "DELETE",
            f"/open-apis/sheets/v2/spreadsheets/{quote(spreadsheet_token, safe='')}/dimension_range",
            json={
                "dimension": {
                    "sheetId": str(sheet_id),
                    "majorDimension": "ROWS",
                    "startIndex": start_row,
                    "endIndex": end_row,
                }
            },
        )

    def normalize_raw_date_column(
        self,
        spreadsheet_token: str,
        sheet: Mapping[str, Any],
        batch_size: int,
    ) -> dict[str, int]:
        """Convert existing ISO date text in column A without touching other columns."""

        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        batch_size = min(batch_size, 500)
        sheet_id = str(sheet["sheet_id"])
        row_count = int(sheet.get("grid_properties", {}).get("row_count", 200))
        if row_count <= 1:
            return {"data_rows": 0, "converted_rows": 0}

        # Complete the read/validation pass before making any write. This keeps a
        # malformed or non-contiguous column from causing a partial conversion.
        normalized: list[list[Any]] = []
        first_blank_row: int | None = None
        for offset in range(2, row_count + 1, batch_size):
            last_row = min(row_count, offset + batch_size - 1)
            raw_values = self.read_range(spreadsheet_token, f"{sheet_id}!A{offset}:A{last_row}")
            for index in range(last_row - offset + 1):
                row_number = offset + index
                value = raw_values[index][0] if index < len(raw_values) and raw_values[index] else ""
                if value in (None, ""):
                    if first_blank_row is None:
                        first_blank_row = row_number
                    continue
                if first_blank_row is not None:
                    raise FeishuError(
                        f"raw date column has a blank before non-empty row {row_number}; refusing to alter it"
                    )
                if isinstance(value, bool):
                    raise FeishuError(f"raw date column has invalid boolean at row {row_number}")
                if isinstance(value, (int, float, Decimal)):
                    serial = float(value) if isinstance(value, (float, Decimal)) else value
                elif isinstance(value, str):
                    serial = feishu_date_serial(value.strip())
                else:
                    raise FeishuError(
                        f"raw date column has unsupported value at row {row_number}: {type(value).__name__}"
                    )
                normalized.append([serial])

        data_rows = len(normalized)
        converted_rows = 0
        for offset in range(0, data_rows, batch_size):
            chunk = normalized[offset : offset + batch_size]
            first_row = offset + 2
            last_row = first_row + len(chunk) - 1
            self.write_range(
                spreadsheet_token,
                f"{sheet_id}!A{first_row}:A{last_row}",
                chunk,
            )
            self.set_formatter(
                spreadsheet_token,
                f"{sheet_id}!A{first_row}:A{last_row}",
                FEISHU_DATE_FORMAT,
            )
            converted_rows += len(chunk)
        return {"data_rows": data_rows, "converted_rows": converted_rows}

    def assert_reference_sheet_empty(
        self,
        spreadsheet_token: str,
        sheet: Mapping[str, Any],
        headers: Sequence[str],
    ) -> None:
        sheet_id = str(sheet["sheet_id"])
        row_count = int(sheet.get("grid_properties", {}).get("row_count", 200))
        if row_count > 100_000:
            raise FeishuError("reference sheet is too large to prove empty; refusing to write")
        last_row = max(200, row_count)
        last_column = column_name(len(headers))
        values = self.read_range(spreadsheet_token, f"{sheet_id}!A1:{last_column}{last_row}")
        for index, row in enumerate(values):
            cells = list(row[: len(headers)])
            if index == 0 and cells == list(headers):
                continue
            if any(cell not in (None, "") for cell in cells):
                raise FeishuError(
                    f"reference sheet {sheet.get('title', sheet_id)!r} is not empty; refusing to overwrite"
                )

    def write_reference_sheet(
        self,
        spreadsheet_token: str,
        sheet: Mapping[str, Any],
        headers: Sequence[str],
        rows: Sequence[list[Any]],
        batch_size: int,
    ) -> None:
        batch_size = min(max(batch_size, 1), 500)
        sheet_id = str(sheet["sheet_id"])
        self.ensure_row_capacity(spreadsheet_token, sheet, len(rows) + 1)
        end_column = column_name(len(headers))
        self.write_range(
            spreadsheet_token,
            f"{sheet_id}!A1:{end_column}1",
            [list(headers)],
        )
        for offset in range(0, len(rows), batch_size):
            chunk = list(rows[offset : offset + batch_size])
            first_row = offset + 2
            last_row = first_row + len(chunk) - 1
            self.write_range(
                spreadsheet_token,
                f"{sheet_id}!A{first_row}:{end_column}{last_row}",
                chunk,
            )

    def sync_reference_sheets(
        self,
        spreadsheet_token: str,
        company_rows: Sequence[list[Any]],
        rate_rows: Sequence[list[Any]],
        batch_size: int,
    ) -> dict[str, int]:
        self.validate_spreadsheet_title(spreadsheet_token)
        sheets = self.list_sheets(spreadsheet_token)
        by_title = {str(sheet["title"]): sheet for sheet in sheets}
        missing = [title for title in (COMPANY_SHEET_TITLE, RATE_SHEET_TITLE) if title not in by_title]
        if missing:
            raise FeishuError(f"missing reference sheets: {missing}")
        company_sheet = by_title[COMPANY_SHEET_TITLE]
        rate_sheet = by_title[RATE_SHEET_TITLE]
        # Preflight both sheets before either one is changed.
        self.assert_reference_sheet_empty(spreadsheet_token, company_sheet, COMPANY_HEADERS)
        self.assert_reference_sheet_empty(spreadsheet_token, rate_sheet, RATE_HEADERS)
        self.write_reference_sheet(
            spreadsheet_token,
            company_sheet,
            COMPANY_HEADERS,
            company_rows,
            batch_size,
        )
        self.write_reference_sheet(
            spreadsheet_token,
            rate_sheet,
            RATE_HEADERS,
            rate_rows,
            batch_size,
        )
        return {"company_rows": len(company_rows), "rate_rows": len(rate_rows)}


def write_headers(client: FeishuClient, spreadsheet_token: str, sheet_ids: Mapping[str, str]) -> None:
    header_sets = {
        RAW_SHEET_TITLE: RAW_HEADERS,
        COMPANY_SHEET_TITLE: COMPANY_HEADERS,
        RATE_SHEET_TITLE: RATE_HEADERS,
    }
    for title, headers in header_sets.items():
        end_column = column_name(len(headers))
        client.write_range(
            spreadsheet_token,
            f"{sheet_ids[title]}!A1:{end_column}1",
            [headers],
        )


def write_raw_rows(
    client: FeishuClient,
    spreadsheet_token: str,
    sheet_id: str,
    values: Sequence[list[Any]],
    batch_size: int,
    start_row: int = 2,
) -> None:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if start_row < 2:
        raise ValueError("raw data cannot be written over the header row")
    batch_size = min(batch_size, 500)
    last_column = column_name(len(RAW_HEADERS))
    timestamp_column = column_name(len(RAW_HEADERS))
    for offset in range(0, len(values), batch_size):
        chunk = list(values[offset : offset + batch_size])
        first_row = start_row + offset
        last_row = first_row + len(chunk) - 1
        client.write_range(
            spreadsheet_token,
            f"{sheet_id}!A{first_row}:{last_column}{last_row}",
            chunk,
        )
        client.set_formatter(
            spreadsheet_token,
            f"{sheet_id}!A{first_row}:A{last_row}",
            FEISHU_DATE_FORMAT,
        )
        client.set_formatter(
            spreadsheet_token,
            f"{sheet_id}!{timestamp_column}{first_row}:{timestamp_column}{last_row}",
            FEISHU_DATETIME_FORMAT,
        )
        LOG.info("wrote rows %d-%d", first_row, last_row)


def date_chunks(start: date, end: date, chunk_days: int) -> Iterable[tuple[date, date]]:
    if chunk_days < 1:
        raise ValueError("chunk_days must be positive")
    current = start
    while current <= end:
        chunk_end = min(end, current + timedelta(days=chunk_days - 1))
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


def collect_rows(
    config: Mapping[str, str],
    start: date | None,
    end: date | None,
    days: int,
    query_chunk_days: int,
) -> tuple[date, date, list[dict[str, Any]]]:
    with MySQLReader(config) as reader:
        latest = reader.latest_common_date() if end is None else end
        if start is None:
            start = latest - timedelta(days=days - 1)
        if start > latest:
            raise DataQualityError(f"start date {start} is after end date {latest}")
        if (latest - start).days + 1 > days:
            raise DataQualityError(f"date range exceeds configured {days} days")
        all_metric_rows: list[dict[str, Any]] = []
        for chunk_start, chunk_end in date_chunks(start, latest, query_chunk_days):
            LOG.info("querying database chunk %s through %s", chunk_start, chunk_end)
            for spec in METRICS:
                rows = reader.fetch_metric(spec, chunk_start, chunk_end)
                LOG.info("read %d company-level rows from %s", len(rows), spec.table)
                all_metric_rows.extend(rows)
    return start, latest, merge_metric_rows(all_metric_rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-env", type=Path, default=Path(".env"))
    parser.add_argument("--spreadsheet-token", help="formal Feishu spreadsheet token")
    parser.add_argument("--folder-token", help="Feishu folder token for --bootstrap")
    parser.add_argument("--bootstrap", action="store_true", help="create a formal empty spreadsheet and headers")
    parser.add_argument("--dry-run", action="store_true", help="query and validate without writing Feishu")
    parser.add_argument(
        "--normalize-date-column",
        action="store_true",
        help="convert existing raw-sheet column A date text in place without reloading database data",
    )
    parser.add_argument(
        "--rename-spreadsheet-with-time",
        action="store_true",
        help="rename the formal spreadsheet with the current Beijing date/time without changing cells",
    )
    parser.add_argument(
        "--sync-reference-sheets",
        action="store_true",
        help="write MCP-derived company/rate reference rows without reloading the raw data sheet",
    )
    parser.add_argument(
        "--reference-json",
        help="reference JSON path, or '-' to read MCP-derived reference JSON from stdin",
    )
    parser.add_argument("--start-date", type=lambda value: parse_yyyymmdd(value.replace("-", "")))
    parser.add_argument("--end-date", type=lambda value: parse_yyyymmdd(value.replace("-", "")))
    parser.add_argument("--days", type=int, default=400)
    parser.add_argument("--query-chunk-days", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--log-level", default="INFO", choices=("WARNING", "INFO", "DEBUG"))
    return parser


def run(args: argparse.Namespace) -> int:
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s")
    config = load_runtime_config(args.project_env)

    if args.sync_reference_sheets:
        if args.bootstrap or args.dry_run or args.normalize_date_column or args.rename_spreadsheet_with_time:
            raise ConfigurationError(
                "--sync-reference-sheets cannot be combined with --bootstrap, --dry-run, "
                "--normalize-date-column, or --rename-spreadsheet-with-time"
            )
        if not args.spreadsheet_token:
            raise ConfigurationError("--sync-reference-sheets requires --spreadsheet-token")
        if not args.reference_json:
            raise ConfigurationError("--sync-reference-sheets requires --reference-json")
        company_rows, rate_rows = load_reference_rows(args.reference_json)
        client = FeishuClient(config)
        result = client.sync_reference_sheets(
            args.spreadsheet_token,
            company_rows,
            rate_rows,
            args.batch_size,
        )
        print(json.dumps({"spreadsheet_token_present": True, **result}, ensure_ascii=False))
        return 0

    if args.rename_spreadsheet_with_time:
        if args.bootstrap or args.dry_run or args.normalize_date_column:
            raise ConfigurationError(
                "--rename-spreadsheet-with-time cannot be combined with --bootstrap, --dry-run, "
                "or --normalize-date-column"
            )
        if not args.spreadsheet_token:
            raise ConfigurationError("--rename-spreadsheet-with-time requires --spreadsheet-token")
        client = FeishuClient(config)
        client.validate_spreadsheet_title(args.spreadsheet_token)
        new_title = f"{SPREADSHEET_TITLE_PREFIX} {datetime.now(BJ_TZ):%Y-%m-%d %H:%M}"
        client.rename_spreadsheet(args.spreadsheet_token, new_title)
        print(json.dumps({"title": new_title, "spreadsheet_token_present": True}, ensure_ascii=False))
        return 0

    if args.normalize_date_column:
        if args.bootstrap or args.dry_run:
            raise ConfigurationError("--normalize-date-column cannot be combined with --bootstrap or --dry-run")
        if not args.spreadsheet_token:
            raise ConfigurationError("--normalize-date-column requires --spreadsheet-token")
        client = FeishuClient(config)
        client.validate_spreadsheet_title(args.spreadsheet_token)
        sheets = client.list_sheets(args.spreadsheet_token)
        target_sheet = next(
            (sheet for sheet in sheets if str(sheet["title"]) == RAW_SHEET_TITLE),
            None,
        )
        if target_sheet is None:
            raise FeishuError(
                f"target spreadsheet has no {RAW_SHEET_TITLE!r} sheet; refusing to alter it"
            )
        result = client.normalize_raw_date_column(
            args.spreadsheet_token,
            target_sheet,
            args.batch_size,
        )
        print(json.dumps({"spreadsheet_token_present": True, **result}, ensure_ascii=False))
        return 0

    if args.bootstrap:
        if args.dry_run:
            raise ConfigurationError("--bootstrap and --dry-run cannot be used together")
        if not args.folder_token:
            raise ConfigurationError("--bootstrap requires --folder-token")
        client = FeishuClient(config)
        spreadsheet = client.create_spreadsheet(RAW_SHEET_TITLE, args.folder_token)
        token = str(spreadsheet["spreadsheet_token"])
        sheet_ids = client.ensure_layout(token)
        write_headers(client, token, sheet_ids)
        print(json.dumps({"title": RAW_SHEET_TITLE, "spreadsheet_url": spreadsheet.get("url"), "sheets": sheet_ids}, ensure_ascii=False))
        return 0

    start, end, rows = collect_rows(
        config,
        args.start_date,
        args.end_date,
        args.days,
        args.query_chunk_days,
    )
    written_at = datetime.now(BJ_TZ).replace(second=0, microsecond=0)
    values = rows_to_values(rows, written_at)
    summary = {"start_date": iso_date(start), "end_date": iso_date(end), "row_count": len(rows), "column_count": len(RAW_HEADERS)}
    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    if not args.spreadsheet_token:
        raise ConfigurationError("--spreadsheet-token is required unless --dry-run or --bootstrap is used")
    client = FeishuClient(config)
    # Resolve and validate the existing target read-only before any layout mutation.
    client.validate_spreadsheet_title(args.spreadsheet_token)
    existing_sheets = client.list_sheets(args.spreadsheet_token)
    existing_by_title = {str(sheet["title"]): sheet for sheet in existing_sheets}
    if RAW_SHEET_TITLE not in existing_by_title:
        raise FeishuError(
            f"target spreadsheet has no {RAW_SHEET_TITLE!r} sheet; run --bootstrap first"
        )
    target_sheet = existing_by_title[RAW_SHEET_TITLE]
    client.assert_sheet_empty(args.spreadsheet_token, target_sheet)
    # The target is proven empty. It is now safe to create missing reference sheets.
    sheet_ids = client.ensure_layout(args.spreadsheet_token)
    refreshed_sheets = client.list_sheets(args.spreadsheet_token)
    target_sheet = next(
        sheet for sheet in refreshed_sheets if str(sheet["sheet_id"]) == sheet_ids[RAW_SHEET_TITLE]
    )
    client.ensure_row_capacity(args.spreadsheet_token, target_sheet, len(values) + 1)
    client.write_range(
        args.spreadsheet_token,
        f"{sheet_ids[RAW_SHEET_TITLE]}!A1:{column_name(len(RAW_HEADERS))}1",
        [RAW_HEADERS],
    )
    write_raw_rows(client, args.spreadsheet_token, sheet_ids[RAW_SHEET_TITLE], values, args.batch_size)
    client.verify_written_rows(args.spreadsheet_token, sheet_ids[RAW_SHEET_TITLE], values)
    print(json.dumps(summary | {"spreadsheet_token_present": True}, ensure_ascii=False))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(build_parser().parse_args(argv))
    except (ConfigurationError, DataQualityError, FeishuError, pymysql.MySQLError, requests.RequestException) as exc:
        LOG.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
