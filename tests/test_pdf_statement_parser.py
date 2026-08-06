import unittest
from decimal import Decimal

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


def _icici_wrapped_table_pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page(width=842, height=595)
    page.insert_text((40, 40), "ICICI Bank Statement", fontsize=10)
    headers = ((40, "DATE"), (150, "MODE"), (260, "PARTICULARS"),
               (560, "DEPOSITS"), (650, "WITHDRAWALS"), (750, "BALANCE"))
    for x, label in headers:
        page.insert_text((x, 75), label, fontsize=9)

    page.insert_text((40, 100), "01-07-2026", fontsize=9)
    page.insert_text((260, 100), "B/F", fontsize=9)
    page.insert_text((750, 100), "16,76,151.59", fontsize=9)

    page.insert_text((40, 135), "03-07-2026", fontsize=9)
    page.insert_text((260, 124), "BIL/NEFT/IN12618444669550/Family/Sudha", fontsize=9)
    page.insert_text((260, 136), "Soni/SBIN0005895", fontsize=9)
    page.insert_text((650, 135), "13,000.00", fontsize=9)
    page.insert_text((750, 135), "16,63,151.59", fontsize=9)

    page.insert_text((40, 170), "04-07-2026", fontsize=9)
    page.insert_text((150, 170), "MOBILE BANKING", fontsize=9)
    page.insert_text((260, 160), "Aakash Son", fontsize=9)
    page.insert_text((260, 172), "MMT/IMPS/618514128740/SAMPLE", fontsize=9)
    page.insert_text((650, 170), "70,000.00", fontsize=9)
    page.insert_text((750, 170), "15,93,151.59", fontsize=9)

    page.insert_text((40, 205), "05-07-2026", fontsize=9)
    page.insert_text((260, 205), "ACH/HDFC BANK LTD/SAMPLE", fontsize=9)
    page.insert_text((650, 205), "52,929.00", fontsize=9)
    page.insert_text((750, 205), "15,40,222.59", fontsize=9)

    page.insert_text((40, 250), "30-07-2026", fontsize=9)
    page.insert_text((260, 238), "ServiceNow Software Development India", fontsize=9)
    page.insert_text((260, 250), "Private Limited", fontsize=9)
    # The date is vertically offset from the amount/balance in this wrapped
    # row, matching the real statement layout that previously leaked the
    # deposit into the following transaction.
    page.insert_text((560, 266), "12,699.00", fontsize=9)
    page.insert_text((750, 266), "15,52,921.59", fontsize=9)

    page.insert_text((40, 285), "31-07-2026", fontsize=9)
    page.insert_text((150, 285), "MOBILE BANKING", fontsize=9)
    page.insert_text((260, 276), "Aakash Son", fontsize=9)
    page.insert_text((260, 288), "MMT/IMPS/621214242600/SAMPLE", fontsize=9)
    page.insert_text((650, 285), "50,000.00", fontsize=9)
    page.insert_text((750, 285), "15,02,921.59", fontsize=9)
    page.insert_text((560, 312), "12,699.00", fontsize=9)
    page.insert_text((650, 312), "1,85,929.00", fontsize=9)
    page.insert_text((750, 312), "15,02,921.59", fontsize=9)
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

    def test_reconstructs_all_wrapped_icici_deposit_withdrawal_rows(self):
        parsed = parse_pdf_statement(
            "icici-bank-statement.pdf",
            _icici_wrapped_table_pdf_bytes(),
            None,
        )

        self.assertEqual(len(parsed.rows), 5)
        self.assertEqual(
            [row["amount"] for row in parsed.rows],
            [13000, 70000, 52929, 12699, 50000],
        )
        self.assertEqual(
            [row["direction"] for row in parsed.rows],
            ["debit", "debit", "debit", "credit", "debit"],
        )
        self.assertEqual(parsed.metadata["opening_balance"], Decimal("1676151.59"))
        self.assertEqual(parsed.metadata["closing_balance"], Decimal("1502921.59"))

    def test_bank_statement_is_not_classified_as_a_card_from_footer_text(self):
        content = _pdf_bytes("""HDFC Bank Statement
Credit Card offers are available.
01/08/2026 UPI SWIGGY ORDER 850.00 19,150.00""")

        parsed = parse_pdf_statement("hdfc-bank-statement.pdf", content, None)

        self.assertEqual(parsed.parser_name, "hdfc_bank_pdf")
        self.assertEqual(parsed.rows[0]["amount"], 850)

    def test_bank_statement_uses_final_running_balance_as_a_balance_baseline(self):
        content = _pdf_bytes("""ICICI Bank Statement
Statement Period: 01/08/2026 to 31/08/2026
01/08/2026 UPI TEST MERCHANT 850.00 19,150.00
31/08/2026 SALARY CREDIT 1,000.00 CR 20,150.00""")

        parsed = parse_pdf_statement("icici-bank.pdf", content, None)

        self.assertEqual(str(parsed.metadata["period_start"]), "2026-08-01")
        self.assertEqual(str(parsed.metadata["period_end"]), "2026-08-31")
        self.assertEqual(parsed.metadata["closing_balance"], 20150)

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

    def test_icici_brought_forward_is_opening_balance_not_transaction(self):
        content = _pdf_bytes("""ICICI Bank Statement
Statement Period: 01/03/2026 to 31/03/2026
01/03/2026 B/F 0.00 0.00 80,000.00
02/03/2026 UPI PURCHASE 2,000.00 78,000.00
03/03/2026 NEFT SALARY 60,000.00 138,000.00""")

        parsed = parse_pdf_statement("icici-bank-statement.pdf", content, None)

        self.assertEqual(parsed.metadata["opening_balance"], 80000)
        self.assertEqual(len(parsed.rows), 2)
        self.assertEqual(
            [row["narration"] for row in parsed.rows],
            ["UPI PURCHASE", "NEFT SALARY"],
        )
        self.assertEqual(
            [row["direction"] for row in parsed.rows],
            ["debit", "credit"],
        )

    def test_dcb_interest_is_credit_and_total_balance_is_not_transaction(self):
        content = _pdf_bytes("""DCB Bank Consolidated Account Statement
Opening Balance: 13,070.11
30-06-2026 SB Int.****29999:Pd:01-04-2026 to 30-06-2026 49.00 13,119.11
3-3-62 FL.NO 401 SAMPLE RESIDENCY Total Deposits & Investments 13,119.11
Closing Balance: 13,119.11""")

        parsed = parse_pdf_statement("dcb-bank-statement.pdf", content, None)

        self.assertEqual(parsed.metadata["opening_balance"], Decimal("13070.11"))
        self.assertEqual(parsed.metadata["closing_balance"], Decimal("13119.11"))
        self.assertEqual(len(parsed.rows), 1)
        self.assertEqual(parsed.rows[0]["amount"], 49)
        self.assertEqual(parsed.rows[0]["direction"], "credit")

    def test_sbi_consolidated_statement_only_imports_savings_account_rows(self):
        content = _pdf_bytes("""State Bank of India Consolidated Statement
Statement Period: 01/07/2026 to 31/07/2026
Account Type: REGULAR SB
01/07/2026 UPI GROCERY STORE 500.00 9,500.00
02/07/2026 SALARY CREDIT 5,000.00 CR 14,500.00
Account Type: DEMAND LOAN (DL)
03/07/2026 LOAN DISBURSEMENT 50,000.00 CR 50,000.00
04/07/2026 LOAN REPAYMENT 2,000.00 48,000.00
Account Type: TERM LOAN (TL)
05/07/2026 TERM LOAN INTEREST 700.00 47,300.00""")

        parsed = parse_pdf_statement("sbi-consolidated-statement.pdf", content, None)

        self.assertEqual(parsed.parser_name, "sbi_bank_pdf")
        self.assertEqual(len(parsed.rows), 2)
        self.assertEqual(
            [row["narration"] for row in parsed.rows],
            ["UPI GROCERY STORE", "SALARY CREDIT"],
        )
        self.assertEqual(parsed.metadata["closing_balance"], 14500)

    def test_sbi_dl_and_tl_sections_before_savings_are_ignored(self):
        content = _pdf_bytes("""STATE BANK OF INDIA
DL Account
01/07/2026 DEMAND LOAN REPAYMENT 1,000.00 20,000.00
TL Account
02/07/2026 TERM LOAN INTEREST 500.00 19,500.00
Savings Bank Account
03/07/2026 UPI MERCHANT 250.00 8,750.00""")

        parsed = parse_pdf_statement("sbi-statement.pdf", content, None)

        self.assertEqual(len(parsed.rows), 1)
        self.assertEqual(parsed.rows[0]["narration"], "UPI MERCHANT")
        self.assertEqual(parsed.metadata["closing_balance"], 8750)

    def test_sbi_relationship_summary_excludes_combined_dl_tl_account(self):
        content = _pdf_bytes("""STATE BANK OF INDIA Relationship Summary
As on 30-06-26
SAVING ACCOUNT
XXXXXXX1234
Your Opening Balance on 01-06-26: 60,994.38
25-06-26 INTEREST CREDIT 378.00 0.00 61,372.38
28-06-26 NEFT SAMPLE TRANSFER 1,000.00 0.00 62,372.38
Your Closing Balance on 30-06-26: 62,372.38
DL/TL ACCOUNT
XXXXXXX5678
Your Opening Balance on 01-06-26: 42,063.91
15-06-26 INTEREST REPAYMENT GL TO LOANS 358.00 0.00 41,705.91
15-06-26 PRINCIPAL REPAYMENT GL TO LOAN 11,098.00 0.00 30,607.91
30-06-26 INTEREST 0.00 266.00 30,873.91
Your Closing Balance on 30-06-26: 30,873.91""")

        parsed = parse_pdf_statement("sbi-relationship-summary.pdf", content, None)

        self.assertEqual(parsed.parser_name, "sbi_bank_pdf")
        self.assertEqual(len(parsed.rows), 2)
        self.assertEqual(
            [row["narration"] for row in parsed.rows],
            ["INTEREST CREDIT", "NEFT SAMPLE TRANSFER"],
        )
        self.assertEqual([row["direction"] for row in parsed.rows], ["credit", "credit"])
        self.assertEqual(parsed.metadata["opening_balance"], Decimal("60994.38"))
        self.assertEqual(parsed.metadata["closing_balance"], Decimal("62372.38"))
