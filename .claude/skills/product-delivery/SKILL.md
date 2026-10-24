---
name: product-delivery
description: MANDATORY gate for any edit, modify, adjust, fix, refactor, feature, or "change X" request in this repo, before any code is touched. Use it even when the request sounds small, even when the user says "just fix", and even when a plan already exists. Binds the Superpowers brainstorming -> writing-plans -> subagent-driven-development chain to docs/product/ so every change carries a FEAT-ID, an approved spec, a plan, one PR, and an updated product record. Enforced by scripts/gate/spec_gate.py in the pre-commit hook and CI; work that skips this skill is rejected there.
---

# Product delivery gate

Every change is traceable: FEAT-ID -> spec -> plan -> one branch -> one PR -> product docs updated.
Superpowers does the work. This skill decides what gets written, where, and what "done" means.

Read `references/spec-template.md` and `references/plan-template.md` before writing either file.

## Phase 0: classify (always, first)

State exactly one, in one line, before doing anything else:

- **TRIVIAL**: typo, comment or wording in a doc (branch `docs/<slug>`), or a dependency bump that touches only manifests and lockfiles (branch `chore/<slug>`; in `package.json` or `pyproject.toml` only the dependency fields, since a `scripts` or tool-config edit is code CI runs). No spec. Stop here. A config or workflow change is not trivial: it is a CHANGE under the capability that owns the file: workflows and CI configuration under FEAT-CICD-001 (both repos), deploy scripts and Cloud Build triggers under FEAT-DEPLOY-001 (stocks), anything else under the capability whose catalog row or record covers it.
- **SPIKE**: investigation, no code will merge. One session budget. Output is one note at `docs/superpowers/spikes/YYYY-MM-DD-<slug>.md`. Branch `spike/<slug>`. No PR: the gate lets `spike/` commit code locally and gives it no allowance in CI. Stop here.
- **CHANGE**: everything else. Continue.

If unsure, it is a CHANGE. "Just fix it quickly" is a CHANGE.

## Phase 1: intake

1. Open `docs/product/02-FEATURE-CATALOG.md`. Name the FEAT-ID this change serves. Quote the row.
   No matching row: stop and ask the user whether to add one to 02 first. Never invent an ID.
2. From `docs/product/01-PRODUCT-REQUIREMENTS.md` in the stocks repo, which is canonical for both repos, list the REQ-IDs involved. The gate checks every `req_ids` entry: against the requirement definitions in that file where the repo holds them (stocks), by shape (`REQ-XXX-000`) where it does not (solyra).
3. List open GitHub issues the change closes or touches.
4. Check `docs/superpowers/specs/` for an existing spec with this `feat_id`. If one is `status: approved` and covers the change, skip to Phase 3. If it exists but does not cover it, write a new spec; do not silently widen the old one.
5. Check `docs/product/canvases.yml` for canvases that depict this area. Record their URLs; they go in the spec frontmatter.

## Phase 2: spec

Invoke `superpowers:brainstorming`. It asks the questions and proposes approaches. When the user picks one, write:

    docs/superpowers/specs/YYYY-MM-DD-<feat-id-lowercase>-<slug>.md

with the frontmatter in `references/spec-template.md`. `done_when` is the contract: each item must be verifiable by a test, a query, or a file the reviewer can open.

Present the spec in sections. Stop after each section for feedback. Do not proceed until the user says approved. Then set `status: approved` and commit the spec alone (branch `docs/spec-<feat-id-lowercase>`, kebab-case like every delivery branch; the gate validates the spec's frontmatter and nothing else there), and merge it before the implementation branch opens: the gate reads the catalog row and the approved spec from the merge base (HEAD for a local commit), so a change that adds or edits its own spec, or its own catalog row, is refused.

If review changes an approved spec on its open PR, present the changed sections to the user again and get their approval before that PR merges. A fix that changes no decision and no `done_when` item (wording, a citation, a line number) needs no new approval.

## Phase 3: plan

Invoke `superpowers:writing-plans`. Write:

    docs/superpowers/plans/YYYY-MM-DD-<feat-id-lowercase>-<slug>.md

with the frontmatter in `references/plan-template.md`, including `spec:` pointing at the approved spec. Every task names the spec section it implements and which `done_when` item it moves. The gate finds the plan by its `branch:`, so exactly one plan names each branch, and it authorizes code only while `status: ready`.

One plan = one branch = one PR. Branch name: `feature/<feat-id-lowercase>-<slug>` or `fix/<feat-id-lowercase>-<slug>`, exactly; the gate reads the FEAT-ID from that position and rejects any other shape.

If the plan exceeds roughly 15 tasks, split it into two specs, not one long plan.

## Phase 4: execute

Invoke `superpowers:using-git-worktrees`, then `superpowers:subagent-driven-development` (or `superpowers:executing-plans` when subagents are unavailable).

PR rules:
- Title: `<FEAT-ID>: <what changed>`, starting with the branch's FEAT-ID. CI rejects any other title.
- Body: link the spec and the plan by their exact paths, paste each `done_when` item as a `- [ ]` line that starts with the item's text, then the Capacity section: in stocks the three numbers and cost CLAUDE.md rule 0 requires; in solyra, which runs no workload, `n/a: <why>`. CI reads the body as it renders (HTML comments and fenced code removed), refuses a ticked item whose line defers the work (`follow-up`, `non-blocking`, `future-work`, `TODO`, and the like), and when the PR touches `gcp/` or `.github/workflows/` it requires the Capacity section's Volume, Velocity, Wall-clock and cost to be filled, or an `n/a: <why>`.
- Open the PR as a draft, then set the plan's `pr` to its number in the next commit. A draft may still say `null`; a number that is not this PR fails the gate, and once the PR is marked ready for review CI requires the number and the Phase 5 records.
- Review cap and disposition: follow AGENTS.md “What blocks the merge” and “Review budget and finding identity”. Four coordinated judgment passes per lineage include pre-push reviews; at most two external code-review rounds. Preserve all predecessor/split/replacement history and stable findings. At exhaustion stop autonomous fixes, pushes and review requests and obtain owner adjudication; never force a P2/P3-only re-cut or auto-pass a blocker. Disposition does not authorize merging.
- Never open a follow-up PR from an unmerged PR. Never stack.
- A change to a gate file (`scripts/gate/`, `.githooks/pre-commit`, the two gate workflows, their suites) requires a pre-push red-team cohort: three parallel reviewers for shell semantics, YAML/Actions, and exporter/policy documents, each proving a bypass against a concrete snippet. Reserve the cohort under AGENTS.md before starting. Fix confirmed blockers in one batch and verify within the remaining allowance; repeated judgment passes count. If required clean review cannot be obtained, escalate rather than loop, waive the prerequisite or push findings one at a time.
- Before every commit, run `python3 scripts/gate/spec_gate.py --commit`. The hook runs it anyway; running it first avoids surprises. A commit from a detached HEAD that stages code is blocked; name its branch with `SPEC_GATE_BRANCH=<branch> git commit`.

## Phase 5: close (this is what "done" means)

In the SAME PR, before requesting final review:

1. `docs/product/02-FEATURE-CATALOG.md`: update the FEAT-ID's Status and Last reviewed (stocks: in its capability record under the table; solyra: in the row's columns). Touch only that row or record: CI refuses a change to any other capability's row or record in the catalog or the traceability doc, and any change to `01-PRODUCT-REQUIREMENTS.md` on a feature branch (requirements change on their own `docs/` branch first). CI also checks that Last reviewed has moved to a date and that Status is set; a blank or unrelated edit in the section does not count.
2. `docs/product/12-PR-ISSUE-TRACEABILITY.md`: add this PR's number under the FEAT-ID. A repo without that file (solyra) records it in the catalog row's PRs column instead.
3. If the spec lists canvases, add to the PR body: `Canvas refresh pending: <urls>`, or for a canvas marked `mode: report-only` in `docs/product/canvases.yml`, `Canvas check pending (report-only): <urls>`. CI checks that every canvas the spec lists appears under the marker its mode calls for, and that each is an entry in `canvases.yml`. The refresh is run from chat with the refresh-canvas skill after merge, never from this PR.
4. Run `python3 scripts/gate/export_model_registry.py` if the PR touched `docs/product/07-MODEL-REGISTRY.md` or `docs/EXPERIMENT_REGISTRY.md`, and commit the regenerated JSON.
5. Run the repo's docs audit on this branch and on `origin/main` (stocks: `python3 scripts/maintenance/docs_audit.py`; solyra: `node scripts/docs-audit.mjs`): the branch reports no finding that `main` does not. Then run `python3 scripts/gate/spec_gate.py --pr origin/main`. Both clean, or the PR is not done.
6. Tick every `done_when` box in the PR body with the evidence (test name, query, file) next to it, then mark the PR ready for review. From then on CI requires the catalog update, the PR number from step 2, and every box ticked.
7. After the merge, on a `docs/<slug>` branch: set the plan's `status: done` (a plan is documentation, so the gate does not block it), and stamp any document this PR left unreviewed. The gate refuses `done` while the PR is open, so this is the one step that follows the merge.

## Never

- Never write implementation code before a spec has `status: approved`.
- Never mark a `done_when` item "future-work", "non-blocking", or "follow-up". Either finish it or remove it from the spec with the user's explicit consent, and say so in the PR.
- Never edit `docs/product/` from a feature branch except the one FEAT row or record and the traceability entry this PR owns, the `07-MODEL-REGISTRY.md` rows for models this spec changes, the `generated/model-registry.json` that step 4 regenerates, and only the inventory blocks and existing fixed renderer-owned count/as-of substitutions of `05-a-ARCHITECTURE.md`, `05-c-DATA_DEPENDENCIES.md` and `05-e-API.md` re-rendered by `scripts/maintenance/doc_inventory.py` from committed source and merge-base prose (REQ-GOV-004). After the approved branch-document-review protocol implementation is on main, the additional SITE implementation-source note rows are permitted only under the exact declaration and byte-preservation contract below. This does not open existing SITE tables, frontend claims or deployment evidence.
- Never let a second agent (Codex, Lovable, a webhook-triggered session) push to a branch this plan owns. One plan, one author.

# Committed-source documentation identity (FEAT-CICD-001)

The approved `docs/superpowers/specs/2026-10-13-feat-cicd-001-source-review-verifier.md` governs this protocol. This precise skill/template policy is delivered by the separate approved policy-only FEAT-CICD-001 CODE change; `.claude` policy Markdown remains gated process code. Only after that policy CODE implementation and the separately approved verifier spec are on main may the verifier implementation branch open. Policy publication does not activate a verifier or grant permission to use an unimplemented SITE allowance.

Owner approval was received October13,2026; actual approved verifier spec AND completed policy-only CODE implementation on main still precede verifier code; the policy-only branch instead follows its own approved spec/ready plan and ordinary gate. The initial CICD implementation PR edits no SITE content, no registry watcher and no pinned workflow. Its one initial-bootstrap route is bound to exact FEAT-CICD-001 and this exact approved protocol spec, empty note IDs and unchanged raw SITE body/marker. Trusted current policy must lack `scripts/maintenance/doc_source_snapshot.py`, and changed watched paths relative to the actual recorded ancestral main baseline may only be `scripts/maintenance/doc_source_snapshot.py`, `scripts/maintenance/docs_audit.py`, `scripts/gate/spec_gate.py`, `tests/scripts/test_doc_source_snapshot.py`, `tests/scripts/test_docs_audit.py`, `tests/scripts/test_spec_gate.py`. Add the verifier and otherwise retain existing initializer bytes. Scoped catalog/traceability/plan/sidecar changes remain under normal rules. The unchanged BASE gate still judges the PR; the actual HEAD audit may consume only this eligible committed identity record, following the existing branch-audit execution model. After squash bootstrap is accepted only when complete current SOURCE/BODY equal current MAIN and the actual ancestral baseline lacked the verifier; future changed-source branches cannot reuse it. Compare actual branch/main audit outputs with no new findings; do not replace either with synthetic evidence. All ordinary BASE checks, unchanged BASE suite, complete affected suites, four independent gate-review seats, authenticated current-head external CODE review, green CI and resolved conversations remain required. An inability to satisfy this bootstrap is a blocker, not a waiver.

Only after that implementation is on main may a capability use its immutable approved merge-base spec's optional `site_source_notes` list. The list contains sorted, unique existing SITE Chain element IDs. A feature cannot add or widen the declaration in its own implementation PR. Ordinary identity eligibility independently binds the actual approved spec/FEAT at recorded ancestral main, its unchanged mode/type/blob in current POLICY and SOURCE, and actual added/updated own declared notes relative to that baseline. Every declared note must begin `source_identity_sha256=<exact current source hash>; ` followed by nonempty backend/source/test prose. An absent/empty declaration, unchanged notes, wrong hash/spec/FEAT or a removal alone cannot clear watched CODE drift. SITE edits are restricted to its own `(FEAT-ID, declared Component-ID)` rows in the appended `## Implementation-source notes` table with header `| FEAT | Component | Backend source and tests (implementation only; rollout pending) |` and delimiter `|---|---|---|`. Preserve all other bytes, existing Chain/checklist/frontend/progress/S/T/V/Te/deployment evidence and the historical marker. Notes describe backend implementation source and local tests only, without assertions of deployed availability. External CODE review judges prose; the gate checks exact structural ownership.

Produce a snapshot from the actual trusted main policy and committed source, commit the sidecar, then verify it from the resulting committed HEAD:

```bash
python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json
python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 8388608 --max-entries 20000
```

For ordinary notes, use producer preflight's reported source identity to update declared note cells, commit them, rerun production for the exact final body, commit the sidecar and verify. Preflight cannot install a record until notes are eligible. SITE and sidecar are outside the source hash, so this has no self-cycle. The verification command follows the sidecar commit; the ordinary gate/hook applies to that commit too. Watcher coverage and SITE body identity come from actual committed inputs, not authored subsets or an unavailable feature SHA. The record's real `baseline.main_commit_oid` is an actual current-main commit for branch acceptance and an available ancestor for landed verification, whose actual tree/spec is independently checked. Independently compare SOURCE registry `docs/DOC_REGISTRY.md` blob OID, mode and type to trusted POLICY; any difference refuses this route, with original findings retained. Reproduce and re-review after later watched-code/body/policy edits; reject dirty SITE state. Fixed ceilings cover combined input bytes and current/baseline entry counts, and one whole-verification deadline. No caller may raise them. There are no authentication or network calls.

A matching eligible declared-note/bootstrap record means only `implementation-source identity matched; external CODE review under existing rules; rollout pending`. Anyone may reproduce it. It contains no external-review attestation and does not authenticate reviewers, waive merge prerequisites, certify deployment/data freshness, or move Last reviewed/Against. Only for SITE does eligible valid proof replace source/body changed-since checks with that explicit context; missing/invalid/ineligible proof retains original checks and adds provenance findings when the identity route is needed. No record Boolean/kind/caller flag can admit CODE changes without notes by pretending to be DOC close-out or reusing bootstrap. Every other audit predicate and document remains checked. Branch-versus-main no-new findings remains mandatory.

After squash, independently verify the actual main source/body identity in a fresh clone without assuming the feature commit survives. Complete separate DOC main/staging close-out with real evidence. If only the marker needs changing, use existing trunk-only `--stamp --verify` after real checks, then remove the sidecar in the same DOC commit. A valid ordinary verified current-trunk marker with zero original source AND body drift takes precedence over records; absent sidecar is then legal and no provenance/rollout-pending output is emitted. Invalid marker or unresolved drift cannot retire the route.

If deployed-evidence prose must first change, the fixed `trunk-closeout-pending` route admits ONLY the independently measured committed delta of SITE plus sidecar, regular mode100644 blobs, historical marker unchanged, no other path/type/mode change, entire runtime SOURCE equal current MAIN, registry/spec equality and baseline exactly current MAIN. The exact approved protocol FEAT/spec binds this DOC-only record, with empty component IDs and context `implementation-source; trunk-closeout-pending`; output says `trunk documentation close-out pending`, never deployed verified. Actual external CODE reviewers must review genuine source/body/staging evidence. After body-first DOC squash, fetch that actual main body revision and recheck real source/body/staging evidence; a second DOC-only PR uses existing trunk-only stamping against that body-containing revision and removes the sidecar. Landed pending proof independently rechecks the two-path-only ancestral delta and accepts only exact complete SOURCE/BODY equal MAIN. Plan-done is separate DOC work. Final ordinary marker and zero original source/body drift must pass independently with the sidecar absent. No dirty/uncommitted body, unavailable feature SHA or new CODE change is admitted. This sequence grants no no-new waiver and no deployment inference from records.

Catalog and PR records must distinguish identity matching, external CODE review and rollout/deployed verification; identity matching alone does not complete delivery. AGENTS.md lineage review limits, owner-approved immutable specs, renderer60second/512MiB and registry285second contracts remain unchanged. Actual producer/verifier/audit/gate controls must refuse no-note CODE changes, bootstrap reuse, registry blob/mode/type changes and premature retirement, paired with accepted branch/squash/fresh-clone/two-phase DOC retirement controls.

Shared evidence publication follows AGENTS.md “Generated evidence and one writer”: exclusive publisher, private reviewer outputs, expected-head/hash refusal, non-force push and owner-acknowledged quiescent handoff. Hash checks alone are not atomic exclusion.
