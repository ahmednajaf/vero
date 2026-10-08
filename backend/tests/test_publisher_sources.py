# ruff: noqa: F811 -- pytest shared fixtures are imported by name.
"""Official-page PDF links may use publishing CDNs, never arbitrary mirrors."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Report
from app.discovery.crawler import discover
from app.discovery.http import AcquisitionError, SourcePolicy
from app.discovery.service import discover_company, download_report
from test_discovery import PDF, company, http_factory  # noqa: F401

CDN = "https://s21.q4cdn.com/123/files/2025-sustainability-report.pdf"
ORIGIN = "https://example.com/"


def test_resume_reuses_robot_file_failure_only_after_explicit_opt_in():
    from uuid import uuid4

    from app.knowledge.ingestion import retryable_downloads

    identifier = uuid4()
    report = {
        "report_id": str(identifier),
        "stage": "download",
        "reason": "robots.txt returned HTTP 403; stopped conservatively",
    }
    assert not retryable_downloads({"reports": [report]})
    assert retryable_downloads(
        {"reports": [report]}, allow_unavailable_robots=True
    ) == {identifier}
    for refusal in (
        "HTTP 403",
        "Disallowed by robots.txt",
        "robots.txt presented a login or bot challenge; stopped",
    ):
        assert not retryable_downloads(
            {"reports": [{**report, "reason": refusal}]},
            allow_unavailable_robots=True,
        )


def test_exact_asset_grant_does_not_allow_entire_cdn():
    policy = SourcePolicy(("example.com",)).endorse_document(CDN, ORIGIN)
    assert policy.check(CDN) == CDN
    assert not policy.owns(CDN)
    assert policy.check("https://s21.q4cdn.com/robots.txt")
    for other in (
        CDN + "?new=1",
        "https://s21.q4cdn.com/other.pdf",
        "https://s21.q4cdn.com/",
        "http://s21.q4cdn.com/robots.txt",
    ):
        with pytest.raises(AcquisitionError):
            policy.check(other)


@pytest.mark.parametrize(
    "host",
    [
        "downloads.ctfassets.net",
        "assets.contentstack.io",
        "company-cdn.azureedge.net",
        "company.a01.azurefd.net",
        "delivery-p157365-e1666014.adobeaemcloud.com",
        "company.s3.us-east-2.amazonaws.com",
        "company.s3.amazonaws.com",
    ],
)
def test_observed_publisher_families_are_exact_file_grants(host):
    url = f"https://{host}/2025-sustainability-report.pdf"
    policy = SourcePolicy(("example.com",)).endorse_document(url, ORIGIN)
    assert policy.check(url) == url
    assert not policy.owns(url)
    with pytest.raises(AcquisitionError):
        policy.check(f"https://{host}/another-company.pdf")
    with pytest.raises(AcquisitionError):
        policy.check(f"https://{host}/")
    assert SourcePolicy(("example.com",)).endorse_document(
        url, "https://mirror.example.org/"
    ).document_urls == ()


@pytest.mark.parametrize(
    "url,source",
    [
        (CDN, "https://mirror.example.org/"),
        (CDN, "http://example.com/"),
        ("https://s21.q4cdn.com.evil.example/report.pdf", ORIGIN),
        ("https://mirror.example.org/report.pdf", ORIGIN),
        ("https://assets.ctfassets.net/viewer.html", ORIGIN),
        ("http://assets.ctfassets.net/report.pdf", ORIGIN),
        ("https://company.azurefd.net.evil.example/report.pdf", ORIGIN),
        ("https://company.s3.us-east-2.amazonaws.com.evil.example/report.pdf", ORIGIN),
        ("https://random.adobeaemcloud.com/report.pdf", ORIGIN),
        ("https://assets.contentstack.io/viewer", ORIGIN),
    ],
)
def test_untrusted_sources_and_non_pdf_assets_are_never_endorsed(url, source):
    policy = SourcePolicy(("example.com",))
    assert policy.endorse_document(url, source) == policy


def test_crawler_preserves_observed_official_link_and_skips_mirror(http_factory):
    http = http_factory(
        {
            ORIGIN: (
                200,
                "text/html",
                f'<a href="{CDN}">2025 Sustainability Report</a><a href="https://mirror.example.org/report-2025.pdf">2025 ESG report</a>',
            )
        }
    )
    result = discover(http, [ORIGIN], 2025)
    assert result.status == "discovered"
    selected = next(c for c in result.candidates if c.selected)
    assert selected.url == CDN and selected.official
    assert (
        next(d for d in result.diagnostics if d["code"] == "official_document_link")[
            "source_page"
        ]
        == ORIGIN
    )
    assert not any("mirror.example.org" in call for call in http.session.calls)


def test_resumed_download_restores_exact_grant_and_checks_cdn_robots(
    db_engine, company, http_factory
):
    discovery = http_factory(
        {ORIGIN: (200, "text/html", f'<a href="{CDN}">2025 Sustainability Report</a>')}
    )
    with Session(db_engine) as session:
        run = discover_company(session, company, 2025, discovery.settings, discovery)
        report = session.scalar(
            select(Report).where(Report.discovery_run_id == run.id, Report.is_selected)
        )
        downloader = http_factory({CDN: (200, "application/pdf", PDF)})
        download_report(session, report, company, downloader.settings, downloader)
        assert report.status == "downloaded" and report.content_sha256
        assert "https://s21.q4cdn.com/robots.txt" in downloader.session.calls


def test_publisher_link_never_bypasses_robots(http_factory):
    http = http_factory(
        {
            "https://s21.q4cdn.com/robots.txt": (
                200,
                "text/plain",
                "User-agent: *\nDisallow: /",
            ),
            CDN: (200, "application/pdf", PDF),
        }
    )
    http.policy = http.policy.endorse_document(CDN, ORIGIN)
    with pytest.raises(AcquisitionError, match="Disallowed"):
        http.get(CDN)
    assert CDN not in http.session.calls


@pytest.mark.parametrize("disallowed", [False, True])
def test_exact_cdn_robots_redirect_is_metadata_only(http_factory, disallowed):
    handler = "https://s21.q4cdn.com/notfound.aspx?item=robots"
    http = http_factory(
        {
            "https://s21.q4cdn.com/robots.txt": (
                302, "text/html", "", {"Location": handler},
            ),
            handler: (
                200 if disallowed else 404,
                "text/plain",
                "User-agent: *\nDisallow: /" if disallowed else "Not found",
            ),
            CDN: (200, "application/pdf", PDF),
        }
    )
    http.policy = http.policy.endorse_document(CDN, ORIGIN)
    if disallowed:
        with pytest.raises(AcquisitionError, match="Disallowed"):
            http.get(CDN)
        assert CDN not in http.session.calls
    else:
        assert http.get(CDN).status_code == 200
    assert handler in http.session.calls
    assert http.audit[0]["resource"] == "robots"
    assert http.policy.document_urls == (CDN,)
    with pytest.raises(AcquisitionError):
        http.get(handler)


def test_cdn_redirect_to_unobserved_asset_stops(http_factory):
    http = http_factory(
        {
            CDN: (
                302,
                "text/html",
                "",
                {"Location": "https://s21.q4cdn.com/other-company.pdf"},
            )
        }
    )
    http.policy = http.policy.endorse_document(CDN, ORIGIN)
    with pytest.raises(AcquisitionError, match="approved"):
        http.get(CDN)
    assert http.audit[-1]["target_url"] == "https://s21.q4cdn.com/other-company.pdf"
    assert "https://s21.q4cdn.com/other-company.pdf" not in http.session.calls


def test_explicit_unavailable_robots_mode_allows_only_published_pdf(http_factory):
    http = http_factory(
        {
            "https://s21.q4cdn.com/robots.txt": (
                403,
                "text/html",
                "<title>403 Forbidden</title>",
            ),
            CDN: (200, "application/pdf", PDF),
        },
        discovery_allow_unavailable_robots_for_linked_documents=True,
    )
    http.policy = http.policy.endorse_document(CDN, ORIGIN)
    assert http.get(CDN).status_code == 200
    assert http.audit[0]["code"] == "robots_unavailable_exact_document"
    assert http.audit[0]["http_status"] == 403
    with pytest.raises(AcquisitionError):
        http.get("https://s21.q4cdn.com/not-published.pdf")


@pytest.mark.parametrize(
    "status,body",
    [
        (200, "User-agent: *\nDisallow: /"),
        (403, "<title>Verify you are human CAPTCHA</title>"),
        (401, "Login required"),
        (429, "Slow down"),
        (503, "Unavailable"),
    ],
)
def test_exact_pdf_rule_preserves_robots_and_access_controls(
    http_factory, status, body
):
    http = http_factory(
        {
            "https://s21.q4cdn.com/robots.txt": (status, "text/plain", body),
            CDN: (200, "application/pdf", PDF),
        },
        discovery_allow_unavailable_robots_for_linked_documents=True,
    )
    http.policy = http.policy.endorse_document(CDN, ORIGIN)
    with pytest.raises(AcquisitionError):
        http.get(CDN)
    assert CDN not in http.session.calls


def test_robots_403_still_stops_without_opt_in(http_factory):
    http = http_factory(
        {"https://s21.q4cdn.com/robots.txt": (403, "text/plain", "Forbidden")}
    )
    http.policy = http.policy.endorse_document(CDN, ORIGIN)
    with pytest.raises(AcquisitionError):
        http.get(CDN)


def test_exact_owned_pdf_exception_never_allows_html_crawling(http_factory):
    pdf = "https://example.com/sustainability-2025.pdf"
    http = http_factory(
        {
            ORIGIN + "robots.txt": (403, "text/plain", "Forbidden"),
            pdf: (200, "application/pdf", PDF),
            ORIGIN: (200, "text/html", "Home"),
        },
        discovery_allow_unavailable_robots_for_linked_documents=True,
    )
    with pytest.raises(AcquisitionError):
        http.get(ORIGIN)
    http.policy = http.policy.endorse_document(pdf, ORIGIN + "reports")
    assert http.get(pdf).status_code == 200
    with pytest.raises(AcquisitionError):
        http.get(ORIGIN)
    assert ORIGIN not in http.session.calls
    assert http.audit[0]["url"] == pdf


def test_owned_pdf_download_endpoint_is_exact_not_a_host_grant():
    pdf = ORIGIN + "get_file/?file_id=123&file_ext=.pdf"
    policy = SourcePolicy(("example.com",)).endorse_document(pdf, ORIGIN)
    assert policy.document_urls == (pdf,)
    assert not policy.endorse_document(ORIGIN + "viewer", ORIGIN).document_urls[1:]
    external = "https://assets.ctfassets.net/get_file/?file_id=123&file_ext=.pdf"
    assert policy.endorse_document(external, ORIGIN) == policy


def test_owned_pdf_redirect_retains_exact_file_scope(http_factory):
    start = ORIGIN + "get_file/?file_id=123&file_ext=.pdf"
    final = "https://download.example.com/2025-report.pdf?Signature=public-link"
    http = http_factory(
        {
            start: (302, "text/html", "", {"Location": final}),
            "https://download.example.com/robots.txt": (403, "text/plain", "Forbidden"),
            final: (200, "application/pdf", PDF),
        },
        discovery_allow_unavailable_robots_for_linked_documents=True,
    )
    http.policy = http.policy.endorse_document(start, ORIGIN + "reports")
    assert http.get(start).status_code == 200
    assert final in http.policy.document_urls
    with pytest.raises(AcquisitionError):
        http.get("https://download.example.com/other.pdf")
    assert "https://download.example.com/other.pdf" not in http.session.calls


def test_viewer_uses_document_url_not_extension_or_filename(http_factory):
    http = http_factory(
        {
            ORIGIN: (
                200,
                "text/html",
                """
      <a href="/get_file/?id=123&amp;file_ext=.pdf">2025 Sustainability Report</a>
      <a href="/viewer?mediaId=%2Freports%2F2025-climate-report.pdf">2025 Climate Report</a>
      <a href="/download?filename=2025-esg-report.pdf">2025 ESG Report</a>
    """,
            )
        }
    )
    result = discover(http, [ORIGIN], 2025)
    urls = {candidate.url for candidate in result.candidates}
    assert ORIGIN + "get_file/?id=123&file_ext=.pdf" in urls
    assert ORIGIN + "reports/2025-climate-report.pdf" in urls
    assert not any("/get_file/.pdf" in url for url in urls)
    assert ORIGIN + "2025-esg-report.pdf" not in urls


def test_actual_pdf_403_is_never_bypassed(http_factory):
    from app.discovery.http import require_success

    http = http_factory(
        {
            "https://s21.q4cdn.com/robots.txt": (403, "text/plain", "Forbidden"),
            CDN: (403, "text/plain", "Forbidden"),
        },
        discovery_allow_unavailable_robots_for_linked_documents=True,
    )
    http.policy = http.policy.endorse_document(CDN, ORIGIN)
    with pytest.raises(AcquisitionError, match="no authentication or anti-bot bypass"):
        require_success(http.get(CDN))
    assert http.session.calls.count(CDN) == 1
