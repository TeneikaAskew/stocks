"""Gather candidate tickers from every catalyst source we collect.

Every ticker has a list of catalyst tags attached so the ranker can
filter by catalyst type (e.g. 'just earnings names today') and the UI
can display *why* this ticker is a candidate.

Sources merged here:
  * earnings_calendar     — anyone reporting in the next N days
  * sec_filings (8-K)     — recent material event filings
  * insider_transactions  — recent insider activity
  * top_movers_daily      — today's biggest movers
  * economic_events       — only the affected ETFs (small static map)
  * Manual watchlist      — INSIGHT_TICKERS env / config

Returns CandidateTicker objects. Duplicates across sources are merged
and the source list grows.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Optional

import pandas as pd


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


def _candidates_from_manual(
    out: dict[str, CandidateTicker], manual_tickers: list[str]
) -> None:
    for tk in manual_tickers:
        tk = tk.upper().strip()
        if not tk:
            continue
        cand = out.setdefault(tk, CandidateTicker(ticker=tk))
        cand.add_catalyst("manual")


def gather_candidates(
    *,
    catalyst_filter: Optional[set[CatalystType]] = None,
    earnings_days_ahead: int = 7,
    sec_8k_days: int = 3,
    insider_days: int = 30,
    economic_days_ahead: int = 5,
    manual_tickers: Optional[list[str]] = None,
) -> list[CandidateTicker]:
    """Build the day's candidate list.

    Args:
        catalyst_filter: if provided, only include tickers that have at
            least one catalyst tag in this set. None = include everyone.
        manual_tickers: explicit list to always include (e.g. SPY/IWM/QQQ
            from INSIGHT_TICKERS env).
    """
    out: dict[str, CandidateTicker] = {}

    _candidates_from_earnings(out, earnings_days_ahead)
    _candidates_from_8k(out, sec_8k_days)
    _candidates_from_insiders(out, insider_days)
    _candidates_from_top_movers(out)
    _candidates_from_economic(out, economic_days_ahead)
    if manual_tickers is None:
        env_default = os.environ.get("INSIGHT_TICKERS", "SPY,IWM,QQQ")
        manual_tickers = [t.strip() for t in env_default.split(",") if t.strip()]
    _candidates_from_manual(out, manual_tickers)

    if catalyst_filter:
        out = {
            tk: c for tk, c in out.items()
            if any(t in catalyst_filter for t in c.catalyst_types)
        }

    return sorted(out.values(), key=lambda c: c.ticker)
