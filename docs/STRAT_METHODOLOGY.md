# The Strat — Methodology Reference

**Version:** 2.0 (post-rename, post-Failed_2-fix)
**Companion doc:** `docs/STRAT_IMPLEMENTATION_PLAN.md`
**Source of truth:** Rob Smith's Strat methodology
**Scope:** Pattern definitions, level classification, FTFC scoring, bonus rules, and a complete source-of-truth inventory mapping every name to its file:line.

---

## Variables used throughout

```
H     = current bar high
L     = current bar low
O     = current bar open
C     = current bar close
pH    = previous bar high
pL    = previous bar low
pH2   = two bars ago high
pL2   = two bars ago low
type  = current bar strat classification
prev  = previous bar strat classification
prev2 = two bars ago strat classification
```

---

## 1. Base candle classification (single bar vs previous bar)

These four labels are exhaustive — every bar (after the first) gets exactly one.

### Inside Bar (Type 1)
```
H <= pH  AND  L >= pL
```
Current bar entirely within previous bar's range. Compression. Breakout pending.

**Note: inclusive inequalities.** Equal high or equal low is still "inside" — Rob Smith's definition treats no-break as inside.

### Directional Up (Type 2U)
```
H > pH  AND  L >= pL
```
Broke above previous high without breaking previous low. Bullish momentum.

### Directional Down (Type 2D)
```
L < pL  AND  H <= pH
```
Broke below previous low without breaking previous high. Bearish momentum.

### Outside Bar (Type 3)
```
H > pH  AND  L < pL
```
Broke both sides of previous bar's range. Volatility expansion.

---

## 2. Failed patterns (single bar, close vs open)

A "failed" candle breaks one side of the previous range but closes in the opposite direction of the break. **The test is close vs open** — bullish/bearish refers to the bar's body color, not its position relative to prev range.

### Failed 2U (`f2u_bear_reversal`) — bearish reversal signal
```
H > pH  AND  L >= pL  AND  C < O
```
Broke above previous high but closed bearish (red body). Bias: **PUT**.

### Failed 2D (`f2d_bull_reversal`) — bullish reversal signal
```
L < pL  AND  H <= pH  AND  C > O
```
Broke below previous low but closed bullish (green body). Bias: **CALL**.

### Clean 2U (`clean_2u_bull`) — confirmed bullish
```
H > pH  AND  L >= pL  AND  C >= O
```
Broke above previous high and closed bullish (or doji). Bias: **CALL**.

### Clean 2D (`clean_2d_bear`) — confirmed bearish
```
L < pL  AND  H <= pH  AND  C <= O
```
Broke below previous low and closed bearish (or doji). Bias: **PUT**.

### Doji edge case
`C == O` is treated as clean (not failed). Strict inequality on the failed test handles this automatically.

---

## 3. Multi-inside compression patterns

### Double Inside (`11_inside_compression`)
```
type == '1'  AND  prev == '1'
```
Two consecutive inside bars. Deeper compression than single inside.

### Triple Inside (`111_inside_compression`)
```
type == '1'  AND  prev == '1'  AND  prev2 == '1'
```
Three consecutive inside bars. Maximum compression. Explosive move imminent — trade the break in either direction.

Example: AYCE MSFT triple inside break below 520.15.

---

## 4. Two-bar combos (consecutive directional, no inside between)

### 22 REV Up (`22_bull_reversal`) — bias **CALL**, bonus **+1.0**
```
prev == '2D'  AND  type == '2U'
```
Down move reversed up. Display: "22 REV to the upside".

### 22 REV Down (`22_bear_reversal`) — bias **PUT**, bonus **+1.0**
```
prev == '2U'  AND  type == '2D'
```
Up move reversed down. Display: "22 REV to the downside".

### 22 CON Up (`22_bull_continuation`) — bias **CALL**, bonus **+0.5**
```
prev == '2U'  AND  type == '2U'
```
Sustained bullish momentum. Display: "22 CON to the upside".

### 22 CON Down (`22_bear_continuation`) — bias **PUT**, bonus **+0.5**
```
prev == '2D'  AND  type == '2D'
```
Sustained bearish momentum. Display: "22 CON to the downside".

---

## 5. Three-bar 2-1-2 combos (with inside-bar coil)

### 212 REV Up (`212_bull_reversal`) — bias **CALL**, bonus **+1.0**
```
prev2 == '2D'  AND  prev == '1'  AND  type == '2U'  AND  H > prev1.High
```
Moved down, compressed, reversed up. Highest-conviction reversal. Display: "212 REV to the upside".

Example: BABA "5D + 4D 212 REV to the upside".

### 212 REV Down (`212_bear_reversal`) — bias **PUT**, bonus **+1.0**
```
prev2 == '2U'  AND  prev == '1'  AND  type == '2D'  AND  L < prev1.Low
```

### 212 CON Up (`212_bull_continuation`) — bias **CALL**, bonus **+0.75**
```
prev2 == '2U'  AND  prev == '1'  AND  type == '2U'  AND  H > prev1.High
```
Moved up, paused, continued up.

### 212 CON Down (`212_bear_continuation`) — bias **PUT**, bonus **+0.75**
```
prev2 == '2D'  AND  prev == '1'  AND  type == '2D'  AND  L < prev1.Low
```

---

## 6. Three-bar 3-1-2 combos (outside bar digested)

### 312 REV Up (`312_bull_reversal`) — bias **CALL**, bonus **+1.0**
```
prev2 == '3'  AND  prev == '1'  AND  type == '2U'  AND  H > prev1.High
```

### 312 REV Down (`312_bear_reversal`) — bias **PUT**, bonus **+1.0**
```
prev2 == '3'  AND  prev == '1'  AND  type == '2D'  AND  L < prev1.Low
```

---

## 7. Three-bar 1-3-2 combos (coil → explode → follow)

### 132U (`132_bull_continuation`) — bias **CALL**, bonus **+1.0**
```
prev2 == '1'  AND  prev == '3'  AND  type == '2U'
```
Inside compressed, outside released, 2U confirms. High-energy continuation.

Example: BABA "2D 132U to the upside".

### 132D (`132_bear_continuation`) — bias **PUT**, bonus **+1.0**
```
prev2 == '1'  AND  prev == '3'  AND  type == '2D'
```

---

## 8. Three-bar 3-2-2 combos (expansion then direction)

### 322U (`322_bull_continuation`) — bias **CALL**, bonus **+0.75**
```
prev2 == '3'  AND  prev == '2U'  AND  type == '2U'
```
Outside bar then two consecutive bullish. Expansion resolved bullish.

Example: AYCE IWM "322 first live + Daily failed directional to the upside".

### 322D (`322_bear_continuation`) — bias **PUT**, bonus **+0.75**
```
prev2 == '3'  AND  prev == '2D'  AND  type == '2D'
```

---

## 9. Two-bar 3-2 combos (outside then directional)

### 32 REV Up (`32_bull_reversal`) — bias **CALL**, bonus **+0.75**
```
prev == '3'  AND  type == '2U'
```
Outside bar followed by bullish directional. Volatility resolved bullish.

### 32 REV Down (`32_bear_reversal`) — bias **PUT**, bonus **+0.75**
```
prev == '3'  AND  type == '2D'
```

---

## 10. Level classification (current period vs previous period)

Classifies the relationship between the current period's price action and the previous period's range. Used for dynamic level coloring and brief output.

```
cH  = current period high (live)
cL  = current period low (live)
cO  = current period open (fixed at period start)
cC  = current price / close
pH  = previous period high (fixed)
pL  = previous period low (fixed)
```

| Class | Test | Color | Meaning |
|---|---|---|---|
| Inside (`1`) | `cH <= pH AND cL >= pL` | gray | Current period within prev range |
| 2U | `cH > pH AND cL >= pL AND cC >= cO` | aqua / green | Broke above prev high, currently bullish |
| Failed 2U | `cH > pH AND cL >= pL AND cC < cO` | fuchsia / red warning | Broke above prev high but reversed below open |
| 2D | `cL < pL AND cH <= pH AND cC <= cO` | red / dark | Broke below prev low, currently bearish |
| Failed 2D | `cL < pL AND cH <= pH AND cC > cO` | lime / yellow warning | Broke below prev low but reversed above open |
| Outside (`3`) | `cH > pH AND cL < pL` | purple / dark purple | Both sides broken |

**Inclusive inequalities** match the base candle classification — required for exhaustiveness.

Applied to each timeframe pair:
- Current Day Open vs Previous Day H/L
- Current Week Open vs Previous Week H/L
- Current Month Open vs Previous Month H/L
- Current Quarter Open vs Previous Quarter H/L
- Current Year Open vs Previous Year H/L

---

## 11. Level hierarchy

### Previous levels (fixed, no repainting)
| Code | Name | Width |
|---|---|---|
| `PYH` / `PYL` | Previous Year High / Low | widest |
| `PQH` / `PQL` | Previous Quarter High / Low | |
| `PMH` / `PML` | Previous Month High / Low | |
| `PWH` / `PWL` | Previous Week High / Low | |
| `PDH` / `PDL` | Previous Day High / Low | most-traded |

### Current levels (live, repaints)
| Code | Name |
|---|---|
| `CYO` | Current Year Open |
| `CQO` | Current Quarter Open |
| `CMO` | Current Month Open |
| `CWO` | Current Week Open |
| `CDO` | Current Day Open |

### Intraday levels
| Code | Name |
|---|---|
| `ORB_H` / `ORB_L` | Opening Range High / Low (5m, 15m, or 30m) |
| `HOD` / `LOD` | High / Low of Day (live) |
| `PMK_H` / `PMK_L` | Pre-market High / Low |

### Derived levels
| Code | Name |
|---|---|
| `GAP_H` / `GAP_L` | Unfilled gap boundaries (magnetic targets) |
| `PMG zone` | Pivot Machine Gun cluster (≥2 levels within 0.15%) |

---

## 12. PMG (Pivot Machine Gun)

Two interpretations — both valid, both implemented:

### Spatial PMG (level cluster)
Two or more levels from different timeframes clustering within a tight band (default 0.15%).

```python
for each level L[i]:
    cluster = {L[i]}
    for each level L[j] where j > i:
        if abs(L[j].price - L[i].price) / L[i].price <= 0.0015:
            cluster.add(L[j])
    if len(cluster) >= 2:
        PMG zone at mean(cluster prices)
```

**Strength = count + (unique_timeframes - 1) * 0.5**

Example: PDL=262.14, PWL=262.30, gap fill=262.10. count=3, timeframes={day, week}=2. Strength = 3 + 0.5 = 3.5.

### Temporal PMG (consecutive pivots)
N consecutive higher highs (`bull` direction) or lower lows (`bear`). AYCE's "daily PMG" = consecutive days of new pivots running into a level cluster.

---

## 13. Room to run

Distance from current price to next level in trade direction.

```
CALL: (next_level_above - current_price) / current_price * 100
PUT:  (current_price - next_level_below) / current_price * 100
```

**Minimum threshold: 0.20%.** Below this the R:R is poor — wait for level break and target T2 instead.

---

## 14. Trigger level identification (premarket brief)

Brief output format:
```
CALLS above 265.17 (PDH)
  Stop: 262.14 (PDL)
  T1: 266.89 (PWH) — 0.65% room (R:R 1.7)
  T2: 268.50 (PMH) — 1.26% room (R:R 4.1)
```

### Logic
- **CALL trigger** = first significant level above current price (usually PDH, sometimes ORB_H or CWO)
- **CALL stop** = first significant level below current price (usually PDL)
- **CALL targets** = subsequent levels above the trigger, ordered by price
- **PUT trigger / stop / targets** mirror

### Bias adjustment
- Daily bias **bearish** (Failed 2U, 22 REV Down, etc.): primary = PUTS below PDL; secondary = "CALLS above PDH — only if bias denied"
- Daily bias **bullish**: primary = CALLS above PDH; secondary = "PUTS below PDL — only if bias denied"
- Daily bias **neutral**: both presented equally; "trade what triggers"

The combo and daily strat class must be passed into `identify_triggers()` so the reasoning string includes "212 REV on Daily, CALLS above PDH" — not just "CALLS above PDH".

---

## 15. Multi-day candle aggregation

Construct N-day candles from daily OHLCV:

```
agg_open  = first bar's open
agg_high  = max(all bars' highs)
agg_low   = min(all bars' lows)
agg_close = last bar's close
```

Then classify the aggregated candle using §1 rules against its previous N-day candle.

Standard periods: **2D, 4D, 5D, 8D, 10D, 11D**.

Example: MSFT "below 517.55 triggers the 11D 22 REV to the downside" — the 11-day aggregated sequence shows a 22 REV pattern.

---

## 16. Full Timeframe Continuity (FTFC)

All timeframes aligned in the same direction.

### Weights (sum to 1.00)
| Timeframe | Key | Weight |
|---|---|---|
| 5-minute | `5m` | 0.05 |
| 15-minute | `15m` | 0.10 |
| 1-hour | `1h` | 0.15 |
| 4-hour | `4h` | 0.15 |
| 12-hour | `12h` | 0.15 |
| 1-day | `1d` | 0.30 |
| 1-week | `1w` | 0.10 |

### Per-timeframe contribution
- 2U → +weight
- 2D → -weight
- Type 1 or 3 → 0 (neutral)

### Score
```
FTFC = sum(weighted contributions)
range: [-1.0, +1.0]
```
- `+1.0` = all timeframes bullish (max conviction CALL)
- `-1.0` = all timeframes bearish (max conviction PUT)
- `0.0` = mixed / neutral

### Direction string
- `bullish` if score > +threshold
- `bearish` if score < -threshold
- `mixed` otherwise (default threshold 0.30)

### Bonus contribution
- Full continuity (|score| >= 0.8) → +1.0
- Partial continuity (0.5 ≤ |score| < 0.8) → +0.5
- No continuity (|score| < 0.5) → 0.0
- Strong contradiction (sign opposes signal direction, |score| >= threshold) → -1.0

---

## 17. Pattern priority order

When multiple patterns match the same bar, assign the highest-priority label using an "empty" mask to prevent overwrites. **Multi-bar patterns beat single-bar Failed_2** — they have more context and higher conviction.

| # | Pattern | Reason |
|---|---|---|
| 1 | 212 REV (3-bar reversal after coil) | Highest conviction reversal |
| 2 | 312 REV (outside-digested reversal) | Volatility absorbed then directional |
| 3 | 212 CON (3-bar continuation after pause) | Trend continuation after consolidation |
| 4 | 132 (coil-explode-follow) | High-energy 3-bar pattern |
| 5 | 322 (expansion-confirmed) | Outside resolved into 2 confirming bars |
| 6 | 32 REV (outside then directional) | 2-bar volatility resolution |
| 7 | 22 REV (consecutive opposite directional) | 2-bar reversal |
| 8 | 22 CON (consecutive same directional) | 2-bar continuation |
| 9 | 111 inside compression | Triple inside — pending breakout |
| 10 | 11 inside compression | Double inside |
| 11 | Failed 2U / Failed 2D (single-bar close-vs-open) | Fallback when no multi-bar pattern |
| 12 | Clean 2U / Clean 2D (single-bar bullish/bearish) | Lowest — no pattern context |
| 13 | none (Type 1 or 3 with no multi-bar pattern) | Default |

### Rationale
A bar matching both 22 REV and Failed_2U gets `22_*_reversal`. The 22 sequence has more context (knows the prior bar was directional and reversed), Failed_2U is just "this bar broke high but closed bearish" — same information but less specific. Existing code that overrode multi-bar with Failed_2 was wrong.

---

## 18. Bonus scoring

Per-combo bonus values added to base signal score. Returns `float`.

| Pattern | CALL bonus | PUT bonus |
|---|---:|---:|
| `f2d_bull_reversal` | +1.0 | -0.5 |
| `f2u_bear_reversal` | -0.5 | +1.0 |
| `212_bull_reversal` | +1.0 | 0.0 |
| `212_bear_reversal` | 0.0 | +1.0 |
| `212_bull_continuation` | +0.75 | 0.0 |
| `212_bear_continuation` | 0.0 | +0.75 |
| `312_bull_reversal` | +1.0 | 0.0 |
| `312_bear_reversal` | 0.0 | +1.0 |
| `132_bull_continuation` | +1.0 | 0.0 |
| `132_bear_continuation` | 0.0 | +1.0 |
| `322_bull_continuation` | +0.75 | 0.0 |
| `322_bear_continuation` | 0.0 | +0.75 |
| `32_bull_reversal` | +0.75 | 0.0 |
| `32_bear_reversal` | 0.0 | +0.75 |
| `22_bull_reversal` | +1.0 | -0.5 |
| `22_bear_reversal` | -0.5 | +1.0 |
| `22_bull_continuation` | +0.5 | 0.0 |
| `22_bear_continuation` | 0.0 | +0.5 |
| `clean_2u_bull` | +0.25 | 0.0 |
| `clean_2d_bear` | 0.0 | +0.25 |
| `11_inside_compression` | 0.0 | 0.0 |
| `111_inside_compression` | 0.0 | 0.0 |
| `none` | 0.0 | 0.0 |

Negative bonuses fire when the detected pattern opposes your trade direction — a 22 REV forming against you is a warning to reduce or exit. FTFC alignment and ORB alignment are scored separately and additive.

---

## 19. Naming conventions (canonical)

These are the names every part of the codebase must use.

### Candle classification value
String in `{'1', '2U', '2D', '3', 'X'}`. Uppercase directional letter. `'X'` for the first bar with no prior.

### Column for candle classification
**`strat_candle`** in every layer:
- `lib/strat.py` DataFrame output
- `market_data_daily` Cloud SQL column
- `premarket_analysis` Cloud SQL column
- `signal_alerts` Cloud SQL column
- API JSON field
- TypeScript interface

(Old names `strat_type` and `strat_daily` are deprecated and removed in Commit 2/3.)

### Combo string format
`<pattern>_<direction>_<kind>`

- `<pattern>` ∈ `{212, 312, 132, 322, 32, 22, 11, 111, f2u, f2d, clean_2u, clean_2d}`
- `<direction>` ∈ `{bull, bear}`
- `<kind>` ∈ `{reversal, continuation, compression}`

Examples: `212_bull_reversal`, `f2u_bear_reversal`, `132_bear_continuation`, `11_inside_compression`.

`'none'` is reserved for Type 1 or Type 3 bars without a multi-bar pattern.

### FTFC timeframe keys
Lowercase letter+unit: `5m, 15m, 30m, 1h, 4h, 12h, 1d, 1w`. (Old `D` / `W` deprecated.)

### Resample rules dict
`lib/data_loader.py:RESAMPLE_RULES` keys match FTFC timeframe keys.

### FTFC direction enum
`{'bullish', 'bearish', 'mixed'}`. Note `mixed` not `neutral`.

### Function name verbs
- `classify_*` for labelers
- `detect_*` for combo finders
- `calculate_*` for math
- `compute_*` for level-engine specifics (`compute_previous_levels`, `compute_room_to_run`)
- `get_*` for accessors
- `add_*` for DataFrame mutators (in-place column additions)
- `build_*` for orchestrators (`build_level_map`)
- `format_*` for string output (`format_levels_for_brief`)
- `persist_*` for SQL writes (`persist_level_map`)

### Mask variable names (inside `detect_combos`)
`mask_<pattern>_<direction>` — e.g. `mask_212_bull`, `mask_22_bear`, `mask_322_bull`, `mask_f2u`, `mask_f2d`, `mask_11`, `mask_111`.

### Level naming
- Previous: `PYH/PYL/PQH/PQL/PMH/PML/PWH/PWL/PDH/PDL`
- Current opens: `CYO/CQO/CMO/CWO/CDO`
- Intraday: `ORB_H/ORB_L/HOD/LOD/PMK_H/PMK_L`
- Derived: `GAP_H/GAP_L` (per gap, dated suffix)

---

## 20. Source-of-truth inventory

Every Strat-related name in the codebase, where it lives, and its current vs. canonical status. Use this as the single reference when grepping or refactoring.

### 20.1 Candle classification labels

| String | Status | First defined | Read at |
|---|---|---|---|
| `'1'` | canonical | `lib/strat.py:55` | every consumer |
| `'2U'` | canonical | `lib/strat.py:57` | every consumer |
| `'2D'` | canonical | `lib/strat.py:59` | every consumer |
| `'3'` | canonical | `lib/strat.py:55, 80` | every consumer |
| `'X'` | canonical | `lib/strat.py:76, 83` | first-bar marker only |

### 20.2 Candle classification column name

| Name | Status | Defined at | Read by |
|---|---|---|---|
| `strat_candle` (canonical, post-rename) | target | `lib/strat.py` (will rename from `strat_type`); `gcp/schema.sql:69` (already correct in `market_data_daily`) | All consumers after Commit 3 |
| `strat_type` | DEPRECATED | `lib/strat.py:127` (DataFrame output today); 7 analysis scripts read this | Rename in Commit 2 |
| `strat_daily` | DEPRECATED | `gcp/schema.sql:628`; `gcp/premarket_brief.py:406-408, 542, 830` | Rename in Commit 3 |

Read sites for `strat_type` (rename in Commit 3):
- `scripts/analysis/phase2_indicator_confirmation.py:496`
- `scripts/analysis/phase3_orb_strategies.py:180`
- `scripts/analysis/phase4_setup_discovery.py:709, 732`
- `scripts/analysis/phase5_additional_dimensions.py:52, 168, 272, 427, 642`
- `scripts/analysis/phase6_playbook.py:713`

Read sites for `strat_daily` (rename in Commit 3):
- `gcp/premarket_brief.py:406, 542, 830`
- `platform/src/routes/DashboardPage.tsx:842, 844` (currently has `||` fallback — drop after rename)

Read sites for `strat_candle` (already correct):
- `lib/data_loader.py:255`
- `lib/agents/summarizers.py:153, 162, 177`
- `gcp/fetchers/fetch_market_data.py:356`
- `platform/api/routers/dashboard.py:136, 178`
- `platform/src/routes/DashboardPage.tsx:51, 842`

### 20.3 Combo labels

Mapping from current label → canonical label. All renames happen in Commit 2.

| Current label | Canonical label | First defined | Bonus rules |
|---|---|---|---|
| `'2D-1-2U_reversal'` | `'212_bull_reversal'` | `lib/strat.py:137` | CALL +1.0 |
| `'2U-1-2D_reversal'` | `'212_bear_reversal'` | `lib/strat.py:141` | PUT +1.0 |
| `'3-1-2U_reversal'` | `'312_bull_reversal'` | `lib/strat.py:145` | CALL +1.0 |
| `'3-1-2D_reversal'` | `'312_bear_reversal'` | `lib/strat.py:149` | PUT +1.0 |
| `'Failed_2U'` | `'f2u_bear_reversal'` | `lib/strat.py:167` | PUT +1.0, CALL -0.5 |
| `'Failed_2D'` | `'f2d_bull_reversal'` | `lib/strat.py:168` | CALL +1.0, PUT -0.5 |
| `'2U-1-2U_continuation'` | `'212_bull_continuation'` | `lib/strat.py:176` | CALL +0.75 |
| `'2D-1-2D_continuation'` | `'212_bear_continuation'` | `lib/strat.py:181` | PUT +0.75 |
| `'2U_continuation'` | `'22_bull_continuation'` | `lib/strat.py:188` | CALL +0.5 |
| `'2D_continuation'` | `'22_bear_continuation'` | `lib/strat.py:189` | PUT +0.5 |
| `'3-2U_reversal'` | `'32_bull_reversal'` | `lib/strat.py:198` | CALL +0.75 |
| `'3-2D_reversal'` | `'32_bear_reversal'` | `lib/strat.py:197` | PUT +0.75 |
| (new) | `'22_bull_reversal'` | (Commit 2) | CALL +1.0, PUT -0.5 |
| (new) | `'22_bear_reversal'` | (Commit 2) | PUT +1.0, CALL -0.5 |
| (new) | `'132_bull_continuation'` | (Commit 2) | CALL +1.0 |
| (new) | `'132_bear_continuation'` | (Commit 2) | PUT +1.0 |
| (new) | `'322_bull_continuation'` | (Commit 2) | CALL +0.75 |
| (new) | `'322_bear_continuation'` | (Commit 2) | PUT +0.75 |
| (new) | `'11_inside_compression'` | (Commit 2) | 0.0 |
| (new) | `'111_inside_compression'` | (Commit 2) | 0.0 |
| (new) | `'clean_2u_bull'` | (Commit 2) | CALL +0.25 |
| (new) | `'clean_2d_bear'` | (Commit 2) | PUT +0.25 |
| `'none'` | unchanged | `lib/strat.py:128` | 0.0 |

External read sites for combo strings (need updating in Commit 3 wherever string literals appear):
- `lib/agents/prompts.py:42` — example combo in prompt template
- `lib/agents/schema.py:74` — Pydantic field description
- `lib/agents/ranker/signals.py:55, 89` — SQL SELECT + dict key (column name only, opaque value)
- `lib/agents/summarizers.py:178` — opaque value, no string-literal check
- `lib/backtest.py:674-675` — opaque combo passed to bonus scorer
- `gcp/premarket_brief.py:543` — `if d['strat_combo'] != 'none':` — opaque comparison
- `gcp/signal_monitor.py:219` — opaque
- `tests/test_strat.py` — full rewrite for new strings (Commit 2)

### 20.4 FTFC keys

| Key | Status | Defined at | Used in |
|---|---|---|---|
| `5m` | canonical | `lib/strat.py:23` | DEFAULT_WEIGHTS, RESAMPLE_RULES, tests |
| `15m` | canonical | `lib/strat.py:24` | same |
| `30m` | canonical | `lib/data_loader.py:44` | RESAMPLE_RULES only (not in FTFC weights) |
| `1h` | canonical | `lib/strat.py:25` | DEFAULT_WEIGHTS, RESAMPLE_RULES |
| `4h` (new) | target | (Commit 2) | DEFAULT_WEIGHTS, RESAMPLE_RULES |
| `12h` (new) | target | (Commit 2) | DEFAULT_WEIGHTS, RESAMPLE_RULES |
| `D` | DEPRECATED | `lib/strat.py:26`; `lib/data_loader.py:46` | rename → `1d` in Commit 2 |
| `W` | DEPRECATED | `lib/strat.py:27`; `lib/data_loader.py:47` | rename → `1w` in Commit 2 |
| `M` | DEPRECATED | `lib/data_loader.py:48` | rename → `1mo` in Commit 2 |

### 20.5 FTFC direction values

| Value | Defined at | Read at |
|---|---|---|
| `'bullish'` | `lib/strat.py:261` | `gcp/premarket_brief.py:467, 475` |
| `'bearish'` | `lib/strat.py:263` | same |
| `'mixed'` | `lib/strat.py:265` | same |

### 20.6 Schema columns

| Column | Table | Status | Source line |
|---|---|---|---|
| `strat_candle` | `market_data_daily` | canonical | `gcp/schema.sql:69` |
| `strat_combo` | `market_data_daily` | canonical | `gcp/schema.sql:70` |
| `strat_setup` | `market_data_daily` | canonical | `gcp/schema.sql:71` |
| `ftfc_score` | `market_data_daily` | canonical | `gcp/schema.sql:72` |
| `ftfc_direction` | `market_data_daily` | canonical | `gcp/schema.sql:73` |
| `strat_combo` | `signal_alerts` | canonical | `gcp/schema.sql:575` |
| `ftfc_score` | `signal_alerts` | canonical | `gcp/schema.sql:576` |
| `level_broken` (new) | `signal_alerts` | target (Commit 7) | tba |
| `strat_daily` | `premarket_analysis` | DEPRECATED → `strat_candle` | `gcp/schema.sql:628` |
| `strat_combo` | `premarket_analysis` | canonical | `gcp/schema.sql:629` |
| `strat_setup` | `premarket_analysis` | canonical | `gcp/schema.sql:630` |
| `ftfc_score` | `premarket_analysis` | canonical | `gcp/schema.sql:631` |
| `ftfc_direction` | `premarket_analysis` | canonical | `gcp/schema.sql:632` |
| `prev_quarter_*` (new, ~10 cols) | `market_data_daily` | target (Commit 4) | tba |
| `recommended_orb_window` (new) | `premarket_analysis` | target (Commit 6) | tba |
| `recommended_orb_reason` (new) | `premarket_analysis` | target (Commit 6) | tba |

### 20.7 New table

| Table | Status | Commit |
|---|---|---|
| `strat_levels (ticker, as_of, level_name, price, timeframe, level_type, strat_class, is_current, period_label)` | target | Commit 5 |

### 20.8 Functions in `lib/strat.py`

| Function | Line | Status |
|---|---|---|
| `StratClassifier.classify_candle` | 42 | canonical |
| `StratClassifier.classify_series` | 63 | canonical |
| `StratClassifier.get_trigger_levels` | 92 | canonical (per-bar prev H/L) |
| `StratClassifier.detect_combos` | 104 | full rewrite Commit 2 |
| `StratClassifier.calculate_ftfc` | 212 | weight dict update Commit 2 |
| `StratClassifier.get_strat_bonus` | 273 | full rewrite Commit 2 (dict-based, float return) |
| `StratClassifier.add_strat_columns` | 346 | column rename Commit 2 |

### 20.9 Levels engine functions (new in Commit 5)

| Function | File | Notes |
|---|---|---|
| `classify_level_strat` | `lib/strat_levels.py` | Calls `StratClassifier.classify_candle` for base, adds Failed_2 |
| `compute_previous_levels` | `lib/strat_levels.py` | Reads `Prev_Day_*` etc. from `market_data_daily` — does NOT recompute |
| `compute_current_levels` | `lib/strat_levels.py` | |
| `compute_gap_levels` | `lib/strat_levels.py` | Lookback 20 days, returns unfilled gaps |
| `detect_level_clusters` | `lib/strat_levels.py` | Spatial PMG, tolerance 0.15% default |
| `detect_pmg_temporal` | `lib/strat_levels.py` | N consecutive higher-highs / lower-lows |
| `compute_room_to_run` | `lib/strat_levels.py` | Min 0.20% threshold |
| `compute_risk_reward` | `lib/strat_levels.py` | (entry, stop, target) → float ratio |
| `identify_triggers` | `lib/strat_levels.py` | Wires `daily_strat_class` + `combo` into reasoning |
| `build_level_map` | `lib/strat_levels.py` | Top-level orchestrator |
| `format_levels_for_brief` | `lib/strat_levels.py` | Discord playbook string |
| `persist_level_map` | `lib/strat_levels.py` | Writes to `strat_levels` table |

### 20.10 Levels columns in `market_data_daily` (existing)

`lib/indicators.py:242-288` `calculate_historical_levels()` produces ~80 columns per period. Per period, the suffix pattern is:

```
Prev_<Period>_High
Prev_<Period>_Low
Prev_<Period>_Open
Prev_<Period>_Close
Prev_<Period>_HL_Mid
Prev_<Period>_OC_Mid
<each-of-above>_Pct        (price-position percentage)
At_<each-of-above>         (within 0.1% flag)
Broke_Prev_<Period>_High   (close beyond, flag)
Broke_Prev_<Period>_Low    (close beyond, flag)
```

Periods today: `Day`, `Week`, `Month`, `Year`. Adding `Quarter` in Commit 4.

### 20.11 ORB columns

`lib/indicators.py:295` `calculate_orb()` produces per window (`5m`, `15m`, `30m`):

```
ORB_<label>_High / Low / Range / Mid
ORB_<label>_Broke_High / Broke_Low / Within_Range / Trend / Distance
```

### 20.12 Test files

| File | Coverage |
|---|---|
| `tests/test_strat.py` | Full rewrite Commit 2 — every new pattern + drift tests |
| `tests/test_strat_levels.py` | New in Commit 5 — every levels function + drift guard against `market_data_daily` |
| `tests/test_indicators.py` | Quarter test added in Commit 4 |
| `tests/test_premarket_brief.py` | Brief format + ORB selection tests in Commit 6 |
| `tests/test_signal_monitor.py` | Level-break dedup + ORB snapshot tests in Commit 7 |
| `tests/conftest.py` | `known_strat_sequence`, `strat_combo_sequence`, `sample_ohlcv`, `sample_daily` fixtures — reused, may add new fixtures for multi-inside |

### 20.13 Pine Script reference

`tradingview-pine-scripts/strat-assistant-v2`:

| Pine variable | Python equivalent |
|---|---|
| `_is322BearishReversal` (line 58) | `322_bear_continuation` (Commit 2) |
| `_is322BullishReversal` (line 59) | `322_bull_continuation` (Commit 2) |
| `_is122BearishRevStratReversal` (line 64, 214) | NOT a Failed_2 — different 3-bar pattern. Optional: add as `122_bear_revstrat` later |
| `_is122BullishRevStratReversal` (line 65, 215) | Optional: `122_bull_revstrat` |
| `_is3BearishRevStratReversal` (line 68, 218) | `32_bear_reversal` |
| `_is3BullishRevStratReversal` (line 69, 219) | `32_bull_reversal` |

Pine `122_RevStrat` is **not** the same as Python single-bar Failed_2. Existing `lib/strat.py:155-161` docstring conflates them — to be removed in Commit 2.

---

## Validation against current code

This document is the source of truth. Where it disagrees with current code:

| Area | Current code | This doc | Resolution |
|---|---|---|---|
| Failed_2 test | `close <= prev_high` (`lib/strat.py:164-168`) | `close < open` | Commit 2 changes code to match doc |
| Failed_2 priority | Overrides multi-bar (`lib/strat.py:166-167` no `none` gate) | Lowest priority | Commit 2 adds `none` gate |
| Inside bar inequality | Inclusive (`lib/strat.py:77`) | Inclusive | Already aligned |
| Combo string format | `2D-1-2U_reversal` style | `212_bull_reversal` style | Commit 2 renames |
| FTFC weights | 5 keys, no 4h/12h (`lib/strat.py:22-28`) | 7 keys with 4h+12h | Commit 2 expands |
| FTFC direction enum | `bullish`/`bearish`/`mixed` | same | Already aligned |
| Bonus return type | `int` (`lib/strat.py:295`) | `float` | Commit 2 changes |
| Combo bonus method | tuple membership | per-combo dict | Commit 2 changes |
| Multi-inside | not present | `11_inside_compression`, `111_inside_compression` | Commit 2 adds |
| Quarter level | not computed | required | Commit 4 adds |
| Levels engine | not present | full module | Commit 5 adds |
