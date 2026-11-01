---
feat_id: FEAT-CATALYST-001
req_ids: [REQ-DATA-001, REQ-PLAYBOOK-001]
issues: []
canvases: []
site_source_notes: [CATALYSTS-04]
done_when:
  - "tests/lib/test_earnings_reactions_recommended_structure.py::test_implied_move_invalid_returns_skip_only_where_the_guard_is_consulted: with long_only=True, score_quintile 'Q5' and a calibration that confirms over-pricing (realized_vs_implied_ratio below _IC_RATIO_THRESHOLD and avg_short_strangle_pnl_pct above _IC_STRANGLE_THRESHOLD), recommended_structure(archetype, 'Q5', calibration, implied_move_pct=None, implied_move_invalid=True) returns 'SKIP' for every archetype, where the same call without the keyword returns the long archetype action. With the keyword True, every other branch is unchanged: score_quintile other than 'Q5' returns the archetype action; calibration None or not over-priced returns the archetype action; long_only=False returns 'IC' for the over-priced Q5 case and the archetype action otherwise."
  - "tests/lib/test_earnings_reactions_recommended_structure.py::test_default_false_is_byte_identical_behaviour: for every combination of archetype in (bullish_trend, bearish_trend, reversal_play, mixed, None), score_quintile in (Q1, Q5, None), calibration in (None, under-priced, over-priced), implied_move_pct in (None, 5.0, 20.0) and long_only in (True, False), the return value with implied_move_invalid omitted equals the return value on main d806bfd1 (captured as a table in the test), and implied_move_invalid=False gives the same value."
  - "tests/lib/test_earnings_reactions_recommended_structure.py::test_invalid_flag_is_keyword_only_and_does_not_shadow_a_valid_implied_move: passing implied_move_invalid positionally raises TypeError; implied_move_invalid=True together with a non-None implied_move_pct raises ValueError at function entry, before any branch, in both modes (long_only True and False), for every score_quintile including None, and for calibration None (the brief never sends both; the contradiction is an error, not a silent choice)."
  - "git diff against the merge base changes only lib/earnings_reactions.py (the recommended_structure signature, its docstring, one entry check raising ValueError, and one branch returning 'SKIP') and the new test file. gcp/refresh_earnings_views.py, gcp/premarket_brief.py and gcp/earnings_reactions_brief.py are unchanged, and the two refresh_earnings_views call sites (L248, L252 at d806bfd1) still omit the keyword."
  - "The existing tests under tests/lib/ and tests/gcp/ that exercise recommended_structure pass unmodified."
  - "Own narrow plan and product records, the no-new documentation audit, current-head required Codex code review and CI pass through the normal gates."
  - "Source identity (CATALYSTS-04): on the implementation PR head (stocks#1670), the existing bounded producer and verifier (`scripts/maintenance/doc_source_snapshot.py produce`, then `verify` with the fixed ceilings, run from the committed HEAD) prove committed source and SITE body identity bound to this approved spec at the actual merge base, where its blob equals the one on current main; the plan binds this spec; the only SITE change is the FEAT-CATALYST-001 / CATALYSTS-04 row of the Implementation-source notes table, updated with the prefix source_identity_sha256=<current source hash> and nonempty implementation and test prose that describes this PR's recommended_structure keyword and its tests and keeps the earlier accurate own content of that row; every other SITE byte is unchanged; the sidecar is produced from the final committed SITE body and committed, replacing the sidecar record the merge of main carries; the matched main and branch `scripts/maintenance/docs_audit.py` runs report no finding that main does not; `tests/scripts/test_doc_source_snapshot.py` and `tests/scripts/test_docs_audit.py` pass unchanged; the registry `docs/DOC_REGISTRY.md` blob, mode and type equal main's; required current-head checks pass before merge under the repository's existing review rules, which this spec does not extend."
status: draft
supersedes: docs/superpowers/specs/2026-10-31-feat-catalyst-001-implied-move-invalid-guard.md
---

# recommended_structure implied_move_invalid keyword: SITE source-note successor

## Why this spec replaces the 2026-10-31 spec (amendment, read first)

This spec supersedes `2026-10-31-feat-catalyst-001-implied-move-invalid-guard.md` (approved, on main since
ca043892, #1650, blob c6ec9060) and repeats its contract unchanged: `done_when` items 1 to 6 here are that
spec's six items byte for byte, and the section "Retained text of the 2026-10-31 spec" below is its body byte
for byte. Inside that retained text, "this spec" and "this PR" mean the 2026-10-31 spec as written on that
date. This spec adds only:

- `site_source_notes: [CATALYSTS-04]`, the existing SITE Chain element that FEAT-CATALYST-001 specs already
  declare for their implementation-source note (selection evidence below);
- `done_when` item 7, the pre-merge source-identity obligation the spec template requires
  (`.claude/skills/product-delivery/references/spec-template.md`, the `site_source_notes` bullets);
- the sections "Source identity and close-out", "Retirement of the 2026-10-31 spec", "Separation of evidence"
  and "Status".

Why it is needed: the implementation (draft stocks#1670) edits `lib/earnings_reactions.py` and adds a test
under `tests/`, both inside SITE's watched scope (`platform/api, platform/deploy.sh, platform/Dockerfile, gcp,
lib, scripts, tests`, as the audit reports it). The product-delivery skill lets a feature clear watched-code
drift only through a note declared by its approved spec, and an implementation PR cannot add that declaration
to its own spec. The 2026-10-31 spec declares none, and an approved spec does not change in place, so the
declaration needs this replacement. Executed evidence: `scripts/maintenance/docs_audit.py` run on #1670's
committed head and on main 751a6c13 with one shared issues snapshot reports three findings on the branch that
main does not (two `changed-since` and one `source-provenance`, all on `docs/product/03-SITE-TRACEABILITY.md`).

What it does not change: the keyword, the entry-check ValueError, the guard branch, the None rule, thresholds,
IC mode, every other `done_when` behaviour of the 2026-10-31 spec, its test names, its no-caller-change rule
and its no-deploy rollout. No code, plan, test, SITE row, sidecar or other product document changes in the
change that lands this spec. It makes no runtime or deployment claim.

## Reading of inherited `done_when` item 4 (scope clarification, not a new policy)

Item 4 is kept byte for byte. Its file list ("changes only lib/earnings_reactions.py ... and the new test file")
is read as the limit on runtime CODE and TEST files: no other code or test file changes, and the three named
callers stay unchanged. It does not forbid the delivery records that the repository's own rules require in the
same pull request, none of which changes runtime behaviour:

- the branch's plan under `docs/superpowers/plans/` (product-delivery Phase 3; the gate refuses code without it);
- the FEAT-CATALYST-001 catalog record and the traceability entry (Phase 5 and inherited item 6);
- the re-rendered `inventory:reads` block of `docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md`, whose
  `lib/earnings_reactions.py` line citations move when the function grows (REQ-GOV-004: "A pull request that
  changes what those blocks cite SHALL carry the re-rendered blocks itself"; on #1670 this is three citation
  lines, commit 487e7868);
- the declared `(FEAT-CATALYST-001, CATALYSTS-04)` SITE note row and the source-identity sidecar (item 7).

This reading adds no runtime policy and widens no behavioural criterion. If the owner prefers different
wording, the change is to this section only.

## Ownership and dependencies

- `recommended_structure` and the new test file are reserved to the briefing implementation (draft stocks#1670)
  by the recovery thread's ledger entry 105. Draft stocks#1608 (recovery-owned) appends to the same library file
  only after L958 and writes the same CATALYSTS-04 row; neither PR changes the other's lines.
- #1670 depends on this spec: it cannot clear the documentation audit until this spec is approved and on main.
- The FEAT-PLAYBOOK-001 brief plan (spec #1651) still waits for #1670's keyword to land on main; this spec does not
  change that order.

## Textual differences from the 2026-10-31 spec

- Frontmatter: `site_source_notes: [CATALYSTS-04]` added after `canvases: []`; `done_when` item 7 added after the six
  retained items; `status: draft` (was `approved`); `supersedes:` names the 2026-10-31 spec (was `null`).
  `feat_id`, `req_ids`, `issues`, `canvases` and items 1 to 6 are byte-identical.
- Body: a new title and the new sections above and below, followed by the 2026-10-31 body byte for byte under
  "Retained text of the 2026-10-31 spec".

## Choice of Chain element: CATALYSTS-04

The declaration must be sorted, unique and name existing Chain IDs of the SITE body on the base
(`scripts/maintenance/doc_source_snapshot.py` `declaration` and `chain_ids`, read on main 751a6c13; executed
there, the parser returns 222 Chain IDs including CATALYSTS-04).

- Four approved FEAT-CATALYST-001 specs on main already declare `[CATALYSTS-04]`:
  `2026-10-13-feat-catalyst-001-av-catalysts-delivery.md`,
  `2026-10-24-feat-catalyst-001-event-bound-reaction-integration.md` and its successor
  `2026-10-25-feat-catalyst-001-model-trace-metadata.md` (both for `lib/earnings_reactions.py`, draft
  stocks#1608), and `2026-10-27-feat-catalyst-001-optional-earnings-estimate.md` (stocks#1621, merged
  2026-10-27 as e7c48250).
- CATALYSTS-04 is a Chain row of the Catalysts screen, whose capability is FEAT-CATALYST-001
  (`docs/product/03-SITE-TRACEABILITY.md`, the SCREEN-CATALYSTS section). No Chain element names
  `recommended_structure`, the premarket brief's action tag or the `/api/earnings` recommended-structure
  columns, so no narrower existing ID exists. CATALYSTS-04 is an identity anchor for the
  `lib/earnings_reactions.py` source note, not a claim that the keyword changes the event timeline.
- The row `(FEAT-CATALYST-001, CATALYSTS-04)` is on main now with #1621's prose. It is one row shared by name
  with every FEAT-CATALYST-001 implementation that declares CATALYSTS-04, including #1608. Each PR writes it at
  its own merge base. Whichever lands later composes the cell from the row then on main, keeps earlier accurate
  content, describes only its own source and tests, and recomputes the source hash. No PR attests another's
  change. #1670 and #1608 both touch `lib/earnings_reactions.py` (#1670 inside `recommended_structure`, #1608
  only after L958), so the later one also rebases its code onto the earlier.

## Source identity and close-out

Declaration: only the `(FEAT-CATALYST-001, CATALYSTS-04)` row in the existing Implementation-source notes table
of `docs/product/03-SITE-TRACEABILITY.md` may describe this implementation and its local tests. Every other SITE
byte, the historical marker, foreign rows and every Chain, checklist, frontend, progress and deployment cell stay
unchanged. The note describes backend library source and local tests only. It claims no deployment, no caller
adoption, no frontend effect and no authenticated external review.

Pre-merge (`done_when` item 7), on the #1670 branch, after the merge of main that brings in this spec:

1. The plan `docs/superpowers/plans/2026-11-01-feat-catalyst-001-implied-move-invalid-guard.md` is rebound to
   this spec in that same merge-of-main commit, while the merge is in progress, and gains a task with a `Spec:`
   line and a checklist item for item 7. During a merge of main the commit gate reads the approved spec from
   MERGE_HEAD (`scripts/gate/spec_gate.py`, the `--commit` branch that sets `against = ["MERGE_HEAD"]`), where
   the 2026-10-31 spec is superseded, so a plan still naming it is refused there; a plan naming this spec in a
   later ordinary commit is instead measured against HEAD. Read from source at 751a6c13, not executed on a
   landed successor: it is a mandatory real check at that merge, not a result.
2. This spec's blob must be the same in the actual merge base, in current main and in the branch head
   (`spec_binding` in doc_source_snapshot.py), with `status: approved` and feat FEAT-CATALYST-001.
3. Read the producer's current source hash, commit the `(FEAT-CATALYST-001, CATALYSTS-04)` note with the prefix
   `source_identity_sha256=<hash>; ` and nonempty prose (canonical single-line row, rows in sorted order),
   produce the sidecar from the final committed body, commit it, and run `verify` on the final HEAD within the
   unchanged ceilings. Repeat after any later watched-code, SITE body or policy change, including every further
   merge of main.
4. The registry `docs/DOC_REGISTRY.md` blob, mode and type stay equal to main's; the catalog record and the
   traceability entry are updated as Phase 5 requires; the matched main and branch audit reports nothing new;
   the affected suites, the normal current-head review under the existing rules and CI pass. The ordinary
   pre-commit hook and PR-mode gate judge every commit. Nothing is bypassed.

Post-merge obligations, tracked here, in the plan and in the PR, never as pre-merge `done_when` boxes:

- Verify the actual main source and body identity in a fresh clone after the squash.
- Complete the separate DOC main and staging close-out with real evidence; this spec claims none.
- Retire the sidecar only as the skill prescribes (trunk-only `--stamp --verify` after real checks, removing
  the sidecar in the same DOC commit, or the fixed `trunk-closeout-pending` route). A record never retires
  itself.
- Set the plan to `status: done` on a `docs/` branch after the merge.

Evidence kinds stay separate: pre-merge identity of committed source and SITE body, the current-head review and
CI, and the post-merge main, staging and sidecar-retirement evidence are different records. A local identity
record is not review authentication, deployment evidence or data freshness.

## Retirement of the 2026-10-31 spec

The 2026-10-31 spec has `supersedes: null` and no spec on main names it as a predecessor, so its retirement does
not meet the depth-two case. The status-only flip (`status: approved` to `superseded`, nothing else) is made in
the same change as this spec's approval. Nothing else is edited in that file.

## Separation of evidence

Executed by this author on 2026-11-01 against main 751a6c13, in a local worktree with the repository hook
installed (`core.hooksPath=.githooks`; nothing bypassed):

- `scripts/gate/spec_gate.py --check-spec` on this file: `spec ok`.
- The commit of this file alone on its docs branch: the hook printed `spec gate ok`.
- Items 1 to 6 and the retained body compared byte for byte with the 2026-10-31 spec (blob c6ec9060): equal.
- `doc_source_snapshot.chain_ids` on main's SITE body: 222 IDs, CATALYSTS-04 among them.
- On #1670 (not this spec): `docs_audit.py` on branch and on main with one issues snapshot: three new SITE findings.

Read from source, not executed: the merge-of-main plan rebind, spec binding at a real merge, and the producer and
verifier on #1670. Not run: CI, the producer and verifier, any check against a landed successor, and any hosted
review. The predecessor's status flip is prepared as a one-line diff and is not applied in this draft.

## Status

Local docs-only proposal, prepared on coordinator direction under the owner's request to land the briefing
prerequisite; unpublished and unreviewed when written. `status: approved` is set only after the owner's written
approval of this exact text, records that admission and nothing else, and is followed by the normal
current-head review and CI before merge. It is not a formal review, Ready, merge or deployment permission. The
2026-10-31 spec's admission record is kept in its retained text and in stocks#1650.

## Retained text of the 2026-10-31 spec (byte for byte)


# recommended_structure: an invalid implied move fails closed where the long-only guard is consulted

## Status

Rev 2.1, approved as a specification on 2026-10-31 (admission record below); rev 2.1 is rev 2 plus one post-review text edit: the template heading `Design` replaces `Change`; LOCAL-DESIGN2 reviewed rev 2, `../history/rev2-catalyst-seed-69a9e44f.md`), prepared locally on 2026-10-31 against stocks main `d806bfd19a82bb723acfdb7035e2a3ad52deb77c`. Published as a specification-only draft pull request on its own `docs/spec-feat-catalyst-001-implied-move-invalid-guard` branch from main d806bfd1 (owner direction 2026-10-31 12:34 UTC); not implemented; `status: approved` records the owner's cumulative admission on that pull request (product-delivery SKILL.md:40) and nothing else changed with it: no design, done_when or policy text. Rev 2 (after the first independent design review, LOCAL-DESIGN1) adds REQ-DATA-001 to req_ids (the fail-explicit requirement the guard serves), fixes the ValueError check's placement at function entry, names the mode in done_when 3, and adds the template headings; rev 1 is `../history/rev1-catalyst-seed-9ff32793.md`. It exists because the FEAT-PLAYBOOK-001 spec `2026-10-31-feat-playbook-001-premarket-brief-finite-values.md` (rev 5.1, part 2) needs one library keyword, and `lib/earnings_reactions.py` is a FEAT-CATALYST-001 catalog Code row, so the change is specified under its owner rather than edited across feature lines.

Approval attribution: the owner approved the briefing design part "prevent invalid-only data from producing a LONG CALL through the existing long-only guard" (asked 06:39:47 UTC, answered "That's fine" 10:18:34 UTC, 2026-10-31). This spec is the author's design for the library half of that part. On 2026-10-31 at 20:58:17 UTC the owner answered "yes" to the 18:42:45 UTC question asking whether they approve the written acceptance sections of the FEAT-PLAYBOOK-001 brief spec (done_when, L6 to L18 at commit 619dd069) and of this FEAT-CATALYST-001 keyword spec (done_when, L6 to L12 at commit 1d8b0535), stated as: preserve valid data, daily selections and unrelated callers; isolate invalid after-market rows and choose valid finite alternatives where available; prevent invalid-only values from producing a LONG CALL through the existing guard, with only the explicitly listed long-only cases changing and iron-condor behaviour unchanged; reject invalid internal calls rather than invent numeric inputs, and retain existing tests and review gates. Cumulative admission: the 10:18:34 UTC design approval plus the 20:58:17 UTC written-contract approval; the owner ruled (21:00 UTC) that no additional whole-document phrase is required where the policy and the mapped decisions are already covered. This is specification approval only: not merge or deployment permission, not a GitHub review approval and not a waiver of hosted review. **Approval provenance, mapped to sections:** part (2) of the approved question ("prevent invalid-only data from producing a LONG CALL through the existing long-only guard") covers the Design section's keyword and guard branch and done_when 1, 2, 4 and 5; the entry-check ValueError (done_when 3) was admitted with the written acceptance section at 20:58:17 UTC; the test names, line anchors and headings are author metadata on which no decision depends. Part (1) of the approved question does not concern this file.

`supersedes: null` is actual: no FEAT-CATALYST-001 spec on main names `recommended_structure` (the only spec that does, `2026-10-13-feat-option-001-av-earnings-cycle-contexts.md`, belongs to FEAT-OPTION-001 and is not altered).

## Problem

`recommended_structure` (L305 to L400 at d806bfd1) consults `implied_move_pct` only in long-only mode for an over-priced Q5 row (the Q5 gate at L369, the IC return at L389 to L390, the implied test at L396 to L398) and documents `None` as "no filter, keep the long recommendation". The brief has no way to say "a value was present but invalid, so do not grant the long recommendation": its only options are a real number, None (which grants), or a fabricated number (a silent fallback that yields SKIP at the same place and is indistinguishable at the output). Replicating the guard predicate in the brief would duplicate policy that lives here.

## Design

One keyword-only argument, `implied_move_invalid: bool = False`.

- **Entry check.** If `implied_move_invalid` is true and `implied_move_pct` is not None, raise `ValueError` immediately, before any branch and in every mode: the caller is contradicting itself, and the function does not pick for it.
- **Guard branch.** In the branch reached only when `long_only` is true, `score_quintile == 'Q5'` and `is_over_priced` holds, immediately before the existing `implied_move_pct > _LO_IMPLIED_HARD_MAX` test: if `implied_move_invalid` is true, return `'SKIP'`; otherwise the existing test and return are unchanged.

The docstring gains three lines describing the three caller states (valid number, None for absent, True flag for invalid). `_LO_IMPLIED_HARD_MAX`, the IC rule, the archetype maps, `_env_long_only` and every other branch are unchanged. With the keyword omitted or False the function is byte-identical in behaviour to main (done_when 2).

## Non-goals

No change to the None rule (absent still grants the long recommendation), to thresholds, to IC mode, to `compute_playability_score`, `confidence_label` or any reader. No caller is changed in this spec; the brief adopts the keyword in its own spec. The separately owned EarningsWhispers retirement change writes NULL for EW-derived fields in `gcp/refresh_earnings_views.py` and does not call or change this function; the two contracts stay separate.

## Approaches considered

- **Brief-side predicate copy or surrogate number.** Rejected (one source of truth for math; silent fallback).
- **A sentinel value for `implied_move_pct` (for example `float('nan')`).** Rejected: a NaN compares False against the threshold and silently grants the long action, the exact failure being fixed.
- **A tri-state enum replacing `implied_move_pct`.** Rejected: changes the two existing callers' signatures for no gain.

## Risks

- A caller that sets the flag and a number gets a ValueError; today no caller sends the flag. The brief's spec pins that it never sends both.
- Default-off compatibility: `gcp/refresh_earnings_views.py:248, 252` omit the keyword and are asserted unchanged (done_when 4 and 5).

## Files and ownership

- `lib/earnings_reactions.py`: FEAT-CATALYST-001 catalog Code row. The open draft stocks#1608 (`feature/feat-catalyst-001-event-bound-reactions`, head 59aab3f0, merge base d4478433) inserts 529 lines into this file after L958, none inside `recommended_structure`; this change is additive and is sequenced with #1608's owner (the recovery thread), which does not modify #1608 for it.
- `tests/lib/test_earnings_reactions_recommended_structure.py`: new.

## Rollout

Spec alone on `docs/spec-feat-catalyst-001-implied-move-invalid-guard`, published as a draft independently of the FEAT-PLAYBOOK-001 spec draft; after the owner's admission, review and CI, merge. Then one plan and one `fix/feat-catalyst-001-implied-move-invalid-guard` branch; review and CI; merge. The FEAT-PLAYBOOK-001 brief implementation plan is cut only from a main that holds this keyword (no implementation stacking); the two specification drafts do not wait on each other. No deploy is implied: the keyword is inert until the brief passes it.
