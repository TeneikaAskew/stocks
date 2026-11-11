---
feat_id: FEAT-SIGNAL-001
req_ids: [REQ-SIGNAL-001, REQ-DATA-003]
issues: []
canvases: []
done_when:
  - "tests/gcp/test_signal_monitor_gate_record.py proves the persisted signal_alerts row carries gate_action, gate_reason, insight_direction, insight_conviction and insight_regime for each direction-gate outcome that fires (pass, downgrade, tag, annotate), with and without an insight row."
  - "The same suite proves no stale decision leaks: a fire for one ticker after another ticker's gate decision records its own decision; with INSIGHT_GATE_MODE=disabled all gate and insight columns are NULL; when the gate raises, the columns are NULL and the fire proceeds unchanged."
  - "The same suite proves shadow mode records the decision it would have applied, with gate_reason prefixed 'shadow:', while the fire's strength and firing are unchanged."
  - "The same suite proves that an insight whose direction, conviction or regime is longer than its column (VARCHAR(8), VARCHAR(8), VARCHAR(20)) is persisted truncated to that width with one warning log line, and the signal_alerts row is still written."
  - "The same suite proves thesis_invalidated is persisted as NULL when the insight carries no invalidation level, never a fabricated FALSE."
  - "Every existing tests/gcp/test_signal_monitor*.py and tests/scripts/test_replay_signal_monitor.py test passes unchanged, showing no fire, score, strength or delivery decision changed."
  - "02-FEATURE-CATALOG FEAT-SIGNAL-001 record and 12-PR-ISSUE-TRACEABILITY carry this PR; docs audit shows no new finding versus main and spec_gate --pr passes."
status: draft
supersedes: null
---

# Record the live direction gate's decision on every signal alert

## Problem

On 2026-11-09 the signal monitor fired 11 PUT alerts on a strong up day; 10 lost. The question was why
alerts against the morning brief were not stopped. The evidence (branch
`replay/feat-signal-001-brief-gate-evidence`, `signal-gate/REPORT.md`, read-only pulls of 3,102 live alerts
from 2026-05-01 to 2026-11-10) shows:

- The brief tag (`brief_alignment`) is a label by design; no gate reads it. The level and RVOL gates run in
  shadow mode.
- The one gate that can stop a fire is the insight direction gate (`lib/strategies/insight_cache.py`,
  `INSIGHT_GATE_MODE` default `active`). On 2026-11-09 the insight said IWM short and QQQ short, so the PUTs
  passed as aligned; the gate suppressed 50 weak SPY PUT candidates and 4 weak IWM CALL candidates (log lines
  only).
- `_persist_signal_alert` never writes the gate's decision. `gate_action`, `gate_reason`,
  `insight_direction`, `insight_conviction`, `insight_regime` and `thesis_invalidated` exist in
  `gcp/schema.sql` (added for this gate's audit) and are NULL on every row since they were added. The gate
  that decides what fires cannot be measured from the table, which breaks REQ-SIGNAL-001 (persist reason
  codes before delivery).
- `insight_invalidated` is never set anywhere, and none of the 396 live insight rows since May carries an
  `invalidation_level`, so the gate's invalidation tripwire is inert. Persisting FALSE would claim a check
  that never ran.

No new direction rule validated: alerts opposed to the brief won in 2026-08-28 to 2026-10-15
(+0.083% mean, CI above zero) and lost in 2026-10-16 to 2026-11-10 (-0.363%); fading a brief leg already
past T1, with or without a neutral brief, and the combination of both, failed the same two-window test.

## Non-goals

- No new gate, threshold, matrix change or mode change. Fire, score, strength, size and Discord decisions
  stay byte-for-byte the same.
- No change to `INSIGHT_GATE_MODE`, the level gate or the RVOL gate defaults.
- No fix to the inert invalidation tripwire (it changes what fires and needs its own measured spec).
- No recording of suppressed candidates (they never reach `signal_alerts`; a separate table needs a
  migration and its own spec).
- No schema change, migration or backfill: the columns already exist and old rows stay NULL.
- No change to the replay script's output format.

## Approaches considered

1. Add a brief-opposed or fade-past-T1 gate. Rejected: neither held in both windows; shipping it would fit
   two weeks of a rally.
2. Record the existing gate's decision and insight context in the columns built for it. Chosen: no
   behavior change, closes the REQ-SIGNAL-001 gap, and makes the live gate measurable per fire.
3. Also persist suppressed candidates. Deferred: needs a new table and migration (production write).

## Design

In `gcp/signal_monitor.py`:

- At the start of each fire's gate block, reset the per-fire stash: `_latest_insight_ctx = None`,
  `_latest_gate_action = None`, `_latest_gate_reason = None`. Today the stash is only assigned when the gate
  succeeds and is shared across tickers, so a later fire could inherit an earlier decision.
- When the gate runs (`active` or `shadow`), stash the decision and the context as today. In `shadow`, store
  `gate_reason` as `shadow:<reason>` so a reader can tell an applied decision from a would-have decision.
- If the gate raises, leave the stash NULL (the fire proceeds, as today).
- In `_persist_signal_alert`, add to the row:
  - `gate_action`, `gate_reason` from the stash (NULL when the gate is disabled or raised);
  - `insight_direction`, `insight_conviction`, `insight_regime` from `_latest_insight_ctx` (NULL when there
    is no insight row);
  - `thesis_invalidated`: the boolean when the context has an `invalidation_level`, otherwise NULL.
- Values fit the declared widths (`gate_action` VARCHAR(16), `insight_*` VARCHAR(8)/(20), `gate_reason`
  TEXT); a direction, conviction or regime longer than its column is truncated to the width with a warning
  log, never dropped silently.

Tests go in a new `tests/gcp/test_signal_monitor_gate_record.py`, driving `evaluate_ticker`'s fire path
with a stubbed insight fetcher and capturing the row handed to `upsert_dataframe`, following the pattern
in `tests/gcp/test_signal_monitor_persist.py`.

Capacity (CLAUDE.md rule 0): Volume, about 20 to 40 live fires a day across SPY, QQQ, IWM (3,102 rows in
133 sessions), each gaining six small fields (under 100 bytes). Velocity, zero new queries or round trips:
the insight row is already fetched and cached for the gate. Wall-clock, unchanged (in-memory dict keys).
Cost, $0 a month.

## Close-out (after merge, not pre-merge boxes)

After the merge deploys and signal-monitor runs a session on the new image:
`SELECT alert_date, count(*), count(gate_action), count(insight_direction) FROM signal_alerts
WHERE alert_date = <first session> AND run_kind = 'live' GROUP BY 1` shows `count(gate_action)` equal to
`count(*)` while `INSIGHT_GATE_MODE` is active. The signal-monitor image redeploy is a production step
that waits for the owner.

## Risks

- A typo in a row key would fail the upsert and drop the alert: the persist tests assert the exact row keys
  and the existing persist suite keeps passing.
- A leaked decision across tickers would mislabel rows: covered by the stale-stash test.
- Shadow and active decisions mixed in analysis: the `shadow:` prefix separates them.
