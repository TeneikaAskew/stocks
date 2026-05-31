#!/usr/bin/env python3
"""Phase-4 fetcher — cross-asset features (VIX/UST10Y/DXY/Oil/Gold).

Lands into market_data_cross_asset. SCAFFOLD ONLY — backfill not yet
executed. Magnitude Engine Phase 4 will be marked PENDING_BACKFILL in
the results doc until this fetcher's backfill mode has run.

Sources:
  - VIX: AlphaVantage TIME_SERIES_INTRADAY symbol=VIX (5min, 15min)
  - UST 10Y: FRED series DGS10 (daily)
  - DXY: FRED series DTWEXBGS (daily) — Broad Trade-Weighted USD Index
  - Oil: AV daily for USO (proxy)
  - Gold: AV daily for GLD (proxy)

For each (ticker, ts) in the source intraday set, we attach the latest
available cross-asset value at-or-before ts (no lookahead). The
fetcher writes joined rows keyed by (ticker, interval, ts) so the
dataset loader can JOIN by (ticker, ts) directly.

Usage:
    python -m gcp.fetchers.fetch_cross_asset --ticker SPY --intervals 15min,daily

NOT scheduled.
"""
from __future__ import annotations
import argparse
import logging
import os
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import get_engine, upsert_dataframe
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

AV_BASE_URL = "https://www.alphavantage.co/query"
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


# NOTE: full implementation is deliberately stubbed.
# When the first run of this script is needed, fill in the body:
#   1. fetch VIX intraday from AV (function=TIME_SERIES_INTRADAY, symbol=VIX)
#   2. compute 5m delta (close-to-close) and 15-bar rolling z
#   3. fetch UST10Y + DXY from FRED (free, no key for some series; with
#      API key for others — set FRED_API_KEY)
#   4. fetch USO + GLD daily from AV; compute 20-day rolling z
#   5. resample / align to (ticker, ts) of the strat_features intraday
#      grid via merge_asof (with direction="backward")
#   6. upsert market_data_cross_asset

def main():
    raise SystemExit(
        "fetch_cross_asset is a scaffold only. Phase 4 backfill requires "
        "the body of this script to be implemented before dispatch. "
        "Magnitude Engine Phase 4 will report PENDING_BACKFILL until "
        "this fetcher writes rows."
    )


if __name__ == "__main__":
    main()
