# Gamma Balance Audit — 2026-08-25

**Status:** RESOLVED same day — see §0. The evaluation below is preserved as
written (including the post-Codex correction); §0 records what shipped.
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

## §0 Resolution (2026-08-25, same PR)

The owner's directive — **"none of these should be null, ever"** — settled §7's
open decision in favour of fixing the metric rather than deleting its
monitoring. Shipped, verification-first (failing suite written before the
implementation: `tests/test_gamma_never_null.py`, 8 red → 14 green):

| Item | Outcome |
|---|---|
| R5 **adopted** | `compute_gamma_balance` redefined as the OI-weighted gamma **median** — cumulative \|net_gamma\|, anchored at each strike's center, interpolated to the half-mass point. Always defined for a chain with any gamma; NULL only for genuine data absence (§3.7). Spot-independent chain property. |
| Flip robustness | `compute_gamma_flip_bs` escalates its search window ±10%→±25%→±50% before concluding "no flip" — a real crossing just outside the caller's window can no longer manufacture NULL. Thin/IV-less/one-sided-across-±50% chains still return None (genuine signal). |
| R1 **superseded** | Instead of deleting the balance nullity check, it returns to the strict dense shape (90%/1-day): with the median always defined, a NULL is a real pipeline bug — the check now means what the owner wants it to mean. The old metric's two failed calibrations (#644, #762) were symptoms of thresholding a regime-tracking quantity; that quantity no longer exists. |
| R2 **applied** | `strat_features_5m.gamma_flip` nullity check added at 90%/1-day (closes C-04). |
| R3 **mooted** | The feature no longer thins out on high-vol sessions; it stays in the model feature lists. The §9 `converse_breaks` query is now historical interest only. |
| R4 | Still open (incremental-vol ablation before sizing) — unchanged. |

**Post-deploy runbook (ordering matters):**
1. Deploy the image (`./gcp/deploy.sh build` + strat-engine/trading-system).
2. Rebuild `gamma_levels_eod` over at least the trailing window
   (`p2_build_gamma_levels`) so T-1 joins pick up median values, then refresh
   `strat_features_*` via `gcp/queries/strat_features_gamma_backfill.sql`
   (`./scripts/db_query_cr.sh -f ... --commit`). Full-history rebuild is the
   same job over all quarters (~90s of build_summary per header estimate).
3. `freshness-watchdog` then goes green on both gamma checks; close #765.
   Until step 2 lands, the strict checks will truthfully flag the not-yet-
   rebuilt sessions — deploy and rebuild in the same maintenance window.

**Feature-semantics note:** `gamma_balance_price` values change scale/meaning
(zero-crossing → median). LightGBM models pick the new distribution up on
their next walk-forward retrain; do not mix pre/post rows in a single training
window without noting the 2026-08-25 boundary.

Collateral corrections while verifying (§8 updated in place): C-02 was
over-stated — `_na_to_none_records` (PR #650) already NaN-sanitizes the
`upsert_dataframe` fallback, so both write paths bind SQL NULL; what remained
was only a vestigial `import psycopg2` gate in `bulk_copy_upsert` forcing the
slow path on an unused dependency (removed), plus possible pre-#650 historical
float8-NaN rows (data question, not code). C-03 was wrong: `.fillna("unknown")`
is an explicit, distinguishable sentinel — exactly what §3.7 asks for — not a
violation.

---

## §1 Executive summary

> **Correction (2026-08-25, post-review).** The first draft of this audit claimed
> `gamma_balance_price IS NULL` was *equivalent* to `regime = negative_gamma`.
> **That was wrong**, and a Codex review on PR #771 caught it. A cumulative path
> can cross zero an even number of times and finish negative, so a negative-gamma
> chain can still return a balance price. Only the one-way implication holds. The
> section below is the corrected version; §2 carries the counterexample.

`gamma_balance_price` is NULL **only when** the session is in the negative-gamma
regime — but the reverse does not follow. The implication runs one way:

```
gamma_balance_price IS NULL   ⟹   total_gex < 0   ⟹   regime = 'negative_gamma'
        (given a put-dominated lowest strike, which real ETF chains have)

regime = 'negative_gamma'     ⇏   gamma_balance_price IS NULL
```

| Question asked | Answer |
|---|---|
| Why is it NULL? | The running total of `net_gamma`, accumulated from zero at the bottom of the ladder, never came back through zero. That requires the chain to be put-gamma-heavy overall. |
| Upstream or downstream? | **Neither.** No fetcher gap, no code regression, no chain-completeness issue. |
| Is it a bug? | The metric is fragile by construction. A chain always *has* a balance point; this construction finds one only when the running total happens to change sign. |
| Should it be NULL? | Not for the reason it is. And it is disproportionately absent on the high-volatility sessions where it would matter most. |
| Is the feature salvageable? | Not as written. `compute_gamma_flip_bs` already does the job and resolved on 42/42 chains, including every one where balance was NULL. |

**What this does and does not license.** A NULL tells you the regime is negative —
which `total_gex` already tells you directly and densely, so the NULL adds
nothing. A *non*-NULL tells you nothing about the regime either way. As a regime
signal the column is therefore redundant in one direction and silent in the
other. That is the basis for R1/R3 — **not** an equivalence.

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
chains are put-dominated at low strikes, so the running total goes negative on
the first strike.

### What follows (and what does not)

**Holds.** If there is no crossing, the running total never changed sign, so it
ends on the side it began. With a put-dominated lowest strike that side is
negative. And because `gex = net_gamma × spot² × GEX_MULTIPLIER` with both
factors strictly positive, `sign(total_gex) ≡ sign(Σ net_gamma)`. Therefore:

> **NULL ⟹ total_gex < 0 ⟹ regime = negative_gamma.**

**Does not hold.** The converse. A cumulative path may cross zero, come back,
and finish negative — an even number of crossings — which returns a balance
price in a negative-gamma regime. Minimal case, run through the production
function: per-strike `net_gamma` of `[-2, +5, -4]` gives cumulative
`[-2, +3, -1]`, two crossings, `total_gex = -102.01`, and
`compute_gamma_balance` returns `100.4`.

This is not only a toy. `test_negative_regime_can_still_return_a_balance` builds
it at realistic magnitudes from structures real index chains have — a call
cluster below spot lifting the running total above zero, a heavy put wall above
spot dragging the final total back negative:

| upper put OI | end cumulative | crossings | total_gex | balance |
|---|---|---|---|---|
| 1,400 | +1,072.8 | 1 | +429,122 | 194.42 |
| 3,000 | −65.1 | 2 | −26,047 | **194.42** |
| 5,000 | −1,487.5 | 2 | −595,009 | **194.42** |
| 9,000 | −4,332.3 | 2 | −1,732,933 | **203.45** |

Every row from `upper put OI` = 3,000 down is a negative-gamma chain that still
returns a balance price.

### How often does the converse fail in practice?

**Unknown, and this audit cannot answer it.** Across ~14,000 randomized chains
from naturally-shaped generators — smooth wings, and wings with random
single-strike OI clusters — the converse never failed once: every negative-gamma
chain was NULL. Producing a failure required deliberately alternating call/put
dominance across the ladder with enough magnitude to move the running total
across zero twice.

So the two conditions may well coincide on most real sessions. But "may well" is
not evidence, and the frequency question is exactly what §9's query settles.
**Run it before acting on R1 or R3.**

### Corroboration for the direction that holds

The B6 entry in `EXPERIMENT_REGISTRY.md` (2026-06-07) independently recorded
that `compute_gamma_flip` (the old name for this function) *"returns None on
~half the days — disproportionately the negative-gamma days, which were dumped
into 'unknown'"*. That is the one-way implication showing up in production data,
logged as a quirk rather than traced.

#744's 07-28 table separately noted the metric is binary per session — 0% or
100%, never partial. That is consistent with a single chain-level condition
evaluated once per `(ticker, date)` and fanned out to every row of that day, and
inconsistent with a chain-completeness gap, which would produce partial days.

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

Every NULL falls on one of those sessions (§2, forward direction), and B6
independently measured the column absent on roughly half of all days,
*disproportionately* the negative-gamma ones. So the feature thins out precisely
where the volatility is — and it remains live in both the `direction` and `size`
model axes (`strat_config.py:50`; it is *not* in either `NEAR_DEAD` set, so it
survives pruning).

The precise claim: NULLs are confined to negative-gamma sessions, and B6's
~50%-of-days absence rate means a large share of those sessions lose the
feature. It is **not** true that every negative-gamma session is NULL — see §2.

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

> **Superseded by §0** — the owner's never-null directive resolved this table
> the same day (R5 adopted, R2 applied, R1 superseded, R3 mooted, R4 open).
> Preserved as written for the decision record.

Ordered by confidence. **None of these are applied in this PR** — the gamma math
is a trading-math decision and #744 already flagged it as needing quant judgment.

| # | Action | Confidence | Notes |
|---|---|---|---|
| R1 | Drop `strat_features_5m.gamma_balance_price` from `COLUMN_NULLITY_CHECKS` | High | Two independent reasons, neither needing the (false) equivalence. **(a)** A NULL only ever means negative-gamma, which `total_gex` reports directly and densely at 90%/1-day — so the check re-detects a condition already covered. **(b)** The column's fill rate tracks market regime rather than pipeline health, so a fixed nullity threshold cannot be calibrated stably: it has now been recalibrated twice (#644 → #762) and failed both times. |
| R2 | Add a nullity check for `gamma_flip` | High | It is the level `gamma_proximity` trades and it has **no** check today. Monitoring is currently inverted relative to value. |
| R3 | Drop `gamma_balance_price` from `STRAT_NUMERIC_FEATURES` | Medium | A feature whose absence is confined to high-vol sessions thins out where it would matter most. LightGBM tolerates the NaN, so this is a cleanup, not a correctness fix — and it is worth confirming against §9 first, since the practical NULL rate is what makes it dead weight. |
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
| C-02 | **Corrected (see §0):** first written as "the DQ1 family-B cast is still missing." In fact `_na_to_none_records` (PR #650) sanitizes NaN→None for every `upsert_dataframe` caller and the COPY path renders NaN as the CSV NULL token — both write paths bind SQL NULL. The remediation landed centrally, which is why the per-callsite cast DQ1 recorded never appeared. Remaining: the vestigial `import psycopg2` gate in `bulk_copy_upsert` (removed in this PR) and possibly historical float8-NaN rows written before #650 (verify with `col = 'NaN'::float8` if ever load-bearing). | `gcp/database.py:306` |
| C-03 | **Withdrawn (see §0):** `.fillna("unknown")` is an explicit, distinguishable sentinel — the opposite of a silent fallback, and what §3.7 prescribes. The category is also in `NEAR_DEAD` on both model axes. Original finding over-called. | `strat_data_builder.py:580` |
| C-04 | **Fixed (see §0):** `gamma_flip` nullity check added at 90%/1-day. | `scripts/audit_data_freshness.py` |

---

## §9 Scope and limits

Every claim above is derived from the code at `8749b83` and from chains run
through the **production** functions (`aggregate_by_strike` → `build_summary`),
per CLAUDE.md Rule 3.6 — no throwaway harness; the proof lives in
`tests/test_gamma.py` where it can be re-run.

**GCP credentials in this session return `ACCESS_TOKEN_TYPE_UNSUPPORTED`,** so no
production rows were queried. The production figures quoted (24.8% / ~55% /
~60%, the 0/312, the 2/18 ticker-days) are taken from the triage comments on
#744 and #765.

**This query is now a prerequisite, not a formality.** The first draft treated it
as a sanity check because the equivalence was believed proven. It isn't — §2 only
establishes the forward direction — so the practical question of how often the
two conditions coincide has to come from production:

```sql
SELECT ticker,
       count(*)                                                   AS n,
       count(gamma_balance_price)                                 AS bal,
       count(*) FILTER (WHERE total_gex > 0)                      AS pos_gex,
       -- MUST be 0: a NULL balance in a positive-gamma session would
       -- falsify even the forward implication in §2.
       count(*) FILTER (WHERE gamma_balance_price IS NULL
                          AND total_gex > 0)                      AS forward_breaks,
       -- Expected to be small; this is the number §2 cannot predict.
       -- It is the count of negative-gamma sessions that STILL produced a
       -- balance price, i.e. how much independent signal the column carries.
       count(*) FILTER (WHERE gamma_balance_price IS NOT NULL
                          AND total_gex < 0)                      AS converse_breaks
FROM gamma_levels_eod
WHERE date > current_date - 120
GROUP BY ticker ORDER BY ticker;
```

Read it as:

- `forward_breaks > 0` → §2 is wrong even in the direction claimed; discard this
  audit's reasoning and start over.
- `converse_breaks ≈ 0` → the column is, in practice, a redundant restatement of
  `total_gex < 0`. R1 and R3 are safe.
- `converse_breaks` materially above zero → the column *does* carry independent
  information on those sessions. R1 still holds on ground (b) — the check cannot
  be calibrated stably — but **R3 should be reconsidered**, because the feature
  is then not merely a regime echo.
