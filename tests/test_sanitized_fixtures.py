import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "fixtures" / "sanitized"
EXPECTED = FIXTURES / "expected"
REQUIRED_TRANSACTION_FIELDS = {"amount", "currency", "direction", "source_kind", "transaction_date"}


class SanitizedFixtureTests(unittest.TestCase):
    def test_every_expected_record_has_the_normalized_transaction_contract(self):
        for expectation_path in EXPECTED.glob("*.json"):
            payload = json.loads(expectation_path.read_text(encoding="utf-8"))
            records = payload if isinstance(payload, list) else [payload]
            for record in records:
                self.assertTrue(
                    REQUIRED_TRANSACTION_FIELDS.issubset(record),
                    f"{expectation_path.name} is missing a required normalized field",
                )
                self.assertIn(record["direction"], {"debit", "credit"})
                self.assertEqual(record["currency"], "INR")

    def test_gmail_fixtures_are_synthetic_and_have_corresponding_expectations(self):
        for email_path in (FIXTURES / "gmail").glob("*.eml"):
            expected_path = EXPECTED / f"{email_path.stem}.json"
            content = email_path.read_text(encoding="utf-8")
            self.assertTrue(expected_path.is_file())
            self.assertIn("example.invalid", content)
            self.assertIn("SAN-EMAIL", content)
