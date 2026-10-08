"""Single coordinator, bounded workers, frozen cohort, strict staged expansion."""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Company, PipelineJob, PipelineRun, Report
from app.extraction.contracts import (
    PROMPT_VERSION,
    QUALITY_VERSION,
    PIPELINE_VERSION,
    NORMALISATION_VERSION,
    RETRIEVAL_VERSION,
    SCHEMA_VERSION,
)
from app.discovery.crawler import POLICY_VERSION
from app.parsing.contracts import PARSER_VERSION
from app.parsing.engine import versions
from app.extraction.service import canonical, sha
from app.llm.contracts import ExtractionError, ModelIdentity
from app.pipeline.ledger import (
    CHECKPOINTS,
    STAGES,
    TERMINAL,
    VERSION,
    emit,
    recover,
    state,
    transition,
)
from app.pipeline.stages import Services, StageFailure


def select_companies(
    engine: Engine,
    limit: int,
    *,
    sector: str | None = None,
    country: str | None = None,
    companies: list[UUID] | None = None,
) -> list[dict[str, Any]]:
    with Session(engine) as session:
        query = select(Company).where(Company.active.is_(True))
        if sector:
            query = query.where(Company.sector == sector)
        if country:
            query = query.where(Company.country == country.upper())
        if companies:
            query = query.where(Company.id.in_(companies))
        selected = list(session.scalars(query.order_by(Company.id).limit(limit)))
        if companies and set(companies) != {c.id for c in selected}:
            raise ValueError(
                "Requested companies are missing, inactive, filtered out or exceed --limit"
            )
        if not selected or (
            len(selected) != limit
            and not (len(selected) < 5 and (companies or sector or country))
        ):
            raise ValueError(
                f"Checkpoint requires {limit} active companies; selected {len(selected)}. No work started."
            )
        return [
            {
                "id": str(c.id),
                "name": c.company_name,
                "sector": c.sector,
                "country": c.country,
                "official_domain": c.official_domain,
                "investor_relations_url": c.investor_relations_url,
                "sustainability_url": c.sustainability_url,
            }
            for c in selected
        ]


def profile(
    settings: Settings,
    identity: ModelIdentity,
    year: int,
    observation_year: int,
    filters: dict[str, Any],
    metrics: tuple[str, ...],
    top_k: int,
) -> dict[str, Any]:
    # Do not store DB credentials or arbitrary environment variables.
    return {
        "version": VERSION,
        "component_versions": {
            "extraction": PIPELINE_VERSION,
            "normalisation": NORMALISATION_VERSION,
            "retrieval": RETRIEVAL_VERSION,
            "schema": SCHEMA_VERSION,
            "discovery": POLICY_VERSION,
            "parser": PARSER_VERSION,
            "parser_libraries": versions(),
        },
        "prompt_version": PROMPT_VERSION,
        "quality_version": QUALITY_VERSION,
        "requested_year": year,
        "observation_year": observation_year,
        "filters": filters,
        "metrics": list(metrics),
        "top_k": top_k,
        "model": identity.__dict__,
        "configuration": settings.model_dump(
            mode="json",
            include={
                k
                for k in Settings.model_fields
                if k.startswith(("discovery_", "parse_", "llm_", "pipeline_"))
                and k != "pipeline_root"
            },
        ),
        "reports_root": str(settings.reports_root.resolve()),
        "checkpoint_policy": "every_company_downloaded_parsed_with_source_backed_metric",
    }


def get_run(
    engine: Engine,
    parameters: dict[str, Any],
    cohort: list[dict[str, Any]],
    checkpoint: int,
    parent: UUID | None,
) -> tuple[UUID, bool]:
    fingerprint = sha(canonical(parameters))
    with Session(engine, expire_on_commit=False) as session, session.begin():
        if checkpoint not in CHECKPOINTS or len(cohort) > checkpoint:
            raise ValueError("Invalid checkpoint cohort")
        if checkpoint > 5:
            previous = session.get(PipelineRun, parent) if parent else None
            required = CHECKPOINTS[CHECKPOINTS.index(checkpoint) - 1]
            if (
                previous is None
                or previous.status != "succeeded"
                or previous.checkpoint != required
                or previous.profile_sha256 != fingerprint
                or previous.company_snapshot != cohort[:required]
                or not previous.summary.get("checkpoint_passed")
            ):
                raise ValueError(
                    "Earlier matching data-complete checkpoint is required"
                )
        for prior in session.scalars(
            select(PipelineRun)
            .where(
                PipelineRun.profile_sha256 == fingerprint,
                PipelineRun.checkpoint == checkpoint,
            )
            .order_by(PipelineRun.created_at.desc())
        ):
            if prior.company_snapshot == cohort:
                return prior.id, True
        run = PipelineRun(
            profile_sha256=fingerprint,
            checkpoint=checkpoint,
            requested_year=parameters["requested_year"],
            observation_year=parameters["observation_year"],
            parameters=parameters,
            company_snapshot=cohort,
            parent_run_id=parent,
        )
        session.add(run)
        session.flush()
        inherited = {}
        if parent:
            inherited = {
                (str(j.company_id), j.stage, j.metric_code): j
                for j in session.scalars(
                    select(PipelineJob).where(
                        PipelineJob.run_id == parent, PipelineJob.status == "succeeded"
                    )
                )
            }
        for company in cohort:
            for stage in STAGES:
                codes = parameters["metrics"] if stage in STAGES[3:] else [""]
                for code in codes:
                    old = inherited.get((company["id"], stage, code))
                    job = PipelineJob(
                        run_id=run.id,
                        company_id=UUID(company["id"]),
                        stage=stage,
                        metric_code=code,
                        status="succeeded" if old else "pending",
                        result=(
                            {**old.result, "inherited_from_job_id": str(old.id)}
                            if old
                            else {}
                        ),
                    )
                    session.add(job)
        return run.id, False


async def execute_run(
    engine: Engine, settings: Settings, run_id: UUID, services: Services
) -> None:
    recover(engine, run_id)
    with Session(engine) as session, session.begin():
        run = session.get(PipelineRun, run_id)
        assert run is not None
        run.status, run.finished_at = "running", None
        parameters: dict[str, Any] = dict(run.parameters)
        cohort = list(run.company_snapshot)
        jobs = {
            (str(j.company_id), j.stage, j.metric_code): j.id
            for j in session.scalars(
                select(PipelineJob).where(PipelineJob.run_id == run_id)
            )
        }
    semaphore = asyncio.Semaphore(settings.pipeline_company_workers)
    halted = asyncio.Event()

    def halt() -> None:
        if settings.pipeline_fail_fast:
            halted.set()

    async def job(
        company: str,
        stage: str,
        code: str,
        operation: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any] | None:
        identifier = jobs[company, stage, code]
        saved = state(engine, identifier)
        if saved.status == "succeeded":
            emit(
                "stage_reused",
                run_id=run_id,
                job_id=identifier,
                stage=stage,
                company_id=company,
                metric=code,
            )
            return saved.result
        if saved.status in TERMINAL or (
            saved.status == "failed" and not saved.retryable
        ):
            halt()
            return None
        if halted.is_set() and stage not in {"validate", "normalise", "store"}:
            transition(
                engine, identifier, "blocked", reason="checkpoint_stopped_after_failure"
            )
            return None
        if saved.attempts >= settings.pipeline_job_max_attempts:
            transition(
                engine,
                identifier,
                "failed",
                reason="retry_budget_exhausted",
                result={**saved.result, "last_failure": saved.reason_code},
            )
            halt()
            return None
        # One stage attempt per invocation. Transport retries are bounded inside
        # requests/Ollama; resume retries transient failed stages, not HTTP controls.
        if saved.attempts:
            await asyncio.sleep(min(2 ** (saved.attempts - 1), 4))
        transition(engine, identifier, "running")
        try:
            result = await operation()
        except StageFailure as exc:
            halt()
            transition(
                engine,
                identifier,
                exc.status,
                result=exc.details,
                reason=exc.code,
                retryable=exc.retryable,
            )
            return None
        except ExtractionError as exc:
            halt()
            transition(
                engine,
                identifier,
                "failed",
                reason=exc.code,
                retryable=exc.code
                in {"timeout", "server_unavailable", "connection_failed"},
            )
            return None
        except (OSError, ValueError) as exc:
            halt()
            transition(
                engine,
                identifier,
                "failed",
                reason="integrity_or_configuration_" + type(exc).__name__,
            )
            return None
        except asyncio.CancelledError:
            transition(engine, identifier, "failed", reason="cancelled", retryable=True)
            raise
        except Exception as exc:
            halt()
            transition(
                engine, identifier, "failed", reason="unexpected_" + type(exc).__name__
            )
            raise
        transition(engine, identifier, "succeeded", result=result)
        return result

    def block(company: str, failed_stage: str, code: str | None = None) -> None:
        for (cid, stage, metric), identifier in jobs.items():
            if (
                cid != company
                or STAGES.index(stage) <= STAGES.index(failed_stage)
                or (code is not None and metric != code)
            ):
                continue
            saved = state(engine, identifier)
            if saved.status in {"pending", "blocked"}:
                transition(
                    engine, identifier, "blocked", reason="upstream_" + failed_stage
                )

    async def company_worker(company: dict[str, Any]) -> None:
        async with semaphore:
            cid = company["id"]
            discovered = await job(
                cid,
                "discover",
                "",
                lambda: asyncio.to_thread(
                    services.discover, UUID(cid), int(parameters["requested_year"])
                ),
            )
            if discovered is None:
                block(cid, "discover")
                return
            report_id = UUID(discovered["report_id"])
            downloaded = await job(
                cid,
                "download",
                "",
                lambda: asyncio.to_thread(services.download, report_id),
            )
            if downloaded is None:
                block(cid, "download")
                return
            parsed = await job(cid, "parse", "", lambda: services.parse(report_id))
            if parsed is None:
                block(cid, "parse")
                return
            for code in parameters["metrics"]:
                year, top_k = int(parameters["observation_year"]), int(
                    parameters["top_k"]
                )
                passages = await job(
                    cid,
                    "retrieve",
                    code,
                    lambda: asyncio.to_thread(
                        services.retrieval, report_id, code, year, top_k
                    ),
                )
                if passages is None:
                    block(cid, "retrieve", code)
                    continue
                extracted = await job(
                    cid,
                    "extract",
                    code,
                    lambda: services.extract(report_id, code, year, top_k),
                )
                if extracted is None:
                    block(cid, "extract", code)
                    continue
                for stage in ("validate", "normalise", "store"):
                    receipt = await job(
                        cid,
                        stage,
                        code,
                        lambda: asyncio.to_thread(
                            services.receipt,
                            UUID(extracted["extraction_run_id"]),
                            stage,
                        ),
                    )
                    if receipt is None:
                        block(cid, stage, code)
                        break

    try:
        # Await all workers on ordinary exceptions; never release the process lock
        # while a thread is still mutating a report. asyncio.run drains threads.
        results = await asyncio.gather(
            *(company_worker(c) for c in cohort), return_exceptions=True
        )
        failures = [r for r in results if isinstance(r, BaseException)]
        if failures:
            raise RuntimeError("worker_failure; inspect stage events") from failures[0]
    except BaseException:
        with Session(engine) as session, session.begin():
            current = session.get(PipelineRun, run_id)
            assert current is not None
            current.status = "interrupted"
        raise


def verify_artifacts(engine: Engine, settings: Settings, run_id: UUID) -> None:
    with Session(engine) as session:
        jobs = list(
            session.scalars(
                select(PipelineJob).where(
                    PipelineJob.run_id == run_id,
                    PipelineJob.stage == "download",
                    PipelineJob.status == "succeeded",
                )
            )
        )
        for job in jobs:
            report = session.get(Report, UUID(str(job.result["report_id"])))
            code = None
            try:
                if (
                    report is None
                    or not report.storage_key
                    or not report.content_sha256
                ):
                    raise ValueError("artifact_metadata_missing")
                root = settings.reports_root.resolve()
                path = (root / report.storage_key).resolve()
                if not path.is_relative_to(root):
                    raise ValueError("unsafe_path")
                with path.open("rb") as handle:
                    digest = hashlib.file_digest(handle, "sha256").hexdigest()
                if (
                    digest != report.content_sha256
                    or path.stat().st_size != report.file_size_bytes
                ):
                    raise ValueError("artifact_checksum_mismatch")
            except OSError:
                code = "artifact_unreadable"
            except ValueError as exc:
                code = str(exc)
            if code:
                transition(engine, job.id, "failed", reason=code, result=job.result)


def batch_lock(engine: Engine) -> Any:
    # Dedicated connection held by CLI through asyncio.run, including thread drain.
    connection = engine.connect()
    acquired = connection.scalar(
        text(
            "SELECT pg_try_advisory_lock(hashtextextended('sbi-batch-coordinator', 0))"
        )
    )
    connection.commit()
    if not acquired:
        connection.close()
        raise ValueError("Another batch coordinator is running; no work started")
    return connection
