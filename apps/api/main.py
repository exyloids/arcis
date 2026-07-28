import json
from datetime import UTC, datetime
from uuid import UUID

from arcis_backend import __version__
from arcis_backend.candidates import CandidateService
from arcis_backend.celery_app import celery_app
from arcis_backend.gmail_artifacts import GmailArtifactRepository
from arcis_backend.gmail_oauth import GmailOAuthError, GmailOAuthService
from arcis_backend.ledger import LedgerError, LedgerService, database_engine, inspect_tabular_upload
from arcis_backend.mailboxes import CredentialCipher, MailboxError, MailboxService
from arcis_backend.settings import get_settings
from arcis_backend.statements import StatementService
from arcis_backend.storage import MinioArtifactStorage
from arcis_backend.sync_jobs import GmailSyncJobService, SyncJobError
from arcis_contracts.health import HealthResponse, ReadinessResponse
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

settings = get_settings()
app = FastAPI(
    title="Arcis API",
    version=__version__,
    description="Read-only personal finance tracker API",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type"],
)

ledger = LedgerService(
    database_engine(settings.database_url),
    settings.demo_user_id,
    MinioArtifactStorage(
        settings.object_storage_endpoint,
        settings.object_storage_access_key,
        settings.object_storage_secret_key,
        settings.object_storage_bucket,
    ),
)
mailboxes = MailboxService(
    database_engine(settings.database_url),
    settings.demo_user_id,
    CredentialCipher(settings.credential_encryption_key_version, settings.credential_encryption_key),
)
sync_jobs = GmailSyncJobService(database_engine(settings.database_url), settings.demo_user_id)
gmail_artifacts = GmailArtifactRepository(
    database_engine(settings.database_url), settings.demo_user_id,
    MinioArtifactStorage(settings.object_storage_endpoint, settings.object_storage_access_key,
                         settings.object_storage_secret_key, settings.object_storage_bucket),
)
candidates = CandidateService(database_engine(settings.database_url), settings.demo_user_id)
gmail_oauth = GmailOAuthService(
    database_engine(settings.database_url), settings.demo_user_id, mailboxes,
    settings.gmail_oauth_client_id, settings.gmail_oauth_client_secret, settings.gmail_oauth_redirect_uri,
)
statements = StatementService(
    database_engine(settings.database_url), settings.demo_user_id,
    MinioArtifactStorage(settings.object_storage_endpoint, settings.object_storage_access_key,
                         settings.object_storage_secret_key, settings.object_storage_bucket),
)


@app.on_event("startup")
def initialize_ledger() -> None:
    ledger.initialize_user()


def ledger_error(error: LedgerError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))


def mailbox_error(error: MailboxError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))


def sync_job_error(error: SyncJobError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))


def gmail_oauth_error(error: GmailOAuthError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))


@app.get("/health", response_model=HealthResponse, tags=["operations"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="api",
        version=__version__,
        checked_at=datetime.now(UTC),
    )


@app.get("/ready", response_model=ReadinessResponse, tags=["operations"])
def readiness() -> ReadinessResponse:
    # Dependency probes are introduced with the first database/worker slice.
    # The endpoint is explicit so orchestration can distinguish liveness from
    # readiness without treating an unimplemented probe as healthy.
    return ReadinessResponse(
        status="starting",
        service="api",
        version=__version__,
        dependencies={"database": "not_checked", "redis": "not_checked"},
        checked_at=datetime.now(UTC),
    )


@app.get("/api/v1/financial-accounts", tags=["accounts"])
def list_accounts() -> list[dict[str, object]]:
    return ledger.list_accounts()


@app.post("/api/v1/financial-accounts", status_code=201, tags=["accounts"])
def create_account(payload: dict[str, object]) -> dict[str, object]:
    try:
        return ledger.create_account(payload)
    except LedgerError as error:
        raise ledger_error(error) from error


@app.get("/api/v1/categories", tags=["categories"])
def list_categories() -> list[dict[str, object]]:
    return ledger.list_categories()


@app.get("/api/v1/merchant-rules", tags=["categories"])
def list_merchant_rules() -> list[dict[str, object]]:
    return ledger.list_merchant_rules()


@app.post("/api/v1/merchant-rules", status_code=201, tags=["categories"])
def create_merchant_rule(payload: dict[str, object]) -> dict[str, object]:
    try:
        return ledger.create_merchant_rule(payload)
    except (LedgerError, ValueError) as error:
        raise ledger_error(LedgerError(str(error))) from error


@app.post("/api/v1/merchant-rules/apply", tags=["categories"])
def apply_merchant_rules() -> dict[str, int]:
    return ledger.apply_merchant_rules()


@app.post("/api/v1/categories/apply-builtins", tags=["categories"])
def apply_builtin_categories() -> dict[str, int]:
    return ledger.apply_builtin_categories()


@app.post("/api/v1/categories/categorize", tags=["categories"])
def categorize_transactions() -> dict[str, int]:
    return ledger.categorize_transactions()


@app.post("/api/v1/recurring-payments/detect", tags=["insights"])
def detect_recurring_payments() -> dict[str, int]:
    return ledger.detect_recurring_payments()


@app.get("/api/v1/recurring-payments", tags=["insights"])
def list_recurring_payments(state: str | None = Query(default=None, pattern=r"^(detected|confirmed|dismissed)$")) -> list[dict[str, object]]:
    return ledger.list_recurring_payments(state)


@app.post("/api/v1/recurring-payments/{detection_id}/review", tags=["insights"])
def review_recurring_payment(detection_id: UUID, payload: dict[str, str]) -> dict[str, object]:
    try:
        return ledger.review_recurring_payment(detection_id, payload.get("state", ""))
    except LedgerError as error:
        raise ledger_error(error) from error


@app.get("/api/v1/accounts/balance-summary", tags=["accounts"])
def account_balance_summary() -> dict[str, object]:
    return ledger.balance_summary()


@app.get("/api/v1/parser-candidates", tags=["mailboxes"])
def list_parser_candidates(state: str | None = None) -> list[dict[str, object]]:
    return candidates.list(state)


@app.get("/api/v1/parser-candidates/metrics", tags=["mailboxes"])
def parser_candidate_metrics() -> list[dict[str, object]]:
    return candidates.metrics()


@app.post("/api/v1/parser-candidates/{candidate_id}/review", tags=["mailboxes"])
def review_parser_candidate(candidate_id: UUID, payload: dict[str, str]) -> dict[str, object]:
    try:
        return candidates.review(candidate_id, payload.get("state", ""))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.patch("/api/v1/parser-candidates/{candidate_id}/account", tags=["mailboxes"])
def assign_parser_candidate_account(candidate_id: UUID, payload: dict[str, str]) -> dict[str, object]:
    try:
        return candidates.assign_account(candidate_id, UUID(payload.get("financial_account_id", "")))
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/v1/oauth/gmail/start", tags=["mailboxes"])
def start_gmail_oauth() -> RedirectResponse:
    try:
        return RedirectResponse(gmail_oauth.start(), status_code=302)
    except GmailOAuthError as error:
        raise gmail_oauth_error(error) from error


@app.get("/api/v1/oauth/gmail/callback", tags=["mailboxes"])
def complete_gmail_oauth(code: str, state: str) -> RedirectResponse:
    try:
        gmail_oauth.complete(code, state)
        return RedirectResponse("http://localhost:3000/?gmail=connected", status_code=302)
    except GmailOAuthError as error:
        raise gmail_oauth_error(error) from error


@app.get("/api/v1/mailboxes", tags=["mailboxes"])
def list_mailboxes() -> list[dict[str, object]]:
    return mailboxes.list_mailboxes()


@app.post("/api/v1/mailboxes/gmail", status_code=201, tags=["mailboxes"])
def save_gmail_mailbox(payload: dict[str, object]) -> dict[str, object]:
    try:
        scopes = payload.get("granted_scopes", [])
        if not isinstance(scopes, list) or not all(isinstance(scope, str) for scope in scopes):
            raise MailboxError("granted_scopes must be a list of strings")
        return mailboxes.save_gmail_connection(
            str(payload.get("provider_subject", "")), str(payload.get("display_email", "")), scopes,
            str(payload.get("refresh_token", "")),
        )
    except MailboxError as error:
        raise mailbox_error(error) from error


@app.post("/api/v1/mailboxes/{mailbox_id}/disconnect", status_code=204, tags=["mailboxes"])
def disconnect_mailbox(mailbox_id: UUID) -> None:
    try:
        mailboxes.disconnect_mailbox(mailbox_id)
    except MailboxError as error:
        raise mailbox_error(error) from error


@app.post("/api/v1/mailboxes/{mailbox_id}/sync", status_code=202, tags=["mailboxes"])
def request_mailbox_sync(mailbox_id: UUID) -> dict[str, object]:
    try:
        job = sync_jobs.request_sync(mailbox_id)
        # The database job is the source of truth; Celery only receives a
        # lightweight wake-up task that claims the next queued job.
        celery_app.send_task("arcis.gmail.run_next")
        return job
    except SyncJobError as error:
        raise sync_job_error(error) from error


@app.post("/api/v1/mailboxes/{mailbox_id}/backfill", tags=["mailboxes"])
def backfill_mailbox(mailbox_id: UUID, payload: dict[str, object]) -> dict[str, int]:
    try:
        return sync_jobs.backfill(
            mailbox_id, str(payload.get("query", "")), mailboxes, gmail_oauth, gmail_artifacts, candidates,
            int(payload.get("max_results", 500)),
        )
    except (SyncJobError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/v1/sync-jobs/{job_id}", tags=["mailboxes"])
def get_sync_job(job_id: UUID) -> dict[str, object]:
    try:
        return sync_jobs.get_job(job_id)
    except SyncJobError as error:
        raise sync_job_error(error) from error


@app.get("/api/v1/mailboxes/{mailbox_id}/sync-history", tags=["mailboxes"])
def mailbox_sync_history(mailbox_id: UUID, limit: int = 25) -> list[dict[str, object]]:
    return sync_jobs.history(mailbox_id, limit)


@app.post("/api/v1/sync-jobs/run-next", tags=["mailboxes"])
def run_next_sync_job() -> dict[str, object] | None:
    try:
        return sync_jobs.run_next(mailboxes, gmail_oauth, gmail_artifacts, candidates)
    except SyncJobError as error:
        raise sync_job_error(error) from error


@app.post("/api/v1/categories", status_code=201, tags=["categories"])
def create_category(payload: dict[str, object]) -> dict[str, object]:
    try:
        return ledger.create_category(payload)
    except LedgerError as error:
        raise ledger_error(error) from error


@app.post("/api/v1/imports", status_code=201, tags=["imports"])
async def create_import(
    account_id: UUID,
    file: UploadFile = File(...),
    column_mapping: str | None = Form(default=None),
    pdf_password: str | None = Form(default=None),
) -> dict[str, object]:
    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise LedgerError("Statement uploads must not exceed 10 MiB")
        filename = file.filename or "statement.csv"
        if filename.lower().endswith(".pdf"):
            return statements.stage_pdf(account_id, filename, content, pdf_password)
        if not filename.lower().endswith((".csv", ".xlsx")):
            raise LedgerError("Only CSV, XLSX, and PDF statement imports are supported")
        try:
            mapping = json.loads(column_mapping) if column_mapping else None
        except json.JSONDecodeError as error:
            raise LedgerError("Column mapping is not valid JSON") from error
        if mapping is not None and not isinstance(mapping, dict):
            raise LedgerError("Column mapping must be a JSON object")
        return ledger.stage_import(account_id, filename, content, mapping)
    except LedgerError as error:
        raise ledger_error(error) from error


@app.post("/api/v1/imports/inspect", tags=["imports"])
async def inspect_import(file: UploadFile = File(...)) -> dict[str, object]:
    try:
        return inspect_tabular_upload(file.filename or "statement.csv", await file.read())
    except LedgerError as error:
        raise ledger_error(error) from error


@app.get("/api/v1/imports/{import_id}/preview", tags=["imports"])
def preview_import(import_id: UUID) -> dict[str, object]:
    try:
        return statements.preview(import_id) if statements.has_statement(import_id) else ledger.import_preview(import_id)
    except LedgerError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/v1/imports/{import_id}", tags=["imports"])
def get_import(import_id: UUID) -> dict[str, object]:
    try:
        return statements.preview(import_id) if statements.has_statement(import_id) else ledger.import_preview(import_id)
    except LedgerError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/v1/imports/{import_id}/confirm", tags=["imports"])
def confirm_import(import_id: UUID) -> dict[str, int]:
    try:
        result = statements.confirm(import_id) if statements.has_statement(import_id) else ledger.confirm_import(import_id)
        categorized = ledger.categorize_transactions()
        return {**result, "categorized": categorized["transactions_updated"]}
    except LedgerError as error:
        raise ledger_error(error) from error


@app.get("/api/v1/reconciliation-reviews", tags=["imports"])
def list_reconciliation_reviews(state: str = "needs_review") -> list[dict[str, object]]:
    try:
        return statements.reviews(state)
    except LedgerError as error:
        raise ledger_error(error) from error


@app.get("/api/v1/statement-attachments", tags=["imports"])
def list_statement_attachments() -> list[dict[str, object]]:
    return statements.gmail_attachments()


@app.post("/api/v1/statement-attachments/{artifact_id}/preview", tags=["imports"])
def preview_statement_attachment(artifact_id: UUID, account_id: UUID, payload: dict[str, str]) -> dict[str, object]:
    try:
        return statements.stage_gmail_attachment(artifact_id, account_id, payload.get("pdf_password"))
    except LedgerError as error:
        raise ledger_error(error) from error


@app.post("/api/v1/reconciliation-reviews/{review_id}", tags=["imports"])
def resolve_reconciliation_review(review_id: UUID, payload: dict[str, str]) -> dict[str, object]:
    try:
        return statements.review(review_id, payload.get("state", ""))
    except LedgerError as error:
        raise ledger_error(error) from error


@app.get("/api/v1/imports", tags=["imports"])
def list_imports() -> list[dict[str, object]]:
    return ledger.list_imports()


@app.post("/api/v1/imports/{import_id}/cancel", status_code=204, tags=["imports"])
def cancel_import(import_id: UUID) -> None:
    try:
        ledger.cancel_import(import_id)
    except LedgerError as error:
        raise ledger_error(error) from error


@app.get("/api/v1/transactions", tags=["ledger"])
def list_transactions(
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    account_id: UUID | None = None,
    account_type: str | None = Query(default=None, pattern=r"^(bank_account|credit_card)$"),
    category_id: UUID | None = None,
    q: str | None = Query(default=None, min_length=1, max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict[str, object]]:
    return ledger.list_transactions(
        month=month, account_id=account_id, account_type=account_type, category_id=category_id, query_text=q, limit=limit
    )


@app.get("/api/v1/transactions/page", tags=["ledger"])
def transaction_page(
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    account_id: UUID | None = None,
    account_type: str | None = Query(default=None, pattern=r"^(bank_account|credit_card)$"),
    category_id: UUID | None = None,
    q: str | None = Query(default=None, min_length=1, max_length=100),
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    try:
        return ledger.transaction_page(
            month=month,
            account_id=account_id,
            account_type=account_type,
            category_id=category_id,
            query_text=q,
            cursor=cursor,
            limit=limit,
        )
    except LedgerError as error:
        raise ledger_error(error) from error


@app.get("/api/v1/transactions/{transaction_id}/evidence", tags=["ledger"])
def get_transaction_evidence(transaction_id: UUID) -> list[dict[str, object]]:
    return ledger.transaction_evidence(transaction_id)


@app.patch("/api/v1/transactions/{transaction_id}", tags=["ledger"])
def update_transaction(transaction_id: UUID, payload: dict[str, object]) -> dict[str, object]:
    try:
        return ledger.update_transaction(transaction_id, payload)
    except LedgerError as error:
        raise ledger_error(error) from error


@app.get("/api/v1/reports/monthly", tags=["analytics"])
def monthly_report(month: str = Query(pattern=r"^\d{4}-\d{2}$")) -> dict[str, object]:
    return ledger.monthly_report(month)


@app.get("/api/v1/insights/monthly", tags=["insights"])
def monthly_insights(month: str = Query(pattern=r"^\d{4}-\d{2}$")) -> dict[str, object]:
    return ledger.monthly_insights(month)
