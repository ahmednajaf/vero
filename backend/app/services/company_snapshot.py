"""Portable, atomic import of a sourced JSON universe without re-scraping metadata."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.db.models import Company
from app.schemas.company import CompanyInput
from app.services.company_import import IMPORT_LOCK


def import_snapshot(path: Path, engine: Engine) -> dict[str, Any]:
    if path.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("Company snapshot exceeds 5 MiB")
    content = path.read_bytes()
    snapshot = json.loads(content)
    raw_rows = snapshot.get("companies") if isinstance(snapshot, dict) else None
    if not isinstance(raw_rows, list) or not 1 <= len(raw_rows) <= 10000:
        raise ValueError("Snapshot must contain 1–10000 company objects")
    rows = [CompanyInput.model_validate(row) for row in raw_rows]
    if len({row.id for row in rows}) != len(rows) or len(
        {(row.exchange, row.ticker) for row in rows}
    ) != len(rows):
        raise ValueError(
            "Duplicate company IDs or listings in snapshot; no rows imported"
        )
    provenance = snapshot.get("provenance", {})
    if not isinstance(provenance, dict) or any(
        not provenance.get(str(row.id)) for row in rows
    ):
        raise ValueError("Every company requires a provenance record")
    digest = hashlib.sha256(content).hexdigest()
    inserted = preserved = 0
    with Session(engine) as session, session.begin():
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": IMPORT_LOCK}
        )
        existing = {company.id: company for company in session.scalars(select(Company))}
        listings = {(c.exchange, c.ticker): c.id for c in existing.values()}
        for row in rows:
            owner = listings.get((row.exchange, row.ticker))
            if owner is not None and owner != row.id:
                raise ValueError(
                    f"Listing {row.exchange}:{row.ticker} belongs to a different stable company ID; import rolled back"
                )
        for position, row in enumerate(rows, 1):
            if row.id in existing:
                preserved += 1
                continue  # Existing user-managed metadata is never overwritten by a seed snapshot.
            session.add(
                Company(
                    **row.model_dump(),
                    source_file=str(path.resolve()),
                    source_row=position,
                    source_sha256=digest,
                    imported_at=datetime.now(UTC),
                )
            )
            inserted += 1
    return {
        "source_file": str(path.resolve()),
        "sha256": digest,
        "companies": len(rows),
        "inserted": inserted,
        "existing_preserved": preserved,
        "committed": True,
        "metrics_added": 0,
    }
