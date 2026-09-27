"""Shared helpers for magnitude_engine analysis scripts.

Centralizes the GCS prediction-CSV loader and calendar-key computation
that are used by multiple analysis scripts (check_event_window,
bootstrap_gate_fragility, naive_calendar_lookup, model_vs_calendar_decomp,
implied_vs_realized). Single source of truth so the four scripts can't
drift on path scheme or bucket bin.
"""
from __future__ import annotations
import io
import json
import sys

import pandas as pd
from google.cloud import storage as gcs

from gcp.research.magnitude_engine.evaluation_windows import WINDOWS


def add_research_arg(p) -> None:
    """Register --research on a post-hoc analysis script.

    A run under non-default label semantics writes its artifacts to a
    sibling `_research/<slug>/` root (mag_config.gcs_run_prefix), so every
    consumer of the prediction CSVs needs to be told which experiment it is
    reading. Without it these scripts search only the canonical prefix and
    exit claiming the run has no predictions — including gate 7
    (implied_vs_realized_check), which is required post-hoc evidence for
    exactly the research runs the namespace exists to hold.
    """
    p.add_argument(
        "--research", default=None, metavar="SLUG",
        help="Read from the research namespace with this slug (e.g. "
             "'excursion', 't0.35_0.75_1.25', 'put__t0.35_0.75_1.25') "
             "instead of the canonical body-label prefix. The slug is the "
             "path segment mag_config.research_namespace() produced for the "
             "run, and it is recorded in the run's walk_forward JSON as "
             "label_mode + thresholds.")
    p.add_argument(
        "--evaluation-window", default="development", choices=tuple(WINDOWS),
        help="Read the artifacts of this evaluation window "
             "(evaluation_windows.py). Validation and final-test runs live "
             "under their own _windows/<name>/ root, so a listing of the "
             "development prefix never reaches them; the run's walk_forward "
             "JSON records the window as split_name.")


def apply_research_contract(research: str | None,
                            label_mode: str | None = None) -> tuple[str, tuple]:
    """Adopt the label contract the selected research namespace stands for.

    Returns `(label_mode, thresholds)` and, for a non-default threshold set,
    exports MAG_THRESHOLDS so the dataset builder buckets the SAME way the
    model was trained. Without this an analysis loads the right predictions
    and then rebuilds `body` labels at the default cut points, scoring a model
    against a target it never predicted (Codex on #1055).

    `label_mode` is the value the caller's own --label-mode carries, when it
    has one. It must agree with the namespace: a `put` run evaluated with
    `body` realizations produces a plausible and invalid verdict, so a
    conflict is refused rather than silently resolved either way.
    """
    import os
    from gcp.research.magnitude_engine.mag_config import (
        DEFAULT_LABEL_MODE, MAGNITUDE_THRESHOLDS, parse_research_namespace)

    if not research:
        # The canonical prefix IS the serving contract: body labels at the
        # default cut points. Accepting --label-mode=put here would score a
        # canonical body run against put realizations and put IV — the same
        # invalid verdict the mismatch check below refuses, arrived at from
        # the other side (Codex on #1055).
        if label_mode is not None and label_mode != DEFAULT_LABEL_MODE:
            raise SystemExit(
                f"--label-mode={label_mode} needs the matching --research "
                f"namespace: without it the canonical prefix is read, and that "
                f"holds {DEFAULT_LABEL_MODE} labels at "
                f"{tuple(MAGNITUDE_THRESHOLDS)}. Pass --research=... for the "
                f"run you mean.")
        resolved, thresholds = DEFAULT_LABEL_MODE, MAGNITUDE_THRESHOLDS
    else:
        resolved, thresholds = parse_research_namespace(research)
        if label_mode is not None and label_mode != resolved:
            raise SystemExit(
                f"--label-mode={label_mode} contradicts --research={research}, "
                f"which was trained with label_mode={resolved}. The namespace "
                f"carries the contract; drop --label-mode or make it match.")
    # Replace, never merely add: an ambient MAG_THRESHOLDS left in place for a
    # default-threshold contract would have the dataset bucket at the ambient
    # values while this function reports the defaults, so the analysis would
    # describe a different target than the predictions it loaded.
    if tuple(thresholds) != tuple(MAGNITUDE_THRESHOLDS):
        os.environ["MAG_THRESHOLDS"] = ",".join(repr(float(v)) for v in thresholds)
    else:
        os.environ.pop("MAG_THRESHOLDS", None)
    return resolved, tuple(thresholds)


def research_prefix(phase: str, ticker: str, tf: str,
                    research: str | None = None,
                    evaluation_window: str | None = None) -> str:
    """GCS prefix for a cell's artifacts: canonical, research, or windowed.

    Mirrors mag_config.gcs_run_prefix (which the writer uses) with the slug
    already resolved: a `_windows/<name>/` root for any window but
    development, then a `_research/<slug>/` root, then the cell.
    """
    root = "research/magnitude_engine"
    if evaluation_window not in (None, "development"):
        if evaluation_window not in WINDOWS:
            raise ValueError(
                f"unknown evaluation window {evaluation_window!r}; "
                f"expected one of {list(WINDOWS)}")
        root = f"{root}/_windows/{evaluation_window}"
    if research:
        root = f"{root}/_research/{research}"
    return f"{root}/{phase}/{ticker.lower()}_{tf}/"


def load_predictions(phase: str, ticker: str, tf: str,
                      bucket: str, run_id: str | None,
                      research: str | None = None,
                      evaluation_window: str | None = None) -> pd.DataFrame:
    """Load the latest predictions CSV for a (phase, ticker, tf) cell.

    Filters by run_id when supplied. `research` selects the namespace a
    non-default-label run wrote to. Raises SystemExit when no matching blob
    exists — callers wrap into a per-cell skip if doing a sweep.
    """
    client = gcs.Client()
    bkt = client.bucket(bucket)
    prefix = research_prefix(phase, ticker, tf, research, evaluation_window)
    blobs = [b for b in bkt.list_blobs(prefix=prefix)
             if b.name.endswith(".csv") and "predictions_" in b.name]
    if not blobs:
        raise SystemExit(f"no prediction CSV under gs://{bucket}/{prefix}")
    if run_id:
        # Exact filename, not a substring: `r1` must not select
        # predictions_r10.csv, whose run carries a different readiness
        # version (Codex P2 on #1187).
        want = f"predictions_{run_id}.csv"
        blobs = [b for b in blobs if b.name.rsplit("/", 1)[-1] == want]
        if not blobs:
            raise SystemExit(
                f"no prediction CSV matching run_id={run_id} under gs://{bucket}/{prefix}"
            )
    target = sorted(blobs, key=lambda b: b.name)[-1]
    print(f"loading predictions: gs://{bucket}/{target.name}", file=sys.stderr)
    return pd.read_csv(io.BytesIO(target.download_as_bytes()))


def load_run_readiness_version(phase: str, ticker: str, tf: str,
                               bucket: str, run_id: str,
                               research: str | None = None,
                               evaluation_window: str | None = None) -> str | None:
    """The production_readiness_version the walk-forward run recorded.

    Read from that run's own walk_forward_<run_id>.json, so an analysis of
    an older run carries the policy the run was produced under rather than
    the one the code holds today. None means the run predates the policy;
    that is a fact about the run, not a default. A missing summary raises,
    like a missing predictions CSV.
    """
    name = (research_prefix(phase, ticker, tf, research, evaluation_window)
            + f"walk_forward_{run_id}.json")
    blob = gcs.Client().bucket(bucket).blob(name)
    if not blob.exists():
        raise SystemExit(f"no walk-forward summary at gs://{bucket}/{name}")
    return json.loads(blob.download_as_bytes()).get("production_readiness_version")


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
