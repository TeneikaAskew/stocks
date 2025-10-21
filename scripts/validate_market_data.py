#!/usr/bin/env python3
"""
Validate Market Data Completeness

Checks that all required market data has been fetched and is complete:
1. ETF daily market data (IWM, SPY, QQQ, SPX)
2. ETF minute-level data
3. ETF options data

Runs daily at 9pm EDT to verify data collection was successful.
"""

import sys
import json
from datetime import datetime, timedelta, date
from pathlib import Path
import pandas as pd
import pytz
from typing import Dict, List, Tuple


# Define tickers to validate
TICKERS = ['iwm', 'spy', 'qqq', 'spx']

# Required columns for daily market data
REQUIRED_DAILY_COLUMNS = ['Open', 'High', 'Low', 'Close', 'Volume']

# Required columns for options data
REQUIRED_OPTIONS_COLUMNS = ['symbol', 'strike', 'expiration', 'optionType', 'lastPrice']


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


def validate_minute_data(ticker: str, result: ValidationResult) -> bool:
    """
    Validate minute-level market data for a ticker.

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
        result.add_warning(f"{ticker.upper()}: Minute data directory not found")
        return True  # Not critical, just a warning

    # Check for today's minute data
    expected_date = get_expected_date()
    minute_file = ticker_dir / f"{ticker}_minute_{expected_date.strftime('%Y%m%d')}.parquet"

    if not minute_file.exists():
        # Check if it's a weekend or market holiday
        if expected_date.weekday() >= 5:
            result.add_info(f"{ticker.upper()}: No minute data expected for {expected_date} (weekend)")
            return True

        result.add_warning(f"{ticker.upper()}: Minute data not found for {expected_date}")
        return True  # Warning, not error

    # Try to read the file
    try:
        df = pd.read_parquet(minute_file)
        print(f"✓ Minute data file exists with {len(df)} records")
        result.add_info(f"{ticker.upper()}: Minute data available for {expected_date} ({len(df)} bars)")
        result.pass_check()

        # Basic validation
        if len(df) < 100:  # Expect at least 100 minute bars for a full trading day
            result.add_warning(
                f"{ticker.upper()}: Minute data seems incomplete ({len(df)} bars, expected ~390 for full day)"
            )
    except Exception as e:
        result.add_warning(f"{ticker.upper()}: Could not read minute data: {e}")

    return True


def validate_options_data(ticker: str, result: ValidationResult) -> bool:
    """
    Validate ETF options data for a ticker.

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

    # Options are fetched intraday, so we look for any file from today
    date_pattern = expected_date.strftime('%Y%m%d')
    options_files = list(options_dir.glob(f"{ticker}_{date_pattern}_*.parquet"))

    if not options_files:
        # Check if it's a weekend
        if expected_date.weekday() >= 5:
            result.add_info(f"{ticker}: No options data expected for {expected_date} (weekend)")
            return True

        # Check for files from previous trading day
        prev_date = expected_date - timedelta(days=1)
        prev_pattern = prev_date.strftime('%Y%m%d')
        prev_files = list(options_dir.glob(f"{ticker}_{prev_pattern}_*.parquet"))

        if prev_files:
            result.add_warning(
                f"{ticker}: No options data for {expected_date}, "
                f"but found {len(prev_files)} files from {prev_date}"
            )
            return True

        result.add_error(f"{ticker}: No options data found for {expected_date}")
        return False

    print(f"✓ Found {len(options_files)} options snapshots for {expected_date}")
    result.add_info(f"{ticker}: {len(options_files)} options snapshots available")
    result.pass_check()

    # Validate the most recent file
    latest_file = sorted(options_files)[-1]
    print(f"  Checking latest file: {latest_file.name}")

    try:
        df = pd.read_parquet(latest_file)
        print(f"✓ Successfully read {len(df)} option contracts")
        result.pass_check()

        # Check for required columns
        missing_columns = [col for col in REQUIRED_OPTIONS_COLUMNS if col not in df.columns]
        if missing_columns:
            result.add_error(f"{ticker}: Options file missing columns: {missing_columns}")
            return False

        print(f"✓ All required columns present")
        result.pass_check()

        # Check data distribution
        calls = len(df[df['optionType'] == 'calls'])
        puts = len(df[df['optionType'] == 'puts'])
        print(f"✓ Contract breakdown: {calls} calls, {puts} puts")

        if calls == 0 or puts == 0:
            result.add_warning(f"{ticker}: Imbalanced options data (calls: {calls}, puts: {puts})")
        else:
            result.pass_check()

        # Check for expirations
        expirations = df['expiration'].nunique()
        print(f"✓ {expirations} unique expiration dates")

        if expirations < 3:
            result.add_warning(f"{ticker}: Limited expiration dates ({expirations})")
        else:
            result.pass_check()

    except Exception as e:
        result.add_error(f"{ticker}: Failed to validate options data: {e}")
        return False

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
    for ticker in TICKERS:
        success = validate_daily_market_data(ticker, result)
        if not success:
            print(f"✗ {ticker.upper()} daily data validation failed")
        else:
            print(f"✓ {ticker.upper()} daily data validation passed")

    # Validate minute data for each ticker
    for ticker in TICKERS:
        validate_minute_data(ticker, result)

    # Validate options data for each ticker (use uppercase for options)
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
