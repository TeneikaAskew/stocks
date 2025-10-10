"""
Data Loader Module
Handles loading, parsing, and preprocessing of strategy CSV files
"""
import pandas as pd
import numpy as np
import json
import os
import glob
from datetime import datetime, timedelta
import sys
import warnings

# Add parent directory to path for config import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


class DataLoader:
    """
    Loads and preprocesses options strategy data from CSV exports
    """

    def __init__(self, data_path=None):
        """
        Initialize data loader

        Args:
            data_path: Path to directory containing CSV files
        """
        self.data_path = data_path or config.DATA_PATH
        self.data = {}  # Dictionary to store DataFrames by strategy
        self.unified_df = None  # Combined DataFrame across all strategies
        self.incomplete_df = None  # DataFrame of incomplete/excluded trades

    def load_all_strategies(self, verbose=True):
        """
        Load all strategy CSV files from data directory

        Returns:
            dict: Dictionary with strategy names as keys and DataFrames as values
        """
        if verbose:
            print(f"\n{'='*60}")
            print("Loading Strategy Data")
            print(f"{'='*60}")

        # Find all CSV files in data directory
        csv_files = glob.glob(os.path.join(self.data_path, "*.csv"))

        if not csv_files:
            print(f"⚠️  No CSV files found in {self.data_path}")
            return self.data

        for csv_file in csv_files:
            # Extract strategy name from filename
            filename = os.path.basename(csv_file)

            # Try to match with known strategies
            strategy_name = None
            for strategy in config.STRATEGIES:
                if strategy.lower().replace(' ', '') in filename.lower().replace(' ', ''):
                    strategy_name = strategy
                    break

            if not strategy_name:
                if verbose:
                    print(f"⚠️  Skipping {filename} - not a recognized strategy")
                continue

            try:
                # Load CSV
                df = pd.read_csv(csv_file, low_memory=False)

                if verbose:
                    print(f"✓ Loaded {strategy_name}: {len(df)} rows, {len(df.columns)} columns")

                # Add strategy column if not present
                if 'Strategy' not in df.columns:
                    df['Strategy'] = strategy_name

                self.data[strategy_name] = df

            except Exception as e:
                if verbose:
                    print(f"✗ Error loading {filename}: {str(e)}")

        if verbose:
            print(f"\nTotal strategies loaded: {len(self.data)}")
            print(f"{'='*60}\n")

        return self.data

    def parse_json_arrays(self, df, verbose=False):
        """
        Parse JSON array columns (Strike_Hit, indicators, OHLC, etc.)

        Args:
            df: DataFrame to process
            verbose: Print progress

        Returns:
            DataFrame with parsed arrays
        """
        json_columns = config.TRACKING_COLUMNS['arrays'] + config.TRACKING_COLUMNS['indicators']

        for col in json_columns:
            if col not in df.columns:
                continue

            if verbose:
                print(f"  Parsing {col}...")

            def parse_json_safe(val):
                """Safely parse JSON, handling errors and converting to numeric where appropriate"""
                if pd.isna(val) or val == '' or val is None:
                    return None
                try:
                    if isinstance(val, str):
                        parsed = json.loads(val)
                        # If it's a list, try to convert elements to float
                        if isinstance(parsed, list):
                            numeric_list = []
                            for item in parsed:
                                if item is None or item == 'NO_DATA' or item == '':
                                    numeric_list.append(None)
                                else:
                                    try:
                                        numeric_list.append(float(item))
                                    except (ValueError, TypeError):
                                        numeric_list.append(item)
                            return numeric_list
                        return parsed
                    return val
                except (json.JSONDecodeError, TypeError):
                    return None

            df[f'{col}_parsed'] = df[col].apply(parse_json_safe)

        return df

    def calculate_daily_profits(self, df, verbose=False):
        """
        Calculate daily profit percentages from Strike_Hit or Max_Favorable arrays

        Args:
            df: DataFrame with parsed arrays
            verbose: Print progress

        Returns:
            DataFrame with daily profit columns
        """
        if verbose:
            print("  Calculating daily profits...")

        # Use Strike_Hit array if available, otherwise Max_Favorable
        profit_source = 'Strike_Hit_parsed' if 'Strike_Hit_parsed' in df.columns else 'Max_Favorable_parsed'

        if profit_source not in df.columns:
            return df

        # Extract daily profits (Day0 through Day5)
        for day in range(6):
            def extract_profit(x):
                """Extract profit safely, handling NO_DATA and None values"""
                if not x or not isinstance(x, list) or len(x) <= day:
                    return np.nan
                val = x[day]
                if val is None or val == 'NO_DATA' or val == '':
                    return np.nan
                try:
                    return float(val) * 100
                except (ValueError, TypeError):
                    return np.nan

            df[f'Day{day}_Profit_Pct'] = df[profit_source].apply(extract_profit)

        # Calculate peak profit across all days
        profit_cols = [f'Day{d}_Profit_Pct' for d in range(6)]
        df['Peak_Profit_Pct'] = df[profit_cols].max(axis=1)

        # Handle all-NA rows to avoid FutureWarning
        # Suppress FutureWarning for idxmax with all-NA values
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore',
                                  message='.*idxmax with all-NA values.*',
                                  category=FutureWarning)

            # Check if each row has any non-NA values first
            has_data = df[profit_cols].notna().any(axis=1)

            # Initialize with default value
            df['Peak_Profit_Day'] = '0'

            # Only calculate idxmax for rows with data
            if has_data.sum() > 0:
                peak_day_series = df.loc[has_data, profit_cols].idxmax(axis=1)
                df.loc[has_data, 'Peak_Profit_Day'] = peak_day_series.str.replace('Day', '').str.replace('_Profit_Pct', '')

        # Calculate average profit
        df['Avg_Profit_Pct'] = df[profit_cols].mean(axis=1)

        return df

    def calculate_time_to_hit(self, df, verbose=False):
        """
        Calculate days until strike first hit from Strike_Hit array

        Args:
            df: DataFrame with parsed arrays
            verbose: Print progress

        Returns:
            DataFrame with time_to_hit column
        """
        if verbose:
            print("  Calculating time to strike hit...")

        if 'Strike_Hit_parsed' not in df.columns:
            return df

        def find_first_hit_day(strike_array):
            """Find first day where strike was hit (positive value for bullish, negative for bearish)"""
            if not strike_array or not isinstance(strike_array, list):
                return np.nan

            for day_idx, value in enumerate(strike_array):
                if value is None or value == 'NO_DATA' or value == '':
                    continue
                try:
                    val_float = float(value)
                    # Strike hit if value is non-zero (positive or negative depending on strategy)
                    if abs(val_float) > 0.0001:  # Account for floating point errors
                        return day_idx
                except (ValueError, TypeError):
                    continue

            return np.nan

        df['Time_To_Hit_Days'] = df['Strike_Hit_parsed'].apply(find_first_hit_day)

        # Flag whether strike was ever hit
        df['Strike_Ever_Hit'] = df['Time_To_Hit_Days'].notna()

        return df

    def enrich_earnings_timing(self, df, verbose=False):
        """
        Add earnings timing features (days to earnings, pre/post flags)

        Args:
            df: DataFrame with date columns
            verbose: Print progress

        Returns:
            DataFrame with earnings timing columns
        """
        if verbose:
            print("  Enriching earnings timing data...")

        # Ensure date columns are datetime
        date_columns = ['Run Date', 'nextEPSDate', 'expDate']
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')

        # Calculate days to earnings
        if 'Run Date' in df.columns and 'nextEPSDate' in df.columns:
            df['Days_To_Earnings'] = (df['nextEPSDate'] - df['Run Date']).dt.days

            # Classify by earnings window
            df['Earnings_Window'] = pd.cut(
                df['Days_To_Earnings'],
                bins=[-999, 2, 5, 10, 20, 999],
                labels=['0-2 days', '3-5 days', '6-10 days', '11-20 days', '21+ days']
            )

            # Pre vs post earnings flag
            df['Is_Pre_Earnings'] = df['Days_To_Earnings'] >= 0

        # Release time flags
        if 'releaseTime' in df.columns:
            # Convert to string first if needed
            df['releaseTime'] = df['releaseTime'].astype(str)
            df['Is_Before_Open'] = df['releaseTime'].str.contains('beforeOpen', case=False, na=False)
            df['Is_After_Close'] = df['releaseTime'].str.contains('afterClose', case=False, na=False)

        return df

    def calculate_derived_metrics(self, df, verbose=False):
        """
        Calculate additional derived metrics

        Args:
            df: DataFrame
            verbose: Print progress

        Returns:
            DataFrame with derived metrics
        """
        if verbose:
            print("  Calculating derived metrics...")

        # Win/Loss flag
        if 'Peak_Profit_Pct' in df.columns:
            df['Is_Winner'] = df['Peak_Profit_Pct'] > 0
            df['Is_Big_Winner'] = df['Peak_Profit_Pct'] > config.HIGH_PROFIT_PCT

        # Strike positioning (OTM %)
        if 'strike' in df.columns:
            # For single-leg strategies
            if 'Day0_Check' in df.columns:
                df['Strike_OTM_Pct'] = ((df['strike'] - df['Day0_Check']) / df['Day0_Check']) * 100
        elif 'longStrike' in df.columns:
            # For spread strategies
            if 'Day0_Check' in df.columns:
                df['Strike_OTM_Pct'] = ((df['longStrike'] - df['Day0_Check']) / df['Day0_Check']) * 100

        # Days to expiration at entry
        if 'Run Date' in df.columns and 'expDate' in df.columns:
            df['Days_To_Exp_At_Entry'] = (df['expDate'] - df['Run Date']).dt.days

        # Strategy categorization
        df['Strategy_Type'] = df['Strategy'].apply(self._categorize_strategy)

        return df

    @staticmethod
    def _categorize_strategy(strategy):
        """Categorize strategy as bullish, bearish, or neutral"""
        if strategy in config.BULLISH_STRATEGIES:
            return 'Bullish'
        elif strategy in config.BEARISH_STRATEGIES:
            return 'Bearish'
        elif strategy in config.NEUTRAL_STRATEGIES:
            return 'Neutral'
        return 'Unknown'

    def create_unified_dataset(self, verbose=True):
        """
        Combine all strategy DataFrames into single unified dataset

        Returns:
            DataFrame: Combined dataset with all strategies
        """
        if verbose:
            print(f"\n{'='*60}")
            print("Creating Unified Dataset")
            print(f"{'='*60}")

        if not self.data:
            print("⚠️  No data loaded. Run load_all_strategies() first.")
            return None

        # Process each strategy DataFrame
        processed_dfs = []
        for strategy, df in self.data.items():
            if verbose:
                print(f"\nProcessing {strategy}...")

            # Make a copy to avoid modifying original
            df_copy = df.copy()

            # Apply all transformations
            df_copy = self.parse_json_arrays(df_copy, verbose=verbose)
            df_copy = self.calculate_daily_profits(df_copy, verbose=verbose)
            df_copy = self.calculate_time_to_hit(df_copy, verbose=verbose)
            df_copy = self.enrich_earnings_timing(df_copy, verbose=verbose)
            df_copy = self.calculate_derived_metrics(df_copy, verbose=verbose)

            processed_dfs.append(df_copy)

        # Combine all DataFrames
        self.unified_df = pd.concat(processed_dfs, ignore_index=True)

        # Separate incomplete trades (no profit data) before filtering
        initial_count = len(self.unified_df)
        if 'Peak_Profit_Pct' in self.unified_df.columns:
            # Save incomplete trades for analysis
            self.incomplete_df = self.unified_df[self.unified_df['Peak_Profit_Pct'].isna()].copy()

            # Keep only complete trades
            self.unified_df = self.unified_df[self.unified_df['Peak_Profit_Pct'].notna()].copy()
            filtered_count = initial_count - len(self.unified_df)

            if verbose and filtered_count > 0:
                print(f"\n⚠️  Filtered out {filtered_count} incomplete trades (no profit data)")
                print(f"    Incomplete trades saved for inspection")

        if verbose:
            print(f"\n{'='*60}")
            print(f"✓ Unified dataset created: {len(self.unified_df)} total rows")
            print(f"{'='*60}\n")

        return self.unified_df

    def get_strategy_df(self, strategy_name):
        """Get DataFrame for specific strategy"""
        return self.data.get(strategy_name)

    def get_unified_df(self):
        """Get unified DataFrame across all strategies"""
        return self.unified_df

    def get_incomplete_df(self):
        """Get DataFrame of incomplete/excluded trades"""
        return self.incomplete_df

    def summary_stats(self):
        """Print summary statistics of loaded data"""
        if not self.data:
            print("No data loaded.")
            return

        print(f"\n{'='*60}")
        print("Data Summary Statistics")
        print(f"{'='*60}\n")

        for strategy, df in self.data.items():
            print(f"{strategy}:")
            print(f"  Total Trades: {len(df)}")
            if 'Strike_Ever_Hit' in df.columns:
                hit_rate = df['Strike_Ever_Hit'].mean() * 100
                print(f"  Hit Rate: {hit_rate:.1f}%")
            if 'Peak_Profit_Pct' in df.columns:
                winners = df['Peak_Profit_Pct'] > 0
                print(f"  Win Rate: {winners.mean() * 100:.1f}%")
                print(f"  Avg Profit: {df.loc[winners, 'Peak_Profit_Pct'].mean():.2f}%")
                print(f"  Avg Loss: {df.loc[~winners, 'Peak_Profit_Pct'].mean():.2f}%")
            print()

        if self.unified_df is not None:
            print(f"Combined Dataset: {len(self.unified_df)} total trades across {len(self.data)} strategies")

        print(f"{'='*60}\n")


if __name__ == "__main__":
    # Test the data loader
    loader = DataLoader()
    loader.load_all_strategies()
    loader.create_unified_dataset()
    loader.summary_stats()
