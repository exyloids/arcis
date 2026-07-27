"""Integration coverage for mailbox ownership and encrypted credentials."""

from __future__ import annotations

import base64
import os
import unittest
from uuid import uuid4

from arcis_backend.ledger import LedgerService, database_engine
from arcis_backend.mailboxes import CredentialCipher, MailboxError, MailboxService

DATABASE_URL = os.getenv("ARCIS_INTEGRATION_DATABASE_URL")
KEY = base64.urlsafe_b64encode(b"0123456789abcdef0123456789abcdef").decode("ascii")


@unittest.skipUnless(DATABASE_URL, "set ARCIS_INTEGRATION_DATABASE_URL to run PostgreSQL integration tests")
class MailboxPostgresTests(unittest.TestCase):
    def setUp(self) -> None:
        self.user_id = uuid4()
        self.engine = database_engine(DATABASE_URL)
        LedgerService(self.engine, self.user_id).initialize_user()
        self.service = MailboxService(self.engine, self.user_id, CredentialCipher("test-v1", KEY))

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_connection_persists_ciphertext_and_does_not_expose_refresh_token(self) -> None:
        connected = self.service.save_gmail_connection(
            "google-subject-1", "Owner@Example.com", ["https://www.googleapis.com/auth/gmail.readonly"], "refresh-secret"
        )

        self.assertEqual(connected["connection_status"], "connected")
        self.assertEqual(connected["display_email"], "owner@example.com")
        self.assertNotIn("refresh_token", connected)
        self.assertEqual(self.service.active_refresh_token(connected["id"]), "refresh-secret")

        with self.service.engine.connect() as connection:
            stored = connection.exec_driver_sql(
                "SELECT encrypted_secret FROM oauth_credentials WHERE mailbox_id = %s", (connected["id"],)
            ).scalar_one()
        self.assertNotIn("refresh-secret", stored)

    def test_reconnect_rotates_secret_and_disconnect_revokes_it(self) -> None:
        first = self.service.save_gmail_connection("google-subject-2", "owner@example.com", ["scope"], "old-secret")
        second = self.service.save_gmail_connection("google-subject-2", "owner@example.com", ["scope"], "new-secret")

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(self.service.active_refresh_token(second["id"]), "new-secret")
        self.service.disconnect_mailbox(second["id"])
        self.assertEqual(self.service.list_mailboxes()[0]["connection_status"], "disconnected")
        with self.assertRaisesRegex(MailboxError, "not found"):
            self.service.active_refresh_token(second["id"])
