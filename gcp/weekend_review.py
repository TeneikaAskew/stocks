#!/usr/bin/env python3
"""
Weekend review -- Cloud Run Job triggered Saturday morning.

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


def generate_weekly_review(cfg=None, trades_dir: str = None) -> dict:
    """Generate weekly performance review from logged trades."""
    if cfg is None:
        cfg = load_config()

    trades_dir = trades_dir or cfg.market.trades_dir
    logger = TradeLogger(output_dir=trades_dir)

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
    max_score = cfg.risk.max_score
    if 'signal_strength' in trades.columns or 'total_score' in trades.columns:
        score_col = 'total_score' if 'total_score' in trades.columns else 'signal_strength'

        # Grouped by LABEL, computed from the UNROUNDED score.
        #
        # Until 2026-09-22 this called `get_signal_strength_label(int(score))`
        # while the live monitor passes the unrounded `total_score`
        # (`gcp/signal_monitor.py:1343`). Fractional scores are the normal
        # case, not an edge one: four of six catalyst-proximity multipliers are
        # non-integral (`lib/config.py:370-376`) and `strat_bonus` moves in
        # quarter points (`lib/strat.py:29-54`). Because `int()` truncates
        # toward zero, every mismatch was a DOWNGRADE -- a live `strong` at 5.1
        # was reported `medium`, a live `perfect` at 6.6 reported `strong` --
        # so each rung's win rate was contaminated by trades from the rung
        # above it, in the one report that shows the ladder's realized
        # performance to anyone. DOC-56.
        #
        # Grouping by the raw float compounded it: 4.25 and 4.5 were two groups
        # both rendered `score: 4`, so the embed showed duplicate rows with
        # conflicting win rates. One rung is now one row, with the observed
        # score span rather than a single misleading integer.
        scores = pd.to_numeric(trades[score_col], errors='coerce')
        scored = trades[scores.notna()]

        # A NaN score cannot be labelled, and must not be guessed at: every
        # `<=` comparison against NaN is False, so the ladder's else-branch
        # would have returned `perfect` -- the worst possible silent default
        # for a missing value (CLAUDE.md Rule 3.7). Counted and surfaced.
        unlabelled = int(scores.isna().sum())
        if unlabelled:
            review['strength_unlabelled_trades'] = unlabelled

        strength_data = []
        if not scored.empty:
            labels = scores[scores.notna()].map(
                lambda s: get_signal_strength_label(float(s), cfg.risk)
            )
            for label in labels.unique():
                rung = scored[labels == label]
                rung_scores = scores[rung.index]
                strength_data.append({
                    'label': label,
                    'score_min': float(rung_scores.min()),
                    'score_max': float(rung_scores.max()),
                    'trades': len(rung),
                    'win_rate': float((rung['return_pct'] > 0).mean()) if 'return_pct' in rung.columns else 0,
                    'max_score': max_score,
                })
            strength_data.sort(key=lambda r: r['score_min'])
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


def format_discord_message(review: dict, max_score: int = 8) -> dict:
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
            s_max = s.get('max_score', max_score)
            lo, hi = s['score_min'], s['score_max']
            # One rung, one row. The span is shown because a rung genuinely
            # covers a range of fractional scores; printing a single rounded
            # integer is what produced duplicate rows with conflicting win
            # rates before 2026-09-22.
            span = f"{lo:g}" if lo == hi else f"{lo:g}-{hi:g}"
            strength_lines.append(
                f"{s['label']} ({span}/{s_max}): {s['trades']} trades, {s['win_rate']:.1%} win rate"
            )
        if review.get('strength_unlabelled_trades'):
            strength_lines.append(
                f"_{review['strength_unlabelled_trades']} trade(s) with no score — not labelled_"
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

    cfg = load_config()
    trades_dir = os.environ.get('TRADES_DIR', cfg.market.trades_dir)

    print("Generating weekly review...")
    review = generate_weekly_review(cfg=cfg, trades_dir=trades_dir)
    print(json.dumps(review, indent=2, default=str))

    message = format_discord_message(review, max_score=cfg.risk.max_score)

    if webhook_url:
        requests.post(webhook_url, json=message, timeout=cfg.monitor.discord_timeout)
        print("Discord message sent.")
    else:
        print("\nDISCORD_WEBHOOK_URL not set -- printing message only")
        print(json.dumps(message, indent=2))


if __name__ == '__main__':
    main()
