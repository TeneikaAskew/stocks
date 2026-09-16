# MODEL-CALIB-001 — Per-ticker threshold calibration

**Code:** `lib/walk_forward.py` (607 lines), `scripts/calibrate_thresholds.py`,
`scripts/calibrate_iwm_strat.py`, `scripts/run_walk_forward.py` ·
**Table:** `ticker_calibration` · **Job:** `calibrate-thresholds`
(`0 2 1 1,4,7,10 *`, quarterly) ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** **Invalidated** · **Rec:** RESTRUCTURE
**Doc health:** CURRENT · **Last verified:** 2026-09-16

> **Read this before using a calibrated threshold.** This model's status is
> **Invalidated**, and the reasons are not cosmetic — see
> [Why this is Invalidated](#why-this-is-invalidated). It writes to production on a
> quarterly cron regardless.

## What it decides

Per-ticker parameter thresholds, written into the `ticker_calibration` table, which
[MODEL-MOM-001](MODEL-MOM-001.md), [MODEL-MR-001](MODEL-MR-001.md) and the live signal
monitor then read as their operating configuration.

Implements **anchored walk-forward**: an expanding training window with a fixed test
window, sliding forward one test period at a time.

## Entry points

| Symbol | Role |
|---|---|
| `WalkForwardValidator` | The anchored walk-forward driver |
| `WalkForwardResult` | Per-fold result record |
| `profile_to_signal_config` | Converts a mined profile (see [MODEL-STYLE-001](MODEL-STYLE-001.md)) into `SignalConfig` |
| `select_calibration_winner` | Picks the winning parameter set across folds |

## Why this is Invalidated

Three open findings, each independently sufficient:

| Issue | Finding |
|---|---|
| [#813](https://github.com/TeneikaAskew/stocks/issues/813) | The "out-of-sample" calibration **is in-sample**, and it **auto-writes production** — training writes configuration as a side effect of the job completing |
| [#817](https://github.com/TeneikaAskew/stocks/issues/817) | Exhaustive in-sample mining with no out-of-sample holdout and **no multiple-testing control** |
| [#886](https://github.com/TeneikaAskew/stocks/issues/886) | Hand-picked-universe **survivorship bias** |

[#380](https://github.com/TeneikaAskew/stocks/issues/380) is the open follow-up to close
the loop with data-driven `disabled_conditions`.

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

**UNKNOWN — not recorded in code or tests**, and the surrounding evidence is contested.
The anchored walk-forward *design* is stated in the module docstring; what is missing is
any record that the thresholds it produces generalise, which is precisely what #813 and
#817 dispute.

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
