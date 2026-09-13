import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.nova_spreadsheet_import import (
    NovaDataQualityError,
    import_rows,
    normalize_row,
    parse_datetime,
    parse_feishu_date,
)


class NovaSpreadsheetImportTests(unittest.TestCase):
    def test_parses_native_date_and_timestamp_serials(self):
        self.assertEqual(parse_feishu_date(46276), "2026-09-11")
        self.assertEqual(parse_datetime(46278.5), "2026-09-13 12:00:00")

    def test_normalizes_row_and_builds_stable_key(self):
        row = normalize_row(
            [46276, "dtt", 7, "Nova包", 1, 2, 3.4, 5, "6.70", 46278.5],
            2,
        )
        self.assertEqual(row.business_type, "DTT")
        self.assertEqual(row.source_key, "2026-09-11|DTT|7|Nova包")
        self.assertEqual(row.recharge_revenue_usd_before_tax, "3.40")

    def test_rejects_unsupported_business_type(self):
        with self.assertRaises(NovaDataQualityError):
            normalize_row([46276, "COMBO", 7, "Nova包"], 2)

    def test_import_is_idempotent_and_upserts_by_business_key(self):
        rows = [normalize_row([46276, "DTT", 7, "Nova包", 1, 2, 3.4, 5, 6.7, ""], 2)]
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "nova.sqlite3"
            first = import_rows(database, "Nova 每日业务数据", "sheet-1", rows)
            second = import_rows(database, "Nova 每日业务数据", "sheet-1", rows)
            self.assertEqual(first["status"], "imported")
            self.assertEqual(second["status"], "already_imported")
            connection = sqlite3.connect(database)
            try:
                count = connection.execute("SELECT COUNT(*) FROM nova_daily_metrics").fetchone()[0]
                self.assertEqual(count, 1)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
