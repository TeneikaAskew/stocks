---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-REVIEW-001]
issues: []
canvases: []
done_when:
  - "AGENTS.md has a '## Review guidelines' section that says: the first review of a PR is the complete one; the reviewer reads every changed file in full and the callers and callees of what changed; every finding at every severity goes in that one review; a finding that is one instance of a class is reported once with every location; the edges a change creates are checked (errors and rejections, late or out-of-order responses, signed-out and other-account states, empty and null data, and the docs, tests and generated files that cite what changed); a spec PR is reviewed against the code it will change; later rounds check the earlier findings and then the new commits, marking a missed real problem as missed; and a pre-existing problem is reported as an issue or labelled pre-existing rather than as a merge blocker"
  - "python3 scripts/gate/spec_gate.py --pr origin/main passes on the PR head, and the docs audit reports nothing new over origin/main"
  - "The FEAT-CICD-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists this PR under FEAT-CICD-001"
status: approved
supersedes: null
---

# Ask reviewers for the complete review in the first round

## Problem

Every PR here gets at most two review rounds (CLAUDE.md, "Review cap"); after that it is split,
re-cut or discarded. An approved spec cannot change in place either: the commit-time gate refuses
any edit to a spec committed as `approved`, so each revision of a spec PR is a new PR cut from
`main`.

Codex has been finding new issues in every round rather than all of them in the first. On
2026-10-10 the solyra verify-email spec went through six cuts (solyra#231, solyra#232, solyra#233,
solyra#235, solyra#237, solyra#239), and each first review raised two to five findings the previous one could have raised: most
were further instances of one class (state that survives a switch of the signed-in account) found
one at a time. The stocks retire-prod spec took two cuts (#1363, #1364). Each cut costs a PR,
a CI run and a review wait.

Codex reads review instructions from a `## Review guidelines` section in `AGENTS.md`. Neither
repository's `AGENTS.md` has one, so reviewers get no guidance on depth or on reporting a class of
finding at once.

## Non-goals

- No change to the review cap, the gate, or the spec rules. The guidance makes the first round
  fuller; it does not add rounds.
- Not Codex's own settings (which events trigger a review), which live outside the repository.
- Not CLAUDE.md. Its review rules (Rule 2.5) govern how an author handles findings; this section
  governs how a reviewer writes them.

## Approaches considered

1. Raise the round cap. Rejected: more rounds is the cost being reduced, not the fix.
2. Put the guidance in a separate `REVIEW.md`. Rejected: Codex looks for it in `AGENTS.md`, the file
   every agent already loads here.
3. A `## Review guidelines` section in `AGENTS.md`, in both repositories with the same text. Chosen.

Chosen on 2026-10-11 at the owner's request: "when doing a code review it needs to be the most
exhaustive as possible in the first round".

## Design

`AGENTS.md` gains a `## Review guidelines` section after its existing content, addressed to every
reviewer (Codex, Claude, a person), with three parts:

- **The first review is the complete one.** Why (the cap and the in-place rule make a held-back
  finding cost a whole PR), then what to do before posting: read every changed file in full and the
  callers and callees of what changed; report every finding at every severity at once; when a
  finding is one instance of a class, search for every instance and report the class once with each
  location; check the edges a change creates (errors and rejections, late or out-of-order
  responses, signed-out and other-account states, empty and null data under the repository's
  no-silent-fallbacks rule, and the docs, tests and generated files that cite what changed); for a
  spec PR, open each file the spec names and check every `done_when` item can be met and would fail
  against a broken implementation.
- **Later rounds review the new commits.** Check each earlier finding is fixed, then what changed;
  a real problem in code the first review already saw is still reported, marked as missed.
- **Pre-existing problems are issues, not blockers.** A problem the PR did not introduce and does
  not make worse is a new issue, or a comment labelled pre-existing.

The text is the same in both repositories except the no-silent-fallbacks rule's number (stocks
Rule 3.7, solyra Rule 4).

Capacity: n/a. No workload runs differently.

## Risks

- A longer first review. That is the trade wanted: one long review instead of several short ones.
- Reviewers may ignore it. Nothing enforces it; the rounds on the next few spec PRs will show
  whether first reviews got fuller.
