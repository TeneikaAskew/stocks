# Trading Workflow Audit — Multi-Track Evaluation Plan

## Context

Three weeks of fast iteration (Phase 0.7.6 momentum tuning shipped 2026-05-07,
ticker calibration 2026-05-06, earnings reactions enhancements 2026-05-07,
signal-monitor TZ fix 2026-05-07) have changed the system meaningfully. You
need a clear map of **what's working / what's broken / what's still pending**
across the full pipeline, evaluated against actual market behavior on
**2026-05-04 → 2026-05-07** (4 trading days; today 2026-05-08 is excluded
since it's mid-session and incomplete).

This plan splits the audit into **7 tracks designed to run in parallel
without touching each other**. Each track produces written analysis + a
backlog of follow-up issues; no code changes (per your scope choice).
Per-ticker engineering (Track E) is the largest scope: full per-ticker
rebuild across 1m/5m/15m/30m/1h/4h for SPY/IWM/QQQ.

### What's already known from exploration

- **Architecture diagram**: `/home/user/stocks/Architecture.drawio` (122 KB, last
  modified 2026-05-08). Track F audits and updates it.
- **Watchlist source of truth**: `watchlists` Cloud SQL table (not config
  file). Per-surface flags: `in_brief`, `in_insight`, `signals`. Default
  ETFs (SPY, IWM, QQQ) are populated via this table, not hardcoded.
- **Intraday table**: ONE logical table `market_data_intraday`, LIST-partitioned
  by ticker into `_spy`, `_iwm`, `_qqq`, `_spx`, `_other`. References to
  `market_data_intraday_*` below mean "the partitions of that one table".
- **Exit targets are hardcoded global defaults** (`lib/config.py:ExitConfig`):
  CALL +0.30%, PUT +0.38%, CALL stop −0.15%, PUT stop −0.20%, CALL time
  stop 30 min, PUT 35 min. They are NOT computed from ticker historical
  ATR / volatility / win-rate distributions. The comment at
  `gcp/signal_monitor.py:764` explicitly flags per-ticker calibration as
  "a follow-up". Track E's job is to replace these with per-ticker,
  data-driven values.
- **Per-ticker engineering today**: Only RSI ranges per ticker
  (`ticker_calibration` Tier A). Combo bonuses, FTFC weights, exit targets,
  time stops, and momentum-vs-mean-reversion selection are all global.
  Track E rebuilds this layer.
- **Output persistence**: Brief → `premarket_analysis`, insights →
  `insight_reports`, alerts → `signal_alerts`. All replayable post-hoc.
- **DB access from this environment**: Direct Cloud SQL access is available
  in this sandbox — query the DB directly, no `db-query.yml` workflow
  needed.

### File-boundary map (so tracks don't collide)

| Track | Reads | Queries (read-only) | Writes |
|---|---|---|---|
| A — Foundation | `gcp/fetchers/_watchlist.py`, `gcp/schema.sql`, fetcher scripts | `watchlists`, `market_data_daily`, `market_data_intraday_*`, `daily_rates` | findings doc only |
| B — Brief | `gcp/premarket_brief.py`, `lib/strat.py`, `lib/strat_levels.py` | `premarket_analysis`, `premarket_analysis_history` | findings doc only |
| C — AI Insights | `gcp/insight_pipeline_job.py`, `lib/agents/`, `lib/insights.py` | `insight_reports`, `insight_runs`, `model_routing` | findings doc only |
| D — Intraday Alerts | `gcp/signal_monitor.py`, `lib/strategies/` | `signal_alerts`, `trades` | findings doc only |
| E — Per-Ticker Rebuild | `lib/strategies/calibration.py`, `lib/strat.py`, `lib/strategies/config.py`, `lib/strategies/timeframe.py` | `watchlists`, `signal_alerts` (90+ day history), `ticker_calibration`, `market_data_intraday` partitions | findings doc + `recommended_per_ticker_config.json` + new reusable script `scripts/analysis/per_ticker_calibration.py` |
| F — Architecture Diagram | `Architecture.drawio`, `docs/ARCHITECTURE.md`, `gcp/deploy.sh` | none | `Architecture.drawio` (only file edited) |
| G — Synthesis (runs LAST) | All track outputs | none | top-level findings + prioritized issue list |

No two tracks edit the same file. No two tracks query data in conflicting
ways. A–F can run concurrently; G runs after the others complete.

---

## Track A — Foundation: Watchlist & Data Pipeline Health

**Goal**: Verify the inputs everything else depends on are clean and fresh
for the eval window (May 4–7).

**Scope**:
1. **Watchlist state**:
   - Query `watchlists` for current rows. Confirm SPY/IWM/QQQ are present
     with the correct surface flags (`in_brief=TRUE`, `in_insight=TRUE`,
     `signals=TRUE`).
   - Look for unexpected entries (added then never removed) and
     soft-deleted rows that should be hard-deleted.
2. **Daily data freshness** for May 4–7:
   - Query `market_data_daily` for rows per ticker per session.
   - Verify all 50+ indicator columns are non-null.
   - Check for NULL-close placeholder rows (per
     `docs/incidents/2026-04-30-null-rows.md`).
3. **Intraday data coverage** for May 4–7:
   - Query each `market_data_intraday_*` partition (`_spy`, `_iwm`, `_qqq`,
     `_spx`).
   - Count bars per session per ticker (expect ~390 bars from 9:30 to 4:00
     ET). Flag sessions with < 380 or > 400.
4. **SPX gap investigation**:
   - The Dec 2025 SPX intraday gap is open. Confirm whether it's still
     missing or now backfilled.
5. **Fetcher run audit**:
   - Check Cloud Run Job execution logs for `fetch-market-data`,
     `av-intraday-nightly`, `fred-rates-daily` over May 4–7. Any failures?

**Critical files**:
- `gcp/fetchers/_watchlist.py` — watchlist loader
- `gcp/fetchers/fetch_market_data.py:404` — daily fetcher entry
- `gcp/fetchers/fetch_alphavantage_intraday.py:175` — intraday fetcher
- `gcp/schema.sql` — table definitions
- `docs/incidents/2026-04-14-market-data-daily-gap.md` — prior gap context
- `docs/incidents/2026-04-30-null-rows.md` — null-rows context

**Verification**: Direct SQL queries against Cloud SQL from this sandbox.

**Deliverables**:
- Per-ticker, per-session row-count + null-rate table
- List of failed fetcher runs in window
- Verdict: Foundation HEALTHY / DEGRADED / BROKEN
- Backlog: any data-quality issues to fix

---

## Track B — Premarket Brief Evaluation

**Goal**: Did the 8:30 AM brief on May 4–7 give an accurate read of each
session?

**Scope**:
1. **Did it run?**
   - Confirm one `premarket_analysis` row per (ticker, date) for May 4–7
     × {SPY, IWM, QQQ}. Expect 12 rows.
   - Check `premarket_analysis_history` for retries / failures.
2. **Section quality** (sample 1 day, e.g. May 7):
   - Pull the row's full JSON. Verify all 4 embed sections populated:
     overview, strat levels, earnings calendar, economic events.
   - Cross-check strat candle classification against actual prior-day
     candle (compute manually from `market_data_daily`).
3. **Bias accuracy** (per session in window):
   - Brief said bias = X for ticker T at 8:30 AM.
   - Actual session direction (close vs prior close): Y.
   - Compute hit rate: brief_bias matched actual direction (hit / miss /
     mixed for sideways days within ±0.3%).
4. **Levels accuracy**:
   - Brief published trigger levels (PDH, PDL, breakout zones).
   - For each level, did intraday price actually touch it? Was the call
     correct (breakout held vs faded)?
5. **Entry/stop/target sanity**:
   - Brief uses global +0.30% / -0.38% pct targets, 30/35 min time stops.
   - For days where the bias was right, did the target get hit before the
     time stop? (This is partial overlap with Track D — Track B reports
     the brief's predicted outcome, Track D reports actual fired alerts.)

**Critical files**:
- `gcp/premarket_brief.py` (entry: line 2036+, output: line 2148)
- `lib/strat.py:376` — `compute_strat_status()` (shared with insights)
- `lib/strat_levels.py` — level map builder
- `lib/earnings_reactions.py` — earnings lean summary
- `gcp/schema.sql` — `premarket_analysis` table definition

**Verification**: SQL queries on `premarket_analysis` joined with
`market_data_daily` for actual outcomes.

**Deliverables**:
- 4-day × 3-ticker accuracy matrix (bias hit/miss, level touch rate)
- Section-by-section quality assessment (one sampled day)
- Verdict: Brief WORKING / WORKING WITH GAPS / BROKEN
- Backlog: any per-section issues found

---

## Track C — AI Insights Evaluation

**Goal**: Did the 8:45 AM insights pipeline produce useful, accurate calls
on May 4–7? Were costs reasonable? Did Strat integration hold?

**Scope**:
1. **Did it run?**
   - One `insight_reports` row per (ticker, as_of) for May 4–7 × 3 ETFs.
   - `insight_runs` audit: success status, model used, tokens, latency,
     cost.
2. **Convergence with brief**:
   - For each (ticker, date), compare insights `direction` and conviction
     vs brief's bias. Are they directionally aligned? When they disagree,
     is there a clear reason (different timeframe, fresher data)?
3. **Play quality**:
   - For each insight, the `plays` array specifies (timeframe, setup).
   - For May 4–7 plays, did the proposed entry trigger? If yes, did the
     setup behave as described?
4. **Strat integration check**:
   - Verify the `strat_analyst` agent output mirrors what
     `compute_strat_status()` returns for the same inputs (i.e. both brief
     and insights see the same Strat state).
5. **Entry / exit specificity** (the STRAT-relevant question):
   - For each play, did the insight specify a concrete trigger price /
     level (e.g. "break above 2D candle high at $X")? Or was it vague
     ("looks bullish")?
   - Did it specify an exit / invalidation level the same way?
   - Vague calls = useless for STRAT; concrete trigger + invalidation =
     usable.

6. **Best application — strategy factor analysis** (the
   "why are most plays only hitting 3/8?" question):

   The signal-scoring system has ~8 distinct factors split across two
   strategies. Momentum has 7 (post Phase 0.7.1 prune); mean-reversion
   has a near-mirror set. `MIN_CONDITIONS_MOMENTUM=5` (raised 2026-05-06),
   but `MIN_CONDITIONS=3` for mean-reversion — which is why most plays
   surface as 3-of-8.

   **Factor inventory** (read from `lib/strategies/momentum.py` and
   `lib/strategies/mean_reversion.py`):
   - **Momentum CALL (7)**: `consecutive_up`, `rsi_bullish_recovery`,
     `above_vwap`, `above_ema9`, `rvol_above_recent`, `atr_expansion`,
     `rsi_thrust`
   - **Momentum PUT (7)**: mirror — `consecutive_down`,
     `rsi_bearish_recovery`, `below_vwap`, `below_ema9`,
     `rvol_above_recent`, `atr_expansion`, `rsi_thrust`
   - **Mean-reversion (TBD by reading `mean_reversion.py`)** — list,
     compare to momentum, identify overlap and uniques

   **For each factor, compute over May 4–7 across SPY/IWM/QQQ**:
   1. **Fire rate**: % of intraday bars where the factor was true
      (across all bars, not just signal bars). Pull from
      `signal_alerts.conditions_met` JSONB plus a recomputation against
      `market_data_intraday` partitions for bars where no signal fired.
   2. **Discrimination score**: difference between fire-rate-on-winning-
      signals vs fire-rate-on-losing-signals. A factor that fires
      equally on winners and losers contributes nothing.
   3. **Co-fire matrix**: which pairs of factors fire together? If two
      factors are 95% correlated, they're effectively one factor with
      double weight.

   **Anomaly check** (the user's hypothesis):
   - Was the factor introduced based on a single backtest or single
     observed pattern (n=1 anomaly)?
   - Trace each factor back to the commit that introduced it and the PR
     description. Phase 0.7.x commits (2026-04 onward) are the most
     recent additions: `rvol_above_recent`, `atr_expansion`,
     `rsi_thrust`.
   - Walk-forward stability: does the factor's discrimination score
     hold across 6+ folds, or is it concentrated in 1–2 lucky months?

   **Precedent**: The codebase already removed
   `stoch_rsi_not_overbought` in Phase 0.7.1 because it fired on 72.2%
   of bars (free score, no discrimination). That's the exact pattern to
   look for again.

   **"Best application" deliverable**:
   - Ranked table: factor → fire rate → discrimination score →
     co-fire correlations → anomaly verdict
   - Recommendation per factor: KEEP / DEMOTE (used as weight, not
     gate) / DROP
   - Recommended `MIN_CONDITIONS` per strategy after the prune (e.g.
     "after dropping factors X and Y, MR should require 4-of-5 not
     3-of-7")
   - **The plays you'll want to lean into**: which factor combinations
     showed the highest win-rate over May 4–7? This becomes the
     "preferred play setup" per ticker, feeding Track E.

**Critical files**:
- `gcp/insight_pipeline_job.py` (entry: line 430+ for AS_OF)
- `lib/agents/orchestrator.py` — 11-node agent graph
- `lib/agents/summarizers.py` — context extraction (calls
  `compute_strat_status`)
- `gcp/insight_discord_push.py` — Discord dispatcher
- `gcp/schema.sql` — `insight_reports`, `insight_runs`, `model_routing`
- `lib/strategies/momentum.py` — 7-factor CALL / PUT condition set
- `lib/strategies/mean_reversion.py` — mean-reversion factor set
- `lib/strategies/config.py` — `MIN_CONDITIONS`,
  `MIN_CONDITIONS_MOMENTUM` thresholds
- Git log: trace each Phase 0.7.x factor introduction to its PR for
  anomaly check

**Verification**: SQL on `insight_reports` × `insight_runs` joined with
`market_data_daily` for outcomes. Read the agent code to confirm Strat
integration didn't drift.

**Deliverables**:
- Per-day convergence matrix (brief vs insights agreement)
- Play-trigger and play-success rates
- Concrete-vs-vague entry/exit specificity rate (the STRAT bar)
- **Factor analysis table**: each of ~8 factors → fire rate →
  discrimination score → co-fire correlation → KEEP / DEMOTE / DROP
  recommendation
- **Best-play library**: ranked factor combinations that won most
  reliably over May 4–7 (per ticker — feeds Track E)
- Recommended new `MIN_CONDITIONS` thresholds post-prune
- Verdict: Insights WORKING / DRIFTING / BROKEN
- Backlog: prompt fixes to enforce concrete entry/exit levels;
  factor-prune PRs (one per dropped factor so risk is isolated)

---

## Track D — Intraday Alerts & Signal Monitor Evaluation

**Goal**: Did the signal monitor fire useful entry / exit alerts on
May 4–7? Were entries timely against the STRAT? Were exits the right
call?

**Scope**:
1. **Alert volume**:
   - Total signals fired per (ticker, day, direction).
   - ORB snapshots at 9:45 / 10:00 — confirm both fired.
2. **Entry accuracy** (the core question):
   - For each entry alert: did `target_price` get hit before
     `time_stop_minutes` elapsed? Use the `market_data_intraday`
     partitions for bar-by-bar reconstruction.
   - Compute: hit rate, miss rate, time-stop rate, RSI-extreme exit rate.
   - Bucketize by `total_score` quartile — high-conviction signals should
     have higher hit rates.
   - **STRAT-relevant**: was the entry triggered at the candle-trigger
     level (2U high / 2D low / failed-2 reclaim) or at an arbitrary
     mid-bar price? Entries off the trigger level are STRAT-violating
     and should be flagged.
3. **Exit accuracy**:
   - For each exit, was the reason (TARGET / TIME_STOP / RSI_EXTREME)
     correct given the actual price action?
   - **STRAT-relevant**: did exits respect the next opposing candle's
     break (the STRAT exit rule), or did the global +0.30%/-0.38% target
     fire too early / too late vs where the STRAT would have exited?
4. **Brief / insights alignment**:
   - For each `signal_alerts` row, the `brief_bias` and `brief_alignment`
     columns capture whether the signal aligned with the morning brief.
   - Compute alignment vs hit-rate: do aligned signals win more than
     opposed ones?
5. **Strategy mix**:
   - Signal Monitor runs both momentum and mean-reversion. From
     `conditions_met` (JSONB) and `strategy_agreement`, count which
     strategy fired each signal.
   - Per-ticker: which strategy is winning? (Feeds Track E.)

**Critical files**:
- `gcp/signal_monitor.py` (entry: line 147 `is_market_hours()`, fire: 373,
  persist: 707, exit: 801)
- `lib/strategies/momentum.py`, `lib/strategies/mean_reversion.py`
- `lib/strategies/catalyst_proximity.py`
- `gcp/schema.sql` — `signal_alerts` table (lines 702–760)

**Verification**: Direct SQL on `signal_alerts` joined to
`market_data_intraday` partitions for bar-by-bar outcome reconstruction.

**Deliverables**:
- Hit-rate matrix: ticker × direction × strategy × score-quartile
- Entry-trigger fidelity table (entries on STRAT trigger level vs not)
- Exit-reason accuracy table (target/time-stop/RSI vs STRAT-correct exit)
- Brief-alignment vs hit-rate correlation
- Verdict: Monitor WORKING / WORKING WITH GAPS / BROKEN
- Backlog: STRAT-violating entries or exits to fix, score-threshold
  tuning needs

---

## Track E — Per-Ticker Strategy Engineering (Largest Scope)

**Goal**: Build the per-ticker rebuild that doesn't exist today. Currently
only RSI ranges are per-ticker; momentum/MR selection, FTFC weights, combo
bonuses, exit targets, and time stops are all global.

**Equal-treatment principle**: SPY, IWM, and QQQ all get the *exact same*
analysis, *exact same* output schema, and *exact same* config-override
keys. IWM has historically gotten the per-ticker spotlight (because it
had the worst bug surface and the PR-6 #283 momentum issue), but the
deliverable here is a **per-ticker recommendation for every ticker on
the watchlist**, not an IWM deep-dive with SPY/QQQ as afterthoughts.

**Reusability principle**: The diagnostic logic must be a **reusable
script** (`scripts/analysis/per_ticker_calibration.py` —
new file, this is the one new file Track E creates) that takes a ticker
list as input and produces the recommendation JSON for any ticker. When
you add SPX or a new ETF to the watchlist next month, you re-run the same
script with the new ticker and get a calibration JSON without rewriting
the analysis. No hardcoded ticker symbols in the analysis pipeline —
pull the ticker list from the `watchlists` Cloud SQL table at runtime.

**Scope** — diagnostic + recommended config (no production code changes
yet; only the new analysis script):

1. **Per-ticker historical signal profile** — same metrics, every ticker,
   90+ days of `signal_alerts`. Computed by the reusable script:
   - Win rate by strategy (momentum vs MR)
   - Win rate by direction (CALL vs PUT)
   - Win rate by `total_score` quartile
   - Win rate by `timeframe_tag` (5m / 15m / 30m / 60m)
   - Win rate by `brief_alignment` (aligned / opposed / neutral)
   - Average return-pct per strategy
2. **Multi-timeframe analysis** (1m/5m/15m/30m/1h/4h) — same loop, every
   ticker:
   - Resample the relevant `market_data_intraday` partition to each
     timeframe.
   - For each ticker × timeframe, compute:
     - Mean and std of bar return
     - Auto-correlation (does momentum persist or mean-revert?)
     - Best-performing strat combo on that timeframe
   - **Key question** (answered per ticker, not per favorite ticker):
     which timeframe favors momentum vs mean-reversion?
3. **Per-ticker root-cause writeup** — for *every* ticker, not just IWM:
   - SPY: why is its current performance what it is? RVOL / ATR / RSI
     distributions, regime characterization.
   - IWM: same.
   - QQQ: same.
   - Comparison table so each ticker's profile is visible side-by-side
     (the current Track E quietly favored IWM by giving it a "deep dive"
     section while SPY/QQQ got bullet-list treatment).
4. **Recommended configuration JSON** — the deliverable, one file with
   one entry per ticker, identical schema for each:
   ```json
   {
     "SPY": { "call_rsi_range": [...], "put_rsi_range": [...],
              "min_conditions_momentum": N, "min_conditions_mr": N,
              "call_target": 0.00xx, "put_target": 0.00xx,
              "call_time_stop": NN, "put_time_stop": NN,
              "combo_bonus_overrides": {...},
              "preferred_strategy_call": "momentum|mr",
              "preferred_strategy_put": "momentum|mr",
              "preferred_timeframe_call": "5m|15m|30m|60m",
              "preferred_timeframe_put": "5m|15m|30m|60m" },
     "IWM": { ... same keys ... },
     "QQQ": { ... same keys ... }
   }
   ```
   No ticker has unique keys. If a recommendation can't be made for a
   ticker (insufficient data), the value is `null` and a `notes` field
   explains why — the schema stays uniform.
5. **Backtest the recommended configs** (analytically, no code change):
   - For each recommended override, replay against the 90-day history
     and report projected win-rate delta vs current global config.
   - Same backtest function applied to all tickers identically.

**Critical files**:

*Read-only (existing logic):*
- `lib/strategies/calibration.py` — Tier A per-ticker RSI calibration
  (the only existing per-ticker layer)
- `lib/strategies/config.py` — global Tier B fallback values
- `lib/strategies/timeframe.py` — currently global timeframe selection
- `lib/strategies/momentum.py`, `lib/strategies/mean_reversion.py`
- `lib/strat.py` — `COMBO_BONUS_CALL/PUT` (lines 29–55), FTFC weights
  (lines 62–70)
- `lib/strategies/catalyst_proximity.py`
- `lib/walk_forward.py` — reusable backtest replay engine
- `gcp/schema.sql` — `watchlists` table (ticker source), `ticker_calibration`
  table (current per-ticker config destination)

*New (this is the only new file Track E creates):*
- `scripts/analysis/per_ticker_calibration.py` — the reusable
  diagnostic script. Inputs: ticker list (default = pulled from
  `watchlists` table where `signals=true`), lookback window (default 90
  days). Outputs: `recommended_per_ticker_config.json` and a per-ticker
  markdown writeup. Re-runnable for any ticker added later.

**Verification**: Run the script for SPY, IWM, QQQ. Confirm the output
JSON has identical schema for all three. Confirm the writeup gives each
ticker equivalent depth (no ticker is missing the regime / RVOL / ATR /
RSI distribution table). Smoke-test the script with a 4th synthetic
ticker (e.g. add SPX temporarily) to prove it works on new tickers
without code changes.

**Deliverables**:
- `recommended_per_ticker_config.json` with **one entry per
  watchlist-signaled ticker**, identical schema across all entries
- Per-ticker root-cause writeup (one section per ticker, equivalent depth)
- Side-by-side comparison table: SPY vs IWM vs QQQ on every metric
- Reusable script committed to `scripts/analysis/` so adding a 4th or
  5th ticker is "add to watchlist + re-run script" rather than "write a
  new analysis"
- Projected impact per ticker: expected win-rate delta per recommendation
- Verdict per ticker (urgent custom config / minor tweak / fine on
  globals)
- Backlog: implementation PRs split by ticker (so SPY changes don't risk
  breaking IWM and vice versa)

---

## Track F — Architecture Documentation Alignment

**Goal**: Bring **both** `docs/ARCHITECTURE.md` *and* `Architecture.drawio`
into alignment with what actually exists today. Per the user,
`docs/ARCHITECTURE.md` was originally **derived from** the .drawio, so the
two should be reconciled — not treated as one being primary and the other
auto-generated. The .drawio's mxGraph XML is human-readable and parseable,
so the source-of-truth content can be extracted from it directly.

**Order of operations** (this ordering is load-bearing — do not reverse):

1. **Extract the .drawio inventory first.** The .drawio is mxGraph XML —
   parse it, list every node (id, label, parent group/swimlane) and
   every edge (source → target, label). This produces a flat
   "current-as-diagrammed" component list.
2. **Cross-check against today's ground truth** (7-layer map below).
   Categorize each diagrammed node as: still-correct / outdated /
   missing-but-needed.
3. **Update `docs/ARCHITECTURE.md` FIRST.** Because the .md was derived
   from the .drawio, edits to the .md are easier to express and easier
   to review than edits to mxGraph XML. Land the corrections in the .md
   first — add new components, rename outdated ones, remove dead ones.
4. **Then update `Architecture.drawio` to match the corrected .md.**
   Mirror every change made in step 3 into the diagram. New components
   become new mxCell nodes; renames become label edits; removed
   components are deleted.
5. **Final alignment check.** Diff the .md component list against the
   .drawio component list (post-edit). They must agree node-for-node.
   Any mismatch is a bug in this track's output.

**The 7-layer ground truth to validate against**:
- Watchlist layer (DB-backed `watchlists` table, per-surface flags)
- Data ingestion (daily / intraday / FRED / earnings fetchers, GH
  Actions cron schedule)
- Brief (8:30 AM, `gcp/premarket_brief.py`, `premarket_analysis` table)
- AI Insights (8:45 AM, 11-node agent graph, Vertex/Anthropic model
  routing, Cloud Tasks for on-demand refresh)
- Signal Monitor (9:25 AM Cloud Run Service, 60s polling, ORB snapshots
  9:45/10:00)
- Frontend (FastAPI + React, 13 routers, 11 pages, the playbook /
  insights / brief / signals surfaces)
- Failure handling (auto-issue + auto-PR per workflow failure)

**Watch for**: the auto-refresh workflow
(`.github/workflows/refresh-architecture-docs.yml`). Verify whether it
actually regenerates `docs/ARCHITECTURE.md` from code today or whether
that path has lapsed. If the workflow is live and rewrites the .md,
your manual .md edits will be clobbered next run — in that case the fix
must land in the regenerator script (likely `scripts/`) instead of the
.md directly. Flag this finding before editing.

**Critical files**:
- `Architecture.drawio` (mxGraph XML, will edit in step 4)
- `docs/ARCHITECTURE.md` (will edit in step 3, *if* not regenerated)
- `.github/workflows/refresh-architecture-docs.yml` (verify
  regeneration behavior — read step 0 of this track)
- Any `scripts/refresh_architecture*.py` referenced by the workflow
- `gcp/deploy.sh` (canonical Cloud Run / Scheduler config — ground
  truth for what's actually deployed)

**Verification**:
- `.md` and `.drawio` post-edit produce identical component lists when
  flattened.
- Every component in the 7-layer ground truth appears in both files.
- No components appear in either file that don't exist in the codebase.

**Deliverables**:
- Updated `docs/ARCHITECTURE.md`
- Updated `Architecture.drawio`
- A flat component-list table (markdown, in the findings doc) showing
  pre-edit vs post-edit, with status column (kept / added / renamed /
  removed)
- A note on whether the auto-refresh workflow is live and what it does
- Backlog: any code-level documentation gaps surfaced during
  reconciliation (e.g. components that exist but have no module
  docstring)

---

## Track G — Synthesis (RUNS LAST)

**Goal**: Pull A–F findings into a single top-level audit report and
prioritized issue list.

**Scope**:
1. Read each track's findings doc.
2. Build the master "Working / Wobbly / Broken / Pending" table covering
   every component.
3. Cross-track correlation: e.g. if Track B says brief bias was 50%
   accurate but Track D says aligned signals had 70% hit-rate — what does
   that mean?
4. Prioritize the combined backlog:
   - **P0**: data-correctness or continuity gaps (e.g. SPX still missing,
     monitor restart in window, fetcher silently failing)
   - **P1**: per-ticker rebuilds for tickers that flunked Track E
   - **P2**: prompt / routing tuning from Track C
   - **P3**: docs / diagram / cosmetic
5. Write the executive summary the user can read in 5 minutes.

**Critical inputs**:
- Findings docs from Tracks A–F (each track will produce one)

**Verification**: Manual review of all track outputs.

**Deliverables**:
- `audit-summary.md` — master Working/Wobbly/Broken/Pending table
- Prioritized GitHub-issue-ready backlog
- One-page exec summary

---

## How to run this

**Each track is its own conversation.** Open a new Claude Code session for
each, paste the track's "Scope" + "Critical files" + "Deliverables"
sections, and tell it the eval window is 2026-05-04 → 2026-05-07. Each
track produces a markdown findings doc; commit those to
`docs/audit/2026-05-08/track-X.md`.

**Run order**:
1. **Parallel batch 1** (no dependencies on each other): A, B, C, D, F
2. **After A is done**: E (Track E reuses Track A's data-quality verdict
   to know whether to trust the historical numbers)
3. **After A–F done**: G

**Estimated effort per track**:
- A, F: ~30 min each (mostly DB queries + diagram editing)
- B, C: ~1 hr each (SQL + cross-checks)
- D: ~1.5 hr (continuity + accuracy + alignment)
- E: ~3 hr (the big one — per-ticker × per-timeframe analysis)
- G: ~30 min (synthesis only after others land)

Total ~8 hr, but parallelizable down to ~3.5 hr wall-clock if you run A,
B, C, D, F simultaneously.

---

## Verification (end-to-end)

After all tracks complete:
- `docs/audit/2026-05-08/` contains 7 markdown files (one per track + the
  G summary)
- `Architecture.drawio` has been updated
- A prioritized backlog of GitHub issues exists, ready to file
- The user can answer "what's working, what's broken, what's pending"
  in one paragraph from the G exec summary

---

## ⚠️ DO NOT START THIS PLAN IN THIS CONVERSATION

This conversation built the plan; it does **not** execute it. The scope
is too large for a single context window — attempting all seven tracks
here will hit context-compression and produce shallow findings on the
later tracks.

**Instead, share this plan across separate conversations and assign
tracks as follows. Six sessions total (not seven), because A and E are
bundled:**

| Session | Tracks | Why |
|---|---|---|
| 1 | **A + E** (same conversation) | E directly consumes A's data-quality verdict and watchlist contents. Splitting them forces re-discovery; bundling them lets one session walk straight from "is the data trustworthy?" into "build the per-ticker calibration on top of trusted data." |
| 2 | B (Brief) | Independent of A/E. |
| 3 | C (AI Insights) | Independent. |
| 4 | D (Intraday Alerts) | Independent. |
| 5 | F (Architecture docs alignment) | Independent. |
| 6 | G (Synthesis) | **Runs last.** Waits for sessions 1–5 to land their findings docs. |

**Steps for the human running these:**

1. Open six new Claude Code sessions (do not run them in this one).
2. In each session, paste **only** that session's track section(s) —
   Goal, Scope, Critical Files, Verification, Deliverables — plus this
   shared header context:
   - Eval window: **2026-05-04 → 2026-05-07**
   - Watchlist source: `watchlists` Cloud SQL table (not config file)
   - DB access: direct Cloud SQL is available in the sandbox
   - Output destination: `docs/audit/2026-05-08/track-<X>.md`
3. For Session 1 (A + E), paste **both** track sections so the session
   knows it owns the full A → E pipeline. It should produce
   `track-A.md` first, then `track-E.md` after.
4. Respect the run order:
   - **Wave 1 (parallel)**: Sessions 1 (A + E), 2 (B), 3 (C), 4 (D),
     5 (F).
   - **Wave 2 (after Wave 1 finishes)**: Session 6 (G — synthesis).
5. When each session finishes, the findings docs should be committed
   to `docs/audit/2026-05-08/`. Session 6 reads all of them and
   produces the synthesis.

**Why bundle A + E**: Track E builds the per-ticker calibration *on top
of* the historical signal data Track A validated. If A finds the
intraday partition for a ticker is stale or has gaps, E's win-rate
numbers for that ticker are noise. The same conversation that confirmed
the data is clean is the one that should run the calibration — no
re-explaining the data shape, no re-loading the watchlist contents into
context.

**Why split everything else**: Tracks B/C/D each involve dense SQL on
different tables and different time windows. Track F is a pure
documentation reconciliation. Bundling them blurs context and produces
shallow findings on the later tracks. Splitting them keeps each session
focused and lets the waves run in parallel.

**This conversation's job ends with the plan file.** Hand the file to
the Wave 1 sessions and let them go.
