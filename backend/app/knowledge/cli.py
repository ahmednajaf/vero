import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Company, KnowledgeJob, Report
from app.knowledge.contracts import Scope, SearchRequest
from app.knowledge.indexing import index_report
from app.knowledge.ingestion import queue, run_jobs
from app.knowledge.search import coverage, search


def configure(subparsers: Any) -> None:
    snapshot = subparsers.add_parser(
        "import-company-snapshot",
        help="Atomically import the sourced JSON universe; no network, no metrics, existing identities preserved",
    )
    snapshot.add_argument("path", type=Path)
    collect = subparsers.add_parser(
        "collect-reports",
        help="Run the full official-report cohort; continue through gaps; no AI",
    )
    collect.add_argument("--year", type=int, default=2025)
    collect.add_argument("--limit", type=int, default=500)
    collect.add_argument("--company", type=UUID, action="append")
    collect.add_argument("--sector")
    collect.add_argument("--country")
    collect.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    collect.add_argument("--parse-workers", type=int, choices=(1, 2), default=1)
    collect.add_argument("--max-pages", type=int, choices=range(1, 101), default=10)
    collect.add_argument("--allow-js", action="store_true")
    collect.add_argument("--no-search", action="store_true")
    collect.add_argument(
        "--allow-unlabelled-year",
        action="store_true",
        help="Retain otherwise eligible official PDFs with unknown year labels for search, never requested-year coverage",
    )
    collect.add_argument(
        "--allow-prior-year",
        action="store_true",
        help="If no requested-year report is found, retain a discovered prior-year report with its real year; never count it as requested-year coverage",
    )
    collect.add_argument(
        "--resume",
        type=UUID,
        help="Resume the frozen cohort/configuration of this run ID",
    )
    status = subparsers.add_parser(
        "collection-status", help="Exact per-company source manifest and failures"
    )
    status.add_argument("run_id", type=UUID)
    indexing = subparsers.add_parser(
        "knowledge-index",
        help="Index ALL retained pages/tables from downloaded parsed official reports; no network or AI",
    )
    indexing.add_argument(
        "--report",
        type=UUID,
        action="append",
        required=True,
        help="Explicitly selected source report; historic records are never bulk-promoted",
    )
    indexing.add_argument("--limit", type=int, default=500)
    ingest = subparsers.add_parser(
        "knowledge-ingest",
        help="Discover, download, parse and index up to 500 companies, continuing on failures; no AI",
    )
    ingest.add_argument("--year", type=int, required=True)
    ingest.add_argument("--limit", type=int, default=20)
    cohort = ingest.add_mutually_exclusive_group(required=True)
    cohort.add_argument(
        "--company",
        type=UUID,
        action="append",
        help="Explicitly selected current-universe company; repeatable",
    )
    cohort.add_argument(
        "--all-active",
        action="store_true",
        help="Explicitly select the active registry; inspect/import the new universe first",
    )
    ingest.add_argument("--sector")
    ingest.add_argument("--country")
    ingest.add_argument(
        "--report",
        type=UUID,
        action="append",
        help="Explicitly registered official report UUID; requires exactly one --company; no old reports are substituted",
    )
    ingest.add_argument(
        "--resume",
        action="store_true",
        help="Retry incomplete jobs, reusing completed downloads/parses",
    )
    ingest.add_argument(
        "--refresh",
        action="store_true",
        help="Explicitly retry discovery including completed jobs; retained source files are never overwritten",
    )
    ingest.add_argument(
        "--reuse-retained",
        action="store_true",
        help="Explicitly opt into historic retained reports; default requires fresh discovery",
    )
    subparsers.add_parser(
        "knowledge-status",
        help="Coverage and ingestion outcomes, not a metric quality score",
    )
    query = subparsers.add_parser(
        "knowledge-search",
        help="Search indexed report content beyond the metric catalogue",
    )
    query.add_argument("query")
    query.add_argument("--company", type=UUID, action="append")
    query.add_argument("--limit", type=int, default=10)
    recover = subparsers.add_parser(
        "knowledge-recover-ai",
        help="Operator recovery of a crashed research call; retains its entire cost reservation",
    )
    recover.add_argument("answer_id", type=UUID)


def run_command(args: argparse.Namespace, settings: Settings, engine: Engine) -> int:
    if args.command == "import-company-snapshot":
        from app.core.config import BACKEND_DIR
        from app.services.company_snapshot import import_snapshot

        path = args.path if args.path.is_file() else BACKEND_DIR.parent / args.path
        print(json.dumps(import_snapshot(path, engine), indent=2))
        return 0
    if args.command in {"collect-reports", "collection-status"}:
        from app.knowledge.collection import (
            create_collection,
            export_snapshot,
            run_collection,
        )

        if args.command == "collection-status":
            data = export_snapshot(
                engine,
                args.run_id,
                settings.pipeline_root.parent / "collections" / str(args.run_id),
            )
        else:
            run_id = args.resume
            if not run_id:
                with Session(engine) as session:
                    query = select(Company.id).where(Company.active.is_(True))
                    if args.company:
                        query = query.where(Company.id.in_(args.company))
                    if args.sector:
                        query = query.where(Company.sector == args.sector)
                    if args.country:
                        query = query.where(Company.country == args.country.upper())
                    ids = list(
                        session.scalars(
                            query.order_by(Company.company_name, Company.id).limit(
                                args.limit
                            )
                        )
                    )
                run_id = create_collection(
                    engine,
                    ids,
                    args.year,
                    {
                        "workers": args.workers,
                        "parse_workers": args.parse_workers,
                        "max_pages": args.max_pages,
                        "search_fallback": not args.no_search,
                        "allow_js": args.allow_js,
                        "allow_prior_year": args.allow_prior_year,
                        "allow_unlabelled_year": args.allow_unlabelled_year,
                    },
                )
            data = run_collection(engine, run_id, settings)
        print(json.dumps({k: v for k, v in data.items() if k != "companies"}, indent=2))
        return 0 if data["status"] in {"completed", "running"} else 2
    if args.command == "knowledge-index":
        with Session(engine) as session:
            query = select(Report.id).where(
                Report.status == "downloaded", Report.source_policy == "official"
            )
            if args.report:
                query = query.where(Report.id.in_(args.report))
            identifiers = list(
                session.scalars(query.order_by(Report.id).limit(args.limit))
            )
        outcomes = []
        for identifier in identifiers:
            try:
                outcome = index_report(engine, identifier, settings)
            except (ValueError, OSError) as exc:
                outcome = {
                    "report_id": str(identifier),
                    "status": "failed",
                    "reason": str(exc)
                    if isinstance(exc, ValueError)
                    else type(exc).__name__,
                }
            outcomes.append(outcome)
            print(json.dumps(outcome), flush=True)
        print(
            json.dumps(
                {
                    "processed": len(outcomes),
                    "outcomes": dict(Counter(o["status"] for o in outcomes)),
                }
            )
        )
        return int(any(o["status"] == "failed" for o in outcomes))
    if args.command == "knowledge-ingest":
        with Session(engine) as session:
            query = select(Company.id).where(Company.active.is_(True))
            if args.company:
                query = query.where(Company.id.in_(args.company))
            if args.sector:
                query = query.where(Company.sector == args.sector)
            if args.country:
                query = query.where(Company.country == args.country.upper())
            identifiers = list(
                session.scalars(
                    query.order_by(Company.company_name, Company.id).limit(args.limit)
                )
            )
        if args.report and (not args.company or len(identifiers) != 1 or args.refresh):
            raise ValueError(
                "--report requires exactly one selected --company and cannot be combined with --refresh"
            )
        result = run_jobs(
            engine,
            queue(engine, identifiers, args.year),
            settings,
            resume=args.resume,
            refresh=args.refresh,
            reuse_retained=args.reuse_retained,
            source_report_ids=args.report,
        )
        print(
            json.dumps(
                {
                    "companies_selected": len(identifiers),
                    "requested_limit": args.limit,
                    "outcomes": dict(Counter(r["status"] for r in result)),
                }
            )
        )
        return int(any(r["status"] != "succeeded" for r in result))
    with Session(engine) as session:
        if args.command == "knowledge-search":
            print(
                json.dumps(
                    search(
                        session,
                        SearchRequest(
                            query=args.query,
                            company_ids=args.company or [],
                            limit=min(args.limit, 100),
                        ),
                    ),
                    indent=2,
                )
            )
        elif args.command == "knowledge-recover-ai":
            from datetime import UTC, datetime, timedelta

            from app.db.models import KnowledgeAnswer

            answer = session.get(KnowledgeAnswer, args.answer_id, with_for_update=True)
            if (
                not answer
                or answer.status != "running"
                or answer.created_at > datetime.now(UTC) - timedelta(minutes=10)
            ):
                raise ValueError(
                    "Only interrupted research calls older than ten minutes can be recovered"
                )
            answer.status, answer.error_code = (
                "failed",
                "operator_recovered_interrupted_call",
            )
            session.commit()
            print(
                json.dumps(
                    {
                        "answer_id": str(answer.id),
                        "status": answer.status,
                        "reservation_retained": True,
                    }
                )
            )
        else:
            states = Counter(session.scalars(select(KnowledgeJob.status)))
            print(
                json.dumps(
                    {**coverage(session, Scope()), "ingestion_jobs": dict(states)},
                    indent=2,
                )
            )
    return 0
