---
feat_id: FEAT-DATA-001
req_ids: [REQ-DATA-001]
issues: []
canvases: []
site_source_notes: [SHARED-07]
done_when:
  - "gcp/fetchers/evaluate_ew_strikes.py contains only the existing nyse_sessions pandas_market_calendars wrapper, byte-identical to main's L196-206, its imports, and a docstring naming the OPS, OPTION and DATA specs that still bind the import (2026-10-12-feat-ops-001-av-operations.md:225, 2026-10-13 av-source-journal.md:176, 2026-10-12 av-market-data.md:501); it exports no scoring_session, evaluate_range or main, contains no earnings_whispers literal and no AlphaVantageConfig import; no new calendar helper is introduced and lib/eastern_time.py is unchanged"
  - "gcp/fetchers/_av_realtime_collector.py is unchanged and its import from gcp.fetchers.evaluate_ew_strikes import nyse_sessions still resolves; tests/gcp/test_av_options_collector_entry.py passes unchanged, still patching ew.nyse_sessions"
  - "scoring_session (L208-234) and the Session dataclass (L185-193) are removed with the scorer: at d806bfd1 their only consumers are evaluate_range (L377, removed here) and gcp/premarket_brief.py load_ew_recap (L738, L762, removed by the FEAT-PLAYBOOK-001 retire-ew-brief PR, which is why this PR waits for it), and the PR description shows the repo-wide grep for scoring_session and nyse_sessions proving no other consumer; tests/gcp/test_evaluate_ew_strikes.py is split, not deleted: its 28 scorer functions (49 collected cases at L142-477 and L597-604, each calling evaluate_range, main, scoring_session or _compute_verdict, including test_intraday_on_a_closed_day_has_no_session and test_an_early_close_session_ends_at_one_pm) are removed with the code they test, and its seven fetch_market_data vendor-contract functions (22 collected cases at L513-594, with the helpers _Resp, _month and _daily and the fetch_market_data import at L31; #1181, #1188, #1202) move verbatim to a new tests/gcp/test_fetch_market_data_vendor_answers.py, whose collected node ids equal the 22 recorded at d806bfd1 and all pass; the PR description shows, as executed on its base and its head, the repository's collected totals, where head minus base equals minus 49 (the 71 cases of the old file leave, the 22 vendor cases arrive in the new file) plus the collected count of the new tests/gcp/test_nyse_sessions_shim.py, with no other file's count changed; a new tests/gcp/test_nyse_sessions_shim.py, labelled new, tests the kept wrapper itself: the library schedule with UTC open/close for a holiday week (2026-11-26 absent, 2026-11-27 closes 18:00Z) and a DST date (2027-03-15 opens 13:30Z), ImportError when pandas_market_calendars is unimportable (no weekday fallback), and the module surface (no scoring_session, Session, evaluate_range, main, _compute_verdict, _UPDATE_SQL, _CLEAR_SQL; L196-206 byte-identical to main)"
  - "07-MODEL-REGISTRY.md L47 shows MODEL-EWV-001 Status Retired and Rec REMOVE (the declared Rec vocabulary at L11 is KEEP / RETEST / RESTRUCTURE / PAUSE / REMOVE, enforced by tests/meta/test_model_registry_consistency.py::test_rec_cells_use_the_declared_vocabulary) with the retirement date; no history row or blockquote is deleted; docs/product/generated/model-registry.json is regenerated and export_model_registry.py --check exits 0; docs/models/MODEL-EWV-001.md carries a retirement header and its Tests section cites tests/gcp/test_nyse_sessions_shim.py and tests/gcp/test_av_options_collector_entry.py, each of which exists and mentions the module stem as tests/meta/test_model_registry_consistency.py L548-561 requires of a cited file; that suite passes"
  - "tests/meta/test_timezone_boundaries.py passes on a baseline regenerated with --write-baseline, from which the two scoring_session entries at tests/fixtures/timezone_boundary_baseline.json:97-101 have left, with no new violation; tests/lib/test_av_account_allowance.py CONSUMERS no longer lists the module and the test passes; docs/product/06-DATA-ARCHITECTURE.md is not changed by this PR, because check_product_scope (scripts/gate/spec_gate.py L4176-4227) admits under docs/product/ only the FEAT's own catalog and traceability records, the model registry and its generated files, and the renderer-owned inventory blocks; the PR description names the follow-up docs-only PR P-J (branch docs/ew-retirement-product-docs, RETIREMENT-DESIGN.md section 6.1), which drops the module from the earnings_calendar producer cell at line 55 after this PR and the other phases it documents have merged; docs/models/MODEL-EWV-001.md's retirement header states the executed collection at d806bfd1 (71 cases over 35 functions), the 49 removed and the 22 moved"
  - "The PR opens only after the FEAT-PLAYBOOK-001 retire-ew-brief PR is on main (the brief imports scoring_session until then) and after RUNTIME-QUALIFICATION-PLAN.md section 2 (evaluate-ew-strikes job and scheduler deleted) is complete, both recorded in the PR description"
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists this PR"
  - "Source identity (SHARED-07): on the implementation PR head, the existing bounded producer and verifier (`scripts/maintenance/doc_source_snapshot.py produce`, then `verify` with the fixed ceilings, run from the committed HEAD) prove committed source and SITE body identity bound to this approved spec at the actual merge base, where its blob equals the one on current main; the plan binds this spec; the only SITE change is the FEAT-DATA-001 / SHARED-07 row of the Implementation-source notes table, updated with the prefix source_identity_sha256=<current source hash> and nonempty implementation and test prose that describes this PR's module strip, its moved and new tests and the MODEL-EWV-001 retirement, keeping the row's earlier own content; every other SITE byte is unchanged; the sidecar is produced from the final committed SITE body and committed, replacing the sidecar record the merge of main carries; the matched main and branch `scripts/maintenance/docs_audit.py` runs report no finding that main does not; `tests/scripts/test_doc_source_snapshot.py` and `tests/scripts/test_docs_audit.py` pass unchanged; the registry `docs/DOC_REGISTRY.md` blob, mode and type equal main's; required current-head checks pass before merge under the repository's existing review rules, which this spec does not extend."
status: approved
supersedes: null
---

# Strip gcp/fetchers/evaluate_ew_strikes.py to the nyse_sessions calendar shim; retire MODEL-EWV-001

P-I in RETIREMENT-DESIGN.md rev 3.9 sections 4, 4.1 (site 24 and the two UPDATE writers), 6 and 8 (residual 3 resolved); test surface per ACCEPTANCE-PLAN.md section 1 and TEST-INVENTORY.md section 1 (rev 3.6). Owned by FEAT-DATA-001 because 02-FEATURE-CATALOG.md:523 puts gcp/fetchers/ under its Code field; the registry row 07-MODEL-REGISTRY.md:47 binds MODEL-EWV-001 to this code path and to no capability, and the product-delivery skill lets the spec that changes a model carry its registry rows (.claude/skills/product-delivery/SKILL.md:85). The job, scheduler and dispatcher are the FEAT-DEPLOY-001 spec 2026-10-31-feat-deploy-001-retire-ew-evaluator.md (P-C). The nyse_sessions wrapper and its consumers are preserved byte-for-byte until the approved shared-calendar spec's own gates migrate them; PR #1546 is not a prerequisite.

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

Item 1 keeps `nyse_sessions` byte-identical to main's L196-206 and item 3's new shim test checks the
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
