"""The stored 2026-11-16 insight reports and brief rows, for FEAT-INSIGHT-001.

Files: tests/fixtures/insight_2026_11_16/, exported read-only (no --commit)
by one scripts/db_query_cr.sh dispatch; sources.json names the execution,
the two SQL statements and each file's byte count and sha256.

- <T>_stored_report.json: insight_reports.report of the 13:46Z live run
- <T>_level_basis.json: that report's level_basis
- <T>_brief_row.json: the session's live premarket_analysis row, the 28
  columns of lib.agents.summarizers.BRIEF_ROW_SQL

sources.json also records, per ticker, whether the report's level_basis
equals the brief row's. They are not equal on 2026-11-16 (see
level_basis_equal there); brief_row() puts the report's level_basis in
the row unless a test overrides it, as the implementation plan specifies.
"""
from __future__ import annotations

import copy
import json
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "insight_2026_11_16"
TICKERS = ("IWM", "QQQ", "SPY")
SESSION = date(2026, 11, 16)

# entry, trigger name where the spec gives it, stop, stop name, targets:
# the short side of each ticker, copied from the spec's D3.
EXPECTED_SHORT = {
    "IWM": (275.86, "PMK_L", 277.41, "PQL", [269.875]),
    "QQQ": (668.30, None, 679.89, "PDC", [662.02, 637.01]),
    "SPY": (747.95, None, 750.36, "PML", [741.025, 729.10]),
}

# The columns of BRIEF_ROW_SQL, in its order.
BRIEF_ROW_COLUMNS = (
    "analysis_date", "analysis_ts", "run_kind", "ticker", "price", "rsi", "sma200",
    "ema9", "ema20", "atr14", "bb_upper", "bb_lower", "rvol", "volatility_20d",
    "vol_regime", "macd_cross", "above_sma200", "strat_candle", "strat_combo",
    "strat_setup", "ftfc_score", "ftfc_direction", "ftfc_labels", "tf_continuity",
    "tf_continuity_frames", "prev_day_high", "prev_day_low", "level_basis",
)


@lru_cache(maxsize=None)
def _read(name: str) -> str:
    return (FIXTURE_DIR / name).read_text()


def level_basis(ticker: str) -> dict:
    """The stored report's level_basis; a fresh deep copy each call."""
    return json.loads(_read(f"{ticker.upper()}_level_basis.json"))


def stored_report(ticker: str) -> dict:
    """The stored 13:46Z report; a fresh copy each call."""
    return json.loads(_read(f"{ticker.upper()}_stored_report.json"))


def brief_row_dict(ticker: str) -> dict:
    """The exported brief row as written to the file (its own level_basis)."""
    return json.loads(_read(f"{ticker.upper()}_brief_row.json"))


def brief_row(ticker: str, **overrides) -> pd.DataFrame:
    """One row with the columns of BRIEF_ROW_SQL, as the strict reader returns
    it: analysis_date a date, analysis_ts a UTC Timestamp, JSONB cells as the
    driver hands them. Its level_basis cell is level_basis(ticker) unless a
    keyword overrides it; any other column may be overridden the same way."""
    row = brief_row_dict(ticker)
    row["analysis_date"] = date.fromisoformat(row["analysis_date"])
    row["analysis_ts"] = pd.Timestamp(row["analysis_ts"]).tz_convert("UTC")
    row["level_basis"] = level_basis(ticker)
    unknown = set(overrides) - set(BRIEF_ROW_COLUMNS)
    if unknown:
        raise KeyError(f"not a brief row column: {sorted(unknown)}")
    row.update(copy.deepcopy(overrides))
    return pd.DataFrame([{c: row[c] for c in BRIEF_ROW_COLUMNS}], columns=list(BRIEF_ROW_COLUMNS))
