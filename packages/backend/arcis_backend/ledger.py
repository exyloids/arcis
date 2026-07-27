"""Manual-ledger application services backed by PostgreSQL.

This is deliberately small but keeps the important boundary: uploaded rows are
staged first, then confirmation atomically creates immutable source records and
canonical transactions.
"""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import io
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID, uuid4

from openpyxl import load_workbook
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from arcis_backend.storage import MinioArtifactStorage

DEFAULT_CATEGORIES = (
    ("food_dining", "Food and Dining"),
    ("groceries", "Groceries"),
    ("shopping", "Shopping"),
    ("bills_utilities", "Bills and Utilities"),
    ("travel", "Travel"),
    ("transportation", "Transportation"),
    ("salary_income", "Salary and Income"),
    ("transfers", "Transfers"),
    ("cash_withdrawal", "Cash Withdrawal"),
    ("fees_charges", "Fees and Charges"),
    ("other", "Other"),
)


class LedgerError(ValueError):
    """A safe, user-correctable ledger operation error."""


def database_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


class LedgerService:
    def __init__(self, engine: Engine, user_id: UUID, storage: MinioArtifactStorage | None = None) -> None:
        self.engine = engine
        self.user_id = user_id
        self.storage = storage

    def initialize_user(self) -> None:
        with Session(self.engine) as session, session.begin():
            session.execute(
                text(
                    """
                    INSERT INTO users (id, email_normalized, display_name)
                    VALUES (:id, :email, 'Local Arcis User')
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {"id": self.user_id, "email": f"local-{self.user_id}@arcis.invalid"},
            )
            for code, name in DEFAULT_CATEGORIES:
                session.execute(
                    text(
                        """
                        INSERT INTO categories (id, user_id, code, name, is_system)
                        VALUES (:id, :user_id, :code, :name, true)
                        ON CONFLICT (user_id, code) DO NOTHING
                        """
                    ),
                    {"id": uuid4(), "user_id": self.user_id, "code": code, "name": name},
                )

    def list_accounts(self) -> list[dict[str, object]]:
        return self._rows(
            """
            SELECT id, account_type, institution_code, product_name, display_name,
                   masked_identifier, currency, status, version
            FROM financial_accounts WHERE user_id = :user_id AND status = 'active'
            ORDER BY display_name
            """
        )

    def create_account(self, payload: dict[str, object]) -> dict[str, object]:
        account_id = uuid4()
        account_type = _required_choice(payload, "account_type", {"bank_account", "credit_card"})
        display_name = _required_text(payload, "display_name")
        with Session(self.engine) as session, session.begin():
            session.execute(
                text(
                    """
                    INSERT INTO financial_accounts
                    (id, user_id, account_type, institution_code, product_name, display_name,
                     masked_identifier, currency)
                    VALUES (:id, :user_id, :account_type, :institution_code, :product_name,
                            :display_name, :masked_identifier, :currency)
                    """
                ),
                {
                    "id": account_id,
                    "user_id": self.user_id,
                    "account_type": account_type,
                    "institution_code": _required_text(payload, "institution_code").lower(),
                    "product_name": _required_text(payload, "product_name"),
                    "display_name": display_name,
                    "masked_identifier": _optional_text(payload, "masked_identifier"),
                    "currency": _optional_text(payload, "currency") or "INR",
                },
            )
        return self._one("SELECT * FROM financial_accounts WHERE id = :id", {"id": account_id})

    def list_categories(self) -> list[dict[str, object]]:
        return self._rows(
            "SELECT id, code, name, is_system, version FROM categories "
            "WHERE user_id = :user_id AND archived_at IS NULL ORDER BY name"
        )

    def create_category(self, payload: dict[str, object]) -> dict[str, object]:
        category_id = uuid4()
        with Session(self.engine) as session, session.begin():
            session.execute(
                text(
                    "INSERT INTO categories (id, user_id, code, name) VALUES (:id, :user_id, :code, :name)"
                ),
                {
                    "id": category_id,
                    "user_id": self.user_id,
                    "code": _required_text(payload, "code").lower().replace(" ", "_"),
                    "name": _required_text(payload, "name"),
                },
            )
        return self._one("SELECT * FROM categories WHERE id = :id", {"id": category_id})

    def stage_import(
        self, account_id: UUID, filename: str, content: bytes, column_mapping: dict[str, str] | None = None
    ) -> dict[str, object]:
        self._require_account(account_id)
        rows, row_errors = _parse_tabular_upload_with_issues(filename, content, column_mapping)
        if not rows and not row_errors:
            raise LedgerError("The uploaded statement has no transaction rows")
        import_id = uuid4()
        content_hash = hashlib.sha256(content).hexdigest()
        with Session(self.engine) as session:
            existing_import_id = session.execute(
                text(
                    """SELECT id FROM imports WHERE user_id = :user_id
                    AND financial_account_id = :account_id AND content_sha256 = :content_sha256"""
                ),
                {"user_id": self.user_id, "account_id": account_id, "content_sha256": content_hash},
            ).scalar_one_or_none()
        if existing_import_id is not None:
            return self.import_preview(existing_import_id)
        stored = None
        if self.storage is not None:
            stored = self.storage.put(self.user_id, import_id, _safe_filename(filename), content)
        with Session(self.engine) as session, session.begin():
            session.execute(
                text(
                    """
                    INSERT INTO imports (id, user_id, financial_account_id, filename, content_sha256, state,
                                         row_count, valid_row_count, invalid_row_count, error_code, object_key,
                                         detected_mime_type, byte_size)
                    VALUES (:id, :user_id, :account_id, :filename, :content_sha256, :state, :row_count,
                            :valid_row_count, :invalid_row_count, :error_code, :object_key,
                            :detected_mime_type, :byte_size)
                    """
                ),
                {
                    "id": import_id,
                    "user_id": self.user_id,
                    "account_id": account_id,
                    "filename": _safe_filename(filename),
                    "content_sha256": content_hash,
                    "state": "preview_ready" if rows else "failed",
                    "row_count": len(rows) + len(row_errors),
                    "valid_row_count": len(rows),
                    "invalid_row_count": len(row_errors),
                    "error_code": "row_validation_failed" if row_errors else None,
                    "object_key": stored.object_key if stored else None,
                    "detected_mime_type": stored.content_type if stored else None,
                    "byte_size": stored.byte_size if stored else len(content),
                },
            )
            for ordinal, row in enumerate(rows, start=1):
                session.execute(
                    text(
                        """
                        INSERT INTO import_rows
                        (id, import_id, ordinal, transaction_date, posted_date, narration, amount, currency,
                         direction, provider_reference, raw_columns)
                        VALUES (:id, :import_id, :ordinal, :transaction_date, :posted_date, :narration,
                                :amount, :currency, :direction, :provider_reference, CAST(:raw_columns AS jsonb))
                        """
                    ),
                    {"id": uuid4(), "import_id": import_id, "ordinal": ordinal, **row},
                )
            for error in row_errors:
                session.execute(
                    text(
                        """INSERT INTO import_row_errors (id, import_id, ordinal, message)
                        VALUES (:id, :import_id, :ordinal, :message)"""
                    ),
                    {"id": uuid4(), "import_id": import_id, **error},
                )
        return self.import_preview(import_id)

    def import_preview(self, import_id: UUID) -> dict[str, object]:
        import_row = self._one(
            "SELECT id, financial_account_id, filename, state, row_count, valid_row_count, invalid_row_count, "
            "created_at FROM imports "
            "WHERE id = :id AND user_id = :user_id",
            {"id": import_id, "user_id": self.user_id},
        )
        rows = self._rows(
            "SELECT ordinal, transaction_date, posted_date, narration, amount, currency, direction, "
            "provider_reference FROM import_rows WHERE import_id = :id ORDER BY ordinal",
            {"id": import_id},
        )
        errors = self._rows(
            "SELECT ordinal, message FROM import_row_errors WHERE import_id = :id ORDER BY ordinal",
            {"id": import_id},
        )
        return {"import": import_row, "rows": rows, "errors": errors}

    def list_imports(self) -> list[dict[str, object]]:
        return self._rows(
            """SELECT id, financial_account_id, filename, state, row_count, valid_row_count, invalid_row_count,
            duplicate_count,
            confirmed_at, created_at FROM imports WHERE user_id = :user_id ORDER BY created_at DESC"""
        )

    def cancel_import(self, import_id: UUID) -> None:
        with Session(self.engine) as session, session.begin():
            imported = session.execute(
                text("SELECT state, object_key FROM imports WHERE id = :id AND user_id = :user_id FOR UPDATE"),
                {"id": import_id, "user_id": self.user_id},
            ).mappings().one_or_none()
            if imported is None:
                raise LedgerError("Import was not found")
            if imported["state"] == "confirmed":
                raise LedgerError("Confirmed imports cannot be cancelled")
            session.execute(
                text("UPDATE imports SET state = 'cancelled', cancelled_at = now() WHERE id = :id"),
                {"id": import_id},
            )
        if imported["object_key"] and self.storage is not None:
            self.storage.delete(imported["object_key"])

    def confirm_import(self, import_id: UUID) -> dict[str, int]:
        with Session(self.engine) as session, session.begin():
            imported = session.execute(
                text(
                    "SELECT * FROM imports WHERE id = :id AND user_id = :user_id FOR UPDATE"
                ),
                {"id": import_id, "user_id": self.user_id},
            ).mappings().one_or_none()
            if imported is None:
                raise LedgerError("Import was not found")
            if imported["state"] == "confirmed":
                return {"created": 0, "duplicates": imported["duplicate_count"], "confirmed": 1}
            if imported["state"] != "preview_ready":
                raise LedgerError(f"Import cannot be confirmed from state {imported['state']}")
            artifact_id = uuid4()
            session.execute(
                text(
                    """
                    INSERT INTO source_artifacts (id, user_id, kind, content_sha256, detected_mime_type,
                                                  lifecycle_state, import_id, object_key, byte_size)
                    VALUES (:id, :user_id, 'manual_upload', :content_sha256, 'text/tabular', 'active', :import_id,
                            :object_key, :byte_size)
                    ON CONFLICT (user_id, kind, content_sha256) DO NOTHING
                    """
                ),
                {"id": artifact_id, "user_id": self.user_id, "content_sha256": imported["content_sha256"], "import_id": import_id, "object_key": imported["object_key"], "byte_size": imported["byte_size"]},
            )
            artifact = session.execute(
                text("SELECT id FROM source_artifacts WHERE user_id = :user_id AND kind = 'manual_upload' "
                     "AND content_sha256 = :content_sha256"),
                {"user_id": self.user_id, "content_sha256": imported["content_sha256"]},
            ).scalar_one()
            created = duplicates = 0
            for row in session.execute(
                text("SELECT * FROM import_rows WHERE import_id = :id ORDER BY ordinal"), {"id": import_id}
            ).mappings():
                source_id = uuid4()
                source_key = f"{import_id}:{row['ordinal']}"
                source_insert = session.execute(
                    text(
                        """
                        INSERT INTO source_records (id, user_id, artifact_id, source_record_key, transaction_date,
                                                    posted_date, narration, amount, currency, direction, provider_reference)
                        VALUES (:id, :user_id, :artifact_id, :source_record_key, :transaction_date, :posted_date,
                                :narration, :amount, :currency, :direction, :provider_reference)
                        ON CONFLICT (artifact_id, source_record_key) DO NOTHING
                        """
                    ),
                    {"id": source_id, "user_id": self.user_id, "artifact_id": artifact, "source_record_key": source_key,
                     "transaction_date": row["transaction_date"], "posted_date": row["posted_date"],
                     "narration": row["narration"], "amount": row["amount"], "currency": row["currency"],
                     "direction": row["direction"], "provider_reference": row["provider_reference"]},
                )
                if source_insert.rowcount == 0:
                    duplicates += 1
                    continue
                duplicate = session.execute(
                    text(
                        """SELECT id FROM transactions WHERE user_id = :user_id AND financial_account_id = :account_id
                        AND transaction_date = :transaction_date AND amount = :amount AND direction = :direction
                        AND COALESCE(provider_reference, '') = COALESCE(:provider_reference, '') LIMIT 1"""
                    ),
                    {"user_id": self.user_id, "account_id": imported["financial_account_id"],
                     "transaction_date": row["transaction_date"], "amount": row["amount"], "direction": row["direction"],
                     "provider_reference": row["provider_reference"]},
                ).scalar_one_or_none()
                if duplicate is not None:
                    duplicates += 1
                    continue
                kind = _transaction_kind(row["narration"])
                transaction_id = uuid4()
                session.execute(
                    text(
                        """INSERT INTO transactions (id, user_id, financial_account_id, transaction_date, posted_date,
                                                     narration, amount, currency, direction, transaction_kind,
                                                     reconciliation_state, source_record_id)
                        VALUES (:id, :user_id, :account_id, :transaction_date, :posted_date, :narration, :amount,
                                :currency, :direction, :transaction_kind, 'statement_confirmed', :source_record_id)"""
                    ),
                    {"id": transaction_id, "user_id": self.user_id, "account_id": imported["financial_account_id"],
                     "transaction_date": row["transaction_date"], "posted_date": row["posted_date"],
                     "narration": row["narration"], "amount": row["amount"], "currency": row["currency"],
                     "direction": row["direction"], "transaction_kind": kind, "source_record_id": source_id},
                )
                session.execute(
                    text("INSERT INTO transaction_evidence (transaction_id, source_record_id, relationship, match_method) "
                         "VALUES (:transaction_id, :source_record_id, 'primary', 'import_confirmation')"),
                    {"transaction_id": transaction_id, "source_record_id": source_id},
                )
                created += 1
            session.execute(
                text("UPDATE imports SET state = 'confirmed', confirmed_at = now(), duplicate_count = :duplicates "
                     "WHERE id = :id"), {"duplicates": duplicates, "id": import_id}
            )
        return {"created": created, "duplicates": duplicates, "confirmed": 1}

    def list_transactions(
        self,
        *,
        month: str | None = None,
        account_id: UUID | None = None,
        category_id: UUID | None = None,
        query_text: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        query = """
            SELECT t.id, t.financial_account_id, a.display_name AS account_name, t.transaction_date,
                   t.posted_date, t.narration, t.amount, t.currency, t.direction, t.transaction_kind,
                   t.reconciliation_state, t.category_id, c.name AS category
            FROM transactions t JOIN financial_accounts a ON a.id = t.financial_account_id
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.user_id = :user_id
        """
        parameters: dict[str, object] = {"user_id": self.user_id}
        if month:
            query += " AND to_char(t.transaction_date, 'YYYY-MM') = :month"
            parameters["month"] = month
        if account_id:
            query += " AND t.financial_account_id = :account_id"
            parameters["account_id"] = account_id
        if category_id:
            query += " AND t.category_id = :category_id"
            parameters["category_id"] = category_id
        if query_text:
            query += " AND t.narration ILIKE :query_text"
            parameters["query_text"] = f"%{query_text.strip()}%"
        parameters["limit"] = min(max(limit, 1), 200)
        return self._rows(query + " ORDER BY t.transaction_date DESC, t.created_at DESC LIMIT :limit", parameters)

    def transaction_page(
        self,
        *,
        month: str | None = None,
        account_id: UUID | None = None,
        category_id: UUID | None = None,
        query_text: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, object]:
        query = """
            SELECT t.id, t.financial_account_id, a.display_name AS account_name, t.transaction_date,
                   t.posted_date, t.narration, t.amount, t.currency, t.direction, t.transaction_kind,
                   t.reconciliation_state, t.category_id, c.name AS category
            FROM transactions t JOIN financial_accounts a ON a.id = t.financial_account_id
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.user_id = :user_id
        """
        parameters: dict[str, object] = {"user_id": self.user_id}
        if month:
            query += " AND to_char(t.transaction_date, 'YYYY-MM') = :month"
            parameters["month"] = month
        if account_id:
            query += " AND t.financial_account_id = :account_id"
            parameters["account_id"] = account_id
        if category_id:
            query += " AND t.category_id = :category_id"
            parameters["category_id"] = category_id
        if query_text:
            query += " AND t.narration ILIKE :query_text"
            parameters["query_text"] = f"%{query_text.strip()}%"
        if cursor:
            cursor_date, cursor_id = _decode_transaction_cursor(cursor)
            query += " AND (t.transaction_date, t.id) < (:cursor_date, :cursor_id)"
            parameters.update({"cursor_date": cursor_date, "cursor_id": cursor_id})
        requested_limit = min(max(limit, 1), 200)
        parameters["limit"] = requested_limit + 1
        rows = self._rows(query + " ORDER BY t.transaction_date DESC, t.id DESC LIMIT :limit", parameters)
        has_more = len(rows) > requested_limit
        items = rows[:requested_limit]
        next_cursor = None
        if has_more and items:
            next_cursor = _encode_transaction_cursor(items[-1]["transaction_date"], items[-1]["id"])
        return {"items": items, "next_cursor": next_cursor}

    def transaction_evidence(self, transaction_id: UUID) -> list[dict[str, object]]:
        return self._rows(
            """SELECT sr.id AS source_record_id, sr.source_record_key, sr.transaction_date, sr.narration,
            sr.amount, sr.currency, sr.direction, sr.provider_reference, sa.kind AS artifact_kind,
            i.id AS import_id, i.filename AS import_filename
            FROM transaction_evidence te JOIN source_records sr ON sr.id = te.source_record_id
            JOIN source_artifacts sa ON sa.id = sr.artifact_id
            LEFT JOIN imports i ON i.id = sa.import_id
            WHERE te.transaction_id = :transaction_id AND sr.user_id = :user_id""",
            {"transaction_id": transaction_id, "user_id": self.user_id},
        )

    def update_transaction(self, transaction_id: UUID, payload: dict[str, object]) -> dict[str, object]:
        fields: list[str] = []
        parameters: dict[str, object] = {"id": transaction_id, "user_id": self.user_id}
        for field in ("narration", "transaction_kind"):
            if field in payload:
                fields.append(f"{field} = :{field}")
                parameters[field] = _required_text(payload, field)
        if "category_id" in payload:
            fields.append("category_id = :category_id")
            parameters["category_id"] = UUID(str(payload["category_id"])) if payload["category_id"] else None
        if not fields:
            raise LedgerError("No mutable transaction fields were supplied")
        fields.append("version = version + 1")
        fields.append("updated_at = now()")
        with Session(self.engine) as session, session.begin():
            result = session.execute(
                text("UPDATE transactions SET " + ", ".join(fields) + " WHERE id = :id AND user_id = :user_id"),
                parameters,
            )
            if result.rowcount != 1:
                raise LedgerError("Transaction was not found")
        return self._one("SELECT * FROM transactions WHERE id = :id", {"id": transaction_id})

    def monthly_report(self, month: str) -> dict[str, object]:
        rows = self._rows(
            """SELECT COALESCE(c.name, 'Uncategorized') AS category, t.direction, SUM(t.amount) AS amount
            FROM transactions t LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.user_id = :user_id AND to_char(t.transaction_date, 'YYYY-MM') = :month
              AND t.transaction_kind NOT IN ('transfer', 'credit_card_payment')
            GROUP BY c.name, t.direction ORDER BY amount DESC""",
            {"user_id": self.user_id, "month": month},
        )
        totals = {"income": Decimal("0"), "expense": Decimal("0")}
        for row in rows:
            totals["expense" if row["direction"] == "debit" else "income"] += row["amount"]
        return {"month": month, "income": totals["income"], "expense": totals["expense"], "categories": rows}

    def _require_account(self, account_id: UUID) -> None:
        self._one("SELECT id FROM financial_accounts WHERE id = :id AND user_id = :user_id AND status = 'active'", {"id": account_id, "user_id": self.user_id})

    def _rows(self, query: str, parameters: dict[str, object] | None = None) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            return [dict(row) for row in session.execute(text(query), parameters or {"user_id": self.user_id}).mappings()]

    def _one(self, query: str, parameters: dict[str, object]) -> dict[str, object]:
        with Session(self.engine) as session:
            row = session.execute(text(query), parameters).mappings().one_or_none()
            if row is None:
                raise LedgerError("Requested resource was not found")
            return dict(row)


def _parse_tabular_upload(filename: str, content: bytes) -> list[dict[str, object]]:
    return _parse_tabular_upload_with_mapping(filename, content, None)


def inspect_tabular_upload(filename: str, content: bytes) -> dict[str, object]:
    records = _tabular_records(filename, content)
    headers = list(records[0]) if records else []
    normalized_headers = {header.strip().lower(): header for header in headers}
    suggestions = {
        field: normalized_headers[candidate]
        for field, candidates in _MAPPING_CANDIDATES.items()
        for candidate in candidates
        if candidate in normalized_headers
    }
    return {"headers": headers, "suggested_mapping": suggestions, "sample_row_count": len(records)}


_MAPPING_CANDIDATES = {
    "transaction_date": ("transaction date", "date", "txn date"),
    "posted_date": ("value date", "value dt", "posted date"),
    "narration": ("transaction remarks", "narration", "description", "particulars"),
    "provider_reference": ("reference no.", "ref no", "chq./ref.no.", "utr"),
    "debit": ("withdrawal amount", "withdrawal amt.", "debit"),
    "credit": ("deposit amount", "deposit amt.", "credit"),
}


def _parse_tabular_upload_with_mapping(
    filename: str, content: bytes, column_mapping: dict[str, str] | None
) -> list[dict[str, object]]:
    normalized_rows, errors = _parse_tabular_upload_with_issues(filename, content, column_mapping)
    if errors:
        messages = [f"row {error['ordinal']}: {error['message']}" for error in errors]
        raise LedgerError("Statement validation failed — " + "; ".join(messages[:10]))
    return normalized_rows


def _parse_tabular_upload_with_issues(
    filename: str, content: bytes, column_mapping: dict[str, str] | None
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    records = _tabular_records(filename, content)
    if column_mapping:
        required = {"transaction_date", "narration", "debit", "credit"}
        missing = required - set(column_mapping)
        if missing:
            raise LedgerError(f"Column mapping is missing: {', '.join(sorted(missing))}")
        records = [_apply_column_mapping(record, column_mapping) for record in records]
    normalized_rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    for ordinal, record in enumerate(records, start=2):
        try:
            normalized_rows.append(_normalize_row(record))
        except LedgerError as error:
            errors.append({"ordinal": ordinal, "message": str(error)})
    return normalized_rows, errors


def _tabular_records(filename: str, content: bytes) -> list[dict[str, object]]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        if b"\x00" in content:
            raise LedgerError("CSV contains unsupported binary data")
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise LedgerError("CSV must be UTF-8 encoded") from error
        return list(csv.DictReader(io.StringIO(decoded)))
    elif suffix == ".xlsx":
        if not content.startswith(b"PK"):
            raise LedgerError("XLSX file signature is invalid")
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        if len(workbook.sheetnames) > 10:
            raise LedgerError("XLSX workbook has too many sheets")
        worksheet = workbook.active
        values = list(worksheet.iter_rows(values_only=True))
        if len(values) > 100_001:
            raise LedgerError("XLSX worksheet has too many rows")
        if not values:
            return []
        headers = [str(value or "").strip() for value in values[0]]
        return [dict(zip(headers, row, strict=True)) for row in values[1:] if any(row)]
    else:
        raise LedgerError("Only CSV and XLSX statement imports are supported")


def _apply_column_mapping(record: dict[str, object], mapping: dict[str, str]) -> dict[str, object]:
    available = {str(key): value for key, value in record.items()}
    missing = [header for header in mapping.values() if header not in available]
    if missing:
        raise LedgerError(f"Mapped statement columns were not found: {', '.join(sorted(missing))}")
    return {
        "Transaction Date": available[mapping["transaction_date"]],
        "Value Date": available[mapping["posted_date"]] if mapping.get("posted_date") else None,
        "Transaction Remarks": available[mapping["narration"]],
        "Withdrawal Amount": available[mapping["debit"]],
        "Deposit Amount": available[mapping["credit"]],
        "Reference No.": available[mapping["provider_reference"]] if mapping.get("provider_reference") else None,
    }


def _normalize_row(raw: dict[str, object]) -> dict[str, object]:
    normalized = {str(key).strip().lower(): value for key, value in raw.items()}
    date_value = _first(normalized, "transaction date", "date", "txn date")
    narration = _first(normalized, "transaction remarks", "narration", "description", "particulars")
    reference = _first(normalized, "reference no.", "ref no", "chq./ref.no.", "utr")
    withdrawal = _money(_first(normalized, "withdrawal amount", "withdrawal amt.", "debit"))
    deposit = _money(_first(normalized, "deposit amount", "deposit amt.", "credit"))
    if (withdrawal is None) == (deposit is None):
        raise LedgerError("Each row must contain exactly one debit or credit amount")
    return {
        "transaction_date": _date(date_value),
        "posted_date": _date(_first(normalized, "value date", "value dt", "posted date"), optional=True),
        "narration": _text(narration, "narration"),
        "amount": withdrawal or deposit,
        "currency": "INR",
        "direction": "debit" if withdrawal is not None else "credit",
        "provider_reference": str(reference).strip() if reference not in (None, "") else None,
        "raw_columns": json.dumps({key: str(value) for key, value in raw.items()}, sort_keys=True),
    }


def _first(values: dict[str, object], *names: str) -> object | None:
    return next((values[name] for name in names if values.get(name) not in (None, "")), None)


def _money(value: object | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        amount = Decimal(str(value).replace(",", "").replace("₹", "").strip())
    except InvalidOperation as exc:
        raise LedgerError("A statement amount is invalid") from exc
    if amount <= 0:
        raise LedgerError("A statement amount must be positive")
    return amount


def _date(value: object | None, *, optional: bool = False) -> date | None:
    if value in (None, "") and optional:
        return None
    if isinstance(value, date):
        return value
    for pattern in ("%d/%m/%Y", "%d-%b-%Y", "%Y-%m-%d"):
        try:
            from datetime import datetime
            return datetime.strptime(str(value), pattern).date()
        except ValueError:
            continue
    raise LedgerError("A statement date is invalid")


def _transaction_kind(narration: str) -> str:
    upper = narration.upper()
    if any(marker in upper for marker in ("SALARY", "INTEREST", "DIVIDEND")):
        return "income"
    if any(marker in upper for marker in ("CARD PAYMENT", "CC PAYMENT", "CREDIT CARD PAYMENT")):
        return "credit_card_payment"
    if any(marker in upper for marker in ("NEFT", "IMPS", "RTGS", "TRANSFER")):
        return "transfer"
    return "unknown"


def _required_text(payload: dict[str, object], key: str) -> str:
    return _text(payload.get(key), key)


def _optional_text(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    return str(value).strip() if value not in (None, "") else None


def _text(value: object | None, field: str) -> str:
    if value is None or not str(value).strip():
        raise LedgerError(f"{field} is required")
    return str(value).strip()


def _required_choice(payload: dict[str, object], key: str, allowed: set[str]) -> str:
    value = _required_text(payload, key)
    if value not in allowed:
        raise LedgerError(f"{key} is invalid")
    return value


def _safe_filename(value: str) -> str:
    return Path(value).name[:255]


def _encode_transaction_cursor(transaction_date: object, transaction_id: object) -> str:
    value = f"{transaction_date}|{transaction_id}".encode("ascii")
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_transaction_cursor(cursor: str) -> tuple[date, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
        date_value, id_value = value.split("|", maxsplit=1)
        return date.fromisoformat(date_value), UUID(id_value)
    except (ValueError, UnicodeDecodeError, binascii.Error) as error:
        raise LedgerError("Transaction cursor is invalid") from error
