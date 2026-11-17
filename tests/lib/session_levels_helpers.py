"""Small builders for SessionLevels test fixtures (FEAT-STRAT-001).

`basis(...)` writes a level_basis dict the way the brief stores it, and
`session(...)` reads it back through SessionLevels.from_basis, the path every
live consumer uses, so the picks come from the one builder's rules.
"""
from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

import lib.strat_levels as _strat_levels
from lib.strat_levels import ATR_RUNG_KEYS, LEVEL_RULE_VERSION, LevelParams, SessionLevels, SideLevels
from tests.lib.level_params_fixtures import fixture_params

_TF = {"D": "day", "W": "week", "M": "month", "Q": "quarter", "Y": "year"}
_KIND = {"H": "high", "L": "low", "C": "close", "O": "open"}


def _level(name: str, price: float) -> dict:
    if name.startswith("parent_bar_"):
        return {"name": name, "price": float(price), "timeframe": "day",
                "level_type": name.rsplit("_", 1)[1], "period_label": ""}
    tf = _TF.get(name[1], "day") if len(name) == 3 else "day"
    kind = _KIND.get(name[-1], "pivot")
    return {"name": name, "price": float(price), "timeframe": tf,
            "level_type": kind, "period_label": ""}


def basis(levels: dict, *, prior_close: float, atr, premarket: dict | None = None,
          session_date: date = date(2026, 11, 6), reference: float | None = None,
          ticker: str = "TST", params: LevelParams | None = None) -> dict:
    """`params` defaults to fixture_params (every key ok at the #1753
    values), recorded on the basis as the brief records them; `atr` is the
    ATR(14), the policy's day-one basis. A premarket snapshot is recorded as
    filtered unless it says otherwise."""
    pm = None
    if premarket is not None:
        pm = {"date": session_date.isoformat(), "pre_filter_status": "ok", **premarket}
    lp = params if params is not None else fixture_params(ticker, session_date)
    out = {
        "rule_version": LEVEL_RULE_VERSION,
        "ticker": ticker,
        "session_date": session_date.isoformat(),
        "status": "ok",
        "last_bar_date": None,
        "atr": atr,
        "atr_14": atr,
        "atr_5": None,
        **lp.to_basis(),
        "prior_close": prior_close,
        "premarket": pm,
        "levels": [_level(n, p) for n, p in levels.items()],
        "pmg_zones": [],
    }
    if any(k in lp.params for k in ATR_RUNG_KEYS):
        # A brief built under the ATR rung rule records `atr_rung_status`,
        # the marker SessionLevels.from_basis rebuilds rungs on.
        out["atr_rung_status"] = None
    if reference is not None:
        out["reference"] = reference
        out["reference_source"] = "caller"
    return out


def session(levels: dict, **kw) -> SessionLevels:
    return SessionLevels.from_basis(basis(levels, **kw))


def with_triggers(*, long: float | None = None, short: float | None = None,
                  long_stop: float | None = None, short_stop: float | None = None,
                  reference: float | None = None, atr: float | None = None,
                  params: LevelParams | None = None) -> SessionLevels:
    """A SessionLevels whose sides carry exactly these picks, for the
    planner's offset arithmetic (entry buffers, ATR stops, R multiples),
    which is the same whatever level the trigger came from. `atr` is the
    ATR(14) the offsets are measured in; `params` defaults to fixture_params
    (every key ok at the #1753 values)."""
    session_date = date(2026, 4, 7)
    lp = params if params is not None else fixture_params("TST", session_date)
    sl = SessionLevels(ticker="TST", session_date=session_date, reference=reference,
                       atr=atr, atr_14=atr, atr_basis=lp.atr_basis, params=lp)

    def _side(name, side, price, stop):
        if price is None:
            return SideLevels(side, reason="no_levels")
        return SideLevels(
            side, trigger={"name": name, "price": float(price), "level_type": "high",
                           "timeframe": "day", "period": "", "aliases": []},
            regime="normal", reason=None,
            stop=({"name": "stop", "price": float(stop), "level_type": "low",
                   "timeframe": "day", "period": "", "aliases": []} if stop is not None else None),
        )

    sl.long = _side("PDH", "long", long, long_stop)
    sl.short = _side("PDL", "short", short, short_stop)
    return sl


# ── Exits in thirds spec, Design 8: the golden fixture ─────────────────

D8_LEVELS = {'PDH': 253.00, 'PMH': 275.00, 'PQH': 280.00, 'PYH': 285.00,
             'PDL': 247.50, 'PDC': 247.00, 'PML': 225.00, 'PQL': 220.00, 'PYL': 215.00}
D8_PREMARKET = {'pre_high': 252.10, 'pre_low': 248.20, 'pre_vwap': 250.00}


def d8_params(*, window=2.6, spacing=0.25, statuses=None, anchors=None, **overrides):
    """The Design 8 ticker's LevelParams: both windows `window`, the spacing
    `spacing`, every other key ok; `statuses` marks keys not ok. `anchors`
    replaces the atr_rung_anchors policy row's list (ATR levels spec), as a
    later policy row would."""
    lp = fixture_params('TST', overrides={'trigger_window_long_atr': window,
                                          'trigger_window_short_atr': window,
                                          'target_min_spacing_atr': spacing, **overrides},
                        statuses=statuses)
    if anchors is not None:
        from dataclasses import replace
        p = lp.params['atr_rung_anchors']
        lp.params['atr_rung_anchors'] = replace(p, value=float(len(anchors)),
                                                extra={'anchors': list(anchors)})
    return lp


def d8_basis(levels=None, *, atr=14.0, params=None, **kw) -> dict:
    """The Design 8 level_basis: reference 250.00 (the premarket VWAP),
    premarket 252.10 / 248.20, prior close 247.00, ATR(14) 14.00."""
    return basis(levels or D8_LEVELS, prior_close=247.00, atr=atr, premarket=D8_PREMARKET,
                 params=params if params is not None else d8_params(**kw))


def d8_session(levels=None, **kw) -> SessionLevels:
    """The Design 8 fixture through SessionLevels.from_basis, the path every
    live consumer uses."""
    return SessionLevels.from_basis(d8_basis(levels, **kw))


# ── Unknown rule version spec (2026-11-16), Design 5 ──────────────────

def newer_rule_versions() -> tuple[str, str, str]:
    """Three rule versions newer than the newest this image knows: the newest
    member of lib.strat_levels.PICK_RULE_VERSIONS plus 1, plus 2, and v99.
    Read at call time from the module attribute, so a test that patches
    PICK_RULE_VERSIONS (a straggler image) gets versions newer than the
    patched list, and the tests hold after a build adds v5. The numbers are
    parsed here, not through the classifier under test."""
    newest = max(int(v.rsplit('.v', 1)[1]) for v in _strat_levels.PICK_RULE_VERSIONS)
    return (f'feat-strat-001.v{newest + 1}', f'feat-strat-001.v{newest + 2}', 'feat-strat-001.v99')


# ── ATR marks spec (2026-11-16), Design 7: the three stored bases ──────
#
# The level_basis of the live 2026-11-16 brief rows (built 08:31:19 ET,
# feat-strat-001.v3), as exported read-only into
# tests/fixtures/premarket_2026_11_16/brief_rows.json, and what origin/main
# f3b2344c4 gives for each (tests/fixtures/level_basis_2026-11-16/).

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BASES_1116 = FIXTURES / "premarket_2026_11_16" / "brief_rows.json"
MAIN_1116 = FIXTURES / "level_basis_2026-11-16"
TICKERS_1116 = ("SPY", "QQQ", "IWM")

# Design 7's reach histories for the goldens, in ATR from the trigger.
CALLS_REACH_D7 = (0.1, 0.3, 0.4, 0.7, 1.1, 1.2, 1.6, 2.4)
PUTS_REACH_D7 = (0.05, 0.2, 0.3, 0.6, 0.9, 1.3, 1.5, 2.1)

_BASES_1116: dict | None = None


def stored_1116(ticker: str) -> dict:
    """The stored 2026-11-16 level_basis of `ticker`, a fresh copy each call."""
    global _BASES_1116
    if _BASES_1116 is None:
        d = json.loads(BASES_1116.read_text())
        rows = [dict(zip(d["columns"], r)) for r in d["rows"]]
        _BASES_1116 = {r["ticker"]: r["level_basis"] for r in rows}
    return copy.deepcopy(_BASES_1116[ticker])


def main_1116(ticker: str) -> dict:
    """What origin/main f3b2344c4 gives for the stored basis (sides and plan_inputs)."""
    return json.loads((MAIN_1116 / f"{ticker}.main.json").read_text())


def main_text_1116(ticker: str) -> str:
    """format_levels_for_brief(..., 'bearish') on origin/main f3b2344c4 for the stored basis."""
    return (MAIN_1116 / f"{ticker}.main.txt").read_text().removesuffix("\n")


MAIN_SIDE_KEYS = ("trigger", "stop", "targets", "skipped", "gate_targets", "target_status", "plan")


def side_records(sl: SessionLevels) -> dict:
    """Each side's MAIN_SIDE_KEYS from sl.to_basis(), the shape <T>.main.json holds."""
    b = sl.to_basis()
    return {side: {k: b[side][k] for k in MAIN_SIDE_KEYS} for side in ("long", "short")}


MARKS_VERSION = "feat-strat-001.v6"


def marks_basis(stored: dict, marks, legs: int, *, marks_extra: dict | None = None) -> dict:
    """A copy of a stored basis rebuilt as the ATR marks version would be:
    its params record plan_target_marks_atr with `marks` (or `marks_extra`)
    and exit_legs with `legs`, each as policy_wide_param builds them, its
    rule_version is the marks version, and its long and short records are
    removed so nothing stored is trusted."""
    from lib.strat_levels import policy_wide_param

    out = copy.deepcopy(stored)
    for key, extra in (("plan_target_marks_atr",
                        marks_extra if marks_extra is not None else {"marks": list(marks)}),
                       ("exit_legs", {"legs": legs})):
        pol = {"extra": extra, "effective_from": "2026-12-01", "method_id": "policy"}
        out["params"][key] = policy_wide_param(key, pol, out.get("ticker") or "",
                                               out.get("atr_basis") or "atr_14").to_basis()
    out["rule_version"] = MARKS_VERSION
    out.pop("long", None)
    out.pop("short", None)
    return out


QUARTER_MARKS = (0.25, 0.5, 0.75, 1.0)
