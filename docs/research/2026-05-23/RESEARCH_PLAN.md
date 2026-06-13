# Trading-Hypothesis Research Plan (2026-05-23)

**Sponsor:** msztee89@gmail.com — ~$140-150 of Claude credits to deploy
**Owner branch:** new `research/hypothesis-audit-2026-05-23` (forked
from `claude/signal-monitor-gamma-walls-UAe6g`)
**Question being answered:** Are the signals we ship to Discord
(strat candles, FTFC stack, gamma king/gate/flip) actually predictive,
across the full range of horizons we care about, and which features
add NEW information vs. just correlating with stuff we already use?

## Honest scoping caveats (read these first)

| dimension | what's available | what's NOT |
|---|---|---|
| Bar resolutions | 1-min RTH bars → can aggregate to 5m / 15m / 30m / 1h | 4h / 12h aren't meaningful — equity RTH is 6.5h. Plan substitutes "intraday → next-day → 5d → 20d" |
| Intraday options-greeks history | ~weeks (REALTIME fetcher = Track 0, shipped recently) | Multi-month intraday gamma snapshots don't exist. Workaround: use EOD-greeks-with-intraday-price as a proxy for the deeper history |
| Daily price history | Multi-year for SPY/IWM/QQQ + universe | n/a |
| Strat candle history | Computable on the fly from daily bars | n/a |
| Universe | SPY/IWM/QQQ confirmed; broader universe quality varies | The earnings-universe (1,361 names) has thinner intraday coverage; deep-history work limited to liquid ETFs |

The plan is honest about each of these inside the affected phase.

## Multiple-testing risk — pre-registered

This is the single biggest research risk. With 6 horizons × ~10
subgroup dimensions × ~20 features × multiple tickers, p-hacking is
trivial. To mitigate:

1. **Primary tests are pre-registered** in this doc before any
   analysis runs. Anything we add after-the-fact is labelled
   "exploratory" in the report and gets a lower confidence rating.
2. **Benjamini-Hochberg FDR correction** at q=0.10 on the primary
   test family within each phase.
3. **Phase 5 walk-forward** is non-negotiable — an edge that doesn't
   survive out-of-sample on a rolling window goes in the "not yet
   actionable" bucket regardless of in-sample significance.

## Pre-registered primary hypotheses

These are the questions we are PRE-COMMITTING to test (i.e. report
the result regardless of which direction it points):

| # | Hypothesis | Test |
|---|---|---|
| H1 | King-magnet effect (price drifts TOWARD king strike at 65-77% within 15m) holds for **all 3 ETFs** over **all available history**, not just SPY 14d | Per-ticker hit-rate at 15m + bootstrap 95% CI; compare against unconditional fwd-15m direction baseline |
| H2 | Flip-cross PUT aligned with DOWN-prev-day (76.7% in 30d) is significantly above baseline | Same as H1, target = flip × FTFC subgroup |
| H3 | Gate-break alerts add edge over baseline AFTER FTFC filter | Same; if hit rate ≤ baseline + 1σ, gate alerts are dropped |
| H4 | Gamma features add information beyond technicals (RSI, VWAP, RVOL, ATR, agreement, strat-class) | XGBoost feature-importance: `dist_to_king`, `in_gate_band`, `at_flip`, `gamma_regime`, `GEX_pct` rank in top-10 of SHAP-importance for ≥ 1 horizon |
| H5 | 4-TF FTFC stack adds edge over 1-TF (prev-day) FTFC | Compare hit rates of strat-combo events with 4-TF aligned vs. 1-TF aligned; the marginal lift must survive walk-forward |
| H6 | Strat-combo events (Failed_2U, Failed_2D, RevStrat) have positive expectancy at 1-5d horizons | Hit rate + signed-return distribution per combo per horizon; control = random daily bars matched by ticker/regime |
| H7 | Time-of-day matters: first / last 30 min of RTH have different signal-quality than midday | Time-bucketed conditional hit rate |
| H8 | VIX regime matters: signals work in low-vol but break down in high-vol (or vice versa) | VIX tercile-conditioned hit rate |

Any other finding from the research is "exploratory" and clearly
labelled as such.

---

## Phase 1 — Data inventory + return baselines (~5% of budget)

### Inputs
- `market_data_intraday` (1-min bars)
- `market_data_daily`
- `etf_options_snapshots`
- `signal_alerts` (historical fires + outcomes)
- VIX series (likely in `market_data_daily` under ticker `^VIX` or in
  the FRED tables — to confirm in Phase 1 itself)

### What we compute
1. **Coverage matrix**: for each table × ticker, `min(ts)`, `max(ts)`,
   row count, gap-count. So Phase 2-5 has a known data envelope.
2. **Unconditional fwd-return baselines**: sample N=50,000 random
   RTH 1-min bars per ETF, compute fwd 5m / 15m / 30m / 60m / EOD /
   1d / 5d returns. Report mean, std, P25/P50/P75, and "prob > 0"
   per horizon. This is the **noise floor** every later hit-rate
   compares against — without it, "65% hit rate" is meaningless.
3. **Conditional-on-VIX baselines**: same but split by VIX tercile.
   Tells us whether high-vol periods have systematically different
   directional bias that could fake an edge.
4. **Calendar / seasonality**: monthly + day-of-week fwd-return
   means (sanity check for Phase 7 / time-of-day analysis).

### Deliverables
- `docs/research/2026-05-23/P1_data_inventory.md` — narrative + tables
- `docs/research/2026-05-23/data/baselines.csv` — raw baseline numbers
- `scripts/research/P1_data_inventory.py` — reproducible script

### How it runs
- Multi-statement SQL via `db-query.yml` (coverage matrix).
- Python script `scripts/research/P1_data_inventory.py` for the
  random-sample baselines — runs as a Cloud Run Job to access the
  DB (sandbox can't), OR runs inside a `db-query.yml` dispatch that
  exports a CSV. Cloud Run Job is cleaner; budget ~$0.10/run.
- Delegated to `general-purpose` agent in a new subagent context so
  the main thread doesn't drown in raw SQL output.

### Success criteria
- Every later phase can quote "X events vs. Y unconditional baseline"
  with a real baseline number, not vibes.

---

## Phase 2 — Gamma × FTFC × horizon outcome grid (~20% of budget)

### Inputs
- Phase 1 baselines
- `etf_options_snapshots` for King/Gate/Flip strikes per (ticker, date)
- `market_data_intraday` for 1-min bars + fwd-return computation
- `market_data_daily` for prev-day-direction FTFC proxy and VIX

### What we compute

For each (ticker × alert_kind × alert_direction × FTFC × horizon ×
gamma_regime × VIX_tercile × time_of_day_bucket × day_of_week):

| metric | formula |
|---|---|
| N | event count |
| hit_rate | % with fwd return in alert direction |
| mean_signed_return_bps | mean of (return × direction sign) |
| sharpe_per_signal | `(mean / std) * sqrt(N)` for the per-signal sample |
| baseline_diff | hit_rate − Phase-1 unconditional baseline |
| bs_ci_lower / bs_ci_upper | 95% CI from 1000 bootstrap resamples |
| ks_pvalue | Kolmogorov-Smirnov test vs. unconditional return distribution |

Horizons: 5m, 15m, 30m, 60m, EOD, next-day open-to-open, 5-day close-to-close.

### Why this grid

- Confirms or breaks H1, H2, H3 across the full subgroup space —
  not just the SPY-only / 14d window the FTFC filter shipped on.
- Surfaces unknown subgroup interactions (e.g. "gate breaks work
  ONLY in negative-gamma regime, not in positive").
- Time-of-day + DOW: H7 sanity check.

### Deliverables
- `docs/research/2026-05-23/P2_gamma_outcomes.md` — narrative,
  interpretation, recommended production changes
- `docs/research/2026-05-23/data/gamma_outcomes_grid.parquet` —
  full 8-dimensional result table
- `docs/research/2026-05-23/figures/p2_*.png` — per-ticker × per-
  alert-kind heatmaps (hit rate vs. baseline)
- `scripts/research/P2_gamma_outcomes.py`

### How it runs
- Heavy SQL — likely needs to be a Cloud Run Job or batched
  `db-query.yml` dispatches.
- Bootstrap CIs in Python via numpy.
- Delegated to `general-purpose` agent with explicit instructions
  to commit the data files + figures, not just summarize.

### Risks
- **Sample sizes get thin fast** when you condition on 7 dimensions
  simultaneously. Plan: collapse to 3D (alert_kind × FTFC × horizon)
  as primary; the 7D grid is exploratory + flagged as such.
- Phase 5 walk-forward gates any "winning" 7D cell.

---

## Phase 3 — Strat methodology edge audit (~20% of budget)

### Inputs
- `market_data_daily` for daily strat classification (1/2U/2D/3)
- Intraday bars for FTFC stack (60m / 30m / 15m candles)
- `lib/strat.py:StratClassifier` for the canonical taxonomy

### What we compute

1. **Per-combo edge table**: For each strat combo (Failed_2U,
   Failed_2D, RevStrat 2D→2U, RevStrat 2U→2D, 3-bar reversal,
   continuation), hit rate + signed return at 1d / 3d / 5d / 10d /
   20d, conditioned on FTFC alignment depth (none / 1-TF / 2-TF /
   3-TF / 4-TF).

2. **FTFC marginal-lift table**: For each combo, does each additional
   TF of FTFC actually add edge? E.g.,
   ```
   Failed_2U + no-FTFC:     52% hit (baseline)
   Failed_2U + 1-TF FTFC:   58% hit  (+6pp lift)
   Failed_2U + 2-TF FTFC:   61% hit  (+3pp marginal)
   Failed_2U + 3-TF FTFC:   62% hit  (+1pp marginal — not worth it?)
   ```
   This directly tests H5.

3. **Strat-vs-baseline comparison**: control group = random daily
   bars matched on ticker + month + VIX-tercile. Apples-to-apples
   "does the strat label add information beyond just being a US
   equity bar on that date."

4. **Universe coverage check**: same edges in SPY/IWM/QQQ vs. a
   broader 100-name liquid universe. Detects "this only works for
   one ticker by coincidence."

### Deliverables
- `docs/research/2026-05-23/P3_strat_audit.md`
- `data/strat_combo_edges.parquet`
- `figures/p3_*.png` — combo × FTFC heatmaps
- `scripts/research/P3_strat_audit.py`

### How it runs
- Python script with `lib.strat.StratClassifier` + daily bars
  pulled via `db-query.yml` to a CSV artifact, then crunched
  locally in a subagent.
- Multi-year daily history is small enough (~250 bars/yr × 100
  tickers × 3yr ≈ 75k rows) to crunch in-memory.

### What "uncomfortable" looks like

If the per-combo edges are within 2pp of the baseline (i.e. the
strat taxonomy is largely a relabeling of "directional bar" with
no new information), I will write that in the report. The point
of the audit is to know.

---

## Phase 4 — Feature importance + correlation (~25% of budget)

### Inputs
- All of P1-P3 outputs
- Computed per-bar feature matrix at multiple resolutions

### Feature set (~30 features)

| family | features |
|---|---|
| Technicals | RSI, VWAP_dist_pct, RVOL_5min, ATR_expansion_pct, agreement_score, consec_up, consec_down, BB_pct_b |
| Gamma | dist_to_king_pct, in_gate_band_bool, at_flip_pct, gamma_regime (one-hot), GEX_pct, n_kings_visible |
| Strat | candle_type (one-hot), strat_combo (one-hot), FTFC_4tf_bool, FTFC_depth (0-4) |
| Temporal | minutes_since_open, day_of_week, days_to_opex |
| Market | VIX_level, VIX_tercile, SPY_5d_return, term_structure (VIX3M/VIX) |

### Targets

- Binary: `direction(fwd_return) == 'UP'` at each horizon
- Continuous: `fwd_return_bps` at each horizon

### Methodology

1. **Train/test split**: time-based, not random. Last 20% of history
   = holdout. No leakage.
2. **Models**: XGBoost + LightGBM (cross-check). Train on
   classification for direction; regression for magnitude.
3. **SHAP values**: tree SHAP per feature, per horizon. Mean
   absolute SHAP → importance ranking.
4. **Partial dependence**: PDP on the top-10 features for each
   horizon — does the model agree the feature has the SIGN we
   expect? (e.g. dist_to_king < 0 should push prob_up higher per
   the magnet thesis)
5. **Correlation matrix**: full Spearman correlation across all
   features. Identifies multi-collinearity (do gamma features
   correlate so strongly with VWAP_dist that they add no info?).
6. **Drop-and-relearn**: drop the gamma feature family entirely;
   does model AUC drop? By how much? This is the cleanest answer
   to H4.

### Deliverables
- `docs/research/2026-05-23/P4_feature_importance.md`
- `data/shap_per_horizon.parquet`
- `data/feature_correlation.parquet`
- `figures/p4_shap_*.png`, `figures/p4_corr_heatmap.png`,
  `figures/p4_pdp_*.png`
- `scripts/research/P4_feature_importance.py`

### How it runs
- Python script using xgboost + shap + scikit-learn, runs locally
  in a subagent with full data loaded from a SQL→CSV dispatch.
- ~15-30 min of model training (per-horizon × 2-model cross-check).

### What success looks like
- Either: gamma features rank in top-10 SHAP for ≥1 horizon →
  H4 confirmed, gamma adds real info
- Or: gamma features rank below all technicals → H4 rejected,
  gamma is redundant with what we already use, and the production
  alerts have value only as a "trigger reason" not as new alpha

---

## Phase 5 — Walk-forward stability (~15% of budget)

### Inputs
- The top-N "winners" from P2 + P3 (top-N to be set per phase,
  pre-registered at ~5 each)

### What we compute

For each candidate edge:

1. **Rolling 20-day hit-rate** — does the edge persist or is it
   front-loaded?
2. **Stability score** = `std(rolling_hit_rate) / mean(rolling_hit_rate)`
   (coefficient of variation) — lower is more stable
3. **Walk-forward Sharpe** with 60-day train / 20-day test windows
4. **Time-decay regression**: regress per-month hit rate on month
   index; significant negative slope = decaying edge
5. **Benjamini-Hochberg FDR correction** across all pre-registered
   primary tests at q=0.10

### Deliverables
- `docs/research/2026-05-23/P5_stability.md`
- `data/stability_per_edge.parquet`
- `figures/p5_rolling_*.png` — per-edge rolling hit-rate plots
- `scripts/research/P5_stability.py`

### Decision rule

Edges are categorized:

| category | criteria | recommendation |
|---|---|---|
| GREEN | survives walk-forward + BH-FDR-corrected p < 0.10 + stability CV < 0.3 | Ship to production |
| YELLOW | walk-forward marginal OR stability CV 0.3-0.5 | A/B test in Discord, monitor 30d before promoting |
| RED | walk-forward fails OR stability CV > 0.5 | Document as "in-sample only", do NOT ship |

---

## Phase 6 — Synthesis + production recommendations (~10% of budget)

### Inputs
- Everything above

### Deliverables

- `docs/research/2026-05-23/RESEARCH_SUMMARY.md` — top-level
  narrative: H1-H8 verdicts, ranked list of recommended changes,
  open questions
- `docs/research/2026-05-23/PRODUCTION_CHANGELIST.md` — concrete
  code edits with file:line targets, e.g.:
  - "Drop gate PUT alerts unconditionally (P2: hit 44.9% even
    aligned; P5: not stable)"
  - "Add `at_flip × neg_gamma` interaction to signal scoring
    (P4: top-3 SHAP feature at 60m horizon, P5: stable)"
  - "FTFC 3-TF stack is the sweet spot; 4-TF adds <1pp lift,
    not worth the extra dependency on 15m bars" (P3 H5 verdict)
- A draft PR opening these changes against `main` for review

---

## Sequencing + parallelism

```
   Phase 1 ──┬─→ Phase 2 ─┐
             │             ├─→ Phase 5 ─→ Phase 6
             ├─→ Phase 3 ─┤
             │             │
             └─→ Phase 4 ─┘
```

Phases 2, 3, 4 are independent given Phase 1 outputs and run in
parallel subagents. Phase 5 collects winners from each. Phase 6
synthesizes.

Wall-clock: ~3-5 hours elapsed if phases run in parallel where
they can. Budget: $140-150 across all phases.

## What I'd need from you to start

- **GO / NO-GO on the whole plan** (or phase-by-phase if you want
  to budget incrementally — P1 + P2 first, then decide on P3-P6
  is a sensible incremental approach)
- **Universe choice**: confine to SPY/IWM/QQQ (cleanest, fastest)
  vs. include a broader 100-name liquid set (more general findings,
  ~3× cost). Default: SPY/IWM/QQQ for P1-P2, broader for P3-P4.
- **One-shot or in-progress reports**: do I send you final docs
  at the end, or post phase-by-phase progress comments as I go?

Tests + lint will run after every committed change (the existing
51 gamma_proximity tests stay green throughout; new research
scripts get their own pytest module).

All artifacts land under `docs/research/2026-05-23/` and
`scripts/research/` so they're greppable and reproducible. The
research branch will be PR'd to `main` for archival but the
deliverables don't directly touch production code — that's what
Phase 6's PRODUCTION_CHANGELIST is for, as a separate change set.
