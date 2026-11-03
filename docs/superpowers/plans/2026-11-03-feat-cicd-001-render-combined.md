---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-13-feat-cicd-001-complete-generated-inventory.md
branch: fix/feat-cicd-001-render-combined
pr: null
status: ready
---

# Inventory render measurement: meet the approved 512 MiB contract on the real tree

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.

**Goal:** done_when 13 of the approved spec requires `python3 tests/scripts/measure_inventory_render.py --ref HEAD --max-rss-mib 512 --max-seconds 60` to run the committed-tree trusted gate renderer within 512 MiB and 60 seconds, and the test suite to exercise accepted and refusal controls at that contract. On main 1fb97576 both fail:

- The real-tree measurement fails `rss_limit` at about 537 MB under Python 3.14.6 and 3.13, and under 3.12 it passes or fails by the run. The cause is in the gate's `materialize`: it read the whole `git cat-file --batch` output into memory (406 MiB peak) and held about 181 MiB of it through the render, while the renderer's own AST cache holds about 200 MiB.
- The accepted fixture control runs at `--max-rss-mib 128`, a value no spec defines. Python 3.14's larger interpreter baseline reaches it on identical inputs (the ubuntu-latest 26.04 failures on #1673 and #1696).
- A measurement whose worker family is killed leaves its `spec-gate-render-*` tree behind in the shared temporary directory. The 47 such trees under /tmp, which no record ties to an owner, are how this was found. They are not touched by this change.

**Spec:** `docs/superpowers/specs/2026-10-13-feat-cicd-001-complete-generated-inventory.md` (approved, unchanged): done_when 13 (the contract and its controls), done_when 2 (exact render: bytes, refused paths), done_when 6 (suites), done_when 7 (four-seat red-team pass), done_when 9 and 10 (records). No new spec: product-delivery Phase 1.4, the approved spec covers this.

**Base:** main 1fb97576. One branch, one PR, one author. This plan replaces the unpublished fixture-only plan of fix/feat-cicd-001-render-fixture-512 (6e98401f, never pushed), whose one-token test change is carried here unchanged.

## Global constraints

- Changed source: `scripts/gate/spec_gate.py` (`materialize` only), `tests/scripts/measure_inventory_render.py`, `tests/scripts/test_spec_gate.py`. Both gate workflows, their pinned copies, the hook and `.gitattributes` stay byte-identical to main.
- Unchanged: the CLI default and maximum of 512 MiB and 60 seconds, the 513/61/nan/0/true rejections, the 1 MiB real refusal and 96 MiB-at-64 MiB allocation controls, time-limit group reaping, path containment, exact materialized bytes, and every aggregate and per-file proof budget.
- No OS pin, no Python selection in a workflow, no production cap change, no workflow timeout change.
- No hook bypass and no history rewrite. The gate-file red-team pass runs on the frozen candidate before the one push.
- The operation refused on stocks#1630 is not retried, replaced or routed around. No temporary tree outside this change's own fresh roots is deleted.

## Task 1: stream the materialized tree (spec_gate.py)
Spec: done_when 13 (contract), done_when 2 (exact render).
- [x] `materialize` streams `git cat-file --batch` output to each file in chunks of at most 1 MiB. It checks each header's object id, type and line end, every blob's length and the separator after it, and the batch's exit status, and raises GitFailed on any mismatch. Path containment is checked for every entry before anything is written, as before.
- [x] `test_materialize_streams_exact_bytes_one_blob_at_a_time`: blob sizes 0, 1, 1 MiB-1, 1 MiB, 1 MiB+1 and 3 MiB+7 bytes of binary with newlines arrive byte for byte; a missing object raises GitFailed; one 32 MiB blob grows a fresh process's VmHWM by less than 8 MiB (measured 2,236 KiB streamed against 65,744 KiB buffered). Its work directories are the test's own `tmp_path`, and the 32 MiB output is removed after its size is asserted.

## Task 2: the monitor owns its scratch root (measure_inventory_render.py)
Spec: done_when 13 ("without weakening hook/CLI assertions").
- [x] The monitor creates a private scratch root, passes it to the worker family as TMPDIR, and records a CREATED-BY receipt in it. The receipt is attribution only, never proof that descendants are gone after a monitor kill.
- [x] The monitor holds the parent and the root by descriptor, checks the root's identity before clearing, before removing the receipt and before the final `rmdir(name, dir_fd=parent)`, clears without following links, and bounds the removal by the measurement deadline.
- [x] It retains the root, and reports why (root_not_held, spawn_children_unknown, spawn_not_registered, family_not_proven_reaped, removal_deadline, removal_failed), whenever it cannot prove the family reaped or the root unchanged.
- [x] Residual limit, stated in the PR: a same-user swap inside the single system call between the last identity check and the final rmdir is not excluded.

## Task 3: the accepted fixture uses the contract
Spec: done_when 13.
- [x] `test_measure_inventory_render_runs_the_actual_gate`: the accepted control's `'--max-rss-mib', '128'` becomes `'512'`. No other assertion of that test changes.

## Task 4: suites, controls and the real tree
Spec: done_when 6 and 13.
- [x] Focused controls and mutants for Tasks 1 to 3 on Python 3.12.3, 3.13.17 and 3.14.6.
- [ ] `tests/scripts/test_spec_gate.py` passes in full on the frozen head under 3.12.3, 3.13.17 and 3.14.6, serial, each run behind a free-space preflight.
- [x] One real-tree measurement per interpreter on 0d497d03 (the head's runtime): completed within 512 MiB and 60 seconds, renderer exit 0 with no refusals, family reaped and scratch root removed.

## Task 5: gate-file red-team pass
Spec: done_when 7, plus the CLAUDE.md gate-file rule.
- [ ] One four-seat pass on the frozen head and body: shell; YAML/Actions; exporter and policy documents; diff and byte parsing together with the render check. Each finding is proven by running the gate or the measurement against a concrete snippet. Seats share one read-only checkout; file-creating controls run one at a time behind a free-space preflight; no seat runs a full-tree measurement.
- [ ] Earlier judgments stay counted and are listed in the PR with their findings: RENDER512-RT1 (one four-seat nonempty pass on the fixture-only head 6e98401f), IND1 (one seat on 588d94af) and IND2 (one seat on 1761997f), each spent and nonempty.

## Task 6: source identity, records and close
Spec: done_when 9 and 10.
- [x] Update only the `(FEAT-CICD-001, SHARED-01)` SITE note row with the current source hash and prose for this change, keeping its earlier accurate content. Produce and commit the sidecar from the final committed body, and verify from the committed HEAD.
- [ ] Full default `docs_audit.py` on main and on the head: nothing new on the head.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` with the PR body.
- [ ] At Ready, one records commit only: this plan's `pr`, the catalog's FEAT-CICD-001 Last reviewed (the commit's date) and record note, and the PR in the 12-PR-ISSUE-TRACEABILITY lineage. It touches no gate file, mode or `.gitattributes`.
- [ ] Natural CI on the head, with no rerun of unchanged CI. Review and merge follow the repository's rules; no provider exception is assumed.
