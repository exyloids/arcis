"""Integration coverage against a migrated PostgreSQL database."""

from __future__ import annotations

import os
import unittest
from uuid import uuid4

from arcis_backend.ledger import LedgerError, LedgerService, database_engine
from sqlalchemy import text
from sqlalchemy.orm import Session

DATABASE_URL = os.getenv("ARCIS_INTEGRATION_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "set ARCIS_INTEGRATION_DATABASE_URL to run PostgreSQL integration tests")
class ManualLedgerPostgresTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = database_engine(DATABASE_URL)
        self.service = LedgerService(self.engine, uuid4())
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

    def tearDown(self) -> None:
        self.engine.dispose()

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

    def test_manual_category_can_be_confirmed_for_uncategorized_vendor_matches(self) -> None:
        content = (
            b"Date,Narration,Debit,Credit,Reference\n"
            b"01/07/2026,ACME COFFEE,100,,MATCH-001\n"
            b"02/07/2026,ACME COFFEE,110,,MATCH-002\n"
            b"03/07/2026,ACME COFFEE,120,,MATCH-003\n"
            b"04/07/2026,ACME COFFEE,130,,MATCH-004\n"
            b"05/07/2026,OTHER MERCHANT,140,,OTHER-001\n"
        )
        preview = self.service.stage_import(self.account["id"], "matching-merchants.csv", content)
        self.service.confirm_import(preview["import"]["id"])
        transactions = self.service.list_transactions(month="2026-07")
        matching = [transaction for transaction in transactions if transaction["narration"] == "ACME COFFEE"]
        categories = self.service.list_categories()
        selected_category = next(category for category in categories if category["code"] == "food_drinks_tea_coffee")
        protected_category = next(category for category in categories if category["code"] == "shopping_books")

        self.service.update_transaction(
            matching[0]["id"],
            {
                "category_id": protected_category["parent_id"],
                "subcategory_id": protected_category["id"],
            },
        )
        updated = self.service.update_transaction(
            matching[1]["id"],
            {
                "category_id": selected_category["parent_id"],
                "subcategory_id": selected_category["id"],
                "remember_merchant": True,
            },
        )

        self.assertEqual(updated["matching_transaction_count"], 2)
        self.assertEqual(updated["matched_merchant"], "ACME COFFEE")
        rules = self.service.list_merchant_rules()
        remembered = next(rule for rule in rules if rule["match_pattern"] == "acme coffee")
        self.assertEqual(remembered["category_id"], selected_category["parent_id"])
        self.assertEqual(remembered["subcategory_id"], selected_category["id"])
        match_preview = self.service.category_match_preview(matching[1]["id"])
        self.assertEqual(match_preview["matching_transaction_count"], 2)
        self.assertEqual(match_preview["merchant"], "ACME COFFEE")

        applied = self.service.apply_category_to_matching_transactions(matching[1]["id"])
        self.assertEqual(applied["updated"], 2)
        refreshed = {transaction["id"]: transaction for transaction in self.service.list_transactions(month="2026-07")}
        self.assertEqual(refreshed[matching[0]["id"]]["category_id"], protected_category["parent_id"])
        self.assertEqual(refreshed[matching[0]["id"]]["subcategory_id"], protected_category["id"])
        self.assertTrue(
            all(
                refreshed[transaction["id"]]["category_id"] == selected_category["parent_id"]
                and refreshed[transaction["id"]]["subcategory_id"] == selected_category["id"]
                for transaction in matching[1:]
            )
        )
        uncategorized = self.service.transaction_page(period="all_time", uncategorized=True)
        self.assertEqual([item["narration"] for item in uncategorized["items"]], ["OTHER MERCHANT"])

    def test_bank_balance_requires_a_statement_baseline_and_rolls_forward_newer_activity(self) -> None:
        preview = self.service.stage_import(self.account["id"], "statement.csv", self.content)
        self.service.confirm_import(preview["import"]["id"])

        without_baseline = self.service.balance_summary()
        self.assertIsNone(without_baseline["accounts"][0]["balance"])
        self.assertFalse(without_baseline["cash_balance_complete"])

        import_id, statement_id = uuid4(), uuid4()
        with Session(self.engine) as session, session.begin():
            session.execute(
                text(
                    """INSERT INTO imports
                       (id, user_id, financial_account_id, filename, content_sha256, state,
                        row_count, confirmed_at)
                       VALUES (:id, :user_id, :account_id, 'baseline.pdf', :hash,
                               'confirmed', 0, now())"""
                ),
                {
                    "id": import_id,
                    "user_id": self.service.user_id,
                    "account_id": self.account["id"],
                    "hash": "a" * 64,
                },
            )
            session.execute(
                text(
                    """INSERT INTO statements
                       (id, user_id, financial_account_id, import_id, parser_name,
                        parser_version, period_end, closing_balance, state, confirmed_at)
                       VALUES (:id, :user_id, :account_id, :import_id, 'integration',
                               '1', '2026-07-01', 5000, 'reconciled', now())"""
                ),
                {
                    "id": statement_id,
                    "user_id": self.service.user_id,
                    "account_id": self.account["id"],
                    "import_id": import_id,
                },
            )

        with_baseline = self.service.balance_summary()
        self.assertEqual(with_baseline["accounts"][0]["balance"], 6000)
        self.assertEqual(with_baseline["accounts"][0]["balance_source"], "statement_plus_transactions")
        self.assertTrue(with_baseline["cash_balance_complete"])

    def test_account_details_can_be_updated_and_account_can_be_archived(self) -> None:
        updated = self.service.update_account(
            self.account["id"],
            {
                "display_name": "Salary account",
                "product_name": "Premium Savings",
                "masked_identifier": "••••0001",
                "currency": "inr",
            },
        )

        self.assertEqual(updated["display_name"], "Salary account")
        self.assertEqual(updated["product_name"], "Premium Savings")
        self.assertEqual(updated["currency"], "INR")
        self.assertEqual(updated["version"], 2)

        self.service.archive_account(self.account["id"])

        self.assertEqual(self.service.list_accounts(), [])
        with self.assertRaisesRegex(LedgerError, "Active account"):
            self.service.archive_account(self.account["id"])
