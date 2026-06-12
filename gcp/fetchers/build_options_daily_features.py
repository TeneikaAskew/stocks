#!/usr/bin/env python3
"""Populate the materialized `options_daily_features` table (perf fix).

etf_options_snapshots is ~52 GB once the REALTIME intraday session landed, and
the daily PCR / IV aggregates the research harness needs were being recomputed
by scanning that whole table on every walk-forward run (~20 min for the 2026
slice alone, because the planner seq-scans past the REALTIME rows). This job
runs the EXACT live aggregation ONCE per ticker and upserts the raw per-date
aggregates so the harness reads a ~2,600-row indexed table instead.

Idempotent: ON CONFLICT DO UPDATE. Safe to re-run for incremental days via
--since. Reuses lib.features.experimental.options_derived.build_materialized so
the stored values are byte-identical to what the live path would compute.

    python -m gcp.fetchers.build_options_daily_features \
        --tickers SPY,IWM,QQQ --since 2016-01-01 --until 2026-12-31
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gcp.database import get_engine
from lib.features.experimental.options_derived import build_materialized
from lib.logging_config import setup_logging
import logging

setup_logging()
log = logging.getLogger(__name__)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tickers", default="SPY,IWM,QQQ")
    p.add_argument("--since", default="2016-01-01")
    p.add_argument("--until", default="2026-12-31")
    args = p.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    engine = get_engine()
    total = 0
    for tk in tickers:
        log.info("building options_daily_features for %s [%s..%s]…",
                 tk, args.since, args.until)
        total += build_materialized(engine, tk, args.since, args.until)
    log.info("DONE — upserted %d total rows across %s", total, tickers)


if __name__ == "__main__":
    main()
