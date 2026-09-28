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

Present the spec in sections. Stop after each section for feedback. Do not proceed until the user says approved. Then set `status: approved` and commit the spec alone (branch `docs/spec-<feat-id>` is fine; the gate never gates documentation), and merge it before the implementation branch opens: the gate reads the catalog row and the approved spec from the merge base (HEAD for a local commit), so a change that adds or edits its own spec, or its own catalog row, is refused.

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
- Body: link the spec and the plan by their exact paths, paste each `done_when` item as a `- [ ]` line that starts with the item's text, then the capacity numbers CLAUDE.md requires. CI reads the body as it renders (HTML comments and fenced code removed), refuses a ticked item whose line defers the work (`follow-up`, `non-blocking`, `future-work`, `TODO`, and the like), and when the PR touches `gcp/` or `.github/workflows/` it requires the Capacity section's Volume, Velocity, Wall-clock and cost to be filled, or an `n/a: <why>`.
- Open the PR as a draft, then set the plan's `pr` to its number in the next commit. A draft may still say `null`; a number that is not this PR fails the gate, and once the PR is marked ready for review CI requires the number and the Phase 5 records.
- Review cap: TWO rounds. After the second round of review comments, do not keep fixing in place. Invoke `superpowers:finishing-a-development-branch` and present: split into smaller PRs, re-cut from the spec, or discard. A PR that is not mergeable after two rounds is a spec problem, not a code problem.
- Never open a follow-up PR from an unmerged PR. Never stack.
- Before every commit, run `python3 scripts/gate/spec_gate.py --commit`. The hook runs it anyway; running it first avoids surprises. A commit from a detached HEAD that stages code is blocked; name its branch with `SPEC_GATE_BRANCH=<branch> git commit`.

## Phase 5: close (this is what "done" means)

In the SAME PR, before requesting final review:

1. `docs/product/02-FEATURE-CATALOG.md`: update the FEAT-ID's Status and Last reviewed (stocks: in its capability record under the table; solyra: in the row's columns). Touch only that row or record: CI refuses a change to any other capability's row or record in the catalog or the traceability doc, and any change to `01-PRODUCT-REQUIREMENTS.md` on a feature branch (requirements change on their own `docs/` branch first). CI also checks that Last reviewed has moved to a date and that Status is set; a blank or unrelated edit in the section does not count.
2. `docs/product/12-PR-ISSUE-TRACEABILITY.md`: add this PR's number under the FEAT-ID. A repo without that file (solyra) records it in the catalog row's PRs column instead.
3. If the spec lists canvases, add to the PR body: `Canvas refresh pending: <urls>`, or for a canvas marked `mode: report-only` in `docs/product/canvases.yml`, `Canvas check pending (report-only): <urls>`. CI checks that every canvas the spec lists appears under the marker its mode calls for, and that each is an entry in `canvases.yml`. The refresh is run from chat with the refresh-canvas skill after merge, never from this PR.
4. Run `python3 scripts/gate/export_model_registry.py` if the PR touched `docs/product/07-MODEL-REGISTRY.md` or `docs/EXPERIMENT_REGISTRY.md`, and commit the regenerated JSON.
5. Run the repo's docs audit on this branch and on `origin/main` (stocks: `python3 scripts/maintenance/docs_audit.py`; solyra: `node scripts/docs-audit.mjs`): the branch reports no finding that `main` does not. Then run `python3 scripts/gate/spec_gate.py --pr origin/main`. Both clean, or the PR is not done.
6. Tick every `done_when` box in the PR body with the evidence (test name, query, file) next to it, then mark the PR ready for review. From then on CI requires the catalog update, the PR number from step 2, and every box ticked.

## Never

- Never write implementation code before a spec has `status: approved`.
- Never mark a `done_when` item "future-work", "non-blocking", or "follow-up". Either finish it or remove it from the spec with the user's explicit consent, and say so in the PR.
- Never edit `docs/product/` from a feature branch except the one FEAT row or record and the traceability entry this PR owns, the `07-MODEL-REGISTRY.md` rows for models this spec changes, and the `generated/model-registry.json` that step 4 regenerates.
- Never let a second agent (Codex, Lovable, a webhook-triggered session) push to a branch this plan owns. One plan, one author.
