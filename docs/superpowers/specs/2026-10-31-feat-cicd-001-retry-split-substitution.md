---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-004]
issues: []
site_source_notes: [SHARED-01]
canvases: []
done_when:
  - "scripts/maintenance/doc_inventory.py defines RETRY_SPLIT matching only the two literal 05-a shapes \"`--max-retries <k>` is the norm (<n> of the <total> declared jobs)\" and \"the <n> `--max-retries <k>` jobs\", and insert_blocks(counts=True) rewrites only <n> and <total> in docs/product/infrastructure/05-a-ARCHITECTURE.md from the same declared-job parse gate_derived_numbers counts (defaults included); tests/scripts/test_doc_inventory.py proves main's 05-a renders byte-identically (68 declared, 43 at retries 0, 24 at retries 1); fixtures taken from the actual isolated and integrated gcp/deploy.sh sources each render the split that the same parse counts for that fixture, with the expectation pinned to the fixture's blob: the news retry change alone (68, 46, 21), the EW evaluator retirement alone (67, 43, 23) and both together (67, 46, 20); a fixture adding one retries-0 job renders the incremented count and total; and restore_blocks (counts=False) leaves a hand-edited split unchanged"
  - "scripts/maintenance/check_generated_docs.py reads the same RETRY_SPLIT object (tests/scripts/test_check_generated_docs.py asserts identity with doc_inventory.RETRY_SPLIT), every existing gate_derived_numbers phrasing, assertion and the full existing test_check_generated_docs.py suite remain unchanged and pass, and a non-owned phrasing it parses still fails when wrong"
  - "tests/scripts/test_spec_gate.py runs the unchanged PR-mode render check with merge-base 05-a prose and committed head source inputs, accepts a head whose only outside-block change is the exact computed retry split, and refuses with a REQ-GOV-004 message each of: a hand-typed wrong count in an owned shape, changed neighbouring prose on the same line, an inserted non-owned retry phrasing, a changed flag digit inside an owned shape, a change to any other retry mention (05-a signal-monitor sentence, 05-i, 05-k), and an owned shape in 05-c or 05-e; each refusal has an accepted control differing only in the condition under test"
  - "Every done_when obligation of docs/superpowers/specs/2026-10-13-feat-cicd-001-complete-generated-inventory.md other than its exact enumeration of three substitutions remains in force and still passes on the PR head: the unchanged byte, marker, clean-byte, plain-file, initializer, trust-boundary, child-isolation and existing-substitution controls; the 285-second registry-equivalent suite, 600-second BASE suite and 60-second/512MiB renderer measurement; and no change to scripts/gate/spec_gate.py verdict logic, the hook, the gate workflows, their pinned copies, the snapshot or any generated document"
  - "Each new assertion is shown failing against origin/main when the PR opens; before the PR's one push, the pre-push red-team pass required for a gate-suite change ran with its four independent roles (shell; YAML/Actions; exporter and policy documents; diff and byte parsing with the render check) under the owner-reserved FEAT-CICD-001 allowance LOCAL-RENDER1 (the exporter and policy seat scoped to this change only and authorized on the implementation PR; the stopped stocks#1630 operation is not retried, replaced or routed around), each finding proven by running the gate on a concrete snippet, the last pass empty and earlier findings listed with their refusing tests"
  - "python3 scripts/gate/spec_gate.py --pr origin/main passes on the PR head; branch/main docs_audit.py reports no new findings through the declared SHARED-01 own implementation-source note and committed eligible sidecar; the FEAT-CICD-001 catalog record shows a current Status and Last reviewed and 12-PR-ISSUE-TRACEABILITY lists this PR under FEAT-CICD-001"
status: approved
supersedes: docs/superpowers/specs/2026-10-13-feat-cicd-001-complete-generated-inventory.md
---

# Render the declared retry split as a trusted substitution

Status: approved. The owner approved the narrow scope on 2026-11-01 (02:35:06 UTC): admit only the derived retry-split substitutions, keep every independent truth check and the fail-closed rejection of unrelated prose. The owner accepted the six done_when items as written at 78dde0bd on 2026-11-01.

## Problem

`check_generated_docs.gate_derived_numbers` derives the job retry split from `gcp/deploy.sh` and requires 05-a's prose to match it. Its own docstring says such numbers should never be a prose claim anyone keeps in sync. The REQ-GOV-004 render gate accepts a feature branch's 05-a only as main's trusted renderer re-renders it from merge-base prose, and `insert_blocks(counts=True)` owns only `RUNTIME_RELATION_COUNT`, `RELATION_BREAKDOWN` and `ASOF_LABELS`. A declared retry change therefore fails one of the two checks whichever way 05-a line 811 is left.

Observed on the FEAT-DEPLOY-001 news branch (base d806bfd1, source f3206696, probe 44895970): the PR gate refused the computed 46/21 prose ("changes line 811 outside its inventory blocks"), and with main's 43/24 prose, six test_check_generated_docs.py checks failed; main passes 140/140. The EW evaluator retirement (stocks#1658, head 9b076797) hits the same gap from the other side: removing one retries-1 job declares 67 jobs, 43 at retries 0 and 23 at retries 1, and its CI stops at test_committed_docs_pass_every_gate. This is the same contradiction class the predecessor resolved for relation totals and breakdowns. REQ-GOV-004 admits declared job retry-split counts since 27c3c9ec (#1655).

## Non-goals

No deletion, historicizing or rewording of retry counts; no removed or loosened assertion; no owned-FEAT exception; no change to the render-check comparison, `scripts/gate/spec_gate.py` verdict logic, the hook, gate workflows, pinned copies or the committed snapshot; no new document, marker, live input or as-of semantics; no generated-document change in this PR; no retry policy change to any job; no change to the supersedes protocol (separately diagnosed).

## Approaches considered

1. Hand-edit the prose in the feature PR: refused by REQ-GOV-004 and rightly so, since a typed number is what the derived check exists to catch.
2. Remove the counts from the prose: rejected by the owner; it hides a checked fact instead of rendering it.
3. Render the split in the trusted renderer from the declared jobs, as the predecessor did for relation counts. Chosen: the number is computable from the same parse the check already uses, the outside-prose comparison stays fail-closed, and only the exact computed digits can move.

## Design

Retained predecessor contract: the Design, File ownership limits not changed below, Capacity and cost, and Validation and rollout sections of `2026-10-13-feat-cicd-001-complete-generated-inventory.md` remain operative word for word, except that its sentence "Existing substitutions are exactly the unchanged renderer RUNTIME_RELATION_COUNT, RELATION_BREAKDOWN and ASOF_LABELS" becomes "Existing substitutions are exactly the renderer's RUNTIME_RELATION_COUNT, RELATION_BREAKDOWN, ASOF_LABELS and RETRY_SPLIT", and its renderer-unchanged clause admits only the RETRY_SPLIT addition below. Its named bootstrap prerequisites are on main: the requirement-only change #1440 (8322eef3), the source-review policy spec #1461 (ddb1e6d7) and its implementation #1464 (fdbcdaa7, `.claude/skills/product-delivery/SKILL.md`), the source-review verifier spec #1462 (182d444e) and its implementation #1470 (7e5cb49e, `scripts/maintenance/doc_source_snapshot.py`, the producer and verifier generation the SITE note and sidecar use), and the predecessor's own implementation #1538 (a5749d4c). They are not repeated as new gates. The later approved FEAT-CICD-001 specs `2026-10-25-feat-cicd-001-verifier-presence.md` and `2026-10-26-feat-cicd-001-metadata-successor.md` (implementation stocks#1630) have no implementation on main. This spec does not rely on them, does not claim them complete, and leaves their obligations unchanged.

Change: add `RETRY_SPLIT` beside the existing substitutions in `scripts/maintenance/doc_inventory.py`, matching only the two literal shapes on main's 05-a line 811. Rendering replaces `<n>` with `Counter(job["max_retries"])[<k>]` and `<total>` with the declared job count from `repo_inventory`, which is the parse `gate_derived_numbers` counts, defaults included. The flag digit, every other byte and clause order are preserved. Scope is 05-a only. `insert_blocks(counts=True)` applies it; `restore_blocks` keeps `counts=False`, so a model edit after the monthly render is still reported. `check_generated_docs` uses `inv.RETRY_SPLIT` by identity, as it does `ASOF_LABELS`. Other phrasings it parses stay checked and non-owned.

The gate needs no code change: its RENDER_MODE already runs main's `insert_blocks(counts=True)` over merge-base prose. Once this lands, a feature branch that changes a declared retry carries the exact computed split, and nothing else outside the blocks may differ.

## File ownership

scripts/maintenance/doc_inventory.py (RETRY_SPLIT and its application only); scripts/maintenance/check_generated_docs.py (shared-object reuse only); tests/scripts/test_doc_inventory.py; tests/scripts/test_check_generated_docs.py (additions only); tests/scripts/test_spec_gate.py (additions only); the FEAT-CICD-001 catalog and traceability records; one ready plan; the own (FEAT-CICD-001, SHARED-01) implementation-source note and committed sidecar. `.claude/skills/product-delivery/SKILL.md` is not changed: its allowance already reads "only the inventory blocks and existing fixed renderer-owned count/as-of substitutions of `05-a-ARCHITECTURE.md`, `05-c-DATA_DEPENDENCIES.md` and `05-e-API.md` re-rendered by `scripts/maintenance/doc_inventory.py`" (L85, from #1538), as do the gate's refusal messages (`scripts/gate/spec_gate.py` L3883 and L4227), and RETRY_SPLIT is such a substitution of 05-a. The canonical REQ-GOV-004 amendment is on main (27c3c9ec, #1655).

## Capacity and cost

One extra compiled-regex substitution over one in-memory document inside the existing single render; no extra process, file read, git call or snapshot field. Existing 285 s / 600 s / 60 s / 512 MiB ceilings are re-measured unchanged.

## Risks

A broad pattern could rewrite historical or unrelated retry mentions: the literal shapes and the 05-a-only scope, refused by the third done_when item's controls, prevent that. A drift between render and check shapes would re-create the contradiction: the identity assertion catches it. A silent correction of a model's wrong number: restore_blocks keeps counts=False. Sequencing: the predecessor's status-only flip is refused by the current supersedes check on main (probe in the PR description). Main holds only the specification of that repair (a79ac45d, #1653); its gate implementation (stocks#1656) is not on main. This spec's approval and merge with the predecessor retirement wait until that implementation is merged. Merging this spec with the predecessor left approved, or flipping it later in a separate change, is not an authorized procedure.

## Delivery

Three governance stages, as in the predecessor: (1) the requirement-only REQ-GOV-004 change, merged as 27c3c9ec (#1655); (2) this spec alone with the predecessor's retirement; (3) one fix/feat-cicd-001-retry-split-substitution implementation PR carrying its plan.

This PR is stage 2: this spec at `status: approved` and the predecessor's status-only change to `superseded`, which the supersedes-chain gate implementation (stocks#1656, cb136f3e) admits. It gets its own current-head hosted review and CI before it merges, and no exemption from any gate is claimed.

Then stage 3 opens. The red-team allowance is LOCAL-RENDER1, reserved by the owner before stage 3, as the fifth done_when item states. After stage 3 lands, the FEAT-DEPLOY-001 news branch and the EW evaluator retirement base-sync and re-render with `--insert`.
