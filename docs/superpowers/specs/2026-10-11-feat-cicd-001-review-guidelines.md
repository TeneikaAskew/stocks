---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-003]
issues: []
canvases: []
done_when:
  - "The root AGENTS.md of this repository (stocks) has a '## Review guidelines' section that says: a reviewer's first review of a pull request is the complete one; it reads every changed file in full, generated files included, and the direct callers and callees of what changed, and where a changed file's generator runs in the reviewer's environment it re-runs it and compares; it posts, against the revision it reviews, every finding it can raise on a defect the pull request introduces or makes worse, at every severity, with one finding per defect class listing each location; it checks the edges a change creates (errors and rejections, late or out-of-order responses, signed-out and other-account states, empty and null data, and the docs, tests and generated files that cite what changed); a spec PR is reviewed against the code it will change, and each done_when item that describes behavior must fail against a broken implementation; a later review by the same reviewer checks its earlier findings, then the new commits, and still posts a defect it finds in what its first review covered, for the author to classify under CLAUDE.md Rule 2.5; a problem the pull request neither introduces nor makes worse is not posted as a finding (a reviewer who can open an issue may open one); and a change a user can see in the site carries Playwright evidence from a run that exercises the changed code: solyra's hermetic suite for a solyra change; for a stocks change, an API test of the changed response in the PR, while runs against the deployed site before the merge and once staging has deployed it are close-out steps the owner posts on the PR, not boxes the PR ticks; with screenshots of the state each run shows, described state by state in a PR comment and kept in the e2e run's playwright-report artifact (saved under test-results/, kept 7 days) or sent to the owner; the reviewer asks for the hermetic run or the API test when the PR lacks it"
  - "CLAUDE.md Rule 2.5 says a thread holding a finding that a reviewer posted after its own first review is not resolved until a reply on it classifies each location, taking the first class that applies: uncounted (not a defect, a defect the pull request neither introduces nor makes worse, or one that first review raised there), missed (the pull request had introduced or worsened it by the commit that first review covered, named by SHA), or new (a later commit introduced or worsened it, named by SHA); it defines a reviewer and a first review as REQ-GOV-003 does; it says a first review that posts no findings leaves no review object, that the commit it covered is the one Codex's review-summary comment shows for that review type when that row first reads Completed, and that the author records that SHA in a PR comment then, since the next run replaces the row; and it tells a reviewer of a pull request to follow AGENTS.md's '## Review guidelines'"
  - "CLAUDE.md §2.5 'A resolved thread is not a reviewed commit' says Codex's code review also runs when new commits are pushed to a PR open for review (the 'New commits' trigger in its review-summary comment on #1366 and #1371), that a review with no findings leaves no review object, and that the head counts as reviewed only when, after the PR's latest review-triggering event, a review authored by chatgpt-codex-connector[bot] was submitted naming it in commit_id, or the Code Review row of Codex's own review-summary comment reads Completed for the head's SHA, as .claude/commands/resolve-issue.md step 2 requires"
  - ".github/pull_request_template.md's Merge gate counts the head as reviewed as §2.5 does and asks for the classifying reply on each later finding, and .claude/commands/resolve-issue.md quotes §2.5's trigger list as it now reads, resolves a later finding's thread only after that reply, replaces its 'There is no round limit' with the two-round review cap: after a PR's second review round, stop and split, re-cut or discard it, as CLAUDE.md and the product-delivery skill say, and rewords 'Nine review rounds on one PR is not hypothetical here' to say paging matters because one PR can carry several reviews' threads"
  - "CLAUDE.md §3.11's definition of evidence includes, for a change the site shows, Playwright evidence as AGENTS.md's '## Review guidelines' define it: an API test of the changed response in the PR, and runs against the deployed site before the merge and once staging has deployed it, which the owner posts on the PR as close-out steps, with screenshots of the state each shows"
  - ".claude/agents/debug-local.md's Verify step says a bug a user sees in the site is verified with a Playwright run that reproduces it before the fix and passes after it, with screenshots of both: an API test of the fixed response in the PR that fails before the fix and passes after it, and runs against the deployed site that reproduce it before the merge and pass once staging has deployed the fix, which the owner posts on the PR as close-out steps"
  - ".claude/commands/resolve-issue.md's deploy step treats the staging deploy that a merge to main starts as the deployment and no longer has a promote-to-prod procedure (promote_to_prod and the deploy-solyra-api-prod trigger, deleted 2026-10-10 under #1366), .github/prompts/architecture.md describes solyra-api-staging as the only API service, and git grep -n solyra-api-prod -- .claude .github prints only lines that say it was retired"
  - "python3 scripts/gate/spec_gate.py --pr origin/main passes on the PR head, and the docs audit reports nothing new over origin/main"
  - "The FEAT-CICD-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists this PR under FEAT-CICD-001"
status: approved
supersedes: null
---

# Ask reviewers for the complete review in the first round, and for browser proof of a visible change

## Problem

Every PR here gets at most two review rounds (CLAUDE.md, "Review cap"); after that it is split,
re-cut or discarded. An approved spec cannot change in place either: the commit-time gate refuses
any edit to a spec committed as `approved`, so each revision of a spec PR is a new PR cut from
`main`. Codex's code review also runs when new commits reach a PR open for review, so each fix pushed
is a round.

Codex has been finding new issues in every round rather than all of them in the first. Between
2026-10-10 22:46 and 2026-10-11 00:25 UTC the solyra verify-email spec went through six cuts
(solyra#231, #232, #233, #235, #237, #239). The first reviews of cuts two to five (solyra#232, solyra#233, solyra#235, solyra#237) raised four, three, four and five findings, and solyra#239 passed with none; most were further instances of one class
(state that survives a switch of the signed-in account) found one at a time. The stocks retire-prod spec
took two cuts (#1363, #1364). Each cut costs a PR, a CI run and a review wait.

Codex reads review instructions from a `## Review guidelines` section in `AGENTS.md`. Neither
repository's `AGENTS.md` has one, so reviewers get no guidance on depth or on reporting a class of
finding at once. REQ-GOV-003 (#1368, re-cut as #1371) now requires that section in both repositories, and a reply that
classifies each later finding so misses can be counted. Its Enforced-by column plans both: the section
under FEAT-CICD-001, and the reply in CLAUDE.md Rule 2.5.

This re-cuts #1367, written before REQ-GOV-003 settled. It had the reviewer mark its own misses,
and sent pre-existing problems to a new issue or a comment labelled pre-existing, neither of which Codex's
review can produce.

Two process files also still describe `solyra-api-prod`, retired on 2026-10-10 (#1366), as live:
`.claude/commands/resolve-issue.md` and `.github/prompts/architecture.md`. Process files change only
under FEAT-CICD-001, and this change already edits the first.

## Non-goals

- No change to the review cap, the gate, or the spec rules. The guidance makes the first round
  fuller; it does not add rounds.
- Not Codex's own settings (which events trigger a review), which live outside the repository.
- No mechanical check of the classifying reply. A check that reads review threads would be its own change.
- Not REQ-GOV-003's Enforced-by column. A feature branch cannot edit `01-PRODUCT-REQUIREMENTS.md`,
  so a `docs/` PR after this merges moves it from "planned" to the sections this change adds.
- Not the other repository. This spec covers stocks' files; solyra's own spec (re-cutting solyra#240) covers the other one,
  with its own plan and PR, because each repository's gate only sees its own files.

## Approaches considered

1. Raise the round cap. Rejected: more rounds is the cost being reduced, not the fix.
2. Put the guidance in a separate `REVIEW.md`. Rejected: `AGENTS.md` is the file Codex reads, and
   CLAUDE.md, which Claude Code loads, can point reviewers to it.
3. A `## Review guidelines` section in `AGENTS.md` for reviewers, and the classifying reply in
   CLAUDE.md Rule 2.5 for authors, in both repositories, each under its own spec. Chosen.

Chosen on 2026-10-11 at the owner's request: "when doing a code review it needs to be the most
exhaustive as possible in the first round", and later the same day, that Playwright is "an evidence path
of proof it's fixed" in review and debugging. REQ-GOV-003 states the first as a requirement; the second
applies REQ-GOV-001's reproduction rule to a change a user can see.

## Design

- **Review guidelines (`AGENTS.md`).** The root `AGENTS.md` gains a `## Review guidelines` section after
  its existing content, addressed to every reviewer (Codex, Claude, a person):
  - *The first review is the complete one.* Why (the cap, the in-place rule and per-push reviews make
    a held-back finding cost a round or a whole PR), then what to do before posting: read every changed
    file in full, generated files included, and the direct callers and callees of what changed; where a
    file's generator runs in the reviewer's environment, re-run it and compare; post every finding on a
    defect the PR introduces or makes worse, at every severity, at once; when a finding is one instance of
    a class, search for every instance and post the class once with each location; check the edges a
    change creates (errors and rejections, late or out-of-order responses, signed-out and other-account
    states, empty and null data under the repository's no-silent-fallbacks rule (Rule 3.7), and the docs,
    tests and generated files that cite what changed); for a spec PR, open each file the spec names, check
    every `done_when` item can be met, and check that each item describing behavior would fail against a
    broken implementation. Items that record delivery (the gate, the docs audit, the catalog row) are only
    checked for being met.
  - *Later reviews.* A reviewer's later review checks its earlier findings, then the new commits, and
    still posts a defect it finds in what its first review covered, for the author to classify.
  - *Not this PR's problems.* A problem the PR neither introduces nor makes worse is not posted as a
    finding, since every thread holds the merge (REQ-GOV-001). A reviewer who can open an issue may open
    one.
  - *Browser proof.* A change a user can see in the site carries Playwright evidence from a run that
    exercises the changed code. solyra's hermetic suite covers a solyra change; it intercepts every
    `/api` call, so for a stocks change the proof in the PR is an API test of the changed response.
    Runs against the deployed site, one before the merge and one once staging has deployed it, are
    close-out steps the owner posts on the PR, not boxes the PR ticks: staging's trigger deploys from
    `main`, deploying a branch with `platform/deploy.sh` would put unreviewed code behind the live site,
    and the deployed site's sign-in is interactive (`npm run e2e:cloud:auth` runs headed). Screenshots of the
    state each run shows are described state by state in a PR comment and kept in the e2e run's
    `playwright-report` artifact (saved under `test-results/`, kept 7 days) or sent to the owner, since
    images cannot be attached to a PR from a Claude Code session.
    The reviewer asks for the hermetic run or the API test when the PR lacks it.

- **The classifying reply (CLAUDE.md Rule 2.5).** The author's side of REQ-GOV-003, in its words: a
  thread holding a finding that a reviewer posted after its own first review is not resolved until a
  reply classifies each location, taking the first class that applies: uncounted, missed (with the SHA
  of the commit the first review covered) or new (with the SHA of the later commit). A reviewer is one
  account, split by review type where one account runs separately triggered types; its first review is
  the earliest it completes, including one with no findings. A clean first review leaves no review
  object, and Codex's review-summary comment shows only the latest run per type, so the author records
  that SHA in a PR comment when the row first reads Completed. Rule 2.5 also tells a reviewer to follow
  `AGENTS.md`'s `## Review guidelines`, since Claude Code loads CLAUDE.md and not `AGENTS.md`.

- **A reviewed head (CLAUDE.md §2.5).** "A resolved thread is not a reviewed commit" says a push does not
  trigger a Codex re-review and checks a head by a review's `commit_id`. Codex's code review now runs on
  new commits to a PR open for review, a review with no findings leaves no review object, and a reply on a
  thread is itself a review object naming the head. The paragraph says so and adopts the check that
  `.claude/commands/resolve-issue.md` step 2 already makes, with the same cutoff on both alternatives:
  after the PR's latest review-triggering event, a review authored by `chatgpt-codex-connector[bot]` was
  submitted naming the head, or the Code Review row of Codex's own review-summary comment reads Completed
  for the head's SHA. Without the cutoff, re-marking a draft ready or an `@codex review` on an unchanged
  head would count the older review while the new run is still going. The two places that
  quote the old paragraph follow it: the Merge gate of `.github/pull_request_template.md`, which also asks
  for the classifying reply, and `.claude/commands/resolve-issue.md`, which quotes the trigger list,
  resolves a later finding's thread only after that reply, and loses its "There is no round limit" for
  the two-round review cap CLAUDE.md and the product-delivery skill already set.

- **The retired service in process files.** `solyra-api-prod` and its `deploy-solyra-api-prod` trigger
  were deleted on 2026-10-10 (#1366). `.claude/commands/resolve-issue.md` still tells the resolver to
  promote a fix to prod through that trigger (`promote_to_prod`), a step that can no longer run, and
  `.github/prompts/architecture.md:92`, which the monthly refresh feeds to Gemini, still says two API
  services serve the API, so each refresh writes that back into `05-a-ARCHITECTURE.md`. Both are process
  files, so they change under FEAT-CICD-001 here. The deploy step keeps its point that a merge starts
  a staging build only when the trigger's `includedFiles` match, and verifies the fix against staging.

- **Evidence rules (`CLAUDE.md`).** §3.11 ("A Claim Without Evidence Is A Guess") names that evidence, for a change the site shows, as
  part of what counts as evidence.
- **Debugging (`.claude/agents/debug-local.md`, Step 4 Verify).** A bug a user sees is verified with a
  Playwright run that reproduces it before the fix and passes after, with screenshots of both. This is
  REQ-GOV-001's "reproduced against pre-fix code before a fix is written", carried into the browser.

The guideline text and Rule 2.5's classifying-reply text are the same in both repositories except the
no-silent-fallbacks rule's number (stocks Rule 3.7, solyra Rule 4).

Capacity: n/a. No workload runs differently.

## Risks

- A longer first review. That is the trade wanted: one long review instead of several short ones.
- Reviewers may ignore it. Nothing enforces the guidelines; the missed count is the signal, and it is
  a lower bound, since a miss that no later review raises is never counted.
- An extra reply per later finding, and a comment recording a clean first review's SHA. Each is one line.
- Chromium may not run in a given session. The PR then says so: a solyra change cites solyra's CI e2e run. A stocks change's deployed-site runs sign in interactively, so they are the owner's close-out steps either way.
