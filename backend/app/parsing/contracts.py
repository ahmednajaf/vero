from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PARSER_VERSION = "page-provenance-v2"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ParseOptions(Contract):
    chunk_chars: int = Field(default=2400, ge=200, le=10000)
    max_pages: int = Field(default=1500, ge=1, le=5000)
    max_page_chars: int = Field(default=300000, ge=1000, le=1000000)
    max_document_chars: int = Field(default=25000000, ge=1000, le=100000000)
    max_tables_per_page: int = Field(default=50, ge=1, le=200)
    pdfplumber_fallback: bool = True


class ParseWarning(Contract):
    code: str
    message: str
    page_number: int | None = None
    severity: Literal["info", "review"] = "review"


class Line(Contract):
    block_number: int
    line_number: int
    text: str
    bbox: tuple[float, float, float, float]
    font_size: float
    bold: bool
    direction: tuple[float, float]
    start: int = 0
    end: int = 0


class ParsedTable(Contract):
    bbox: list[float]
    cells: list[list[str | None]]
    cell_bboxes: list[list[float] | None]
    header_metadata: dict[str, Any]
    extraction_metadata: dict[str, Any]
    extraction_method: str
    parser_version: str
    content_sha256: str


class ParsedChunk(Contract):
    text: str
    text_sha256: str
    start: int
    end: int
    section_heading: str | None
    source_spans: list[dict[str, Any]]


class ParsedPage(Contract):
    page_number: int
    printed_page_label: str | None
    width_points: float
    height_points: float
    rotation: int
    raw_text: str
    raw_text_sha256: str
    ordered_text: str
    ordered_text_sha256: str
    headings: list[dict[str, Any]]
    layout: dict[str, Any]
    status: Literal["parsed", "needs_ocr", "failed"]
    warnings: list[ParseWarning]
    tables: list[ParsedTable]
    chunks: list[ParsedChunk]


class ParseResult(Contract):
    status: Literal["parsed", "needs_ocr", "needs_review", "failed"]
    pages: list[ParsedPage]
    warnings: list[ParseWarning]
    quality: dict[str, Any]
    versions: dict[str, str]
    error_code: str | None = None
    error_summary: str | None = None
