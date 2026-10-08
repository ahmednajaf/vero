"""Bounded, robots-aware HTTP. All redirects pass through the same source policy."""

import ipaddress
import re
import socket
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

import requests
from protego import Protego

from app.core.config import Settings


class AcquisitionError(Exception):
    def __init__(self, code: str, message: str, status: str = "needs_review"):
        super().__init__(message)
        self.code, self.status = code, status


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in {"https", "http"} or not parts.hostname:
        raise AcquisitionError("invalid_url", "Only absolute HTTP(S) URLs are allowed")
    if parts.username or parts.password or parts.port not in {None, 80, 443}:
        raise AcquisitionError(
            "invalid_url", "Credentials and nonstandard ports are prohibited"
        )
    host = parts.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    return urlunsplit((parts.scheme.lower(), host, parts.path or "/", parts.query, ""))


@dataclass(frozen=True)
class SourcePolicy:
    domains: tuple[str, ...]
    document_urls: tuple[str, ...] = ()

    def owns(self, url: str) -> bool:
        try:
            host = urlsplit(canonical_url(url)).hostname or ""
        except (AcquisitionError, ValueError, UnicodeError):
            return False
        return any(
            host == domain or host.endswith("." + domain) for domain in self.domains
        )

    def check(self, url: str) -> str:
        value = canonical_url(url)
        if not (
            self.owns(value)
            or value in self.document_urls
            or self.document_robots(value)
        ):
            raise AcquisitionError(
                "external_host", "Host is not an approved company-owned domain"
            )
        return value

    def document_robots(self, url: str) -> bool:
        """An exact linked asset permits only its own HTTPS robots file, not its host."""
        parts = urlsplit(url)
        return (
            parts.scheme == "https"
            and parts.path == "/robots.txt"
            and not parts.query
            and any(
                urlsplit(item).netloc == parts.netloc for item in self.document_urls
            )
        )

    def endorse_document(self, url: str, source_page: str) -> "SourcePolicy":
        """A fetched company page can endorse an exact owned or publishing-CDN PDF.

        No blanket CDN-domain permission, guessed URL, shortener or external crawl.
        Callers must retain the observed anchor and the official page as provenance.
        """
        value, source = canonical_url(url), canonical_url(source_page)
        parts = urlsplit(value)
        host = parts.hostname or ""
        pdf_link = bool(re.search(r"\.pdf$", parts.path, re.I)) or (
            self.owns(value) and parse_qs(parts.query).get("file_ext") == [".pdf"]
        )
        publisher_cdn = (
            bool(re.fullmatch(r"s\d+\.q4cdn\.com", host))
            or host
            in {
                "assets.ctfassets.net",
                "downloads.ctfassets.net",
                "assets.contentstack.io",
                "cdn.prod.website-files.com",
                "cdn.sanity.io",
            }
            or host.endswith(".cdn.prismic.io")
            or host.endswith(".cloudfront.net")
            or host.endswith(".azureedge.net")
            or host.endswith(".azurefd.net")
            or bool(re.fullmatch(r"delivery-p\d+-e\d+\.adobeaemcloud\.com", host))
            or bool(
                re.fullmatch(
                    r"[a-z0-9][a-z0-9.-]*\.s3(?:\.[a-z]{2}-[a-z]+-\d)?\.amazonaws\.com",
                    host,
                )
            )
        )
        if not (
            self.owns(source)
            and source.startswith("https:")
            and value.startswith("https:")
            and (self.owns(value) or publisher_cdn)
            and pdf_link
        ):
            return self
        return replace(
            self, document_urls=tuple(dict.fromkeys((*self.document_urls, value)))
        )


def public_dns(host: str) -> None:
    try:
        addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise AcquisitionError(
            "dns", f"DNS resolution failed for {host}", "failed"
        ) from exc
    if not addresses or any(
        not ipaddress.ip_address(item[4][0]).is_global for item in addresses
    ):
        raise AcquisitionError(
            "private_address", "Non-public network addresses are prohibited"
        )


class SafeHTTP:
    """One company job. No ambient credentials, automatic redirects, or cookie persistence.

    The CLI takes operator-curated company URLs, not anonymous user-supplied URLs.
    DNS preflight is defense-in-depth, not a DNS-rebinding-hardened network sandbox.
    """

    def __init__(
        self,
        settings: Settings,
        policy: SourcePolicy,
        session: requests.Session | None = None,
        resolver: Callable[[str], None] = public_dns,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        pacer: Callable[[str, float], None] | None = None,
    ):
        self.settings, self.policy = settings, policy
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.session.headers.update({"User-Agent": settings.discovery_user_agent})
        self.resolver, self.sleep, self.clock = resolver, sleeper, clock
        self.pacer = pacer
        self.requests = 0
        self._robots: dict[str, Protego | None] = {}
        self._robots_errors: dict[str, AcquisitionError] = {}
        self._last: dict[str, float] = {}
        self._delay: dict[str, float] = {}
        self.audit: list[dict[str, object]] = []

    def close(self) -> None:
        self.session.close()

    def known_sitemaps(self) -> list[str]:
        """Only sitemap locations actually published in fetched robots files."""
        return list(
            dict.fromkeys(
                url
                for parser in self._robots.values()
                if parser is not None
                for url in parser.sitemaps
                if self.policy.owns(url)
            )
        )[:20]

    def _pace(self, host: str) -> None:
        delay = max(self.settings.discovery_delay_seconds, self._delay.get(host, 0))
        if delay > 60:
            raise AcquisitionError(
                "crawl_delay",
                "Site requires a crawl delay above this job's 60s limit; deferred",
            )
        if self.pacer is not None:
            self.pacer(host, delay)
            return
        remaining = self._last.get(host, -float("inf")) + delay - self.clock()
        if remaining > 0:
            self.sleep(remaining)
        self._last[host] = self.clock()

    def _request(self, url: str) -> requests.Response:
        host = urlsplit(url).hostname or ""
        for attempt in range(self.settings.discovery_retries + 1):
            if self.requests >= self.settings.discovery_max_requests:
                raise AcquisitionError(
                    "request_limit", "Per-company HTTP request budget exhausted"
                )
            self.resolver(host)
            self._pace(host)
            self.requests += 1
            self.session.cookies.clear()
            try:
                response = self.session.get(
                    url,
                    allow_redirects=False,
                    stream=True,
                    timeout=(
                        self.settings.discovery_timeout_seconds,
                        self.settings.discovery_timeout_seconds,
                    ),
                    headers={
                        "Accept": "text/html,application/pdf,application/xhtml+xml;q=0.9,*/*;q=0.5"
                    },
                )
            except requests.RequestException as exc:
                if attempt < self.settings.discovery_retries:
                    self.sleep(min(2**attempt, 4))
                    continue
                raise AcquisitionError(
                    "timeout" if isinstance(exc, requests.Timeout) else "network",
                    str(exc)[:300],
                    "failed",
                ) from exc
            if response.status_code == 429:
                response.close()
                raise AcquisitionError(
                    "rate_limited",
                    "HTTP 429; stopped without retrying or bypassing the control",
                )
            if (
                response.status_code in {500, 502, 503, 504}
                and attempt < self.settings.discovery_retries
            ):
                wait = float(2**attempt)
                retry = response.headers.get("Retry-After")
                if retry:
                    try:
                        wait = max(wait, float(retry))
                    except ValueError:
                        try:
                            wait = max(
                                wait,
                                (
                                    parsedate_to_datetime(retry) - datetime.now(UTC)
                                ).total_seconds(),
                            )
                        except (ValueError, TypeError):
                            pass
                response.close()
                if wait > 10:
                    raise AcquisitionError(
                        "retry_after",
                        "Server requested a longer retry delay; job deferred",
                    )
                self.sleep(wait)
                continue
            return response
        raise AssertionError("unreachable")

    def _check_robots(self, url: str) -> None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._robots_errors:
            error = self._robots_errors[origin]
            if not (
                self.settings.discovery_allow_unavailable_robots_for_linked_documents
                and url in self.policy.document_urls
                and str(error) == "robots.txt returned HTTP 403; stopped conservatively"
            ):
                raise AcquisitionError(error.code, str(error), error.status)
            # Recheck normally for this exact retained PDF only. A prior generic
            # page denial is not an authorization to crawl the origin.
            del self._robots_errors[origin]
        if origin not in self._robots:
            # Robots redirect fetching never recurses into robots checks, but is still
            # bounded, paced, public-network-only, and restricted to owned domains.
            response = self.get(origin + "/robots.txt", robots=False)
            try:
                if response.status_code in {404, 410}:
                    self._robots[origin] = None
                elif (
                    self.settings.discovery_allow_unavailable_robots_for_linked_documents
                    and url in self.policy.document_urls
                    and 400 <= response.status_code < 500
                    and response.status_code not in {401, 407, 429, 451}
                ):
                    # RFC 9309 §2.3.1.3 distinguishes an unavailable robots file
                    # from a document-level refusal. This opt-in grants no extra
                    # URL, authentication, header disguise or anti-bot workaround.
                    body = self.read(response, 512_000).decode(
                        "utf-8", errors="replace"
                    )
                    if re.search(
                        r"captcha|verify.{0,60}human|bot.detect|automated.requests|enable.{0,60}cookies|challenge-platform|cf-chl|security.check|just.a.moment|sign.in|log.in|type\s*=\s*['\"]password",
                        body,
                        re.I,
                    ):
                        raise AcquisitionError(
                            "robots_unavailable",
                            "robots.txt presented a login or bot challenge; stopped",
                        )
                    self.audit.append(
                        {
                            "code": "robots_unavailable_exact_document",
                            "url": url,
                            "robots_url": origin + "/robots.txt",
                            "http_status": response.status_code,
                            "policy": "rfc9309-2.3.1.3-exact-pdf-v1",
                            "message": "Unavailable robots file; normal GET of exact company-published PDF permitted by explicit configuration. Document access controls still apply.",
                        }
                    )
                    # Do not cache this as an origin-wide robots allowance.
                    # Another path, including an HTML page on an owned domain,
                    # must independently satisfy the normal robots policy.
                    return
                elif response.status_code == 200:
                    body = self.read(response, 512_000).decode(
                        "utf-8", errors="replace"
                    )
                    if (
                        "<html" in body[:1000].lower()
                        or "captcha" in body[:1000].lower()
                    ):
                        raise AcquisitionError(
                            "robots_unavailable",
                            "robots.txt returned HTML or a challenge; stopped conservatively",
                        )
                    self._robots[origin] = Protego.parse(body)
                else:
                    raise AcquisitionError(
                        "robots_unavailable",
                        f"robots.txt returned HTTP {response.status_code}; stopped conservatively",
                    )
            except AcquisitionError as exc:
                if exc.code == "robots_unavailable":
                    self._robots_errors[origin] = exc
                raise
            finally:
                response.close()
        parser = self._robots[origin]
        if parser is not None:
            agent = self.settings.discovery_user_agent
            if not parser.can_fetch(url, agent):
                raise AcquisitionError("robots_denied", "Disallowed by robots.txt")
            delay = parser.crawl_delay(agent) or 0
            rate = parser.request_rate(agent)
            if rate and rate.requests:
                delay = max(delay, rate.seconds / rate.requests)
            self._delay[parts.hostname or ""] = float(delay)

    def get(self, url: str, *, robots: bool = True) -> requests.Response:
        current = self.policy.check(url)
        robots_origin = (
            urlsplit(current).netloc
            if not robots and self.policy.document_robots(current)
            else None
        )
        visited: set[str] = set()
        for _ in range(6):
            if current in visited:
                raise AcquisitionError(
                    "redirect_loop", "Redirect loop detected", "failed"
                )
            visited.add(current)
            if robots:
                self._check_robots(current)
            response = self._request(current)
            if response.status_code not in {301, 302, 303, 307, 308}:
                # Requests' response.url is also set by the mock HTTP test transport.
                return response
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise AcquisitionError(
                    "redirect", "Redirect lacks a Location header", "failed"
                )
            target = canonical_url(urljoin(current, location))
            # Retain even a refused redirect so failures identify the actual
            # destination. Recording it never authorises fetching that URL.
            self.audit.append(
                {
                    "code": "http_redirect",
                    "url": current,
                    "target_url": target,
                    "http_status": response.status_code,
                    "resource": "document" if robots else "robots",
                    "message": "Normal redirect; target must independently satisfy source and robots policy",
                }
            )
            if not (
                robots_origin
                and urlsplit(target).scheme == "https"
                and urlsplit(target).netloc == robots_origin
            ):
                self.policy.check(target)
            # Same-origin robots redirects may lead to a site's 404 handler.
            # This lookup-only exception never changes the document policy or
            # authorises visiting that handler through a normal page request.
            if current.startswith("https:") and target.startswith("http:"):
                raise AcquisitionError(
                    "insecure_redirect", "HTTPS-to-HTTP redirect requires review"
                )
            if robots:
                # An observed official PDF endpoint may redirect to an exact
                # PDF on another subdomain owned by the same company. Retain
                # that server-published chain; do not grant any other path.
                if (
                    current in self.policy.document_urls
                    and self.policy.owns(current)
                    and self.policy.owns(target)
                ):
                    self.policy = self.policy.endorse_document(target, current)
            current = target
        raise AcquisitionError("redirect_limit", "Too many redirects", "failed")

    def chunks(self, response: requests.Response, limit: int) -> Iterator[bytes]:
        size = 0
        started = self.clock()
        try:
            for chunk in response.iter_content(64 * 1024):
                size += len(chunk)
                if size > limit:
                    raise AcquisitionError(
                        "size_limit", "Response exceeded the configured byte limit"
                    )
                if self.clock() - started > 120:
                    raise AcquisitionError(
                        "transfer_timeout", "Transfer exceeded 120 seconds", "failed"
                    )
                if chunk:
                    yield chunk
        except requests.RequestException as exc:
            raise AcquisitionError("transfer", str(exc)[:300], "failed") from exc

    def read(self, response: requests.Response, limit: int = 2_000_000) -> bytes:
        return b"".join(self.chunks(response, limit))


def require_success(response: requests.Response) -> None:
    if response.status_code in {401, 403, 407}:
        raise AcquisitionError(
            "access_control",
            f"HTTP {response.status_code}; no authentication or anti-bot bypass attempted",
        )
    if response.status_code in {404, 410}:
        raise AcquisitionError(
            "not_found", f"HTTP {response.status_code}", "unavailable"
        )
    if response.status_code != 200:
        raise AcquisitionError("http_error", f"HTTP {response.status_code}", "failed")
