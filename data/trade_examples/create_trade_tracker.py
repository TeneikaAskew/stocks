#!/usr/bin/env python3
"""
Create trade tracker for identifying entry/exit points in IWM data
Time column serves as the unique ID to join with historical_iwm_0824_0825_with_indicators.csv
"""

import pandas as pd
import os
from datetime import datetime

def create_trade_tracker():
    """Create a new trade tracker CSV with simplified columns"""
    
    # Simplified columns for trade tracking
    columns = [
        'ID',                     # Unique trade ID (T001, T002, etc.)
        'Time',                   # Timestamp - matches IWM data for joining
        'Trade_Type',             # CALL or PUT
        'Action',                 # ENTRY, EXIT, STOP_LOSS, or RUNNER
        'Stop_Loss_ID',           # ID of the stop loss exit for this trade
        'Runner_ID',              # ID of the runner/profit target exit for this trade
        'Parent_Trade_ID',        # For EXIT/STOP_LOSS/RUNNER rows, refers back to ENTRY
        'Duration_Minutes',       # Time in trade (calculated)
        'Notes'                   # Trading notes/rationale
    ]
    
    # Create empty dataframe
    df = pd.DataFrame(columns=columns)
    
    # Save to CSV
    filename = 'data/trade_examples/trade_tracker.csv'
    df.to_csv(filename, index=False)
    print(f"Created trade tracker: {filename}")
    print("\nColumns:")
    for col in columns:
        print(f"  - {col}")
    
    print("\nNote: Time column will be used to join with IWM indicators data")
    print("All price and indicator data will come from historical_iwm_0824_0825_with_indicators.csv")
    
    return filename

def create_example_entries():
    """Create example entries showing the format"""
    
    # Example data - simplified for trade identification
    examples = [
        # Trade 1: CALL example with multiple scenarios
        {
            'ID': 'T001',
            'Time': '2024-10-15 09:35:00',
            'Trade_Type': 'CALL',
            'Action': 'ENTRY',
            'Stop_Loss_ID': 'T001_SL',
            'Runner_ID': 'T001_RUN',
            'Parent_Trade_ID': '',
            'Duration_Minutes': '',
            'Notes': 'Strong upward momentum, breakout pattern'
        },
        {
            'ID': 'T001_EXIT',
            'Time': '2024-10-15 09:38:00',
            'Trade_Type': 'CALL',
            'Action': 'EXIT',
            'Stop_Loss_ID': '',
            'Runner_ID': '',
            'Parent_Trade_ID': 'T001',
            'Duration_Minutes': 3,
            'Notes': 'Target reached, momentum slowing'
        },
        {
            'ID': 'T001_SL',
            'Time': '2024-10-15 09:36:30',
            'Trade_Type': 'CALL',
            'Action': 'STOP_LOSS',
            'Stop_Loss_ID': '',
            'Runner_ID': '',
            'Parent_Trade_ID': 'T001',
            'Duration_Minutes': 1.5,
            'Notes': 'Stop loss level - if price reversed'
        },
        {
            'ID': 'T001_RUN',
            'Time': '2024-10-15 09:42:00',
            'Trade_Type': 'CALL',
            'Action': 'RUNNER',
            'Stop_Loss_ID': '',
            'Runner_ID': '',
            'Parent_Trade_ID': 'T001',
            'Duration_Minutes': 7,
            'Notes': 'Extended target - if held longer'
        },
        # Trade 2: PUT example
        {
            'ID': 'T002',
            'Time': '2024-10-15 10:15:00',
            'Trade_Type': 'PUT',
            'Action': 'ENTRY',
            'Stop_Loss_ID': 'T002_SL',
            'Runner_ID': 'T002_RUN',
            'Parent_Trade_ID': '',
            'Duration_Minutes': '',
            'Notes': 'Rejection at resistance, declining volume'
        },
        {
            'ID': 'T002_EXIT',
            'Time': '2024-10-15 10:19:00',
            'Trade_Type': 'PUT',
            'Action': 'EXIT',
            'Stop_Loss_ID': '',
            'Runner_ID': '',
            'Parent_Trade_ID': 'T002',
            'Duration_Minutes': 4,
            'Notes': 'Support approaching, taking profits'
        }
    ]
    
    # Create dataframe
    df = pd.DataFrame(examples)
    
    # Save to CSV
    filename = 'data/trade_examples/trade_tracker_example.csv'
    df.to_csv(filename, index=False)
    print(f"\nCreated example tracker: {filename}")
    print("\nExample shows:")
    print("  - Trade entries and exits with timestamps")
    print("  - Stop loss and runner scenarios")
    print("  - Duration tracking for analysis")
    print("\nTo use:")
    print("  1. Fill in your profitable trade times")
    print("  2. Join with IWM data using Time column")
    print("  3. Analyze patterns in price/indicators at entry/exit")
    
    return filename

def create_analysis_script():
    """Create a script to analyze trades using the tracker"""
    
    analysis_script = '''#!/usr/bin/env python3
"""
Analyze trades from trade_tracker.csv by joining with IWM indicators data
"""

import pandas as pd
import numpy as np
import os

class TradeAnalyzer:
    def __init__(self):
        self.trades_df = None
        self.iwm_df = None
        
    def load_data(self):
        """Load trade tracker and IWM data"""
        # Load trade tracker
        tracker_file = 'data/trade_examples/trade_tracker.csv'
        if not os.path.exists(tracker_file):
            print(f"Trade tracker not found: {tracker_file}")
            return False
            
        self.trades_df = pd.read_csv(tracker_file)
        self.trades_df['Time'] = pd.to_datetime(self.trades_df['Time'])
        
        # Load IWM data with indicators
        iwm_file = 'data/historical_iwm_0824_0825_with_indicators.csv'
        if not os.path.exists(iwm_file):
            print(f"IWM data not found: {iwm_file}")
            return False
            
        self.iwm_df = pd.read_csv(iwm_file)
        self.iwm_df['Time'] = pd.to_datetime(self.iwm_df['Time'])
        
        print(f"Loaded {len(self.trades_df)} trades")
        print(f"IWM data: {len(self.iwm_df)} rows")
        
        return True
    
    def analyze_trades(self):
        """Join trades with IWM data and analyze"""
        # Join on Time column
        entry_trades = self.trades_df[self.trades_df['Action'] == 'ENTRY']
        exit_trades = self.trades_df[self.trades_df['Action'] == 'EXIT']
        
        # Merge with IWM data
        entries_with_data = pd.merge(entry_trades, self.iwm_df, on='Time', how='left')
        exits_with_data = pd.merge(exit_trades, self.iwm_df, on='Time', how='left')
        
        print("\\nEntry Analysis:")
        print("-" * 50)
        for _, entry in entries_with_data.iterrows():
            if pd.notna(entry['Last']):
                print(f"\\nTrade {entry['ID']} ({entry['Trade_Type']}):")
                print(f"  Time: {entry['Time']}")
                print(f"  Price: {entry['Last']:.2f}")
                print(f"  RSI: {entry['RSI14_W']:.2f}")
                print(f"  VWAP: {entry['VWAP']:.2f}")
                print(f"  Volume: {entry['Volume']:,.0f}")
                print(f"  Notes: {entry['Notes']}")
            else:
                print(f"\\nWarning: No IWM data found for {entry['Time']}")
        
        # Calculate statistics
        call_entries = entries_with_data[entries_with_data['Trade_Type'] == 'CALL']
        put_entries = entries_with_data[entries_with_data['Trade_Type'] == 'PUT']
        
        if len(call_entries) > 0:
            print("\\nCALL Entry Statistics:")
            print(f"  Avg RSI at entry: {call_entries['RSI14_W'].mean():.2f}")
            print(f"  Avg Volume: {call_entries['Volume'].mean():,.0f}")
            
        if len(put_entries) > 0:
            print("\\nPUT Entry Statistics:")
            print(f"  Avg RSI at entry: {put_entries['RSI14_W'].mean():.2f}")
            print(f"  Avg Volume: {put_entries['Volume'].mean():,.0f}")
    
    def export_enriched_trades(self, output_file='data/trades_with_indicators.csv'):
        """Export trades with all indicator data"""
        # Join all trades with IWM data
        enriched_trades = pd.merge(
            self.trades_df, 
            self.iwm_df, 
            on='Time', 
            how='left',
            suffixes=('', '_iwm')
        )
        
        enriched_trades.to_csv(output_file, index=False)
        print(f"\\nExported enriched trades to: {output_file}")
        return enriched_trades

if __name__ == "__main__":
    analyzer = TradeAnalyzer()
    if analyzer.load_data():
        analyzer.analyze_trades()
        analyzer.export_enriched_trades()
'''
    
    filename = 'analyze_trades.py'
    with open(filename, 'w') as f:
        f.write(analysis_script)
    
    print(f"\nCreated analysis script: {filename}")
    print("This script will join your trades with IWM indicator data")
    
    return filename

def main():
    """Create all tracking files"""
    print("Creating Trade Tracker Files")
    print("="*60)
    
    # Create main tracker
    create_trade_tracker()
    
    # Create example file
    create_example_entries()
    
    # Create analysis script
    create_analysis_script()
    
    # Remove old options tracker files if they exist
    old_files = ['data/options_tracker.csv', 'data/options_tracker_example.csv', 'track_options.py']
    for old_file in old_files:
        if os.path.exists(old_file):
            os.remove(old_file)
            print(f"\nRemoved old file: {old_file}")
    
    print("\n" + "="*60)
    print("Trade tracker setup complete!")
    print("\nFiles created:")
    print("  1. data/trade_examples/trade_tracker.csv - Main tracking spreadsheet")
    print("  2. data/trade_examples/trade_tracker_example.csv - Example entries")
    print("  3. analyze_trades.py - Script to join with IWM data")
    print("\nWorkflow:")
    print("  1. Enter your profitable trades in data/trade_examples/trade_tracker.csv")
    print("  2. Use exact timestamps from IWM data")
    print("  3. Run analyze_trades.py to join with indicators")
    print("  4. Analyze patterns to refine iwm_analysis.py")

if __name__ == "__main__":
    main()