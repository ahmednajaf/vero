from collections.abc import Generator
from typing import cast

from fastapi import Depends, Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    # Engine construction is lazy: importing/starting the API never opens a connection.
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=5,
        pool_recycle=1800,
        connect_args={
            "connect_timeout": settings.database_connect_timeout,
            "options": "-c timezone=UTC",
        },
        hide_parameters=True,
    )


def get_engine(request: Request) -> Engine:
    return cast(Engine, request.app.state.database_engine)


def get_session(engine: Engine = Depends(get_engine)) -> Generator[Session, None, None]:
    # Operations will explicitly own commits. Failed requests roll back on close.
    with Session(engine, autoflush=False, expire_on_commit=False) as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
