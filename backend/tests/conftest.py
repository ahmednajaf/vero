import csv
import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, Settings
from app.db.session import get_session
from app.main import create_app
from app.services.company_import import COLUMNS


@pytest.fixture
def migration_config():
    return Config(str(BACKEND_DIR / "alembic.ini"))


@pytest.fixture
def db_engine(migration_config):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "Set TEST_DATABASE_URL to a disposable PostgreSQL database ending in _test"
        )
    parsed = make_url(url)
    if parsed.drivername != "postgresql+psycopg" or not (
        parsed.database or ""
    ).endswith("_test"):
        pytest.fail(
            "TEST_DATABASE_URL must be PostgreSQL with a database name ending in _test"
        )
    # Every test gets a new private schema, never truncates public/user tables.
    schema = f"sbi_test_{uuid4().hex}"
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with engine.begin() as connection:
            migration_config.attributes["connection"] = connection
            command.upgrade(migration_config, "head")
        migration_config.attributes.pop("connection", None)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def api_client(db_engine):
    application = create_app(Settings(_env_file=None, app_env="test"))

    def database():
        with Session(db_engine) as session:
            yield session

    application.dependency_overrides[get_session] = database
    with TestClient(application) as client:
        yield client


@pytest.fixture
def company_row():
    return {
        "id": str(uuid4()),
        "company_name": "Example Industrial plc",
        "ticker": "EXMP",
        "country": "GB",
        "region": "Europe",
        "exchange": "XLON",
        "index": "",
        "sector": "Industrials",
        "industry": "Industrial Equipment",
        "official_domain": "example.com",
        "investor_relations_url": "https://example.com/investors",
        "sustainability_url": "",
        "reporting_currency": "",
        "revenue": "",
        "revenue_year": "",
        "reporting_year": "2025",
        "market_cap": "",
        "active": "true",
    }


@pytest.fixture
def csv_file(tmp_path):
    def write(rows, headers=COLUMNS, bom=False):
        path = tmp_path / f"companies-{uuid4().hex}.csv"
        with path.open(
            "w", encoding="utf-8-sig" if bom else "utf-8", newline=""
        ) as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        return path

    return write


@pytest.fixture
def seed_csv():
    return BACKEND_DIR.parent / "data" / "company_universe.csv"
