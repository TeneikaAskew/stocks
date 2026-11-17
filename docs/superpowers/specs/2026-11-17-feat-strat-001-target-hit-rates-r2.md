---
feat_id: FEAT-STRAT-001
req_ids: [REQ-PLAYBOOK-001, REQ-DATA-001, REQ-REL-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "Policy: gcp/schema.sql seeds one new level_param_policy row target_reach_rate (method_id plan_excursion_share, lookback_sessions NULL, min_sample 30, effective 2015-01-02, extra {\"since\": \"2022-01-03\", \"measure\": \"touch_atr\"}) with ON CONFLICT DO NOTHING; no other level_param_policy row changes; lib/strat_levels.py names the key once (TARGET_REACH_RATE_KEY) in POLICY_WIDE_KEYS, and policy_wide_param gives it status ok with value equal to min_sample when min_sample is a positive integer, lookback_sessions is NULL or a positive integer, since is an ISO date and measure is one of touch_atr, held_5m_atr, touch or held_5m, and input_unavailable otherwise; a test in tests/lib/test_level_params_loader.py loads the seeded policy from gcp/schema.sql and asserts status ok and value 30, and each unusable field gives input_unavailable"
  - "Table: gcp/schema.sql creates plan_excursions (ticker, session_date, rule_version, side, trigger_price, stop_price, fill_price, fill_ts, stop_ts, atr, excursion_r, excursion_held5_r, excursion_atr, excursion_held5_atr, source, resolver_version, written_at) with PRIMARY KEY (ticker, session_date, rule_version), CREATE TABLE IF NOT EXISTS, source limited to resolver or history by a CHECK, and atr NULL or positive by a CHECK; tests/gcp/test_schema_sql.py (or the file that already checks schema.sql) asserts the table, key and both checks"
  - "Excursion: a pure function in gcp/premarket_playbook_resolver.py, sharing resolve_plan's entry walk (no second copy of it), returns for one side on the session's bars cut at the exchange close and the basis's ATR: nothing unless the side is entered with a valid stop; otherwise the fill bar, the stop bar (the first bar from the fill bar on that touches the stop, or none), excursion_r and excursion_held5_r as Design 3 defines them, and excursion_atr and excursion_held5_atr, the same two distances divided by the ATR (NULL when the basis has no ATR or the distance is NULL); tests/gcp/test_premarket_playbook_resolver.py pins hand-built sessions for calls and puts: a rung touched only on the fill bar is not reached, a bar touching the stop and a rung counts the stop first, no bar between the fill bar and the stop bar gives NULL for all four, five closes beyond a level that end on the stop bar do not count as held, a cross bar that opened beyond the trigger is still measured from the trigger, a call with trigger 100.00, stop 99.00 and ATR 2.00 whose high reaches 103.00 before a later stop gives excursion_r 3.0 and excursion_atr 1.5, the mirrored put (trigger 100.00, stop 101.00, ATR 2.00, low 97.00) gives the same, and a basis with no ATR gives NULL for both ATR values and the stop-distance values unchanged; on every fixture a rung counts as reached exactly when a bar after the fill bar touches it before the stop bar; the rung at or behind the fill fixture (trigger 100, stop 99, cross bar opening at 102, a later high of 102.9: excursion_r 2.9, rungs 101 and 102 reached, rung 103 not) and the existing test_a_gap_fill_past_t1_and_t2_holds_every_leg_to_the_close still pass unchanged"
  - "One trade per ticker-day: the function that picks the row takes both sides' results and returns the side whose fill bar is earlier; both sides filled on the same bar, or neither entered, gives no row; tests cover the four cases"
  - "Entry rule version: lib/strat_levels.py defines entry_rule_version(version), the rule version whose entry trigger and stop rule a basis of that version uses; on this change it returns its argument for every version is_current_pick_rule accepts and None for any other; it is added to the allowed sites of the rule-version meta test and no other comparison with a rule version is added; tests/lib/test_strat_levels.py pins each version on main and an unknown one"
  - "Live writer: resolve_one upserts at most one plan_excursions row per resolved (analysis_date, ticker) with source resolver, rule_version entry_rule_version of the basis's rule_version, the basis's ATR and RESOLVER_VERSION, in the same transaction as the premarket_analysis update; re-resolving with force replaces it, and when the forced re-resolution gives no trade (a same-bar tie or no entry) it deletes the existing row for that ticker, session and rule version in the same transaction, pinned by a writer test that first resolves a trade and then force-resolves the session to no trade; a row whose basis has no rule_version, or whose entry_rule_version is None, writes nothing; RESOLVER_VERSION moves to the next version after the one on the implementation's merge base; the existing outcome and plan columns are byte-identical to origin/main's on the existing resolver tests"
  - "History writer: gcp/backfill_plan_excursions.py (TICKERS, START, END; START defaults to the policy row's since) rebuilds each session's level basis through the same build the brief runs under BRIEF_AS_OF, with no_persist so nothing is written to premarket_analysis or premarket_analysis_history and no model is called, reads one ticker-month of market_data_intraday bars per query, scores with the Excursion function and upserts source history rows keyed by entry_rule_version of the rebuilt basis's version, that never replace a source resolver row, and deletes its own source history row for a session that now gives no trade; a re-run over the same span writes the same rows; tests cover resume, the delete, the never-replace rule and that no model client is called; the job's deploy entry is not part of this change (gcp/deploy.sh belongs to FEAT-DEPLOY-001 and is changed there)"
  - "Reader: lib/target_reach.py loads, in ONE query per brief run for all of the run's tickers, the excursions of rows whose rule_version equals entry_rule_version of the basis being built (never a constant), session_date before the brief's session and on or after since (or within the last lookback_sessions sessions when that is set), and gives per ticker the trade count, the first and last dates, and for any distance the number of trades whose excursion in the policy's measure column is at least that distance, NULL counting as reaching nothing; a failed query or a missing table raises and the brief prints the unavailable line of Design 5 for that ticker, never a count; tests cover the window, the point-in-time cut, each of the four measures, the version filter and the NULL rule"
  - "Brief copy: tests/lib/test_strat_levels.py has a golden on the IWM 2025-10-22 basis (tests/fixtures/iwm_2025_10_22_level_basis.json) with a fixed reach table equal to the Experiment's 906 IWM trades before that date in ATR, giving the puts block of Design 5 byte for byte: the counts line after the stop line and each target line ending with its count and percent; with fewer trades than min_sample each line ends with the count and no percent; with no trades each line ends with 'no history yet' and never '0 of 0'; the unavailable line and the no-stop line are pinned; in every case every other line of the side's block is unchanged, there is no line of rungs separate from the target lines, and with no reach table passed (every caller but the brief) format_levels_for_brief's output equals origin/main's, so the existing D8 goldens are unchanged"
  - "Wired into the brief: a test in tests/gcp/ on generate_premarket_brief (the production path, BRIEF_AS_OF with a stubbed database) asserts that the run issues the reach read once for all of its tickers, that the stored playbook text carries the counts of Design 5 on the target lines, and that a failed reach read leaves every ticker's brief written with the unavailable line in place of the counts (no PLAYBOOK_FAILED, no count)"
  - "Unchanged, each pinned by an existing test that passes on origin/main and on the implementation head: the trigger and stop rule, gate targets and the t1..t3 columns, the plan's targets, spacing, thirds, entry cutoff and gap edges, the ATR levels line, the signal monitor, the movement statement, persona plans and every premarket_analysis column the resolver writes today; LEVEL_RULE_VERSION does not change"
  - "Experiment through the production paths, before any production change: the implementation PR body shows the history writer run on a local copy built like this spec's Experiment (as-traded bars, 2022-01-03 to 2026-11-10, SPY 2025-04-09 and IWM 2026-06-26 left out) producing the same 3,463 trades (same ticker, date, side and stop) and, on every trade filled at the trigger, excursions in stop distances and in ATR within 1e-6 of this spec's rows; Tables 3, 4, 6 and 7 reproduced from those rows; and the measured wall-clock per ticker, which sets the job's timeout at four times or more; a reproduction for the record, not a gate"
  - "Source identity (DASHBOARD-01): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-STRAT-001, DASHBOARD-01) note row carries that source_identity_sha256 with implementation and test prose for this PR"
  - "The FEAT-STRAT-001 catalog record and the PR traceability entry are updated; python3 scripts/gate/spec_gate.py --pr origin/main passes; the owner's merge of the implementation PR is the yes for the table and the policy row, which the apply-schema build creates from gcp/schema.sql on that merge (both additive: CREATE TABLE IF NOT EXISTS and ON CONFLICT DO NOTHING), before any deploy; the deploy and the history run each wait for their own yes and are recorded with their row counts"
status: approved
supersedes: docs/superpowers/specs/2026-11-16-feat-strat-001-target-hit-rates.md
---

# Each target line in the brief says how often price has reached it before the stop, back to 2022

## What changed from r1

This spec (r2, 2026-11-17) supersedes `docs/superpowers/specs/2026-11-16-feat-strat-001-target-hit-rates.md`
(r1: approved, merged in stocks #1996), which is marked `superseded` in the same commit, its
`status` line the only edit to it. The build plan bound to r1 (stocks #2005) is pointed at this
file by its own change before the implementation PR opens, since the gate refuses a plan bound to a
superseded spec.

The owner chose one set of target lines on 2026-11-17 (below). So:

1. **No separate ladder.** r1 printed a block of up to six rungs under each plan. Now each target
   line the plan already prints ends with its count. Under today's rule those are the plan's level
   targets; once the quarter-target change is built, its four ATR targets and the levels between
   them read the same counts through the same reader (that change's own revision).
2. **Distances in ATR.** The quarter targets are fractions of ATR from the trigger, so the counts
   are read in ATR. Out of sample ATR scored better than stop distances (Table 6). The table keeps
   both, and the measure is a policy value.
3. **Counts, with a percent once there are enough trades.** Each line reads `reached k of n (p%)`;
   below the policy's minimum it reads `reached k of n`; with none, `no history yet`. The same words
   the quarter-target spec prints.
4. **History from the first day.** Rows are keyed by the rule version that sets the trigger and
   stop (`entry_rule_version`), not by the version that picks targets. The quarter targets keep
   today's trigger and stop, so the history this job writes from 2022 serves their lines on the day
   they go live, as the thirds test did.
5. **The history job's deploy entry** is left to a FEAT-DEPLOY-001 change; the gate assigns
   `gcp/deploy.sh` there.

Unchanged from r1: the table's one trade per ticker-day, the excursion rule, the writers, the
policy row's window, per-ticker reading with sides pooled, the Experiment's Tables 1 to 5 and every
non-goal.

## Authority

The owner asked on 2026-11-11 (UTC) for experiments on "did it hit the levels" (T1, T2, T3, held 5
or more minutes), and on 2026-11-15 (UTC) said "Ok so I like this" to a brief showing each rung's
hit rate. On 2026-11-16 the owner moved the exit plan to quarter targets at 25, 50, 75 and 100
percent of ATR ("Quarters not Thirds anymore", approved spec
`docs/superpowers/specs/2026-11-16-feat-strat-001-atr-quarter-targets-r2.md`) and asked to "align
it to that plan with the atr targets and levels". On 2026-11-17 (UTC) the owner answered "Yes" to:
should the hit rates go on the new quarter-target lines instead of a separate ladder, with history
back to 2022; and added "When I did thos in thirds it was able to go back. Do last week's".

Rulings still in force: values are never hard-coded and come from policy or per-ticker rows
(2026-11-08); a change is tested before it is swapped in; R and every distance here are the stock's
move, in stop distances or in ATR, never money, and comparisons are like for like; 1-minute bars
are as-traded and come only from the store the nightly fills (2026-11-13).

Written by a FEAT-STRAT-001 delivery lane and not self-approved: it takes effect only when the owner
merges the spec-only PR that adds it, and that merge is the approval its `status` records.

## Problem

The brief prints each side's targets but never says how often price has got that far. The owner
wants every target line to say so, measured on the ticker's own trades since 2022, and wants the
quarter targets to show that history from their first day rather than an empty count.

What decides the rate is how far the line is from the trigger, not its number: the first rung of
r1's ladder was reached 75% of the time when it was a near level and 25% when it was the plan's T1
further out (Table 2).

## Non-goals

- Exits and targets. The plan's targets, spacing, legs, cutoff and gap edges are unchanged here; the
  quarter targets are their own spec. Counts describe reach; they do not pick targets.
- Rating the ATR levels line, the NEXT LEVELS list or PMG ZONES.
- The movement statement's own reach rates and its feature flag.
- The signal monitor, Discord alerts and persona plans.
- Judging a level's quality.

## Decisions for the owner (recommended pick first)

1. **Distance in ATR (recommended)** or in stop distances. ATR matches the quarter targets and
   scored better out of sample (Brier 0.1426 against 0.1539, Table 6). Both are stored; switching is
   a policy edit.
2. **Touch (recommended)** or held 5 minutes. Touch is a bar reaching the line, the same test the
   exits use. Held 5 reads up to 8 points lower on the first quarter (Table 7). Both are stored.
3. **Window: every trade since 2022-01-03 (recommended)** or the last 250 sessions. The windows tie
   (Table 6); full history gives about four times the trades.
4. **Per ticker, sides pooled (recommended).** Per ticker follows the 2026-11-08 rule; per ticker
   and pooled tie (Table 4), and splitting calls and puts scored slightly worse.
5. **Counts with a percent from 30 trades (recommended)** or counts only. The quarter spec prints
   counts; with about 900 to 1,150 trades a ticker, the percent is easier to read. Below 30 trades
   (the movement statement's LOW_SAMPLE_THRESHOLD) only the count prints.
6. **Rows keyed by the entry rule (recommended)** or by the full rule version. Keyed by the entry
   rule, the quarter targets read the history from 2022 on day one, because they keep today's
   trigger and stop. Keyed by the full version, they start at `no history yet` and fill one session
   a day. A later level rule that moves triggers or stops gets its own entry version, and the
   history job is run again for it.

## Approaches considered

1. Chosen: a reach curve per ticker, read on each target line. Store, for every past trade, how far
   price went past the trigger before the stop; a line's count is the trades that went at least
   that far.
2. r1's separate ladder of up to six rungs. Replaced on the owner's 2026-11-17 answer: one set of
   target lines.
3. The quarter spec r2's two `*_plan_mfe_atr` columns on `premarket_analysis`. They hold the same
   number but only for sessions the resolver scores from deploy on, so the lines start empty; its
   revision reads this table instead.
4. Rates by rung number or by distance band: rejected on Table 4.

## Design

### 1. The policy row

`gcp/schema.sql` seeds, next to the gap-edge row:

```sql
('target_reach_rate', 'plan_excursion_share', NULL, NULL, 30, '{"since": "2022-01-03", "measure": "touch_atr"}',
 '2015-01-02', 'trades a target count is read from: since a date or the last lookback_sessions; touch_atr, held_5m_atr, touch or held_5m; a percent from min_sample'),
```

`policy_wide_param` reads it like the other policy-wide keys. `lookback_sessions` NULL means every
session from `since` on; a positive number means only the ticker's last that many sessions before
the brief's. `measure` names the column read: `touch_atr` is `excursion_atr`, `held_5m_atr` is
`excursion_held5_atr`, `touch` is `excursion_r`, `held_5m` is `excursion_held5_r`. A line's distance
is read in the same unit. A missing or unusable row gives `input_unavailable`, and the brief prints
the unavailable line, never a count (CLAUDE.md 3.7).

### 2. The table

```sql
CREATE TABLE IF NOT EXISTS plan_excursions (
    ticker               VARCHAR(10)      NOT NULL,
    session_date         DATE             NOT NULL,
    rule_version         VARCHAR(40)      NOT NULL,
    side                 VARCHAR(5)       NOT NULL CHECK (side IN ('calls', 'puts')),
    trigger_price        DOUBLE PRECISION NOT NULL,
    stop_price           DOUBLE PRECISION NOT NULL,
    fill_price           DOUBLE PRECISION NOT NULL,
    fill_ts              TIMESTAMPTZ      NOT NULL,
    stop_ts              TIMESTAMPTZ,
    atr                  DOUBLE PRECISION CHECK (atr IS NULL OR atr > 0),
    excursion_r          DOUBLE PRECISION,
    excursion_held5_r    DOUBLE PRECISION,
    excursion_atr        DOUBLE PRECISION,
    excursion_held5_atr  DOUBLE PRECISION,
    source               VARCHAR(10)      NOT NULL CHECK (source IN ('resolver', 'history')),
    resolver_version     VARCHAR(40)      NOT NULL,
    written_at           TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, session_date, rule_version)
);
```

One row per ticker-day that had a trade: the first side to fill. A day where both sides filled on
the same bar, or neither entered, has no row, as in the 1832 tests. `rule_version` is
`entry_rule_version` of the basis's version (Design 4). `atr` is the basis's own ATR for its
`atr_basis`, the same number the plan's ATR targets are built from.

### 3. The excursion

On the session's regular-hours bars cut at the exchange close (13:00 ET on a half day), with the
entry walk `resolve_plan` already uses (opened through, no cross and late cross are not entries; the
fill is at the trigger, or at the open of a cross bar that opened beyond it):

- The fill bar is the first bar that reaches the trigger. The stop bar is the first bar from the
  fill bar on that touches the stop.
- The excursion is the furthest the high (calls) or low (puts) went past the trigger on the bars
  after the fill bar and before the stop bar. `excursion_r` is it divided by the trigger-to-stop
  distance, `excursion_atr` by the ATR. NULL when there is no such bar; NULL reaches nothing.
- The held excursion is the same for the furthest price that five consecutive closes all stayed at
  or beyond, every one of them before the stop bar: `excursion_held5_r`, `excursion_held5_atr`.

So a line `d` past the trigger is reached exactly when the excursion is at least `d`, in the same
unit: a bar after the fill bar touched it before any bar touched the stop, a bar touching both
counting the stop first. For a line beyond the fill that is the walk the plan's exits use. The
Experiment checked the rule on all 8,022 rungs.

### 4. Who writes it, and under which version

**`entry_rule_version(version)`** in `lib/strat_levels.py` names the rule version whose entry
trigger and stop rule a basis of `version` uses. On this change it returns its argument for every
version `is_current_pick_rule` accepts, and None otherwise. The quarter-target change maps its
marks version to the level version it is built on, because that change keeps the trigger and stop
(its Design 1). It joins the allowed sites of the rule-version meta test; nothing else compares a
rule version.

- **Every resolved day:** `resolve_one` writes the day's row after it scores the plans, in the same
  transaction, `source` resolver, `rule_version` the entry version. A forced re-resolution that now
  gives no trade deletes the day's row. `RESOLVER_VERSION` moves. Nothing else it writes changes.
- **History, once per entry version:** `gcp/backfill_plan_excursions.py` rebuilds each session's
  level basis the way the brief builds it under BRIEF_AS_OF with `no_persist` (nothing written to
  `premarket_analysis`, no model called), scores it with the same function on
  `market_data_intraday` bars, and writes `source` history rows only, never replacing a resolver
  row. It runs per ticker, one month of bars per query, and resumes where it stopped. Its deploy
  entry is a FEAT-DEPLOY-001 change.

### 5. What the brief will look like

The brief reads the counts in one query per run (Design 1's window, sessions before the brief's own,
the basis's entry version only). After the stop line of each side with a plan it prints one line
naming the trades counted, and each target line ends with its count. No other line changes and no
line is added between the targets.

IWM on 2025-10-22, puts side (trigger 245.66 PMK_L, stop 246.99 PDC, ATR(14) 4.48), counted from
the 906 IWM trades from 2022-01-03 to 2025-10-21. Today:

```
  PUTS below 245.66 (PMK_L), new entries 09:30 to 10:00 ET
    No entry if the open is at or below 245.66.
    Stop: 246.99 (PDC)
    T1: 243.41 (PWC), sell 1/3
    T2: 241.96 (PMC), sell 1/3
    T3: 240.36 (PWL), sell the last 1/3, or hold to the close or the stop
    Skipped, closer than 0.25 x ATR(14) = 1.12: 245.50 (PDL), 244.98 (PYH)
    Room to trigger: 0.24%
```

After:

```
  PUTS below 245.66 (PMK_L), new entries 09:30 to 10:00 ET
    No entry if the open is at or below 245.66.
    Stop: 246.99 (PDC)
    Reached before the stop: IWM trades 2022-01-03 to 2025-10-21 (906)
    T1: 243.41 (PWC), sell 1/3, 0.50 ATR past the trigger, reached 245 of 906 (27%)
    T2: 241.96 (PMC), sell 1/3, 0.82 ATR past the trigger, reached 81 of 906 (9%)
    T3: 240.36 (PWL), sell the last 1/3, or hold to the close or the stop, 1.18 ATR past the trigger, reached 23 of 906 (3%)
    Skipped, closer than 0.25 x ATR(14) = 1.12: 245.50 (PDL), 244.98 (PYH)
    Room to trigger: 0.24%
```

That day price reached T1 and T2 before the stop and missed T3 (low 240.77). Once the quarter
targets are built, the same day's lines would read T1 244.54 reached 475 of 906 (52%), T2 243.42
247 (27%), T3 242.30 105 (12%), T4 241.18 38 (4%), with PDL 245.50 (802, 89%) and PYH 244.98 (616,
68%) as levels on the way, in that change's own words.

With fewer trades than the minimum each line ends `reached 12 of 20`, no percent. With none, each
line ends `no history yet`. With the row or the table unusable the counts line reads
`    Reached before the stop: unavailable (input_unavailable).` and no target line carries a count. A
side with no stop, or a stop not on the losing side of the trigger, reads
`    Reached before the stop: unavailable (no stop to measure from).` A side with no plan prints
nothing new.

### 6. Production order

`gcp/cloudbuild/apply-schema-cloudbuild.yaml` applies `gcp/schema.sql` on every push to main that
touches it, so the table and the policy row are created when the implementation PR merges, before
anything is deployed; the owner's merge of the implementation PR is the yes for them. Both are
additive: nothing live changes until the deploy. Then, each on its own yes:

1. The history job's deploy entry, through its FEAT-DEPLOY-001 change.
2. Deploy the resolver and the brief. Until step 3 every line reads `no history yet`.
3. Run `gcp/backfill_plan_excursions.py` per ticker and record the rows written per ticker.

The order can be 1, 3, 2 to avoid any day of `no history yet`.

## Experiment

Hypothesis (r1): a line's chance of being reached before the stop is set by its distance from the
trigger, so a per-ticker reach curve rates every line better than a table by rung number. Added in
r2: in ATR the curve rates at least as well as in stop distances, so the quarter targets can read
it.

Data (read only, not in the repo): the same 3,463 trades as the 1832 and gap-edge tests (SPY 1,161,
QQQ 1,152, IWM 1,150; 1,212 sessions from 2022-01-03 to 2026-11-10; one trade per ticker-day, the
first side to cross its trigger; a same-bar tie is no trade; SPY 2025-04-09 and IWM 2026-06-26 left
out), from the Nov 15 combined-ladder run, with the as-traded 1-minute bars in
`/mnt/project-files/stocks-scorecard/research/fable_lab/data/bars_1min/` (to 2025-02) and
`/mnt/project-files/stocks-scorecard/inputs/bars_raw/` (from 2025-03), half days cut at the exchange
close. Each trade's ATR is the basis ATR stored with it (`ladder6_all.csv`, column `atr`), and its
excursion in ATR is its excursion in stop distances times the stop distance over that ATR.
Distances are measured from the fill, which is the trigger except when the cross bar opened beyond
it.

Table 1, reproduction: the share of all 3,463 trades reaching combined-ladder rung 1 to 6 is 46.5%,
21.1%, 7.8%, 1.6%, 0.2%, 0.0%, as reported on 2026-11-15.

Table 2, why the rung number misleads (rung 1 only):

| Rung 1 | Rungs | Reached before the stop |
|---|---|---|
| All trades with a rung 1 | 3,075 | 52.3% |
| A current-rule target only | 1,656 | 74.5% |
| Both a current-rule and a plan target | 1,354 | 24.9% |
| Under 0.5 stop distances past the fill | 1,397 | 78.3% |
| 2 to 3 stop distances | 246 | 11.8% |
| 3 or more | 245 | 6.5% |

Table 3, the reach curve per ticker in stop distances (touch / held 5 minutes):

| Ticker | 0.25 | 0.5 | 1 | 1.5 | 2 | 3 | 4 |
|---|---|---|---|---|---|---|---|
| SPY | 77/65 | 60/51 | 36/30 | 23/19 | 15/12 | 6/5 | 3/2 |
| QQQ | 77/63 | 58/50 | 38/33 | 25/21 | 17/14 | 8/7 | 4/4 |
| IWM | 78/63 | 62/51 | 41/34 | 27/21 | 17/14 | 7/7 | 3/2 |

Table 4, out of sample (fitted 2022-01-03 to 2024-06-28, scored 2024-07-01 to 2026-11-10, 3,880
rungs). Brier score, lower is better: one rate for every rung 0.2213; by rung number 0.1919; by
distance band 0.1557; reach curve pooled 0.1535; per ticker 0.1537; per ticker and side 0.1544.

Table 5, window, walk-forward in stop distances: since 2022-01-03 0.1532; last 500 0.1527; last 250
0.1526; last 120 0.1536.

Table 6 (r2), ATR against stop distances, same rungs, per ticker, Brier:

| Scored | Stop distances | ATR |
|---|---|---|
| Fixed split, as Table 4 | 0.1539 | 0.1426 |
| Walk-forward, every trade since 2022-01-03 | 0.1534 | 0.1425 |
| Walk-forward, last 250 sessions | 0.1528 | 0.1431 |

This run used a per-ticker, per-day ATR scale from the rung rows (3,075 trades); the implementation
reruns it on the job's own rows with each trade's ATR.

Table 7 (r2), the quarter marks: trades reaching 25, 50, 75 and 100 percent of ATR past the fill
before the stop, every trade with its own ATR (touch, then held 5 minutes):

| Ticker | Trades | 25% | 50% | 75% | 100% | Held 5: 25 / 50 / 75 / 100 | Median stop |
|---|---|---|---|---|---|---|---|
| SPY | 1,161 | 604 (52%) | 308 (27%) | 151 (13%) | 76 (7%) | 44 / 22 / 11 / 5% | 0.37 ATR |
| QQQ | 1,152 | 603 (52%) | 311 (27%) | 153 (13%) | 79 (7%) | 45 / 23 / 11 / 6% | 0.38 ATR |
| IWM | 1,150 | 599 (52%) | 316 (27%) | 138 (12%) | 60 (5%) | 44 / 23 / 10 / 5% | 0.34 ATR |

Last week, as the owner asked (from the same rows; sessions after 2026-11-10 are not in the
research copy and are added from production by the history job): 2026-11-09 all three went calls
and ran past all four quarters before the close (SPY 1.18 ATR, QQQ 1.23, IWM 1.21, no stop);
2026-11-10 SPY puts went 0.15 ATR and QQQ calls 0.07 ATR, short of the first quarter, neither
stopped.

Reading:

- The identity holds: a rung was hit exactly when the trade's excursion reached its distance, on
  8,022 of 8,022 rungs, touch and held.
- The curve beats the rung-number table clearly. ATR beats stop distances by about 0.011 Brier
  under every window.
- About half of all trades reach the first quarter, a quarter reach the second, one in eight the
  third and one in fifteen to twenty the fourth, on all three tickers.
- Moves were smaller in 2024 to 2026 than in 2022 to 2023, so full-history counts read a few points
  high on recent days. The window is a policy edit.

Commands (bars and the ladder file as above):

```bash
LAB=/mnt/project-files/stocks-scorecard/research
cd $LAB/rung_hits
python3 -I rung_hits.py $LAB/combine/ladder6_all.csv rung_rows.csv   # 3,463 trades, 8,022 rungs
python3 -I report.py rung_rows.csv 3463                             # Tables 1 and 2
python3 -I curve.py rung_rows.csv rung_rows_trades.csv              # identity, Tables 3 and 4
python3 -I walk.py rung_rows.csv rung_rows_trades.csv               # Table 5
cd $LAB/quarter_lastweek
python3 -I unit.py $LAB/rung_hits                                   # Table 6
python3 -I hist.py                                                  # Table 7, last week
```

sha256 prefixes: rung_hits.py 149914b3, report.py a8f01838, curve.py 78c67ea1, walk.py a853de95,
unit.py 5d86c7a8, hist.py 113d28cf, ladder6_all.csv 09c0d177, rung_rows.csv 20d8e15b,
rung_rows_trades.csv 148e8dff.

## Expected effect

Each side with a plan prints one more line (the trades counted), and each target line ends with how
far it sits from the trigger in ATR and how many of that ticker's trades got that far before the
stop. Near targets read high, the far ones single digits. Nothing the brief trades, alerts or scores
changes.

## Capacity and cost

- **Volume:** about 3,500 history rows once per entry version (one per trade, 2022-01-03 on), then
  at most 3 rows per session; each brief run reads about 3,500 excursions.
- **Velocity:** one new read per brief run; one upsert per resolved ticker-day; the history run reads
  one ticker-month of bars per query (177 queries for three tickers since 2022-01) plus the inputs
  of the basis rebuild per session.
- **Wall-clock:** measured locally at about 0.5 s per session basis rebuild and 13 s per ticker for
  bars and scoring; the job's timeout is set at four times the measured run or more.
- **Cost:** no new scheduled job, schedule or resource; the history run is one manual job.

## Source identity and close-out

`lib/`, `gcp/` and `tests/` are inside SITE's watched scope. DASHBOARD-01 (the brief) shows the new
counts. Only the `(FEAT-STRAT-001, DASHBOARD-01)` row of the Implementation-source notes table may
describe this implementation, as backend source and local tests only. Every other SITE byte stays
unchanged.

After the merge, separately and never as a pre-merge box: confirm the apply-schema build created the
table and the one policy row (record both); on the owner's yes, the deploy entry and the deploy; on a
second yes, run the history job and record the rows per ticker; confirm the next live brief prints
the counts; mark r1 `superseded` in the change that sets this one `approved` (done in this change);
and complete the DOC close-out as the product-delivery skill prescribes.

## Risks

- **Counts are history, not a forecast.** Recent moves were smaller; the window is a policy edit.
- **Distance is measured from the trigger, the Experiment from the fill.** They are the same price
  on every trade filled at the trigger; the implementation PR reports how many differ (1 of 1,188
  where the trigger is known).
- **An entry version that moves triggers or stops restarts the counts** until the history job is run
  for it.
- **A rule change mislabelled as sharing the entry rule** would mix trades with different stops.
  `entry_rule_version` is the only place that says so, and the quarter change pins that its
  trigger and stop equal the level rule's on stored bases.
- **Deploy order.** Design 6.

## Found while reading (not changed by this spec)

- `resolve_plan`'s plan hit timestamps (`*_plan_t1_hit_ts` to `t3`) are first touches from the cross
  bar itself, so a target touched only on the fill bar is stamped as hit although no exit there is
  possible. Anyone reading hit rates from those columns gets numbers above this spec's.
