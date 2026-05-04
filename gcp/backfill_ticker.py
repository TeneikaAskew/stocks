"""
Backfill historical data for a single ticker — Cloud Run Job.

Triggered by the Discord `/replay` command when the requested ticker has
no daily history in `market_data_daily`. The job:

  1. Calls AV TIME_SERIES_DAILY_ADJUSTED (outputsize=full) and writes
     the most recent ``BACKFILL_HISTORY_DAYS`` rows (default 250) into
     market_data_daily — enough history for ATR14, SMA200, weekly /
     monthly / quarterly level computation.
  2. Calls AV TIME_SERIES_INTRADAY for every month touched by
     BACKFILL_DATES + the prior trading day so pre-market context can
     be computed using the prior-close reference.
  3. Optionally calls AV NEWS_SENTIMENT for the
     ``[first_date - news_window, last_date + 1d]`` window.
  4. Computes pre-market context (pre_high / pre_low / pre_vwap /
     pre_volume / gap_pct / pre_range_atr) for each requested date
     plus its prior trading day.
  5. Adds the ticker to the `watchlists` Cloud SQL table so subsequent
     `/replay` invocations skip the backfill (idempotent ON CONFLICT).

Everything runs through ``gcp.database.upsert_dataframe`` — the same
Cloud SQL Connector path the rest of the platform uses, so this works
in Cloud Run without IAM headaches.

Environment:
  BACKFILL_TICKER          ticker symbol, e.g. AMD                (required)
  BACKFILL_DATES           comma- or semicolon-separated dates
                           that need pre-market context computed.
                           If unset, defaults to the last 7 weekdays.
  BACKFILL_HISTORY_DAYS    daily-history depth (default 250)
  BACKFILL_INCLUDE_NEWS    "true" / "false" (default "true")
  BACKFILL_NEWS_WINDOW     news lookback in days (default 7)
  ALPHA_VANTAGE_API_KEY    AV key (mounted from Secret Manager)
  CLOUD_SQL_CONNECTION_NAME / DB_USER / DB_PASS / DB_NAME
                           Cloud SQL Connector creds
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s - %(message)s")
log = logging.getLogger("backfill-ticker")


AV_BASE = "https://www.alphavantage.co/query"


# ──────────────────────────────────────────────────────────────────────
# Env resolution
# ──────────────────────────────────────────────────────────────────────
def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    return v.strip() if v and v.strip() else default


def _parse_dates(raw: Optional[str]) -> list[date]:
    """Parse BACKFILL_DATES — accepts comma, semicolon, or whitespace."""
    if not raw:
        # Default: the last 7 weekdays — enough to backfill any recent
        # /replay request without the user having to spell out dates.
        out: list[date] = []
        d = date.today()
        while len(out) < 7:
            d -= timedelta(days=1)
            if d.weekday() < 5:
                out.append(d)
        return sorted(out)
    cleaned = raw.replace(",", " ").replace(";", " ").split()
    return sorted({date.fromisoformat(s) for s in cleaned if s.strip()})


# ──────────────────────────────────────────────────────────────────────
# AlphaVantage
# ──────────────────────────────────────────────────────────────────────
def av_daily_full(ticker: str, api_key: str) -> pd.DataFrame:
    """Pull entire daily history (split/dividend-adjusted)."""
    log.info("AV daily-full %s", ticker)
    r = requests.get(AV_BASE, params={
        "function": "TIME_SERIES_DAILY_ADJUSTED",
        "symbol": ticker, "outputsize": "full",
        "datatype": "json", "apikey": api_key,
    }, timeout=60)
    r.raise_for_status()
    data = r.json()
    if any(k in data for k in ("Error Message", "Information", "Note")):
        msg = data.get("Error Message") or data.get("Information") or data.get("Note")
        raise RuntimeError(f"AV daily {ticker}: {msg}")
    ts = data.get("Time Series (Daily)") or {}
    if not ts:
        raise RuntimeError(f"AV daily {ticker}: empty time series")
    rows = []
    for d, v in ts.items():
        rows.append({
            "date":           pd.to_datetime(d).date(),
            "open":           float(v["1. open"]),
            "high":           float(v["2. high"]),
            "low":            float(v["3. low"]),
            "close":          float(v["4. close"]),
            "adjusted_close": float(v["5. adjusted close"]),
            "volume":         int(v["6. volume"]),
        })
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    log.info("  → %d daily rows (%s … %s)", len(df), df["date"].iloc[0], df["date"].iloc[-1])
    return df


def av_intraday_month(ticker: str, year_month: str, api_key: str) -> pd.DataFrame:
    """Pull a full month of 1-min bars (extended hours included)."""
    log.info("AV intraday-month %s %s", ticker, year_month)
    r = requests.get(AV_BASE, params={
        "function": "TIME_SERIES_INTRADAY", "symbol": ticker,
        "interval": "1min", "month": year_month,
        "outputsize": "full", "adjusted": "true",
        "extended_hours": "true", "entitlement": "realtime",
        "datatype": "json", "apikey": api_key,
    }, timeout=120)
    r.raise_for_status()
    data = r.json()
    if any(k in data for k in ("Error Message", "Information", "Note")):
        msg = data.get("Error Message") or data.get("Information") or data.get("Note")
        raise RuntimeError(f"AV intraday {ticker} {year_month}: {msg}")
    ts = data.get("Time Series (1min)") or {}
    if not ts:
        log.warning("  AV intraday: empty for %s %s", ticker, year_month)
        return pd.DataFrame()
    df = pd.DataFrame.from_dict(ts, orient="index")
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    for c in ("Open", "High", "Low", "Close"):
        df[c] = pd.to_numeric(df[c])
    df["Volume"] = pd.to_numeric(df["Volume"]).astype("int64")
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    log.info("  → %d intraday bars", len(df))
    return df


def av_news(ticker: str, time_from: str, time_to: str,
            api_key: str, limit: int = 1000) -> list[dict]:
    """Pull NEWS_SENTIMENT for ticker over [time_from, time_to] (UTC)."""
    log.info("AV news %s [%s → %s]", ticker, time_from, time_to)
    r = requests.get(AV_BASE, params={
        "function": "NEWS_SENTIMENT", "tickers": ticker,
        "time_from": time_from, "time_to": time_to,
        "sort": "EARLIEST", "limit": limit, "apikey": api_key,
    }, timeout=60)
    r.raise_for_status()
    data = r.json()
    if "Information" in data:
        log.warning("  AV news: %s", data["Information"])
    feed = data.get("feed") or []
    log.info("  → %d articles", len(feed))
    return feed


def _safe_float(x) -> Optional[float]:
    if x is None or x == "" or x == "None":
        return None
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


def av_news_to_rows(feed: list[dict]) -> list[dict]:
    """Explode AV news feed into one row per (article, ticker)."""
    rows = []
    for art in feed:
        pub_raw = art.get("time_published") or ""
        try:
            pub_ts = datetime.strptime(pub_raw[:15], "%Y%m%dT%H%M%S").replace(
                tzinfo=timezone.utc,
            )
        except Exception:
            continue
        title = (art.get("title") or "")[:500] or None
        url = (art.get("url") or "")[:1000] or None
        summary = (art.get("summary") or "")[:2000] or None
        source = (art.get("source") or "")[:100] or None
        overall_score = _safe_float(art.get("overall_sentiment_score"))
        overall_label = (art.get("overall_sentiment_label") or "")[:20] or None
        topics = [t["topic"] for t in (art.get("topics") or [])
                  if isinstance(t, dict) and t.get("topic")]
        for tk in (art.get("ticker_sentiment") or []):
            tkv = (tk.get("ticker") or "").upper().strip()
            if not tkv:
                continue
            rows.append({
                "ticker": tkv,
                "published_ts": pub_ts,
                "title": title, "url": url, "summary": summary,
                "sentiment_score": _safe_float(tk.get("ticker_sentiment_score")),
                "relevance_score": _safe_float(tk.get("relevance_score")),
                "overall_sentiment_score": overall_score,
                "overall_sentiment_label": overall_label,
                "topics": topics or None,
                "source": source,
                "data_source": "alphavantage",
                "match_method": "av_ticker_sentiment",
            })
    return rows


# ──────────────────────────────────────────────────────────────────────
# Watchlist + indicator computation
# ──────────────────────────────────────────────────────────────────────
def add_to_watchlist(ticker: str) -> None:
    """Insert into watchlists table; idempotent via ON CONFLICT.

    Schema (per gcp/schema.sql):
      * Composite PK is (user_id, ticker), with user_id defaulting to
        'default'. The Discord-driven /replay flow always uses 'default'.
      * `added_at TIMESTAMPTZ` defaults to NOW() — we don't pass it.
      * `removed_at IS NULL` encodes "active". Any existing soft-removed
        row gets reactivated by clearing removed_at.

    `source='discord-replay'` tags rows added via this auto-backfill
    path so a later audit can tell self-served replay tickers apart
    from manually-curated watchlist entries.
    """
    from gcp.database import get_engine
    import sqlalchemy
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                "INSERT INTO watchlists (user_id, ticker, source) "
                "VALUES ('default', :t, 'discord-replay') "
                "ON CONFLICT (user_id, ticker) DO UPDATE "
                "  SET removed_at = NULL, "
                "      source = COALESCE(watchlists.source, EXCLUDED.source)"
            ),
            {"t": ticker.upper()},
        )
    log.info("✓ added %s to watchlists", ticker.upper())


# Multi-day indicator → DB column mapping. Module-level so
# compute_indicators_for_full_range and compute_indicators_for_dates
# stay in sync when we add or rename indicators.
_IND_MAP = {
    "MA5": "ma_5", "MA10": "ma_10", "MA20": "ma_20", "MA50": "ma_50",
    "EMA9": "ema_9", "EMA20": "ema_20", "EMA50": "ema_50", "SMA200": "sma_200",
    "RSI": "rsi_14", "RSI9": "rsi_9", "RSI30": "rsi_30",
    "StochRSI_K": "stoch_rsi_k", "StochRSI_D": "stoch_rsi_d",
    "ATR14": "atr_14", "ATR20": "atr_20",
    "OBV": "obv", "RVOL": "rvol", "RVOL10": "rvol_10",
    "Volume_MA10": "volume_ma_10", "Volume_MA20": "volume_ma_20",
    "Volume_USD": "volume_usd",
    "MACD": "macd", "MACD_Signal": "macd_signal", "MACD_Histogram": "macd_histogram",
    "BB_Upper": "bb_upper", "BB_Lower": "bb_lower",
    "BB_Width": "bb_width", "BB_Pct": "bb_pct",
    "Return": "return", "volatility_5d": "volatility_5d",
    "volatility_20d": "volatility_20d",
    "high_low_spread": "high_low_spread",
    "high_low_spread_pct": "high_low_spread_pct",
    "consecutive_up": "consecutive_up",
    "consecutive_down": "consecutive_down",
    "VWAP": "vwap", "Price_vs_VWAP": "price_vs_vwap",
    "Price_vs_EMA9": "price_vs_ema9",
    "Price_vs_EMA20": "price_vs_ema20",
}
_INT_COLS = {"consecutive_up", "consecutive_down"}


def compute_indicators_for_full_range(ticker: str) -> int:
    """Compute multi-day indicators (RSI, MA, EMA, ATR, etc.) for EVERY
    OHLC row we have for this ticker, and upsert them in chunks.

    Closes the gap where ``compute_indicators_for_dates`` (and the
    daily fetcher's ``compute_and_upsert_daily_indicators``) only write
    indicator values for one target date even though the full
    rolling-window context was already computed in memory. Without
    this, a freshly-backfilled ticker has 250+ days of OHLC but
    indicators populated on only a handful of rows — every historical
    ATR/RSI/MA query against the rest of the range returns NULL.

    Strat fields and pre-market context are *not* written here — those
    require per-date intraday bars and stay in
    ``compute_indicators_for_dates``.

    Returns the number of rows upserted.
    """
    from gcp.database import query_to_dataframe, upsert_dataframe
    from lib.indicators import add_all_indicators

    df = query_to_dataframe(
        'SELECT date, open AS "Open", high AS "High", low AS "Low", '
        'close AS "Close", volume AS "Volume" '
        "FROM market_data_daily "
        "WHERE ticker = :ticker "
        "ORDER BY date ASC",
        {"ticker": ticker.upper()},
    )
    if df.empty or len(df) < 2:
        log.warning(
            "insufficient daily history for %s (%d rows) — "
            "skipping full-range indicators", ticker, len(df),
        )
        return 0

    enriched = add_all_indicators(df, close_col="Close")
    enriched["volatility_20d"] = (
        enriched["Close"].pct_change().rolling(20).std() * np.sqrt(252)
    )

    rows: list[dict] = []
    for i in range(len(enriched)):
        bar = enriched.iloc[i]
        row: dict = {"ticker": ticker.upper(), "date": df["date"].iloc[i]}
        any_set = False
        for src, dst in _IND_MAP.items():
            v = bar.get(src)
            if v is not None and pd.notna(v):
                row[dst] = int(v) if dst in _INT_COLS else float(v)
                any_set = True
        if any_set:
            rows.append(row)

    if not rows:
        log.warning("no indicator rows produced for %s", ticker)
        return 0

    # Chunked upsert (CLAUDE.md §0.4): bound memory and let a partial
    # crash leave durable progress instead of losing the whole batch.
    CHUNK = 200
    total = 0
    for start in range(0, len(rows), CHUNK):
        chunk = rows[start:start + CHUNK]
        upsert_dataframe(
            pd.DataFrame(chunk),
            "market_data_daily", ["ticker", "date"],
        )
        total += len(chunk)
        log.info("  ✓ indicators %s rows %d-%d/%d",
                 ticker, start, start + len(chunk), len(rows))
    log.info("✓ full-range indicators %s: %d rows upserted", ticker, total)
    return total


def compute_indicators_for_dates(ticker: str, target_dates: list[date]) -> None:
    """For each target_date, recompute multi-day indicators + pre-market
    context from the data we just loaded. Mirrors gcp.fetchers.
    fetch_market_data.compute_and_upsert_daily_indicators so the
    backfilled rows look identical to a live-fetched row."""
    from gcp.database import query_to_dataframe, upsert_dataframe
    from lib.indicators import add_all_indicators, calculate_premarket_context
    from lib.strat import StratClassifier

    clf = StratClassifier()

    for fd in sorted(target_dates):
        df = query_to_dataframe(
            'SELECT date, open AS "Open", high AS "High", low AS "Low", '
            'close AS "Close", volume AS "Volume" '
            "FROM market_data_daily "
            "WHERE ticker = :ticker AND date <= :fd "
            "ORDER BY date DESC LIMIT 250",
            {"ticker": ticker.upper(), "fd": str(fd)},
        )
        if df.empty or len(df) < 2:
            log.warning("insufficient daily history for %s @ %s (%d rows)",
                        ticker, fd, len(df))
            continue
        df = df.iloc[::-1].reset_index(drop=True)
        enriched = add_all_indicators(df, close_col="Close")
        enriched["volatility_20d"] = (
            enriched["Close"].pct_change().rolling(20).std() * np.sqrt(252)
        )
        last = enriched.iloc[-1]

        row: dict = {"ticker": ticker.upper(), "date": fd}
        for src, dst in _IND_MAP.items():
            v = last.get(src)
            if v is not None and pd.notna(v):
                row[dst] = int(v) if dst in _INT_COLS else float(v)

        # Strat fields
        try:
            ohlc = enriched[["Open", "High", "Low", "Close"]]
            labels = clf.classify_series(ohlc)
            last_candle = labels.iloc[-1]
            combos = clf.detect_combos(ohlc, labels)
            last_combo = (combos.iloc[-1].get("combo")
                          if not combos.empty else None)
            df_dt = enriched.copy()
            df_dt["date"] = df["date"].values
            df_dt = df_dt.set_index(pd.to_datetime(df_dt["date"]))
            weekly = df_dt[["Open", "High", "Low", "Close"]].resample("W").agg({
                "Open": "first", "High": "max", "Low": "min", "Close": "last",
            }).dropna()
            ftfc_in = {"1d": df_dt[["Open", "High", "Low", "Close"]]}
            if len(weekly) >= 2:
                ftfc_in["1w"] = weekly
            ftfc_score, ftfc_dir, _ = clf.calculate_ftfc(
                ftfc_in, weights={"1d": 0.7, "1w": 0.3},
            )
            if last_candle and last_candle != "X":
                row["strat_candle"] = str(last_candle)
            if last_combo:
                row["strat_combo"] = str(last_combo)[:30]
            row["ftfc_score"] = float(ftfc_score) if ftfc_score is not None else 0.0
            row["ftfc_direction"] = str(ftfc_dir or "mixed")[:10]
            row["strat_setup"] = bool(last_combo and abs(ftfc_score or 0.0) >= 0.3)
        except Exception as exc:
            log.warning("strat compute failed for %s @ %s: %s", ticker, fd, exc)

        # Pre-market context from intraday bars
        try:
            ibars = query_to_dataframe(
                "SELECT ts, open, high, low, close, volume "
                "FROM market_data_intraday "
                "WHERE ticker = :ticker "
                "  AND ts >= CAST(:fd AS DATE) "
                "  AND ts <  CAST(:fd AS DATE) + INTERVAL '1 day' "
                "ORDER BY ts",
                {"ticker": ticker.upper(), "fd": str(fd)},
            )
            if not ibars.empty:
                prev_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else None
                atr14 = float(last.get("ATR14")) if last.get("ATR14") is not None else None
                pm = calculate_premarket_context(
                    times=ibars["ts"], open_=ibars["open"], high=ibars["high"],
                    low=ibars["low"], close=ibars["close"], volume=ibars["volume"],
                    prev_close=prev_close, atr14=atr14,
                )
                if pm["bar_count"] > 0:
                    for k_pm, k_db in [
                        ("pre_high", "pre_high"), ("pre_low", "pre_low"),
                        ("pre_vwap", "pre_vwap"), ("pre_volume", "pre_volume"),
                        ("gap_pct", "gap_pct"),
                        ("pre_range_atr", "pre_range_atr"),
                    ]:
                        if pm[k_pm] is not None:
                            row[k_db] = pm[k_pm]
                    log.info("  ✓ pre-market %s @ %s: pre_high=%s gap=%s",
                             ticker, fd, pm["pre_high"], pm["gap_pct"])
        except Exception as exc:
            log.warning("pre-market compute failed for %s @ %s: %s", ticker, fd, exc)

        upsert_dataframe(pd.DataFrame([row]),
                         "market_data_daily", ["ticker", "date"])
        log.info("✓ indicators+strat %s @ %s", ticker, fd)


# ──────────────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────────────
def run() -> int:
    ticker = (_env("BACKFILL_TICKER") or "").upper()
    if not ticker:
        log.error("BACKFILL_TICKER is required")
        return 1

    api_key = _env("ALPHA_VANTAGE_API_KEY") or _env("AV_API_KEY")
    if not api_key:
        log.error("ALPHA_VANTAGE_API_KEY is required")
        return 1

    history_days = int(_env("BACKFILL_HISTORY_DAYS", "250"))
    include_news = (_env("BACKFILL_INCLUDE_NEWS", "true") or "true").lower() == "true"
    news_window = int(_env("BACKFILL_NEWS_WINDOW", "7"))
    dates = _parse_dates(_env("BACKFILL_DATES"))

    log.info("backfill ticker=%s dates=%s history=%dd news=%s",
             ticker, dates, history_days, include_news)

    from gcp.database import upsert_dataframe

    # 1. Daily history
    daily = av_daily_full(ticker, api_key)
    keep = daily.tail(history_days).copy()
    daily_rows = [
        {"ticker": ticker, "date": r["date"],
         "open": r["open"], "high": r["high"], "low": r["low"],
         "close": r["close"], "adjusted_close": r["adjusted_close"],
         "volume": int(r["volume"]), "data_source": "alphavantage"}
        for _, r in keep.iterrows()
    ]
    upsert_dataframe(pd.DataFrame(daily_rows),
                     "market_data_daily", ["ticker", "date"])
    log.info("✓ wrote %d daily rows for %s", len(daily_rows), ticker)

    # 2. Intraday for every month touched by any requested date + its prior
    months: set[str] = set()
    for d in dates:
        months.add(d.strftime("%Y-%m"))
        prior = d - timedelta(days=4)  # crosses weekend
        months.add(prior.strftime("%Y-%m"))
    for m in sorted(months):
        intraday = av_intraday_month(ticker, m, api_key)
        if not intraday.empty:
            ir_rows = [{
                "ticker": ticker, "interval": "1min",
                "ts": ts.to_pydatetime(),
                "open": float(r["Open"]), "high": float(r["High"]),
                "low": float(r["Low"]), "close": float(r["Close"]),
                "volume": int(r["Volume"]),
                "data_source": "alphavantage",
            } for ts, r in intraday.iterrows()]
            upsert_dataframe(pd.DataFrame(ir_rows),
                             "market_data_intraday",
                             ["ticker", "interval", "ts"])
            log.info("✓ wrote %d intraday bars for %s month=%s",
                     len(ir_rows), ticker, m)

    # 3. News (optional)
    if include_news and dates:
        first = min(dates) - timedelta(days=news_window)
        last = max(dates) + timedelta(days=1)
        feed = av_news(ticker, first.strftime("%Y%m%dT0000"),
                       last.strftime("%Y%m%dT2359"), api_key)
        rows = av_news_to_rows(feed)
        if rows:
            upsert_dataframe(pd.DataFrame(rows), "news_sentiment",
                             ["ticker", "published_ts", "url"])
            log.info("✓ wrote %d news rows", len(rows))

    # 4a. Multi-day indicators for the FULL backfilled range. Without
    #     this only the BACKFILL_DATES rows below get indicators, and
    #     downstream queries (ATR around historical earnings, RSI on
    #     a 6-month chart, etc.) hit NULLs even though OHLC is loaded.
    compute_indicators_for_full_range(ticker)

    # 4b. Strat fields + pre-market context for each target date and
    #     its prior trading day (needs intraday bars per date — that's
    #     why this stays per-date, while 4a is a single full pass).
    target = set(dates)
    for d in dates:
        prior = d - timedelta(days=1)
        while prior.weekday() >= 5:
            prior -= timedelta(days=1)
        target.add(prior)
    compute_indicators_for_dates(ticker, sorted(target))

    # 5. Watchlist
    add_to_watchlist(ticker)

    log.info("backfill complete for %s", ticker)
    return 0


def main() -> None:
    code = run()
    sys.exit(code)


if __name__ == "__main__":
    main()
