"""Local-only Ollama transport; no SDK fallback, automatic pull or remote resolver."""

import asyncio
import hashlib
import json
import logging
import math
import re
from time import perf_counter
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.config import Settings
from app.llm.contracts import (
    ExtractionError,
    ModelIdentity,
    Prompt,
    StructuredResult,
    T,
)
from app.llm.prompts import INSTRUCTION_VERSION, SYSTEM_INSTRUCTION
from app.llm.schema import output_schema

logger = logging.getLogger(__name__)


class OllamaHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reachable: bool = False
    selected_model: str | None = None
    available_models: list[str] = []
    model_available: bool = False
    ready: bool = False
    error_code: str | None = None


def strict_json(value: str | bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = item
        return result

    def constant(_value: str) -> None:
        raise ValueError("Non-finite JSON constant")

    try:
        result = json.loads(value, object_pairs_hook=pairs, parse_constant=constant)

        def finite(node: Any) -> None:
            if isinstance(node, float) and not math.isfinite(node):
                raise ValueError("Non-finite JSON number")
            if isinstance(node, dict):
                for item in node.values():
                    finite(item)
            elif isinstance(node, list):
                for item in node:
                    finite(item)

        finite(result)
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise ExtractionError("malformed_json") from None


def canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class OllamaAdapter:
    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ):
        # Revalidate even when the caller used Pydantic's unchecked model_copy.
        self.settings = Settings.model_validate(settings.model_dump(warnings=False))
        url = self.settings.ollama_base_url
        # Pin localhost to a literal; never resolve environment-controlled DNS.
        host = "[::1]" if url.host == "[::1]" else "127.0.0.1"
        self.base_url = f"http://{host}:{url.port or 80}"
        self.transport = transport

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            transport=self.transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(
                self.settings.llm_timeout_seconds,
                connect=self.settings.llm_connect_timeout_seconds,
            ),
            headers={"Accept": "application/json", "Accept-Encoding": "identity"},
        )

    async def request(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        metadata: bool = False,
    ) -> tuple[dict[str, Any], int]:
        for attempt in range(self.settings.llm_retries + 1):
            retry_code: str | None = None
            try:
                async with client.stream(method, path, json=payload) as response:
                    if response.status_code in (429, 503):
                        retry_code = "server_busy"
                    elif 300 <= response.status_code < 400:
                        raise ExtractionError("redirect_rejected")
                    elif response.status_code == 404:
                        raise ExtractionError("model_or_endpoint_missing")
                    elif response.status_code != 200:
                        raise ExtractionError("server_error")
                    else:
                        content_type = response.headers.get("content-type", "").split(
                            ";", 1
                        )[0]
                        if content_type != "application/json":
                            raise ExtractionError("invalid_content_type")
                        if (
                            response.headers.get("content-encoding", "identity")
                            != "identity"
                        ):
                            raise ExtractionError("encoded_response_rejected")
                        body = bytearray()
                        async for block in response.aiter_bytes():
                            if (
                                len(body) + len(block)
                                > self.settings.llm_max_response_bytes
                            ):
                                raise ExtractionError("response_too_large")
                            body.extend(block)
                        parsed = strict_json(bytes(body))
                        if not isinstance(parsed, dict):
                            raise ExtractionError("invalid_response")
                        if "error" in parsed:
                            raise ExtractionError("server_error")
                        return parsed, attempt + 1
            except (httpx.ConnectError, httpx.ConnectTimeout):
                retry_code = "server_unavailable"
            except httpx.TimeoutException:
                if not metadata:
                    raise ExtractionError("timeout") from None
                retry_code = "timeout"
            except httpx.HTTPError:
                # Do not replay a generation after an ambiguous disconnect/write.
                raise ExtractionError("transport_error") from None
            if attempt == self.settings.llm_retries:
                raise ExtractionError(retry_code or "transport_error")
            await asyncio.sleep(0.25 * (2**attempt))
        raise ExtractionError("transport_error")

    async def models(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        payload, _ = await self.request(client, "GET", "/api/tags", metadata=True)
        models = payload.get("models")
        if not isinstance(models, list) or any(
            not isinstance(m, dict)
            or not isinstance(m.get("name"), str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,199}", m["name"])
            for m in models
        ):
            raise ExtractionError("invalid_model_list")
        return models

    async def local_model(
        self, client: httpx.AsyncClient, models: list[dict[str, Any]]
    ) -> str:
        selected = self.settings.ollama_model
        if not selected:
            raise ExtractionError("model_not_configured")
        match = next((m for m in models if m["name"] == selected), None)
        if match is None:
            raise ExtractionError("model_missing")
        if (
            "cloud" in selected.lower()
            or match.get("remote_host")
            or match.get("remote_model")
        ):
            raise ExtractionError("remote_model_rejected")
        model_digest, size = match.get("digest"), match.get("size")
        if (
            not isinstance(model_digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", model_digest)
            or type(size) is not int
            or size <= 0
        ):
            raise ExtractionError("local_model_unverified")
        details, _ = await self.request(
            client, "POST", "/api/show", {"model": selected}, metadata=True
        )
        if details.get("remote_host") or details.get("remote_model"):
            raise ExtractionError("remote_model_rejected")
        info = details.get("model_info")
        model_details = details.get("details")
        capabilities = details.get("capabilities")
        if (
            not isinstance(model_details, dict)
            or model_details.get("format") != "gguf"
            or not isinstance(info, dict)
            or type(info.get("general.parameter_count")) is not int
            or info["general.parameter_count"] <= 0
            or not isinstance(capabilities, list)
            or "completion" not in capabilities
        ):
            raise ExtractionError("local_model_unverified")
        return model_digest

    async def model_identity(self) -> ModelIdentity:
        try:
            async with (
                asyncio.timeout(self.settings.llm_health_timeout_seconds),
                self.client() as client,
            ):
                model_digest = await self.local_model(client, await self.models(client))
                return ModelIdentity(
                    "ollama", str(self.settings.ollama_model), model_digest
                )
        except TimeoutError:
            raise ExtractionError("timeout") from None

    async def health(self) -> OllamaHealth:
        result = OllamaHealth(selected_model=self.settings.ollama_model)
        try:
            async with (
                asyncio.timeout(self.settings.llm_health_timeout_seconds),
                self.client() as client,
            ):
                models = await self.models(client)
                result.reachable = True
                result.available_models = sorted({m["name"] for m in models})
                result.model_available = (
                    self.settings.ollama_model in result.available_models
                )
                await self.local_model(client, models)
                result.ready = True
        except ExtractionError as exc:
            result.error_code = exc.code
        except TimeoutError:
            result.error_code = "timeout"
        return result

    async def extract_structured(
        self, prompt: Prompt, schema: type[T]
    ) -> StructuredResult[T]:
        started = perf_counter()
        model = self.settings.ollama_model
        logger.info(
            "llm_start model=%s prompt=%s version=%s instructions=%s",
            model,
            prompt.name,
            prompt.version,
            INSTRUCTION_VERSION,
        )
        try:
            if len(prompt.text) > self.settings.llm_max_prompt_chars:
                raise ExtractionError("prompt_too_large")
            specification = output_schema(schema)
            rendered = (
                f"{prompt.text}\n\nRequired JSON schema:\n{canonical(specification)}"
            )
            async with (
                asyncio.timeout(self.settings.llm_timeout_seconds),
                self.client() as client,
            ):
                model_digest = await self.local_model(client, await self.models(client))
                inference_started = perf_counter()
                payload, attempts = await self.request(
                    client,
                    "POST",
                    "/api/generate",
                    {
                        "model": model,
                        "prompt": rendered,
                        "system": SYSTEM_INSTRUCTION,
                        "format": specification,
                        "stream": False,
                        "think": False,
                        "truncate": False,
                        "options": {
                            "temperature": 0,
                            "num_ctx": self.settings.llm_context_tokens,
                            "num_predict": self.settings.llm_max_output_tokens,
                        },
                    },
                )
                inference_ms = (perf_counter() - inference_started) * 1000
            if payload.get("remote_host") or payload.get("remote_model"):
                raise ExtractionError("remote_model_rejected")
            if payload.get("model") != model:
                raise ExtractionError("model_mismatch")
            if payload.get("done") is not True or payload.get("done_reason") != "stop":
                raise ExtractionError("incomplete_output")
            raw = payload.get("response")
            if not isinstance(raw, str):
                raise ExtractionError("invalid_response")
            if len(raw) > self.settings.llm_max_output_chars:
                raise ExtractionError("output_too_large")
            if not isinstance(strict_json(raw), dict):
                raise ExtractionError("schema_validation_failed")
            try:
                validated = schema.model_validate_json(raw, strict=True, extra="forbid")
            except ValidationError:
                raise ExtractionError("schema_validation_failed") from None
            elapsed = (perf_counter() - started) * 1000
            logger.info(
                "llm_success model=%s prompt=%s version=%s latency_ms=%.2f attempts=%d",
                model,
                prompt.name,
                prompt.version,
                elapsed,
                attempts,
            )
            return StructuredResult(
                data=validated,
                raw_json=raw,
                model=str(model),
                model_digest=model_digest,
                prompt_name=prompt.name,
                prompt_version=prompt.version,
                prompt_sha256=digest(SYSTEM_INSTRUCTION + "\n" + rendered),
                schema_sha256=digest(canonical(specification)),
                instruction_version=INSTRUCTION_VERSION,
                latency_ms=round(elapsed, 2),
                inference_latency_ms=round(inference_ms, 2),
                attempts=attempts,
            )
        except TimeoutError:
            logger.warning(
                "llm_failed model=%s prompt=%s version=%s code=timeout",
                model,
                prompt.name,
                prompt.version,
            )
            raise ExtractionError("timeout") from None
        except ExtractionError as exc:
            logger.warning(
                "llm_failed model=%s prompt=%s version=%s code=%s",
                model,
                prompt.name,
                prompt.version,
                exc.code,
            )
            raise
