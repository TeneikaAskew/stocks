# MODEL-SWEEP-001 — Walk-forward parameter sweep

**Code:** `lib/walk_forward.py` (607 lines), `scripts/run_param_sweep.py`,
`scripts/calibrate_iwm_strat.py`, `scripts/run_walk_forward.py` ·
**Table:** `exit_config_overrides` · **Job:** `param-sweep` — deployed but **unscheduled**, run by hand ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** **Invalidated** · **Rec:** RESTRUCTURE
**Doc health:** CURRENT · **Last verified:** 2026-09-18

> **Read this before using a swept parameter set.** The status is **Invalidated** and the
> reasons are not cosmetic — see [Why this is Invalidated](#why-this-is-invalidated).

## What it decides

Anchored walk-forward over entry/exit parameter combinations, picking a winner per ticker
and writing it to `exit_config_overrides`, which the live exit path reads.

**This was split out of MODEL-CALIB-001 on 2026-09-18.** Until then one registry row
covered both this and the percentile calibrator, so an operator assessing the *scheduled*
quarterly job inherited this system's `Invalidated` status and its three CRITICAL findings.
The two share the word "calibration" and nothing else:

| | **Percentile calibrator** | **Walk-forward parameter sweep** |
|---|---|---|
| Entry point | `scripts/calibrate_thresholds.py` | `scripts/run_param_sweep.py` |
| Scheduled? | **Yes** — `calibrate-thresholds-quarterly`, `0 2 1 1,4,7,10 *` | No — run by hand |
| Algorithm | ATR / RVOL / RSI distributions over a **rolling 60-day** bar history | **Anchored walk-forward** via `WalkForwardValidator`, winner by `select_calibration_winner` |
| Writes | `ticker_calibration` | `exit_config_overrides` |
| Read by | [MODEL-MOM-001](MODEL-MOM-001.md), [MODEL-MR-001](MODEL-MR-001.md), the live signal monitor | the live exit path ([MODEL-EXIT-001](../product/07-MODEL-REGISTRY.md)) |
| Implicated by #813 / #817 | No | **Yes** |

`scripts/calibrate_thresholds.py` does not import `WalkForwardValidator` at all. Everything
below belongs to **this** model, not to [MODEL-CALIB-001](MODEL-CALIB-001.md).

## Entry points

| Symbol | Role |
|---|---|
| `WalkForwardValidator` | The anchored walk-forward driver (`lib/walk_forward.py`) |
| `WalkForwardResult` | Per-fold result record |
| `select_calibration_winner` | Picks the winning parameter set across folds |
| `profile_to_signal_config` | Converts a mined profile (see [MODEL-STYLE-001](MODEL-STYLE-001.md)) into `SignalConfig` |
| `run_param_sweep.main` | The sweep entry point that writes `exit_config_overrides` |

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

**There is no `E-` id for MODEL-SWEEP-001** in
[EXPERIMENT_REGISTRY](../EXPERIMENT_REGISTRY.md). That absence is itself the finding: the
sweep writes `exit_config_overrides` — the configuration that gates live fires — and no
experiment in the ledger evaluates it. Its `Invalidated` status rests on the three audit
findings below, not on a ledger result.

(The percentile calibrator, [MODEL-CALIB-001](MODEL-CALIB-001.md), has the same gap for its
own separate reason. This section was copied from that document when the two were split and
initially still described it; corrected 2026-09-18.)

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
