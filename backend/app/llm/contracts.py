"""No Ollama payloads or response objects escape this boundary."""

import re
from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str = field(repr=False)

    def __post_init__(self) -> None:
        if not all(
            re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", v) for v in (self.name, self.version)
        ):
            raise ValueError("Prompts require safe, explicit names and versions")
        if not self.text.strip():
            raise ValueError("Prompt must not be empty")


@dataclass(frozen=True)
class StructuredResult(Generic[T]):
    data: T = field(repr=False)
    raw_json: str = field(repr=False)
    model: str
    model_digest: str
    prompt_name: str
    prompt_version: str
    prompt_sha256: str
    schema_sha256: str
    instruction_version: str
    latency_ms: float
    inference_latency_ms: float
    attempts: int


class ExtractionError(Exception):
    """Safe error codes only: never include request text, response bodies or URLs."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ModelIdentity:
    provider: str
    name: str
    digest: str


class StructuredExtractor(Protocol):
    async def model_identity(self) -> ModelIdentity: ...

    async def extract_structured(
        self, prompt: Prompt, schema: type[T]
    ) -> StructuredResult[T]: ...
