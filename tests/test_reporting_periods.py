import unittest
from datetime import date

from arcis_backend.ledger import LedgerError, _reporting_period_bounds


class ReportingPeriodTests(unittest.TestCase):
    def test_month_periods_use_exclusive_upper_bound(self) -> None:
        today = date(2026, 7, 29)
        self.assertEqual(
            _reporting_period_bounds("this_month", today),
            (date(2026, 7, 1), date(2026, 8, 1)),
        )
        self.assertEqual(
            _reporting_period_bounds("last_month", today),
            (date(2026, 6, 1), date(2026, 7, 1)),
        )

    def test_rolling_and_year_periods_are_calendar_aligned(self) -> None:
        today = date(2026, 2, 10)
        self.assertEqual(
            _reporting_period_bounds("last_3_months", today),
            (date(2025, 12, 1), date(2026, 3, 1)),
        )
        self.assertEqual(
            _reporting_period_bounds("this_year", today),
            (date(2026, 1, 1), date(2027, 1, 1)),
        )

    def test_all_time_and_invalid_period(self) -> None:
        self.assertEqual(_reporting_period_bounds("all_time", date(2026, 1, 1)), (None, None))
        with self.assertRaises(LedgerError):
            _reporting_period_bounds("quarter")


if __name__ == "__main__":
    unittest.main()
