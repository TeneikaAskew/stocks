"""Every registered API operation is requested here, and none of them crashes.

The gap this closes, measured rather than asserted: on `main` at 2026-09-06,
**23 of 99** registered `/api` operations were never requested by any test.
Both endpoints that broke this week were in that 23:

    GET /api/options/{ticker}/{date_str}/levels   500 on every request (#991)
    GET /api/options/dates/{ticker}               9,870 ms query      (#992)

4,253 tests passed over a hard 500. Not because the suite is thin, but because
the hole sat exactly where the defects were.


What this file proves, and what it does not
-------------------------------------------

It proves that **every operation the app registers is requested from this
file**, and that each one answers with a status FastAPI produced and a JSON
body, rather than an unhandled exception. That is a low bar, and it is exactly
the bar `/levels` failed.

It does not prove the answers are *correct*. Per-endpoint assertions belong in
`test_platform_api.py` next to their own fixtures.


Three earlier versions of this file measured coverage in ways that were all
too generous, and each was wrong in a way worth recording because the mistake
is easy to repeat:

1. It walked `app.routes` naively. This FastAPI version keeps included routers
   as `_IncludedRouter` wrappers rather than flattening them, so it found 8
   operations and reported "0 uncovered of 8" — a clean bill of health from an
   audit seeing 8% of the surface.

2. It regex-matched every route template independently, ignored the HTTP
   method, and counted any `/api` string literal anywhere under `tests/` as a
   caller. So one request to `/api/options/dates/IWM` also credited
   `/api/options/{ticker}/{date_str}`, a tested `GET /api/me/profile` covered
   `PUT` as well, and a URL in a docstring counted as a request.

3. It parsed real request calls from the AST instead — better, and still
   wrong. It credited calls inside modules that are **skipped** under the
   default configuration (all of `test_routers_insights_admin.py`, the sole
   coverage for `POST /api/insights/report/{ticker}/refresh` and
   `GET /api/admin/models`) and calls against a test-local stub app rather
   than `api.main.app` (the `/api/me` calls in `test_platform_auth.py`).

The through-line: each version answered "does this URL appear somewhere" when
the question is "does the suite issue this request". So the inventory is no
longer inferred from other files at all. `REQUESTS` below declares one request
per operation and this file issues them. There is nothing left to over-credit,
and `test_every_operation_is_requested` compares the declared table against the
app's real route table in registration order.


The harness, and why it disables the *connection* rather than the helpers
------------------------------------------------------------------------

A request that stops at a pre-handler gate proves nothing about the handler.
`/api/options/IWM/2026-09-04/levels` returned 503 at `_require_cloud_sql()`
before reaching its `await get_options(...)` — the exact line whose regression
this file is named after — so restoring that bug left the guard green. The
same was true of every Cloud-SQL-gated route (503) and every admin route
(401). `no_backend` below opens those gates: the `_CLOUD_SQL` / `_HAS_CLOUD_SQL`
flags are set True and the admin identity is supplied, so the handler bodies
actually run.

With the gates open something has to stand in for the backend, and *what* is
patched decides whether the result means anything. A first version replaced
`query_to_dataframe` and the `gcs_reader` helpers with functions that raise.
That reported **13 hard 500s** — and 11 of them were artifacts. Those helpers
swallow in production (`query_to_dataframe` returns an empty DataFrame,
`list_matching_blobs` returns `[]`; see the fallback audit), so making them
raise did not simulate an outage, it deleted the app's own error handling and
then blamed the app for not having any.

So the harness disables the **connection layer** instead: `get_engine`,
`model_routing.connect`, and `storage.Client` fail the way they fail when the
database and GCS are genuinely unreachable. Every layer above them then
behaves exactly as it does in production — the swallowing helpers still
swallow, the strict ones still raise — and what surfaces is real. That is also
what makes this file hermetic: no socket is opened, so no request here can
reach a database (or write to one) even on a machine that has one configured.

Nine genuine hard 500s were found this way, all of them plain-text
"Internal Server Error" with no JSON envelope for the frontend to render:

    GET  /api/insights/report/{ticker}            OperationalError escaped
    GET  /api/insights/report/{ticker}/history    OperationalError escaped
    GET  /api/insights/reports/{report_id}        OperationalError escaped
    POST /api/insights/report/{ticker}/refresh    OperationalError escaped
    GET  /api/insights/runs/{run_id}              OperationalError escaped
    GET  /api/admin/routes                        OperationalError escaped
    GET  /api/admin/users                         ModuleNotFoundError escaped
    PUT  /api/admin/users/{uid}/roles             ModuleNotFoundError escaped
    PUT  /api/admin/users/{uid}/status            ModuleNotFoundError escaped

All nine are fixed in this change set.
"""
from __future__ import annotations

import dataclasses
import os
import pathlib
import sys
from typing import Any, Optional

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "platform"))

pytest.importorskip("fastapi")


# ── the route table, from the app itself ────────────────────────────────────

def _flatten(routes, out):
    """Every real Route, in REGISTRATION ORDER.

    Order is load-bearing rather than incidental: Starlette dispatches to the
    FIRST matching route, which is why `main.py` says "grid MUST mount before
    options — options has a greedy path".
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


def _dispatch(method: str, url: str, ops) -> Optional[tuple[str, str]]:
    """Which registered operation does this request actually reach?

    Starlette dispatches to the first route whose pattern matches, so this
    walks in registration order and stops there. Regex-matching every template
    independently over-credits: `/api/options/dates/IWM` also matches
    `/api/options/{ticker}/{date_str}`, so one request would mark two
    operations covered.

    Uses Starlette's own compiled `path_regex` rather than a pattern rebuilt
    from the template — a hand-rolled `{param}` -> `[^/]+` happens to match
    these routes but diverges the moment anyone uses a path converter.
    """
    path_only = url.split("?", 1)[0]
    for m, path, route in ops:
        if method != m:
            continue
        if route.path_regex.fullmatch(path_only):
            return (m, path)
    return None


# ── the declared requests ───────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class Req:
    """One request, and what it is expected to answer with no backend.

    `expect` is the status measured against a backend-less instance. It is
    pinned rather than left as "anything but 500" because a change from 404 to
    503, or from 200 to 401, is a contract change someone should have to look
    at. `body_ran=False` marks the requests that stop at FastAPI's own request
    validation and therefore say nothing about the handler; everything else
    entered the endpoint function.
    """
    method: str
    url: str
    expect: int
    json: Optional[dict[str, Any]] = None
    body_ran: bool = True
    note: str = ""

    @property
    def label(self) -> str:
        return f"{self.method} {self.url}"


T = "IWM"
D = "2026-09-04"
UUID0 = "00000000-0000-0000-0000-000000000000"

REQUESTS: list[Req] = [
    # ── live ────────────────────────────────────────────────────────────────
    Req("GET", "/api/live/status", 200),
    Req("GET", f"/api/live/quote/{T}", 503, note="no AV key"),
    Req("GET", f"/api/live/history/{T}", 503, note="no AV key"),
    Req("GET", f"/api/live/avg-volume/{T}", 503, note="no AV key, no DB"),
    Req("POST", "/api/live/indicators", 200, json={"bars": []}),
    Req("POST", "/api/live/signal-series", 422, json={"bars": []},
        note="the handler's own warm-up check, not request validation"),

    # ── options ─────────────────────────────────────────────────────────────
    Req("GET", f"/api/options/{T}/grid", 503),
    Req("GET", f"/api/options/{T}/{D}/grid", 503),
    Req("GET", f"/api/options/{T}/nodes", 503),
    Req("GET", f"/api/options/{T}/{D}/nodes", 503),
    Req("GET", f"/api/options/{T}/grid/timeseries", 503),
    Req("GET", f"/api/options/dates/{T}", 404, note="#992's endpoint"),
    Req("GET", f"/api/options/{T}/{D}", 404),
    Req("GET", f"/api/options/live/{T}/{D}", 503, note="no AV key"),
    Req("POST", "/api/options/greeks", 422, json={"options": [], "spot": 200.0},
        body_ran=False, note="spot_price is required; see the deep test below"),
    Req("GET", f"/api/options/{T}/{D}/levels", 404,
        note="#991's endpoint; see test_levels_actually_awaits_the_chain"),

    # ── playbook / reports ──────────────────────────────────────────────────
    Req("GET", f"/api/playbook/{T}", 502, note="GCS unreachable"),
    Req("GET", f"/api/reports/list/{T}", 404,
        note="404 not 502: list_matching_blobs swallows (fallback backlog)"),
    Req("GET", f"/api/reports/{T}/premarket", 404, note="same swallow"),
    Req("POST", "/api/playbook/evaluate", 422, json={"snapshot": {}},
        body_ran=False),

    # ── backtest / style ────────────────────────────────────────────────────
    Req("GET", f"/api/backtest/results/{T}", 404, note="same swallow"),
    Req("GET", f"/api/backtest/equity/{T}", 404, note="same swallow"),
    Req("GET", f"/api/backtest/all/{T}", 404, note="same swallow"),
    Req("POST", "/api/backtest/replay-trades", 422,
        json={"ticker": T, "trades": []},
        note="the handler's own check for trade_ids/session_id"),
    Req("POST", "/api/style/mine-and-validate", 200, json={"ticker": T}),

    # ── signals ─────────────────────────────────────────────────────────────
    Req("GET", f"/api/signals/{T}", 200),
    Req("GET", f"/api/signals/{T}/similar?direction=CALL&rsi=50&stoch_k=50"
               "&atr_pct=1.0&score=5.0", 200),

    # ── insights ────────────────────────────────────────────────────────────
    Req("GET", "/api/insights/ticker/search?keywords=russell", 200),
    Req("GET", f"/api/insights/ticker/{T}/info", 404,
        note="deterministic miss: the on-disk cache is redirected to tmp"),
    Req("GET", f"/api/insights/ticker/{T}/quote", 404),
    Req("GET", f"/api/insights/ticker/{T}/peers", 200),
    Req("POST", "/api/insights/watchlist/add", 503, json={"ticker": T}),
    Req("DELETE", f"/api/insights/watchlist/{T}", 503),
    Req("GET", "/api/insights/watchlist", 200),
    Req("GET", f"/api/insights/report/{T}", 503, note="was a bare 500"),
    Req("GET", f"/api/insights/report/{T}/history", 503, note="was a bare 500"),
    Req("GET", f"/api/insights/reports/{UUID0}", 503, note="was a bare 500"),
    Req("POST", f"/api/insights/report/{T}/refresh", 503, json={},
        note="was a bare 500; only covered by a SKIPPED module before"),
    Req("GET", f"/api/insights/runs/{UUID0}", 503, note="was a bare 500"),
    Req("POST", "/api/insights/chat", 400, json={"message": ""},
        note="rejects an empty message before touching Gemini"),

    # ── journal ─────────────────────────────────────────────────────────────
    Req("GET", f"/api/journal/trades/{T}", 200),
    Req("GET", f"/api/journal/examples/{T}", 200),
    Req("POST", "/api/journal/trades", 200,
        json={"ticker": T, "direction": "CALL", "entry_date": D,
              "entry_time": "10:00", "entry_price": 200.0}),
    Req("PATCH", f"/api/journal/trades/{UUID0}", 404,
        json={"exit_date": D, "exit_time": "11:00", "exit_price": 201.0}),
    Req("DELETE", f"/api/journal/trades/{UUID0}", 200),
    Req("GET", f"/api/journal/seed/{T}?date={D}", 503),
    Req("POST", f"/api/journal/export/{T}", 200, json={"trades": []}),
    Req("POST", "/api/journal/import/preview", 422, json={"broker": "generic"},
        body_ran=False),
    Req("POST", "/api/journal/import/commit", 422,
        json={"broker": "schwab", "trades": []},
        note="the handler's own broker allow-list"),

    # ── dashboard / movement ────────────────────────────────────────────────
    Req("GET", f"/api/dashboard/brief/{T}", 200),
    Req("GET", f"/api/movement-statement?ticker={T}", 404),

    # ── catalysts ───────────────────────────────────────────────────────────
    Req("GET", "/api/catalysts/events", 200),
    Req("GET", f"/api/catalysts/ticker/{T}", 200),
    Req("GET", f"/api/catalysts/snapshot/{T}", 200),
    Req("GET", f"/api/catalysts/asof/{T}", 200),
    Req("GET", "/api/catalysts/types", 200),

    # ── admin ───────────────────────────────────────────────────────────────
    Req("GET", "/api/admin/routes", 503, note="was a bare 500"),
    Req("PUT", "/api/admin/routes/analyst", 400,
        json={"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        note="the handler's own adapter check runs before any DB access"),
    Req("GET", "/api/admin/models", 200),
    Req("GET", "/api/admin/structure-brief", 200),
    Req("GET", "/api/admin/strat-engine/state", 200),
    Req("POST", "/api/admin/strat-engine/predict", 400,
        json={"ticker": T, "timeframe": "1d"},
        note="the handler's own timeframe check"),
    Req("POST", "/api/admin/strat-engine/structure-continuation", 404,
        json={"ticker": T, "timeframe": "15m"}),
    Req("GET", "/api/admin/users", 503, note="was a bare 500"),
    Req("PUT", f"/api/admin/users/test-uid/roles", 503, json={"roles": []},
        note="was a bare 500"),
    Req("PUT", f"/api/admin/users/test-uid/status", 503,
        json={"disabled": False}, note="was a bare 500"),
    Req("GET", "/api/admin/data-sources", 200),
    Req("POST", "/api/admin/data-sources/market_data_daily/refresh", 503),

    # ── analytics ───────────────────────────────────────────────────────────
    Req("POST", "/api/analytics/trade-stats", 200, json={"trades": []}),
    Req("GET", f"/api/analytics/summary/{T}", 200),

    # ── config / health / glossary ──────────────────────────────────────────
    Req("GET", "/api/config/firebase", 200),
    Req("GET", "/api/config/indicators", 200),
    Req("GET", "/api/config/market-hours", 200),
    Req("GET", "/api/health/freshness", 200),
    Req("GET", "/api/glossary/gamma", 200),
    Req("GET", "/api/health", 200),
    Req("GET", "/api/me", 200),

    # ── magnitude ───────────────────────────────────────────────────────────
    Req("GET", f"/api/magnitude/{T}/1d/latest", 404),
    Req("GET", f"/api/magnitude/{T}/1d/at/2026-09-04T14:30:00Z", 404),

    # ── earnings ────────────────────────────────────────────────────────────
    Req("GET", "/api/earnings/upcoming", 503),
    Req("GET", f"/api/earnings/history/{T}", 503),
    Req("GET", f"/api/earnings/event/{T}/{D}", 503),
    Req("GET", "/api/earnings/lean", 503),
    Req("GET", f"/api/earnings/ticker/{T}/lean", 503),
    Req("GET", "/api/earnings/insights/grid", 503),
    Req("GET", "/api/earnings/insights/winners", 503),
    Req("GET", "/api/earnings/calibration", 503),
    Req("GET", "/api/earnings/health/ping", 200),

    # ── waitlist / me ───────────────────────────────────────────────────────
    Req("POST", "/api/waitlist", 503,
        json={"email": "route-coverage@example.test"},
        note="hermetic: the write cannot reach a database, see no_backend"),
    Req("GET", "/api/me/preferences", 503),
    Req("PUT", "/api/me/preferences", 422, json={"preferences": {}},
        body_ran=False),
    Req("GET", "/api/me/profile", 503),
    Req("PUT", "/api/me/profile", 503, json={"display_name": "rc"}),

    # ── market ──────────────────────────────────────────────────────────────
    Req("GET", f"/api/market/dates/{T}", 200),
    Req("GET", f"/api/market/data/{T}/{D}", 404),
    Req("GET", f"/api/market/reference/{T}/{D}", 404),
    Req("GET", f"/api/market/coverage?symbols={T}", 503),
    Req("GET", "/api/market/sectors", 503),
    Req("GET", "/api/market/most-active", 503),
]


# ── the harness ─────────────────────────────────────────────────────────────

class _BackendDown(RuntimeError):
    """Raised where a socket to Cloud SQL or GCS would be opened."""


def _no_connection(*_a, **_k):
    raise _BackendDown("backend disabled by the route-coverage harness")


_GATE_FLAGS = ("_HAS_CLOUD_SQL", "_CLOUD_SQL")


def _clear_process_caches() -> None:
    """Empty every module-level response cache before the sweep runs.

    These caches live on the module, not on the app, so they outlive a
    `TestClient` and are shared with every other test file in the session.
    `test_market_sectors.py` leaves a canned payload in
    `main._SECTORS_CACHE`, and `GET /api/market/sectors` then answered 200
    here instead of the 503 an unreachable database produces — passing alone
    and failing in the full suite, which is the worst way for a test to be
    wrong.

    A pinned status is only meaningful if the state behind it is this file's
    own. Clearing is also the honest direction: a cache hit skips the handler
    entirely, so a stale entry would mean an operation is inventoried without
    executing any of the code it is supposed to cover.
    """
    for name, module in list(sys.modules.items()):
        if not name.startswith("api."):
            continue
        for attr in dir(module):
            if not attr.endswith("_CACHE"):
                continue
            cache = getattr(module, attr, None)
            if hasattr(cache, "clear"):
                try:
                    cache.clear()
                except Exception:            # pragma: no cover - defensive
                    pass
    import api.routers.health as health

    health._cache_value = None
    health._cache_expires_at = 0.0


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """TestClient for the real app, with the pre-handler gates opened.

    Four things happen here and each is load-bearing:

    * `os.chdir` into `platform/`, restored in a `finally`. Without the
      `finally`, an import error inside `api.main` left pytest in `platform/`
      for every test collected afterwards, turning one setup failure into
      unrelated cascading failures.
    * the connection layer is disabled, so nothing here opens a socket. This
      is what makes the file hermetic even on a machine with a database
      configured, which matters because the table above includes writes.
    * the `_CLOUD_SQL` / `_HAS_CLOUD_SQL` gates are set True and an admin
      identity is supplied, so requests reach the handler bodies instead of
      stopping at `_require_cloud_sql()` or `_require_admin()`.
    * the journal's two write targets are redirected into a tmp directory.
      Opening the gates is what made this necessary: `POST /api/journal/trades`
      and `POST /api/journal/export/{ticker}` now reach their handlers and
      succeed, and unredirected they would write `data/journal/iwm_journal.json`
      and `data/signals/iwm_trade_tracker.csv` into the repository — dirtying
      the tree and handing the journal tests a file this one wrote.
    """
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    original_cwd = os.getcwd()
    platform_dir = str(PROJECT_ROOT / "platform")
    if platform_dir not in sys.path:
        sys.path.insert(0, platform_dir)
    os.chdir(platform_dir)
    try:
        from starlette.testclient import TestClient

        import gcp.database as database
        from lib.agents import model_routing

        mp.setattr(database, "get_engine", _no_connection)
        mp.setattr(model_routing, "connect", _no_connection)
        mp.setattr(model_routing, "_get_connector", _no_connection, raising=False)

        from api.main import app

        # Names bound at import time in a router's own namespace do not see
        # the patch above, so patch them where they are looked up.
        for name, module in list(sys.modules.items()):
            if not name.startswith("api."):
                continue
            for attr in ("get_engine", "connect", "_get_connector"):
                if callable(getattr(module, attr, None)):
                    mp.setattr(module, attr, _no_connection, raising=False)
            for flag in _GATE_FLAGS:
                if isinstance(getattr(module, flag, None), bool):
                    mp.setattr(module, flag, True, raising=False)

        import api.gcs_reader as gcs_reader

        mp.setattr(gcs_reader, "_get_client", _no_connection)

        import api.routers.admin as admin

        mp.setattr(admin, "current_user_email", lambda _request: "admin@example.test")
        mp.setattr(admin, "is_admin_email", lambda _email: True)

        import api.routers.journal as journal

        scratch = tmp_path_factory.mktemp("route-coverage")
        mp.setattr(journal, "LOCAL_JOURNAL_DIR", scratch / "journal")
        mp.setattr(journal, "SIGNALS_DIR", scratch / "signals")

        # Same reason, one layer down. `GET /api/insights/ticker/{ticker}/info`
        # reads lib/ticker_info's on-disk cache and WRITES to it, so the first
        # request creates `data/ticker_info.json` and every later run answers
        # 200 from what an earlier run left there. That is how this file passed
        # locally and failed in CI on a fresh checkout: 200 against a cache my
        # own probe had written, 404 on a machine that had never run it. The
        # environment was answering, not the code.
        import lib.ticker_info as ticker_info

        mp.setattr(ticker_info, "_LOCAL_CACHE_PATH", scratch / "ticker_info.json")

        _clear_process_caches()

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        # Clear again on the way out. The sweep populates the same
        # process-wide caches it cleared on the way in, and leaving a response
        # this file produced (under an admin identity, with the Cloud SQL
        # gates forced open) in a cache another test file reads would export
        # this file's harness to the rest of the suite.
        _clear_process_caches()
        mp.undo()
        os.chdir(original_cwd)


# ── coverage: the declared table against the real route table ───────────────

# A route may sit here only with a reason a reader can check. It is empty, and
# that is the state to keep it in: the two endpoints that broke this week both
# lived in the uncovered set, so "we'll add a test later" has a track record.
COVERAGE_ALLOWLIST: dict[tuple[str, str], str] = {}


def test_the_route_table_is_not_truncated(client):
    """Guards the "0 uncovered of 8" failure mode.

    An earlier version walked `app.routes` without unwrapping `_IncludedRouter`
    and found 8 operations. Every assertion below passed, over 8% of the app.
    """
    ops = _registered_operations()
    assert len(ops) > 50, (
        f"only {len(ops)} operations found — did the route table move? "
        "A truncated table makes every coverage assertion here vacuous.")


def test_every_operation_is_requested(client):
    ops = _registered_operations()
    requested = set()
    for req in REQUESTS:
        hit = _dispatch(req.method, req.url, ops)
        if hit is not None:
            requested.add(hit)

    uncovered = [
        (m, p) for m, p, _route in ops
        if (m, p) not in COVERAGE_ALLOWLIST and (m, p) not in requested
    ]
    assert not uncovered, (
        f"{len(uncovered)} of {len(ops)} registered API operations have no "
        f"request in REQUESTS. A handler nothing calls can return 500 on every "
        f"request with the whole suite green — /levels did:\n  "
        + "\n  ".join(f"{m} {p}" for m, p in uncovered))


def test_every_declared_request_reaches_an_operation(client):
    """The other direction: no entry in the table is dead.

    A renamed route would otherwise leave its old URL in `REQUESTS`, still
    requested, still green, and covering nothing.
    """
    ops = _registered_operations()
    stale = [r.label for r in REQUESTS if _dispatch(r.method, r.url, ops) is None]
    assert not stale, (
        "declared requests that match no registered operation:\n  "
        + "\n  ".join(stale))


def test_no_two_requests_cover_the_same_operation(client):
    """Keeps the table a one-to-one inventory rather than a pile.

    Two entries hitting one operation means some other operation is being
    covered by nothing while the count still looks right.
    """
    ops = _registered_operations()
    seen: dict[tuple[str, str], str] = {}
    dupes = []
    for req in REQUESTS:
        hit = _dispatch(req.method, req.url, ops)
        if hit is None:
            continue
        if hit in seen:
            dupes.append(f"{hit[0]} {hit[1]}: {seen[hit]} and {req.label}")
        seen[hit] = req.label
    assert not dupes, "operations covered twice:\n  " + "\n  ".join(dupes)


def test_the_allowlist_is_empty():
    """A separate assertion so shrinking coverage is a visible diff."""
    assert not COVERAGE_ALLOWLIST, (
        "routes exempted from coverage:\n  "
        + "\n  ".join(f"{m} {p} — {why}"
                      for (m, p), why in COVERAGE_ALLOWLIST.items()))


# ── every operation answers, rather than raising ────────────────────────────

# A status in this set means FastAPI produced it. 500 means an unhandled
# exception reached the framework, which is what `/levels` did for every
# request while 4,253 tests passed.
ANSWERED = {200, 204, 304, 400, 401, 403, 404, 409, 422, 429, 500, 502, 503}
NOT_A_CRASH = ANSWERED - {500}


@pytest.mark.parametrize("req", REQUESTS, ids=lambda r: r.label)
def test_operation_answers(client, req: Req):
    r = client.request(req.method, req.url, json=req.json)

    assert r.status_code in NOT_A_CRASH, (
        f"{req.label} returned {r.status_code}. A 500 here is an unhandled "
        f"exception reaching FastAPI, not an error the frontend can render.\n"
        f"body: {r.text[:400]}")

    # An error still has to be a JSON envelope, not a stack trace or a bare
    # "Internal Server Error" string. The nine handlers this file fixed all
    # answered `text/plain` before.
    assert r.headers.get("content-type", "").startswith("application/json"), (
        f"{req.label} answered {r.status_code} with content-type "
        f"{r.headers.get('content-type')!r}")

    assert r.status_code == req.expect, (
        f"{req.label} answered {r.status_code}, the table says {req.expect}. "
        f"Either this is a regression or the contract changed and the table "
        f"needs updating — both deserve a look.\nbody: {r.text[:400]}")


def test_most_requests_reach_the_handler(client):
    """The file states how much of itself is real, and holds itself to it.

    `body_ran=False` marks a request stopped by FastAPI's own body validation,
    which says nothing about the handler behind it. Those are the honest
    exceptions and they are meant to stay few: a table that drifted to mostly
    422s would still report "every operation requested" while executing almost
    no application code, which is the shape of over-claim this whole file
    exists to avoid.
    """
    shallow = [r.label for r in REQUESTS if not r.body_ran]
    assert len(shallow) <= 5, (
        f"{len(shallow)} of {len(REQUESTS)} requests stop at request "
        f"validation:\n  " + "\n  ".join(shallow))


# ── deep tests: the specific regressions, pinned by name ────────────────────

def test_levels_actually_awaits_the_chain(client, monkeypatch):
    """The regression this file is named after, tested where it lives.

    `/api/options/{ticker}/{date_str}/levels` returned 500 on every request
    after 69 handlers were converted to `def` while `get_gamma_levels` kept
    `await get_options(...)`. Nothing requested it, so nothing noticed.

    Two gates stand between a request and that `await`, and both had to be
    opened before this test meant anything:

    1. `_require_cloud_sql()` answers 503 two lines earlier when no database
       is configured. The `client` fixture opens that.
    2. With the gate open but no data, `get_options` raises `HTTPException`
       404 — and `await f(...)` evaluates `f(...)` FIRST, so a raising call
       never reaches the await at all. A version of this test asserted that
       404 and claimed it proved the await had run. It did not: making
       `get_options` synchronous left it green, which is the same failure the
       whole file is about. That was caught by trying the regression rather
       than reasoning about it.

    So the chain query is stubbed with a canned frame, `get_options` returns
    normally, and the await is the only thing left between that and the 200
    asserted here. Against a synchronous `get_options` this raises
    `TypeError: object dict can't be used in 'await' expression` and answers
    500 — verified by editing the `async` off and re-running.
    """
    import pandas as pd

    from api.routers import options as options_module

    strikes = [195.0, 200.0, 205.0, 210.0]
    chain = pd.DataFrame([
        {
            "contract_symbol": f"IWM260904{t[0]}{int(k * 1000):08d}",
            "expiration": "2026-09-19", "strike": k, "option_type": t,
            "bid": 1.0, "ask": 1.2, "mark": 1.1, "last_price": 1.1,
            "volume": 100, "open_interest": 500,
            "implied_volatility": 0.2, "delta": d, "gamma": 0.01,
            "theta": -0.05, "vega": 0.10, "rho": 0.01,
            "snapshot_ts": pd.Timestamp("2026-09-04T20:00:00Z"),
        }
        for k in strikes
        for t, d in (("call", 0.5), ("put", -0.5))
    ])

    monkeypatch.setattr(options_module, "query_to_dataframe",
                        lambda _sql, _params=None: chain)
    monkeypatch.setattr(options_module, "_CHAIN_CACHE", {})

    r = client.get(f"/api/options/{T}/{D}/levels")
    assert r.status_code == 200, (
        "the levels handler did not complete. A 500 here with "
        "\"can't be used in 'await' expression\" is the #991 regression: "
        f"get_options is no longer a coroutine.\nbody: {r.text[:400]}")
    body = r.json()
    assert body["chain_size"] == len(chain), (
        "the handler answered without the chain get_options returned — "
        f"chain_size={body.get('chain_size')}, expected {len(chain)}")


def test_insight_report_lookups_are_503_not_a_bare_500(client, monkeypatch):
    """The five DB-backed insights handlers, with the failure injected.

    Each let a `psycopg2.OperationalError` reach FastAPI, which answered
    `500 Internal Server Error` with a plain-text body. Every other DB-backed
    router in this app answers 503 with a JSON detail.

    The failure is INJECTED rather than relied upon. An earlier version just
    requested one of these and asserted `!= 500`, which passes for the wrong
    reason wherever a database happens to be reachable, and quietly stopped
    being hermetic. Same shape as the ticker-info test on #991 that passed
    because the test supplied what production lacked.
    """
    from api.routers import insights as insights_module

    def boom(*_a, **_k):
        raise RuntimeError("connection to server at 127.0.0.1:5432 refused")

    for name in ("_fetch_latest_report", "_fetch_report_history",
                 "_fetch_report_by_id", "_insert_run", "_fetch_run"):
        monkeypatch.setattr(insights_module, name, boom)

    for method, url in [
        ("GET", f"/api/insights/report/{T}"),
        ("GET", f"/api/insights/report/{T}/history"),
        ("GET", f"/api/insights/reports/{UUID0}"),
        ("POST", f"/api/insights/report/{T}/refresh"),
        ("GET", f"/api/insights/runs/{UUID0}"),
    ]:
        r = client.request(method, url, json={} if method == "POST" else None)
        assert r.status_code == 503, f"{method} {url}: {r.text[:300]}"
        assert r.headers["content-type"].startswith("application/json")
        assert "RuntimeError" in r.json()["detail"], r.text[:300]


def test_admin_answers_503_when_firebase_is_unavailable(client):
    """`_fb_auth()` raised ModuleNotFoundError from outside every try block.

    The three admin user routes each guard the firebase *call* and answer 503,
    but the SDK import and initialization sat before that guard, so an
    instance without `firebase-admin` or without ADC answered a bare 500 on
    all three. This environment has neither, which is why the assertion below
    needs no injection.
    """
    for method, url, body in [
        ("GET", "/api/admin/users", None),
        ("PUT", "/api/admin/users/test-uid/roles", {"roles": []}),
        ("PUT", "/api/admin/users/test-uid/status", {"disabled": False}),
    ]:
        r = client.request(method, url, json=body)
        assert r.status_code == 503, f"{method} {url}: {r.text[:300]}"
        assert r.json()["detail"] == "user directory temporarily unavailable"


def test_options_dates_is_not_a_500(client):
    """The other endpoint from this week's defects (#992)."""
    r = client.get(f"/api/options/dates/{T}")
    assert r.status_code == 404, r.text[:300]
