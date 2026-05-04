# Strat Implementation Plan

**Branch:** `claude/review-implementation-roadmap-AJKAQ`
**Date:** 2026-04-26
**Companion doc:** `docs/STRAT_METHODOLOGY.md` (pattern definitions + source-of-truth inventory)

---

## Context

The trading platform's Strat methodology has six gap areas identified through repo audit:

1. **Strat pattern catalogue is incomplete.** Existing `lib/strat.py` ships 12 combo patterns. Six are missing: `22_REV` (mixed-direction 2-bar), `132` (coil-explode-follow), `322` (expansion-confirmed). Two multi-inside patterns (`1-1`, `1-1-1`) are also missing.
2. **`Failed_2U/2D` semantics are wrong.** Existing code at `lib/strat.py:164-168` uses `close <= prev_high` (close-back-inside-range). The methodology actually defines Failed_2 by **close vs open** (`close < open` = bearish close after bullish breakout). The two definitions tag different bars.
3. **Failed_2 priority is wrong.** Existing code overrides multi-bar patterns with Failed_2; methodology says multi-bar patterns are higher conviction and should win.
4. **Levels engine is missing.** `lib/indicators.py` already produces ~80 columns of multi-period H/L/O/C, but quarter levels are missing, current-period opens are not classified, no PMG detection (spatial or temporal), no gap detection, no room-to-run, no R:R, no playbook trigger format.
5. **Brief surfaces only Prev_Day_H/L.** Premarket Discord brief doesn't render the playbook format (`CALLS above X / PUTS below Y / 30-min ORB recommended`).
6. **No real-time edge for ORB or level breaks.** ORB is computed inside `signal_monitor` but never fired as a 9:45/10:00 ET scheduled alert. Level-break detection isn't wired into the live monitor.

This plan also resolves five repo-wide naming inconsistencies the user has approved: `strat_type`/`strat_daily` → `strat_candle`; combo strings → `<pattern>_<direction>_<kind>`; FTFC keys `D`/`W` → `1d`/`1w`; remove Pine `122_RevStrat` mis-reference; standardize mask variable names.

The intended outcome: a coherent Strat engine where the methodology doc, code, schema, brief, and monitor all use the same names and definitions, and where every combo pattern AYCE / Rob Smith / community recaps reference is detectable in Python.

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

## Files to create or modify

### Created
- `docs/STRAT_METHODOLOGY.md` — pattern definitions + source-of-truth inventory
- `docs/STRAT_IMPLEMENTATION_PLAN.md` — this file
- `lib/strat_levels.py` — levels engine
- `tests/test_strat_levels.py`
- `tests/test_premarket_brief.py` (or extend existing)
- `tests/test_signal_monitor.py` (or extend existing)

### Modified
- `lib/strat.py` — full refactor of `detect_combos`, `get_strat_bonus`, `DEFAULT_WEIGHTS`
- `lib/data_loader.py` — `RESAMPLE_RULES`
- `lib/indicators.py` — add Quarter to `calculate_historical_levels`
- `lib/backtest.py` — column ref + combo string ref
- `lib/agents/summarizers.py`, `prompts.py`, `schema.py`
- `lib/agents/ranker/signals.py`
- `lib/signals.py` — level-break vote (Phase 7)
- `gcp/schema.sql` — `strat_daily` → `strat_candle`, add Quarter cols, add `strat_levels` table, `signal_alerts.level_broken`
- `gcp/fetchers/fetch_market_data.py`
- `gcp/premarket_brief.py` — playbook embed + ORB selection
- `gcp/signal_monitor.py` — ORB snapshot mode + level break detection
- `gcp/trade_logger.py`
- `gcp/deploy.sh` — new scheduler triggers
- `platform/api/routers/dashboard.py`
- `platform/src/routes/DashboardPage.tsx`
- `scripts/analysis/phase2_indicator_confirmation.py`
- `scripts/analysis/phase3_orb_strategies.py`
- `scripts/analysis/phase4_setup_discovery.py`
- `scripts/analysis/phase5_additional_dimensions.py`
- `scripts/analysis/phase6_playbook.py`
- `scripts/backfill_signals.py`
- `tests/test_strat.py` — full rewrite for new names + new patterns

---

## Existing functions/utilities to reuse (do not duplicate)

| Function | Path | Reuse for |
|---|---|---|
| `StratClassifier.classify_candle()` | `lib/strat.py:42` | Base 1/2U/2D/3 classification — call from `classify_level_strat()` for the structural step |
| `StratClassifier.classify_series()` | `lib/strat.py:63` | Vectorized classification — call inside multi-day aggregator |
| `StratClassifier.get_trigger_levels()` | `lib/strat.py:92` | Per-bar prev H/L — keep, augmented by levels engine |
| `calculate_historical_levels()` | `lib/indicators.py:242` | Already produces `Prev_Day_*`, `Prev_Week_*`, `Prev_Month_*`, `Prev_Year_*`. **Add Quarter; do not reaggregate from raw daily_df in the new module.** |
| `calculate_orb()` | `lib/indicators.py:295` | ORB H/L/Mid + breakout flags |
| `Broke_Prev_Day_High/Low` columns | `market_data_daily` | Already populated; level-break vote in `lib/signals.py` reads these |
| `signal_monitor.check_orb()` | `gcp/signal_monitor.py:168` | Existing ORB compute inside monitor loop — extract for the 9:45/10:00 snapshot mode |
| `economic_events.event_time` | Cloud SQL | Already loaded by `gcp/premarket_brief.py:247` — read for ORB-window selection |

---

## Commit plan (7 commits)

### Commit 1 — Docs to repo
- `docs/STRAT_IMPLEMENTATION_PLAN.md` (this file)
- `docs/STRAT_METHODOLOGY.md` (pattern spec + inventory section)

### Commit 2 — `lib/strat.py` core refactor (atomic)
1. Result column rename: `strat_type` → `strat_candle`
2. Switch Failed_2 to close-vs-open
3. Demote Failed_2 to lowest priority (gate on `combo == 'none'`)
4. Add 6 new combos: `22_bull_reversal`, `22_bear_reversal`, `132_bull_continuation`, `132_bear_continuation`, `322_bull_continuation`, `322_bear_continuation`
5. Add 2 multi-inside: `11_inside_compression`, `111_inside_compression`
6. Rename existing 12 combo strings to `<pattern>_<direction>_<kind>` format
7. Tag clean 2U/2D no-combo bars as `clean_2u_bull` / `clean_2d_bear`
8. Standardize mask variable names
9. Remove Pine `122_RevStrat` docstring reference
10. Replace bonus tuple-membership with per-combo dict (float, includes negative bonuses)
11. `DEFAULT_WEIGHTS` → 7-key dict including `4h`, `12h`
12. Update `lib/data_loader.py` `RESAMPLE_RULES` keys

Tests rewritten in same commit.

### Commit 3 — Cascade rename across consumers
Mechanical updates to ~15 files (analysis scripts, agents, brief, monitor, dashboard, schema, frontend, ranker, backtest). Verification: `grep` returns zero hits for old names.

### Commit 4 — Quarter levels
- `lib/indicators.py:264` — extend loop with `('Quarter', 'Quarter')`
- `gcp/schema.sql` — `ALTER TABLE market_data_daily ADD COLUMN IF NOT EXISTS prev_quarter_*`
- Test in `tests/test_indicators.py`

### Commit 5 — `lib/strat_levels.py` engine
- Dataclasses `StratLevel`, `LevelMap`
- `classify_level_strat`, `compute_previous_levels` (reads existing columns), `compute_current_levels`, `compute_gap_levels`, `detect_level_clusters` (spatial PMG), `detect_pmg_temporal`, `compute_room_to_run`, `compute_risk_reward`, `identify_triggers` (wires `daily_strat_class` + `combo`), `build_level_map`, `format_levels_for_brief`, `persist_level_map`
- New `strat_levels` table in `gcp/schema.sql`
- Full test file `tests/test_strat_levels.py` including drift-guard test that asserts `compute_previous_levels` returns the same values as `Prev_Day_High` etc. from `market_data_daily`

### Commit 6 — Brief upgrade
- New 4th Discord embed with playbook block per ticker
- Catalyst-aware ORB window selection (8:30 ET event → 15-min, 10:00 ET event → 30-min, no event → 5-min default)
- Persist `recommended_orb_window`, `recommended_orb_reason` to `premarket_analysis`

### Commit 7 — Real-time edge
- `gcp/signal_monitor.py` — `--mode=orb-snapshot --window=15m|30m`, `check_level_breaks()` with dedup
- `gcp/deploy.sh` — new triggers `orb-15m-alert` (9:45 ET) and `orb-30m-alert` (10:00 ET), both EDT and EST cron entries
- `lib/signals.py` — 6th condition or strat-bonus component for "level break aligned with entry direction" using existing `Broke_Prev_Day_High/Low`
- `signal_alerts.level_broken` column

---

## Out of scope (explicit)

| Item | Reason for deferral |
|---|---|
| Frontend Levels component on `/dashboard`, `/charts` | Phase 8 — separate UI work, not blocking brief or monitor |
| Multi-day aggregation (2D/4D/5D/8D/10D/11D candles) | §15 of methodology doc — lower priority than intraday edge |
| Earnings screener (ATR coverage / drift / continuation) | Overlaps `earnings_options_analytics/` — confirm scope first |
| TradingView Pine port-back of new logic | Pine v2 already has most |
| `daily_rates` / SPX BSM unblock | Verify whether briefing deck §16.1 or PR #93 is current |
| Auto-tuning ORB window from backtest | Manual mapping fine for now |
| `122_bull_revstrat` / `122_bear_revstrat` 3-bar Pine pattern | Optional; can come later |

---

## Verification

### Per-commit gates

| Commit | Verification |
|---|---|
| 1 docs | Markdown renders cleanly; methodology doc inventory has all entries with file:line refs |
| 2 strat refactor | `pytest tests/test_strat.py -v` green; new patterns covered |
| 3 cascade rename | `grep -rn "strat_type\|strat_daily\|2D-1-2U_reversal\|Failed_2U" lib/ gcp/ scripts/ platform/` returns zero hits in source files (only in docs) |
| 4 quarter | `psql -c "SELECT prev_quarter_high FROM market_data_daily WHERE ticker='IWM' ORDER BY date DESC LIMIT 5"` returns non-null after fetcher run |
| 5 levels engine | `pytest tests/test_strat_levels.py -v`; round-trip persistence; drift-guard test passes |
| 6 brief | Local dry-run prints expected Discord embed JSON for fixture date with all sections (Combo, T1, Stop, PMG) populated |
| 7 real-time | Cloud Scheduler shows `orb-15m-alert` and `orb-30m-alert` triggers; signal_monitor logs level-break embeds during paper-trade hour |

### End-to-end test

After all 7 commits land:

```bash
# 1. Schema migration
bash gcp/deploy.sh migrate

# 2. Run unit + integration tests
make test
# Expected: only pre-existing failures (test_pipeline_end_to_end_green, test_health_returns_ok,
# Cloud-SQL-dependent tests). All Strat / levels / brief tests green.

# 3. Run E2E
make test-e2e

# 4. Run script regression
make test-scripts

# 5. Trigger premarket brief in dev mode
python -m gcp.premarket_brief --ticker IWM --dry-run
# Expected: 4-embed Discord JSON with playbook block, levels, ORB recommendation

# 6. Trigger ORB snapshot manually
python -m gcp.signal_monitor --mode=orb-snapshot --window=15m --ticker=IWM --dry-run
# Expected: ORB break classification + Discord embed format

# 7. Run signal_monitor in fixture mode
python -m gcp.signal_monitor --fixture=tests/fixtures/iwm_intraday.csv
# Expected: level-break alerts log when synthetic price crosses PDH or PDL
```

### Drift guard (committed test)

`tests/test_strat_levels.py::test_compute_previous_levels_matches_market_data_daily` —
loads a real row from `market_data_daily` for IWM, calls `compute_previous_levels()` with
the same date, asserts that `levels['PDH'].price == row['prev_day_high']`. Catches future
divergence between the two code paths.

### Smoke check

```bash
# After Commit 3, verify no orphaned references:
grep -rn "strat_type\|strat_daily" lib/ gcp/ scripts/ platform/ | grep -v "\.md:"
# Expected output: empty

# Verify all old combo strings replaced:
grep -rn "2D-1-2U_reversal\|2U-1-2D_reversal\|3-1-2U_reversal\|3-1-2D_reversal\|Failed_2U\|Failed_2D\|2U_continuation\|2D_continuation" lib/ gcp/ scripts/ platform/ | grep -v "\.md:"
# Expected output: empty
```

---

## Total scope

| Commit | Files | Approx LOC | Risk |
|---|---|---|---|
| 1 docs | 2 | ~1100 | Zero |
| 2 strat refactor | 3 | ~400 | High blast radius |
| 3 cascade rename | ~15 | ~80 mechanical | Medium |
| 4 quarter | 3 | ~30 | Low |
| 5 levels engine | 3 | ~600 | Medium |
| 6 brief upgrade | 3 | ~150 | Low |
| 7 real-time | 5 | ~200 | Medium |
| **Total** | **~30 files** | **~2500 LOC** | |

Estimated 5–6 focused sessions if no major regressions.
