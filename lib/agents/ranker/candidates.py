"""Gather candidate tickers from every catalyst source we collect.

Every ticker has a list of catalyst tags attached so the ranker can
filter by catalyst type (e.g. 'just earnings names today') and the UI
can display *why* this ticker is a candidate.

Default scope: only tickers on the configured watchlist
(`alert_config.json` → `"watchlist"`). Catalyst sources are still
queried so each watchlist ticker carries its catalyst tags + reasons,
but tickers not on the watchlist are dropped. This keeps the candidate
set small enough that scoring runs in seconds rather than minutes.

Set `expand_universe=True` to lift the watchlist gate and pull every
catalyst-tagged ticker (the legacy behavior — slow at any real scale).

`extras` is a one-shot way to inject names without editing the
watchlist file (e.g. add AVGO for a single ranker run).

Sources merged here:
  * earnings_calendar     — anyone reporting in the next N days
  * sec_filings (8-K)     — recent material event filings
  * insider_transactions  — recent insider activity
  * top_movers_daily      — today's biggest movers
  * economic_events       — only the affected ETFs (small static map)
  * Watchlist             — alert_config.json `watchlist` (always included)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date as date_type
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


CatalystType = str   # 'earnings' | 'sec_8k' | 'insider' | 'top_mover'
                     # | 'economic_event' | 'manual'


@dataclass
class CandidateTicker:
    ticker: str
    catalyst_types: list[CatalystType] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def add_catalyst(self, kind: CatalystType, **meta) -> None:
        if kind not in self.catalyst_types:
            self.catalyst_types.append(kind)
        if meta:
            self.metadata.setdefault(kind, []).append(meta)


def _query(sql: str, params: Optional[dict] = None):
    from gcp.database import query_to_dataframe

    return query_to_dataframe(sql, params or {})


# Lightweight ETF impact map for macro events. Keep it small and obvious;
# expand as needed. The `event_name LIKE` patterns are intentionally
# permissive because the FRED feed name strings vary.
ECONOMIC_EVENT_ETF_MAP: list[tuple[str, list[str]]] = [
    ("CPI",                          ["TLT", "SPY", "QQQ"]),
    ("Consumer Price Index",         ["TLT", "SPY", "QQQ"]),
    ("Federal Funds",                ["TLT", "SPY", "IWM", "QQQ"]),
    ("FOMC",                         ["TLT", "SPY", "IWM", "QQQ"]),
    ("Nonfarm Payroll",              ["SPY", "IWM", "QQQ"]),
    ("Unemployment",                 ["SPY", "IWM", "TLT"]),
    ("PCE",                          ["TLT", "SPY"]),
    ("Retail Sales",                 ["XLY", "SPY"]),
    ("GDP",                          ["SPY", "IWM"]),
]


def _candidates_from_earnings(
    out: dict[str, CandidateTicker], days_ahead: int
) -> None:
    df = _query(
        """
        SELECT DISTINCT ticker, MIN(earnings_date) AS next_date,
               MIN(earnings_time) AS earnings_time
        FROM earnings_calendar
        WHERE earnings_date BETWEEN CURRENT_DATE
          AND CURRENT_DATE + (:days || ' days')::interval
        GROUP BY ticker
        """,
        {"days": days_ahead},
    )
    if df is None or df.empty:
        return
    for _, row in df.iterrows():
        tk = (row.get("ticker") or "").upper().strip()
        if not tk:
            continue
        cand = out.setdefault(tk, CandidateTicker(ticker=tk))
        cand.add_catalyst(
            "earnings",
            date=str(row.get("next_date")),
            timing=row.get("earnings_time"),
        )


def _candidates_from_8k(
    out: dict[str, CandidateTicker], days: int
) -> None:
    df = _query(
        """
        SELECT ticker, filing_date, items
        FROM sec_filings
        WHERE form = '8-K'
          AND filing_date >= CURRENT_DATE - (:days || ' days')::interval
          AND ticker IS NOT NULL
        """,
        {"days": days},
    )
    if df is None or df.empty:
        return
    for _, row in df.iterrows():
        tk = (row.get("ticker") or "").upper().strip()
        if not tk:
            continue
        cand = out.setdefault(tk, CandidateTicker(ticker=tk))
        cand.add_catalyst(
            "sec_8k",
            filing_date=str(row.get("filing_date")),
            items=list(row.get("items") or []),
        )


def _candidates_from_insiders(
    out: dict[str, CandidateTicker], days: int
) -> None:
    df = _query(
        """
        SELECT ticker, COUNT(*) AS txns,
               COUNT(DISTINCT executive) AS insiders
        FROM insider_transactions
        WHERE transaction_date >= CURRENT_DATE - (:days || ' days')::interval
        GROUP BY ticker
        HAVING COUNT(*) > 0
        """,
        {"days": days},
    )
    if df is None or df.empty:
        return
    for _, row in df.iterrows():
        tk = (row.get("ticker") or "").upper().strip()
        if not tk:
            continue
        cand = out.setdefault(tk, CandidateTicker(ticker=tk))
        cand.add_catalyst(
            "insider",
            txns=int(row.get("txns") or 0),
            insiders=int(row.get("insiders") or 0),
        )


def _candidates_from_top_movers(out: dict[str, CandidateTicker]) -> None:
    df = _query(
        """
        SELECT ticker, category, rank, change_pct
        FROM top_movers_daily
        WHERE snapshot_date = CURRENT_DATE
        """,
        {},
    )
    if df is None or df.empty:
        return
    for _, row in df.iterrows():
        tk = (row.get("ticker") or "").upper().strip()
        if not tk:
            continue
        cand = out.setdefault(tk, CandidateTicker(ticker=tk))
        cand.add_catalyst(
            "top_mover",
            category=row.get("category"),
            rank=int(row.get("rank") or 0),
            change_pct=float(row.get("change_pct") or 0.0),
        )


def _candidates_from_economic(
    out: dict[str, CandidateTicker], days_ahead: int
) -> None:
    df = _query(
        """
        SELECT event_date, event_name, importance
        FROM economic_events
        WHERE event_date BETWEEN CURRENT_DATE
          AND CURRENT_DATE + (:days || ' days')::interval
          AND COALESCE(importance, '') IN ('high', 'medium', '')
        """,
        {"days": days_ahead},
    )
    if df is None or df.empty:
        return
    for _, row in df.iterrows():
        name = (row.get("event_name") or "").lower()
        for needle, etfs in ECONOMIC_EVENT_ETF_MAP:
            if needle.lower() in name:
                for tk in etfs:
                    cand = out.setdefault(tk, CandidateTicker(ticker=tk))
                    cand.add_catalyst(
                        "economic_event",
                        event_date=str(row.get("event_date")),
                        event_name=row.get("event_name"),
                        importance=row.get("importance"),
                    )
                break


def _candidates_from_watchlist(
    out: dict[str, CandidateTicker], watchlist: list[str]
) -> None:
    """Seed every watchlist ticker. They show up even if no catalyst hit
    today — that way the dashboard always renders the names you care
    about, ranked by their non-catalyst signals (volatility, IV, etc.)."""
    for tk in watchlist:
        tk = tk.upper().strip()
        if not tk:
            continue
        cand = out.setdefault(tk, CandidateTicker(ticker=tk))
        cand.add_catalyst("watchlist")


def _load_watchlist(user_id: Optional[str] = None) -> list[str]:
    """Return the active research watchlist from the centralized helper.

    Single source of truth: `watchlists` Cloud SQL table where
    removed_at IS NULL, with INSIGHT_TICKERS env var as the only
    fallback. The legacy alert_config.json watchlist key was removed
    in favor of this DB-backed source.

    `user_id` scopes the watchlist to a single owner (the signed-in
    user's email when called from the per-user API). `None` defers to
    the helper's default owner — used by the brief/insight/CLI callers.
    """
    try:
        from gcp.fetchers._watchlist import DEFAULT_USER_ID, load_watchlist
        return load_watchlist(
            user_id=user_id if user_id is not None else DEFAULT_USER_ID,
            surface="all",
        )
    except Exception as exc:
        logger.warning("watchlist load failed (%s); falling back to env", exc)
    env = os.environ.get("INSIGHT_TICKERS", "SPY,IWM,QQQ")
    return [t.strip().upper() for t in env.split(",") if t.strip()]


def gather_candidates(
    *,
    catalyst_filter: Optional[set[CatalystType]] = None,
    earnings_days_ahead: int = 7,
    sec_8k_days: int = 3,
    insider_days: int = 30,
    economic_days_ahead: int = 5,
    expand_universe: bool = False,
    extras: Optional[list[str]] = None,
    watchlist: Optional[list[str]] = None,
    user_id: Optional[str] = None,
) -> list[CandidateTicker]:
    """Build the day's candidate list.

    Default scope (`expand_universe=False`): the result is constrained to
    tickers on the configured watchlist plus anything in `extras`.
    Catalyst tags still attach so the score breakdown can explain
    *why* a ticker ranks where it does.

    Set `expand_universe=True` to drop the watchlist gate and return
    every catalyst-tagged ticker (slow — legacy behavior).

    Args:
        catalyst_filter: keep only tickers with at least one matching
            catalyst tag. `None` = no filter.
        expand_universe: bypass the watchlist gate.
        extras: ad-hoc additions (always included regardless of gate).
        watchlist: override the configured watchlist for this call.
        user_id: scope the loaded watchlist to a single owner (per-user
            API). `None` uses the helper's default owner.
    """
    out: dict[str, CandidateTicker] = {}

    _candidates_from_earnings(out, earnings_days_ahead)
    _candidates_from_8k(out, sec_8k_days)
    _candidates_from_insiders(out, insider_days)
    _candidates_from_top_movers(out)
    _candidates_from_economic(out, economic_days_ahead)

    wl = watchlist if watchlist is not None else _load_watchlist(user_id=user_id)
    _candidates_from_watchlist(out, wl)

    extras_set: set[str] = {
        t.strip().upper() for t in (extras or []) if t.strip()
    }
    for tk in extras_set:
        cand = out.setdefault(tk, CandidateTicker(ticker=tk))
        cand.add_catalyst("manual")

    if not expand_universe:
        keep: set[str] = {t.upper() for t in wl} | extras_set
        out = {tk: c for tk, c in out.items() if tk in keep}

    if catalyst_filter:
        out = {
            tk: c for tk, c in out.items()
            if any(t in catalyst_filter for t in c.catalyst_types)
        }

    return sorted(out.values(), key=lambda c: c.ticker)
