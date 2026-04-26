"""Deterministic ticker ranker.

Combines catalyst sources (earnings_calendar, sec_filings, insider_
transactions, top_movers_daily, economic_events, manual watchlist)
with per-ticker signal extractors (Strat, IV, news, sentiment shift,
historical earnings reaction, insider cluster, recent 8-K) into a
single weighted score per candidate. No LLM calls — pure SQL + Python.

Public API:
    rank_tickers(weights=None, catalyst_filter=None, limit=10) -> dict

Configuration lives in `alert_config.json` under the `ranker` key
(see lib/config.RankerConfig); defaults in `scoring.DEFAULT_WEIGHTS`.
"""

from .rank import rank_tickers, RankedTicker
from .scoring import DEFAULT_WEIGHTS, ScoreResult, weighted_score
from .signals import ALL_SIGNALS

__all__ = [
    "rank_tickers",
    "RankedTicker",
    "DEFAULT_WEIGHTS",
    "ScoreResult",
    "weighted_score",
    "ALL_SIGNALS",
]
