# MODEL-MR-001 — Mean-reversion strategy

**Code:** `lib/signals.py` (`evaluate_signal`, the **live** implementation) ·
`lib/strategies/mean_reversion.py` (`MeanReversionStrategy`, the offline class) ·
thresholds in `lib/strategies/config.py` and `lib/config.py:SignalConfig` ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Production but needs remediation · **Rec:** RETEST
**Doc health:** CURRENT · **Last verified:** 2026-09-17

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

**Precedence:** when both sides clear the gate, the **higher score wins**, and CALL wins
only a **tie**: the CALL branch is `call_score >= MIN_CONDITIONS and call_score >= put_score`
(`mean_reversion.py:160`), so `call_score=3, put_score=4` fails it and the `elif
put_score >= MIN_CONDITIONS` branch (`:164`) emits PUT. Only `call_score == put_score` with
both at or above 3 is decided by precedence. The live path has the same shape
(`lib/signals.py:333-344`, with the kill switches added — see [Entry points](#entry-points)).

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

**Two implementations exist, and the live one is not the class.** An earlier revision of
this document called `lib/signals.py` "a thin shim re-exporting from" `MeanReversionStrategy`.
It is the opposite: `lib/signals.py` carries its own `check_call_conditions` (`:33`),
`check_put_conditions` (`:98`) and `evaluate_signal` (`:178`), and that is what production
calls.

| Symbol | Role |
|---|---|
| `lib.signals.evaluate_signal` | **The live implementation.** `SignalMonitor._evaluate_strategies_for_bar` calls it directly (`gcp/signal_monitor.py:1107-1114`) with `min_conditions=self.signal_cfg.min_conditions`, `consecutive_periods=get_consecutive_periods(ticker)` and `ticker=ticker` |
| `MeanReversionStrategy` (`lib/strategies/mean_reversion.py`) | The Phase 0.8 extraction, exported as the `MEAN_REVERSION` singleton (`lib/strategies/__init__.py:33`). Used by the agreement detector's docstring contract and the offline tests; **not called on the production fire path** |

The two score the same five factor names with the same thresholds, and both dropped the
EMA condition (`lib/signals.py:78-81` records the same 84.6% measurement). What only the
live path applies — and what therefore decides real fires — is the runtime layer around
the score:

| Gate | Where | Value |
|---|---|---|
| Score floor | `SignalConfig.min_conditions`, not the module constant | default **3** (`lib/config.py:425`), overridable from config |
| Consecutive window | `get_consecutive_periods(ticker)` (`lib/strategies/exit_config_overrides.py:220`) | Tier A `exit_config_overrides.consecutive_periods`, written by the walk-forward sweep ([MODEL-CALIB-001](MODEL-CALIB-001.md)); Tier B `SignalConfig.consecutive_periods = 3` (`lib/config.py:426`) |
| Condition kill switch | `exit_config_overrides.disabled_conditions` | matching names are stripped from `call_conds` / `put_conds` and the scores decremented **before** the floor is compared (`lib/signals.py:311-314`) |
| Direction kill switch | `get_disabled_directions(ticker)` (`lib/signals.py:315`, `exit_config_overrides.py:237`) | a disabled side cannot fire even if it clears the floor (`:333-344`) |
| Fail-closed | malformed `disabled_conditions` (`:290`, `:306`) or a resolver failure (`:329`) | **no mean-reversion signal for that bar** — `return None`, logged, per CLAUDE.md Rule 3.7 |

None of these gates exists in `MeanReversionStrategy.evaluate`, so a reader who reasons
from the class alone will predict fires on a ticker whose PUT side is switched off. No
issue tracks the duplicate mean-reversion path (the momentum twin is
[#285](https://github.com/TeneikaAskew/stocks/issues/285)); recorded as DOC-22 in
[07 § Documentation coverage](../product/07-MODEL-REGISTRY.md#documentation-coverage-and-freshness).

## Rationale

**Partly recorded.** Dropping EMA-proximity is derived, with the 84.6% fire-rate measurement
quoted above — the same reasoning that removed StochRSI from momentum, applied consistently.

**UNKNOWN — not recorded in code or tests:** `MIN_CONDITIONS = 3`, the `(25, 50)` band,
`CONSECUTIVE_PERIODS = 3`, and the `30` / `70` StochRSI bounds.
[#249](https://github.com/TeneikaAskew/stocks/issues/249) proposes deriving the RSI
thresholds by walk-forward rather than asserting them, which is the open work.

The CALL-on-tie precedence is stated in code but carries no rationale, and it is not
neutral: on a bar where both sides score the same, direction is decided by precedence
rather than evidence. (When the scores differ the higher one wins, which needs no rationale.)

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
