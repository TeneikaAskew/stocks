"""Shared helpers for magnitude_engine analysis scripts.

Centralizes the GCS prediction-CSV loader and calendar-key computation
that are used by multiple analysis scripts (check_event_window,
bootstrap_gate_fragility, naive_calendar_lookup, model_vs_calendar_decomp,
implied_vs_realized). Single source of truth so the four scripts can't
drift on path scheme or bucket bin.
"""
from __future__ import annotations
import io
import sys

import pandas as pd
from google.cloud import storage as gcs


def load_predictions(phase: str, ticker: str, tf: str,
                      bucket: str, run_id: str | None) -> pd.DataFrame:
    """Load the latest predictions CSV for a (phase, ticker, tf) cell.

    Filters by run_id when supplied. Raises SystemExit when no matching
    blob exists — callers wrap into a per-cell skip if doing a sweep.
    """
    client = gcs.Client()
    bkt = client.bucket(bucket)
    prefix = f"research/magnitude_engine/{phase}/{ticker.lower()}_{tf}/"
    blobs = [b for b in bkt.list_blobs(prefix=prefix)
             if b.name.endswith(".csv") and "predictions_" in b.name]
    if not blobs:
        raise SystemExit(f"no prediction CSV under gs://{bucket}/{prefix}")
    if run_id:
        blobs = [b for b in blobs if run_id in b.name]
        if not blobs:
            raise SystemExit(
                f"no prediction CSV matching run_id={run_id} under gs://{bucket}/{prefix}"
            )
    target = sorted(blobs, key=lambda b: b.name)[-1]
    print(f"loading predictions: gs://{bucket}/{target.name}", file=sys.stderr)
    return pd.read_csv(io.BytesIO(target.download_as_bytes()))


def calendar_keys(ts_series, bucket_minutes: int = 30):
    """Compute (day_of_week, time_bucket) keys for each timestamp.

    bucket_minutes = 30 → 13 RTH buckets per day × 5 DoW = 65 cells.
    At ~250 trading days per year × 8 training years ≈ 2000 days, that's
    ~30 days of samples per cell — enough for stable rates.

    Returns (dow_array, bucket_array) as numpy ints.
    """
    ts_et = pd.to_datetime(ts_series, utc=True).dt.tz_convert("America/New_York")
    dow = ts_et.dt.dayofweek.values
    minutes_of_day = ts_et.dt.hour.values * 60 + ts_et.dt.minute.values
    bucket = (minutes_of_day // bucket_minutes).astype(int)
    return dow, bucket
