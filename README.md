# Arcis

**Know where your money goes. Understand what to do next.**

Arcis is an AI-powered personal finance tracker designed to consolidate bank
accounts and credit cards into one trustworthy, read-only financial workspace.
It collects transaction evidence from connected Gmail accounts and uploaded
statements, normalizes it into a canonical ledger, reconciles duplicates, and
turns the result into useful reports and grounded financial insights.

The project is currently in the planning and architecture phase. It is being
built for personal use first, while keeping the data model and security
boundaries ready for future multi-user support.

## What Arcis will do

- Connect multiple Gmail accounts through OAuth.
- Synchronize bank and credit-card transaction alerts daily or on demand.
- Import PDF, CSV, and XLSX statements.
- Reconcile email transactions with monthly statements.
- Detect missing, duplicate, reversed, refunded, and unusual transactions.
- Categorize spending and normalize merchants such as `SWIGGY` and
  `WWW.SWIGGY.IN` into one merchant.
- Track account balances as dated observations rather than pretending they are
  always current.
- Track credit-card statement amounts, minimum dues, due dates, and payment
  status.
- Identify transfers, card payments, subscriptions, recurring expenses, and
  potential anomalies.
- Generate monthly spending summaries, forecasts, and savings opportunities.
- Answer questions through a conversational assistant backed by safe,
  predefined analytics tools.

## Example use cases

### Understand spending

See current-month expenses, income, net cash flow, category breakdowns,
merchant-wise spending, and comparisons with previous months.

### Consolidate accounts and cards

View transactions from HDFC, ICICI, SBI, DBS, Axis, Union Bank, and supported
credit cards in one ledger without treating separate cards from the same bank
as the same account.

### Reconcile a monthly statement

Upload a statement or let Arcis find one in Gmail. Review which transactions
match, which are new, which appear duplicated, and which need manual review
before confirming the import.

### Avoid double-counting transfers

Link a bank debit to an owned-account transfer or credit-card payment so it is
visible in cash flow without being counted as a second expense.

### Track upcoming card payments

See statement amounts, minimum amounts due, due dates, payment status, and
upcoming reminders for each credit card.

### Find recurring commitments

Detect subscriptions, rent, utility bills, insurance premiums, EMIs, SIPs, and
other regular payments based on merchant, amount, and timing patterns.

### Ask natural-language questions

Examples:

- “How much did I spend on food this month?”
- “Compare restaurant expenses for the last six months.”
- “Show transactions above ₹10,000.”
- “Which subscriptions are due next week?”
- “Which transactions are not confirmed by a statement?”

The assistant will use allow-listed analytics functions. It will not generate
or execute unrestricted SQL, and it will not invent totals or anomalies.

## Initial supported accounts

Bank accounts:

- HDFC Bank
- ICICI Bank
- State Bank of India
- DBS Bank
- Axis Bank
- Union Bank of India

Credit cards:

- ICICI Credit Card
- Amazon Pay ICICI Credit Card
- Kiwi Credit Card — YES Bank
- OneCard — Federal Bank
- HDFC Swiggy Credit Card
- Scapia Travel Credit Card — Federal Bank

The first adapter rollout will focus on ICICI bank/card products and HDFC
bank/card products before expanding institution by institution.

## Safety and privacy

Arcis is strictly read-only. It will never initiate a bank transfer, card
payment, trade, or money movement.

The design includes:

- Gmail OAuth instead of Gmail passwords.
- Encrypted OAuth refresh tokens.
- Masked account and card identifiers.
- No passwords, tokens, complete documents, or raw email bodies in logs.
- Encrypted artifact storage with explicit retention and deletion workflows.
- Evidence links for ledger entries and AI-generated claims.
- Deterministic validation before AI-assisted categorization or explanations.
- User ownership checks on every API query and background job.
- Review queues for uncertain parsing, matching, and categorization decisions.

## Planned architecture

Arcis is planned as a modular monolith with clear domain boundaries:

```text
Next.js + TypeScript frontend
          ↓
FastAPI modular backend
          ↓
PostgreSQL — canonical ledger and application state
          ↔
Redis + Celery — jobs, scheduling, locks, and cache
          ↓
Gmail, statement parsers, analytics, and AI services
```

The system separates immutable source evidence from canonical transactions.
That allows parser reprocessing, safe deduplication, reconciliation, audit
history, and reproducible reports.

Planned technologies include Next.js, FastAPI, PostgreSQL, SQLAlchemy, Alembic,
Celery, Redis, Gmail API, PyMuPDF, pandas, openpyxl, OpenAI structured outputs,
embeddings, tool calling, pytest, Vitest, Playwright, Docker Compose, and AWS
managed services for production learning.

## Project status and documentation

Implementation has not started yet. The project is currently defining its
contracts, security boundaries, feasibility checks, and delivery sequence.

- [Project plan](docs/PLAN.md) — product scope, MVP boundary, phases, risks,
  success criteria, and execution protocol.
- [Technical architecture](docs/ARCHITECTURE.md) — database model, API
  contracts, ingestion workflows, workers, security, deployment, testing, and
  recovery behavior.

The first usable release will prioritize a trustworthy monthly-close workflow:
manual statement import, accurate categorization, reconciliation, reporting,
and then Gmail automation and AI features.

## Development

Copy `.env.example` to `.env`, then start the local infrastructure:

```bash
docker compose -f deploy/compose/docker-compose.yml up -d
```

Run the API locally:

```bash
python3 -m pip install -e '.[dev]'
python3 -m alembic upgrade head
python3 -m uvicorn apps.api.main:app --reload --port 8000
```

Run the web application in a second terminal:

```bash
cd apps/web
npm ci
npm run dev
```

Run the dependency-free test suite:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The local stack exposes the web app on port `3000`, the API on port `8000`,
PostgreSQL on `5432`, Redis on `6379`, and the S3-compatible MinIO service on
`9000` with its console on `9001`.

## License

License information will be added before implementation and distribution.
