"""Institution-specific email adapters that emit normalized transaction candidates."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from hashlib import sha256
from html import unescape

INSTITUTION_SENDER_DOMAINS: dict[str, tuple[str, ...]] = {
    "hdfc": ("hdfcbank.bank.in", "hdfcbank.net", "hdfcbank.com"),
    "icici": ("icicibank.com", "icici.bank.in"),
    "yes": ("yes.bank.in",),
    "sbi": ("sbi.bank.in",),
    "citi": ("india.citi.com", "citicorp.com"),
    "dcb": ("dcbbank.com",),
    "onecard": ("getonecard.app",),
}


class ParserError(ValueError):
    """A message is unsupported or cannot be safely normalized."""


def parse_icici_alert(raw_message: bytes) -> dict[str, object]:
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    if _sender_institution(message) != "icici":
        raise ParserError("Message sender is not an ICICI alert sender")
    text = _message_text(message)
    account = re.search(r"account (XX\d{4}).*?debited by INR ([\d,.]+) on (\d{2}-[A-Za-z]{3}-\d{4}) for\s*(.+?)\. Reference number: ([\w-]+)", text, re.I | re.S)
    card = re.search(r"Credit Card ending (\d{4}).*?INR ([\d,.]+) on\s*(\d{2}-[A-Za-z]{3}-\d{4}) at (.+?)\. Reference number: ([\w-]+)", text, re.I | re.S)
    transfer = re.search(r"iMobile transfer of INR ([\d,.]+).*?account (XX\d{4}) on\s*(\d{2}-[A-Za-z]{3}-\d{4}) to (.+?)\. Reference number: ([\w-]+)", text, re.I | re.S)
    debit_card = re.search(r"purchase of Rs\.\s*([\d,.]+).*?linked to ICICI Bank Account\s+([\w*]+)\s+on\s+(\d{2}-[A-Za-z]{3}-\d{2,4})\.\s*Info:\s*(.+?)\.\s*The Available Balance", text, re.I | re.S)
    credit_card = re.search(r"ICICI Bank Credit Card\s+([\w*]+)\s+has been used for a transaction of INR\s*([\d,.]+)\s+on\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+at.*?Info:\s*(.+?)\.\s*The Available Credit Limit", text, re.I | re.S)
    net_banking = re.search(
        r"online(?:\s+\w+)?\s+payment\s+of\s+(?:INR|Rs\.?)\s*([\d,.]+)"
        r"\s+towards\s+(.+?)\s+on\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})"
        r".*?from\s+your\s+(?:ICICI\s+Bank\s+)?(?:Savings\s+)?Account"
        r"\s+([Xx*\d\s-]+?)\s*\.\s*The\s+transaction\s+ID\s+is\s+([\w-]+)",
        text,
        re.I | re.S,
    )
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
        amount, merchant, date_text, identifier, reference = net_banking.groups()
        return _transaction("bank_account", identifier, amount, date_text, merchant, reference, "%b %d, %Y")
    raise ParserError("Unsupported ICICI transaction alert format")


def parse_hdfc_alert(raw_message: bytes) -> dict[str, object]:
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    if _sender_institution(message) != "hdfc":
        raise ParserError("Message sender is not an HDFC alert sender")
    text = _message_text(message)
    legacy = re.search(r"Account (XX\d{4}) was debited by INR ([\d,.]+) on\s*(\d{2}-[A-Za-z]{3}-\d{4})\. Paid to (.+?)\. UTR: ([\w-]+)", text, re.I | re.S)
    if legacy:
        identifier, amount, date_text, merchant, reference = legacy.groups()
        return _transaction(
            "bank_account",
            identifier,
            amount,
            date_text,
            merchant,
            reference,
            "%d-%b-%Y",
        )

    ending_alert = re.search(
        r"Rs\.?\s*([\d,.]+)\s+is\s+(debited|credited)\s+"
        r"(?:from|to)\s+your\s+account\s+ending\s+([Xx*\d\s-]+?)\s+"
        r"(?:towards|from)\s+(.+?)\s+on\s+"
        r"(\d{1,2}[-/][A-Za-z0-9]{2,3}[-/]\d{2,4})"
        r".*?UPI\s+transaction\s+reference\s+(?:no\.?|number)"
        r"(?:\s+is)?\s*[:.-]?\s*([\w-]+)",
        text,
        re.I | re.S,
    )
    if ending_alert:
        amount, event, identifier, merchant, date_text, reference = (
            ending_alert.groups()
        )
        return _transaction_flexible_date(
            "bank_account",
            identifier,
            amount,
            date_text,
            merchant,
            reference,
            "credit" if event.lower() == "credited" else "debit",
        )

    account_alert = re.search(
        r"Rs\.?\s*([\d,.]+)\s+has\s+been\s+(debited|credited)\s+"
        r"(?:from|to)\s+(?:HDFC\s+Bank\s+)?(?:Account(?:\s+Number)?\s+)"
        r"([Xx*\d\s-]+?)\s+(?:to|towards|from)\s+(.+?)\s+on\s+"
        r"(\d{1,2}[-/][A-Za-z0-9]{2,3}[-/]\d{2,4})"
        r".*?(?:UPI\s+transaction\s+reference\s+(?:no\.?|number)"
        r"(?:\s+is)?\s*[:.-]?\s*([\w-]+))",
        text,
        re.I | re.S,
    )
    if account_alert:
        amount, event, identifier, merchant, date_text, reference = (
            account_alert.groups()
        )
        return _transaction_flexible_date(
            "bank_account",
            identifier,
            amount,
            date_text,
            merchant,
            reference,
            "credit" if event.lower() == "credited" else "debit",
        )
    raise ParserError("Unsupported HDFC transaction alert format")


def parse_yes_alert(raw_message: bytes) -> dict[str, object]:
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    if _sender_institution(message) != "yes":
        raise ParserError("Message sender is not a YES BANK alert sender")
    text = _message_text(message)
    match = re.search(
        r"INR\s*([\d,.]+)\s+has\s+been\s+spent\s+on\s+your\s+"
        r"YES\s+BANK\s+Credit\s+Card\s+ending\s+with\s+([Xx*\d\s-]+?)"
        r"\s+at\s+(.+?)\s+on\s+(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        text,
        re.I | re.S,
    )
    if match is None:
        raise ParserError("Unsupported YES BANK transaction alert format")
    amount, identifier, merchant, date_text = match.groups()
    return _transaction_flexible_date(
        "credit_card",
        identifier,
        amount,
        date_text,
        merchant,
        _stable_reference(raw_message, "yes-card"),
        "debit",
    )


def parse_sbi_alert(raw_message: bytes) -> dict[str, object]:
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    if _sender_institution(message) != "sbi":
        raise ParserError("Message sender is not an SBI alert sender")
    text = _message_text(message)
    match = re.search(
        r"credited\s+to\s+your\s+A\s*/\s*C\s*:\s*([Xx*\d\s-]+?)"
        r"\s+Amount\s*:\s*INR\s*([\d,.]+)\s+UTR\s+No\.?\s*:\s*([\w-]+)"
        r"\s+Date\s*:\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})",
        text,
        re.I | re.S,
    )
    if match is None:
        raise ParserError("Unsupported SBI transaction alert format")
    identifier, amount, reference, date_text = match.groups()
    return _transaction_flexible_date(
        "bank_account",
        identifier,
        amount,
        date_text,
        "NEFT credit",
        reference,
        "credit",
    )


def parse_dcb_alert(raw_message: bytes) -> dict[str, object]:
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    if _sender_institution(message) != "dcb":
        raise ParserError("Message sender is not a DCB alert sender")
    text = _message_text(message)
    match = re.search(
        r"Account\s+Number\s+([Xx*\d\s-]+?)\s+is\s+(credited|debited)"
        r"(?:\s+\w+){0,3}\s+INR\s*([\d,.]+)\s+on\s+"
        r"(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})",
        text,
        re.I | re.S,
    )
    if match is None:
        raise ParserError("Unsupported DCB transaction alert format")
    identifier, event, amount, date_text = match.groups()
    direction = "credit" if event.lower() == "credited" else "debit"
    return _transaction_flexible_date(
        "bank_account",
        identifier,
        amount,
        date_text,
        f"DCB account {direction}",
        _stable_reference(raw_message, f"dcb-{direction}"),
        direction,
    )


def parse_onecard_alert(raw_message: bytes) -> dict[str, object]:
    """Parse Federal Bank OneCard purchase alerts."""
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    if _sender_institution(message) != "onecard":
        raise ParserError("Message sender is not a OneCard alert sender")
    text = _message_text(message)
    match = re.search(
        r"(?:Federal\s+(?:Bank\s+)?One\s+)?Credit\s+Card\s+ending\s+in\s+"
        r"([Xx*\d\s-]+?)\s+was\s+used\s+to\s+make\s+a\s+payment\.\s*"
        r"Amount\s*:\s*INR\s*([\d,.]+)\s+Merchant\s*:\s*(.+?)\s+"
        r"Date\s*:\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        text,
        re.I | re.S,
    )
    if match is None:
        raise ParserError("Unsupported OneCard transaction alert format")
    identifier, amount, merchant, date_text = match.groups()
    return _transaction_flexible_date(
        "credit_card",
        identifier,
        amount,
        date_text,
        merchant,
        _stable_reference(raw_message, "onecard-payment"),
        "debit",
    )


def parse_supported_alert(raw_message: bytes) -> dict[str, object]:
    institution = institution_for_message(raw_message)
    if institution == "icici":
        return parse_icici_alert(raw_message)
    if institution == "hdfc":
        return parse_hdfc_alert(raw_message)
    if institution == "yes":
        return parse_yes_alert(raw_message)
    if institution == "sbi":
        return parse_sbi_alert(raw_message)
    if institution == "dcb":
        return parse_dcb_alert(raw_message)
    if institution == "onecard":
        return parse_onecard_alert(raw_message)
    if institution:
        raise ParserError(
            f"Unsupported {institution.upper()} transaction alert format"
        )
    raise ParserError("Unsupported or untrusted email sender")


def discover_financial_product(raw_message: bytes) -> tuple[str, dict[str, str]] | None:
    """Identify a bank account/card without requiring transaction normalization."""
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    institution = _sender_institution(message)
    if institution is None:
        return None

    text = _message_text(message)
    if not _looks_like_transaction_alert(text):
        return None

    card_identifier = _contextual_identifier(
        text,
        (
            r"\bCredit\s+Card\s+Account"
            r"(?:\s+(?:Number|No\.?))?\s*[:#-]?\s*"
            r"([Xx*\d][Xx*\d\s-]{2,40})",
            r"\bCredit\s+Card\b[^.\n]{0,60}?\b(?:ending|ends)"
            r"(?:\s+(?:with|in))?\s*[:#-]?\s*([Xx*\d][Xx*\d\s-]{2,40})",
            r"\bCard\s+(?:Number|No\.?)\b[^.\n]{0,30}?\b(?:ending|ends)"
            r"(?:\s+(?:with|in))?\s*[:#-]?\s*([Xx*\d][Xx*\d\s-]{2,40})",
            r"\b(?:ICICI\s+Bank\s+|YES\s+BANK\s+)?Credit\s+Card"
            r"(?:\s+(?:Number|No\.?))?\s*[:#-]?\s*"
            r"([Xx*\d][Xx*\d\s-]{2,40})",
        ),
    )
    if card_identifier:
        return institution, {
            "financial_account_hint": f"credit_card_ending_{card_identifier}",
            "currency": "INR",
        }

    account_identifier = _contextual_identifier(
        text,
        (
            r"(?<!Card\s)\b(?:Savings\s+|Current\s+|Bank\s+)?Account\b"
            r"[^.\n]{0,45}?\b(?:ending|ends)(?:\s+(?:with|in))?"
            r"\s*[:#-]?\s*([Xx*\d][Xx*\d\s-]{2,40})",
            r"\b(?:HDFC\s+Bank\s+|ICICI\s+Bank\s+)?"
            r"(?:Savings\s+|Current\s+)?(?<!Card\s)Account"
            r"(?:\s+(?:Number|No\.?))?\s*[:#-]?\s*"
            r"([Xx*\d][Xx*\d\s-]{2,40})",
            r"\bA\s*/\s*C(?:\s+(?:Number|No\.?|ending))?"
            r"\s*[:#-]?\s*([Xx*\d][Xx*\d\s-]{2,40})",
            r"\bAcct(?:\s+(?:Number|No\.?|ending))?"
            r"\s*[:#-]?\s*([Xx*\d][Xx*\d\s-]{2,40})",
        ),
    )
    if account_identifier:
        return institution, {
            "financial_account_hint": f"bank_account_ending_{account_identifier}",
            "currency": "INR",
        }
    return None


def institution_for_message(raw_message: bytes) -> str | None:
    """Return the trusted institution for an RFC 822 message sender."""
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    return _sender_institution(message)


def _contextual_identifier(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match is None:
            continue
        digits = re.sub(r"\D", "", match.group(1))
        ending = digits[-4:]
        if len(ending) == 4:
            return ending
    return None


def _sender_institution(message: object) -> str | None:
    addresses = getaddresses(message.get_all("From", []))
    domains = {
        address.rsplit("@", 1)[-1].strip().lower().rstrip(".")
        for _, address in addresses
        if "@" in address
    }
    for institution, allowed_domains in INSTITUTION_SENDER_DOMAINS.items():
        if any(
            domain == allowed or domain.endswith(f".{allowed}")
            for domain in domains
            for allowed in allowed_domains
        ):
            return institution
    return None


def _looks_like_transaction_alert(text: str) -> bool:
    has_amount = re.search(
        r"(?:\b(?:INR|Rs\.?)\s*[:.]?\s*[\d,]+(?:\.\d+)?|₹\s*[\d,]+)",
        text,
        re.I,
    )
    has_event = re.search(
        r"\b(?:debited|credited|spent|withdrawn|deposited|"
        r"payment\s+(?:of|received)|received\s+towards|purchase(?:d)?|"
        r"transaction\s+of|"
        r"used\s+for\s+(?:a\s+)?transaction|"
        r"used\s+to\s+make\s+(?:a\s+)?payment)\b",
        text,
        re.I,
    )
    return has_amount is not None and has_event is not None


def _message_text(message: object) -> str:
    # Some providers publish a literal `null` text/plain placeholder beside a
    # complete HTML body. Treat placeholders as absent instead of allowing
    # them to hide the usable MIME alternative.
    for content_type in ("plain", "html"):
        body = message.get_body(preferencelist=(content_type,))
        value = str(body.get_content()) if body else ""
        if not value.strip() or value.strip().lower() in {"null", "none"}:
            continue
        if content_type == "html":
            value = re.sub(r"<[^>]+>", " ", value)
        return re.sub(r"\s+", " ", unescape(value)).strip()
    return ""


def _transaction_flexible_date(
    account_type: str,
    identifier: str,
    amount: str,
    date_text: str,
    merchant: str,
    reference: str,
    direction: str,
) -> dict[str, object]:
    formats = (
        "%d-%m-%Y",
        "%d-%m-%y",
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d.%m.%Y",
        "%d.%m.%y",
        "%d-%b-%Y",
        "%d-%b-%y",
    )
    for date_format in formats:
        try:
            datetime.strptime(date_text, date_format)
        except ValueError:
            continue
        return _transaction(
            account_type,
            identifier,
            amount,
            date_text,
            merchant,
            reference,
            date_format,
            direction,
        )
    raise ParserError("Alert date format is unsupported")


def _stable_reference(raw_message: bytes, prefix: str) -> str:
    return f"{prefix}-{sha256(raw_message).hexdigest()[:24]}"


def _transaction(
    account_type: str,
    identifier: str,
    amount: str,
    date_text: str,
    merchant: str,
    reference: str,
    date_format: str,
    direction: str = "debit",
) -> dict[str, object]:
    ending = re.sub(r"\D", "", identifier)[-4:]
    if len(ending) != 4:
        raise ParserError("Alert did not contain a usable account identifier")
    return {
        "financial_account_hint": f"{account_type}_ending_{ending}",
        "transaction_date": datetime.strptime(date_text, date_format).date().isoformat(),
        "amount": str(Decimal(amount.replace(",", ""))),
        "currency": "INR", "direction": direction,
        "merchant": re.sub(r"^UPI payment to\s+", "", merchant.strip(), flags=re.I),
        "provider_reference": reference, "source_kind": "gmail_message",
    }
