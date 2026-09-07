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

With an issue number, read the body **and every comment** before anything else,
paging `get_comments` to exhaustion rather than stopping at page 1 — the same
discipline this file requires for issue listings and for review comments, and
for the same reason: the correction is usually the newest thing on the thread.
Comments carry that history: a severity that was challenged, a Codex reply that
already implemented half of it, a prior status comment naming what is still
open. Reading the first page of a long issue gets you the original claim and
none of what has happened to it. Classify:

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
# and: mcp__github__search_pull_requests
#        q="repo:TeneikaAskew/stocks is:open <issue-number>"
# This is a KEYWORD search, not a link lookup: a bare number matches any
# PR whose text happens to mention it, and misses one linked only through
# the issue's development sidebar. So a hit is a candidate, not an answer.
# Confirm the relationship before treating any result as this issue's PR —
# a closing keyword in its body, or the issue's own linked-PR entry — and
# read the issue timeline when the search comes back empty. It is paginated
# too — the fourth such read in this file — so page it out rather than
# concluding "no existing PR" from one page of keyword hits.
# `is:open` matters: without it the search returns closed and merged PRs
# too, and CASE A below would check out a dead PR's retained branch and
# push commits that can never reach the merge gate. Confirm the state of
# whichever PR you pick before reusing its head.
```

**Branch before touching any file** (CLAUDE.md Rule 2), and the two cases are
exclusive. Check out the existing head, or create a branch, never both:

**A dirty worktree stops you here.** Ordinary `checkout` preserves
non-conflicting local edits, so uncommitted work from another task follows you
onto the issue branch: Phase 5 then tests a mixed candidate, and Phase 7's
file-level `git add` can commit hunks that have nothing to do with this issue.
If `git status --porcelain` is not empty, stop and ask whether to stash or
commit it. Never `checkout -f`, which discards it.

```bash
git status --porcelain           # must be empty before going further
git rev-parse --abbrev-ref HEAD
git fetch origin

# CASE A — a PR already exists for this issue (including an auto-created
# fix/workflow-* draft). Work on ITS head. Do not open a second PR.
# First: is the head in THIS repo? A PR from a fork has no
# origin/<headRefName>, so both paths below fail, and Phase 7 would push to
# origin rather than the fork. Read headRepositoryOwner from the PR; if it is
# not TeneikaAskew, STOP and say the PR is from a fork. Neither repo takes
# fork PRs today (every branch is same-repo: claude/*, codex/*, fix/*), so
# this is a guard, not a gap — building fork push-back would be speculative.
# Never `checkout -B` here: -B RESETS an existing local branch to the start
# point, silently discarding unpushed commits from an earlier run.
if git show-ref --verify --quiet "refs/heads/<headRefName>"; then
  git checkout "<headRefName>"        # already local: keep what it carries
  # `|| echo` would swallow the failure: a diverged branch would then be
  # implemented and tested against a head missing remote commits, and only
  # fail at push. A non-fast-forward here is a STOP.
  git merge --ff-only "origin/<headRefName>" \
    || { echo "DIVERGED from origin/<headRefName> — reconcile before any edit"; false; }
else
  git checkout -b "<headRefName>" --track "origin/<headRefName>"
fi

# CASE B — no existing PR. Create one branch, and remember its name; every
# later phase refers back to it rather than reconstructing a prefix.
# Name the base explicitly: without it the branch forks from whatever is
# checked out, so an unrelated feature branch's commits ride into the PR, or
# the branch starts behind main. `git fetch` above does not move HEAD.
git checkout -b fix/<short-description> origin/main   # or feature/ chore/ docs/ test/
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

**On outcomes 2 and 3, deal with the PR as well as the issue.** If Phase 0 took
CASE A there is an open or draft PR attached to this issue, and closing only the
issue leaves it live: it keeps drawing review rounds and CI minutes, and it can
still be merged later by someone who never reads the close comment. Close it as
superseded, naming the evidence, or say explicitly on the PR why it stays open.
The auto-created `fix/workflow-*` drafts are the common case here — a workflow
that has since gone green leaves both an issue and a draft behind.

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
- **Rule 6 — a shape change is TWO change sets, and every phase below is
  written for one.** If this fix changes a response shape, the solyra edits are
  not a footnote: that repo needs its own branch, commit, PR and review, while
  the phases after this one only ever track the stocks checkout and one PR
  number. Carry both explicitly, or the backend merges while the frontend sits
  uncommitted against a contract it no longer matches.

  Concretely: open the solyra PR in the same session and name each PR in the
  other's description. If you cannot do the solyra half now, do not merge the
  stocks half either; say what is outstanding.

  **The consumer changes first, in both directions — not stocks first.** An
  earlier version of this said to merge stocks first, because the snapshot
  solyra vendors is read from stocks `main`. That derives the rollout order
  from what keeps solyra's `contract:check` green, which is a CI question, and
  not from what keeps the deployed app working, which is a different one. For
  a widening it is backwards: this side merges, staging deploys, the API
  starts emitting `null`, and the frontend in front of it still assumes the
  old non-null shape — the runtime break the pair exists to prevent.

  A widening is three steps:

  1. **solyra first** — it widens its TS type and guards every call site `tsc`
     then flags; that pair IS the compatibility change. The null is exercised
     by a TEST-ONLY payload, never solyra's canonical mock, which `satisfies`
     its types and is validated against the vendored schema — still the OLD
     one at this step. No snapshot change, so its `contract:check` still
     passes against the current stocks `main`. Merged and deployed.
  2. **then stocks** — widen the response model, regenerate
     `platform/api/openapi.json`, merge, deploy.
  3. **then solyra again** — `contract:sync`, and the null moves into the
     canonical mock and fixtures now that the schema admits it.

  A narrowing runs the same way: solyra stops reading or sending the field
  first, and this repo drops it only once nothing consumes it. Say in both PR
  descriptions which step yours is.
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
| Signal, indicator, strategy or fire-path code | `env -u REPLAY_PERSIST python -m scripts.replay_signal_monitor --date <D> --tickers SPY,IWM,QQQ`. In-process and the production path per Rule 3.6, so it runs YOUR tree — but read the two notes below before believing its output. |
| Brief or insight code | The as-of entrypoints in-process (`BRIEF_AS_OF`, `INSIGHT_AS_OF`) against the local tree — but they are NOT hermetic; see below before running one. |
| A Cloud Run Job's own behaviour, sizing or schedule | Build the candidate and run it **somewhere that is not the live job** — but read the isolation note below first: a renamed job is not an isolated one. |
| API handler code | The hermetic suite plus a local `uvicorn`; the deployed service is not carrying your change yet. **For a MUTATING route, local is not isolated** — see below. |
| A query plan | `EXPLAIN (ANALYZE, BUFFERS)` runs against live data and is independent of any deploy, so it is valid now — for a **SELECT**. On a mutation it EXECUTES the statement; see below. |

**A local `uvicorn` is process isolation, not data isolation.** The journal
POST/PATCH/DELETE routes, the profile and preferences PUTs and every other
mutating handler write through whatever `gcp/database.py:get_engine()` resolves
to, and in an environment carrying the repo's Cloud SQL credentials that is
production. Running the candidate on `localhost:8000` changes which process
serves the request and nothing about which database it writes. So a mutating
route gets the same treatment as everything else in this phase: an isolated
database, or persistence mocked at the boundary the hermetic suite already
mocks. Read-only handlers are fine as written.

**`EXPLAIN ANALYZE` on an INSERT, UPDATE or DELETE runs it.** `ANALYZE` means
"execute and report actual timings", and Postgres makes no exception for a
mutation. So tuning a write with it against production writes to production.
Two ways out, and say which you used:

- plain `EXPLAIN` (no `ANALYZE`), which plans without executing — estimated
  rows rather than actual, which is weaker but often enough to see a seq scan;
- `./scripts/db_query_cr.sh` **without** `--commit`, whose rollback-by-default
  transaction is exactly the isolation this needs. That is the load-bearing
  safety guarantee CLAUDE.md describes for a typo'd UPDATE, and it covers this
  case for free.

Never run `EXPLAIN ANALYZE <mutation>` through a connection you opened
yourself.

**The signal replay is hermetic only if `REPLAY_PERSIST` is unset.**
`scripts/replay_signal_monitor.py:465-466` treats that variable as an alias for
`--persist`:

```python
# REPLAY_PERSIST env var is an alias for --persist. Either source enables.
persist_mode = args.persist or os.environ.get('REPLAY_PERSIST', '').lower() == 'true'
```

So an environment carrying it from an earlier acceptance run commits captured
fires to `signal_alerts` through production credentials, while the instruction
above calls the command side-effect-free. Hence `env -u REPLAY_PERSIST` in the
table, rather than trusting the shell you happen to be in.

**A replay that exits 0 with zero fires may mean every bar failed.**
`scripts/replay_signal_monitor.py:174-178` catches every exception from
`evaluate_ticker` as a `logger.warning` and continues, and the no-fire path
prints "No signals fired during the replay window." and `return 0`. A candidate
that raises on every single bar therefore produces a clean-looking summary and
a zero exit — the shape of a passing run, from code that evaluated nothing.

So "zero fires" is only evidence once you have checked it is not zero
evaluations:

```bash
set -o pipefail          # else the pipeline reports tee's status, not python's
env -u REPLAY_PERSIST python -m scripts.replay_signal_monitor \
    --date <D> --tickers SPY,IWM,QQQ 2>&1 | tee /tmp/replay.log
echo "exit=$?"                                     # must be 0
grep -c "evaluate_ticker raised" /tmp/replay.log   # must be 0
```

**And know what this replay is NOT exercising.** `filter_to_rth` runs only
under `persist_mode` (`scripts/replay_signal_monitor.py:505-512`), so the
`env -u REPLAY_PERSIST` invocation above — the one that makes it safe — is
also the one that leaves the RTH filter off. Production evaluates only while
`is_market_hours()` is true (`gcp/signal_monitor.py:2267`), so this replay
feeds premarket and after-hours bars into rolling state and into
`evaluate_ticker`, and the positive-`Bars` check below can pass on a date with
no RTH data at all. Fire counts from it are therefore NOT comparable to
production, and a candidate can fire here in a way production never would.

Use it for "does the candidate raise / does the fire path execute". Do NOT
quote its counts as production behaviour. If the issue turns on a fire count,
the Rule 3.6 answer applies: decouple `filter_to_rth` from `persist_mode` with
an `--rth` flag in a small PR against the script FIRST, then run the audit —
rather than reading numbers this invocation cannot produce faithfully.

Three separate things have to hold, and each covers a hole the others do not:

- **`pipefail` (or `${PIPESTATUS[0]}`).** Without it the pipeline's status is
  `tee`'s, which is 0 whatever python did. A replay that died in imports, DB
  init or argument parsing never reaches the summary, logs no
  `evaluate_ticker raised`, and reports a clean pipeline.
- **Zero warnings.** A non-zero count fails the verification regardless of what
  the summary says.
- **A positive `Bars` count for every ticker you asked for.** The summary's
  per-ticker table is the check. `replay_ticker` returns `(0, 0)` at
  `scripts/replay_signal_monitor.py:143-144` when `bars.empty` — before
  `evaluate_ticker` is ever called — so a weekend date, a ticker with no
  intraday ingestion, or a typo'd symbol produces zero fires, zero warnings and
  a zero exit. Every signal this section relies on reads clean, and nothing
  was evaluated.

Paste all three alongside the fire counts.

**`BRIEF_AS_OF` and `INSIGHT_AS_OF` are not sandbox flags.** Setting either
resolves to `allow_update=True`:

```
gcp/premarket_brief.py     if os.environ.get('BRIEF_AS_OF'):   return True, 'replay_refresh'
gcp/insight_pipeline_job.py if os.environ.get('INSIGHT_AS_OF'): return True, 'replay_refresh'
```

So an as-of run persists history and overwrites the canonical report row for
that date. `run_kind='replay_refresh'` labels what it wrote, which makes the
write *distinguishable* — it does not make it *not happen*. Run one in an
environment holding production credentials and unreviewed code has rewritten a
production row. And in a sandbox with no database path it writes nothing and
exercises none of the persistence, so it is not a candidate check either way.
Mock the persistence and the outbound calls, or point at an isolated database,
before running one — the same requirement as the candidate job below, for the
same reason.

**A `<job>-candidate` isolates the Cloud Run resource, not its dependencies.**
There is no staging database here. `gcp/deploy.sh:50` sets a single
`DB_NAME="trading"` inside `_env_string`, which every job deploy passes
verbatim, and `--set-secrets` hands the candidate the same credentials and the
same Discord webhooks. So a candidate built from unreviewed code and executed
under a new name writes to production exactly as the live job would. The rename
changes which row in the Cloud Run console it appears under, and nothing else.

Before executing any candidate, isolate what it can touch, in this order:

1. **Use the job's own dry-run flag if it has one** (`gcp/apply_schema.py`,
   `gcp/auth_email_templates.py` and `gcp/auto_refresh_top_n.py` all take
   `--dry-run`). Name the flag in the evidence, so the reader can tell a
   no-write run from a real one.
2. **Otherwise run the entrypoint in-process**, the way
   `scripts/replay_signal_monitor.py` does: production code path, DB upsert and
   webhook mocked at the boundary. That is the Rule 3.6 path and it is
   hermetic, so it proves behaviour without touching live state.
3. **If neither exists, do not execute the candidate at all.** Prove the change
   with the Rule 0.3 I/O-shape test — "N source rows of K tickers triggers
   exactly K queries" — and defer behaviour proof to the post-merge deploy in
   Phase 8 step 8. Say plainly in the issue that the candidate was not executed
   and why, rather than running it against production and calling that
   isolated.

Adding a dry-run flag to a job that lacks one is a legitimate small PR before
the audit, the same way Rule 3.6 says to add a missing as-of flag rather than
write a throwaway harness.

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

0. **If the PR is a draft, mark it ready — before any check below.** CASE A can
   land you on an auto-created `fix/workflow-*` draft, and pushing to a draft
   does not un-draft it; GitHub refuses the merge. CLAUDE.md's failure-handler
   procedure requires converting it once fixed.

   This is step 0 rather than a late step because **marking ready is itself a
   review trigger** (CLAUDE.md §2.5: "a PR opened for review, a draft marked
   ready, or an explicit `@codex review`"). Undrafting after the review checks
   starts a fresh review that the remaining steps would walk straight past, and
   the PR merges while it is still running. Undraft first, then let every check
   below run against the review that transition triggered.

   If you cannot or should not undraft it — a PR this session did not open —
   stop and say a human must.
1. `pull_request_read` `method: "get_review_comments"` — **before** CI, not
   after, and **page it to exhaustion**. Nine review rounds on one PR is not
   hypothetical here, and a first page that happens to show every thread
   resolved says nothing about the next one. Zero unresolved means zero across
   every page, the same discipline the issue listing and `get_reviews` already
   get.
2. Confirm the current head **has been reviewed**, which is not the same as "a
   review object exists for it". A clean run posts no review at all, only a
   reaction, so requiring a review object would deadlock every PR that has
   nothing wrong with it. Either of these satisfies this step:
   - `pull_request_read` `method: "get_reviews"` returning a review that is
     **authored by the review bot**, is not `CHANGES_REQUESTED`, whose
     `commit_id` is the head SHA. **Only if step 0 actually undrafted the PR**,
     the review must also carry a `submitted_at` **after** that transition:
     marking a draft ready does not move the head, so a review of that same SHA
     from an earlier `@codex review` would satisfy a SHA-only test while the
     readiness-triggered run is still going. Note the transition time when you
     undraft. **On a PR that was never a draft — which is every CASE B PR this
     command opens — there is no transition and no cutoff**; the head SHA and
     the author check carry the step on their own, and applying a cutoff to an
     event that did not happen makes the gate unsatisfiable on the normal path.
     **`get_reviews` returns oldest first, so the current
     review is on the LAST page**; reading page 1 and finding an older "no
     findings" is exactly how #991 merged two minutes after a review it never
     saw; or
   - the Codex summary comment showing **Completed** against the head SHA —
     and, **again only where step 0 undrafted**, started after that transition,
     for the same reason and with the same exemption. The previous run's
     summary keeps reading Completed for an unchanged SHA until the newly
     triggered run replaces it, so on that path a SHA-only summary check merges
     straight through the window. The summary carries its own timestamp;
     compare it when the transition exists.

   **Check the author, not just the SHA.** Every reply you post on a thread is
   itself recorded as a review on the current head. Measured on this PR:
   `get_reviews` returned eight entries for `dcc8843`, seven of them mine, and
   the only Codex review named `06160ad`. A SHA-only test would have let your
   own replies satisfy the gate while the real review was still running.

   What fails this step: a summary showing Running, or naming an older commit
   with all threads `is_outdated`, or a head whose only reviews are yours. That
   head is unreviewed — comment `@codex review` and wait.
3. **Re-page `get_review_comments` now**, after step 2 established the review
   is Completed — do not reuse step 1's snapshot. Step 1 runs deliberately
   before CI and can therefore run while the current head's review is still
   posting; every finding it lands between that read and step 2's completion is
   absent from what you are holding. And a review WITH findings satisfies step 2
   perfectly well, since the bar there is "not `CHANGES_REQUESTED`", so nothing
   else catches it. Then: every thread fixed-and-resolved, naming what changed
   and the covering test and commit, or replied to with why not. Zero unresolved
   across every page is the bar.
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
6. Only then CI green on the current head, and no merge conflict.
7. **Merge it.** Steps 0-6 are the gate, not the destination; stopping here
   leaves the fix on a branch while Phase 9 describes the issue as landed.
   Merge once every step above passes, and record the merge commit in the
   Phase 9 status comment.

   Two cases where you stop instead of merging, and say which: the PR is one
   this session did not open and was not asked to drive, so the merge is its
   author's call; or the user has said they want to merge it themselves. Never
   merge to get past a step above that has not passed.
8. **Merging is not deploying.** If Phase 6 deferred the final proof to the
   merged image, the issue is not closeable yet, because nothing between here
   and Phase 9 puts that image in front of a user.

   `gcp/cloudbuild/deploy-solyra-api-staging-cloudbuild.yaml:26` says it
   outright: *"Merging to main NEVER touches prod. Prod moves only when a human
   runs the `deploy-solyra-api-prod` trigger."* And the staging build itself is
   conditional — the same file records that the trigger's `includedFiles` is
   `platform/**, lib/**, requirements.txt, gcp/database.py`, so a fix under
   `scripts/` or `gcp/` that an API route imports at request time merges to
   main and starts **no build at all**. Cloud Run Jobs are further out still:
   they move only when someone runs `./gcp/deploy.sh <target>`.

   So after merging, do one of these and say which:

   - **Deploy it yourself where you can** — `./gcp/deploy.sh <target>` for a
     job — then re-run the Phase 6 verification against the deployed revision
     and paste that output. Name the digest.

     **Check out the merge commit first.** `deploy.sh` builds by copying the
     working tree into a tmpdir and running `gcloud builds submit --tag
     "${IMAGE}" "$tmpdir"`; it never reads a commit and never records one. The
     merge happened on the remote, so the local checkout is still the feature
     branch — and if `main` advanced while the PR was open, deploying from
     here publishes an image missing those merged changes, under a tag that
     claims to be main:

     **And build from a pristine tree, not this one.** `deploy.sh:64-66` does
     `cp -r lib/ gcp/ scripts/` straight out of the working directory, and
     `git checkout` does not remove untracked or modified files — `-f` would be
     the flag that discards local modifications, and even that leaves untracked
     ones. Phase 7's deliberately file-scoped `git add` is what makes this
     reachable: anything a run left behind under those three directories gets
     copied into the production image, uncommitted and unreviewed, while
     `git rev-parse` reports the merge SHA and looks clean. Use a separate
     worktree so there is nothing to leave behind:

     ```bash
     git fetch origin main
     git worktree add /tmp/deploy-src origin/main
     cd /tmp/deploy-src
     git rev-parse HEAD                    # must equal the PR's merge commit
     test -z "$(git status --porcelain)"   # must be silent
     ./gcp/deploy.sh <target>
     cd - && git worktree remove /tmp/deploy-src
     ```

   - **For an API change, confirm the staging build actually fired** rather
     than assuming the merge triggered one; a merge outside `includedFiles`
     silently does not. **Staging is not the end of it.** The same file says
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

     ```bash
     REV=$(gcloud run services describe solyra-api-staging --region=us-east1 \
             --format=json | python gcp/cloudbuild/serving_revision.py)
     # ...verify against staging while it is serving $REV...
     gcloud builds triggers run deploy-solyra-api-prod \
       --substitutions=_EXPECT_STAGING_REVISION="$REV"
     ```

     It fails closed, which is the safe direction — but "run the trigger" as
     written simply does not promote anything, so the issue would be closed on a
     deploy that never happened.
   - **Where promotion is an owner action this session cannot take**, keep the
     issue OPEN, put the exact command in "Still open before this closes", and
     say the fix is merged but not yet serving. Closing on candidate evidence
     while calling it production proof is the failure this whole phase exists
     to prevent.

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
