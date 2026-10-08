"""Build a sourced, 500-issuer registry; no invented domains or financial metrics.

Existing identities are preserved. Expansion uses a dated S&P 500 constituent
snapshot and revision-backed company infobox website statements. Unresolved entities,
multiple share classes and ambiguous countries are excluded, not guessed.
"""

import argparse
import hashlib
import json
import re
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import NAMESPACE_URL, uuid5

import requests
import pycountry
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Company
from app.db.session import create_database_engine
from app.schemas.company import CompanyInput

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "backend/storage/universe-metadata"
SECTORS = {
    "Information Technology": "Technology",
    "Financials": "Financial Services",
    "Energy": "Energy",
    "Utilities": "Energy",
    "Consumer Staples": "Consumer / Retail",
    "Consumer Discretionary": "Consumer / Retail",
    "Industrials": "Industrials",
    "Materials": "Industrials",
    "Communication Services": "Technology",
}
REGIONS = {
    "US": "North America",
    "CA": "North America",
    "JP": "Asia",
    "AU": "Oceania",
    "NZ": "Oceania",
    "SG": "Asia",
    "CN": "Asia",
    "HK": "Asia",
    "IN": "Asia",
    "IL": "Middle East",
    "BM": "North America",
}
EUROPE = {
    "GB",
    "IE",
    "DE",
    "FR",
    "NL",
    "CH",
    "SE",
    "NO",
    "DK",
    "FI",
    "IT",
    "ES",
    "LU",
    "BE",
    "AT",
}


class Metadata:
    def __init__(self):
        CACHE.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers["User-Agent"] = (
            "VeroResearchCollector/1.0 (public sustainability research; metadata acquisition)"
        )

    def get(self, host, **params):
        url = f"https://{host}/w/api.php"
        params.update(format="json", maxlag=5)
        key = hashlib.sha256(
            (url + json.dumps(params, sort_keys=True)).encode()
        ).hexdigest()
        path = CACHE / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text())["body"]
        time.sleep(5)
        for attempt in range(6):
            response = self.session.get(url, params=params, timeout=45)
            response.raise_for_status()  # No challenge, forbidden or rate-limit bypass.
            body = response.json()
            if body.get("error", {}).get("code") != "maxlag":
                break
            print(
                json.dumps({"event": "metadata_server_lag", "retry": attempt + 1}),
                flush=True,
            )
            time.sleep(min(30, 5 * (attempt + 1)))
        if "error" in body:
            raise RuntimeError(body["error"].get("code", "metadata_api_error"))
        path.write_text(
            json.dumps(
                {
                    "url": response.url,
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "sha256": hashlib.sha256(response.content).hexdigest(),
                    "body": body,
                }
            )
        )
        return body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=500)
    parser.add_argument("--import-db", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.size <= 1000:
        parser.error("size must be 1–1000")
    api = Metadata()
    parsed = api.get(
        "en.wikipedia.org",
        action="parse",
        page="List of S&P 500 companies",
        prop="text|revid",
    )["parse"]
    table = BeautifulSoup(parsed["text"]["*"], "html.parser").select_one(
        "#constituents"
    )
    if table is None:
        raise RuntimeError("constituent_table_missing")
    rows = []
    for tr in table.select("tr")[1:]:
        cells = tr.find_all("td")
        link = cells[1].find("a", href=True)
        listing = cells[0].find("a", href=True)
        if not link or not listing:
            continue
        exchange_url = str(listing["href"])
        exchange = (
            "XNYS"
            if "nyse.com/quote/" in exchange_url
            else "XNAS"
            if "nasdaq.com" in exchange_url
            else None
        )
        if not exchange:
            continue
        title = unquote(str(link["href"]).removeprefix("/wiki/")).replace("_", " ")
        rows.append(
            {
                "title": title,
                "company_name": cells[1].get_text(" ", strip=True),
                "ticker": cells[0].get_text(" ", strip=True),
                "exchange": exchange,
                "gics": cells[2].get_text(" ", strip=True),
                "industry": cells[3].get_text(" ", strip=True),
                "headquarters": cells[4].get_text(" ", strip=True),
                "cik": cells[6].get_text(strip=True),
                "listing_url": exchange_url,
            }
        )
    titles = list(dict.fromkeys(r["title"] for r in rows))
    qids = {}
    for start in range(0, len(titles), 40):
        body = api.get(
            "en.wikipedia.org",
            action="query",
            prop="pageprops",
            titles="|".join(titles[start : start + 40]),
            redirects=1,
        )["query"]
        batch = {
            p["title"]: p.get("pageprops", {}).get("wikibase_item")
            for p in body["pages"].values()
        }
        for entry in body.get("redirects", []):
            batch[entry["from"]] = batch.get(entry["to"])
        qids.update(batch)
        print(
            json.dumps(
                {
                    "event": "metadata_pages",
                    "processed": min(start + 40, len(titles)),
                    "total": len(titles),
                }
            ),
            flush=True,
        )
    # Wikidata returned maxlag followed by HTTP 429 on this run: do not retry it.
    # Company article infoboxes are an independent, revision-addressed metadata
    # source. No report or metric is accepted on the authority of Wikipedia.
    articles = {}
    for start in range(0, len(titles), 25):
        body = api.get(
            "en.wikipedia.org",
            action="query",
            prop="revisions",
            rvprop="ids|content",
            rvslots="main",
            titles="|".join(titles[start : start + 25]),
            redirects=1,
        )["query"]
        batch = {p["title"]: p for p in body["pages"].values()}
        for entry in body.get("redirects", []):
            batch[entry["from"]] = batch.get(entry["to"], {})
        articles.update(batch)
        print(
            json.dumps(
                {
                    "event": "company_metadata",
                    "processed": min(start + 25, len(titles)),
                    "total": len(titles),
                }
            ),
            flush=True,
        )
    us_states = {s.name for s in pycountry.subdivisions.get(country_code="US")} | {
        "Washington, D.C.",
        "Washington D.C.",
        "D.C.",
    }
    country_names = {c.name: c.alpha_2 for c in pycountry.countries} | {
        "UK": "GB",
        "United Kingdom": "GB",
        "South Korea": "KR",
        "Taiwan": "TW",
    }
    engine = create_database_engine(get_settings())
    with Session(engine) as session:
        existing = list(
            session.scalars(
                select(Company)
                .where(Company.active.is_(True))
                .order_by(Company.company_name)
            )
        )
        companies = [
            CompanyInput(
                **{key: getattr(c, key) for key in CompanyInput.model_fields}
            ).model_dump(mode="json")
            for c in existing
        ]
        evidence = {
            str(c.id): {
                "basis": "preserved_existing_registry",
                "source_file": c.source_file,
                "source_sha256": c.source_sha256,
                "source_row": c.source_row,
            }
            for c in existing
        }
    seen_listings = {(c["exchange"], c["ticker"]) for c in companies}
    seen_domains = {c["official_domain"].removeprefix("www.") for c in companies}
    seen_issuers = set()
    exclusions = []
    for row in rows:
        qid = qids.get(row["title"])
        article = articles.get(row["title"], {})
        revision = article.get("revisions", [{}])[0]
        content = revision.get("slots", {}).get("main", {}).get("*", "")
        sector = (
            "Pharmaceuticals"
            if row["industry"] in {"Pharmaceuticals", "Biotechnology"}
            else SECTORS.get(row["gics"])
        )
        reason = None
        website_fields = re.findall(
            r"^\|\s*(?:website|homepage|url)\s*=\s*(.+)$", content, re.M | re.I
        )
        websites = []
        for field in website_fields[:1]:
            websites.extend(re.findall(r"https?://[^\s<>|\]}]+", field))
            websites.extend(
                "https://" + u
                for u in re.findall(
                    r"\{\{(?:URL|official website)\s*\|\s*(?!https?://)([a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s|}<>]*)?)",
                    field,
                    re.I,
                )
            )
        websites = sorted(set(websites))
        domains = {
            urlsplit(v).hostname.removeprefix("www.")
            for v in websites
            if urlsplit(v).hostname
        }
        hq = row["headquarters"]
        place = hq.rsplit(",", 1)[-1].strip()
        codes = (
            {"US"}
            if place in us_states or hq.endswith("Washington, D.C.")
            else ({country_names[place]} if place in country_names else set())
        )
        if (
            (row["exchange"], row["ticker"]) in seen_listings
            or domains & seen_domains
            or qid in seen_issuers
        ):
            reason = "existing_issuer_or_share_class"
        elif not sector:
            reason = "outside_current_sector_taxonomy"
        elif not qid or len(codes) != 1 or not domains:
            reason = "unresolved_identity_country_or_official_website"
        elif len(domains) != 1:
            reason = "multiple_official_domains_need_review"
        if reason:
            exclusions.append(
                {"company": row["company_name"], "reason": reason, "wikidata": qid}
            )
            continue
        country = next(iter(codes))
        region = "Europe" if country in EUROPE else REGIONS.get(country)
        if region is None:
            exclusions.append(
                {
                    "company": row["company_name"],
                    "reason": "region_needs_review",
                    "country": country,
                }
            )
            continue
        item = CompanyInput(
            id=uuid5(NAMESPACE_URL, f"https://www.wikidata.org/entity/{qid}"),
            company_name=row["company_name"],
            ticker=row["ticker"],
            exchange=row["exchange"],
            country=country,
            region=region,
            index="S&P 500",
            sector=sector,
            industry=row["industry"],
            official_domain=next(iter(domains)),
            reporting_year=2025,
            active=True,
        ).model_dump(mode="json")
        companies.append(item)
        seen_issuers.add(qid)
        seen_domains.add(item["official_domain"])
        seen_listings.add((item["exchange"], item["ticker"]))
        evidence[item["id"]] = {
            "basis": "index_snapshot_and_company_infobox",
            "index_source": f"https://en.wikipedia.org/w/index.php?oldid={parsed['revid']}",
            "website_metadata_source": f"https://en.wikipedia.org/w/index.php?oldid={revision.get('revid')}",
            "entity_source": f"https://www.wikidata.org/wiki/{qid}",
            "official_websites": websites,
            "country_basis": "Index headquarters location, not verified legal domicile",
            "headquarters_as_reported": hq,
            "index_listing_source": row["listing_url"],
            "cik": row["cik"],
            "gics_sector": row["gics"],
            "sector_mapping": "Vero coarse research buckets; not a comparability assertion",
        }
        if len(companies) >= args.size:
            break
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "requested": args.size,
        "actual": len(companies),
        "scope": "Existing international pilot plus sourced S&P 500 expansion; not a claim of the world's 500 largest companies",
        "companies": companies,
        "provenance": evidence,
        "exclusions": exclusions,
        "sectors": dict(Counter(c["sector"] for c in companies)),
        "countries": dict(Counter(c["country"] for c in companies)),
        "metrics_added": 0,
    }
    path = ROOT / "data" / f"company_universe_{args.size}.json"
    if path.exists():
        raise RuntimeError(
            f"Refusing to overwrite {path}; inspect the existing snapshot first"
        )
    path.write_text(json.dumps(payload, indent=2) + "\n")
    inserted = 0
    if args.import_db:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with Session(engine) as session, session.begin():
            for number, raw in enumerate(companies, 1):
                item = CompanyInput.model_validate(raw)
                if session.get(Company, item.id):
                    continue  # Never overwrite existing user-managed company metadata.
                session.add(
                    Company(
                        **item.model_dump(),
                        source_file=str(path.relative_to(ROOT)),
                        source_sha256=digest,
                        source_row=number,
                        imported_at=datetime.now(UTC),
                    )
                )
                inserted += 1
    print(
        json.dumps(
            {
                "file": str(path),
                "companies": len(companies),
                "inserted": inserted,
                "countries": payload["countries"],
                "sectors": payload["sectors"],
                "excluded": len(exclusions),
                "metrics_added": 0,
            }
        ),
        flush=True,
    )
    engine.dispose()


if __name__ == "__main__":
    main()
