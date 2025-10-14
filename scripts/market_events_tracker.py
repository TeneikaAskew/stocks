#!/usr/bin/env python3
"""
Market events tracker for economic indicators and their impact on markets.
Tracks events like CPI, FOMC, NFP, GDP, and other market-moving events.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import requests
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')


class MarketEventsTracker:
    """Track and analyze economic events and their market impact."""
    
    def __init__(self):
        self.events_file = Path("data/market_events.json")
        self.events_archive_file = Path("data/market_events_archive.json")
        self.events_df = pd.DataFrame()
        self.initialize_event_types()
        
    def initialize_event_types(self):
        """Initialize the types of economic events we track."""
        self.event_types = {
            'CPI': {
                'name': 'Consumer Price Index',
                'frequency': 'Monthly',
                'impact': 'High',
                'typical_release_time': '08:30 ET',
                'market_reaction': 'Volatility in bonds, equities, and USD'
            },
            'FOMC': {
                'name': 'Federal Open Market Committee Meeting',
                'frequency': '8 times per year',
                'impact': 'Very High',
                'typical_release_time': '14:00 ET',
                'market_reaction': 'Major moves in all markets'
            },
            'NFP': {
                'name': 'Non-Farm Payrolls',
                'frequency': 'Monthly',
                'impact': 'High',
                'typical_release_time': '08:30 ET',
                'market_reaction': 'Significant equity and bond moves'
            },
            'GDP': {
                'name': 'Gross Domestic Product',
                'frequency': 'Quarterly',
                'impact': 'High',
                'typical_release_time': '08:30 ET',
                'market_reaction': 'Broad market impact'
            },
            'PCE': {
                'name': 'Personal Consumption Expenditures',
                'frequency': 'Monthly',
                'impact': 'High',
                'typical_release_time': '08:30 ET',
                'market_reaction': 'Fed preferred inflation measure'
            },
            'RETAIL_SALES': {
                'name': 'Retail Sales',
                'frequency': 'Monthly',
                'impact': 'Medium',
                'typical_release_time': '08:30 ET',
                'market_reaction': 'Consumer sector stocks'
            },
            'ISM_PMI': {
                'name': 'ISM Manufacturing PMI',
                'frequency': 'Monthly',
                'impact': 'Medium',
                'typical_release_time': '10:00 ET',
                'market_reaction': 'Manufacturing and industrial sectors'
            },
            'HOUSING_STARTS': {
                'name': 'Housing Starts',
                'frequency': 'Monthly',
                'impact': 'Medium',
                'typical_release_time': '08:30 ET',
                'market_reaction': 'Housing and construction sectors'
            },
            'JOBLESS_CLAIMS': {
                'name': 'Initial Jobless Claims',
                'frequency': 'Weekly',
                'impact': 'Low-Medium',
                'typical_release_time': '08:30 ET',
                'market_reaction': 'Short-term volatility'
            },
            'EARNINGS': {
                'name': 'Major Earnings Releases',
                'frequency': 'Quarterly',
                'impact': 'Variable',
                'typical_release_time': 'Before/After Market',
                'market_reaction': 'Sector and index impacts'
            }
        }
        
    def fetch_fred_releases(self, start_date=None, end_date=None):
        """Fetch economic events from FRED releases/dates API."""
        import os

        fred_api_key = os.environ.get('FRED_API_KEY')
        if not fred_api_key:
            print("Warning: FRED_API_KEY not found in environment variables")
            return pd.DataFrame()

        # Default date range: 2024-01-01 to 2026-12-31
        if not start_date:
            start_date = '2024-01-01'
        if not end_date:
            end_date = '2026-12-31'

        url = 'https://api.stlouisfed.org/fred/releases/dates'
        params = {
            'api_key': fred_api_key,
            'file_type': 'json',
            'realtime_start': start_date,
            'realtime_end': end_date,
            'limit': 10000  # Get all events in range
        }

        try:
            print(f"Fetching FRED releases from {start_date} to {end_date}...")
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if 'release_dates' not in data:
                print("Warning: No release_dates in FRED API response")
                return pd.DataFrame()

            events = []
            for release in data['release_dates']:
                # Auto-classify event type based on release name
                event_type, expected_impact = self._classify_fred_event(release['release_name'])

                events.append({
                    'date': release['date'],
                    'event_type': event_type,
                    'event': release['release_name'],
                    'expected_impact': expected_impact,
                    'actual': None,
                    'consensus': None,
                    'notes': None,
                    'source': 'FRED'
                })

            print(f"Fetched {len(events)} events from FRED API")
            return pd.DataFrame(events)

        except requests.exceptions.RequestException as e:
            print(f"Error fetching from FRED API: {e}")
            return pd.DataFrame()

    def _classify_fred_event(self, release_name):
        """Classify FRED event type and impact level based on release name."""
        release_lower = release_name.lower()

        # Very High Impact Events
        if 'fomc' in release_lower or 'federal open market' in release_lower:
            return 'FOMC', 'Very High'

        # High Impact Events
        if 'consumer price index' in release_lower or 'cpi' in release_lower:
            return 'CPI', 'High'
        if 'employment situation' in release_lower or 'non-farm payroll' in release_lower or 'nonfarm payroll' in release_lower:
            return 'NFP', 'High'
        if 'gdp' in release_lower or 'gross domestic product' in release_lower:
            return 'GDP', 'High'
        if 'personal consumption expenditures' in release_lower or 'pce' in release_lower:
            return 'PCE', 'High'

        # Medium Impact Events
        if 'retail sales' in release_lower or 'advance retail' in release_lower:
            return 'RETAIL_SALES', 'Medium'
        if 'ism' in release_lower or 'pmi' in release_lower or 'purchasing managers' in release_lower:
            return 'ISM_PMI', 'Medium'
        if 'ppi' in release_lower or 'producer price' in release_lower:
            return 'PPI', 'Medium'
        if 'housing starts' in release_lower or 'building permits' in release_lower:
            return 'HOUSING_STARTS', 'Medium'
        if 'industrial production' in release_lower:
            return 'INDUSTRIAL_PRODUCTION', 'Medium'
        if 'durable goods' in release_lower:
            return 'DURABLE_GOODS', 'Medium'

        # Low-Medium Impact Events
        if 'jobless claims' in release_lower or 'unemployment insurance' in release_lower:
            return 'JOBLESS_CLAIMS', 'Low-Medium'
        if 'consumer sentiment' in release_lower or 'consumer confidence' in release_lower:
            return 'CONSUMER_SENTIMENT', 'Low-Medium'
        if 'trade balance' in release_lower or 'international trade' in release_lower:
            return 'TRADE_BALANCE', 'Low-Medium'

        # Default classification
        return 'OTHER', 'Low'

    def fetch_unusual_whales_trading_calendar(self, year=2025):
        """
        Fetch trading calendar from Unusual Whales API.
        This includes FOMC meetings, market holidays, OPEX dates, and major events.

        API: https://phx.unusualwhales.com/api/trading-calendar?month=X&year=YYYY
        """
        all_events = []

        try:
            print(f"Fetching Unusual Whales trading calendar for {year}...")

            # Fetch data for each month of the year
            # Add headers to avoid being blocked
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json',
            }

            for month in range(1, 13):
                url = f"https://phx.unusualwhales.com/api/trading-calendar?month={month}&year={year}"

                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()

                if not data or "data" not in data:
                    continue

                month_events = data["data"]

                for event_item in month_events:
                    # Parse event details
                    event_date = event_item.get('start_date')
                    if not event_date:
                        continue

                    event_name = event_item.get('event', 'Unknown Event')
                    event_type = event_item.get('event_type', '')
                    description = event_item.get('description', '')

                    # Classify event type and impact
                    classified_type, impact = self._classify_unusual_whales_event(event_name, event_type)

                    # Build event description
                    full_event_name = event_name
                    if description:
                        full_event_name = f"{event_name} - {description}"

                    all_events.append({
                        'date': event_date,
                        'event_type': classified_type,
                        'event': full_event_name,
                        'expected_impact': impact,
                        'actual': None,
                        'consensus': None,
                        'notes': event_item.get('link'),
                        'source': 'UnusualWhales'
                    })

            print(f"Fetched {len(all_events)} events from Unusual Whales trading calendar")
            return pd.DataFrame(all_events)

        except requests.exceptions.RequestException as e:
            print(f"Error fetching from Unusual Whales API: {e}")
            return pd.DataFrame()
        except Exception as e:
            print(f"Error parsing Unusual Whales data: {e}")
            return pd.DataFrame()

    def _classify_unusual_whales_event(self, event_name, event_type=''):
        """Classify event type from Unusual Whales event name and type."""
        event_lower = event_name.lower()
        type_lower = event_type.lower() if event_type else ''

        # Check event_type field first
        if type_lower == 'market_closed' or 'closed' in event_lower:
            return 'SPECIAL', 'Market Closed'
        if type_lower == 'opex' or 'opex' in event_lower:
            return 'OPEX', 'Medium'

        # Check event name
        if 'fomc' in event_lower:
            return 'FOMC', 'Very High'
        if 'cpi' in event_lower or 'consumer price' in event_lower:
            return 'CPI', 'High'
        if 'nfp' in event_lower or 'non-farm' in event_lower or 'payroll' in event_lower:
            return 'NFP', 'High'
        if 'gdp' in event_lower:
            return 'GDP', 'High'
        if 'pce' in event_lower:
            return 'PCE', 'High'
        if 'retail sales' in event_lower:
            return 'RETAIL_SALES', 'Medium'
        if 'earnings season' in event_lower:
            return 'EARNINGS_SEASON', 'Medium'
        if 'rebalance' in event_lower:
            return 'INDEX_REBALANCE', 'Medium'
        if 'earnings' in event_lower:
            return 'EARNINGS', 'Variable'

        return 'OTHER', 'Low'

    def get_market_holidays(self, year):
        """
        Get US market holidays and early closes for a given year using pandas-market-calendars.
        This fetches official NYSE holidays from the maintained library.
        Holidays are calculated as weekdays NOT in the trading schedule.
        """
        try:
            import pandas_market_calendars as mcal

            # Get NYSE calendar
            nyse = mcal.get_calendar('XNYS')

            # Get date range for the year
            start_date = f'{year}-01-01'
            end_date = f'{year}-12-31'

            # Get trading schedule (tz-aware index of trading days)
            schedule = nyse.schedule(start_date=start_date, end_date=end_date)

            # Calculate full-day holidays = weekdays NOT in the trading schedule
            trading_days = schedule.index.tz_localize(None)  # Strip timezone
            all_weekdays = pd.date_range(start_date, end_date, freq='B')  # Business days (Mon-Fri)
            holiday_dates = all_weekdays.difference(trading_days)  # Market closed weekdays

            # Get early closes
            early_closes = nyse.early_closes(schedule)
            if not early_closes.empty:
                early_closes.index = early_closes.index.tz_localize(None)  # Remove timezone

            # Convert holidays to our format
            holidays = []
            for holiday_date in holiday_dates:
                # Get the holiday name
                holiday_name = holiday_date.strftime('%Y-%m-%d')

                # Try to get a descriptive name
                date_obj = pd.to_datetime(holiday_date)
                month_day = date_obj.strftime('%m-%d')

                # Map common holidays to names
                holiday_names = {
                    '01-01': "New Year's Day",
                    '01-02': "New Year's Day (Observed)",
                    '07-03': "Independence Day (Observed)",
                    '07-04': "Independence Day",
                    '07-05': "Independence Day (Observed)",
                    '12-24': "Christmas (Observed)",
                    '12-25': "Christmas",
                    '12-26': "Christmas (Observed)",
                    '06-19': "Juneteenth",
                    '06-20': "Juneteenth (Observed)",
                }

                # Determine name based on date or day of week
                if month_day in holiday_names:
                    event_name = holiday_names[month_day]
                elif date_obj.month == 1 and date_obj.day > 14 and date_obj.day < 22:
                    event_name = "Martin Luther King Jr. Day"
                elif date_obj.month == 2 and date_obj.day > 14 and date_obj.day < 22:
                    event_name = "Presidents Day"
                elif date_obj.month == 5 and date_obj.day > 24:
                    event_name = "Memorial Day"
                elif date_obj.month == 9 and date_obj.day < 8:
                    event_name = "Labor Day"
                elif date_obj.month == 11 and date_obj.day > 21 and date_obj.day < 29:
                    event_name = "Thanksgiving"
                elif date_obj.month == 11 and date_obj.day == 29:
                    event_name = "Day after Thanksgiving (Early Close)"
                else:
                    event_name = "Market Holiday"

                holidays.append({
                    'date': holiday_date.strftime('%Y-%m-%d'),
                    'event_type': 'SPECIAL',
                    'event': f'{event_name} - Markets Closed',
                    'expected_impact': 'Market Closed',
                    'actual': None,
                    'consensus': None,
                    'notes': f'NYSE Holiday - {event_name}',
                    'source': 'NYSE'  # Fetched from pandas-market-calendars
                })

            # Add early closes
            if not early_closes.empty:
                for early_date, row in early_closes.iterrows():
                    close_time = row['market_close'].strftime('%I:%M %p') if 'market_close' in row else 'Early'

                    # Determine early close name
                    date_obj = pd.to_datetime(early_date)
                    if date_obj.month == 7:
                        early_name = "Independence Day"
                    elif date_obj.month == 11:
                        early_name = "Thanksgiving"
                    elif date_obj.month == 12:
                        early_name = "Christmas"
                    else:
                        early_name = "Market Holiday"

                    holidays.append({
                        'date': early_date.strftime('%Y-%m-%d'),
                        'event_type': 'SPECIAL',
                        'event': f'Early Close - {early_name} ({close_time})',
                        'expected_impact': 'Early Close',
                        'actual': None,
                        'consensus': None,
                        'notes': f'NYSE Early Close - Market closes at {close_time}',
                        'source': 'NYSE'
                    })

            print(f"  Fetched {len(holidays)} NYSE holidays/early closes for {year}")
            return holidays

        except ImportError:
            print(f"  Warning: pandas-market-calendars not installed. Install with: pip install pandas-market-calendars")
            print(f"  Falling back to empty holiday list for {year}")
            return []
        except Exception as e:
            print(f"  Error fetching NYSE holidays for {year}: {e}")
            print(f"  Falling back to empty holiday list")
            return []

    def get_official_2025_calendar(self):
        """
        Get official 2025 economic calendar from known government sources.
        These dates are from official schedules published by BLS, Federal Reserve, and BEA.
        Sources:
        - CPI: Bureau of Labor Statistics release schedule
        - FOMC: Federal Reserve meeting schedule
        - NFP: Bureau of Labor Statistics (first Friday of month)
        - GDP: Bureau of Economic Analysis release schedule
        - PCE: Bureau of Economic Analysis release schedule
        """
        events = [
            # CPI Releases (BLS Schedule)
            {'date': '2025-01-14', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-02-13', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-03-12', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-04-10', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-05-14', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-06-12', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-07-11', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-08-13', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-09-11', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-10-10', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-11-13', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-12-11', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},

            # FOMC Meetings (Federal Reserve Schedule)
            {'date': '2025-01-29', 'event_type': 'FOMC', 'event': 'FOMC Meeting & Decision', 'expected_impact': 'Very High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'Federal Reserve'},
            {'date': '2025-03-19', 'event_type': 'FOMC', 'event': 'FOMC Meeting & Decision', 'expected_impact': 'Very High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'Federal Reserve'},
            {'date': '2025-05-07', 'event_type': 'FOMC', 'event': 'FOMC Meeting & Decision', 'expected_impact': 'Very High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'Federal Reserve'},
            {'date': '2025-06-18', 'event_type': 'FOMC', 'event': 'FOMC Meeting & Decision', 'expected_impact': 'Very High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'Federal Reserve'},
            {'date': '2025-07-30', 'event_type': 'FOMC', 'event': 'FOMC Meeting & Decision', 'expected_impact': 'Very High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'Federal Reserve'},
            {'date': '2025-09-17', 'event_type': 'FOMC', 'event': 'FOMC Meeting & Decision', 'expected_impact': 'Very High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'Federal Reserve'},
            {'date': '2025-11-05', 'event_type': 'FOMC', 'event': 'FOMC Meeting & Decision', 'expected_impact': 'Very High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'Federal Reserve'},
            {'date': '2025-12-17', 'event_type': 'FOMC', 'event': 'FOMC Meeting & Decision', 'expected_impact': 'Very High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'Federal Reserve'},

            # NFP (First Friday of each month - BLS Schedule)
            {'date': '2025-01-10', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-02-07', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-03-07', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-04-04', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-05-02', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-06-06', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-07-03', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-08-01', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-09-05', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-10-03', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-11-07', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},
            {'date': '2025-12-05', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BLS'},

            # GDP (Quarterly - BEA Schedule)
            {'date': '2025-01-30', 'event_type': 'GDP', 'event': 'GDP Q4 2024 Advance', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-02-27', 'event_type': 'GDP', 'event': 'GDP Q4 2024 Second', 'expected_impact': 'Medium', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-03-27', 'event_type': 'GDP', 'event': 'GDP Q4 2024 Final', 'expected_impact': 'Low', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-04-30', 'event_type': 'GDP', 'event': 'GDP Q1 2025 Advance', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-05-29', 'event_type': 'GDP', 'event': 'GDP Q1 2025 Second', 'expected_impact': 'Medium', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-06-26', 'event_type': 'GDP', 'event': 'GDP Q1 2025 Final', 'expected_impact': 'Low', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-07-31', 'event_type': 'GDP', 'event': 'GDP Q2 2025 Advance', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-08-28', 'event_type': 'GDP', 'event': 'GDP Q2 2025 Second', 'expected_impact': 'Medium', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-09-26', 'event_type': 'GDP', 'event': 'GDP Q2 2025 Final', 'expected_impact': 'Low', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-10-30', 'event_type': 'GDP', 'event': 'GDP Q3 2025 Advance', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},

            # PCE (Monthly - BEA Schedule)
            {'date': '2025-01-31', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-02-28', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-03-28', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-04-30', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-05-30', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-06-27', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-07-31', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-08-29', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-09-26', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
            {'date': '2025-10-31', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None, 'notes': None, 'source': 'BEA'},
        ]

        return events

    def fetch_all_events(self, start_date=None, end_date=None):
        """Fetch events from all sources and combine them."""
        all_events = []

        # Add official 2025 calendar (backup for key economic events)
        calendar_2025 = self.get_official_2025_calendar()
        all_events.append(pd.DataFrame(calendar_2025))

        # Fetch from FRED (optional, requires API key)
        fred_events = self.fetch_fred_releases(start_date, end_date)
        if not fred_events.empty:
            all_events.append(fred_events)

        # Fetch from Unusual Whales trading calendar (2025)
        uw_events = self.fetch_unusual_whales_trading_calendar(year=2025)
        if not uw_events.empty:
            all_events.append(uw_events)

        # Add market holidays for 2024-2026 (backup)
        years = [2024, 2026]  # 2025 already covered by UW API
        for year in years:
            holidays = self.get_market_holidays(year)
            all_events.append(pd.DataFrame(holidays))

        if not all_events:
            print("Warning: No events fetched from any source")
            return pd.DataFrame()

        # Combine all events
        combined_df = pd.concat(all_events, ignore_index=True)
        combined_df['date'] = pd.to_datetime(combined_df['date'], errors='coerce')

        # Remove events with invalid dates (NaT)
        before_count = len(combined_df)
        combined_df = combined_df.dropna(subset=['date'])
        invalid_removed = before_count - len(combined_df)

        if invalid_removed > 0:
            print(f"Removed {invalid_removed} events with invalid dates")

        print(f"Combined {len(combined_df)} total events from all sources")
        return combined_df

    def merge_and_deduplicate_events(self, new_events_df):
        """Merge new events with existing events and remove duplicates."""
        if new_events_df.empty:
            print("No new events to merge")
            return

        # Load existing events
        existing_df = self.events_df if not self.events_df.empty else pd.DataFrame()

        if existing_df.empty:
            # No existing events, just use new ones
            self.events_df = new_events_df
            print(f"Initialized with {len(self.events_df)} new events")
            return

        # Combine existing and new events
        combined = pd.concat([existing_df, new_events_df], ignore_index=True)

        # Remove duplicates based on date + event name
        # Keep the first occurrence (existing events take precedence)
        before_count = len(combined)
        combined = combined.drop_duplicates(subset=['date', 'event'], keep='first')
        duplicates_removed = before_count - len(combined)

        # Sort by date
        combined = combined.sort_values('date').reset_index(drop=True)

        self.events_df = combined
        print(f"Merged events: {len(existing_df)} existing + {len(new_events_df)} new = {len(combined)} total ({duplicates_removed} duplicates removed)")

        return self.events_df
    
    def load_events(self, fetch_new=True, start_date=None, end_date=None):
        """Load existing events from file and optionally fetch new events from APIs."""
        # Load existing events from JSON if file exists
        if self.events_file.exists():
            self.events_df = pd.read_json(self.events_file, orient='records')
            self.events_df['date'] = pd.to_datetime(self.events_df['date'])
            print(f"Loaded {len(self.events_df)} existing events from JSON")
        else:
            self.events_df = pd.DataFrame()
            print("No existing events file found, will fetch from APIs")

        # Fetch new events from APIs and merge
        if fetch_new:
            print("\nFetching new events from APIs...")
            new_events = self.fetch_all_events(start_date, end_date)

            if not new_events.empty:
                self.merge_and_deduplicate_events(new_events)
                self.save_events()
            else:
                print("No new events fetched from APIs")

        return self.events_df

    def save_events(self):
        """Save events to JSON file, sorted by date."""
        # Sort by date before saving
        self.events_df = self.events_df.sort_values('date').reset_index(drop=True)

        # Convert datetime to string for JSON serialization
        events_to_save = self.events_df.copy()
        events_to_save['date'] = events_to_save['date'].dt.strftime('%Y-%m-%d')

        # Save as JSON
        events_to_save.to_json(self.events_file, orient='records', indent=2)
        print(f"Saved {len(self.events_df)} events to {self.events_file} (sorted by date)")
    
    def add_event(self, date, event_type, event, expected_impact='Medium', actual=None, consensus=None, notes=None):
        """Add a new event to the tracker."""
        new_event = {
            'date': pd.to_datetime(date),
            'event_type': event_type,
            'event': event,
            'expected_impact': expected_impact,
            'actual': actual,
            'consensus': consensus,
            'notes': notes,
            'added_timestamp': datetime.now()
        }
        
        self.events_df = pd.concat([self.events_df, pd.DataFrame([new_event])], ignore_index=True)
        self.save_events()
        return new_event
    
    def get_upcoming_events(self, days_ahead=30):
        """Get upcoming events within specified days."""
        today = pd.Timestamp.now().normalize()
        future_date = today + timedelta(days=days_ahead)
        
        upcoming = self.events_df[
            (self.events_df['date'] >= today) & 
            (self.events_df['date'] <= future_date)
        ].sort_values('date')
        
        return upcoming
    
    def get_events_by_type(self, event_type):
        """Get all events of a specific type."""
        return self.events_df[self.events_df['event_type'] == event_type].sort_values('date')
    
    def get_high_impact_events(self):
        """Get all high impact events."""
        high_impact = self.events_df[
            self.events_df['expected_impact'].isin(['High', 'Very High'])
        ].sort_values('date')
        return high_impact
    
    def get_events_for_date_range(self, start_date, end_date):
        """Get events within a specific date range."""
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        
        return self.events_df[
            (self.events_df['date'] >= start) & 
            (self.events_df['date'] <= end)
        ].sort_values('date')
    
    def analyze_event_impact(self, event_date, ticker_data):
        """Analyze market impact of an event using ticker data."""
        event_date = pd.to_datetime(event_date)
        
        # Get event details
        event = self.events_df[self.events_df['date'] == event_date]
        if event.empty:
            return None
        
        event = event.iloc[0]
        
        # Find the event in ticker data
        if event_date not in ticker_data.index:
            # Find nearest trading day
            nearest_idx = ticker_data.index.get_indexer([event_date], method='nearest')[0]
            event_date = ticker_data.index[nearest_idx]
        
        # Calculate impact metrics
        impact = {}
        
        # Day of event
        if event_date in ticker_data.index:
            day_of = ticker_data.loc[event_date]
            impact['event_day_return'] = day_of.get('price_change', 0)
            impact['event_day_volume'] = day_of.get('Volume', 0)
            impact['event_day_volatility'] = day_of.get('atr_percent', 0)
        
        # Day after event
        next_day_idx = ticker_data.index.get_loc(event_date) + 1
        if next_day_idx < len(ticker_data):
            next_day = ticker_data.iloc[next_day_idx]
            impact['next_day_return'] = next_day.get('price_change', 0)
        
        # Week after event
        week_after_idx = ticker_data.index.get_loc(event_date) + 5
        if week_after_idx < len(ticker_data):
            week_range = ticker_data.iloc[ticker_data.index.get_loc(event_date):week_after_idx+1]
            impact['week_after_return'] = ((week_range['Close'].iloc[-1] / week_range['Close'].iloc[0]) - 1) * 100
            impact['week_after_max_move'] = week_range['price_change'].abs().max()
        
        return impact
    
    def create_event_calendar_html(self, output_file='data/event_calendar.html'):
        """Create an HTML calendar view of events."""
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Economic Events Calendar 2025</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                h1 { color: #333; }
                table { border-collapse: collapse; width: 100%; margin-top: 20px; }
                th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
                th { background-color: #4CAF50; color: white; }
                tr:hover { background-color: #f5f5f5; }
                .high-impact { background-color: #ffebee; }
                .very-high-impact { background-color: #ffcdd2; }
                .market-closed { background-color: #e0e0e0; }
                .past-event { opacity: 0.6; }
                .legend { margin-top: 20px; }
                .legend-item { display: inline-block; margin-right: 20px; }
                .legend-color { display: inline-block; width: 20px; height: 20px; margin-right: 5px; vertical-align: middle; }
            </style>
        </head>
        <body>
            <h1>Economic Events Calendar 2025</h1>
            <div class="legend">
                <div class="legend-item"><span class="legend-color" style="background-color: #ffcdd2;"></span>Very High Impact</div>
                <div class="legend-item"><span class="legend-color" style="background-color: #ffebee;"></span>High Impact</div>
                <div class="legend-item"><span class="legend-color" style="background-color: #e0e0e0;"></span>Market Closed</div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Event Type</th>
                        <th>Event</th>
                        <th>Expected Impact</th>
                        <th>Consensus</th>
                        <th>Actual</th>
                        <th>Notes</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        today = pd.Timestamp.now().normalize()

        for _, event in self.events_df.sort_values('date').iterrows():
            # Skip events with invalid dates (NaT)
            if pd.isna(event['date']):
                continue

            row_class = []

            if event['expected_impact'] == 'Very High':
                row_class.append('very-high-impact')
            elif event['expected_impact'] == 'High':
                row_class.append('high-impact')
            elif event['expected_impact'] == 'Market Closed':
                row_class.append('market-closed')

            if event['date'] < today:
                row_class.append('past-event')

            class_str = ' '.join(row_class)

            html_content += f"""
                <tr class="{class_str}">
                    <td>{event['date'].strftime('%Y-%m-%d')}</td>
                    <td>{event.get('event_type', '')}</td>
                    <td>{event['event']}</td>
                    <td>{event['expected_impact']}</td>
                    <td>{event.get('consensus', '') or ''}</td>
                    <td>{event.get('actual', '') or ''}</td>
                    <td>{event.get('notes', '') or ''}</td>
                </tr>
            """
        
        html_content += """
                </tbody>
            </table>
        </body>
        </html>
        """
        
        with open(output_file, 'w') as f:
            f.write(html_content)
        
        print(f"Created HTML calendar at {output_file}")
        return output_file
    
    def export_for_ml(self, output_file='data/events_for_ml.json'):
        """Export events in a format suitable for ML models."""
        ml_data = []
        
        for _, event in self.events_df.iterrows():
            ml_event = {
                'date': event['date'].isoformat(),
                'day_of_week': event['date'].dayofweek,
                'month': event['date'].month,
                'quarter': (event['date'].month - 1) // 3 + 1,
                'event_type': event['event_type'],
                'impact_level': self._encode_impact(event['expected_impact']),
                'is_fomc': 1 if event['event_type'] == 'FOMC' else 0,
                'is_cpi': 1 if event['event_type'] == 'CPI' else 0,
                'is_nfp': 1 if event['event_type'] == 'NFP' else 0,
                'is_gdp': 1 if event['event_type'] == 'GDP' else 0,
                'is_market_closed': 1 if event['expected_impact'] == 'Market Closed' else 0
            }
            ml_data.append(ml_event)
        
        with open(output_file, 'w') as f:
            json.dump(ml_data, f, indent=2)
        
        print(f"Exported {len(ml_data)} events for ML to {output_file}")
        return ml_data
    
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
    
    def print_summary(self):
        """Print summary of events."""
        print("\n" + "="*60)
        print("MARKET EVENTS SUMMARY")
        print("="*60)

        print(f"\nTotal Events: {len(self.events_df)}")

        if self.events_df.empty:
            print("\nNo events in database. Run without --no-fetch to fetch events from APIs.")
            return

        # Events by type
        print("\nEvents by Type:")
        for event_type in self.events_df['event_type'].unique():
            count = len(self.events_df[self.events_df['event_type'] == event_type])
            print(f"  {event_type}: {count}")

        # Upcoming events
        upcoming = self.get_upcoming_events(30)
        print(f"\nUpcoming Events (Next 30 Days): {len(upcoming)}")

        if not upcoming.empty:
            print("\nNext 5 Events:")
            for _, event in upcoming.head(5).iterrows():
                days_until = (event['date'] - pd.Timestamp.now()).days
                print(f"  {event['date'].strftime('%Y-%m-%d')} ({days_until} days): {event['event']} [{event['expected_impact']}]")

        # High impact events
        high_impact = self.get_high_impact_events()
        future_high_impact = high_impact[high_impact['date'] >= pd.Timestamp.now()]
        print(f"\nUpcoming High Impact Events: {len(future_high_impact)}")

        if not future_high_impact.empty:
            print("\nNext 3 High Impact Events:")
            for _, event in future_high_impact.head(3).iterrows():
                print(f"  {event['date'].strftime('%Y-%m-%d')}: {event['event']}")


def main():
    """Main function to run the market events tracker."""
    import argparse

    parser = argparse.ArgumentParser(description='Market Events Tracker - Fetch and manage economic events')
    parser.add_argument('--target-date', type=str, help='Target date for analysis (YYYY-MM-DD)')
    parser.add_argument('--start-date', type=str, help='Start date for fetching events (YYYY-MM-DD), default: 2024-01-01')
    parser.add_argument('--end-date', type=str, help='End date for fetching events (YYYY-MM-DD), default: 2026-12-31')
    parser.add_argument('--no-fetch', action='store_true', help='Skip fetching new events from APIs')

    args = parser.parse_args()

    # Determine date range for API fetching
    fetch_start = args.start_date if args.start_date else '2024-01-01'
    fetch_end = args.end_date if args.end_date else '2026-12-31'

    tracker = MarketEventsTracker()

    # Load existing events and fetch new ones from APIs
    fetch_new = not args.no_fetch
    events_df = tracker.load_events(fetch_new=fetch_new, start_date=fetch_start, end_date=fetch_end)

    # Print summary
    tracker.print_summary()

    # Create HTML calendar
    tracker.create_event_calendar_html()

    # Export for ML
    tracker.export_for_ml()

    # Show events for target date or date range
    today_events = pd.DataFrame()  # Initialize
    today = pd.Timestamp.now().normalize()

    if args.target_date:
        # Show events for specific target date
        target_date = pd.Timestamp(args.target_date)
        today_events = tracker.get_events_for_date_range(target_date, target_date)

        if not today_events.empty:
            date_str = args.target_date
            print(f"\n{'='*60}")
            print(f"EVENTS FOR {date_str}")
            print(f"{'='*60}")
            for _, event in today_events.iterrows():
                print(f"\nEvent: {event['event']}")
                print(f"Type: {event['event_type']}")
                print(f"Expected Impact: {event['expected_impact']}")
                if event.get('actual'):
                    print(f"Actual: {event['actual']}")
                if event.get('consensus'):
                    print(f"Consensus: {event['consensus']}")
                if event.get('notes'):
                    print(f"Notes: {event['notes']}")
    else:
        # Show today's events by default
        today_events = tracker.get_events_for_date_range(today, today)

        if not today_events.empty:
            print(f"\n{'='*60}")
            print(f"EVENTS FOR TODAY ({today.strftime('%Y-%m-%d')})")
            print(f"{'='*60}")
            for _, event in today_events.iterrows():
                print(f"\nEvent: {event['event']}")
                print(f"Type: {event['event_type']}")
                print(f"Expected Impact: {event['expected_impact']}")

    print("\n" + "="*60)
    print("Market Events Tracker Completed Successfully!")
    print(f"Total events in database: {len(tracker.events_df)}")
    print("="*60)


if __name__ == "__main__":
    main()