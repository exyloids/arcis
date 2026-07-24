import sqlite3
import tempfile
import unittest
from pathlib import Path

from spikes.statement_replay.statement_replay import (
    ReplayRepository,
    artifact_sha256,
    parse_statement,
    run_proof,
)

ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "fixtures/sanitized/icici_bank_statement.csv"


class StatementReplayTests(unittest.TestCase):
    def test_fixture_parses_expected_directions_and_amounts(self):
        records = parse_statement(FIXTURE, artifact_sha256(FIXTURE))
        self.assertEqual(len(records), 3)
        self.assertEqual([record.direction for record in records], ["debit", "credit", "debit"])
        self.assertEqual(
            [str(record.amount) for record in records],
            ["850.00", "125000.00", "5000.00"],
        )

    def test_replaying_same_artifact_is_idempotent(self):
        first, replay, transaction_count = run_proof(FIXTURE)
        self.assertEqual(first["artifacts_added"], 1)
        self.assertEqual(first["source_records_added"], 3)
        self.assertEqual(first["transactions_added"], 3)
        self.assertEqual(first["duplicates_ignored"], 0)
        self.assertEqual(replay["artifacts_added"], 0)
        self.assertEqual(replay["source_records_added"], 0)
        self.assertEqual(replay["transactions_added"], 0)
        self.assertEqual(replay["duplicates_ignored"], 3)
        self.assertEqual(transaction_count, 3)

    def test_same_bytes_for_different_account_are_not_reused(self):
        records = parse_statement(FIXTURE, artifact_sha256(FIXTURE))
        connection = sqlite3.connect(":memory:")
        repository = ReplayRepository(connection)
        first = repository.ingest(
            user_id="sanitized-user",
            account_id="icici-bank-sanitized",
            artifact_id="artifact-account-one",
            artifact_hash=artifact_sha256(FIXTURE),
            records=records,
        )
        second = repository.ingest(
            user_id="sanitized-user",
            account_id="hdfc-bank-sanitized",
            artifact_id="artifact-account-two",
            artifact_hash=artifact_sha256(FIXTURE),
            records=records,
        )
        self.assertEqual(first["artifacts_added"], 1)
        self.assertEqual(second["artifacts_added"], 1)
        self.assertEqual(second["transactions_added"], 3)
        self.assertEqual(
            connection.execute("SELECT COUNT(*) FROM source_artifacts").fetchone()[0],
            2,
        )
        connection.close()

    def test_invalid_row_with_two_amounts_fails_closed(self):
        invalid_csv = (
            "Transaction Date,Value Date,Transaction Remarks,Withdrawal Amount,"
            "Deposit Amount,Reference No.\n"
            "01/07/2026,01/07/2026,INVALID,100.00,10.00,INVALID-001\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.csv"
            path.write_text(invalid_csv, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exactly one amount"):
                parse_statement(path, "fixture-hash")


if __name__ == "__main__":
    unittest.main()
