"""Opt-in, budget-controlled real-library evaluation. No inference without --live.

backend/.venv/bin/python scripts/evaluate-research-workflow.py --live --case specific-fact
This records observations, not a fabricated accuracy score. Review claims and pages.
"""

# ruff: noqa: E402
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from app.core.config import Settings
from app.db.models import KnowledgeAnswer
from app.knowledge.contracts import AskRequest
from app.knowledge.provider import PROMPT_VERSION, ResearchError
from app.knowledge.research import ask


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--output", default="outputs/research-workflow-evaluation.json")
    args = parser.parse_args()
    cases = json.loads((ROOT / "data/research_workflow_cases.json").read_text())
    if not args.live:
        print(json.dumps({"live_calls": False, "cases": cases}, indent=2))
        return
    if not args.case or set(args.case) - {c["id"] for c in cases}:
        parser.error("Live evaluation requires explicit, valid --case IDs.")
    settings = Settings()
    engine = create_engine(settings.database_url.get_secret_value())
    with Session(engine) as db:
        if db.scalar(
            select(func.count())
            .select_from(KnowledgeAnswer)
            .where(KnowledgeAnswer.status == "running")
        ):
            parser.error("An analysis is already running; wait before evaluating.")
    results = []
    for case in cases:
        if case["id"] not in args.case:
            continue
        with Session(engine, expire_on_commit=False) as db:
            try:
                result = await ask(db, AskRequest(question=case["question"]), settings)
                results.append({**case, "result": result})
                print(
                    json.dumps(
                        {
                            "case": case["id"],
                            "answer_id": result.get("answer_id"),
                            "status": result["status"],
                            "intent": result.get("research_plan", {}).get("intent"),
                            "queries": result.get("research_plan", {}).get("queries"),
                            "companies": result.get("retrieval_scope", {}).get(
                                "company_names"
                            ),
                            "claims": [c["text"] for c in result["claims"]],
                            "notes": result.get("notes"),
                            "validation": result.get("validation"),
                            "usage": result.get("usage"),
                            "cost": result.get("estimated_cost_usd"),
                        }
                    ),
                    flush=True,
                )
            except ResearchError as error:
                results.append({**case, "error_code": error.code})
                print(
                    json.dumps({"case": case["id"], "error_code": error.code}),
                    flush=True,
                )
        # Persist after each case so interruptions do not erase known outcomes.
        path = ROOT / args.output
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "model": settings.openai_model,
                    "prompt_version": PROMPT_VERSION,
                    "note": "Real outputs for manual assessment; source checks alone are not an accuracy evaluation.",
                    "cases": results,
                },
                indent=2,
            )
        )
    engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
