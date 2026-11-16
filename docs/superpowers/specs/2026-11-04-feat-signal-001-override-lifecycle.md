---
feat_id: FEAT-SIGNAL-001
req_ids: [REQ-DATA-001, REQ-REL-001, REQ-RISK-001, REQ-REPLAY-001, REQ-GOV-002]
issues: [862]
canvases:
  - https://claude.ai/artifact/Fg4VQHB6dFGWF9iXSJUDtg
done_when:
  - "Resolver tests exercise actual SQL-to-row resolution at ages 179, 180 and 181 days, without mocking away freshness, and prove numerical defaults and explicit restrictions follow the approved lifecycle."
  - "One-process midnight tests prove numerical freshness changes at day 181 while approved explicit restrictions remain effective, with one cached successful SQL read and no cached exceptions."
  - "Mean-reversion and standalone-momentum tests allow otherwise eligible QQQ PUT signals under the confirmed policy at ages 179, 180 and 181; approved restrictions on other fixture tickers, condition score subtraction, and malformed/read-failure suppression remain effective."
  - "Schema and supported calibration-writer regression tests prevent reintroduction or copying of the retired QQQ PUT restriction and reject contradictory configuration explicitly; protection scope and deployment verification are documented."
  - "Logs distinguish numerical expiry from restriction retention and contain ticker, original calibration date and age, with bounded repetition proven by tests."
  - "Existing valid-row, missing-row, NULL, malformed-payload, unavailable-database and numeric-fallback guarantees remain tested; QQQ-PUT fixtures are updated only for the explicit retired-policy conflict, with equivalent permitted-restriction coverage on other fixture tickers."
  - "Normal product records, documentation audit, delivery gate and current-head review pass; release and monitor resumption remain separately authorized."
status: approved
supersedes: null
---

# Separate numerical freshness from explicit signal restrictions

## Status and ownership

Owner-approved written specification; both QQQ eligibility and restriction-retention
behavior are confirmed below. Numerical-default validation remains a release prerequisite.
Isolated branch `docs/spec-feat-signal-001-override-lifecycle`, refreshed to main
`3ab668a9` on November 4 before the spec-only commit.
No source/test/gate or production changes have been made. The parent authorized progressing
the normal specification/implementation workflow subject to its gates; no production
write, numerical change, deployment or monitor restart is authorized.

## Confirmed owner decision — November 4, 2026

The parent supplied this direct conversation evidence:

> Assistant: Should QQQ put signals remain allowed, with protections against that old restriction being reintroduced? Separately, the fallback targets need validation before restarting the monitor. I’m preparing that work without changing production.
>
> User: Yes

QQQ PUT signals must remain eligible under the ordinary scoring and safety checks; the
retired static QQQ PUT prohibition must not be revived by numeric expiry, calibration
copy-forward, schema seed or a supported deployment path. Allowed does not mean forced:
failed/malformed configuration, condition scoring and independent legitimate gates can
still suppress a signal. This decision supersedes preservation of the current QQQ PUT
database value as an intended policy. It does not approve changing that row now, removing
other restrictions, selecting numerical defaults, deploying, or resuming the monitor.
The historical record remains unchanged. The user's Yes approves the stated policy,
not the unreviewed implementation details or this entire specification.

### Confirmed restriction lifecycle and read-failure decision

The parent supplied this additional direct conversation evidence:

> Assistant: There are two other existing controls on IWM and QQQ that exclude certain overbought indicators from the score. They do not block all put signals. I recommend keeping those controls when old numerical settings expire, while keeping QQQ puts eligible as you confirmed. If the controls cannot be read reliably, the affected new signals would be held rather than generated with unknown rules.
>
> May I use that behavior in the fix? The numerical fallback still needs separate validation before the monitor can restart.
>
> User: Yes if you believe thats whats best

This selects retention of the IWM/QQQ condition exclusions independently of numerical
age and refusal of affected new signals when their controls cannot be read reliably.
QQQ PUT eligibility remains confirmed. Neither behavior decision is pending or needs
reconfirmation. Numerical values, production rows, deployment and monitor restart remain
outside this approval. That behavior-only transcript did not approve the whole artifact. The later written-spec
approval recorded below now covers the technical contract and seven acceptance items.

### Proposed protection and release contract for review

Add a shared validation boundary for the retired QQQ PUT restriction, used by the
supported writer and reader. A contradictory QQQ row must be reported as a policy
conflict rather than silently accepted, silently filtered, or copied into a new snapshot.
Writer refusal must occur before any override-table write in apply_winner, including
same-day conflict updates; this does not make the enclosing research sweep a dry run.
Reader conflicts remain fail-closed while
the monitor is held; they are not a new permanent QQQ ban. A separately authorized,
audited correction of the existing production row and successful policy/config validation
must precede any resume, which also remains gated on numerical validation.

Schema tests must prove no seed restores QQQ PUT; writer tests must prove a conflicting
source/destination row is not propagated and valid NULL/empty direction rows remain
unchanged. On valid policy input, actual MR and standalone momentum paths must admit an
otherwise eligible QQQ PUT. No writer may silently delete an unrelated restriction.
The current process cache requires an explicit refresh/new process after authorized
correction; do not claim live recognition within a warm process.

Old images or arbitrary manual SQL can bypass new source validation. Before a separately
authorized release, check migration-job digest and all supported schema/writer launch paths;
do not claim a source test prevents an operator from executing an old binary. A database
constraint could provide stronger enforcement but is a separate schema/migration choice,
not part of this authorization. No old schema or monitor image may be treated as a safe
rollback while it can reintroduce the restriction; keep the hold in place on rollback.

Catalog owner: `FEAT-SIGNAL-001 | Signals / execution | Signal discovery, alerting, exits`;
the row names `signal_alerts`, `historical_signals`, `exit_config_overrides`.
The catalog status is Production but needs remediation.

Issue #862 is open with no assignee. Its six comments include a historical claim of
commit `59f3a43` adding a 150-day warning, but that object is unavailable in this clone
and fetched main still has only the generic stale warning. Do not claim it landed.
The September correction explicitly confirms stale rows do NOT fail closed.
Searches for open PRs naming exit_config_overrides found none. Related #1022 provides
existing read/parse failure behavior; #1097 records the corrected expiry interpretation;
#1136 and #1279 concern duplicate/offline/overlay consumers, not this lifecycle repair.
Search results are candidate discovery, not a complete timeline/changed-file inventory;
complete REQ-GOV-002 inventory before scheduling implementation. Do not duplicate those streams.
No approved main spec mentions disabled_directions or disabled_conditions.

## Problem and evidence

Production SELECT-only query `db-query-5xv5j` at 2026-11-04 21:44:08.509400 UTC found
May 8 calibration rows for SPY/IWM/QQQ, age 180. QQQ disables PUT; IWM/QQQ disable
stoch_rsi_overbought and rsi_overbought_zone. The strict age >180 comparison expires them
November 5. The deployed image is sha256:a8af7bc74f281c7d7de4c384e942b58690931cca380467119ec2447fe891c9a7.
The approved temporary hold was independently verified PAUSED at 21:45:09.748325 UTC.

`lib/strategies/exit_config_overrides.py::_latest_overrides` caches the complete
freshness-filtered row per ticker/process. Expiry returns None. Numerical getters
use defaults, get_disabled_directions returns an empty set, and lib/signals.py loses
disabled_conditions. Successful cached rows also retain yesterday's freshness decision
across midnight. Failed reads raise OverridesUnavailable and are not cached.

## Written-specification approval and remaining delivery gate

The parent supplied the owner's approval of the attached complete written specification:

> Assistant: The written Stocks monitor fix is ready for review. It includes the signal behavior you approved, checks that old calibration writes cannot restore the retired QQQ restriction, and tests expiry, failures and both signal paths. The repository requires approval of the written specification before implementation.
>
> Please review and approve this draft if you’re comfortable with it. The monitor stays paused, and its numerical fallback still needs validation before restart. [Attached: Stocks-862-Override-Lifecycle-DRAFT.md]
>
> User: You have approval to handle and do all of this. Check the clause code status for verification and validation before pursuing anything to ensure you are not duplicating

This approves the written contract, not just the previously selected behavior. No further
owner approval of this unchanged contract is required. Publication must still pass normal
spec-only PR review and CI, and the approved spec must land on main before implementation.
No production data change, numerical change, deployment or monitor resumption is authorized.

Before editing, checked current issue #862, all six comments, the complete issue timeline,
open PR searches for #862 and exit_config_overrides, and local worktrees. #862 remains open
and unassigned; Claude Code's latest published correction distinguishes stale-row fallback
from failed-read suppression. No active matching implementation PR was found. The #1700
search hit is separate gate work and is not touched. There is no available live Claude
Code session-status tool; published repository evidence cannot prove absence of unpublished
remote work. Current main includes #1546, which does not modify this fix's resolver/writer.

## Non-goals

No production SQL, deployment, scheduler change, numerical recalibration, new default
values, backdating, automatic restriction retirement or new capture service is authorized.
The replay discussion is a feasibility appendix, not implementation scope. No claim of
complete financial validation, exact historical parity or safe monitor resumption is made.

### Additional evidence: historical policy conflicts with the production row

Commit `3ec4350a77ae6152bfb866da1b1772e659e6a6dd` (PR #373, May 10
01:49:34 UTC) says the QQQ PUT seed was removed **per user direction** because
a static side restriction was too broad and its motivating win rate preceded #329.
`gcp/schema.sql:3370-3378` retains that explanation. The incident document's
verification expects all disabled_directions to be NULL, yet November 4 production
still has QQQ [PUT]. This is evidence of historical intent and current divergence,
not current authorization to clear production. A preservation fix must not describe
that QQQ policy as revalidated or permanently approved. The confirmed decision above
now resolves the intended QQQ policy: PUT is allowed, subject to normal gates.

The latest owner decision selects independent retention. Earlier repository requirements
did not establish a lifetime; the following alternatives record the decision history.

1. **Selected lifecycle for still-approved restrictions: retain them from the latest row
   regardless of numerical age.** Numerical knobs still expire after 180 days.
   A subsequent latest row's explicit NULL/empty values retain their existing clearing
   semantics; do not search backward or merge restrictions across historical rows.
   An operational review must confirm that a newer calibration writer cannot accidentally
   clear restrictions through omitted/NULL fields before approving this release.
2. **Alternative: refuse affected signal evaluation once calibration expires.** This
   avoids firing under stale/changed policy but suspends additional signaling. It is a
   different policy requiring approval, not an automatic implementation fallback.
3. **Separate durable restriction records with explicit revisions/retirement.** Stronger
   lifecycle control, but requires schema/writer changes and migration approval; beyond
   the minimal read-side fix.

The confirmed retention decision does not preserve the retired QQQ PUT prohibition.
A pre-expiry warning threshold is excluded from this fix; the historical 150-day proposal
is not adopted and does not require another owner decision for this scope.
No approval of new trading parameters, automatic recalibration or resume is requested here.

## Risks and acceptance boundaries

- A generic preserve-stale-row change would preserve the retired QQQ ban: the explicit
  conflict and valid-policy QQQ eligibility tests must cover this separately.
- Checking only the writer's source misses an already-conflicting same-day destination:
  real ephemeral-SQL tests must prove both are checked atomically, including no-source
  and zero-row outcomes. Do not claim arbitrary external writers are prevented.
- Numeric getters currently permit read-error fallback. A policy conflict must remain
  distinguishable from OverridesUnavailable; the approved plan must not catch it and
  silently report a healthy configuration. Signal admission must reject the conflict
  through the shared restriction reader even if a standalone numeric accessor is lenient.
- Cache retention can hide a subsequent external write. The fixed contract here remains
  a per-process snapshot, with explicit refresh/new-process verification before release;
  real-time policy refresh would be additional design scope.
- Source protections alone cannot prevent an old binary restoring a retired seed. A
  verified release/digest gate and separately authorized correction are necessary before
  resume. No source-only pass completes that operational obligation.

## Numerical-default assessment and writer trace

The present defaults are defined by ExitConfig in lib/config.py:304-340. Latest
production values below come from the November 4 read, not from a fresh calibration.
Targets are underlying-price fractions expressed here as percentages, not option returns.

| Ticker | CALL target: row -> default | PUT target: row -> default | CALL minutes | PUT minutes |
|---|---|---|---|---|
| SPY | 0.184% -> 0.300% | 0.202% -> 0.380% | 25 -> 30 | 25 -> 35 |
| IWM | 0.281% -> 0.300% | 0.249% -> 0.380% | 20 -> 30 | 25 -> 35 |
| QQQ | 0.301% -> 0.300% | 0.238% -> 0.380% | 20 -> 30 | 25 -> 35 |

These are material changes, especially SPY's target and every PUT target/time window.
The live monitor consumes targets and time limits at fire_alert; existing positions
retain their stored target/time limits. Its normal _check_exits path uses target,
elapsed time and RSI, not get_call_stop/get_put_stop. The default stop values 0.15%
CALL and 0.20% PUT are legacy backtest controls. Do not wire them into live to claim
parity. lib/backtest.py:_check_exit still applies those stops: its performance is not
direct evidence of live default-policy suitability. Source comments explicitly require
execution-aware sequential replay and out-of-sample validation before reconsidering stops.
Issue #815 remains open; #940 restart risk-state restoration remains open. #818 is
closed, but its count-cap repair does not independently establish exact fire/position parity.

The May 8 schema seed records SPY/IWM calibration from an MR-only universe in which
momentum did not fire. The current monitor includes standalone momentum. Neither that
old sample nor the fact that defaults exist demonstrates their suitability today.
The model registry labels MODEL-EXIT-001 Broken / RESTRUCTURE / UNVERIFIED. No new
performance result or profitability recommendation is asserted here.

Other numeric expiry effects: consecutive_periods already NULL in the three production
rows, so it already resolves to SignalConfig 3. Blue-sky ATR offset defaults to 0.20;
the May seed gives SPY/IWM 0.15 and QQQ 0.20, so the planner has another potential
numeric change; verify actual production offsets before any activation decision.

Writer trace (repository search, not a claim to inventory every external SQL client):
- scripts/run_param_sweep.py:113-163 apply_winner copies disabled_conditions and
  disabled_directions from the latest row into a new date's row via INSERT SELECT.
  On a same-date conflict it updates only swept numeric knobs and notes, preserving
  restrictions in the existing destination row. It does not automatically clear them.
- gcp/schema.sql seeds the historical May 8 numeric row with ON CONFLICT DO NOTHING.
  Its condition UPDATE sets the two IWM/QQQ names only when that historical field is
  NULL. Reapplying schema can therefore reintroduce those names after a NULL clear
  on the May row; an empty JSON array is not NULL and is not reseeded.
- Removing the QQQ direction seed in #373 did not UPDATE existing QQQ rows to NULL.
  This permits an old row to survive; historical #376 additionally reports an old image
  re-seeding it after a manual clear. Neither proves the complete subsequent write history.
- A latest row with restriction NULL/[] reads unrestricted. A newer partial insert,
  deleting the latest row, or arbitrary manual SQL can change the selected policy.
  There is no independent restriction revision or removal authorization in the reader.
  Current process cache observes those writes only after explicit clear or restart.

The existing integration test test_apply_winner_carries_forward_non_swept_knobs asserts
stop values only; it does not seed/assert either restriction field. Extend that test
on ephemeral Postgres after approval to cover new-day and same-day preservation;
never run its destructive TST cleanup fixture against production.

## Source design for the selected lifecycle

Retain _latest_overrides as the successful raw-row process cache, including original
calibration_date; remove ONLY its freshness rejection. Keep SQL query, latest-row
ordering, missing-row/unconfigured behavior and exception propagation unchanged.
Move the numerical freshness decision into _latest_overrides_or_default, evaluated
on every lookup against the existing date.today clock. Thus no extra SQL is required
to expire numerical values after midnight. Every numerical getter and audit-tier getter
continues to use that filtered path, including consecutive_periods and blue-sky offset.
Keep direction parsing and lib/signals.py condition parsing on the raw-row path.
Audit every direct _latest_overrides caller before implementation; no mutable cached
row is edited to blank numerical fields. Existing cache_clear API remains effective.

Retain current session-snapshot caching: an operator DB update is not promised to be
visible inside an already running process. Tests must establish refresh after cache_clear
and new process, rather than inventing a TTL or per-bar DB read. Exceptions remain uncached;
a transient first read failure must suppress firing and retry on the next attempt.
Do not broaden missing-row/NULL/import-unavailable behavior in this narrow change.
Malformed restriction payloads still fail closed even on a stale row. Invalid calibration
dates must never be treated as fresh; pin existing behavior before considering changes.

Emit a numerical-expiry diagnostic with ticker/date/age, defaults selected, and explicit
statement that restrictions are retained (when present). Deduplicate by ticker/date/state
with a bounded cache, cleared alongside explicit cache reset; verify repeated bars do not
flood logs. Do not falsely describe the entire raw row as fresh. Implementing this logging
detail must not change parser failure handling or create a second freshness policy.

## Tests and verification plan

The lifecycle-only implementation footprint remains one runtime file,
lib/strategies/exit_config_overrides.py (reader/cache contract, numerical freshness
filter, bounded diagnostics and docstrings). The only external direct raw-reader
consumer found is lib/signals.py:266; it already uses the row only for condition
restrictions. get_disabled_directions already consumes that reader. The newly confirmed
QQQ reintroduction protection additionally needs a proposed writer guard in
scripts/run_param_sweep.py and schema regression assertions. The writer guard must
validate the actual selected source/destination within the same transaction as the write,
not a racing preflight SELECT. Its exact transaction design belongs in the reviewed plan.
No scoring, monitor or numerical-parameter change is proposed. Schema data mutation is
not authorized; guarding old binaries at the database layer remains outside this draft.
Preserve malformed/missing calibration-date failure behavior when splitting the reader:
removing the age calculation must not accidentally make previously rejected row shapes
valid. Existing future-date behavior is not silently redesigned by this fix.

Test edits are confined to tests/lib/test_exit_config_overrides.py,
tests/lib/test_signals_per_ticker_overrides.py,
tests/gcp/test_signal_monitor_standalone_momentum.py, and the ephemeral-only
tests/integration/test_param_sweep_persistence.py, plus schema assertions in
tests/gcp/test_exit_config_overrides_schema.py. Existing tests/lib/test_backtest_exit_extraction.py
and tests/gcp/test_signal_monitor_exit_watcher.py are regression checks, not a request
to change exit policy. Fixtures mocking the raw row must include a real calibration_date
where numerical getters now evaluate freshness; preserve their original assertions.

Read-only baseline already run on bbc47e87: resolver, per-ticker signals, backtest exit
extraction and standalone-momentum suites, 65 passed in 1.89 seconds. No new tests
written and no new-regression pass claimed before specification approval.

Use the actual resolver with a fake SQL adapter and fixed dates, not a mocked resolver:
179/180 preserve every valid numeric knob; 181 chooses existing defaults while preserving
still-approved restrictions on non-QQQ fixture tickers and both condition names. QQQ's
retired PUT restriction is a contradictory-policy fixture that must be diagnosed, not
preserved as approved. Verify numerical NULL/NaN/inf fallback and exact audit
tier. Warm the cache at 180 then advance the clock to 181 without clearing it. Assert
one SQL read, changed numerical tier, retained restrictions. Cache clear must expose a
new latest row, including explicit empty/NULL restriction clearing without historical carry-forward.

Test stale malformed JSON, dict/false/unknown direction and condition names; query and
engine failures; first failure followed by success; missing row; unconfigured SQL; case
normalization; duplicate restrictions; numeric-only rows; repeated-log bounds.
Execute existing production mean-reversion and standalone-momentum entry functions with
eligible bars: QQQ PUT fires under valid NULL/empty direction policy if other gates pass;
a disabled direction on another fixture ticker does not fire; condition stripping occurs
before score/floor comparison. Legacy QQQ PUT rows raise a visible policy conflict rather
than silently reintroducing that ban. Tests must distinguish this configuration refusal
from ordinary eligibility and retain failure suppression for malformed/unknown inputs.
Use shared live/replay entry fixtures for REQ-REL-001. Unit control-flow evidence is not
performance, calibration fitness, or permission to promote numerical defaults.

Affected suites: tests/lib/test_exit_config_overrides.py,
tests/lib/test_signals_per_ticker_overrides.py, tests/lib/test_backtest_exit_extraction.py,
tests/gcp/test_signal_monitor_standalone_momentum.py; add tests at real consumer boundaries
as needed. Show each new regression failing against main before implementing it.
No network, real SQL, provider requests, notifications or producer execution in tests.

## Capacity, rollout and rollback

No new job, query or schema. For the three live tickers: at most three successful cached
row reads per process as today, plus uncached failure retries as today. Freshness arithmetic
is O(1) per getter; diagnostic state is bounded. Measure query counts and local wall-clock
before documenting cost as unchanged; no production benchmark is authorized.

Preserve historical dates, rows and parameters. Keep signal-monitor-daily paused throughout
development/review. Do not run param-sweep. After separate release authorization, inspect
deployed digest/source, SELECT actual rows, run approved replay proving exact live fire
identities and restriction behavior, and verify diagnostics before separately approving
resume. Numeric-default suitability remains an independent unresolved #862 decision.

Rollback is a reviewed source revert/image rollback only under release authorization;
keep the scheduler held because the old image restores the expiry defect. No automatic
resume, row rewriting, backdating or calibration_date refresh is a rollback step.

## Follow-up provenance and isolated replay design (November 4)

### QQQ decision lineage and limits

- PR #358, commit 52eb69ba, introduced the QQQ PUT seed for G.P1.19 using the
  11.1% MR PUT success figure. It also repaired missing live wiring from #329.
- PR #373, commit 3ec4350a77ae6152bfb866da1b1772e659e6a6dd, removed that seed
  with an explicit statement of user direction. The linked Claude session is
  https://claude.ai/code/session_01P1Y7xYERrFFYdfn1haTZcC. Its original transcript
  has not been retrieved; no verbatim original user instruction about QQQ is available.
  GitHub shows the PR on the owner's account, generated by Claude Code, with no
  conversation comments. Treat the statement as recorded historical intent, not
  independent direct-user authentication or present authorization.
- The incident document records a manual NULL clear at May 9 21:02 UTC. #376
  (created May 10 01:58:08 UTC) explicitly reports a later invocation of the old
  baked migration image re-set QQQ to PUT. It reports another committed clear and
  condition seed, verified in workflow run 25617049383. That run's raw output has
  not been retrieved in this investigation: this is a historical report, not a
  newly verified SQL/audit log. Timeline precision is suspect: #373's incident
  narrative claims #358 merged at 02:09 UTC, while GitHub #358 metadata reports
  created 09:10:43 and closed 09:10:54 UTC. Preserve this inconsistency.
- #376 was closed not_planned in August because the infrastructure flow changed,
  not because a reviewer approved the QQQ restriction. Later #1022 makes unknown
  restriction reads fail closed; it does not establish which directions to disable.
- #380 remains open. It quotes the user's concern about manual indicator removal
  becoming stale and proposes a formal re-evaluation/write-back process. It concerns
  disabled_conditions, not an explicit reinstatement of QQQ disabled_directions.
- Repository commit searches, current specs, PR searches and issue searches found
  no later explicit decision superseding #373. September #1279 and November SQL
  record the actual disabled side; observations are not policy approvals.
  Search coverage cannot prove no private conversation or external SQL action exists.

### Why the current replay cannot establish default fitness

scripts/replay_signal_monitor.py uses production evaluate_ticker but replaces
fire_alert with make_capturing_fire_alert. The stub captures FireRecord and increments
daily_trades; it bypasses _persist_signal_alert, where production appends active_positions.
Therefore it does not reproduce the live position/exit/P&L lifecycle needed to compare
targets and time stops. simulate_exit uses next-bar-open entry, intrabar high/low target
touch and a separate time-stop loop; it is not the live close-price/RSI/time implementation.
gcp/signal_monitor.py:_check_exits uses datetime.now rather than the replay _now clock.
The replay loops all bars of one ticker before the next, which cannot establish shared
portfolio state under a changed exit policy. evaluate_ticker exceptions are logged and
continued, so a result can be incomplete without terminal failure. These are blockers
to decision-grade output, not reasons to run a bespoke profitability simulator.

### Safe proposed experiment, not executed or implemented

1. Approve a separate narrow production-replay repair contract under REQ-REPLAY-002.
   Reuse real fire_alert, position creation, _check_exits and session state; replace
   only external I/O adapters. Fix production-owned replay clock routing and drive
   synchronized ticker bars in observed live polling order. No duplicated scoring
   or exit arithmetic. Make missing inputs and evaluation failures terminal/unavailable.
2. Produce a manifest of immutable, authorized SELECT-only captures: one-minute bars
   including warmup; original live poll timestamps/order if available; briefs and level
   inputs known at each instant; calibration/restriction rows; effective configuration;
   strategy-route tags; alerts/trades and exposure state for parity. Hash files and pin
   deployed code digest. Do not invent unavailable historical revisions or fill gaps.
   Partition exports by session/ticker with row caps/timeouts and record extraction time.
   New production captures, if needed, use only the documented rollback diagnostics.
3. Run in a credential-free container with no network, read-only code/input mounts and
   a writable local results directory. Do not mount gcloud/ADC/secrets. Local fixture
   adapters refuse unknown reads and all external writes; local event capture is allowed.
   Explicitly omit --persist and unset REPLAY_PERSIST. These flags alone are not safety:
   the OS network boundary plus absent credentials must enforce isolation. Do not invoke
   param-sweep, production schedulers, notifications, schema application or write helpers.
4. First reproduce a known session using the original code/config and exact inputs.
   Match ticker, direction, fire timestamp, route, size, active position context, target,
   time stop, exit reason/time and realized state. Counts alone do not pass. Minute OHLC
   may not reproduce vendor polls/sub-minute timestamps: if raw poll snapshots are absent,
   record that fidelity limit and stop claims of exact parity rather than adding tolerance
   that masks the difference. No re-evaluation approval follows a failed parity gate.
5. Once parity is demonstrated, compare two predeclared isolated arms: recorded numerical
   overrides versus current numerical defaults. Keep restriction policy, scoring mix,
   blue-sky levels, costs and all unrelated settings identical in both. Supply original
   dated values as explicit local scenario inputs; never rewrite calibration dates to
   force freshness. Run expiry correctness separately from numerical policy comparison.
   Apply the now-confirmed QQQ-allowed policy identically in both numerical arms; keep
   any historical QQQ-blocked reproduction separately labelled. Never change both axes
   and attribute the result to numerical defaults.
6. Start with one complete captured session as a fidelity/capacity pilot, then evaluate
   a predeclared development window and untouched later holdout across all three tickers.
   Fix the window and objective before inspecting outcomes; report per-strategy/side/ticker
   coverage, paired session return differences, trade identity changes, drawdown/tail losses,
   duration, concurrency, cap effects and missing-data rates. Use chronological blocks for
   uncertainty; do not claim significance from a tiny cohort. Research underlying-price
   returns do not establish executable option P&L without option quotes/fill evidence.
7. Acceptance objective, minimum cohort size, cost/slippage assumptions, and allowable
   tail/drawdown tradeoff need owner/research review. No automatic winner or promotion.
   A reviewed local result still does not authorize deployment, data changes or resume.

Capacity pilot: 3 tickers x (99 warmup + 390 regular bars) = 1,467 input rows per
ordinary session; two arms = 2,340 evaluated ticker-bars plus warmup processing.
At an illustrative 1 KiB normalized record, raw bar input is about 1.43 MiB/session,
excluding context and outcomes; measure real bytes and CPU in the pilot before scaling.
Zero network calls during replay. Bound rows/sessions, memory, output and wall-clock
before execution; a timeout produces unavailable results, not partial fitness evidence.

## Existing-captures feasibility result

### Capture feasibility check, November 4 approximately 22:02 UTC

No sufficient historical monitor-poll/context bundle was found. Do not schedule a large
replay repair on the assumption that such inputs exist.

Read-only GCS inspection of the configured trading-data bucket found raw/, research/,
audit-reports/, recovery-artifacts/, direction-program/ and other infrastructure prefixes.
Complete listings of raw/{spy,iwm,qqq}/intraday/ returned four files per ticker, latest
updated May 10; raw/{ticker}/minute/ returned 25 files each, last named May 8 and latest
updated May 9. A read of spy_av_1min_202605.parquet found 5,765 rows with exactly ts,
open, high, low, close, volume, ticker, interval and data_source: no retrieval time,
poll identifier, ordered response membership or revision clock. Other research-prefix
names describe backtest/STRAT outputs, not evidence of captured live polling. Top-level
and relevant raw-prefix inspection is not an exhaustive search of every object or bucket.

Existing November 4 log capture contains 1,655 entries and 381 Polling messages, with
zero Time Series/provider payload/bar snapshot messages. Example: embedded 09:30:22 EST
poll start was ingested at 15:12:43.943093 UTC alongside later buffered messages. It can
recover approximate loop starts, not exact per-ticker response content/timing or failed
requests' prior-window state. fetch_latest_bar reads each compact 100-bar response and
returns a DataFrame without writing it; update_window overwrites duplicate bar timestamps
with the latest value. market_data_intraday's key is ticker/interval/ts, not observation
revision. Final historical bars cannot reconstruct those overwritten intrapoll values.

Persisted alert/trade rows provide selected fires and exits, not all rejected candidates
or contemporaneous indicator/context inputs. premarket_analysis_history may help recover
brief revisions but its existence does not prove the exact cached revision selected by
each poll. Local STRAT replay artifacts explicitly describe synthetic brief/insight tests,
not a qualified historical signal-monitor capture; do not reuse their pass as market parity.

Smallest reliable next step: keep lifecycle and QQQ policy correctness work separate from
policy fitness. Existing actual _check_exits tests plus frozen resolver scenarios can
validate mechanical target/time behavior without market claims, after spec approval.
For fitness, first require one complete immutable session capture (raw ordered responses,
request/evaluation clocks, as-seen context/config, and observed state/output). No such
bundle was established here. An externally supplied existing capture can satisfy this;
otherwise prospective observation requires separately approved capture work and must not
restart the held monitor by implication. Only after one bundle passes completeness should
the smallest replay adapter/parity pilot be implemented. If only historical final bars
are available, an approximate fixed-entry sensitivity exercise must remain explicitly
non-decision-grade; it cannot validate defaults for the stateful current strategy mix or
authorize resume. No SQL job, replay, param-sweep, production write or restart was run
during this capture check.

## Bounded self-review and next approval

One complete author self-review of the revised draft was performed November 4 under
brainstorming's Spec Self-Review instructions (placeholders, consistency, scope, ambiguity).
Corrections in that pass: distinguish the approved QQQ policy from proposed option 1;
remove the contradictory requirement to retain QQQ's retired ban; specify source AND
same-day destination writer checks; limit the before-write guarantee to override writes;
separate replay feasibility from implementation scope; distinguish numeric read fallback
from a policy conflict; qualify old-binary/manual-SQL protection and warm-cache limits.
This is author review, not independent or authenticated external approval. No hosted
review rounds have been used and no review counter has been reset.

Remaining gates, in order:
1. Normal spec-only PR review and CI with no unresolved threads. Owner approval of the
   complete written specification is recorded above; it is not pending.
2. Land the approved specification on main, then invoke writing-plans. No implementation
   begins before that merge. Complete the candidate changed-file inventory before scheduling
   implementation; a historical cross-reference does not establish coverage.
3. Numerical fitness remains a release blocker, not a reason to invent values.

The product-delivery skill requires "Never write implementation code before a spec has
status: approved" and requires that spec on main before implementation. Brainstorming's
User Review Gate says "Only proceed once the user approves." No external review agent
is required for this current author self-review step by the instructions read. No agent
was spawned and no external message was sent. If the later PR workflow needs an external
reviewer, use an explicitly authorized available reviewer and preserve the two-round cap;
do not count this self-review as one of those approvals.

## Owner decision brief — November 4 follow-up

QQQ PUT eligibility and independent retention of the following condition exclusions are
settled by the two owner decisions above. The brief below records the selected behavior.

| Latest recorded restriction (21:44:08 UTC capture) | User-visible meaning |
|---|---|
| IWM: `stoch_rsi_overbought`, `rsi_overbought_zone` | These two conditions contribute no points to mean-reversion PUT scoring. |
| QQQ: the same two conditions | The same scoring exclusions; QQQ PUT remains eligible if its remaining score and other gates qualify. |
| SPY: no condition exclusions | No equivalent scoring exclusions recorded. |

These are not hard prohibitions on signals whenever RSI is high. Each excluded condition
would otherwise add one point when true. Removing those contributions can prevent a PUT
from reaching its minimum score or change the CALL/PUT tie comparison. Exact alert-count
or performance changes cannot be inferred without a qualified replay. They do not directly
change standalone momentum's condition scoring or live exit thresholds. No other direction
restriction is recorded for these three tickers after excluding the retired QQQ PUT value.
This inventory is scoped to the three captured monitor tickers, not every database row.

Alternatives considered (option 1 selected):

1. **Selected: retain the condition exclusions until explicitly changed.** Numerical
   calibration can expire independently; its existing fallback remains visible and must
   be validated before restart. A new valid latest snapshot can explicitly clear or replace
   exclusions under existing NULL/empty semantics. Users retain the intended selective
   scoring behavior without an automatic age-based signal outage. The tradeoff is that an
   ineffective old exclusion can remain until reviewed; retention is not proof of fitness.
2. **Stop new signals when a ticker's calibration expires.** This avoids evaluating new
   entries with expired calibration, even if the restrictions remain readable. Because all
   three captured calibrations expire together, a ticker-wide rule would stop new SPY,
   IWM and QQQ entries, both directions and both MR/standalone momentum, until a reviewed
   usable calibration exists. It must leave existing-position exit handling and EOD
   reconciliation operational. A narrower IWM/QQQ-only or MR-only stop is a different
   contract and must not be assumed. This alternative needs revised acceptance tests.

Recommendation rationale: current schema comments explicitly favor condition-level
adjustments over static direction gates, and #1022 preserves operator restrictions when
configuration is valid while refusing unreadable/malformed configuration. Separating a
known exclusion from numerical freshness preserves that distinction with the smallest
policy change. This lifecycle is now supported by the explicit owner decision above,
not an invented historical approval. The canonical requirements file labels requirements
PROPOSED — TARGET. Numerical suitability remains independently unproven.

The approved contract in plain language is: keep QQQ PUT eligible; prevent the
supported schema/calibration paths from restoring its retired ban; preserve other explicit
condition exclusions independently of numeric age; retain the existing strict >180-day
numeric expiry and values without rewriting dates; make conflicts and unreadable or malformed
controls visible and suppress affected new entries; re-evaluate numeric age across midnight
while documenting the process-snapshot cache; test boundary dates, both actual fire paths,
writer source/destination conflicts, errors, logs and refresh behavior. Keep the monitor
held until the existing conflicting row is separately corrected with authorization, deployed
images/writer paths are checked, and numerical defaults are validated through a qualified
production replay. Rollback keeps the hold; it must not restore a known conflicting image.
No deployment, SQL correction, recalibration, new capture or restart is authorized by this
specification. Option 1 and the complete written contract are approved. Implementation
follows approved-spec-on-main, plan, PR review and CI gates.

## Expanded existing-capture search — 22:09:56 UTC

Read-only complete object-name listings in the existing trading-data bucket covered
recovery-artifacts/ (3), audit-reports/ (48), research/ (1,617), direction-program/ (30)
and retired/ (3). Candidate-name review found a recovery manifest, which was fetched and
read. It identifies a 30-member October 23 current-vintage reacquisition archive, including
IWM/QQQ minute responses and an SPY one-minute probe, not the original live monitor session.
Its own flags say `historical_input_qualification: false`, `original_library_export_confirmed:
false`, and `source_capture_vintage: 2026-10-23 new acquisition; original467filecapture
remainsmissing`. The inventory has no ordered per-poll response/context/state bundle.
A raw provider response is useful but is not evidence of what the monitor saw at each poll.
The local September live_gcp_snapshot fixture inventories infrastructure and row counts,
not market-response sessions. No sufficient session capture was established by these
additional checks. Object names do not prove archive contents universally absent; unrelated
buckets, externally held exports and private libraries were not exhaustively searched.

Local evidence: `/tmp/stocks-862-capture-search-expanded.json` and
`/tmp/stocks-862-existing-recovery-manifest.json`. No production data or configuration
was created or changed, no diagnostic SQL job was launched, and no replay was executed.

## Approval reconciliation check

After the second owner decision, reconciled all current decision/status sections: option 1
and unreadable-control suppression are selected, QQQ remains eligible, and the old demand
for another lifecycle choice is removed. No acceptance item was weakened, no new numeric
value was selected, and the deferred pre-expiry warning is explicitly outside scope.
Written-artifact approval is distinguished from behavior approval. This is an author
consistency correction, not a new hosted review round or an external review attestation.

## Publication reconciliation

Recorded the later written-artifact approval and duplicate-work check. Changed approval
status/provenance only; the seven acceptance items and technical behavior in the attached
review copy remain unchanged. Repository validation and independent PR review are separate
from owner approval. No production authorization is inferred from either.
