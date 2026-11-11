"""Small builders for SessionLevels test fixtures (FEAT-STRAT-001).

`basis(...)` writes a level_basis dict the way the brief stores it, and
`session(...)` reads it back through SessionLevels.from_basis, the path every
live consumer uses, so the picks come from the one builder's rules.
"""
from __future__ import annotations

from datetime import date

from lib.strat_levels import LEVEL_RULE_VERSION, LevelParams, SessionLevels, SideLevels
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
