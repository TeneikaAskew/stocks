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
    TICKERS, TIMEFRAMES, CONTRACT_BLOB, ContractRejection,
    GCS_BUCKET_DEFAULT,
)
from gcp.research.magnitude_engine import mag_inference  # noqa: E402


# The contract in force when the legacy artifacts were trained, written out
# as literals ON PURPOSE rather than derived from the live constants (Codex
# P2 on #1074).
#
# Deriving it would mean that after any future change to MAGNITUDE_THRESHOLDS
# or LABEL_CLASSES this script stamps an OLD model with the NEW constants,
# and mag_inference would then accept an artifact whose probability columns
# mean something else -- which is the precise evolution CONTRACT.json exists
# to catch. A backfill that re-derives its own answer cannot detect drift; it
# moves with it.
#
# So this states history, and the verification pass below checks history
# against what inference will actually accept. If the two ever disagree, the
# script writes the truth and then FAILS, telling the operator these legacy
# artifacts cannot be served under the new contract. That is the correct
# outcome, and it is only reachable because these values do not move.
_AUDITED_LEGACY_CONTRACT = {
    "label_mode": "body",
    "thresholds": [0.5, 1.0, 1.5],
    "classes": ["TIGHT", "NORMAL", "EXPANDED", "EXPLOSIVE"],
}


class _PointerMoved(RuntimeError):
    """LATEST changed underneath a read that had pinned itself to one version.

    Raised rather than returned so it cannot be mistaken for "no pointer".
    """


def _read_latest(bucket, base) -> tuple[str, int] | None:
    """A cell's LATEST as (run_id, generation), or None if it has none.

    The read is PINNED to the generation `reload()` saw, so the pair always
    describes ONE version of the pointer instead of a run id from one version
    and a generation from another. Carrying the generation is what makes an
    A -> B -> A flip detectable at all: comparing run ids alone would call
    that sequence unchanged.
    """
    from google.api_core import exceptions as gapi   # noqa: PLC0415
    blob = bucket.blob(f"{base}/LATEST")
    try:
        blob.reload()
    except gapi.NotFound:
        return None
    try:
        text = blob.download_as_text(if_generation_match=blob.generation)
    except gapi.PreconditionFailed as e:
        raise _PointerMoved(f"{base}/LATEST moved mid-read") from e
    except gapi.NotFound as e:
        raise _PointerMoved(f"{base}/LATEST deleted mid-read") from e
    return text.strip(), blob.generation


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
    # The verdict below delegates to mag_inference._load_model_and_version,
    # which picks its own bucket from GCS_BUCKET. Without this, a run against
    # a non-default --bucket would scan and write one bucket while VERIFYING
    # another -- reporting the requested bucket safe on the strength of
    # unrelated artifacts, or failing despite a successful backfill (Codex P2
    # on #1074). Delegating to the reader is what removed the drift between
    # two implementations; this is what stops it reintroducing drift between
    # two BUCKETS.
    os.environ["GCS_BUCKET"] = args.bucket
    bucket = gcs.Client().bucket(args.bucket)
    payload = json.dumps(_AUDITED_LEGACY_CONTRACT, indent=2)

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
    # Rescan EVERY cell, not just the ones that were serving at scan time. A
    # cell idle during the scan can gain a LATEST before the verdict -- the
    # old writer is still promoting during the pre-deploy backfill -- and
    # iterating over the scan's keys would omit it entirely, so a freshly
    # promoted artifact with no CONTRACT.json would sit behind a "safe to
    # deploy" (Codex P2 on #1074). The previous round taught the loop that a
    # pointer can MOVE or VANISH; this one is the third case, that one can
    # APPEAR. The verdict covers the whole fleet or it is not a verdict.
    unverified = []
    verified = 0
    for ticker, tf in [(t, f) for t in TICKERS for f in TIMEFRAMES]:
        scanned_run = latest_of.get((ticker, tf))
        base = f"magnitude-models/production/{ticker}/{tf}"
        # Re-read LATEST rather than trusting the run id cached at scan time.
        # A promotion running concurrently -- entirely possible during the
        # pre-deploy backfill, since it still uses the old writer -- flips the
        # pointer between the scan and here, and validating the stale run
        # would print "safe to deploy" about an artifact that is no longer the
        # one serving (Codex P2 on #1074). The verdict has to describe the
        # world at the moment it is issued.
        try:
            current = _read_latest(bucket, base)
        except _PointerMoved:
            unverified.append(
                f"{ticker}:{tf} — LATEST changed while it was being read; "
                f"re-run once promotions have settled")
            continue
        if current is None:
            if scanned_run is None:
                continue          # idle at the scan and still idle; nothing serving
            unverified.append(
                f"{ticker}:{tf} — LATEST vanished during the run "
                f"(was {scanned_run}); re-run once promotions have settled")
            continue
        run_id, generation = current
        if scanned_run is None:
            unverified.append(
                f"{ticker}:{tf} — LATEST appeared during the run "
                f"(now {run_id}); it was idle at scan time so this run never "
                f"audited it; re-run once promotions have settled")
            continue
        if run_id != scanned_run:
            unverified.append(
                f"{ticker}:{tf} — LATEST moved during the run "
                f"({scanned_run} -> {run_id}); re-run once promotions have "
                f"settled")
            continue
        where = f"{ticker}:{tf} (run={run_id})"
        # Ask the READER rather than re-implementing its checks. The previous
        # version parsed the contract itself and claimed "the reader accepts",
        # which stopped being true the moment the reader grew a check this
        # loop did not have -- it gained an estimator class-order check one
        # commit ago and this verdict kept saying "safe to deploy" for an
        # artifact the reader would reject (Codex P2 on #1074).
        #
        # Adding the missing check would not fix the class, because the next
        # check added to the reader re-opens it. Calling the reader is the
        # only version that cannot drift: if _load_model_and_version returns,
        # the reader accepts this artifact, which is exactly the claim the
        # exit code makes. It costs a model download per serving cell, which
        # for a one-time pre-deploy gate over at most nine cells is the right
        # trade.
        try:
            mag_inference._load_model_and_version(ticker, tf)
        except ContractRejection as e:
            unverified.append(f"{where} — {type(e).__name__}: {e}")
            continue
        except Exception as e:                      # noqa: BLE001
            unverified.append(
                f"{where} — could not be loaded to verify "
                f"({type(e).__name__}: {e})")
            continue
        # LATEST can flip AGAIN between the re-read above and the moment the
        # reader resolves its OWN pointer. The reader would then have verified
        # run A while run B is the one now serving, and B is exactly the kind
        # of artifact this gate exists to catch: freshly promoted by the old
        # writer, carrying no CONTRACT.json (Codex P2 on #1074). Re-read after
        # the load and compare the exact VERSION, not just the run id.
        #
        # This narrows the window to the load itself. It does not close it,
        # and no number of checks can -- a flip is always possible after the
        # last one, including after this line. The durable mitigation is not
        # running this backfill concurrently with promotions, which is what
        # the message tells the operator to do.
        try:
            after = _read_latest(bucket, base)
            moved = after is None or after[1] != generation
        except _PointerMoved:
            moved = True
        if moved:
            unverified.append(
                f"{where} — LATEST changed while the artifact was being "
                f"verified, so the reader may have resolved a different run; "
                f"re-run with promotions paused")
            continue
        verified += 1
    if unverified:
        print(f"\nUNVERIFIED serving artifacts, {len(unverified)}:")
        for cell in unverified:
            print(f"  {cell}")
        print("mag_inference will REFUSE these cells. Do not deploy the "
              "contract check until every one carries a CONTRACT.json — "
              "audit each run and re-run with it named by --audited-run-id.")
        return 1
    # Report what was actually verified in THIS pass, not what the scan saw.
    print(f"\nall {verified} serving artifact(s) carry a {CONTRACT_BLOB} the "
          f"reader accepts; safe to deploy the contract check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
