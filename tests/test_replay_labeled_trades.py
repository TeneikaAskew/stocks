"""Tests for Task 3.2: `replay_labeled_trades` (lib/backtest.py) and
`POST /api/backtest/replay-trades` (platform/api/routers/backtest.py).

Scores user-labeled journal trades against actual bars, benchmarking the
user's own exit against what BacktestEngine.simulate_exit (Task 3.1) would
have done from the same entry. UNITS: every *_pct field is TRUE PERCENT
(0.3-style values, not 0.003 engine fractions) — see lib/backtest.py's
`replay_labeled_trades` docstring for the conversion.

Three lib-level fixture cases (Step 1 of the task brief):
  (a) clean win whose user exit beats the system's stop
  (b) entry_price outside the entry bar's [low, high] -> fill_check flag,
      still scored
  (c) trade on a date with no bars in `bars_by_date` -> unavailable

Plus a TestClient case for the endpoint with the bar loader and journal
query indirections monkeypatched (hermetic — no real Cloud SQL/GCS).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

from lib.backtest import replay_labeled_trades
from lib.config import ExitConfig

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLATFORM_DIR = PROJECT_ROOT / "platform"
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))


# ---------------------------------------------------------------------------
# Fixture bars — 40 synthetic 1-min bars per date, uppercase OHLCV + a
# 'Time' column (the shape lib.indicators / lib.signals / lib.backtest all
# expect; mirrors what the router's `_normalize_bars_for_replay` produces
# from main.py's `_load_date_data`).
# ---------------------------------------------------------------------------

_EXIT_CFG = ExitConfig(
    call_target=0.0030, put_target=0.0038,
    call_stop=0.0015, put_stop=0.0020,
    call_time_stop=30, put_time_stop=35,
)


def _make_day_bars(date_str: str, entry_idx: int, prices: dict[int, float],
                    base: float = 100.0, n_bars: int = 40) -> pd.DataFrame:
    """Build a flat `n_bars`-long 1-min OHLCV frame for `date_str`, with
    specific bar closes overridden via `prices` (bar_idx -> close). Every
    bar's High/Low straddle its Close by a fixed +/-0.05 band unless the
    caller wants a narrower band (case (b) overrides Low/High directly by
    mutating the returned frame after construction)."""
    times = pd.date_range(f"{date_str} 09:30", periods=n_bars, freq="1min")
    closes = [prices.get(i, base) for i in range(n_bars)]
    df = pd.DataFrame({
        "Time": [str(t) for t in times],
        "Open": closes,
        "High": [c + 0.05 for c in closes],
        "Low": [c - 0.05 for c in closes],
        "Close": closes,
        "Volume": [1000.0] * n_bars,
    })
    return df


class TestReplayLabeledTradesLib:
    def test_clean_win_user_exit_beats_system_stop(self):
        """(a) Case a: bar6 (idx6) dumps -0.20% -> system CALL stop_loss
        fires immediately (call_stop=0.15%). The user's LABELED exit is
        much later at a +1.00% win — the user's actual return beats what
        the system would have banked. entry_idx=5 (<14) keeps
        system_signal_at_entry deterministically 'unavailable' (mirrors
        live.py's >=14-bar warm-up gate) without depending on indicator
        internals."""
        date_str = "2026-06-02"
        prices = {5: 100.00, 6: 99.80}
        for i in range(7, 40):
            prices[i] = 101.00
        bars = _make_day_bars(date_str, entry_idx=5, prices=prices)

        labeled = [{
            "id": "t-a",
            "direction": "CALL",
            "entry_ts": f"{date_str} 09:35:00",
            "entry_price": 100.00,
            "exit_ts": f"{date_str} 09:55:00",
            "exit_price": 101.00,
        }]

        result = replay_labeled_trades(
            labeled, {date_str: bars}, exit_config=_EXIT_CFG, ticker=None,
        )

        assert result["trades"], "expected one scorecard"
        card = result["trades"][0]
        assert card["id"] == "t-a"
        assert card["status"] == "ok"
        assert card["fill_check"] == "ok"

        # Percent units end-to-end: ~1.0, not ~0.01.
        expected_actual = (101.00 - 100.00) / 100.00 * 100.0
        assert card["actual_return_pct"] == pytest.approx(expected_actual, abs=1e-3)
        assert 0.5 < card["actual_return_pct"] < 5.0

        # System stopped out at -0.20% (percent units, not -0.002).
        expected_system = (99.80 - 100.00) / 100.00 * 100.0
        assert card["system_exit"]["exit_reason"] == "stop_loss"
        assert card["system_exit"]["return_pct"] == pytest.approx(expected_system, abs=1e-3)
        assert -1.0 < card["system_exit"]["return_pct"] < 0.0

        # exit_edge_bps = (user_return_pct - system_return_pct) * 100 (percent -> bps)
        expected_edge_bps = (expected_actual - expected_system) * 100.0
        assert card["exit_edge_bps"] == pytest.approx(expected_edge_bps, abs=1e-2)
        assert card["exit_edge_bps"] > 0  # user beat the system

        # <14-bar warm-up -> deterministic unavailable shape for the signal field.
        assert card["system_signal_at_entry"] == {"status": "unavailable"}

    def test_entry_price_outside_bar_range_still_scored(self):
        """(b) entry_price=105.00 is outside the entry bar's [104.95, 104.99]
        Low/High band -> fill_check flags it, but the trade is still scored
        (status stays 'ok'). direction=PUT exercises the sign-corrected
        return math end-to-end."""
        date_str = "2026-06-03"
        prices = {5: 104.97, 6: 104.50}
        for i in range(7, 40):
            prices[i] = 104.50
        bars = _make_day_bars(date_str, entry_idx=5, prices=prices)
        # Narrow the entry bar's range so entry_price=105.00 falls outside it.
        bars.loc[5, "Low"] = 104.95
        bars.loc[5, "High"] = 104.99

        labeled = [{
            "id": "t-b",
            "direction": "PUT",
            "entry_ts": f"{date_str} 09:35:00",
            "entry_price": 105.00,
            "exit_ts": f"{date_str} 09:50:00",
            "exit_price": 103.00,
        }]

        result = replay_labeled_trades(
            labeled, {date_str: bars}, exit_config=_EXIT_CFG, ticker=None,
        )

        card = result["trades"][0]
        assert card["id"] == "t-b"
        assert card["status"] == "ok"
        assert card["fill_check"] == "price_outside_bar_range"

        # PUT: actual_return_pct is sign-corrected (price down = user win).
        raw_pct = (103.00 - 105.00) / 105.00 * 100.0
        expected_actual = -raw_pct
        assert card["actual_return_pct"] == pytest.approx(expected_actual, abs=1e-3)
        assert card["actual_return_pct"] > 0

        # System: unrealized (105.00 - 104.50) / 105.00 = 0.4762% >= put_target
        # (0.38%) -> 'target' at bar6, sign-corrected the same way.
        assert card["system_exit"]["exit_reason"] == "target"
        expected_system = (105.00 - 104.50) / 105.00 * 100.0
        assert card["system_exit"]["return_pct"] == pytest.approx(expected_system, abs=1e-3)

        expected_edge_bps = (expected_actual - expected_system) * 100.0
        assert card["exit_edge_bps"] == pytest.approx(expected_edge_bps, abs=1e-2)

    def test_missing_bars_for_date_is_unavailable(self):
        """(c) The trade's date has no entry in `bars_by_date` at all ->
        unavailable, never zero-filled (CLAUDE.md Rule 3.7)."""
        labeled = [{
            "id": "t-c",
            "direction": "CALL",
            "entry_ts": "2026-06-04 09:35:00",
            "entry_price": 100.00,
            "exit_ts": "2026-06-04 09:50:00",
            "exit_price": 101.00,
        }]

        result = replay_labeled_trades(labeled, {}, exit_config=_EXIT_CFG, ticker=None)

        card = result["trades"][0]
        assert card["id"] == "t-c"
        assert card["status"] == "unavailable"
        assert card.get("reason")
        # Never zero-filled: no fabricated return/exit fields on an
        # unavailable card.
        assert "actual_return_pct" not in card
        assert "system_exit" not in card

    def test_aggregate_across_all_three_cases(self):
        """Aggregate combines all three cases: n=3, scored_n=2 (a and b are
        'ok'; c is 'unavailable'), win_rate=1.0 (both scored trades are
        wins), agreement fields present even though both scored trades'
        system_signal_at_entry is the deterministic 'unavailable' shape
        (entry_idx=5 < 14-bar warm-up in both a and b)."""
        date_a, date_b = "2026-06-02", "2026-06-03"
        prices_a = {5: 100.00, 6: 99.80}
        for i in range(7, 40):
            prices_a[i] = 101.00
        bars_a = _make_day_bars(date_a, entry_idx=5, prices=prices_a)

        prices_b = {5: 104.97, 6: 104.50}
        for i in range(7, 40):
            prices_b[i] = 104.50
        bars_b = _make_day_bars(date_b, entry_idx=5, prices=prices_b)
        bars_b.loc[5, "Low"] = 104.95
        bars_b.loc[5, "High"] = 104.99

        labeled = [
            {
                "id": "t-a", "direction": "CALL",
                "entry_ts": f"{date_a} 09:35:00", "entry_price": 100.00,
                "exit_ts": f"{date_a} 09:55:00", "exit_price": 101.00,
            },
            {
                "id": "t-b", "direction": "PUT",
                "entry_ts": f"{date_b} 09:35:00", "entry_price": 105.00,
                "exit_ts": f"{date_b} 09:50:00", "exit_price": 103.00,
            },
            {
                "id": "t-c", "direction": "CALL",
                "entry_ts": "2026-06-04 09:35:00", "entry_price": 100.00,
                "exit_ts": "2026-06-04 09:50:00", "exit_price": 101.00,
            },
        ]

        result = replay_labeled_trades(
            labeled, {date_a: bars_a, date_b: bars_b},
            exit_config=_EXIT_CFG, ticker=None,
        )

        agg = result["aggregate"]
        assert agg["n"] == 3
        assert agg["scored_n"] == 2
        assert agg["win_rate"] == pytest.approx(1.0)
        assert agg["avg_return_pct"] > 0
        # Both scored trades' system_signal_at_entry lack a 'direction' key
        # (the <14-bar 'unavailable' shape) -> neither is system-resolved,
        # so the denominator is 0 and the rate is an honest None (never a
        # fabricated 0.0 -- CLAUDE.md Rule 3.7).
        assert agg["system_resolved_n"] == 0
        assert agg["system_no_signal_n"] == 0
        assert agg["system_agreement_rate"] is None
        assert agg["avg_exit_edge_bps"] > 0

    def test_agreement_rate_counts_only_system_resolved_trades(self, monkeypatch):
        """Finding 1 (medium): system_agreement_rate must not conflate
        unavailable/no-signal with disagreement. Three trades on one date:
          - t-warmup: entry_idx=5 (<14 warm-up) -> system_signal_at_entry
            stays the deterministic 'unavailable' shape.
          - t-match: entry_idx=20 (>=14), evaluate_signal monkeypatched to
            return a CALL matching the labeled direction -> resolved +
            agreement.
          - t-nosignal: entry_idx=25 (>=14), evaluate_signal monkeypatched
            to return None -> benchmark ran, no setup.
        Expect: only t-match counts toward the denominator ->
        system_resolved_n=1, system_no_signal_n=1,
        system_agreement_rate=1/1=1.0 (not diluted by the other two)."""
        import lib.backtest as backtest_mod

        date_str = "2026-06-05"
        prices = {5: 100.00, 20: 100.00, 25: 100.00}
        for i in range(30, 40):
            prices[i] = 100.50
        bars = _make_day_bars(date_str, entry_idx=5, prices=prices)

        # Marker column survives add_signal_indicators (it does `df.copy()`
        # then only adds new indicator columns), so the monkeypatched
        # evaluate_signal below can key off it deterministically without
        # needing to hand-craft real indicator-triggering price action.
        bars["_marker"] = "none"
        bars.loc[20, "_marker"] = "match"
        bars.loc[25, "_marker"] = "nosignal"

        def fake_evaluate_signal(row, *args, **kwargs):
            marker = row.get("_marker")
            if marker == "match":
                return {"direction": "CALL", "total_score": 5}
            return None

        monkeypatch.setattr(backtest_mod, "evaluate_signal", fake_evaluate_signal)

        labeled = [
            {
                "id": "t-warmup", "direction": "CALL",
                "entry_ts": f"{date_str} 09:35:00", "entry_price": 100.00,
                "exit_ts": f"{date_str} 10:00:00", "exit_price": 100.50,
            },
            {
                "id": "t-match", "direction": "CALL",
                "entry_ts": f"{date_str} 09:50:00", "entry_price": 100.00,
                "exit_ts": f"{date_str} 10:00:00", "exit_price": 100.50,
            },
            {
                "id": "t-nosignal", "direction": "CALL",
                "entry_ts": f"{date_str} 09:55:00", "entry_price": 100.00,
                "exit_ts": f"{date_str} 10:00:00", "exit_price": 100.50,
            },
        ]

        result = replay_labeled_trades(
            labeled, {date_str: bars}, exit_config=_EXIT_CFG, ticker=None,
        )

        agg = result["aggregate"]
        assert agg["scored_n"] == 3
        assert agg["system_resolved_n"] == 1
        assert agg["system_no_signal_n"] == 1
        assert agg["system_agreement_rate"] == pytest.approx(1.0)

    def test_ok_card_invariant_raises_on_missing_numeric_field(self):
        """LOW finding: a status=='ok' card missing exit_edge_bps or
        actual_return_pct must raise loudly (not silently skip) when the
        aggregate is built."""
        from lib.backtest import _aggregate_scorecards

        bad_cards = [{
            "id": "t-bad",
            "status": "ok",
            "actual_return_pct": None,
            "fill_check": "ok",
            "system_signal_at_entry": {"status": "unavailable"},
            "system_exit": {"exit_reason": None, "return_pct": None, "exit_time": None},
            "exit_edge_bps": None,
            "_labeled_direction": "CALL",
        }]
        with pytest.raises(ValueError, match="t-bad"):
            _aggregate_scorecards(bad_cards)

    def test_nan_entry_price_is_unavailable(self):
        """INFO finding: a NaN entry_price (e.g. a float NaN surviving a
        pandas round-trip) must be treated the same as None/0 -- unavailable,
        never a silent NaN-poisoned return calculation."""
        date_str = "2026-06-06"
        bars = _make_day_bars(date_str, entry_idx=5, prices={5: 100.00})

        labeled = [{
            "id": "t-nan",
            "direction": "CALL",
            "entry_ts": f"{date_str} 09:35:00",
            "entry_price": float("nan"),
            "exit_ts": f"{date_str} 09:50:00",
            "exit_price": 101.00,
        }]

        result = replay_labeled_trades(
            labeled, {date_str: bars}, exit_config=_EXIT_CFG, ticker=None,
        )

        card = result["trades"][0]
        assert card["id"] == "t-nan"
        assert card["status"] == "unavailable"
        assert card["reason"] == "invalid entry price"


# ---------------------------------------------------------------------------
# Endpoint: POST /api/backtest/replay-trades
# ---------------------------------------------------------------------------

pytest.importorskip("fastapi")

import os  # noqa: E402


@pytest.fixture(scope="module")
def client():
    original_cwd = os.getcwd()
    os.chdir(str(PLATFORM_DIR))

    from starlette.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:
        yield c

    os.chdir(original_cwd)


def _journal_rows_df():
    """Two closed rows (one win) + one still-active row (NULL exit)."""
    return pd.DataFrame([
        {
            "id": "row-1", "direction": "CALL",
            "entry_ts": pd.Timestamp("2026-06-02 09:35:00"),
            "exit_ts": pd.Timestamp("2026-06-02 09:55:00"),
            "entry_price": 100.00, "exit_price": 101.00,
        },
        {
            "id": "row-2", "direction": "CALL",
            "entry_ts": pd.Timestamp("2026-06-02 09:40:00"),
            "exit_ts": pd.NaT,
            "entry_price": 100.00, "exit_price": float("nan"),
        },
    ])


def _make_raw_loader_frame(date_str: str, prices: dict[int, float], n_bars: int = 40) -> pd.DataFrame:
    """Mimics main.py's `_load_date_data` return contract exactly: lowercase
    open/high/low/close/volume columns + a DatetimeIndex, NO 'Time' column
    — what `_replay_bar_loader` really hands back before
    `_normalize_bars_for_replay` reshapes it for lib.backtest."""
    times = pd.date_range(f"{date_str} 09:30", periods=n_bars, freq="1min")
    closes = [prices.get(i, 100.0) for i in range(n_bars)]
    return pd.DataFrame({
        "open": closes,
        "high": [c + 0.05 for c in closes],
        "low": [c - 0.05 for c in closes],
        "close": closes,
        "volume": [1000.0] * n_bars,
    }, index=times)


def test_replay_trades_endpoint_scores_closed_marks_active_unavailable(client, monkeypatch):
    from api.routers import backtest as backtest_router

    prices = {5: 100.00, 6: 99.80}
    for i in range(7, 40):
        prices[i] = 101.00
    bars = _make_raw_loader_frame("2026-06-02", prices)

    # Returns the RAW `_load_date_data` shape (lowercase cols + DatetimeIndex)
    # so this test exercises the real `_normalize_bars_for_replay` reshape,
    # not just a bypassed pass-through.
    def fake_bar_loader(ticker_lower, date):
        assert ticker_lower == "spy"
        return bars

    def fake_journal_query(sql, params=None):
        return _journal_rows_df()

    monkeypatch.setattr(backtest_router, "_HAS_CLOUD_SQL", True, raising=False)
    monkeypatch.setattr(backtest_router, "_replay_bar_loader", fake_bar_loader)
    monkeypatch.setattr(backtest_router, "_replay_journal_query", fake_journal_query)

    resp = client.post("/api/backtest/replay-trades", json={
        "ticker": "SPY", "trade_ids": ["row-1", "row-2"],
    })
    assert resp.status_code == 200
    body = resp.json()

    cards = {c["id"]: c for c in body["trades"]}
    assert cards["row-1"]["status"] == "ok"
    assert cards["row-1"]["actual_return_pct"] == pytest.approx(1.0, abs=1e-6)
    assert cards["row-2"]["status"] == "unavailable"
    assert cards["row-2"]["reason"] == "trade still open"

    assert body["aggregate"]["n"] == 2
    assert body["aggregate"]["scored_n"] == 1


def test_replay_trades_endpoint_422_without_trade_ids_or_session(client):
    resp = client.post("/api/backtest/replay-trades", json={"ticker": "SPY"})
    assert resp.status_code == 422


def test_replay_trades_endpoint_404_when_no_rows_match(client, monkeypatch):
    from api.routers import backtest as backtest_router

    def empty_query(sql, params=None):
        return pd.DataFrame()

    monkeypatch.setattr(backtest_router, "_HAS_CLOUD_SQL", True, raising=False)
    monkeypatch.setattr(backtest_router, "_replay_journal_query", empty_query)

    resp = client.post("/api/backtest/replay-trades", json={
        "ticker": "SPY", "trade_ids": ["nope"],
    })
    assert resp.status_code == 404
