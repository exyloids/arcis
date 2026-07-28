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
from uuid import UUID, uuid4

import fitz
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from arcis_backend.ledger import LedgerError
from arcis_backend.storage import MinioArtifactStorage

PARSER_VERSION = "2026-07-28"


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
            return [dict(row) for row in session.execute(text("""SELECT id, mailbox_id, provider_message_id,
                byte_size, created_at FROM source_artifacts WHERE user_id = :user_id AND kind = 'gmail_attachment'
                AND lifecycle_state = 'active' ORDER BY created_at DESC"""), {"user_id": self.user_id}).mappings()]

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
        positioned_text = "\n".join(_positioned_lines(page) for page in pages)
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
    parser = "icici_credit_card_pdf" if is_credit_card and "icici" in lowered else "icici_bank_pdf" if "icici" in lowered else "hdfc_bank_pdf" if "hdfc" in lowered else "generic_pdf"
    rows = _parse_rows(document_text, is_credit_card=is_credit_card)
    for positioned_row in _parse_rows(positioned_text, is_credit_card=is_credit_card):
        key = (positioned_row["transaction_date"], positioned_row["narration"], positioned_row["amount"], positioned_row["direction"])
        if not any((row["transaction_date"], row["narration"], row["amount"], row["direction"]) == key for row in rows):
            rows.append(positioned_row)
    if not rows:
        raise LedgerError("Supported PDF statement format was detected but no transaction rows could be extracted")
    return ParsedStatement(parser, _metadata(document_text), tuple(rows))


def _parse_rows(value: str, *, is_credit_card: bool) -> list[dict[str, object]]:
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
            rows.append({"transaction_date": transaction_date, "posted_date": None, "narration": narration,
                         "amount": amount, "currency": "INR", "direction": direction,
                         "provider_reference": None, "raw_columns": {"line": compact}})
            break
    for fallback in _parse_columnar_rows(value, is_credit_card=is_credit_card):
        key = (fallback["transaction_date"], fallback["narration"], fallback["amount"], fallback["direction"])
        if not any((row["transaction_date"], row["narration"], row["amount"], row["direction"]) == key for row in rows):
            rows.append(fallback)
    return sorted(rows, key=lambda row: (row["transaction_date"], row["narration"], row["amount"]))


def _parse_columnar_rows(value: str, *, is_credit_card: bool) -> list[dict[str, object]]:
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
            debit_amount, credit_amount = amount_values[0], amount_values[1]
            if debit_amount == 0 and credit_amount > 0:
                amount_text, column_direction = amounts[1], "credit"
            elif credit_amount == 0 and debit_amount > 0:
                amount_text, column_direction = amounts[0], "debit"
            previous_balance = amount_values[-1]
        elif not is_credit_card and len(amounts) == 2:
            running_balance = amount_values[-1]
            if previous_balance is not None and running_balance != previous_balance:
                column_direction = "credit" if running_balance > previous_balance else "debit"
            previous_balance = running_balance
        narration = body[: money_pattern.search(body).start()].strip(" -:|")
        if len(narration) < 2 or narration.lower() in {"transaction", "description", "particulars"}:
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
    return "debit"


def _reference(body: str) -> str | None:
    match = re.search(r"\b(?:ref(?:erence)?(?:\s*(?:no|number))?\s*[:#-]?\s*)?([A-Z0-9]{10,})\b", body, re.I)
    return match.group(1) if match else None


def _metadata(value: str) -> dict[str, object]:
    return {"period_start": _find_date(value, r"(?:statement\s+period|period)\D{0,20}(\d{1,2}[/-][A-Za-z]{3}[/-]\d{2,4}|\d{2}[/-]\d{2}[/-]\d{4})"),
            "period_end": None, "opening_balance": _find_money(value, r"opening\s+balance\D{0,20}([\d,]+\.\d{2})"),
            "closing_balance": _find_money(value, r"closing\s+balance\D{0,20}([\d,]+\.\d{2})"),
            "statement_amount": _find_money(value, r"(?:total\s+amount\s+due|statement\s+amount)\D{0,20}([\d,]+\.\d{2})"),
            "minimum_due": _find_money(value, r"minimum\s+(?:amount\s+)?due\D{0,20}([\d,]+\.\d{2})"),
            "due_date": _find_date(value, r"payment\s+due\s+date\D{0,20}(\d{1,2}[/-][A-Za-z]{3}[/-]\d{2,4}|\d{2}[/-]\d{2}[/-]\d{4})"),
            "total_limit": _find_money(value, r"total\s+credit\s+limit\D{0,20}([\d,]+\.\d{2})"),
            "available_limit": _find_money(value, r"available\s+credit\s+limit\D{0,20}([\d,]+\.\d{2})")}


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
