"""Integration coverage against a migrated PostgreSQL database."""

from __future__ import annotations

import os
import unittest
from uuid import uuid4

from arcis_backend.ledger import LedgerError, LedgerService, database_engine

DATABASE_URL = os.getenv("ARCIS_INTEGRATION_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "set ARCIS_INTEGRATION_DATABASE_URL to run PostgreSQL integration tests")
class ManualLedgerPostgresTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = LedgerService(database_engine(DATABASE_URL), uuid4())
        self.service.initialize_user()
        self.account = self.service.create_account(
            {
                "account_type": "bank_account",
                "institution_code": "integration_bank",
                "product_name": "Integration Savings",
                "display_name": "Integration account",
                "masked_identifier": "XX0001",
                "currency": "INR",
            }
        )
        self.content = (
            b"Transaction Date,Value Date,Transaction Remarks,Withdrawal Amount,Deposit Amount,Reference No.\n"
            b"01/07/2026,01/07/2026,UPI-TEST-MERCHANT,100.00,,REF-001\n"
            b"02/07/2026,02/07/2026,NEFT-SALARY,,1000.00,REF-002\n"
        )

    def test_preview_confirm_replay_and_monthly_report(self) -> None:
        preview = self.service.stage_import(self.account["id"], "statement.csv", self.content)
        import_id = preview["import"]["id"]
        self.assertEqual(len(preview["rows"]), 2)

        confirmed = self.service.confirm_import(import_id)
        replay = self.service.confirm_import(import_id)
        transactions = self.service.list_transactions(month="2026-07")
        report = self.service.monthly_report("2026-07")

        self.assertEqual(confirmed, {"created": 2, "duplicates": 0, "confirmed": 1})
        self.assertEqual(replay, {"created": 0, "duplicates": 0, "confirmed": 1})
        self.assertEqual(len(transactions), 2)
        self.assertEqual(str(report["income"]), "1000.0000")
        self.assertEqual(str(report["expense"]), "100.0000")

    def test_cancelled_import_cannot_be_confirmed(self) -> None:
        preview = self.service.stage_import(self.account["id"], "statement.csv", self.content)
        import_id = preview["import"]["id"]
        self.service.cancel_import(import_id)

        with self.assertRaisesRegex(LedgerError, "cancelled"):
            self.service.confirm_import(import_id)

    def test_invalid_statement_row_fails_before_import_persistence(self) -> None:
        invalid = b"Date,Narration,Debit,Credit\n01/07/2026,Invalid,100,200\n"

        with self.assertRaisesRegex(LedgerError, "exactly one debit or credit"):
            self.service.stage_import(self.account["id"], "invalid.csv", invalid)
