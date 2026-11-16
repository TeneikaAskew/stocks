---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-REVIEW-001]
issues: []
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "`scripts/maintenance/doc_source_snapshot.py` sets `MAX_BYTES = 16777216`, and the `Budget` bound and the CLI `--max-input-bytes` default follow it; `MAX_FILE_BYTES = 8388608` and the audit's per-file registry check are unchanged. Nothing else about what is read, hashed, admitted or refused changes: no read is removed, deduplicated or trimmed, repeated reads are still charged, and the five-second deadline and 20000-entry ceiling are unchanged."
  - "In `tests/scripts/test_doc_source_snapshot.py` the pin of the approved ceiling reads `assert MAX_BYTES == 16777216`, recorded failing on main and passing on the head; the existing control that a verify whose actual input totals exactly `MAX_BYTES` is admitted and one byte more is refused with the reason `object exceeds remaining input-byte allowance` passes at the new ceiling; no other test, case or assertion changes, and `tests/scripts/test_doc_source_snapshot.py` and `tests/scripts/test_docs_audit.py` pass in full on the head."
  - "The implementation PR records, from the unchanged CLI on its head, `counted_bytes` and `elapsed_seconds` for a main self-check and for the head, each inside the unchanged five-second deadline and 20000-entry ceiling, and names by SHA at least one real ref that the 12582912-byte ceiling refused with the reason `object exceeds remaining input-byte allowance`, with its result under the new ceiling (identity-matched, or a refusal for a different stated reason)."
  - "`.claude/skills/product-delivery/SKILL.md` shows the verify command with `--max-input-bytes 16777216`; no other process document changes its meaning."
  - "Source identity (SHARED-01): on the implementation PR head the existing producer and verifier, run from the committed HEAD with its fixed ceilings, prove committed source and SITE body identity bound to this approved spec at the actual merge base, where its blob equals the one on current main; the plan binds this spec; the only SITE change is the FEAT-CICD-001 / SHARED-01 row of the Implementation-source notes table with the prefix source_identity_sha256=<current source hash> and nonempty prose describing this change and its tests while keeping the earlier accurate own content of that row; the sidecar is produced from the final committed SITE body and committed; the matched main and branch `scripts/maintenance/docs_audit.py` runs report no finding that main does not; the registry `docs/DOC_REGISTRY.md` blob, mode and type equal main's; the required current-head checks pass before merge under the repository's existing review rules, which this spec does not extend."
status: approved
supersedes: null
---

# SITE source verifier: sixteen-MiB aggregate input ceiling

## What changes and why

The SITE source verifier (`scripts/maintenance/doc_source_snapshot.py`) charges every byte it reads
against one combined ceiling, `MAX_BYTES`, set to 12,582,912 bytes (12 MiB) by
`2026-11-02-feat-cicd-001-verifier-twelve-mib.md` (#1690, implemented in #1699). Its largest read
is every spec blob on main, which grows with each merged spec. That spec's Capacity section asked
that a main self-check with under 1 MiB of headroom go to the owner. Measured on main c57009f6
(2026-11-16): a main self-check counts 12,223,076 bytes (0.74 s), leaving about 323 KB once the
audit's registry debit is taken off.

A branch that edits `docs/product/03-SITE-TRACEABILITY.md` reads that 1.09 MB document at both refs,
so it needs more than main does. #1968's head 56168a1d (the Part A live stage, which edits only its
own SHARED-01 row) is refused with `object exceeds remaining input-byte allowance` at 7,014,924 bytes
used, while the spec blobs (6,089,118 bytes over 183 specs) are still to be read; `docs_audit.py`
then reports `implementation-source identity unavailable` and two `changed-since` fallbacks on the
SITE document. Every FEAT PR that updates its SITE note row now hits the same refusal.

This spec moves `MAX_BYTES` to 16,777,216 bytes (16 MiB). Nothing about what is read changes.

Owner decision: on 2026-11-16 at 17:11:37Z the owner answered "Yes" to "Should I raise the source
check limit to 16 MiB in a small PR with a short spec? It's a one-line change in code."

## Experiment (main c57009f6, before this spec)

With only `MAX_BYTES = 16777216` changed in a scratch copy and nothing committed:

| Ref | Ceiling | Result | counted_bytes | elapsed_seconds |
|---|---|---|---|---|
| main c57009f6 self-check | 12582912 | identity-matched | 12,223,076 | 0.74 |
| #1968 head 56168a1d | 12582912 | refused, `object exceeds remaining input-byte allowance` | (stops at 7,014,924 used) | n/a |
| #1968 head 56168a1d | 16777216 | identity-matched, route declared-note | 13,108,532 | 0.77 (three runs 0.65 to 0.77) |

The implementation PR repeats these from its own head (done_when 3).

## Relation to the twelve-MiB spec

This spec amends one number of `2026-11-02-feat-cicd-001-verifier-twelve-mib.md` and does not
supersede it. That spec stays `approved` and unedited: the verifier binds it as `CLOSEOUT_SPEC` for
the DOC-only close-out route, and `tests/scripts/test_doc_source_snapshot.py` builds fixtures from its
live bytes as `SUCCESSOR_SPEC`, so flipping it to `superseded` would break both (that spec's own
Retirement section measured the same effect on its predecessor). Where its done_when items 6, 9, 10
and 12 name the twelve-MiB value (`12582912`, "combined twelve-MiB"), this spec's value governs from
the implementation PR's merge on; every other item of that spec stands as written.

## Exact change the implementation makes

- `scripts/maintenance/doc_source_snapshot.py`: `MAX_BYTES = 16777216`. The `Budget` check
  `0 < max_bytes <= MAX_BYTES` and the CLI default for `--max-input-bytes` already follow the
  constant. `MAX_FILE_BYTES = 8388608` stays.
- `tests/scripts/test_doc_source_snapshot.py`: `assert MAX_BYTES == 12582912` becomes
  `assert MAX_BYTES == 16777216`. Every other control already derives its padding from `MAX_BYTES`
  or `MAX_FILE_BYTES`.
- `.claude/skills/product-delivery/SKILL.md` L100: `--max-input-bytes 16777216`.
- The plan, the FEAT-CICD-001 catalog and lineage records, the SHARED-01 note row and its sidecar.
- Nothing else in what the verifier or the audit reads, hashes, admits or refuses changes.

## Capacity (CLAUDE.md rule 0)

- Volume: 12,223,076 bytes for a main self-check and 13,108,532 bytes for a branch that edits the
  SITE document, measured above; the ceiling bounds one verify at 16,777,216 bytes.
- Velocity: 1 verify per docs audit, local or CI; no network calls, no database, no scheduled job.
- Wall-clock: 0.65 to 0.77 seconds measured above under the unchanged five-second deadline.
- Runway (estimate, not checked): 16 MiB less the measured branch need leaves about 3.6 MB, roughly
  five weeks at the twelve-MiB spec's measured spec growth (about 690 KB a week). The same manual
  revisit applies: if 16,777,216 - 36,852 - a main self-check's `counted_bytes` is under 1 MiB, that
  goes to the owner as a FEAT-CICD-001 capacity question.
- Cost: 0 new resources or services.

## Durable alternative, not in scope

Two changes would stop the ceiling tracking spec growth: reading only spec frontmatter in the
supersession scan, or charging a blob read once when both refs hold the same blob. Each reads or
charges less than today, so each needs its own owner decision. This spec does neither.

## Source identity and close-out

Declaration `[SHARED-01]`: only the `(FEAT-CICD-001, SHARED-01)` row of the Implementation-source
notes table may describe this implementation and its tests, composed from the row then on main,
keeping earlier accurate own content, with a recomputed hash; every other SITE byte stays.
Pre-merge, as done_when 5 says. Post-merge (not pre-merge boxes): plan `status: done` on a `docs/`
branch.

Review: `doc_source_snapshot.py` is not under `scripts/gate/`, so the existing rules ask no red-team
pass; this spec adds no review obligation.

## Rollback

Revert the implementation PR. A branch that then needs more than 12 MiB is refused again with the
same reason; nothing else depends on the larger value.
