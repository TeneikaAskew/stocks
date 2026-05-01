# Signal Quality Test Plan

**Status:** Draft — phased rollout designed against the v3/v4 evaluation findings.
**Author:** session 2026-05-01
**Scope:** `gcp/signal_monitor.py`, `lib/trading_analysis.py`, `signal_alerts` schema, Discord push.
**Goal:** Get from "12% of fires are clean hits" to "30%+ clean fires" *without* dropping signal volume on trending days, by surfacing each signal's optimal timeframe and gating noise more intelligently.

---

## 1. The problem we're testing against

From the v4 multi-timeframe evaluation across 30,792 historical signal-eligible bars (Apr 1 – May 1, SPY/QQQ/IWM):

| Finding | Number | What it means |
|---|---|---|
| Bar-level CLEAN_HIT rate (60m, ≥0.5%) | 7.6% | Most bars where conditions fire don't lead to real moves |
| Live monitor's actual fire CLEAN rate | ~14.7% | Debounce ~2× better than random — preserving some signal |
| Estimated clean candidates **filtered out** by debounce | ~216/day | The "missed good ones" the user is concerned about |
| Signals where signal_strength=5 | 197 | Strength ordinal does NOT predict cleanness — strength 5 has 7.1% clean vs strength 3 at 7.6% |
| Day-to-day variance | 0.3% – 31% clean | Trending days catch real moves; chop days catch nothing — **but no day should be excluded** |
| Critical bug | 17-day signal_alerts gap | Live monitor wrote nothing 4/14–4/30 despite Cloud Run runs succeeding daily |

---

## 2. What we're going to change (4 phases)

### Phase 0 — fix the live monitor write bug *(blocking everything)*

**Problem:** Cloud Run job `signal-monitor` ran every weekday from 4/14–4/30 and exited 0 each time, but `signal_alerts` got 0 rows for those 17 days. Yesterday's deploy fixed it (today wrote 99). Need root cause confirmation.

**Test:**
1. `gcloud logging read 'resource.type="cloud_run_job" resource.labels.job_name="signal-monitor"' --filter "timestamp > 2026-04-29T00:00:00Z" --limit 200 --format="value(timestamp,textPayload)"` to find the silent error pattern.
2. Compare 4/13 (last working day) vs 4/14 (first silent day) deploys/commits.
3. Add a smoke-test in CI: after every deploy, run `signal-monitor` for 30 sec and assert ≥1 row written to `signal_alerts`.

**Success criterion:** Daily run produces ≥1 row in `signal_alerts` OR the failure-notifier fires. No silent exits.

**Owner / ETA:** Independent investigation — start now, doesn't block phases below.

---

### Phase 0.7 — strategy reconciliation *(blocks all measurement)*

**Problem discovered 2026-05-01:** the codebase has TWO completely different signal generators with **opposite CALL logic**:

| | `lib/signals.py:check_call_conditions()` | `lib/trading_analysis.py:799-836` |
|---|---|---|
| Used by | live `signal_monitor.py` → `signal_alerts` | nightly `historical-signals-watchlist` → `historical_signals` |
| CALL logic | **Mean-reversion** (consec_DOWN, below VWAP, below EMAs, RSI oversold) | **Momentum** (consec_UP, above VWAP, above EMA9, RSI bullish range) |
| `conditions_met` format | JSON array `["consecutive_down", "rsi_oversold_zone", ...]` | String `"3/5"` |

The §3 multi-timeframe findings were generated against `historical_signals` — i.e. the **momentum** strategy. They do NOT describe the live mean-reversion fires you see in Discord. The plan and §3 mappings are still useful but only for the momentum strategy; mean-reversion needs its own measurement.

**Decision: Option B — keep both as parallel strategies, measure each side-by-side.**

**What gets built:**

1. **Schema:** add a `strategy` column to `historical_signals`:
   ```sql
   ALTER TABLE historical_signals ADD COLUMN IF NOT EXISTS strategy
       VARCHAR(16) NOT NULL DEFAULT 'momentum'
       CHECK (strategy IN ('momentum', 'mean_reversion'));
   CREATE INDEX IF NOT EXISTS idx_historical_signals_strategy
       ON historical_signals (strategy, entry_time DESC);
   ```
   Existing rows backfill as `'momentum'` (current behavior).
2. **Refactor `scripts/run_historical_signals.py`** to accept `--strategy {momentum,mean_reversion}`:
   - `momentum` → uses existing `MarketAnalyzer` path (status quo)
   - `mean_reversion` → calls `lib.signals.evaluate_signal()` against the same indicator-enriched bars; writes rows with `strategy='mean_reversion'`.
3. **Backfill mean-reversion** for SPY/QQQ/IWM × 2026-04-01 → present, `--force` (rebuild from scratch).
4. **Update `signal_metrics`** (Phase 0.5's table) to carry `strategy` so the per-timeframe classifications track per strategy.
5. **Weekly QA report** (§4.1) shows side-by-side: momentum clean-rate vs mean-reversion clean-rate at every timeframe, per-(ticker, direction).
6. **Live `signal_monitor.py` stays mean-reversion.** No live behavior change.
7. **Discord embed update** (small): when a signal fires, show its strategy tag — e.g. "🟢 SPY CALL [mean_reversion / 90m]".

**Test:**

1. Apply schema migration via `apply-schema-migrations`.
2. Run `python scripts/run_historical_signals.py --symbol SPY --strategy mean_reversion --start-date 2026-04-01 --end-date 2026-05-02 --force` (and similarly for QQQ/IWM).
3. Confirm both strategies' rows coexist in `historical_signals` for the same dates with different signal-eligibility patterns.
4. Re-run the multi-tf analyzer (Phase 0.5's `signal_quality_report.py`) with `--strategy mean_reversion` filter. Compare to existing momentum results.
5. Update §3 in this plan with side-by-side tables.

**Success criterion:** both strategies have ≥ 4 weeks of rows in `historical_signals`, side-by-side multi-tf comparison published, and the §3.4 per-(ticker, direction) table now has TWO rows per class — one per strategy.

**ETA:** 2 days dev (schema + refactor + backfill) + 1 day analysis update.

---

### Phase 0.5 — productionize the analysis pipeline itself *(must precede Phases 1-4 measurement)*

**Problem:** the multi-timeframe analysis we just ran (`scripts/_signal_multi_tf.py`) is a throwaway. It reads creds from a temp directory, writes to a CSV, and only runs when someone types the command. Without productionizing it first, every later phase will be impossible to *measure* — we'd be tuning blind.

**What gets built:**

1. **Promote the script** — `scripts/_signal_multi_tf.py` → `scripts/signal_quality_report.py` with these productionization gates:
   - Reads creds from Secret Manager (drop the `.creds_tmp/` local-dev shim).
   - Drops the parquet read for 90/120/240m extension; queries `market_data_intraday` directly. *(Requires Phase 0's fetcher bug fix landed first.)*
   - Adds `--mode={historical, rolling}` so the script handles both completed-signal evaluation and in-progress signals (today's fires that don't have 60m of data yet → tagged `PENDING`).
   - Replaces stdout-only output with structured persistence (see #2).
2. **New Cloud SQL table** `signal_metrics`:
   ```sql
   CREATE TABLE signal_metrics (
       signal_id          UUID PRIMARY KEY,           -- FK to signal_alerts.id (or historical_signals composite)
       evaluated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       cls_5m   VARCHAR(10), cls_15m  VARCHAR(10),
       cls_30m  VARCHAR(10), cls_60m  VARCHAR(10),
       cls_90m  VARCHAR(10), cls_120m VARCHAR(10),
       cls_240m VARCHAR(10),
       best_tf            VARCHAR(8),                  -- 5m | 15m | ... | 240m | NULL if none clean
       return_5m          DOUBLE PRECISION, return_15m DOUBLE PRECISION,
       return_30m         DOUBLE PRECISION, return_60m DOUBLE PRECISION,
       return_90m         DOUBLE PRECISION, return_120m DOUBLE PRECISION,
       return_240m        DOUBLE PRECISION,
       atr_5m_pct         DOUBLE PRECISION,
       mfe_60m_atrs       DOUBLE PRECISION,            -- the unit-normalized metric from §4
       status             VARCHAR(12) NOT NULL DEFAULT 'final'
                          CHECK (status IN ('final','pending'))
   );
   CREATE INDEX idx_signal_metrics_evaluated_at ON signal_metrics (evaluated_at DESC);
   ```
3. **New Cloud Run Job** `signal-quality-report`:
   - Same image, command `python -m scripts.signal_quality_report`.
   - Runs hourly during market hours in `--mode=rolling` (incremental updates as 60m/90m/etc. windows close out).
   - Runs once nightly in `--mode=historical` to write/update the `final` rows.
   - Memory 1 GiB, timeout 10 min.
4. **Cloud Scheduler triggers**:
   - `signal-quality-report-hourly` — `0 14-20 * * 1-5` (every hour 10 AM – 4 PM ET).
   - `signal-quality-report-nightly` — `0 1 * * 2-6` (Tue–Sat 01:00 ET, after `historical-signals-watchlist`).
5. **Weekly QA report** (formerly §4.1) consumes from `signal_metrics` instead of recomputing — see §4.1 below.
6. **Regression alarm**: trailing-7-day vs prior-7-day clean-rate. If delta < -3pp, post to `#signal-qa` Discord channel and create a GitHub issue. Wired through the existing `failure-notifier` plumbing.
7. **Stale-data fail-loud**: if `market_data_intraday.max(ts)` is older than `now() - 1h` during market hours, the report posts a "🚨 stale intraday — analysis paused" alert instead of silently producing wrong numbers. *(This is what bit us today — Cloud SQL was 4 days behind and I only noticed because the user pushed back.)*

**Test:**

1. Deploy schema migration via `apply-schema-migrations`.
2. Run `signal-quality-report --mode=historical --start 2026-04-01 --end 2026-05-01` to backfill `signal_metrics` from existing `historical_signals`.
3. Verify the persisted classifications match what the throwaway script produced (`data/signal_eval_multi_tf.csv` is the reference).
4. Deploy hourly + nightly schedulers. Watch for one full day. Confirm the rolling-mode rows transition `pending → final` correctly.

**Success criterion:** every row in `signal_alerts` from this point forward has a corresponding `signal_metrics` row within 1 hour of fire (rolling) or by 1:30 AM next-day (final). Regression alarm fires correctly on a synthetic 5pp drop.

**ETA:** 3 days dev + 2 days validation. **Blocks all later phases' measurement.**

---

### Phase 1 — add timeframe tagging to every signal *(small but high-leverage)*

**Hypothesis:** Different signals work on different timeframes. A 5m scalp setup, a 15m breakout, and a 60m trend-continuation are not the same trade. Currently the system fires them all the same way.

**Schema change** (idempotent, additive):
```sql
ALTER TABLE signal_alerts ADD COLUMN IF NOT EXISTS timeframe_tag VARCHAR(8);
ALTER TABLE signal_alerts ADD COLUMN IF NOT EXISTS expected_hold_min INTEGER;
ALTER TABLE historical_signals ADD COLUMN IF NOT EXISTS timeframe_tag VARCHAR(8);
ALTER TABLE historical_signals ADD COLUMN IF NOT EXISTS expected_hold_min INTEGER;
```

`timeframe_tag` ∈ `{"5m", "15m", "30m", "60m", "90m", "120m", "240m"}`.
`expected_hold_min` is the planned holding period in minutes (default = upper bound of the timeframe bucket).

**Tagging logic** (the v4 multi-tf data tells us which conditions favor which timeframe — exact mapping populated below from analysis).

In `gcp/signal_monitor.py` at signal-fire time, after the conditions are evaluated, add:
```python
def assign_timeframe(conditions_met: list[str], rsi: float, rvol: float,
                     price_vs_vwap: float, atr_5m: float, atr_60m: float) -> tuple[str, int]:
    """Return (timeframe_tag, expected_hold_minutes)."""
    # MAPPING POPULATED FROM v4 MULTI-TF ANALYSIS (see §3 below)
    ...
```

**Discord push change:** the embed currently says "🟢 SPY CALL". Change to "🟢 SPY CALL **[15m]** — exit ~10:00 ET". Single-line addition.

**Test:**
1. Deploy the schema migration via `apply-schema-migrations` job.
2. Backfill `timeframe_tag` on existing `historical_signals` rows by re-running the v4 analysis logic.
3. Deploy the updated `signal_monitor.py`. Forward-test for 5 trading days. Compare clean-rate at the *signal's tagged timeframe* vs at 60m globally.

**Success criterion:** Clean-rate at the tagged timeframe ≥ 25% (vs 12% currently at 60m baseline).

**ETA:** 2 days dev + 5 days forward-test.

---

### Phase 2 — debounce tuning by outcome feedback

**Hypothesis:** Today's debounce is fixed-time (e.g. "no same-direction fire within X min"). Smarter debounce uses early outcome:
- If last fire's `return_5min` was profitable, *shorten* cooldown — momentum is real.
- If last fire's `mae_5min` exceeded `1× ATR_5m`, *lengthen* cooldown — that fire was wrong.

**Implementation:**
1. After each fire, schedule a 5-min follow-up that reads market_data_intraday and computes `return_5min` and `mae_5min` for the just-fired signal.
2. Persist to a new `signal_outcomes` table.
3. The next fire check reads the most recent outcome and adjusts cooldown.

**Test:** simulate against the historical_signals data (already exists for the full month). Compare:
- Static cooldown (current): N fires/day, clean rate X%
- Outcome-adaptive cooldown: M fires/day, clean rate Y%

If Y > X with M ≈ N, ship it.

**Success criterion:** ≥ 5pp improvement in clean rate without dropping >20% of fires.

**ETA:** 4 days simulation, then 5-day forward test.

---

### Phase 3 — multi-timeframe parallel signal generation

**Hypothesis:** Today's `signal_monitor.py` runs ONE evaluation per minute. It should run *parallel* evaluations at 5m / 15m / 30m / 60m bar resolutions, with timeframe-specific thresholds and conditions.

For example:
- A 5m breakout uses RSI from the 5m bar series, RVOL from the 5m series, etc.
- A 60m trend-continuation uses RSI/EMA from the 60m bar series (resampled).

Currently the system uses 1-min bars + indicators on the 1-min series for all "timeframes." That's why the score doesn't discriminate by timeframe — it's all one timeframe.

**Implementation:**
1. Add a resampling layer: per cycle, also compute indicators on 5m/15m/30m/60m resampled bars.
2. Run a separate condition-set per timeframe.
3. Each fire is now tagged by *which timeframe's evaluator triggered it*, not derived heuristically from the conditions.

**Test:** Run a 2-week parallel forward test with the multi-tf evaluator alongside the current single-tf.
- Compare fire counts per timeframe.
- Compare per-timeframe clean rates.
- Check that the multi-tf fires don't double-count the single-tf fires.

**Success criterion:** at least one timeframe (probably 15m or 30m) shows ≥35% clean rate.

**ETA:** 5 days dev + 14 days forward-test.

---

### Phase 4 — score weighting + condition reweighting

**Hypothesis:** The 5-condition voter currently gives 1.0 weight to every condition. Per Phase 1's data (populated below), some conditions correlate with the 30m+ timeframe and others with 5m scalps. Re-weighting by predicted timeframe contribution should widen the score distribution.

**Implementation:** Add per-condition weights to `lib/signals.py`. Initial weights (refined from v4 conditions analysis — see §3):

```python
# placeholder weights — will be tuned from data
WEIGHTS = {
    "rsi_oversold_zone": 1.0,        # Base
    "near_below_emas":   1.0,        # Base
    "stoch_rsi_oversold":1.0,        # Base
    "above_vwap":        1.5,        # Confirms uptrend
    "consecutive_up":    1.5,        # Momentum confirmation
    "level_break":       2.0,        # High-conviction structural
    # ...
}
```

**Test:** Re-classify all 30,792 historical signals using new weights. Confirm score distribution widens (current: 74% at 3.0; target: <30% at any single value).

**Success criterion:** The new score is ordinally predictive — `clean_pct` increases monotonically with score bucket.

**ETA:** 2 days dev + 5 days forward-test.

---

## 3. Data-driven mapping: signal → timeframe

### 3.1 Clean-rate by timeframe (all 30,792 candidates, every day, no exclusion)

| Timeframe | Threshold (% favorable) | n | CLEAN_HIT % | WRONG % | NOISE % |
|---|---|---|---|---|---|
| 5m | ≥0.15% | 30,792 | 4.4% | 0.3% | 90.6% |
| 15m | ≥0.30% | 30,792 | 4.2% | 0.1% | 91.5% |
| 30m | ≥0.40% | 30,792 | 5.3% | 0.1% | 88.4% |
| 60m | ≥0.50% | 30,792 | 7.6% | 0.1% | 83.5% |
| **90m** | **≥0.60%** | **28,277** | **12.2%** | 1.3% | 72.2% |
| 120m | ≥0.70% | 28,768 | 12.1% | 0.8% | 72.4% |
| **240m** | **≥1.00%** | **30,792** | **13.3%** | 0.0% | 70.2% |

**Key insight:** clean-rate **doubles** going from 60m → 90m. Most "noisy" signals at 60m are actually slower trend plays that need 90m+ to materialize. The system is exiting too early.

### 3.2 Where each signal performs best (per-signal optimal timeframe)

| Best timeframe | Count | % of all signals |
|---|---|---|
| **none_clean** | **23,191** | **75.3%** |
| 90m | 2,269 | 7.4% |
| 240m | 1,711 | 5.6% |
| 60m | 977 | 3.2% |
| 5m | 946 | 3.1% |
| 120m | 732 | 2.4% |
| 15m | 490 | 1.6% |
| 30m | 476 | 1.5% |

**24.7% of signals (7,601 of 30,792) have AT LEAST ONE clean timeframe.** That's the upper bound on theoretical clean-fire rate. Today's 12% clean rate is roughly half of optimal.

### 3.3 The four trade profiles (mean MFE % across all timeframes per best_tf cohort)

| Best TF | n | 5m | 15m | 30m | 60m | 90m | 120m | 240m | Profile |
|---|---|---|---|---|---|---|---|---|---|
| **5m** | 946 | **+0.41%** | +0.44% | +0.49% | +0.54% | +0.32% | +0.34% | +0.52% | **Quick scalp; exits fade** |
| 15m | 490 | +0.08 | **+0.82** | +0.85 | +0.89 | +0.28 | +0.29 | +0.53 | **15-30m breakout** |
| 30m | 476 | +0.06 | +0.18 | **+1.21** | +1.24 | +0.58 | +0.60 | +0.76 | **Spike + fade by 60m** |
| 60m | 977 | +0.05 | +0.15 | +0.31 | **+1.25** | +0.31 | +0.38 | +0.58 | **60m peak, MUST exit before 90m** |
| **90m** | **2,269** | +0.03 | +0.08 | +0.13 | +0.22 | **+2.62** | +2.63 | +2.66 | **Slow trend, hold to 90-240m** |
| 120m | 732 | +0.03 | +0.08 | +0.13 | +0.28 | +0.72 | **+2.52** | +2.61 | **120m hold** |
| 240m | 1,711 | +0.02 | +0.06 | +0.10 | +0.16 | +0.28 | +0.43 | **+3.32** | **All-session trend** |

**Read the rows carefully:**
- Best-at-5m signals **peak at 60m then fade back to 0.32%** — if you're holding past 60m you're giving back gains.
- Best-at-60m signals **collapse from +1.25% at 60m to +0.31% at 90m** — exit timing is critical here.
- Best-at-90m signals show **+0.22% at 60m but +2.62% at 90m** — 60m would have called this NOISE. Need to hold longer.

This is the strongest case for timeframe tagging: **the right exit window varies by 50× across signal types.**

### 3.4 Per ticker × direction breakdown — every timeframe

% of signals in each (ticker, direction) class whose **best** timeframe is X:

| Ticker | Direction | 5m % | 15m % | 30m % | 60m % | 90m % | 120m % | 240m % | none_clean % | Total clean-tf % |
|---|---|---|---|---|---|---|---|---|---|---|
| IWM | CALL | 5.4 | 2.4 | 2.2 | 4.9 | 2.9 | 1.7 | 3.2 | 77.3 | **22.7%** |
| IWM | PUT | 3.2 | 1.9 | 2.4 | 3.6 | **9.9** | 2.9 | 4.8 | 71.2 | 28.8% |
| QQQ | CALL | 2.9 | 1.6 | 1.3 | 3.5 | 7.6 | 2.4 | 5.1 | 75.6 | 24.4% |
| **QQQ** | **PUT** | 3.6 | 1.8 | 1.9 | 2.6 | **16.7** | 4.4 | **10.4** | 58.7 | **41.3%** ← best |
| SPY | CALL | 1.9 | 1.1 | 1.0 | 2.4 | 2.0 | 1.1 | 1.5 | **89.0** | 11.0% ← worst |
| SPY | PUT | 1.4 | 0.6 | 0.7 | 1.5 | 11.4 | 3.2 | **13.7** | 67.5 | 32.5% |

**Reading the rows:**

- **IWM CALL** has its biggest cohort at **5m (5.4%)** — these are *fast* signals; longer timeframes drop off. IWM call setups are scalps.
- **IWM PUT** flips to longer holds (90m=9.9%, 240m=4.8%). PUTs work better when held.
- **QQQ PUT** is the best-performing class — heavy at 90m (16.7%) and 240m (10.4%). These are slow trend trades.
- **SPY PUT** leans hardest into 240m (13.7%) — multi-hour holds.
- **SPY CALL** has nothing meaningful at any timeframe (max is 60m at 2.4%) — the regime-mismatch finding holds.

**Two distinct strategies emerge per ticker:**

| Class | Strategy | Recommended exit |
|---|---|---|
| IWM CALL | Quick scalp | **5m** |
| IWM PUT | Trend hold | **90m** |
| QQQ CALL | Mid-cycle | 90m / 240m (split) |
| QQQ PUT | Slow trend | **90m** |
| SPY PUT | Multi-hour | **240m** |
| SPY CALL | *don't fire* | n/a — needs regime gate |

This per-class table is what should drive the `assign_timeframe()` heuristic in Phase 1.

### 3.5 Daily breakdown (every day, no skipping)

Total clean-tf signals per day (signals with ≥1 clean timeframe):

| Date | Total candidates | Has clean tf | % with clean tf | Notes |
|---|---|---|---|---|
| 4/01 | 2,060 | 571 | 27.7% | OK |
| 4/02 | 2,110 | 637 | 30.2% | OK |
| 4/06 | 2,660 | 321 | 12.1% | Choppy |
| **4/07** | 2,629 | **1,354** | **51.5%** | **Trending** |
| 4/08 | 2,740 | 1,050 | 38.3% | Trending |
| 4/09 | 2,756 | 385 | 14.0% | Choppy |
| 4/10 | 2,635 | 449 | 17.0% | Choppy |
| 4/13 | 2,149 | 711 | 33.1% | Trending |
| 4/24 | 2,091 | 355 | 17.0% | Choppy |
| 4/27 | 2,572 | 189 | 7.3% | Dead chop |
| 4/28 | 2,173 | 636 | 29.3% | OK |
| 4/29 | 2,126 | 489 | 23.0% | OK |
| 4/30 | 2,090 | 453 | 21.7% | OK |

**Even on the worst day (4/27, 7.3% clean-tf), the system fired ~2,572 candidates.** That's the gap between bar-level conditions and timeframe-validated signals — and it's where most of the noise comes from.

---

## 4. Forward-testing infrastructure

To make every test repeatable and observable:

### 4.1 Weekly QA report (consumes Phase 0.5 metrics)

Saturday morning Cloud Run Job `signal-quality-weekly` reads from the
`signal_metrics` table populated by Phase 0.5's hourly+nightly pipeline.
It does NOT recompute classification — that work already happened during
the week. The job's only job is **summarization + comparison**:

- Total fires that week (signal_alerts) and bar-level candidates (historical_signals)
- Clean-rate at each timeframe — pulled directly from `signal_metrics.cls_*`
- Per-ticker × per-direction breakdown — pulled directly
- "Missed good ones" estimate: rows with `best_tf IS NOT NULL` that don't
  match a `signal_alerts.id` — i.e. clean candidates the live monitor didn't fire on
- Comparison to previous week — flag regressions, post to `#signal-qa`
- Per-class strategy compliance (e.g. "are QQQ PUT signals being held to 90m?")

This is a **lightweight aggregator** — most of the cost is already paid by
Phase 0.5's continuous evaluator.

### 4.2 A/B simulation harness

`scripts/simulate_signal_changes.py` — takes a config patch (e.g. "increase rvol-gate threshold to 1.2") and replays it against historical_signals. Outputs:
- Fire count delta
- Clean-rate delta
- Wrong-direction-rate delta
- Per-day delta

Run before any code change. Don't ship anything that regresses on simulation.

### 4.3 Data freshness gate

Phase 0 also includes: fix the `fetch-market-data.py:102-104` single-day filter so intraday data stays current. Without that, every signal-eval analysis is fighting stale data.

---

## 5. Sequencing + critical path

```mermaid
gantt
    title Signal Quality Improvement Plan
    dateFormat YYYY-MM-DD
    section Phase 0 (block)
    Fix signal-monitor write bug      :p0a, 2026-05-01, 2d
    Fix fetch-market-data day filter  :p0b, 2026-05-01, 2d
    section Phase 0.7 (strategy)
    Schema strategy column            :p07a, after p0a, 1d
    Refactor + backfill mean-reversion:p07b, after p07a, 2d
    section Phase 0.5 (measure)
    Promote analysis script           :p05a, after p07b, 2d
    signal_metrics table + Cloud Run job :p05b, after p05a, 1d
    Backfill + validate               :p05c, after p05b, 2d
    section Phase 1 (timeframe tag)
    Schema + tagging logic            :p1a, after p05c, 2d
    Forward-test (5 days)             :p1b, after p1a, 5d
    section Phase 2 (debounce)
    Outcome tracking + adaptive cooldown :p2a, after p1a, 4d
    Forward-test                      :p2b, after p2a, 5d
    section Phase 3 (multi-tf)
    Parallel TF evaluation            :p3a, after p2a, 5d
    Forward-test                      :p3b, after p3a, 14d
    section Phase 4 (weights)
    Reweight conditions               :p4a, after p3a, 2d
    Forward-test                      :p4b, after p4a, 5d
    section Continuous
    Weekly QA report                  :qa, after p05c, 30d
```

**Critical path:** Phase 0 → Phase 0.7 → Phase 0.5 → Phase 1 → Phase 3. Phases 2 and 4 can run in parallel after Phase 1 ships.

**Why Phase 0.5 is non-negotiable before Phase 1+:** without persisted, automated, per-signal classification you can't measure whether any later phase's change actually moved the clean-rate. You'd be tuning blind. The throwaway script we used today only worked because someone (me) hand-pulled fresh AV data, hand-set creds, and hand-read the output.

**Total timeline to "all phases shipped + validated":** ~32 trading days (added 2 for Phase 0.5).

---

## 6. Out of scope (intentionally)

- Strategy changes (the conditions themselves) — that's a separate research track.
- New tickers — work on the 3 we have first.
- Adding ML models — only after the rule-based system has been measured properly.
- "Skip dead days" filtering — we evaluate every day equally. Variance in outcome by regime is information, not a problem to mask.

---

## 7. How we'll know it worked

**End-state target metrics (after all 4 phases, 30 trading days of forward data):**

| Metric | Today (v4 baseline) | Target | Measured how |
|---|---|---|---|
| Clean-rate per fire | 12% | **≥30%** | weekly QA report |
| Wrong-direction rate | 14% | **≤8%** | weekly QA report |
| Score discrimination | 74% at one value | **≤30% at any value** | distribution check |
| Fires per day (avg) | ~30 | 25-50 (timeframe-tagged) | volume report |
| Missed-good-ones gap | ~216/day (estimated) | **≤50/day** | bar-level vs fire comparison |
| Live data freshness | 4-day lag (was) | <1h | freshness gate |

**Roll-back trigger:** any phase regresses the clean-rate by ≥3pp in forward-test → revert + investigate.

---

## Appendix A — files modified per phase

| Phase | Files |
|---|---|
| 0 | `gcp/signal_monitor.py` (bug fix), `gcp/fetchers/fetch_market_data.py:102-104` |
| 0.7 | `gcp/schema.sql` (strategy column on historical_signals), `scripts/run_historical_signals.py` (--strategy flag, calls `lib.signals.evaluate_signal` for mean_reversion), `gcp/insight_discord_push.py` (strategy tag in embed) |
| 0.5 | `scripts/signal_quality_report.py` (NEW, promoted from `_signal_multi_tf.py`), `gcp/schema.sql` (signal_metrics table + strategy column), `gcp/deploy.sh` (new job + scheduler entries), `gcp/signal_quality_alarm.py` (NEW, regression check + stale-data fail-loud) |
| 1 | `gcp/schema.sql` (timeframe_tag column), `gcp/signal_monitor.py`, `lib/signals.py` (timeframe heuristic from §3.4), `gcp/insight_discord_push.py` (embed format) |
| 2 | `gcp/signal_monitor.py`, `gcp/schema.sql` (signal_outcomes table), `scripts/simulate_signal_changes.py` (NEW) |
| 3 | `gcp/signal_monitor.py` (multi-tf evaluator), `lib/trading_analysis.py` (resampling) |
| 4 | `lib/signals.py` (weights), `lib/trading_analysis.py` (score calc) |

## Appendix B — scripts that already exist

- `scripts/_signal_evaluation.py` (v1, kept for legacy)
- `scripts/_signal_eval_v2.py` (Apr 1–May 1 with fresh AV intraday)
- `scripts/_signal_eval_v3.py` (per-ticker + SPY-CALL bug + today's session)
- `scripts/_signal_eval_v4.py` (historical_signals-based, full month)
- `scripts/_signal_multi_tf.py` (multi-timeframe, GET-ALL-DATA — populates the table in §3)

These are local/throwaway under `scripts/_*` per project convention. The promote-to-real path is to refactor `_signal_multi_tf.py` into `scripts/signal_quality_report.py` for the weekly QA job.
