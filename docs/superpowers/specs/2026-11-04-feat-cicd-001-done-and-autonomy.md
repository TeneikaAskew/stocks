---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001]
issues: []
canvases: []
done_when:
  - "CLAUDE.md has a '## Definition of done and autonomy (owner directive)' section directly after '## Before any change (read this first)' that says: done means merged to main, deployed where the change ships (the staging deploy that a merge to main starts, for a change that ships), and verified, where verified means the tests pass, a change the site shows carries Playwright evidence as AGENTS.md's '## Review guidelines' define it, and real queries against GCP show the expected result, with that evidence recorded on the PR; within its assigned scope a session makes reversible calls itself and takes its own recommendations, and commits, pushes, opens PRs and iterates on review without waiting, inside this file's spec gate, review cap and gate-file red-team rules, recording its choices on the PR instead of batching decisions back to the owner; a session stops for the owner only for irreversible or production-destructive steps (live migrations, data deletes, production config), spending money, or contacting people outside the project, and asks one specific question, not a list; the owner's latest instruction in a session supersedes earlier holds in it; and a session that another lane blocks opens a small PR for the blocking piece or coordinates with that lane's owner instead of waiting"
  - "The implementing PR changes no line of CLAUDE.md outside that new section and changes no other process file (AGENTS.md, .claude/, .githooks/, .github/, scripts/gate/)"
  - "python3 scripts/gate/spec_gate.py --pr origin/main passes on the PR head, and the docs audit reports nothing new over origin/main"
  - "The FEAT-CICD-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists the implementing PR under FEAT-CICD-001"
status: approved
supersedes: null
---

# Owner directive: definition of done and autonomy for every session

## Problem

On 2026-11-04 the owner had five delivery sessions open on this repository. Each one finished local
work and then stopped: some to hand back a reversible choice they had already recommended, some at a
push they could have made, some because an earlier hold in the session was never lifted, and some
because another lane had not landed yet. Several called work finished that was not merged, not
deployed and not checked against live data. The owner had to read each session and type the same
go-ahead into each one.

The universal acceptance gate in 01-PRODUCT-REQUIREMENTS.md already says what a significant feature
needs before it is done. Nothing in CLAUDE.md tells a session that its work is not done until it is
merged, deployed and verified against live data, or which decisions the owner expects it to make
without asking.

## Decision

Add one short owner directive to CLAUDE.md, directly after "Before any change (read this first)", so
every session reads it before it plans work. It states:

1. Done means merged to main, deployed where the change ships, and verified: tests pass, Playwright
   evidence for a change the site shows (as AGENTS.md's Review guidelines define it), and real
   queries against GCP that show the expected result, recorded on the PR.
2. Within its assigned scope, a session makes reversible calls itself and takes its own
   recommendations. It commits, pushes, opens PRs and iterates on review without waiting, inside the
   existing spec gate, review cap and gate-file red-team rules, and records its choices on the PR.
3. It stops for the owner only for irreversible or production-destructive steps, spending money, or
   contacting people outside the project, and asks one specific question.
4. The owner's latest instruction in a session supersedes earlier holds in it.
5. A lane blocked by another lane opens a small PR for the blocking piece or coordinates with that
   lane's owner instead of waiting.

## Scope

Only CLAUDE.md gains the new section. No other rule in CLAUDE.md changes, and the gate, the hook,
the workflows, AGENTS.md and the local skills are untouched. The directive narrows nothing the
existing rules require: the spec gate, the review cap, the merge gate in Rule 2.5 and Rule 0's
capacity numbers all still apply, and the directive only says the session acts on them without
waiting for the owner.

## Delivery

This spec merges first. The implementing PR comes from
`feature/feat-cicd-001-done-and-autonomy` with a plan, the CLAUDE.md section, and the FEAT-CICD-001
catalog and PR-traceability records.

## Cost, side effects and rollback

No code, workflow, job or schema changes, so no workload runs differently and no GCP cost changes.
Rollback is reverting the implementing PR.
