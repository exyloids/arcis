import sqlite3
import unittest

from spikes.gmail_sync.gmail_sync import (
    FakeGmailProvider,
    GmailSyncEngine,
    SyncRepository,
)


class GmailSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = FakeGmailProvider()
        self.connection = sqlite3.connect(":memory:")
        self.repository = SyncRepository(self.connection)
        self.engine = GmailSyncEngine(self.provider, self.repository)

    def tearDown(self) -> None:
        self.connection.close()

    def test_two_mailboxes_have_independent_cursors_and_artifacts(self):
        self.provider.add_message("mailbox-a", "ICICI", "a-1")
        self.provider.add_message("mailbox-a", "HDFC", "a-2")
        self.provider.add_message("mailbox-b", "ICICI", "b-1")

        result_a = self.engine.sync("mailbox-a")
        result_b = self.engine.sync("mailbox-b")

        self.assertEqual(
            result_a,
            {"mailbox_id": "mailbox-a", "mode": "initial", "scanned": 2, "added": 2},
        )
        self.assertEqual(
            result_b,
            {"mailbox_id": "mailbox-b", "mode": "initial", "scanned": 1, "added": 1},
        )
        self.assertEqual(self.repository.artifact_count("mailbox-a"), 2)
        self.assertEqual(self.repository.artifact_count("mailbox-b"), 1)

    def test_incremental_sync_only_fetches_new_messages(self):
        self.provider.add_message("mailbox-a", "ICICI", "a-1")
        self.engine.sync("mailbox-a")
        self.provider.add_message("mailbox-a", "ICICI", "a-2")

        result = self.engine.sync("mailbox-a")

        self.assertEqual(result["mode"], "incremental")
        self.assertEqual(result["scanned"], 1)
        self.assertEqual(result["added"], 1)
        self.assertEqual(self.repository.artifact_count("mailbox-a"), 2)

    def test_invalid_cursor_uses_bounded_overlap_without_duplicates(self):
        for body in ("a-1", "a-2", "a-3"):
            self.provider.add_message("mailbox-a", "ICICI", body)
        self.engine.sync("mailbox-a")
        self.provider.invalidate_history("mailbox-a")
        self.provider.add_message("mailbox-a", "ICICI", "a-4")

        result = self.engine.sync("mailbox-a", recovery_overlap=3)

        self.assertEqual(result["mode"], "recovery_overlap")
        self.assertEqual(result["scanned"], 3)
        self.assertEqual(result["added"], 1)
        self.assertEqual(self.repository.artifact_count("mailbox-a"), 4)


if __name__ == "__main__":
    unittest.main()
