"""Premarket-brief bias resolver — visibility-only Phase 1.

Reads the morning premarket_analysis row for `(ticker, date)` and
derives a structured "bias" signal that the live signal monitor can
display alongside its own intraday signal. Bias is NOT used to gate
or modify scores yet — until we have enough data on whether
brief-aligned signals actually outperform brief-opposed ones, this
layer is read-only and purely informational.

Bias values:
  CALL        — brief explicitly recommends CALL setup, FTFC agrees
  PUT         — brief explicitly recommends PUT  setup, FTFC agrees
  NEUTRAL     — brief is "No signal" or only "building" (not actionable)
  CONFLICTED  — brief direction disagrees with FTFC direction
                (e.g. "PUT setup (3/5)" + ftfc_direction='bullish' —
                 the brief itself is internally inconsistent)
  UNAVAILABLE — no brief row for this (ticker, date)

Cold start: any unmapped state returns UNAVAILABLE so the live monitor
treats it as no information rather than spurious agreement.

Tier-B fallback: when Cloud SQL isn't configured (CI / unit tests) or
the query fails, returns UNAVAILABLE. The signal monitor's display is
purely additive in that case — it just doesn't show a brief tag.
"""
from __future__ import annotations

import logging
import re
from datetime import date as _date
from functools import lru_cache
from typing import Optional

log = logging.getLogger(__name__)

# Match the count out of 5 in 'CALL setup (3/5)' or 'PUT setup (4/5)'.
_SETUP_RE = re.compile(r'\((\d)/5\)')


def _extract_setup_count(signal_status: str) -> int:
    m = _SETUP_RE.search(signal_status or '')
    return int(m.group(1)) if m else 0


@lru_cache(maxsize=128)
def get_premarket_bias(ticker: str, target_date: _date) -> dict:
    """Resolve the brief bias for `(ticker, target_date)`.

    Returns a dict shaped:
        {
            'bias':           'CALL' | 'PUT' | 'NEUTRAL' | 'CONFLICTED' | 'UNAVAILABLE',
            'alignment':      None,  # filled in by signal monitor when comparing to live signal direction
            'setup_count':    int (0-5),
            'ftfc_direction': 'bullish' | 'bearish' | 'mixed' | None,
            'reason':         human-readable label
        }

    Cached lru on (ticker, date) — one DB hit per ticker per session.
    """
    try:
        from gcp.database import get_engine, is_cloud_sql_configured
    except ImportError:
        return _unavailable('import_failed')

    if not is_cloud_sql_configured():
        return _unavailable('db_not_configured')

    import pandas as pd
    from sqlalchemy import text

    sql = text(
        """
        SELECT signal_status, ftfc_direction, ftfc_score, strat_combo
          FROM premarket_analysis
         WHERE ticker = :ticker AND analysis_date = :d
         LIMIT 1
        """
    )
    try:
        df = pd.read_sql(sql, get_engine(), params={'ticker': ticker.upper(),
                                                    'd': target_date})
    except Exception as e:
        log.warning("brief bias query failed for %s %s: %s",
                    ticker, target_date, e)
        return _unavailable('query_failed')

    if df.empty:
        return _unavailable('no_brief_row')

    row = df.iloc[0].to_dict()
    return classify(row)


def classify(row: dict) -> dict:
    """Pure classifier — separate from DB read so unit tests can drive it."""
    status = (row.get('signal_status') or '').strip()
    ftfc_dir = (row.get('ftfc_direction') or '').lower() or None

    # Parse setup direction + count.
    if 'CALL setup' in status:
        setup_dir, setup_count = 'CALL', _extract_setup_count(status)
    elif 'PUT setup' in status:
        setup_dir, setup_count = 'PUT', _extract_setup_count(status)
    elif 'building' in status.lower():
        # Partial setup — not actionable, don't claim a bias.
        return _bias('NEUTRAL', 'building', setup_count=_extract_setup_count(status),
                     ftfc_direction=ftfc_dir)
    elif 'No signal' in status or not status:
        return _bias('NEUTRAL', 'no_setup', ftfc_direction=ftfc_dir)
    else:
        # Unknown status string — be safe.
        return _bias('NEUTRAL', f'unknown_status:{status[:30]}', ftfc_direction=ftfc_dir)

    # Cross-check setup direction against FTFC direction. If they
    # disagree, the brief is internally inconsistent — flag CONFLICTED
    # so the monitor knows not to penalize live signals in either dir.
    if ftfc_dir == 'bullish' and setup_dir == 'PUT':
        return _bias('CONFLICTED', 'setup_put_vs_ftfc_bullish',
                     setup_count=setup_count, ftfc_direction=ftfc_dir)
    if ftfc_dir == 'bearish' and setup_dir == 'CALL':
        return _bias('CONFLICTED', 'setup_call_vs_ftfc_bearish',
                     setup_count=setup_count, ftfc_direction=ftfc_dir)

    return _bias(setup_dir, 'aligned',
                 setup_count=setup_count, ftfc_direction=ftfc_dir)


def alignment(live_direction: str, bias: dict) -> Optional[str]:
    """Return 'aligned' / 'opposed' / None given a live signal direction
    and a resolved bias dict."""
    b = bias.get('bias')
    if b not in ('CALL', 'PUT'):
        return None  # NEUTRAL / CONFLICTED / UNAVAILABLE → no opinion
    return 'aligned' if live_direction == b else 'opposed'


def _bias(bias_value: str, reason: str,
          setup_count: int = 0,
          ftfc_direction: Optional[str] = None) -> dict:
    return {
        'bias':           bias_value,
        'alignment':      None,   # filled by caller when comparing to live signal
        'setup_count':    setup_count,
        'ftfc_direction': ftfc_direction,
        'reason':         reason,
    }


def _unavailable(reason: str) -> dict:
    return _bias('UNAVAILABLE', reason)
