"""Committed job boundaries; a process lock makes abandoned leases recoverable."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import PipelineEvent, PipelineJob

STAGES = (
    "discover",
    "download",
    "parse",
    "retrieve",
    "extract",
    "validate",
    "normalise",
    "store",
)
METRICS = (
    "scope_1_emissions",
    "scope_2_location_based",
    "scope_2_market_based",
    "scope_3_emissions",
    "renewable_energy_percent",
    "net_zero_target_year",
    "assurance_status",
)
CHECKPOINTS = (5, 20, 50, 100, 200)
VERSION = "resumable-batch-v1.2"
TERMINAL = {"succeeded", "needs_review", "unavailable"}
RETRYABLE = {
    "timeout",
    "network",
    "dns",
    "transfer",
    "transfer_timeout",
    "http_error",
    "busy",
    "server_unavailable",
    "connection_failed",
    "interrupted",
    "cancelled",
}


def emit(event: str, **fields: Any) -> None:
    # Whitelisted identifiers/statuses only. No environment, URL credentials,
    # source excerpts, exception text or model prompts in operational logs.
    print(
        json.dumps(
            {"timestamp": datetime.now(UTC).isoformat(), "event": event, **fields},
            default=str,
        ),
        flush=True,
    )


def state(engine: Engine, job_id: UUID) -> PipelineJob:
    with Session(engine, expire_on_commit=False) as session:
        job = session.get(PipelineJob, job_id)
        assert job is not None
        return job


def transition(
    engine: Engine,
    job_id: UUID,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    reason: str | None = None,
    retryable: bool = False
) -> PipelineJob:
    with Session(engine, expire_on_commit=False) as session, session.begin():
        job = session.scalar(
            select(PipelineJob).where(PipelineJob.id == job_id).with_for_update()
        )
        assert job is not None
        if status == "running":
            job.attempts += 1
            job.started_at, job.finished_at = datetime.now(UTC), None
        else:
            job.finished_at = datetime.now(UTC)
        job.status, job.reason_code, job.retryable = status, reason, retryable
        if result is not None:
            job.result = result
        session.add(
            PipelineEvent(
                job_id=job_id,
                status=status,
                attempt=job.attempts,
                reason_code=reason,
                details=job.result,
            )
        )
    emit(
        "stage_transition",
        run_id=job.run_id,
        job_id=job.id,
        company_id=job.company_id,
        stage=job.stage,
        metric=job.metric_code,
        status=status,
        attempt=job.attempts,
        reason_code=reason,
        retryable=retryable,
    )
    return job


def recover(engine: Engine, run_id: UUID) -> None:
    # Caller owns the database-wide batch lock; no live batch worker can own these.
    with Session(engine) as session:
        ids = list(
            session.scalars(
                select(PipelineJob.id).where(
                    PipelineJob.run_id == run_id, PipelineJob.status == "running"
                )
            )
        )
    for identifier in ids:
        transition(engine, identifier, "failed", reason="interrupted", retryable=True)
