# MODEL-MR-001 — Mean-reversion strategy

**Code:** `lib/strategies/mean_reversion.py` (200 lines), thresholds in
`lib/strategies/config.py` ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Production but needs remediation · **Rec:** RETEST
**Doc health:** CURRENT · **Last verified:** 2026-09-16

> **Read from the scoring functions, not the module docstring.** The first version of this
> document was assembled from `mean_reversion.py`'s module docstring, which lists an EMA
> condition the code no longer has — see
> [A warning about this module's own docstring](#a-warning-about-this-modules-own-docstring).

## What it decides

Per bar, per ticker: whether a CALL or PUT mean-reversion signal is eligible to fire.
`CALL = buy oversold dips` — the opposite call logic from
[MODEL-MOM-001](MODEL-MOM-001.md).

## The firing rule: a scored gate, not a conjunction

**It is not "all conditions hold".** Five conditions are scored one point each; a fire needs
`score >= MIN_CONDITIONS` = **3** of 5 (`config.py:107`, applied at `mean_reversion.py:160`).

Unlike [MODEL-MOM-001](MODEL-MOM-001.md) there is **no core-condition requirement** — any
three of the five suffice.

**Tie-break:** when both sides clear the gate, CALL wins
(`call_score >= MIN_CONDITIONS and call_score >= put_score`, `:160`). PUT fires only when it
clears and CALL does not (`:164`).

## The five scored conditions (CALL; PUT mirrors)

| # | Condition name | Test | Threshold | Source |
|---|---|---|---|---|
| 1 | `consecutive_down` | `Consecutive_Down >= 3` | `CONSECUTIVE_PERIODS = 3` | `config.py:53` |
| 2 | `rsi_oversold_zone` | `25 < RSI < 50` | `CALL_RSI_RANGE = (25.0, 50.0)` | `config.py:31` |
| 3 | `below_vwap` | `Price_vs_VWAP < 0` | — | `mean_reversion.py:82` |
| 4 | `stoch_rsi_oversold` | `StochRSI_K < 30` | `STOCH_RSI_OVERSOLD = 30.0` | `config.py:43` |
| 5 | `level_break_pdh` | `Broke_Prev_Day_High == 1` | — | `mean_reversion.py:90` |

PUT mirrors: `consecutive_up`, `50 < RSI < 75` (`PUT_RSI_RANGE`), `Price_vs_VWAP > 0`,
`StochRSI_K > 70` (`STOCH_RSI_OVERBOUGHT`), `Broke_Prev_Day_Low == 1`.

**There is no EMA condition.** EMA-proximity was removed, and the function docstring records
why with the measurement: it *"fired on 84.6% of bars — the same 'free score' pathology
momentum had with `stoch_rsi_not_overbought`"*.

Note condition 2's band `(25, 50)` is **identical** to MODEL-MOM-001's while every other
condition is inverted. That is the mechanism behind the opposing-direction overlap the
momentum module records.

## Entry points

| Symbol | Role |
|---|---|
| `MeanReversionStrategy` | The canonical implementation. `lib/signals.py` is now a thin shim re-exporting from here |

## Rationale

**Partly recorded.** Dropping EMA-proximity is derived, with the 84.6% fire-rate measurement
quoted above — the same reasoning that removed StochRSI from momentum, applied consistently.

**UNKNOWN — not recorded in code or tests:** `MIN_CONDITIONS = 3`, the `(25, 50)` band,
`CONSECUTIVE_PERIODS = 3`, and the `30` / `70` StochRSI bounds.
[#249](https://github.com/TeneikaAskew/stocks/issues/249) proposes deriving the RSI
thresholds by walk-forward rather than asserting them, which is the open work.

The CALL-wins tie-break is stated in code but carries no rationale, and it is not neutral:
on a bar where both sides score 3, direction is decided by precedence rather than evidence.

## A warning about this module's own docstring

`mean_reversion.py`'s **module** docstring (lines 1-18) lists six CALL conditions including
*"Near or below EMA fast / EMA mid"*. That condition **does not exist in the code** — it was
removed, as the function docstring at `:60-64` explains. A reader trusting the module
docstring would expect a factor the strategy never evaluates.

Recorded as DOC-18 in
[07 § Documentation coverage](../product/07-MODEL-REGISTRY.md#documentation-coverage-and-freshness).

## Tests

`tests/lib/test_strategy_mean_reversion.py` · `test_strategy_interface.py` ·
`test_strategy_isolation.py` · `test_strategy_legacy_parity.py` ·
`test_strategy_timeframe.py` · `test_strategy_agreement.py` ·
`tests/gcp/test_signal_monitor_timeframe.py`

## Known issues

[#249](https://github.com/TeneikaAskew/stocks/issues/249) walk-forward RSI thresholds.
Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
