# ruff: noqa: F811 -- pytest imports this shared fixture by name
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KnowledgeJob, Report, ReportCollection
from app.knowledge.collection import (
    create_collection,
    export_snapshot,
    run_collection,
    snapshot,
)
from app.knowledge.ingestion import queue
from test_knowledge import corpus  # noqa: F401 -- shared page-aware PostgreSQL fixture


def test_collection_continues_after_failure_and_resumes_same_cohort(
    db_engine, corpus, tmp_path, monkeypatch
):
    settings, ids = corpus
    settings = settings.model_copy(update={"pipeline_root": tmp_path / "pipeline"})
    company_ids = [i[0] for i in ids]
    jobs = queue(db_engine, company_ids, 2025)
    with Session(db_engine) as session, session.begin():
        first = session.scalar(
            select(KnowledgeJob).where(KnowledgeJob.company_id == ids[0][0])
        )
        first.status = "succeeded"
        first.outcome = {
            "stage": "finished",
            "reports": [{"report_id": str(ids[0][1]), "status": "indexed"}],
        }
    worker = Mock(side_effect=RuntimeError("fixture worker failure"))
    monkeypatch.setattr("app.knowledge.collection.execute_job", worker)
    run_id = create_collection(db_engine, company_ids, 2025, {"workers": 2})
    result = run_collection(db_engine, run_id, settings)
    assert result["status"] == "completed_with_gaps"
    assert result["summary"]["processed"] == 2
    assert result["summary"]["outcomes"] == {"succeeded": 1, "failed": 1}
    assert result["summary"]["ai_calls"] == result["summary"]["metrics_extracted"] == 0
    assert (
        worker.call_count == 1
    )  # Existing primary source was checksum-verified, not downloaded again.
    stored = json.loads(
        (tmp_path / "collections" / str(run_id) / "manifest.json").read_text()
    )
    assert stored["companies"][0]["reports"][0]["sha256"]
    again = run_collection(db_engine, run_id, settings)
    assert again["summary"]["companies"] == 2
    assert (
        worker.call_count == 2
    )  # Retry the failed company, preserve the successful one.
    with Session(db_engine) as session:
        assert session.get(ReportCollection, run_id).company_ids == [
            str(i) for i in company_ids
        ]
        assert len(list(session.scalars(select(KnowledgeJob.id)))) == len(jobs)


def test_collection_rejects_duplicate_and_unknown_companies(db_engine, corpus):
    _, ids = corpus
    with pytest.raises(ValueError, match="distinct"):
        create_collection(db_engine, [ids[0][0], ids[0][0]], 2025, {})
    with pytest.raises(ValueError, match="unknown"):
        create_collection(db_engine, [uuid4()], 2025, {})
    with pytest.raises(ValueError, match="unknown_collection"):
        snapshot(db_engine, uuid4())


def test_missing_source_file_is_not_a_successful_resume(
    db_engine, corpus, tmp_path, monkeypatch
):
    settings, ids = corpus
    settings = settings.model_copy(update={"pipeline_root": tmp_path / "pipeline"})
    queue(db_engine, [ids[0][0]], 2025)
    with Session(db_engine) as session, session.begin():
        job = session.scalar(
            select(KnowledgeJob).where(KnowledgeJob.company_id == ids[0][0])
        )
        job.status = "succeeded"
        job.outcome = {"reports": [{"report_id": str(ids[0][1]), "status": "indexed"}]}
        job_id = job.id
    (settings.reports_root / "0.pdf").unlink()
    worker = Mock(
        return_value={
            "job_id": str(job_id),
            "status": "failed",
            "outcome": {"reason": "source_missing"},
        }
    )
    monkeypatch.setattr("app.knowledge.collection.execute_job", worker)
    run_id = create_collection(db_engine, [ids[0][0]], 2025, {"workers": 1})
    result = run_collection(db_engine, run_id, settings)
    assert result["status"] == "completed_with_gaps"
    assert worker.call_args.kwargs["refresh"] is True


def test_unknown_year_reuse_remains_partial_not_requested_year_success(
    db_engine, corpus, tmp_path
):
    settings, ids = corpus
    settings = settings.model_copy(update={"pipeline_root": tmp_path / "pipeline"})
    queue(db_engine, [ids[0][0]], 2025)
    with Session(db_engine) as session, session.begin():
        session.get(Report, ids[0][1]).detected_year = None
        job = session.scalar(
            select(KnowledgeJob).where(KnowledgeJob.company_id == ids[0][0])
        )
        job.status = "succeeded"
        job.outcome = {"reports": [{"report_id": str(ids[0][1]), "status": "indexed"}]}
    run_id = create_collection(db_engine, [ids[0][0]], 2025, {"workers": 1})
    result = run_collection(db_engine, run_id, settings)
    assert result["summary"]["outcomes"] == {"partial": 1}
    assert result["summary"]["unknown_year_reports"] == 1
    assert result["summary"]["requested_year_reports"] == 0


def test_collection_lock_prevents_concurrent_same_run(db_engine, corpus, tmp_path):
    from sqlalchemy import text

    settings, ids = corpus
    settings = settings.model_copy(update={"pipeline_root": tmp_path / "pipeline"})
    run_id = create_collection(db_engine, [ids[0][0]], 2025, {})
    with db_engine.connect() as connection:
        params = {"key": f"report-collection:{run_id}"}
        connection.execute(
            text("SELECT pg_advisory_lock(hashtextextended(:key, 0))"), params
        )
        connection.commit()
        try:
            with pytest.raises(ValueError, match="already_running"):
                run_collection(db_engine, run_id, settings)
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"), params
            )
            connection.commit()


def test_read_only_collection_api(db_engine, corpus, api_client):
    _, ids = corpus
    run_id = create_collection(db_engine, [ids[0][0]], 2025, {"workers": 2})
    response = api_client.get("/api/knowledge/collections")
    assert response.status_code == 200
    assert response.json()["items"][0]["run_id"] == str(run_id)
    details = api_client.get(f"/api/knowledge/collections/{run_id}")
    assert details.status_code == 200
    assert details.json()["summary"]["processed"] == 0
    assert details.json()["summary"]["companies"] == 1
    assert api_client.get(f"/api/knowledge/collections/{uuid4()}").status_code == 404


def test_concurrent_checkpoint_and_status_export_are_atomic(tmp_path, monkeypatch):
    barrier = Barrier(2)
    original = Path.write_text

    def write_then_wait(path, value, *args, **kwargs):
        result = original(path, value, *args, **kwargs)
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(Path, "write_text", write_then_wait)
    monkeypatch.setattr(
        "app.knowledge.collection.snapshot", lambda *_: {"complete": True}
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(export_snapshot, None, uuid4(), tmp_path) for _ in range(2)
        ]
        assert all(f.result() == {"complete": True} for f in futures)
    assert json.loads((tmp_path / "manifest.json").read_text()) == {"complete": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_partial_supporting_document_retries_primary_discovery(
    db_engine, corpus, tmp_path, monkeypatch
):
    settings, ids = corpus
    settings = settings.model_copy(update={"pipeline_root": tmp_path / "pipeline"})
    queue(db_engine, [ids[0][0]], 2025)
    with Session(db_engine) as session, session.begin():
        session.get(Report, ids[0][1]).title = "2025 CEO message"
        job = session.scalar(
            select(KnowledgeJob).where(KnowledgeJob.company_id == ids[0][0])
        )
        job.status = "partial"
        job.outcome = {"reports": [{"report_id": str(ids[0][1]), "status": "indexed"}]}
        job_id = job.id
    worker = Mock(
        return_value={"job_id": str(job_id), "status": "needs_review", "outcome": {}}
    )
    monkeypatch.setattr("app.knowledge.collection.execute_job", worker)
    run_id = create_collection(db_engine, [ids[0][0]], 2025, {"workers": 1})
    run_collection(db_engine, run_id, settings)
    assert worker.call_args.kwargs["refresh"] is True
