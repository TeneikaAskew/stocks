#!/usr/bin/env python3
"""
Historical Stock Price Analysis with Technical Indicators and Trading Signals.

Ticker-agnostic — pass any of IWM/QQQ/SPY (or other tickers loaded into
``data/{ticker}/intraday/``) via ``--symbol``. Generates put/call signals
based on a 5-condition voter over price movements + indicators.
"""

import pandas as pd
import numpy as np
from datetime import datetime, time
import os
import glob
import shutil
from typing import Tuple, List, Dict
import warnings
# import json  # No longer needed - removed run-based analysis
warnings.filterwarnings('ignore')


class MarketAnalyzer:
    def __init__(self):
        self.df = None
        self.signals_df = None
        self.data_source = None  # Track whether data is from 'csv' or 'parquet'

    def _archive_file(self, file_path: str) -> None:
        """Archive existing file with timestamp to data/signals/archive/ directory

        Args:
            file_path: Path to file to archive
        """
        if os.path.exists(file_path):
            # Create archive directory
            archive_dir = 'data/signals/archive'
            os.makedirs(archive_dir, exist_ok=True)

            # Create archive filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            base_name = os.path.basename(file_path)
            name_without_ext = os.path.splitext(base_name)[0]
            ext = os.path.splitext(base_name)[1]
            archive_filename = f"{name_without_ext}_archive_{timestamp}{ext}"
            archive_path = os.path.join(archive_dir, archive_filename)

            # Move existing file to archive
            shutil.move(file_path, archive_path)
            print(f"  Archived existing file to: {archive_path}")

    def load_parquet_data(self, symbol: str = 'IWM', interval: str = '1min',
                          market_hours_only: bool = False, data_dir: str = None) -> pd.DataFrame:
        """Load data from AlphaVantage parquet files

        Args:
            symbol: Stock ticker (default: IWM)
            interval: Time interval (default: 1min)
            market_hours_only: If True, filter to 9:30 AM - 4:00 PM only
                             If False, include extended hours (4:00 AM - 8:00 PM)
                             Default is False to match CSV behavior
        """
        from pathlib import Path

        print(f"Loading AlphaVantage parquet data for {symbol}...")

        # Use provided data_dir or default path
        if data_dir:
            parquet_file = Path(f'{data_dir}/{symbol.lower()}_av_{interval}_combined.parquet')
        else:
            parquet_file = Path(f'data/{symbol.lower()}/intraday/{symbol.lower()}_av_{interval}_combined.parquet')

        if not parquet_file.exists():
            print(f"Parquet file not found: {parquet_file}")
            return None

        # Load parquet
        df = pd.read_parquet(parquet_file)
        print(f"Loaded {len(df):,} rows from parquet")

        # Transform to expected format
        df = df.reset_index()  # timestamp index -> column
        df = df.rename(columns={'timestamp': 'Time', 'Close': 'Last'})

        # Ensure Time is datetime
        df['Time'] = pd.to_datetime(df['Time'])

        # Filter to regular market hours if requested
        if market_hours_only:
            print("  Filtering to regular market hours (9:30 AM - 4:00 PM)...")
            original_len = len(df)

            df['Hour'] = df['Time'].dt.hour
            df['Minute'] = df['Time'].dt.minute

            # Regular market hours: 9:30 AM - 4:00 PM
            regular_hours = (
                ((df['Hour'] == 9) & (df['Minute'] >= 30)) |
                ((df['Hour'] >= 10) & (df['Hour'] < 16)) |
                ((df['Hour'] == 16) & (df['Minute'] == 0))
            )

            df = df[regular_hours]
            df = df.drop(['Hour', 'Minute'], axis=1)
            print(f"  Filtered: {original_len:,} -> {len(df):,} rows")
        else:
            print("  Including extended hours (4:00 AM - 8:00 PM)")

        # Sort by time
        df = df.sort_values('Time')

        # Calculate Change and %Chg columns
        df['Change'] = df['Last'].diff().fillna(0)
        df['%Chg'] = df['Last'].pct_change() * 100
        df['%Chg'] = df['%Chg'].apply(lambda x: f'{x:.2f}%' if pd.notna(x) else '0.00%')

        # Set first row values
        if len(df) > 0:
            df.iloc[0, df.columns.get_loc('Change')] = 0.0
            df.iloc[0, df.columns.get_loc('%Chg')] = '0.00%'

        # Select columns in expected order
        columns = ['Time', 'Open', 'High', 'Low', 'Last', 'Change', '%Chg', 'Volume']
        df = df[columns]

        # Remove duplicates
        df = df.drop_duplicates(subset=['Time'], keep='first')
        df = df.reset_index(drop=True)

        print(f"Parquet data loaded: {len(df):,} rows")
        print(f"Date range: {df['Time'].min()} to {df['Time'].max()}")

        # Set data source
        self.data_source = 'parquet'
        self.df = df

        return df

    def combine_csv_files(self, folder_path: str, output_path: str) -> pd.DataFrame:
        """Combine all CSV files from stock_prices folder

        Args:
            folder_path: Path to CSV files
            output_path: Path to save combined data
        """

        # Load CSV files
        print("Loading CSV files...")
        csv_files = glob.glob(os.path.join(folder_path, "*.csv"))

        dfs = []

        if len(csv_files) > 0:
            print(f"Found {len(csv_files)} CSV files")
            for file in csv_files:
                # Read CSV and filter out non-data rows
                df_temp = pd.read_csv(file)
                # Remove rows where 'Time' column contains "Downloaded from"
                df_temp = df_temp[~df_temp['Time'].str.contains("Downloaded from", na=False)]
                dfs.append(df_temp)
                print(f"  Read {file}: {len(df_temp)} rows")
        else:
            print(f"No CSV files found in {folder_path}")

        # Check if we have any data
        if len(dfs) == 0:
            raise FileNotFoundError(f"No CSV files found in {folder_path}")

        # Combine all dataframes
        print(f"\nCombining {len(dfs)} data sources...")
        df_combined = pd.concat(dfs, ignore_index=True)

        # Convert Time column to datetime
        df_combined['Time'] = pd.to_datetime(df_combined['Time'])

        # Sort by time (ascending)
        df_combined = df_combined.sort_values('Time')

        # Remove duplicates based on Time (keep first occurrence)
        original_len = len(df_combined)
        df_combined = df_combined.drop_duplicates(subset=['Time'], keep='first')
        duplicates_removed = original_len - len(df_combined)

        if duplicates_removed > 0:
            print(f"Removed {duplicates_removed:,} duplicate timestamps")

        # Reset index
        df_combined = df_combined.reset_index(drop=True)

        # Archive existing file if it exists
        self._archive_file(output_path)

        # Save combined file
        df_combined.to_csv(output_path, index=False)
        print(f"Combined data saved to {output_path}")
        print(f"Total rows: {len(df_combined):,}")
        print(f"Date range: {df_combined['Time'].min()} to {df_combined['Time'].max()}")

        # Set data source
        self.data_source = 'csv'
        self.df = df_combined
        return df_combined
    
    def calculate_true_range(self, high: pd.Series, low: pd.Series, close_prev: pd.Series) -> pd.Series:
        """Calculate True Range for ATR calculation"""
        hl = high - low
        hc = np.abs(high - close_prev)
        lc = np.abs(low - close_prev)
        return pd.concat([hl, hc, lc], axis=1).max(axis=1)
    
    def wilder_moving_average(self, values: pd.Series, period: int) -> pd.Series:
        """Calculate Wilder's Moving Average (RMA) - Vectorized version

        Wilder's smoothing formula: RMA[i] = (RMA[i-1] * (period-1) + value[i]) / period
        This is equivalent to an EWM with alpha = 1/period
        """
        # Use exponential weighted moving average with alpha = 1/period
        # adjust=False ensures we use the recursive formula like Wilder's method
        alpha = 1.0 / period
        return values.ewm(alpha=alpha, adjust=False).mean()
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range with Wilder's smoothing"""
        high = df['High']
        low = df['Low']
        close = df['Last']
        close_prev = close.shift(1)
        
        tr = self.calculate_true_range(high, low, close_prev)
        atr = self.wilder_moving_average(tr, period)
        
        return atr
    
    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI with Wilder's smoothing"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0))
        loss = (-delta.where(delta < 0, 0))
        
        avg_gain = self.wilder_moving_average(gain, period)
        avg_loss = self.wilder_moving_average(loss, period)
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_ema(self, prices: pd.Series, period: int, sma_seed: bool = False) -> pd.Series:
        """Calculate EMA using standard method (matches TradingView / AlphaVantage)"""
        # min_periods=period ensures the first value is NaN until a full window
        # of data is available, matching TradingView's EMA initialisation.
        return prices.ewm(span=period, adjust=False, min_periods=period).mean()
    
    def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Calculate VWAP (resets each session) - Vectorized version"""
        df = df.copy()
        df['Date'] = df['Time'].dt.date
        df['TypicalPrice'] = (df['High'] + df['Low'] + df['Last']) / 3
        df['TPxV'] = df['TypicalPrice'] * df['Volume']

        # Use groupby with cumsum for vectorized calculation per date
        df['CumTPxV'] = df.groupby('Date')['TPxV'].cumsum()
        df['CumVol'] = df.groupby('Date')['Volume'].cumsum()
        vwap = df['CumTPxV'] / df['CumVol']

        # Clean up temporary columns
        df.drop(['Date', 'TypicalPrice', 'TPxV', 'CumTPxV', 'CumVol'], axis=1, inplace=True)

        return vwap
    
    def calculate_rvol(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        """Calculate Relative Volume"""
        rolling_avg = df['Volume'].rolling(window=period).mean()
        rvol = df['Volume'] / rolling_avg
        return rvol
    
    def calculate_rvol_minute_of_day(self, df: pd.DataFrame, exclude_current: bool = False) -> Tuple[pd.Series, pd.Series]:
        """Calculate RVOL based on minute of day average - Vectorized version"""
        df = df.copy()
        df['MinuteOfDay'] = df['Time'].dt.hour * 60 + df['Time'].dt.minute
        df['Date'] = df['Time'].dt.date

        # Calculate average volume for each minute of day (including current session)
        minute_avg = df.groupby('MinuteOfDay')['Volume'].mean()

        # RVOL minute of day (including current session) - Vectorized using map
        df['_MinuteAvg'] = df['MinuteOfDay'].map(minute_avg)
        rvol_mod = df['Volume'] / df['_MinuteAvg']

        # RVOL minute of day (excluding current session)
        if exclude_current:
            # Calculate average volume per minute excluding current date - Vectorized
            # Group by Date and MinuteOfDay, calculate total volume and count
            grouped = df.groupby(['Date', 'MinuteOfDay'])['Volume'].agg(['sum', 'count'])

            # Calculate global totals per minute
            minute_totals = df.groupby('MinuteOfDay')['Volume'].agg(['sum', 'count'])

            # For each row, subtract current date's contribution from global average
            df['_GlobalSum'] = df['MinuteOfDay'].map(minute_totals['sum'])
            df['_GlobalCount'] = df['MinuteOfDay'].map(minute_totals['count'])
            df['_DateMinuteSum'] = df.set_index(['Date', 'MinuteOfDay']).index.map(grouped['sum'].to_dict())
            df['_DateMinuteCount'] = df.set_index(['Date', 'MinuteOfDay']).index.map(grouped['count'].to_dict())

            # Calculate average excluding current date
            df['_ExcludedAvg'] = (df['_GlobalSum'] - df['_DateMinuteSum']) / (df['_GlobalCount'] - df['_DateMinuteCount'])
            rvol_mod_excl = df['Volume'] / df['_ExcludedAvg']

            # Clean up temporary columns
            df.drop(['_MinuteAvg', '_GlobalSum', '_GlobalCount', '_DateMinuteSum', '_DateMinuteCount', '_ExcludedAvg'], axis=1, inplace=True)
        else:
            rvol_mod_excl = rvol_mod
            df.drop(['_MinuteAvg'], axis=1, inplace=True)

        return rvol_mod, rvol_mod_excl
    
    def calculate_obv(self, df: pd.DataFrame) -> pd.Series:
        """Calculate On-Balance Volume using continuous method (matches Robinhood) - Vectorized version"""
        df = df.copy()
        price_change = df['Last'].diff()

        # Vectorized OBV calculation
        # When price goes up: add volume, when down: subtract volume, when flat: add 0
        volume_direction = pd.Series(0, index=df.index)
        volume_direction[price_change > 0] = df['Volume'][price_change > 0]
        volume_direction[price_change < 0] = -df['Volume'][price_change < 0]

        # Cumulative sum gives OBV
        obv = volume_direction.cumsum()

        return obv
    
    def calculate_stoch_rsi(self, rsi: pd.Series, period: int = 14, k_period: int = 3, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
        """Calculate Stochastic RSI with Wilder smoothing"""
        # Calculate Stochastic of RSI
        rsi_min = rsi.rolling(window=period).min()
        rsi_max = rsi.rolling(window=period).max()

        # Handle division by zero
        rsi_range = rsi_max - rsi_min

        # Debug: Count how many times range is zero
        zero_range_count = (rsi_range == 0).sum()
        if zero_range_count > 0:
            print(f"        Warning: RSI range is zero in {zero_range_count} periods (RSI constant)")

        # Calculate StochRSI, will be NaN where range is 0
        # Avoid division by zero warning
        with np.errstate(divide='ignore', invalid='ignore'):
            stoch_rsi = 100 * (rsi - rsi_min) / rsi_range
            stoch_rsi = pd.Series(stoch_rsi, index=rsi.index)

        # SMA smoothing for %K and %D — matches TradingView and AlphaVantage
        stoch_rsi_k = stoch_rsi.rolling(window=k_period).mean()

        # Apply SMA smoothing for %D
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period).mean()

        return stoch_rsi_k, stoch_rsi_d

    def calculate_historical_levels(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate previous period levels (day, week, month, year) and their midpoints"""
        df = df.copy()

        # Ensure Time column is datetime
        if 'Time' not in df.columns:
            df['Time'] = df.index

        # Add date components for grouping
        df['Date'] = pd.to_datetime(df['Time']).dt.date
        df['Week'] = pd.to_datetime(df['Time']).dt.to_period('W')
        df['Month'] = pd.to_datetime(df['Time']).dt.to_period('M')
        df['Year'] = pd.to_datetime(df['Time']).dt.to_period('Y')

        # Initialize columns
        level_columns = []

        # Previous Day Levels
        print("    - Calculating previous day levels...")
        daily_groups = df.groupby('Date').agg({
            'High': 'max',
            'Low': 'min',
            'Open': 'first',
            'Last': 'last'
        })

        # Shift to get previous day values
        df['Prev_Day_High'] = df['Date'].map(daily_groups['High'].shift(1))
        df['Prev_Day_Low'] = df['Date'].map(daily_groups['Low'].shift(1))
        df['Prev_Day_Open'] = df['Date'].map(daily_groups['Open'].shift(1))
        df['Prev_Day_Close'] = df['Date'].map(daily_groups['Last'].shift(1))

        # Calculate midpoints (50% levels)
        df['Prev_Day_HL_Mid'] = (df['Prev_Day_High'] + df['Prev_Day_Low']) / 2
        df['Prev_Day_OC_Mid'] = (df['Prev_Day_Open'] + df['Prev_Day_Close']) / 2

        level_columns.extend(['Prev_Day_High', 'Prev_Day_Low', 'Prev_Day_Open', 'Prev_Day_Close',
                             'Prev_Day_HL_Mid', 'Prev_Day_OC_Mid'])

        # Previous Week Levels
        print("    - Calculating previous week levels...")
        weekly_groups = df.groupby('Week').agg({
            'High': 'max',
            'Low': 'min',
            'Open': 'first',
            'Last': 'last'
        })

        df['Prev_Week_High'] = df['Week'].map(weekly_groups['High'].shift(1))
        df['Prev_Week_Low'] = df['Week'].map(weekly_groups['Low'].shift(1))
        df['Prev_Week_Open'] = df['Week'].map(weekly_groups['Open'].shift(1))
        df['Prev_Week_Close'] = df['Week'].map(weekly_groups['Last'].shift(1))

        df['Prev_Week_HL_Mid'] = (df['Prev_Week_High'] + df['Prev_Week_Low']) / 2
        df['Prev_Week_OC_Mid'] = (df['Prev_Week_Open'] + df['Prev_Week_Close']) / 2

        level_columns.extend(['Prev_Week_High', 'Prev_Week_Low', 'Prev_Week_Open', 'Prev_Week_Close',
                             'Prev_Week_HL_Mid', 'Prev_Week_OC_Mid'])

        # Previous Month Levels
        print("    - Calculating previous month levels...")
        monthly_groups = df.groupby('Month').agg({
            'High': 'max',
            'Low': 'min',
            'Open': 'first',
            'Last': 'last'
        })

        df['Prev_Month_High'] = df['Month'].map(monthly_groups['High'].shift(1))
        df['Prev_Month_Low'] = df['Month'].map(monthly_groups['Low'].shift(1))
        df['Prev_Month_Open'] = df['Month'].map(monthly_groups['Open'].shift(1))
        df['Prev_Month_Close'] = df['Month'].map(monthly_groups['Last'].shift(1))

        df['Prev_Month_HL_Mid'] = (df['Prev_Month_High'] + df['Prev_Month_Low']) / 2
        df['Prev_Month_OC_Mid'] = (df['Prev_Month_Open'] + df['Prev_Month_Close']) / 2

        level_columns.extend(['Prev_Month_High', 'Prev_Month_Low', 'Prev_Month_Open', 'Prev_Month_Close',
                             'Prev_Month_HL_Mid', 'Prev_Month_OC_Mid'])

        # Previous Year Levels
        print("    - Calculating previous year levels...")
        yearly_groups = df.groupby('Year').agg({
            'High': 'max',
            'Low': 'min',
            'Open': 'first',
            'Last': 'last'
        })

        df['Prev_Year_High'] = df['Year'].map(yearly_groups['High'].shift(1))
        df['Prev_Year_Low'] = df['Year'].map(yearly_groups['Low'].shift(1))
        df['Prev_Year_Open'] = df['Year'].map(yearly_groups['Open'].shift(1))
        df['Prev_Year_Close'] = df['Year'].map(yearly_groups['Last'].shift(1))

        df['Prev_Year_HL_Mid'] = (df['Prev_Year_High'] + df['Prev_Year_Low']) / 2
        df['Prev_Year_OC_Mid'] = (df['Prev_Year_Open'] + df['Prev_Year_Close']) / 2

        level_columns.extend(['Prev_Year_High', 'Prev_Year_Low', 'Prev_Year_Open', 'Prev_Year_Close',
                             'Prev_Year_HL_Mid', 'Prev_Year_OC_Mid'])

        # Calculate price position relative to levels (as percentage) - Vectorized
        print("    - Calculating price position relative to levels...")
        current_price = df['Last']

        # Vectorized percentage calculation for all level columns at once
        for level_col in level_columns:
            if level_col in df.columns:
                pct_col = f'{level_col}_Pct'
                df[pct_col] = ((current_price - df[level_col]) / df[level_col] * 100)

        # Calculate if price is at/near key levels (within 0.1% tolerance) - Vectorized
        tolerance = 0.1  # 0.1% threshold

        for level_col in level_columns:
            if level_col in df.columns:
                pct_col = f'{level_col}_Pct'
                if pct_col in df.columns:
                    at_level_col = f'At_{level_col}'
                    df[at_level_col] = (abs(df[pct_col]) <= tolerance).astype(int)

        # Calculate breakout/breakdown flags
        print("    - Calculating breakout/breakdown indicators...")

        # Day breakouts
        df['Broke_Prev_Day_High'] = (df['Last'] > df['Prev_Day_High']).astype(int)
        df['Broke_Prev_Day_Low'] = (df['Last'] < df['Prev_Day_Low']).astype(int)

        # Week breakouts
        df['Broke_Prev_Week_High'] = (df['Last'] > df['Prev_Week_High']).astype(int)
        df['Broke_Prev_Week_Low'] = (df['Last'] < df['Prev_Week_Low']).astype(int)

        # Month breakouts
        df['Broke_Prev_Month_High'] = (df['Last'] > df['Prev_Month_High']).astype(int)
        df['Broke_Prev_Month_Low'] = (df['Last'] < df['Prev_Month_Low']).astype(int)

        # Year breakouts
        df['Broke_Prev_Year_High'] = (df['Last'] > df['Prev_Year_High']).astype(int)
        df['Broke_Prev_Year_Low'] = (df['Last'] < df['Prev_Year_Low']).astype(int)

        # Remove temporary grouping columns
        df = df.drop(['Date', 'Week', 'Month', 'Year'], axis=1)

        return df

    def calculate_order_blocks_and_orb(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Order Blocks and Opening Range Breakout (ORB) levels"""
        df = df.copy()

        # Ensure Time column exists
        if 'Time' not in df.columns:
            df['Time'] = df.index

        # Convert to datetime and extract time components
        df['DateTime'] = pd.to_datetime(df['Time'])
        df['Date'] = df['DateTime'].dt.date
        df['TimeOnly'] = df['DateTime'].dt.time

        # Market open time (9:30 AM)
        market_open = time(9, 30)

        # Initialize ORB columns
        print("    - Calculating 5-minute ORB...")
        df = self._calculate_orb(df, market_open, minutes=5, label='5m')

        print("    - Calculating 15-minute ORB...")
        df = self._calculate_orb(df, market_open, minutes=15, label='15m')

        print("    - Calculating 30-minute ORB...")
        df = self._calculate_orb(df, market_open, minutes=30, label='30m')

        # Calculate Order Blocks
        print("    - Calculating Order Blocks...")
        df = self._calculate_order_blocks(df)

        # Clean up temporary columns
        df = df.drop(['DateTime', 'Date', 'TimeOnly'], axis=1, errors='ignore')

        return df

    def _calculate_orb(self, df: pd.DataFrame, market_open: time, minutes: int, label: str) -> pd.DataFrame:
        """Calculate Opening Range Breakout for specified time period - Vectorized version"""
        from datetime import datetime, timedelta

        # Calculate the ORB end time
        orb_end_time = (datetime.combine(datetime.today(), market_open) +
                       timedelta(minutes=minutes)).time()

        # Identify rows within ORB period
        in_orb_period = (df['TimeOnly'] >= market_open) & (df['TimeOnly'] <= orb_end_time)

        # Calculate ORB high/low for each date using groupby - VECTORIZED
        orb_highs = df[in_orb_period].groupby('Date')['High'].max()
        orb_lows = df[in_orb_period].groupby('Date')['Low'].min()

        # Map ORB levels back to all rows of each date
        df[f'ORB_{label}_High'] = df['Date'].map(orb_highs)
        df[f'ORB_{label}_Low'] = df['Date'].map(orb_lows)
        df[f'ORB_{label}_Range'] = df[f'ORB_{label}_High'] - df[f'ORB_{label}_Low']
        df[f'ORB_{label}_Mid'] = (df[f'ORB_{label}_High'] + df[f'ORB_{label}_Low']) / 2

        # Calculate price position relative to ORB - VECTORIZED
        df[f'ORB_{label}_High_Pct'] = ((df['Last'] - df[f'ORB_{label}_High']) / df[f'ORB_{label}_High'] * 100)
        df[f'ORB_{label}_Low_Pct'] = ((df['Last'] - df[f'ORB_{label}_Low']) / df[f'ORB_{label}_Low'] * 100)
        df[f'ORB_{label}_Mid_Pct'] = ((df['Last'] - df[f'ORB_{label}_Mid']) / df[f'ORB_{label}_Mid'] * 100)

        # Initialize trend indicators (default 0)
        df[f'ORB_{label}_Broke_High'] = 0
        df[f'ORB_{label}_Broke_Low'] = 0
        df[f'ORB_{label}_Within_Range'] = 0
        df[f'ORB_{label}_Trend'] = 0
        df[f'ORB_{label}_Distance'] = 0.0

        # Only calculate for periods after ORB is established - VECTORIZED
        post_orb = df['TimeOnly'] > orb_end_time

        # Breakout above ORB high
        df.loc[post_orb, f'ORB_{label}_Broke_High'] = (
            df.loc[post_orb, 'Last'] > df.loc[post_orb, f'ORB_{label}_High']
        ).astype(int)

        # Breakdown below ORB low
        df.loc[post_orb, f'ORB_{label}_Broke_Low'] = (
            df.loc[post_orb, 'Last'] < df.loc[post_orb, f'ORB_{label}_Low']
        ).astype(int)

        # Within ORB range (sideways/neutral)
        df.loc[post_orb, f'ORB_{label}_Within_Range'] = (
            (df.loc[post_orb, 'Last'] >= df.loc[post_orb, f'ORB_{label}_Low']) &
            (df.loc[post_orb, 'Last'] <= df.loc[post_orb, f'ORB_{label}_High'])
        ).astype(int)

        # Trend direction: 1 = bullish (above), -1 = bearish (below), 0 = neutral (within)
        df.loc[post_orb & (df['Last'] > df[f'ORB_{label}_High']), f'ORB_{label}_Trend'] = 1
        df.loc[post_orb & (df['Last'] < df[f'ORB_{label}_Low']), f'ORB_{label}_Trend'] = -1

        # Distance from ORB range (0 if within range) - VECTORIZED
        above = post_orb & (df['Last'] > df[f'ORB_{label}_High'])
        below = post_orb & (df['Last'] < df[f'ORB_{label}_Low'])
        df.loc[above, f'ORB_{label}_Distance'] = df.loc[above, 'Last'] - df.loc[above, f'ORB_{label}_High']
        df.loc[below, f'ORB_{label}_Distance'] = df.loc[below, 'Last'] - df.loc[below, f'ORB_{label}_Low']

        return df

    def _calculate_order_blocks(self, df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
        """
        Calculate Order Blocks - consolidation zones that may act as support/resistance.
        An order block is identified by:
        1. A zone of price consolidation (low volatility)
        2. Followed by a significant move (breakout)

        Adjusted for 1-minute data with more lenient thresholds.
        """
        # Calculate rolling volatility (using ATR if available, otherwise range)
        if 'ATR14_W' in df.columns:
            volatility = df['ATR14_W']
        else:
            volatility = df['High'] - df['Low']

        # Rolling average volatility
        avg_volatility = volatility.rolling(window=lookback, min_periods=1).mean()

        # Low volatility threshold - adjusted for 1-minute data
        # Use 60% of average (was 30%) to capture more consolidation zones
        low_vol_threshold = avg_volatility * 0.6

        # Identify consolidation zones (low volatility)
        df['Order_Block_Zone'] = (volatility < low_vol_threshold).astype(int)

        # Calculate price range during consolidation
        # For each consolidation zone, track the high and low
        df['Order_Block_High'] = np.nan
        df['Order_Block_Low'] = np.nan
        df['Order_Block_Mid'] = np.nan

        # For 1-minute data, use 5-bar window instead of 3-bar
        # This gives a 5-minute consolidation zone which is more realistic
        consolidation_window = 5
        consolidation_count = df['Order_Block_Zone'].rolling(window=consolidation_window, min_periods=consolidation_window).sum()
        # Need at least 3 of 5 bars consolidating (60%)
        is_order_block = consolidation_count >= 3

        # Calculate rolling max/min for consolidation windows (5 bars = 5 minutes)
        df['Order_Block_High'] = df['High'].rolling(window=consolidation_window, min_periods=consolidation_window).max()
        df['Order_Block_Low'] = df['Low'].rolling(window=consolidation_window, min_periods=consolidation_window).min()

        # Only keep order blocks where consolidation condition is met
        df.loc[~is_order_block, 'Order_Block_High'] = np.nan
        df.loc[~is_order_block, 'Order_Block_Low'] = np.nan

        # Calculate mid point
        df['Order_Block_Mid'] = (df['Order_Block_High'] + df['Order_Block_Low']) / 2

        # Forward fill order blocks for next 30 bars (30 minutes)
        # Order blocks remain relevant for longer on 1-minute data
        df['Order_Block_High'] = df['Order_Block_High'].fillna(method='ffill', limit=30)
        df['Order_Block_Low'] = df['Order_Block_Low'].fillna(method='ffill', limit=30)
        df['Order_Block_Mid'] = df['Order_Block_Mid'].fillna(method='ffill', limit=30)

        # Price position relative to order block
        df['Order_Block_Position'] = 0  # 0 = within, 1 = above, -1 = below
        df.loc[df['Last'] > df['Order_Block_High'], 'Order_Block_Position'] = 1
        df.loc[df['Last'] < df['Order_Block_Low'], 'Order_Block_Position'] = -1

        # Distance from order block
        df['Order_Block_Distance'] = 0.0
        above_ob = df['Last'] > df['Order_Block_High']
        below_ob = df['Last'] < df['Order_Block_Low']
        df.loc[above_ob, 'Order_Block_Distance'] = df.loc[above_ob, 'Last'] - df.loc[above_ob, 'Order_Block_High']
        df.loc[below_ob, 'Order_Block_Distance'] = df.loc[below_ob, 'Last'] - df.loc[below_ob, 'Order_Block_Low']

        # Test of order block (price touching the zone)
        tolerance = 0.001  # 0.1% tolerance
        at_ob_high = abs((df['Last'] - df['Order_Block_High']) / df['Order_Block_High']) <= tolerance
        at_ob_low = abs((df['Last'] - df['Order_Block_Low']) / df['Order_Block_Low']) <= tolerance
        df['Order_Block_Test'] = (at_ob_high | at_ob_low).astype(int)

        return df

    def add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add all technical indicators to the dataframe"""
        print("\nCalculating technical indicators...")
        print("-" * 50)

        # ATR with Wilder
        print("1/11 - Calculating ATR (Average True Range)...")
        df['ATR14_W'] = self.calculate_atr(df, 14)

        # RSI with Wilder
        print("2/11 - Calculating RSI (Relative Strength Index)...")
        df['RSI14_W'] = self.calculate_rsi(df['Last'], 14)
        # Phase 0.7.x — signed 3-bar RSI delta for the directional
        # `rsi_thrust` momentum gate (mirrors `add_all_indicators`).
        df['RSI_Thrust_3'] = df['RSI14_W'] - df['RSI14_W'].shift(3)

        # EMAs with SMA seeding
        print("3/11 - Calculating EMAs (Exponential Moving Averages)...")
        print("    - EMA 9...")
        df['EMA9'] = self.calculate_ema(df['Last'], 9)
        print("    - EMA 20...")
        df['EMA20'] = self.calculate_ema(df['Last'], 20)
        print("    - EMA 50...")
        df['EMA50'] = self.calculate_ema(df['Last'], 50)

        # VWAP
        print("4/11 - Calculating VWAP (Volume Weighted Average Price)...")
        df['VWAP'] = self.calculate_vwap(df)

        # RVOL
        print("5/11 - Calculating RVOL (Relative Volume)...")
        print("    - RVOL 20-period...")
        df['RVOL20'] = self.calculate_rvol(df, 20)
        print("    - RVOL minute of day...")
        df['RVOL_MOD'], df['RVOL_MOD_EXCL'] = self.calculate_rvol_minute_of_day(df, exclude_current=True)
        # Phase 0.7.x — `rvol_above_recent` confirmer column. Median-based
        # rolling RVOL (robust to outlier spikes), read by the new
        # momentum condition. Mirrors `lib.indicators.calculate_rvol_recent`
        # so the legacy MarketAnalyzer path stays in sync with the canonical
        # add_all_indicators output. Without this, the rvol confirmer never
        # fires on this code path (Codex P2 review on PR #262).
        _rvol_med = df['Volume'].rolling(window=20, min_periods=1).median()
        df['RVol_Recent_20'] = df['Volume'] / _rvol_med.where(_rvol_med > 0, np.nan)
        # Phase 0.7.x — `atr_expansion` confirmer column. Short-ATR / long-ATR
        # ratio. Mirrors `lib.indicators.calculate_atr_expansion`.
        _atr_short = self.calculate_atr(df, 5)
        _atr_long  = self.calculate_atr(df, 20)
        df['ATR_Expansion'] = _atr_short / _atr_long.where(_atr_long > 0, np.nan)

        # OBV
        print("6/11 - Calculating OBV (On-Balance Volume)...")
        df['OBV'] = self.calculate_obv(df)

        # Stochastic RSI
        print("7/11 - Calculating Stochastic RSI...")
        # Debug RSI values first
        rsi_stats = df['RSI14_W'].describe()
        print(f"    - RSI stats: min={rsi_stats['min']:.2f}, max={rsi_stats['max']:.2f}, mean={rsi_stats['50%']:.2f}")
        print(f"    - RSI valid values: {df['RSI14_W'].count()} out of {len(df)} total rows")
        
        df['StochRSI_K'], df['StochRSI_D'] = self.calculate_stoch_rsi(df['RSI14_W'])
        print(f"    - StochRSI K: {df['StochRSI_K'].count()} valid values, mean={df['StochRSI_K'].mean():.2f}")
        print(f"    - StochRSI D: {df['StochRSI_D'].count()} valid values, mean={df['StochRSI_D'].mean():.2f}")

        # Historical levels
        print("8/11 - Calculating Historical Levels (Day, Week, Month, Year)...")
        df = self.calculate_historical_levels(df)

        # Order Blocks and ORB
        print("9/11 - Calculating Order Blocks and ORB (5m, 15m, 30m)...")
        df = self.calculate_order_blocks_and_orb(df)

        print("10/11 - Validating indicators...")
        # Validate all indicators were calculated
        indicators = ['ATR14_W', 'RSI14_W', 'EMA9', 'EMA20', 'EMA50', 'VWAP',
                     'RVOL20', 'RVOL_MOD', 'RVOL_MOD_EXCL', 'OBV', 'StochRSI_K', 'StochRSI_D']
        for indicator in indicators:
            valid_count = df[indicator].count()
            if valid_count == 0:
                print(f"    ⚠️  WARNING: {indicator} has no valid values!")
            else:
                print(f"    OK {indicator}: {valid_count} valid values")

        # Validate historical levels
        level_indicators = ['Prev_Day_High', 'Prev_Week_High', 'Prev_Month_High', 'Prev_Year_High']
        print(f"\n    Historical Levels:")
        for level in level_indicators:
            if level in df.columns:
                valid_count = df[level].count()
                print(f"    {level}: {valid_count} valid values")

        # Validate ORB and Order Blocks
        orb_indicators = ['ORB_5m_High', 'ORB_15m_High', 'ORB_30m_High', 'Order_Block_High']
        print(f"\n    ORB & Order Blocks:")
        for orb in orb_indicators:
            if orb in df.columns:
                valid_count = df[orb].count()
                print(f"    {orb}: {valid_count} valid values")

        print("11/11 - Technical indicators, levels, and ORB calculated successfully!")
        print("-" * 50)
        return df
    
    def generate_technical_signals(self, df: pd.DataFrame, consecutive_periods: int = 3) -> pd.DataFrame:
        """Generate trading signals based on technical indicators and consecutive price movements"""
        print("\nGenerating technical indicator-based signals...")
        print("-" * 50)
        
        # Calculate price movement trends
        df = df.copy()
        df['Price_Change'] = df['Last'].pct_change() * 100
        df['Price_MA3'] = df['Price_Change'].rolling(3).mean()
        
        # Consecutive movement detection
        df['Up_Move'] = df['Price_Change'] > 0
        df['Down_Move'] = df['Price_Change'] < 0
        
        # Count consecutive movements
        df['Consecutive_Up'] = df['Up_Move'].rolling(consecutive_periods).sum()
        df['Consecutive_Down'] = df['Down_Move'].rolling(consecutive_periods).sum()
        # Phase 0.7.2: relaxed 3-of-5 windows for the momentum gate.
        df['Consecutive_Up_5'] = df['Up_Move'].rolling(5).sum()
        df['Consecutive_Down_5'] = df['Down_Move'].rolling(5).sum()
        
        signals = []
        total_rows = len(df)
        processed = 0
        
        # Signal conditions
        for idx in range(consecutive_periods, min(len(df)-20, len(df))):  # Need lookahead
            processed += 1
            if processed % 5000 == 0:
                print(f"  Progress: {processed}/{min(total_rows-consecutive_periods, total_rows-20)} rows processed")
                
            current = df.iloc[idx]
            
            # Skip if missing indicator data
            if pd.isna(current.get('RSI14_W')) or pd.isna(current.get('StochRSI_K')):
                continue
            
            signal = None
            signal_strength = 0
            
            # CALL Signal Conditions — Phase 0.7.x:
            #   - dropped `stoch_rsi_not_overbought` (free score, fired ~72%)
            #   - relaxed `consecutive_up` from 3-of-3 to 3-of-5
            #   - added `rvol_above_recent` (volume confirmation)
            #   - added `atr_expansion` (volatility regime gate)
            #   - added `rsi_thrust` (directional RSI velocity)
            rvol_recent = current.get('RVol_Recent_20')
            rvol_recent_fires = (
                rvol_recent is not None
                and not pd.isna(rvol_recent)
                and rvol_recent > 1.2
            )
            atr_exp = current.get('ATR_Expansion')
            atr_expansion_fires = (
                atr_exp is not None
                and not pd.isna(atr_exp)
                and atr_exp > 1.15
            )
            rsi_thrust = current.get('RSI_Thrust_3')
            rsi_thrust_valid = rsi_thrust is not None and not pd.isna(rsi_thrust)

            # Phase 0.7.x: track CORE-tier counts in parallel so the
            # tier gate can require a credible setup floor (CORE >= 2)
            # before CONFIRMING conditions can pile on. CORE = defines
            # the setup (consec, RSI band, above/below VWAP, above/below
            # EMA9). CONFIRMING = rvol, atr_expansion, rsi_thrust.
            call_conditions = 0
            call_core = 0
            if current.get('Consecutive_Up', 0) >= 3:  # 3-of-3 strict up bars
                call_conditions += 1
                call_core += 1
            if current['RSI14_W'] < 50 and current['RSI14_W'] > 25:  # RSI in bullish range
                call_conditions += 1
                call_core += 1
            if current['Last'] > current.get('VWAP', current['Last']):  # Price above VWAP
                call_conditions += 1
                call_core += 1
            if current['Last'] > current.get('EMA9', current['Last']):  # Price above EMA9
                call_conditions += 1
                call_core += 1
            if rvol_recent_fires:  # current vol > 1.2x rolling-20 median
                call_conditions += 1
            if atr_expansion_fires:  # ATR(5) > 1.15x ATR(20) — vol expanding
                call_conditions += 1
            if rsi_thrust_valid and rsi_thrust > 5.0:  # RSI accelerating up
                call_conditions += 1

            # PUT Signal Conditions — Phase 0.7.x mirror.
            put_conditions = 0
            put_core = 0
            if current.get('Consecutive_Down', 0) >= 3:  # 3-of-3 strict down bars
                put_conditions += 1
                put_core += 1
            if current['RSI14_W'] > 50 and current['RSI14_W'] < 75:  # RSI in bearish range
                put_conditions += 1
                put_core += 1
            if current['Last'] < current.get('VWAP', current['Last']):  # Price below VWAP
                put_conditions += 1
                put_core += 1
            if current['Last'] < current.get('EMA9', current['Last']):  # Price below EMA9
                put_conditions += 1
                put_core += 1
            if rvol_recent_fires:  # direction-agnostic volume confirmation
                put_conditions += 1
            if atr_expansion_fires:  # direction-agnostic vol regime gate
                put_conditions += 1
            if rsi_thrust_valid and rsi_thrust < -5.0:  # RSI accelerating down
                put_conditions += 1

            # Generate signal if enough conditions are met. A gate-blocked
            # direction can't suppress the eligible direction — see
            # MomentumStrategy.evaluate for the parallel logic.
            min_conditions = 5  # B+: raised from 3, only score>=5 clears costs
            min_core_conditions = 2

            call_eligible = (call_conditions >= min_conditions
                             and call_core >= min_core_conditions)
            put_eligible  = (put_conditions  >= min_conditions
                             and put_core   >= min_core_conditions)

            if call_eligible and put_eligible:
                if call_conditions > put_conditions:
                    signal = 'call'
                    signal_strength = call_conditions
                elif put_conditions > call_conditions:
                    signal = 'put'
                    signal_strength = put_conditions
            elif call_eligible:
                signal = 'call'
                signal_strength = call_conditions
            elif put_eligible:
                signal = 'put'
                signal_strength = put_conditions
            
            if signal:
                # Calculate returns over multiple time windows
                time_windows = [5, 10, 15, 20, 30, 45, 60]  # minutes
                returns_by_window = {}
                best_return = 0
                best_window = 0

                for window in time_windows:
                    lookahead = min(window, len(df) - idx - 1)
                    if lookahead > 0:
                        future_prices = df.iloc[idx+1:idx+1+lookahead]['Last'].values

                        if len(future_prices) > 0:
                            if signal == 'call':
                                max_price = np.max(future_prices)
                                window_return = (max_price - current['Last']) / current['Last'] * 100
                            else:  # put
                                min_price = np.min(future_prices)
                                window_return = (current['Last'] - min_price) / current['Last'] * 100

                            returns_by_window[f'return_{window}min'] = window_return

                            # Track best return across all windows
                            if window_return > best_return:
                                best_return = window_return
                                best_window = window

                # Use 20-minute window as default for backward compatibility
                lookahead = min(20, len(df) - idx - 1)
                if lookahead > 0:
                    future_prices = df.iloc[idx+1:idx+1+lookahead]['Last'].values

                    if len(future_prices) > 0:
                        if signal == 'call':
                            max_price = np.max(future_prices)
                            exit_idx = np.argmax(future_prices) + 1
                            return_pct = (max_price - current['Last']) / current['Last'] * 100
                        else:  # put
                            min_price = np.min(future_prices)
                            exit_idx = np.argmin(future_prices) + 1
                            return_pct = (current['Last'] - min_price) / current['Last'] * 100

                        signal_data = {
                            'entry_time': current['Time'],
                            'trade_type': signal,
                            'entry_price': current['Last'],
                            'entry_volume': current['Volume'],
                            'duration_minutes': exit_idx,
                            'return_pct': return_pct,
                            'best_return': best_return,
                            'best_window_minutes': best_window,
                            'signal_strength': signal_strength,
                            'conditions_met': f"{signal_strength}/5",
                            'entry_rsi': current['RSI14_W'],
                            'entry_vwap': current.get('VWAP', np.nan),
                            'entry_ema9': current.get('EMA9', np.nan),
                            'entry_ema20': current.get('EMA20', np.nan),
                            'entry_stochrsi_k': current.get('StochRSI_K', np.nan),
                            'entry_atr': current.get('ATR14_W', np.nan),
                            'entry_obv': current.get('OBV', np.nan),

                            # Historical Levels at Entry
                            'entry_prev_day_high': current.get('Prev_Day_High', np.nan),
                            'entry_prev_day_low': current.get('Prev_Day_Low', np.nan),
                            'entry_prev_day_hl_mid': current.get('Prev_Day_HL_Mid', np.nan),
                            'entry_prev_week_high': current.get('Prev_Week_High', np.nan),
                            'entry_prev_week_low': current.get('Prev_Week_Low', np.nan),
                            'entry_prev_week_hl_mid': current.get('Prev_Week_HL_Mid', np.nan),
                            'entry_prev_month_high': current.get('Prev_Month_High', np.nan),
                            'entry_prev_month_low': current.get('Prev_Month_Low', np.nan),
                            'entry_prev_month_hl_mid': current.get('Prev_Month_HL_Mid', np.nan),

                            # Price position relative to levels
                            'entry_vs_prev_day_high_pct': current.get('Prev_Day_High_Pct', np.nan),
                            'entry_vs_prev_day_low_pct': current.get('Prev_Day_Low_Pct', np.nan),
                            'entry_vs_prev_week_high_pct': current.get('Prev_Week_High_Pct', np.nan),
                            'entry_vs_prev_week_low_pct': current.get('Prev_Week_Low_Pct', np.nan),
                            'entry_vs_prev_month_high_pct': current.get('Prev_Month_High_Pct', np.nan),
                            'entry_vs_prev_month_low_pct': current.get('Prev_Month_Low_Pct', np.nan),

                            # Breakout flags
                            'entry_broke_prev_day_high': current.get('Broke_Prev_Day_High', 0),
                            'entry_broke_prev_day_low': current.get('Broke_Prev_Day_Low', 0),
                            'entry_broke_prev_week_high': current.get('Broke_Prev_Week_High', 0),
                            'entry_broke_prev_week_low': current.get('Broke_Prev_Week_Low', 0),
                            'entry_broke_prev_month_high': current.get('Broke_Prev_Month_High', 0),
                            'entry_broke_prev_month_low': current.get('Broke_Prev_Month_Low', 0),

                            # At level flags (within 0.1% of key levels)
                            'entry_at_prev_day_high': current.get('At_Prev_Day_High', 0),
                            'entry_at_prev_day_low': current.get('At_Prev_Day_Low', 0),
                            'entry_at_prev_day_hl_mid': current.get('At_Prev_Day_HL_Mid', 0),
                            'entry_at_prev_week_high': current.get('At_Prev_Week_High', 0),
                            'entry_at_prev_week_low': current.get('At_Prev_Week_Low', 0),
                            'entry_at_prev_week_hl_mid': current.get('At_Prev_Week_HL_Mid', 0),

                            # ORB (Opening Range Breakout) data
                            'entry_orb_5m_high': current.get('ORB_5m_High', np.nan),
                            'entry_orb_5m_low': current.get('ORB_5m_Low', np.nan),
                            'entry_orb_5m_mid': current.get('ORB_5m_Mid', np.nan),
                            'entry_orb_5m_trend': current.get('ORB_5m_Trend', 0),
                            'entry_orb_5m_broke_high': current.get('ORB_5m_Broke_High', 0),
                            'entry_orb_5m_broke_low': current.get('ORB_5m_Broke_Low', 0),
                            'entry_orb_5m_within_range': current.get('ORB_5m_Within_Range', 0),

                            'entry_orb_15m_high': current.get('ORB_15m_High', np.nan),
                            'entry_orb_15m_low': current.get('ORB_15m_Low', np.nan),
                            'entry_orb_15m_mid': current.get('ORB_15m_Mid', np.nan),
                            'entry_orb_15m_trend': current.get('ORB_15m_Trend', 0),
                            'entry_orb_15m_broke_high': current.get('ORB_15m_Broke_High', 0),
                            'entry_orb_15m_broke_low': current.get('ORB_15m_Broke_Low', 0),
                            'entry_orb_15m_within_range': current.get('ORB_15m_Within_Range', 0),

                            'entry_orb_30m_high': current.get('ORB_30m_High', np.nan),
                            'entry_orb_30m_low': current.get('ORB_30m_Low', np.nan),
                            'entry_orb_30m_mid': current.get('ORB_30m_Mid', np.nan),
                            'entry_orb_30m_trend': current.get('ORB_30m_Trend', 0),
                            'entry_orb_30m_broke_high': current.get('ORB_30m_Broke_High', 0),
                            'entry_orb_30m_broke_low': current.get('ORB_30m_Broke_Low', 0),
                            'entry_orb_30m_within_range': current.get('ORB_30m_Within_Range', 0),

                            # Order Block data
                            'entry_order_block_high': current.get('Order_Block_High', np.nan),
                            'entry_order_block_low': current.get('Order_Block_Low', np.nan),
                            'entry_order_block_mid': current.get('Order_Block_Mid', np.nan),
                            'entry_order_block_position': current.get('Order_Block_Position', 0),
                            'entry_order_block_test': current.get('Order_Block_Test', 0),
                            'entry_order_block_distance': current.get('Order_Block_Distance', 0.0),

                            'exit_time': df.iloc[idx + exit_idx]['Time'],
                            'exit_price': max_price if signal == 'call' else min_price,
                            'exit_rsi': df.iloc[idx + exit_idx]['RSI14_W'],
                            'exit_vwap': df.iloc[idx + exit_idx].get('VWAP', np.nan),
                            'exit_obv': df.iloc[idx + exit_idx].get('OBV', np.nan)
                        }

                        # Add all window returns to signal_data
                        signal_data.update(returns_by_window)
                        
                        signals.append(signal_data)
        
        print(f"  Progress: 100% - Signal generation complete!")
        
        signals_df = pd.DataFrame(signals)
        if len(signals_df) == 0:
            # Return empty dataframe with expected columns
            return pd.DataFrame(columns=['entry_time', 'trade_type', 'entry_price', 'return_pct'])

        return signals_df

    def analyze_feature_importance(self, signals_df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
        """Analyze feature importance using correlation and RandomForest

        Args:
            signals_df: DataFrame with trading signals and features
            top_n: Number of top features to return (default: 20)

        Returns:
            DataFrame with feature importance rankings
        """
        print("\nAnalyzing feature importance...")
        print("-" * 50)

        if len(signals_df) == 0:
            print("  WARNING: No signals to analyze!")
            return pd.DataFrame()

        # Import required libraries
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.preprocessing import StandardScaler

        # Define target variable (profitability)
        target_col = 'return_pct'
        if target_col not in signals_df.columns:
            print(f"  ERROR: Target column '{target_col}' not found!")
            return pd.DataFrame()

        # Identify feature columns (exclude metadata and target)
        exclude_cols = [
            'entry_time', 'exit_time', 'trade_type', 'entry_price', 'exit_price',
            'return_pct', 'best_return', 'best_window_minutes', 'duration_minutes',
            'signal_strength', 'conditions_met'
        ]

        # Also exclude individual window returns (they're derivatives of the target)
        exclude_cols.extend([col for col in signals_df.columns if col.startswith('return_') and 'min' in col])

        # Get all numeric feature columns
        feature_cols = [col for col in signals_df.columns
                       if col not in exclude_cols
                       and signals_df[col].dtype in ['int64', 'float64', 'int32', 'float32']]

        print(f"  Analyzing {len(feature_cols)} features from {len(signals_df)} signals...")

        # Remove features with too many NaN values (>50%)
        valid_features = []
        for col in feature_cols:
            nan_pct = signals_df[col].isna().sum() / len(signals_df) * 100
            if nan_pct < 50:
                valid_features.append(col)
            else:
                print(f"    Skipping {col}: {nan_pct:.1f}% NaN values")

        if len(valid_features) == 0:
            print("  ERROR: No valid features found!")
            return pd.DataFrame()

        print(f"  Using {len(valid_features)} valid features...")

        # Prepare data - fill remaining NaN with median
        X = signals_df[valid_features].copy()
        y = signals_df[target_col].copy()

        # Fill NaN values with median for each column
        for col in X.columns:
            if X[col].isna().any():
                X[col] = X[col].fillna(X[col].median())

        # Remove any rows where target is NaN
        valid_rows = ~y.isna()
        X = X[valid_rows]
        y = y[valid_rows]

        if len(X) == 0:
            print("  ERROR: No valid rows after cleaning!")
            return pd.DataFrame()

        print(f"  Final dataset: {len(X)} samples x {len(valid_features)} features")

        # 1. Calculate Correlation with Target
        print("\n  Step 1/3: Calculating correlations...")
        correlations = {}
        for col in valid_features:
            corr = X[col].corr(y)
            correlations[col] = abs(corr)  # Use absolute correlation

        # 2. Calculate RandomForest Feature Importance
        print("  Step 2/3: Training RandomForest model...")

        # Scale features for better RF performance
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Train RandomForest (use fewer trees for speed)
        rf = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1  # Use all CPU cores
        )

        rf.fit(X_scaled, y)

        # Get feature importances
        rf_importances = dict(zip(valid_features, rf.feature_importances_))

        # 3. Combine scores (weighted average: 40% correlation, 60% RF importance)
        print("  Step 3/3: Combining scores...")
        combined_scores = {}

        # Normalize scores to 0-1 range
        max_corr = max(correlations.values()) if correlations else 1
        max_rf = max(rf_importances.values()) if rf_importances else 1

        for feature in valid_features:
            norm_corr = correlations.get(feature, 0) / max_corr
            norm_rf = rf_importances.get(feature, 0) / max_rf

            # Weighted combination
            combined_scores[feature] = (0.4 * norm_corr) + (0.6 * norm_rf)

        # Create results dataframe
        results = pd.DataFrame({
            'feature': valid_features,
            'correlation': [correlations.get(f, 0) for f in valid_features],
            'rf_importance': [rf_importances.get(f, 0) for f in valid_features],
            'combined_score': [combined_scores.get(f, 0) for f in valid_features]
        })

        # Sort by combined score
        results = results.sort_values('combined_score', ascending=False)
        results['rank'] = range(1, len(results) + 1)

        # Add feature stats (mean, std)
        results['feature_mean'] = [X[f].mean() for f in results['feature']]
        results['feature_std'] = [X[f].std() for f in results['feature']]

        # Reorder columns
        results = results[['rank', 'feature', 'combined_score', 'correlation',
                          'rf_importance', 'feature_mean', 'feature_std']]

        # Print top features
        print("\n" + "="*80)
        print(f"TOP {min(top_n, len(results))} MOST IMPORTANT FEATURES")
        print("="*80)
        print(f"{'Rank':<5} {'Feature':<45} {'Score':<8} {'Corr':<8} {'RF-Imp':<8}")
        print("-"*80)

        for idx, row in results.head(top_n).iterrows():
            print(f"{int(row['rank']):<5} {row['feature']:<45} {row['combined_score']:.4f}   "
                  f"{row['correlation']:.4f}   {row['rf_importance']:.4f}")

        print("-"*80)
        print(f"\nModel Performance:")
        print(f"  R² Score: {rf.score(X_scaled, y):.4f}")
        print(f"  Total Features Analyzed: {len(valid_features)}")
        print(f"  Total Signals: {len(signals_df)}")

        return results

    # Deprecated - keeping for reference but not used
    def identify_runs(self, df: pd.DataFrame) -> List[Dict]:
        """Identify consecutive price runs (up or down)"""
        print("\nIdentifying price runs...")
        print("-" * 50)
        runs = []
        current_run = None
        total_rows = len(df)
        
        # Progress tracking
        last_progress = 0
        
        for i in range(1, total_rows):
            # Show progress every 10%
            progress = int((i / total_rows) * 100)
            if progress >= last_progress + 10:
                print(f"Progress: {progress}% ({i}/{total_rows} rows processed)")
                last_progress = progress
            price_change = df.iloc[i]['Last'] - df.iloc[i-1]['Last']
            
            if price_change > 0:  # Up move
                if current_run is None or current_run['direction'] != 'up':
                    # Start new up run
                    if current_run is not None:
                        runs.append(current_run)
                    current_run = {
                        'direction': 'up',
                        'start_idx': i-1,
                        'end_idx': i,
                        'start_time': df.iloc[i-1]['Time'],
                        'end_time': df.iloc[i]['Time'],
                        'start_price': df.iloc[i-1]['Last'],
                        'end_price': df.iloc[i]['Last']
                    }
                else:
                    # Continue up run
                    current_run['end_idx'] = i
                    current_run['end_time'] = df.iloc[i]['Time']
                    current_run['end_price'] = df.iloc[i]['Last']
                    
            elif price_change < 0:  # Down move
                if current_run is None or current_run['direction'] != 'down':
                    # Start new down run
                    if current_run is not None:
                        runs.append(current_run)
                    current_run = {
                        'direction': 'down',
                        'start_idx': i-1,
                        'end_idx': i,
                        'start_time': df.iloc[i-1]['Time'],
                        'end_time': df.iloc[i]['Time'],
                        'start_price': df.iloc[i-1]['Last'],
                        'end_price': df.iloc[i]['Last']
                    }
                else:
                    # Continue down run
                    current_run['end_idx'] = i
                    current_run['end_time'] = df.iloc[i]['Time']
                    current_run['end_price'] = df.iloc[i]['Last']
        
        # Add last run
        if current_run is not None:
            runs.append(current_run)
        
        print(f"Progress: 100% ({total_rows}/{total_rows} rows processed)")
        
        # Calculate duration and price change for each run
        print(f"\nCalculating run statistics for {len(runs)} runs...")
        for run in runs:
            run['duration_minutes'] = (run['end_idx'] - run['start_idx'])
            run['price_change'] = run['end_price'] - run['start_price']
            run['return_pct'] = (abs(run['price_change']) / run['start_price']) * 100
        
        print(f"Identified {len(runs)} price runs successfully!")
        print("-" * 50)
        return runs
    
    def generate_signals(self, df: pd.DataFrame, runs: List[Dict], use_duration_stats: bool = True) -> pd.DataFrame:
        """Generate put/call signals based on run analysis using median thresholds"""
        print("\nGenerating trading signals...")
        print("-" * 50)
        
        # Filter for profitable runs only
        print("Filtering for profitable movements...")
        profitable_up_runs = [r for r in runs if r['direction'] == 'up' and r['price_change'] > 0]
        profitable_down_runs = [r for r in runs if r['direction'] == 'down' and r['price_change'] < 0]
        
        print(f"  - Total up runs: {len([r for r in runs if r['direction'] == 'up'])}")
        print(f"  - Profitable up runs: {len(profitable_up_runs)}")
        print(f"  - Total down runs: {len([r for r in runs if r['direction'] == 'down'])}")
        print(f"  - Profitable down runs: {len(profitable_down_runs)}")
        
        # Use profitable runs for median calculation
        up_runs = profitable_up_runs
        down_runs = profitable_down_runs
        
        median_up_duration = np.median([r['duration_minutes'] for r in up_runs]) if up_runs else 0
        median_down_duration = np.median([r['duration_minutes'] for r in down_runs]) if down_runs else 0
        
        # Load duration statistics if available
        if use_duration_stats and os.path.exists('data/profitable_duration_stats.json'):
            print("\nLoading duration statistics from analysis...")
            with open('data/profitable_duration_stats.json', 'r') as f:
                duration_stats = json.load(f)
            
            # Use median durations from full dataset analysis
            stats_up_median = duration_stats['up_runs']['durations']['median']
            stats_down_median = duration_stats['down_runs']['durations']['median']
            
            print(f"  - Using analyzed CALL threshold: {stats_up_median:.1f} minutes")
            print(f"  - Using analyzed PUT threshold: {stats_down_median:.1f} minutes")
            
            median_up_duration = stats_up_median
            median_down_duration = stats_down_median
        else:
            # Fallback to calculated medians from current dataset
            print("\nUsing calculated medians from current dataset")
        
        print(f"\nDuration thresholds:")
        print(f"  - CALL threshold: {median_up_duration:.2f} minutes")
        print(f"  - PUT threshold: {median_down_duration:.2f} minutes")
        
        # Generate signals for runs that meet median threshold
        print("\nEvaluating runs for signal generation...")
        signals = []
        total_runs = len(runs)
        qualified_runs = 0
        
        for idx, run in enumerate(runs):
            if (idx + 1) % 1000 == 0:
                print(f"  Processed {idx + 1}/{total_runs} runs...")
            # Only generate signals for profitable movements that meet duration threshold
            if (run['direction'] == 'up' and run['price_change'] > 0 and 
                run['duration_minutes'] >= median_up_duration):
                # Call signal
                signal = self._create_signal(df, run, 'call')
                signals.append(signal)
                qualified_runs += 1
            elif (run['direction'] == 'down' and run['price_change'] < 0 and 
                  run['duration_minutes'] >= median_down_duration):
                # Put signal
                signal = self._create_signal(df, run, 'put')
                signals.append(signal)
                qualified_runs += 1
        
        print(f"\nSignal generation complete!")
        print(f"  - Total runs evaluated: {total_runs}")
        print(f"  - Profitable runs: {len(up_runs) + len(down_runs)}")
        print(f"  - Runs meeting duration threshold: {qualified_runs}")
        print(f"  - Signals generated: {len(signals)}")
        
        if signals:
            avg_duration = np.mean([s['duration_minutes'] for s in signals])
            avg_return = np.mean([s['return_pct'] for s in signals])
            print(f"\nSignal statistics:")
            print(f"  - Average duration: {avg_duration:.2f} minutes")
            print(f"  - Average return: {avg_return:.4f}%")
        
        print("-" * 50)
        
        signals_df = pd.DataFrame(signals)
        return signals_df
    
    def _create_signal(self, df: pd.DataFrame, run: Dict, trade_type: str) -> Dict:
        """Create a signal dictionary with all required fields"""
        entry_idx = run['start_idx']
        exit_idx = run['end_idx']
        
        signal = {
            'trade_type': trade_type,
            'duration_minutes': run['duration_minutes'],
            'price_change': run['price_change'],
            'return_pct': run['return_pct'],
            
            # Entry data
            'entry_timestamp': df.iloc[entry_idx]['Time'],
            'entry_price': df.iloc[entry_idx]['Last'],
            'entry_open': df.iloc[entry_idx]['Open'],
            'entry_high': df.iloc[entry_idx]['High'],
            'entry_low': df.iloc[entry_idx]['Low'],
            'entry_close': df.iloc[entry_idx]['Last'],
            'entry_volume': df.iloc[entry_idx]['Volume'],
            'entry_EMA9': df.iloc[entry_idx]['EMA9'],
            'entry_EMA20': df.iloc[entry_idx]['EMA20'],
            'entry_EMA50': df.iloc[entry_idx]['EMA50'],
            'entry_VWAP': df.iloc[entry_idx]['VWAP'],
            'entry_RVOL20': df.iloc[entry_idx]['RVOL20'],
            'entry_RVOL_MOD': df.iloc[entry_idx]['RVOL_MOD'],
            'entry_RVOL_MOD_EXCL': df.iloc[entry_idx]['RVOL_MOD_EXCL'],
            'entry_ATR14_W': df.iloc[entry_idx]['ATR14_W'],
            'entry_RSI14_W': df.iloc[entry_idx]['RSI14_W'],
            'entry_StochRSI_K': df.iloc[entry_idx]['StochRSI_K'],
            'entry_StochRSI_D': df.iloc[entry_idx]['StochRSI_D'],
            'entry_OBV': df.iloc[entry_idx]['OBV'],
            
            # Exit data
            'exit_timestamp': df.iloc[exit_idx]['Time'],
            'exit_price': df.iloc[exit_idx]['Last'],
            'exit_open': df.iloc[exit_idx]['Open'],
            'exit_high': df.iloc[exit_idx]['High'],
            'exit_low': df.iloc[exit_idx]['Low'],
            'exit_close': df.iloc[exit_idx]['Last'],
            'exit_volume': df.iloc[exit_idx]['Volume'],
            'exit_EMA9': df.iloc[exit_idx]['EMA9'],
            'exit_EMA20': df.iloc[exit_idx]['EMA20'],
            'exit_EMA50': df.iloc[exit_idx]['EMA50'],
            'exit_VWAP': df.iloc[exit_idx]['VWAP'],
            'exit_RVOL20': df.iloc[exit_idx]['RVOL20'],
            'exit_RVOL_MOD': df.iloc[exit_idx]['RVOL_MOD'],
            'exit_RVOL_MOD_EXCL': df.iloc[exit_idx]['RVOL_MOD_EXCL'],
            'exit_ATR14_W': df.iloc[exit_idx]['ATR14_W'],
            'exit_RSI14_W': df.iloc[exit_idx]['RSI14_W'],
            'exit_StochRSI_K': df.iloc[exit_idx]['StochRSI_K'],
            'exit_StochRSI_D': df.iloc[exit_idx]['StochRSI_D'],
            'exit_OBV': df.iloc[exit_idx]['OBV']
        }
        
        return signal
    
    def run_analysis(self, input_folder: str, output_file: str, signals_file: str, months_limit: int = None):
        """Run the complete analysis pipeline"""
        # Step 1: Check if combined file exists, if not combine/load data
        if os.path.exists(output_file):
            print(f"Combined file already exists: {output_file}")
            print("Loading existing combined data...")

            # Load based on data source
            if self.data_source == 'parquet':
                df = pd.read_parquet(output_file)
            else:
                df = pd.read_csv(output_file)

            # Convert Time to datetime
            df['Time'] = pd.to_datetime(df['Time'])
            df = df.sort_values('Time')

            # Limit to recent months if specified
            if months_limit:
                cutoff_date = df['Time'].max() - pd.DateOffset(months=months_limit)
                original_len = len(df)
                df = df[df['Time'] >= cutoff_date].copy()
                print(f"Limiting data to last {months_limit} months (from {cutoff_date})")
                print(f"Reduced dataset from {original_len} to {len(df)} rows")

            self.df = df
            print(f"Loaded {len(df)} rows of data")
            print(f"Date range: {df['Time'].min()} to {df['Time'].max()}")
        else:
            print("\n" + "="*60)
            print("STEP 1: DATA COLLECTION")
            print("="*60)

            # Load data based on source type
            if self.data_source == 'parquet':
                # Extract symbol from input_folder path (e.g., "data/iwm/intraday" -> "iwm")
                symbol = os.path.basename(os.path.dirname(input_folder))

                # Load from parquet combined file
                df = self.load_parquet_data(symbol=symbol.upper(), data_dir=input_folder)
                if months_limit:
                    cutoff_date = df['Time'].max() - pd.DateOffset(months=months_limit)
                    df = df[df['Time'] >= cutoff_date].copy()
                    print(f"Limited to last {months_limit} months ({len(df)} rows)")
                self.df = df
            else:
                # Combine CSV files
                df = self.combine_csv_files(input_folder, output_file)
        
        # Step 2: Add technical indicators
        print("\n" + "="*60)
        print("STEP 2: TECHNICAL ANALYSIS")
        print("="*60)
        df = self.add_technical_indicators(df)
        
        # Save enhanced data to data/signals/ directory
        # Extract filename components for proper path construction
        base_filename = os.path.basename(output_file)
        if self.data_source == 'parquet':
            enhanced_filename = base_filename.replace('.parquet', '_with_indicators.parquet').replace('.csv', '_with_indicators.parquet')
            enhanced_file = os.path.join('data/signals', enhanced_filename)
            print("\nSaving enhanced data with indicators (parquet format)...")
            self._archive_file(enhanced_file)
            # Convert %Chg back to float for parquet
            df_save = df.copy()
            df_save['%Chg'] = df_save['%Chg'].str.rstrip('%').astype(float)
            df_save.to_parquet(enhanced_file, index=False)
            print(f"SUCCESS: Enhanced data saved to: {enhanced_file}")
        else:
            enhanced_filename = base_filename.replace('.csv', '_with_indicators.csv')
            enhanced_file = os.path.join('data/signals', enhanced_filename)
            print("\nSaving enhanced data with indicators (CSV format)...")
            self._archive_file(enhanced_file)
            df.to_csv(enhanced_file, index=False)
            print(f"SUCCESS: Enhanced data saved to: {enhanced_file}")

        # Step 3: Generate technical indicator-based signals
        print("\n" + "="*60)
        print("STEP 3: TECHNICAL SIGNAL GENERATION")
        print("="*60)
        signals_df = self.generate_technical_signals(df)

        # Save signals (use format based on data source)
        if self.data_source == 'parquet':
            signals_file_final = signals_file.replace('.csv', '.parquet')
            print("\nSaving trading signals (parquet format)...")
            self._archive_file(signals_file_final)
            signals_df.to_parquet(signals_file_final, index=False)
            print(f"SUCCESS: Trading signals saved to: {signals_file_final}")
        else:
            print("\nSaving trading signals (CSV format)...")
            self._archive_file(signals_file)
            signals_df.to_csv(signals_file, index=False)
            print(f"SUCCESS: Trading signals saved to: {signals_file}")

        # Step 4: Analyze feature importance
        print("\n" + "="*60)
        print("STEP 4: FEATURE IMPORTANCE ANALYSIS")
        print("="*60)

        if len(signals_df) > 0:
            importance_df = self.analyze_feature_importance(signals_df, top_n=20)

            # Save feature importance results
            if len(importance_df) > 0:
                if self.data_source == 'parquet':
                    importance_file = signals_file.replace('_signals.parquet', '_feature_importance.parquet')
                    print(f"\nSaving feature importance analysis (parquet format)...")
                    self._archive_file(importance_file)
                    importance_df.to_parquet(importance_file, index=False)
                    print(f"SUCCESS: Feature importance saved to: {importance_file}")
                else:
                    importance_file = signals_file.replace('_signals.csv', '_feature_importance.csv')
                    print(f"\nSaving feature importance analysis (CSV format)...")
                    self._archive_file(importance_file)
                    importance_df.to_csv(importance_file, index=False)
                    print(f"SUCCESS: Feature importance saved to: {importance_file}")
        else:
            print("  Skipping feature importance analysis (no signals generated)")

        # Print summary statistics
        print("\n" + "="*60)
        print("ANALYSIS SUMMARY")
        print("="*60)
        print(f"Total signals generated: {len(signals_df)}")
        if len(signals_df) > 0:
            print(f"  - Call signals: {len(signals_df[signals_df['trade_type'] == 'call'])}")
            print(f"  - Put signals: {len(signals_df[signals_df['trade_type'] == 'put'])}")
            print(f"  - Average return (20min): {signals_df['return_pct'].mean():.2f}%")
            print(f"  - Best average return: {signals_df['best_return'].mean():.2f}% (avg window: {signals_df['best_window_minutes'].mean():.0f} min)")
            print(f"  - Profitable signals: {len(signals_df[signals_df['return_pct'] > 0])} ({len(signals_df[signals_df['return_pct'] > 0])/len(signals_df)*100:.1f}%)")

            # Show returns by time window
            print("\n  Returns by time window:")
            time_windows = [5, 10, 15, 20, 30, 45, 60]
            for window in time_windows:
                col = f'return_{window}min'
                if col in signals_df.columns:
                    avg_return = signals_df[col].mean()
                    profitable_pct = (signals_df[col] > 0).sum() / len(signals_df) * 100
                    print(f"    {window:2d} min: {avg_return:6.2f}% avg ({profitable_pct:4.1f}% profitable)")

        self.df = df
        self.signals_df = signals_df

        return df, signals_df


def main():
    """Main execution function"""
    import argparse
    
    # Set up command line arguments
    parser = argparse.ArgumentParser(description='Analyze stock historical data with technical indicators')
    parser.add_argument('-symbol', '--symbol', type=str, default='IWM',
                       help='Stock symbol to analyze: IWM, QQQ, SPY (default: IWM)')
    parser.add_argument('-months', type=int, default=2,
                       help='Number of months to analyze (default: 2)')
    parser.add_argument('-all', action='store_true',
                       help='Analyze all available data (overrides -months)')
    parser.add_argument('--source', type=str, choices=['csv', 'parquet', 'auto'], default='auto',
                       help='Data source format: csv, parquet, or auto (default: auto - prefers parquet)')

    args = parser.parse_args()

    # Normalize symbol to uppercase
    symbol = args.symbol.upper()

    # Determine months limit
    months_limit = None if args.all else args.months

    # Display what we're analyzing
    if args.all:
        print(f"Analyzing ALL available {symbol} data...")
    else:
        print(f"Analyzing last {months_limit} months of {symbol} data...")

    analyzer = MarketAnalyzer()

    # Define paths based on symbol - using relative paths for compatibility
    symbol_lower = symbol.lower()

    # Determine data source and input folder
    if args.source == 'parquet' or args.source == 'auto':
        # Check if parquet data exists
        parquet_folder = f"data/{symbol_lower}/intraday"
        if os.path.exists(parquet_folder):
            # Look for combined parquet file
            combined_parquet = f"{parquet_folder}/{symbol_lower}_av_1min_combined.parquet"
            if os.path.exists(combined_parquet):
                print(f"Using parquet data from: {parquet_folder}")
                input_folder = parquet_folder
                data_source = 'parquet'
            elif args.source == 'parquet':
                print(f"ERROR: No combined parquet file found at {combined_parquet}")
                print(f"Run: python scripts/fetch_alphavantage_intraday.py --symbol {symbol}")
                return
            else:
                # Auto mode - fall back to CSV
                print(f"No parquet data found, falling back to CSV...")
                input_folder = "data/stock_prices"
                data_source = 'csv'
        elif args.source == 'parquet':
            print(f"ERROR: Parquet folder not found: {parquet_folder}")
            print(f"Run: python scripts/fetch_alphavantage_intraday.py --symbol {symbol}")
            return
        else:
            # Auto mode - fall back to CSV
            input_folder = "data/stock_prices"
            data_source = 'csv'
    else:
        input_folder = "data/stock_prices"
        data_source = 'csv'

    # Check for existing combined file to determine date range
    import glob as glob_module

    # Look for existing combined files based on data source
    if data_source == 'parquet':
        # Check for parquet combined file
        existing_combined = glob_module.glob(f"data/{symbol_lower}/intraday/{symbol_lower}_av_1min_combined.parquet")
    else:
        # Check for CSV combined files
        existing_combined = glob_module.glob(f"data/historical_{symbol_lower}_*_*.csv")
        existing_combined = [f for f in existing_combined if '_with_indicators' not in f and '_signals' not in f and '_archive' not in f]

    if existing_combined:
        # Load existing file to get date range
        existing_file = existing_combined[0]
        if data_source == 'parquet':
            temp_df = pd.read_parquet(existing_file)
            # Parquet files have timestamp as index, reset to column
            temp_df = temp_df.reset_index()
            # Rename timestamp to Time if needed
            if 'timestamp' in temp_df.columns:
                temp_df = temp_df.rename(columns={'timestamp': 'Time'})
        else:
            temp_df = pd.read_csv(existing_file)

        temp_df['Time'] = pd.to_datetime(temp_df['Time'])

        # Apply months limit if specified
        if months_limit:
            cutoff_date = temp_df['Time'].max() - pd.DateOffset(months=months_limit)
            temp_df = temp_df[temp_df['Time'] >= cutoff_date]

        start_date = temp_df['Time'].min().strftime('%Y%m%d')
        end_date = temp_df['Time'].max().strftime('%Y%m%d')
    else:
        # Use placeholder - will be determined after combining files
        start_date = "YYYYMMDD"
        end_date = "YYYYMMDD"

    # Create signals directory if it doesn't exist
    signals_dir = "data/signals"
    os.makedirs(signals_dir, exist_ok=True)

    # Determine file extensions based on data source
    if data_source == 'parquet':
        data_ext = '.parquet'
    else:
        data_ext = '.csv'

    # Generate filenames with symbol and date range
    output_file = f"data/historical_{symbol_lower}_{start_date}_{end_date}{data_ext}"
    enhanced_file = f"{signals_dir}/historical_{symbol_lower}_{start_date}_{end_date}_with_indicators{data_ext}"
    signals_file = f"{signals_dir}/historical_{symbol_lower}_{start_date}_{end_date}_signals{data_ext}"

    # Set the data source in analyzer so it knows which format to use
    analyzer.data_source = data_source

    # Run analysis
    df, signals_df = analyzer.run_analysis(input_folder, output_file, signals_file, months_limit)

    # If we used placeholders, rename files with actual dates
    if start_date == "YYYYMMDD" and df is not None and len(df) > 0:
        actual_start = df['Time'].min().strftime('%Y%m%d')
        actual_end = df['Time'].max().strftime('%Y%m%d')

        proper_output = f"data/historical_{symbol_lower}_{actual_start}_{actual_end}{data_ext}"
        proper_enhanced = f"data/historical_{symbol_lower}_{actual_start}_{actual_end}_with_indicators{data_ext}"
        proper_signals = f"{signals_dir}/historical_{symbol_lower}_{actual_start}_{actual_end}_signals{data_ext}"

        import shutil
        if output_file != proper_output and os.path.exists(output_file):
            shutil.move(output_file, proper_output)
            output_file = proper_output
        if enhanced_file != proper_enhanced and os.path.exists(enhanced_file):
            shutil.move(enhanced_file, proper_enhanced)
            enhanced_file = proper_enhanced
        if signals_file != proper_signals and os.path.exists(signals_file):
            shutil.move(signals_file, proper_signals)
            signals_file = proper_signals
    
    print("\n" + "="*60)
    print("SUCCESS: ANALYSIS COMPLETE!")
    print("="*60)
    print("\nOutput files:")
    print(f"  1. Combined data: {output_file}")
    print(f"  2. Enhanced data: {enhanced_file}")
    print(f"  3. Trading signals: {signals_file}")
    print("\nAnalysis finished successfully!")


if __name__ == "__main__":
    main()