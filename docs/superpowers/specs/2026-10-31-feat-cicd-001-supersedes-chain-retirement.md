---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-003, REQ-REVIEW-001]
issues: []
canvases: []
done_when:
  - "Retirement admitted (acceptance A1 to A4): tests/scripts/test_spec_gate.py::test_depth_two_retirement_pr_mode_admits_status_only_flip_with_approved_replacement, ::test_depth_two_retirement_commit_mode_admits_status_only_flip (both halves) and ::test_longer_chain_retirement_passes_and_traversal_terminates pass on the implementation and fail on main d806bfd1 with the round-eight message."
  - "Exemption unreachable (B1 to B6): ::test_new_pointer_to_superseded_target_still_refused, ::test_draft_to_approved_with_stale_pointer_refused, ::test_flip_with_changed_pointer_refused, ::test_flip_without_valid_replacement_refused_both_ways and ::test_extra_predecessor_bytes_refused (done_when word, trailing whitespace, CRLF, changed blank line) assert today's messages unchanged on main and on the implementation."
  - "Lineage traversal (B7, B7b, B7c, C6): ::test_inherited_invalid_own_pointer_refused_on_flip, ::test_deeper_inherited_edge_refused (noncanonical, missing, cross-FEAT) and ::test_deleted_ancestor_is_not_read_from_base assert the new messages 'supersedes chain reaches', 'supersedes chain breaks at <node>, which this change deletes' and the cross-FEAT variant beside the existing refusals; each new message is absent on main."
  - "Cycles (B8 to B11b): ::test_supersedes_cycle_refused (self-cycle, two new specs, cycle closed against the base, draft-level cycle) and ::test_simultaneous_draft_edit_cycle_uses_head_value assert 'supersedes chain revisits <node> (cycle)'; every row is red on main, including B11, which main passes today."
  - "Base advance (C1 to C5): ::test_redundant_flip_after_base_advance_gets_merge_main_diagnostic asserts 'already superseded on the current base; merge main so the file leaves this change' (red on main); ::test_pointer_to_target_superseded_after_fork_refused, ::test_merge_of_main_carrying_the_flip_is_not_rechecked and ::test_unchanged_ancestry_is_read_at_the_current_base pass as baseline controls; A1 passes with the divergent-base fixture."
  - "History and plans (A5, A6, A8, B12 to B16): the existing deletion, immutability, born-superseded, depth-one flip and plan-binding tests pass unchanged; ::test_unrelated_draft_edit_beside_retirement_passes and ::test_retirement_leaves_done_plans_unbound_and_untouched pass and show no plan is read or rebound by a docs/ branch retirement."
  - "Bounds and untouched surfaces (D2 to D4): a 60-spec chained fixture completes with look calls at most the distinct spec count on head plus base; --check-spec still calls validate_spec only; the implementation diff leaves .githooks/pre-commit, scripts/gate/pinned/* and both gate workflows byte-identical."
  - "Base suite (D1): the spec-gate workflow's base-suite job, main's tests/scripts/test_spec_gate.py against the proposed spec_gate.py, is green on the implementation PR head, so no message main's suite asserts has changed."
  - "Review contract: the implementation PR records a three-role red-team pass (shell semantics; YAML/Actions structure; exporter and policy documents) on the head it pushed, each reviewer having executed the gate against a concrete snippet, findings fixed in one batch and one push; the #1630 denied reviewer operation is neither retried nor replaced; current-head hosted code review and CI pass before merge."
  - "Records: the FEAT-CICD-001 record in docs/product/02-FEATURE-CATALOG.md and docs/product/12-PR-ISSUE-TRACEABILITY.md identify the implementation PR, and the record states that scripts/gate/ is owned through WORKFLOW_FEAT (spec_gate.py L1096) while the Code row lists .github/workflows/ and the review guidelines; no other capability's row or record changes."
status: draft
supersedes: null
---

# Admit the exact status-only retirement of a spec that itself superseded one, and validate the whole supersedes lineage

## Problem and authorization

An approved spec P that names a predecessor Q (`supersedes: Q`, Q `superseded`) cannot be
retired. The normal retirement edit, written in one change, is: add the replacement N
(`approved`, `supersedes: P`) and flip P's `status:` line from `approved` to `superseded`,
changing nothing else in P. `check_changed_specs` (`scripts/gate/spec_gate.py` L1814 to L1870 on
main d806bfd1) treats the flipped P as a changed spec and re-runs `check_supersedes` on P's
unchanged pointer (L1842 to L1843). `check_supersedes` (L1506 to L1521) refuses at L1519 to
L1520 because P's target Q is already superseded: `supersedes Q, which is already superseded;
name the spec that replaced it (round eight)`. The in-place rule for approved specs (L1850 to
L1864) admits exactly this status-only flip when an approved same-FEAT replacement names P, so
the two checks contradict each other on the one edit the process requires.

Observed, executed: stocks#1649 was refused twice with that message when the FEAT-OPTION-001
source-declaration spec tried to retire `2026-10-25-feat-option-001-realtime-transport.md`
(issue1646 ledger section 4). Measured on main d806bfd1 (minute not retained): 60 specs, 45
approved, 8 superseded, 7 legacy; 10 non-null `supersedes` pointers, all canonical, existing and
same-FEAT; no cycle; no chain longer than one edge; 8 approved heads point at superseded targets
and cannot be retired by the normal edit (FEAT-AUTH-001 signin-hardening-r2, FEAT-DEPLOY-001
retire-prod-service, FEAT-CATALYST-001 av-catalysts-delivery, FEAT-CICD-001
complete-generated-inventory and registry-measured-acceptance, FEAT-DATA-001
av-account-allowance-source-proof and news-log-source-proof, FEAT-OPTION-001
collector-source-declaration); 2 point at approved specs; the 8 retired roots have null pointers.
The round-eight clause entered with stocks#1205 (19bff03a, 2026-09-28); no spec on main carries
it (grep over specs and plans for "already superseded", "round eight" and `check_supersedes`
finds nothing), so this spec has `supersedes: null` and is not itself blocked by the defect.

Why the narrow rule, in plain words: the gate refuses P's pointer because it reads "P names Q,
and Q is already retired" as the author trying to point a new spec at a dead one. That reading is
right for a new or changed pointer. It is wrong for the one edit that retires P, because P's
pointer is history that must not change, and the only thing moving is P's own status. So the
exemption is cut to exactly that edit, and because the gate has never walked beyond the first
edge of a lineage, this spec adds the walk, so that a broken, foreign, deleted or circular
ancestor is refused at every depth instead of never being examined.

Authorization and provenance: the owner approved the narrow governance repair on 2026-10-31 at
15:52:35Z ("Yes but explain it") in answer to the 13:55:51Z question "Do you approve this narrow
governance repair through the normal specification, review and test process? This is separate
from the news documentation-count repair." The approved basis is the Library design
`SUPERSEDES-GATE-DESIGN-rev2.md` (sha256
3b4a5b402832d1c05bf2d96a61ead6f4a9c40404a1b5b07ebbdb1a0aa67c7438) and acceptance plan
`SUPERSEDES-GATE-ACCEPTANCE-PLAN-rev2.md` (sha256
f3e70e1df02363d64532039eaf127420ff6c6600533456c7092dfcdd05a1538f) under
`/mnt/project-files/recovery-2026-10-30/issue1646/review/`. That approval authorizes this spec
through the normal process; it does not approve the separate news retry-count renderer change, a
hosted review trigger, a formal PR approval, ready, merge or deploy, or any gate code before this
spec is approved and on main. This spec adds a narrow gate policy under existing requirements
(REQ-GOV-001, REQ-GOV-003, REQ-REVIEW-001, as `2026-10-26-feat-cicd-001-metadata-successor.md`
did for the previous supersession repair); no requirement amendment is proposed.

## Non-goals

- Skipping `check_supersedes` as a whole for any spec, or skipping canonical-path, existence or
  same-FEAT validation of any pointer.
- Rewriting, relabelling or deleting historical specs, plans or their pointers; migrating the 8
  blocked heads in this change (each owning thread retires its own spec afterwards, as its own
  spec-only change).
- Changing any message that main's `tests/scripts/test_spec_gate.py` asserts; changing
  `.githooks/pre-commit`, either gate workflow or a pinned copy.
- Changing plan binding (L2332 to L2345), deletion refusal (L1826 to L1834), born-superseded
  refusal (L1838 to L1839), the in-place rule (L1850 to L1864) or superseded immutability (L1865
  to L1869).
- Any merge-base read of policy in PR mode; the current-base rule (L4676) stays.
- The news renderer and retry-count proposal (FEAT-CICD-001, separate spec, separate branch).
- Implementing anything here: this spec is documentation; the gate code follows on its own plan
  and `feature/feat-cicd-001-supersedes-chain-retirement` branch after this spec is approved and
  merged.

## Approaches considered

1. Skip the target-status check whenever a changed spec's pointer is unchanged. Too wide: a
   draft approved in place with a stale pointer to a retired spec would land with wrong lineage.
   Rejected.
2. Skip `check_supersedes` entirely on a status flip. Drops path, existence and FEAT validation
   of the flipped spec's own pointer. Outside the approved boundary. Rejected.
3. Exempt only the target-status rejection, only for the exact approved-to-superseded
   status-only unchanged-pointer edit with a valid approved same-FEAT replacement on the head
   tree, and add a bounded traversal of the changed spec's lineage that validates every edge
   (canonical, revisit, existence, same FEAT) reading changed paths at their proposed value and
   unchanged paths at the current base. Chosen: coextensive with what the in-place rule already
   admits, and it closes the unexamined-deeper-edge and cycle gaps.
4. For the traversal, a raw head-first lookup. A path the branch deleted would be read from the
   base and resurrected; a path main changed after the fork would be read from the branch's
   stale copy. Rejected for the changed-set overlay in approach 3.
5. For a flip that main already made after the fork (branch copy byte-identical to the current
   base's superseded copy): admit as a no-op. A second exemption for a state that merging main
   removes. Rejected for a fail-closed refusal with a merge-main diagnostic.
6. A repository-wide lineage audit on every run. Not needed: the traversal is per changed spec
   and bounded to its lineage.

## Design

Line anchors are main d806bfd1. For every changed spec S in `check_changed_specs` with a head
text (not deleted, not legacy):

1. `validate_spec` runs as today.
2. Own-pointer validation always runs when `supersedes` is non-null: canonical normalized path
   under `docs/superpowers/specs/`, target readable on `ch.base` (the current base tip in PR
   mode; HEAD or MERGE_HEAD in commit mode), same `feat_id` (L1512 to L1518, same messages). New
   specs, changed pointers, draft to approved and every other edit keep steps 2 and 3 in full.
3. The target-status rejection (L1519 to L1520) is skipped only when all of these hold, with
   `base_text = ch.base.read(S)`: `base_text` is not None and its status is `approved`; the head
   status is `superseded`; the base and head `supersedes` values are equal; `strip(text) ==
   strip(base_text)` with the L1855 lambda (`re.sub(r"^status:.*$", "", t, flags=re.M)`), so the
   only byte change is the `status:` line; and the head tree holds a spec other than S with
   `status: approved`, the same `feat_id` and `supersedes == S` (the L1859 to L1864 condition).
   Otherwise step 3 runs as today. `check_supersedes` gains a keyword
   `allow_superseded_target=False` and returns `[]` in place of the round-eight error only when
   it is True and every other check passed.
4. Affected-lineage traversal, new, with overlay semantics. `look(path)`: if `path in
   ch.changed`, the value is the proposed one, `ch.tree.read(path)` (staged content in commit
   mode, the head commit in PR mode), and None means this change deletes the path, which the
   traversal refuses and never reads from the base; otherwise the value is `ch.base.read(path)`,
   the current base tip in PR mode, HEAD or MERGE_HEAD in commit mode. For S with a non-null
   pointer: `visited = [S]; node = fm["supersedes"]`, then loop: canonical path
   (`isinstance(node, str) and node == posixpath.normpath(node) and
   node.startswith("docs/superpowers/specs/")`, else `"{S}: supersedes chain reaches {node!r},
   which is not written as docs/superpowers/specs/<file>.md"`); revisit (`node in visited`, else
   `"{S}: supersedes chain revisits {node} (cycle)"`); existence (`look(node)` None, else `"{S}:
   supersedes chain breaks at {node}, which {'this change deletes' if node in ch.changed else
   'is not a spec on the base'}"`); same FEAT (`"{S}: supersedes chain reaches {node}, a spec for
   {that}, not {S's}"`); then `visited.append(node); node = frontmatter(node_text).get(
   "supersedes")`, stopping when `node` is None. Target status is never examined in the
   traversal, so the legitimate flip passes it. The walk is bounded: at most one `look` per
   distinct node, and `len(visited)` cannot exceed the number of distinct spec paths in
   `ch.tree.list(SPECS)` union `ch.base.list(SPECS)`. A cycle introduced by a change must contain
   a changed edge and the traversal starts at every changed spec, so a self-cycle, a two-spec
   cycle written in one change, a cycle closed against an unchanged base spec and a cycle formed
   by editing a draft node's pointer in the same change are all found from a changed spec.
5. Redundant flip after base advance, fail-closed: when `base_text` is not None, its status is
   `superseded` and `text == base_text`, refuse `"{S}: already superseded on the current base;
   merge main so the file leaves this change"`. Today this state is refused with the round-eight
   message, which misdirects.
6. Everything else is unchanged byte for byte.

Edit site, L1842 to L1843, plus two helpers and hoisting `base_text` from L1850:

```
base_text = ch.base.read(path); fm, base_fm = frontmatter(text), frontmatter(base_text)
strip = lambda t: re.sub(r"^status:.*$", "", t, flags=re.M)
if base_text is not None and base_fm.get("status") == "superseded" and text == base_text:
    errs.append(f"{path}: already superseded on the current base; merge main so the file leaves this change")
flip = (base_text is not None and base_fm.get("status") == "approved" and fm.get("status") == "superseded"
        and base_fm.get("supersedes") == fm.get("supersedes") and strip(text) == strip(base_text)
        and any((n := frontmatter(ch.tree.read(s))).get("supersedes") == path and n.get("status") == "approved"
                and n.get("feat_id") == fm.get("feat_id") for s in ch.tree.list(SPECS) if s != path))
errs += validate_spec(...) + check_supersedes(fm, path, ch.base, allow_superseded_target=flip) + check_chain(fm, path, ch)
```

`check_chain(fm, path, ch)` is step 4; `look` is a closure over `ch.changed`, `ch.tree` and
`ch.base`.

### Mode and base-advance behaviour

- BA1, PR mode, redundant flip: refused by step 5 with the merge-main diagnostic.
- BA2, PR mode: the branch adds N naming P; after the fork P was superseded on main by N2. N's
  pointer is new and P is superseded at the current base, so round eight refuses, correctly.
- BA3, commit mode with a merge of main in progress: `against = MERGE_HEAD` (L4647); a P already
  flipped on main equals the staged P, so P is not in `changed` and is not re-checked.
- BA4, commit mode, plain commit: `ch.base = Tree(HEAD)`; N committed earlier and P flipped now,
  or N and P in one commit, both satisfy step 3.
- BA5, unchanged ancestry advanced on main: draft D names approved Q at the fork; main then
  retires Q; the branch approves D in place. `look(Q)` reads the current base where Q is
  superseded; step 3 does not apply (D's base status is draft), so round eight refuses,
  correctly. A merge-base read would have admitted D with a stale pointer.
- Plans: no plan is read for a `docs/` branch; plans on the base that cite P are not in
  `changed`, are not re-validated and are not rebound. A later `feature/` or `fix/` branch whose
  plan names P is refused by L2344, today and after. Nothing rebinds a done plan.
- Historical files: deleting Q or P stays refused (L1826 to L1834), and a flip whose chain passes
  through a deleted Q is also refused at the chain; editing a superseded spec stays refused
  (L1865 to L1869).

### Acceptance fixtures (tests/scripts/test_spec_gate.py)

Fixtures `spec(**over)` (L100, default `approved`, FEAT-MODEL-001), `write` (L152), `_git`
(L140), `gate` (L209), `on_base` (L221), `pr` (L239), `base_and_head` (L3894). Lineage: Q =
`SPEC` on base, superseded; P = `2026-09-02-model-decisions-v2.md`, approved, supersedes Q; N =
`2026-09-03-model-decisions-v3.md`, new on the branch, approved, supersedes P; R for depth three;
D for a draft node. Divergent-base fixture, after L1976 to L1985: cut the branch from `base`,
commit, record `head`; advance main and move the `base` tag; run `gate(repo, "--pr", <base>,
head, PR_HEAD_REF=branch)`, so the recorded head keeps the old merge base while policy is read at
the advanced tip. The `done_when` items above enumerate the planned tests by name; the companion
acceptance plan's tables A to E give each case's fixture, mode, today's behaviour read from
source, the designed behaviour and the asserted message. Every new refusal uses a new message;
no message main's suite asserts changes.

### Ownership, sequence and review roles

- Owner FEAT: FEAT-CICD-001. `scripts/gate/spec_gate.py` and `tests/scripts/test_spec_gate.py`
  are process files (`is_process_file` L1102 to L1107, `SUITE` L1110); a change to them on
  another FEAT's branch is refused at L4694 to L4697. The gate claims `scripts/gate/` through
  `WORKFLOW_FEAT` (L1096) while the catalog Code row lists `.github/workflows/` and the review
  guidelines; the implementation PR's catalog record states that gap (done_when 10).
- Sequence: this spec, `status: draft`, alone on
  `docs/spec-feat-cicd-001-supersedes-chain-retirement`, presented in sections; the owner says
  approved; `status: approved`; current-head hosted code review and CI; merge. Then one ready
  plan and one `feature/feat-cicd-001-supersedes-chain-retirement` branch (a gate behaviour
  change is code with a plan, as #1585 and #1597 were); the red-team pass before the one push;
  draft PR; hosted code review on the head; CI including `base-suite`; two-round cap;
  conversation resolution; merge. Only then do the 8 blocked flips proceed in their owning
  threads, each as its own spec-only change. No stacking.
- Review roles, read from the contract: a gate-file change gets three parallel red-team
  reviewers, one each for shell semantics, YAML/Actions structure, and the exporter and policy
  documents (`.claude/skills/product-delivery/SKILL.md` L66; CLAUDE.md L12). The four-role pass is
  a done_when item of `2026-10-13-feat-cicd-001-complete-generated-inventory.md` (L14), scoped to
  renderer and diff-byte parsing, which this change does not touch (`RENDERER_FILES` L82), so the
  three-role contract applies and the fourth role is not inherited.
- The #1630 exporter and policy reviewer operation remains denied; this spec dispatches no
  reviewer and does not retry, replace or route around it. Staffing that role for the
  implementation PR is the owner's decision at that time.
- Coordination with the news renderer proposal (also FEAT-CICD-001): it plans no `spec_gate.py`
  edit and its new spec must supersede `2026-10-13-feat-cicd-001-complete-generated-inventory.md`,
  one of the 8 blocked heads, so this repair lands first and that flip follows on its own branch.
  The only shared file is `tests/scripts/test_spec_gate.py`, each change adding its own tests;
  the second to land rebases its additions. `spec_gate.py` is this change's alone.

## Risks

- A wider exemption than intended. Caught by done_when 2: every near-miss (new pointer, changed
  pointer, draft approved with a stale pointer, flip without a valid replacement, any extra byte
  in P) must still be refused with today's messages.
- The traversal resurrecting a deleted ancestor or reading stale lineage. Caught by done_when 3
  and 5 (deletion read from the head, unchanged ancestry read at the current base, redundant
  flip refused with the merge-main message).
- A cycle or deeper bad edge admitted. Caught by done_when 3 and 4, each red on main.
- An existing asserted message changing, which would break every open branch's pre-commit hook.
  Caught by done_when 8 (`base-suite`) and by the new-message rule.
- Unbounded traversal. Caught by done_when 7.
- Capacity (CLAUDE.md rule 0): no workload runs differently; the gate runs locally and in CI
  and performs at most one tree read per distinct spec in a changed spec's lineage.

## Separation of evidence

Observed and executed: the two #1649 refusals; the graph measurement on main d806bfd1. Read from
source, not executed: every line anchor above. Planned, not run: every acceptance case; the
proposed code does not exist. Still to run on the implementation: the `base-suite` job and the
red-team pass. Not checked: behaviour of the proposed code on any input.

## Status

Spec-only draft published from main d806bfd1 for the owner's section-by-section admission
(SKILL.md L40), which is the merge gate; `status: approved` is set only after that admission. No
gate code, plan, hook, workflow or pinned copy changes in this PR.
