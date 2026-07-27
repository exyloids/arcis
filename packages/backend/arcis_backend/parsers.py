"""Institution-specific email adapters that emit normalized transaction candidates."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from email import policy
from email.parser import BytesParser
from html import unescape


class ParserError(ValueError):
    """A message is unsupported or cannot be safely normalized."""


def parse_icici_alert(raw_message: bytes) -> dict[str, object]:
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    sender = str(message.get("From", "")).lower()
    if "icicibank.com" not in sender:
        raise ParserError("Message sender is not an ICICI alert sender")
    text = _message_text(message)
    account = re.search(r"account (XX\d{4}).*?debited by INR ([\d,.]+) on (\d{2}-[A-Za-z]{3}-\d{4}) for\s*(.+?)\. Reference number: ([\w-]+)", text, re.I | re.S)
    card = re.search(r"Credit Card ending (\d{4}).*?INR ([\d,.]+) on\s*(\d{2}-[A-Za-z]{3}-\d{4}) at (.+?)\. Reference number: ([\w-]+)", text, re.I | re.S)
    transfer = re.search(r"iMobile transfer of INR ([\d,.]+).*?account (XX\d{4}) on\s*(\d{2}-[A-Za-z]{3}-\d{4}) to (.+?)\. Reference number: ([\w-]+)", text, re.I | re.S)
    debit_card = re.search(r"purchase of Rs\.\s*([\d,.]+).*?linked to ICICI Bank Account\s+([\w*]+)\s+on\s+(\d{2}-[A-Za-z]{3}-\d{2,4})\.\s*Info:\s*(.+?)\.\s*The Available Balance", text, re.I | re.S)
    credit_card = re.search(r"ICICI Bank Credit Card\s+([\w*]+)\s+has been used for a transaction of INR\s*([\d,.]+)\s+on\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+at.*?Info:\s*(.+?)\.\s*The Available Credit Limit", text, re.I | re.S)
    net_banking = re.search(r"online payment of INR\s*([\d,.]+)\s+towards\s+(.+?)\s+from your Account\s+([\w*]+)\s+on\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+at.*?Transaction ID is\s+([\w-]+)", text, re.I | re.S)
    match = account or card or transfer
    if match is not None:
        groups = match.groups()
        if transfer:
            amount, identifier, date_text, merchant, reference = groups
        else:
            identifier, amount, date_text, merchant, reference = groups
        parsed = _transaction(
            "bank_account" if account or transfer else "credit_card", identifier, amount, date_text,
            merchant, reference, "%d-%b-%Y",
        )
        if transfer:
            parsed["transaction_kind"] = "transfer"
        return parsed
    if debit_card:
        amount, identifier, date_text, merchant = debit_card.groups()
        return _transaction("bank_account", identifier, amount, date_text, merchant, f"icici-debit-{date_text}-{amount}", "%d-%b-%y")
    if credit_card:
        identifier, amount, date_text, merchant = credit_card.groups()
        return _transaction("credit_card", identifier, amount, date_text, merchant, f"icici-card-{date_text}-{amount}", "%b %d, %Y")
    if net_banking:
        amount, merchant, identifier, date_text, reference = net_banking.groups()
        return _transaction("bank_account", identifier, amount, date_text, merchant, reference, "%b %d, %Y")
    raise ParserError("Unsupported ICICI transaction alert format")


def parse_hdfc_alert(raw_message: bytes) -> dict[str, object]:
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    if "hdfcbank.com" not in str(message.get("From", "")).lower():
        raise ParserError("Message sender is not an HDFC alert sender")
    text = _message_text(message)
    match = re.search(r"Account (XX\d{4}) was debited by INR ([\d,.]+) on\s*(\d{2}-[A-Za-z]{3}-\d{4})\. Paid to (.+?)\. UTR: ([\w-]+)", text, re.I | re.S)
    if match is None:
        raise ParserError("Unsupported HDFC transaction alert format")
    identifier, amount, date_text, merchant, reference = match.groups()
    return {"financial_account_hint": f"bank_account_ending_{identifier.removeprefix('XX')}",
            "transaction_date": datetime.strptime(date_text, "%d-%b-%Y").date().isoformat(),
            "amount": str(Decimal(amount.replace(",", ""))), "currency": "INR", "direction": "debit",
            "merchant": merchant.strip(), "provider_reference": reference, "source_kind": "gmail_message"}


def parse_supported_alert(raw_message: bytes) -> dict[str, object]:
    sender = BytesParser(policy=policy.default).parsebytes(raw_message).get("From", "").lower()
    if "icicibank.com" in sender:
        return parse_icici_alert(raw_message)
    if "hdfcbank.com" in sender:
        return parse_hdfc_alert(raw_message)
    raise ParserError("Unsupported email sender")


def _message_text(message: object) -> str:
    body = message.get_body(preferencelist=("plain", "html"))
    value = body.get_content() if body else ""
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value)))


def _transaction(account_type: str, identifier: str, amount: str, date_text: str, merchant: str, reference: str, date_format: str) -> dict[str, object]:
    ending = re.sub(r"\D", "", identifier)[-4:]
    if len(ending) != 4:
        raise ParserError("ICICI alert did not contain a usable account identifier")
    return {
        "financial_account_hint": f"{account_type}_ending_{ending}",
        "transaction_date": datetime.strptime(date_text, date_format).date().isoformat(),
        "amount": str(Decimal(amount.replace(",", ""))),
        "currency": "INR", "direction": "debit",
        "merchant": re.sub(r"^UPI payment to\s+", "", merchant.strip(), flags=re.I),
        "provider_reference": reference, "source_kind": "gmail_message",
    }
