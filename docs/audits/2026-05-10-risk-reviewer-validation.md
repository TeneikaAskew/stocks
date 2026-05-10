# Risk-Reviewer Empirical Validation — 2026-05-10

**Window:** 2026-03-19 → 2026-05-08 (36 trading days, SPY/IWM/QQQ)
**Data source:** insight_reports + market_data_daily + signal_alerts, all replayed/refreshed on the post-fix image (`main` HEAD `95263ef` — includes PR #400 analysis_date fix, replay-leakage fix, and PR #406 clock-source fix)
**Replay command pattern:** `gcloud run jobs execute premarket-brief --update-env-vars=BRIEF_AS_OF=YYYY-MM-DD --async` (Discord suppressed via `BRIEF_AS_OF` triggering the new auto-skip implemented in PR #415)
**Re-replays executed in this session:**
- 36 brief replays — all succeeded, all persisted to `premarket_analysis` + `premarket_analysis_history`
- 36 insight-pipeline replays — all succeeded, all persisted to `insight_reports` (upsert on `(ticker, as_of)`)

**Persistence verified.** Both replay batches landed in Cloud SQL. Not one-off / not in-memory.

---

## 1. TL;DR

A two-axis empirical validation:

| Axis | Headline finding |
|---|---|
| **LLM math accuracy** | The LLM's "stop < 1 ATR" rule has **44.4% precision and 22.2% recall** when compared against deterministically-computed `stop_distance_atr`. Mathematics performed by the LLM is unreliable. |
| **Flag predictive accuracy** | Despite the math errors, the flags carry **real predictive signal**. Days flagged with `stop_less_than_atr`, `stop_gt_1pct`, `above_sma200`, or `targets_close` had win rates **19–31pp lower** than days without. |

**Conclusion (reversing my earlier eyeballed recommendation):**

| Rule | Earlier (wrong) recommendation | Empirically-validated recommendation |
|---|---|---|
| "Stop < 1 ATR" | Remove (LLM hallucinates the math) | **Keep the concept, replace LLM math with `stop_distance_atr` column** |
| "Stop > 1% of price" | Remove (mis-calibrated for index ETFs) | **Keep — flag carries -24.9pp win-rate signal**; replace LLM math with `stop_distance_pct` column |
| "Entry far above SMA200 = contrarian" | Remove (inverts trend-following methodology) | **Keep — flag carries -21.8pp win-rate signal**; replace LLM math with `entry_vs_sma200_pct` column, threshold to be empirically tuned |
| "Targets too close" | Remove (subjective persona preference) | **Keep — flag carries -18.8pp signal**; replace with `target_r_multiples` column |
| "Catalyst within holding period" | Keep | **Remove or downgrade — Δwin=+1.3pp (no signal)** |
| "Stop too wide" | n/a | **Insufficient data (n=8); keep with empirical threshold tuning** |

The architectural principle stands: **calculations are computed deterministically and persisted to columns; the LLM reads facts, never computes them.** But the rules themselves — most of them — are empirically validated and should NOT be dropped.

---

## 2. Methodology

### 2.1 Persistence integrity check

Before any analysis, the 36-day window was re-replayed on the current post-fix image:

```
# Brief replays (writes premarket_analysis + premarket_analysis_history):
for d in <36 trading days>:
  gcloud run jobs execute premarket-brief --update-env-vars="BRIEF_AS_OF=$d" --async

# Insight replays (writes insight_reports):
for d in <36 trading days>:
  gcloud run jobs execute insight-pipeline \
    --update-env-vars="^|^INSIGHT_AS_OF=$d|INSIGHT_TICKERS=SPY,IWM,QQQ" \
    --args="--update" --async
```

Both completed: **36/36 brief replays OK**, **36/36 insight replays OK**.

`persist_to_cloud_sql` runs BEFORE the Discord post in the brief; insight pipeline uses `ON CONFLICT (ticker, as_of) DO UPDATE`. Both write paths are independent of Discord. Verified clean rows visible via SELECT.

### 2.2 Three datasets joined

1. **`persona_plans`** (`insight_reports.report->'persona_plans'`) — 141 rows (37 ticker-days × ~3 personas, some missing due to direction=flat)
2. **`market_metrics`** (`market_data_daily` joined on `date = as_of - 1 day`) — `atr_14`, `sma_200`. 87 of 141 persona plans had both metrics (weekend/holiday gaps in the join).
3. **`signal_alerts`** (live, 36-day window) — 1,965 alerts, 1,178 with exit data

### 2.3 Deterministic metric computations (the proposed column set)

For each persona plan, computed in Python (would be persisted to `PersonaPlan.risk_metrics` per the proposal):

```python
entry_mid = (entry_lo + entry_hi) / 2
risk_per_unit = abs(entry_mid - stop)
sign = +1 if plan_dir == 'long' else -1 if plan_dir == 'short' else 0

stop_distance_atr  = risk_per_unit / atr_14
stop_distance_pct  = risk_per_unit / entry_mid * 100
t_r_multiples      = [(t - entry_mid) / risk_per_unit * sign for t in targets]
entry_vs_sma200_pct = (entry_mid - sma_200) / sma_200 * 100
entry_vs_sma200_atr = (entry_mid - sma_200) / atr_14
```

### 2.4 Two-axis validation

**Axis A — LLM math accuracy** (precision/recall of LLM flag firing vs deterministically-computed condition).

**Axis B — Flag predictive accuracy** (win rate of subsequent aligned signal_alerts fires on days WITH the flag vs WITHOUT).

---

## 3. Axis A: LLM math accuracy

For the `stop_less_than_atr` flag (the highest-frequency one):

| Predicted (LLM) vs Actual (computed) | Count |
|---|---|
| TP: flag fired AND stop_distance_atr < 1.0 | 8 |
| FP: flag fired AND stop_distance_atr >= 1.0 (false positive) | 10 |
| FN: no flag AND stop_distance_atr < 1.0 (missed) | 28 |
| TN: no flag AND stop_distance_atr >= 1.0 | 41 |

- **Precision** (when LLM flags it, was it actually below threshold?): **44.4%**
- **Recall** (of actual <1 ATR cases, what % did LLM catch?): **22.2%**

Sample mismatches:
- `2026-03-19 IWM neutral`: computed_atr=1.03 (NOT below 1.0) → LLM still flagged it (false positive)
- `2026-03-24 IWM conservative`: computed_atr=0.70 (clearly below) → LLM missed it (false negative)
- `2026-03-24 SPY conservative`: computed_atr=0.49 → missed

**Conclusion**: LLM cannot reliably compute `(entry_mid − stop) / atr` from the persona plan. The math must move upstream.

---

## 4. Axis B: Flag predictive accuracy

Hypothesis: if a flag is a real warning, days WITH the flag should have LOWER win rate (of subsequent aligned signal_alerts) than days WITHOUT.

| Flag tag | n_with | win% with | n_without | win% without | Δwin% | Verdict |
|---|---|---|---|---|---|---|
| `stop_less_than_atr` | 178 | 40.4% | 172 | 71.5% | **−31.1pp** | **PREDICTIVE** |
| `stop_gt_1pct` | 193 | 44.6% | 157 | 69.4% | **−24.9pp** | **PREDICTIVE** |
| `above_sma200` | 82 | 39.0% | 268 | 60.8% | **−21.8pp** | **PREDICTIVE** |
| `targets_close` | 213 | 48.4% | 137 | 67.2% | **−18.8pp** | **PREDICTIVE** |
| `catalyst_window` | 138 | 56.5% | 212 | 55.2% | +1.3pp | no signal |
| `stop_too_wide` | 8 | 87.5% | 342 | 55.0% | +32.5pp | insufficient (n=8) |

### 4.1 Why "above_sma200" looks like both bad and good

Earlier eyeballing said "above SMA200 = contrarian is wrong for trend-following longs". The DATA says the flag IS predictive of bad outcomes (-21.8pp). What's the reconciliation?

When I bucketed `entry_vs_sma200_pct` directly (independent of the flag):

| Bucket | n | Win% | Avg return |
|---|---|---|---|
| 5–10% above SMA200 | 23 | **91.3%** | +0.104% |
| 10–15% above SMA200 | 117 | 54.7% | +0.014% |
| 15–20% above SMA200 | 199 | 52.3% | +0.021% |

The 5–10% bucket wins 91%. The LLM's flag isn't firing in that range — it's firing on the 15–20% range where win rate is mediocre. The LLM has implicitly captured a non-zero threshold; my earlier "this rule is wrong" claim was reading the rule's nominal text rather than what the LLM actually does with it. The flag's predictive value is real, just at a higher threshold than "any amount above SMA200."

**Conclusion**: keep the rule, but expose `entry_vs_sma200_pct` as a column and let the new threshold be **>10% (or wherever empirical inflection sits)**, not "far above" subjective.

### 4.2 Why this matters for the architecture

The empirical evidence says:
- LLM math: unreliable (44% precision)
- LLM aggregate judgment: useful (-20 to -31pp win-rate deltas)

This is the textbook case for the proposed architecture:
- **Compute the math deterministically** (so the unreliable axis becomes reliable)
- **Let the LLM read the precomputed fact + apply the rule**
- **Calibrate thresholds empirically** (so the rule fires at the right cutoff)

The combined system gets the benefit of the LLM's aggregate signaling without the cost of the math errors.

---

## 5. Aligned vs Opposite (the Phase 1 direction gate finding)

| Direction | n | Win% | Avg return |
|---|---|---|---|
| Aligned with plan direction | 350 | **55.7%** | **+0.023%** |
| Opposite to plan direction | 601 | **35.4%** | **−0.047%** |

Independently confirms the Phase 0 finding from `docs/replays/2026-05-10-corrected-baseline-v2.md`. The Phase 1 direction gate filtering opposing fires would improve win rate from 43% overall to ~56% on the surviving aligned set, with no per-rule conviction-weighting required.

---

## 6. Per-rule recommendation

| Rule | Architecture action | Threshold (empirical) | Note |
|---|---|---|---|
| `stop_less_than_atr` | Move math to `PersonaPlan.risk_metrics.stop_distance_atr` column. LLM reads, doesn't compute. | `< 1.0` (existing threshold; predictive at −31pp) | Highest-impact rule. |
| `stop_gt_1pct` | Move to `stop_distance_pct` column. | `> 1.0%` (empirical confirms; -24.9pp) | Earlier "miscalibrated for index ETFs" claim was WRONG. |
| `above_sma200` | Move to `entry_vs_sma200_pct` column. | `> 10%` (empirical: 5-10% wins 91%, >10% wins 53-55%) | Threshold tuned by data, not subjective "far". |
| `targets_close` | Move to `target_r_multiples` column. | First target R-multiple < ~1.5 (needs calibration) | -18.8pp signal supports keeping. |
| `catalyst_window` | Keep as-is (LLM judgment on calendar dates) | n/a | No predictive signal in this window. Re-evaluate over longer window. |
| `stop_too_wide` | Keep with caution | TBD | Sample n=8 too small to draw conclusions. |
| `ftfc_mismatch` | Already deterministic via `_calibrate_conviction` | n/a | No change. |
| `against_20_sma` | Investigate further | n/a | Zero occurrences in flagged data — check if pattern matcher misses real cases. |

---

## 7. Revised Phase 1α scope

**Renamed**: `fix/risk-reviewer-deterministic-metrics` → `feat/persona-risk-metrics-column-+-empirical-thresholds`

**Scope:**

1. **Add `RiskMetrics` to `PersonaPlan` schema** (per the earlier proposal):
   ```python
   class RiskMetrics(BaseModel):
       stop_distance_atr: float
       stop_distance_pct: float
       target_r_multiples: list[float]
       entry_vs_sma200_pct: Optional[float]
       entry_vs_sma200_atr: Optional[float]
       ftfc_aligned: bool
       invalidation_distance_atr: Optional[float]
   ```

2. **Compute deterministically in `trade_planner.compute_persona_plans`** — alongside the existing entry/stop/targets math.

3. **Persist** in `insight_reports.report->persona_plans[].risk_metrics` JSONB sub-object.

4. **Rewrite reviewer prompts** as rule-tables that READ `risk_metrics.*`:
   ```
   You are the neutral risk reviewer. You receive a PersonaPlan with
   pre-computed `risk_metrics`. Apply these rules verbatim:

     If risk_metrics.stop_distance_atr < 1.0:
         flag: 'stop_too_tight', severity: 'warn',
         message: f"Stop only {stop_distance_atr:.2f}× ATR from entry midpoint"

     If risk_metrics.stop_distance_pct > 1.0:
         flag: 'stop_too_wide_pct', severity: 'warn',
         message: f"Stop {stop_distance_pct:.2f}% from entry"

     If risk_metrics.entry_vs_sma200_pct > 10.0:
         flag: 'overextended_from_sma200', severity: 'warn',
         message: f"Entry {entry_vs_sma200_pct:.1f}% above 200 SMA"

     ... (rest of rules with explicit thresholds)

   Do NOT recompute any number. Use the values as given. Emit
   `flags` only.
   ```

5. **Remove `catalyst_window` from the warn-firing set** (Δwin=+1.3pp, no predictive value in this window).

6. **Tests**:
   - Math correctness: `compute_risk_metrics(plan)` produces expected values
   - Rule firing: when `stop_distance_atr=0.72`, "stop_too_tight" is in the LLM's expected output (LLM only has to do conditional + format-string, not math)
   - Backfill: re-replay 36-day window post-fix; check that the same `stop_distance_atr` math no longer produces 44% precision; should be 100% (deterministic)

7. **Phase 1α-v2 (optional follow-up)**: replace LLM reviewer calls with `lib/agents/risk_engine.py` Python rules. The LLM is doing conditional + format-string at that point — no actual judgment. Native code would be cheaper + more reliable.

---

## 8. Why the empirical evidence trumped the eyeballing

The earlier proposal (in the corrected-baseline-v2 doc and the conviction-audit issue comment) said:
- "Drop `stop > 1% of price` — too tight for index ETFs"
- "Drop `above SMA200 = contrarian` — inverts trend-following methodology"

Both based on:
- 1 week of 5/4–5/8 data
- Reading the rule's nominal text and judging its logical soundness
- Without the 36-day predictive analysis

The 36-day analysis showed both rules carry strong predictive signal (−24.9pp and −21.8pp respectively). The rules were CORRECT directionally; the issue was:
- LLM hallucinating the math (so flags fire on wrong cases — fixed by deterministic columns)
- Threshold rough (so flag fires both on real warnings AND on noise — fixed by empirical tuning)

**The architectural principle the user enforced — calculations to columns, LLM reads facts — was right.** The proposed RULE CHANGES (which rules to keep/remove) were wrong because they came from too small a sample.

---

## 9. Plan revision

**Phase 1** (direction gate): unchanged. Conviction-unaware. Aligned vs opposite is the only signal needed.

**Phase 1α** (this doc's subject): revised scope per §7. **Keep most rules; deterministic math; empirical thresholds.**

**Phase 1.5** (conviction-weighted gate): unblocked after Phase 1α lands, because:
- Flag firings will be ACCURATE post-fix
- Conviction calibration will receive proper warn/block counts
- Conviction will distribute across low/medium/high meaningfully (not pinned to low)

**Phase 2** (weak-tier experiments): unchanged.

**Phase 3** (post-open insight + gap_faded): unchanged.

---

## 10. Appendix: data files

- `/tmp/risk_audit/personas.csv` — 141 persona plans + risk_flags + market metrics
- `/tmp/risk_audit/signal_alerts.csv` — 1,965 signal_alerts in the 36-day window
- All raw SQL queries dispatched via `db-query.yml`; full audit trail in the workflow logs

(Files transient; not committed.)
