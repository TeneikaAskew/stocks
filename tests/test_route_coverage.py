"""Every registered API route must be reachable by at least one test.

The gap this closes, measured rather than asserted: on `main` at 2026-09-06,
**23 of 99** registered `/api` operations were never requested by any test.
Both endpoints that broke this week were in that 23:

    GET /api/options/{ticker}/{date_str}/levels   500 on every request (#991)
    GET /api/options/dates/{ticker}               9,870 ms query      (#992)

4,253 tests passed over a hard 500. Not because the suite is thin — 253 API
tests cover 76 of 99 operations — but because the hole sat exactly where the
defects were.

The first version of this file measured this three ways that were all too
generous, and the corrected numbers are the ones above. It regex-matched every
route template independently (so one request to `/api/options/dates/IWM`
credited `/api/options/{ticker}/{date_str}` too), ignored the HTTP method (so
a tested `GET /api/me/profile` covered `PUT` as well), and counted any `/api`
string literal anywhere under `tests/` — a docstring, an expected value, a
dead helper — as a caller. Codex caught all three. The measurement now walks
the real route table in registration order, resolves each request the way
Starlette dispatches it, and only counts requests the suite actually issues.

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

import ast
import pathlib
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

def _flatten(routes, out):
    """Every real Route, in REGISTRATION ORDER.

    This FastAPI version keeps included routers as `_IncludedRouter` wrappers
    rather than flattening them, so walking `app.routes` naively finds 8
    operations instead of 99. An earlier version of this file did exactly
    that and reported "0 uncovered of 8" — a clean bill of health from an
    audit seeing 8% of the surface, which is worse than no audit.

    Order matters and is preserved: FastAPI dispatches to the FIRST matching
    route, which is why `main.py` says "grid MUST mount before options".
    """
    for r in routes:
        if type(r).__name__ == "_IncludedRouter":
            _flatten(r.original_router.routes, out)
        elif hasattr(r, "path") and hasattr(r, "path_regex"):
            out.append(r)
    return out


def _registered_operations():
    """[(METHOD, path, route)] for every /api operation the app serves."""
    from api.main import app

    out = []
    for route in _flatten(app.routes, []):
        if not route.path.startswith("/api"):
            continue
        for method in sorted((route.methods or set()) - {"HEAD", "OPTIONS"}):
            out.append((method, route.path, route))
    return out


# Attribute names that issue an HTTP request in this suite: `client.get(...)`,
# `page.route(...)` in Playwright-style helpers, `requests.post(...)`.
_REQUEST_VERBS = {"get", "post", "put", "patch", "delete", "head", "options",
                  "request", "route"}


def _requested_operations() -> set[tuple[str, str]]:
    """(METHOD, url) for every request the suite actually ISSUES.

    Parsed from the AST, not by scanning string literals. A URL that appears
    only in a docstring, an expected value, an unused fixture, or a dead
    helper is not a caller, and counting it as one reintroduces the exact
    failure this file exists to catch: a route nobody invokes, with the guard
    green. (Same trap as the handler-name proxy that produced a "80%
    uncovered" headline on #992 — a measurement that is easy to take is not
    the measurement you want.)
    """
    out: set[tuple[str, str]] = set()
    for path in (PROJECT_ROOT / "tests").rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(errors="replace"))
        except SyntaxError:
            continue

        # Module-level `NAME = ["/api/...", ...]`, so a parametrized request
        # (`@parametrize("url", GET_SMOKE)` then `client.get(url)`) is credited
        # for each URL it actually drives. Only literal lists of literal
        # strings at module scope — anything computed is not resolved, and is
        # therefore not counted, which is the safe direction.
        const_lists: dict[str, list[str]] = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            if not isinstance(node.value, (ast.List, ast.Tuple)):
                continue
            values = [e.value for e in node.value.elts
                      if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if values:
                const_lists[target.id] = values

        # `@pytest.mark.parametrize("url", GET_SMOKE)` binds the loop variable
        # to the list, so `client.get(url)` inside that function drives every
        # entry. Resolved per-function, so a `url` name elsewhere is not
        # credited with someone else's list.
        params: dict[int, dict[str, list[str]]] = {}
        for fn_node in ast.walk(tree):
            if not isinstance(fn_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            bound: dict[str, list[str]] = {}
            for dec in fn_node.decorator_list:
                if not (isinstance(dec, ast.Call) and len(dec.args) == 2):
                    continue
                f = dec.func
                if not (isinstance(f, ast.Attribute) and f.attr == "parametrize"):
                    continue
                names, values = dec.args
                if not (isinstance(names, ast.Constant)
                        and isinstance(names.value, str)):
                    continue
                if isinstance(values, ast.Name) and values.id in const_lists:
                    resolved = const_lists[values.id]
                elif isinstance(values, (ast.List, ast.Tuple)):
                    resolved = [e.value for e in values.elts
                                if isinstance(e, ast.Constant)
                                and isinstance(e.value, str)]
                else:
                    continue
                if "," not in names.value and resolved:
                    bound[names.value.strip()] = resolved
            if bound:
                params[id(fn_node)] = bound
                for sub in ast.walk(fn_node):
                    sub._param_scope = bound        # type: ignore[attr-defined]

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            fn = node.func
            if not isinstance(fn, ast.Attribute) or fn.attr not in _REQUEST_VERBS:
                continue
            first = node.args[0]
            scope = getattr(node, "_param_scope", {})
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                urls = [first.value]
            elif isinstance(first, ast.Name) and first.id in scope:
                urls = scope[first.id]
            elif isinstance(first, ast.Name) and first.id in const_lists:
                urls = const_lists[first.id]
            else:
                continue
            for raw in urls:
                url = raw.split("?")[0]
                if not url.startswith("/api"):
                    continue
                if fn.attr in {"request", "route"}:
                    # `client.request("POST", url)` / a router mock: the verb
                    # is elsewhere, so credit every method on the match.
                    out.add(("*", url))
                else:
                    out.add((fn.attr.upper(), url))
    return out


def _dispatch(method: str, url: str, ops) -> tuple[str, str] | None:
    """Which registered operation does this request actually reach?

    Starlette dispatches to the FIRST route whose pattern matches, so this
    walks in registration order and stops. Regex-matching every template
    independently over-credits: `/api/options/dates/IWM` also matches
    `/api/options/{ticker}/{date_str}`, so one request would mark two
    operations covered and removing the chain endpoint's own tests would
    leave the guard green.
    """
    for m, path, route in ops:
        if method not in ("*", m):
            continue
        if route.path_regex.fullmatch(url):
            return (m, path)
    return None


# A route may sit here only with a reason a reader can check. It is empty, and
# that is the state to keep it in: the two endpoints that broke this week both
# lived in the uncovered set, so "we'll add a test later" has a track record.
COVERAGE_ALLOWLIST: dict[tuple[str, str], str] = {}


def test_every_route_is_requested_by_some_test():
    ops = _registered_operations()
    assert len(ops) > 50, f"only {len(ops)} operations found — did the route table move?"

    covered = set()
    for method, url in _requested_operations():
        hit = _dispatch(method, url, ops)
        if hit is not None:
            covered.add(hit)

    uncovered = [
        (m, p) for m, p, _route in ops
        if (m, p) not in COVERAGE_ALLOWLIST and (m, p) not in covered
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
    "/api/catalysts/snapshot/IWM",
    "/api/movement-statement",
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


def test_insight_report_by_id_is_503_not_a_bare_500(client, monkeypatch):
    """What this file found on its first run.

    `/api/insights/reports/{report_id}` let a `psycopg2.OperationalError`
    reach FastAPI, which answered `500 Internal Server Error` with a plain
    text body. Every other DB-backed handler in that router answers 503 with
    a JSON detail; this one had no test, so nothing noticed.

    The failure is INJECTED rather than relied upon. A first version just
    requested the route and asserted `!= 500`, which passes for the wrong
    reason wherever a database happens to be reachable (404 for the all-zero
    UUID) and quietly stopped being hermetic. Same shape as the ticker-info
    test on #991 that passed because the test supplied what production
    lacked.
    """
    from api.routers import insights as insights_module

    def boom(_report_id):
        raise RuntimeError("connection to server at 127.0.0.1:5432 refused")

    monkeypatch.setattr(insights_module, "_fetch_report_by_id", boom)
    r = client.get("/api/insights/reports/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 503, r.text[:300]
    assert r.headers.get("content-type", "").startswith("application/json")
    assert "report lookup failed" in r.json()["detail"]


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
