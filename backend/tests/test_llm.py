import asyncio
import json
import logging
from unittest.mock import patch

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.config import Settings
from app.llm import ExtractionError, Prompt, create_extractor
from app.llm.ollama import OllamaAdapter, output_schema
from app.llm.prompts import SMOKE_PROMPT, SmokeResponse

MODEL = "fictional-local:small"
DIGEST = "a" * 64
TAGS = {"models": [{"name": MODEL, "digest": DIGEST, "size": 1024}]}
SHOW = {
    "details": {"format": "gguf"},
    "model_info": {"general.parameter_count": 1000},
    "capabilities": ["completion"],
}
VALID = {"company_name": "Example Manufacturing plc", "reporting_year": 2025}


def config(**kwargs):
    return Settings(_env_file=None, ollama_model=MODEL, llm_retries=0, **kwargs)


def envelope(content=None, **kwargs):
    return {
        "model": MODEL,
        "done": True,
        "done_reason": "stop",
        "response": json.dumps(VALID if content is None else content),
        **kwargs,
    }


def mocked(*, generate=None, tags=None, show=None, settings=None):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=TAGS if tags is None else tags)
        if request.url.path == "/api/show":
            return httpx.Response(200, json=SHOW if show is None else show)
        assert request.url.path == "/api/generate"
        if isinstance(generate, Exception):
            raise generate
        if callable(generate):
            return generate(request)
        return httpx.Response(200, json=envelope() if generate is None else generate)

    return (
        OllamaAdapter(settings or config(), transport=httpx.MockTransport(handler)),
        calls,
    )


def infer(adapter, schema=SmokeResponse, prompt=SMOKE_PROMPT):
    return asyncio.run(adapter.extract_structured(prompt, schema))


def assert_error(adapter, code, **kwargs):
    with pytest.raises(ExtractionError) as caught:
        infer(adapter, **kwargs)
    assert caught.value.code == code


def test_valid_response_is_typed_versioned_bounded_and_content_is_not_logged(caplog):
    adapter, calls = mocked()
    with caplog.at_level(logging.INFO, logger="app.llm.ollama"):
        result = infer(adapter)
    assert result.data.model_dump() == VALID
    assert result.model == MODEL and result.model_digest == DIGEST
    assert result.prompt_version == "1.0.0" and result.instruction_version
    assert len(result.prompt_sha256) == len(result.schema_sha256) == 64
    assert result.latency_ms >= result.inference_latency_ms >= 0
    assert result.attempts == 1
    assert MODEL in caplog.text and "version=1.0.0" in caplog.text
    assert (
        SMOKE_PROMPT.text not in caplog.text
        and VALID["company_name"] not in caplog.text
    )
    assert VALID["company_name"] not in repr(result)
    request = json.loads(calls[-1].content)
    assert request["format"]["additionalProperties"] is False
    assert request["options"]["num_predict"] == adapter.settings.llm_max_output_tokens
    assert request["think"] is False and request["stream"] is False
    assert request["model"] == MODEL
    assert all(str(call.url).startswith("http://127.0.0.1:11434/") for call in calls)


def test_server_unavailable_and_health_are_sanitised():
    def unavailable(request):
        raise httpx.ConnectError("secret-proxy-password", request=request)

    adapter = OllamaAdapter(config(), transport=httpx.MockTransport(unavailable))
    assert_error(adapter, "server_unavailable")
    health = asyncio.run(adapter.health())
    assert not health.reachable and not health.ready
    assert health.available_models == [] and health.selected_model == MODEL
    assert "secret-proxy-password" not in health.model_dump_json()


def test_missing_model_never_generates_or_substitutes():
    adapter, calls = mocked(
        tags={"models": [{**TAGS["models"][0], "name": "another:local"}]}
    )
    assert_error(adapter, "model_missing")
    assert [c.url.path for c in calls] == ["/api/tags"]
    health = asyncio.run(adapter.health())
    assert health.reachable and not health.model_available and not health.ready
    assert health.available_models == ["another:local"]


def test_unconfigured_model_does_not_choose_first_installed():
    adapter, calls = mocked(settings=Settings(_env_file=None, ollama_model=None))
    assert_error(adapter, "model_not_configured")
    assert not any(c.url.path == "/api/generate" for c in calls)


@pytest.mark.parametrize(
    "raw",
    [
        "not JSON",
        "```json\n{}\n```",
        '{"x":NaN}',
        '{"x":1,"x":2}',
        '{"x":Infinity}',
        '{"x":1e400}',
    ],
)
def test_malformed_json_is_not_repaired_or_retried(raw):
    adapter, calls = mocked(generate=envelope(response=raw))
    assert_error(adapter, "malformed_json")
    assert sum(c.url.path == "/api/generate" for c in calls) == 1


@pytest.mark.parametrize(
    "content",
    [
        {**VALID, "secret_extra": "no"},
        {"company_name": "Example", "reporting_year": "2025"},
        {"company_name": "Example"},
        [VALID],
    ],
)
def test_unexpected_fields_wrong_types_missing_fields_and_wrong_shape(content):
    adapter, _ = mocked(generate=envelope(content))
    assert_error(adapter, "schema_validation_failed")


def test_nested_unexpected_fields_are_rejected_even_with_default_pydantic_config():
    class Inner(BaseModel):
        value: str

    class Outer(BaseModel):
        item: Inner

    adapter, _ = mocked(
        generate=envelope({"item": {"value": "yes", "extra": "reject"}})
    )
    assert_error(adapter, "schema_validation_failed", schema=Outer)
    assert output_schema(Outer)["$defs"]["Inner"]["additionalProperties"] is False


def test_read_timeout_is_never_retried_after_submission():
    adapter, calls = mocked(
        generate=httpx.ReadTimeout("prompt must not leak"),
        settings=Settings(_env_file=None, ollama_model=MODEL, llm_retries=2),
    )
    assert_error(adapter, "timeout")
    assert sum(c.url.path == "/api/generate" for c in calls) == 1


def test_total_deadline_cancels_slow_stream():
    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=TAGS)

    adapter = OllamaAdapter(
        config(llm_timeout_seconds=0.1), transport=httpx.MockTransport(slow)
    )
    assert_error(adapter, "timeout")


@pytest.mark.parametrize("failure", ["connect", 429, 503])
def test_only_safe_transient_failures_are_retried(failure):
    count = 0

    def temporary(request):
        nonlocal count
        count += 1
        if count == 1:
            if failure == "connect":
                raise httpx.ConnectError("refused", request=request)
            return httpx.Response(failure)
        return httpx.Response(200, json=envelope())

    adapter, _ = mocked(
        generate=temporary,
        settings=Settings(_env_file=None, ollama_model=MODEL, llm_retries=1),
    )
    assert infer(adapter).attempts == count == 2


@pytest.mark.parametrize(
    "status,code",
    [
        (500, "server_error"),
        (400, "server_error"),
        (404, "model_or_endpoint_missing"),
        (307, "redirect_rejected"),
    ],
)
def test_permanent_errors_and_redirects_are_not_retried(status, code):
    adapter, calls = mocked(
        generate=lambda _: httpx.Response(
            status, headers={"Location": "https://external.invalid/steal"}
        ),
        settings=Settings(_env_file=None, ollama_model=MODEL, llm_retries=2),
    )
    assert_error(adapter, code)
    assert sum(c.url.path == "/api/generate" for c in calls) == 1


def test_retries_are_bounded():
    adapter, calls = mocked(
        generate=lambda _: httpx.Response(503),
        settings=Settings(_env_file=None, ollama_model=MODEL, llm_retries=1),
    )
    assert_error(adapter, "server_busy")
    assert sum(c.url.path == "/api/generate" for c in calls) == 2


@pytest.mark.parametrize(
    "patch", [{"done": False}, {"done_reason": "length"}, {"done_reason": "unknown"}]
)
def test_truncated_or_incomplete_json_is_rejected_even_if_syntactically_valid(patch):
    adapter, _ = mocked(generate=envelope(**patch))
    assert_error(adapter, "incomplete_output")


def test_output_character_limit_and_http_byte_limit():
    adapter, _ = mocked(
        generate=envelope(response=" " * 129), settings=config(llm_max_output_chars=128)
    )
    assert_error(adapter, "output_too_large")
    adapter, _ = mocked(
        generate=envelope(response=" " * 2000),
        settings=config(llm_max_response_bytes=1024),
    )
    assert_error(adapter, "response_too_large")


def test_prompt_size_limit_prevents_network_call():
    adapter, calls = mocked(settings=config(llm_max_prompt_chars=128))
    assert_error(adapter, "prompt_too_large", prompt=Prompt("large", "1", "X" * 129))
    assert calls == []


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example.com",
        "http://192.168.1.2:11434",
        "http://0.0.0.0:11434",
        "http://localhost.evil.invalid",
        "http://user:secret@localhost:11434",
        "http://localhost:11434/proxy",
        "http://localhost:11434/?token=secret",
        "http://localhost:11434/#secret",
    ],
)
def test_nonlocal_or_credentialed_endpoints_are_rejected_before_io(url):
    with pytest.raises(ValidationError):
        config(ollama_base_url=url)


def test_local_endpoint_is_pinned_and_environment_proxies_disabled(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://external.invalid")
    monkeypatch.setenv("ALL_PROXY", "http://external.invalid")
    adapter, _ = mocked()
    assert infer(adapter).data.model_dump() == VALID
    with patch("app.llm.ollama.httpx.AsyncClient") as client:
        adapter.client()
    assert client.call_args.kwargs["trust_env"] is False
    assert client.call_args.kwargs["follow_redirects"] is False
    assert client.call_args.kwargs["base_url"] == "http://127.0.0.1:11434"


@pytest.mark.parametrize(
    "metadata",
    [
        {**SHOW, "remote_host": "https://remote.invalid"},
        {**SHOW, "remote_model": "alias"},
        {"details": {"format": "remote"}},
        {**SHOW, "capabilities": ["embedding"]},
    ],
)
def test_cloud_aliases_and_unverifiable_models_are_rejected_before_prompt(metadata):
    adapter, calls = mocked(show=metadata)
    with pytest.raises(ExtractionError):
        infer(adapter)
    assert not any(c.url.path == "/api/generate" for c in calls)


def test_changed_response_model_is_not_a_silent_fallback():
    adapter, _ = mocked(generate=envelope(model="another:model"))
    assert_error(adapter, "model_mismatch")


def test_invalid_model_metadata_is_an_explicit_error_not_an_unhandled_exception():
    adapter, calls = mocked(show={**SHOW, "capabilities": None})
    assert_error(adapter, "local_model_unverified")
    assert not any(c.url.path == "/api/generate" for c in calls)


def test_malformed_transport_json_and_embedded_server_errors_are_sanitised():
    adapter, _ = mocked(
        generate=lambda _: httpx.Response(
            200,
            content=b"PRIVATE not JSON",
            headers={"content-type": "application/json"},
        )
    )
    assert_error(adapter, "malformed_json")
    adapter, _ = mocked(generate={"error": "PRIVATE service internals"})
    assert_error(adapter, "server_error")


def test_ipv6_loopback_is_allowed_and_bad_model_config_is_revalidated():
    adapter = OllamaAdapter(config(ollama_base_url="http://[::1]:11434"))
    assert adapter.base_url == "http://[::1]:11434"
    with pytest.raises(ValidationError):
        OllamaAdapter(
            config().model_copy(update={"ollama_base_url": "https://remote.invalid"})
        )


def test_health_deadline_and_malformed_model_list_are_safe():
    adapter, _ = mocked(tags={"models": "secret-invalid"})
    result = asyncio.run(adapter.health())
    assert not result.ready and result.error_code == "invalid_model_list"
    assert "secret-invalid" not in result.model_dump_json()

    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=TAGS)

    adapter = OllamaAdapter(
        config(llm_health_timeout_seconds=0.1), transport=httpx.MockTransport(slow)
    )
    assert asyncio.run(adapter.health()).error_code == "timeout"


def test_cloud_named_models_are_rejected_without_show_or_prompt():
    selected = "fictional:cloud"
    adapter, calls = mocked(
        tags={"models": [{**TAGS["models"][0], "name": selected}]},
        settings=Settings(_env_file=None, ollama_model=selected),
    )
    assert_error(adapter, "remote_model_rejected")
    assert [c.url.path for c in calls] == ["/api/tags"]


def test_external_provider_is_not_supported():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_provider="paid")
    with pytest.raises(ExtractionError):
        create_extractor(config().model_copy(update={"llm_provider": "paid"}))


def test_legacy_adapter_health_returns_only_safe_metadata_without_inference():
    adapter, calls = mocked(
        show={**SHOW, "system": "SECRET_SYSTEM", "license": "PRIVATE_METADATA"}
    )
    result = asyncio.run(adapter.health())
    assert result.model_dump() == {
        "reachable": True,
        "selected_model": MODEL,
        "available_models": [MODEL],
        "model_available": True,
        "ready": True,
        "error_code": None,
    }
    assert "SECRET" not in result.model_dump_json()
    assert "PRIVATE" not in result.model_dump_json()
    assert not any(c.url.path == "/api/generate" for c in calls)


def test_legacy_adapter_missing_model_does_not_invent_readiness():
    adapter, _ = mocked(tags={"models": []})
    result = asyncio.run(adapter.health())
    assert not result.ready
    assert result.error_code == "model_missing"


def test_prompt_requires_version_and_schema_rejects_open_maps():
    with pytest.raises(ValueError):
        Prompt("unversioned", "", "example")

    class Open(BaseModel):
        model_config = ConfigDict(extra="allow")
        value: str

    with pytest.raises(ExtractionError, match="open_object_schema"):
        output_schema(Open)
