"""Export source inventory with independently rechecked PDF bytes and page counts."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import DocumentPage, KnowledgeIndex, KnowledgePassage, Report
from app.db.session import create_database_engine
from app.knowledge.collection import snapshot
from app.knowledge.contracts import SearchRequest
from app.knowledge.search import search


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", type=UUID)
    parser.add_argument("--include-run", type=UUID, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output path; audit snapshots are immutable")
    settings = get_settings()
    engine = create_database_engine(settings)
    manifest = snapshot(engine, args.run_id)
    additional = [snapshot(engine, identifier) for identifier in args.include_run]
    if any(m["status"] == "running" for m in [manifest, *additional]):
        parser.error(
            "Audit a completed/interrupted run; live progress uses collection-status"
        )
    root = settings.reports_root.resolve()
    checks = []
    checked_ids = set()
    companies = [c for m in [manifest, *additional] for c in m["companies"]]
    with Session(engine) as session:
        for company in companies:
            for item in company["reports"]:
                if item["status"] != "downloaded" or item["id"] in checked_ids:
                    continue
                checked_ids.add(item["id"])
                report = session.get(Report, UUID(item["id"]))
                path = (root / (report.storage_key or "")).resolve()
                verified = path.is_relative_to(root) and path.is_file()
                if verified:
                    with path.open("rb") as stream:
                        verified = (
                            hashlib.file_digest(stream, "sha256").hexdigest()
                            == report.content_sha256
                        )
                index = session.scalar(
                    select(KnowledgeIndex).where(KnowledgeIndex.report_id == report.id)
                )
                checks.append(
                    {
                        "company": company["company"],
                        **item,
                        "pdf_hash_verified": verified,
                        "indexed": index is not None,
                        "indexed_page_count": session.scalar(
                            select(func.count())
                            .select_from(DocumentPage)
                            .where(DocumentPage.parse_run_id == index.parse_run_id)
                        )
                        if index
                        else 0,
                        "passages": session.scalar(
                            select(func.count())
                            .select_from(KnowledgePassage)
                            .where(KnowledgePassage.index_id == index.id)
                        )
                        if index
                        else 0,
                        "pages_needing_ocr": index.quality.get("pages_needing_ocr", [])
                        if index
                        else [],
                        "text_characters": index.quality.get("text_characters", 0)
                        if index
                        else 0,
                    }
                )
        company_ids = sorted({UUID(c["company_id"]) for c in companies})
        examples = {
            query: search(
                session, SearchRequest(query=query, company_ids=company_ids, limit=3)
            )
            for query in [
                "supplier water scarcity",
                "biodiversity habitats",
                "climate transition risks",
            ]
        }
    payload = {
        "audited_at": datetime.now(UTC).isoformat(),
        "run": manifest,
        "additional_runs": additional,
        "file_checks": checks,
        "search_examples": examples,
        "verification": {
            "downloaded_report_records": len(checks),
            "companies_with_downloads": len({r["company_id"] for r in checks}),
            "unique_pdf_hashes": len({r["sha256"] for r in checks}),
            "all_downloaded_files_match_hashes": all(
                r["pdf_hash_verified"] for r in checks
            ),
            "indexed_reports": sum(r["indexed"] for r in checks),
            "searchable_reports": sum(r["passages"] > 0 for r in checks),
            "companies_with_searchable_reports": len(
                {r["company_id"] for r in checks if r["passages"] > 0}
            ),
            "companies_with_searchable_primary_candidates": len(
                {
                    r["company_id"]
                    for r in checks
                    if r["passages"] > 0
                    and r["document_role"] == "primary_report_candidate"
                }
            ),
            "searchable_primary_candidates": sum(
                r["passages"] > 0 and r["document_role"] == "primary_report_candidate"
                for r in checks
            ),
            "searchable_supporting_documents": sum(
                r["passages"] > 0 and r["document_role"] == "supporting_document"
                for r in checks
            ),
            "indexed_pages": sum(r["indexed_page_count"] for r in checks),
            "passages": sum(r["passages"] for r in checks),
            "text_characters": sum(r["text_characters"] for r in checks),
        },
        "metrics_written_by_collection": 0,
        "ai_calls_by_collection": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "summary": manifest["summary"],
                "verification": payload["verification"],
            },
            indent=2,
        )
    )
    engine.dispose()
    if not payload["verification"]["all_downloaded_files_match_hashes"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
