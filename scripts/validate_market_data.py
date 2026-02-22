#!/usr/bin/env python3
"""
Validate Market Data Completeness

Checks that all required market data has been fetched and is complete:
1. ETF daily market data (IWM, SPY, QQQ, SPX)
2. ETF minute-level data (390 minutes per trading day)
3. ETF options data (multiple snapshots + aggregated files)

Runs daily at 9pm EDT to verify data collection was successful.
"""

import sys
import json
from datetime import datetime, timedelta, date, time as dt_time
from pathlib import Path
import pandas as pd
import pytz
from typing import Dict, List, Tuple, Optional


# Define tickers to validate
TICKERS = ['iwm', 'spy', 'qqq', 'spx']

# Required columns for daily market data
REQUIRED_DAILY_COLUMNS = ['Open', 'High', 'Low', 'Close', 'Volume']

# Required columns for options data
REQUIRED_OPTIONS_COLUMNS = ['symbol', 'strike', 'expiration', 'optionType', 'lastPrice']

# Market hours (ET)
MARKET_OPEN = dt_time(9, 30)
MARKET_CLOSE = dt_time(16, 0)
EXPECTED_MINUTE_BARS = 390  # 6.5 hours * 60 minutes

# Minimum expected options snapshots per day
MIN_OPTIONS_SNAPSHOTS = 5


class ValidationResult:
    """Container for validation results."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        self.checks_passed = 0
        self.checks_failed = 0

    def add_error(self, message: str):
        """Add an error message."""
        self.errors.append(message)
        self.checks_failed += 1

    def add_warning(self, message: str):
        """Add a warning message."""
        self.warnings.append(message)

    def add_info(self, message: str):
        """Add an info message."""
        self.info.append(message)

    def pass_check(self):
        """Increment passed checks counter."""
        self.checks_passed += 1

    def is_success(self) -> bool:
        """Check if validation passed (no errors)."""
        return len(self.errors) == 0

    def get_summary(self) -> Dict:
        """Get validation summary as dict."""
        return {
            'success': self.is_success(),
            'checks_passed': self.checks_passed,
            'checks_failed': self.checks_failed,
            'errors': self.errors,
            'warnings': self.warnings,
            'info': self.info,
            'timestamp': datetime.now().isoformat()
        }


def get_expected_date() -> date:
    """
    Get the expected date for market data.
    If today is a weekend or after market close, use last trading day.
    """
    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    today = now.date()

    # If it's Saturday (5) or Sunday (6), go back to Friday
    if today.weekday() == 5:  # Saturday
        expected_date = today - timedelta(days=1)
    elif today.weekday() == 6:  # Sunday
        expected_date = today - timedelta(days=2)
    else:
        # On weekdays, expect today's data after market close
        # Market closes at 4pm ET, data processing takes time
        # At 9pm ET we should have all data for today
        expected_date = today

    return expected_date


def validate_daily_market_data(ticker: str, result: ValidationResult) -> bool:
    """
    Validate daily market data for a ticker.

    Args:
        ticker: Ticker symbol (lowercase)
        result: ValidationResult object to record findings

    Returns:
        True if validation passed, False otherwise
    """
    print(f"\n{'='*60}")
    print(f"Validating Daily Market Data: {ticker.upper()}")
    print(f"{'='*60}")

    ticker_dir = Path("data") / ticker
    current_year = datetime.now().year
    daily_file = ticker_dir / f"{ticker}_{current_year}.parquet"
    summary_file = ticker_dir / f"{ticker}_summary.json"

    # Check if daily file exists
    if not daily_file.exists():
        result.add_error(f"{ticker.upper()}: Daily data file not found: {daily_file}")
        return False

    print(f"✓ Daily data file exists: {daily_file}")
    result.add_info(f"{ticker.upper()}: Daily data file exists")

    # Read the parquet file
    try:
        df = pd.read_parquet(daily_file)
        print(f"✓ Successfully read {len(df)} records")
        result.pass_check()
    except Exception as e:
        result.add_error(f"{ticker.upper()}: Failed to read daily data: {e}")
        return False

    # Check for required columns
    missing_columns = [col for col in REQUIRED_DAILY_COLUMNS if col not in df.columns]
    if missing_columns:
        result.add_error(f"{ticker.upper()}: Missing required columns: {missing_columns}")
        return False

    print(f"✓ All required columns present: {REQUIRED_DAILY_COLUMNS}")
    result.pass_check()

    # Check for expected date
    expected_date = get_expected_date()
    df.index = pd.to_datetime(df.index)
    latest_date = df.index.max().date()

    print(f"  Expected date: {expected_date}")
    print(f"  Latest date in file: {latest_date}")

    if latest_date < expected_date:
        # Calculate how many trading days behind
        days_behind = (expected_date - latest_date).days
        result.add_error(
            f"{ticker.upper()}: Data is outdated. Latest: {latest_date}, Expected: {expected_date} "
            f"({days_behind} calendar days behind)"
        )
        return False
    elif latest_date == expected_date:
        print(f"✓ Data is current (latest date: {latest_date})")
        result.pass_check()
    else:
        # Data is from the future? This might happen if running in different timezone
        result.add_warning(
            f"{ticker.upper()}: Latest date {latest_date} is ahead of expected {expected_date}"
        )
        result.pass_check()

    # Check data quality for the latest record
    latest_record = df.iloc[-1]

    # Check for null values in critical columns
    null_columns = [col for col in REQUIRED_DAILY_COLUMNS if pd.isna(latest_record[col])]
    if null_columns:
        result.add_error(f"{ticker.upper()}: Latest record has null values in: {null_columns}")
        return False

    print(f"✓ No null values in latest record")
    result.pass_check()

    # Check for reasonable price values (should be positive and within reasonable ranges)
    if latest_record['Close'] <= 0:
        result.add_error(f"{ticker.upper()}: Invalid Close price: {latest_record['Close']}")
        return False

    if latest_record['Volume'] < 0:
        result.add_error(f"{ticker.upper()}: Invalid Volume: {latest_record['Volume']}")
        return False

    print(f"✓ Latest record looks valid:")
    print(f"    Close: ${latest_record['Close']:.2f}")
    print(f"    Volume: {latest_record['Volume']:,.0f}")
    result.pass_check()

    # Validate summary file
    if summary_file.exists():
        try:
            with open(summary_file, 'r') as f:
                summary = json.load(f)

            summary_date = pd.to_datetime(summary.get('last_date')).date()
            if summary_date == latest_date:
                print(f"✓ Summary file is in sync")
                result.pass_check()
            else:
                result.add_warning(
                    f"{ticker.upper()}: Summary file date mismatch. "
                    f"Summary: {summary_date}, Data: {latest_date}"
                )
        except Exception as e:
            result.add_warning(f"{ticker.upper()}: Could not validate summary file: {e}")
    else:
        result.add_warning(f"{ticker.upper()}: Summary file not found")

    return True


def find_time_gaps(timestamps: pd.DatetimeIndex, expected_minutes: int = 390) -> List[Tuple[datetime, datetime]]:
    """
    Find gaps in minute-level data.

    Args:
        timestamps: DatetimeIndex of minute bars
        expected_minutes: Expected number of minutes (default 390)

    Returns:
        List of (gap_start, gap_end) tuples
    """
    gaps = []

    if len(timestamps) == 0:
        return gaps

    # Sort timestamps
    timestamps = timestamps.sort_values()

    # Check for gaps larger than 1 minute
    for i in range(1, len(timestamps)):
        time_diff = (timestamps[i] - timestamps[i-1]).total_seconds() / 60

        # If gap is more than 1 minute, record it
        if time_diff > 1.5:  # Allow some tolerance
            gaps.append((timestamps[i-1], timestamps[i]))

    return gaps


def validate_minute_data(ticker: str, result: ValidationResult) -> bool:
    """
    Validate minute-level market data for a ticker.
    Checks that all 390 minutes are present with no gaps.

    Args:
        ticker: Ticker symbol (lowercase)
        result: ValidationResult object to record findings

    Returns:
        True if validation passed, False otherwise
    """
    print(f"\n{'='*60}")
    print(f"Validating Minute Data: {ticker.upper()}")
    print(f"{'='*60}")

    ticker_dir = Path("data") / ticker / "minute"

    if not ticker_dir.exists():
        result.add_error(f"{ticker.upper()}: Minute data directory not found: {ticker_dir}")
        return False

    # Check for today's minute data
    expected_date = get_expected_date()
    minute_file = ticker_dir / f"{ticker}_minute_{expected_date.strftime('%Y%m%d')}.parquet"

    if not minute_file.exists():
        # Check if it's a weekend or market holiday
        if expected_date.weekday() >= 5:
            result.add_info(f"{ticker.upper()}: No minute data expected for {expected_date} (weekend)")
            return True

        result.add_error(f"{ticker.upper()}: Minute data not found for {expected_date}: {minute_file}")
        return False

    # Read the minute data file
    try:
        df = pd.read_parquet(minute_file)
        print(f"✓ Minute data file exists: {minute_file}")
        print(f"  Total bars: {len(df)}")
        result.pass_check()

        # Check number of bars
        if len(df) < EXPECTED_MINUTE_BARS:
            missing_bars = EXPECTED_MINUTE_BARS - len(df)
            result.add_error(
                f"{ticker.upper()}: Incomplete minute data. "
                f"Expected {EXPECTED_MINUTE_BARS} bars, found {len(df)} ({missing_bars} missing)"
            )
            return False
        elif len(df) > EXPECTED_MINUTE_BARS:
            extra_bars = len(df) - EXPECTED_MINUTE_BARS
            result.add_warning(
                f"{ticker.upper()}: More minute bars than expected. "
                f"Expected {EXPECTED_MINUTE_BARS}, found {len(df)} ({extra_bars} extra)"
            )
        else:
            print(f"✓ Correct number of minute bars: {EXPECTED_MINUTE_BARS}")
            result.pass_check()

        # Check for required columns
        missing_columns = [col for col in REQUIRED_DAILY_COLUMNS if col not in df.columns]
        if missing_columns:
            result.add_error(f"{ticker.upper()}: Minute data missing columns: {missing_columns}")
            return False

        print(f"✓ All required columns present")
        result.pass_check()

        # Check for gaps in timestamps
        gaps = find_time_gaps(df.index, EXPECTED_MINUTE_BARS)

        if gaps:
            gap_count = len(gaps)
            result.add_error(f"{ticker.upper()}: Found {gap_count} time gap(s) in minute data:")
            for gap_start, gap_end in gaps[:5]:  # Show first 5 gaps
                gap_minutes = (gap_end - gap_start).total_seconds() / 60
                result.add_error(
                    f"  Gap: {gap_start.strftime('%H:%M')} to {gap_end.strftime('%H:%M')} "
                    f"({gap_minutes:.0f} minutes)"
                )
            if gap_count > 5:
                result.add_error(f"  ... and {gap_count - 5} more gaps")
            return False
        else:
            print(f"✓ No gaps in minute data (continuous timestamps)")
            result.pass_check()

        # Validate time range covers market hours
        eastern = pytz.timezone('US/Eastern')
        df_et = df.copy()
        df_et.index = df_et.index.tz_convert('US/Eastern')

        first_time = df_et.index.min().time()
        last_time = df_et.index.max().time()

        print(f"  Time range: {first_time.strftime('%H:%M')} - {last_time.strftime('%H:%M')} ET")

        # Check if data starts at market open (9:30 AM)
        if first_time != MARKET_OPEN:
            result.add_warning(
                f"{ticker.upper()}: First bar at {first_time.strftime('%H:%M')} ET, "
                f"expected {MARKET_OPEN.strftime('%H:%M')} ET"
            )

        # Check if data ends at or near market close (4:00 PM)
        # Last bar should be at 3:59 PM (since bars are for the minute starting at that time)
        expected_last = dt_time(15, 59)
        if last_time != expected_last:
            result.add_warning(
                f"{ticker.upper()}: Last bar at {last_time.strftime('%H:%M')} ET, "
                f"expected {expected_last.strftime('%H:%M')} ET"
            )

        # Check for null values
        null_counts = df[REQUIRED_DAILY_COLUMNS].isnull().sum()
        if null_counts.any():
            null_cols = null_counts[null_counts > 0].to_dict()
            result.add_warning(f"{ticker.upper()}: Minute data has null values: {null_cols}")

        result.add_info(f"{ticker.upper()}: Minute data complete with {len(df)} bars, no gaps")

    except Exception as e:
        result.add_error(f"{ticker.upper()}: Failed to validate minute data: {e}")
        return False

    return True


def validate_options_data(ticker: str, result: ValidationResult) -> bool:
    """
    Validate ETF options data for a ticker.
    Checks for minimum number of snapshots and aggregated files.

    Args:
        ticker: Ticker symbol (uppercase for options files)
        result: ValidationResult object to record findings

    Returns:
        True if validation passed, False otherwise
    """
    print(f"\n{'='*60}")
    print(f"Validating Options Data: {ticker}")
    print(f"{'='*60}")

    options_dir = Path("data/options/etfs")

    if not options_dir.exists():
        result.add_error(f"Options data directory not found: {options_dir}")
        return False

    # Look for recent options files for this ticker
    expected_date = get_expected_date()

    # Check if it's a weekend
    if expected_date.weekday() >= 5:
        result.add_info(f"{ticker}: No options data expected for {expected_date} (weekend)")
        return True

    # Options are fetched intraday, so we look for any file from today
    date_pattern = expected_date.strftime('%Y%m%d')
    ticker_files = list(options_dir.glob(f"{ticker}_{date_pattern}_*.parquet"))
    aggregated_files = list(options_dir.glob(f"etf_options_{date_pattern}_*.parquet"))

    print(f"  Ticker-specific files: {len(ticker_files)}")
    print(f"  Aggregated files: {len(aggregated_files)}")

    # Validate ticker-specific snapshots
    if not ticker_files:
        result.add_error(f"{ticker}: No options snapshots found for {expected_date}")
        return False

    if len(ticker_files) < MIN_OPTIONS_SNAPSHOTS:
        result.add_error(
            f"{ticker}: Insufficient options snapshots. "
            f"Found {len(ticker_files)}, minimum required: {MIN_OPTIONS_SNAPSHOTS}"
        )
        return False

    print(f"✓ Found {len(ticker_files)} options snapshots (minimum {MIN_OPTIONS_SNAPSHOTS} required)")
    result.pass_check()

    # Validate aggregated files exist
    if not aggregated_files:
        result.add_error(f"{ticker}: No aggregated options files found for {expected_date}")
        return False

    if len(aggregated_files) < MIN_OPTIONS_SNAPSHOTS:
        result.add_warning(
            f"{ticker}: Fewer aggregated files ({len(aggregated_files)}) than expected "
            f"(minimum {MIN_OPTIONS_SNAPSHOTS})"
        )
    else:
        print(f"✓ Found {len(aggregated_files)} aggregated options files")
        result.pass_check()

    # Validate the most recent ticker-specific file
    latest_ticker_file = sorted(ticker_files)[-1]
    print(f"  Validating latest ticker file: {latest_ticker_file.name}")

    try:
        df = pd.read_parquet(latest_ticker_file)
        print(f"  ✓ Successfully read {len(df)} option contracts")
        result.pass_check()

        # Check for required columns
        missing_columns = [col for col in REQUIRED_OPTIONS_COLUMNS if col not in df.columns]
        if missing_columns:
            result.add_error(f"{ticker}: Options file missing columns: {missing_columns}")
            return False

        print(f"  ✓ All required columns present")
        result.pass_check()

        # Check data distribution
        calls = len(df[df['optionType'] == 'calls'])
        puts = len(df[df['optionType'] == 'puts'])
        print(f"  ✓ Contract breakdown: {calls} calls, {puts} puts")

        if calls == 0 or puts == 0:
            result.add_error(f"{ticker}: Missing option type (calls: {calls}, puts: {puts})")
            return False
        else:
            result.pass_check()

        # Check for expirations
        expirations = df['expiration'].nunique()
        print(f"  ✓ {expirations} unique expiration dates")

        if expirations < 3:
            result.add_warning(f"{ticker}: Limited expiration dates ({expirations})")
        else:
            result.pass_check()

    except Exception as e:
        result.add_error(f"{ticker}: Failed to validate options data: {e}")
        return False

    # Validate the most recent aggregated file
    latest_agg_file = sorted(aggregated_files)[-1]
    print(f"  Validating latest aggregated file: {latest_agg_file.name}")

    try:
        agg_df = pd.read_parquet(latest_agg_file)
        print(f"  ✓ Aggregated file contains {len(agg_df)} total contracts")

        # Check that our ticker is in the aggregated file
        if 'symbol' in agg_df.columns:
            tickers_in_file = agg_df['symbol'].unique()
            if ticker not in tickers_in_file and f"^{ticker}" not in tickers_in_file:
                result.add_error(
                    f"{ticker}: Not found in aggregated file. "
                    f"Found tickers: {list(tickers_in_file)}"
                )
                return False
            print(f"  ✓ Ticker {ticker} found in aggregated file")
            result.pass_check()

    except Exception as e:
        result.add_warning(f"{ticker}: Could not fully validate aggregated file: {e}")

    result.add_info(
        f"{ticker}: {len(ticker_files)} snapshots + {len(aggregated_files)} aggregated files available"
    )

    return True


def main():
    """Main validation function."""
    print("="*80)
    print("Market Data Validation Pipeline")
    print("="*80)

    eastern = pytz.timezone('US/Eastern')
    now = datetime.now(eastern)
    expected_date = get_expected_date()

    print(f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Expected data date: {expected_date}")
    print(f"Validating: {', '.join([t.upper() for t in TICKERS])}")
    print()

    result = ValidationResult()

    # Validate daily market data for each ticker
    print("\n" + "="*80)
    print("DAILY MARKET DATA VALIDATION")
    print("="*80)
    for ticker in TICKERS:
        success = validate_daily_market_data(ticker, result)
        if not success:
            print(f"✗ {ticker.upper()} daily data validation failed")
        else:
            print(f"✓ {ticker.upper()} daily data validation passed")

    # Validate minute data for each ticker
    print("\n" + "="*80)
    print("MINUTE DATA VALIDATION")
    print("="*80)
    for ticker in TICKERS:
        success = validate_minute_data(ticker, result)
        if not success:
            print(f"✗ {ticker.upper()} minute data validation failed")
        else:
            print(f"✓ {ticker.upper()} minute data validation passed")

    # Validate options data for each ticker
    print("\n" + "="*80)
    print("OPTIONS DATA VALIDATION")
    print("="*80)
    for ticker in TICKERS:
        # Options files use uppercase ticker names, except SPX
        options_ticker = 'SPX' if ticker == 'spx' else ticker.upper()
        success = validate_options_data(options_ticker, result)
        if not success:
            print(f"✗ {options_ticker} options data validation failed")
        else:
            print(f"✓ {options_ticker} options data validation passed")

    # Print summary
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)

    summary = result.get_summary()

    print(f"\nStatus: {'✓ PASSED' if summary['success'] else '✗ FAILED'}")
    print(f"Checks passed: {summary['checks_passed']}")
    print(f"Checks failed: {summary['checks_failed']}")

    if summary['errors']:
        print(f"\n❌ ERRORS ({len(summary['errors'])}):")
        for i, error in enumerate(summary['errors'], 1):
            print(f"  {i}. {error}")

    if summary['warnings']:
        print(f"\n⚠ WARNINGS ({len(summary['warnings'])}):")
        for i, warning in enumerate(summary['warnings'], 1):
            print(f"  {i}. {warning}")

    if summary['info']:
        print(f"\nℹ INFO ({len(summary['info'])}):")
        for i, info in enumerate(summary['info'], 1):
            print(f"  {i}. {info}")

    # Save summary to file
    summary_file = Path("data/market_data_validation.json")
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"\n✓ Validation summary saved to {summary_file}")

    print("\n" + "="*80)

    # Exit with appropriate code
    sys.exit(0 if summary['success'] else 1)


if __name__ == '__main__':
    main()
