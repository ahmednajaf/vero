"""Read-only local administration. No endpoint initiates network acquisition."""

from math import ceil
from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.companies import Database
from app.discovery.service import status_snapshot

router = APIRouter(prefix="/api/admin", tags=["report discovery"])


@router.get("/report-status")
def report_status(
    session: Database,
    year: Annotated[int, Query(ge=2000, le=2100)] = 2025,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    result = status_snapshot(session, year, page=page, page_size=page_size)
    total = result["total"]
    return {
        **result,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size),
    }
