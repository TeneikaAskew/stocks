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

- **TRIVIAL**: typo, comment, wording in a doc, dependency bump, a one-line config value. Branch `docs/<slug>` or `chore/<slug>`. No spec. Stop here.
- **SPIKE**: investigation, no code will merge. One session budget. Output is one note at `docs/superpowers/spikes/YYYY-MM-DD-<slug>.md`. Branch `spike/<slug>`. No PR. Stop here.
- **CHANGE**: everything else. Continue.

If unsure, it is a CHANGE. "Just fix it quickly" is a CHANGE.

## Phase 1: intake

1. Open `docs/product/02-FEATURE-CATALOG.md`. Name the FEAT-ID this change serves. Quote the row.
   No matching row: stop and ask the user whether to add one to 02 first. Never invent an ID.
2. From `docs/product/01-PRODUCT-REQUIREMENTS.md`, list the REQ-IDs involved.
3. List open GitHub issues the change closes or touches.
4. Check `docs/superpowers/specs/` for an existing spec with this `feat_id`. If one is `status: approved` and covers the change, skip to Phase 3. If it exists but does not cover it, write a new spec; do not silently widen the old one.
5. Check `docs/product/canvases.yml` for canvases that depict this area. Record their URLs; they go in the spec frontmatter.

## Phase 2: spec

Invoke `superpowers:brainstorming`. It asks the questions and proposes approaches. When the user picks one, write:

    docs/superpowers/specs/YYYY-MM-DD-<feat-id-lowercase>-<slug>.md

with the frontmatter in `references/spec-template.md`. `done_when` is the contract: each item must be verifiable by a test, a query, or a file the reviewer can open.

Present the spec in sections. Stop after each section for feedback. Do not proceed until the user says approved. Then set `status: approved` and commit the spec alone (branch `docs/spec-<feat-id>` is fine; the gate exempts `docs/`).

## Phase 3: plan

Invoke `superpowers:writing-plans`. Write:

    docs/superpowers/plans/YYYY-MM-DD-<feat-id-lowercase>-<slug>.md

with the frontmatter in `references/plan-template.md`, including `spec:` pointing at the approved spec. Every task names the spec section it implements and which `done_when` item it moves.

One plan = one branch = one PR. Branch name: `feature/<feat-id-lowercase>-<slug>` or `fix/<feat-id-lowercase>-<slug>`. The gate reads the FEAT-ID from the branch name.

If the plan exceeds roughly 15 tasks, split it into two specs, not one long plan.

## Phase 4: execute

Invoke `superpowers:using-git-worktrees`, then `superpowers:subagent-driven-development` (or `superpowers:executing-plans` when subagents are unavailable).

PR rules:
- Title: `<FEAT-ID>: <what changed>`. CI rejects titles without a FEAT-ID.
- Body: link the spec and plan, paste `done_when` as a `- [ ]` checklist, then the capacity numbers CLAUDE.md requires.
- Review cap: TWO rounds. After the second round of review comments, do not keep fixing in place. Invoke `superpowers:finishing-a-development-branch` and present: split into smaller PRs, re-cut from the spec, or discard. A PR that is not mergeable after two rounds is a spec problem, not a code problem.
- Never open a follow-up PR from an unmerged PR. Never stack.
- Before every commit, run `python3 scripts/gate/spec_gate.py --commit`. The hook runs it anyway; running it first avoids surprises.

## Phase 5: close (this is what "done" means)

In the SAME PR, before requesting final review:

1. `docs/product/02-FEATURE-CATALOG.md`: update the FEAT-ID row (Status, Last reviewed, evidence PR number). Touch only that row.
2. `docs/product/12-PR-ISSUE-TRACEABILITY.md`: add this PR under the FEAT-ID.
3. If the spec lists canvases, add to the PR body: `Canvas refresh pending: <urls>`. The refresh is run from chat with the refresh-canvas skill after merge, never from this PR.
4. Run `python3 scripts/gate/export_model_registry.py` if the PR touched `docs/product/07-MODEL-REGISTRY.md` or `docs/EXPERIMENT_REGISTRY.md`, and commit the regenerated JSON.
5. Run `python3 scripts/maintenance/docs_audit.py` and `python3 scripts/gate/spec_gate.py --pr origin/main`. Both clean, or the PR is not done.
6. Tick every `done_when` box in the PR body with the evidence (test name, query, file) next to it.

## Never

- Never write implementation code before a spec has `status: approved`.
- Never mark a `done_when` item "future-work", "non-blocking", or "follow-up". Either finish it or remove it from the spec with the user's explicit consent, and say so in the PR.
- Never edit `docs/product/` from a feature branch except the one FEAT row and the traceability entry this PR owns.
- Never let a second agent (Codex, Lovable, a webhook-triggered session) push to a branch this plan owns. One plan, one author.
