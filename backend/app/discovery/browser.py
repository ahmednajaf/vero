"""Explicitly opt-in browser fallback, only called for a clear client-rendered shell."""

from threading import Semaphore

from app.discovery.http import AcquisitionError, SafeHTTP

_browser_gate = Semaphore(1)


def render_page(url: str, http: SafeHTTP) -> str:
    # Keep a multi-company run within the laptop's memory budget.
    with _browser_gate:
        return _render_page(url, http)


def _render_page(url: str, http: SafeHTTP) -> str:
    try:
        from playwright.sync_api import Error, Route, sync_playwright
    except ImportError as exc:
        raise AcquisitionError(
            "browser_missing",
            "Install the optional browser extra and an approved browser binary",
        ) from exc
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=http.settings.discovery_user_agent,
                service_workers="block",
                accept_downloads=False,
            )
            context.route_web_socket("**/*", lambda websocket: websocket.close())

            def route_request(route: Route) -> None:
                request = route.request
                if request.method != "GET" or request.resource_type not in {
                    "document",
                    "script",
                    "xhr",
                    "fetch",
                    "stylesheet",
                }:
                    route.abort()
                    return
                response = None
                try:
                    # Never allow the browser its own network path: every resource
                    # uses the same robots, redirect, host and rate-limit controls.
                    response = http.get(request.url)
                    if response.status_code != 200:
                        route.abort()
                        return
                    body = http.read(response, 4_000_000)
                    route.fulfill(
                        status=200,
                        body=body,
                        content_type=response.headers.get("Content-Type", "text/plain"),
                    )
                except AcquisitionError:
                    route.abort()
                finally:
                    if response is not None:
                        response.close()

            context.route("**/*", route_request)
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                for attempt in range(3):
                    page.wait_for_timeout(1000)
                    try:
                        return page.content()
                    except Error:
                        # A normal client-side navigation may replace the initial
                        # shell. This is not a network/access-control retry.
                        if attempt == 2:
                            raise
                raise AssertionError("unreachable")
            finally:
                context.close()
                browser.close()
    except Error as exc:
        raise AcquisitionError("browser_failed", str(exc)[:300], "failed") from exc
