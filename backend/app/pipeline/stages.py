"""Reuse existing acquisition/parser/extractor contracts, not parallel implementations."""

import asyncio
from urllib.parse import unquote
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    Company,
    DocumentPage,
    ExtractionRun,
    Report,
    ReportDiscoveryRun,
)
from app.discovery.http import SafeHTTP
from app.discovery.crawler import SPECIALISED_FINANCING
from app.discovery.service import (
    discover_company,
    download_report,
    policy_for,
    report_dict,
)
from app.extraction.retrieval import retrieve
from app.extraction.service import extract_metric, inputs
from app.llm.contracts import ModelIdentity, StructuredExtractor
from app.parsing.service import parse_report
from app.parsing.review import reviewed_decorative_pages
from app.pipeline.ledger import RETRYABLE
from app.pipeline.throttle import DomainPacer


class StageFailure(Exception):
    def __init__(
        self,
        code: str,
        *,
        retryable: bool = False,
        status: str = "failed",
        details: dict[str, Any] | None = None,
    ):
        self.code, self.retryable, self.status, self.details = (
            code,
            retryable,
            status,
            details or {},
        )
        super().__init__(code)


class Services:
    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        extractor: StructuredExtractor,
        identity: ModelIdentity,
    ):
        self.engine, self.settings, self.extractor, self.identity = (
            engine,
            settings,
            extractor,
            identity,
        )
        self.parsing = asyncio.Semaphore(settings.pipeline_parse_workers)
        self.inference = asyncio.Semaphore(settings.pipeline_model_workers)

    def discover(self, company_id: UUID, year: int) -> dict[str, Any]:
        with Session(self.engine, expire_on_commit=False) as session:
            company = session.get(Company, company_id)
            assert company is not None
            # Reuse successful prior official acquisition, not failed historical searches.
            prior_reports = session.scalars(
                select(Report)
                .where(
                    Report.company_id == company_id,
                    Report.requested_year == year,
                    Report.is_selected.is_(True),
                    Report.source_policy == "official",
                    Report.status.in_(["downloaded", "discovered"]),
                )
                .order_by(Report.created_at.desc())
            )
            report = next(
                (
                    r
                    for r in prior_reports
                    if not SPECIALISED_FINANCING.search(
                        unquote(f"{r.title or ''} {r.source_url}")
                    )
                ),
                None,
            )
            if report is not None:
                return {
                    "report_id": str(report.id),
                    "discovery_run_id": str(report.discovery_run_id),
                    "reused": True,
                    "report": report_dict(report),
                }
            policy = policy_for(company, self.settings)
            client = SafeHTTP(
                self.settings, policy, pacer=DomainPacer(self.engine, policy.domains)
            )
            try:
                run = discover_company(
                    session, company, year, self.settings, http=client
                )
            finally:
                client.close()
            report = session.scalar(
                select(Report).where(
                    Report.discovery_run_id == run.id, Report.is_selected.is_(True)
                )
            )
            if report is None or report.status != "discovered":
                codes = [str(d.get("code")) for d in run.diagnostics if d.get("code")]
                raise StageFailure(
                    codes[-1] if codes else "report_unavailable",
                    status=(
                        run.status
                        if run.status in {"failed", "needs_review", "unavailable"}
                        else "needs_review"
                    ),
                    retryable=bool(codes) and all(c in RETRYABLE for c in codes),
                    details={
                        "discovery_run_id": str(run.id),
                        "reason": run.selection_reason,
                        "diagnostics": run.diagnostics,
                    },
                )
            require_primary_report(report)
            return {
                "report_id": str(report.id),
                "discovery_run_id": str(run.id),
                "report": report_dict(report),
            }

    def download(self, report_id: UUID) -> dict[str, Any]:
        with Session(self.engine, expire_on_commit=False) as session:
            report = session.get(Report, report_id)
            assert report is not None
            require_primary_report(report)
            company = session.get(Company, report.company_id)
            assert company is not None
            policy = policy_for(company, self.settings)
            client = SafeHTTP(
                self.settings, policy, pacer=DomainPacer(self.engine, policy.domains)
            )
            try:
                download_report(session, report, company, self.settings, http=client)
            finally:
                client.close()
            if report.status != "downloaded":
                run = session.get(ReportDiscoveryRun, report.discovery_run_id)
                diagnostics = run.diagnostics if run else []
                code = (
                    str(diagnostics[-1].get("code", "download_failed"))
                    if diagnostics
                    else "download_failed"
                )
                raise StageFailure(
                    code,
                    status=report.status,
                    retryable=code in RETRYABLE,
                    details={"report": report_dict(report), "diagnostics": diagnostics},
                )
            return {"report_id": str(report.id), "report": report_dict(report)}

    async def parse(self, report_id: UUID) -> dict[str, Any]:
        async with self.parsing:
            result = await asyncio.to_thread(
                parse_report, self.engine, report_id, self.settings
            )
        parse_state = (result.get("quality") or {}).get(
            "parse_status", result["status"]
        )
        if parse_state == "needs_ocr" and not (result.get("quality") or {}).get(
            "pages_failed", 0
        ):
            with Session(self.engine) as session:
                report = session.get(Report, report_id)
                assert report is not None
                parse_id = UUID(result["run_id"])
                flagged = set(
                    session.scalars(
                        select(DocumentPage.page_number).where(
                            DocumentPage.parse_run_id == parse_id,
                            DocumentPage.status == "needs_ocr",
                        )
                    )
                )
                reviewed = reviewed_decorative_pages(
                    session, report_id, parse_id, report.content_sha256 or ""
                )
            if flagged and flagged.issubset(reviewed):
                result = {
                    **result,
                    "visual_page_reviews": {
                        str(p): reviewed[p] for p in sorted(flagged)
                    },
                    "parse_gate": "text_extracted_with_reviewed_decorative_pages",
                }
                parse_state = "needs_review"
        if parse_state not in {"parsed", "unchanged", "needs_review"} or not (
            result.get("quality") or {}
        ).get("pages_with_text", 0):
            code = result.get("error_code") or parse_state
            raise StageFailure(
                code,
                status="needs_review" if parse_state == "needs_ocr" else "failed",
                retryable=code in {"busy", "timeout"},
                details=result,
            )
        return result

    def retrieval(
        self, report_id: UUID, metric: str, year: int, top_k: int
    ) -> dict[str, Any]:
        with Session(self.engine) as session:
            _, parsed, _, definition, passages = inputs(session, report_id, metric)
            candidates = retrieve(passages, definition, year, top_k=top_k)
        return {
            "report_id": str(report_id),
            "parse_run_id": str(parsed.id),
            "candidates": [
                {
                    "chunk_id": str(c.passage.chunk_id),
                    "page": c.passage.page,
                    "sha256": c.passage.sha256,
                    "score": c.score,
                }
                for c in candidates
            ],
            "report_absence_established": False,
        }

    async def extract(
        self, report_id: UUID, metric: str, year: int, top_k: int
    ) -> dict[str, Any]:
        async with self.inference:
            result = await extract_metric(
                self.engine,
                report_id,
                metric,
                year,
                self.settings,
                self.extractor,
                identity=self.identity,
                top_k=top_k,
                resume_calls=True,
            )
        if result["status"] not in {"succeeded", "unchanged"}:
            codes = [
                c["error_code"]
                for c in result.get("summary", {}).get("calls", [])
                if c.get("error_code")
            ]
            code = codes[-1] if codes else result["status"]
            raise StageFailure(
                code,
                retryable=code in RETRYABLE,
                details={
                    "extraction_run_id": result.get("run_id"),
                    "error_codes": codes,
                },
            )
        return {
            "extraction_run_id": result["run_id"],
            "observation_count": result.get("summary", {}).get("observation_count", 0),
            "reused": result["status"] == "unchanged",
        }

    def receipt(self, extraction_id: UUID, stage: str) -> dict[str, Any]:
        with Session(self.engine) as session:
            run = session.get(ExtractionRun, extraction_id)
            if run is None or run.status != "succeeded":
                raise StageFailure("extraction_receipt_missing")
            summary = run.output_summary or {}
            # These operations are already atomic inside extract_metric. Persist
            # explicit receipts, never falsely claim independent human validation.
            return {
                "extraction_run_id": str(run.id),
                "atomic_group": "extract_validate_normalise_store",
                "operation": stage,
                "assessment_count": summary.get("assessment_count", 0),
                "observation_count": summary.get("observation_count", 0),
                "observation_ids": summary.get("observation_ids", []),
                "states": summary.get("persisted_states", {}),
                "automatically_validated": 0,
            }


def require_primary_report(report: Report) -> None:
    # A corporate sustainability-looking link may actually concern a ring-fenced
    # bond portfolio. Never silently treat financed-project impact as company data.
    label = unquote(f"{report.title or ''} {report.source_url}").lower()
    if SPECIALISED_FINANCING.search(label):
        raise StageFailure(
            "specialised_financing_disclosure",
            status="needs_review",
            details={
                "report_id": str(report.id),
                "report": report_dict(report),
                "reason": "Bond allocation/impact disclosure is not approved as a company-wide sustainability report; source review required",
            },
        )
