# MODEL-MR-001 — Mean-reversion strategy

**Code:** `lib/strategies/mean_reversion.py` (200 lines) ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Production but needs remediation · **Rec:** RETEST
**Doc health:** CURRENT · **Last verified:** 2026-09-16

> **Scope of this document.** It records what the code does, read from the source and
> its tests. Where the code does not record *why* a value was chosen, this document says
> so rather than inferring. See [Rationale](#rationale).

## What it decides

Per bar, per ticker: whether a CALL or PUT mean-reversion signal is eligible to fire.
`CALL = buy oversold dips` — the opposite call logic from
[MODEL-MOM-001](MODEL-MOM-001.md).

## Inputs

Indicator columns on the current bar from `lib/indicators.py`: `Consecutive_Down` /
`Consecutive_Up`, `RSI`, `StochRSI`, VWAP, EMA fast, EMA mid, and the Strat v2 level
flag `Broke_Prev_Day_High`.

## Entry points

| Symbol | Role |
|---|---|
| `MeanReversionStrategy` | The canonical implementation. `lib/signals.py` is now a thin shim re-exporting from here; it was the original implementation the live monitor used before the refactor |

## Conditions and thresholds

CALL fires when all hold (PUT mirrors):

| Condition | Value |
|---|---|
| Consecutive down bars | `>= 3` |
| RSI | in `(25, 50)` — described in-source as "oversold but not extreme" |
| Price vs VWAP | below |
| Price vs EMA fast / EMA mid | near or below |
| StochRSI | `< 30` — "oversold" |
| `level_break_pdh` | Strat v2: `Broke_Prev_Day_High` aligned with a bullish reversal |

Note the RSI band `(25, 50)` is **identical** to MODEL-MOM-001's, while every other
condition is inverted. That is what produces the opposing-direction overlap the momentum
docstring records.

## Rationale

**UNKNOWN — not recorded in code or tests.** The source labels the bands but records no
derivation for `3` bars, `(25, 50)`, or the `30` StochRSI floor.
[#249](https://github.com/TeneikaAskew/stocks/issues/249) proposes deriving the RSI
thresholds by walk-forward rather than asserting them, which is the open work here.

## Tests

`tests/lib/test_strategy_mean_reversion.py` · `test_strategy_interface.py` ·
`test_strategy_isolation.py` · `test_strategy_legacy_parity.py` ·
`test_strategy_timeframe.py` · `test_strategy_agreement.py` ·
`tests/gcp/test_signal_monitor_timeframe.py`

## Known issues

[#249](https://github.com/TeneikaAskew/stocks/issues/249) walk-forward RSI thresholds.
Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
