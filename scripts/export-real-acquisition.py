"""Read-only audit of the REAL collected library; never seeds data or calls AI.

Run with backend/.venv/bin/python scripts/export-real-acquisition.py OUTPUT.json.
The output path must be new. Includes actual API checks and local PDF checksums.
"""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    Company,
    KnowledgeIndex,
    KnowledgeJob,
    Report,
    ReportDiscoveryRun,
)
from app.db.session import create_database_engine
from app.discovery.crawler import SUPPLEMENT
from app.knowledge.contracts import Scope
from app.knowledge.search import indexed_sources
from app.main import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite an existing audit")
    settings = Settings()
    engine = create_database_engine(settings)
    documents, jobs = [], []
    with Session(engine) as session:
        rows = session.execute(
            select(Report, Company, KnowledgeIndex)
            .join(Company, Company.id == Report.company_id)
            .join(KnowledgeIndex, KnowledgeIndex.report_id == Report.id)
            .where(Report.id.in_(indexed_sources(Scope()).with_only_columns(Report.id)))
            .order_by(Company.company_name, Report.created_at)
        )
        for report, company, index in rows:
            root = settings.reports_root.resolve()
            path = (root / report.storage_key).resolve()
            assert path.is_relative_to(root)
            with path.open("rb") as stream:
                verified = (
                    hashlib.file_digest(stream, "sha256").hexdigest()
                    == report.content_sha256
                )
            assert verified, f"PDF hash mismatch: {report.id}"
            supporting = bool(SUPPLEMENT.search(report.title + " " + report.source_url))
            documents.append(
                {
                    "company": company.company_name,
                    "company_id": str(company.id),
                    "country": company.country,
                    "sector": company.sector,
                    "report_id": str(report.id),
                    "title": report.title,
                    "document_role": "supporting_document"
                    if supporting
                    else "primary_report_candidate",
                    "source_url": report.source_url,
                    "discovered_from": report.discovered_from_url,
                    "retrieved_at": report.retrieved_at.isoformat(),
                    "requested_year": report.requested_year,
                    "detected_year": report.detected_year,
                    "reporting_year": report.reporting_year,
                    "local_pdf": str(path),
                    "sha256": report.content_sha256,
                    "file_size_bytes": report.file_size_bytes,
                    "local_hash_verified": verified,
                    "pages": index.quality["pages_total"],
                    "text_pages": index.quality["pages_with_text"],
                    "text_characters": index.quality["text_characters"],
                    "tables": index.quality["tables"],
                    "passages": index.quality["passages"],
                    "pages_needing_ocr": index.quality["pages_needing_ocr"],
                    "parse_status": report.parse_status,
                    "metric_validation": False,
                }
            )
        for job, company in session.execute(
            select(KnowledgeJob, Company).join(Company).order_by(Company.company_name)
        ):
            runs = session.scalars(
                select(ReportDiscoveryRun)
                .where(
                    ReportDiscoveryRun.company_id == company.id,
                    ReportDiscoveryRun.created_at >= job.created_at,
                )
                .order_by(ReportDiscoveryRun.created_at)
            )
            jobs.append(
                {
                    "company": company.company_name,
                    "job_id": str(job.id),
                    "status": job.status,
                    "attempts": job.attempts,
                    "outcome": job.outcome,
                    "discovery_attempts": [
                        {
                            "run_id": str(r.id),
                            "status": r.status,
                            "reason": r.selection_reason,
                            "diagnostics": r.diagnostics,
                        }
                        for r in runs
                    ],
                }
            )
    checks, examples = [], []
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/knowledge/status")
        assert response.status_code == 200
        status = response.json()
        # The production library is paginated and may also include PDFs still
        # awaiting indexing. Read every page, not only the first 100 records.
        api_report_ids = set()
        for offset in range(0, 10_000, 100):
            response = client.get(f"/api/knowledge/reports?limit=100&offset={offset}")
            assert response.status_code == 200
            items = response.json()["items"]
            api_report_ids.update(item["id"] for item in items)
            if len(items) < 100:
                break
        else:
            raise AssertionError("Report library exceeded the audit's pagination bound")
        assert {d["report_id"] for d in documents} <= api_report_ids
        checks.extend(
            ["GET /api/knowledge/status: 200", "GET /api/knowledge/reports: 200"]
        )
        for query in (
            "supplier water scarcity",
            "biodiversity",
            "climate transition",
            "executive remuneration",
        ):
            response = client.post(
                "/api/knowledge/search", json={"query": query, "limit": 3}
            )
            assert response.status_code == 200
            body = response.json()
            assert body["items"], f"No actual source evidence for {query}"
            example = body["items"][0]
            evidence = client.get("/api/knowledge/evidence/" + example["evidence_id"])
            assert evidence.status_code == 200
            examples.append(
                {
                    "query": query,
                    "matching_passages": body["total"],
                    "company": example["company"],
                    "report_id": example["report_id"],
                    "page": example["page"],
                    "source_url": example["source_url"],
                    "excerpt": example["text"][:240],
                    "evidence_id": example["evidence_id"],
                }
            )
        checks.append("Four real topic searches and their evidence-page endpoints: 200")
        for document in documents:
            response = client.get(f"/api/reports/{document['report_id']}/file")
            assert response.status_code == 200 and response.content.startswith(b"%PDF-")
            assert hashlib.sha256(response.content).hexdigest() == document["sha256"]
        checks.append(
            f"{len(documents)} real PDF source endpoints: 200 and matching SHA-256"
        )
    primary = [r for r in documents if r["document_role"] == "primary_report_candidate"]
    summary = {
        "companies_attempted": len(jobs),
        "companies_with_primary_report": len({r["company_id"] for r in primary}),
        "primary_reports": len(primary),
        "primary_report_pages": sum(r["pages"] for r in primary),
        "supporting_documents": len(documents) - len(primary),
        "documents_total": len(documents),
        "pdf_hashes_verified": len(documents),
        "ai_calls": 0,
        "synthetic_records_added": 0,
    }
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "caveat": "Live read-only inventory of current indexes; acquisition may continue during checks. Real source acquisition and text indexing, not validated metrics or comparable benchmark coverage. Report label year is not automatically the observation year.",
        "api_status": status,
        "api_checks": checks,
        "source_examples": examples,
        "documents": documents,
        "jobs": jobs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
    engine.dispose()
    print(
        json.dumps(
            {"audit_file": str(args.output.resolve()), **summary, "api_checks": checks},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
