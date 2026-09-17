"""The cross-ticker analog pull must be bounded by the watchlist.

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
than 10 analogs (summarizers.py:1118). Verified with the production
matcher against real bars at the production as_of of 2026-09-15:
NVDA 6, AMD 6 (both expand, both OOM'd); AVGO 29, SPY 194 (neither
expands, both completed). Four for four, and day-dependent rather than
ticker-dependent: NVDA had 41 same-ticker analogs on 09-12 and 32 on
09-16.

Bounded to the 15 other watchlist names the same production code gives
NVDA 65 analogs from 38,850 rows at a measured 9.1 MB peak, sourced from
AMD/AVGO/MRVL. So the fix makes the analysis cheaper AND better: the
unbounded universe was matching an equity's gap-and-volume setup against
`^VIX`, `^VIX3M` and `^VVIX`.
"""
from __future__ import annotations

import datetime
import logging

import numpy as np
import pandas as pd
import pytest

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


@pytest.fixture
def capture(monkeypatch):
    """Install a fake _query that records every SQL it is handed."""
    seen: list[tuple[str, dict]] = []

    def fake_query(sql: str, params=None):
        params = params or {}
        seen.append((sql, params))
        if "JOIN watchlists" in sql or "ticker <> :ticker" in sql:
            frames = []
            for i, tk in enumerate(("PEER1", "PEER2", "PEER3")):
                f = _bars(260, seed=100 + i)
                f.insert(0, "ticker", tk)
                frames.append(f)
            return pd.concat(frames, ignore_index=True)
        return _bars(230, seed=7)

    monkeypatch.setattr(summarizers, "_query", fake_query)
    return seen


def _cross_call(seen) -> tuple[str, dict]:
    matches = [(s, p) for s, p in seen
               if "watchlists" in s or "ticker <> :ticker" in s]
    assert matches, "the cross-ticker pull never ran; the test data no longer forces expansion"
    return matches[-1]


def _cross_sql(seen) -> str:
    return _cross_call(seen)[0]


def test_the_cross_ticker_pull_is_bounded_by_the_watchlist(capture):
    """Red before the fix: the query named no universe at all.

    This is the whole fix. Without a universe the query's cost scales with
    how many tickers happen to exist in market_data_daily, which is the
    shape CLAUDE.md Rule 3.8 forbids.
    """
    summarizers.summarize_backtest_metrics("TGT")
    sql = _cross_sql(capture)
    assert "watchlists" in sql, (
        "the cross-ticker analog pull does not bound its universe by "
        "`watchlists`, so it is every ticker in market_data_daily (2,609 on "
        "2026-09-16, 5,597,928 rows, 2.93 GiB in pandas)."
    )
    assert "w.removed_at IS NULL" in sql, (
        "the universe does not filter removed_at, so tickers removed from "
        "the watchlist stay in the analog universe forever."
    )


def test_the_universe_cannot_fan_out_when_two_users_watch_one_ticker(capture):
    """Codex P1 on `c75c22c`. Verified against the schema before fixing.

    `watchlists` is `PRIMARY KEY (user_id, ticker)`, and its own schema
    comment says 'default' is the shared list driving the brief/insight/
    signal jobs while "a signed-in user's rows are owned by their verified
    email". So one ticker can hold one row per user, and a plain
    `JOIN watchlists` returns every market-data bar once per subscriber.

    That is silent corruption, not an error: `_engineer` below groups by
    ticker and calls `.diff()`, `.rolling()`, `.ewm()` and `.shift(-n)` on
    the group, so duplicated dates are consumed as consecutive sessions.
    Every feature and every forward return is computed over a doubled
    series, and the analog statistics get weighted by subscriber count.

    Measured on production 2026-09-17: 16 active rows, 16 distinct tickers,
    1 distinct user. The defect is latent, which is exactly why it would
    have shipped. It fires the first time any signed-in user watches a
    ticker `default` already watches.

    A semi-join cannot multiply rows whatever the owner scoping later
    becomes, so that is what is pinned here rather than the scoping alone.
    """
    summarizers.summarize_backtest_metrics("TGT")
    sql = _cross_sql(capture)
    assert "EXISTS" in sql, (
        "the cross-ticker universe is not a semi-join, so a ticker watched "
        "by N users multiplies that ticker's bars N times."
    )
    assert "JOIN watchlists" not in sql, (
        "a row-multiplying `JOIN watchlists` is back; use EXISTS so the "
        "universe filters rather than joins."
    )


def test_the_universe_is_scoped_to_one_watchlist_owner(capture):
    """The analog set must not change when a stranger adds a ticker.

    `watchlists` holds every signed-in user's list alongside the shared
    `default` one. Reading all owners would let any user silently alter the
    forward-return statistics the insight reports are built on. The
    canonical read (`gcp/fetchers/_watchlist.py:91`) is owner-scoped and
    defaults to DEFAULT_USER_ID; this matches it.
    """
    from gcp.fetchers._watchlist import DEFAULT_USER_ID

    summarizers.summarize_backtest_metrics("TGT")
    sql, params = _cross_call(capture)
    assert "w.user_id = :watchlist_owner" in sql, (
        "the cross-ticker universe is not scoped to a single watchlist "
        "owner, so it is the union of every user's list."
    )
    assert params.get("watchlist_owner") == DEFAULT_USER_ID, (
        f"owner bound to {params.get('watchlist_owner')!r}, expected "
        f"DEFAULT_USER_ID ({DEFAULT_USER_ID!r})"
    )


def test_peers_match_the_targets_asset_class(capture):
    """Codex P2 on `1069e50`. An unconditional caret exclusion is wrong
    in one direction.

    ^VIX, ^VIX3M and ^VVIX were all in the unbounded universe, and a
    volatility index is not an analog for an equity's gap-and-volume
    setup. But excluding carets *unconditionally* means that when the
    target is itself an index with sparse same-ticker matches, every
    index peer is dropped and only equities remain -- the same cross-asset
    comparison, inverted. Match the target's class instead.

    Reachability, measured 2026-09-17: the `default` watchlist holds no
    caret ticker, so this predicate is a no-op today and the defect is
    latent. `SPX` was watchlisted (and removed 2026-04-30), so index-like
    symbols do get added.
    """
    summarizers.summarize_backtest_metrics("TGT")
    sql = _cross_sql(capture)
    assert "(left(m.ticker, 1) = '^') = (left(:ticker, 1) = '^')" in sql, (
        "the asset-class predicate is not relative to the target, so an "
        "index target would be compared against equities only."
    )


def test_the_universe_resolves_membership_at_the_cutoff(capture):
    """Codex P2 on `1069e50`. Future config must not leak into a replay.

    The bar predicate is cutoff-relative but `removed_at IS NULL` asked
    whether a row is active NOW, so an `INSIGHT_AS_OF` replay resolved its
    analog universe from today's watchlist. A ticker added after the
    cutoff leaked in; one removed after it vanished. Re-running the same
    historical date could therefore return different analog statistics
    purely because someone edited the watchlist in between -- the #822
    look-ahead class, reintroduced through a config table rather than
    through bars.

    Demonstrable on the live table, which has real mutation history:
    MSFT removed 2026-04-28, SPX removed 2026-04-30, MCK added 2026-05-04.
    A replay of 2026-04-29 should see SPX and must not see MCK.
    """
    summarizers.summarize_backtest_metrics(
        "TGT", as_of=datetime.date(2024, 9, 1))
    sql = _cross_sql(capture)
    assert "w.added_at" in sql, (
        "the universe does not bound `added_at` by the cutoff, so tickers "
        "watchlisted after the replay date leak into it."
    )
    assert "w.removed_at IS NULL OR w.removed_at" in sql, (
        "the universe still asks whether a row is active now rather than "
        "whether it was active at the cutoff."
    )
    assert "w.removed_at IS NULL AND" not in sql


def test_the_unbounded_form_is_gone(capture):
    """Guards the exact string that shipped the OOM."""
    summarizers.summarize_backtest_metrics("TGT")
    sql = _cross_sql(capture)
    assert "FROM market_data_daily \nWHERE" not in sql
    assert "FROM market_data_daily WHERE ticker <> :ticker" not in sql, (
        "the cross-ticker pull reverted to selecting from market_data_daily "
        "with no join."
    )


def test_no_limit_truncates_the_analog_sample(capture):
    """The bound belongs on the universe, not on the row count.

    A LIMIT would look like a fix and silently bias the sample: the query
    is ORDER BY ticker, so a LIMIT keeps only the alphabetically-early
    names. Forward-return statistics computed from an A-to-C slice of the
    watchlist are not the statistics they claim to be.
    """
    summarizers.summarize_backtest_metrics("TGT")
    sql = _cross_sql(capture)
    assert "LIMIT" not in sql.upper(), (
        "a LIMIT was added to the cross-ticker analog pull; it truncates "
        "the sample in ticker order rather than bounding the universe."
    )


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


def test_analogs_are_still_found_and_attributed_to_their_source(capture):
    """The fix must not break the thing the expansion exists to do.

    Bounding the universe changes which analogs are found, by design. It
    must not stop analogs being found, and each one must still name the
    ticker it came from.
    """
    out = summarizers.summarize_backtest_metrics("TGT")
    assert out["available"] is True
    assert out["cross_ticker_used"] is True, (
        "expansion did not fire, so this test is not exercising the "
        "cross-ticker path"
    )
    assert out["analog_count"] >= 3, out.get("note")
    sources = {a["ticker"] for a in out["top_analogs"]}
    assert sources - {"TGT"}, "no analog was attributed to a peer ticker"
    assert sources <= {"TGT", "PEER1", "PEER2", "PEER3"}, (
        f"analogs came from outside the universe the query returned: {sources}"
    )


def test_an_empty_universe_is_logged_not_silent(monkeypatch, caplog):
    """An empty watchlist must not read as 'this ticker has no analogs'.

    CLAUDE.md Rule 3.7: returning None here is correct (the caller reports
    cross_ticker_used=False), but doing it without a word makes an empty
    watchlist indistinguishable from a genuinely narrow market.
    """
    def fake_query(sql: str, params=None):
        if "watchlists" in sql:
            return pd.DataFrame()
        return _bars(230, seed=7)

    monkeypatch.setattr(summarizers, "_query", fake_query)
    with caplog.at_level(logging.WARNING, logger="lib.agents.summarizers"):
        result = summarizers._build_cross_ticker_history("TGT", "2026-09-15")
    assert result is None
    assert any("universe empty" in r.getMessage() for r in caplog.records), (
        "an empty analog universe produced no log line"
    )
