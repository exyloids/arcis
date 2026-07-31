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
- [x] **GMAIL-006** Discover bank accounts and credit cards from Gmail alerts,
  require product-level confirmation before ledger materialization, and
  persist rejected-product decisions so future matching alerts are skipped.

## Phase 3 — Statements and reconciliation

- [x] **STATEMENT-001** Implement private PDF statement staging, preview, and confirmation for manual uploads.
- [x] **STATEMENT-002** Detect and stage PDF statement attachments discovered during Gmail synchronization.
- [x] **STATEMENT-003** Extract initial ICICI/HDFC statement rows and statement/card metadata through versioned deterministic parsers.
- [x] **RECONCILIATION-001** Match statement rows to canonical transactions, retain evidence, and create statement-only transactions for missed alerts.
- [x] **RECONCILIATION-002** Provide a review queue for uncertain matches, including explicit accept/reject decisions without data loss.

## Next milestone — Phase 4 intelligence

- [x] **INTELLIGENCE-001** Define merchant normalization rules and a correction-backed merchant vocabulary.
- [x] **INTELLIGENCE-002** Add deterministic category rules, confidence scores, and correction-backed user overrides.
- [x] **INTELLIGENCE-005** Ask before propagating a manual category to existing
  uncategorized transactions from the same normalized vendor, while retaining
  the vendor override for future detections.
- [x] **INTELLIGENCE-006** Persist parent categories and subcategories
  independently, with searchable and usage-ranked transaction tagging.
- [x] **INTELLIGENCE-003** Implement recurring-payment and subscription detection from canonical transactions.
- [x] **INTELLIGENCE-004** Add evidence-linked anomaly detection and monthly spending forecasts.

## Product experience

- [x] **UX-001** Establish the responsive Arcis visual system and separate the
  operational page into Home, Transactions, Accounts, Cards, Imports, and
  Mailboxes views.
- [ ] **UX-002** Review the deployed Home screen with real data and refine
  information hierarchy, copy, density, and mobile interaction details.

## Phase 5 — Everyday controls, trust, and polish

- [x] **ANALYTICS-001** Define and implement shared reporting-period semantics
  across Home, Transactions, Spending, Budgets, and Insights, including
  a server-side per-user persisted preference.
- [x] **BUDGETS-001** Implement monthly category budgets with spent, remaining,
  utilization, over-budget state, and budget-versus-actual views on Home and
  Spending.
- [x] **RECURRING-001** Provide a dedicated recurring and subscription
  management experience with confirm, dismiss, restore-dismissed, edit, next
  date, and monthly/annual commitment views.
- [x] **REMINDERS-001** Track credit-card statement amount, minimum due, due
  date, and payment status, with idempotent upcoming and overdue reminders.
- [x] **ACCOUNTS-001** Let users edit confirmed account/card details and
  archive products safely while retaining history and suppressing future
  Gmail alerts for removed discoveries.
- [x] **BALANCES-001** Base savings balances on the latest confirmed statement
  closing balance plus newer activity; mark accounts without a baseline as
  unavailable and provide a notification-led Gmail-statement password workflow.
- [x] **NOTIFICATIONS-001** Add an in-app notification center for Gmail scan
  completion, statement password confirmation, and payment reminders.
- [x] **SOURCE-RETENTION-001** Keep uploaded and Gmail-detected source files
  internal, with safe storage, parser/review status, and
  source metadata without exposing sensitive raw content.
- [ ] **PRIVACY-001** Implement verified user export, mailbox/account/source
  deletion, retention controls, and an exercised restoration workflow.
- [x] **UX-003** Establish accessibility and responsive acceptance gates:
  keyboard-safe dialogs, visible focus, readable text, touch targets, and
  desktop/tablet/mobile visual regression coverage.
- [x] **RELEASE-001** Create a release verification suite covering imports,
  duplicate handling, reconciliation, Gmail sync recovery, categorization,
  recurring review, privacy controls, and critical browser journeys.

## Update protocol

1. Keep task IDs stable and descriptive.
2. Mark a task complete only after implementation and tests pass.
3. Record commands, outputs, fixture names, and deviations in `STATUS.md`.
4. Add an ADR before changing a locked boundary or durable contract.
