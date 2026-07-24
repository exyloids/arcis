from datetime import UTC, datetime

from arcis_backend import __version__
from arcis_backend.settings import get_settings
from arcis_contracts.health import HealthResponse, ReadinessResponse
from fastapi import FastAPI

settings = get_settings()
app = FastAPI(
    title="Arcis API",
    version=__version__,
    description="Read-only personal finance tracker API",
)


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
