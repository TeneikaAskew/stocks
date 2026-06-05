# Model Rethink — Build Plans (endorsed 2026-06-04)

Three models, derived from research reframings #2, #3, #6, #7. Plus the single
insight that ties them together and dissolves the wall the magnitude project hit.

---

## ★ The unifying insight: stop trying to beat IV — trade the underlying

Every gate-7 failure (body, call, put) says the same thing: **you cannot beat the
option's implied move on a bet the option market has already priced.** That is the
Variance Risk Premium — implied ≥ realized on average; buying vol is a structural
loser. It dooms *options-buying* on these signals. It does **not** doom directional
trading.

All three models below **trade the underlying** (shares / futures / a directional
spread), where **there is no IV to beat.** The ~0.8 ATR Strat directional move that
"failed" the options test is a perfectly good *underlying* edge. So the success
metric changes:

| Old (wrong for these) | New (correct) |
|---|---|
| realized move ÷ implied move ≥ 1.25 (gate-7) | out-of-sample **trade expectancy** (ATR units, net of slippage), **profit factor**, **hit-rate**, **Sharpe** |

Keep gate-7 **only** if/when the vehicle is a long option. For B1–B3 it does not apply.

---

## Model 1 · `STRAT-BREAKOUT-META`  ⭐ flagship (reframings #2 + #7)

**Reframe:** The Strat is a *stop-entry breakout* system. Direction is **deterministic**
given a trigger break (2U through `trigger_high` → long; 2D through `trigger_low` →
short). Don't predict direction — predict whether to **take** the trade. This is
López de Prado meta-labeling; the 24/24 direction failure does not apply because the
side is given by the rule.

**Two stages**
1. **Primary (rule, no ML):** event = next bar trades through the prior bar's
   trigger; side fixed by the combo bias. Use the existing combo logic in
   `lib/strat.py` (212/312/RevStrat/Failed-2 → bull/bear) + `trigger_high/low`,
   `is_continuation`, `is_reversal` (already persisted).
2. **Meta-label (the ML model):** **triple-barrier** label from the entry price —
   upper barrier = profit target (k_PT·ATR), lower = stop (k_SL·ATR), vertical =
   N bars. Label 1 = PT hit first; 0 = SL first or adverse time-out. Train a binary
   classifier P(follow-through | entry features). It predicts **trade quality**, a
   well-posed problem, not direction.

**Features (at the entry bar):** spine ~140 + the structural context that should
matter for follow-through — which combo fired, **FTFC score** (higher-TF alignment),
**signed distance to gamma flip / King/Gate walls** (does dealer positioning aid or
oppose the break), **RVOL** (volume confirmation), time-of-day, ATR regime. Add
order-flow proxy (close-location-value) when available.

**Data:** `strat_features_<tf>` (triggers + entry features) + **`market_data_intraday`
1-min bars** (to resolve which barrier hit first). No new external data.

**Experiment:** event-based sampling (only bars where primary fired → fewer, cleaner
rows). 8-fold anchored walk-forward (2019→2026), SPY/IWM/QQQ, 5m/15m/30m. Small grid
over (k_PT, k_SL, N). **Metric:** OOS precision (of taken trades, fraction hitting
PT), profit factor, expectancy in ATR. **The López de Prado test:** does the
meta-filter beat *taking every primary breakout*?

**Build:**
1. `gcp/research/strat_engine/breakout_meta_dataset.py` — primary event detection +
   triple-barrier labeling vs `market_data_intraday`.
2. `breakout_meta_walk_forward.py` — clone the `strat_dir_walk_forward.py` harness
   (cutoffs, binary LightGBM, fold loop).
3. `breakout_meta_report.py` — precision / profit-factor / expectancy (NOT
   implied-vs-realized).

---

## Model 2 · `DIR-REGIME` (reframing #3)

**Reframe:** Unconditional direction is a coin flip (proven). But the **same bar means
opposite things in opposite gamma regimes** — positive gamma → dealers fade →
mean-reversion; negative gamma (below flip) → dealers chase → momentum. A single
pooled model averages "fade" and "follow" to ≈0. **Split by regime.**

**Architecture:** partition bars by `gamma_regime` / sign of (spot − `flip_price`)
(both persisted). Train **two** direction models (or one with an explicit
price-location × gamma-sign interaction). Hypothesis: in negative-gamma, recent-return
momentum → continuation; in positive-gamma → reversal. Each conditional model may beat
base-rate log-loss even though the pooled one didn't.

**Features:** recent multi-bar returns (momentum), **signed distance to flip/walls**,
RVOL, spine; the **interaction** is the hypothesis, so include signed-distance-to-flip
explicitly.

**Data:** `strat_features_<tf>` + gamma columns (`total_gex`, `flip_price`,
`gamma_regime`, `dealer_regime`). **Prereq: verify gamma coverage across 2019-2026**
(one `db_query_cr` probe) — if GEX is sparse pre-2021, scope to the covered span.

**Experiment:** 8-fold walk-forward; run the existing direction gate (log-loss beat in
≥6/8) **separately within each regime subset.** Pooled was 24/24 FAIL — the test is
whether a regime subset passes. **Honest control:** must beat *naively following the
regime* (always-momentum in neg-gamma), not just base rate — else the model is just
relabeling "trend day."

**Build:** `dir_regime_walk_forward.py` — clone `strat_dir_walk_forward.py`, add
`--regime-split`, report per-regime gates + per-regime underlying expectancy.

---

## Model 3 · `INTRADAY-MOM` (reframing #6) — fast probe

**Reframe:** Direction isn't a property of *every* bar — it concentrates in time
windows. Gao-Han-Li-Zhou: the **first-30-min return predicts the last-30-min return**
on SPY/ETFs (R² ≈ 1.6–2.6%), **stronger on high-vol / high-volume / news days** —
exactly your EXPLOSIVE regime. Reframe from per-bar to **per-day**.

**Architecture:** per-day model. Feature = first half-hour return (9:30–10:00) [+ the
12th half-hour]. Target = last half-hour return (15:30–16:00), sign and/or size.
**Step 1 = pure replication** of the published linear regression on your data; if you
can't reproduce ~1.6% R² + significance, stop (timezone/data bug). **Step 2** = ML with
conditioning features.

**Features:** first-30-min return, 12th-half-hour return, day-level vol (overnight gap,
morning RVOL), is-news/is-FOMC (calendar you already built), VIX level. The
conditioning is the alpha.

**Data:** `market_data_intraday` + calendar/event features. No new data. Day-level →
tiny dataset (~1,800 rows over 7y) → fast, but keep the model simple (literature is
linear) to avoid overfit.

**Experiment:** replicate (R², t-stat per ticker) → walk-forward ML → metric =
last-30-min directional accuracy + expectancy of the underlying trade (clean MOC-style
vehicle, no IV).

**Build:** `intraday_momentum.py` — per-day dataset, replication regression, then
walk-forward ML + report.

---

## Recommended sequencing

1. **`INTRADAY-MOM`** first — cleanest academic prior, smallest data, fastest
   validate-or-kill, clear underlying vehicle. A quick win or quick kill.
2. **`STRAT-BREAKOUT-META`** — highest leverage, reuses the most infra, the *correct*
   version of what STRAT-DIR was trying to be.
3. **`DIR-REGIME`** — gated on the gamma-coverage check; subtler (must beat naive
   regime-following).

Deferred (you didn't prioritize): `FLOW-OFI` (needs order-flow data), `HONEST-GATE7`
(only matters if we revisit an options vehicle).

---

## RESULTS (2026-06-05)

All three built and run on SPY/IWM/QQQ, 8 anchored walk-forward folds (2019→2026).
First pass produced 0/3; a self-audit found two of the three tests were
structurally incapable of detecting their signal, so all three were corrected
and re-run.

### Corrected scorecard

| model | first pass | corrected | verdict |
|---|---|---|---|
| INTRADAY-MOM | FAIL | FAIL | **true null** |
| DIR-REGIME | FAIL | FAIL | **true null** |
| STRAT-BREAKOUT-META | FAIL | **PASS 24/24** | **false failure → real signal (gross)** |

### INTRADAY-MOM — true null
Pooled OLS β negative (SPY −0.049 t=−2.39, IWM −0.019, QQQ −0.014). The
corrected test added the CONDITIONAL subsets (high-VIX, big-open) the paper says
the effect lives in — β stays **negative & insignificant** there too. The
1993–2013 intraday-momentum anomaly is gone (mild mean-reversion now) in
2016–2026. Genuinely dead; not a scaffolding artifact.

### DIR-REGIME — true null
Corrected target (sign of N-bar **forward return** = move continuation, replacing
the unlearnable next_close>next_open) + verdict on **expectancy** vs a
naive-regime-follow control (replacing log-loss). Still FAIL: positive expectancy
in only 3–4/8 folds, rarely beats the naive control, log-loss beat 0/8. Gamma
coverage 22–63% (IWM low). Regime-split direction is not tradeable at 15m.

### STRAT-BREAKOUT-META — false failure, now the strongest signal (GROSS)
The first-pass FAIL was **my labeling artifact**: same-tf conservative-stop
labeling mislabels any bar spanning both barriers as a stop, deflating base
follow-through to 0.28 and corrupting labels. **Corrected to 1-min barrier
labeling** (true intra-bar PT/SL order), run on 5m for more events:

- base follow-through **0.28 → 0.33** (the artifact, quantified).
- taking every breakout ≈ breakeven-to-negative (base exp −0.05 to −0.09 R).
- meta-model at **take≥0.55** lifts precision to **0.40–0.57** and expectancy to
  **+0.1 to +0.36 R** in **24 of 24** ticker-folds (8/8 × SPY/IWM/QQQ),
  every year 2019→2026.
- No leakage: features = bar-t close + breakout side (both known when the
  breakout fires); 1-min bars are only the label.

Meta-labeling thesis (reframings #2/#7) **validated**: don't predict direction
(the Strat rule gives it), predict follow-through — that IS learnable. It is
also the only candidate that sidesteps the variance-risk-premium wall, because
it trades the underlying breakout, not an option.

**Open gate — NET tradability.** The 24/24 is GROSS (no slippage/spread/
commission; mildly optimistic fills). The +0.1 R folds would likely go negative
after costs; the +0.2–0.36 R folds have room. Next step: a friction model on
BREAKOUT-META + a PT/SL sweep. Until then it is a validated *gross* edge, not a
shippable strategy.

### Meta-lesson
Of three "failures," one was structural (mine), not the market — and it was the
flagship. A first-pass null is a hypothesis about the *test* as much as the
signal; corrected tests are mandatory before "fail" is earned.
