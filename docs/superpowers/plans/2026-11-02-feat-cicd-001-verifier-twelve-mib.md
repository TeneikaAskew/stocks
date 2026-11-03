---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-02-feat-cicd-001-verifier-twelve-mib.md
branch: feature/feat-cicd-001-verifier-twelve-mib
pr: null
status: ready
---

# SITE source verifier twelve-MiB ceiling implementation plan

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.

**Goal:** raise the verifier's one combined input-byte ceiling from 8,388,608 to 12,582,912 bytes, keep the separate eight-MiB per-file registry limit under its own constant, and change nothing else about what is read, hashed, admitted or refused.

**Spec:** `docs/superpowers/specs/2026-11-02-feat-cicd-001-verifier-twelve-mib.md` (approved, on main since 5f16c96e, #1690).

**Base:** main 1ac70bfd (fast-forwarded from 5f16c96e; none of the three commits between touch a file this plan changes), then main 1fb97576 (#1694) merged in; its appended tests and this plan's appended tests are both kept. One branch, one PR, one author. The SITE row, sidecar, catalog and lineage (Task 9) are shared with #1694 and #1696 and are produced only on the main that exists after those land.

## Global constraints

- No read is removed, deduplicated or trimmed; repeated reads are still charged; the five-second deadline and the 20000-entry ceiling are unchanged; no caller may raise a ceiling.
- No test assertion is removed or weakened. Every over-ceiling control still fails an over-ceiling input.
- The 2026-10-13 protocol spec file is not edited here. Its status-only retirement is a separate docs-only change after this PR lands (spec § Retirement).
- No network, database, provider or deployment call. Nothing under `platform/`, `lib/`, `gcp/` or `.github/workflows/` changes.

## Task 1: combined ceiling and per-file constant
Spec: § Exact change, `doc_source_snapshot.py`. Advances done_when[8].
- [x] `MAX_BYTES = 12582912`; the `Budget` bound and the CLI `--max-input-bytes` default follow it.
- [x] Add `MAX_FILE_BYTES = 8388608` with a comment that it is the per-file limit, not the combined ceiling.

## Task 2: registry per-file check
Spec: § Exact change, `docs_audit.py`. Advances done_when[8].
- [x] The registry size check compares against `protocol.MAX_FILE_BYTES`; its message "registry exceeds the fixed eight-MiB policy-input allowance" is unchanged.

## Task 3: name the constants in existing controls
Spec: § Exact change, tests. Advances done_when[9].
- [x] Each control that hard-codes 8388608 names the constant it means (`MAX_BYTES` for the combined ceiling, `MAX_FILE_BYTES` for the per-file limit); every over-ceiling control still fails.

## Task 4: boundary controls, reproduced on main first
Spec: § Exact change, tests; done_when[9].
- [x] A verify whose actual input totals exactly `MAX_BYTES` is admitted; one byte more is refused with `object exceeds remaining input-byte allowance`.
- [x] `--max-input-bytes` above `MAX_BYTES` is refused.
- [x] A registry of exactly 8388608 bytes passes the audit's per-file check; 8388609 bytes is refused with the eight-MiB message.
- [x] Run each new control against main first (done on main 1ac70bfd) and record which fail or are absent there.

## Task 5: pin the historical approved protocol spec in fixtures
Spec: § Retirement of the 2026-10-13 spec. Keeps done_when[0] to [7] meaningful after the later flip.
- [x] Fixtures write the 2026-10-13 spec bytes as approved on main (blob 2ed20f9d, last changed by 182d444e) from a vendored copy whose Git blob id the suite checks, not the live file.
- [x] A control asserts the live file equals those bytes, or differs only by the status-only flip to `superseded`.
- [x] A control shows the unchanged binding still refuses that spec once it carries the flip in baseline, POLICY and SOURCE.
- [x] Run the full snapshot suite with the live file flipped (local, not committed) and record that it passes.

## Task 6: delivery skill
Spec: § Exact change, SKILL.md. Advances done_when[11].
- [x] `.claude/skills/product-delivery/SKILL.md` shows `--max-input-bytes 12582912`; no other process text changes meaning.

## Task 7: suites
Spec: § Retained done_when items. Advances done_when[0] to [7].
- [x] `tests/scripts/test_doc_source_snapshot.py`, `tests/scripts/test_docs_audit.py` and `tests/scripts/test_spec_gate.py` pass on the head.

## Task 8: capacity measurements
Spec: § Capacity. Advances done_when[10].
- [x] From the unchanged CLI on the head, record `counted_bytes` and `elapsed_seconds` for a main self-check and for the head, each inside the five-second deadline and 20000-entry ceiling: main 1fb97576 under the main module 8,239,011 bytes, 0.76 to 1.23 s; under the head module 8,239,016 bytes, 0.82 to 0.87 s; 1,482 entries each.
- [x] Name by SHA at least one real ref the 8388608-byte ceiling refused with `object exceeds remaining input-byte allowance`, and its result under the new ceiling: #1689's e355e728 against its policy base 1ac70bfd is refused at 5,807,066 counted bytes under 8388608 and identity-matched at 8,468,326 bytes (0.84 to 1.00 s) under 12582912.

## Task 9: source identity and close
Spec: § Source identity and close-out. Advances done_when[12].
- [ ] Update only the `(FEAT-CICD-001, SHARED-01)` row of the SITE Implementation-source notes table with the current `source_identity_sha256=<hash>; ` prefix and prose for this change, keeping its earlier accurate content.
- [ ] Produce the sidecar from the final committed SITE body, commit it, and verify from the committed HEAD under the new ceiling.
- [ ] Registry blob, mode and type equal main's; matched main and branch `docs_audit.py` runs report nothing new.
- [ ] Catalog and PR-traceability records for this PR; `python3 scripts/gate/spec_gate.py --pr origin/main HEAD` with the PR body.
