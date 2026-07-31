# Financial email format notes

This document records privacy-safe structural findings used by Arcis email
adapters. It must not contain copied email bodies, subjects, names, transaction
amounts, addresses, account/card endings, customer IDs, or reference numbers.

## Corpus reviewed

The local development review covered 392 RFC 822 email files and 49 statement
PDFs. Raw samples remain outside the repository. Most email bodies are HTML;
adapters must therefore handle both HTML-only and multipart messages.

The highest-volume trusted bank sender domains observed were:

- HDFC: `hdfcbank.bank.in`, `hdfcbank.net`, and legacy `hdfcbank.com`
- ICICI: `icicibank.com` and `icici.bank.in`, including their subdomains
- YES BANK: `yes.bank.in`, including its subdomains
- SBI: `sbi.bank.in`, including its subdomains
- DCB: `dcbbank.com`, including its subdomains
- OneCard: `getonecard.app`, including its subdomains

Sender matching uses an exact registered bank domain or one of its subdomains.
A string merely containing a bank domain is not trusted.

## Observed transaction template families

### HDFC

- Debit and credit alerts can say `account`, `account ending`, or
  `Bank Account Number`.
- Amounts commonly use `Rs` rather than `INR`.
- Dates occur in both numeric and abbreviated-month formats.
- UPI alerts may include a VPA and a transaction reference number.
- Current messages may be sent from `hdfcbank.bank.in` or `hdfcbank.net`;
  limiting discovery to `hdfcbank.com` misses valid products.

### ICICI

- Credit-card alerts commonly identify a masked card immediately before
  wording such as `has been used for a transaction`.
- Credit-card payment confirmations may use `Credit Card Account` before the
  masked card token. The word `Account` in this phrase still describes a card
  and must not create a savings-account product.
- A declined transaction still provides evidence that a card exists, but it
  must never create a ledger transaction.
- Savings-account alerts may say `online payment ... from your savings
  account`, without using the word `debited`.
- Debit-card alerts may also name the linked bank account. The linked account
  identifier is usable; the debit-card identifier is not a bank-account
  identifier.
- Current messages may arrive from `icicibank.com`, `icici.bank.in`, or their
  subdomains.

### YES BANK

- Card alerts commonly use `spent on your ... Credit Card ending with`.
- Some non-transaction instructions also mention the last four card digits.
  Discovery therefore requires a monetary amount and a concrete transaction
  event, not identifier wording alone.

### SBI and DCB

- Account credits may use `A/C` or `Account Number`.
- Numeric date formats and UTR/reference fields are common.

### OneCard

- Messages from `getonecard.app` were present, but the reviewed mailbox set
  contained promotional communications without a reliable masked card
  identity or posted-transaction event.
- Arcis must not create a card from sender presence alone. Until an identity is
  available from a transaction alert or supported statement, the card requires
  explicit user confirmation/manual creation.

## Product identity rules

Product discovery follows these deterministic rules:

1. Trust only an allowlisted institution sender domain or its subdomain.
2. Require both a monetary amount and a concrete transaction event.
3. Require account/card context around the identifier.
4. Prefer explicit `ending`, `ends with`, or masked/full account/card tokens.
5. Always retain only the final four digits of a matched token.
6. Never use `starting` or first digits as the product identity.
7. Never treat a customer ID as a bank-account identifier.
8. Never treat debit-card ending digits as a bank-account identifier.
9. Keep bank accounts and credit cards as different product types even when
   their final four digits happen to match.
10. Leave ambiguous messages unsupported for review instead of guessing.

These rules apply only to product discovery. A message can prove a product
exists without representing a posted transaction. Ledger ingestion continues
to require a supported institution-specific transaction parser.

Observed HDFC UPI, ICICI online savings payment, YES BANK card purchase, SBI
NEFT credit, and DCB debit/credit alerts have deterministic transaction
adapters. Other layouts remain quarantined until covered by synthetic
regression tests.

## Test-data policy

Regression tests use synthetic senders, identifiers, amounts, merchants, and
references. Real local samples are used only for private aggregate validation.
No raw financial email or statement data is committed.
