import json
from datetime import UTC, datetime
from uuid import UUID

from arcis_backend import __version__
from arcis_backend.gmail_oauth import GmailOAuthError, GmailOAuthService
from arcis_backend.ledger import LedgerError, LedgerService, database_engine, inspect_tabular_upload
from arcis_backend.mailboxes import CredentialCipher, MailboxError, MailboxService
from arcis_backend.settings import get_settings
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
gmail_oauth = GmailOAuthService(
    database_engine(settings.database_url), settings.demo_user_id, mailboxes,
    settings.gmail_oauth_client_id, settings.gmail_oauth_client_secret, settings.gmail_oauth_redirect_uri,
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
        return sync_jobs.request_sync(mailbox_id)
    except SyncJobError as error:
        raise sync_job_error(error) from error


@app.get("/api/v1/sync-jobs/{job_id}", tags=["mailboxes"])
def get_sync_job(job_id: UUID) -> dict[str, object]:
    try:
        return sync_jobs.get_job(job_id)
    except SyncJobError as error:
        raise sync_job_error(error) from error


@app.post("/api/v1/sync-jobs/run-next", tags=["mailboxes"])
def run_next_sync_job() -> dict[str, object] | None:
    try:
        return sync_jobs.run_next_baseline(mailboxes, gmail_oauth)
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
) -> dict[str, object]:
    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise LedgerError("Statement uploads must not exceed 10 MiB")
        filename = file.filename or "statement.csv"
        if not filename.lower().endswith((".csv", ".xlsx")):
            raise LedgerError("Only CSV and XLSX statement imports are supported")
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
        return ledger.import_preview(import_id)
    except LedgerError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/v1/imports/{import_id}", tags=["imports"])
def get_import(import_id: UUID) -> dict[str, object]:
    try:
        return ledger.import_preview(import_id)
    except LedgerError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/v1/imports/{import_id}/confirm", tags=["imports"])
def confirm_import(import_id: UUID) -> dict[str, int]:
    try:
        return ledger.confirm_import(import_id)
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
    category_id: UUID | None = None,
    q: str | None = Query(default=None, min_length=1, max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
) -> list[dict[str, object]]:
    return ledger.list_transactions(
        month=month, account_id=account_id, category_id=category_id, query_text=q, limit=limit
    )


@app.get("/api/v1/transactions/page", tags=["ledger"])
def transaction_page(
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    account_id: UUID | None = None,
    category_id: UUID | None = None,
    q: str | None = Query(default=None, min_length=1, max_length=100),
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    try:
        return ledger.transaction_page(
            month=month,
            account_id=account_id,
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
