# Signal Gate Out-of-Sample Experiment Plan

**Status:** prerequisites failing (see §1). **Written:** 2026-09-25.
**Purpose:** find, per ticker and side, the entry thresholds, features and
exits that give the best out-of-sample expectancy net of costs, and prove
it on data never used for selection. §3 is a prompt to hand to an agent
(Codex or Claude) to run it.

This plan replaces the approach in the 2026-09-22 model-evaluation audit.
That audit sliced two weeks of delivered alerts and then "held out" three
sessions. It never tested a threshold the live gate had not already
applied, and its samples were too small to confirm or reject anything
(n=5 gives a 95% CI on win rate of roughly 0.5%..72%).

---

## 1. Parity check, run 2026-09-25 (prompt step 3, done first)

**Question:** does the canonical replay path reproduce what the live
monitor fired? If not, no historical experiment measures the signal
users actually receive.

**Method.** Three hermetic replays of the production `signal-monitor`
job (`REPLAY_TICKERS=<t>`, `REPLAY_START=2026-09-18`,
`REPLAY_END=2026-09-25`, `--args=--json`, no `--persist`):

| Execution | Ticker | Bars | Replay fires | Live fires | Wall-clock |
|---|---|---|---|---|---|
| `signal-monitor-47x5l` | SPY | 1950 | 25 (10 CALL / 15 PUT) | 25 (11 / 14) | 117 s |
| `signal-monitor-vl5ph` | QQQ | 1950 | 25 (CALL) | 25 (CALL) | 111 s |
| `signal-monitor-86r76` | IWM | 1950 | 20 (CALL) | 15 (CALL) | 111 s |

Live fires come from `signal_alerts` (`run_kind='live'`, query
`db-query-jp6v6`). A replay fire matches a live fire when ticker and
direction agree and live's poll minute equals the replay bar + 1 minute.
That offset was chosen by measurement: of offsets -1..+3 it gives the
most matches (39 at +1, 30 at 0, 24 at +2).

**Result, all ten sessions:** 39 of 65 live fires reproduced at the same
minute, 24 with identical base and total score.

### Finding A: the stored history mixes two timestamp conventions, and replay reads them wrong

On 2026-09-24, every live QQQ price was 36..64 bp below the stored bar
for the same minute. The QQQ daily bar (open 735.289, low 734.62) agrees
with live, not with the stored bars (stored RTH low 737.76, plus a
772.58 high the daily high of 742.66 rules out). Reading the same rows
by their raw clock label instead of as UTC instants lines them up with
live:

| Live fire (ET) | Live price | Stored, raw label read as ET | Stored, read as UTC instant |
|---|---|---|---|
| QQQ 10:13 | 736.48 | 736.50 (+0.3 bp) | 739.16 (+36.4 bp) |
| QQQ 10:54 | 736.48 | 736.57 (+1.2 bp) | 741.22 (+64.3 bp) |
| SPY 09:34 | 764.645 | 764.67 (+0.3 bp) | 767.13 (+32.5 bp) |

QQQ's raw "09:30" open equals the daily open exactly. So those sessions
are ET wall-clock stored as UTC (the CLAUDE.md §3.9 warning), and the
replay (`resolve_window` compares aware ET bounds as instants) scored
bars from four hours later in the day.

**How much history this affects.** `gcp/queries/classify_intraday_ts_convention.sql`
classifies each session by where the opening-volume spike sits (true
instant vs raw label). No reference table is needed. It was validated
against the 09-24 price evidence above. `market_data_daily` can't settle
the question: its 2024 closes differ from intraday by about 190 bp under
both readings, consistent with dividend adjustment. The ratio is bimodal
(1,870 sessions < 0.2, 34 > 1.5, 71 in between), and a Python and a SQL
implementation agree on 2,009 of 2,009 sessions
(`db-query-mzf66`, 2024-01-01..2026-09-25):

| Ticker | true-UTC | ET-as-UTC | mixed (both writers) | no open bars |
|---|---|---|---|---|
| SPY | 625 | 22 | 0 | 18 |
| QQQ | 640 | 12 | 0 | 4 |
| IWM | 605 | 0 | 71 | 12 |

IWM non-clean sessions by month (75 of 126 since 2026-04): 2026-04: 8, 05: 10, 06: 10, 07: 18,
08: 18, 09: 11. **Most recent IWM sessions are corrupt**, and they are
exactly the window a lockbox would use.

Not checked: whether the 2026-09-22 audit's IWM minute-bar and magnitude
results (IWM was the worst-performing ticker there) were affected. They
read the same table.

### Finding B: on clean sessions, live still only partly matches replay

Restricted to sessions classified true-UTC for that ticker:

| Ticker | Sessions | Live | Replay | Matched | Same score | Live only | Replay only |
|---|---|---|---|---|---|---|---|
| IWM | 09-21, 09-22 | 5 | 6 | 2 | 2 | 3 | 4 |
| QQQ | 09-18, 21, 22, 23 | 20 | 20 | 15 | 10 | 5 | 5 |
| SPY | 09-18, 21, 22, 23 | 20 | 20 | 15 | 7 | 5 | 5 |
| **Total** | | **45** | **46** | **32 (71%)** | **19 (42%)** | 13 | 14 |

Two mechanisms, both in code:

1. **Live scores the bar that is still forming.** `gcp/signal_monitor.py:1986`:
   "`latest` is the minute currently forming, whose volume is only what
   has accumulated so far". Live fires land 1..58 s into the minute. The
   price live acted on equals the stored close of the previous bar in
   only 9 of 65 fires (median gap 1.6 bp). Replay scores completed bars.
   So live decisions depend on where in the minute the poll landed, and
   no historical replay can reproduce that.
2. **The 5-per-day cap spreads early differences into later ones.**
   `max_daily_trades = 5` binds on most ticker-days (live never exceeds
   5). One fire that differs early changes which later bars can fire.
   QQQ 09-24 is an example: replay used its 5 by 09:45, while live fired
   09:56..10:54.

### What this means for any experiment

- Every historical backtest here measures a completed-bar signal. Live
  runs a forming-bar signal. They agree on the exact fire and score about
  42% of the time on clean data. Results transfer to live only as far as
  that gap allows, or until live is changed to score completed bars (a
  production decision, not made here).
- Any session not classified true-UTC must be excluded or re-framed
  before use. For IWM that removes most of 2026-04..09.

---

## 2. Prior work to reuse, not redo

- `docs/EXPERIMENT_REGISTRY.md` has 35 registered experiments. E-18 is
  the only claimed real edge (breakout meta-labeling). E-23 is the
  cost/friction analysis. The next id is E-36.
- Cost model from E-18/E-32: realistic SPY spread about 0.6 bp
  round-trip. E-25 used a 2 bp/side stress.
- `scripts/run_param_sweep.py` tunes exits only (243 combos of
  consecutive_periods, targets, time stops). `select_calibration_winner`
  (`lib/walk_forward.py:579`) picks the winner on the same folds it
  reports, and `lib/walk_forward.py` has no purge or embargo. The sweep
  also calls `add_all_indicators` directly, which §3.6 forbids. Do not
  reuse it as the selection mechanism.

---

## 3. Prompt

```text
GOAL
Find, per ticker (IWM, QQQ, SPY) and per side (CALL, PUT), the combination
of entry thresholds, features and exit parameters that gives the best
out-of-sample expectancy NET OF COSTS, and prove it on data never used for
selection. Research only: do NOT write to exit_config_overrides or any
production table, and do NOT change live signal behavior.

READ FIRST
- docs/plans/SIGNAL_OOS_EXPERIMENT_PLAN.md sections 1 and 2. The replay path
  currently fails parity for two measured reasons; step 0 below exists
  because of them.
- docs/EXPERIMENT_REGISTRY.md. Do not repeat an experiment already there.
  Register this one as E-36.
- CLAUDE.md 0, 3.6, 3.7, 3.8, 3.9, 3.11.

WHY THE PRIOR AUDIT IS NOT SUFFICIENT
- Slicing delivered alerts can only evaluate subsets of the current gate.
  You must replay history with alternative configs to find new thresholds.
- 10 discovery sessions and 3 holdout sessions are too small. Use years.
- Thresholds were chosen on the data that scored them.

0. DATA HYGIENE (blocking)
- Run gcp/queries/classify_intraday_ts_convention.sql. Use ONLY sessions
  classified 'true-UTC' for that ticker. Report counts dropped per ticker
  and month. Do NOT "fix" ET-as-UTC rows by converting unconditionally
  (CLAUDE.md 3.9: that was tried and reverted). If you want those sessions
  back, re-frame them per session using the classifier's verdict, and
  prove the re-framing on 3 sessions by matching live price_at_signal.
- IWM is mostly 'mixed' from 2026-04 onward. If fewer than 60 clean IWM
  sessions remain in any split, report IWM as insufficient data for that
  split rather than shrinking the split.

1. PRE-REGISTER BEFORE RUNNING ANYTHING
Add the E-36 entry to docs/EXPERIMENT_REGISTRY.md with the objective,
splits, search space, trial budget and promotion criteria below, and
commit it before any result exists. Do not change it after seeing
results; add a dated amendment if you must.

2. SPLITS
- Lockbox: the most recent 3 months of CLEAN sessions per ticker. Do not
  load it until step 7.
- Development: all earlier clean sessions (target >= 2 years).
- Nested walk-forward inside development: expanding train window, 1-month
  test folds, purge = max holding horizon, embargo = 1 session between
  train and test. Selection happens inside each fold's train window only;
  each test fold is scored once.

3. PRODUCTION PARITY (CLAUDE.md 3.6)
- Signals must come from the production functions (signal_monitor
  calculate_indicators / evaluate_ticker, as scripts/replay_signal_monitor.py
  drives them), including the max_daily_trades cap, the RVOL gate and the
  level gate. Never call add_all_indicators directly.
- The replay costs ~23 s per ticker-session (measured: 5 sessions in
  ~115 s including start-up). 500 sessions x 300 trials x 6 cells is
  months of compute. So: build a vectorized evaluator over features cached
  ONCE per ticker (GCS parquet), and PROVE it equals the production replay
  on at least 20 clean sessions per ticker (identical fire minutes and
  scores under the current config) before using it. If it doesn't match,
  stop and report the diff.
- Live scores the still-forming minute; replay scores completed bars
  (plan section 1, finding B). Evaluate completed bars, and report the
  measured live-vs-replay agreement next to every result so readers know
  how far it transfers.
- Features at bar t use only bars <= t. Entry at the next bar's open.
  Premarket-brief alignment may only use a brief generated as-of that
  day; where none exists the feature is missing, not neutral.

4. OBJECTIVE AND METRICS (fixed before searching)
Primary: mean net return per trade after costs, with a 95% bootstrap CI
resampled BY SESSION.
Costs: 0.6 bp round-trip (E-18 realistic) and 2 bp per side (stress).
Secondary (report, never optimize): hit rate, trades per session, share
of folds positive, max drawdown, worst month.
Control: the current production config on the same bars. Report every
result as a difference from control.

5. SEARCH SPACE (per ticker x side, independently)
Stage A, ablation: from production, drop each entry condition one at a
time (consecutive, RSI zone, VWAP side, stoch RSI, level break, RVOL, ATR
expansion, RSI thrust, brief alignment, Strat bonus) and try time-of-day
windows. Report delta vs control per fold.
Stage B, joint search over what survived A: RSI band edges, stoch
thresholds, consecutive_periods, min core conditions, score floor, RVOL
and ATR thresholds, target, stop, time stop, max_daily_trades. Optuna TPE
or a coarse grid with a FIXED trial budget from the pre-registration
(for example 300 per cell). Log every trial, including failures.
Magnitude model: evaluate only as a binary EXPLOSIVE flag. Report PR-AUC,
reliability curve, precision at recall 0.3 and 0.5, thresholds chosen
inside train folds, on clean sessions only.

6. OVERFITTING CONTROLS
- Report configs tried and the Deflated Sharpe Ratio (or White's Reality
  Check / Hansen SPA) for each selected config.
- Report how much the selected thresholds move between folds. Large
  jumps are a finding.
- Minimum 200 trades in development and 60 in the lockbox, or the verdict
  is "insufficient sample", not a win or a loss.

7. LOCKBOX, ONE SHOT
Freeze one config per ticker x side (or "keep control"). Score it once on
the lockbox together with control. Promotable only if all hold:
  a) lower bound of the session-clustered 95% CI of (candidate - control)
     net expectancy > 0 at the 2 bp/side cost,
  b) beats control in >= 60% of development test folds,
  c) Deflated Sharpe > 0 given the trial count,
  d) minimum trade counts met.
Everything else is "not promoted", with the numbers shown. "No config
beats control" is a valid result.

8. COMPUTE (CLAUDE.md Rule 0)
Before running, write down volume, velocity, wall-clock and $/run. Run as
a Cloud Run Job, one task per ticker, task-timeout >= 4x the estimate,
max-retries 0. Read the DB only through production loaders or
scripts/db_query_cr.sh.

9. DELIVERABLES
- The E-36 registry entry, updated with results: per ticker x side table
  (control vs best, net expectancy with CI at both costs, trades, fold win
  %, DSR, lockbox result, verdict), the ablation table, the magnitude PR
  curves, sessions excluded by the hygiene step.
- Every number traceable to a committed script or query plus the Cloud
  Run execution ID. Show outputs, don't paraphrase them (CLAUDE.md 3.11).
- Hermetic tests: (a) no lookahead (perturb a future bar, assert features
  at t are unchanged); (b) vectorized evaluator equals the production
  replay on a fixture session; (c) the convention classifier on a
  synthetic true-UTC session and a synthetic ET-as-UTC session.
- A list of what could NOT be tested and why.
- Commit and push to a feature branch. Do not merge. Leave requirements
  files alone unless a dependency is truly needed; if one is, use a
  separate commit that says why.

STOP CONDITIONS
- Vectorized evaluator does not match the replay: stop, report the diff.
- Clean development data < 12 months for a ticker: report it, run the
  other tickers.
```

---

## 4. Decisions this plan leaves to the owner

1. **Should live score completed bars?** That would make live match what
   any backtest measures, at the cost of up to about one minute of
   latency. Until it does, historical results carry the 42% exact-match
   caveat above.
2. **Fix the intraday writer and migrate the ET-as-UTC and mixed rows.**
   This is the §3.9 item still open. IWM research on recent months is
   blocked until it is done.
