"""No company HTTP calls happen during the ordinary test suite."""

import os

import pytest

from app.core.config import Settings
from app.discovery.crawler import discover
from app.discovery.http import SafeHTTP, SourcePolicy


@pytest.mark.live
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_REPORT_TESTS") != "1",
    reason="Live official-site smoke test is opt-in",
)
def test_explicit_official_site_smoke():
    domain = os.environ["LIVE_OFFICIAL_DOMAIN"]
    url = os.environ["LIVE_SUSTAINABILITY_URL"]
    http = SafeHTTP(
        Settings(_env_file=None, discovery_max_pages=3), SourcePolicy((domain,))
    )
    try:
        result = discover(http, [url], int(os.getenv("LIVE_REPORT_YEAR", "2025")))
        assert result.http_requests > 0
        assert result.status in {"discovered", "needs_review", "unavailable", "failed"}
        assert all(not c.selected or c.official for c in result.candidates)
        print(result)
    finally:
        http.close()
