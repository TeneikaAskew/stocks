---
feat_id: FEAT-DEPLOY-001
req_ids: [REQ-DEPLOY-001, REQ-CAP-003]
issues: []
canvases: []
site_source_notes: [SHARED-07]
done_when:
  - "gcp/deploy.sh no longer defines deploy_evaluate_ew_strikes, deploy_fetchers no longer calls it, deploy_schedulers no longer calls _schedule for evaluate-ew-strikes-daily and instead issues the retired-schedule deletion in the existing L4179-4188 pattern (NOT_FOUND tolerated), the dispatcher case evaluate-ew-strikes) is a retirement stub that echoes a message containing RETIRED and exits 1 in the shape of the existing p7b-classifier stub, including an evaluate-ew-strikes entry in the _NEEDS_DEPLOY_CREDS=0 list at L1090-1094 (as p7b-classifier has at L1092) so that tests/gcp/test_deploy_reachability.py::test_targets_that_read_no_secret_are_exempt_from_the_eager_probe (L342-360) passes unchanged, and the help text has no evaluate-ew-strikes entry; the unrelated scheduler-block comment at L4732 is unchanged"
  - "tests/gcp/test_deploy_ew_evaluator.py (new, created by this PR alone; the bindings PR has its own tests/gcp/test_deploy_ew_bindings.py), with the repo's gcloud stub, proves: deploy_fetchers issues no run jobs create or update naming evaluate-ew-strikes; deploy_schedulers issues the delete and no create or update for evaluate-ew-strikes-daily; ./deploy.sh evaluate-ew-strikes exits 1, prints the RETIRED message and runs no gcloud command; ./deploy.sh help output contains no evaluate-ew-strikes; every other scheduler and job argument equals the argv captured on origin/main; the three deploy_fetch_news_sentiment* function bodies are byte-identical to the merge base"
  - "tests/gcp/test_deploy_image_pinning.py keeps test_a_deploy_names_the_built_digest and test_a_deploy_without_a_build_mutates_nothing with unchanged assertions against deploy_fetch_fred_rates, and its collected test count equals main's"
  - "07-MODEL-REGISTRY.md has no evaluate-ew-strikes-daily scheduler row (L370 removed; the MODEL-EWV-001 model row at L47 is changed by the FEAT-DATA-001 retire-ew-module-shim spec, not here); docs/product/05-INFRASTRUCTURE.md is not changed by this PR (check_product_scope, scripts/gate/spec_gate.py L4222-4227, refuses it on a fix branch; its L192 evaluate-ew-strikes row is removed by the docs-only PR P-J after this PR merges, RETIREMENT-DESIGN.md section 6.1); 05-a and 05-c inventory blocks equal scripts/maintenance/doc_inventory.py output (test_check_generated_docs.py::test_committed_docs_pass_every_gate)"
  - "gcp/fetchers/evaluate_ew_strikes.py is not changed by this spec"
  - "No Cloud Run job, scheduler or secret is mutated by this PR; RUNTIME-QUALIFICATION-PLAN.md section 2 (pause, delete scheduler, delete job) is linked from the PR as separately authorized close-out, and must be complete before the FEAT-DATA-001 module-shim PR's image ships"
  - "02-FEATURE-CATALOG FEAT-DEPLOY-001 record shows Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists this PR"
  - "Source identity (SHARED-07): on the implementation PR head (#1658), the existing bounded producer and verifier (`scripts/maintenance/doc_source_snapshot.py produce`, then `verify` with the fixed ceilings, run from the committed HEAD) prove committed source and SITE body identity bound to this approved spec at the actual merge base, where its blob equals the one on current main; the plan binds this spec; the only SITE change is the FEAT-DEPLOY-001 / SHARED-07 row of the Implementation-source notes table, added or updated with the prefix source_identity_sha256=<current source hash> and nonempty implementation and test prose that describes only this PR's gcp/deploy.sh retirement and its tests and keeps any earlier accurate own content of that row; every other SITE byte is unchanged; the sidecar is produced from the final committed SITE body and committed, replacing the carried FEAT-PLAYBOOK-001 / PLAYBOOK-09 record; the matched main and branch `scripts/maintenance/docs_audit.py` runs report no finding that main does not; `tests/scripts/test_doc_source_snapshot.py` and `tests/scripts/test_docs_audit.py` pass unchanged; the registry `docs/DOC_REGISTRY.md` blob, mode and type equal main's; required current-head checks pass before merge under the repository's existing review rules, which this spec does not extend."
status: draft
supersedes: docs/superpowers/specs/2026-10-31-feat-deploy-001-retire-ew-evaluator.md
---

# Bind the evaluate-ew-strikes retirement to its SITE source note (FEAT-DEPLOY-001)

## Why this spec replaces the 2026-10-31 spec (amendment, read first)

This spec supersedes `2026-10-31-feat-deploy-001-retire-ew-evaluator.md` (approved, on main since
412e1f85, #1652, blob 6a3453b1) and repeats its contract unchanged: `done_when` items 1 to 7 here are
that spec's seven items byte for byte, and the section "Retained text of the 2026-10-31 spec" below is
its body byte for byte. Inside that retained text, "this spec" and "this PR" mean the 2026-10-31 spec as
written on that date. This spec adds only:

- `site_source_notes: [SHARED-07]`, the existing SITE Chain element under which FEAT-DEPLOY-001 already
  writes its `gcp/deploy.sh` implementation-source note (selection evidence below);
- `done_when` item 8, the pre-merge source-identity obligation the spec template requires
  (`.claude/skills/product-delivery/references/spec-template.md`, the `site_source_notes` bullets);
- the sections "Source identity and close-out", "Retirement of the 2026-10-31 spec" and "Status".

Why it is needed: the implementation (stocks#1658) edits `gcp/deploy.sh` and tests under `tests/`, which
are inside SITE's watched scope (`docs/DOC_REGISTRY.md` row for `docs/product/03-SITE-TRACEABILITY.md`:
`platform/api, platform/deploy.sh, platform/Dockerfile, gcp, lib, scripts, tests`, as read on main
765fc91c). The product-delivery skill lets a feature clear watched-code drift only through a note declared
by its approved spec, and an implementation PR cannot add that declaration to its own spec. The
2026-10-31 spec declares none, and an approved spec does not change in place, so the declaration needs
this replacement. The same gap was reported for #1658 by the native read-only source audit (relayed in the
EW thread through the coordinator); this author read the gate and producer source and did not execute the
documentation audit on #1658. The #1658 branch also carries a sidecar for an unrelated record
(FEAT-PLAYBOOK-001 / PLAYBOOK-09, spec blob 3e114953, read at 9b076797); the sidecar this PR produces
replaces it.

What it does not change: the `gcp/deploy.sh` retirement and every other `done_when` behaviour of the
2026-10-31 spec, its tests, the retirement stub, the exclusion of `gcp/fetchers/evaluate_ew_strikes.py`
(the FEAT-DATA-001 module-shim spec), the exclusion of `docs/product/05-INFRASTRUCTURE.md`, and the rule
that no Cloud Run job, scheduler or secret is mutated by the PR. No code, plan, test, SITE row, sidecar or
other product document changes in the change that lands this spec. It makes no runtime or cloud claim.

## Choice of Chain element: SHARED-07

The declaration must be sorted, unique and name existing Chain IDs of the SITE body on the base
(`scripts/maintenance/doc_source_snapshot.py` `declaration`, L100 to L106 on main 765fc91c). Read from
source, not assumed:

- Three approved or retired FEAT-DEPLOY-001 specs on main already declare `[SHARED-07]` for their
  `gcp/deploy.sh` changes: `2026-10-12-feat-deploy-001-av-deployment.md` (superseded),
  `2026-10-29-feat-deploy-001-news-retry-coupling.md` (approved) and
  `2026-10-31-feat-deploy-001-retire-ew-bindings.md` (approved, stocks#1659's spec).
- SITE's SHARED-07 Chain row names `gcp/deploy.sh` as the file that defines the Cloud Run job and its
  triggers it describes (`freshness-watchdog`, `freshness-watchdog-hourly`, `freshness-watchdog-nightly`).
- The SITE rows that do mention `evaluate-ew-strikes` (CATALYSTS-01, -02, -03, -04, -06, -12 and
  DASHBOARD-06, -09 on main) mention it as an upstream writer of the `ew_*` columns on the catalyst read
  path. They are FEAT-CATALYST-001's elements (its spec already declares CATALYSTS-04), and this change
  touches no catalyst code or claim, so they are not declared here.
- No Chain element describes the evaluator's own deployment. SHARED-07 is therefore the narrowest
  existing ID with FEAT-DEPLOY-001 precedent. It is an identity anchor for the `gcp/deploy.sh` source
  note, not a claim that the evaluator feeds the freshness path. The owner approves or changes this
  choice with the exact text.
- The row `(FEAT-DEPLOY-001, SHARED-07)` is one row shared by name with the other FEAT-DEPLOY-001
  implementations that declare SHARED-07 (stocks#1659 and the news retry implementation). Each PR writes
  it at its own merge base. Whichever lands later composes the cell from the row then on main, keeps earlier
  accurate content, describes only its own source and tests, and recomputes the source hash. No PR
  attests another's change.

## Retained text of the 2026-10-31 spec (byte for byte)

# Retire the evaluate-ew-strikes job, scheduler and dispatcher; leave the module to its DATA owner

P-C in RETIREMENT-DESIGN.md rev 3.9 sections 4, 6 and 7. Scope is gcp/deploy.sh and the deploy-side docs only; the gate assigns gcp/deploy.sh to FEAT-DEPLOY-001 (spec_gate.py:1099, 4698-4701). The module gcp/fetchers/evaluate_ew_strikes.py is under gcp/fetchers/, FEAT-DATA-001's Code path (02-FEATURE-CATALOG.md:523), so its strip to the nyse_sessions shim and the MODEL-EWV-001 model-row change are the FEAT-DATA-001 spec 2026-10-31-feat-data-001-retire-ew-module-shim.md (P-I). No dependency on PR #1546 or lib.eastern_time. The dispatcher case is a retirement stub rather than a deletion so that an operator or scheduler invoking the old name fails loudly with the reason, matching the p7b-classifier precedent in gcp/deploy.sh (~L5415). Acceptance is behavioural: the earlier "exactly two grep lines" expectation was wrong because the unrelated comment at L4732 also contains the job name and is deliberately left alone.

## Source identity and close-out

Declaration: only the `(FEAT-DEPLOY-001, SHARED-07)` row in the existing Implementation-source notes table
of `docs/product/03-SITE-TRACEABILITY.md` may describe this implementation and its local tests. Every other
SITE byte, the historical marker (`Against: 05ab15fcc762`), foreign rows and every Chain, checklist,
frontend, progress and deployment cell stay unchanged. The note describes backend deployment-script source
and local tests only. It claims no deployment, no live retirement, no frontend effect and no authenticated
external review.

Pre-merge (`done_when` item 8), on the #1658 branch, after the merge of main that brings in this spec:

1. The plan `docs/superpowers/plans/2026-11-01-feat-deploy-001-retire-ew-evaluator.md` is rebound to this
   spec in that same merge-of-main commit, while the merge is in progress, and gains a task with a `Spec:`
   line and a checklist item for item 8. The plan exists only on the branch, so main holds no copy for the
   plan-stays-bound check to compare (`scripts/gate/spec_gate.py` `plan_stays_bound`, L1524 to L1529); a
   later ordinary commit is measured against HEAD, where the plan names the 2026-10-31 spec, and is
   refused as "a plan binds one spec". Once this spec is approved on main, a plan that names the
   2026-10-31 spec is refused as superseded. Read from source at 765fc91c, not executed on a landed
   successor: it is a mandatory real check at that merge, not a result.
2. This spec's blob must be the same in the actual merge base, in current main and in the branch head
   (`spec_binding`, doc_source_snapshot.py L673 to L678), and `status: approved` with feat FEAT-DEPLOY-001.
3. Read the producer's current source hash, commit the `(FEAT-DEPLOY-001, SHARED-07)` note with the prefix
   `source_identity_sha256=<hash>; ` and nonempty prose (canonical single-line row, rows in sorted order),
   produce the sidecar from the final committed body, commit it, and run `verify` on the final HEAD within the
   unchanged ceilings. Repeat after any later watched-code, SITE body or policy change, including every
   further merge of main.
4. The registry `docs/DOC_REGISTRY.md` blob, mode and type stay equal to main's; the catalog record keeps
   its date, PR, spec and plan links (the plan is re-pointed, the spec link moves to this spec); the
   matched main and branch audit reports nothing new; the affected BASE suite, the normal current-head
   review under the existing rules and CI pass. The ordinary pre-commit hook and PR-mode gate judge
   every commit. Nothing is bypassed, and a clone without the hook runs `spec_gate.py --commit` by hand.

Post-merge obligations, tracked here, in the plan and in the PR, never as pre-merge `done_when` boxes and
never ticked before the genuine evidence exists:

- Verify the actual main source and body identity in a fresh clone after the squash, without assuming the
  feature commit survives.
- Complete the separate DOC main and staging close-out with real evidence. This spec claims none, and the
  live job and scheduler deletion stays the separately authorized runtime close-out of the 2026-10-31
  `done_when` item 6.
- Retire the sidecar only as the skill prescribes: an ordinary trunk-only `--stamp --verify` after real
  checks, removing the sidecar in the same DOC commit, or the fixed `trunk-closeout-pending` route when
  deployed-evidence prose must change first. A record never retires itself.
- Set the plan to `status: done` on a `docs/` branch after the merge.

Evidence kinds stay separate: pre-merge identity of committed source and SITE body, the current-head
review and CI, and the post-merge main, staging and sidecar-retirement evidence are different records. A
local identity record is not review authentication, deployment evidence or data freshness.

## Retirement of the 2026-10-31 spec

The 2026-10-31 spec has `supersedes: null` and no spec names it as a predecessor on main, so its normal
retirement does not meet the depth-two defect that blocks a spec whose own pointer names an
already-superseded spec. The status-only flip (`status: approved` to `superseded`, nothing else) is made in
the same change as this spec's approval, the route the in-place rule admits when an approved same-FEAT
replacement names it. Nothing else is edited in that file; its pointer stays null. See "Separation of evidence" below for what was executed.

## Separation of evidence

Executed by this author on 2026-11-01 with `scripts/gate/spec_gate.py` from main 765fc91c, run by hand in a
scratch worktree on a local branch (the harness clone installs no hook; nothing was bypassed, no hook path or
flag was changed):

- `--check-spec` on this file reports `spec ok`. The same file with `site_source_notes: [NOPE-99]` reports
  `site_source_notes unavailable: site_source_notes must be sorted unique existing Chain IDs` and exits 1, so
  the declaration check is live and SHARED-07 is an existing Chain ID on main.
- `--commit` with this spec staged alone as a draft passes.
- `--commit` with this spec `approved` and the 2026-10-31 spec's status line flipped to `superseded` in one
  staged change passes; with this spec approved and the predecessor left approved it passes. With the flip
  and this spec still a draft it is refused (`no approved spec for its FEAT names it in supersedes`), and with
  the flip plus one extra byte in the predecessor it is refused (`an approved spec does not change in place`).
  The exemption is therefore not open, and the flip needs no deferral for this predecessor.

Read from source at 765fc91c, not executed: every line anchor above, the plan-stays-bound and spec-binding
behaviour at a real merge, and what the documentation audit reports for #1658. Not run: PR mode, CI, the
base suite, the producer and verifier, and any check against a landed successor; those stay mandatory real
checks at the later merge and are never recorded as passed here. The results were re-run on the final bytes
of this file; their hashes are in the EW thread's ledger, not in this spec.

## Status

Authoring snapshot, shell clock 2026-11-01T21:27:32Z: this text was prepared as a local docs-only proposal for
one owner decision, on coordinator direction under the owner's existing request to retire EarningsWhispers
from all active use, delivered to the EW thread at 21:21:20Z. That direction lifts a local-preparation hold
only and is not an owner decision or an admission. At that snapshot the text was unpublished and
unreviewed. This paragraph records the snapshot and is not kept current: the spec's admission, review,
CI and merge state at any later time is its `status:` line read with its pull request and the EW ledger.
`status: approved` is set only after the owner's written approval of this exact text, records that
admission and nothing else, and is followed by the normal current-head review and CI before merge. It is
not a formal review, Ready, merge or deployment permission, and no exception from another change transfers
to it. The 2026-10-31 spec's admission record is kept in its retained text and in stocks#1652.
