"""Compatibility NYSE calendar shim after scorer retirement.

The import remains bound by the OPS, OPTION and DATA contracts:
2026-10-12-feat-ops-001-av-operations.md,
2026-10-13-feat-option-001-av-source-journal.md, and
2026-10-12-feat-data-001-av-market-data.md.
Calendar consumers retain the shared library's strict session behavior.
"""
from datetime import date

import pandas as pd

from lib.eastern_time import session_schedule


def nyse_sessions(start: date, end: date) -> pd.DataFrame:
    """NYSE sessions in [start, end]: indexed by session date, with UTC
    `market_open` / `market_close` (early closes included).

    Read from the shared NYSE calendar (`lib.eastern_time`, FEAT-DATA-001).
    There is no weekday fallback: a guessed session is the defect #1151
    fixed, so a missing calendar must fail the run.
    """
    return session_schedule(start, end)
