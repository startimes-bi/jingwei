import unittest
from datetime import date

from src.galaxy_ceo_portal_daily_update import (
    ExistingRawRow,
    RawSnapshot,
    build_update_plan,
    date_ranges,
    deletion_ranges,
    parse_feishu_date,
)


class DailyUpdateTests(unittest.TestCase):
    def test_parse_native_serial_and_legacy_text(self):
        self.assertEqual(parse_feishu_date(46276), date(2026, 9, 11))
        self.assertEqual(parse_feishu_date("2026-09-11"), date(2026, 9, 11))

    def test_plan_fetches_date_gaps_and_expires_old_rows(self):
        rows = (
            ExistingRawRow(2, date(2026, 9, 8), ("2026-09-08", "DTT", 7, "总计")),
            ExistingRawRow(3, date(2026, 9, 10), ("2026-09-10", "DTT", 7, "总计")),
            ExistingRawRow(4, date(2026, 9, 12), ("2026-09-12", "DTT", 7, "总计")),
        )
        snapshot = RawSnapshot(
            rows=rows,
            keys=frozenset(row.key for row in rows),
            dates=frozenset(row.business_date for row in rows),
        )
        plan = build_update_plan(snapshot, date(2026, 9, 12), retention_days=3)
        self.assertEqual(plan.target_start, date(2026, 9, 10))
        self.assertEqual(plan.fetch_ranges, ((date(2026, 9, 11), date(2026, 9, 12)),))
        self.assertEqual([row.row_number for row in plan.expired_rows], [2])

    def test_date_ranges_are_contiguous_and_sorted(self):
        self.assertEqual(
            date_ranges([date(2026, 9, 12), date(2026, 9, 10), date(2026, 9, 11), date(2026, 9, 8)]),
            ((date(2026, 9, 8), date(2026, 9, 8)), (date(2026, 9, 10), date(2026, 9, 12))),
        )

    def test_deletion_ranges_are_bottom_to_top(self):
        rows = [
            ExistingRawRow(2, date(2026, 1, 1), ("2026-01-01", "DTT", 7, "总计")),
            ExistingRawRow(3, date(2026, 1, 2), ("2026-01-02", "DTT", 7, "总计")),
            ExistingRawRow(10, date(2026, 1, 3), ("2026-01-03", "DTT", 7, "总计")),
            ExistingRawRow(11, date(2026, 1, 4), ("2026-01-04", "DTT", 7, "总计")),
        ]
        self.assertEqual(deletion_ranges(rows), ((10, 11), (2, 3)))


if __name__ == "__main__":
    unittest.main()
