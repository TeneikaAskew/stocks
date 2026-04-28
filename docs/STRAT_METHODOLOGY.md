# The Strat — Complete Pattern Definitions

**Source of truth** for all Strat logic in this codebase.
When code and this doc diverge, **this doc wins**.

**Reference:** Rob Smith methodology, TheStrat-Indicators.com, AYCE community recaps.

---

## Variables used throughout

```
H     = current bar high          pH    = previous bar high
L     = current bar low           pL    = previous bar low
O     = current bar open          pH2   = two bars ago high
C     = current bar close         pL2   = two bars ago low
type  = current bar strat class   prev  = previous bar class
                                  prev2 = two bars ago class
```

---

## 1. Base candle classification (single bar vs previous bar)

| Type | Condition | Meaning |
|---|---|---|
| **1** (Inside) | `H <= pH AND L >= pL` | Entirely within previous range. Compression. |
| **2U** (Up) | `H > pH AND L >= pL` | Broke above previous high only. Bullish attempt. |
| **2D** (Down) | `L < pL AND H <= pH` | Broke below previous low only. Bearish attempt. |
| **3** (Outside) | `H > pH AND L < pL` | Broke both sides. Expansion / broadening. |

**Note:** Inclusive inequalities (`<=`, `>=`) ensure classification is exhaustive. When `H == pH AND L == pL`, the bar is Type 1 (no break either way).

First bar in any series has no prior — classified as `'X'` (unknown).

---

## 2. Failed patterns (single bar, close vs open)

A "failed" candle breaks one side of the previous range but closes in the opposite direction of the break. **Close vs open determines bullish/bearish**, not close vs previous range.

| Pattern | Condition | Meaning | Bias |
|---|---|---|---|
| **Failed 2U** | `H > pH AND L >= pL AND C < O` | Broke prev high but closed bearish (red) | PUT |
| **Failed 2D** | `L < pL AND H <= pH AND C > O` | Broke prev low but closed bullish (green) | CALL |
| **Clean 2U** | `H > pH AND L >= pL AND C >= O` | Broke prev high and closed bullish | CALL |
| **Clean 2D** | `L < pL AND H <= pH AND C <= O` | Broke prev low and closed bearish | PUT |

**Doji edge case:** `C == O` exactly → treat as clean (not failed). Strict inequality (`C < O`, not `C <= O`) handles this.

**Why close vs open, not close vs prev range:**
- The methodology says "takes out the high and **closes bearish**"
- A bar can break prev high, close bearish (red), yet still close above prev high — that's still a failed breakout because the candle reversed direction
- The Pine `122_RevStrat` pattern (close back inside range) is a **different, 3-bar pattern**, not single-bar Failed_2

---

## 3. Multi-inside patterns (consecutive Type 1 bars)

| Pattern | Condition | Label | Signal |
|---|---|---|---|
| **Double Inside** | `type == '1' AND prev == '1'` | `11_inside_compression` | Deeper compression, larger breakout expected |
| **Triple Inside** | `type == '1' AND prev == '1' AND prev2 == '1'` | `111_inside_compression` | Maximum compression, explosive move imminent |

Example: MSFT triple inside break below 520.15 (AYCE).

---

## 4. Two-bar combos (consecutive directional, no inside between)

| Pattern | Condition | Label | Display | Bias | Bonus |
|---|---|---|---|---|---|
| **22 REV Up** | `prev == '2D' AND type == '2U'` | `22_bull_reversal` | "22 REV to the upside" | CALL | +1.0 |
| **22 REV Down** | `prev == '2U' AND type == '2D'` | `22_bear_reversal` | "22 REV to the downside" | PUT | +1.0 |
| **22 CON Up** | `prev == '2U' AND type == '2U'` | `22_bull_continuation` | "22 CON to the upside" | CALL | +0.5 |
| **22 CON Down** | `prev == '2D' AND type == '2D'` | `22_bear_continuation` | "22 CON to the downside" | PUT | +0.5 |

---

## 5. Three-bar combos: 2-1-2 (reversal / continuation after coil)

| Pattern | Condition | Label | Display | Bias | Bonus |
|---|---|---|---|---|---|
| **212 REV Up** | `prev2 == '2D' AND prev == '1' AND type == '2U'` | `212_bull_reversal` | "212 REV to the upside" | CALL | +1.0 |
| **212 REV Down** | `prev2 == '2U' AND prev == '1' AND type == '2D'` | `212_bear_reversal` | "212 REV to the downside" | PUT | +1.0 |
| **212 CON Up** | `prev2 == '2U' AND prev == '1' AND type == '2U'` | `212_bull_continuation` | "212 CON to the upside" | CALL | +0.75 |
| **212 CON Down** | `prev2 == '2D' AND prev == '1' AND type == '2D'` | `212_bear_continuation` | "212 CON to the downside" | PUT | +0.75 |

---

## 6. Three-bar combos: 3-1-2 (outside bar digested)

| Pattern | Condition | Label | Bias | Bonus |
|---|---|---|---|---|
| **312 Up** | `prev2 == '3' AND prev == '1' AND type == '2U'` | `312_bull_reversal` | CALL | +1.0 |
| **312 Down** | `prev2 == '3' AND prev == '1' AND type == '2D'` | `312_bear_reversal` | PUT | +1.0 |

---

## 7. Three-bar combos: 1-3-2 (coil, explode, follow-through)

| Pattern | Condition | Label | Display | Bias | Bonus |
|---|---|---|---|---|---|
| **132U** | `prev2 == '1' AND prev == '3' AND type == '2U'` | `132_bull_continuation` | "132U to the upside" | CALL | +1.0 |
| **132D** | `prev2 == '1' AND prev == '3' AND type == '2D'` | `132_bear_continuation` | "132D to the downside" | PUT | +1.0 |

Example: BABA "2D 132U to the upside" (AYCE).

---

## 8. Three-bar combos: 3-2-2 (expansion then direction)

| Pattern | Condition | Label | Display | Bias | Bonus |
|---|---|---|---|---|---|
| **322U** | `prev2 == '3' AND prev == '2U' AND type == '2U'` | `322_bull_continuation` | "322 to the upside" | CALL | +0.75 |
| **322D** | `prev2 == '3' AND prev == '2D' AND type == '2D'` | `322_bear_continuation` | "322 to the downside" | PUT | +0.75 |

Example: IWM "322 first live + Daily failed directional to the upside" (AYCE).

---

## 9. Two-bar combos: 3-2 (outside bar then directional)

| Pattern | Condition | Label | Bias | Bonus |
|---|---|---|---|---|
| **32 Up** | `prev == '3' AND type == '2U'` | `32_bull_reversal` | CALL | +0.75 |
| **32 Down** | `prev == '3' AND type == '2D'` | `32_bear_reversal` | PUT | +0.75 |

---

## 10. Level classification (current period vs previous period)

Classifies the RELATIONSHIP between the current period's evolving price action and the previous period's range. Used for dynamic level coloring.

| State | Condition | Color | Meaning |
|---|---|---|---|
| **Inside (1)** | `cH <= pH AND cL >= pL` | Gray | Trading within previous range |
| **2U** | `cH > pH AND cL >= pL AND cC >= cO` | Aqua/Green | Broke above, currently bullish |
| **Failed 2U** | `cH > pH AND cL >= pL AND cC < cO` | Fuchsia/Red | Broke above but reversed below open |
| **2D** | `cL < pL AND cH <= pH AND cC <= cO` | Red/Dark | Broke below, currently bearish |
| **Failed 2D** | `cL < pL AND cH <= pH AND cC > cO` | Lime/Yellow | Broke below but reversed above open |
| **3 (Outside)** | `cH > pH AND cL < pL` | Purple | Broke both sides |

Applied to each timeframe pair:
- Current Day Open vs Previous Day High/Low
- Current Week Open vs Previous Week High/Low
- Current Month Open vs Previous Month High/Low
- Current Quarter Open vs Previous Quarter High/Low
- Current Year Open vs Previous Year High/Low

---

## 11. Level hierarchy

### Previous levels (fixed, no repainting)

| Abbrev | Full name | Timeframe |
|---|---|---|
| PYH / PYL | Previous Year High / Low | Yearly (strongest) |
| PQH / PQL | Previous Quarter High / Low | Quarterly |
| PMH / PML | Previous Month High / Low | Monthly |
| PWH / PWL | Previous Week High / Low | Weekly |
| PDH / PDL | Previous Day High / Low | Daily (most traded) |

### Current levels (live, repaints)

| Abbrev | Full name |
|---|---|
| CYO | Current Year Open |
| CQO | Current Quarter Open |
| CMO | Current Month Open |
| CWO | Current Week Open |
| CDO | Current Day Open |

### Intraday levels

| Abbrev | Full name |
|---|---|
| ORB_H / ORB_L | Opening Range High / Low (15m or 30m) |
| HOD / LOD | High of Day / Low of Day |
| PMK_H / PMK_L | Pre-Market High / Low |

### Derived levels

| Abbrev | Full name |
|---|---|
| GAP_H / GAP_L | Unfilled gap boundaries |
| PMG zone | Pivot Machine Gun cluster |

---

## 12. PMG (Pivot Machine Gun)

Two or more levels from DIFFERENT timeframes clustering within a tight price band (default 0.15%).

**Detection:**
```
for each level L[i]:
    cluster = {L[i]}
    for each L[j] where j > i:
        if abs(L[j].price - L[i].price) / L[i].price <= 0.0015:
            cluster.add(L[j])
    if len(cluster) >= 2:
        PMG zone at mean(cluster prices)
```

**Strength scoring:**
`strength = count(levels) + (count(unique_timeframes) - 1) * 0.5`

Example: PDL at 262.14, PWL at 262.30, gap fill at 262.10 → count=3, timeframes=2, strength=3.5

When price approaches a PMG zone, it either bounces hard (all levels as S/R) or breaks through and runs (multiple targets taken out = "daily PMG" per AYCE).

---

## 13. Room to run

Distance from current price to next level in the trade direction.

- **CALL:** `(next_level_above - price) / price * 100`
- **PUT:** `(price - next_level_below) / price * 100`
- **Minimum threshold:** 0.20% room to justify entry

Below 0.20% → caution, insufficient risk/reward.

---

## 14. Trigger level identification (for the brief)

```
CALLS above 265.17 (PDH)
  Stop: 262.14 (PDL)
  T1: 266.89 (PWH) — 0.58% room (R:R 1.7)
  T2: 268.50 (PMH) — 1.40% room (R:R 4.1)
```

**Logic:**
- CALL trigger = first significant level above price (usually PDH)
- PUT trigger = first significant level below price (usually PDL)
- Stop = opposite-direction level
- Targets = subsequent levels in direction, ordered by price

**Bias adjustment:**
- Bearish bias (Failed 2U) → PUTS primary, CALLS "only if bias denied"
- Bullish bias (Failed 2D) → CALLS primary, PUTS "only if bias denied"
- Mixed/neutral → both presented equally: "trade what triggers"

---

## 15. Multi-day aggregation

Custom-period candles (2D, 4D, 5D, 8D, 10D, 11D):

```
agg_open  = first bar's open
agg_high  = max(all bars' highs)
agg_low   = min(all bars' lows)
agg_close = last bar's close
```

Classify the aggregated candle against its previous N-day candle using §1 rules.

Example: MSFT "below 517.55 triggers the 11D 22 REV to the downside" — the 11-day aggregated sequence shows a 22 REV.

---

## 16. Full Timeframe Continuity (FTFC)

All timeframes aligned in the same directional bias.

### Weights

| Timeframe | Key | Weight |
|---|---|---|
| Weekly | `1w` | 0.10 |
| Daily | `1d` | 0.30 |
| 12-Hour | `12h` | 0.15 |
| 4-Hour | `4h` | 0.15 |
| 1-Hour | `1h` | 0.15 |
| 15-Minute | `15m` | 0.10 |
| 5-Minute | `5m` | 0.05 |
| **Total** | | **1.00** |

### Per-timeframe contribution

| Last bar type | Contribution |
|---|---|
| 2U | +weight |
| 2D | -weight |
| 1 or 3 | 0 (neutral) |

### Score

`FTFC score = sum(weighted contributions)` — range [-1.0, +1.0]

| Score | Direction |
|---|---|
| > +threshold | `bullish` |
| < -threshold | `bearish` |
| within ±threshold | `mixed` |

---

## 17. Pattern priority order

When multiple patterns match the same bar, assign the highest-priority label. Lower-priority patterns are gated by `strat_combo == 'none'`.

| Priority | Pattern | Rationale |
|---|---|---|
| 1 | 212 REV | 3-bar reversal after coil — highest conviction |
| 2 | 312 REV | 3-bar outside-digested reversal |
| 3 | 212 CON | 3-bar continuation after coil |
| 4 | 132 | 3-bar coil-explode-follow |
| 5 | 322 | 3-bar expansion-confirmed |
| 6 | 32 REV | 2-bar outside then directional |
| 7 | 22 REV | 2-bar consecutive reversal |
| 8 | 22 CON | 2-bar consecutive continuation |
| 9 | 11 / 111 | Multi-inside compression |
| 10 | Failed_2U / Failed_2D | Single-bar close-vs-open |
| 11 | Clean 2U / Clean 2D | No multi-bar context |

---

## 18. Bonus scoring

### Combo bonuses (per direction)

| Pattern | Label | CALL bonus | PUT bonus |
|---|---|---|---|
| Failed 2D | `f2d_bull_reversal` | +1.0 | -0.5 |
| Failed 2U | `f2u_bear_reversal` | -0.5 | +1.0 |
| 212 REV Up | `212_bull_reversal` | +1.0 | 0.0 |
| 212 REV Down | `212_bear_reversal` | 0.0 | +1.0 |
| 212 CON Up | `212_bull_continuation` | +0.75 | 0.0 |
| 212 CON Down | `212_bear_continuation` | 0.0 | +0.75 |
| 312 REV Up | `312_bull_reversal` | +1.0 | 0.0 |
| 312 REV Down | `312_bear_reversal` | 0.0 | +1.0 |
| 132U | `132_bull_continuation` | +1.0 | 0.0 |
| 132D | `132_bear_continuation` | 0.0 | +1.0 |
| 322U | `322_bull_continuation` | +0.75 | 0.0 |
| 322D | `322_bear_continuation` | 0.0 | +0.75 |
| 32 REV Up | `32_bull_reversal` | +0.75 | 0.0 |
| 32 REV Down | `32_bear_reversal` | 0.0 | +0.75 |
| 22 REV Up | `22_bull_reversal` | +1.0 | -0.5 |
| 22 REV Down | `22_bear_reversal` | -0.5 | +1.0 |
| 22 CON Up | `22_bull_continuation` | +0.5 | 0.0 |
| 22 CON Down | `22_bear_continuation` | 0.0 | +0.5 |
| Clean 2U | `clean_2u_bull` | +0.25 | 0.0 |
| Clean 2D | `clean_2d_bear` | 0.0 | +0.25 |
| Double Inside | `11_inside_compression` | 0.0 | 0.0 |
| Triple Inside | `111_inside_compression` | 0.0 | 0.0 |
| None / Type 1 / Type 3 | `none` | 0.0 | 0.0 |

Negative bonuses = pattern opposes your direction (warning to exit or reduce).

### FTFC bonus

| Condition | Bonus |
|---|---|
| FTFC score aligned with direction (≥ threshold) | +1.0 |
| FTFC score contradicts direction (≤ -threshold) | -1.0 |
| FTFC within threshold | 0.0 |

### ORB alignment bonus

| Condition | Bonus |
|---|---|
| ORB trend matches signal direction | +1.0 |
| Otherwise | 0.0 |

---

## 19. Naming conventions

### Candle classification values
`'1'`, `'2U'`, `'2D'`, `'3'`, `'X'` — uppercase directional letter.

### Column names
| Concept | Canonical name |
|---|---|
| Candle classification | `strat_candle` |
| Combo pattern | `strat_combo` |
| Setup forming | `strat_setup` |
| FTFC score | `ftfc_score` |
| FTFC direction | `ftfc_direction` |

### Combo label format
`<pattern>_<direction>_<kind>`

- pattern ∈ `{212, 312, 22, 32, 132, 322, f2u, f2d, 11, 111, clean_2u, clean_2d}`
- direction ∈ `{bull, bear, inside}`
- kind ∈ `{reversal, continuation, compression}`

### FTFC direction enum
`'bullish'`, `'bearish'`, `'mixed'`

### FTFC timeframe keys
`'5m'`, `'15m'`, `'1h'`, `'4h'`, `'12h'`, `'1d'`, `'1w'`

### Mask variable naming (inside `detect_combos`)
`mask_<pattern>_<direction>` — e.g. `mask_212_bull`, `mask_f2u`, `mask_22_bear`

---

## 20. Source-of-truth inventory

### Candle classification

| Value | Produced at | Consumed by |
|---|---|---|
| `'1'`, `'2U'`, `'2D'`, `'3'`, `'X'` | `lib/strat.py:classify_candle()` (line 42), `classify_series()` (line 63) | Stored as `strat_candle` column in `lib/strat.py:detect_combos()` output; written to `market_data_daily.strat_candle` by `gcp/fetchers/fetch_market_data.py:356`; read by `gcp/premarket_brief.py:349`, `gcp/signal_monitor.py:219`, `lib/agents/summarizers.py:177`, `platform/api/routers/dashboard.py:178` |

### Combo labels

| Label | Produced at | Consumed by |
|---|---|---|
| `212_bull_reversal` | `lib/strat.py:detect_combos()` | `lib/strat.py:get_strat_bonus()`, `lib/backtest.py:674`, `gcp/premarket_brief.py:543-544`, `gcp/signal_monitor.py:219`, `lib/agents/summarizers.py:178`, `lib/agents/ranker/signals.py:89` |
| *(all other combo labels)* | same | same consumers (they read `strat_combo` column opaquely or check `!= 'none'`) |

### Column names in Cloud SQL

| Table | Column | Type | Purpose |
|---|---|---|---|
| `market_data_daily` | `strat_candle` | `VARCHAR(10)` | Daily candle classification |
| `market_data_daily` | `strat_combo` | `VARCHAR(30)` | Combo pattern label |
| `market_data_daily` | `strat_setup` | `BOOLEAN` | Inside bar forming after directional |
| `market_data_daily` | `ftfc_score` | `DOUBLE PRECISION` | FTFC alignment score |
| `market_data_daily` | `ftfc_direction` | `VARCHAR(10)` | `bullish` / `bearish` / `mixed` |
| `premarket_analysis` | `strat_candle` | `VARCHAR(10)` | Daily candle (was `strat_daily`) |
| `premarket_analysis` | `strat_combo` | `VARCHAR(30)` | Combo label |
| `premarket_analysis` | `strat_setup` | `BOOLEAN` | Setup flag |
| `premarket_analysis` | `ftfc_score` | `DOUBLE PRECISION` | FTFC score |
| `premarket_analysis` | `ftfc_direction` | `VARCHAR(10)` | Direction |
| `signal_alerts` | `strat_combo` | `VARCHAR(30)` | Combo at signal time |
| `strat_levels` | *(new table)* | | Per-level classification, see plan |

### FTFC weights

| Key | Weight | Produced at | Consumed by |
|---|---|---|---|
| `5m` | 0.05 | `lib/strat.py:DEFAULT_WEIGHTS` | `lib/strat.py:calculate_ftfc()`, `lib/backtest.py` |
| `15m` | 0.10 | same | same |
| `1h` | 0.15 | same | same |
| `4h` | 0.15 | same | same |
| `12h` | 0.15 | same | same |
| `1d` | 0.30 | same | same |
| `1w` | 0.10 | same | same |

### RESAMPLE_RULES

| Key | Pandas rule | Defined at |
|---|---|---|
| `1m` | `1min` | `lib/data_loader.py:RESAMPLE_RULES` |
| `5m` | `5min` | same |
| `15m` | `15min` | same |
| `30m` | `30min` | same |
| `1h` | `1h` | same |
| `4h` | `4h` | same |
| `12h` | `12h` | same |
| `1d` | `1D` | same |
| `1w` | `W-FRI` | same |
| `1mo` | `ME` | same |

### Functions

| Function | File:Line | Purpose |
|---|---|---|
| `classify_candle()` | `lib/strat.py:42` | Single-bar 1/2U/2D/3 |
| `classify_series()` | `lib/strat.py:63` | Vectorized over DataFrame |
| `get_trigger_levels()` | `lib/strat.py:92` | Per-bar prev H/L |
| `detect_combos()` | `lib/strat.py:104` | All combo patterns + setup + compression |
| `calculate_ftfc()` | `lib/strat.py:212` | Multi-TF alignment score |
| `get_strat_bonus()` | `lib/strat.py:273` | Per-combo float bonus |
| `add_strat_columns()` | `lib/strat.py:346` | Convenience: classify + detect |
| `calculate_historical_levels()` | `lib/indicators.py:242` | Prev Day/Week/Month/Quarter/Year H/L/O/C |
| `calculate_orb()` | `lib/indicators.py:295` | Opening Range Breakout |
| `classify_level_strat()` | `lib/strat_levels.py` *(new)* | Level classification |
| `build_level_map()` | `lib/strat_levels.py` *(new)* | Full level map orchestrator |
| `format_levels_for_brief()` | `lib/strat_levels.py` *(new)* | Discord playbook format |

### Pine Script cross-reference

| Pine label | Python label | Pine file |
|---|---|---|
| `_is322BearishReversal` | `322_bear_continuation` | `tradingview-pine-scripts/strat-assistant-v2:58` |
| `_is322BullishReversal` | `322_bull_continuation` | same:59 |
| `_is122BearishRevStratReversal` | *(not implemented — separate 3-bar pattern)* | same:64 |
| `_is122BullishRevStratReversal` | *(not implemented)* | same:65 |
| `_is3BearishRevStratReversal` | `32_bear_reversal` | same:68 |
| `_is3BullishRevStratReversal` | `32_bull_reversal` | same:69 |

---

# Operational integration (added in PR #101)

The previous sections (§1–§17) describe the algorithms.
The next sections describe how those algorithms wire into the
deployed system — schedulers, persistence, naming conventions,
and source-of-truth file locations.

## 18. Catalyst-aware ORB selection

The premarket brief picks the ORB window per-ticker based on the
day's economic calendar:

- 8:30 ET high-impact event (NFP, CPI, retail sales) → `15m` (settle the
  initial reaction first)
- 10:00 ET high-impact event (ISM, consumer sentiment) → `30m`
- No high-impact event before 10:30 ET → `5m` (default scalp window)

Selection result is persisted to `premarket_analysis.recommended_orb_window`
and `recommended_orb_reason`.

Realtime ORB snapshots fire as separate Cloud Run executions of
`signal-monitor` with `--mode=orb-snapshot --window={5m,15m,30m}`,
scheduled at 9:35 / 9:45 / 10:00 ET respectively. Each snapshot posts
H/L/Mid/Range to Discord and stores the trigger levels for
intraday level-break detection.

---

## 19. Naming conventions (locked)

| Surface | Old | New |
|---|---|---|
| Result column | `strat_type` / `strat_daily` | `strat_candle` |
| Combo strings | `2D-1-2U_reversal` | `212_bull_reversal` |
| FTFC weight keys | `D` / `W` | `1d` / `1w` |
| FTFC keys present | `5m, 15m, 1h, D, W` | `5m, 15m, 1h, 4h, 12h, 1d, 1w` |
| Pine `122_RevStrat` reference | in `lib/strat.py` docstring | removed (wrong: that name is a 3-bar Pine pattern unrelated to Failed_2) |
| Mask variables | `mask_failed_2u` | `mask_f2u_bear` |
| Mask pattern | mixed | `mask_<pattern>_<direction>` — e.g. `mask_212_bull`, `mask_22_bear` |

---

## 20. Source-of-truth inventory

| Concept | Authoritative location | Status |
|---|---|---|
| Single-bar classification | `lib/strat.py` `StratClassifier.classify_candle` | ✅ inclusive |
| Vectorized classification | `lib/strat.py` `classify_series` | ✅ |
| Trigger levels | `lib/strat.py` `get_trigger_levels` | ✅ |
| Combo detection | `lib/strat.py` `detect_combos` | 🔧 refactored in this PR |
| FTFC scoring | `lib/strat.py` `calculate_ftfc` | 🔧 weights updated |
| Bonus scoring | `lib/strat.py` `get_strat_bonus` | 🔧 dict-based, float return |
| **Shared strat status helper** | `lib/strat.py` `compute_strat_status` | ✅ from PR #105 — single source for brief + LLM |
| Resample rules | `lib/data_loader.py` `RESAMPLE_RULES` | 🔧 4h/12h added, D/W renamed |
| Historical levels | `lib/indicators.py` `calculate_historical_levels` | 🔧 Quarter added |
| ORB | `lib/indicators.py` `calculate_orb` | ✅ |
| **Levels engine** | `lib/strat_levels.py` | 🆕 this PR |
| **`strat_levels` table** | `gcp/schema.sql` | 🆕 this PR |
| Brief playbook | `gcp/premarket_brief.py` | 🔧 calls `compute_strat_status` + `format_levels_for_brief` |
| Real-time ORB / level breaks | `gcp/signal_monitor.py` | 🔧 `check_level_breaks()` + ORB snapshot mode |
| Watchlist source of truth | `watchlists` Cloud SQL table (PR #108) | ✅ shared with insight-pipeline + fetchers |
| Pine v2 mirror | `tradingview-pine-scripts/strat-assistant-v2` | (out of scope) |
