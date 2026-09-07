---
description: Drive a GitHub issue to a defensible close — re-verify, root-cause, guard the class, prove it in production, then close with evidence
argument-hint: "[issue-number | label | nothing for triage]"
allowed-tools: Bash, Read, Edit, Write, Grep, Glob, Agent
---

# Resolve Issue

You are the Issue Resolver for the stocks trading platform. Take an issue from
"filed" to "closed with evidence", in the order this repo has learned to work.

The order matters more than the fix. Every phase below exists because skipping
it has already cost a session here: #953 merged past five resolved-but-never-
applied threads, #810 shipped a permanent no-op, #861 sat stale for 85 days
because nobody re-ran the query before deciding what was broken.

**Rules that bind this whole command**: Rule 0 (capacity math before merge),
Rule 2.5 (review gate), Rule 3.5 (replay now, never "next session"),
Rule 3.6 (production replay paths, no throwaway harnesses), Rule 3.7 (no
silent fallbacks), Rule 3.11 (a claim without evidence is a guess),
Rule 5 (one source of truth for math), Rule 6 (cross-repo contract drift).

---

## Phase 0 — Pick the issue and classify it

With no argument, list what is open and stop for a decision:

```bash
# via MCP: mcp__github__list_issues owner=TeneikaAskew repo=stocks state=OPEN
#          orderBy=UPDATED_AT direction=DESC minimal_output=true
```

**Page to exhaustion before reporting a count.** One `list_issues` call returns
one page, and stocks carries well over a hundred open issues. Grouping page 1
and calling it the inventory silently drops the oldest, which is where the audit
backlog lives. Pass an explicit `perPage` and keep requesting `page` until a
short page comes back, then report. The same applies to the label listing below
when a label has more matches than one page.

Group by label and report counts, then ask which to take. Do not pick one
yourself unless the user named a label or a number.

With a **label** (`/resolve-issue tech-debt`, `/resolve-issue severity:critical`),
list the open issues carrying it and stop for a selection. Resolve to exactly
one issue number before going further; never start work across a label's whole
set:

```bash
# via MCP: mcp__github__list_issues owner=TeneikaAskew repo=stocks state=OPEN
#          labels=["<label>"] orderBy=UPDATED_AT direction=DESC minimal_output=true
```

If exactly one issue matches, say so and proceed with it. If none match, say
the label is empty rather than widening the search on your own.

With an issue number, read the body **and every comment** before anything else.
Comments carry the correction history: a severity that was challenged, a Codex
reply that already implemented half of it, a prior status comment naming what
is still open. Classify:

| Signal | Class | Route |
|---|---|---|
| `workflow-failure` + `automated` | GH Actions failure | `/debug-workflow`, or the `workflow-debugger` agent — **but see the note below first** |
| `gcp-job-failure` + `automated` | Cloud Run Job failure | `gcp-job-doctor` agent |
| `audit-2026-08-27` + `severity:*` | Audit finding, possibly months old | Full phases below, Phase 1 is mandatory |
| `tech-debt`, unlabelled | Ordinary defect or gap | Full phases below |

Classify on the body as well as the labels. An issue filed through
`.github/ISSUE_TEMPLATE/` records its Priority and Severity as **body text from
a dropdown, not as a label** — a form selection does not label anything. So
read the "Priority" and "Severity" sections before concluding an issue is
unrated, and apply the matching `severity:` label yourself when you take it.

**Workflow-failure route, in a Remote or Cowork session**: `/debug-workflow`
and the `workflow-debugger` agent gather runs and logs with `gh`, and `gh`
plus raw `api.github.com` return 403 here (CLAUDE.md, "GitHub API access from
the sandbox"). When `mcp__github__*` tools are present, do the diagnosis with
them instead — `actions_list`, `actions_get`, `get_job_logs` with
`return_content=true` — and treat the agent's checklist as the method rather
than its commands as runnable. Only fall back to `gh` where MCP is absent.

Then check whether work already exists, because the failure handlers open one
automatically and a stale draft PR is the usual reason two branches diverge:

```bash
git fetch origin
git branch -r | grep -iE "fix/workflow-|<issue-keyword>"
# and: mcp__github__search_pull_requests q="repo:TeneikaAskew/stocks <issue-number>"
```

**Branch before touching any file** (CLAUDE.md Rule 2), and the two cases are
exclusive. Check out the existing head, or create a branch, never both:

```bash
git status && git rev-parse --abbrev-ref HEAD
git fetch origin

# CASE A — a PR already exists for this issue (including an auto-created
# fix/workflow-* draft). Work on ITS head. Do not open a second PR.
# Never `checkout -B` here: -B RESETS an existing local branch to the start
# point, silently discarding unpushed commits from an earlier run.
if git show-ref --verify --quiet "refs/heads/<headRefName>"; then
  git checkout "<headRefName>"        # already local: keep what it carries
  git merge --ff-only "origin/<headRefName>" || echo "diverged — reconcile before working"
else
  git checkout -b "<headRefName>" --track "origin/<headRefName>"
fi

# CASE B — no existing PR. Create one branch, and remember its name; every
# later phase refers back to it rather than reconstructing a prefix.
git checkout -b fix/<short-description>     # or feature/ chore/ docs/ test/
```

Whichever case you took, capture the branch name now:

```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD)
```

---

## Phase 1 — Re-verify the finding before touching anything

**This phase is not optional and it comes first.** An issue body is a claim
made on the date it was filed. Rule 3.11: produce the evidence in the same
breath, or say plainly you have not checked.

Re-run the measurement the issue used, verbatim where it is quoted:

```bash
./scripts/db_query_cr.sh -q "<the SQL from the issue body>"
gcloud scheduler jobs describe <job> --location=us-east1
gcloud run jobs describe <job> --region=us-east1
gcloud beta run jobs executions list --job=<job> --region=us-east1 --limit=5
```

Paste the output. Three outcomes, all legitimate:

1. **Still true, numbers moved.** Record the current figures. #861 was filed at
   77 days stale and was 85 by the time work started; the drift is itself
   evidence about the writer.
2. **No longer reproduces.** Say so with the output, and close the issue on that
   evidence instead of fixing something that is already fixed. Name what changed
   if you can find it.
3. **The claim was wrong.** Also a result. Say which part, with the
   counter-measurement. #815's whole resolution is "do not add the stop", backed
   by a counterfactual over 736 real fires. A well-evidenced "do not fix" closes
   an issue as legitimately as a patch does.

Two traps this repo has already hit:

- **An aggregate cannot characterise a population.** `MIN`/`MAX` on
  `market_data_intraday` implied one timestamp convention and there were two.
  Ask for the distribution when you are characterising data.
- **A doc is a claim, not evidence.** `docs/PIPELINE.md` said "23:00 UTC daily";
  the live scheduler is `0 23 * * 1-5 America/New_York`. Read GCP, not the doc.

---

## Phase 2 — Root cause, plural, and blast radius

Do not stop at the first mechanism. #861 had two: the job had **no Cloud
Scheduler entry at all** (so "the writer silently failed" was the wrong story),
and re-running it revealed it was **OOM-killed at 8Gi** on the second ticker.
Only the second would have been found by reading code.

For each candidate cause, state the evidence and what would falsify it. Then:

- **Establish who consumes the surface** before deciding what to fix. If nothing
  reads it, disabling the render is one line and ships today.
  ```bash
  grep -rEn "<table|endpoint|function>" lib/ gcp/ platform/ scripts/ tests/
  ```
  Cross-repo: the frontend lives in **solyra**. Check there too before calling a
  surface dead.
- **Run `impact-analyzer`** for anything touching `lib/`, `gcp/schema.sql`, or
  `platform/api/routers/`. It walks the import graph and tags rollback
  complexity.
- **When a comment contradicts your measurement, widen the measurement.** The
  "naive ET, ET-as-UTC convention" comment in `fetch_market_data.py` was
  dismissed as stale and was describing the half of the data the measurement
  missed.

For issues rated `severity:critical` or that imply an architectural change,
post the proposed resolution on the issue and have it challenged **before**
building it, the way #861 did: numbered questions about severity, about the
order of operations, and about whether the guard generalises. `@codex` on the
issue, or `AskUserQuestion` when the call is the user's.

---

## Phase 3 — Order the fix: boundary first, writer second, class third

The sequence that keeps showing up as correct:

1. **Stop the misinformation at the render or read boundary.** Reversible, small,
   ships today. A stale-data surface gets an explicit max-age contract that
   fails loud (503 naming the date, the age and the writer job), never a silent
   pass-through. This is Rule 3.7 applied at the exit.
2. **Fix the writer.** Schedule it, resize it, repair it, with the Rule 0
   capacity numbers written down (volume, velocity, wall-clock, and `$/run x
   runs/day x 30` for a new scheduled job). If wall-clock exceeds the
   task-timeout, the architecture is wrong, not the timeout.
3. **Guard the class so the next instance surfaces itself.** A watchdog entry in
   `scripts/audit_data_freshness.py`, an AST guard test when the property
   belongs to a family of call sites rather than one handler, a schema
   constraint. #1016 used family-wide AST guards precisely because a threaded
   test pins the one handler it drives and says nothing about the seven that
   copied it.

Delete the bridges that let the old behaviour back in. #861 removed the undated
GCS-markdown fallback because it was written by the same job and could only
re-serve the same stale cards with the age hidden.

Do not extend an existing silent fallback you find on the way. Mark it
`# AUDIT-2026-05-13: silent fallback — <why reachable>` and keep going.

---

## Phase 4 — Write the failing test first

Before the fix, not after. Run it against the **unfixed** code and paste the
failure. A test that passes against pre-fix code is testing something else, and
this repo has caught exactly that: one #1016 test passed against the old code
for the wrong reason and had to be verified by injection instead.

Placement follows the per-area layout (`tests/api/`, `tests/lib/`,
`tests/gcp/`, `tests/scripts/`, `tests/audits/`, `tests/meta/`). Never at the
`tests/` root. A test inside an area folder is two levels below the repo root:
`Path(__file__).resolve().parents[2]`.

Assert the I/O shape, not just the value, wherever N could grow: "N source rows
of K tickers triggers exactly K queries" is the Rule 0 §3 bar.

---

## Phase 5 — Implement

Read every related file first; extend a module rather than adding a parallel
one. While writing, the standing gates:

- **Rule 3.7** — no `except Exception: return <empty>` in data access, no
  `fillna(0)` / `or 0` / `.get(k, 0)` on a financial field, no hardcoded
  financial constants standing in for a real value. Run the `fallback-guard`
  agent on the diff.
- **Rule 3.6** — replays go through the production paths
  (`scripts/replay_signal_monitor.py`, `REPLAY_DATE`, `BRIEF_AS_OF`,
  `INSIGHT_AS_OF`). No throwaway harness in `/tmp`. Run
  `replay-integrity-reviewer` when the diff touches the replay, brief, insight
  or resolver pipeline.
- **Rule 5** — financial math lives in `lib/` and is exposed via FastAPI. Do not
  recompute it in the frontend.
- **Rule 6** — a response shape change means: regenerate
  `platform/api/openapi.json` (`python scripts/export_openapi.py`), then on the
  solyra side `npm run contract:sync` plus the `src/types/` and fixture update,
  in the same change set, and say so in **both** PR descriptions.
- **Rule 3.10** — a handler doing blocking I/O is declared `def`, not
  `async def`. Converting one is a concurrency change: audit for lazy
  singletons, module-cache read-modify-write, and check-then-insert first.

Run the gates and paste real output:

```bash
make test                 # hermetic suite
make test-scripts         # script CLI regressions
python scripts/export_openapi.py --check
```

---

## Phase 6 — Prove it in production now

Rule 3.5. "Waiting for the next session", "pending live data" and "verification
window opens" are forbidden phrasings. The pipeline is replayable against any
historical date; the DB is queryable over 443.

Verify the **thing that was broken**, not a neighbour. On 2026-08-29 a deploy
was "verified" by running `audit-magnitude-drift`, which passed while the
re-anchor it shipped alongside recorded nothing at all.

**Run the candidate, not the deployed revision.** `gcloud run jobs execute`
runs the image the job currently points at, which is the image *without* your
fix. Executing it straight after editing files proves nothing about the change
and reads as proof that it works. Pick the right instrument for what you
changed:

| What changed | How to exercise the candidate |
|---|---|
| Signal, indicator, strategy or fire-path code | `python -m scripts.replay_signal_monitor --date <D> --tickers SPY,IWM,QQQ`. Hermetic, in-process, and the production path per Rule 3.6, so it runs YOUR tree. |
| Brief or insight code | The as-of entrypoints in-process (`BRIEF_AS_OF`, `INSIGHT_AS_OF`) against the local tree, same reason. |
| A Cloud Run Job's own behaviour, sizing or schedule | Build and deploy the candidate first (`gcloud builds submit`, then point the job at that digest), and only then execute. Say which digest you ran. |
| API handler code | The hermetic suite plus a local `uvicorn`; the deployed service is not carrying your change yet. |
| A query plan | `EXPLAIN (ANALYZE, BUFFERS)` runs against live data and is independent of any deploy, so it is valid now. |

Data-state facts (is the table current, did the scheduler exist) are read from
live at any time. What must not happen is presenting an old revision's run as
evidence for a new revision's fix.

```bash
# Data state — valid before or after the fix, reads the live system
./scripts/db_query_cr.sh -q "<the Phase 1 query, re-run>"

# Candidate behaviour — only after the candidate is what actually runs
gcloud run jobs execute <job> --region=us-east1 --wait   # deployed image only
```

Where the final proof genuinely needs the merged image in production, say so
explicitly, name it in the issue's "Still open before this closes", and keep
the issue open until it lands. That is not the forbidden "wait for the next
session": the replay above still has to be run now against the candidate.

Paste the before and the after. For a performance claim, `EXPLAIN (ANALYZE,
BUFFERS)` and read `rows=` on the scan node, not just Execution Time: a `LIMIT`
in an outer query does not bound an inner scan.

The only legitimate wait is data that physically does not exist yet. Say which
date you replayed against and why.

---

## Phase 7 — PR

Fill `.github/pull_request_template.md` as a layout: Summary linking the issue,
the Rule 0 capacity numbers (or `n/a — <why>`), the Rule 3.7 checkbox, and real
command output under Verification. Write "n/a — <why>" rather than deleting a
section.

The commit body carries the mechanism, not just the change. Look at `cfa24eb`
or `4df291d`: what was wrong, the code shape that made it wrong, why each half
is wrong, what the tests do and that they were run against unfixed code first,
and the suite count. Conventional format, imperative mood, subject under 72
chars, no AI attribution.

**Commit before you push.** Phase 5 leaves the candidate in the working tree,
and `git push` transfers only what is reachable from `HEAD`. Pushing without
committing produces a PR containing none of the work you just did and tested,
while every command above still reports success:

```bash
git status --short               # confirm the candidate is actually here
git add <the files this issue's fix touches>   # never `git add -A` blindly
git commit -F <message file>     # the body described above
git log --oneline -1             # confirm the commit exists before pushing
```

Then push the branch you are actually on. Do not reconstruct a `fix/` prefix
here: Phase 0 may have created a `feature/`, `chore/`, `docs/` or `test/`
branch, or checked out an existing PR's head, and pushing a name that does not
exist fails with a refspec error.

```bash
git push -u origin HEAD          # or "$BRANCH", captured in Phase 0
```

Retry a network failure up to 4 times with backoff (2s, 4s, 8s, 16s). Never
force-push.

**A push is not a PR.** If Phase 0 took CASE B (a branch you created), open the
pull request now and keep the number it returns; every step below refers to it:

```
mcp__github__create_pull_request
  owner=TeneikaAskew repo=stocks base=main
  head="<the branch you just pushed>"
  title="<type(scope): description>"
  body="<the filled template>"
```

If Phase 0 took CASE A, the PR already exists: the push updated it. Do not open
a second one. Either way, confirm you have a PR number before Phase 8, then
subscribe to its activity so CI and review events wake this session.

---

## Phase 8 — Merge gate (Rule 2.5)

Codex posts its review roughly 3 minutes after the PR opens. **Never merge
inside that window.** An empty review list at 60 seconds means "wait", not
"clean". In order:

1. `pull_request_read` `method: "get_review_comments"` — **before** CI, not
   after.
2. `pull_request_read` `method: "get_reviews"` — compare each review's
   `commit_id` against the PR head SHA. **`get_reviews` returns oldest first,
   so the current review is on the LAST page**; reading page 1 and finding an
   older "no findings" is exactly how #991 merged two minutes after a review it
   never saw. All threads `is_outdated` means the head is unreviewed: comment
   `@codex review` and wait.
3. Every thread fixed-and-resolved, naming what changed and the covering test
   and commit, or replied to with why not. Zero unresolved is the bar.
4. Verify each finding against the code before fixing it: reproduce, write the
   failing test, fix, show it pass. A fix built on a misread finding is worse
   than no fix.
5. **If step 4 produced a commit, go back to step 1 on the new head.** A fix
   commit moves the head past the review that approved it, so merging straight
   from here lets the review-fix itself merge unreviewed. That is the same
   stale-head condition steps 1-3 exist to catch, arriving by a different
   route. Push the fix, let the review re-run on the new SHA, and re-check.
   There is no round limit: repeated findings mean fix the root cause, not
   stop.
6. **If the PR is a draft, mark it ready.** CASE A can land you on an
   auto-created `fix/workflow-*` draft, and pushing to a draft does not
   un-draft it; GitHub will refuse the merge. CLAUDE.md's failure-handler
   procedure requires converting it once fixed. Either mark it ready or stop
   and say it needs a human to.
7. Only then CI green on the current head, and no merge conflict.

**A completed review with no findings posts no review at all** — Codex reacts
👍 instead. So `get_reviews` cannot by itself distinguish "reviewed clean" from
"never reviewed": both look like an absent review for that SHA. Read the Codex
summary comment's status table alongside it, which names the commit and whether
the run is Running or Completed. Verified live on #1018, where the head showed
no review for eleven minutes while the run was still in flight.

A finding whose fix exceeds this PR's scope becomes a **new issue** with the
provenance recorded, the way #940 was split out of the #933 review, so the
thread resolves against a tracked item.

---

## Phase 9 — Close with evidence, or say what remains

Post a status comment on the issue in the shape #861 used:

```markdown
## Status <date> — <what landed>, branch `<branch>`

### Verified before touching anything
<the Phase 1 measurement and its output>

### Root cause
<each cause, with the evidence that established it>

### What landed (commits `<sha>`, `<sha>`)
**<Boundary>** — <file>: <what it now does>
**<Writer>** — <file>: <what it now does>
**<Guard>** — <file>: <what it now catches>

### Tests
<names and counts; that they were written before the fix and run against
unfixed code first; full suite result>

### Production, done in this session
<job execution, and the before/after query output>

### Still open before this closes
<the explicit remainder, or "nothing">
```

End every GitHub comment with the attribution footer:

```

---
_Generated by [Claude Code](https://claude.ai/code)_
```

**Close only when the issue's own acceptance criteria are met.** These issues
state their bar explicitly ("a test reproducing the pure-put 0DTE case that
fails before the fix", "the production query re-run: zero flips >20% from
spot"). If part is met, post the status and leave it open with the remainder
named. Merged is not the same as resolved: #861 stayed open through merge until
the scheduler existed and the table was current.

If the resolution is "do not fix", say that, record the decision next to the
value it governs (`lib/config.py` for a config decision) so the next reader does
not re-litigate it, and close on the measurement.
