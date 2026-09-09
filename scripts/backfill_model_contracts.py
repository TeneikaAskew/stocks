#!/usr/bin/env python3
"""Write CONTRACT.json for production model artifacts published before it existed.

mag_inference refuses to score a model whose artifact does not state its own
label contract (see mag_config.CONTRACT_BLOB). Artifacts promoted before that
blob existed carry model.joblib + feature_cols.txt + VERSION and nothing that
says what their buckets MEAN, so they need one written once.

The value is not a blanket assumption, and the earlier version of this
docstring overstated it (Codex P2 on #1074). Before #1055 the single-cell
`--phase --ticker --tf` path DID forward `--label-mode` into training, and
the persist path performed no contract check, so `--label-mode=excursion
--persist-production-model` on that path would have promoted a non-`body`
model with nothing recording the fact. A legacy artifact is therefore NOT
`body` merely by virtue of being old.

What is provable is per-run, so this script refuses to stamp anything it has
not been told is audited:

  * `--audited-run-id` must name each run explicitly. An artifact whose
    LATEST points elsewhere is skipped, loudly.
  * A named run must also span more than one cell. The single-cell dispatch
    path writes exactly one, and that path is the one that could carry a
    non-default label, so a one-cell run is refused unless the operator
    overrides with --allow-single-cell-run after checking its walk-forward
    summary by hand.

magnitude-engine-c49qf satisfies both: it wrote all nine cells (SPY, QQQ,
IWM x 5m, 15m, 30m), which only the Cloud Run task-parallel path does, and
that path called walk_forward() WITHOUT label_mode -- finding 1 of #1055 --
so it necessarily trained the `body` default at the then-constant
MAGNITUDE_THRESHOLDS.

Refuses to overwrite an existing CONTRACT.json: one that is already there was
written by the walk-forward that produced the model and is authoritative.

    python -m scripts.backfill_model_contracts \
        --audited-run-id magnitude-engine-c49qf
    python -m scripts.backfill_model_contracts \
        --audited-run-id magnitude-engine-c49qf --commit
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gcp.research.magnitude_engine.mag_config import (  # noqa: E402
    TICKERS, TIMEFRAMES, CONTRACT_BLOB, contract_payload,
    DEFAULT_LABEL_MODE, MAGNITUDE_THRESHOLDS, GCS_BUCKET_DEFAULT,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", action="store_true",
                    help="actually write; default is a dry run")
    ap.add_argument("--audited-run-id", action="append", default=[],
                    metavar="RUN_ID", required=True,
                    help="a run whose label contract you have verified; "
                         "repeatable. Anything else is skipped.")
    ap.add_argument("--allow-single-cell-run", action="store_true",
                    help="permit an audited run that wrote only one cell. "
                         "The single-cell dispatch path is the one that "
                         "could carry a non-default label, so this needs "
                         "the walk-forward summary checked by hand.")
    ap.add_argument("--bucket",
                    default=os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT))
    args = ap.parse_args()

    from google.cloud import storage as gcs
    bucket = gcs.Client().bucket(args.bucket)
    payload = json.dumps(
        contract_payload(DEFAULT_LABEL_MODE, MAGNITUDE_THRESHOLDS), indent=2)

    # How many cells each run wrote. The task-parallel path fans out across
    # cells; the single-cell path writes exactly one. That is the signal
    # separating a run that could not have carried a non-default label from
    # one that could.
    span: dict[str, int] = {}
    latest_of: dict[tuple[str, str], str] = {}
    for ticker in TICKERS:
        for tf in TIMEFRAMES:
            base = f"magnitude-models/production/{ticker}/{tf}"
            latest = bucket.blob(f"{base}/LATEST")
            if not latest.exists():
                continue
            run_id = latest.download_as_text().strip()
            latest_of[(ticker, tf)] = run_id
    for run_id in set(latest_of.values()):
        span[run_id] = sum(
            1 for ticker in TICKERS for tf in TIMEFRAMES
            if list(bucket.list_blobs(
                prefix=f"magnitude-models/production/{ticker}/{tf}/"
                       f"{run_id}/", max_results=1)))

    written = skipped = missing = refused = 0
    for ticker in TICKERS:
        for tf in TIMEFRAMES:
            base = f"magnitude-models/production/{ticker}/{tf}"
            run_id = latest_of.get((ticker, tf))
            if run_id is None:
                print(f"{ticker}:{tf} — no LATEST, nothing serving; skipped")
                missing += 1
                continue
            if run_id not in args.audited_run_id:
                print(f"{ticker}:{tf} run={run_id} — REFUSED: not named by "
                      f"--audited-run-id. Its label contract is unverified; "
                      f"check its walk-forward summary before stamping it.")
                refused += 1
                continue
            if span.get(run_id, 0) < 2 and not args.allow_single_cell_run:
                print(f"{ticker}:{tf} run={run_id} — REFUSED: wrote only "
                      f"{span.get(run_id, 0)} cell(s), which is the "
                      f"single-cell dispatch path -- the one that could "
                      f"carry a non-default label. Verify by hand and pass "
                      f"--allow-single-cell-run.")
                refused += 1
                continue
            blob = bucket.blob(f"{base}/{run_id}/{CONTRACT_BLOB}")
            if blob.exists():
                print(f"{ticker}:{tf} run={run_id} — {CONTRACT_BLOB} already "
                      f"present, left alone")
                skipped += 1
                continue
            if args.commit:
                blob.upload_from_string(payload,
                                        content_type="application/json")
                print(f"{ticker}:{tf} run={run_id} (spans {span[run_id]} "
                      f"cells) — wrote {CONTRACT_BLOB}")
            else:
                print(f"{ticker}:{tf} run={run_id} (spans {span[run_id]} "
                      f"cells) — WOULD write {CONTRACT_BLOB}")
            written += 1

    verb = "wrote" if args.commit else "would write"
    print(f"\n{verb} {written}; {skipped} already had one; "
          f"{refused} refused as unverified; {missing} cells not serving")
    if not args.commit and written:
        print("dry run — re-run with --commit to apply")

    # The exit code answers one question: is every SERVING artifact now
    # verifiable? Nothing less, because this gates a deploy -- mag_inference
    # refuses a cell with no CONTRACT.json, and its own majority-failure
    # threshold means a minority of unstamped cells can leave the job exiting
    # 0 while those cells serve nothing. A backfill that refused an artifact
    # and still reported success would be the fabricated success this whole
    # change exists to prevent, in the tool meant to prevent it (Codex P1 on
    # #1074).
    #
    # Read back rather than trusting the writes: in commit mode this is the
    # difference between "upload_from_string returned" and "the blob is
    # there", and it is the same check done by hand before the first backfill.
    unverified = []
    for (ticker, tf), run_id in sorted(latest_of.items()):
        blob = bucket.blob(
            f"magnitude-models/production/{ticker}/{tf}/{run_id}/"
            f"{CONTRACT_BLOB}")
        if not blob.exists():
            unverified.append(f"{ticker}:{tf} (run={run_id})")
    if unverified:
        print(f"\nUNVERIFIED serving artifacts, {len(unverified)}:")
        for cell in unverified:
            print(f"  {cell}")
        print("mag_inference will REFUSE these cells. Do not deploy the "
              "contract check until every one carries a CONTRACT.json — "
              "audit each run and re-run with it named by --audited-run-id.")
        return 1
    print(f"\nall {len(latest_of)} serving artifact(s) carry "
          f"{CONTRACT_BLOB}; safe to deploy the contract check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
