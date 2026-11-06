---
feat_id: FEAT-OPTION-001
req_ids: [REQ-DATA-001, REQ-REL-001, REQ-CAP-001, REQ-CAP-003, REQ-SECRET-001]
issues: [1646]
canvases: []
done_when:
  - "tests/gcp/test_av_options_realtime_producer.py::test_persistence_time_does_not_spend_the_source_window passes: SPY, IWM and QQQ with fast source calls and a 12-second write each all commit, the run exits 0 and logs no source_deadline; the same test fails on the current collector, which refuses QQQ."
  - "tests/gcp/test_av_options_realtime_producer.py::test_failed_write_time_does_not_spend_the_source_window passes: a write that raises after 20 seconds still returns its time to the source window, the sibling ticker commits, and the run exits 1."
  - "The existing collector suites pass unchanged: tests/gcp/test_av_options_realtime_producer.py (including test_body_time_accumulates_across_tickers_preserving_first_ack), tests/gcp/test_av_options_collector_entry.py, tests/gcp/test_av_options_response_schema.py and tests/integration/test_options_collector_durability.py; gcp/fetchers/_av_realtime_transport.py is byte-identical (SHA256 af238d07c2043a0d34319dd533f6e36842e68a9ff536c37d9700e859de117284)."
  - "Own narrow plan/product records, no-new documentation audit, current-head required Codex review and CI pass through normal gates."
status: draft
supersedes: docs/superpowers/specs/2026-10-29-feat-option-001-collector-source-declaration.md
---

# Realtime options source window excludes database writes

## Problem

Since 2026-10-30 09:30 ET every scheduled fetch-av-options-realtime execution has failed: issue #1646 holds 469 failure comments, 77 to 79 per trading day (every five-minute fire, Oct 30 and Nov 2 to Nov 6). The first failing fire is the first one after PR #1565 (the bounded collector) merged on 2026-10-29 21:35 ET.

The collector opens one absolute 15-second source window before the ticker loop. The superseded spec says "SQL between source operations consumes remaining source-window time". Each ticker's chain is written to Cloud SQL inside that window: AV returned 13,164 SPY contracts on 2026-11-06, and one SPY upsert through `gcp.database.upsert_dataframe` took 5.1 to 5.5 seconds against a local socket PostgreSQL with pg8000 (Cloud SQL through the connector is slower, and the first write also starts the engine). After two tickers' downloads and writes the window is spent, so the next ticker is refused at pacing with `source_deadline` and the job exits 1 every time. The deploy sizing comment already expected 10 to 15 seconds for the whole three-ticker run including writes.

The parent design (2026-10-13 source journal, A10) measured the 15 seconds as an ALL-ticker HTTP, body, pacing and retry phase, separately from the SQL allowance. Counting writes against it was a narrowing in the 2026-10-29 spec that the production write time cannot fit.

## Non-goals

- No change to `gcp/fetchers/_av_realtime_transport.py` (hash-pinned), the 15-second length, the 10 MiB body caps, retry classification, attempt counts, pacing, telemetry, calendar admission, acknowledgement checks or the API fetch path.
- No new bound on SQL duration; the existing 600-second task timeout still covers the whole run, as before.
- No schema, scheduler, resource, credential or provider change; no historical snapshot repair or replay.

## Approaches considered

1. Hand the time each write took back to the source window (chosen): the window still bounds every source request, body, pace and retry cumulatively across tickers, and writes stop starving later tickers. Smallest change, collector-only.
2. Raise the window to 60 seconds: edits the pinned transport and still lets a slow write refuse later tickers.
3. One scheduled job per ticker: three jobs, three schedulers and a deploy-script change for the same effect.

## Design

All in `gcp/fetchers/_av_realtime_collector.py`, every other behavior carried forward from the superseded spec unchanged:

- `process_ticker` takes an optional `_persistence_elapsed` list. It reads the transport's own monotonic clock immediately before `upsert_dataframe` and appends the finite, positive elapsed seconds in a `finally`, so a write that raises is counted too. An unreadable clock records nothing (the time then stays charged to the window, the conservative side).
- `main` keeps one source deadline. Before pacing each later ticker it moves the deadline forward by the recorded write time (`_exclude_persistence`), never backwards; a non-finite result is a `SourceDeadline`, as any invalid clock already is.
- Body, transfer, pacing and empty-retry time still accumulate across all tickers in the one 15-second window.

Capacity (CLAUDE.md rule 0): volume and velocity unchanged, three tickers per fire, at most nine AV calls, 78 fires per session. Wall-clock: source phase at most 15 seconds across tickers as before, plus three writes of about 13k rows (measured 5 to 6 s each on local PostgreSQL), well inside the 600-second task timeout. Cost unchanged: same AV calls, same rows.

## Rollout and evidence

After merge, update only this job's image, as the superseded spec required: `gcp/deploy.sh` has no narrow target for it (it is deployed only through the broad `fetchers` group), so build the main image once and run `gcloud run jobs update fetch-av-options-realtime --region us-east1 --image <new digest>`, recording the old and new digests. No other job, flag, secret or scheduler changes. Evidence: the next regular-session scheduled execution succeeds, its log shows SPY, IWM and QQQ acknowledged with no `source_deadline`, and `etf_options_snapshots` holds REALTIME rows for all three tickers at that snapshot_ts. Rollback is the captured previous digest.

## Risks

- A write that hangs is still bounded only by the task timeout, as before this collector; the window no longer refuses later tickers because of it. done_when[0] and [1] cover the hand-back; done_when[2] keeps the source-phase cutoffs.
- A clock read failure around a write leaves the time charged to the window, which can refuse a later ticker as today; it cannot extend the window.
