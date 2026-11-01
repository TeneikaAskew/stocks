---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-31-feat-cicd-001-supersedes-chain-retirement.md
branch: feature/feat-cicd-001-supersedes-chain-retirement
pr: 1656
status: ready
---

# Supersedes chain retirement implementation plan

> For agentic workers: use superpowers:executing-plans. One author, one branch, one PR. Every task cites a spec
> section and the done_when item it advances (zero-based indices into the spec's `done_when` list).

## Binding and sequence

The spec landed on main as a79ac45dcb82dccaa2933defe6096108f9316af8 (stocks#1653, squash of 68aec5ed; file sha256
57b02d0b671a81389b66531d24ced0a8324ff7acda0c3e4429845f4bab7fdf6d). This branch is cut from that commit. Line anchors
below are main d806bfd1, which the spec uses; a79ac45d adds one spec file and changes no gate line, so the anchors hold.

Files this branch changes: `scripts/gate/spec_gate.py` (the edit site at L1842 to L1843, two helpers, the hoisted
`base_text`), `tests/scripts/test_spec_gate.py` (new tests appended; no existing test or asserted message changes), this
plan, and in the close task the owned FEAT-CICD-001 catalog record and traceability entry. Nothing else: no hook, no
workflow, no pinned copy, no renderer file, no other capability's row.

Push discipline (spec, Ownership, sequence and review roles; SKILL.md L66): the plan is pushed alone first and the draft
PR opened on it, then the plan's `pr` binding is committed and pushed (both pushes change no gate file). The gate and
test change is pushed exactly once, after the three-role red-team pass on that head comes back empty. No hosted review
is requested by this plan; the Ready transition and merge wait for the owner's merge authorization.

Review reservation (reported to the owner before any reviewer is dispatched; AGENTS.md review budget): a new cohort
owned by this branch, with its own target (the local code head of `feature/feat-cicd-001-supersedes-chain-retirement`,
named by SHA when it exists) and its own scope (the `scripts/gate/spec_gate.py` edit at L1842 to L1843 with its two
helpers, and the appended tests, under the landed #1653 contract). One red-team pass of three parallel reviewers on that
head, one each for shell semantics, YAML/Actions structure, and the exporter and policy documents, each required to
prove a bypass by executing the gate against a concrete snippet; repeated only until a pass comes back empty, findings
fixed in one batch between passes; counts recorded per pass on the PR. The stopped operation on stocks#1630 (the
exporter and policy seat for LOCAL3 on frozen a58c7172, covering metadata-field and pin checks, the prior registry and
that PR's gate and verifier controls, stopped by a tool-policy flag before any review result; #1630 comment 6485122675)
is excluded from this cohort: no reviewer here reviews #1630, a58c7172 or the metadata successor work, and this cohort
is not a retry, rephrasing, rerouting or substitute for that seat. The exporter and policy seat here is staffed only
under the owner's own recorded authorization on this PR; if its invocation is flagged, the pass stops and the owner is
told, with no alternate reviewer or route. Hosted code review on the pushed head: 0 of 2 rounds used.

## Task 1: bind the plan and open the draft PR
Spec: § Ownership, sequence and review roles. Advances done_when[9] (the records name the implementation PR).
- [ ] `python3 scripts/gate/spec_gate.py --commit` on the staged plan, then commit the plan alone (hook runs the gate).
- [ ] Push `feature/feat-cicd-001-supersedes-chain-retirement` (plan only) and open the draft PR titled
      `FEAT-CICD-001: admit status-only retirement of a superseding spec and validate the supersedes lineage`, body with
      the spec and plan paths, every done_when item as an unticked `- [ ]` line, and the Capacity section.
- [ ] Commit `pr: <number>` in this plan and push (plan only; no gate file changed yet).

## Task 2: fixture lineage and the divergent-base helper
Spec: § Acceptance fixtures. Advances done_when[0].
- [ ] In `tests/scripts/test_spec_gate.py`, add module-level names for the lineage: `P_SPEC`
      (`docs/superpowers/specs/2026-09-02-model-decisions-v2.md`), `N_SPEC` (`2026-09-03-model-decisions-v3.md`),
      `R_SPEC` (depth three) and `D_SPEC` (a draft node), plus a helper `retirement_lineage(repo)` that puts Q (`SPEC`,
      superseded) and P (approved, `supersedes: Q`) on the base with `on_base`.
- [ ] Add `divergent_pr(repo, branch, branch_files, main_files, **env)` following the existing shape at L1976 to L1985:
      cut the branch from `base`, commit the branch files, record the head, advance main with `on_base(main_files)`, then
      `gate(repo, "--pr", <base sha>, head, PR_HEAD_REF=branch)`.
- [ ] Run `python3 -m pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest -k retirement` (expect
      collection only; no new test yet).

## Task 3: admission tests, red on main
Spec: § Design steps 3 and 4; § Acceptance fixtures (A1 to A4). Advances done_when[0].
- [ ] Write `test_depth_two_retirement_pr_mode_admits_status_only_flip_with_approved_replacement` (A1: N added and P
      flipped status-only in one PR; also with the divergent fixture, C4),
      `test_depth_two_retirement_commit_mode_admits_status_only_flip` (A2 one commit; A3 N committed first, then the
      flip) and `test_longer_chain_retirement_passes_and_traversal_terminates` (A4: R superseded null, Q superseded
      names R, P approved names Q, N added, P flipped).
- [ ] Run them against main's gate (the repo fixture copies the checkout's `scripts/gate/spec_gate.py`): expect FAIL,
      each with the round-eight message `which is already superseded; name the spec that replaced it (round eight)`.

## Task 4: the exemption is unreachable, green on main
Spec: § Design steps 2 and 3; § Risks (a wider exemption). Advances done_when[1].
- [ ] Write `test_new_pointer_to_superseded_target_still_refused` (B1, B2),
      `test_draft_to_approved_with_stale_pointer_refused` (B3), `test_flip_with_changed_pointer_refused` (B4),
      `test_flip_without_valid_replacement_refused_both_ways` (B5: no N, N draft, N another FEAT) and
      `test_extra_predecessor_bytes_refused` (B6: a done_when word, trailing whitespace, CRLF, a changed blank line),
      each asserting today's message text. Executed against main a79ac45d: `Tree.read` reads through `git(...)` in
      text mode, which folds CRLF, so the CRLF variant is byte-equal to the base as the gate reads it and the in-place
      rule never sees it; main refuses it with round eight alone. B6 therefore asserts round eight for all four
      variants and the in-place message for the other three; the spec's design step 3 ("the only byte change is the
      `status:` line") does not hold for CRLF, and Task 10 closes that with a bytes conjunct in `flip`.
- [ ] Run against main's gate: expect PASS (baseline controls).

## Task 5: lineage traversal tests
Spec: § Design step 4; § Mode and base-advance behaviour (historical files). Advances done_when[2].
- [ ] Write `test_inherited_invalid_own_pointer_refused_on_flip` (B7: P's own pointer missing, `./docs/...`, cross-FEAT;
      asserts today's L1512 to L1518 messages), `test_deeper_inherited_edge_refused` (B7b: Q's pointer noncanonical,
      missing R, FEAT-DATA-001 R; asserts the three new chain messages) and
      `test_deleted_ancestor_is_not_read_from_base` (B7c and C6: flip P beside N and delete Q; asserts
      `supersedes chain breaks at <Q>, which this change deletes` beside the existing `is not deleted`).
- [ ] Run against main's gate: B7 PASS; B7b and B7c FAIL on the absent chain messages.

## Task 6: cycle tests
Spec: § Design step 4 (revisit). Advances done_when[3].
- [ ] Write `test_supersedes_cycle_refused` (B8 self-cycle, B9 two new specs, B10 closed against the base, B11 draft
      level) and `test_simultaneous_draft_edit_cycle_uses_head_value` (B11b), each asserting
      `supersedes chain revisits <node> (cycle)`.
- [ ] Run against main's gate: every row FAIL (B11 passes the gate on main today; the test asserts the refusal).

## Task 7: base-advance tests
Spec: § Design step 5; § Mode and base-advance behaviour (BA1 to BA5). Advances done_when[4].
- [ ] Write `test_redundant_flip_after_base_advance_gets_merge_main_diagnostic` (C1: asserts
      `already superseded on the current base; merge main so the file leaves this change` beside the round-eight
      message), `test_pointer_to_target_superseded_after_fork_refused` (C2),
      `test_merge_of_main_carrying_the_flip_is_not_rechecked` (C3: `git merge --no-commit main`, then `--commit`) and
      `test_unchanged_ancestry_is_read_at_the_current_base` (C5).
- [ ] Run against main's gate: C1 FAIL (new message); C2, C3, C5 PASS (baseline controls).

## Task 8: history and plan regression guards
Spec: § Non-goals; § Mode and base-advance behaviour (plans). Advances done_when[5].
- [ ] Write `test_unrelated_draft_edit_beside_retirement_passes` (A8) and
      `test_retirement_leaves_done_plans_unbound_and_untouched` (B15: a done plan on the base cites P; a docs/ branch
      retirement produces no plan output).
- [ ] Confirm the existing deletion, immutability, born-superseded, depth-one flip and plan-binding tests (L560 to L575,
      L933 to L949, L401 to L420) are not edited by this branch (`git diff origin/main -- tests/scripts/test_spec_gate.py`
      shows additions only).

## Task 9: bound and untouched surfaces
Spec: § Design step 4 (bound); § Non-goals; § Capacity. Advances done_when[6].
- [ ] Write `test_traversal_bound_on_sixty_chained_specs`: sixty chained specs on the base; load the gate module with
      `load_gate` and count `Tree.read` calls made by `check_chain` for the changed spec; assert the count is at most the
      number of distinct spec paths in the union of head and base spec lists, and that the gate run completes.
- [ ] Assert in the same test module that `--check-spec` on a spec with a pointer prints `spec ok` without any chain
      message (the path calls `validate_spec` only).
- [ ] In the PR body, record `git diff origin/main --stat` showing `.githooks/pre-commit`, `scripts/gate/pinned/*`,
      `.github/workflows/spec-gate.yml` and `registry-check.yml` absent from the diff.

## Task 10: implement the narrow rule
Spec: § Design steps 1 to 6 and the edit-site pseudocode. Advances done_when[0], done_when[1], done_when[2],
done_when[3], done_when[4].
- [ ] `check_supersedes(fm, name, base, *, allow_superseded_target=False)`: unchanged path, existence and same-FEAT
      checks; return `[]` instead of the round-eight error only when the keyword is True and every other check passed.
- [ ] `check_chain(fm, path, ch)`: `look` closure over `ch.changed`, `ch.tree`, `ch.base` (a changed path reads the
      proposed value and None means deleted; an unchanged path reads the current base); walk `visited = [path]`,
      `node = fm.get("supersedes")`, refusing noncanonical, revisit, missing or deleted, and cross-FEAT nodes with the
      spec's exact message texts; never examine target status.
- [ ] At L1842 to L1843: hoist `base_text = ch.base.read(path)`; add the step 5 diagnostic; compute `flip` with the
      five conditions (base approved, head superseded, equal pointer, `strip` equality, approved same-FEAT replacement on
      the head tree) plus one the Task 4 run showed necessary: `strip_bytes(ch.tree.raw(path)) ==
      strip_bytes(ch.base.raw(path))` with `strip_bytes = re.sub(rb"^status:[^\r\n]*", b"", ...)`, so a relabel that
      rewrote the line endings is not a flip (spec done_when L8, B6 CRLF; the spec's step 3 text folds CRLF without
      saying so). This only narrows the exemption (replaced after IMPL-CICD2 by the position-preserving
      `status_entry` conjunct, below). Call `validate_spec(...) + check_supersedes(...,
      allow_superseded_target=flip) + check_chain(...)`. Reuse the hoisted `base_text` at L1850 and the hoisted
      `strip` lambda (main's L1855) in the in-place block, whose only two differences from L1850 to L1869 are those two
      removed lines; keep it otherwise byte-identical.
- [ ] Corrections after the IMPL-CICD1 pass on 8814e1c1, each reproduced there and compared with main a79ac45d's
      gate before the fix, each with one test (`test_crlf_relabel_of_a_superseded_spec_is_not_called_redundant`,
      `test_cr_only_line_endings_take_the_flip_and_refuse_extra_bytes`,
      `test_nul_byte_in_an_inherited_pointer_is_refused_not_a_traceback`):
      R1 F1 (P1): the step 5 diagnostic is decided on `ch.tree.raw(path) == ch.base.raw(path)`, not `text ==
      base_text` as the spec's pseudocode writes it, because a superseded spec relabelled LF to CRLF reads text-equal
      while its bytes differ, so it stays in the change after a merge of main and "merge main so the file leaves
      this change" was false (8814e1c1 refused it with that message; main admitted a null-pointer relabel and
      refused one naming a superseded spec by round eight alone; after the fix the gate does what main does).
      R1 F3 (P2): `check_chain` refuses a node containing a NUL byte as not written canonically, with the step 4
      message, instead of handing it to `git show` (uncaught ValueError, traceback, no verdict; main admitted the
      change because it never read the inherited edge). R1 F2 (P2): `strip_bytes` anchors on the start of the
      bytes or after any CR or LF, so a CR-only spec takes the same flip (round eight had refused it), and the
      status-stripped text and bytes of one are judged as an LF file's are (a done_when word is refused in place and
      by round eight; a relabel to LF by round eight; superseded after IMPL-CICD2, below). The three edits only remove a false message, a
      traceback and a false refusal; nothing the spec enumerates as refused is admitted.
- [ ] Corrections after the IMPL-CICD2 pass on 29314273 (R1 F1, R1 F2; and pass 1's R3 P2-2 and R1 F4, which
      pass 1 recorded as a prose gap and pass 2 showed to be an admission), scope settled by the owner 2026-11-01.
      The spec's step 3 sentence "so the only byte change is the `status:` line" and its Risks entry ("any extra
      byte in P must still be refused with today's messages") are stronger than the L1855 lambda step 3 names, which
      blanks every physical line beginning `status:`, while `frontmatter` splits that line on every separator
      `str.splitlines` knows. Executed on 29314273: `status: superseded\x0cissues: [4242]` (and the U+2028 form)
      read as two keys and rode the flip at depth two (rc 0; main refuses it by round eight), so a flip could change
      metadata; a body line beginning `status:` rewritten inside the flip, or moved between two blank lines, was
      admitted the same way. The code keeps the spec's `strip` equality and replaces the bytes conjunct with one
      that is position-preserving: `status_entry` finds the one physical line holding the frontmatter `status`
      entry the way `frontmatter` finds it (opening `---`, closing line starting `---`, unindented key `status`),
      returns None if the bytes are not UTF-8, if `status` is keyed on more than one line, or if that line holds a
      `str.splitlines` separator; the flip then requires every byte before and after that line to be equal in base
      and head. A check on the status lines' values alone was tried first (scratch candidate, not committed) and
      lost position: it admitted a body `status:` line moved between blank lines, and refused quoted and spaced
      values the parser reads. Refused by round eight now, as `test_flip_changes_only_the_status_entry_and_hides_no_key`
      asserts: a key hidden on the entry line (form feed, U+2028), a trailing separator on it, a rewritten or moved
      body `status:` line, a CRLF relabel. Admitted: the canonical flip on LF, CRLF-kept and CR-only files at depth
      two and three; quoted-to-quoted, plain-to-quoted, spaced and commented values on the entry alone, which the
      parser reads as today; an unchanged body `status:` line. `status : approved` (space before the colon) stays
      refused, by the spec's own lambda (`^status:.*$` does not blank it) and by the in-place rule, on main too.
      At a79ac45d (this branch's base) 61 spec files, 54 with a status line, carry exactly `status: approved` (46) or
      `status: superseded` (8); at ca043892 (main when this was measured) 64 files, 57 with a status line, 48 and 9;
      neither has a body `status:` line or a CR byte. The in-place rule, `frontmatter`, the hook, the pinned copies and the workflows are untouched: at
      depth one the hidden key is still admitted through the in-place rule on this gate as on main (the test's last
      case). So the exemption is a subset of what the in-place rule admits, narrower by at least these edit shapes,
      each admitted at depth one on main and refused here at depth two (IMPL-CICD3 R1 and R3, executed): a CRLF
      relabel, a key hidden on the entry line, a separator alone at the end of that line, a rewritten, moved or
      inserted body `status:` line, any non-UTF-8 byte in the file even if unchanged, and a frontmatter whose second
      line starts `---` (`status_entry` takes it as the closing line; `frontmatter` reads on). The "coextensive"
      sentences of step 3 and Approaches 3 are not literally true for those shapes. done_when 2 holds: its four
      enumerated byte changes sit outside the status entry and are refused. The Risks bullet "any extra byte in P
      must still be refused" holds only read as "any byte outside the frontmatter status entry": read literally it
      is exceeded by the safe forms the owner's settled scope keeps on the entry line, which the code admits at depth
      two where main refuses them (plain to quoted, an added comment, added trailing whitespace on that line). That
      Risks sentence is the one spec clause those forms conflict with; the merged spec is not edited.
      Known and recorded after IMPL-CICD3, not changed in this head: the step 5 mode conjunct compares the head's mode
      with the current base's, so when main (not the branch) flipped P and changed its mode, the true "merge main"
      advice is dropped and round eight alone is printed (fail-closed, rc unchanged; IMPL-CICD3 R1 F1, P2); the
      `status_entry` docstring's "the way `frontmatter` finds it" does not hold for a second line starting `---`
      (IMPL-CICD3 R3 P3-2), which fails closed as above.
      R1 F1 (P2): the step 5 diagnostic also requires `ch.tree.mode(path) == ch.base.mode(path)`, because a mode
      change alone (100644 to 100755, bytes identical) keeps a superseded spec in the change after a merge of main,
      so "merge main so the file leaves this change" was false (29314273 printed it beside round eight; main prints
      round eight alone); `test_mode_only_change_of_a_superseded_spec_is_not_called_redundant`.
- [ ] Run the tests from Tasks 3 to 9: all PASS. Run Task 4's tests again: still PASS with today's messages.

## Task 11: suites and gates, locally
Spec: § Design (D1 base suite); § Separation of evidence. Advances done_when[7].
- [ ] `python3 -m pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest` on the branch: all PASS.
- [ ] Base-suite simulation as `.github/workflows/spec-gate.yml` L80 to L100 runs it: a checkout of main a79ac45d with
      the branch's `scripts/gate/spec_gate.py` copied in, then main's `tests/scripts/test_spec_gate.py` and
      `tests/scripts/test_export_model_registry.py` with the same flags: all PASS (no asserted message changed).
- [ ] `python3 scripts/gate/spec_gate.py --commit` before each commit (the hook runs it too); after the last commit,
      `python3 scripts/gate/spec_gate.py --pr origin/main` prints `spec gate ok`.
- [ ] Record each command and result in the PR body's Verification section.

## Task 12: red-team pass, then the one code push
Spec: § Ownership, sequence and review roles (review roles; the #1630 invocation). Advances done_when[8].
- [ ] Report the exact reservation to the owner before dispatch: one pass, three reviewers (shell semantics;
      YAML/Actions structure; exporter and policy documents), each executing the gate against a concrete snippet; the
      exporter and policy seat staffed only under the owner's own recorded authorization on this PR, which is not a retry,
      replacement or rerouting of the #1630 invocation. Dispatch nothing until the owner records it.
- [ ] Run the pass on the local head; fix every confirmed finding in one batch; run the pass again; repeat until a pass
      comes back empty.
- [ ] Push once. Record on the PR the head SHA reviewed, the three roles, each reviewer's snippet and verdict, and the
      owner's authorization for the exporter and policy seat. CI (gate, base-suite, registry, tests) must be green on that
      head; hosted code review on it is recorded truthfully (requested only when the owner says so; unavailable is written
      as unavailable, never as completed).

## Task 13: close
Spec: § Done when (done_when 10); § Ownership, sequence and review roles (the WORKFLOW_FEAT gap). Advances done_when[9].
- [ ] `docs/product/02-FEATURE-CATALOG.md`, FEAT-CICD-001 record only: Status and Last reviewed updated; the record
      states that `scripts/gate/` is owned through the gate's `WORKFLOW_FEAT` constant while the Code row lists
      `.github/workflows/` and the review guidelines; the Code row text itself is not changed.
- [ ] `docs/product/12-PR-ISSUE-TRACEABILITY.md`: add this PR under FEAT-CICD-001. No other row or record changes.
- [ ] `python3 scripts/maintenance/docs_audit.py` on the branch and on `origin/main`: no finding the branch adds.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`: `spec gate ok`.
- [ ] Tick every done_when box in the PR body with its evidence; the Ready transition and the merge wait for the owner's
      explicit authorization (two-round review cap; no stacking; the 8 blocked flips proceed only after this merges, each
      in its owning thread).
