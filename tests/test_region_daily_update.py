import unittest
from datetime import date

from src.galaxy_ceo_portal_region_daily_update import (
    ExistingRegionRow,
    RegionSnapshot,
    build_update_plan,
    first_day_previous_month,
    parse_region_key,
)


class RegionDailyUpdateTests(unittest.TestCase):
    def test_window_uses_source_month_not_system_month(self) -> None:
        self.assertEqual(first_day_previous_month(date(2026, 9, 13)), date(2026, 8, 1))
        self.assertEqual(first_day_previous_month(date(2026, 10, 1)), date(2026, 9, 1))
        self.assertEqual(first_day_previous_month(date(2027, 1, 2)), date(2026, 12, 1))

    def test_blank_region_id_is_company_total_key(self) -> None:
        business_date, key = parse_region_key(
            ["2026-09-12", "DTT", "乌干达", 7, ""],
            2,
        )
        self.assertEqual(business_date, date(2026, 9, 12))
        self.assertEqual(key, ("2026-09-12", "DTT", 7, None))

    def test_plan_uses_previous_month_and_marks_old_rows(self) -> None:
        old = ExistingRegionRow(
            2,
            date(2026, 7, 31),
            ("2026-07-31", "DTT", 7, None),
        )
        current = ExistingRegionRow(
            3,
            date(2026, 8, 1),
            ("2026-08-01", "DTT", 7, None),
        )
        snapshot = RegionSnapshot(
            rows=(old, current),
            keys=frozenset((old.key, current.key)),
            dates=frozenset((old.business_date, current.business_date)),
        )
        plan = build_update_plan(snapshot, date(2026, 9, 13))
        self.assertEqual(plan.target_start, date(2026, 8, 1))
        self.assertEqual(plan.target_end, date(2026, 9, 13))
        self.assertEqual(plan.expired_rows, (old,))
        self.assertEqual(plan.fetch_ranges[0][0], date(2026, 8, 2))
        self.assertEqual(plan.fetch_ranges[-1][1], date(2026, 9, 13))


if __name__ == "__main__":
    unittest.main()
