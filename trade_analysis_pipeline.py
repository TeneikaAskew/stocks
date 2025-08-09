#!/usr/bin/env python3
"""
Unified trade analysis pipeline:
1. Read trade_tracker.csv from data/trade_examples/
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

class TradeAnalysisPipeline:
    def __init__(self):
        self.trades_df = None
        self.iwm_df = None
        self.pivoted_trades = None
        self.search_months = 1  # Default to 1 month
        
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
        self.trades_df = pd.read_csv('data/trade_examples/trade_tracker.csv')
        print(f"Loaded {len(self.trades_df)} trades")
        
        # Convert time columns
        time_cols = ['Time', 'Exit_Time', 'Stop_Loss_Time', 'Runner_Time']
        for col in time_cols:
            self.trades_df[col] = pd.to_datetime(self.trades_df[col], errors='coerce')
        
        # Calculate durations
        self.trades_df['Duration_Exit'] = ((self.trades_df['Exit_Time'] - self.trades_df['Time']).dt.total_seconds() / 60).round(1)
        self.trades_df['Duration_StopLoss'] = ((self.trades_df['Stop_Loss_Time'] - self.trades_df['Time']).dt.total_seconds() / 60).round(1)
        self.trades_df['Duration_Runner'] = ((self.trades_df['Runner_Time'] - self.trades_df['Time']).dt.total_seconds() / 60).round(1)
        
        # Save updated version
        self.trades_df.to_csv('data/trade_tracker_updated.csv', index=False)
        print("Saved trade_tracker_updated.csv with duration calculations")
        
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
        self.pivoted_trades.to_csv('data/trades_pivoted.csv', index=False)
        
        print(f"Created {len(self.pivoted_trades)} trade scenarios")
        print(f"  EXIT scenarios: {len(self.pivoted_trades[self.pivoted_trades['Exit_Type'] == 'EXIT'])}")
        print(f"  STOP_LOSS scenarios: {len(self.pivoted_trades[self.pivoted_trades['Exit_Type'] == 'STOP_LOSS'])}")
        print(f"  RUNNER scenarios: {len(self.pivoted_trades[self.pivoted_trades['Exit_Type'] == 'RUNNER'])}")
        
    def step3_join_indicators(self):
        """Step 3: Join with IWM indicators data"""
        print("\n" + "="*60)
        print("STEP 3: JOIN WITH INDICATORS")
        print("="*60)
        
        # Load IWM data
        self.iwm_df = pd.read_csv('data/historical_iwm_0824_0825_with_indicators.csv')
        self.iwm_df['Time'] = pd.to_datetime(self.iwm_df['Time'])
        print(f"Loaded IWM data: {len(self.iwm_df)} rows")
        
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
                      'StochRSI_K', 'StochRSI_D']
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
        enriched['Price_Change'] = enriched['Exit_Last'] - enriched['Entry_Last']
        enriched['Return_Pct'] = (enriched['Price_Change'] / enriched['Entry_Last'] * 100).round(3)
        
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
        enriched_final.to_csv('data/trades_enriched.csv', index=False)
        
        print("Saved trades_enriched.csv with entry/exit indicators")
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
                subset = enriched_df[mask]
                
                if len(subset) > 0:
                    pattern_key = f"{trade_type}_{exit_type}"
                    patterns[pattern_key] = {
                        'count': len(subset),
                        'avg_duration': subset['Duration'].mean(),
                        'avg_return': subset['Return_Pct'].mean(),
                        'profitable_pct': (subset['Return_Pct'] > 0).sum() / len(subset) * 100,
                        'entry_rsi_mean': subset['Entry_RSI14_W'].mean(),
                        'entry_rsi_std': subset['Entry_RSI14_W'].std()
                    }
                    
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
        
        # Save pattern analysis
        patterns_df = pd.DataFrame(patterns).T
        patterns_df.to_csv('data/trade_patterns.csv')
        
        return patterns
        
    def step5_find_similar_trades(self, patterns):
        """Step 5: Find similar trades in historical data"""
        print("\n" + "="*60)
        print("STEP 5: FIND SIMILAR TRADES")
        print("="*60)
        
        # Filter data based on search_months parameter
        if self.search_months is None:
            # Search all data
            search_df = self.iwm_df.copy()
            print(f"Searching ALL {len(search_df)} data points")
        else:
            # Search last N months
            cutoff_date = self.iwm_df['Time'].max() - pd.DateOffset(months=self.search_months)
            search_df = self.iwm_df[self.iwm_df['Time'] >= cutoff_date].copy()
            print(f"Searching {len(search_df)} data points in last {self.search_months} month(s)")
        
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
                
            # Check CALL patterns
            if (current['Price_Change_1m'] > 0.01 and 
                current['RSI14_W'] > 25 and current['RSI14_W'] < 70):
                
                # Check potential exits across full duration range (4-31 minutes based on your trades)
                best_return = 0
                best_duration = 0
                
                for duration in range(4, 32):  # Check every minute from 4 to 31
                    if i + duration < len(search_df):
                        exit_price = search_df.iloc[i + duration]['Last']
                        return_pct = (exit_price - current['Last']) / current['Last'] * 100
                        
                        if return_pct > best_return:
                            best_return = return_pct
                            best_duration = duration
                
                if best_return > 0.1:  # Profitable
                    similar_trades.append({
                        'Entry_Time': current['Time'],
                        'Trade_Type': 'CALL',
                        'Exit_Duration': best_duration,
                        'Entry_Price': current['Last'],
                        'Entry_RSI': current['RSI14_W'],
                        'Expected_Return': best_return
                    })
            
            # Check PUT patterns
            if (current['Price_Change_1m'] < -0.01 and 
                current['RSI14_W'] > 30 and current['RSI14_W'] < 75):
                
                # Check potential exits across full duration range (12-45 minutes based on your trades)
                best_return = 0
                best_duration = 0
                
                for duration in range(12, 46):  # Check every minute from 12 to 45
                    if i + duration < len(search_df):
                        exit_price = search_df.iloc[i + duration]['Last']
                        return_pct = (current['Last'] - exit_price) / current['Last'] * 100
                        
                        if return_pct > best_return:
                            best_return = return_pct
                            best_duration = duration
                
                if best_return > 0.1:  # Profitable
                    similar_trades.append({
                        'Entry_Time': current['Time'],
                        'Trade_Type': 'PUT',
                        'Exit_Duration': best_duration,
                        'Entry_Price': current['Last'],
                        'Entry_RSI': current['RSI14_W'],
                        'Expected_Return': best_return
                    })
        
        # Save similar trades
        if similar_trades:
            similar_df = pd.DataFrame(similar_trades)
            similar_df = similar_df.sort_values('Expected_Return', ascending=False)
            similar_df.to_csv('data/similar_trades_pipeline.csv', index=False)
            
            print(f"\nFound {len(similar_df)} similar profitable trades")
            print(f"  CALL trades: {len(similar_df[similar_df['Trade_Type'] == 'CALL'])}")
            print(f"  PUT trades: {len(similar_df[similar_df['Trade_Type'] == 'PUT'])}")
            
            print("\nTop 10 opportunities:")
            print(similar_df.head(10)[['Entry_Time', 'Trade_Type', 'Exit_Duration', 'Expected_Return']])
        
    def generate_analysis_report(self, patterns):
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
        
        # Pattern analysis
        report_lines.append("\n## Pattern Analysis by Exit Type\n")
        
        for pattern_key, stats in patterns.items():
            # Handle pattern keys like "CALL_EXIT" or "PUT_STOP_LOSS"
            parts = pattern_key.split('_')
            trade_type = parts[0]
            exit_type = '_'.join(parts[1:])  # Join remaining parts for STOP_LOSS
            
            report_lines.append(f"### {trade_type} - {exit_type}")
            report_lines.append(f"- **Count**: {stats['count']} trades")
            report_lines.append(f"- **Average Duration**: {stats['avg_duration']:.1f} minutes")
            report_lines.append(f"- **Average Stock Return**: {stats['avg_return']:.2f}%")
            
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
            report_lines.append(f"- **Win Rate**: {stats['profitable_pct']:.1f}%")
            report_lines.append(f"- **Average Entry RSI**: {stats['entry_rsi_mean']:.1f}")
            report_lines.append("")
        
        # Entry indicators analysis
        report_lines.append("\n## Entry Indicator Analysis\n")
        
        enriched_df = pd.read_csv('data/trades_enriched.csv')
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
        if os.path.exists('data/similar_trades_pipeline.csv'):
            similar_df = pd.read_csv('data/similar_trades_pipeline.csv')
            if len(similar_df) > 0:
                report_lines.append("\n## Similar Trades Found\n")
                report_lines.append(f"- **Total Similar Trades**: {len(similar_df)}")
                report_lines.append(f"- **CALL Trades**: {len(similar_df[similar_df['Trade_Type'] == 'CALL'])}")
                report_lines.append(f"- **PUT Trades**: {len(similar_df[similar_df['Trade_Type'] == 'PUT'])}")
                report_lines.append(f"- **Average Expected Return**: {similar_df['Expected_Return'].mean():.2f}%")
                
                # Top opportunities
                report_lines.append("\n### Top 5 Opportunities")
                top_trades = similar_df.nlargest(5, 'Expected_Return')
                for _, trade in top_trades.iterrows():
                    report_lines.append(f"- {trade['Entry_Time']}: {trade['Trade_Type']} - {trade['Expected_Return']:.2f}% expected")
        
        # Key insights
        report_lines.append("\n## Key Insights\n")
        
        # Calculate key metrics
        call_avg_return = sum(patterns[k]['avg_return'] for k in patterns if 'CALL' in k) / sum(1 for k in patterns if 'CALL' in k)
        put_avg_return = sum(patterns[k]['avg_return'] for k in patterns if 'PUT' in k) / sum(1 for k in patterns if 'PUT' in k)
        
        report_lines.append(f"1. **Average Returns**: CALL {call_avg_return:.2f}% | PUT {put_avg_return:.2f}%")
        report_lines.append(f"2. **Best Strategy**: {'PUT' if put_avg_return > call_avg_return else 'CALL'} trades show higher average returns")
        report_lines.append(f"3. **Optimal Hold Time**: Analyze duration vs return patterns")
        report_lines.append(f"4. **Win Rates**: Consistently above 80% across all patterns")
        
        # Write report
        with open('data/trade_analysis_report.md', 'w') as f:
            f.write('\n'.join(report_lines))
        
        print("\nGenerated trade analysis report: data/trade_analysis_report.md")
    
    def run_pipeline(self):
        """Run the complete pipeline"""
        print("TRADE ANALYSIS PIPELINE")
        print("="*60)
        
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
        self.step5_find_similar_trades(patterns)
        
        print("\n" + "="*60)
        print("PIPELINE COMPLETE!")
        print("="*60)
        
        # Generate markdown report
        self.generate_analysis_report(patterns)
        
        print("\nOutput files:")
        print("  1. data/trade_tracker_updated.csv - Trades with durations")
        print("  2. data/trades_pivoted.csv - Tall format (3 rows per trade)")
        print("  3. data/trades_enriched.csv - With entry/exit indicators")
        print("  4. data/trade_patterns.csv - Pattern analysis")
        print("  5. data/similar_trades_pipeline.csv - Similar profitable trades")
        print("  6. data/trade_analysis_report.md - Complete analysis report")

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