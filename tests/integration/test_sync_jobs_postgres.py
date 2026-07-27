"""Integration coverage for durable mailbox sync job requests."""

from __future__ import annotations

import base64
import os
import unittest
from uuid import uuid4

from arcis_backend.ledger import LedgerService, database_engine
from arcis_backend.mailboxes import CredentialCipher, MailboxService
from arcis_backend.sync_jobs import GmailSyncJobService

DATABASE_URL = os.getenv("ARCIS_INTEGRATION_DATABASE_URL")
KEY = base64.urlsafe_b64encode(b"0123456789abcdef0123456789abcdef").decode("ascii")


@unittest.skipUnless(DATABASE_URL, "set ARCIS_INTEGRATION_DATABASE_URL to run PostgreSQL integration tests")
class SyncJobsPostgresTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = database_engine(DATABASE_URL)
        self.user_id = uuid4()
        LedgerService(self.engine, self.user_id).initialize_user()
        mailbox = MailboxService(self.engine, self.user_id, CredentialCipher("test-v1", KEY))
        self.mailbox = mailbox.save_gmail_connection("sync-subject", "sync@example.com", ["scope"], "refresh-secret")
        self.service = GmailSyncJobService(self.engine, self.user_id)

    def test_sync_request_is_mailbox_scoped_and_idempotent_while_active(self) -> None:
        first = self.service.request_sync(self.mailbox["id"])
        second = self.service.request_sync(self.mailbox["id"])

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["state"], "queued")
        self.assertEqual(first["progress"], {"mailbox_id": str(self.mailbox["id"])})

    def test_worker_claims_once_and_records_terminal_state(self) -> None:
        queued = self.service.request_sync(self.mailbox["id"])
        claimed = self.service.claim_next()

        self.assertEqual(claimed["id"], queued["id"])
        self.assertEqual(claimed["state"], "running")
        self.assertEqual(claimed["attempt"], 1)
        self.assertIsNone(self.service.claim_next())

        completed = self.service.finish(claimed["id"], {"scanned": 0, "added": 0})
        self.assertEqual(completed["state"], "completed")
        self.assertEqual(completed["progress"], {"scanned": 0, "added": 0})
