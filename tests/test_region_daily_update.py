import unittest
from datetime import date

from src.galaxy_ceo_portal_region_daily_update import (
    ExistingRegionRow,
    RegionSnapshot,
    build_update_plan,
    parse_region_key,
)


class RegionDailyUpdateTests(unittest.TestCase):
    def test_blank_region_id_is_company_total_key(self) -> None:
        business_date, key = parse_region_key(
            ["2026-09-12", "DTT", "乌干达", 7, ""],
            2,
        )
        self.assertEqual(business_date, date(2026, 9, 12))
        self.assertEqual(key, ("2026-09-12", "DTT", 7, None))

    def test_plan_uses_rolling_400_day_window_and_marks_old_rows(self) -> None:
        old = ExistingRegionRow(
            2,
            date(2025, 8, 9),
            ("2025-08-09", "DTT", 7, None),
        )
        current = ExistingRegionRow(
            3,
            date(2025, 8, 10),
            ("2025-08-10", "DTT", 7, None),
        )
        snapshot = RegionSnapshot(
            rows=(old, current),
            keys=frozenset((old.key, current.key)),
            dates=frozenset((old.business_date, current.business_date)),
        )
        plan = build_update_plan(snapshot, date(2026, 9, 13))
        self.assertEqual(plan.target_start, date(2025, 8, 10))
        self.assertEqual(plan.target_end, date(2026, 9, 13))
        self.assertEqual(plan.expired_rows, (old,))
        self.assertEqual(plan.fetch_ranges[0][0], date(2025, 8, 11))
        self.assertEqual(plan.fetch_ranges[-1][1], date(2026, 9, 13))

    def test_plan_accepts_a_custom_retention_window(self) -> None:
        snapshot = RegionSnapshot(rows=(), keys=frozenset(), dates=frozenset())
        plan = build_update_plan(snapshot, date(2026, 9, 13), retention_days=3)
        self.assertEqual(plan.target_start, date(2026, 9, 11))
        self.assertEqual(plan.target_end, date(2026, 9, 13))


if __name__ == "__main__":
    unittest.main()
