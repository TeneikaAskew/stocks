# Corrected Baseline (re-replay 2026-05-10, post clock-source fix)

**Supersedes:** earlier draft at `docs/replays/2026-05-10-corrected-baseline.md` (which was contaminated by the clock-source bug PR #406 just fixed)
**Replay window:** 2026-05-04 → 2026-05-08 (5 trading days, SPY/IWM/QQQ)
**Image:** `us-east1-docker.pkg.dev/adept-mountain-474619-d4/trading/trading-system@sha256:55f0747c42505d9c4bdc454dd59dcae4eb377add09b0f62a7293e5dbcd005ce5`
**Built from:** `main` HEAD `95263ef` — includes PR #400 (analysis_date + replay leakage) + PR #406 (clock-source fix)
**Replay mode:** `signal-monitor --mode=replay --json` via Cloud Run Job
**Wall-clock:** ~2 min/execution (vs ~7 min in the pre-clock-fix replay — the brief-bias resolver no longer hits the wrong-date lookup-failed retry loop)

---

## 1. Headline finding

The clock-source fix is **working** but the **direction-misalignment problem persists**, because FTFC affects only `total_score` / `strength_label`, not whether `fire_alert` is called. The 60.6% (or higher) opposite-direction rate from the pre-fix baseline is not a data artifact — it's a structural property of the indicator-scoring layer.

| Measurement | Pre-clock-fix (contaminated) | Post-clock-fix (clean) |
|---|---|---|
| Total fires across 5/4–5/8 (3 tickers) | 3,149 | 3,149 (identical) |
| Fires with `total_score` changed by FTFC | n/a (FTFC was 0) | 60 of 74 matched fires (81%) |
| Largest opposing-fire penalty | n/a | −5.00 (5/6 13:56 SPY PUT: 6.00 → 1.00) |
| Largest aligned-fire boost | n/a | +4.75 (5/6 11:59 SPY CALL: 1.25 → 6.00) |
| Aligned fires boosted weak→medium tier | n/a | 7 |
| Opposite fires demoted medium→weak tier | n/a | 5 |

**Why fire counts didn't change:** `signal_monitor.evaluate_ticker` calls `fire_alert` for every scored signal regardless of FTFC. FTFC only changes the **strength label** assigned to the fire, not whether the fire happens.

**This matters for the Phase 1 gate design.** A strength-aware direction gate can use the new (now-correct) strength labels: opposing weak fires become more numerous post-fix because counter-FTFC PUTs that were "medium" pre-fix are now "weak" post-fix. The gate's suppression logic then catches them.

---

## 2. Methodology

### 2.1 What changed since the earlier draft

The earlier `docs/replays/2026-05-10-corrected-baseline.md` was generated from a replay that:
- Used the correct strat_levels (PDH/PDL/PWH/etc.) — PR #400 fix loaded
- Used the correct AS-OF query semantics for summarize_market_context — PR #400 fix loaded
- But used **wall-clock-now** for `_resolve_brief_bias` and catalyst-proximity lookups (the bug PR #406 fixed)

Result: every fire was scored with `ftfc_score=0.0` because the brief-bias lookup queried `premarket_analysis WHERE analysis_date=today` (2026-05-10, empty) instead of `WHERE analysis_date=replay_date`. PR #379's FTFC fix was code-correct but architecturally inert during replay.

### 2.2 What's clean now

- Replay clock per bar is wired through `SignalMonitor._now()` → `replay_clock_ts` (PR #406)
- The brief-bias resolver finds the correct date's `premarket_analysis` row
- Catalyst proximity uses bar-time
- FTFC scores from `premarket_analysis.ftfc_score` (range 0.25 to 1.0 across the window, mostly 1.0 bullish) flow into `Strat.get_strat_bonus` and shift `total_score` per bar

### 2.3 Sample limitations (unchanged from earlier draft)

- Cloud Run logs truncate the per-fire JSON output at ~85-160 records per execution. Full `captured_fires` lengths are 500+ per execution. The aggregate fire counts in §3.1 come from the (single-line, non-truncated) `REPLAY SUMMARY` block. Per-fire detail comes from the truncated JSON.
- Hermetic replay doesn't simulate exits → no `exit_return_pct` for the post-fix fires. Win-rate by strength tier still pending Phase 1 prereq #404 (`REPLAY_PERSIST` mode).

---

## 3. Data

### 3.1 Fire counts (unchanged from pre-clock-fix replay)

| Date | SPY | IWM | QQQ | Total | CALL | PUT |
|---|---|---|---|---|---|---|
| 2026-05-04 | 361 | 106 | 157 | 624 | 411 | 213 |
| 2026-05-05 | 360 | 166 | 54 | 580 | 304 | 276 |
| 2026-05-06 | 335 | 110 | 118 | 563 | 348 | 215 |
| 2026-05-07 | 405 | 180 | 234 | 819 | 631 | 188 |
| 2026-05-08 | 380 | 126 | 57 | 563 | 252 | 311 |
| **Total** | **1,841** | **688** | **620** | **3,149** | **1,946** | **1,203** |

(Counts identical to the pre-clock-fix replay because FTFC doesn't gate fires — only changes strength.)

### 3.2 Score-tier transitions from the FTFC fix (JSON sample, 74 matched fires across 5/4-5/8)

Matched by `(timestamp, ticker, direction)` between pre- and post-clock-fix logs:

| Transition | Count | What it means |
|---|---|---|
| Opposite-direction fire demoted ≥5 → <5 | **5** | Counter-FTFC PUTs on bullish-FTFC days got the penalty they were supposed to get; their `strength_label` flips from medium → weak |
| Aligned-direction fire boosted <5 → ≥5 | **7** | Aligned-FTFC CALLs on bullish-FTFC days got the +ftfc_bonus they were supposed to get; their `strength_label` flips from weak → medium |
| Score unchanged | 14 | FTFC delta below the strength-tier boundary |
| Score changed but stayed in tier | 48 | Most common case — FTFC delta visible but not big enough to flip tier |

### 3.3 Top individual score deltas

```
Counter-FTFC penalties (PUT on bullish-FTFC day, biggest hits):
  2026-05-06 13:56 SPY PUT  6.000 →  1.000  (Δ=-5.000)
  2026-05-06 14:09 SPY PUT  5.250 →  1.250  (Δ=-4.000)

Aligned-FTFC boosts (CALL on bullish-FTFC day, biggest hits):
  2026-05-06 11:59 SPY CALL 1.250 →  6.000  (Δ=+4.750)
  2026-05-06 07:58 SPY CALL 5.000 →  5.500  (Δ=+0.500)
```

The 5/6 SPY example is exactly the case PR #379's commit message called out: counter-bullish-FTFC PUTs on 5/6 SPY were "escaping the −ftfc_bonus penalty they were supposed to receive." They now get it.

---

## 4. Phase 0 decision tree (re-applied)

Per `docs/audit/2026-05-10/post-open-insight-architecture.md` §2.3:

| Outcome (post-clock-fix replay) | Decision |
|---|---|
| Opposite rate stays >50%, opposite win rate <40% | **PROCEED to Phase 1** |
| Opposite rate drops to 40-50% | PROCEED with conservative gate |
| Opposite rate drops below 35% | RECONSIDER |

**Status**: Pre-fix opposite rate was 60.6% (live full-RTH) with 32.1% win rate. The clock fix doesn't change which direction the indicator-scoring layer fires — it only changes the **score** of those fires. The opposite rate is fundamentally a property of the per-bar RSI/MACD/momentum scoring; it doesn't reduce post-FTFC-fix.

**What DOES change post-fix**: the score-tier (weak/medium/strong) distribution. Counter-trend fires that were "medium" pre-fix are correctly demoted to "weak" post-fix, which is exactly the signal the Phase 1 direction gate uses to suppress them.

**Decision: PROCEED to Phase 1**, with the modified design from §5 below.

---

## 5. New blocker for Phase 1: conviction is structurally pinned to "low"

While analyzing the corrected baseline, I queried the conviction breakdown for 5/4–5/8 (posted as findings on issue #405). **15/15 ticker-days have `conviction='low'`**, but **not because FTFC is wrong** — because the risk-reviewer LLMs are issuing false-positive `warn` and `block` flags at scale.

The two block flags (5/6 IWM, 5/8 IWM) are real-looking but mis-calibrated:
- `"Stop loss is too wide at $5.67, exceeding defined risk parameters"` — risk-parameter rule mis-set for IWM volatility
- `"Price is far above the 200 SMA. This is a contrarian signal"` — wrong-headed for trend-following longs

The 13 non-blocked days hit 4–7 warn flags each. Top recurring false-positives:

| Flag (origin persona) | Frequency | Why false |
|---|---|---|
| `"Stop loss is smaller than one ATR"` (neutral) | ~13/15 | LLM is mis-comparing entry-zone-low minus stop vs ATR — math wrong, even when actual distance is >1 ATR |
| `"Stop loss > 1% of current price"` (conservative) | ~7/15 | Index-ETF ATR stops are routinely 1.5–3% of price; rule rejects every legitimate stop |
| `"Targets too close"` (aggressive) | ~14/15 | Persona preference, not risk; should be info, not warn |
| `"Price far above 200 SMA = contrarian"` (conservative) | ~5/15 | Inverts trend-following methodology |

`_calibrate_conviction` at `lib/agents/orchestrator.py:840` deterministically forces conviction=low when:
- Any block flag → `low` AND direction=`flat`
- >1 warn flag → cap at `medium` (cannot reach `high`)

Result: conviction is always low → Phase 1's conviction-weighted direction gate (per the phased plan §3.3 matrix) would degrade to **annotate-only on every fire — no actual suppression happens, no boost happens, the gate has zero effect**.

This was the matrix from the original phased plan:

| Insight direction | Conviction | Opposing weak | Aligned weak |
|---|---|---|---|
| long/short | **low** | **annotate only** | no upgrade |
| long/short | medium | suppress | upgrade to medium |
| long/short | high | suppress | upgrade to medium |

If 100% of days have conv=low → 100% of fires get annotate-only. Phase 1 has no effect.

---

## 6. Phase 1 design pivot — drop conviction-weighting in v1

To unblock Phase 1, we drop the conviction-weighting from the v1 matrix:

| Insight direction | Opposing weak | Opposing medium | Opposing strong | Aligned weak |
|---|---|---|---|---|
| long/short | **suppress** | downgrade to weak | keep + tag | no upgrade |
| flat | annotate only | downgrade to weak | keep + tag | n/a |

Rationale:
- **Suppress opposing weak** unconditionally. Opposing weak fires are noise on long-bias days. Pre-fix opposite-direction win rate was 32.1% — well below random. Filtering them is high expected value regardless of conviction.
- **Downgrade opposing medium** to weak. Don't fully suppress (might be a real reversal signal) but reduce sizing.
- **Keep opposing strong with tag**. Strong opposing signals on a directional day are often the actual reversal. Don't kill them; tag them so the trader sees both.
- **No aligned-boost** in v1. Adding "upgrade weak to medium" introduces position-size increases on the long-bias side — too risky without conviction validation.

Phase 1.5 (after issue #405 fixes the risk-reviewer false positives and conviction becomes meaningful again) reintroduces the conviction-weighted matrix.

---

## 7. Updated plan

### Phase 0 — DONE
- ✅ Correctness fixes shipped (PR #400, PR #406)
- ✅ Corrected baseline replayed and analyzed
- ✅ Conviction audit completed (findings on issue #405)

### Phase 1 — Direction Gate (modified)
**Branch:** `feat/insight-direction-gate`
**Scope:**
- Schema additions: `signal_alerts.insight_direction`, `insight_conviction`, `insight_regime`, `gate_action`, `thesis_invalidated`
- `InsightCache` + 60s refresh
- **Conviction-unaware** direction gate (matrix in §6 above) — drops the conviction dependency
- Flat-day behavior (suppress weak momentum; medium requires structural-level proximity)
- Invalidation tripwire (neutral/reversal-watch state)
- Stale-insight handling
- Discord embed enrichment
- `SHADOW_MODE` flag for counterfactual measurement

**Out of scope:** schedule shifts, post-open 9:35 insight, `gap_faded` regime, RTH-so-far context, auto-trigger.

**Pre-reqs:** Issue #404 (`REPLAY_PERSIST` mode) — without it, Phase 1's §3.10 acceptance gates can't be measured cleanly. Build this concurrently with the gate itself.

**Acceptance gates** (per phased plan §3.10):
- Surviving-fire win rate ≥ 50%
- Opposite-direction fire rate ≤ 30%
- Total fire reduction 25–50%
- No per-ticker win-rate drop >3pp
- Missed-winner rate <15% (measured in shadow mode)

### Phase 1α — Risk-Reviewer Fix (PARALLEL with Phase 1)
**Branch:** `fix/risk-reviewer-false-positives`
**Scope:**
- Tighten neutral reviewer prompt: don't issue `stop < 1 ATR` warning unless math actually holds (force structured math output)
- Recalibrate conservative reviewer prompt: drop `stop > 1% of price`, drop `above SMA200 = contrarian for longs`
- Make `_calibrate_conviction` distinguish info-vs-warn (currently treats all non-info as warn)

**Acceptance:** Re-run insight pipeline for 5/4-5/8; conviction distribution should show non-low values (target: ≥30% `medium` or `high`).

**Why parallel:** Phase 1 doesn't depend on this fix, but Phase 1.5 (conviction-weighted gate) does.

### Phase 1.5 — Conviction-Weighted Gate
**Trigger:** Phase 1 in production ≥5 trading days AND Phase 1α landed
**Scope:** Reintroduce conviction weighting per original phased plan §3.3 matrix.

### Phase 2 — Weak-Tier Experiments
**Trigger:** Phase 1 shipped (or in parallel if Phase 0 data justified)
**Scope:** Run 4 experiments (suppress all weak, tighten threshold, gate-only-weak, delete weak entirely). Decide threshold changes from empirical data.

### Phase 3 — Post-Open Insight + gap_faded Regime
**Trigger:** Phase 1 in production ≥5 days, validated
**Scope:** Additive 9:35 insight run (does NOT replace 8:45), RTH-so-far context, `gap_faded_reclaim`/`gap_faded_distribute` regimes. Calibrate `GAP_FADED_ATR_MULT` from a longer backtest, not the 5/4-5/8 sample.

### Phase 4 — Higher-TF Auto-Trigger
**Trigger:** Phase 3 in production ≥10 days, empirical case shown
**Scope:** Build only if Phase 3 data shows insights going stale during sessions where higher-tf regime flipped.

---

## 8. Appendix: replay execution map

| Execution | REPLAY_DATE | log file | duration | summary fires |
|---|---|---|---|---|
| signal-monitor-gbqjd | 2026-05-04 | replay-2026-05-04.log | 1m54s | 624 |
| signal-monitor-nwk99 | 2026-05-05 | replay-2026-05-05.log | 2m04s | 580 |
| signal-monitor-7dl4v | 2026-05-06 | replay-2026-05-06.log | 2m02s | 563 |
| signal-monitor-fmrts | 2026-05-07 | replay-2026-05-07.log | 2m12s | 819 |
| signal-monitor-mn7c6 | 2026-05-08 | replay-2026-05-08.log | 2m06s | 563 |

(Logs in /tmp/baseline2/logs/ — not committed; transient session data.)
