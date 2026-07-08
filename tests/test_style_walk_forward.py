"""Tests for Task 4.3: labeled walk-forward + persistence + run endpoint.

`lib.walk_forward.profile_to_signal_config` / `WalkForwardValidator.run_profile`
convert a mined `StyleProfile` (Task 4.2, `lib/style_miner.py`) into a
`SignalConfig` override and validate it via the EXISTING anchored fold loop
(`_run_anchored_folds`, shared with `run()`). `POST /api/style/mine-and-validate`
(`platform/api/routers/backtest.py`) wires the whole pipeline: closed-trade
prefilter -> mine -> pick top profile -> walk-forward -> persist
`user_style_results` + upsert `playbook_cards_staging`.

Three test classes:
  TestProfileToSignalConfig — the profile -> SignalConfig conversion (pure,
    no engine/DB involved): known-vocabulary mapping, unknown-condition
    ValueError, consec-N cross-check, and the documented
    "fires when >= N of the 5 factors are true" semantics pinned directly
    against `lib.signals.evaluate_signal`.
  TestRunProfileFoldMechanics — `WalkForwardValidator.run_profile`'s fold
    loop, with `lib.walk_forward.BacktestEngine` replaced by a capturing
    stub so the assertion is about WHICH SignalConfig/use_strat each fold's
    engine is built from, independent of real indicator/price realism.
  TestMineAndValidateEndpoint — the FastAPI endpoint, with the journal
    query / bar loaders / mine_style / WalkForwardValidator / persistence
    all monkeypatched (hermetic, mirrors tests/test_replay_labeled_trades.py's
    TestClient pattern) — pins the closed-trade prefilter (open trades
    excluded BEFORE mine_style sees them), the <10-honest path, and that
    persisted/staged values are percent-converted.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

from lib.backtest import BacktestResult
from lib.config import SignalConfig
from lib.signals import evaluate_signal
from lib.style_miner import StyleProfile
from lib.walk_forward import (
    WalkForwardResult, WalkForwardValidator, profile_to_signal_config,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLATFORM_DIR = PROJECT_ROOT / "platform"
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))


# ---------------------------------------------------------------------------
# TestProfileToSignalConfig — pure conversion, no engine/DB
# ---------------------------------------------------------------------------

class TestProfileToSignalConfig:
    def test_known_conditions_map_to_min_conditions_and_defaults(self):
        profile = StyleProfile(
            direction="CALL",
            conditions=["below_vwap", "rsi_25_50", "stoch_oversold"],
            support=4, total=5,
        )
        cfg = profile_to_signal_config(profile)
        base = SignalConfig()

        assert cfg.min_conditions == 3
        # Everything else stays at fresh SignalConfig() defaults — hard
        # seam #2: the miner mines against defaults, never a per-ticker
        # override, so validation must use the same defaults.
        assert cfg.consecutive_periods == base.consecutive_periods
        assert cfg.call_rsi_range == base.call_rsi_range
        assert cfg.put_rsi_range == base.put_rsi_range
        assert cfg.stoch_rsi_oversold == base.stoch_rsi_oversold
        assert cfg.stoch_rsi_overbought == base.stoch_rsi_overbought
        # Trading-logic fix (review of 1c7a7f35): the profile's conditions
        # are also translated to the internal factor-name allowlist, so
        # min_conditions is an EXACT gate, not an approximation.
        assert set(cfg.enabled_conditions) == {
            "below_vwap", "rsi_oversold_zone", "stoch_rsi_oversold",
        }

    def test_unknown_condition_raises_value_error(self):
        profile = StyleProfile(
            direction="PUT", conditions=["macd_bullish_cross"], support=5, total=5,
        )
        with pytest.raises(ValueError, match="unknown style condition"):
            profile_to_signal_config(profile)

    def test_consec_condition_matching_default_is_accepted(self):
        n = SignalConfig().consecutive_periods
        profile = StyleProfile(
            direction="CALL", conditions=[f"consec_down_ge_{n}"], support=5, total=5,
        )
        cfg = profile_to_signal_config(profile)
        assert cfg.min_conditions == 1
        assert cfg.consecutive_periods == n

    def test_consec_condition_mismatched_default_raises(self):
        n = SignalConfig().consecutive_periods
        stale_n = n + 1
        profile = StyleProfile(
            direction="PUT", conditions=[f"consec_up_ge_{stale_n}"], support=5, total=5,
        )
        with pytest.raises(ValueError, match="stale"):
            profile_to_signal_config(profile)

    def test_fires_when_conditions_true_not_when_one_missing(self):
        """The documented "requires >= N of the 5-factor set" semantics,
        pinned directly against `evaluate_signal` with a crafted row (no
        full day/engine loop needed — evaluate_signal is per-bar). CALL's
        5 factors: consecutive_down, rsi_oversold_zone (25-50), below_vwap,
        stoch_rsi_oversold, level_break_pdh. The profile names two of them
        (below_vwap, stoch_oversold) -> min_conditions=2."""
        profile = StyleProfile(
            direction="CALL", conditions=["below_vwap", "stoch_oversold"],
            support=4, total=5,
        )
        cfg = profile_to_signal_config(profile)

        # Both named factors true; RSI/consecutive/level-break false ->
        # score == 2 == min_conditions -> fires as CALL. RSI14=90 sits
        # outside BOTH the call (25-50) and put (50-75) bands.
        firing_row = pd.Series({
            "Consecutive_Down": 0, "Consecutive_Up": 0,
            "RSI14": 90.0,
            "Price_vs_VWAP": -0.5,   # below_vwap true
            "StochRSI_K": 10.0,      # stoch_oversold true
            "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
        })

        sig = evaluate_signal(
            firing_row,
            min_conditions=cfg.min_conditions,
            consecutive_periods=cfg.consecutive_periods,
            call_rsi_range=cfg.call_rsi_range,
            put_rsi_range=cfg.put_rsi_range,
            signal_config=cfg,
        )
        assert sig is not None
        assert sig["direction"] == "CALL"
        assert set(sig["conditions_met"]) == {"below_vwap", "stoch_rsi_oversold"}

        # Drop stoch_oversold (StochRSI_K=50 is neither oversold nor
        # overbought) -> score drops to 1 < min_conditions=2 -> no fire.
        not_firing_row = firing_row.copy()
        not_firing_row["StochRSI_K"] = 50.0
        sig2 = evaluate_signal(
            not_firing_row,
            min_conditions=cfg.min_conditions,
            consecutive_periods=cfg.consecutive_periods,
            call_rsi_range=cfg.call_rsi_range,
            put_rsi_range=cfg.put_rsi_range,
            signal_config=cfg,
        )
        assert sig2 is None

    def test_enabled_conditions_gate_blocks_off_profile_factor_combo(self):
        """Trading-logic CRITICAL fix (review of commit 1c7a7f35): before
        this fix, `min_conditions` alone was scored against the FULL
        5-factor set, so a bar could reach `min_conditions` via factors the
        profile never named. Worked example from the review: CALL profile
        {below_vwap, rsi_25_50} (min_conditions=2) used to FIRE on a bar
        where only consecutive_down + stoch_rsi_oversold were true (neither
        of which is below_vwap or rsi_oversold_zone). With `enabled_conditions`
        wired through (this test passes it explicitly, mirroring how
        `lib.backtest._check_entry` threads `self.signal.enabled_conditions`),
        that bar must NOT fire — the two off-profile factors contribute 0."""
        profile = StyleProfile(
            direction="CALL", conditions=["below_vwap", "rsi_25_50"],
            support=4, total=5,
        )
        cfg = profile_to_signal_config(profile)
        assert cfg.min_conditions == 2

        # consecutive_down + stoch_rsi_oversold true (the leak factors);
        # below_vwap / rsi_oversold_zone (the NAMED factors) false.
        leak_row = pd.Series({
            "Consecutive_Down": 5, "Consecutive_Up": 0,
            "RSI14": 90.0,           # outside both CALL (25-50) and PUT (50-75) bands
            "Price_vs_VWAP": 0.0,    # neither below_vwap nor above_vwap
            "StochRSI_K": 10.0,      # stoch_rsi_oversold true (not a named factor)
            "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 0,
        })

        # Sanity check: WITHOUT the gate (enabled_conditions=None, today's
        # default for every caller that doesn't opt in), this bar reaches
        # score 2 == min_conditions via the off-profile factors — this is
        # the exact leak the review flagged.
        leaked_sig = evaluate_signal(
            leak_row,
            min_conditions=cfg.min_conditions,
            consecutive_periods=cfg.consecutive_periods,
            call_rsi_range=cfg.call_rsi_range,
            put_rsi_range=cfg.put_rsi_range,
            signal_config=cfg,
        )
        assert leaked_sig is not None
        assert leaked_sig["direction"] == "CALL"
        assert set(leaked_sig["conditions_met"]) == {
            "consecutive_down", "stoch_rsi_oversold",
        }

        # With the allowlist wired through (the fix), the same bar must NOT
        # fire — below_vwap and rsi_oversold_zone are both false, and the
        # off-profile factors that WERE true no longer count.
        gated_sig = evaluate_signal(
            leak_row,
            min_conditions=cfg.min_conditions,
            consecutive_periods=cfg.consecutive_periods,
            call_rsi_range=cfg.call_rsi_range,
            put_rsi_range=cfg.put_rsi_range,
            signal_config=cfg,
            enabled_conditions=cfg.enabled_conditions,
        )
        assert gated_sig is None

    def test_call_profile_never_fires_put_via_enabled_conditions(self):
        """HIGH: direction gating falls out of the allowlist for free — CALL
        and PUT factor names never overlap (lib/signals.py), so a CALL
        profile's `enabled_conditions` list contains zero PUT factor names
        and `put_score` is forced to 0 on every bar, regardless of how many
        PUT-side conditions are actually true. Crafted "run" of several bars
        that each strongly satisfy the PUT-side factor set; zero of them may
        ever fire PUT once the CALL profile's allowlist is wired through."""
        profile = StyleProfile(
            direction="CALL", conditions=["below_vwap", "stoch_oversold"],
            support=4, total=5,
        )
        cfg = profile_to_signal_config(profile)

        # Every row below satisfies ALL 5 PUT-side factors (consecutive_up,
        # rsi_overbought_zone, above_vwap, stoch_rsi_overbought,
        # level_break_pdl) and NONE of the CALL-side factors — a bar that,
        # pre-fix, could fire PUT under a naive same-min_conditions check
        # applied to both directions.
        put_leaning_rows = [
            pd.Series({
                "Consecutive_Down": 0, "Consecutive_Up": 5,
                "RSI14": 60.0,             # rsi_overbought_zone (50-75) true
                "Price_vs_VWAP": 0.5,      # above_vwap true
                "StochRSI_K": 90.0,        # stoch_rsi_overbought true
                "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 1,
            }),
            pd.Series({
                "Consecutive_Down": 0, "Consecutive_Up": 4,
                "RSI14": 65.0,
                "Price_vs_VWAP": 1.2,
                "StochRSI_K": 85.0,
                "Broke_Prev_Day_High": 0, "Broke_Prev_Day_Low": 1,
            }),
        ]

        put_fires = 0
        for row in put_leaning_rows:
            sig = evaluate_signal(
                row,
                min_conditions=cfg.min_conditions,
                consecutive_periods=cfg.consecutive_periods,
                call_rsi_range=cfg.call_rsi_range,
                put_rsi_range=cfg.put_rsi_range,
                signal_config=cfg,
                enabled_conditions=cfg.enabled_conditions,
            )
            if sig is not None and sig["direction"] == "PUT":
                put_fires += 1

        assert put_fires == 0


# ---------------------------------------------------------------------------
# TestRunProfileFoldMechanics — fold loop, with BacktestEngine replaced by a
# capturing stub so the assertion is about config wiring, not price realism.
# ---------------------------------------------------------------------------

def _make_long_intraday(n_months=4, bars_per_day=60, seed=7):
    """Small synthetic multi-month 1-min frame — same shape
    tests/test_walk_forward.py's `_make_long_intraday` uses, kept local
    (and smaller) so this file doesn't depend on that test module's
    private helper staying importable."""
    import numpy as np
    np.random.seed(seed)
    frames = []
    base = 100.0
    start = pd.Timestamp("2024-01-02")
    end = start + pd.DateOffset(months=n_months)
    trading_days = pd.bdate_range(start, end)

    for day in trading_days:
        times = pd.date_range(f"{day.date()} 09:30", periods=bars_per_day, freq="1min")
        returns = np.random.normal(0, 0.001, bars_per_day)
        close = base * np.exp(np.cumsum(returns))
        high = close * (1 + np.abs(np.random.normal(0, 0.001, bars_per_day)))
        low = close * (1 - np.abs(np.random.normal(0, 0.001, bars_per_day)))
        open_ = pd.Series(close).shift(1).fillna(base).values
        volume = np.random.randint(10000, 100000, bars_per_day).astype(float)
        frames.append(pd.DataFrame({
            "Time": times, "Open": open_, "High": high, "Low": low,
            "Close": close, "Volume": volume,
        }, index=times))
        base = close[-1]

    return pd.concat(frames)


class _CapturingEngine:
    """Stand-in for `lib.backtest.BacktestEngine` that records every
    constructor kwargs dict + each `.run()` call's `use_strat`, and returns
    an empty (but well-formed) `BacktestResult` so `_aggregate_metrics` /
    `_calculate_stability` still run over real (empty) fold results."""
    calls: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        type(self).calls.append(kwargs)

    def run(self, test_df, use_strat=False, close_col="Close"):
        self.kwargs["use_strat"] = use_strat
        return BacktestResult(
            trades=[], daily_pnl=[], equity_curve=pd.Series(dtype=float),
            annualization_factor=252, filter_counts={},
        )


class TestRunProfileFoldMechanics:
    def test_engine_built_from_converted_signal_config_never_uses_strat(self, monkeypatch):
        import lib.walk_forward as wf_mod

        _CapturingEngine.calls = []
        monkeypatch.setattr(wf_mod, "BacktestEngine", _CapturingEngine)

        profile = StyleProfile(
            direction="CALL", conditions=["below_vwap", "stoch_oversold"],
            support=4, total=5,
        )
        expected_cfg = profile_to_signal_config(profile)

        df = _make_long_intraday(n_months=4)
        validator = WalkForwardValidator(train_months=2, test_months=1)
        result = validator.run_profile(df, profile)

        assert isinstance(result, WalkForwardResult)
        assert len(_CapturingEngine.calls) == len(result.fold_results)
        assert len(_CapturingEngine.calls) >= 1
        for kwargs in _CapturingEngine.calls:
            assert kwargs["signal_config"] == expected_cfg
            assert kwargs["use_strat"] is False

    def test_fold_count_matches_plain_run_on_same_df(self, monkeypatch):
        """run_profile's fold SLICING is identical to run()'s — same
        train/test windows, same count — only the signal_config differs."""
        import lib.walk_forward as wf_mod

        _CapturingEngine.calls = []
        monkeypatch.setattr(wf_mod, "BacktestEngine", _CapturingEngine)

        df = _make_long_intraday(n_months=4)
        profile = StyleProfile(
            direction="PUT", conditions=["above_vwap"], support=5, total=5,
        )
        validator = WalkForwardValidator(train_months=2, test_months=1)

        plain_result = validator.run(df)
        n_plain_folds = len(plain_result.fold_results)

        _CapturingEngine.calls = []
        profile_result = validator.run_profile(df, profile)

        assert len(profile_result.fold_results) == n_plain_folds


# ---------------------------------------------------------------------------
# TestMineAndValidateEndpoint — POST /api/style/mine-and-validate
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


def _journal_row(row_id, direction, status, entry_ts, exit_ts, source="manual"):
    return {
        "id": row_id, "direction": direction, "status": status, "source": source,
        "entry_ts": pd.Timestamp(entry_ts) if entry_ts else pd.NaT,
        "exit_ts": pd.Timestamp(exit_ts) if exit_ts else pd.NaT,
        "entry_price": 100.0, "exit_price": 101.0 if exit_ts else float("nan"),
    }


def _closed_rows(n, start_day=1):
    """`n` closed (status='win', exit_ts present) rows on distinct dates."""
    rows = []
    for i in range(n):
        day = start_day + i
        date_str = f"2026-06-{day:02d}"
        rows.append(_journal_row(
            f"closed-{i}", "CALL", "win",
            f"{date_str} 09:35:00", f"{date_str} 09:55:00",
        ))
    return rows


def _make_raw_loader_frame(date_str: str, n_bars: int = 40) -> pd.DataFrame:
    """Mimics `_replay_bar_loader`'s raw return shape (lowercase OHLCV +
    DatetimeIndex, no 'Time' column) — see test_replay_labeled_trades.py's
    identically-named helper."""
    times = pd.date_range(f"{date_str} 09:30", periods=n_bars, freq="1min")
    return pd.DataFrame({
        "open": [100.0] * n_bars, "high": [100.05] * n_bars,
        "low": [99.95] * n_bars, "close": [100.0] * n_bars,
        "volume": [1000.0] * n_bars,
    }, index=times)


class _StubValidator:
    """Replaces `backtest_router.WalkForwardValidator` in endpoint tests so
    the walk-forward's OWN correctness (tested above / in
    tests/test_walk_forward.py) doesn't need to be re-proven through a full
    HTTP round trip — only the endpoint's data flow and percent conversion."""
    captured_kwargs: dict = {}

    def __init__(self, **kwargs):
        type(self).captured_kwargs = kwargs

    def run_profile(self, df, profile, close_col="Close"):
        return WalkForwardResult(
            fold_results=[], fold_dates=[],
            aggregate_metrics={
                "avg_expectancy_pct": 0.0025,   # raw fraction == 0.25%
                "std_expectancy_pct": 0.0010,
                "avg_win_rate": 0.55,           # already 0-1 fraction
                "total_folds": 3,
                "total_trades_all_folds": 42,
            },
            stability_score=0.75,
        )


def test_endpoint_fewer_than_ten_closed_trades_returns_unavailable(client, monkeypatch):
    from api.routers import backtest as backtest_router

    def fake_journal_query(sql, params=None):
        return pd.DataFrame(_closed_rows(5))

    def fail_if_called(*a, **kw):
        raise AssertionError("mine_style must not be called below the 10-closed-trade floor")

    monkeypatch.setattr(backtest_router, "_HAS_CLOUD_SQL", True, raising=False)
    monkeypatch.setattr(backtest_router, "_replay_journal_query", fake_journal_query)
    monkeypatch.setattr(backtest_router, "mine_style", fail_if_called)
    monkeypatch.setattr(backtest_router, "_style_exec", fail_if_called)

    resp = client.post("/api/style/mine-and-validate", json={"ticker": "SPY"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unavailable"
    assert body["reason"] == "need >= 10 closed trades, have 5"


def test_endpoint_excludes_open_trades_before_mine_style(client, monkeypatch):
    """Hard seam: an ACTIVE (no exit_ts) row must never reach mine_style,
    even when it would push the RAW row count past 10. 10 closed + 3 open
    (13 total rows) -> mine_style must be called with exactly 10 entries."""
    from api.routers import backtest as backtest_router
    from lib.style_miner import StyleProfile as _SP

    open_rows = [
        _journal_row(f"open-{i}", "CALL", "active", "2026-06-20 09:35:00", None)
        for i in range(3)
    ]
    all_rows = _closed_rows(10) + open_rows

    def fake_journal_query(sql, params=None):
        return pd.DataFrame(all_rows)

    def fake_bar_loader(ticker_lower, date):
        return _make_raw_loader_frame(f"2026-06-{date[-2:]}")

    captured_mine_args = {}

    def fake_mine_style(entries, bars_by_date, min_support_frac=0.6):
        captured_mine_args["entries"] = entries
        return [_SP(direction="CALL", conditions=["below_vwap"], support=8, total=10)]

    monkeypatch.setattr(backtest_router, "_HAS_CLOUD_SQL", True, raising=False)
    monkeypatch.setattr(backtest_router, "_replay_journal_query", fake_journal_query)
    monkeypatch.setattr(backtest_router, "_replay_bar_loader", fake_bar_loader)
    monkeypatch.setattr(backtest_router, "mine_style", fake_mine_style)
    monkeypatch.setattr(backtest_router, "WalkForwardValidator", _StubValidator)
    monkeypatch.setattr(
        backtest_router, "_style_history_bar_loader",
        lambda ticker_upper: _make_raw_loader_frame("2026-06-01", n_bars=100).rename(
            columns={"open": "Open", "high": "High", "low": "Low",
                     "close": "Close", "volume": "Volume"}
        ),
    )
    persisted_calls = []
    monkeypatch.setattr(
        backtest_router, "_style_exec",
        lambda sql, params=None: persisted_calls.append((sql, params)),
    )

    resp = client.post("/api/style/mine-and-validate", json={"ticker": "SPY"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["staged"] is True

    assert len(captured_mine_args["entries"]) == 10
    assert {e["id"] for e in captured_mine_args["entries"]} == {
        f"closed-{i}" for i in range(10)
    }


def test_endpoint_no_profile_mined_returns_unavailable(client, monkeypatch):
    from api.routers import backtest as backtest_router

    def fake_journal_query(sql, params=None):
        return pd.DataFrame(_closed_rows(10))

    def fake_bar_loader(ticker_lower, date):
        return _make_raw_loader_frame(f"2026-06-{date[-2:]}")

    def fail_if_called(*a, **kw):
        raise AssertionError("must not walk-forward when mining produced no profile")

    monkeypatch.setattr(backtest_router, "_HAS_CLOUD_SQL", True, raising=False)
    monkeypatch.setattr(backtest_router, "_replay_journal_query", fake_journal_query)
    monkeypatch.setattr(backtest_router, "_replay_bar_loader", fake_bar_loader)
    monkeypatch.setattr(backtest_router, "mine_style", lambda entries, bars_by_date, min_support_frac=0.6: [])
    monkeypatch.setattr(backtest_router, "_style_history_bar_loader", fail_if_called)
    monkeypatch.setattr(backtest_router, "_style_exec", fail_if_called)

    resp = client.post("/api/style/mine-and-validate", json={"ticker": "SPY"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unavailable"
    assert "mining threshold" in body["reason"]


def test_endpoint_success_persists_percent_converted_values(client, monkeypatch):
    """Full happy path: response + both persistence calls use PERCENT units
    (avg_expectancy_pct, avg_return_bps), never the engine's raw fraction."""
    from api.routers import backtest as backtest_router
    from lib.style_miner import StyleProfile as _SP

    def fake_journal_query(sql, params=None):
        return pd.DataFrame(_closed_rows(10))

    def fake_bar_loader(ticker_lower, date):
        return _make_raw_loader_frame(f"2026-06-{date[-2:]}")

    top_profile = _SP(direction="CALL", conditions=["below_vwap", "rsi_25_50"], support=8, total=10)
    other_profile = _SP(direction="PUT", conditions=["above_vwap"], support=5, total=10)

    def fake_mine_style(entries, bars_by_date, min_support_frac=0.6):
        # other_profile has a lower support fraction (0.5 vs 0.8) -> top
        # profile selection must pick `top_profile`.
        return [other_profile, top_profile]

    def fake_history_loader(ticker_upper):
        raw = _make_raw_loader_frame("2026-06-01", n_bars=100)
        return raw.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        })

    persisted_calls = []

    monkeypatch.setattr(backtest_router, "_HAS_CLOUD_SQL", True, raising=False)
    monkeypatch.setattr(backtest_router, "_replay_journal_query", fake_journal_query)
    monkeypatch.setattr(backtest_router, "_replay_bar_loader", fake_bar_loader)
    monkeypatch.setattr(backtest_router, "mine_style", fake_mine_style)
    monkeypatch.setattr(backtest_router, "_style_history_bar_loader", fake_history_loader)
    monkeypatch.setattr(backtest_router, "WalkForwardValidator", _StubValidator)
    monkeypatch.setattr(
        backtest_router, "_style_exec",
        lambda sql, params=None: persisted_calls.append((sql, params)),
    )

    resp = client.post("/api/style/mine-and-validate", json={"ticker": "SPY"})
    assert resp.status_code == 200
    body = resp.json()

    assert body["staged"] is True
    assert body["profile"] == {
        "direction": "CALL", "conditions": ["below_vwap", "rsi_25_50"],
        "support": 8, "total": 10,
    }
    assert body["stability_score"] == pytest.approx(0.75)
    # PERCENT units: the stub's raw-fraction 0.0025 -> 0.25.
    assert body["aggregate_metrics"]["avg_expectancy_pct"] == pytest.approx(0.25)
    # win_rate stays a 0-1 fraction, untouched.
    assert body["aggregate_metrics"]["avg_win_rate"] == pytest.approx(0.55)

    assert len(persisted_calls) == 2
    style_sql, style_params = persisted_calls[0]
    assert "user_style_results" in style_sql
    assert style_params["avg_expectancy_pct"] == pytest.approx(0.25)
    assert style_params["avg_win_rate"] == pytest.approx(0.55)
    assert style_params["trained_on_trades"] == 10
    assert style_params["total_trades"] == 42

    playbook_sql, playbook_params = persisted_calls[1]
    assert "playbook_cards_staging" in playbook_sql
    assert "ON CONFLICT" in playbook_sql
    assert playbook_params["direction"] == "CALL"
    assert playbook_params["win_rate"] == pytest.approx(0.55)
    # bps = percent * 100 -> 0.25% == 25 bps.
    assert playbook_params["avg_return_bps"] == pytest.approx(25.0)
    assert playbook_params["sample_n"] == 42


def test_endpoint_zero_trades_across_folds_returns_unavailable(client, monkeypatch):
    """HIGH: when validation fires ZERO trades across all folds (common with
    strict all-conditions gates), must return unavailable instead of persisting
    a fabricated "0% win rate" card (CLAUDE.md Rule 3.7 violation).

    Uses _StubValidator but with total_trades_all_folds=0. Assert:
    - status code 200 with {"status": "unavailable", reason contains "zero trades"}
    - _style_exec was NOT called (no persistence happened)
    """
    from api.routers import backtest as backtest_router
    from lib.style_miner import StyleProfile as _SP

    def fake_journal_query(sql, params=None):
        return pd.DataFrame(_closed_rows(10))

    def fake_bar_loader(ticker_lower, date):
        return _make_raw_loader_frame(f"2026-06-{date[-2:]}")

    top_profile = _SP(direction="CALL", conditions=["below_vwap"], support=8, total=10)

    def fake_mine_style(entries, bars_by_date, min_support_frac=0.6):
        return [top_profile]

    def fake_history_loader(ticker_upper):
        raw = _make_raw_loader_frame("2026-06-01", n_bars=100)
        return raw.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        })

    class _ZeroTradesValidator:
        """Stub that returns zero trades across folds."""
        def __init__(self, **kwargs):
            pass

        def run_profile(self, df, profile, close_col="Close"):
            return WalkForwardResult(
                fold_results=[], fold_dates=[],
                aggregate_metrics={
                    "avg_expectancy_pct": 0.0,
                    "std_expectancy_pct": 0.0,
                    "avg_win_rate": 0.0,
                    "total_folds": 3,
                    "total_trades_all_folds": 0,  # ZERO TRADES — THE BUG CASE
                },
                stability_score=0.0,
            )

    persisted_calls = []

    monkeypatch.setattr(backtest_router, "_HAS_CLOUD_SQL", True, raising=False)
    monkeypatch.setattr(backtest_router, "_replay_journal_query", fake_journal_query)
    monkeypatch.setattr(backtest_router, "_replay_bar_loader", fake_bar_loader)
    monkeypatch.setattr(backtest_router, "mine_style", fake_mine_style)
    monkeypatch.setattr(backtest_router, "_style_history_bar_loader", fake_history_loader)
    monkeypatch.setattr(backtest_router, "WalkForwardValidator", _ZeroTradesValidator)
    monkeypatch.setattr(
        backtest_router, "_style_exec",
        lambda sql, params=None: persisted_calls.append((sql, params)),
    )

    resp = client.post("/api/style/mine-and-validate", json={"ticker": "SPY"})
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] == "unavailable"
    assert "zero trades" in body["reason"].lower()
    # CRITICAL: persistence must NOT happen
    assert len(persisted_calls) == 0


def test_endpoint_503_when_cloud_sql_not_configured(client, monkeypatch):
    from api.routers import backtest as backtest_router
    monkeypatch.setattr(backtest_router, "_HAS_CLOUD_SQL", False, raising=False)

    resp = client.post("/api/style/mine-and-validate", json={"ticker": "SPY"})
    assert resp.status_code == 503
