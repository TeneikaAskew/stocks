"""
Comprehensive backfill + replay for historical brief/insight testing.

Use this when you need to ask "would our system have caught the move on
ticker X on date D?" — e.g. AMD 4/24 gap-up, CARS 3/31 catalyst, ARM
multi-day setup. The script handles every dependency the AI insight
pipeline needs:

    1. AV TIME_SERIES_DAILY_ADJUSTED (full history, ~250d back)
       → market_data_daily (OHLCV + adjusted close)
    2. AV TIME_SERIES_INTRADAY (1-min, full month, extended hours included)
       → market_data_intraday  (4 AM-9:30 AM ET pre-market bars)
    3. AV NEWS_SENTIMENT (topic-tagged articles)
       → news_sentiment       (sentiment_score per (article, ticker))
    4. lib.indicators.add_all_indicators + calculate_premarket_context
       → daily indicators + pre_high/pre_low/pre_vwap/gap_pct/pre_range_atr
    5. lib.strat.compute_strat_status → ftfc_score + strat_candle/combo
    6. (optional) Cloud Run insight-pipeline job execution at as_of=09:15 ET
       → 8-agent LLM analyst run with pre-market context block
    7. (optional) Cloud Run insight-discord-push for review notification

Usage:
    # Single ticker, one date, full pipeline (fetch + indicators + LLM)
    python -m scripts.backfill_and_replay --ticker AMD --dates 2026-04-24

    # Multiple dates, with news, no Discord push
    python -m scripts.backfill_and_replay --ticker ARM \\
        --dates 2026-04-20,2026-04-21,2026-04-22,2026-04-23 \\
        --include-news --skip-discord

    # Skip data fetch (already backfilled), just rerun the LLM
    python -m scripts.backfill_and_replay --ticker CARS \\
        --dates 2026-03-31 --skip-backfill

    # Skip the LLM (just data backfill, no Cloud Run cost)
    python -m scripts.backfill_and_replay --ticker AMD \\
        --dates 2026-04-23,2026-04-24 --skip-replay

Requirements:
    * Run locally with the user's IP whitelisted on Cloud SQL (104.8.79.228/32)
    * gcloud CLI authenticated for the project (insight-pipeline job exec)
    * AV API key in Secret Manager as `av-api-key`
    * DB user/pass in Secret Manager as `db-trading-user` / `db-trading-pass`
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras
import requests

# Make `lib.*` importable when invoked as a script from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.indicators import add_all_indicators, calculate_premarket_context  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
log = logging.getLogger('backfill_and_replay')


# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────
GCLOUD = r'C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
PROJECT = 'adept-mountain-474619-d4'
REGION = 'us-east1'
DB_HOST = '34.24.66.12'
DB_NAME = 'trading'
AV_BASE = 'https://www.alphavantage.co/query'

DAILY_HISTORY_DAYS = 250


# ──────────────────────────────────────────────────────────────────────
# Secrets + DB
# ──────────────────────────────────────────────────────────────────────
def secret(name: str) -> str:
    return subprocess.check_output(
        [GCLOUD, 'secrets', 'versions', 'access', 'latest',
         f'--secret={name}', f'--project={PROJECT}'],
        text=True,
    ).rstrip('\n')


def db_connect():
    return psycopg2.connect(
        host=DB_HOST,
        user=secret('db-trading-user'),
        password=secret('db-trading-pass'),
        dbname=DB_NAME,
        sslmode='require',
    )


def upsert_rows(conn, table: str, rows: list[dict], conflict_cols: list[str]):
    """Bulk upsert with ON CONFLICT DO UPDATE.

    Filters DataFrame columns to only those present in the target table
    (matching `gcp.database.upsert_dataframe` semantics so callers don't
    need to know the schema).
    """
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s",
            (table,),
        )
        valid_cols = {r[0] for r in cur.fetchall()}

    # Filter every row to valid columns
    filtered = []
    dropped: set[str] = set()
    for r in rows:
        kept = {k: v for k, v in r.items() if k in valid_cols}
        dropped.update(set(r.keys()) - set(kept.keys()))
        filtered.append(kept)
    if dropped:
        log.warning("upsert(%s): dropped columns not in schema: %s", table, sorted(dropped))

    if not filtered:
        return 0
    cols = sorted({c for r in filtered for c in r.keys()})
    insert_cols = ', '.join(cols)
    placeholders = ', '.join(['%s'] * len(cols))
    update_set = ', '.join(
        f'{c} = EXCLUDED.{c}' for c in cols if c not in conflict_cols
    )
    conflict_target = ', '.join(conflict_cols)
    if update_set:
        sql = (f'INSERT INTO {table} ({insert_cols}) VALUES ({placeholders}) '
               f'ON CONFLICT ({conflict_target}) DO UPDATE SET {update_set}')
    else:
        sql = (f'INSERT INTO {table} ({insert_cols}) VALUES ({placeholders}) '
               f'ON CONFLICT ({conflict_target}) DO NOTHING')
    values = [tuple(r.get(c) for c in cols) for r in filtered]
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, sql, values, page_size=500)
    conn.commit()
    return len(filtered)


# ──────────────────────────────────────────────────────────────────────
# AlphaVantage — data fetch
# ──────────────────────────────────────────────────────────────────────
def av_daily_full(ticker: str, api_key: str) -> pd.DataFrame:
    """Pull entire daily history (split/dividend-adjusted)."""
    log.info("AV daily-full %s", ticker)
    r = requests.get(AV_BASE, params={
        'function': 'TIME_SERIES_DAILY_ADJUSTED',
        'symbol': ticker,
        'outputsize': 'full',
        'datatype': 'json',
        'apikey': api_key,
    }, timeout=60)
    r.raise_for_status()
    data = r.json()
    if 'Error Message' in data or 'Information' in data or 'Note' in data:
        msg = data.get('Error Message') or data.get('Information') or data.get('Note')
        raise RuntimeError(f"AV daily {ticker}: {msg}")
    ts = data.get('Time Series (Daily)') or {}
    if not ts:
        raise RuntimeError(f"AV daily {ticker}: empty time series")
    rows = []
    for d, v in ts.items():
        rows.append({
            'date': pd.to_datetime(d).date(),
            'open': float(v['1. open']),
            'high': float(v['2. high']),
            'low':  float(v['3. low']),
            'close': float(v['4. close']),
            'adjusted_close': float(v['5. adjusted close']),
            'volume': int(v['6. volume']),
        })
    df = pd.DataFrame(rows).sort_values('date').reset_index(drop=True)
    log.info("  → %d daily rows (%s … %s)", len(df), df['date'].iloc[0], df['date'].iloc[-1])
    return df


def av_intraday_month(ticker: str, year_month: str, api_key: str) -> pd.DataFrame:
    """Pull entire month of 1-min bars (extended hours included by default)."""
    log.info("AV intraday-month %s %s", ticker, year_month)
    r = requests.get(AV_BASE, params={
        'function': 'TIME_SERIES_INTRADAY',
        'symbol': ticker,
        'interval': '1min',
        'month': year_month,
        'outputsize': 'full',
        'adjusted': 'true',
        'extended_hours': 'true',
        'entitlement': 'realtime',
        'apikey': api_key,
        'datatype': 'json',
    }, timeout=120)
    r.raise_for_status()
    data = r.json()
    if 'Error Message' in data or 'Information' in data or 'Note' in data:
        msg = data.get('Error Message') or data.get('Information') or data.get('Note')
        raise RuntimeError(f"AV intraday {ticker} {year_month}: {msg}")
    ts = data.get('Time Series (1min)') or {}
    if not ts:
        log.warning("  AV intraday: empty for %s %s", ticker, year_month)
        return pd.DataFrame()
    df = pd.DataFrame.from_dict(ts, orient='index')
    df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    for c in ['Open', 'High', 'Low', 'Close']:
        df[c] = pd.to_numeric(df[c])
    df['Volume'] = pd.to_numeric(df['Volume']).astype('int64')
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    log.info("  → %d bars (%s … %s)", len(df), df.index[0], df.index[-1])
    return df


def av_news(ticker: str, time_from: str, time_to: str,
            api_key: str, limit: int = 1000) -> list[dict]:
    """Pull NEWS_SENTIMENT for ticker over [time_from, time_to] (UTC)."""
    log.info("AV news %s [%s → %s]", ticker, time_from, time_to)
    r = requests.get(AV_BASE, params={
        'function': 'NEWS_SENTIMENT',
        'tickers': ticker,
        'time_from': time_from,
        'time_to': time_to,
        'sort': 'EARLIEST',
        'limit': limit,
        'apikey': api_key,
    }, timeout=60)
    r.raise_for_status()
    data = r.json()
    if 'Information' in data:
        log.warning("  AV news rate limit/info: %s", data['Information'])
    feed = data.get('feed') or []
    log.info("  → %d articles", len(feed))
    return feed


def av_news_to_rows(feed: list[dict], focus_ticker: str) -> list[dict]:
    """Explode AV news feed into one row per (article, ticker)."""
    rows = []
    for art in feed:
        pub_raw = art.get('time_published') or ''
        try:
            pub_ts = datetime.strptime(pub_raw[:15], '%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc)
        except Exception:
            continue
        title = (art.get('title') or '')[:500] or None
        url = (art.get('url') or '')[:1000] or None
        summary = (art.get('summary') or '')[:2000] or None
        source = (art.get('source') or '')[:100] or None
        overall_score = _safe_float(art.get('overall_sentiment_score'))
        overall_label = (art.get('overall_sentiment_label') or '')[:20] or None
        topics = [t['topic'] for t in (art.get('topics') or [])
                  if isinstance(t, dict) and t.get('topic')]
        for tk_entry in (art.get('ticker_sentiment') or []):
            tk = (tk_entry.get('ticker') or '').upper().strip()
            if not tk:
                continue
            rows.append({
                'ticker': tk,
                'published_ts': pub_ts,
                'title': title,
                'url': url,
                'summary': summary,
                'sentiment_score': _safe_float(tk_entry.get('ticker_sentiment_score')),
                'relevance_score': _safe_float(tk_entry.get('relevance_score')),
                'overall_sentiment_score': overall_score,
                'overall_sentiment_label': overall_label,
                'topics': topics or None,
                'source': source,
                'data_source': 'alphavantage',
                'match_method': 'av_ticker_sentiment',
            })
    return rows


def _safe_float(x) -> float | None:
    if x is None or x == '' or x == 'None':
        return None
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


# ──────────────────────────────────────────────────────────────────────
# Persistence + indicator computation
# ──────────────────────────────────────────────────────────────────────
def write_daily_history(conn, ticker: str, df: pd.DataFrame, days: int):
    """Upsert the last `days` daily rows."""
    if df.empty:
        return
    keep = df.tail(days).copy()
    rows = []
    for _, r in keep.iterrows():
        rows.append({
            'ticker': ticker,
            'date': r['date'],
            'open': r['open'],
            'high': r['high'],
            'low': r['low'],
            'close': r['close'],
            'adjusted_close': r['adjusted_close'],
            'volume': int(r['volume']),
            'data_source': 'alphavantage',
        })
    n = upsert_rows(conn, 'market_data_daily', rows, ['ticker', 'date'])
    log.info("  ✓ wrote %d daily rows for %s", n, ticker)


def write_intraday_bars(conn, ticker: str, intraday: pd.DataFrame,
                        only_dates: set[date] | None = None):
    """Upsert 1-min bars; optionally filter to specific dates."""
    if intraday.empty:
        return
    df = intraday.copy()
    if only_dates is not None:
        df = df[df.index.normalize().isin(pd.to_datetime(list(only_dates)))]
    if df.empty:
        return
    rows = []
    for ts, r in df.iterrows():
        rows.append({
            'ticker': ticker,
            'interval': '1min',
            'ts': ts.to_pydatetime(),
            'open': float(r['Open']),
            'high': float(r['High']),
            'low': float(r['Low']),
            'close': float(r['Close']),
            'volume': int(r['Volume']),
            'data_source': 'alphavantage',
        })
    n = upsert_rows(conn, 'market_data_intraday', rows, ['ticker', 'interval', 'ts'])
    log.info("  ✓ wrote %d intraday bars for %s", n, ticker)


def compute_daily_indicators_for_ticker(conn, ticker: str, target_dates: list[date]):
    """For each `target_date` recompute multi-day indicators + pre-market context.

    Reads the last 250 daily bars + that date's intraday bars from Cloud SQL
    so the result is identical to what the live `fetch-market-data` job
    would have produced on that date.
    """
    from lib.strat import StratClassifier
    clf = StratClassifier()

    for fd in sorted(target_dates):
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT date, open AS "Open", high AS "High",
                          low AS "Low", close AS "Close", volume AS "Volume"
                     FROM market_data_daily
                    WHERE ticker = %s AND date <= %s
                    ORDER BY date DESC
                    LIMIT 250""",
                (ticker, fd),
            )
            rows = cur.fetchall()
        if len(rows) < 2:
            log.warning("  insufficient daily history for %s @ %s (%d bars)",
                        ticker, fd, len(rows))
            continue
        df = pd.DataFrame(rows).iloc[::-1].reset_index(drop=True)
        enriched = add_all_indicators(df, close_col='Close')
        enriched['volatility_20d'] = (
            enriched['Close'].pct_change().rolling(20).std() * np.sqrt(252)
        )
        last = enriched.iloc[-1]

        # Map enriched indicator names → Cloud SQL columns (same map as
        # gcp/fetchers/fetch_market_data.py:_DAILY_IND_TO_SQL).
        ind_map = {
            'MA5': 'ma_5', 'MA10': 'ma_10', 'MA20': 'ma_20', 'MA50': 'ma_50',
            'EMA9': 'ema_9', 'EMA20': 'ema_20', 'EMA50': 'ema_50',
            'SMA200': 'sma_200',
            'RSI': 'rsi_14', 'RSI9': 'rsi_9', 'RSI30': 'rsi_30',
            'StochRSI_K': 'stoch_rsi_k', 'StochRSI_D': 'stoch_rsi_d',
            'ATR14': 'atr_14', 'ATR20': 'atr_20',
            'OBV': 'obv',
            'RVOL': 'rvol', 'RVOL10': 'rvol_10',
            'Volume_MA10': 'volume_ma_10', 'Volume_MA20': 'volume_ma_20',
            'Volume_USD': 'volume_usd',
            'MACD': 'macd', 'MACD_Signal': 'macd_signal', 'MACD_Histogram': 'macd_histogram',
            'BB_Upper': 'bb_upper', 'BB_Lower': 'bb_lower',
            'BB_Width': 'bb_width', 'BB_Pct': 'bb_pct',
            'Return': 'return',
            'volatility_5d': 'volatility_5d',
            'volatility_20d': 'volatility_20d',
            'high_low_spread': 'high_low_spread',
            'high_low_spread_pct': 'high_low_spread_pct',
            'consecutive_up': 'consecutive_up',
            'consecutive_down': 'consecutive_down',
            'VWAP': 'vwap',
            'Price_vs_VWAP': 'price_vs_vwap',
            'Price_vs_EMA9': 'price_vs_ema9',
            'Price_vs_EMA20': 'price_vs_ema20',
        }
        int_cols = {'consecutive_up', 'consecutive_down'}
        row: dict = {'ticker': ticker, 'date': fd}
        for src, dst in ind_map.items():
            v = last.get(src)
            if v is not None and pd.notna(v):
                row[dst] = int(v) if dst in int_cols else float(v)

        # Strat fields (same recipe as fetch_market_data.compute_and_upsert_daily_indicators)
        try:
            ohlc = enriched[['Open', 'High', 'Low', 'Close']]
            labels = clf.classify_series(ohlc)
            last_candle = labels.iloc[-1]
            combos = clf.detect_combos(ohlc, labels)
            last_combo = None
            if not combos.empty:
                last_combo = combos.iloc[-1].get('combo')
            df_dt = enriched.copy()
            df_dt['date'] = df['date'].values
            df_dt = df_dt.set_index(pd.to_datetime(df_dt['date']))
            weekly = df_dt[['Open', 'High', 'Low', 'Close']].resample('W').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last',
            }).dropna()
            ftfc_in = {'1d': df_dt[['Open', 'High', 'Low', 'Close']]}
            if len(weekly) >= 2:
                ftfc_in['1w'] = weekly
            ftfc_score, ftfc_dir, _ = clf.calculate_ftfc(
                ftfc_in, weights={'1d': 0.7, '1w': 0.3},
            )
            if last_candle and last_candle != 'X':
                row['strat_candle'] = str(last_candle)
            if last_combo:
                row['strat_combo'] = str(last_combo)[:30]
            row['ftfc_score'] = float(ftfc_score) if ftfc_score is not None else 0.0
            row['ftfc_direction'] = str(ftfc_dir or 'mixed')[:10]
            row['strat_setup'] = bool(last_combo and abs(ftfc_score or 0.0) >= 0.3)
        except Exception as e:
            log.warning("  strat compute failed for %s @ %s: %s", ticker, fd, e)

        # Pre-market context from intraday bars
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT ts, open, high, low, close, volume
                         FROM market_data_intraday
                        WHERE ticker = %s
                          AND ts >= %s::date
                          AND ts <  %s::date + INTERVAL '1 day'
                        ORDER BY ts""",
                    (ticker, fd, fd),
                )
                ibars = cur.fetchall()
            if ibars:
                idf = pd.DataFrame(ibars)
                prev_close = float(df['Close'].iloc[-2]) if len(df) >= 2 else None
                atr14 = float(last.get('ATR14')) if last.get('ATR14') is not None else None
                pm = calculate_premarket_context(
                    times=idf['ts'], open_=idf['open'], high=idf['high'],
                    low=idf['low'], close=idf['close'], volume=idf['volume'],
                    prev_close=prev_close, atr14=atr14,
                )
                if pm['bar_count'] > 0:
                    if pm['pre_high'] is not None: row['pre_high'] = pm['pre_high']
                    if pm['pre_low'] is not None: row['pre_low'] = pm['pre_low']
                    if pm['pre_vwap'] is not None: row['pre_vwap'] = pm['pre_vwap']
                    if pm['pre_volume'] is not None: row['pre_volume'] = pm['pre_volume']
                    if pm['gap_pct'] is not None: row['gap_pct'] = pm['gap_pct']
                    if pm['pre_range_atr'] is not None: row['pre_range_atr'] = pm['pre_range_atr']
                    log.info("  ✓ premarket %s @ %s: pre_high=%s pre_low=%s gap=%s",
                             ticker, fd, pm['pre_high'], pm['pre_low'], pm['gap_pct'])
        except Exception as e:
            log.warning("  pre-market compute failed for %s @ %s: %s", ticker, fd, e)

        upsert_rows(conn, 'market_data_daily', [row], ['ticker', 'date'])
        log.info("  ✓ indicators+strat persisted %s @ %s", ticker, fd)


# ──────────────────────────────────────────────────────────────────────
# Cloud Run job triggers (insight-pipeline replay)
# ──────────────────────────────────────────────────────────────────────
def trigger_insight_pipeline(ticker: str, as_of_iso_utc: str, wait: bool = True):
    """Execute the insight-pipeline Cloud Run Job for one (ticker, as_of) pair."""
    log.info("Cloud Run insight-pipeline → %s as_of=%s", ticker, as_of_iso_utc)
    cmd = [
        GCLOUD, 'run', 'jobs', 'execute', 'insight-pipeline',
        f'--region={REGION}', f'--project={PROJECT}',
        '--update-env-vars', f'INSIGHT_TICKERS={ticker},INSIGHT_AS_OF={as_of_iso_utc}',
    ]
    if wait:
        cmd.append('--wait')
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log.error("  insight-pipeline failed: %s", proc.stderr.strip()[-500:])
    else:
        log.info("  ✓ insight-pipeline complete")


def trigger_discord_push(ticker: str, push_date: str, wait: bool = True):
    log.info("Cloud Run insight-discord-push → %s date=%s", ticker, push_date)
    cmd = [
        GCLOUD, 'run', 'jobs', 'execute', 'insight-discord-push',
        f'--region={REGION}', f'--project={PROJECT}',
        '--update-env-vars', f'INSIGHT_PUSH_TICKER={ticker},INSIGHT_PUSH_DATE={push_date}',
    ]
    if wait:
        cmd.append('--wait')
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log.error("  discord-push failed: %s", proc.stderr.strip()[-500:])
    else:
        log.info("  ✓ discord-push complete")


# ──────────────────────────────────────────────────────────────────────
# Reporting — comparison
# ──────────────────────────────────────────────────────────────────────
def report_comparison(conn, ticker: str, dates: list[date]):
    """Print a side-by-side: insight zone vs actual session H/L vs pre-market."""
    print()
    print('=' * 92)
    print(f'  {ticker}  --  insight vs actual')
    print('=' * 92)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        for d in dates:
            cur.execute(
                """SELECT open, high, low, close, pre_high, pre_low,
                          pre_vwap, gap_pct, ftfc_score, ftfc_direction
                     FROM market_data_daily
                    WHERE ticker=%s AND date=%s""",
                (ticker, d),
            )
            row = cur.fetchone()
            cur.execute(
                """SELECT as_of, report
                     FROM insight_reports
                    WHERE ticker=%s AND as_of::date=%s
                    ORDER BY as_of DESC LIMIT 1""",
                (ticker, d),
            )
            ins = cur.fetchone()
            print(f'\n  {d} -- actual session: O={_fmt(row, "open")} H={_fmt(row, "high")} '
                  f'L={_fmt(row, "low")} C={_fmt(row, "close")}')
            print(f'    pre-market: pre_H={_fmt(row, "pre_high")} pre_L={_fmt(row, "pre_low")} '
                  f'pre_VWAP={_fmt(row, "pre_vwap")} gap={_pct(row, "gap_pct")}')
            print(f'    FTFC: score={_fmt(row, "ftfc_score")} dir={row.get("ftfc_direction") if row else "-"}')
            if ins:
                rep = ins['report'] if isinstance(ins['report'], dict) else json.loads(ins['report'])
                ez = rep.get('entry_zone') or {}
                print(f'    insight @ {ins["as_of"]} -> {rep.get("direction"):>5} '
                      f'({rep.get("conviction")}) entry=${ez.get("low")}-${ez.get("high")} '
                      f'stop=${rep.get("stop")} targets={rep.get("targets")}')
                # Reachability check
                if row and row.get('low') is not None and row.get('high') is not None:
                    if ez.get('low') is not None and ez.get('high') is not None:
                        reached = (row['low'] <= ez['high'] and row['high'] >= ez['low'])
                        print(f'    entry reached during RTH? {"YES" if reached else "NO"}')
            else:
                print('    insight: (none)')
    print('=' * 92)


def _fmt(row: dict | None, key: str) -> str:
    if not row or row.get(key) is None:
        return '-'
    return f'{row[key]:.2f}'


def _pct(row: dict | None, key: str) -> str:
    """Format a value already stored as a percent (1.62 = 1.62%)."""
    if not row or row.get(key) is None:
        return '-'
    return f'{row[key]:+.2f}%'


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--ticker', required=True,
                   help='Ticker symbol (e.g. AMD, CARS, ARM)')
    p.add_argument('--dates', required=True,
                   help='Comma-separated YYYY-MM-DD dates to replay')
    p.add_argument('--history-days', type=int, default=DAILY_HISTORY_DAYS,
                   help=f'Daily-history depth (default {DAILY_HISTORY_DAYS}d)')
    p.add_argument('--include-news', action='store_true',
                   help='Also fetch AV NEWS_SENTIMENT for the ticker')
    p.add_argument('--news-window-days', type=int, default=7,
                   help='News lookback window in days (default 7)')
    p.add_argument('--insight-time-et', default='09:15',
                   help='ET time-of-day for insight as_of (default 09:15)')
    p.add_argument('--skip-backfill', action='store_true',
                   help='Skip AV fetches + indicator compute (use existing DB state)')
    p.add_argument('--skip-replay', action='store_true',
                   help='Only backfill data; do not trigger insight-pipeline runs')
    p.add_argument('--skip-discord', action='store_true',
                   help='Skip Discord push after insight runs (default: push)')
    args = p.parse_args()

    ticker = args.ticker.upper()
    dates = [pd.to_datetime(d.strip()).date() for d in args.dates.split(',') if d.strip()]
    if not dates:
        sys.exit('--dates required')

    log.info('Backfill+replay: ticker=%s dates=%s history=%dd', ticker, dates, args.history_days)

    conn = db_connect()
    try:
        if not args.skip_backfill:
            api_key = secret('av-api-key')

            # 1. Daily history
            daily = av_daily_full(ticker, api_key)
            write_daily_history(conn, ticker, daily, args.history_days)

            # 2. Intraday for every month covered by dates AND prior trading day
            #    (prior day matters for prev_close / gap_pct calc).
            months: set[str] = set()
            for d in dates:
                months.add(d.strftime('%Y-%m'))
                prior = d - timedelta(days=4)  # crosses weekend
                months.add(prior.strftime('%Y-%m'))
            for m in sorted(months):
                intraday = av_intraday_month(ticker, m, api_key)
                if not intraday.empty:
                    write_intraday_bars(conn, ticker, intraday)

            # 3. News (optional)
            if args.include_news:
                first = min(dates) - timedelta(days=args.news_window_days)
                last = max(dates) + timedelta(days=1)
                tf = first.strftime('%Y%m%dT0000')
                tt = last.strftime('%Y%m%dT2359')
                feed = av_news(ticker, tf, tt, api_key)
                rows = av_news_to_rows(feed, ticker)
                if rows:
                    n = upsert_rows(conn, 'news_sentiment', rows,
                                    ['ticker', 'published_ts', 'url'])
                    log.info("  ✓ wrote %d news rows", n)

            # 4. Compute daily indicators + pre-market context
            #    (run for every date in dates AND the prior trading day so
            #    the LLM's prev_close reference is correct)
            target_dates = set(dates)
            for d in dates:
                # rough prior trading day
                prior = d - timedelta(days=1)
                while prior.weekday() >= 5:
                    prior -= timedelta(days=1)
                target_dates.add(prior)
            compute_daily_indicators_for_ticker(conn, ticker, sorted(target_dates))

        # 5. Replay LLM insight pipeline
        if not args.skip_replay:
            hh, mm = args.insight_time_et.split(':')
            for d in dates:
                # ET → UTC. ET is UTC-4 in DST (EDT, Mar-Nov), UTC-5 otherwise.
                # Approximation: ET timestamps in 4 AM-9 AM range stored as
                # naive ET-as-UTC by AV; for insight as_of we want UTC ISO.
                # 09:15 ET = 13:15 UTC during DST.
                as_of = datetime(d.year, d.month, d.day, int(hh) + 4, int(mm),
                                 tzinfo=timezone.utc)
                trigger_insight_pipeline(ticker, as_of.strftime('%Y-%m-%dT%H:%M:%SZ'))
                if not args.skip_discord:
                    trigger_discord_push(ticker, d.strftime('%Y-%m-%d'))

        # 6. Side-by-side report
        report_comparison(conn, ticker, dates)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
