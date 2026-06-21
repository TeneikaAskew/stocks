"""
End-to-end Playwright tests for static web applications.

Tests the static web frontends by spinning up a local HTTP server for each:
  - success-report-site  (port 8102)
  - website              (port 8104)

The legacy options-heatseeker static app was retired in #255 (cutover
to FastAPI under platform/) — its directory no longer exists.

Run these separately from the unit suite:
  pytest tests/test_e2e.py --headed       # visible browser
  pytest tests/test_e2e.py               # headless (CI)
"""

import http.server
import functools
import threading
import time
from pathlib import Path

import pytest

# These tests need the pytest-playwright plugin (provides the `page`
# fixture) and its browser binaries. CI's e2e job installs them; without
# the plugin, skip the whole module cleanly rather than erroring every
# test with "fixture 'page' not found".
pytest.importorskip("pytest_playwright")

# ---------------------------------------------------------------------------
# Repo root and app paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
APPS = {
    "success_report": REPO_ROOT / "success-report-site",
    "website": REPO_ROOT / "website",
}
PORTS = {
    "success_report": 8102,
    "website": 8104,
}


# ---------------------------------------------------------------------------
# Session-scoped HTTP server factory
# ---------------------------------------------------------------------------

def _start_server(directory: Path, port: int) -> http.server.HTTPServer:
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(directory),
    )
    # Suppress noisy access logs in test output
    handler.log_message = lambda *a: None  # type: ignore[method-assign]
    server = http.server.HTTPServer(("localhost", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


@pytest.fixture(scope="session")
def servers():
    """Start one HTTP server per web app for the whole test session."""
    active = {}
    for name, directory in APPS.items():
        if directory.exists():
            active[name] = _start_server(directory, PORTS[name])
    time.sleep(0.2)  # brief settle
    yield active
    for srv in active.values():
        srv.shutdown()


def url(name: str, path: str = "") -> str:
    return f"http://localhost:{PORTS[name]}/{path}"


# ---------------------------------------------------------------------------
# Success Report Site tests
# ---------------------------------------------------------------------------

class TestSuccessReportSite:
    """Smoke tests for success-report-site/index.html."""

    def test_page_loads(self, page, servers):
        page.goto(url("success_report"))
        page.wait_for_load_state("domcontentloaded")
        assert page.locator("body").is_visible()

    def test_tab_buttons_rendered(self, page, servers):
        page.goto(url("success_report"))
        page.wait_for_load_state("domcontentloaded")
        tabs = page.locator(".tab-btn")
        assert tabs.count() >= 4  # Overview, Multi-Day, Indicators, Earnings...

    def test_overview_tab_content_present(self, page, servers):
        page.goto(url("success_report"))
        page.wait_for_load_state("domcontentloaded")
        assert page.locator("#overview").count() == 1

    def test_metric_displays_present(self, page, servers):
        page.goto(url("success_report"))
        page.wait_for_load_state("domcontentloaded")
        for metric_id in ["#hitRate", "#profitableRate", "#avgRiskReward", "#avgDaysToHit"]:
            assert page.locator(metric_id).count() == 1, f"Missing metric: {metric_id}"

    def test_refresh_button_present(self, page, servers):
        page.goto(url("success_report"))
        page.wait_for_load_state("domcontentloaded")
        assert page.locator("#refreshData").count() == 1

    def test_tab_switching_works(self, page, servers):
        page.goto(url("success_report"))
        page.wait_for_load_state("domcontentloaded")
        tabs = page.locator(".tab-btn")
        if tabs.count() >= 2:
            tabs.nth(1).click()
            # Page should not crash after clicking second tab
            page.wait_for_timeout(300)
            assert page.locator("body").is_visible()

    def test_no_fatal_js_errors(self, page, servers):
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url("success_report"))
        page.wait_for_load_state("domcontentloaded")
        fatal = [e for e in errors if "SyntaxError" in e or "ReferenceError" in e]
        assert fatal == [], f"Fatal JS errors: {fatal}"


# ---------------------------------------------------------------------------
# Trading Dashboard (website) tests
# ---------------------------------------------------------------------------

class TestTradingDashboard:
    """Smoke tests for website/trading-dashboard.html."""

    def test_page_loads(self, page, servers):
        page.goto(url("website", "trading-dashboard.html"))
        page.wait_for_load_state("domcontentloaded")
        assert page.locator("body").is_visible()

    def test_header_present(self, page, servers):
        page.goto(url("website", "trading-dashboard.html"))
        page.wait_for_load_state("domcontentloaded")
        assert page.locator(".header").count() >= 1

    def test_status_bar_present(self, page, servers):
        page.goto(url("website", "trading-dashboard.html"))
        page.wait_for_load_state("domcontentloaded")
        assert page.locator(".status-bar").count() >= 1

    def test_no_fatal_js_errors(self, page, servers):
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url("website", "trading-dashboard.html"))
        page.wait_for_load_state("domcontentloaded")
        # API auth errors are expected; only catch syntax/reference errors
        fatal = [e for e in errors if "SyntaxError" in e or "ReferenceError" in e]
        assert fatal == [], f"Fatal JS errors: {fatal}"
