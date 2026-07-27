"""Mailbox connection and encrypted OAuth credential persistence."""

from __future__ import annotations

import base64
import json
import secrets
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session


class MailboxError(ValueError):
    """A safe, user-correctable mailbox operation error."""


class CredentialCipher:
    """Versioned AES-GCM encryption for OAuth material at rest."""

    def __init__(self, key_version: str, key_b64: str) -> None:
        try:
            key = base64.urlsafe_b64decode(key_b64 + "=" * (-len(key_b64) % 4))
        except (ValueError, UnicodeDecodeError) as error:
            raise MailboxError("Credential encryption key is invalid") from error
        if len(key) != 32:
            raise MailboxError("Credential encryption key must be a 256-bit base64 value")
        self.key_version = key_version
        self._cipher = AESGCM(key)

    def encrypt(self, refresh_token: str, associated_data: str) -> str:
        nonce = secrets.token_bytes(12)
        ciphertext = self._cipher.encrypt(nonce, refresh_token.encode("utf-8"), associated_data.encode("utf-8"))
        return json.dumps(
            {"nonce": base64.b64encode(nonce).decode("ascii"), "ciphertext": base64.b64encode(ciphertext).decode("ascii")},
            separators=(",", ":"),
            sort_keys=True,
        )

    def decrypt(self, encrypted_secret: str, associated_data: str) -> str:
        try:
            payload = json.loads(encrypted_secret)
            return self._cipher.decrypt(
                base64.b64decode(payload["nonce"]),
                base64.b64decode(payload["ciphertext"]),
                associated_data.encode("utf-8"),
            ).decode("utf-8")
        except Exception as error:  # cryptography deliberately uses several exception types
            raise MailboxError("Mailbox credential cannot be decrypted") from error


class MailboxService:
    def __init__(self, engine: Engine, user_id: UUID, cipher: CredentialCipher) -> None:
        self.engine = engine
        self.user_id = user_id
        self.cipher = cipher

    def list_mailboxes(self) -> list[dict[str, object]]:
        return self._rows(
            """SELECT id, provider, provider_subject, display_email, connection_status, granted_scopes,
            history_cursor, last_successful_sync_at, created_at, updated_at
            FROM mailboxes WHERE user_id = :user_id ORDER BY created_at DESC"""
        )

    def save_gmail_connection(
        self, provider_subject: str, display_email: str, granted_scopes: list[str], refresh_token: str
    ) -> dict[str, object]:
        subject = _required_text(provider_subject, "provider_subject")
        email = _required_text(display_email, "display_email").lower()
        token = _required_text(refresh_token, "refresh_token")
        if "@" not in email:
            raise MailboxError("display_email is invalid")
        scopes = sorted({_required_text(scope, "granted_scope") for scope in granted_scopes})
        if not scopes:
            raise MailboxError("At least one granted Gmail scope is required")
        with Session(self.engine) as session, session.begin():
            mailbox = session.execute(
                text("""SELECT id FROM mailboxes WHERE user_id = :user_id AND provider = 'gmail'
                AND provider_subject = :provider_subject FOR UPDATE"""),
                {"user_id": self.user_id, "provider_subject": subject},
            ).scalar_one_or_none()
            mailbox_id = mailbox or uuid4()
            if mailbox is None:
                session.execute(
                    text("""INSERT INTO mailboxes (id, user_id, provider, provider_subject, display_email,
                    connection_status, granted_scopes) VALUES (:id, :user_id, 'gmail', :provider_subject,
                    :display_email, 'connected', CAST(:granted_scopes AS jsonb))"""),
                    {"id": mailbox_id, "user_id": self.user_id, "provider_subject": subject,
                     "display_email": email, "granted_scopes": json.dumps(scopes)},
                )
            else:
                session.execute(
                    text("""UPDATE mailboxes SET display_email = :display_email, connection_status = 'connected',
                    granted_scopes = CAST(:granted_scopes AS jsonb), version = version + 1, updated_at = now()
                    WHERE id = :id"""),
                    {"id": mailbox_id, "display_email": email, "granted_scopes": json.dumps(scopes)},
                )
            session.execute(
                text("""INSERT INTO oauth_credentials (mailbox_id, encrypted_secret, key_version, rotated_at, revoked_at)
                VALUES (:mailbox_id, :encrypted_secret, :key_version, now(), NULL)
                ON CONFLICT (mailbox_id) DO UPDATE SET encrypted_secret = EXCLUDED.encrypted_secret,
                key_version = EXCLUDED.key_version, rotated_at = now(), revoked_at = NULL"""),
                {"mailbox_id": mailbox_id, "encrypted_secret": self.cipher.encrypt(token, self._aad(mailbox_id)),
                 "key_version": self.cipher.key_version},
            )
        return self._one("SELECT id, provider, provider_subject, display_email, connection_status, granted_scopes, history_cursor FROM mailboxes WHERE id = :id", {"id": mailbox_id})

    def disconnect_mailbox(self, mailbox_id: UUID) -> None:
        with Session(self.engine) as session, session.begin():
            updated = session.execute(
                text("""UPDATE mailboxes SET connection_status = 'disconnected', version = version + 1, updated_at = now()
                WHERE id = :id AND user_id = :user_id"""), {"id": mailbox_id, "user_id": self.user_id}
            )
            if updated.rowcount != 1:
                raise MailboxError("Mailbox was not found")
            session.execute(text("UPDATE oauth_credentials SET revoked_at = now() WHERE mailbox_id = :id"), {"id": mailbox_id})

    def active_refresh_token(self, mailbox_id: UUID) -> str:
        row = self._one(
            """SELECT c.encrypted_secret FROM oauth_credentials c JOIN mailboxes m ON m.id = c.mailbox_id
            WHERE c.mailbox_id = :id AND m.user_id = :user_id AND m.connection_status = 'connected'
            AND c.revoked_at IS NULL""", {"id": mailbox_id, "user_id": self.user_id}
        )
        return self.cipher.decrypt(str(row["encrypted_secret"]), self._aad(mailbox_id))

    def set_history_cursor(self, mailbox_id: UUID, history_cursor: str) -> None:
        with Session(self.engine) as session, session.begin():
            result = session.execute(
                text("""UPDATE mailboxes SET history_cursor = :history_cursor, last_successful_sync_at = now(),
                updated_at = now(), version = version + 1 WHERE id = :id AND user_id = :user_id
                AND connection_status = 'connected'"""),
                {"id": mailbox_id, "user_id": self.user_id, "history_cursor": history_cursor},
            )
            if result.rowcount != 1:
                raise MailboxError("Connected Gmail mailbox was not found")

    def _aad(self, mailbox_id: UUID) -> str:
        return f"arcis:gmail:{self.user_id}:{mailbox_id}"

    def _rows(self, query: str) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            return [dict(row) for row in session.execute(text(query), {"user_id": self.user_id}).mappings()]

    def _one(self, query: str, parameters: dict[str, object]) -> dict[str, object]:
        with Session(self.engine) as session:
            row = session.execute(text(query), parameters).mappings().one_or_none()
        if row is None:
            raise MailboxError("Mailbox credential was not found")
        return dict(row)


def _required_text(value: object, field: str) -> str:
    text_value = str(value).strip() if value is not None else ""
    if not text_value:
        raise MailboxError(f"{field} is required")
    return text_value
