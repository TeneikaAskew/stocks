#!/usr/bin/env python3
"""
Prepare data for GitHub Pages deployment by converting current month's AlphaVantage
parquet data to daily JSON files. This reduces deployment size and speeds up builds.
"""

import os
import shutil
import json
import pandas as pd
from datetime import datetime
from pathlib import Path

def create_daily_json(day_data, ticker_dest, date_str):
    """Create a daily JSON file from parquet data."""
    candlestick_data = []
    volume_data = []

    for timestamp, row in day_data.iterrows():
        # Convert timestamp to Unix time
        unix_time = int(timestamp.timestamp())

        candlestick_data.append({
            "time": unix_time,
            "open": float(row['Open']),
            "high": float(row['High']),
            "low": float(row['Low']),
            "close": float(row['Close'])
        })

        volume_data.append({
            "time": unix_time,
            "value": int(row['Volume']),
            "color": "rgba(16, 185, 129, 0.5)" if row['Close'] >= row['Open'] else "rgba(239, 68, 68, 0.5)"
        })

    # Create the daily JSON file
    json_data = {
        "candlestick": candlestick_data,
        "volume": volume_data
    }

    json_file = ticker_dest / f"{date_str}_1min.json"
    with open(json_file, 'w') as f:
        json.dump(json_data, f, separators=(',', ':'))

def prepare_github_pages_data():
    """Convert most recent month's AlphaVantage parquet data to daily JSON files."""

    print("Preparing GitHub Pages data...")

    # Source and destination paths
    project_root = Path(__file__).parent.parent
    source_data_dir = project_root / "data"
    dest_data_dir = project_root / "chart-viewer" / "data"

    # Clear destination directory
    if dest_data_dir.exists():
        shutil.rmtree(dest_data_dir)
    dest_data_dir.mkdir(parents=True, exist_ok=True)

    tickers = ["iwm", "spy", "qqq"]

    for ticker in tickers:
        ticker_source = source_data_dir / ticker / "intraday"
        ticker_dest = dest_data_dir / ticker
        ticker_dest.mkdir(parents=True, exist_ok=True)

        if not ticker_source.exists():
            print(f"  {ticker.upper()}: intraday directory does not exist, skipping...")
            continue

        # Find all AlphaVantage parquet files (exclude combined)
        av_files = sorted([
            f for f in ticker_source.glob(f"{ticker}_av_1min_*.parquet")
            if "combined" not in f.name
        ])

        if not av_files:
            print(f"  {ticker.upper()}: No AlphaVantage data files found, skipping...")
            continue

        # Get the most recent month's file
        most_recent_file = av_files[-1]
        month_str = most_recent_file.stem.split("_")[-1]  # Extract YYYYMM

        print(f"  {ticker.upper()}: Processing {most_recent_file.name} (month: {month_str})")

        try:
            # Read the parquet file
            df = pd.read_parquet(most_recent_file)

            # Group by date and convert to daily JSON files
            df['date'] = pd.to_datetime(df.index).date
            daily_dates = []

            for date, day_data in df.groupby('date'):
                # Format date as YYYYMMDD
                date_str = date.strftime('%Y%m%d')
                daily_dates.append(date_str)
                create_daily_json(day_data, ticker_dest, date_str)

            # Create dates.json with all dates from this month
            daily_dates.sort()
            dates_file = ticker_dest / "dates.json"
            with open(dates_file, 'w') as f:
                json.dump(daily_dates, f)

            print(f"  {ticker.upper()}: Created {len(daily_dates)} daily JSON files for {month_str}")
            print(f"  {ticker.upper()}: Date range: {daily_dates[0]} to {daily_dates[-1]}")

        except Exception as e:
            print(f"  {ticker.upper()}: Error processing data: {e}")
            import traceback
            traceback.print_exc()
            continue

    print(f"\nGitHub Pages data prepared successfully!")
    print(f"  Location: {dest_data_dir}")
    print(f"\nNote: Only the most recent month's data is deployed to GitHub Pages.")
    print(f"      Older months should be loaded via API when selected.")

if __name__ == "__main__":
    prepare_github_pages_data()
