from math import ceil
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Company
from app.db.session import get_session
from app.schemas.company import CompanyPage, CompanyResponse

router = APIRouter(prefix="/api/companies", tags=["companies"])
Database = Annotated[Session, Depends(get_session)]


@router.get("", response_model=CompanyPage)
def list_companies(
    session: Database,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    sector: Annotated[str | None, Query(max_length=80)] = None,
    country: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    active: bool | None = None,
) -> CompanyPage:
    conditions = []
    if sector is not None:
        conditions.append(func.lower(Company.sector) == sector.strip().lower())
    if country is not None:
        conditions.append(Company.country == country.upper())
    if active is not None:
        conditions.append(Company.active == active)
    if search is not None and search.strip():
        # Autoescape makes %, _ and / literal user text, never query wildcards.
        term = search.strip()
        conditions.append(
            or_(
                Company.company_name.icontains(term, autoescape=True),
                Company.ticker.icontains(term, autoescape=True),
                Company.official_domain.icontains(term, autoescape=True),
            )
        )
    total = (
        session.scalar(select(func.count()).select_from(Company).where(*conditions))
        or 0
    )
    companies = session.scalars(
        select(Company)
        .where(*conditions)
        .order_by(func.lower(Company.company_name), Company.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return CompanyPage(
        items=[CompanyResponse.model_validate(company) for company in companies],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size),
    )


@router.get("/{id}", response_model=CompanyResponse)
def get_company(
    company_id: Annotated[UUID, Path(alias="id")], session: Database
) -> CompanyResponse:
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyResponse.model_validate(company)
