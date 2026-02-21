#!/usr/bin/env python3
"""
Weekend review — Cloud Run Job triggered Saturday morning.

Loads the week's trades, enriches with indicators, compares actual
performance to backtest expectations, and sends a Discord summary.
"""

import os
import sys
import json
import requests
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np

from gcp.trade_logger import TradeLogger
from lib.config import load_config, get_signal_strength_label


def generate_weekly_review(trades_dir: str = 'data/trades') -> dict:
    """Generate weekly performance review from logged trades."""
    logger = TradeLogger(output_dir=trades_dir)
    risk, exit_, signal, strat = load_config()

    trades = logger.get_weekly_trades()
    review = {
        'week_ending': datetime.now().strftime('%Y-%m-%d'),
        'has_trades': not trades.empty,
    }

    if trades.empty:
        review['summary'] = 'No trades logged this week.'
        return review

    # Overall metrics
    total = len(trades)
    winners = trades[trades.get('return_pct', pd.Series(dtype=float)) > 0]
    win_rate = len(winners) / total if total > 0 else 0

    review['total_trades'] = total
    review['win_rate'] = win_rate
    review['total_pnl'] = float(trades['return_pct'].sum()) if 'return_pct' in trades.columns else 0
    review['avg_return'] = float(trades['return_pct'].mean()) if 'return_pct' in trades.columns else 0

    # By direction
    if 'direction' in trades.columns:
        for direction in ['CALL', 'PUT']:
            dir_trades = trades[trades['direction'] == direction]
            if not dir_trades.empty:
                review[f'{direction.lower()}_trades'] = len(dir_trades)
                review[f'{direction.lower()}_win_rate'] = float(
                    (dir_trades['return_pct'] > 0).mean() if 'return_pct' in dir_trades.columns else 0
                )

    # By signal strength
    if 'signal_strength' in trades.columns or 'total_score' in trades.columns:
        score_col = 'total_score' if 'total_score' in trades.columns else 'signal_strength'
        strength_data = []
        for score in trades[score_col].unique():
            score_trades = trades[trades[score_col] == score]
            strength_data.append({
                'score': int(score),
                'label': get_signal_strength_label(int(score)),
                'trades': len(score_trades),
                'win_rate': float((score_trades['return_pct'] > 0).mean()) if 'return_pct' in score_trades.columns else 0,
            })
        review['by_strength'] = strength_data

    # By ticker
    if 'ticker' in trades.columns:
        ticker_data = []
        for ticker in trades['ticker'].unique():
            t_trades = trades[trades['ticker'] == ticker]
            ticker_data.append({
                'ticker': ticker,
                'trades': len(t_trades),
                'win_rate': float((t_trades['return_pct'] > 0).mean()) if 'return_pct' in t_trades.columns else 0,
                'total_return': float(t_trades['return_pct'].sum()) if 'return_pct' in t_trades.columns else 0,
            })
        review['by_ticker'] = ticker_data

    # Exit reason analysis
    if 'exit_reason' in trades.columns:
        exit_data = trades.groupby('exit_reason').agg(
            count=('exit_reason', 'count'),
            avg_return=('return_pct', 'mean'),
        ).to_dict('index')
        review['by_exit_reason'] = exit_data

    return review


def format_discord_message(review: dict) -> dict:
    """Format weekly review as Discord embed."""
    if not review.get('has_trades'):
        return {
            'embeds': [{
                'title': f"WEEKLY REVIEW \u2014 {review['week_ending']}",
                'description': 'No trades logged this week.',
                'color': 0x808080,
            }]
        }

    # Build fields
    fields = [
        {
            'name': 'Overall',
            'value': (
                f"Trades: {review['total_trades']} | "
                f"Win Rate: {review['win_rate']:.1%}\n"
                f"Total P/L: {review['total_pnl']:.3%} | "
                f"Avg Return: {review['avg_return']:.3%}"
            ),
            'inline': False,
        }
    ]

    # By direction
    for direction in ['call', 'put']:
        count = review.get(f'{direction}_trades')
        if count:
            fields.append({
                'name': direction.upper(),
                'value': f"Trades: {count} | Win Rate: {review.get(f'{direction}_win_rate', 0):.1%}",
                'inline': True,
            })

    # By strength
    if 'by_strength' in review:
        strength_lines = []
        for s in review['by_strength']:
            strength_lines.append(
                f"{s['label']} ({s['score']}/8): {s['trades']} trades, {s['win_rate']:.1%} win rate"
            )
        fields.append({
            'name': 'By Signal Strength',
            'value': '\n'.join(strength_lines),
            'inline': False,
        })

    color = 0x00ff00 if review['total_pnl'] > 0 else 0xff0000

    return {
        'embeds': [{
            'title': f"WEEKLY REVIEW \u2014 {review['week_ending']}",
            'fields': fields,
            'color': color,
        }]
    }


def main():
    webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')
    trades_dir = os.environ.get('TRADES_DIR', 'data/trades')

    print("Generating weekly review...")
    review = generate_weekly_review(trades_dir=trades_dir)
    print(json.dumps(review, indent=2, default=str))

    message = format_discord_message(review)

    if webhook_url:
        requests.post(webhook_url, json=message, timeout=10)
        print("Discord message sent.")
    else:
        print("\nDISCORD_WEBHOOK_URL not set — printing message only")
        print(json.dumps(message, indent=2))


if __name__ == '__main__':
    main()
