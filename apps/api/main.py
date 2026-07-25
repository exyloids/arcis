from datetime import UTC, datetime
from uuid import UUID

from arcis_backend import __version__
from arcis_backend.ledger import LedgerError, LedgerService, database_engine
from arcis_backend.settings import get_settings
from arcis_contracts.health import HealthResponse, ReadinessResponse
from fastapi import FastAPI, File, HTTPException, Query, UploadFile

settings = get_settings()
app = FastAPI(
    title="Arcis API",
    version=__version__,
    description="Read-only personal finance tracker API",
)

ledger = LedgerService(database_engine(settings.database_url), settings.demo_user_id)


@app.on_event("startup")
def initialize_ledger() -> None:
    ledger.initialize_user()


def ledger_error(error: LedgerError) -> HTTPException:
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
) -> dict[str, object]:
    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise LedgerError("Statement uploads must not exceed 10 MiB")
        filename = file.filename or "statement.csv"
        if not filename.lower().endswith((".csv", ".xlsx")):
            raise LedgerError("Only CSV and XLSX statement imports are supported")
        return ledger.stage_import(account_id, filename, content)
    except LedgerError as error:
        raise ledger_error(error) from error


@app.get("/api/v1/imports/{import_id}/preview", tags=["imports"])
def preview_import(import_id: UUID) -> dict[str, object]:
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


@app.get("/api/v1/transactions", tags=["ledger"])
def list_transactions(month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$")) -> list[dict[str, object]]:
    return ledger.list_transactions(month=month)


@app.patch("/api/v1/transactions/{transaction_id}", tags=["ledger"])
def update_transaction(transaction_id: UUID, payload: dict[str, object]) -> dict[str, object]:
    try:
        return ledger.update_transaction(transaction_id, payload)
    except LedgerError as error:
        raise ledger_error(error) from error


@app.get("/api/v1/reports/monthly", tags=["analytics"])
def monthly_report(month: str = Query(pattern=r"^\d{4}-\d{2}$")) -> dict[str, object]:
    return ledger.monthly_report(month)
