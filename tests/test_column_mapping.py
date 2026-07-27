import unittest
from pathlib import Path

from arcis_backend.ledger import (
    LedgerError,
    _parse_tabular_upload_with_mapping,
    inspect_tabular_upload,
)

ROOT = Path(__file__).parents[1]


class ColumnMappingTests(unittest.TestCase):
    def test_known_hdfc_headers_receive_mapping_suggestions(self):
        content = (ROOT / "fixtures/sanitized/hdfc_bank_statement.csv").read_bytes()

        inspection = inspect_tabular_upload("hdfc.csv", content)

        self.assertEqual(inspection["sample_row_count"], 3)
        self.assertEqual(inspection["suggested_mapping"]["debit"], "Withdrawal Amt.")
        self.assertEqual(inspection["suggested_mapping"]["credit"], "Deposit Amt.")

    def test_explicit_mapping_normalizes_unknown_headers(self):
        content = b"When,Details,Out,In,Ref\n01/07/2026,Test purchase,12.50,,REF-1\n"
        mapping = {
            "transaction_date": "When",
            "narration": "Details",
            "debit": "Out",
            "credit": "In",
            "provider_reference": "Ref",
        }

        rows = _parse_tabular_upload_with_mapping("unknown.csv", content, mapping)

        self.assertEqual(rows[0]["amount"], 12.5)
        self.assertEqual(rows[0]["direction"], "debit")

    def test_mapping_requires_core_columns(self):
        with self.assertRaisesRegex(LedgerError, "missing"):
            _parse_tabular_upload_with_mapping(
                "unknown.csv", b"When,Details\n01/07/2026,Test\n", {"transaction_date": "When"}
            )

    def test_validation_error_identifies_statement_row(self):
        with self.assertRaisesRegex(LedgerError, "row 2"):
            _parse_tabular_upload_with_mapping(
                "invalid.csv", b"Date,Narration,Debit,Credit\n01/07/2026,Invalid,100,200\n", None
            )

    def test_xlsx_requires_zip_signature(self):
        with self.assertRaisesRegex(LedgerError, "signature"):
            _parse_tabular_upload_with_mapping("invalid.xlsx", b"not-an-xlsx", None)
