from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.api.health import router as health_router
from app.api.companies import router as companies_router
from app.api.reports import router as reports_router
from app.api.system import router as system_router
from app.api.metrics import router as metrics_router
from app.api.benchmarks import router as benchmarks_router
from app.api.evidence import router as evidence_router
from app.api.knowledge import router as knowledge_router
from app.api.briefings import router as briefings_router
from app.core.config import Settings, get_settings
from app.db.session import create_database_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    engine = create_database_engine(config)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title=config.api_title,
        version=__version__,
        description="Provenance-first company, report, metric and transparent prototype benchmarking APIs.",
        lifespan=lifespan,
    )
    application.state.settings = config
    application.state.database_engine = engine
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Accept", "Content-Type"],
        expose_headers=["X-Explanation-SHA256", "Content-Disposition"],
    )
    application.include_router(health_router)
    application.include_router(health_router, prefix="/api", include_in_schema=False)
    application.include_router(companies_router)
    application.include_router(reports_router)
    application.include_router(system_router)
    application.include_router(metrics_router)
    application.include_router(benchmarks_router)
    application.include_router(evidence_router)
    application.include_router(knowledge_router)
    application.include_router(briefings_router)

    @application.exception_handler(SQLAlchemyError)
    async def database_unavailable(
        _request: object, _exc: SQLAlchemyError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "Database unavailable or schema not migrated."},
        )

    return application


app = create_app()
