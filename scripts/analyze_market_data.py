#!/usr/bin/env python3
"""
Analyze market data stored in Parquet format for multiple tickers.
Provides various analysis functions for IWM, SPY, QQQ, and SPX data.
"""

import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import argparse
import json

def load_ticker_data(ticker):
    """Load all data for a specific ticker from Parquet files."""
    data_dir = Path("data")
    all_data = []
    
    # Handle SPX special case (stored as SPX but ticker is ^GSPC)
    file_pattern = f"{ticker.lower()}_*.parquet"
    
    for parquet_file in data_dir.glob(file_pattern):
        if not parquet_file.stem.endswith("_summary"):
            df = pd.read_parquet(parquet_file)
            all_data.append(df)
    
    if all_data:
        return pd.concat(all_data).sort_index()
    return pd.DataFrame()

def load_all_market_data():
    """Load data for all available tickers."""
    tickers = ['IWM', 'SPY', 'QQQ', 'SPX']
    market_data = {}
    
    for ticker in tickers:
        df = load_ticker_data(ticker)
        if not df.empty:
            market_data[ticker] = df
    
    return market_data

def analyze_ticker_performance(ticker, df=None):
    """Analyze performance metrics for a specific ticker."""
    if df is None:
        df = load_ticker_data(ticker)
    
    if df.empty:
        print(f"No data available for {ticker}")
        return
    
    print("=" * 60)
    print(f"{ticker} Performance Analysis")
    print("=" * 60)
    
    # Basic statistics
    print(f"\nData Range: {df.index.min().date()} to {df.index.max().date()}")
    print(f"Total Trading Days: {len(df)}")
    
    # Price statistics
    print(f"\nPrice Statistics:")
    print(f"  Current Price: ${df['Close'].iloc[-1]:.2f}")
    print(f"  52-Week High: ${df['Close'].tail(252).max():.2f}" if len(df) >= 252 else f"  High: ${df['Close'].max():.2f}")
    print(f"  52-Week Low: ${df['Close'].tail(252).min():.2f}" if len(df) >= 252 else f"  Low: ${df['Close'].min():.2f}")
    
    # Returns
    if 'daily_return' in df.columns:
        print(f"\nReturn Metrics:")
        print(f"  Daily Return (avg): {df['daily_return'].mean() * 100:.3f}%")
        print(f"  Daily Volatility: {df['daily_return'].std() * 100:.3f}%")
        print(f"  Annualized Volatility: {df['daily_return'].std() * (252 ** 0.5) * 100:.2f}%")
        
        # Sharpe Ratio (assuming 0% risk-free rate for simplicity)
        if df['daily_return'].std() > 0:
            sharpe = (df['daily_return'].mean() / df['daily_return'].std()) * (252 ** 0.5)
            print(f"  Sharpe Ratio: {sharpe:.2f}")
    
    # Volume analysis
    print(f"\nVolume Analysis:")
    print(f"  Average Daily Volume: {df['Volume'].mean():,.0f}")
    if 'volume_usd' in df.columns:
        print(f"  Average Dollar Volume: ${df['volume_usd'].mean():,.0f}")
    
    # Recent performance
    if len(df) >= 5:
        print(f"\nRecent Performance:")
        print(f"  5-Day Return: {((df['Close'].iloc[-1] / df['Close'].iloc[-5]) - 1) * 100:.2f}%")
    if len(df) >= 20:
        print(f"  20-Day Return: {((df['Close'].iloc[-1] / df['Close'].iloc[-20]) - 1) * 100:.2f}%")
    if len(df) >= 252:
        print(f"  1-Year Return: {((df['Close'].iloc[-1] / df['Close'].iloc[-252]) - 1) * 100:.2f}%")
    
    # Technical indicators
    if 'ma_20' in df.columns and 'ma_50' in df.columns:
        print(f"\nTechnical Indicators (Latest):")
        latest = df.iloc[-1]
        if pd.notna(latest['ma_20']):
            print(f"  Price vs MA(20): {((latest['Close'] / latest['ma_20']) - 1) * 100:.2f}%")
        if pd.notna(latest['ma_50']):
            print(f"  Price vs MA(50): {((latest['Close'] / latest['ma_50']) - 1) * 100:.2f}%")
        if 'rsi' in df.columns and pd.notna(latest['rsi']):
            print(f"  RSI(14): {latest['rsi']:.2f}")
        if 'rvol' in df.columns and pd.notna(latest['rvol']):
            print(f"  RVOL: {latest['rvol']:.2f}x")

def compare_tickers():
    """Compare performance across all available tickers."""
    market_data = load_all_market_data()
    
    if not market_data:
        print("No market data available for comparison")
        return
    
    print("=" * 60)
    print("Market Comparison Analysis")
    print("=" * 60)
    
    comparison = []
    
    for ticker, df in market_data.items():
        if df.empty or len(df) < 2:
            continue
            
        stats = {
            'Ticker': ticker,
            'Last Close': df['Close'].iloc[-1],
            '1D Return': ((df['Close'].iloc[-1] / df['Close'].iloc[-2]) - 1) * 100 if len(df) >= 2 else None,
            '5D Return': ((df['Close'].iloc[-1] / df['Close'].iloc[-5]) - 1) * 100 if len(df) >= 5 else None,
            '20D Return': ((df['Close'].iloc[-1] / df['Close'].iloc[-20]) - 1) * 100 if len(df) >= 20 else None,
            'Volatility': df['daily_return'].std() * (252 ** 0.5) * 100 if 'daily_return' in df.columns else None,
            'Latest RSI': df['rsi'].iloc[-1] if 'rsi' in df.columns and pd.notna(df['rsi'].iloc[-1]) else None
        }
        comparison.append(stats)
    
    if comparison:
        comp_df = pd.DataFrame(comparison)
        comp_df = comp_df.set_index('Ticker')
        
        print("\nPrice & Returns:")
        print(comp_df[['Last Close', '1D Return', '5D Return', '20D Return']].to_string(
            float_format=lambda x: f'{x:.2f}' if pd.notna(x) else 'N/A'
        ))
        
        print("\nRisk & Technical:")
        print(comp_df[['Volatility', 'Latest RSI']].to_string(
            float_format=lambda x: f'{x:.2f}' if pd.notna(x) else 'N/A'
        ))

def query_date_range(ticker, start_date, end_date):
    """Query market data for a specific ticker and date range."""
    df = load_ticker_data(ticker)
    
    if df.empty:
        print(f"No data available for {ticker}")
        return pd.DataFrame()
    
    mask = (df.index >= start_date) & (df.index <= end_date)
    result = df.loc[mask]
    
    print(f"Found {len(result)} records for {ticker} from {start_date} to {end_date}")
    return result

def export_to_csv(ticker=None, output_file=None):
    """Export market data to CSV format."""
    if ticker:
        df = load_ticker_data(ticker)
        if output_file is None:
            output_file = f"{ticker.lower()}_data.csv"
    else:
        # Export all tickers
        market_data = load_all_market_data()
        if not market_data:
            print("No data available for export")
            return
        
        for t, df in market_data.items():
            if not df.empty:
                file = f"{t.lower()}_data.csv"
                df.to_csv(file)
                print(f"Exported {t}: {len(df)} records to {file}")
        return
    
    if df.empty:
        print(f"No data available for {ticker}")
        return
    
    df.to_csv(output_file)
    print(f"Data exported to {output_file}")
    print(f"Total records: {len(df)}")

def correlation_analysis():
    """Analyze correlations between different tickers."""
    market_data = load_all_market_data()
    
    if len(market_data) < 2:
        print("Need at least 2 tickers for correlation analysis")
        return
    
    print("=" * 60)
    print("Correlation Analysis")
    print("=" * 60)
    
    # Align all dataframes and get returns
    returns = {}
    for ticker, df in market_data.items():
        if 'daily_return' in df.columns:
            returns[ticker] = df['daily_return']
    
    if len(returns) < 2:
        print("Insufficient return data for correlation analysis")
        return
    
    # Create combined dataframe
    returns_df = pd.DataFrame(returns)
    
    # Calculate correlation matrix
    corr_matrix = returns_df.corr()
    
    print("\nDaily Return Correlations:")
    print(corr_matrix.to_string(float_format=lambda x: f'{x:.3f}'))
    
    # Price correlations
    prices = {}
    for ticker, df in market_data.items():
        prices[ticker] = df['Close']
    
    prices_df = pd.DataFrame(prices)
    price_corr = prices_df.corr()
    
    print("\nPrice Correlations:")
    print(price_corr.to_string(float_format=lambda x: f'{x:.3f}'))

def main():
    """Main function with CLI interface."""
    parser = argparse.ArgumentParser(description='Analyze market data for multiple tickers')
    parser.add_argument('--ticker', choices=['IWM', 'SPY', 'QQQ', 'SPX'], 
                       help='Analyze specific ticker')
    parser.add_argument('--compare', action='store_true', 
                       help='Compare all tickers')
    parser.add_argument('--correlations', action='store_true',
                       help='Show correlation analysis')
    parser.add_argument('--export', nargs='?', const='all', 
                       help='Export to CSV (optionally specify ticker)')
    parser.add_argument('--days', type=int, default=30,
                       help='Number of days for recent data query (default: 30)')
    
    args = parser.parse_args()
    
    if args.export:
        if args.export == 'all':
            export_to_csv()
        else:
            export_to_csv(args.export.upper())
    elif args.compare:
        compare_tickers()
    elif args.correlations:
        correlation_analysis()
    elif args.ticker:
        analyze_ticker_performance(args.ticker)
        
        # Also show recent data
        print("\n" + "=" * 60)
        print(f"Last {args.days} Days Data Sample:")
        print("=" * 60)
        end = datetime.now()
        start = end - timedelta(days=args.days)
        recent_data = query_date_range(args.ticker, start, end)
        if not recent_data.empty:
            cols_to_show = ['Close', 'Volume']
            if 'daily_return' in recent_data.columns:
                cols_to_show.append('daily_return')
            if 'rsi' in recent_data.columns:
                cols_to_show.append('rsi')
            print(recent_data[cols_to_show].tail(10))
    else:
        # Default: analyze all tickers
        market_data = load_all_market_data()
        for ticker in market_data.keys():
            analyze_ticker_performance(ticker, market_data[ticker])
            print()

if __name__ == "__main__":
    main()