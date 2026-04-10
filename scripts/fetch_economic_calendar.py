#!/usr/bin/env python3
"""
Fetch economic calendar data from various sources.
This script fetches upcoming economic events and market data for ML model training.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import requests
from pathlib import Path
import requests as _requests_lib
import os
import warnings
warnings.filterwarnings('ignore')

# Try to import fredapi, but make it optional
try:
    from fredapi import Fred
    FRED_AVAILABLE = True
except ImportError:
    FRED_AVAILABLE = False
    print("Warning: fredapi not installed. Install with: pip install fredapi")


class EconomicCalendarFetcher:
    """Fetch and process economic calendar data from multiple sources."""
    
    def __init__(self):
        self.data_dir = Path("data")
        self.events_file = self.data_dir / "economic_events" / "market_events.json"
        self.ml_features_file = self.data_dir / "ml_features.csv"
        self.fred_api_key = os.environ.get('FRED_API_KEY')
        self.fred_client = None

        # Initialize FRED client if API key is available
        if self.fred_api_key and FRED_AVAILABLE:
            try:
                self.fred_client = Fred(api_key=self.fred_api_key)
                print("FRED API client initialized successfully")
            except Exception as e:
                print(f"Warning: Could not initialize FRED client: {e}")
        elif not self.fred_api_key:
            print("Warning: FRED_API_KEY not found in environment variables")

    def fetch_fred_data(self, start_date='2024-01-01', end_date=None):
        """
        Fetch economic indicators from FRED (Federal Reserve Economic Data).
        Requires FRED_API_KEY environment variable.

        Args:
            start_date: Start date for data fetch (YYYY-MM-DD)
            end_date: End date for data fetch (defaults to today)

        Returns:
            DataFrame with FRED economic indicators
        """
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')

        # FRED indicators to track
        indicators = {
            'DFF': 'Federal Funds Rate',
            'UNRATE': 'Unemployment Rate',
            'CPIAUCSL': 'Consumer Price Index',
            'GDP': 'Gross Domestic Product',
            'DEXUSEU': 'USD/EUR Exchange Rate',
            'DGS10': '10-Year Treasury Rate',
            'DGS2': '2-Year Treasury Rate',
            'VIXCLS': 'VIX Volatility Index',
            'DCOILWTICO': 'WTI Crude Oil Price',
            'GOLDAMGBD228NLBM': 'Gold Price'
        }

        # If FRED client is available, fetch real data
        if self.fred_client:
            print(f"Fetching FRED data from {start_date} to {end_date}...")
            fred_series = {}

            for series_id, description in indicators.items():
                try:
                    data = self.fred_client.get_series(
                        series_id,
                        observation_start=start_date,
                        observation_end=end_date
                    )
                    fred_series[series_id] = data
                    print(f"  ✓ Fetched {description} ({series_id}): {len(data)} observations")
                except Exception as e:
                    print(f"  ✗ Error fetching {description} ({series_id}): {e}")

            # Combine all series into a single DataFrame
            if fred_series:
                fred_df = pd.DataFrame(fred_series)
                fred_df.index.name = 'date'
                fred_df = fred_df.reset_index()

                # Rename columns to more readable names
                column_mapping = {
                    'DFF': 'fed_funds_rate',
                    'UNRATE': 'unemployment_rate',
                    'CPIAUCSL': 'cpi',
                    'GDP': 'gdp',
                    'DEXUSEU': 'usd_eur',
                    'DGS10': 'treasury_10y',
                    'DGS2': 'treasury_2y',
                    'VIXCLS': 'vix',
                    'DCOILWTICO': 'oil_price',
                    'GOLDAMGBD228NLBM': 'gold_price'
                }
                fred_df = fred_df.rename(columns=column_mapping)

                # Forward fill missing values (FRED data has gaps)
                fred_df = fred_df.ffill()

                # Save to file
                fred_file = self.data_dir / "fred_economic_data.csv"
                fred_df.to_csv(fred_file, index=False)
                print(f"\nSaved FRED data to {fred_file} ({len(fred_df)} rows)")

                return fred_df

        # Fallback: return sample data if FRED API is not available
        print("Warning: Using sample data (FRED API not available)")
        fred_data = {
            'date': pd.date_range(start=start_date, end=end_date, freq='D'),
            'fed_funds_rate': np.random.uniform(4.5, 5.5, len(pd.date_range(start=start_date, end=end_date, freq='D'))),
            'unemployment_rate': np.random.uniform(3.5, 4.5, len(pd.date_range(start=start_date, end=end_date, freq='D'))),
            'cpi': np.random.uniform(2.0, 3.0, len(pd.date_range(start=start_date, end=end_date, freq='D'))),
            'gdp': np.random.uniform(1.5, 3.0, len(pd.date_range(start=start_date, end=end_date, freq='D'))),
            'usd_eur': np.random.uniform(0.9, 1.1, len(pd.date_range(start=start_date, end=end_date, freq='D'))),
            'treasury_10y': np.random.uniform(3.5, 4.5, len(pd.date_range(start=start_date, end=end_date, freq='D'))),
            'treasury_2y': np.random.uniform(3.0, 4.0, len(pd.date_range(start=start_date, end=end_date, freq='D'))),
            'vix': np.random.uniform(12, 25, len(pd.date_range(start=start_date, end=end_date, freq='D'))),
            'oil_price': np.random.uniform(70, 90, len(pd.date_range(start=start_date, end=end_date, freq='D'))),
            'gold_price': np.random.uniform(1900, 2100, len(pd.date_range(start=start_date, end=end_date, freq='D')))
        }

        return pd.DataFrame(fred_data)
    
    def fetch_market_data(self, tickers=['SPY', 'QQQ', 'IWM', 'DIA', 'TLT', 'GLD', 'USO']):
        """Fetch market data for correlation analysis via AlphaVantage."""
        import os
        from dotenv import load_dotenv
        load_dotenv()
        av_key = os.environ.get('AV_API_KEY') or os.environ.get('ALPHA_VANTAGE_API_KEY', '')
        market_data = {}

        for ticker in tickers:
            try:
                params = {
                    'function': 'TIME_SERIES_DAILY_ADJUSTED',
                    'symbol': ticker,
                    'outputsize': 'full',
                    'datatype': 'json',
                    'apikey': av_key,
                }
                resp = _requests_lib.get('https://www.alphavantage.co/query', params=params, timeout=60)
                resp.raise_for_status()
                raw = resp.json()
                ts = raw.get('Time Series (Daily)', {})
                if not ts:
                    continue
                data = pd.DataFrame.from_dict(ts, orient='index')
                data = data.rename(columns={
                    '1. open': 'Open', '2. high': 'High', '3. low': 'Low',
                    '4. close': 'Close', '6. volume': 'Volume',
                })
                for col in ['Open', 'High', 'Low', 'Close']:
                    data[col] = pd.to_numeric(data[col])
                data['Volume'] = pd.to_numeric(data['Volume']).astype('int64')
                data.index = pd.to_datetime(data.index)
                data = data.sort_index()
                if not data.empty:
                    market_data[ticker] = {
                        'close': data['Close'],
                        'volume': data['Volume'],
                        'high': data['High'],
                        'low': data['Low'],
                        'open': data['Open']
                    }
                    print(f"Fetched data for {ticker}")
            except Exception as e:
                print(f"Error fetching {ticker}: {e}")
        
        return market_data
    
    def fetch_earnings_calendar(self):
        """Fetch major earnings releases that impact markets."""
        # Major companies that move markets
        major_earnings = [
            {'date': '2025-01-28', 'company': 'AAPL', 'market_cap': 'Large', 'sector': 'Technology'},
            {'date': '2025-01-30', 'company': 'MSFT', 'market_cap': 'Large', 'sector': 'Technology'},
            {'date': '2025-02-04', 'company': 'GOOGL', 'market_cap': 'Large', 'sector': 'Technology'},
            {'date': '2025-02-06', 'company': 'AMZN', 'market_cap': 'Large', 'sector': 'Technology'},
            {'date': '2025-01-23', 'company': 'TSLA', 'market_cap': 'Large', 'sector': 'Auto'},
            {'date': '2025-01-31', 'company': 'META', 'market_cap': 'Large', 'sector': 'Technology'},
            {'date': '2025-02-13', 'company': 'NVDA', 'market_cap': 'Large', 'sector': 'Technology'},
            {'date': '2025-01-17', 'company': 'JPM', 'market_cap': 'Large', 'sector': 'Financial'},
            {'date': '2025-01-15', 'company': 'BAC', 'market_cap': 'Large', 'sector': 'Financial'},
            {'date': '2025-01-16', 'company': 'GS', 'market_cap': 'Large', 'sector': 'Financial'},
        ]
        
        return pd.DataFrame(major_earnings)
    
    def calculate_market_regime(self, market_data):
        """Calculate market regime indicators."""
        spy_data = market_data.get('SPY', {}).get('close')
        
        if spy_data is not None and len(spy_data) > 0:
            # Calculate moving averages
            ma_20 = spy_data.rolling(window=20).mean()
            ma_50 = spy_data.rolling(window=50).mean()
            ma_200 = spy_data.rolling(window=200).mean()
            
            # Market regime classification
            regime = pd.Series(index=spy_data.index, dtype='object', data='Neutral')
            
            # Use .loc for proper indexing
            regime.loc[spy_data > ma_200] = 'Bull Market'
            regime.loc[spy_data < ma_200] = 'Bear Market'
            regime.loc[(spy_data > ma_50) & (spy_data < ma_200)] = 'Correction'
            regime.loc[(ma_20 > ma_50) & (ma_50 > ma_200)] = 'Strong Uptrend'
            regime.loc[(ma_20 < ma_50) & (ma_50 < ma_200)] = 'Strong Downtrend'
            
            return regime
        
        return pd.Series()
    
    def create_ml_features(self):
        """Create comprehensive features for ML model."""
        features = []
        
        # Load existing events from JSON
        if self.events_file.exists():
            events_df = pd.read_json(self.events_file, orient='records')
            events_df['date'] = pd.to_datetime(events_df['date'])
            
            # Create features for each day
            date_range = pd.date_range(start='2025-01-01', end='2025-12-31', freq='D')
            
            for date in date_range:
                feature_row = {
                    'date': date,
                    'day_of_week': date.dayofweek,
                    'day_of_month': date.day,
                    'month': date.month,
                    'quarter': (date.month - 1) // 3 + 1,
                    'is_month_start': date.day <= 5,
                    'is_month_end': date.day >= 25,
                    'is_quarter_end': (date.month % 3 == 0) and (date.day >= 25),
                    'is_friday': date.dayofweek == 4,
                    'is_monday': date.dayofweek == 0,
                    'is_opex': self._is_opex(date),  # Options expiration
                }
                
                # Check for events on this date
                day_events = events_df[events_df['date'] == date]
                
                feature_row['has_event'] = len(day_events) > 0
                feature_row['num_events'] = len(day_events)
                feature_row['has_cpi'] = any(day_events['event_type'] == 'CPI')
                feature_row['has_fomc'] = any(day_events['event_type'] == 'FOMC')
                feature_row['has_nfp'] = any(day_events['event_type'] == 'NFP')
                feature_row['has_gdp'] = any(day_events['event_type'] == 'GDP')
                feature_row['has_pce'] = any(day_events['event_type'] == 'PCE')
                
                # Days until next major event
                future_events = events_df[events_df['date'] > date]
                if not future_events.empty:
                    next_event = future_events.iloc[0]
                    feature_row['days_to_next_event'] = (next_event['date'] - date).days
                    feature_row['next_event_type'] = next_event['event_type']
                    feature_row['next_event_impact'] = self._encode_impact(next_event.get('expected_impact', 'Medium'))
                else:
                    feature_row['days_to_next_event'] = 999
                    feature_row['next_event_type'] = 'None'
                    feature_row['next_event_impact'] = 0
                
                # Days since last major event
                past_events = events_df[events_df['date'] < date]
                if not past_events.empty:
                    last_event = past_events.iloc[-1]
                    feature_row['days_since_last_event'] = (date - last_event['date']).days
                    feature_row['last_event_type'] = last_event['event_type']
                else:
                    feature_row['days_since_last_event'] = 999
                    feature_row['last_event_type'] = 'None'
                
                features.append(feature_row)
        
        features_df = pd.DataFrame(features)
        
        # Add technical calendar features
        features_df['is_january_effect'] = (features_df['month'] == 1)
        features_df['is_sell_in_may'] = features_df['month'].isin([5, 6, 7, 8, 9])
        features_df['is_santa_rally'] = (features_df['month'] == 12) & (features_df['day_of_month'] >= 15)
        features_df['is_window_dressing'] = (features_df['is_month_end'] | features_df['is_quarter_end'])
        
        return features_df
    
    def _is_opex(self, date):
        """Check if date is options expiration (3rd Friday of month)."""
        if date.dayofweek != 4:  # Not Friday
            return False
        
        # Find first Friday of the month
        first_day = date.replace(day=1)
        first_friday = first_day + timedelta(days=(4 - first_day.dayofweek) % 7)
        
        # Third Friday is 14 days after first Friday
        third_friday = first_friday + timedelta(days=14)
        
        return date == third_friday
    
    def _encode_impact(self, impact):
        """Encode impact level for ML models."""
        impact_map = {
            'Low': 1,
            'Low-Medium': 2,
            'Medium': 3,
            'High': 4,
            'Very High': 5,
            'Market Closed': 0
        }
        return impact_map.get(impact, 3)
    
    def fetch_sentiment_indicators(self):
        """Fetch market sentiment indicators."""
        # These would normally come from APIs
        sentiment_data = {
            'put_call_ratio': np.random.uniform(0.6, 1.4, 365),
            'aaii_bull_bear': np.random.uniform(-20, 40, 365),
            'fear_greed_index': np.random.uniform(20, 80, 365),
            'short_interest': np.random.uniform(15, 25, 365),
            'margin_debt_change': np.random.uniform(-5, 5, 365)
        }
        
        dates = pd.date_range(start='2025-01-01', end='2025-12-31', freq='D')
        sentiment_df = pd.DataFrame(sentiment_data, index=dates)
        
        return sentiment_df
    
    def create_combined_dataset(self):
        """Combine all data sources into a comprehensive dataset."""
        print("Creating combined ML dataset...")
        
        # Create ML features
        features_df = self.create_ml_features()
        features_df.set_index('date', inplace=True)
        
        # Fetch market data
        print("Fetching market data...")
        market_data = self.fetch_market_data()
        
        # Calculate market regime
        if market_data:
            regime = self.calculate_market_regime(market_data)
            if not regime.empty:
                features_df['market_regime'] = regime
        
        # Fetch sentiment indicators
        print("Fetching sentiment indicators...")
        sentiment_df = self.fetch_sentiment_indicators()
        
        # Combine all features
        combined_df = features_df.join(sentiment_df, how='left')
        
        # Add lagged features
        for col in ['put_call_ratio', 'fear_greed_index']:
            if col in combined_df.columns:
                combined_df[f'{col}_lag1'] = combined_df[col].shift(1)
                combined_df[f'{col}_lag5'] = combined_df[col].shift(5)
                combined_df[f'{col}_ma5'] = combined_df[col].rolling(5).mean()
        
        # Save to file
        combined_df.to_csv(self.ml_features_file)
        print(f"Saved ML features to {self.ml_features_file}")
        
        return combined_df
    
    def print_data_summary(self, df):
        """Print summary of the fetched data."""
        print("\n" + "="*60)
        print("ML FEATURES DATASET SUMMARY")
        print("="*60)
        
        print(f"\nDataset Shape: {df.shape}")
        print(f"Date Range: {df.index.min()} to {df.index.max()}")
        
        print("\nFeature Categories:")
        print(f"  Calendar Features: {sum(1 for col in df.columns if 'day' in col or 'month' in col or 'quarter' in col)}")
        print(f"  Event Features: {sum(1 for col in df.columns if 'event' in col or 'has_' in col.lower())}")
        print(f"  Sentiment Features: {sum(1 for col in df.columns if 'sentiment' in col.lower() or 'fear' in col or 'put_call' in col)}")
        print(f"  Market Regime Features: {sum(1 for col in df.columns if 'regime' in col.lower())}")
        
        # Event statistics
        if 'has_event' in df.columns:
            print(f"\nEvent Statistics:")
            print(f"  Days with events: {df['has_event'].sum()}")
            print(f"  Days with CPI: {df['has_cpi'].sum() if 'has_cpi' in df.columns else 0}")
            print(f"  Days with FOMC: {df['has_fomc'].sum() if 'has_fomc' in df.columns else 0}")
            print(f"  Days with NFP: {df['has_nfp'].sum() if 'has_nfp' in df.columns else 0}")
        
        print("\nSample of features:")
        print(df.head(3).T)


def main():
    """Main function to fetch and process economic calendar data."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Economic Calendar Data Fetcher')
    parser.add_argument('--target-date', type=str, help='Target date for analysis (YYYY-MM-DD)')
    parser.add_argument('--start-date', type=str, help='Start date for range analysis (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='End date for range analysis (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    fetcher = EconomicCalendarFetcher()
    
    # Create combined dataset
    combined_df = fetcher.create_combined_dataset()
    
    # Print summary
    fetcher.print_data_summary(combined_df)
    
    # Fetch earnings calendar
    earnings_df = fetcher.fetch_earnings_calendar()
    print(f"\n\nFetched {len(earnings_df)} major earnings events")
    
    print("\n" + "="*60)
    print("Economic Calendar Data Fetcher Complete!")
    print("="*60)
    print(f"\nGenerated files:")
    print(f"  - {fetcher.ml_features_file}")
    print(f"  - Ready for ML model training")


if __name__ == "__main__":
    main()