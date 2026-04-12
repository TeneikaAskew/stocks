#!/usr/bin/env python3
"""
Pre-market brief -- Cloud Run Job triggered by Cloud Scheduler at 8:30 AM ET.

Loads latest daily data from Cloud SQL, computes Strat/FTFC classifications,
queries upcoming economic events, and sends a rich multi-embed Discord brief.
Also persists per-ticker analysis to the premarket_analysis table.
"""

import os
import sys
import json
import logging
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, date, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.data_loader import DataLoader
from lib.indicators import add_all_indicators
from lib.strat import StratClassifier
from lib.signals import check_call_conditions, check_put_conditions
from lib.config import load_config

logger = logging.getLogger(__name__)

# Discord embed limits
MAX_EMBED_CHARS = 6000
MAX_FIELD_VALUE = 1024


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_float(val, default=None):
    """Extract a float from a pandas value, returning default if NaN/None."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if pd.isna(f) else f
    except (TypeError, ValueError):
        return default


def _vol_regime(vol_20d):
    """Classify annualized 20-day volatility into a regime label."""
    if vol_20d is None:
        return 'N/A'
    v = vol_20d * 100 if vol_20d < 1 else vol_20d  # handle both decimal and pct
    if v < 12:
        return 'Low'
    if v < 20:
        return 'Normal'
    if v < 30:
        return 'High'
    return 'Extreme'


def _macd_cross(macd, macd_signal):
    """Return 'Bullish' or 'Bearish' based on MACD vs signal line."""
    if macd is None or macd_signal is None:
        return 'N/A'
    return 'Bullish' if macd > macd_signal else 'Bearish'


# ── Earnings Calendar ───────────────────────────────────────────────────────

def load_earnings_for_brief(today: date, weekly: bool = False) -> dict:
    """Query earnings_calendar for the premarket brief.

    On weekdays (weekly=False): returns today's earnings only.
    On Sundays (weekly=True):   returns the upcoming Mon-Fri earnings.

    Priority within a (ticker, date) pair: earnings_whispers > alphavantage > unusual_whales.
    EW rows carry strategy picks which are the most actionable for trading.
    """
    try:
        from gcp.database import is_cloud_sql_configured, query_to_dataframe
    except ImportError:
        return {'mode': 'daily', 'earnings': []}

    if not is_cloud_sql_configured():
        return {'mode': 'daily', 'earnings': []}

    if weekly:
        # Sunday → next Mon through Fri
        days_until_monday = (7 - today.weekday()) % 7 or 7
        start = today + timedelta(days=days_until_monday)
        end = start + timedelta(days=4)  # Mon..Fri
        mode = 'weekly'
    else:
        start = end = today
        mode = 'daily'

    sql = """
        SELECT DISTINCT ON (ticker, earnings_date)
               ticker, earnings_date, company_name, earnings_time,
               eps_estimate, expected_move, sector,
               strategy, strike, premium, score, data_source
        FROM earnings_calendar
        WHERE earnings_date BETWEEN :start AND :end
        ORDER BY ticker, earnings_date,
                 CASE data_source
                     WHEN 'earnings_whispers' THEN 1
                     WHEN 'alphavantage'      THEN 2
                     WHEN 'unusual_whales'    THEN 3
                     ELSE 4
                 END
    """
    df = query_to_dataframe(sql, {'start': start, 'end': end})

    earnings = []
    for _, row in df.iterrows():
        earnings.append({
            'ticker': row['ticker'],
            'date': row['earnings_date'],
            'company_name': row.get('company_name') or '',
            'time': row.get('earnings_time') or 'unknown',
            'eps_estimate': row.get('eps_estimate'),
            'expected_move': row.get('expected_move'),
            'sector': row.get('sector') or '',
            'strategy': row.get('strategy') or '',
            'strike': row.get('strike'),
            'premium': row.get('premium'),
            'score': row.get('score'),
            'source': row.get('data_source'),
        })

    return {'mode': mode, 'start': start, 'end': end, 'earnings': earnings}


# ── Economic Events ─────────────────────────────────────────────────────────

def load_economic_events(today: date, days_ahead: int = 5) -> dict:
    """Query economic_events from Cloud SQL for today and upcoming days."""
    try:
        from gcp.database import is_cloud_sql_configured, query_to_dataframe
    except ImportError:
        return {'today': [], 'week': []}

    if not is_cloud_sql_configured():
        return {'today': [], 'week': []}

    end_date = today + timedelta(days=days_ahead)
    sql = """
        SELECT event_date, event_time, event_name, importance, actual, forecast, previous
        FROM economic_events
        WHERE event_date BETWEEN :start AND :end
          AND importance IN ('high', 'medium')
        ORDER BY event_date, importance DESC, event_time
    """
    df = query_to_dataframe(sql, {'start': today, 'end': end_date})

    today_events, week_events = [], []
    for _, row in df.iterrows():
        ev = {
            'date': row['event_date'],
            'time': str(row['event_time'])[:5] if row.get('event_time') else '',
            'name': row['event_name'],
            'importance': row['importance'],
            'forecast': row.get('forecast') or '',
            'previous': row.get('previous') or '',
        }
        if row['event_date'] == today:
            today_events.append(ev)
        else:
            week_events.append(ev)

    return {'today': today_events, 'week': week_events}


# ── Brief Generation ────────────────────────────────────────────────────────

def generate_premarket_brief(cfg=None, data_dir: str = None) -> dict:
    """Generate pre-market brief for all tickers.

    Returns a dict with per-ticker analysis and economic events.
    """
    if cfg is None:
        cfg = load_config()

    data_dir = data_dir or cfg.market.data_dir
    tickers = cfg.market.tickers
    signal_threshold = cfg.signal.premarket_signal_threshold
    building_threshold = cfg.signal.premarket_building_threshold

    loader = DataLoader(data_dir=data_dir)
    strat = StratClassifier(strat_config=cfg.strat)
    brief = {'date': datetime.now().strftime('%a %b %d, %Y'), 'tickers': {}}

    for ticker in tickers:
        df = loader.load_daily(ticker)
        if df.empty or len(df) < 2:
            brief['tickers'][ticker] = {'status': 'NO DATA'}
            continue

        close_col = 'Close' if 'Close' in df.columns else 'Last'
        df = add_all_indicators(df, close_col=close_col)

        latest = df.iloc[-1]       # yesterday (most recent trading day)
        prior = df.iloc[-2]        # day before yesterday
        rsi = latest.get(cfg.indicator.rsi_col, 50)

        # ── Previous day context ────────────────────────────────────────
        prev_close = _safe_float(prior.get(close_col))
        curr_close = _safe_float(latest.get(close_col))
        change_pct = None
        if prev_close and curr_close and prev_close > 0:
            change_pct = (curr_close - prev_close) / prev_close * 100

        # Volume vs 20-day average
        vol_sma20 = _safe_float(df['Volume'].rolling(20).mean().iloc[-1])
        latest_vol = _safe_float(latest.get('Volume'))
        rvol = (latest_vol / vol_sma20) if (vol_sma20 and vol_sma20 > 0) else None

        # ── Key levels ──────────────────────────────────────────────────
        sma200 = _safe_float(latest.get('SMA200'))
        ema9 = _safe_float(latest.get('EMA9'))
        ema20 = _safe_float(latest.get('EMA20'))
        bb_upper = _safe_float(latest.get('BB_Upper'))
        bb_lower = _safe_float(latest.get('BB_Lower'))
        atr14 = _safe_float(latest.get('ATR14'))
        macd = _safe_float(latest.get('MACD'))
        macd_sig = _safe_float(latest.get('MACD_Signal'))
        stoch_k = _safe_float(latest.get('StochRSI_K'))
        stoch_d = _safe_float(latest.get('StochRSI_D'))
        vol_20d = _safe_float(latest.get('volatility_20d'))

        above_sma200 = (curr_close > sma200) if (curr_close and sma200) else None

        # ── Strat / FTFC ────────────────────────────────────────────────
        strat_labels = strat.classify_series(df)
        strat_data = strat.detect_combos(df, strat_labels)
        daily_strat = strat_labels.iloc[-1]
        daily_combo = strat_data['strat_combo'].iloc[-1]
        daily_setup = strat_data['strat_setup'].iloc[-1]

        tf_dfs = loader.build_multi_timeframe(df, timeframes=['D', 'W', 'M'])
        tf_classified = {tf: tf_df for tf, tf_df in tf_dfs.items() if not tf_df.empty}
        ftfc_score, ftfc_dir, ftfc_labels = strat.calculate_ftfc(tf_classified)

        # ── Signal conditions ───────────────────────────────────────────
        call_score, _ = check_call_conditions(latest)
        put_score, _ = check_put_conditions(latest)

        if call_score >= signal_threshold:
            signal_status = f'CALL setup ({call_score}/5)'
        elif put_score >= signal_threshold:
            signal_status = f'PUT setup ({put_score}/5)'
        elif call_score >= building_threshold:
            signal_status = f'CALL building ({call_score}/5)'
        elif put_score >= building_threshold:
            signal_status = f'PUT building ({put_score}/5)'
        else:
            signal_status = 'No signal'

        consec_up = int(latest.get('Consecutive_Up', 0))
        consec_down = int(latest.get('Consecutive_Down', 0))

        brief['tickers'][ticker] = {
            # Price & change
            'price': curr_close,
            'change_pct': change_pct,
            'prev_day_high': _safe_float(latest.get('High')),
            'prev_day_low': _safe_float(latest.get('Low')),
            'prev_day_open': _safe_float(latest.get('Open')),
            'prev_day_close': curr_close,
            'prev_day_volume': latest_vol,
            'rvol': rvol,
            # Indicators
            'rsi': _safe_float(rsi),
            'rsi_direction': 'down' if (rsi and rsi < 50) else 'up',
            'stoch_k': stoch_k,
            'stoch_d': stoch_d,
            'macd': macd,
            'macd_signal_val': macd_sig,
            'macd_cross': _macd_cross(macd, macd_sig),
            # Key levels
            'sma200': sma200,
            'ema9': ema9,
            'ema20': ema20,
            'bb_upper': bb_upper,
            'bb_lower': bb_lower,
            'atr14': atr14,
            'above_sma200': above_sma200,
            'vol_regime': _vol_regime(vol_20d),
            'volatility_20d': vol_20d,
            # Signal / strat
            'consecutive_up': consec_up,
            'consecutive_down': consec_down,
            'signal_status': signal_status,
            'strat_daily': daily_strat,
            'strat_combo': daily_combo,
            'strat_setup': bool(daily_setup),
            'ftfc_score': float(ftfc_score),
            'ftfc_direction': ftfc_dir,
            'ftfc_labels': {k: v for k, v in ftfc_labels.items()},
        }

    # Economic events
    brief['events'] = load_economic_events(date.today())

    # Earnings: weekday → today's; Sunday → upcoming week's
    today = date.today()
    is_sunday = today.weekday() == 6
    brief['earnings'] = load_earnings_for_brief(today, weekly=is_sunday)

    return brief


# ── Discord Formatting (3 embeds) ───────────────────────────────────────────

def _fmt_price(val):
    return f'${val:,.2f}' if val is not None else 'N/A'


def _fmt_pct(val):
    return f'{val:+.2f}%' if val is not None else ''


def _build_overview_embed(brief: dict) -> dict:
    """Embed 1: Market overview — previous day recap + regime context."""
    lines = []
    for ticker, d in brief.get('tickers', {}).items():
        if d.get('status') == 'NO DATA':
            lines.append(f'**{ticker}** — No data')
            continue

        chg = _fmt_pct(d.get('change_pct'))
        rsi_arrow = '\u2193' if d.get('rsi_direction') == 'down' else '\u2191'
        sma_pos = ''
        if d.get('above_sma200') is not None:
            sma_pos = 'Above' if d['above_sma200'] else 'Below'
            sma_pos = f' | {sma_pos} SMA200'

        rvol_str = f' | RVOL {d["rvol"]:.1f}x' if d.get('rvol') else ''
        vol_str = f' | Vol: {d["vol_regime"]}' if d.get('vol_regime') != 'N/A' else ''

        lines.append(
            f'**{ticker}** {_fmt_price(d["price"])} ({chg})'
            f' | RSI {d["rsi"]:.0f}{rsi_arrow}'
            f'{sma_pos}{rvol_str}{vol_str}'
        )

    # FTFC summary line
    ftfc_parts = []
    for ticker, d in brief.get('tickers', {}).items():
        if d.get('status') == 'NO DATA':
            continue
        ftfc_parts.append(f'{ticker}: {d["ftfc_direction"]} ({d["ftfc_score"]:+.1f})')
    if ftfc_parts:
        lines.append('')
        lines.append('**FTFC:** ' + ' | '.join(ftfc_parts))

    # Determine overall color
    bullish_count = sum(
        1 for d in brief.get('tickers', {}).values()
        if d.get('ftfc_direction') == 'bullish'
    )
    total = sum(1 for d in brief.get('tickers', {}).values() if d.get('status') != 'NO DATA')
    if bullish_count > total / 2:
        color = 0x2ecc71  # green
    elif bullish_count < total / 2:
        color = 0xe74c3c  # red
    else:
        color = 0x3498db  # blue

    return {
        'title': f'PRE-MARKET BRIEF \u2014 {brief["date"]}',
        'description': '\n'.join(lines),
        'color': color,
    }


def _build_ticker_fields(brief: dict) -> list:
    """Build per-ticker analysis fields (3 fields per ticker, inline)."""
    fields = []
    for ticker, d in brief.get('tickers', {}).items():
        if d.get('status') == 'NO DATA':
            fields.append({'name': f'{ticker}', 'value': 'No data', 'inline': False})
            continue

        # Field 1: Key Levels
        level_lines = []
        if d.get('prev_day_high') and d.get('prev_day_low'):
            level_lines.append(f'Prev H/L: {_fmt_price(d["prev_day_high"])} / {_fmt_price(d["prev_day_low"])}')
        if d.get('sma200'):
            level_lines.append(f'SMA200: {_fmt_price(d["sma200"])}')
        if d.get('bb_upper') and d.get('bb_lower'):
            level_lines.append(f'BB: {_fmt_price(d["bb_upper"])} / {_fmt_price(d["bb_lower"])}')
        if d.get('ema9') and d.get('ema20'):
            level_lines.append(f'EMA 9/20: {_fmt_price(d["ema9"])} / {_fmt_price(d["ema20"])}')
        if d.get('atr14'):
            level_lines.append(f'ATR14: {_fmt_price(d["atr14"])}')

        fields.append({
            'name': f'{ticker} Levels',
            'value': '\n'.join(level_lines) or 'N/A',
            'inline': True,
        })

        # Field 2: Momentum
        rsi_arrow = '\u2193' if d.get('rsi_direction') == 'down' else '\u2191'
        mom_lines = [f'RSI: {d["rsi"]:.0f} {rsi_arrow}']
        if d.get('stoch_k') is not None:
            mom_lines[0] += f' | StochRSI: {d["stoch_k"]:.0f}/{d["stoch_d"]:.0f}'
        mom_lines.append(f'MACD: {d.get("macd_cross", "N/A")}')

        consec = ''
        if d['consecutive_down'] >= 2:
            consec = f'{d["consecutive_down"]} consecutive down'
        elif d['consecutive_up'] >= 2:
            consec = f'{d["consecutive_up"]} consecutive up'
        if consec:
            mom_lines.append(consec)
        mom_lines.append(d['signal_status'])

        fields.append({
            'name': f'{ticker} Momentum',
            'value': '\n'.join(mom_lines),
            'inline': True,
        })

        # Field 3: Strat / FTFC
        strat_lines = [f'Daily: {d["strat_daily"]}']
        if d['strat_combo'] != 'none':
            strat_lines[0] += f' | Combo: {d["strat_combo"]}'
        strat_lines.append(
            f'FTFC: {d["ftfc_score"]:+.1f} ({d["ftfc_direction"]})'
        )
        tf_parts = ' '.join(f'{k}:{v}' for k, v in d.get('ftfc_labels', {}).items())
        if tf_parts:
            strat_lines.append(tf_parts)
        if d['strat_setup']:
            strat_lines.append('**SETUP FORMING**')

        fields.append({
            'name': f'{ticker} Strat',
            'value': '\n'.join(strat_lines),
            'inline': True,
        })

    return fields


def _build_calendar_embed(events: dict) -> dict:
    """Embed 3: Economic calendar — today's events + week ahead."""
    today_evts = events.get('today', [])
    week_evts = events.get('week', [])

    # Today's events
    if today_evts:
        today_lines = []
        for ev in today_evts[:8]:
            icon = '\U0001f534' if ev['importance'] == 'high' else '\U0001f7e1'
            time_str = ev['time'] or 'TBD'
            line = f'{icon} **{time_str}** {ev["name"]}'
            if ev.get('forecast'):
                line += f' (Fcst: {ev["forecast"]})'
            today_lines.append(line)
        today_text = '\n'.join(today_lines)
    else:
        today_text = 'No major events today'

    embed = {
        'title': 'Economic Calendar',
        'description': today_text,
        'color': 0x95a5a6,
    }

    # Week ahead field
    if week_evts:
        week_lines = []
        for ev in week_evts[:6]:
            icon = '\U0001f534' if ev['importance'] == 'high' else '\U0001f7e1'
            d = ev['date']
            day_str = d.strftime('%a %m/%d') if hasattr(d, 'strftime') else str(d)
            week_lines.append(f'{icon} {day_str} — {ev["name"]}')
        embed['fields'] = [{
            'name': 'This Week',
            'value': '\n'.join(week_lines),
            'inline': False,
        }]

    return embed


def format_discord_message(brief: dict) -> dict:
    """Format brief as a Discord webhook payload with 3 embeds."""
    overview = _build_overview_embed(brief)
    ticker_fields = _build_ticker_fields(brief)
    calendar = _build_calendar_embed(brief.get('events', {}))

    # Ticker analysis embed with the per-ticker fields
    ticker_embed = {
        'title': 'Ticker Analysis',
        'fields': ticker_fields,
        'color': overview.get('color', 0x3498db),
    }

    embeds = [overview, ticker_embed, calendar]

    # Safety: truncate if total exceeds Discord limit
    total_chars = sum(len(json.dumps(e)) for e in embeds)
    if total_chars > MAX_EMBED_CHARS:
        logger.warning("Discord payload %d chars exceeds %d, dropping calendar",
                        total_chars, MAX_EMBED_CHARS)
        embeds = embeds[:2]

    return {'embeds': embeds}


# ── Cloud SQL Persistence ───────────────────────────────────────────────────

def persist_to_cloud_sql(brief: dict) -> int:
    """Write premarket analysis rows to Cloud SQL premarket_analysis table."""
    try:
        from gcp.database import is_cloud_sql_configured, upsert_dataframe
    except ImportError:
        logger.warning("gcp.database not available -- skipping DB persist")
        return 0

    if not is_cloud_sql_configured():
        logger.info("Cloud SQL not configured -- skipping DB persist")
        return 0

    analysis_date = date.today()
    rows = []
    for ticker, data in brief.get('tickers', {}).items():
        if data.get('status') == 'NO DATA':
            continue
        rows.append({
            'analysis_date': analysis_date,
            'ticker': ticker,
            'price': data.get('price'),
            'rsi': data.get('rsi'),
            'rsi_direction': data.get('rsi_direction'),
            'consecutive_up': data.get('consecutive_up'),
            'consecutive_down': data.get('consecutive_down'),
            'signal_status': data.get('signal_status'),
            'strat_daily': str(data.get('strat_daily', '')),
            'strat_combo': str(data.get('strat_combo', '')),
            'strat_setup': data.get('strat_setup', False),
            'ftfc_score': data.get('ftfc_score'),
            'ftfc_direction': data.get('ftfc_direction'),
            'ftfc_labels': json.dumps(data.get('ftfc_labels', {})),
            'prev_day_high': data.get('prev_day_high'),
            'prev_day_low': data.get('prev_day_low'),
            # New enriched fields (silently dropped if columns don't exist yet)
            'change_pct': data.get('change_pct'),
            'rvol': data.get('rvol'),
            'sma200': data.get('sma200'),
            'bb_upper': data.get('bb_upper'),
            'bb_lower': data.get('bb_lower'),
            'ema9': data.get('ema9'),
            'ema20': data.get('ema20'),
            'atr14': data.get('atr14'),
            'volatility_20d': data.get('volatility_20d'),
            'macd_cross': data.get('macd_cross'),
            'vol_regime': data.get('vol_regime'),
            'above_sma200': data.get('above_sma200'),
            'stoch_rsi_k': data.get('stoch_k'),
            'stoch_rsi_d': data.get('stoch_d'),
        })

    if not rows:
        return 0

    df = pd.DataFrame(rows)
    n = upsert_dataframe(df, 'premarket_analysis', ['analysis_date', 'ticker'])
    logger.info("Upserted %d rows to premarket_analysis", n)
    return n


def send_to_discord(message: dict, webhook_url: str, timeout: int = 10):
    """Send formatted message to Discord webhook."""
    response = requests.post(webhook_url, json=message, timeout=timeout)
    response.raise_for_status()
    print(f"Discord message sent successfully (status {response.status_code})")


def main():
    webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')

    cfg = load_config()
    data_dir = os.environ.get('DATA_DIR', cfg.market.data_dir)

    print("Generating pre-market brief...")
    brief = generate_premarket_brief(cfg=cfg, data_dir=data_dir)
    print(json.dumps(brief, indent=2, default=str))

    # Persist to Cloud SQL
    n = persist_to_cloud_sql(brief)
    print(f"Persisted {n} rows to premarket_analysis")

    if webhook_url:
        message = format_discord_message(brief)
        send_to_discord(message, webhook_url, timeout=cfg.monitor.discord_timeout)
    else:
        print("\nDISCORD_WEBHOOK_URL not set -- printing message only")
        message = format_discord_message(brief)
        print(json.dumps(message, indent=2))


if __name__ == '__main__':
    main()
