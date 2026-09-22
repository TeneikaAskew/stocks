#!/usr/bin/env python3
"""
Weekend review -- Cloud Run Job triggered Saturday morning.

Loads the week's logged trades and computes their realized performance five
ways: overall, by direction, by signal-strength rung, by ticker and by exit
reason.

**The Discord embed carries three of those five.** `format_discord_message`
emits `Overall`, the per-direction pair and `By Signal Strength` and nothing
else, so `by_ticker` and `by_exit_reason` are computed on every run and reach
only this job's stdout. An earlier version of this docstring said the summary
was "broken down ... by ticker and by exit reason" -- written on 2026-09-22 in
the same commit that established, in MODEL-WEEK-001, that it is not. DOC-64.

Every number is a realized statistic over `trades`. Nothing here is compared
to a backtest, an expectation or a prior -- until 2026-09-22 this docstring
said it "compares actual performance to backtest expectations", which no code
in this file has ever done (DOC-36, under #1137).

Unknown is not zero. A return the writer did not record stays `NaN` through
every statistic and renders as an em-dash in the embed; see `_win_rate`.
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


def _win_rate(returns: pd.Series) -> float:
    """Fraction of KNOWN returns that are positive; `nan` when none are known.

    `(s > 0).mean()` answers `0.0` for an all-NULL Series, because `NaN > 0` is
    False for every row. On the weekly embed that renders as "Win Rate: 0.0%",
    indistinguishable from a week in which every trade lost -- CLAUDE.md Rule
    3.7 forbidden pattern 2, on the one surface a person reads to judge the
    score ladder. Measured 2026-09-22 by running an all-NULL frame through
    `generate_weekly_review`; the embed published 0.0% in seven places.
    """
    known = returns.dropna()
    if known.empty:
        return float("nan")
    return float((known > 0).mean())


def _total_return(returns: pd.Series) -> float:
    """Sum of KNOWN returns; `nan` when none are known.

    The same fabricated zero in a different shape: pandas sums an all-NaN
    Series to `0.0` because `min_count` defaults to 0. `min_count=1` returns
    `NaN` instead, which is what `avg_return` (`.mean()`) already did -- the
    file always knew how to say "unknown" on one of the three.
    """
    return float(returns.sum(min_count=1))


def _known_returns(trades: pd.DataFrame) -> pd.Series:
    """The `return_pct` column as floats, with unparseable values as NaN.

    A `trades` frame with rows but no `return_pct` column is a defect in the
    writer, not a degraded week, so it raises rather than publishing a review
    whose every return statistic would be unknown. Until 2026-09-22 it raised
    too -- but incidentally, as `IndexingError: Unalignable boolean Series
    provided as indexer` out of `trades[trades.get(...) > 0]`, which named
    neither the column nor the cause. Loud was never the complaint;
    unintelligible was.
    """
    if "return_pct" not in trades.columns:
        raise ValueError(
            f"`trades` has {len(trades)} row(s) but no `return_pct` column "
            f"(columns: {sorted(trades.columns)}). Refusing to publish a "
            "weekly review in which every return statistic would be unknown."
        )
    return pd.to_numeric(trades["return_pct"], errors="coerce")


def _pct(value, digits: int = 1) -> str:
    """Render a rate or return, or an em-dash when it is unknown.

    The display layer is the one place CLAUDE.md Rule 3.7 permits a fallback --
    it lists display-layer rendering of a null or NaN value as an em-dash among
    its allowed exceptions, because the embed cannot print a float that does not
    exist. Everything above this function carries `NaN` end to end.
    """
    if value is None:
        return "\u2014"
    try:
        if np.isnan(value):
            return "\u2014"
    except TypeError:
        return "\u2014"
    return f"{value:.{digits}%}"


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

    # Overall metrics. `returns` is the single NaN-preserving view every
    # statistic below is computed from; a missing column raises in
    # `_known_returns` rather than coercing to a number nothing can
    # distinguish from a real one.
    returns = _known_returns(trades)
    total = len(trades)

    review['total_trades'] = total
    review['win_rate'] = _win_rate(returns)
    review['total_pnl'] = _total_return(returns)
    review['avg_return'] = float(returns.mean())

    # By direction
    if 'direction' in trades.columns:
        for direction in ['CALL', 'PUT']:
            dir_trades = trades[trades['direction'] == direction]
            if not dir_trades.empty:
                review[f'{direction.lower()}_trades'] = len(dir_trades)
                review[f'{direction.lower()}_win_rate'] = _win_rate(returns[dir_trades.index])

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
                    'win_rate': _win_rate(returns[rung.index]),
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
                'win_rate': _win_rate(returns[t_trades.index]),
                'total_return': _total_return(returns[t_trades.index]),
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
                f"Win Rate: {_pct(review['win_rate'])}\n"
                f"Total P/L: {_pct(review['total_pnl'], 3)} | "
                f"Avg Return: {_pct(review['avg_return'], 3)}"
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
                # `.get(key, 0)` on a win rate was itself Rule 3.7 pattern 2:
                # an absent key rendered as 0.0%. Absent is now an em-dash.
                'value': f"Trades: {count} | Win Rate: {_pct(review.get(f'{direction}_win_rate'))}",
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
                f"{s['label']} ({span}/{s_max}): {s['trades']} trades, "
                f"{_pct(s['win_rate'])} win rate"
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

    # `NaN > 0` is False, so an all-unknown week would have taken the red
    # branch and read as a losing week. Unknown gets the same grey the
    # no-trades embed uses.
    pnl = review['total_pnl']
    if pnl is None or np.isnan(pnl):
        color = 0x808080
    else:
        color = 0x00ff00 if pnl > 0 else 0xff0000

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
