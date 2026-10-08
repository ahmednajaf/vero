import hashlib
import io
from unittest.mock import Mock

import pytest
import requests
from app.core.config import Settings
from app.db.models import Company, Report, ReportArtifact
from app.discovery.crawler import discover, needs_javascript
from app.discovery.http import AcquisitionError, SafeHTTP, SourcePolicy
from app.discovery.service import discover_company, download_report, status_snapshot
from app.services.company_import import import_companies
from bs4 import BeautifulSoup
from sqlalchemy import func, select
from sqlalchemy.orm import Session

PDF = b"%PDF-1.7\nFictional fixture; no real metrics.\n%%EOF"
PDF_URL = "https://example.com/sustainability-report-2025.pdf"


def test_discovery_policy_identifier_fits_existing_database_column():
    from app.db.models import ReportDiscoveryRun
    from app.discovery.crawler import POLICY_VERSION

    assert len(POLICY_VERSION) <= ReportDiscoveryRun.__table__.c.policy_version.type.length


class MockHTTP(requests.Session):
    """Mock at requests' transport boundary: robots and redirects exercise real code."""

    def __init__(self, routes):
        super().__init__()
        self.routes, self.calls = routes, []

    def get(self, url, **kwargs):
        self.calls.append(url)
        assert kwargs["allow_redirects"] is False and kwargs["stream"] is True
        item = self.routes.get(
            url,
            (
                (200, "text/plain", b"User-agent: *\nAllow: /")
                if url.endswith("/robots.txt")
                else (404, "text/html", b"Missing")
            ),
        )
        if isinstance(item, Exception):
            raise item
        code, mime, body, *headers = item
        response = requests.Response()
        response.status_code, response.url = code, url
        response.headers.update(
            {"Content-Type": mime, **(headers[0] if headers else {})}
        )
        response.raw = io.BytesIO(body if isinstance(body, bytes) else body.encode())
        return response


@pytest.fixture
def http_factory(tmp_path):
    clients = []

    def create(routes, **settings):
        config = Settings(
            _env_file=None,
            discovery_retries=0,
            reports_root=tmp_path / "reports",
            **settings,
        )
        client = SafeHTTP(
            config,
            SourcePolicy(("example.com",)),
            session=MockHTTP(routes),
            resolver=lambda _: None,
            sleeper=lambda _: None,
        )
        clients.append(client)
        return client

    yield create
    for client in clients:
        client.close()


def test_direct_pdf(http_factory):
    http = http_factory(
        {PDF_URL: (200, "application/pdf", PDF, {"Content-Length": str(len(PDF))})}
    )
    result = discover(http, [PDF_URL], 2025)
    assert result.status == "discovered"
    assert result.candidates[0].selected
    assert result.candidates[0].mime_type == "application/pdf"
    assert result.candidates[0].file_size == len(PDF)
    assert http.session.calls == ["https://example.com/robots.txt", PDF_URL]


def test_redirected_pdf_each_host_robots_checked(http_factory):
    target = "https://reports.example.com/sustainability-report-2025.pdf"
    http = http_factory(
        {
            PDF_URL: (302, "text/html", "", {"Location": target}),
            target: (200, "application/pdf", PDF),
        }
    )
    result = discover(http, [PDF_URL], 2025)
    assert result.candidates[0].url == target
    assert result.candidates[0].discovered_from == PDF_URL
    assert "https://reports.example.com/robots.txt" in http.session.calls


def test_multiple_candidates_keep_alternatives_and_reject_excluded_types(http_factory):
    body = """<a href='/sustainability-report-2024.pdf'>2024 Sustainability Report</a>
    <a href='/sustainability-report-2025.pdf'>2025 Sustainability Report</a>
    <a href='/esg-policy-2025.pdf'>ESG Policy 2025</a>
    <a href='/climate-report-2025.pdf'>2025 Climate Report</a>
    <a href='https://mirror.example.org/esg-report-2025.pdf'>ESG Report 2025</a>
    <a href='/annual-report-2025.pdf'>Annual Report 2025</a>"""
    http = http_factory({"https://example.com/": (200, "text/html", body)})
    result = discover(http, ["https://example.com/"], 2025)
    assert len(result.candidates) == 6
    assert sum(c.selected for c in result.candidates) == 1
    assert next(c for c in result.candidates if c.selected).url == PDF_URL
    assert all(
        c.status == "needs_review"
        for c in result.candidates
        if any(word in c.url for word in ("2024", "policy", "mirror", "annual"))
    )
    assert all("mirror.example.org" not in url for url in http.session.calls)


@pytest.mark.parametrize(
    "name",
    [
        "press-release",
        "brochure",
        "supplier-code",
        "policy",
        "investor-deck",
        "presentation",
        "highlights",
        "summary",
        "sustainable-bond",
        "green-bond",
        "bond-impact",
        "reporting-framework",
        "communication-on-progress",
        "assurance",
        "conflict-minerals",
        "forced-labour",
        "ceo-message",
        "sustainable-issuance",
        "principal-adverse-impact",
        "certain-weapons-statement",
    ],
)
def test_excluded_documents_cannot_win(name, http_factory):
    url = f"https://example.com/sustainability-report-2025-{name}.pdf"
    result = discover(http_factory({url: (200, "application/pdf", PDF)}), [url], 2025)
    assert result.status == "needs_review"
    assert not result.candidates[0].selected


def test_annual_report_needs_local_sustainability_context(http_factory):
    body = "<div><a href='/annual-report-2025.pdf'>Annual Report 2025</a> Includes sustainability disclosures</div>"
    result = discover(
        http_factory({"https://example.com/": (200, "text/html", body)}),
        ["https://example.com/"],
        2025,
    )
    assert result.candidates[0].selected


def test_missing_report_is_unavailable_not_zero_or_fake_report(http_factory):
    result = discover(
        http_factory({"https://example.com/": (200, "text/html", "<p>Contact us</p>")}),
        ["https://example.com/"],
        2025,
    )
    assert result.status == "unavailable" and result.candidates == []


def test_archive_table_report_beats_separate_assurance_pdf(http_factory):
    body = """<table>
    <tr><td>Hitachi Sustainability Report 2025</td><td><a href='/en_sustainability2025.pdf'>PDF format</a></td></tr>
    <tr><td>Hitachi Sustainability Report 2024</td><td><a href='/en_sustainability2024.pdf'>PDF format</a></td></tr>
    </table><a href='/sustainability/en_assurance2025.pdf'>Independent Practitioner's Limited Assurance Report</a>"""
    result = discover(
        http_factory({"https://example.com/": (200, "text/html", body)}),
        ["https://example.com/"],
        2025,
    )
    selected = [c for c in result.candidates if c.selected]
    assert len(selected) == 1
    assert selected[0].url.endswith("en_sustainability2025.pdf")
    assert all(not c.selected for c in result.candidates if "assurance" in c.url)


def test_non_financial_statement_is_a_sustainability_source(http_factory):
    body = (
        "<a href='/non-financial-statement-2025.pdf'>Non-Financial Statement 2025</a>"
    )
    result = discover(
        http_factory({"https://example.com/": (200, "text/html", body)}),
        ["https://example.com/"],
        2025,
    )
    assert result.candidates[0].selected
    assert result.candidates[0].report_type == "sustainability"


def test_empty_script_shell_without_react_root_is_detected():
    shell = '<html><title>Reporting centre</title><script src="/clientlibs/app.min.js"></script></html>'
    assert needs_javascript(BeautifulSoup(shell, "html.parser"))
    normal = (
        '<html><p>Report unavailable.</p><script src="analytics.js"></script></html>'
    )
    assert not needs_javascript(BeautifulSoup(normal, "html.parser"))


def test_annual_pdf_can_be_downloaded_for_a_subsequent_content_check(http_factory):
    body = '<a href="/annual-report-2025.pdf">Annual Report 2025</a>'
    http = http_factory(
        {"https://example.com/": (200, "text/html", body)},
        discovery_verify_annual_content=True,
    )
    result = discover(http, ["https://example.com/"], 2025)
    assert result.candidates[0].selected
    assert "requires PDF content check" in result.candidates[0].reason


def test_official_sitemap_finds_report_without_third_party_hosts(http_factory):
    from app.discovery.sitemaps import discover_sitemaps

    http = http_factory(
        {
            "https://example.com/robots.txt": (
                200,
                "text/plain",
                "User-agent: *\nAllow: /\nSitemap: https://example.com/map.xml",
            ),
            "https://example.com/": (200, "text/html", "<p>Home</p>"),
            "https://example.com/map.xml": (
                200,
                "application/xml",
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/sustainability-report-2025.pdf</loc></url><url><loc>https://mirror.com/esg-report-2025.pdf</loc></url></urlset>',
            ),
        }
    )
    discover(http, ["https://example.com/"], 2025)
    result = discover_sitemaps(http, 2025)
    assert len(result.candidates) == 1
    assert result.candidates[0].url == PDF_URL
    assert result.candidates[0].status == "discovered"
    assert not any("mirror.com" in url for url in http.session.calls)


def test_sitemap_entities_are_not_expanded(http_factory):
    from app.discovery.sitemaps import discover_sitemaps

    http = http_factory(
        {
            "https://example.com/robots.txt": (
                200,
                "text/plain",
                "User-agent: *\nAllow: /\nSitemap: https://example.com/map.xml",
            ),
            "https://example.com/": (200, "text/html", "<p>Home</p>"),
            "https://example.com/map.xml": (
                200,
                "application/xml",
                '<!DOCTYPE x [<!ENTITY e SYSTEM "file:///private">]><urlset>&e;</urlset>',
            ),
        }
    )
    discover(http, ["https://example.com/"], 2025)
    result = discover_sitemaps(http, 2025)
    assert not result.candidates
    assert result.diagnostics[0]["code"] == "unsafe_sitemap"


def test_prior_year_fallback_preserves_actual_year(db_engine, company, http_factory):
    body = '<a href="/sustainability-report-2024.pdf">Sustainability Report 2024</a>'
    http = http_factory(
        {"https://example.com/": (200, "text/html", body)},
        discovery_allow_prior_year=True,
    )
    with Session(db_engine) as session:
        run = discover_company(session, company, 2025, http.settings, http)
        report = session.scalar(
            select(Report).where(
                Report.discovery_run_id == run.id, Report.is_selected.is_(True)
            )
        )
        assert report.requested_year == 2025
        assert report.detected_year == 2024
        assert report.reporting_year is None
        assert "PRIOR-YEAR SOURCE 2024" in report.selection_reason


def test_robots_forbidden_is_not_repeated_for_alternative_files(http_factory):
    http = http_factory(
        {"https://example.com/robots.txt": (403, "text/plain", "Forbidden")}
    )
    for url in [PDF_URL, "https://example.com/alternative.pdf"]:
        with pytest.raises(AcquisitionError, match="HTTP 403"):
            http.get(url)
    assert http.session.calls == ["https://example.com/robots.txt"]


@pytest.mark.parametrize("annual_only", [False, True])
@pytest.mark.parametrize("crawl_budget_used", [False, True])
def test_ingestion_tries_alternatives_and_checks_annual_pdf_contents(
    db_engine, company, http_factory, monkeypatch, annual_only, crawl_budget_used
):
    import pymupdf
    from app.db.models import KnowledgeIndex
    from app.knowledge.ingestion import execute_job, queue

    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text(
        (50, 50),
        "Annual Report 2025. Financial statements only."
        if annual_only
        else "Sustainability Report 2025. Scope 1 emissions: 50 tonnes.",
    )
    content = pdf.tobytes()
    pdf.close()
    good = "https://example.com/annual-report-2025.pdf" if annual_only else PDF_URL
    broken = "https://example.com/esg-2025.pdf"
    body = f'<a href="{good}">{"Annual" if annual_only else "Sustainability"} Report 2025</a>'
    if not annual_only:
        body = f'<a href="{broken}">Sustainability Report 2025</a>' + body
    with Session(db_engine) as session, session.begin():
        record = session.get(Company, company.id)
        record.sustainability_url, record.investor_relations_url = (
            "https://example.com/",
            None,
        )
    http = http_factory(
        {
            "https://example.com/": (200, "text/html", body),
            good: (200, "application/pdf", content),
            broken: (200, "text/html", "Not a PDF"),
        },
        discovery_verify_annual_content=True,
    )
    monkeypatch.setattr(
        "app.knowledge.ingestion.SafeHTTP", lambda *args, **kwargs: http
    )
    if crawl_budget_used:
        full_budget = http.settings.discovery_max_requests

        def use_discovery_budget(*args, **kwargs):
            assert http.settings.discovery_max_requests < full_budget
            result = discover_company(*args, **kwargs)
            http.requests = http.settings.discovery_max_requests
            return result

        monkeypatch.setattr(
            "app.knowledge.ingestion.discover_company", use_discovery_budget
        )
    result = execute_job(
        db_engine, queue(db_engine, [company.id], 2025)[0], http.settings
    )
    with Session(db_engine) as session:
        indexed = session.scalar(select(func.count()).select_from(KnowledgeIndex))
    if annual_only:
        assert indexed == 0
        assert (
            result["outcome"]["reports"][0]["reason"]
            == "annual_report_sustainability_disclosure_not_identified"
        )
    else:
        assert indexed == 1
        attempts = result["outcome"]["reports"]
        assert len(attempts) == 2
        assert attempts[0]["stage"] == "download"
        assert "expected PDF MIME" in attempts[0]["reason"]
        assert attempts[1]["status"] == "indexed"


def test_timeout_is_failed_and_preserves_diagnostic(http_factory):
    result = discover(
        http_factory({PDF_URL: requests.Timeout("read timed out")}), [PDF_URL], 2025
    )
    assert result.status == "failed"
    assert result.diagnostics[0]["code"] == "timeout"


@pytest.mark.parametrize(
    "label,detected",
    [
        ("View our FY25 Sustainability Report", 2025),
        ("FY 25 Sustainability Report", 2025),
        ("FY24/25 Sustainability Report", None),
        ("FY24–FY25 Sustainability Report", None),
        ("25 Sustainability Report", 2026),
    ],
)
def test_fiscal_report_label_is_distinct_from_publication_directory(
    http_factory, label, detected
):
    from app.discovery.crawler import make_candidate

    http = http_factory({})
    candidate = make_candidate(
        "https://example.com/2026/sustainability-report.pdf",
        label, "", "https://example.com/", 2025, http,
    )
    assert candidate.detected_year == detected
    assert (candidate.status == "discovered") == (detected == 2025)


@pytest.mark.parametrize(
    "mime,reason",
    [
        ("application/pdf", "Per-company HTTP request budget exhausted"),
        (
            "application/x-pdf",
            "Download refused: expected PDF MIME, received application/x-pdf",
        ),
    ],
)
def test_bulk_resume_downloads_budget_deferred_candidate_without_recrawling(
    db_engine, company, http_factory, monkeypatch, tmp_path, mime, reason
):
    import pymupdf
    from app.db.models import KnowledgeJob
    from app.knowledge.collection import create_collection, run_collection
    from app.knowledge.ingestion import queue

    pdf = pymupdf.open()
    pdf.new_page().insert_text(
        (50, 50), "Sustainability Report 2025. Scope 1 emissions: 50 tonnes."
    )
    data = pdf.tobytes()
    pdf.close()
    http = http_factory(
        {PDF_URL: (200, mime, data)}, pipeline_root=tmp_path / "pipeline"
    )
    job_id = queue(db_engine, [company.id], 2025)[0]
    with Session(db_engine) as session:
        run = discover_company(session, company, 2025, http.settings, http)
        report = session.scalar(
            select(Report).where(
                Report.discovery_run_id == run.id, Report.is_selected.is_(True)
            )
        )
        report.status = "needs_review"
        job = session.get(KnowledgeJob, job_id)
        job.status = "failed"
        job.outcome = {
            "reports": [
                {
                    "report_id": str(report.id),
                    "status": "needs_review",
                    "stage": "download",
                    "reason": reason,
                }
            ]
        }
        session.commit()
    monkeypatch.setattr("app.knowledge.ingestion.SafeHTTP", lambda *a, **kw: http)
    monkeypatch.setattr(
        "app.knowledge.ingestion.discover_company",
        Mock(
            side_effect=AssertionError("Should resume download, not repeat discovery")
        ),
    )
    identifier = create_collection(db_engine, [company.id], 2025, {"workers": 1})
    outcome = run_collection(db_engine, identifier, http.settings)
    assert outcome["summary"]["outcomes"] == {"succeeded": 1}
    assert outcome["summary"]["downloaded_reports"] == 1


def test_js_rendered_fallback_only_when_explicitly_allowed(http_factory):
    url = "https://example.com/sustainability"
    shell = '<html><div id="root"></div><script src="app.js"></script></html>'
    renderer = Mock(return_value=f'<a href="{PDF_URL}">Sustainability Report 2025</a>')
    http = http_factory({url: (200, "text/html", shell)}, discovery_allow_js=True)
    result = discover(http, [url], 2025, renderer)
    assert result.status == "discovered"
    renderer.assert_called_once_with(url, http)
    assert result.diagnostics[0]["code"] == "javascript_fallback"
    disabled = discover(
        http_factory({url: (200, "text/html", shell)}), [url], 2025, renderer
    )
    assert disabled.status == "needs_review" and renderer.call_count == 1


def test_no_js_fallback_for_access_control_or_useful_static_html(http_factory):
    renderer = Mock()
    for html in (
        "<title>Access denied</title><script></script>",
        '<input type="password"><script></script>',
        f'<a href="{PDF_URL}">Sustainability Report 2025</a><script></script>',
    ):
        discover(
            http_factory(
                {"https://example.com/": (200, "text/html", html)},
                discovery_allow_js=True,
            ),
            ["https://example.com/"],
            2025,
            renderer,
        )
    renderer.assert_not_called()


def test_robots_wildcards_allow_precedence_and_fail_closed(http_factory):
    http = http_factory(
        {
            "https://example.com/robots.txt": (
                200,
                "text/plain",
                "User-agent: *\nDisallow: /*.pdf$\nAllow: /allowed.pdf$",
            )
        }
    )
    with pytest.raises(AcquisitionError, match="Disallowed"):
        http.get(PDF_URL)
    assert PDF_URL not in http.session.calls
    http.get("https://example.com/allowed.pdf").close()
    denied = http_factory(
        {"https://example.com/robots.txt": (403, "text/html", "Denied")}
    )
    with pytest.raises(AcquisitionError, match="robots.txt returned HTTP 403"):
        denied.get(PDF_URL)
    assert PDF_URL not in denied.session.calls


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.test/report.pdf",
        "https://example.com.evil.test/report.pdf",
        "http://example.com/report.pdf",
        "https://user:secret@example.com/report.pdf",
    ],
)
def test_redirect_policy_prevents_external_insecure_or_credentialed_redirects(
    target, http_factory
):
    http = http_factory({PDF_URL: (302, "text/html", "", {"Location": target})})
    with pytest.raises(AcquisitionError):
        http.get(PDF_URL)
    assert target not in http.session.calls


def test_private_dns_and_rate_limit_are_not_bypassed(http_factory):
    http = http_factory({PDF_URL: (429, "text/html", "Slow down")})
    with pytest.raises(AcquisitionError, match="429"):
        http.get(PDF_URL)
    assert http.session.calls.count(PDF_URL) == 1
    http.resolver = Mock(
        side_effect=AcquisitionError("private_address", "Private address")
    )
    with pytest.raises(AcquisitionError, match="Private address"):
        http.get(PDF_URL)
    assert http.session.calls.count(PDF_URL) == 1


def test_seed_order_and_bounded_crawl(http_factory):
    seeds = [
        "https://example.com/sustainability",
        "https://example.com/investors",
        "https://example.com/",
    ]
    http = http_factory(
        {url: (200, "text/html", "<a href='/climate'>Climate</a>") for url in seeds},
        discovery_max_pages=3,
    )
    result = discover(http, seeds, 2025)
    assert [
        url for url in http.session.calls if not url.endswith("robots.txt")
    ] == seeds
    assert result.status == "needs_review"


@pytest.fixture
def company(db_engine, company_row, csv_file):
    company_row["sustainability_url"] = PDF_URL
    assert import_companies(csv_file([company_row]), db_engine).committed
    with Session(db_engine) as session:
        instance = session.scalar(select(Company))
        session.expunge(instance)
        return instance


def test_discover_download_and_duplicate_blob(
    db_engine, company, http_factory, api_client
):
    http = http_factory({PDF_URL: (200, "application/pdf", PDF)})
    with Session(db_engine, expire_on_commit=False) as session:
        first = discover_company(session, company, 2025, http.settings, http)
        report = session.scalar(
            select(Report).where(
                Report.discovery_run_id == first.id, Report.is_selected.is_(True)
            )
        )
        assert report.reporting_year is None
        assert "Downloaded" in download_report(
            session, report, company, http.settings, http
        )
        assert report.content_sha256 == hashlib.sha256(PDF).hexdigest()
        assert (http.settings.reports_root / report.storage_key).read_bytes() == PDF
        second = discover_company(session, company, 2025, http.settings, http)
        duplicate = session.scalar(
            select(Report).where(
                Report.discovery_run_id == second.id, Report.is_selected.is_(True)
            )
        )
        assert "duplicate" in download_report(
            session, duplicate, company, http.settings, http
        )
        assert duplicate.artifact_id == report.artifact_id
        assert session.scalar(select(func.count()).select_from(ReportArtifact)) == 1
        assert len(list(http.settings.reports_root.rglob("*.pdf"))) == 1
        assert not list(http.settings.reports_root.rglob("*.part"))
        snapshot = status_snapshot(session, 2025)
        assert snapshot["companies_processed"] == 1
        assert snapshot["counts"]["downloaded"] == 1
        assert snapshot["items"][0]["run_id"] == str(second.id)
    response = api_client.get("/api/admin/report-status?year=2025&page_size=1")
    assert response.status_code == 200
    assert (
        response.json()["items"][0]["selected_report"]["sha256"]
        == hashlib.sha256(PDF).hexdigest()
    )
    assert api_client.get("/api/admin/report-status?page=0").status_code == 422
    assert (
        api_client.get("/api/admin/report-status?year=2024").json()[
            "companies_processed"
        ]
        == 0
    )


@pytest.mark.parametrize("allowed", [False, True])
def test_unlabelled_primary_source_is_opt_in_and_year_stays_unknown(
    db_engine, company, http_factory, allowed
):
    url = "https://example.com/sustainability-report.pdf"
    company.sustainability_url = url
    http = http_factory(
        {url: (200, "application/pdf", PDF)}, discovery_allow_unlabelled_year=allowed
    )
    with Session(db_engine) as session:
        run = discover_company(session, company, 2025, http.settings, http)
        selected = session.scalar(
            select(Report).where(
                Report.discovery_run_id == run.id, Report.is_selected.is_(True)
            )
        )
        if not allowed:
            assert selected is None
        else:
            assert selected.detected_year is selected.reporting_year is None
            assert "not 2025 coverage" in selected.selection_reason
            assert "Downloaded" in download_report(
                session, selected, company, http.settings, http
            )
            assert selected.detected_year is None


@pytest.mark.parametrize(
    "filename",
    ["assurance-statement", "supplier-code-report", "sustainability-report-summary"],
)
def test_unlabelled_fallback_does_not_approve_excluded_documents(
    db_engine, company, http_factory, filename
):
    url = f"https://example.com/{filename}.pdf"
    company.sustainability_url = url
    http = http_factory(
        {url: (200, "application/pdf", PDF)}, discovery_allow_unlabelled_year=True
    )
    with Session(db_engine) as session:
        run = discover_company(session, company, 2025, http.settings, http)
        assert run.status != "discovered"
        assert not session.scalar(
            select(Report.id).where(
                Report.discovery_run_id == run.id, Report.is_selected.is_(True)
            )
        )


@pytest.mark.parametrize(
    "mime,body,expected",
    [
        ("text/html", "<h1>Login</h1>", "wrong_mime"),
        ("application/pdf", b"Not a PDF", "wrong_signature"),
        ("application/pdf", b"%PDF-" + b"x" * (1024 * 1024), "size_limit"),
    ],
    ids=["wrong-mime", "wrong-signature", "oversized-pdf"],
)
def test_wrong_mime_signature_and_size_never_saved(
    db_engine, company, http_factory, mime, body, expected
):
    http = http_factory(
        {PDF_URL: (200, "application/pdf", PDF)}, discovery_max_download_mb=1
    )
    with Session(db_engine, expire_on_commit=False) as session:
        run = discover_company(session, company, 2025, http.settings, http)
        report = session.scalar(
            select(Report).where(
                Report.discovery_run_id == run.id, Report.is_selected.is_(True)
            )
        )
        http.session.routes[PDF_URL] = (200, mime, body)
        download_report(session, report, company, http.settings, http)
        assert report.status == "needs_review"
        assert report.content_sha256 is None
        assert run.diagnostics[-1]["code"] == expected
        assert not list(http.settings.reports_root.rglob("*.pdf"))
        assert not list(http.settings.reports_root.rglob("*.part"))


def test_robots_crawl_delay_retry_and_timeout_budget():
    now = [0.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    transport = MockHTTP(
        {
            "https://example.com/robots.txt": (
                200,
                "text/plain",
                "User-agent: *\nCrawl-delay: 3",
            ),
            PDF_URL: requests.Timeout("timeout"),
        }
    )
    http = SafeHTTP(
        Settings(_env_file=None, discovery_retries=1),
        SourcePolicy(("example.com",)),
        transport,
        lambda _: None,
        sleep,
        lambda: now[0],
    )
    with pytest.raises(AcquisitionError):
        http.get(PDF_URL)
    assert transport.calls.count(PDF_URL) == 2
    assert now[0] >= 6


def test_year_ambiguity_and_html_disclosures_require_review(http_factory):
    body = '<a href="/sustainability-report-2025.pdf">2024 Sustainability Report</a><a href="/esg-report-2025">ESG Report 2025</a>'
    result = discover(
        http_factory({"https://example.com/": (200, "text/html", body)}),
        ["https://example.com/"],
        2025,
    )
    assert result.status == "needs_review"
    assert all(not item.selected for item in result.candidates)


def test_candidate_limit_preserves_best_late_link_and_excludes_product_scope(
    http_factory,
):
    body = "".join(
        f'<a href="/environmental-report-{year}.pdf">Report {year}</a>'
        for year in range(2000, 2020)
    )
    body += f'<a href="{PDF_URL}">Sustainability Report 2025</a><a href="/products/environmental-report-2025.pdf">Product Environmental Report 2025</a>'
    result = discover(
        http_factory(
            {"https://example.com/": (200, "text/html", body)},
            discovery_max_candidates=2,
        ),
        ["https://example.com/"],
        2025,
    )
    assert len(result.candidates) == 2 and result.candidates[0].url == PDF_URL
    assert result.candidates[0].selected and not result.candidates[1].selected
    assert any(d["code"] == "candidate_limit" for d in result.diagnostics)


def test_unavailable_job_persisted_without_placeholder_url(
    db_engine, company, http_factory
):
    http = http_factory({})
    with Session(db_engine, expire_on_commit=False) as session:
        run = discover_company(session, company, 2025, http.settings, http)
        assert run.status == "unavailable"
        assert session.scalar(select(func.count()).select_from(Report)) == 0
        assert status_snapshot(session, 2025)["counts"]["unavailable"] == 1


def test_global_deduplication_across_companies_and_status_pagination(
    db_engine, company, http_factory, api_client
):
    http = http_factory({PDF_URL: (200, "application/pdf", PDF)})
    with Session(db_engine, expire_on_commit=False) as session:
        other = Company(
            company_name="Second Fictional plc",
            ticker="SECOND",
            country="GB",
            region="Europe",
            exchange="XLON",
            sector="Industrials",
            industry="Equipment",
            official_domain="example.com",
            sustainability_url=PDF_URL,
            reporting_year=2025,
        )
        session.add(other)
        session.commit()
        for current in (company, other):
            run = discover_company(session, current, 2025, http.settings, http)
            report = session.scalar(
                select(Report).where(
                    Report.discovery_run_id == run.id, Report.is_selected.is_(True)
                )
            )
            download_report(session, report, current, http.settings, http)
        assert session.scalar(select(func.count()).select_from(ReportArtifact)) == 1
        assert len(list(http.settings.reports_root.rglob("*.pdf"))) == 1
    data = api_client.get(
        "/api/admin/report-status?year=2025&page_size=1&page=2"
    ).json()
    assert data["companies_processed"] == 2 and data["counts"]["downloaded"] == 2
    assert data["total"] == 2 and data["total_pages"] == 2 and len(data["items"]) == 1
    assert (
        api_client.get("/api/admin/report-status?year=2025&page_size=1&page=3").json()[
            "items"
        ]
        == []
    )


def test_direct_sql_discovery_constraints_and_lossy_downgrade_refusal(
    db_engine, company, http_factory, migration_config
):
    from alembic import command
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError, ProgrammingError

    http = http_factory({PDF_URL: (200, "application/pdf", PDF)})
    with Session(db_engine, expire_on_commit=False) as session:
        run = discover_company(session, company, 2025, http.settings, http)
        report_id = session.scalar(
            select(Report.id).where(Report.discovery_run_id == run.id)
        )
    for assignment in ("status='invented'", "confidence=1.01", "requested_year=2024"):
        with pytest.raises(IntegrityError), db_engine.begin() as connection:
            connection.execute(
                text(f"UPDATE reports SET {assignment} WHERE id=:id"), {"id": report_id}
            )
    with (
        pytest.raises(ProgrammingError, match="Refusing lossy"),
        db_engine.begin() as connection,
    ):
        migration_config.attributes["connection"] = connection
        command.downgrade(migration_config, "0001")


def test_report_navigation_outranks_news_old_archives_and_binary_downloads():
    from app.discovery.crawler import navigation_priority, NON_DOCUMENT

    hub = navigation_priority("/en/sustainability/reports/", 2025)
    assert hub < navigation_priority("/news/2025/sustainability-event/", 2025)
    assert hub < navigation_priority("/annual-reports/2016/", 2025)
    assert NON_DOCUMENT.search("/annual-report-2025.zip")
    assert not NON_DOCUMENT.search("/annual-report-2025.pdf")
