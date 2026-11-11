---
feat_id: FEAT-PLAYBOOK-001
req_ids: [REQ-PLAYBOOK-001, REQ-REL-001, REQ-REPLAY-001, REQ-GOV-001]
issues: [1168]
canvases: []
site_source_notes: [PLAYBOOK-09]
done_when:
  - "tests/gcp/test_premarket_brief.py::test_retired_sources_excluded_by_real_brief_sql executes the actual load_earnings_for_brief query against fixtures containing both earnings_whispers and EarningsWhispers, before grouping, using the landed earnings_not_retired_sql('ec') helper. Daily, weekly, BRIEF_AS_OF and include-unconfirmed cases exclude EW-only rows; mixed-source results equal the identical fixture with EW removed. NULL, unknown, Earnings_Whispers, alphavantage, unusual_whales and yahoo controls survive the source predicate (normal eligibility still applies). Removing only the predicate admits both retired aliases in the SQL result. Mocks must not prefilter the fixture."
  - "tests/gcp/test_premarket_brief.py::test_retired_sources_excluded_by_real_prior_amc_sql executes the actual load_yesterday_amc_reactions query with hydrated EW rows that pass its volume filter; EW cannot set expected_move or options_volume. The no-predicate control yields EW maxima 9 and 30000 instead of retained UW 5 and 20000. MAX(ec.strategy) and its read are absent; the output strategy key is empty. Non-EW EPS, gap, liquidity, top-N ordering and one conditional-lean call per kept row match the EW-removed baseline."
  - "tests/gcp/test_premarket_brief.py::test_non_ew_brief_contract_after_retirement covers real daily and weekly loaders: non-EW tiers 2, 4 and 6 retain their numbers, source/date confirmation, daily liquidity rules, Track A/B, Q1 low-conviction routing, history-derived playability and ordering match the fixture with EW removed. No EW-only strategy/strike/premium/score columns are selected or read; those four output keys remain '', None, None, None. Direct-caller inspection finds no surviving dependency on their EW values. EW-specific tiers and priority branches disappear; ranking tests use genuinely distinct surviving tiers rather than alphabetical ties."
  - "tests/gcp/test_premarket_brief.py::test_brief_pipeline_never_acquires_ew_recap drives generate_premarket_brief and its actual earnings embed caller with supported mocked I/O on weekday, Sunday and BRIEF_AS_OF paths. No EW recap query, evaluator calendar import, source acquisition, socket, subprocess, database connection or webhook send occurs. Removed load_ew_recap and _ew_recap_or_unavailable definitions and their wiring are absent, and neither scoring_session nor nyse_sessions is imported from the EW evaluator. Existing non-EW boundaries are stubbed, not the pipeline or embed under test. This fails on the prior path that requests a weekday recap; structural import/definition checks complement runtime assertions."
  - "tests/gcp/test_premarket_brief.py::test_legacy_ew_payload_cannot_render and ::test_non_ew_embed_golden_after_retirement exercise the actual embed with legacy strategy, verdict, recap, NaN recap metrics and unavailable payloads: no Whispers section, EW verdict, recap or EW warning renders. Non-EW BMO/AMC, prior-AMC, watchlist, low-conviction, economic and empty-state golden content is unchanged. A supported-source busy fixture stays within the existing 4090-character bound without EW occupying truncation priority. _valid_num and unrelated helpers remain unchanged. The legacy cases fail on the pre-retirement renderer; pure non-EW controls pass on both."
  - "The exact base/head collected-node reconciliation follows docs/review-evidence/ew-first/test-node-inventory.md, refreshed against the actual implementation base. Every unchanged non-EW test remains unchanged; each intentionally retired EW assertion has its named replacement and preserved independent non-EW obligation. The three caller-test/helper files only lose obsolete recap stubs: tests/gcp/test_strat_snapshot_parity.py, tests/api/test_brief_level_break_response.py and tests/lib/strat_2026_11_06.py. Preserve all collected caller nodes, fixture setup, assertions and parametrization; execute the actual affected shared-level caller suites. All brief, affected caller, shared-calendar/vendor and model-pointer tests pass without skip/xfail or unrelated deletion. Finite-value coverage and all 13 accepted successor obligations remain required under the separately admitted sequencing amendment; filtering an invalid EW input is never numeric-validation evidence."
  - "Source/test changes are confined to gcp/premarket_brief.py, tests/gcp/test_premarket_brief.py, tests/gcp/test_strat_snapshot_parity.py, tests/api/test_brief_level_break_response.py and tests/lib/strat_2026_11_06.py; the latter three permit only removal of their obsolete _ew_recap_or_unavailable stubs. lib/earnings_reactions.py, gcp/fetchers/evaluate_ew_strikes.py, lib/eastern_time.py, schema, deployment scripts and schedules remain unchanged. No historical rows, verdict columns or secrets are removed. Own ready plan, FEAT-PLAYBOOK-001 catalog/traceability and relevant MODEL-BRIEF-001 references are updated; MODEL-EWV-001 changes only its brief-consumer/recap claims and their tests/pointers, preserving evaluator and audit history. That cross-model documentation scope requires explicit owner admission before implementation."
  - "The committed implementation head passes existing bounded source/SITE produce and verify with the approved merge-base spec binding and unchanged fixed ceilings, using only the FEAT-PLAYBOOK-001 / PLAYBOOK-09 implementation-source note and its sidecar. Earlier accurate own prose and all other SITE bytes are preserved; no frontend/deployment claim is added. Matched main/head docs_audit reports no new finding; unchanged source-snapshot, docs-audit and model-registry tests pass; DOC_REGISTRY blob/mode/type is unchanged. Required current-head review and CI pass, all conversations are resolved, and existing review limits are respected. These are admission checks, not runtime release evidence."
status: approved
supersedes: docs/superpowers/specs/2026-11-09-feat-playbook-001-retire-ew-brief.md
---

# Caller-scope successor for EW brief retirement

## Narrow amendment and admission status

This successor is admitted on November 11 under the coordinator's explicit interpretation of the user's full EarningsWhispers removal/deployment direction and subsequent “Yes and Fix the required check” instruction. The coordinator determined that removal of the one obsolete recap stub, while preserving every assertion, is necessary maintenance within the approved retirement. This records that authorization basis; it does not claim the user literally approved #1799 or every technical sentence. Only the already-published narrow caller-file allowance is admitted. The predecessor receives only its approved-to-superseded status flip. This specification remains a Draft PR pending normal review and merge; no implementation is published by it.

Only `done_when` items 6 and 7 and the Design-and-caller-scope paragraph change the inherited contract. The additional permission is removal of exactly this obsolete line in `tests/lib/strat_2026_11_06.py::run_brief` (line 152 on main `3991c628ff2a614ce5f74a1aa9ca1843d1faca80`):

```python
    monkeypatch.setattr(pb, "_ew_recap_or_unavailable", lambda *a, **k: {})
```

All fixture setup, assertions and parametrized nodes remain unchanged. Do not retain a dummy production helper, inject it from another test, or skip callers to avoid the failure. The dependent shared-level suites are `tests/lib/test_brief_planner_parity.py`, `tests/gcp/test_level_basis.py` and `tests/gcp/test_premarket_provenance.py`; refresh their collected-node inventory against actual main and preserve every node. The older 43-node receipt is historical, not the current count. Other imports of the helper module must remain intact. Preserve #1753 session-own premarket cleanup and #1784 calibrated-level behavior.

Items 1–5 and 8, the FEAT/REQ/issue/canvas/SITE declarations and all thirteen separately admitted finite-values obligations remain unchanged. No numeric handling, schema, evaluator, shared calendar, deployment, secret or historical-data change is admitted here. The inherited approval/publication narrative below describes the predecessor, not approval or completion of this proposal. Prior review accounting and #1687 history remain intact.

After normal admission and merge, use a fresh main-based implementation plan bound to this successor from its first commit. Carry the preserved unpublished P-D candidate by explicit source diff and requalify against current dependencies; never stack on an unmerged source branch or claim old receipts cover changed bytes. The existing source candidate and history remain preserved. This does not reset review limits or certify deployment.

## Inherited specification, with only the enumerated caller-scope changes


# Retire EarningsWhispers from the premarket brief (P-D)

## Scope approval and publication record

On November 9, 2026 the user answered “Yes” to the bundled admission request that included: “Premarket brief: filter both EW source spellings before calculations and remove EW picks, scoring and recap. Keep compatibility fields empty, preserve non-EW earnings and the shared calendar, and retain historical records. EW picks would also stop appearing in replays. Preserve the separate finite-values repair and its test coverage.” The earlier EW-first sequencing proposal was also answered “Yes”. The user separately instructed: “Do it amd complete FULL REMOVAL. Deploy as well”.

This records approval of the presented substantive scope and preservation conditions, not a claim that the user read every technical word. The prepared acceptance contracts implement that scope without a new behavioral decision. The coordinating parent selected the verified direct-main successor route and authorized normal specification publication. The standalone P-D spec does not supersede the finite-values contract; the paired successor preserves that contract and #1687's source-note obligation. #1687's branch, work and review receipts are untouched; it must not merge unchanged after its predecessor is superseded. No review allowance resets.

Publication is documentation only. Normal required review and CI remain, with at most two rounds and no bypass. The P-A owner holds the next main merge; this documentation PR must not merge ahead of P-A #1758. P-D's implementation branch opens only after these approved specifications and the actual P-A helper implementation are on main. Shared-file ownership is serialized; Recovery's work and calibration drafts are preserved. Existing test receipts characterize the base, not new implementation behavior.

General EW deployment authorization is present. Production execution, digest/target/effect coordination with the release owner, real output verification and any action-specific confirmation remain separate. This PR performs no production operation, migration, data/secret deletion or schedule change. Historical EW data and the shared calendar remain intact.

## Problem and inspected evidence

Inspected base: 02f6df9b5b373c0f65cb3756436e3ad4977aaab6. `load_earnings_for_brief` (301; SQL 354–377) reads retired rows and strategy/strike/premium/score. Its EW priority/tier branches are at 387–442. `load_yesterday_amc_reactions` (790; SQL 823–843) includes EW maxima and strategy. Recap helpers at 719–787 import evaluator calendar functions and read EW verdicts. Generation wires the recap at 1386–1389; `_build_earnings_embed` (2474 onward) renders legacy payloads and reserves recap truncation priority.

The current brief suite passed 211 collected cases locally. That is baseline evidence, not evidence of retirement. Earlier supplied SQLite characterization (EW maxima 9/30000 versus UW 5/20000) is a proposed reproducible fixture, not a newly executed receipt in this task. Actual PostgreSQL/runtime qualification is separate. A test that supplies already-filtered rows cannot prove the SQL boundary.

FEAT-PLAYBOOK-001 owns the structured daily setup/brief path; issue #1168 supplies recap history, not an automatic closure claim. Requirements cover playbook, reliability, replay and governance. `canvases: []`: inspected canvases.yml has no PLAYBOOK-owned canvas. PLAYBOOK-09 exists in SITE but its Chain describes GET /api/playbook/{ticker}; it is used solely as the existing capability-owned implementation-source note anchor, not a claim that the UI displays this earnings embed. The own note already exists. Source/test references in MODEL-BRIEF-001 and the explicit brief-consumer section of MODEL-EWV-001 are affected.

## Approaches

Hide the header only: rejected because SQL aggregates and recap acquisition remain. Delete historical rows/evaluator: rejected because audit history and shared calendar users must survive. Exclude both exact aliases at both SQL boundaries and remove EW-only acquisition/presentation: selected for the admitted scope.

## Design and caller scope

Reuse P-A's NULL-safe predicate with alias `ec` in each WHERE clause before grouping/aggregation. Preserve `Earnings_Whispers` and unknown sources; source-predicate retention does not override ordinary eligibility. Remove EW row/time priorities and tier branches, preserving non-EW tiers 2/4/6. Do not replace history-derived playability with the retired calendar score. Keep compatibility keys empty as specified. Remove prior-AMC MAX(strategy) only, preserving its gap/top-N/lean behavior.

Remove recap definitions, weekday wiring, verdict/Whispers/recap formatting and retired badges. Preserve non-EW `_valid_num`, `_gap_str`, `_beat_miss_str`, `_row_line`, calendar/economic/ORB/gamma/FTFC behavior and routing. Direct consumers found via source search are the brief renderer and `format_discord_messages_routed`; persistence writes per-ticker content, not an API earnings shape. Recheck these callers at the actual implementation base.

Three existing caller fixtures monkeypatch the function being deleted: `tests/gcp/test_strat_snapshot_parity.py::_brief`, `tests/api/test_brief_level_break_response.py::_run_brief_and_persist` and `tests/lib/strat_2026_11_06.py::run_brief`. The third fixture landed with #1753 after the original caller inventory and remains in current main after #1784. Delete only these obsolete stubs, preserving every assertion, parametrized node and all session-own premarket/level-basis/provenance and calibrated-level behavior. The admitted source/test scope is these five files. This specification changes no source/test file.

`docs/models/MODEL-EWV-001.md` lines 44–66 assert the current recap consumer and tests. Replace only those present-tense claims with accurately scoped retirement/historical context; leave evaluator behavior, past verdict evidence, shared calendar and ingestion details intact. This semantic documentation update remains part of the inherited admitted contract, not hidden as a line-number repair or permission to edit another capability's product row.

## Acceptance implementation details

The tests named in done_when are proposed nodes, not existing or passing tests. Execute actual query text with both source aliases, bound date parameters and all columns needed by the real loader. A local SQLite adapter may supplement tests if SQL is compatible, but record the adapter and retain real caller paths; it is not PostgreSQL release evidence. Predicate-removed controls must fail the exclusion assertion while supported controls still pass. Both aliases must be tested with high-liquidity rows so eligibility cannot mask a missing predicate.

For pipeline tests use supported existing I/O seams, real date/replay routing and real embed; forbid live effects. Verify exactly one earnings query and one prior-AMC query when those paths are invoked; zero recap queries/evaluator session lookups. Sunday routing has its existing different loader calls and must be asserted separately, not forced into a weekday call count. Do not add numeric coercion to make retirement tests pass. A legacy EW NaN payload ignored by the renderer proves retirement only; future supported-source finite-value tests prove number handling.

The complete current-node inventory and the finite-value successor accompany this specification. At implementation, regenerate against actual main, retain additions since this snapshot, and obtain approval for any new disposition instead of using this snapshot to delete new coverage. All tests outside the enumerated retirements retain their behavior.

## Capacity, risks and rollout

No new API/source calls, jobs or schedules. Earnings/prior-AMC retain their individual SQL queries; weekday recap query and evaluator-session lookup disappear. Record branch-local elapsed time, peak memory, query/call counts and fixture row/byte envelopes; no production performance claim is made from local tests. No timeout, memory allocation, retry, image or cadence changes. Cost is bounded by unchanged cadence and removed calls; actual billed savings remain unmeasured.

Risks are aggregation before filtering, inactive invalid-sibling fixtures, stale caller stubs, accidental non-EW tier/routing changes and leftover legacy recap rendering. Actual-query negative controls, explicit node mapping, caller tests and golden supported-source outputs address these separately.

This source/spec change does not implement the finite-values repair, delete data/schema/secrets or change the evaluator/shared calendar. This specification PR does not deploy, execute Cloud Run or send notifications. No release is certified by CI. After the authorized deployment proceeds through its applicable release gates with a pinned digest, the release owner must record real weekday and supported replay output, deployed image and query/call evidence without secrets. P-F evaluator stripping still waits for its own consumer and live-job retirement prerequisites. Historical d4478433/d806bfd1 receipts remain historical.

## Historical publication base

Prepared from main `59bfb52a779e366083e9f47c158c4328311d8a78`, after #1703's P-A own-scope specification merged. Source/test/model anchors are unchanged from `02f6df9b`. P-A's helper implementation is separately pending in #1758; a specification merge is not proof that helper code has landed. Revalidate prerequisites against actual main before implementation.


## Successor admission base

Admission reconciles current main `7322f23691e4f6ed8c4836338b7fa6d53c2d581f`. P-A helper implementation landed through #1758 at `82967a88`; its prior pending status above is historical. The 45-node caller inventory and qualification remain bound to `3991c628`, whose relevant runtime/test bytes are unchanged at this admission base. Revalidate the actual implementation base after the specification merges. #1685 is sequenced first; this PR stays Draft until the coordinated final base sync and normal review. No review history or allowance is reset.
