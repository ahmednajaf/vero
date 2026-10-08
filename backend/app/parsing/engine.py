"""Pure PDF -> structured pages. Content and geometry are retained, never scored.

Raw text is native content-stream extraction. A separate, explicitly heuristic
reading-order representation supports retrieval; chunks are exact slices of it.
"""

import base64
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Literal

import pdfplumber
import pymupdf

from app.parsing.contracts import (
    PARSER_VERSION,
    Line,
    ParseOptions,
    ParsedChunk,
    ParsedPage,
    ParsedTable,
    ParseResult,
    ParseWarning,
)


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def versions() -> dict[str, str]:
    return {
        "pipeline": PARSER_VERSION,
        "pymupdf": pymupdf.VersionBind,
        "pdfplumber": pdfplumber.__version__,
    }


class ParseFailure(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def reading_order(lines: list[Line], depth: int = 0) -> list[Line]:
    """Recursive whitespace cuts: columns before rows, retaining each source line.

    Spanning headings split a page into bands before the columns can be separated.
    This is a reproducible geometric heuristic, not semantic layout understanding.
    """
    if len(lines) <= 1:
        return lines
    if depth < 50:
        for axis, minimum in ((0, 12.0), (1, 3.0)):
            intervals = sorted((line.bbox[axis], line.bbox[axis + 2]) for line in lines)
            end = intervals[0][1]
            gaps: list[tuple[float, float]] = []
            for start, stop in intervals[1:]:
                if start - end >= minimum:
                    gaps.append((start - end, (start + end) / 2))
                end = max(end, stop)
            if gaps:
                _, cut = max(gaps)
                before = [line for line in lines if line.bbox[axis + 2] <= cut]
                after = [line for line in lines if line.bbox[axis] >= cut]
                if before and after and len(before) + len(after) == len(lines):
                    return reading_order(before, depth + 1) + reading_order(
                        after, depth + 1
                    )
    return sorted(
        lines,
        key=lambda line: (
            round(line.bbox[1], 1),
            line.bbox[0],
            line.block_number,
            line.line_number,
        ),
    )


def page_lines(page: Any) -> tuple[list[Line], float]:
    dictionary = page.get_text(
        "dict", sort=False, flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
    )
    lines: list[Line] = []
    fonts: Counter[float] = Counter()
    for block in dictionary["blocks"]:
        if block.get("type") != 0:
            continue
        for number, source in enumerate(block.get("lines", [])):
            spans = source.get("spans", [])
            text = "".join(span["text"] for span in spans).replace("\x00", "\ufffd")
            if not text:
                continue
            for span in spans:
                fonts[round(span["size"], 1)] += len(span["text"].strip())
            lines.append(
                Line(
                    block_number=block["number"],
                    line_number=number,
                    text=text,
                    bbox=source["bbox"],
                    font_size=max((s["size"] for s in spans), default=0),
                    bold=any(s["flags"] & 16 for s in spans),
                    direction=source.get("dir", (1, 0)),
                )
            )
    return lines, fonts.most_common(1)[0][0] if fonts else 0


def chunk_page(
    text: str,
    lines: list[Line],
    headings: list[dict[str, Any]],
    chunk_chars: int,
    outline_heading: str | None,
) -> list[ParsedChunk]:
    chunks: list[ParsedChunk] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + chunk_chars // 2, end)
            if boundary < 0:
                boundary = text.rfind(" ", start + chunk_chars // 2, end)
            if boundary >= 0:
                end = boundary + 1
        value = text[start:end]
        section = outline_heading
        preceding = [
            h
            for h in headings
            if h.get("start", 0) <= start and h["method"] == "typography"
        ]
        if preceding:
            section = str(preceding[-1]["text"])
        spans = [
            {
                "block_number": line.block_number,
                "line_number": line.line_number,
                "bbox": list(line.bbox),
                "page_text_start": max(start, line.start),
                "page_text_end": min(end, line.end),
                "line_text_start": max(0, start - line.start),
                "line_text_end": min(len(line.text), end - line.start),
            }
            for line in lines
            if line.start < end and line.end > start
        ]
        # Whitespace is preserved, not stripped; concatenating chunks reconstructs
        # the page's ordered_text exactly. No overlap or cross-page concatenation.
        chunks.append(
            ParsedChunk(
                text=value,
                text_sha256=text_hash(value),
                start=start,
                end=end,
                section_heading=section,
                source_spans=spans,
            )
        )
        start = end
    return chunks


def valid_table(cells: list[list[str | None]]) -> bool:
    return (
        len(cells) >= 2
        and max((len(row) for row in cells), default=0) >= 2
        and sum(bool(cell and cell.strip()) for row in cells for cell in row) >= 4
    )


def table_result(
    table: Any, method: str, version: str, metadata: dict[str, Any]
) -> ParsedTable | None:
    cells = table.extract()
    if not valid_table(cells):
        return None
    # NULL cells stay NULL; header relationships/merged cells are not inferred.
    cells = [
        [
            cell.replace("\x00", "\\u0000") if isinstance(cell, str) else None
            for cell in row
        ]
        for row in cells
    ]
    header = getattr(table, "header", None)
    return ParsedTable(
        bbox=list(table.bbox),
        cells=cells,
        cell_bboxes=[
            list(cell) if cell is not None else None
            for row in table.rows
            for cell in row.cells
        ],
        header_metadata=(
            {
                "names": list(header.names),
                "bbox": list(header.bbox),
                "external": bool(header.external),
                "inferred": True,
            }
            if header
            else {"inferred": False}
        ),
        extraction_metadata=metadata,
        extraction_method=method,
        parser_version=version,
        content_sha256=text_hash(canonical_json(cells)),
    )


def looks_tabular(page: Any) -> bool:
    numeric_rows: dict[int, list[float]] = defaultdict(list)
    for word in page.get_text("words"):
        if re.fullmatch(r"[()\d,.%−+\-]+", word[4]) and re.search(r"\d", word[4]):
            numeric_rows[round(word[1] / 4)].append(word[0])
    return (
        sum(
            len(values) >= 2 and max(values) - min(values) >= 30
            for values in numeric_rows.values()
        )
        >= 3
    )


def horizontal_rule_tables(page: Any) -> list[ParsedTable]:
    """Recover horizontal-rule tables without merging neighbouring page columns.

    Group actual horizontal strokes by matching x extents, split at large row
    gaps, and infer only column separators from whitespace between native lines.
    No semantic headers, numeric conversions, or model-based layout are inferred.
    """
    groups: dict[tuple[int, int], list[tuple[float, float, float]]] = defaultdict(list)
    strokes: dict[float, list[tuple[float, float]]] = defaultdict(list)
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                first, last = item[1], item[2]
                x0, x1 = sorted((first.x, last.x))
                if abs(first.y - last.y) < 1 and x1 - x0 > 3:
                    strokes[round((first.y + last.y) / 2, 1)].append((x0, x1))
            elif item[0] == "re" and item[1].height < 1:
                rect = item[1]
                strokes[round((rect.y0 + rect.y1) / 2, 1)].append((rect.x0, rect.x1))
    # PDF producers often emit each row rule as adjacent cell-length strokes.
    # Join only collinear touching strokes, never the gutter between page columns.
    for y, pieces in strokes.items():
        merged: list[list[float]] = []
        for x0, x1 in sorted(pieces):
            if merged and x0 - merged[-1][1] <= 2:
                merged[-1][1] = max(merged[-1][1], x1)
            else:
                merged.append([x0, x1])
        for x0, x1 in merged:
            if x1 - x0 >= page.cropbox.width * 0.15:
                groups[(round(x0 / 5), round(x1 / 5))].append((x0, x1, y))
    lines, _ = page_lines(page)
    tables: list[ParsedTable] = []
    for rules in groups.values():
        ys = sorted(set(round(rule[2], 2) for rule in rules))
        if len(ys) < 3:
            continue
        gaps = [b - a for a, b in zip(ys, ys[1:]) if b - a > 2]
        if not gaps:
            continue
        step = median(gaps)
        sections: list[list[float]] = [[ys[0]]]
        for y in ys[1:]:
            if y - sections[-1][-1] > max(20, step * 1.8):
                sections.append([])
            sections[-1].append(y)
        x0, x1 = min(rule[0] for rule in rules), max(rule[1] for rule in rules)
        for section in sections:
            if len(section) < 3:
                continue
            top = max(0, section[0] - step * 0.9)
            bottom = section[-1] + 1
            local = [
                line
                for line in lines
                if x0 - 2 <= line.bbox[0]
                and line.bbox[2] <= x1 + 2
                and top <= (line.bbox[1] + line.bbox[3]) / 2 <= bottom
            ]
            intervals = sorted(
                (line.bbox[0], line.bbox[2])
                for line in local
                if line.bbox[2] - line.bbox[0] < (x1 - x0) * 0.7
            )
            if not intervals:
                continue
            end = intervals[0][1]
            separators: list[float] = []
            for start, stop in intervals[1:]:
                if start - end >= 5:
                    separators.append((start + end) / 2)
                end = max(end, stop)
            if not separators or len(separators) > 15:
                continue
            vertical = [x0, *separators, x1]
            horizontal = [top, *section]
            finder = page.find_tables(
                clip=(x0 - 1, top, x1 + 1, bottom),
                vertical_lines=vertical,
                horizontal_lines=horizontal,
                use_layout=False,
            )
            for table in finder.tables:
                result = table_result(
                    table,
                    "pymupdf.horizontal_rules_whitespace",
                    pymupdf.VersionBind,
                    {
                        "coordinate_system": "unrotated PyMuPDF page points; top-left origin",
                        "observed_horizontal_rules": section,
                        "inferred_vertical_boundaries": vertical,
                        "inferred_header_top": top,
                        "validation_state": "needs_review",
                        "use_layout": False,
                    },
                )
                if result:
                    tables.append(result)
    return tables


def table_aware_order(lines: list[Line], tables: list[ParsedTable]) -> list[Line]:
    """Keep table text row-wise within a geometric region; page columns stay separate."""
    groups: dict[int, list[Line]] = {}
    remaining = list(lines)
    proxies: list[Line] = []
    for index, table in enumerate(tables):
        if not table.extraction_method.startswith("pymupdf."):
            continue
        x0, y0, x1, y1 = table.bbox
        local = [
            line
            for line in remaining
            if x0 - 2 <= (line.bbox[0] + line.bbox[2]) / 2 <= x1 + 2
            and y0 - 2 <= (line.bbox[1] + line.bbox[3]) / 2 <= y1 + 2
        ]
        if not local:
            continue
        identities = {id(line) for line in local}
        remaining = [line for line in remaining if id(line) not in identities]
        groups[index] = sorted(
            local, key=lambda line: (round(line.bbox[3] / 3), line.bbox[0])
        )
        proxies.append(
            Line(
                block_number=-1,
                line_number=index,
                text="",
                bbox=(x0, y0, x1, y1),
                font_size=0,
                bold=False,
                direction=(1, 0),
            )
        )
    result: list[Line] = []
    for line in reading_order(remaining + proxies):
        result.extend(groups[line.line_number] if line.block_number == -1 else [line])
    return result


def extract_tables(
    page: Any,
    path: Path,
    options: ParseOptions,
    plumber_holder: list[Any],
    warnings: list[ParseWarning],
) -> list[ParsedTable]:
    tables: list[ParsedTable] = []
    primary_failed = False
    try:
        finder = page.find_tables(strategy="lines_strict", use_layout=False)
        for table in finder.tables:
            result = table_result(
                table,
                "pymupdf.lines_strict",
                pymupdf.VersionBind,
                {
                    "coordinate_system": "unrotated PyMuPDF page points; top-left origin",
                    "use_layout": False,
                    "validation_state": "needs_review",
                },
            )
            if result:
                tables.append(result)
    except Exception as exc:
        primary_failed = True
        warnings.append(
            ParseWarning(
                code="table_primary_failed",
                message=f"Geometric table detection failed: {type(exc).__name__}",
                page_number=page.number + 1,
            )
        )
    if not tables:
        try:
            tables = horizontal_rule_tables(page)
        except Exception as exc:
            warnings.append(
                ParseWarning(
                    code="horizontal_table_failed",
                    message=f"Horizontal-rule table extraction failed: {type(exc).__name__}",
                    page_number=page.number + 1,
                )
            )
    if (
        not tables
        and options.pdfplumber_fallback
        and (primary_failed or looks_tabular(page))
    ):
        try:
            if not plumber_holder:
                plumber_holder.append(pdfplumber.open(path))
            fallback = plumber_holder[0].pages[page.number]
            try:
                settings = {
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                    "min_words_vertical": 3,
                    "min_words_horizontal": 2,
                }
                for table in fallback.find_tables(table_settings=settings):
                    result = table_result(
                        table,
                        "pdfplumber.text_alignment",
                        pdfplumber.__version__,
                        {
                            "coordinate_system": "pdfplumber page points; top-left origin",
                            "page_bbox": list(fallback.bbox),
                            "page_rotation": fallback.rotation,
                            "settings": settings,
                            "validation_state": "needs_review",
                            "note": "Heuristic text-aligned table; may include prose or charts",
                        },
                    )
                    if result:
                        tables.append(result)
                if tables:
                    warnings.append(
                        ParseWarning(
                            code="table_fallback",
                            message="Text-aligned pdfplumber table candidates require visual review",
                            page_number=page.number + 1,
                        )
                    )
            finally:
                fallback.close()
        except Exception as exc:
            warnings.append(
                ParseWarning(
                    code="table_fallback_failed",
                    message=f"pdfplumber fallback failed: {type(exc).__name__}",
                    page_number=page.number + 1,
                )
            )
    if len(tables) > options.max_tables_per_page:
        warnings.append(
            ParseWarning(
                code="table_limit",
                message=f"Only first {options.max_tables_per_page} table candidates retained",
                page_number=page.number + 1,
            )
        )
    return tables[: options.max_tables_per_page]


def parse_pdf(path: Path, options: ParseOptions | None = None) -> ParseResult:
    options = options or ParseOptions()
    pages: list[ParsedPage] = []
    warnings: list[ParseWarning] = []
    plumber_holder: list[Any] = []
    try:
        with pymupdf.open(path) as document:  # type: ignore[no-untyped-call]
            if not document.is_pdf:
                raise ParseFailure("not_pdf", "Input is not a PDF")
            if document.needs_pass:
                raise ParseFailure(
                    "encrypted",
                    "Password-protected PDF; no password guessing or bypass attempted",
                )
            if not 0 < document.page_count <= options.max_pages:
                raise ParseFailure(
                    "page_limit",
                    f"Page count {document.page_count} outside configured limit {options.max_pages}",
                )
            if document.is_repaired:
                warnings.append(
                    ParseWarning(
                        code="pdf_repaired",
                        message="PyMuPDF repaired the PDF structure in memory; source bytes unchanged",
                    )
                )
            try:
                outline = document.get_toc(simple=True)
            except Exception:
                outline = []
                warnings.append(
                    ParseWarning(
                        code="outline_failed", message="PDF outline could not be read"
                    )
                )
            total_chars = 0
            for page in document:
                number = page.number + 1
                page_warnings: list[ParseWarning] = []
                layout: dict[str, Any] = {
                    "coordinate_system": "unrotated PyMuPDF page points; top-left origin",
                    "reading_order": "recursive-whitespace-cuts-v2; heuristic LTR; geometric tables row-wise",
                    "cropbox": list(page.cropbox),
                    "mediabox": list(page.mediabox),
                }
                headings: list[dict[str, Any]] = []
                raw = ordered = ""
                tables: list[ParsedTable] = []
                chunks: list[ParsedChunk] = []
                page_status: Literal["parsed", "needs_ocr", "failed"] = "parsed"
                try:
                    raw = page.get_text(
                        "text", sort=False, flags=pymupdf.TEXTFLAGS_TEXT
                    )
                    if "\x00" in raw:
                        layout["original_raw_utf8_base64"] = base64.b64encode(
                            raw.encode("utf-8")
                        ).decode("ascii")
                        raw = raw.replace("\x00", "\ufffd")
                        page_warnings.append(
                            ParseWarning(
                                code="nul_text",
                                message="NUL characters replaced for PostgreSQL; original extraction preserved losslessly as base64",
                                page_number=number,
                            )
                        )
                    if len(raw) > options.max_page_chars:
                        raise ParseFailure(
                            "page_text_limit",
                            f"Page {number} exceeds configured text-size limit; not silently truncated",
                        )
                    total_chars += len(raw)
                    if total_chars > options.max_document_chars:
                        raise ParseFailure(
                            "document_text_limit",
                            "Document text exceeds configured size limit; not silently truncated",
                        )
                    image_count = len(page.get_images())
                    if raw.strip() and not (image_count and len(raw.strip()) < 40):
                        tables = extract_tables(
                            page, path, options, plumber_holder, page_warnings
                        )
                    lines, body_size = page_lines(page)
                    lines = table_aware_order(lines, tables)
                    pieces: list[str] = []
                    offset = 0
                    for line in lines:
                        line.start, line.end = offset, offset + len(line.text)
                        pieces.append(line.text + "\n")
                        offset = line.end + 1
                        if (
                            line.text.strip()
                            and len(line.text) <= 180
                            and len(line.text.split()) <= 20
                            and not line.text.strip().isdigit()
                            and (
                                line.font_size >= body_size * 1.2
                                or (
                                    line.bold
                                    and line.font_size >= body_size
                                    and len(line.text) < 90
                                )
                            )
                        ):
                            headings.append(
                                {
                                    "text": line.text,
                                    "bbox": list(line.bbox),
                                    "font_size": line.font_size,
                                    "start": line.start,
                                    "method": "typography",
                                    "validated": False,
                                }
                            )
                    ordered = "".join(pieces)
                    # On a layout extraction mismatch, retain the complete native
                    # text as the retrieval representation instead of losing text.
                    if raw.strip() and not ordered.strip():
                        ordered = raw
                        page_warnings.append(
                            ParseWarning(
                                code="layout_unavailable",
                                message="Native text retained without line coordinates",
                                page_number=number,
                            )
                        )
                    layout["lines"] = [line.model_dump(mode="json") for line in lines]
                    layout["body_font_size"] = body_size
                    if any(
                        abs(line.direction[1]) > 0.1 or line.direction[0] < 0.9
                        for line in lines
                    ):
                        page_warnings.append(
                            ParseWarning(
                                code="rotated_text",
                                message="Non-horizontal text detected; heuristic reading order needs review",
                                page_number=number,
                            )
                        )
                    active_outline = [
                        entry for entry in outline if 0 < entry[2] <= number
                    ]
                    section = str(active_outline[-1][1]) if active_outline else None
                    for level, title, physical_page in outline:
                        if physical_page == number:
                            headings.append(
                                {
                                    "text": title,
                                    "level": level,
                                    "method": "pdf_outline",
                                    "start": 0,
                                    "validated": False,
                                }
                            )
                    layout["image_count"] = image_count
                    if not raw.strip():
                        page_status = "needs_ocr"
                        page_warnings.append(
                            ParseWarning(
                                code="no_text",
                                message="No native text; flagged needs_ocr without running OCR (may be blank or image-only)",
                                page_number=number,
                            )
                        )
                    elif image_count and len(raw.strip()) < 40:
                        page_status = "needs_ocr"
                        page_warnings.append(
                            ParseWarning(
                                code="sparse_image_page",
                                message="Sparse native text with images; possible scan with a text footer. No OCR run",
                                page_number=number,
                            )
                        )
                    if raw.strip():
                        chunks = chunk_page(
                            ordered, lines, headings, options.chunk_chars, section
                        )
                except ParseFailure:
                    raise
                except Exception as exc:
                    page_status = "failed"
                    page_warnings.append(
                        ParseWarning(
                            code="page_failed",
                            message=f"Page extraction failed: {type(exc).__name__}: {str(exc)[:200]}",
                            page_number=number,
                        )
                    )
                label = page.get_label() or None
                pages.append(
                    ParsedPage(
                        page_number=number,
                        printed_page_label=label,
                        width_points=page.cropbox.width,
                        height_points=page.cropbox.height,
                        rotation=page.rotation,
                        raw_text=raw,
                        raw_text_sha256=text_hash(raw),
                        ordered_text=ordered,
                        ordered_text_sha256=text_hash(ordered),
                        headings=headings,
                        layout=layout,
                        status=page_status,
                        warnings=page_warnings,
                        tables=tables,
                        chunks=chunks,
                    )
                )
                warnings.extend(page_warnings)
    except Exception as exc:
        code = exc.code if isinstance(exc, ParseFailure) else "invalid_pdf"
        return ParseResult(
            status="failed",
            pages=[],
            warnings=warnings,
            quality={
                "pages_total": None,
                "pages_with_text": 0,
                "text_characters": 0,
                "table_count": 0,
                "chunk_count": 0,
                "ocr_performed": False,
            },
            versions=versions(),
            error_code=code,
            error_summary=str(exc)[:500],
        )
    finally:
        for plumber in plumber_holder:
            plumber.close()
    failed = sum(page.status == "failed" for page in pages)
    needs_ocr = sum(page.status == "needs_ocr" for page in pages)
    status: Literal["parsed", "needs_ocr", "needs_review", "failed"] = (
        "failed"
        if failed == len(pages)
        else (
            "needs_ocr"
            if needs_ocr
            else (
                "needs_review"
                if failed or any(w.severity == "review" for w in warnings)
                else "parsed"
            )
        )
    )
    return ParseResult(
        status=status,
        pages=pages,
        warnings=warnings,
        versions=versions(),
        quality={
            "pages_total": len(pages),
            "pages_with_text": sum(bool(page.raw_text.strip()) for page in pages),
            "text_characters": sum(len(page.raw_text) for page in pages),
            "table_count": sum(len(page.tables) for page in pages),
            "chunk_count": sum(len(page.chunks) for page in pages),
            "pages_needing_ocr": needs_ocr,
            "pages_failed": failed,
            "parse_warnings": len(warnings),
            "ocr_performed": False,
        },
    )
