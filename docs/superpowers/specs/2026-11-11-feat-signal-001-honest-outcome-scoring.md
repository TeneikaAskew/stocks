---
feat_id: FEAT-SIGNAL-001
req_ids: [REQ-SIGNAL-001, REQ-PLAYBOOK-001, REQ-DATA-002, REQ-DATA-003, REQ-VALID-001]
issues: []
canvases: []
site_source_notes: [CHARTS-06]
done_when:
  - "tests/lib/test_trading_analysis_realized_outcome.py passes: on a synthetic one-minute frame with tz-aware UTC Time, generate_technical_signals gives every signal realized_return_pct and realized_rule 'next-open-20m-1c-v1'; a call fired on the 10:00 ET bar whose next 20 closes include one above its close, but whose exit open (the open 20 bars after the 10:01 entry open) is below that entry open, has return_pct above 0 and realized_return_pct below 0, equal to (exit open - entry open - 0.01) / entry open * 100; a put is the mirror; a signal on a bar before 09:30 ET or after 15:34 ET, or whose entry or exit bar falls outside the same session's regular hours (a 13:00 half-day close from lib.eastern_time.session_close included), has realized_return_pct NULL; return_pct, best_return and the return_Nmin columns are unchanged from origin/main on the same frame; the realized cases fail on origin/main"
  - "tests/lib/test_trading_analysis_feature_ranking.py passes: analyze_feature_importance ranks no column whose name starts with exit_, realized_, return_ or best_, and no duration_minutes, even when exit_rsi is a copy of the target; its printed model score is labelled out of sample and is computed on the chronologically last 20% of signals by entry_time after fitting on the first 80%; the summary print no longer calls the best-of-20 share profitable (it prints 'moved in favour within 20 bars' and, beside it, the realized win share); the exit_rsi case fails on origin/main"
  - "tests/api/test_platform_api.py passes: GET /api/signals/{ticker}/similar serves pct_profitable as the share of realized_return_pct > 0 among matched rows with a realized value, realized_count as that number of rows, and pct_moved_in_favor as the origin/main share of return_pct > 0; a match set whose rows all have realized_return_pct NULL serves pct_profitable null and realized_count 0, never 0.0; the statistics are still one query; the realized cases fail on origin/main; tests/api/test_openapi_snapshot.py passes on the regenerated platform/api/openapi.json"
  - "tests/gcp/test_premarket_playbook_resolver.py passes: a call whose first RTH bar opens at or above the trigger is entry_status gap_through with fill_price, exit_reason, eod_pnl_pct and eod_pnl_dollar None while trigger_hit_ts is still that bar; a later bar that opens above the trigger after bars below it fills at its own open; a target touched on the fill bar is not hit for the exit (T1 counts only from the next bar); T1 then T2 then the stop realizes at T1 (all out at the first exit); the stop and T1 on the same later bar realize at the stop; a stop touched on the fill bar realizes at the stop; a target at or behind the fill is skipped; puts are the mirror; eod_pnl_pct is measured from fill_price; every *_hit_ts, mfe_pct, mae_pct and reversal_after_trigger expectation that exists on origin/main is unchanged; test_call_hits_all_targets_realized_at_t3 and test_call_t2_then_stop_realizes_at_t2_not_stop now expect T1, a recorded change of rule; the gap-through, later-gap, fill-bar-target and T1-then-T2 cases fail on origin/main"
  - "gcp/schema.sql adds, with ADD COLUMN IF NOT EXISTS and no default, historical_signals.realized_return_pct and realized_rule, and premarket_analysis calls_ and puts_ entry_status, fill_price and exit_reason plus outcome_rule; the comments on return_pct and on calls_t1_hit_ts and calls_eod_pnl_pct state the rules of this spec; scripts/run_historical_signals.py and gcp/historical_signals.py carry the two new historical_signals columns, and a test in tests/gcp/test_historical_signals.py shows both reach the INSERT column list"
  - "scripts/analysis/honest_scoring_experiment.py, run as this spec's Experiment section states, reproduces both Experiment tables to the digit, with the spec-rule rows of the resolver table produced by the implemented resolve_leg, and the implementation PR body carries both tables"
  - "Source identity (CHARTS-06): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-SIGNAL-001, CHARTS-06) note row carries that source_identity_sha256"
  - "The FEAT-SIGNAL-001 catalog record, the FEAT-PLAYBOOK-001 record's Next action and the PR traceability entry are updated, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: null
---

# Trading outcomes are scored on exits that could have been traded

## Authority

The owner asked on 2026-11-11 for a fix to how trading outcomes are scored so that wins are not
over-counted, after the research lanes
(indicators, example_days, gappers_events, triggers_levels) found the flaws below. This spec is written
by a FEAT-SIGNAL-001 delivery lane and is not self-approved: it takes effect only when the owner merges
the spec-only PR that adds it, and that merge is the approval its `status` records. It also changes the
playbook resolver, whose table belongs to FEAT-PLAYBOOK-001; that part is listed under this FEAT-ID so
one implementation PR fixes both scorers against one rule.

## Problem

Two production scorers credit results no trader could have had. Line numbers are origin/main 7322f236;
`lib/trading_analysis.py` and `platform/api/routers/signals.py` are unchanged since 300b40df, and
`resolve_leg` in the resolver is unchanged since 4c34df02, the commits the research lanes read.

### 1. `pct_profitable` (FEAT-SIGNAL-001)

`MarketAnalyzer.generate_technical_signals` (`lib/trading_analysis.py:784`) writes
`historical_signals` through `scripts/run_historical_signals.py`. For every signal:

- **Best case, not an exit.** `return_pct` is the best close of the next 20 rows: the max for a call, the
  min for a put (`:968-979`). That is a maximum favourable excursion. `gcp/schema.sql:2328` already
  calls it "20-min MFE" and the API averages it as `avg_mfe_pct` (`platform/api/routers/signals.py:559`),
  but six lines later the share of rows with `return_pct > 0` is served as `pct_profitable` (`:565`,
  returned at `:594`), and the offline run prints the same share as "Profitable signals"
  (`lib/trading_analysis.py:1605`, per window at `:1614`). Any signal is "profitable" whenever one of 20
  closes is better: about 85% for every ticker. The `best_return` over seven windows (`:942-965`) and
  the `return_Nmin` columns are best cases too.
- **Unfillable entry.** The entry price is the signal bar's own close (`:976`, `:984`); the signal is
  only known once that bar has closed, so the earliest fill is the next bar's open.
- **Hours.** The window counts rows (`iloc[idx+1:idx+1+lookahead]`, `:950`, `:970`) over a frame that
  includes 04:00 to 20:00 (`load_parquet_data(market_hours_only=False)`, `:52`), so windows run across
  the close, overnight and weekends. 58 to 63% of the voter's signals fire outside 09:30 to 15:34 ET.
- **Future data in the feature ranking.** `exit_time`, `exit_price`, `exit_rsi`, `exit_vwap` and
  `exit_obv` are read at the best future bar and saved on the signal row (`:1073-1077`; stored in
  `historical_signals.extra` by the `exit_` prefix in `scripts/run_historical_signals.py:83`).
  `analyze_feature_importance` excludes only `exit_time` and `exit_price` (`:1122-1126`), so
  `exit_rsi`, `exit_vwap` and `exit_obv` are ranked as predictors of the outcome they were read at.
- **In-sample score.** The model score is printed on the rows it was fitted on
  (`rf.score(X_scaled, y)`, `:1250`).
- **No cost**, and **every bar is its own signal** (the `:816` loop keeps no position state, so
  back-to-back fires overlap).
- **Look-ahead features.** The opening range is mapped back to every row of the day, premarket and the
  first minutes included (`:550-556`); minute-of-day relative volume divides by an average over the
  whole file, later sessions included (`:283-287`; the exclude-current variant at `:290-305` removes
  only today); VWAP is anchored at 04:00 (`:256-263`) and prior-day levels use all hours (`:379-390`).

### 2. The playbook resolver (FEAT-PLAYBOOK-001 table)

`resolve_leg` (`gcp/premarket_playbook_resolver.py:208`) writes `premarket_analysis` outcome columns
every weekday at 21:15 ET:

- **Fills at a price that never traded.** The trigger counts as hit when a bar's high (low) reaches it
  (`:238`, `:242`) and P&L is always measured from the trigger price (`:333`), even when that bar
  opened beyond the trigger, so a gap through the trigger is filled at the level it jumped over.
- **Targets on the trigger bar itself.** The walk starts at the trigger bar (`after =
  bars.loc[trigger_idx:]`, `:251`; targets at `:281`), so an open already past T1 books the whole
  trigger-to-T1 distance.
- **Best target reached.** The realized price is the last target hit, T3 over T2 over T1 (`:318-327`),
  unless the stop came at or before T1. A stop between T1 and a later target is ignored, and a T2 that
  is reached when T3 is not is booked although nobody knew in advance to exit there. The schema comment
  on `calls_eod_pnl_pct` (`gcp/schema.sql:1928`) says "at first stop/target/EOD close"; the code does
  not do that.

### 3. The offline scorer (not repo code)

`stocks-scorecard/week_summary.py` `trade()` (in the project files, not this repo) fills at
`max(trigger, open)`, which is right, but checks T1 from the fill bar, so an open already past T1 is
booked as a T1 win of `abs(t1 - fill) / risk`: 78 of 1,610 brief fills, +14.48 R, across 2025-03-03
to 2026-11-10. It is aligned to this rule as a close-out step outside the repo.

## Non-goals

- No change to which signals fire. The look-ahead features (opening range, relative volume, VWAP anchor,
  prior-day levels from all hours) change the voter's inputs and therefore MODEL-MOM-001's signals; they
  are listed above so the record is complete and get their own spec.
- No change to the resolver's touch timestamps (`*_trigger_hit_ts`, `*_t1_hit_ts` to `*_t3_hit_ts`,
  `*_stop_hit_ts`), `*_mfe_pct`, `*_mae_pct` or `*_reversal_after_trigger`. They describe where price
  went, and DASHBOARD-21's reach rates (`lib/movement_statement.py:286`) read them as "how often price
  gets here", which this spec does not change.
- No change to the brief's triggers, stops, targets or the exit plan the brief publishes. Farther or
  scaled targets (the triggers_levels lane's main finding) are a separate decision; the Experiment shows
  them for information only.
- No backfill. Legacy `historical_signals` rows keep `realized_return_pct` NULL and resolved
  `premarket_analysis` rows keep their values with `outcome_rule` NULL; recomputing either is a separate
  owner-authorized run. No cost model in the resolver (it books none today).
- No frontend change in this repo. The solyra Similar setups card (CHARTS-06) reads the new fields in its
  own PR.
- No change to `week_summary.py` inside this repo; it is not in the repo.

## Approaches considered

1. Relabel `pct_profitable` only. Rejected: the number still reads as a win rate and nothing measures a
   real exit.
2. Chosen: score a fixed, pre-declared exit beside the best case, serve the real-exit share under the old
   name and the old share under an honest one, and give the resolver one causal fill and exit rule.
3. For a trigger the session opens beyond: fill at the open, as `week_summary.py` does. Rejected for the
   safer rule, no entry. The brief's trigger means "take it when price crosses"; at a gap there is no
   cross. Filling at the open was the worst entry in every window the triggers_levels lane tested
   (versus requiring a cross, with that lane's 0.25 / 0.5 x ATR stop and target: -18.1 R primary,
   -13.7 R holdout, -221.4 R over 2016-03 to 2025-02), and a
   one-minute bar cannot say what price the open auction gave. No entry can only remove trades the plan
   never called; it can never add a win.
4. For the resolver's exit: hold for T3, or a third at each target. Not chosen here: both change the
   exit the brief plans and belong with the target-spacing decision. All out at the first of stop or T1
   is the contract the schema comment already states and the rule every research comparison used, so
   stored outcomes become comparable to those studies.

## Design

### `lib/trading_analysis.py`

- A pure helper `realized_outcome(bars, signal_idx, direction, hold=20, cost=0.01)` (vectorised, as in
  the research's `realized_outcomes`, rule `next-open-20m-1c-v1`):
  - scoreable only when the signal bar is inside 09:30 to 15:34 ET of a session, with ET from
    `lib.eastern_time` (the producer's `Time` is tz-aware UTC), and the entry bar and the exit bar are in
    the same session before `lib.eastern_time.session_close` of that day;
  - entry at the open of the bar after the signal bar; exit at the open `hold` bars after the entry;
  - `realized_return_pct = direction * (exit_open - entry_open) - cost`, over `entry_open`, times 100;
  - not scoreable gives NULL, never 0.
- `generate_technical_signals` adds `realized_return_pct` and `realized_rule` to each signal row.
  `return_pct`, `best_return`, `best_window_minutes`, `duration_minutes` and `return_Nmin` keep their
  values and stay what they are: best-case excursions.
- `analyze_feature_importance` excludes every column starting `exit_`, `realized_`, `return_` or
  `best_`, and `duration_minutes`; it fits on the first 80% of signals by `entry_time` and prints the
  score on the last 20% as out of sample. The `exit_*` values stay in `extra` as a description of the
  best-case peak; they are never features.
- The run summary prints "moved in favour within 20 bars" for the old share and the realized win share
  beside it.

### `historical_signals` and the API

- `gcp/schema.sql`: `historical_signals.realized_return_pct DOUBLE PRECISION` and
  `realized_rule VARCHAR(32)`, nullable, no default (metadata-only `ALTER` in PostgreSQL); the
  `return_pct` comment says best close of the next 20 rows, not a realized return.
- `gcp/historical_signals.COLS` and `scripts/run_historical_signals.py` carry both columns.
- `/api/signals/{ticker}/similar`, same one query:
  - `pct_profitable` = share of `realized_return_pct > 0` among matched rows where it is not NULL;
  - `realized_count` = that number of rows;
  - `pct_moved_in_favor` = the origin/main expression (share of `return_pct > 0`), the old number under
    an honest name;
  - `avg_mfe_pct` and its percentiles are unchanged; the `avg_return_5min` / `avg_return_20min` field
    descriptions say they are best closes within the window.
  `SimilarStats` gains the two fields; `platform/api/openapi.json` is regenerated with
  `scripts/export_openapi.py`.

### `gcp/premarket_playbook_resolver.py`, rule `cross-fill-t1-v1`

Per leg, on the session's RTH bars:

```
first bar opens at or beyond the trigger           -> entry_status gap_through, no fill, no pnl
no bar reaches the trigger                         -> entry_status not_triggered
first bar i that reaches the trigger:
    fill = trigger                if bar i opened on the near side
    fill = open of bar i          if bar i opened beyond (a gap between two bars after the open)
stop missing or on the wrong side of the fill      -> entry_status invalid_stop, no pnl
targets = T1..T3 strictly beyond the fill; T1 = the first of them
walk bars from i:
    stop touched (bar i included)                  -> exit at the stop, or at that bar's open if a later
                                                      bar opened beyond the stop; stop wins any tie
    T1 touched on a bar after i                    -> exit at T1 (all out)
otherwise                                          -> exit at the last RTH close
eod_pnl_pct = direction * (exit - fill) / fill * 100; eod_pnl_dollar as today
```

New columns per side: `entry_status`, `fill_price`, `exit_reason` (`stop`, `t1`, `close`), and one
`outcome_rule` per row. Touch timestamps, excursions and the reversal flag are computed exactly as on
origin/main. The schema comments are updated to these rules.

### `week_summary.py` (outside the repo)

After the merge, its `trade()` gets the same rule (no entry when the open is past the trigger, T1 only
from the bar after the fill), so offline weekly scorecards and the resolver agree.

## Experiment

Hypothesis: the scorers over-count wins, and a causal exit removes the excess without changing which
signals or legs exist.

Data (read only, not in the repo): Alpha Vantage one-minute bars, extended hours,
`/mnt/project-files/stocks-scorecard/inputs/bars_raw/{SPY,QQQ,IWM}_1min_YYYY-MM.csv` (2025-03 to
2026-11-10; 409,173, 409,049 and 382,898 rows); daily bars
`/mnt/project-files/strat-verify/ftfc-replay/raw/{T}_daily_adjusted.csv`; the production voter's own
signals from origin/main's `generate_technical_signals`,
`/mnt/project-files/stocks-scorecard/research/fable_lab/indicators/work/{T}_voter_signals.parquet`;
and 1,236 ticker-days of 08:30 brief rows from replays of main with their 390 RTH bars,
`/mnt/project-files/stocks-scorecard/research/fable_lab/triggers_levels/work/sessions.pkl`
(built from `inputs/brief_rows.json` by that lane's `code/build_sessions.py`). Windows: holdout
2025-03-03 to 2026-04-30, primary 2026-05-01 to 2026-11-10.

Commands (Python 3 with pandas 2.3, numpy, pyarrow):

```
git -C /home/claude/stocks fetch origin main
git -C /home/claude/stocks worktree add --detach /tmp/wt-scoring origin/main
X=/mnt/project-files/stocks-scorecard/research/fable_lab
# Table A, read-only recheck of the old, real-exit and bracket shares (about 3 minutes)
PYTHONDONTWRITEBYTECODE=1 python3 -I $X/scoring_spec/verify_pct.py
# Table A in full, weekly and per window (rewrites the lab's CSVs; voter_run about 4 to 10 min per ticker)
cd $X/indicators && export STOCKS_WT=/tmp/wt-scoring
for T in SPY QQQ IWM; do python3 -I code/voter_run.py $T; done
python3 -I code/pct_profitable.py        # pct_profitable_summary.csv, pct_profitable_weekly.csv
# Table B, resolve_leg imported unchanged from the checkout (about 1 minute)
PYTHONDONTWRITEBYTECODE=1 python3 -I $X/scoring_spec/resolver_exp.py /tmp/wt-scoring \
  $X/triggers_levels/work/sessions.pkl /tmp/resolver_legs.csv
```

`verify_pct.py` (sha256 96368194c49f80d540bed05ebf839edfeda2ef2cb3f3643cdc9138a6a2257ec5) and
`resolver_exp.py` (sha256 57421a85560fa65c495593104a892da9aefe3dcfb081cf4045e33173bab437fe) are in
`$X/scoring_spec/` with their outputs (`verify_pct.out`, `resolver_exp.out`, `resolver_legs.csv`, one row
per leg). The implementation PR ports both into `scripts/analysis/honest_scoring_experiment.py`.

### Table A: `pct_profitable`, the voter's own signals, 2025-03-03 to 2026-11-10

| Measure | SPY | QQQ | IWM |
|---|---|---|---|
| Signals, all hours | 43,317 | 43,634 | 38,118 |
| Old `pct_profitable` (served today) | 84.5% | 85.4% | 84.2% |
| Regular hours only, still best of 20 closes | 86.1% | 86.4% | 86.4% |
| + the close 20 minutes later instead of the best close | 49.7% | 50.1% | 49.8% |
| **Real exit (this spec): next-bar open, open 20 bars later, 1 cent** | **49.2%** | **49.6%** | **49.1%** |
| Signals scoreable under the real exit | 16,256 | 16,268 | 15,871 |
| Same, one position at a time (4,648 / 4,676 / 4,613 trades) | 49.7% | 50.0% | 49.7% |
| Average net result, real exit (bps per signal) | +0.02 | +0.28 | -0.27 |
| Bracket of 0.15 x prior-day ATR14, information only | 49.2% | 49.2% | 48.9% |
| Weekly range, old (89 weeks) | 79.6 to 88.4% | 81.2 to 89.0% | 77.9 to 88.2% |
| Weekly range, real exit | 34.4 to 64.3% | 38.0 to 64.4% | 30.8 to 61.7% |
| Holdout: old / real exit | 84.7% / 49.3% | 85.4% / 50.0% | 84.5% / 48.7% |
| Primary: old / real exit | 84.1% / 48.9% | 85.2% / 48.8% | 83.6% / 49.9% |

The old share, the real-exit share and the bracket share were recomputed by `verify_pct.py` from the
voter parquet and the bars (0.8449 / 0.4918 / 0.4916, 0.8535 / 0.4961 / 0.4915, 0.842 / 0.4908 /
0.4891) and match `pct_profitable_summary.csv`. Fixing the hours alone leaves 86%; the whole gap is the
best-of-20 exit.

### Table B: the brief's playbook legs scored three ways, 1,236 ticker-days, both sides

R = price result over |entry - stop|, no cost (the resolver books none).

| Rule | Window | Fills | Wins | Total R |
|---|---|---|---|---|
| origin/main `resolve_leg` | holdout | 1,136 | 61.2% | +274.70 |
| origin/main `resolve_leg` | primary | 474 | 61.4% | +94.50 |
| origin/main `resolve_leg` | both | 1,610 | 61.2% | +369.20 |
| of which the session opened past the trigger | both | 299 | | +165.62 |
| of which a later target was booked after the stop | both | 8 | | +10.74 |
| `week_summary.trade` | holdout | 1,136 | 60.6% | -50.89 |
| `week_summary.trade` | primary | 474 | 60.3% | -2.81 |
| `week_summary.trade` | both | 1,610 | 60.5% | -53.70 |
| of which T1 booked with the open already past T1 | holdout / primary / both | 57 / 21 / 78 | | +10.88 / +3.60 / +14.48 |
| **this spec** | holdout | 922 (214 gap_through) | 58.1% | -51.93 |
| **this spec** | primary | 389 (85 gap_through) | 58.9% | -2.25 |
| **this spec** | both | 1,311 (299 gap_through) | 58.4% | -54.18 |

This spec's exits over both windows: T1 614, stop 395, close 302. On the 1,311 legs that did not open
past the trigger, origin/main's resolver books +203.59 R where `week_summary.trade` books -51.47 R: the
difference is the best-target-reached exit. For information, the same entry and ordering held for T3
gives -12.80 R (43.2% wins), and a third at each of T1, T2 and T3 gives -32.50 R (46.4% wins); neither
is chosen here.

The triggers_levels lane measured the same inflation over a longer window with 1 cent a side and one
trade per ticker-day, both sides: the `week_summary` rule ("as scored before") against the no-gap-through
baseline gives +29.2 R against -88.7 R over 2016-03-01 to 2025-02-28 (+117.9 R of credit), +13.0 against
+4.7 primary and -33.0 against -36.2 holdout.

Reading: the hypothesis holds. `pct_profitable` reads 84 to 85% where a real exit reads 49 to 50% on
every ticker and window, and the resolver turns a -54 R record into +369 R through gap-through fills at
the trigger and a best-target exit. The real-exit numbers are near a coin flip; that is the finding, not
a defect of the fix.

## Expected effect

- `/similar` `pct_profitable` drops from about 85% to about 49% for matches with realized rows; for
  matches with only legacy rows it is null with `realized_count` 0 until new rows accumulate or an
  authorized backfill runs. `pct_moved_in_favor` carries the old number.
- `premarket_analysis` rows resolved after the deploy carry `outcome_rule` `cross-fill-t1-v1`, no P&L on
  gap-through legs, P&L from the real fill, and T1 as the only target exit. Touch timestamps and the
  movement-statement reach rates are unchanged.

## Capacity and cost

- **Volume:** `historical_signals` gains two nullable columns on about 1.7 million rows (1,708,932 at
  the 2026-09-14 audit noted in `gcp/historical_signals.py`; metadata-only
  `ALTER`, no rewrite); `premarket_analysis` gains seven nullable columns. New rows add 8 to 40 bytes.
- **Velocity:** the realized outcome is two array lookups per signal inside the producer's existing pass;
  `/similar` keeps one statistics query with two more aggregates; the resolver keeps one walk per leg.
- **Wall-clock:** the producer's run is dominated by the voter's row loop (minutes per ticker); the added
  vectorised step is under a second per ticker. API and resolver change by microseconds per row.
- **Cost:** $0; no new job, schedule or resource.

## Source identity and close-out

`lib/`, `gcp/`, `scripts/`, `platform/api` and `tests/` are inside SITE's watched scope. CHARTS-06 (the
Similar setups card) shows `/similar`'s `pct_profitable`, which this changes. Only the
`(FEAT-SIGNAL-001, CHARTS-06)` row of the Implementation-source notes table may describe this
implementation, as backend source and local tests only. DASHBOARD-21 reads only the unchanged touch
timestamps. Every other SITE byte stays unchanged.

After the merge, separately and never as a pre-merge box: verify main's source and body identity in a
fresh clone; complete the DOC main and staging close-out with real evidence (the schema columns exist in
Cloud SQL, the next `historical-signals-watchlist` run writes `realized_return_pct`, the next
`premarket-playbook-resolver` run writes `outcome_rule`); align `stocks-scorecard/week_summary.py` to
the same rule; retire the sidecar as the product-delivery skill prescribes; and set the plan to
`status: done` on a `docs/` branch.

## Risks

- **The Similar card shows null or a lower number.** Correct, but a visible change; the solyra card must
  show `realized_count` and the unavailable state (CHARTS-06, its own PR).
- **Mixed history.** Old and new resolver rows differ in meaning; any reader of `eod_pnl_pct` must
  filter on `outcome_rule`. No in-repo reader exists today (searched `lib/`, `gcp/`, `platform/`,
  `scripts/`); solyra was not searched from this session.
- **One-minute bars.** The fill bar's order of prints is unknown. The rule takes the stop and never the
  target on that bar; against `week_summary`'s rule on the same 1,311 legs that costs 2.71 R
  (-54.18 R against -51.47 R).
- **Research inputs differ from production.** The brief rows are 08:30 replays from before per-ticker
  level parameters (#1784) and the bars are Alpha Vantage history, not `market_data_intraday`; the
  scoring rule, not the levels, is what Table B compares. Lab-reported figures not rechecked here: the
  earlier study's exit_rsi ranking first in 217 of 231 weekly reruns and the printed in-sample R2 of
  0.64 to 0.69.
- **The docs audit reads solyra's issues**; a session without solyra access cannot run it.
