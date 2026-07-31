"""Idempotent persistence for raw Gmail message evidence."""

from __future__ import annotations

import hashlib
import json
import re
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
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
            # A discovery scan may revisit a message stored before actionable
            # statement notifications were introduced. Re-inspect its PDF
            # metadata without duplicating the source artifacts.
            self._persist_pdf_attachments(mailbox_id, message_id, raw_message)
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
        self._persist_pdf_attachments(mailbox_id, message_id, raw_message)
        return True, self._artifact_id(mailbox_id, message_id)

    def _persist_pdf_attachments(self, mailbox_id: UUID, message_id: str, raw_message: bytes) -> None:
        message = BytesParser(policy=policy.default).parsebytes(raw_message)
        subject = str(message.get("Subject") or "")
        sender = str(message.get("From") or "")
        try:
            message_date = parsedate_to_datetime(str(message.get("Date") or "")).isoformat()
        except (TypeError, ValueError):
            message_date = ""
        message_text = message.get_body(preferencelist=("plain", "html"))
        searchable_text = f"{subject} {message_text.get_content() if message_text else ''}"
        for ordinal, part in enumerate(message.iter_attachments(), start=1):
            content = part.get_payload(decode=True)
            if not isinstance(content, bytes) or not content.startswith(b"%PDF"):
                continue
            filename = part.get_filename() or "Statement.pdf"
            provider_message_id = f"{message_id}:attachment:{ordinal}"
            with Session(self.engine) as session:
                exists = session.execute(text("SELECT id FROM source_artifacts WHERE user_id = :user_id AND mailbox_id = :mailbox_id AND provider_message_id = :provider_message_id"), {"user_id": self.user_id, "mailbox_id": mailbox_id, "provider_message_id": provider_message_id}).scalar_one_or_none()
            if exists:
                with Session(self.engine) as session, session.begin():
                    self._create_statement_notification(
                        session, exists, sender, subject, filename, searchable_text, message_date
                    )
                continue
            stored = self.storage.put_gmail_attachment(self.user_id, mailbox_id, message_id, ordinal, content)
            artifact_id = uuid4()
            with Session(self.engine) as session, session.begin():
                result = session.execute(text("""INSERT INTO source_artifacts (id, user_id, kind, content_sha256,
                    object_key, detected_mime_type, byte_size, lifecycle_state, mailbox_id, provider_message_id)
                    VALUES (:id, :user_id, 'gmail_attachment', :sha, :object_key, 'application/pdf', :byte_size,
                    'active', :mailbox_id, :provider_message_id) ON CONFLICT (mailbox_id, provider_message_id)
                    WHERE mailbox_id IS NOT NULL AND provider_message_id IS NOT NULL DO NOTHING"""),
                    {"id": artifact_id, "user_id": self.user_id, "sha": hashlib.sha256(content).hexdigest(),
                     "object_key": stored.object_key, "byte_size": stored.byte_size, "mailbox_id": mailbox_id,
                     "provider_message_id": provider_message_id})
                if result.rowcount:
                    self._create_statement_notification(
                        session, artifact_id, sender, subject, filename, searchable_text, message_date
                    )
            if result.rowcount == 0:
                self.storage.delete(stored.object_key)

    def _create_statement_notification(
        self,
        session: Session,
        artifact_id: UUID,
        sender: str,
        subject: str,
        filename: str,
        searchable_text: str,
        message_date: str,
    ) -> None:
        """Keep one actionable notification for the latest savings statement per institution."""
        combined = f"{subject} {filename}".lower()
        searchable_lower = searchable_text.lower()
        if "statement" not in combined or re.search(
            r"\b(credit[\s-]?card|card statement)\b", searchable_lower
        ):
            return
        institution = _statement_institution(sender)
        if institution is None:
            return
        accounts = session.execute(
            text(
                """SELECT id, display_name, masked_identifier
                   FROM financial_accounts
                   WHERE user_id = :user_id AND account_type = 'bank_account'
                     AND status = 'active' AND lower(institution_code) = :institution"""
            ),
            {"user_id": self.user_id, "institution": institution},
        ).mappings().all()
        account_id: UUID | None = None
        if len(accounts) == 1:
            account_id = accounts[0]["id"]
        elif accounts:
            matching = [
                account for account in accounts
                if (digits := re.sub(r"\D", "", str(account["masked_identifier"] or ""))[-4:])
                and digits in searchable_text
            ]
            if len(matching) == 1:
                account_id = matching[0]["id"]
        payload = {
            "artifact_id": str(artifact_id),
            "account_id": str(account_id) if account_id else None,
            "institution_code": institution,
            "filename": filename,
            "message_date": message_date,
            "password_hint": _statement_password_guidance(searchable_text),
        }
        existing = session.execute(
            text(
                """SELECT action_payload
                   FROM notifications
                   WHERE user_id = :user_id
                     AND notification_kind = 'bank_statement_password_required'
                     AND deduplication_key = :key"""
            ),
            {"user_id": self.user_id, "key": institution},
        ).scalar_one_or_none()
        if isinstance(existing, dict):
            existing_date = str(existing.get("message_date") or "")
            if existing_date and message_date and existing_date > message_date:
                return
        session.execute(
            text(
                """INSERT INTO notifications
                   (id, user_id, notification_kind, deduplication_key, title, body,
                    action_kind, action_payload)
                   VALUES (:id, :user_id, 'bank_statement_password_required', :key,
                           :title, :body, 'confirm_statement_password',
                           CAST(:payload AS jsonb))
                   ON CONFLICT (user_id, notification_kind, deduplication_key)
                   DO UPDATE SET title = EXCLUDED.title, body = EXCLUDED.body,
                       action_kind = EXCLUDED.action_kind,
                       action_payload = EXCLUDED.action_payload,
                       state = 'unread', updated_at = now()"""
            ),
            {
                "id": uuid4(),
                "user_id": self.user_id,
                "key": institution,
                "title": f"New {institution.upper()} bank statement detected",
                "body": (
                    "Confirm the PDF password to review the latest statement and "
                    "update the recorded account balance."
                ),
                "payload": json.dumps(payload),
            },
        )

    def _artifact_id(self, mailbox_id: UUID, message_id: str) -> UUID | None:
        with Session(self.engine) as session:
            return session.execute(text("SELECT id FROM source_artifacts WHERE user_id = :user_id AND mailbox_id = :mailbox_id AND provider_message_id = :message_id"), {"user_id": self.user_id, "mailbox_id": mailbox_id, "message_id": message_id}).scalar_one_or_none()


def _statement_institution(sender: str) -> str | None:
    lowered = sender.lower()
    for institution, domains in {
        "hdfc": ("hdfcbank.com", "hdfcbank.net", "hdfcbank.bank.in"),
        "icici": ("icicibank.com", "icici.bank.in"),
        "sbi": ("sbi.co.in", "sbi.bank.in"),
        "dcb": ("dcbbank.com",),
        "axis": ("axisbank.com", "axis.bank.in"),
        "union_bank": ("unionbankofindia.bank.in", "unionbankofindia.co.in"),
        "dbs": ("dbs.com",),
    }.items():
        if any(domain in lowered for domain in domains):
            return institution
    return None


def _statement_password_guidance(value: str) -> str:
    """Return useful password instructions without copying a credential value."""
    compact = " ".join(re.sub(r"<[^>]+>", " ", value).split())
    lowered = compact.lower()
    if not re.search(r"\b(?:password|passcode|open the (?:pdf|statement))\b", lowered):
        return "Check the bank's statement email for its PDF password instructions."
    if re.search(r"\bcustomer\s*(?:id|number)\b", lowered):
        return "Use your Customer ID as the PDF password."
    if re.search(r"\b(?:date of birth|dob)\b", lowered):
        formats = re.findall(r"\b(?:DD|MM|YYYY|YY){2,4}\b", compact, re.I)
        suffix = f" in {formats[0].upper()} format" if formats else " in the format described in the email"
        return f"Use your date of birth{suffix} as the PDF password."
    if re.search(r"\bpan(?:\s+(?:number|card))?\b", lowered):
        return "Use the PAN-based password format described in the email."
    if re.search(r"\bregistered\s+mobile\b", lowered):
        return "Use the registered-mobile-number format described in the email."
    if re.search(r"\b(?:first|initial)\s+(?:four|4)\s+(?:letters?|characters?)\b", lowered):
        return "Use the name-based password format described in the email."
    if re.search(r"\b(?:password|passcode)\s*(?:is|:|-)\s*\S+", compact, re.I):
        return (
            "The email contains an explicit PDF password. For security, Arcis "
            "does not copy it; open the bank email and enter it here."
        )
    return "Follow the PDF password instructions in the bank's statement email."
