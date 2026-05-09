# Track C Implementation Plan — close out audit-flagged work

**Branch:** `claude/audit-insights-factors-FWpHz`
**Audit folder:** `docs/audit/2026-05-08/`
**Track:** C (AI Insights pipeline) — owner of items in Track G's
prioritized backlog tagged `C.*`.
**Plan author:** Claude Code session (this turn).
**Plan location at write time:** this file
(`/root/.claude/plans/review-the-following-documenation-wobbly-bear.md`).
**Plan location after approval:** copied to
`docs/audit/2026-05-08/track-C-implementation-plan.md` and committed to
the feature branch as the first commit on top of the merged track-C.md.

---

## Context

The 2026-05-08 multi-track audit produced **66 backlog items** (14 P0,
21 P1, 24 P2, 7 P3) across the 7-layer system. My Track C deliverable
(`docs/audit/2026-05-08/track-C.md`, merged on `main` via PR #290) covered
the AI Insights pipeline for SPY/IWM/QQQ on 2026-05-04 → 2026-05-07 and
flagged 5 P0 + 4 P1 + 4 P2 + 1 P3.

When the synthesis (`docs/audit/2026-05-08/track-G.md` + `audit-summary.md`,
landed on `main` 2026-05-08 via PR #294) reconciled my findings against the
other tracks, **most of my P0s rolled up to other tracks**:

- **G.P0.1** (unfreeze daily fetcher) → **Track A** owns; gates everything else
- **G.P0.4** (brief stale-warn guard) → **Track B** owns
- **G.P0.6** (`signal_alerts.conditions_met` JSONB writer fix) → **Track D** owns; blocks my deferred per-factor audit
- **G.P0.10** (EOD reconciliation Cloud Run Job) → **Track D / A** own; backfills exits I couldn't measure
- **G.P0.11** (momentum-zero-fires investigation) → **Track D** owns; blocks my factor-prune verdict

So Track C's actual work is concentrated in **P1/P2/P3** plus some
verification work post-cross-track-unblock. The user's direction:
*"work the top priorities from your track and everything before another
track blocks it — first round; then when blocker removed, finish."*

This plan organizes the work into **two rounds**:

- **Round 1** = everything I can ship before any other track has to land code.
- **Round 2** = verification + finish-the-investigation work that activates only after specific cross-track deliverables merge.

---

## Master backlog of Track C items (from `track-G.md` §3)

| ID | Item | Priority | Round | Blocker (if any) |
|---|---|---|---|---|
| G.P1.4 | Insights `regime=orb_only` over-classification (10/12) | P1 | **R1** | none (insight pipeline reads fresh `market_data_daily`) |
| G.P1.8 | Brief↔insights direction divergence UI | P1 | **R2** | G.P1.5 (Track B fixes brief `signal_status` ↔ `ftfc_direction` contradiction) |
| G.P1.9 | Thesis-vs-`targets[]` decoupling | P1 | **R1** | none |
| G.P1.10 | `brief_bias` populated only on 5/7 — verify post-fix | P1 | **R2** | G.P0.1 (Track A fresh data) + Track D's G.P1.10 investigation |
| G.P2.1 | Per-factor walk-forward audit on Phase 0.7.x confirmers | P2 | **R2** | G.P0.6 (JSONB writer) + G.P0.11 (momentum fires) |
| G.P2.2 | `strategy_agreement` field re-measure | P2 | **R2** | G.P0.11 (momentum fires) |
| G.P2.3 | Mean-reversion `MIN_CONDITIONS=3` walk-forward calibration | P2 | **R2** | G.P0.11 |
| G.P2.4 | `model_routing` per-role swap UI decision | P2 | **R1** | none |
| G.P2.12 | Reflection memory dormant — commit or remove `JournalRef` | P2 | **R1** | none |
| G.P2.13 | `failed_sections` recurring exception class (backtest 7/12, sentiment 3/12) | P2 | **R1** | none |
| G.P2.14 | `supporting_signals` direction can contradict report direction | P2 | **R1** | none |
| G.P2.24 | `db-query.yml` workflow concurrency / cancelled runs | P2 | **R1** | none (Track G notes "fix may be unobtainable") |
| G.P3.1 | `conviction` enum collapses to `medium` 12/12 | P3 | **R1** | none |
| G.P3.2 | `insight_reports.cost_usd` is sum-only — persist per-role costs | P3 | **R1** | none |
| G.P3.3 | `insight_reports_history` not verified — confirm writes | P3 | **R1** | none |

**Round 1 = 11 items. Round 2 = 4 items (3 in one PR + 1 standalone + 1 verification).**

---

## Cross-track dependencies — file as GitHub issues *first*

Per the user's direction, file issues for each cross-track blocker so
the wait is explicit and trackable. Expected open at the time of plan
write (verify with `mcp__github__list_issues` before filing duplicates):

| Issue # | Cross-track item | Blocks Track C item(s) | Owning track | Pre-flight status (2026-05-08 skim) | Post-2026-05-09 status |
|---|---|---|---|---|---|
| ~~[#295](https://github.com/TeneikaAskew/stocks/issues/295)~~ | **G.P0.1** unfreeze `fetch-market-data` daily fetcher | G.P1.10 verification | A | Identified, not started | ✅ **CLOSED** — shipped via [PR #321](https://github.com/TeneikaAskew/stocks/pull/321) + ops |
| ~~[#296](https://github.com/TeneikaAskew/stocks/issues/296)~~ | **G.P0.6** `signal_alerts.conditions_met` JSONB writer fix + backfill | G.P2.1, G.P2.2, G.P2.3 | D | Identified, not started | ✅ **CLOSED** — shipped via [PR #308](https://github.com/TeneikaAskew/stocks/pull/308) (landed 2026-05-08, before issue filed) |
| ~~[#297](https://github.com/TeneikaAskew/stocks/issues/297)~~ | **G.P0.11** momentum zero-fires investigation | G.P2.1, G.P2.2, G.P2.3 | D | Partially mitigated, unverified | ✅ **CLOSED** — instrumentation in [PR #320](https://github.com/TeneikaAskew/stocks/pull/320), analysis in [PR #330](https://github.com/TeneikaAskew/stocks/pull/330). PR-G still gates on ≥2 weeks of post-fix data (earliest start: 2026-05-22) |
| [#298](https://github.com/TeneikaAskew/stocks/issues/298) | **G.P1.5** brief `signal_status` ↔ `ftfc_direction` contradiction | G.P1.8 | B | Identified, not started | ⏳ **STILL OPEN** — P1 backlog hasn't been touched per close-out doc |
| [#299](https://github.com/TeneikaAskew/stocks/issues/299) | **G.P1.10** `brief_bias` populated only on 5/7 | G.P1.10 (Track C verify) | D (via B) | Cause identified by Track D | ⏳ **STILL OPEN** — TZ-bug fix already shipped via [PR #279](https://github.com/TeneikaAskew/stocks/pull/279); needs post-fix data verification (PR-I) |

**Pre-flight skim (2026-05-08, post-issue-filing):** all five blockers
were unshipped on `main` at audit close.

**Post-2026-05-09 update:** Track A+E P0 close-out (see
[`p0-status-2026-05-09.md`](p0-status-2026-05-09.md)) plus Track D's
9-PR sprint shipped 12 of 14 audited P0s. **Three of Track C's five
blockers (#295, #296, #297) are now resolved.** Round 2 PR-G and PR-I
are now data-gated rather than code-gated — both can proceed once a
trading week or two of post-fix data accumulates. PR-H (UI for
brief↔insights divergence) remains genuinely blocked on #298.

---

## Round 1 — independent work (ship before any blocker)

Six PRs, structured per the user's "one PR per investigation, batched
fixes" guidance.

### **PR-A — Batched mechanical fixes** (~4 hr total)

Mechanical, low-risk Track C changes that don't require investigation.
Single PR keeps review cost down.

| Item | Files to touch | Recipe |
|---|---|---|
| **G.P3.1** conviction enum collapses | `lib/agents/prompts.py:189` (`PORTFOLIO_MANAGER_PROMPT`) | Either (a) rewrite the PM prompt to actually use `low / medium / high` with examples, or (b) remove the enum from `lib/agents/schema.py:191` `InsightReport.conviction` and `lib/agents/schema.py:328` `PortfolioManagerOutput.conviction`. Verify route after change: `confidence_score` (already a 0.0-1.0 float) is the load-bearing field; conviction is purely UX. **Default: option (a)** — fix the prompt with explicit examples for each level. |
| **G.P2.14** `supporting_signals` direction contradiction | `lib/agents/summarizers.py` (the `summarize_signals_history` function) | Add a `direction_filter` parameter that defaults to None and is passed in by `orchestrator.py` once the trader's direction is known. Filter the recent N alerts by `direction == trader.direction.upper()` mapped (`long` → `CALL`, `short` → `PUT`). Add a unit test asserting `supporting_signals` doesn't include the opposite direction. |
| **G.P3.3** `insight_reports_history` not verified | (read-only — query) | Run a one-shot SQL via `db-query.yml`: `SELECT count(*), count(DISTINCT (ticker, as_of)), max(written_at) FROM insight_reports_history`. If 0 rows, file follow-up issue against the writer in `gcp/insight_pipeline_job.py`. If populated, mark closed. |
| **G.P3.2** per-role cost persistence | `lib/agents/orchestrator.py:_Tracker` (lines ~95-110), `gcp/schema.sql:958` (`insight_reports`), `gcp/insight_pipeline_job.py:262` (the upsert) | Add `per_role_cost JSONB` column to `insight_reports`. `_Tracker` stays in-memory but its dict serializes to that column. Schema migration: `ALTER TABLE insight_reports ADD COLUMN IF NOT EXISTS per_role_cost JSONB`. |

**Verification for PR-A:**
- Run existing test suite (`make test`) green
- Manual smoke: dispatch one on-demand insights run for SPY against current data, inspect `insight_reports.per_role_cost` JSONB, confirm conviction is no longer always `medium` if option (a) chosen
- New unit tests for direction-filter on `supporting_signals`

### **PR-B — Investigation: `regime=orb_only` over-classification** (G.P1.4) (~6 hr)

Track G §2.3 confirms the cause is **not** brief staleness — the insight
pipeline reads fresh `market_data_daily`. Three candidate sub-causes
already documented in track-C.md §4:

1. `pre_high / pre_low` clearing logic (`max(ref, ctx.pre_high or ref)`) too aggressive — a 0.2% gap shouldn't clear PWH/PMH/PQH/PYH
2. Multi-timeframe level set naturally tight on tickers in sustained uptrend
3. `effective_pdh` mother-bar walk-back regression to far-below trigger when prior bar is `1` (inside)

**Investigation steps:**

1. Read `lib/agents/trade_planner.py:153-262` (`select_trigger_and_regime`) end-to-end
2. Replay each of the 12 reports' inputs through the function with verbose logging — print which level the loop selected and which got "cleared"
3. Quantify: for each (ticker, day), what fraction of PDH/PWH/PMH/PQH/PYH was cleared by `pre_high`? Is it always all of them?
4. Decide root cause: aggressive `pre_high` (most likely), naturally tight levels (acceptable behavior), or `effective_pdh` regression (real bug)

**Likely fix:**
- If `pre_high` is the cause: tighten the clearing predicate to `pre_high > level + buffer` rather than `pre_high >= level`, where buffer is e.g. 0.5 × ATR_5
- If level set is naturally tight: ship a separate "extended-but-actionable" regime that publishes the next unbroken level (e.g. PWH if PDH cleared) as the trigger rather than collapsing to orb_only
- If `effective_pdh` regression: skip mother-bar walk-back when reference price is above the inner-bar high

**Beyond root cause** (Track G §G.P1.4 also notes): even when orb_only is correct, the 8:45 AM placeholder should be re-issued post-9:45 ORB with real ORB high/low. **Defer the re-issue logic to a separate follow-up PR** — too large for this investigation.

**Verification:**
- Replay against 12 historical reports — confirm fix improves the orb_only rate without making valid orb_only cases incorrectly classify as `normal`
- Add unit test in `tests/test_trade_planner_regime.py` (create if missing) covering each of the three sub-causes
- Manual smoke: re-run insights for one ticker against current data with the fix, confirm regime distribution is sane

### **PR-C — Investigation: thesis-vs-`targets[]` decoupling** (G.P1.9) (~3 hr)

LLM `thesis` text references specific target levels that don't appear in
JSON `targets[]` (which got overridden by deterministic planner).
Sample: QQQ 5/7 thesis says *"targeting 677.8, 691.09 and 704.38"* but
`targets=[]`.

**Investigation:**

1. Read `lib/agents/prompts.py:189` (PM prompt) and `lib/agents/orchestrator.py:441-453` (PortfolioManagerOutput → InsightReport assembly)
2. Decide between two fix flavors:
   - **(a) Post-process** the thesis text: regex-match `\$?\d+(\.\d+)?` numerals near words like "target" / "above" / "below" / "stop", replace with the deterministic planner's actual numbers
   - **(b) Forbid level names in the thesis** via prompt: PM prompt explicitly says "do NOT include any specific price levels in `thesis` — they go in `entry_zone`, `stop`, `targets`, `key_levels`, and `invalidation` only"

**Recommended:** option (b). Post-processing is brittle (regex on free prose), and the schema already has the right home for each number. Add a unit test that asserts no number in the format `\$\d+(\.\d{2})?` appears in `report.thesis` for a sample run.

**Verification:**
- New unit test for thesis no-numbers
- Manual smoke: run for SPY 5/7-equivalent data, eyeball the thesis text

### **PR-D — Investigation: `failed_sections` recurring failures** (G.P2.13) (~1 day)

`backtest` analyst failed 7/12 (58%); `sentiment` 3/12 (25%) in the
audit window. Need to find the recurring exception class.

**Investigation:**

1. Pull the relevant Cloud Run Job logs for the 12 insights runs (5/4-5/7 × SPY/IWM/QQQ) via `gcloud logging read` — filter for `ERROR` and the analyst names
2. Read `lib/agents/summarizers.py:summarize_backtest_metrics` and `summarize_news_sentiment` — look for the failure modes
3. Reproduce locally if possible: run `summarize_backtest_metrics(ticker='QQQ', as_of=date(2026,5,4))` against current DB

**Likely fixes:**
- `backtest`: probably a missing `historical_signals` row for the (ticker, lookback-window) combination — either guard with empty-result handling, or trigger a one-time backfill
- `sentiment`: likely AlphaVantage rate-limit or empty news window — add retry logic or graceful degradation

**Verification:**
- Targeted unit tests for each failure mode found
- Re-run the affected sample dates after fix; expect `failed_sections=[]` more often

### **PR-E — Investigation + decision: reflection memory** (G.P2.12) (~1 day)

Reflection-memory infrastructure exists (`pgvector` extension, ivfflat
index on `journal_entries.embedding`, `JournalRef` schema, retrieval
helper) but `query_embedding=None` is hard-coded in the production
caller — entire feature is dormant.

**Decision tree:**
- **Option A — wire it on:** add a Vertex `text-embedding-005` call at pipeline entry (`gcp/insight_pipeline_job.py:run_insight_pipeline` invocation) that embeds the day's bundle summary, pass to `run_insight_pipeline(query_embedding=...)`. Need to budget one extra Vertex call per ticker per day (≈$0.0001).
- **Option B — remove it:** strip `query_embedding` parameter from `run_insight_pipeline`, drop the `JournalRef` schema, drop `similar_past_trades` field, remove the pgvector index (or leave it for direct journal browsing).

**Recommendation:** option A. Reflection memory is one of the audit's
"is the system actually using its data?" failure modes; the cost is
trivial. Do it.

**Verification:**
- New unit test: pipeline with embedding wired returns at least one `JournalRef` (mocked DB)
- Manual smoke: dispatch insights for SPY against real DB, verify `similar_past_trades` is non-empty if `journal_entries` has any matches in window

### **PR-F — Standalone observability touch-ups** (G.P2.4 + G.P2.24) (~2 hr)

Two small standalones that would otherwise dribble; bundling for review efficiency.

| Item | Files / action |
|---|---|
| **G.P2.4** `model_routing` per-role swap UI dormant | All 7 roles point at `vertex:gemini-2.0-flash`. Two options: (a) keep the UI but document that it's dormant by design until cost-vs-quality data justifies diversification, (b) remove the per-role swap from the /admin React page and document a single-model assumption. Track G recommends a 1-week A/B with `judge` on Gemini 2.5 Pro, but that's a separate experiment. **For this PR**, just commit the docs decision (option a) — leave the UI; mark it dormant in the README. The actual A/B is its own follow-up. |
| **G.P2.24** `db-query.yml` workflow contention | Track G already notes "fix may be unobtainable (GitHub-side behavior)". Steps: read the workflow YAML and verify `concurrency.cancel-in-progress: false` is present. Then test by dispatching 3 SQL batches in 5-second succession and observing the cancellation pattern. If cancellation is genuinely GitHub-side and unfixable, document as "known limitation" in `CLAUDE.md` `## Database access` section. If fixable (e.g. by changing concurrency group key), file a follow-up. |

---

## Round 2 — work that activates only after specific cross-track PRs land

Each item below is **paused** until the named blocker merges. When a
blocker merges, resume the corresponding item.

### **PR-G — Per-factor walk-forward audit** (G.P2.1 + G.P2.2 + G.P2.3) (~1 day)

**Resume when:** G.P0.6 (Track D writes native JSONB array) **AND** G.P0.11 (Track D proves momentum can fire) **AND** at least 2 weeks of post-fix data accumulated.

**Plan:**
1. Run the §3.10-style fire-rate methodology against the three Phase 0.7.x momentum confirmers (`rvol_above_recent`, `atr_expansion`, `rsi_thrust`):
   - Per-factor fire rate per bar (target: <50% — anything higher is "free score" like the `stoch_rsi_not_overbought` retired in PR #229)
   - Win-rate-on-fire vs win-rate-overall (discrimination check)
   - Walk-forward stability across 4-6 folds
2. Same exercise for mean-reversion's existing 5 conditions, with a focus on whether `MIN_CONDITIONS=3` clears spread+slippage costs. If not, recommend `MIN_CONDITIONS=4`.
3. Re-measure `strategy_agreement` payload now that momentum fires. Update `gcp/schema.sql:744-760` rationale comment to reflect post-Phase-0.7.x stacked-rate.

**Deliverable:** investigation doc updating §5 of `track-C.md`, plus
backlog of factor-by-factor KEEP/DEMOTE/DROP recommendations with
walk-forward evidence.

### **PR-H — Brief↔insights divergence UI** (G.P1.8) (~1 day frontend)

**Resume when:** G.P1.5 (Track B resolves brief `signal_status` ↔ `ftfc_direction` contradiction) merges.

**Plan:**
- Add a "Disagreement" panel to the React playbook page rendering (when brief and insights disagree directionally) the brief's claim, the insight's claim, and the FTFC alignment of each
- Possibly extend the insights API response to include `brief_bias_at_publish` so the frontend doesn't have to do a second join

**Verification:**
- Storybook story for the disagreement panel
- E2E test for a sample 5/7-style day where brief said PUT and insights said long

### **PR-I — `brief_bias` verification** (G.P1.10 verify side) (~1 hr)

**Resume when:** G.P0.1 (Track A unfreezes fetcher) **AND** Track D's G.P1.10 investigation (`get_premarket_bias()` failing silently?) merges.

**Plan:**
- Run the same SQL from track-C.md result_006: `SELECT alert_date, ticker, brief_bias, COUNT(*), COUNT(brief_alignment), SUM(CASE WHEN brief_alignment='aligned' THEN 1 END), SUM(CASE WHEN brief_alignment='opposed' THEN 1 END) FROM signal_alerts WHERE alert_date BETWEEN <post-fix-start> AND <today> GROUP BY ...`
- Confirm `brief_bias` is now populated on every (ticker, day) bucket where the brief published
- If still missing, re-open against Track D / Track B with new data

---

## Critical files and helpers to reuse

| File | Purpose | Round 1/2 |
|---|---|---|
| `lib/agents/orchestrator.py:_Tracker` (lines ~95-110) | Per-call cost accumulator — extend for per-role persistence (G.P3.2) | R1 PR-A |
| `lib/agents/prompts.py:189` (`PORTFOLIO_MANAGER_PROMPT`) | PM prompt — fix conviction (G.P3.1) and forbid level names (G.P1.9) | R1 PR-A, PR-C |
| `lib/agents/summarizers.py:summarize_signals_history` | Where the direction filter lands (G.P2.14) | R1 PR-A |
| `lib/agents/summarizers.py:summarize_backtest_metrics`, `summarize_news_sentiment` | Failed-sections root-cause investigation (G.P2.13) | R1 PR-D |
| `lib/agents/trade_planner.py:153-262` (`select_trigger_and_regime`) | orb_only investigation (G.P1.4) | R1 PR-B |
| `lib/agents/schema.py:191` (`InsightReport`), `schema.py:328` (`PortfolioManagerOutput`) | Conviction enum — keep + fix prompt (option a) or remove enum (option b) | R1 PR-A |
| `gcp/schema.sql:958` (`insight_reports` DDL) | Add `per_role_cost JSONB` (G.P3.2) | R1 PR-A |
| `gcp/insight_pipeline_job.py:run_insight_pipeline` invocation | Wire `query_embedding` for reflection memory (G.P2.12) | R1 PR-E |
| `lib/agents/orchestrator.py:run_insight_pipeline` signature (lines 260-285) | Existing `query_embedding` param — already supported, just unused in production caller | R1 PR-E |
| `.github/workflows/db-query.yml` | Workflow contention investigation (G.P2.24) | R1 PR-F |

---

## Verification (end-to-end across the full plan)

After **Round 1** (PR-A through PR-F) merges:
- `make test` green
- Insight reports for the next batch run (Mon 5/11 morning?) show: `conviction` distribution non-degenerate; `supporting_signals` aligned with report direction; `failed_sections` rate measurably down; `per_role_cost` populated per-role; orb_only rate measurably reduced (target: <50% on a fresh-data day for SPY/IWM/QQQ)
- README / CLAUDE.md updated with model_routing dormancy decision and db-query workflow contention notes

After **Round 2** (PR-G through PR-I) merges:
- Per-factor walk-forward audit committed as `docs/audit/2026-05-08/track-C-factor-audit.md` with KEEP/DEMOTE/DROP recommendations
- React playbook page renders brief↔insights disagreement panel on disagreement days
- `signal_alerts.brief_bias` populated on every (ticker, day) bucket
- Track G `track-G.md` §3 "P1/P2/P3 — Track C" backlog items all checked off or rolled into follow-up issues

End-state: every `C.*` and `[C, X]` (cross-track) item in
`track-G.md` §3 has either landed code, an explicit "deferred / not
fixable" note, or a follow-up issue tracking it.

---

## Plan execution checklist (mark off as items complete)

### Pre-flight (before R1)
- [x] **Copy this plan** to `docs/audit/2026-05-08/track-C-implementation-plan.md`, commit, push (commit `7ee008e`)
- [x] **File cross-track issues** — #295, #296, #297, #298, #299 (commit `2856526` links them in)
- [x] Skim Track A/B/D's own track docs — confirmed all five blockers unshipped at audit-close moment
- [x] **2026-05-09 close-out update** — close #295/#296/#297; comment update on #298/#299 with current status

### Round 1 (no blockers)
- [x] **PR-A** — Batched mechanical fixes (G.P3.1, G.P2.14, G.P3.2, G.P3.3) → `claude/track-c-r1-mechanical-fixes` → **[PR #305](https://github.com/TeneikaAskew/stocks/pull/305) open**, MERGEABLE. Filed [#313](https://github.com/TeneikaAskew/stocks/issues/313) for the `run_kind='scheduled'` incidental finding discovered during G.P3.3 verification.
- [ ] **PR-B** — orb_only investigation (G.P1.4) → `claude/track-c-r1-orb-only`
- [ ] **PR-C** — Thesis-vs-targets decoupling (G.P1.9) → `claude/track-c-r1-thesis-targets`
- [ ] **PR-D** — failed_sections root cause (G.P2.13) → `claude/track-c-r1-failed-sections`
- [ ] **PR-E** — Reflection memory wiring (G.P2.12) → `claude/track-c-r1-reflection-memory`
- [ ] **PR-F** — Observability touch-ups (G.P2.4, G.P2.24) → `claude/track-c-r1-observability`

### Round 2 (gated)
- [ ] **PR-G** — Per-factor walk-forward audit (G.P2.1+2+3) — code blockers cleared (G.P0.6 #296 + G.P0.11 #297 closed); **now data-gated** — needs ≥2 weeks of post-fix data, earliest start 2026-05-22
- [ ] **PR-H** — Brief↔insights divergence UI (G.P1.8) — *still genuinely blocked on #298 (G.P1.5)*
- [ ] **PR-I** — `brief_bias` verification (G.P1.10) — code blockers cleared (G.P0.1 #295 closed; TZ-bug fix in PR #279); **now data-gated** — needs a few days of post-fix data

### Closeout
- [ ] Update this plan with each PR# next to its checkbox as work lands
- [ ] Open a final review PR rolling all R1+R2 work into a single `track-C-status.md` summary
- [ ] Cross-link every closed item back into `track-G.md` (or open a follow-up doc PR if track-G should be amended)

---

## Open questions / risks

1. **Round 1 sequencing within itself**: PRs A through F are independent, but PR-A's "remove conviction enum" (option b) would conflict with PR-B/C if those PRs touch `lib/agents/schema.py`. **Mitigation:** Lock in option (a) for conviction (fix prompt, keep enum) so the schema doesn't change in PR-A. Locked.
2. **PR-B (orb_only) result is unknown**: investigation may conclude "the planner is correct, the regime really is orb_only on most gap days." If so, reframe as a UX fix (re-publish post-9:45 ORB) rather than a planner bug. Either way, the PR ships an investigation note.
3. **PR-D (failed_sections) may need DB writes**: if `backtest` is failing because `historical_signals` is empty for a ticker, the fix may be a one-shot backfill rather than code. Track that as a sub-task.
4. **Reflection memory wiring (PR-E) adds Vertex cost**: ≈$0.0001 per ticker per day in embedding calls. Trivial but need to confirm with the user before shipping. Will note in the PR description and tag for explicit approval.
5. **Image-lag pattern from G.P0.11 may apply to my PRs too**: since the signal monitor / insights pipeline is shipped via Cloud Run image, deploys take ~12 min to roll. Note in each PR's "Test plan" that I'll verify against the *deployed* image after merge, not just CI.

---

## Out of scope

- Track A's data-freshness fix (G.P0.1) — owned by Track A
- Track B's brief contradiction fix (G.P1.5) — owned by Track B
- Track D's JSONB writer fix, momentum investigation, EOD reconciliation, exit-watcher backfill (G.P0.6/.10/.11, G.P1.10) — owned by Track D
- Track E's per-ticker overrides, MR PUT condition prune (G.P0.12-14) — owned by Track E
- Track F's auto-refresh PR investigation (G.P1.18) — owned by Track F
- Per-ticker calibration recurring job (G.P1.20-21) — owned by Track E
- Frontend rebuilds beyond the disagreement panel (G.P1.8 / G.P2.18)
