"""Explicit, synthetic local inference only; never reads company report data."""

import argparse
import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.llm import ExtractionError, create_extractor
from app.llm.prompts import SMOKE_PROMPT, SYSTEM_INSTRUCTION, SmokeResponse


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One explicit local structured-output smoke test; no download"
    )
    parser.add_argument(
        "--output", type=Path, help="New JSON evidence file, never overwrite"
    )
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("Output already exists")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    # Do not enable HTTP wire/debug logging, which can include request content.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        settings = get_settings()
        adapter = create_extractor(settings)
        result = asyncio.run(adapter.extract_structured(SMOKE_PROMPT, SmokeResponse))
    except ExtractionError as exc:
        print(json.dumps({"status": "failed", "error_code": exc.code}))
        return 1
    evidence = {
        "tested_at": datetime.now(UTC).isoformat(),
        "provider": settings.llm_provider,
        "selected_model": result.model,
        "model_digest": result.model_digest,
        "prompt_name": result.prompt_name,
        "prompt_version": result.prompt_version,
        "instruction_version": result.instruction_version,
        "system_instruction": SYSTEM_INSTRUCTION,
        "prompt": SMOKE_PROMPT.text,
        "schema": SmokeResponse.model_json_schema(),
        "prompt_sha256": result.prompt_sha256,
        "schema_sha256": result.schema_sha256,
        "response": result.data.model_dump(),
        "raw_response": result.raw_json,
        "inference_latency_ms": result.inference_latency_ms,
        "total_latency_ms": result.latency_ms,
        "generation_attempts": result.attempts,
        "new_model_downloaded": False,
        "company_reports_used": False,
    }
    output = json.dumps(evidence, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as file:
            file.write(output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
