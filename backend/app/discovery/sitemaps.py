"""Bounded fallback over company-published sitemaps, never guessed report URLs."""

import re
from xml.etree import ElementTree

from app.discovery.crawler import (
    Discovery,
    RELEVANT,
    NON_DOCUMENT,
    discover,
    make_candidate,
    navigation_priority,
)
from app.discovery.http import AcquisitionError, SafeHTTP, require_success


def discover_sitemaps(http: SafeHTTP, year: int) -> Discovery:
    result = Discovery(sources=[])
    pending = http.known_sitemaps()
    seen: set[str] = set()
    pages: list[str] = []
    while pending and len(seen) < 6:
        url = pending.pop(0)
        if url in seen or not http.policy.owns(url):
            continue
        seen.add(url)
        response = None
        try:
            response = http.get(url)
            require_success(response)
            body = http.read(response, 3_000_000)
            # ElementTree does not resolve external entities; additionally reject DTDs.
            if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
                raise AcquisitionError(
                    "unsafe_sitemap", "Sitemap DTD/entity declarations refused"
                )
            tree = ElementTree.fromstring(body)
            locations = [
                node.text.strip()
                for node in tree.iter()
                if node.tag.rsplit("}", 1)[-1] == "loc" and node.text
            ][:5000]
            if tree.tag.rsplit("}", 1)[-1] == "sitemapindex":
                pending.extend(
                    sorted(
                        (v for v in locations if http.policy.owns(v) and v not in seen),
                        key=lambda v: (
                            not bool(RELEVANT.search(v)),
                            not bool(
                                re.search(r"[/_.-]en(?:[-_/\.]|$)|english", v, re.I)
                            ),
                            len(v),
                        ),
                    )[:12]
                )
            else:
                for location in locations:
                    if (
                        not http.policy.owns(location)
                        or not RELEVANT.search(location)
                        or NON_DOCUMENT.search(location)
                    ):
                        continue
                    if re.search(r"\.pdf(?:$|\?)", location, re.I):
                        result.candidates.append(
                            make_candidate(
                                location,
                                location.rsplit("/", 1)[-1],
                                "",
                                url,
                                year,
                                http,
                            )
                        )
                    else:
                        pages.append(location)
            result.diagnostics.append(
                {
                    "code": "sitemap_read",
                    "url": url,
                    "status": "discovered",
                    "locations": len(locations),
                }
            )
        except (AcquisitionError, ElementTree.ParseError) as exc:
            result.diagnostics.append(
                {
                    "code": exc.code
                    if isinstance(exc, AcquisitionError)
                    else "sitemap_xml",
                    "url": url,
                    "status": "needs_review",
                    "message": str(exc)[:300],
                }
            )
        finally:
            if response is not None:
                response.close()
    if not any(c.status == "discovered" for c in result.candidates) and pages:
        selected = sorted(
            set(pages),
            key=lambda v: (navigation_priority(v, year), len(v)),
        )[:4]
        # Reuse exactly the same request budget, robots decisions and throttling.
        additional = discover(http, selected, year)
        result.candidates.extend(additional.candidates)
        result.diagnostics.extend(additional.diagnostics)
        result.pages_visited += additional.pages_visited
    return result
