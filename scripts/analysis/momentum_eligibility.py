"""Momentum strategy fire-eligibility analysis (Track A G.P0.11.e — analysis half).

The audit (2026-05-08) found that the momentum strategy fired 0 alerts
in 50 days across SPY/IWM/QQQ. Two possible causes:
  (a) The strategy was CONSIDERED but never reached
      MIN_CONDITIONS_MOMENTUM (default 5) — tuning issue.
  (b) The strategy was NEVER CONSIDERED (orchestration excludes it) —
      pipeline issue.

This script answers (a) by replaying `momentum._check_call_conditions`
and `_check_put_conditions` against historical 1-min bars from
`market_data_intraday` and reporting:
  - Per-condition fire rate (% of bars where each scored)
  - Score distribution (0–7 histogram per ticker per direction)
  - Would-fire counts at MIN_CONDITIONS ∈ {3, 4, 5, 6}

Track D's separate "live considered-vs-fired counter" instrumentation
half (issue #312) answers (b). Pair the two to fully close G.P0.11.

Usage:
  python -m scripts.analysis.momentum_eligibility \
    --tickers SPY IWM QQQ \
    --days 50 \
    --output docs/audit/2026-05-08/momentum_eligibility_report.md

The data loader uses Cloud SQL when CLOUD_SQL_CONNECTION_NAME is set,
falling back to local parquet otherwise.
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import List

import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.data_loader import DataLoader  # noqa: E402
from lib.indicators import add_all_indicators  # noqa: E402
from lib.strategies import momentum as mom  # noqa: E402
from lib.strategies.config import (  # noqa: E402
    CALL_RSI_RANGE, PUT_RSI_RANGE, MIN_CONDITIONS_MOMENTUM,
    MIN_CORE_CONDITIONS, CORE_CALL_CONDITIONS, CORE_PUT_CONDITIONS,
)

log = logging.getLogger(__name__)


# ── Pure helpers ──────────────────────────────────────────────────────


def evaluate_bars(
    df: pd.DataFrame,
    *,
    call_rsi_range=CALL_RSI_RANGE,
    put_rsi_range=PUT_RSI_RANGE,
    thresholds: tuple[int, ...] = (3, 4, 5, 6),
) -> dict:
    """Score every bar against momentum CALL + PUT conditions.

    `would_fire_at[t]` counts bars where (a) `score >= t` AND (b) at
    least `MIN_CORE_CONDITIONS` (default 2) of the score's contributing
    conditions are CORE conditions (consecutive_*, rsi_*_recovery,
    above/below_vwap, above/below_ema9). This mirrors the live gate in
    `MomentumStrategy.evaluate()` — without it, threshold 3/4 bars
    composed only of confirmer factors (rvol/atr/rsi_thrust) would
    inflate the would-fire count beyond what production would actually
    surface. Codex review on PR #330 caught this.

    Returns:
      {
        'n_bars': int,
        'call': {
            'condition_fire_count': {cond: count, ...},
            'score_dist': {0: n0, 1: n1, ..., 7: n7},
            'would_fire_at': {3: n3, 4: n4, 5: n5, 6: n6},
            'would_fire_at_no_core_gate': {...},  # diagnostic
        },
        'put': {...},
      }
    """
    out = {
        'n_bars': 0,
        'call': {
            'condition_fire_count': Counter(),
            'score_dist': Counter(),
            'would_fire_at': {t: 0 for t in thresholds},
            'would_fire_at_no_core_gate': {t: 0 for t in thresholds},
        },
        'put': {
            'condition_fire_count': Counter(),
            'score_dist': Counter(),
            'would_fire_at': {t: 0 for t in thresholds},
            'would_fire_at_no_core_gate': {t: 0 for t in thresholds},
        },
    }

    for _, row in df.iterrows():
        # Skip bars where the load-bearing indicators are NaN — the
        # strategy itself bails on these (warmup window).
        rsi_col = mom._rsi_col_name() if hasattr(mom, '_rsi_col_name') else 'RSI14'
        if pd.isna(row.get(rsi_col, row.get('RSI14'))):
            continue

        out['n_bars'] += 1

        call_score, call_conds = mom._check_call_conditions(row, call_rsi_range)
        put_score, put_conds = mom._check_put_conditions(row, put_rsi_range)
        call_core = sum(1 for c in call_conds if c in CORE_CALL_CONDITIONS)
        put_core = sum(1 for c in put_conds if c in CORE_PUT_CONDITIONS)

        for c in call_conds:
            out['call']['condition_fire_count'][c] += 1
        out['call']['score_dist'][call_score] += 1
        for t in thresholds:
            if call_score >= t:
                out['call']['would_fire_at_no_core_gate'][t] += 1
                if call_core >= MIN_CORE_CONDITIONS:
                    out['call']['would_fire_at'][t] += 1

        for c in put_conds:
            out['put']['condition_fire_count'][c] += 1
        out['put']['score_dist'][put_score] += 1
        for t in thresholds:
            if put_score >= t:
                out['put']['would_fire_at_no_core_gate'][t] += 1
                if put_core >= MIN_CORE_CONDITIONS:
                    out['put']['would_fire_at'][t] += 1

    return out


def format_report(per_ticker: dict, days: int) -> str:
    """Render the analysis dict as a markdown report."""
    lines: list[str] = []
    lines.append("# Momentum Strategy — Fire-Eligibility Analysis")
    lines.append("")
    lines.append(f"**Date generated**: {date.today().isoformat()}  ")
    # Codex review on PR #330 caught that --days was documented as
    # trading days but used as calendar days. Now stated explicitly.
    lines.append(f"**Lookback**: {days} calendar days (≈ {int(days * 5/7)} trading days)  ")
    lines.append(f"**Strategy**: `lib/strategies/momentum.py` (7 conditions per direction)  ")
    lines.append(f"**Live MIN_CONDITIONS**: {MIN_CONDITIONS_MOMENTUM} (current production gate)  ")
    lines.append(f"**Live MIN_CORE_CONDITIONS gate**: {MIN_CORE_CONDITIONS} (would-fire counts apply this)  ")
    lines.append("")
    lines.append("## Background")
    lines.append("")
    lines.append("Audit 2026-05-08 found 0 momentum fires across SPY/IWM/QQQ in 50 days. "
                 "This report tests hypothesis (a) — the strategy reached `evaluate()` "
                 "but never crossed MIN_CONDITIONS — by replaying both condition checks "
                 "against historical 1-min bars. Hypothesis (b) (orchestration excludes "
                 "the strategy) is answered by Track D's instrumentation half (issue #312).")
    lines.append("")

    for ticker, result in sorted(per_ticker.items()):
        lines.append(f"## {ticker}")
        lines.append("")
        n = result['n_bars']
        if n == 0:
            lines.append(f"_No bars available for {ticker}._")
            lines.append("")
            continue
        lines.append(f"**Bars evaluated**: {n:,}")
        lines.append("")

        for direction in ('call', 'put'):
            lines.append(f"### {direction.upper()}")
            lines.append("")
            cond_count = result[direction]['condition_fire_count']
            score_dist = result[direction]['score_dist']
            would_fire = result[direction]['would_fire_at']

            lines.append("**Per-condition fire rate** (% of bars where condition scored):")
            lines.append("")
            lines.append("| Condition | Fires | % of bars |")
            lines.append("|---|---:|---:|")
            for c, count in cond_count.most_common():
                pct = 100.0 * count / n
                lines.append(f"| `{c}` | {count:,} | {pct:.1f}% |")
            lines.append("")

            lines.append("**Score distribution**:")
            lines.append("")
            lines.append("| Score | Bars | % |")
            lines.append("|---:|---:|---:|")
            for s in sorted(score_dist.keys()):
                pct = 100.0 * score_dist[s] / n
                lines.append(f"| {s} | {score_dist[s]:,} | {pct:.1f}% |")
            lines.append("")

            no_gate = result[direction]['would_fire_at_no_core_gate']
            lines.append("**Would-fire count at each MIN_CONDITIONS threshold** "
                         f"(after MIN_CORE_CONDITIONS={MIN_CORE_CONDITIONS} gate, "
                         "which mirrors the live `MomentumStrategy.evaluate()`):")
            lines.append("")
            lines.append("| Threshold | With core gate | % | Without core gate (diagnostic) | Δ confirmer-only |")
            lines.append("|---:|---:|---:|---:|---:|")
            for t in sorted(would_fire.keys()):
                gated = would_fire[t]
                ungated = no_gate[t]
                gated_pct = 100.0 * gated / n
                marker = "  ← live" if t == MIN_CONDITIONS_MOMENTUM else ""
                lines.append(
                    f"| ≥ {t} | {gated:,} | {gated_pct:.1f}% | {ungated:,} | "
                    f"{ungated - gated:,} |{marker}"
                )
            lines.append("")

    lines.append("## Interpretation guide")
    lines.append("")
    lines.append("- **A condition that fires on >70% of bars** is a free-score factor; the audit "
                 "(§3.10) has historically dropped these (e.g. `stoch_rsi_not_overbought` in 0.7.1, "
                 "`near_below_emas` in 0.7.2). Candidates for removal.")
    lines.append("- **A condition that fires on <2% of bars** is a chronically-missing gate; if it's "
                 "the difference between score=4 and score=5 (live threshold), the strategy is "
                 "structurally unable to fire and the threshold should be either lowered OR the "
                 "condition replaced.")
    lines.append("- **Would-fire at threshold N**: if `would_fire_at[5]` is 0 but `would_fire_at[4]` "
                 "is non-trivial, the audit's '0 fires' finding is a tuning issue, not an orchestration "
                 "issue.")
    lines.append("")
    lines.append("## Pair with Track D's instrumentation half")
    lines.append("")
    lines.append("This analysis is one half of G.P0.11. The other half — instrumenting the live "
                 "monitor to count `momentum.evaluate()` invocations vs fires — is tracked in "
                 "issue #312 (Track D). Once that lands, comparing the live consideration count "
                 "against this report's would-fire counts answers whether the discrepancy is a "
                 "tuning issue (here) or an orchestration issue (there).")
    lines.append("")
    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────


def main(argv: List[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tickers', nargs='+', default=['SPY', 'IWM', 'QQQ'])
    # `--days` is calendar days, not trading days. Codex review on
    # PR #330 caught the naming confusion. `--calendar-days` is the
    # canonical alias; `--days` kept as backward-compat shim.
    parser.add_argument('--calendar-days', '--days', dest='days', type=int,
                        default=50,
                        help='Lookback in calendar days (≈ days × 5/7 trading sessions). '
                             '50 calendar days ≈ 35 trading days.')
    parser.add_argument('--output', default='docs/audit/2026-05-08/momentum_eligibility_report.md',
                        help='Path to write the markdown report')
    parser.add_argument('--data-dir', default='data',
                        help='Local parquet root (used as fallback when Cloud SQL not configured)')
    parser.add_argument('--cached-csv-dir', default=None,
                        help='If set, read intraday from <dir>/intraday_<ticker_lower>_full.csv '
                             'instead of Cloud SQL / parquet. Used for offline replay against '
                             'Track E\'s cached audit pulls.')
    args = parser.parse_args(argv)

    loader = DataLoader(data_dir=args.data_dir)
    today = date.today()
    start = today - timedelta(days=args.days)

    per_ticker: dict = {}
    for ticker in args.tickers:
        if args.cached_csv_dir:
            csv_path = Path(args.cached_csv_dir) / f'intraday_{ticker.lower()}_full.csv'
            if not csv_path.exists():
                csv_path = Path(args.cached_csv_dir) / f'intraday_{ticker.lower()}.csv'
            log.info("loading intraday for %s from %s", ticker, csv_path)
            df = pd.read_csv(csv_path)
            df['ts'] = pd.to_datetime(df['ts'], utc=True).dt.tz_localize(None)
            df = df.set_index('ts')
            df.index.name = 'Time'
            df['Time'] = df.index
            df = df.rename(columns={
                'open': 'Open', 'high': 'High', 'low': 'Low',
                'close': 'Close', 'volume': 'Volume',
            })
        else:
            log.info("loading intraday for %s [%s..%s]", ticker, start, today)
            df = loader.load_intraday(
                ticker,
                start_date=start.strftime('%Y-%m-%d'),
                end_date=today.strftime('%Y-%m-%d'),
            )
        if df is None or df.empty:
            log.warning("no intraday data for %s — skipping", ticker)
            per_ticker[ticker] = {'n_bars': 0,
                                  'call': {'condition_fire_count': Counter(),
                                           'score_dist': Counter(),
                                           'would_fire_at': {3: 0, 4: 0, 5: 0, 6: 0}},
                                  'put':  {'condition_fire_count': Counter(),
                                           'score_dist': Counter(),
                                           'would_fire_at': {3: 0, 4: 0, 5: 0, 6: 0}}}
            continue

        # Add the indicator columns the strategy reads (RSI14, VWAP, EMA9,
        # RVol_Recent_20, ATR_Expansion, RSI_Thrust_3, Consecutive_*).
        df = add_all_indicators(df)
        per_ticker[ticker] = evaluate_bars(df)
        log.info("%s: %d bars evaluated, would-fire-at-5 CALL=%d PUT=%d",
                 ticker, per_ticker[ticker]['n_bars'],
                 per_ticker[ticker]['call']['would_fire_at'][5],
                 per_ticker[ticker]['put']['would_fire_at'][5])

    report = format_report(per_ticker, args.days)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    log.info("wrote report → %s", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
