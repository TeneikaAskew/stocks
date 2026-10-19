"""
Config router — exposes server-side configuration to the frontend.

Endpoints
---------
GET /api/config/indicators
    Indicator periods and signal thresholds straight from lib/config.py.
    Lets the UI label RSI zones, EMA windows, StochRSI thresholds, etc.
    without hardcoding numbers that can drift from Python.

GET /api/config/market-hours
    US equity market session boundaries (RTH, pre, post), plus the NYSE
    holidays and early closes for the current and next year from the shared
    calendar (lib.eastern_time). Used by the chart time-of-day filters and
    session badges.
"""
from __future__ import annotations

import os
import sys
from datetime import date, time
from pathlib import Path

from fastapi import APIRouter

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Market hours live in the live router already — re-use, don't duplicate.
from api.routers.live import (  # noqa: E402
    MARKET_OPEN,
    MARKET_CLOSE,
)
from lib.eastern_time import ET_NAME, holidays_in, market_today, session_schedule
from lib.config import load_config  # noqa: E402
from api import auth as _auth  # noqa: E402  (AUTH_MODE validated at import there)
from api.schemas import (
    IndicatorConfigResponse,
    MarketHoursResponse,
    RuntimeConfigResponse,
)

router = APIRouter()


@router.get("/api/config/firebase", response_model=RuntimeConfigResponse, response_model_exclude_unset=True)
def get_firebase_config() -> dict:
    """Public runtime auth config for the frontend bootstrap.

    Returns the active AUTH_MODE and, only in firebase mode, the Firebase web
    config (apiKey/authDomain/projectId/appId — these are identifiers, safe to
    expose; access is enforced by Firebase + authorized domains + server-side
    token verification). Served from env so one image works in every
    environment. Must stay reachable pre-auth (see api/auth._OPEN_API_PREFIXES).
    """
    # api.auth validated this value at import (unknown modes refuse to
    # start), so it always matches RuntimeConfigResponse's Literal. Read as
    # an attribute so tests that monkeypatch api.auth.AUTH_MODE are seen.
    mode = _auth.AUTH_MODE
    api_key = os.environ.get("FIREBASE_API_KEY", "").strip()
    firebase = None
    if mode == "firebase" and api_key:
        firebase = {
            "apiKey": api_key,
            "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN", "").strip(),
            "projectId": os.environ.get("FIREBASE_PROJECT_ID", "").strip(),
            "appId": os.environ.get("FIREBASE_APP_ID", "").strip(),
        }
    return {"authMode": mode, "firebase": firebase}


def _time_to_str(t: time) -> str:
    return t.strftime("%H:%M")


@router.get("/api/config/indicators", response_model=IndicatorConfigResponse, response_model_exclude_unset=True)
def get_indicator_config() -> dict:
    """Return indicator periods, signal thresholds, and zone labels."""
    cfg = load_config()
    ind = cfg.indicator
    sig = cfg.signal
    exit_cfg = cfg.exit

    # RSI zones are rendered as labels on the Dashboard. Expressing them as
    # data lets the frontend render the same thresholds that Python uses.
    rsi_zones = [
        {"max": 30, "label": "Oversold"},
        {"max": 45, "label": "Weak"},
        {"max": 55, "label": "Neutral"},
        {"max": 70, "label": "Strong"},
        {"max": 101, "label": "Overbought"},
    ]

    return {
        "rsi": {
            "period": ind.rsi_period,
            "fast_period": ind.rsi_fast_period,
            "oversold": 30,
            "overbought": 70,
            "zones": rsi_zones,
            "call_range": list(sig.call_rsi_range),
            "put_range": list(sig.put_rsi_range),
            "call_exit": exit_cfg.call_rsi_exit,
            "put_exit": exit_cfg.put_rsi_exit,
        },
        "ema": {"periods": list(ind.ema_periods)},
        "atr": {
            "period": ind.atr_period,
            # Trend-following signal condition threshold used by the
            # dashboard Call/Put confirmation logic.
            "high_threshold": 2.0,
        },
        "rvol": {
            "period": ind.rvol_period,
            "signal_threshold": 1.0,
        },
        "stoch_rsi": {
            "period": ind.stoch_rsi_period,
            "k_period": ind.stoch_rsi_k_period,
            "d_period": ind.stoch_rsi_d_period,
            "oversold": sig.stoch_rsi_oversold,
            "overbought": sig.stoch_rsi_overbought,
        },
        "signal": {
            "min_conditions": sig.min_conditions,
            "consecutive_periods": sig.consecutive_periods,
            "premarket_threshold": sig.premarket_signal_threshold,
        },
    }


def _early_closes(first_year: int, last_year: int) -> list[dict]:
    """Sessions in ``first_year`` .. ``last_year`` that close before the
    regular 16:00 ET, each with its Eastern close as ``HH:MM``."""
    schedule = session_schedule(date(first_year, 1, 1), date(last_year, 12, 31))
    closes = schedule["market_close"].dt.tz_convert(ET_NAME)
    return [
        {"date": day.date().isoformat(), "close": close.strftime("%H:%M")}
        for day, close in closes.items()
        if close.time() < MARKET_CLOSE
    ]


@router.get("/api/config/market-hours", response_model=MarketHoursResponse, response_model_exclude_unset=True)
def get_market_hours() -> dict:
    """Return US equity market session windows, holidays and early closes.

    ``holidays`` and ``early_closes`` cover the current and next year by the
    Eastern date, so the window rolls at 00:00 ET on 1 January. Half days
    are sessions, so they are in ``early_closes`` and never in ``holidays``.
    ``holidays_2026`` is kept, filled from the same calendar, for solyra's
    replay picker until Spec C moves it to ``holidays`` and removes it.
    A calendar failure raises (CLAUDE.md 3.7); nothing is filled in.
    """
    year = market_today().year
    return {
        "timezone": "America/New_York",
        "regular": {
            "open": _time_to_str(MARKET_OPEN),
            "close": _time_to_str(MARKET_CLOSE),
        },
        "pre_market": {"open": "04:00", "close": _time_to_str(MARKET_OPEN)},
        "after_hours": {"open": _time_to_str(MARKET_CLOSE), "close": "20:00"},
        "holidays_2026": [d.isoformat() for d in holidays_in(2026)],
        "holidays": [d.isoformat() for d in holidays_in(year) + holidays_in(year + 1)],
        "early_closes": _early_closes(year, year + 1),
    }
