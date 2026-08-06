"""PDF statement staging and deterministic reconciliation services."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from email import policy
from email.parser import BytesParser
from uuid import UUID, uuid4

import fitz
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from arcis_backend.ledger import LedgerError
from arcis_backend.storage import MinioArtifactStorage

PARSER_VERSION = "2026-07-31"


@dataclass(frozen=True)
class ParsedStatement:
    parser_name: str
    metadata: dict[str, object]
    rows: tuple[dict[str, object], ...]


class StatementService:
    def __init__(self, engine: Engine, user_id: UUID, storage: MinioArtifactStorage) -> None:
        self.engine, self.user_id, self.storage = engine, user_id, storage

    def stage_pdf(self, account_id: UUID, filename: str, content: bytes, password: str | None) -> dict[str, object]:
        self._require_account(account_id)
        if not content.startswith(b"%PDF"):
            raise LedgerError("The uploaded file is not a PDF")
        if len(content) > 20 * 1024 * 1024:
            raise LedgerError("PDF statements must not exceed 20 MiB")
        parsed = parse_pdf_statement(filename, content, password)
        content_hash = hashlib.sha256(content).hexdigest()
        with Session(self.engine) as session:
            existing = session.execute(
                text("SELECT id FROM imports WHERE user_id = :user_id AND financial_account_id = :account_id AND content_sha256 = :hash"),
                {"user_id": self.user_id, "account_id": account_id, "hash": content_hash},
            ).scalar_one_or_none()
        if existing is not None:
            return self.preview(existing)
        import_id, statement_id = uuid4(), uuid4()
        stored = self.storage.put(self.user_id, import_id, _safe_filename(filename), content)
        try:
            with Session(self.engine) as session, session.begin():
                session.execute(
                    text("""INSERT INTO imports (id, user_id, financial_account_id, filename, content_sha256, state,
                    row_count, valid_row_count, invalid_row_count, object_key, detected_mime_type, byte_size)
                    VALUES (:id, :user_id, :account_id, :filename, :hash, 'preview_ready', :count, :count, 0,
                    :object_key, 'application/pdf', :byte_size)"""),
                    {"id": import_id, "user_id": self.user_id, "account_id": account_id,
                     "filename": _safe_filename(filename), "hash": content_hash, "count": len(parsed.rows),
                     "object_key": stored.object_key, "byte_size": stored.byte_size},
                )
                session.execute(
                    text("""INSERT INTO statements (id, user_id, financial_account_id, import_id, parser_name,
                    parser_version, period_start, period_end, opening_balance, closing_balance, statement_amount,
                    minimum_due, due_date, total_limit, available_limit, state)
                    VALUES (:id, :user_id, :account_id, :import_id, :parser_name, :parser_version, :period_start,
                    :period_end, :opening_balance, :closing_balance, :statement_amount, :minimum_due, :due_date,
                    :total_limit, :available_limit, 'preview_ready')"""),
                    {"id": statement_id, "user_id": self.user_id, "account_id": account_id,
                     "import_id": import_id, "parser_name": parsed.parser_name, "parser_version": PARSER_VERSION,
                     **parsed.metadata},
                )
                for ordinal, row in enumerate(parsed.rows, start=1):
                    session.execute(
                        text("""INSERT INTO import_rows (id, import_id, ordinal, transaction_date, posted_date,
                        narration, amount, currency, direction, provider_reference, raw_columns)
                        VALUES (:id, :import_id, :ordinal, :transaction_date, :posted_date, :narration, :amount,
                        :currency, :direction, :provider_reference, CAST(:raw_columns AS jsonb))"""),
                        {"id": uuid4(), "import_id": import_id, "ordinal": ordinal,
                         **{**row, "raw_columns": json.dumps(row["raw_columns"])}},
                    )
        except Exception:
            self.storage.delete(stored.object_key)
            raise
        return self.preview(import_id)

    def gmail_attachments(self) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            rows = session.execute(
                text(
                    """SELECT attachment.id, attachment.mailbox_id, attachment.provider_message_id,
                              attachment.byte_size, attachment.created_at, mailbox.display_email,
                              message.object_key AS message_object_key
                       FROM source_artifacts attachment
                       LEFT JOIN mailboxes mailbox ON mailbox.id = attachment.mailbox_id
                       LEFT JOIN source_artifacts message
                         ON message.user_id = attachment.user_id
                        AND message.mailbox_id = attachment.mailbox_id
                        AND message.kind = 'gmail_message'
                        AND message.provider_message_id =
                            split_part(attachment.provider_message_id, ':attachment:', 1)
                       WHERE attachment.user_id = :user_id
                         AND attachment.kind = 'gmail_attachment'
                         AND attachment.lifecycle_state = 'active'
                       ORDER BY attachment.created_at DESC LIMIT 20"""
                ),
                {"user_id": self.user_id},
            ).mappings()
            attachments = []
            for row in rows:
                item = dict(row)
                item.update(self._gmail_attachment_labels(item))
                item.pop("message_object_key", None)
                attachments.append(item)
            return attachments

    def _gmail_attachment_labels(self, attachment: dict[str, object]) -> dict[str, str]:
        labels = {"subject": "Monthly statement", "filename": "Statement.pdf"}
        object_key = attachment.get("message_object_key")
        provider_message_id = str(attachment.get("provider_message_id") or "")
        if not object_key:
            return labels
        try:
            message = BytesParser(policy=policy.default).parsebytes(self.storage.get_bytes(str(object_key)))
            labels["subject"] = str(message.get("Subject") or labels["subject"])
            ordinal = int(provider_message_id.rsplit(":attachment:", 1)[1])
            part = list(message.iter_attachments())[ordinal - 1]
            labels["filename"] = part.get_filename() or labels["filename"]
        except (IndexError, TypeError, ValueError):
            pass
        return labels

    def stage_gmail_attachment(self, artifact_id: UUID, account_id: UUID, password: str | None) -> dict[str, object]:
        with Session(self.engine) as session:
            artifact = session.execute(text("""SELECT object_key, provider_message_id FROM source_artifacts
                WHERE id = :id AND user_id = :user_id AND kind = 'gmail_attachment'"""),
                {"id": artifact_id, "user_id": self.user_id}).mappings().one_or_none()
        if artifact is None:
            raise LedgerError("Gmail statement attachment was not found")
        return self.stage_pdf(account_id, f"gmail-{artifact['provider_message_id']}.pdf", self.storage.get_bytes(artifact["object_key"]), password)

    def preview(self, import_id: UUID) -> dict[str, object]:
        with Session(self.engine) as session:
            imported = session.execute(text("SELECT id, financial_account_id, filename, state, row_count, valid_row_count, invalid_row_count, created_at FROM imports WHERE id = :id AND user_id = :user_id"), {"id": import_id, "user_id": self.user_id}).mappings().one_or_none()
            statement = session.execute(text("SELECT parser_name, parser_version, period_start, period_end, opening_balance, closing_balance, statement_amount, minimum_due, due_date, total_limit, available_limit, state FROM statements WHERE import_id = :id AND user_id = :user_id"), {"id": import_id, "user_id": self.user_id}).mappings().one_or_none()
            rows = [dict(row) for row in session.execute(text("SELECT id, ordinal, transaction_date, posted_date, narration, amount, currency, direction, provider_reference FROM import_rows WHERE import_id = :id ORDER BY ordinal"), {"id": import_id}).mappings()]
        if imported is None or statement is None:
            raise LedgerError("PDF statement import was not found")
        return {"import": dict(imported), "statement": dict(statement), "rows": rows, "errors": []}

    def has_statement(self, import_id: UUID) -> bool:
        with Session(self.engine) as session:
            return session.execute(
                text("SELECT 1 FROM statements WHERE import_id = :id AND user_id = :user_id"),
                {"id": import_id, "user_id": self.user_id},
            ).scalar_one_or_none() is not None

    def confirm(self, import_id: UUID) -> dict[str, int]:
        with Session(self.engine) as session, session.begin():
            statement = session.execute(text("SELECT s.*, i.content_sha256, i.object_key, i.byte_size FROM statements s JOIN imports i ON i.id = s.import_id WHERE s.import_id = :id AND s.user_id = :user_id FOR UPDATE"), {"id": import_id, "user_id": self.user_id}).mappings().one_or_none()
            if statement is None:
                raise LedgerError("PDF statement import was not found")
            if statement["state"] in {"confirmed", "reconciled"}:
                return {"created": 0, "matched": 0, "uncertain": 0, "confirmed": 1}
            artifact_id = uuid4()
            session.execute(text("""INSERT INTO source_artifacts (id, user_id, kind, content_sha256, object_key,
                detected_mime_type, byte_size, lifecycle_state, import_id)
                VALUES (:id, :user_id, 'manual_upload', :hash, :object_key, 'application/pdf', :byte_size, 'active', :import_id)
                ON CONFLICT (user_id, kind, content_sha256) DO NOTHING"""),
                {"id": artifact_id, "user_id": self.user_id, "hash": statement["content_sha256"],
                 "object_key": statement["object_key"], "byte_size": statement["byte_size"], "import_id": import_id})
            artifact_id = session.execute(text("SELECT id FROM source_artifacts WHERE user_id = :user_id AND kind = 'manual_upload' AND content_sha256 = :hash"), {"user_id": self.user_id, "hash": statement["content_sha256"]}).scalar_one()
            created = matched = uncertain = 0
            for row in session.execute(text("SELECT * FROM import_rows WHERE import_id = :id ORDER BY ordinal"), {"id": import_id}).mappings():
                source_id = uuid4()
                inserted = session.execute(text("""INSERT INTO source_records (id, user_id, artifact_id, source_record_key,
                    transaction_date, posted_date, narration, amount, currency, direction, provider_reference)
                    VALUES (:id, :user_id, :artifact_id, :source_key, :transaction_date, :posted_date, :narration,
                    :amount, :currency, :direction, :reference) ON CONFLICT (artifact_id, source_record_key) DO NOTHING"""),
                    {"id": source_id, "user_id": self.user_id, "artifact_id": artifact_id,
                     "source_key": f"{import_id}:{row['ordinal']}", "transaction_date": row["transaction_date"],
                     "posted_date": row["posted_date"], "narration": row["narration"], "amount": row["amount"],
                     "currency": row["currency"], "direction": row["direction"], "reference": row["provider_reference"]})
                if inserted.rowcount == 0:
                    continue
                source_id = session.execute(text("SELECT id FROM source_records WHERE artifact_id = :artifact_id AND source_record_key = :source_key"), {"artifact_id": artifact_id, "source_key": f"{import_id}:{row['ordinal']}"}).scalar_one()
                candidates = _match_transactions(session, self.user_id, statement["financial_account_id"], row)
                if len(candidates) == 1 and candidates[0]["score"] >= Decimal("0.95"):
                    transaction_id = candidates[0]["id"]
                    _link_evidence(session, transaction_id, source_id, candidates[0]["method"], candidates[0]["score"])
                    session.execute(text("UPDATE transactions SET reconciliation_state = 'statement_confirmed', updated_at = now() WHERE id = :id"), {"id": transaction_id})
                    matched += 1
                elif candidates:
                    for candidate in candidates:
                        session.execute(text("""INSERT INTO reconciliation_reviews (id, user_id, statement_id, import_row_id,
                        transaction_id, state, match_method, match_score, reason) VALUES (:id, :user_id, :statement_id,
                        :row_id, :transaction_id, 'needs_review', :method, :score, :reason) ON CONFLICT DO NOTHING"""),
                        {"id": uuid4(), "user_id": self.user_id, "statement_id": statement["id"], "row_id": row["id"],
                         "transaction_id": candidate["id"], "method": candidate["method"], "score": candidate["score"],
                         "reason": "More than one plausible ledger transaction matched this statement row"})
                    uncertain += 1
                else:
                    transaction_id = uuid4()
                    session.execute(text("""INSERT INTO transactions (id, user_id, financial_account_id, transaction_date,
                    posted_date, narration, amount, currency, direction, transaction_kind, reconciliation_state,
                    source_record_id, provider_reference) VALUES (:id, :user_id, :account_id, :transaction_date,
                    :posted_date, :narration, :amount, :currency, :direction, :kind, 'statement_only', :source_id, :reference)"""),
                    {"id": transaction_id, "user_id": self.user_id, "account_id": statement["financial_account_id"],
                     "transaction_date": row["transaction_date"], "posted_date": row["posted_date"],
                     "narration": row["narration"], "amount": row["amount"], "currency": row["currency"],
                     "direction": row["direction"], "kind": _kind(row["narration"]), "source_id": source_id,
                     "reference": row["provider_reference"]})
                    _link_evidence(session, transaction_id, source_id, "statement_only", Decimal("1"))
                    created += 1
            state = "reconciled" if uncertain == 0 else "confirmed"
            session.execute(text("UPDATE statements SET state = :state, confirmed_at = now() WHERE id = :id"), {"state": state, "id": statement["id"]})
            session.execute(text("UPDATE imports SET state = 'confirmed', confirmed_at = now(), duplicate_count = :duplicates WHERE id = :id"), {"duplicates": matched, "id": import_id})
        return {"created": created, "matched": matched, "uncertain": uncertain, "confirmed": 1}

    def reviews(self, state: str = "needs_review") -> list[dict[str, object]]:
        with Session(self.engine) as session:
            return [dict(row) for row in session.execute(text("""SELECT rr.id, rr.state, rr.match_method, rr.match_score,
                rr.reason, ir.ordinal, ir.transaction_date, ir.narration, ir.amount, ir.direction,
                t.narration AS candidate_narration, t.transaction_date AS candidate_date
                FROM reconciliation_reviews rr JOIN import_rows ir ON ir.id = rr.import_row_id
                LEFT JOIN transactions t ON t.id = rr.transaction_id WHERE rr.user_id = :user_id AND rr.state = :state
                ORDER BY rr.created_at DESC"""), {"user_id": self.user_id, "state": state}).mappings()]

    def review(self, review_id: UUID, decision: str) -> dict[str, object]:
        if decision not in {"accepted", "rejected"}:
            raise LedgerError("Reconciliation decision is invalid")
        with Session(self.engine) as session, session.begin():
            review = session.execute(text("SELECT * FROM reconciliation_reviews WHERE id = :id AND user_id = :user_id FOR UPDATE"), {"id": review_id, "user_id": self.user_id}).mappings().one_or_none()
            if review is None or review["state"] != "needs_review":
                raise LedgerError("Reconciliation review is not available")
            source_id = _source_id_for_row(session, review["statement_id"], review["import_row_id"])
            if decision == "accepted" and review["transaction_id"] is not None:
                _link_evidence(session, review["transaction_id"], source_id, "manual_reconciliation", Decimal("1"))
                session.execute(text("UPDATE transactions SET reconciliation_state = 'statement_confirmed', updated_at = now() WHERE id = :id"), {"id": review["transaction_id"]})
                session.execute(text("""UPDATE reconciliation_reviews SET state = 'rejected', reviewed_at = now()
                    WHERE import_row_id = :row_id AND id != :id AND state = 'needs_review'"""),
                    {"row_id": review["import_row_id"], "id": review_id})
            session.execute(text("UPDATE reconciliation_reviews SET state = :state, reviewed_at = now() WHERE id = :id"), {"state": decision, "id": review_id})
            if decision == "rejected":
                remaining = session.execute(text("SELECT 1 FROM reconciliation_reviews WHERE import_row_id = :row_id AND state = 'needs_review'"), {"row_id": review["import_row_id"]}).scalar_one_or_none()
                if remaining is None:
                    row = session.execute(text("SELECT * FROM import_rows WHERE id = :id"), {"id": review["import_row_id"]}).mappings().one()
                    account_id = session.execute(text("SELECT financial_account_id FROM statements WHERE id = :id"), {"id": review["statement_id"]}).scalar_one()
                    _create_statement_only(session, self.user_id, account_id, row, source_id)
        return {"id": review_id, "state": decision}

    def _require_account(self, account_id: UUID) -> None:
        with Session(self.engine) as session:
            found = session.execute(text("SELECT 1 FROM financial_accounts WHERE id = :id AND user_id = :user_id AND status = 'active'"), {"id": account_id, "user_id": self.user_id}).scalar_one_or_none()
        if found is None:
            raise LedgerError("Financial account was not found")


def parse_pdf_statement(filename: str, content: bytes, password: str | None) -> ParsedStatement:
    """Parse a statement in a bounded child process; passwords never enter logs or storage."""
    with tempfile.TemporaryDirectory(prefix="arcis-pdf-") as temporary_directory:
        input_path = f"{temporary_directory}/statement.pdf"
        with open(input_path, "wb") as handle:
            handle.write(content)
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "arcis_backend.pdf_worker", input_path, filename],
                input=(password or "").encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=30,
            )
        except subprocess.TimeoutExpired as error:
            raise LedgerError("PDF statement parsing timed out") from error
    if completed.returncode != 0:
        try:
            error_code = json.loads(completed.stdout).get("error")
        except (AttributeError, json.JSONDecodeError):
            error_code = None
        messages = {
            "password": "PDF password is required or incorrect",
            "no_text": "PDF opened successfully but contains no extractable text; OCR is not enabled yet",
            "unsupported_layout": "PDF opened successfully, but this statement layout is not supported yet",
            "invalid_pdf": "PDF statement could not be opened safely",
        }
        raise LedgerError(messages.get(error_code, "PDF statement parsing failed"))
    try:
        result = json.loads(completed.stdout)
        metadata = {
            key: Decimal(value) if key in {"opening_balance", "closing_balance", "statement_amount", "minimum_due", "total_limit", "available_limit"} and value is not None
            else date.fromisoformat(value) if key in {"period_start", "period_end", "due_date"} and value is not None
            else value
            for key, value in result["metadata"].items()
        }
        rows = tuple({**row, "transaction_date": date.fromisoformat(row["transaction_date"]), "posted_date": date.fromisoformat(row["posted_date"]) if row["posted_date"] else None, "amount": Decimal(row["amount"])} for row in result["rows"])
        return ParsedStatement(result["parser_name"], metadata, rows)
    except (KeyError, TypeError, ValueError, InvalidOperation, json.JSONDecodeError) as error:
        raise LedgerError("PDF statement parser returned an invalid result") from error


def parse_pdf_statement_in_process(filename: str, content: bytes, password: str | None) -> ParsedStatement:
    try:
        document = fitz.open(stream=content, filetype="pdf")
        if document.needs_pass and (not password or document.authenticate(password) <= 0):
            raise LedgerError("PDF password is required or incorrect")
        pages = list(document)
        document_text = "\n".join(page.get_text("text") for page in pages)
        positioned_text = "\n".join(
            "\n".join(
                part
                for part in (
                    _positioned_lines(page),
                    _positioned_deposit_withdrawal_lines(page),
                )
                if part
            )
            for page in pages
        )
    except fitz.FileDataError as error:
        raise LedgerError("PDF statement could not be opened") from error
    finally:
        if "document" in locals():
            document.close()
    if not document_text.strip():
        raise LedgerError("PDF statement has no extractable text; OCR support is not enabled")
    lowered = f"{filename}\n{document_text}".lower()
    filename_lower = filename.lower().replace("-", " ").replace("_", " ")
    is_credit_card = any(marker in filename_lower for marker in ("credit card", "amazon pay", "card statement"))
    is_sbi = bool(re.search(r"\b(?:state bank of india|sbi)\b", lowered))
    parser = "icici_credit_card_pdf" if is_credit_card and "icici" in lowered else "icici_bank_pdf" if "icici" in lowered else "hdfc_bank_pdf" if "hdfc" in lowered else "sbi_bank_pdf" if is_sbi else "generic_pdf"
    parse_text = _sbi_savings_section(document_text) if is_sbi else document_text
    positioned_parse_text = _sbi_savings_section(positioned_text) if is_sbi else positioned_text
    rows = _parse_rows(
        parse_text,
        is_credit_card=is_credit_card,
        credit_before_debit=is_sbi,
    )
    for positioned_row in _parse_rows(
        positioned_parse_text,
        is_credit_card=is_credit_card,
        credit_before_debit=is_sbi,
    ):
        _merge_extracted_row(rows, positioned_row)
    if not rows:
        raise LedgerError("Supported PDF statement format was detected but no transaction rows could be extracted")
    metadata = _metadata(parse_text)
    if not is_credit_card:
        if metadata["opening_balance"] is None:
            metadata["opening_balance"] = (
                _brought_forward_balance(parse_text)
                or _brought_forward_balance(positioned_parse_text)
            )
        if metadata["period_start"] is None:
            metadata["period_start"] = min(row["transaction_date"] for row in rows)
        if metadata["period_end"] is None:
            metadata["period_end"] = max(row["transaction_date"] for row in rows)
        if metadata["closing_balance"] is None:
            metadata["closing_balance"] = _last_running_balance(rows)
    return ParsedStatement(parser, metadata, tuple(rows))


def _sbi_savings_section(value: str) -> str:
    """Exclude loan-account sections from an SBI consolidated statement.

    SBI statements can contain an SB account followed by Demand Loan (DL) or
    Term Loan (TL) accounts. Account-type headings are treated as hard section
    boundaries. Unknown/global header lines remain available for statement
    metadata, but rows after a loan heading remain excluded until a savings
    heading is encountered.
    """
    lines = value.splitlines()
    classifications = [_sbi_account_section(line) for line in lines]
    if False not in classifications:
        return value
    selected: list[str] = []
    include_section: bool | None = None
    for line, classification in zip(lines, classifications, strict=True):
        if classification is not None:
            include_section = classification
        if include_section is not False:
            selected.append(line)
    return "\n".join(selected)


def _sbi_account_section(line: str) -> bool | None:
    """Return True for savings, False for DL/TL loan, and None otherwise."""
    compact = " ".join(line.split())
    # SBI relationship-summary statements label their combined loan section
    # as ``DL/TL ACCOUNT``.  Treat the slash form as a hard boundary before
    # looking for the more general account headings below.
    if re.search(r"^\s*DL\s*/\s*TL\s+(?:bank\s+)?(?:account|a/c)\b", compact, re.I):
        return False
    heading = bool(
        re.search(
            r"\b(?:account|a/c)\s*(?:type|category|product)\b"
            r"|\b(?:type|category|product)\s+of\s+(?:account|a/c)\b",
            compact,
            re.I,
        )
    )
    explicit_section = bool(
        re.search(
            r"^\s*(?:savings?|sb(?:chq)?|demand\s+loan|term\s+loan|DL(?:\s*/\s*TL)?|TL)"
            r"\s+(?:bank\s+)?(?:account|a/c)\b",
            compact,
            re.I,
        )
    )
    if not heading and not explicit_section:
        return None
    if re.search(r"\b(?:demand\s+loan|term\s+loan|loan|DL|TL)\b", compact, re.I):
        return False
    if re.search(r"\b(?:savings?|SB(?:CHQ)?)\b", compact, re.I):
        return True
    return None


def _parse_rows(
    value: str,
    *,
    is_credit_card: bool,
    credit_before_debit: bool = False,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    patterns = (
        re.compile(r"(?P<date>\d{2}[/-]\d{2}[/-]\d{4})\s+(?P<narration>.+?)\s+(?P<amount>[\d,]+\.\d{2})\s*(?P<direction>DR|CR|DEBIT|CREDIT)\b", re.I),
        re.compile(r"(?P<date>\d{2}\s+[A-Za-z]{3}\s+\d{4})\s+(?P<narration>.+?)\s+(?P<amount>[\d,]+\.\d{2})\s*(?P<direction>DR|CR)\b", re.I),
    )
    for line in value.splitlines():
        compact = " ".join(line.split())
        for pattern in patterns:
            match = pattern.search(compact)
            if match is None:
                continue
            try:
                transaction_date = _date(match["date"])
                amount = _money(match["amount"])
            except LedgerError:
                break
            direction = "credit" if match["direction"].upper() in {"CR", "CREDIT"} else "debit"
            narration = match["narration"].strip(" -")
            if _is_brought_forward(narration) or _is_statement_summary(narration):
                break
            rows.append({"transaction_date": transaction_date, "posted_date": None, "narration": narration,
                         "amount": amount, "currency": "INR", "direction": direction,
                         "provider_reference": None, "raw_columns": {"line": compact}})
            break
    for fallback in _parse_columnar_rows(
        value,
        is_credit_card=is_credit_card,
        credit_before_debit=credit_before_debit,
    ):
        _merge_extracted_row(rows, fallback)
    return sorted(rows, key=lambda row: (row["transaction_date"], row["narration"], row["amount"]))


def _merge_extracted_row(rows: list[dict[str, object]], candidate: dict[str, object]) -> None:
    """Prefer a reconstructed wrapped row over its partial visual-line copy."""
    generic_modes = {"mobile banking", "internet banking", "net banking"}
    candidate_narration = str(candidate["narration"]).strip()
    candidate_normalized = " ".join(candidate_narration.lower().split())
    for index, existing in enumerate(rows):
        if any(
            existing[field] != candidate[field]
            for field in ("transaction_date", "amount")
        ):
            continue
        existing_narration = str(existing["narration"]).strip()
        existing_normalized = " ".join(existing_narration.lower().split())
        same_description = (
            existing_normalized in candidate_normalized
            or candidate_normalized in existing_normalized
            or existing_normalized in generic_modes
            or candidate_normalized in generic_modes
        )
        if not same_description:
            continue
        candidate_line = str(candidate.get("raw_columns", {}).get("line", ""))
        existing_line = str(existing.get("raw_columns", {}).get("line", ""))
        candidate_explicit = bool(re.search(r"\s(?:CR|DR)\s", candidate_line, re.I))
        existing_explicit = bool(re.search(r"\s(?:CR|DR)\s", existing_line, re.I))
        if candidate_explicit and not existing_explicit:
            rows[index] = candidate
        elif candidate_explicit == existing_explicit and len(candidate_narration) > len(existing_narration):
            rows[index] = candidate
        return
    rows.append(candidate)


def _parse_columnar_rows(
    value: str,
    *,
    is_credit_card: bool,
    credit_before_debit: bool = False,
) -> list[dict[str, object]]:
    """Fallback for text PDFs where debit, credit, and balance are separate columns."""
    rows: list[dict[str, object]] = []
    previous_balance: Decimal | None = None
    date_prefix = re.compile(r"^(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}[ -][A-Za-z]{3}[ -]\d{2,4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})\s+(?P<body>.+)$")
    money_pattern = re.compile(r"(?<![\d/.-])(?:₹|rs\.?\s*)?(?P<amount>[\d,]+\.\d{2})(?![\d.])", re.I)
    for line in value.splitlines():
        compact = " ".join(line.split())
        match = date_prefix.match(compact)
        if match is None:
            continue
        try:
            transaction_date = _date(match["date"])
        except LedgerError:
            continue
        body = match["body"]
        amounts = [item["amount"] for item in money_pattern.finditer(body)]
        if not amounts:
            continue
        # Card statements generally have one charge amount. Bank statements
        # commonly emit debit, credit, and running balance as three columns.
        # Use the non-zero debit/credit value, never the running balance.
        amount_text = amounts[-1] if is_credit_card else amounts[0]
        column_direction: str | None = None
        amount_values = [_money(amount) for amount in amounts]
        if not is_credit_card and len(amounts) >= 3:
            if credit_before_debit:
                credit_amount, debit_amount = amount_values[0], amount_values[1]
            else:
                debit_amount, credit_amount = amount_values[0], amount_values[1]
            if debit_amount == 0 and credit_amount > 0:
                amount_text = amounts[0] if credit_before_debit else amounts[1]
                column_direction = "credit"
            elif credit_amount == 0 and debit_amount > 0:
                amount_text = amounts[1] if credit_before_debit else amounts[0]
                column_direction = "debit"
            previous_balance = amount_values[-1]
        elif not is_credit_card and len(amounts) == 2:
            running_balance = amount_values[-1]
            if previous_balance is not None and running_balance != previous_balance:
                column_direction = "credit" if running_balance > previous_balance else "debit"
            previous_balance = running_balance
        narration = body[: money_pattern.search(body).start()].strip(" -:|")
        if len(narration) < 2 or narration.lower() in {"transaction", "description", "particulars"}:
            continue
        if _is_brought_forward(narration) or _is_statement_summary(narration):
            continue
        direction = column_direction or _column_direction(body, narration, is_credit_card)
        rows.append({"transaction_date": transaction_date, "posted_date": None, "narration": narration,
                     "amount": _money(amount_text), "currency": "INR", "direction": direction,
                     "provider_reference": _reference(body), "raw_columns": {"line": compact}})
    return rows


def _column_direction(body: str, narration: str, is_credit_card: bool) -> str:
    if re.search(r"\b(?:cr|credit|refund|reversal)\b", body, re.I):
        return "credit"
    if re.search(r"\b(?:dr|debit)\b", body, re.I):
        return "debit"
    if is_credit_card and re.search(r"\b(?:payment received|payment|cashback|adjustment)\b", narration, re.I):
        return "credit"
    if not is_credit_card and re.search(
        r"\b(?:savings?|sb)\s+int\.?\b|\binterest\s+(?:paid|credited)\b",
        narration,
        re.I,
    ):
        return "credit"
    return "debit"


def _reference(body: str) -> str | None:
    match = re.search(r"\b(?:ref(?:erence)?(?:\s*(?:no|number))?\s*[:#-]?\s*)?([A-Z0-9]{10,})\b", body, re.I)
    return match.group(1) if match else None


def _metadata(value: str) -> dict[str, object]:
    period_range = re.search(
        r"(?:statement\s+period|period)\D{0,20}"
        r"(?P<start>\d{1,2}[/-][A-Za-z]{3}[/-]\d{2,4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"
        r"\D{1,20}(?P<end>\d{1,2}[/-][A-Za-z]{3}[/-]\d{2,4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        value,
        re.I,
    )
    period_start = _date(period_range["start"]) if period_range else _find_date(
        value,
        r"(?:statement\s+period|period)\D{0,20}"
        r"(\d{1,2}[/-][A-Za-z]{3}[/-]\d{2,4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    )
    period_end = _date(period_range["end"]) if period_range else _find_date(
        value,
        r"(?:statement\s+date|as\s+on|ending\s+on)\D{0,20}"
        r"(\d{1,2}[/-][A-Za-z]{3}[/-]\d{2,4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    )
    return {"period_start": period_start,
            "period_end": period_end,
            "opening_balance": _find_money(
                value,
                r"opening\s+balance(?:\s+on\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4})?\D{0,20}([\d,]+\.\d{2})",
            ),
            "closing_balance": _find_money(
                value,
                r"closing\s+balance(?:\s+on\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4})?\D{0,20}([\d,]+\.\d{2})",
            ),
            "statement_amount": _find_money(value, r"(?:total\s+amount\s+due|statement\s+amount)\D{0,20}([\d,]+\.\d{2})"),
            "minimum_due": _find_money(value, r"minimum\s+(?:amount\s+)?due\D{0,20}([\d,]+\.\d{2})"),
            "due_date": _find_date(value, r"payment\s+due\s+date\D{0,20}(\d{1,2}[/-][A-Za-z]{3}[/-]\d{2,4}|\d{2}[/-]\d{2}[/-]\d{4})"),
            "total_limit": _find_money(value, r"total\s+credit\s+limit\D{0,20}([\d,]+\.\d{2})"),
            "available_limit": _find_money(value, r"available\s+credit\s+limit\D{0,20}([\d,]+\.\d{2})")}


def _is_brought_forward(narration: str) -> bool:
    """Identify balance carry-forward labels that are not ledger activity."""
    return bool(
        re.search(
            r"(?:^|\b)b\s*/\s*f(?:\b|$)|\bbrought\s+forward\b|\bbalance\s+b/f\b",
            narration,
            re.I,
        )
    )


def _is_statement_summary(narration: str) -> bool:
    """Reject dated-looking statement totals, addresses, and balance summaries."""
    return bool(
        re.search(
            r"\btotal\s+(?:deposits?\s*(?:&|and)\s*investments?|balance|assets?)\b"
            r"|\b(?:closing|current|available)\s+balance\b",
            narration,
            re.I,
        )
    )


def _brought_forward_balance(value: str) -> Decimal | None:
    """Use the final amount on a B/F row as the statement opening balance."""
    money_pattern = re.compile(
        r"(?<![\d/.-])(?:₹|rs\.?\s*)?([\d,]+\.\d{2})(?![\d.])",
        re.I,
    )
    for line in value.splitlines():
        if not _is_brought_forward(line):
            continue
        amounts = money_pattern.findall(line)
        if amounts:
            return _money(amounts[-1])
    return None


def _last_running_balance(rows: list[dict[str, object]]) -> Decimal | None:
    """Read the final balance column without treating it as a transaction amount."""
    money_pattern = re.compile(r"(?<![\d/.-])(?:₹|rs\.?\s*)?([\d,]+\.\d{2})(?![\d.])", re.I)
    for row in sorted(rows, key=lambda item: item["transaction_date"], reverse=True):
        raw_columns = row.get("raw_columns")
        line = raw_columns.get("line") if isinstance(raw_columns, dict) else None
        amounts = money_pattern.findall(str(line or ""))
        if len(amounts) >= 2:
            return _money(amounts[-1])
    return None


def _match_transactions(session: Session, user_id: UUID, account_id: UUID, row: object) -> list[dict[str, object]]:
    candidates = [dict(item) for item in session.execute(text("""SELECT id, transaction_date, narration, provider_reference
        FROM transactions WHERE user_id = :user_id AND financial_account_id = :account_id AND amount = :amount
        AND direction = :direction AND currency = :currency AND transaction_date BETWEEN :start_date AND :end_date"""),
        {"user_id": user_id, "account_id": account_id, "amount": row["amount"], "direction": row["direction"], "currency": row["currency"],
         "start_date": row["transaction_date"] - timedelta(days=3), "end_date": row["transaction_date"] + timedelta(days=3)}).mappings()]
    for candidate in candidates:
        same_reference = row["provider_reference"] and row["provider_reference"] == candidate["provider_reference"]
        same_date = row["transaction_date"] == candidate["transaction_date"]
        candidate["score"] = Decimal("1") if same_reference else Decimal("0.98") if same_date else Decimal("0.70")
        candidate["method"] = "reference" if same_reference else "account_amount_date" if same_date else "account_amount_near_date"
    return candidates


def _link_evidence(session: Session, transaction_id: UUID, source_id: UUID, method: str, score: Decimal) -> None:
    session.execute(text("""INSERT INTO transaction_evidence (transaction_id, source_record_id, relationship, match_method, match_score)
        VALUES (:transaction_id, :source_id, 'supporting', :method, :score) ON CONFLICT DO NOTHING"""),
        {"transaction_id": transaction_id, "source_id": source_id, "method": method, "score": score})


def _source_id_for_row(session: Session, statement_id: UUID, row_id: UUID) -> UUID:
    source_id = session.execute(text("""SELECT sr.id FROM source_records sr
        JOIN source_artifacts sa ON sa.id = sr.artifact_id
        JOIN statements s ON s.import_id = sa.import_id
        JOIN import_rows ir ON ir.import_id = s.import_id
        WHERE s.id = :statement_id AND ir.id = :row_id
          AND sr.source_record_key = ir.import_id::text || ':' || ir.ordinal::text"""),
        {"statement_id": statement_id, "row_id": row_id}).scalar_one_or_none()
    if source_id is None:
        raise LedgerError("Statement source record was not found")
    return source_id


def _create_statement_only(session: Session, user_id: UUID, account_id: UUID, row: object, source_id: UUID) -> None:
    transaction_id = uuid4()
    session.execute(text("""INSERT INTO transactions (id, user_id, financial_account_id, transaction_date,
        posted_date, narration, amount, currency, direction, transaction_kind, reconciliation_state,
        source_record_id, provider_reference) VALUES (:id, :user_id, :account_id, :transaction_date,
        :posted_date, :narration, :amount, :currency, :direction, :kind, 'statement_only', :source_id, :reference)"""),
        {"id": transaction_id, "user_id": user_id, "account_id": account_id,
         "transaction_date": row["transaction_date"], "posted_date": row["posted_date"],
         "narration": row["narration"], "amount": row["amount"], "currency": row["currency"],
         "direction": row["direction"], "kind": _kind(row["narration"]), "source_id": source_id,
         "reference": row["provider_reference"]})
    _link_evidence(session, transaction_id, source_id, "statement_only_after_review", Decimal("1"))


def _date(value: str) -> date:
    for pattern in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d %b %Y", "%d %b %y", "%d-%b-%Y", "%d-%b-%y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise LedgerError("Statement transaction date is invalid")


def _money(value: str) -> Decimal:
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation as error:
        raise LedgerError("Statement amount is invalid") from error


def _find_money(value: str, pattern: str) -> Decimal | None:
    match = re.search(pattern, value, re.I)
    return _money(match.group(1)) if match else None


def _find_date(value: str, pattern: str) -> date | None:
    match = re.search(pattern, value, re.I)
    return _date(match.group(1)) if match else None


def _kind(narration: str) -> str:
    if re.search(r"refund|reversal", narration, re.I):
        return "refund"
    if re.search(r"card payment|credit card payment|card bill|payment received", narration, re.I):
        return "credit_card_payment"
    return "unknown"


def _safe_filename(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", filename)[:180] or "statement.pdf"


def _positioned_lines(page: fitz.Page) -> str:
    """Reconstruct visual table rows when PDF text extraction separates columns."""
    words = sorted(page.get_text("words"), key=lambda word: (round(word[1] / 3), word[0]))
    lines: list[list[object]] = []
    for word in words:
        if not lines or abs(float(word[1]) - float(lines[-1][0][1])) > 3:
            lines.append([word])
        else:
            lines[-1].append(word)
    return "\n".join(" ".join(str(word[4]) for word in line) for line in lines)


def _positioned_deposit_withdrawal_lines(page: fitz.Page) -> str:
    """Rebuild wrapped bank rows using the table's visual column positions.

    ICICI savings statements render a transaction's date, mode, multi-line
    particulars, deposit, withdrawal, and balance in separate text boxes. A
    normal text extraction can therefore put the date and amount on different
    lines. The visible column headers provide stable x-axis boundaries, while
    transaction dates provide the y-axis row anchors.
    """
    words = list(page.get_text("words"))
    header_positions: dict[str, float] = {}
    for word in words:
        label = str(word[4]).upper().rstrip(":")
        if label in {"DATE", "MODE", "PARTICULARS", "DEPOSITS", "WITHDRAWALS", "BALANCE"}:
            header_positions.setdefault(label, float(word[0]))
    required = {"DATE", "PARTICULARS", "DEPOSITS", "WITHDRAWALS", "BALANCE"}
    if not required.issubset(header_positions):
        return ""

    date_pattern = re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$")
    date_words = sorted(
        (word for word in words if date_pattern.fullmatch(str(word[4]))),
        key=lambda word: float(word[1]),
    )
    if not date_words:
        return ""

    particulars_x = header_positions["PARTICULARS"]
    deposits_x = header_positions["DEPOSITS"]
    withdrawals_x = header_positions["WITHDRAWALS"]
    balance_x = header_positions["BALANCE"]
    money_pattern = re.compile(r"^(?:₹|rs\.?\s*)?[\d,]+\.\d{2}$", re.I)

    def money_cells(start: float, end: float | None = None) -> list[tuple[object, ...]]:
        return [
            word
            for word in words
            if float(word[0]) >= start
            and (end is None or float(word[0]) < end)
            and money_pattern.fullmatch(str(word[4]))
        ]

    balance_cells = money_cells(balance_x)
    used_balance_cells: set[int] = set()
    reconstructed: list[str] = []
    for index, date_word in enumerate(date_words):
        anchor_y = (float(date_word[1]) + float(date_word[3])) / 2
        previous_y = (
            (float(date_words[index - 1][1]) + float(date_words[index - 1][3])) / 2
            if index > 0
            else anchor_y - 80
        )
        next_y = (
            (float(date_words[index + 1][1]) + float(date_words[index + 1][3])) / 2
            if index + 1 < len(date_words)
            else anchor_y + 80
        )
        top = max((previous_y + anchor_y) / 2, anchor_y - 32)
        bottom = min((anchor_y + next_y) / 2, anchor_y + 32)
        row_words = [
            word
            for word in words
            if top <= (float(word[1]) + float(word[3])) / 2 < bottom
            and word is not date_word
        ]

        def column_text(start: float, end: float | None = None) -> str:
            selected = [
                word
                for word in row_words
                if float(word[0]) >= start and (end is None or float(word[0]) < end)
            ]
            selected.sort(key=lambda word: (round(float(word[1]) / 3), float(word[0])))
            return " ".join(str(word[4]) for word in selected).strip()

        narration = column_text(particulars_x, deposits_x)
        available_balances = [
            word for word in balance_cells if id(word) not in used_balance_cells
        ]
        if not available_balances:
            continue
        balance_word = min(
            available_balances,
            key=lambda word: abs(((float(word[1]) + float(word[3])) / 2) - anchor_y),
        )
        used_balance_cells.add(id(balance_word))
        balance_y = (float(balance_word[1]) + float(balance_word[3])) / 2

        def nearest_amount(start: float, end: float) -> str:
            candidates = money_cells(start, end)
            if not candidates:
                return ""
            nearest = min(
                candidates,
                key=lambda word: abs(((float(word[1]) + float(word[3])) / 2) - balance_y),
            )
            distance = abs(((float(nearest[1]) + float(nearest[3])) / 2) - balance_y)
            return str(nearest[4]) if distance <= 14 else ""

        deposit = nearest_amount(deposits_x, withdrawals_x)
        withdrawal = nearest_amount(withdrawals_x, balance_x)
        balance = str(balance_word[4])
        if not narration or not balance:
            continue
        if deposit and re.search(r"\d", deposit):
            reconstructed.append(f"{date_word[4]} {narration} {deposit} CR {balance}")
        elif withdrawal and re.search(r"\d", withdrawal):
            reconstructed.append(f"{date_word[4]} {narration} {withdrawal} DR {balance}")
        elif _is_brought_forward(narration):
            reconstructed.append(f"{date_word[4]} {narration} 0.00 CR {balance}")
    return "\n".join(reconstructed)
