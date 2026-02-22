#!/usr/bin/env python3
"""
Fetch upcoming earnings calendar from Unusual Whales API.

This script fetches upcoming earnings announcements and saves them to a JSON file.
It can be run standalone or as part of the weekly market events update workflow.

Usage:
    python scripts/fetch_earnings_calendar.py
    python scripts/fetch_earnings_calendar.py --days 30
    python scripts/fetch_earnings_calendar.py --start-date 2024-01-01 --end-date 2024-12-31
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests


class EarningsCalendarFetcher:
    """Fetch and manage earnings calendar data from Unusual Whales."""

    def __init__(self):
        self.output_dir = Path("data/earnings")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.earnings_file = self.output_dir / "earnings_calendar.json"

    def fetch_unusual_whales_earnings(self, days_ahead=90):
        """
        Fetch upcoming earnings from Unusual Whales API.

        Args:
            days_ahead: Number of days ahead to fetch earnings (default: 90)

        Returns:
            pd.DataFrame: Earnings data
        """
        try:
            # Unusual Whales upcoming earnings endpoint
            # Using formats=table to get all available earnings data
            url = "https://phx.unusualwhales.com/api/companies_earnings/upcoming_earnings_v2?formats=table"

            print(f"Fetching earnings calendar from Unusual Whales...")
            print(f"URL: {url}")

            # Add headers to avoid being blocked
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json',
            }

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            if not data or "data" not in data:
                print("Warning: No earnings data found in API response")
                return pd.DataFrame()

            earnings_data = data["data"]

            if not earnings_data:
                print(f"Note: API returned 0 earnings announcements")
                print("This may be due to rate limiting or time of day.")
                print("The API typically returns data during market hours or with proper auth.")
                return pd.DataFrame()

            print(f"Fetched {len(earnings_data)} earnings announcements")

            # Parse and structure the data
            earnings_list = []
            today = datetime.now().date()
            cutoff_date = today + timedelta(days=days_ahead)

            for item in earnings_data:
                # Parse earnings date - field is 'report_date'
                earnings_date_str = item.get("report_date")
                if not earnings_date_str:
                    continue

                try:
                    # Try parsing different date formats
                    if "T" in earnings_date_str:
                        earnings_date = datetime.fromisoformat(
                            earnings_date_str.replace("Z", "+00:00")
                        ).date()
                    else:
                        earnings_date = datetime.strptime(
                            earnings_date_str, "%Y-%m-%d"
                        ).date()
                except (ValueError, AttributeError):
                    continue

                # Filter by date range
                if earnings_date > cutoff_date:
                    continue

                earnings_list.append(
                    {
                        "date": earnings_date.strftime("%Y-%m-%d"),
                        "ticker": item.get("symbol", ""),
                        "company_name": item.get("full_name", ""),
                        "time": item.get("report_time", ""),  # premarket, postmarket
                        "eps_estimate": item.get("eps_mean_est"),
                        "market_cap": item.get("marketcap"),
                        "sector": item.get("sector", ""),
                        "has_options": item.get("has_options", False),
                        "expected_move": item.get("expected_move"),
                        "source": "UnusualWhales",
                        "fetched_at": datetime.now().isoformat(),
                    }
                )

            df = pd.DataFrame(earnings_list)

            if not df.empty:
                df = df.sort_values("date").reset_index(drop=True)
                print(f"Processed {len(df)} earnings announcements")
                print(f"Date range: {df['date'].min()} to {df['date'].max()}")
            else:
                print("No earnings data after processing")

            return df

        except requests.exceptions.RequestException as e:
            print(f"Error fetching from Unusual Whales API: {e}")
            return pd.DataFrame()
        except Exception as e:
            print(f"Error processing earnings data: {e}")
            import traceback

            traceback.print_exc()
            return pd.DataFrame()

    def save_earnings(self, earnings_df):
        """
        Save earnings data to JSON file with deduplication.
        Merges new data with existing data and removes duplicates.

        Args:
            earnings_df: DataFrame with earnings data
        """
        if earnings_df.empty:
            print("No earnings data to save")
            return

        # Load existing earnings if file exists
        if self.earnings_file.exists():
            try:
                with open(self.earnings_file, "r") as f:
                    existing_data = json.load(f)
                existing_df = pd.DataFrame(existing_data)
                print(f"Loaded {len(existing_df)} existing earnings records")

                # Combine new and existing data
                combined_df = pd.concat([existing_df, earnings_df], ignore_index=True)

                # Remove duplicates based on ticker and date
                before_dedup = len(combined_df)
                combined_df = combined_df.drop_duplicates(
                    subset=['ticker', 'date'],
                    keep='last'  # Keep the most recent fetch
                )
                after_dedup = len(combined_df)
                duplicates_removed = before_dedup - after_dedup

                print(f"Merged data: {len(existing_df)} existing + {len(earnings_df)} new = {after_dedup} total ({duplicates_removed} duplicates removed)")

                earnings_df = combined_df

            except Exception as e:
                print(f"Note: Could not load existing earnings file: {e}")
                print("Saving new data only")

        # Sort by date for easier reading
        earnings_df = earnings_df.sort_values('date').reset_index(drop=True)

        # Convert to list of dicts for JSON
        earnings_data = earnings_df.to_dict(orient="records")

        # Save to JSON file
        with open(self.earnings_file, "w") as f:
            json.dump(earnings_data, f, indent=2)

        print(f"\n{'='*80}")
        print(f"Saved {len(earnings_data)} earnings announcements to {self.earnings_file} (sorted by date)")
        print(f"{'='*80}")

    def print_summary(self, earnings_df):
        """Print summary statistics of earnings data."""
        if earnings_df.empty:
            print("\nNo earnings data available")
            return

        print(f"\n{'='*80}")
        print("EARNINGS CALENDAR SUMMARY")
        print(f"{'='*80}")

        print(f"\nTotal Earnings: {len(earnings_df)}")

        # Group by date
        by_date = earnings_df.groupby("date").size()
        print(f"\nEarnings by Date:")
        for date, count in by_date.head(10).items():
            print(f"  {date}: {count} companies")

        if len(by_date) > 10:
            print(f"  ... and {len(by_date) - 10} more dates")

        # Group by sector
        if "sector" in earnings_df.columns and earnings_df["sector"].notna().any():
            by_sector = earnings_df.groupby("sector").size().sort_values(ascending=False)
            print(f"\nTop Sectors:")
            for sector, count in by_sector.head(5).items():
                if sector:
                    print(f"  {sector}: {count}")

        # Time of day breakdown
        if "time" in earnings_df.columns and earnings_df["time"].notna().any():
            by_time = earnings_df.groupby("time").size()
            print(f"\nEarnings Time:")
            for time, count in by_time.items():
                if time:
                    print(f"  {time}: {count}")

        # Upcoming earnings (next 7 days)
        today = datetime.now().date()
        next_week = today + timedelta(days=7)
        upcoming = earnings_df[
            earnings_df["date"].apply(
                lambda x: today
                <= datetime.strptime(x, "%Y-%m-%d").date()
                <= next_week
            )
        ]

        if not upcoming.empty:
            print(f"\nUpcoming Earnings (Next 7 Days): {len(upcoming)}")
            for _, row in upcoming.head(10).iterrows():
                print(
                    f"  {row['date']} ({row.get('time', 'N/A')}): {row['ticker']} - {row.get('company_name', 'N/A')}"
                )


def main():
    """Main function to fetch earnings calendar."""
    parser = argparse.ArgumentParser(
        description="Fetch upcoming earnings calendar from Unusual Whales"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Number of days ahead to fetch earnings (default: 90)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date for filtering (YYYY-MM-DD) - overrides --days",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date for filtering (YYYY-MM-DD) - overrides --days",
    )

    args = parser.parse_args()

    fetcher = EarningsCalendarFetcher()

    # Fetch earnings data
    if args.start_date and args.end_date:
        # Calculate days ahead from start/end dates
        start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(args.end_date, "%Y-%m-%d").date()
        days_ahead = (end - datetime.now().date()).days
        days_ahead = max(days_ahead, 90)  # Minimum 90 days
        print(f"Fetching earnings for date range: {args.start_date} to {args.end_date}")
        print(f"Using {days_ahead} days ahead for API fetch")
    else:
        days_ahead = args.days
        print(f"Fetching earnings for next {days_ahead} days")

    earnings_df = fetcher.fetch_unusual_whales_earnings(days_ahead=days_ahead)

    # Filter by date range if specified
    if args.start_date and args.end_date and not earnings_df.empty:
        print(
            f"Filtering earnings between {args.start_date} and {args.end_date}..."
        )
        earnings_df = earnings_df[
            (earnings_df["date"] >= args.start_date)
            & (earnings_df["date"] <= args.end_date)
        ]
        print(f"Filtered to {len(earnings_df)} earnings announcements")

    if not earnings_df.empty:
        # Save earnings data
        fetcher.save_earnings(earnings_df)

        # Print summary
        fetcher.print_summary(earnings_df)

        print("\n" + "=" * 80)
        print("Earnings Calendar Fetch Completed Successfully!")
        print("=" * 80)
    else:
        print("\nNo earnings data fetched")
        sys.exit(1)


if __name__ == "__main__":
    main()
