# Strat Implementation Plan

**Branch:** `docs/strat-implementation-plan`
**Date:** 2026-04-26
**Status:** Strat v2 shipped 2026-04-27 via PR #101 + hardening follow-ups.
**Companion doc:** [`docs/STRAT_METHODOLOGY.md`](STRAT_METHODOLOGY.md)

## Shipping log

| Item | Status | Landed in |
|---|---|---|
| Levels engine (`lib/strat_levels.py`) — PDH/PDL/PWH/PWL/PMH/PML/PQH/PQL/PYH/PYL, current-period open classification, gap detection, PMG, room-to-run | ✅ Shipped 2026-04-27 | PR #101 |
| Combo bonus tables + 4h/12h timeframe weights | ✅ Shipped 2026-04-27 | PR #101 |
| Failed_2 close-vs-open semantics + lowest-priority collision rule | ✅ Shipped 2026-04-27 | PR #101 |
| Schema: `strat_levels` long table, `level_broken` on `signal_alerts`, `strat_daily` → `strat_candle` rename | ✅ Shipped 2026-04-27 | PR #101 |
| Quarter period support in `calculate_historical_levels()` | ✅ Shipped 2026-04-27 | PR #101 |
| Brief integration: `select_orb_window()` (catalyst-aware ORB) + `format_levels_for_brief` | ✅ Shipped 2026-04-27 | PR #101 |
| Signal monitor integration: `refresh_level_map()` + `check_level_breaks()` | ✅ Shipped 2026-04-27 | PR #101 |
| Hotfix: restore FTFC + persist `strat_levels` (post-#101 deploy regressions) | ✅ Shipped 2026-04-27 | PR #120 |
| `strat_levels.strat_class` widen VARCHAR(8) → VARCHAR(16) (allow `Failed_2U`/`Failed_2D`) | ✅ Shipped 2026-04-27 | PR #125 |
| Diagnostic plumbing (basicConfig + flush + stderr step-by-step) | ✅ Shipped 2026-04-27 | PRs #121, #123, #124 |
| Remove legacy `D`/`W`/`M` timeframe-key compatibility shim (now raises `ValueError`) | ✅ Shipped 2026-04-28 | PR #128 |
| `premarket_analysis.playbook` column + warn-on-dropped-columns guard + persist allow-list | ✅ Shipped 2026-04-28 | PRs #129, #130 |
| Single-source-of-truth FTFC across brief + LLM analyst | ✅ Shipped 2026-04-27 | PR #105 |
| Level-aware trigger + gap-regime gate in trade planner | ✅ Shipped 2026-04-28 | PR #136 |
| Named-cleared-levels in `format_levels_for_brief` orb_only banner (e.g. "Last bullish level passed: PMH 228.00") | ✅ Shipped 2026-04-29 | PR #140 |
| Render polish: combo title-case + timeframe uppercase across brief + push | ✅ Shipped 2026-04-29 | PRs #143, #145 |

---

## Context

The trading platform's Strat methodology has six gap areas identified through repo audit:

1. **Strat pattern catalogue is incomplete.** `lib/strat.py` ships 12 combo patterns. Six are missing: 22 REV (mixed-direction 2-bar), 132 (coil-explode-follow), 322 (expansion-confirmed). Two multi-inside patterns (1-1, 1-1-1) are also missing.
2. **Failed_2U/2D semantics are wrong.** Code at `lib/strat.py:164-168` uses `close <= prev_high` (close-back-inside-range). The methodology defines Failed_2 by **close vs open** (`close < open` = bearish close after bullish breakout).
3. **Failed_2 priority is wrong.** Code overrides multi-bar patterns with Failed_2; methodology says multi-bar patterns are higher conviction and should win.
4. **Levels engine is missing.** `lib/indicators.py` produces ~80 columns of multi-period H/L/O/C but quarter levels are missing, current-period opens are not classified, no PMG, no gap detection, no room-to-run, no playbook trigger format.
5. **Brief only surfaces Prev_Day_H/L.** Discord brief doesn't render the playbook format (CALLS above X / PUTS below Y / ORB recommended).
6. **No real-time edge for ORB or level breaks.** ORB is computed in `signal_monitor` but no scheduled 9:45/10:00 ET alert. Level-break detection not wired into the live monitor.

This plan also resolves five naming inconsistencies:
- `strat_type`/`strat_daily` → `strat_candle`
- combo strings → `<pattern>_<direction>_<kind>`
- FTFC keys `D`/`W` → `1d`/`1w`
- remove Pine `122_RevStrat` mis-reference
- standardize mask variable names

---

## Locked decisions

| Decision | Resolution |
|---|---|
| Failed_2 definition | Close vs open. `Failed_2U`: `H>pH & L>=pL & C<O`. `Failed_2D`: `L<pL & H<=pH & C>O`. |
| Failed_2 priority | Lowest. Multi-bar combos win on collision. |
| Inside bar definition | Inclusive (`H<=pH AND L>=pL`). Must be exhaustive. |
| Column rename | `strat_type` / `strat_daily` → `strat_candle` everywhere. |
| Combo string format | `<pattern>_<direction>_<kind>` — e.g. `212_bull_reversal`, `f2u_bear_reversal`. |
| FTFC keys | `5m`, `15m`, `1h`, `4h`, `12h`, `1d`, `1w`. |
| FTFC weights | `5m: 0.05, 15m: 0.10, 1h: 0.15, 4h: 0.15, 12h: 0.15, 1d: 0.30, 1w: 0.10` (sum 1.00). |
| Mask names | `mask_<pattern>_<direction>` — `mask_212_bull`, `mask_22_bear`, `mask_f2u`, etc. |
| Levels storage | Long table `strat_levels (ticker, as_of, level_name, price, ...)`. |
| Bonus scorer return type | `float` (was `int`). Per-combo dict, supports negative bonuses for opposing patterns. |
| Multi-inside labels | `11_inside_compression`, `111_inside_compression`. |
| Clean 2U/2D bars without combo | Tagged as `clean_2u_bull` / `clean_2d_bear`. |

---

## Combo string mapping (old → new)

| Old string | New string |
|---|---|
| `2D-1-2U_reversal` | `212_bull_reversal` |
| `2U-1-2D_reversal` | `212_bear_reversal` |
| `3-1-2U_reversal` | `312_bull_reversal` |
| `3-1-2D_reversal` | `312_bear_reversal` |
| `2U-1-2U_continuation` | `212_bull_continuation` |
| `2D-1-2D_continuation` | `212_bear_continuation` |
| `2U_continuation` | `22_bull_continuation` |
| `2D_continuation` | `22_bear_continuation` |
| `3-2U_reversal` | `32_bull_reversal` |
| `3-2D_reversal` | `32_bear_reversal` |
| `Failed_2U` | `f2u_bear_reversal` |
| `Failed_2D` | `f2d_bull_reversal` |
| *(new)* | `22_bull_reversal` |
| *(new)* | `22_bear_reversal` |
| *(new)* | `132_bull_continuation` |
| *(new)* | `132_bear_continuation` |
| *(new)* | `322_bull_continuation` |
| *(new)* | `322_bear_continuation` |
| *(new)* | `11_inside_compression` |
| *(new)* | `111_inside_compression` |
| *(new)* | `clean_2u_bull` |
| *(new)* | `clean_2d_bear` |

---

## Files to create or modify

### Created
| File | Purpose |
|---|---|
| `docs/STRAT_METHODOLOGY.md` | Pattern definitions + source-of-truth inventory |
| `docs/STRAT_IMPLEMENTATION_PLAN.md` | This file |
| `lib/strat_levels.py` | Levels engine |
| `tests/test_strat_levels.py` | Levels engine tests |

### Modified
| File | Change |
|---|---|
| `lib/strat.py` | Full refactor: combos, Failed_2, bonus, weights, naming |
| `lib/data_loader.py` | `RESAMPLE_RULES` key rename + 4h/12h |
| `lib/indicators.py` | Add Quarter to `calculate_historical_levels` |
| `lib/backtest.py` | Column ref update |
| `lib/signals.py` | Level-break vote (Phase 7) |
| `lib/agents/summarizers.py` | Column + combo refs |
| `lib/agents/prompts.py` | Example combo string |
| `lib/agents/schema.py` | Pydantic field description |
| `lib/agents/ranker/signals.py` | SQL column ref |
| `gcp/schema.sql` | Column renames, Quarter cols, strat_levels table |
| `gcp/premarket_brief.py` | Playbook embed + ORB selection |
| `gcp/signal_monitor.py` | ORB snapshot + level breaks |
| `gcp/fetchers/fetch_market_data.py` | Column write verify |
| `gcp/trade_logger.py` | Column ref |
| `gcp/deploy.sh` | New scheduler triggers |
| `platform/api/routers/dashboard.py` | Column refs |
| `platform/src/routes/DashboardPage.tsx` | Drop fallback |
| `scripts/analysis/phase2_indicator_confirmation.py` | `strat_type` → `strat_candle` |
| `scripts/analysis/phase3_orb_strategies.py` | same |
| `scripts/analysis/phase4_setup_discovery.py` | same |
| `scripts/analysis/phase5_additional_dimensions.py` | same (5 sites) |
| `scripts/analysis/phase6_playbook.py` | same |
| `scripts/backfill_signals.py` | Default value |
| `tests/test_strat.py` | Full rewrite |
| `tests/conftest.py` | Fixture column name |

---

## Existing functions to reuse (do not duplicate)

| Function | Path | Reuse for |
|---|---|---|
| `StratClassifier.classify_candle()` | `lib/strat.py:42` | Call from `classify_level_strat()` |
| `StratClassifier.classify_series()` | `lib/strat.py:63` | Multi-day aggregator |
| `calculate_historical_levels()` | `lib/indicators.py:242` | Already produces Prev_Day/Week/Month/Year — add Quarter, don't reaggregate |
| `calculate_orb()` | `lib/indicators.py:295` | ORB H/L/Mid + breakout flags |
| `Broke_Prev_Day_High/Low` cols | `market_data_daily` | Level-break vote reads these |
| `signal_monitor.check_orb()` | `gcp/signal_monitor.py:168` | Extract for 9:45/10:00 snapshot |
| `economic_events.event_time` | Cloud SQL | ORB window selection |

---

## Commit plan

### Commit 1 — Docs
- `docs/STRAT_IMPLEMENTATION_PLAN.md`
- `docs/STRAT_METHODOLOGY.md`

### Commit 2 — `lib/strat.py` core refactor
All Strat logic changes atomic so behavior is consistent:
1. `strat_type` → `strat_candle`
2. Failed_2 → close-vs-open
3. Failed_2 → lowest priority
4. Add 6 new combos + 2 multi-inside
5. Rename 12 existing combo strings
6. Tag clean 2U/2D as `clean_2u_bull` / `clean_2d_bear`
7. Standardize mask names
8. Per-combo bonus dict (float, negative bonuses)
9. `DEFAULT_WEIGHTS` → 7 keys with 4h/12h
10. `RESAMPLE_RULES` update in `lib/data_loader.py`
11. Full `tests/test_strat.py` rewrite

### Commit 3 — Cascade rename
Mechanical ~15-file rename: old column/combo strings → new. Grep verification.

### Commit 4 — Quarter levels
`lib/indicators.py:264` loop + schema migration.

### Commit 5 — Levels engine (`lib/strat_levels.py`)
- `StratLevel`, `LevelMap` dataclasses
- `classify_level_strat`, `compute_previous_levels` (reads existing cols), `compute_current_levels`, `compute_gap_levels`, `detect_level_clusters`, `detect_pmg_temporal`, `compute_room_to_run`, `compute_risk_reward`, `identify_triggers`, `build_level_map`, `format_levels_for_brief`, `persist_level_map`
- `strat_levels` table + `tests/test_strat_levels.py`

### Commit 6 — Brief upgrade
4th Discord embed with playbook block. Catalyst-aware ORB selection.

### Commit 7 — Real-time edge
ORB snapshot mode, level-break detection, deploy.sh triggers, signal scoring.

---

## Verification

### Per-commit gates

| Commit | Gate |
|---|---|
| 1 | Markdown renders, inventory refs valid |
| 2 | `pytest tests/test_strat.py -v` green |
| 3 | `grep` returns zero hits for old strings in source files |
| 4 | Quarter columns populated in market_data_daily |
| 5 | `pytest tests/test_strat_levels.py -v` green; drift-guard passes |
| 6 | Dry-run brief prints expected playbook format |
| 7 | Scheduler triggers exist; monitor logs level-break embeds |

### Smoke check after Commit 3

```bash
grep -rn "strat_type\|strat_daily" lib/ gcp/ scripts/ platform/ | grep -v "\.md:"
# Expected: empty

grep -rn "2D-1-2U_reversal\|Failed_2U\|2U_continuation" lib/ gcp/ scripts/ platform/ | grep -v "\.md:"
# Expected: empty
```

### End-to-end after all commits

```bash
make test           # unit + integration
make test-e2e       # Playwright
make test-scripts   # CLI regression
```

---

## Out of scope

| Item | Reason |
|---|---|
| Frontend Levels component | Separate UI work |
| Multi-day aggregation (2D/4D/5D/8D/10D/11D) | Lower priority than intraday edge |
| Earnings screener | Overlaps `earnings_options_analytics/` |
| Pine port-back | Pine v2 already has most |
| `122_bull_revstrat` / `122_bear_revstrat` | Optional later addition |

---

## Total scope

| Commit | Files | LOC | Risk |
|---|---|---|---|
| 1 docs | 2 | ~1100 | Zero |
| 2 strat refactor | 3 | ~400 | High |
| 3 cascade rename | ~15 | ~80 | Medium |
| 4 quarter | 3 | ~30 | Low |
| 5 levels engine | 3 | ~600 | Medium |
| 6 brief upgrade | 3 | ~150 | Low |
| 7 real-time | 5 | ~200 | Medium |
| **Total** | **~30** | **~2500** | |
