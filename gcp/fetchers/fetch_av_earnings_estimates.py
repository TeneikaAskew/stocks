"""Bounded AV EARNINGS_ESTIMATES capture and permanent consensus vintages."""
from __future__ import annotations

import argparse
import os
import time
import uuid
from datetime import datetime, timezone

from gcp.fetchers import _av_ingestion as av


def parse_estimates(capture):
    data = capture.json()
    ticker = capture.parameters["symbol"].upper()
    if data.get("symbol", "").upper() != ticker or not isinstance(data.get("estimates"), list):
        raise av.SourceError("estimate_schema")
    if len(data["estimates"]) > 100:
        raise av.SourceError("estimate_row_limit")
    records, identities = [], set()
    for payload in data["estimates"]:
        if not isinstance(payload, dict) or payload.get("horizon") not in {"fiscal quarter", "fiscal year"}:
            raise av.SourceError("estimate_horizon")
        try:
            fiscal = datetime.strptime(payload["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError, TypeError):
            raise av.SourceError("estimate_date") from None
        key = (fiscal.isoformat(), payload["horizon"])
        if key in identities:
            raise av.SourceError("duplicate_estimate_identity")
        identities.add(key)
        records.append({"observation_id": str(uuid.uuid5(uuid.UUID(capture.observation_id), av.canonical(key))),
                        "fetch_id": capture.observation_id, "ticker": ticker,
                        "fiscal_date_ending": fiscal.isoformat(), "horizon": payload["horizon"],
                        "source_retrieved_at": capture.retrieved_at.isoformat(),
                        "raw_sha256": capture.body_sha256, "payload": payload})
    return records


def persist_estimate_group(group, *, executor=None):
    executor = executor or av.isolated_sql
    if len(group) > 10:
        raise av.SourceError("estimate_group_limit")
    captures, rows, receipts = [], [], []
    for capture, uri, records in group:
        captures.append(av.capture_record(capture, uri, len(records)))
        rows.extend({**r, "raw_uri": uri} for r in records)
    executor(av.capture_sql(captures), {"captures": av.canonical(captures)}, timeout_s=2)
    # Source capture ACK precedes the actual knowledge clock.
    known = datetime.now(timezone.utc)
    rows = [{**r, "known_at": known.isoformat()} for r in rows]
    executor("""INSERT INTO av_earnings_estimates_observations
      SELECT * FROM jsonb_populate_recordset(NULL::av_earnings_estimates_observations,CAST(:rows AS jsonb))
      ON CONFLICT(fetch_id,ticker,fiscal_date_ending,horizon) DO NOTHING""", {"rows": av.canonical(rows)}, timeout_s=2)
    for capture, uri, records in group:
        receipts.append({"ticker": capture.parameters["symbol"], "fetch_id": capture.observation_id,
                         "status": "validated" if records else "validated_empty",
                         "source_retrieved_at": capture.retrieved_at.isoformat(), "known_at": known.isoformat(),
                         "raw_sha256": capture.body_sha256, "raw_uri": uri, "observation_count": len(records)})
    return receipts


def resolve_universe():
    from gcp.database import query_to_dataframe_strict
    df = query_to_dataframe_strict("""SELECT DISTINCT ticker FROM (
      SELECT ticker FROM earnings_history UNION SELECT ticker FROM earnings_calendar
      WHERE earnings_date BETWEEN (NOW() AT TIME ZONE 'America/New_York')::date-30
        AND (NOW() AT TIME ZONE 'America/New_York')::date+30
    ) configured ORDER BY ticker""", timeout_s=5)
    return df["ticker"].str.upper().tolist() if not df.empty else []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers")
    parser.add_argument("--max-tickers", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    run = av.Run("fetch-av-earnings-estimates", "daily")
    started = time.monotonic()
    receipts, group, manifest = [], [], None
    outcomes = []
    try:
        if not 1 <= args.max_tickers <= 100:
            raise av.SourceError("estimate_admission_limit")
        key = os.environ.get("AV_API_KEY") or os.environ.get("ALPHA_VANTAGE_API_KEY")
        if not key:
            raise av.SourceError("credential_missing")
        universe = sorted(set(args.tickers.upper().split(","))) if args.tickers else resolve_universe()
        run.expected = len(universe)
        selected = av.claim_work("EARNINGS_ESTIMATES", universe, "daily", run.execution_name,
                                 limit=args.max_tickers, dry_run=args.dry_run)
        run.pending = len(universe) - len(selected)
        for ticker in selected:
            remaining = 450 - (time.monotonic() - started)
            if remaining < 14:
                run.pending += len(selected) - run.attempted
                break
            run.attempted += 1; run.request_attempts += 1
            try:
                capture = av.fetch_capture("EARNINGS_ESTIMATES", {"symbol": ticker}, key,
                                           timeout_s=min(30,remaining-12))
                uri = av.archive_capture(capture, dry_run=args.dry_run)
                rows = parse_estimates(capture)
                if args.dry_run:
                    run.processed += 1
                else:
                    group.append((capture, uri, rows))
                if len(group) == 10:
                    durable = persist_estimate_group(group)
                    receipts.extend(durable); run.processed += len(group)
                    run.rows_written += sum(len(r) for _,_,r in group)
                    outcomes.extend({"ticker": r["ticker"], "success": True,
                                     "observed_at": r["source_retrieved_at"]} for r in durable)
                    group.clear()
            except av.SourceError as exc:
                run.failed += 1
                outcomes.append({"ticker": ticker, "success": False, "observed_at": None})
                run.groups.append({"ticker": ticker, "error_class": str(exc), "coverage_complete": False})
        if group:
            durable = persist_estimate_group(group)
            receipts.extend(durable); run.processed += len(group)
            run.rows_written += sum(len(r) for _,_,r in group)
            outcomes.extend({"ticker": r["ticker"], "success": True,
                             "observed_at": r["source_retrieved_at"]} for r in durable)
        if not args.dry_run:
            av.finish_work("EARNINGS_ESTIMATES", "daily", outcomes)
            manifest = {"schema_version": "av_catalyst_run/v1", "pipeline_scope": "estimates_daily",
              "scope_hash": av.digest(universe), "universe_count": len(universe), "configured_universe": universe,
              "selected_scope_hash": av.digest(selected), "selected_count": len(selected), "pending_count": run.pending,
              "source_window_start": run.started_at.isoformat(), "source_window_end": datetime.now(timezone.utc).isoformat(),
              "complete_through": datetime.now(timezone.utc).isoformat() if not run.failed and not run.pending else None,
              "coverage_complete": not run.failed and not run.pending, "captured_receipts": receipts,
              "source_revision_ids": [r["fetch_id"] for r in receipts], "source_digest": av.digest(receipts),
              "predecessor_execution_name": None, **av.code_identity()}
            manifest = av.publish_manifest(run, manifest)
    except Exception as exc:
        run.failed += 1
        run.groups.append({"error_class": str(exc) if isinstance(exc,av.SourceError) else type(exc).__name__, "coverage_complete": False})
    return run.terminal(dry_run=args.dry_run, extra=manifest)


if __name__ == "__main__":
    raise SystemExit(main())
