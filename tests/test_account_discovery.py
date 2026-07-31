import unittest

from arcis_backend.candidates import account_discovery_identity
from arcis_backend.parsers import discover_financial_product


class AccountDiscoveryIdentityTests(unittest.TestCase):
    def test_builds_stable_bank_account_fingerprint(self) -> None:
        identity = account_discovery_identity(
            "icici",
            {
                "financial_account_hint": "bank_account_ending_1234",
                "currency": "INR",
            },
        )

        self.assertEqual(identity["fingerprint"], "icici:bank_account:1234")
        self.assertEqual(identity["masked_identifier"], "••••1234")
        self.assertEqual(identity["product_name"], "ICICI Bank Account")
        self.assertEqual(identity["currency"], "INR")

    def test_keeps_card_identity_separate_from_bank_account(self) -> None:
        identity = account_discovery_identity(
            "hdfc",
            {
                "financial_account_hint": "credit_card_ending_1234",
                "currency": "inr",
            },
        )

        self.assertEqual(identity["fingerprint"], "hdfc:credit_card:1234")
        self.assertEqual(identity["account_type"], "credit_card")
        self.assertEqual(identity["currency"], "INR")

    def test_uses_provider_display_name_for_yes_bank(self) -> None:
        identity = account_discovery_identity(
            "yes",
            {
                "financial_account_hint": "credit_card_ending_1234",
                "currency": "INR",
            },
        )

        self.assertEqual(identity["product_name"], "YES BANK Credit Card")

    def test_rejects_identifier_without_last_four_digits(self) -> None:
        with self.assertRaisesRegex(ValueError, "usable account or card identifier"):
            account_discovery_identity(
                "icici",
                {"financial_account_hint": "bank_account_unknown"},
            )

    def test_detects_hdfc_savings_account_from_unsupported_layout(self) -> None:
        detected = discover_financial_product(
            _email(
                "alerts@alerts.hdfcbank.com",
                "Rs.500.00 has been debited from HDFC Bank Account Number "
                "12345678901234 towards a mandate.",
            )
        )

        self.assertEqual(
            detected,
            (
                "hdfc",
                {
                    "financial_account_hint": "bank_account_ending_1234",
                    "currency": "INR",
                },
            ),
        )

    def test_detects_icici_savings_account_with_a_c_notation(self) -> None:
        detected = discover_financial_product(
            _email(
                "alerts@alerts.icicibank.com",
                "INR 900.00 was credited to A/C XXXXXXXX5678 on 30-Jul-2026.",
            )
        )

        self.assertEqual(
            detected,
            (
                "icici",
                {
                    "financial_account_hint": "bank_account_ending_5678",
                    "currency": "INR",
                },
            ),
        )

    def test_detects_credit_card_without_confusing_it_with_bank_account(self) -> None:
        detected = discover_financial_product(
            _email(
                "alerts@alerts.icicibank.com",
                "Payment of INR 500.00 received towards "
                "ICICI Bank Credit Card XX8765.",
            )
        )

        self.assertEqual(
            detected,
            (
                "icici",
                {
                    "financial_account_hint": "credit_card_ending_8765",
                    "currency": "INR",
                },
            ),
        )

    def test_credit_card_account_wording_remains_a_card(self) -> None:
        detected = discover_financial_product(
            _email(
                "alerts@icicibank.com",
                "We received payment of INR 500.00 on your ICICI Bank "
                "Credit Card Account 4XXX XXXX XXXX 8765.",
            )
        )

        self.assertEqual(
            detected,
            (
                "icici",
                {
                    "financial_account_hint": "credit_card_ending_8765",
                    "currency": "INR",
                },
            ),
        )

    def test_does_not_discover_product_from_promotional_email(self) -> None:
        detected = discover_financial_product(
            _email(
                "offers@icicibank.com",
                "Explore rewards for your Account Number 12345678901234.",
            )
        )

        self.assertIsNone(detected)

    def test_detects_new_hdfc_sender_and_keeps_only_ending_digits(self) -> None:
        detected = discover_financial_product(
            _email(
                "alerts@hdfcbank.bank.in",
                "Rs 250.00 has been debited from HDFC Bank Account Number "
                "12345678904321 towards a payment.",
            )
        )

        self.assertEqual(
            detected,
            (
                "hdfc",
                {
                    "financial_account_hint": "bank_account_ending_4321",
                    "currency": "INR",
                },
            ),
        )

    def test_detects_hdfc_net_sender(self) -> None:
        detected = discover_financial_product(
            _email(
                "alerts@hdfcbank.net",
                "Rs 250.00 is credited to your account ending 4321.",
            )
        )

        self.assertEqual(
            detected,
            (
                "hdfc",
                {
                    "financial_account_hint": "bank_account_ending_4321",
                    "currency": "INR",
                },
            ),
        )

    def test_detects_icici_payment_from_savings_account(self) -> None:
        detected = discover_financial_product(
            _email(
                "services@custcomm.icicibank.com",
                "An online payment of Rs 450.00 was made from your "
                "ICICI Bank Savings Account XXXX4321. "
                "The transaction ID is TEST-REFERENCE.",
            )
        )

        self.assertEqual(
            detected,
            (
                "icici",
                {
                    "financial_account_hint": "bank_account_ending_4321",
                    "currency": "INR",
                },
            ),
        )

    def test_detects_declined_card_as_product_not_as_transaction(self) -> None:
        raw = _email(
            "customernotification@icici.bank.in",
            "Your transaction of INR 800.00 using your ICICI Bank "
            "Credit Card XX4321 has been declined.",
        )

        self.assertEqual(
            discover_financial_product(raw),
            (
                "icici",
                {
                    "financial_account_hint": "credit_card_ending_4321",
                    "currency": "INR",
                },
            ),
        )

    def test_detects_yes_bank_credit_card(self) -> None:
        detected = discover_financial_product(
            _email(
                "alerts@yes.bank.in",
                "INR 900.00 has been spent on your YES BANK "
                "Credit Card ending with 4321.",
            )
        )

        self.assertEqual(
            detected,
            (
                "yes",
                {
                    "financial_account_hint": "credit_card_ending_4321",
                    "currency": "INR",
                },
            ),
        )

    def test_detects_sbi_a_c_notation(self) -> None:
        detected = discover_financial_product(
            _email(
                "notice@alerts.sbi.bank.in",
                "Your A/C XXXXX4321 has been credited with INR 900.00.",
            )
        )

        self.assertEqual(
            detected,
            (
                "sbi",
                {
                    "financial_account_hint": "bank_account_ending_4321",
                    "currency": "INR",
                },
            ),
        )

    def test_detects_dcb_account(self) -> None:
        detected = discover_financial_product(
            _email(
                "alerts@dcbbank.com",
                "Your Account Number XXXXX4321 was credited INR 900.00.",
            )
        )

        self.assertEqual(
            detected,
            (
                "dcb",
                {
                    "financial_account_hint": "bank_account_ending_4321",
                    "currency": "INR",
                },
            ),
        )

    def test_ignores_starting_digits_without_an_ending(self) -> None:
        detected = discover_financial_product(
            _email(
                "alerts@icicibank.com",
                "INR 100.00 was spent using a Credit Card starting with 4321.",
            )
        )

        self.assertIsNone(detected)

    def test_uses_ending_digits_when_token_contains_start_and_end(self) -> None:
        detected = discover_financial_product(
            _email(
                "alerts@icicibank.com",
                "INR 100.00 was spent using ICICI Bank Credit Card "
                "4321XXXXXXXX8765.",
            )
        )

        self.assertEqual(
            detected,
            (
                "icici",
                {
                    "financial_account_hint": "credit_card_ending_8765",
                    "currency": "INR",
                },
            ),
        )

    def test_does_not_treat_customer_id_as_an_account(self) -> None:
        detected = discover_financial_product(
            _email(
                "alerts@hdfcbank.bank.in",
                "A payment of Rs 100.00 was received. "
                "Your customer ID is 12345678.",
            )
        )

        self.assertIsNone(detected)

    def test_does_not_treat_debit_card_ending_as_bank_account(self) -> None:
        detected = discover_financial_product(
            _email(
                "alerts@icici.bank.in",
                "INR 100.00 was spent using Debit Card ending with 4321.",
            )
        )

        self.assertIsNone(detected)

    def test_rejects_sender_domain_suffix_spoofing(self) -> None:
        detected = discover_financial_product(
            _email(
                "alerts@icicibank.com.evil.example",
                "INR 100.00 was spent using Credit Card XX4321.",
            )
        )

        self.assertIsNone(detected)

    def test_ignores_last_four_in_non_transaction_instructions(self) -> None:
        detected = discover_financial_product(
            _email(
                "alerts@yes.bank.in",
                "Send the last 4 digits of your card number to 12345.",
            )
        )

        self.assertIsNone(detected)


def _email(sender: str, body: str) -> bytes:
    return (
        f"From: Bank Alerts <{sender}>\n"
        "To: owner@example.invalid\n"
        "Subject: Transaction alert\n"
        "MIME-Version: 1.0\n"
        'Content-Type: text/plain; charset="utf-8"\n'
        f"\n{body}\n"
    ).encode()


if __name__ == "__main__":
    unittest.main()
