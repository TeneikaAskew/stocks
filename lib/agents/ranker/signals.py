"""Per-ticker signal extractors for the ranker.

Every function here is **deterministic SQL + Python** — no LLM calls,
no external HTTP. Each returns a uniform shape so `scoring.py` can
treat them interchangeably:

    {
        "available": bool,        # could we compute the signal at all?
        "score_0_to_1": float,    # normalized contribution before weighting
        "reason": str,            # human-readable explanation
        "raw": dict,              # optional debugging data
    }

Test pattern (mirrors lib/agents/summarizers): monkey-patch `_query`
with a fake that returns canned DataFrames. No live DB needed.
"""

from __future__ import annotations

import logging
from datetime import date as date_type, datetime, timedelta
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _query(sql: str, params: Optional[dict] = None):
    """Lazy wrapper — defer gcp.database import so unit tests can
    monkey-patch a fake query fn without requiring sqlalchemy.

    Tests do: `monkeypatch.setattr(signals, "_query", fake_query)`.
    """
    from gcp.database import query_to_dataframe

    return query_to_dataframe(sql, params or {})


# ---------------------------------------------------------------------------
# 1. Strat alignment — FTFC + setup state on the daily timeframe
# ---------------------------------------------------------------------------


def signal_strat_alignment(ticker: str) -> dict:
    """Score 0-1 based on Strat setup quality.

    Components (each contributes up to ~0.33):
      * `strat_setup` boolean (the daily fetcher flags actionable setups)
      * `ftfc_score` magnitude (how many timeframes agree)
      * `ftfc_direction` cleanness (bull/bear vs mixed)
    """
    df = _query(
        """
        SELECT strat_setup, ftfc_score, ftfc_direction, strat_combo
        FROM market_data_daily
        WHERE ticker = :ticker
        ORDER BY date DESC
        LIMIT 1
        """,
        {"ticker": ticker.upper()},
    )
    if df is None or df.empty:
        return {"available": False, "score_0_to_1": 0.0,
                "reason": "no daily bars", "raw": {}}

    row = df.iloc[0]
    setup = bool(row.get("strat_setup") or False)
    ftfc = float(row.get("ftfc_score") or 0.0)
    direction = (row.get("ftfc_direction") or "mixed").lower()

    setup_pts = 0.34 if setup else 0.0
    ftfc_pts = min(max(ftfc, 0.0), 1.0) * 0.33
    dir_pts = 0.33 if direction in ("bull", "bear") else 0.0

    score = setup_pts + ftfc_pts + dir_pts
    reason_parts = []
    if setup:
        reason_parts.append("strat_setup=true")
    reason_parts.append(f"ftfc={ftfc:.2f}")
    reason_parts.append(f"dir={direction}")

    return {
        "available": True,
        "score_0_to_1": round(score, 3),
        "reason": " ".join(reason_parts),
        "raw": {
            "strat_setup": setup, "ftfc_score": ftfc,
            "ftfc_direction": direction, "strat_combo": row.get("strat_combo"),
        },
    }


# ---------------------------------------------------------------------------
# 2. IV signals — IV percentile + IV/HV ratio (for tickers with options)
# ---------------------------------------------------------------------------


def signal_iv(ticker: str) -> dict:
    """Aggregate today's options chain IV vs. 60d realized volatility.

    Score = clamp(IV/HV, 0.5, 2.0) → mapped to 0-1.
    IV/HV well above 1 means options are pricing in more volatility than
    has historically been realized → favors selling premium / fade plays.
    Below 1 favors directional buys.

    The ranker treats this as a "catalyst pricing" signal — we rank
    higher when options have meaningful IV regardless of direction.
    """
    df_iv = _query(
        """
        SELECT AVG(implied_volatility) AS avg_iv
        FROM etf_options_snapshots
        WHERE ticker = :ticker
          AND data_source = 'alphavantage'
          AND snapshot_date = (
              SELECT MAX(snapshot_date) FROM etf_options_snapshots
              WHERE ticker = :ticker AND data_source = 'alphavantage'
          )
          AND implied_volatility IS NOT NULL
          AND implied_volatility BETWEEN 0.05 AND 5.0
        """,
        {"ticker": ticker.upper()},
    )
    if df_iv is None or df_iv.empty or pd.isna(df_iv.iloc[0].get("avg_iv")):
        return {"available": False, "score_0_to_1": 0.0,
                "reason": "no options chain", "raw": {}}

    avg_iv = float(df_iv.iloc[0]["avg_iv"])

    df_hv = _query(
        """
        SELECT volatility_20d
        FROM market_data_daily
        WHERE ticker = :ticker AND volatility_20d IS NOT NULL
        ORDER BY date DESC LIMIT 1
        """,
        {"ticker": ticker.upper()},
    )
    hv = float(df_hv.iloc[0]["volatility_20d"]) if (
        df_hv is not None and not df_hv.empty
    ) else None

    if hv is None or hv <= 0:
        # Fall back to using IV alone — high IV is itself a setup signal
        # because it means the market is pricing in a move.
        score = min(max((avg_iv - 0.2) / 0.6, 0.0), 1.0)
        return {
            "available": True, "score_0_to_1": round(score, 3),
            "reason": f"IV={avg_iv:.2f} (no HV available)",
            "raw": {"avg_iv": avg_iv, "hv": None},
        }

    iv_hv = avg_iv / hv
    # Map 0.5x → 0, 1.0x → 0.5, 2.0x → 1.0 (logarithmic-ish)
    import math
    score = min(max((math.log(iv_hv) + math.log(2)) / (2 * math.log(2)), 0.0), 1.0)
    return {
        "available": True, "score_0_to_1": round(score, 3),
        "reason": f"IV={avg_iv:.2f} HV={hv:.2f} ratio={iv_hv:.2f}",
        "raw": {"avg_iv": avg_iv, "hv": hv, "iv_hv": iv_hv},
    }


# ---------------------------------------------------------------------------
# 3. News topic score — recent catalyst-tagged articles weighted by sentiment
# ---------------------------------------------------------------------------


# AV NEWS_SENTIMENT returns topics as lowercase snake_case strings. The
# catalyst set below is intentionally narrow — sector tags like
# `financial_markets` and `technology` appear on almost every article and
# would dilute the signal. We want topics that genuinely move price.
CATALYST_TOPICS = {
    "mergers_and_acquisitions",
    "earnings",
    "ipo",
    "economy_monetary",          # FOMC / rate decisions
    "energy_transportation",     # for energy/transport-sensitive names
}


def signal_news_topic_score(ticker: str, lookback_hours: int = 24) -> dict:
    """Recent news activity weighted by catalyst topic + sentiment magnitude.

    A single high-relevance article tagged with a real catalyst topic (e.g.
    M&A) should be a meaningful score on its own — that's the kind of
    headline that drives short-DTE option P&L. Score = 0.6 * density (capped
    at 2 articles for full credit) + 0.4 * relevance-weighted abs sentiment.
    """
    df = _query(
        """
        SELECT topics, overall_sentiment_score, relevance_score, published_ts
        FROM news_sentiment
        WHERE ticker = :ticker
          AND published_ts >= NOW() - (:hours || ' hours')::interval
        """,
        {"ticker": ticker.upper(), "hours": lookback_hours},
    )
    if df is None or df.empty:
        return {"available": True, "score_0_to_1": 0.0,
                "reason": "no recent news", "raw": {"article_count": 0}}

    catalyst_count = 0
    weighted_sentiment = 0.0
    weight_sum = 0.0
    matched_topics: set[str] = set()
    for _, row in df.iterrows():
        topics = row.get("topics") or []
        if not isinstance(topics, (list, tuple)):
            continue
        hit = [t for t in topics if t in CATALYST_TOPICS]
        if not hit:
            continue
        catalyst_count += 1
        matched_topics.update(hit)
        rel = float(row.get("relevance_score") or 0.0)
        sentiment = float(row.get("overall_sentiment_score") or 0.0)
        # Weight by relevance: a relevance-1.0 article counts fully, a 0.3
        # passing-mention counts ~third.
        weighted_sentiment += abs(sentiment) * rel
        weight_sum += rel

    if catalyst_count == 0:
        return {"available": True, "score_0_to_1": 0.0,
                "reason": f"{len(df)} articles but none tagged as catalyst",
                "raw": {"article_count": len(df), "catalyst_count": 0}}

    # Density: 2+ catalyst articles in window = full credit. The Apr-7
    # AVGO/Google headlines fired *two* M&A-tagged articles in <2 minutes,
    # which the prior `/5` divisor undervalued.
    density = min(catalyst_count / 2.0, 1.0) * 0.6
    avg_weighted_sent = (weighted_sentiment / weight_sum) if weight_sum else 0.0
    sentiment_pts = min(avg_weighted_sent * 2, 1.0) * 0.4
    score = density + sentiment_pts

    return {
        "available": True, "score_0_to_1": round(min(score, 1.0), 3),
        "reason": (
            f"{catalyst_count}/{len(df)} catalyst articles "
            f"({','.join(sorted(matched_topics))}), "
            f"weighted|sentiment|={avg_weighted_sent:.2f}"
        ),
        "raw": {
            "article_count": len(df),
            "catalyst_count": catalyst_count,
            "matched_topics": sorted(matched_topics),
            "weighted_avg_sentiment": round(avg_weighted_sent, 3),
        },
    }


# ---------------------------------------------------------------------------
# 4. Sentiment shift — change in 7d avg sentiment vs. prior 7d
# ---------------------------------------------------------------------------


def signal_sentiment_shift(ticker: str) -> dict:
    """Recent vs. prior week sentiment shift magnitude."""
    df = _query(
        """
        SELECT
          AVG(CASE WHEN published_ts >= NOW() - INTERVAL '7 days'
                   THEN overall_sentiment_score END) AS recent,
          AVG(CASE WHEN published_ts BETWEEN NOW() - INTERVAL '14 days'
                                       AND NOW() - INTERVAL '7 days'
                   THEN overall_sentiment_score END) AS prior
        FROM news_sentiment
        WHERE ticker = :ticker
          AND published_ts >= NOW() - INTERVAL '14 days'
          AND overall_sentiment_score IS NOT NULL
        """,
        {"ticker": ticker.upper()},
    )
    if df is None or df.empty:
        return {"available": False, "score_0_to_1": 0.0,
                "reason": "no news", "raw": {}}

    recent = df.iloc[0].get("recent")
    prior = df.iloc[0].get("prior")
    if recent is None or pd.isna(recent) or prior is None or pd.isna(prior):
        return {"available": False, "score_0_to_1": 0.0,
                "reason": "insufficient sentiment data", "raw": {}}

    shift = abs(float(recent) - float(prior))
    # AV sentiment_score range is roughly [-1, 1]; a 0.5 shift is large.
    score = min(shift / 0.5, 1.0)
    return {
        "available": True, "score_0_to_1": round(score, 3),
        "reason": f"7d avg shifted {float(recent) - float(prior):+.2f}",
        "raw": {"recent_7d": round(float(recent), 3),
                "prior_7d": round(float(prior), 3)},
    }


# ---------------------------------------------------------------------------
# 5. Liquidity floor — pass/fail; if fail, the ticker is excluded entirely
# ---------------------------------------------------------------------------


def signal_liquidity(ticker: str, min_avg_volume: int = 500_000) -> dict:
    """Average daily volume gate. Returns score 1.0 if pass, 0.0 if fail.

    Treated specially in scoring: a fail means the ticker is dropped
    from the ranking entirely (no point ranking illiquid names).
    """
    df = _query(
        """
        SELECT AVG(volume) AS avg_vol
        FROM market_data_daily
        WHERE ticker = :ticker
          AND date >= CURRENT_DATE - INTERVAL '20 days'
        """,
        {"ticker": ticker.upper()},
    )
    if df is None or df.empty or pd.isna(df.iloc[0].get("avg_vol")):
        return {"available": False, "score_0_to_1": 0.0,
                "reason": "no volume data", "raw": {"passes": False}}

    avg_vol = int(df.iloc[0]["avg_vol"] or 0)
    passes = avg_vol >= min_avg_volume
    return {
        "available": True,
        "score_0_to_1": 1.0 if passes else 0.0,
        "reason": (
            f"avg 20d volume {avg_vol:,} {'>=' if passes else '<'} {min_avg_volume:,}"
        ),
        "raw": {"avg_volume_20d": avg_vol, "passes": passes,
                "min_required": min_avg_volume},
    }


# ---------------------------------------------------------------------------
# 6. Historical earnings reaction — last N earnings post-announcement moves
# ---------------------------------------------------------------------------


def signal_historical_earnings_reaction(
    ticker: str, n_quarters: int = 4
) -> dict:
    """Average + consistency of recent post-earnings price moves.

    Joins earnings_history → market_data_daily to compute the close-to-close
    move from T-1 → T+1 for each of the last N reported earnings dates.

    Score components:
      * Magnitude (avg |move| / 0.05) → high = consistently big movers
      * Direction consistency (% of last N that moved in same direction)
    """
    df = _query(
        """
        SELECT
            eh.reported_date,
            md_pre.close  AS pre_close,
            md_post.close AS post_close
        FROM earnings_history eh
        LEFT JOIN market_data_daily md_pre
            ON md_pre.ticker = eh.ticker
            AND md_pre.date  = eh.reported_date - INTERVAL '1 day'
        LEFT JOIN market_data_daily md_post
            ON md_post.ticker = eh.ticker
            AND md_post.date  = eh.reported_date + INTERVAL '1 day'
        WHERE eh.ticker = :ticker
          AND eh.reported_date IS NOT NULL
          AND eh.reported_date < CURRENT_DATE
        ORDER BY eh.reported_date DESC
        LIMIT :n
        """,
        {"ticker": ticker.upper(), "n": n_quarters},
    )
    if df is None or df.empty:
        return {"available": False, "score_0_to_1": 0.0,
                "reason": "no earnings_history", "raw": {}}

    moves = []
    for _, row in df.iterrows():
        pre = row.get("pre_close")
        post = row.get("post_close")
        if pre is None or post is None or pd.isna(pre) or pd.isna(post) or float(pre) <= 0:
            continue
        moves.append((float(post) - float(pre)) / float(pre))

    if not moves:
        return {"available": False, "score_0_to_1": 0.0,
                "reason": "no matching market_data for earnings dates",
                "raw": {"earnings_rows": len(df)}}

    avg_abs = sum(abs(m) for m in moves) / len(moves)
    same_sign = sum(1 for m in moves if m > 0)
    consistency = max(same_sign, len(moves) - same_sign) / len(moves)

    magnitude_pts = min(avg_abs / 0.05, 1.0) * 0.6  # 5% avg move = max
    consistency_pts = max((consistency - 0.5) * 2, 0.0) * 0.4  # 100% = 1.0
    score = magnitude_pts + consistency_pts
    avg_signed = sum(moves) / len(moves)
    return {
        "available": True, "score_0_to_1": round(min(score, 1.0), 3),
        "reason": (
            f"{len(moves)} earnings: avg move {avg_signed*100:+.2f}%, "
            f"consistency {consistency*100:.0f}%"
        ),
        "raw": {
            "n_earnings": len(moves),
            "avg_signed_move_pct": round(avg_signed * 100, 2),
            "avg_abs_move_pct": round(avg_abs * 100, 2),
            "same_direction_pct": round(consistency * 100, 1),
        },
    }


# ---------------------------------------------------------------------------
# 7. Insider cluster — Form 4 buys/sells in window
# ---------------------------------------------------------------------------


def _insider_window(ticker: str, days: int):
    """Shared SQL fetch for insider buying + selling signals."""
    return _query(
        """
        SELECT executive, transaction_type, shares, share_price,
               COALESCE(transaction_value, shares * share_price) AS value
        FROM insider_transactions
        WHERE ticker = :ticker
          AND transaction_date >= CURRENT_DATE - (:days || ' days')::interval
        """,
        {"ticker": ticker.upper(), "days": days},
    )


def _insider_score(df, side: str, big_value_threshold: float) -> dict:
    """Score one side (buys or sells) of insider activity."""
    code = "A" if side == "buy" else "D"
    side_df = df[df["transaction_type"] == code] if df is not None else None
    if side_df is None or side_df.empty:
        return {"available": True, "score_0_to_1": 0.0,
                "reason": f"no insider {side}ing", "raw": {side + "s": 0}}
    n_people = int(side_df["executive"].nunique())
    big_n = int((side_df["value"].fillna(0) >= big_value_threshold).sum())
    cluster_pts = min(n_people / 3.0, 1.0) * 0.6
    big_pts = min(big_n / 1.0, 1.0) * 0.4
    score = min(cluster_pts + big_pts, 1.0)
    total_value = float(side_df["value"].fillna(0).sum())
    return {
        "available": True, "score_0_to_1": round(score, 3),
        "reason": (
            f"{n_people} insider(s) {side}ing, {len(side_df)} txns, "
            f"{big_n} >${big_value_threshold/1e6:.1f}M, total ${total_value/1e6:.1f}M"
        ),
        "raw": {
            "side": side, "txns": int(len(side_df)),
            "unique_insiders": n_people, "big_transactions": big_n,
            "total_value": total_value,
        },
    }


def signal_insider_buying(
    ticker: str, days: int = 30,
    big_value_threshold: float = 1_000_000.0,
) -> dict:
    """Cluster of insider acquisitions (transaction_type=A) — bullish."""
    df = _insider_window(ticker, days)
    if df is None or df.empty:
        return {"available": True, "score_0_to_1": 0.0,
                "reason": f"no insider transactions in {days}d",
                "raw": {"transactions": 0}}
    return _insider_score(df, "buy", big_value_threshold)


def signal_insider_selling(
    ticker: str, days: int = 30,
    big_value_threshold: float = 1_000_000.0,
) -> dict:
    """Cluster of insider disposals (transaction_type=D) — bearish.

    Returns a positive score_0_to_1; the ranker config gives this signal
    a *negative* weight so the contribution to total score is negative.
    """
    df = _insider_window(ticker, days)
    if df is None or df.empty:
        return {"available": True, "score_0_to_1": 0.0,
                "reason": f"no insider transactions in {days}d",
                "raw": {"transactions": 0}}
    return _insider_score(df, "sell", big_value_threshold)


# ---------------------------------------------------------------------------
# 8. Top mover today — appearance in TOP_GAINERS_LOSERS today
# ---------------------------------------------------------------------------


def signal_is_top_mover(ticker: str) -> dict:
    df = _query(
        """
        SELECT category, rank, change_pct, volume
        FROM top_movers_daily
        WHERE ticker = :ticker
          AND snapshot_date = CURRENT_DATE
        """,
        {"ticker": ticker.upper()},
    )
    if df is None or df.empty:
        return {"available": True, "score_0_to_1": 0.0,
                "reason": "not in today's top movers", "raw": {}}
    row = df.iloc[0]
    cat = row.get("category", "")
    rank = int(row.get("rank") or 99)
    # Higher score for lower (better) rank
    score = max(1.0 - (rank - 1) / 20.0, 0.2)
    return {
        "available": True, "score_0_to_1": round(score, 3),
        "reason": f"{cat} rank {rank}, change {row.get('change_pct')}%",
        "raw": {"category": cat, "rank": rank,
                "change_pct": float(row.get("change_pct") or 0.0)},
    }


# ---------------------------------------------------------------------------
# 9. Recent 8-K — material event within window
# ---------------------------------------------------------------------------


# Item codes that signal material catalyst events.
HIGH_IMPACT_8K_ITEMS = {
    "1.01",  # Material Definitive Agreement (M&A!)
    "1.02",  # Termination of Material Agreement
    "1.03",  # Bankruptcy
    "2.01",  # Acquisition / Disposition complete
    "2.02",  # Earnings release (8-K wrapper)
    "2.05",  # Material restructuring
    "5.02",  # Exec change
    "5.07",  # Shareholder vote
    "7.01",  # Reg FD
    "8.01",  # Other material events
}


def signal_recent_8k(ticker: str, days: int = 3) -> dict:
    df = _query(
        """
        SELECT filing_date, items
        FROM sec_filings
        WHERE ticker = :ticker
          AND form = '8-K'
          AND filing_date >= CURRENT_DATE - (:days || ' days')::interval
        ORDER BY filing_date DESC
        """,
        {"ticker": ticker.upper(), "days": days},
    )
    if df is None or df.empty:
        return {"available": True, "score_0_to_1": 0.0,
                "reason": f"no 8-K in {days}d", "raw": {"filings": 0}}

    high_impact_count = 0
    matched_items = []
    for _, row in df.iterrows():
        items = row.get("items") or []
        if not isinstance(items, (list, tuple)):
            continue
        for item in items:
            if item in HIGH_IMPACT_8K_ITEMS:
                high_impact_count += 1
                matched_items.append(item)

    if high_impact_count == 0:
        return {"available": True, "score_0_to_1": 0.2,
                "reason": f"{len(df)} 8-K(s) but no high-impact items",
                "raw": {"filings": len(df), "matched_items": []}}

    score = min(high_impact_count / 2.0, 1.0)
    return {
        "available": True, "score_0_to_1": round(score, 3),
        "reason": (
            f"{len(df)} 8-K filing(s), {high_impact_count} high-impact "
            f"item(s): {sorted(set(matched_items))}"
        ),
        "raw": {
            "filings": len(df), "high_impact_count": high_impact_count,
            "matched_items": sorted(set(matched_items)),
        },
    }


# ---------------------------------------------------------------------------
# All signals registry — keys map to weight names in alert_config.json
# ---------------------------------------------------------------------------


ALL_SIGNALS = {
    "strat_alignment": signal_strat_alignment,
    "iv_signals": signal_iv,
    "news_topic_score": signal_news_topic_score,
    "sentiment_shift": signal_sentiment_shift,
    "liquidity": signal_liquidity,
    "historical_earnings_reaction": signal_historical_earnings_reaction,
    "insider_buying": signal_insider_buying,
    "insider_selling": signal_insider_selling,
    "is_top_mover_today": signal_is_top_mover,
    "has_recent_8k": signal_recent_8k,
}
