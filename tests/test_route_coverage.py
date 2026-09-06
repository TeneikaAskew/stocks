"""Every registered API route must be reachable by at least one test.

The gap this closes, measured rather than asserted: on `main` at 2026-09-06,
**21 of 98** registered `/api` operations were never requested by any test.
Both endpoints that broke this week were in that 21:

    GET /api/options/{ticker}/{date_str}/levels   500 on every request (#991)
    GET /api/options/dates/{ticker}               9,870 ms query      (#992)

4,253 tests passed over a hard 500. Not because the suite is thin — 253 API
tests cover 77 of 98 operations — but because the hole sat exactly where the
defects were.

Two things live here.

**A guard** (`test_every_route_is_requested_by_some_test`) that reads the
route table from the app's own OpenAPI schema and the request URLs from
`tests/`, and fails when a route has no caller. It has an allow-list, and the
allow-list is empty; adding a route to it should be an argument, not a habit.

**Smoke requests** for the 21, which are what make the guard pass. They are
deliberately shallow: no per-route mocking, no fixture per endpoint. Each
asserts the route *answers* — a status FastAPI produced rather than an
unhandled exception, and a JSON body. That is a low bar, and it is exactly the
bar `/levels` failed: `await` on a function that had become synchronous raised
`TypeError` and returned 500, which any request at all would have caught.

Deeper per-endpoint assertions belong in `test_platform_api.py` next to their
own fixtures. This file's job is that no route is *unrequested*.

Hermetic: no database, no network, no credentials. Endpoints that need Cloud
SQL answer 503 here, which is a pass — the point is that they answer.
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "platform"))

pytest.importorskip("fastapi")


@pytest.fixture(scope="module")
def client():
    """TestClient for the FastAPI app (no live server)."""
    import os

    original_cwd = os.getcwd()
    platform_dir = str(PROJECT_ROOT / "platform")
    if platform_dir not in sys.path:
        sys.path.insert(0, platform_dir)
    os.chdir(platform_dir)

    from starlette.testclient import TestClient
    from api.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    os.chdir(original_cwd)


# ── the route table, from the app itself ────────────────────────────────────

def _registered_operations() -> list[tuple[str, str]]:
    """(METHOD, path) for every /api operation the app actually serves.

    Read from `app.openapi()` rather than `app.routes`: this FastAPI version
    keeps included routers as `_IncludedRouter` objects rather than flattening
    them, so walking `app.routes` finds 8 operations instead of 98. A route
    audit that silently sees 8% of the surface is worse than none, which is
    why this reads the schema the app publishes.
    """
    from api.main import app

    out = []
    for path, ops in app.openapi()["paths"].items():
        if not path.startswith("/api"):
            continue
        for method in ops:
            if method.upper() in {"HEAD", "OPTIONS", "PARAMETERS"}:
                continue
            out.append((method.upper(), path))
    return sorted(out)


def _tested_urls() -> set[str]:
    """Every `/api/...` literal appearing anywhere under `tests/`."""
    urls: set[str] = set()
    for p in (PROJECT_ROOT / "tests").rglob("*.py"):
        for m in re.finditer(r'["\'](/api/[^"\'\s]*)["\']',
                             p.read_text(errors="replace")):
            urls.add(m.group(1).split("?")[0])
    return urls


def _covers(template: str, url: str) -> bool:
    """Does a concrete request URL match a route template?"""
    return re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", template), url) is not None


# A route may sit here only with a reason a reader can check. It is empty, and
# that is the state to keep it in: the two endpoints that broke this week both
# lived in the uncovered set, so "we'll add a test later" has a track record.
COVERAGE_ALLOWLIST: dict[tuple[str, str], str] = {}


def test_every_route_is_requested_by_some_test():
    ops = _registered_operations()
    assert len(ops) > 50, f"only {len(ops)} operations found — did the schema move?"

    urls = _tested_urls()
    uncovered = [
        (m, p) for m, p in ops
        if (m, p) not in COVERAGE_ALLOWLIST
        and not any(_covers(p, u) for u in urls)
    ]
    assert not uncovered, (
        f"{len(uncovered)} of {len(ops)} registered API operations are never "
        f"requested by any test. A handler nothing calls can return 500 on "
        f"every request with the whole suite green — /levels did:\n  "
        + "\n  ".join(f"{m} {p}" for m, p in uncovered)
    )


def test_the_allowlist_is_empty():
    """A separate assertion so shrinking coverage is a visible diff.

    If the guard above ever passes because something was added here rather
    than tested, this fails and names it.
    """
    assert not COVERAGE_ALLOWLIST, (
        "routes exempted from coverage:\n  "
        + "\n  ".join(f"{m} {p} — {why}"
                      for (m, p), why in COVERAGE_ALLOWLIST.items()))


# ── smoke requests: the route answers, rather than raising ──────────────────
#
# A status in this set means FastAPI produced it. 500 means an unhandled
# exception reached the framework, which is what `/levels` did for every
# request while 4,253 tests passed.
ANSWERED = {200, 204, 304, 400, 401, 403, 404, 409, 422, 429, 500, 502, 503}
NOT_A_CRASH = ANSWERED - {500}

GET_SMOKE = [
    "/api/admin/strat-engine/state",
    "/api/admin/structure-brief",
    "/api/analytics/summary/IWM",
    "/api/catalysts/asof/IWM",
    "/api/catalysts/events",
    "/api/catalysts/ticker/IWM",
    "/api/catalysts/types",
    "/api/config/firebase",
    "/api/config/indicators",
    "/api/config/market-hours",
    "/api/earnings/insights/grid",
    "/api/earnings/insights/winners",
    "/api/earnings/ticker/IWM/lean",
    "/api/glossary/gamma",
    "/api/insights/reports/00000000-0000-0000-0000-000000000000",
    "/api/live/avg-volume/IWM",
    "/api/options/dates/IWM",
    "/api/options/IWM/2026-09-04/levels",
]


@pytest.mark.parametrize("url", GET_SMOKE)
def test_get_route_answers(client, url):
    r = client.get(url)
    assert r.status_code in NOT_A_CRASH, (
        f"GET {url} returned {r.status_code}; body: {r.text[:300]}")
    # An error still has to be a JSON envelope the frontend can render, not a
    # stack trace or an empty body.
    assert r.headers.get("content-type", "").startswith("application/json"), (
        f"GET {url} answered {r.status_code} with "
        f"content-type {r.headers.get('content-type')!r}")


def test_options_levels_is_not_a_500(client):
    """Pinned by name as well as by the sweep above.

    This is the route that returned 500 on every request after 69 handlers
    were converted to `def` while `get_gamma_levels` kept
    `await get_options(...)`. Nothing requested it, so nothing noticed.
    """
    r = client.get("/api/options/IWM/2026-09-04/levels")
    assert r.status_code != 500, f"regression: {r.text[:300]}"


def test_options_dates_is_not_a_500(client):
    """The other endpoint from this week's defects (#992)."""
    r = client.get("/api/options/dates/IWM")
    assert r.status_code != 500, f"regression: {r.text[:300]}"


def test_insight_report_by_id_is_503_not_a_bare_500(client):
    """What this file found on its first run.

    `/api/insights/reports/{report_id}` let a `psycopg2.OperationalError`
    reach FastAPI, which answered `500 Internal Server Error` with a plain
    text body. Every other DB-backed handler in that router answers 503 with
    a JSON detail; this one had no test, so nothing noticed.
    """
    r = client.get("/api/insights/reports/00000000-0000-0000-0000-000000000000")
    assert r.status_code != 500, r.text[:300]
    assert r.headers.get("content-type", "").startswith("application/json")


# ── POST routes: a body is required, so these are individual ────────────────

def test_analytics_trade_stats_answers(client):
    r = client.post("/api/analytics/trade-stats", json={"trades": []})
    assert r.status_code in NOT_A_CRASH, r.text[:300]


def test_options_greeks_answers(client):
    r = client.post("/api/options/greeks", json={
        "spot": 200.0, "strike": 205.0, "days_to_expiry": 7,
        "volatility": 0.2, "option_type": "call",
    })
    assert r.status_code in NOT_A_CRASH, r.text[:300]


def test_insights_chat_rejects_an_empty_message(client):
    """Cheapest safe request to this route: it 400s before touching Gemini.

    Requesting it at all is the point — it is a StreamingResponse handler and
    the exemption that used to cover it in the dispatch guard was wrong.
    """
    r = client.post("/api/insights/chat",
                    json={"message": "", "mode": "chat", "ticker": "IWM",
                          "history": []})
    assert r.status_code in NOT_A_CRASH, r.text[:300]
