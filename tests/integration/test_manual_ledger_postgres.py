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
        repeated_preview = self.service.stage_import(self.account["id"], "statement.csv", self.content)
        self.assertEqual(len(preview["rows"]), 2)
        self.assertEqual(repeated_preview["import"]["id"], import_id)

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

    def test_all_invalid_statement_rows_create_a_failed_review_record(self) -> None:
        invalid = b"Date,Narration,Debit,Credit\n01/07/2026,Invalid,100,200\n"

        preview = self.service.stage_import(self.account["id"], "invalid.csv", invalid)

        self.assertEqual(preview["import"]["state"], "failed")
        self.assertEqual(preview["import"]["valid_row_count"], 0)
        self.assertEqual(preview["import"]["invalid_row_count"], 1)
        self.assertEqual(preview["errors"], [{"ordinal": 2, "message": "Each row must contain exactly one debit or credit amount"}])
        with self.assertRaisesRegex(LedgerError, "failed"):
            self.service.confirm_import(preview["import"]["id"])

    def test_preview_retains_valid_rows_and_persists_invalid_row_feedback(self) -> None:
        mixed = (
            b"Date,Narration,Debit,Credit\n"
            b"01/07/2026,Valid purchase,100,\n"
            b"02/07/2026,Invalid purchase,100,200\n"
        )

        preview = self.service.stage_import(self.account["id"], "mixed.csv", mixed)

        self.assertEqual(preview["import"]["state"], "preview_ready")
        self.assertEqual(preview["import"]["valid_row_count"], 1)
        self.assertEqual(preview["import"]["invalid_row_count"], 1)
        self.assertEqual(len(preview["rows"]), 1)
        self.assertEqual(preview["errors"], [{"ordinal": 3, "message": "Each row must contain exactly one debit or credit amount"}])
        self.assertEqual(self.service.confirm_import(preview["import"]["id"])["created"], 1)

    def test_transaction_page_uses_an_opaque_cursor_without_repeating_rows(self) -> None:
        preview = self.service.stage_import(self.account["id"], "statement.csv", self.content)
        self.service.confirm_import(preview["import"]["id"])

        first_page = self.service.transaction_page(month="2026-07", limit=1)
        second_page = self.service.transaction_page(month="2026-07", cursor=first_page["next_cursor"], limit=1)

        self.assertEqual(len(first_page["items"]), 1)
        self.assertIsNotNone(first_page["next_cursor"])
        self.assertEqual(len(second_page["items"]), 1)
        self.assertIsNone(second_page["next_cursor"])
        self.assertNotEqual(first_page["items"][0]["id"], second_page["items"][0]["id"])

        with self.assertRaisesRegex(LedgerError, "cursor is invalid"):
            self.service.transaction_page(cursor="not-a-valid-cursor")
