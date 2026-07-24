"""Credential-at-rest proof using AES-GCM and versioned encryption keys.

The production secret store will wrap this interface with KMS/Secrets Manager.
This proof focuses on the invariants: ciphertext-only persistence, associated
data binding, key rotation, and revocation.
"""

from __future__ import annotations

import base64
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
    AESGCM = None  # type: ignore[assignment,misc]
    _CRYPTOGRAPHY_ERROR = exc
else:
    _CRYPTOGRAPHY_ERROR = None


def require_cryptography() -> type:
    if AESGCM is None:
        raise RuntimeError(
            "cryptography is required for credential_security; install project dependencies"
        ) from _CRYPTOGRAPHY_ERROR
    return AESGCM


@dataclass(frozen=True)
class EncryptedSecret:
    key_version: str
    nonce_b64: str
    ciphertext_b64: str

    def serialize(self) -> str:
        return json.dumps(
            {
                "key_version": self.key_version,
                "nonce": self.nonce_b64,
                "ciphertext": self.ciphertext_b64,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def deserialize(cls, value: str) -> EncryptedSecret:
        data = json.loads(value)
        return cls(
            key_version=data["key_version"],
            nonce_b64=data["nonce"],
            ciphertext_b64=data["ciphertext"],
        )


class CredentialVault:
    def __init__(self, keys: dict[str, bytes], active_key_version: str) -> None:
        require_cryptography()
        if active_key_version not in keys:
            raise ValueError("active key version is not available")
        if any(len(key) not in (16, 24, 32) for key in keys.values()):
            raise ValueError("AES-GCM keys must be 128, 192, or 256 bits")
        self.keys = keys
        self.active_key_version = active_key_version

    def encrypt(self, plaintext: str, associated_data: str) -> EncryptedSecret:
        aes_gcm = require_cryptography()(self.keys[self.active_key_version])
        nonce = secrets.token_bytes(12)
        ciphertext = aes_gcm.encrypt(
            nonce,
            plaintext.encode("utf-8"),
            associated_data.encode("utf-8"),
        )
        return EncryptedSecret(
            key_version=self.active_key_version,
            nonce_b64=base64.b64encode(nonce).decode("ascii"),
            ciphertext_b64=base64.b64encode(ciphertext).decode("ascii"),
        )

    def decrypt(self, secret: EncryptedSecret, associated_data: str) -> str:
        key = self.keys.get(secret.key_version)
        if key is None:
            raise ValueError("encryption key version is unavailable")
        plaintext = require_cryptography()(key).decrypt(
            base64.b64decode(secret.nonce_b64),
            base64.b64decode(secret.ciphertext_b64),
            associated_data.encode("utf-8"),
        )
        return plaintext.decode("utf-8")

    def rotate(self, secret: EncryptedSecret, associated_data: str) -> EncryptedSecret:
        return self.encrypt(self.decrypt(secret, associated_data), associated_data)


class CredentialRepository:
    """SQLite proof repository that stores only encrypted credential material."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.execute(
            """
            CREATE TABLE oauth_credentials (
                mailbox_id TEXT PRIMARY KEY,
                encrypted_secret TEXT NOT NULL,
                revoked_at TEXT
            )
            """
        )

    def save(self, mailbox_id: str, secret: EncryptedSecret) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO oauth_credentials VALUES (?, ?, NULL)",
            (mailbox_id, secret.serialize()),
        )
        self.connection.commit()

    def revoke(self, mailbox_id: str) -> None:
        self.connection.execute(
            "UPDATE oauth_credentials SET revoked_at = ? WHERE mailbox_id = ?",
            (datetime.now(UTC).isoformat(), mailbox_id),
        )
        self.connection.commit()

    def load_active(self, mailbox_id: str) -> EncryptedSecret:
        row = self.connection.execute(
            "SELECT encrypted_secret, revoked_at FROM oauth_credentials WHERE mailbox_id = ?",
            (mailbox_id,),
        ).fetchone()
        if row is None or row[1] is not None:
            raise ValueError("credential is missing or revoked")
        return EncryptedSecret.deserialize(row[0])

    def persisted_material(self) -> str:
        return self.connection.execute(
            "SELECT encrypted_secret FROM oauth_credentials"
        ).fetchone()[0]
