#!/usr/bin/env python3
"""
Convert options parquet files to JSON for GitHub Pages deployment
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
CHART_VIEWER_ROOT = PROJECT_ROOT / 'chart-viewer'
DATA_OUTPUT = CHART_VIEWER_ROOT / 'data'

def convert_options_to_json():
    """Convert IWM options combined parquet to daily JSON files"""

    print("=" * 70)
    print("Converting Options Data to JSON")
    print("=" * 70)
    print()

    # Load IWM options combined parquet
    options_file = PROJECT_ROOT / 'data' / 'iwm' / 'options' / 'iwm_av_options_combined.parquet'

    if not options_file.exists():
        print(f"[ERROR] Options file not found: {options_file}")
        return

    print(f"Loading options from: {options_file}")
    df = pd.read_parquet(options_file)

    print(f"   Total contracts: {len(df)}")
    print(f"   Columns: {list(df.columns)}")
    print()

    # Create output directory
    output_dir = DATA_OUTPUT / 'iwm' / 'options'
    output_dir.mkdir(parents=True, exist_ok=True)

    # Group by snapshot_date and save each day
    print("Converting to daily JSON files...")

    dates_converted = []
    total_contracts = 0

    for snapshot_date, group_df in df.groupby('snapshot_date'):
        # Format date as YYYYMMDD
        date_str = snapshot_date.strftime('%Y%m%d')

        # Convert to JSON-friendly format
        contracts = group_df.to_dict('records')

        # Convert datetime fields to strings
        for contract in contracts:
            if 'expiration' in contract and pd.notna(contract['expiration']):
                contract['expiration'] = contract['expiration'].strftime('%Y-%m-%d')
            if 'date' in contract and pd.notna(contract['date']):
                contract['date'] = contract['date'].strftime('%Y-%m-%d')
            if 'snapshot_date' in contract and pd.notna(contract['snapshot_date']):
                contract['snapshot_date'] = contract['snapshot_date'].strftime('%Y-%m-%d')
            if 'fetch_timestamp' in contract:
                del contract['fetch_timestamp']  # Remove internal timestamp

        # Save to JSON
        output_file = output_dir / f'{date_str}_options.json'
        with open(output_file, 'w') as f:
            json.dump(contracts, f)

        dates_converted.append(date_str)
        total_contracts += len(contracts)

        print(f"   [OK] {date_str}: {len(contracts)} contracts")

    print()
    print("=" * 70)
    print(f"Conversion Complete!")
    print("=" * 70)
    print(f"   Dates converted: {len(dates_converted)}")
    print(f"   Total contracts: {total_contracts}")
    print(f"   Output directory: {output_dir}")
    print()
    print(f"   First date: {dates_converted[0] if dates_converted else 'N/A'}")
    print(f"   Last date: {dates_converted[-1] if dates_converted else 'N/A'}")
    print("=" * 70)


if __name__ == '__main__':
    convert_options_to_json()
