import unittest

import fitz
from arcis_backend.ledger import LedgerError
from arcis_backend.statements import parse_pdf_statement


def _pdf_bytes(text: str, password: str | None = None) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    if password:
        payload = document.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw=password,
            user_pw=password,
        )
    else:
        payload = document.tobytes()
    document.close()
    return payload


def _table_pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "01/08/2026", fontsize=10)
    page.insert_text((180, 72), "UPI SWIGGY ORDER", fontsize=10)
    page.insert_text((420, 72), "850.00", fontsize=10)
    page.insert_text((500, 72), "19,150.00", fontsize=10)
    payload = document.tobytes()
    document.close()
    return payload


class PdfStatementParserTests(unittest.TestCase):
    def test_extracts_rows_and_card_metadata(self):
        content = _pdf_bytes("""ICICI Credit Card Statement
Total Amount Due: 1,250.00
Minimum Amount Due: 125.00
Payment Due Date: 15/08/2026
01/08/2026 SWIGGY ORDER 850.00 DR
02/08/2026 REFUND FROM STORE 400.00 CR""")

        parsed = parse_pdf_statement("icici-credit-card.pdf", content, None)

        self.assertEqual(parsed.parser_name, "icici_credit_card_pdf")
        self.assertEqual(parsed.metadata["statement_amount"], 1250)
        self.assertEqual(parsed.metadata["minimum_due"], 125)
        self.assertEqual(str(parsed.metadata["due_date"]), "2026-08-15")
        self.assertEqual(len(parsed.rows), 2)
        self.assertEqual(parsed.rows[0]["direction"], "debit")
        self.assertEqual(parsed.rows[1]["direction"], "credit")

    def test_requires_the_ephemeral_password_for_a_protected_pdf(self):
        content = _pdf_bytes("01/08/2026 TEST PURCHASE 100.00 DR", password="test-password")

        with self.assertRaisesRegex(LedgerError, "password"):
            parse_pdf_statement("icici-bank.pdf", content, None)
        parsed = parse_pdf_statement("icici-bank.pdf", content, "test-password")

        self.assertEqual(len(parsed.rows), 1)

    def test_reports_an_unsupported_layout_after_a_pdf_opens(self):
        content = _pdf_bytes("ICICI Bank Statement\nThis layout has no extractable transaction rows.")

        with self.assertRaisesRegex(LedgerError, "layout is not supported"):
            parse_pdf_statement("icici-bank.pdf", content, None)

    def test_extracts_columnar_bank_and_card_rows_without_direction_suffixes(self):
        bank = _pdf_bytes("""HDFC Bank Statement
01/08/2026 UPI SWIGGY ORDER 850.00 19,150.00
02/08/2026 SALARY CREDIT 125,000.00 CR 144,150.00""")
        card = _pdf_bytes("""Amazon Pay ICICI Credit Card Statement
01/08/2026 AMAZON MARKETPLACE 1,250.00
02/08/2026 PAYMENT RECEIVED 1,250.00""")

        bank_rows = parse_pdf_statement("hdfc-bank.pdf", bank, None).rows
        card_rows = parse_pdf_statement("amazon-pay-credit-card.pdf", card, None).rows

        self.assertEqual([row["amount"] for row in bank_rows], [850, 125000])
        self.assertEqual([row["direction"] for row in bank_rows], ["debit", "credit"])
        self.assertEqual([row["direction"] for row in card_rows], ["debit", "credit"])

    def test_reconstructs_a_visually_positioned_statement_table_row(self):
        rows = parse_pdf_statement("hdfc-bank.pdf", _table_pdf_bytes(), None).rows

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["narration"], "UPI SWIGGY ORDER")
        self.assertEqual(rows[0]["amount"], 850)

    def test_bank_statement_is_not_classified_as_a_card_from_footer_text(self):
        content = _pdf_bytes("""HDFC Bank Statement
Credit Card offers are available.
01/08/2026 UPI SWIGGY ORDER 850.00 19,150.00""")

        parsed = parse_pdf_statement("hdfc-bank-statement.pdf", content, None)

        self.assertEqual(parsed.parser_name, "hdfc_bank_pdf")
        self.assertEqual(parsed.rows[0]["amount"], 850)

    def test_uses_bank_debit_credit_columns_instead_of_the_running_balance(self):
        content = _pdf_bytes("""HDFC Bank Statement
01/08/2026 UPI SWIGGY ORDER 2,000.00 0.00 80,791.52
02/08/2026 NEFT SALARY 0.00 60,000.00 140,791.52""")

        rows = parse_pdf_statement("hdfc-bank-statement.pdf", content, None).rows

        self.assertEqual([row["amount"] for row in rows], [2000, 60000])
        self.assertEqual([row["direction"] for row in rows], ["debit", "credit"])

    def test_inferrs_icici_direction_from_running_balance_changes(self):
        content = _pdf_bytes("""ICICI Bank Statement
01/03/2026 UPI PURCHASE 2,000.00 80,000.00
02/03/2026 NEFT SALARY 60,000.00 140,000.00
03/03/2026 ATM WITHDRAWAL 5,000.00 135,000.00""")

        rows = parse_pdf_statement("icici-bank-statement.pdf", content, None).rows

        self.assertEqual([row["direction"] for row in rows], ["debit", "credit", "debit"])
