---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-11-feat-cicd-001-review-guidelines.md
branch: feature/feat-cicd-001-review-guidelines-r2
pr: 1387
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
`.github/pull_request_template.md`, `.claude/commands/resolve-issue.md`, `.claude/agents/debug-local.md`,
`.claude/agents/code-reviewer.md`, `.github/prompts/architecture.md`, `docs/DOC_REGISTRY.md`), then the
FEAT-CICD-001 product records. Each task's failing test is a clause check: every clause of the done_when
item it moves, in the spec's words, plus every clause the two review rounds added, must be present in
the named section. Each check fails on `origin/main` and passes after the edit, with the counts quoted
per task. Every edit below is an Old/New pair cut from this branch's head, and
`$SCRATCH/plan_replay.py` (Task 7) applies them all, in order, to `origin/main` at `17bbacd3` and
confirms the result equals the branch byte for byte, so the plan and the files cannot drift apart.

**Tech Stack:** Markdown; Python 3 (`$SCRATCH/clause_check.py`, `$SCRATCH/plan_replay.py`,
`scripts/gate/spec_gate.py`, `scripts/maintenance/docs_audit.py`); bash (`$SCRATCH/gate_stub_test.sh`);
git.

**Spec:** `docs/superpowers/specs/2026-10-11-feat-cicd-001-review-guidelines.md` (on `main` via stocks#1377). Read it with this plan.

## Re-cut and review history

- **#1380** (`feature/feat-cicd-001-review-guidelines`) executed the first version of this plan.
- **Round 1**, Codex's code review of `7daf2384`, four findings: debug-local's before-fix capture sat
  under "After the fix" (4240413675); resolve-issue step 4 fixed a finding before settling its round
  (4240413677); removing `promote_to_prod` also removed the fail-closed `STAGING_VERIFIED` check, leaving
  the staging verification as unenforced prose (4240413682, P1); "a first review that posts no findings
  leaves no review object" is true of Codex only (4240413683). An independent review added: `AGENTS.md`
  was unclassified in `docs/DOC_REGISTRY.md`; resolve-issue's resume notes still named a promotion;
  code-reviewer.md's "Be Proportional", "Be Efficient" and pre-existing findings contradicted the
  guidelines; step 5 had no definition of a round; the reviewed-head rule read differently in CLAUDE.md,
  the template and resolve-issue step 2; the stocks API test is pytest, not Playwright, and carries no
  screenshots; the deployed-site runs need a solyra `*.cloud.spec.ts`; debug-local's output template had
  no line for item 5. All landed in #1380 (`7e972811`..`daa0591a`), and `2b559d3d` dropped an unmeasured
  claim that `@codex security review` starts only the security review.
- **Round 2**, Codex's code review of `2b559d3d`, two findings: debug-local's unconditional "back out
  the fix" handler covered the owner's post-merge deployed-site run, which a local back-out cannot undo,
  and its output template pre-ticked that close-out (4240531081); this plan's snippets still produced
  the pre-round-1 text (4240531079).
- **The re-cut.** The review cap is two rounds, so the work moved to
  `feature/feat-cicd-001-review-guidelines-r2`, cut from `origin/main` `17bbacd3`. Its first commit
  carries #1380's tree at `2b559d3d` for every file #1380 changes (this plan naming the new branch, `pr`
  unset). Its second commit fixes both round-2 findings, and the defects of the same classes the re-cut's
  own review found: resolve-issue step 8 now says what to do when a production check fails after the
  merge, `staging_verified` is bound only after the reproduction passes, debug-local Step 2 no longer
  makes the owner's deployed-site run block writing the fix, and the gate reads the revision with
  `python3`, as `platform/deploy.sh` does. The tasks below carry the head's text.
- Task numbers are unchanged. Round-1 work sits with the task that owns its file area: the registry rows
  in Task 1, code-reviewer.md in Task 2, the reviewed-head rule in Tasks 3 and 4, the staging gate and
  the resume notes in Task 5, debug-local's before-fix capture and failure handling in Task 6.

## Global Constraints

- **The spec landed first.** The gate reads the approved spec and the catalog row from the base and
  refuses a plan whose spec is not there. Check:
  `git fetch origin main && git show origin/main:docs/superpowers/specs/2026-10-11-feat-cicd-001-review-guidelines.md | sed -n 16p` prints `status: approved`.
- **One branch, one PR.** `feature/feat-cicd-001-review-guidelines-r2`, cut from `origin/main` in a
  worktree (superpowers:using-git-worktrees). PR title starts `FEAT-CICD-001:`. Never rebase, amend or
  force-push a pushed commit; bring in a moved `main` with `git merge origin/main`.
- **Before every commit** run `python3 scripts/gate/spec_gate.py --commit` (expect `spec gate ok`).
  Commit messages: `type: description`, imperative, no AI attribution, no `Co-Authored-By` or
  `Claude-Session` trailer, no Claude signature, no 🤖 (CLAUDE.md §2 "Git Commit Guidelines").
- **Shared text.** The `## Review guidelines` section (Task 1) is byte-identical to solyra's, except
  `Rule 3.7` here and `Rule 4` there (spec § Design, last paragraph); it is not edited in this PR, and
  its corrections go to a later spec for both repositories. The Rule 2.5 subsections (Task 2) match
  solyra's except that rule number and round 1's Codex qualification of the clean-review paragraph
  (4240413683), which solyra carries in its own PR or not.
- **Anchors.** Line numbers are `origin/main` at `17bbacd3`; the target files there are unchanged
  from `1a6ff45e`, where the first version of this plan was measured. Each Old block occurs exactly once
  in its file on `main`, and `plan_replay.py` fails if one does not.
- **The retired service.** A line under `.claude/` or `.github/` that names `solyra-api-prod` says
  "retired" on the same physical line, because done_when[6] is a line-based grep.
- **Review cap: two rounds** (CLAUDE.md "Review cap", product-delivery Phase 4). After a second round
  that raises a finding: split, re-cut or discard; no third round. A second round with no findings goes
  on to the merge.
- **PR-body evidence.** What follows a ticked done_when item is scanned by the gate's `DEFERRAL` pattern
  (`scripts/gate/spec_gate.py`); the item's own words are not. Do not write `Phase 8`, `Phase 9`,
  `pending`, `after the merge`, `follow-up`, `to follow`, `skipped`, `partial`, `TODO`, `later PR`,
  `not yet …`, `out of scope` or `in progress` after an item. Task 7 runs the gate on the body to prove it.
- **Capacity** (CLAUDE.md rule 0): `n/a: process documents and one model prompt; no workload runs
  differently` (spec: "Capacity: n/a").

Four helper scripts, saved outside the checkout. `$SCRATCH` below is any directory outside the
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

`$SCRATCH/plan_replay.py`: replays this plan's Edit and Append blocks onto `origin/main` and compares
the result with the branch (Task 7):

````python
#!/usr/bin/env python3
"""plan_replay.py PLAN BASE_REF [EXEMPT...]: the plan's edits, replayed.

Applies every "**Edit `FILE`**" (an Old block replaced by a New block) and every
"**Append to `FILE`**" (a blank line, then the block) in PLAN, in document order, to
FILE as it is at BASE_REF, then compares each result with the working tree. An Old
block must occur exactly once in the file as the earlier edits left it. Also lists
the files the branch changes against BASE_REF that no edit touches (EXEMPT ones aside).
Exits 1 on any miss.
"""
import re
import subprocess
import sys

plan, base, *exempt = sys.argv[1:]
text = open(plan, encoding="utf-8").read()
FENCE = r"````markdown\n(.*?)````"
pat = re.compile(r"^\*\*(Edit|Append to) `([^`]+)`\*\*[^\n]*\n\n(?:Old:\n\n" + FENCE + r"\n\nNew:\n\n" + FENCE
                 + r"|" + FENCE + r")", re.S | re.M)
files, n, bad = {}, 0, []
for m in pat.finditer(text):
    kind, path = m.group(1), m.group(2)
    if path not in files:
        files[path] = subprocess.run(["git", "show", f"{base}:{path}"], capture_output=True, text=True,
                                     check=True).stdout
    n += 1
    if kind == "Edit":
        old, new = m.group(3), m.group(4)
        hits = files[path].count(old)
        if hits != 1:
            bad.append(f"edit {n} ({path}): the Old block occurs {hits} times")
            continue
        files[path] = files[path].replace(old, new)
    else:
        files[path] += "\n" + m.group(5)
for path, body in files.items():
    if body != open(path, encoding="utf-8").read():
        bad.append(f"{path}: the replayed file differs from the working tree")
changed = subprocess.run(["git", "diff", "--name-only", base], capture_output=True, text=True,
                         check=True).stdout.split()
untouched = sorted(set(changed) - set(files) - set(exempt))
bad += [f"{p}: changed on this branch, but no edit in the plan touches it" for p in untouched]
for b in bad:
    print("FAIL:", b)
print(f"{n} edit(s) over {len(files)} file(s); {len(files) - sum(':' in b and 'differs' in b for b in bad)} "
      f"reproduce the working tree; {len(bad)} problem(s)")
sys.exit(1 if bad else 0)
````

`$SCRATCH/gate_stub_test.sh`: executes Task 5's `staging_verified` gate against a stubbed `gcloud`:

````bash
#!/usr/bin/env bash
# gate_stub_test.sh: runs Phase 8 step 8's staging_serving_revision and staging_verified,
# exactly as .claude/commands/resolve-issue.md prints them, against a stubbed gcloud,
# and prints each case's exit status. No network, nothing deployed.
set -u
cd "$(git rev-parse --show-toplevel)"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
mkdir "$T/bin"
cat > "$T/bin/gcloud" <<'STUB'
#!/bin/bash
case "$*" in
  "config get-value project") echo "${STUB_PROJECT-proj}" ;;
  run\ services\ describe*) [ -n "${STUB_FAIL:-}" ] && exit 1; cat "$STUB_JSON" ;;
esac
STUB
chmod +x "$T/bin/gcloud"
awk '/^     staging_serving_revision\(\) \{/ {p = 1} p && /^     staging_verified     # BARE/ {exit} p' \
  .claude/commands/resolve-issue.md | sed 's/^     //' > "$T/funcs.sh"
traffic() { printf '{"status":{"traffic":[%s]}}' "$2" > "$T/$1.json"; }
traffic one '{"revisionName":"rev-1","percent":100}'
traffic two '{"revisionName":"rev-2","percent":100}'
traffic split '{"revisionName":"rev-1","percent":50},{"revisionName":"rev-2","percent":50}'
run() {
  local name=$1; shift
  env PATH="$T/bin:$PATH" "$@" bash -c ". '$T/funcs.sh'; staging_verified" > /dev/null 2>&1
  echo "$name: rc=$?"
}
run "bare call (the read before)" STUB_JSON="$T/one.json"
run "STAGING_VERIFIED matches"    STUB_JSON="$T/one.json" STAGING_VERIFIED=rev-1
run "staging moved meanwhile"     STUB_JSON="$T/two.json" STAGING_VERIFIED=rev-1
run "describe fails"              STUB_JSON="$T/one.json" STUB_FAIL=1 STAGING_VERIFIED=rev-1
run "traffic split"               STUB_JSON="$T/split.json" STAGING_VERIFIED=rev-1
run "no project resolved"         STUB_JSON="$T/one.json" STUB_PROJECT= STAGING_VERIFIED=rev-1
````

## Review Focus

1. **A clause split by a line wrap.** `clause_check.py` collapses wraps, so every task checks with it
   rather than with `grep`.
2. **A `solyra-api-prod` line that says "retired" only on the next line.** Task 5 runs the grep with
   `grep -v retired` and expects no output.
3. **The trigger list quoted in `resolve-issue.md` drifting from CLAUDE.md §2.5's sentence.** Task 3
   checks CLAUDE.md's sentence and Task 4 checks that `resolve-issue.md` quotes the same sentence.
4. **The cap stopping a PR whose second round is clean.** Task 4 checks step 5 says "a second round with
   no findings goes on to step 6".
5. **A ticked box the gate refuses, or a same-day catalog record.** Task 7 runs the gate with the PR body
   before the PR is marked ready, and edits the record's Code field as well as its date.
6. **A post-merge or owner step treated as pre-merge or pre-ticked** (round 2, 4240531081). Task 6
   checks debug-local's two failure paragraphs and the unticked close-out line; Task 5 checks step 8's
   post-merge failure paragraph and that `STAGING_VERIFIED` is set only once the reproduction passes.
7. **The reviewed-head rule reading differently in its three homes.** Tasks 3 and 4 check the same
   scoping sentence in CLAUDE.md, the template and resolve-issue step 2.
8. **The plan drifting from the files** (round 2, 4240531079). Task 7 runs `plan_replay.py`.

---

## Task 1: `## Review guidelines` in `AGENTS.md`, and its registry row

Spec: § Design, "Review guidelines (`AGENTS.md`)". Advances done_when[0]; the registry rows keep the
docs audit clean (done_when[7]).

**Files:**
- Create: `docs/superpowers/plans/2026-10-11-feat-cicd-001-review-guidelines.md` (this plan)
- Modify: `AGENTS.md` (7 lines on main; the section is appended after line 7)
- Modify: `docs/DOC_REGISTRY.md:195` and after `:297` (round 1)

**Interfaces:**
- Produces: the heading `## Review guidelines` and its subsections (`### The first review is the
  complete one`, `### Later reviews`, `### Problems this pull request did not cause`, `### Browser proof`),
  which Task 2's Rule 2.5 text and code-reviewer.md, Task 6's §3.11 sentence and debug-local item point
  to by name.

- [ ] **Step 1: Commit this plan.** On #1380 it was the branch's first commit, alone; on this re-cut it
  arrived in the first commit, with #1380's tree.

```bash
python3 scripts/gate/spec_gate.py --commit   # expect: spec gate ok
git add docs/superpowers/plans/2026-10-11-feat-cicd-001-review-guidelines.md
git commit -m "docs: add the FEAT-CICD-001 review guidelines plan"
```

- [ ] **Step 2: Run the checks (expect FAIL)**

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

```bash
python3 "$SCRATCH/clause_check.py" docs/DOC_REGISTRY.md '^## Registry' '^## (?!Registry)' \
  "| D | CLAUDE.md | .claude, gcp/deploy.sh, AGENTS.md | |" \
  "| X | AGENTS.md | | |"
```

Expected on main: `AGENTS.md: no line matches '^## Review guidelines'; 0/15 clauses present` and
registry `0/2`, both exit 1.

- [ ] **Step 3: Append the section**

**Append to `AGENTS.md`** (after line 7, `(the vendored skills), as Phase 0 of the product-delivery skill sets out.`, with one blank line before it, so the file ends with it)

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

- [ ] **Step 4: Classify `AGENTS.md` in the registry** (round 1): it is agent instructions, class X,
  and CLAUDE.md declares it among the paths it describes.

**Edit `docs/DOC_REGISTRY.md`** (line 195 on origin/main)

Old:

````markdown
| D | CLAUDE.md | .claude, gcp/deploy.sh |  |
````

New:

````markdown
| D | CLAUDE.md | .claude, gcp/deploy.sh, AGENTS.md |  |
````

**Edit `docs/DOC_REGISTRY.md`** (line 297 on origin/main)

Old:

````markdown
| X | .github/pull_request_template.md | |  |
````

New:

````markdown
| X | .github/pull_request_template.md | |  |
| X | AGENTS.md | |  |
````

- [ ] **Step 5: Run the checks again (expect PASS)**

Same commands. Expected: `15/15` and registry `2/2`, exit 0. The docs
audit's `unclassified` count drops from 2 on main to 1 (`.claude/skills/SUPERPOWERS.md` remains).

- [ ] **Step 6: Commit**

```bash
python3 scripts/gate/spec_gate.py --commit
git add AGENTS.md docs/DOC_REGISTRY.md
git commit -m "docs: add review guidelines to AGENTS.md"
```

## Task 2: Rule 2.5, the reviewer pointer and the classifying reply, and the code-reviewer agent

Spec: § Design, "The classifying reply (CLAUDE.md Rule 2.5)". Advances done_when[1].

**Files:**
- Modify: `CLAUDE.md:195-197` (between the last bullet of `#### Resolving is part of the fix` and the
  heading `#### A resolved thread is not a reviewed commit`)
- Modify: `.claude/agents/code-reviewer.md:150-159` (round 1)

**Interfaces:**
- Consumes: Task 1's heading `## Review guidelines`.
- Produces: `#### Reviewing a pull request` and `#### A finding raised after a reviewer's first review`
  in Rule 2.5. Tasks 3 and 4 cite "CLAUDE.md Rule 2.5" for the classifying reply; Task 1's text cites
  it for "the author to classify". code-reviewer.md, which Claude Code runs as a reviewer, is held to
  the same guidelines (round 1).

- [ ] **Step 1: Run the checks (expect FAIL)**

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
  "follows AGENTS.md's ## Review guidelines" \
  "For Codex, a first review that posts no findings leaves no review object" \
  "A reviewer whose clean review does create a review object, as a person's approval does, needs no such comment: that object's commit_id names the commit its first review covered"
```

```bash
python3 "$SCRATCH/clause_check.py" .claude/agents/code-reviewer.md '^## Your Output Format' '^## Project Context' \
  "A finding is a defect this diff introduces or makes worse" \
  "A pre-existing problem you noticed goes under a separate Not this PR heading, as an issue to open, never as a finding" \
  "Be Complete: The first review is the complete one (AGENTS.md, ## Review guidelines)" \
  "Be Exhaustive: Post every finding on a defect this diff introduces or worsens, at every severity, one per defect class listing each location"
grep -n "Be Proportional\|Be Efficient\|a pre-existing issue you noticed" .claude/agents/code-reviewer.md
```

Expected on main: rule25 `0/12`, code-reviewer `0/4`, both exit 1, and the grep
prints three lines.

- [ ] **Step 2: Insert the two subsections.** The clean-review paragraph is qualified as Codex's
  (round 1, 4240413683): a person's clean approval is a review object whose `commit_id` names the SHA.

**Edit `CLAUDE.md`** (lines 195-197 on origin/main)

Old:

````markdown
- If the fix landed in a different PR, say which one.

#### A resolved thread is not a reviewed commit
````

New:

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

For Codex, a first review that posts no findings leaves no review object, so
the commit it covered is the one Codex's review-summary comment shows for
that review type when that row first reads Completed, and the author records
that SHA in a PR comment then, since the next run replaces the row:
`First Codex code review: Completed on <sha>, no findings.` A reviewer whose
clean review does create a review object, as a person's approval does, needs
no such comment: that object's `commit_id` names the commit its first review
covered.

#### A resolved thread is not a reviewed commit
````

- [ ] **Step 3: Hold the code-reviewer agent to the guidelines** (round 1)

**Edit `.claude/agents/code-reviewer.md`** (lines 150-159 on origin/main)

Old:

````markdown
(reproduced delta or test result). Tag whether each finding is a NEW regression
from this diff vs. a pre-existing issue you noticed (don't conflate the two).

## Your Behavioral Guidelines:

- **Be Specific**: Always reference exact line numbers, function names, or code blocks
- **Be Actionable**: Every issue must include a concrete suggestion for improvement
- **Be Proportional**: Focus review depth based on code criticality and risk
- **Be Constructive**: Frame feedback to educate and improve, not criticize
- **Be Efficient**: Only report significant issues that genuinely require action
````

New:

````markdown
(reproduced delta or test result). A finding is a defect this diff introduces
or makes worse. A pre-existing problem you noticed goes under a separate
**Not this PR** heading, as an issue to open, never as a finding (`AGENTS.md`,
`## Review guidelines`, "Problems this pull request did not cause").

## Your Behavioral Guidelines:

- **Be Specific**: Always reference exact line numbers, function names, or code blocks
- **Be Actionable**: Every issue must include a concrete suggestion for improvement
- **Be Complete**: The first review is the complete one (`AGENTS.md`, `## Review guidelines`)
- **Be Constructive**: Frame feedback to educate and improve, not criticize
- **Be Exhaustive**: Post every finding on a defect this diff introduces or worsens, at every severity, one per defect class listing each location
````

- [ ] **Step 4: Run the checks again (expect PASS)**

Same commands. Expected: rule25 `12/12`, code-reviewer `4/4`, exit 0; the grep
prints nothing (exit 1).

- [ ] **Step 5: Commit**

```bash
python3 scripts/gate/spec_gate.py --commit
git add CLAUDE.md .claude/agents/code-reviewer.md
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
- Produces: the trigger-list sentence Task 4 quotes verbatim in `resolve-issue.md` step 0, and the
  reviewed-head rule with its scoping sentence ("Both halves count Codex's code review only: …"), which
  Task 4 states again in step 2 in the same words (round 1).

- [ ] **Step 1: Run both checks (expect FAIL)**

```bash
python3 "$SCRATCH/clause_check.py" CLAUDE.md '^#### A resolved thread is not a reviewed commit' '^#### Verify the claim' \
  "Codex's code review also runs when new commits are pushed to a PR open for review (the 'New commits' trigger in its review-summary comment on #1366 and #1371)" \
  "a review with no findings leaves no review object" \
  "the head counts as reviewed only when, after the PR's latest review-triggering event, a review authored by chatgpt-codex-connector[bot] was submitted naming it in commit_id, or the Code Review row of Codex's own review-summary comment reads Completed for the head's SHA, as .claude/commands/resolve-issue.md step 2 requires" \
  "a PR opened for review, a draft marked ready, or an explicit @codex review comment, and Codex's code review also runs when new commits are pushed to a PR open for review" \
  "from Codex, a review with no findings leaves no review object" \
  "Both halves count Codex's code review only: the review-triggering events are the PR opened for review, the draft marked ready, an @codex review comment and a push of new commits, and the review must not be CHANGES_REQUESTED"
```

```bash
python3 "$SCRATCH/clause_check.py" .github/pull_request_template.md '^## Merge gate' '^## (?!Merge gate)' \
  "reviewed as CLAUDE.md §2.5 counts it" \
  "after the PR's latest review-triggering event, a review authored by chatgpt-codex-connector[bot] was submitted naming it in commit_id" \
  "or the Code Review row of Codex's review-summary comment reads Completed for the head's SHA" \
  "Each thread holding a finding a reviewer posted after its own first review carries the reply classifying each location before it is resolved" \
  "uncounted, missed (with the SHA of the commit the first review covered) or new (with the SHA of the later commit)" \
  "a clean Codex review leaves no review object" \
  "Both halves count Codex's code review only: the review-triggering events are the PR opened for review, the draft marked ready, an @codex review comment and a push of new commits, and the review must not be CHANGES_REQUESTED"
```

Expected on main: claude-25 `0/6`, template `0/7`, both exit 1.

- [ ] **Step 2: Replace the §2.5 paragraphs** (the closing paragraph, "When the head is unreviewed and
  the change is more than cosmetic, comment `@codex review` and wait…", stays as it is)

**Edit `CLAUDE.md`** (lines 202-220 on origin/main)

Old:

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

New:

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
about to merge, and neither does the review list on its own: from Codex, a
review with no findings leaves no review object (it reacts 👍 instead), and
every reply you post on a thread is itself a review object naming the head.
So the head counts as reviewed only when, after the PR's latest
review-triggering event, a review authored by `chatgpt-codex-connector[bot]`
was submitted naming it in `commit_id`, or the Code Review row of Codex's own
review-summary comment reads Completed for the head's SHA, as
`.claude/commands/resolve-issue.md` step 2 requires. Both halves count
Codex's code review only: the review-triggering events are the PR opened for
review, the draft marked ready, an `@codex review` comment and a push of new
commits, and the review must not be `CHANGES_REQUESTED`. The cutoff matters:
re-marking a draft ready, or an `@codex review` on an unchanged head, would
otherwise count the older review while the new run is still going.
`get_reviews` returns oldest first, so the current review is on the last page,
and all threads `is_outdated` still means the review predates the current
content entirely.
````

The `New commits` trigger is quoted from Codex's review-summary comments: on #1371 (comment
6104454716) and #1366 (comment 6103923840) the Code Review row's "Review trigger" column reads
`New commits`, and both comments are authored by `chatgpt-codex-connector[bot]` (read 2026-10-11).

- [ ] **Step 3: Replace the template's Merge gate items**

**Edit `.github/pull_request_template.md`** (lines 66-73 on origin/main)

Old:

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

New:

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
      Completed for the head's SHA (a clean Codex review leaves no review
      object, so read the row). Both halves count Codex's code review only:
      the review-triggering events are the PR opened for review, the draft
      marked ready, an `@codex review` comment and a push of new commits, and
      the review must not be `CHANGES_REQUESTED`. `get_reviews` returns OLDEST
      FIRST, so the current review is on the LAST page: reading page 1 and
      finding an older "no findings" is how #991 was merged two minutes
      after a review it never saw. Unreviewed → comment `@codex review` and
      wait
````

- [ ] **Step 4: Run both checks again (expect PASS)**

Same commands. Expected: claude-25 `6/6`, template `7/7`, exit 0. Also
`grep -n "A push does not" CLAUDE.md` prints nothing (exit 1).

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
  3982 on main): steps 0 to 6

**Interfaces:**
- Consumes: Task 3's trigger sentence (quoted verbatim in step 0) and reviewed-head rule (stated again
  in step 2), and Task 2's Rule 2.5 classifying reply (cited in steps 3, 5 and 6).

- [ ] **Step 1: Run the check (expect FAIL)**

```bash
python3 "$SCRATCH/clause_check.py" .claude/commands/resolve-issue.md '^## Phase 8' '^## Phase 9' \
  "(CLAUDE.md §2.5: \"a PR opened for review, a draft marked ready, or an explicit @codex review comment, and Codex's code review also runs when new commits are pushed to a PR open for review\")" \
  "One PR can carry several reviews' threads" \
  "If step 4 produced a commit for a finding from the PR's first review round, go back to step 1 on the new head" \
  "after a PR's second review round, stop and split, re-cut or discard it" \
  "a second round with no findings goes on to step 6" \
  "A thread holding a finding that a reviewer posted after its own first review is resolved only after a reply on it classifies each location" \
  "The rule, as CLAUDE.md §2.5 and the PR template's Merge gate state it: the head counts as reviewed only when, after the PR's latest review-triggering event, a review authored by chatgpt-codex-connector[bot] was submitted naming it in commit_id, or the Code Review row of Codex's own review-summary comment reads Completed for the head's SHA" \
  "Both halves count Codex's code review only: the review-triggering events are the PR opened for review, the draft marked ready, an @codex review comment and a push of new commits, and the review must not be CHANGES_REQUESTED" \
  "returning a code review that is authored by the review bot (chatgpt-codex-connector[bot]), is not CHANGES_REQUESTED" \
  "the Code Review row of the Codex summary comment showing Completed against the head SHA" \
  "Settle the round first: which run of Codex's code review raised the finding (step 5 says what a round is)" \
  "A finding from the PR's second review round is verified here and not fixed: step 5 says what it gets." \
  "A round is one run of Codex's code review on the PR. After the second, push nothing but a merge of main that edits no conflict by hand, and handle any finding the run it starts raises as a second-round finding."
```

Expected on main: phase8 `0/13`, exit 1.

- [ ] **Step 2: Step 0, the quoted trigger list**

**Edit `.claude/commands/resolve-issue.md`** (lines 3994-3995 on origin/main)

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

- [ ] **Step 3: Step 1, paging** ("Nine review rounds on one PR is not hypothetical here" goes)

**Edit `.claude/commands/resolve-issue.md`** (lines 4009-4013 on origin/main)

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

- [ ] **Step 4: Step 2, the rule in CLAUDE.md's words** (round 1): the same rule and scoping sentence
  as Task 3, then the detail; the review-object alternative is a code review by
  `chatgpt-codex-connector[bot]`, and the summary alternative reads the Code Review row.

**Edit `.claude/commands/resolve-issue.md`** (lines 4017-4019 on origin/main)

Old:

````markdown
   nothing wrong with it. Either of these satisfies this step:
   - `pull_request_read` `method: "get_reviews"` returning a review that is
     **authored by the review bot**, is not `CHANGES_REQUESTED`, whose
````

New:

````markdown
   nothing wrong with it. The rule, as CLAUDE.md §2.5 and the PR template's
   Merge gate state it: the head counts as reviewed only when, after the PR's
   latest review-triggering event, a review authored by
   `chatgpt-codex-connector[bot]` was submitted naming it in `commit_id`, or
   the Code Review row of Codex's own review-summary comment reads Completed
   for the head's SHA. Both halves count Codex's code review only: the
   review-triggering events are the PR opened for review, the draft marked
   ready, an `@codex review` comment and a push of new commits, and the review
   must not be `CHANGES_REQUESTED`. In detail, either of these satisfies this
   step:
   - `pull_request_read` `method: "get_reviews"` returning a code review that
     is **authored by the review bot** (`chatgpt-codex-connector[bot]`), is
     not `CHANGES_REQUESTED`, whose
````

**Edit `.claude/commands/resolve-issue.md`** (lines 4031-4033 on origin/main, the push trigger and the ordinary path's cutoff)

Old:

````markdown
     rerun may have been requested by someone else. **On a PR that was never
     drafted and never re-triggered — the ordinary CASE B path — there is no
     such event and no cutoff**; the head SHA and the author check carry the
````

New:

````markdown
     rerun may have been requested by someone else. A push of new commits
     triggers a review too (CLAUDE.md §2.5), but it moves the head, so the
     head-SHA test already ties the review to it. **On a PR that was never
     drafted and never re-triggered — the ordinary CASE B path — the only
     events are the opening and the pushes, which any review naming the head
     already follows, so there is no separate cutoff**; the head SHA and the
     author check carry the
````

**Edit `.claude/commands/resolve-issue.md`** (line 4042 on origin/main)

Old:

````markdown
   - the Codex summary comment showing **Completed** against the head SHA,
````

New:

````markdown
   - the **Code Review row** of the Codex summary comment showing
     **Completed** against the head SHA,
````

**Edit `.claude/commands/resolve-issue.md`** (lines 4063-4064 on origin/main)

Old:

````markdown
     **On a PR that was never drafted and never re-triggered there is still no
     event and no cutoff**, exactly as above; the head SHA and the author check
````

New:

````markdown
     **On a PR that was never drafted and never re-triggered there is still no
     separate cutoff**, exactly as above; the head SHA and the author check
````

- [ ] **Step 5: Step 3, the bar, and step 4, the round first** ("step 5 enforces" becomes "step 6
  enforces", since step 6 checks zero unresolved; step 4 settles the round before fixing, round 1,
  4240413677)

**Edit `.claude/commands/resolve-issue.md`** (lines 4089-4095 on origin/main)

Old:

````markdown
   fix there. What follows is the bar step 5 enforces: every thread
   fixed-and-resolved, naming what changed
   and the covering test and commit, or replied to with why not. Zero unresolved
   across every page is the bar.
4. Verify each finding against the code before fixing it: reproduce, write the
   failing test, fix, show it pass. A fix built on a misread finding is worse
   than no fix.
````

New:

````markdown
   fix there. What follows is the bar step 6 enforces: every thread
   fixed-and-resolved, naming what changed
   and the covering test and commit, or replied to with why not, and a thread
   holding a finding a reviewer posted after its own first review resolved
   only after the reply that classifies each location (CLAUDE.md Rule 2.5).
   Zero unresolved across every page is the bar.
4. **Settle the round first:** which run of Codex's code review raised the
   finding (step 5 says what a round is). Then verify each finding against the
   code before fixing it: reproduce, write the failing test, fix, show it
   pass. A fix built on a misread finding is worse than no fix.
````

- [ ] **Step 6: Step 4's last word on a second-round finding, and step 5, the review cap and what a
  round is** (replaces "There is no round limit")

**Edit `.claude/commands/resolve-issue.md`** (lines 4116-4123 on origin/main)

Old:

````markdown
   recognising a hostile string.
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
   recognising a hostile string.

   A finding from the PR's second review round is verified here and not
   fixed: step 5 says what it gets.
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
   Phase 9 "Still open before this closes". A round is one run of Codex's code
   review on the PR. After the second, push nothing but a merge of `main` that
   edits no conflict by hand, and handle any finding the run it starts raises
   as a second-round finding.
````

- [ ] **Step 7: Step 6, the classifying reply before a later finding's thread resolves**

**Edit `.claude/commands/resolve-issue.md`** (lines 4127-4128 on origin/main)

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

Same command. Expected: phase8 `13/13`, exit 0. And
`grep -n "There is no round limit\|Nine review rounds" .claude/commands/resolve-issue.md` prints
nothing (exit 1). The scoping sentence now reads the same in all three homes:

```bash
python3 - <<'EOF'
import re
norm = lambda s: re.sub(r"\s+", " ", re.sub(r"[`*]", "", s)).lower()
both = norm("Both halves count Codex's code review only: the review-triggering events are the PR opened "
            "for review, the draft marked ready, an @codex review comment and a push of new commits, and "
            "the review must not be CHANGES_REQUESTED.")
for f in ("CLAUDE.md", ".github/pull_request_template.md", ".claude/commands/resolve-issue.md"):
    print(f, norm(open(f).read()).count(both))
EOF
```

Expected: each file prints `1`.

- [ ] **Step 9: Commit**

```bash
python3 scripts/gate/spec_gate.py --commit
git add .claude/commands/resolve-issue.md
git commit -m "docs: cap resolve-issue at two review rounds and classify later findings"
```

## Task 5: the deploy step and the architecture prompt describe one API service

Spec: § Design, "The retired service in process files". Advances done_when[6].

**Files:**
- Modify: `.claude/commands/resolve-issue.md`: the resume notes at lines 227-246 (round 1), Phase 8
  step 8 at 4156-4163 (the post-merge failure paragraph and the cited staging file), 4664-4665 (the
  build-id note) and 4681-4774 (the promotion procedure, through the owner-action bullet), and the
  Phase 9 status template at 4811-4812
- Modify: `.github/prompts/architecture.md:92-95` (the first of "Two facts to keep asserting")

**Interfaces:**
- Consumes: `gcp/cloudbuild/deploy-solyra-api-staging-cloudbuild.yaml:2-8` (the `includedFiles`
  caveat, kept) and `:24-26` ("the one API service since solyra-api-prod and its deploy-solyra-api-prod
  promote trigger were retired on 2026-10-10"); `gcp/cloudbuild/serving_revision.py` (reads `gcloud run
  services describe … --format=json` on stdin, prints the serving revision; `platform/deploy.sh:251`
  calls it with `python3`, as the gate does).
- Produces: `staging_verified`, the fail-closed gate Phase 9 closes on (round 1, 4240413682). It
  refuses unless `STAGING_VERIFIED` names the revision staging serves after the reproduction, and it is
  set only once the reproduction passed (round 2's class).

- [ ] **Step 1: Run the checks (expect FAIL)**

```bash
git grep -n solyra-api-prod -- .claude .github
git grep -n solyra-api-prod -- .claude .github | grep -v retired   # lines that do not say retired
grep -c "promote_to_prod\|_EXPECT_STAGING_REVISION" .claude/commands/resolve-issue.md
bash "$SCRATCH/gate_stub_test.sh"
```

```bash
python3 "$SCRATCH/clause_check.py" .claude/commands/resolve-issue.md '^## Phase 8' '^## Phase 9' \
  "the staging deploy that a merge to main starts is the deployment" \
  "That staging deploy is the deployment." \
  "the trigger's includedFiles is platform/**, lib/**, requirements.txt, gcp/database.py" \
  "staging_serving_revision" \
  "A production check that fails after the merge is not a local failure: the fix is merged and may already be serving, and backing out a local change undoes nothing" \
  "Only its pass, where both reads name the same revision, lets Phase 9 close the issue" \
  "If the reproduction fails against staging, do not set STAGING_VERIFIED: the merged fix does not work where it serves, so keep the issue open and start a revert or a new remediation" \
  "STAGING_VERIFIED=%q staging_verified"
python3 "$SCRATCH/clause_check.py" .claude/commands/resolve-issue.md '^\*\*One merged PR you must NOT skip past' '^#{2,3} ' \
  "when the staging deploy or its verification needs an owner action" \
  "a deploy, a staging verification or a cross-repo sync"
python3 "$SCRATCH/clause_check.py" .claude/commands/resolve-issue.md '^## Phase 9' '^\*\*Close only when' \
  "for an API change, the staging_verified refusal and pass from Phase 8 step 8, with the reproduction's output"
```

```bash
python3 "$SCRATCH/clause_check.py" .github/prompts/architecture.md '^## Two facts' '^## Rules' \
  "The API is served by ONE API-only Cloud Run service, solyra-api-staging"
```

Expected on main: the second command prints six lines (`resolve-issue.md:4161`, `:4684`, `:4690`,
`:4753`, `:4763`, `architecture.md:92`), the count is `7`, every stub case prints `rc=127` (there is no
gate to run), and deploy `1/8`, resume `0/2`, phase9 `0/1`, prompt `0/1` (the deploy
check's one is the kept `includedFiles` clause), each exit 1.

- [ ] **Step 2: The resume notes no longer name a promotion** (round 1)

**Edit `.claude/commands/resolve-issue.md`** (lines 227-235 on origin/main)

Old:

````markdown
**One merged PR you must NOT skip past.** Phase 8 step 8 leaves an issue open
when promotion needs an owner action, with the outstanding deploy named in its
status comment. On the next run `is:open` hides that merged PR, CASE B then
creates a fresh branch from `main`, and the run re-implements a fix that has
already merged. So before branching: if the issue is open and a status comment
**passing both checks above** says the code merged and only deployment or
production verification remains, **do not branch at all** — resume at Phase 8
step 8, deploy, verify, and close. Check the issue's linked PRs for a merged one
rather than trusting `is:open` to have told you everything.
````

New:

````markdown
**One merged PR you must NOT skip past.** Phase 8 step 8 leaves an issue open
when the staging deploy or its verification needs an owner action, with the
outstanding deploy named in its status comment. On the next run `is:open`
hides that merged PR, CASE B then creates a fresh branch from `main`, and the
run re-implements a fix that has already merged. So before branching: if the
issue is open and a status comment **passing both checks above** says the code
merged and only deployment or production verification remains, **do not
branch at all** — resume at Phase 8 step 8, deploy, verify, and close. Check
the issue's linked PRs for a merged one rather than trusting `is:open` to have
told you everything.
````

**Edit `.claude/commands/resolve-issue.md`** (lines 242-246 on origin/main)

Old:

````markdown
to re-implement work that shipped. Read the status comment — after the two
checks above — for what it POINTS AT as remaining, a deploy, a promotion or a
cross-repo sync, then confirm that remainder against the system before acting
on it, and resume THAT in the repo it belongs to. Branching in this repo is
correct only when the remaining work is a code change in this repo.
````

New:

````markdown
to re-implement work that shipped. Read the status comment — after the two
checks above — for what it POINTS AT as remaining, a deploy, a staging
verification or a cross-repo sync, then confirm that remainder against the
system before acting on it, and resume THAT in the repo it belongs to.
Branching in this repo is correct only when the remaining work is a code
change in this repo.
````

- [ ] **Step 3: Step 8, a production check that fails after the merge, and the cited staging file**
  (the failure paragraph is round 2's class: a local back-out cannot undo a merge)

**Edit `.claude/commands/resolve-issue.md`** (lines 4156-4163 on origin/main)

Old:

````markdown
   Documentation, tests, and CI-only changes are the genuine exemption — they
   ship by merging.

   `gcp/cloudbuild/deploy-solyra-api-staging-cloudbuild.yaml:26` says it
   outright: *"Merging to main NEVER touches prod. Prod moves only when a human
   runs the `deploy-solyra-api-prod` trigger."* And the staging build itself is
   conditional — the same file records that the trigger's `includedFiles` is
   `platform/**, lib/**, requirements.txt, gcp/database.py`, so a fix under
````

New:

````markdown
   Documentation, tests, and CI-only changes are the genuine exemption — they
   ship by merging.

   A production check that fails after the merge is not a local failure: the
   fix is merged and may already be serving, and backing out a local change
   undoes nothing. Keep the issue open, post the failing output on it, and
   start a revert of the merged change or a new remediation.

   `gcp/cloudbuild/deploy-solyra-api-staging-cloudbuild.yaml:24-26` says the
   trigger deploys `solyra-api-staging`, the one API service since
   `solyra-api-prod` and its promote trigger were retired on 2026-10-10, so
   the staging deploy that a merge to `main` starts is the deployment for an
   API change. That build is conditional — the same file records (lines 2-8)
   that the trigger's `includedFiles` is
   `platform/**, lib/**, requirements.txt, gcp/database.py`, so a fix under
````

- [ ] **Step 4: The build-id note**

**Edit `.claude/commands/resolve-issue.md`** (lines 4664-4665 on origin/main)

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

- [ ] **Step 5: Replace the promotion procedure with the staging verification and its gate.** This
  removes "**Staging is not the end of it.**", the `_EXPECT_STAGING_REVISION` explanation,
  `promote_to_prod()` and the `deploy-solyra-api-prod` trigger run; it keeps the serving-revision read
  (as `staging_serving_revision`, with its messages on stderr so the gate can capture the revision),
  restores a fail-closed check as `staging_verified`, and keeps the keep-the-issue-open bullet. The next
  line, the paragraph `**A completed review with no findings posts no review at all**` (4776), stays.

**Edit `.claude/commands/resolve-issue.md`** (lines 4681-4774 on origin/main)

Old:

````markdown
     Then validate against staging and read its serving revision, as below.
     Promoting without this promotes whatever staging was already serving,
     which is the code your fix was meant to replace. **Staging is not the end of it.** The same file says
     prod moves only when a human runs the `deploy-solyra-api-prod` trigger,
     so a staging-only outcome leaves the fix not serving. Run that trigger
     and verify against prod, or take the next bullet — do not treat "staging
     is green" as the deployment.

     **That trigger will not run without the revision you validated.**
     `gcp/cloudbuild/deploy-solyra-api-prod-cloudbuild.yaml:84-92` exits 1 on an
     empty `_EXPECT_STAGING_REVISION`, and exits 1 again if the value does not
     match what staging is serving now — by design, so a promotion moves the
     revision you actually checked rather than whatever landed on staging while
     you were checking. So capture the staging revision as part of the
     verification, not afterwards:

     Read the revision with the repo's own helper, not
     `latestReadyRevisionName`. `gcp/cloudbuild/serving_revision.py` exists
     because the two differ whenever staging was rolled back, is split across
     revisions, or was deployed `--no-traffic` — and in each of those "the
     latest ready revision is precisely the one nobody validated". The prod
     trigger resolves the serving revision with that helper, so binding
     `_EXPECT_STAGING_REVISION` to the latest-ready name makes the promotion
     fail closed on exactly the cases the helper exists to catch. It also fails
     loud on nothing-serving or a traffic split, rather than picking one:

     **`--project` on both, resolved once.** Neither command carried it, so
     both ran in whatever project the active gcloud configuration points at:
     the describe reads a `solyra-api-staging` that may not be the one you
     validated, and the trigger promotes in that project or not at all. This is
     the ambient-project hole the retirement helpers refuse by construction,
     reintroduced in the block that promotes to production.

     **A function here too, and for a second reason.** `return` outside a
     function is not merely wrong, it is the `false` bug wearing different
     clothes: bash prints `return: can only \`return\' from a function or
     sourced script` and **carries on to the next line** — measured, the guard
     above printed "no project resolved" and the following command ran anyway.
     Under `set -e` it aborts instead, so the same two lines behave differently
     depending on a shell option the reader cannot see. `exit` is not the
     alternative: these blocks are pasted into a live shell, and `exit` closes
     it. A function is the only form that stops exactly the recipe.

     ```bash
     promote_to_prod() {
       local PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project)}" REV
       test -n "$PROJECT_ID" || { echo "no project resolved"; return 1; }
       REV=$(gcloud run services describe solyra-api-staging \
               --project="$PROJECT_ID" --region=us-east1 \
               --format=json | python gcp/cloudbuild/serving_revision.py) \
         || { echo "could not read the staging serving revision"; return 1; }
       test -n "$REV" || { echo "staging is serving nothing, or is split"; return 1; }
       # THE VERIFICATION IS A STEP, NOT A COMMENT. This line used to read
       # "...verify against staging while it is serving $REV, THEN promote..."
       # and nothing enforced it: measured with a stubbed gcloud, the function
       # as supplied read the revision and ran the production trigger, rc=0,
       # with no verification of any kind. Reading which revision staging
       # serves proves that staging serves it, and nothing about whether the
       # fix works there.
       # BOUND TO $REV, the same shape round 50 gave the advanced-tip gate:
       # an acknowledgement of the revision you checked yesterday cannot clear
       # today's promotion, and staging moves whenever anything else deploys.
       test "${STAGING_VERIFIED:-}" = "$REV" || {
         echo "staging is serving $REV and nothing here has verified it."
         echo "Run THIS ISSUE's reproduction against staging now, while it is"
         echo "still serving that revision — the failing-before test from"
         echo "Phase 4, against the staging URL — then re-run bound to it:"
         printf '  STAGING_VERIFIED=%q promote_to_prod\n' "$REV"
         echo "If staging has moved on by then, this refuses again with the new"
         echo "revision, which is the point: the acknowledgement names what you"
         echo "actually tested."
         return 1; }
       gcloud builds triggers run deploy-solyra-api-prod \
         --project="$PROJECT_ID" --branch=main \
         --substitutions=_EXPECT_STAGING_REVISION="$REV"
     }
     promote_to_prod     # BARE, and nothing after it
     ```

     The `|| { …; return 1; }` on the `REV=` assignment is not decoration. A
     command substitution's failure is invisible to the next line: `REV=$(…)`
     that dies still assigns the empty string, and `--substitutions=_EXPECT_STAGING_REVISION=`
     is precisely the empty value `deploy-solyra-api-prod-cloudbuild.yaml:84-92`
     exits 1 on — a promotion that reports failure for the wrong reason, from a
     read that failed rather than a revision that moved.

     It fails closed, which is the safe direction — but "run the trigger" as
     written simply does not promote anything, so the issue would be closed on a
     deploy that never happened.
   - **Where promotion is an owner action this session cannot take**, keep the
     issue OPEN, put the exact command in "Still open before this closes", and
     say the fix is merged but not yet serving. Closing on candidate evidence
     while calling it production proof is the failure this whole phase exists
     to prevent.
````

New:

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
     nothing-serving or a traffic split, rather than picking one. Two
     functions, with `--project` resolved once, for the reasons the blocks
     above give: one reads the revision, the other is the gate Phase 9 closes
     on.

     ```bash
     staging_serving_revision() {
       local PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project)}" REV
       test -n "$PROJECT_ID" || { echo "no project resolved" >&2; return 1; }
       REV=$(gcloud run services describe solyra-api-staging \
               --project="$PROJECT_ID" --region=us-east1 \
               --format=json | python3 gcp/cloudbuild/serving_revision.py) \
         || { echo "could not read the staging serving revision" >&2; return 1; }
       test -n "$REV" || { echo "staging is serving nothing, or is split" >&2; return 1; }
       echo "$REV"
     }
     staging_verified() {
       local REV
       REV=$(staging_serving_revision) || return 1
       # THE VERIFICATION IS A STEP, NOT A COMMENT. Reading which revision
       # staging serves proves that it serves it, and nothing about whether
       # the fix works there. BOUND TO $REV: STAGING_VERIFIED names the
       # revision read before the reproduction and this read comes after it,
       # so a revision that moved while you were checking refuses here.
       test "${STAGING_VERIFIED:-}" = "$REV" || {
         echo "staging is serving $REV and nothing here has verified it."
         echo "Run THIS ISSUE's reproduction against staging now, while it is"
         echo "still serving that revision (the failing-before test from"
         echo "Phase 4, against the staging URL). Once it passes, re-run:"
         printf '  STAGING_VERIFIED=%q staging_verified\n' "$REV"
         echo "If it fails, do not set it: keep the issue open and start a"
         echo "revert or a new remediation. If staging has moved on by then,"
         echo "this refuses again with the new revision: verify against it."
         return 1; }
       echo "staging verified: $REV, read before and after the reproduction"
     }
     staging_verified     # BARE, and nothing after it
     ```

     Call it bare first: the refusal is the read before the reproduction,
     and it names the revision. Run the reproduction, and only once it
     passes call it with `STAGING_VERIFIED` set to that revision: that is the
     read after. Only its pass, where both reads name the same revision, lets
     Phase 9 close the issue. If the revision changed in between, something
     else deployed while you were checking: verify again against the new one.
     If the reproduction fails against staging, do not set
     `STAGING_VERIFIED`: the merged fix does not work where it serves, so keep
     the issue open and start a revert or a new remediation, as the top of
     this step says. Paste the refusal, the pass and the reproduction's output
     in the Phase 9 status comment.
   - **Where the staging deploy or its verification is an owner action this
     session cannot take**, keep the issue OPEN, put the exact command in
     "Still open before this closes", and say the fix is merged but not yet
     verified as serving. Closing on candidate evidence while calling it
     production proof is the failure this whole phase exists to prevent.
````

- [ ] **Step 6: Phase 9's status template asks for the gate's output**

**Edit `.claude/commands/resolve-issue.md`** (lines 4811-4812 on origin/main)

Old:

````markdown
### Production, done in this session
<job execution, and the before/after query output>
````

New:

````markdown
### Production, done in this session
<job execution, and the before/after query output; for an API change, the
`staging_verified` refusal and pass from Phase 8 step 8, with the
reproduction's output>
````

- [ ] **Step 7: The architecture prompt**

**Edit `.github/prompts/architecture.md`** (lines 92-95 on origin/main)

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

- [ ] **Step 8: Run the checks again (expect PASS)**

Same commands. Expected: `git grep -n solyra-api-prod -- .claude .github` prints exactly three lines,
each saying retired (`resolve-issue.md` in step 8's staging paragraph and its verification paragraph,
`architecture.md:94`); the `grep -v retired` line prints nothing; the count is `0`; the stub cases print
`rc=1`, `rc=0`, `rc=1`, `rc=1`, `rc=1`, `rc=1` in order (only a matching `STAGING_VERIFIED` passes);
and deploy `8/8`, resume `2/2`, phase9 `1/1`, prompt `1/1`, exit 0. Every line
naming `STAGING_VERIFIED` sits inside the gate or the paragraph after it:

```bash
python3 - <<'EOF'
lines = open(".claude/commands/resolve-issue.md").read().splitlines()
start = next(n for n, l in enumerate(lines) if l.strip() == "staging_verified() {")
end = next(n for n in range(start, len(lines)) if "in the Phase 9 status comment." in lines[n])
outside = [n + 1 for n, l in enumerate(lines) if "STAGING_VERIFIED" in l and not start <= n <= end]
print("STAGING_VERIFIED outside the gate:", outside or "none")
EOF
```

- [ ] **Step 9: Commit**

```bash
python3 scripts/gate/spec_gate.py --commit
git add .claude/commands/resolve-issue.md .github/prompts/architecture.md
git commit -m "docs: treat the staging deploy as the deployment now prod is retired"
```

## Task 6: browser evidence in §3.11 and in debug-local's steps

Spec: § Design, "Evidence rules (`CLAUDE.md`)" and "Debugging (`.claude/agents/debug-local.md`, Step 4
Verify)". Advances done_when[4] and done_when[5].

**Files:**
- Modify: `CLAUDE.md:794-796` (the "Evidence means" paragraph of §3.11)
- Modify: `.claude/agents/debug-local.md`: Step 2 (after line 54), Step 4 (lines 80-82, item 5 and the
  failure handler), and the output template (after lines 166 and 174)

**Interfaces:**
- Consumes: Task 1's `## Review guidelines` ("Browser proof"), which both new passages point to.

- [ ] **Step 1: Run the checks (expect FAIL)**

```bash
python3 "$SCRATCH/clause_check.py" CLAUDE.md '^### 3\.11\.' '^#### A doc is a claim' \
  "For a change the site shows" \
  "Playwright evidence as AGENTS.md's ## Review guidelines define it: an API test of the changed response in the PR, and runs against the deployed site before the merge and once staging has deployed it, which the owner posts on the PR as close-out steps, with screenshots of the state each shows" \
  "In stocks the API test is pytest under tests/api/ and carries no screenshots; the screenshots come from the Playwright runs against the deployed site" \
  "Those runs use a *.cloud.spec.ts written in solyra for the change and run with npm run e2e:cloud (none exists yet; solyra CLAUDE.md, Testing discipline, item 5)"
```

```bash
python3 "$SCRATCH/clause_check.py" .claude/agents/debug-local.md '^### Step 2' '^### Step 3' \
  "capture the before-fix reproduction here, before Step 3 writes any fix: an API test of the broken response under tests/api/, run against the unfixed code to show it fails" \
  "the deployed site serves the unfixed code until the merge, so that run can come any time before it, and the owner posts it on the PR"
python3 "$SCRATCH/clause_check.py" .claude/agents/debug-local.md '^### Step 4' '^### Step 5' \
  "A bug a user sees in the site is verified with a Playwright run that reproduces it before the fix and passes after it, with screenshots of both: an API test of the fixed response in the PR that fails before the fix and passes after it, and runs against the deployed site that reproduce it before the merge and pass once staging has deployed the fix, which the owner posts on the PR as close-out steps" \
  "The runs that reproduce it before the fix are the ones Step 2 captured, and the after-fix runs repeat them" \
  "In stocks the API test is pytest under tests/api/ and carries no screenshots; the screenshots come from the Playwright runs against the deployed site" \
  "Those runs use a *.cloud.spec.ts written in solyra for the change and run with npm run e2e:cloud (none exists yet; solyra CLAUDE.md, Testing discipline, item 5)" \
  "If a verification step before the merge fails (items 1 to 4, or item 5's API test), back out the fix and return to Step 2" \
  "backing out a local fix cannot undo a merged deployment. If that run still shows the bug, keep the issue open, post the failing run and its screenshots on it, and start a revert of the merged change or a new remediation"
python3 "$SCRATCH/clause_check.py" .claude/agents/debug-local.md '^## Output format' '^## Rules' \
  "Before-fix reproduction (a bug a user sees)" \
  "- [x] a bug a user sees: the Step 2 API test now passes (item 5)" \
  "- [ ] pending, the owner's close-out after the merge: the deployed-site run passes once staging has deployed the fix"
```

Expected on main: claude-311 `0/4`, debug-step2 `0/2`, debug-step4 `0/6`, debug-output `0/3`, each exit 1.

- [ ] **Step 2: §3.11's definition of evidence** (the pytest and cloud-spec sentences are round 1's)

**Edit `CLAUDE.md`** (lines 794-796 on origin/main)

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
steps, with screenshots of the state each shows. In stocks the API test is
pytest under `tests/api/` and carries no screenshots; the screenshots come from
the Playwright runs against the deployed site. Those runs use a
`*.cloud.spec.ts` written in solyra for the change and run with
`npm run e2e:cloud` (none exists yet; solyra CLAUDE.md, Testing discipline,
item 5).
````

- [ ] **Step 3: debug-local Step 2 captures the before-fix reproduction** before any fix is written
  (round 1, 4240413675). The owner's deployed-site run reproduces the bug whenever it runs before the
  merge, so it does not block Step 3 (round 2's class).

**Edit `.claude/agents/debug-local.md`** (lines 54-56 on origin/main)

Old:

````markdown
If the stack trace points into `site-packages/`, trace back until you hit the first frame in the user's own code — THAT is the failing line, not the library internals.

### Step 3 — Propose a minimal fix (≤5 lines)
````

New:

````markdown
If the stack trace points into `site-packages/`, trace back until you hit the first frame in the user's own code — THAT is the failing line, not the library internals.

For a bug a user sees in the site, capture the before-fix reproduction here, before Step 3 writes any fix: an API test of the broken response under `tests/api/`, run against the unfixed code to show it fails. Ask the owner for the Playwright run against the deployed site that reproduces the bug, with screenshots; the deployed site serves the unfixed code until the merge, so that run can come any time before it, and the owner posts it on the PR. Step 4 item 5 checks the fix against these runs.

### Step 3 — Propose a minimal fix (≤5 lines)
````

- [ ] **Step 4: debug-local Step 4, item 5, and the two failure paths.** A failed pre-merge step backs
  out the fix; a failed post-merge run keeps the issue open for a revert or a new remediation (round 2,
  4240531081).

**Edit `.claude/agents/debug-local.md`** (lines 80-82 on origin/main)

Old:

````markdown
4. Verify no regressions in adjacent features

If any verification step fails, back out the fix and return to Step 2 — you had the wrong root cause.
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
   browser. The runs that reproduce it before the fix are the ones Step 2 captured, and the
   after-fix runs repeat them. In stocks the API test is pytest under `tests/api/` and carries
   no screenshots; the screenshots come from the Playwright runs against the deployed site.
   Those runs use a `*.cloud.spec.ts` written in solyra for the change and run with
   `npm run e2e:cloud` (none exists yet; solyra CLAUDE.md, Testing discipline, item 5).

If a verification step before the merge fails (items 1 to 4, or item 5's API test), back out the fix and return to Step 2: you had the wrong root cause.

Item 5's after-fix run against the deployed site comes only after the merge, once staging has deployed the fix, and backing out a local fix cannot undo a merged deployment. If that run still shows the bug, keep the issue open, post the failing run and its screenshots on it, and start a revert of the merged change or a new remediation (a fresh pass from Step 1).
````

- [ ] **Step 5: The output template.** Step 2 records the before-fix runs; Step 4 ticks only what
  happens before the merge and leaves the owner's close-out unticked (round 2, 4240531081).

**Edit `.claude/agents/debug-local.md`** (lines 166-167 on origin/main)

Old:

````markdown
Cause: <explanation>

````

New:

````markdown
Cause: <explanation>
Before-fix reproduction (a bug a user sees): <the failing tests/api/ test and its output>; deployed-site run: <link once the owner posts it on the PR, before the merge>

````

**Edit `.claude/agents/debug-local.md`** (lines 174-175 on origin/main)

Old:

````markdown
- [x] no regressions observed

````

New:

````markdown
- [x] no regressions observed
- [x] a bug a user sees: the Step 2 API test now passes (item 5)
- [ ] pending, the owner's close-out after the merge: the deployed-site run passes once staging has deployed the fix, with screenshots posted on the PR; if it fails, the issue stays open for a revert or a new remediation

````

- [ ] **Step 6: Run the checks again (expect PASS)**

Same commands. Expected: claude-311 `4/4`, debug-step2 `2/2`, debug-step4 `6/6`, debug-output `3/3`, exit 0.
`grep -n "If any verification step fails" .claude/agents/debug-local.md` prints nothing (exit 1).

- [ ] **Step 7: Commit**

```bash
python3 scripts/gate/spec_gate.py --commit
git add CLAUDE.md .claude/agents/debug-local.md
git commit -m "docs: count Playwright runs as evidence for a change the site shows"
```

## Task 7: close-out, product records, docs audit, replay and gate

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
later `docs/` PR, spec § Non-goals). On this re-cut the catalog record (Last reviewed `2026-10-11`, the
Code field) and the lineage entry for #1380 arrived with #1380's tree; the PR number is the one edit
left.

- [ ] **Step 1: Replay, gate and docs audit before the PR opens**

```bash
python3 "$SCRATCH/plan_replay.py" docs/superpowers/plans/2026-10-11-feat-cicd-001-review-guidelines.md origin/main \
  docs/superpowers/plans/2026-10-11-feat-cicd-001-review-guidelines.md \
  docs/product/02-FEATURE-CATALOG.md docs/product/12-PR-ISSUE-TRACEABILITY.md
# expect: 28 edit(s) over 8 file(s); 8 reproduce the working tree; 0 problem(s)
python3 scripts/gate/spec_gate.py --pr origin/main          # expect: spec gate ok (branch=feature/feat-cicd-001-review-guidelines-r2, …)
git worktree add --detach "$SCRATCH/stocks-main-audit" origin/main
(cd "$SCRATCH/stocks-main-audit" && python3 scripts/maintenance/docs_audit.py --json) > "$SCRATCH/audit-main.json"
python3 scripts/maintenance/docs_audit.py --json > "$SCRATCH/audit-branch.json"
python3 "$SCRATCH/audit_diff.py" "$SCRATCH/audit-main.json" "$SCRATCH/audit-branch.json"   # expect: 0 new finding(s) over main
git worktree remove "$SCRATCH/stocks-main-audit"
```

On `17bbacd3` the audit summary is `changed-since 1, class-a 4, closed-issue 1, dead-link 161, marker
115, unclassified 2`; the branch gives the same with `unclassified 1` (Task 1's registry row) and 0 new.

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
(what changed, per task; that this re-cuts #1380 after its second review round, naming both rounds'
findings; the Playwright evidence rule this PR adds does not apply to it, since no change here is visible
in the site)
````

- [ ] **Step 3: Record the PR number, in one commit**

With `NNN` the PR number:

- `docs/superpowers/plans/2026-10-11-feat-cicd-001-review-guidelines.md`: `pr: null` → `pr: NNN`.
- `docs/product/12-PR-ISSUE-TRACEABILITY.md:419`: after
  `· [#1380](https://github.com/TeneikaAskew/stocks/pull/1380) *evolution*`, which stays (#1380 is
  part of this capability's history), append
  ` · [#NNN](https://github.com/TeneikaAskew/stocks/pull/NNN) *evolution*`.
- `docs/product/02-FEATURE-CATALOG.md:584`: `| Last reviewed | 2026-10-11 |` stays while the commit
  lands on 2026-10-11 (the gate reads the head commit's committer or author date); on a later day, move
  it to that day.

```bash
python3 scripts/gate/spec_gate.py --commit
git add docs/superpowers/plans/2026-10-11-feat-cicd-001-review-guidelines.md docs/product/12-PR-ISSUE-TRACEABILITY.md
git commit -m "docs: record #NNN under FEAT-CICD-001"
```

- [ ] **Step 4: Tick the boxes with evidence, then prove the ready-for-review gate locally**

Change each `- [ ]` under "Done when" to `- [x]` and append ` — <evidence>` after the item's text, the
check name and its output from the tasks above (Task 1 15/15, Task 2 12/12, Task 3 6/6 and 7/7, Task 4
13/13, Task 5's greps, count, stub test and 8/8, Task 6 4/4 and 6/6, Step 1's replay, gate and audit,
and the records). Save the body to `$SCRATCH/pr-body.md`, re-run Step 1, then:

```bash
PR_BODY="$(cat "$SCRATCH/pr-body.md")" PR_TITLE="FEAT-CICD-001: ask reviewers for the complete first review and browser proof" \
PR_NUMBER=NNN PR_DRAFT=false PR_HEAD_REF=feature/feat-cicd-001-review-guidelines-r2 PR_BASE_REF=main \
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
