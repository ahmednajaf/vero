"""CLI checkpoint gates are enforced before adding any larger cohort."""

import argparse
import asyncio
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.catalogue.seed import load_catalogue
from app.core.config import Settings
from app.db.models import PipelineRun
from app.llm.contracts import ExtractionError
from app.llm.factory import create_extractor
from app.pipeline.export import export, finish, snapshot
from app.pipeline.ledger import CHECKPOINTS, METRICS, emit
from app.pipeline.runner import (
    batch_lock,
    execute_run,
    get_run,
    profile,
    select_companies,
    verify_artifacts,
)
from app.pipeline.stages import Services


def configure(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "run-pipeline",
        help="Resumable local batches, gated at 5/20/50/100/200 companies",
    )
    parser.add_argument(
        "--year", type=int, required=True, help="Requested report/publication cycle"
    )
    parser.add_argument(
        "--observation-year",
        type=int,
        help="Metric year; defaults to --year, never inferred from filename",
    )
    parser.add_argument("--limit", type=int, default=5, choices=CHECKPOINTS)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Require an existing matching batch; resume its incomplete work",
    )
    parser.add_argument(
        "--run", type=UUID, help="Exact existing batch ID; requires --resume"
    )
    parser.add_argument("--sector")
    parser.add_argument("--country", type=str.upper)
    parser.add_argument("--company", type=UUID, action="append")
    parser.add_argument(
        "--metric",
        action="append",
        choices=[m.canonical_id for m in load_catalogue().metrics],
    )
    parser.add_argument("--top-k", type=int, default=1, choices=range(1, 7))
    status = subparsers.add_parser(
        "pipeline-status",
        help="Export all stages, failures, metric coverage and provenance",
    )
    status.add_argument("--run", type=UUID, required=True)


def run_command(args: argparse.Namespace, settings: Settings, engine: Engine) -> int:
    if args.command == "pipeline-status":
        payload = snapshot(engine, args.run)
        path = export(payload, settings.pipeline_root)
        emit(
            "pipeline_summary",
            run_id=args.run,
            **payload["summary"],
            json_export=str(path),
            csv_export=str(path.with_suffix(".csv"))
        )
        return 0
    year = args.observation_year if args.observation_year is not None else args.year
    if not 2000 <= year <= 2100:
        raise ValueError("--observation-year must be between 2000 and 2100")
    if args.run and not args.resume:
        raise ValueError("--run requires --resume")
    cohort = select_companies(
        engine,
        args.limit,
        sector=args.sector,
        country=args.country,
        companies=args.company,
    )
    connection = batch_lock(engine)
    last_id = None
    try:
        extractor = create_extractor(settings)
        identity = asyncio.run(extractor.model_identity())
        parameters = profile(
            settings,
            identity,
            args.year,
            year,
            {
                "sector": args.sector,
                "country": args.country,
                "company": sorted(str(c) for c in (args.company or [])),
            },
            tuple(dict.fromkeys(args.metric or METRICS)),
            args.top_k,
        )
        parent = None
        for checkpoint in CHECKPOINTS:
            if checkpoint > args.limit:
                break
            # --resume must not silently create an entirely different selection.
            if args.resume and parent is None:
                with Session(engine) as session:
                    from app.extraction.service import canonical, sha

                    matches = list(
                        session.scalars(
                            select(PipelineRun).where(
                                PipelineRun.profile_sha256 == sha(canonical(parameters))
                            )
                        )
                    )
                    if not any(
                        r.company_snapshot == cohort[: r.checkpoint] for r in matches
                    ):
                        raise ValueError(
                            "No matching saved batch for these filters, years, model and configuration"
                        )
                    if args.run and not any(
                        r.id == args.run
                        and r.company_snapshot == cohort[: r.checkpoint]
                        for r in matches
                    ):
                        raise ValueError(
                            "--run does not match the frozen cohort/configuration"
                        )
            run_id, reused = get_run(
                engine, parameters, cohort[:checkpoint], checkpoint, parent
            )
            last_id = run_id
            emit(
                "checkpoint_start",
                run_id=run_id,
                checkpoint=checkpoint,
                reused=reused,
                companies=checkpoint,
                model=identity.name,
                observation_year=year,
                requested_year=args.year,
            )
            # A successful previous checkpoint is re-evaluated against current
            # observation states before it is used to authorise expansion.
            with Session(engine) as session:
                saved = session.get(PipelineRun, run_id)
                assert saved is not None
                succeeded = saved.status == "succeeded"
            if not succeeded:
                asyncio.run(
                    execute_run(
                        engine,
                        settings,
                        run_id,
                        Services(engine, settings, extractor, identity),
                    )
                )
            verify_artifacts(engine, settings, run_id)
            payload = finish(engine, run_id)
            path = export(payload, settings.pipeline_root)
            emit(
                "pipeline_summary",
                run_id=run_id,
                **payload["summary"],
                json_export=str(path),
                csv_export=str(path.with_suffix(".csv"))
            )
            if not payload["summary"]["checkpoint_passed"]:
                emit(
                    "expansion_blocked",
                    run_id=run_id,
                    checkpoint=checkpoint,
                    requested_limit=args.limit,
                    reason="data_complete_checkpoint_failed",
                )
                return 1
            parent = run_id
        return 0
    except (KeyboardInterrupt, ExtractionError, RuntimeError, ValueError) as exc:
        code = exc.code if isinstance(exc, ExtractionError) else type(exc).__name__
        emit("pipeline_stopped", run_id=last_id, reason_code=code)
        if last_id:
            path = export(snapshot(engine, last_id), settings.pipeline_root)
            emit("interrupted_export", run_id=last_id, json_export=str(path))
        if isinstance(exc, ValueError):
            raise
        return 130 if isinstance(exc, KeyboardInterrupt) else 2
    finally:
        connection.rollback()
        connection.execute(
            text(
                "SELECT pg_advisory_unlock(hashtextextended('sbi-batch-coordinator', 0))"
            )
        )
        connection.commit()
        connection.close()
