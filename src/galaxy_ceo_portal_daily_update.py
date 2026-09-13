#!/usr/bin/env python3
"""Incrementally maintain the MGW raw-data Feishu spreadsheet.

The scheduled entry point checks the Feishu sheet first, waits for the common
database source to contain yesterday's Beijing date, fills date/key gaps, and
keeps a rolling window of 400 business days.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import math
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pymysql
import requests

# Make direct execution (`python src/galaxy_ceo_portal_daily_update.py`) use the
# repository root just like module execution (`python -m src...`).
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.galaxy_ceo_portal_raw_data import (
    BJ_TZ,
    ConfigurationError,
    FEISHU_DATE_FORMAT,
    FeishuClient,
    FeishuError,
    DataQualityError,
    MySQLReader,
    RAW_HEADERS,
    RAW_SHEET_TITLE,
    SPREADSHEET_TITLE_PREFIX,
    collect_rows,
    load_runtime_config,
    render_package,
    rows_to_values,
    write_raw_rows,
)


LOG = logging.getLogger("galaxy_ceo_portal_daily_update")
FEISHU_EPOCH = date(1899, 12, 30)
DEFAULT_RETENTION_DAYS = 400
DEFAULT_RETRY_COUNT = 3
DEFAULT_RETRY_INTERVAL_SECONDS = 3_600
DEFAULT_BATCH_SIZE = 500
DEFAULT_LOCK_FILE = Path("/tmp/galaxy_ceo_portal_daily_update.lock")

RawKey = tuple[str, str, int, str]


class UpdateError(RuntimeError):
    """Raised when a scheduled update cannot safely complete."""


@dataclass(frozen=True)
class ExistingRawRow:
    row_number: int
    business_date: date
    key: RawKey


@dataclass(frozen=True)
class RawSnapshot:
    rows: tuple[ExistingRawRow, ...]
    keys: frozenset[RawKey]
    dates: frozenset[date]

    @property
    def data_rows(self) -> int:
        return len(self.rows)

    @property
    def max_date(self) -> date | None:
        return max(self.dates) if self.dates else None


@dataclass(frozen=True)
class UpdatePlan:
    target_start: date
    target_end: date
    fetch_ranges: tuple[tuple[date, date], ...]
    expired_rows: tuple[ExistingRawRow, ...]


def parse_feishu_date(value: Any) -> date:
    """Read either a native Feishu date serial or the legacy ISO text form."""

    if value in (None, ""):
        raise UpdateError("raw date cell is empty")
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
            raise UpdateError(f"invalid Feishu date value: {value!r}") from exc
    if isinstance(value, bool):
        raise UpdateError(f"invalid Feishu date value: {value!r}")
    if not isinstance(value, (int, float, Decimal)):
        raise UpdateError(f"unsupported Feishu date value type: {type(value).__name__}")
    if isinstance(value, float) and not math.isfinite(value):
        raise UpdateError(f"invalid Feishu date serial: {value!r}")
    try:
        serial = Decimal(str(value))
    except InvalidOperation as exc:
        raise UpdateError(f"invalid Feishu date serial: {value!r}") from exc
    if serial != serial.to_integral_value():
        raise UpdateError(f"date serial has a time component: {value!r}")
    serial_int = int(serial)
    if serial_int < 1 or serial_int > 200_000:
        raise UpdateError(f"Feishu date serial is outside the safe range: {value!r}")
    return FEISHU_EPOCH + timedelta(days=serial_int)


def parse_int_cell(value: Any, label: str) -> int:
    if value in (None, ""):
        raise UpdateError(f"{label} cell is empty")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise UpdateError(f"invalid {label}: {value!r}") from exc
    if number != number.to_integral_value():
        raise UpdateError(f"{label} is not an integer: {value!r}")
    return int(number)


def existing_key(row: Sequence[Any], row_number: int) -> tuple[date, RawKey]:
    if len(row) < 4 or row[0] in (None, ""):
        raise UpdateError(f"raw row {row_number} has no date")
    business_date = parse_feishu_date(row[0])
    business = str(row[1]).strip() if row[1] not in (None, "") else ""
    if business not in {"DTT", "DTH"}:
        raise UpdateError(f"raw row {row_number} has invalid business: {business!r}")
    company_id = parse_int_cell(row[2], f"company ID at row {row_number}")
    package = str(row[3]).strip() if row[3] not in (None, "") else ""
    if not package:
        raise UpdateError(f"raw row {row_number} has an empty package value")
    return business_date, (business_date.isoformat(), business, company_id, package)


def read_raw_snapshot(
    client: FeishuClient,
    spreadsheet_token: str,
    sheet: Mapping[str, Any],
    batch_size: int,
) -> RawSnapshot:
    """Read only A:D to identify existing rows, dates, and append keys."""

    header = client.read_range(spreadsheet_token, f"{sheet['sheet_id']}!A1:J1")
    if header != [RAW_HEADERS]:
        raise FeishuError("raw sheet header does not match the expected layout")
    row_count = int(sheet.get("grid_properties", {}).get("row_count", 200))
    if row_count > 1_000_000:
        raise FeishuError("raw sheet is too large to scan safely")
    batch_size = min(max(batch_size, 1), DEFAULT_BATCH_SIZE)
    rows: list[ExistingRawRow] = []
    first_blank_row: int | None = None
    for offset in range(2, max(row_count, 2) + 1, batch_size):
        last_row = min(max(row_count, 2), offset + batch_size - 1)
        values = client.read_range(spreadsheet_token, f"{sheet['sheet_id']}!A{offset}:D{last_row}")
        for index in range(last_row - offset + 1):
            row_number = offset + index
            row = list(values[index]) if index < len(values) else []
            if not any(cell not in (None, "") for cell in row):
                if first_blank_row is None:
                    first_blank_row = row_number
                continue
            if first_blank_row is not None:
                raise FeishuError(
                    f"raw sheet has a blank row before non-empty row {row_number}; refusing to update"
                )
            business_date, key = existing_key(row, row_number)
            rows.append(ExistingRawRow(row_number, business_date, key))
    return RawSnapshot(
        rows=tuple(rows),
        keys=frozenset(row.key for row in rows),
        dates=frozenset(row.business_date for row in rows),
    )


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
    snapshot: RawSnapshot,
    target_end: date,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> UpdatePlan:
    if retention_days < 1:
        raise ValueError("retention_days must be positive")
    target_start = target_end - timedelta(days=retention_days - 1)
    expected_dates = set(iter_dates(target_start, target_end))
    missing_dates = expected_dates - set(snapshot.dates)
    # Always re-read the newest target date so a failed mid-batch run is repaired.
    missing_dates.add(target_end)
    expired_rows = tuple(row for row in snapshot.rows if row.business_date < target_start)
    return UpdatePlan(
        target_start=target_start,
        target_end=target_end,
        fetch_ranges=date_ranges(missing_dates),
        expired_rows=expired_rows,
    )


def source_key(row: Mapping[str, Any]) -> RawKey:
    return (
        str(row["date"]),
        str(row["business"]),
        int(row["company_id"]),
        render_package(row["package_class"]),
    )


def missing_source_rows(
    source_rows: Sequence[dict[str, Any]],
    existing_keys: Iterable[RawKey],
) -> list[dict[str, Any]]:
    seen = set(existing_keys)
    missing: list[dict[str, Any]] = []
    for row in source_rows:
        key = source_key(row)
        if key in seen:
            continue
        seen.add(key)
        missing.append(row)
    return missing


def deletion_ranges(
    expired_rows: Sequence[ExistingRawRow],
    max_rows_per_request: int = 5_000,
) -> tuple[tuple[int, int], ...]:
    """Return inclusive 1-based row ranges in bottom-to-top deletion order."""

    if max_rows_per_request < 1:
        raise ValueError("max_rows_per_request must be positive")
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


def fetch_source_rows(
    config: Mapping[str, str],
    ranges: Sequence[tuple[date, date]],
    query_chunk_days: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for start, end in ranges:
        _, _, range_rows = collect_rows(
            config,
            start=start,
            end=end,
            days=(end - start).days + 1,
            query_chunk_days=query_chunk_days,
        )
        rows.extend(range_rows)
    return rows


def find_raw_sheet(client: FeishuClient, spreadsheet_token: str) -> Mapping[str, Any]:
    for sheet in client.list_sheets(spreadsheet_token):
        if str(sheet.get("title")) == RAW_SHEET_TITLE:
            return sheet
    raise FeishuError(f"target spreadsheet has no {RAW_SHEET_TITLE!r} sheet")


def apply_update(
    client: FeishuClient,
    spreadsheet_token: str,
    snapshot: RawSnapshot,
    raw_sheet: Mapping[str, Any],
    plan: UpdatePlan,
    source_rows: Sequence[dict[str, Any]],
    now: datetime,
    batch_size: int,
    dry_run: bool,
) -> dict[str, Any]:
    append_rows = missing_source_rows(source_rows, snapshot.keys)
    expired_ranges = deletion_ranges(plan.expired_rows)
    result: dict[str, Any] = {
        "target_start_date": plan.target_start.isoformat(),
        "target_end_date": plan.target_end.isoformat(),
        "feishu_max_date": snapshot.max_date.isoformat() if snapshot.max_date else None,
        "source_rows_read": len(source_rows),
        "rows_to_append": len(append_rows),
        "rows_to_delete": len(plan.expired_rows),
        "delete_ranges": len(expired_ranges),
    }
    if dry_run:
        result["dry_run"] = True
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
        write_raw_rows(
            client,
            spreadsheet_token,
            str(refreshed_sheet["sheet_id"]),
            rows_to_values(append_rows, now),
            batch_size,
            start_row=remaining_rows + 2,
        )

    new_title = f"{SPREADSHEET_TITLE_PREFIX} {now.astimezone(BJ_TZ):%Y-%m-%d %H:%M}"
    client.rename_spreadsheet(spreadsheet_token, new_title)
    result["title"] = new_title
    return result


def update_once(
    config: Mapping[str, str],
    spreadsheet_token: str,
    retention_days: int,
    query_chunk_days: int,
    batch_size: int,
    now: datetime | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    now = now or datetime.now(BJ_TZ)
    now = now.astimezone(BJ_TZ)
    client = FeishuClient(config)
    client.validate_spreadsheet_title(spreadsheet_token)
    raw_sheet = find_raw_sheet(client, spreadsheet_token)
    # This read intentionally precedes the database readiness check.
    snapshot = read_raw_snapshot(client, spreadsheet_token, raw_sheet, batch_size)
    yesterday = now.date() - timedelta(days=1)
    with MySQLReader(config) as reader:
        source_latest = reader.latest_common_date()
    LOG.info(
        "Feishu max business date=%s; database latest common date=%s; Beijing yesterday=%s",
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
        }

    target_end = min(source_latest, yesterday)
    plan = build_update_plan(snapshot, target_end, retention_days)
    source_rows = fetch_source_rows(config, plan.fetch_ranges, query_chunk_days)
    result = apply_update(
        client,
        spreadsheet_token,
        snapshot,
        raw_sheet,
        plan,
        source_rows,
        now,
        batch_size,
        dry_run,
    )
    result.update({"ready": True, "source_latest_date": source_latest.isoformat()})
    return result


def run_with_retries(args: argparse.Namespace) -> int:
    if args.max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    if args.retry_interval_seconds < 0:
        raise ValueError("retry_interval_seconds must be non-negative")
    config = load_runtime_config(args.project_env)
    spreadsheet_token = (args.spreadsheet_token or config.get("GALAXY_CEO_PORTAL_SPREADSHEET_TOKEN", "")).strip()
    if not spreadsheet_token:
        raise ConfigurationError(
            "--spreadsheet-token or GALAXY_CEO_PORTAL_SPREADSHEET_TOKEN is required"
        )
    last_result: dict[str, Any] | None = None
    for attempt in range(args.max_retries + 1):
        LOG.info("daily update attempt %d/%d", attempt + 1, args.max_retries + 1)
        try:
            result = update_once(
                config,
                spreadsheet_token,
                args.retention_days,
                args.query_chunk_days,
                args.batch_size,
                dry_run=args.dry_run,
            )
            last_result = result
            if result.get("ready"):
                print(json.dumps(result, ensure_ascii=False))
                return 0
            LOG.warning(
                "database is not ready for yesterday; will retry if attempts remain: %s",
                result,
            )
        except (FeishuError, pymysql.MySQLError, requests.RequestException) as exc:
            if attempt >= args.max_retries:
                raise
            LOG.warning("transient update failure: %s", exc)
        if attempt < args.max_retries:
            LOG.info("sleeping %s seconds before the next attempt", args.retry_interval_seconds)
            time.sleep(args.retry_interval_seconds)
    raise UpdateError(
        "database did not reach yesterday after the configured retries; "
        f"last_result={last_result}"
    )


@contextmanager
def process_lock(path: Path) -> Iterable[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise UpdateError(f"another daily update is already running: {path}") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-env", type=Path, default=Path(".env"))
    parser.add_argument(
        "--spreadsheet-token",
        help="formal spreadsheet token; defaults to GALAXY_CEO_PORTAL_SPREADSHEET_TOKEN",
    )
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    parser.add_argument("--query-chunk-days", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-retries", type=int, default=DEFAULT_RETRY_COUNT)
    parser.add_argument(
        "--retry-interval-seconds",
        type=int,
        default=DEFAULT_RETRY_INTERVAL_SECONDS,
    )
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
        UpdateError,
        ValueError,
        pymysql.MySQLError,
        requests.RequestException,
    ) as exc:
        LOG.error("%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
