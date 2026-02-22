#!/usr/bin/env python3
"""
Trade logger — appends trades to daily parquet files.

Used by the signal monitor and can also be fed manually.
Stores to local filesystem or GCS bucket.
"""

import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd


class TradeLogger:
    """Log trades to daily parquet files."""

    def __init__(self, output_dir: str = 'data/trades'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _daily_file(self, date=None) -> Path:
        if date is None:
            date = datetime.now().date()
        return self.output_dir / f'{date}.parquet'

    def log_trade(self, trade_data: dict):
        """Append a trade record to today's parquet file.

        trade_data should include:
            ticker, direction, entry_time, entry_price, exit_time,
            exit_price, exit_reason, signal_strength, position_size,
            return_pct, conditions_met, strat_combo, ftfc_score
        """
        row = pd.DataFrame([trade_data])
        path = self._daily_file()

        if path.exists():
            existing = pd.read_parquet(path)
            combined = pd.concat([existing, row], ignore_index=True)
        else:
            combined = row

        combined.to_parquet(path, index=False)

    def get_daily_trades(self, date=None) -> pd.DataFrame:
        """Load trades for a specific date."""
        path = self._daily_file(date)
        if path.exists():
            return pd.read_parquet(path)
        return pd.DataFrame()

    def get_weekly_trades(self, week_end_date=None) -> pd.DataFrame:
        """Load all trades from the past 7 days."""
        if week_end_date is None:
            week_end_date = datetime.now().date()

        frames = []
        for i in range(7):
            date = week_end_date - pd.Timedelta(days=i)
            df = self.get_daily_trades(date)
            if not df.empty:
                frames.append(df)

        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def get_all_trades(self) -> pd.DataFrame:
        """Load all logged trades."""
        files = sorted(self.output_dir.glob('*.parquet'))
        if not files:
            return pd.DataFrame()
        frames = [pd.read_parquet(f) for f in files]
        return pd.concat(frames, ignore_index=True)
