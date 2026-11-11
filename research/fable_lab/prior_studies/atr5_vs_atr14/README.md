# ATR5 vs ATR14 as the level parameter basis (PR #1784)

Date: 2026-11-11. Code: PR #1784 head 049ffa3f (feature/feat-strat-001-level-params-v3), run from a detached worktree. Research only: nothing pushed, no production access.

## Question and hypothesis

Every per-ticker level parameter in #1784 is in ATR units of the column named by the `level_param_policy` row `atr_basis` (seeded `atr_14`). Hypothesis: calibrating and applying the parameters on ATR5 instead of ATR14 gives better brief trigger and plan outcomes, because levels adapt faster to volatility changes.

Pass rule used here: ATR5 minus ATR14 in R is positive with a 90% day-bootstrap range above zero, for triggers or plans, in both windows, with no significant loss on the other.

## Answer

**No. ATR5 does not meet the hypothesis in either window.** Every total difference has a 90% range that spans zero, and the signs disagree between windows.

| Window | Triggers, ATR5 minus ATR14 (R) | Plans, ATR5 minus ATR14 (R) |
|---|---|---|
| Recent, 2026-05-01 to 2026-11-10 (134 sessions) | -2.47 [-7.23, 1.62] | +4.92 [-16.82, 25.74] |
| Holdout, 2025-03-03 to 2026-04-30 (293 sessions), break keys min sample 40 | -0.48 [-3.63, 2.45] | -12.98 [-39.29, 13.64] |
| Holdout, policy as seeded | -0.48 [-3.63, 2.45] | -4.02 [-8.52, -0.61] (artefact, see below) |

Per ticker (R, 90% range):

| | Recent triggers | Recent plans | Holdout triggers | Holdout plans (min sample 40) |
|---|---|---|---|---|
| SPY | -1.56 [-3.86, 0.31] | +3.46 [-6.59, 13.47] | -0.96 [-4.16, 1.88] | -1.97 [-13.96, 9.50] |
| QQQ | -0.57 [-5.89, 3.16] | +9.62 [-4.24, 22.34] | +0.38 [-0.05, 0.93] | -18.91 [-35.48, -2.59] |
| IWM | -0.34 [-1.64, 0.92] | -8.16 [-20.40, 3.37] | +0.10 [-0.01, 0.24] | +7.90 [-4.61, 21.49] |

The one range clear of zero is QQQ holdout plans, and it goes against ATR5.

The mechanism the hypothesis relies on (sessions where ATR5 and ATR14 disagree) does not show a consistent gain either:

| Subset (ticker-sessions) | Recent triggers | Recent plans | Holdout triggers | Holdout plans (40) |
|---|---|---|---|---|
| Vol rising, ATR5/ATR14 > 1.15 (46; 126) | +1.15 [-0.12, 3.15] | +1.17 [-10.11, 13.42] | -2.27 [-5.34, -0.03] | -8.57 [-23.41, 5.63] |
| Vol falling, ATR5/ATR14 < 0.85 (55; 147) | +0.16 [0.00, 0.48] | -2.28 [-12.84, 8.36] | +0.48 [0.05, 1.03] | +3.92 [-3.01, 11.17] |
| Steady, 0.85 to 1.15 (289; 573) | -3.78 [-8.06, -0.33] | +6.03 [-7.81, 20.15] | +1.31 [0.00, 3.19] | -8.33 [-27.81, 11.68] |

Absolute totals for context (recent, all three tickers): triggers -1.54 R (ATR14) vs -4.01 R (ATR5) on 442 vs 435 fills; plans -68.56 R vs -63.64 R on 1,032 vs 1,014 fills. Both arms lose on plans in this replay; the basis does not change that.

Recommendation: keep `atr_basis = atr_14`. Do not add the switching policy row.

## How different the levels are

The basis changes little, because ATR5 and ATR14 sit close most days (median ATR5/ATR14 0.98; 10th to 90th percentile 0.83 to 1.17) and each parameter is recalibrated in its own basis, which absorbs most of the scale difference.

Brief fields (recent window, 390 ticker-sessions scored):
- Calls trigger changed on 11 of 390, puts trigger on 14 of 389; median change when changed 3.3 points (SPY 2.7 / 5.6, QQQ 9.4 / 4.0, IWM 0.3 / 0.8 calls / puts). Median change over all sessions: 0 points.
- Brief stops changed on 4, T1 on 13.
- Premarket high or low changed (print filter) on 25.

Plans (median absolute change per ticker-session, recent): entry midpoint 0.08 points (SPY 0.09, QQQ 0.15, IWM 0.05), stop 0.16 (SPY 0.18, QQQ 0.34, IWM 0.08), first target 0.16. On vol-rising sessions these grow to 0.30 / 0.55 / 0.70.
Holdout: triggers changed on 17 of 1,689 sides, median 1.0 to 1.2 points; plan entry 0.05, stop 0.11, T1 0.12 points.

Calibrated parameters in points (value times the basis ATR), median absolute change per session, recent window: trigger windows SPY 1.5 / 2.2, QQQ 1.9 / 2.6, IWM 0.7 / 0.6 points (long / short); pm_spike SPY 0.85, QQQ 1.30, IWM 0.24; stop_neutral SPY 0.21, QQQ 0.37, IWM 0.09. Full table: `params_points.json`.

## Method

1. **Daily bars**: the as-traded open/high/low/close columns of `/mnt/project-files/strat-verify/ftfc-replay/raw/*_daily_adjusted.csv` (2015 onward), plus the committed fixture rows for 2026-11-05, 11-06 and the 2026-11-09 bar replay_day.py appends. `atr_14` and `atr_5` from `lib.indicators.calculate_atr` (Wilder), `sma_200` a 200-session mean of close: the columns the job reads from `market_data_daily`.
   Checks (`tools/prep_data.py`, `data_checks.json`): raw daily equals the committed fixture on all 483 overlapping days (max difference 1e-13); `adjusted_close` differs from close by up to 4.6% since 2023 (dividends), so adjusted prices were not used, since production and the 1-min bars are unadjusted; 1-min RTH close vs daily close median error 0.007%, max 0.96% (SPY); 1-min RTH high and low equal the daily high and low on at least 95% of 423 sessions.
2. **Calibration** (`tools/calibrate_basis.py`): the #1784 job's own path, `gcp.calibrate_level_params.policy_on(..., atr_basis=...)` (the job's `--atr-basis` preparation run), `window_policy_resolver`, `lib.level_calibration.HistoryCalibrator.calibrate`, `to_rows`, with the policy rows seeded by `gcp/schema.sql`. One version per ticker per session, each from bars strictly before that session (no lookahead), for both bases, 2025-03-03 to 2026-11-10. 1-min bars: `/mnt/project-files/stocks-scorecard/inputs/bars_raw/`.
3. **Replay** (`tools/run_basis.py`, `tools/replay_basis.py`): the scorecard's `tools/replay_day.py`, unchanged, at the 08:30 cutoff, each session with its own params file. `replay_basis.py` makes two changes: the params file's basis becomes the `atr_basis` policy row in force (a row dated 2015-01-03 beside the seeded one, as a basis switch would be done), and the premarket snapshot is filtered as production's `fetch_premarket_refresh` does (`premarket_filter_inputs` on the session's params and the prior session's ATR in the policy basis), where the fixture always used ATR14.
4. **Scoring** (`tools/compare.py`, `tools/hscore_local.py`): `hscore.py` unchanged except that a session with no premarket snapshot scores instead of raising. Brief triggers both sides with the brief's stop and T1; every persona plan at its entry midpoint, stop and first target; R = move / |fill - stop| on 09:30 to 15:59 bars. Paired ATR5 minus ATR14 per ticker-session; 90% range = 5th to 95th percentile of 2000 resamples of session days (seed 7), as `paired.py`.

## Caveats (what is not production-faithful, and why)

1. **One-minute history starts 2025-03-03.** Production calibrated from Cloud SQL minutes back to about 2023-11. There is no older 1-min data in the project files and production was off limits. Effect, checked against run 84421818 for 2026-11-02 to 11-06 (`params_run_84421818`) with ATR14:
   - Identical: both trigger windows on all three tickers, the at-trigger entry edges, pm_spike (SPY, QQQ), level_cluster (SPY, IWM). Daily-bar and 60-session minute parameters are reproduced exactly.
   - Different: break-derived keys (entry buffers, stops, targets: 750-session lookback) use only 2025-03 onward offline. Example SPY 2026-11-06: entry_buffer_aggressive_hi 1.125 (production) vs 0.326 (offline), neutral_hi 0.418 vs 0.085; production SPY has stop_aggressive, stop_conservative and the aggressive and conservative targets at insufficient_history, offline they are ok. QQQ and IWM are closer (QQQ aggressive_hi 0.48 vs 0.40). pm_stale_print is about 20% higher in production (the live feed carries prints the AV history lacks).
   So the A/B is like for like (both bases see identical data), but absolute plan R is not production's. The SPY production entry buffers look large next to QQQ and IWM and next to the offline values; worth a separate look at SPY's pre-2025 minute rows in Cloud SQL.
2. **Holdout break parameters.** With history from 2025-03-03, the policy minimum of 150 breaks is reached about 2025-09 for entry buffers and only 2026-04 to 2026-05 for stops and targets. Under the policy as seeded the holdout publishes almost no plans; its QQQ plan difference (-4.02 R) comes from a few April 2026 sessions where ATR14 reached the minimum (2026-04-10) before ATR5 (2026-04-16), an availability artefact, not a basis effect. The holdout plan result above therefore uses a second calibration with min_sample 40 for every break-derived key in both arms (a policy deviation, no lookahead). Trigger results are identical in the two holdout runs, as expected (brief triggers do not read those keys).
3. **First 39 holdout sessions** (2025-03-03 to 2025-04-28): the premarket thresholds lack 40 sessions of minute history, so the snapshot is unfiltered in both arms.
4. The recent window's first 9 to 14 sessions (to about 2026-05-20) also have stops and targets at insufficient_history in one or both arms; kept, as production would behave the same with this data.
5. 08:30 cutoff only; the 09:20 cutoff was not run.
6. The brief's ATR comes from the committed fixture frame (bars from 2024-12-02), so early-2025 ATR14 carries a small Wilder warm-up residue (about 1%); the calibration ATR uses bars from 2015.
7. R is in each trade's own risk, so it compares outcomes, not dollar size.

## Files

- `sessions_recent_2026-05-01_2026-11-10.csv`, `sessions_holdout_minsample40_2025-03-03_2026-04-30.csv`, `sessions_holdout_policy_2025-03-03_2026-04-30.csv`: one row per session and ticker, R per arm, fills, every brief level per arm and its change, plan entry/stop/T1 changes, ATR14 and ATR5.
- `summary_*.json`: the tables above, plus fills and average R.
- `params_points.json`: calibrated parameter values and points per basis.
- `tools/`: every script used.
- Intermediate outputs (per-day params files, calibration rows, replay JSONs) are in `/tmp/claude-0/-home-user/e21e199c-cf90-5c22-8afa-93bf6f11a73f/scratchpad/atr_exp/` (scratch, not kept).

## Rerun

```bash
WT=/tmp/claude-0/-home-user/e21e199c-cf90-5c22-8afa-93bf6f11a73f/scratchpad/atr_wt   # any path
W=/tmp/claude-0/-home-user/e21e199c-cf90-5c22-8afa-93bf6f11a73f/scratchpad/atr_exp   # work dir
R=/mnt/project-files/stocks-scorecard/research/atr5_vs_atr14
git -C /home/claude/stocks-v3 worktree add --detach $WT 049ffa3f
# prep, 12 calibrations, 6 replay sets (about 1,440 replays), 3 comparisons; skips outputs that exist
bash $R/tools/run_all.sh $WT $W
cd $WT && PYTHONPATH=platform:. /home/claude/venv/bin/python $R/tools/params_diff.py $W $R
```

Calibration takes about 2.5 minutes per ticker and basis; a replay about 3 seconds per session (4 in parallel).
