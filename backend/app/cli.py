"""Run from backend/: python -m app.cli import-companies data/company_universe.csv."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, get_settings
from app.db.session import create_database_engine
from app.db.models import Company, Report
from app.discovery.service import (
    discover_company,
    download_report,
    latest_runs,
    status_snapshot,
)
from app.services.company_import import import_companies
from app.parsing.service import parse_report, parse_status
from app.extraction.cli import (
    configure as configure_extraction,
    run_command as run_extraction,
)
from app.pipeline.cli import (
    configure as configure_pipeline,
    run_command as run_pipeline,
)
from app.knowledge.cli import configure as configure_knowledge, run_command as run_knowledge


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Company universe, official reports, page-aware parsing and explicit local metric extraction"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    configure_extraction(subparsers)
    configure_pipeline(subparsers)
    configure_knowledge(subparsers)
    curated = subparsers.add_parser(
        "register-reports",
        help="Register explicitly researched official sources; does not download or approve metrics",
    )
    curated.add_argument("manifest", type=Path)
    review_parse = subparsers.add_parser(
        "review-parse-pages",
        help="Record explicit visual dispositions for flagged pages; never approve metric values",
    )
    review_parse.add_argument("manifest", type=Path)
    fact_review = subparsers.add_parser(
        "review-source-facts",
        help="Apply explicit source-table reviews with checksum checks; no peer admission",
    )
    fact_review.add_argument("manifest", type=Path)
    benchmark = subparsers.add_parser(
        "build-benchmarks",
        help="Persist a deterministic benchmark snapshot from existing reviewed evidence only; no collection or inference",
    )
    benchmark.add_argument("--year", type=int, required=True)
    benchmark.add_argument(
        "--peer-group",
        choices=["sector", "country", "region", "industry", "revenue_band"],
        default="sector",
    )
    benchmark.add_argument("--min-peers", type=int, choices=range(5, 501), default=5)
    benchmark.add_argument(
        "--scope2-method",
        choices=["location_based", "market_based"],
        default="location_based",
    )
    importer = subparsers.add_parser(
        "import-companies", help="Atomically insert/update companies by CSV UUID"
    )
    importer.add_argument("csv_path", type=Path)
    importer.add_argument(
        "--report",
        type=Path,
        help="New JSON report path; existing files are never overwritten",
    )
    discovery = subparsers.add_parser(
        "discover-reports", help="Bounded official-site report discovery"
    )
    discovery.add_argument("--year", type=int, required=True)
    discovery.add_argument("--limit", type=int, default=20)
    discovery.add_argument(
        "--company",
        type=UUID,
        action="append",
        help="Restrict to company UUID; repeatable",
    )
    discovery.add_argument(
        "--allow-js",
        action="store_true",
        help="Opt in to restricted browser fallback for clear JS shells only",
    )
    downloader = subparsers.add_parser(
        "download-reports",
        help="Download selected reports from latest completed discovery jobs",
    )
    downloader.add_argument("--year", type=int)
    downloader.add_argument("--company", type=UUID, action="append")
    downloader.add_argument("--limit", type=int, default=20)
    status = subparsers.add_parser(
        "report-status",
        help="JSON status and candidate evidence, latest job per company/year",
    )
    status.add_argument("--year", type=int)
    status.add_argument("--company", type=UUID, action="append")
    status.add_argument(
        "--output", type=Path, help="Also save JSON to a new file (never overwrite)"
    )
    parse = subparsers.add_parser(
        "parse-reports",
        help="Parse verified downloaded PDFs into page-aware text and tables; no OCR",
    )
    parse.add_argument("--year", type=int)
    parse.add_argument(
        "--report",
        type=UUID,
        action="append",
        help="Downloaded report UUID; repeatable",
    )
    parse.add_argument("--limit", type=int, default=20)
    parse.add_argument(
        "--force",
        action="store_true",
        help="New immutable attempt even if this parser/input profile succeeded before",
    )
    parsed = subparsers.add_parser(
        "parse-status", help="Latest parse quality and warnings for downloaded reports"
    )
    parsed.add_argument("--year", type=int)
    parsed.add_argument("--report", type=UUID, action="append")
    parsed.add_argument(
        "--examples",
        type=int,
        default=0,
        choices=range(0, 6),
        help="Include up to five page-aware chunk examples per report",
    )
    parsed.add_argument(
        "--output", type=Path, help="Save JSON to a new file, never overwrite"
    )
    args = parser.parse_args(argv)
    if args.command != "import-companies":
        if getattr(args, "year", None) is not None and not 2000 <= args.year <= 2100:
            parser.error("--year must be between 2000 and 2100")
        if not 1 <= getattr(args, "limit", 20) <= 500:
            parser.error("--limit must be between 1 and 500")
        config = get_settings()
        if args.command == "collect-reports":
            # Company job locks, per-domain pacing and parser transactions use
            # separate connections. This remains bounded for eight workers.
            config = config.model_copy(update={"database_pool_size": 12, "database_max_overflow": 8})
        if getattr(args, "allow_js", False):
            config = config.model_copy(update={"discovery_allow_js": True})
        report_engine = create_database_engine(config)
        try:
            if args.command.startswith("knowledge-") or args.command in {"collect-reports", "collection-status", "import-company-snapshot"}:
                return run_knowledge(args, config, report_engine)
            if args.command == "review-source-facts":
                from app.extraction.review import review_facts

                print(
                    json.dumps(
                        review_facts(report_engine, config, args.manifest), indent=2
                    )
                )
                return 0
            if args.command == "review-parse-pages":
                from app.parsing.review import save_review

                print(json.dumps(save_review(report_engine, args.manifest)))
                return 0
            if args.command == "register-reports":
                from app.discovery.curation import register_sources

                print(
                    json.dumps(
                        register_sources(args.manifest, report_engine, config), indent=2
                    )
                )
                return 0
            if args.command == "build-benchmarks":
                from app.benchmarking.service import calculate, persist

                with Session(report_engine) as session, session.begin():
                    session.connection(
                        execution_options={"isolation_level": "REPEATABLE READ"}
                    )
                    benchmark_payload = calculate(
                        session,
                        year=args.year,
                        peer_group=args.peer_group,
                        min_peers=args.min_peers,
                        scope2_method=args.scope2_method,
                    )
                    snapshot_id = persist(session, benchmark_payload)
                print(
                    json.dumps(
                        {
                            "snapshot_id": str(snapshot_id),
                            "input_sha256": benchmark_payload["input_sha256"],
                            "companies": benchmark_payload["total"],
                            "scored": sum(
                                c["score"]["value"] is not None
                                for c in benchmark_payload["items"]
                            ),
                            "label": benchmark_payload["label"],
                        }
                    )
                )
                return 0
            if args.command in {"run-pipeline", "pipeline-status"}:
                return run_pipeline(args, config, report_engine)
            if args.command in {
                "retrieve-metrics",
                "extract-metrics",
                "extraction-status",
                "recheck-extractions",
            }:
                return run_extraction(args, config, report_engine)
            if args.command == "parse-reports":
                with Session(report_engine) as session:
                    parse_query = select(Report).where(Report.status == "downloaded")
                    if args.year is not None:
                        parse_query = parse_query.where(
                            Report.requested_year == args.year
                        )
                    if args.report:
                        parse_query = parse_query.where(Report.id.in_(args.report))
                    report_ids = list(
                        session.scalars(
                            parse_query.with_only_columns(Report.id)
                            .order_by(Report.created_at, Report.id)
                            .limit(args.limit)
                        )
                    )
                outcomes: dict[str, int] = {}
                for report_id in report_ids:
                    print(f"Parsing {report_id}…", flush=True)
                    parse_outcome = parse_report(
                        report_engine, report_id, config, force=args.force
                    )
                    outcomes[parse_outcome["status"]] = (
                        outcomes.get(parse_outcome["status"], 0) + 1
                    )
                    compact = {
                        **parse_outcome,
                        "quality": {
                            key: value
                            for key, value in (
                                parse_outcome.get("quality") or {}
                            ).items()
                            if key != "warnings"
                        },
                    }
                    print(json.dumps(compact, ensure_ascii=False), flush=True)
                print(
                    json.dumps(
                        {"reports_processed": len(report_ids), "outcomes": outcomes}
                    ),
                    flush=True,
                )
                return 1 if outcomes.get("failed") else 0
            with Session(report_engine, expire_on_commit=False) as session:
                if args.command in {"report-status", "parse-status"}:
                    payload = json.dumps(
                        (
                            parse_status(
                                session,
                                report_ids=args.report,
                                year=args.year,
                                examples=args.examples,
                            )
                            if args.command == "parse-status"
                            else status_snapshot(session, args.year, args.company)
                        ),
                        indent=2,
                    )
                    if args.output:
                        args.output.parent.mkdir(parents=True, exist_ok=True)
                        with args.output.open("x", encoding="utf-8") as output:
                            output.write(payload + "\n")
                    print(payload)
                elif args.command == "discover-reports":
                    query = select(Company).where(Company.active.is_(True))
                    if args.company:
                        query = query.where(Company.id.in_(args.company))
                    companies = list(
                        session.scalars(
                            query.order_by(Company.company_name, Company.id).limit(
                                args.limit
                            )
                        )
                    )
                    for company in companies:
                        print(
                            f"Discovering {company.company_name} ({args.year})…",
                            flush=True,
                        )
                        run = discover_company(session, company, args.year, config)
                        print(
                            f"  {run.status}: {run.selection_reason} [pages={run.pages_visited}, requests={run.http_requests}]",
                            flush=True,
                        )
                    print(
                        f"Completed {len(companies)} company discovery jobs. See report-status for alternatives and diagnostics."
                    )
                else:
                    runs = latest_runs(session, args.year, args.company)
                    reports = list(
                        session.scalars(
                            select(Report)
                            .where(
                                Report.discovery_run_id.in_([r.id for r in runs]),
                                Report.is_selected.is_(True),
                                Report.status != "downloaded",
                            )
                            .order_by(Report.created_at, Report.id)
                            .limit(args.limit)
                        )
                    )
                    for report in reports:
                        report_company = session.get(Company, report.company_id)
                        assert report_company is not None
                        message = download_report(
                            session, report, report_company, config
                        )
                        print(
                            f"{report_company.company_name}: {report.status} — {message}",
                            flush=True,
                        )
                    print(f"Processed {len(reports)} selected reports.")
            return 0
        except (SQLAlchemyError, OSError, ValueError) as exc:
            print(
                f"Report command could not complete ({type(exc).__name__}); check database migrations and configuration."
            )
            return 2
        finally:
            report_engine.dispose()
    source = args.csv_path
    # Support the documented command from backend/ while keeping one canonical root data/.
    if not source.is_absolute() and not source.exists():
        source = BACKEND_DIR.parent / source
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_path = (
        args.report
        or BACKEND_DIR
        / "storage"
        / "imports"
        / f"companies-{stamp}-{uuid4().hex[:8]}.json"
    )
    engine: Engine | None = None
    try:
        if not source.is_file():
            raise FileNotFoundError(f"CSV not found: {source}")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        # Reserve a writable report before mutating the database.
        with report_path.open("x", encoding="utf-8") as report_file:
            engine = create_database_engine(get_settings())
            summary = import_companies(source, engine)
            json.dump(summary.as_dict(), report_file, ensure_ascii=False, indent=2)
            report_file.write("\n")
        outcome = "COMMITTED" if summary.committed else "REJECTED (no database changes)"
        print(
            f"{outcome}: rows={summary.total_rows} inserted={summary.inserted} updated={summary.updated} "
            f"unchanged={summary.unchanged} rejected_rows={summary.rejected_rows} errors={len(summary.errors)}"
        )
        print(f"Import report: {report_path.resolve()}")
        for error in summary.errors[:10]:
            print(f"  row {error.source_row} [{error.field}]: {error.message}")
        return 0 if summary.committed else 1
    except (OSError, ValueError) as exc:
        print(f"Import could not run: {exc}")
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
