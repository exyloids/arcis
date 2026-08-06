import json
import unittest
from pathlib import Path

from arcis_backend.parsers import (
    parse_dcb_alert,
    parse_hdfc_alert,
    parse_icici_alert,
    parse_onecard_alert,
    parse_sbi_alert,
    parse_yes_alert,
)

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

    def test_current_hdfc_upi_debit_layout(self):
        parsed = parse_hdfc_alert(
            _email(
                "alerts@hdfcbank.bank.in",
                "Rs. 425.50 is debited from your account ending 8765 "
                "towards SYNTHETIC-MERCHANT@BANK on 30-07-26. "
                "UPI transaction reference no.: TEST-HDFC-REF.",
            )
        )

        self.assertEqual(parsed["financial_account_hint"], "bank_account_ending_8765")
        self.assertEqual(parsed["transaction_date"], "2026-07-30")
        self.assertEqual(parsed["amount"], "425.50")
        self.assertEqual(parsed["direction"], "debit")
        self.assertEqual(parsed["provider_reference"], "TEST-HDFC-REF")

    def test_current_icici_online_payment_layout(self):
        parsed = parse_icici_alert(
            _email(
                "services@custcomm.icicibank.com",
                "You have made an online IMPS payment of Rs. 425.50 "
                "towards SYNTHETIC MERCHANT on Jul 30, 2026 at 10:30 AM "
                "from your ICICI Bank Savings Account XXXX8765. "
                "The transaction ID is TEST-ICICI-REF.",
            )
        )

        self.assertEqual(parsed["financial_account_hint"], "bank_account_ending_8765")
        self.assertEqual(parsed["transaction_date"], "2026-07-30")
        self.assertEqual(parsed["direction"], "debit")
        self.assertEqual(parsed["provider_reference"], "TEST-ICICI-REF")

    def test_yes_card_purchase_layout(self):
        parsed = parse_yes_alert(
            _email(
                "alerts@yes.bank.in",
                "INR 425.50 has been spent on your YES BANK Credit Card "
                "ending with 8765 at SYNTHETIC MERCHANT on 30-07-2026 "
                "at 10:30 AM.",
            )
        )

        self.assertEqual(parsed["financial_account_hint"], "credit_card_ending_8765")
        self.assertEqual(parsed["transaction_date"], "2026-07-30")
        self.assertEqual(parsed["direction"], "debit")

    def test_sbi_neft_credit_layout(self):
        parsed = parse_sbi_alert(
            _email(
                "notice@alerts.sbi.bank.in",
                "Credited to your A/C: XX8765 Amount: INR 425.50 "
                "UTR No.: TEST-SBI-REF Date: 30/07/2026",
            )
        )

        self.assertEqual(parsed["financial_account_hint"], "bank_account_ending_8765")
        self.assertEqual(parsed["transaction_date"], "2026-07-30")
        self.assertEqual(parsed["direction"], "credit")
        self.assertEqual(parsed["provider_reference"], "TEST-SBI-REF")

    def test_dcb_debit_layout(self):
        parsed = parse_dcb_alert(
            _email(
                "alerts@dcbbank.com",
                "Your Account Number ***8765 is debited by INR 425.50 "
                "on 30-07-2026. Available balance is INR 1,000.00.",
            )
        )

        self.assertEqual(parsed["financial_account_hint"], "bank_account_ending_8765")
        self.assertEqual(parsed["transaction_date"], "2026-07-30")
        self.assertEqual(parsed["direction"], "debit")

    def test_onecard_html_alert_ignores_null_plain_part(self):
        parsed = parse_onecard_alert(
            _multipart_email(
                "no-reply@getonecard.app",
                "Your Federal Bank One Credit Card ending in 8765 was used "
                "to make a payment. Amount: INR 425.50 Merchant: SYNTHETIC "
                "MERCHANT Date: 30/07/2026 Time: 10:30:00",
            )
        )

        self.assertEqual(parsed["financial_account_hint"], "credit_card_ending_8765")
        self.assertEqual(parsed["transaction_date"], "2026-07-30")
        self.assertEqual(parsed["amount"], "425.50")
        self.assertEqual(parsed["merchant"], "SYNTHETIC MERCHANT")
        self.assertEqual(parsed["direction"], "debit")


def _email(sender: str, body: str) -> bytes:
    return (
        f"From: Bank Alerts <{sender}>\n"
        "To: owner@example.invalid\n"
        "Subject: Transaction alert\n"
        "MIME-Version: 1.0\n"
        'Content-Type: text/plain; charset="utf-8"\n'
        f"\n{body}\n"
    ).encode()


def _multipart_email(sender: str, html_body: str) -> bytes:
    return (
        f"From: Card Alerts <{sender}>\n"
        "To: owner@example.invalid\n"
        "Subject: Payment update\n"
        "MIME-Version: 1.0\n"
        'Content-Type: multipart/alternative; boundary="arcis-test"\n\n'
        "--arcis-test\nContent-Type: text/plain; charset=utf-8\n\nnull\n"
        "--arcis-test\nContent-Type: text/html; charset=utf-8\n\n"
        f"<html><body>{html_body}</body></html>\n"
        "--arcis-test--\n"
    ).encode()
