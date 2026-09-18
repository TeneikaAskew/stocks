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


def _universe(*tickers: str, as_of=datetime.date(2026, 9, 15),
              resolution: str = "exact") -> WatchlistMembership:
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
    assert "no analog universe" in empty["cross_ticker"]["reason"]

    off = summarizers.summarize_backtest_metrics("TGT", cross_ticker=False)
    assert off["cross_ticker"]["attempted"] is False
    assert "not needed" in off["cross_ticker"]["reason"]


def test_an_empty_universe_is_logged_not_silent(caplog):
    """An empty watchlist must not read as 'this ticker has no analogs'."""
    with caplog.at_level(logging.WARNING, logger="lib.agents.summarizers"):
        result = summarizers._build_cross_ticker_history(
            "TGT", "2026-09-15", universe=_universe())
    assert result is None
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
