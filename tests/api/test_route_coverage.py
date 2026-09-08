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
swallow, the strict ones still raise — and what surfaces is real.

That is also what makes this file hermetic, and "hermetic" here means every
door rather than the obvious one. Patching `gcs_reader._get_client` alone was
not enough: `routers/admin.py` constructs `storage.Client()` directly, so the
class itself is patched. `firebase_admin.initialize_app()` SUCCEEDS wherever
ADC is configured, after which the admin user routes would reach the real
project and `PUT /users/{uid}/status` could call `update_user`, so
`_ensure_firebase` is patched to raise. `lib.ticker_info` scrapes FinViz on a
cache miss, so its two fetchers are patched, and its on-disk cache — which it
WRITES — is redirected to tmp along with the journal's write targets. No
request in this file opens a socket or leaves a file behind, on any machine,
whatever is configured. That matters because the table below includes writes.

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

# What libpq actually raises for a refused connection (libpq 17, captured
# live). The classifier reads a code-less OperationalError by its message,
# so a harness that raised a bare "refused" would exercise a path
# production never takes.
_REFUSED = 'connection to server at "127.0.0.1", port 5432 failed: Connection refused'


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
    # 503, not 404. #992 replaced the swallowing query helper with the strict
    # one precisely so a database outage stops being reported as "no data
    # ingested, run the fetcher" -- so with no reachable database this is now
    # an explicit unavailable state. The 404 remains the answer when the
    # database ANSWERS and the ticker genuinely has no snapshots.
    Req("GET", f"/api/options/dates/{T}", 503, note="#992's endpoint"),
    Req("GET", f"/api/options/{T}/{D}", 404),
    Req("GET", f"/api/options/live/{T}/{D}", 503, note="no AV key"),
    Req("POST", "/api/options/greeks", 422, json={"options": [], "spot": 200.0},
        body_ran=False, note="spot_price is required; see the deep test below"),
    Req("GET", f"/api/options/{T}/{D}/levels", 404,
        note="#991's endpoint; see test_levels_actually_awaits_the_chain"),

    # ── playbook / reports ──────────────────────────────────────────────────
    # #1005 moved this handler off GCS onto playbook_cards in Cloud SQL, so
    # the backend-less answer changed from 502 (GCS unreachable) to 503 at
    # the `is_cloud_sql_configured()` gate. That gate is the first thing the
    # handler does, so this row proves the route is wired and little else;
    # the freshness contract underneath it (stale refusal, the age boundary,
    # 404 on no rows) is covered by tests/api/test_playbook_evaluate.py.
    Req("GET", f"/api/playbook/{T}", 503,
        note="Cloud SQL not configured; deep paths in test_playbook_evaluate.py"),
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
    Req("PUT", "/api/admin/routes/analyst", 503,
        json={"provider": "vertex", "model": "gemini-2.5-flash"},
        note="a REAL provider/model, so it reaches set_route's DB write; "
             "an invalid one 400s at adapter validation and covers nothing"),
    Req("GET", "/api/admin/models", 200),
    Req("GET", "/api/admin/structure-brief", 200),
    Req("GET", "/api/admin/strat-engine/state", 200),
    Req("POST", "/api/admin/strat-engine/predict", 503,
        json={"ticker": T, "timeframe": "15m"},
        note="a VALID timeframe, so it reaches get_engine(); '1d' stopped at "
             "the handler's own timeframe check and covered nothing past it"),
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
    # 503 for the same reason as the options twin above: #991 made a
    # configured-but-broken Cloud SQL fail loud rather than fall through to
    # the GCS staging parquets with a 200, which had degraded the answer with
    # nothing visible to the user or the operator.
    Req("GET", f"/api/market/dates/{T}", 503),
    Req("GET", f"/api/market/data/{T}/{D}", 404),
    Req("GET", f"/api/market/reference/{T}/{D}", 404),
    Req("GET", f"/api/market/coverage?symbols={T}", 503),
    Req("GET", "/api/market/sectors", 503),
    Req("GET", "/api/market/most-active", 503),
]


# ── the harness ─────────────────────────────────────────────────────────────

from unittest.mock import MagicMock as _MagicMock


_HEAVY_ML_MODULES = ("lightgbm", "sklearn", "sklearn.calibration",
                     "sklearn.metrics", "joblib", "scipy")


def _reach_predict_backend(monkeypatch):
    """Let the predict/structure-continuation handlers import `strat_pred_serve`
    for THIS test only, so the request reaches `get_engine()` instead of 503ing
    on the missing `lightgbm` import.

    Scoped with `monkeypatch.setitem`, NOT a module-level stub: a permanent
    `sys.modules["lightgbm"]` mock leaks into collection and makes another
    module's `pytest.importorskip("lightgbm")` run against the fake instead of
    skipping (Codex P2 on #999). The stubs are reverted at teardown. We do NOT
    evict `strat_pred_serve` itself: `del sys.modules[name]` drops the entry but
    leaves the parent package's `strat_pred_serve` attribute bound to the old
    object, so the next `import ... as serve` and a callee's `from ... import`
    resolve to two different module instances and a `setattr` patch on one is
    invisible to the other (it silently un-mocked the movement-statement suite).
    """
    for m in _HEAVY_ML_MODULES:
        try:
            __import__(m)
        except Exception:
            parts = m.split(".")
            for i in range(1, len(parts) + 1):
                key = ".".join(parts[:i])
                if key not in sys.modules:
                    monkeypatch.setitem(sys.modules, key, _MagicMock())


class _BackendDown(ConnectionError):
    """Raised where a socket to Cloud SQL or GCS would be opened.

    A `ConnectionError`, not a bare `RuntimeError`, because the handlers now
    ask `lib.infra_errors.is_infrastructure_error` whether a failure is an
    outage or a bug, and a harness that raises something no real outage raises
    would exercise a classification path production never takes. This is the
    same correction as the harness rewrite recorded above: what stands in for
    the backend decides whether any of this means anything (Codex P1 on #999).

    `ConnectionError` is the honest type for both backends -- it is what a
    refused socket to Cloud SQL or to GCS actually surfaces as -- and it is
    what the docstring already claimed this class stood for.
    """


def _no_connection(*_a, **_k):
    raise _BackendDown("backend disabled by the route-coverage harness")


_GATE_FLAGS = ("_HAS_CLOUD_SQL", "_CLOUD_SQL")

# Every variable `gcp.database.is_cloud_sql_configured()` reads, listed from
# that function rather than recalled: it needs DB_USER/DB_PASS/DB_NAME plus one
# of CLOUD_SQL_CONNECTION_NAME or DB_HOST. DB_PORT joins them because
# `_direct_db_url` reads it and a stray value should not reach a URL this
# harness builds.
_DB_ENV = ("DB_USER", "DB_PASS", "DB_NAME", "DB_HOST", "DB_PORT",
           "CLOUD_SQL_CONNECTION_NAME")


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
    # `health` keeps its audit in ONE tuple rebinding (`_cache`), not a
    # value/expiry pair -- deliberately, so a reader cannot observe a fresh
    # deadline over a stale payload. Setting the old `_cache_value` /
    # `_cache_expires_at` names here would create two attributes nothing
    # reads and leave the real cache holding a previous file's audit, which
    # is the silent version of not clearing at all.
    import api.routers.health as health

    health._cache = None


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

        # The app is imported BEFORE the sources are patched, and the order is
        # load-bearing. Patching first meant that when this fixture was the
        # first code to import `api.main`, `routers/insights.py` bound
        # `_no_connection` at import; the module sweep below then recorded THAT
        # as the alias's previous value, so `mp.undo()` restored the stub
        # rather than the real function and every later insights test in the
        # same process saw a harness-injected outage it never asked for
        # (Codex, PR #999). Importing first means every alias's recorded
        # previous value is the real one.
        #
        # Safe because nothing under `api.` opens a connection at import time:
        # the routers bind names and register routes. If that ever changes,
        # this fixture is where it will show up, as a real connection attempt
        # during collection rather than a silent one.
        from api.main import app

        # `GET /api/health/freshness` and `GET /api/admin/data-sources` both
        # run `audit_data_freshness.audit_all()`, and one of its checks --
        # `enrichment_coverage` -- is gated on the WALL-CLOCK HOUR in Eastern
        # time. Inside `_ENRICHMENT_WINDOW_ET` (05:00-12:59 ET) it issues SQL,
        # which under this harness raises and 500s the route; outside it, it
        # returns a "skipped" row, issues nothing, and the route answers 200.
        #
        # So those two rows were pinned to the time of day. CI ran this file
        # at 04:27 ET and passed; the same commit fails at 05:52 ET. Nothing
        # about the code changes -- the suite would simply have started
        # failing on its own for eight hours out of every twenty-four, which
        # is worse than the environment-dependence it was already carrying
        # because it looks like a real regression.
        #
        # The window is emptied so the check always takes its documented
        # skip path. This file asserts that every route ANSWERS; whether the
        # coverage query is correct is a different file's business, and
        # pinning it here would have meant pinning a clock.
        import audit_data_freshness

        mp.setattr(audit_data_freshness, "_ENRICHMENT_WINDOW_ET", (0, 0))

        # Clear the database environment. Two routers gate at REQUEST time
        # rather than at import -- `grid._require_cloud_sql` and
        # `get_playbook` each `from gcp.database import
        # is_cloud_sql_configured` inside the function -- so patching
        # `get_engine` never reached them and their answer came from the
        # developer's shell. Reproduced: with DB_HOST/DB_USER/DB_PASS/DB_NAME
        # exported, the five grid rows and `GET /api/playbook/IWM` all diverge
        # from what this table pins (Codex, PR #999).
        #
        # Clearing the environment rather than patching the predicate, because
        # the predicate is not the only thing that reads these variables and a
        # call site added later would go straight back to the shell. The
        # assertion below is what keeps that true: it fails at setup if a new
        # variable appears that `_DB_ENV` does not name, rather than letting a
        # route quietly answer something else.
        for var in _DB_ENV:
            mp.delenv(var, raising=False)
        assert not database.is_cloud_sql_configured(), (
            "the harness cleared _DB_ENV and a database still reports as "
            "configured — `is_cloud_sql_configured` reads a variable this "
            "list does not name, and the pinned statuses below are now "
            "answering from the environment rather than from the code")

        mp.setattr(database, "get_engine", _no_connection)
        mp.setattr(model_routing, "connect", _no_connection)
        mp.setattr(model_routing, "_get_connector", _no_connection, raising=False)

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
        from google.cloud import storage as gcs

        mp.setattr(gcs_reader, "_get_client", _no_connection)
        # `gcs_reader._get_client` is not the only door. `routers/admin.py`
        # constructs `storage.Client()` DIRECTLY in two places, which
        # `/api/admin/structure-brief` and `/api/admin/strat-engine/state`
        # reach, so on a machine with Application Default Credentials those
        # two requests read the real production bucket. Patching the class
        # itself closes every door at once, including ones added later.
        mp.setattr(gcs, "Client", _no_connection)

        # Same shape, worse consequence. `_fb_auth()` calls
        # `firebase_admin.initialize_app()`, which SUCCEEDS wherever ADC is
        # configured -- and then the three admin user requests below list and
        # look up accounts in the real project, with
        # `PUT /users/{uid}/status` able to call `update_user`. A route
        # sweep must not be able to disable somebody's account because the
        # developer happened to be logged in. The failure is injected rather
        # than assumed absent.
        import api.auth as api_auth

        mp.setattr(api_auth, "_ensure_firebase", _no_connection)

        # `lib.ticker_info` reaches the network on a cache miss:
        # `get_peers` scrapes FinViz, with a screener lookup as fallback.
        # `/api/insights/ticker/{ticker}/peers` calls it unconditionally, so
        # "no socket is opened" was not true of this file until now -- the
        # sweep could block on FinViz being slow and vary with what it
        # returned.
        import lib.ticker_info as ticker_info

        mp.setattr(ticker_info, "_fetch_finviz_peers", lambda _t: None)
        mp.setattr(ticker_info, "_fetch_industry_peers", lambda _t: None)
        # AlphaVantage is the other vendor these routes reach. `/live/quote`,
        # `/live/history` and `/options/live/...` go out over httpx when a key
        # is configured, and ticker search/info/quote go through
        # `fetch_with_retry`. The key is read into a module-level constant at
        # import time, so clearing the environment is not enough on an already
        # imported module -- blank the constants where they are looked up.
        # `api.main` binds its own copy and `_fetch_av_daily_reference` opens
        # an httpx connection with it; its failures are swallowed before the
        # expected 404, so the sweep stayed green while making an external
        # request and the pinned status varied with whether a key was
        # configured (Codex, PR #999). Four modules, not three.
        for mod_name, attr in (("api.main", "AV_API_KEY"),
                               ("api.routers.live", "AV_API_KEY"),
                               ("api.routers.grid", "_AV_API_KEY"),
                               ("api.routers.options", "_AV_API_KEY")):
            mod = sys.modules.get(mod_name)
            if mod is not None and hasattr(mod, attr):
                mp.setattr(mod, attr, "")
        mp.setattr(ticker_info, "_get_av_key",
                   lambda: (_ for _ in ()).throw(KeyError("no AV key in tests")))

        # Benzinga is the third vendor these routes reach. `/catalysts/events`
        # and `/catalysts/ticker/{t}` call `_fetch_live_events` on a cache
        # miss, which hits the Benzinga calendar with a 30 s timeout and, on
        # success, calls `save_catalysts` -- writing
        # `platform/data/catalysts/catalyst_calendar.json`, because this
        # fixture chdirs into `platform/`. So the sweep could spend vendor
        # quota, block on the network, and leave state behind while still
        # returning the expected 200 (Codex, PR #999).
        #
        # Read from the environment at CALL time (`catalysts.py`
        # `_fetch_live_events`), so clearing the variable is enough here --
        # unlike the AV constants above, which are bound at import.
        mp.delenv("BENZINGA_API_KEY", raising=False)

        # Pin the auth mode. It is read from the environment at import time,
        # and under `AUTH_MODE=firebase` the middleware 401s every gated route
        # before its handler runs -- the sweep would fail at `GET
        # /api/live/status` and the pinned statuses would describe a different
        # deployment than the one under test.
        import api.auth as api_auth_mode

        mp.setattr(api_auth_mode, "AUTH_MODE", "open")

        # Feature flags. Both are read from the environment at call time and
        # default OFF, so the table's expectations described whichever
        # deployment the developer's shell happened to describe. Pinned OFF
        # here, which is what the flag-OFF 404 rows assert; the enabled paths
        # get their own requests in
        # `test_the_feature_gated_handlers_survive_a_backend_outage`, because
        # a sweep that only ever sees the 404 marks the operation covered
        # without executing the code that serves users (Codex, PR #999).
        mp.delenv("MOVEMENT_STATEMENT_ENABLED", raising=False)
        mp.delenv("STRUCTURE_CONTINUATION_ENABLED", raising=False)

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
        #
        # In its own `try`, because it is the only fallible step here and it
        # ran FIRST. If setup failed while importing `api.routers.health` --
        # or cache clearing raised for any other reason -- the finalizer
        # exited before `mp.undo()` and `os.chdir()`, leaving the patches and
        # the `platform/` working directory in place for every test collected
        # afterwards: exactly the cascade this `finally` exists to prevent,
        # reached through the finalizer itself (Codex, PR #999).
        #
        # Restoration must not depend on cleanup succeeding, so cleanup is
        # what gets wrapped, not the other way round.
        try:
            _clear_process_caches()
        finally:
            mp.undo()
            os.chdir(original_cwd)

        # `mp.undo()` restores each attribute to whatever it held when
        # `setattr` recorded it -- which is only the real function if the
        # routers had already bound the real function. Patching the sources
        # before importing the app made the recorded value the stub itself,
        # so undo restored the stub and every later insights test in this
        # process saw an outage this file injected (Codex, PR #999). The
        # import above is ordered to prevent that; this is the assertion that
        # says so out loud, because the ordering has no other visible effect.
        leaked = sorted(
            f"{name}.{attr}"
            for name, module in list(sys.modules.items())
            if name.startswith("api.")
            for attr in ("get_engine", "connect", "_get_connector")
            if getattr(module, attr, None) is _no_connection
        )
        assert not leaked, (
            "this harness left its outage stub bound after teardown, so every "
            "later test in this process sees a failure it did not ask for:\n  "
            + "\n  ".join(leaked))


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
# Any success counts: 200 today, and a 201 for a create or a 202 for an
# asynchronous job tomorrow must not fail the crash check when the table
# expects exactly that status -- the exact-status assertion below is what
# pins the contract (Codex P2 on #999). The error side stays a closed list:
# these are the envelopes the handlers raise.
ANSWERED_ERRORS = {304, 400, 401, 403, 404, 409, 422, 429, 500, 502, 503}


def _answered(status: int) -> bool:
    return 200 <= status < 300 or status in ANSWERED_ERRORS


def _not_a_crash(status: int) -> bool:
    return _answered(status) and status != 500


# A 204, a 205 or a 304 carries no body by definition (RFC 9110 §15.3.5,
# §15.3.6 and §15.4.5) and so no content-type. All three are answers, and
# the envelope check ran on every status alike, which would have failed the
# sweep the first time an operation answered 204 (Codex P2 on #999). None
# does today; the gate must not be what forbids it.
BODYLESS = frozenset({204, 205, 304})


def _assert_json_envelope(label: str, response) -> None:
    """Every answer that may carry a body carries a JSON envelope.

    Not a stack trace or a bare "Internal Server Error" string: the nine
    handlers this file fixed all answered `text/plain` before. A bodyless
    status is held to the opposite, that it really sent nothing.
    """
    if response.status_code in BODYLESS:
        assert not response.content, (
            f"{label} answered {response.status_code} with a body: "
            f"{response.content[:200]!r}")
        return
    assert response.headers.get("content-type", "").startswith("application/json"), (
        f"{label} answered {response.status_code} with content-type "
        f"{response.headers.get('content-type')!r}")


@pytest.mark.parametrize("req", REQUESTS, ids=lambda r: r.label)
def test_operation_answers(client, req: Req):
    r = client.request(req.method, req.url, json=req.json)

    assert _not_a_crash(r.status_code), (
        f"{req.label} returned {r.status_code}. A 500 here is an unhandled "
        f"exception reaching FastAPI, not an error the frontend can render.\n"
        f"body: {r.text[:400]}")

    _assert_json_envelope(req.label, r)

    assert r.status_code == req.expect, (
        f"{req.label} answered {r.status_code}, the table says {req.expect}. "
        f"Either this is a regression or the contract changed and the table "
        f"needs updating — both deserve a look.\nbody: {r.text[:400]}")


def test_a_bodyless_answer_passes_the_envelope_check():
    """204 and 304 have no body, and the check must not demand a JSON one.

    Exercised through a real FastAPI app so the assertion sees exactly what
    the sweep sees. A 204 declared on the decorator still carries
    `content-type: application/json` (FastAPI serialises the `None`), so
    the old check happened to pass it; a `Response(status_code=204)` and
    a 304 carry no content-type at all, and the old check failed both.
    Then the two failures the check must still catch: a body-bearing
    status without a JSON envelope, and a bodyless status that sent bytes
    anyway.
    """
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.responses import PlainTextResponse, Response
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.delete("/declared", status_code=204)
    def _declared() -> None:
        return None

    @app.delete("/explicit")
    def _explicit():
        return Response(status_code=204)

    @app.get("/cached")
    def _cached():
        return Response(status_code=304)

    @app.get("/plain")
    def _plain():
        return PlainTextResponse("Internal Server Error", status_code=500)

    with TestClient(app) as tc:
        for method, path, status, typed in (("DELETE", "/declared", 204, True),
                                            ("DELETE", "/explicit", 204, False),
                                            ("GET", "/cached", 304, False)):
            r = tc.request(method, path)
            assert r.status_code == status and not r.content, r.text[:100]
            assert ("content-type" in r.headers) is typed, r.headers
            _assert_json_envelope(f"{method} {path}", r)
        with pytest.raises(AssertionError, match="content-type 'text/plain"):
            _assert_json_envelope("GET /plain", tc.get("/plain"))
    with pytest.raises(AssertionError, match="with a body"):
        _assert_json_envelope("DELETE /leaky", SimpleNamespace(
            status_code=204, headers={}, content=b"{}"))


def _handler_ran(response) -> bool:
    """Did the endpoint function execute, judged from the response?

    FastAPI raises `RequestValidationError` BEFORE calling the endpoint and
    answers 422 with a distinctive body: `detail` is a list of
    `{"type", "loc", "msg"}` objects. Every other status -- including a 422 a
    handler raises itself, whose `detail` is a plain string -- means the
    endpoint ran.

    Derived rather than declared. `body_ran` on the table is an annotation I
    wrote, defaulting to True, so counting it measured my own bookkeeping: if
    an entry currently answering a handler-raised 422 started failing
    FastAPI's validation instead, the status would not change and the count
    would not change, and the sweep would stay green while quietly executing
    one less handler.
    """
    if response.status_code != 422:
        return True
    try:
        detail = response.json().get("detail")
    except ValueError:
        return True
    return not (isinstance(detail, list) and detail
                and isinstance(detail[0], dict) and "loc" in detail[0])


def test_the_declared_handler_reach_matches_what_actually_happened(client):
    """Every `body_ran` annotation is checked against the real response."""
    wrong = []
    for req in REQUESTS:
        r = client.request(req.method, req.url, json=req.json)
        actual = _handler_ran(r)
        if actual != req.body_ran:
            wrong.append(
                f"{req.label}: table says body_ran={req.body_ran}, the "
                f"response says {actual} ({r.status_code}: {r.text[:90]})")
    assert not wrong, (
        "the table's handler-reach annotations disagree with the responses:"
        "\n  " + "\n  ".join(wrong))


def test_most_requests_reach_the_handler(client):
    """The file states how much of itself is real, and holds itself to it.

    A request stopped by FastAPI's own body validation says nothing about the
    handler behind it. Those are the honest exceptions and they are meant to
    stay few: a table that drifted to mostly 422s would still report "every
    operation requested" while executing almost no application code, which is
    the shape of over-claim this whole file exists to avoid.

    Measured from the responses, not read off the table -- see `_handler_ran`.
    """
    shallow = []
    for req in REQUESTS:
        r = client.request(req.method, req.url, json=req.json)
        if not _handler_ran(r):
            shallow.append(f"{req.label} -> {r.status_code}")
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
    import psycopg2

    def boom(*_a, **_k):
        # The type a real outage raises, not a stand-in. The handlers now ask
        # `is_infrastructure_error` whether a failure is an outage or a bug, so
        # a `RuntimeError` here would assert 503 against a classification path
        # production never reaches -- and would have kept passing after the
        # narrowing that this test exists to constrain (Codex P1 on #999).
        raise psycopg2.OperationalError(_REFUSED)

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
        assert "OperationalError" in r.json()["detail"], r.text[:300]


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
    """The other endpoint from this week's defects (#992).

    This test is why the route table exists. Merging main brought in #992's
    switch to the strict query helper, and strict WITHOUT a handler is not an
    improvement over swallowing -- it just moves the wrong answer, from a 404
    blaming the operator to a bare 500 carrying a driver traceback. Neither is
    the explicit unavailable state Rule 3.7 asks for, and 113 other tests
    passed over it.

    503, and the detail must not leak the driver message: this endpoint is
    reachable unauthenticated and a SQLAlchemy error renders the SQL, its
    bound parameters and connection metadata.
    """
    r = client.get(f"/api/options/dates/{T}")
    assert r.status_code == 503, r.text[:300]
    # EXACT, not a keyword scan. A first version listed driver strings to
    # look for and passed against a detail that interpolated the exception,
    # because this environment's error text happened to contain none of them
    # — a leak test that only catches the leaks you guessed. Pinning the whole
    # string catches any interpolation, whatever the driver says that day.
    assert r.json()["detail"] == (
        f"Could not read option snapshot dates for {T}: "
        f"the database is unavailable."), r.json()["detail"]


@pytest.mark.parametrize("flag,method,path,body", [
    ("MOVEMENT_STATEMENT_ENABLED", "GET",
     f"/api/movement-statement?ticker={T}&timeframe=15m", None),
    ("STRUCTURE_CONTINUATION_ENABLED", "POST",
     "/api/admin/strat-engine/structure-continuation",
     {"ticker": T, "timeframe": "15m"}),
])
def test_the_feature_gated_handlers_survive_a_backend_outage(
    client, monkeypatch, flag, method, path, body,
):
    """A flag-OFF 404 covers the route and executes none of the real code.

    The sweep's rows for these two operations stop at the feature-flag check,
    which is the first statement in each handler. The table therefore marked
    both covered while the code that serves users -- the part behind the flag,
    which reads the database -- was never executed. Turned on with the same
    backend outage injected, both returned a BARE 500 from an unguarded
    `get_engine()` (Codex, PR #999).

    So the flag is turned ON here and the response is required to be a handled
    one. 503 is the contract: these endpoints already return explicit
    UNAVAILABLE envelopes for "the model has nothing to say", and a database
    that is unreachable is infrastructure rather than a consulted-but-empty
    model -- answering 200 with an envelope would tell the caller the opposite
    of what happened.
    """
    monkeypatch.setenv(flag, "1")
    # Prove the request reaches the DATABASE, not just the flag check or the
    # heavy-module import: a spy on `get_engine` that fails like the harness,
    # asserted called after the response (Codex P2 on #999).
    _reach_predict_backend(monkeypatch)
    from gcp import database
    spy = _MagicMock(side_effect=_BackendDown("down"))
    monkeypatch.setattr(database, "get_engine", spy)
    resp = client.request(method, path, json=body) if body else client.get(path)
    assert spy.called, (
        f"{method} {path} answered {resp.status_code} without calling "
        f"get_engine — the 503 came from the import guard, not the backend")

    assert resp.status_code != 500, (
        f"{method} {path} with {flag}=1 returned a bare 500 — an unhandled "
        f"exception reaching FastAPI, not an error the frontend can render.\n"
        f"body: {resp.text[:400]}")
    assert resp.status_code == 503, (
        f"expected 503 for a backend outage on the enabled path, got "
        f"{resp.status_code}: {resp.text[:400]}")
    assert resp.headers.get("content-type", "").startswith("application/json")
def test_every_success_status_is_an_answer():
    """201 and 202 are answers, as any 2xx is; 500 and a redirect are not."""
    for status in (200, 201, 202, 204, 205, 206):
        assert _not_a_crash(status), status
    for status in (304, 400, 401, 403, 404, 409, 422, 429, 502, 503):
        assert _not_a_crash(status), status
    for status in (500, 302, 307, 501):
        assert not _not_a_crash(status), status
    assert _answered(500) and not _not_a_crash(500)


@pytest.mark.parametrize("path,flag", [
    ("/api/admin/strat-engine/predict", None),
    ("/api/admin/strat-engine/structure-continuation",
     "STRUCTURE_CONTINUATION_ENABLED"),
])
def test_a_malformed_as_of_timestamp_is_the_callers_error(
    client, monkeypatch, path, flag,
):
    """400, not 503.

    The parse sat inside the infrastructure guard, so `"not-a-date"` came back
    as "strat engine temporarily unavailable" -- telling an authenticated
    admin to retry a request that can never succeed, and accusing a backend
    that is healthy (Codex, PR #999). Both endpoints had it.
    """
    if flag:
        monkeypatch.setenv(flag, "1")
    resp = client.post(path, json={
        "ticker": T, "timeframe": "15m", "as_of_timestamp": "not-a-date"})

    assert resp.status_code == 400, (
        f"{path} answered {resp.status_code} for a malformed as_of_timestamp; "
        f"a bad request is not a backend outage.\nbody: {resp.text[:300]}")
    assert "as_of_timestamp" in resp.text
    assert resp.headers.get("content-type", "").startswith("application/json")


def test_a_valid_as_of_timestamp_still_reaches_the_backend(client, monkeypatch):
    """The 400 above must not swallow a well-formed request.

    With the same outage injected, a parseable timestamp has to get past the
    parse and fail on the infrastructure instead -- otherwise the fix would
    have replaced one wrong answer with another.
    """
    monkeypatch.setenv("STRUCTURE_CONTINUATION_ENABLED", "1")
    _reach_predict_backend(monkeypatch)
    from gcp import database
    spy = _MagicMock(side_effect=_BackendDown("down"))
    monkeypatch.setattr(database, "get_engine", spy)
    resp = client.post("/api/admin/strat-engine/structure-continuation", json={
        "ticker": T, "timeframe": "15m", "as_of_timestamp": "2026-09-04T14:30:00"})
    assert spy.called, (
        f"a valid timestamp answered {resp.status_code} without reaching "
        f"get_engine — the guard was not exercised")

    assert resp.status_code == 503, (
        f"a valid timestamp answered {resp.status_code}; it should reach the "
        f"backend guard.\nbody: {resp.text[:300]}")


def test_a_successful_route_write_still_guards_its_reload(client, monkeypatch):
    """`set_route` and `list_routes` open separate connections.

    The sweep's `PUT /api/admin/routes/analyst` row makes the WRITE fail, so
    it never reaches the reload underneath. A committed write followed by a
    transient read failure therefore still escaped as a bare 500, past the 503
    the write had just gained (Codex, PR #999). Stub the write to SUCCEED and
    only the read to fail.
    """
    import api.routers.admin as admin

    import psycopg2

    monkeypatch.setattr(admin, "set_route", lambda *a, **k: None)
    monkeypatch.setattr(
        admin, "list_routes",
        lambda: (_ for _ in ()).throw(
            psycopg2.OperationalError(_REFUSED)))

    resp = client.put("/api/admin/routes/analyst",
                      json={"provider": "vertex", "model": "gemini-2.5-flash"})

    assert resp.status_code == 503, (
        f"a read failure after a successful write is still a bare "
        f"{resp.status_code}: {resp.text[:400]}")
    assert resp.json()["detail"] == "model route store temporarily unavailable"


# ── an INTERNAL defect must fail loudly ─────────────────────────────────────
#
# Every 503 guard this PR added wraps a whole helper, not a connection
# boundary, so `except Exception` rewrote a `KeyError` or `TypeError` from our
# own code into a retryable "temporarily unavailable" -- and the coverage
# requests above, which assert 503, would have stayed green straight through a
# schema regression (Codex P1 on #999).
#
# Rule 3.7 already draws the line these tests enforce: an EXTERNAL failure is
# reported as an explicit 503, an INTERNAL one is a bug and must surface.


def test_an_internal_defect_is_not_reported_as_an_outage(client, monkeypatch):
    """A `TypeError` in a guarded helper is a 500, not a 503.

    One case per guard Codex named, plus the two route-store guards that were
    not named and had the same conflation. The pair with the 503 tests above
    is the point: the same call site must answer 503 for a driver failure and
    500 for a defect, and only one of those was true before this.
    """
    import psycopg2
    from api.routers import insights as insights_module
    import api.routers.admin as admin
    import api.routers.dashboard as dashboard

    def defect(*_a, **_k):
        raise TypeError("movement_result.reach_rate: expected float, got dict")

    # The fixture builds its client with `raise_server_exceptions=False`, so
    # an unhandled exception arrives as the 500 FastAPI would really answer.
    # That is the contract worth asserting anyway: "fails loudly" means the
    # caller sees a 500, not that a particular exception escapes the app.
    def bare_500(resp, where):
        assert resp.status_code == 500, (
            f"{where}: an internal defect was reported as "
            f"{resp.status_code} -- an operator would retry a bug.\n"
            f"body: {resp.text[:300]}")

    # 1. insights, through `_db_call`.
    monkeypatch.setattr(insights_module, "_fetch_latest_report", defect)
    bare_500(client.get(f"/api/insights/report/{T}"), "insights report lookup")

    # 2. the model route store, on the read path.
    monkeypatch.setattr(admin, "list_routes", defect)
    bare_500(client.get("/api/admin/routes"), "admin route listing")

    # 3. the movement statement, behind its flag.
    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "1")
    monkeypatch.setattr(dashboard, "_build_movement_level_map", defect)
    bare_500(client.get(f"/api/movement-statement?ticker={T}&timeframe=15m"),
             "movement statement")

    # And the same call sites still answer 503 for a real driver failure, so
    # the narrowing did not simply delete the guards.
    def outage(*_a, **_k):
        raise psycopg2.OperationalError(_REFUSED)

    monkeypatch.setattr(admin, "list_routes", outage)
    r = client.get("/api/admin/routes")
    assert r.status_code == 503, r.text[:200]


def test_infrastructure_errors_are_classified_by_type():
    """The predicate itself, over the cases the guards depend on."""
    import psycopg2
    from lib.infra_errors import is_infrastructure_error

    for exc in (psycopg2.OperationalError(_REFUSED),
                psycopg2.InterfaceError("connection already closed"),
                ConnectionRefusedError(),
                TimeoutError(),
                # Constructed the way the interpreter constructs it: with
                # `name` set. A bare `ModuleNotFoundError("lightgbm")` never
                # comes from an import, and the name-based classifier declines
                # it on purpose (see the cases at the end of this test).
                ModuleNotFoundError("No module named 'lightgbm'",
                                    name="lightgbm")):
        assert is_infrastructure_error(exc), type(exc).__name__

    for exc in (TypeError("bad"), KeyError("reach_rate"), AttributeError("x"),
                ValueError("v"), psycopg2.ProgrammingError("syntax error")):
        assert not is_infrastructure_error(exc), type(exc).__name__

    # A driver error re-raised inside a helper's own wrapper is still an
    # outage; the chain is followed.
    wrapped = RuntimeError("could not load routes")
    wrapped.__cause__ = psycopg2.OperationalError(_REFUSED)
    assert is_infrastructure_error(wrapped)

    # ...but a wrapper around a DEFECT is not.
    wrapped2 = RuntimeError("could not load routes")
    wrapped2.__cause__ = TypeError("bad")
    assert not is_infrastructure_error(wrapped2)

    # A self-referencing chain terminates rather than spinning.
    loop = RuntimeError("a")
    loop.__cause__ = loop
    assert not is_infrastructure_error(loop)

    # The pool saying every connection is checked out is a capacity outage.
    # `sqlalchemy.exc.TimeoutError` is NOT the builtin `TimeoutError`, and the
    # guards were re-raising it as a bare 500 (Codex P2 on #999).
    from sqlalchemy import exc as sa_exc
    assert not issubclass(sa_exc.TimeoutError, TimeoutError)
    assert is_infrastructure_error(
        sa_exc.TimeoutError("QueuePool limit of size 7 overflow 0 reached"))

    # A missing OPTIONAL package is an unavailable feature. A renamed symbol,
    # or a typo in one of OUR module paths, is a bug and stays loud -- both
    # used to read as an outage because every `ImportError` did
    # (Codex P1 on #999).
    assert is_infrastructure_error(
        ModuleNotFoundError("No module named 'lightgbm'", name="lightgbm"))
    assert is_infrastructure_error(
        ModuleNotFoundError("No module named 'firebase_admin'",
                            name="firebase_admin"))
    assert not is_infrastructure_error(
        ImportError("cannot import name 'predict_one' from "
                    "'gcp.research.strat_engine.strat_pred_serve'"))
    assert not is_infrastructure_error(
        ModuleNotFoundError("No module named 'gcp.research.strat_pred_serv'",
                            name="gcp.research.strat_pred_serv"))
    assert not is_infrastructure_error(
        ModuleNotFoundError("No module named 'x'"))      # no name: not decided
    # EXACT name. The interpreter names the module it could not find, so a
    # submodule that does not exist inside an INSTALLED optional package is
    # `sklearn.nonexistent`, and matching the top-level segment read that
    # typo as an unavailable feature (Codex P1 on #999). Pinned against the
    # interpreter itself, on a package every image has.
    try:
        import json.nonexistent_zzz  # noqa: F401
    except ModuleNotFoundError as real:
        assert real.name == "json.nonexistent_zzz"
    for name in ("sklearn.nonexistent", "scipy.sparse.nonexistent",
                 "firebase_admin.typo", "lightgbm.sklearn.x"):
        assert not is_infrastructure_error(
            ModuleNotFoundError(f"No module named '{name}'", name=name)), name
    assert is_infrastructure_error(
        ModuleNotFoundError("No module named 'scipy'", name="scipy"))

    from lib.infra_errors import INFRASTRUCTURE_ERRORS
    # The data-plane socket. The connector opens it with
    # `socket.create_connection` before handing it to pg8000, and a network
    # that is gone is a plain `OSError` by errno, or a `socket.gaierror` for
    # a name that will not resolve -- neither a `ConnectionError`
    # (Codex P1 on #999). A path or permission error is still ours.
    import errno
    import socket
    for exc in (OSError(errno.ENETUNREACH, "Network is unreachable"),
                OSError(errno.EHOSTUNREACH, "No route to host"),
                OSError(errno.ENETDOWN, "Network is down"),
                # ...and a socket that could not be ALLOCATED: descriptors or
                # buffers exhausted, a capacity outage (Codex P2 on #999).
                OSError(errno.EMFILE, "Too many open files"),
                OSError(errno.ENFILE, "Too many open files in system"),
                OSError(errno.ENOBUFS, "No buffer space available"),
                socket.gaierror(-2, "Name or service not known"),
                socket.herror(1, "Unknown host"),
                socket.timeout("timed out")):
        assert is_infrastructure_error(exc), (type(exc).__name__, exc)
    for exc in (FileNotFoundError(errno.ENOENT, "no such file"),
                PermissionError(errno.EACCES, "denied"),
                IsADirectoryError(errno.EISDIR, "dir"),
                OSError(errno.EIO, "i/o error"),
                OSError("no errno at all")):
        assert not is_infrastructure_error(exc), (type(exc).__name__, exc)
    # The TLS layer. The connector wraps the socket before pg8000 sees it,
    # and a proxy restart or a certificate rotation aborts the handshake
    # with an `ssl.SSLError` carrying the SSL library's errno, which is
    # neither a `ConnectionError` nor a network errno (Codex P1 on #999).
    import ssl
    for exc in (ssl.SSLError(1, "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF"),
                ssl.SSLEOFError(8, "EOF occurred in violation of protocol"),
                ssl.SSLZeroReturnError(6, "TLS/SSL connection has been closed")):
        assert is_infrastructure_error(exc), type(exc).__name__
    # A certificate the endpoint presented that does not verify is a bad
    # trust chain, a hostname mismatch or an intercepted endpoint, and no
    # retry resolves it (Codex P2 on #999). Through aiohttp as well, where
    # the certificate error inherits from BOTH the connection error and
    # `SSLCertVerificationError`.
    assert not is_infrastructure_error(
        ssl.SSLCertVerificationError(1, "certificate verify failed"))

    # psycopg2's `OperationalError` is the base of every server error in
    # classes 08, 28, 53, 57 and 58 alike, and was registered wholesale, so a
    # wrong password classified as an outage (Codex P2 on #999). The SQLSTATE
    # decides; a code-less plain `OperationalError` is the driver's own
    # connection failure.
    import psycopg2.errors as pg_errors
    assert psycopg2.OperationalError not in INFRASTRUCTURE_ERRORS
    assert sa_exc.OperationalError not in INFRASTRUCTURE_ERRORS
    # A code-less OperationalError is the driver's own, and libpq wraps every
    # failed connection attempt identically, so the failure named after the
    # wrapper decides. Captured live through psycopg2 2.9.12 / libpq 17
    # against Postgres 16: a refused port, a role over its connection limit
    # and the server terminating mid-query are outages; no password, a wrong
    # one, an unknown database and a server without SSL are deployments,
    # under the same wrapper with the same `pgcode` None (Codex P2 on #999,
    # twice). The exact texts are in `_LIBPQ_*` in infra_errors.py.
    for exc in (psycopg2.OperationalError(
                    "could not connect to server: Connection refused\n"
                    '\tIs the server running on host "db" (10.0.0.5) and '
                    "accepting\n\tTCP/IP connections on port 5432?"),  # libpq < 14
                psycopg2.OperationalError(
                    "server closed the connection unexpectedly\n"
                    "\tThis probably means the server terminated abnormally\n"
                    "\tbefore or while processing the request.\n"),
                psycopg2.OperationalError(_REFUSED),
                psycopg2.OperationalError(
                    'connection to server at "127.0.0.1", port 54329 failed: '
                    "Connection refused\n\tIs the server running on that host "
                    "and accepting TCP/IP connections?\n"),
                psycopg2.OperationalError(                # one attempt per address
                    'connection to server at "localhost" (::1), port 5432 failed: '
                    "Connection refused\n\tIs the server running on that host "
                    "and accepting TCP/IP connections?\n"
                    'connection to server at "localhost" (127.0.0.1), port 5432 '
                    "failed: Connection refused\n\tIs the server running on "
                    "that host and accepting TCP/IP connections?\n"),
                psycopg2.OperationalError(
                    'connection to server at "10.255.255.1", port 5432 failed: '
                    "timeout expired"),
                psycopg2.OperationalError(
                    'connection to server at "db", port 5432 failed: '
                    "No route to host"),
                psycopg2.OperationalError(
                    'connection to server on socket "/cloudsql/p:r:i/.s.PGSQL.5432" '
                    "failed: Connection refused"),
                psycopg2.OperationalError(
                    'connection to server at "127.0.0.1", port 54329 failed: '
                    'FATAL:  too many connections for role "app"\n'),  # 53300
                psycopg2.OperationalError(
                    'connection to server at "db", port 5432 failed: '
                    "FATAL:  the database system is starting up\n"),   # 57P03
                psycopg2.OperationalError(
                    'connection to server at "db", port 5432 failed: '
                    "FATAL:  remaining connection slots are reserved for roles "
                    "with the SUPERUSER attribute\n"),                 # 53300
                psycopg2.OperationalError(
                    'could not translate host name "db.invalid" to address: '
                    "Name or service not known"),
                psycopg2.OperationalError("SSL SYSCALL error: EOF detected"),
                psycopg2.OperationalError(
                    "could not receive data from server: Connection reset by peer"),
                pg_errors.ConnectionFailure("connection failure"),      # 08006
                pg_errors.ProtocolViolation("protocol violation"),      # 08P01
                pg_errors.AdminShutdown("terminating connection"),      # 57P01
                pg_errors.CannotConnectNow("starting up"),              # 57P03
                pg_errors.DatabaseDropped("database has been dropped"), # 57P04
                pg_errors.IdleSessionTimeout("idle-session timeout"),   # 57P05
                pg_errors.TooManyConnections("too many clients"),       # 53300
                pg_errors.DiskFull("could not write"),                  # 53100
                pg_errors.OutOfMemory("out of memory"),                 # 53200
                pg_errors.IoError("could not read block")):             # 58030
        assert is_infrastructure_error(exc), type(exc).__name__
    for exc in (psycopg2.OperationalError(
                    'invalid integer value "abc" for connection option "port"'),
                psycopg2.OperationalError('invalid sslmode value: "bogus"'),
                psycopg2.OperationalError("some new message"),
                psycopg2.OperationalError("could not connect to server"),  # names no failure
                psycopg2.OperationalError(                # DB_PASS unset: live text
                    'connection to server at "127.0.0.1", port 54329 failed: '
                    "fe_sendauth: no password supplied\n"),
                psycopg2.OperationalError(
                    'connection to server at "127.0.0.1", port 54329 failed: '
                    'FATAL:  password authentication failed for user "postgres"\n'),
                psycopg2.OperationalError(
                    'connection to server at "127.0.0.1", port 54329 failed: '
                    'FATAL:  database "nope" does not exist\n'),
                psycopg2.OperationalError(
                    'connection to server at "db", port 5432 failed: '
                    'FATAL:  no pg_hba.conf entry for host "10.0.0.9", user "app", '
                    'database "trading", no encryption\n'),
                psycopg2.OperationalError(
                    'connection to server at "127.0.0.1", port 54329 failed: '
                    "server does not support SSL, but SSL was required\n"),
                psycopg2.OperationalError(
                    'connection to server at "db", port 5432 failed: '
                    "SSL error: certificate verify failed: self-signed certificate\n"),
                psycopg2.OperationalError(
                    'connection to server on socket "/cloudsql/p:r:i/.s.PGSQL.5432" '
                    "failed: No such file or directory\n"),
                psycopg2.OperationalError(                # refused, then rejected
                    'connection to server at "localhost" (::1), port 5432 failed: '
                    "Connection refused\n\tIs the server running on that host "
                    "and accepting TCP/IP connections?\n"
                    'connection to server at "localhost" (127.0.0.1), port 5432 '
                    'failed: FATAL:  password authentication failed for user "x"\n'),
                pg_errors.InvalidPassword("password authentication failed"),
                pg_errors.InvalidAuthorizationSpecification("no role"),  # 28000
                pg_errors.QueryCanceled("canceling statement"),          # 57014
                pg_errors.OperatorIntervention("intervention"),          # 57000
                pg_errors.ObjectInUse("database is being accessed")):    # 55006
        assert isinstance(exc, psycopg2.OperationalError), type(exc).__name__
        assert not is_infrastructure_error(exc), type(exc).__name__
    # The server's OWN failures, class XX, arrive as `InternalError`
    # subclasses rather than `OperationalError`, and a predicate gated on the
    # latter never reached their code while pg8000 already answered 503 for
    # the same codes (Codex P2 on #999). The class-level SQLSTATE rules
    # decide every DatabaseError subclass the same way.
    for exc in (pg_errors.InternalError_("internal error"),              # XX000
                pg_errors.DataCorrupted("invalid page"),                 # XX001
                pg_errors.IndexCorrupted("index corrupted")):            # XX002
        assert isinstance(exc, psycopg2.InternalError), type(exc).__name__
        assert not isinstance(exc, psycopg2.OperationalError)
        assert is_infrastructure_error(exc), type(exc).__name__
    for exc in (pg_errors.ConfigFileError("config"),                     # F0000
                pg_errors.UndefinedTable("no such table"),               # 42P01
                pg_errors.UniqueViolation("duplicate key"),              # 23505
                psycopg2.InternalError("no code at all"),
                psycopg2.DatabaseError("no code at all")):
        assert not is_infrastructure_error(exc), type(exc).__name__
    # The SQLAlchemy wrapper is decided by what it wraps, in both directions.
    for orig, expected in ((pg_errors.InvalidPassword("bad password"), False),
                           (pg_errors.AdminShutdown("terminating"), True),
                           (psycopg2.OperationalError(
                               'connection to server at "h", port 5432 failed: '
                               "Connection refused"), True),
                           (psycopg2.OperationalError(
                               'invalid integer value "x" for connection option '
                               '"port"'), False)):
        try:
            raise sa_exc.OperationalError("connect", {}, orig) from orig
        except sa_exc.OperationalError as wrapped_sa:
            assert is_infrastructure_error(wrapped_sa) is expected, type(orig).__name__

    # psycopg2's `InterfaceError` has the same two faces as pg8000's and was
    # registered wholesale (Codex P1 on #999): the connection being gone
    # classifies; the cursor being closed, a value the driver cannot parse,
    # and misuse of the asynchronous API do not.
    assert psycopg2.InterfaceError not in INFRASTRUCTURE_ERRORS
    for message in ("connection already closed", "asynchronous connection failed"):
        assert is_infrastructure_error(psycopg2.InterfaceError(message)), message
    for message in ("cursor already closed", "failed to parse range: '[1,2'",
                    "can't parse type: 'x'",
                    "execute cannot be used while an asynchronous query is underway"):
        assert not is_infrastructure_error(psycopg2.InterfaceError(message)), message
    assert not is_infrastructure_error(psycopg2.InterfaceError())

    # The PRODUCTION driver. `model_routing.connect()` returns a bare pg8000
    # connection, so its client-side failures arrive raw and without a
    # `__cause__`; they were classified as bugs (Codex P1 on #999). pg8000
    # has no `ProgrammingError` and folds a syntax error into
    # `DatabaseError`, so that class stays OUT: it is where our own SQL
    # mistakes land.
    import pg8000.exceptions as pg8000_exc
    # The transport, in the words `pg8000.core` uses: an outage.
    for message in ("network error", "communication error",
                    "connection is closed"):
        assert is_infrastructure_error(pg8000_exc.InterfaceError(message)), message
    # The same class for the application misusing the driver: a defect.
    # Registering the class wholesale hid these (Codex P1 on #999).
    for message in ("Cursor closed", "identifier must be a str",
                    "The parameter x can't be of type <class 'object'>.",
                    "Server refuses SSL"):
        assert not is_infrastructure_error(
            pg8000_exc.InterfaceError(message)), message
    assert not is_infrastructure_error(pg8000_exc.InterfaceError())
    # A PostgreSQL error response is `DatabaseError` whatever it says; the
    # SQLSTATE under `C` decides. A failover's shutdown, a lost connection
    # and an exhausted server are outages; our SQL being wrong is not
    # (Codex P1 on #999).
    for code in ("57P01", "57P02", "57P03", "57P04", "57P05", "08006", "08003",
                 "08001", "53300", "53100", "53200", "58030", "XX001"):
        assert is_infrastructure_error(pg8000_exc.DatabaseError(
            {"S": "FATAL", "C": code, "M": "terminating connection"})), code
    for code in ("42601", "42P01", "23505", "22P02", "0A000", "57014", "57000",
                 "28P01", "3D000", "F0000", "55006"):
        assert not is_infrastructure_error(pg8000_exc.DatabaseError(
            {"S": "ERROR", "C": code, "M": "syntax error at or near"})), code
    assert not is_infrastructure_error(pg8000_exc.DatabaseError("no payload"))
    assert not is_infrastructure_error(pg8000_exc.DatabaseError({"M": "no code"}))
    assert not is_infrastructure_error(pg8000_exc.Error("base class"))
    assert not hasattr(pg8000_exc, "ProgrammingError"), (
        "pg8000 grew a ProgrammingError: revisit whether DatabaseError can "
        "now be split and the connection half classified")
    # SQLAlchemy wraps the same response as its own DatabaseError raised FROM
    # the driver's; the cause walk reaches the SQLSTATE either way.
    gone = pg8000_exc.DatabaseError(
        {"S": "FATAL", "C": "57P01", "M": "administrator command"})
    try:
        raise sa_exc.DatabaseError("SELECT 1", {}, gone) from gone
    except sa_exc.DatabaseError as wrapped_sa:
        assert is_infrastructure_error(wrapped_sa)
    wrong = pg8000_exc.DatabaseError({"S": "ERROR", "C": "42601", "M": "syntax"})
    try:
        raise sa_exc.DatabaseError("SELEC 1", {}, wrong) from wrong
    except sa_exc.DatabaseError as wrapped_sa:
        assert not is_infrastructure_error(wrapped_sa)
    # The wrapper's class only echoes the driver's class name, so it is not
    # registered: `sa_exc.InterfaceError` around pg8000's "Cursor closed" was
    # accepted wholesale, straight past the message filter (Codex P1 on
    # #999). What it wraps decides, reached through `__cause__` and, when a
    # re-raise has stripped that, through `.orig`.
    assert sa_exc.InterfaceError not in INFRASTRUCTURE_ERRORS
    for message, expected in (("Cursor closed", False),
                              ("identifier must be a str", False),
                              ("network error", True),
                              ("connection is closed", True)):
        orig = pg8000_exc.InterfaceError(message)
        try:
            raise sa_exc.InterfaceError("SELECT 1", {}, orig) from orig
        except sa_exc.InterfaceError as wrapped_sa:
            assert is_infrastructure_error(wrapped_sa) is expected, message
        bare = sa_exc.InterfaceError("SELECT 1", {}, orig)   # no __cause__
        assert bare.__cause__ is None and bare.orig is orig
        assert is_infrastructure_error(bare) is expected, (message, "orig")
    for message, expected in (("connection already closed", True),
                              ("cursor already closed", False)):
        psy = psycopg2.InterfaceError(message)
        try:
            raise sa_exc.InterfaceError("SELECT 1", {}, psy) from psy
        except sa_exc.InterfaceError as wrapped_sa:
            assert is_infrastructure_error(wrapped_sa) is expected, message

    # The Cloud SQL connector's control plane. `Connector.connect()` fetches
    # metadata and an ephemeral certificate from the SQL Admin API over
    # aiohttp before opening a socket, and its lazy refresh re-raises what
    # that fetch raised: a network failure is `ClientConnectionError`, and a
    # response it gave up on after its own 5xx retries is
    # `ClientResponseError` -- neither the builtin ConnectionError nor any
    # google.api_core class (Codex P1 on #999). Status decides the second:
    # 429 and 5xx are the service; a 4xx is our credentials or configuration.
    import aiohttp
    from types import SimpleNamespace
    assert is_infrastructure_error(
        aiohttp.ClientConnectionError("Cannot connect to sqladmin.googleapis.com"))
    assert issubclass(aiohttp.ClientConnectorError, aiohttp.ClientConnectionError)
    key = SimpleNamespace(host="sqladmin.googleapis.com", port=443, ssl=None)
    assert not is_infrastructure_error(aiohttp.ClientConnectorCertificateError(
        key, ssl.SSLCertVerificationError(1, "certificate verify failed")))
    assert is_infrastructure_error(aiohttp.ClientConnectorSSLError(
        key, ssl.SSLError(1, "[SSL: UNEXPECTED_EOF_WHILE_READING]")))
    assert not issubclass(aiohttp.ClientConnectorSSLError,
                          aiohttp.ClientConnectorCertificateError)
    req = SimpleNamespace(real_url="https://sqladmin.googleapis.com/sql/v1beta4/x")
    for status in (429, 500, 502, 503, 504):
        assert is_infrastructure_error(
            aiohttp.ClientResponseError(req, (), status=status)), status
    for status in (400, 401, 403, 404):
        assert not is_infrastructure_error(
            aiohttp.ClientResponseError(req, (), status=status)), status


def test_the_final_four_guards_keep_the_split(client, monkeypatch):
    """The catches the final review found still broad, each both ways.

    Each site answers 503 for what a real outage raises and a bare 500 for a
    defect, on the same call site -- the pair is the property, not either
    half (Codex, final review on #999).
    """
    import psycopg2
    from sqlalchemy import exc as sa_exc
    import api.routers.admin as admin
    import api.routers.options as options
    import api.auth as auth

    def bare_500(resp, where):
        assert resp.status_code == 500, (
            f"{where}: an internal defect was reported as {resp.status_code}"
            f"\nbody: {resp.text[:300]}")

    # 1-2. The options dates probe and query.
    def defect(*_a, **_k):
        raise sa_exc.ProgrammingError(
            "SELECT snapshot_dat", {}, psycopg2.ProgrammingError("column"))
    monkeypatch.setattr(options, "_dates_query", defect)
    bare_500(client.get(f"/api/options/dates/{T}"), "options dates probe")

    def outage(*_a, **_k):
        raise sa_exc.TimeoutError("QueuePool limit of size 7 overflow 0 reached")
    monkeypatch.setattr(options, "_dates_query", outage)
    r = client.get(f"/api/options/dates/{T}")
    assert r.status_code == 503, r.text[:200]

    # 3. Firebase initialisation.
    monkeypatch.setattr(auth, "_ensure_firebase",
                        lambda: (_ for _ in ()).throw(TypeError("bad init")))
    bare_500(client.get("/api/admin/users"), "firebase initialisation")
    monkeypatch.setattr(auth, "_ensure_firebase",
                        lambda: (_ for _ in ()).throw(ModuleNotFoundError(
                            "No module named 'firebase_admin'",
                            name="firebase_admin")))
    r = client.get("/api/admin/users")
    assert r.status_code == 503, r.text[:200]
    assert r.json()["detail"] == "user directory temporarily unavailable"

    # 4. The timestamp parser: a bad string is the caller's 400, a defect
    #    inside the parser is not.
    r = client.post("/api/admin/strat-engine/predict",
                    json={"ticker": T, "timeframe": "15m",
                          "as_of_timestamp": "not-a-timestamp"})
    assert r.status_code == 400, r.text[:200]
    import pandas as pd
    monkeypatch.setattr(pd, "to_datetime",
                        lambda *_a, **_k: (_ for _ in ()).throw(
                            AttributeError("integration regression")))
    bare_500(client.post("/api/admin/strat-engine/predict",
                         json={"ticker": T, "timeframe": "15m",
                               "as_of_timestamp": "2026-09-05T15:30:00Z"}),
             "timestamp parser")


def test_a_retryable_credential_refresh_is_an_outage_and_a_missing_package_is_not():
    """Two edges of the classifier (Codex P1 on #999).

    google-auth marks a `RefreshError` retryable when the token endpoint
    answered 5xx through its own retries; that is a control-plane outage and
    subclasses neither registered google-auth class. And `is_backend_outage`
    is the classifier a library read helper consults: everything
    `is_infrastructure_error` accepts except a research package this image
    lacks, which is an unavailable feature rather than an outage.
    """
    import psycopg2
    from google.auth import exceptions as gauth
    from lib.infra_errors import is_backend_outage, is_infrastructure_error

    assert is_infrastructure_error(gauth.RefreshError("server_error", retryable=True))
    assert not is_infrastructure_error(
        gauth.RefreshError("invalid_grant: Bad Request", retryable=False))
    assert not is_infrastructure_error(gauth.RefreshError("invalid_grant"))
    assert is_infrastructure_error(gauth.TransportError("connection reset"))

    missing = ModuleNotFoundError("No module named 'lightgbm'", name="lightgbm")
    assert is_infrastructure_error(missing)
    assert not is_backend_outage(missing)

    # google.api_core BadGateway (502) is a sibling of the 5xx classes, not a
    # subclass, so it needed adding explicitly (Codex P1 on #999).
    from google.api_core import exceptions as gapi
    assert is_backend_outage(gapi.BadGateway("bad gateway"))
    assert is_backend_outage(gapi.GatewayTimeout("timeout"))
    assert not is_backend_outage(gapi.NotFound("absent"))

    # EADDRNOTAVAIL: the local ephemeral-port range is exhausted (Codex P2).
    import errno as _errno
    assert is_backend_outage(
        OSError(_errno.EADDRNOTAVAIL, "Cannot assign requested address"))
    assert not is_backend_outage(OSError(_errno.ENOENT, "no such file"))

    # google.auth TransportError is an outage UNLESS it wraps a certificate
    # failure, which stays loud like the raw ssl and aiohttp cert cases
    # (Codex P2 on #999).
    import ssl as _ssl
    assert is_infrastructure_error(gauth.TransportError("connection reset"))
    cert = gauth.TransportError("SSL error")
    cert.__cause__ = _ssl.SSLCertVerificationError("certificate verify failed")
    assert not is_infrastructure_error(cert)
    cert2 = gauth.TransportError(
        "HTTPSConnectionPool: certificate verify failed: self-signed certificate")
    assert not is_infrastructure_error(cert2)
    for exc in (psycopg2.OperationalError(_REFUSED),
                gauth.RefreshError("server_error", retryable=True),
                ConnectionRefusedError()):
        assert is_backend_outage(exc), type(exc).__name__
    for exc in (TypeError("bad"), RuntimeError("corrupt artifact"),
                gauth.RefreshError("invalid_grant")):
        assert not is_backend_outage(exc), type(exc).__name__

