# MODEL-STYLE-001 — User style mining

**Code:** `lib/style_miner.py` (301 lines), `platform/api/routers/backtest.py`
(`/api/style/mine-and-validate`) · **Table:** `user_style_results` ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Experimental · **Rec:** RETEST
**Doc health:** CURRENT · **Last verified:** 2026-09-16

> **Scope of this document.** It records what the code does, read from the source and
> its tests. Where the code does not record *why* a value was chosen, this document says
> so rather than inferring. See [Rationale](#rationale).

## What it decides

Derives a user's trading-style condition profile from their **labeled journal entries**,
producing a `StyleProfile` that converts directly into engine configuration.

## The condition vocabulary

A **fixed vocabulary of 8 boolean conditions**, each evaluated at the entry bar and each
mapping 1:1 onto a `lib.config.SignalConfig` tunable:

| Condition | Reads | SignalConfig tunable |
|---|---|---|
| `rsi_25_50` | `RSI{rsi_period}` between `call_lo`/`call_hi` | `call_rsi_range` (default 25–50) |
| `rsi_50_75` | `RSI{rsi_period}` between `put_lo`/`put_hi` | `put_rsi_range` (default 50–75) |
| `above_vwap` | `Price_vs_VWAP > 0` | VWAP side |
| `below_vwap` | `Price_vs_VWAP < 0` | VWAP side |
| `consec_up_ge_{N}` | `Consecutive_Up >= N` | `consecutive_periods` |
| `consec_down_ge_{N}` | `Consecutive_Down >= N` | `consecutive_periods` |
| `stoch_oversold` | `StochRSI_K < sig_cfg.stoch_rsi_oversold` | `stoch_rsi_oversold` |
| `stoch_overbought` | `StochRSI_K > sig_cfg.stoch_rsi_overbought` | `stoch_rsi_overbought` |

All eight, read from the returned dict at `lib/style_miner.py:200-210`. The `{N}` in the two
consecutive-bar keys is interpolated from the resolved `consecutive_periods`, so the key name
itself carries the threshold.



**Conditions are evaluated through the production indicator path**
(`lib.indicators.add_signal_indicators`) — the same function the live signal-series
endpoint and `lib.backtest.replay_labeled_trades` use — *"never a hand-rolled formula"*.
That is CLAUDE.md Rule 3.6 applied deliberately, and it is the reason this model's
outputs are comparable with production rather than with a parallel implementation.

## Thresholds

| Name | Value | Line | Meaning |
|---|---|---|---|
| `_WARMUP_BARS` | `14` | `lib/style_miner.py:103` | bars required before conditions are evaluable |
| `_MIN_TOTAL_ENTRIES` | `10` | `:107` | minimum labeled entries to mine a profile |
| `_MIN_DIRECTION_ENTRIES` | `_MIN_TOTAL_ENTRIES // 2` = `5` | `:112` | minimum per direction |
| `_DIRECTIONS` | `('CALL', 'PUT')` | `:114` | |

## Entry points

`StyleProfile` · `snapshot_entry_conditions` · `mine_style`

## Rationale

**Partly recorded, and the sample floors are among the recorded parts.** The choice to
route through the production indicator path *is* explained, with the rule it implements.
So are both floors, at `style_miner.py:105-112`: `_MIN_TOTAL_ENTRIES = 10` is tied to the
*"spec §8 / Task 4.3 endpoint contract (need >= 10 closed trades)"*, and
`_MIN_DIRECTION_ENTRIES` is derived as half of it because *"denominators of 1-4 are too
coarse to call the result a style rather than noise"*. An earlier revision of this
document said both carried no derivation, which discarded recorded provenance.

**UNKNOWN:** `_WARMUP_BARS = 14` is consistent with a 14-period RSI, but the source does
not say that is why.

Mined profiles are walk-forward validated through
[MODEL-CALIB-001](MODEL-CALIB-001.md)'s machinery
(`tests/lib/test_style_walk_forward.py`), whose own status is **Invalidated** — see that
document before treating a validated profile as out-of-sample.

## Tests

`tests/lib/test_style_miner.py` · `tests/lib/test_style_walk_forward.py` ·
`tests/integration/test_journal_timestamptz_roundtrip.py`

## Known issues

None filed. Origin: [#707](https://github.com/TeneikaAskew/stocks/pull/707).
