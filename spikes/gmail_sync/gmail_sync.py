"""Gmail synchronization feasibility proof: two-mailbox cursors and recovery.

The provider is a deterministic fake that models the behavior Arcis needs from
Gmail: mailbox-local history cursors, new-message history events, and an
invalidated cursor that requires a bounded recent overlap scan. The repository
uses SQLite only for this proof; production state remains PostgreSQL-backed.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


class InvalidHistoryCursor(Exception):
    """The provider no longer retains the requested mailbox history cursor."""


@dataclass(frozen=True)
class GmailMessage:
    mailbox_id: str
    provider_message_id: str
    received_at: datetime
    subject: str
    body: str
    history_id: int


class FakeGmailProvider:
    def __init__(self) -> None:
        self._messages: dict[str, list[GmailMessage]] = {}
        self._next_history_id: dict[str, int] = {}
        self._invalidated: set[str] = set()

    def add_message(self, mailbox_id: str, subject: str, body: str) -> GmailMessage:
        history_id = self._next_history_id.get(mailbox_id, 0) + 1
        self._next_history_id[mailbox_id] = history_id
        message = GmailMessage(
            mailbox_id=mailbox_id,
            provider_message_id=f"{mailbox_id}-message-{history_id}",
            received_at=datetime.now(UTC) + timedelta(seconds=history_id),
            subject=subject,
            body=body,
            history_id=history_id,
        )
        self._messages.setdefault(mailbox_id, []).append(message)
        return message

    def invalidate_history(self, mailbox_id: str) -> None:
        self._invalidated.add(mailbox_id)

    def current_history_id(self, mailbox_id: str) -> int:
        return self._next_history_id.get(mailbox_id, 0)

    def history_since(self, mailbox_id: str, cursor: int) -> list[GmailMessage]:
        if mailbox_id in self._invalidated:
            raise InvalidHistoryCursor(mailbox_id)
        return [
            message
            for message in self._messages.get(mailbox_id, [])
            if message.history_id > cursor
        ]

    def recent(self, mailbox_id: str, limit: int) -> list[GmailMessage]:
        messages = self._messages.get(mailbox_id, [])
        return messages[-limit:]


class SyncRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS mailboxes (
                mailbox_id TEXT PRIMARY KEY,
                history_cursor INTEGER,
                last_sync_mode TEXT,
                sync_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS source_artifacts (
                mailbox_id TEXT NOT NULL,
                provider_message_id TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                subject TEXT NOT NULL,
                received_at TEXT NOT NULL,
                PRIMARY KEY (mailbox_id, provider_message_id),
                UNIQUE (mailbox_id, content_sha256)
            );
            """
        )

    def ensure_mailbox(self, mailbox_id: str) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO mailboxes (mailbox_id) VALUES (?)", (mailbox_id,)
        )

    def cursor(self, mailbox_id: str) -> int | None:
        row = self.connection.execute(
            "SELECT history_cursor FROM mailboxes WHERE mailbox_id = ?", (mailbox_id,)
        ).fetchone()
        return None if row is None else row[0]

    def set_cursor(self, mailbox_id: str, cursor: int, mode: str) -> None:
        self.connection.execute(
            """
            UPDATE mailboxes
            SET history_cursor = ?, last_sync_mode = ?, sync_count = sync_count + 1
            WHERE mailbox_id = ?
            """,
            (cursor, mode, mailbox_id),
        )

    def persist_messages(self, messages: Iterable[GmailMessage]) -> int:
        added = 0
        for message in messages:
            content_hash = hashlib.sha256(message.body.encode("utf-8")).hexdigest()
            result = self.connection.execute(
                """
                INSERT OR IGNORE INTO source_artifacts
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    message.mailbox_id,
                    message.provider_message_id,
                    content_hash,
                    message.subject,
                    message.received_at.isoformat(),
                ),
            )
            added += result.rowcount
        return added

    def artifact_count(self, mailbox_id: str) -> int:
        return self.connection.execute(
            "SELECT COUNT(*) FROM source_artifacts WHERE mailbox_id = ?", (mailbox_id,)
        ).fetchone()[0]


class GmailSyncEngine:
    def __init__(self, provider: FakeGmailProvider, repository: SyncRepository) -> None:
        self.provider = provider
        self.repository = repository

    def sync(self, mailbox_id: str, recovery_overlap: int = 3) -> dict[str, int | str]:
        self.repository.ensure_mailbox(mailbox_id)
        cursor = self.repository.cursor(mailbox_id)
        mode = "initial" if cursor is None else "incremental"
        try:
            messages = (
                self.provider.recent(mailbox_id, recovery_overlap)
                if cursor is None
                else self.provider.history_since(mailbox_id, cursor)
            )
        except InvalidHistoryCursor:
            mode = "recovery_overlap"
            messages = self.provider.recent(mailbox_id, recovery_overlap)

        with self.repository.connection:
            added = self.repository.persist_messages(messages)
            self.repository.set_cursor(
                mailbox_id,
                self.provider.current_history_id(mailbox_id),
                mode,
            )
        return {"mailbox_id": mailbox_id, "mode": mode, "scanned": len(messages), "added": added}


def run_proof() -> tuple[dict[str, int | str], ...]:
    provider = FakeGmailProvider()
    repository = SyncRepository(sqlite3.connect(":memory:"))
    engine = GmailSyncEngine(provider, repository)

    provider.add_message("mailbox-a", "ICICI alert", "transaction-a-1")
    provider.add_message("mailbox-a", "HDFC alert", "transaction-a-2")
    provider.add_message("mailbox-b", "ICICI alert", "transaction-b-1")
    initial_a = engine.sync("mailbox-a")
    initial_b = engine.sync("mailbox-b")

    provider.add_message("mailbox-a", "ICICI alert", "transaction-a-3")
    incremental_a = engine.sync("mailbox-a")
    provider.invalidate_history("mailbox-a")
    provider.add_message("mailbox-a", "ICICI alert", "transaction-a-4")
    recovery_a = engine.sync("mailbox-a")

    return initial_a, initial_b, incremental_a, recovery_a


if __name__ == "__main__":
    for result in run_proof():
        print(result)
