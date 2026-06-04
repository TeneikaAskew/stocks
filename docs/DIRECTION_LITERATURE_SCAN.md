# Direction Research — Literature Scan (Phase 0)

**Date:** 2026-06-04 · **Branch:** `claude/strat-engine-directional-calibration-wHAis`

**Purpose.** Before spending GCP compute hunting for a directional edge, establish
what the academic + practitioner literature says is *possible*. This scan gates
the experiment matrix in the companion plan and frames the eventual ship/no-ship
verdict. It is the Phase-0 step of the staged directionality program and the
companion to [`DIRECTION_FEATURES_R&D.md`](DIRECTION_FEATURES_R&D.md) (which
already proved that adding *feature families* to the `next_close > next_open`
target fails 0/8).

**Method.** Five parallel web-research agents, one per angle, each fetching
primary/authoritative sources and emitting confidence-tagged falsifiable claims.
Findings below are ranked by **cross-agent corroboration** (a claim independently
surfaced by multiple agents from independent sources is treated as the strongest
verification signal available short of replication).

---

## TL;DR — what the literature says

1. **A ~50% single-bar directional hit rate on a liquid index ETF is the
   expected efficient-market result, not a bug.** The 0/72-fold failure of the
   `next_close > next_open` model is exactly what theory and empirics predict.
2. **Magnitude is predictable; sign is not — especially at the highest
   frequencies.** This split is both empirical (SPY: 45.0% directional accuracy
   *despite* a 2.89× absolute-return effect) and theoretical (sign predictability
   is a byproduct of volatility dynamics, weakest at minute scale).
3. **The one durable directional effect is intraday momentum** — a *conditional,
   time-of-day, regime-dependent* continuation effect, not generic next-bar
   prediction. It is the single most-corroborated finding in this scan.
4. **Dealer gamma / GEX is a volatility/mean-reversion signal, not a directional
   one.** "GEX is not a price predictor."
5. **Meta-labeling is a precision filter, not a direction generator.** It cannot
   manufacture alpha on a primary with no directional edge — one independent
   reproduction saw Sharpe *fall*.
6. **FTFC (full timeframe continuity) has zero rigorous validation** — all
   evidence is vendor/educational.

The honest read: the literature does **not** promise a recoverable single-bar
directional edge from one instrument's own price/volume technicals. It points to
exactly three narrow, conditional places an edge could plausibly live — **longer
horizon, volatility/time-of-day regime, and trigger-conditioning** — and warns
that even those are thin and easily eaten by transaction costs. This *supports
running the staged probes*, with a sober prior that the most likely outcome is a
PARTIAL/conditional or DEAD-END verdict rather than an unconditional ship.

---

## Findings ranked by corroboration

### A. Magnitude-predictable / sign-unpredictable [STRONGLY CORROBORATED — agents 1 & 3]
- SPY: conditioning on a hidden-order signal raised 5-min **absolute** returns
  2.89× (t=12.41, p<10⁻⁴) yet left **directional** accuracy at 45.0%,
  indistinguishable from a coin flip (p=0.12). The authors call it an explicit
  "paradox… consistent with weak-form efficiency."
  ([arXiv 2512.15720](https://arxiv.org/abs/2512.15720))
- Theory: volatility forecastability *generates* sign forecastability only when
  expected returns are non-zero, and sign dependence is **weakest at the highest
  frequencies** (daily/intraday) — i.e. minute-scale single-bar direction is
  among the *least* favorable horizons.
  ([NBER w10009, Christoffersen & Diebold, *Mgmt Sci* 2006](https://www.nber.org/papers/w10009))
- Independent corroboration from the gamma angle: dealer gamma feedback
  "amplif[ies] volatility magnitude in either direction but does not predict the
  sign of returns." ([arXiv 2511.22766](https://arxiv.org/pdf/2511.22766))

**→ Design decision:** abandon the single-next-bar sign target permanently (it's
the proven dead end). Direction work must change the *label* — horizon, barrier,
or conditioning — never just the features.

### B. Intraday momentum is the real (but conditional) directional effect [STRONGLY CORROBORATED — agents 1, 3, 4]
- SPY (1993–2013): the first half-hour return predicts the **last** half-hour
  with in-sample R²=1.6% (OOS 1.4%); timing strategy Sharpe 1.08 vs 0.29
  buy-and-hold, "remains significant even after transaction costs."
  ([Gao, Han, Li & Zhou, *Market Intraday Momentum*, JFE 2018](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866))
- The effect is **concentrated**: stronger on high-volatility, high-volume,
  recession, and macro-news days (Gao et al.).
- Mechanistically attributed to short-gamma dealer hedging + leveraged-ETF
  rebalancing forcing end-of-day continuation, robust across 60+ futures
  1974–2020. ([Baltussen, Da, Lammers, Martens, JFE 2021](https://ideas.repec.org/a/eee/jfinec/v142y2021i1p377-403.html))
- **Caveat (cuts against us):** predictability is *greater for lower-liquidity*
  instruments; the most-liquid ETF is the *hardest* to time. Gamma-fragility
  momentum is "stronger for the least liquid underlying securities."
  ([Barbon & Buraschi, "Gamma Fragility"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3725454))

**→ Design decision:** (1) prioritize **regime/time-of-day conditioning** (E3) —
this is where the literature says any edge lives. (2) Add an **open-to-close /
time-of-day-conditioned probe variant** modeled on Gao et al. (3) Mild support
for prioritizing **IWM over SPY/QQQ** as the target (less liquid → more
timeable). (4) Set EV expectations low — R²≈1.6% is a *weak* signal.

### C. Label reframes: triple-barrier + meta-labeling are the defensible combo [CORROBORATED — agents 2 & 5]
- Triple-barrier labels each event by which volatility-scaled barrier
  (profit-take / stop-loss / time) is touched *first* — encoding a realistic exit
  path instead of an arbitrary fixed-interval sign.
  ([DeepWiki / mlfinlab](https://deepwiki.com/quantopian/mlfinlab/6.3-triple-barrier-method))
- A controlled experiment (triple-barrier + meta-labeling) lifted OOS accuracy
  17%→63% and precision 0.17→0.20 on mean-reversion, precision 0.48→0.54 on
  trend — **real but modest, and precision-only.**
  ([Hudson & Thames](https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy-triple-barrier-method/))
- Longer/dynamic horizons can raise directional predictability but create
  **overlapping label windows** that require purging + embargo or the backtest
  leaks. ([Wikipedia / Purged CV](https://en.wikipedia.org/wiki/Purged_cross-validation))
- Trend-scanning (t-value-maximizing horizon) is itself an unguarded
  **multiple-comparisons hazard.**
  ([mlfinlab / trend scanning](https://random-docs.readthedocs.io/en/latest/implementations/labeling_trend_scanning.html))

**→ Design decision:** E1 (longer horizon) and E5 (triple-barrier) are
well-motivated, but E1 **must** add embargo ≥ horizon and E5 **must** add
uniqueness weighting. Avoid t-value-maximizing horizon search (data-snooping).

### D. Meta-labeling depends on a primary edge — it cannot create one [CORROBORATED — agents 2 & 5]
- Meta-labeling "does not generate additional trading signals; its function is to
  filter out weaker signals," so performance "depends heavily on the accuracy of
  the primary model." ([Wikipedia / Meta-Labeling](https://en.wikipedia.org/wiki/Meta-Labeling))
- It improves **precision / F1 / Sharpe**, not recall or direction; on a no-edge
  primary it "would likely only reduce the downside."
- Independent critique: cascading two models on the same features is "squeezing
  the same orange twice"; a grid-search reproduction found **average Sharpe
  *lower*** with meta-labeling.
  ([QuantConnect critique](https://www.quantconnect.com/forum/discussion/14706/why-meta-labeling-is-not-a-silver-bullet/))
- Leakage traps: train primary/secondary on **strictly disjoint data**; weight by
  **average uniqueness** + sequential bootstrap (triple-barrier labels overlap →
  violate IID); validate with **purged k-fold + embargo**, never plain k-fold.
  ([Hudson & Thames / sequential bootstrapping](https://hudsonthames.org/bagging-in-financial-machine-learning-sequential-bootstrapping-python/))

**→ Design decision (load-bearing for the staged plan):** meta-labeling (E4) is
**gated on E0/E2 first proving a primary side better than random**. If no primary
edge exists, skip E4 entirely — it's evidence-backed wasted compute. This is the
core justification for "reuse-first probes before building the toolkit."

### E. Dealer gamma is vol, not direction [WELL-SOURCED — agent 3]
- Positive gamma → counter-cyclical hedging → lower realized vol + mean reversion;
  negative gamma → pro-cyclical hedging → amplified moves. **Symmetric in
  direction, asymmetric only in magnitude.**
  ([SpotGamma](https://spotgamma.com/gamma-exposure-gex/), corroborated by arXiv 2511.22766)
- MM net 0DTE gamma *negatively predicts future intraday volatility* — a vol
  claim. ([Dim, Eraker, Vilkov, SSRN 4692190](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4692190))
- Data-quality caveats: GEX sign is **modeled, not observed** (vendors disagree on
  sign/levels); OI input is **T-1 stale** precisely when intraday precision is
  wanted. ([InsiderFinance](https://www.insiderfinance.io/resources/the-ultimate-guide-to-gamma-exposure-gex))
- Charm/vanna OPEX-drift directional claims are **vendor marketing**, no
  peer-reviewed after-cost evidence. [LOW]

**→ Design decision:** use our gamma/regime features for E3 **conditioning**
(vol-regime stratification, mean-revert vs trend), **not** as a direct
directional predictor. Don't build a "GEX → up/down" probe.

### F. FTFC has no rigorous validation [agent 4]
- Time-series momentum is real but a ~12-month phenomenon, and even that is
  contested (asset-by-asset evidence "quite weak"; pooled t-stat unreliable under
  bootstrap). ([AQR/MOP](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum);
  [Huang et al. critique](https://alphaarchitect.com/are-trend-following-and-time-series-momentum-research-results-robust/))
- "The Strat" FTFC is presented purely as a discretionary/educational pattern;
  **no peer-reviewed backtest, win-rate, or significance test** could be located.
  The one practitioner backtest with numbers (73% win, PF 2.0) omits costs, OOS,
  and a baseline; the author concedes MTF "is not a standalone edge."
  ([FXOpen](https://fxopen.com/blog/en/how-can-you-use-the-strat-method-in-trading/),
  [QuantifiedStrategies](https://quantifiedstrategies.substack.com/p/multi-timeframe-analysis-and-strategy))

**→ Design decision:** E0 (deterministic FTFC baseline) stays as a *measurement*,
not a hope. Treat any FTFC hit-rate as unvalidated until it clears purged CV +
the EV bar. A conjunction filter that cuts sample size without lifting edge is the
expected null result.

---

## Net implications for the experiment matrix

| Lit finding | Effect on plan |
|---|---|
| Single-bar sign = coin flip (A) | Permanently retire `next_close>next_open`; vary the label. |
| Intraday momentum is conditional/time-of-day (B) | Elevate **E3 regime + a new time-of-day/open-to-close probe**; lower EV expectations. |
| Less-liquid = more timeable (B) | **Target IWM first**, then SPY/QQQ. |
| Triple-barrier + meta-labeling modest/precision-only (C,D) | Keep E5/E4 but gate E4 on a proven primary edge; mandatory embargo + uniqueness. |
| Meta-labeling needs a primary edge (D) | **E0/E2 are the gate for E4** — the staged plan's central control flow. |
| Gamma = vol not direction (E) | Use gamma features for **conditioning only**, not a direct probe. |
| FTFC unvalidated (F) | E0 is a sober measurement; expect a null. |

**Prior on the verdict:** the literature makes an *unconditional* directional ship
unlikely. The realistic best case is a **PARTIAL/conditional** edge in a specific
regime/time-of-day pocket that clears the EV bar; the base case is a
**DEAD-END** confirmed rigorously. Either is a valid, decision-useful outcome —
and per the EV decision rule, both beat shipping an overfit unconditional model.

---

## Sourcing caveats (honest limits of this scan)
- Several primary PDFs (SSRN, ScienceDirect, SqueezeMetrics, Macrosynergy,
  Huang et al.) returned 403 / unparseable-binary; the affected claims rest on
  publisher abstracts or credible secondary summaries and are tagged [MED] in the
  per-agent reports. The most decision-relevant such gap is that **net-of-cost
  Sharpe of the Baltussen intraday-momentum effect could not be confirmed from a
  readable source.**
- The strongest pro-meta-labeling sources (Hudson & Thames, Wikipedia) carry a
  documented vendor / conflict-of-interest angle; the skeptical reproduction is a
  forum post, not peer-reviewed. The *mechanism* of meta-labeling is uncontested;
  independent peer-reviewed evidence it reliably adds OOS Sharpe is thin and
  partly contradicted.
- "Absence of a durable post-cost above-50% single-bar directional result" is an
  absence-of-evidence bounded by search coverage, not a proven impossibility.

## Full per-agent reports
The five raw agent reports (with every claim, confidence tag, and source URL)
were captured during the 2026-06-04 scan. This document is the merged synthesis;
the per-agent detail lives in the session transcript.
