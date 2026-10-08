"""Persist discovery evidence and content-addressed downloads. No metric ingestion."""

import hashlib
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import Settings
from app.db.models import Company, Report, ReportArtifact, ReportDiscoveryRun
from app.discovery.browser import render_page
from app.discovery.crawler import POLICY_VERSION, Discovery, discover, make_candidate
from app.discovery.http import AcquisitionError, SafeHTTP, SourcePolicy, require_success

STATES = ("discovered", "downloaded", "needs_review", "unavailable", "failed")


def policy_for(company: Company, settings: Settings) -> SourcePolicy:
    return SourcePolicy(
        tuple(
            dict.fromkeys(
                [
                    company.official_domain.lower().removeprefix("www."),
                    *settings.discovery_official_domains.get(str(company.id), []),
                ]
            )
        )
    )


def persist_discovery(
    session: Session, run: ReportDiscoveryRun, result: Discovery
) -> None:
    run.status, run.selection_reason = result.status, result.reason
    run.diagnostics = result.diagnostics
    run.pages_visited, run.http_requests = result.pages_visited, result.http_requests
    run.finished_at = datetime.now(UTC)
    for candidate in result.candidates:
        session.add(
            Report(
                company_id=run.company_id,
                discovery_run_id=run.id,
                requested_year=run.requested_year,
                detected_year=candidate.detected_year,
                # A filename year is not an established reporting period.
                reporting_year=None,
                title=candidate.title,
                report_type=candidate.report_type,
                source_url=candidate.url,
                discovered_from_url=candidate.discovered_from,
                url_sha256=hashlib.sha256(candidate.url.encode()).hexdigest(),
                mime_type=candidate.mime_type,
                file_size_bytes=candidate.file_size,
                confidence=Decimal(str(candidate.confidence)),
                selection_reason=candidate.reason,
                status=candidate.status,
                is_selected=candidate.selected,
                source_policy=(
                    "official" if candidate.official else "unverified_external"
                ),
                notes="Discovery labels only. Content, reporting boundary and achieved performance have not been validated.",
            )
        )
    session.commit()


def discover_company(
    session: Session,
    company: Company,
    year: int,
    settings: Settings,
    http: SafeHTTP | None = None,
) -> ReportDiscoveryRun:
    # Revisit a small number of actual company pages that previously linked a
    # current-year CDN candidate. This is a discovery hint, not source approval:
    # the page and anchor must be fetched and observed again under current policy.
    policy = policy_for(company, settings)
    prior_pages: list[str] = []
    for prior_record in session.scalars(
        select(Report)
        .where(
            Report.company_id == company.id,
            Report.source_policy == "unverified_external",
            Report.detected_year.in_([year, year - 1]),
        )
        .order_by(Report.created_at.desc())
        .limit(100)
    ):
        if (
            prior_record.discovered_from_url
            and policy.endorse_document(
                prior_record.source_url, prior_record.discovered_from_url
            )
            != policy
        ):
            if prior_record.discovered_from_url not in prior_pages:
                prior_pages.append(prior_record.discovered_from_url)
        if len(prior_pages) == 3:
            break
    sources = list(
        dict.fromkeys(
            url
            for url in (
                company.sustainability_url,
                *prior_pages,
                company.investor_relations_url,
                f"https://{company.official_domain}/",
            )
            if url
        )
    )
    run = ReportDiscoveryRun(
        company_id=company.id,
        requested_year=year,
        status="failed",
        selection_reason="Discovery started but has not completed",
        policy_version=POLICY_VERSION,
        sources=sources,
        diagnostics=[],
    )
    session.add(run)
    session.commit()
    client = http or SafeHTTP(settings, policy)
    try:
        result = discover(
            client, sources, year, render_page if settings.discovery_allow_js else None
        )
        if result.status != "discovered" and settings.discovery_sitemap_fallback:
            from app.discovery.sitemaps import discover_sitemaps

            extra = discover_sitemaps(client, year)
            result.diagnostics.extend(extra.diagnostics)
            result.pages_visited += extra.pages_visited
            candidates = {c.url: c for c in result.candidates}
            for candidate in extra.candidates:
                if (
                    candidate.url not in candidates
                    or candidate.confidence > candidates[candidate.url].confidence
                ):
                    candidates[candidate.url] = candidate
            result.candidates = list(candidates.values())
            eligible = sorted(
                (c for c in result.candidates if c.status == "discovered"),
                key=lambda c: (-c.confidence, len(c.url), c.url),
            )
            if eligible:
                for candidate in result.candidates:
                    candidate.selected = candidate is eligible[0]
                result.status, result.reason = "discovered", eligible[0].reason
        if result.status != "discovered" and settings.discovery_search_fallback:
            from app.discovery.search_engine import official_search

            try:
                bind = session.get_bind()
                search_engine = bind if isinstance(bind, Engine) else bind.engine
                hits, search_url = official_search(
                    company.official_domain.removeprefix("www."),
                    year,
                    settings,
                    search_engine,
                )
                result.diagnostics.append(
                    {
                        "code": "official_search",
                        "url": search_url,
                        "hits": len(hits),
                        "status": "discovered",
                        "message": "Search URLs only; snippets are not report evidence",
                    }
                )
                existing = {c.url for c in result.candidates}
                for hit in hits:
                    candidate = make_candidate(
                        hit["url"],
                        hit["title"],
                        hit["snippet"],
                        search_url,
                        year,
                        client,
                    )
                    if candidate.url not in existing:
                        result.candidates.append(candidate)
                        existing.add(candidate.url)
                eligible = sorted(
                    (c for c in result.candidates if c.status == "discovered"),
                    key=lambda c: (-c.confidence, len(c.url), c.url),
                )
                if eligible:
                    for candidate in result.candidates:
                        candidate.selected = candidate is eligible[0]
                    result.status, result.reason = "discovered", eligible[0].reason
            except AcquisitionError as exc:
                result.diagnostics.append(
                    {"code": exc.code, "status": exc.status, "message": str(exc)}
                )
        if result.status != "discovered" and settings.discovery_allow_prior_year:
            # Reassess actual discovered links, never synthesize a prior-year URL.
            prior = []
            for item in result.candidates:
                if item.detected_year == year - 1:
                    candidate = make_candidate(
                        item.url,
                        item.title,
                        "",
                        item.discovered_from,
                        year - 1,
                        client,
                        direct_pdf=item.pdf,
                    )
                    if candidate.status == "discovered":
                        prior.append(candidate)
            if prior:
                selected = sorted(
                    prior, key=lambda c: (-c.confidence, len(c.url), c.url)
                )[0]
                selected.selected = True
                selected.reason = (
                    f"Requested {year} report not located in bounded search; PRIOR-YEAR SOURCE {year - 1}, not {year} coverage. "
                    + selected.reason
                )
                result.candidates = [
                    c for c in result.candidates if c.url != selected.url
                ] + [selected]
                result.status, result.reason = "discovered", selected.reason
                result.diagnostics.append(
                    {
                        "code": "prior_year_source",
                        "status": "needs_review",
                        "message": selected.reason,
                    }
                )
        if result.status != "discovered" and settings.discovery_allow_unlabelled_year:
            # Missing filename metadata must not exclude an otherwise eligible
            # official source from the knowledge library. Never infer its year.
            unlabelled = []
            for item in result.candidates:
                if item.detected_year is None:
                    candidate = make_candidate(
                        item.url,
                        item.title,
                        "",
                        item.discovered_from,
                        year,
                        client,
                        direct_pdf=item.pdf,
                        allow_unlabelled_year=True,
                    )
                    if candidate.status == "discovered":
                        unlabelled.append(candidate)
            if unlabelled:
                selected = sorted(
                    unlabelled, key=lambda c: (-c.confidence, len(c.url), c.url)
                )[0]
                selected.selected = True
                result.candidates = [
                    c for c in result.candidates if c.url != selected.url
                ] + [selected]
                result.status, result.reason = "discovered", selected.reason
                result.diagnostics.append(
                    {
                        "code": "unlabelled_year_source",
                        "status": "needs_review",
                        "message": selected.reason,
                    }
                )
        result.http_requests = client.requests
        persist_discovery(session, run, result)
    finally:
        if http is None:
            client.close()
    return run


def latest_runs(
    session: Session, year: int | None = None, company_ids: list[UUID] | None = None
) -> list[ReportDiscoveryRun]:
    conditions: list[ColumnElement[bool]] = [
        ReportDiscoveryRun.finished_at.is_not(None)
    ]
    if year is not None:
        conditions.append(ReportDiscoveryRun.requested_year == year)
    if company_ids:
        conditions.append(ReportDiscoveryRun.company_id.in_(company_ids))
    ranked = (
        select(
            ReportDiscoveryRun.id,
            func.row_number()
            .over(
                partition_by=(
                    ReportDiscoveryRun.company_id,
                    ReportDiscoveryRun.requested_year,
                ),
                order_by=(
                    ReportDiscoveryRun.created_at.desc(),
                    ReportDiscoveryRun.id.desc(),
                ),
            )
            .label("position"),
        )
        .where(*conditions)
        .subquery()
    )
    return list(
        session.scalars(
            select(ReportDiscoveryRun)
            .join(ranked, ranked.c.id == ReportDiscoveryRun.id)
            .where(ranked.c.position == 1)
            .order_by(ReportDiscoveryRun.company_id, ReportDiscoveryRun.requested_year)
        )
    )


def download_report(
    session: Session,
    report: Report,
    company: Company,
    settings: Settings,
    http: SafeHTTP | None = None,
) -> str:
    if (
        report.requested_year is None
        or report.discovery_run_id is None
        or not report.is_selected
    ):
        raise ValueError(
            "Only selected discovery reports can be downloaded automatically"
        )
    if report.status == "downloaded":
        return (
            "Already downloaded; run discovery again to acquire a new document version"
        )
    client = http or SafeHTTP(settings, policy_for(company, settings))
    response = None
    partial: Path | None = None
    run = session.get(ReportDiscoveryRun, report.discovery_run_id)
    assert run is not None
    # A resumed download must restore only the exact asset grant documented by
    # this company's discovery run. The shared CDN domain is never allowlisted.
    if (
        run.company_id == company.id
        and report.company_id == company.id
        and report.discovered_from_url
    ):
        # Earlier owned-domain discoveries predate explicit publisher-link audit
        # entries. Their exact URL + owned source page are already retained. Do
        # not extend this compatibility path to external hosts or unknown sources.
        if report.source_policy == "official" and client.policy.owns(report.source_url):
            client.policy = client.policy.endorse_document(
                report.source_url, report.discovered_from_url
            )
        for diagnostic in run.diagnostics:
            if (
                diagnostic.get("code") == "official_document_link"
                and diagnostic.get("policy") == "exact-publisher-pdf-v1"
                and diagnostic.get("url") == report.source_url
                and diagnostic.get("source_page") == report.discovered_from_url
            ):
                client.policy = client.policy.endorse_document(
                    report.source_url, report.discovered_from_url
                )
    try:
        response = client.get(report.source_url)
        run.diagnostics = [
            *run.diagnostics,
            *[entry for entry in client.audit if entry not in run.diagnostics],
        ]
        require_success(response)
        mime = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        report.final_url = response.url
        report.mime_type = mime or None
        report.retrieved_at = datetime.now(UTC)
        if mime not in {
            "application/pdf",
            "application/x-pdf",
            "application/octet-stream",
            "binary/octet-stream",
        }:
            raise AcquisitionError(
                "wrong_mime",
                f"Download refused: expected PDF MIME, received {mime or 'missing'}",
            )
        limit = settings.discovery_max_download_mb * 1024 * 1024
        declared = response.headers.get("Content-Length", "")
        if declared.isdigit() and int(declared) > limit:
            raise AcquisitionError(
                "size_limit", "Declared file size exceeds download limit"
            )
        root = settings.reports_root.resolve()
        directory = root / str(company.id) / str(report.requested_year)
        directory.mkdir(parents=True, exist_ok=True)
        sha = hashlib.sha256()
        size = 0
        prefix = b""
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=".download-", suffix=".part", delete=False
        ) as file:
            partial = Path(file.name)
            for chunk in client.chunks(response, limit):
                prefix = (prefix + chunk)[:1024]
                sha.update(chunk)
                size += len(chunk)
                file.write(chunk)
        if not prefix.lstrip().startswith(b"%PDF-"):
            raise AcquisitionError(
                "wrong_signature",
                "PDF signature missing; HTML challenges and non-PDF content are not saved",
            )
        digest = sha.hexdigest()
        # Serialize only identical blobs, including concurrent CLI processes.
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:digest, 0))"),
            {"digest": digest},
        )
        artifact = session.scalar(
            select(ReportArtifact).where(ReportArtifact.content_sha256 == digest)
        )
        duplicate = artifact is not None
        target = (
            root / artifact.storage_key if artifact else directory / f"{digest}.pdf"
        )
        target = target.resolve()
        if not target.is_relative_to(root):
            raise AcquisitionError(
                "unsafe_path",
                "Artifact path escapes configured report storage",
                "failed",
            )
        if target.exists():
            with target.open("rb") as existing:
                if hashlib.file_digest(existing, "sha256").hexdigest() != digest:
                    raise AcquisitionError(
                        "storage_integrity",
                        "Existing artifact failed checksum verification; not overwritten",
                        "failed",
                    )
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            partial.replace(target)
        if artifact is None:
            artifact = ReportArtifact(
                content_sha256=digest,
                storage_key=str(target.relative_to(root)),
                file_size_bytes=size,
                mime_type="application/pdf",
            )
            session.add(artifact)
            session.flush()
        report.artifact_id, report.content_sha256 = artifact.id, digest
        report.storage_key, report.file_size_bytes = artifact.storage_key, size
        report.status, report.download_status = "downloaded", "downloaded"
        run.status = "downloaded"
        note = (
            "SHA-256 duplicate; reused verified canonical file"
            if duplicate
            else "Downloaded and verified PDF MIME/signature; SHA-256 recorded"
        )
        run.selection_reason = f"{report.selection_reason}. {note}"
        session.commit()
        return note
    except (AcquisitionError, OSError) as exc:
        state = exc.status if isinstance(exc, AcquisitionError) else "failed"
        code = exc.code if isinstance(exc, AcquisitionError) else "filesystem"
        report.status, report.download_status = state, state
        run.status, run.selection_reason = state, str(exc)
        run.diagnostics = [
            *run.diagnostics,
            *[entry for entry in client.audit if entry not in run.diagnostics],
            {
                "url": report.source_url,
                "code": code,
                "status": state,
                "message": str(exc),
                "stage": "download",
            },
        ]
        session.commit()
        return str(exc)
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)
        if response is not None:
            response.close()
        if http is None:
            client.close()


def report_dict(report: Report) -> dict[str, Any]:
    return {
        "id": str(report.id),
        "company_id": str(report.company_id),
        "requested_year": report.requested_year,
        "url": report.source_url,
        "final_url": report.final_url,
        "title": report.title,
        "discovered_from": report.discovered_from_url,
        "detected_year": report.detected_year,
        "mime_type": report.mime_type,
        "file_size": report.file_size_bytes,
        "sha256": report.content_sha256,
        "confidence": (
            float(report.confidence) if report.confidence is not None else None
        ),
        "selection_reason": report.selection_reason,
        "retrieved_at": (
            report.retrieved_at.isoformat() if report.retrieved_at else None
        ),
        "discovered_at": report.created_at.isoformat(),
        "status": report.status,
        "is_selected": report.is_selected,
        "source_policy": report.source_policy,
        "storage_key": report.storage_key,
    }


def status_snapshot(
    session: Session,
    year: int | None = None,
    company_ids: list[UUID] | None = None,
    *,
    page: int | None = None,
    page_size: int = 20,
) -> dict[str, Any]:
    runs = latest_runs(session, year, company_ids)
    counts = {state: 0 for state in STATES}
    items: list[dict[str, Any]] = []
    company_map = {c.id: c for c in session.scalars(select(Company))}
    for run in runs:
        counts[run.status] += 1
    total = len(runs)
    companies_processed = len({run.company_id for run in runs})
    runs.sort(
        key=lambda run: (
            company_map[run.company_id].company_name.lower(),
            run.requested_year,
        )
    )
    if page is not None:
        runs = runs[(page - 1) * page_size : page * page_size]
    reports: dict[UUID, list[Report]] = {}
    if runs:
        for report in session.scalars(
            select(Report)
            .where(Report.discovery_run_id.in_([run.id for run in runs]))
            .order_by(Report.confidence.desc(), Report.source_url)
        ):
            assert report.discovery_run_id
            reports.setdefault(report.discovery_run_id, []).append(report)
    for run in runs:
        candidates = reports.get(run.id, [])
        selected = next((r for r in candidates if r.is_selected), None)
        items.append(
            {
                "run_id": str(run.id),
                "company_id": str(run.company_id),
                "company_name": company_map[run.company_id].company_name,
                "requested_year": run.requested_year,
                "status": run.status,
                "selection_reason": run.selection_reason,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "pages_visited": run.pages_visited,
                "http_requests": run.http_requests,
                "sources": run.sources,
                "diagnostics": run.diagnostics,
                "selected_report": report_dict(selected) if selected else None,
                "candidates": [report_dict(report) for report in candidates],
            }
        )
    items.sort(key=lambda item: (item["company_name"].lower(), item["requested_year"]))
    return {
        "year": year,
        "companies_processed": companies_processed,
        "company_years_processed": total,
        "counts": counts,
        "items": items,
        "total": total,
    }
