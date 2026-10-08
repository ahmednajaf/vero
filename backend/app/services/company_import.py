"""Atomic CSV import, keyed by explicit immutable company UUIDs."""

import csv
import hashlib
import io
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Company
from app.schemas.company import CompanyInput

COLUMNS = tuple(CompanyInput.model_fields)
REQUIRED_COLUMNS = {
    name
    for name, field_info in CompanyInput.model_fields.items()
    if field_info.is_required()
}
MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10000
IMPORT_LOCK = 736204891


@dataclass
class RowError:
    source_row: int
    field: str
    code: str
    message: str
    raw_values: dict[str, str | None]
    raw_cells: list[str]


@dataclass
class ImportSummary:
    source_file: str
    source_sha256: str = ""
    total_rows: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected_rows: int = 0
    committed: bool = False
    errors: list[RowError] = field(default_factory=list)
    completed_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def finish(self) -> "ImportSummary":
        self.rejected_rows = len(
            {error.source_row for error in self.errors if error.source_row >= 2}
        )
        self.completed_at = datetime.now(UTC).isoformat()
        return self


@dataclass
class SourceRow:
    number: int
    raw: dict[str, str | None]
    cells: list[str]
    company: CompanyInput


def read_companies(path: Path) -> tuple[ImportSummary, list[SourceRow]]:
    summary = ImportSummary(source_file=str(path.resolve()))
    rows: list[SourceRow] = []
    if path.stat().st_size > MAX_BYTES:
        summary.errors.append(
            RowError(0, "file", "too_large", "CSV exceeds 5 MiB", {}, [])
        )
        return summary, rows
    content = path.read_bytes()
    summary.source_sha256 = hashlib.sha256(content).hexdigest()
    try:
        reader = csv.reader(
            io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True
        )
        headers = next(reader, [])
        if (
            len(headers) != len(set(headers))
            or not REQUIRED_COLUMNS.issubset(headers)
            or not set(headers).issubset(COLUMNS)
        ):
            missing = sorted(REQUIRED_COLUMNS - set(headers))
            unknown = sorted(set(headers) - set(COLUMNS))
            summary.errors.append(
                RowError(
                    1,
                    "header",
                    "invalid_header",
                    f"Headers must be unique and recognised. Missing: {missing}. Unknown: {unknown}.",
                    {},
                    headers,
                )
            )
            return summary, rows
        while True:
            number = reader.line_num + 1
            cells = next(reader, None)
            if cells is None:
                break
            if (
                not cells
            ):  # Ignore wholly empty physical lines, not rows of empty cells.
                continue
            summary.total_rows += 1
            raw = {
                name: cells[index] if index < len(cells) else None
                for index, name in enumerate(headers)
            }
            if summary.total_rows > MAX_ROWS:
                summary.errors.append(
                    RowError(
                        number,
                        "file",
                        "too_many_rows",
                        "CSV exceeds 10,000 rows",
                        raw,
                        cells,
                    )
                )
                break
            if len(cells) != len(headers):
                summary.errors.append(
                    RowError(
                        number,
                        "row",
                        "column_count",
                        "Row width differs from header",
                        raw,
                        cells,
                    )
                )
                continue
            values = {
                name: (value.strip() if value is not None and value.strip() else None)
                for name, value in raw.items()
            }
            try:
                company = CompanyInput.model_validate(values)
            except ValidationError as exc:
                for error in exc.errors(include_url=False, include_input=False):
                    summary.errors.append(
                        RowError(
                            number,
                            ".".join(map(str, error["loc"])) or "row",
                            str(error["type"]),
                            str(error["msg"]),
                            raw,
                            cells,
                        )
                    )
            else:
                rows.append(SourceRow(number, raw, cells, company))
    except (UnicodeDecodeError, csv.Error) as exc:
        summary.errors.append(RowError(0, "file", "invalid_csv", str(exc), {}, []))
        return summary, rows

    for key_name, key in (
        ("id", lambda row: row.company.id),
        ("exchange/ticker", lambda row: (row.company.exchange, row.company.ticker)),
    ):
        grouped: dict[object, list[SourceRow]] = {}
        for row in rows:
            grouped.setdefault(key(row), []).append(row)
        for duplicates in grouped.values():
            if len(duplicates) > 1:
                numbers = [row.number for row in duplicates]
                for row in duplicates:
                    summary.errors.append(
                        RowError(
                            row.number,
                            key_name,
                            "duplicate_in_file",
                            f"Duplicate {key_name} in source rows {numbers}",
                            row.raw,
                            row.cells,
                        )
                    )
    if not summary.total_rows and not summary.errors:
        summary.errors.append(
            RowError(1, "file", "empty_file", "CSV contains no company rows", {}, [])
        )
    return summary, rows


def import_companies(path: Path, engine: Engine) -> ImportSummary:
    summary, rows = read_companies(path)
    if summary.errors:
        return summary.finish()

    current: SourceRow | None = None
    try:
        with Session(engine) as session, session.begin():
            # Serialise imports, including the read/check/write sequence. Database unique
            # constraints remain authoritative for writes from other applications.
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": IMPORT_LOCK}
            )
            companies = list(session.scalars(select(Company)))
            by_id: dict[UUID, Company] = {company.id: company for company in companies}
            by_listing = {
                (company.exchange.lower(), company.ticker.lower()): company.id
                for company in companies
            }
            for row in rows:
                key = (row.company.exchange.lower(), row.company.ticker.lower())
                owner = by_listing.get(key)
                if owner is not None and owner != row.company.id:
                    summary.errors.append(
                        RowError(
                            row.number,
                            "exchange/ticker",
                            "existing_listing",
                            f"Listing belongs to company id {owner}; use its stable id to update",
                            row.raw,
                            row.cells,
                        )
                    )
            if summary.errors:
                return summary.finish()
            for current in rows:
                payload = current.company.model_dump()
                existing = by_id.get(current.company.id)
                if existing is not None and all(
                    getattr(existing, name) == value for name, value in payload.items()
                ):
                    summary.unchanged += 1
                    continue
                if existing is None:
                    existing = Company(**payload)
                    session.add(existing)
                    summary.inserted += 1
                else:
                    for name, value in payload.items():
                        setattr(existing, name, value)
                    summary.updated += 1
                existing.source_file = summary.source_file
                existing.source_row = current.number
                existing.source_sha256 = summary.source_sha256
                existing.imported_at = datetime.now(UTC)
                session.flush()  # Attribute constraint errors to their original source row.
        summary.committed = True
    except SQLAlchemyError:
        summary.inserted = summary.updated = summary.unchanged = 0
        summary.errors.append(
            RowError(
                current.number if current else 0,
                "database",
                "database_error",
                "Import rolled back. Check database availability, migrations and constraints. No rows were committed.",
                current.raw if current else {},
                current.cells if current else [],
            )
        )
    return summary.finish()
