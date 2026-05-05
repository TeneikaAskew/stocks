"""
Convert Alpha Vantage parquet files to JSON for web consumption
This script should be run periodically to update the web app's data
"""

import pandas as pd
import json
import os
from pathlib import Path
from datetime import datetime

def convert_parquet_to_json(ticker, date_str, data_dir='../data', output_dir='data'):
    """
    Convert a single parquet file to JSON

    Args:
        ticker: Stock ticker (e.g., 'iwm', 'qqq', 'spy')
        date_str: Date string in YYYYMMDD format
        data_dir: Base data directory
        output_dir: Output directory for JSON files
    """
    # Construct paths
    parquet_path = Path(data_dir) / ticker / 'options' / f'{ticker}_av_options_{date_str}.parquet'
    output_path = Path(output_dir) / ticker / f'{ticker}_options_{date_str}.json'

    # Create output directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not parquet_path.exists():
        print(f"File not found: {parquet_path}")
        return False

    try:
        # Read parquet file
        df = pd.read_parquet(parquet_path)

        # Convert date columns to strings
        date_columns = ['expiration', 'date', 'snapshot_date', 'fetch_timestamp']
        for col in date_columns:
            if col in df.columns:
                df[col] = df[col].astype(str)

        # Convert to JSON-friendly format
        data = {
            'ticker': ticker.upper(),
            'date': date_str,
            'snapshot_timestamp': df['snapshot_date'].iloc[0] if 'snapshot_date' in df.columns else date_str,
            'options': df.to_dict(orient='records')
        }

        # Write JSON file
        with open(output_path, 'w') as f:
            json.dump(data, f, separators=(',', ':'))  # Compact JSON

        print(f"[OK] Converted {ticker} {date_str} -> {output_path}")
        return True

    except Exception as e:
        print(f"[ERROR] Error converting {parquet_path}: {e}")
        return False


def convert_recent_data(tickers=['iwm', 'qqq', 'spy'], days=30):
    """
    Convert recent parquet files to JSON

    Args:
        tickers: List of tickers to process
        days: Number of recent days to convert
    """
    data_dir = '../data'
    output_dir = 'data'

    for ticker in tickers:
        ticker_path = Path(data_dir) / ticker / 'options'

        if not ticker_path.exists():
            print(f"Directory not found: {ticker_path}")
            continue

        # Get all parquet files for this ticker
        parquet_files = sorted(ticker_path.glob(f'{ticker}_av_options_*.parquet'))

        # Take the most recent files
        recent_files = parquet_files[-days:] if len(parquet_files) > days else parquet_files

        print(f"\nProcessing {len(recent_files)} files for {ticker.upper()}...")

        for parquet_file in recent_files:
            # Extract date from filename
            date_str = parquet_file.stem.split('_')[-1]

            # Skip combined files (too large for GitHub)
            if date_str == 'combined':
                print(f"Skipping combined file: {parquet_file.name}")
                continue

            convert_parquet_to_json(ticker, date_str, data_dir, output_dir)


def create_index_file(output_dir='data'):
    """
    Create an index file listing all available dates for each ticker
    """
    index = {}

    for ticker_dir in Path(output_dir).iterdir():
        if ticker_dir.is_dir():
            ticker = ticker_dir.name
            json_files = sorted(ticker_dir.glob(f'{ticker}_options_*.json'))

            dates = []
            for json_file in json_files:
                date_str = json_file.stem.split('_')[-1]
                dates.append(date_str)

            index[ticker] = {
                'count': len(dates),
                'first_date': dates[0] if dates else None,
                'last_date': dates[-1] if dates else None,
                'dates': dates
            }

    # Write index file
    index_path = Path(output_dir) / 'index.json'
    with open(index_path, 'w') as f:
        json.dump(index, f, indent=2)

    print(f"\n[OK] Created index file: {index_path}")
    print(f"Available tickers: {list(index.keys())}")
    for ticker, info in index.items():
        print(f"  {ticker.upper()}: {info['count']} dates ({info['first_date']} to {info['last_date']})")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Convert parquet files to JSON for web app')
    parser.add_argument('--tickers', nargs='+', default=['iwm', 'qqq', 'spy'],
                       help='Tickers to process (default: iwm qqq spy)')
    parser.add_argument('--days', type=int, default=30,
                       help='Number of recent days to convert (default: 30)')
    parser.add_argument('--date', type=str, help='Specific date to convert (YYYYMMDD)')

    args = parser.parse_args()

    if args.date:
        # Convert specific date
        for ticker in args.tickers:
            convert_parquet_to_json(ticker, args.date)
    else:
        # Convert recent data
        convert_recent_data(args.tickers, args.days)

    # Create index file
    create_index_file()
