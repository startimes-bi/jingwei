#!/usr/bin/env python3
"""Import the Nova daily business spreadsheet into an isolated SQLite store.

The spreadsheet is read-only in this phase.  Each successful source snapshot is
recorded as an import batch and each business row is upserted by its stable
date/business/company/package key.  The importer never writes back to Feishu
and never stores credentials or the raw spreadsheet payload.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.nova_feishu import ConfigurationError, FeishuClient, FeishuError, read_env_file, required


LOG = logging.getLogger("nova_spreadsheet_import")
FEISHU_EPOCH = date(1899, 12, 30)
DEFAULT_SHEET_TITLE = "Nova 每日业务数据"
MAX_SOURCE_ROWS = 100_000
READ_BATCH_SIZE = 500

NOVA_HEADERS = (
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
)
BUSINESS_TYPES = frozenset({"DTT", "DTH"})
COUNT_FIELDS = ("new_users", "recharge_users", "deduction_users")
MONEY_FIELDS = ("recharge_revenue_usd_before_tax", "deduction_revenue_usd_after_tax")


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS nova_import_batches (
    id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_sheet_id TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL UNIQUE,
    imported_at_utc TEXT NOT NULL,
    source_rows INTEGER NOT NULL DEFAULT 0,
    inserted_or_updated_rows INTEGER NOT NULL DEFAULT 0,
    rejected_rows INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error_summary TEXT
);

CREATE TABLE IF NOT EXISTS nova_daily_metrics (
    id INTEGER PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    business_date TEXT NOT NULL,
    business_type TEXT NOT NULL,
    company_id INTEGER NOT NULL,
    package_name TEXT NOT NULL,
    new_users INTEGER,
    recharge_users INTEGER,
    recharge_revenue_usd_before_tax NUMERIC,
    deduction_users INTEGER,
    deduction_revenue_usd_after_tax NUMERIC,
    source_updated_at_bj TEXT,
    source_row_number INTEGER NOT NULL,
    import_batch_id INTEGER NOT NULL REFERENCES nova_import_batches(id),
    updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_nova_daily_metrics_date
    ON nova_daily_metrics(business_date);
CREATE INDEX IF NOT EXISTS idx_nova_daily_metrics_company_package
    ON nova_daily_metrics(company_id, package_name, business_date);
CREATE INDEX IF NOT EXISTS idx_nova_daily_metrics_business
    ON nova_daily_metrics(business_type, business_date);
"""


@dataclass(frozen=True)
class NovaRow:
    source_row_number: int
    business_date: str
    business_type: str
    company_id: int
    package_name: str
    new_users: int | None
    recharge_users: int | None
    recharge_revenue_usd_before_tax: str | None
    deduction_users: int | None
    deduction_revenue_usd_after_tax: str | None
    source_updated_at_bj: str | None

    @property
    def source_key(self) -> str:
        return "|".join(
            (
                self.business_date,
                self.business_type,
                str(self.company_id),
                self.package_name,
            )
        )

    def canonical(self) -> dict[str, Any]:
        return {
            "business_date": self.business_date,
            "business_type": self.business_type,
            "company_id": self.company_id,
            "package_name": self.package_name,
            "new_users": self.new_users,
            "recharge_users": self.recharge_users,
            "recharge_revenue_usd_before_tax": self.recharge_revenue_usd_before_tax,
            "deduction_users": self.deduction_users,
            "deduction_revenue_usd_after_tax": self.deduction_revenue_usd_after_tax,
            "source_updated_at_bj": self.source_updated_at_bj,
        }


class NovaDataQualityError(ValueError):
    """Raised when the source cannot be imported without ambiguous data."""


def parse_feishu_date(value: Any) -> str:
    if value in (None, ""):
        raise NovaDataQualityError("date is empty")
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
            try:
                return datetime.strptime(text, fmt).date().isoformat()
            except ValueError:
                pass
        try:
            value = Decimal(text)
        except InvalidOperation as exc:
            raise NovaDataQualityError("date is invalid") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise NovaDataQualityError("date has an unsupported type")
    try:
        serial = Decimal(str(value))
    except InvalidOperation as exc:
        raise NovaDataQualityError("date serial is invalid") from exc
    if serial != serial.to_integral_value():
        raise NovaDataQualityError("date serial has a time component")
    serial_int = int(serial)
    if serial_int < 1 or serial_int > 200_000:
        raise NovaDataQualityError("date serial is outside the safe range")
    return (FEISHU_EPOCH + timedelta(days=serial_int)).isoformat()


def parse_integer(value: Any, field: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise NovaDataQualityError(f"{field} is not an integer") from exc
    if number != number.to_integral_value() or number < 0:
        raise NovaDataQualityError(f"{field} is not a non-negative integer")
    return int(number)


def parse_money(value: Any, field: str) -> str | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value).strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, AttributeError) as exc:
        raise NovaDataQualityError(f"{field} is not a valid amount") from exc
    if number < 0:
        raise NovaDataQualityError(f"{field} is negative")
    return format(number, "f")


def parse_datetime(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        try:
            days = Decimal(str(value))
            whole_days = int(days)
            seconds = int((days - whole_days) * 86_400)
            return (
                datetime.combine(FEISHU_EPOCH + timedelta(days=whole_days), datetime.min.time())
                + timedelta(seconds=seconds)
            ).isoformat(sep=" ")
        except (ValueError, TypeError, InvalidOperation) as exc:
            raise NovaDataQualityError("updated_at is invalid") from exc
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).isoformat(sep=" ")
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat(sep=" ")
    except ValueError as exc:
        raise NovaDataQualityError("updated_at is invalid") from exc


def normalize_row(raw: Sequence[Any], source_row_number: int) -> NovaRow:
    cells = list(raw) + [None] * max(0, len(NOVA_HEADERS) - len(raw))
    business_date = parse_feishu_date(cells[0])
    business_type = str(cells[1] or "").strip().upper()
    if business_type not in BUSINESS_TYPES:
        raise NovaDataQualityError("business type is not DTT or DTH")
    company_id = parse_integer(cells[2], "company id")
    if company_id is None or company_id < 1:
        raise NovaDataQualityError("company id is missing")
    package_name = str(cells[3] or "").strip()
    if not package_name:
        raise NovaDataQualityError("package is empty")
    return NovaRow(
        source_row_number=source_row_number,
        business_date=business_date,
        business_type=business_type,
        company_id=company_id,
        package_name=package_name,
        new_users=parse_integer(cells[4], "new users"),
        recharge_users=parse_integer(cells[5], "recharge users"),
        recharge_revenue_usd_before_tax=parse_money(cells[6], "recharge revenue"),
        deduction_users=parse_integer(cells[7], "deduction users"),
        deduction_revenue_usd_after_tax=parse_money(cells[8], "deduction revenue"),
        source_updated_at_bj=parse_datetime(cells[9]),
    )


def read_source_rows(
    client: FeishuClient,
    spreadsheet_token: str,
    sheet: Mapping[str, Any],
    batch_size: int = READ_BATCH_SIZE,
) -> tuple[list[NovaRow], int, list[str]]:
    sheet_id = required({"sheet_id": str(sheet.get("sheet_id", ""))}, "sheet_id")
    header = client.read_range(spreadsheet_token, f"{sheet_id}!A1:J1")
    if header != [list(NOVA_HEADERS)]:
        raise FeishuError("Nova source sheet header does not match the expected 10-column layout")
    row_count = int(sheet.get("grid_properties", {}).get("row_count", 200))
    if row_count > MAX_SOURCE_ROWS:
        raise FeishuError("Nova source sheet is too large to scan safely")

    rows: list[NovaRow] = []
    errors: list[str] = []
    saw_blank = False
    for start in range(2, max(row_count, 2) + 1, min(max(batch_size, 1), READ_BATCH_SIZE)):
        end = min(row_count, start + min(max(batch_size, 1), READ_BATCH_SIZE) - 1)
        values = client.read_range(spreadsheet_token, f"{sheet_id}!A{start}:J{end}")
        for offset in range(end - start + 1):
            row_number = start + offset
            raw = list(values[offset]) if offset < len(values) else []
            if not any(cell not in (None, "") for cell in raw):
                saw_blank = True
                continue
            if saw_blank:
                raise NovaDataQualityError(f"non-empty row follows a blank row at source row {row_number}")
            try:
                rows.append(normalize_row(raw, row_number))
            except NovaDataQualityError as exc:
                errors.append(f"row {row_number}: {exc}")
    return rows, row_count - 1, errors


def source_fingerprint(rows: Iterable[NovaRow]) -> str:
    payload = [row.canonical() for row in rows]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def select_sheet(
    client: FeishuClient,
    spreadsheet_token: str,
    sheet_id: str | None,
    sheet_title: str,
) -> Mapping[str, Any]:
    sheets = client.list_sheets(spreadsheet_token)
    if sheet_id:
        for sheet in sheets:
            if str(sheet.get("sheet_id")) == sheet_id:
                return sheet
        raise FeishuError("requested Nova source sheet id was not found")
    for sheet in sheets:
        if str(sheet.get("title")) == sheet_title:
            return sheet
    raise FeishuError(f"requested Nova source sheet title was not found: {sheet_title!r}")


def import_rows(
    database: Path,
    source_name: str,
    source_sheet_id: str,
    rows: Sequence[NovaRow],
    rejected_errors: Sequence[str] = (),
) -> dict[str, Any]:
    database.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fingerprint = source_fingerprint(rows)
    imported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    error_summary = "; ".join(rejected_errors[:20]) or None

    connection = sqlite3.connect(database)
    try:
        connection.executescript(SCHEMA)
        existing = connection.execute(
            "SELECT id, status FROM nova_import_batches WHERE source_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        if existing:
            return {
                "status": "already_imported",
                "batch_id": existing[0],
                "source_rows": len(rows),
                "rejected_rows": len(rejected_errors),
            }
        if rejected_errors:
            raise NovaDataQualityError(
                f"source contains {len(rejected_errors)} invalid row(s); first error: {rejected_errors[0]}"
            )

        with connection:
            batch_id = connection.execute(
                """INSERT INTO nova_import_batches(
                    source_name, source_sheet_id, source_fingerprint, imported_at_utc,
                    source_rows, status
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (source_name, source_sheet_id, fingerprint, imported_at, len(rows), "running"),
            ).lastrowid
            for row in rows:
                connection.execute(
                    """INSERT INTO nova_daily_metrics(
                        source_key, business_date, business_type, company_id, package_name,
                        new_users, recharge_users, recharge_revenue_usd_before_tax,
                        deduction_users, deduction_revenue_usd_after_tax,
                        source_updated_at_bj, source_row_number, import_batch_id, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_key) DO UPDATE SET
                        business_date=excluded.business_date,
                        business_type=excluded.business_type,
                        company_id=excluded.company_id,
                        package_name=excluded.package_name,
                        new_users=excluded.new_users,
                        recharge_users=excluded.recharge_users,
                        recharge_revenue_usd_before_tax=excluded.recharge_revenue_usd_before_tax,
                        deduction_users=excluded.deduction_users,
                        deduction_revenue_usd_after_tax=excluded.deduction_revenue_usd_after_tax,
                        source_updated_at_bj=excluded.source_updated_at_bj,
                        source_row_number=excluded.source_row_number,
                        import_batch_id=excluded.import_batch_id,
                        updated_at_utc=excluded.updated_at_utc""",
                    (
                        row.source_key,
                        row.business_date,
                        row.business_type,
                        row.company_id,
                        row.package_name,
                        row.new_users,
                        row.recharge_users,
                        row.recharge_revenue_usd_before_tax,
                        row.deduction_users,
                        row.deduction_revenue_usd_after_tax,
                        row.source_updated_at_bj,
                        row.source_row_number,
                        batch_id,
                        imported_at,
                    ),
                )
            connection.execute(
                """UPDATE nova_import_batches
                   SET inserted_or_updated_rows = ?, status = ?, error_summary = ?
                   WHERE id = ?""",
                (len(rows), "imported", error_summary, batch_id),
            )
        return {
            "status": "imported",
            "batch_id": batch_id,
            "source_rows": len(rows),
            "inserted_or_updated_rows": len(rows),
            "rejected_rows": len(rejected_errors),
        }
    finally:
        connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True, help="controlled Feishu env file")
    parser.add_argument("--spreadsheet-token", required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--sheet-id")
    group.add_argument("--sheet-title", default=DEFAULT_SHEET_TITLE)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=READ_BATCH_SIZE)
    parser.add_argument("--dry-run", action="store_true", help="read and validate without writing SQLite")
    parser.add_argument("--log-level", default="INFO", choices=("WARNING", "INFO", "DEBUG"))
    return parser


def run(args: argparse.Namespace) -> int:
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s")
    config = read_env_file(args.env_file)
    client = FeishuClient(config)
    sheet = select_sheet(client, args.spreadsheet_token, args.sheet_id, args.sheet_title)
    rows, scanned_rows, errors = read_source_rows(client, args.spreadsheet_token, sheet, args.batch_size)
    result: dict[str, Any] = {
        "status": "validated",
        "sheet_title": str(sheet.get("title", "")),
        "sheet_id_present": bool(sheet.get("sheet_id")),
        "scanned_rows": scanned_rows,
        "valid_rows": len(rows),
        "rejected_rows": len(errors),
    }
    if args.dry_run:
        if errors:
            result["first_errors"] = errors[:5]
        print(json.dumps(result, ensure_ascii=False))
        return 2 if errors else 0
    result.update(
        import_rows(
            args.database,
            str(sheet.get("title", args.sheet_title)),
            str(sheet.get("sheet_id", args.sheet_id or "")),
            rows,
            errors,
        )
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(build_parser().parse_args(argv))
    except (ConfigurationError, FeishuError, NovaDataQualityError, sqlite3.Error) as exc:
        LOG.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
