import json
import unittest
from pathlib import Path

from arcis_backend.parsers import parse_hdfc_alert, parse_icici_alert

ROOT = Path(__file__).parents[1]


class IciciEmailParserTests(unittest.TestCase):
    def test_account_debit_fixture(self):
        parsed = parse_icici_alert((ROOT / "fixtures/sanitized/gmail/icici_account_debit.eml").read_bytes())
        expected = json.loads((ROOT / "fixtures/sanitized/expected/icici_account_debit.json").read_text())
        self.assertEqual(parsed, expected)

    def test_credit_card_fixture(self):
        parsed = parse_icici_alert((ROOT / "fixtures/sanitized/gmail/icici_credit_card_purchase.eml").read_bytes())
        expected = json.loads((ROOT / "fixtures/sanitized/expected/icici_credit_card_purchase.json").read_text())
        self.assertEqual(parsed, expected)

    def test_imobile_transfer_fixture(self):
        parsed = parse_icici_alert((ROOT / "fixtures/sanitized/gmail/icici_imobile_transfer.eml").read_bytes())
        expected = json.loads((ROOT / "fixtures/sanitized/expected/icici_imobile_transfer.json").read_text())
        self.assertEqual(parsed, expected)

    def test_hdfc_upi_fixture(self):
        parsed = parse_hdfc_alert((ROOT / "fixtures/sanitized/gmail/hdfc_upi_debit.eml").read_bytes())
        expected = json.loads((ROOT / "fixtures/sanitized/expected/hdfc_upi_debit.json").read_text())
        self.assertEqual(parsed, expected)
