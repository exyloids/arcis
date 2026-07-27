"""Idempotent persistence for raw Gmail message evidence."""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from arcis_backend.storage import MinioArtifactStorage


class GmailArtifactRepository:
    def __init__(self, engine: Engine, user_id: UUID, storage: MinioArtifactStorage) -> None:
        self.engine, self.user_id, self.storage = engine, user_id, storage

    def persist(self, mailbox_id: UUID, message_id: str, raw_message: bytes) -> tuple[bool, UUID | None]:
        with Session(self.engine) as session:
            exists = session.execute(
                text("""SELECT 1 FROM source_artifacts WHERE user_id = :user_id AND mailbox_id = :mailbox_id
                AND provider_message_id = :message_id"""),
                {"user_id": self.user_id, "mailbox_id": mailbox_id, "message_id": message_id},
            ).scalar_one_or_none()
        if exists:
            return False, self._artifact_id(mailbox_id, message_id)
        stored = self.storage.put_gmail_message(self.user_id, mailbox_id, message_id, raw_message)
        with Session(self.engine) as session, session.begin():
            inserted = session.execute(
                text("""INSERT INTO source_artifacts (id, user_id, kind, content_sha256, object_key,
                detected_mime_type, byte_size, lifecycle_state, mailbox_id, provider_message_id)
                VALUES (:id, :user_id, 'gmail_message', :sha, :object_key, :content_type, :byte_size,
                'active', :mailbox_id, :message_id) ON CONFLICT (mailbox_id, provider_message_id)
                WHERE mailbox_id IS NOT NULL AND provider_message_id IS NOT NULL DO NOTHING"""),
                {"id": uuid4(), "user_id": self.user_id, "sha": hashlib.sha256(raw_message).hexdigest(),
                 "object_key": stored.object_key, "content_type": stored.content_type, "byte_size": stored.byte_size,
                 "mailbox_id": mailbox_id, "message_id": message_id},
            )
        if inserted.rowcount == 0:
            self.storage.delete(stored.object_key)
            return False, self._artifact_id(mailbox_id, message_id)
        return True, self._artifact_id(mailbox_id, message_id)

    def _artifact_id(self, mailbox_id: UUID, message_id: str) -> UUID | None:
        with Session(self.engine) as session:
            return session.execute(text("SELECT id FROM source_artifacts WHERE user_id = :user_id AND mailbox_id = :mailbox_id AND provider_message_id = :message_id"), {"user_id": self.user_id, "mailbox_id": mailbox_id, "message_id": message_id}).scalar_one_or_none()
