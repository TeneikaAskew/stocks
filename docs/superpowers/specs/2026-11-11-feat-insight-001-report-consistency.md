---
feat_id: FEAT-INSIGHT-001
req_ids: [REQ-GOV-002, REQ-GOV-004, REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-LLM-001, REQ-PLAYBOOK-001, REQ-UX-001, REQ-FRESH-001, REQ-FRESH-002, REQ-REL-001, REQ-REPLAY-001, REQ-CAP-001, REQ-CAP-002, REQ-OBS-001, REQ-PERF-001]
issues: [1295, 867, 916]
canvases: []
site_source_notes: [INSIGHTS-01, INSIGHTS-03, INSIGHTS-06, INSIGHTS-07, INSIGHTS-08]
done_when:
  - "I1 decision and risk identity: tests/lib/test_report_consistency.py drives the real run_insight_pipeline with an injected LLM factory that records every request, and proves the portfolio-manager proposal is requested before the risk tier; each of the three configured risk reviewers (aggressive, conservative, neutral) receives the exact deterministic persona candidates and their reviewed_plan_id map (rfc8785-sha256-v1 over source version ids, data_cutoff, recipe id and the complete typed candidate) and never the TraderOutput entry, stop or targets; a missing, failed, duplicated or foreign reviewed_plan_id from any one reviewer makes every affected persona plan unavailable with plan_reason risk_review_incomplete and its executable fields cleared; a candidate whose sizing, levels, metrics, source versions or data_cutoff change after review is published unavailable with risk_plan_mismatch; a matched block yields not_applicable and keeps the blocked candidate id as non-executable provenance; the published direction, conviction and plan summary come from DecisionFacts and contradicting recommendation prose is withheld with narrative_inconsistent; and no case makes a model call beyond the existing roster; fails on origin/main, where lib/agents/report_consistency.py does not exist and _risk_payload sends TraderOutput"
  - "I2 plan states: tests/lib/test_trade_planner_pending.py proves every PersonaPlan from compute_persona_plans carries plan_status; the IWM 2026-10-08 fixture (close 277.7, ATR 3.7368433430628203, PYL 171.73 outside the 3 ATR window) is pending_confirmation with plan_reason set from the side's orb_only reason, a typed ConfirmationCondition (opening_range_break, 15 minutes, direction) and entry_zone, stop, targets, position_size_pct and risk_metrics null or empty, while 171.73 appears only in key_levels; a parameter that is not ok is unavailable with its parameter reason; the conservative weak-FTFC (long and short) and long-below-200-SMA stand-asides are not_applicable with every executable field cleared; a missing ftfc_score is never 0.0 (conservative plan unavailable with ftfc_unavailable, ftfc_aligned null, conviction null with conviction_status unavailable); an LLM-only invalidation assertion reaches unavailable with invalidation_evidence_unavailable through the real orchestrator; a hand-built legacy invalidated or not_applicable plan is cleared by finalization and serialization; and a normal ready plan is byte-identical to origin/main's numbers; fails on origin/main, where PersonaPlan has no plan_status and the stand-asides keep entry, stop and targets"
  - "I3 failures, outcome and telemetry: tests/lib/test_report_consistency.py and tests/api/test_insight_report_integrity.py prove a failed trader, portfolio manager, risk reviewer or planner adds its section to failed_sections with a canonical public reason stage:error_class:stable_code built by capture_failure, publishes confidence_score null with confidence_kind unavailable (never 0.0 or 0.3) and never copies an LLM entry, stop or targets into the headline; no executable entry, stop, targets, sizing or risk metric reaches persisted JSON, GET latest, by-id, history or runs, or the Discord embed, for pending_confirmation, invalidated, unavailable or not_applicable; the job, the API fallback writer and scripts/generate_historical_report.py persist status done with completion_status degraded for a usable partial report, and GET /api/insights/runs/{run_id} returns the same failed_section_reasons map; dummy bearer, key, password, DSN, URL query, header and SQL strings injected into exceptions reach no public reason, operator diagnostic, API body, embed or captured log record; existing queued, running, done and failed pollers still terminate; and each of the three writers emits exactly one structured terminal event per run carrying run_id, ticker, generation_kind, claim_epoch, attempt counts, failed-section count, data_cutoff watermark, duration_ms, error_class and terminal status plus completion_status; fails on origin/main, where the trader and manager fallbacks add no failed section and confidence_score is 0.3"
  - "I4 immutable versions and fenced runs: tests/api/test_insight_report_integrity.py, with the real schema applier and isolated PostgreSQL, proves two runs at the same ticker and data_cutoff append two immutable history versions; exact history:<id> lookup, availability and generation-kind filtered history apply before LIMIT; default ticker selection stays live-only despite a later replay or backfill; an explicit generation_kind opts in; a current-cache UUID still resolves by id; dependencies are judged at the version's own data_cutoff; mixed-kind EXPLAIN (ANALYZE, BUFFERS) uses the (ticker, generation_kind, available_at DESC, id DESC) index for the live LIMIT 20 read; claim_run and transition_run fence every write by owner_token, claim_epoch and database now() < lease_expires_at with a fixed 1860 s lease; an active owner is never displaced and a stale owner cannot publish; the generation deadline is task timeout 1800 s minus a 300 s cancellation and final-transaction margin, and a provider wait past it is cancelled and the failed or degraded terminal transaction commits before the task timeout on a fake clock; the immutable version, current pointer and fenced done transition commit in one transaction (an injected terminal failure rolls back all three; a lost commit acknowledgement resumes the same version and hash with zero model calls); the historical normal path adds at most 2 round trips; deleting the run row keeps the copied attempt_run_id, hash and API run_id; and tests/scripts/test_backfill_history_tables_integrity.py proves scripts/backfill_history_tables.py stays idempotent through legacy_backfill_key after uq_irh_ticker_asof_written is replaced; fails on origin/main, where history has no version identity and insight_runs has no lease"
  - "I5 inputs at a cutoff and producer proof: tests/integration/test_insight_report_acceptance.py runs the production writer and an INSIGHT_AS_OF replay against isolated PostgreSQL and proves the replay bundle reads only persisted eligible input snapshots and DATA spec §M versions; options and gamma sections in a replay are unavailable with reason options_as_of_owned_by_feat_option_001 and are never refilled from a date-only query; a same-date market row mutated after the cutoff, a late-ingested news article and a journal entry created or completed after the cutoff never enter the replay or its embed (Discord makes zero fetch_top_news_articles calls); the IWM same-cutoff fixture (data_cutoff 2026-10-08T13:00:00Z, versions available 14:00 and 15:00 UTC) is admitted at 16:00, first-only at 14:30 and empty at 13:00, a 13:30 dependency is rejected for the 13:00 version, and 21 later versions do not hide the first; date-only GET stays end-of-day UTC, date-only generation stays midnight UTC and naive ISO stays UTC; code_commit, image_digest, pipeline_version, effective_config_hash, model and rule versions and input artifact hashes are persisted and returned, and a missing one marks the version unproven; and the test exports tests/fixtures/data_integrity/report_version_contract.json with a manifest (commit, test node ids, artifact SHA-256, RFC 8785 vector digests, producer_integrity_hash per item and for the S9 collection) that a passed run of solyra supabase/functions/insights-research/evidence.test.ts on a reviewed solyra commit verifies; fails on origin/main"
  - "I6 records and local performance: docs/runbooks/insight-report-consistency.md records the fixtures, API compatibility, rollout and rollback, the measured capacity and the post-merge checks; a local benchmark of GET /api/insights/report/{ticker}/history?versions=true&limit=20 through the full route and real PostgreSQL (10 warmups, 100 requests, concurrency 4, at least 10000 mixed-kind rows for the ticker) reports p95 at or under 2 s and every response at or under 180000 bytes, with the cold request, p50, p95, max, errors and environment in the PR body; platform/api/openapi.json is regenerated and passes its check; scripts/maintenance/doc_inventory.py --insert has re-rendered the inventory blocks; the FEAT-INSIGHT-001 catalog record and 12-PR-ISSUE-TRACEABILITY list the implementation PR; the (FEAT-INSIGHT-001, <component>) note rows for INSIGHTS-01, INSIGHTS-03, INSIGHTS-06, INSIGHTS-07 and INSIGHTS-08 carry a source identity produced and verified from the committed head; scripts/maintenance/docs_audit.py on the branch reports nothing main does not; python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: draft
supersedes: null
---

# Report consistency, explicit plan states and immutable report versions

## Status and authority

Draft. This spec is not approved and claims no approval, review or evidence it did not produce. It
is a re-cut, written by a FEAT-INSIGHT-001 delivery lane from current main (e1a17c2c), of stocks#1425
(`docs/superpowers/specs/2026-10-12-feat-insight-001-report-consistency.md`, never merged), which
itself replaced #1412. It takes effect only if the owner approves it. Its predecessors cited an owner
direction of 2026-10-12 and an outside planning page; this text relies on neither and adds no scope
beyond what #1425 covered.

## What changed from #1425

- **The DATA contract is now a real file.** #1425 consumed `2026-10-12-feat-data-001-data-integrity.md`
  §M, which never reached main (Codex P1 on #1425 round 2). This spec consumes §M "Consumed temporal
  contract (stable)" of `docs/superpowers/specs/2026-11-11-feat-data-001-data-integrity.md`, the draft
  in stocks#1828 (head 44699ad9). That file is not on main. **This spec depends on #1828's DATA spec
  being approved and merged first**, and its implementation on DATA Part 1 (§A, §B, §M) being on main.
  Nothing here requires what §M excludes (see §G).
- **Staging monitoring is a close-out step.** #1425's I6 put Cloud Run request-log and Monitoring
  checks of the `versions=true` route in `done_when`, which cannot be met before merge because staging
  deploys from `main` (Codex P1). The local route benchmark stays in I6; the staging check is in
  Close-out.
- **Deployed-UI evidence is a merge prerequisite, not a box.** #1425's I7 asked the PR to tick owner
  staging evidence of the tolerant solyra consumer. AGENTS.md "Browser proof" makes deployed-site runs
  the owner's close-out, never boxes the PR ticks. It is now a named merge prerequisite (§K).
- **Main moved under the planner.** FEAT-STRAT-001 one-level-source and the approved
  `2026-11-07-feat-insight-001-trigger-distance-cap.md` (merged in #1746) mean the planner no longer
  walks to a distant level or synthesizes one: on the IWM fixture it already returns an `orb_only`
  plan with null entry and stop. What remains is the explicit `plan_status`, the cleared stand-asides,
  the typed confirmation condition and everything downstream (§B).
- **Round-2 P2 findings are folded in:** the reordered tiers are documented (§C, Close-out), #867 and
  #916 are listed, the generation deadline is derived from the task timeout with a margin (§E), one
  structured terminal event per run (§D), a typed trigger and confirmation in `pending_plan` (§B), and
  a nullable conviction in `finalize_decision` (§A).
- **The bundle has eight sections now** (`session_levels` was added), so the pre-model capture holds
  nine snapshots with reflection, not eight.
- **The scheduling-inventory prerequisite is met.** The 2026-10-12 scheduling pass and its #867/#916
  delta are on main in `docs/product/12-PR-ISSUE-TRACEABILITY.md`; nothing waits on it.

## Dependencies and merge order

1. stocks#1828's DATA spec approved and merged, then its Part 1 implementation
   (`feature/feat-data-001-source-receipts`: §A, §B, §M, D11) on main. This spec's implementation
   imports `select_evidence_version`, `select_schedule_as_of`, `EvidenceVersion`, `EvidenceUnavailable`,
   the M4 `temporal_proof` shape and the M5 hash from that code, and the RFC 8785 implementation and
   vectors it lands.
2. The companion FEAT-DEPLOY-001 change in #1828 (`deploy_insight_pipeline` at `--max-retries 0` on
   create and update, task timeout clamped to at most 1800 s) on main and deployed, before fenced
   generation is activated (§E).
3. This spec approved, then one implementation PR from main, opened only after 1 is on main. No
   stacked PRs.

If #1828's spec changes §M before approval, this spec is revised to match before it is approved. If
§M is dropped, this spec cannot be approved as written.

## Issue map

| Issue | State on 2026-11-11 | This spec |
|---|---|---|
| #1295 trader or manager failure publishes fallback fields with no failed section | open | closes on merge and the owner's post-merge check: §A, §B, §D |
| #867 risk reviewers evaluate a different plan than the published one | open | closes on merge and the frozen-fixture evidence the issue asks for: §C |
| #916 ablate the agent graph and prohibit unsupported numeric recommendations | open | partial: only numeric fields from supplied structured inputs (§A, §C); the blinded ablation trials stay open |
| #1217 point-in-time replay leaks post-cutoff data | open | context only: §G and §H stop the report's own replay from reading later data; #1217's other replay paths are not claimed |

The inventory rows for #1295 (2026-10-12 scheduling pass) and #867 and #916 (the 2026-10-12 report
delta) are on main in `docs/product/12-PR-ISSUE-TRACEABILITY.md`. That delta's line "Keep existing
Risk→PM topology" described an earlier draft; this spec moves the portfolio-manager proposal ahead of
the risk tier (§C), which the round-2 review of #1425 accepted and asked to be documented.

## Problem (verified on main e1a17c2c)

1. **Fallbacks publish invented values with no failed section** (#1295). The trader fallback
   (`lib/agents/orchestrator.py:417-428`) is a flat plan with entry 0.0 to 0.0, stop 0.0 and confidence
   0.0. The portfolio-manager fallback (`:467-482`) copies the trader's entry, stop and targets and sets
   `confidence_score=0.3`. Neither adds a failed section. When the planner fails, the headline takes the
   LLM's entry, stop and targets (`:641-643`). A failed risk reviewer is logged and dropped (`:449`),
   so two reviews pass as a full review.
2. **Missing FTFC reads as 0.0.** `orchestrator.py:554` and `trade_planner.py:641` both use
   `float(... or 0.0)`, so an unknown FTFC fails the conservative gate and feeds calibration as
   "unaligned".
3. **Risk reviews a different plan** (#867). `_risk_payload(bundle, trader)` (`:226`, called at `:430`)
   sends the LLM `TraderOutput`; deterministic `PersonaPlan`s are built afterwards (`:594`). A block can
   refer to plan A while the user gets plan B.
4. **Calibration follows the narrative.** The portfolio manager writes direction, thesis and conviction
   (`:453-466`); `_calibrate_conviction` then replaces conviction (`:556`) after the thesis is written,
   so a strong thesis can ship under a low final conviction. `_validate_thesis_consistency` (`:704`)
   only warns.
5. **No explicit plan state.** `PersonaPlan` (`lib/agents/schema.py:214`) has `regime` but no status.
   An `orb_only` plan has null entry and stop (`trade_planner.py:404`), a parameter that is not ok has
   null fields (`:452`), but the conservative weak-FTFC and long-below-200-SMA stand-asides keep their
   entry, stop and targets with size 0 (`:306-311`). A consumer cannot tell "waiting for the opening
   range" from "computation failed" from "this persona stands aside".
6. **Failure reasons carry raw exception text.** `failed_reasons[section] = f"analyst-llm: {type}: {exc}"`
   (`:346`) and the planner's (`:607`) persist `str(exc)`, which can hold URLs, keys or SQL.
7. **History is not an immutable version store.** `insight_reports_history` (`gcp/schema.sql:2252`) is
   unique on `(ticker, as_of, written_at)`, has no attempt identity, no availability clock, no data
   cutoff and no provenance. The job appends history and upserts the current row in separate
   transactions (`gcp/insight_pipeline_job.py:532-533`); the API fallback (`platform/api/routers/insights.py:411`)
   and `scripts/generate_historical_report.py:55` write only the mutable current row. `insight_runs`
   (`gcp/schema.sql:1590`) is claimed by a status compare-and-swap with no owner or lease
   (`insight_pipeline_job.py:246-254`), while `gcp/deploy.sh:615-618` creates the job with
   `--max-retries 1`.
8. **Replay reads later data.** An `INSIGHT_AS_OF` run rebuilds the bundle from mutable tables with
   date-only filters. `retrieve_similar_journal` (`lib/agents/summarizers.py:1969`) filters only ticker
   and ownership and returns outcome-derived `return_pct`. The Discord embed re-queries news at push
   time (`gcp/insight_discord_push.py:504`), so a late-ingested article can appear in a frozen report.
9. **No version history API.** `GET /api/insights/report/{ticker}/history` (`insights.py:793`) lists
   current-cache rows of every `run_kind`; there is no way to read the report that was available at a
   cutoff.

## Non-goals

- No calibration threshold, persona threshold, sizing rule, level window or new entry strategy. The
  FTFC rule of `2026-11-05-feat-insight-001-ftfc-consumer-gates.md` and the window of
  `2026-11-07-feat-insight-001-trigger-distance-cap.md` are unchanged.
- No new model call, role or retry tier; no change to the model roster or prompts beyond marking
  draft interpretation versus authoritative facts.
- No ORB monitoring service. `pending_confirmation` never upgrades itself because time passed.
- No rewrite of stored historical reports; legacy rows stay as they are and read as `unknown`.
- No options or gamma as-of visibility (FEAT-OPTION-001, #1490 `revision_visible`), no ETF fields (none
  in the insight bundle; DATA §M defers them), no catalyst ingestion or earnings revision reader
  (FEAT-CATALYST-001), no receipt or freshness primitive (FEAT-DATA-001).
- No `gcp/deploy.sh` change (FEAT-DEPLOY-001 companion in #1828).
- No blinded ablation of the agent graph (#916's main ask).
- No REQ-LLM-002 roster test; it is still PROPOSED in `docs/product/08-AI-AGENT-ARCHITECTURE.md`.

## Approaches considered

1. Prompt-only warnings. Rejected: calibration after the narrative still changes the published
   decision.
2. Retune thresholds or replace the planner. Rejected: the defect is how known deterministic output is
   represented, not the output.
3. Chosen: settle deterministic facts before publication, constrain the narrative to them, review the
   exact deterministic candidates, represent non-ready plans explicitly, and persist each report as an
   immutable, provenance-carrying version read at a cutoff.

## Design

### A. Final decision contract

New `lib/agents/report_consistency.py`:

- `DecisionFacts` (frozen): final `direction`, `calibrated_conviction: Conviction | None`,
  `conviction_status` (`calibrated|unavailable`), `confidence_score: float | None`, `confidence_kind`
  (`model_score|unavailable`), the headline plan state, persona plans, source version references,
  `failed_sections` and `failed_section_reasons`.
- `finalize_decision(*, direction: str, conviction: str | None, confidence_score: float | None,
  plans: list[PersonaPlan], failed_sections: list[str], failed_section_reasons: dict[str, str],
  source_status: list[dict]) -> DecisionFacts` composes the facts without inventing a value. A `None`
  conviction (missing calibration input) stays `None` with `conviction_status=unavailable`.
- `_calibrate_conviction` keeps its rules and thresholds. Its FTFC input comes from the strat section
  without `or 0.0`; missing FTFC (or any other missing calibration input) makes the result `None`.
- `lib/agents/schema.py`: `InsightReport.conviction` and `confidence_score` become nullable;
  `conviction_status`, `confidence_kind`, `decision_provenance` and the plan fields of §B are added.
  Legacy complete reports keep their values; a report without the new fields reads as
  `plan_status=unknown` in presentation metadata, never inferred ready.
- For every non-ready plan, finalization sets `entry_zone=null`, `stop=null`, `targets=[]`,
  `position_size_pct=null` and `risk_metrics=null` at persona and headline level, before persistence,
  and the API and Discord serializers apply the same clearing again. Only `ready` carries executable
  numbers. `key_levels` and a labelled `candidate_trigger` may remain as non-executable context.
- No field promises a calibrated probability. `confidence_score` is the portfolio manager's model
  score when valid, labelled `model_score`; otherwise null.

### B. Plan states

`PersonaPlan` gains `plan_status` (`ready|pending_confirmation|invalidated|unavailable|not_applicable`),
`plan_reason` (closed vocabulary), `confirmation: ConfirmationCondition | None` and
`candidate_trigger: TriggerRef | None`, and `position_size_pct` becomes nullable.

- `TriggerRef`: `price`, `level_name`, `source_version_id`, `observed_at`.
- `ConfirmationCondition`: `kind` (`opening_range_break`), `timeframe_minutes` (15), `direction`, and
  the side's machine reason. Display prose lives in a separate non-authoritative field.
- `pending_plan(*, persona: str, regime: str, reason: str, candidate_trigger: TriggerRef | None,
  confirmation: ConfirmationCondition) -> PersonaPlan` never manufactures prices or zero financial
  fields.

`lib/agents/trade_planner.py`:

- `_orb_only_plan` (`:404`) returns `pending_confirmation` with `plan_reason` from
  `ctx.orb_only_reason(direction)` and an `opening_range_break` condition. On current paths there is
  no trigger, so `candidate_trigger` is null; distant levels stay in `key_levels` only.
- `_params_unavailable_plan` (`:452`) returns `unavailable` with the parameter's reason.
- `_plan` returns `not_applicable` for the conservative weak-FTFC and long-below-200-SMA stand-asides,
  with every executable field cleared and the existing "Stand aside" rationale kept. Thresholds are
  unchanged.
- `context_from_bundle` (`:641`) keeps `ftfc_score=None` when the strat section has none; the
  conservative FTFC gate then returns `unavailable` with `ftfc_unavailable`, and
  `compute_risk_metrics` leaves `ftfc_aligned` null. Other personas are unaffected.
- A normal plan is `ready` with its numbers unchanged.
- `invalidated` is reserved compatibility input. No production rule observes an invalidation today,
  so the planner never emits it; an LLM-only claim that invalidation occurred reaches `unavailable`
  with `invalidation_evidence_unavailable`. Conditional invalidation prose is not such a claim.
- Missing price, ATR or session levels and compute failures are `unavailable`.

### C. Narrative and the risk identity barrier

Tier order in `run_insight_pipeline` becomes: analysts, bull and bear, judge, trader (interpretation
only), **portfolio-manager proposal**, deterministic persona candidates, risk tier, finalization.
The PM's direction and conviction are draft inputs; the PM no longer reads risk reviews of
`TraderOutput`.

- Candidates are built with the existing planner from the PM draft direction and conviction.
  Each of the existing three reviewer calls (aggressive, conservative, neutral) receives the candidate
  set keyed by persona and `reviewed_plan_ids`, a map persona to
  `sha256_rfc8785({source_version_ids, data_cutoff, recipe_id, candidate})`. The candidate is the
  complete typed `PersonaPlan` minus enumerated display prose (rationale text and confidence display);
  `plan_status`, `plan_reason`, `confirmation`, `candidate_trigger`, levels, sizing and metrics are all
  hashed. A typed field added later must update the hash-vector test.
- Each response must bind its findings to the exact ids the transport sent. All three reviewers must
  return valid matching ids. A missing, failed, duplicated or foreign id marks the reviewer's section
  failed and makes every affected plan `unavailable` with `risk_review_incomplete`. Two reviews are not
  a quorum. Invalid identities cannot influence calibration or blocking. No retry or extra call.
- After matched reviews, calibration runs with its existing rules. If the final candidate differs from
  the reviewed one (sizing, levels, metrics, source versions or cutoff), it is published `unavailable`
  with `risk_plan_mismatch`. A matched block yields `not_applicable` and keeps the blocked candidate id
  as non-executable provenance.
- `reconcile_narrative(draft: NarrativeDraft, facts: DecisionFacts) -> NarrativeResult` checks the
  structured direction, conviction and plan claims against `DecisionFacts` and the sourced numbers.
  Bull and bear cases stay as conditional scenarios. The short decision summary is built
  deterministically from the facts. Contradicting or unverified recommendation prose is withheld with
  `narrative_inconsistent`; no regex rewriting of numbers. The draft is kept as diagnostic
  interpretation only.
- `lib/agents/prompts.py` marks which inputs are authoritative facts and which are draft
  interpretation.
- The module docstring of `orchestrator.py` (`:4-31`) is corrected to the new order in the same PR.
  `docs/product/08-AI-AGENT-ARCHITECTURE.md` (tier table, graph and node contract) cannot be edited from
  a feature branch, so it is updated on a `docs/` branch right after the merge (Close-out).

### D. Failure reasons, completion outcome and telemetry

- `capture_failure(stage: FailureStage, exc: Exception, *, code: FailureCode) -> FailureRecord`.
  `public_reason` is at most 128 characters, `stage:error_class:stable_code`, built only from
  allowlists: stages are the configured role and section ids; `error_class` is one of timeout,
  transport, schema, dependency, planner, persistence, cancellation, internal (unknown maps to
  internal); codes include role_timeout, provider_unavailable, schema_invalid, source_unavailable,
  planner_failed, persistence_failed, generation_deadline, risk_review_incomplete, risk_plan_mismatch
  and internal_error. The public map is built once at capture and round-trips unchanged through
  `DecisionFacts`, persisted JSON, the API and Discord.
- An optional `operator_diagnostic` (at most 1024 bytes) carries only allowlisted context (stage, code,
  run and section id). Authorization, cookie, key, token, password and secret values, credential-bearing
  URLs, DSNs, SQL parameters, headers, bodies and stack traces are discarded, never pattern-scrubbed.
  On these handled paths no raw `str(exc)`, `repr(exc)` or `logger.exception` chain reaches a log.
- `insight_runs.status` keeps `queued|running|done|failed`. New nullable `completion_status`
  (`complete|degraded`), `report_version_id` and `failed_section_reasons` are written with the
  terminal transition. A usable partial report is `done` plus `degraded`; `failed` means no usable
  version committed. Legacy rows stay unknown. `GET /api/insights/runs/{run_id}` returns the new
  fields; existing pollers that stop on done or failed are unchanged.
- One structured terminal log event per run from each of the three writers (REQ-OBS-001):
  `event=insight_run_terminal`, `run_id`, `ticker`, `generation_kind`, `operation_kind`, `claim_epoch`
  (the retry signal), counts (model calls attempted and failed, failed sections, snapshots captured),
  `data_cutoff` (watermark), `duration_ms`, `error_class` (or null), `status` and `completion_status`.
  No token, prompt or payload is logged.
- Writers: `gcp/insight_pipeline_job.py`, `platform/api/routers/insights.py` (`_execute_pipeline`) and
  `scripts/generate_historical_report.py::_generate_one`.

### E. Immutable versions, leases and recovery

Schema in `gcp/schema.sql`, applied by `gcp/apply_schema.py` before readers:

- `insight_reports_history` gains `attempt_run_id UUID` (copied, not a foreign key), `generation_kind`
  (`live|replay|backfill`), `operation_kind` (the existing operational kind), `data_cutoff`,
  `generated_at`, `available_at`, `payload_hash`, `temporal_proof JSONB` (DATA M4), `provenance JSONB`
  (`code_commit`, `image_digest`, `pipeline_version`, `effective_config_hash`, a redacted resolved
  config artifact, model and rule versions, input artifact ids and hashes), `completion_status`,
  `failed_section_reasons` and nullable `legacy_backfill_key`. `uq_irh_ticker_asof_written` is replaced
  by a unique `(attempt_run_id, ticker, as_of)` for new rows and a partial unique index on
  `legacy_backfill_key`; the index `(ticker, generation_kind, available_at DESC, id DESC) WHERE
  available_at IS NOT NULL` serves the selectors. Existing rows are preserved; legacy provenance is
  null and unproven.
- `insight_runs` gains `owner_token`, `claim_epoch BIGINT` and `lease_expires_at TIMESTAMPTZ`.
- New `lib/agents/report_versions.py` with `claim_run(run_id, owner_token) -> RunLease | None`,
  `transition_run(run_id, *, lease, status, outcome, version_id, public_reasons) -> bool` and
  `persist_report_version(report, *, run_id, lease, generation_kind, operation_kind, generated_at,
  source_versions) -> ReportVersion`, used by all three writers. The historical script creates its own
  run row with `generation_kind=backfill` and stops writing the current row directly.
- **Lease.** Claim is one compare-and-set on database time: a queued attempt, or a failed or running
  attempt whose lease has expired, gets a new owner, `claim_epoch + 1` and `lease_expires_at = now() +
  1860 s`. An unexpired lease is never taken, whatever the status. Every section, version, pointer and
  terminal write matches `run_id`, `owner_token`, `claim_epoch` and `now() < lease_expires_at` under a
  row lock in the same short transaction, with no external I/O inside it and statement and lock
  timeouts bounded by the remaining lease.
- **Deadline with margin.** The job's Cloud Run task timeout is 1800 s (create path today; the DEPLOY
  companion clamps update to at most 1800 s). The generation deadline is `task_timeout - 300 s` =
  1500 s, covering provider waits and cancellation; the 300 s margin covers cancellation (at most 60
  s), the final transaction (statement timeout 30 s) and slack. The constant is
  `INSIGHT_TASK_TIMEOUT_SECONDS = 1800` in code, and the activation check in §K records that the live
  job's effective timeout equals it; if it is lower, fenced generation is not activated. Past the
  deadline, generation is cancelled, late output is rejected and the terminal transaction records
  `failed` or `degraded` from what is already committed. No timeout increase, no heartbeat.
- **Three persistence phases on a normal run**: (1) claim plus a lookup of a committed version under
  `(run_id, ticker, as_of)`; (2) one batched pre-model snapshot write (§G, §H); (3) one transaction that
  appends the immutable version, updates the current pointer where allowed and applies the fenced
  `done` transition with its outcome. The historical path today has one write, so it gains at most two
  round trips; the job's four writes become three.
- **Recovery.** If phase 1 finds a committed version, it verifies the hash, restores the pointer and
  finalizes the run from the stored outcome without calling a model. A terminal failure inside phase 3
  rolls back the version, pointer and transition together. A lost acknowledgement after commit
  resumes the same version and hash with zero model calls. A task killed before phase 3 leaves its
  lease to expire (at most 31 minutes); a new owner then regenerates because no version exists. A
  legacy committed-version-with-running-status row is repaired at claim after expiry.
- `scripts/backfill_history_tables.py::backfill_insight_reports` (`:190`) moves from
  `ON CONFLICT (ticker, as_of, written_at)` to `legacy_backfill_key`, a digest of the source UUID,
  canonical `as_of` and payload hash; an unchanged rerun inserts nothing, changed content appends, and
  ambiguous existing copies are reported, not duplicated. The premarket backfill is untouched.

### F. Cutoffs and selectors (API)

- `normalize_report_cutoff(value, *, purpose: Literal["lookup", "generation"]) -> datetime` keeps both
  current behaviours: a date-only lookup cutoff is 23:59:59.999999 UTC
  (`_fetch_latest_report`, `insights.py:217-218`); a date-only generation cutoff is 00:00 UTC
  (`orchestrator._as_datetime`, `:1206`). Naive ISO is UTC; aware values convert to UTC. The existing
  future-date checks run first. Weekends and holidays are not shifted.
- `GET /api/insights/report/{ticker}` without selectors keeps the current-cache behaviour. With
  `as_of`, `select_report_version(ticker, *, cutoff, version_id=None, generation_kind="live")` reads
  history requiring `available_at <= cutoff`, a known `data_cutoff <= cutoff`, and every dependency
  eligible at the version's own `data_cutoff`. Default is live only, applied before ordering and
  LIMIT; `generation_kind=replay|backfill` is explicit and the response names it.
- `GET /api/insights/report/{ticker}/history?versions=true&as_of=...&limit=20` uses
  `list_report_versions(...)` with the same predicates applied in SQL before LIMIT, ordered
  `available_at DESC, id DESC`. Each item: `id=history:<id>`, `current_report_id` (or null), `run_id`
  (from `attempt_run_id`), the three clocks, `generation_kind`, `operation_kind`, `temporal_proof` and a
  bounded decision projection. Without `versions=true` the legacy response is unchanged.
- `GET /api/insights/reports/{report_id}` keeps current UUIDs (any disclosed run kind, as today) and
  adds `history:<positive integer>`; malformed is 400, absent 404, and a kind or cutoff mismatch is no
  eligible result. The envelope carries `record_kind` (`history_version|current_cache`).
- `platform/api/schemas.py` and `platform/api/openapi.json` carry the additive fields.

### G. Inputs at a cutoff (consumes DATA §M)

The pre-model capture `capture_bundle_versions(bundle, *, run_id, lease, captured_at) ->
list[InputSnapshotRef]` (new `lib/agents/evidence_snapshots.py`) writes one immutable row per section
to a new `insight_input_snapshots` table (a trigger refuses UPDATE and DELETE): `snapshot_id`,
`run_id`, `ticker`, `section`, `payload JSONB`, `payload_sha256`, the M1 clocks, `data_cutoff`,
`captured_at`, `replay_eligible`. Every report version references its snapshots.

`select_replay_bundle(ticker, *, cutoff) -> dict` builds an `INSIGHT_AS_OF` bundle:

| Section | Replay source |
|---|---|
| market, strat, session_levels, backtest, sentiment | latest `insight_input_snapshots` row with `replay_eligible`, `captured_at <= cutoff` and `data_cutoff <= cutoff`; none means unavailable |
| catalysts | DATA M3 `select_evidence_version` and `select_schedule_as_of` at the cutoff; any dataset that returns `EvidenceUnavailable` is listed in `excluded_sections` with its reason, and the section is unavailable when nothing is eligible |
| options, gamma | unavailable with `options_as_of_owned_by_feat_option_001`, the reason §M3 returns; live snapshots of them are provenance only (`replay_eligible=false`) |

No replay section is refilled from a date-only query. The existing exclusion of signal history from
the bundle stays. A replay may still yield a degraded report with unavailable sections and an
unavailable plan; nothing is invented to make it actionable.

`gcp/insight_discord_push.py::format_report_embed` renders headlines from the report version's
sentiment snapshot, or omits them as unavailable; it no longer calls `fetch_top_news_articles`
(`:504`).

### H. Reflection snapshot

The `retrieve_similar_journal` result (at most 5 system-owned rows, `user_email IS NULL`) becomes the
ninth snapshot in the same batch, before any model call, with each row's creation and outcome-completion
clocks. In replay the pipeline does not query `journal_entries` or embed: it reads a reflection
snapshot whose rows are eligible at the cutoff, drops any row whose outcome was learned later, and
marks reflection unavailable when no proof exists. All nine snapshots share a 100 KB aggregate and one
capture round trip; overflow is unavailable.

### I. Producer integrity and S9

This is the producer half of the approved solyra spec `2026-10-12-feat-insight-001-research-evidence.md`
(§F, §G, "S9 collection integrity").

- New persisted JSON hashes and `producer_integrity_hash` use DATA M5: lowercase SHA-256 of RFC 8785
  over exactly `{contract_version, version_id, payload, temporal_metadata}`, tag `rfc8785-sha256-v1`,
  `temporal_metadata` holding the thirteen M5 fields. Legacy hashes keep a legacy label.
- Each history item hashes its returned bounded projection; the producer verifies the stored
  `payload_hash` and lists it as a dependency.
- The `versions=true` response also carries the S9 collection input
  `{contract_version: "report-history-list-v1", version_id: null, payload: {selection, items},
  temporal_metadata}` and its digest outside the input. `selection` is ticker, requested_cutoff,
  generation_kind, limit and order (`available_at_desc,id_desc`). Collection clocks are null; every item
  carries its own. Empty lists still have a digest.
- I5's acceptance test exports `tests/fixtures/data_integrity/report_version_contract.json` and its
  manifest, the path the solyra spec names.

### J. Interactive history performance

REQ-PERF-001 asks for a p95 target and monitoring per endpoint; `docs/product/15-OPEN-DECISIONS.md`
still lists numeric latency objectives as TBD. This spec sets a scoped target for
`GET /api/insights/report/{ticker}/history?versions=true&limit=20`: p95 at or under 2 s end to end
(auth, SQL, proof and hash checks, serialization) and at most 180000 bytes, with no per-item fetch. It
is not an existing SLA. The local benchmark is I6. Monitoring on staging is Close-out, because staging
deploys from main; until it is recorded, the route is `performance_unverified` and no availability
claim is made.

### K. Frontend compatibility and release order

Nullable conviction, confidence, entry, stop, targets and size break renderers that dereference them.
The solyra consumers (`src/components/insights/ReportCards.tsx`, `src/routes/InsightsPage.tsx`,
`src/routes/AiInsightsLovablePage.tsx`, `src/types/insights.ts`) must render pending, unavailable,
invalidated, not_applicable, null-confidence, null-conviction and legacy complete reports (null
confidence shows unavailable, never 0%). That is solyra work under its approved specs, not this spec.

**Merge prerequisites** (posted by the owner on the implementation PR, not `done_when` boxes):

1. The tolerant solyra commit is deployed and the owner has posted the staging check of
   `/insights` and `/ai-insights-lovable` for each state above, with the Playwright screenshots
   described state by state and the `playwright-report` run named, as AGENTS.md "Browser proof" says.
   Because stocks deploys from main, the nullable backend does not merge before this.
2. The DEPLOY companion is on main and deployed, and `gcloud run jobs describe insight-pipeline` shows
   `maxRetries 0` and a task timeout of 1800 s. Without it, fenced generation is not activated.

Rolling the backend back to complete-only shapes is safe for the tolerant UI; the UI is not rolled
back while nullable responses are live.

## Capacity and cost (Rule 0)

Re-measured in the implementation PR; a value above a quarter of its timeout changes the design, not
the timeout.

| | Volume | Velocity | Wall clock and cost |
|---|---|---|---|
| Per ticker run | at most 100 KB of snapshots plus at most 100 KB report and projection, so at most 200 KB persisted | no added model call; three persistence phases (job: four writes become three; historical: one becomes three) | at most 2 added round trips x 2 s + 0.1 s validation = 4.1 s per ticker |
| Daily batch (3 tickers, fan-out) | at most 600 KB | as above | 12.3 s added; with the reviewed 2026-10 run of about 161 s, about 173 s against a quarter of 1800 s (450 s) |
| Cost | | | 12.3 s x (2 vCPU x $0.000024 + 8 GiB x $0.0000025) = $0.0008364 per run, $0.025092 per 30 runs at the deployed 2 vCPU and 8 GiB |
| History read | at most 20 items, at most 180000 bytes | one indexed SELECT, no per-item fetch | p95 target 2 s (§J) |

Storage: about 200 KB per ticker per run, 3 tickers per weekday, about 13 MB per month in Cloud SQL,
within the always-on instance.

## Risks

- **More unavailable plans.** If calibration changes conviction after review, sizing changes and the
  plan is `unavailable` with `risk_plan_mismatch`. I1 measures it on the frozen fixtures and the PR body
  reports the share; if it is high, the owner decides before merge.
- **Replays degrade.** Dates with no captured snapshots replay with unavailable sections; options and
  gamma are unavailable in every replay until FEAT-OPTION-001 supplies as-of visibility.
- **Nullable fields break old renderers**: blocked by merge prerequisite 1.
- **Lease timing.** A killed task blocks its run for up to 31 minutes; retries 0 and the deadline
  margin (I4) bound it.
- **DATA §M may change before approval**: this spec is revised to match before approval.

## Delivery

One implementation PR, `feature/feat-insight-001-report-consistency`, with one ready plan, opened from
main after the dependencies above. If the plan exceeds about 15 tasks, the owner may split it into
(a) §A to §D and (b) §E to §J under a superseding spec; this spec does not pre-split.

## Close-out

Not `done_when` items; tracked in the implementation PR and plan:

- After staging deploys the merge: the owner records, from Cloud Run request logs and Cloud Monitoring,
  the `versions=true` route's sample count, window, p95, errors and payload size (separate from the
  default history route; add an allowlisted route tag only if logs cannot separate it), with the query
  definition and the recovery instruction. Until then the route stays `performance_unverified`.
- A `docs/` PR updates `docs/product/08-AI-AGENT-ARCHITECTURE.md` (tier table, graph, node contract and
  the #867 note) and the insight tables in `docs/product/infrastructure/05-b-ERD.md` and
  `05-h-DATA_DICTIONARY.md` (lease, identity, index and the replaced unique constraint) to the merged
  code.
- #867's frozen-fixture evidence and the historical-artifact disposition are posted on the issue.
- The `(FEAT-INSIGHT-001, <component>)` notes are re-verified from a fresh clone after the squash, as
  the product-delivery skill requires.
- The plan's `status: done` is set on a `docs/` branch after the merge.

## Open questions for the owner

1. Calibration after review can make `risk_plan_mismatch` common (Risks). Accept that, or should the
   identity exclude sizing so only levels and status are bound (a change from #1425's contract)?
2. One implementation PR, or split §A to §D from §E to §J now?
