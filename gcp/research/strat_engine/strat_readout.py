"""Stage 6 — Read-out — `strat_readout.py`.

Assembles the "right now" view for a ticker:
  - Four probabilities at each available TF (from the latest scored bar)
  - The FTFC stack and continuity score
  - The top drivers for the current read (from Stage 3 corr output)

Output: JSON (the rulebook-friendly format). Other forms (dashboard tile,
Pine label feed) are open decision #5 — table/JSON default per PRD.
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.database import get_engine
from gcp.research.strat_engine.strat_config import (
    TICKERS, TIMEFRAMES, LABEL_CLASSES, DEFAULT_TRAIN_UNTIL,
    GCS_BUCKET_DEFAULT, gcs_model_prefix,
)
from gcp.research.strat_engine.strat_ftfc_assemble import (
    assemble_ftfc, load_model_and_features,
)
from google.cloud import storage as gcs
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


def _gcs_bucket():
    return gcs.Client().bucket(os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT))


def _upload(content: bytes, blob_path: str, ctype="application/json"):
    _gcs_bucket().blob(blob_path).upload_from_string(content, content_type=ctype)


def _latest_corr_drivers(ticker: str, tf: str, top_n: int = 5) -> dict:
    """Pull the most recent Stage 3 output for this (ticker, tf) and return
    the top-N driver per class. Returns {} if no corr file exists yet."""
    prefix = gcs_model_prefix(ticker, tf)
    blobs = sorted(_gcs_bucket().list_blobs(prefix=f"{prefix}/corr_"),
                   key=lambda b: b.time_created or b.name)
    if not blobs:
        return {}
    latest = blobs[-1]
    payload = json.loads(latest.download_as_bytes().decode())
    rankings = payload.get("rankings", {})
    return {
        cls: [
            {"feature": r["feature"], "mi": r["mi"], "direction": r["direction"]}
            for r in rankings.get(cls, [])[:top_n]
        ]
        for cls in LABEL_CLASSES
    }


def build_readout(engine, ticker: str, since: str) -> dict:
    log.info("=" * 70)
    log.info("Stage 6 READOUT  ticker=%s  since=%s", ticker, since)
    log.info("=" * 70)

    # Get the FTFC-assembled stack and pick the LAST row (most recent bar)
    ftfc = assemble_ftfc(engine, ticker, since)
    if len(ftfc) == 0:
        raise RuntimeError("no FTFC rows — Stage 4/5 outputs missing")
    last = ftfc.iloc[-1]
    log.info("most recent bar: ts=%s", last["ts"])

    per_tf = {}
    for tf in TIMEFRAMES:
        col_2u = f"{tf}_p_2u"
        if col_2u not in ftfc.columns: continue
        if pd.isna(last[col_2u]): continue
        per_tf[tf] = {
            "p_inside":  round(float(last[f"{tf}_p_1"]), 4),
            "p_2u":      round(float(last[f"{tf}_p_2u"]), 4),
            "p_2d":      round(float(last[f"{tf}_p_2d"]), 4),
            "p_outside": round(float(last[f"{tf}_p_3"]), 4),
            "top_class": str(last[f"{tf}_top"]),
            "directional_edge": round(float(last[col_2u] - last[f"{tf}_p_2d"]), 4),
        }

    # Pull drivers from the FINEST TF that has a corr file
    drivers = {}
    for tf in TIMEFRAMES:
        if tf in per_tf:
            drivers = _latest_corr_drivers(ticker, tf, top_n=5)
            drivers_source_tf = tf
            break
    else:
        drivers_source_tf = None

    readout = {
        "ticker": ticker,
        "as_of_bar_ts": str(last["ts"]),
        "per_tf": per_tf,
        "ftfc": {
            "continuity_score": round(float(last["continuity_score"]), 4),
            "aligned_direction": str(last["aligned_direction"]),
            "tfs_in_stack": list(per_tf.keys()),
        },
        "drivers": {"source_tf": drivers_source_tf, "top_per_class": drivers},
        "generated_at": pd.Timestamp.utcnow().isoformat(),
    }

    log.info("READOUT for %s @ %s:", ticker, last["ts"])
    log.info("  FTFC: continuity=%+.3f  aligned=%s",
             readout["ftfc"]["continuity_score"],
             readout["ftfc"]["aligned_direction"])
    for tf, row in per_tf.items():
        log.info("  %-3s  2U:%.1f%%  2D:%.1f%%  1:%.1f%%  3:%.1f%%   top=%s  edge=%+.3f",
                 tf, row["p_2u"]*100, row["p_2d"]*100,
                 row["p_inside"]*100, row["p_outside"]*100,
                 row["top_class"], row["directional_edge"])

    blob = f"research/strat_engine/_readout/{ticker.lower()}_{int(time.time())}.json"
    _upload(json.dumps(readout, indent=2, default=str).encode(), blob)
    log.info("saved: gs://%s/%s",
             os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT), blob)
    return readout


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--since", default=DEFAULT_TRAIN_UNTIL)
    args = p.parse_args()
    engine = get_engine()
    build_readout(engine, args.ticker, args.since)


if __name__ == "__main__":
    main()
