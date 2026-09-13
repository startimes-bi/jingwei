import unittest
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.galaxy_ceo_portal_raw_data import (
    METRICS,
    RAW_HEADERS,
    SPREADSHEET_TITLE_PATTERN,
    date_chunks,
    feishu_date_serial,
    feishu_datetime_serial,
    is_reconciled_zero_total_placeholder,
    merge_metric_rows,
    render_package,
    rows_to_values,
)


class GalaxyCeoPortalTests(unittest.TestCase):
    def test_merge_keeps_company_total_and_package_rows_without_summing_children(self):
        source = [
            {"date": "2026-09-11", "business": "DTT", "company_id": 7, "package_class": None, "metric": "recharge_count", "value": 25528},
            {"date": "2026-09-11", "business": "DTT", "company_id": 7, "package_class": "Nova包", "metric": "recharge_count", "value": 15995},
            {"date": "2026-09-11", "business": "DTT", "company_id": 7, "package_class": "Nova包", "metric": "recharge_money", "value": Decimal("25012.71")},
        ]
        rows = merge_metric_rows(source)
        self.assertEqual(len(rows), 2)
        total = next(row for row in rows if row["package_class"] is None)
        nova = next(row for row in rows if row["package_class"] == "Nova包")
        self.assertEqual(total["recharge_count"], 25528)
        self.assertEqual(nova["recharge_count"], 15995)
        self.assertEqual(nova["recharge_money"], Decimal("25012.71"))

    def test_null_package_is_explicitly_rendered_as_company_total(self):
        self.assertEqual(render_package(None), "公司合计（package_class=NULL）")

    def test_zero_recharge_total_is_allowed_only_after_detail_reconciliation(self):
        spec = next(metric for metric in METRICS if metric.name == "recharge_money")
        raw = {
            "load_date": "20251110",
            "business": "DTT",
            "company_id": 2,
            "package_class": None,
            "source_rows": 2,
            "populated_values": 2,
            "min_value": 0.0,
            "max_value": 761.76,
        }
        key = ("20251110", "DTT", 2)
        self.assertTrue(is_reconciled_zero_total_placeholder(spec, raw, {key: Decimal("761.76")}))
        self.assertFalse(is_reconciled_zero_total_placeholder(spec, raw, {key: Decimal("761.74")}))

    def test_timestamp_uses_beijing_wall_clock(self):
        value = datetime(2026, 9, 13, 12, 7, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertAlmostEqual(feishu_datetime_serial(value), 46278.50486111111)

    def test_date_uses_date_only_serial_without_timezone(self):
        self.assertEqual(feishu_date_serial("2026-09-11"), 46276)

    def test_timestamped_spreadsheet_title_is_accepted(self):
        self.assertTrue(SPREADSHEET_TITLE_PATTERN.fullmatch("银河CEO门户原始数据"))
        self.assertTrue(SPREADSHEET_TITLE_PATTERN.fullmatch("银河CEO门户原始数据 2026-09-13 16:35"))
        self.assertFalse(SPREADSHEET_TITLE_PATTERN.fullmatch("其他表格 2026-09-13 16:35"))

    def test_date_chunks_cover_the_range_without_overlap(self):
        chunks = list(date_chunks(datetime(2026, 1, 1).date(), datetime(2026, 2, 5).date(), 30))
        self.assertEqual(chunks, [
            (datetime(2026, 1, 1).date(), datetime(2026, 1, 30).date()),
            (datetime(2026, 1, 31).date(), datetime(2026, 2, 5).date()),
        ])

    def test_output_column_order_and_missing_values(self):
        rows = [
            {
                "date": "2026-09-11",
                "business": "DTT",
                "company_id": 7,
                "package_class": "Nova包",
                "new_users": 0,
                "recharge_count": None,
                "recharge_money": Decimal("1.20"),
                "deduction_count": 4,
                "deduction_money": None,
            }
        ]
        values = rows_to_values(rows, datetime(2026, 9, 13, 12, 7, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertEqual(len(RAW_HEADERS), 10)
        self.assertEqual(values[0][:9], [46276, "DTT", 7, "Nova包", 0, "", 1.2, 4, ""])
        self.assertEqual(values[0][9], 46278.50486111111)


if __name__ == "__main__":
    unittest.main()
