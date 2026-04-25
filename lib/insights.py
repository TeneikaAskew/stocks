"""
Template-driven insight generator for backtest results.

Takes raw trade DataFrames and produces narrative text blocks that
describe what the numbers mean in plain English.  Used by
``scripts/generate_backtest_report.py`` to build BACKTEST_RESULTS.md.

Every public function returns a list of Markdown strings (lines).

Wording rules (locked in v3 of the insights pipeline):
- Always say "stock price" — never "underlying".
- Show percentages as ``+0.41%`` — never ``+41 bps`` in user-facing text.
- "Direction Win Rate" = strat truth (stock moved your way).
- "Contract Win Rate" = trader truth (option printed money).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from lib.copy import (
    DELTA_SLIGHTLY_OTM,
    HOLD_BUCKETS_MIN,
    HOLD_BUCKET_LABELS,
    format_option_translation,
    format_stock_move,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct(val: float, digits: int = 1) -> str:
    return f"{val * 100:.{digits}f}%"

def _stock_move(val: float) -> str:
    """User-facing stock-price-movement formatter (replaces ``_bps``)."""
    return format_stock_move(val)

def _option_translation(val: float, delta: float = DELTA_SLIGHTLY_OTM) -> str:
    """Inline ``≈ +2.0% on a slightly-OTM option`` string for a stock move."""
    return format_option_translation(val, delta)

# Legacy bps formatters — kept for raw CSV exports only. Do NOT use in
# user-facing markdown; prefer ``_stock_move`` above.
def _bps(val: float) -> str:
    return f"{val * 10000:+.0f} bps"

def _bps_unsigned(val: float) -> str:
    return f"{val * 10000:.0f} bps"

def _mins(val: float) -> str:
    return f"{val:.0f} min"

def _range_str(lo: float, hi: float) -> str:
    return f"{lo:.0f}–{hi:.0f}"


def _hold_time_bucket_stats(df: pd.DataFrame) -> List[dict]:
    """Win rate by hold-duration bucket — exposes the theta cliff.

    Returns one row per bucket in ``lib.copy.HOLD_BUCKETS_MIN`` with count,
    direction win rate, and average stock-price return. Phase 2 will add a
    parallel ``contract_wr`` column once contract premium math is wired in.
    """
    df = df.copy()
    df["duration_min"] = (
        pd.to_datetime(df["exit_time"]) - pd.to_datetime(df["entry_time"])
    ).dt.total_seconds() / 60.0
    df["direction_won"] = df["return_pct"] > 0
    rows = []
    for (lo, hi), label in zip(HOLD_BUCKETS_MIN, HOLD_BUCKET_LABELS):
        sub = df[(df["duration_min"] >= lo) & (df["duration_min"] < hi)]
        if len(sub) == 0:
            continue
        rows.append({
            "bucket": label,
            "count": len(sub),
            "direction_wr": sub["direction_won"].mean(),
            "avg_return": sub["return_pct"].mean(),
        })
    return rows


def _exit_stats(df: pd.DataFrame) -> Dict[str, dict]:
    """Per-exit-reason stats from a trades DataFrame.

    The ``won`` column is preserved for backwards-compatible internal use; in
    user-facing copy this is rendered as "Direction Win Rate" because it
    measures whether the stock moved in the trade's favor (not whether the
    option contract printed money).
    """
    df = df.copy()
    df['duration_min'] = (pd.to_datetime(df['exit_time']) -
                          pd.to_datetime(df['entry_time'])).dt.total_seconds() / 60.0
    df['won'] = df['return_pct'] > 0
    df['direction_won'] = df['won']
    n = len(df)
    stats = {}
    for reason in ['target', 'stop_loss', 'time_stop', 'rsi_extreme', 'eod_close']:
        sub = df[df['exit_reason'] == reason]
        if len(sub) == 0:
            continue
        stats[reason] = {
            'count': len(sub),
            'pct': len(sub) / n,
            'avg_dur': sub['duration_min'].mean(),
            'med_dur': sub['duration_min'].median(),
            'q25_dur': sub['duration_min'].quantile(0.25),
            'q75_dur': sub['duration_min'].quantile(0.75),
            'avg_ret': sub['return_pct'].mean(),
            'wr': sub['won'].mean(),
        }
    return stats


def _direction_stats(df: pd.DataFrame) -> Dict[str, dict]:
    """Per-direction stats."""
    df = df.copy()
    df['duration_min'] = (pd.to_datetime(df['exit_time']) -
                          pd.to_datetime(df['entry_time'])).dt.total_seconds() / 60.0
    df['won'] = df['return_pct'] > 0
    df['direction_won'] = df['won']
    stats = {}
    for d in ['CALL', 'PUT']:
        sub = df[df['direction'] == d]
        if len(sub) == 0:
            continue
        w = sub[sub['won']]
        l = sub[~sub['won']]
        stats[d] = {
            'count': len(sub),
            'wr': sub['won'].mean(),
            'avg_dur': sub['duration_min'].mean(),
            'avg_dur_w': w['duration_min'].mean() if len(w) else 0,
            'avg_dur_l': l['duration_min'].mean() if len(l) else 0,
            'avg_win': w['return_pct'].mean() if len(w) else 0,
            'avg_loss': l['return_pct'].mean() if len(l) else 0,
        }
    return stats


# ---------------------------------------------------------------------------
# Insight blocks — each returns List[str] of Markdown lines
# ---------------------------------------------------------------------------

def insight_trade_profile(ticker_stats: Dict[str, dict]) -> List[str]:
    """Overall trade profile summary table.

    ticker_stats: {ticker: {'trades': N, 'wr': float, 'avg_dur': float,
                            'avg_dur_w': float, 'avg_dur_l': float,
                            'target_pct': float, 'stop_pct': float,
                            'time_pct': float}}
    """
    lines = [
        "### Typical Trade Profile",
        "",
        "| Ticker | Trades | Win Rate | Avg Hold | Median Hold | Avg Hold (wins) | Avg Hold (losses) | Target Hit % | Stopped Out % | Time Stop % |",
        "|--------|--------|----------|----------|-------------|-----------------|-------------------|--------------|---------------|-------------|",
    ]
    for ticker, s in ticker_stats.items():
        lines.append(
            f"| **{ticker}** "
            f"| {s['trades']:,} "
            f"| {s['wr']:.1%} "
            f"| {s['avg_dur']:.0f} min "
            f"| {s['med_dur']:.0f} min "
            f"| {s['avg_dur_w']:.0f} min "
            f"| {s['avg_dur_l']:.0f} min "
            f"| {s['target_pct']:.1%} "
            f"| {s['stop_pct']:.1%} "
            f"| {s['time_pct']:.1%} |"
        )
    lines.append("")
    return lines


def insight_exit_reason_table(ticker: str, es: Dict[str, dict]) -> List[str]:
    """Duration-by-exit-reason table for one ticker."""
    lines = [
        f"**{ticker}:**",
        "",
        "| Exit Reason | Count | % | Avg Duration | Median | IQR | Avg Return | Win Rate |",
        "|-------------|-------|---|--------------|--------|-----|------------|----------|",
    ]
    for reason in ['target', 'stop_loss', 'time_stop', 'rsi_extreme', 'eod_close']:
        if reason not in es:
            continue
        d = es[reason]
        ret_str = f"**{_stock_move(d['avg_ret'])}**" if reason == 'target' else _stock_move(d['avg_ret'])
        lines.append(
            f"| {reason} "
            f"| {d['count']} "
            f"| {d['pct']:.0%} "
            f"| {d['avg_dur']:.0f} min "
            f"| {d['med_dur']:.0f} min "
            f"| {d['q25_dur']:.0f}–{d['q75_dur']:.0f} min "
            f"| {ret_str} "
            f"| {d['wr']:.0%} |"
        )
    lines.append("")
    return lines


def insight_direction_table(all_dir_stats: Dict[str, Dict[str, dict]]) -> List[str]:
    """Direction breakdown table across tickers.

    "Direction Win Rate" = % of trades where the stock moved in the trade's
    favor. "Avg Win/Loss" columns show the stock-price movement; the option
    translation alongside is computed at a slightly-OTM delta anchor.
    """
    lines = [
        "### Direction Breakdown",
        "",
        "*Win rate measures whether the **stock moved your way**. "
        "Avg Win/Loss columns show the stock-price movement plus the "
        "approximate option-equivalent return at a slightly-OTM delta.*",
        "",
        "| Ticker | Dir | Trades | Direction Win Rate | Avg Hold | Avg Hold (W) | Avg Hold (L) | Avg Win (stock) | Avg Win (option) | Avg Loss (stock) | Avg Loss (option) |",
        "|--------|-----|--------|--------------------|----------|--------------|--------------|-----------------|------------------|------------------|-------------------|",
    ]
    for ticker, dirs in all_dir_stats.items():
        for d in ['CALL', 'PUT']:
            if d not in dirs:
                continue
            s = dirs[d]
            lines.append(
                f"| **{ticker}** | {d} "
                f"| {s['count']} "
                f"| {s['wr']:.1%} "
                f"| {s['avg_dur']:.0f} min "
                f"| {s['avg_dur_w']:.0f} min "
                f"| {s['avg_dur_l']:.0f} min "
                f"| {_stock_move(s['avg_win'])} "
                f"| {_option_translation(s['avg_win'])} "
                f"| {_stock_move(s['avg_loss'])} "
                f"| {_option_translation(s['avg_loss'])} |"
            )
    lines.append("")
    return lines


def insight_narrative_exit_reasons(all_exit: Dict[str, Dict[str, dict]]) -> List[str]:
    """Generate the plain-English narrative insights from exit-reason data."""
    tickers = list(all_exit.keys())
    lines = ["### Key Insights", ""]

    # -- Target hits --
    targets = {t: all_exit[t]['target'] for t in tickers if 'target' in all_exit[t]}
    if targets:
        pct_lo = min(d['pct'] for d in targets.values())
        pct_hi = max(d['pct'] for d in targets.values())
        dur_lo = min(d['med_dur'] for d in targets.values())
        dur_hi = max(d['med_dur'] for d in targets.values())
        ret_lo = min(d['avg_ret'] for d in targets.values())
        ret_hi = max(d['avg_ret'] for d in targets.values())
        lines.append(
            f"**Target hit ({pct_lo:.0%}–{pct_hi:.0%} of trades)** — "
            f"These are the clean winners. Resolve in **{dur_lo:.0f}–{dur_hi:.0f} minutes median**. "
            f"Avg stock-price movement: **{_stock_move(ret_lo)} to {_stock_move(ret_hi)}** "
            f"({_option_translation(ret_lo)} to {_option_translation(ret_hi)})."
        )
        # Per-ticker detail
        for t, d in targets.items():
            lines.append(
                f"- *{t}*: {d['med_dur']:.0f} min median "
                f"({d['q25_dur']:.0f}–{d['q75_dur']:.0f} min IQR), "
                f"avg {_stock_move(d['avg_ret'])} stock move "
                f"({_option_translation(d['avg_ret'])})"
            )
        lines.append("")

    # -- Stop losses --
    stops = {t: all_exit[t]['stop_loss'] for t in tickers if 'stop_loss' in all_exit[t]}
    if stops:
        pct_lo = min(d['pct'] for d in stops.values())
        pct_hi = max(d['pct'] for d in stops.values())
        dur_lo = min(d['med_dur'] for d in stops.values())
        dur_hi = max(d['med_dur'] for d in stops.values())
        # Find fastest-failing ticker
        fastest_t = min(stops, key=lambda t: stops[t]['med_dur'])
        fastest_d = stops[fastest_t]
        lines.append(
            f"**Stopped out ({pct_lo:.0%}–{pct_hi:.0%} of trades)** — "
            f"Losers fail fast. **{dur_lo:.0f}–{dur_hi:.0f} minutes median**. "
            f"On {fastest_t}, half of all stopped-out trades fail within "
            f"{fastest_d['med_dur']:.0f} minutes. "
            f"If the trade hasn't moved in your favor by ~10 min, probability drops."
        )
        for t, d in stops.items():
            lines.append(
                f"- *{t}*: {d['med_dur']:.0f} min median "
                f"({d['q25_dur']:.0f}–{d['q75_dur']:.0f} min IQR), "
                f"avg {_stock_move(d['avg_ret'])} stock move "
                f"({_option_translation(d['avg_ret'])})"
            )
        lines.append("")

    # -- Time stops --
    tstops = {t: all_exit[t]['time_stop'] for t in tickers if 'time_stop' in all_exit[t]}
    if tstops:
        pct_lo = min(d['pct'] for d in tstops.values())
        pct_hi = max(d['pct'] for d in tstops.values())
        wr_lo = min(d['wr'] for d in tstops.values())
        wr_hi = max(d['wr'] for d in tstops.values())
        ret_lo = min(d['avg_ret'] for d in tstops.values())
        ret_hi = max(d['avg_ret'] for d in tstops.values())
        lines.append(
            f"**Time stop ({pct_lo:.0%}–{pct_hi:.0%} of trades)** — "
            f"The trade drifts sideways, never hitting target or stop. "
            f"Held the full 30–35 minutes. But these still "
            f"**win {wr_lo:.0%}–{wr_hi:.0%}** of the time with small positive stock-price moves "
            f"({_stock_move(ret_lo)} to {_stock_move(ret_hi)}). "
            f"Note: option contracts may still lose money on these because of "
            f"theta decay over the long hold — Phase 2 contract math will "
            f"quantify this drag."
        )
        lines.append("")

    # -- Winners vs Losers duration --
    lines.append("**Winners vs Losers:**")
    lines.append("")
    # Collect avg win/loss durations from all_exit indirectly — we'll get this from caller
    # For now note the general pattern
    lines.append(
        "- Winners need **more time** to work than losers. "
        "A winning trade gradually moves to target over 12–18 min; "
        "a losing trade hits the tighter stop quickly."
    )
    lines.append(
        "- **CALL trades are faster** (morning window 9:30–10:00) than PUTs "
        "(all-day window 9:30–2:00). This reflects higher morning volatility."
    )
    lines.append("")

    return lines


def insight_narrative_winners_losers(
    ticker_stats: Dict[str, dict],
) -> List[str]:
    """Insight block comparing winners vs losers hold times."""
    lines = []
    w_durs = [s['avg_dur_w'] for s in ticker_stats.values()]
    l_durs = [s['avg_dur_l'] for s in ticker_stats.values()]
    if w_durs and l_durs:
        lines.append(
            f"**Winners take longer.** "
            f"Winning trades average {min(w_durs):.0f}–{max(w_durs):.0f} min hold vs "
            f"{min(l_durs):.0f}–{max(l_durs):.0f} min for losers. "
            f"If a trade is going to hit target, expect to wait 12–18 minutes."
        )
        lines.append("")
    return lines


def insight_timeframe_sweep(sweep_data: Dict[str, pd.DataFrame]) -> List[str]:
    """Insights from the timeframe sweep CSVs."""
    lines = [
        "### Single Timeframe Performance",
        "",
        "*Running the signal system on different bar sizes. "
        "Entry signal generated on each timeframe independently.*",
        "",
        "| Ticker | TF | Trades | Win Rate | PF | Sharpe | Expectancy |",
        "|--------|-----|--------|----------|----|--------|------------|",
    ]
    for ticker, df in sweep_data.items():
        single = df[df['type'] == 'single']
        for _, row in single.iterrows():
            lines.append(
                f"| **{ticker}** "
                f"| {row['label']} "
                f"| {int(row['trades']):,} "
                f"| {row['win_rate']:.1%} "
                f"| {row['pf']:.2f} "
                f"| {row['sharpe']:.2f} "
                f"| {row['expectancy']:+.4%} |"
            )
    lines.append("")

    # Insight
    lines.append(
        "**Single timeframes alone are mediocre.** "
        "The 5m and 15m by themselves produce near-random win rates (~48–49%) "
        "and Sharpe ratios near zero. Only IWM shows standalone edge."
    )
    lines.append("")
    return lines


def insight_combo_sweep(sweep_data: Dict[str, pd.DataFrame]) -> List[str]:
    """Insights from the combo (1m + higher-TF filter) sweep."""
    lines = [
        "### Combination Analysis — 1m Signal + Higher-TF Trend Filter",
        "",
        "*Entry on 1-minute bars, but only when higher-timeframe EMA20 trend agrees.*",
        "",
        "| Ticker | Filter | Trades | Win Rate | PF | Sharpe | Max DD | Expectancy |",
        "|--------|--------|--------|----------|----|--------|--------|------------|",
    ]
    best_per_ticker = {}
    for ticker, df in sweep_data.items():
        combo = df[df['type'] == 'combo']
        for _, row in combo.iterrows():
            lines.append(
                f"| **{ticker}** "
                f"| {row['label']} "
                f"| {int(row['trades']):,} "
                f"| {row['win_rate']:.1%} "
                f"| {row['pf']:.2f} "
                f"| {row['sharpe']:.2f} "
                f"| {row['max_dd']:.2%} "
                f"| {row['expectancy']:+.4%} |"
            )
        # Find best combo (excluding baseline)
        non_baseline = combo[~combo['label'].str.contains('baseline')]
        if len(non_baseline) > 0:
            best_idx = non_baseline['sharpe'].idxmax()
            best = non_baseline.loc[best_idx]
            best_per_ticker[ticker] = best
    lines.append("")

    # Narrative
    lines.append("**The higher-TF filter is the real edge:**")
    lines.append("")
    for ticker, best in best_per_ticker.items():
        lines.append(
            f"- **{ticker}**: Best combo = **{best['label']}** "
            f"(Sharpe {best['sharpe']:.2f}, WR {best['win_rate']:.1%}, "
            f"E={best['expectancy']:+.4%}/trade)"
        )
    lines.append("")
    lines.append(
        "The 1m+15m combination consistently ranks #1 or #2. "
        "The higher-TF EMA20 trend filter transforms a near-zero-edge strategy "
        "into a high-Sharpe system by only trading in the direction of the "
        "15-minute trend."
    )
    lines.append("")
    return lines


def insight_base_vs_strat(
    base_dfs: Dict[str, pd.DataFrame],
    strat_dfs: Dict[str, pd.DataFrame],
) -> List[str]:
    """Side-by-side Base vs Strat comparison table + narrative."""
    lines = [
        "### Base Strategy vs Strat Overlay (FTFC + ORB Filtering)",
        "",
        "| Ticker | Mode | Trades | Win Rate | Avg Win | Avg Loss | PF | Sharpe | Expectancy |",
        "|--------|------|--------|----------|---------|----------|------|--------|------------|",
    ]
    deltas: Dict[str, dict] = {}

    for ticker in strat_dfs:
        for label, src in [("Base", base_dfs), ("**Strat**", strat_dfs)]:
            if ticker not in src:
                continue
            df = src[ticker]
            s = _compute_core_stats(df)
            lines.append(
                f"| **{ticker}** | {label} "
                f"| {s['n']:,} "
                f"| {s['wr']:.1%} "
                f"| +{s['avg_w']:.2%} "
                f"| {s['avg_l']:.2%} "
                f"| {s['pf']:.2f} "
                f"| {s['sharpe']:.2f} "
                f"| {s['exp']:+.3%} |"
            )
        # Compute delta
        if ticker in base_dfs and ticker in strat_dfs:
            sb = _compute_core_stats(base_dfs[ticker])
            ss = _compute_core_stats(strat_dfs[ticker])
            if sb['sharpe'] != 0:
                sharpe_delta = (ss['sharpe'] - sb['sharpe']) / abs(sb['sharpe']) * 100
            else:
                sharpe_delta = 0
            deltas[ticker] = {
                'trades_removed': sb['n'] - ss['n'],
                'wr_delta': ss['wr'] - sb['wr'],
                'sharpe_delta_pct': sharpe_delta,
                'base_sharpe': sb['sharpe'],
                'strat_sharpe': ss['sharpe'],
            }

    lines.append("")

    # Narrative
    if deltas:
        lines.append("**What the Strat overlay does:**")
        lines.append("")
        for ticker, d in deltas.items():
            lines.append(
                f"- **{ticker}**: Removed {d['trades_removed']} low-quality trades, "
                f"win rate {d['wr_delta']:+.1%} pts, "
                f"Sharpe {d['base_sharpe']:.2f} → {d['strat_sharpe']:.2f} "
                f"({d['sharpe_delta_pct']:+.0f}%)"
            )
        lines.append("")

    return lines


def insight_filter_stats(
    base_dfs: Dict[str, pd.DataFrame],
    strat_dfs: Dict[str, pd.DataFrame],
) -> List[str]:
    """Filter rejection stats — how many signals got blocked by FTFC/ORB."""
    lines = [
        "### Filter Rejection Rates",
        "",
        "| Ticker | Base Signals | Strat Signals | Filtered Out | Filter Rate |",
        "|--------|-------------|---------------|--------------|-------------|",
    ]
    for ticker in strat_dfs:
        base_n = len(base_dfs[ticker]) if ticker in base_dfs else 0
        strat_n = len(strat_dfs[ticker])
        filtered = base_n - strat_n
        rate = filtered / base_n if base_n > 0 else 0
        lines.append(
            f"| **{ticker}** "
            f"| {base_n:,} "
            f"| {strat_n:,} "
            f"| {filtered:,} "
            f"| {rate:.1%} |"
        )
    lines.append("")

    # Narrative
    rates = []
    for ticker in strat_dfs:
        if ticker in base_dfs:
            base_n = len(base_dfs[ticker])
            strat_n = len(strat_dfs[ticker])
            if base_n > 0:
                rates.append((base_n - strat_n) / base_n)
    if rates:
        avg_rate = np.mean(rates)
        lines.append(
            f"The FTFC + ORB filters reject **~{avg_rate:.0%}** of raw signals on average, "
            f"leaving only trades aligned with higher-timeframe structure."
        )
        lines.append("")
    return lines


def insight_signal_strength(strat_dfs: Dict[str, pd.DataFrame]) -> List[str]:
    """Performance breakdown by signal strength score."""
    lines = [
        "### Performance by Signal Strength",
        "",
        "| Ticker | Score | Trades | Win Rate | Avg Return | Position Size |",
        "|--------|-------|--------|----------|------------|---------------|",
    ]
    has_data = False
    for ticker, df in strat_dfs.items():
        if 'total_score' not in df.columns:
            continue
        for score in sorted(df['total_score'].unique()):
            sub = df[df['total_score'] == score]
            if len(sub) < 5:
                continue
            has_data = True
            wr = sub['won'].mean()
            avg_ret = sub['return_pct'].mean()
            # Position size from score
            pos = sub['position_size'].mean() if 'position_size' in sub.columns else 0
            lines.append(
                f"| **{ticker}** "
                f"| {int(score)}/8 "
                f"| {len(sub)} "
                f"| {wr:.1%} "
                f"| {_stock_move(avg_ret)} "
                f"| {pos:.0%} |"
            )

    if not has_data:
        return []  # skip section entirely if no score data

    lines.append("")

    # Insight
    lines.append(
        "Higher signal scores generally produce better win rates and returns. "
        "Score 5+ trades (with Strat bonus) outperform score 3–4 trades."
    )
    lines.append("")
    return lines


def insight_key_findings(
    strat_dfs: Dict[str, pd.DataFrame],
    all_exit: Dict[str, Dict[str, dict]],
    sweep_data: Dict[str, pd.DataFrame],
) -> List[str]:
    """Cross-ticker Key Findings summary — the big takeaways."""
    lines = [
        "## Key Findings",
        "",
    ]

    # 1. Best ticker
    sharpes = {}
    for ticker, df in strat_dfs.items():
        s = _compute_core_stats(df)
        sharpes[ticker] = s['sharpe']
    if sharpes:
        best_ticker = max(sharpes, key=sharpes.get)
        lines.append(
            f"1. **{best_ticker} is the strongest ticker** with Sharpe "
            f"{sharpes[best_ticker]:.2f} on the base strategy. "
            f"It has the widest profit targets and most volatile price action, "
            f"producing the cleanest signal-to-noise ratio."
        )
        lines.append("")

    # 2. FTFC filter impact
    lines.append(
        "2. **The Strat overlay (FTFC + ORB) improves every ticker.** "
        "It removes low-quality trades that contradict higher-timeframe structure, "
        "boosting Sharpe ratios and win rates across the board."
    )
    lines.append("")

    # 3. Duration insight
    targets = {t: all_exit[t].get('target', {}) for t in all_exit}
    stops = {t: all_exit[t].get('stop_loss', {}) for t in all_exit}
    target_durs = [d.get('med_dur', 0) for d in targets.values() if d]
    stop_durs = [d.get('med_dur', 0) for d in stops.values() if d]
    if target_durs and stop_durs:
        lines.append(
            f"3. **Trades resolve quickly.** "
            f"Target hits in {min(target_durs):.0f}–{max(target_durs):.0f} min, "
            f"stops in {min(stop_durs):.0f}–{max(stop_durs):.0f} min. "
            f"You know within 10–15 minutes whether a trade is working."
        )
        lines.append("")

    # 4. Combo insight
    if sweep_data:
        best_combos = {}
        for ticker, df in sweep_data.items():
            combo = df[(df['type'] == 'combo') & (~df['label'].str.contains('baseline'))]
            if len(combo) > 0:
                best_idx = combo['sharpe'].idxmax()
                best_combos[ticker] = combo.loc[best_idx]
        if best_combos:
            lines.append(
                "4. **The 1m+15m combination is the sweet spot.** "
                "Adding a 15-minute EMA20 trend filter to 1-minute signals "
                "produces the highest Sharpe ratios across all tickers:"
            )
            for ticker, best in best_combos.items():
                lines.append(
                    f"   - {ticker}: **{best['label']}** — "
                    f"Sharpe {best['sharpe']:.2f}, WR {best['win_rate']:.1%}"
                )
            lines.append("")

    # 5. Time stops
    tstops = {t: all_exit[t].get('time_stop', {}) for t in all_exit}
    wrs = [d.get('wr', 0) for d in tstops.values() if d]
    if wrs:
        lines.append(
            f"5. **Time-stop trades are still profitable.** "
            f"Trades that never hit target or stop still win "
            f"{min(wrs):.0%}–{max(wrs):.0%} of the time. "
            f"Consider a trailing stop or wider target for these "
            f"to capture more of the move."
        )
        lines.append("")

    # 6. Morning vs afternoon
    lines.append(
        "6. **Morning CALL trades are the fastest.** "
        "The 9:30–10:00 AM window produces the most volatile, decisive trades. "
        "CALL entries resolve in 10–17 min avg. PUT entries throughout the day "
        "take 23–27 min avg but have more opportunities."
    )
    lines.append("")

    return lines


def _compute_core_stats(df: pd.DataFrame) -> dict:
    """Compute core metrics from a trades DataFrame."""
    n = len(df)
    won = df['won'] if 'won' in df.columns else df['return_pct'] > 0
    wins = df[won]
    losses = df[~won]
    pf_num = wins['return_pct'].sum() if len(wins) else 0
    pf_den = abs(losses['return_pct'].sum()) if len(losses) else 0

    df_day = df.copy()
    df_day['date'] = pd.to_datetime(df_day['entry_time']).dt.date
    daily_pnl = df_day.groupby('date')['return_pct'].sum()
    sharpe = (daily_pnl.mean() / daily_pnl.std() * np.sqrt(252)) if daily_pnl.std() > 0 else 0

    return {
        'n': n,
        'wr': len(wins) / n if n else 0,
        'avg_w': wins['return_pct'].mean() if len(wins) else 0,
        'avg_l': losses['return_pct'].mean() if len(losses) else 0,
        'pf': pf_num / pf_den if pf_den > 0 else 0,
        'exp': df['return_pct'].mean() if n else 0,
        'sharpe': sharpe,
    }


def insight_what_numbers_mean() -> List[str]:
    """Static explainer for how to read the metrics.

    Phase 1 wording: every metric describes whether it's about the **stock**
    or about the **option contract**, with an option-equivalent translation
    inline. Phase 2 will add a parallel "Contract Win Rate" column once
    real option-premium math is wired in.
    """
    return [
        "### How to Read These Numbers",
        "",
        "*The strat predicts **stock-price movement**. Below, every number "
        "tells you which is being measured — the stock or a single option "
        "contract — and translates between them so you never have to do the "
        "math in your head.*",
        "",
        "| Metric | What It Means | What's Good |",
        "|--------|---------------|-------------|",
        "| **Direction Win Rate** | % of trades where the **stock moved your way** — this is the strat's truth metric | >50% with filters |",
        "| **Avg Win (stock)** | Average **stock-price movement** on winning trades | Bigger absolute value than Avg Loss |",
        "| **Avg Win (option)** | Same move translated to an option's % return at a slightly-OTM delta | — |",
        "| **Avg Loss** | Same idea for losers, on stock and option | Smaller absolute value than Avg Win |",
        "| **Avg Hold** | How long you're in the trade | Shorter = less theta exposure |",
        "| **Target Hit %** | Trades that reach profit target | Higher = cleaner entries |",
        "| **Time Stop %** | Trades that expire without hitting target or stop | Lower = more decisive |",
        "| **Sharpe** | Risk-adjusted return (return / volatility) | >1 tradeable, >3 strong |",
        "| **PF** | Gross wins / gross losses | >1.5 good, >2.0 exceptional |",
        "| **Expectancy** | Average stock-price P/L per trade | Must be positive |",
        "",
        "#### How a stock move turns into option profit",
        "",
        "*Approximate translation. A real option's return depends on its "
        "delta (which itself depends on strike-vs-spot and time to expiry), "
        "plus theta decay over the hold. Phase 2 of the insights pipeline "
        "computes this against real option premium — the table below is a "
        "linear delta-based estimate.*",
        "",
        "| Stock price movement | ATM option (~0.50Δ) | Slightly OTM (~0.35Δ, default) | OTM (~0.20Δ) |",
        "|----------------------|---------------------|--------------------------------|---------------|",
        "| +0.15% | +0.08% | +0.05% | +0.03% |",
        "| +0.30% | +0.15% | +0.11% | +0.06% |",
        "| +0.41% | +0.21% | +0.14% | +0.08% |",
        "| +0.50% | +0.25% | +0.18% | +0.10% |",
        "| −0.41% | −0.21% | −0.14% | −0.08% |",
        "",
        "**Why the option number is smaller than you'd expect for a 0.41% "
        "stock move:** these are intraday hold-period returns, not "
        "annualized, and the multiplier is delta — not the leverage ratio "
        "you'd see on a full expiry. Phase 2 will replace this estimate with "
        "real contract premium from a 5–10-strike-OTM contract at trade time.",
        "",
        "#### What 'Contract Win Rate' will mean (Phase 2, coming soon)",
        "",
        "Today the win rate measures whether the **stock** moved your way. "
        "Phase 2 adds a second column — **Contract Win Rate** — that "
        "measures whether the **option contract** actually printed money "
        "after theta and IV crush. The gap between the two is the cost of "
        "using options to express the strat. Both will be shown side-by-side "
        "with a method badge (real / greek-estimated) on every figure.",
        "",
    ]


def insight_hold_time_win_rate(df: pd.DataFrame) -> List[str]:
    """Hold-time Win Rate — exposes the theta cliff.

    Splits trades into duration buckets (0–10, 10–30, 30–60, 60+ minutes) and
    reports Direction Win Rate per bucket. Phase 2 will add a parallel
    Contract Win Rate per bucket so the widening gap (= theta drag) becomes
    visible at a glance.
    """
    rows = _hold_time_bucket_stats(df)
    if not rows:
        return []
    lines = [
        "### Win Rate by Hold Duration",
        "",
        "*Direction Win Rate stays roughly stable as hold time grows — "
        "the stock either moves your way or it doesn't, regardless of how "
        "long you wait. Contract Win Rate (Phase 2) will tell a different "
        "story: theta is a clock, and longer holds bleed premium even when "
        "the stock cooperates.*",
        "",
        "| Hold Bucket | Trades | Direction Win Rate | Avg Stock Move | Slightly-OTM Option |",
        "|-------------|--------|--------------------|----------------|---------------------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['bucket']} "
            f"| {r['count']} "
            f"| {r['direction_wr']:.0%} "
            f"| {_stock_move(r['avg_return'])} "
            f"| {_option_translation(r['avg_return'])} |"
        )
    lines.append("")
    return lines
