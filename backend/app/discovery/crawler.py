"""Deterministic candidate retrieval and explainable ranking; no PDF text extraction."""

import heapq
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

from bs4 import BeautifulSoup

from app.discovery.http import (
    AcquisitionError,
    SafeHTTP,
    canonical_url,
    require_success,
)

POLICY_VERSION = "official-reports-v9-exact-assets"
SPECIALISED_FINANCING = re.compile(
    r"(?:sustainable|sustainability|green|social)[\s_-]+bond|bond[\s_-]+(?:allocation|impact|report)",
    re.I,
)
RELEVANT = re.compile(
    r"sustainab|\besg\b|climate|environment|responsib|impact|annual[\s_-]*report|integrated[\s_-]*report|non[\s_-]*financial[\s_-]*statement",
    re.I,
)
NAVIGATION = re.compile(r"investor|reports?|reporting|publications?|downloads?", re.I)
EXCLUDED = re.compile(
    r"press[\s_/-]*release|news[\s_/-]*release|brochure|supplier[\s_-]*(code|conduct)|code[\s_-]*of[\s_-]*conduct|\bpolic(?:y|ies)\b|investor[\s_-]*(deck|presentation)|\bpresentation\b|\bhighlights\b|\bfactsheet\b",
    re.I,
)
SUPPLEMENT = re.compile(
    r"assurance|verification[\s_-]*(?:statement|report)|(?:gri|sasb)[\s_-]*(?:content[\s_-]*)?index|(?:report[\s_-]*)?editorial[\s_-]*policy|reporting[\s_-]*framework|principles[\s_-]*for[\s_-]*responsible[\s_-]*banking|communication[\s_-]*on[\s_-]*progress|lobbying[\s_-]*report|modern[\s_-]*slavery|conflict[\s_-]*minerals|forced[\s_-]*labou?r|(?:ceo|chief[\s_-]*executive|chairman)[\s_-]*(?:message|letter)|sustainable[\s_-]*issuance|certain[\s_-]*weapons[\s_-]*statement|portfolio[\s_-]*update|principal[\s_-]*adverse[\s_-]*impact|[-_/]pai[-_/]|environmental-stewardship-jnj",
    re.I,
)
YEARS = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
FISCAL_YEARS = re.compile(
    r"\bFY[\s._-]*(\d{2})(?!\d)(?:\s*[/–-]\s*(?:FY\s*)?(\d{2})(?!\d))?",
    re.I,
)
NON_DOCUMENT = re.compile(
    r"\.(?:zip|xlsx?|csv|jpe?g|png|gif|svg|webp|mp4|mp3|css|js)(?:$|[?#])", re.I
)


def published_downloads(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """Read literal JSON download records, never execute a publisher's scripts.

    Supports JSON hydration and Next flight string frames. Only a file's own
    URL/filename and its enclosing download label are associated; page-wide text
    cannot supply a missing year. Object count/depth and input sizes are bounded.
    """
    found: dict[str, str] = {}
    visited = 0

    def walk(value: object, depth: int = 0) -> None:
        nonlocal visited
        visited += 1
        if visited > 20_000 or depth > 30 or len(found) >= 200:
            return
        if isinstance(value, dict):
            asset = value.get("file", value.get("document"))
            if not isinstance(asset, dict):
                asset = value if "originalFilename" in value else None
            if isinstance(asset, dict):
                url = asset.get("url")
                labels = [
                    value.get("label"),
                    value.get("title"),
                    asset.get("originalFilename"),
                ]
                label = " ".join(
                    v for v in labels if isinstance(v, str) and len(v) < 1000
                )
                if (
                    isinstance(url, str)
                    and re.search(r"\.pdf(?:$|[?&#])", url, re.I)
                    and RELEVANT.search(label + " " + url)
                ):
                    # Different language records may share a file; first explicit
                    # labelled download wins, without changing the observed URL.
                    found.setdefault(url, label or url)
            for child in value.values():
                walk(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                walk(child, depth + 1)

    for script in soup.find_all("script", limit=300):
        raw = script.string or ""
        if not raw or len(raw) > 2_000_000 or ".pdf" not in raw:
            continue
        try:
            if script.get("type") in {"application/json", "application/ld+json"}:
                walk(json.loads(raw))
            elif raw.strip().startswith("self.__next_f.push("):
                # Decode the literal call argument, not JavaScript expressions.
                argument = raw.strip()[len("self.__next_f.push(") :].rstrip("; ")
                if not argument.endswith(")"):
                    continue
                frame = json.loads(argument[:-1])
                if (
                    isinstance(frame, list)
                    and len(frame) == 2
                    and frame[0] == 1
                    and isinstance(frame[1], str)
                ):
                    for line in frame[1].splitlines():
                        _, _, payload = line.partition(":")
                        if payload.startswith(("{", "[")):
                            try:
                                walk(json.loads(payload))
                            except (ValueError, RecursionError):
                                continue
        except (ValueError, RecursionError):
            continue
    return list(found.items())


def navigation_priority(value: str, year: int, depth: int = 0) -> int:
    """Spend the existing crawl budget on reporting hubs, not news and archives."""
    text = unquote(value).lower()
    score = depth * 2
    if re.search(r"sustainab|responsib|environment|\besg\b", text):
        score -= 5
    if re.search(r"report|disclosure|publication", text):
        score -= 4
    if str(year) in text:
        score -= 4
    if re.search(r"/(?:news|blog|events?)/", text):
        score += 12
    labelled_years = [int(y) for y in YEARS.findall(text)]
    if labelled_years and max(labelled_years) < year - 1:
        score += 20
    return score


@dataclass
class Candidate:
    url: str
    title: str
    discovered_from: str
    detected_year: int | None
    report_type: str
    confidence: float
    reason: str
    status: str
    official: bool
    pdf: bool
    mime_type: str | None = None
    file_size: int | None = None
    selected: bool = False


@dataclass
class Discovery:
    sources: list[str]
    candidates: list[Candidate] = field(default_factory=list)
    diagnostics: list[dict[str, object]] = field(default_factory=list)
    pages_visited: int = 0
    http_requests: int = 0
    status: str = "unavailable"
    reason: str = "No matching report found within the bounded official-site search"


def report_kind(text: str) -> str:
    value = re.sub(r"[-_/]+", " ", text.lower())
    if re.search(r"non\s*financial\s*statement", value):
        return "sustainability"
    for word, kind in (
        ("integrated", "integrated"),
        ("annual", "annual"),
        ("sustainab", "sustainability"),
        ("esg", "esg"),
        ("climate", "climate"),
        ("environment", "environmental"),
        ("responsib", "responsibility"),
        ("impact", "impact"),
    ):
        if word in value:
            return kind
    return "unknown"


def make_candidate(
    url: str,
    title: str,
    context: str,
    source: str,
    year: int,
    http: SafeHTTP,
    *,
    direct_pdf: bool = False,
    allow_unlabelled_year: bool = False,
) -> Candidate:
    decoded = unquote(url)
    primary = f"{title} {decoded}"
    # A 2025 report often lives in a /2026/ publication directory. Prefer the
    # explicit link title, then the filename, before directory/context years.
    def labelled_years(value: str) -> set[str]:
        years = set(YEARS.findall(value))
        # An explicit FY25 label is not the /2026/ publication directory.
        # A range remains ambiguous. No naked two-digit number becomes a year.
        for match in FISCAL_YEARS.finditer(value):
            years.update("20" + y for y in match.groups() if y)
        return years

    found = labelled_years(title)
    if not found:
        found = labelled_years(urlsplit(decoded).path.rsplit("/", 1)[-1])
    if not found:
        found = labelled_years(primary)
    if not found:
        found = labelled_years(context)
    detected = int(next(iter(found))) if len(found) == 1 else None
    kind = report_kind(primary)
    if kind == "unknown":
        kind = report_kind(context)
    pdf = direct_pdf or bool(re.search(r"\.pdf(?:$|[?&#])", decoded, re.I))
    official = http.policy.owns(url) or canonical_url(url) in http.policy.document_urls
    exclusions: list[str] = []
    if SPECIALISED_FINANCING.search(primary):
        exclusions.append(
            "Specialised financing disclosure, not a company-wide primary report"
        )
    if SUPPLEMENT.search(primary):
        exclusions.append(
            "Supporting assurance/index document, not the complete company report"
        )
    # Delimiters are spaces so /policy/ and supplier-code URLs are excluded too.
    if EXCLUDED.search(re.sub(r"[-_/]+", " ", primary)):
        exclusions.append("Excluded document type; explicit approval required")
    if "/products/" in decoded.lower() or re.search(
        r"product[\s_-]+environmental[\s_-]+report", primary, re.I
    ):
        exclusions.append(
            "Product-level disclosure is not a company-wide primary report"
        )
    if not official:
        exclusions.append("Unverified external host; not an approved primary source")
    if detected != year and not (allow_unlabelled_year and detected is None):
        exclusions.append(
            f"Year label {detected or 'unknown/ambiguous'} does not establish requested year {year}"
        )
    if kind == "unknown":
        exclusions.append("No recognised report type")
    if not re.search(r"report|disclosure|statement", primary + " " + context, re.I):
        exclusions.append("Document is not labelled as a report or disclosure")
    annual_needs_check = kind == "annual" and not re.search(
        r"sustainab|\besg\b|climate|environment|responsib", title + " " + context, re.I
    )
    if annual_needs_check and not http.settings.discovery_verify_annual_content:
        exclusions.append(
            "Annual report lacks nearby evidence of sustainability disclosure"
        )
    if not pdf:
        exclusions.append("HTML/viewer disclosure requires review or a direct PDF link")
    score = (
        0.95
        if kind in {"sustainability", "esg"}
        else (
            0.90
            if kind
            in {"climate", "environmental", "integrated", "responsibility", "impact"}
            else 0.80
        )
    )
    if not YEARS.search(primary) and detected:
        score -= 0.10
    if re.search(r"summary|at.a.glance", primary, re.I):
        exclusions.append("Summary, not demonstrably the complete report")
    reason = (
        "; ".join(exclusions)
        if exclusions
        else f"Official {kind} PDF; exact {year} year label. Label is not a verified reporting period"
    )
    if annual_needs_check and not exclusions:
        reason += (
            "; requires PDF content check for sustainability disclosure before indexing"
        )
    if not exclusions and detected is None:
        score = min(score, 0.65)
        reason = f"Official {kind} PDF with unknown/ambiguous year label; retained for document search only, not {year} coverage"
    return Candidate(
        url,
        title[:1000] or url,
        source,
        detected,
        kind,
        min(score, 0.45) if exclusions else score,
        reason,
        "needs_review" if exclusions else "discovered",
        official,
        pdf,
    )


def access_challenge(soup: BeautifulSoup) -> bool:
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = soup.get_text(" ", strip=True)[:2000]
    return (
        bool(
            re.search(
                r"access denied|request rejected|verify (?:that )?you are human|checking your browser|just a moment|captcha|enable javascript and cookies to continue",
                title + " " + text,
                re.I,
            )
        )
        or soup.select_one('input[type="password"]') is not None
    )


def needs_javascript(soup: BeautifulSoup) -> bool:
    plain = soup.get_text(" ", strip=True)
    return bool(soup.find("script")) and (
        bool(
            re.search(
                r"enable javascript|javascript (?:is )?required|requires javascript",
                plain,
                re.I,
            )
        )
        or (len(plain) < 200 and soup.select_one("#root, #app, #__next") is not None)
        or (
            len(plain) < 200
            and not soup.find("a", href=True)
            and soup.select_one(
                'script[src*="app."], script[src*="bundle."], script[src*="main."]'
            )
            is not None
        )
    )


def discover(
    http: SafeHTTP,
    sources: list[str],
    year: int,
    renderer: Callable[[str, SafeHTTP], str] | None = None,
) -> Discovery:
    result = Discovery(sources=list(dict.fromkeys(sources)))
    queue: list[tuple[int, int, str, str, int, str]] = []
    serial = 0
    queued: set[str] = set()
    visited: set[str] = set()
    candidates: dict[str, Candidate] = {}
    omitted = 0

    def rank(item: Candidate) -> tuple[float, bool, int, str]:
        return (-item.confidence, item.detected_year != year, len(item.url), item.url)

    def enqueue(url: str, source: str, depth: int, title: str, priority: int) -> None:
        nonlocal serial
        try:
            value = canonical_url(url)
        except (AcquisitionError, ValueError, UnicodeError):
            return
        if value in queued or not http.policy.owns(value):
            return
        queued.add(value)
        serial += 1
        heapq.heappush(queue, (priority, serial, value, source, depth, title))

    def candidate(
        url: str, title: str, context: str, source: str, **kwargs: bool
    ) -> None:
        nonlocal omitted
        try:
            url = canonical_url(url)
        except (AcquisitionError, ValueError, UnicodeError):
            return
        new = make_candidate(url, title, context, source, year, http, **kwargs)
        old = candidates.get(url)
        if old is None or new.confidence > old.confidence:
            candidates[url] = new
        if len(candidates) > http.settings.discovery_max_candidates:
            # Do not let a long archive at the top of a page hide the best report
            # appearing later in document order.
            worst = max(candidates.values(), key=rank)
            del candidates[worst.url]
            omitted += 1

    for index, source in enumerate(result.sources):
        if not http.policy.owns(source):
            result.diagnostics.append(
                {
                    "url": source,
                    "code": "external_seed",
                    "status": "needs_review",
                    "message": "Configured seed is not on an approved company-owned domain; not fetched",
                }
            )
        enqueue(source, source, 0, source, index)
    while queue and result.pages_visited < http.settings.discovery_max_pages:
        _, _, url, source, depth, label = heapq.heappop(queue)
        if url in visited:
            continue
        visited.add(url)
        response = None
        try:
            response = http.get(url)
            require_success(response)
            final_url = canonical_url(response.url)
            mime = (
                response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            )
            if mime in {"application/pdf", "application/x-pdf"}:
                candidate(final_url, label, "", source, direct_pdf=True)
                entry = candidates.get(final_url)
                if entry:
                    entry.mime_type = mime
                    length = response.headers.get("Content-Length", "")
                    entry.file_size = int(length) if length.isdigit() else None
                continue
            if mime not in {"text/html", "application/xhtml+xml", ""}:
                raise AcquisitionError(
                    "wrong_mime", f"Expected HTML or PDF, received {mime or 'unknown'}"
                )
            body = http.read(response, 5_000_000)
            # Some official download endpoints serve PDFs as octet-stream; only a
            # download with signature validation can establish that type.
            soup = BeautifulSoup(body, "html.parser")
            result.pages_visited += 1
            if access_challenge(soup):
                raise AcquisitionError(
                    "access_control",
                    "Login or explicit anti-bot challenge; no bypass attempted",
                )
            for download_url, download_label in published_downloads(soup):
                try:
                    http.policy = http.policy.endorse_document(download_url, final_url)
                    if download_url in http.policy.document_urls:
                        result.diagnostics.append(
                            {
                                "code": "official_document_link",
                                "status": "discovered",
                                "url": canonical_url(download_url),
                                "source_page": final_url,
                                "link_text": download_label[:1000],
                                "policy": "exact-publisher-pdf-v1",
                                "evidence_method": "literal_page_download_data",
                                "message": "Exact PDF URL and adjacent download metadata read from published page JSON; no script execution",
                            }
                        )
                    candidate(download_url, download_label, download_label, final_url)
                except (AcquisitionError, ValueError, UnicodeError):
                    continue
            anchors = soup.find_all("a", href=True)
            useful = any(
                c.official and c.pdf and c.discovered_from == final_url
                for c in candidates.values()
            ) or any(
                RELEVANT.search(a.get_text(" ", strip=True) + str(a.get("href")))
                for a in anchors
            )
            if needs_javascript(soup) and not useful:
                if renderer is None or not http.settings.discovery_allow_js:
                    raise AcquisitionError(
                        "javascript_required",
                        "Clear client-rendered shell; optional browser fallback is disabled",
                    )
                soup = BeautifulSoup(renderer(final_url, http), "html.parser")
                if access_challenge(soup):
                    raise AcquisitionError(
                        "access_control",
                        "Rendered page presented an access control; stopped",
                    )
                result.diagnostics.append(
                    {
                        "url": final_url,
                        "code": "javascript_fallback",
                        "status": "discovered",
                        "message": "Static HTML insufficient; used restricted browser fallback",
                    }
                )
                anchors = soup.find_all("a", href=True)
            for anchor in anchors:
                href = str(anchor.get("href", ""))
                if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                    continue
                target = urljoin(final_url, href)
                if NON_DOCUMENT.search(unquote(target)):
                    continue
                title = (
                    anchor.get_text(" ", strip=True)
                    or str(anchor.get("aria-label", ""))
                    or str(anchor.get("title", ""))
                )
                if not title:
                    title = " ".join(
                        str(img.get("alt", "")) for img in anchor.find_all("img")
                    )
                parent = anchor.parent
                # Never borrow a year or sustainability label from unrelated links,
                # navigation, or the entire page (especially for annual reports).
                context = (
                    parent.get_text(" ", strip=True)[:600]
                    if parent
                    and parent.name
                    not in {"body", "html", "nav", "footer", "header", "[document]"}
                    and len(parent.find_all("a")) == 1
                    else title
                )
                # Archive tables often label their link only 'PDF format'. The
                # report name/year is in a neighbouring cell of the SAME row.
                # Do not borrow labels from the whole archive or preceding row.
                row = anchor.find_parent("tr")
                if row is not None and len(row.get_text(" ", strip=True)) <= 600:
                    context = row.get_text(" ", strip=True)
                text = title + " " + unquote(target)
                relevant = bool(RELEVANT.search(text))
                is_pdf = bool(re.search(r"\.pdf(?:$|[?&#])", unquote(target), re.I))
                if is_pdf and (relevant or RELEVANT.search(context)):
                    try:
                        endorsed = http.policy.endorse_document(target, final_url)
                        if endorsed != http.policy:
                            http.policy = endorsed
                            result.diagnostics.append(
                                {
                                    "code": "official_document_link",
                                    "status": "discovered",
                                    "url": canonical_url(target),
                                    "source_page": final_url,
                                    "link_text": title[:1000],
                                    "policy": "exact-publisher-pdf-v1",
                                    "message": "Exact PDF linked by a fetched official HTTPS page; this does not grant wider crawling permission",
                                }
                            )
                    except (AcquisitionError, ValueError, UnicodeError):
                        pass
                    candidate(target, title, context, final_url)
                elif relevant or NAVIGATION.search(text):
                    if YEARS.search(text) and re.search(
                        r"report|disclosure", text, re.I
                    ):
                        candidate(target, title, context, final_url)
                    if (
                        depth < http.settings.discovery_max_depth
                        and not EXCLUDED.search(text)
                    ):
                        priority = navigation_priority(text, year, depth + 1)
                        enqueue(target, final_url, depth + 1, title, priority)
                # Official viewer links sometimes encode a direct PDF in mediaId/url.
                for key, values in parse_qs(urlsplit(target).query).items():
                    # Only URL-bearing viewer parameters are links. An extension
                    # (.pdf), attachment filename or storage key is not a URL and
                    # must never become a guessed path like /get_file/.pdf.
                    if key.lower() not in {
                        "mediaid",
                        "url",
                        "file",
                        "document",
                        "pdf",
                        "pdfurl",
                        "fileurl",
                        "downloadurl",
                        "src",
                    }:
                        continue
                    for value in values:
                        if re.search(r"[^/]\.pdf$", value, re.I) and RELEVANT.search(
                            title + " " + value
                        ):
                            candidate(urljoin(target, value), title, context, final_url)
        except AcquisitionError as exc:
            result.diagnostics.append(
                {
                    "url": url,
                    "code": exc.code,
                    "status": exc.status,
                    "message": str(exc),
                }
            )
            if exc.code in {"request_limit", "rate_limited"}:
                break
        finally:
            if response is not None:
                response.close()
    if queue:
        result.diagnostics.append(
            {
                "code": "crawl_limit",
                "status": "needs_review",
                "message": "Bounded crawl ended with unvisited links; not exhaustive",
            }
        )
    if omitted:
        result.diagnostics.append(
            {
                "code": "candidate_limit",
                "status": "needs_review",
                "message": f"Retained best {len(candidates)} candidates; {omitted} lower-ranked encounters omitted",
            }
        )
    result.candidates = sorted(candidates.values(), key=rank)
    selected = next((c for c in result.candidates if c.status == "discovered"), None)
    if selected:
        selected.selected = True
        selected.reason += "; highest eligible deterministic score (ties: shortest URL, then lexical URL)"
        result.status, result.reason = "discovered", selected.reason
    elif result.candidates or any(
        d["status"] == "needs_review" for d in result.diagnostics
    ):
        result.status, result.reason = (
            "needs_review",
            "No eligible exact-year primary PDF; review candidates and crawl diagnostics",
        )
    elif any(d["status"] == "failed" for d in result.diagnostics):
        result.status, result.reason = (
            "failed",
            "Discovery was incomplete because of network or HTTP failures",
        )
    result.http_requests = http.requests
    return result
