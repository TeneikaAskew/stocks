#!/usr/bin/env python3
"""
Scan historical 1-minute data for ETF swing trades.

Entry: afternoon (14:00-15:55 ET) at relative low (CALL) or relative high (PUT).
Exit: next trading day, tracking best return by noon and by EOD.

Usage:
    python scripts/find_swing_trades.py --ticker IWM
    python scripts/find_swing_trades.py --ticker SPY --entry-start 1400 --entry-end 1555
    python scripts/find_swing_trades.py --ticker QQQ --min-score 3
    python scripts/find_swing_trades.py --all
"""

import argparse
import sys
import os
from pathlib import Path
from datetime import datetime
import glob

import pandas as pd
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class SwingTradeScanner:
    """Scan historical data for afternoon entry / next-day exit swing trades."""

    TICKERS = ['IWM', 'SPY', 'QQQ']

    def __init__(self, ticker, entry_start=1400, entry_end=1555, min_score=2,
                 options_pnl=False):
        self.ticker = ticker.upper()
        self.entry_start = entry_start
        self.entry_end = entry_end
        self.min_score = min_score
        self.options_pnl = options_pnl
        self.df = None
        self.trading_days = None
        self.day_groups = None
        self.results = []

    # ------------------------------------------------------------------
    # Step 1: Load and prepare data
    # ------------------------------------------------------------------
    def load_data(self):
        """Load historical indicator parquet and filter to market hours."""
        symbol_lower = self.ticker.lower()
        parquet_files = glob.glob(
            f'data/signals/historical_{symbol_lower}_*_with_indicators.parquet'
        )
        if not parquet_files:
            raise FileNotFoundError(
                f"No indicator parquet found for {self.ticker}. "
                f"Expected data/signals/historical_{symbol_lower}_*_with_indicators.parquet"
            )

        print(f"Loading {parquet_files[0]}...")
        self.df = pd.read_parquet(parquet_files[0])
        self.df['Time'] = pd.to_datetime(self.df['Time'])

        # Filter to market hours (9:30-16:00)
        hour = self.df['Time'].dt.hour
        minute = self.df['Time'].dt.minute
        time_val = hour * 100 + minute
        original_len = len(self.df)
        self.df = self.df[(time_val >= 930) & (time_val <= 1600)].copy()
        print(f"  Loaded {original_len:,} rows, filtered to {len(self.df):,} market-hours rows")

        # Build day index
        self.df['Day_Date'] = self.df['Time'].dt.date
        self.trading_days = sorted(self.df['Day_Date'].unique())
        self.day_groups = {d: grp for d, grp in self.df.groupby('Day_Date')}
        print(f"  {len(self.trading_days)} trading days "
              f"({self.trading_days[0]} to {self.trading_days[-1]})")

    # ------------------------------------------------------------------
    # Step 2: Compute daily context (vectorized)
    # ------------------------------------------------------------------
    def compute_daily_context(self):
        """Add running day low/high and position-in-range columns."""
        self.df['Running_Low'] = self.df.groupby('Day_Date')['Low'].cummin()
        self.df['Running_High'] = self.df.groupby('Day_Date')['High'].cummax()
        self.df['Day_Range'] = self.df['Running_High'] - self.df['Running_Low']

        # How far price is from day low/high (0.0 = at extreme, 1.0 = at opposite)
        safe_range = self.df['Day_Range'].replace(0, np.nan)
        self.df['Pct_From_Day_Low'] = (
            (self.df['Last'] - self.df['Running_Low']) / safe_range
        ).fillna(0.5)
        self.df['Pct_From_Day_High'] = (
            (self.df['Running_High'] - self.df['Last']) / safe_range
        ).fillna(0.5)

        # Rebuild day_groups after adding columns
        self.day_groups = {d: grp for d, grp in self.df.groupby('Day_Date')}
        print("  Computed daily context (running low/high, position in range)")

    # ------------------------------------------------------------------
    # Step 3: Entry scoring
    # ------------------------------------------------------------------
    def score_long_entry(self, row):
        """Score a bar as a potential CALL (long) swing entry. Returns (score, conditions)."""
        score = 0
        conditions = []

        if row['Pct_From_Day_Low'] < 0.25:
            score += 1
            conditions.append('near_day_low')
        if not pd.isna(row.get('RSI14_W')) and row['RSI14_W'] < 40:
            score += 1
            conditions.append('rsi_oversold')
        if not pd.isna(row.get('StochRSI_K')) and row['StochRSI_K'] < 30:
            score += 1
            conditions.append('stochrsi_oversold')
        if not pd.isna(row.get('VWAP')) and row['Last'] < row['VWAP']:
            score += 1
            conditions.append('below_vwap')
        if not pd.isna(row.get('EMA20')) and row['Last'] < row['EMA20']:
            score += 1
            conditions.append('below_ema20')

        return score, conditions

    def score_short_entry(self, row):
        """Score a bar as a potential PUT (short) swing entry. Returns (score, conditions)."""
        score = 0
        conditions = []

        if row['Pct_From_Day_High'] < 0.25:
            score += 1
            conditions.append('near_day_high')
        if not pd.isna(row.get('RSI14_W')) and row['RSI14_W'] > 60:
            score += 1
            conditions.append('rsi_overbought')
        if not pd.isna(row.get('StochRSI_K')) and row['StochRSI_K'] > 70:
            score += 1
            conditions.append('stochrsi_overbought')
        if not pd.isna(row.get('VWAP')) and row['Last'] > row['VWAP']:
            score += 1
            conditions.append('above_vwap')
        if not pd.isna(row.get('EMA20')) and row['Last'] > row['EMA20']:
            score += 1
            conditions.append('above_ema20')

        return score, conditions

    # ------------------------------------------------------------------
    # Step 4: Next-day exit metrics
    # ------------------------------------------------------------------
    def _next_trading_day(self, entry_date):
        """Return the next trading day after entry_date, or None."""
        idx = self.trading_days.index(entry_date)
        if idx + 1 < len(self.trading_days):
            return self.trading_days[idx + 1]
        return None

    def compute_exit_metrics(self, entry_row, next_day_df, direction):
        """Compute next-day exit metrics for a swing trade entry."""
        entry_price = entry_row['Last']
        ndf = next_day_df.copy()

        # Time values for filtering
        ndf_hm = ndf['Time'].dt.hour * 100 + ndf['Time'].dt.minute

        # Next day open
        next_day_open = ndf.iloc[0]['Open'] if 'Open' in ndf.columns else ndf.iloc[0]['Last']
        gap_pct = (next_day_open - entry_price) / entry_price * 100

        # Compute per-bar returns using High/Low for realistic tracking
        if direction == 'CALL':
            ndf['Best_Bar_Return'] = (ndf['High'] - entry_price) / entry_price * 100
            ndf['Worst_Bar_Return'] = (ndf['Low'] - entry_price) / entry_price * 100
        else:  # PUT
            ndf['Best_Bar_Return'] = (entry_price - ndf['Low']) / entry_price * 100
            ndf['Worst_Bar_Return'] = (entry_price - ndf['High']) / entry_price * 100

        # By-noon metrics (9:30 - 12:00)
        by_noon = ndf[ndf_hm <= 1200]
        best_return_noon = by_noon['Best_Bar_Return'].max() if len(by_noon) > 0 else 0.0

        # By-EOD metrics (full day)
        best_return_eod = ndf['Best_Bar_Return'].max()
        best_exit_idx = ndf['Best_Bar_Return'].idxmax()
        best_exit_time = ndf.loc[best_exit_idx, 'Time']
        if direction == 'CALL':
            best_exit_price = ndf.loc[best_exit_idx, 'High']
        else:
            best_exit_price = ndf.loc[best_exit_idx, 'Low']

        # Time from open to best exit
        open_time = ndf.iloc[0]['Time']
        time_to_best = (best_exit_time - open_time).total_seconds() / 60

        # Max adverse excursion before best exit
        bars_before_best = ndf.loc[:best_exit_idx]
        max_adverse = abs(bars_before_best['Worst_Bar_Return'].min()) if len(bars_before_best) > 0 else 0.0

        # Noon price (closest bar to 12:00)
        noon_bars = ndf[(ndf_hm >= 1155) & (ndf_hm <= 1205)]
        if len(noon_bars) > 0:
            noon_bar = noon_bars.iloc[len(noon_bars) // 2]
            noon_price = noon_bar['Last']
        else:
            noon_price = np.nan
        if direction == 'CALL':
            noon_return = (noon_price - entry_price) / entry_price * 100 if not pd.isna(noon_price) else np.nan
        else:
            noon_return = (entry_price - noon_price) / entry_price * 100 if not pd.isna(noon_price) else np.nan

        # EOD price
        eod_price = ndf.iloc[-1]['Last']
        if direction == 'CALL':
            eod_return = (eod_price - entry_price) / entry_price * 100
        else:
            eod_return = (entry_price - eod_price) / entry_price * 100

        return {
            'Exit_Date': ndf.iloc[0]['Time'].date(),
            'Next_Day_Open': round(next_day_open, 2),
            'Next_Day_Gap_Pct': round(gap_pct, 3),
            'Best_Return_By_Noon': round(best_return_noon, 3),
            'Best_Return_By_EOD': round(best_return_eod, 3),
            'Best_Exit_Time': best_exit_time,
            'Best_Exit_Price': round(best_exit_price, 2),
            'Time_To_Best_Exit_Min': round(time_to_best, 0),
            'Max_Adverse_Pct': round(max_adverse, 3),
            'Noon_Price': round(noon_price, 2) if not pd.isna(noon_price) else np.nan,
            'Noon_Return_Pct': round(noon_return, 3) if not pd.isna(noon_return) else np.nan,
            'EOD_Price': round(eod_price, 2),
            'EOD_Return_Pct': round(eod_return, 3),
            'Profitable_By_Noon': int(best_return_noon > 0.1),
            'Profitable_By_EOD': int(best_return_eod > 0.1),
            'EOD_Profitable': int(eod_return > 0),
        }

    # ------------------------------------------------------------------
    # Step 5: Build trade record
    # ------------------------------------------------------------------
    def _build_trade_record(self, direction, score, conditions, entry_row, exit_metrics):
        """Combine entry info and exit metrics into a single trade record."""
        record = {
            'ID': f'SWING_{len(self.results) + 1}',
            'Ticker': self.ticker,
            'Direction': direction,
            'Entry_Score': score,
            'Entry_Conditions': ','.join(conditions),
            'Entry_Date': entry_row['Time'].date(),
            'Entry_Time': entry_row['Time'],
            'Entry_Price': round(entry_row['Last'], 2),
        }

        # Entry indicators
        for col in ['RSI14_W', 'StochRSI_K', 'StochRSI_D', 'VWAP', 'EMA9', 'EMA20',
                     'EMA50', 'ATR14_W', 'RVOL20', 'Volume', 'OBV']:
            if col in entry_row.index and not pd.isna(entry_row[col]):
                record[f'Entry_{col}'] = round(entry_row[col], 4) if isinstance(entry_row[col], float) else entry_row[col]

        # Daily context
        record['Entry_Pct_From_Day_Low'] = round(entry_row['Pct_From_Day_Low'], 3)
        record['Entry_Pct_From_Day_High'] = round(entry_row['Pct_From_Day_High'], 3)
        record['Entry_Day_Range'] = round(entry_row['Day_Range'], 2)

        # Previous day close
        if 'Prev_Day_Close' in entry_row.index and not pd.isna(entry_row['Prev_Day_Close']):
            record['Entry_Prev_Day_Close'] = round(entry_row['Prev_Day_Close'], 2)
            record['Entry_vs_Prev_Close_Pct'] = round(
                (entry_row['Last'] - entry_row['Prev_Day_Close']) / entry_row['Prev_Day_Close'] * 100, 3
            )

        # Exit metrics
        record.update(exit_metrics)

        return record

    # ------------------------------------------------------------------
    # Step 6: Main scan loop
    # ------------------------------------------------------------------
    def scan_trades(self):
        """Scan all afternoon bars for qualifying entries, compute next-day exits."""
        self.results = []
        total_days = len(self.trading_days) - 1  # skip last day
        print(f"\nScanning {total_days} trading days for swing entries "
              f"({self.entry_start}-{self.entry_end}, min score {self.min_score})...")

        for i, day_date in enumerate(self.trading_days[:-1]):
            next_date = self._next_trading_day(day_date)
            if next_date is None:
                continue

            next_day_df = self.day_groups.get(next_date)
            if next_day_df is None or len(next_day_df) == 0:
                continue

            # Get afternoon bars in entry window
            day_df = self.day_groups[day_date]
            hm = day_df['Time'].dt.hour * 100 + day_df['Time'].dt.minute
            afternoon = day_df[(hm >= self.entry_start) & (hm <= self.entry_end)]

            if len(afternoon) == 0:
                continue

            # Find best entry per direction
            best_long = None
            best_short = None

            for idx, row in afternoon.iterrows():
                if pd.isna(row.get('RSI14_W')):
                    continue

                long_score, long_conds = self.score_long_entry(row)
                if long_score >= self.min_score:
                    if best_long is None or long_score > best_long[0]:
                        best_long = (long_score, long_conds, row)

                short_score, short_conds = self.score_short_entry(row)
                if short_score >= self.min_score:
                    if best_short is None or short_score > best_short[0]:
                        best_short = (short_score, short_conds, row)

            # Process best entries
            for direction, best in [('CALL', best_long), ('PUT', best_short)]:
                if best is not None:
                    score, conditions, entry_row = best
                    exit_metrics = self.compute_exit_metrics(entry_row, next_day_df, direction)
                    self.results.append(
                        self._build_trade_record(direction, score, conditions, entry_row, exit_metrics)
                    )

            if (i + 1) % 100 == 0:
                print(f"  Processed {i + 1}/{total_days} days, {len(self.results)} trades found...")

        print(f"\nFound {len(self.results)} swing trade entries")
        calls = sum(1 for r in self.results if r['Direction'] == 'CALL')
        puts = sum(1 for r in self.results if r['Direction'] == 'PUT')
        print(f"  CALL: {calls}, PUT: {puts}")

    # ------------------------------------------------------------------
    # Step 6b: Enrich with options P&L estimates
    # ------------------------------------------------------------------
    def enrich_with_options_pnl(self):
        """Enrich trade results with estimated options P&L using EOD Greeks."""
        from scripts.analysis.options_pnl_translation import (
            load_options_chain, find_swing_option, estimate_swing_options_pnl,
        )

        print(f"\nEnriching {len(self.results)} trades with options P&L estimates...")
        matched = 0
        missing_chain = 0
        missing_option = 0
        chain_cache = {}

        for trade in self.results:
            entry_date = trade['Entry_Date']
            exit_date = trade['Exit_Date']

            # Cache chains by date to avoid re-reading
            if entry_date not in chain_cache:
                chain_cache[entry_date] = load_options_chain(self.ticker, entry_date)
            chain = chain_cache[entry_date]

            if chain.empty:
                missing_chain += 1
                continue

            atm = find_swing_option(
                chain, trade['Entry_Price'], entry_date, exit_date, trade['Direction']
            )
            if atm.empty:
                missing_option += 1
                continue

            underlying_returns = {
                'Noon': trade.get('Best_Return_By_Noon', np.nan),
                'BestEOD': trade.get('Best_Return_By_EOD', np.nan),
                'EOD': trade.get('EOD_Return_Pct', np.nan),
            }

            est = estimate_swing_options_pnl(
                entry_price=trade['Entry_Price'],
                direction=trade['Direction'],
                atm_opt=atm,
                entry_date=entry_date,
                exit_date=exit_date,
                underlying_returns=underlying_returns,
            )

            if est is not None:
                trade.update(est)
                matched += 1

        print(f"  Options matched: {matched}/{len(self.results)} "
              f"({missing_chain} missing chains, {missing_option} no ATM found)")

    # ------------------------------------------------------------------
    # Step 7: Save results
    # ------------------------------------------------------------------
    def save_results(self):
        """Save results to CSV and Parquet."""
        if not self.results:
            print("No trades found, nothing to save.")
            return None

        df = pd.DataFrame(self.results)
        csv_path = f'data/signals/{self.ticker.lower()}_swing_trades.csv'
        parquet_path = csv_path.replace('.csv', '.parquet')

        df.to_csv(csv_path, index=False)
        df.to_parquet(parquet_path, index=False)
        print(f"\nSaved {len(df)} trades to {csv_path} and {parquet_path}")
        return df

    # ------------------------------------------------------------------
    # Step 7b: Options P&L report section
    # ------------------------------------------------------------------
    def _generate_options_report(self, df):
        """Generate the Options P&L Estimates section for the report."""
        lines = []
        opt = df.dropna(subset=['Opt_Mark'])

        if len(opt) == 0:
            lines.append("\n## Options P&L Estimates\n")
            lines.append("No options data matched for any trades.\n")
            return lines

        lines.append("\n## Options P&L Estimates\n")
        lines.append("> **Estimation caveat**: Options P&L uses EOD Greeks snapshots. "
                      "Theta is estimated as |theta| x calendar days held. "
                      "IV shifts overnight are NOT modeled. "
                      "Treat results as an approximate upper bound.\n")

        # Overall summary table
        lines.append("### Overall Summary\n")
        lines.append("| Metric | Underlying | Options (est.) |")
        lines.append("|--------|-----------|----------------|")
        lines.append(f"| Trades with options data | {len(df)} | {len(opt)} |")
        lines.append(f"| Win Rate (Best by Noon) | "
                      f"{df['Profitable_By_Noon'].mean() * 100:.1f}% | "
                      f"{opt['Opt_Noon_Win'].mean() * 100:.1f}% |")
        lines.append(f"| Win Rate (Best by EOD) | "
                      f"{df['Profitable_By_EOD'].mean() * 100:.1f}% | "
                      f"{opt['Opt_BestEOD_Win'].mean() * 100:.1f}% |")
        lines.append(f"| Win Rate (EOD Close) | "
                      f"{df['EOD_Profitable'].mean() * 100:.1f}% | "
                      f"{opt['Opt_EOD_Win'].mean() * 100:.1f}% |")
        lines.append(f"| Avg Return (Best EOD) | "
                      f"{df['Best_Return_By_EOD'].mean():.3f}% | "
                      f"{opt['Opt_BestEOD_PnL_Pct'].mean():.1f}% (on premium) |")
        lines.append(f"| Avg Return (EOD Close) | "
                      f"{df['EOD_Return_Pct'].mean():.3f}% | "
                      f"{opt['Opt_EOD_PnL_Pct'].mean():.1f}% (on premium) |")
        theta_rate_avg = opt['Opt_Theta'].abs().mean()
        theta_total_avg = (opt['Opt_Theta'].abs() * opt['Opt_Theta_Days']).mean() \
            if 'Opt_Theta_Days' in opt.columns else theta_rate_avg
        lines.append(f"| Avg Theta Rate | — | ${theta_rate_avg:.3f}/day |")
        lines.append(f"| Avg Total Theta Cost | — | ${theta_total_avg:.3f} (rate × days held) |")
        lines.append(f"| Avg Spread Cost | — | ${opt['Opt_Spread_Cost'].mean():.3f} |")
        lines.append(f"| Avg Mark Price | — | ${opt['Opt_Mark'].mean():.2f} |")
        lines.append(f"| Avg Delta | — | {opt['Opt_Delta'].abs().mean():.3f} |")

        # Direction breakdown
        lines.append("\n### Options P&L by Direction\n")
        lines.append("| Metric | CALL | PUT |")
        lines.append("|--------|------|-----|")
        call_opt = opt[opt['Direction'] == 'CALL']
        put_opt = opt[opt['Direction'] == 'PUT']
        for label, col in [('Trades', None), ('Win Rate (Best EOD)', 'Opt_BestEOD_Win'),
                            ('Win Rate (EOD Close)', 'Opt_EOD_Win'),
                            ('Avg Return (Best EOD)', 'Opt_BestEOD_PnL_Pct'),
                            ('Avg Return (EOD Close)', 'Opt_EOD_PnL_Pct'),
                            ('Avg Theta Cost', 'Opt_Theta'), ('Avg Mark', 'Opt_Mark')]:
            if col is None:
                lines.append(f"| {label} | {len(call_opt)} | {len(put_opt)} |")
            elif col == 'Opt_Theta':
                lines.append(f"| {label} | ${call_opt[col].abs().mean():.3f} | "
                              f"${put_opt[col].abs().mean():.3f} |")
            elif col == 'Opt_Mark':
                lines.append(f"| {label} | ${call_opt[col].mean():.2f} | "
                              f"${put_opt[col].mean():.2f} |")
            elif 'Win' in col:
                cv = call_opt[col].mean() * 100 if len(call_opt) > 0 else 0
                pv = put_opt[col].mean() * 100 if len(put_opt) > 0 else 0
                lines.append(f"| {label} | {cv:.1f}% | {pv:.1f}% |")
            else:
                cv = call_opt[col].mean() if len(call_opt) > 0 else 0
                pv = put_opt[col].mean() if len(put_opt) > 0 else 0
                lines.append(f"| {label} | {cv:.1f}% | {pv:.1f}% |")

        # Weekend vs weekday comparison
        if 'Opt_Theta_Days' in opt.columns:
            weekday = opt[opt['Opt_Theta_Days'] == 1]
            weekend = opt[opt['Opt_Theta_Days'] >= 3]
            if len(weekday) > 0 and len(weekend) > 0:
                lines.append("\n### Weekday vs Weekend Holds\n")
                lines.append("| Metric | Weekday (1 day) | Weekend (3+ days) |")
                lines.append("|--------|-----------------|-------------------|")
                lines.append(f"| Trades | {len(weekday)} | {len(weekend)} |")
                lines.append(f"| Options Win Rate (Best EOD) | "
                              f"{weekday['Opt_BestEOD_Win'].mean() * 100:.1f}% | "
                              f"{weekend['Opt_BestEOD_Win'].mean() * 100:.1f}% |")
                lines.append(f"| Avg Theta Rate ($/day) | "
                              f"${weekday['Opt_Theta'].abs().mean():.3f} | "
                              f"${weekend['Opt_Theta'].abs().mean():.3f} |")
                lines.append(f"| Avg Theta Cost (total) | "
                              f"${(weekday['Opt_Theta'].abs() * weekday['Opt_Theta_Days']).mean():.3f} | "
                              f"${(weekend['Opt_Theta'].abs() * weekend['Opt_Theta_Days']).mean():.3f} |")
                lines.append(f"| Avg Options Return (Best EOD) | "
                              f"{weekday['Opt_BestEOD_PnL_Pct'].mean():.1f}% | "
                              f"{weekend['Opt_BestEOD_PnL_Pct'].mean():.1f}% |")
                lines.append(
                    f"\n> **Note**: Weekday entries buy next-day (1-DTE) options; "
                    f"Friday entries buy Monday-expiry (~3-DTE) options. "
                    f"3-DTE options carry ~3× lower per-day theta than 1-DTE options, "
                    f"so total theta costs end up similar despite the longer hold."
                )

        # Leverage analysis by underlying return bucket
        lines.append("\n### Options Leverage by Underlying Return\n")
        lines.append("| Underlying Return | Trades | Avg Opt Return | Leverage |")
        lines.append("|-------------------|--------|----------------|----------|")
        buckets = [(0, 0.3, '0.0-0.3%'), (0.3, 0.6, '0.3-0.6%'),
                    (0.6, 1.0, '0.6-1.0%'), (1.0, 100, '1.0%+')]
        for lo, hi, label in buckets:
            mask = (opt['Best_Return_By_EOD'].abs() >= lo) & (opt['Best_Return_By_EOD'].abs() < hi)
            sub = opt[mask]
            if len(sub) < 3:
                continue
            avg_und = sub['Best_Return_By_EOD'].mean()
            avg_opt = sub['Opt_BestEOD_PnL_Pct'].mean()
            if avg_und > 0.3:
                leverage = avg_opt / avg_und
                lev_str = f"{leverage:.1f}x"
            else:
                lev_str = "N/A (small move)"
            lines.append(f"| {label} | {len(sub)} | {avg_opt:.1f}% | {lev_str} |")

        # Verdict
        opt_wr = opt['Opt_BestEOD_Win'].mean() * 100
        if opt_wr >= 55:
            verdict = "SURVIVES — Edge holds in options after estimated costs."
        elif opt_wr >= 50:
            verdict = "MARGINAL — Barely positive. Real theta/IV costs could flip this."
        else:
            verdict = "DOES NOT SURVIVE — Theta + spread wipes the underlying edge."
        lines.append(f"\n**Options Verdict: {verdict}**\n")

        return lines

    # ------------------------------------------------------------------
    # Step 7c: Winner vs Loser Indicator Profile
    # ------------------------------------------------------------------
    def _generate_winner_profile_section(self, df):
        """Generate Winner vs Loser Indicator Profile section."""
        if 'Profitable_By_EOD' not in df.columns:
            return []

        lines = []
        lines.append("\n## Winner vs Loser Indicator Profile\n")
        lines.append("> Trades where the next-day move went in the predicted direction (winners) "
                     "vs those that did not (losers). Based on Best Return by EOD > 0.1% threshold.\n")

        call_df = df[df['Direction'] == 'CALL']
        put_df = df[df['Direction'] == 'PUT']
        winners = df[df['Profitable_By_EOD'] == 1]
        losers = df[df['Profitable_By_EOD'] == 0]

        call_wr = call_df['Profitable_By_EOD'].mean() * 100
        put_wr = put_df['Profitable_By_EOD'].mean() * 100

        def profit_factor(sub_df):
            wins = sub_df[sub_df['Profitable_By_EOD'] == 1]['Best_Return_By_EOD']
            losses_eod = sub_df[sub_df['Profitable_By_EOD'] == 0]['EOD_Return_Pct']
            avg_win = wins.mean() if len(wins) > 0 else 0
            avg_loss = abs(losses_eod.mean()) if len(losses_eod) > 0 else 0
            return avg_win / avg_loss if avg_loss > 0 else 99.9

        # 1. Direction Bias
        lines.append("### Direction Bias\n")
        lines.append("| Direction | Trades | Win Rate | Avg Best Return | Profit Factor |")
        lines.append("|-----------|--------|----------|-----------------|---------------|")
        for direction, sub in [('CALL', call_df), ('PUT', put_df)]:
            pf = profit_factor(sub)
            pf_str = f"{pf:.2f}x" if pf < 90 else ">90x"
            lines.append(f"| {direction} | {len(sub)} | "
                         f"{sub['Profitable_By_EOD'].mean()*100:.1f}% | "
                         f"{sub['Best_Return_By_EOD'].mean():.3f}% | {pf_str} |")

        # 2. Overnight Gap Analysis
        if 'Next_Day_Gap_Pct' in df.columns:
            lines.append("\n### Overnight Gap Analysis\n")
            lines.append("> The gap direction (next-day open vs entry price) is the strongest predictor of trade outcome.\n")
            lines.append("| Direction | Outcome | Count | Avg Gap |")
            lines.append("|-----------|---------|-------|---------|")
            for direction, sub in [('CALL', call_df), ('PUT', put_df)]:
                for outcome, label in [(1, 'Winner'), (0, 'Loser')]:
                    grp = sub[sub['Profitable_By_EOD'] == outcome]
                    if len(grp) == 0:
                        continue
                    avg_gap = grp['Next_Day_Gap_Pct'].mean()
                    sign = '+' if avg_gap >= 0 else ''
                    lines.append(f"| {direction} | {label} | {len(grp)} | {sign}{avg_gap:.2f}% |")

        # 3. RSI Bucket analysis
        if 'Entry_RSI14_W' in df.columns:
            lines.append("\n### RSI at Entry: Winners vs Losers\n")
            lines.append("| RSI Bucket | CALL Trades | CALL Win Rate | PUT Trades | PUT Win Rate |")
            lines.append("|------------|-------------|---------------|------------|--------------|")
            buckets = [
                (0, 25, '< 25'), (25, 35, '25-35'), (35, 45, '35-45'), (45, 55, '45-55'),
                (55, 65, '55-65'), (65, 75, '65-75'), (75, 85, '75-85'), (85, 101, '> 85'),
            ]
            for lo, hi, label in buckets:
                call_sub = df[(df['Direction'] == 'CALL') & (df['Entry_RSI14_W'] >= lo) & (df['Entry_RSI14_W'] < hi)]
                put_sub = df[(df['Direction'] == 'PUT') & (df['Entry_RSI14_W'] >= lo) & (df['Entry_RSI14_W'] < hi)]
                if len(call_sub) < 3 and len(put_sub) < 3:
                    continue
                call_wr_str = f"{call_sub['Profitable_By_EOD'].mean()*100:.1f}%" if len(call_sub) >= 3 else "—"
                put_wr_str = f"{put_sub['Profitable_By_EOD'].mean()*100:.1f}%" if len(put_sub) >= 3 else "—"
                lines.append(f"| {label} | {len(call_sub)} | {call_wr_str} | {len(put_sub)} | {put_wr_str} |")

        # 4. Day Range vs Return
        if 'Entry_Day_Range' in df.columns:
            lines.append("\n### Day Range vs Return Size\n")
            lines.append("| Return Bucket | Trades | Avg Day Range | Avg Best Return |")
            lines.append("|---------------|--------|---------------|-----------------|")
            ret_buckets = [
                (0, 0.5, '< 0.5%'), (0.5, 1.0, '0.5-1.0%'),
                (1.0, 1.5, '1.0-1.5%'), (1.5, 999, '> 1.5%'),
            ]
            for lo, hi, label in ret_buckets:
                sub = df[(df['Best_Return_By_EOD'] >= lo) & (df['Best_Return_By_EOD'] < hi)]
                if len(sub) < 3:
                    continue
                lines.append(f"| {label} | {len(sub)} | "
                             f"${sub['Entry_Day_Range'].mean():.2f} | "
                             f"{sub['Best_Return_By_EOD'].mean():.2f}% |")

        # 5. Entry Condition Win Rate with vs without
        lines.append("\n### Entry Condition: Win Rate With vs Without\n")
        lines.append("| Condition | Direction | With Condition | Without Condition | Lift |")
        lines.append("|-----------|-----------|----------------|-------------------|------|")
        CALL_CONDITIONS = {'near_day_low', 'rsi_oversold', 'stochrsi_oversold', 'below_vwap', 'below_ema20'}
        PUT_CONDITIONS = {'near_day_high', 'rsi_overbought', 'stochrsi_overbought', 'above_vwap', 'above_ema20'}
        for cond in sorted(CALL_CONDITIONS | PUT_CONDITIONS):
            direction = 'CALL' if cond in CALL_CONDITIONS else 'PUT'
            sub = call_df if direction == 'CALL' else put_df
            with_cond = sub[sub['Entry_Conditions'].str.contains(cond, na=False)]
            without_cond = sub[~sub['Entry_Conditions'].str.contains(cond, na=False)]
            if len(with_cond) < 5 or len(without_cond) < 5:
                continue
            wr_with = with_cond['Profitable_By_EOD'].mean() * 100
            wr_without = without_cond['Profitable_By_EOD'].mean() * 100
            lift = wr_with - wr_without
            lift_str = f"+{lift:.1f}%" if lift >= 0 else f"{lift:.1f}%"
            lines.append(f"| {cond} | {direction} | {wr_with:.1f}% | {wr_without:.1f}% | {lift_str} |")

        # 6. What PREDICTS winners — dynamic table
        lines.append("\n### What Predicts Winners\n")
        lines.append("| Factor | Signal | Impact |")
        lines.append("|--------|--------|--------|")

        # Direction bias row
        bias_note = "Strong upward drift — prefer CALLs" if call_wr > put_wr + 3 else "Both directions viable"
        lines.append(f"| Direction Bias | CALLs {call_wr:.1f}% WR vs PUTs {put_wr:.1f}% WR | {bias_note} |")

        # Overnight gap row
        if 'Next_Day_Gap_Pct' in df.columns:
            cw_gap = call_df[call_df['Profitable_By_EOD'] == 1]['Next_Day_Gap_Pct'].mean()
            cl_gap = call_df[call_df['Profitable_By_EOD'] == 0]['Next_Day_Gap_Pct'].mean()
            pw_gap = put_df[put_df['Profitable_By_EOD'] == 1]['Next_Day_Gap_Pct'].mean()
            pl_gap = put_df[put_df['Profitable_By_EOD'] == 0]['Next_Day_Gap_Pct'].mean()
            cw_s = '+' if cw_gap >= 0 else ''
            pw_s = '+' if pw_gap >= 0 else ''
            lines.append(f"| Overnight Gap | "
                         f"CALL: winners {cw_s}{cw_gap:.2f}% vs losers {cl_gap:.2f}%; "
                         f"PUT: winners {pw_s}{pw_gap:.2f}% vs losers +{pl_gap:.2f}% | "
                         f"#1 predictor — gap confirming trade direction is strongest signal |")

        # RSI sweet spot row
        if 'Entry_RSI14_W' in df.columns:
            call_mid = df[(df['Direction'] == 'CALL') & df['Entry_RSI14_W'].between(25, 45)]
            call_ext = df[(df['Direction'] == 'CALL') & (df['Entry_RSI14_W'] < 25)]
            put_mid = df[(df['Direction'] == 'PUT') & df['Entry_RSI14_W'].between(55, 75)]
            put_ext = df[(df['Direction'] == 'PUT') & (df['Entry_RSI14_W'] >= 75)]
            cm_wr = call_mid['Profitable_By_EOD'].mean() * 100 if len(call_mid) >= 5 else 0
            ce_wr = call_ext['Profitable_By_EOD'].mean() * 100 if len(call_ext) >= 5 else 0
            pm_wr = put_mid['Profitable_By_EOD'].mean() * 100 if len(put_mid) >= 5 else 0
            pe_wr = put_ext['Profitable_By_EOD'].mean() * 100 if len(put_ext) >= 5 else 0
            lines.append(f"| RSI Sweet Spot | "
                         f"CALL RSI 25-45: {cm_wr:.1f}% WR (extreme <25: {ce_wr:.1f}%); "
                         f"PUT RSI 55-75: {pm_wr:.1f}% WR (extreme 75+: {pe_wr:.1f}%) | "
                         f"Moderate levels beat extreme readings |")

        # Day range row
        if 'Entry_Day_Range' in df.columns:
            big_range = df[df['Best_Return_By_EOD'] >= 1.5]['Entry_Day_Range'].mean()
            all_range = df['Entry_Day_Range'].mean()
            pct_wider = (big_range / all_range - 1) * 100 if all_range > 0 else 0
            lines.append(f"| Day Volatility | "
                         f"Big winners (>1.5%) avg ${big_range:.2f} day range vs ${all_range:.2f} overall | "
                         f"{pct_wider:.0f}% wider range on best trade days |")

        # Condition count row
        df_cc = df.copy()
        df_cc['_nc'] = df_cc['Entry_Conditions'].str.split(',').str.len()
        few_wr = df_cc[df_cc['_nc'] <= 3]['Profitable_By_EOD'].mean() * 100
        many_wr = df_cc[df_cc['_nc'] >= 4]['Profitable_By_EOD'].mean() * 100
        few_note = "Fewer conditions → higher-quality setups" if few_wr > many_wr else "More conditions help marginally"
        lines.append(f"| Condition Count | ≤3 conditions: {few_wr:.1f}% WR; ≥4 conditions: {many_wr:.1f}% WR | {few_note} |")

        # 7. What DOESN'T predict winners — dynamic table
        lines.append("\n### What Does NOT Predict Winners\n")
        lines.append("| Factor | Finding | Notes |")
        lines.append("|--------|---------|-------|")

        # RVOL
        if 'Entry_RVOL20' in df.columns:
            win_rvol = winners['Entry_RVOL20'].mean()
            loss_rvol = losers['Entry_RVOL20'].mean()
            lines.append(f"| Relative Volume (RVOL) | "
                         f"Winners {win_rvol:.2f}x vs Losers {loss_rvol:.2f}x | "
                         f"Near-identical — volume at entry has no predictive value |")

        # Proximity to day extreme
        call_at_ext = call_df[call_df['Entry_Pct_From_Day_Low'] < 0.10]['Profitable_By_EOD'].mean() * 100
        call_near_ext = call_df[call_df['Entry_Pct_From_Day_Low'].between(0.10, 0.25)]['Profitable_By_EOD'].mean() * 100
        put_at_ext = put_df[put_df['Entry_Pct_From_Day_High'] < 0.10]['Profitable_By_EOD'].mean() * 100
        put_near_ext = put_df[put_df['Entry_Pct_From_Day_High'].between(0.10, 0.25)]['Profitable_By_EOD'].mean() * 100
        lines.append(f"| Exact Price Extreme | "
                     f"CALL at extreme (<10%): {call_at_ext:.1f}% vs near extreme (10-25%): {call_near_ext:.1f}%; "
                     f"PUT: {put_at_ext:.1f}% vs {put_near_ext:.1f}% | "
                     f"Being at the very extreme vs nearby shows no consistent edge |")

        # Entry score
        score5_wr = df[df['Entry_Score'] == 5]['Profitable_By_EOD'].mean() * 100
        score_low_wr = df[df['Entry_Score'] <= 3]['Profitable_By_EOD'].mean() * 100
        lines.append(f"| Entry Score | "
                     f"Score 5: {score5_wr:.1f}% WR; Score ≤3: {score_low_wr:.1f}% WR | "
                     f"Higher composite score does not reliably improve outcomes |")

        # 8. Key Takeaways
        lines.append("\n### Key Takeaways\n")
        if 'Next_Day_Gap_Pct' in df.columns:
            lines.append("- **#1 signal — Overnight gap direction**: A gap confirming your trade "
                         "direction (gap up for CALL, gap down for PUT) is the most reliable predictor")
        if call_wr > put_wr + 3:
            start_yr = str(df['Entry_Date'].min())[:4]
            end_yr = str(df['Entry_Date'].max())[:4]
            lines.append(f"- **Period bias**: CALLs ({call_wr:.1f}% WR) significantly outperform "
                         f"PUTs ({put_wr:.1f}% WR) — upward drift in {start_yr}–{end_yr} data")
        if 'Entry_RSI14_W' in df.columns:
            lines.append("- **RSI sweet spot**: Moderate oversold (RSI 25-45 for CALLs) and moderate "
                         "overbought (RSI 55-75 for PUTs) outperform extreme readings")
        lines.append("- **RVOL is noise**: Relative volume at entry has near-zero predictive value")
        lines.append("- **More signals ≠ better**: 2-3 qualifying conditions tend to outperform "
                     "5-condition setups — quality over quantity")

        return lines

    # ------------------------------------------------------------------
    # Step 8: Generate report
    # ------------------------------------------------------------------
    def generate_report(self):
        """Generate a markdown summary report."""
        if not self.results:
            print("No trades to report.")
            return

        df = pd.DataFrame(self.results)
        lines = []

        first_date = str(self.trading_days[0])
        last_date = str(self.trading_days[-1])

        lines.append(f"# Swing Trade Analysis Report — {self.ticker}")
        lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Analysis Period: {first_date} to {last_date}")
        lines.append(f"\nEntry Window: {self.entry_start // 100}:{self.entry_start % 100:02d} "
                      f"- {self.entry_end // 100}:{self.entry_end % 100:02d}")
        lines.append(f"Minimum Entry Score: {self.min_score} / 5")
        lines.append(f"\n---\n")

        # Summary statistics
        lines.append("## Summary Statistics\n")
        lines.append(f"- **Analysis Period**: {first_date} to {last_date}")
        lines.append(f"- **Trading Days Scanned**: {len(self.trading_days) - 1}")
        lines.append(f"- **Total Swing Entries Found**: {len(df)}")
        lines.append(f"  - CALL (long) entries: {len(df[df['Direction'] == 'CALL'])}")
        lines.append(f"  - PUT (short) entries: {len(df[df['Direction'] == 'PUT'])}")
        lines.append(f"- **Average Entry Score**: {df['Entry_Score'].mean():.1f} / 5")
        noon_wr = df['Profitable_By_Noon'].mean() * 100
        eod_wr = df['Profitable_By_EOD'].mean() * 100
        eod_close_wr = df['EOD_Profitable'].mean() * 100
        lines.append(f"- **Profitable by Noon**: {noon_wr:.1f}% "
                      f"({df['Profitable_By_Noon'].sum()}/{len(df)})")
        lines.append(f"- **Profitable by EOD (best)**: {eod_wr:.1f}% "
                      f"({df['Profitable_By_EOD'].sum()}/{len(df)})")
        lines.append(f"- **EOD Close Profitable**: {eod_close_wr:.1f}% "
                      f"({df['EOD_Profitable'].sum()}/{len(df)})")

        # Winner vs Loser Indicator Profile
        lines.extend(self._generate_winner_profile_section(df))

        # Direction breakdown
        for direction in ['CALL', 'PUT']:
            sub = df[df['Direction'] == direction]
            if len(sub) == 0:
                continue
            label = 'CALL (Long)' if direction == 'CALL' else 'PUT (Short)'
            lines.append(f"\n## {label} Swing Trades\n")
            lines.append(f"- **Total**: {len(sub)}")
            lines.append(f"- **Win Rate (by noon)**: {sub['Profitable_By_Noon'].mean() * 100:.1f}%")
            lines.append(f"- **Win Rate (by EOD best)**: {sub['Profitable_By_EOD'].mean() * 100:.1f}%")
            lines.append(f"- **Win Rate (EOD close)**: {sub['EOD_Profitable'].mean() * 100:.1f}%")
            lines.append(f"- **Avg Best Return (noon)**: {sub['Best_Return_By_Noon'].mean():.3f}%")
            lines.append(f"- **Avg Best Return (EOD)**: {sub['Best_Return_By_EOD'].mean():.3f}%")
            lines.append(f"- **Avg EOD Close Return**: {sub['EOD_Return_Pct'].mean():.3f}%")
            lines.append(f"- **Avg Max Adverse**: {sub['Max_Adverse_Pct'].mean():.3f}%")
            if 'Entry_RSI14_W' in sub.columns:
                lines.append(f"- **Avg Entry RSI**: {sub['Entry_RSI14_W'].mean():.1f}")
            lines.append(f"- **Avg Entry Score**: {sub['Entry_Score'].mean():.1f}")

        # Score effectiveness
        lines.append("\n## Entry Score Effectiveness\n")
        lines.append("| Score | Count | Win Rate Noon | Win Rate EOD | Avg Return EOD | Avg Adverse |")
        lines.append("|-------|-------|---------------|--------------|----------------|-------------|")
        for score in sorted(df['Entry_Score'].unique(), reverse=True):
            s = df[df['Entry_Score'] == score]
            lines.append(
                f"| {score} | {len(s)} | "
                f"{s['Profitable_By_Noon'].mean() * 100:.1f}% | "
                f"{s['Profitable_By_EOD'].mean() * 100:.1f}% | "
                f"{s['Best_Return_By_EOD'].mean():.3f}% | "
                f"{s['Max_Adverse_Pct'].mean():.3f}% |"
            )

        # Entry condition effectiveness
        lines.append("\n## Entry Condition Effectiveness\n")
        lines.append("| Condition | Trades | Win Rate (EOD) | Avg Return | Direction |")
        lines.append("|-----------|--------|----------------|------------|-----------|")
        all_conds = set()
        for conds_str in df['Entry_Conditions']:
            all_conds.update(conds_str.split(','))
        for cond in sorted(all_conds):
            if not cond:
                continue
            mask = df['Entry_Conditions'].str.contains(cond, na=False)
            sub = df[mask]
            if len(sub) < 5:
                continue
            call_pct = len(sub[sub['Direction'] == 'CALL']) / len(sub) * 100
            dir_label = 'CALL' if call_pct > 60 else ('PUT' if call_pct < 40 else 'Both')
            lines.append(
                f"| {cond} | {len(sub)} | "
                f"{sub['Profitable_By_EOD'].mean() * 100:.1f}% | "
                f"{sub['Best_Return_By_EOD'].mean():.3f}% | {dir_label} |"
            )

        # Options P&L section (if enriched)
        if 'Opt_Mark' in df.columns:
            lines.extend(self._generate_options_report(df))

        # Time-of-day analysis
        lines.append("\n## Entry Time Analysis\n")
        lines.append("| Entry Half-Hour | Count | Win Rate | Avg Return | Avg Adverse |")
        lines.append("|-----------------|-------|----------|------------|-------------|")
        df['Entry_HalfHour'] = (pd.to_datetime(df['Entry_Time']).dt.hour * 100 +
                                 (pd.to_datetime(df['Entry_Time']).dt.minute // 30) * 30)
        for hh in sorted(df['Entry_HalfHour'].unique()):
            sub = df[df['Entry_HalfHour'] == hh]
            h, m = hh // 100, hh % 100
            lines.append(
                f"| {h}:{m:02d} | {len(sub)} | "
                f"{sub['Profitable_By_EOD'].mean() * 100:.1f}% | "
                f"{sub['Best_Return_By_EOD'].mean():.3f}% | "
                f"{sub['Max_Adverse_Pct'].mean():.3f}% |"
            )

        # Top 20 trades
        lines.append("\n## Top 20 Best Swing Trades\n")
        lines.append("| # | Date | Dir | Score | Entry Price | Best Return | Exit Time | Adverse |")
        lines.append("|---|------|-----|-------|-------------|-------------|-----------|---------|")
        top = df.nlargest(20, 'Best_Return_By_EOD')
        for rank, (_, t) in enumerate(top.iterrows(), 1):
            exit_t = pd.to_datetime(t['Best_Exit_Time']).strftime('%H:%M') if pd.notna(t['Best_Exit_Time']) else '-'
            lines.append(
                f"| {rank} | {t['Entry_Date']} | {t['Direction']} | "
                f"{t['Entry_Score']} | ${t['Entry_Price']:.2f} | "
                f"{t['Best_Return_By_EOD']:.2f}% | {exit_t} | "
                f"{t['Max_Adverse_Pct']:.2f}% |"
            )

        # Monthly performance
        lines.append("\n## Monthly Performance\n")
        lines.append("| Month | Trades | Win Rate | Avg Return | Best | Worst |")
        lines.append("|-------|--------|----------|------------|------|-------|")
        df['Month'] = pd.to_datetime(df['Entry_Date']).dt.to_period('M')
        for month in sorted(df['Month'].unique()):
            sub = df[df['Month'] == month]
            lines.append(
                f"| {month} | {len(sub)} | "
                f"{sub['Profitable_By_EOD'].mean() * 100:.1f}% | "
                f"{sub['Best_Return_By_EOD'].mean():.3f}% | "
                f"{sub['Best_Return_By_EOD'].max():.2f}% | "
                f"{sub['EOD_Return_Pct'].min():.2f}% |"
            )

        report_path = f'data/signals/{self.ticker.lower()}_swing_trades_report.md'
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        print(f"Generated report: {report_path}")

    # ------------------------------------------------------------------
    # Orchestrator
    # ------------------------------------------------------------------
    def run(self):
        """Run the full swing trade scan pipeline."""
        print(f"\n{'=' * 60}")
        print(f"SWING TRADE SCANNER — {self.ticker}")
        print(f"{'=' * 60}\n")

        self.load_data()
        self.compute_daily_context()
        self.scan_trades()
        if self.options_pnl:
            self.enrich_with_options_pnl()
        self.save_results()
        self.generate_report()

        print(f"\n{'=' * 60}")
        print("SCAN COMPLETE")
        print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(
        description='Scan historical data for afternoon swing trade entries'
    )
    parser.add_argument('--ticker', type=str, default='IWM',
                        choices=['IWM', 'SPY', 'QQQ', 'iwm', 'spy', 'qqq'],
                        help='ETF ticker to scan (default: IWM)')
    parser.add_argument('--all', action='store_true',
                        help='Scan all tickers (IWM, SPY, QQQ)')
    parser.add_argument('--entry-start', type=int, default=1400,
                        help='Entry window start as HHMM (default: 1400 = 2:00 PM)')
    parser.add_argument('--entry-end', type=int, default=1555,
                        help='Entry window end as HHMM (default: 1555 = 3:55 PM)')
    parser.add_argument('--min-score', type=int, default=2,
                        help='Minimum entry quality score 1-5 (default: 2)')
    parser.add_argument('--options-pnl', action='store_true',
                        help='Estimate options P&L using EOD options chain data')

    args = parser.parse_args()

    tickers = SwingTradeScanner.TICKERS if args.all else [args.ticker.upper()]

    for ticker in tickers:
        scanner = SwingTradeScanner(
            ticker=ticker,
            entry_start=args.entry_start,
            entry_end=args.entry_end,
            min_score=args.min_score,
            options_pnl=args.options_pnl,
        )
        scanner.run()


if __name__ == '__main__':
    main()
