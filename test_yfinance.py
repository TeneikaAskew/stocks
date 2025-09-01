#!/usr/bin/env python3
"""Test yfinance to see actual column structure"""

import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd
import pytz

# Test with a known working date from last week
eastern = pytz.timezone('US/Eastern')
test_date = datetime(2025, 8, 26, 9, 30)  # Tuesday Aug 26, 2025 at 9:30 AM
test_date = eastern.localize(test_date)
end_date = test_date + timedelta(hours=7)  # 4:30 PM

print(f"Testing yfinance with date range: {test_date} to {end_date}")
print("="*60)

# Test with SPY
ticker = "SPY"
print(f"\nFetching {ticker} minute data...")

df = yf.download(
    ticker,
    start=test_date,
    end=end_date,
    interval="1m",
    progress=False,
    prepost=False,
    group_by=None,
    auto_adjust=True,
    threads=False
)

print(f"\nDataFrame shape: {df.shape}")
print(f"DataFrame empty: {df.empty}")

if not df.empty:
    print(f"\nColumn names: {list(df.columns)}")
    print(f"Column types: {df.columns.__class__.__name__}")
    
    if isinstance(df.columns, pd.MultiIndex):
        print("\nMultiIndex detected!")
        print(f"Levels: {df.columns.nlevels}")
        for i in range(df.columns.nlevels):
            print(f"Level {i}: {list(df.columns.get_level_values(i).unique())}")
    
    print(f"\nFirst few rows:")
    print(df.head())
    
    print(f"\nData types:")
    print(df.dtypes)
else:
    print("No data returned!")
    
    # Try with a more recent date
    print("\n" + "="*60)
    print("Trying with yesterday's date...")
    yesterday = datetime.now() - timedelta(days=1)
    if yesterday.weekday() == 6:  # Sunday
        yesterday = yesterday - timedelta(days=2)
    elif yesterday.weekday() == 5:  # Saturday
        yesterday = yesterday - timedelta(days=1)
    
    start = datetime(yesterday.year, yesterday.month, yesterday.day, 9, 30)
    end = datetime(yesterday.year, yesterday.month, yesterday.day, 16, 0)
    start = eastern.localize(start)
    end = eastern.localize(end)
    
    print(f"Testing with: {start} to {end}")
    
    df2 = yf.download(
        ticker,
        start=start,
        end=end,
        interval="1m",
        progress=True,
        prepost=False
    )
    
    if not df2.empty:
        print(f"\nDataFrame shape: {df2.shape}")
        print(f"Column names: {list(df2.columns)}")
        print(f"Column types: {df2.columns.__class__.__name__}")
    else:
        print("Still no data!")