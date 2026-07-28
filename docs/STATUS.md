# Arcis status

## Current phase

Phase 4 — Finance intelligence

## Current task

The initial Phase 4 intelligence milestone is complete. The next focus is Home
screen UX refinement using real data, followed by budgets and reminders.

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
