# The Strat Methodology — Reference Spec

**Status:** Source of truth for `lib/strat.py`, `lib/strat_levels.py`, and every
consumer (FastAPI router, AI agents, CLI scripts, premarket brief, signal
monitor). When code disagrees with this document, the document wins —
update the code.

---

## 1. Single-bar candle classification

Every bar is classified relative to the **prior** bar's High and Low.

| Type | Definition | Reading |
|---|---|---|
| `1` | `H ≤ pH AND L ≥ pL` | Inside bar — compression / consolidation |
| `2U` | `H > pH AND L ≥ pL` | Higher-high, did not undercut prior low — directional up |
| `2D` | `L < pL AND H ≤ pH` | Lower-low, did not exceed prior high — directional down |
| `3` | `H > pH AND L < pL` | Outside bar — both sides taken; broadest range |

**Inclusive inequalities** are intentional. Equality on either side keeps the
classification exhaustive — every non-first bar receives exactly one label.
The first bar of any series has no prior and is labelled `X`.

### Failed_2 sub-classification

A `2U` or `2D` bar can additionally be a **Failed_2** when the close
contradicts the directional break:

| Sub-type | Required structure | Close-vs-open rule |
|---|---|---|
| `f2u` (Failed 2U → bearish reversal) | bar is a `2U` | `Close < Open` |
| `f2d` (Failed 2D → bullish reversal) | bar is a `2D` | `Close > Open` |

Doji case (`Close == Open`) on a `2U/2D` is **not** failed — it stays a
clean `2u_bull` / `2d_bear` (see §17).

---

## 2. Combo patterns (multi-bar)

Combo strings use `<pattern>_<direction>_<kind>` format.

### Reversal combos

| Combo | Bars (oldest→newest) | Direction | Trigger |
|---|---|---|---|
| `212_bull_reversal` | `2D, 1, 2U` | bullish | break above the inside bar's high |
| `212_bear_reversal` | `2U, 1, 2D` | bearish | break below the inside bar's low |
| `312_bull_reversal` | `3, 1, 2U` | bullish | break above the inside bar's high |
| `312_bear_reversal` | `3, 1, 2D` | bearish | break below the inside bar's low |
| `32_bull_reversal` | `3, 2U` (prev close bearish) | bullish | break above prior bar |
| `32_bear_reversal` | `3, 2D` (prev close bullish) | bearish | break below prior bar |
| `22_bull_reversal` | `2D, 2U` | bullish | flips direction without compression |
| `22_bear_reversal` | `2U, 2D` | bearish | flips direction without compression |
| `f2u_bear_reversal` | single bar | bearish | `2U` that closes below open |
| `f2d_bull_reversal` | single bar | bullish | `2D` that closes above open |

### Continuation combos

| Combo | Bars | Direction |
|---|---|---|
| `212_bull_continuation` | `2U, 1, 2U` | bullish |
| `212_bear_continuation` | `2D, 1, 2D` | bearish |
| `22_bull_continuation` | `2U, 2U` | bullish |
| `22_bear_continuation` | `2D, 2D` | bearish |
| `132_bull_continuation` | `1, 3, 2U` | bullish — coil + expansion + follow |
| `132_bear_continuation` | `1, 3, 2D` | bearish |
| `322_bull_continuation` | `3, 2U, 2U` | bullish — expansion-confirmed |
| `322_bear_continuation` | `3, 2D, 2D` | bearish |

### Compression / passive states

| Combo | Bars | Notes |
|---|---|---|
| `11_inside_compression` | `1, 1` | Two consecutive inside bars |
| `111_inside_compression` | `1, 1, 1` | Three consecutive inside bars (high-coil) |
| `clean_2u_bull` | single `2U` (no other combo, `Close ≥ Open`) | Plain trending up bar |
| `clean_2d_bear` | single `2D` (no other combo, `Close ≤ Open`) | Plain trending down bar |

---

## 3. Pattern priority on collision

Multiple combos can match a single bar. Highest priority wins; lower
priorities are discarded for that bar.

1. `212_*_reversal` (3-bar reversal)
2. `312_*_reversal` (3-bar reversal off outside bar)
3. `132_*_continuation` (coil-expand-follow)
4. `322_*_continuation` (expansion confirmed)
5. `212_*_continuation` (3-bar continuation)
6. `32_*_reversal` (2-bar exhaustion reversal)
7. `22_*_reversal` (mixed-direction 2-bar reversal)
8. `22_*_continuation` (same-direction 2-bar continuation)
9. `111_inside_compression`
10. `11_inside_compression`
11. `f2u_bear_reversal` / `f2d_bull_reversal` (Failed_2 — single bar, lowest)
12. `clean_2u_bull` / `clean_2d_bear` (only if nothing else matched)
13. `none`

**Rationale:** multi-bar patterns carry more information about
structure than single-bar Failed_2 prints. A bar that matches both
`22_bear_reversal` and `f2u_bear_reversal` is tagged the multi-bar
combo. Implementation-wise: walk the priority list in order, only
overwriting `'none'`.

---

## 4. FTFC — Full Timeframe Continuity

FTFC measures alignment of the latest classification across timeframes,
weighted by significance.

### Timeframes and weights

| Key | Weight |
|---|---|
| `5m` | 0.05 |
| `15m` | 0.10 |
| `1h` | 0.15 |
| `4h` | 0.15 |
| `12h` | 0.15 |
| `1d` | 0.30 |
| `1w` | 0.10 |
| **Total** | **1.00** |

The score is a weighted sum where each timeframe contributes:
- `+weight` if the latest bar is `2U`
- `-weight` if the latest bar is `2D`
- `0` for `1` (inside) or `3` (outside)

Score range: `[-1.0, +1.0]`. Direction:
- `bullish` if `score > ftfc_direction_threshold` (default 0.3)
- `bearish` if `score < -ftfc_direction_threshold`
- `mixed` otherwise

---

## 5. Bonus scoring per combo

`get_strat_bonus` returns a `float`. Per-combo dicts keyed by direction:

```python
COMBO_BONUS_CALL = {
    # Bullish combos (positive)
    '212_bull_reversal':     1.5,
    '312_bull_reversal':     1.5,
    '132_bull_continuation': 1.25,
    '322_bull_continuation': 1.25,
    '212_bull_continuation': 1.0,
    '32_bull_reversal':      1.0,
    '22_bull_reversal':      1.0,
    '22_bull_continuation':  0.75,
    'clean_2u_bull':         0.25,
    'f2d_bull_reversal':     0.5,
    # Bearish combos (negative — opposing pattern penalises CALL)
    '212_bear_reversal':     -1.5,
    '312_bear_reversal':     -1.5,
    '132_bear_continuation': -1.25,
    '322_bear_continuation': -1.25,
    '212_bear_continuation': -1.0,
    '32_bear_reversal':      -1.0,
    '22_bear_reversal':      -1.0,
    '22_bear_continuation':  -0.75,
    'clean_2d_bear':         -0.25,
    'f2u_bear_reversal':     -0.5,
}
```

`COMBO_BONUS_PUT` is the sign-flipped mirror — bearish combos give
positive bonuses, bullish combos give negatives.

`11_inside_compression`, `111_inside_compression`, and `none` always
score `0.0` (no directional information).

The total bonus is `combo_bonus + ftfc_bonus + orb_bonus`, where:
- `ftfc_bonus = +1` (CALL) when `ftfc_score ≥ ftfc_threshold`, `-1` when
  `ftfc_score ≤ -ftfc_threshold`. Sign-flipped for PUT.
- `orb_bonus = +1` when ORB trend matches the signal direction.

---

## 6. Levels engine — what counts as a "level"

Every Strat level is a horizontal price marker that becomes a magnet,
support, or resistance. The levels engine in `lib/strat_levels.py`
produces a per-ticker `LevelMap` containing:

| Category | Source | Examples |
|---|---|---|
| **Previous-period** | `market_data_daily.prev_*_high/low/open/close` (no recompute) | `Prev_Day_High`, `Prev_Week_Low`, `Prev_Quarter_HL_Mid`, `Prev_Year_Open` |
| **Current-period opens** | classified live against prior period | `Current_Day_Open` (`2U` once price > Prev_Day_High), `Current_Week_Open`, `Current_Quarter_Open`, `Current_Year_Open` |
| **Gap levels** | unfilled gaps on daily candles, lookback 20 | `Gap_Up_2024-03-15` |
| **PMG (spatial)** | clusters of levels within `tolerance_pct` of each other | merged into a single zone with strength = level count |
| **PMG (temporal)** | N consecutive higher-highs / lower-lows | momentum confirmation flag |

Each level has: `name`, `price`, `timeframe`, `level_type` (support /
resistance / pivot / gap), `strat_class` (`1` / `2U` / `2D` / `3` once
classified against the appropriate prior).

---

## 7. Triggers and playbook output

For a given current price + bias + combo, the engine identifies:

- **Entry trigger** — the level the price must break to confirm the bias
- **Stop** — the nearest opposing-side level
- **Target 1, Target 2** — next two levels in trade direction with
  `Room_to_run` ≥ a configurable minimum
- **Risk:Reward** — `(target - entry) / (entry - stop)` for longs,
  mirror for shorts
- **PMG zones** — spatial clusters near current price annotated as cluster
  with strength

The brief renders this in the format:

```
IWM 215.42 — Daily 2U, Combo: 212_bull_reversal, FTFC +0.7 bullish
CALLS above 215.85 (PDH) — 30-min ORB recommended (10:00 ISM release)
  Stop: 213.20 (PDL)
  T1: 217.10 (PWH) — 0.58% room (R:R 1.7)
  T2: 218.45 (PMH) — 1.40% room (R:R 4.1)
PUTS below 213.20 (PDL) — only if bias denied
PMG: 217.05 (PWH+PMH cluster, strength 2.5)
```

---

## 8. Catalyst-aware ORB selection

The premarket brief picks the ORB window per-ticker based on the
day's economic calendar:

- 8:30 ET high-impact event (NFP, CPI, retail sales) → `15m` (settle the
  initial reaction first)
- 10:00 ET high-impact event (ISM, consumer sentiment) → `30m`
- No high-impact event before 10:30 ET → `5m` (default scalp window)

Selection result is persisted to `premarket_analysis.recommended_orb_window`
and `recommended_orb_reason`.

---

## 9. Naming conventions (locked)

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

## 10. Source-of-truth inventory

| Concept | Authoritative location | Status |
|---|---|---|
| Single-bar classification | `lib/strat.py:42` `StratClassifier.classify_candle` | ✅ inclusive (existing code is correct; doc updated to match) |
| Vectorized classification | `lib/strat.py:63` `classify_series` | ✅ |
| Trigger levels | `lib/strat.py:92` `get_trigger_levels` | ✅ |
| Combo detection | `lib/strat.py:104` `detect_combos` | 🔧 refactored in commit 2 |
| FTFC scoring | `lib/strat.py:212` `calculate_ftfc` | 🔧 weights updated in commit 2 |
| Bonus scoring | `lib/strat.py:273` `get_strat_bonus` | 🔧 dict-based, float return in commit 2 |
| Resample rules | `lib/data_loader.py:40` `RESAMPLE_RULES` | 🔧 add 4h/12h, rename D/W in commit 2 |
| Historical levels | `lib/indicators.py:242` `calculate_historical_levels` | 🔧 add Quarter in commit 4 |
| ORB | `lib/indicators.py:295` `calculate_orb` | ✅ |
| Levels engine | `lib/strat_levels.py` | 🆕 created in commit 5 |
| `strat_levels` table | `gcp/schema.sql` | 🆕 added in commit 5 |
| Brief playbook | `gcp/premarket_brief.py` | 🔧 updated in commit 6 |
| Real-time ORB / level breaks | `gcp/signal_monitor.py` | 🔧 updated in commit 7 |
| Pine v2 mirror | `tradingview-pine-scripts/strat-assistant-v2` | (out of scope for this work) |
