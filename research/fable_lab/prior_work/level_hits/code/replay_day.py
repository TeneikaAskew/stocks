"""Replay the production brief offline for 2026-11-10 in the current
worktree (run with cwd = worktree root, PYTHONPATH=platform:.).
Inputs: Alpha Vantage daily fixture through 2026-11-06 (committed in the
repo) and Alpha Vantage 1-min bars for 2026-11-10 04:00-09:29 ET.
Usage: replay_day.py <session YYYY-MM-DD> <prior YYYY-MM-DD> <cutoff HH:MM> <av_dir> <out.json> [calibrated_params.json]"""
import json, sys, inspect
from datetime import date
from pathlib import Path
import pandas as pd
import pytest

SESSION, PRIOR = date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2])
CUT = sys.argv[3]
av, out = Path(sys.argv[4]), Path(sys.argv[5])
params_json = next((Path(a) for a in sys.argv[6:] if a.endswith(".json")), None)
STUB = "--stub-conditions" in sys.argv
pm_dir = out.parent / f"pm{CUT.replace(':','')}_{SESSION}_{out.stem}"
pm_dir.mkdir(parents=True, exist_ok=True)
for t in ("SPY", "QQQ", "IWM"):
    m = pd.read_csv(av / f"{t}_1min_{SESSION:%Y-%m}.csv", parse_dates=["timestamp"]).sort_values("timestamp")
    m = m[(m.timestamp >= f"{SESSION} 04:00") & (m.timestamp < f"{SESSION} {CUT}")]
    m.to_csv(pm_dir / f"{t}.csv", index=False)

import tests.lib.strat_2026_11_06 as fx

# Monday 2026-11-09 daily bar (Alpha Vantage TIME_SERIES_DAILY, unadjusted)
NOV9 = {"SPY": ["2026-11-09", 741.95, 755.42, 741.025, 752.69, 50281221],
        "QQQ": ["2026-11-09", 662.64, 682.48, 662.02, 679.35, 53587228],
        "IWM": ["2026-11-09", 277.44, 283.79, 276.81, 282.51, 28942482]}
_orig_raw = fx._raw()
_aug = {**_orig_raw, "tickers": {t: list(v) + ([NOV9[t]] if t in NOV9 and PRIOR >= date(2026, 11, 9) else []) for t, v in _orig_raw["tickers"].items()}}
try:
    import tests.lib.level_params_fixtures as lpf
except ImportError:
    lpf = None
from lib import strat_levels as sl
HAS_PARAMS = "params" in inspect.signature(sl.build_session_levels).parameters
res = {"session": str(SESSION), "cutoff": CUT, "code": "params" if HAS_PARAMS else "constants", "params_file": str(params_json) if params_json else None,
       "stub_conditions": STUB, "tickers": {}}
with pytest.MonkeyPatch.context() as mp:
    mp.setattr(fx, "SESSION", SESSION)
    mp.setattr(fx, "PRIOR", PRIOR)
    mp.setattr(fx, "PREMARKET_DIR", pm_dir)
    mp.setattr(fx, "_raw", lambda: _aug)
    orig_daily = fx.daily
    mp.setattr(fx, "daily", lambda t, through=PRIOR: orig_daily(t, through))
    PM_RULE = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--pm-rule=")), None)
    if PM_RULE:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import pm_rules
        def _pm_ctx(ticker, *, atr14="prior", raw=False, **_k):
            bars = fx.premarket_bars(ticker); d = fx.daily(ticker)
            return pm_rules.context(PM_RULE, ticker, bars["timestamp"], bars["open"], bars["high"], bars["low"],
                                    bars["close"], bars["volume"], float(d["Close"].iloc[-1]), float(d["Open"].iloc[-1]),
                                    fx.prior_atr(ticker))
        mp.setattr(fx, "premarket_context", _pm_ctx)
        res["pm_rule"] = PM_RULE
    db = None
    if HAS_PARAMS and params_json:
        db = lpf.calibrated_db(params_json)
        mp.setattr(lpf, "fixture_params", lambda t="TST", session_date=SESSION, **k: db.load([t], SESSION)[t])
    for t in ("SPY", "QQQ", "IWM"):
        frame = fx.loader_frame(t)
        if not STUB:
            from lib.indicators import add_all_indicators
            base = frame.iloc[:-1].copy()
            enriched = add_all_indicators(base.reset_index(drop=True)).set_index(base.index)
            for c in enriched.columns:
                if c not in frame.columns:
                    frame[c] = list(enriched[c]) + [float("nan")]
        with pytest.MonkeyPatch.context() as mp2:
            kw = {}
            if HAS_PARAMS:
                kw["params_db"] = db if db is not None else lpf.legacy_db(t)
            if not STUB:
                import gcp.premarket_brief as pb
                real_call, real_put = pb.check_call_conditions, pb.check_put_conditions
                orig_setattr = mp2.setattr
                def guarded(target, name, value=None, *a, **k):
                    if target is pb and name in ("check_call_conditions", "check_put_conditions"):
                        return None
                    return orig_setattr(target, name, value, *a, **k)
                mp2.setattr = guarded
            entry = fx.run_brief(mp2, t, frame, as_of=SESSION.isoformat(), **kw)
        maps = entry.pop("_persisted_level_maps", None) or []
        lv = []
        for lm in maps:
            for x in getattr(lm, "levels", []):
                d = x if isinstance(x, dict) else getattr(x, "__dict__", {})
                lv.append({k: d.get(k) for k in ("name", "level_name", "price", "timeframe", "level_type")})
        entry["_levels"] = lv
        plans = {}
        for direction in ("long", "short"):
            with pytest.MonkeyPatch.context() as mp3:
                kw = {"params_db": (db if db is not None else lpf.legacy_db(t))} if HAS_PARAMS else {}
                try:
                    _sec, ctx, pl, _n = fx.run_planner(mp3, t, frame, direction, **kw)
                    plans[direction] = [{"persona": x.persona, "entry": None if x.entry_zone is None else
                                         [x.entry_zone.low, x.entry_zone.high], "stop": x.stop,
                                         "targets": list(x.targets), "regime": x.regime, "size": getattr(x, "position_size_pct", None)} for x in pl]
                except Exception as exc:
                    plans[direction] = {"error": repr(exc)[:300]}
        entry["_plans"] = plans
        res["tickers"][t] = entry
out.write_text(json.dumps(res, default=str, indent=1))
print("ok", res["code"], {t: sorted(v.keys())[:60] for t, v in list(res["tickers"].items())[:1]})
