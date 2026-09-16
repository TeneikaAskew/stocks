# MODEL-MOM-001 — Momentum strategy

**Code:** `lib/strategies/momentum.py` (260 lines) ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Production but needs remediation · **Rec:** RETEST
**Doc health:** CURRENT · **Last verified:** 2026-09-16

> **Scope of this document.** It records what the code does, read from the source and
> its tests. Where the code does not record *why* a value was chosen, this document says
> so rather than inferring. See [Rationale](#rationale).

## What it decides

Per bar, per ticker: whether a CALL or PUT momentum signal is eligible to fire.
`CALL = buy strength` — the opposite call logic from
[MODEL-MR-001](MODEL-MR-001.md), which buys oversold dips.

The module docstring records that when both strategies fire on the same bar they take
**opposite directions ~78.6% of the time** (attributed to a 2026-05-01 audit). The
overlap case is handled by [MODEL-AGREE-001](MODEL-AGREE-001.md).

## Inputs

Indicator columns on the current bar, produced upstream by `lib/indicators.py`:
`Consecutive_Up` / `Consecutive_Down`, `RSI`, `StochRSI`, VWAP, EMA9.

## Entry points

| Symbol | Role |
|---|---|
| `MomentumStrategy` | The canonical implementation. `lib/trading_analysis.py`'s `MarketAnalyzer.generate_technical_signals` is a back-compat wrapper that delegates here |

## Conditions and thresholds

CALL fires when all hold (PUT mirrors):

| Condition | Value |
|---|---|
| Consecutive up bars | `>= 3` |
| RSI | in `(25, 50)` — described in-source as the "bullish recovery range" |
| StochRSI | `< 80` — described as "not yet overbought" |
| Price vs VWAP | above |
| Price vs EMA9 | above |

Per-ticker overrides come from `ticker_calibration` via
[MODEL-CALIB-001](MODEL-CALIB-001.md), whose own status is **Invalidated** — see its
document before treating a calibrated threshold as validated.

## Rationale

**UNKNOWN — not recorded in code or tests.** The source states the thresholds and gives
each a short label ("bullish recovery range", "not yet overbought") but records no
derivation for `3` bars, the `(25, 50)` RSI band, or the `80` StochRSI ceiling. The
module header attributes the implementation to an extraction from
`lib/trading_analysis.py:799-836`, so the values predate this module. No experiment in
[EXPERIMENT_REGISTRY](../EXPERIMENT_REGISTRY.md) evaluates them.

## Tests

`tests/lib/test_strategy_momentum.py` · `test_strategy_interface.py` ·
`test_strategy_isolation.py` · `test_strategy_legacy_parity.py` (delegation parity with
the legacy inline path) · `test_strategy_timeframe.py` ·
`tests/gcp/test_signal_monitor_standalone_momentum.py` ·
`tests/scripts/test_momentum_eligibility.py`

## Known issues

[#285](https://github.com/TeneikaAskew/stocks/issues/285) duplicate inline path ·
[#701](https://github.com/TeneikaAskew/stocks/issues/701) two divergent voters.
Titles and severity are owned by
[12-PR-ISSUE-TRACEABILITY](../product/12-PR-ISSUE-TRACEABILITY.md).
