# Arcis status

## Current phase

Phase 5 — Everyday controls, trust, and polish

## Current task

Gmail-first account and card discovery is implemented. A connected mailbox can
be scanned asynchronously for supported institution alerts; detected products
must be confirmed before accounts or transactions are created. Rejected
products remain suppressed for future matching alerts and can be reconsidered.
The remaining Phase 5 work is full user/account erasure and final real-data
visual sign-off. The user-facing Documents section has been removed; source
files remain private implementation evidence governed through privacy controls.

## Actionable notifications and statement-confirmed balances

- The app now has a dedicated Notifications destination and an unread badge in
  the global header. Completed Gmail jobs create a concise scan-result
  notification.
- Gmail PDF attachments are inspected for supported savings-account statement
  signals. Arcis keeps one actionable notification for the most recent
  statement per institution and avoids routing recognized credit-card
  statements into the savings-balance workflow.
- Opening the notification asks the user to select the savings account when it
  cannot be inferred safely and to confirm the PDF password. Arcis derives a
  safe instruction such as “Use your Customer ID” from the source email, but
  never copies an explicit password, customer ID, account number, or other
  credential value. The entered password is sent only to the preview operation.
- After the user reviews and confirms the preview, the existing reconciliation
  pipeline records the statement baseline and recalculates the available bank
  balance from the closing balance plus newer activity.
- The former Documents page and the long manual Gmail-attachment picker were
  removed. Uploaded and emailed files remain internal evidence with retention
  and recovery controls.
- SBI consolidated statements now use account-type boundaries before parsing.
  Only Savings/SB/SBCHQ sections contribute transactions or the closing-balance
  baseline; Demand Loan, Term Loan, DL, and TL sections are ignored.

## Vendor category propagation and statement-backed balances

- Transactions now persist a parent category and optional subcategory
  independently. Selecting a subcategory also selects its parent, and ledger
  labels render as `Category (Subcategory)`.
- The tagging dialog provides live category/subcategory search, highlights the
  selected child, ranks categories by transaction relevance and historical
  usage, and exposes the five most-used categories as quick choices.
- Category usage counts are user-scoped. Merchant overrides and confirmed bulk
  propagation preserve both category levels.
- A manual transaction category now creates or updates the highest-priority
  normalized merchant override, so later Gmail and statement transactions from
  the same vendor receive the category deterministically.
- After the selected transaction is saved, the UI reports the exact number of
  other uncategorized transactions with the same normalized merchant and asks
  before applying the category in bulk. Existing categorized transactions are
  never overwritten by this action.
- The UI requests a fresh match preview after the category save instead of
  relying on fields in the update response. This also makes propagation
  recoverable by reopening and saving an already categorized transaction.
  Real-data verification detected all 10 older uncategorized transactions for
  a recurring vendor whose narration varied only by punctuation.
- Gmail synchronization stores PDF attachments privately and raises an
  actionable notification for the most recent supported savings statement.
  The account selector and ephemeral PDF-password field are shown only when the
  user opens that notification.
- Savings balances no longer assume that an account started at zero. Arcis uses
  the latest confirmed statement closing balance and rolls it forward with
  transactions dated after the statement period. Without a confirmed baseline,
  the account is labelled **Balance unavailable** and excluded from the
  confirmed bank-balance total instead of showing a misleading negative value.
- Bank-statement parsing now extracts statement-period ranges and can derive the
  closing balance from the final running-balance column when no labelled
  closing-balance field is present.

Verification completed on 2026-07-30:

```bash
.venv/bin/ruff check apps/api/main.py packages/backend/arcis_backend/ledger.py \
  packages/backend/arcis_backend/statements.py tests/test_pdf_statement_parser.py \
  tests/integration/test_manual_ledger_postgres.py
.venv/bin/python -m unittest tests.test_pdf_statement_parser -v
ARCIS_INTEGRATION_DATABASE_URL=postgresql+psycopg://arcis:arcis@localhost:5432/arcis \
  .venv/bin/python -m unittest \
  tests.integration.test_manual_ledger_postgres.ManualLedgerPostgresTests.test_bank_balance_requires_a_statement_baseline_and_rolls_forward_newer_activity \
  tests.integration.test_manual_ledger_postgres.ManualLedgerPostgresTests.test_manual_category_can_be_confirmed_for_uncategorized_vendor_matches -v
(cd apps/web && npm run build)
```

Result: Ruff passed; 81 runnable/default tests passed with 15 opt-in integration
tests skipped; both selected PostgreSQL integration tests passed; the Next.js
production build passed; and all 12 desktop/tablet/mobile browser journeys
passed, including the vendor-match confirmation flow.

## Gmail-first product onboarding

- Added durable `pending`, `confirmed`, and `rejected` financial-product
  discoveries, keyed per user by institution, account type, and last four.
- Added a Celery-backed bounded Gmail discovery job so historical scanning does
  not hold an HTTP request open.
- Pending candidates are quarantined from the canonical ledger. Confirmation
  creates the account and imports all linked alerts; future alerts materialize
  automatically.
- Product identity detection is independent of complete transaction parsing.
  Explicit HDFC/ICICI account or card context can therefore create a pending
  product suggestion while an unsupported alert remains quarantined.
- Rejection suppresses current and future matching alerts. **Review again**
  explicitly returns the product to pending.
- The Mailboxes page now presents detected products with editable product name,
  display name, and currency. Manual account creation remains a fallback.
- Confirmed accounts and cards can be edited or removed from their respective
  pages. Removal archives the product, suppresses future linked Gmail alerts,
  and retains accepted history for audit and historical reporting.
- Added unit and PostgreSQL lifecycle coverage for detection identity,
  independent discovery-job idempotency, rejection persistence, confirmation,
  and transaction gating.
- Reviewed 392 locally downloaded RFC 822 messages without copying personal
  financial content into the repository. Discovery now recognizes current
  HDFC, ICICI, YES BANK, SBI, DCB, and OneCard sender domains and HTML-only
  bodies.
- Product matching requires a monetary amount, a concrete transaction event,
  and explicit account/card context. It retains only ending four digits and
  rejects starting digits, customer IDs, debit-card-only identifiers, sender
  suffix spoofing, and instructional messages that merely mention last-four
  digits.
- Private aggregate validation against user-supplied product ground truth
  matched every product for which a supported top-level email body was present.
  One supplied card appeared only inside forwarded/nested content and one
  supplied savings account had no decoded email-body evidence in the reviewed
  corpus, so neither is guessed.

Verification completed on 2026-07-30:

```bash
.venv/bin/ruff check apps packages migrations scripts spikes tests
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
ARCIS_INTEGRATION_DATABASE_URL=postgresql+psycopg://arcis:arcis@localhost:5432/arcis \
  .venv/bin/python -m unittest \
  tests.integration.test_account_discovery_postgres \
  tests.integration.test_sync_jobs_postgres -v
```

Result: lint passed; 74 runnable tests passed with 13 opt-in tests skipped by
the default suite; all five selected PostgreSQL discovery and job tests passed.

Real-mailbox verification on 2026-07-30 reprocessed 908 matching messages
without duplicating source artifacts. The corrected detector surfaced both an
HDFC savings account and ICICI savings-account candidates as pending products;
no newly detected product was confirmed automatically.

The follow-up verification passed Ruff, 60 runnable unit/default tests, eight
selected PostgreSQL discovery/account-lifecycle tests, and the Next.js
production build. All 12 desktop/tablet/mobile browser journeys passed.
Thirteen opt-in integration tests were skipped by the default suite as
expected.

Verification completed on 2026-07-29:

```bash
.venv/bin/ruff check apps packages migrations scripts spikes tests
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
ARCIS_INTEGRATION_DATABASE_URL=postgresql+psycopg://arcis:arcis@localhost:5432/arcis \
  .venv/bin/python -m unittest \
  tests.integration.test_account_discovery_postgres \
  tests.integration.test_sync_jobs_postgres -v
(cd apps/web && npm run build)
(cd apps/web && npm run test:e2e)
docker-compose -f deploy/compose/docker-compose.yml exec -T api alembic current
```

Result: lint passed; 56 runnable tests passed with 11 opt-in integration tests
skipped in the default suite; all four selected PostgreSQL lifecycle/job tests
passed; the Next.js production build and all nine desktop/tablet/mobile browser
journeys passed; and Alembic reached `0015_gmail_account_discovery`.

## Phase 5 everyday controls

- Reporting periods are defined once and persisted in PostgreSQL preferences.
  Home, Transactions, reports, budgets, and relevant insights use the selected
  calendar-aligned period.
- Monthly category budgets show spent, remaining, utilization, and
  over-budget state.
- Recurring commitments have detected, confirmed, dismissed, restored, and
  editable states, with next-date and monthly/annual commitment totals.
- Credit-card statements expose amount, minimum due, due date, payment status,
  and idempotent upcoming/overdue in-app reminders.
- Manual uploads and Gmail artifacts remain internal source evidence rather
  than a user-facing document browser. Deletion moves bytes to a private
  recovery key for 30 days; restore copies bytes back to the original key.
- Privacy controls provide a safe metadata/ledger export, Gmail disconnect,
  per-source deletion and restoration, configurable retention, immediate
  enforcement, and daily scheduled enforcement. Full account erasure remains
  open as `PRIVACY-001`.
- Dialogs now contain keyboard focus, close with Escape, return focus after
  closing, prevent background scrolling, and expose labelled dialog roles.
- The release suite adds deterministic Playwright journeys at desktop, tablet,
  and mobile viewport sizes. Existing unit and opt-in PostgreSQL integration
  suites continue to cover imports, duplicates, reconciliation, Gmail
  recovery, and parser behavior.
- `/ready` now probes PostgreSQL and Redis instead of returning placeholder
  dependency states.
- Patched PostCSS and Sharp versions are enforced through npm overrides; the
  production dependency audit reports zero vulnerabilities.

Verification completed on 2026-07-29:

```bash
.venv/bin/ruff check apps packages migrations scripts spikes tests
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
(cd apps/web && npm run build)
(cd apps/web && npm run test:e2e)
(cd apps/web && npm audit --omit=dev)
docker-compose -f deploy/compose/docker-compose.yml exec -T api alembic current
curl -fsS http://localhost:8000/api/v1/privacy/inventory
curl -fsS -X POST http://localhost:8000/api/v1/privacy/retention/enforce
```

Result: lint passed; 62 tests passed with 9 opt-in PostgreSQL tests skipped;
the production web build passed; all six desktop/tablet/mobile browser journeys
passed; npm reported zero production dependency vulnerabilities; Alembic
reached `0014_document_retention_recovery`; and retention enforcement reported
zero currently expired files.

The recovery workflow was exercised against rejected Gmail artifact
`1514883a-89b0-4f20-864f-544cfa81adbf`. It entered a recoverable deletion
state with a 30-day purge date and was immediately restored with its original
20,658-byte size. No user artifact was left deleted.

## Product-improvement backlog adopted

The following improvements were promoted into the delivery ledger after a
comparison with an external personal-finance product specification:

- consistent reporting-period semantics;
- recurring/subscription review and dismissal management;
- a safe document-vault experience;
- user export, deletion, retention, and restore controls;
- explicit accessibility/responsive quality gates; and
- a release-verification suite for critical financial workflows.

The architecture already contains the underlying privacy, retention, export,
and test boundaries. `NEXT.md` now tracks the missing product work as ordered
Phase 5 tasks; no external-platform or simplified-storage design was adopted.

## Home review refinements in progress

- Home now renders a dashboard loading state while its financial data is being
  retrieved. It no longer briefly presents a zero balance or empty cards as if
  they were confirmed financial facts.
- The cash-flow summary labels now explicitly say that incoming and outgoing
  values are for the current month. Card outstanding remains a separate live
  balance, consistent with the savings-account-only total balance rule.
- Real-data review is still open: verify information hierarchy, content
  density, and mobile interaction after regular use with imported statements.

Verification completed on 2026-07-29:

```bash
(cd apps/web && npm run build)
```

Result: the Next.js production build passed.

## Spending analytics page

- Added a dedicated **Spending** item in the primary navigation and changed the
  Home-card action from a recent-transactions link to **View spending**.
- The page groups all available debit transactions at the parent-category
  level, shows total category spend and percentage in an interactive SVG donut
  and selectable breakdown, and displays the selected category across its
  complete monthly or yearly history.
- Hovering a trend point shows its exact period and amount. The page has no
  date-picker filter: the category graph always represents all available data.
- Transfers and credit-card bill-payment records are excluded from this expense
  analysis to prevent credit-card purchases and their subsequent bank payment
  from being counted twice.
- Added analytics endpoints for the monthly category summary and a selected
  category's monthly/yearly trend.

Verification completed on 2026-07-29:

```bash
.venv/bin/ruff check apps/api/main.py packages/backend/arcis_backend/ledger.py
(cd apps/web && npm run build)
curl -fsS "http://localhost:8000/api/v1/spending/summary"
curl -fsS "http://localhost:8000/api/v1/spending/categories/<CATEGORY_ID>/trend?granularity=monthly"
```

Result: lint and production build passed. The local API returned category
percentages and a complete category trend series.

## Phase 4 monthly insights

- Added deterministic monthly spending forecasts that extrapolate observed
  eligible debit spend to the end of the selected calendar month.
- Added evidence-linked anomaly facts for unusually large transactions and
  category spending spikes versus the prior month. Each result includes the
  supporting transaction or category calculation; no LLM is used to invent a
  conclusion.
- Added the Home-screen Monthly insights card, which presents the forecast and
  the top evidence-linked findings.

Verification completed on 2026-07-28:

```bash
.venv/bin/ruff check apps/api/main.py packages/backend/arcis_backend/ledger.py
(cd apps/web && npm run build)
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
curl -fsS http://localhost:8000/health
```

Result: lint passed; frontend production build passed; 57 tests passed with 9
optional PostgreSQL integration tests skipped; API health returned `status: ok`.

## Phase 4 recurring-payment detection

- Added deterministic recurring-payment detection for consistent weekly,
  monthly, quarterly, and yearly debit patterns. It requires at least three
  occurrences, bounded amount variation, and excludes transfers and credit-card
  bill payments.
- Detections are persisted as reviewable records with a predicted next date,
  cadence, typical amount, confidence, and detected/confirmed/dismissed state.
- The Home screen includes an Upcoming recurring payments card. **Scan** runs
  detection; each candidate can be confirmed or dismissed without changing the
  underlying ledger transaction.

Verification completed on 2026-07-28:

```bash
.venv/bin/ruff check apps/api/main.py packages/backend/arcis_backend/ledger.py \
  migrations/versions/0012_recurring_payment_detection.py tests/test_recurring_payments.py
.venv/bin/python -m unittest discover -s tests -p 'test_recurring_payments.py' -v
(cd apps/web && npm run build)
docker-compose -f deploy/compose/docker-compose.yml exec -T api alembic upgrade head
curl -fsS http://localhost:8000/health
```

Result: lint passed; three cadence tests passed; the production web build
passed; Alembic applied `0012_recurring_payment_detection`; API health returned
`status: ok`.

The manual-ledger milestone is complete. Real Gmail-provider validation remains
an external configuration gate, requiring two configured Google test mailboxes.

## UI visual foundation

- Replaced the single operational page with a dark, card-based, responsive
  interface inspired by the supplied finance-app references while retaining an
  original Arcis design and no third-party branding.
- Added focused Home, Transactions, Accounts, Credit cards, Imports, and
  Mailboxes views. Desktop uses a sidebar; mobile uses a scrollable top
  navigation so every workflow remains reachable.
- Home now prioritizes total bank balance, current-month cash flow, separate
  credit-card outstanding, spending categories, accounts, cards, recent
  transactions, and mailbox connection state.
- Transactions use touch-friendly cards on all screen sizes and retain filters,
  categorization, evidence access, and transaction detail controls.
- Replaced the transaction category dropdown with a dedicated Tag transaction
  sheet. It presents parent categories as groups and selectable subcategories
  as icon tiles, while transaction cards show only the parent category name.
- All existing import, reconciliation, Gmail, and account-management actions
  remain available in their dedicated views. No backend API or data-model
  boundary changed in this UI milestone.

Verification completed on 2026-07-28:

```bash
(cd apps/web && npm run build)
docker-compose -f deploy/compose/docker-compose.yml build web
docker-compose -f deploy/compose/docker-compose.yml up -d web
curl -fsS http://localhost:3000/
```

Result: the Next.js production build passed and the web container served the
application with the API container healthy.

## Phase 4 initial categorization

- Categories now support parent/child taxonomy, including the user-defined
  Transport, Food & Drinks, Shopping, and supporting finance categories.
- Every transaction view presents its source account, date, merchant, incoming
  or outgoing direction, amount, narration, transaction ID, and reference/UTR
  when provided by the source.
- Deterministic categorization evaluates user overrides, exact merchant rules,
  MCC rules, then ordered keyword rules. Manual category choices are protected
  from later automated recategorization.
- Built-in mappings for common merchants are seeded as keyword rules. Statement
  confirmation runs categorization automatically; the ledger also exposes a
  user-visible **Categorize transactions** action for existing records.
- A user can choose a category from a transaction's details and remember that
  merchant choice. This creates a highest-priority user override with full
  confidence for matching normalized merchant text.

Verification completed on 2026-07-28:

```bash
.venv/bin/ruff check apps packages migrations tests
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
(cd apps/web && npm run build)
docker-compose -f deploy/compose/docker-compose.yml run --rm api alembic upgrade head
docker-compose -f deploy/compose/docker-compose.yml up -d api web
curl -fsS http://localhost:8000/health
curl -fsS -X POST http://localhost:8000/api/v1/categories/categorize
```

Result: lint passed; 54 tests passed (9 optional PostgreSQL integration tests
skipped without `ARCIS_INTEGRATION_DATABASE_URL`); the Next.js production build
passed; Alembic reached `0011_category_rules`; API health returned `status: ok`;
and the live categorization endpoint applied the seeded deterministic rules.

## Phase 3 completion

- Manual PDF statement uploads now create a reviewable preview before they can
  affect the canonical ledger. The original document is held in private object
  storage and imports are idempotent per account and document hash.
- Password-protected PDFs are parsed in a bounded child process. The password
  travels only over the request body and child-process standard input; it is
  never persisted, logged, placed in a job payload, or passed on a command line.
- Gmail ingestion saves PDF attachments as separate private artifacts. The web
  app exposes them as account-scoped statement previews, with the optional
  password supplied only at preview time.
- Initial deterministic ICICI/HDFC PDF recognition extracts transaction rows
  and common balance/card fields. Unsupported or non-text PDFs fail closed;
  OCR remains a later adapter rather than silently inventing rows.
- Confirmation reconciles exact account/direction/amount/date or reference
  matches automatically, preserves evidence, creates statement-only rows for
  transactions missed by email alerts, and sends less certain matches to a
  user decision queue. Rejecting the final candidate creates a statement-only
  row, so no statement transaction is discarded.

Verification completed on 2026-07-28:

```bash
.venv/bin/ruff check apps packages migrations tests
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
(cd apps/web && npm run build)
docker-compose -f deploy/compose/docker-compose.yml up --build -d api worker web
docker-compose -f deploy/compose/docker-compose.yml exec -T api alembic current
curl -fsS http://localhost:8000/health
```

Result: lint passed; 48 unit tests passed (9 database integration tests
skipped without a database URL); the Next.js production build passed; the
runtime migration was `0008_statements_reconciliation` at that milestone; and
the API health endpoint returned `status: ok`.

## GMAIL-001 evidence

- Added application mailbox APIs to list Gmail mailboxes, persist a completed
  Gmail connection, and disconnect/revoke a mailbox credential.
- Added `arcis_backend.mailboxes` with AES-256-GCM encryption. Credential
  associated data binds each secret to its user, mailbox, and Gmail provider.
- Refresh tokens are ciphertext-only in `oauth_credentials`; list and save
  responses never include them. Reconnecting the same Google subject replaces
  the encrypted secret and clears revocation; disconnecting revokes it.
- Mailboxes retain their independent `history_cursor` field for the upcoming
  synchronization workflow.

Verification completed on 2026-07-27: 46 generic tests passed (9 integration
tests skipped without a database URL), the dedicated PostgreSQL suite passed
9/9, and the Next.js production build passed.

## Phase 2 completion

- Added Gmail OAuth with durable PKCE state, encrypted refresh-token storage,
  mailbox-local History cursors, and disconnect/revocation controls.
- Added queued Sync Now jobs, worker-safe claims, Celery worker/Beat services,
  daily scheduling, bounded historical search, and mailbox sync history.
- Gmail History ingestion stores idempotent raw message artifacts in MinIO;
  cursors advance only after all retrieved messages persist successfully.
- Added ICICI account/card/iMobile and HDFC UPI adapters, candidate review,
  parser metrics, and evidence-preserving acceptance into canonical ledger
  transactions.

## Phase 1 — Trustworthy manual ledger

- Implemented user-owned financial accounts, categories, statement imports,
  immutable source artifacts and source records, canonical transactions, and
  transaction-to-evidence links.
- CSV/XLSX imports support header inspection, suggested or explicit mappings,
  bounded file parsing, row-level validation messages, preview, confirmation,
  cancellation, and idempotent replay for the same account and content.
- The ledger supports account, category, month, and narration filters; manual
  category corrections; evidence inspection; and opaque keyset pagination.
- Import classification keeps salary-like credits as income and identifies
  transfers, card payments, cash withdrawals, refunds, and expenses so card
  bill payments do not become duplicate spending.
- Monthly reporting aggregates income, expenses, and category totals from
  canonical transactions.

Verification completed on 2026-07-27:

```bash
.venv/bin/ruff check apps packages migrations scripts spikes tests
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
make test-integration
(cd apps/web && npm run build)
```

Result: lint passed; 38 unit tests passed (5 database tests are skipped by
the generic suite); the dedicated PostgreSQL integration suite passed 5/5;
and the Next.js production build passed.

The deterministic two-mailbox proof is complete. The remaining foundation
gate needs two Google test mailboxes and a locally configured Google OAuth
client; no credentials should be committed or shared in this repository.

## FOUNDATION-003B implementation in progress

- Added `spikes/gmail_provider_validation/gmail_provider_validation.py`, a
  real Google OAuth and Gmail History API adapter using authorization-code
  flow with PKCE, read-only scope, refresh-token exchange, and paginated
  message-added discovery.
- Added tests in `tests/gmail_provider_validation/` for PKCE/state, token
  exchange, refresh behavior, secret redaction, pagination, de-duplication,
  cursor advance, and explicit invalid-history handling.
- Added `spikes/gmail_provider_validation/run_live_validation.py`, an
  interactive local-only validator that holds credentials in process memory
  and prints no codes or tokens.
- Added the setup and evidence procedure in `docs/GMAIL_TESTING.md`.

The task remains open until the live procedure succeeds for the configured
test mailboxes and the safe results are recorded below.

## FOUNDATION-007 implementation in progress

- Added `scripts/catalog_samples.py`, which creates a local-only structural
  catalog of `.eml` and PDF samples without emitting message content, subjects,
  addresses, attachment names, or PDF text.
- Added `fixtures/sanitized/README.md` with the fixture redaction and expected
  result policy.
- Added `example_transactions/` to `.gitignore` because it holds raw local
  financial documents.
- Added synthetic ICICI/HDFC alert and structured-statement fixtures with
  expected normalized transaction records. These establish the committed
  baseline; template-specific fixture expansion follows local review of each
  raw source format.

Result: the local catalog reports 20 email samples and 10 statement samples;
the committed baseline contains four synthetic email fixtures, two structured
statement fixtures, and matching normalized expectations. Fixture-policy tests
passed on 2026-07-24.

## FOUNDATION-001 evidence

- Fixture: `fixtures/sanitized/icici_bank_statement.csv`
- Proof: `spikes/statement_replay/statement_replay.py`
- Tests: `tests/statement_replay/test_statement_replay.py`
- First import: 1 artifact, 3 source records, 3 canonical transactions.
- Replay: 0 new artifacts, 0 new source records, 0 new transactions, 3 duplicates ignored.
- Artifact idempotency is scoped to `(user_id, account_id, content_sha256)`.

Verification commands:

```bash
python3 spikes/statement_replay/statement_replay.py
python3 -m unittest tests.statement_replay.test_statement_replay -v
```

Result: 4 tests passed on 2026-07-24.

## FOUNDATION-002 implementation

- Added Python project metadata in `pyproject.toml`.
- Added FastAPI health/readiness scaffold in `apps/api/`.
- Added Next.js web shell in `apps/web/`.
- Added shared health contracts in `packages/contracts/`.
- Added Alembic configuration and initial PostgreSQL migration.
- Added Docker Compose services for PostgreSQL, Redis, MinIO, API, and web.
- Added `.env.example`, `.gitignore`, `Makefile`, Dockerfiles, and CI workflow.
- Added scaffold tests in `tests/scaffold/`.

Verification:

- Created the project virtual environment at `.venv` and installed the
  development dependencies from `pyproject.toml`.
- Installed Node.js and generated the committed web dependency lockfile.
- Added `.dockerignore` so the API image build has a bounded, production-like
  context.
- Corrected Alembic runtime configuration to read `ARCIS_DATABASE_URL` inside
  the Compose API container.

Verification completed on 2026-07-24:

```bash
.venv/bin/ruff check apps packages migrations scripts spikes tests
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
.venv/bin/python scripts/generate_client.py --check
.venv/bin/python -m pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/arcis-wheel .
(cd apps/web && npm run build)
docker-compose -f deploy/compose/docker-compose.yml config
docker-compose -f deploy/compose/docker-compose.yml up --build -d
docker-compose -f deploy/compose/docker-compose.yml exec -T api alembic upgrade head
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready
curl -fsS http://localhost:3000/
docker-compose -f deploy/compose/docker-compose.yml exec -T redis redis-cli ping
```

Results: lint passed; 17 unit tests passed; generated-client drift check
passed; wheel build passed; Next.js production build passed; Compose
configuration and service startup passed; migration `0001_initial` applied;
API health/readiness endpoints responded; web returned HTML; Redis returned
`PONG`; PostgreSQL and MinIO were healthy; MinIO initialized the
`arcis-local` bucket.

## FOUNDATION-003A evidence

- Proof: `spikes/gmail_sync/gmail_sync.py`
- Tests: `tests/gmail_sync/test_gmail_sync.py`
- Two mailbox-local cursors and artifact sets were verified.
- Incremental synchronization fetched only newly added messages.
- Invalid cursor recovery scanned a bounded overlap and ignored already stored
  provider message IDs.

Result: 3 tests passed on 2026-07-24.

Real Gmail OAuth is intentionally not claimed. FOUNDATION-003B requires
configured Google test mailboxes and local OAuth credentials.

## FOUNDATION-004 evidence

- Proof: `spikes/credential_security/credential_security.py`
- Tests: `tests/credential_security/test_credential_security.py`
- Uses versioned AES-GCM keys with associated data bound to the credential
  owner and provider.
- SQLite proof storage contains ciphertext and key version only; it never
  stores the plaintext refresh token.
- Tests cover encryption/decryption, wrong-owner rejection, rotation to a new
  key, retirement of the old key, and credential revocation.

Result: 5 tests passed on 2026-07-24.

## FOUNDATION-005 evidence

- Proof: `spikes/document_security/document_security.py`
- Tests: `tests/document_security/test_document_security.py`
- A synthetic encrypted document is processed by an isolated subprocess.
- Its temporary password is supplied on standard input only, never through the
  command line, environment, stored artifact, or telemetry.
- Tests cover successful processing and rejection of an incorrect password.

Result: 2 tests passed on 2026-07-24.

## FOUNDATION-006 evidence

- Proof: `spikes/job_recovery/job_recovery.py`
- Tests: `tests/job_recovery/test_job_recovery.py`
- A durable SQLite job proof commits each item independently. After a simulated
  worker crash, the retry skips committed work and completes the remaining
  item without duplicate side effects.
- OpenAPI contract: `packages/contracts/spec/openapi.json`
- Generator: `scripts/generate_client.py`
- Generated client: `apps/web/lib/generated/api-client.ts`
- The generated-client drift check is part of the verified foundation suite.

Result: 3 tests passed on 2026-07-24.
