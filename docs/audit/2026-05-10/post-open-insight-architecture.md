# Post-Open Insight Architecture — Deep Dive

**Date:** 2026-05-10
**Author:** investigation triggered by 5/6 QQQ chart review
**Branch:** `fix/persist-intraday-levels` (level fix + replay-leakage fix already shipped); proposed follow-up branch `feat/post-open-insight-pipeline` for the architectural changes
**Replay window:** 2026-05-04 → 2026-05-08 (5 trading days, SPY/IWM/QQQ)
**Production state at time of writing:** image `af477` from `origin/main` HEAD (`d515d55`); my two fixes (`5d3e97e`, `b4f89de`) NOT yet on main. Tables below show the production state, not the post-fix state.

---

## 1. Executive Summary

Three independent layers produce trading guidance every morning:

1. **`premarket-brief`** (8:30 ET) — natural-language playbook posted to Discord with a CALL/PUT trigger pair derived from structural levels (PDH/PDL/PWH/PWL/etc.). Tells the trader: *"if X breaks, go this way to that target."*
2. **`insight-pipeline`** (8:45 ET) — multi-LLM analyst panel (technical, options-flow, sentiment, gamma, risk) produces a per-persona trade plan: `direction`, `regime`, `entry_zone`, `stop`, `targets[]`, `invalidation`. Posted at 9:15 ET.
3. **`signal-monitor`** (9:25 ET → market close) — real-time per-bar evaluator that fires Discord alerts when an indicator-scoring threshold is crossed combined with structural-level breaks.

These three were built independently and **the third does not read the second**. Empirical alignment over 5/4–5/8 (500 fires across SPY/IWM/QQQ):

| Bucket | Count | % of fires | Win % |
|---|---|---|---|
| **OPPOSITE direction** (monitor PUT on insight-long day) | **303** | **60.6%** | **32.1%** |
| OUT — fired before reaching insight zone | 169 | 33.8% | 53.8% |
| OUT — fired past zone | 19 | 3.8% | 47.4% |
| **IN insight zone** | **9** | **1.8%** | 44.4% |

The monitor is firing in the WRONG direction relative to the morning plan **60.6% of the time**, and those trades win **32.1%** — well below random's 50%. This is the headline finding.

This document describes the current architecture, what each layer actually produces (with per-ticker tables), the three failure modes that drive the misalignment, and a proposed unified architecture that addresses all three with three surgical changes.

---

## 2. Current Architecture

### 2.1 Production schedule

```
07:15 ET  earnings-calendar-daily          (catalysts populated for the day)
08:20 ET  fetch-premarket-refresh          (writes pre_high/pre_low/pre_vwap to market_data_daily)
08:30 ET  premarket-brief-daily            (Discord playbook posts here)
08:45 ET  insight-pipeline-daily           (LLM analysts run; ~1 min per ticker × 7 tickers)
09:15 ET  insight-discord-push-daily       (Discord embeds for insights)
09:25 ET  signal-monitor-daily             (boots; runs until market close)
09:30 ET  RTH OPEN
09:45 ET  orb-15m-alert                    (15-min ORB closes; second monitor pass)
16:00 ET  RTH CLOSE
16:30 ET  signal-monitor-eod-resolver-daily (cleans up open positions)
23:00 ET  fetch-market-data-daily          (post-RTH daily bar persisted)
```

### 2.2 What each layer produces

**Premarket-brief** writes to `premarket_analysis` (one canonical row per (analysis_date, ticker)) and to `premarket_analysis_history` (append-only audit). The interesting columns:
- `llm_overview` — 2–3 sentence cross-ticker market summary (same string across all 3 tickers)
- `llm_playbook` — per-ticker natural-language plan with explicit trigger/stop/targets keyed by structural-level names (PDH/PDL/PWH/CDO/CWO/etc.)
- `llm_analysis`, `llm_orb_explanation` — supplementary

**Insight-pipeline** writes to `insight_reports` (one row per (ticker, as_of)). The key fields inside `report` JSONB:
- `direction` ∈ `{long, short, flat}`
- `regime` ∈ `{normal, extended, orb_only}` (no `gap_faded` yet — see §4)
- `conviction` ∈ `{low, medium, high}`
- `entry_zone: {low, high}` — single-zone, deterministic from `trade_planner.compute_persona_plans`
- `stop`, `targets[3]`, `invalidation` (string), `bull_case`, `bear_case`, `key_levels` (dict), `persona_plans[]` (3 personas: aggressive/neutral/conservative)

**Signal-monitor** writes to `signal_alerts` (one row per fire). The fire decision is made independently of insight_reports — see §2.3.

### 2.3 Data flow today

```
                                ┌──────────────────────┐
                                │ market_data_daily    │  populated by 08:20 fetcher (pre_high)
                                │ market_data_intraday │  populated continuously (1-min bars)
                                │ strat_levels         │  populated by 08:30 brief writer
                                └──────────┬───────────┘
                                           │
        ┌──────────────────────────────────┼──────────────────────────────────┐
        │                                  │                                  │
        ▼                                  ▼                                  ▼
┌───────────────────┐            ┌──────────────────┐                ┌───────────────────┐
│ premarket-brief   │            │ insight-pipeline │                │ signal-monitor    │
│ 08:30 ET          │            │ 08:45 ET         │                │ 09:25 ET → close  │
│                   │            │                  │                │                   │
│ build_level_map() │            │ context_bundle = │                │ run_loop():       │
│  - PDH/PDL/PWH/   │            │  {market, strat, │                │  for each bar:    │
│    PMH/PQH/PYH    │            │   options, etc.} │                │   evaluate_       │
│  - CDO/CWO/CMO    │            │ 6 LLM analysts → │                │     ticker():     │
│                   │            │ judge → trader → │                │   - check_orb     │
│ persist to:       │            │ pm reviewer →    │                │   - check_exits   │
│ - premarket_      │            │ deterministic    │                │   - check_level_  │
│   analysis        │            │ trade_planner    │                │     breaks  ←┐    │
│ - strat_levels    │            │                  │                │   - rsi/macd │    │
│                   │            │ persist to:      │                │     /momentum│    │
│ Discord post      │            │ - insight_       │                │     scoring  │    │
│ at 08:30          │            │   reports        │                │   - strat_   │    │
└───────────────────┘            │                  │                │     bonus    │    │
                                 │ Discord embeds   │                │   - catalyst │    │
                                 │ at 09:15         │                │     proximity│    │
                                 └──────────────────┘                │   - fire_alert    │
                                                                     │     if total_score│
                                                                     │     >= threshold  │
                                                                     │                   │
                                                                     │ persist to:       │
                                                                     │ - signal_alerts   │
                                                                     │                   │
                                                                     │ Discord post per  │
                                                                     │ fire              │
                                                                     │                   │
                                                                     │ NEVER reads       │
                                                                     │ insight_reports!  │
                                                                     └───────────────────┘
```

The signal_monitor reads `strat_levels` (for level-break detection) but never reads `insight_reports`. The insight pipeline's `direction` / `regime` / `entry_zone` is invisible to the live monitor.

---

## 3. Empirical State — May 4 to May 8

### 3.1 Premarket-brief output (per ticker, per day)

Cross-ticker `llm_overview` strings (one per day, broadcast to all 3 tickers):

| Date | Overview headline |
|---|---|
| 5/4 | "QQQ and SPY are strongly bullish across all timeframes, while IWM is moderately bullish. Expect trend-continuation setups." |
| 5/5 | "QQQ is strongly bullish, but SPY is bearish and IWM is mixed. Expect QQQ to outperform, but SPY may lag and IWM will likely chop." |
| 5/6 | "All three major indices show complete bullish agreement across timeframes; look for trend-following opportunities. Overbought RSI readings suggest [chop possible]." |
| 5/7 | "All timeframes are in agreement, expect trend-continuation setups. Overbought RSI readings suggest some chop is possible, but path of least resistance remains higher." |
| 5/8 | "QQQ and SPY are strongly bullish across all timeframes, suggesting trend-following setups. IWM's mixed score indicates small caps may offer counter-trend opportunities." |

Per-ticker playbook trigger/target snippets (truncated to highlight the level wiring):

| Date | Ticker | Brief CALLS / PUTS triggers (from `llm_playbook`) |
|---|---|---|
| 5/4 | IWM | CALL trigger PWH $279.79, stop CMO $278.66, target PMH $279.79; PUT trigger CMO $278.66 |
| 5/4 | QQQ | Short trigger CMO $669.16; targets CDO $669.16, PMH $668.90, PDH $668.90 |
| 5/4 | SPY | CALL trigger CDO $721.25, stop PMH $719.79; PUT trigger PMH $719.79, targets PDH $719.79, PWH $714.47 |
| 5/5 | IWM | CALL trigger CMO $278.66, stop PDL $276.57; targets CDO/CWO $278.70, PMH $279.79 |
| 5/5 | QQQ | CALLS trigger CDO $674.66, stop CMO $669.16; targets CWO $674.66, PDH $675.97, PWH $675.97 |
| 5/5 | SPY | CALL trigger PMH $719.79, target CDO/CWO $720.07, PDL $720.47 |
| 5/6 | IWM | Short trigger break of PDH $280.79; targets CDO $280.13, PWH $279.81, PMH $279.79 |
| 5/6 | QQQ | Short trigger below CDO $677.96; targets PDH **$676.73 (off-by-one bug — should be $682.77)**, PWH $675.97, CWO $674.66 |
| 5/6 | SPY | CALL trigger PWH $724.87; PUT trigger PDH $722.12, targets CDO $721.77, CMO $721.25 |
| 5/7 | IWM | Short trigger CDO $285.36; T1 PDH $282.94, T2 PDL $280.00, T3 PWH $279.81 |
| 5/7 | QQQ | Short trigger CDO $687.78; targets PDH $682.77, PDL $677.51, PWH $675.97 |
| 5/7 | SPY | PUT trigger break of CDO $728.16; targets PDH $725.04, PWH $724.87, PDL $721.49 |
| 5/8 | IWM | Short trigger PWH $279.81, stop PDL $283.36; targets PMH, CWO, CMO |
| 5/8 | QQQ | Bullish trigger break of PDH $695.93, target CDO $696.58; PUT trigger PDL $686.48 |
| 5/8 | SPY | CALL trigger PDH $734.59, stop PDL $727.82, target CDO $735.05 |

**Observation 1**: The 5/6 QQQ brief writes PDH=$676.73 — that's the *day-before-yesterday* (5/4 high), the off-by-one bug we already fixed on `fix/persist-intraday-levels`. On a post-fix run this would be PDH=$682.77 (5/5 high). All other 5/6 levels likely have the same bug (PWH off by one week, etc.).

**Observation 2**: The brief is structurally bidirectional — it always emits both a CALL trigger and a PUT trigger ("if bias denied"). It never picks ONE direction. The directional choice is implicit in the order/wording.

### 3.2 Insight-pipeline output (per ticker, per day)

| Date | Ticker | direction | regime | conviction | entry_zone | stop | targets |
|---|---|---|---|---|---|---|---|
| 5/4 | IWM | long | normal | low | $281.60 – $282.95 | $276.88 | [$287.68, $293.07, $298.47] |
| 5/4 | QQQ | flat | normal | low | $676.00 – $688.50 | $663.45 | [$690.00, $700.00, $710.00] |
| 5/4 | SPY | flat | normal | low | $720.47 – $723.00 | $710.65 | [$724.87, $730.00, $735.00] |
| 5/5 | IWM | long | normal | low | $283.21 – $284.42 | $278.97 | [$288.65, $293.49, $298.33] |
| 5/5 | QQQ | long | normal | low | $683.88 – $686.31 | $675.39 | [$694.79, $704.49, $714.19] |
| 5/5 | SPY | long | normal | low | $724.87 – $727.86 | $714.41 | [$738.31, $750.26, $762.21] |
| 5/6 | IWM | flat | normal | low | $282.94 – $283.50 | $277.27 | [$288.61, $294.28, $299.95] |
| 5/6 | QQQ | long | normal | low | **$695.52 – $698.84** | $683.90 | [$710.46, $723.74, $737.02] |
| 5/6 | SPY | long | normal | low | $734.10 – $736.68 | $725.09 | [$745.69, $755.99, $766.29] |
| 5/7 | IWM | long | normal | low | $288.44 – $289.87 | $283.43 | [$294.89, $300.62, $306.35] |
| 5/7 | QQQ | long | normal | low | $703.97 – $707.39 | $692.02 | [$719.34, $733.00, $746.66] |
| 5/7 | SPY | long | normal | low | $737.63 – $740.14 | $728.87 | [$748.91, $758.93, $768.95] |
| 5/8 | IWM | flat | normal | low | $287.58 – $288.58 | $282.81 | [$292.35, $297.12, $301.89] |
| 5/8 | QQQ | long | normal | low | $712.55 – $715.16 | $703.41 | [$724.29, $734.73, $745.17] |
| 5/8 | SPY | long | normal | low | $739.51 – $742.29 | $729.78 | [$752.02, $763.14, $774.26] |

**Observation 3**: Every conviction is `low`. Every regime is `normal`. There is no `gap_faded` regime in production today — the trade_planner's blue-sky branch synthesizes a trigger past pre_high whenever pre_high cleared all structural longs, and labels it `normal`. There is no detection of "premarket peaked then faded back below CDO."

**Observation 4**: 5/6 QQQ entry zone $695.52–$698.84 is the canonical example of the 5/6 problem — synthetic blue-sky trigger above pre_high. Reality on 5/6: open $687.18 (gap up but **below** premarket peak $692.97), low $686.48, climbed to $695.93 and closed $695.77. The synth entry $695.52 was barely touched (1 bar at the day's high) and the move from $687→$695 was missed. The user's chart annotation showed an ORB-up signal at ~$687 around 10am — that's where the actual trade was, but the insight system didn't see it.

**Observation 5**: 11 of 15 ticker-days are `direction=long`. 4 are `direction=flat`. Zero `short`. The bias is overwhelmingly long during this window (consistent with the brief overviews). This sets up the alignment failure — see §3.3.

### 3.3 Signal-monitor fires (per ticker, per day)

| Date | Ticker | n_fires | CALL / PUT | strong / med / weak | wins / losses | avg ret % | insight bias |
|---|---|---|---|---|---|---|---|
| 5/4 | IWM | 31 | 11 / 20 | 0 / 1 / 30 | 14 / 17 | −0.041 | long |
| 5/4 | QQQ | 20 | 9 / 11 | 0 / 0 / 20 | 10 / 10 | +0.043 | flat |
| 5/4 | SPY | 28 | 11 / 17 | 0 / 0 / 28 | 10 / 18 | −0.053 | flat |
| 5/5 | IWM | 46 | 7 / 39 | 0 / 2 / 44 | 21 / 25 | −0.068 | long |
| 5/5 | QQQ | 50 | 8 / 42 | 0 / 1 / 49 | 20 / 30 | −0.015 | long |
| 5/5 | SPY | 59 | 15 / 44 | 0 / 7 / 52 | 30 / 28 | −0.006 | long |
| 5/6 | IWM | 34 | 11 / 23 | 0 / 1 / 33 | 10 / 24 | −0.155 | flat |
| 5/6 | QQQ | 74 | 17 / 57 | 1 / 5 / 68 | 32 / 42 | −0.016 | long |
| 5/6 | SPY | 54 | 8 / 46 | 0 / 5 / 49 | 17 / 37 | −0.078 | long |
| 5/7 | IWM | 111 | 86 / 25 | 0 / 3 / 108 | 43 / 68 | −0.045 | long |
| 5/7 | QQQ | 138 | 79 / 59 | 2 / 9 / 127 | 66 / 72 | +0.012 | long |
| 5/7 | SPY | 137 | 82 / 55 | 0 / 4 / 133 | 56 / 81 | −0.003 | long |
| 5/8 | IWM | 145 | 47 / 98 | 2 / 10 / 133 | 85 / 60 | +0.029 | flat |
| 5/8 | QQQ | 127 | 10 / 117 | 0 / 3 / 124 | 27 / 99 | −0.068 | long |
| 5/8 | SPY | 124 | 27 / 97 | 0 / 4 / 120 | 82 / 41 | +0.029 | long |

**Observation 6**: Total fires across the 5-day window — 1,178. Of those:
- 428 CALL, 750 PUT (64% PUT-side bias)
- 5 strong, 50 medium, 1,123 weak (95.3% are weak — the threshold is generous)
- ~523 wins, ~652 losses (44.5% overall win rate)

**Observation 7**: The directional misalignment is per-ticker stark:
- IWM: 162 CALL / 205 PUT across 5 days (56% PUT) — but insight bias was long on 3 of those days
- **QQQ: 123 CALL / 286 PUT (70% PUT)** — but insight bias was long on 4 of those days
- **SPY: 143 CALL / 259 PUT (64% PUT)** — but insight bias was long on 4 of those days

The monitor's per-bar RSI/MACD/momentum scoring fires bidirectionally on intraday volatility. On a long-bias day where price chops within a range, the monitor will fire PUTs on every dip and CALLs on every bounce. The insight saying "we're long-biased today, only take CALL setups" is exactly the filter that's missing.

### 3.4 The 5/6 QQQ case study (live walk-through)

```
Premarket (4:00–9:30 ET):
  $683 → $692.97 high (~7am) → fades to $686 by 9am → $687 at 9:25
  Final premarket: pre_high=$692.86, pre_low=$681.61, pre_vwap=$690.30, gap_pct=+2.74%

Brief (8:30 ET, today's behavior):
  Computes PDH from compute_previous_levels(daily_df) using df ending in 5/5.
  BUG: iloc[-2] picks 5/4 not 5/5 → PDH=$676.73 (should be $682.77).
  llm_playbook: "Short trigger below CDO $677.96; targets PDH $676.73, PWH $675.97, CWO $674.66"
  All targets are BELOW spot. Brief is structurally bearish despite a long-bias overview.

Insight pipeline (8:45 ET, today's behavior):
  context_from_bundle reads market_data_daily WHERE date <= as_of LIMIT 1
  → picks 5/6's row (close=$695.77 already populated by 23:00 prior-day fetcher in replay)
  → ctx.close = $695.77 (LEAKED RTH close)
  → cleared_above = max($695.77, pre_high=$692.86) = $695.77
  → all structural longs (PDH=$682.77 corrected, PWH=$675.97, etc.) are below cleared_above
  → blue-sky synth: trigger = $695.77 + 0.20×ATR = $697.71, but headline_entry shows $695.52
  → entry_zone $695.52–$698.84, stop $683.90, targets [$710.46, $723.74, $737.02]

Reality 5/6 RTH:
  09:30 open: $687.18 (gap UP from yesterday $681.61, but DOWN from premarket peak $692.97)
  09:30–10:00: fade to low $686.48
  10:00–11:00: ORB-up reclaim; price reclaims pre_vwap $690.30
  11:00–14:00: steady climb $691→$695
  14:00–16:00: hits $695.93 high, closes $695.77

  Actual trade opportunity: long at ~$687 (10am ORB), exit ~$695 = +1.16%
  Insight's recommended trade: long at $695.52 (entry_zone), exit ~$695.77 = +0.04%
  → Insight missed essentially all of the move.

Signal monitor (live on 5/6):
  Fired 74 times. 17 CALL, 57 PUT. 32 wins, 42 losses. avg return -0.016%.
  Some of those PUTs likely fired during the 9:30–10:00 fade — exactly when the insight
  said "long bias." If the monitor had a direction gate against insight.direction=long,
  most of those 57 PUT fires would have been suppressed.
```

This single ticker-day exemplifies all three failure modes (timing, leakage, no direction gate).

---

## 4. The Three Failure Modes

### Failure mode 1: Brief and insights are blind to late-premarket dynamics

The brief at 8:30 ET sees premarket data through ~8:20 ET (the 8:20 fetcher's cutoff). On a day where premarket peaks at 7am and fades through 8:30–9:30, the 8:30 brief's `pre_high` already encodes the peak — but the brief has no way to know whether premarket *held* into RTH or *faded* before open. Same for insights at 8:45.

**Effect on 5/6 QQQ**: pre_high $692.86 was set at ~7am. By 9:25 premarket had faded to ~$687. RTH opened at $687.18 (well below pre_high). The 8:30 brief and 8:45 insight had no way to factor this in — they treated pre_high as still-valid resistance to break above.

### Failure mode 2: Replay leakage in `summarize_market_context`

`lib/agents/summarizers.py:summarize_market_context` queries `market_data_daily WHERE date <= :as_of LIMIT 1`. When AS-OF is set (replay), this picks the AS-OF day's row — which on a replay run later in the week has the **already-populated post-RTH close**. Trade_planner's blue-sky math uses `cleared_above = max(close, pre_high)` — and with `close = today's RTH close`, every structural level is below `cleared_above`, forcing blue-sky synthesis even on days where the live 8:45 ET run would have seen `close = NULL` (RTH not yet closed).

**Already fixed on `fix/persist-intraday-levels`** (commit `b4f89de`): split the query, use `date < as_of` for daily/indicator columns and `date = as_of` for premarket columns. NOT yet deployed (image build needed after rebase onto main).

### Failure mode 3: Signal_monitor doesn't read insights

This is the headline finding: **monitor and insight disagree on direction 60.6% of the time**, and disagreements lose 67.9% of the time.

The monitor's per-bar evaluator (`evaluate_ticker` → `_evaluate_strategies_for_bar`) computes a directional `signal` from RSI/MACD/momentum/volume + a strat-bonus from candle-pattern detection, then sums into a `total_score`. If `total_score >= threshold` it fires. There is no comparison against `insight_reports.direction`. There is no comparison against `insight_reports.regime`. The monitor is operationally blind to the morning plan.

On a long-bias day, every dip looks like a PUT signal (RSI drops, MACD turns down, momentum weakens) and every bounce looks like a CALL. The monitor fires both and racks up small losses on the dips before the day's actual long move resolves.

---

## 5. Process Flow — Current vs. Proposed

### 5.1 Current

```
07:15 earnings → 08:20 premarket-refresh → 08:30 brief (Discord)
                                          → 08:45 insight (LLM panel) → 09:15 Discord push
                                          → 09:25 monitor boots (NEVER reads insight)
                                          → 09:30 RTH OPEN
                                          → 09:45 ORB
                                          → ... market hours ...
                                          → 16:00 RTH CLOSE
                                          → 16:30 EOD resolver
                                          → 23:00 daily fetcher
```

### 5.2 Proposed (consolidated changes)

```
07:15 earnings → 09:15 premarket-refresh (full premarket through 9:15)
                09:20 brief (Discord) — uses near-final premarket
                09:30 RTH OPEN
                09:35 insight (LLM panel) — sees ACTUAL CDO + first 5 RTH 1-min bars
                09:35 monitor boots — reads insight at boot + every 60s thereafter
                09:40 insight Discord push
                09:45 ORB
                ... market hours: monitor enforces direction gate + invalidation tripwire ...
                16:00 RTH CLOSE
                16:30 EOD resolver
                23:00 daily fetcher
```

**Key architectural shift**: insights now publish AFTER market open, with the 9:30 1-min RTH bars in hand. CDO is observable, not estimated. The 9:35 insight is the canonical morning plan (replaces the 8:45 version). Signal_monitor reads it.

---

## 6. Proposed Architecture

### 6.1 Schedule shifts (`gcp/deploy.sh`)

| Job | Old | New |
|---|---|---|
| earnings-calendar-daily | 7:15 | 7:15 (unchanged) |
| premarket-refresh-daily | 8:20 | **9:15** |
| premarket-brief-daily | 8:30 | **9:20** |
| insight-pipeline-daily | 8:45 | **9:35** |
| insight-discord-push-daily | 9:15 | **9:40** |
| signal-monitor-daily | 9:25 | **9:35** |
| orb-15m-alert | 9:45 | 9:45 (unchanged) |

**Rationale**: ordering becomes earnings → premarket → brief → insight → monitor. Each consumer reads only data its producer has finalized. No layer guesses about what will happen post-its-own-cutoff.

### 6.2 CDO + first-RTH-bars in `summarize_market_context`

When `as_of` is today (or any replay), query `market_data_intraday` for ALL bars where `time >= 9:30 ET AND time < as_of_time`, surface in the bundle:

```python
rth_so_far = {
    "cdo": 687.18,                # open of 9:30 bar
    "rth_high": 689.78,           # max(high) over bars seen
    "rth_low": 687.18,            # min(low)
    "rth_vwap": 688.12,           # volume-weighted avg
    "rth_close": 689.69,          # close of latest bar
    "n_bars": 5,                  # bars seen
    "range_pct": 0.38,            # (high - low) / cdo * 100
}
```

At 9:35 that's bars 9:30, 9:31, 9:32, 9:33, 9:34. Five minutes of RTH data — enough to see whether the open held or faded AND whether the first 5 min are trending up or down.

The query is targeted: `SELECT time, open, high, low, close, volume FROM market_data_intraday WHERE ticker=:t AND time::date = :d AND time::time >= '09:30' AND time::time < :cutoff_time ORDER BY time`. Adds ~50 ms per ticker. Replay path uses the same query.

### 6.3 `gap_faded` regime in `trade_planner.select_trigger_and_regime`

```python
# Inside select_trigger_and_regime, AFTER the existing has_multi_tf check:
if cdo is not None and pre_high is not None and pre_low is not None:
    # Premarket peaked then faded back below CDO before RTH — pre_high
    # is now overhead resistance, not "still cleared." Trade is reclaim.
    if cdo < pre_high - 0.4 * atr:
        if rth_close > rth_vwap:
            regime = "gap_faded_reclaim"
            # Buyer is winning the first 5 min — wait for break of either
            # the first-5min high or pre_high (whichever is higher).
            trigger = max(pre_high, rth_high + 0.05 * atr)
        else:
            regime = "gap_faded_distribute"
            # Seller still winning — wait for break of first-5min high
            # before getting long.
            trigger = rth_high + 0.05 * atr
        stop = min(cdo, pre_low) - 0.5 * atr
        # Targets: pre_high (T1, the level being reclaimed),
        #          pre_high + 0.5 ATR (T2, where the old synth was),
        #          pre_high + 1.0 ATR (T3 stretch).
        targets = [pre_high, pre_high + 0.5 * atr, pre_high + 1.0 * atr]
        return (regime, trigger, stop, distance_atr, False)  # is_blue_sky=False
```

For 5/6 QQQ this produces (CDO=$687.18, pre_high=$692.86, pre_low=$681.61, ATR=$9.7, rth_high=$689.78, rth_close=$689.69 > rth_vwap=$688.12 → reclaim):
- trigger = max($692.86, $689.78 + $0.49) = **$692.86** (the reclaim level)
- stop = min($687.18, $681.61) − $4.85 = $676.76
- targets = [$692.86, $697.71, $702.56]

Entry near $692.86 (the reclaim) replaces the synthetic $694.80. T1 hit at noon, T2 hit at the actual 5/6 close, T3 hit on 5/7.

### 6.4 Signal-monitor insight integration

Three layers, all reading the same `insight_reports` row:

**(a) Direction gate at fire time** — inside `evaluate_ticker` before `fire_alert`:
```python
insight = self.insight_cache.get(ticker)  # refreshed every 60s in run_loop
if insight and insight['direction'] in ('long', 'short'):
    sig_long = sig['direction'] == 'CALL'
    insight_long = insight['direction'] == 'long'
    if sig_long != insight_long:
        # Direction conflicts with morning plan. Suppress weak; downgrade
        # medium → weak; downgrade strong → medium.
        if strength == 'weak':
            return  # skip fire entirely
        elif strength == 'medium':
            strength = 'weak'
        elif strength == 'strong':
            strength = 'medium'
```

**(b) Regime tag in Discord embed**: surface `insight['regime']` as a field on every fire's Discord embed. Trader sees "Regime: gap_faded_reclaim — wait for ORB confirmation" alongside the fire.

**(c) Invalidation tripwire**: trade_planner emits `invalidation_level: float` (typically the stop price OR the failed-2 level on the daily strat). Monitor monitors that level. On crossing, monitor:
- Posts a one-time "Thesis invalidated at X" Discord alert
- Sets `self.insight_invalidated[ticker] = True`
- Drops the direction gate from layer (a) for the rest of the session — the morning plan is mechanically wrong, no point suppressing fires that would oppose it
- Optionally re-enqueues an insight-pipeline run for that ticker (this is layer 6.5)

### 6.5 Higher-timeframe regime auto-trigger

When signal_monitor detects one of these RARE events (typically 1–3 events per ticker per WEEK, not per day):
- Daily strat candle's classification flips during the session (started as 2U, becomes Failed_2U)
- 30-min Failed_2 fires
- Daily SMA200 cross sustained for ≥30 min

It enqueues a Cloud Tasks message to `insight-pipeline-queue` for that ticker. Pipeline reruns ~5 min later with the updated context (now-flipped daily classification, current session RTH bars). New `insight_reports` row lands. Monitor's 60s pull picks it up. Direction gate (a) starts using the new direction.

This is the answer to "what if the market changes direction mid-session" — the trigger is a *higher-timeframe* event, not a 1-min flicker, so notification fatigue stays bounded.

---

## 7. Technical Breakdown

### 7.1 Files touched

| File | What changes | Approx LOC |
|---|---|---|
| `gcp/deploy.sh` | 6 schedule cron lines | ~6 |
| `lib/agents/summarizers.py` | Add `_query_rth_so_far(ticker, as_of_time)`; wire into `summarize_market_context` return dict | ~40 |
| `lib/agents/trade_planner.py` | Add `cdo`, `rth_*` fields to `PlanContext`; add `gap_faded_reclaim` / `gap_faded_distribute` branches in `select_trigger_and_regime`; emit `is_gap_faded` flag; propagate through `compute_persona_plans` | ~80 |
| `lib/agents/schema.py` | Add `invalidation_level: Optional[float]` to InsightReport / PersonaPlan | ~5 |
| `gcp/signal_monitor.py` | Add `insight_cache`, `_refresh_insight_cache()` (every 60s in run_loop), direction gate inside `evaluate_ticker`, regime annotation in `fire_alert`, invalidation tripwire in `_check_exits` (or new `_check_invalidation`), Cloud Tasks enqueue on higher-tf regime change | ~120 |
| `tests/test_summarizers.py` | RTH-so-far query fixtures | ~30 |
| `tests/test_trade_planner.py` | gap_faded scenarios (5/6 QQQ replay, hold case, distribute case) | ~80 |
| `tests/test_signal_monitor_insight_integration.py` (new) | Direction gate, invalidation tripwire, regime change auto-enqueue | ~100 |

Total: ~460 LOC change including tests.

### 7.2 Schema changes

None to existing tables. The `invalidation_level` field is added to the `insight_reports.report` JSONB document — no migration needed (existing rows simply lack the field; consumers tolerate `None`).

### 7.3 Cost impact

- Schedule shift is free (same number of executions, different times)
- RTH-so-far query: ~50 ms × 7 tickers × 1 call/run × 1 run/day = 350 ms/day extra Cloud SQL load. Negligible.
- Insight cache refresh: 1 query per ticker per 60s × 7 tickers × 6.5 hours = ~2,700 queries/day. Each query is ~10 ms. ~27 sec/day extra signal-monitor runtime. Negligible cost.
- Higher-tf regime auto-trigger: estimated 1–3 reruns/week × all-tickers cohort × ~$0.10/run = ~$1.50/month. Negligible.
- No new Cloud Run jobs. No new fetchers. No new schedulers.

### 7.4 Test coverage targets

- `gap_faded_reclaim`: unit test reproducing 5/6 QQQ, asserts trigger=$692.86 (not $694.80 synth)
- `gap_faded_distribute`: unit test for fade that's still selling, asserts trigger=`rth_high + 0.05 * atr`
- `gap_held` (= `normal` blue-sky path): unit test for the case CDO ≈ pre_high, asserts blue-sky synth still fires at `pre_high + 0.20 * atr`
- Direction gate: unit test that a CALL signal on a `direction=short` insight gets suppressed (weak) / downgraded (medium → weak)
- Invalidation tripwire: unit test that crossing `invalidation_level` posts the one-time alert and sets the kill-switch flag
- 60s insight cache refresh: unit test that a new `insight_reports` row published mid-session is visible within the next poll cycle
- Replay path: integration test that 5/6 QQQ replay through the full pipeline produces `regime=gap_faded_reclaim`, `entry_zone` near $692.86, `direction=long`

---

## 8. Rollout Plan

### Phase 1: Pre-deploy verification (no production change)
1. Rebase `fix/persist-intraday-levels` onto current main (`d515d55`)
2. Cherry-pick or re-apply the analysis_date + replay-leakage fixes if main has divergent edits
3. Open PR for the level/replay fixes that's already pushed (`5d3e97e`, `b4f89de`)
4. After that lands, branch `feat/post-open-insight-pipeline` from main

### Phase 2: Implementation order on the new branch
1. Schedule + CDO/RTH fallback in summarize_market_context first (testable hermetically; replay validates)
2. `gap_faded_*` regime in trade_planner + tests (5/6 QQQ replay is the acceptance test)
3. Invalidation level emission in PersonaPlan / InsightReport
4. Signal-monitor: insight cache + direction gate + regime annotation
5. Signal-monitor: invalidation tripwire + kill-switch
6. Signal-monitor: higher-timeframe regime auto-trigger (last — narrowest scope, rare events)

### Phase 3: Production validation
1. Replay 5/4–5/8 with the new image; compare alignment table to today's baseline (target: opposite-direction fires drop from 60.6% to <10%; in-zone fires rise from 1.8% to >40%)
2. Replay specific case studies: 5/6 QQQ (gap_faded_reclaim), 5/8 IWM (mixed signals), 5/4 SPY (flat day)
3. Capture before/after Discord embed screenshots for the runbook

### Phase 4: Cron flip + deploy
1. Update cron schedules in `gcp/deploy.sh`, deploy
2. Run for one trading week, monitor signal_alerts win rate vs prior week
3. Compare per-ticker fire counts: expect total fires to drop ~30–40% (suppressed counter-trend fires) while win rate rises

### Phase 5: Follow-up backlog
1. Add a `signal_monitor_directional_suppression_count` metric
2. Backtest the suppression rule on a longer window (full April, full May)
3. Tune `0.4 ATR` threshold in gap_faded detection — empirically calibrate from the broader window

### Rollback
- Schedule changes are reversible by reverting the cron lines and redeploying
- Code changes guard against null/missing fields (insight_cache is empty → direction gate is no-op; gap_faded path requires CDO+pre_high+pre_low+rth_so_far — missing any → falls back to existing normal/extended/orb_only branches)
- No schema migrations to undo

---

## 9. Open Questions

1. **Discord push at 9:40 (post-open) vs 9:15 (pre-open)**: traders accustomed to a pre-open insight may push back. Mitigation: the brief at 9:20 is still pre-open; the insight at 9:40 is the *confirmed* version. Two messages with distinct purposes.

2. **Should the direction gate suppress weak fires entirely or downgrade them?** Current proposal in §6.4 is suppress weak. Alternative: downgrade weak → "info-only" embed without trade math. Trade-off: more notifications but more transparency.

3. **`gap_faded` threshold (0.4 ATR)**: the 5/6 QQQ data fits at 0.59 ATR ($687.18 vs $692.86, ATR=$9.7). Need to backtest April–May to find the right cutoff. 0.4 might be too tight (false-trigger on small fades that would still hold).

4. **Higher-tf regime auto-trigger thresholds**: which events count? Daily Failed_2U is conservative (rare but reliable). 30-min Failed_2 might over-fire. Need a calibration window.

5. **Premarket fetcher at 9:15** — does this conflict with the existing 9:25 fetch-premarket-refresh slot? Currently premarket-refresh is 8:20. Moving it to 9:15 means the data is finalized within minutes of RTH open. Should be safe but worth verifying no downstream consumers depend on the 8:20 timing.

---

## 10. Decision Required

Approve and proceed to spike on `feat/post-open-insight-pipeline`. Implementation order per §8 Phase 2. Acceptance test: 5/6 QQQ replay produces `regime=gap_faded_reclaim`, `entry_zone` anchored at $692.86, signal_monitor's PUT fires during 9:30–10:00 fade get suppressed by the direction gate, and the post-10am long fires get the regime annotation.

Pending answers to §9 open questions (especially #2 weak-suppression policy and #5 fetcher timing).
