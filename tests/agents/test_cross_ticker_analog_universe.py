"""The cross-ticker analog pull must be bounded by a resolved universe.

Added 2026-09-16, after `insight-pipeline` OOM-killed NVDA and AMD on
2026-09-15 (PR #1116 raised the job to 4Gi; this is the actual cause).

`_build_cross_ticker_history` ran `WHERE ticker <> :ticker` against
`market_data_daily` with no universe filter and no bound, on its own
docstring's assumption of "the current ~5-ticker analog universe". The
table had grown to 2,609 tickers. Measured against production on
2026-09-16:

    rows returned        5,597,928   (Parallel Seq Scan; `<>` has no index)
    pd.read_sql peak     2.39 GiB
    after groupby .copy()2.93 GiB
    job memory limit     2 GiB       -> signal 9

The branch is reached only when the ticker's own history yields fewer
than 10 analogs. Verified with the production matcher against real bars
at the production as_of of 2026-09-15: NVDA 6, AMD 6 (both expand, both
OOM'd); AVGO 29, SPY 194 (neither expands, both completed). Four for
four, and day-dependent rather than ticker-dependent.

The universe is now RESOLVED by `gcp.fetchers._watchlist.
resolve_membership_at` and passed in, rather than expressed as a
sub-select inside the bar query. These tests pin the properties of that
arrangement; the membership rule itself is real-SQL tested in
`tests/integration/test_watchlist_history.py`, because it is a database
trigger and a mocked connection would only prove the mock fired.
"""
from __future__ import annotations

import datetime
import logging

import numpy as np
import pandas as pd
import pytest

from gcp.fetchers._watchlist import WatchlistMembership
from lib.agents import summarizers


def _bars(n: int, seed: int, start: float = 100.0) -> pd.DataFrame:
    """Deterministic random-walk OHLCV, oldest first."""
    rng = np.random.default_rng(seed)
    close = start * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
    d0 = datetime.date(2024, 1, 2)
    return pd.DataFrame({
        "date": [d0 + datetime.timedelta(days=i) for i in range(n)],
        "open": close * (1 + rng.normal(0, 0.003, n)),
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    })


def _universe(*tickers: str, as_of=None,
              resolution: str = "exact") -> WatchlistMembership:
    """A resolved universe, defaulting to TODAY's date.

    This used to hardcode 2026-09-15, which was "today" the day it was
    written. `summarize_backtest_metrics` defaults its cutoff to today, so
    the literal drifted out of agreement with it as soon as the date rolled
    over, and three tests were silently injecting a universe resolved for a
    different date than the bars they queried -- the defect Codex filed on
    `e3463b3`, live in the suite meant to cover this code. Tests that want a
    mismatch now have to ask for one.
    """
    if as_of is None:
        as_of = datetime.date.today()
    return WatchlistMembership(
        tickers=tuple(tickers), as_of=as_of, owner="default",
        resolution=resolution, horizon=None,
    )


PEERS = ("PEER1", "PEER2", "PEER3")


@pytest.fixture
def capture(monkeypatch):
    """Record every SQL handed to the strict and non-strict query paths.

    Also stubs the membership resolver so these stay hermetic: what the
    resolver returns is tested against a real Postgres elsewhere, and
    what matters here is that whatever it returns is what bounds the
    pull.
    """
    class _Seen(list):
        """A list of (sql, params) that also carries the resolver calls."""
        resolved: list

    seen = _Seen()
    resolved: list[tuple] = []

    def fake_query(sql: str, params=None):
        params = params or {}
        seen.append((sql, params))
        if "= ANY(:tickers)" in sql:
            frames = []
            for i, tk in enumerate(params.get("tickers") or ()):
                f = _bars(260, seed=100 + i)
                f.insert(0, "ticker", tk)
                frames.append(f)
            return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return _bars(230, seed=7)

    def fake_resolve(as_of, user_id="default"):
        resolved.append((as_of, user_id))
        return _universe(*PEERS, as_of=as_of)

    monkeypatch.setattr(summarizers, "_query", fake_query)
    monkeypatch.setattr(summarizers, "_query_strict", fake_query)
    monkeypatch.setattr(
        "gcp.fetchers._watchlist.resolve_membership_at", fake_resolve)
    seen.resolved = resolved
    return seen


def _cross_call(seen) -> tuple[str, dict]:
    matches = [(s, p) for s, p in seen if "= ANY(:tickers)" in s]
    assert matches, (
        "the cross-ticker pull never ran; the test data no longer forces "
        "expansion"
    )
    return matches[-1]


def _cross_sql(seen) -> str:
    return _cross_call(seen)[0]


# ---------------------------------------------------------------------------
# The bound
# ---------------------------------------------------------------------------


def test_the_cross_ticker_pull_is_bounded_by_the_resolved_universe(capture):
    """Red before the fix: the query named no universe at all.

    This is the whole fix. Without a universe the query's cost scales with
    how many tickers happen to exist in market_data_daily, which is the
    shape CLAUDE.md Rule 3.8 forbids. The bound is now an explicit list,
    so the test can assert the exact set rather than the presence of a
    join clause.
    """
    summarizers.summarize_backtest_metrics("TGT")
    sql, params = _cross_call(capture)
    assert sorted(params["tickers"]) == sorted(PEERS), (
        f"the pull was bounded by {params['tickers']!r}, not the resolved "
        "universe"
    )
    assert "market_data_daily" in sql and "watchlists" not in sql, (
        "the bar query still reads the watchlist table; membership is "
        "resolved separately so this query cannot fan out or drift from it"
    )


def test_the_unbounded_form_is_gone(capture):
    """Guards the exact string that shipped the OOM."""
    summarizers.summarize_backtest_metrics("TGT")
    sql = _cross_sql(capture)
    assert "ticker <> :ticker" not in sql, (
        "the cross-ticker pull reverted to `<>` against every other ticker "
        "in market_data_daily"
    )


def test_no_limit_truncates_the_analog_sample(capture):
    """The bound belongs on the universe, not on the row count.

    A LIMIT would look like a fix and silently bias the sample: the query
    is ORDER BY ticker, so a LIMIT keeps only the alphabetically-early
    names. Forward-return statistics computed from an A-to-C slice of the
    watchlist are not the statistics they claim to be.
    """
    summarizers.summarize_backtest_metrics("TGT")
    assert "LIMIT" not in _cross_sql(capture).upper(), (
        "a LIMIT was added to the cross-ticker analog pull; it truncates "
        "the sample in ticker order rather than bounding the universe."
    )


def test_the_universe_cannot_fan_out(capture):
    """Codex P1 on `c75c22c`, now structurally impossible.

    `watchlists` is `PRIMARY KEY (user_id, ticker)`, so one ticker holds
    one row per user and a plain `JOIN watchlists` returned every bar once
    per subscriber. That is silent corruption, not an error: `_engineer`
    groups by ticker and calls `.diff()`, `.rolling()`, `.ewm()` and
    `.shift(-n)` on the group, so duplicated dates are consumed as
    consecutive sessions and analog statistics get weighted by subscriber
    count.

    A resolved list of distinct tickers cannot multiply rows however the
    owner scoping later changes, which is a stronger guarantee than the
    EXISTS semi-join that replaced the join.
    """
    summarizers.summarize_backtest_metrics("TGT")
    _, params = _cross_call(capture)
    bound = params["tickers"]
    assert len(bound) == len(set(bound)), (
        f"the bound universe contains duplicates ({bound!r}); each would "
        "multiply that ticker's bars"
    )
    assert "JOIN watchlists" not in _cross_sql(capture)


def test_the_target_is_never_its_own_peer(capture):
    summarizers.summarize_backtest_metrics("PEER2")
    _, params = _cross_call(capture)
    assert "PEER2" not in params["tickers"], (
        "the target is in its own analog universe, so its own history is "
        "matched against itself and counted twice"
    )


# ---------------------------------------------------------------------------
# Asset class — now Python, still relative to the target
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target,expected",
    [
        ("TGT", ["AMD", "AVGO"]),
        ("^VIX", ["^VIX3M", "^VVIX"]),
    ],
)
def test_peers_match_the_targets_asset_class(monkeypatch, target, expected):
    """Codex P2 on `1069e50`. An unconditional caret exclusion is wrong
    in one direction.

    ^VIX, ^VIX3M and ^VVIX were all in the unbounded universe, and a
    volatility index is not an analog for an equity's gap-and-volume
    setup. But excluding carets *unconditionally* means that when the
    target is itself an index with sparse same-ticker matches, every
    index peer is dropped and only equities remain -- the same cross-asset
    comparison, inverted.

    Reachability, measured 2026-09-17: the `default` watchlist holds no
    caret ticker, so this is latent today. `SPX` was watchlisted (and
    removed 2026-04-30), so index-like symbols do get added.
    """
    seen: list[dict] = []

    def fake_query(sql: str, params=None):
        seen.append(params or {})
        return pd.DataFrame()

    monkeypatch.setattr(summarizers, "_query_strict", fake_query)
    summarizers._build_cross_ticker_history(
        target, "2026-09-15",
        universe=_universe("AMD", "AVGO", "^VIX3M", "^VVIX", "^VIX", "TGT"),
    )
    assert seen, "no query was issued"
    assert sorted(seen[-1]["tickers"]) == expected


# ---------------------------------------------------------------------------
# As-of
# ---------------------------------------------------------------------------


def test_membership_is_resolved_at_the_cutoff_not_now(capture):
    """Codex P2 on `1069e50`. Future config must not leak into a replay.

    The bar predicate was cutoff-relative while `removed_at IS NULL` asked
    whether a row is active NOW, so an `INSIGHT_AS_OF` replay resolved its
    analog universe from today's watchlist: a ticker added after the
    cutoff leaked in, one removed after it vanished, and re-running the
    same historical date could return different statistics because
    someone edited the watchlist in between -- the #822 look-ahead class
    arriving through a config table rather than through bars.
    """
    as_of = datetime.date(2024, 9, 1)
    summarizers.summarize_backtest_metrics("TGT", as_of=as_of)
    assert capture.resolved, "membership was never resolved"
    resolved_at, owner = capture.resolved[-1]
    assert resolved_at == as_of, (
        f"membership resolved at {resolved_at}, not the cutoff {as_of}; "
        "a replay would take its universe from today's watchlist"
    )
    assert owner == "default"


@pytest.mark.parametrize("inclusive_today,expected_op", [(False, "<"), (True, "<=")])
def test_the_as_of_operator_still_reaches_the_cross_ticker_pull(
    capture, inclusive_today, expected_op
):
    """Regression guard for #822 (audit R5) across the rewritten query.

    The as-of bar must not leak back in through the analogs. Rewriting the
    SQL is exactly when an f-string operator gets dropped.
    """
    summarizers.summarize_backtest_metrics(
        "TGT", as_of=datetime.date(2024, 9, 1), inclusive_today=inclusive_today
    )
    sql = _cross_sql(capture)
    assert f"m.date {expected_op} CAST(:cutoff AS date)" in sql, (
        f"cross-ticker pull lost its `{expected_op}` cutoff operator; the "
        f"as-of bar can leak into the analog set."
    )


# ---------------------------------------------------------------------------
# Threading
# ---------------------------------------------------------------------------


def test_an_injected_universe_is_used_and_not_re_resolved(capture):
    """The injection point exists so a replay can pin the analog set and a
    test can drive this path without a database."""
    summarizers.summarize_backtest_metrics(
        "TGT", universe=_universe("AMD", "AVGO"))
    _, params = _cross_call(capture)
    assert sorted(params["tickers"]) == ["AMD", "AVGO"]
    assert not capture.resolved, (
        "a universe was supplied and the resolver ran anyway; that is two "
        "resolutions that can disagree"
    )


def test_the_bundle_forwards_the_universe_to_the_backtest_section(monkeypatch):
    got: dict = {}

    def fake_backtest(ticker, **kw):
        got.update(kw)
        return {"available": True}

    monkeypatch.setattr(summarizers, "summarize_backtest_metrics", fake_backtest)
    for name in ("summarize_market_context", "summarize_strat_status",
                 "summarize_options_flow", "summarize_gamma_levels",
                 "summarize_catalysts", "summarize_news_sentiment"):
        monkeypatch.setattr(summarizers, name,
                            lambda *a, **k: {"available": True})

    u = _universe("AMD")
    summarizers.build_context_bundle("SPY", universe=u)
    assert got.get("universe") is u


# ---------------------------------------------------------------------------
# Disclosure — CLAUDE.md Rules 3.7 and 3.7.1
# ---------------------------------------------------------------------------


def test_analogs_are_still_found_and_attributed_to_their_source(capture):
    """The fix must not break the thing the expansion exists to do."""
    out = summarizers.summarize_backtest_metrics("TGT")
    assert out["available"] is True
    assert out["cross_ticker_used"] is True, (
        "expansion did not fire, so this test is not exercising the "
        "cross-ticker path"
    )
    assert out["analog_count"] >= 3, out.get("note")
    sources = {a["ticker"] for a in out["top_analogs"]}
    assert sources - {"TGT"}, "no analog was attributed to a peer ticker"
    assert sources <= {"TGT", *PEERS}, (
        f"analogs came from outside the resolved universe: {sources}"
    )


def test_the_report_carries_the_universe_and_its_resolution_quality(capture):
    """CLAUDE.md Rule 3.7.1: an undisclosed quality difference is a silent
    fallback. `approximate` means the cutoff predates the history horizon,
    where membership was seeded from `watchlists` and inherits its blind
    spot. A reader must be able to see that without reading the logs.
    """
    out = summarizers.summarize_backtest_metrics(
        "TGT", universe=_universe(*PEERS, resolution="approximate"))
    detail = out["cross_ticker"]
    assert detail["attempted"] is True
    assert detail["used"] is True
    assert detail["universe"]["resolution"] == "approximate"
    assert detail["universe"]["ticker_count"] == len(PEERS)


def test_not_used_says_which_of_the_three_reasons_it_was(monkeypatch):
    """`cross_ticker_used=False` meant three different things and a reader
    could not tell which: expansion not needed, universe empty, or peers
    present but nothing matched the band. That is a value the caller
    cannot distinguish from a legitimate result (CLAUDE.md Rule 3.7).
    """
    def only_own_bars(sql: str, params=None):
        if "= ANY(:tickers)" in sql:
            return pd.DataFrame()
        return _bars(230, seed=7)

    monkeypatch.setattr(summarizers, "_query", only_own_bars)
    monkeypatch.setattr(summarizers, "_query_strict", only_own_bars)

    empty = summarizers.summarize_backtest_metrics("TGT", universe=_universe())
    assert empty["cross_ticker_used"] is False
    assert empty["cross_ticker"]["attempted"] is True
    # Names the cause, not a pointer to Cloud Logging: an empty watchlist
    # resolves zero same-class peers, which is cause 1.
    assert "asset class" in empty["cross_ticker"]["reason"]

    off = summarizers.summarize_backtest_metrics("TGT", cross_ticker=False)
    assert off["cross_ticker"]["attempted"] is False
    assert "not needed" in off["cross_ticker"]["reason"]


def test_an_empty_universe_is_logged_not_silent(caplog):
    """An empty watchlist must not read as 'this ticker has no analogs'."""
    with caplog.at_level(logging.WARNING, logger="lib.agents.summarizers"):
        result, reason = summarizers._build_cross_ticker_history(
            "TGT", "2026-09-15", universe=_universe())
    assert result is None
    assert reason and "asset class" in reason
    assert any("universe empty" in r.getMessage() for r in caplog.records), (
        "an empty analog universe produced no log line"
    )


def test_a_database_failure_is_not_reported_as_no_analogs(monkeypatch):
    """`_query` returns an empty frame on error, which lands on the same
    branch as 'this universe has no bars'. The strict sibling raises, so
    build_context_bundle records the section as failed with the reason
    instead of publishing 'no analogs exist' (CLAUDE.md Rule 3.7).
    """
    def boom(sql: str, params=None):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(summarizers, "_query_strict", boom)
    with pytest.raises(RuntimeError, match="connection reset"):
        summarizers._build_cross_ticker_history(
            "TGT", "2026-09-15", universe=_universe("AMD"))


def test_a_caretless_index_symbol_is_not_filed_as_an_equity(monkeypatch):
    """The caret is a naming convention, not an asset class.

    `^VIX` is self-describing; `SPX`, `NDX`, `RUT` and `XSP` are not, and
    this repo carries them un-careted — `lib/options_greeks.py` keeps exactly
    that set as the cash-settled index roots whose Greeks it computes, and
    SPX is on the production watchlist (the history tests have it active on
    2026-04-29). Under `startswith("^")` an equity target pulls SPX index
    bars into its analog statistics and an SPX target pulls equities into
    its own, which is the cross-asset contamination this filter exists to
    stop (Codex P2 on `775a29f`).
    """
    seen: list[dict] = []

    def fake_query(sql: str, params=None):
        seen.append(params or {})
        return pd.DataFrame()

    monkeypatch.setattr(summarizers, "_query_strict", fake_query)

    summarizers._build_cross_ticker_history(
        "TGT", "2026-09-15",
        universe=_universe("AMD", "SPX", "NDX", "^VIX"),
    )
    assert sorted(seen[-1]["tickers"]) == ["AMD"], (
        "an equity target pulled index bars into its analog universe"
    )

    seen.clear()
    summarizers._build_cross_ticker_history(
        "SPX", "2026-09-15",
        universe=_universe("AMD", "NDX", "^VIX", "SPX"),
    )
    assert sorted(seen[-1]["tickers"]) == ["NDX", "^VIX"], (
        "an index target pulled equity bars into its analog universe"
    )


def test_each_empty_universe_cause_is_persisted_not_just_logged(monkeypatch):
    """`cross_ticker.reason` must name WHICH cause, not point at Cloud Logs.

    Before this, all three `return None` paths collapsed into one literal
    string telling the reader to go read the warning in Cloud Logging. That
    is the same indistinguishable-value defect `cross_ticker_used=False`
    had, one layer up: a report consumer cannot tell "this watchlist has no
    same-class peers" (a curation fact) from "the peers have no bars" (an
    ingestion gap) from "the peers are too new" (a timing fact), and the
    three want different responses (Codex P2 on `775a29f`).
    """
    # Cause 1 — no same-class peers.
    frame, reason = summarizers._build_cross_ticker_history(
        "TGT", "2026-09-15", universe=_universe("^VIX", "^VVIX"))
    assert frame is None
    assert "asset class" in reason

    # Cause 2 — peers exist, no bars.
    monkeypatch.setattr(
        summarizers, "_query_strict", lambda sql, params=None: pd.DataFrame())
    frame, no_bars = summarizers._build_cross_ticker_history(
        "TGT", "2026-09-15", universe=_universe("AMD", "AVGO"))
    assert frame is None
    assert "none has daily bars" in no_bars

    # Cause 3 — peers have bars, but under the 60-bar feature minimum.
    short = pd.DataFrame({
        "ticker": ["AMD"] * 10,
        "date": pd.date_range("2026-08-01", periods=10).date,
        "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0,
    })
    monkeypatch.setattr(
        summarizers, "_query_strict", lambda sql, params=None: short)
    frame, too_short = summarizers._build_cross_ticker_history(
        "TGT", "2026-09-15", universe=_universe("AMD"))
    assert frame is None
    assert "enough history" in too_short

    assert len({reason, no_bars, too_short}) == 3, (
        "the three causes must be distinguishable by a report consumer"
    )


def test_the_index_set_covers_the_repos_cash_settled_index_roots():
    """`_CARETLESS_INDEX_SYMBOLS` is kept local so a Greeks-side edit cannot
    silently reclassify an asset class. That independence is only safe if
    the two cannot drift in the dangerous direction: anything
    `lib.options_greeks` treats as a cash-settled index root must still
    classify as an index here.
    """
    from lib.options_greeks import COMPUTE_GREEKS_TICKERS

    missing = sorted(
        t for t in COMPUTE_GREEKS_TICKERS
        if not summarizers._is_index_symbol(t)
    )
    assert not missing, (
        f"{missing} are index roots to the Greeks pipeline but would be "
        f"matched against equities as analogs"
    )


def test_the_analog_universe_reaches_the_persisted_report():
    """`cross_ticker.reason` on the bundle is not disclosure on its own.

    `build_context_bundle`'s output is transient. The persisted artifact is
    `InsightReport`, written to `insight_reports.report` (JSONB) via
    `model_dump_json()`, and it carries no backtest section. The sparse
    cross-ticker path still returns `available: True`, so the section never
    lands in `failed_sections` either — meaning the cause reached no report
    consumer and no API response. That is the unread-field shape Rule 3.7.1
    names, one layer further out than the thread that prompted it (Codex P2
    on `28162e4`).

    `InsightReport` sets `extra="forbid"`, so this is red until the field
    exists rather than silently accepted and dropped.
    """
    import json

    from lib.agents.schema import InsightReport

    detail = {
        "attempted": True,
        "used": False,
        "reason": "3 peer(s) had bars but none had enough history",
        "universe": {"owner": "default", "tickers": 16,
                     "resolution": "exact"},
    }
    fields = InsightReport.model_fields
    assert "analog_universe" in fields, (
        "the persisted report has no field for the cross-ticker provenance, "
        "so the cause dies with the transient bundle"
    )

    # And it must survive the exact serialization the DB write uses.
    assert json.loads(
        InsightReport.model_construct(analog_universe=detail)
        .model_dump_json()
    )["analog_universe"]["reason"] == detail["reason"]


def test_the_orchestrator_actually_populates_it():
    """A field nothing writes is the same unread disclosure in a new place.

    Checked by AST rather than regex: the `InsightReport(...)` call spans
    ~28 lines, so a line-anchored pattern cannot see its keywords.
    """
    import ast
    import pathlib

    src = pathlib.Path("lib/agents/orchestrator.py").read_text()
    calls = [
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "InsightReport"
    ]
    assert calls, "no InsightReport(...) construction found"
    supplied = {kw.arg for c in calls for kw in c.keywords}
    assert "analog_universe" in supplied, (
        "InsightReport is built without analog_universe, so the resolved "
        "universe and the empty-cause never reach the persisted report"
    )


# ---------------------------------------------------------------------------
# The injected universe has to belong to THIS cutoff
# ---------------------------------------------------------------------------


def test_a_universe_resolved_for_another_date_is_refused(capture):
    """Codex P2 on `e3463b3`.

    The injection point trusted whatever it was handed. A universe resolved
    for a different day selects peers from one date while the bars are
    queried at another, and `describe()` then persists that universe's
    `as_of` as this report's provenance -- a fabricated account of how the
    analog set was chosen, which is the exact failure this change exists to
    prevent, arriving through the parameter the change added.

    Reachable from precisely the usage the parameter invites: replay code
    that resolves once and reuses the object across dates. It was also live
    in this file -- `_universe` hardcoded 2026-09-15 while the default
    cutoff is today, so three tests here were injecting a mismatch.

    Refused rather than silently re-resolved: re-resolving would discard
    the caller's frozen universe, which is the one thing the parameter
    exists to guarantee.
    """
    with pytest.raises(ValueError) as excinfo:
        summarizers.summarize_backtest_metrics(
            "TGT",
            universe=_universe("AMD", "AVGO", as_of=datetime.date(2020, 1, 2)),
        )
    message = str(excinfo.value)
    assert "2020-01-02" in message and str(datetime.date.today()) in message
    assert not capture.resolved, (
        "the mismatch was papered over by re-resolving, which throws away "
        "the caller's frozen universe"
    )


def test_an_aware_datetime_cutoff_still_matches_its_own_calendar_date(capture):
    """The guard must normalize both sides or it rejects agreeing pairs.

    `datetime` subclasses `date`, so `cutoff` here can be an aware datetime
    while `WatchlistMembership.as_of` is always a plain date -- the same
    trap `28162e4` fixed one layer down in the resolver. A guard comparing
    them raw would raise on a universe that matches perfectly.
    """
    summarizers.summarize_backtest_metrics(
        "TGT",
        as_of=datetime.datetime(2026, 9, 15, 14, 30, tzinfo=datetime.timezone.utc),
        universe=_universe("AMD", "AVGO", as_of=datetime.date(2026, 9, 15)),
    )
    _, params = _cross_call(capture)
    assert sorted(params["tickers"]) == ["AMD", "AVGO"]
