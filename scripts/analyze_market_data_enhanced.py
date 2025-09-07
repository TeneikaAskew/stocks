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
    
    def add_enhanced_indicators(self, df, ticker):
        """Add comprehensive technical indicators to dataframe."""
        print(f"  Calculating enhanced indicators for {ticker}...")
        
        # Ensure we have the necessary columns
        if 'Close' not in df.columns:
            print(f"    Warning: No Close price data for {ticker}")
            return df
        
        # Price changes
        df['price_change'] = df['Close'].pct_change() * 100
        df['price_ma3'] = df['price_change'].rolling(3).mean()
        
        # Consecutive movement detection
        df['up_move'] = df['price_change'] > 0
        df['down_move'] = df['price_change'] < 0
        df['consecutive_up'] = df['up_move'].rolling(3).sum()
        df['consecutive_down'] = df['down_move'].rolling(3).sum()
        
        # Enhanced technical indicators
        if 'rsi_14' in df.columns:
            # Calculate Stochastic RSI
            df['stoch_rsi_k'], df['stoch_rsi_d'] = self.calculate_stoch_rsi(df['rsi_14'])
        
        # VWAP approximation (using daily data)
        # For true VWAP, we'd need minute data
        df['typical_price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['tpv'] = df['typical_price'] * df['Volume']
        df['vwap_approx'] = df['tpv'].cumsum() / df['Volume'].cumsum()
        
        # Price position relative to indicators
        if 'ema_9' in df.columns:
            df['price_vs_ema9'] = (df['Close'] / df['ema_9'] - 1) * 100
        if 'ema_21' in df.columns:
            df['price_vs_ema21'] = (df['Close'] / df['ema_21'] - 1) * 100
        if 'vwap_approx' in df.columns:
            df['price_vs_vwap'] = (df['Close'] / df['vwap_approx'] - 1) * 100
        
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
            
            if call_conditions >= min_conditions and call_conditions > put_conditions:
                signal = 'CALL'
                signal_strength = call_conditions
                signal_conditions = conditions_detail
            elif put_conditions >= min_conditions and put_conditions > call_conditions:
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
        
        # Price statistics
        latest = df.iloc[-1]
        print(f"\nPrice Analysis:")
        print(f"  Current Price: ${latest['Close']:.2f}")
        if len(df) >= 252:
            print(f"  52-Week High: ${df['Close'].tail(252).max():.2f}")
            print(f"  52-Week Low: ${df['Close'].tail(252).min():.2f}")
            year_return = (latest['Close'] / df['Close'].iloc[-252] - 1) * 100
            print(f"  1-Year Return: {year_return:.2f}%")
        
        # Technical indicators
        print(f"\nTechnical Indicators (Latest):")
        if 'rsi_14' in df.columns and not pd.isna(latest.get('rsi_14')):
            print(f"  RSI(14): {latest['rsi_14']:.2f}")
        if 'stoch_rsi_k' in df.columns and not pd.isna(latest.get('stoch_rsi_k')):
            print(f"  Stochastic RSI K: {latest['stoch_rsi_k']:.2f}")
        if 'rvol' in df.columns and not pd.isna(latest.get('rvol')):
            print(f"  RVOL: {latest['rvol']:.2f}x")
        if 'atr_14' in df.columns and not pd.isna(latest.get('atr_14')):
            print(f"  ATR(14): ${latest['atr_14']:.2f}")
        
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
    
    args = parser.parse_args()
    
    analyzer = MarketAnalyzer()
    
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