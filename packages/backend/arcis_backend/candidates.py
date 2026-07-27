"""Parse Gmail evidence into reviewable, account-resolved candidates."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from arcis_backend.parsers import parse_supported_alert


class CandidateService:
    def __init__(self, engine: Engine, user_id: UUID) -> None:
        self.engine, self.user_id = engine, user_id

    def create_from_artifact(self, artifact_id: UUID, raw_message: bytes) -> dict[str, object]:
        try:
            normalized = parse_supported_alert(raw_message)
        except Exception as error:  # Untrusted provider email must never abort a mailbox batch.
            normalized, parser_name, account, state, reason = {}, "unsupported", None, "unsupported", str(error)
        else:
            parser_name = "icici" if b"icicibank.com" in raw_message.lower() else "hdfc"
            account = self._account_for_hint(str(normalized["financial_account_hint"]))
            state = "ready" if account else "needs_review"
            reason = None if account else "No active Arcis account matched the email account hint"
        with Session(self.engine) as session, session.begin():
            # Upgrade a prior unsupported candidate when parser support is
            # added, while preserving a user-rejected item as an audit trail.
            candidate_id = session.execute(
                text("""UPDATE parser_candidates SET financial_account_id = :account_id, parser_name = :parser_name,
                state = :state, review_reason = :reason, normalized = CAST(:normalized AS jsonb), updated_at = now()
                WHERE artifact_id = :artifact_id AND parser_name = 'unsupported' AND state IN ('unsupported', 'needs_review')
                RETURNING id"""),
                {"artifact_id": artifact_id, "account_id": account, "parser_name": parser_name,
                 "state": state, "reason": reason, "normalized": json.dumps(normalized)},
            ).scalar_one_or_none()
            if candidate_id is None:
                candidate_id = session.execute(
                text("""INSERT INTO parser_candidates (id, user_id, artifact_id, financial_account_id, parser_name, state, review_reason, normalized)
                VALUES (:id, :user_id, :artifact_id, :account_id, :parser_name, :state, :reason, CAST(:normalized AS jsonb))
                ON CONFLICT (artifact_id, parser_name) DO UPDATE SET financial_account_id = EXCLUDED.financial_account_id,
                state = EXCLUDED.state, review_reason = EXCLUDED.review_reason, normalized = EXCLUDED.normalized,
                updated_at = now() WHERE parser_candidates.state IN ('unsupported', 'needs_review') RETURNING id"""),
                {"id": uuid4(), "user_id": self.user_id, "artifact_id": artifact_id, "account_id": account,
                 "parser_name": parser_name, "state": state, "reason": reason, "normalized": json.dumps(normalized)},
                ).scalar_one_or_none()
        if candidate_id is None:
            with Session(self.engine) as session:
                candidate_id = session.execute(
                    text("SELECT id FROM parser_candidates WHERE artifact_id = :artifact_id AND parser_name = :parser_name"),
                    {"artifact_id": artifact_id, "parser_name": parser_name},
                ).scalar_one()
        return self.get(candidate_id)

    def list(self, state: str | None = None) -> list[dict[str, object]]:
        query = "SELECT * FROM parser_candidates WHERE user_id = :user_id"
        params: dict[str, object] = {"user_id": self.user_id}
        if state:
            query += " AND state = :state"
            params["state"] = state
        with Session(self.engine) as session:
            return [dict(row) for row in session.execute(text(query + " ORDER BY created_at DESC"), params).mappings()]

    def metrics(self) -> list[dict[str, object]]:
        with Session(self.engine) as session:
            return [dict(row) for row in session.execute(text("SELECT parser_name, state, COUNT(*) AS count FROM parser_candidates WHERE user_id = :user_id GROUP BY parser_name, state ORDER BY parser_name, state"), {"user_id": self.user_id}).mappings()]

    def get(self, candidate_id: UUID) -> dict[str, object]:
        with Session(self.engine) as session:
            row = session.execute(text("SELECT * FROM parser_candidates WHERE id = :id AND user_id = :user_id"), {"id": candidate_id, "user_id": self.user_id}).mappings().one()
        return dict(row)

    def assign_account(self, candidate_id: UUID, account_id: UUID) -> dict[str, object]:
        with Session(self.engine) as session, session.begin():
            candidate = session.execute(
                text("SELECT normalized, state FROM parser_candidates WHERE id = :id AND user_id = :user_id FOR UPDATE"),
                {"id": candidate_id, "user_id": self.user_id},
            ).mappings().one_or_none()
            if candidate is None or candidate["state"] not in {"ready", "needs_review"}:
                raise ValueError("Candidate is not available for account assignment")
            normalized = candidate["normalized"]
            hint = normalized.get("financial_account_hint") if isinstance(normalized, dict) else None
            expected_type = "credit_card" if isinstance(hint, str) and hint.startswith("credit_card_") else "bank_account"
            account = session.execute(
                text("""SELECT id FROM financial_accounts WHERE id = :id AND user_id = :user_id
                AND status = 'active' AND account_type = :account_type"""),
                {"id": account_id, "user_id": self.user_id, "account_type": expected_type},
            ).scalar_one_or_none()
            if account is None:
                raise ValueError(f"Select an active {expected_type.replace('_', ' ')}")
            session.execute(
                text("""UPDATE parser_candidates SET financial_account_id = :account_id, state = 'ready',
                review_reason = NULL, updated_at = now() WHERE id = :id AND user_id = :user_id"""),
                {"id": candidate_id, "account_id": account_id, "user_id": self.user_id},
            )
        return self.get(candidate_id)

    def review(self, candidate_id: UUID, state: str) -> dict[str, object]:
        if state not in {"accepted", "rejected"}:
            raise ValueError("Candidate review state is invalid")
        with Session(self.engine) as session, session.begin():
            if state == "accepted":
                candidate = session.execute(text("SELECT * FROM parser_candidates WHERE id = :id AND user_id = :user_id FOR UPDATE"), {"id": candidate_id, "user_id": self.user_id}).mappings().one_or_none()
                if candidate is None or candidate["state"] != "ready" or candidate["financial_account_id"] is None:
                    raise ValueError("Assign an account before accepting this candidate")
                normalized = candidate["normalized"]
                source_id, transaction_id = uuid4(), uuid4()
                session.execute(text("""INSERT INTO source_records (id, user_id, artifact_id, source_record_key, transaction_date, narration, amount, currency, direction, provider_reference)
                    VALUES (:id, :user_id, :artifact_id, :source_key, :transaction_date, :narration, :amount, :currency, :direction, :reference)
                    ON CONFLICT (artifact_id, source_record_key) DO NOTHING"""),
                    {"id": source_id, "user_id": self.user_id, "artifact_id": candidate["artifact_id"], "source_key": str(candidate_id),
                     "transaction_date": normalized["transaction_date"], "narration": normalized["merchant"], "amount": normalized["amount"], "currency": normalized["currency"], "direction": normalized["direction"], "reference": normalized["provider_reference"]})
                source_id = session.execute(text("SELECT id FROM source_records WHERE artifact_id = :artifact_id AND source_record_key = :source_key"), {"artifact_id": candidate["artifact_id"], "source_key": str(candidate_id)}).scalar_one()
                session.execute(text("""INSERT INTO transactions (id, user_id, financial_account_id, transaction_date, narration, amount, currency, direction, transaction_kind, reconciliation_state, source_record_id, provider_reference)
                    VALUES (:id, :user_id, :account_id, :transaction_date, :narration, :amount, :currency, :direction, :kind, 'email_only', :source_id, :reference)
                    ON CONFLICT DO NOTHING"""),
                    {"id": transaction_id, "user_id": self.user_id, "account_id": candidate["financial_account_id"], "transaction_date": normalized["transaction_date"], "narration": normalized["merchant"], "amount": normalized["amount"], "currency": normalized["currency"], "direction": normalized["direction"], "kind": normalized.get("transaction_kind", "unknown"), "source_id": source_id, "reference": normalized["provider_reference"]})
                transaction_id = session.execute(text("SELECT id FROM transactions WHERE source_record_id = :source_id"), {"source_id": source_id}).scalar_one()
                session.execute(text("INSERT INTO transaction_evidence (transaction_id, source_record_id, relationship, match_method) VALUES (:transaction_id, :source_id, 'primary', 'email_parser') ON CONFLICT DO NOTHING"), {"transaction_id": transaction_id, "source_id": source_id})
            result = session.execute(text("""UPDATE parser_candidates SET state = :state, updated_at = now()
                WHERE id = :id AND user_id = :user_id AND state IN ('ready', 'needs_review', 'unsupported')"""),
                {"id": candidate_id, "user_id": self.user_id, "state": state})
            if result.rowcount != 1:
                raise ValueError("Candidate was not found or has already been reviewed")
        return self.get(candidate_id)

    def _account_for_hint(self, hint: str) -> UUID | None:
        ending = hint.rsplit("_", 1)[-1]
        account_type = "credit_card" if hint.startswith("credit_card") else "bank_account"
        with Session(self.engine) as session:
            return session.execute(text("""SELECT id FROM financial_accounts WHERE user_id = :user_id AND account_type = :account_type
                AND masked_identifier LIKE :ending AND status = 'active'"""), {"user_id": self.user_id, "account_type": account_type, "ending": f"%{ending}"}).scalar_one_or_none()
