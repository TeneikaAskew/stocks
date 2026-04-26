# Strat Implementation Plan

**Branch:** `claude/review-implementation-roadmap-tYcRI`
**Companion doc:** [`docs/STRAT_METHODOLOGY.md`](STRAT_METHODOLOGY.md) — pattern definitions + source-of-truth inventory.

---

## Locked decisions

| Decision | Resolution |
|---|---|
| Failed_2 definition | Close vs open. `f2u_bear_reversal`: `2U & Close < Open`. `f2d_bull_reversal`: `2D & Close > Open`. |
| Failed_2 priority | Lowest. Multi-bar combos win on collision. |
| Inside bar definition | Inclusive (`H ≤ pH AND L ≥ pL`). |
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

## Commit plan (7 commits)

| # | Goal | Files | Risk |
|---|---|---|---|
| 1 | Methodology + plan docs | 2 | Zero |
| 2 | `lib/strat.py` core refactor + tests + `RESAMPLE_RULES` | 3 | High blast radius |
| 3 | Cascade `strat_type`/`strat_daily` rename + combo string rename across consumers | ~15 | Medium (mechanical) |
| 4 | Add Quarter levels to `lib/indicators.py` + schema columns | 3 | Low |
| 5 | `lib/strat_levels.py` engine + tests + `strat_levels` table | 3 | Medium |
| 6 | Premarket brief playbook embed + catalyst-aware ORB | 3 | Low |
| 7 | ORB scheduled snapshots + level-break detection in monitor + level-break vote in signals | 5 | Medium |

---

## Reuse — do not duplicate

| Function | Path | Purpose |
|---|---|---|
| `StratClassifier.classify_candle` | `lib/strat.py:42` | Base 1/2U/2D/3 classification |
| `StratClassifier.classify_series` | `lib/strat.py:63` | Vectorized classification |
| `StratClassifier.get_trigger_levels` | `lib/strat.py:92` | Per-bar prev H/L |
| `calculate_historical_levels` | `lib/indicators.py:242` | Prev period H/L/O/C — Quarter added in commit 4 |
| `calculate_orb` | `lib/indicators.py:295` | ORB H/L/Mid + breakout flags |
| `Broke_Prev_Day_High/Low` columns | `market_data_daily` | Already populated; level-break vote consumes these |
| `signal_monitor.check_orb` | `gcp/signal_monitor.py` | Existing ORB compute |
| `economic_events.event_time` | Cloud SQL | Brief reads for ORB-window selection |

---

## Verification gates

| Commit | Gate |
|---|---|
| 1 | Markdown renders cleanly; inventory table has all entries with file:line refs |
| 2 | `pytest tests/test_strat.py` green; full coverage of new patterns |
| 3 | `grep` returns zero hits for old strings; `make test` baseline |
| 4 | `Prev_Quarter_*` columns populate for SPY/IWM/QQQ daily fetcher run |
| 5 | `pytest tests/test_strat_levels.py`; round-trip persistence works |
| 6 | Manual Discord webhook fires expected format in dev env |
| 7 | Cloud Scheduler shows new triggers; signal_monitor logs level breaks |

---

## Out of scope

- Frontend Levels component on `/dashboard` and `/charts`
- Multi-day aggregation (2D/4D/5D/8D/10D/11D)
- Earnings screener (ATR / drift / continuation)
- TradingView Pine port-back
- Auto-tuning ORB window selection from backtest
- `122_bull_revstrat` / `122_bear_revstrat` 3-bar Pine pattern
