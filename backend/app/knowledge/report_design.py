"""Vero's offline, print-first report design. All content comes from publication.document.

Charts use the saved calculated rows, never a second analytical/model call. Brand
assets are shared with the frontend; report graphics are native PDF vectors.
"""
from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
import re
from typing import Any

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak, Flowable, HRFlowable, Image, KeepTogether, PageBreak,
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


ASSETS = Path(__file__).resolve().parents[3] / "frontend" / "public"
INK = colors.HexColor("#171924")
MUTED = colors.HexColor("#626879")
ACCENT = colors.HexColor("#6855a2")
LINE = colors.HexColor("#dddfe7")
PAPER = colors.HexColor("#f4f3f8")
PEER_COLORS = ["#8c7bc1", "#5c92bc", "#63a3a3", "#ad8a6c", "#8f98ad"]
WIDTH, HEIGHT = A4
MARGIN = 48
CONTENT = WIDTH - 2 * MARGIN


def asset(name: str) -> Path:
    return ASSETS / name


def badge_asset(name: str) -> Path:
    words = name.lower()
    category = "people" if any(k in words for k in ("people", "training", "inclusion", "diversity", "women")) else (
        "innovation" if any(k in words for k in ("innovation", "ai ", "digital", "execution stack")) else "clarity"
    )
    return asset(f"awards/{category}.png")


def number(value: Any) -> str:
    return f"{float(value):,.3f}".rstrip("0").rstrip(".")


def clean(value: Any) -> str:
    # Normalize punctuation, not facts. No truncation of findings or company names.
    return re.sub(r"[\u2010-\u2015\u2212]", "-", str(value)).replace("\u00a0", " ")


def _fonts() -> None:
    folder = Path(reportlab.__file__).parent / "fonts"
    for name, filename in [("VeroSans", "Vera.ttf"), ("VeroSans-Bold", "VeraBd.ttf")]:
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(folder / filename)))
    pdfmetrics.registerFontFamily("VeroSans", normal="VeroSans", bold="VeroSans-Bold")


def _styles() -> dict[str, ParagraphStyle]:
    base = dict(fontName="VeroSans", textColor=INK, fontSize=9.4, leading=15, spaceAfter=10)
    def style(name: str, **changes: Any) -> ParagraphStyle:
        return ParagraphStyle(name, **{**base, **changes})
    return {
        "body": style("body"),
        "small": style("small", fontSize=7.6, leading=11.5, textColor=MUTED, spaceAfter=7),
        "cell": style("cell", fontSize=8, leading=12, spaceAfter=0),
        "cell_head": style("cell_head", fontName="VeroSans-Bold", fontSize=7.3, leading=11, spaceAfter=0),
        "label": style("label", fontName="VeroSans-Bold", fontSize=7.4, leading=11, textColor=ACCENT, spaceAfter=10, keepWithNext=True),
        "chapter": style("chapter", fontName="Times-Roman", fontSize=29, leading=33, spaceAfter=20, keepWithNext=True),
        "head": style("head", fontName="VeroSans-Bold", fontSize=12, leading=17, spaceBefore=5, spaceAfter=10, keepWithNext=True),
        "appendix_head": style("appendix_head", fontName="VeroSans-Bold", fontSize=10.5, leading=14, spaceBefore=9, spaceAfter=5, keepWithNext=True),
        "appendix": style("appendix", fontSize=7.6, leading=11.5, textColor=MUTED, spaceAfter=3),
        "takeaway": style("takeaway", fontSize=10.3, leading=16, textColor=ACCENT),
        "cover": style("cover", fontName="Times-Roman", fontSize=36, leading=40, spaceAfter=0),
        "cover_white": style("cover_white", fontName="Times-Roman", fontSize=25, leading=30, textColor=colors.white),
    }


class PeerChart(Flowable):  # type: ignore[misc]  # ReportLab has no Flowable stubs.
    """Zero-based bars with signed values; no hidden peers or implied ranking."""

    def __init__(self, rows: list[dict[str, Any]], domain: tuple[float, float], peer_colors: dict[str, str], styles: dict[str, Any]):
        Flowable.__init__(self)
        self.rows, self.domain, self.peer_colors, self.styles = rows, domain, peer_colors, styles
        self.width = CONTENT

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        self.width = min(CONTENT, availWidth)
        self.layout = []
        for row in self.rows:
            label = Paragraph(escape(clean(row["company"])) + f' <font color="#626879" size="7">/ {escape(str(row["year"]))}</font>', self.styles["cell"])
            value = Paragraph(f'<font size="12">{escape(number(row["value"]))}</font> <font size="7.5">{escape(str(row["unit"]))}</font>', self.styles["cell_head"])
            _, lh = label.wrap(self.width * .64, 1000)
            _, vh = value.wrap(self.width * .30, 1000)
            self.layout.append((label, value, max(lh, vh) + 39))
        self.height = sum(item[2] for item in self.layout) + 24
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        low, high = self.domain
        span = high - low or 1
        zero = (0 - low) / span * self.width
        y = self.height
        for row, (label, value, height) in zip(self.rows, self.layout):
            label.drawOn(c, 0, y - label.height)
            value.drawOn(c, self.width * .70, y - value.height)
            y -= height
            c.setFillColor(colors.HexColor("#eeedf3"))
            c.roundRect(0, y + 9, self.width, 8, 4, stroke=0, fill=1)
            x = (float(row["value"]) - low) / span * self.width
            c.setFillColor(colors.HexColor(self.peer_colors.get(row["company_id"], PEER_COLORS[0])))
            if abs(x - zero) > .1:
                c.roundRect(min(zero, x), y + 9, abs(x - zero), 8, min(4, abs(x-zero)/2), stroke=0, fill=1)
            else:
                c.circle(zero, y + 13, 2.5, stroke=0, fill=1)
            if low < 0 < high:
                c.setStrokeColor(MUTED)
                c.line(zero, y + 7, zero, y + 19)
        c.setFillColor(MUTED)
        c.setFont("VeroSans", 7)
        c.drawString(0, 3, number(low))
        c.drawRightString(self.width, 3, number(high))
        if low < 0 < high:
            c.drawCentredString(zero, 3, "0")


class Cover(Flowable):  # type: ignore[misc]  # ReportLab has no Flowable stubs.
    def __init__(self, doc: dict[str, Any], payload: dict[str, Any], styles: dict[str, Any]):
        Flowable.__init__(self)
        self.doc, self.payload, self.styles = doc, payload, styles
        self.width, self.height = CONTENT, 686

    def draw(self) -> None:
        c = self.canv
        logo = asset("brand/vero-wordmark.png")
        if logo.exists():
            c.drawImage(str(logo), -5, 622, width=142, height=55, preserveAspectRatio=True, mask="auto")
        else:
            c.setFont("VeroSans-Bold", 30)
            c.drawString(0, 643, "Vero")
        c.setFillColor(MUTED)
        c.setFont("VeroSans", 7)
        c.drawRightString(CONTENT, 658, "SUSTAINABILITY / PEER INTELLIGENCE")
        c.setStrokeColor(LINE)
        c.line(0, 608, CONTENT, 608)

        def draw_text(text: str, style: str, x: float, top: float, width: float) -> float:
            paragraph = Paragraph(escape(clean(text)).replace("\n", "<br/>"), self.styles[style])
            _, height = paragraph.wrap(width, 1000)
            paragraph.drawOn(c, x, top - height)
            return float(top - height)

        draw_text(self.doc["package"].upper(), "label", 0, 580, CONTENT)
        title = Paragraph(escape(clean(self.doc["title"])), self.styles["cover"])
        _, th = title.wrap(CONTENT, 1000)
        size = 36
        while th > 145 and size > 17:
            size -= 1
            compact = ParagraphStyle("compact_cover", parent=self.styles["cover"], fontSize=size, leading=size + 4)
            title = Paragraph(escape(clean(self.doc["title"])), compact)
            _, th = title.wrap(CONTENT, 1000)
        title.drawOn(c, 0, 550 - th)
        companies = self.payload["definition"]["companies"]
        cohort = " / ".join(x["company_name"] for x in companies) if len(companies) <= 5 else f"{len(companies)} selected companies - full peer group inside"
        draw_text(cohort, "small", 0, 540 - th, CONTENT)

        # An editorial orbital motif, not a data chart. No environmental claims.
        c.setFillColor(INK)
        c.roundRect(0, 52, CONTENT, 270, 12, stroke=0, fill=1)
        c.saveState()
        clip = c.beginPath()
        clip.rect(CONTENT * .53, 144, CONTENT * .47, 178)
        c.clipPath(clip, stroke=0)
        for i in range(12):
            c.setStrokeColor(colors.HexColor("#4b4569" if i % 3 else "#8c7bc1"))
            c.setLineWidth(.7 if i % 3 else 1.1)
            c.ellipse(CONTENT - 185 - i * 8, 118 - i * 6, CONTENT + 88 + i * 8, 385 + i * 6, stroke=1, fill=0)
        c.restoreState()
        c.setFillColor(colors.HexColor("#c5bbdf"))
        c.setFont("VeroSans-Bold", 7)
        c.drawString(23, 286, "THE PEER PERSPECTIVE")
        draw_text("Evidence.\nPerspective.\nAdvantage.", "cover_white", 23, 264, 230)
        c.setStrokeColor(colors.HexColor("#464052"))
        c.line(23, 135, CONTENT - 23, 135)
        for x, value, label in [(23, len(companies), "COMPANIES"), (174, len(self.doc["awards"]), "CALCULATIONS"), (325, len(self.doc["badges"]), "DISTINCTIONS")]:
            c.setFont("Times-Roman", 26)
            c.setFillColor(colors.white)
            c.drawString(x, 99, str(value))
            c.setFont("VeroSans", 6.5)
            c.setFillColor(colors.HexColor("#c5c3cf"))
            c.drawString(x, 79, label)
        c.setFont("VeroSans", 7)
        c.setFillColor(MUTED)
        c.drawString(0, 27, "Prepared " + str(self.payload.get("created_at", ""))[:10])
        c.drawRightString(CONTENT, 27, "VERO / RESEARCH EDITION")
        if self.doc["incomplete"]:
            c.setFillColor(ACCENT)
            c.setFont("VeroSans-Bold", 8)
            c.drawString(0, 7, "WORKING DRAFT / ANALYSIS INCOMPLETE")


def render_pdf(payload: dict[str, Any], doc: dict[str, Any], source_url: Any) -> bytes:
    _fonts()
    styles = _styles()

    def p(text: Any, style: str = "body") -> Paragraph:
        return Paragraph(escape(clean(text)).replace("\n", "<br/>"), styles[style])

    def linked_refs(values: list[int]) -> Paragraph:
        return Paragraph("SOURCES  " + "  ".join(f'<a href="#source-{r}" color="#6855a2">[{r}]</a>' for r in values), styles["small"])

    reference_map = {(r["report_id"], r["page"]): r["reference"] for r in doc["references"]}

    def refs(sources: list[dict[str, Any]]) -> list[int]:
        return sorted({reference_map[(s["report_id"], s["page"])] for s in sources if (s["report_id"], s["page"]) in reference_map})

    def heading(title: str, key: str, label: str) -> list[Any]:
        title_p = p(title, "chapter")
        title_p.bookmark = key
        title_p.section_title = title
        return [p(label.upper(), "label"), title_p]

    def table(rows: list[list[Any]], widths: list[float]) -> Table:
        result = Table([[cell if isinstance(cell, Flowable) else p(cell, "cell_head" if n == 0 else "cell") for cell in row] for n, row in enumerate(rows)], colWidths=widths, repeatRows=1, hAlign="LEFT")
        result.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10), ("BACKGROUND", (0, 0), (-1, 0), PAPER),
            ("LINEBELOW", (0, 0), (-1, 0), .7, ACCENT), ("LINEBELOW", (0, 1), (-1, -1), .4, LINE),
        ]))
        return result

    def note(text: Any, style: str = "small") -> Table:
        box = Table([[p(text, style)]], colWidths=[CONTENT], hAlign="LEFT")
        box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PAPER), ("LINEBEFORE", (0, 0), (0, -1), 2, ACCENT),
            ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        return box

    class Report(SimpleDocTemplate):  # type: ignore[misc]  # ReportLab has no template stubs.
        def afterFlowable(self, flowable: Any) -> None:
            if getattr(flowable, "bookmark", None):
                key = flowable.bookmark
                self.canv.bookmarkPage(key)
                title = flowable.section_title
                self.canv.addOutlineEntry(clean(title), key, 0)
                self.notify("TOCEntry", (0, escape(clean(title)), self.page, key))

        def afterPage(self) -> None:
            if self.page == 1:
                return
            c = self.canv
            c.saveState()
            logo = asset("brand/vero-wordmark.png")
            if logo.exists():
                c.drawImage(str(logo), MARGIN - 2, HEIGHT - 48, width=57, height=23, preserveAspectRatio=True, mask="auto")
            else:
                c.setFont("VeroSans-Bold", 12)
                c.drawString(MARGIN, HEIGHT - 38, "Vero")
            c.setFillColor(MUTED)
            c.setFont("VeroSans", 7)
            c.drawRightString(WIDTH - MARGIN, HEIGHT - 38, clean(doc["package"]).upper())
            c.setStrokeColor(LINE)
            c.setLineWidth(.4)
            c.line(MARGIN, 43, WIDTH - MARGIN, 43)
            c.drawString(MARGIN, 27, "VERO / SUSTAINABILITY PEER INTELLIGENCE")
            c.drawRightString(WIDTH - MARGIN, 27, f"{self.page:02d}")
            c.restoreState()

    stream = BytesIO()
    report = Report(stream, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=70, bottomMargin=62,
                    title=doc["title"], author="Vero", subject="Sustainability peer intelligence", pageCompression=1)
    story: list[Any] = [Cover(doc, payload, styles), PageBreak(), p("EDITION GUIDE", "label"), p("In this report", "chapter")]
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("contents", parent=styles["body"], fontSize=9, leading=13, spaceBefore=7, spaceAfter=2, textColor=INK)]
    toc.dotsMinLevel = 0
    story += [toc, Spacer(1, 22), note("Click a section title to navigate. Numbered references lead to the source appendix; page links open the original company reports. Full data, calculations and the promise register are in the companion workbook.")]
    if not doc["authored"]:
        story.append(p("This edition presents the saved research findings; it has not been regenerated with the package-writing workflow.", "small"))

    companies = payload["definition"]["companies"]
    peer_colors = {c["id"]: PEER_COLORS[i % len(PEER_COLORS)] for i, c in enumerate(companies)}
    story += [PageBreak(), *heading("The peer group", "peers", "Research scope")]
    story.append(table([["Company", "Sector", "Country"]] + [[c["company_name"], c.get("sector") or "-", c.get("country") or "-"] for c in companies], [CONTENT * .49, CONTENT * .35, CONTENT * .16]))
    story += [Spacer(1, 24), p("How to read this edition", "head"), p("Figures retain their measurement years. Calculated metrics use the saved formulas and source-linked inputs. The charts show those results directly; a company missing from a calculation is not assigned a zero."),
              p("AI-assisted analysis of public company disclosures. Distinctions describe a criterion within this peer group, not an independent ESG rating.", "small")]
    if doc["incomplete"]:
        story.append(note("Working draft - analysis incomplete. Saved findings are included; unfinished stages have not been presented as completed analysis."))

    leads = [chapter["paragraphs"][0] for chapter in doc["chapters"] if chapter["paragraphs"]]
    if leads:
        story += [PageBreak(), *heading("The executive view", "executive", "What matters")]
        for i, item in enumerate(leads, 1):
            story += [CondPageBreak(155), p(f"{i:02d} / {doc['chapters'][i-1]['title']}", "label"), p(item["heading"], "head"),
                      p(item.get("takeaway") or item["text"], "takeaway"), linked_refs(item["references"]),
                      HRFlowable(width="100%", thickness=.5, color=LINE, spaceBefore=5, spaceAfter=20)]

    for chapter_index, chapter in enumerate(doc["chapters"], 1):
        story += [PageBreak(), *heading(chapter["title"], f"chapter-{chapter_index}", f"{chapter_index:02d} / Research & comparison")]
        for item in chapter["paragraphs"]:
            story += [CondPageBreak(155), p(item["heading"], "head")]
            # Split long prose only at sentence boundaries; keep every word.
            paragraphs, current = [], ""
            for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", item["text"]):
                if current and len(current) + len(sentence) > 850:
                    paragraphs.append(current)
                    current = ""
                current = (current + " " + sentence).strip()
            if current:
                paragraphs.append(current)
            story += [p(text) for text in paragraphs]
            story += [linked_refs(item["references"]), HRFlowable(width="100%", thickness=.4, color=LINE, spaceBefore=3, spaceAfter=17)]

    for i, metric in enumerate(doc["awards"], 1):
        story += [PageBreak(), *heading(metric["name"], f"metric-{i}", f"Calculated comparison / {i:02d}"), p(metric["criterion"])]
        values = [float(r["value"]) for r in metric["rows"]]
        domain = (min([0, *values]), max([0, *values]))
        story += [p(f"{metric['sample_size']} assessed companies / {metric['cohort_size']} selected. " + ("Contextual comparison." if metric.get("contextual") else ""), "small"), Spacer(1, 9)]
        for start in range(0, len(metric["rows"]), 6):
            story += [PeerChart(metric["rows"][start:start+6], domain, peer_colors, styles), Spacer(1, 14)]
        story += [Spacer(1, 16), p("The calculation", "head"), note((metric.get("formula") or metric["operation"]).replace("_", " "), "body")]
        if metric.get("interpretation"):
            story += [Spacer(1, 9), p(metric["interpretation"])]
        if metric["caveat"]:
            story += [Spacer(1, 8), p(metric["caveat"], "small")]
        winners = [r["company"] for r in metric["rows"] if r["company_id"] in metric["winner_ids"]]
        if winners:
            story.append(p("Leading result: " + ", ".join(winners), "small"))
        story.append(linked_refs(refs([o["source"] for r in metric["rows"] for o in r["inputs"]])))

    if doc["badges"]:
        story += [PageBreak(), *heading("What sets these peers apart", "distinctions", "Peer distinctions"), p("Recognition within this selected peer group, based on the stated criteria.", "small")]
        for badge in doc["badges"]:
            winner_names = ", ".join(r["company"] for r in badge["rows"] if r["company_id"] in badge["winner_ids"])
            logo = badge_asset(badge["name"])
            badge_image = Image(str(logo), width=88, height=88) if logo.exists() else Spacer(88, 88)
            title = Table([[badge_image, [p(badge["name"], "head"), p(winner_names or "Not awarded", "takeaway")]]], colWidths=[110, CONTENT-110])
            title.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
            block = [title, Spacer(1, 5), p(badge["why_it_matters"]),
                     p(f"{badge['sample_size']} assessed companies / {badge['basis']} criterion", "small")]
            if badge["basis"] == "qualitative":
                block.append(p("Rubric: " + "; ".join(f"{r['criterion']} (up to {r['max_points']} points)" for r in badge["rubric"]), "small"))
            block += [table([["Company", "Criterion result", "Sources"]] + [[r["company"], number(r["value"]), linked_refs(refs(r["sources"]))] for r in badge["rows"]], [CONTENT*.47, CONTENT*.23, CONTENT*.30]), Spacer(1, 24)]
            story.append(KeepTogether(block))

    scores = doc["disclosure_scores"]
    if scores and scores.get("criteria"):
        story += [PageBreak(), *heading("What peers disclose", "disclosures", "Disclosure scorecard"), p(scores["meaning"])]
        story.append(table([["Company", "Score / 100", "Common items"]] + [[r["company"], number(r["score"]) if r["score"] is not None else "Pending", f"{r['disclosed']} / {r['total']}"] for r in scores["rows"]], [CONTENT*.50, CONTENT*.25, CONTENT*.25]))
        for row in scores["rows"]:
            if row["deductions"] or row["pending"]:
                story += [Spacer(1, 13), p(row["company"], "head")]
            for deduction in row["deductions"]:
                story.append(p(f"-{deduction['points']:.1f} points: {deduction['criterion']}. {deduction['reason']}"))
            if row["pending"]:
                story.append(p("Checks to complete: " + "; ".join(row["pending"]), "small"))
    if doc["promises"]:
        story += [Spacer(1, 20), note(f"The companion workbook includes the full {len(doc['promises'])}-entry promise register: company commitments, deadlines, reported delivery and report-page links. Material comparisons are discussed in the research chapters.")]

    if doc["awards"]:
        story += [PageBreak(), *heading("Calculation inputs", "calculation-inputs", "Appendix / original figures"), p("Original reported values and years. The companion workbook contains the live calculation steps.", "small")]
        for metric in doc["awards"]:
            block = [p(metric["name"], "appendix_head")]
            for row in metric["rows"]:
                inputs = []
                for operand in row["inputs"]:
                    raw, unit = str(operand["raw_value"]), str(operand["raw_unit"])
                    displayed = raw if unit.lower() in {"%", "percent", "percentage"} and raw.rstrip().endswith("%") else f"{raw} {unit}"
                    inputs.append(f"{displayed} ({operand['year']})")
                labels = " ".join(f'<a href="#source-{r}" color="#6855a2">[{r}]</a>' for r in refs([o["source"] for o in row["inputs"]]))
                block.append(Paragraph(escape(clean(row["company"] + ": " + "; ".join(inputs))) + " " + labels, styles["appendix"]))
            story.append(KeepTogether(block))

    story += [PageBreak(), *heading("The evidence index", "sources", "Source references"), p("Open a page reference to inspect the original report. Page numbers refer to physical PDF pages.", "small")]
    # Group by company/report to avoid repeating long titles on every line.
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for source in doc["references"]:
        groups.setdefault((source["company"], source["report"]), []).append(source)
    for (company, title), entries in groups.items():
        cells = []
        for s in entries:
            url = source_url(s)
            label = escape(f"[{s['reference']:02d}]  PDF page {s['page']}")
            link = f'<a href="{escape(url, quote=True)}" color="#6855a2">{label}</a>' if url else label
            cells.append(Paragraph(f'<a name="source-{s["reference"]}"/>' + link, styles["appendix"]))
        rows = [cells[i:i+3] + [""] * (3-len(cells[i:i+3])) for i in range(0, len(cells), 3)]
        grid = Table(rows, colWidths=[CONTENT/3]*3, hAlign="LEFT")
        grid.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 8),
            ("TOPPADDING", (0,0), (-1,-1), 2), ("BOTTOMPADDING", (0,0), (-1,-1), 2)]))
        story.append(KeepTogether([p(company,"appendix_head"),p(title,"appendix"),grid,Spacer(1,4),HRFlowable(width="100%",thickness=.4,color=LINE,spaceAfter=8)]))
    report.multiBuild(story)
    return stream.getvalue()
