"""
Deterministic SQL summarizers for the agent pipeline.

These are pure Python functions that query existing Cloud SQL tables
(or on-disk parquets where a table doesn't exist yet) and return
typed dicts. No LLM calls. They exist so every agent prompt is
grounded in real platform state — the LLMs reason *over* this JSON,
they don't fetch it.

One function per analyst section plus a catalyst lookup and a
journal-memory retrieval. Each returns a dict that's trivially
JSON-serializable for embedding in a prompt.

All DB access goes through `gcp.database.query_to_dataframe`, which
returns an empty DataFrame on failure — summarizers degrade to
`{'available': False, 'reason': ...}` rather than raising. The
orchestrator passes degraded bundles to analysts with a clear flag
so the final report can mark which sections were missing.
"""

from __future__ import annotations

import logging
import math
from datetime import date as date_type, datetime, timedelta, timezone
from typing import Any, Optional

from .embeddings import format_vector_literal
from .schema import JournalRef

logger = logging.getLogger(__name__)


def _query(sql: str, params: Optional[dict] = None):
    """Lazy wrapper — defer gcp.database import so unit tests can
    monkey-patch a fake query fn without requiring sqlalchemy."""
    from gcp.database import query_to_dataframe

    return query_to_dataframe(sql, params or {})


def _scalar(row, col, cast=float, digits: Optional[int] = None):
    """Null-safe scalar extraction from a pandas Series row."""
    val = row.get(col)
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        out = cast(val)
    except (TypeError, ValueError):
        return None
    if digits is not None and isinstance(out, float):
        return round(out, digits)
    return out


def _unavailable(reason: str) -> dict:
    return {"available": False, "reason": reason}


# ---------------------------------------------------------------------------
# 1. Market context
# ---------------------------------------------------------------------------


def summarize_market_context(
    ticker: str, as_of: Optional[date_type] = None
) -> dict:
    """Daily OHLCV + indicators + regime classification.

    Reads market_data_daily for the row at or before `as_of` (default:
    latest). Computes a regime tag (trending up/down/ranging) and a
    20-day realized vol tag (low/normal/elevated).
    """
    sql = (
        "SELECT date, open, high, low, close, volume, "
        "       sma_200, ema_20, ema_50, rsi_14, macd, macd_signal, "
        "       macd_histogram, bb_upper, bb_lower, bb_pct, atr_14, "
        "       rvol, volatility_20d, price_vs_ema20 "
        "FROM market_data_daily "
        "WHERE ticker = :ticker "
        + ("AND date <= :as_of " if as_of else "")
        + "ORDER BY date DESC LIMIT 1"
    )
    params: dict[str, Any] = {"ticker": ticker.upper()}
    if as_of:
        params["as_of"] = str(as_of)
    df = _query(sql, params)
    if df.empty:
        return _unavailable(f"no market_data_daily row for {ticker}")

    row = df.iloc[0]
    close = _scalar(row, "close", digits=2)
    ema_20 = _scalar(row, "ema_20", digits=2)
    sma_200 = _scalar(row, "sma_200", digits=2)
    rsi = _scalar(row, "rsi_14", digits=1)
    vol20 = _scalar(row, "volatility_20d", digits=3)
    price_vs_ema20 = _scalar(row, "price_vs_ema20", digits=3)

    # Trend tag
    above_200 = None
    if close is not None and sma_200 is not None:
        above_200 = close > sma_200
    if above_200 is True and (price_vs_ema20 or 0) > 0:
        regime = "trending_up"
    elif above_200 is False and (price_vs_ema20 or 0) < 0:
        regime = "trending_down"
    else:
        regime = "ranging"

    # Vol tag (annualized 20d realized)
    if vol20 is None:
        vol_tag = "unknown"
    elif vol20 < 0.12:
        vol_tag = "low"
    elif vol20 < 0.22:
        vol_tag = "normal"
    else:
        vol_tag = "elevated"

    return {
        "available": True,
        "date": str(row.get("date", "")),
        "close": close,
        "ema_20": ema_20,
        "sma_200": sma_200,
        "above_sma_200": above_200,
        "rsi_14": rsi,
        "price_vs_ema20_pct": price_vs_ema20,
        "bb_pct": _scalar(row, "bb_pct", digits=3),
        "atr_14": _scalar(row, "atr_14", digits=2),
        "rvol": _scalar(row, "rvol", digits=2),
        "volatility_20d": vol20,
        "regime": regime,
        "vol_tag": vol_tag,
        "macd": _scalar(row, "macd", digits=4),
        "macd_histogram": _scalar(row, "macd_histogram", digits=4),
    }


# ---------------------------------------------------------------------------
# 2. Strat status (live recompute from market_data_daily — audit fix #10)
# ---------------------------------------------------------------------------


def summarize_strat_status(
    ticker: str, as_of: Optional[date_type] = None
) -> dict:
    """Rob Smith strat state from the most recent daily row.

    Reads `strat_candle`, `strat_combo`, `strat_setup`, `ftfc_score`,
    `ftfc_direction`, prev_day high/low from market_data_daily. This
    is computed live from daily bars by the fetcher, so it's always
    fresh — no dependency on stale premarket_analysis snapshots.

    Returns the fields expected by StratSnapshot in schema.py plus
    `available` and `trigger_high` / `trigger_low`.
    """
    sql = (
        "SELECT date, strat_candle, strat_combo, strat_setup, "
        "       ftfc_score, ftfc_direction, high, low "
        "FROM market_data_daily "
        "WHERE ticker = :ticker "
        + ("AND date <= :as_of " if as_of else "")
        + "ORDER BY date DESC LIMIT 2"
    )
    params: dict[str, Any] = {"ticker": ticker.upper()}
    if as_of:
        params["as_of"] = str(as_of)
    df = _query(sql, params)
    if df.empty:
        return _unavailable(f"no market_data_daily for {ticker}")

    row = df.iloc[0]
    candle = row.get("strat_candle") or "1"
    combo = row.get("strat_combo")
    ftfc_score = _scalar(row, "ftfc_score", digits=2)
    ftfc_direction = row.get("ftfc_direction") or "mixed"

    # Prior day high/low as trigger levels
    if len(df) >= 2:
        prev = df.iloc[1]
        trig_high = _scalar(prev, "high", digits=2)
        trig_low = _scalar(prev, "low", digits=2)
    else:
        trig_high = trig_low = None

    return {
        "available": True,
        "date": str(row.get("date", "")),
        "last_candle": candle,
        "in_force_combo": combo,
        "strat_setup": bool(row.get("strat_setup", False)),
        "ftfc_score": ftfc_score if ftfc_score is not None else 0.0,
        "ftfc_direction": ftfc_direction,
        "trigger_high": trig_high,
        "trigger_low": trig_low,
    }


# ---------------------------------------------------------------------------
# 3. Options flow
# ---------------------------------------------------------------------------


def summarize_options_flow(
    ticker: str, as_of: Optional[date_type] = None
) -> dict:
    """Latest AlphaVantage EOD options chain snapshot aggregates.

    Returns total call/put volume, put/call ratio, max-pain strike,
    top open-interest strikes, and weighted average IV.
    """
    sql = (
        "SELECT option_type, strike, volume, open_interest, "
        "       implied_volatility, delta "
        "FROM etf_options_snapshots "
        "WHERE ticker = :ticker "
        "  AND data_source = 'alphavantage' "
        + ("AND snapshot_date <= :as_of " if as_of else "")
        + "  AND snapshot_date = ("
        "      SELECT MAX(snapshot_date) FROM etf_options_snapshots "
        "      WHERE ticker = :ticker AND data_source = 'alphavantage'"
        + ("      AND snapshot_date <= :as_of" if as_of else "")
        + "  )"
    )
    params: dict[str, Any] = {"ticker": ticker.upper()}
    if as_of:
        params["as_of"] = str(as_of)
    df = _query(sql, params)
    if df.empty:
        return _unavailable(f"no etf_options_snapshots for {ticker}")

    calls = df[df["option_type"] == "calls"]
    puts = df[df["option_type"] == "puts"]
    call_vol = int(calls["volume"].fillna(0).sum())
    put_vol = int(puts["volume"].fillna(0).sum())
    pcr = round(put_vol / call_vol, 3) if call_vol > 0 else None

    # Max pain: strike that minimizes total dollar payout of ITM options
    # Approximation: the strike where call OI + put OI is maximized (simple proxy)
    if not df.empty:
        oi_by_strike = (
            df.groupby("strike")["open_interest"].sum().fillna(0).sort_values(ascending=False)
        )
        top_strikes = oi_by_strike.head(5).index.tolist()
        max_pain_proxy = float(oi_by_strike.idxmax()) if not oi_by_strike.empty else None
    else:
        top_strikes = []
        max_pain_proxy = None

    # Weighted-average IV by volume
    vol_series = df["volume"].fillna(0)
    iv_series = df["implied_volatility"].fillna(0)
    total_vol = vol_series.sum()
    avg_iv = (
        round(float((iv_series * vol_series).sum() / total_vol), 3)
        if total_vol > 0
        else None
    )

    return {
        "available": True,
        "call_volume": call_vol,
        "put_volume": put_vol,
        "put_call_ratio": pcr,
        "max_pain_strike_proxy": max_pain_proxy,
        "top_oi_strikes": [float(s) for s in top_strikes],
        "vol_weighted_iv": avg_iv,
        "contract_count": int(len(df)),
    }


# ---------------------------------------------------------------------------
# 3b. Gamma levels (King / Gate / Spot / Flip taxonomy + regime)
# ---------------------------------------------------------------------------


def summarize_gamma_levels(
    ticker: str, as_of: Optional[date_type] = None
) -> dict:
    """Stratalyst-style gamma analytics: King / Gate / Spot / Flip + regime.

    Pulls the latest AlphaVantage chain for the ticker (or the most recent
    snapshot on or before `as_of`) and runs lib.gamma.build_summary. The
    output feeds the gamma analyst prompt; any consumer wanting a richer
    response should call the /api/options/{ticker}/{date}/levels endpoint
    directly instead of consuming this summary.
    """
    from lib import gamma  # local import to avoid circular at module load

    sql = (
        "SELECT option_type, strike, expiration, "
        "       open_interest, gamma, vega, delta, "
        "       bid, ask, mark, last_price "
        "FROM etf_options_snapshots "
        "WHERE ticker = :ticker "
        "  AND data_source = 'alphavantage' "
        + ("AND snapshot_date <= :as_of " if as_of else "")
        + "  AND snapshot_date = ("
        "      SELECT MAX(snapshot_date) FROM etf_options_snapshots "
        "      WHERE ticker = :ticker AND data_source = 'alphavantage'"
        + ("      AND snapshot_date <= :as_of" if as_of else "")
        + "  )"
    )
    params: dict[str, Any] = {"ticker": ticker.upper()}
    if as_of:
        params["as_of"] = str(as_of)
    df = _query(sql, params)
    if df.empty:
        return _unavailable(f"no etf_options_snapshots for {ticker}")

    # Map the chain rows to the dict shape lib.gamma accepts.
    type_map = {"calls": "call", "puts": "put"}
    options = []
    for row in df.to_dict(orient="records"):
        exp = row.get("expiration")
        if hasattr(exp, "strftime"):
            exp = exp.strftime("%Y-%m-%d")
        options.append({
            "type": type_map.get(row.get("option_type"), row.get("option_type")),
            "strike": row.get("strike"),
            "expiration": exp,
            "open_interest": row.get("open_interest"),
            "gamma": row.get("gamma"),
            "vega": row.get("vega"),
            "delta": row.get("delta"),
            "bid": row.get("bid"),
            "ask": row.get("ask"),
            "mark": row.get("mark"),
            "last": row.get("last_price"),
        })

    snapshot_date = str(as_of) if as_of else "latest"
    summary = gamma.build_summary(
        ticker=ticker,
        snapshot_date=snapshot_date,
        options=options,
    )

    # Compact shape for the analyst — full GammaSummary is too verbose.
    def _level_brief(lv: gamma.Level) -> dict:
        return {
            "strike": lv.strike,
            "gex": round(lv.gex, 0),
            "distance_pct": round(lv.distance_pct, 2),
            "call_oi": lv.call_oi,
            "put_oi": lv.put_oi,
        }

    return {
        "available": True,
        "spot": round(summary.spot.price, 2),
        "spot_method": summary.spot.method,
        "flip": round(summary.flip, 2) if summary.flip else None,
        "regime": summary.regime,
        "total_gex": round(summary.total_gex, 0),
        "kings": [_level_brief(lv) for lv in summary.kings[:3]],
        "gates": [_level_brief(lv) for lv in summary.gates[:5]],
        "flip_levels": [_level_brief(lv) for lv in summary.flip_levels],
        "warnings": summary.warnings,
        "chain_size": len(options),
    }


# ---------------------------------------------------------------------------
# 4. Signal history
# ---------------------------------------------------------------------------


def summarize_signals_history(
    ticker: str,
    lookback_days: int = 30,
    as_of: Optional[date_type] = None,
) -> dict:
    """signal_alerts aggregates anchored at `as_of`.

    Returns the `lookback_days` window ending at `as_of` (defaults to
    now when None). Grouped by direction/strength, with the 5 most
    recent rows for reference. Historical runs therefore see the same
    data the live platform would have seen on `as_of`, not today's
    live signals.
    """
    if as_of is None:
        sql = (
            "SELECT alert_ts, direction, strength_label, total_score "
            "FROM signal_alerts "
            "WHERE ticker = :ticker "
            "  AND alert_ts >= NOW() - (:days || ' days')::interval "
            "ORDER BY alert_ts DESC"
        )
        params: dict[str, Any] = {"ticker": ticker.upper(), "days": lookback_days}
    else:
        # CAST() rather than ::timestamptz because SQLAlchemy text()
        # collides with the `::` cast syntax when it appears right
        # after a :param reference. Explicit cast also fixes pg8000
        # TEXT binding for `end - interval` math.
        # Use start of the *next* day with `<` so that all intraday
        # alerts on `as_of` are included (str(date) resolves to midnight
        # at the *start*, which would exclude the entire day with `<=`).
        end_exclusive = as_of + timedelta(days=1)
        sql = (
            "SELECT alert_ts, direction, strength_label, total_score "
            "FROM signal_alerts "
            "WHERE ticker = :ticker "
            "  AND alert_ts < CAST(:end_ts AS timestamptz) "
            "  AND alert_ts >= CAST(:end_ts AS timestamptz) - (:days || ' days')::interval "
            "ORDER BY alert_ts DESC"
        )
        params = {
            "ticker": ticker.upper(),
            "days": lookback_days,
            "end_ts": str(end_exclusive),
        }
    df = _query(sql, params)
    if df.empty:
        return {
            "available": True,
            "lookback_days": lookback_days,
            "total_alerts": 0,
            "call_count": 0,
            "put_count": 0,
            "recent": [],
        }

    call_count = int((df["direction"] == "CALL").sum())
    put_count = int((df["direction"] == "PUT").sum())
    recent_rows = df.head(5).to_dict(orient="records")
    recent = [
        {
            "alert_ts": str(r["alert_ts"]),
            "direction": r["direction"],
            "strength": r.get("strength_label") or "unknown",
            "score": float(r["total_score"]) if r.get("total_score") is not None else 0.0,
        }
        for r in recent_rows
    ]

    return {
        "available": True,
        "lookback_days": lookback_days,
        "total_alerts": int(len(df)),
        "call_count": call_count,
        "put_count": put_count,
        "recent": recent,
    }


# ---------------------------------------------------------------------------
# 5. Backtest metrics
# ---------------------------------------------------------------------------


def summarize_backtest_metrics(
    ticker: str,
    lookback_days: int = 90,
    as_of: Optional[date_type] = None,
) -> dict:
    """Aggregate metrics over pipeline trades in the lookback window
    ending at `as_of` (defaults to today when None).

    Computes win rate, avg return, profit factor (sum of wins / abs
    sum of losses), and raw trade count. Sharpe is intentionally
    omitted — it needs a longer horizon than 90 days of intraday
    trades to be meaningful.

    Historical runs pass `as_of` so the metrics reflect what the
    platform's trade log *looked like* on that date, not today.
    """
    if as_of is None:
        sql = (
            "SELECT return_pct, direction, exit_reason "
            "FROM trades "
            "WHERE ticker = :ticker "
            "  AND trade_date >= CURRENT_DATE - (:days || ' days')::interval"
        )
        params: dict[str, Any] = {"ticker": ticker.upper(), "days": lookback_days}
    else:
        # Same pg8000-vs-psycopg2 + SQLAlchemy cast-parser story as
        # summarize_signals_history — use CAST() not ::.
        sql = (
            "SELECT return_pct, direction, exit_reason "
            "FROM trades "
            "WHERE ticker = :ticker "
            "  AND trade_date <= CAST(:end_date AS date) "
            "  AND trade_date >= CAST(:end_date AS date) - (:days || ' days')::interval"
        )
        params = {
            "ticker": ticker.upper(),
            "days": lookback_days,
            "end_date": str(as_of),
        }
    df = _query(sql, params)
    if df.empty:
        return _unavailable(f"no trades for {ticker} in last {lookback_days}d")

    returns = df["return_pct"].dropna().astype(float)
    if returns.empty:
        return _unavailable("trades exist but have no return_pct")

    wins = returns[returns > 0]
    losses = returns[returns < 0]
    win_rate = float(len(wins)) / float(len(returns))

    gross_wins = float(wins.sum())
    gross_losses = float(-losses.sum())
    profit_factor = (
        round(gross_wins / gross_losses, 2) if gross_losses > 0 else None
    )

    return {
        "available": True,
        "lookback_days": lookback_days,
        "trade_count": int(len(returns)),
        "win_rate": round(win_rate, 3),
        "avg_return_pct": round(float(returns.mean()), 3),
        "profit_factor": profit_factor,
        "gross_wins_pct": round(gross_wins, 3),
        "gross_losses_pct": round(gross_losses, 3),
    }


# ---------------------------------------------------------------------------
# 6. Catalysts (economic + earnings)
# ---------------------------------------------------------------------------


def summarize_catalysts(
    ticker: str, as_of: Optional[date_type] = None, lookahead_days: int = 14
) -> dict:
    """Next N days of economic events + earnings dates.

    Economic events are market-wide (no ticker filter); earnings are
    ticker-specific. Merged, sorted by date, capped at 5 entries.
    """
    today = as_of or datetime.now(timezone.utc).date()
    end = today + timedelta(days=lookahead_days)

    econ_sql = (
        "SELECT event_date, event_name, importance "
        "FROM economic_events "
        "WHERE event_date BETWEEN :start AND :end "
        "  AND importance IN ('high', 'medium') "
        "ORDER BY event_date ASC LIMIT 10"
    )
    econ_df = _query(econ_sql, {"start": str(today), "end": str(end)})

    earn_sql = (
        "SELECT earnings_date, company_name "
        "FROM earnings_calendar "
        "WHERE ticker = :ticker "
        "  AND earnings_date BETWEEN :start AND :end "
        "ORDER BY earnings_date ASC LIMIT 5"
    )
    earn_df = _query(
        earn_sql, {"ticker": ticker.upper(), "start": str(today), "end": str(end)}
    )

    out: list[dict] = []
    if not econ_df.empty:
        for _, r in econ_df.iterrows():
            out.append(
                {
                    "name": str(r["event_name"]),
                    "date": str(r["event_date"]),
                    "impact": str(r.get("importance") or "medium"),
                    "kind": "economic",
                }
            )
    if not earn_df.empty:
        for _, r in earn_df.iterrows():
            out.append(
                {
                    "name": f"Earnings — {r.get('company_name') or ticker.upper()}",
                    "date": str(r["earnings_date"]),
                    "impact": "high",
                    "kind": "earnings",
                }
            )

    out.sort(key=lambda e: e["date"])
    return {
        "available": True,
        "window_start": str(today),
        "window_end": str(end),
        "events": out[:5],
    }


# ---------------------------------------------------------------------------
# 7. News sentiment
# ---------------------------------------------------------------------------


def summarize_news_sentiment(
    ticker: str, as_of: Optional[date_type] = None, lookback_hours: int = 48
) -> dict:
    """Aggregate recent news sentiment from the news_sentiment table.

    Returns headline counts, average sentiment score, and the top 5
    most relevant recent headlines. Uses a 48-hour lookback window
    ending at `as_of` (defaults to now when None).
    """
    if as_of is None:
        sql = (
            "SELECT title, sentiment_score, relevance_score, source, published_ts "
            "FROM news_sentiment "
            "WHERE ticker = :ticker "
            "  AND published_ts >= NOW() - (:hours || ' hours')::interval "
            "ORDER BY published_ts DESC"
        )
        params: dict[str, Any] = {"ticker": ticker.upper(), "hours": lookback_hours}
    else:
        # Use start of the *next* day with `<` so intraday articles on
        # `as_of` are included (str(date) resolves to midnight start).
        end_exclusive = as_of + timedelta(days=1)
        sql = (
            "SELECT title, sentiment_score, relevance_score, source, published_ts "
            "FROM news_sentiment "
            "WHERE ticker = :ticker "
            "  AND published_ts < CAST(:end_ts AS timestamptz) "
            "  AND published_ts >= CAST(:end_ts AS timestamptz) - (:hours || ' hours')::interval "
            "ORDER BY published_ts DESC"
        )
        params = {
            "ticker": ticker.upper(),
            "hours": lookback_hours,
            "end_ts": str(end_exclusive),
        }
    df = _query(sql, params)
    if df.empty:
        return _unavailable(f"no news_sentiment rows for {ticker} in last {lookback_hours}h")

    scores = df["sentiment_score"].dropna().astype(float)
    relevances = df["relevance_score"].dropna().astype(float)

    bullish = int((scores > 0.15).sum())
    bearish = int((scores < -0.15).sum())
    neutral = int(len(scores)) - bullish - bearish
    avg_score = round(float(scores.mean()), 4) if not scores.empty else 0.0

    # Top 5 most relevant headlines
    top_df = df.nlargest(5, "relevance_score") if "relevance_score" in df.columns else df.head(5)
    headlines = [
        {
            "title": str(r.get("title", "")),
            "sentiment": round(float(r["sentiment_score"]), 3) if r.get("sentiment_score") is not None else None,
            "source": str(r.get("source", "")),
            "published": str(r.get("published_ts", "")),
        }
        for _, r in top_df.iterrows()
    ]

    return {
        "available": True,
        "lookback_hours": lookback_hours,
        "article_count": int(len(df)),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "avg_sentiment_score": avg_score,
        "headlines": headlines,
    }


# ---------------------------------------------------------------------------
# 8. Reflection memory (pgvector over journal_entries)
# ---------------------------------------------------------------------------


def retrieve_similar_journal(
    ticker: str, query_embedding: list[float], k: int = 5
) -> list[JournalRef]:
    """Find journal entries whose embedding is closest to the query.

    Uses pgvector cosine distance (`<=>`). Returns `JournalRef` objects
    (not raw rows) so downstream agents receive typed data.
    """
    if not query_embedding or len(query_embedding) == 0:
        return []

    # psycopg2 has no native pgvector adapter; serialize to text literal.
    vec_literal = format_vector_literal(query_embedding)
    sql = (
        "SELECT id::text AS id, ticker, direction, return_pct, "
        "       (embedding <=> :vec::vector) AS cosine_distance "
        "FROM journal_entries "
        "WHERE embedding IS NOT NULL AND ticker = :ticker "
        "ORDER BY embedding <=> :vec::vector ASC "
        "LIMIT :k"
    )
    df = _query(sql, {"vec": vec_literal, "ticker": ticker.upper(), "k": k})
    if df.empty:
        return []
    out: list[JournalRef] = []
    for _, row in df.iterrows():
        out.append(
            JournalRef(
                id=str(row["id"]),
                ticker=str(row["ticker"]),
                direction=str(row["direction"]),
                return_pct=(
                    float(row["return_pct"]) if row.get("return_pct") is not None else None
                ),
                cosine_distance=float(row["cosine_distance"]),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Bundle — one call to collect every section. Failed summaries are
# captured in `failed_sections` rather than raising.
# ---------------------------------------------------------------------------


def build_context_bundle(
    ticker: str, as_of: Optional[date_type] = None
) -> dict:
    """Collect all summarizer outputs into one dict for analyst prompts.

    Each section is either a populated dict with `available: True` or
    `{available: False, reason: ...}`. A top-level `failed_sections`
    list tells the orchestrator which sections to mark degraded.
    """
    bundle = {
        "ticker": ticker.upper(),
        "as_of": str(as_of) if as_of else None,
    }
    sections = {
        "market": lambda: summarize_market_context(ticker, as_of),
        "strat": lambda: summarize_strat_status(ticker, as_of),
        "options": lambda: summarize_options_flow(ticker, as_of),
        "gamma": lambda: summarize_gamma_levels(ticker, as_of),
        "signals": lambda: summarize_signals_history(ticker, as_of=as_of),
        "backtest": lambda: summarize_backtest_metrics(ticker, as_of=as_of),
        "catalysts": lambda: summarize_catalysts(ticker, as_of),
        "sentiment": lambda: summarize_news_sentiment(ticker, as_of),
    }
    failed: list[str] = []
    for name, fn in sections.items():
        try:
            result = fn()
            bundle[name] = result
            if not result.get("available"):
                failed.append(name)
        except Exception as e:
            logger.exception("summarizer %s failed", name)
            bundle[name] = {"available": False, "reason": f"exception: {e}"}
            failed.append(name)
    bundle["failed_sections"] = failed
    return bundle
