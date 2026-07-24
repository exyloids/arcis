import sqlite3
import unittest

from spikes.credential_security.credential_security import (
    CredentialRepository,
    CredentialVault,
    require_cryptography,
)


class CredentialSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            require_cryptography()
        except RuntimeError as exc:
            raise unittest.SkipTest(str(exc)) from exc

    def test_ciphertext_only_storage_and_key_rotation(self):
        old_key = b"old-key-material-32-bytes-long!!!"[:32]
        new_key = b"new-key-material-32-bytes-long!!!"[:32]
        old_vault = CredentialVault({"2026-01": old_key}, "2026-01")
        repository = CredentialRepository(sqlite3.connect(":memory:"))
        secret = old_vault.encrypt("refresh-token-value", "mailbox:one")
        repository.save("mailbox-one", secret)

        persisted = repository.persisted_material()
        self.assertNotIn("refresh-token-value", persisted)
        self.assertEqual(
            old_vault.decrypt(repository.load_active("mailbox-one"), "mailbox:one"),
            "refresh-token-value",
        )

        new_vault = CredentialVault(
            {"2026-01": old_key, "2026-07": new_key}, "2026-07"
        )
        rotated = new_vault.rotate(repository.load_active("mailbox-one"), "mailbox:one")
        repository.save("mailbox-one", rotated)
        self.assertEqual(rotated.key_version, "2026-07")
        self.assertEqual(new_vault.decrypt(rotated, "mailbox:one"), "refresh-token-value")

    def test_associated_data_prevents_cross_mailbox_decryption(self):
        vault = CredentialVault({"2026-07": b"key-material-32-bytes-long!!!!!!"[:32]}, "2026-07")
        secret = vault.encrypt("refresh-token-value", "mailbox:one")
        with self.assertRaises(Exception):
            vault.decrypt(secret, "mailbox:two")

    def test_revocation_blocks_credential_load(self):
        vault = CredentialVault({"2026-07": b"key-material-32-bytes-long!!!!!!"[:32]}, "2026-07")
        repository = CredentialRepository(sqlite3.connect(":memory:"))
        repository.save("mailbox-one", vault.encrypt("token", "mailbox:one"))
        repository.revoke("mailbox-one")
        with self.assertRaisesRegex(ValueError, "revoked"):
            repository.load_active("mailbox-one")


if __name__ == "__main__":
    unittest.main()
