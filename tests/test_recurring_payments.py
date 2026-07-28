import unittest

from arcis_backend.ledger import _recurrence_cadence


class RecurringPaymentTests(unittest.TestCase):
    def test_recognises_consistent_monthly_intervals(self) -> None:
        self.assertEqual(_recurrence_cadence([30, 31, 29]), ("monthly", 30))

    def test_recognises_consistent_weekly_intervals(self) -> None:
        self.assertEqual(_recurrence_cadence([7, 7, 8]), ("weekly", 7))

    def test_rejects_irregular_intervals(self) -> None:
        self.assertIsNone(_recurrence_cadence([5, 19, 42]))
