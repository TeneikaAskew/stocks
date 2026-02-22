#!/usr/bin/env python3
"""
Enhanced market data analyzer with comprehensive technical indicators and trading signals.
Analyzes data for all tickers (IWM, SPY, QQQ, SPX) with the same capabilities as IWM analysis.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta, time
import argparse
import json
import warnings
warnings.filterwarnings('ignore')


class MarketAnalyzer:
    """Comprehensive market analyzer for all tickers with signal generation."""
    
    def __init__(self):
        self.tickers = ['IWM', 'SPY', 'QQQ', 'SPX']
        self.market_data = {}
        self.signals = {}
        self.min_periods_for_indicators = 2  # Allow calculation with minimal data
        
    def load_ticker_data(self, ticker):
        """Load parquet data for a specific ticker."""
        data_dir = Path("data")
        ticker_lower = ticker.lower()
        ticker_dir = data_dir / ticker_lower
        
        # Try to load the current year's data
        current_year = datetime.now().year
        parquet_file = ticker_dir / f"{ticker_lower}_{current_year}.parquet"
        
        if parquet_file.exists():
            df = pd.read_parquet(parquet_file)
            if not df.empty:
                # Ensure index is datetime
                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index)
                return df.sort_index()
        
        return pd.DataFrame()
    
    def load_minute_data(self, ticker, date):
        """Load minute-level data for a specific ticker and date."""
        data_dir = Path("data")
        ticker_lower = ticker.lower()
        minute_dir = data_dir / ticker_lower / "minute"
        
        date_str = date.strftime('%Y%m%d')
        minute_file = minute_dir / f"{ticker_lower}_minute_{date_str}.parquet"
        
        if minute_file.exists():
            return pd.read_parquet(minute_file)
        return pd.DataFrame()
    
    def load_all_market_data(self):
        """Load data for all available tickers."""
        for ticker in self.tickers:
            df = self.load_ticker_data(ticker)
            if not df.empty:
                self.market_data[ticker] = df
                print(f"Loaded {ticker}: {len(df)} daily records")
        return self.market_data
    
    def calculate_vwap_from_minute(self, ticker, date):
        """Calculate VWAP from minute data for a specific date."""
        minute_df = self.load_minute_data(ticker, date)
        if minute_df.empty:
            return np.nan
        
        typical_price = (minute_df['High'] + minute_df['Low'] + minute_df['Close']) / 3
        vwap = (typical_price * minute_df['Volume']).sum() / minute_df['Volume'].sum()
        return vwap
    
    def calculate_stoch_rsi(self, rsi, period=14, k_period=3, d_period=3):
        """Calculate Stochastic RSI."""
        rsi_min = rsi.rolling(window=period).min()
        rsi_max = rsi.rolling(window=period).max()
        
        # Handle division by zero
        rsi_range = rsi_max - rsi_min
        rsi_range = rsi_range.replace(0, np.nan)
        
        stoch_rsi = 100 * (rsi - rsi_min) / rsi_range
        
        # Apply smoothing for %K and %D
        stoch_rsi_k = stoch_rsi.rolling(window=k_period).mean()
        stoch_rsi_d = stoch_rsi_k.rolling(window=d_period).mean()
        
        return stoch_rsi_k, stoch_rsi_d
    
    def calculate_rsi(self, prices, period=14):
        """Calculate RSI with proper Wilder's smoothing."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0))
        loss = (-delta.where(delta < 0, 0))
        
        # Use exponential weighted mean for RSI calculation
        avg_gain = gain.rolling(window=period, min_periods=1).mean()
        avg_loss = loss.rolling(window=period, min_periods=1).mean()
        
        # For proper Wilder's smoothing (after initial period)
        for i in range(period, len(prices)):
            avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
            avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_atr(self, df, period=14):
        """Calculate Average True Range."""
        high = df['High']
        low = df['Low']
        close = df['Close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean()
        
        # Apply Wilder's smoothing
        for i in range(period, len(tr)):
            if i > 0:
                atr.iloc[i] = (atr.iloc[i-1] * (period - 1) + tr.iloc[i]) / period
        
        return atr
    
    def add_enhanced_indicators(self, df, ticker):
        """Add comprehensive technical indicators to dataframe."""
        print(f"  Calculating enhanced indicators for {ticker}...")
        
        # Ensure we have the necessary columns
        if 'Close' not in df.columns:
            print(f"    Warning: No Close price data for {ticker}")
            return df
        
        # Convert Last to Close if needed
        if 'Last' in df.columns and 'Close' not in df.columns:
            df['Close'] = df['Last']
        elif 'Last' in df.columns:
            df['Close'] = df['Close'].fillna(df['Last'])
        
        # Basic price metrics
        df['price_change'] = df['Close'].pct_change() * 100
        df['price_change_dollar'] = df['Close'].diff()
        
        # Volume metrics
        if 'Volume' in df.columns:
            df['volume_ma'] = df['Volume'].rolling(window=20, min_periods=1).mean()
            df['rvol'] = df['Volume'] / df['volume_ma']
            df['dollar_volume'] = df['Close'] * df['Volume']
        
        # Moving averages - use min_periods for limited data
        df['sma_5'] = df['Close'].rolling(window=5, min_periods=1).mean()
        df['sma_10'] = df['Close'].rolling(window=10, min_periods=1).mean()
        df['sma_20'] = df['Close'].rolling(window=20, min_periods=1).mean()
        df['sma_50'] = df['Close'].rolling(window=50, min_periods=1).mean()
        df['sma_200'] = df['Close'].rolling(window=200, min_periods=1).mean()
        
        # Exponential moving averages
        df['ema_9'] = df['Close'].ewm(span=9, min_periods=1, adjust=False).mean()
        df['ema_21'] = df['Close'].ewm(span=21, min_periods=1, adjust=False).mean()
        df['ema_50'] = df['Close'].ewm(span=50, min_periods=1, adjust=False).mean()
        
        # RSI calculation
        df['rsi_14'] = self.calculate_rsi(df['Close'], period=14)
        df['rsi_9'] = self.calculate_rsi(df['Close'], period=9)
        
        # ATR calculation
        df['atr_14'] = self.calculate_atr(df, period=14)
        df['atr_percent'] = (df['atr_14'] / df['Close']) * 100
        
        # Bollinger Bands
        df['bb_middle'] = df['sma_20']
        df['bb_std'] = df['Close'].rolling(window=20, min_periods=1).std()
        df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * 2)
        df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * 2)
        df['bb_width'] = df['bb_upper'] - df['bb_lower']
        df['bb_percent'] = (df['Close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
        
        # MACD
        exp1 = df['Close'].ewm(span=12, min_periods=1, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, min_periods=1, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9, min_periods=1, adjust=False).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        
        # Stochastic Oscillator
        low_min = df['Low'].rolling(window=14, min_periods=1).min()
        high_max = df['High'].rolling(window=14, min_periods=1).max()
        df['stoch_k'] = 100 * ((df['Close'] - low_min) / (high_max - low_min))
        df['stoch_d'] = df['stoch_k'].rolling(window=3, min_periods=1).mean()
        
        # Price position metrics
        df['high_52w'] = df['High'].rolling(window=252, min_periods=1).max()
        df['low_52w'] = df['Low'].rolling(window=252, min_periods=1).min()
        df['pct_from_52w_high'] = ((df['Close'] - df['high_52w']) / df['high_52w']) * 100
        df['pct_from_52w_low'] = ((df['Close'] - df['low_52w']) / df['low_52w']) * 100
        
        # Consecutive movement detection
        df['up_move'] = df['price_change'] > 0
        df['down_move'] = df['price_change'] < 0
        df['consecutive_up'] = df['up_move'].rolling(3, min_periods=1).sum()
        df['consecutive_down'] = df['down_move'].rolling(3, min_periods=1).sum()
        
        # Support and Resistance levels
        df['resistance_1'] = df['High'].rolling(window=20, min_periods=1).max()
        df['support_1'] = df['Low'].rolling(window=20, min_periods=1).min()
        df['pivot'] = (df['High'] + df['Low'] + df['Close']) / 3
        
        # Calculate Stochastic RSI
        df['stoch_rsi_k'], df['stoch_rsi_d'] = self.calculate_stoch_rsi(df['rsi_14'])
        
        # VWAP calculation
        if 'Volume' in df.columns:
            df['typical_price'] = (df['High'] + df['Low'] + df['Close']) / 3
            df['tpv'] = df['typical_price'] * df['Volume']
            
            # Calculate daily VWAP (reset each day)
            df['vwap'] = df.groupby(df.index.date).apply(
                lambda x: (x['tpv'].cumsum() / x['Volume'].cumsum()) if len(x) > 0 else x['typical_price']
            ).reset_index(level=0, drop=True)
            
            # If VWAP is NaN, use typical price
            df['vwap'] = df['vwap'].fillna(df['typical_price'])
        
        # Price position relative to indicators
        df['price_vs_sma20'] = ((df['Close'] - df['sma_20']) / df['sma_20']) * 100
        df['price_vs_sma50'] = ((df['Close'] - df['sma_50']) / df['sma_50']) * 100
        df['price_vs_ema9'] = ((df['Close'] - df['ema_9']) / df['ema_9']) * 100
        df['price_vs_ema21'] = ((df['Close'] - df['ema_21']) / df['ema_21']) * 100
        
        if 'vwap' in df.columns:
            df['price_vs_vwap'] = ((df['Close'] - df['vwap']) / df['vwap']) * 100
        
        # Gap analysis
        df['gap'] = df['Open'] - df['Close'].shift(1)
        df['gap_percent'] = (df['gap'] / df['Close'].shift(1)) * 100
        
        # Range metrics
        df['daily_range'] = df['High'] - df['Low']
        df['daily_range_percent'] = (df['daily_range'] / df['Close']) * 100
        df['close_vs_range'] = (df['Close'] - df['Low']) / df['daily_range']
        
        return df
    
    def generate_trading_signals(self, df, ticker, consecutive_periods=3):
        """Generate trading signals based on technical indicators."""
        print(f"  Generating trading signals for {ticker}...")
        
        signals = []
        total_rows = len(df)
        
        # Skip if not enough data
        if total_rows < consecutive_periods + 20:
            print(f"    Not enough data for signal generation")
            return pd.DataFrame()
        
        # Signal generation
        for idx in range(consecutive_periods, min(len(df)-20, len(df))):
            current = df.iloc[idx]
            
            # Skip if missing critical indicators
            if pd.isna(current.get('rsi_14')) or pd.isna(current.get('Close')):
                continue
            
            signal = None
            signal_strength = 0
            conditions_detail = []
            
            # CALL Signal Conditions
            call_conditions = 0
            if current.get('consecutive_up', 0) >= consecutive_periods:
                call_conditions += 1
                conditions_detail.append('consecutive_up')
            
            if 25 < current.get('rsi_14', 50) < 50:
                call_conditions += 1
                conditions_detail.append('rsi_bullish')
            
            if current.get('stoch_rsi_k', 50) < 80:
                call_conditions += 1
                conditions_detail.append('stoch_not_overbought')
            
            if current.get('price_vs_vwap', 0) > 0:
                call_conditions += 1
                conditions_detail.append('above_vwap')
            
            if current.get('price_vs_ema9', 0) > 0:
                call_conditions += 1
                conditions_detail.append('above_ema9')
            
            # PUT Signal Conditions
            put_conditions = 0
            put_conditions_detail = []
            
            if current.get('consecutive_down', 0) >= consecutive_periods:
                put_conditions += 1
                put_conditions_detail.append('consecutive_down')
            
            if 50 < current.get('rsi_14', 50) < 75:
                put_conditions += 1
                put_conditions_detail.append('rsi_bearish')
            
            if current.get('stoch_rsi_k', 50) > 20:
                put_conditions += 1
                put_conditions_detail.append('stoch_not_oversold')
            
            if current.get('price_vs_vwap', 0) < 0:
                put_conditions += 1
                put_conditions_detail.append('below_vwap')
            
            if current.get('price_vs_ema9', 0) < 0:
                put_conditions += 1
                put_conditions_detail.append('below_ema9')
            
            # Generate signal if enough conditions are met
            min_conditions = 3
            
            if call_conditions >= min_conditions:
                signal = 'CALL'
                signal_strength = call_conditions
                signal_conditions = conditions_detail
            elif put_conditions >= min_conditions:
                signal = 'PUT'
                signal_strength = put_conditions
                signal_conditions = put_conditions_detail
            
            if signal:
                # Look ahead for potential exit
                lookahead = min(20, len(df) - idx - 1)
                if lookahead > 0:
                    future_prices = df.iloc[idx+1:idx+1+lookahead]['Close'].values
                    
                    if len(future_prices) > 0:
                        if signal == 'CALL':
                            max_price = np.max(future_prices)
                            exit_idx = np.argmax(future_prices) + 1
                            return_pct = (max_price - current['Close']) / current['Close'] * 100
                            exit_price = max_price
                        else:  # PUT
                            min_price = np.min(future_prices)
                            exit_idx = np.argmin(future_prices) + 1
                            return_pct = (current['Close'] - min_price) / current['Close'] * 100
                            exit_price = min_price
                        
                        signal_data = {
                            'ticker': ticker,
                            'entry_date': df.index[idx],
                            'signal_type': signal,
                            'entry_price': current['Close'],
                            'entry_volume': current.get('Volume', 0),
                            'signal_strength': f"{signal_strength}/5",
                            'conditions_met': ', '.join(signal_conditions),
                            'entry_rsi': current.get('rsi_14', np.nan),
                            'entry_stoch_rsi_k': current.get('stoch_rsi_k', np.nan),
                            'entry_ema9': current.get('ema_9', np.nan),
                            'entry_ema21': current.get('ema_21', np.nan),
                            'entry_atr': current.get('atr_14', np.nan),
                            'exit_date': df.index[idx + exit_idx],
                            'exit_price': exit_price,
                            'duration_days': exit_idx,
                            'return_pct': return_pct,
                            'profitable': return_pct > 0
                        }
                        
                        signals.append(signal_data)
        
        signals_df = pd.DataFrame(signals)
        if not signals_df.empty:
            print(f"    Generated {len(signals_df)} signals ({len(signals_df[signals_df['profitable']])} profitable)")
        else:
            print(f"    No signals generated")
        
        return signals_df
    
    def analyze_ticker_comprehensive(self, ticker, df=None):
        """Perform comprehensive analysis for a ticker."""
        if df is None:
            df = self.load_ticker_data(ticker)
        
        if df.empty:
            print(f"No data available for {ticker}")
            return None, None
        
        print(f"\n{'='*60}")
        print(f"{ticker} Comprehensive Analysis")
        print(f"{'='*60}")
        
        # Add enhanced indicators
        df = self.add_enhanced_indicators(df, ticker)
        
        # Generate trading signals
        signals_df = self.generate_trading_signals(df, ticker)
        
        # Store results
        self.market_data[ticker] = df
        self.signals[ticker] = signals_df
        
        # Print analysis summary
        self._print_analysis_summary(ticker, df, signals_df)
        
        return df, signals_df
    
    def _print_analysis_summary(self, ticker, df, signals_df):
        """Print comprehensive analysis summary."""
        # Basic statistics
        print(f"\nData Statistics:")
        print(f"  Date Range: {df.index.min().date()} to {df.index.max().date()}")
        print(f"  Total Trading Days: {len(df)}")
        
        # Get latest values
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        
        # Price Analysis
        print(f"\n{'='*40}")
        print(f"PRICE ANALYSIS")
        print(f"{'='*40}")
        print(f"  Current Price: ${latest['Close']:.2f}")
        print(f"  Previous Close: ${prev['Close']:.2f}")
        print(f"  Change: ${latest.get('price_change_dollar', 0):.2f} ({latest.get('price_change', 0):.2f}%)")
        print(f"  Day Range: ${latest['Low']:.2f} - ${latest['High']:.2f}")
        print(f"  Open: ${latest['Open']:.2f}")
        
        if 'Volume' in df.columns:
            print(f"  Volume: {latest['Volume']:,.0f}")
            if 'rvol' in df.columns and not pd.isna(latest['rvol']):
                print(f"  RVOL: {latest['rvol']:.2f}x")
            if 'dollar_volume' in df.columns:
                print(f"  Dollar Volume: ${latest['dollar_volume']:,.0f}")
        
        # Historical ranges
        if len(df) >= 5:
            print(f"\n  5-Day Range: ${df['Low'].tail(5).min():.2f} - ${df['High'].tail(5).max():.2f}")
            print(f"  5-Day Return: {((latest['Close'] / df['Close'].iloc[-5]) - 1) * 100:.2f}%")
        
        if len(df) >= 20:
            print(f"  20-Day Range: ${df['Low'].tail(20).min():.2f} - ${df['High'].tail(20).max():.2f}")
            print(f"  20-Day Return: {((latest['Close'] / df['Close'].iloc[-20]) - 1) * 100:.2f}%")
        
        if 'high_52w' in df.columns and not pd.isna(latest['high_52w']):
            print(f"\n  52-Week High: ${latest['high_52w']:.2f}")
            print(f"  52-Week Low: ${latest['low_52w']:.2f}")
            print(f"  % from 52W High: {latest['pct_from_52w_high']:.2f}%")
            print(f"  % from 52W Low: {latest['pct_from_52w_low']:.2f}%")
        
        # Technical Indicators
        print(f"\n{'='*40}")
        print(f"TECHNICAL INDICATORS")
        print(f"{'='*40}")
        
        # Momentum Indicators
        print(f"\nMomentum:")
        if not pd.isna(latest.get('rsi_14')):
            rsi_val = latest['rsi_14']
            rsi_status = "Overbought" if rsi_val > 70 else "Oversold" if rsi_val < 30 else "Neutral"
            print(f"  RSI(14): {rsi_val:.2f} ({rsi_status})")
        if not pd.isna(latest.get('rsi_9')):
            print(f"  RSI(9): {latest['rsi_9']:.2f}")
        
        if not pd.isna(latest.get('stoch_k')):
            print(f"  Stochastic %K: {latest['stoch_k']:.2f}")
            print(f"  Stochastic %D: {latest['stoch_d']:.2f}")
        
        if not pd.isna(latest.get('stoch_rsi_k')):
            print(f"  Stochastic RSI K: {latest['stoch_rsi_k']:.2f}")
            print(f"  Stochastic RSI D: {latest['stoch_rsi_d']:.2f}")
        
        if not pd.isna(latest.get('macd')):
            print(f"\n  MACD: {latest['macd']:.4f}")
            print(f"  MACD Signal: {latest['macd_signal']:.4f}")
            print(f"  MACD Histogram: {latest['macd_histogram']:.4f}")
        
        # Moving Averages
        print(f"\nMoving Averages:")
        for ma in ['sma_5', 'sma_10', 'sma_20', 'sma_50', 'sma_200']:
            if ma in df.columns and not pd.isna(latest[ma]):
                ma_val = latest[ma]
                position = "Above" if latest['Close'] > ma_val else "Below"
                print(f"  {ma.upper().replace('_', '')}:  ${ma_val:.2f} ({position})")
        
        print(f"\nExponential MAs:")
        for ema in ['ema_9', 'ema_21', 'ema_50']:
            if ema in df.columns and not pd.isna(latest[ema]):
                ema_val = latest[ema]
                position = "Above" if latest['Close'] > ema_val else "Below"
                print(f"  {ema.upper().replace('_', '')}:  ${ema_val:.2f} ({position})")
        
        # Volatility
        print(f"\nVolatility:")
        if not pd.isna(latest.get('atr_14')):
            print(f"  ATR(14): ${latest['atr_14']:.2f}")
            print(f"  ATR %: {latest.get('atr_percent', 0):.2f}%")
        
        if not pd.isna(latest.get('bb_upper')):
            print(f"\nBollinger Bands:")
            print(f"  Upper: ${latest['bb_upper']:.2f}")
            print(f"  Middle: ${latest['bb_middle']:.2f}")
            print(f"  Lower: ${latest['bb_lower']:.2f}")
            print(f"  Width: ${latest['bb_width']:.2f}")
            bb_position = latest.get('bb_percent', 0.5)
            bb_status = "Above Upper" if bb_position > 1 else "Below Lower" if bb_position < 0 else f"{bb_position*100:.1f}% in band"
            print(f"  Position: {bb_status}")
        
        # Support/Resistance
        if not pd.isna(latest.get('support_1')):
            print(f"\nSupport/Resistance:")
            print(f"  Support: ${latest['support_1']:.2f}")
            print(f"  Resistance: ${latest['resistance_1']:.2f}")
            print(f"  Pivot: ${latest['pivot']:.2f}")
        
        # VWAP
        if 'vwap' in df.columns and not pd.isna(latest.get('vwap')):
            print(f"\nVWAP: ${latest['vwap']:.2f}")
            print(f"  Price vs VWAP: {latest.get('price_vs_vwap', 0):.2f}%")
        
        # Price Position
        print(f"\nPrice Position:")
        for col in ['price_vs_sma20', 'price_vs_sma50', 'price_vs_ema9', 'price_vs_ema21']:
            if col in df.columns and not pd.isna(latest.get(col)):
                indicator = col.replace('price_vs_', '').upper()
                print(f"  vs {indicator}: {latest[col]:+.2f}%")
        
        # Pattern Detection
        if not pd.isna(latest.get('consecutive_up')):
            print(f"\nPattern Detection:")
            print(f"  Consecutive Up Days: {int(latest['consecutive_up'])}")
            print(f"  Consecutive Down Days: {int(latest['consecutive_down'])}")
        
        if not pd.isna(latest.get('gap_percent')):
            print(f"  Gap: {latest['gap_percent']:.2f}%")
        
        if not pd.isna(latest.get('close_vs_range')):
            print(f"  Close Position in Range: {latest['close_vs_range']*100:.1f}%")
        
        # Signal analysis
        if not signals_df.empty:
            print(f"\nSignal Analysis:")
            print(f"  Total Signals: {len(signals_df)}")
            print(f"  CALL Signals: {len(signals_df[signals_df['signal_type'] == 'CALL'])}")
            print(f"  PUT Signals: {len(signals_df[signals_df['signal_type'] == 'PUT'])}")
            print(f"  Profitable: {len(signals_df[signals_df['profitable']])} ({len(signals_df[signals_df['profitable']])/len(signals_df)*100:.1f}%)")
            print(f"  Average Return: {signals_df['return_pct'].mean():.2f}%")
            print(f"  Best Return: {signals_df['return_pct'].max():.2f}%")
            print(f"  Worst Return: {signals_df['return_pct'].min():.2f}%")
            
            # Recent signals
            recent_signals = signals_df.tail(5)
            if not recent_signals.empty:
                print(f"\nRecent Signals (Last 5):")
                for _, sig in recent_signals.iterrows():
                    print(f"  {sig['entry_date'].date()}: {sig['signal_type']} @ ${sig['entry_price']:.2f} "
                          f"→ {sig['return_pct']:.2f}% ({sig['signal_strength']})")
    
    def compare_all_tickers(self):
        """Compare performance and signals across all tickers."""
        print(f"\n{'='*60}")
        print("Market-Wide Comparison")
        print(f"{'='*60}")
        
        comparison = []
        
        for ticker in self.tickers:
            df = self.market_data.get(ticker)
            signals = self.signals.get(ticker)
            
            if df is None or df.empty:
                continue
            
            latest = df.iloc[-1]
            stats = {
                'Ticker': ticker,
                'Last Close': latest['Close'],
                '1D Return': ((latest['Close'] / df['Close'].iloc[-2]) - 1) * 100 if len(df) >= 2 else 0,
                '5D Return': ((latest['Close'] / df['Close'].iloc[-5]) - 1) * 100 if len(df) >= 5 else 0,
                'RSI': latest.get('rsi_14', np.nan),
                'Signals': len(signals) if signals is not None else 0,
                'Win Rate': (len(signals[signals['profitable']]) / len(signals) * 100) if signals is not None and len(signals) > 0 else 0
            }
            comparison.append(stats)
        
        if comparison:
            comp_df = pd.DataFrame(comparison)
            print("\nPerformance Comparison:")
            print(comp_df.to_string(index=False, float_format=lambda x: f'{x:.2f}' if pd.notna(x) else 'N/A'))
    
    def export_signals(self, output_dir="data/signals"):
        """Export all signals to CSV files."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        for ticker, signals_df in self.signals.items():
            if signals_df is not None and not signals_df.empty:
                filename = output_path / f"{ticker.lower()}_signals.csv"
                signals_df.to_csv(filename, index=False)
                print(f"Exported {ticker} signals to {filename}")
    
    def run_full_analysis(self, export=False):
        """Run comprehensive analysis for all tickers."""
        print("Starting comprehensive market analysis...")
        print(f"Analyzing tickers: {', '.join(self.tickers)}")
        
        # Load all data
        self.load_all_market_data()
        
        # Analyze each ticker
        for ticker in self.tickers:
            df = self.market_data.get(ticker)
            if df is not None:
                self.analyze_ticker_comprehensive(ticker, df)
        
        # Compare all tickers
        self.compare_all_tickers()
        
        # Export if requested
        if export:
            self.export_signals()
            print("\nSignals exported successfully!")
        
        return self.market_data, self.signals


def main():
    """Main function with CLI interface."""
    parser = argparse.ArgumentParser(description='Enhanced market data analyzer with signal generation')
    parser.add_argument('--ticker', choices=['IWM', 'SPY', 'QQQ', 'SPX', 'ALL'], 
                       default='ALL', help='Analyze specific ticker or all')
    parser.add_argument('--export', action='store_true', 
                       help='Export signals to CSV files')
    parser.add_argument('--signals-only', action='store_true',
                       help='Show only signal analysis')
    parser.add_argument('--compare', action='store_true',
                       help='Show comparison across all tickers')
    parser.add_argument('--target-date', type=str, 
                       help='Target date for analysis (YYYY-MM-DD)')
    parser.add_argument('--start-date', type=str, 
                       help='Start date for range analysis (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, 
                       help='End date for range analysis (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    analyzer = MarketAnalyzer()
    
    # Add date filtering if specified
    if args.target_date or (args.start_date and args.end_date):
        print(f"Date filtering enabled:")
        if args.target_date:
            print(f"  Target date: {args.target_date}")
        if args.start_date and args.end_date:
            print(f"  Date range: {args.start_date} to {args.end_date}")
    
    if args.ticker == 'ALL':
        # Analyze all tickers
        analyzer.run_full_analysis(export=args.export)
    else:
        # Analyze specific ticker
        df, signals = analyzer.analyze_ticker_comprehensive(args.ticker)
        
        if args.export and signals is not None and not signals.empty:
            output_dir = Path("data/signals")
            output_dir.mkdir(exist_ok=True)
            filename = output_dir / f"{args.ticker.lower()}_signals.csv"
            signals.to_csv(filename, index=False)
            print(f"\nSignals exported to {filename}")
    
    if args.compare:
        analyzer.compare_all_tickers()
    
    print("\n" + "="*60)
    print("Analysis Complete!")
    print("="*60)


if __name__ == "__main__":
    main()