"""The branded exports remain read-only, source-linked and safe at larger sizes."""
from copy import deepcopy
from io import BytesIO

from bs4 import BeautifulSoup
import pymupdf
from reportlab.pdfgen.canvas import Canvas

from app.knowledge import report_design
from app.knowledge.publication import document
from app.knowledge.report_exports import html, pdf, source_url
from test_publication import sample_payload


def test_report_uses_real_brand_and_embedded_awards_with_navigation():
    payload = sample_payload()
    before = deepcopy(payload)
    with pymupdf.open(stream=pdf(payload), filetype="pdf") as parsed:
        assert parsed[0].get_images()  # Actual raster wordmark, not a typeset substitute.
        assert all(page.get_images() for page in parsed)
        assert len(parsed.get_toc()) >= 3
        assert any(link.get("uri", "").endswith("#page=12") for page in parsed for link in page.get_links())
        assert any(link["kind"] == pymupdf.LINK_GOTO for page in parsed for link in page.get_links())
        assert "Vero" == parsed.metadata["author"]
    assert payload == before


def test_html_is_self_contained_escaped_and_has_named_sections():
    payload = sample_payload()
    rendered = html(payload)
    soup = BeautifulSoup(rendered, "html.parser")
    assert soup.find("script") is None
    assert soup.find("img", alt="Vero")["src"].startswith("data:image/png;base64,")
    assert soup.find("nav", attrs={"aria-label": "Report contents"})
    assert soup.find(id="sources")
    assert soup.find("h1").text == payload["title"]
    assert all(image["src"].startswith("data:image/png;base64,") for image in soup.find_all("img"))
    assert all(soup.find(id=link["href"][1:]) for link in soup.select('a[href^="#"]'))


def test_signed_and_zero_chart_values_keep_all_company_labels():
    report_design._fonts()
    rows = [{"company_id": str(i), "company": f"Company {i} with a long full legal name", "value": v, "unit": "%", "year": 2025} for i, v in enumerate([-12.5, 0, 4.75])]
    chart = report_design.PeerChart(rows, (-12.5, 4.75), {}, report_design._styles())
    stream = BytesIO()
    canvas = Canvas(stream)
    _, height = chart.wrap(499, 700)
    chart.drawOn(canvas, 48, 700-height)
    canvas.save()
    with pymupdf.open(stream=stream.getvalue(), filetype="pdf") as parsed:
        text = parsed[0].get_text()
        assert all(row["company"] in text for row in rows)
        assert all(f"{row['value']}" in text for row in rows)
        assert text.count("2025") == 3


def test_large_cohort_and_long_findings_do_not_clip_or_drop_content():
    payload = sample_payload()
    doc = document(payload)
    payload["definition"]["companies"] = [
        {"id": str(i), "company_name": f"Company {i:02d} International Holdings and Research Limited", "sector": "Financial Services", "country": "GB"}
        for i in range(20)
    ]
    doc["title"] = "A detailed sustainability comparison of the selected international banking and financial services peer group"
    paragraph = doc["chapters"][0]["paragraphs"][0]
    paragraph["text"] = " ".join(["The saved report describes this finding and its supporting evidence."] * 55) + " END OF FINDING."
    with pymupdf.open(stream=report_design.render_pdf(payload, doc, source_url), filetype="pdf") as parsed:
        text = " ".join(" ".join(page.get_text().split()) for page in parsed)
        assert "END OF FINDING." in text
        assert all(company["company_name"] in text for company in payload["definition"]["companies"])
        for page in parsed:
            for block in page.get_text("blocks"):
                assert block[0] >= 35 and block[2] <= page.rect.width - 35
                assert block[1] >= 12 and block[3] <= page.rect.height - 12


def test_report_assets_are_available_in_the_project():
    assert report_design.asset("brand/vero-wordmark.png").is_file()
    for title in ("Clearest disclosure", "Best training system", "AI execution stack"):
        assert report_design.badge_asset(title).is_file()
