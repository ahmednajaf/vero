from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.db.session import get_engine, get_session
from app.main import create_app


def application():
    return create_app(Settings(_env_file=None, app_env="test", reporting_year=2025))


def test_liveness_does_not_require_a_database_or_ollama():
    app = application()
    engine = MagicMock()
    engine.connect.side_effect = AssertionError(
        "Liveness must not connect to PostgreSQL"
    )
    app.dependency_overrides[get_engine] = lambda: engine
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "sustainability-benchmarking-api",
        "version": "0.1.0",
        "reporting_year": 2025,
    }
    engine.connect.assert_not_called()


def test_readiness_executes_a_real_query_contract():
    app = application()
    engine = MagicMock()
    app.dependency_overrides[get_engine] = lambda: engine
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "reachable"
    execute = engine.connect.return_value.__enter__.return_value.execute
    assert str(execute.call_args.args[0]) == "SELECT 1"
    assert "does not verify migration status" in response.json()["detail"]


def test_unavailable_database_returns_503_without_connection_secrets():
    app = application()
    engine = MagicMock()
    engine.connect.side_effect = OperationalError(
        "SELECT 1", {}, Exception("password=do-not-expose private-host.example")
    )
    app.dependency_overrides[get_engine] = lambda: engine
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert "do-not-expose" not in response.text
    assert "private-host" not in response.text


def test_cors_allows_only_configured_origins():
    with TestClient(application()) as client:
        allowed = client.get("/health", headers={"Origin": "http://127.0.0.1:5173"})
        blocked = client.get("/health", headers={"Origin": "https://unrelated.example"})
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "access-control-allow-origin" not in blocked.headers


def test_only_documented_endpoints_are_exposed():
    with TestClient(application()) as client:
        schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {
        "/health",
        "/health/ready",
        "/api/companies",
        "/api/companies/{id}",
        "/api/admin/report-status",
        "/api/metrics",
        "/api/benchmarks",
        "/api/companies/{id}/benchmark",
        "/api/companies/{id}/peer-explanation",
        "/api/companies/{id}/peer-explanation/export",
        "/api/sectors/{sector}/summary",
        "/api/library",
        "/api/companies/{company_id}/evidence",
        "/api/reports/{report_id}/file",
        "/api/reports/{report_id}/extract-metric",
        "/api/system/ai",
        "/api/knowledge/status",
        "/api/knowledge/companies",
        "/api/knowledge/answers",
        "/api/knowledge/collections",
        "/api/knowledge/collections/{run_id}",
        "/api/knowledge/reports",
        "/api/knowledge/reports/{report_id}/inspection",
        "/api/knowledge/preview",
        "/api/knowledge/search",
        "/api/knowledge/coverage",
        "/api/knowledge/evidence/{evidence_id}",
        "/api/knowledge/ask",
        "/api/knowledge/answers/{answer_id}",
        "/api/knowledge/briefings",
        "/api/knowledge/briefings/{identifier}",
        "/api/knowledge/briefings/{identifier}/advance",
        "/api/knowledge/briefings/{identifier}/export",
    }
    assert all(
        set(methods) == {"get"}
        for path, methods in schema["paths"].items()
        if path
        not in {
            "/api/knowledge/preview",
            "/api/knowledge/search",
            "/api/knowledge/coverage",
            "/api/knowledge/ask",
            "/api/knowledge/briefings",
            "/api/knowledge/briefings/{identifier}/advance",
            "/api/reports/{report_id}/extract-metric",
        }
    )


def test_company_database_errors_are_sanitised():
    app = application()

    def unavailable():
        raise OperationalError(
            "SELECT companies", {}, Exception("password=private-secret")
        )

    app.dependency_overrides[get_session] = unavailable
    with TestClient(app) as client:
        response = client.get("/api/companies")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable or schema not migrated."}
    assert "private-secret" not in response.text


def test_health_alias_supports_unchanged_api_proxy_paths():
    with TestClient(application()) as client:
        assert client.get("/api/health").json() == client.get("/health").json()
