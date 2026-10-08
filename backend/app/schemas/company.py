import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit
from uuid import UUID

import pycountry
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Sector = Literal[
    "Financial Services", "Technology", "Energy", "Consumer / Retail", "Industrials", "Pharmaceuticals"
]
Money = Annotated[
    Decimal, Field(ge=0, max_digits=30, decimal_places=6, allow_inf_nan=False)
]


class CompanyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: UUID
    company_name: str = Field(min_length=1, max_length=240)
    ticker: str = Field(min_length=1, max_length=32)
    country: str
    region: str = Field(min_length=1, max_length=80)
    exchange: str = Field(min_length=1, max_length=32)
    index: str | None = Field(default=None, max_length=160)
    sector: Sector
    industry: str = Field(min_length=1, max_length=160)
    official_domain: str = Field(min_length=3, max_length=253)
    investor_relations_url: str | None = Field(default=None, max_length=2048)
    sustainability_url: str | None = Field(default=None, max_length=2048)
    reporting_currency: str | None = None
    revenue: Money | None = None
    revenue_year: int | None = Field(default=None, ge=1900, le=2100)
    reporting_year: int = Field(ge=2000, le=2100)
    market_cap: Money | None = None
    active: bool

    @field_validator("id")
    @classmethod
    def nonzero_uuid(cls, value: UUID) -> UUID:
        if value.int == 0:
            raise ValueError("Use a non-zero stable UUID")
        return value

    @field_validator(
        "ticker", "exchange", "country", "reporting_currency", mode="before"
    )
    @classmethod
    def upper_codes(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("country")
    @classmethod
    def country_code(cls, value: str) -> str:
        if len(value) != 2 or pycountry.countries.get(alpha_2=value) is None:
            raise ValueError(
                "country must be an ISO 3166-1 alpha-2 code, e.g. US or GB"
            )
        return value

    @field_validator("reporting_currency")
    @classmethod
    def currency_code(cls, value: str | None) -> str | None:
        if value is not None and (
            len(value) != 3 or pycountry.currencies.get(alpha_3=value) is None
        ):
            raise ValueError("reporting_currency must be an ISO 4217 code")
        return value

    @field_validator("official_domain")
    @classmethod
    def domain(cls, value: str) -> str:
        value = value.lower().rstrip(".")
        if not re.fullmatch(
            r"(?=.{3,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
            value,
        ):
            raise ValueError(
                "official_domain must be a hostname only, without scheme, port or path"
            )
        return value

    @field_validator("investor_relations_url", "sustainability_url")
    @classmethod
    def http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value)
        if (
            parts.scheme not in {"https", "http"}
            or not parts.hostname
            or parts.username
            or parts.password
            or any(char.isspace() for char in value)
        ):
            raise ValueError(
                "URL must be HTTP(S) without embedded credentials or whitespace"
            )
        _ = (
            parts.port
        )  # Reject invalid port syntax. URLs are stored, never fetched here.
        return value

    @field_validator("active", mode="before")
    @classmethod
    def active_flag(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
            return value.strip().lower() == "true"
        raise ValueError("active must be true or false")

    @model_validator(mode="after")
    def financial_context(self) -> Self:
        if self.revenue is not None and (
            self.revenue_year is None or self.reporting_currency is None
        ):
            raise ValueError(
                "revenue requires revenue_year and reporting_currency; use blank for unknown"
            )
        if self.market_cap is not None and self.reporting_currency is None:
            raise ValueError("market_cap requires reporting_currency")
        return self


class CompanyResponse(CompanyInput):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    created_at: datetime
    updated_at: datetime


class CompanyPage(BaseModel):
    items: list[CompanyResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
