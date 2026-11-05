# STRAT foundation diagnostic (strat-foundation-diagnostic-v1)

Separately versioned captured-data diagnostic for FEAT-STRAT-001 done_when 5
([spec](../../../superpowers/specs/2026-11-05-feat-strat-001-foundation-tracked-docs-audit.md),
[plan](../../../superpowers/plans/2026-11-04-feat-strat-001-confirmed-foundation.md)).
It runs the actual producers and adapters (`lib.strat.compute_strat_status`,
`compute_confirmed_setups`, `lib.agents.summarizers.summarize_strat_status` and
`lib.agents.schema.StratSnapshot` through `lib.agents.orchestrator`) on a captured
daily IWM table already committed in the repository. It adds no vendor data,
scores no outcomes and reads no holdout.

## Result

39 cases, every check passes (`summary.all_checks_pass: true`). Each case records
the clock, the status view, the per-timeframe confirmation state and reasons, the
adapter snapshot and its checks: the adapter keeps the clock, candle, confirmed
set and score; rows after the clock change nothing; intraday timeframes are
explicitly unavailable; unavailable cases stay explicit (`X`, no score).

Four cases are unavailable and kept, not dropped: `before_second_bar`,
`daily_close_2026-04-24`, `daily_pre_close_2026-04-27` and `week_close_2026-04-24`.
The capture has no rows from 2026-04-14 to 2026-04-23, so the periods that touch
that gap are reported unconfirmed with `incomplete_coverage` and
`missing_observations` instead of being classified. The Good Friday week
(2026-04-03 holiday) completes at the 2026-04-02 16:00 close. A clock from
Monday to Thursday keeps the last closed week as the confirmed one and reports
the current week as developing until its final session close, so 22 cases carry
a confirmed weekly setup.

`weekly-confirmation.svg` draws the weekly rows (clock, judged week, state,
candle, combo) from the same manifest; its hash is in `visual.sha256`.

## Files and hashes

| File | SHA-256 |
|---|---|
| Input `tests/fixtures/iwm_market_data.json` (266 rows, 2025-03-25 to 2026-04-27) | `4bf6c653640c7636d78b88f72558a16cedff6a72b516b96320e281e0c36ac98d` |
| `StratConfig` (weights, thresholds) | `693ae966edf2a36bf225f6c7b0c828029616eb5df9cdf0fdf7ae138a597c5c31` |
| `weekly-confirmation.svg` | `91d68baa84ea6a0c7741baa7975efdf45e755a390050e4e0cd6e2610039604ee` |

Producer and adapter source hashes are in `manifest.json` under `code_sha256`.

## Reproduce

```
python scripts/research/strat_foundation_diagnostic.py          # check only, writes nothing
python scripts/research/strat_foundation_diagnostic.py --write  # rewrites this directory
```

Sockets are refused and the database loader is patched to the fixture for the
whole run. `tests/gcp/test_strat_snapshot_parity.py::test_captured_foundation_diagnostic_matches_actual_producers`
checks this manifest against the current producers and reruns four of its cases.
A new version writes a new directory; this one is not overwritten in place.

## Limitations

- `single_capture_vintage_2026-04-29_not_point_in_time`: one capture taken on
  2026-04-29, not the data as it stood on each clock.
- `price_adjustment_unknown`: the capture does not say whether prices are adjusted.
- `no_intraday_rows_5m_to_4h_confirmation_unavailable`: the capture is daily only,
  so 5m to 4h confirmation is reported unavailable, not exercised. Those timeframes
  are covered by `tests/lib/test_strat.py::TestClosedCandleConfirmation`.
- `legacy_stored_columns_are_retrospective_context_not_truth`: the stored
  `strat_candle` column is compared as context only.
- `no_outcome_scoring_or_holdout_access`.
