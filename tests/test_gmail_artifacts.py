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

    def test_dcb_guidance_preserves_customer_id_and_pan_alternatives(self):
        guidance = _statement_password_guidance(
            "The password is your DCB Bank Customer ID or 10-digit PAN in "
            "uppercase. For joint accounts, use the primary account holder."
        )

        self.assertEqual(
            guidance,
            "Use your DCB Bank Customer ID or the primary account holder's "
            "10-digit PAN in uppercase as the PDF password.",
        )

    def test_sbi_guidance_preserves_composition_and_dob_format(self):
        guidance = _statement_password_guidance(
            "Your SBI e-account statement is protected by a password, which is "
            "the last five digits of customer registered mobile number and date "
            "of birth (DOB) in DDMMYY format registered with Bank."
        )

        self.assertEqual(
            guidance,
            "Use the last five digits of your registered mobile number followed "
            "by your date of birth in DDMMYY format as the PDF password.",
        )

    def test_current_hdfc_guidance_is_customer_id(self):
        guidance = _statement_password_guidance(
            "HDFC Bank Combined Email Statement. "
            "Enter your Customer ID as the password."
        )

        self.assertEqual(guidance, "Use your HDFC Customer ID as the PDF password.")

    def test_icici_statement_uses_lowercase_name_and_dob_format(self):
        guidance = _statement_password_guidance(
            "ICICI Bank Statement for July 2026 is attached."
        )

        self.assertEqual(
            guidance,
            "Use the first four letters of your name as it appears on your card, "
            "followed by your date of birth in DDMM format. Enter the letters in "
            "lowercase with no spaces or special characters.",
        )
