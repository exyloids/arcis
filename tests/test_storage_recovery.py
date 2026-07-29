import unittest
from uuid import UUID

from arcis_backend.storage import MinioArtifactStorage


class FakeMinioClient:
    def __init__(self) -> None:
        self.copies: list[tuple[str, str, str, str]] = []
        self.removals: list[tuple[str, str]] = []

    def copy_object(self, bucket: str, destination: str, source: object) -> None:
        self.copies.append(
            (
                bucket,
                destination,
                str(getattr(source, "bucket_name")),
                str(getattr(source, "object_name")),
            )
        )

    def remove_object(self, bucket: str, object_key: str) -> None:
        self.removals.append((bucket, object_key))


class StorageRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = object.__new__(MinioArtifactStorage)
        self.storage.bucket = "private-artifacts"
        self.storage.client = FakeMinioClient()

    def test_quarantine_moves_content_to_user_scoped_recovery_key(self) -> None:
        user_id = UUID("00000000-0000-4000-8000-000000000001")
        artifact_id = UUID("00000000-0000-4000-8000-000000000002")

        recovery_key = self.storage.quarantine(
            "gmail/user/mailbox/message.eml",
            user_id,
            artifact_id,
        )

        self.assertEqual(
            recovery_key,
            f"recovery/{user_id}/{artifact_id}/source",
        )
        self.assertEqual(
            self.storage.client.copies,
            [
                (
                    "private-artifacts",
                    recovery_key,
                    "private-artifacts",
                    "gmail/user/mailbox/message.eml",
                )
            ],
        )
        self.assertEqual(
            self.storage.client.removals,
            [("private-artifacts", "gmail/user/mailbox/message.eml")],
        )

    def test_restore_copies_back_before_removing_recovery_object(self) -> None:
        self.storage.restore(
            "recovery/user/artifact/source",
            "imports/user/import/statement.pdf",
        )

        self.assertEqual(
            self.storage.client.copies,
            [
                (
                    "private-artifacts",
                    "imports/user/import/statement.pdf",
                    "private-artifacts",
                    "recovery/user/artifact/source",
                )
            ],
        )
        self.assertEqual(
            self.storage.client.removals,
            [("private-artifacts", "recovery/user/artifact/source")],
        )


if __name__ == "__main__":
    unittest.main()
