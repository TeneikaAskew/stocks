"""The ATR levels spec's "Display only" cases (FEAT-STRAT-001, 2026-11-11).

Each case builds one session and projects every plan decision the ATR rungs
must not move: both sides' trigger, stop, gate_targets, plan targets,
skipped list, target_status, reason, regime, candidates and ladder, the
LevelMap's NEXT LEVELS ladders and trigger dicts, the premarket_analysis
structured playbook columns the brief writes, the persisted levels and the
PMG zones. Timestamps (built_at, as_of) are not decisions and are left out.

tests/fixtures/atr_levels_display_only_base.json holds this projection as
the implementation PR's base (fix/feat-strat-001-brief-exits-in-thirds,
1054b46a) computes it, written by running this module there:

    git worktree add --detach /tmp/base origin/fix/feat-strat-001-brief-exits-in-thirds
    cp tests/lib/atr_levels_display_only.py /tmp/base/tests/lib/
    cd /tmp/base && python3 -m tests.lib.atr_levels_display_only > out.json

tests/fixtures/atr_levels_brief_base.json holds, the same way
(`python3 -m tests.lib.atr_levels_display_only brief`), the ticker entries
gcp.premarket_brief writes for SPY, QQQ and IWM on the committed 2026-11-06
fixture (tests/lib/strat_2026_11_06.run_brief, the production brief path
offline): every column, with level_basis's random run_id and built_at and
the persisted LevelMap objects (timestamps) left out.

The module uses only names the base also has, so the same file runs on
both and the test compares the head's projection with the base's.
"""
from __future__ import annotations

import json
import sys
from datetime import date

import numpy as np
import pandas as pd

from lib.strat_levels import SessionLevels, build_session_levels
from tests.lib.level_params_fixtures import fixture_params
from tests.lib.session_levels_helpers import D8_LEVELS, basis, d8_params, d8_session

RUNG_KEYS = ("atr_rung_anchors", "atr_rung_step_atr", "atr_rung_max_atr", "atr_rung_stretch_atr")
BUILD_SESSION = date(2026, 3, 27)


def _daily_frame() -> pd.DataFrame:
    """60 weekday bars ending the session before BUILD_SESSION."""
    rng = np.random.default_rng(7)
    dates = pd.bdate_range(end="2026-03-26", periods=60)
    close = 250 * np.exp(np.cumsum(rng.normal(0.0, 0.012, len(dates))))
    high = close * (1 + np.abs(rng.normal(0, 0.006, len(dates))))
    low = close * (1 - np.abs(rng.normal(0, 0.006, len(dates))))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    return pd.DataFrame({"Date": dates, "Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": 1_000_000})


def _built() -> SessionLevels:
    df = _daily_frame()
    prior = float(df["Close"].iloc[-1])
    premarket = {"date": BUILD_SESSION.isoformat(), "pre_high": round(prior * 1.004, 2),
                 "pre_low": round(prior * 0.997, 2), "pre_vwap": round(prior * 1.001, 2),
                 "pre_filter_status": "ok"}
    params = fixture_params("TST", BUILD_SESSION, overrides={
        "trigger_window_long_atr": 2.6, "trigger_window_short_atr": 2.6,
        "target_min_spacing_atr": 0.25})
    atr = float((df["High"] - df["Low"]).tail(14).mean())
    return build_session_levels("TST", BUILD_SESSION, df, {"atr_14": atr}, premarket, params)


def cases() -> dict:
    out = {
        "design_8": lambda: d8_session(),
        "atr_24_windows_1.6": lambda: d8_session(atr=24.0, window=1.6),
        "spacing_not_ok": lambda: d8_session(
            statuses={"target_min_spacing_atr": "insufficient_history"}),
        "no_premarket": lambda: SessionLevels.from_basis(basis(
            D8_LEVELS, prior_close=247.00, atr=14.0, premarket=None, params=d8_params())),
        "build_session_levels": _built,
    }
    for key in RUNG_KEYS:
        status = "input_unavailable" if key == "atr_rung_anchors" else "insufficient_history"
        out[f"{key}_not_ok"] = (lambda k=key, st=status: d8_session(statuses={k: st}))
    return out


def _side(s) -> dict:
    return {
        "trigger": s.trigger, "stop": s.stop, "gate_targets": s.gate_targets,
        "targets": s.targets, "skipped": s.skipped, "target_status": s.target_status,
        "reason": s.reason, "regime": s.regime, "candidates": s.candidates,
        "ladder": s.ladder, "room_pct": s.room_pct, "distance_atr": s.distance_atr,
        "plan": s.plan,
    }


def project(sl: SessionLevels) -> dict:
    from gcp.premarket_brief import structured_playbook_columns

    lm = sl.to_level_map()
    return {
        "long": _side(sl.long), "short": _side(sl.short),
        "reference": sl.reference, "premarket_status": sl.premarket_status,
        "levels": [(lv.name, lv.price, lv.timeframe, lv.level_type) for lv in sl.levels],
        "pmg_zones": sl.pmg_zones,
        "level_map": {
            "levels": [(lv.name, lv.price) for lv in lm.levels],
            "calls_trigger": lm.calls_trigger, "puts_trigger": lm.puts_trigger,
            "call_levels": lm.call_levels, "put_levels": lm.put_levels,
            "room_to_run_up": lm.room_to_run_up, "room_to_run_down": lm.room_to_run_down,
            "regime_long": lm.regime_long, "regime_short": lm.regime_short,
            "reason_long": lm.reason_long, "reason_short": lm.reason_short,
        },
        "columns": structured_playbook_columns(lm),
    }


def projections() -> dict:
    """Every case's projection, round-tripped through JSON as stored."""
    return json.loads(json.dumps({name: project(build()) for name, build in cases().items()},
                                 sort_keys=True, default=str))


BRIEF_TICKERS = ("SPY", "QQQ", "IWM")


def _strip_run_ids(x):
    if isinstance(x, dict):
        return {k: _strip_run_ids(v) for k, v in x.items() if k not in ("run_id", "built_at")}
    if isinstance(x, list):
        return [_strip_run_ids(v) for v in x]
    return x


def brief_entries(monkeypatch=None) -> dict:
    """The brief's ticker entries for BRIEF_TICKERS, as stored (JSON)."""
    import pytest

    from tests.lib import strat_2026_11_06 as fx

    own = monkeypatch is None
    mp = pytest.MonkeyPatch() if own else monkeypatch
    out = {}
    try:
        for t in BRIEF_TICKERS:
            e = dict(fx.run_brief(mp, t, fx.loader_frame(t)))
            e.pop("_persisted_level_maps", None)
            e["level_basis"] = _strip_run_ids(e.get("level_basis"))
            out[t] = json.loads(json.dumps(e, sort_keys=True, default=str))
    finally:
        if own:
            mp.undo()
    return out


if __name__ == "__main__":
    data = brief_entries() if sys.argv[1:] == ["brief"] else projections()
    json.dump(data, sys.stdout, sort_keys=True, indent=1)
    sys.stdout.write("\n")
