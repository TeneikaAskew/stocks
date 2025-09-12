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
        self.events_file = Path("data/market_events.csv")
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
        
    def get_2025_economic_calendar(self):
        """Get the 2025 economic calendar with known dates."""
        # Known 2025 economic event dates
        events = [
            # CPI Releases (Monthly, typically around 13th)
            {'date': '2025-01-14', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-02-13', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-03-12', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-04-10', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-05-14', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-06-12', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-07-11', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-08-13', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-09-11', 'event_type': 'CPI', 'event': 'CPI Release - September 2025', 'expected_impact': 'High', 
             'actual': '2.4% YoY', 'consensus': '2.3% YoY', 'notes': 'Higher than expected, caused market volatility'},
            {'date': '2025-10-10', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-11-13', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-12-11', 'event_type': 'CPI', 'event': 'CPI Release', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            
            # FOMC Meetings (8 per year)
            {'date': '2025-01-29', 'event_type': 'FOMC', 'event': 'FOMC Meeting & Decision', 'expected_impact': 'Very High', 'actual': None, 'consensus': None},
            {'date': '2025-03-19', 'event_type': 'FOMC', 'event': 'FOMC Meeting & Decision', 'expected_impact': 'Very High', 'actual': None, 'consensus': None},
            {'date': '2025-05-07', 'event_type': 'FOMC', 'event': 'FOMC Meeting & Decision', 'expected_impact': 'Very High', 'actual': None, 'consensus': None},
            {'date': '2025-06-18', 'event_type': 'FOMC', 'event': 'FOMC Meeting & Decision', 'expected_impact': 'Very High', 'actual': None, 'consensus': None},
            {'date': '2025-07-30', 'event_type': 'FOMC', 'event': 'FOMC Meeting & Decision', 'expected_impact': 'Very High', 'actual': None, 'consensus': None},
            {'date': '2025-09-17', 'event_type': 'FOMC', 'event': 'FOMC Meeting & Decision', 'expected_impact': 'Very High', 'actual': None, 'consensus': None},
            {'date': '2025-11-05', 'event_type': 'FOMC', 'event': 'FOMC Meeting & Decision', 'expected_impact': 'Very High', 'actual': None, 'consensus': None},
            {'date': '2025-12-17', 'event_type': 'FOMC', 'event': 'FOMC Meeting & Decision', 'expected_impact': 'Very High', 'actual': None, 'consensus': None},
            
            # NFP (First Friday of each month)
            {'date': '2025-01-10', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-02-07', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-03-07', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-04-04', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-05-02', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-06-06', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-07-03', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-08-01', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-09-05', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls - September 2025', 'expected_impact': 'High', 
             'actual': '142K', 'consensus': '165K', 'notes': 'Below expectations, raised recession concerns'},
            {'date': '2025-10-03', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-11-07', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-12-05', 'event_type': 'NFP', 'event': 'Non-Farm Payrolls', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            
            # GDP (Quarterly)
            {'date': '2025-01-30', 'event_type': 'GDP', 'event': 'GDP Q4 2024 Advance', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-02-27', 'event_type': 'GDP', 'event': 'GDP Q4 2024 Second', 'expected_impact': 'Medium', 'actual': None, 'consensus': None},
            {'date': '2025-03-27', 'event_type': 'GDP', 'event': 'GDP Q4 2024 Final', 'expected_impact': 'Low', 'actual': None, 'consensus': None},
            {'date': '2025-04-30', 'event_type': 'GDP', 'event': 'GDP Q1 2025 Advance', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-05-29', 'event_type': 'GDP', 'event': 'GDP Q1 2025 Second', 'expected_impact': 'Medium', 'actual': None, 'consensus': None},
            {'date': '2025-06-26', 'event_type': 'GDP', 'event': 'GDP Q1 2025 Final', 'expected_impact': 'Low', 'actual': None, 'consensus': None},
            {'date': '2025-07-31', 'event_type': 'GDP', 'event': 'GDP Q2 2025 Advance', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-08-28', 'event_type': 'GDP', 'event': 'GDP Q2 2025 Second', 'expected_impact': 'Medium', 'actual': None, 'consensus': None},
            {'date': '2025-09-26', 'event_type': 'GDP', 'event': 'GDP Q2 2025 Final', 'expected_impact': 'Low', 'actual': None, 'consensus': None},
            {'date': '2025-10-30', 'event_type': 'GDP', 'event': 'GDP Q3 2025 Advance', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            
            # PCE (Monthly, typically end of month)
            {'date': '2025-01-31', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-02-28', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-03-28', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-04-30', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-05-30', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-06-27', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-07-31', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-08-29', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-09-26', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            {'date': '2025-10-31', 'event_type': 'PCE', 'event': 'PCE Price Index', 'expected_impact': 'High', 'actual': None, 'consensus': None},
            
            # Special Events
            {'date': '2025-01-20', 'event_type': 'SPECIAL', 'event': 'Martin Luther King Jr. Day - Markets Closed', 'expected_impact': 'Market Closed', 'actual': None, 'consensus': None},
            {'date': '2025-02-17', 'event_type': 'SPECIAL', 'event': 'Presidents Day - Markets Closed', 'expected_impact': 'Market Closed', 'actual': None, 'consensus': None},
            {'date': '2025-04-18', 'event_type': 'SPECIAL', 'event': 'Good Friday - Markets Closed', 'expected_impact': 'Market Closed', 'actual': None, 'consensus': None},
            {'date': '2025-05-26', 'event_type': 'SPECIAL', 'event': 'Memorial Day - Markets Closed', 'expected_impact': 'Market Closed', 'actual': None, 'consensus': None},
            {'date': '2025-06-19', 'event_type': 'SPECIAL', 'event': 'Juneteenth - Markets Closed', 'expected_impact': 'Market Closed', 'actual': None, 'consensus': None},
            {'date': '2025-07-04', 'event_type': 'SPECIAL', 'event': 'Independence Day - Markets Closed', 'expected_impact': 'Market Closed', 'actual': None, 'consensus': None},
            {'date': '2025-09-01', 'event_type': 'SPECIAL', 'event': 'Labor Day - Markets Closed', 'expected_impact': 'Market Closed', 'actual': None, 'consensus': None},
            {'date': '2025-11-27', 'event_type': 'SPECIAL', 'event': 'Thanksgiving - Markets Closed', 'expected_impact': 'Market Closed', 'actual': None, 'consensus': None},
            {'date': '2025-12-25', 'event_type': 'SPECIAL', 'event': 'Christmas - Markets Closed', 'expected_impact': 'Market Closed', 'actual': None, 'consensus': None},
        ]
        
        return pd.DataFrame(events)
    
    def load_events(self):
        """Load existing events from file."""
        if self.events_file.exists():
            self.events_df = pd.read_csv(self.events_file)
            self.events_df['date'] = pd.to_datetime(self.events_df['date'])
            print(f"Loaded {len(self.events_df)} existing events")
        else:
            # Initialize with known events
            self.events_df = self.get_2025_economic_calendar()
            self.events_df['date'] = pd.to_datetime(self.events_df['date'])
            self.save_events()
            print(f"Initialized with {len(self.events_df)} events for 2025")
        
        return self.events_df
    
    def save_events(self):
        """Save events to CSV file."""
        self.events_df.to_csv(self.events_file, index=False)
        print(f"Saved {len(self.events_df)} events to {self.events_file}")
    
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
    
    parser = argparse.ArgumentParser(description='Market Events Tracker')
    parser.add_argument('--target-date', type=str, help='Target date for analysis (YYYY-MM-DD)')
    parser.add_argument('--start-date', type=str, help='Start date for range analysis (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='End date for range analysis (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    tracker = MarketEventsTracker()
    
    # Load events
    events_df = tracker.load_events()
    
    # Print summary
    tracker.print_summary()
    
    # Create HTML calendar
    tracker.create_event_calendar_html()
    
    # Export for ML
    tracker.export_for_ml()
    
    # Show events for target date or date range
    today_events = pd.DataFrame()  # Initialize
    today = pd.Timestamp.now().normalize()
    
    if args.start_date and args.end_date:
        print(f"\n{'='*60}")
        print(f"EVENTS FOR DATE RANGE: {args.start_date} to {args.end_date}")
        print(f"{'='*60}")
        range_events = tracker.get_events_for_date_range(args.start_date, args.end_date)
        if not range_events.empty:
            for _, event in range_events.iterrows():
                print(f"\n{event['date'].strftime('%Y-%m-%d')}: {event['event']}")
                print(f"  Type: {event['event_type']}, Impact: {event['expected_impact']}")
    elif args.target_date:
        target_date = pd.Timestamp(args.target_date)
        today_events = tracker.get_events_for_date_range(target_date, target_date)
    else:
        today_events = tracker.get_events_for_date_range(today, today)
    
    if not today_events.empty and not (args.start_date and args.end_date):
        date_str = args.target_date if args.target_date else today.strftime('%Y-%m-%d')
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
    
    print("\n" + "="*60)
    print("Market Events Tracker Initialized Successfully!")
    print("="*60)


if __name__ == "__main__":
    main()