"""Frozen local-model evaluation; never publishes model answers as research facts.

Run: python -m app.llm.evaluate --model gemma3:4b
Gold answers stay outside the prompt. The original 18 cases are not modified.
"""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import BACKEND_DIR, get_settings
from app.extraction.quality import locate_excerpt, scope_row_matches
from app.llm.contracts import ExtractionError, Prompt
from app.llm.ollama import OllamaAdapter

VERSION = "local-fact-evaluation-v1"
FIXTURE = BACKEND_DIR.parent / "data/model-evaluation/pharma-v1.json"


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    metric: str
    value: str | None
    unit: str | None
    year: int | None
    page: int | None
    excerpt: str = Field(max_length=2200)
    status: Literal["reported", "not_found", "ambiguous"]


def prompt(case: dict[str, Any]) -> Prompt:
    supplied = {
        k: case[k] for k in ("document", "metric", "requested_year", "passages")
    }
    return Prompt(
        name="single-report-fact",
        version=VERSION,
        text=(
            "Extract only the requested metric from the supplied PDF pages. Do not use general knowledge. "
            "Preserve the original numeric value and unit without conversion. Select the requested year; "
            "if only an earlier year is disclosed, retain that earlier year. Do not add categories or infer totals. "
            "Distinguish Scope 1/2/3 and location/market methods, electricity versus energy, actuals versus targets. "
            "A net-zero target is a future value; year is its reporting year, not the target year. "
            "A table's final column is not necessarily populated for every row. Check footnotes. "
            "Return one fact with a short verbatim excerpt containing the value and its metric label. "
            "For missing disclosure use not_found, null value/unit/year/page and empty excerpt. "
            "For an uncertain row/year association use ambiguous. Never invent a value.\n"
            + json.dumps(supplied, ensure_ascii=False)
        ),
    )


def number(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", "").replace(" ", "").replace("%", ""))
    except InvalidOperation:
        return None


def score(case: dict[str, Any], fact: Fact) -> dict[str, bool]:
    gold = case["expected"]
    page = next((p for p in case["passages"] if p["page"] == fact.page), None)
    absence = gold["value"] is None
    grounded = bool(page and locate_excerpt(page["text"], fact.excerpt))
    row_ok = not (
        fact.metric
        in {"scope_1_emissions", "scope_2_location_based", "scope_2_market_based"}
        and fact.value is not None
    ) or scope_row_matches(fact.metric, fact.excerpt, fact.value or "")
    unit_ok = (fact.unit or "").casefold().split() == (
        gold["unit"] or ""
    ).casefold().split()
    correct = (
        fact.metric == case["metric"]
        and number(fact.value) == number(gold["value"])
        and fact.year == gold["year"]
    )
    empty = (
        fact.status == "not_found"
        and all(v is None for v in (fact.value, fact.unit, fact.year, fact.page))
        and not fact.excerpt
    )
    return {
        "metric_correct": fact.metric == case["metric"],
        "value_correct": number(fact.value) == number(gold["value"]),
        "unit_exact": unit_ok,
        "year_correct": fact.year == gold["year"],
        "page_correct": fact.page == gold["page"],
        "source_grounded": empty if absence else grounded and row_ok,
        "case_correct": empty
        if absence
        else correct and unit_ok and fact.page == gold["page"] and grounded and row_ok,
        "unsupported_inference": fact.value is not None
        and (absence or not grounded or not correct or not row_ok),
    }


async def run(model: str, output: Path) -> None:
    raw = FIXTURE.read_bytes()
    cases = json.loads(raw)["cases"]
    settings = get_settings().model_copy(
        update={
            "ollama_model": model,
            "llm_max_prompt_chars": 40000,
            "llm_max_output_tokens": 1024,
            "llm_timeout_seconds": 120,
        }
    )
    adapter = OllamaAdapter(settings)
    health = await adapter.health()
    if not health.ready:
        raise RuntimeError(health.error_code)
    results: list[dict[str, Any]] = []
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "version": VERSION,
        "fixture_sha256": hashlib.sha256(raw).hexdigest(),
        "model": model,
        "provider": "ollama",
        "started_at": datetime.now(UTC).isoformat(),
        "context_tokens": settings.llm_context_tokens,
    }
    for case in cases:
        result: dict[str, Any] = {"id": case["id"], "schema_valid": False}
        try:
            answer = await adapter.extract_structured(prompt(case), Fact)
            result.update(
                schema_valid=True,
                output=answer.data.model_dump(),
                checks=score(case, answer.data),
                latency_ms=answer.latency_ms,
                model_digest=answer.model_digest,
                prompt_sha256=answer.prompt_sha256,
            )
        except ExtractionError as exc:
            result["error"] = exc.code
        results.append(result)
        output.write_text(
            json.dumps({**metadata, "completed": False, "cases": results}, indent=2)
        )
        print(
            json.dumps(
                {
                    k: v
                    for k, v in result.items()
                    if k not in {"output", "model_digest", "prompt_sha256"}
                }
            ),
            flush=True,
        )
    timings = [r["latency_ms"] for r in results if "latency_ms" in r]
    summary = {
        "total": len(cases),
        "schema_valid": sum(r["schema_valid"] for r in results),
        "fully_correct": sum(
            r.get("checks", {}).get("case_correct", False) for r in results
        ),
        "source_grounded": sum(
            r.get("checks", {}).get("source_grounded", False) for r in results
        ),
        "unsupported_inferences": sum(
            r.get("checks", {}).get("unsupported_inference", False) for r in results
        ),
        "median_latency_ms": median(timings) if timings else None,
        "average_latency_ms": sum(timings) / len(timings) if timings else None,
        "hosted_cost": 0,
        "approved_for_unattended_publication": False,
    }
    output.write_text(
        json.dumps(
            {**metadata, "completed": True, "summary": summary, "cases": results},
            indent=2,
        )
    )
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=BACKEND_DIR.parent / "output/model-evaluation/local-gemma3-4b.json",
    )
    args = parser.parse_args()
    asyncio.run(run(args.model, args.output))
