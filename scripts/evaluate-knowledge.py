"""Read-only, real-corpus retrieval checks. Never calls AI or writes database records."""

import argparse
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    DocumentPage,
    KnowledgeAnswer,
    KnowledgeIndex,
    MetricObservation,
)
from app.db.session import create_database_engine
from app.knowledge.contracts import AskRequest
from app.knowledge.inspection import inspect_source
from app.knowledge.research import normalise, packet


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", type=Path, default=root / "data/knowledge_evaluation_cases.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(
            "Choose a new output path; evaluation snapshots are not overwritten."
        )
    cases = json.loads(args.cases.read_text())
    settings = get_settings()
    engine = create_database_engine(settings)
    results, inspections = [], {}
    with Session(engine) as session:
        session.execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        )
        before = {
            table.__tablename__: session.scalar(select(func.count()).select_from(table))
            for table in (MetricObservation, KnowledgeAnswer)
        }
        for key, spec in cases["sources"].items():
            report_id = UUID(spec["report_id"])
            inspected = inspect_source(session, report_id, settings, verify_file=True)
            inspections[key] = inspected
        for case in cases["cases"]:
            specs = [cases["sources"][key] for key in case["sources"]]
            request = AskRequest(
                question=case["question"],
                company_ids=[UUID(s["company_id"]) for s in specs],
                report_ids=[UUID(s["report_id"]) for s in specs],
            )
            started = time.monotonic()
            payload, coverage = packet(session, request, settings)
            latency_ms = round((time.monotonic() - started) * 1000, 2)
            anchors = []
            for anchor in case["anchors"]:
                spec = cases["sources"][anchor["source"]]
                page = session.scalar(
                    select(DocumentPage)
                    .join(
                        KnowledgeIndex,
                        KnowledgeIndex.parse_run_id == DocumentPage.parse_run_id,
                    )
                    .where(
                        KnowledgeIndex.report_id == UUID(spec["report_id"]),
                        DocumentPage.page_number == anchor["page"],
                    )
                )
                expected = normalise(anchor["quote"])
                present = page is not None and expected in normalise(page.raw_text)
                retrieved = any(
                    s["report_id"] == spec["report_id"]
                    and s["page"] == anchor["page"]
                    and expected in normalise(s["text"])
                    for s in payload["evidence"]
                )
                anchors.append(
                    {
                        **anchor,
                        "present_on_source_page": present,
                        "included_in_model_packet": retrieved,
                    }
                )
            source_ok = all(
                inspections[key]
                and inspections[key]["file_checksum_check"] == "matched"
                and inspections[key]["report_sha256"] == cases["sources"][key]["sha256"]
                for key in case["sources"]
            )
            peers_ok = len(coverage["companies"]) == len(specs) and all(
                c["status"] == "supplied" for c in coverage["companies"]
            )
            passed = (
                source_ok
                and peers_ok
                and all(
                    a["present_on_source_page"] and a["included_in_model_packet"]
                    for a in anchors
                )
            )
            results.append(
                {
                    "id": case["id"],
                    "question": case["question"],
                    "passed": passed,
                    "source_hashes_match": source_ok,
                    "all_selected_companies_supplied": peers_ok,
                    "latency_ms": latency_ms,
                    "anchors": anchors,
                    "coverage": coverage,
                    "payload": payload,
                }
            )
        after = {
            table.__tablename__: session.scalar(select(func.count()).select_from(table))
            for table in (MetricObservation, KnowledgeAnswer)
        }
    output = {
        "evaluated_at": datetime.now(UTC).isoformat(),
        "case_version": cases["version"],
        "meaning": cases["purpose"],
        "model_called": False,
        "model_accuracy": None,
        "provider_cost_usd": "0",
        "database_writes": False,
        "unchanged_row_counts": before == after,
        "row_counts": after,
        "summary": {
            "cases": len(results),
            "passed": sum(r["passed"] for r in results),
            "failed": sum(not r["passed"] for r in results),
            "median_retrieval_latency_ms": statistics.median(
                r["latency_ms"] for r in results
            ),
        },
        "source_inspections": inspections,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(output, stream, indent=2, ensure_ascii=False)
    print(
        json.dumps(
            {
                **output["summary"],
                "output": str(args.output.resolve()),
                "failed_cases": [r["id"] for r in results if not r["passed"]],
                "model_called": False,
                "database_writes": False,
            }
        )
    )
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
