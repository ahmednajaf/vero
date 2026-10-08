import asyncio
import httpx
import pytest
from app.core.config import Settings
from app.llm.evaluate import Fact, prompt, score
from app.llm.ollama import OllamaAdapter
from app.extraction.quality import scope_row_matches


def test_retired_provider_configuration_is_absent():
    fields = Settings.model_fields
    assert not any(k.startswith(("openrouter_", "chatgpt_")) for k in fields)
    with pytest.raises(ValueError):
        Settings(_env_file=None, ollama_base_url="https://example.com")


def test_retired_selfservice_routes_are_absent(api_client):
    paths = api_client.get("/openapi.json").json()["paths"]
    assert not any("selfservice" in p or "benchmark-sessions" in p for p in paths)
    assert not any("pharma" in p or "editions" in p for p in paths)


def test_wrong_scope_row_cannot_be_accepted():
    quote = "2025 GHG emissions (tCO2e)\nScope 1 emissions 100\nScope 2 emissions 200"
    assert not scope_row_matches("scope_1_emissions", quote, "200")
    case = {
        "metric": "scope_1_emissions",
        "passages": [{"page": 1, "text": quote}],
        "expected": {"value": "100", "unit": "tCO2e", "year": 2025, "page": 1},
    }
    f = Fact(
        metric="scope_1_emissions",
        value="200",
        unit="tCO2e",
        year=2025,
        page=1,
        excerpt=quote,
        status="reported",
    )
    assert score(case, f)["unsupported_inference"]
    assert not score(case, f)["case_correct"]


def test_evaluation_does_not_leak_gold_into_prompt():
    text = prompt(
        {
            "document": {"id": "test"},
            "metric": "scope_1_emissions",
            "requested_year": 2025,
            "passages": [],
            "expected": {"value": "SECRET_GOLD_VALUE"},
        }
    ).text
    assert "SECRET_GOLD_VALUE" not in text


def test_local_health_never_resolves_hosted_provider():
    adapter = OllamaAdapter(
        Settings(_env_file=None),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"models": []})
        ),
    )
    result = asyncio.run(adapter.health())
    assert result.reachable and not result.ready
    assert result.available_models == []
