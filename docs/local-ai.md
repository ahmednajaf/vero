# Local structured-output adapter

The application boundary is `StructuredExtractor.extract_structured(prompt, schema)`, an asynchronous two-argument protocol. `Prompt` carries a name, explicit version and text; `schema` is a Pydantic model class. `model_identity()` now supplies verified provider-neutral name/digest metadata for run fingerprints. Consumers import the factory/contracts, not Ollama payloads or HTTP clients. The only provider implementation is local Ollama. No paid provider, automatic model selection, model pull or external fallback is included. The later [metric extraction stage](extraction.md) uses this adapter for bounded real-report passages; the original adapter-only smoke record below remains historical evidence.

```python
from pydantic import BaseModel, ConfigDict
from app.core.config import get_settings
from app.llm import Prompt, create_extractor

class Disclosure(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    company_name: str
    reporting_year: int

async def example():
    extractor = create_extractor(get_settings())
    return await extractor.extract_structured(
        Prompt("company-year", "1.0.0", "Source: Fictional plc reported for 2025."),
        Disclosure,
    )
```

The result contains typed `data`, original `raw_json`, exact configured model name and local digest, prompt/instruction versions, prompt/schema hashes, total and inference request latency, and generation attempt count. Prompt text and response fields are excluded from dataclass representations. Schema validation is not factual verification or authorisation to write sustainability observations.

## Configuration and selection

```dotenv
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=<exact approved installed name>
LLM_TIMEOUT_SECONDS=120
LLM_CONNECT_TIMEOUT_SECONDS=3
LLM_HEALTH_TIMEOUT_SECONDS=5
LLM_RETRIES=1
LLM_MAX_OUTPUT_TOKENS=1024
LLM_MAX_OUTPUT_CHARS=16000
LLM_MAX_RESPONSE_BYTES=262144
LLM_MAX_PROMPT_CHARS=16000
```

Inspect `ollama list` before setting the model. The example environment deliberately leaves the name blank: no model is hard-coded in adapter/factory code. A missing selection raises `model_not_configured`; an exact name absent from the installed list raises `model_missing`. No first-model fallback, guessed Gemma alias or automatic `:latest` resolution occurs. The application can still start and report its health without a configured model.

On 2026-09-29, local inspection showed **only `qwen3:14b`, 9.3 GB**, digest `bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`. No Gemma was installed. After explicit user approval, that existing model was selected in ignored `backend/.env`. No download occurred. Shared `.env.example` remains model-neutral.

## Local-only transport and trust boundary

- Endpoint validation accepts only plain HTTP `localhost`, `127.0.0.1` or `[::1]`, with a valid port and no credentials, path, query or fragment. `localhost` is pinned to literal `127.0.0.1`; there is no arbitrary DNS lookup. Remote/LAN hosts and other providers fail configuration validation.
- HTTPX uses `trust_env=False` and `follow_redirects=False`. Proxy environment variables cannot route prompts externally; all redirects fail, including redirects to another local address. Credentials are never attached. Compressed responses are rejected; received bodies are bounded before JSON parsing.
- Before sending any prompt, the adapter lists installed models and reads the selected model's metadata. It requires a local digest, positive local size, GGUF format, positive parameter count and completion capability; cloud names, remote host/model metadata and unverifiable models are rejected. A custom alias backed by a remote model fails before generation.
- Only `/api/tags`, `/api/show` and `/api/generate` are called. No `/pull`, cloud, web-search, tool execution, embeddings or OpenAI-compatible provider route is used. Report text is never automatically read by this adapter.
- As defense in depth, start the **Ollama server** with `OLLAMA_NO_CLOUD=1`. This variable in the backend's `.env` alone cannot reconfigure a separately running daemon. This implementation does not restart or alter the user's existing Ollama service. Its current cloud setting was enabled, but the selected model was verified as local; no cloud model was invoked. The local daemon and its model metadata are trusted infrastructure: application checks are not an OS network sandbox, nor protection against a malicious local proxy or concurrent administrator replacing a model alias. Use a cloud-disabled server and host-level egress controls where stronger operational isolation is required. [Ollama local-only configuration](https://docs.ollama.com/faq#how-do-i-disable-ollama-cloud-features).

## Structured output, limits and retries

The adapter supplies a closed JSON Schema to `format`, repeats it in the prompt, sets temperature zero, disables thinking, requests `stream=false`, sets `num_predict`, and asks the server not to truncate the input. HTTP response bytes are read incrementally with a hard cap even though Ollama generation is non-streaming. These controls follow the [structured-output API](https://docs.ollama.com/capabilities/structured-outputs) and [generation endpoint](https://docs.ollama.com/api/generate).

The returned JSON is independently checked: no code fences, repairs, duplicate keys, non-finite numbers, arrays instead of an object, missing required values, wrong types or unknown fields (including nested objects). Strict Pydantic validation is applied. Closed, typed object schemas are supported; arbitrary open maps and external schema references are rejected. Model mismatch, incomplete output and token-limit termination fail even if the partial JSON happens to be syntactically valid. There is no retry with a weaker schema or different model.

Default limits: 1,024 output tokens, 16,000 output characters, 256 KiB total HTTP JSON envelope, 16,000 source prompt characters, and a 32,000-character schema cap. The whole network operation, including metadata and backoff, has a 120-second deadline; connect timeout is 3 seconds. Health has its own 5-second total deadline. Token caps bound requested generation; character/byte caps bound accepted output. Timing out cancels/closes the client request; this is not a guarantee that the local daemon immediately releases a loaded model or stops all backend computation.

One retry by default (configurable 0–2), with 0.25/0.5-second backoff, only for connection establishment failure or explicit HTTP 429/503. Metadata read timeouts may also retry because those operations are read-only. Generation read/write timeouts, ambiguous disconnects, other HTTP errors, malformed JSON, schema errors and output limits are **not** replayed. One total deadline bounds all retries. No error body, prompt, response or server exception text is included in application error codes/logs.

Versioned prompts live in `app/llm/prompts.py`. The current common instruction version is `structured-extraction.v1`; the synthetic smoke prompt is `adapter-smoke` version `1.0.0`. Change the relevant version whenever a template changes. Per-call hashes additionally identify the rendered instruction/prompt/schema. INFO/WARNING application logs record selected model, prompt name/version, instruction version, success latency/attempts or a safe failure code; they never record source text or generated answers. Keep HTTP wire logging off for real data.

## Health endpoint

`GET /api/system/ollama` is read-only and never generates text, downloads models or connects to PostgreSQL. HTTP 200 requires usable selected local-model metadata; otherwise it returns 503 with the same response shape. `reachable` means the local model-list API returned valid metadata; it is not an inference benchmark.

Actual response on 2026-09-29:

```json
{
  "reachable": true,
  "selected_model": "qwen3:14b",
  "available_models": ["qwen3:14b"],
  "model_available": true,
  "ready": true,
  "error_code": null
}
```

Only selected/available names, booleans and safe error codes are returned: no credentials, server address, model system prompt, license, paths or raw errors. Existing liveness and database-readiness routes stay independent. No frontend or hosted-site changes are included.

## Tests and real local smoke

Routine tests use `httpx.MockTransport`: unavailable server, missing/unconfigured model, malformed JSON, duplicate/non-finite JSON, strict and nested unexpected fields, timeouts/deadlines, valid output, safe bounded retries, limits, truncated output, model mismatch, rejected remote/alias metadata, unsafe origins, environment proxies, sanitised logs and API health. They never invoke a real model. Verification on 2026-09-29: **53 adapter tests; 185 total backend tests passed, 1 optional live acquisition test skipped**, with real isolated PostgreSQL schemas. Python typing, scoped lint, dependency consistency and Alembic no-drift checks passed. The unchanged frontend passed 12 tests, TypeScript checking and its production build.

The one explicitly requested real test used the existing approved `qwen3:14b` model and fictional text, with **one generation request**, no retries, no downloaded model and no company reports. Client-measured inference request latency (including any model loading) was **32,011.88 ms**; total adapter latency including local preflight was **32,064.95 ms**. This is one observation, not a throughput benchmark.

Prompt:

> Extract the company name and reporting year from this fictional sentence. Source: Example Manufacturing plc published its report for reporting year 2025.

Validated response:

```json
{"company_name": "Example Manufacturing plc", "reporting_year": 2025}
```

The [complete captured evidence](ollama-live-2026-09-29.json) contains the exact system instruction, schema, prompt/version/hashes, raw response, model digest, timestamp and latency. It intentionally records this **synthetic** prompt/answer; normal adapter logging does not. The wire prompt is the recorded prompt followed by `\n\nRequired JSON schema:\n` and the canonical schema JSON (sorted keys, compact separators).

To explicitly repeat a synthetic test with your configured model:

```bash
cd backend
source .venv/bin/activate
python -m app.llm.smoke --output /tmp/new-local-ai-smoke.json
```

The output path must not exist. No general-purpose inference HTTP endpoint, report ingestion, metric extraction, database migration, local model installation or new cloud infrastructure was added. The isolated PostgreSQL regression instance is stopped after verification; the user's existing Ollama service is left running unchanged.

Changed files: `backend/app/llm/{__init__,contracts,factory,ollama,prompts,smoke}.py`, `backend/app/api/system.py`, `backend/app/main.py`, `backend/app/core/config.py`, `backend/.env.example`, ignored local `backend/.env`, `backend/pyproject.toml`, `backend/tests/test_llm.py`, endpoint expectations in `backend/tests/test_health.py`, `README.md`, `docs/architecture.md`, this document and the captured JSON. HTTPX was already installed/pinned in `requirements-dev.lock`; it is now declared as a runtime rather than dev-only dependency. Frontend source, company data and database schema are unchanged. Existing project files were untracked before this stage.
