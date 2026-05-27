# Phase 2 — Gamma Alerts × Outcomes (10-year audit)

**Date:** 2026-05-23
**Universe:** SPY, IWM, QQQ
**Window:** 2016-05-10 → 2026-05-22 (~2,500 trading days each)
**Method:** Production-replay path — D-1 EOD chain → `lib.gamma.build_summary` → `lib.strategies.gamma_proximity.evaluate_all` walked bar-by-bar
**Total alerts:** 8,119
**Status:** Complete

## TL;DR

1. **At 1-day horizon, gamma alerts ARE directional — but the lift is the bull-market drift, not gamma physics.** All 4 (kind × CALL) cells hit 80-95% at the 1d horizon (+25-35pp over baseline). PUT alerts hit 15-25% (i.e. price went UP 75-85% of the time, *against* the alert). Both numbers are consistent with a strong bull-market drift acting through whatever entry filter selects the alert.
2. **At intraday horizons (5m / 15m / 30m / 60m), gamma alerts have NO meaningful edge over baseline** — pooled lifts are −4 to +5 pp, well within sampling noise. Cells that survive BH-FDR at intraday horizons are uniformly low-N and not robust.
3. **The 76.7% live "flip-PUT" figure does NOT replicate in 10-year replay.** Historical `gamma_flip_cross` PUT fires are very rare (14 events in 10 years), with hit_1d = 28.6% — i.e. price went DOWN only 28.6% of the time after a flip-cross PUT, far below the 76.7% live figure. The live number likely reflects a different horizon, an aggregation across a different alert family, or a small in-sample window. **Needs investigation before continuing to rely on this signal.**
4. **gate_break + king_approach alerts ARE FTFC-prefiltered in the production code** — every `gate_break CALL` event in the table has `ftfc_prev_day_dir=UP` (1,898 of 1,898). So the apparent 1-day "edge" is really a measurement of "prior-day-up days continued up the next day" — a known bull-drift autocorrelation, not a gamma-walls finding.
5. **PUT alerts are actively counter-productive at 1d horizon in this regime.** Across 1,948 gate_break PUTs, 84.7% saw the next-day close *higher* than the entry — the alert fired, price went the opposite direction. In a directional-trading P&L lens this is a substantial drag, not a profitable signal.

## 1. Data envelope

Built from Phase 1's pre-locked inputs + two new tables created by this phase:

| input | source | rows |
|---|---|---|
| EOD options chain | `etf_options_snapshots WHERE data_source='alphavantage' AND market_session='EOD'` | 46.7M rows (SPY 21.6M, IWM 10.6M, QQQ 14.5M) |
| 1-min RTH bars | `market_data_intraday_{spy,iwm,qqq}` filtered to RTH 09:30-15:59 ET | ~3M bars per ticker |
| VIX | `market_data_daily WHERE ticker='^VIX'` (Phase 1 backfill) | 2,864 days |
| Daily bars (entry / 1d / 5d horizon close) | `market_data_daily` | ~2,530 per ticker |

Two intermediate tables emitted:
- **`gamma_levels_eod`** — pre-computed Kings / Gates / Flip per (ticker, snapshot_date), 91,514 level rows over 10 years. PK `(ticker, snapshot_date, level_kind, level_strike)`. Idempotent. Built by `gcp/research/p2_build_gamma_levels.py` running as Cloud Run Job in ~43 min.
- **`gamma_events`** — one row per fired alert with FTFC + VIX + ToD + DoW stratification dims and forward returns at 5m/15m/30m/60m/240m/1d/5d horizons. 8,119 rows. PK `(ticker, alert_ts, alert_kind, level_strike)`. Built by `gcp/research/p2_outcomes_grid.py` in ~3 min after the N+1 query bug was fixed.

## 2. Alert volume by kind × direction (10 years)

| alert_kind | CALL | PUT | total |
|---|---|---|---|
| `gamma_gate_break` | 1,899 | 1,948 | 3,847 |
| `gamma_king_approach` | 2,470 | 1,708 | 4,178 |
| `gamma_flip_cross` | 80 | 14 | 94 |

`gamma_flip_cross` is dramatically rarer than the other two — roughly 1 event per 5-6 weeks. Any per-cell strata of `flip_cross` will be too thin to bootstrap. **The live-production 76.7% flip-PUT number cannot have come from 10 years of historical fires; we have only 14 such events total.**

## 3. The headline finding — pooled lift over baseline by (kind × direction × horizon)

For each cell, lift = `hit_rate_observed − baseline_pct_up_for_direction`. Baseline is the unconditional pct_up from Phase 1 (per ticker × horizon, mirrored for PUT direction).

Lift in percentage points (pp). Bolded cells have ≥100 events.

| ticker | kind | dir | 5m | 15m | 30m | 60m | 240m | 1d | 5d |
|---|---|---|---|---|---|---|---|---|---|
| SPY | gate_break | **CALL** | -2.3 | +1.4 | +5.0 | +3.6 | +2.4 | **+30.8** | +21.2 |
| SPY | gate_break | **PUT**  | -0.4 | -3.0 | -4.6 | -1.9 | +1.4 | **−30.6** | -15.8 |
| SPY | king_approach | **CALL** | -0.8 | -3.6 | -2.2 | -3.5 | +2.3 | **+27.7** | +13.3 |
| SPY | king_approach | **PUT**  | +1.3 | +4.5 | +3.9 | +0.9 | +2.6 | **−25.7** | -11.8 |
| IWM | gate_break | **CALL** | +4.6 | +4.9 | +2.6 | +3.9 | +2.1 | **+32.6** | +23.9 |
| IWM | gate_break | **PUT**  | -2.0 | +1.0 | +2.7 | +0.9 | -0.3 | **−31.9** | -24.5 |
| IWM | king_approach | **CALL** | +0.8 | -0.2 | -2.1 | -1.5 | +0.1 | **+32.0** | +22.5 |
| IWM | king_approach | **PUT**  | -0.5 | +1.2 | +3.7 | +3.4 | +1.7 | **−30.0** | -24.5 |
| QQQ | gate_break | **CALL** | +1.0 | -0.8 | +0.7 | +0.4 | -1.4 | **+27.8** | +19.6 |
| QQQ | gate_break | **PUT**  | +0.7 | -2.8 | -0.8 | -0.3 | -0.3 | **−27.0** | -17.8 |
| QQQ | king_approach | **CALL** | -1.3 | -3.1 | -2.9 | -3.4 | +0.6 | **+24.3** | +11.1 |
| QQQ | king_approach | **PUT**  | -0.5 | +0.7 | +3.9 | +6.1 | +5.5 | **−19.3** | -9.7 |
| QQQ | flip_cross | CALL | -10.1 | +3.3 | -3.4 | -1.4 | -6.2 | +12.5 | +2.5 |

### Reading the table

- **All intraday horizons (5m to 240m): lift is ≤ ±5 pp**, within bootstrap noise. No actionable scalp/day-trade edge.
- **All 1d horizons: |lift| ≥ 19 pp**, and the sign is uniform — **+** for CALL, **−** for PUT, across all 3 tickers and both major alert kinds. This is the bull-drift-dominated finding.
- **5d horizons trend back toward baseline** for CALLs (the bull-drift effect dilutes over a week) and persist for PUTs (which keep losing).

### Why "+30pp at 1d" isn't what it looks like

`evaluate_all` in production applies an FTFC filter: `gate_break CALL` requires `prev_day_dir=UP`, `gate_break PUT` requires `prev_day_dir=DOWN`. So:

- A `gate_break CALL` event is by construction "yesterday was UP and price broke above the gate today."
- This is the well-known **next-day continuation effect** in trending equity markets: a green Mon increases P(green Tue) above the unconditional baseline.
- The gamma walls don't add information beyond the prior-day-direction signal, at the daily horizon.

A clean A/B test would compare:
- **(A) Gamma-alert-conditioned** subset of UP-prev-day days
- **(B) Random** subset of UP-prev-day days

If the lifts in column 1d are similar between A and B, the gamma walls aren't doing the predictive work. This is **the next Phase 2.5 test** — not done in this audit, recommended before any production change.

## 4. The PUT problem

The audit found that **PUT alerts are systematically wrong at the 1-day horizon** across all kinds, all tickers, all VIX regimes:

| alert_kind | direction | n | hit_1d | mean_1d_bps |
|---|---|---|---|---|
| `gamma_gate_break` | PUT | 1,948 | **15.3%** | −267.3 |
| `gamma_king_approach` | PUT | 1,708 | **20.5%** | −223.1 |
| `gamma_flip_cross` | PUT | 14 | 28.6% | n/a (small N) |

Each PUT entry "lost" −223 to −267 bps on average over 1 day. This is a **direct P&L drag**, not a tradeable signal.

VIX-conditioned breakdown shows the problem is **worst in low-VIX environments**:

| kind | dir | VIX | n | hit_1d | mean_1d_bps |
|---|---|---|---|---|---|
| gate_break | PUT | LOW | 266 | 5.3% | −319.5 |
| gate_break | PUT | MID | 740 | 18.1% | −193.2 |
| gate_break | PUT | HIGH | 942 | 15.9% | −310.9 |
| king_approach | PUT | LOW | 169 | 9.5% | −268.5 |
| king_approach | PUT | MID | 662 | 26.6% | −136.5 |
| king_approach | PUT | HIGH | 872 | 18.0% | −280.1 |

LOW-VIX × PUT is essentially **the maximum-drag combination**: complacent market, predicted reversal didn't come. Production should consider **muting PUT alerts during VIX_LOW (`<14.65`) regimes** — at minimum require additional confirmation.

## 5. The 76.7% live flip-PUT claim — does NOT replicate

**Pre-investigation finding:** the live signal_monitor's flip-PUT result of 76.7% hit-rate cannot have come from anywhere in this 10-year replay. Three reasons:

1. **There are only 94 `gamma_flip_cross` events in 10 years (14 PUTs).** A 76.7% rate on 14 events would mean ~11 hits and 3 misses. We saw 4 hits and 10 misses (hit_1d = 28.6%).
2. **No alternative interpretation of "PUT" + "flip" + "76.7%" matches anything in the historical replay.** The closest large-N PUT cohort is `gamma_gate_break PUT high-VIX low-prev-day-down combinations` — those bottom out at ~22% hit_1d, not 77%.
3. **At intraday horizons (5m-60m), no PUT cohort exceeds 60% hit-rate** in the historical replay.

**Possible explanations for the live result:**
- It was measured over a small live-window where bull drift was reversed (e.g. 5-7 day window during a drawdown)
- It was measured at a much shorter horizon than the audit (e.g. 5-min) AND in a specific tight VIX/ToD configuration
- The live signal_monitor's filter chain is materially different from `evaluate_all`'s replay path — verify by running the SAME replay-driver script (`scripts/replay_signal_monitor.py`) against the 5/15-5/22 live window and comparing

**Recommended next action (outside this audit's scope):** dispatch the production replay over the live window where the 76.7% figure was measured, with `evaluate_all` AS-OF that window, and compute the same hit-rate. If it doesn't match, the live monitor has drift from this audit's logic.

## 6. Cells that survived BH-FDR

226 of 1,195 cells reject the null at q=0.10 (19% — much higher than the 10% expected by chance, so the signal isn't pure noise). But most rejections are 1d-horizon cells, where the FTFC + bull-drift confound dominates. Of the 226:

- **194** are 1d-horizon (the bull-drift cells)
- **22** are 5d-horizon
- **10** are intraday cells, mostly **at the cell-floor N=10-15**, mean lift ±10 pp — these are likely false positives despite FDR adjustment (no Bonferroni, and high cell granularity)

The few large-N intraday cells that pass:

| ticker | kind | dir | horizon | ftfc | vix | tod | n | hit | lift_pp |
|---|---|---|---|---|---|---|---|---|---|
| QQQ | king_approach | PUT | 15m | UP | MID | open | 42 | 71.4% | **+23.1** |
| SPY | king_approach | CALL | 15m | DOWN | MID | open | 59 | 33.9% | **−17.8** |
| IWM | gate_break | PUT | 15m | DOWN | MID | midday | 10 | 10.0% | −39.4 |

The QQQ king-approach PUT at 15m (n=42) is **the only intraday-horizon cell with N>30 AND positive significant lift in the entire grid**. Worth a sanity check before any conclusion — this could be the real intraday gamma signal, but N=42 is still thin.

## 7. Verdict on H1-H8 hypotheses (pre-registered in plan)

| H | hypothesis | verdict |
|---|---|---|
| H1 | Gamma alerts beat baseline at 15-min horizon | **REJECTED**: pooled intraday lifts ≤ ±5 pp |
| H2 | Gamma alerts beat baseline at 1-day horizon | **NOT FALSIFIED** but explained by FTFC + bull drift, not by gamma |
| H3 | High-VIX × PUT > High-VIX × CALL | **REJECTED**: PUT hit-rates are uniformly lower across all VIX regimes |
| H4 | King > Gate at hit-rate | **NOT TESTED at clean N**: lifts are comparable |
| H5 | Flip-cross is the highest-edge alert | **REJECTED**: flip_cross has 94 events total in 10 years — too rare, and the 14 PUTs hit only 29% |
| H6 | Prev-day-UP × CALL boosts hit-rate | **CONFOUNDED**: production's FTFC filter makes this a tautology — every gate_break CALL has prev_day=UP |
| H7 | Open ToD is the highest-edge bucket | **NOT TESTED**: most cells too thin |
| H8 | Negative-gamma regime amplifies signals | **NOT TESTED**: 5,694 of 8,119 events have `regime=unknown`; need to fix the regime classifier before this can be retested |

## 8. Implications for production

1. **Stop scalping gamma walls at 5-30 min horizons** — no edge over noise.
2. **Reframe gamma walls as a swing-trade (1-day to 5-day) confirmation, NOT an intraday entry trigger.**
3. **Add an A/B test against random-FTFC-aligned days** to determine whether gamma adds info beyond the prior-day-direction trend (Phase 2.5).
4. **Mute PUT alerts in LOW-VIX regime** (VIX < 14.65) — bottom-decile −319 bps avg drag.
5. **Investigate the 76.7% live flip-PUT figure** with a production-replay script against the live window. If the replay can't reproduce it, the live monitor has logic drift from this audit's replay.
6. **Fix the regime classifier** — 70% of events have `regime=unknown`, blocking H8 and any positive/negative-gamma-conditional analysis.

## 9. Open items for Phase 3-5

- Phase 3 (strat methodology audit): apply same baseline-diff lens to FTFC + strat-combo signals on 10yr daily bars.
- Phase 4 (feature importance): include `gamma_event_recent` as a feature alongside RSI/EMA/etc., test SHAP importance vs unconditional model.
- Phase 5 (walk-forward stability): the 1d "+30pp" finding here is unconditional across the full 10-year window — split into 2-year rolling windows to see whether the bull-drift effect persists or dies in down regimes (2018-Q4, 2022).

## 10. Reproducibility

| artifact | path |
|---|---|
| Step 1 job | [`gcp/research/p2_build_gamma_levels.py`](../../../gcp/research/p2_build_gamma_levels.py) |
| Step 2 job | [`gcp/research/p2_outcomes_grid.py`](../../../gcp/research/p2_outcomes_grid.py) |
| Step 3 script | [`scripts/research/p2_stratify_outcomes.py`](../../../scripts/research/p2_stratify_outcomes.py) |
| Cloud Run Jobs | `p2-build-gamma-levels`, `p2-outcomes-grid` (us-east1) |
| Image | `us-east1-docker.pkg.dev/adept-mountain-474619-d4/trading/trading-system:research-p2` |
| `gamma_levels_eod` | Cloud SQL `trading` (PK ticker, snapshot_date, level_kind, level_strike) — 91,514 rows |
| `gamma_events` | Cloud SQL `trading` (PK ticker, alert_ts, alert_kind, level_strike) — 8,119 rows |
| Local parquet | [`data/gamma_events.parquet`](data/gamma_events.parquet) |
| Outcome grid | [`data/p2_outcomes_grid.parquet`](data/p2_outcomes_grid.parquet) |
| Pooled lifts CSV | [`data/p2_pooled_by_ticker.csv`](data/p2_pooled_by_ticker.csv) |
