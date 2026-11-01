---
feat_id: FEAT-INSIGHT-001
req_ids: [REQ-DATA-001]
issues: []
canvases: []
site_source_notes: [INSIGHTS-04, INSIGHTS-07]
done_when:
  - "Every earnings_calendar query in lib/agents/ranker/candidates.py (_candidates_from_earnings) and lib/agents/summarizers.py (earn_sql) carries lib.earnings_reactions.EARNINGS_NOT_RETIRED_SQL inside its existing WHERE (inside the aggregating subquery where there is one), with no other change to the query"
  - "A hermetic test per read site in tests/agents/ runs the actual reader with the query layer faked over that site's discriminating fixture from tests/fixtures/earnings_calendar_sources.py (for lib/agents/ranker/candidates.py an EW postmarket row dated earlier than the AV premarket row, so the EW row wins MIN(earnings_date) and MIN(earnings_time) on main; for lib/agents/summarizers.py an earlier-dated EW row that leads the ORDER BY earnings_date LIMIT 5 list on main), asserts the main-shaped query returns the EW value as the negative control and the predicated query returns the AV value, keeps the NULL and unknown rows, removes both alias rows, and leaves an EW-only ticker out"
  - "No fallback value, relabelling or substitute source is introduced; main's behaviour for AV, UW and Yahoo rows is byte-identical in the tests' expected sets"
  - "Source identity (INSIGHTS-04, INSIGHTS-07): on the implementation PR head, the existing bounded producer and verifier (`scripts/maintenance/doc_source_snapshot.py produce`, then `verify` with the fixed ceilings, run from the committed HEAD) prove committed source and SITE body identity bound to this approved spec at the actual merge base, where its blob equals the one on current main; the plan binds this spec; the only SITE changes are the FEAT-INSIGHT-001 / INSIGHTS-04 and FEAT-INSIGHT-001 / INSIGHTS-07 rows of the Implementation-source notes table, added with the prefix source_identity_sha256=<current source hash> and nonempty implementation and test prose that describes only this PR's two earnings_calendar predicates and their tests; every other SITE byte is unchanged; the sidecar is produced from the final committed SITE body and committed, replacing the sidecar record the merge of main carries; the matched main and branch `scripts/maintenance/docs_audit.py` runs report no finding that main does not; `tests/scripts/test_doc_source_snapshot.py` and `tests/scripts/test_docs_audit.py` pass unchanged; the registry `docs/DOC_REGISTRY.md` blob, mode and type equal main's; required current-head checks pass before merge under the repository's existing review rules, which this spec does not extend."
status: draft
supersedes: null
---

# Exclude retired EarningsWhispers rows from the FEAT-INSIGHT-001 earnings_calendar readers

One-line predicate PR (P-G in RETIREMENT-DESIGN.md rev 3.9 sections 4.1 (sites 21-22) and 6). Owned by FEAT-INSIGHT-001 because 02-FEATURE-CATALOG.md:291 lists lib/agents/ under its Code field; the gate takes one feat_id per spec (spec_gate.py:1465). Depends on the FEAT-CATALYST-001 retire-ew-source PR (P-A) being merged on main, since the readers import lib.earnings_reactions.EARNINGS_NOT_RETIRED_SQL from it; the PR opens after that merge and no literal is vendored or duplicated. Legacy EW rows age out of forward windows within 8 days of P-A and P-B landing; this spec is what removes them from backward and whole-history reads.

## Changes from the local rev 3.9 draft (read first)

The title, the paragraph above and `done_when` items 1 to 3 are the local rev 3.9 draft byte for byte
(sha256 `97b8b335555360ad877a26707326a7e17499e8546cf9826aeb9956cad9807733`, kept in the EW retirement
project folder under `proposed-specs/`). Checked against main 751a6c13 on 2026-11-01, the two read sites
are unchanged in content since that draft (`lib/agents/ranker/candidates.py` `_candidates_from_earnings`,
query at L85-95; `lib/agents/summarizers.py` `summarize_catalysts`, `earn_sql` at L1612-1618), and one
prerequisite the draft lacked is genuine. This text adds only:

- `site_source_notes: [INSIGHTS-04, INSIGHTS-07]` and `done_when` item 4. The implementation edits two
  files under `lib/` and tests under `tests/agents/`, inside SITE's watched scope (`docs/DOC_REGISTRY.md`
  row for `docs/product/03-SITE-TRACEABILITY.md`: `platform/api, platform/deploy.sh, platform/Dockerfile,
  gcp, lib, scripts, tests`). The product-delivery skill lets a feature clear watched-code drift only
  through a note its approved spec declares, and an implementation PR cannot add its own declaration
  (`.claude/skills/product-delivery/references/spec-template.md`, the `site_source_notes` bullets). Item 4
  is the template's pre-merge source-identity obligation, in the shape approved for FEAT-DEPLOY-001 on #1666.
- the sections "Choice of Chain elements", "Source identity and close-out", "Separation of evidence" and
  "Status".

Item 4 and these sections are new and unreviewed: no judgment pass has looked at them. Nothing else
changed. Items 1 to 3 still name the two P-A artifacts absent on main 751a6c13
(`lib.earnings_reactions.EARNINGS_NOT_RETIRED_SQL` and `tests/fixtures/earnings_calendar_sources.py`);
P-A creates them, which is why the implementation waits for P-A on main.

## Choice of Chain elements: INSIGHTS-04 and INSIGHTS-07

Each read site reaches the page through a different existing Chain element, read on main 751a6c13:

- `_candidates_from_earnings` is called by `gather_candidates` (`lib/agents/ranker/candidates.py:290`),
  which `lib/agents/ranker/rank.py:99` calls. INSIGHTS-04 (`GET /api/insights/watchlist`,
  `docs/product/03-SITE-TRACEABILITY.md:753`) names `lib/agents/ranker/candidates.py` in its Backend cell
  and `fetch-earnings-calendar` in its GCP cell.
- `summarize_catalysts` is called by `build_context_bundle` (`lib/agents/summarizers.py:1980`), which
  `lib/agents/orchestrator.py:311` calls. INSIGHTS-07 (`POST /api/insights/report/{ticker}/refresh`,
  L756) names `lib/agents/orchestrator.py` and `lib/agents/summarizers.py` in its Backend cell.

INSIGHTS-01, -06 and -08 also show reports built through `build_context_bundle` (the scheduled
`insight-pipeline` job and the as-of replay). They describe the same predicate, so they are not declared:
one row per read site is enough to bind the source identity. FEAT-INSIGHT-001 has no row in the
Implementation-source notes table on main 751a6c13, so the implementation adds both rows.

Ownership, read 2026-11-01 from the open pull requests and their branch diffs against main: none changes
`lib/agents/`, `tests/agents/`, or a FEAT-INSIGHT-001 or INSIGHTS-04/07 row in
`docs/product/03-SITE-TRACEABILITY.md` or `docs/product/02-FEATURE-CATALOG.md`. #1608 and #1670 change
`lib/earnings_reactions.py`, which this spec only imports from; that file is P-A's to change.

## Source identity and close-out

Declaration: only the `(FEAT-INSIGHT-001, INSIGHTS-04)` and `(FEAT-INSIGHT-001, INSIGHTS-07)` rows in the
existing Implementation-source notes table of `docs/product/03-SITE-TRACEABILITY.md` may describe this
implementation and its local tests. Every other SITE byte, foreign rows and every Chain, checklist,
frontend, progress and deployment cell stay unchanged. The notes describe backend source and local tests
only. They claim no deployment, no rewrite of stored `insight_reports` rows, no frontend effect and no
authenticated external review.

Pre-merge (`done_when` item 4), on the implementation branch `fix/feat-insight-001-retire-ew-reader`,
after P-A and this spec are on main:

1. The plan binds this spec from its first commit, with a task whose `Spec:` line names item 4.
2. This spec's blob must be the same in the actual merge base, in current main and in the branch head
   (`spec_binding` in `scripts/maintenance/doc_source_snapshot.py`), with `status: approved` and feat
   FEAT-INSIGHT-001.
3. Read the producer's current source hash, commit both rows with the prefix
   `source_identity_sha256=<hash>; ` and nonempty prose (canonical single-line rows, rows in sorted order),
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
- Complete the separate DOC main and staging close-out with real evidence: the deployed
  `solyra-api-staging` service and the `insight-pipeline` and `auto-refresh-top-n` job images carry the
  predicates. This spec claims none.
- Retire the sidecar only as the skill prescribes: an ordinary trunk-only `--stamp --verify` after real
  checks, removing the sidecar in the same DOC commit, or the fixed `trunk-closeout-pending` route when
  deployed-evidence prose must change first. A record never retires itself.
- Set the plan to `status: done` on a `docs/` branch after the merge.

## Separation of evidence

Kept apart, and never offered for one another: the pre-merge identity of committed source and SITE body;
the hermetic tests of items 2 and 3, which run the real readers with only the query layer faked; the
current-head review and CI; and the post-merge main, staging and sidecar-retirement evidence. A local
identity record is not review authentication, deployment evidence or data freshness. Reports written
before the deploy keep the catalysts they were built with; this spec recomputes nothing.

## Status

Authoring snapshot, shell clock 2026-11-01: this text was prepared as a draft spec for owner acceptance
under the owner's 2026-11-01T23:46:01Z direction to continue the independent P-G qualification and publish
a focused draft through the ordinary gates. That direction is not an acceptance or an admission. At that
snapshot the text had no owner acceptance and no review. This paragraph records the snapshot and is not
kept current: the spec's admission, review, CI and merge state at any later time is its `status:` line
read with its pull request and the EW ledger. `status: approved` is set only after the owner's written
approval of this exact text, records that admission and nothing else, and is followed by the normal
current-head review and CI before merge. No exception from another change transfers to it.
