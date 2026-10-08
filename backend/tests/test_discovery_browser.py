"""Optional real browser, entirely mocked company HTTP (no live websites)."""

import os

import pytest

from app.discovery.browser import render_page
from app.discovery.crawler import discover
from test_discovery import PDF_URL, http_factory  # noqa: F401 -- share mock fixture


@pytest.mark.skipif(
    os.getenv("RUN_BROWSER_REPORT_TESTS") != "1",
    reason="Optional installed-browser test is opt-in",
)
def test_actual_restricted_browser_uses_mocked_robots_aware_transport(request):
    make_http = request.getfixturevalue("http_factory")
    url = "https://example.com/sustainability"
    http = make_http(
        {
            url: (
                200,
                "text/html",
                '<div id="root"></div><script src="/app.js"></script>',
            ),
            "https://example.com/app.js": (
                200,
                "application/javascript",
                f'document.getElementById("root").innerHTML = \'<a href="{PDF_URL}">Sustainability Report 2025</a>\';',
            ),
        },
        discovery_allow_js=True,
    )
    result = discover(http, [url], 2025, render_page)
    assert result.status == "discovered"
    assert any(item["code"] == "javascript_fallback" for item in result.diagnostics)
    assert "https://example.com/app.js" in http.session.calls
    assert http.session.calls[0] == "https://example.com/robots.txt"
