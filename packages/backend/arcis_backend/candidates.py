"""Parse Gmail evidence into reviewable, account-resolved candidates."""

from __future__ import annotations

import json
import re
from uuid import UUID, uuid4

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from arcis_backend.parsers import (
    discover_financial_product,
    institution_for_message,
    parse_supported_alert,
)


class CandidateService:
    def __init__(self, engine: Engine, user_id: UUID) -> None:
        self.engine, self.user_id = engine, user_id

    def create_from_artifact(self, artifact_id: UUID, raw_message: bytes) -> dict[str, object]:
        try:
            normalized = parse_supported_alert(raw_message)
        except Exception as error:  # Untrusted provider email must never abort a mailbox batch.
            detected_product = discover_financial_product(raw_message)
            normalized, parser_name, account, discovery_id, state, reason = (
                detected_product[1] if detected_product else {},
                "unsupported",
                None,
                None,
                "unsupported",
                str(error),
            )
            if detected_product:
                institution_code, product = detected_product
                hint = product["financial_account_hint"]
                account = self._account_for_hint(hint, institution_code)
                discovery = self._discover_account(
                    artifact_id,
                    institution_code,
                    normalized,
                    account,
                )
                discovery_id = discovery["id"]
                if discovery["state"] == "rejected":
                    state = "rejected"
                    reason = "Skipped because this account or card was declined"
        else:
            parser_name = institution_for_message(raw_message)
            if parser_name is None:
                raise ValueError("Parsed alert did not have a trusted institution sender")
            hint = str(normalized["financial_account_hint"])
            account = self._account_for_hint(hint, parser_name)
            discovery = self._discover_account(artifact_id, parser_name, normalized, account)
            discovery_id = discovery["id"]
            if discovery["state"] == "confirmed":
                account = discovery["financial_account_id"]
                state, reason = "ready", None
            elif discovery["state"] == "rejected":
                account = None
                state, reason = "rejected", "Skipped because this account or card was declined"
            else:
                account = None
                state, reason = (
                    "needs_review",
                    "Waiting for account or card confirmation",
                )
        with Session(self.engine) as session, session.begin():
            # Upgrade a prior unsupported candidate when parser support is
            # added, while preserving a user-rejected item as an audit trail.
            candidate_id = session.execute(
                text("""UPDATE parser_candidates SET financial_account_id = :account_id,
                discovered_account_id = :discovery_id, parser_name = :parser_name,
                state = :state, review_reason = :reason,
                normalized = CAST(:normalized AS jsonb), updated_at = now()
                WHERE artifact_id = :artifact_id AND parser_name = 'unsupported' AND state IN ('unsupported', 'needs_review')
                RETURNING id"""),
                {
                    "artifact_id": artifact_id,
                    "account_id": account,
                    "discovery_id": discovery_id,
                    "parser_name": parser_name,
                    "state": state,
                    "reason": reason,
                    "normalized": json.dumps(normalized),
                },
            ).scalar_one_or_none()
            if candidate_id is None:
                candidate_id = session.execute(
                text("""INSERT INTO parser_candidates
                (id, user_id, artifact_id, financial_account_id, discovered_account_id,
                 parser_name, state, review_reason, normalized)
                VALUES (:id, :user_id, :artifact_id, :account_id, :discovery_id,
                        :parser_name, :state, :reason, CAST(:normalized AS jsonb))
                ON CONFLICT (artifact_id, parser_name) DO UPDATE SET financial_account_id = EXCLUDED.financial_account_id,
                discovered_account_id = EXCLUDED.discovered_account_id,
                state = EXCLUDED.state, review_reason = EXCLUDED.review_reason,
                normalized = EXCLUDED.normalized,
                updated_at = now() WHERE parser_candidates.state IN ('unsupported', 'needs_review') RETURNING id"""),
                {
                    "id": uuid4(),
                    "user_id": self.user_id,
                    "artifact_id": artifact_id,
                    "account_id": account,
                    "discovery_id": discovery_id,
                    "parser_name": parser_name,
                    "state": state,
                    "reason": reason,
                    "normalized": json.dumps(normalized),
                },
                ).scalar_one_or_none()
        if candidate_id is None:
            with Session(self.engine) as session:
                candidate_id = session.execute(
                    text("SELECT id FROM parser_candidates WHERE artifact_id = :artifact_id AND parser_name = :parser_name"),
                    {"artifact_id": artifact_id, "parser_name": parser_name},
                ).scalar_one()
        if discovery_id is not None and state == "ready":
            candidate = self.get(candidate_id)
            if candidate["state"] == "ready":
                return self.review(candidate_id, "accepted")
        return self.get(candidate_id)

    def list(self, state: str | None = None) -> list[dict[str, object]]:
        query = "SELECT * FROM parser_candidates WHERE user_id = :user_id"
        params: dict[str, object] = {"user_id": self.user_id}
        if state:
            query += " AND state = :state"
            params["state"] = state
        else:
            query += """ AND state IN ('ready', 'needs_review', 'unsupported')
                         AND (discovered_account_id IS NULL OR state = 'unsupported')"""
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

    def list_discovered_accounts(self, state: str | None = None) -> list[dict[str, object]]:
        parameters: dict[str, object] = {"user_id": self.user_id}
        query = """SELECT d.id, d.mailbox_id, m.display_email AS mailbox_email,
                          d.fingerprint, d.institution_code, d.account_type,
                          d.masked_identifier, d.suggested_product_name,
                          d.suggested_display_name, d.currency, d.state,
                          d.financial_account_id, d.first_detected_at,
                          d.last_detected_at, d.decided_at,
                          COUNT(pc.id) AS transaction_alert_count
                   FROM discovered_financial_accounts d
                   LEFT JOIN mailboxes m ON m.id = d.mailbox_id
                   LEFT JOIN parser_candidates pc ON pc.discovered_account_id = d.id
                   WHERE d.user_id = :user_id"""
        if state:
            if state not in {"pending", "confirmed", "rejected"}:
                raise ValueError("Discovered account state is invalid")
            query += " AND d.state = :state"
            parameters["state"] = state
        query += """ GROUP BY d.id, m.display_email
                     ORDER BY CASE d.state WHEN 'pending' THEN 0 WHEN 'confirmed' THEN 1 ELSE 2 END,
                              d.last_detected_at DESC"""
        with Session(self.engine) as session:
            return [
                dict(row)
                for row in session.execute(text(query), parameters).mappings()
            ]

    def confirm_discovered_account(
        self,
        discovery_id: UUID,
        payload: dict[str, object],
    ) -> dict[str, object]:
        product_name = _required_discovery_text(payload, "product_name")
        display_name = _required_discovery_text(payload, "display_name")
        currency = str(payload.get("currency", "INR")).strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("Currency must be a three-letter ISO code")

        with Session(self.engine) as session, session.begin():
            discovery = session.execute(
                text(
                    """SELECT * FROM discovered_financial_accounts
                       WHERE id = :id AND user_id = :user_id FOR UPDATE"""
                ),
                {"id": discovery_id, "user_id": self.user_id},
            ).mappings().one_or_none()
            if discovery is None:
                raise ValueError("Discovered account or card was not found")
            if discovery["state"] == "confirmed":
                raise ValueError("This account or card has already been confirmed")

            account_id = session.execute(
                text(
                    """SELECT id FROM financial_accounts
                       WHERE user_id = :user_id
                         AND LOWER(institution_code) = :institution_code
                         AND account_type = :account_type
                         AND masked_identifier = :masked_identifier
                         AND status = 'active'
                       LIMIT 1"""
                ),
                {
                    "user_id": self.user_id,
                    "institution_code": discovery["institution_code"],
                    "account_type": discovery["account_type"],
                    "masked_identifier": discovery["masked_identifier"],
                },
            ).scalar_one_or_none()
            if account_id is None:
                account_id = uuid4()
                session.execute(
                    text(
                        """INSERT INTO financial_accounts
                           (id, user_id, account_type, institution_code,
                            product_name, display_name, masked_identifier, currency)
                           VALUES (:id, :user_id, :account_type, :institution_code,
                                   :product_name, :display_name, :masked_identifier, :currency)"""
                    ),
                    {
                        "id": account_id,
                        "user_id": self.user_id,
                        "account_type": discovery["account_type"],
                        "institution_code": discovery["institution_code"],
                        "product_name": product_name,
                        "display_name": display_name,
                        "masked_identifier": discovery["masked_identifier"],
                        "currency": currency,
                    },
                )

            session.execute(
                text(
                    """UPDATE discovered_financial_accounts
                       SET state = 'confirmed', financial_account_id = :account_id,
                           suggested_product_name = :product_name,
                           suggested_display_name = :display_name,
                           currency = :currency, decided_at = now(), updated_at = now()
                       WHERE id = :id AND user_id = :user_id"""
                ),
                {
                    "id": discovery_id,
                    "user_id": self.user_id,
                    "account_id": account_id,
                    "product_name": product_name,
                    "display_name": display_name,
                    "currency": currency,
                },
            )
            candidate_ids = session.execute(
                text(
                    """UPDATE parser_candidates
                       SET financial_account_id = :account_id, state = 'ready',
                           review_reason = NULL, updated_at = now()
                       WHERE discovered_account_id = :discovery_id
                         AND user_id = :user_id
                         AND state IN ('needs_review', 'ready', 'rejected')
                       RETURNING id"""
                ),
                {
                    "account_id": account_id,
                    "discovery_id": discovery_id,
                    "user_id": self.user_id,
                },
            ).scalars().all()

        imported = 0
        for candidate_id in candidate_ids:
            self.review(candidate_id, "accepted")
            imported += 1
        result = next(
            item for item in self.list_discovered_accounts() if item["id"] == discovery_id
        )
        return {**result, "transactions_imported": imported}

    def reject_discovered_account(self, discovery_id: UUID) -> dict[str, object]:
        with Session(self.engine) as session, session.begin():
            result = session.execute(
                text(
                    """UPDATE discovered_financial_accounts
                       SET state = 'rejected', financial_account_id = NULL,
                           decided_at = now(), updated_at = now()
                       WHERE id = :id AND user_id = :user_id AND state = 'pending'"""
                ),
                {"id": discovery_id, "user_id": self.user_id},
            )
            if result.rowcount != 1:
                raise ValueError("Only a pending account or card can be declined")
            session.execute(
                text(
                    """UPDATE parser_candidates
                       SET state = 'rejected',
                           review_reason = 'Skipped because this account or card was declined',
                           updated_at = now()
                       WHERE discovered_account_id = :discovery_id
                         AND user_id = :user_id
                         AND state IN ('needs_review', 'ready')"""
                ),
                {"discovery_id": discovery_id, "user_id": self.user_id},
            )
        return next(
            item for item in self.list_discovered_accounts() if item["id"] == discovery_id
        )

    def reconsider_discovered_account(self, discovery_id: UUID) -> dict[str, object]:
        with Session(self.engine) as session, session.begin():
            result = session.execute(
                text(
                    """UPDATE discovered_financial_accounts
                       SET state = 'pending', decided_at = NULL, updated_at = now()
                       WHERE id = :id AND user_id = :user_id AND state = 'rejected'"""
                ),
                {"id": discovery_id, "user_id": self.user_id},
            )
            if result.rowcount != 1:
                raise ValueError("Only a declined account or card can be reconsidered")
            session.execute(
                text(
                    """UPDATE parser_candidates
                       SET state = 'needs_review',
                           review_reason = 'Waiting for account or card confirmation',
                           updated_at = now()
                       WHERE discovered_account_id = :discovery_id
                         AND user_id = :user_id
                         AND state = 'rejected'"""
                ),
                {"discovery_id": discovery_id, "user_id": self.user_id},
            )
        return next(
            item for item in self.list_discovered_accounts() if item["id"] == discovery_id
        )

    def _discover_account(
        self,
        artifact_id: UUID,
        parser_name: str,
        normalized: dict[str, object],
        existing_account_id: UUID | None,
    ) -> dict[str, object]:
        identity = account_discovery_identity(parser_name, normalized)
        with Session(self.engine) as session, session.begin():
            mailbox_id = session.execute(
                text(
                    """SELECT mailbox_id FROM source_artifacts
                       WHERE id = :id AND user_id = :user_id"""
                ),
                {"id": artifact_id, "user_id": self.user_id},
            ).scalar_one_or_none()
            if mailbox_id is None:
                raise ValueError("Gmail source artifact was not found")
            state = "confirmed" if existing_account_id else "pending"
            discovery_id = session.execute(
                text(
                    """INSERT INTO discovered_financial_accounts
                       (id, user_id, mailbox_id, fingerprint, institution_code,
                        account_type, masked_identifier, suggested_product_name,
                        suggested_display_name, currency, state, financial_account_id,
                        decided_at)
                       VALUES (:id, :user_id, :mailbox_id, :fingerprint,
                               :institution_code, :account_type, :masked_identifier,
                               :product_name, :display_name, :currency, :state,
                               :account_id,
                               CASE WHEN :state = 'confirmed' THEN now() ELSE NULL END)
                       ON CONFLICT (user_id, fingerprint) DO UPDATE
                       SET mailbox_id = EXCLUDED.mailbox_id,
                           last_detected_at = now(), updated_at = now(),
                           financial_account_id = COALESCE(
                               discovered_financial_accounts.financial_account_id,
                               EXCLUDED.financial_account_id
                           ),
                           state = CASE
                               WHEN discovered_financial_accounts.state = 'rejected'
                                   THEN 'rejected'
                               WHEN discovered_financial_accounts.state = 'confirmed'
                                   THEN 'confirmed'
                               ELSE EXCLUDED.state
                           END
                       RETURNING id"""
                ),
                {
                    "id": uuid4(),
                    "user_id": self.user_id,
                    "mailbox_id": mailbox_id,
                    **identity,
                    "state": state,
                    "account_id": existing_account_id,
                },
            ).scalar_one()
            row = session.execute(
                text(
                    """SELECT id, state, financial_account_id
                       FROM discovered_financial_accounts WHERE id = :id"""
                ),
                {"id": discovery_id},
            ).mappings().one()
        return dict(row)

    def _account_for_hint(self, hint: str, institution_code: str) -> UUID | None:
        ending = hint.rsplit("_", 1)[-1]
        account_type = "credit_card" if hint.startswith("credit_card") else "bank_account"
        with Session(self.engine) as session:
            return session.execute(
                text(
                    """SELECT id FROM financial_accounts
                       WHERE user_id = :user_id
                         AND LOWER(institution_code) = :institution_code
                         AND account_type = :account_type
                         AND masked_identifier LIKE :ending
                         AND status = 'active'
                       ORDER BY created_at
                       LIMIT 1"""
                ),
                {
                    "user_id": self.user_id,
                    "institution_code": institution_code,
                    "account_type": account_type,
                    "ending": f"%{ending}",
                },
            ).scalar_one_or_none()


def account_discovery_identity(
    parser_name: str,
    normalized: dict[str, object],
) -> dict[str, str]:
    hint = str(normalized.get("financial_account_hint", ""))
    match = re.fullmatch(r"(bank_account|credit_card)_ending_(\d{4})", hint)
    if match is None:
        raise ValueError("Parsed alert does not contain a usable account or card identifier")
    account_type, ending = match.groups()
    institution_code = parser_name.lower()
    institution_name = {
        "icici": "ICICI",
        "hdfc": "HDFC",
        "yes": "YES BANK",
        "sbi": "SBI",
        "dcb": "DCB",
        "onecard": "OneCard",
        "citi": "Citi",
    }.get(institution_code, institution_code.upper())
    kind_name = "Credit Card" if account_type == "credit_card" else "Bank Account"
    return {
        "fingerprint": f"{institution_code}:{account_type}:{ending}",
        "institution_code": institution_code,
        "account_type": account_type,
        "masked_identifier": f"••••{ending}",
        "product_name": f"{institution_name} {kind_name}",
        "display_name": f"{institution_name} {kind_name} ••••{ending}",
        "currency": str(normalized.get("currency", "INR")).upper(),
    }


def _required_discovery_text(payload: dict[str, object], field: str) -> str:
    value = str(payload.get(field, "")).strip()
    if not value or len(value) > 120:
        raise ValueError(f"{field.replace('_', ' ').title()} is required")
    return value
