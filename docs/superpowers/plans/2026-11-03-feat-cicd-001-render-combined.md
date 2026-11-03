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

- The real-tree measurement fails `rss_limit` at about 537 MB under Python 3.14.6; under 3.13.17 and 3.12.3 it passes or fails by the run (3.13.17 completed at 534,167,552 B on 6e98401f and 534,278,144 B on main in RENDER512-RT1 seat R1, and failed in seats R2 and R3). The cause is in the gate's `materialize`: it read the whole `git cat-file --batch` output into memory (406 MiB peak) and held about 181 MiB of it through the render, while the renderer's own AST cache holds about 200 MiB.
- The accepted fixture control runs at `--max-rss-mib 128`, a value no spec defines. Python 3.14's larger interpreter baseline reaches it on identical inputs (the ubuntu-latest 26.04 failures on #1673 and #1696).
- A measurement whose worker family is killed leaves its `spec-gate-render-*` tree behind in the shared temporary directory. The 47 such trees under /tmp, which no record ties to an owner, are how this was found. They are not touched by this change.

**Spec:** `docs/superpowers/specs/2026-10-13-feat-cicd-001-complete-generated-inventory.md` (approved, unchanged): done_when 13 (the contract and its controls), done_when 2 (exact render: bytes, refused paths), done_when 6 (suites), done_when 7 (four-seat red-team pass), done_when 9 and 10 (records). No new spec: product-delivery Phase 1.4, the approved spec covers this.

**Base:** main 1fb97576. One branch, one PR, one author. This plan replaces the unpublished fixture-only plan of fix/feat-cicd-001-render-fixture-512 (6e98401f, never pushed), whose one-token test change is carried here unchanged.

## Global constraints

- Changed source: `scripts/gate/spec_gate.py` (`materialize` only), `tests/scripts/measure_inventory_render.py`, `tests/scripts/test_spec_gate.py`. Both gate workflows, their pinned copies, the hook and `.gitattributes` stay byte-identical to main.
- Unchanged: the CLI default and maximum of 512 MiB and 60 seconds, the 513/61/nan/0/true rejections, the refusal controls (a 96 MiB allocation refused at a 64 MiB limit, and the 1 MiB runs, whose refusal comes from the monitor's own RSS before any worker starts), time-limit group reaping, path containment, exact materialized bytes, and every aggregate and per-file proof budget.
- No OS pin, no Python selection in a workflow, no production cap change, no workflow timeout change.
- No hook bypass and no history rewrite. The gate-file red-team pass runs on the frozen candidate before the one push.
- The operation refused on stocks#1630 is not retried, replaced or routed around. No temporary tree outside this change's own fresh roots is deleted.

## Task 1: stream the materialized tree (spec_gate.py)
Spec: done_when 13 (contract), done_when 2 (exact render).
- [x] `materialize` streams `git cat-file --batch` output to each file in chunks of at most 1 MiB. It checks each header's object id, type, line end and plain decimal size, every blob's length and the separator after it, that nothing follows the last object, and the batch's exit status, and raises GitFailed on any mismatch. A wrong answer is refused with its path and object id before git is ended, so a broken pipe never replaces the cause; an answer that ends early reports git's own exit status when it is nonzero. The pipe from git is closed explicitly on every path. Path containment is checked for every entry before anything is written, as before.
- [x] `test_materialize_streams_exact_bytes_one_blob_at_a_time`: blob sizes 0, 1, 1 MiB-1, 1 MiB, 1 MiB+1 and 3 MiB+7 bytes of binary with newlines arrive byte for byte; a missing object raises GitFailed; one 32 MiB blob grows a fresh process's VmHWM by less than 8 MiB (measured 2,236 KiB streamed against 65,744 KiB buffered). Its work directories are the test's own `tmp_path`, and the 32 MiB output is removed after its size is asserted.
- [x] `test_materialize_names_the_refused_entry_and_checks_every_field`: with real git, a missing object and a tree object, each followed by a 256 KiB blob, are refused naming their path and object id; a stand-in `git` on PATH gives one case per check (short read, header without its line end, another type, another object id, no separator, nonzero exit after a complete answer, a size that is not a plain decimal in four forms, output after the last object), each refused with GitFailed naming what it refuses; four early ends (no answer, inside the header, inside the blob, before the separator) report git's exit status 128 and its stderr; a wrong separator and trailing output, each with 256 KiB still to write, are named before git is ended. The real-git cases run in a separate process with a 60 s limit, so a wait-before-kill regression fails instead of hanging the suite (QUAL2 R4 F1, F2). The stand-in writes its pending output one write after another until done, so a write after the gate closed the pipe reports the broken pipe (real git dies of SIGPIPE there, rc -13; the stand-in exits 141 only because Python ignores SIGPIPE, and no assertion depends on which; QUAL3 R4 F1): with one buffered write, measured on 3.12.3, 3.13.17 and 3.14.6, a pipe closed during the write left the stand-in exiting 0, and a gate that closed the pipe before naming the wrong separator still passed (mutant X3a, 2026-11-03).

## Task 2: the monitor owns its scratch root (measure_inventory_render.py)
Spec: done_when 13 ("without weakening hook/CLI assertions").
- [x] The monitor creates a private scratch root, passes it to the worker family as TMPDIR, and records a CREATED-BY receipt in it. The receipt is attribution only, never proof that descendants are gone after a monitor kill.
- [x] The monitor holds the parent and the root by descriptor, checks the root's identity before clearing, before removing the receipt and before the final `rmdir(name, dir_fd=parent)`, clears without following links, and bounds the removal by the measurement deadline.
- [x] It retains the root, and reports why (root_not_held, spawn_children_unknown, spawn_not_registered, family_not_proven_reaped, removal_deadline, removal_failed), whenever it cannot prove the family reaped or the root unchanged.
- [x] Residual limit, stated in the PR: a same-user swap inside the single system call between the last identity check and the final rmdir is not excluded.
- [x] A child Popen forked but never returned (an interrupt after fork) is killed through a PIDfd checked against its listed start ticks and reaped within the deadline; the monitor's direct children are then listed again, and the root is removed only if none remain, otherwise retained as spawn_not_registered with the killed and remaining children in the receipt. On that path no report prints, so stderr names each killed child and any retained root.
- [x] (C2, QUAL2 R1 F1 and F2) The kill and relist repeat within the same deadline, so a descendant adopted from a killed child is reaped by the same identity-checked PIDfd kill; they stop when no child remains, when a pass kills nothing or at the deadline. A child that cannot be identified is never signalled: it stays in the receipt, the root is kept, and stderr names it as not proven killed. Stderr notices are written last, after the receipt, the removal and the subreaper restore, and a stderr write failure never replaces the interrupt. Controls: the grandchild, unidentified-child and unwritable-stderr cases of `keeps_a_scratch_root_it_cannot_prove_free`. Shown failing on 8a3cdee6 (grandchild, unwritable stderr, and the unidentified child's notice) and passing on the C2 head; mutants C1 to C3 killed.
- [x] (FIX3, QUAL3 R1 F1, R1 F2 and R3 F3) The first identity-checked kill pass runs even when the interrupt arrives after the deadline; the deadline bounds only reaping and further passes. The root is kept whenever any child remains, and each remaining child is named on stderr with its reason (identity unverified, signal refused, signalled but not reaped by the deadline, not examined before the deadline), built before the receipt write so a failed write cannot silence it; the retained-root notice carries the cleanup error. Controls: `test_measure_inventory_render_signals_and_names_every_unregistered_child` (late interrupt, refused signal, unidentified child with a broken receipt) and the reason in the unidentified-child case.
- [x] The receipt is opened with O_NONBLOCK and must be a regular file, as `regular_output` already requires; a failed final rmdir appends a removal_failed event before the error propagates.

## Task 3: the accepted fixture uses the contract
Spec: done_when 13.
- [x] `test_measure_inventory_render_runs_the_actual_gate`: the accepted control's `'--max-rss-mib', '128'` becomes `'512'`. No other assertion of that test changes.
- [x] What this gives up, stated in the PR as open: the accepted control no longer detects fixture memory growth between about 134 MB and 512 MiB (a renderer holding 300 MiB more passes at 512 and fails at 128, RENDER-COMBINED-QUAL1 R3 F1; RENDER512-RT1 R4 F1 and F4), and no CI job runs the real-tree measurement. A baseline-relative control is not added: the spec defines no such cap.

## Task 4: suites, controls and the real tree
Spec: done_when 6 and 13.
- [x] For the 8a3cdee6 corrections: focused controls on Python 3.12.3, 3.13.17 and 3.14.6 (all three on the working tree committed as 2c5931e3, before that commit), mutants on 3.14.6 only, and the new controls shown failing first on f07e96cc (and on main where the check exists there), except `kills_only_the_listed_identity_and_writes_only_a_regular_receipt`, which was not run on f07e96cc: its start-tick half is proven by a mutant only, and its FIFO-with-a-reader half, behavior that existed on f07e96cc, by the regular-file mutant only.
- [x] For C2: the grandchild, unwritable-stderr and unidentified-child (its notice) cases shown failing on 8a3cdee6; the six stand-in git cases and the timed real-git half, whose behaviour 8a3cdee6 already has, shown passing there (also with the corrected stand-in) and failing under the mutants that break it; focused controls on 3.14.6, and through the full suite on the three interpreters; nine mutants on 3.14.6 (X5a, X5b, X5c, X3a, X4c, X5d, C1, C2, C3), all killed, X5d by the real-git runner's 60 s limit. X3a first survived; the stand-in correction in Task 1 is what kills it.
- [x] `tests/scripts/test_spec_gate.py` passes in full on the frozen source under 3.12.3, 3.13.17 and 3.14.6, serial, each run behind a free-space preflight: 192 passed in 435.98 s, 435.60 s and 446.04 s, on the working tree whose source and test bytes are the C2 source commit (the suite reads neither this plan nor the SITE row). `tests/scripts/test_export_model_registry.py`: 41 passed on each.
- [x] One real-tree measurement per interpreter on 0d497d03: completed within 512 MiB and 60 seconds, renderer exit 0 with no refusals, family reaped and scratch root removed. The correction commit changes `materialize`, which that measurement runs, so these receipts are for 0d497d03, not the corrected head; whether a real-tree run on the corrected head is required is decided at its frozen checkpoint.
- [x] One real-tree measurement per interpreter on the C2 frozen head 3465479b (13:26:29Z to 13:28:46Z): completed within 512 MiB and 60 seconds, renderer exit 0 with no refusals, family reaped and scratch root removed.
- [x] For FIX3: the late-interrupt, refused-signal and broken-receipt cases, and the unidentified-child reason, shown failing on 3465479b's source, passing on the FIX3 source, and eight mutants (F1, F2, F3a, F3b, F3c, C2, C1, C3) killed, 3.14.6. Focused 27 plus 1 passed on 3.14.6; tests/scripts/test_spec_gate.py in full, serial: 193 passed on d17f7a42 in 473.93 s (3.14.6), 440.69 s (3.13.17) and 453.71 s (3.12.3), each over 285 s and the 360 s registry cap; test_export_model_registry.py 41 passed on each.
- [ ] One real-tree measurement on the FIX3 head: 512 MiB and 60 seconds, serial, behind the 918 MiB free-space preflight plus 16 MiB reserve. Blocked while free space is below 979,369,984 B; no deletion is authorized to make room.

## Task 5: gate-file red-team pass
Spec: done_when 7, plus the CLAUDE.md gate-file rule.
- [x] One four-seat pass on the frozen head and body: shell; YAML/Actions; exporter and policy documents; diff and byte parsing together with the render check. RENDER-COMBINED-QUAL1 ran once on f07e96cc: nonempty, no P1, 3 P2 and 10 P3, corrected in 2c5931e3 and 505bb52c. RENDER-COMBINED-QUAL2 ran once on 8a3cdee6: nonempty, no P1, no P2, 10 P3 (8 distinct), corrected in C2.
- [x] RENDER-COMBINED-QUAL3 ran once on the C2 frozen head 3465479b and body 03dfad92: nonempty, 0 P1, 0 P2, 7 P3, corrected in FIX3.
- [ ] The next qualification of the FIX3 head, as the owner decides (none is started automatically), finds nothing. Seats share one read-only checkout; file-creating controls run one at a time behind a free-space preflight; no seat runs a full-tree measurement.
- [ ] Earlier judgments stay counted and are listed in the PR with their findings and the test that refuses each: RENDER512-RT1 (one four-seat nonempty pass on the fixture-only head 6e98401f), IND1 (one seat on 588d94af), IND2 (one seat on 1761997f), RENDER-COMBINED-QUAL1 (four seats on f07e96cc), RENDER-COMBINED-QUAL2 (four seats on 8a3cdee6) and RENDER-COMBINED-QUAL3 (four seats on 3465479b), each spent and nonempty.

## Task 6: source identity, records and close
Spec: done_when 9 and 10.
- [x] Update only the `(FEAT-CICD-001, SHARED-01)` SITE note row with the current source hash and prose for this change, keeping its earlier accurate content. Produce and commit the sidecar from the final committed body, and verify from the committed HEAD.
- [ ] Full default `docs_audit.py` on main and on the head: nothing new on the head.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` with the PR body.
- [ ] At Ready, one records commit only: this plan's `pr` and the ticks of Tasks 4 to 6 that the PR body's receipts support, the catalog's FEAT-CICD-001 Last reviewed (the commit's date) and record note, and the PR in the 12-PR-ISSUE-TRACEABILITY lineage. It touches no gate file, mode or `.gitattributes`.
- [ ] Natural CI on the head, with no rerun of unchanged CI. Review and merge follow the repository's rules; no provider exception is assumed.
