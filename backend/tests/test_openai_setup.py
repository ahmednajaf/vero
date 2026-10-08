"""Direct OpenAI configuration/health tests: no real credentials or network."""

import asyncio
import json
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.core.config import BACKEND_DIR, Settings
from app.knowledge.provider import OpenAIResearchProvider, request_body
from app.main import create_app


def configured(**overrides):
    values = dict(
        knowledge_ai_enabled=True,
        openai_api_key=SecretStr("fixture-secret-never-display"),
        openai_model="fixture-model",
        openai_allowed_models=["fixture-model"],
        openai_input_price=2,
        openai_output_price=10,
        knowledge_monthly_budget_usd=5,
    )
    return Settings(_env_file=None, **(values | overrides))


def test_health_gets_only_selected_model_and_never_runs_inference():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert str(request.url) == "https://api.openai.com/v1/models/fixture-model"
        assert request.headers["Authorization"] == "Bearer fixture-secret-never-display"
        return httpx.Response(
            200, json={"id": "fixture-model", "private": "DO_NOT_RETURN"}
        )

    adapter = OpenAIResearchProvider(configured(), httpx.MockTransport(handler))
    with patch("app.api.system.OpenAIResearchProvider", return_value=adapter):
        with TestClient(create_app(configured())) as client:
            response = client.get("/api/system/ai")
            assert client.get("/api/system/ollama").status_code == 404
    assert response.status_code == 200 and len(calls) == 1
    assert response.headers["Cache-Control"] == "no-store"
    result = response.json()
    assert result["provider"] == "openai" and result["ready"]
    assert result["model_available"] and result["connectivity_tested"]
    assert not result["inference_verified"] and not result["fallback_enabled"]
    assert (
        "fixture-secret" not in response.text and "DO_NOT_RETURN" not in response.text
    )


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "openai_authentication"),
        (403, "openai_access_denied"),
        (404, "openai_model_unavailable"),
        (429, "openai_rate_limit"),
        (500, "openai_unavailable"),
        (302, "openai_unavailable"),
    ],
)
def test_health_errors_are_safe_no_redirect_retry_or_fallback(status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, text="SENSITIVE", headers={"Location": "https://example.com"}
        )

    adapter = OpenAIResearchProvider(configured(), httpx.MockTransport(handler))
    with patch("app.api.system.OpenAIResearchProvider", return_value=adapter):
        with TestClient(create_app(configured())) as client:
            response = client.get("/api/system/ai")
    assert response.status_code == 503 and len(calls) == 1
    assert response.json()["error_code"] == code
    assert "SENSITIVE" not in response.text and "fixture-secret" not in response.text


def test_missing_key_makes_no_network_request():
    def unexpected(_):
        pytest.fail("Missing credentials must not trigger HTTP")

    adapter = OpenAIResearchProvider(
        configured(openai_api_key=SecretStr("")), httpx.MockTransport(unexpected)
    )
    result = asyncio.run(adapter.health())
    assert result["error_code"] == "openai_key_missing"
    assert result["reachable"] is None and not result["connectivity_tested"]


@pytest.mark.parametrize(
    "error,code",
    [
        (httpx.ReadTimeout, "openai_timeout"),
        (httpx.ConnectError, "openai_unavailable"),
    ],
)
def test_unavailable_server_has_clear_safe_error(error, code):
    def handler(request):
        raise error("SENSITIVE", request=request)

    result = asyncio.run(
        OpenAIResearchProvider(configured(), httpx.MockTransport(handler)).health()
    )
    assert result["error_code"] == code and result["reachable"] is False
    assert "SENSITIVE" not in json.dumps(result)


@pytest.mark.parametrize(
    "body,code",
    [
        (b"not json", "openai_invalid_model_metadata"),
        (b"x" * 65537, "openai_invalid_model_metadata"),
        (b'{"id":"different-model"}', "openai_model_mismatch"),
    ],
)
def test_bad_model_metadata_never_claims_readiness(body, code):
    adapter = OpenAIResearchProvider(
        configured(), httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    )
    result = asyncio.run(adapter.health())
    assert result["error_code"] == code and not result["ready"]


def test_secret_validation_and_configuration_are_safe():
    config = configured(openai_api_key=SecretStr("  fixture-secret  "))
    assert config.openai_api_key.get_secret_value() == "fixture-secret"
    assert "fixture-secret" not in repr(config)
    with pytest.raises(ValidationError) as error:
        configured(openai_api_key=SecretStr("PRIVATE secret"))
    assert "PRIVATE" not in str(error.value)
    with pytest.raises(ValidationError):
        configured(ai_provider="openrouter")


def test_backend_environment_path_is_explicit_and_examples_have_no_keys():
    assert Settings.model_config["env_file"] == BACKEND_DIR / ".env"
    for path in (BACKEND_DIR / ".env.example", BACKEND_DIR.parent / ".env.example"):
        lines = path.read_text().splitlines()
        assert "AI_PROVIDER=openai" in lines and "OPENAI_API_KEY=" in lines
        assert not any(
            line.startswith(("OPENROUTER_", "CHATGPT_", "OLLAMA_", "LLM_PROVIDER="))
            for line in lines
        )


def test_reasoning_and_output_budget_are_explicit_not_silently_inferred():
    body = request_body(
        configured(openai_reasoning_effort="low", openai_max_output_tokens=4000), {}
    )
    assert body["reasoning"] == {"effort": "low"}
    assert body["max_output_tokens"] == 4000
    assert body["service_tier"] == "default"
    assert "reasoning" not in request_body(configured(), {})
