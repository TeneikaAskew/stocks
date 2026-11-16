---
feat_id: FEAT-STRAT-001
req_ids: [REQ-PLAYBOOK-001, REQ-DATA-001, REQ-REL-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "Policy: gcp/schema.sql seeds one new level_param_policy row target_reach_rate (method_id plan_excursion_share, lookback_sessions NULL, min_sample 30, effective 2015-01-02, extra {\"since\": \"2022-01-03\", \"measure\": \"touch\"}) with ON CONFLICT DO NOTHING; no other level_param_policy row changes; lib/strat_levels.py names the key once (TARGET_REACH_RATE_KEY) in POLICY_WIDE_KEYS, and policy_wide_param gives it status ok with value equal to min_sample when min_sample is a positive integer, lookback_sessions is NULL or a positive integer, since is an ISO date and measure is touch or held_5m, and input_unavailable otherwise; a test in tests/lib/test_level_params_loader.py loads the seeded policy from gcp/schema.sql and asserts status ok and value 30, and each unusable field gives input_unavailable"
  - "Table: gcp/schema.sql creates plan_excursions (ticker, session_date, rule_version, side, trigger_price, stop_price, fill_price, fill_ts, stop_ts, excursion_r, excursion_held5_r, source, resolver_version, written_at) with PRIMARY KEY (ticker, session_date, rule_version), CREATE TABLE IF NOT EXISTS, and source limited to resolver or history by a CHECK; tests/gcp/test_schema_sql.py (or the file that already checks schema.sql) asserts the table, key and check"
  - "Excursion: a pure function in gcp/premarket_playbook_resolver.py, sharing resolve_plan's entry walk (no second copy of it), returns for one side on the session's bars cut at the exchange close: nothing unless the side is entered with a valid stop; otherwise the fill bar, the stop bar (the first bar from the fill bar on that touches the stop, or none), excursion_r as Design 3 defines it and excursion_held5_r likewise; tests/gcp/test_premarket_playbook_resolver.py pins hand-built sessions for calls and puts: a rung touched only on the fill bar is not reached, a bar touching the stop and a rung counts the stop first, no bar between the fill bar and the stop bar gives NULL for both, five closes beyond a level that end on the stop bar do not count as held, a cross bar that opened beyond the trigger is still measured from the trigger, and on every fixture a rung counts as reached exactly when the touch-based plan hit for that rung would be set by resolve_plan's exit walk"
  - "One trade per ticker-day: the function that picks the row takes both sides' results and returns the side whose fill bar is earlier; both sides filled on the same bar, or neither entered, gives no row; tests cover the four cases"
  - "Live writer: resolve_one upserts at most one plan_excursions row per resolved (analysis_date, ticker) with source resolver, the basis's rule_version and RESOLVER_VERSION, in the same transaction as the premarket_analysis update; re-resolving with force replaces it; a row whose basis has no rule_version writes nothing; RESOLVER_VERSION moves to 2026-11-16.v5; the existing outcome and plan columns are byte-identical to origin/main's on the existing resolver tests"
  - "History writer: gcp/backfill_plan_excursions.py (TICKERS, START, END; START defaults to the policy row's since) rebuilds each session's level basis through the same build the brief runs under BRIEF_AS_OF, without writing premarket_analysis or premarket_analysis_history, reads one ticker-month of market_data_intraday bars per query, scores with the Excursion function and upserts source history rows that never replace a source resolver row; a re-run over the same span writes the same rows; tests cover resume and the never-replace rule"
  - "Reader: lib/target_reach.py loads, in ONE query per brief run for all of the run's tickers, the excursions of rows with rule_version equal to LEVEL_RULE_VERSION, session_date before the brief's session and on or after since (or within the last lookback_sessions sessions when that is set), and gives per ticker the trade count, the first and last dates, and for any distance the share whose excursion (touch or held5 per the policy's measure) is at least that distance, NULL counting as reaching nothing; a failed query or a missing table raises and the brief prints the unavailable line of Design 5 for that ticker, never a rate; tests cover the window, the point-in-time cut, the measure switch and the NULL rule"
  - "Brief copy: tests/lib/test_strat_levels.py has a new golden on the IWM 2025-10-22 basis of Design 5 (stored in tests as a fixture) with a fixed reach table equal to the Experiment's 906 IWM trades before that date, giving the puts lines of Design 5 byte for byte; the thin line (fewer trades than min_sample) and the unavailable line are pinned; with no reach table passed (every caller but the brief) format_levels_for_brief's output equals origin/main's, so the existing D8 goldens are unchanged"
  - "Unchanged, each pinned by an existing test that passes on origin/main and on the implementation head: the trigger and stop rule, gate targets and the t1..t3 columns, the plan's targets, spacing, thirds, entry cutoff and gap edges, the ATR levels line, the signal monitor, the movement statement, persona plans and every premarket_analysis column the resolver writes today; LEVEL_RULE_VERSION does not change"
  - "Experiment through the production paths, before any production change: the implementation PR body shows the history writer run on a local copy built like this spec's Experiment (as-traded bars, 2022-01-03 to 2026-11-10, SPY 2025-04-09 and IWM 2026-06-26 left out) producing the same 3,463 trades (same ticker, date, side and stop) and, on every trade filled at the trigger, excursions within 1e-6 of this spec's rung_rows_trades.csv; the reach curve and the out-of-sample table of this spec reproduced from those rows; and the measured wall-clock per ticker, which sets the job's timeout at four times or more; a reproduction for the record, not a gate"
  - "Source identity (DASHBOARD-01): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-STRAT-001, DASHBOARD-01) note row carries that source_identity_sha256 with implementation and test prose for this PR"
  - "The FEAT-STRAT-001 catalog record and the PR traceability entry are updated; python3 scripts/gate/spec_gate.py --pr origin/main passes; the production table and policy row are created only after the owner's yes, by Design 6's statements, before the code that reads them is deployed, and the history run starts only after a separate yes, each recorded with its row counts"
status: approved
supersedes: null
---

# Each target in the brief shows how often price has reached it before the stop

## Authority

The owner asked on 2026-11-11 (UTC) for experiments on "did it hit the levels" (T1, T2, T3, held 5 or
more minutes), and on 2026-11-15 (UTC) said "Ok so I like this" to a brief that "shows the combined
ladder with each rung's hit rate, so you see how accurate every level is", with the exits still
following the 1832 plan's three rungs. This spec is that display. The Experiment below tests how the
rates should be worked out before anything is built.

Rulings still in force: values are never hard-coded and come from policy or per-ticker rows
(2026-11-08); a change is tested before it is swapped in; R and every distance here are the stock's
move measured in stop distances, never money, and comparisons are like for like; 1-minute bars are
as-traded and come only from the store the nightly fills (2026-11-13).

This spec is written by a FEAT-STRAT-001 delivery lane and is not self-approved: it takes effect only
when the owner merges the spec-only PR that adds it, and that merge is the approval its `status`
records. No implementation is written before that merge. Five choices are the owner's (Decisions);
the spec is written with the recommended pick for each, and a different pick is a one-line edit
before the merge.

## Problem

The brief prints the plan's three targets and, until #1832, printed the next three levels as T1 to T3.
It never says how often price has actually got to a target. The owner wants every rung of the
combined ladder (the current-rule targets plus the plan's targets) shown with its hit rate.

Hit rates by rung number mislead. Over 3,463 trades (2022-01-03 to 2026-11-10), the first rung of the
combined ladder was reached before the stop 52% of the time, but 75% when it was a current-rule target
close to the trigger and 25% when it was the plan's own T1 further out (Experiment, table 2). What
decides the rate is how far the rung is from the trigger in stop distances, not its number.

## Non-goals

- Exits. The plan's targets, spacing, thirds, cutoff and gap edges are unchanged. The rates describe
  reach; they do not pick targets. Whatever exit rule the owner settles on, the rates stay valid,
  because they are measured from the trigger and stop alone.
- Rating the ATR levels line (display only, #1951) or the NEXT LEVELS list.
- The movement statement's own reach rates and its feature flag.
- The signal monitor, Discord alerts and persona plans.
- Judging a level's quality. A rate says how often price got this far, not whether the level itself
  turned price.

## Decisions for the owner (recommended pick first)

1. **Rate by distance (recommended)** or by rung number. By distance every rung gets its own number
   from all of the ticker's trades. By rung number scored clearly worse out of sample (Brier 0.1919
   against 0.1537, lower is better) and lumps near and far rungs together.
2. **Touch (recommended)** or held 5 minutes. Touch is a bar reaching the rung, the same test the
   plan's exits and R use. Held 5 is five 1-minute closes at or beyond it; it reads up to 15 points
   lower, most on the nearest rungs. Both are stored, so switching later is a policy edit.
3. **Window: every trade since 2022-01-03 (recommended)** or the last 500 sessions. Scored day by
   day from earlier days only, the windows tie (Brier 0.1526 to 0.1536); full history gives about
   twice the trades per ticker.
4. **Per ticker (recommended)** or SPY, QQQ and IWM pooled. Per ticker follows the 2026-11-08 rule
   that values fit the ticker; out of sample the two tie (0.1537 against 0.1535). Calls and puts are
   pooled, because splitting them scored slightly worse (0.1544).
5. **Thin samples:** the trade count is always printed; with fewer than 30 trades in the window the
   brief prints that there are too few instead of a percent. 30 matches the movement statement's
   LOW_SAMPLE_THRESHOLD.

## Approaches considered

1. Chosen: a reach curve per ticker. Store, for every past trade, how far price went past the trigger
   before the stop. A rung's rate is the share of the ticker's trades that went at least that far.
2. A table of rates by rung number per ticker. Rejected: Brier 0.1919 out of sample, and rung 1 means
   different things on different days.
3. A table of rates by distance band (under 0.5, 0.5 to 1, ... stop distances). Close to the curve
   (0.1557) but coarse: two rungs in one band get the same rate, and thin bands need merging.
4. Read the resolver's plan hit columns. Rejected: they hold the three plan targets only, count a
   touch on the fill bar (Found while reading), and cover only days the resolver has
   scored under the current rule.

## Design

### 1. The policy row

`gcp/schema.sql` seeds, next to the gap-edge row:

```sql
('target_reach_rate', 'plan_excursion_share', NULL, NULL, 30, '{"since": "2022-01-03", "measure": "touch"}',
 '2015-01-02', 'trades a target hit rate is read from: since a date or the last lookback_sessions, touch or held_5m, at least min_sample'),
```

`policy_wide_param` reads it like the other policy-wide keys. `lookback_sessions` NULL means every
session from `since` on; a positive number means only the ticker's last that many sessions before the
brief's. `measure` names the stored column the rate is read from. A missing or unusable row gives
`input_unavailable`, and the brief prints the unavailable line, never a rate (CLAUDE.md 3.7).

### 2. The table

```sql
CREATE TABLE IF NOT EXISTS plan_excursions (
    ticker             VARCHAR(10)      NOT NULL,
    session_date       DATE             NOT NULL,
    rule_version       VARCHAR(40)      NOT NULL,
    side               VARCHAR(5)       NOT NULL CHECK (side IN ('calls', 'puts')),
    trigger_price      DOUBLE PRECISION NOT NULL,
    stop_price         DOUBLE PRECISION NOT NULL,
    fill_price         DOUBLE PRECISION NOT NULL,
    fill_ts            TIMESTAMPTZ      NOT NULL,
    stop_ts            TIMESTAMPTZ,
    excursion_r        DOUBLE PRECISION,
    excursion_held5_r  DOUBLE PRECISION,
    source             VARCHAR(10)      NOT NULL CHECK (source IN ('resolver', 'history')),
    resolver_version   VARCHAR(40)      NOT NULL,
    written_at         TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, session_date, rule_version)
);
```

One row per ticker-day that had a trade: the first side to fill. A day where both sides filled on the
same bar, or neither entered, has no row, as in the 1832 tests.

### 3. The excursion

On the session's regular-hours bars cut at the exchange close (13:00 ET on a half day), with the
entry walk `resolve_plan` already uses (opened through, no cross and late cross are not entries; the
fill is at the trigger, or at the open of a cross bar that opened beyond it):

- The fill bar is the first bar that reaches the trigger. The stop bar is the first bar from the fill
  bar on that touches the stop.
- `excursion_r` is the furthest the high (calls) or low (puts) went past the trigger on the bars after
  the fill bar and before the stop bar, divided by the trigger-to-stop distance. NULL when there is no
  such bar; NULL reaches no rung.
- `excursion_held5_r` is the same for the furthest price that five consecutive closes all stayed at or
  beyond, every one of them before the stop bar.

So a rung at distance d past the trigger is reached exactly when `excursion_r >= d`: a bar after the
fill bar touched it before any bar touched the stop, with a bar touching both counting the stop
first. That is the walk the plan's exits use. The Experiment checked this on all 8,022 rungs.

### 4. Who writes it

- **Every resolved day:** `resolve_one` writes the day's row after it scores the plans, in the same
  transaction, `source` resolver. `RESOLVER_VERSION` moves to `2026-11-16.v5`. Nothing else it writes
  changes.
- **History, once:** `gcp/backfill_plan_excursions.py` rebuilds each session's level basis the way the
  brief builds it under BRIEF_AS_OF (the path the Experiment's replay used), scores it with the same
  function on `market_data_intraday` bars, and writes `source` history rows only. It never touches
  premarket_analysis, and never replaces a resolver row. It runs per ticker, one month of bars per
  query, and resumes where it stopped.

### 5. What the brief will look like

The brief reads the rates in one query per run (Design 1's window, sessions before the brief's own,
current rule version only). Under each side's plan, after the Skipped line, it prints the combined
ladder: the current-rule targets and the plan's targets, one rung per cent, in order from the trigger,
up to six, each with its distance in stop distances and its rate. The plan's exits are marked.

IWM on 2025-10-22, puts side (trigger 245.66 PMK_L, stop 246.99 PDC, one stop distance 1.33), rated
from the 906 IWM trades from 2022-01-03 to 2025-10-21:

```
    Hit rates, IWM trades 2022-01-03 to 2025-10-21 that reached each price before the stop (906 trades):
      245.50 (PDL), 0.12 stop distances: 87%
      244.98 (PYH), 0.51 stop distances: 62%
      243.41 (PWC), 1.69 stop distances, plan T1: 22%
      241.96 (PMC), 2.78 stop distances, plan T2: 9%
      240.36 (PWL), 3.98 stop distances, plan T3: 4%
```

That day price reached the first four before the stop and missed 240.36 (low 240.77). With fewer
trades than the policy's minimum:

```
    Hit rates: too few IWM trades so far (12, at least 30 needed).
```

With the row or the table unusable: `    Hit rates unavailable (input_unavailable).` A side with no plan
prints no ladder. Every other line of the brief is unchanged.

### 6. Production order

After the owner's yes: create the table and insert the policy row, then deploy the resolver and the
brief. The brief prints "too few" until the history run fills the table; that run is its own yes. The
statements:

```sql
-- the CREATE TABLE of Design 2, then:
INSERT INTO level_param_policy (param_key, method_id, statistic_q, lookback_sessions, min_sample,
                                extra, effective_from, note)
VALUES ('target_reach_rate', 'plan_excursion_share', NULL, NULL, 30,
        '{"since": "2022-01-03", "measure": "touch"}', '2015-01-02',
        'trades a target hit rate is read from: since a date or the last lookback_sessions, touch or held_5m, at least min_sample')
ON CONFLICT (param_key, effective_from) DO NOTHING;
```

## Experiment

Hypothesis: a rung's chance of being reached before the stop is set by its distance from the trigger
in stop distances, so a per-ticker reach curve rates every rung better than a table by rung number.

Data (read only, not in the repo): the same 3,463 trades as the 1832 and gap-edge tests (SPY 1,161,
QQQ 1,152, IWM 1,150; 1,212 sessions from 2022-01-03 to 2026-11-10; one trade per ticker-day, the
first side to cross its trigger; a same-bar tie is no trade; SPY 2025-04-09 and IWM 2026-06-26 left
out), from the Nov 15 combined-ladder run, with the as-traded 1-minute bars in
`/mnt/project-files/stocks-scorecard/research/fable_lab/data/bars_1min/` (to 2025-02) and
`/mnt/project-files/stocks-scorecard/inputs/bars_raw/` (from 2025-03), half days cut at the exchange
close. Each rung of the combined ladder (8,022 rungs) is scored with `resolve_plan`'s rules.
Distances here are measured from the fill, which is the trigger except when the cross bar opened
beyond it.

Table 1, reproduction: the share of all 3,463 trades reaching combined-ladder rung 1 to 6 is 46.5%,
21.1%, 7.8%, 1.6%, 0.2%, 0.0%, as reported on 2026-11-15. Held 5 minutes: 39.3%, 18.1%, 6.8%, 1.3%,
0.1%, 0.0%.

Table 2, why the rung number misleads (rung 1 only):

| Rung 1 | Rungs | Reached before the stop |
|---|---|---|
| All trades with a rung 1 | 3,075 | 52.3% |
| A current-rule target only | 1,656 | 74.5% |
| Both a current-rule and a plan target | 1,354 | 24.9% |
| Under 0.5 stop distances past the fill | 1,397 | 78.3% |
| 0.5 to 1 | 612 | 47.2% |
| 1 to 1.5 | 357 | 35.9% |
| 1.5 to 2 | 218 | 24.3% |
| 2 to 3 | 246 | 11.8% |
| 3 or more | 245 | 6.5% |

Table 3, the reach curve per ticker (share of trades reaching at least d stop distances before the
stop, touch / held 5 minutes, all 1,212 sessions):

| Ticker | 0.25 | 0.5 | 1 | 1.5 | 2 | 3 | 4 |
|---|---|---|---|---|---|---|---|
| SPY | 77/65 | 60/51 | 36/30 | 23/19 | 15/12 | 6/5 | 3/2 |
| QQQ | 77/63 | 58/50 | 38/33 | 25/21 | 17/14 | 8/7 | 4/4 |
| IWM | 78/63 | 62/51 | 41/34 | 27/21 | 17/14 | 7/7 | 3/2 |

Table 4, out of sample: rates fitted on 2022-01-03 to 2024-06-28 (607 sessions), scored on
2024-07-01 to 2026-11-10 (579 sessions, 3,880 rungs). Brier score, lower is better:

| How the rate is worked out | Brier |
|---|---|
| One rate for every rung | 0.2213 |
| By rung number, per ticker | 0.1919 |
| By distance band, per ticker | 0.1557 |
| Reach curve, pooled | 0.1535 |
| Reach curve, per ticker | 0.1537 |
| Reach curve, per ticker and side | 0.1544 |

Table 5, window, walk-forward (each day rated only from earlier days, same 579 test sessions):
every session since 2022-01-03 0.1532; last 750 sessions 0.1528; last 500 0.1527; last 250 0.1526;
last 120 0.1536.

Reading:

- The identity holds: a rung was hit exactly when the trade's excursion reached its distance, on
  8,022 of 8,022 rungs, and for held 5 minutes on 8,022 of 8,022.
- The curve beats the rung-number table clearly and the band table slightly. Per ticker and pooled
  tie.
- Moves were smaller in the second half: on equal halves (606 sessions each) the curve reads 3 to 8
  points lower in the second half (IWM at 1 stop distance: 45% then 37%). So the fitted curve read
  high on the test half where it was near 50% (predicted 0.52, actual 0.41). The window choice barely
  changes this (Table 5).
- 44% of trades hit the stop before the close.

Commands (bars and the ladder file as above):

```bash
LAB=/mnt/project-files/stocks-scorecard/research
cd $LAB/rung_hits
python3 -I rung_hits.py $LAB/combine/ladder6_all.csv rung_rows.csv   # 3,463 trades, 8,022 rungs
python3 -I report.py rung_rows.csv 3463                             # Tables 1 and 2
python3 -I curve.py rung_rows.csv rung_rows_trades.csv              # identity, Tables 3 and 4
python3 -I walk.py rung_rows.csv rung_rows_trades.csv               # Table 5
```

sha256 prefixes: rung_hits.py 149914b3, report.py a8f01838, curve.py 78c67ea1, walk.py a853de95,
ladder6_all.csv 09c0d177, rung_rows.csv 20d8e15b, rung_rows_trades.csv 148e8dff.

## Expected effect

Each side with a plan prints three to six more lines: the combined ladder, each rung's distance in
stop distances and how often that ticker's trades got that far before the stop. Near rungs read high
(a rung under half a stop distance away, about 78%), the plan's T1 usually reads 20%
to 40%, and far rungs read single digits. Nothing the brief trades, alerts or scores changes.

## Capacity and cost

- **Volume:** about 3,500 history rows once (one per trade, 2022-01-03 on), then at most 3 rows per
  session; each brief run reads about 3,500 excursions (about 1,200 per ticker).
- **Velocity:** one new read per brief run; one upsert per resolved ticker-day; the history run reads
  one ticker-month of bars per query (177 queries for three tickers since 2022-01) plus the inputs of
  the basis rebuild per session.
- **Wall-clock:** the brief's read is one indexed query; the resolver adds one row write. The history
  run's time is set by the basis rebuild and is measured on the local copy in the implementation PR
  before any production run; its timeout is set at four times that or more.
- **Cost:** no new scheduled job, schedule or resource; the history run is one manual job.

## Source identity and close-out

`lib/`, `gcp/` and `tests/` are inside SITE's watched scope. DASHBOARD-01 (the brief) shows the new
lines. Only the `(FEAT-STRAT-001, DASHBOARD-01)` row of the Implementation-source notes table may
describe this implementation, as backend source and local tests only. Every other SITE byte stays
unchanged.

After the merge, separately and never as a pre-merge box: on the owner's yes, run Design 6's
statements and record the row counts, then deploy; on a second yes, run the history job and record
the rows per ticker; confirm the next live brief prints the ladder with the trade count; and complete
the DOC close-out as the product-delivery skill prescribes.

## Risks

- **Rates are history, not a forecast.** Moves were smaller in 2024 to 2026 than in 2022 to 2023, so
  full-history rates read a few points high on recent days. The window is a policy edit.
- **Distance is measured from the trigger, the Experiment from the fill.** They are the same price on
  every trade filled at the trigger; on the rest the cross bar opened beyond the trigger and the live
  brief cannot know the fill. The implementation PR reports how many trades differ.
- **A new level rule restarts the rates.** Only rows built under the current `LEVEL_RULE_VERSION` are
  read, so a rule change needs the history run again.
- **Deploy order.** The brief before the table or row prints the unavailable line; Design 6 puts them
  first.

## Found while reading (not changed by this spec)

- `resolve_plan`'s plan hit timestamps (`*_plan_t1_hit_ts` to `t3`) are first touches from the cross
  bar itself, so a target touched only on the fill bar is stamped as hit although no exit there is
  possible. Its docstring says so. Anyone reading hit rates from those columns gets numbers above
  this spec's.
