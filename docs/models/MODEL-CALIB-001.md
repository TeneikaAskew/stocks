# MODEL-CALIB-001 — Per-ticker threshold calibration (percentile)

**Code:** `scripts/calibrate_thresholds.py` ·
**Table:** `ticker_calibration` · **Job:** `calibrate-thresholds`
(`0 2 1 1,4,7,10 *`, quarterly) ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** **Retest Required** · **Rec:** RETEST
**Doc health:** CURRENT · **Last verified:** 2026-09-18

> **This model is not Invalidated, and until 2026-09-18 this document said it was.** One
> registry row used to cover both this and the walk-forward sweep, so the `Invalidated`
> status and issues [#813](https://github.com/TeneikaAskew/stocks/issues/813) /
> [#817](https://github.com/TeneikaAskew/stocks/issues/817) — which belong to the sweep —
> were attached to the scheduled quarterly job as well. They are now
> [MODEL-SWEEP-001](MODEL-SWEEP-001.md).

## What it decides

Per-ticker ATR / RVOL / RSI distributions over a **rolling 60-day** bar history, upserted
into `ticker_calibration`.

**Most of what it writes is never read.** The only production consumer is
`lib/strategies/calibration.py`, and it selects **`rsi_p10` … `rsi_p90`** alone, deriving the
CALL range from `(rsi_p10, rsi_p50)` and the PUT range from `(rsi_p50, rsi_p90)` for
[MODEL-MOM-001](MODEL-MOM-001.md) and [MODEL-MR-001](MODEL-MR-001.md). `threshold_clean`,
`threshold_wrong`, `threshold_noise`, `rvol_min`, `rvol_max` and the ATR medians are written
and tested but no fire path consumes them. An earlier revision said the strategies read its
ATR, RVOL and RSI thresholds as operating configuration, which overstated the reach of a
scheduled job by most of its output.

**The `threshold_clean` / `_wrong` / `_noise` columns are stranded more sharply than "no fire
path reads them" conveys.** The one system in this repository that classifies signals as clean,
wrong or noise — by those exact names — is [MODEL-QUAL-001](MODEL-QUAL-001.md)
(`scripts/signal_quality_report.py`), and it uses **module-level constants of its own**,
`CLEAN_THRESHOLD = 0.005` and `NOISE_THRESHOLD = 0.003` (`:69-70`), classifying every ticker at
the same cut-points. It never queries `ticker_calibration`. So a per-ticker calibration is
computed quarterly, drift-checked, refused above 3σ, and then ignored by its only conceptual
consumer. Recorded 2026-09-18 when MODEL-QUAL-001 was registered.

## The resolution chain — a successful write does not mean a changed threshold

**Writing a row is not the same as production reading it.** An earlier revision of this
document described the path to MODEL-MOM-001 / MODEL-MR-001 as unconditional. It is gated four
ways, and any one of them silently substitutes the universal Tier-B constants
`CALL_RSI_RANGE = (25.0, 50.0)` / `PUT_RSI_RANGE = (50.0, 75.0)`
(`lib/strategies/config.py:31-32`). An operator reading only "the quarterly job succeeded"
would conclude live thresholds moved; often they did not.

`_latest_calibration` (`lib/strategies/calibration.py:60-137`) returns `None` — meaning Tier B —
when:

| Gate | Where | Effect |
|---|---|---|
| Cloud SQL not configured | `:73-74` | CI and unit tests always run Tier B |
| No row for the ticker | `:118-120` | logged `no row for %s — Tier-B fallback` |
| **Row older than `_STALE_DAYS = 180`** (`:36`) | `:124-129` | a quarterly writer leaves ~90 days of headroom; two consecutive skipped quarters expire the row |
| **`drift_flagged` is true** | `:130-137` | the row is written and then ignored |

and, per percentile rather than per row, `_is_usable_number` (`:39-55`) rejects `None`, `NaN`
and `inf`. That guard is load-bearing: `pd.read_sql` materialises SQL `NULL` as `NaN`, and a
`(nan, nan)` range makes the gate `low < rsi < high` silently **always false** for that ticker —
CLAUDE.md Rule 3.7 applied at the read side.

`drift_flagged` is set by the writer, not the reader. `scripts/calibrate_thresholds.py`
compares each new value against the rolling 4-row mean and standard deviation for that ticker
(`_DRIFT_MIN_PRIOR_ROWS = 3`, `:279`):

- **≥ `_DRIFT_WARN_SIGMAS = 2.0`** (`:277`) → the row is written with `drift_flagged=TRUE`, so
  the reader falls back to Tier B. One anomalous quarter cannot whipsaw production.
- **≥ `_DRIFT_REFUSE_SIGMAS = 3.0`** (`:278`) → the write is **refused** for that ticker
  (`:436-442`) unless `--force`.
- **`sd == 0.0` — a flat prior history → *any* nonzero change flags** (`:343-352`), with the
  sigma thresholds never reached: the branch sets `drift_flagged = True` and `continue`s, so it
  can flag but can never **refuse**. The log line says so — *"sd=0 (history is flat) → ANY
  change is drift"*.

  This is the branch most likely to surprise an operator, and it is not a corner case: the
  guard needs only `_DRIFT_MIN_PRIOR_ROWS = 3` prior rows, and a quarterly writer producing
  three or four identical values for a stable ticker is ordinary. The next calibration that
  moves a percentile by any amount at all is then flagged, and the live resolver silently drops
  to Tier B for that ticker. A successful write, a tiny change, and no threshold crossed — and
  production stops reading it.

So `--force` is the switch that puts a drifted calibration into production: with it, the row is
written `drift_flagged=FALSE` (`:450-457`), which the comment there explains is deliberate —
otherwise the reader would keep falling back and the manual override would be a no-op.

> **The code and its own comment disagree by one boundary.** The design comment at `:255-260`
> says `|new - mean| > 2σ` and `> 3σ`; the implementation at `:354` and `:361` compares `>=`.
> Exactly-2σ flags and exactly-3σ refuses. Recorded rather than corrected — changing either is a
> code PR, and this document's job is to say what runs.

## Not a walk-forward system

`scripts/calibrate_thresholds.py` does not import `WalkForwardValidator`:

| | **Percentile calibrator** | **Walk-forward parameter sweep** |
|---|---|---|
| Entry point | `scripts/calibrate_thresholds.py` | `scripts/run_param_sweep.py` |
| Scheduled? | **Yes** — `calibrate-thresholds-quarterly`, `0 2 1 1,4,7,10 *` | No — run by hand |
| Algorithm | ATR / RVOL / RSI distributions over a **rolling 60-day** bar history | **Anchored walk-forward** via `WalkForwardValidator`, winner by `select_calibration_winner` |
| Writes | `ticker_calibration` | `exit_config_overrides` |
| Read by | [MODEL-MOM-001](MODEL-MOM-001.md), [MODEL-MR-001](MODEL-MR-001.md), the live signal monitor | the live exit path ([MODEL-EXIT-001](../product/07-MODEL-REGISTRY.md)) |
| Implicated by #813 / #817 | No | **Yes** |

## Entry points

| Symbol | Role |
|---|---|
| `calibrate_thresholds.main` | The scheduled entry point (`scripts/calibrate_thresholds.py`), `--lookback-days` default 60 |

## Why this is not evaluated

**No experiment in the ledger evaluates this system**, and that absence is the finding. The
system that writes operating thresholds into production quarterly has never been tested
against the question it exists to answer: whether a rolling 60-day percentile is the right
threshold. That is why the status is **Retest Required** rather than a promotion-grade one.

It is also why [#380](https://github.com/TeneikaAskew/stocks/issues/380), the open follow-up
on data-driven `disabled_conditions`, matters here — it is the nearest thing to an
evaluation anyone has proposed.

## Rationale

**UNKNOWN — not recorded in code or tests.** The 60-day lookback carries no derivation. The
percentile cut-points are stated as constants. Nothing records why 60 days rather than 30 or
120, and no measurement compares them.

## Tests

`tests/scripts/test_scripts.py` covers the CLI surface. There is no test asserting that the
thresholds it produces generalise, which is the gap the status records.

## Known issues

None open names this system directly. [#380](https://github.com/TeneikaAskew/stocks/issues/380)
is adjacent. The issues that used to appear here — #813, #817, #886 — belong to
[MODEL-SWEEP-001](MODEL-SWEEP-001.md).
