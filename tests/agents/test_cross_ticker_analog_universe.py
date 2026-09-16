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


def _cross_sql(seen) -> str:
    matches = [s for s, _ in seen if "watchlists" in s or "ticker <> :ticker" in s]
    assert matches, "the cross-ticker pull never ran; the test data no longer forces expansion"
    return matches[-1]


def test_the_cross_ticker_pull_is_bounded_by_the_watchlist(capture):
    """Red before the fix: the query named no universe at all.

    This is the whole fix. Without the join the query's cost scales with
    how many tickers happen to exist in market_data_daily, which is the
    shape CLAUDE.md Rule 3.8 forbids.
    """
    summarizers.summarize_backtest_metrics("TGT")
    sql = _cross_sql(capture)
    assert "JOIN watchlists" in sql, (
        "the cross-ticker analog pull does not join `watchlists`, so its "
        "universe is every ticker in market_data_daily (2,609 on "
        "2026-09-16, 5,597,928 rows, 2.93 GiB in pandas)."
    )
    assert "w.removed_at IS NULL" in sql, (
        "the watchlist join does not filter removed_at, so tickers removed "
        "from the watchlist stay in the analog universe forever."
    )


def test_the_cross_ticker_pull_excludes_index_symbols(capture):
    """A volatility index is not an analog for an equity's setup.

    ^VIX, ^VIX3M and ^VVIX were all in the unbounded universe. They are
    legitimately on the watchlist for the signal monitor, so the join
    alone does not exclude them.
    """
    summarizers.summarize_backtest_metrics("TGT")
    sql = _cross_sql(capture)
    assert "left(m.ticker, 1) <> '^'" in sql, (
        "index symbols (^VIX, ^VIX3M, ^VVIX) are not excluded from the "
        "analog universe."
    )


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
