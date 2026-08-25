# Gamma Balance Audit — 2026-08-25

**Status:** Evaluation + one doc correction. The gamma math itself is UNCHANGED
pending a decision (see §7).
**Scope:** What `gamma_balance_price` is, why it is NULL, how gamma is consumed
across the platform, and whether we are harvesting the edge we validated.
**Trigger:** Repository owner — *"IWM should never be null, so there is concern
there and it could be upstream or downstream."* Correct instinct; the answer is
neither.
**Originating issues:**

- #744 — `freshness-watchdog` / `gamma_balance_price` stale for IWM (opened 07-20,
  auto-closed 08-25 on job recovery with its analysis unresolved)
- #765 — `freshness-watchdog` failing hourly (open)
- PR #741 — proposed dropping the check; closed as do-not-merge for lack of a mechanism
- B6 / DQ1 in `docs/EXPERIMENT_REGISTRY.md` — the 11-year gamma reassessment

---

## §1 Executive summary

`gamma_balance_price` is NULL **if and only if** the session is in the
negative-gamma regime. This is an algebraic identity, not a correlation, and it
holds through the production `build_summary` on 42 of 42 test chains.

| Question asked | Answer |
|---|---|
| Why is it NULL? | The chain is put-gamma-heavy. The metric can only resolve on call-heavy chains. |
| Upstream or downstream? | **Neither.** No fetcher gap, no code regression, no chain-completeness issue. |
| Is it a bug? | The metric is mis-specified. A chain always *has* a balance point; this construction cannot find it. |
| Should it be NULL? | No — and worse, it is NULL exactly on the high-volatility sessions where it would matter most. |
| Is the feature salvageable? | Not as written. `compute_gamma_flip_bs` already does the job and resolved on 42/42 chains. |

**The one-line version:** the nullity carries no information that `total_gex` —
already stored, already densely monitored — does not carry more directly.

---

## §2 The mechanism

`lib/gamma.py:524` walks strikes ascending, accumulating `net_gamma`, and returns
where the running total crosses zero:

```python
cumulative = 0.0
for r in rows:                      # rows sorted ascending by strike
    prev = cumulative
    cumulative += r["net_gamma"]
    if prev_strike is not None and prev * cumulative < 0:
        crossings.append(...)
if not crossings:
    return None
```

The accumulator starts at **zero at the bottom of the strike ladder**. Real ETF
chains are put-dominated at low strikes, so the running total dives negative on
the first few strikes and can only cross back through zero if it finishes
positive. Therefore:

> **A crossing exists ⟺ Σ net_gamma > 0 ⟺ the chain is net call-gamma-heavy.**

And because `gex = net_gamma × spot² × GEX_MULTIPLIER` with both factors strictly
positive:

> **sign(total_gex) ≡ sign(Σ net_gamma)**

Combining the two gives the identity:

```
gamma_balance_price IS NULL
  ≡  Σ net_gamma < 0
  ≡  total_gex < 0
  ≡  regime = 'negative_gamma'
```

**Evidence.** `tests/test_gamma.py::TestGammaBalanceNullityIdentity` runs 42
chains through `build_summary` across three spot/strike-grid configurations
(IWM-like $200/$1, SPY-like $600/$5, QQQ-like $450/$2.50), sweeping put/call OI
skew from 0.80 to 1.45. **42 agree, 0 disagree.** The tipping point sits at a
put/call OI skew of roughly 1.05–1.15.

**Corroboration.** The B6 entry in `EXPERIMENT_REGISTRY.md` (2026-06-07) already
recorded the empirical shadow of this — `compute_gamma_flip` (the old name for
this function) *"returns None on ~half the days — disproportionately the
negative-gamma days, which were dumped into 'unknown'"*. It was logged as a quirk
rather than traced to its cause.

**The observed data signature also predicts it.** #744's 07-28 table noted the
metric is binary per session — 0% or 100%, never partial. That is exactly what a
single global sign test, evaluated once per `(ticker, date)` and fanned out to
every row of that day, produces. A chain-completeness gap would produce partial
days. It never does.

---

## §3 Why IWM specifically

IWM is the small-cap hedging vehicle; its chain is persistently put-gamma-heavy,
so it sits below the tipping point most sessions. SPY and QQQ oscillate across
it. That predicts the production fill rates reported on #744 exactly:

| ticker | `gamma_balance_price` non-null | `total_gex` non-null |
|---|---|---|
| IWM | 24.8% | 100% |
| QQQ | ~55% | 100% |
| SPY | ~60% | 100% |

Nothing changed in the pipeline around the 2026-06-30 or 2026-08-18 onsets. No
commit between 2026-06-01 and 2026-07-15 touched `lib/gamma.py`,
`lib/options_greeks.py`, `gcp/fetchers/`, or `p2_build_gamma_levels.py`. What
changed is the market: all three tickers moved into a sustained put-heavy regime
together.

---

## §4 The consequence that matters

B6 established, over 11 years and 14k–25k bars per cell, that negative-gamma
sessions carry materially larger forward moves:

| ticker | neg-gamma fwd \|30m\| | pos-gamma fwd \|30m\| | ratio |
|---|---|---|---|
| IWM | 21.1 bps | 15.8 bps | 1.34× |
| QQQ | 21.7 bps | 13.1 bps | 1.66× |
| SPY | 18.5 bps | 9.9 bps | 1.87× |

Those are precisely the sessions on which `gamma_balance_price` is guaranteed
NULL. **The feature is present on quiet days and absent on violent ones** — and
it remains a live feature in both the `direction` and `size` model axes
(`strat_config.py:50`; it is *not* in either `NEAR_DEAD` set, so it survives
pruning).

---

## §5 Where gamma actually goes

| Surface | What it uses | Status |
|---|---|---|
| `gcp/research/p2_build_gamma_levels.py` | writes `gamma_levels_eod` | production |
| `strat_engine/strat_data_builder.py` | joins T−1 gamma into `strat_features_{tf}` | production |
| direction + size models | 7 continuous gamma features kept; all 9 discretized (`gamma_regime_*`, `gex_tercile_*`, `vex_tercile_*`) are `NEAR_DEAD` on **both** axes | production |
| `gcp/premarket_brief.py` | freshness footer + narrative | production |
| `lib/agents/summarizers.py` | narrative recaps | production |
| `gcp/build_realtime_gex.py` → `realtime_gex_15m` | `total_gex`, `total_dex`, `total_oi`, `gamma_flip`, `spot` — **no balance price** | production |
| `lib/strategies/gamma_proximity.py` | King approach, Gate break, **flip cross** | **research only** — referenced solely from `p2_outcomes_grid.py`, not wired into `gcp/signal_monitor.py` |

Two observations. The newer realtime GEX table **already dropped**
`gamma_balance_price` from its column set — the codebase's own more recent work
concluded it wasn't worth carrying. And the only strategy that trades gamma
levels does not fire in production.

---

## §6 Are we harvesting the edge?

No. The evidence and the wiring point in opposite directions.

1. **The volatility edge is real and unharvested.** B6 closed with open item (2),
   *"productionize vol-regime for position sizing / strategy selection."* Still
   open. `get_position_size(total_score, risk)` (`signal_monitor.py:773`) takes no
   volatility-regime input, and no gamma symbol appears anywhere in
   `lib/signals.py`, `lib/backtest.py`, or `gcp/signal_monitor.py`.
2. **The direction hypothesis is dead, and we keep feeding it.** B6's powered test
   (1,177 neg vs 438 pos days) found within-day 30m return autocorrelation of
   −0.012 vs −0.020 — zero in both. The 2026-07-08 importance audit independently
   marked every discretized gamma feature near-dead on both axes. Two methods,
   same answer.
3. **The tradeable level exists but isn't traded.** `gamma_proximity` implements
   flip-cross and King/Gate logic with FTFC gating and documented per-ticker hit
   rates, and fires nowhere in production.

**Caveat worth settling before acting on (1).** B6 measured gamma's
*unconditional* volatility split. The models measure *incremental* importance
alongside ~250 other features including ATR, RVOL and VIX. A feature can be
genuinely predictive and still add nothing on the margin. Do not build a sizing
model on the 1.87× number until that distinction is resolved — an ablation
against ATR/RVOL/VIX is the cheap version of the test.

---

## §7 Recommendations

Ordered by confidence. **None of these are applied in this PR** — the gamma math
is a trading-math decision and #744 already flagged it as needing quant judgment.

| # | Action | Confidence | Notes |
|---|---|---|---|
| R1 | Drop `strat_features_5m.gamma_balance_price` from `COLUMN_NULLITY_CHECKS` | High | Its nullity restates `total_gex`'s sign, which is monitored densely at 90%/1-day. This is what PR #741 proposed; it was closed for lack of a mechanism, and §2 supplies it. |
| R2 | Add a nullity check for `gamma_flip` | High | It is the level `gamma_proximity` trades and it has **no** check today. Monitoring is currently inverted relative to value. |
| R3 | Drop `gamma_balance_price` from `STRAT_NUMERIC_FEATURES` | Medium-high | A feature that is absent exactly on high-vol sessions is worse than no feature. LightGBM tolerates the NaN, so this is a cleanup, not a correctness fix. |
| R4 | Settle the incremental-vol question, then wire regime → `get_position_size` | Medium | The only recommendation here with revenue attached. Gated on the §6 caveat. |
| R5 | If a balance price is still wanted as a distinct quantity, redefine it as the **gamma median** | Medium | The strike where cumulative `\|net_gamma\|` reaches half the chain total. Always exists for a non-empty chain, and matches what the docstring already claims ("a balance point in OI-weighted gamma space"). Note this changes `tests/test_gamma.py::TestComputeGammaBalance::test_no_crossing_returns_none`, which currently pins the degenerate behaviour. |

`compute_gamma_flip_bs` is the ready replacement for R2/R3: across the same 42
chains — including all 24 in the negative-gamma regime where `gamma_balance` is
NULL 24/24 times — it returned a value **every time**. It re-prices each
contract's BSM gamma across candidate spots rather than walking stored chain
gamma, so it does not require a call-heavy chain. Already computed, already
stored, already in `realtime_gex_15m`.

---

## §8 Collateral findings

| # | Finding | Where |
|---|---|---|
| C-01 | **`docs/gamma_levels.md` taught a disproven rule.** It defined regime as "spot above/below flip" — the rule B6 found gives the *inverted* vol split (2,765 of 2,767 rows mislabelled) and which was replaced in code on 2026-06-07 by `sign(total_gex)`. The doc was never updated. **Corrected in this PR.** | `docs/gamma_levels.md:29-30` |
| C-02 | **DQ1 family-B cast still missing.** DQ1 flagged `flip_price` (now `gamma_balance_price`) as 56.7% IEEE-NaN rather than SQL NULL — IWM 77.5%, SPY 37.4% — with the fix recorded as a `.where(notna, None)` cast at write. The column is still written through a bare `.map()`. A float NaN counts as present to `count()`, so the nullity check and the feature loader can disagree about the same cell. | `strat_data_builder.py:574` |
| C-03 | **`gamma_regime` written with `.fillna("unknown")`,** converting a missing regime into a category the models learn from. `dealer_regime_GEX_nan_VEX_nan` exists as a one-hot level for the same reason. Rule 3.7-adjacent. | `strat_data_builder.py:580` |
| C-04 | **`gamma_flip` is unmonitored** while the degenerate metric pages hourly. | `scripts/audit_data_freshness.py` |

---

## §9 Scope and limits

Every claim above is derived from the code at `8749b83` and from chains run
through the **production** functions (`aggregate_by_strike` → `build_summary`),
per CLAUDE.md Rule 3.6 — no throwaway harness; the proof lives in
`tests/test_gamma.py` where it can be re-run.

**GCP credentials in this session return `ACCESS_TOKEN_TYPE_UNSUPPORTED`,** so no
production rows were queried directly. The production figures quoted (24.8% /
~55% / ~60%, the 0/312, the 2/18 ticker-days) are taken from the triage comments
on #744 and #765. **The mechanism is proven from code and does not depend on
them** — but R1/R3 should be sanity-checked against one live query before merging:

```sql
SELECT ticker,
       count(*)                                                   AS n,
       count(gamma_balance_price)                                 AS bal,
       count(*) FILTER (WHERE total_gex > 0)                      AS pos_gex,
       count(*) FILTER (WHERE (gamma_balance_price IS NOT NULL)
                          <> (total_gex > 0))                     AS identity_breaks
FROM gamma_levels_eod
WHERE date > current_date - 120
GROUP BY ticker ORDER BY ticker;
```

`identity_breaks` should be **0**. If it isn't, §2 is wrong for real chains and
every recommendation here needs revisiting.
