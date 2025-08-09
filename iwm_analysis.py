#!/usr/bin/env python3
"""
IWM Historical Stock Price Analysis with Technical Indicators and Trading Signals
Implements various technical indicators and generates put/call signals based on price movements
"""

import pandas as pd
import numpy as np
from datetime import datetime, time
import os
import glob
from typing import Tuple, List, Dict
import warnings
# import json  # No longer needed - removed run-based analysis
warnings.filterwarnings('ignore')


class IWMAnalyzer:
    def __init__(self):
        self.df = None
        self.signals_df = None
        
    def combine_csv_files(self, folder_path: str, output_path: str) -> pd.DataFrame:
        """Combine all CSV files from stock_prices folder into one DataFrame"""
        print("Combining CSV files...")
        
        # Get all CSV files
        csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
        print(f"Found {len(csv_files)} CSV files")
        
        # Read and combine all files
        dfs = []
        for file in csv_files:
            # Read CSV and filter out non-data rows
            df_temp = pd.read_csv(file)
            # Remove rows where 'Time' column contains "Downloaded from"
            df_temp = df_temp[~df_temp['Time'].str.contains("Downloaded from", na=False)]
            dfs.append(df_temp)
            print(f"Read {file}: {len(df_temp)} rows")
        
        # Combine all dataframes
        df_combined = pd.concat(dfs, ignore_index=True)
        
        # Convert Time column to datetime
        df_combined['Time'] = pd.to_datetime(df_combined['Time'])
        
        # Sort by time (ascending)
        df_combined = df_combined.sort_values('Time')
        
        # Remove duplicates based on Time
        df_combined = df_combined.drop_duplicates(subset=['Time'], keep='first')
        
        # Reset index
        df_combined = df_combined.reset_index(drop=True)
        
        # Save combined file
        df_combined.to_csv(output_path, index=False)
        print(f"Combined data saved to {output_path}")
        print(f"Total rows: {len(df_combined)}")
        print(f"Date range: {df_combined['Time'].min()} to {df_combined['Time'].max()}")
        
        self.df = df_combined
        return df_combined
    
    def calculate_true_range(self, high: pd.Series, low: pd.Series, close_prev: pd.Series) -> pd.Series:
        """Calculate True Range for ATR calculation"""
        hl = high - low
        hc = np.abs(high - close_prev)
        lc = np.abs(low - close_prev)
        return pd.concat([hl, hc, lc], axis=1).max(axis=1)
    
    def wilder_moving_average(self, values: pd.Series, period: int) -> pd.Series:
        """Calculate Wilder's Moving Average (RMA)"""
        # Start with SMA for the first period
        rma = values.rolling(window=period).mean()
        
        # Apply Wilder's smoothing
        for i in range(period, len(values)):
            if not pd.isna(rma.iloc[i-1]) and not pd.isna(values.iloc[i]):
                rma.iloc[i] = (rma.iloc[i-1] * (period - 1) + values.iloc[i]) / period
        
        return rma
    
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
        """Calculate EMA using standard method (matches Robinhood and other platforms)"""
        # Use pandas built-in EMA which matches the standard calculation
        # This uses: EMA = (Price * Multiplier) + (Previous EMA * (1 - Multiplier))
        # Where Multiplier = 2 / (Period + 1)
        return prices.ewm(span=period, adjust=False).mean()
    
    def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Calculate VWAP (resets each session)"""
        df = df.copy()
        df['Date'] = df['Time'].dt.date
        df['TypicalPrice'] = (df['High'] + df['Low'] + df['Last']) / 3
        df['TPxV'] = df['TypicalPrice'] * df['Volume']
        
        vwap = pd.Series(index=df.index, dtype=float)
        
        for date in df['Date'].unique():
            mask = df['Date'] == date
            cum_tpv = df.loc[mask, 'TPxV'].cumsum()
            cum_vol = df.loc[mask, 'Volume'].cumsum()
            vwap.loc[mask] = cum_tpv / cum_vol
        
        return vwap
    
    def calculate_rvol(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        """Calculate Relative Volume"""
        rolling_avg = df['Volume'].rolling(window=period).mean()
        rvol = df['Volume'] / rolling_avg
        return rvol
    
    def calculate_rvol_minute_of_day(self, df: pd.DataFrame, exclude_current: bool = False) -> Tuple[pd.Series, pd.Series]:
        """Calculate RVOL based on minute of day average"""
        df = df.copy()
        df['MinuteOfDay'] = df['Time'].dt.hour * 60 + df['Time'].dt.minute
        df['Date'] = df['Time'].dt.date
        
        # Calculate average volume for each minute of day
        minute_avg = df.groupby('MinuteOfDay')['Volume'].mean()
        
        # RVOL minute of day (including current session)
        rvol_mod = df.apply(lambda row: row['Volume'] / minute_avg.get(row['MinuteOfDay'], np.nan) 
                           if row['MinuteOfDay'] in minute_avg else np.nan, axis=1)
        
        # RVOL minute of day (excluding current session)
        rvol_mod_excl = pd.Series(index=df.index, dtype=float)
        
        if exclude_current:
            for date in df['Date'].unique():
                date_mask = df['Date'] == date
                other_dates_mask = df['Date'] != date
                
                for minute in df.loc[date_mask, 'MinuteOfDay'].unique():
                    minute_mask = df['MinuteOfDay'] == minute
                    other_dates_minute_mask = other_dates_mask & minute_mask
                    
                    if other_dates_minute_mask.any():
                        avg_vol = df.loc[other_dates_minute_mask, 'Volume'].mean()
                        current_mask = date_mask & minute_mask
                        rvol_mod_excl.loc[current_mask] = df.loc[current_mask, 'Volume'] / avg_vol
        else:
            rvol_mod_excl = rvol_mod
        
        return rvol_mod, rvol_mod_excl
    
    def calculate_obv(self, df: pd.DataFrame) -> pd.Series:
        """Calculate On-Balance Volume using continuous method (matches Robinhood)"""
        df = df.copy()
        price_change = df['Last'].diff()
        
        obv = pd.Series(index=df.index, dtype=float)
        
        # Start with 0 for first value (platforms may add offset for display)
        obv.iloc[0] = 0
        
        # Calculate OBV continuously without daily resets
        for i in range(1, len(df)):
            if price_change.iloc[i] > 0:
                obv.iloc[i] = obv.iloc[i-1] + df['Volume'].iloc[i]
            elif price_change.iloc[i] < 0:
                obv.iloc[i] = obv.iloc[i-1] - df['Volume'].iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1]
        
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
        
        # Apply Wilder's smoothing for %K
        stoch_rsi_k = self.wilder_moving_average(stoch_rsi, k_period)
        
        # Apply Wilder's smoothing for %D
        stoch_rsi_d = self.wilder_moving_average(stoch_rsi_k, d_period)
        
        return stoch_rsi_k, stoch_rsi_d
    
    def add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add all technical indicators to the dataframe"""
        print("\nCalculating technical indicators...")
        print("-" * 50)
        
        # ATR with Wilder
        print("1/9 - Calculating ATR (Average True Range)...")
        df['ATR14_W'] = self.calculate_atr(df, 14)
        
        # RSI with Wilder
        print("2/9 - Calculating RSI (Relative Strength Index)...")
        df['RSI14_W'] = self.calculate_rsi(df['Last'], 14)
        
        # EMAs with SMA seeding
        print("3/9 - Calculating EMAs (Exponential Moving Averages)...")
        print("    - EMA 9...")
        df['EMA9'] = self.calculate_ema(df['Last'], 9)
        print("    - EMA 20...")
        df['EMA20'] = self.calculate_ema(df['Last'], 20)
        print("    - EMA 50...")
        df['EMA50'] = self.calculate_ema(df['Last'], 50)
        
        # VWAP
        print("4/9 - Calculating VWAP (Volume Weighted Average Price)...")
        df['VWAP'] = self.calculate_vwap(df)
        
        # RVOL
        print("5/9 - Calculating RVOL (Relative Volume)...")
        print("    - RVOL 20-period...")
        df['RVOL20'] = self.calculate_rvol(df, 20)
        print("    - RVOL minute of day...")
        df['RVOL_MOD'], df['RVOL_MOD_EXCL'] = self.calculate_rvol_minute_of_day(df, exclude_current=True)
        
        # OBV
        print("6/9 - Calculating OBV (On-Balance Volume)...")
        df['OBV'] = self.calculate_obv(df)
        
        # Stochastic RSI
        print("7/9 - Calculating Stochastic RSI...")
        # Debug RSI values first
        rsi_stats = df['RSI14_W'].describe()
        print(f"    - RSI stats: min={rsi_stats['min']:.2f}, max={rsi_stats['max']:.2f}, mean={rsi_stats['50%']:.2f}")
        print(f"    - RSI valid values: {df['RSI14_W'].count()} out of {len(df)} total rows")
        
        df['StochRSI_K'], df['StochRSI_D'] = self.calculate_stoch_rsi(df['RSI14_W'])
        print(f"    - StochRSI K: {df['StochRSI_K'].count()} valid values, mean={df['StochRSI_K'].mean():.2f}")
        print(f"    - StochRSI D: {df['StochRSI_D'].count()} valid values, mean={df['StochRSI_D'].mean():.2f}")
        
        print("8/9 - Validating indicators...")
        # Validate all indicators were calculated
        indicators = ['ATR14_W', 'RSI14_W', 'EMA9', 'EMA20', 'EMA50', 'VWAP', 
                     'RVOL20', 'RVOL_MOD', 'RVOL_MOD_EXCL', 'OBV', 'StochRSI_K', 'StochRSI_D']
        for indicator in indicators:
            valid_count = df[indicator].count()
            if valid_count == 0:
                print(f"    ⚠️  WARNING: {indicator} has no valid values!")
            else:
                print(f"    ✓ {indicator}: {valid_count} valid values")
        
        print("9/9 - Technical indicators calculated successfully!")
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
            
            # CALL Signal Conditions
            call_conditions = 0
            if current['Consecutive_Up'] >= consecutive_periods:  # Consecutive up moves
                call_conditions += 1
            if current['RSI14_W'] < 50 and current['RSI14_W'] > 25:  # RSI in bullish range
                call_conditions += 1
            if current.get('StochRSI_K', 50) < 80:  # StochRSI not overbought
                call_conditions += 1
            if current['Last'] > current.get('VWAP', current['Last']):  # Price above VWAP
                call_conditions += 1
            if current['Last'] > current.get('EMA9', current['Last']):  # Price above EMA9
                call_conditions += 1
            
            # PUT Signal Conditions
            put_conditions = 0
            if current['Consecutive_Down'] >= consecutive_periods:  # Consecutive down moves
                put_conditions += 1
            if current['RSI14_W'] > 50 and current['RSI14_W'] < 75:  # RSI in bearish range
                put_conditions += 1
            if current.get('StochRSI_K', 50) > 20:  # StochRSI not oversold
                put_conditions += 1
            if current['Last'] < current.get('VWAP', current['Last']):  # Price below VWAP
                put_conditions += 1
            if current['Last'] < current.get('EMA9', current['Last']):  # Price below EMA9
                put_conditions += 1
            
            # Generate signal if enough conditions are met
            min_conditions = 3
            
            if call_conditions >= min_conditions and call_conditions > put_conditions:
                signal = 'call'
                signal_strength = call_conditions
            elif put_conditions >= min_conditions and put_conditions > call_conditions:
                signal = 'put'
                signal_strength = put_conditions
            
            if signal:
                # Look ahead for potential exit (limited lookahead)
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
                            'signal_strength': signal_strength,
                            'conditions_met': f"{signal_strength}/5",
                            'entry_rsi': current['RSI14_W'],
                            'entry_vwap': current.get('VWAP', np.nan),
                            'entry_ema9': current.get('EMA9', np.nan),
                            'entry_ema20': current.get('EMA20', np.nan),
                            'entry_stochrsi_k': current.get('StochRSI_K', np.nan),
                            'entry_atr': current.get('ATR14_W', np.nan),
                            'entry_obv': current.get('OBV', np.nan),
                            'exit_time': df.iloc[idx + exit_idx]['Time'],
                            'exit_price': max_price if signal == 'call' else min_price,
                            'exit_rsi': df.iloc[idx + exit_idx]['RSI14_W'],
                            'exit_vwap': df.iloc[idx + exit_idx].get('VWAP', np.nan),
                            'exit_obv': df.iloc[idx + exit_idx].get('OBV', np.nan)
                        }
                        
                        signals.append(signal_data)
        
        print(f"  Progress: 100% - Signal generation complete!")
        
        signals_df = pd.DataFrame(signals)
        if len(signals_df) == 0:
            # Return empty dataframe with expected columns
            return pd.DataFrame(columns=['entry_time', 'trade_type', 'entry_price', 'return_pct'])
        
        return signals_df
    
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
        # Step 1: Check if combined file exists, if not combine CSV files
        if os.path.exists(output_file):
            print(f"Combined file already exists: {output_file}")
            print("Loading existing combined data...")
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
            # Combine CSV files
            df = self.combine_csv_files(input_folder, output_file)
        
        # Step 2: Add technical indicators
        print("\n" + "="*60)
        print("STEP 2: TECHNICAL ANALYSIS")
        print("="*60)
        df = self.add_technical_indicators(df)
        
        # Save enhanced data
        enhanced_file = output_file.replace('.csv', '_with_indicators.csv')
        print("\nSaving enhanced data with indicators...")
        df.to_csv(enhanced_file, index=False)
        print(f"✓ Enhanced data saved to: {enhanced_file}")
        
        # Step 3: Generate technical indicator-based signals
        print("\n" + "="*60)
        print("STEP 3: TECHNICAL SIGNAL GENERATION")
        print("="*60)
        signals_df = self.generate_technical_signals(df)
        
        # Save signals
        print("\nSaving trading signals...")
        signals_df.to_csv(signals_file, index=False)
        print(f"✓ Trading signals saved to: {signals_file}")
        
        # Print summary statistics
        print("\n" + "="*60)
        print("ANALYSIS SUMMARY")
        print("="*60)
        print(f"Total signals generated: {len(signals_df)}")
        if len(signals_df) > 0:
            print(f"  - Call signals: {len(signals_df[signals_df['trade_type'] == 'call'])}")
            print(f"  - Put signals: {len(signals_df[signals_df['trade_type'] == 'put'])}")
            print(f"  - Average return: {signals_df['return_pct'].mean():.2f}%")
            print(f"  - Profitable signals: {len(signals_df[signals_df['return_pct'] > 0])} ({len(signals_df[signals_df['return_pct'] > 0])/len(signals_df)*100:.1f}%)")
        
        self.df = df
        self.signals_df = signals_df
        
        return df, signals_df


def main():
    """Main execution function"""
    import argparse
    
    # Set up command line arguments
    parser = argparse.ArgumentParser(description='Analyze IWM historical data with technical indicators')
    parser.add_argument('-months', type=int, default=2, 
                       help='Number of months to analyze (default: 2)')
    parser.add_argument('-all', action='store_true', 
                       help='Analyze all available data (overrides -months)')
    
    args = parser.parse_args()
    
    # Determine months limit
    months_limit = None if args.all else args.months
    
    # Display what we're analyzing
    if args.all:
        print("Analyzing ALL available data...")
    else:
        print(f"Analyzing last {months_limit} months of data...")
    
    analyzer = IWMAnalyzer()
    
    # Define paths - using relative paths for compatibility
    input_folder = "data/stock_prices"
    output_file = "data/historical_iwm_0824_0825.csv"
    enhanced_file = "data/historical_iwm_0824_0825_with_indicators.csv"
    signals_file = "data/historical_iwm_0824_0825_signals.csv"
    
    # Run analysis
    df, signals_df = analyzer.run_analysis(input_folder, output_file, signals_file, months_limit)
    
    print("\n" + "="*60)
    print("✓ ANALYSIS COMPLETE!")
    print("="*60)
    print("\nOutput files:")
    print(f"  1. Combined data: {output_file}")
    print(f"  2. Enhanced data: {enhanced_file}")
    print(f"  3. Trading signals: {signals_file}")
    print("\nAnalysis finished successfully!")


if __name__ == "__main__":
    main()