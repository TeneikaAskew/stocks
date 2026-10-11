---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-11-feat-cicd-001-review-guidelines.md
branch: feature/feat-cicd-001-review-guidelines
pr: null
status: ready
---

# Review guidelines and browser proof (stocks) implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`)
> syntax for tracking. Every task cites a spec section and the done_when item it advances.

**Goal:** Give every reviewer of a stocks pull request a `## Review guidelines` section in `AGENTS.md`
that asks for the complete review in the first round and for browser proof of a visible change; give
authors the classifying reply and the corrected reviewed-head check in CLAUDE.md Rule 2.5 and the two
places that quote it; and take the retired `solyra-api-prod` out of the process files.

**Architecture:** Edits to process documents only (`AGENTS.md`, `CLAUDE.md`,
`.github/pull_request_template.md`, `.claude/commands/resolve-issue.md`,
`.claude/agents/debug-local.md`, `.github/prompts/architecture.md`), then the FEAT-CICD-001 product
records. Each task's failing test is a clause check: every clause of the done_when item it moves, in
the spec's words, must be present in the named section. It fails on `origin/main` (output quoted per
task) and passes after the edit. The exact text of every edit is in this plan and was applied to a
scratch copy of `origin/main` at `1a6ff45e`, where every check below passed, the docs audit reported
nothing new, and `git grep -n solyra-api-prod -- .claude .github` printed only lines that say retired.

**Tech Stack:** Markdown; Python 3 (`$SCRATCH/clause_check.py`, `scripts/gate/spec_gate.py`,
`scripts/maintenance/docs_audit.py`); git.

**Spec:** `docs/superpowers/specs/2026-10-11-feat-cicd-001-review-guidelines.md` (lands on `main` via stocks#1377). Read it with this plan.

## Global Constraints

- **The spec lands first.** Cut the branch only after stocks#1377 has merged: the gate reads the approved
  spec and the catalog row from the base and refuses a plan whose spec is not there. Check:
  `git fetch origin main && git show origin/main:docs/superpowers/specs/2026-10-11-feat-cicd-001-review-guidelines.md | sed -n 16p` prints `status: approved`.
- **One branch, one PR.** `feature/feat-cicd-001-review-guidelines`, cut from `origin/main` in a worktree
  (superpowers:using-git-worktrees). PR title starts `FEAT-CICD-001:`. Never rebase, amend or
  force-push a pushed commit; bring in a moved `main` with `git merge origin/main`.
- **Before every commit** run `python3 scripts/gate/spec_gate.py --commit` (expect `spec gate ok`).
  Commit messages: `type: description`, imperative, no AI attribution, no Claude signature, no 🤖
  (CLAUDE.md §2 "Git Commit Guidelines").
- **Shared text.** The `## Review guidelines` section (Task 1) and the two Rule 2.5 subsections (Task 2)
  are byte-identical to the solyra plan's, except `Rule 3.7` here and `Rule 4` there (spec § Design, last
  paragraph). Paste them as given and do not rewrap them.
- **Anchors.** Line numbers are `origin/main` at `1a6ff45e` (2026-10-10). An earlier task moves later
  line numbers in the same file, so find each edit by its quoted old text; every quoted old text occurs
  exactly once in its file.
- **The retired service.** A line under `.claude/` or `.github/` that names `solyra-api-prod` says
  "retired" on the same physical line, because done_when[6] is a line-based grep.
- **Review cap: two rounds** (CLAUDE.md "Review cap", product-delivery Phase 4). After the second round
  raises a finding: split, re-cut or discard; no third round.
- **PR-body evidence.** What follows a ticked done_when item is scanned by the gate's `DEFERRAL` pattern
  (`scripts/gate/spec_gate.py`); the item's own words are not. Do not write `Phase 8`, `Phase 9`,
  `pending`, `after the merge`, `follow-up`, `to follow`, `skipped`, `partial`, `TODO`, `later PR`,
  `not yet …`, `out of scope` or `in progress` after an item. Task 7 runs the gate on the body to prove it.
- **Capacity** (CLAUDE.md rule 0): `n/a: process documents and one model prompt; no workload runs
  differently` (spec: "Capacity: n/a").

Two helper scripts, saved outside the checkout. `$SCRATCH` below is any directory outside the
repository (the session scratchpad works); set it once per shell: `export SCRATCH=<dir>`.

`$SCRATCH/clause_check.py`: the test every documentation task runs, red on `origin/main`, green
after the edit. It checks that each clause appears in the named section after dropping backticks
and asterisks, folding quotes and collapsing line wraps, so a clause the edit wraps across lines
still counts:

````python
#!/usr/bin/env python3
"""clause_check.py FILE START_RE END_RE CLAUSE...

Every CLAUSE must appear in FILE between the first line matching START_RE and the next line
matching END_RE (end of file if none). Both sides are normalized first: backticks and asterisks
dropped, curly and single quotes folded to ", whitespace (line wraps included) collapsed,
lowercased. Prints each missing clause and a count; exits 1 if the section or any clause is
missing.
"""
import re
import sys

path, start, end, *clauses = sys.argv[1:]
lines = open(path, encoding="utf-8").read().splitlines()
i = next((n for n, line in enumerate(lines) if re.search(start, line)), None)
if i is None:
    print(f"{path}: no line matches {start!r}; 0/{len(clauses)} clauses present")
    sys.exit(1)
j = next((n for n in range(i + 1, len(lines)) if re.search(end, lines[n])), len(lines))


def norm(s: str) -> str:
    s = re.sub(r"[`*]", "", s)
    for q in ("“", "”", "‘", "’", "'"):
        s = s.replace(q, '"')
    return re.sub(r"\s+", " ", s).strip().lower()


body = norm("\n".join(lines[i:j]))
missing = [c for c in clauses if norm(c) not in body]
for c in missing:
    print("MISSING:", c)
print(f"{path} lines {i + 1}-{j}: {len(clauses) - len(missing)}/{len(clauses)} clauses present")
sys.exit(1 if missing else 0)
````

`$SCRATCH/audit_diff.py`: the docs-audit comparison the close-out runs:

````python
#!/usr/bin/env python3
"""audit_diff.py MAIN_JSON BRANCH_JSON: findings the branch has and main does not.

A finding is keyed by (check, doc, detail), so line numbers that move do not count as new."""
import json
import sys

key = lambda p: {(f["check"], f["doc"], f.get("detail")) for f in json.load(open(p))["findings"]}
new = sorted(key(sys.argv[2]) - key(sys.argv[1]), key=str)
for f in new:
    print("NEW:", f)
print(f"{len(new)} new finding(s) over main")
sys.exit(1 if new else 0)
````

## Review Focus

1. **A clause split by a line wrap.** A reader who greps for a done_when phrase misses it when the
   edit wraps it; `clause_check.py` collapses wraps, so every task checks with it rather than with
   `grep`. Covered by every task's check.
2. **A `solyra-api-prod` line that says "retired" only on the next line.** The done_when[6] grep is
   per line and would print it. Task 5 runs the grep with `grep -v retired` and expects no output.
3. **The trigger list quoted in `resolve-issue.md` drifting from CLAUDE.md §2.5's sentence.** Task 3
   checks CLAUDE.md's sentence and Task 4 checks that `resolve-issue.md` quotes the same sentence.
4. **The cap stopping a PR whose second round is clean.** A second round with no findings must still
   merge. Task 4 checks the step says "a second round with no findings goes on to step 6".
5. **A ticked box the gate refuses, or a same-day catalog record.** Evidence text can trip
   `DEFERRAL`, and another FEAT-CICD-001 PR merged the same day (the generated-docs-render work has an
   approved spec on `main`) leaves Last reviewed already at that date, so a date-only edit reads as
   unchanged. Task 7 also edits the record's Code field and runs the gate with the PR body before the
   PR is marked ready.

---

## Task 1: `## Review guidelines` in `AGENTS.md`

Spec: § Design, "Review guidelines (`AGENTS.md`)". Advances done_when[0].

**Files:**
- Create: `docs/superpowers/plans/2026-10-11-feat-cicd-001-review-guidelines.md` (this plan, committed first)
- Modify: `AGENTS.md` (7 lines on main; the section is appended after line 7)

**Interfaces:**
- Produces: the heading `## Review guidelines` and its subsections (`### The first review is the
  complete one`, `### Later reviews`, `### Problems this pull request did not cause`, `### Browser proof`),
  which Task 2's Rule 2.5 text, Task 6's §3.11 sentence and debug-local item point to by name.

- [ ] **Step 1: Commit this plan, alone, as the branch's first commit**

```bash
cp /path/to/plan-review-guidelines-stocks.md docs/superpowers/plans/2026-10-11-feat-cicd-001-review-guidelines.md
python3 scripts/gate/spec_gate.py --commit   # expect: spec gate ok
git add docs/superpowers/plans/2026-10-11-feat-cicd-001-review-guidelines.md
git commit -m "docs: add the FEAT-CICD-001 review guidelines plan"
```

- [ ] **Step 2: Run the check (expect FAIL)**

```bash
python3 "$SCRATCH/clause_check.py" AGENTS.md '^## Review guidelines' '^## (?!Review guidelines)' \
  "A reviewer's first review of a pull request is the complete one" \
  "it reads every changed file in full, generated files included, and the direct callers and callees of what changed" \
  "where a changed file's generator runs in the reviewer's environment it re-runs it and compares" \
  "it posts, against the revision it reviews, every finding it can raise on a defect the pull request introduces or makes worse, at every severity, with one finding per defect class listing each location" \
  "it checks the edges a change creates (errors and rejections, late or out-of-order responses, signed-out and other-account states, empty and null data, and the docs, tests and generated files that cite what changed)" \
  "no-silent-fallbacks rule, CLAUDE.md Rule 3.7" \
  "A spec PR is reviewed against the code it will change" \
  "each done_when item that describes behavior must fail against a broken implementation" \
  "A later review by the same reviewer checks its earlier findings, then the new commits, and still posts a defect it finds in what its first review covered, for the author to classify under CLAUDE.md Rule 2.5" \
  "A problem the pull request neither introduces nor makes worse is not posted as a finding (a reviewer who can open an issue may open one)" \
  "A change a user can see in the site carries Playwright evidence from a run that exercises the changed code: solyra's hermetic suite for a solyra change; for a stocks change, an API test of the changed response in the PR, while runs against the deployed site before the merge and once staging has deployed it are close-out steps the owner posts on the PR, not boxes the PR ticks" \
  "screenshots of the state each run shows, which the test saves with page.screenshot into its output directory under test-results/" \
  "where the e2e workflow's playwright-report artifact keeps them 7 days" \
  "described state by state in a PR comment and kept in the e2e run's playwright-report artifact (saved under test-results/, kept 7 days) or sent to the owner" \
  "the reviewer asks for the hermetic run or the API test when the PR lacks it"
```

Expected on main: `AGENTS.md: no line matches '^## Review guidelines'; 0/15 clauses present`, exit 1.

- [ ] **Step 3: Append the section**

Append one blank line and then this text after line 7 (`(the vendored skills), as Phase 0 of the
product-delivery skill sets out.`), so the file ends with it:

````markdown
## Review guidelines

For every reviewer of a pull request in this repository: Codex, which reads this section; Claude,
which CLAUDE.md Rule 2.5 sends here; and a person. stocks and solyra carry the same guidelines.

### The first review is the complete one

A reviewer's first review of a pull request is the complete one. A pull request gets at most two
review rounds (CLAUDE.md, "Review cap"), an approved spec does not change in place, and Codex's code
review runs again when new commits are pushed to a pull request open for review, so a finding held
back costs a round, and on a spec PR a whole re-cut PR. Before it posts:

- It reads every changed file in full, generated files included, and the direct callers and callees
  of what changed, and where a changed file's generator runs in the reviewer's environment it re-runs
  it and compares.
- It posts, against the revision it reviews, every finding it can raise on a defect the pull request
  introduces or makes worse, at every severity, with one finding per defect class listing each
  location. When a finding is one instance of a class, it searches for every instance before it
  posts the class.
- It checks the edges a change creates (errors and rejections, late or out-of-order responses,
  signed-out and other-account states, empty and null data, and the docs, tests and generated files
  that cite what changed). Empty and null data are judged by this repository's no-silent-fallbacks
  rule, CLAUDE.md Rule 3.7.
- A spec PR is reviewed against the code it will change: the reviewer opens each file the spec names
  and checks that every `done_when` item can be met, and each `done_when` item that describes
  behavior must fail against a broken implementation. Items that record delivery (the gate, the docs
  audit, the catalog row) are only checked for being met.

### Later reviews

A later review by the same reviewer checks its earlier findings, then the new commits, and still
posts a defect it finds in what its first review covered, for the author to classify under CLAUDE.md
Rule 2.5.

### Problems this pull request did not cause

A problem the pull request neither introduces nor makes worse is not posted as a finding (a reviewer
who can open an issue may open one), since every thread holds the merge (REQ-GOV-001).

### Browser proof

A change a user can see in the site carries Playwright evidence from a run that exercises the
changed code: solyra's hermetic suite for a solyra change; for a stocks change, an API test of the
changed response in the PR, while runs against the deployed site before the merge and once staging
has deployed it are close-out steps the owner posts on the PR, not boxes the PR ticks.

- solyra's hermetic suite (`npm run e2e`) intercepts every `/api` call, so it cannot prove a stocks
  change. The API test in the stocks PR is that proof.
- The deployed-site runs are the owner's: staging's trigger deploys from `main`, deploying a stocks
  branch with `platform/deploy.sh` would put unreviewed code behind the live site, and the deployed
  site's sign-in is interactive (`npm run e2e:cloud:auth` runs headed).
- Each run carries screenshots of the state each run shows, which the test saves with
  `page.screenshot` into its output directory under `test-results/` (`testInfo.outputPath(...)`),
  where the e2e workflow's `playwright-report` artifact keeps them 7 days. The test takes them itself
  because `npm run e2e` runs with Playwright's screenshot option off; solyra's e2e workflow uploads
  `test-results/` in that artifact.
- The screenshots are described state by state in a PR comment and kept in the e2e run's
  `playwright-report` artifact (saved under `test-results/`, kept 7 days) or sent to the owner, since
  images cannot be attached to a PR from a Claude Code session.

The reviewer asks for the hermetic run or the API test when the PR lacks it.
````

- [ ] **Step 4: Run the check again (expect PASS)**

Same command as Step 2. Expected: `15/15 clauses present`, exit 0.

- [ ] **Step 5: Commit**

```bash
python3 scripts/gate/spec_gate.py --commit
git add AGENTS.md
git commit -m "docs: add review guidelines to AGENTS.md"
```

## Task 2: Rule 2.5, the reviewer pointer and the classifying reply

Spec: § Design, "The classifying reply (CLAUDE.md Rule 2.5)". Advances done_when[1].

**Files:**
- Modify: `CLAUDE.md:195-197` (between the last bullet of `#### Resolving is part of the fix` and the
  heading `#### A resolved thread is not a reviewed commit`)

**Interfaces:**
- Consumes: Task 1's heading `## Review guidelines`.
- Produces: `#### Reviewing a pull request` and `#### A finding raised after a reviewer's first review`
  in Rule 2.5. Tasks 3 and 4 cite "CLAUDE.md Rule 2.5" for the classifying reply; Task 1's text cites
  it for "the author to classify".

- [ ] **Step 1: Run the check (expect FAIL)**

```bash
python3 "$SCRATCH/clause_check.py" CLAUDE.md '^### 2\.5\.' '^### 3\.' \
  "a thread holding a finding that a reviewer posted after its own first review is not resolved until a reply on it classifies each location, taking the first class that applies" \
  "uncounted (not a defect, a defect the pull request neither introduces nor makes worse, or one that first review raised there)" \
  "missed (the pull request had introduced or worsened it by the commit that first review covered, named by SHA)" \
  "or new (a later commit introduced or worsened it, named by SHA)" \
  "A reviewer is one account, split by review type where the account runs separately triggered types (Codex's code review and its security review are two), and its first review is the earliest review it completes on the pull request, including one that posts no findings" \
  "A first review that posts no findings leaves no review object" \
  "the commit it covered is the one Codex's review-summary comment shows for that review type when that row first reads Completed" \
  "the author records that SHA in a PR comment then, since the next run replaces the row" \
  "A reviewer of a pull request here" \
  "follows AGENTS.md's ## Review guidelines"
```

Expected on main: `0/10 clauses present`, exit 1.

- [ ] **Step 2: Insert the two subsections**

Old text (lines 195-197):

````markdown
- If the fix landed in a different PR, say which one.

#### A resolved thread is not a reviewed commit
````

New text:

````markdown
- If the fix landed in a different PR, say which one.

#### Reviewing a pull request

A reviewer of a pull request here, Claude included, follows
`AGENTS.md`'s `## Review guidelines`: its first review is the complete one.
Claude Code loads this file and not `AGENTS.md`, so this is where a Claude
reviewer is sent to them.

#### A finding raised after a reviewer's first review

A reviewer is one account, split by review type where the account runs
separately triggered types (Codex's code review and its security review are
two), and its first review is the earliest review it completes on the pull
request, including one that posts no findings (REQ-GOV-003).

A thread holding a finding that a reviewer posted after its own first review
is not resolved until a reply on it classifies each location, taking the
first class that applies: uncounted (not a defect, a defect the pull request
neither introduces nor makes worse, or one that first review raised there),
missed (the pull request had introduced or worsened it by the commit that
first review covered, named by SHA), or new (a later commit introduced or
worsened it, named by SHA). The missed count per reviewer and pull request is
the lower bound REQ-GOV-003 keeps on what a first review misses.

A first review that posts no findings leaves no review object, so the commit
it covered is the one Codex's review-summary comment shows for that review
type when that row first reads Completed, and the author records that SHA in
a PR comment then, since the next run replaces the row:
`First Codex code review: Completed on <sha>, no findings.`

#### A resolved thread is not a reviewed commit
````

- [ ] **Step 3: Run the check again (expect PASS)**

Same command. Expected: `10/10 clauses present` once Task 3 has also run;
after this task alone the range ends earlier and the count is the same 10/10, exit 0.

- [ ] **Step 4: Commit**

```bash
python3 scripts/gate/spec_gate.py --commit
git add CLAUDE.md
git commit -m "docs: classify findings raised after a first review in Rule 2.5"
```

## Task 3: a reviewed head, in §2.5 and the PR template's Merge gate

Spec: § Design, "A reviewed head (CLAUDE.md §2.5)". Advances done_when[2] and the template half of
done_when[3].

**Files:**
- Modify: `CLAUDE.md:202-220` (the first three paragraphs and the numbered list under
  `#### A resolved thread is not a reviewed commit`; lines 199-200 and 222-223 stay)
- Modify: `.github/pull_request_template.md:66-73` (Merge gate items two and three)

**Interfaces:**
- Produces: the trigger-list sentence Task 4 quotes verbatim in `resolve-issue.md` step 0:
  `a PR opened for review, a draft marked ready, or an explicit `@codex review` comment, and Codex's code review also runs when new commits are pushed to a PR open for review`.
- Consumes: the reviewed-head rule `.claude/commands/resolve-issue.md` step 2 already makes (lines
  4014-4075 on main), which the new paragraph names.

- [ ] **Step 1: Run both checks (expect FAIL)**

```bash
python3 "$SCRATCH/clause_check.py" CLAUDE.md '^#### A resolved thread is not a reviewed commit' '^#### Verify the claim' \
  "Codex's code review also runs when new commits are pushed to a PR open for review (the 'New commits' trigger in its review-summary comment on #1366 and #1371)" \
  "a review with no findings leaves no review object" \
  "the head counts as reviewed only when, after the PR's latest review-triggering event, a review authored by chatgpt-codex-connector[bot] was submitted naming it in commit_id, or the Code Review row of Codex's own review-summary comment reads Completed for the head's SHA, as .claude/commands/resolve-issue.md step 2 requires" \
  "a PR opened for review, a draft marked ready, or an explicit @codex review comment, and Codex's code review also runs when new commits are pushed to a PR open for review"
```

```bash
python3 "$SCRATCH/clause_check.py" .github/pull_request_template.md '^## Merge gate' '^## (?!Merge gate)' \
  "reviewed as CLAUDE.md §2.5 counts it" \
  "after the PR's latest review-triggering event, a review authored by chatgpt-codex-connector[bot] was submitted naming it in commit_id" \
  "or the Code Review row of Codex's review-summary comment reads Completed for the head's SHA" \
  "Each thread holding a finding a reviewer posted after its own first review carries the reply classifying each location before it is resolved" \
  "uncounted, missed (with the SHA of the commit the first review covered) or new (with the SHA of the later commit)"
```

Expected on main: `0/4 clauses present` and
`0/5 clauses present`, both exit 1.

- [ ] **Step 2: Replace the §2.5 paragraphs**

Old text (`CLAUDE.md:202-220`):

````markdown
Codex reviews on a fixed set of triggers: a PR opened for review, a draft
marked ready, or an explicit `@codex review` comment. **A push does not
trigger a re-review** — not a force-push, not a branch update, not a
regeneration. #953's only Codex review was of commit `40cc6a149e`, the
original blind-generated docs. The branch was then fully regenerated
twice (`f8fece0`, `a5990b2`) and merged, and Codex never saw either.
Every thread carried `is_outdated: true`, which is the tell, and it was
read past.

So resolving a thread records that *someone* answered the finding. It
says nothing about whether a reviewer has looked at what is actually
about to merge. Before merging, check both:

1. `pull_request_read` with `method: "get_reviews"` — compare each
   review's `commit_id` against the PR's current head SHA. If no review
   names the head, the head is unreviewed regardless of how many threads
   show resolved.
2. `is_outdated` on every thread. All-outdated means the review predates
   the current content entirely.
````

New text (the closing paragraph at 222-223, "When the head is unreviewed and the change is more than
cosmetic, comment `@codex review` and wait…", stays as it is):

````markdown
Codex reviews on a fixed set of triggers: a PR opened for review, a draft
marked ready, or an explicit `@codex review` comment, and Codex's code review
also runs when new commits are pushed to a PR open for review (the "New
commits" trigger in its review-summary comment on #1366 and #1371). When #953
merged, a push did not trigger a re-review: #953's only Codex review was of
commit `40cc6a149e`, the original blind-generated docs. The branch was then
fully regenerated twice (`f8fece0`, `a5990b2`) and merged, and Codex never
saw either. Every thread carried `is_outdated: true`, which is the tell, and
it was read past.

So resolving a thread records that *someone* answered the finding. It
says nothing about whether a reviewer has looked at what is actually
about to merge, and neither does the review list on its own: a review with
no findings leaves no review object (Codex reacts 👍 instead), and every reply
you post on a thread is itself a review object naming the head. So the head
counts as reviewed only when, after the PR's latest review-triggering event,
a review authored by `chatgpt-codex-connector[bot]` was submitted naming it
in `commit_id`, or the Code Review row of Codex's own review-summary comment
reads Completed for the head's SHA, as `.claude/commands/resolve-issue.md`
step 2 requires. The cutoff matters: re-marking a draft ready, or an
`@codex review` on an unchanged head, would otherwise count the older review
while the new run is still going. `get_reviews` returns oldest first, so the
current review is on the last page, and all threads `is_outdated` still
means the review predates the current content entirely.
````

The `New commits` trigger is quoted from Codex's review-summary comments: on #1371 (comment
6104454716) and #1366 (comment 6103923840) the Code Review row's "Review trigger" column reads
`New commits`, and both comments are authored by `chatgpt-codex-connector[bot]` (read 2026-10-11).

- [ ] **Step 3: Replace the template's Merge gate items**

Old text (`.github/pull_request_template.md:66-73`):

````markdown
- [ ] Zero unresolved threads: each one fixed-and-resolved (naming what
      changed and the covering test/commit) or replied to with why not
- [ ] A review exists for the **current head SHA** — compare `get_reviews`
      `commit_id` against head; all threads `is_outdated` means the head is
      unreviewed → comment `@codex review` and wait.
      `get_reviews` returns OLDEST FIRST, so the current review is on the
      LAST page: reading page 1 and finding an older "no findings" is how
      #991 was merged two minutes after a review it never saw
````

New text:

````markdown
- [ ] Zero unresolved threads: each one fixed-and-resolved (naming what
      changed and the covering test/commit) or replied to with why not
- [ ] Each thread holding a finding a reviewer posted after its own first
      review carries the reply classifying each location before it is
      resolved: uncounted, missed (with the SHA of the commit the first
      review covered) or new (with the SHA of the later commit), as
      CLAUDE.md Rule 2.5 says
- [ ] The **current head** is reviewed as CLAUDE.md §2.5 counts it: after
      the PR's latest review-triggering event, a review authored by
      `chatgpt-codex-connector[bot]` was submitted naming it in `commit_id`,
      or the Code Review row of Codex's review-summary comment reads
      Completed for the head's SHA (a clean review leaves no review object,
      so read the row). `get_reviews` returns OLDEST FIRST, so the current
      review is on the LAST page: reading page 1 and finding an older "no
      findings" is how #991 was merged two minutes after a review it never
      saw. Unreviewed → comment `@codex review` and wait
````

- [ ] **Step 4: Run both checks again (expect PASS)**

Same commands. Expected: `4/4 clauses present` and `5/5 clauses present`, exit 0. Also `grep -n "A push does not" CLAUDE.md` prints nothing (exit 1).

- [ ] **Step 5: Commit**

```bash
python3 scripts/gate/spec_gate.py --commit
git add CLAUDE.md .github/pull_request_template.md
git commit -m "docs: count a head as reviewed by review or summary row after the latest trigger"
```

## Task 4: `resolve-issue.md` Phase 8, the review steps

Spec: § Design, "A reviewed head (CLAUDE.md §2.5)", its last sentence (the two places that quote the
old paragraph). Advances done_when[3].

**Files:**
- Modify: `.claude/commands/resolve-issue.md` Phase 8 (`## Phase 8 — Merge gate (Rule 2.5)`, line
  3982 on main): step 0 at 3994-3995, step 1 at 4009-4013, step 2 at 4031, step 3 at 4089-4092,
  step 5 at 4117-4123, step 6 at 4127-4128

**Interfaces:**
- Consumes: Task 3's trigger sentence (quoted verbatim in step 0) and Task 2's Rule 2.5 classifying
  reply (cited in steps 3, 5 and 6).

- [ ] **Step 1: Run the check (expect FAIL)**

```bash
python3 "$SCRATCH/clause_check.py" .claude/commands/resolve-issue.md '^## Phase 8' '^## Phase 9' \
  "(CLAUDE.md §2.5: \"a PR opened for review, a draft marked ready, or an explicit @codex review comment, and Codex's code review also runs when new commits are pushed to a PR open for review\")" \
  "One PR can carry several reviews' threads" \
  "If step 4 produced a commit for a finding from the PR's first review round, go back to step 1 on the new head" \
  "after a PR's second review round, stop and split, re-cut or discard it" \
  "a second round with no findings goes on to step 6" \
  "A thread holding a finding that a reviewer posted after its own first review is resolved only after a reply on it classifies each location"
```

Expected on main: `0/6 clauses present`, exit 1.

- [ ] **Step 2: Step 0, the quoted trigger list** (lines 3994-3995)

Old:

````markdown
   review trigger** (CLAUDE.md §2.5: "a PR opened for review, a draft marked
   ready, or an explicit `@codex review`"). Undrafting after the review checks
````

New:

````markdown
   review trigger** (CLAUDE.md §2.5: "a PR opened for review, a draft marked
   ready, or an explicit `@codex review` comment, and Codex's code review also
   runs when new commits are pushed to a PR open for review"). Undrafting after the review checks
````

- [ ] **Step 3: Step 1, paging** (lines 4009-4013; "Nine review rounds on one PR is not hypothetical
  here" goes)

Old:

````markdown
   after, and **page it to exhaustion**. Nine review rounds on one PR is not
   hypothetical here, and a first page that happens to show every thread
   resolved says nothing about the next one. Zero unresolved means zero across
   every page, the same discipline the issue listing and `get_reviews` already
   get.
````

New:

````markdown
   after, and **page it to exhaustion**. One PR can carry several reviews'
   threads (each review type's first review, and a later review for each push
   of new commits), so a first page that happens to show every thread resolved
   says nothing about the next one. Zero unresolved means zero across every
   page, the same discipline the issue listing and `get_reviews` already get.
````

- [ ] **Step 4: Step 2, the push trigger and the cutoff** (line 4031)

Old:

````markdown
     rerun may have been requested by someone else. **On a PR that was never
````

New:

````markdown
     rerun may have been requested by someone else. A push of new commits
     triggers a review too (CLAUDE.md §2.5), but it moves the head, so the
     head-SHA test already ties the review to it. **On a PR that was never
````

- [ ] **Step 5: Step 3, the bar** (lines 4089-4092; "step 5 enforces" becomes "step 6 enforces",
  since step 6 is the one that checks zero unresolved, as line 4084 already says)

Old:

````markdown
   fix there. What follows is the bar step 5 enforces: every thread
   fixed-and-resolved, naming what changed
   and the covering test and commit, or replied to with why not. Zero unresolved
   across every page is the bar.
````

New:

````markdown
   fix there. What follows is the bar step 6 enforces: every thread
   fixed-and-resolved, naming what changed
   and the covering test and commit, or replied to with why not, and a thread
   holding a finding a reviewer posted after its own first review resolved
   only after the reply that classifies each location (CLAUDE.md Rule 2.5).
   Zero unresolved across every page is the bar.
````

- [ ] **Step 6: Step 5, the review cap replaces "There is no round limit"** (lines 4117-4123)

Old:

````markdown
5. **If step 4 produced a commit, go back to step 1 on the new head.** A fix
   commit moves the head past the review that approved it, so merging straight
   from here lets the review-fix itself merge unreviewed. That is the same
   stale-head condition steps 1-3 exist to catch, arriving by a different
   route. Push the fix, let the review re-run on the new SHA, and re-check.
   There is no round limit: repeated findings mean fix the root cause, not
   stop.
````

New:

````markdown
5. **If step 4 produced a commit for a finding from the PR's first review
   round, go back to step 1 on the new head.** A fix commit moves the head
   past the review that approved it, so merging straight from here lets the
   review-fix itself merge unreviewed. That is the same stale-head condition
   steps 1-3 exist to catch, arriving by a different route. Push the fix, let
   the review re-run on the new SHA, and re-check: that run is the PR's
   second review round.

   **The review cap is two rounds** (CLAUDE.md, "Review cap"; the
   product-delivery skill, Phase 4): after a PR's second review round, stop
   and split, re-cut or discard it when that round raised a finding; a second
   round with no findings goes on to step 6. A finding from the second round
   gets its classifying reply (CLAUDE.md Rule 2.5) and no fix commit, so there
   is no third review: present split, re-cut or discard
   (`superpowers:finishing-a-development-branch`) and name that choice in the
   Phase 9 "Still open before this closes".
````

- [ ] **Step 7: Step 6, the classifying reply before a later finding's thread resolves** (lines
  4127-4128)

Old:

````markdown
   to be looked at rather than assumed empty. Then CI green on the current
   head, and no merge conflict.
````

New:

````markdown
   to be looked at rather than assumed empty. A thread holding a finding that
   a reviewer posted after its own first review is resolved only after a
   reply on it classifies each location: uncounted, missed (with the SHA of
   the commit that first review covered) or new (with the SHA of the later
   commit), as CLAUDE.md Rule 2.5 says. Then CI green on the current head,
   and no merge conflict.
````

- [ ] **Step 8: Run the check again (expect PASS)**

Same command. Expected: `6/6 clauses present`, exit 0. And
`grep -n "There is no round limit\|Nine review rounds" .claude/commands/resolve-issue.md` prints
nothing (exit 1).

- [ ] **Step 9: Commit**

```bash
python3 scripts/gate/spec_gate.py --commit
git add .claude/commands/resolve-issue.md
git commit -m "docs: cap resolve-issue at two review rounds and classify later findings"
```

## Task 5: the deploy step and the architecture prompt describe one API service

Spec: § Design, "The retired service in process files". Advances done_when[6].

**Files:**
- Modify: `.claude/commands/resolve-issue.md` Phase 8 step 8: lines 4159-4163 (the cited staging
  file), 4664-4665 (the build-id note), 4681-4774 (the promotion paragraph through the end of the
  owner-action bullet)
- Modify: `.github/prompts/architecture.md:92-95` (the first of "Two facts to keep asserting")

**Interfaces:**
- Consumes: `gcp/cloudbuild/deploy-solyra-api-staging-cloudbuild.yaml:2-8` (the `includedFiles`
  caveat, kept) and `:24-26` ("the one API service since solyra-api-prod and its deploy-solyra-api-prod
  promote trigger were retired on 2026-10-10"); `gcp/cloudbuild/serving_revision.py` (reads `gcloud run
  services describe … --format=json` on stdin, prints the serving revision).

- [ ] **Step 1: Run the checks (expect FAIL)**

```bash
git grep -n solyra-api-prod -- .claude .github
git grep -n solyra-api-prod -- .claude .github | grep -v retired   # lines that do not say retired
grep -c "promote_to_prod\|_EXPECT_STAGING_REVISION\|STAGING_VERIFIED" .claude/commands/resolve-issue.md
```

```bash
python3 "$SCRATCH/clause_check.py" .claude/commands/resolve-issue.md '^## Phase 8' '^## Phase 9' \
  "the staging deploy that a merge to main starts is the deployment" \
  "That staging deploy is the deployment." \
  "the trigger's includedFiles is platform/**, lib/**, requirements.txt, gcp/database.py" \
  "staging_serving_revision"
```

```bash
python3 "$SCRATCH/clause_check.py" .github/prompts/architecture.md '^## Two facts' '^## Rules' \
  "The API is served by ONE API-only Cloud Run service, solyra-api-staging"
```

Expected on main: the second command prints six lines (`resolve-issue.md:4161`, `:4684`, `:4690`,
`:4753`, `:4763`, `architecture.md:92`), the count is `8`, the deploy check is `1/4` (only the kept
`includedFiles` clause) and the prompt check `0/1`, both exit 1.

- [ ] **Step 2: The cited staging file** (lines 4159-4163)

Old:

````markdown
   `gcp/cloudbuild/deploy-solyra-api-staging-cloudbuild.yaml:26` says it
   outright: *"Merging to main NEVER touches prod. Prod moves only when a human
   runs the `deploy-solyra-api-prod` trigger."* And the staging build itself is
   conditional — the same file records that the trigger's `includedFiles` is
   `platform/**, lib/**, requirements.txt, gcp/database.py`, so a fix under
````

New (lines 4164-4166 on main, "`scripts/` or `gcp/` that an API route imports … `./gcp/deploy.sh
<target>`.", stay):

````markdown
   `gcp/cloudbuild/deploy-solyra-api-staging-cloudbuild.yaml:24-26` says the
   trigger deploys `solyra-api-staging`, the one API service since
   `solyra-api-prod` and its promote trigger were retired on 2026-10-10, so
   the staging deploy that a merge to `main` starts is the deployment for an
   API change. That build is conditional — the same file records (lines 2-8)
   that the trigger's `includedFiles` is
   `platform/**, lib/**, requirements.txt, gcp/database.py`, so a fix under
````

- [ ] **Step 3: The build-id note** (lines 4664-4665)

Old:

````markdown
     which you then watch go green and promote, shipping the revision staging
     was already serving.
````

New:

````markdown
     which you then watch go green and verify against, while staging still
     serves the revision it was already serving.
````

- [ ] **Step 4: Replace the promotion procedure with the staging verification**

Replace the 94 lines from `Then validate against staging and read its serving revision, as below.` (line 4681 on main) through the line
`to prevent.` (line 4774), which ends the bullet `- **Where promotion is an owner
action this session cannot take**`, with the text below. This removes "**Staging is not the end of
it.**", the `_EXPECT_STAGING_REVISION` explanation, `promote_to_prod()` and the
`deploy-solyra-api-prod` trigger run; it keeps the serving-revision read (as
`staging_serving_revision`) and the keep-the-issue-open bullet. The next line, the paragraph `**A
completed review with no findings posts no review at all**` (4776), stays.

````markdown
     Then verify the fix against staging: re-run THIS ISSUE's reproduction
     from Phase 4 — the failing-before test — against the staging URL, and
     read which revision staging is serving while you do. **That staging
     deploy is the deployment.** `solyra-api-staging` is the only API service:
     `solyra-api-prod` and its `deploy-solyra-api-prod` trigger were retired on 2026-10-10 (#1366),
     so there is no promotion step after it, and the reproduction passing
     against the revision you read is the production evidence Phase 9 asks for.

     Read the revision with the repo's own helper, not
     `latestReadyRevisionName`. `gcp/cloudbuild/serving_revision.py` exists
     because the two differ whenever staging was rolled back, is split across
     revisions, or was deployed `--no-traffic`, and in each of those the latest
     ready revision is precisely the one nobody validated. It also fails loud on
     nothing-serving or a traffic split, rather than picking one. A function,
     with `--project` resolved once, for the reasons the blocks above give:

     ```bash
     staging_serving_revision() {
       local PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project)}" REV
       test -n "$PROJECT_ID" || { echo "no project resolved"; return 1; }
       REV=$(gcloud run services describe solyra-api-staging \
               --project="$PROJECT_ID" --region=us-east1 \
               --format=json | python gcp/cloudbuild/serving_revision.py) \
         || { echo "could not read the staging serving revision"; return 1; }
       test -n "$REV" || { echo "staging is serving nothing, or is split"; return 1; }
       echo "staging is serving $REV"
     }
     staging_serving_revision     # BARE — see the note above
     ```

     Run it before and after the reproduction. If the revision changed in
     between, something else deployed while you were checking: verify again
     against the new one. Paste both reads and the reproduction's output in
     the Phase 9 status comment, naming the revision.
   - **Where the staging deploy or its verification is an owner action this
     session cannot take**, keep the issue OPEN, put the exact command in
     "Still open before this closes", and say the fix is merged but not yet
     verified as serving. Closing on candidate evidence while calling it
     production proof is the failure this whole phase exists to prevent.
````

- [ ] **Step 5: The architecture prompt** (lines 92-95)

Old:

````markdown
- **The API is served by TWO API-only Cloud Run services**: `solyra-api-prod`
  behind IAP, and `solyra-api-staging` on a public edge gated per request by a
  Firebase ID token. The React frontend left this repo in #957 and lives at
  github.com/TeneikaAskew/solyra; the image contains no SPA.
````

New:

````markdown
- **The API is served by ONE API-only Cloud Run service**, `solyra-api-staging`,
  on a public edge gated per request by a Firebase ID token.
  `solyra-api-prod` (behind IAP) and its `deploy-solyra-api-prod` trigger were retired on 2026-10-10
  (#1366): never describe either as live, and write the services table, the
  diagram and the deploy path with the one service. The React frontend left
  this repo in #957 and lives at github.com/TeneikaAskew/solyra; the image
  contains no SPA.
````

- [ ] **Step 6: Run the checks again (expect PASS)**

Same commands. Expected: `git grep -n solyra-api-prod -- .claude .github` prints exactly three lines,
each saying retired (`resolve-issue.md` in step 8's staging paragraph and its verification paragraph,
`architecture.md:94`); the `grep -v retired` line prints nothing; the count is `0`; the deploy check
`4/4` and the prompt check `1/1`, exit 0.

- [ ] **Step 7: Commit**

```bash
python3 scripts/gate/spec_gate.py --commit
git add .claude/commands/resolve-issue.md .github/prompts/architecture.md
git commit -m "docs: treat the staging deploy as the deployment now prod is retired"
```

## Task 6: browser evidence in §3.11 and in debug-local's Verify step

Spec: § Design, "Evidence rules (`CLAUDE.md`)" and "Debugging (`.claude/agents/debug-local.md`, Step 4
Verify)". Advances done_when[4] and done_when[5].

**Files:**
- Modify: `CLAUDE.md:794-796` (the "Evidence means" paragraph of §3.11)
- Modify: `.claude/agents/debug-local.md:80` (after item 4 of `### Step 4 — Verify`)

**Interfaces:**
- Consumes: Task 1's `## Review guidelines` ("Browser proof"), which both new sentences point to.

- [ ] **Step 1: Run the checks (expect FAIL)**

```bash
python3 "$SCRATCH/clause_check.py" CLAUDE.md '^### 3\.11\.' '^#### A doc is a claim' \
  "For a change the site shows" \
  "Playwright evidence as AGENTS.md's ## Review guidelines define it: an API test of the changed response in the PR, and runs against the deployed site before the merge and once staging has deployed it, which the owner posts on the PR as close-out steps, with screenshots of the state each shows"
```

```bash
python3 "$SCRATCH/clause_check.py" .claude/agents/debug-local.md '^### Step 4' '^### Step 5' \
  "A bug a user sees in the site is verified with a Playwright run that reproduces it before the fix and passes after it, with screenshots of both: an API test of the fixed response in the PR that fails before the fix and passes after it, and runs against the deployed site that reproduce it before the merge and pass once staging has deployed the fix, which the owner posts on the PR as close-out steps"
```

Expected on main: `0/2 clauses present` and
`0/1 clauses present`, both exit 1.

- [ ] **Step 2: §3.11's definition of evidence** (`CLAUDE.md:794-796`)

Old:

````markdown
Evidence means `EXPLAIN (ANALYZE, BUFFERS)`, a live `gcloud` read, a log query,
or a test run — **with the output shown**. Not a doc, not a code comment, not a
plausible mechanism.
````

New:

````markdown
Evidence means `EXPLAIN (ANALYZE, BUFFERS)`, a live `gcloud` read, a log query,
or a test run — **with the output shown**. Not a doc, not a code comment, not a
plausible mechanism. For a change the site shows, evidence includes Playwright
evidence as `AGENTS.md`'s `## Review guidelines` define it: an API test of the
changed response in the PR, and runs against the deployed site before the merge
and once staging has deployed it, which the owner posts on the PR as close-out
steps, with screenshots of the state each shows.
````

- [ ] **Step 3: debug-local Step 4, item 5** (after line 80)

Old:

````markdown
4. Verify no regressions in adjacent features
````

New:

````markdown
4. Verify no regressions in adjacent features
5. A bug a user sees in the site is verified with a Playwright run that reproduces it before the
   fix and passes after it, with screenshots of both: an API test of the fixed response in the PR
   that fails before the fix and passes after it, and runs against the deployed site that
   reproduce it before the merge and pass once staging has deployed the fix, which the owner posts
   on the PR as close-out steps (`AGENTS.md`, `## Review guidelines`, "Browser proof"). This is
   REQ-GOV-001's "reproduced against pre-fix code before a fix is written", carried into the
   browser.
````

- [ ] **Step 4: Run the checks again (expect PASS)**

Same commands. Expected: `2/2` and `1/1`, exit 0.

- [ ] **Step 5: Commit**

```bash
python3 scripts/gate/spec_gate.py --commit
git add CLAUDE.md .claude/agents/debug-local.md
git commit -m "docs: count Playwright runs as evidence for a change the site shows"
```

## Task 7: close-out, product records, docs audit and gate

Spec: done_when[7] and done_when[8] (delivery records; the product-delivery skill, Phase 5). Advances
done_when[7] and done_when[8].

**Files:**
- Modify: `docs/product/02-FEATURE-CATALOG.md:584` (`| Last reviewed | 2026-08-30 |`) and `:590`
  (`` | Code | `.github/workflows/` | ``) in the `### FEAT-CICD-001` record (lines 573-594); Status (580)
  stays `Production but needs remediation`
- Modify: `docs/product/12-PR-ISSUE-TRACEABILITY.md:419` (the FEAT-CICD-001 `**PR lineage:**` line)
- Modify: `docs/superpowers/plans/2026-10-11-feat-cicd-001-review-guidelines.md` (`pr: null` → `pr: NNN`)

Touch nothing else under `docs/product/`: the gate refuses a line outside FEAT-CICD-001's record or
section, and any change to `01-PRODUCT-REQUIREMENTS.md` (REQ-GOV-003's Enforced-by column moves in a
later `docs/` PR, spec § Non-goals).

- [ ] **Step 1: Gate and docs audit before the PR opens**

```bash
python3 scripts/gate/spec_gate.py --pr origin/main          # expect: spec gate ok (branch=feature/feat-cicd-001-review-guidelines, …)
git worktree add --detach "$SCRATCH/stocks-main-audit" origin/main
(cd "$SCRATCH/stocks-main-audit" && python3 scripts/maintenance/docs_audit.py --json) > "$SCRATCH/audit-main.json"
python3 scripts/maintenance/docs_audit.py --json > "$SCRATCH/audit-branch.json"
python3 "$SCRATCH/audit_diff.py" "$SCRATCH/audit-main.json" "$SCRATCH/audit-branch.json"   # expect: 0 new finding(s) over main
git worktree remove "$SCRATCH/stocks-main-audit"
```

On `1a6ff45e` the audit summary was `changed-since 2, class-a 4, closed-issue 1, dead-link 161, marker
115, unclassified 2`; the scratch copy with every edit above gave the same summary and 0 new.

- [ ] **Step 2: Open the PR as a draft**

Title: `FEAT-CICD-001: ask reviewers for the complete first review and browser proof`. Body (copy each
done_when item exactly; the gate matches the line's start against the item):

````markdown
**FEAT-ID:** FEAT-CICD-001
**Spec:** docs/superpowers/specs/2026-10-11-feat-cicd-001-review-guidelines.md
**Plan:** docs/superpowers/plans/2026-10-11-feat-cicd-001-review-guidelines.md

## Done when (copied from the spec)
- [ ] The root AGENTS.md of this repository (stocks) has a '## Review guidelines' section that says: a reviewer's first review of a pull request is the complete one; it reads every changed file in full, generated files included, and the direct callers and callees of what changed, and where a changed file's generator runs in the reviewer's environment it re-runs it and compares; it posts, against the revision it reviews, every finding it can raise on a defect the pull request introduces or makes worse, at every severity, with one finding per defect class listing each location; it checks the edges a change creates (errors and rejections, late or out-of-order responses, signed-out and other-account states, empty and null data, and the docs, tests and generated files that cite what changed); a spec PR is reviewed against the code it will change, and each done_when item that describes behavior must fail against a broken implementation; a later review by the same reviewer checks its earlier findings, then the new commits, and still posts a defect it finds in what its first review covered, for the author to classify under CLAUDE.md Rule 2.5; a problem the pull request neither introduces nor makes worse is not posted as a finding (a reviewer who can open an issue may open one); and a change a user can see in the site carries Playwright evidence from a run that exercises the changed code: solyra's hermetic suite for a solyra change; for a stocks change, an API test of the changed response in the PR, while runs against the deployed site before the merge and once staging has deployed it are close-out steps the owner posts on the PR, not boxes the PR ticks; with screenshots of the state each run shows, described state by state in a PR comment and kept in the e2e run's playwright-report artifact (saved under test-results/, kept 7 days) or sent to the owner; the reviewer asks for the hermetic run or the API test when the PR lacks it
- [ ] CLAUDE.md Rule 2.5 says a thread holding a finding that a reviewer posted after its own first review is not resolved until a reply on it classifies each location, taking the first class that applies: uncounted (not a defect, a defect the pull request neither introduces nor makes worse, or one that first review raised there), missed (the pull request had introduced or worsened it by the commit that first review covered, named by SHA), or new (a later commit introduced or worsened it, named by SHA); it defines a reviewer and a first review as REQ-GOV-003 does; it says a first review that posts no findings leaves no review object, that the commit it covered is the one Codex's review-summary comment shows for that review type when that row first reads Completed, and that the author records that SHA in a PR comment then, since the next run replaces the row; and it tells a reviewer of a pull request to follow AGENTS.md's '## Review guidelines'
- [ ] CLAUDE.md §2.5 'A resolved thread is not a reviewed commit' says Codex's code review also runs when new commits are pushed to a PR open for review (the 'New commits' trigger in its review-summary comment on #1366 and #1371), that a review with no findings leaves no review object, and that the head counts as reviewed only when, after the PR's latest review-triggering event, a review authored by chatgpt-codex-connector[bot] was submitted naming it in commit_id, or the Code Review row of Codex's own review-summary comment reads Completed for the head's SHA, as .claude/commands/resolve-issue.md step 2 requires
- [ ] .github/pull_request_template.md's Merge gate counts the head as reviewed as §2.5 does and asks for the classifying reply on each later finding, and .claude/commands/resolve-issue.md quotes §2.5's trigger list as it now reads, resolves a later finding's thread only after that reply, replaces its 'There is no round limit' with the two-round review cap: after a PR's second review round, stop and split, re-cut or discard it, as CLAUDE.md and the product-delivery skill say, and rewords 'Nine review rounds on one PR is not hypothetical here' to say paging matters because one PR can carry several reviews' threads
- [ ] CLAUDE.md §3.11's definition of evidence includes, for a change the site shows, Playwright evidence as AGENTS.md's '## Review guidelines' define it: an API test of the changed response in the PR, and runs against the deployed site before the merge and once staging has deployed it, which the owner posts on the PR as close-out steps, with screenshots of the state each shows
- [ ] .claude/agents/debug-local.md's Verify step says a bug a user sees in the site is verified with a Playwright run that reproduces it before the fix and passes after it, with screenshots of both: an API test of the fixed response in the PR that fails before the fix and passes after it, and runs against the deployed site that reproduce it before the merge and pass once staging has deployed the fix, which the owner posts on the PR as close-out steps
- [ ] .claude/commands/resolve-issue.md's deploy step treats the staging deploy that a merge to main starts as the deployment and no longer has a promote-to-prod procedure (promote_to_prod and the deploy-solyra-api-prod trigger, deleted 2026-10-10 under #1366), .github/prompts/architecture.md describes solyra-api-staging as the only API service, and git grep -n solyra-api-prod -- .claude .github prints only lines that say it was retired
- [ ] python3 scripts/gate/spec_gate.py --pr origin/main passes on the PR head, and the docs audit reports nothing new over origin/main
- [ ] The FEAT-CICD-001 record in 02-FEATURE-CATALOG shows a current Status and Last reviewed, and 12-PR-ISSUE-TRACEABILITY lists this PR under FEAT-CICD-001

## Capacity (CLAUDE.md rule 0)
n/a: process documents and one model prompt; no workload runs differently.

Canvas refresh pending: none

## Summary
(what changed, per task; the Playwright evidence rule this PR adds does not apply to it, since no
change here is visible in the site)
````

- [ ] **Step 3: Record the PR number, the date and the lineage, in one commit**

With `NNN` the PR number and `YYYY-MM-DD` today's date as `git show -s --format=%cs HEAD` will print it for
this commit (the gate requires the head commit's committer or author date; if a later commit lands on
another day, move `YYYY-MM-DD` in that commit):

- `docs/superpowers/plans/2026-10-11-feat-cicd-001-review-guidelines.md`: `pr: null` → `pr: NNN`.
- `docs/product/02-FEATURE-CATALOG.md:584`: `| Last reviewed | 2026-08-30 |` → `| Last reviewed | YYYY-MM-DD |`.
  The same old line is in 20 other records; change only the one under `### FEAT-CICD-001`.
- `docs/product/02-FEATURE-CATALOG.md:590`: `` | Code | `.github/workflows/` | `` →
  `` | Code | `.github/workflows/`; review guidelines in `AGENTS.md` (`## Review guidelines`), merge gate in `CLAUDE.md` Rule 2.5 | ``
- `docs/product/12-PR-ISSUE-TRACEABILITY.md:419`: append
  ` · [#NNN](https://github.com/TeneikaAskew/stocks/pull/NNN) *evolution*` to the end of the line.

```bash
python3 scripts/gate/spec_gate.py --commit
git add docs/superpowers/plans/2026-10-11-feat-cicd-001-review-guidelines.md docs/product/02-FEATURE-CATALOG.md docs/product/12-PR-ISSUE-TRACEABILITY.md
git commit -m "docs: record #NNN under FEAT-CICD-001"
```

- [ ] **Step 4: Tick the boxes with evidence, then prove the ready-for-review gate locally**

Change each `- [ ]` under "Done when" to `- [x]` and append ` — <evidence>` after the item's text.
Evidence that passes the gate's deferral scan (checked against `DEFERRAL` while writing this plan):

````text
done_when[0]: — evidence: Task 1 clause check, 15/15 in the AGENTS.md section
done_when[1]: — evidence: Task 2 clause check, 10/10 in Rule 2.5
done_when[2]: — evidence: Task 3 clause check, 4/4; the Code Review rows of the summary comments on #1366 and #1371 read New commits
done_when[3]: — evidence: Task 3 template check 5/5 and Task 4 check 6/6; the round-limit and nine-rounds lines are gone
done_when[4]: — evidence: Task 6 clause check, 2/2 in §3.11
done_when[5]: — evidence: Task 6 clause check, 1/1 in Step 4
done_when[6]: — evidence: Task 5 grep, every printed line says retired; promote_to_prod count 0
done_when[7]: — evidence: spec gate ok on the head; docs audit 0 new finding(s) over origin/main
done_when[8]: — evidence: FEAT-CICD-001 record Last reviewed YYYY-MM-DD; this PR in its PR lineage
````

Save the body to `$SCRATCH/pr-body.md`, re-run the docs audit comparison from Step 1, then:

```bash
PR_BODY="$(cat "$SCRATCH/pr-body.md")" PR_TITLE="FEAT-CICD-001: ask reviewers for the complete first review and browser proof" \
PR_NUMBER=NNN PR_DRAFT=false PR_HEAD_REF=feature/feat-cicd-001-review-guidelines PR_BASE_REF=main \
  python3 scripts/gate/spec_gate.py --pr origin/main
# expect: spec gate ok
```

Then push, update the PR body on GitHub with the same text, and mark the PR ready for review. From here
CLAUDE.md Rule 2.5 governs: read the review before CI, record the first Codex review's SHA in a PR
comment if it posts no findings, give each later finding its classifying reply, and stop at two rounds.

- [ ] **Step 5: After the merge**

Owner-side, outside this PR's done_when: on a `docs/` branch set this plan's `status: done`
(product-delivery Phase 5 step 7), and move REQ-GOV-003's Enforced-by column in
`docs/product/01-PRODUCT-REQUIREMENTS.md` from "planned" to the sections this PR added (spec §
Non-goals).
