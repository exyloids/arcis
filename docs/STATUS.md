# Arcis status

## Current phase

Foundation — feasibility and delivery baseline

## Current task

FOUNDATION-003B — Real Gmail-provider validation

The deterministic two-mailbox proof is complete. The remaining foundation
gate needs two Google test mailboxes and a locally configured Google OAuth
client; no credentials should be committed or shared in this repository.

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
