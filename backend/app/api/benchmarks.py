from math import ceil
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy.orm import Session

from app.benchmarking.contracts import PeerGroup, Scope2Method
from app.benchmarking.service import calculate, sector_summary
from app.benchmarking.engine import canonical
from app.benchmarking.explanations import csv_export, explain
from app.db.models import Company
from app.db.session import get_session

router = APIRouter(tags=["benchmarks"])
Database = Annotated[Session, Depends(get_session)]


def benchmark_parameters(
    year: Annotated[int, Query(ge=2000, le=2100)],
    peer_group: PeerGroup = "sector",
    min_peers: Annotated[int, Query(ge=5, le=500)] = 5,
    scope2_method: Scope2Method = "location_based",
) -> dict[str, Any]:
    return dict(
        year=year,
        peer_group=peer_group,
        min_peers=min_peers,
        scope2_method=scope2_method,
    )


Parameters = Annotated[dict[str, Any], Depends(benchmark_parameters)]


def read_snapshot(session: Session, parameters: dict[str, Any]) -> dict[str, Any]:
    # All bulk reads observe the same database snapshot. GET never persists anything.
    session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    return calculate(session, **parameters)


@router.get("/api/benchmarks")
def benchmarks(
    session: Database,
    parameters: Parameters,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    sector: Annotated[str | None, Query(max_length=80)] = None,
    country: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
) -> dict[str, Any]:
    payload = read_snapshot(session, parameters)
    items = [
        c
        for c in payload["items"]
        if (not sector or c["sector"].casefold() == sector.strip().casefold())
        and (not country or c["country"].casefold() == country.casefold())
    ]
    return {
        **payload,
        "total": len(items),
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(len(items) / page_size),
        "items": items[(page - 1) * page_size : page * page_size],
        "filter_notice": "Display filters/pagination do not change the underlying peer universe.",
    }


@router.get("/api/companies/{id}/benchmark")
def company_benchmark(
    company_id: Annotated[UUID, Path(alias="id")],
    session: Database,
    parameters: Parameters,
) -> dict[str, Any]:
    payload = read_snapshot(session, parameters)
    item = next(
        (c for c in payload["items"] if c["company_id"] == str(company_id)), None
    )
    if item is None:
        existing = session.get(Company, company_id)
        raise HTTPException(
            409 if existing else 404,
            (
                "Company is inactive and excluded from peer universe"
                if existing
                else "Company not found"
            ),
        )
    return {k: v for k, v in payload.items() if k not in {"items", "total"}} | {
        "company": item
    }


@router.get("/api/sectors/{sector}/summary")
def summary(
    sector: str,
    session: Database,
    year: Annotated[int, Query(ge=2000, le=2100)],
    min_peers: Annotated[int, Query(ge=5, le=500)] = 5,
    scope2_method: Scope2Method = "location_based",
) -> dict[str, Any]:
    payload = read_snapshot(
        session,
        dict(
            year=year,
            peer_group="sector",
            min_peers=min_peers,
            scope2_method=scope2_method,
        ),
    )
    result = sector_summary(payload, sector.strip())
    if not result["companies_total"]:
        raise HTTPException(404, "Sector has no active companies")
    return result


def explanation_data(
    session: Session,
    parameters: dict[str, Any],
    company_id: UUID,
    expected_input_sha256: str | None,
) -> dict[str, Any]:
    payload = read_snapshot(session, parameters)
    if expected_input_sha256 and expected_input_sha256 != payload["input_sha256"]:
        raise HTTPException(
            409,
            "Benchmark evidence changed. Refresh the company page before exporting or explaining.",
        )
    try:
        return explain(payload, str(company_id))
    except KeyError:
        existing = session.get(Company, company_id)
        raise HTTPException(
            409 if existing else 404,
            "Company is inactive" if existing else "Company not found",
        ) from None


@router.get("/api/companies/{id}/peer-explanation")
def peer_explanation(
    company_id: Annotated[UUID, Path(alias="id")],
    session: Database,
    parameters: Parameters,
    expected_input_sha256: Annotated[
        str | None, Query(pattern="^[a-f0-9]{64}$")
    ] = None,
) -> dict[str, Any]:
    return explanation_data(session, parameters, company_id, expected_input_sha256)


@router.get("/api/companies/{id}/peer-explanation/export")
def export_peer_explanation(
    company_id: Annotated[UUID, Path(alias="id")],
    session: Database,
    parameters: Parameters,
    format: Literal["json", "csv"] = "json",
    expected_input_sha256: Annotated[
        str | None, Query(pattern="^[a-f0-9]{64}$")
    ] = None,
) -> Response:
    data = explanation_data(session, parameters, company_id, expected_input_sha256)
    return Response(
        content=csv_export(data) if format == "csv" else canonical(data),
        media_type="text/csv" if format == "csv" else "application/json",
        headers={
            "Content-Disposition": f'attachment; filename="peer-gap-{company_id}-{data["year"]}.{format}"',
            "Cache-Control": "no-store",
            "X-Explanation-SHA256": data["explanation_sha256"],
        },
    )
