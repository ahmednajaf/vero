"""Bridge the existing metric pipeline to the application's guarded OpenAI client."""

import hashlib
import json
import logging
from decimal import Decimal

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import KnowledgeAnswer
from app.knowledge.budget import check_limits
from app.knowledge.provider import (
    OpenAIResearchProvider,
    ResearchError,
    configured,
    request_body,
)
from app.llm.contracts import (
    ExtractionError,
    ModelIdentity,
    Prompt,
    StructuredResult,
    T,
)
from app.llm.prompts import INSTRUCTION_VERSION, SYSTEM_INSTRUCTION
from app.llm.schema import output_schema

log = logging.getLogger(__name__)


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class OpenAIStructuredExtractor:
    def __init__(
        self,
        settings: Settings,
        engine: Engine,
        provider: OpenAIResearchProvider | None = None,
    ):
        self.settings, self.engine = settings, engine
        self.provider = provider or OpenAIResearchProvider(settings)

    async def model_identity(self) -> ModelIdentity:
        if reason := configured(self.settings):
            raise ExtractionError(reason)
        # Hosted providers don't expose weight digests. This is explicitly a
        # configuration fingerprint, not a claim about the model's weights.
        fingerprint = digest(
            canonical(
                {
                    "provider": "openai",
                    "model": self.settings.openai_model,
                    "reasoning": self.settings.openai_reasoning_effort,
                    "output_limit": self.settings.openai_max_output_tokens,
                    "instructions": INSTRUCTION_VERSION,
                    "adapter": "openai-extraction-v1",
                }
            )
        )
        return ModelIdentity(
            "openai", self.settings.openai_model, "config-sha256:" + fingerprint
        )

    async def extract_structured(
        self, prompt: Prompt, schema: type[T]
    ) -> StructuredResult[T]:
        identity = await self.model_identity()
        schema_hash = digest(canonical(output_schema(schema)))
        prompt_hash = digest(prompt.text)
        cache_key = digest(
            canonical(
                [identity.digest, prompt.name, prompt.version, prompt_hash, schema_hash]
            )
        )
        payload = {"source_extraction_task": prompt.text}
        # UTF-8 bytes + framing margin is a conservative token reservation, not
        # an invented measured token count. It includes the JSON schema.
        input_bound = (
            len(
                canonical(
                    request_body(
                        self.settings,
                        payload,
                        schema=schema,
                        instructions=SYSTEM_INSTRUCTION,
                    )
                ).encode()
            )
            + 4096
        )
        output_bound = self.settings.openai_max_output_tokens
        price_in = Decimal(str(self.settings.openai_input_price)) / 1_000_000
        price_out = Decimal(str(self.settings.openai_output_price)) / 1_000_000
        reservation = input_bound * price_in + output_bound * price_out

        def result(raw: str, latency: float, attempts: int) -> StructuredResult[T]:
            return StructuredResult(
                schema.model_validate_json(raw),
                raw,
                identity.name,
                identity.digest,
                prompt.name,
                prompt.version,
                prompt_hash,
                schema_hash,
                INSTRUCTION_VERSION,
                latency,
                latency,
                attempts,
            )

        with Session(self.engine, expire_on_commit=False) as session:
            session.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtextextended('knowledge-budget', 0))"
                )
            )
            cached = session.scalar(
                select(KnowledgeAnswer).where(
                    KnowledgeAnswer.request_sha256 == cache_key,
                    KnowledgeAnswer.status == "completed",
                )
            )
            if cached:
                return result(str(cached.payload["structured_result"]), 0, 0)
            try:
                check_limits(
                    session, self.settings, reservation, input_bound + output_bound
                )
                if session.scalar(
                    select(KnowledgeAnswer.id)
                    .where(KnowledgeAnswer.status == "running")
                    .limit(1)
                ):
                    raise ResearchError("research_busy_or_interrupted")
            except ResearchError as exc:
                raise ExtractionError(exc.code) from None
            saved = KnowledgeAnswer(
                request_sha256=cache_key,
                question=f"Metric extraction · {prompt.name} · {prompt.version}",
                provider="openai",
                model=identity.name,
                status="running",
                payload={"task_type": "metric_extraction"},
                reserved_usd=reservation,
                usage={"reserved_tokens": input_bound + output_bound},
            )
            session.add(saved)
            session.commit()  # Reserve before the network call; never retry a POST silently.
            try:
                completion = await self.provider.structured(
                    payload, schema, SYSTEM_INSTRUCTION
                )
                saved.usage = {
                    **saved.usage,
                    "input_tokens": completion.input_tokens,
                    "output_tokens": completion.output_tokens,
                    "latency_ms": round(completion.latency_ms, 2),
                    "task_type": "metric_extraction",
                }
                saved.charged_usd = (
                    completion.input_tokens * price_in
                    + completion.output_tokens * price_out
                )
                session.commit()
                if completion.model != identity.name:
                    raise ResearchError("openai_model_mismatch")
                if (
                    completion.input_tokens > input_bound
                    or completion.output_tokens > output_bound
                ):
                    raise ResearchError("provider_exceeded_token_bound")
                raw = completion.raw_json or completion.data.model_dump_json()
                parsed = result(raw, completion.latency_ms, 1)
                saved.status = "completed"
                saved.payload = {
                    "task_type": "metric_extraction",
                    "structured_result": raw,
                    "prompt_sha256": prompt_hash,
                    "schema_sha256": schema_hash,
                }
                session.commit()
                log.info(
                    "metric_extraction provider=openai model=%s latency_ms=%.0f",
                    identity.name,
                    completion.latency_ms,
                )
                return parsed
            except Exception as exc:
                saved.status = "failed"
                saved.error_code = (
                    exc.code
                    if isinstance(exc, ResearchError)
                    else "structured_extraction_failed"
                )
                session.commit()  # Unknown outcomes retain the reservation.
                raise ExtractionError(saved.error_code) from None
