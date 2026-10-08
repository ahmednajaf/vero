import argparse
import asyncio
import json
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.catalogue.seed import load_catalogue
from app.core.config import Settings
from app.db.models import ExtractionRun, Report
from app.extraction.retrieval import retrieve
from app.extraction.recheck import recheck_scope_rows
from app.extraction.service import extract_metric, inputs, observation_provenance
from app.llm.contracts import ExtractionError
from app.llm.factory import create_extractor


def configure(subparsers: Any) -> None:
    for name in ("retrieve-metrics", "extract-metrics"):
        parser = subparsers.add_parser(
            name,
            help=(
                "Bounded lexical retrieval"
                if name.startswith("retrieve")
                else "Local-only extraction of page-local candidates"
            ),
        )
        parser.add_argument(
            "--year",
            type=int,
            required=True,
            help="Observation year, NOT report publication year",
        )
        parser.add_argument("--report", type=UUID, action="append")
        parser.add_argument(
            "--metric",
            action="append",
            choices=[m.canonical_id for m in load_catalogue().metrics],
        )
        parser.add_argument("--top-k", type=int, default=3, choices=range(1, 7))
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument(
            "--output", type=Path, help="New JSON audit file; never overwrite"
        )
        if name == "extract-metrics":
            parser.add_argument(
                "--force",
                action="store_true",
                help="Retain a new attempt; never replace earlier evidence",
            )
    status = subparsers.add_parser(
        "extraction-status",
        help="Saved extraction attempts and full observation provenance",
    )
    status.add_argument("--run", type=UUID, action="append")
    status.add_argument("--limit", type=int, default=100)
    status.add_argument("--output", type=Path)
    recheck = subparsers.add_parser(
        "recheck-extractions",
        help="Audit old explicit-scope row associations without any model call",
    )
    recheck.add_argument("--run", type=UUID, action="append")
    recheck.add_argument("--limit", type=int, default=100)
    recheck.add_argument("--output", type=Path)


async def execute(
    args: argparse.Namespace, settings: Settings, engine: Engine
) -> dict[str, Any]:
    if args.command == "recheck-extractions":
        return recheck_scope_rows(engine, args.run, args.limit)
    if args.command == "extraction-status":
        with Session(engine) as session:
            query = select(ExtractionRun).where(
                ExtractionRun.stage == "extraction",
                ExtractionRun.code_version.startswith("metric-extraction-"),
            )
            if args.run:
                query = query.where(ExtractionRun.id.in_(args.run))
            runs = list(
                session.scalars(
                    query.order_by(ExtractionRun.created_at.desc()).limit(args.limit)
                )
            )
            return {
                "runs": [
                    {
                        "run_id": str(r.id),
                        "report_id": str(r.report_id),
                        "status": r.status,
                        "model": r.model_name,
                        "parameters": r.parameters,
                        "summary": r.output_summary,
                        "error_code": r.error_code,
                    }
                    for r in runs
                ],
                "observations": observation_provenance(session, [r.id for r in runs]),
            }
    with Session(engine) as session:
        query_reports = select(Report.id).where(Report.status == "downloaded")
        if args.report:
            query_reports = query_reports.where(Report.id.in_(args.report))
        reports = list(
            session.scalars(
                query_reports.order_by(Report.created_at, Report.id).limit(args.limit)
            )
        )
        if args.report and not set(args.report).issubset(reports):
            raise ValueError(
                "Requested reports missing/not downloaded or exceed --limit"
            )
    codes = list(
        dict.fromkeys(args.metric or [m.canonical_id for m in load_catalogue().metrics])
    )
    extractor = create_extractor(settings)
    identity = (
        await extractor.model_identity() if args.command == "extract-metrics" else None
    )
    outcomes = []
    run_ids = []
    for report_id in reports:
        for code in codes:
            if args.command == "retrieve-metrics":
                with Session(engine) as session:
                    _, _, _, metric, passages = inputs(session, report_id, code)
                    selected = retrieve(passages, metric, args.year, top_k=args.top_k)
                    outcomes.append(
                        {
                            "report_id": str(report_id),
                            "metric_id": code,
                            "year": args.year,
                            "candidates": [
                                {
                                    "chunk_id": str(item.passage.chunk_id),
                                    "page": item.passage.page,
                                    "score": item.score,
                                    "matched_terms": item.matched_terms,
                                    "text": item.passage.text,
                                }
                                for item in selected
                            ],
                        }
                    )
            else:
                print(
                    f"Extracting {report_id} / {code} / {args.year} locally…",
                    flush=True,
                )
                outcome = await extract_metric(
                    engine,
                    report_id,
                    code,
                    args.year,
                    settings,
                    extractor,
                    identity=identity,
                    top_k=args.top_k,
                    force=args.force,
                )
                outcomes.append(outcome)
                if "run_id" in outcome:
                    run_ids.append(UUID(outcome["run_id"]))
                summary = outcome.get("summary", {})
                print(
                    json.dumps(
                        {
                            "run_id": outcome.get("run_id"),
                            "status": outcome["status"],
                            "observation_count": summary.get("observation_count", 0),
                            "states": summary.get("persisted_states", {}),
                        }
                    ),
                    flush=True,
                )
    with Session(engine) as session:
        observations = observation_provenance(session, run_ids)
    return {
        "reports_processed": len(reports),
        "metric_jobs": len(outcomes),
        "outcomes": outcomes,
        "observations": observations,
    }


def run_command(args: argparse.Namespace, settings: Settings, engine: Engine) -> int:
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve a new path before any inference/database writes.
    output_context = (
        args.output.open("x", encoding="utf-8") if args.output else nullcontext(None)
    )
    with output_context as output:
        try:
            payload = asyncio.run(execute(args, settings, engine))
        except ExtractionError as exc:
            payload = {"status": "failed", "error_code": exc.code}
        except KeyboardInterrupt:
            payload = {
                "status": "failed",
                "error_code": "cancelled",
                "message": "Saved calls remain in the database; inspect extraction-status",
            }
        if output is not None:
            output.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            print(f"Full audit: {args.output.resolve()}")
        if args.command != "extract-metrics" or not args.output:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        return (
            1
            if payload.get("status") == "failed"
            or any(
                o["status"] in {"failed", "busy"}
                for o in payload.get("outcomes", [])
                if "status" in o
            )
            else 0
        )
