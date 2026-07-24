"""Statement replay feasibility proof for an ICICI-style CSV statement.

This intentionally uses only the Python standard library. It is a small,
fixture-driven proof of the source-evidence/canonical-ledger boundary. The
production implementation will replace the SQLite proof repository with the
PostgreSQL repositories defined in docs/ARCHITECTURE.md.
"""

from __future__ import annotations

import csv
import hashlib
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

EXPECTED_COLUMNS = (
    "Transaction Date",
    "Value Date",
    "Transaction Remarks",
    "Withdrawal Amount",
    "Deposit Amount",
    "Reference No.",
)


@dataclass(frozen=True)
class ParsedRecord:
    source_record_key: str
    transaction_date: date
    posted_date: date
    narration: str
    amount: Decimal
    direction: str
    reference: str
    row_number: int


def parse_date(value: str) -> date:
    return datetime.strptime(value.strip(), "%d/%m/%Y").date()


def parse_amount(value: str | None) -> Decimal | None:
    if value is None or not value.strip():
        return None
    amount = Decimal(value.replace(",", "").strip())
    if amount < 0:
        raise ValueError("statement amounts must be positive")
    return amount.quantize(Decimal("0.01"))


def parse_statement(path: Path, artifact_hash: str) -> list[ParsedRecord]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
            raise ValueError("unexpected ICICI statement columns")

        records: list[ParsedRecord] = []
        for row_number, row in enumerate(reader, start=2):
            withdrawal = parse_amount(row["Withdrawal Amount"])
            deposit = parse_amount(row["Deposit Amount"])
            if (withdrawal is None) == (deposit is None):
                raise ValueError(f"row {row_number}: exactly one amount is required")

            reference = row["Reference No."].strip()
            if not reference:
                raise ValueError(f"row {row_number}: reference is required")

            direction = "debit" if withdrawal is not None else "credit"
            amount = withdrawal if withdrawal is not None else deposit
            source_record_key = hashlib.sha256(
                f"{artifact_hash}:{reference}".encode()
            ).hexdigest()
            records.append(
                ParsedRecord(
                    source_record_key=source_record_key,
                    transaction_date=parse_date(row["Transaction Date"]),
                    posted_date=parse_date(row["Value Date"]),
                    narration=row["Transaction Remarks"].strip(),
                    amount=amount,
                    direction=direction,
                    reference=reference,
                    row_number=row_number,
                )
            )
        return records


class ReplayRepository:
    """Minimal transactional repository used only by this feasibility proof."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_artifacts (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                UNIQUE (user_id, account_id, content_sha256)
            );
            CREATE TABLE IF NOT EXISTS source_records (
                id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL REFERENCES source_artifacts(id),
                source_record_key TEXT NOT NULL,
                transaction_date TEXT NOT NULL,
                posted_date TEXT NOT NULL,
                narration TEXT NOT NULL,
                amount TEXT NOT NULL,
                direction TEXT NOT NULL,
                reference TEXT NOT NULL,
                UNIQUE (artifact_id, source_record_key)
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                transaction_date TEXT NOT NULL,
                posted_date TEXT NOT NULL,
                narration TEXT NOT NULL,
                amount TEXT NOT NULL,
                direction TEXT NOT NULL,
                UNIQUE (user_id, account_id, transaction_date, posted_date,
                        amount, direction, narration)
            );
            CREATE TABLE IF NOT EXISTS transaction_evidence (
                transaction_id TEXT NOT NULL REFERENCES transactions(id),
                source_record_id TEXT NOT NULL REFERENCES source_records(id),
                PRIMARY KEY (transaction_id, source_record_id),
                UNIQUE (source_record_id)
            );
            """
        )

    def ingest(
        self,
        *,
        user_id: str,
        account_id: str,
        artifact_id: str,
        artifact_hash: str,
        records: Iterable[ParsedRecord],
    ) -> dict[str, int]:
        added_artifacts = 0
        added_records = 0
        added_transactions = 0
        ignored_duplicates = 0

        with self.connection:
            artifact = self.connection.execute(
                """
                SELECT id FROM source_artifacts
                WHERE user_id = ? AND account_id = ? AND content_sha256 = ?
                """,
                (user_id, account_id, artifact_hash),
            ).fetchone()
            if artifact is None:
                self.connection.execute(
                    "INSERT INTO source_artifacts VALUES (?, ?, ?, ?)",
                    (artifact_id, user_id, account_id, artifact_hash),
                )
                artifact_id_in_db = artifact_id
                added_artifacts = 1
            else:
                artifact_id_in_db = artifact[0]

            for record in records:
                source_id = hashlib.sha256(
                    f"{artifact_id_in_db}:{record.source_record_key}".encode()
                ).hexdigest()
                inserted = self.connection.execute(
                    """
                    INSERT OR IGNORE INTO source_records
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        artifact_id_in_db,
                        record.source_record_key,
                        record.transaction_date.isoformat(),
                        record.posted_date.isoformat(),
                        record.narration,
                        str(record.amount),
                        record.direction,
                        record.reference,
                    ),
                )
                if inserted.rowcount == 0:
                    ignored_duplicates += 1
                    continue
                added_records += 1

                transaction_id = hashlib.sha256(
                    f"{user_id}:{account_id}:{record.source_record_key}".encode()
                ).hexdigest()
                inserted = self.connection.execute(
                    """
                    INSERT OR IGNORE INTO transactions
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        transaction_id,
                        user_id,
                        account_id,
                        record.transaction_date.isoformat(),
                        record.posted_date.isoformat(),
                        record.narration,
                        str(record.amount),
                        record.direction,
                    ),
                )
                if inserted.rowcount == 1:
                    added_transactions += 1
                self.connection.execute(
                    "INSERT OR IGNORE INTO transaction_evidence VALUES (?, ?)",
                    (transaction_id, source_id),
                )

        return {
            "artifacts_added": added_artifacts,
            "source_records_added": added_records,
            "transactions_added": added_transactions,
            "duplicates_ignored": ignored_duplicates,
        }


def artifact_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_proof(fixture: Path) -> tuple[dict[str, int], dict[str, int], int]:
    digest = artifact_sha256(fixture)
    records = parse_statement(fixture, digest)
    connection = sqlite3.connect(":memory:")
    repository = ReplayRepository(connection)
    first = repository.ingest(
        user_id="sanitized-user",
        account_id="icici-bank-sanitized",
        artifact_id="artifact-icici-001",
        artifact_hash=digest,
        records=records,
    )
    replay = repository.ingest(
        user_id="sanitized-user",
        account_id="icici-bank-sanitized",
        artifact_id="artifact-icici-001-retry",
        artifact_hash=digest,
        records=records,
    )
    transaction_count = connection.execute(
        "SELECT COUNT(*) FROM transactions"
    ).fetchone()[0]
    connection.close()
    return first, replay, transaction_count


if __name__ == "__main__":
    fixture = Path(__file__).parents[2] / "fixtures/sanitized/icici_bank_statement.csv"
    first, replay, transaction_count = run_proof(fixture)
    print({"first_import": first, "replay": replay, "transaction_count": transaction_count})
