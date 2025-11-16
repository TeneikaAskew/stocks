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
        ticker_dest = dest_data_dir / ticker
        ticker_dest.mkdir(parents=True, exist_ok=True)

        # Try AlphaVantage format first (intraday directory with monthly files)
        av_source = source_data_dir / ticker / "intraday"
        minute_source = source_data_dir / ticker / "minute"

        files_to_process = []
        data_format = None

        # Check for AlphaVantage monthly files
        if av_source.exists():
            av_files = sorted([
                f for f in av_source.glob(f"{ticker}_av_1min_*.parquet")
                if "combined" not in f.name
            ])
            if av_files:
                # Get most recent month's file
                files_to_process = [av_files[-1]]
                data_format = "alphavantage_monthly"
                month_str = files_to_process[0].stem.split("_")[-1]
                print(f"  {ticker.upper()}: Processing AlphaVantage monthly data (month: {month_str})")

        # If no AlphaVantage data, check for daily minute files
        if not files_to_process and minute_source.exists():
            daily_files = sorted(list(minute_source.glob(f"{ticker}_minute_*.parquet")))
            if daily_files:
                # Get files from most recent 30 days
                files_to_process = daily_files[-30:]
                data_format = "minute_daily"
                print(f"  {ticker.upper()}: Processing {len(files_to_process)} daily minute files")

        if not files_to_process:
            print(f"  {ticker.upper()}: No data files found, skipping...")
            continue

        try:
            all_dates = []

            # Process based on data format
            if data_format == "alphavantage_monthly":
                # Read single monthly file
                df = pd.read_parquet(files_to_process[0])
                df['date'] = pd.to_datetime(df.index).date

                for date, day_data in df.groupby('date'):
                    date_str = date.strftime('%Y%m%d')
                    all_dates.append(date_str)
                    _create_daily_json(day_data, ticker_dest, date_str)

            elif data_format == "minute_daily":
                # Process multiple daily files
                for daily_file in files_to_process:
                    df = pd.read_parquet(daily_file)

                    # Extract date from filename or data
                    if df.index.size > 0:
                        date = pd.to_datetime(df.index[0]).date()
                        date_str = date.strftime('%Y%m%d')
                        all_dates.append(date_str)
                        _create_daily_json(df, ticker_dest, date_str)

            # Create dates.json
            all_dates.sort()
            dates_file = ticker_dest / "dates.json"
            with open(dates_file, 'w') as f:
                json.dump(all_dates, f)

            print(f"  {ticker.upper()}: Created {len(all_dates)} daily JSON files")
            if all_dates:
                print(f"  {ticker.upper()}: Date range: {all_dates[0]} to {all_dates[-1]}")

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
