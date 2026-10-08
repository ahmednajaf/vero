from uuid import uuid4

import pytest

from app.services.company_import import import_companies


@pytest.fixture
def populated(db_engine, seed_csv):
    assert import_companies(seed_csv, db_engine).committed


def test_pagination(api_client, populated):
    first = api_client.get("/api/companies?page=1&page_size=7").json()
    second = api_client.get("/api/companies?page=2&page_size=7").json()
    third = api_client.get("/api/companies?page=3&page_size=7").json()
    assert first["total"] == 20 and first["total_pages"] == 3
    assert [len(page["items"]) for page in (first, second, third)] == [7, 7, 6]
    assert (
        len({row["id"] for page in (first, second, third) for row in page["items"]})
        == 20
    )
    assert first == api_client.get("/api/companies?page=1&page_size=7").json()
    assert api_client.get("/api/companies?page=100").json()["items"] == []


def test_filters_and_combined_filters(api_client, populated):
    sector = api_client.get("/api/companies", params={"sector": "technology"}).json()
    assert sector["total"] == 4
    country = api_client.get("/api/companies?country=gb").json()
    assert country["total"] == 3
    combined = api_client.get(
        "/api/companies", params={"country": "US", "sector": "Technology"}
    ).json()
    assert combined["total"] == 2
    assert {row["ticker"] for row in combined["items"]} == {"AAPL", "MSFT"}
    assert api_client.get("/api/companies?sector=Unknown").json()["total"] == 0


@pytest.mark.parametrize(
    "term,ticker",
    [
        ("mIcRoSoFt", "MSFT"),
        ("aapl", "AAPL"),
        ("aramco.com", "2222"),
        ("005930", "005930"),
    ],
)
def test_search(api_client, populated, term, ticker):
    result = api_client.get("/api/companies", params={"search": term}).json()
    assert result["total"] == 1 and result["items"][0]["ticker"] == ticker


@pytest.mark.parametrize("search", ["%", "_", "' OR 1=1 --"])
def test_search_is_literal_and_parameterised(api_client, populated, search):
    response = api_client.get("/api/companies", params={"search": search})
    assert response.status_code == 200 and response.json()["total"] == 0


def test_detail_and_not_found(api_client, populated):
    first = api_client.get("/api/companies").json()["items"][0]
    response = api_client.get(f"/api/companies/{first['id']}")
    assert response.status_code == 200 and response.json() == first
    assert first["revenue"] is None and first["market_cap"] is None
    assert api_client.get(f"/api/companies/{uuid4()}").status_code == 404
    assert api_client.get("/api/companies/not-a-uuid").status_code == 422


@pytest.mark.parametrize(
    "query", ["page=0", "page_size=0", "page_size=101", "page=abc", "country=USA"]
)
def test_invalid_pagination_and_filter_input(api_client, query):
    assert api_client.get(f"/api/companies?{query}").status_code == 422


def test_empty_universe(api_client):
    assert api_client.get("/api/companies").json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 25,
        "total_pages": 0,
    }


def test_active_filter_and_money_serialisation(
    api_client, db_engine, company_row, csv_file
):
    company_row.update(
        active="false",
        revenue="100.123456",
        revenue_year="2025",
        reporting_currency="GBP",
    )
    assert import_companies(csv_file([company_row]), db_engine).committed
    assert api_client.get("/api/companies?active=true").json()["total"] == 0
    result = api_client.get("/api/companies?active=false").json()
    assert result["total"] == 1 and result["items"][0]["revenue"] == "100.123456"
