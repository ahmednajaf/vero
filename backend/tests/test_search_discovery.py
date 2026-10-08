import threading
from urllib.parse import urlencode

import pytest

from app.core.config import Settings
from app.discovery import search_engine
from app.discovery.http import AcquisitionError, SafeHTTP, SourcePolicy
from test_discovery import MockHTTP


def search_client(monkeypatch, body, code=200):
    settings = Settings(_env_file=None)
    query = "site:example.com 2025 sustainability ESG environmental annual report filetype:pdf"
    url = "https://html.duckduckgo.com/html/?" + urlencode({"q": query})
    transport = MockHTTP({url: (code, "text/html", body)})
    client = SafeHTTP(
        settings,
        SourcePolicy(("html.duckduckgo.com",)),
        session=transport,
        resolver=lambda _: None,
        sleeper=lambda _: None,
    )
    monkeypatch.setattr(search_engine, "SafeHTTP", lambda *a, **kw: client)
    monkeypatch.setattr(search_engine, "_disabled", threading.Event())
    return settings, transport


def test_search_retains_official_urls_not_third_party_mirrors(monkeypatch):
    body = """<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Freport-2025.pdf">2025 Sustainability Report</a><span class="result__snippet">Source discovery only</span></div>
    <a class="result__a" href="https://mirror.com/report-2025.pdf">Report</a>"""
    settings, transport = search_client(monkeypatch, body)
    hits, url = search_engine.official_search("example.com", 2025, settings)
    assert hits == [
        {
            "url": "https://example.com/report-2025.pdf",
            "title": "2025 Sustainability Report",
            "snippet": "Source discovery only",
        }
    ]
    assert transport.calls[0].endswith("/robots.txt")
    assert "mirror.com" not in " ".join(transport.calls)


@pytest.mark.parametrize(
    "code,body",
    [
        (202, "challenge"),
        (429, "slow down"),
        (200, '<form id="challenge-form">Challenge</form>'),
    ],
)
def test_search_challenge_opens_circuit_without_bypass(monkeypatch, code, body):
    settings, transport = search_client(monkeypatch, body, code)
    with pytest.raises(AcquisitionError):
        search_engine.official_search("example.com", 2025, settings)
    count = len(transport.calls)
    with pytest.raises(AcquisitionError, match="challenged/rate-limited"):
        search_engine.official_search("example.com", 2025, settings)
    assert len(transport.calls) == count


def test_filename_year_precedes_upload_directory_year():
    from app.discovery.crawler import make_candidate

    http = SafeHTTP(Settings(_env_file=None), SourcePolicy(("example.com",)))
    try:
        result = make_candidate(
            "https://example.com/uploads/2026/sustainability-report-2025.pdf",
            "Download report",
            "",
            "https://example.com/",
            2025,
            http,
        )
        assert result.detected_year == 2025
        assert result.status == "discovered"
    finally:
        http.close()
