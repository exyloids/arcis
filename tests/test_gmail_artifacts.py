import unittest

from arcis_backend.gmail_artifacts import _statement_password_guidance


class StatementPasswordGuidanceTests(unittest.TestCase):
    def test_customer_id_instruction_is_displayed_without_copying_the_value(self):
        guidance = _statement_password_guidance(
            "Enter your customer ID 12345678 as the password to open the statement."
        )

        self.assertEqual(guidance, "Use your Customer ID as the PDF password.")
        self.assertNotIn("12345678", guidance)

    def test_explicit_password_is_never_copied(self):
        guidance = _statement_password_guidance(
            "Your statement password is SecretValue123."
        )

        self.assertIn("does not copy it", guidance)
        self.assertNotIn("SecretValue123", guidance)

    def test_date_of_birth_format_is_retained_without_personal_data(self):
        guidance = _statement_password_guidance(
            "Use your date of birth in DDMMYYYY format as the PDF password."
        )

        self.assertEqual(
            guidance,
            "Use your date of birth in DDMMYYYY format as the PDF password.",
        )
