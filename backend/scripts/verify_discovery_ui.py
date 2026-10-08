"""Optional local browser verification; API/Vite must be running with smoke data.

Run from backend/: .venv/bin/python scripts/verify_discovery_ui.py
Uses the installed Chromium binary; does not install or download one.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    output = Path(__file__).resolve().parents[1] / "storage" / "verification"
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1120}, device_scale_factor=1
        )
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:5173/admin/reports", wait_until="networkidle")
        page.get_by_role("heading", name="Apple Inc.", exact=True).wait_for()
        assert page.locator(".report-run").count() == 5
        assert page.locator(".count-card.processed strong").inner_text() == "5"
        assert page.locator(".count-card.downloaded strong").inner_text() == "2"
        page.screenshot(path=str(output / "report-quality-desktop.png"), full_page=True)
        page.locator(".report-run").first.locator("summary").click()
        assert (
            page.get_by_text(
                "597676e8b48ac45529303abc7ef47425ca62ff4efc3a375962a077a033525f74",
                exact=True,
            ).count()
            == 1
        )
        page.locator(".report-run").first.locator("summary").click()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        )
        page.screenshot(path=str(output / "report-quality-mobile.png"), full_page=True)
        assert errors == [], errors
        browser.close()
    print(f"Desktop/mobile checks passed; no page errors. Screenshots: {output}")


if __name__ == "__main__":
    main()
