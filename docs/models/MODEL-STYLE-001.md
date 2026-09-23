# MODEL-STYLE-001 — User style mining

**Code:** `lib/style_miner.py` (301 lines), `platform/api/routers/backtest.py`
(`/api/style/mine-and-validate`) · **Table:** `user_style_results` ·
**Registry:** [07-MODEL-REGISTRY](../product/07-MODEL-REGISTRY.md) ·
**Status:** Experimental · **Rec:** RETEST
**Doc health:** CURRENT · **Last verified:** 2026-09-17

> **Scope of this document.** It records what the code does, read from the source and
> its tests. Where the code does not record *why* a value was chosen, this document says
> so rather than inferring. See [Rationale](#rationale).

## What it decides

Derives a user's trading-style condition profile from their **labeled journal entries**,
producing a `StyleProfile` that is converted into a `SignalConfig` **for offline validation
only**.

`profile_to_signal_config` is called solely inside `WalkForwardValidator.run_profile`. The
endpoint writes results to `user_style_results` and candidate cards to
**`playbook_cards_staging`**, and `PLAYBOOK_USER_CARDS = False`
(`platform/api/routers/backtest.py:613`) — the live playbook reads `playbook_cards`, never the
staging table. No mined profile controls a production signal today. An earlier revision said
the profile "converts directly into engine configuration", which read as a live path.

## The condition vocabulary

A **fixed vocabulary of 8 boolean conditions**, each evaluated at the entry bar. The
`SignalConfig` column below names the lever each condition *relates to* — it is **not** a
1:1 mapping, and the miner does not learn per-condition values.

`profile_to_signal_config` (`lib/walk_forward.py:83-97,153-163`) translates the whole
profile into the single **`enabled_conditions` allowlist** and sets
`min_conditions = len(profile.conditions)`. Every threshold field —
`call_rsi_range`, `put_rsi_range`, `consecutive_periods`, `stoch_rsi_oversold`,
`stoch_rsi_overbought` — is copied from `base`, i.e. left at its default. A mined profile
therefore **selects a subset of default-valued factors**; it does not tune them. Note also
that `above_vwap` / `below_vwap` have no `SignalConfig` field at all, and both `consec_*`
conditions share one:

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

## `profile.direction` is never read, and the argument that it need not be is wrong

`StyleProfile` carries a `direction` field — `'CALL'` or `'PUT'`
(`lib/style_miner.py:133`) — and `profile_to_signal_config` (`lib/walk_forward.py:77-163`)
**never reads it**. The returned `SignalConfig` contains `min_conditions`, the four threshold
fields copied from `base`, and `enabled_conditions`. Nothing in it says which side the profile
was mined for.

The function's docstring argues that no direction gate is needed, and marks the argument
HIGH-severity (`:105-112`):

> CALL's and PUT's internal factor names never overlap … so a CALL profile's
> `enabled_conditions` list contains zero PUT factor names. `check_put_conditions` therefore
> scores 0 for every PUT factor, `put_score` is always 0, and `evaluate_signal` can never
> select PUT for that config.

**Each step is true except the premise.** The internal factor names really are disjoint
(`lib/walk_forward.py:42-45`). What does not hold is that a CALL profile contains only CALL
factor names — and the reason is in this document's own vocabulary table above.
`snapshot_entry_conditions` (`lib/style_miner.py:201-210`) returns **all eight conditions on
every entry, regardless of direction**: it evaluates `rsi_25_50` *and* `rsi_50_75`,
`above_vwap` *and* `below_vwap`, both `consec_*`, both `stoch_*`. `mine_style` then keeps, per
direction, whichever of those eight were true at or above `min_support_frac` of that
direction's resolved entries (`:238-239`).

Nothing restricts that selection to one side. A CALL fire needs 3 of its 5 conditions, so a
CALL entry at RSI 58 fails `rsi_25_50` and satisfies `rsi_50_75`; if that is common enough
among a ticker's CALL entries, `rsi_50_75` enters the CALL profile. `_translate_condition`
maps it to `rsi_overbought_zone`, it lands in `enabled_conditions`, `put_score` becomes
nonzero, and `evaluate_signal` — which selects the higher of the two scores, CALL winning only
a tie — can return **PUT** for a profile mined from CALL entries.

### Blast radius, measured

`profile_to_signal_config` has exactly one non-test caller: `WalkForwardValidator.run_profile`
(`lib/walk_forward.py:296`), itself called once, at
`platform/api/routers/backtest.py:801` — the mine-and-validate endpoint. So the consequence is
**corrupted validation metrics**, not a live trade:

- the expectancy and win rate returned in that endpoint's HTTP response describe a config that
  could fire either direction;
- the same numbers are archived to `user_style_results` and upserted into
  `playbook_cards_staging`;
- they do **not** reach the admin playbook UI, because `PLAYBOOK_USER_CARDS = False`
  (`backtest.py:613`) and the comment at `:610-611` records that the UI reads `playbook_cards`
  and never the staging table.

No signal-monitor path touches it. That bounds the damage without excusing it: the number a
user is shown for their mined style can be produced by trades in the opposite direction.

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

**Mostly recorded.** The choice to route through the production indicator path *is*
explained, with the rule it implements. So are the sample-size floors, which an earlier
revision of this document wrongly called underived:

- **`_MIN_TOTAL_ENTRIES = 10`** is pinned to a contract, not chosen locally: *"spec §8 /
  Task 4.3's endpoint contract ('need >= 10 closed trades') — the absolute floor before
  mining is attempted at all"* (`lib/style_miner.py:105-107`). The contract is
  `docs/superpowers/plans/2026-07-08-phases2-5-trade-journal-program.md:290`, which has
  `/api/style/mine-and-validate` answer `{status: "unavailable", reason: "need >= 10 closed
  trades, have N"}` below it.
- **`_MIN_DIRECTION_ENTRIES = 5`** is derived from that: *"Half of `_MIN_TOTAL_ENTRIES`, split
  across the two possible directions — below this a direction's frequency counts are too
  coarse (denominators of 1-4) to call the result a 'style' rather than noise"* (`:109-112`).
- **`_WARMUP_BARS = 14`** is a parity choice: it *"mirrors `lib.backtest._SIGNAL_WARMUP_BARS`
  / `platform/api/routers/live.py`'s `compute_live_signal_series` warm-up gate — indicators
  aren't trustworthy before this many bars"* (`:100-103`).

**UNKNOWN:** why the endpoint contract chose ten, and why the shared warm-up gate is
fourteen. Fourteen is consistent with the 14-period RSI, but none of the three sources says
that is the reason.

Mined profiles are walk-forward validated through
[MODEL-SWEEP-001](MODEL-SWEEP-001.md)'s walk-forward machinery
(`tests/lib/test_style_walk_forward.py`), whose own status is **Invalidated** — see that
document before treating a validated profile as out-of-sample.

## Tests

`tests/lib/test_style_miner.py` · `tests/lib/test_style_walk_forward.py` ·
`tests/integration/test_journal_timestamptz_roundtrip.py`

## Known issues

None filed. Origin: [#707](https://github.com/TeneikaAskew/stocks/pull/707).
