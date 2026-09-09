#!/usr/bin/env python3
"""Write CONTRACT.json for production model artifacts published before it existed.

mag_inference refuses to score a model whose artifact does not state its own
label contract (see mag_config.CONTRACT_BLOB). Artifacts promoted before that
blob existed carry model.joblib + feature_cols.txt + VERSION and nothing that
says what their buckets MEAN, so they need one written once.

The value is not a guess. Every artifact in magnitude-models/production/ was
promoted before #1055, and before #1055 two things were true:

  * `--label-mode` was forwarded on the single-cell dispatch path only. The
    production runs went through the Cloud Run task-parallel path, which
    called walk_forward() without it and therefore always trained the `body`
    default. That was finding 1 of #1055.
  * MAGNITUDE_THRESHOLDS was a module constant with no override. MAG_THRESHOLDS
    did not exist until the same PR.

So a legacy artifact is necessarily body at (0.5, 1.0, 1.5) -- the code could
not have produced anything else on that path. This script states that fact in
the artifact rather than leaving mag_inference to assume it, which is the
distinction between a recorded contract and a silent fallback.

Refuses to overwrite an existing CONTRACT.json: one that is already there was
written by the walk-forward that produced the model and is authoritative.

    python -m scripts.backfill_model_contracts --dry-run
    python -m scripts.backfill_model_contracts --commit
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
    ap.add_argument("--bucket",
                    default=os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT))
    args = ap.parse_args()

    from google.cloud import storage as gcs
    bucket = gcs.Client().bucket(args.bucket)
    payload = json.dumps(
        contract_payload(DEFAULT_LABEL_MODE, MAGNITUDE_THRESHOLDS), indent=2)

    written = skipped = missing = 0
    for ticker in TICKERS:
        for tf in TIMEFRAMES:
            base = f"magnitude-models/production/{ticker}/{tf}"
            latest = bucket.blob(f"{base}/LATEST")
            if not latest.exists():
                print(f"{ticker}:{tf} — no LATEST, nothing serving; skipped")
                missing += 1
                continue
            run_id = latest.download_as_text().strip()
            blob = bucket.blob(f"{base}/{run_id}/{CONTRACT_BLOB}")
            if blob.exists():
                print(f"{ticker}:{tf} run={run_id} — {CONTRACT_BLOB} already "
                      f"present, left alone")
                skipped += 1
                continue
            if args.commit:
                blob.upload_from_string(payload,
                                        content_type="application/json")
                print(f"{ticker}:{tf} run={run_id} — wrote {CONTRACT_BLOB}")
            else:
                print(f"{ticker}:{tf} run={run_id} — WOULD write "
                      f"{CONTRACT_BLOB}")
            written += 1

    verb = "wrote" if args.commit else "would write"
    print(f"\n{verb} {written}; {skipped} already had one; "
          f"{missing} cells not serving")
    if not args.commit and written:
        print("dry run — re-run with --commit to apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
