"""Integration coverage for Gmail-first account approval and rejection gating."""

from __future__ import annotations

import base64
import hashlib
import os
import unittest
from pathlib import Path
from uuid import uuid4

from arcis_backend.candidates import CandidateService
from arcis_backend.ledger import LedgerService, database_engine
from arcis_backend.mailboxes import CredentialCipher, MailboxService
from sqlalchemy import text
from sqlalchemy.orm import Session

DATABASE_URL = os.getenv("ARCIS_INTEGRATION_DATABASE_URL")
KEY = base64.urlsafe_b64encode(b"0123456789abcdef0123456789abcdef").decode("ascii")
ROOT = Path(__file__).parents[2]


@unittest.skipUnless(
    DATABASE_URL,
    "set ARCIS_INTEGRATION_DATABASE_URL to run PostgreSQL integration tests",
)
class AccountDiscoveryPostgresTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = database_engine(DATABASE_URL)
        self.user_id = uuid4()
        LedgerService(self.engine, self.user_id).initialize_user()
        mailboxes = MailboxService(
            self.engine,
            self.user_id,
            CredentialCipher("test-v1", KEY),
        )
        self.mailbox = mailboxes.save_gmail_connection(
            f"discovery-{self.user_id}",
            "discovery@example.com",
            ["scope"],
            "refresh-secret",
        )
        self.service = CandidateService(self.engine, self.user_id)

    def tearDown(self) -> None:
        self.engine.dispose()

    def artifact(self, fixture_name: str):
        raw_message = (ROOT / "fixtures/sanitized/gmail" / fixture_name).read_bytes()
        return self.artifact_from_bytes(raw_message)

    def artifact_from_bytes(self, raw_message: bytes):
        artifact_id = uuid4()
        with Session(self.engine) as session, session.begin():
            session.execute(
                text(
                    """INSERT INTO source_artifacts
                       (id, user_id, kind, content_sha256, detected_mime_type,
                        byte_size, mailbox_id, provider_message_id)
                       VALUES (:id, :user_id, 'gmail_message', :sha256,
                               'message/rfc822', :byte_size, :mailbox_id,
                               :provider_message_id)"""
                ),
                {
                    "id": artifact_id,
                    "user_id": self.user_id,
                    "sha256": hashlib.sha256(raw_message).hexdigest(),
                    "byte_size": len(raw_message),
                    "mailbox_id": self.mailbox["id"],
                    "provider_message_id": str(artifact_id),
                },
            )
        return artifact_id, raw_message

    def counts(self) -> tuple[int, int]:
        with Session(self.engine) as session:
            accounts = session.execute(
                text("SELECT COUNT(*) FROM financial_accounts WHERE user_id = :user_id"),
                {"user_id": self.user_id},
            ).scalar_one()
            transactions = session.execute(
                text("SELECT COUNT(*) FROM transactions WHERE user_id = :user_id"),
                {"user_id": self.user_id},
            ).scalar_one()
        return accounts, transactions

    def test_rejection_skips_future_alerts_until_product_is_confirmed(self) -> None:
        artifact_id, raw_message = self.artifact("icici_account_debit.eml")
        first = self.service.create_from_artifact(artifact_id, raw_message)
        discovery = self.service.list_discovered_accounts()[0]

        self.assertEqual(first["state"], "needs_review")
        self.assertEqual(discovery["state"], "pending")
        self.assertEqual(self.counts(), (0, 0))

        self.service.reject_discovered_account(discovery["id"])
        artifact_id, raw_message = self.artifact("icici_imobile_transfer.eml")
        second = self.service.create_from_artifact(artifact_id, raw_message)

        self.assertEqual(second["state"], "rejected")
        self.assertEqual(self.counts(), (0, 0))

        self.service.reconsider_discovered_account(discovery["id"])
        confirmed = self.service.confirm_discovered_account(
            discovery["id"],
            {
                "product_name": "ICICI Savings",
                "display_name": "Primary ICICI account",
                "currency": "INR",
            },
        )

        self.assertEqual(confirmed["state"], "confirmed")
        self.assertEqual(confirmed["transactions_imported"], 2)
        self.assertEqual(self.counts(), (1, 2))

    def test_unsupported_layout_can_discover_product_without_importing_transaction(self) -> None:
        artifact_id, raw_message = self.artifact_from_bytes(
            b"From: HDFC Alerts <alerts@alerts.hdfcbank.com>\n"
            b"To: owner@example.invalid\n"
            b"Subject: Debit notification\n"
            b"MIME-Version: 1.0\n"
            b'Content-Type: text/plain; charset="utf-8"\n\n'
            b"Rs.500.00 has been debited from HDFC Bank Account Number "
            b"12345678901234 towards a mandate on 15-Oct-2026.\n"
        )

        candidate = self.service.create_from_artifact(artifact_id, raw_message)
        discovery = self.service.list_discovered_accounts()[0]

        self.assertEqual(candidate["state"], "unsupported")
        self.assertEqual(discovery["state"], "pending")
        self.assertEqual(discovery["account_type"], "bank_account")
        self.assertEqual(discovery["masked_identifier"], "\u2022\u2022\u2022\u20221234")
        self.assertEqual(self.counts(), (0, 0))


if __name__ == "__main__":
    unittest.main()
