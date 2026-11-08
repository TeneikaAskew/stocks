---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-004]
issues: [1372]
site_source_notes: [SHARED-01]
canvases: []
done_when:
  - "tests/scripts/test_spec_gate.py asserts, on a fixture tree holding scripts/maintenance/, the GCP snapshot and only the four files the three documents' blocks render from (platform/api/main.py, gcp/deploy.sh, gcp/schema.sql, scripts/discord/register_commands.py), that a feature or fix branch passes the PR-mode gate when it inserts four lines near the top of platform/api/main.py, as #1366 did, and its only other change under docs/product/, besides its own catalog and traceability records, is the inventory blocks of docs/product/infrastructure/05-a-ARCHITECTURE.md, 05-c-DATA_DEPENDENCIES.md and 05-e-API.md re-rendered by scripts/maintenance/doc_inventory.py"
  - "tests/scripts/test_spec_gate.py asserts that the PR-mode gate refuses each of these with a message citing REQ-GOV-004, and accepts a control that differs from it only in the condition under test: a changed byte outside every inventory block body and the existing fixed renderer-owned count/as-of substitutions in one of the three documents; a marker line added, removed, moved, renamed, re-spaced or repeated, or a line matching the marker pattern whose name is not one of that document's expected blocks; a CRLF line ending added inside a block body; a NUL, U+0085, U+2028 or U+2029 inside a block body that comes from the fixture tree's own rendered text (a route path), so that only the clean-bytes rule refuses it; a block body that differs from what main's doc_inventory.py renders from the pull request's committed blobs (a hand-edited row); a .gitattributes in the head tree that would change a file's bytes on export (export-subst, eol, ident); a symbolic link or submodule anywhere in the head tree; a head-tree path with an empty, '.', '..' or '.git' component; a render that opens a file outside the materialized tree (a job entrypoint given as an absolute path to a file the test creates outside it); one of the three documents deleted, renamed or given another file mode; and a block change in a pull request that also changes scripts/maintenance/doc_inventory.py, scripts/maintenance/check_generated_docs.py, tests/scripts/test_check_generated_docs.py or tests/fixtures/live_gcp_snapshot_2026-09-07.json"
  - "tests/scripts/test_spec_gate.py asserts that changed_lines reads the diff as bytes and reports a changed content line that begins with '---', '+++', '--' or '++', a line holding a lone carriage return, and a line after a U+2028 within the same line; that a binary or hunkless diff of a changed path raises instead of returning no lines; that feat_span and section_of read the blob's raw bytes and number lines by '\\n' only; that added_lines, which has no caller, is gone; and that the catalog scope check therefore refuses each of: a removed '---' line in another capability's record, a NUL in the branch's own Status line alongside an edit to another record, and U+2028 characters or lone carriage returns in the branch's own record alongside lines added to another record"
  - "tests/scripts/test_spec_gate.py asserts that the gate's three document paths equal MARKER_DOCS in scripts/maintenance/check_generated_docs.py, that its snapshot path equals SNAPSHOT in tests/scripts/test_check_generated_docs.py, that the gate imports scripts/maintenance only when one of the three documents changes, and that a checkout without scripts/maintenance/ (solyra's) refuses a change to them as today rather than failing"
  - "is_process_file covers scripts/maintenance/doc_inventory.py, scripts/maintenance/check_generated_docs.py, scripts/maintenance/__init__.py and tests/fixtures/live_gcp_snapshot_2026-09-07.json, so a change to any of them needs a FEAT-CICD-001 branch, and tests/scripts/test_spec_gate.py asserts it"
  - "Each new assertion is shown failing against the gate on origin/main when the PR opens; tests/scripts/test_spec_gate.py passes in full on the PR head, and the base-suite job, main's suite run against the new gate, is green within its 10-minute limit"
  - "Before the PR's one push, a red-team pass ran with four reviewers: shell, YAML/Actions, the exporter and policy documents, and the diff and byte parsing together with the render check. Each finding is proven by running the gate on a concrete snippet; the last pass found nothing, and every earlier finding is listed in the PR with the test that now refuses it"
  - "The refusal message for other docs/product/ paths in check_product_scope and the 'Never' list in .claude/skills/product-delivery/SKILL.md name the exact re-rendered inventory blocks and existing renderer-owned count/as-of substitutions as allowed changes and cite REQ-GOV-004"
  - "python3 scripts/gate/spec_gate.py --pr origin/main passes on the PR head, and actual branch/main docs_audit.py reports no new findings using the previously merged source-review verifier, this approved SHARED-01 declaration, genuinely changed source-bound own implementation note and committed eligible sidecar; no watcher or historical marker is changed"
  - "The FEAT-CICD-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists this PR under FEAT-CICD-001"
  - "tests/scripts/test_spec_gate.py runs the unchanged trusted renderer with merge-base document prose and committed head source inputs, accepts exact runtime-relation totals, declared table/materialized-view/view breakdowns and existing fixed snapshot as-of substitutions, and refuses wrong counts, arbitrary neighboring prose, altered historical dates, forged marker-prefix rows and new count/as-of patterns; real-gate refused cases have accepted controls."
  - "tests/scripts/test_spec_gate.py proves scripts/__init__.py and scripts/maintenance/__init__.py are FEAT-CICD-001 process inputs and rejects changes to either alongside generated documents; a concrete trusted-base startup regression cannot introduce a verdict-changing initializer through an unrelated feature branch, and no head code is imported or executed."
  - "The complete unchanged hosted registry-check / registry job on the PR's exact head passes every test and the unchanged exporter, with all required actual hook/CLI assertions preserved, in at most 335 seconds whole job, which leaves at least 25 seconds of reserve under the 360 second six-minute limit and stays the bound if a longer live limit lands first; every hosted attempt on that head is recorded with its exact head, pytest and whole-job times, no retry selects a favourable sample, and the earlier 285 second pytest target is recorded as UNMET, not certified. The unchanged BASE suite completes within600seconds, and python3 tests/scripts/measure_inventory_render.py --ref HEAD --max-rss-mib 512 --max-seconds 60 runs the actual committed-tree trusted gate renderer, fails on an observed total process-tree-plus-monitor RSS above512MiB or elapsed time above60seconds, records source bytes and actual sampling gaps/kernel child peak, and exercises accepted and actual memory/time refusal controls without weakening hook/CLI assertions; no workflow timeout or pinned-file changes are permitted."
status: approved
supersedes: docs/superpowers/specs/2026-10-13-feat-cicd-001-complete-generated-inventory.md
---

# Complete generated inventory: whole-job registry acceptance

## Authority

The owner approved this decision on 2026-11-04. The question offered the reconciliation "the full job must finish within 335 seconds of its six-minute limit, leaving at least 25 seconds spare" and asked whether the yes covered the Stocks timing-specification change; the owner answered "Both". The relayed instruction at 13:33:32Z directs this immutable-spec successor route and keeps every correctness, memory, trust, security, failure-path and review obligation. This spec records that decision. It is not a finding waiver, an additional review round for #1700, or a rollout.

## Problem

`docs/superpowers/specs/2026-10-13-feat-cicd-001-complete-generated-inventory.md` done_when item 13 begins: "The unchanged registry-workflow equivalent full suite completes below285seconds". PR #1538 met it at 284.137 s with 144 tests. The suite has since grown: on #1700's published head 946d94d2, the hosted registry job ran 215 tests with pytest at 306.51 s and a whole job of 327 s, under the 360 second limit, with every hosted check passing. Item 13 cannot be ticked truthfully, and the gate judges #1700's plan against this spec because no approved spec names it in `supersedes`.

The later registry specs already moved off a pytest allocation, but none of them names this spec. `2026-10-25-feat-cicd-001-registry-measured-acceptance.md` binds the whole job at 335 s or less with at least 25 s reserve under 360 s, and records 285 s as UNMET at 288.72 s. `2026-11-02-feat-cicd-001-registry-ten-minute-envelope.md` says the old 285 second pytest ceiling is not carried forward as an acceptance limit.

## Non-goals

- No change to any workflow, timeout, pinned file, gate, exporter, renderer, snapshot, test, assertion or runtime safety threshold. The live registry limit stays six minutes. The ten-minute envelope proceeds only through its own specs and stages.
- No change to the BASE 600 s limit, the renderer 60 s / 512 MiB command and controls, the verifier limits, the two-round review cap or any review budget.
- No speed claim. No rerun to find a favourable sample.
- No change to any other capability's acceptance. The approved, still unimplemented `2026-10-13-feat-cicd-001-capacity-cost-label.md` and `2026-10-13-feat-cicd-001-capacity-fixture-bridge.md` keep their own 285 second clauses for their own future work.
- The SKILL text and citing plans are not edited here (see "Citing texts").

## Approaches considered

1. Make the suite fit 285 s again. The owner paused speculative timing work; the measured candidates are unpushed and unreviewed, and a hosted runner varies by tens of seconds.
2. Raise the cap. Out of scope: workflow and pinned-file changes are excluded, and the ten-minute envelope has its own staged route.
3. Chosen: a successor that replaces only the first clause of item 13 with the whole-job acceptance the six-minute envelope already uses (at most 335 s, at least 25 s reserve under 360 s). It measures the same whole-job duration bounded by CI's unchanged 360-second timeout, adds the approved 25-second reserve as a 335-second specification acceptance ceiling, keeps every other obligation, and matches the six-minute registry acceptance.

## Design

The done_when list is the predecessor's list, item for item. Items 1 to 12 are byte-identical. In item 13 only the first clause changes, from:

> The unchanged registry-workflow equivalent full suite completes below285seconds with all required actual hook/CLI assertions preserved,

to the whole-job acceptance in this spec's item 13. That acceptance:
- requires the complete unchanged hosted `registry-check / registry` job on the PR's exact head to pass every test and the unchanged exporter in at most 335 s;
- records every attempt;
- records the 285 s pytest target as UNMET, not certified.

The rest of item 13 is unchanged: BASE within 600 s, the real-tree `measure_inventory_render.py --ref HEAD --max-rss-mib 512 --max-seconds 60` command with its accepted and refusal controls, and "no workflow timeout or pinned-file changes are permitted". The 335 s bound stays binding even if a longer live limit lands first, so the ten-minute stage cannot loosen this capability's acceptance.

The predecessor's sections "Design", "File ownership", "Capacity and cost", "Validation and rollout" and "Lawful source-documentation delivery prerequisite" apply word for word. The one exception is the Capacity sentence "The actual full registry equivalent must be below285seconds of its unchanged300second cap", which is replaced by item 13's whole-job acceptance above. The predecessor stays on main, unchanged except its status-only move to `superseded` in the same PR as this spec. That is the gate's one permitted edit of an approved spec, and the procedure #1594 and #1683 used. Its approved body is the record that #1538 and its plan cite.

## Citing texts and their routes

| Text | What it says | Route |
|---|---|---|
| `.claude/skills/product-delivery/SKILL.md` line 111 | "renderer60second/512MiB and registry285second contracts remain unchanged" | It is gate-tracked (LOCAL_SKILLS), so it changes only through a FEAT-CICD-001 fix PR with its own plan. A PR bound to this spec must tick every item here, so that edit needs its own small stage spec, as `2026-11-02-feat-cicd-001-registry-ten-minute-pin.md` did. Proposed wording: "renderer60second/512MiB contracts and the registry acceptance of the current approved specs remain unchanged". That spec is drafted after this one lands and is approved separately. Until then, this spec and the ten-minute envelope spec are the later approved statements of the inventory capability's and the registry job's acceptance. |
| `docs/superpowers/specs/2026-10-13-feat-cicd-001-source-review-policy.md` line 73 | the same sentence | Approved and immutable. It states that the policy change left those contracts unchanged, which stays true of that change. Not edited or superseded. |
| `docs/superpowers/plans/2026-10-18-feat-cicd-001-complete-generated-inventory.md` | binds the predecessor; records 285 s | Delivered history: #1538 merged 2026-10-23 with item 13 met at 284.137 s. A plan on main keeps its spec, so it is not re-pointed. Its frontmatter still reads `ready`; that is a separate records question, not changed here. |
| `docs/superpowers/plans/2026-11-03-feat-cicd-001-render-combined.md` (#1700, not on main) | binds the predecessor; records 285 s as unmet | After this spec is on main, #1700 re-points its plan here, by the route the owner decides, and updates its PR body's done_when list. That plan's text naming 285 s changes there, not here. |
| Other plans and specs naming 285 s (`registry-envelope-pin-bound`, `registry-envelope-measured`, `registry-read-batching`, `registry-ci-envelope-pin`, `source-review-verifier`) | stage history of the five- and six-minute envelopes | Bound to other specs; unchanged. |

## Capacity and cost

- **Volume and velocity:** unchanged from the predecessor. One registry job per existing PR event; one render only when a PR changes one of the three inventory documents.
- **Wall-clock:** measured hosted whole job 327 s on 946d94d2 (pytest 306.51 s, 215 tests, 33 s reserve under 360 s). That is one run, not a guarantee. Acceptance is per exact head, with every attempt recorded.
- **Cost:** $0 new GCP workload, schedule or resource. Hosted runner minutes are unchanged, because no limit changes.

## Risks

- **Suite growth or runner variance.** The job could exceed 335 s. Item 13 then fails and holds release; no rerun selects a sample, and the timeout is not raised here.
- **A longer live limit landing first.** The 335 s bound still applies, so the ten-minute stage does not loosen it.
- **The SKILL line stays stale until its stage PR lands.** It already disagreed with the ten-minute envelope spec. The routing table above keeps that visible, and no gate reads that line as a threshold.

## Validation and rollout

1. This spec-only PR, on branch `docs/spec-feat-cicd-001-inventory-whole-job`, holds this file plus the predecessor's status-only change.
2. The PR passes `python3 scripts/gate/spec_gate.py --pr origin/main` and normal review within budget, and merges only on owner authorization.
3. #1700 then re-binds its plan and body, requalifies its exact head, and needs a hosted registry job meeting item 13.
4. No production action.
