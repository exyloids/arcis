# Arcis implementation ledger

Read `docs/PLAN.md`, `docs/ARCHITECTURE.md`, and `docs/STATUS.md` before
starting work. Complete tasks in order and record evidence in `STATUS.md`.

## Foundation — feasibility and delivery baseline

- [x] **FOUNDATION-001** Parse and replay a sanitized ICICI-style statement without creating duplicate canonical transactions.
- [x] **FOUNDATION-002** Verify the repository scaffold, local services, migrations, API health, web build, and CI baseline.
- [x] **FOUNDATION-003A** Prove two-mailbox synchronization mechanics, incremental history, and cursor recovery with a deterministic provider.
- [ ] **FOUNDATION-003B** Prove real two-mailbox Gmail OAuth, token refresh, and provider pagination with configured test mailboxes.
- [x] **FOUNDATION-004** Prove encrypted credential lifecycle and key rotation.
- [x] **FOUNDATION-005** Prove protected-document processing without password persistence or telemetry leakage.
- [x] **FOUNDATION-006** Prove interrupted-job retry and OpenAPI client contract generation.
- [x] **FOUNDATION-007** Build a local sample catalog and sanitized golden fixture corpus for the initial ICICI and HDFC email and statement templates.

## Phase 1 — Trustworthy manual ledger

- [x] **LEDGER-001** Implement production contracts, migrations, accounts, artifacts, and source records.
- [x] **LEDGER-002** Implement CSV/XLSX upload, mapping, preview, and confirmation.
- [x] **LEDGER-003** Implement transaction ledger, evidence links, categories, and corrections.
- [x] **LEDGER-004** Implement duplicate detection, transfers, card payments, and monthly reporting.

## Phase 2 — Gmail automation

- [x] **GMAIL-001** Persist Gmail mailbox connections, encrypted OAuth credentials, and mailbox-local synchronization cursors in the application backend.
- [x] **GMAIL-002** Implement the asynchronous Gmail synchronization workflow, including Sync Now, incremental history retrieval, idempotent source-artifact persistence, and recoverable job state.
- [x] **GMAIL-003** Implement the initial ICICI transaction-alert adapter using sanitized fixtures and a parser-review queue for unsupported messages.
- [x] **GMAIL-004** Implement the initial HDFC transaction-alert adapter, parser metrics, and safe failure reporting.
- [x] **GMAIL-005** Add scheduled mailbox synchronization and user-visible run history after on-demand synchronization is reliable.

## Update protocol

1. Keep task IDs stable and descriptive.
2. Mark a task complete only after implementation and tests pass.
3. Record commands, outputs, fixture names, and deviations in `STATUS.md`.
4. Add an ADR before changing a locked boundary or durable contract.
