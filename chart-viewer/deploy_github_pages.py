#!/usr/bin/env python3
"""
Convert parquet files to JSON for GitHub Pages deployment
This allows the chart viewer to work without a backend server
"""

import pandas as pd
import json
from pathlib import Path
import sys

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
CHART_VIEWER_ROOT = Path(__file__).parent
DATA_OUTPUT = CHART_VIEWER_ROOT / 'data'

DATA_SOURCES = {
    'iwm': PROJECT_ROOT / 'data' / 'iwm' / 'minute',
    'spy': PROJECT_ROOT / 'data' / 'spy' / 'minute',
    'qqq': PROJECT_ROOT / 'data' / 'qqq' / 'minute',
}


def parse_filename_date(filename):
    """Extract date from filename"""
    parts = filename.stem.split('_')
    if len(parts) >= 3:
        return parts[2]  # YYYYMMDD
    return None


def convert_parquet_to_json(parquet_file, ticker):
    """Convert a parquet file to JSON format"""
    try:
        # Read parquet file
        df = pd.read_parquet(parquet_file)

        # Normalize column names
        df.columns = [col.capitalize() if col.lower() in ['open', 'high', 'low', 'close', 'volume']
                      else col for col in df.columns]

        # Reset index to make timestamp a column
        df = df.reset_index()

        # Find timestamp column
        timestamp_cols = ['Datetime', 'datetime', 'index']
        timestamp_col = next((col for col in timestamp_cols if col in df.columns), df.columns[0])

        # Convert to Unix timestamp (seconds)
        df['time'] = pd.to_datetime(df[timestamp_col]).astype(int) // 10**9

        # Select and rename columns
        result = df[['time', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
        result.columns = ['time', 'open', 'high', 'low', 'close', 'volume']

        # Extract date from filename
        date_str = parse_filename_date(parquet_file)

        if not date_str:
            print(f"  ⚠️  Could not extract date from {parquet_file.name}")
            return None

        # Create output directory
        output_dir = DATA_OUTPUT / ticker.lower()
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save as JSON (1-minute data)
        output_file = output_dir / f"{date_str}_1min.json"
        result.to_json(output_file, orient='records')

        print(f"  ✓ {parquet_file.name} -> {output_file.name} ({len(result)} candles)")

        return {
            'date': date_str,
            'candles': len(result),
            'file': output_file.name
        }

    except Exception as e:
        print(f"  ✗ Error converting {parquet_file.name}: {e}")
        return None


def create_dates_index(ticker, converted_files):
    """Create dates.json index file for a ticker"""
    dates = sorted([f['date'] for f in converted_files if f])

    output_dir = DATA_OUTPUT / ticker.lower()
    output_file = output_dir / 'dates.json'

    with open(output_file, 'w') as f:
        json.dump(dates, f)

    print(f"  ✓ Created {output_file} with {len(dates)} dates")

    return dates


def main():
    print("=" * 70)
    print("GitHub Pages Deployment - Convert Parquet to JSON")
    print("=" * 70)
    print()

    total_converted = 0
    total_failed = 0

    # Process each ticker
    for ticker, source_path in DATA_SOURCES.items():
        print(f"📊 Processing {ticker.upper()}...")

        if not source_path.exists():
            print(f"  ⚠️  Source directory not found: {source_path}")
            print()
            continue

        # Get all parquet files
        parquet_files = sorted(source_path.glob('*.parquet'))

        if not parquet_files:
            print(f"  ⚠️  No parquet files found in {source_path}")
            print()
            continue

        print(f"  Found {len(parquet_files)} parquet files")

        # Convert each file
        converted = []
        for pf in parquet_files:
            result = convert_parquet_to_json(pf, ticker)
            if result:
                converted.append(result)
                total_converted += 1
            else:
                total_failed += 1

        # Create dates index
        if converted:
            create_dates_index(ticker, converted)

        print()

    # Update config.js
    config_file = CHART_VIEWER_ROOT / 'src' / 'config.js'

    print("⚙️  Updating configuration...")

    if config_file.exists():
        with open(config_file, 'r') as f:
            content = f.read()

        # Update USE_LOCAL_API to false
        content = content.replace('USE_LOCAL_API: true', 'USE_LOCAL_API: false')

        with open(config_file, 'w') as f:
            f.write(content)

        print("  ✓ Updated src/config.js (USE_LOCAL_API = false)")
    else:
        print(f"  ⚠️  Config file not found: {config_file}")

    print()
    print("=" * 70)
    print("✅ Deployment Preparation Complete!")
    print("=" * 70)
    print(f"Total files converted: {total_converted}")
    print(f"Total failures: {total_failed}")
    print()
    print("📁 Output location: chart-viewer/data/")
    print()
    print("🚀 Next steps:")
    print("  1. Commit and push the chart-viewer directory")
    print("  2. Enable GitHub Pages in repository settings")
    print("  3. Set source to the chart-viewer folder")
    print("  4. Access at: https://yourusername.github.io/stocks/chart-viewer/")
    print()
    print("💡 To revert to local API mode, change USE_LOCAL_API to true in src/config.js")
    print("=" * 70)


if __name__ == '__main__':
    main()
