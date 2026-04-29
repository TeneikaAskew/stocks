# Plan — Pre-Market Context for Entry/Stop Calibration

**Status:** Fix A shipped 2026-04-28 via PR #134. Fixes B + C still pending.
**Author:** session 2026-04-28
**Scope:** AI Insight pipeline + premarket brief

## Shipping log

| Fix | Status | Landed in |
|---|---|---|
| Fix A — Pre-market H/L/VWAP/volume/gap_pct/pre_range_atr block in `summarize_market_context`; surfaced in brief overview embed and in the LLM analyst prompt | ✅ Shipped 2026-04-28 | PR #134 |
| Adjacent — level-aware trigger + gap-regime gate (uses Fix A's pre_high to mark "cleared" levels and to switch into `orb_only` regime on extreme gaps) | ✅ Shipped 2026-04-28 | PR #136 |
| Fix B — Overnight futures (ES / NQ / RTY) context | 📋 Pending |
| Fix C — Pre-market range expansion vs ATR14 as a regime gate (partially covered by `pre_range_atr` in Fix A) | 🟡 Partial — surfaced as a number but not yet a regime classifier |

---

## 1. Why this matters (the 4/27 lesson)

The 8:45 AM 4/27 AI insights for SPY/IWM/QQQ all produced entry zones based on **Friday's H/L** (e.g., IWM entry zone $265.36–$266.57, derived from Friday's prev-day high). But Monday gapped up significantly:

| Ticker | Fri close (used as basis) | Mon open (actual reality at 9:30) | Entry zone proposed | Was it ever reachable? |
|---|---|---|---|---|
| IWM | $276.65 | **$276.92** | $265.36 – $266.57 | ❌ never traded that low all day |
| SPY | $713.94 | **$714.60** | $686.30 – $697.53 | ❌ |
| QQQ | $663.88 | **$663.44** | $626.74 – $628.74 | ❌ |
| AVGO | $422.76 | **$416.06** (gap down) | $422.76 – $429.31 | ❌ session high $418.59 |

**Root cause**: the AI / brief computed levels off the prior day's session range and ignored:
1. Pre-market price action (8:00 AM – 9:30 AM ET) — would have shown the gap up before the bell.
2. Pre-market H/L — the actual range traders cared about.
3. Overnight futures activity (ES, NQ, RTY) — would have signalled overnight gap risk.

So entries were stale before they were even rendered. The model's directional read was correct (long, market closed up), but every level was misplaced.

---

## 2. What "pre-market context" should include

| Signal | Source | Why it matters |
|---|---|---|
| **Pre-market H / L** (4 AM – 9:30 AM ET) | AV `TIME_SERIES_INTRADAY` with extended-hours flag | Shows where overnight orders settled |
| **Pre-market VWAP** | Computed from extended-hours bars | Better basis for entry than prior-day close |
| **Pre-market volume** | Extended-hours bars | Confirms whether the gap is "real" (high vol) vs noise |
| **Gap %** (today open vs prior close) | open_today / close_prior - 1 | Categorize: fade gap (>2% with low vol) vs continuation (high vol) |
| **Overnight futures (ES / NQ / RTY)** | AV intraday for ES=F / NQ=F / RTY=F | Equity ETFs front-run futures by ~4 AM ET |
| **Pre-market range expansion** | (preH - preL) / ATR14 | Pre-market range > 0.5 ATR = volatility regime change |

---

## 3. Three concrete fixes (in priority)

### Fix A — Pre-market range as a dedicated input (smallest, biggest leverage)

Add to `lib/agents/summarizers.summarize_market_context` a new output:

```python
"premarket": {
    "pre_high":     279.42,    # extended-hours session high
    "pre_low":      276.85,
    "pre_vwap":     277.93,
    "pre_volume":   1_200_000,
    "gap_pct":      +0.12,     # vs prior-day close
    "pre_range_atr": 0.42,     # (preH-preL) / ATR14, regime tag
}
```

The LLM analyst prompt already accepts `market` block context. Adding `premarket` sub-key means the analyst can write:

> "Pre-market range $276.85 – $279.42 (0.42 ATR) suggests a contained gap. Entry above PDH=265.36 is now stale — use pre_high=279.42 as the failure level."

### Fix B — Recompute entry zone using "today's reality" not "Friday's high"

Update [lib/strat_levels.identify_triggers](lib/strat_levels.py) to use this priority order for `calls_trigger`:

1. If `pre_high > prev_day_high` and gap > 0.5%: use `pre_high` as the breakout level
2. Else: use `prev_day_high` (current behaviour)

Same logic for `puts_trigger` (use `pre_low` when gap-down). The strat_levels engine already classifies `CDO` (current day open) — extend it to also include `CDH/CDL` (current-day pre-market H/L).

### Fix C — Catalyst-aware override (already exists for ORB, extend to entry calibration)

The brief already has `select_orb_window` that picks a 15m / 30m ORB on high-impact catalyst days. Extend that same pattern: on days with an 8:30 AM ET catalyst (NFP, CPI), **mark the brief's entry levels as "STALE — wait for ORB"** instead of publishing pre-catalyst stale levels.

---

## 4. Schema additions

```sql
-- Add to market_data_daily (one row per ticker per date, computed
-- after pre-market session ends at 9:30 ET)
ALTER TABLE market_data_daily
    ADD COLUMN IF NOT EXISTS pre_high       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pre_low        DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pre_vwap       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pre_volume     BIGINT,
    ADD COLUMN IF NOT EXISTS gap_pct        DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pre_range_atr  DOUBLE PRECISION;
```

These are populated by `fetch-market-data` when it pulls intraday bars (extended-hours flag = `true`). Idempotent ALTER, no data loss.

---

## 5. New StratLevel types in `lib/strat_levels.py`

Add to `StratLevel.level_type` enum:
- `pre_high` — pre-market high (replaces PDH when gap > 0.5%)
- `pre_low` — pre-market low (replaces PDL when gap < -0.5%)
- `pre_vwap` — pre-market VWAP (used as initial mean-reversion target)

`compute_current_levels()` becomes catalyst-aware: when pre-market range is computed, it weights the pre-H/L into the level map alongside CDO/CWO.

---

## 6. Verification with the existing validator

`scripts/validation/validate_brief_accuracy.py` already validates trigger/stop/target hits against intraday bars. After implementing Fix A+B, re-run on 4/27 with the new logic against the same 1-min bars — entry zone for IWM should shift from $265-266 (the never-reached Friday-based zone) to $276-279 (the pre-market-aware zone).

The validator will report `entry_reached: ✓` instead of `✗ not reached` for IWM/SPY/QQQ on a backtest of the new logic against 4/27.

---

## 7. Implementation order (4 small PRs, not one big bang)

1. **PR α — Schema + fetcher**: add 6 cols to `market_data_daily`, update `fetch-market-data` to compute pre-market H/L/VWAP/volume from existing 1-min bars (extended-hours bars are already in `market_data_intraday`, just need to filter by ts < 13:30 UTC and aggregate).
2. **PR β — Summarizer wiring**: extend `summarize_market_context` with `premarket` sub-key. LLM analyst prompt unchanged (it already reads market context).
3. **PR γ — Strat levels engine**: add `pre_high` / `pre_low` / `pre_vwap` level types in `lib/strat_levels.py`; `identify_triggers` priority adjusted.
4. **PR δ — Brief integration**: brief's playbook now reflects pre-market-aware triggers. ORB selection cross-references pre_range_atr (high pre_range_atr → recommend 15m/30m ORB even without high-impact catalyst).

Each PR is < 200 LOC, independently testable, independently revertible.

---

## 8. What we're NOT doing in this plan

- Pulling overnight futures (ES/NQ/RTY) data — explicitly out of scope for v1. Easy add later if pre-market signals alone aren't sufficient.
- Pre-market sentiment / news tagging — out of scope. Today's `news_sentiment` lookback covers it.
- Real-time pre-market alerts — not in this plan; brief runs at 8:30 AM after the pre-market session has substantial data already.

---

**Question for review before implementation:**
- Approve the 4-PR order? Any signal you want priorities reshuffled?
- Should pre-market range expansion (>0.5 ATR) automatically tag the report `failed_sections=['stale_levels']` to flag low-confidence entry zones, or just nudge them?
- Any pre-market hours window other than 4 AM – 9:30 AM ET worth using? AlphaVantage's extended-hours data starts at 4:00 AM ET.
