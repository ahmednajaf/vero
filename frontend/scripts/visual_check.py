"""Local UI smoke/visual checks. In-browser fictional fixtures; never writes a DB.

Run from frontend/: ../backend/.venv/bin/python scripts/visual_check.py
Requires the existing optional Playwright install/browser and a running Vite server.
"""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[2] / "backend/storage/verification/frontend")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    captures: list[str] = []
    checks: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))

        def capture(name: str, label: str = "VISUAL QA · FICTIONAL TEST DATA · NOT REAL COMPANY METRICS") -> None:
            page.evaluate("""label => {
                let note = document.getElementById('visual-qa-label');
                if (!note) { note = document.createElement('div'); note.id='visual-qa-label'; document.body.append(note); }
                note.textContent = label;
                note.style.cssText='position:fixed;bottom:2px;right:6px;z-index:1000;background:#fff7d7;color:#765c2b;padding:3px 7px;font:9px sans-serif;pointer-events:none';
            }""", label)
            page.screenshot(path=str(args.output / name), full_page=True)
            captures.append(name)
            overflow = page.evaluate("""() => document.documentElement.scrollWidth > window.innerWidth ? [...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > window.innerWidth).map(e => ({tag:e.tagName, class:e.className?.toString(), right:e.getBoundingClientRect().right, position:getComputedStyle(e).position})).slice(0,30) : []""")
            assert not overflow, f"Page overflow: {name}: {overflow}"

        page.goto(args.url)
        expect(page.get_by_role("heading", level=1)).to_be_visible()
        # This initial view is the actual local connection state, not a mock.
        page.get_by_text("Loading source-backed records…").wait_for(state="hidden")
        capture("actual-local-state-desktop.png", "LOCAL CONNECTION STATE · NO FIXTURE INJECTION")
        fixtures = page.evaluate("""async () => {
            const fixture = await import('/src/tests/benchmarkFixtures.ts');
            return {companies: fixture.companies, benchmarks: fixture.fixtureBenchmarks()};
        }""")

        def fixture_route(route):
            if "/api/companies?" in route.request.url:
                route.fulfill(json={"items": fixtures["companies"], "total": 7, "page": 1, "page_size": 100, "total_pages": 1})
            elif "/api/benchmarks?" in route.request.url:
                route.fulfill(json=fixtures["benchmarks"])
            else:
                route.fulfill(status=404, json={"detail": "No fixture for this endpoint"})

        page.route("**/api/**", fixture_route)
        page.reload()
        expect(page.get_by_text("Data connected", exact=True)).to_be_visible()
        capture("fixture-overview-desktop.png")
        navigation = page.get_by_role("navigation", name="Main navigation")
        navigation.get_by_role("link", name="Companies", exact=True).click()
        page.get_by_role("textbox", name="Search companies").fill("Aster")
        expect(page.get_by_role("table").get_by_text("Boreal Systems")).to_have_count(0)
        page.get_by_role("button", name="Clear search").click()
        page.get_by_role("combobox", name="Sector", exact=True).select_option("Technology")
        expect(page.get_by_role("table").get_by_text("Granite Energy")).to_have_count(0)
        capture("fixture-companies-desktop.png")
        checks.append("Search and sector filter")
        for name in ["Aster Systems", "Boreal Systems"]:
            page.get_by_role("checkbox", name=f"Compare {name}", exact=True).check()
        page.get_by_role("link", name="Compare companies", exact=True).click()
        expect(page.get_by_role("region", name="Company comparison table")).to_be_visible()
        expect(page.locator("figure.intel-chart [role=img]")).to_have_count(2)
        capture("fixture-compare-desktop.png")
        checks.append("Comparison table and two rendered grouped charts")
        page.get_by_role("region", name="Company comparison table").get_by_role("link", name="Aster Systems United States").click()
        expect(page.get_by_role("heading", name="Aster Systems", exact=True)).to_be_visible()
        capture("fixture-company-desktop.png")
        trigger = page.get_by_role("button", name="View source: Scope 1 emissions", exact=True)
        trigger.click()
        expect(page.get_by_role("dialog", name="Source evidence")).to_be_visible()
        expect(page.get_by_role("dialog").get_by_text("14000", exact=True)).to_be_visible()
        capture("fixture-source-desktop.png")
        page.keyboard.press("Escape")
        expect(trigger).to_be_focused()
        checks.append("Source drawer fields, Escape and focus restoration")
        for view in ["Race", "Trends", "Methodology"]:
            navigation.get_by_role("link", name=view, exact=True).click()
            if view in {"Race", "Trends"}:
                page.get_by_role("combobox", name=f"{view} sector").select_option("Technology")
            capture(f"fixture-{view.lower()}-desktop.png")
        checks.append("Race, Trends and Methodology navigation")
        page.set_viewport_size({"width": 390, "height": 844})
        for view in ["Overview", "Companies", "Compare", "Race", "Trends", "Methodology"]:
            navigation.get_by_role("link", name=view, exact=True if view != "Compare" else False).click()
            capture(f"fixture-{view.lower()}-mobile.png")
        page.goto(f"{args.url}/companies/{fixtures['companies'][0]['id']}")
        expect(page.get_by_role("heading", name="Aster Systems", exact=True)).to_be_visible()
        capture("fixture-company-mobile.png")
        page.get_by_role("button", name="View source: Scope 1 emissions", exact=True).click()
        expect(page.get_by_role("dialog")).to_be_visible()
        capture("fixture-source-mobile.png")
        page.keyboard.press("Escape")
        checks.append("All six navigation routes, company profile and source drawer at mobile width without page-level overflow")
        assert not errors, errors
        browser.close()
    print(json.dumps({"checks": checks, "browser_errors": errors, "screenshots": captures, "output": str(args.output), "fixture_notice": "All fixture images are explicitly watermarked. No company data was created or changed."}, indent=2))


if __name__ == "__main__":
    main()
