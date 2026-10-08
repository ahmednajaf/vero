"""Optional free public search, with robots, shared pacing and a challenge circuit.

Search only discovers URLs. Snippets never become metric evidence. The ordinary
official-site downloader must still authorise and retrieve every resulting PDF.
"""

import threading
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup
from sqlalchemy import Engine

from app.core.config import Settings
from app.discovery.crawler import access_challenge
from app.discovery.http import AcquisitionError, SafeHTTP, SourcePolicy, require_success
from app.pipeline.throttle import DomainPacer

_disabled = threading.Event()
_lock = threading.Lock()


def official_search(
    domain: str, year: int, settings: Settings, engine: Engine | None = None
) -> tuple[list[dict[str, str]], str]:
    if _disabled.is_set():
        raise AcquisitionError(
            "search_circuit_open",
            "Search provider challenged/rate-limited this process; no further requests",
        )
    query = f"site:{domain} {year} sustainability ESG environmental annual report filetype:pdf"
    url = "https://html.duckduckgo.com/html/?" + urlencode({"q": query})
    config = settings.model_copy(
        update={
            "discovery_delay_seconds": settings.discovery_search_delay_seconds,
            "discovery_retries": 0,
        }
    )
    client = SafeHTTP(
        config,
        SourcePolicy(("html.duckduckgo.com",)),
        pacer=DomainPacer(engine, ("html.duckduckgo.com",))
        if engine is not None
        else None,
    )
    try:
        # Serialise search requests across this run as well as DB per-domain slots.
        with _lock:
            if _disabled.is_set():
                raise AcquisitionError(
                    "search_circuit_open",
                    "Search provider unavailable for this process",
                )
            response = client.get(url)
            try:
                if response.status_code in {202, 403, 429}:
                    _disabled.set()
                    raise AcquisitionError(
                        "search_access_control",
                        f"Search HTTP {response.status_code}; stopped without bypass",
                    )
                require_success(response)
                soup = BeautifulSoup(client.read(response), "html.parser")
            finally:
                response.close()
            if access_challenge(soup) or soup.select_one(
                "#challenge-form, #anomaly-modal"
            ):
                _disabled.set()
                raise AcquisitionError(
                    "search_access_control",
                    "Search challenge detected; stopped without bypass",
                )
        hits = []
        for anchor in soup.select(".result__a")[:10]:
            href = urljoin(url, str(anchor.get("href", "")))
            target = parse_qs(urlsplit(href).query).get("uddg", [href])[0]
            container = anchor.find_parent(class_="result")
            snippet = container.select_one(".result__snippet") if container else None
            if SourcePolicy((domain,)).owns(target):
                hits.append(
                    {
                        "url": target,
                        "title": anchor.get_text(" ", strip=True),
                        "snippet": snippet.get_text(" ", strip=True) if snippet else "",
                    }
                )
        return hits, url
    except AcquisitionError as exc:
        if exc.code in {"rate_limited", "access_control"}:
            _disabled.set()
        raise
    finally:
        client.close()
