#!/usr/bin/env python3
"""
Phase 6: Beginner's Playbook — Per-Ticker Decision Cards

Generates 12 decision cards per ticker (36 total) in plain English "If-Then" format.
Each card is populated with actual data from Phases 1-5.

Output: reports/phase6_playbook_{ticker}.md + reports/phase6_playbook_combined.md
"""

import sys
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.analysis.shared_utils import (
    TICKERS, REPORTS_DIR,
    load_ticker_1m, enrich_with_indicators, classify_strat_series,
    build_multi_timeframe_dict,
    md_header, md_table, fmt_pct, fmt_bps, fmt_num, save_report,
    timestamp_str, sample_size_label, progress,
    IndicatorConfig, ExitConfig,
)


# ---------------------------------------------------------------------------
# Card data computation
# ---------------------------------------------------------------------------

def compute_card_stats(df: pd.DataFrame, labels: pd.Series,
                       pattern_mask: pd.Series, direction: str,
                       target_bps: float, stop_bps: float,
                       time_stop_min: int = 30) -> Dict:
    """Compute statistics for a single playbook card."""
    close = df['Close'] if 'Close' in df.columns else df['Last']
    next_return = close.pct_change().shift(-1) * 10000

    n = pattern_mask.sum()
    if n == 0:
        return {'count': 0}

    if direction == 'CALL':
        trade_return = next_return[pattern_mask]
        win_mask = trade_return > 0
    else:
        trade_return = -next_return[pattern_mask]
        win_mask = trade_return > 0

    win_rate = win_mask.mean() if len(win_mask) > 0 else 0
    avg_return = trade_return.mean() if len(trade_return) > 0 else 0

    # Forward returns at different horizons
    fwd_returns = {}
    for p in [5, 10, 15, 30]:
        fwd = close.pct_change(p).shift(-p) * 10000
        if direction == 'PUT':
            fwd = -fwd
        vals = fwd[pattern_mask].dropna()
        fwd_returns[p] = vals.mean() if len(vals) > 0 else 0

    # MFE/MAE over 30 bars
    indices = df.index[pattern_mask]
    mfe_list, mae_list = [], []
    for idx in indices:
        pos = df.index.get_loc(idx)
        end = min(pos + 31, len(df))
        if end <= pos + 1:
            continue
        future = close.iloc[pos:end]
        ep = close.iloc[pos]
        if ep <= 0:
            continue
        if direction == 'CALL':
            rets = (future - ep) / ep * 10000
        else:
            rets = (ep - future) / ep * 10000
        mfe_list.append(rets.max())
        mae_list.append(rets.min())

    return {
        'count': int(n),
        'win_rate': win_rate,
        'avg_return_bps': avg_return,
        'fwd_5': fwd_returns.get(5, 0),
        'fwd_10': fwd_returns.get(10, 0),
        'fwd_15': fwd_returns.get(15, 0),
        'fwd_30': fwd_returns.get(30, 0),
        'avg_mfe': np.mean(mfe_list) if mfe_list else 0,
        'avg_mae': np.mean(mae_list) if mae_list else 0,
        'confidence': sample_size_label(int(n)),
    }


# ---------------------------------------------------------------------------
# Card definitions
# ---------------------------------------------------------------------------

def generate_card(card_num: int, title: str, ticker: str,
                  visual_setup: str, checklist: List[str],
                  direction: str, stats: Dict,
                  target_pct: str, stop_pct: str,
                  hold_time: str, warnings: List[str],
                  ticker_notes: List[str]) -> str:
    """Generate a single playbook card in markdown."""

    card = f"\n---\n\n"
    card += md_header(f"{ticker} CARD {card_num}: {title}", 3)

    # What you see
    card += "**WHAT YOU SEE ON THE CHART:**\n"
    card += visual_setup + "\n\n"

    # Checklist
    card += "**WHAT TO CHECK:**\n"
    for item in checklist:
        card += f"  - [ ] {item}\n"
    card += "\n"

    # Entry
    if stats['count'] > 0:
        card += f"**IF ALL CONFIRMED -> {direction} ENTRY**\n"
        card += f"  - Confidence: {stats['confidence']} (n={stats['count']:,})\n"
        card += f"  - Historical win rate: {stats['win_rate']:.1%}\n"
        card += f"  - Avg return: {fmt_bps(stats['avg_return_bps'])}\n"
        card += f"  - Target: {target_pct}\n"
        card += f"  - Stop: {stop_pct}\n"
        card += f"  - Expected hold: {hold_time}\n"
        card += f"  - Avg MFE: {fmt_bps(stats['avg_mfe'])}\n"
        card += f"  - Avg MAE: {fmt_bps(stats['avg_mae'])}\n\n"
    else:
        card += f"**IF ALL CONFIRMED -> {direction} ENTRY**\n"
        card += f"  - Insufficient data for this pattern on {ticker}\n\n"

    # Warnings
    card += "**REVERSAL WARNING SIGNS (exit early):**\n"
    for w in warnings:
        card += f"  - {w}\n"
    card += "\n"

    # Ticker notes
    card += f"**{ticker}-SPECIFIC NOTES:**\n"
    for note in ticker_notes:
        card += f"  - {note}\n"
    card += "\n"

    return card


def build_all_cards(ticker: str, df: pd.DataFrame, labels: pd.Series) -> str:
    """Build all 12 playbook cards for a ticker."""
    report = ""
    ind = IndicatorConfig()
    rsi_col = ind.rsi_col
    close = df['Close'] if 'Close' in df.columns else df['Last']

    rsi = df.get(rsi_col, pd.Series(50, index=df.index))
    vwap_pos = df.get('Price_vs_VWAP', pd.Series(0, index=df.index))
    ema_cross = df.get('EMA_Cross', pd.Series(0, index=df.index))
    orb_trend = df.get('ORB_30m_Trend', pd.Series(0, index=df.index))
    stoch_k = df.get('StochRSI_K', pd.Series(50, index=df.index))
    rvol = df.get('RVOL', pd.Series(1.0, index=df.index))

    prev = labels.shift(1)
    prev2 = labels.shift(2)
    next_label = labels.shift(-1)

    # Ticker-specific defaults
    if ticker == 'IWM':
        call_target, put_target = '+0.30%', '+0.38%'
        call_stop, put_stop = '-0.15%', '-0.20%'
        hold_time = '10-15 min'
    elif ticker == 'SPY':
        call_target, put_target = '+0.15%', '+0.20%'
        call_stop, put_stop = '-0.10%', '-0.12%'
        hold_time = '12-18 min'
    else:  # QQQ
        call_target, put_target = '+0.25%', '+0.25%'
        call_stop, put_stop = '-0.12%', '-0.12%'
        hold_time = '10-15 min'

    # --- CARD 1: Bullish Continuation (2U-2U-2U) ---
    mask = (prev2 == '2U') & (prev == '2U') & (labels == '2U')
    stats = compute_card_stats(df, labels, mask, 'CALL', 30, 15)
    report += generate_card(
        1, "Bullish Continuation (2U-2U-2U)", ticker,
        "  * Daily bar is 2U (higher high, higher low)\n"
        "  * 15m bar is 2U\n"
        "  * 1m shows: 2U -> 2U -> 2U (three consecutive bullish bars)",
        [
            f"RSI between 40-65 (not overbought yet)",
            "Price above VWAP",
            f"Price above EMA{ind.ema_fast_period}",
            "ORB 30m trend is bullish",
            f"EMA{ind.ema_fast_period} > EMA{ind.ema_mid_period} (bullish cross)",
        ],
        'CALL', stats, call_target, call_stop, hold_time,
        [
            "RSI crosses above 75 -> take profit",
            "1m bar prints 2D -> tighten stop to breakeven",
            "RVOL drops below 0.8 -> momentum fading",
            "Price hits prev day/week high -> resistance",
        ],
        _get_ticker_notes(ticker, 'bullish_continuation'),
    )

    # --- CARD 2: Bearish Continuation (2D-2D-2D) ---
    mask = (prev2 == '2D') & (prev == '2D') & (labels == '2D')
    stats = compute_card_stats(df, labels, mask, 'PUT', 38, 20)
    report += generate_card(
        2, "Bearish Continuation (2D-2D-2D)", ticker,
        "  * Daily bar is 2D (lower high, lower low)\n"
        "  * 15m bar is 2D\n"
        "  * 1m shows: 2D -> 2D -> 2D (three consecutive bearish bars)",
        [
            "RSI between 35-60 (not oversold yet)",
            "Price below VWAP",
            f"Price below EMA{ind.ema_fast_period}",
            "ORB 30m trend is bearish",
            f"EMA{ind.ema_fast_period} < EMA{ind.ema_mid_period} (bearish cross)",
        ],
        'PUT', stats, put_target, put_stop, hold_time,
        [
            "RSI crosses below 25 -> take profit",
            "1m bar prints 2U -> tighten stop to breakeven",
            "RVOL drops below 0.8 -> selling pressure fading",
            "Price hits prev day/week low -> support",
        ],
        _get_ticker_notes(ticker, 'bearish_continuation'),
    )

    # --- CARD 3: Bullish Reversal 2-1-2 ---
    mask = (prev2 == '2D') & (prev == '1') & (labels == '2U')
    stats = compute_card_stats(df, labels, mask, 'CALL', 30, 15)
    report += generate_card(
        3, "Bullish Reversal (2D-1-2U)", ticker,
        "  * Previous bars: 2D (bearish) -> 1 (inside bar compression)\n"
        "  * Current bar: Breaking above the inside bar's high (2U)",
        [
            "RSI < 45 (was oversold from the 2D move)",
            "Price at or near support level (prev day low, VWAP, order block)",
            "StochRSI was oversold (< 20), now turning up",
            "Volume confirming (RVOL > 1.0)",
        ],
        'CALL', stats, call_target, call_stop, hold_time,
        [
            "If breakout fails and price drops back inside the 1 bar -> exit immediately",
            "RSI fails to cross above 50 -> weak reversal",
            "No volume on breakout -> likely false breakout",
        ],
        _get_ticker_notes(ticker, 'bullish_reversal'),
    )

    # --- CARD 4: Bearish Reversal 2-1-2 ---
    mask = (prev2 == '2U') & (prev == '1') & (labels == '2D')
    stats = compute_card_stats(df, labels, mask, 'PUT', 38, 20)
    report += generate_card(
        4, "Bearish Reversal (2U-1-2D)", ticker,
        "  * Previous bars: 2U (bullish) -> 1 (inside bar compression)\n"
        "  * Current bar: Breaking below the inside bar's low (2D)",
        [
            "RSI > 55 (was overbought from the 2U move)",
            "Price at or near resistance (prev day high, upper BB)",
            "StochRSI was overbought (> 80), now turning down",
            "Volume confirming (RVOL > 1.0)",
        ],
        'PUT', stats, put_target, put_stop, hold_time,
        [
            "If price recovers back above inside bar's low -> exit immediately",
            "RSI fails to cross below 50 -> weak reversal",
            "No volume on breakdown -> likely false breakdown",
        ],
        _get_ticker_notes(ticker, 'bearish_reversal'),
    )

    # --- CARD 5: Outside Bar Breakout (Type 3) ---
    mask = labels == '3'
    bullish_3 = mask & (close > close.shift(1))
    stats_bull = compute_card_stats(df, labels, bullish_3, 'CALL', 30, 15)
    report += generate_card(
        5, "Outside Bar Breakout (Type 3 Bullish)", ticker,
        "  * Current bar is Type 3 (higher high AND lower low than prev bar)\n"
        "  * Close is above previous bar's close (bullish resolution)",
        [
            "RSI between 40-60 (room to run)",
            "Close in upper half of the bar's range",
            "Volume above average (RVOL > 1.2)",
            "Higher timeframe supports the direction",
        ],
        'CALL', stats_bull, call_target, call_stop, hold_time,
        [
            "If next bar is Type 1 (inside) -> tighten stop",
            "Price drops below midpoint of the 3 bar -> exit",
            "Outside bars often exhaust moves -> be ready for reversal",
        ],
        _get_ticker_notes(ticker, 'outside_bar'),
    )

    # --- CARD 6: ORB Breakout Bullish ---
    mask = (orb_trend == 1) & (labels.isin(['2U', '3']))
    stats = compute_card_stats(df, labels, mask, 'CALL', 30, 15)
    report += generate_card(
        6, "ORB Breakout — Bullish", ticker,
        "  * Price has broken above 30m Opening Range High\n"
        "  * Current Strat bar confirms: 2U or 3",
        [
            "RSI not overbought (< 70)",
            "Price above VWAP",
            f"EMA{ind.ema_fast_period} > EMA{ind.ema_mid_period}",
            "RVOL > 1.0 (volume confirming breakout)",
            "At least 30 min after market open",
        ],
        'CALL', stats, call_target, call_stop, hold_time,
        [
            "Price returns inside ORB range -> failed breakout, exit",
            "Declining volume on continuation -> fade risk",
            "Approaching prev day/week high -> resistance ahead",
        ],
        _get_ticker_notes(ticker, 'orb_breakout'),
    )

    # --- CARD 7: ORB Breakout Bearish ---
    mask = (orb_trend == -1) & (labels.isin(['2D', '3']))
    stats = compute_card_stats(df, labels, mask, 'PUT', 38, 20)
    report += generate_card(
        7, "ORB Breakout — Bearish", ticker,
        "  * Price has broken below 30m Opening Range Low\n"
        "  * Current Strat bar confirms: 2D or 3",
        [
            "RSI not oversold (> 30)",
            "Price below VWAP",
            f"EMA{ind.ema_fast_period} < EMA{ind.ema_mid_period}",
            "RVOL > 1.0",
            "At least 30 min after market open",
        ],
        'PUT', stats, put_target, put_stop, hold_time,
        [
            "Price returns inside ORB range -> failed breakdown, exit",
            "RSI reaching extreme oversold -> bounce risk",
            "Approaching prev day/week low -> support ahead",
        ],
        _get_ticker_notes(ticker, 'orb_breakdown'),
    )

    # --- CARD 8: ORB Failure / Mean Reversion ---
    # Detect bars that went above ORB high then came back within
    if 'ORB_30m_High' in df.columns and 'ORB_30m_Low' in df.columns:
        was_above = close.shift(1) > df['ORB_30m_High']
        now_within = (close <= df['ORB_30m_High']) & (close >= df['ORB_30m_Low'])
        mask = was_above & now_within & (labels == '2D')
    else:
        mask = pd.Series(False, index=df.index)
    stats = compute_card_stats(df, labels, mask, 'PUT', 20, 15)
    report += generate_card(
        8, "ORB Failure / Mean Reversion", ticker,
        "  * Price broke above ORB high, then FAILED and returned inside range\n"
        "  * Current Strat shows 2D (confirming the failure)",
        [
            "RSI was elevated (> 60) at breakout",
            "Volume declining on the failed breakout",
            "Strat shows reversal (2D after 2U or 3)",
            "VWAP is nearby (target)",
        ],
        'PUT', stats, put_target, put_stop, '8-15 min',
        [
            "Price re-breaks ORB high -> failure of the failure, exit",
            "Price hits ORB mid and stalls -> take partial profit",
            "RSI crosses below 40 -> full reversal, let it run",
        ],
        _get_ticker_notes(ticker, 'orb_failure'),
    )

    # --- CARD 9: Support Bounce ---
    if 'At_Prev_Day_Low' in df.columns:
        mask = (df['At_Prev_Day_Low'] == 1) & (labels == '2U')
    else:
        mask = pd.Series(False, index=df.index)
    stats = compute_card_stats(df, labels, mask, 'CALL', 30, 15)
    report += generate_card(
        9, "Support Bounce (at Historical Level)", ticker,
        "  * Price is at previous day's low (support level)\n"
        "  * Current bar is 2U (bouncing off support)",
        [
            "RSI < 40 (oversold at support)",
            "StochRSI crossed above 20 (turning up)",
            "Order block nearby (institutional interest)",
            "Volume increasing on bounce",
        ],
        'CALL', stats, call_target, call_stop, hold_time,
        [
            "Price breaks below prev day low -> support failed, exit immediately",
            "No follow-through (next bar is 1 or 2D) -> tighten stop",
            "RSI fails to clear 50 -> weak bounce",
        ],
        _get_ticker_notes(ticker, 'support_bounce'),
    )

    # --- CARD 10: Resistance Rejection ---
    if 'At_Prev_Day_High' in df.columns:
        mask = (df['At_Prev_Day_High'] == 1) & (labels == '2D')
    else:
        mask = pd.Series(False, index=df.index)
    stats = compute_card_stats(df, labels, mask, 'PUT', 38, 20)
    report += generate_card(
        10, "Resistance Rejection (at Historical Level)", ticker,
        "  * Price is at previous day's high (resistance level)\n"
        "  * Current bar is 2D (rejecting off resistance)",
        [
            "RSI > 60 (overbought at resistance)",
            "StochRSI crossed below 80 (turning down)",
            "Volume declining on approach to resistance",
            "Bearish divergence (price higher, RSI lower)",
        ],
        'PUT', stats, put_target, put_stop, hold_time,
        [
            "Price breaks above prev day high -> resistance cleared, exit",
            "No follow-through on rejection -> tighten stop",
            "RSI fails to drop below 50 -> weak rejection",
        ],
        _get_ticker_notes(ticker, 'resistance_rejection'),
    )

    # --- CARD 11: Order Block Test ---
    if 'Order_Block_Test' in df.columns:
        # Bullish: testing order block from above
        mask = (df['Order_Block_Test'] == 1) & (df.get('Order_Block_Position', 0) >= 0) & (labels == '2U')
    else:
        mask = pd.Series(False, index=df.index)
    stats = compute_card_stats(df, labels, mask, 'CALL', 30, 15)
    report += generate_card(
        11, "Order Block Test (Institutional Zone)", ticker,
        "  * Price is testing an identified order block zone\n"
        "  * Current bar is 2U (bouncing off the institutional zone)",
        [
            "Price is at order block high or low boundary",
            "RSI between 35-55 (not extreme)",
            "Volume increasing at the zone",
            "Strat shows reversal or continuation with direction",
        ],
        'CALL', stats, call_target, call_stop, hold_time,
        [
            "Price slices through the order block cleanly -> zone invalidated, exit",
            "No bounce within 5 bars -> zone may be broken",
            "Multiple tests weaken the zone -> less reliable each time",
        ],
        _get_ticker_notes(ticker, 'order_block'),
    )

    # --- CARD 12: FTFC Maximum Conviction ---
    # All timeframes aligned (approximate: EMA cross + ORB trend + 2U or 2D)
    bull_ftfc = (ema_cross == 1) & (orb_trend == 1) & (labels == '2U') & (rsi.between(40, 65))
    stats = compute_card_stats(df, labels, bull_ftfc, 'CALL', 30, 15)
    report += generate_card(
        12, "FTFC Maximum Conviction (All Aligned)", ticker,
        "  * ALL timeframes showing the same direction\n"
        "  * EMAs bullish, ORB bullish, Strat 2U, RSI healthy\n"
        "  * This is the STRONGEST possible setup",
        [
            f"EMA{ind.ema_fast_period} > EMA{ind.ema_mid_period} (bullish cross)",
            "ORB 30m trend is bullish",
            "Current Strat bar is 2U",
            "RSI between 40-65 (healthy, not overbought)",
            "Price above VWAP",
            "RVOL > 1.0 (volume confirms)",
        ],
        'CALL', stats, call_target, call_stop, hold_time,
        [
            "Any single alignment breaks -> reduce size",
            "RSI > 75 -> take profit regardless",
            "RVOL drops below 0.8 -> conviction weakening",
            "Losing money after 5 min in this setup -> something's wrong, exit",
        ],
        _get_ticker_notes(ticker, 'ftfc_conviction'),
    )

    return report


def _get_ticker_notes(ticker: str, card_type: str) -> List[str]:
    """Return ticker-specific notes for each card type."""
    notes = {
        'IWM': {
            'bullish_continuation': [
                "IWM mean-reverts more than SPY/QQQ — continuation is less reliable",
                "If RSI > 70, reversal risk is ELEVATED — IWM reverses hard",
                "Best combo: 1m+15m (Sharpe 9.31)",
                "IWM has widest targets but also widest stops",
            ],
            'bearish_continuation': [
                "IWM PUTs win more often (43.4%) than CALLs (38.5%)",
                "72% of IWM trades are PUTs — natural bearish lean",
                "Losers fail fast: 8 min median to stop",
                "Highest per-trade return on target hits (+41 bps avg)",
            ],
            'bullish_reversal': [
                "IWM is the BEST ticker for mean-reversion setups",
                "2-1-2 reversals work particularly well on small caps",
                "Look for reversals at prev week lows",
            ],
            'bearish_reversal': [
                "Bearish reversals strongest when RSI > 70 on IWM",
                "Small caps overshoot — look for exhaustion at resistance",
            ],
            'outside_bar': [
                "IWM has MORE Type 3 bars than SPY (higher volatility)",
                "Outside bars on IWM often lead to sharp continuation",
            ],
            'orb_breakout': [
                "IWM has the WIDEST opening ranges — breakouts are more decisive",
                "Once IWM breaks ORB, it tends to run further than SPY",
            ],
            'orb_breakdown': [
                "IWM bearish ORB breakdowns are particularly strong",
                "Small caps sell off harder — bigger moves on downside",
            ],
            'orb_failure': [
                "IWM has fewer ORB failures but LARGER moves when they happen",
                "Mean reversion works well after failed breakouts on IWM",
            ],
            'support_bounce': [
                "IWM bounces harder off support (mean reversion character)",
                "Previous week low is a strong support level for IWM",
            ],
            'resistance_rejection': [
                "IWM rejections at resistance tend to be sharp",
                "Look for RSI > 70 at resistance for highest probability",
            ],
            'order_block': [
                "Institutional order blocks may be less defined on IWM (small cap)",
                "Use with other confirmation for better results",
            ],
            'ftfc_conviction': [
                "When all aligned, IWM provides the BEST risk/reward",
                "Sharpe 9.64 on 1m+15m — strongest of all tickers",
                "But these setups are RARE (492 trades in 10 years)",
            ],
        },
        'SPY': {
            'bullish_continuation': [
                "SPY trends more cleanly — continuation IS more likely than IWM",
                "VWAP is the #1 indicator for SPY (institutional reference)",
                "Most balanced CALL/PUT distribution of all tickers",
                "Best combo: 1m+30m (Sharpe 5.54, WR 54.5%)",
            ],
            'bearish_continuation': [
                "SPY CALL WR (43.5%) nearly identical to PUT WR (43.7%)",
                "SPY has tightest targets (+0.15% CALL, +0.20% PUT)",
                "Time stops produce 55% win rate on SPY",
            ],
            'bullish_reversal': [
                "SPY reversals are subtler — less dramatic than IWM",
                "VWAP reclaim is the strongest confirmation for SPY reversals",
            ],
            'bearish_reversal': [
                "SPY trend following works better than reversal",
                "Be more selective with bearish reversals on SPY",
            ],
            'outside_bar': [
                "SPY has FEWER Type 3 bars — they're rarer but meaningful",
                "Outside bars on SPY often signal trend change",
            ],
            'orb_breakout': [
                "SPY has tightest opening ranges — false breakouts MORE common",
                "Wait for confirmation before entering SPY ORB breakouts",
            ],
            'orb_breakdown': [
                "SPY bearish ORB breaks tend to be more measured",
                "Tighter targets appropriate (-0.12% stop, +0.20% target)",
            ],
            'orb_failure': [
                "SPY may have the MOST ORB failures (tighter range)",
                "SPY ORB failures are a good mean-reversion opportunity",
            ],
            'support_bounce': [
                "VWAP is the strongest support for SPY",
                "Previous day close also acts as strong reference",
            ],
            'resistance_rejection': [
                "SPY respects previous day high as resistance",
                "Use VWAP crossing to confirm rejection",
            ],
            'order_block': [
                "SPY order blocks are more defined (institutional trading)",
                "SPX-derived levels also apply to SPY",
            ],
            'ftfc_conviction': [
                "SPY FTFC alignment flipped Sharpe from -0.19 to +0.18",
                "The BIGGEST relative improvement from Strat filtering",
                "Best combo: 1m+30m (NOT 1m+15m like other tickers)",
            ],
        },
        'QQQ': {
            'bullish_continuation': [
                "QQQ CALLS only win 37.6% — be EXTRA selective",
                "Momentum matters MORE here — StochRSI is more predictive",
                "Score 6/8 signals hit 52.0% with +3.5 bps — quality over quantity",
                "Best combo: 1m+15m (Sharpe 6.67, WR 52.0%)",
            ],
            'bearish_continuation': [
                "QQQ has the MOST stops hit (49.2%)",
                "Fastest failures: 7 min median to stop",
                "QQQ momentum means 2D sequences may accelerate",
            ],
            'bullish_reversal': [
                "QQQ needs MORE consecutive bars before reversal than IWM",
                "Momentum character means reversals are harder to time",
            ],
            'bearish_reversal': [
                "QQQ bullish-to-bearish exhaustion CAN be profitable",
                "Look for RSI divergence on QQQ (price higher, RSI lower)",
            ],
            'outside_bar': [
                "QQQ outside bars often reflect gap-and-go momentum",
                "Post-gap Type 3 bars have different characteristics",
            ],
            'orb_breakout': [
                "QQQ often GAPS at open — ORB sets differently",
                "After gap opens, ORB breakouts may be more decisive",
            ],
            'orb_breakdown': [
                "QQQ bearish ORB breaks can accelerate fast",
                "Momentum makes stops important — respect -0.12%",
            ],
            'orb_failure': [
                "QQQ ORB failures after gap opens may be especially profitable",
                "Gap fills combine well with failed ORB breakouts",
            ],
            'support_bounce': [
                "QQQ bounces less reliably than IWM (momentum character)",
                "Need STRONG volume confirmation for bounces on QQQ",
            ],
            'resistance_rejection': [
                "QQQ tends to blow through resistance on momentum days",
                "Only fade QQQ at resistance with STRONG reversal signals",
            ],
            'order_block': [
                "Tech mega-caps drive QQQ — order blocks reflect their activity",
                "QQQ order block tests need volume confirmation",
            ],
            'ftfc_conviction': [
                "HARDEST ticker to trade — needs HIGHEST conviction entry",
                "Consider ONLY taking score 5+ signals on QQQ",
                "When aligned, QQQ momentum provides excellent returns",
            ],
        },
    }

    return notes.get(ticker, {}).get(card_type, [f"No specific notes for {ticker}."])


# ---------------------------------------------------------------------------
# Quick Reference: Which Ticker Should I Trade?
# ---------------------------------------------------------------------------

def generate_quick_reference() -> str:
    """Generate the 'which ticker to trade' decision tree."""
    report = md_header("Quick Reference: Which Ticker Should I Trade Right Now?", 2)

    report += """
**Decision Tree:**

1. Check daily Strat for all 3 tickers
2. If IWM shows 2-1-2 reversal setup -> **IWM** (strongest mean reversion)
3. If SPY has cleanest FTFC alignment -> **SPY** (strongest trend following)
4. If QQQ has score 6+ signal -> **QQQ** (highest per-trade return at 6+)
5. If all 3 tickers signal the same direction -> **Highest conviction day**
6. If tickers conflict -> **Reduce size or sit out**

**Ticker Personality Summary:**

| Trait | IWM | SPY | QQQ |
|-------|-----|-----|-----|
| Character | Volatile Mean Reverter | Steady Grinder | Momentum Runner |
| Best For | Reversal setups | Trend following | High-conviction momentum |
| Base WR | ~42% | ~43.5% | ~40% |
| PUT lean | Strong (72%) | Balanced (50/50) | Moderate |
| Best combo | 1m+15m | 1m+30m | 1m+15m |
| Target width | Widest | Tightest | Medium |
| Stop speed | 8 min | Moderate | 7 min (fastest) |
| Risk level | Medium | Low | High |

"""
    return report


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------

def run_phase6(tickers: list = None):
    """Run Phase 6 — generate all playbook cards."""
    if tickers is None:
        tickers = TICKERS

    combined_report = md_header("Phase 6: The Beginner's Playbook — All Tickers", 1)
    combined_report += f"\nGenerated: {timestamp_str()}\n"
    combined_report += "\n12 decision cards per ticker, each with specific entry/exit rules.\n\n"

    combined_report += generate_quick_reference()

    for ticker in tickers:
        progress(f"Starting Phase 6 — building playbook cards", ticker)

        df_1m = load_ticker_1m(ticker)
        if df_1m.empty:
            progress("No data, skipping.", ticker)
            continue

        df = enrich_with_indicators(df_1m)
        labels = df['strat_type'] if 'strat_type' in df.columns else classify_strat_series(df)
        progress(f"Data loaded: {len(df):,} bars", ticker)

        # Build per-ticker report
        report = md_header(f"Phase 6: {ticker} Playbook", 1)
        report += f"\nGenerated: {timestamp_str()}\n"
        report += f"Data: {df.index.min()} to {df.index.max()} ({len(df):,} bars)\n"
        report += "\n12 decision cards for real-time trading.\n"

        cards = build_all_cards(ticker, df, labels)
        report += cards

        save_report(report, f'phase6_playbook_{ticker.lower()}.md')
        combined_report += f"\n---\n\n" + cards

        progress("Phase 6 complete!", ticker)

    save_report(combined_report, 'phase6_playbook_combined.md')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Phase 6: Playbook')
    parser.add_argument('--tickers', nargs='+', default=TICKERS)
    args = parser.parse_args()
    run_phase6(tickers=args.tickers)
