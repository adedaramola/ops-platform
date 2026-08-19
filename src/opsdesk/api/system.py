from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from opsdesk.core.config import get_settings
from opsdesk.db.session import get_engine

router = APIRouter(tags=["system"])
EXPECTED_MIGRATION = "0002_ticket_domain"


def _database_ready() -> bool:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
            return str(revision) == EXPECTED_MIGRATION
    except SQLAlchemyError:
        return False


@router.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "live"}


@router.get("/health/ready")
def readiness(response: Response) -> dict[str, str]:
    if not _database_ready():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready"}
    return {"status": "ready"}


@router.get("/health")
def health(response: Response) -> dict[str, str]:
    ready = _database_ready()
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "healthy" if ready else "degraded"}


@router.get("/ready", include_in_schema=False)
def readiness_compatibility(response: Response) -> dict[str, str]:
    return readiness(response)


@router.get("/api/v1/status")
def application_status() -> dict[str, str]:
    settings = get_settings()
    return {
        "service": settings.service_name,
        "version": settings.version,
        "environment": settings.environment,
        "status": "operational",
    }
