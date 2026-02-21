#!/usr/bin/env python3
"""
Pre-market brief -- Cloud Run Job triggered by Cloud Scheduler at 8:30 AM ET.

Loads latest data, computes Strat daily/weekly labels and FTFC,
checks which tickers have signals building, and sends a Discord embed.
"""

import os
import sys
import json
import requests
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.data_loader import DataLoader
from lib.indicators import add_all_indicators
from lib.strat import StratClassifier
from lib.signals import check_call_conditions, check_put_conditions
from lib.config import load_config


def generate_premarket_brief(cfg=None, data_dir: str = None) -> dict:
    """Generate pre-market brief for all tickers.

    Returns a dict with per-ticker analysis.
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
        # Load daily data with indicators
        df = loader.load_daily(ticker)
        if df.empty:
            brief['tickers'][ticker] = {'status': 'NO DATA'}
            continue

        close_col = 'Close' if 'Close' in df.columns else 'Last'
        df = add_all_indicators(df, close_col=close_col)

        latest = df.iloc[-1]
        rsi = latest.get(cfg.indicator.rsi_col, 50)
        consec_up = int(latest.get('Consecutive_Up', 0))
        consec_down = int(latest.get('Consecutive_Down', 0))

        # Strat classification on daily
        strat_labels = strat.classify_series(df)
        strat_data = strat.detect_combos(df, strat_labels)
        daily_strat = strat_labels.iloc[-1]
        daily_combo = strat_data['strat_combo'].iloc[-1]
        daily_setup = strat_data['strat_setup'].iloc[-1]

        # Multi-timeframe FTFC (using daily data aggregated to weekly/monthly)
        tf_dfs = loader.build_multi_timeframe(df, timeframes=['D', 'W', 'M'])
        # Classify each timeframe
        tf_classified = {}
        for tf, tf_df in tf_dfs.items():
            if not tf_df.empty:
                tf_classified[tf] = tf_df
        ftfc_score, ftfc_dir, ftfc_labels = strat.calculate_ftfc(tf_classified)

        # Check signal conditions building
        call_score, call_conds = check_call_conditions(latest)
        put_score, put_conds = check_put_conditions(latest)

        # Determine status
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

        # Key levels
        ticker_brief = {
            'price': float(latest.get(close_col, 0)),
            'rsi': float(rsi),
            'rsi_direction': 'down' if rsi < 50 else 'up',
            'consecutive_up': consec_up,
            'consecutive_down': consec_down,
            'signal_status': signal_status,
            'strat_daily': daily_strat,
            'strat_combo': daily_combo,
            'strat_setup': bool(daily_setup),
            'ftfc_score': float(ftfc_score),
            'ftfc_direction': ftfc_dir,
            'ftfc_labels': {k: v for k, v in ftfc_labels.items()},
            'prev_day_high': float(latest.get('Prev_Day_High', 0)) if 'Prev_Day_High' in df.columns else None,
            'prev_day_low': float(latest.get('Prev_Day_Low', 0)) if 'Prev_Day_Low' in df.columns else None,
        }
        brief['tickers'][ticker] = ticker_brief

    return brief


def format_discord_message(brief: dict) -> dict:
    """Format brief as a Discord webhook embed."""
    fields = []
    for ticker, data in brief.get('tickers', {}).items():
        if data.get('status') == 'NO DATA':
            fields.append({'name': ticker, 'value': 'No data available', 'inline': True})
            continue

        rsi_arrow = '\u2193' if data['rsi_direction'] == 'down' else '\u2191'
        consec = f"{data['consecutive_down']} down" if data['consecutive_down'] >= 2 else \
                 f"{data['consecutive_up']} up" if data['consecutive_up'] >= 2 else "Neutral"

        strat_info = f"Daily: {data['strat_daily']}"
        if data['strat_combo'] != 'none':
            strat_info += f" | Combo: {data['strat_combo']}"
        if data['strat_setup']:
            strat_info += " | SETUP FORMING"

        ftfc_info = f"FTFC: {data['ftfc_score']:+.2f} ({data['ftfc_direction']})"

        value = (
            f"RSI: {data['rsi']:.0f} {rsi_arrow} | {consec}\n"
            f"{data['signal_status']}\n"
            f"{strat_info}\n"
            f"{ftfc_info}"
        )
        fields.append({'name': f"**{ticker}** ${data['price']:.2f}", 'value': value, 'inline': False})

    embed = {
        'embeds': [{
            'title': f"PRE-MARKET BRIEF \u2014 {brief['date']}",
            'fields': fields,
            'color': 0x1f77b4,
            'footer': {'text': 'Generated by trading system'},
        }]
    }
    return embed


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

    if webhook_url:
        message = format_discord_message(brief)
        send_to_discord(message, webhook_url, timeout=cfg.monitor.discord_timeout)
    else:
        print("\nDISCORD_WEBHOOK_URL not set -- printing message only")
        message = format_discord_message(brief)
        print(json.dumps(message, indent=2))


if __name__ == '__main__':
    main()
