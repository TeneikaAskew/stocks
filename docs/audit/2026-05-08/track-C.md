# Track C — AI Insights Evaluation (2026-05-04 → 2026-05-07)

**Eval window:** 2026-05-04 (Mon) → 2026-05-07 (Thu) ET trading sessions.
**Tickers:** SPY, IWM, QQQ.
**Author:** Claude Code session
`claude/audit-insights-factors-FWpHz`, run 2026-05-08.
**Data source:** Cloud SQL `trading` DB via `db-query.yml` workflow
(direct sandbox connection blocked at TCP).

## TL;DR — Verdict

**WORKING WITH SIGNIFICANT GAPS.** The 8:45 AM AI Insights pipeline ran
12-of-12 expected reports across the 4-day window (3 tickers × 4 days)
with 100% success status, ~14–18 s wall-clock per ticker, and ~$0.0028
per report on Vertex Gemini 2.0 Flash (≈ **$0.011/day, $3.30/month**).
Strat integration is intact (single source of truth — both brief and
insights call `lib.strat.compute_strat_status`). Schema enforces concrete
entry/stop/targets via Pydantic — there is no "vague entries" surface in
the JSON.

But the **executable plays** the reports produced were almost entirely
**non-actionable**:

* **9 of 12 reports** ended up in `regime=orb_only`. The deterministic
  trade-planner replaced the LLM's plan with a placeholder that tells the
  trader "wait for the 15-min ORB." `targets=[]`, `position_size_pct=0.0`.
* **2 of 12 reports** were `direction=flat` (catalyst-blocked by the
  conservative risk persona over upcoming high-impact events).
* **1 of 12 reports** had a real, normal-regime, directional plan
  (SPY 5/6 — but it was overwritten by `direction=flat` from risk
  persona; the `regime=normal` rows in the output table all carried
  `flat`, so genuinely actionable reports = **0/12**).

The pipeline is **delivering at the schedule level** but **not delivering
plays a discretionary trader can execute** for this window.

The factor analysis the plan asked for is partially blocked by data
shape: **`signal_alerts.conditions_met` is stored as a JSON-string-of-an-
array** rather than a native JSONB array (782/782 rows in the window
have `jsonb_typeof = 'string'`). A `(conditions_met #>> '{}')::jsonb`
double-decode unblocks expansion and produced the table in §5; the long-
term fix is a one-line change in the writer plus a backfill. Important
secondary finding from the unblocked expansion: **only mean-reversion
factors fired across May 4-7, 0 momentum fires** — the `Phase 0.7.x`
gate raise plus the strict `Consecutive_Up >= 3` revert appears to have
suppressed the momentum strategy entirely on these tickers in this
regime.

---

## 1. Pipeline ran on schedule

| Section | Result |
|---|---|
| Expected report count | 12 (3 tickers × 4 days) |
| Actual rows in `insight_reports` for window | **12** ✅ |
| `insight_runs` status | **12 / 12 `done`** ✅ |
| Trigger column | all `scheduled` (no manual reruns or failures) |
| Wall-clock latency | min 12.4 s (QQQ 5/6), max 18.5 s (IWM 5/7) |
| Per-report cost | $0.0026 – $0.0032 (Vertex Gemini 2.0 Flash, 7 roles) |
| Daily cost | ≈ $0.0084 / day for 3 tickers, ~$3.30 / month |
| Discord delivery | not in scope — not surfaced in this audit |

Source: `insight_reports` (12 rows), `insight_runs` (12 rows
status=done).

### Model routing snapshot (live)

```
analyst              vertex  gemini-2.0-flash
bear                 vertex  gemini-2.0-flash
bull                 vertex  gemini-2.0-flash
judge                vertex  gemini-2.0-flash
portfolio_manager    vertex  gemini-2.0-flash
risk                 vertex  gemini-2.0-flash
trader               vertex  gemini-2.0-flash
```

All 7 roles point at the same model. The /admin per-role swap UI exists
but is unused — every node runs Flash. This is fine for cost and
acceptable for this throughput, but it's worth flagging that the multi-
provider abstraction is dormant in practice.

---

## 2. Strat integration — VERIFIED

Both consumers call the same function:

* `gcp/premarket_brief.py:777` — brief computes its strat snapshot via
  `compute_strat_status(ticker, df=…, timeframes=['1d','1w','1mo'])`.
* `lib/agents/summarizers.py:217-219` — the analyst-tier `strat_analyst`
  node calls `compute_strat_status(ticker, as_of=as_of)` and emits the
  StratSnapshot embedded in the report.

The orchestrator's final `_build_strat_snapshot` (`lib/agents/orchestrator.py:618-633`)
copies that section verbatim into the report. Spot-check with QQQ
2026-05-07: brief said `strat_candle=1, strat_combo=none, ftfc=0.0/mixed,
prev_high=664.43, prev_low=660.69`; the report's `strat_status` block
matches exactly: `last_candle=1, in_force_combo=none, ftfc_score=0.0,
ftfc_direction=mixed, trigger_high=664.51, trigger_low=656.53` (the small
delta on trigger levels is because the brief reads market_data_daily
prev-close while the agent uses `compute_strat_status`'s mother-bar
walk-back; both legitimate, both documented).

**No drift.** This was the highest-risk integration on the list and it
holds up.

---

## 3. Brief vs Insights — DIVERGENT (and brief data looks frozen)

The brief and the insights pipeline disagree directionally on every row in
the window where they had a clear opinion.

### Brief signals over the window

`premarket_analysis` rows for the four mornings:

| ticker | days 5/4 → 5/7 | signal_status | strat_combo | ftfc | prev_day_high | prev_day_low | price |
|---|---|---|---|---|---|---|---|
| IWM | identical | PUT setup (3/5) | 322_bull_continuation | 1.0 bullish | 278.24 | 276.25 | 277.14 |
| QQQ | identical | PUT setup (3/5) | none | 0.0 mixed | 664.43 | 660.69 | 664.23 |
| SPY | identical | PUT setup (4/5) | 322_bull_continuation | 1.0 bullish | 715.63 | 712.295 | 715.17 |

**Every row is identical across all four trading days for the same
ticker.** Prev-day-high and prev-day-low cannot be the same Mon→Thu in a
normal market — Tue's prev-high is Mon's, Wed's is Tue's, etc.
`market_data_daily` itself is fresh (latest=2026-05-08, 2504 rows for each
ticker) so the data is THERE, but the brief is reading from a fixed
snapshot. Likely cause: the brief job is using a stale `as_of` or the
brief wrote on 5/4 and the same row got re-upserted unchanged on the next
3 days (the UNIQUE constraint is on `(analysis_date, ticker)` so rows
should be distinct per day — yet they're identical, which is only
possible if the brief job ran with the same input data each morning).

This is a **Track A / Track B finding** about brief freshness, not a
direct AI-insights bug, but it has knock-on consequences for Track C:
the strat_section the analyst sees may itself have been built off stale
prev-day levels.

### Insights direction by (ticker, day)

| ticker | 5/4 | 5/5 | 5/6 | 5/7 |
|---|---|---|---|---|
| IWM | long | long | flat (catalyst-blocked) | long |
| QQQ | long | long | flat (catalyst-blocked) | long |
| SPY | long | long | long | long |

All directional reports are `long`, with conviction `medium` everywhere
(zero `low` or `high` from the PM). Two reports were forced flat by the
conservative risk persona over upcoming Unemployment Rate / NFP
catalysts on 5/8 (FOMC events were inside the swing-horizon window).

### Convergence

* Brief said **PUT setup** uniformly. Insights said **long** uniformly.
* On QQQ 5/7 specifically, the signal monitor correctly recorded
  `brief_bias=PUT` (138 of 138 alerts that day) and tagged 79 alerts as
  `opposed` and 59 as `aligned`. CALL signals (opposed the brief)
  outnumbered PUT signals (aligned with brief). Of the resolved
  `opposed` CALLs, 16/78 hit target = 20.5%. Of resolved `aligned` PUTs,
  9/53 hit target = 17.0%. Tiny sample, no signal.
* For IWM and SPY 5/7, `brief_bias=CONFLICTED` (PUT setup vs FTFC
  bullish — the brief is internally inconsistent), so `brief_alignment`
  is intentionally NULL on every alert.
* For 5/4, 5/5, 5/6 across all 3 tickers, **`brief_bias` is NULL** on
  every signal_alerts row. Either the brief_bias module wasn't being
  invoked by the live monitor on those days, or the brief was UNAVAILABLE
  in `lib.strategies.brief_bias.get_premarket_bias` at signal time. Worth
  a Track-D follow-up — if the brief existed (it did, per
  premarket_analysis) but the monitor's brief_bias query came back empty,
  there's a query/caching bug.

**Net read:** the insight pipeline and the brief are operating on
disjoint conclusions. They don't share a "house view." Without
ground-truth daily moves for the window (the daily move query returned
0 rows in my Track C dispatch — Track A's freshness check should
double-confirm), I can't grade which one was right; the pure
`opposed`-vs-`aligned` hit-rate gap on QQQ 5/7 isn't significant.

---

## 4. Play quality — entries are technically concrete, but most are placeholders

### Specificity (the STRAT bar)

The Pydantic schema (`lib/agents/schema.py`) **structurally enforces**
concrete numeric `entry_zone.low`, `entry_zone.high`, `stop`, `targets[]`.
There is no "vague entries" failure mode at the data layer — the
response_model would reject prose-only output. Score: **100% concrete by
construction**.

The deterministic `lib.agents.trade_planner` (added per the Apr-7 ARM
hallucination postmortem in `docs/plans/INSIGHT_ZONE_HALLUCINATION_PLAN.md`)
overrides the LLM's numbers with explicit ATR-and-level math. So even
when the LLM picks the wrong number, the headline `entry_zone/stop/targets`
fields come from the trade_planner — **the LLM cannot hallucinate
prices** anymore. This is a major upgrade and Track C verifies it
landed: every report in the window has `entry_zone`, `stop`, and at most
one regime-classified plan set.

### Where it falls down: the `orb_only` regime

| ticker | 5/4 | 5/5 | 5/6 | 5/7 |
|---|---|---|---|---|
| IWM | orb_only | orb_only | normal/flat | orb_only |
| QQQ | orb_only | orb_only | normal/flat | orb_only |
| SPY | orb_only | orb_only | orb_only | orb_only |

`orb_only` is the planner's "every PDH/PWH/PMH/PQH/PYH has been cleared
by pre-market" bucket. When triggered, all three persona plans get
`position_size_pct=0.0`, `targets=[]`, and a rationale telling the
trader to wait for the 15-min opening range. Sample (QQQ 5/7,
neutral persona):

```
"ORB-only: pre-market (+0.20% gap) cleared every structural resistance
level. Wait for the 15-min opening range to establish before entering."
```

A +0.20 % gap should not clear every PDH/PWH/PMH/PQH/PYH on a normal
session. This points back to the **stale-brief-prev-levels finding from §3**:
the planner's `select_trigger_and_regime` is walking against levels it
read out of `compute_strat_status`, which read out of `market_data_daily`
trimmed to `as_of`. If `as_of` was a stale day, the levels the planner
walked are "already cleared" by today's pre-market — yielding a spurious
`orb_only` classification.

This makes sense of the data: 9 of 12 reports = `orb_only`, plus the
two `flat` reports that got blocked by risk = **11 of 12 reports
publishable but unactionable as concrete plays for the morning open**.

### Thesis text (LLM narrative)

The LLM thesis in every report **does** name concrete trigger prices —
sample excerpts:

* SPY 5/4: *"as long as SPY holds above 712.29, targeting 723.33 and
  730.0"*
* IWM 5/7: *"Breaking above 278.13 and reclaiming the gamma flip at
  275.24 would further support the bullish thesis"*
* QQQ 5/7: *"targeting 677.8, 691.09 and 704.38, while being mindful of
  the 618.15 gamma flip level"* — **but `targets=[]` in the JSON** because
  the plan was overridden to `orb_only`.

The narrative and the executable plan are decoupled — the LLM writes
specific levels in the prose, then the deterministic planner replaces
the JSON `targets` with placeholders. A trader reading the thesis on
the brief embed sees 677.8/691.09/704.38; a trader reading the
persona-plan card sees `targets=[]`. The two presentation surfaces
disagree. That's a UX bug at a minimum; arguably it's also a logic
bug — if the LLM and the planner picked different levels, *one of them
is wrong*.

### Invalidation text — concrete every time

Every report's `invalidation` field is a single concrete sentence with
a price level:

* "Price closes below 651.22"
* "Break below 712.29"
* "Breakdown below 660.69"

These are usable as STRAT-style invalidations. **Specificity score
on invalidation: 12/12 = 100 %.**

---

## 5. Strategy factor analysis — the scoring layer

### Factor inventory (from source)

`lib/strategies/momentum.py` (Phase 0.7.x as of 5/6 main):

**Momentum CALL — 7 conditions** split into CORE + CONFIRMING:

| Tier | Factor | What it checks |
|---|---|---|
| CORE | `consecutive_up` | `Consecutive_Up >= 3` (note: 3-of-3 strict; the 3-of-5 relaxed `Consecutive_Up_5` column exists but is **unused** because PR-1 walk-forward showed regression — config.py:62 documents this) |
| CORE | `rsi_bullish_recovery` | RSI ∈ (Tier-A range, default 25–50) |
| CORE | `above_vwap` | `Close > VWAP` |
| CORE | `above_ema9` | `Close > EMA9` |
| CONFIRM | `rvol_above_recent` | `RVol_Recent_20 > 1.2` (median-based, robust) |
| CONFIRM | `atr_expansion` | `ATR_Expansion > 1.15` (5-bar / 20-bar ATR ratio) |
| CONFIRM | `rsi_thrust` | `RSI_Thrust_3 > +5.0` (signed 3-bar RSI delta) |

**Momentum PUT — mirror 7** with `consecutive_down`, `rsi_bearish_recovery`,
`below_vwap`, `below_ema9` as core; same 3 confirmers. (`rsi_thrust` for
PUT triggers on `RSI_Thrust_3 < -5.0`.)

**Gates (`lib/strategies/config.py:107-108`, `momentum.py:200-212`):**

* `MIN_CONDITIONS_MOMENTUM = 5` (raised 2026-05-06 from 3)
* `MIN_CORE_CONDITIONS = 2` (added in same PR, prevents "3 confirmers,
  zero core" pure-noise fires)

`lib/strategies/mean_reversion.py`:

**Mean-reversion CALL — 5 conditions** (no formal core/confirm split):

| # | Factor | What it checks |
|---|---|---|
| 1 | `consecutive_down` | `Consecutive_Down >= 3` |
| 2 | `rsi_oversold_zone` | RSI ∈ Tier-A (default 25–50) |
| 3 | `below_vwap` | `Price_vs_VWAP < 0` |
| 4 | `stoch_rsi_oversold` | `StochRSI_K < 30` |
| 5 | `level_break_pdh` | `Broke_Prev_Day_High = 1` |

**Mean-reversion PUT — mirror 5** with `consecutive_up`,
`rsi_overbought_zone`, `above_vwap`, `stoch_rsi_overbought`, `level_break_pdl`.

`MIN_CONDITIONS = 3` for mean-reversion (legacy threshold, not yet
walk-forward-calibrated per the comment at config.py:96).

So the user's "3-of-8" intuition is roughly right but the actual ratios
are:

* Momentum: floor at **5-of-7 with ≥2-of-4 core** (post Phase 0.7.x).
  The "3 of 8" days for momentum are gone.
* Mean-reversion: floor at **3-of-5**. This is where most of the
  weak-conviction `(3/5)` brief tags come from.

### Factor introduction history (anomaly check)

Three Phase 0.7.x momentum confirmers were added in the same PR (#262,
2026-05-06) with these justifications from the commit body:

| Factor | Added in | Justification claim | Walk-forward evidence |
|---|---|---|---|
| `rvol_above_recent` | PR #262 (5/6) | "median-based RVOL, robust to outlier-volume bars" | None in the commit message; Phase 0.7.x scoring tested holistically |
| `atr_expansion` | PR #262 (5/6) | "regime expansion = tradeable conditions" | Holistic Phase 0.7.x walk-forward only |
| `rsi_thrust` | PR #262 (5/6) | "complements rsi_bullish_recovery (level test) with delta test" | Holistic Phase 0.7.x walk-forward only |

The commit message does cite walk-forward results that justified
*raising* `MIN_CONDITIONS_MOMENTUM` from 3 to 5: *"score-bucket walk-
forward against IWM Nov 2025 + QQQ Sep 2020 (5-min bars) showed score 3
and 4 fires net-negative after typical 0.02-0.04% spread+slippage costs.
Only score>=5 clears costs"* — that's good evidence the threshold is
right. But it doesn't isolate which of the three new confirmers
contributed the lift. The audit PR (#229, 2026-05-02) that *removed* free-
score conditions by contrast cited specific bar-level fire rates
(stoch_rsi_not_overbought = 72.2%, near_below_emas = 84.6%) which is the
gold standard. The new confirmers don't have that level of evidence in
the commit log.

**Anomaly check verdict:** the three new confirmers were NOT introduced
on a single-backtest n=1 anomaly — they survive the holistic
walk-forward Phase 0.7.x bumped `MIN_CONDITIONS_MOMENTUM` to 5 against.
But the per-factor discrimination data the user asked for is missing
from the commit history. **Recommendation:** before any of these gets
demoted/dropped, run the same Phase 0.7.1-style "fire rate per bar"
audit that retired `stoch_rsi_not_overbought`. If a factor fires on
>50 % of bars, it's "free score" no matter how plausible its prose.

### Factor fire-rate analysis for May 4-7

`signal_alerts.conditions_met` is stored as a **JSONB string of a JSON
array** rather than a native JSONB array (`jsonb_typeof = 'string'` for
all 782 rows in the window, 1250 over the 30-day baseline). A
`(conditions_met #>> '{}')::jsonb` double-decode unblocks expansion;
the long-term fix is to make `gcp/signal_monitor.py` write arrays
directly. Sample value: `"[\"consecutive_up\", \"rsi_overbought_zone\",
\"above_vwap\"]"` — i.e. JSON-encoded string. Functional but breaks
indexing / type-safe queries. **P0 to fix the writer.**

Once the workaround is applied, the factor-fire data for May 4-7 across
SPY+IWM+QQQ falls out as:

| factor | direction | n fires | hits | losses | unres. | hit rate (resolved) |
|---|---|---|---|---|---|---|
| stoch_rsi_oversold     | CALL | 321 | 24 | 192 | 105 | 11.1 % |
| below_vwap             | CALL | 308 | 27 | 202 | 79  | 11.8 % |
| rsi_oversold_zone      | CALL | 258 | 24 | 153 | 81  | 13.6 % |
| consecutive_down       | CALL | 183 | 10 | 102 | 71  |  8.9 % |
| stoch_rsi_overbought   | PUT  | 401 | 14 | 104 | 283 | 11.9 % |
| above_vwap             | PUT  | 368 | 11 |  69 | 288 | 13.8 % |
| rsi_overbought_zone    | PUT  | 358 | 11 |  95 | 252 | 10.4 % |
| consecutive_up         | PUT  | 248 | 10 |  76 | 162 | 11.6 % |

**Two findings jump out, both important:**

1. **The momentum strategy is not firing in production.** Of the eight
   factor names present, **all eight are mean-reversion factors**.
   Momentum's seven distinguishing factors — `above_ema9`,
   `rvol_above_recent`, `atr_expansion`, `rsi_thrust`,
   `rsi_bullish_recovery`, `rsi_bearish_recovery`, `below_ema9` — appear
   on **zero** alerts. Combined with the 5/6 raise to
   `MIN_CONDITIONS_MOMENTUM = 5` plus `MIN_CORE_CONDITIONS = 2` plus
   `Consecutive_Up >= 3` strict (the 3-of-5 relaxation was retracted —
   `config.py:62`), the momentum gate is now too high to trip on these
   tickers in the current regime. Whether that's a feature or a bug
   depends on whether the audit-period regime would have been one where
   momentum should have fired; either way, **the live signal-alerts
   table is showing pure mean-reversion output** which a reader of the
   "two-strategy parallel research path" plan would not expect.

2. **The Strat-aligned `level_break_pdh` / `level_break_pdl` factor
   never fires.** Mean-reversion has 5 conditions; we see 4 in the
   data. The fifth — the only one that uses Rob Smith Strat-style
   prior-day-level breaks — is silent. Either the
   `Broke_Prev_Day_High` / `Broke_Prev_Day_Low` indicator columns
   aren't being populated, or no PDH/PDL was actually broken in the
   window (consistent with the "frozen brief levels" finding from §3 —
   if the levels themselves are stale, "did price break them?" is
   trivially false).

**Discrimination is poor across the board.** Hit rates for resolved
fires cluster tightly between 8.9 % and 13.8 % — a 4.9-point spread
across all eight factors over a 4-day window with sample sizes 183-401.
Given binomial noise at n=180-400, that range isn't statistically
distinguishable. **No factor in this window had a discrimination edge.**

**Co-fire pattern (qualitative, from the sample row inspection):** the
canonical PUT fire at 9:25 ET on 5/4 across all three tickers shows
`["consecutive_up","rsi_overbought_zone","above_vwap"]` — exactly 3 of
5 mean-reversion PUT conditions, the minimum to clear `MIN_CONDITIONS=3`.
The dominant pattern is that `stoch_rsi_*` and `*_vwap` are riding the
gate together.

This dataset is too small (4 days, 782 alerts, only one strategy
firing) to drive a "drop factor X" decision. But it absolutely
suffices to flag that **the strategy mix is degenerate** — only
mean-reversion is producing alerts, and within mean-reversion, the
fifth (Strat-aligned) factor isn't engaging. That's a P0.

### What I CAN say about factors from the visible data

Even without per-factor expansion, the aggregate signal-volume data
(via Track D's batch result for the same window) tells a story:

| ticker | 5/4 | 5/5 | 5/6 | 5/7 | 5/4-7 total |
|---|---|---|---|---|---|
| IWM CALL/PUT | 11/20 | 7/39 | 11/23 | 86/25 | 115/107 = 222 |
| QQQ CALL/PUT | 9/11 | 8/42 | 17/57 | 79/59 | 113/169 = 282 |
| SPY CALL/PUT | 11/17 | 15/44 | 8/46 | 82/55 | 116/162 = 278 |
| **TOTAL** | **79** | **155** | **162** | **386** | **782** |

* **5/7 has 5x the alert volume of 5/4** (386 vs 79). This is not
  expected on a normal week without a big news catalyst — it suggests
  the gates are **firing too often on 5/7 specifically**.
* On 5/4–5/6, the exit watcher logged **0 target-hits, 0 time-stops,
  0 RSI exits** — every alert has `exit_reason=NULL`. This means the
  exit watcher wasn't writing exit columns those days, or the open
  positions were rolled at session end without resolution. (Track D
  finding, but mentioned because it bounds Track C's "did this play
  trigger?" analysis.)
* On 5/7, exit reasons populated for the first time in the window:
  IWM CALL 11/86 = 12.8% target-hit, IWM PUT 5/25 = 20% target-hit,
  QQQ CALL 16/79 = 20.3%, QQQ PUT 9/59 = 15.3%, SPY CALL 0/82 = 0%
  (78 hit time stop), SPY PUT 0/55 = 0% (45 time-stop, 8 RSI exit).
  **SPY hit 0/137 = 0% target-hit on 5/7**. That's a huge red flag for
  the strategy mix on SPY but it's a Track-D depth question.

### Recommended factor work (KEEP / DEMOTE / DROP)

I cannot give a per-factor verdict from this dataset because the
expansion is broken. Conservative recommendations based on what's
known:

| Factor | Strategy | Recommendation | Rationale |
|---|---|---|---|
| `consecutive_up`/`down` (3-of-3) | momentum CORE | **KEEP** | Walk-forward retraction of the 3-of-5 relaxation is documented at config.py:62 |
| `rsi_bullish_recovery`/`bearish_recovery` | momentum CORE | **KEEP** | Tier-A per-ticker calibration (PR #248) makes this the only factor with empirical per-ticker tuning |
| `above_vwap`/`below_ema9` etc. | momentum CORE | **KEEP** | Pure structural — they define "momentum" |
| `rvol_above_recent` | momentum CONFIRM | **KEEP pending audit** | Plausible; no per-factor walk-forward in commit log |
| `atr_expansion` | momentum CONFIRM | **KEEP pending audit** | Same — needs the §3.10-style fire-rate audit before keeping permanently |
| `rsi_thrust` | momentum CONFIRM | **KEEP pending audit** | Same |
| `stoch_rsi_oversold`/`overbought` | mean_rev | **KEEP** | Already pruned the "not_overbought" version in PR #229; the directional version remains |
| `level_break_pdh`/`pdl` | mean_rev | **KEEP** | This is the actual Strat-style level-break; high-quality |
| `consecutive_down`/`up` (mean-rev side) | mean_rev | **KEEP** | The mean-reversion fader's structural anchor |
| `rsi_oversold_zone`/`overbought_zone` | mean_rev | **KEEP** | Same as momentum — Tier-A calibration applies |

**Recommended `MIN_CONDITIONS` post-prune:**

* Momentum: keep `MIN_CONDITIONS_MOMENTUM = 5` and `MIN_CORE_CONDITIONS = 2`.
  The 5/6 raise is well-supported.
* Mean-reversion: **investigate raising `MIN_CONDITIONS` from 3 to 4**.
  Rationale: with 5 conditions and a 3-floor, the gate fires at 60 %
  filled — comparable to where momentum was before the 5/6 tightening.
  The same walk-forward methodology that justified raising momentum to 5
  hasn't been run on mean-reversion. Mean-reversion's `MIN_CONDITIONS`
  is on the same trajectory momentum was on before Phase 0.7.x.

**Best plays to lean into (for the brief / Discord embed):**

For May 4-7, the highest-volume "win" pattern was the
`above_vwap + stoch_rsi_overbought + rsi_overbought_zone + consecutive_up`
4-condition mean-reversion PUT fire — but its hit rate (11–14 %) is
indistinguishable from the loss rate. **No combination in this window
showed reliable edge.** The empirical conclusion is "don't trade May 4-7
without an out-of-sample regime check" rather than "lean into pattern X."

A useful follow-up Track-D could run, once the conditions_met scalar fix
lands, is the same factor expansion against a 90-day window — the
4-day sample is too thin for KEEP/DROP per-factor verdicts. The 30-day
baseline shows 1,250 alerts which is enough sample size for n=8
factors but I didn't get to run that query before time ran out on the
audit window.

---

## 6. Cost discipline

12 reports / 4 days × 3 tickers = ~$0.011 / day. Annualized: $4.00 /
year for the scheduled batch. The Cloud Run job's 8:45 AM cron is the
only scheduled invocation (verified via `INSIGHT_TICKERS=SPY,IWM,QQQ`
default in `gcp/insight_pipeline_job.py:56`). On-demand refreshes via
the `/api/insights/report/{ticker}/refresh` endpoint are not in the
window (no `trigger=on_demand` rows).

The 4/24 incident referenced in `gcp/insight_pipeline_job.py:60` (a
manual 152-ticker run that burned ~$1.20) is now guarded by
`DEFAULT_MAX_BATCH = 10` with `INSIGHT_BATCH_OVERRIDE=1` to bypass.
Cost surface is tight.

**No cost concerns.** The hard cost ceiling is well within budget;
the soft cost concern would be quality (the 9/12 orb_only rate means
~75 % of the $0.011/day is producing reports a trader can't act on).

---

## 7. Backlog (issues to file)

Priority follows the synthesis-track scheme: P0 = data correctness, P1 =
quality regression, P2 = tuning, P3 = docs.

### P0 — investigate stale prev-day levels in brief and insights bundle
**Track A/B/C joint.** All four mornings produced identical
`prev_day_high/prev_day_low/price` rows in `premarket_analysis` for each
ticker. With `market_data_daily` actually fresh through 5/8, this points
to a `compute_strat_status`-or-earlier upstream that's reading a fixed
`as_of`. The downstream effect on insights is the spurious
`regime=orb_only` classification on 9/12 reports — when the level set
is stale, every fresh pre-market gap looks like it cleared every level.
Owner: data-pipeline track. Surface area: `gcp/premarket_brief.py`,
`lib.strat.compute_strat_status`, `lib.strat_levels.compute_previous_levels`.

### P0 — `signal_alerts.conditions_met` stored as JSON-string-of-array
Production rows in the May 4-7 window have `jsonb_typeof = 'string'`
across 782 of 782, with literal contents like `"[\"consecutive_up\",
\"rsi_overbought_zone\", \"above_vwap\"]"`. The writer is `json.dumps`-
ing the list AND THEN passing it to a JSONB column, producing
double-encoded JSON. Cosmetic compatibility workaround:
`(conditions_met #>> '{}')::jsonb`. Real fix: write a Python list (which
pg8000/psycopg2 will adapt as JSONB array directly) instead of a
pre-stringified payload. Likely surface area: `gcp/signal_monitor.py:707`
or whichever upsert helper persists alerts. Backfill is a one-statement
`UPDATE signal_alerts SET conditions_met = (conditions_met #>> '{}')::jsonb`.

### P0 — momentum strategy producing zero alerts
Across 782 alerts in May 4-7 (and 1,250 over the 30-day baseline), all
factor names appearing in `conditions_met` are mean-reversion factors.
None of `above_ema9`, `rvol_above_recent`, `atr_expansion`, `rsi_thrust`,
`rsi_bullish_recovery`, `rsi_bearish_recovery`, `below_ema9` appear on
any row. The 5/6 raise of `MIN_CONDITIONS_MOMENTUM` to 5 plus the
retracted 3-of-5 relaxation plus `MIN_CORE_CONDITIONS=2` may have made
the gate uncrossable in low-volatility regimes. Track D should (a)
confirm the live signal_monitor is actually evaluating the momentum
strategy each bar, (b) instrument a dry-run counter for "momentum-
considered" vs "momentum-fired" to see whether the 5-of-7 floor or the
2-of-4 core floor is the binding constraint.

### P0 — `level_break_pdh` / `level_break_pdl` factor never fires
The fifth mean-reversion factor (`Broke_Prev_Day_High = 1` or low) — the
only Strat-style factor in the set — appears on **zero** alerts in the
window. Either the indicator columns aren't being populated by
`lib.indicators.add_all_indicators` (or the equivalent in
`lib.trading_analysis`), or the prev-day-levels aren't being broken
because the brief data is frozen (P0 above) so the levels themselves
are stale. Cross-reference with Track A's data-freshness verdict.

### P0 — exit-watcher results missing for May 4, 5, 6
On 5/4-5/6, **0 of 396** alerts have any exit_reason populated. On 5/7,
360 of 386 are resolved. Either the exit-watcher (`gcp/signal_monitor.py:801`)
wasn't running on those mornings and only caught up when 5/7 fired, or
the resolution logic only processes "today's" alerts and old ones never
backfill. This is Track D's territory but it bounds Track C's read on
play quality — most of the alerts in this window are simply unresolved,
so the apparent "0 / 78 SPY CALL hit rate" on 5/7 isn't comparable to
the unresolved 5/4-5/6 days.

### P1 — orb_only over-classification for normal sessions
`select_trigger_and_regime` returns `orb_only` when "every structural
level in trade direction has been cleared." Out of 12 reports,
9 hit this branch in a 4-day window. Even granting the stale-levels
P0 above, the planner should fall back to a 15-min ORB plan with a
*real* numerical entry zone (the ORB high) once the 9:45 ORB has
formed, not a placeholder. Today the report is published at 8:45
with `regime=orb_only` and never refreshed.

### P1 — brief↔insights direction divergence
Brief said PUT setup uniformly; insights said long uniformly. The
brief's CONFLICTED status on IWM/SPY 5/7 reflects an internal brief
inconsistency (PUT setup + bullish FTFC). The insights pipeline is
free to disagree with the brief on principle (brief looks at one
day's strat candle; insights looks at gamma + sentiment + catalysts +
analog history) but a discretionary trader cannot easily reconcile two
opposite house views. **Recommendation:** when the brief and insights
disagree, surface that explicitly in the platform UI ("brief: PUT,
insights: long — disagreement reasons: …") rather than letting one
drown out the other.

### P1 — thesis-vs-targets decoupling
The LLM's `thesis` text names specific target levels (e.g. QQQ 5/7
"targeting 677.8, 691.09 and 704.38") that don't appear in the JSON
`targets` array. The deterministic planner correctly overrides the
LLM's numbers to prevent hallucination, but it doesn't sanitize the
narrative text. **Fix options**: (a) post-process the thesis to replace
LLM-named levels with the planner's numbers, or (b) make the prompt
forbid level names in the thesis text and put all numbers in
`key_levels`/`targets`/`entry_zone`/`stop` only.

### P1 — brief_bias missing for 11/12 (ticker, day) pairs
Only QQQ 5/7 had `brief_bias` populated on its `signal_alerts` rows.
For the other 11 (ticker, day) combinations brief_bias is NULL, so
`brief_alignment` is also NULL. The brief existed on every day (12/12
premarket_analysis rows). Either the live monitor's
`get_premarket_bias()` lookup is failing silently, or the column wasn't
being written before some recent date. Track D has the right tooling
to investigate (`gcp/signal_monitor.py:707`).

### P2 — per-factor walk-forward audit (on top of P0 fix)
Once `conditions_met` is fixed AND momentum is actually firing, run the
same §3.10 fire-rate methodology that retired `stoch_rsi_not_overbought`
in PR #229 against the three Phase 0.7.x confirmers (`rvol_above_recent`,
`atr_expansion`, `rsi_thrust`). For each: per-bar fire rate, win-rate-
on-fire vs win-rate-overall, walk-forward stability across folds.
Demote any that fire on >50 % of bars OR fail discrimination. This is
the user's "factor → KEEP/DEMOTE/DROP" deliverable, blocked on P0
(momentum-not-firing).

### P2 — strategy_agreement field never populated
For all 24 (date, ticker, direction) combinations in the window
`agreed=0`. Either both strategies aren't firing on the same bar (likely
given P0 above — only mean-reversion is firing) or the agreement
detector in `lib/strategies/agreement.py` isn't being invoked. The
"stacked-signal" boost mechanism documented at
`gcp/schema.sql:744-760` is dormant. Pair this audit with the momentum-
not-firing P0; if mean-reversion is the only strategy operating, agreement
is structurally impossible.

### P2 — mean-reversion `MIN_CONDITIONS` = 3 not walk-forward calibrated
The `momentum.py` walk-forward bumped momentum's gate to 5/7. Mean-
reversion's gate stays at 3/5 and has no walk-forward record in commits.
Run the same score-bucket analysis (5-min IWM/QQQ over 30+ days) to
establish whether `MIN_CONDITIONS = 3` clears spread+slippage costs or
whether it should be 4.

### P2 — model_routing /admin UI is dormant
All 7 roles point at the same `vertex:gemini-2.0-flash`. The /admin per-
role swap UI exists but nothing diversifies. Either commit to "all
roles use one model" and remove the UI complexity, or run a 1-week A/B
where the `judge` role uses a stronger model (e.g. Gemini 2.5 Pro) to
see if the verdict quality improves.

### P3 — conviction collapsing to `medium`
Every report in the window is `conviction=medium`. The `low|medium|high`
enum exists for a reason; if the PM never picks low or high, the field
isn't differentiating quality. Worth looking at the prompt and example
distribution in the PORTFOLIO_MANAGER_PROMPT.

---

## Appendix A — Source data locations

GitHub Actions runs (db-query.yml workflow against tracking issue #236):

| Run ID | Purpose |
|---|---|
| 25557141173 | schema check + insight_reports row count for window |
| 25557929799 | insight_reports flat fields, premarket_analysis, sample report |
| 25558266103 | model_routing, thesis excerpts, market_data_daily freshness |
| 25558486830 | conditions_met type breakdown (string), strategy_agreement |
| 25558938073 | factor expansion via double-decode workaround |

Local artifact files (`/tmp/q*/result_*.csv` after `gh run download`):

| Result | File |
|---|---|
| Pipeline ran 12/12 reports | run 25557141173 (schema + counts) |
| insight_runs status/latency for 12 rows | `/tmp/qC/result_002.csv` |
| Flat insight_reports fields incl. direction/regime/strat | `/tmp/qC/result_004.csv` |
| Premarket_analysis 12 rows (identical-across-days content) | `/tmp/qC/result_006.csv` |
| Full QQQ 5/7 report payload (sample) | `/tmp/qC/result_016.csv` |
| market_data_daily freshness (latest 5/8, 2504 rows each) | `/tmp/qD/result_004.csv` |
| signal_alerts brief_alignment populated breakdown | `/tmp/qD/result_006.csv` |
| model_routing snapshot (all 7 roles → vertex Gemini Flash) | `/tmp/qD/result_010.csv` |
| Thesis/invalidation excerpts per (ticker, day) | `/tmp/qD/result_012.csv` |
| conditions_met JSONB type breakdown (782/782 string) | `/tmp/qE/result_002.csv` |
| Sample raw conditions_met values | `/tmp/qE/result_004.csv` |
| 30-day conditions_met type breakdown (1250/1250 string) | `/tmp/qE/result_006.csv` |
| signal_alerts row count + open/resolved by day | `/tmp/qE/result_008.csv` |
| strategy_agreement breakdown (all `agreed=0`) | `/tmp/qE/result_010.csv` |
| **Factor fire rates with double-decode workaround** | `/tmp/qF/result_002.csv` |

## Appendix B — Files read for the integration audit

| File | Purpose |
|---|---|
| `lib/agents/orchestrator.py` | 11-node graph, deterministic key_levels and persona-plan injection |
| `lib/agents/summarizers.py:201-300, 1229-1264` | Strat & context-bundle assembly |
| `lib/agents/prompts.py` | All 11 system prompts; trigger-price requirement embedded in TRADER_PROMPT |
| `lib/agents/schema.py` | Pydantic models that enforce concrete entry/stop/targets |
| `lib/agents/trade_planner.py:1-490` | Deterministic per-persona plans + select_trigger_and_regime + orb_only fallback |
| `lib/agents/model_routing.py` | RouteSnapshot + connect() with pg8000 over Cloud SQL Connector |
| `lib/strategies/momentum.py` | Phase 0.7.x momentum (7 conditions, 4 core / 3 confirm) |
| `lib/strategies/mean_reversion.py` | 5-condition mean-reversion |
| `lib/strategies/config.py` | Tier-B fallback + MIN_CONDITIONS thresholds |
| `lib/strategies/brief_bias.py` | Brief→live monitor coordination layer |
| `lib/indicators.py:600-690` | Phase 0.7.x indicator population (RVol_Recent_20, ATR_Expansion, RSI_Thrust_3) |
| `gcp/insight_pipeline_job.py` | Cloud Run job entry point, scheduled vs on_demand modes |
| `gcp/premarket_brief.py:760-800` | Brief computes the same Strat snapshot via `compute_strat_status` |
| `gcp/schema.sql:702-1850` | signal_alerts, insight_reports, model_routing, brief_bias columns |
