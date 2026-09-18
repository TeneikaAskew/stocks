# MODEL-CALIB-001 — Per-ticker threshold calibration

**Code — two writers, see below:** (A) `scripts/calibrate_thresholds.py` → `ticker_calibration`,
scheduled; (B) `lib/walk_forward.py` (607 lines) + `scripts/run_param_sweep.py` →
`exit_config_overrides`, on demand. Also `scripts/calibrate_iwm_strat.py`,
`scripts/run_walk_forward.py` ·
**Jobs:** `calibrate-thresholds` (`0 2 1 1,4,7,10 *`, quarterly) · `param-sweep` (unscheduled) ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** **Invalidated** · **Rec:** RESTRUCTURE
**Doc health:** CURRENT · **Last verified:** 2026-09-17

> **Read this before using a calibrated threshold.** This registry row covers **two
> independent writers** that an earlier revision of this document merged into one: a
> scheduled percentile calibrator and an on-demand walk-forward parameter sweep. The
> **Invalidated** status and the issues behind it belong to the sweep — see
> [Which writer is Invalidated](#which-writer-is-invalidated). The scheduled writer has
> never been evaluated at all. Both write production configuration that the live monitor
> reads.

## What it decides

Per-ticker operating configuration for the live signal monitor, produced by two systems
that share a registry row and nothing else:

| | (A) Percentile calibrator | (B) Walk-forward parameter sweep |
|---|---|---|
| Script | `scripts/calibrate_thresholds.py` | `scripts/run_param_sweep.py` driving `lib/walk_forward.py` |
| Cloud Run Job | `calibrate-thresholds` (`gcp/deploy.sh:3513-3525`, `python -m scripts.calibrate_thresholds`) | `param-sweep` (`gcp/deploy.sh:3541-3564`, `python -m scripts.run_param_sweep`) |
| Schedule | `calibrate-thresholds-quarterly`, `0 2 1 1,4,7,10 *` (`gcp/deploy.sh:4765`) | **none** — *"On-demand only (no Cloud Scheduler entry ...)"* (`:3537-3538`) |
| Writes | `ticker_calibration`, upsert on `(ticker, calibration_date)` (`calibrate_thresholds.py:487`) | every combo to `walk_forward_results`, the winner to `exit_config_overrides` (`run_param_sweep.py:11-13`, `:216-217`) |
| Read live by | `lib/strategies/calibration.py` — Tier A `ticker_calibration.rsi_p10..p90` (`:9`) becomes the per-ticker RSI band the monitor passes into **both** [MODEL-MOM-001](MODEL-MOM-001.md) and [MODEL-MR-001](MODEL-MR-001.md) (`gcp/signal_monitor.py:1084-1085`); missing, stale or drift-flagged rows fall back to Tier B (`calibration.py:119-132`) | `lib/strategies/exit_config_overrides.py` — `consecutive_periods` (`:220`), the exit targets and time-stops, and the `disabled_conditions` / `disabled_directions` kill switches the live MR path applies (`lib/signals.py:311-315`) |

### (A) The scheduled algorithm is a rolling distribution, not a walk-forward

`scripts/calibrate_thresholds.py` reads a rolling 60-day bar history per ticker
(`--lookback-days`, default 60, `:390-391`) from `market_data_intraday` and computes, per
timeframe: the ATR median in % of price (*"the noise floor"*), the RVOL P25/P50/P75/P95
distribution, and the RSI P10/P25/P50/P75/P90 distribution (`:8-11`). It then writes
clean/wrong/noise thresholds as fixed ATR multiples — `CLEAN_ATR_MULT = 1.0`,
`WRONG_ATR_MULT = 1.0`, `NOISE_ATR_MULT = 0.6` (`:72-74`). There are no folds, no held-out
window and no selection step: it describes the recent distribution and publishes it.

### (B) The walk-forward sweep is the anchored walk-forward

`lib/walk_forward.py` implements **anchored walk-forward**: an expanding training window
with a fixed test window, sliding forward one test period at a time (`:4-5`).
`scripts/run_param_sweep.py:183-195` runs `WalkForwardValidator.walk_forward_sweep` over
`PARAM_GRID` (`:63`) — the four exit parameters plus `consecutive_periods` (`:15-16`) —
ranks by out-of-sample expectancy under stability gates, and `select_calibration_winner`
picks the row that `apply_winner` (`:113`) writes to `exit_config_overrides` unless
`--no-apply` is passed.

## Entry points

| Symbol | Writer | Role |
|---|---|---|
| `calibrate_thresholds.main` | A | The quarterly job's entrypoint (`scripts/calibrate_thresholds.py:385`) |
| `WalkForwardValidator` | B | The anchored walk-forward driver |
| `WalkForwardResult` | B | Per-fold result record |
| `select_calibration_winner` | B | Picks the winning parameter set across folds |
| `profile_to_signal_config` | B | Converts a mined profile (see [MODEL-STYLE-001](MODEL-STYLE-001.md)) into `SignalConfig` |

A third scheduled job, `audit-walkforward-weekly` (`0 9 * * 6`), runs
`scripts.analysis.per_factor_walkforward --folds 4` through `gcp.audit_job_runner`
(`gcp/deploy.sh:2579-2580`, `:2592`). It reads and reports; it writes no configuration, and
[#380](https://github.com/TeneikaAskew/stocks/issues/380) is the open proposal to let its
verdicts drive `disabled_conditions`.

## Which writer is Invalidated

The findings that carry the status name the sweep, not the calibrator:

| Issue | Names | Finding |
|---|---|---|
| [#813](https://github.com/TeneikaAskew/stocks/issues/813) | `lib/walk_forward.py:301-380,577-607` + `scripts/run_param_sweep.py:188-206` (its own *Location* line) | The "out-of-sample" calibration **is in-sample**, and it **auto-writes production** — training writes configuration as a side effect of the job completing |
| [#817](https://github.com/TeneikaAskew/stocks/issues/817) | `run_param_sweep.py` (its definition of done) | Exhaustive in-sample mining with no out-of-sample holdout and **no multiple-testing control** |
| [#886](https://github.com/TeneikaAskew/stocks/issues/886) | the research universe | Hand-picked-universe **survivorship bias** — applies to anything calibrated on SPY/QQQ/IWM alone, so to both writers |

`scripts/calibrate_thresholds.py` does not import `WalkForwardValidator` at all; the two
scripts share no code beyond `gcp.database`.

**Writer (A) has no finding, no experiment and no evaluation.** An earlier revision of this
document gave the quarterly percentile calibrator the sweep's algorithm ("anchored
walk-forward"), its evidence and its invalidation rationale, so a reader would have
concluded the scheduled job was condemned by #813 when #813 never examined it. Its actual
standing is *never assessed*: a descriptive-statistics job that writes the RSI band both
live strategies use, on a cron, with nothing in the ledger or the issue tracker saying
whether the band it produces is any better than the Tier-B constant. Recorded under DOC-21 in
[07 § Documentation coverage](../product/07-MODEL-REGISTRY.md#documentation-coverage-and-freshness).
Whether the two writers should be split into separate `MODEL-*` rows is an open decision
in [15-OPEN-DECISIONS](../product/15-OPEN-DECISIONS.md).

CLAUDE.md's promotion criteria state that **training must not write production as a side
effect of a job completing**, and name `mag_walk_forward.promotion_verdict`
([#810](https://github.com/TeneikaAskew/stocks/pull/810)) as the precedent gate to reuse.
This model predates that gate and does not use it.

## No experiment evaluates this system

**There is no `E-` id for MODEL-CALIB-001** in
[EXPERIMENT_REGISTRY](../EXPERIMENT_REGISTRY.md). That absence is itself the finding: the
system that writes thresholds into production has never been evaluated in the ledger.

E-20 is *not* its evidence — E-20 asks whether sigmoid or isotonic post-hoc calibration
improves a LightGBM model's probability ECE, with artifacts in `strat_config.py` and
`mag_config.py`. It belongs to the TYPE and MAG engines. The two share only the word
"calibration"; mapping E-20 here made a successful probability experiment read as support
for this threshold writer, which is why it was moved (DOC-04).

## Rationale

**UNKNOWN — not recorded in code or tests**, for both writers.

- **(A)** The ATR multiples `1.0` / `1.0` / `0.6` (`calibrate_thresholds.py:72-74`) and the
  60-day window carry short labels and no derivation. The script's own docstring frames
  the RSI percentiles as *"for sanity-checking that the universal CALL/PUT RSI ranges ...
  are still appropriate"* (`:10-12`), yet `lib/strategies/calibration.py` promotes them to
  the live Tier-A band — a stronger use than the writer describes for itself.
- **(B)** The anchored walk-forward *design* is stated in the module docstring; what is
  missing is any record that the parameters it selects generalise, which is precisely
  what #813 and #817 dispute.

## Tests

`tests/lib/test_walk_forward.py` · `test_style_walk_forward.py` ·
`test_insight_walk_forward.py` · `test_strat_walk_forward_calibration.py` ·
`test_strat_calibration_flags.py` · `tests/scripts/test_run_walk_forward_persist.py` ·
`test_per_factor_walkforward.py` · `tests/integration/test_param_sweep_persistence.py`

## Known issues

[#813](https://github.com/TeneikaAskew/stocks/issues/813) ·
[#817](https://github.com/TeneikaAskew/stocks/issues/817) ·
[#886](https://github.com/TeneikaAskew/stocks/issues/886) ·
[#380](https://github.com/TeneikaAskew/stocks/issues/380).
Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
