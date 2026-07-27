"""Durable, mailbox-scoped Gmail synchronization job commands."""

from __future__ import annotations

import json
import logging
from uuid import UUID, uuid4

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from arcis_backend.candidates import CandidateService
from arcis_backend.gmail_artifacts import GmailArtifactRepository
from arcis_backend.gmail_oauth import GmailOAuthError, GmailOAuthService
from arcis_backend.mailboxes import MailboxError, MailboxService

logger = logging.getLogger(__name__)


class SyncJobError(ValueError):
    """A safe error for synchronization job commands."""


class GmailSyncJobService:
    def __init__(self, engine: Engine, user_id: UUID) -> None:
        self.engine = engine
        self.user_id = user_id

    def request_sync(self, mailbox_id: UUID) -> dict[str, object]:
        with Session(self.engine) as session, session.begin():
            mailbox = session.execute(
                text("""SELECT id FROM mailboxes WHERE id = :mailbox_id AND user_id = :user_id
                AND provider = 'gmail' AND connection_status = 'connected'"""),
                {"mailbox_id": mailbox_id, "user_id": self.user_id},
            ).scalar_one_or_none()
            if mailbox is None:
                raise SyncJobError("Connected Gmail mailbox was not found")
            existing = session.execute(
                text("""SELECT id, state, job_kind, phase, progress, error_code, attempt, created_at, updated_at
                FROM jobs WHERE user_id = :user_id AND job_kind = 'gmail_sync'
                AND idempotency_key = :key AND state IN ('queued', 'running') FOR UPDATE"""),
                {"user_id": self.user_id, "key": str(mailbox_id)},
            ).mappings().one_or_none()
            if existing is not None:
                return dict(existing)
            job_id = uuid4()
            job_id = session.execute(
                text("""INSERT INTO jobs (id, user_id, job_kind, state, idempotency_key, phase, progress)
                VALUES (:id, :user_id, 'gmail_sync', 'queued', :key, 'queued', CAST(:progress AS jsonb))
                ON CONFLICT (user_id, job_kind, idempotency_key) DO UPDATE SET state = 'queued',
                phase = 'queued', progress = EXCLUDED.progress, error_code = NULL,
                updated_at = now() RETURNING id"""),
                {"id": job_id, "user_id": self.user_id, "key": str(mailbox_id), "progress": json.dumps({"mailbox_id": str(mailbox_id)})},
            ).scalar_one()
        return self.get_job(job_id)

    def get_job(self, job_id: UUID) -> dict[str, object]:
        with Session(self.engine) as session:
            row = session.execute(
                text("""SELECT id, job_kind, state, phase, progress, error_code, attempt, created_at, updated_at
                FROM jobs WHERE id = :id AND user_id = :user_id"""), {"id": job_id, "user_id": self.user_id}
            ).mappings().one_or_none()
        if row is None:
            raise SyncJobError("Synchronization job was not found")
        return dict(row)

    def history(self, mailbox_id: UUID, limit: int = 25) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            return [dict(row) for row in session.execute(text("""SELECT id, state, phase, progress, error_code, attempt, created_at, updated_at
                FROM jobs WHERE user_id = :user_id AND job_kind = 'gmail_sync' AND idempotency_key = :mailbox_id
                ORDER BY created_at DESC LIMIT :limit"""), {"user_id": self.user_id, "mailbox_id": str(mailbox_id), "limit": min(limit, 100)}).mappings()]

    def backfill(self, mailbox_id: UUID, query: str, mailboxes: MailboxService, oauth: GmailOAuthService, artifacts: GmailArtifactRepository, candidates: CandidateService, max_results: int = 500) -> dict[str, int]:
        if len(query) > 500 or not query.strip():
            raise SyncJobError("Backfill query is invalid")
        try:
            access_token = oauth.refresh_access_token(mailboxes.active_refresh_token(mailbox_id))
            message_ids = oauth.search_message_ids(access_token, query, max_results)
            added, skipped = 0, 0
            for message_id in message_ids:
                try:
                    raw_message = oauth.raw_message(access_token, message_id)
                except GmailOAuthError as error:
                    if str(error) != "Gmail message is no longer available":
                        raise
                    skipped += 1
                    continue
                created, artifact_id = artifacts.persist(mailbox_id, message_id, raw_message)
                if artifact_id is not None:
                    candidates.create_from_artifact(artifact_id, raw_message)
                added += int(created)
            return {"scanned": len(message_ids), "added": added, "duplicates": len(message_ids) - added - skipped, "skipped": skipped}
        except (MailboxError, GmailOAuthError, ValueError) as error:
            raise SyncJobError("Gmail historical backfill failed") from error

    def claim_next(self) -> dict[str, object] | None:
        """Atomically claim one queued Gmail job; safe for concurrent workers."""
        with Session(self.engine) as session, session.begin():
            row = session.execute(
                text("""SELECT id FROM jobs WHERE user_id = :user_id AND job_kind = 'gmail_sync'
                AND state = 'queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"""),
                {"user_id": self.user_id},
            ).scalar_one_or_none()
            if row is None:
                return None
            session.execute(
                text("""UPDATE jobs SET state = 'running', phase = 'fetching_history', attempt = attempt + 1,
                updated_at = now() WHERE id = :id"""), {"id": row}
            )
        return self.get_job(row)

    def finish(self, job_id: UUID, progress: dict[str, object]) -> dict[str, object]:
        return self._transition(job_id, "completed", "completed", progress, None)

    def fail(self, job_id: UUID, error_code: str) -> dict[str, object]:
        return self._transition(job_id, "failed", "failed", {}, error_code)

    def run_next_baseline(self, mailboxes: MailboxService, oauth: GmailOAuthService) -> dict[str, object] | None:
        """Run one job and establish a Gmail History baseline without reading mail bodies."""
        job = self.claim_next()
        if job is None:
            return None
        try:
            mailbox_id = UUID(str(job["progress"]["mailbox_id"]))
            refresh_token = mailboxes.active_refresh_token(mailbox_id)
            history_cursor = oauth.current_history_id(oauth.refresh_access_token(refresh_token))
            mailboxes.set_history_cursor(mailbox_id, history_cursor)
            return self.finish(job["id"], {"mailbox_id": str(mailbox_id), "mode": "baseline", "scanned": 0, "added": 0})
        except (MailboxError, GmailOAuthError, KeyError, ValueError):
            return self.fail(job["id"], "gmail_baseline_failed")

    def run_next(self, mailboxes: MailboxService, oauth: GmailOAuthService, artifacts: GmailArtifactRepository, candidates: CandidateService) -> dict[str, object] | None:
        job = self.claim_next()
        if job is None:
            return None
        try:
            mailbox_id = UUID(str(job["progress"]["mailbox_id"]))
            mailbox = next(item for item in mailboxes.list_mailboxes() if item["id"] == mailbox_id)
            access_token = oauth.refresh_access_token(mailboxes.active_refresh_token(mailbox_id))
            cursor = mailbox.get("history_cursor")
            if not isinstance(cursor, str) or not cursor:
                history_cursor = oauth.current_history_id(access_token)
                mailboxes.set_history_cursor(mailbox_id, history_cursor)
                return self.finish(job["id"], {"mailbox_id": str(mailbox_id), "mode": "baseline", "scanned": 0, "added": 0})
            try:
                message_ids, next_cursor = oauth.history_message_ids(access_token, cursor)
            except GmailOAuthError as error:
                # Gmail retains History IDs for a limited period. Resetting
                # the cursor is safe and avoids silently replaying a mailbox;
                # the user can use the explicit bounded backfill for history.
                if str(error) != "Gmail history cursor has expired":
                    raise
                mailboxes.set_history_cursor(mailbox_id, oauth.current_history_id(access_token))
                return self.finish(
                    job["id"],
                    {"mailbox_id": str(mailbox_id), "mode": "cursor_reset", "scanned": 0,
                     "added": 0, "reason": "gmail_history_expired"},
                )
            added, skipped = 0, 0
            for message_id in message_ids:
                try:
                    raw_message = oauth.raw_message(access_token, message_id)
                except GmailOAuthError as error:
                    if str(error) != "Gmail message is no longer available":
                        raise
                    skipped += 1
                    continue
                created, artifact_id = artifacts.persist(mailbox_id, message_id, raw_message)
                if artifact_id is not None:
                    candidates.create_from_artifact(artifact_id, raw_message)
                added += int(created)
            mailboxes.set_history_cursor(mailbox_id, next_cursor)
            return self.finish(job["id"], {"mailbox_id": str(mailbox_id), "mode": "incremental", "scanned": len(message_ids), "added": added, "duplicates": len(message_ids) - added - skipped, "skipped": skipped})
        except (MailboxError, GmailOAuthError, KeyError, StopIteration, ValueError) as error:
            logger.warning("Gmail sync job %s failed with %s: %s", job["id"], type(error).__name__, error)
            error_code = (
                "gmail_reconnect_required"
                if str(error) == "Gmail authorization needs to be reconnected"
                else "gmail_sync_failed"
            )
            return self.fail(job["id"], error_code)

    def _transition(
        self, job_id: UUID, state: str, phase: str, progress: dict[str, object], error_code: str | None
    ) -> dict[str, object]:
        with Session(self.engine) as session, session.begin():
            result = session.execute(
                text("""UPDATE jobs SET state = :state, phase = :phase, progress = CAST(:progress AS jsonb),
                error_code = :error_code, updated_at = now() WHERE id = :id AND user_id = :user_id
                AND state = 'running'"""),
                {"id": job_id, "user_id": self.user_id, "state": state, "phase": phase,
                 "progress": json.dumps(progress), "error_code": error_code},
            )
            if result.rowcount != 1:
                raise SyncJobError("Synchronization job is not running")
        return self.get_job(job_id)
