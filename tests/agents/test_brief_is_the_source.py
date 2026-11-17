"""FEAT-INSIGHT-001 D2: for a brief ticker, nothing the brief holds is
recalculated.

build_context_bundle reads the session's live premarket_analysis row once and
fills the market, strat and session_levels sections from it. Every builder
that could recompute one of those values is replaced by a stand-in that
raises, so a call to any of them shows in the bundle as an exception reason
and in the recorded call list.

Spec: docs/superpowers/specs/2026-11-16-feat-insight-001-insight-one-plan-one-voice.md
(Design 1, decisions 2, 3 and 4).
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from lib.agents import summarizers
from tests.agents import insight_2026_11_16 as fx
from tests.agents.test_agent_orchestrator import canned_bundle  # noqa: F401  (pytest fixture)

SESSION = date(2026, 11, 16)
IWM_ONLY = frozenset({"IWM"})

# section key -> brief row column, as Design 1 maps them
MARKET_KEYS = {
    "close": "price", "rsi_14": "rsi", "sma_200": "sma200", "ema_9": "ema9",
    "ema_20": "ema20", "atr_14": "atr14", "bb_upper": "bb_upper",
    "bb_lower": "bb_lower", "rvol": "rvol", "volatility_20d": "volatility_20d",
    "vol_tag": "vol_regime", "macd_cross": "macd_cross",
    "above_sma_200": "above_sma200",
}
STRAT_KEYS = {
    "last_candle": "strat_candle", "in_force_combo": "strat_combo",
    "strat_setup": "strat_setup", "ftfc_score": "ftfc_score",
    "ftfc_direction": "ftfc_direction", "ftfc_labels": "ftfc_labels",
    "tf_continuity": "tf_continuity", "tf_continuity_frames": "tf_continuity_frames",
    "prev_day_high": "prev_day_high", "prev_day_low": "prev_day_low",
}
BRIEF_SECTIONS = ("market", "strat", "session_levels")


@pytest.fixture
def raising_builders(monkeypatch):
    """Every builder that could recompute what the brief row holds raises,
    and records that it was called."""
    import lib.level_calibration
    import lib.strat
    import lib.strat_levels

    called: list[str] = []

    def stand_in(name):
        def _raise(*_a, **_k):
            called.append(name)
            raise AssertionError("recalculated")
        return _raise

    monkeypatch.setattr(lib.strat, "compute_strat_status", stand_in("compute_strat_status"))
    monkeypatch.setattr(lib.strat_levels, "build_session_levels",
                        stand_in("build_session_levels"))
    monkeypatch.setattr(lib.strat_levels.SessionLevels, "with_premarket",
                        stand_in("SessionLevels.with_premarket"))
    monkeypatch.setattr(lib.strat_levels.SessionLevels, "from_basis",
                        classmethod(stand_in("SessionLevels.from_basis")))
    monkeypatch.setattr(lib.strat_levels, "_assemble", stand_in("_assemble"))
    monkeypatch.setattr(lib.level_calibration, "calibrate_ticker",
                        stand_in("calibrate_ticker"))
    return called


@pytest.fixture
def brief_db(monkeypatch):
    """_query_strict answers premarket_analysis from the fixture's brief row
    (or a frame or exception a test sets); every other read is empty."""
    state = {"brief": fx.brief_row("IWM"), "brief_raise": None, "list_raise": None,
             "watchlist": pd.DataFrame({"ticker": ["iwm", "QQQ", "spy"]})}
    reads: list[tuple[str, dict]] = []

    def strict(sql, params=None):
        reads.append((sql, dict(params or {})))
        if "FROM premarket_analysis" in sql:
            if state["brief_raise"] is not None:
                raise state["brief_raise"]
            return state["brief"]
        if "FROM watchlists" in sql:
            if state["list_raise"] is not None:
                raise state["list_raise"]
            return state["watchlist"]
        return pd.DataFrame()

    monkeypatch.setattr(summarizers, "_query_strict", strict)
    monkeypatch.setattr(summarizers, "_query", lambda sql, params=None: pd.DataFrame())
    return state, reads


def _brief_reads(reads):
    return [sql for sql, _ in reads if sql == summarizers.BRIEF_ROW_SQL]


def test_sections_equal_the_row_column_for_column(raising_builders, brief_db):
    state, reads = brief_db
    cell = state["brief"].iloc[0]
    bundle = summarizers.build_context_bundle("IWM", SESSION, brief_tickers=IWM_ONLY)

    market, strat, levels = (bundle[s] for s in BRIEF_SECTIONS)
    for section in (market, strat, levels):
        assert section["available"] is True
        assert section["source"] == "brief_row"
    for key, column in MARKET_KEYS.items():
        assert market[key] == cell[column], key
    assert market["premarket"] == fx.level_basis("IWM")["premarket"]
    assert market["date"] == "2026-11-16"
    for key, column in STRAT_KEYS.items():
        expected = cell[column]
        if column == "ftfc_labels":
            expected = json.loads(expected)
        assert strat[key] == expected, key
    assert strat["date"] == "2026-11-16"
    assert "trigger_high" not in strat and "trigger_low" not in strat
    assert levels["level_basis"] == fx.level_basis("IWM")
    assert levels["session_date"] == "2026-11-16"
    assert levels["premarket_status"] == fx.level_basis("IWM")["premarket_status"]

    assert bundle["brief_ref"]["analysis_date"] == "2026-11-16"
    assert bundle["brief_ref"]["run_kind"] == "live"
    assert not set(BRIEF_SECTIONS) & set(bundle["failed_sections"])
    assert len(_brief_reads(reads)) == 1
    assert raising_builders == []


def test_missing_row_makes_the_three_sections_unavailable(raising_builders, brief_db):
    state, _ = brief_db
    state["brief"] = pd.DataFrame()
    bundle = summarizers.build_context_bundle("IWM", SESSION, brief_tickers=IWM_ONLY)
    for name in BRIEF_SECTIONS:
        assert bundle[name] == {"available": False, "reason": "brief_row_missing"}
        assert name in bundle["failed_sections"]
        assert bundle["failed_section_reasons"][name] == "brief_row_missing"
    assert bundle["brief_ref"] is None
    assert raising_builders == []


def test_other_ticker_keeps_the_builder_path(canned_bundle, monkeypatch):  # noqa: F811
    strict_reads: list[str] = []

    def strict(sql, params=None):
        strict_reads.append(sql)
        return pd.DataFrame()

    monkeypatch.setattr(summarizers, "_query_strict", strict)
    real_strat = summarizers.summarize_strat_status
    strat_calls: list[str] = []

    def spy(ticker, *args, **kwargs):
        strat_calls.append(ticker)
        return real_strat(ticker, *args, **kwargs)

    monkeypatch.setattr(summarizers, "summarize_strat_status", spy)
    bundle = summarizers.build_context_bundle("NVDA", brief_tickers=IWM_ONLY)
    assert strat_calls == ["NVDA"]
    assert bundle["brief_ref"] is None
    assert bundle["session_levels"]["source"] == "level_basis"
    assert summarizers.BRIEF_ROW_SQL not in strict_reads


def test_brief_ticker_list_is_one_strict_read(raising_builders, brief_db):
    state, reads = brief_db
    assert summarizers.brief_tickers() == frozenset({"IWM", "QQQ", "SPY"})
    list_reads = [(sql, p) for sql, p in reads if "FROM watchlists" in sql]
    assert len(list_reads) == 1
    assert "in_brief = TRUE" in list_reads[0][0]
    assert list_reads[0][1] == {"u": "default"}

    state["list_raise"] = ConnectionError("connection refused")
    with pytest.raises(ConnectionError):
        summarizers.brief_tickers()
    with pytest.raises(ConnectionError):
        summarizers.build_context_bundle("IWM", SESSION)


def test_bundle_resolves_the_list_when_not_given(raising_builders, brief_db):
    _, reads = brief_db
    bundle = summarizers.build_context_bundle("IWM", SESSION)
    assert bundle["session_levels"]["source"] == "brief_row"
    assert len([sql for sql, _ in reads if "FROM watchlists" in sql]) == 1


def test_row_read_outage_is_not_brief_row_missing(raising_builders, brief_db):
    state, reads = brief_db
    state["brief_raise"] = ConnectionError("connection refused")
    bundle = summarizers.build_context_bundle("IWM", SESSION, brief_tickers=IWM_ONLY)
    for name in BRIEF_SECTIONS:
        assert bundle[name]["available"] is False
        assert name in bundle["failed_sections"]
        reason = bundle["failed_section_reasons"][name]
        assert reason.startswith("exception: ConnectionError"), reason
        assert reason != "brief_row_missing"
    assert bundle["brief_ref"] is None
    assert len(_brief_reads(reads)) == 1
    assert raising_builders == []


def test_thin_row(raising_builders, brief_db):
    state, _ = brief_db
    state["brief"] = fx.brief_row("IWM", level_basis=None)
    bundle = summarizers.build_context_bundle("IWM", SESSION, brief_tickers=IWM_ONLY)
    assert bundle["session_levels"]["available"] is False
    assert bundle["session_levels"]["reason"] == "brief_plan_missing"
    assert bundle["session_levels"]["level_basis"] is None
    assert bundle["failed_section_reasons"]["session_levels"] == "brief_plan_missing"
    assert bundle["market"]["available"] is True
    assert bundle["market"]["premarket"] is None
    assert bundle["strat"]["available"] is True

    stale = fx.level_basis("IWM")
    stale["status"] = "stale_daily"
    state["brief"] = fx.brief_row("IWM", level_basis=stale)
    bundle = summarizers.build_context_bundle("IWM", SESSION, brief_tickers=IWM_ONLY)
    assert bundle["session_levels"]["available"] is False
    assert bundle["session_levels"]["reason"] == "stale_daily"

    state["brief"] = fx.brief_row("IWM", ftfc_score=None)
    bundle = summarizers.build_context_bundle("IWM", SESSION, brief_tickers=IWM_ONLY)
    assert bundle["strat"]["ftfc_score"] is None
    assert raising_builders == []
