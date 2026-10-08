"""Literal modern page data is provenance, not executable crawler instructions."""

import json

from bs4 import BeautifulSoup

from app.discovery.crawler import discover, published_downloads
from test_discovery import http_factory  # noqa: F401

URL = "https://cdn.sanity.io/files/project/global/hash.pdf"
RECORD = {
    "file": {"url": URL, "originalFilename": "2025-annual-report.pdf"},
    "label": "2025 Annual Report",
}


def soup(script):
    return BeautifulSoup(script, "html.parser")


def test_json_file_metadata_is_kept_together():
    result = published_downloads(
        soup(
            '<script type="application/json">'
            + json.dumps({"downloads": [RECORD]})
            + "</script>"
        )
    )
    assert result == [(URL, "2025 Annual Report 2025-annual-report.pdf")]


def test_next_literal_frames_are_decoded_without_executing_script():
    frame = json.dumps([1, "8:" + json.dumps([RECORD]) + "\n"])
    result = published_downloads(
        soup("<script>self.__next_f.push(" + frame + ")</script>")
    )
    assert result == [(URL, "2025 Annual Report 2025-annual-report.pdf")]
    assert not published_downloads(
        soup('<script>self.__next_f.push(eval("' + URL + '"))</script>')
    )


def test_arbitrary_script_urls_and_unrelated_metadata_are_not_links():
    assert not published_downloads(soup('<script>window.asset="' + URL + '"</script>'))
    data = {"title": "2025 Sustainability Report", "unrelated": {"url": URL}}
    assert not published_downloads(
        soup('<script type="application/json">' + json.dumps(data) + "</script>")
    )


def test_duplicate_frames_do_not_duplicate_downloads():
    script = '<script type="application/json">' + json.dumps(RECORD) + "</script>"
    assert len(published_downloads(soup(script + script))) == 1


def test_published_json_download_flows_through_official_source_policy(http_factory):  # noqa: F811
    origin = "https://example.com/"
    html = '<script type="application/json">' + json.dumps(RECORD) + "</script>"
    http = http_factory(
        {origin: (200, "text/html", html)}, discovery_verify_annual_content=True
    )
    result = discover(http, [origin], 2025)
    selected = next(c for c in result.candidates if c.selected)
    assert selected.url == URL and selected.official
    assert URL in http.policy.document_urls
    assert not http.policy.owns(URL)
    assert result.diagnostics[0]["evidence_method"] == "literal_page_download_data"
