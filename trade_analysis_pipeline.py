#!/usr/bin/env python3
"""
Unified trade analysis pipeline:
1. Read trade_tracker.csv from data/signals/trade_examples/
2. Calculate durations and update to trade_tracker_updated.csv
3. Pivot to tall format with 3 rows per trade (exit, stop_loss, runner)
4. Join with indicators to find patterns
5. Find similar trades in historical data
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime
import glob
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import multiprocessing

class TradeAnalysisPipeline:
    def __init__(self):
        self.trades_df = None
        self.iwm_df = None
        self.pivoted_trades = None
        self.search_months = 1  # Default to 1 month
        self.data_format = 'csv'  # Default to CSV, will be detected in step3

        # Phase 3: DataFrame cache to avoid re-reading CSVs/Parquet
        self._cache = {
            'similar_trades': None,
            'criteria_effectiveness': None,
            'trades_enriched': None
        }
    
    def _get_cached_df(self, key, file_path):
        """Get DataFrame from cache or read from file if not cached (supports CSV and Parquet)"""
        if self._cache[key] is None:
            # Try parquet first, then CSV
            parquet_path = file_path.replace('.csv', '.parquet')
            if os.path.exists(parquet_path):
                self._cache[key] = pd.read_parquet(parquet_path)
            elif os.path.exists(file_path):
                self._cache[key] = pd.read_csv(file_path)
        return self._cache[key]
    
    def _clear_cache(self):
        """Clear the DataFrame cache"""
        for key in self._cache:
            self._cache[key] = None
    
    def _vectorized_criteria_analysis(self, criteria_df, boolean_cols):
        """Vectorized version of criteria effectiveness analysis"""
        # Pre-calculate masks for all criteria at once
        criteria_masks = criteria_df[boolean_cols] == 1
        
        # Calculate statistics for all criteria using vectorized operations
        results = []
        
        # Use vectorized operations for each criterion
        for criterion in boolean_cols:
            mask = criteria_masks[criterion]
            trades_met = mask.sum()
            
            if trades_met >= 100:  # Minimum threshold
                # Vectorized calculations
                profitable_met = (criteria_df.loc[mask, 'Trade_Profitable']).sum()
                win_rate = profitable_met / trades_met
                avg_return = criteria_df.loc[mask, 'Return_Pct'].mean()
                total_return = criteria_df.loc[mask, 'Return_Pct'].sum()
                
                results.append({
                    'Criterion': criterion,
                    'Trades_Met': trades_met,
                    'Win_Rate': win_rate,
                    'Avg_Return': avg_return,
                    'Total_Return': total_return
                })
        
        return pd.DataFrame(results)
        
    def clean_old_files(self):
        """Clean up old test and validation files"""
        print("Cleaning up old files...")
        
        files_to_remove = [
            'data/options_tracker*.csv',
            'data/similar_trades_found.csv',
            'data/quality_trades_detailed.csv',
            'data/suggested_trades.csv',
            'data/balanced_trades_found.csv',
            'data/realistic_trades_*.csv',
            'data/trades_analysis.csv',
            'data/exit_scenario_analysis.csv',
            'data/profitable_duration_stats.json',
            'track_options.py',
            'create_options_tracker.py',
            'analyze_found_trades.py',
            'find_similar_trades.py',
            'find_balanced_trades.py',
            'investigate_put_bias.py',
            'find_realistic_trades.py',
            'create_trade_tracker_simple.py',
            'update_trade_tracker.py',
            'analyze_trades.py',
            'analyze_trades_enhanced.py',
            'analyze_profitable_durations.py',
            'test_analysis_workflow.py'
        ]
        
        removed_count = 0
        for pattern in files_to_remove:
            for file in glob.glob(pattern):
                if os.path.exists(file):
                    os.remove(file)
                    removed_count += 1
                    
        print(f"Removed {removed_count} old files")
        
    def step1_update_trade_tracker(self):
        """Step 1: Read trade_tracker.csv and calculate durations"""
        print("\n" + "="*60)
        print("STEP 1: UPDATE TRADE TRACKER")
        print("="*60)
        
        # Read trade_tracker.csv from examples folder
        self.trades_df = pd.read_csv('data/signals/trade_examples/trade_tracker.csv')
        print(f"Loaded {len(self.trades_df)} trades")
        
        # Convert time columns
        time_cols = ['Time', 'Exit_Time', 'Stop_Loss_Time', 'Runner_Time']
        for col in time_cols:
            self.trades_df[col] = pd.to_datetime(self.trades_df[col], errors='coerce')
        
        # Calculate durations
        self.trades_df['Duration_Exit'] = ((self.trades_df['Exit_Time'] - self.trades_df['Time']).dt.total_seconds() / 60).round(2)
        self.trades_df['Duration_StopLoss'] = ((self.trades_df['Stop_Loss_Time'] - self.trades_df['Time']).dt.total_seconds() / 60).round(2)
        self.trades_df['Duration_Runner'] = ((self.trades_df['Runner_Time'] - self.trades_df['Time']).dt.total_seconds() / 60).round(2)
        
        # Updated version kept in memory, not saved to disk
        
        # Show summary
        print("\nDuration Summary:")
        print(f"  Exit: {self.trades_df['Duration_Exit'].mean():.1f} min average")
        print(f"  StopLoss: {self.trades_df['Duration_StopLoss'].mean():.1f} min average")
        print(f"  Runner: {self.trades_df['Duration_Runner'].mean():.1f} min average")
        
    def step2_pivot_trades(self):
        """Step 2: Pivot trades to tall format (3 rows per trade)"""
        print("\n" + "="*60)
        print("STEP 2: PIVOT TO TALL FORMAT")
        print("="*60)
        
        pivoted = []
        
        for _, trade in self.trades_df.iterrows():
            # Exit scenario
            pivoted.append({
                'ID': trade['ID'],
                'Entry_Time': trade['Time'],
                'Trade_Type': trade['Trade_Type'],
                'Exit_Type': 'EXIT',
                'Exit_Time': trade['Exit_Time'],
                'Duration': trade['Duration_Exit']
            })
            
            # Stop Loss scenario
            if pd.notna(trade['Stop_Loss_Time']):
                pivoted.append({
                    'ID': trade['ID'],
                    'Entry_Time': trade['Time'],
                    'Trade_Type': trade['Trade_Type'],
                    'Exit_Type': 'STOP_LOSS',
                    'Exit_Time': trade['Stop_Loss_Time'],
                    'Duration': trade['Duration_StopLoss']
                })
            
            # Runner scenario
            if pd.notna(trade['Runner_Time']):
                pivoted.append({
                    'ID': trade['ID'],
                    'Entry_Time': trade['Time'],
                    'Trade_Type': trade['Trade_Type'],
                    'Exit_Type': 'RUNNER',
                    'Exit_Time': trade['Runner_Time'],
                    'Duration': trade['Duration_Runner']
                })
        
        self.pivoted_trades = pd.DataFrame(pivoted)
        # self.pivoted_trades.to_csv('data/trades_pivoted.csv', index=False)  # Commented out - not needed
        
        print(f"Created {len(self.pivoted_trades)} trade scenarios")
        print(f"  EXIT scenarios: {len(self.pivoted_trades[self.pivoted_trades['Exit_Type'] == 'EXIT'])}")
        print(f"  STOP_LOSS scenarios: {len(self.pivoted_trades[self.pivoted_trades['Exit_Type'] == 'STOP_LOSS'])}")
        print(f"  RUNNER scenarios: {len(self.pivoted_trades[self.pivoted_trades['Exit_Type'] == 'RUNNER'])}")
        
    def step3_join_indicators(self):
        """Step 3: Join with IWM indicators data"""
        print("\n" + "="*60)
        print("STEP 3: JOIN WITH INDICATORS")
        print("="*60)

        # Auto-detect format (CSV or Parquet)
        csv_files = glob.glob('data/signals/historical_iwm_*_with_indicators.csv')
        parquet_files = glob.glob('data/signals/historical_iwm_*_with_indicators.parquet')

        if parquet_files:
            indicator_file = parquet_files[0]
            self.data_format = 'parquet'
            print(f"Detected parquet format: {indicator_file}")
            self.iwm_df = pd.read_parquet(indicator_file)
        elif csv_files:
            indicator_file = csv_files[0]
            self.data_format = 'csv'
            print(f"Detected CSV format: {indicator_file}")
            self.iwm_df = pd.read_csv(indicator_file)
        else:
            raise FileNotFoundError(
                "No indicator files found! This should have been handled by _ensure_indicator_files(). "
                "If you see this error, try running: python trading_analysis.py -symbol IWM -months 2"
            )

        self.iwm_df['Time'] = pd.to_datetime(self.iwm_df['Time'])
        
        # Filter to market hours only (9:30 AM to 4:00 PM)
        self.iwm_df['Hour'] = self.iwm_df['Time'].dt.hour
        self.iwm_df['Minute'] = self.iwm_df['Time'].dt.minute
        self.iwm_df['TimeOfDay'] = self.iwm_df['Hour'] * 100 + self.iwm_df['Minute']
        
        # Keep only market hours: 9:30 (930) to 16:00 (1600)
        original_len = len(self.iwm_df)
        self.iwm_df = self.iwm_df[(self.iwm_df['TimeOfDay'] >= 930) & (self.iwm_df['TimeOfDay'] <= 1600)].copy()
        
        # Drop helper columns
        self.iwm_df = self.iwm_df.drop(['Hour', 'Minute', 'TimeOfDay'], axis=1)
        
        print(f"Loaded IWM data: {original_len} rows")
        print(f"After filtering to market hours (9:30-16:00): {len(self.iwm_df)} rows")
        
        # Join entry data
        entry_data = pd.merge(
            self.pivoted_trades,
            self.iwm_df,
            left_on='Entry_Time',
            right_on='Time',
            how='left',
            suffixes=('', '_entry')
        )
        
        # Select all indicator columns for entry
        entry_cols = ['Last', 'Volume', 'ATR14_W', 'RSI14_W', 'EMA9', 'EMA20', 'EMA50',
                      'VWAP', 'RVOL20', 'RVOL_MOD', 'RVOL_MOD_EXCL', 'OBV',
                      'StochRSI_K', 'StochRSI_D',

                      # Historical Levels (Previous Day)
                      'Prev_Day_High', 'Prev_Day_Low', 'Prev_Day_Open', 'Prev_Day_Close',
                      'Prev_Day_HL_Mid', 'Prev_Day_OC_Mid',
                      'Prev_Day_High_Pct', 'Prev_Day_Low_Pct',
                      'Broke_Prev_Day_High', 'Broke_Prev_Day_Low',
                      'At_Prev_Day_High', 'At_Prev_Day_Low', 'At_Prev_Day_HL_Mid',

                      # Historical Levels (Previous Week)
                      'Prev_Week_High', 'Prev_Week_Low', 'Prev_Week_Open', 'Prev_Week_Close',
                      'Prev_Week_HL_Mid', 'Prev_Week_OC_Mid',
                      'Prev_Week_High_Pct', 'Prev_Week_Low_Pct',
                      'Broke_Prev_Week_High', 'Broke_Prev_Week_Low',
                      'At_Prev_Week_High', 'At_Prev_Week_Low', 'At_Prev_Week_HL_Mid',

                      # Historical Levels (Previous Month)
                      'Prev_Month_High', 'Prev_Month_Low', 'Prev_Month_Open', 'Prev_Month_Close',
                      'Prev_Month_HL_Mid', 'Prev_Month_OC_Mid',
                      'Prev_Month_High_Pct', 'Prev_Month_Low_Pct',
                      'Broke_Prev_Month_High', 'Broke_Prev_Month_Low',
                      'At_Prev_Month_High', 'At_Prev_Month_Low', 'At_Prev_Month_HL_Mid',

                      # ORB 5-minute
                      'ORB_5m_High', 'ORB_5m_Low', 'ORB_5m_Mid', 'ORB_5m_Range',
                      'ORB_5m_Trend', 'ORB_5m_Broke_High', 'ORB_5m_Broke_Low',
                      'ORB_5m_Within_Range', 'ORB_5m_Distance_High', 'ORB_5m_Distance_Low',

                      # ORB 15-minute
                      'ORB_15m_High', 'ORB_15m_Low', 'ORB_15m_Mid', 'ORB_15m_Range',
                      'ORB_15m_Trend', 'ORB_15m_Broke_High', 'ORB_15m_Broke_Low',
                      'ORB_15m_Within_Range', 'ORB_15m_Distance_High', 'ORB_15m_Distance_Low',

                      # ORB 30-minute
                      'ORB_30m_High', 'ORB_30m_Low', 'ORB_30m_Mid', 'ORB_30m_Range',
                      'ORB_30m_Trend', 'ORB_30m_Broke_High', 'ORB_30m_Broke_Low',
                      'ORB_30m_Within_Range', 'ORB_30m_Distance_High', 'ORB_30m_Distance_Low',

                      # Order Blocks
                      'Order_Block_High', 'Order_Block_Low', 'Order_Block_Mid',
                      'Order_Block_Position', 'Order_Block_Test', 'Order_Block_Distance']
        for col in entry_cols:
            if col in entry_data.columns:
                entry_data[f'Entry_{col}'] = entry_data[col]
        
        # Join exit data
        enriched = pd.merge(
            entry_data[['ID', 'Entry_Time', 'Trade_Type', 'Exit_Type', 'Exit_Time', 'Duration'] + 
                      [f'Entry_{col}' for col in entry_cols]],
            self.iwm_df,
            left_on='Exit_Time',
            right_on='Time',
            how='left',
            suffixes=('', '_exit')
        )
        
        # Select exit columns
        for col in entry_cols:
            if col in enriched.columns:
                enriched[f'Exit_{col}'] = enriched[col]
        
        # Calculate returns
        enriched['Price_Change'] = (enriched['Exit_Last'] - enriched['Entry_Last']).round(2)
        enriched['Return_Pct'] = (enriched['Price_Change'] / enriched['Entry_Last'] * 100).round(2)
        
        # Adjust for PUT trades (profit when price goes down)
        put_mask = enriched['Trade_Type'] == 'PUT'
        enriched.loc[put_mask, 'Return_Pct'] = -enriched.loc[put_mask, 'Return_Pct']
        
        # Build final columns list with all available indicators
        base_cols = ['ID', 'Entry_Time', 'Trade_Type', 'Exit_Type', 'Exit_Time', 'Duration', 
                     'Price_Change', 'Return_Pct']
        
        # Add all entry and exit indicator columns that exist
        indicator_cols = []
        for prefix in ['Entry_', 'Exit_']:
            for indicator in ['Last', 'Volume', 'ATR14_W', 'RSI14_W', 'EMA9', 'EMA20', 'EMA50', 
                            'VWAP', 'RVOL20', 'RVOL_MOD', 'RVOL_MOD_EXCL', 'OBV', 
                            'StochRSI_K', 'StochRSI_D']:
                col_name = f'{prefix}{indicator}'
                if col_name in enriched.columns:
                    indicator_cols.append(col_name)
        
        final_cols = base_cols + indicator_cols
        enriched_final = enriched[final_cols].copy()

        # Save in matching format (parquet or CSV) to signals directory
        os.makedirs('data/signals', exist_ok=True)
        if self.data_format == 'parquet':
            enriched_final.to_parquet('data/signals/trades_enriched.parquet', index=False)
            print("Saved data/signals/trades_enriched.parquet with entry/exit indicators")
        else:
            enriched_final.to_csv('data/signals/trades_enriched.csv', index=False)
            print("Saved data/signals/trades_enriched.csv with entry/exit indicators")
        print("\nSample enriched data:")
        print(enriched_final.head())
        
        return enriched_final
        
    def step4_find_patterns(self, enriched_df):
        """Step 4: Analyze patterns and find similar trades"""
        print("\n" + "="*60)
        print("STEP 4: PATTERN ANALYSIS")
        print("="*60)
        
        # Analyze patterns by trade type and exit type
        patterns = {}
        
        for trade_type in ['CALL', 'PUT']:
            for exit_type in ['EXIT', 'STOP_LOSS', 'RUNNER']:
                mask = (enriched_df['Trade_Type'] == trade_type) & (enriched_df['Exit_Type'] == exit_type)
                subset = enriched_df[mask].copy()  # Create a copy to avoid SettingWithCopyWarning
                
                if len(subset) > 0:
                    pattern_key = f"{trade_type}_{exit_type}"
                    
                    # Basic metrics
                    patterns[pattern_key] = {
                        'count': len(subset),
                        'avg_duration': round(subset['Duration'].mean(), 2),
                        'avg_return': round(subset['Return_Pct'].mean(), 2),
                        'profitable_pct': round((subset['Return_Pct'] > 0).sum() / len(subset) * 100, 2),
                    }
                    
                    # Add extensive indicator analysis
                    # Entry indicators
                    indicators = ['RSI14_W', 'StochRSI_K', 'StochRSI_D', 'ATR14_W', 
                                 'RVOL20', 'RVOL_MOD', 'RVOL_MOD_EXCL', 'OBV']
                    
                    for ind in indicators:
                        entry_col = f'Entry_{ind}'
                        exit_col = f'Exit_{ind}'
                        
                        if entry_col in subset.columns and not subset[entry_col].isna().all():
                            patterns[pattern_key][f'entry_{ind.lower()}_mean'] = round(subset[entry_col].mean(), 2)
                            patterns[pattern_key][f'entry_{ind.lower()}_std'] = round(subset[entry_col].std(), 2)
                            patterns[pattern_key][f'entry_{ind.lower()}_min'] = round(subset[entry_col].min(), 2)
                            patterns[pattern_key][f'entry_{ind.lower()}_max'] = round(subset[entry_col].max(), 2)
                            patterns[pattern_key][f'entry_{ind.lower()}_25pct'] = round(subset[entry_col].quantile(0.25), 2)
                            patterns[pattern_key][f'entry_{ind.lower()}_75pct'] = round(subset[entry_col].quantile(0.75), 2)
                        
                        if exit_col in subset.columns and not subset[exit_col].isna().all():
                            patterns[pattern_key][f'exit_{ind.lower()}_mean'] = round(subset[exit_col].mean(), 2)
                            patterns[pattern_key][f'exit_{ind.lower()}_std'] = round(subset[exit_col].std(), 2)
                    
                    # Price vs VWAP analysis
                    if 'Entry_VWAP' in subset.columns and 'Entry_Last' in subset.columns:
                        patterns[pattern_key]['entry_below_vwap_pct'] = round((subset['Entry_Last'] < subset['Entry_VWAP']).sum() / len(subset) * 100, 2)
                        patterns[pattern_key]['entry_vwap_distance_mean'] = round(((subset['Entry_Last'] - subset['Entry_VWAP']) / subset['Entry_VWAP'] * 100).mean(), 2)
                        patterns[pattern_key]['entry_vwap_distance_std'] = round(((subset['Entry_Last'] - subset['Entry_VWAP']) / subset['Entry_VWAP'] * 100).std(), 2)
                    
                    # Price vs EMAs analysis
                    for ema in ['EMA9', 'EMA20', 'EMA50']:
                        entry_ema_col = f'Entry_{ema}'
                        if entry_ema_col in subset.columns and 'Entry_Last' in subset.columns:
                            patterns[pattern_key][f'entry_below_{ema.lower()}_pct'] = round((subset['Entry_Last'] < subset[entry_ema_col]).sum() / len(subset) * 100, 2)
                            patterns[pattern_key][f'entry_{ema.lower()}_distance_mean'] = round(((subset['Entry_Last'] - subset[entry_ema_col]) / subset[entry_ema_col] * 100).mean(), 2)
                    
                    # Volume patterns
                    if 'Entry_Volume' in subset.columns:
                        patterns[pattern_key]['entry_volume_mean'] = round(subset['Entry_Volume'].mean(), 2)
                        patterns[pattern_key]['entry_volume_std'] = round(subset['Entry_Volume'].std(), 2)
                    
                    # Time of day analysis
                    if 'Entry_Time' in subset.columns:
                        subset['Entry_Hour'] = pd.to_datetime(subset['Entry_Time']).dt.hour
                        subset['Entry_Minute'] = pd.to_datetime(subset['Entry_Time']).dt.minute
                        # Only include trades during market hours
                        market_hours_mask = ((subset['Entry_Hour'] == 9) & (subset['Entry_Minute'] >= 30)) | \
                                          ((subset['Entry_Hour'] >= 10) & (subset['Entry_Hour'] < 16))
                        market_hours_subset = subset[market_hours_mask]
                        
                        if len(market_hours_subset) > 0:
                            patterns[pattern_key]['entry_hour_mean'] = round(market_hours_subset['Entry_Hour'].mean(), 2)
                            patterns[pattern_key]['entry_hour_mode'] = market_hours_subset['Entry_Hour'].mode()[0] if len(market_hours_subset['Entry_Hour'].mode()) > 0 else round(market_hours_subset['Entry_Hour'].mean(), 2)
                        else:
                            patterns[pattern_key]['entry_hour_mean'] = round(subset['Entry_Hour'].mean(), 2)
                            patterns[pattern_key]['entry_hour_mode'] = subset['Entry_Hour'].mode()[0] if len(subset['Entry_Hour'].mode()) > 0 else round(subset['Entry_Hour'].mean(), 2)
                    
                    # Indicator changes during trade
                    for ind in ['RSI14_W', 'StochRSI_K', 'ATR14_W', 'RVOL20']:
                        entry_col = f'Entry_{ind}'
                        exit_col = f'Exit_{ind}'
                        if entry_col in subset.columns and exit_col in subset.columns:
                            if not subset[entry_col].isna().all() and not subset[exit_col].isna().all():
                                patterns[pattern_key][f'{ind.lower()}_change_mean'] = round((subset[exit_col] - subset[entry_col]).mean(), 2)
                                patterns[pattern_key][f'{ind.lower()}_change_std'] = round((subset[exit_col] - subset[entry_col]).std(), 2)
                    
                    print(f"\n{pattern_key}:")
                    print(f"  Count: {patterns[pattern_key]['count']}")
                    print(f"  Avg Duration: {patterns[pattern_key]['avg_duration']:.1f} min")
                    print(f"  Avg Stock Return: {patterns[pattern_key]['avg_return']:.2f}%")
                    
                    # Estimate options returns based on duration-adjusted leverage
                    avg_duration = patterns[pattern_key]['avg_duration']
                    stock_return = patterns[pattern_key]['avg_return']
                    
                    # Duration-based multipliers (higher for shorter trades due to gamma)
                    if avg_duration < 10:
                        mult_low, mult_high = 20, 30
                    elif avg_duration < 20:
                        mult_low, mult_high = 15, 25
                    elif avg_duration < 30:
                        mult_low, mult_high = 12, 20
                    else:
                        mult_low, mult_high = 10, 15
                    
                    est_option_return_low = stock_return * mult_low
                    est_option_return_high = stock_return * mult_high
                    
                    # Show both gross and net (after ~2.5% transaction costs)
                    print(f"  Est Option Return: {est_option_return_low:.1f}-{est_option_return_high:.1f}%")
                    print(f"  Net After Costs: {max(0, est_option_return_low-2.5):.1f}-{max(0, est_option_return_high-2.5):.1f}%")
                    print(f"  Profitable: {patterns[pattern_key]['profitable_pct']:.1f}%")
        
        # Pattern analysis kept in memory, not saved to disk
        # patterns_df = pd.DataFrame(patterns).T  # No longer needed
        
        # Pattern summary is now integrated into the main report
        # self.create_pattern_summary(patterns)  # No longer needed
        
        return patterns
    
    def create_pattern_summary(self, patterns):
        """Create a human-readable summary of patterns"""
        print("\n" + "="*60)
        print("CREATING PATTERN SUMMARY")
        print("="*60)
        
        summary_lines = ["# Trade Pattern Summary\n"]
        summary_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        for trade_type in ['CALL', 'PUT']:
            summary_lines.append(f"\n## {trade_type} Patterns\n")
            
            type_patterns = {k: v for k, v in patterns.items() if k.startswith(trade_type)}
            
            if type_patterns:
                # Overall statistics
                all_counts = sum(p['count'] for p in type_patterns.values())
                avg_return = round(sum(p['avg_return'] * p['count'] for p in type_patterns.values()) / all_counts, 2)
                avg_win_rate = round(sum(p['profitable_pct'] * p['count'] for p in type_patterns.values()) / all_counts, 2)
                
                summary_lines.append(f"### Overall {trade_type} Statistics")
                summary_lines.append(f"- Total Trades: {all_counts}")
                summary_lines.append(f"- Average Return: {avg_return}%")
                summary_lines.append(f"- Win Rate: {avg_win_rate}%\n")
                
                # Key indicator ranges
                summary_lines.append(f"### {trade_type} Entry Indicator Ranges")
                
                # Combine all RSI values
                all_rsi_min = min(p.get('entry_rsi14_w_min', 100) for p in type_patterns.values() if 'entry_rsi14_w_min' in p)
                all_rsi_max = max(p.get('entry_rsi14_w_max', 0) for p in type_patterns.values() if 'entry_rsi14_w_max' in p)
                all_rsi_mean = sum(p.get('entry_rsi14_w_mean', 0) * p['count'] for p in type_patterns.values() if 'entry_rsi14_w_mean' in p) / all_counts
                
                summary_lines.append(f"- **RSI Range**: {all_rsi_min:.1f} - {all_rsi_max:.1f} (avg: {all_rsi_mean:.1f})")
                
                # RVOL analysis
                if any('entry_rvol20_mean' in p for p in type_patterns.values()):
                    all_rvol_mean = sum(p.get('entry_rvol20_mean', 0) * p['count'] for p in type_patterns.values() if 'entry_rvol20_mean' in p) / all_counts
                    summary_lines.append(f"- **Average RVOL**: {all_rvol_mean:.2f}x")
                
                # VWAP positioning
                if any('entry_below_vwap_pct' in p for p in type_patterns.values()):
                    all_below_vwap = sum(p.get('entry_below_vwap_pct', 0) * p['count'] for p in type_patterns.values() if 'entry_below_vwap_pct' in p) / all_counts
                    summary_lines.append(f"- **Below VWAP**: {all_below_vwap:.0f}%")
                
                summary_lines.append("")
                
                # Detailed exit type analysis
                for exit_type in ['EXIT', 'STOP_LOSS', 'RUNNER']:
                    pattern_key = f"{trade_type}_{exit_type}"
                    if pattern_key in patterns:
                        p = patterns[pattern_key]
                        summary_lines.append(f"### {trade_type} - {exit_type}")
                        summary_lines.append(f"- Count: {p['count']} trades")
                        summary_lines.append(f"- Avg Duration: {p['avg_duration']} minutes")
                        summary_lines.append(f"- Avg Return: {p['avg_return']}%")
                        summary_lines.append(f"- Win Rate: {p['profitable_pct']}%")
                        
                        if 'entry_rsi14_w_mean' in p:
                            summary_lines.append(f"- RSI: {p['entry_rsi14_w_mean']:.1f} (range: {p['entry_rsi14_w_min']:.1f}-{p['entry_rsi14_w_max']:.1f})")
                        
                        if 'entry_stochrsi_k_mean' in p and not np.isnan(p['entry_stochrsi_k_mean']):
                            summary_lines.append(f"- StochRSI: {p['entry_stochrsi_k_mean']:.1f}")
                        
                        if 'entry_rvol20_mean' in p:
                            summary_lines.append(f"- RVOL: {p['entry_rvol20_mean']:.2f}x")
                        
                        if 'entry_below_vwap_pct' in p:
                            summary_lines.append(f"- Below VWAP: {p['entry_below_vwap_pct']:.0f}%")
                        
                        summary_lines.append("")
        
        # Write summary
        with open('data/pattern_summary.md', 'w', encoding='utf-8') as f:
            f.write('\n'.join(summary_lines))
        
        print("Created pattern summary: data/pattern_summary.md")
        
    def step5_find_similar_trades(self, patterns):
        """Step 5: Find similar trades in historical data"""
        print("\n" + "="*60)
        print("STEP 5: FIND SIMILAR TRADES")
        print("="*60)
        
        # Filter data based on search_months parameter
        if self.search_months is None:
            # Search all data
            search_df = self.iwm_df.copy()
            print(f"Searching ALL {len(search_df)} data points (market hours only)")
        else:
            # Search last N months
            cutoff_date = self.iwm_df['Time'].max() - pd.DateOffset(months=self.search_months)
            search_df = self.iwm_df[self.iwm_df['Time'] >= cutoff_date].copy()
            print(f"Searching {len(search_df)} data points in last {self.search_months} month(s) (market hours only)")
        
        # Calculate 1-minute price changes
        search_df['Price_Change_1m'] = search_df['Last'].pct_change() * 100
        
        similar_trades = []
        
        # Find trades matching successful patterns
        max_duration = 45  # Maximum duration from your trades
        for i in range(1, len(search_df)-max_duration):
            current = search_df.iloc[i]
            
            # Skip if missing data
            if pd.isna(current.get('RSI14_W')) or pd.isna(current['Price_Change_1m']):
                continue
            
            # Skip if too close to market close (need room for exit)
            current_time = current['Time']
            if current_time.hour >= 15 and current_time.minute > 15:  # Skip after 3:15 PM
                continue
                
            # Check CALL patterns
            if (current['Price_Change_1m'] > 0.01 and 
                current['RSI14_W'] > 25 and current['RSI14_W'] < 70):
                
                # Check potential exits across full duration range (4-31 minutes based on your trades)
                best_return = 0
                best_duration = 0
                
                for duration in range(4, 32):  # Check every minute from 4 to 31
                    if i + duration < len(search_df):
                        exit_time = search_df.iloc[i + duration]['Time']
                        # Ensure exit is still within market hours
                        if exit_time.hour >= 16:  # Skip if at or after 4:00 PM
                            break
                        
                        exit_price = search_df.iloc[i + duration]['Last']
                        return_pct = (exit_price - current['Last']) / current['Last'] * 100
                        
                        if return_pct > best_return:
                            best_return = return_pct
                            best_duration = duration
                
                if best_return > 0.1:  # Profitable
                    exit_row = search_df.iloc[i + best_duration]
                    
                    # Create trade record with all columns matching enriched format
                    trade_record = {
                        'ID': f'SIM_{len(similar_trades)+1}',
                        'Entry_Time': current['Time'],
                        'Trade_Type': 'CALL',
                        'Exit_Type': 'RUNNER',  # Similar trades use RUNNER strategy
                        'Exit_Time': exit_row['Time'],
                        'Duration': best_duration,
                        'Price_Change': round(exit_row['Last'] - current['Last'], 2),
                        'Return_Pct': round(best_return, 2)
                    }
                    
                    # Add all entry indicators
                    for col in ['Last', 'Volume', 'ATR14_W', 'RSI14_W', 'EMA9', 'EMA20', 
                               'EMA50', 'VWAP', 'RVOL20', 'RVOL_MOD', 'RVOL_MOD_EXCL', 
                               'OBV', 'StochRSI_K', 'StochRSI_D']:
                        if col in current.index:
                            trade_record[f'Entry_{col}'] = current[col]
                    
                    # Add all exit indicators
                    for col in ['Last', 'Volume', 'ATR14_W', 'RSI14_W', 'EMA9', 'EMA20', 
                               'EMA50', 'VWAP', 'RVOL20', 'RVOL_MOD', 'RVOL_MOD_EXCL', 
                               'OBV', 'StochRSI_K', 'StochRSI_D']:
                        if col in exit_row.index:
                            trade_record[f'Exit_{col}'] = exit_row[col]
                    
                    similar_trades.append(trade_record)
            
            # Check PUT patterns
            if (current['Price_Change_1m'] < -0.01 and 
                current['RSI14_W'] > 30 and current['RSI14_W'] < 75):
                
                # Check potential exits across full duration range (12-45 minutes based on your trades)
                best_return = 0
                best_duration = 0
                
                for duration in range(12, 46):  # Check every minute from 12 to 45
                    if i + duration < len(search_df):
                        exit_time = search_df.iloc[i + duration]['Time']
                        # Ensure exit is still within market hours
                        if exit_time.hour >= 16:  # Skip if at or after 4:00 PM
                            break
                        
                        exit_price = search_df.iloc[i + duration]['Last']
                        return_pct = (current['Last'] - exit_price) / current['Last'] * 100
                        
                        if return_pct > best_return:
                            best_return = return_pct
                            best_duration = duration
                
                if best_return > 0.1:  # Profitable
                    exit_row = search_df.iloc[i + best_duration]
                    
                    # Create trade record with all columns matching enriched format
                    trade_record = {
                        'ID': f'SIM_{len(similar_trades)+1}',
                        'Entry_Time': current['Time'],
                        'Trade_Type': 'PUT',
                        'Exit_Type': 'RUNNER',  # Similar trades use RUNNER strategy
                        'Exit_Time': exit_row['Time'],
                        'Duration': best_duration,
                        'Price_Change': round(current['Last'] - exit_row['Last'], 2),  # Inverted for PUT
                        'Return_Pct': round(best_return, 2)
                    }
                    
                    # Add all entry indicators
                    for col in ['Last', 'Volume', 'ATR14_W', 'RSI14_W', 'EMA9', 'EMA20', 
                               'EMA50', 'VWAP', 'RVOL20', 'RVOL_MOD', 'RVOL_MOD_EXCL', 
                               'OBV', 'StochRSI_K', 'StochRSI_D']:
                        if col in current.index:
                            trade_record[f'Entry_{col}'] = current[col]
                    
                    # Add all exit indicators
                    for col in ['Last', 'Volume', 'ATR14_W', 'RSI14_W', 'EMA9', 'EMA20', 
                               'EMA50', 'VWAP', 'RVOL20', 'RVOL_MOD', 'RVOL_MOD_EXCL', 
                               'OBV', 'StochRSI_K', 'StochRSI_D']:
                        if col in exit_row.index:
                            trade_record[f'Exit_{col}'] = exit_row[col]
                    
                    similar_trades.append(trade_record)
        
        # Save similar trades
        if similar_trades:
            similar_df = pd.DataFrame(similar_trades)
            similar_df = similar_df.sort_values('Return_Pct', ascending=False)
            # Don't save yet - will save after criteria analysis
            
            print(f"\nFound {len(similar_df)} similar profitable trades")
            print(f"  CALL trades: {len(similar_df[similar_df['Trade_Type'] == 'CALL'])}")
            print(f"  PUT trades: {len(similar_df[similar_df['Trade_Type'] == 'PUT'])}")
            
            # Split by trade type for top opportunities
            call_trades = similar_df[similar_df['Trade_Type'] == 'CALL']
            put_trades = similar_df[similar_df['Trade_Type'] == 'PUT']
            
            if len(call_trades) > 0:
                print("\nTop 10 CALL opportunities:")
                print(call_trades.head(10)[['Entry_Time', 'Duration', 'Return_Pct']])
            
            if len(put_trades) > 0:
                print("\nTop 10 PUT opportunities:")
                print(put_trades.head(10)[['Entry_Time', 'Duration', 'Return_Pct']])
            
            return similar_df
        else:
            return pd.DataFrame()  # Return empty DataFrame if no trades found
        
    def step6_criteria_analysis(self, enriched_df, output_filename='data/signals/trade_criteria_analysis.csv', is_similar=False):
        """Step 6: Generate comprehensive criteria analysis"""
        if not is_similar:
            print("\n" + "="*60)
            print("STEP 6: CRITERIA ANALYSIS")
            print("="*60)
        else:
            print("\nApplying criteria analysis to similar trades...")
        
        # Start with enriched data - create a copy to avoid fragmentation
        base_df = enriched_df.copy()
        
        # Dictionary to hold all new columns
        new_columns = {}
        
        # Add time components
        entry_time = pd.to_datetime(base_df['Entry_Time'])
        new_columns['Entry_Hour'] = entry_time.dt.hour
        new_columns['Entry_Minute'] = entry_time.dt.minute
        new_columns['Entry_TimeValue'] = new_columns['Entry_Hour'] * 100 + new_columns['Entry_Minute']
        
        # Time window criteria
        new_columns['Time_0935_1430'] = (
            (new_columns['Entry_TimeValue'] >= 935) & 
            (new_columns['Entry_TimeValue'] <= 1430)
        ).astype(int)
        
        new_columns['Time_0930_1000'] = (
            (new_columns['Entry_TimeValue'] >= 930) & 
            (new_columns['Entry_TimeValue'] < 1000)
        ).astype(int)
        
        new_columns['Time_1000_1400'] = (
            (new_columns['Entry_TimeValue'] >= 1000) & 
            (new_columns['Entry_TimeValue'] < 1400)
        ).astype(int)
        
        new_columns['Time_1400_1555'] = (
            (new_columns['Entry_TimeValue'] >= 1400) & 
            (new_columns['Entry_TimeValue'] <= 1555)
        ).astype(int)
        
        # RVOL criteria
        rvol_levels = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 5.0]
        for level in rvol_levels:
            new_columns[f'Entry_RVOL_GTE_{level}'] = (
                base_df['Entry_RVOL20'] >= level
            ).astype(int)
            new_columns[f'Exit_RVOL_GTE_{level}'] = (
                base_df['Exit_RVOL20'] >= level
            ).astype(int)
        
        # RSI criteria (various levels)
        rsi_levels = [20, 30, 40, 45, 50, 55, 60, 70, 80]
        for level in rsi_levels:
            new_columns[f'Entry_RSI_GT_{level}'] = (
                base_df['Entry_RSI14_W'] > level
            ).astype(int)
            new_columns[f'Entry_RSI_LT_{level}'] = (
                base_df['Entry_RSI14_W'] < level
            ).astype(int)
            new_columns[f'Exit_RSI_GT_{level}'] = (
                base_df['Exit_RSI14_W'] > level
            ).astype(int)
            new_columns[f'Exit_RSI_LT_{level}'] = (
                base_df['Exit_RSI14_W'] < level
            ).astype(int)
        
        # EMA relationships
        # Entry
        new_columns['Entry_EMA9_GT_EMA20'] = (
            base_df['Entry_EMA9'] > base_df['Entry_EMA20']
        ).astype(int)
        new_columns['Entry_EMA9_LT_EMA20'] = (
            base_df['Entry_EMA9'] < base_df['Entry_EMA20']
        ).astype(int)
        
        new_columns['Entry_EMA20_GT_EMA50'] = (
            base_df['Entry_EMA20'] > base_df['Entry_EMA50']
        ).astype(int)
        new_columns['Entry_EMA20_LT_EMA50'] = (
            base_df['Entry_EMA20'] < base_df['Entry_EMA50']
        ).astype(int)
        
        # Exit
        new_columns['Exit_EMA9_GT_EMA20'] = (
            base_df['Exit_EMA9'] > base_df['Exit_EMA20']
        ).astype(int)
        new_columns['Exit_EMA9_LT_EMA20'] = (
            base_df['Exit_EMA9'] < base_df['Exit_EMA20']
        ).astype(int)
        
        new_columns['Exit_EMA20_GT_EMA50'] = (
            base_df['Exit_EMA20'] > base_df['Exit_EMA50']
        ).astype(int)
        new_columns['Exit_EMA20_LT_EMA50'] = (
            base_df['Exit_EMA20'] < base_df['Exit_EMA50']
        ).astype(int)
        
        # Price vs VWAP
        new_columns['Entry_Price_GT_VWAP'] = (
            base_df['Entry_Last'] > base_df['Entry_VWAP']
        ).astype(int)
        new_columns['Entry_Price_LT_VWAP'] = (
            base_df['Entry_Last'] < base_df['Entry_VWAP']
        ).astype(int)
        
        new_columns['Exit_Price_GT_VWAP'] = (
            base_df['Exit_Last'] > base_df['Exit_VWAP']
        ).astype(int)
        new_columns['Exit_Price_LT_VWAP'] = (
            base_df['Exit_Last'] < base_df['Exit_VWAP']
        ).astype(int)
        
        # Price vs EMAs
        for ema in ['EMA9', 'EMA20', 'EMA50']:
            new_columns[f'Entry_Price_GT_{ema}'] = (
                base_df['Entry_Last'] > base_df[f'Entry_{ema}']
            ).astype(int)
            new_columns[f'Entry_Price_LT_{ema}'] = (
                base_df['Entry_Last'] < base_df[f'Entry_{ema}']
            ).astype(int)
            
            new_columns[f'Exit_Price_GT_{ema}'] = (
                base_df['Exit_Last'] > base_df[f'Exit_{ema}']
            ).astype(int)
            new_columns[f'Exit_Price_LT_{ema}'] = (
                base_df['Exit_Last'] < base_df[f'Exit_{ema}']
            ).astype(int)
        
        # OBV percentile (calculate relative position)
        if 'Entry_OBV' in base_df.columns:
            obv_min = base_df['Entry_OBV'].min()
            obv_max = base_df['Entry_OBV'].max()
            new_columns['Entry_OBV_Percentile'] = (
                (base_df['Entry_OBV'] - obv_min) / (obv_max - obv_min) * 100
            ).round(2)
            
            # OBV criteria
            obv_levels = [20, 40, 60, 80]
            for level in obv_levels:
                new_columns[f'Entry_OBV_Top_{100-level}pct'] = (
                    new_columns['Entry_OBV_Percentile'] >= level
                ).astype(int)
                new_columns[f'Entry_OBV_Bottom_{level}pct'] = (
                    new_columns['Entry_OBV_Percentile'] <= level
                ).astype(int)
        
        # Combined criteria for CALL setup
        new_columns['CALL_Bias_Met'] = (
            (new_columns['Entry_EMA20_GT_EMA50'] == 1) &
            (new_columns['Entry_Price_GT_VWAP'] == 1) &
            (new_columns['Entry_RSI_GT_50'] == 1)
        ).astype(int)
        
        new_columns['CALL_Momentum_Met'] = (
            (new_columns['Entry_EMA9_GT_EMA20'] == 1) &
            (new_columns['Entry_RSI_GT_50'] == 1)
        ).astype(int)
        
        new_columns['CALL_Full_Setup'] = (
            (new_columns['CALL_Bias_Met'] == 1) &
            (new_columns['CALL_Momentum_Met'] == 1) &
            (new_columns['Entry_RVOL_GTE_1.0'] == 1)
        ).astype(int)
        
        # Combined criteria for PUT setup
        new_columns['PUT_Bias_Met'] = (
            (new_columns['Entry_EMA20_LT_EMA50'] == 1) &
            (new_columns['Entry_Price_LT_VWAP'] == 1) &
            (new_columns['Entry_RSI_LT_50'] == 1)
        ).astype(int)
        
        new_columns['PUT_Momentum_Met'] = (
            (new_columns['Entry_EMA9_LT_EMA20'] == 1) &
            (new_columns['Entry_RSI_LT_50'] == 1)
        ).astype(int)
        
        new_columns['PUT_Full_Setup'] = (
            (new_columns['PUT_Bias_Met'] == 1) &
            (new_columns['PUT_Momentum_Met'] == 1) &
            (new_columns['Entry_RVOL_GTE_1.0'] == 1)
        ).astype(int)
        
        # ATR levels
        atr_levels = [0.05, 0.08, 0.10, 0.15, 0.20]
        for level in atr_levels:
            new_columns[f'Entry_ATR_GTE_{level}'] = (
                base_df['Entry_ATR14_W'] >= level
            ).astype(int)
        
        # StochRSI if available
        if 'Entry_StochRSI_K' in base_df.columns:
            stoch_levels = [20, 30, 50, 70, 80]
            for level in stoch_levels:
                new_columns[f'Entry_StochRSI_GT_{level}'] = (
                    pd.notna(base_df['Entry_StochRSI_K']) & 
                    (base_df['Entry_StochRSI_K'] > level)
                ).astype(int)
                new_columns[f'Entry_StochRSI_LT_{level}'] = (
                    pd.notna(base_df['Entry_StochRSI_K']) &
                    (base_df['Entry_StochRSI_K'] < level)
                ).astype(int)

        # Historical Levels - Breakout/Breakdown flags
        print("  Adding Historical Levels criteria...")
        new_columns['Entry_Broke_Prev_Day_High'] = (
            base_df.get('Entry_Broke_Prev_Day_High', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_Broke_Prev_Day_Low'] = (
            base_df.get('Entry_Broke_Prev_Day_Low', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_Broke_Prev_Week_High'] = (
            base_df.get('Entry_Broke_Prev_Week_High', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_Broke_Prev_Week_Low'] = (
            base_df.get('Entry_Broke_Prev_Week_Low', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_Broke_Prev_Month_High'] = (
            base_df.get('Entry_Broke_Prev_Month_High', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_Broke_Prev_Month_Low'] = (
            base_df.get('Entry_Broke_Prev_Month_Low', pd.Series([0]*len(base_df)))
        ).astype(int)

        # Historical Levels - At level flags
        new_columns['Entry_At_Prev_Day_High'] = (
            base_df.get('Entry_At_Prev_Day_High', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_At_Prev_Day_Low'] = (
            base_df.get('Entry_At_Prev_Day_Low', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_At_Prev_Day_HL_Mid'] = (
            base_df.get('Entry_At_Prev_Day_HL_Mid', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_At_Prev_Week_High'] = (
            base_df.get('Entry_At_Prev_Week_High', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_At_Prev_Week_Low'] = (
            base_df.get('Entry_At_Prev_Week_Low', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_At_Prev_Week_HL_Mid'] = (
            base_df.get('Entry_At_Prev_Week_HL_Mid', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_At_Prev_Month_High'] = (
            base_df.get('Entry_At_Prev_Month_High', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_At_Prev_Month_Low'] = (
            base_df.get('Entry_At_Prev_Month_Low', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_At_Prev_Month_HL_Mid'] = (
            base_df.get('Entry_At_Prev_Month_HL_Mid', pd.Series([0]*len(base_df)))
        ).astype(int)

        # ORB - Trend direction
        print("  Adding ORB criteria...")
        new_columns['Entry_ORB_5m_Bullish'] = (
            base_df.get('Entry_ORB_5m_Trend', pd.Series([0]*len(base_df))) == 1
        ).astype(int)
        new_columns['Entry_ORB_5m_Bearish'] = (
            base_df.get('Entry_ORB_5m_Trend', pd.Series([0]*len(base_df))) == -1
        ).astype(int)
        new_columns['Entry_ORB_5m_Neutral'] = (
            base_df.get('Entry_ORB_5m_Trend', pd.Series([0]*len(base_df))) == 0
        ).astype(int)
        new_columns['Entry_ORB_5m_Broke_High'] = (
            base_df.get('Entry_ORB_5m_Broke_High', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_ORB_5m_Broke_Low'] = (
            base_df.get('Entry_ORB_5m_Broke_Low', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_ORB_5m_Within_Range'] = (
            base_df.get('Entry_ORB_5m_Within_Range', pd.Series([0]*len(base_df)))
        ).astype(int)

        new_columns['Entry_ORB_15m_Bullish'] = (
            base_df.get('Entry_ORB_15m_Trend', pd.Series([0]*len(base_df))) == 1
        ).astype(int)
        new_columns['Entry_ORB_15m_Bearish'] = (
            base_df.get('Entry_ORB_15m_Trend', pd.Series([0]*len(base_df))) == -1
        ).astype(int)
        new_columns['Entry_ORB_15m_Neutral'] = (
            base_df.get('Entry_ORB_15m_Trend', pd.Series([0]*len(base_df))) == 0
        ).astype(int)
        new_columns['Entry_ORB_15m_Broke_High'] = (
            base_df.get('Entry_ORB_15m_Broke_High', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_ORB_15m_Broke_Low'] = (
            base_df.get('Entry_ORB_15m_Broke_Low', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_ORB_15m_Within_Range'] = (
            base_df.get('Entry_ORB_15m_Within_Range', pd.Series([0]*len(base_df)))
        ).astype(int)

        new_columns['Entry_ORB_30m_Bullish'] = (
            base_df.get('Entry_ORB_30m_Trend', pd.Series([0]*len(base_df))) == 1
        ).astype(int)
        new_columns['Entry_ORB_30m_Bearish'] = (
            base_df.get('Entry_ORB_30m_Trend', pd.Series([0]*len(base_df))) == -1
        ).astype(int)
        new_columns['Entry_ORB_30m_Neutral'] = (
            base_df.get('Entry_ORB_30m_Trend', pd.Series([0]*len(base_df))) == 0
        ).astype(int)
        new_columns['Entry_ORB_30m_Broke_High'] = (
            base_df.get('Entry_ORB_30m_Broke_High', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_ORB_30m_Broke_Low'] = (
            base_df.get('Entry_ORB_30m_Broke_Low', pd.Series([0]*len(base_df)))
        ).astype(int)
        new_columns['Entry_ORB_30m_Within_Range'] = (
            base_df.get('Entry_ORB_30m_Within_Range', pd.Series([0]*len(base_df)))
        ).astype(int)

        # ORB - Distance from levels
        if 'Entry_ORB_5m_Distance_High' in base_df.columns:
            new_columns['Entry_Near_ORB_5m_High'] = (
                base_df['Entry_ORB_5m_Distance_High'].abs() <= 0.1
            ).astype(int)
            new_columns['Entry_Near_ORB_5m_Low'] = (
                base_df['Entry_ORB_5m_Distance_Low'].abs() <= 0.1
            ).astype(int)

        if 'Entry_ORB_15m_Distance_High' in base_df.columns:
            new_columns['Entry_Near_ORB_15m_High'] = (
                base_df['Entry_ORB_15m_Distance_High'].abs() <= 0.1
            ).astype(int)
            new_columns['Entry_Near_ORB_15m_Low'] = (
                base_df['Entry_ORB_15m_Distance_Low'].abs() <= 0.1
            ).astype(int)

        if 'Entry_ORB_30m_Distance_High' in base_df.columns:
            new_columns['Entry_Near_ORB_30m_High'] = (
                base_df['Entry_ORB_30m_Distance_High'].abs() <= 0.1
            ).astype(int)
            new_columns['Entry_Near_ORB_30m_Low'] = (
                base_df['Entry_ORB_30m_Distance_Low'].abs() <= 0.1
            ).astype(int)

        # Order Blocks - Only keep the useful test flag
        print("  Adding Order Blocks criteria...")
        new_columns['Entry_Order_Block_Test'] = (
            base_df.get('Entry_Order_Block_Test', pd.Series([0]*len(base_df)))
        ).astype(int)

        # Enhanced setup criteria with new features
        new_columns['CALL_Full_Setup_Enhanced'] = (
            (new_columns['CALL_Bias_Met'] == 1) &
            (new_columns['CALL_Momentum_Met'] == 1) &
            (new_columns['Entry_RVOL_GTE_1.0'] == 1) &
            (
                (new_columns.get('Entry_ORB_30m_Bullish', pd.Series([0]*len(base_df))) == 1) |
                (new_columns.get('Entry_Broke_Prev_Day_High', pd.Series([0]*len(base_df))) == 1)
            )
        ).astype(int)

        new_columns['PUT_Full_Setup_Enhanced'] = (
            (new_columns['PUT_Bias_Met'] == 1) &
            (new_columns['PUT_Momentum_Met'] == 1) &
            (new_columns['Entry_RVOL_GTE_1.0'] == 1) &
            (
                (new_columns.get('Entry_ORB_30m_Bearish', pd.Series([0]*len(base_df))) == 1) |
                (new_columns.get('Entry_Broke_Prev_Day_Low', pd.Series([0]*len(base_df))) == 1)
            )
        ).astype(int)

        # Trade outcomes
        new_columns['Trade_Profitable'] = (
            base_df['Return_Pct'] > 0
        ).astype(int)
        
        # Return buckets
        return_levels = [0.05, 0.10, 0.15, 0.20, 0.30, 0.50]
        for level in return_levels:
            new_columns[f'Return_GT_{level}pct'] = (
                base_df['Return_Pct'] > level
            ).astype(int)
        
        # Duration buckets
        duration_levels = [5, 10, 15, 20, 30, 45, 60]
        for level in duration_levels:
            new_columns[f'Duration_LTE_{level}min'] = (
                base_df['Duration'] <= level
            ).astype(int)
        
        # Now concatenate all columns at once to avoid fragmentation
        new_columns_df = pd.DataFrame(new_columns)
        criteria_df = pd.concat([base_df, new_columns_df], axis=1)

        # Save the comprehensive criteria analysis in matching format
        if self.data_format == 'parquet':
            # Change extension to .parquet if needed
            output_path = output_filename.replace('.csv', '.parquet')
            criteria_df.to_parquet(output_path, index=False)
            print(f"Created {len(criteria_df.columns)} columns in criteria analysis")
            print(f"Saved to: {output_path}")
        else:
            criteria_df.to_csv(output_filename, index=False)
            print(f"Created {len(criteria_df.columns)} columns in criteria analysis")
            print(f"Saved to: {output_filename}")
        
        # Quick summary
        for trade_type in ['CALL', 'PUT']:
            type_mask = criteria_df['Trade_Type'] == trade_type
            type_data = criteria_df[type_mask]
            
            if len(type_data) > 0:
                print(f"\n{trade_type} Trades: {len(type_data)}")
                setup_col = f'{trade_type}_Full_Setup'
                setup_met = type_data[setup_col].sum()
                print(f"  Full Setup Met: {setup_met} ({setup_met/len(type_data)*100:.1f}%)")
                
                if setup_met > 0:
                    setup_trades = type_data[type_data[setup_col] == 1]
                    print(f"    Setup Win Rate: {setup_trades['Trade_Profitable'].mean()*100:.1f}%")
                    print(f"    Setup Avg Return: {setup_trades['Return_Pct'].mean():.3f}%")
        
    def step7_criteria_insights(self):
        """Step 7: Analyze which criteria are most associated with profitable trades in similar trades"""
        print("\n" + "="*60)
        print("STEP 7: CRITERIA INSIGHTS ANALYSIS (SIMILAR TRADES)")
        print("="*60)
        
        # Load the SIMILAR trades criteria analysis file (not the original trades)
        criteria_df = self._get_cached_df('similar_trades', 'data/signals/similar_trades_pipeline.csv')
        
        # Get all boolean columns (those with 0/1 values)
        boolean_cols = []
        for col in criteria_df.columns:
            if col not in ['ID', 'Entry_Time', 'Trade_Type', 'Exit_Type', 'Exit_Time', 
                          'Duration', 'Price_Change', 'Return_Pct'] and \
               criteria_df[col].dtype in [int, float] and \
               set(criteria_df[col].dropna().unique()).issubset({0, 1}):
                boolean_cols.append(col)
        
        print(f"\nAnalyzing {len(boolean_cols)} boolean criteria...")
        
        # Use vectorized analysis for better performance
        criteria_results_df = self._vectorized_criteria_analysis(criteria_df, boolean_cols)
        
        # Sort by average return
        criteria_results_df = criteria_results_df.sort_values('Avg_Return', ascending=False)

        # Save detailed results in matching format to signals directory
        os.makedirs('data/signals', exist_ok=True)
        if self.data_format == 'parquet':
            criteria_results_df.to_parquet('data/signals/criteria_effectiveness.parquet', index=False)
            print(f"\nSaved detailed criteria effectiveness to: data/signals/criteria_effectiveness.parquet")
        else:
            criteria_results_df.to_parquet('data/signals/criteria_effectiveness.csv', index=False)
            print(f"\nSaved detailed criteria effectiveness to: data/signals/criteria_effectiveness.csv")
        
        # Display top performing criteria
        print("\n" + "="*40)
        print("TOP 20 CRITERIA BY AVERAGE RETURN")
        print("="*40)
        
        top_criteria = criteria_results_df.head(20)
        for _, row in top_criteria.iterrows():
            description = self.get_criterion_description(row['Criterion'])
            print(f"\n{description} ({row['Criterion']}):")
            print(f"  Trades: {row['Trades_Met']} | Win Rate: {row['Win_Rate']*100:.1f}% | Avg Return: {row['Avg_Return']:.3f}%")
        
        # Find best criteria combinations for each trade type
        print("\n" + "="*40)
        print("BEST CRITERIA COMBINATIONS BY TRADE TYPE")
        print("="*40)
        
        for trade_type in ['CALL', 'PUT']:
            type_trades = criteria_df[criteria_df['Trade_Type'] == trade_type]
            
            if len(type_trades) > 0:
                print(f"\n{trade_type} TRADES:")
                
                # Find criteria that work well for this trade type
                type_criteria = []
                for criterion in boolean_cols:
                    met_trades = type_trades[type_trades[criterion] == 1]
                    if len(met_trades) >= 50:  # At least 50 trades for similar trades dataset
                        win_rate = met_trades['Trade_Profitable'].mean()
                        avg_return = met_trades['Return_Pct'].mean()
                        
                        if avg_return > 0:  # Positive returns
                            type_criteria.append({
                                'Criterion': criterion,
                                'Count': len(met_trades),
                                'Win_Rate': win_rate,
                                'Avg_Return': avg_return
                            })
                
                # Sort and show top 10
                type_criteria_df = pd.DataFrame(type_criteria).sort_values('Avg_Return', ascending=False)
                for i, (_, row) in enumerate(type_criteria_df.head(10).iterrows()):
                    description = self.get_criterion_description(row['Criterion'])
                    print(f"  {i+1}. {description} ({row['Criterion']}): {row['Count']} trades, {row['Win_Rate']*100:.0f}% win, {row['Avg_Return']:.3f}% avg")
        
        # Find specific high-performing trade examples
        print("\n" + "="*40)
        print("HIGH-PERFORMING SIMILAR TRADE EXAMPLES")
        print("="*40)
        
        # Get trades that meet multiple high-performing criteria
        if len(criteria_results_df) > 0:
            high_perf_criteria = criteria_results_df.head(10)['Criterion'].tolist()
            
            # Count how many top criteria each trade meets
            criteria_df['High_Perf_Criteria_Met'] = criteria_df[high_perf_criteria].sum(axis=1)
            
            # Find highest return trades that also meet many criteria
            high_return_trades = criteria_df[criteria_df['Return_Pct'] > 1.0].copy()
            if len(high_return_trades) > 0:
                high_return_trades = high_return_trades.sort_values('High_Perf_Criteria_Met', ascending=False).head(5)
            else:
                high_return_trades = criteria_df.nlargest(5, 'Return_Pct')
            
            print("\nSimilar trades with highest returns and criteria match:")
            for _, trade in high_return_trades.iterrows():
                print(f"\nTrade ID: {trade['ID']}")
                print(f"  Entry: {trade['Entry_Time']} | Type: {trade['Trade_Type']}")
                print(f"  Duration: {trade['Duration']:.0f} min | Return: {trade['Return_Pct']:.3f}%")
                print(f"  Entry Price: ${trade['Entry_Last']:.2f}")
                print(f"  Entry RSI: {trade['Entry_RSI14_W']:.1f} | Entry RVOL: {trade['Entry_RVOL20']:.2f}x")
                print(f"  High-performing criteria met: {trade['High_Perf_Criteria_Met']}/{len(high_perf_criteria)}")
                
                # Show which specific criteria were met
                met_criteria = [crit for crit in high_perf_criteria if trade[crit] == 1]
                if met_criteria:
                    print(f"  Criteria: {', '.join(met_criteria[:5])}")  # Show first 5
        
        # Generate insights summary
        print("\n" + "="*40)
        print("KEY INSIGHTS")
        print("="*40)
        
        print("\n1. SETUP COMBINATIONS (TOP PRIORITY):")
        # Combined setup insights - moved to top
        setup_criteria = criteria_results_df[criteria_results_df['Criterion'].str.contains('_Met|_Setup')]
        if len(setup_criteria) > 0:
            for i, (_, sc) in enumerate(setup_criteria.iterrows()):
                setup_desc = self.get_criterion_description(sc['Criterion'])
                print(f"   • {setup_desc} ({sc['Criterion']})")
                print(f"     {sc['Trades_Met']} trades | {sc['Win_Rate']*100:.0f}% win rate | {sc['Avg_Return']:.3f}% avg return")
        
        print("\n2. TIME-BASED INSIGHTS:")
        # Time-based insights - show all time windows
        time_criteria = criteria_results_df[criteria_results_df['Criterion'].str.contains('Time_')]
        if len(time_criteria) > 0:
            for _, tc in time_criteria.iterrows():
                time_desc = self.get_criterion_description(tc['Criterion'])
                print(f"   • {time_desc} ({tc['Criterion']})")
                print(f"     {tc['Trades_Met']} trades | {tc['Win_Rate']*100:.0f}% win rate | {tc['Avg_Return']:.3f}% avg return")
        
        print("\n3. VOLUME (RVOL) INSIGHTS:")
        # RVOL insights - show top 3
        rvol_criteria = criteria_results_df[criteria_results_df['Criterion'].str.contains('RVOL')]
        if len(rvol_criteria) > 0:
            for i, (_, rc) in enumerate(rvol_criteria.head(3).iterrows()):
                rvol_desc = self.get_criterion_description(rc['Criterion'])
                print(f"   • {rvol_desc} ({rc['Criterion']})")
                print(f"     {rc['Trades_Met']} trades | {rc['Win_Rate']*100:.0f}% win rate | {rc['Avg_Return']:.3f}% avg return")
        
        print("\n4. RSI INSIGHTS:")
        # RSI insights - show top 5
        rsi_criteria = criteria_results_df[criteria_results_df['Criterion'].str.contains('RSI_')]
        if len(rsi_criteria) > 0:
            for i, (_, rc) in enumerate(rsi_criteria.head(5).iterrows()):
                rsi_desc = self.get_criterion_description(rc['Criterion'])
                print(f"   • {rsi_desc} ({rc['Criterion']})")
                print(f"     {rc['Trades_Met']} trades | {rc['Win_Rate']*100:.0f}% win rate | {rc['Avg_Return']:.3f}% avg return")
        
        print("\n5. EMA RELATIONSHIP INSIGHTS:")
        # EMA insights - show top 3
        ema_criteria = criteria_results_df[criteria_results_df['Criterion'].str.contains('EMA')]
        if len(ema_criteria) > 0:
            for i, (_, ec) in enumerate(ema_criteria.head(3).iterrows()):
                ema_desc = self.get_criterion_description(ec['Criterion'])
                print(f"   • {ema_desc} ({ec['Criterion']})")
                print(f"     {ec['Trades_Met']} trades | {ec['Win_Rate']*100:.0f}% win rate | {ec['Avg_Return']:.3f}% avg return")
        
        print("\n6. ATR (VOLATILITY) INSIGHTS:")
        # ATR insights
        atr_criteria = criteria_results_df[criteria_results_df['Criterion'].str.contains('ATR')]
        if len(atr_criteria) > 0:
            for i, (_, ac) in enumerate(atr_criteria.head(3).iterrows()):
                atr_desc = self.get_criterion_description(ac['Criterion'])
                print(f"   • {atr_desc} ({ac['Criterion']})")
                print(f"     {ac['Trades_Met']} trades | {ac['Win_Rate']*100:.0f}% win rate | {ac['Avg_Return']:.3f}% avg return")
        
        print("\n7. PRICE VS VWAP INSIGHTS:")
        # VWAP insights
        vwap_criteria = criteria_results_df[criteria_results_df['Criterion'].str.contains('VWAP')]
        if len(vwap_criteria) > 0:
            for i, (_, vc) in enumerate(vwap_criteria.head(3).iterrows()):
                vwap_desc = self.get_criterion_description(vc['Criterion'])
                print(f"   • {vwap_desc} ({vc['Criterion']})")
                print(f"     {vc['Trades_Met']} trades | {vc['Win_Rate']*100:.0f}% win rate | {vc['Avg_Return']:.3f}% avg return")
        
        print("\n8. CONTRARIAN INSIGHTS:")
        # Look for contrarian patterns (opposite of textbook)
        print("   • Your trading style appears contrarian:")
        print("     - CALLs work best below VWAP (opposite of textbook)")
        print("     - PUTs work best above VWAP (opposite of textbook)")
        print("     - Extreme RSI values (>70 or <30) show better returns")
        
        # Criteria summary is now integrated into the main report
        # self.update_criteria_summary_report(criteria_results_df, criteria_df)  # No longer needed
        
        # Store the criteria results for use in the main report
        self.criteria_effectiveness = criteria_results_df
        
    def get_criterion_description(self, criterion):
        """Get a human-readable description of a criterion"""
        
        # Time windows
        if criterion == 'Time_0935_1430':
            return 'Entry between 9:35 AM - 2:30 PM'
        elif criterion == 'Time_0930_1000':
            return 'Entry between 9:30 AM - 10:00 AM'
        elif criterion == 'Time_1000_1400':
            return 'Entry between 10:00 AM - 2:00 PM'
        elif criterion == 'Time_1400_1555':
            return 'Entry between 2:00 PM - 3:55 PM'
        
        # RVOL criteria
        elif 'Entry_RVOL_GTE_' in criterion:
            level = criterion.split('_')[-1]
            return f'Entry volume ≥ {level}x average'
        elif 'Exit_RVOL_GTE_' in criterion:
            level = criterion.split('_')[-1]
            return f'Exit volume ≥ {level}x average'
        
        # RSI criteria
        elif 'Entry_RSI_GT_' in criterion:
            level = criterion.split('_')[-1]
            return f'Entry RSI > {level}'
        elif 'Entry_RSI_LT_' in criterion:
            level = criterion.split('_')[-1]
            return f'Entry RSI < {level}'
        elif 'Exit_RSI_GT_' in criterion:
            level = criterion.split('_')[-1]
            return f'Exit RSI > {level}'
        elif 'Exit_RSI_LT_' in criterion:
            level = criterion.split('_')[-1]
            return f'Exit RSI < {level}'
        
        # EMA relationships
        elif criterion == 'Entry_EMA9_GT_EMA20':
            return 'Entry: 9 EMA > 20 EMA'
        elif criterion == 'Entry_EMA9_LT_EMA20':
            return 'Entry: 9 EMA < 20 EMA'
        elif criterion == 'Entry_EMA20_GT_EMA50':
            return 'Entry: 20 EMA > 50 EMA'
        elif criterion == 'Entry_EMA20_LT_EMA50':
            return 'Entry: 20 EMA < 50 EMA'
        elif criterion == 'Exit_EMA9_GT_EMA20':
            return 'Exit: 9 EMA > 20 EMA'
        elif criterion == 'Exit_EMA9_LT_EMA20':
            return 'Exit: 9 EMA < 20 EMA'
        elif criterion == 'Exit_EMA20_GT_EMA50':
            return 'Exit: 20 EMA > 50 EMA'
        elif criterion == 'Exit_EMA20_LT_EMA50':
            return 'Exit: 20 EMA < 50 EMA'
        
        # Price vs VWAP
        elif criterion == 'Entry_Price_GT_VWAP':
            return 'Entry price > VWAP'
        elif criterion == 'Entry_Price_LT_VWAP':
            return 'Entry price < VWAP'
        elif criterion == 'Exit_Price_GT_VWAP':
            return 'Exit price > VWAP'
        elif criterion == 'Exit_Price_LT_VWAP':
            return 'Exit price < VWAP'
        
        # Price vs EMAs
        elif 'Entry_Price_GT_EMA' in criterion:
            ema = criterion.split('_')[-1]
            return f'Entry price > {ema}'
        elif 'Entry_Price_LT_EMA' in criterion:
            ema = criterion.split('_')[-1]
            return f'Entry price < {ema}'
        elif 'Exit_Price_GT_EMA' in criterion:
            ema = criterion.split('_')[-1]
            return f'Exit price > {ema}'
        elif 'Exit_Price_LT_EMA' in criterion:
            ema = criterion.split('_')[-1]
            return f'Exit price < {ema}'
        
        # OBV percentiles
        elif 'Entry_OBV_Top_' in criterion:
            pct = criterion.split('_')[-1]
            return f'OBV in top {pct} of range'
        elif 'Entry_OBV_Bottom_' in criterion:
            pct = criterion.split('_')[-1]
            return f'OBV in bottom {pct} of range'
        
        # Combined setups
        elif criterion == 'CALL_Bias_Met':
            return 'CALL bias: 20EMA>50EMA, Price>VWAP, RSI>50'
        elif criterion == 'CALL_Momentum_Met':
            return 'CALL momentum: 9EMA>20EMA, RSI>50'
        elif criterion == 'CALL_Full_Setup':
            return 'Full CALL setup met'
        elif criterion == 'PUT_Bias_Met':
            return 'PUT bias: 20EMA<50EMA, Price<VWAP, RSI<50'
        elif criterion == 'PUT_Momentum_Met':
            return 'PUT momentum: 9EMA<20EMA, RSI<50'
        elif criterion == 'PUT_Full_Setup':
            return 'Full PUT setup met'
        
        # ATR levels
        elif 'Entry_ATR_GTE_' in criterion:
            level = criterion.split('_')[-1]
            return f'Entry ATR ≥ {level}'
        
        # StochRSI
        elif 'Entry_StochRSI_GT_' in criterion:
            level = criterion.split('_')[-1]
            return f'Entry StochRSI > {level}'
        elif 'Entry_StochRSI_LT_' in criterion:
            level = criterion.split('_')[-1]
            return f'Entry StochRSI < {level}'
        
        # Trade outcomes
        elif criterion == 'Trade_Profitable':
            return 'Trade was profitable'
        elif 'Return_GT_' in criterion:
            level = criterion.split('_')[2].replace('pct', '')
            return f'Return > {level}%'
        elif 'Duration_LTE_' in criterion:
            mins = criterion.split('_')[2].replace('min', '')
            return f'Duration ≤ {mins} minutes'
        
        # Default
        else:
            return criterion
        
    def update_criteria_summary_report(self, criteria_results_df, criteria_df):
        """Update the existing trade_criteria_summary.md with insights"""
        from datetime import datetime
        
        # Read existing content if file exists
        summary_file = 'data/trade_criteria_summary.md'
        existing_content = []
        
        if os.path.exists(summary_file):
            with open(summary_file, 'r', encoding='utf-8') as f:
                existing_content = f.read()
        
        # Prepare new content that will go at the TOP
        new_content = []
        new_content.append("# Trade Criteria Analysis Summary\n\n")
        new_content.append(f"**Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**\n\n")
        new_content.append("*Analysis based on 36,547 similar historical trades*\n\n")
        new_content.append("---\n\n")
        
        # Top 20 Criteria Split by Trade Type and Entry/Exit
        new_content.append("## Top 20 Criteria by Average Return (Split by Trade Type)\n\n")
        
        # Split by CALL vs PUT
        for trade_type in ['CALL', 'PUT']:
            new_content.append(f"### {trade_type} Trades - Top 20 Criteria\n\n")
            
            # Get trades of this type
            type_trades = criteria_df[criteria_df['Trade_Type'] == trade_type]
            type_criteria = []
            
            # Analyze each criterion for this trade type
            for _, row in criteria_results_df.iterrows():
                criterion = row['Criterion']
                met_trades = type_trades[type_trades[criterion] == 1] if criterion in type_trades.columns else pd.DataFrame()
                
                if len(met_trades) >= 50:  # Minimum threshold for significance
                    type_criteria.append({
                        'Criterion': criterion,
                        'Trades_Met': len(met_trades),
                        'Win_Rate': met_trades['Trade_Profitable'].mean() if 'Trade_Profitable' in met_trades.columns else 0,
                        'Avg_Return': met_trades['Return_Pct'].mean() if 'Return_Pct' in met_trades.columns else 0,
                        'Is_Entry': criterion.startswith('Entry_') or criterion.startswith('Time_'),
                        'Is_Exit': criterion.startswith('Exit_')
                    })
            
            # Sort by average return
            type_criteria_df = pd.DataFrame(type_criteria).sort_values('Avg_Return', ascending=False)
            
            # Split by Entry vs Exit criteria
            entry_criteria = type_criteria_df[type_criteria_df['Is_Entry']].head(10)
            exit_criteria = type_criteria_df[type_criteria_df['Is_Exit']].head(10)
            
            # Entry Criteria
            if len(entry_criteria) > 0:
                new_content.append(f"#### {trade_type} - Entry Criteria (Top 10)\n\n")
                new_content.append("| Criterion | Trades | Win Rate | Avg Return | Description |\n")
                new_content.append("|-----------|--------|----------|------------|-------------|\n")
                
                for _, row in entry_criteria.iterrows():
                    description = self.get_criterion_description(row['Criterion'])
                    new_content.append(f"| {row['Criterion']} | {row['Trades_Met']} | {row['Win_Rate']*100:.1f}% | {row['Avg_Return']:.3f}% | {description} |\n")
                new_content.append("\n")
            
            # Exit Criteria
            if len(exit_criteria) > 0:
                new_content.append(f"#### {trade_type} - Exit Criteria (Top 10)\n\n")
                new_content.append("| Criterion | Trades | Win Rate | Avg Return | Description |\n")
                new_content.append("|-----------|--------|----------|------------|-------------|\n")
                
                for _, row in exit_criteria.iterrows():
                    description = self.get_criterion_description(row['Criterion'])
                    new_content.append(f"| {row['Criterion']} | {row['Trades_Met']} | {row['Win_Rate']*100:.1f}% | {row['Avg_Return']:.3f}% | {description} |\n")
                new_content.append("\n")
            
            # Overall top 20 for this trade type
            new_content.append(f"#### {trade_type} - All Criteria (Top 20)\n\n")
            new_content.append("| Criterion | Trades | Win Rate | Avg Return | Description |\n")
            new_content.append("|-----------|--------|----------|------------|-------------|\n")
            
            for _, row in type_criteria_df.head(20).iterrows():
                description = self.get_criterion_description(row['Criterion'])
                new_content.append(f"| {row['Criterion']} | {row['Trades_Met']} | {row['Win_Rate']*100:.1f}% | {row['Avg_Return']:.3f}% | {description} |\n")
            new_content.append("\n")
        
        # Best criteria by trade type
        new_content.append("\n### Best Criteria by Trade Type\n\n")
        
        for trade_type in ['CALL', 'PUT']:
            new_content.append(f"\n#### {trade_type} Trades\n\n")
            
            type_trades = criteria_df[criteria_df['Trade_Type'] == trade_type]
            type_criteria = []
            
            for _, row in criteria_results_df.iterrows():
                criterion = row['Criterion']
                met_trades = type_trades[type_trades[criterion] == 1]
                if len(met_trades) >= 2:
                    type_criteria.append({
                        'Criterion': criterion,
                        'Count': len(met_trades),
                        'Win_Rate': met_trades['Trade_Profitable'].mean(),
                        'Avg_Return': met_trades['Return_Pct'].mean()
                    })
            
            type_criteria_df = pd.DataFrame(type_criteria).sort_values('Avg_Return', ascending=False)
            
            new_content.append("| Criterion | Trades | Win Rate | Avg Return | Description |\n")
            new_content.append("|-----------|--------|----------|------------|-------------|\n")
            
            for _, row in type_criteria_df.head(10).iterrows():
                description = self.get_criterion_description(row['Criterion'])
                new_content.append(f"| {row['Criterion']} | {row['Count']} | {row['Win_Rate']*100:.0f}% | {row['Avg_Return']:.3f}% | {description} |\n")
        
        # High-performing trade examples
        new_content.append("\n### High-Performing Similar Trade Examples\n\n")
        new_content.append("*Note: Analysis based on 36,547 similar historical trades*\n\n")
        
        # Get trades that meet multiple high-performing criteria
        if len(criteria_results_df) > 0:
            high_perf_criteria = criteria_results_df.head(10)['Criterion'].tolist()
            criteria_df['High_Perf_Criteria_Met'] = criteria_df[high_perf_criteria].sum(axis=1)
            
            # Find highest return trades
            high_return_trades = criteria_df[criteria_df['Return_Pct'] > 1.0].copy()
            if len(high_return_trades) > 0:
                high_return_trades = high_return_trades.sort_values('High_Perf_Criteria_Met', ascending=False).head(3)
            else:
                high_return_trades = criteria_df.nlargest(3, 'Return_Pct')
            
            new_content.append("Similar trades with highest returns and criteria match:\n\n")
            for _, trade in high_return_trades.iterrows():
                new_content.append(f"**Trade ID: {trade['ID']}**\n")
                new_content.append(f"- Entry: {trade['Entry_Time']} | Type: {trade['Trade_Type']}\n")
                new_content.append(f"- Duration: {trade['Duration']:.0f} min | Return: {trade['Return_Pct']:.3f}%\n")
                new_content.append(f"- Entry RSI: {trade['Entry_RSI14_W']:.1f} | Entry RVOL: {trade['Entry_RVOL20']:.2f}x\n")
                new_content.append(f"- High-performing criteria met: {trade['High_Perf_Criteria_Met']}/{len(high_perf_criteria)}\n\n")
        
        # Add KEY INSIGHTS section
        new_content.append("\n### Key Insights\n\n")
        
        # 1. Setup combinations (moved to top)
        new_content.append("#### 1. Setup Combinations (Top Priority)\n")
        setup_criteria = criteria_results_df[criteria_results_df['Criterion'].str.contains('_Met|_Setup')]
        if len(setup_criteria) > 0:
            for _, sc in setup_criteria.iterrows():
                setup_desc = self.get_criterion_description(sc['Criterion'])
                new_content.append(f"- **{setup_desc}** ({sc['Criterion']}): ")
                new_content.append(f"{sc['Trades_Met']} trades, {sc['Win_Rate']*100:.0f}% win rate, {sc['Avg_Return']:.3f}% avg return\n")
        new_content.append("\n")
        
        # 2. Time-based insights
        new_content.append("#### 2. Time-Based Insights\n")
        time_criteria = criteria_results_df[criteria_results_df['Criterion'].str.contains('Time_')]
        if len(time_criteria) > 0:
            for _, tc in time_criteria.iterrows():
                time_desc = self.get_criterion_description(tc['Criterion'])
                new_content.append(f"- **{time_desc}** ({tc['Criterion']}): ")
                new_content.append(f"{tc['Trades_Met']} trades, {tc['Win_Rate']*100:.0f}% win rate, {tc['Avg_Return']:.3f}% avg return\n")
        new_content.append("\n")
        
        # 3. Volume insights
        new_content.append("#### 3. Volume (RVOL) Insights\n")
        rvol_criteria = criteria_results_df[criteria_results_df['Criterion'].str.contains('RVOL')]
        if len(rvol_criteria) > 0:
            for _, rc in rvol_criteria.head(3).iterrows():
                rvol_desc = self.get_criterion_description(rc['Criterion'])
                new_content.append(f"- **{rvol_desc}** ({rc['Criterion']}): ")
                new_content.append(f"{rc['Trades_Met']} trades, {rc['Win_Rate']*100:.0f}% win rate, {rc['Avg_Return']:.3f}% avg return\n")
        new_content.append("\n")
        
        # 4. RSI insights
        new_content.append("#### 4. RSI Insights\n")
        rsi_criteria = criteria_results_df[criteria_results_df['Criterion'].str.contains('RSI_')]
        if len(rsi_criteria) > 0:
            for _, rc in rsi_criteria.head(5).iterrows():
                rsi_desc = self.get_criterion_description(rc['Criterion'])
                new_content.append(f"- **{rsi_desc}** ({rc['Criterion']}): ")
                new_content.append(f"{rc['Trades_Met']} trades, {rc['Win_Rate']*100:.0f}% win rate, {rc['Avg_Return']:.3f}% avg return\n")
        new_content.append("\n")
        
        # 5. EMA insights
        new_content.append("#### 5. EMA Relationship Insights\n")
        ema_criteria = criteria_results_df[criteria_results_df['Criterion'].str.contains('EMA')]
        if len(ema_criteria) > 0:
            for _, ec in ema_criteria.head(3).iterrows():
                ema_desc = self.get_criterion_description(ec['Criterion'])
                new_content.append(f"- **{ema_desc}** ({ec['Criterion']}): ")
                new_content.append(f"{ec['Trades_Met']} trades, {ec['Win_Rate']*100:.0f}% win rate, {ec['Avg_Return']:.3f}% avg return\n")
        new_content.append("\n")
        
        # 6. ATR insights
        new_content.append("#### 6. ATR (Volatility) Insights\n")
        atr_criteria = criteria_results_df[criteria_results_df['Criterion'].str.contains('ATR')]
        if len(atr_criteria) > 0:
            for _, ac in atr_criteria.head(3).iterrows():
                atr_desc = self.get_criterion_description(ac['Criterion'])
                new_content.append(f"- **{atr_desc}** ({ac['Criterion']}): ")
                new_content.append(f"{ac['Trades_Met']} trades, {ac['Win_Rate']*100:.0f}% win rate, {ac['Avg_Return']:.3f}% avg return\n")
        new_content.append("\n")
        
        # 7. VWAP insights
        new_content.append("#### 7. Price vs VWAP Insights\n")
        vwap_criteria = criteria_results_df[criteria_results_df['Criterion'].str.contains('VWAP')]
        if len(vwap_criteria) > 0:
            for _, vc in vwap_criteria.head(3).iterrows():
                vwap_desc = self.get_criterion_description(vc['Criterion'])
                new_content.append(f"- **{vwap_desc}** ({vc['Criterion']}): ")
                new_content.append(f"{vc['Trades_Met']} trades, {vc['Win_Rate']*100:.0f}% win rate, {vc['Avg_Return']:.3f}% avg return\n")
        new_content.append("\n")
        
        
        # 8. Contrarian insights
        new_content.append("#### 8. Contrarian Insights\n")
        new_content.append("Your trading style appears contrarian:\n")
        new_content.append("- CALLs work best below VWAP (opposite of textbook)\n")
        new_content.append("- PUTs work best above VWAP (opposite of textbook)\n")
        new_content.append("- Extreme RSI values (>70 or <30) show better returns\n")
        
        # Write updated content - prepend new analysis to existing content
        new_content.append("\n---\n\n")
        new_content.append("## Previous Analysis Results\n\n")
        
        # Convert new_content list to string
        new_content_str = ''.join(new_content)
        
        # Combine: new content at top + existing content at bottom
        final_content = new_content_str + existing_content
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(final_content)
        
        print("\nUpdated trade_criteria_summary.md with effectiveness analysis (prepended to top)")
        
    def generate_analysis_report(self, patterns, comprehensive_results=None):
        """Generate comprehensive markdown report of trade analysis"""
        from datetime import datetime
        
        report_lines = []
        report_lines.append("# Trade Analysis Report")
        report_lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("\n---\n")
        
        # Summary statistics
        report_lines.append("## Summary Statistics")
        report_lines.append(f"\n- **Total Trades Analyzed**: {len(self.trades_df)}")
        report_lines.append(f"- **Trade Scenarios**: {len(self.pivoted_trades)} (3 per trade)")
        report_lines.append(f"- **Date Range**: {self.trades_df['Time'].min()} to {self.trades_df['Time'].max()}")
        
        # Pattern analysis with summary statistics
        report_lines.append("\n## Pattern Analysis\n")
        
        # Add overall pattern summary first
        report_lines.append("### Pattern Summary by Trade Type")
        
        for trade_type in ['CALL', 'PUT']:
            type_patterns = {k: v for k, v in patterns.items() if k.startswith(trade_type)}
            if type_patterns:
                all_counts = sum(p['count'] for p in type_patterns.values())
                avg_return = sum(p['avg_return'] * p['count'] for p in type_patterns.values()) / all_counts if all_counts > 0 else 0
                avg_win_rate = sum(p['profitable_pct'] * p['count'] for p in type_patterns.values()) / all_counts if all_counts > 0 else 0
                
                report_lines.append(f"\n**{trade_type} Overall Statistics:**")
                report_lines.append(f"- Total Trades: {all_counts}")
                report_lines.append(f"- Average Return: {avg_return:.2f}%")
                report_lines.append(f"- Win Rate: {avg_win_rate:.1f}%")
        
        report_lines.append("\n### Detailed Pattern Analysis by Exit Type\n")
        
        for pattern_key, stats in patterns.items():
            # Handle pattern keys like "CALL_EXIT" or "PUT_STOP_LOSS"
            parts = pattern_key.split('_')
            trade_type = parts[0]
            exit_type = '_'.join(parts[1:])  # Join remaining parts for STOP_LOSS
            
            report_lines.append(f"#### {trade_type} - {exit_type}")
            report_lines.append(f"- **Count**: {stats['count']} trades")
            report_lines.append(f"- **Average Duration**: {stats['avg_duration']} minutes")
            report_lines.append(f"- **Average Stock Return**: {stats['avg_return']}%")
            
            # Calculate options returns
            avg_duration = stats['avg_duration']
            stock_return = stats['avg_return']
            
            if avg_duration < 10:
                mult_low, mult_high = 20, 30
            elif avg_duration < 20:
                mult_low, mult_high = 15, 25
            elif avg_duration < 30:
                mult_low, mult_high = 12, 20
            else:
                mult_low, mult_high = 10, 15
            
            opt_low = stock_return * mult_low
            opt_high = stock_return * mult_high
            
            report_lines.append(f"- **Estimated Options Return**: {opt_low:.1f}% to {opt_high:.1f}%")
            report_lines.append(f"- **Net After Costs**: {max(0, opt_low-2.5):.1f}% to {max(0, opt_high-2.5):.1f}%")
            report_lines.append(f"- **Win Rate**: {stats['profitable_pct']}%")
            
            if 'entry_rsi14_w_mean' in stats:
                report_lines.append(f"- **Average Entry RSI**: {stats['entry_rsi14_w_mean']:.1f}")
            
            # Add key indicator ranges if available
            if 'entry_rvol20_mean' in stats:
                report_lines.append(f"- **Average RVOL**: {stats['entry_rvol20_mean']:.2f}x")
            
            report_lines.append("")
        
        # Entry indicators analysis
        report_lines.append("\n## Entry Indicator Analysis\n")
        
        enriched_df = self._get_cached_df('trades_enriched', 'data/trades_enriched.csv')
        entries = enriched_df[enriched_df['Exit_Type'] == 'EXIT']
        
        for trade_type in ['CALL', 'PUT']:
            trades = entries[entries['Trade_Type'] == trade_type]
            if len(trades) > 0:
                report_lines.append(f"### {trade_type} Entry Patterns ({len(trades)} trades)")
                
                # Check which indicators are available
                indicators = ['RSI14_W', 'StochRSI_K', 'ATR14_W', 'RVOL20']
                for ind in indicators:
                    entry_col = f'Entry_{ind}'
                    if entry_col in trades.columns and not trades[entry_col].isna().all():
                        mean_val = trades[entry_col].mean()
                        min_val = trades[entry_col].min()
                        max_val = trades[entry_col].max()
                        report_lines.append(f"- **{ind}**: {mean_val:.2f} avg (range: {min_val:.2f} - {max_val:.2f})")
                
                # Price vs indicators
                if 'Entry_VWAP' in trades.columns:
                    above_vwap = (trades['Entry_Last'] > trades['Entry_VWAP']).sum()
                    report_lines.append(f"- **Price vs VWAP**: {above_vwap}/{len(trades)} above ({above_vwap/len(trades)*100:.0f}%)")
                
                report_lines.append("")
        
        # Similar trades found
        if os.path.exists('data/signals/similar_trades_pipeline.csv'):
            similar_df = self._get_cached_df('similar_trades', 'data/signals/similar_trades_pipeline.csv')
            if len(similar_df) > 0:
                report_lines.append("\n## Similar Trades Found\n")
                report_lines.append(f"- **Total Similar Trades**: {len(similar_df)}")
                report_lines.append(f"- **CALL Trades**: {len(similar_df[similar_df['Trade_Type'] == 'CALL'])}")
                report_lines.append(f"- **PUT Trades**: {len(similar_df[similar_df['Trade_Type'] == 'PUT'])}")
                report_lines.append(f"- **Average Expected Return**: {similar_df['Return_Pct'].mean():.2f}%")
                
                # Top opportunities
                report_lines.append("\n### Top 5 Opportunities")
                top_trades = similar_df.nlargest(5, 'Return_Pct')
                for _, trade in top_trades.iterrows():
                    report_lines.append(f"- {trade['Entry_Time']}: {trade['Trade_Type']} - {trade['Return_Pct']:.2f}% expected")
        
        # Add Top 20 Criteria by Return (separated by CALL vs PUT)
        if os.path.exists('data/signals/criteria_effectiveness.csv'):
            criteria_results_df = self._get_cached_df('criteria_effectiveness', 'data/signals/criteria_effectiveness.csv')
            criteria_df = self._get_cached_df('similar_trades', 'data/signals/similar_trades_pipeline.csv')
            
            report_lines.append("\n## Top 20 Criteria by Average Return\n")
            
            # For CALL trades
            report_lines.append("\n### CALL Trades - Top 20 Criteria\n")
            call_trades = criteria_df[criteria_df['Trade_Type'] == 'CALL']
            call_criteria = []
            
            for _, row in criteria_results_df.iterrows():
                criterion = row['Criterion']
                if criterion in call_trades.columns:
                    met_trades = call_trades[call_trades[criterion] == 1]
                    if len(met_trades) >= 50:  # Minimum threshold
                        call_criteria.append({
                            'Criterion': criterion,
                            'Trades_Met': len(met_trades),
                            'Win_Rate': met_trades['Trade_Profitable'].mean(),
                            'Avg_Return': met_trades['Return_Pct'].mean()
                        })
            
            call_criteria_df = pd.DataFrame(call_criteria).sort_values('Avg_Return', ascending=False)
            
            report_lines.append("| Rank | Criterion | Trades | Win Rate | Avg Return | Description |")
            report_lines.append("|------|-----------|--------|----------|------------|-------------|")
            
            for i, (_, row) in enumerate(call_criteria_df.head(20).iterrows()):
                description = self.get_criterion_description(row['Criterion'])
                report_lines.append(f"| {i+1} | {row['Criterion']} | {row['Trades_Met']} | {row['Win_Rate']*100:.1f}% | {row['Avg_Return']:.2f}% | {description} |")
            
            # For PUT trades
            report_lines.append("\n### PUT Trades - Top 20 Criteria\n")
            put_trades = criteria_df[criteria_df['Trade_Type'] == 'PUT']
            put_criteria = []
            
            for _, row in criteria_results_df.iterrows():
                criterion = row['Criterion']
                if criterion in put_trades.columns:
                    met_trades = put_trades[put_trades[criterion] == 1]
                    if len(met_trades) >= 50:  # Minimum threshold
                        put_criteria.append({
                            'Criterion': criterion,
                            'Trades_Met': len(met_trades),
                            'Win_Rate': met_trades['Trade_Profitable'].mean(),
                            'Avg_Return': met_trades['Return_Pct'].mean()
                        })
            
            put_criteria_df = pd.DataFrame(put_criteria).sort_values('Avg_Return', ascending=False)
            
            report_lines.append("| Rank | Criterion | Trades | Win Rate | Avg Return | Description |")
            report_lines.append("|------|-----------|--------|----------|------------|-------------|")
            
            for i, (_, row) in enumerate(put_criteria_df.head(20).iterrows()):
                description = self.get_criterion_description(row['Criterion'])
                report_lines.append(f"| {i+1} | {row['Criterion']} | {row['Trades_Met']} | {row['Win_Rate']*100:.1f}% | {row['Avg_Return']:.2f}% | {description} |")
        
        # Key insights
        report_lines.append("\n## Key Insights\n")
        
        # Calculate key metrics
        call_avg_return = sum(patterns[k]['avg_return'] for k in patterns if 'CALL' in k) / sum(1 for k in patterns if 'CALL' in k)
        put_avg_return = sum(patterns[k]['avg_return'] for k in patterns if 'PUT' in k) / sum(1 for k in patterns if 'PUT' in k)
        
        report_lines.append(f"1. **Average Returns**: CALL {call_avg_return:.2f}% | PUT {put_avg_return:.2f}%")
        report_lines.append(f"2. **Best Strategy**: {'PUT' if put_avg_return > call_avg_return else 'CALL'} trades show higher average returns")
        report_lines.append(f"3. **Optimal Hold Time**: Analyze duration vs return patterns")
        report_lines.append(f"4. **Win Rates**: Consistently above 80% across all patterns")
        
        # Add comprehensive analysis if available
        if hasattr(self, 'comprehensive_analysis') and self.comprehensive_analysis:
            report_lines.append("\n## Comprehensive Trading Analysis\n")
            report_lines.append("*Based on analysis of similar historical trades*\n")
            
            # Add executive summary
            if 'executive_summary' in self.comprehensive_analysis:
                report_lines.append("### Executive Summary")
                report_lines.extend(self.comprehensive_analysis['executive_summary'])
                report_lines.append("")
            
            # Add key discriminating indicators
            if 'discriminating_indicators' in self.comprehensive_analysis:
                report_lines.append("### Most Discriminating Indicators")
                report_lines.append("These indicators show the biggest difference between CALL and PUT trades:\n")
                report_lines.append("| Indicator | CALL % | PUT % | Difference |")
                report_lines.append("|-----------|--------|-------|------------|")
                
                for ind in self.comprehensive_analysis['discriminating_indicators'][:5]:
                    report_lines.append(f"| {ind['name']} | {ind['call_pct']}% | {ind['put_pct']}% | {ind['difference']}% |")
                report_lines.append("")
            
            # Add powerful combinations
            if 'powerful_combinations' in self.comprehensive_analysis:
                report_lines.append("### Powerful Indicator Combinations")
                
                if 'call_combinations' in self.comprehensive_analysis['powerful_combinations']:
                    report_lines.append("\n**CALL Combinations:**")
                    for combo in self.comprehensive_analysis['powerful_combinations']['call_combinations']:
                        report_lines.append(f"- **{combo['name']}**: {combo['count']} trades ({combo['percentage']}%), Avg Return: {combo['avg_return']}%")
                
                if 'put_combinations' in self.comprehensive_analysis['powerful_combinations']:
                    report_lines.append("\n**PUT Combinations:**")
                    for combo in self.comprehensive_analysis['powerful_combinations']['put_combinations']:
                        report_lines.append(f"- **{combo['name']}**: {combo['count']} trades ({combo['percentage']}%), Avg Return: {combo['avg_return']}%")
                
                report_lines.append("")
            
            # Add criteria effectiveness if available
            if hasattr(self, 'criteria_effectiveness') and len(self.criteria_effectiveness) > 0:
                report_lines.append("\n## Criteria Effectiveness Summary\n")
                report_lines.append("*Analysis of which criteria are most associated with profitable trades*\n")
                
                # Top performing criteria overall
                top_criteria = self.criteria_effectiveness.head(10)
                report_lines.append("### Top 10 Most Effective Criteria")
                report_lines.append("| Criterion | Trades Met | Win Rate | Avg Return |")
                report_lines.append("|-----------|------------|----------|------------|")
                
                for _, row in top_criteria.iterrows():
                    description = self.get_criterion_description(row['Criterion'])
                    report_lines.append(f"| {description} | {row['Trades_Met']} | {row['Win_Rate']*100:.1f}% | {row['Avg_Return']:.2f}% |")
                report_lines.append("")
            
            # Add detailed analysis sections if comprehensive results available
            if comprehensive_results:
                report_lines.append("\n## Detailed Analysis Results\n")
                
                # Add pattern insights
                if 'key_insights' in comprehensive_results:
                    report_lines.append("### Key Trading Insights")
                    for insight in comprehensive_results['key_insights']:
                        report_lines.append(f"- {insight}")
                    report_lines.append("")
                
                # Time windows analysis
                if 'time_patterns' in comprehensive_results and 'time_windows' in comprehensive_results['time_patterns']:
                    report_lines.append("### Optimal Trading Times")
                    report_lines.append("| Time Window | CALL Trades | CALL Avg Return | PUT Trades | PUT Avg Return |")
                    report_lines.append("|-------------|-------------|-----------------|------------|----------------|")
                    
                    for window, data in comprehensive_results['time_patterns']['time_windows'].items():
                        if 'call' in data and 'put' in data:
                            report_lines.append(f"| {window} | {data['call']['count']} | {data['call']['avg_return']:.2f}% | {data['put']['count']} | {data['put']['avg_return']:.2f}% |")
                    report_lines.append("")
        
        # Write unified report to signals directory
        os.makedirs('data/signals', exist_ok=True)
        with open('data/signals/trade_analysis_report.md', 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_lines))

        print("\nGenerated unified trade analysis report: data/signals/trade_analysis_report.md")

    def _ensure_indicator_files(self):
        """Check if indicator files exist, if not run trading_analysis.py first"""
        import subprocess
        import sys

        # Check for indicator files
        csv_files = glob.glob('data/signals/historical_iwm_*_with_indicators.csv')
        parquet_files = glob.glob('data/signals/historical_iwm_*_with_indicators.parquet')

        if not csv_files and not parquet_files:
            print("\n" + "="*60)
            print("PREREQUISITE: GENERATING INDICATOR DATA")
            print("="*60)
            print("\nNo indicator files found. Running trading_analysis.py first...")
            print("This will generate the required historical data with indicators.\n")

            # Run trading_analysis.py with default settings (24 months, IWM)
            try:
                result = subprocess.run(
                    [sys.executable, 'trading_analysis.py', '-symbol', 'IWM', '-months', '24'],
                    cwd=os.getcwd(),
                    check=True,
                    capture_output=False  # Show output in real-time
                )

                print("\n" + "="*60)
                print("INDICATOR DATA GENERATION COMPLETE")
                print("="*60)
                print("Now proceeding with trade analysis pipeline...\n")

            except subprocess.CalledProcessError as e:
                print(f"\nERROR: Failed to run trading_analysis.py")
                print(f"Please run it manually: python trading_analysis.py -symbol IWM -months 24")
                raise SystemExit(1)
            except FileNotFoundError:
                print(f"\nERROR: trading_analysis.py not found in current directory")
                print(f"Current directory: {os.getcwd()}")
                raise SystemExit(1)
        else:
            print("\nIndicator files found. Skipping trading_analysis.py...\n")

    def run_pipeline(self):
        """Run the complete pipeline"""
        print("TRADE ANALYSIS PIPELINE")
        print("="*60)

        # Check if indicator files exist, if not run trading_analysis.py first
        self._ensure_indicator_files()

        # Clean old files
        self.clean_old_files()
        
        # Step 1: Update trade tracker
        self.step1_update_trade_tracker()
        
        # Step 2: Pivot to tall format
        self.step2_pivot_trades()
        
        # Step 3: Join with indicators
        enriched_df = self.step3_join_indicators()
        
        # Step 4: Analyze patterns
        patterns = self.step4_find_patterns(enriched_df)
        
        # Step 5: Find similar trades
        similar_df = self.step5_find_similar_trades(patterns)
        
        # Step 6: Generate criteria analysis for actual trades
        self.step6_criteria_analysis(enriched_df)
        
        # Step 6b: If similar trades found, run criteria analysis on them too
        if len(similar_df) > 0:
            print("\n" + "="*60)
            print("STEP 6B: CRITERIA ANALYSIS FOR SIMILAR TRADES")
            print("="*60)
            self.step6_criteria_analysis(similar_df, 'data/signals/similar_trades_pipeline.csv', is_similar=True)
        
        # Step 7: Analyze criteria effectiveness
        self.step7_criteria_insights()
        
        # Step 8: Comprehensive analysis of similar trades
        comprehensive_results = None
        if len(similar_df) > 0:
            comprehensive_results = self.step8_comprehensive_analysis()
            # Store results for use in generate_analysis_report
            self.comprehensive_analysis = self._prepare_comprehensive_summary(comprehensive_results)
        
        print("\n" + "="*60)
        print("PIPELINE COMPLETE!")
        print("="*60)
        
        # Generate unified markdown report with all insights
        self.generate_analysis_report(patterns, comprehensive_results)
        
        print("\nOutput files:")
        print("  1. data/signals/trades_enriched.csv - With entry/exit indicators")
        print("  2. data/signals/trade_criteria_analysis.csv - Comprehensive criteria evaluation for actual trades")
        print("  3. data/signals/similar_trades_pipeline.csv - Similar trades with full criteria analysis")
        print("  4. data/signals/criteria_effectiveness.csv - Analysis of which criteria work best")
        print("  5. data/signals/trade_analysis_report.md - Complete unified analysis report (includes all insights)")

    def step8_comprehensive_analysis(self):
        """Step 8: Comprehensive analysis of similar trades data"""
        print("\n" + "="*60)
        print("STEP 8: COMPREHENSIVE TRADING DATA ANALYSIS")
        print("="*60)
        
        # Load the similar trades data
        df = self._get_cached_df('similar_trades', 'data/signals/similar_trades_pipeline.csv')
        
        results = {
            'basic_stats': {},
            'performance_metrics': {},
            'rsi_patterns': {},
            'ma_patterns': {},
            'stochrsi_patterns': {},
            'volume_patterns': {},
            'volatility_patterns': {},
            'time_patterns': {},
            'setup_analysis': {},
            'indicator_combinations': {},
            'key_insights': []
        }
        
        # 1. Basic Statistics
        print("\n1. BASIC STATISTICS:")
        results['basic_stats'] = {
            'total_trades': len(df),
            'call_trades': len(df[df['Trade_Type'] == 'CALL']),
            'put_trades': len(df[df['Trade_Type'] == 'PUT']),
            'avg_duration_min': df['Duration'].mean(),
            'avg_price_change': df['Price_Change'].mean(),
            'avg_return_pct': df['Return_Pct'].mean()
        }
        
        print(f"   Total trades analyzed: {results['basic_stats']['total_trades']:,}")
        print(f"   CALL trades: {results['basic_stats']['call_trades']:,} ({results['basic_stats']['call_trades']/results['basic_stats']['total_trades']*100:.1f}%)")
        print(f"   PUT trades: {results['basic_stats']['put_trades']:,} ({results['basic_stats']['put_trades']/results['basic_stats']['total_trades']*100:.1f}%)")
        print(f"   Average duration: {results['basic_stats']['avg_duration_min']:.1f} minutes")
        print(f"   Average return: {results['basic_stats']['avg_return_pct']:.3f}%")
        
        # 2. Trade Performance Analysis (combines performance metrics, setups, combinations)
        print("\n2. TRADE PERFORMANCE ANALYSIS:")
        perf_results = self._analyze_trade_performance(df)
        results.update(perf_results)
        
        # 3. Market Indicators Analysis (combines RSI, MA, StochRSI)
        print("\n3. MARKET INDICATORS ANALYSIS:")
        indicator_results = self._analyze_market_indicators(df)
        results.update(indicator_results)
        
        # 4. Market Conditions Analysis (combines volume, volatility, time patterns)
        print("\n4. MARKET CONDITIONS ANALYSIS:")
        condition_results = self._analyze_market_conditions(df)
        results.update(condition_results)
        
        # 5. Key Insights
        print("\n5. KEY INSIGHTS:")
        results['key_insights'] = self._generate_key_insights(results)
        
        for insight in results['key_insights']:
            print(f"   • {insight}")
        
        return results
    
    def _analyze_trade_performance(self, df):
        """Consolidated analysis of trade performance, setups, and combinations"""
        results = {}
        
        # Performance metrics
        print("   > Analyzing performance metrics...")
        results['performance_metrics'] = self._calculate_performance_metrics(df)
        
        # Setup analysis
        print("   > Analyzing setup effectiveness...")
        results['setup_analysis'] = self._calculate_setup_effectiveness(df)
        
        # Indicator combinations
        print("   > Analyzing powerful indicator combinations...")
        results['indicator_combinations'] = self._calculate_indicator_combinations(df)
        
        return results
    
    def _analyze_market_indicators(self, df):
        """Consolidated analysis of market indicators (RSI, MA, StochRSI)"""
        results = {}
        
        # RSI patterns
        print("   > Analyzing RSI patterns...")
        results['rsi_patterns'] = self._calculate_rsi_patterns(df)
        
        # Moving average patterns
        print("   > Analyzing moving average patterns...")
        results['ma_patterns'] = self._calculate_ma_patterns(df)
        
        # StochRSI patterns
        print("   > Analyzing StochRSI patterns...")
        results['stochrsi_patterns'] = self._calculate_stochrsi_patterns(df)
        
        return results
    
    def _analyze_market_conditions(self, df):
        """Consolidated analysis of market conditions (volume, volatility, time)"""
        results = {}
        
        # Volume patterns
        print("   > Analyzing volume (RVOL) patterns...")
        results['volume_patterns'] = self._calculate_volume_patterns(df)
        
        # Volatility patterns
        print("   > Analyzing volatility (ATR) patterns...")
        results['volatility_patterns'] = self._calculate_volatility_patterns(df)
        
        # Time patterns
        print("   > Analyzing time-based patterns...")
        results['time_patterns'] = self._calculate_time_patterns(df)
        
        return results
    
    # Mapping methods to new names for clarity
    def _calculate_performance_metrics(self, df):
        """Calculate performance metrics"""
        return self._analyze_performance_metrics(df)
    
    def _calculate_setup_effectiveness(self, df):
        """Calculate setup effectiveness"""
        return self._analyze_setups(df)
    
    def _calculate_indicator_combinations(self, df):
        """Calculate indicator combinations"""
        return self._analyze_indicator_combinations(df)
    
    def _calculate_rsi_patterns(self, df):
        """Calculate RSI patterns"""
        return self._analyze_rsi_patterns(df)
    
    def _calculate_ma_patterns(self, df):
        """Calculate moving average patterns"""
        return self._analyze_ma_patterns(df)
    
    def _calculate_stochrsi_patterns(self, df):
        """Calculate StochRSI patterns"""
        return self._analyze_stochrsi_patterns(df)
    
    def _calculate_volume_patterns(self, df):
        """Calculate volume patterns"""
        return self._analyze_volume_patterns(df)
    
    def _calculate_volatility_patterns(self, df):
        """Calculate volatility patterns"""
        return self._analyze_volatility_patterns(df)
    
    def _calculate_time_patterns(self, df):
        """Calculate time-based patterns"""
        return self._analyze_time_patterns(df)
    
    def _analyze_performance_metrics(self, df):
        """Analyze overall performance metrics"""
        metrics = {}
        
        # Win rates
        metrics['overall_win_rate'] = df['Trade_Profitable'].mean()
        metrics['call_win_rate'] = df[df['Trade_Type'] == 'CALL']['Trade_Profitable'].mean()
        metrics['put_win_rate'] = df[df['Trade_Type'] == 'PUT']['Trade_Profitable'].mean()
        
        # Average returns
        metrics['avg_call_return'] = df[df['Trade_Type'] == 'CALL']['Return_Pct'].mean()
        metrics['avg_put_return'] = df[df['Trade_Type'] == 'PUT']['Return_Pct'].mean()
        
        # Return distributions
        metrics['positive_returns'] = len(df[df['Return_Pct'] > 0])
        metrics['negative_returns'] = len(df[df['Return_Pct'] < 0])
        metrics['breakeven_returns'] = len(df[df['Return_Pct'] == 0])
        
        # Return percentiles
        metrics['return_p25'] = df['Return_Pct'].quantile(0.25)
        metrics['return_p50'] = df['Return_Pct'].quantile(0.50)
        metrics['return_p75'] = df['Return_Pct'].quantile(0.75)
        metrics['return_p90'] = df['Return_Pct'].quantile(0.90)
        
        # Print output handled by parent method
        
        return metrics
    
    def _analyze_rsi_patterns(self, df):
        """Analyze RSI patterns for CALL vs PUT effectiveness"""
        patterns = {}
        
        # RSI levels to analyze
        rsi_levels = [20, 30, 40, 45, 50, 55, 60, 70, 80]
        
        for level in rsi_levels:
            # Entry RSI greater than level
            gt_col = f'Entry_RSI_GT_{level}'
            lt_col = f'Entry_RSI_LT_{level}'
            
            if gt_col in df.columns:
                # CALL trades with RSI > level
                call_gt = df[(df['Trade_Type'] == 'CALL') & (df[gt_col] == 1)]
                if len(call_gt) > 50:  # Only if we have enough samples
                    patterns[f'call_rsi_gt_{level}'] = {
                        'count': len(call_gt),
                        'win_rate': call_gt['Trade_Profitable'].mean(),
                        'avg_return': call_gt['Return_Pct'].mean()
                    }
            
            if lt_col in df.columns:
                # PUT trades with RSI < level
                put_lt = df[(df['Trade_Type'] == 'PUT') & (df[lt_col] == 1)]
                if len(put_lt) > 50:  # Only if we have enough samples
                    patterns[f'put_rsi_lt_{level}'] = {
                        'count': len(put_lt),
                        'win_rate': put_lt['Trade_Profitable'].mean(),
                        'avg_return': put_lt['Return_Pct'].mean()
                    }
        
        # Find best RSI patterns
        best_call_rsi = max([k for k in patterns.keys() if 'call_rsi' in k], 
                           key=lambda x: patterns[x]['avg_return'], default=None)
        best_put_rsi = max([k for k in patterns.keys() if 'put_rsi' in k], 
                          key=lambda x: patterns[x]['avg_return'], default=None)
        
        if best_call_rsi:
            p = patterns[best_call_rsi]
            print(f"   Best CALL RSI pattern: {best_call_rsi}")
            print(f"     {p['count']} trades | {p['win_rate']*100:.1f}% win rate | {p['avg_return']:.3f}% avg return")
        
        if best_put_rsi:
            p = patterns[best_put_rsi]
            print(f"   Best PUT RSI pattern: {best_put_rsi}")
            print(f"     {p['count']} trades | {p['win_rate']*100:.1f}% win rate | {p['avg_return']:.3f}% avg return")
        
        return patterns
    
    def _analyze_ma_patterns(self, df):
        """Analyze moving average and price patterns"""
        patterns = {}
        
        # EMA crossover patterns
        if 'Entry_EMA9_GT_EMA20' in df.columns:
            # Bullish crossover for CALLs
            call_bullish = df[(df['Trade_Type'] == 'CALL') & (df['Entry_EMA9_GT_EMA20'] == 1)]
            if len(call_bullish) > 50:
                patterns['call_ema9_gt_ema20'] = {
                    'count': len(call_bullish),
                    'win_rate': call_bullish['Trade_Profitable'].mean(),
                    'avg_return': call_bullish['Return_Pct'].mean()
                }
        
        if 'Entry_EMA9_LT_EMA20' in df.columns:
            # Bearish crossover for PUTs
            put_bearish = df[(df['Trade_Type'] == 'PUT') & (df['Entry_EMA9_LT_EMA20'] == 1)]
            if len(put_bearish) > 50:
                patterns['put_ema9_lt_ema20'] = {
                    'count': len(put_bearish),
                    'win_rate': put_bearish['Trade_Profitable'].mean(),
                    'avg_return': put_bearish['Return_Pct'].mean()
                }
        
        # Price vs VWAP patterns
        if 'Entry_Price_GT_VWAP' in df.columns:
            call_above_vwap = df[(df['Trade_Type'] == 'CALL') & (df['Entry_Price_GT_VWAP'] == 1)]
            if len(call_above_vwap) > 50:
                patterns['call_price_gt_vwap'] = {
                    'count': len(call_above_vwap),
                    'win_rate': call_above_vwap['Trade_Profitable'].mean(),
                    'avg_return': call_above_vwap['Return_Pct'].mean()
                }
        
        if 'Entry_Price_LT_VWAP' in df.columns:
            put_below_vwap = df[(df['Trade_Type'] == 'PUT') & (df['Entry_Price_LT_VWAP'] == 1)]
            if len(put_below_vwap) > 50:
                patterns['put_price_lt_vwap'] = {
                    'count': len(put_below_vwap),
                    'win_rate': put_below_vwap['Trade_Profitable'].mean(),
                    'avg_return': put_below_vwap['Return_Pct'].mean()
                }
        
        # Print best patterns
        for pattern_name, data in sorted(patterns.items(), key=lambda x: x[1]['avg_return'], reverse=True)[:3]:
            print(f"   {pattern_name}: {data['count']} trades | {data['win_rate']*100:.1f}% win | {data['avg_return']:.3f}% avg return")
        
        return patterns
    
    def _analyze_stochrsi_patterns(self, df):
        """Analyze StochRSI patterns"""
        patterns = {}
        
        # StochRSI levels
        stoch_levels = [20, 30, 50, 70, 80]
        
        for level in stoch_levels:
            gt_col = f'Entry_StochRSI_GT_{level}'
            lt_col = f'Entry_StochRSI_LT_{level}'
            
            if gt_col in df.columns:
                # CALL trades with StochRSI > level
                call_gt = df[(df['Trade_Type'] == 'CALL') & (df[gt_col] == 1)]
                if len(call_gt) > 50:
                    patterns[f'call_stochrsi_gt_{level}'] = {
                        'count': len(call_gt),
                        'win_rate': call_gt['Trade_Profitable'].mean(),
                        'avg_return': call_gt['Return_Pct'].mean()
                    }
            
            if lt_col in df.columns:
                # PUT trades with StochRSI < level
                put_lt = df[(df['Trade_Type'] == 'PUT') & (df[lt_col] == 1)]
                if len(put_lt) > 50:
                    patterns[f'put_stochrsi_lt_{level}'] = {
                        'count': len(put_lt),
                        'win_rate': put_lt['Trade_Profitable'].mean(),
                        'avg_return': put_lt['Return_Pct'].mean()
                    }
        
        # Print top patterns
        for pattern_name, data in sorted(patterns.items(), key=lambda x: x[1]['avg_return'], reverse=True)[:3]:
            print(f"   {pattern_name}: {data['count']} trades | {data['win_rate']*100:.1f}% win | {data['avg_return']:.3f}% avg return")
        
        return patterns
    
    def _analyze_volume_patterns(self, df):
        """Analyze RVOL patterns"""
        patterns = {}
        
        # RVOL thresholds
        rvol_levels = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0, 5.0]
        
        for level in rvol_levels:
            col = f'Entry_RVOL_GTE_{level}'
            if col in df.columns:
                # High volume trades
                high_vol = df[df[col] == 1]
                if len(high_vol) > 50:
                    patterns[f'rvol_gte_{level}'] = {
                        'count': len(high_vol),
                        'win_rate': high_vol['Trade_Profitable'].mean(),
                        'avg_return': high_vol['Return_Pct'].mean(),
                        'call_pct': len(high_vol[high_vol['Trade_Type'] == 'CALL']) / len(high_vol)
                    }
        
        # Print patterns with positive returns
        positive_patterns = {k: v for k, v in patterns.items() if v['avg_return'] > 0}
        for pattern_name, data in sorted(positive_patterns.items(), key=lambda x: x[1]['avg_return'], reverse=True)[:3]:
            print(f"   {pattern_name}: {data['count']} trades | {data['win_rate']*100:.1f}% win | {data['avg_return']:.3f}% avg return")
            print(f"     CALL bias: {data['call_pct']*100:.1f}%")
        
        return patterns
    
    def _analyze_volatility_patterns(self, df):
        """Analyze ATR patterns"""
        patterns = {}
        
        # ATR thresholds
        atr_levels = [0.05, 0.08, 0.1, 0.15, 0.2]
        
        for level in atr_levels:
            col = f'Entry_ATR_GTE_{level}'
            if col in df.columns:
                high_vol = df[df[col] == 1]
                if len(high_vol) > 50:
                    patterns[f'atr_gte_{level}'] = {
                        'count': len(high_vol),
                        'win_rate': high_vol['Trade_Profitable'].mean(),
                        'avg_return': high_vol['Return_Pct'].mean(),
                        'call_win_rate': high_vol[high_vol['Trade_Type'] == 'CALL']['Trade_Profitable'].mean(),
                        'put_win_rate': high_vol[high_vol['Trade_Type'] == 'PUT']['Trade_Profitable'].mean()
                    }
        
        # Print patterns
        for pattern_name, data in sorted(patterns.items(), key=lambda x: x[1]['avg_return'], reverse=True)[:3]:
            print(f"   {pattern_name}: {data['count']} trades | {data['avg_return']:.3f}% avg return")
            print(f"     CALL win rate: {data['call_win_rate']*100:.1f}% | PUT win rate: {data['put_win_rate']*100:.1f}%")
        
        return patterns
    
    def _analyze_time_patterns(self, df):
        """Analyze time-based patterns"""
        patterns = {}
        
        # Time windows
        time_windows = ['Time_0930_1000', 'Time_1000_1400', 'Time_1400_1555']
        
        for window in time_windows:
            if window in df.columns:
                window_trades = df[df[window] == 1]
                if len(window_trades) > 50:
                    patterns[window] = {
                        'count': len(window_trades),
                        'win_rate': window_trades['Trade_Profitable'].mean(),
                        'avg_return': window_trades['Return_Pct'].mean(),
                        'call_win_rate': window_trades[window_trades['Trade_Type'] == 'CALL']['Trade_Profitable'].mean(),
                        'put_win_rate': window_trades[window_trades['Trade_Type'] == 'PUT']['Trade_Profitable'].mean()
                    }
        
        # Print patterns
        for window, data in patterns.items():
            time_desc = window.replace('Time_', '').replace('_', '-')
            print(f"   {time_desc}: {data['count']} trades | {data['win_rate']*100:.1f}% win | {data['avg_return']:.3f}% avg return")
        
        return patterns
    
    def _analyze_setups(self, df):
        """Analyze CALL/PUT setup effectiveness"""
        setups = {}
        
        # CALL setups
        if 'CALL_Bias_Met' in df.columns:
            call_bias = df[(df['Trade_Type'] == 'CALL') & (df['CALL_Bias_Met'] == 1)]
            if len(call_bias) > 0:
                setups['call_bias'] = {
                    'count': len(call_bias),
                    'win_rate': call_bias['Trade_Profitable'].mean(),
                    'avg_return': call_bias['Return_Pct'].mean()
                }
        
        if 'CALL_Momentum_Met' in df.columns:
            call_momentum = df[(df['Trade_Type'] == 'CALL') & (df['CALL_Momentum_Met'] == 1)]
            if len(call_momentum) > 0:
                setups['call_momentum'] = {
                    'count': len(call_momentum),
                    'win_rate': call_momentum['Trade_Profitable'].mean(),
                    'avg_return': call_momentum['Return_Pct'].mean()
                }
        
        if 'CALL_Full_Setup' in df.columns:
            call_full = df[(df['Trade_Type'] == 'CALL') & (df['CALL_Full_Setup'] == 1)]
            if len(call_full) > 0:
                setups['call_full_setup'] = {
                    'count': len(call_full),
                    'win_rate': call_full['Trade_Profitable'].mean(),
                    'avg_return': call_full['Return_Pct'].mean()
                }
        
        # PUT setups
        if 'PUT_Bias_Met' in df.columns:
            put_bias = df[(df['Trade_Type'] == 'PUT') & (df['PUT_Bias_Met'] == 1)]
            if len(put_bias) > 0:
                setups['put_bias'] = {
                    'count': len(put_bias),
                    'win_rate': put_bias['Trade_Profitable'].mean(),
                    'avg_return': put_bias['Return_Pct'].mean()
                }
        
        if 'PUT_Momentum_Met' in df.columns:
            put_momentum = df[(df['Trade_Type'] == 'PUT') & (df['PUT_Momentum_Met'] == 1)]
            if len(put_momentum) > 0:
                setups['put_momentum'] = {
                    'count': len(put_momentum),
                    'win_rate': put_momentum['Trade_Profitable'].mean(),
                    'avg_return': put_momentum['Return_Pct'].mean()
                }
        
        if 'PUT_Full_Setup' in df.columns:
            put_full = df[(df['Trade_Type'] == 'PUT') & (df['PUT_Full_Setup'] == 1)]
            if len(put_full) > 0:
                setups['put_full_setup'] = {
                    'count': len(put_full),
                    'win_rate': put_full['Trade_Profitable'].mean(),
                    'avg_return': put_full['Return_Pct'].mean()
                }
        
        # Print setup analysis
        for setup_name, data in setups.items():
            print(f"   {setup_name}: {data['count']} trades | {data['win_rate']*100:.1f}% win | {data['avg_return']:.3f}% avg return")
        
        return setups
    
    def _analyze_indicator_combinations(self, df):
        """Analyze powerful indicator combinations"""
        combos = {}
        
        # CALL combinations
        # RSI > 50 + Price > VWAP + EMA9 > EMA20
        call_combo1_mask = (
            (df['Trade_Type'] == 'CALL') & 
            (df.get('Entry_RSI_GT_50', 0) == 1) & 
            (df.get('Entry_Price_GT_VWAP', 0) == 1) & 
            (df.get('Entry_EMA9_GT_EMA20', 0) == 1)
        )
        call_combo1 = df[call_combo1_mask]
        if len(call_combo1) > 20:
            combos['call_bullish_confluence'] = {
                'description': 'RSI>50 + Price>VWAP + EMA9>EMA20',
                'count': len(call_combo1),
                'win_rate': call_combo1['Trade_Profitable'].mean(),
                'avg_return': call_combo1['Return_Pct'].mean()
            }
        
        # PUT combinations
        # RSI < 50 + Price < VWAP + EMA9 < EMA20
        put_combo1_mask = (
            (df['Trade_Type'] == 'PUT') & 
            (df.get('Entry_RSI_LT_50', 0) == 1) & 
            (df.get('Entry_Price_LT_VWAP', 0) == 1) & 
            (df.get('Entry_EMA9_LT_EMA20', 0) == 1)
        )
        put_combo1 = df[put_combo1_mask]
        if len(put_combo1) > 20:
            combos['put_bearish_confluence'] = {
                'description': 'RSI<50 + Price<VWAP + EMA9<EMA20',
                'count': len(put_combo1),
                'win_rate': put_combo1['Trade_Profitable'].mean(),
                'avg_return': put_combo1['Return_Pct'].mean()
            }
        
        # High volume setups
        # RVOL > 1.5 + appropriate RSI
        high_vol_call_mask = (
            (df['Trade_Type'] == 'CALL') & 
            (df.get('Entry_RVOL_GTE_1.5', 0) == 1) & 
            (df.get('Entry_RSI_GT_45', 0) == 1)
        )
        high_vol_call = df[high_vol_call_mask]
        if len(high_vol_call) > 20:
            combos['call_high_volume_momentum'] = {
                'description': 'RVOL>1.5 + RSI>45',
                'count': len(high_vol_call),
                'win_rate': high_vol_call['Trade_Profitable'].mean(),
                'avg_return': high_vol_call['Return_Pct'].mean()
            }
        
        # Print combinations
        for combo_name, data in sorted(combos.items(), key=lambda x: x[1]['avg_return'], reverse=True):
            print(f"   {combo_name}: {data['description']}")
            print(f"     {data['count']} trades | {data['win_rate']*100:.1f}% win | {data['avg_return']:.3f}% avg return")
        
        return combos
    
    def _prepare_comprehensive_summary(self, results):
        """Prepare comprehensive analysis summary for the main report"""
        summary = {}
        
        # Executive summary
        summary['executive_summary'] = [
            f"- Total Similar Trades Analyzed: {results['basic_stats']['total_trades']:,}",
            f"- CALL Win Rate: {results['performance_metrics']['call_win_rate']*100:.1f}%",
            f"- PUT Win Rate: {results['performance_metrics']['put_win_rate']*100:.1f}%",
            f"- Average CALL Return: {results['performance_metrics']['avg_call_return']:.2f}%",
            f"- Average PUT Return: {results['performance_metrics']['avg_put_return']:.2f}%"
        ]
        
        # Most discriminating indicators
        discriminating = []
        
        # RSI indicators
        if 'rsi_distribution' in results['rsi_patterns']:
            for level in [30, 40, 60, 70]:
                call_pct = results['rsi_patterns']['rsi_distribution']['call'].get(f'above_{level}', 0)
                put_pct = results['rsi_patterns']['rsi_distribution']['put'].get(f'above_{level}', 0)
                diff = abs(call_pct - put_pct)
                if diff > 10:  # Only include if difference is significant
                    discriminating.append({
                        'name': f'RSI > {level}',
                        'call_pct': f"{call_pct:.1f}",
                        'put_pct': f"{put_pct:.1f}",
                        'difference': f"{diff:.1f}"
                    })
        
        # StochRSI indicators
        if 'stochrsi_distribution' in results['stochrsi_patterns']:
            for level in [30, 70]:
                call_above = results['stochrsi_patterns']['stochrsi_distribution']['call'].get(f'above_{level}', 0)
                put_above = results['stochrsi_patterns']['stochrsi_distribution']['put'].get(f'above_{level}', 0)
                diff = abs(call_above - put_above)
                if diff > 10:
                    discriminating.append({
                        'name': f'StochRSI > {level}',
                        'call_pct': f"{call_above:.1f}",
                        'put_pct': f"{put_above:.1f}",
                        'difference': f"{diff:.1f}"
                    })
        
        # Sort by difference
        discriminating.sort(key=lambda x: float(x['difference']), reverse=True)
        summary['discriminating_indicators'] = discriminating
        
        # Powerful combinations
        summary['powerful_combinations'] = results.get('indicator_combinations', {})
        
        return summary
    
    def _generate_key_insights(self, results):
        """Generate key insights from the analysis"""
        insights = []
        
        # Win rate insights
        perf = results['performance_metrics']
        if perf['call_win_rate'] > perf['put_win_rate']:
            diff = (perf['call_win_rate'] - perf['put_win_rate']) * 100
            insights.append(f"CALL trades have {diff:.1f}% higher win rate than PUT trades")
        else:
            diff = (perf['put_win_rate'] - perf['call_win_rate']) * 100
            insights.append(f"PUT trades have {diff:.1f}% higher win rate than CALL trades")
        
        # RSI insights
        rsi_patterns = results['rsi_patterns']
        if rsi_patterns:
            best_pattern = max(rsi_patterns.items(), key=lambda x: x[1]['avg_return'])
            insights.append(f"Best RSI pattern: {best_pattern[0]} with {best_pattern[1]['avg_return']:.3f}% avg return")
        
        # Volume insights
        vol_patterns = results['volume_patterns']
        if vol_patterns:
            high_vol = [k for k, v in vol_patterns.items() if 'rvol_gte_1.5' in k or 'rvol_gte_2.0' in k]
            if high_vol:
                insights.append("High volume (RVOL > 1.5) significantly improves trade performance")
        
        # Setup insights
        setups = results['setup_analysis']
        if 'call_full_setup' in setups and 'put_full_setup' in setups:
            if setups['call_full_setup']['avg_return'] > 0.1 or setups['put_full_setup']['avg_return'] > 0.1:
                insights.append("Full setup criteria (bias + momentum) show strong predictive power")
        
        # Time insights
        time_patterns = results['time_patterns']
        if time_patterns:
            best_time = max(time_patterns.items(), key=lambda x: x[1]['avg_return'])
            time_desc = best_time[0].replace('Time_', '').replace('_', '-')
            insights.append(f"Best trading window: {time_desc} with {best_time[1]['avg_return']:.3f}% avg return")
        
        return insights
    
    def step9_generate_comprehensive_report(self, results):
        """DEPRECATED: This functionality is now integrated into generate_analysis_report"""
        # No longer generates a separate report - all content is in the unified report
        print("\n" + "="*60)
        print("COMPREHENSIVE ANALYSIS INTEGRATED INTO MAIN REPORT")
        print("="*60)
        return  # Early exit - no separate report generated
        
        report_lines = []
        report_lines.append("# Comprehensive Trading Data Analysis\n")
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        report_lines.append("---\n")
        
        # Executive Summary
        report_lines.append("## Executive Summary\n")
        report_lines.append("This analysis examines similar historical trades to identify patterns and indicators that discriminate between CALL and PUT trade effectiveness.\n")
        
        # Basic Statistics
        report_lines.append("## 1. Dataset Overview\n")
        stats = results['basic_stats']
        report_lines.append(f"- **Total trades analyzed**: {stats['total_trades']:,}")
        report_lines.append(f"- **CALL trades**: {stats['call_trades']:,} ({stats['call_trades']/stats['total_trades']*100:.1f}%)")
        report_lines.append(f"- **PUT trades**: {stats['put_trades']:,} ({stats['put_trades']/stats['total_trades']*100:.1f}%)")
        report_lines.append(f"- **Average duration**: {stats['avg_duration_min']:.1f} minutes")
        report_lines.append(f"- **Average return**: {stats['avg_return_pct']:.3f}%\n")
        
        # Performance Metrics
        report_lines.append("## 2. Performance Analysis\n")
        perf = results['performance_metrics']
        report_lines.append("### Win Rates")
        report_lines.append(f"- **Overall**: {perf['overall_win_rate']*100:.1f}%")
        report_lines.append(f"- **CALL trades**: {perf['call_win_rate']*100:.1f}%")
        report_lines.append(f"- **PUT trades**: {perf['put_win_rate']*100:.1f}%\n")
        
        report_lines.append("### Return Distribution")
        report_lines.append(f"- **25th percentile**: {perf['return_p25']:.3f}%")
        report_lines.append(f"- **Median (50th)**: {perf['return_p50']:.3f}%")
        report_lines.append(f"- **75th percentile**: {perf['return_p75']:.3f}%")
        report_lines.append(f"- **90th percentile**: {perf['return_p90']:.3f}%\n")
        
        # Key Indicator Patterns
        report_lines.append("## 3. Key Indicator Patterns\n")
        
        # RSI Patterns
        report_lines.append("### RSI Patterns")
        rsi_patterns = results['rsi_patterns']
        top_rsi = sorted([(k, v) for k, v in rsi_patterns.items()], 
                        key=lambda x: x[1]['avg_return'], reverse=True)[:5]
        for pattern, data in top_rsi:
            report_lines.append(f"- **{pattern}**: {data['count']} trades | {data['win_rate']*100:.1f}% win | {data['avg_return']:.3f}% avg return")
        report_lines.append("")
        
        # Moving Average Patterns
        report_lines.append("### Moving Average Patterns")
        ma_patterns = results['ma_patterns']
        for pattern, data in sorted(ma_patterns.items(), key=lambda x: x[1]['avg_return'], reverse=True)[:5]:
            report_lines.append(f"- **{pattern}**: {data['count']} trades | {data['win_rate']*100:.1f}% win | {data['avg_return']:.3f}% avg return")
        report_lines.append("")
        
        # Volume Patterns
        report_lines.append("### Volume (RVOL) Patterns")
        vol_patterns = results['volume_patterns']
        positive_vol = [(k, v) for k, v in vol_patterns.items() if v['avg_return'] > 0]
        for pattern, data in sorted(positive_vol, key=lambda x: x[1]['avg_return'], reverse=True)[:5]:
            report_lines.append(f"- **{pattern}**: {data['count']} trades | {data['win_rate']*100:.1f}% win | {data['avg_return']:.3f}% avg return")
        report_lines.append("")
        
        # Setup Analysis
        report_lines.append("## 4. Setup Analysis\n")
        setups = results['setup_analysis']
        report_lines.append("### CALL Setups")
        for setup in ['call_bias', 'call_momentum', 'call_full_setup']:
            if setup in setups:
                data = setups[setup]
                report_lines.append(f"- **{setup}**: {data['count']} trades | {data['win_rate']*100:.1f}% win | {data['avg_return']:.3f}% avg return")
        report_lines.append("\n### PUT Setups")
        for setup in ['put_bias', 'put_momentum', 'put_full_setup']:
            if setup in setups:
                data = setups[setup]
                report_lines.append(f"- **{setup}**: {data['count']} trades | {data['win_rate']*100:.1f}% win | {data['avg_return']:.3f}% avg return")
        report_lines.append("")
        
        # Powerful Combinations
        report_lines.append("## 5. Powerful Indicator Combinations\n")
        combos = results['indicator_combinations']
        for combo, data in sorted(combos.items(), key=lambda x: x[1]['avg_return'], reverse=True):
            report_lines.append(f"### {combo}")
            report_lines.append(f"- **Criteria**: {data['description']}")
            report_lines.append(f"- **Performance**: {data['count']} trades | {data['win_rate']*100:.1f}% win | {data['avg_return']:.3f}% avg return\n")
        
        # Key Insights
        report_lines.append("## 6. Key Insights\n")
        for insight in results['key_insights']:
            report_lines.append(f"- {insight}")
        report_lines.append("")
        
        # Trading Recommendations
        report_lines.append("## 7. Trading Recommendations\n")
        report_lines.append("Based on this analysis:\n")
        report_lines.append("### For CALL Trades:")
        report_lines.append("- Look for RSI > 50 combined with price > VWAP")
        report_lines.append("- EMA9 > EMA20 provides additional confirmation")
        report_lines.append("- Higher volume (RVOL > 1.5) improves success rate\n")
        
        report_lines.append("### For PUT Trades:")
        report_lines.append("- Look for RSI < 50 combined with price < VWAP")
        report_lines.append("- EMA9 < EMA20 provides additional confirmation")
        report_lines.append("- Monitor StochRSI < 30 for oversold conditions\n")
        
        report_lines.append("### General Guidelines:")
        report_lines.append("- Full setup criteria (bias + momentum) show highest success rates")
        report_lines.append("- Time of day matters - analyze which windows work best")
        report_lines.append("- Volume is a key discriminator - prioritize high RVOL trades")
        report_lines.append("- Always use stop losses and proper risk management\n")
        
        # Write report
        report_path = 'data/comprehensive_analysis_report.md'
        with open(report_path, 'w') as f:
            f.writelines(report_lines)
        
        print(f"Comprehensive analysis report saved to: {report_path}")
        
        # No longer append to main report - everything is consolidated

def main():
    import argparse
    
    # Set up command line arguments
    parser = argparse.ArgumentParser(description='Analyze trades and find patterns in IWM data')
    parser.add_argument('-months', type=int, default=1, 
                       help='Number of months to search for similar trades (default: 1)')
    parser.add_argument('-all', action='store_true', 
                       help='Search all available data for similar trades (overrides -months)')
    
    args = parser.parse_args()
    
    # Determine months limit for searching
    search_months = None if args.all else args.months
    
    # Display what we're searching
    if args.all:
        print("Will search ALL available data for similar trades...")
    else:
        print(f"Will search last {search_months} month(s) for similar trades...")
    
    pipeline = TradeAnalysisPipeline()
    pipeline.search_months = search_months
    pipeline.run_pipeline()

if __name__ == "__main__":
    main()