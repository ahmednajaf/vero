from typing import cast

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.core.config import Settings
from app.db.session import get_engine
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = cast(Settings, request.app.state.settings)
    return HealthResponse(version=__version__, reporting_year=settings.reporting_year)


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={
        503: {"model": ReadinessResponse, "description": "Database unavailable"}
    },
)
def readiness(
    response: Response, engine: Engine = Depends(get_engine)
) -> ReadinessResponse:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # Never expose driver errors, credentials, hostnames, or connection URLs.
        response.status_code = 503
        return ReadinessResponse(
            status="not_ready",
            database="unavailable",
            detail="PostgreSQL is unavailable. Check the local database and connection settings.",
        )
    return ReadinessResponse(
        status="ready",
        database="reachable",
        detail="PostgreSQL accepts queries. This connectivity check does not verify migration status.",
    )
