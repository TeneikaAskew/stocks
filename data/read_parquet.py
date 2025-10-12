#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick Parquet File Reader

Read and display the first N rows from a parquet file.
Works from the data/ directory - automatically prepends 'data/' to relative paths.

Usage (from project root):
    python data/read_parquet.py options/etfs/SPY_20251011_190154.parquet
    python data/read_parquet.py options/etfs/SPY_20251011_190154.parquet --rows 50
    python data/read_parquet.py options/etfs/SPY_20251011_190154.parquet --columns symbol strike lastPrice delta gamma

    # Or use full path from root
    python data/read_parquet.py data/options/etfs/SPY_20251011_190154.parquet
"""

import sys
import pandas as pd
import argparse
from pathlib import Path

# Fix encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


def read_parquet_file(file_path, num_rows=100, columns=None):
    """
    Read and display parquet file contents.

    Args:
        file_path: Path to parquet file (relative to data/ or absolute)
        num_rows: Number of rows to display (default 100)
        columns: List of specific columns to display (default all)
    """
    file_path = Path(file_path)

    # If path doesn't exist and doesn't start with 'data/', try prepending it
    if not file_path.exists() and not str(file_path).startswith('data'):
        # Get the project root (parent of data directory where this script lives)
        script_dir = Path(__file__).parent  # This is data/
        project_root = script_dir.parent    # This is project root
        file_path = project_root / 'data' / file_path

    if not file_path.exists():
        print(f"❌ Error: File not found: {file_path}")
        return False

    if not file_path.suffix == '.parquet':
        print(f"⚠️  Warning: File doesn't have .parquet extension: {file_path}")

    try:
        # Read parquet file
        print(f"\n{'='*80}")
        print(f"Reading: {file_path.name}")
        print(f"{'='*80}")

        df = pd.read_parquet(file_path)

        # File info
        print(f"\n📊 File Info:")
        print(f"  Total rows: {len(df):,}")
        print(f"  Total columns: {len(df.columns)}")
        print(f"  File size: {file_path.stat().st_size / 1024:.1f} KB")

        # Column info
        print(f"\n📋 Columns ({len(df.columns)}):")
        for i, col in enumerate(df.columns, 1):
            dtype = df[col].dtype
            non_null = df[col].notna().sum()
            print(f"  {i:2d}. {col:25s} ({dtype}) - {non_null:,} non-null")

        # Filter columns if specified
        if columns:
            available_cols = [col for col in columns if col in df.columns]
            missing_cols = [col for col in columns if col not in df.columns]

            if missing_cols:
                print(f"\n⚠️  Missing columns: {', '.join(missing_cols)}")

            if available_cols:
                df = df[available_cols]
                print(f"\n✓ Showing only columns: {', '.join(available_cols)}")
            else:
                print(f"\n❌ None of the specified columns exist in the file")
                return False

        # Display data
        print(f"\n{'='*80}")
        print(f"First {min(num_rows, len(df))} rows:")
        print(f"{'='*80}\n")

        # Set display options for better readability
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        pd.set_option('display.max_colwidth', 30)

        print(df.head(num_rows).to_string(index=True))

        # Summary stats for numeric columns
        numeric_cols = df.select_dtypes(include=['number']).columns
        if len(numeric_cols) > 0 and len(numeric_cols) <= 10:
            print(f"\n{'='*80}")
            print(f"Summary Statistics (numeric columns):")
            print(f"{'='*80}\n")
            print(df[numeric_cols].describe().to_string())

        print(f"\n{'='*80}")
        print(f"✓ Successfully read {len(df):,} rows from {file_path.name}")
        print(f"{'='*80}\n")

        return True

    except Exception as e:
        print(f"\n❌ Error reading file: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Read and display parquet file contents',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Read first 100 rows (default) - paths relative to data/ directory
  python data/read_parquet.py options/etfs/SPY_20251011_190154.parquet

  # Read first 50 rows
  python data/read_parquet.py options/etfs/SPY_20251011_190154.parquet --rows 50

  # Show specific columns only
  python data/read_parquet.py options/etfs/SPY_20251011_190154.parquet --columns symbol strike lastPrice delta gamma

  # Combine options
  python data/read_parquet.py options/etfs/SPY_20251011_190154.parquet --rows 20 --columns symbol strike optionType lastPrice

  # Or use full path from project root
  python data/read_parquet.py data/options/etfs/SPY_20251011_190154.parquet
        """
    )

    parser.add_argument(
        'file_path',
        help='Path to parquet file relative to data/ (e.g., options/etfs/SPY_20251011_190154.parquet)'
    )

    parser.add_argument(
        '--rows', '-n',
        type=int,
        default=100,
        help='Number of rows to display (default: 100)'
    )

    parser.add_argument(
        '--columns', '-c',
        nargs='+',
        help='Specific columns to display (default: all columns)'
    )

    args = parser.parse_args()

    success = read_parquet_file(args.file_path, args.rows, args.columns)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
