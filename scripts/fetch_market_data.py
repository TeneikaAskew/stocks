#!/usr/bin/env python3
"""
Fetch minute-level market data from AlphaVantage for multiple tickers
and calculate daily OHLCV with comprehensive technical indicators.

Supports: IWM, SPY, QQQ, and SPX
"""

import pandas as pd
import requests
from datetime import datetime, timedelta, time
import os
import sys
from pathlib import Path
import pytz
import argparse
import json
from dotenv import load_dotenv

load_dotenv()

AV_BASE_URL = 'https://www.alphavantage.co/query'
AV_API_KEY = os.environ.get('AV_API_KEY') or os.environ.get('ALPHA_VANTAGE_API_KEY', '')

def calculate_daily_ohlcv(minute_df):
    """
    Calculate daily OHLCV from minute-level data.
    This ensures we have the true daily values, not pre-aggregated summaries.
    """
    if minute_df.empty:
        return pd.DataFrame()
    
    # Group by date and calculate OHLCV
    daily_data = minute_df.groupby(minute_df.index.date).agg({
        'Open': 'first',      # First minute's open
        'High': 'max',        # Highest high of the day
        'Low': 'min',         # Lowest low of the day
        'Close': 'last',      # Last minute's close
        'Volume': 'sum'       # Total volume
    })
    
    # Convert index to datetime
    daily_data.index = pd.to_datetime(daily_data.index)
    
    return daily_data

def calculate_rsi(prices, period=14):
    """
    Calculate RSI (Relative Strength Index).
    """
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_ema(prices, period):
    """
    Calculate EMA (Exponential Moving Average).
    """
    return prices.ewm(span=period, adjust=False).mean()

def calculate_rvol(volume, volume_avg):
    """
    Calculate RVOL (Relative Volume).
    RVOL = Current Volume / Average Volume
    """
    return volume / volume_avg.where(volume_avg > 0, 1)  # Avoid division by zero

def calculate_stochastic_rsi(prices, rsi_period=14, stoch_period=14, smooth_k=3, smooth_d=3):
    """
    Calculate Stochastic RSI.
    StochRSI = (RSI - RSI Low) / (RSI High - RSI Low)
    """
    # Calculate RSI first
    rsi = calculate_rsi(prices, rsi_period)
    
    # Calculate Stochastic RSI
    rsi_low = rsi.rolling(window=stoch_period).min()
    rsi_high = rsi.rolling(window=stoch_period).max()
    
    # Avoid division by zero
    denominator = rsi_high - rsi_low
    stoch_rsi = ((rsi - rsi_low) / denominator.where(denominator != 0, 1)) * 100
    
    # Smooth %K
    stoch_rsi_k = stoch_rsi.rolling(window=smooth_k).mean()
    
    # Calculate %D (signal line)
    stoch_rsi_d = stoch_rsi_k.rolling(window=smooth_d).mean()
    
    return stoch_rsi_k, stoch_rsi_d

def calculate_obv(prices, volumes):
    """
    Calculate OBV (On-Balance Volume).
    OBV = Previous OBV + Volume (if close > previous close)
    OBV = Previous OBV - Volume (if close < previous close)
    OBV = Previous OBV (if close = previous close)
    """
    price_diff = prices.diff()
    obv = pd.Series(index=prices.index, dtype='float64')
    obv.iloc[0] = volumes.iloc[0] if len(volumes) > 0 else 0
    
    for i in range(1, len(prices)):
        if price_diff.iloc[i] > 0:
            obv.iloc[i] = obv.iloc[i-1] + volumes.iloc[i]
        elif price_diff.iloc[i] < 0:
            obv.iloc[i] = obv.iloc[i-1] - volumes.iloc[i]
        else:
            obv.iloc[i] = obv.iloc[i-1]
    
    return obv

def calculate_atr(high, low, close, period=14):
    """
    Calculate ATR (Average True Range).
    True Range = max(High - Low, abs(High - Previous Close), abs(Low - Previous Close))
    ATR = Moving average of True Range
    """
    # Calculate True Range components
    high_low = high - low
    high_close = abs(high - close.shift(1))
    low_close = abs(low - close.shift(1))
    
    # True Range is the maximum of the three
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    # Calculate ATR as exponential moving average of True Range
    atr = true_range.ewm(span=period, adjust=False).mean()
    
    return atr

def fetch_minute_data_for_date(ticker, date):
    """
    Fetch minute-level data for a specific date from AlphaVantage TIME_SERIES_INTRADAY.
    """
    if not AV_API_KEY:
        print(f"  ERROR: No AlphaVantage API key set")
        return pd.DataFrame()

    month_str = date.strftime('%Y-%m')
    date_str = date.strftime('%Y-%m-%d')

    try:
        params = {
            'function': 'TIME_SERIES_INTRADAY',
            'symbol': ticker,
            'interval': '1min',
            'month': month_str,
            'outputsize': 'full',
            'adjusted': 'true',
            'entitlement': 'realtime',
            'extended_hours': 'true',
            'apikey': AV_API_KEY,
            'datatype': 'json',
        }
        resp = requests.get(AV_BASE_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if 'Error Message' in data:
            print(f"  AV error for {ticker}: {data['Error Message']}")
            return pd.DataFrame()
        if 'Information' in data or 'Note' in data:
            print(f"  AV rate limit for {ticker}: {data.get('Information', data.get('Note', ''))}")
            return pd.DataFrame()

        ts = data.get('Time Series (1min)', {})
        if not ts:
            print(f"  No data for {ticker} month {month_str}")
            return pd.DataFrame()

        df = pd.DataFrame.from_dict(ts, orient='index')
        df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in ['Open', 'High', 'Low', 'Close']:
            df[col] = pd.to_numeric(df[col])
        df['Volume'] = pd.to_numeric(df['Volume']).astype('int64')
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        # Filter to the requested date
        df = df[df.index.date == date]

        if not df.empty:
            # AV returns naive ET timestamps; localize for compatibility
            eastern = pytz.timezone('US/Eastern')
            if df.index.tz is None:
                df.index = df.index.tz_localize('US/Eastern')
        
        return df
        
    except Exception as e:
        print(f"  Error fetching minute data for {date}: {e}")
        return pd.DataFrame()

def calculate_all_indicators(df, ticker_symbol, is_minute_data=False):
    """
    Calculate all technical indicators for a dataframe.
    
    Args:
        df: DataFrame with OHLCV data
        ticker_symbol: Ticker symbol (for SPX volume handling)
        is_minute_data: If True, adjust window sizes for minute-level data
    """
    # Adjust window sizes for minute vs daily data
    # For minute data, we want shorter windows since we have 390 bars per day
    if is_minute_data:
        # For minute data: approximate daily equivalents
        # 390 minutes = 1 day, so:
        ma_5_window = 5  # 5 minutes
        ma_10_window = 10  # 10 minutes
        ma_20_window = 20  # 20 minutes
        ma_50_window = 50  # 50 minutes
        ma_390_window = 390  # Full day
        volatility_short = 30  # 30 minutes
        volatility_long = 390  # Full day
    else:
        # For daily data: use day counts
        ma_5_window = 5
        ma_10_window = 10
        ma_20_window = 20
        ma_50_window = 50
        ma_390_window = None  # Not applicable for daily
        volatility_short = 5
        volatility_long = 20
    
    # Calculate moving averages
    df['ma_5'] = df['Close'].rolling(window=ma_5_window).mean()
    df['ma_10'] = df['Close'].rolling(window=ma_10_window).mean()
    df['ma_20'] = df['Close'].rolling(window=ma_20_window).mean()
    df['ma_50'] = df['Close'].rolling(window=ma_50_window).mean()
    
    if is_minute_data:
        # Add full-day MA for minute data
        df['ma_390'] = df['Close'].rolling(window=ma_390_window).mean()
    
    df['volume_ma_10'] = df['Volume'].rolling(window=ma_10_window).mean()
    df['volume_ma_20'] = df['Volume'].rolling(window=ma_20_window).mean()
    
    # Calculate returns and volatility
    df['return'] = df['Close'].pct_change()
    if is_minute_data:
        df['volatility_30min'] = df['return'].rolling(window=volatility_short).std()
        df['volatility_day'] = df['return'].rolling(window=volatility_long).std()
    else:
        df['daily_return'] = df['return']  # Keep for compatibility
        df['volatility_5d'] = df['return'].rolling(window=volatility_short).std()
        df['volatility_20d'] = df['return'].rolling(window=volatility_long).std()
    
    # Calculate EMAs
    if is_minute_data:
        df['ema_9'] = calculate_ema(df['Close'], 9)
        df['ema_21'] = calculate_ema(df['Close'], 21)
        df['ema_50'] = calculate_ema(df['Close'], 50)
    else:
        df['ema_9'] = calculate_ema(df['Close'], 9)
        df['ema_21'] = calculate_ema(df['Close'], 21)
        df['ema_50'] = calculate_ema(df['Close'], 50)
    
    # Calculate RSI
    if is_minute_data:
        df['rsi_14'] = calculate_rsi(df['Close'], 14)  # 14 minute RSI
        df['rsi_30'] = calculate_rsi(df['Close'], 30)  # 30 minute RSI
    else:
        df['rsi_14'] = calculate_rsi(df['Close'], 14)
        df['rsi_9'] = calculate_rsi(df['Close'], 9)
    
    # Calculate RVOL (Relative Volume)
    df['rvol'] = calculate_rvol(df['Volume'], df['volume_ma_20'])
    df['rvol_10'] = calculate_rvol(df['Volume'], df['volume_ma_10'])
    
    # Calculate Stochastic RSI
    df['stoch_rsi_k'], df['stoch_rsi_d'] = calculate_stochastic_rsi(df['Close'])
    
    # Calculate OBV (skip for SPX as it has no volume)
    if ticker_symbol not in ('^GSPC', 'SPX'):
        df['obv'] = calculate_obv(df['Close'], df['Volume'])
    
    # Calculate ATR
    df['atr_14'] = calculate_atr(df['High'], df['Low'], df['Close'], 14)
    df['atr_20'] = calculate_atr(df['High'], df['Low'], df['Close'], 20)
    
    # Additional metrics
    df['volume_usd'] = df['Volume'] * df['Close']
    df['high_low_spread'] = df['High'] - df['Low']
    df['high_low_spread_pct'] = (df['High'] - df['Low']) / df['Low'] * 100
    df['intraday_return'] = (df['Close'] - df['Open']) / df['Open'] * 100
    
    return df

def fetch_historical_daily_data(ticker_symbol, start_date, end_date):
    """
    Fetch historical daily data from AlphaVantage TIME_SERIES_DAILY_ADJUSTED.

    Args:
        ticker_symbol: Ticker symbol (e.g., 'SPY', 'SPX')
        start_date: Start date (YYYY-MM-DD or datetime.date)
        end_date: End date (YYYY-MM-DD or datetime.date)

    Returns:
        DataFrame with daily OHLCV data
    """
    if not AV_API_KEY:
        print("  ERROR: No AlphaVantage API key set")
        return pd.DataFrame()

    try:
        print(f"  Fetching historical daily data from {start_date} to {end_date}...")

        params = {
            'function': 'TIME_SERIES_DAILY_ADJUSTED',
            'symbol': ticker_symbol,
            'outputsize': 'full',
            'datatype': 'json',
            'apikey': AV_API_KEY,
        }
        resp = requests.get(AV_BASE_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if 'Error Message' in data:
            print(f"  AV daily error for {ticker_symbol}: {data['Error Message']}")
            return pd.DataFrame()
        if 'Information' in data or 'Note' in data:
            print(f"  AV rate limit: {data.get('Information', data.get('Note', ''))}")
            return pd.DataFrame()

        ts = data.get('Time Series (Daily)', {})
        if not ts:
            print(f"  No daily data for {ticker_symbol}")
            return pd.DataFrame()

        df = pd.DataFrame.from_dict(ts, orient='index')
        df = df.rename(columns={
            '1. open': 'Open',
            '2. high': 'High',
            '3. low': 'Low',
            '4. close': 'Close',
            '5. adjusted close': 'Adj Close',
            '6. volume': 'Volume',
        })
        for col in ['Open', 'High', 'Low', 'Close']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col])
        if 'Volume' in df.columns:
            df['Volume'] = pd.to_numeric(df['Volume']).astype('int64')
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        # Filter to date range
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        df = df[(df.index >= start_dt) & (df.index <= end_dt)]

        if not df.empty:
            print(f"  Fetched {len(df)} days of historical data")
        return df

    except Exception as e:
        print(f"  Error fetching historical data: {e}")
        return pd.DataFrame()

def fetch_ticker_data(ticker_symbol, ticker_name=None, target_date=None, historical=False, start_date=None, end_date=None):
    """
    Fetch and process data for a specific ticker.

    Args:
        ticker_symbol: Ticker symbol (e.g., 'SPY', 'SPX')
        ticker_name: Display name for the ticker
        target_date: Target date for single-day fetch (YYYY-MM-DD)
        historical: If True, fetch historical daily data beyond 7-day window
        start_date: Start date for historical fetch (YYYY-MM-DD)
        end_date: End date for historical fetch (YYYY-MM-DD)
    """
    try:
        # Use display name if provided, otherwise use symbol
        display_name = ticker_name if ticker_name else ticker_symbol
        display_name_lower = display_name.lower()
        
        # Create ticker-specific data directories
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        
        # Create ticker-specific folders
        ticker_dir = data_dir / display_name_lower
        ticker_dir.mkdir(exist_ok=True)
        
        # Create minute subfolder for this ticker
        minute_dir = ticker_dir / "minute"
        minute_dir.mkdir(exist_ok=True)
        
        if target_date:
            today = datetime.strptime(target_date, '%Y-%m-%d').date()
        else:
            today = datetime.now().date()
        current_year = today.year
        
        # File paths - now in ticker-specific folders
        daily_parquet = ticker_dir / f"{display_name_lower}_{current_year}.parquet"
        minute_parquet_template = str(minute_dir / f"{display_name_lower}_minute_{{}}.parquet")
        
        print(f"\n{'='*60}")
        print(f"Fetching {display_name} ({ticker_symbol}) Data")
        print(f"{'='*60}")

        # Handle historical data fetch (daily data beyond 7-day window)
        if historical and start_date and end_date:
            print(f"Historical mode: Fetching daily data from {start_date} to {end_date}")

            # Fetch historical daily data
            historical_df = fetch_historical_daily_data(ticker_symbol, start_date, end_date)

            if not historical_df.empty:
                # Add metadata
                historical_df['ticker'] = display_name
                historical_df['ticker_symbol'] = ticker_symbol
                historical_df['fetch_timestamp'] = datetime.now()
                historical_df['data_source'] = 'daily_historical'

                # Calculate all indicators
                historical_df = calculate_all_indicators(historical_df, ticker_symbol, is_minute_data=False)

                # Save to parquet
                # Group by year and save to separate files
                for year in historical_df.index.year.unique():
                    year_data = historical_df[historical_df.index.year == year]
                    year_parquet = ticker_dir / f"{display_name_lower}_{year}.parquet"

                    # Merge with existing data if file exists
                    if year_parquet.exists():
                        existing_df = pd.read_parquet(year_parquet)
                        combined_df = pd.concat([existing_df, year_data])
                        combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
                        combined_df = combined_df.sort_index()
                        year_data = calculate_all_indicators(combined_df, ticker_symbol, is_minute_data=False)

                    year_data.to_parquet(year_parquet, compression='snappy', index=True)
                    print(f"  Saved {len(year_data)} records to {year_parquet}")

                # Update summary
                summary_file = ticker_dir / f"{display_name_lower}_summary.json"
                summary = {
                    "ticker": display_name,
                    "ticker_symbol": ticker_symbol,
                    "last_update": datetime.now().isoformat(),
                    "last_date": str(historical_df.index.max()),
                    "first_date": str(historical_df.index.min()),
                    "total_daily_records": len(historical_df),
                    "current_year_file": f"{display_name_lower}_{current_year}.parquet",
                    "latest_close": float(historical_df['Close'].iloc[-1]),
                    "latest_volume": int(historical_df['Volume'].iloc[-1]) if 'Volume' in historical_df.columns else 0,
                    "data_source": "historical_daily",
                }

                with open(summary_file, 'w') as f:
                    json.dump(summary, f, indent=2)

                print(f"\nHistorical fetch complete: {len(historical_df)} days")
                print(f"Latest close: ${summary['latest_close']:.2f}")

            return True

        # Determine dates to fetch
        # Yahoo Finance only provides minute data for last 7 days
        max_lookback = 7
        dates_to_fetch = []
        
        if daily_parquet.exists():
            existing_df = pd.read_parquet(daily_parquet)
            if not existing_df.empty:
                last_date = existing_df.index.max().date()
                start_date = last_date + timedelta(days=1)
                print(f"Existing data found. Last date: {last_date}")
            else:
                start_date = max(today - timedelta(days=max_lookback), datetime(current_year, 1, 1).date())
        else:
            # Start from 7 days ago or beginning of year, whichever is later
            start_date = max(today - timedelta(days=max_lookback), datetime(current_year, 1, 1).date())
            print(f"No existing data for {current_year}. Starting from {start_date}")
        
        # Create list of trading days to fetch
        current_date = start_date
        while current_date <= today:
            # Skip weekends (market closed)
            if current_date.weekday() < 5:  # Monday = 0, Friday = 4
                dates_to_fetch.append(current_date)
            current_date += timedelta(days=1)
        
        if not dates_to_fetch:
            print(f"{display_name} data is already up to date")
            return True
        
        print(f"Fetching minute data for {len(dates_to_fetch)} trading days")
        
        all_daily_data = []
        
        # Fetch minute data for each day and calculate OHLCV
        for fetch_date in dates_to_fetch:
            print(f"Fetching minute data for {fetch_date}...")
            
            # Check if minute data already exists for this date
            minute_file = minute_parquet_template.format(fetch_date.strftime('%Y%m%d'))
            
            if Path(minute_file).exists():
                print(f"  Loading existing minute data from {minute_file}")
                minute_df = pd.read_parquet(minute_file)
                
                # Handle multi-level columns if present in saved file
                if isinstance(minute_df.columns, pd.MultiIndex):
                    # Use level 1 which contains the price types (Open, High, Low, etc.)
                    minute_df.columns = minute_df.columns.get_level_values(1)
                
                # Validate loaded data has required columns
                required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
                if not all(col in minute_df.columns for col in required_columns):
                    # Standardize column names only if we are missing required ones
                    column_mapping = {}
                    for col in minute_df.columns:
                        col_lower = str(col).lower().strip()
                        normalized = col_lower.replace(' ', '_')

                        if normalized == 'open':
                            column_mapping[col] = 'Open'
                        elif normalized == 'high':
                            column_mapping[col] = 'High'
                        elif normalized == 'low':
                            column_mapping[col] = 'Low'
                        elif normalized in ('close', 'adj_close', 'adjclose'):
                            column_mapping[col] = 'Close'
                        elif normalized == 'volume':
                            column_mapping[col] = 'Volume'

                    if column_mapping:
                        minute_df = minute_df.rename(columns=column_mapping)

                # Validate loaded data has required columns
                required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
                missing_columns = [col for col in required_columns if col not in minute_df.columns]

                if missing_columns:
                    print(f"  WARNING: Loaded file missing columns: {missing_columns}")
                    print(f"  Available columns: {list(minute_df.columns)}")
                    print(f"  Attempting to re-fetch data for {fetch_date}")
                    minute_df = fetch_minute_data_for_date(ticker_symbol, fetch_date)
                    
                    if not minute_df.empty and all(col in minute_df.columns for col in required_columns):
                        # Re-save with correct format
                        minute_df.to_parquet(minute_file, compression='snappy')
                        print(f"  Re-saved {len(minute_df)} minute bars with correct format")
                    else:
                        print(f"  Failed to get valid data for {fetch_date}")
                        continue
            else:
                # Fetch new minute data
                minute_df = fetch_minute_data_for_date(ticker_symbol, fetch_date)
                
                if not minute_df.empty:
                    # Validate that we have the required columns
                    required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
                    if not all(col in minute_df.columns for col in required_columns):
                        column_mapping = {}
                        for col in minute_df.columns:
                            col_lower = str(col).lower().strip()
                            normalized = col_lower.replace(' ', '_')

                            if normalized == 'open':
                                column_mapping[col] = 'Open'
                            elif normalized == 'high':
                                column_mapping[col] = 'High'
                            elif normalized == 'low':
                                column_mapping[col] = 'Low'
                            elif normalized in ('close', 'adj_close', 'adjclose'):
                                column_mapping[col] = 'Close'
                            elif normalized == 'volume':
                                column_mapping[col] = 'Volume'

                        if column_mapping:
                            minute_df = minute_df.rename(columns=column_mapping)

                    missing_columns = [col for col in required_columns if col not in minute_df.columns]

                    if missing_columns:
                        print(f"  ERROR: Missing required columns: {missing_columns}")
                        print(f"  Available columns: {list(minute_df.columns)}")
                        print(f"  Skipping {fetch_date} due to invalid data format")
                        continue
                    
                    # Calculate indicators for minute data before saving
                    minute_df = calculate_all_indicators(minute_df, ticker_symbol, is_minute_data=True)
                    
                    # Save minute data with indicators
                    minute_df.to_parquet(minute_file, compression='snappy')
                    print(f"  Saved {len(minute_df)} minute bars with indicators to {minute_file}")
                else:
                    print(f"  No data available for {fetch_date} (market holiday?)")
                    continue
            
            # Calculate daily OHLCV from minute data
            if not minute_df.empty:
                daily_ohlcv = calculate_daily_ohlcv(minute_df)
                if not daily_ohlcv.empty:
                    all_daily_data.append(daily_ohlcv)
                    print(f"  Calculated daily OHLCV: O={daily_ohlcv['Open'].iloc[0]:.2f}, "
                          f"H={daily_ohlcv['High'].iloc[0]:.2f}, L={daily_ohlcv['Low'].iloc[0]:.2f}, "
                          f"C={daily_ohlcv['Close'].iloc[0]:.2f}, V={daily_ohlcv['Volume'].iloc[0]:,.0f}")
        
        if not all_daily_data:
            print(f"No new data fetched for {display_name}")
            return True
        
        # Combine all daily data
        new_daily_df = pd.concat(all_daily_data).sort_index()
        
        # Add metadata
        new_daily_df['ticker'] = display_name
        new_daily_df['ticker_symbol'] = ticker_symbol
        new_daily_df['fetch_timestamp'] = datetime.now()
        new_daily_df['data_source'] = 'minute_aggregation'
        
        print(f"\nCalculated {len(new_daily_df)} days of OHLCV from minute data")
        
        # Merge with existing daily data if it exists
        if daily_parquet.exists():
            existing_df = pd.read_parquet(daily_parquet)
            # Combine and remove duplicates (keeping the latest)
            combined_df = pd.concat([existing_df, new_daily_df])
            combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
            combined_df = combined_df.sort_index()
            
            # Recalculate all indicators on the full dataset
            combined_df = calculate_all_indicators(combined_df, ticker_symbol)
            
            new_daily_df = combined_df
            print(f"Total records after merge: {len(new_daily_df)}")
        else:
            # Calculate all indicators for new data
            new_daily_df = calculate_all_indicators(new_daily_df, ticker_symbol)
        
        # Save updated daily data
        new_daily_df.to_parquet(daily_parquet, compression='snappy', index=True)
        print(f"Daily data saved to {daily_parquet}")
        
        # Create summary file in ticker directory
        summary_file = ticker_dir / f"{display_name_lower}_summary.json"
        summary = {
            "ticker": display_name,
            "ticker_symbol": ticker_symbol,
            "last_update": datetime.now().isoformat(),
            "last_date": str(new_daily_df.index.max()),
            "first_date": str(new_daily_df.index.min()),
            "total_daily_records": len(new_daily_df),
            "minute_data_available_from": str(max(new_daily_df.index.max().date() - timedelta(days=6), new_daily_df.index.min().date())),
            "current_year_file": f"{display_name_lower}_{current_year}.parquet",
            "latest_close": float(new_daily_df['Close'].iloc[-1]),
            "latest_volume": int(new_daily_df['Volume'].iloc[-1]) if 'Volume' in new_daily_df.columns else 0,
            "latest_rsi_14": float(new_daily_df['rsi_14'].iloc[-1]) if 'rsi_14' in new_daily_df.columns and not pd.isna(new_daily_df['rsi_14'].iloc[-1]) else None,
            "latest_rvol": float(new_daily_df['rvol'].iloc[-1]) if 'rvol' in new_daily_df.columns and not pd.isna(new_daily_df['rvol'].iloc[-1]) else None,
            "latest_stoch_rsi_k": float(new_daily_df['stoch_rsi_k'].iloc[-1]) if 'stoch_rsi_k' in new_daily_df.columns and not pd.isna(new_daily_df['stoch_rsi_k'].iloc[-1]) else None,
            "latest_stoch_rsi_d": float(new_daily_df['stoch_rsi_d'].iloc[-1]) if 'stoch_rsi_d' in new_daily_df.columns and not pd.isna(new_daily_df['stoch_rsi_d'].iloc[-1]) else None,
            "latest_obv": float(new_daily_df['obv'].iloc[-1]) if 'obv' in new_daily_df.columns and not pd.isna(new_daily_df['obv'].iloc[-1]) else None,
            "latest_atr_14": float(new_daily_df['atr_14'].iloc[-1]) if 'atr_14' in new_daily_df.columns and not pd.isna(new_daily_df['atr_14'].iloc[-1]) else None,
            "data_source": "1-minute aggregation",
            "ytd_return": float((new_daily_df['Close'].iloc[-1] / new_daily_df[new_daily_df.index.year == current_year]['Close'].iloc[0] - 1) * 100) if len(new_daily_df[new_daily_df.index.year == current_year]) > 0 else 0
        }
        
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\nSummary saved to {summary_file}")
        print(f"Latest close: ${summary['latest_close']:.2f}")
        print(f"YTD return: {summary['ytd_return']:.2f}%")
        
        return True
        
    except Exception as e:
        print(f"Error fetching {display_name} data: {e}")
        return False

def main():
    """
    Main function to fetch data for specified tickers.
    """
    parser = argparse.ArgumentParser(description='Fetch market data for specified tickers')
    parser.add_argument('--tickers', nargs='+',
                       choices=['IWM', 'SPY', 'QQQ', 'SPX', 'ALL'],
                       default=['ALL'],
                       help='Tickers to fetch (default: ALL)')
    parser.add_argument('--date', type=str,
                       help='Date to fetch data for (YYYY-MM-DD format). If not provided, uses current date.')
    parser.add_argument('--historical', action='store_true',
                       help='Fetch historical daily data beyond 7-day minute window')
    parser.add_argument('--start-date', type=str,
                       help='Start date for historical fetch (YYYY-MM-DD format)')
    parser.add_argument('--end-date', type=str,
                       help='End date for historical fetch (YYYY-MM-DD format)')

    args = parser.parse_args()
    
    # Define ticker mappings
    ticker_mappings = {
        'IWM': ('IWM', None),      # Russell 2000 ETF
        'SPY': ('SPY', None),      # S&P 500 ETF
        'QQQ': ('QQQ', None),      # Nasdaq 100 ETF
        'SPX': ('SPX', 'SPX'),     # S&P 500 Index
    }
    
    # Determine which tickers to fetch
    if 'ALL' in args.tickers:
        tickers_to_fetch = list(ticker_mappings.keys())
    else:
        tickers_to_fetch = args.tickers
    
    print(f"Market Data Fetcher")
    print(f"{'='*60}")
    print(f"Fetching data for: {', '.join(tickers_to_fetch)}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Track success/failure
    results = {}
    
    # Fetch data for each ticker
    for ticker in tickers_to_fetch:
        symbol, display_name = ticker_mappings[ticker]
        success = fetch_ticker_data(
            symbol,
            display_name,
            args.date,
            historical=args.historical,
            start_date=args.start_date,
            end_date=args.end_date
        )
        results[ticker] = success
    
    # Print summary
    print(f"\n{'='*60}")
    print("Fetch Summary:")
    print(f"{'='*60}")
    for ticker, success in results.items():
        status = "✓ Success" if success else "✗ Failed"
        print(f"{ticker}: {status}")
    
    # Exit with error if any failed
    if not all(results.values()):
        sys.exit(1)
    
    print(f"\nAll tickers fetched successfully!")
    print(f"Note: Minute-level data is only available for the last 7 days.")
    print(f"Historical data beyond 7 days will use daily aggregates.")

if __name__ == "__main__":
    main()