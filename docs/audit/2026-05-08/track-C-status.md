# Track C — final status (closeout 2026-05-09)

**Owner:** AI Insights pipeline (`lib/agents/`, `gcp/insight_pipeline_job.py`,
React `InsightsPage`).
**Audit:** [`track-C.md`](./track-C.md) (2026-05-08, 5/12 ticker-days
sampled). **Synthesis:** [`track-G.md`](./track-G.md) §3.
**Plan:** [`track-C-implementation-plan.md`](./track-C-implementation-plan.md).

This doc is the close-the-loop summary. Every audit-flagged Track C
item is either landed, deferred with a note, or rolled into a recurring
scheduled job. No remaining manual asks.

---

## Outcome

| Round | PRs landed | Status |
|---|---|---|
| Round 1 | 7 (one item split across 3 PRs) | ✅ all merged |
| Round 2 | 5 + 1 fix-up + 1 cron-schedule | ✅ all merged |
| Closeout | this PR | ✅ |

**12 PRs from the 2026-05-08 audit**, plus **3 follow-up PRs** from gaps
surfaced during R2 validation (PR-J / PR-K / PR-L), plus **1 fix PR** for
a schema bug in PR-G that the live-DB audit caught before the operator
did, plus **1 schedule PR** that took the two remaining "manual weekly"
asks off the operator's plate.

---

## Backlog → PR map

Every G.P-tagged Track C item from `track-G.md` §3, with the PR(s) that
addressed it.

### P1 (Track C own)

| ID | Item | Landed via |
|---|---|---|
| G.P1.4 | `regime=orb_only` over-classification (10/12 reports) | **PR #307** (suppress cleared-side trigger when `orb_only`) + **PR #334** (blue-sky synth trigger when uptrend at ATHs) + **PR #345** (tuple-unpack fix) |
| G.P1.8 | Brief↔insights direction divergence — no UI surface | **PR #353** (`BriefVsInsightsCard` on `InsightsPage` with `useBriefDirection` hook) |
| G.P1.9 | Thesis prose references levels not in `targets[]` | **PR #341** (decouple thesis prose from structured price levels) |
| G.P1.10 | `brief_bias` populated only on 5/7 (cross-track verify side) | **PR #357** (`verify_brief_bias.py` + 3 SQL files); live-DB audit 2026-05-09 confirmed 100% coverage on 5/7 + 5/8, zero post-fix NULL holes; **PR #366** schedules weekly recurring check |

### P2 (Track C own)

| ID | Item | Landed via |
|---|---|---|
| G.P2.1 | Per-factor walk-forward audit on Phase 0.7.x confirmers | **PR #355** (framework) + **PR #363** (SQL schema fix); **PR #366** scheduled weekly |
| G.P2.2 | `strategy_agreement` field re-measure | Same workflow — first scheduled run after ≥ 2 weeks post-Phase-0.7.x momentum data accumulates (~2026-05-23) |
| G.P2.3 | Mean-reversion `MIN_CONDITIONS=3` walk-forward calibration | Same workflow |
| G.P2.4 | `model_routing` per-role swap UI dormant | **PR #346** (documented as intentionally dormant in README; A/B experiment is its own follow-up) |
| G.P2.12 | Reflection memory dormant — `query_embedding=None` hardcoded | **PR #344** (auto-embed bundle summary; trivial $0.0001/ticker/day cost) |
| G.P2.13 | `failed_sections` recurring exception class | **PR #343** (graceful failed_sections + diagnostic reasons surfaced per role) |
| G.P2.14 | `supporting_signals` direction can contradict report direction | **PR #305** (direction-filter parameter on `summarize_signals_history`) |
| G.P2.24 | `db-query.yml` workflow concurrency / cancelled runs | **PR #346** (documented as known GitHub-side limitation in CLAUDE.md `## Database access`); not fixable in workflow YAML |

### P3 (Track C own)

| ID | Item | Landed via |
|---|---|---|
| G.P3.1 | `conviction` enum collapses to `medium` 12/12 | **PR #305** (prompt fix — didn't take); **PR #351** (deterministic post-process from `confidence_score` + `analyst_agreement` + `risk_severities`); closes #349 |
| G.P3.2 | `insight_reports.cost_usd` is sum-only — persist per-role | **PR #305** (`per_role_cost JSONB` schema + writer); **PR #338** (`_upsert_report` persist reinforcement) |
| G.P3.3 | `insight_reports_history` not verified — confirm writes | **PR #305** (history-table verify SQL run during PR validation; confirmed populated) |

### Bonus PRs from R2 validation (gaps that weren't in the original audit)

| Issue | PR |
|---|---|
| #313 — `run_kind` always `manual_replay`/`backfill`, never `scheduled` (cron payload mislabel) | **PR #352** (`_schedule_insight` mirrors `_schedule_brief`, injects `INSIGHT_TRIGGERED_BY=cloud-scheduler:<name>`) |
| #349 — Prompt-only conviction fix from PR #305 didn't move distribution | **PR #351** (deterministic post-process replaces LLM) |
| #359 — `_derive_key_levels` gap for gamma walls/flips | **PR #362** (extends function to surface gamma key levels alongside price levels) |

---

## Cross-track items Track C waited on (not Track C's work)

| Blocker | Owning track | Resolved? | Where verified |
|---|---|---|---|
| G.P0.1 — unfreeze `fetch-market-data` daily fetcher | A | ✅ via PR #321 | Daily bars now landing 2026-05-07 onward |
| G.P0.6 — `signal_alerts.conditions_met` JSONB writer fix + backfill | D | ✅ via PR #308 | Per-factor walk-forward script reads native JSONB array |
| G.P0.10 — EOD reconciliation Cloud Run Job | D / A | ✅ shipped | `signal_monitor_eod_resolver.py` running nightly; `exit_return_pct` populated for 713 of 1,753 alerts in 2026-04-01..05-09 (40.7% — open positions won't have outcome until close) |
| G.P0.11 — momentum strategy zero-fires investigation | D | ✅ in progress; momentum starts firing | Walk-forward framework will produce verdicts after ≥ 2 weeks of momentum-fire data |
| G.P1.5 — brief `signal_status` ↔ `ftfc_direction` contradiction | B | ✅ via PR #306 | The divergence UI in PR #353 renders correctly |
| G.P1.10 — `brief_bias` populated only on 5/7 | D (via B) | ✅ via PR #310 + Track D fix; landed ~2026-05-07 | Live-DB audit 2026-05-09: 100% coverage on 5/7 + 5/8 |

---

## Recurring work — now scheduled, not manual

Per the operator's directive ("Anything that you're asking me to do
manually, likely should not be done manually."), all post-merge
recurring asks were converted to GH Actions cron in **PR #366**:

| What | Cron | Path |
|---|---|---|
| `verify-brief-bias` (G.P1.10 verify side) | Sunday 14:00 UTC weekly | `.github/workflows/verify-brief-bias.yml` — exits 0 on coverage clean, opens auto-issue on regression |
| `per-factor-walkforward` (G.P2.1+2+3) | Saturday 13:00 UTC weekly | `.github/workflows/per-factor-walkforward.yml` — uploads markdown report; tolerates `exit 3` (insufficient data) until ~2026-05-23 |

Both workflows reuse the freshness-watchdog credential pattern
(GCP_SA_KEY → ADC + the four CLOUD_SQL_/DB_ secrets) and the standard
`handle-workflow-failure.yml` reusable workflow for issue creation on
failure.

---

## Lessons captured

Three patterns from this audit are now codified in `CLAUDE.md`:

1. **Hermetic-only tests on DB-coupled code** — PR-G #355 shipped with
   16 passing unit tests and a fundamentally broken SQL query
   (`LEFT JOIN trades t ON t.alert_id = a.id` — no such column).
   `_pull_alerts` was never executed against the live DB before merge.
   This is the failure mode CLAUDE.md rule 0.3 already calls out;
   re-emphasized in the PR-#363 retro and the PR-#366 validation
   checklist (workflow_dispatch smoke test post-merge).

2. **Plan-time dates vs evidence-based dates** — the original plan
   defaulted the `verify_brief_bias` cutoff to `2026-05-12` based on
   when the Track C plan *expected* the brief_bias fix to land. The
   actual fix landed ~5 days earlier (2026-05-07). Codex caught this
   on PR-#366 review; fixed in commit `d4c6e5d` to use the
   evidence-based date from the live-DB audit, not the plan's
   prediction.

3. **Always replay against historical data, never wait for the next
   session** — the 2026-05-09 live-DB audit on PR-I #357 confirmed
   `brief_bias` coverage was already at 100% on 5/7 + 5/8 — *before*
   the new cron workflow was scheduled. This is now CLAUDE.md
   rule 3.5 (added in PR #364): every "wait for next live run" prompt
   should first try the historical replay.

---

## What's not closed

Nothing remaining for Track C. The audit's 5 P0 / 4 P1 / 4 P2 / 1 P3
Track-C-tagged items are all addressed (landed, deferred-with-note, or
scheduled-recurring). Cross-track blockers that Track C was waiting on
have all resolved.

The only remaining *future-work* on the Track C surface is data-gated:
- Per-factor KEEP/DEMOTE/DROP verdicts require ≥ 2 weeks of
  post-Phase-0.7.x momentum data. First actionable walk-forward report
  is the 2026-05-23 Saturday cron run (or earlier if momentum fires
  more frequently than expected).
- 2-consecutive-weeks-at-100% criterion for closing the G.P1.10
  verify side — first checkpoint is 2026-05-17 (second Sunday cron).
  If the run on 5/17 is also 100%, G.P1.10 verify side closes for good.

Both will surface as GH Actions runs (and any regression as auto-issues),
not manual asks.
