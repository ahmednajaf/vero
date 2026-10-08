from alembic import context
from sqlalchemy import Connection

from app.core.config import get_settings
from app.db.base import Base
from app.db import models  # noqa: F401 -- register all tables with metadata
from app.db.session import create_database_engine

config = context.config


def migrate(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=Base.metadata, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url.get_secret_value(),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    migrate(config.attributes["connection"])
else:
    engine = create_database_engine(get_settings())
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()
