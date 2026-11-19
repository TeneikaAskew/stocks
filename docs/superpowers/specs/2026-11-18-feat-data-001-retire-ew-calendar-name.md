---
feat_id: FEAT-DATA-001
req_ids: [REQ-DATA-001]
issues: []
canvases: []
site_source_notes: [SHARED-07]
done_when:
  - "gcp/fetchers/evaluate_ew_strikes.py is absent. tests/gcp/test_canonical_calendar_consumers.py proves the two real consumers operate with an import guard rejecting the legacy module, and a fresh process cannot import it. Tracked executable Python and runnable module configuration contain no legacy import or module invocation. These absence/delegation controls fail on the actual pre-change base; historical prose, schema comments, retired-command rejection controls and source-exclusion literals are retained."
  - "Only _regular_session_due in gcp/fetchers/_av_realtime_collector.py and earnings_session_schedule in lib/earnings_reactions.py replace their lazy legacy imports/calls with lib.eastern_time.session_schedule. Preserve public wrapper signature, ET conversion, collector open-inclusive/close-exclusive eligibility, validations, exception handling and every indirect consumer. Update exactly the three legacy-module mock targets in tests/gcp/test_av_options_collector_entry.py to the canonical symbol; preserve all assertions and parametrized cases."
  - "The five old tests/gcp/test_nyse_sessions_shim.py nodes have an exact recorded disposition into tests/gcp/test_canonical_calendar_consumers.py: preserve holiday-week/early-close, DST and missing-calendar/no-fallback assertions; replace obsolete wrapper-source equality and scorer-surface tests with explicit module-absence and real-consumer delegation checks. Cover both DST transitions, closed sessions and actual collector boundary/error behavior. Preserve all 22 cases in tests/gcp/test_fetch_market_data_vendor_answers.py byte-for-byte and pass them. Record actual base/head collected nodes; no unrelated skip, assertion weakening or coverage deletion. Historical 71/49/22 scorer-retirement counts remain historical evidence, not a fresh-run claim."
  - "07-MODEL-REGISTRY.md L47 shows MODEL-EWV-001 Status Retired and Rec REMOVE (the declared Rec vocabulary at L11 is KEEP / RETEST / RESTRUCTURE / PAUSE / REMOVE, enforced by tests/meta/test_model_registry_consistency.py::test_rec_cells_use_the_declared_vocabulary) with the retirement date; no history row or blockquote is deleted; docs/product/generated/model-registry.json is regenerated and export_model_registry.py --check exits 0; docs/models/MODEL-EWV-001.md carries a retirement header and its Tests section cites tests/gcp/test_canonical_calendar_consumers.py and tests/gcp/test_av_options_collector_entry.py, each of which exists and identifies the retired module and its canonical replacement as tests/meta/test_model_registry_consistency.py L548-561 requires of a cited file; that suite passes"
  - "The existing timezone-boundary test passes with no new debt or exemption; lib/eastern_time.py, the 22 vendor cases and indirect consumer source remain byte-identical. The historical producer-table correction belongs to docs-only P-J (#2095), not this runtime PR; preserve its current main content. MODEL-EWV historical 71/49/22 receipts remain intact."
  - "The PR opens only after the FEAT-PLAYBOOK-001 retire-ew-brief PR is on main (the brief imports scoring_session until then) and after RUNTIME-QUALIFICATION-PLAN.md section 2 (evaluate-ew-strikes job and scheduler deleted) is complete, both recorded in the PR description"
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists this PR"
  - "Source identity (SHARED-07): on the implementation PR head, the existing bounded producer and verifier (`scripts/maintenance/doc_source_snapshot.py produce`, then `verify` with the fixed ceilings, run from the committed HEAD) prove committed source and SITE body identity bound to this approved spec at the actual merge base, where its blob equals the one on current main; the plan binds this spec; the only SITE change is the FEAT-DATA-001 / SHARED-07 row of the Implementation-source notes table, updated with the prefix source_identity_sha256=<current source hash> and nonempty implementation and test prose that describes this PR's compatibility-module deletion, canonical consumer imports and mapped tests while retaining prior scorer-retirement evidence, keeping the row's earlier own content; every other SITE byte is unchanged; the sidecar is produced from the final committed SITE body and committed, replacing the sidecar record the merge of main carries; the matched main and branch `scripts/maintenance/docs_audit.py` runs report no finding that main does not; `tests/scripts/test_doc_source_snapshot.py` and `tests/scripts/test_docs_audit.py` pass unchanged; the registry `docs/DOC_REGISTRY.md` blob, mode and type equal main's; required current-head checks pass before merge under the repository's existing review rules, which this spec does not extend."
status: approved
supersedes: docs/superpowers/specs/2026-10-31-feat-data-001-retire-ew-module-shim.md
---

# Retire the EW-named calendar compatibility module

## Proposed calendar-import amendment — not approved

This successor is DRAFT. Historical approvals and review receipts reproduced below apply to the predecessor only, not this amendment. No runtime branch may bind this draft. No new review budget is implied. Preserve every obligation except the expressly enumerated calendar-import changes. All four companion successors must be admitted and land before the DATA migration implementation; only then create its fresh bound plan. Existing accepted predecessor text is immutable; any permitted status flip occurs only through the normal admission process, not this preparation.

The canonical primitive is `lib.eastern_time.session_schedule(start, end)`, retaining the existing schedule/index/UTC types, inclusive date range, holidays, early closes, delayed opens, DST, caching and fail-closed errors. No second calendar or fallback is introduced. Historical references and old review evidence remain historical. The absent `2026-10-12-feat-option-001-av-options.md` was proposed in closed-unmerged #1449; it is not a main predecessor. Its relevant live contract is the source-journal specification landed in #1484. Correcting that citation does not waive any source, freshness, settlement or resource obligation.

## Current implementation scope

Delete only the legacy shim, change the two lazy import/call sites, map the five shim tests into the new canonical-consumer test file and three collector mock targets. Update MODEL-EWV current source/test citations while preserving its retirement header and history; use only own DATA catalog/lineage, declared SHARED-07 and supported generated inventory/source proof. No changes to canonical library, other runtime features, schema, deployment files, schedules, secrets or historical records. No source/archive transfer or production action.

The predecessor's retained-import obligations in acceptance1–3 and implementation body are replaced by the migration acceptance above. Its unrelated historical-retirement, prerequisites, model-history, vendor coverage, delivery and postmerge obligations remain; pre-existing prerequisites are verified on the actual implementation base, never assumed. The historical implementation branch name is not reused: bind a fresh plan/branch. Runtime success is not deployed consumer verification. After review and merge, release ownership separately verifies actual images and external import consumers; unknown out-of-repository clients are not certified by tracked-file scans.

Capacity: zero added calls/retries/SQL/jobs; no changed timeout, memory or renderer/verifier limit. Record actual affected-test time and RSS; no billed savings claim.

## Historical predecessor body (retained evidence, not instructions to recreate the shim)

The complete body below records the old implementation and its review chronology. Its old retention/byte-equality/branch instructions are historical only; current executable acceptance and scope are above. Historical approvals do not approve this draft.


# Strip gcp/fetchers/evaluate_ew_strikes.py to the nyse_sessions calendar shim; retire MODEL-EWV-001

P-I in RETIREMENT-DESIGN.md rev 3.9 sections 4, 4.1 (site 24 and the two UPDATE writers), 6 and 8 (residual 3 resolved); test surface per ACCEPTANCE-PLAN.md section 1 and TEST-INVENTORY.md section 1 (rev 3.6). Owned by FEAT-DATA-001 because 02-FEATURE-CATALOG.md:528 puts gcp/fetchers/ under its Code field; the registry row 07-MODEL-REGISTRY.md:47 binds MODEL-EWV-001 to this code path and to no capability, and the product-delivery skill lets the spec that changes a model carry its registry rows (.claude/skills/product-delivery/SKILL.md:85). The job, scheduler and dispatcher are the FEAT-DEPLOY-001 spec 2026-10-31-feat-deploy-001-retire-ew-evaluator.md (P-C). The nyse_sessions wrapper and its consumers are preserved byte-for-byte until the approved shared-calendar spec's own gates migrate them; PR #1546 is not a prerequisite.

## Changes from the local rev 3.9 draft (read first)

The title, the paragraph above and `done_when` items 1 to 7 are the local rev 3.9 draft byte for byte
(sha256 `21a412db253593bedd3b3d76101bc4ac27c49a75fbc68c594dfa9e1b1ff5e1ad`, kept in the EW retirement
project folder under `proposed-specs/`). That draft was prepared against main d806bfd1. Checked against
main b0f88b5e on 2026-11-02, this text adds only:

- `site_source_notes: [SHARED-07]` and `done_when` item 8. The implementation edits
  `gcp/fetchers/evaluate_ew_strikes.py` and tests under `tests/gcp/`, inside SITE's watched scope
  (`docs/DOC_REGISTRY.md` row for `docs/product/03-SITE-TRACEABILITY.md`: `platform/api, platform/deploy.sh,
  platform/Dockerfile, gcp, lib, scripts, tests`). The product-delivery skill lets a feature clear
  watched-code drift only through a note its approved spec declares, and an implementation PR cannot add
  its own declaration (`.claude/skills/product-delivery/references/spec-template.md`, the
  `site_source_notes` bullets). Item 8 is the template's pre-merge source-identity obligation, in the shape
  approved for FEAT-SIGNAL-001 (#1672) and FEAT-INSIGHT-001 (#1674).
- the sections "Changes from the local rev 3.9 draft (read first)" (this one), "Anchors on current main",
  "Choice of Chain element: SHARED-07", "Ownership and collisions", "Sequencing with #1546", "Source
  identity and close-out", "Separation of evidence" and "Status".

Nothing else changed.

Amended on 2026-11-11 against main 028acf38, after #1546 merged (3ab668a9): only the sentences that
describe main's code were brought up to date, and the intent is unchanged (the shim keeps the calendar
behaviour as main has it). In the intro paragraph the catalog anchor reads `:528`. Item 1 describes the
kept wrapper as main now holds it, a wrapper over `lib.eastern_time.session_schedule`, at L196-205.
Item 2 adds the consumer main gained since d806bfd1, `lib/earnings_reactions.py`. Item 3 gives main's
line numbers beside the d806bfd1 ones, lets the grep show the consumers items 2 and 3 name, and reads
L196-205. Item 5 gives the baseline entries' lines on main beside the d806bfd1 ones. The rev 3.9 sha256
above is that of the text before this amendment. The section "Anchors on current main" gains a
2026-11-11 paragraph and "Sequencing with #1546" a closing paragraph.

## Anchors on current main

Read on main b0f88b5e. `gcp/fetchers/evaluate_ew_strikes.py`, `tests/gcp/test_evaluate_ew_strikes.py`,
`gcp/fetchers/_av_realtime_collector.py` and `tests/gcp/test_av_options_collector_entry.py` are
byte-identical to d806bfd1 (`git diff --quiet d806bfd1 b0f88b5e` on the four paths exits 0), so the line
ranges and the 71/49/22 collection counts in items 1 to 3 are those of the current files; the counts were
executed at d806bfd1 and are not re-executed here. `nyse_sessions` is L196-206, `Session` L185-193,
`scoring_session` L208-234, its call in `evaluate_range` L377. `gcp/premarket_brief.py` still imports
`nyse_sessions, scoring_session` at L738 and calls `scoring_session` at L762. The repository-wide read of
`scoring_session` and `nyse_sessions` outside the module and `docs/` finds only `premarket_brief.py`,
`_av_realtime_collector.py` L425 and L434, `tests/gcp/test_av_options_collector_entry.py`,
`tests/gcp/test_evaluate_ew_strikes.py` and the two baseline entries at
`tests/fixtures/timezone_boundary_baseline.json:99-100` (inside L97-101).
`tests/lib/test_av_account_allowance.py` lists the module at L12. `07-MODEL-REGISTRY.md` L47 is the
MODEL-EWV-001 row and L11 the Rec vocabulary; `tests/meta/test_model_registry_consistency.py` L548-561 is the
cited-test check; `06-DATA-ARCHITECTURE.md` L55 is the `earnings_calendar` producer cell. The three spec
anchors in item 1 read the same (`2026-10-12-feat-ops-001-av-operations.md:225`,
`2026-10-13-feat-option-001-av-source-journal.md:176`, `2026-10-12-feat-data-001-av-market-data.md:501`),
as do `02-FEATURE-CATALOG.md:523` and `.claude/skills/product-delivery/SKILL.md:85`. One anchor moved:
`check_product_scope`, cited in item 5 at `scripts/gate/spec_gate.py` L4176-4227, is at L4278-4339 on
b0f88b5e. Item 5's list of what that check admits under `docs/product/` predates this declaration: with
`site_source_notes` declared, the same check also admits the declared `03-SITE-TRACEABILITY.md` note row,
through `gate_note_scope` (L4317-4323 on b0f88b5e). That row is item 8's only SITE change.

Prerequisites as they stand on b0f88b5e, unchanged from the draft: the FEAT-PLAYBOOK-001 retire-ew-brief
spec (P-D) is not on main and no open pull request carries it, so `premarket_brief.py` still consumes
`scoring_session`; the evaluator job and scheduler are still to be deleted under
RUNTIME-QUALIFICATION-PLAN.md section 2 after #1658 (P-C). Item 6 holds the implementation until both are
recorded.

Re-read on main 028acf38 on 2026-11-11. #1546 merged as 3ab668a9 and changed
`gcp/fetchers/evaluate_ew_strikes.py` only in its two hunks: the import line L67 now reads
`from lib.eastern_time import ET, ET_NAME, session_schedule` and `nyse_sessions` (L196-205) returns
`session_schedule(start, end)`. `Session` is still L185-193; `scoring_session` is L207-232 and its call
in `evaluate_range` L376. `tests/gcp/test_evaluate_ew_strikes.py` and `tests/lib/test_av_account_allowance.py`
are still byte-identical to d806bfd1, so the 71/49/22 counts stand. `gcp/premarket_brief.py` imports
`nyse_sessions, scoring_session` at L745 and calls `scoring_session` at L769;
`_av_realtime_collector.py` imports and calls `nyse_sessions` at L568 and L577; `lib/earnings_reactions.py`
`earnings_session_schedule` (L961-964) is a consumer of `nyse_sessions` that d806bfd1 did not have; the two
baseline entries are `tests/fixtures/timezone_boundary_baseline.json:93-94` (inside L91-95);
the FEAT-DATA-001 Code field is `02-FEATURE-CATALOG.md:528` and now also lists `lib/eastern_time.py`.
The L11, L47, L55, L548-561, SITE L125 and L1303, `SKILL.md:85`, `check_product_scope` and three spec
anchors read as above. The FEAT-PLAYBOOK-001 retire-ew-brief spec
(`2026-11-09-feat-playbook-001-retire-ew-brief.md`, approved) is now on main, but its implementation is
not: `premarket_brief.py` still consumes `scoring_session`, so item 6 still holds the implementation.

## Choice of Chain element: SHARED-07

The module writes `earnings_calendar` verdict columns through the `evaluate-ew-strikes` job and serves no
route. SHARED-07 (Freshness watchdog and /api/health/freshness, under "00 · Shared") is the Chain
element whose Data cell is every tracked Cloud SQL table (`docs/product/03-SITE-TRACEABILITY.md:125` on
main b0f88b5e), and `(FEAT-DATA-001, SHARED-07)` (L1303) is
FEAT-DATA-001's only existing Implementation-source note row. The implementation updates that row and keeps
its earlier own content. The FEAT-DATA-001 fetcher-reader spec (P-F, draft #1685) declares the same row;
whichever implementation merges second merges main and rebinds the row with both descriptions kept.

## Ownership and collisions

Read 2026-11-02 from the 64 open pull requests (each head fetched as `refs/pull/<n>/head`, diffed against its
merge base with main b0f88b5e), for every file items 1 to 5 name, the FEAT-DATA-001 catalog record item 7
changes and the SITE row item 8 changes:

- #1546 (`feature/feat-data-001-market-calendar`, draft) changes `gcp/fetchers/evaluate_ew_strikes.py` in
  two hunks (the `lib.eastern_time` import line, which gains `session_schedule`, and the body of
  `nyse_sessions`, which returns `session_schedule(start, end)`), and changes `lib/eastern_time.py`,
  `tests/fixtures/timezone_boundary_baseline.json` and the FEAT-DATA-001 catalog record (Status, Last
  reviewed and the Code field).
- #1658 (P-C, draft) removes the `evaluate-ew-strikes-daily` scheduler row of `07-MODEL-REGISTRY.md`
  (L370 on b0f88b5e), which names MODEL-EWV-001, regenerates `docs/product/generated/model-registry.json`,
  and lowers the scheduler-count floor in `tests/meta/test_model_registry_consistency.py` from 66 to 65;
  this spec changes the L47 row.
- #1682 and #1608 (drafts) change other `07-MODEL-REGISTRY.md` rows and regenerate
  `docs/product/generated/model-registry.json`; #1430, #1681 (P-A) and #1608 change
  `tests/fixtures/timezone_boundary_baseline.json`.
- #1643 (draft) changes the `(FEAT-DATA-001, SHARED-07)` row and the FEAT-DATA-001 catalog record (its
  Evidence status and an added "Typed-news runtime draft" line); #1564 (draft) changes the same row.
- No open pull request changes `tests/gcp/test_evaluate_ew_strikes.py`,
  `gcp/fetchers/_av_realtime_collector.py`, `tests/gcp/test_av_options_collector_entry.py`,
  `docs/models/MODEL-EWV-001.md` or `tests/lib/test_av_account_allowance.py`.

The implementation edits no other pull request's branch. Where one of them is still open when the
implementation is cut, whichever of the two merges second merges main, regenerates the timezone baseline
and the model-registry export, and rebinds its own SITE row.

## Sequencing with #1546

Item 1 keeps `nyse_sessions` byte-identical to main's L196-205 (L196-206 before #1546 merged) and item 3's new shim test checks the
library schedule, a DST date, ImportError without `pandas_market_calendars` and the module surface.
#1546 (draft, head 5b926526, merge base 11135c4d) changes the wrapper's body, to
`return session_schedule(start, end)` (the wrapper is L196-204 on its head), and the module's
`from lib.eastern_time import ET, ET_NAME` line, to import `session_schedule` too; its
`lib/eastern_time.py` imports `pandas_market_calendars` inside `_build_session_cache` with no `except` in
it or any caller, and returns the same shape (session-date index, UTC `market_open` and `market_close`).

Executed on 2026-11-02, the same probe calling `gcp.fetchers.evaluate_ew_strikes.nyse_sessions` from
main b0f88b5e and from #1546's head, with `pandas_market_calendars` 5.6.0 in a scratch directory outside
the repository:

| Case | main b0f88b5e | #1546 5b926526 |
|---|---|---|
| 2026-11-23 to 2026-11-27 | 11-23, 11-24, 11-25, 11-27; 11-27 closes 18:00Z | identical |
| 2027-03-15 open | 13:30Z | identical |
| library blocked (`sys.modules['pandas_market_calendars'] = None`) | ModuleNotFoundError (an ImportError) | identical |

So the item 3 cases hold for either body, and the merge order changes no calendar behaviour. The
implementation keeps whichever body main holds when it is cut. If #1546 merges first, the kept wrapper and
its import line are #1546's, and the shim test calls `lib.eastern_time._reset_session_cache()` before the
blocked-library case, because #1546's process-wide session cache would otherwise serve that case without
importing the library. If this implementation merges first, #1546's wrapper hunk applies to the kept
wrapper as it is, its import hunk is reapplied by #1546 to the stripped module's import lines, and #1546,
merging second, adds the same cache reset to the shim test; the implementation's author tells #1546's
owner so before the implementation is pushed. Whichever merges second merges main and regenerates the
timezone baseline. Either way the blocked-library case does not pass or fail on cache state.

#1546 merged first (3ab668a9, on main 028acf38), so the first branch above applies: the kept wrapper
and its import line are #1546's as main holds them, and the shim test calls
`lib.eastern_time._reset_session_cache()` before the blocked-library case. Executed on 2026-11-11 against
the merge of main 028acf38, with `pandas_market_calendars` 5.3.0, the same probe gives the table's
results: sessions 11-23, 11-24, 11-25 and 11-27 with 11-27 closing 18:00Z, 2027-03-15 opening 13:30Z,
and ModuleNotFoundError with the library blocked after the cache reset.

## Source identity and close-out

Declaration: only the `(FEAT-DATA-001, SHARED-07)` row in the existing Implementation-source notes table of
`docs/product/03-SITE-TRACEABILITY.md` may describe this implementation and its local tests. Every other
SITE byte, foreign rows and every Chain, checklist, frontend, progress and deployment cell stay unchanged.
The note describes backend source and local tests only. It claims no deployment, no deletion or rewrite of
stored verdict columns, no frontend effect and no authenticated external review.

Pre-merge (`done_when` item 8), on the implementation branch `fix/feat-data-001-ew-module-shim`, after its
prerequisites and this spec are on main:

1. The plan binds this spec from its first commit, with a task whose `Spec:` line names item 8.
2. This spec's blob must be the same in the actual merge base, in current main and in the branch head
   (`spec_binding` in `scripts/maintenance/doc_source_snapshot.py`), with `status: approved` and feat
   FEAT-DATA-001.
3. Read the producer's current source hash, commit the `(FEAT-DATA-001, SHARED-07)` row with the prefix
   `source_identity_sha256=<hash>; ` and nonempty prose (canonical single-line row, rows in sorted order),
   produce the sidecar from the final committed body, commit it, and run `verify` on the final HEAD within
   the unchanged ceilings. Repeat after any later watched-code, SITE body or policy change, including every
   further merge of main.
4. The registry `docs/DOC_REGISTRY.md` blob, mode and type stay equal to main's; the matched main and branch
   audit reports nothing new; the affected BASE suite, the normal current-head review under the existing
   rules and CI pass. The ordinary pre-commit hook and PR-mode gate judge every commit. Nothing is bypassed.

Post-merge obligations, tracked here, in the plan and in the PR, never as pre-merge `done_when` boxes and
never ticked before the genuine evidence exists:

- Verify the actual main source and body identity in a fresh clone after the squash, without assuming the
  feature commit survives.
- Complete the separate DOC main and staging close-out with real evidence: the deployed images of the jobs
  that import the shim (the realtime options collector) carry the stripped module. This spec claims none.
- Retire the sidecar only as the skill prescribes: an ordinary trunk-only `--stamp --verify` after real
  checks, removing the sidecar in the same DOC commit, or the fixed `trunk-closeout-pending` route when
  deployed-evidence prose must change first. A record never retires itself.
- Set the plan to `status: done` on a `docs/` branch after the merge.

## Separation of evidence

Kept apart, and never offered for one another: the pre-merge identity of committed source and SITE body; the
collected-count arithmetic and the moved and new tests of item 3; the registry and baseline checks of items 4
and 5; the current-head review and CI; and the post-merge main, staging and sidecar-retirement evidence. A
local identity record is not review authentication, deployment evidence or data freshness. The historical
verdict columns in `earnings_calendar` are kept as they are; this spec deletes and recomputes nothing.

## Status

Authoring snapshot, shell clock 2026-11-02: this text was prepared as a draft spec for owner acceptance
under the owner's 2026-11-02T03:47:57Z direction to refresh and publish P-I as a truthful draft through the
ordinary gates. That direction is not an acceptance or an admission. At that snapshot the text had no owner
acceptance and no review. This paragraph records the snapshot and is not kept current: the spec's
admission, review, CI and merge state at any later time is its `status:` line read with its pull request
and the EW ledger. `status: approved` is set only after the owner's written approval of this exact text,
records that admission and nothing else, and is followed by the normal current-head review and CI before
merge. No exception from another change transfers to it.
