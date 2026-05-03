# Project Instructions for Claude Code

## Project Overview
This is a stocks/trading application project that includes Google Apps Script components for market data fetching, historical data backfilling, and continuation systems for long-running operations.

## Critical Rules - MUST FOLLOW

### 0. Production-Grade Architecture — NON-NEGOTIABLE

**You only ship production-grade solutions. Every design must explicitly account for cloud and data capacity at design time, NOT as future work.**

This rule was added on **2026-05-01** after a Phase 0.5 incident where I shipped a script with a known per-signal-query architecture, flagged it as "future-work, non-blocking" in my own PR review, then watched it time out repeatedly in production while sending the user a stream of failure emails. The runbook I wrote alongside the PR explicitly told the user to run the exact workload my script couldn't handle. That cost real GCP money, real attention, and real trust.

#### Rules

1. **No "future-work, non-blocking" perf flags on workloads in the runbook.** If a PR's runbook says "kick off this backfill", the code in that PR must handle that backfill. Either fix the perf concern before merging or remove the workload from the runbook with an explicit "do not run X until Y lands."

2. **Always do a back-of-envelope capacity calculation BEFORE merging.** Three numbers, written in the PR description:
   - **Volume**: how many input rows × bytes/row
   - **Velocity**: SQL queries / API calls / network round-trips per input row × total
   - **Wall-clock**: queries × per-query latency at production driver speeds (pg8000 + Cloud SQL Connector ≈ 0.5–2 s per round-trip; psycopg2 ≈ 50–200 ms)
   If wall-clock exceeds the configured Cloud Run task-timeout, the architecture is wrong, not the timeout.

3. **Hermetic tests are necessary but not sufficient.** Synthetic in-memory DataFrames run in microseconds; production runs against the network. A test suite of pure-helper unit tests proves correctness, not deployability. Every PR that touches a Cloud Run job must include either:
   - A test that asserts the I/O shape (e.g. "N source rows of K tickers triggers exactly K queries"), or
   - A documented production smoke test in the test plan with the actual data volume the runbook will hit.

4. **Default architectural patterns for this stack:**
   - **Batch SQL queries by partition/grouping key** (ticker, date, etc.) — never per-row when N could exceed 100. Pull one query covering the union range, slice in memory.
   - **Bound memory** — write to DB in per-group chunks rather than accumulating all results before any commit. A crash mid-job should leave partial progress durable, not lose everything.
   - **Observable progress** — log per-group counts so a 30-minute job is debuggable, not a black box. `logger.info("ticker=%s processed=%d/%d", ...)` is the bar.
   - **Resilient to bad data** — one missing partition logs a warning and skips, doesn't crash the batch.
   - **Idempotent re-runs** — `ON CONFLICT DO UPDATE` so a re-run after a partial failure converges, not duplicates.
   - **Bounded retries** — Cloud Run can't distinguish transient from permanent failures. `--max-retries 0` is the default unless you can prove transient retries help and double-emails are acceptable.

5. **Cloud Run Job sizing checklist:**
   - **task-timeout**: ≥ 4× the wall-clock estimate. Cloud Run charges runtime, not the cap, so headroom is free.
   - **memory**: ≥ 512 MiB (gen2 minimum with always-allocated CPU). Estimate peak working-set, double it.
   - **max-retries**: 0 unless explicitly justified.
   - **--args**: use `--args="--mode=foo"` (with `=`) when the value starts with `-`, otherwise gcloud parses it as a new flag.

6. **Cost discipline:**
   - Estimate **$/run × runs/day × 30** in the PR description for any new scheduled job.
   - A scheduler firing a failing job is a slow leak — paused/disabled-on-failure beats endless-retry-on-failure.
   - Cloud SQL queries are free (instance is always-on); Cloud Run round-trips are cheap individually but expensive in aggregate. Optimize round-trips, not query cost.

7. **When you find yourself writing "non-blocking", "future-work", or "for now" in a perf-related context — stop and re-read rule 1.** Those phrases are how shipping happens with known-broken architecture. They are only acceptable when the slow path is genuinely unreachable from the runbook in the same PR.

### 1. File Management Philosophy - READ FIRST, CREATE LAST
- **ALWAYS** read and understand existing files before making any changes
- **SEARCH** thoroughly for related files using Grep, Glob, and Read tools
- **NEVER** create new files if functionality can be added to existing files
- **PREFER** modifying/extending existing modules over creating new ones
- When addressing a problem:
  1. First: Read ALL related files to understand current implementation
  2. Second: Check if similar functionality already exists
  3. Third: Consider if changes can be made to existing files
  4. Last resort: Only create new files when absolutely necessary
- Before creating any file, ask yourself:
  - Have I read all related existing files?
  - Can this be added to an existing module?
  - Is there a similar pattern already in the codebase?
  - Would modifying an existing file be more appropriate?

### 2. Git Commit Guidelines
- **NEVER** include Claude branding in commits (no "built by Claude", "generated by Claude", etc.)
- **NEVER** use the 🤖 emoji or Claude-specific signatures in commit messages
- Write commit messages as if you are a human developer on the team
- Use conventional commit format: `type: description` (e.g., `fix: resolve API timeout issue`)
- Keep commit messages concise and focused on the change itself

### 2. Branching Strategy

**REMINDER: never edit on `main` directly. Always start on a feature branch.**
This is a guardrail for consistency and reliability — `main` is shared,
deployed, and reviewed; commits there bypass CI / PR review and create
drift between local and origin.

#### First action of every session

Before touching ANY file, run:
```bash
git status                    # confirm current branch
git rev-parse --abbrev-ref HEAD
```

If the result is `main`, STOP and create a feature branch first:
```bash
git checkout -b feature/short-description    # for new features
git checkout -b fix/short-description        # for bug fixes
git checkout -b docs/short-description       # for doc-only changes
```

Then push with upstream tracking on the first push:
```bash
git push -u origin feature/short-description
```

#### Naming convention

- `feature/<description>` — new features
- `fix/<description>` — bug fixes
- `docs/<description>` — doc-only changes
- `chore/<description>` — refactors, deps, build tooling
- `fix/workflow-{name}-{run-number}` — auto-created failure-handler branches

Use kebab-case, keep under ~40 chars, no emoji, no PR/issue numbers.

#### Hard rules (no exceptions without explicit user authorization)

- **Never commit directly to `main`** for any non-trivial change
- **Never `git push origin main`** without explicit user authorization
- **Never `git push --force` to `main`** under any circumstances
- **Never `git rebase` or `git reset --hard` on `main`** when others may pull
- All non-trivial changes go through a PR to `main`, even one-author repos

#### What "trivial" means (the only acceptable direct-to-main edits)

Only these may go straight to `main`:
- Single-line typo fixes in markdown
- README link corrections
- `.gitignore` additions for already-ignored locally-generated files
- The auto-status-tracker bumps that the `/commit` skill writes

Everything else — code, schema, workflows, agent docs, briefing deck
edits, dependency bumps — goes through a feature branch + PR.

#### How to recover when work has accidentally landed on `main`

If you've already committed to `main` locally (haven't pushed):
```bash
git branch feature/short-description    # save the work
git reset --hard origin/main             # rewind main locally
git checkout feature/short-description   # switch to the saved branch
git push -u origin feature/short-description
gh pr create --base main --head feature/short-description ...
```

Never `git push origin main` to "just publish what I already did" — that
defeats the entire purpose of the branch protection.

### 3. Planning & Approval Process
For major changes:
1. **PLAN FIRST**: Create a detailed plan using the TodoWrite tool
2. **GET APPROVAL**: Present the plan to the user and wait for explicit approval before executing
3. **DOCUMENT**: Explain what you're about to do and why
4. Major changes include:
   - Architectural modifications
   - Database schema changes
   - API interface changes
   - Dependency updates
   - Security-related modifications
   - Performance optimizations affecting core functionality

### 4. Testing Strategy Pattern
Follow this rigorous testing approach:

1. **Test What You Suggest**:
   - Before suggesting any code change, understand its impact
   - Write or run tests to validate your suggestions

2. **Provide Specific Feedback**:
   - Clearly state what's broken (with error messages)
   - Explain what was fixed (with specific code references)
   - Show test results proving the fix works

3. **Iterate Until Working**:
   - Run tests after each change
   - If tests fail, analyze the failure
   - Fix the issue and test again
   - Repeat until all tests pass
   - Document each iteration's findings

4. **Testing Checklist**:
   - [ ] Unit tests pass
   - [ ] Integration tests pass (if applicable)
   - [ ] No regressions in existing functionality
   - [ ] Edge cases handled
   - [ ] Error scenarios tested
   - [ ] Performance impact assessed

### 5. Code Quality Standards
- **Read before writing**: Thoroughly explore existing code before making changes
- **Extend, don't duplicate**: Add to existing modules rather than creating similar new ones
- **One place, one purpose**: Keep related functionality together in existing files
- Always run linting before committing
- Ensure TypeScript compilation succeeds (if applicable)
- Follow existing code style and patterns in the project
- Don't introduce new patterns without discussion
- Maintain or improve test coverage

### 6. Communication Protocol
- Be explicit about what you're doing at each step
- Report test results clearly with pass/fail status
- When encountering issues, provide:
  - The exact error message
  - The file and line number
  - Your analysis of the problem
  - Your proposed solution
- Ask for clarification when requirements are ambiguous

## Project-Specific Context

### Technology Stack
- Google Apps Script for spreadsheet automation
- JavaScript/TypeScript for core logic
- Yahoo Finance API integration
- Caching mechanisms for API optimization
- Continuation patterns for long-running operations

### Key Components
- Historical data backfilling system
- Yahoo API fetching with cache-first approach
- Execution continuation for Google Apps Script timeout handling
- Cloud Console logging integration
- Strat methodology (`lib/strat.py`) — candle classification (1/2U/2D/3),
  combo detection (Failed_2U/2D, RevStrat reversals, continuations),
  FTFC scoring across timeframes
- Gamma analytics (`lib/gamma.py`) — per-strike GEX, King/Gate/Spot/Flip
  taxonomy, gamma flip detection, regime classification. See
  [`docs/gamma_levels.md`](docs/gamma_levels.md) for the full reference.

### Architectural rules

- **One source of truth for math.** Per `docs/HARDCODED_VALUES_REMEDIATION.md`,
  the React app never duplicates financial math. Indicators, gamma,
  playbook conditions, trade analytics — all live in `lib/` (Python) and
  are exposed via FastAPI endpoints. The frontend consumes them.
- **`lib/` is the shared backend spine.** All three consumer surfaces
  (FastAPI router, AI agents, CLI scripts) import from the same `lib/`
  modules so behaviour can't drift.

### Database access

> **See also: [`docs/CLAUDE_CODE_ON_WEB.md`](docs/CLAUDE_CODE_ON_WEB.md)** — the
> full field guide for working from a Claude Code on the web sandbox: the
> SessionStart bootstrap script, PAT-via-Secret-Manager pattern, GH Actions
> gotchas, MCP caveats, and the rationale behind the patterns documented
> below.

Direct DB connections from Claude Code on the web sandbox are blocked: the
sandbox firewall only allows outbound TCP on port 443, and Cloud SQL needs
5432 (Postgres) or 3307 (Auth Proxy backend). Both time out. Adding the
sandbox IP to authorized networks does not help — the binding constraint is
the sandbox's outbound firewall, not the DB's inbound ACL.

To query Cloud SQL Postgres (`trading` database) from any session, dispatch
the `.github/workflows/db-query.yml` workflow. It runs the SQL inside a
GitHub Actions runner (which has unrestricted egress to Cloud SQL via the
project's existing `gcp/database.py` connector), captures structured results,
posts a phone-friendly summary as a comment on a tracking issue if specified,
and uploads the full results as a workflow artifact.

#### Invocation patterns

**Single read query** (default — transaction is rolled back, which is a no-op
for SELECT):
```bash
gh workflow run db-query.yml \
  -f sql='SELECT count(*) FROM trades WHERE date > current_date - 7' \
  -f issue_number=<TRACKING_ISSUE>
```

**Multi-statement in one dispatch** — this is the answer to "varying amounts
of queries." Batch into one dispatch instead of dispatching N times. Each
statement runs in its own transaction:
```bash
gh workflow run db-query.yml \
  -f sql='SELECT count(*) FROM trades; SELECT count(*) FROM signal_alerts; SELECT max(date) FROM market_data_daily' \
  -f issue_number=<TRACKING_ISSUE>
```

**File-based** (for SQL too large for a dispatch input or DDL with embedded
semicolons like `DO $$ ... $$` blocks or `CREATE FUNCTION ... LANGUAGE
plpgsql`):
```bash
# Commit the .sql file to gcp/queries/ first, then:
gh workflow run db-query.yml \
  -f sql_file=gcp/queries/check_freshness.sql \
  -f issue_number=<TRACKING_ISSUE>
```
The file content is sent as **one** statement. Multi-statement splitting
only happens for the inline `sql` input. For DO blocks or function
definitions, always use `sql_file`.

**Write query** (must explicitly opt in to commit):
```bash
gh workflow run db-query.yml \
  -f sql="UPDATE trades SET status='reviewed' WHERE id IN (1,2,3)" \
  -f commit=true \
  -f issue_number=<TRACKING_ISSUE>
```
Without `commit=true`, every transaction rolls back at the end. A write
without `commit=true` is a deliberate no-op — the summary will show
`↩️ rolled back` so the user knows. This is the load-bearing safety
guarantee: a typo'd UPDATE/DELETE without `commit=true` cannot persist.

#### Reading results

Each dispatch takes ~30–90 s end-to-end (queue + cold runner + connection +
query + summary). After dispatch:
```bash
sleep 5
RUN_ID=$(gh run list --workflow=db-query.yml --limit=1 --json databaseId -q '.[0].databaseId')
gh run watch $RUN_ID                                       # blocks until done
gh issue view <TRACKING_ISSUE> --comments | tail -120      # phone-friendly summary
# OR for full results:
gh run download $RUN_ID --name "query-results-$RUN_ID"
```

Artifact contents:
- `results.json` — structured per-statement results (columns, rows,
  row_count, truncated, duration_ms, mode, error, sqlstate,
  row_cap_strategy)
- `result_NNN.csv` — per-statement CSV (only for statements that returned
  rows)
- `summary.md` — full markdown summary, untruncated
- `summary_for_comment.md` — same content, hard-truncated to 60 KB for the
  issue comment

#### Inputs reference

| Input | Default | Notes |
|---|---|---|
| `sql` | `""` | Inline SQL; multi-statement separated by `;`. Exclusive with `sql_file`. |
| `sql_file` | `""` | Path to `.sql` file in repo. Sent as one statement. Exclusive with `sql`. |
| `commit` | `false` | `true` to persist writes; otherwise transaction rolls back. |
| `issue_number` | `""` | Issue # to post summary comment to. Empty → falls back to `vars.DB_QUERY_TRACKING_ISSUE`, then to artifact-only. |
| `statement_timeout_seconds` | `120` | Per-statement Postgres `statement_timeout`. |

If you create a single tracking issue once and set the repo variable
`DB_QUERY_TRACKING_ISSUE` to its number (`gh variable set
DB_QUERY_TRACKING_ISSUE -b <num>`), every dispatch posts there by default
without needing `issue_number=` each time.

#### Limits

- **Statement timeout**: 120 s default (override with
  `statement_timeout_seconds`).
- **Row cap**: 50,000 per statement in the artifact, top 50 in the issue
  comment. For single-SELECT statements the cap is enforced server-side via
  subquery wrap (`row_cap_strategy: server_limit`); for multi-statement,
  non-SELECT, or queries with `FOR UPDATE`/`FOR SHARE`/`SELECT INTO` it's
  enforced client-side via `fetchmany(50001)` (`row_cap_strategy:
  client_fetchmany`). The latter is slower for huge result sets but the
  timeout caps wall-time.
- **Issue comment**: 60 KB hard truncation (GitHub's limit is 65 KB);
  truncated comments link to the artifact.
- **Concurrency**: all dispatches serialize through one queue (group
  `db-query`). A read dispatched while a write is in flight waits ~30–60 s
  for the queue.

#### What not to do

- **Don't paste secrets, API keys, or passwords as SQL string literals** in
  `inputs.sql`. The `sql` input is recorded in plaintext in the workflow
  run history and is visible to anyone with **read** access to the repo.
- **Don't dispatch the workflow N times for N queries.** Batch into
  multi-statement SQL (`-f sql='SELECT 1; SELECT 2; ...'`) or commit a
  `.sql` file with the full batch and use `sql_file`. Each dispatch costs
  30–90 s.
- **Don't use this for production migrations.** For schema changes,
  `gcp/schema.sql` + `gcp/apply_schema.py` is the source of truth. This
  workflow is for ad-hoc inspection and one-off data fixes.

#### Why this exists

Phone-only sessions on Claude Code on the web cannot reach Cloud SQL on any
port (sandbox blocks all egress except 443). A GH-Actions-mediated query
workflow is the only path that works without a desktop fallback. The
runner reuses `gcp/database.py:get_engine()` and the existing
`CLOUD_SQL_CONNECTION_NAME` / `DB_USER` / `DB_PASS` / `DB_NAME` repo
secrets. Auth uses a dedicated SA key
(`CLAUDE_CODE_WEB_GCP_SA_KEY`, distinct from the data-pipeline workflows'
`GCP_SA_KEY`) so a key compromise here doesn't put scheduled fetchers at
risk simultaneously.

### GitHub API access from the sandbox

The sandbox cannot run `gh` (not installed). To dispatch workflows, read
runs, download artifacts, or post comments via the REST API, fetch the
GitHub PAT from GCP Secret Manager and use `curl` against `api.github.com`.

The PAT lives at `projects/adept-mountain-474619-d4/secrets/gh-stocks-repo-pat`.
The `claude-web@` SA already has `roles/editor` at the project level, which
includes `secretmanager.secretAccessor` on every secret in the project, so
no per-secret IAM binding is needed.

```bash
# Fetch once per session (avoid embedding in argv where it'd land in process listings)
GH_TOKEN=$(gcloud secrets versions access latest \
  --secret=gh-stocks-repo-pat \
  --project=adept-mountain-474619-d4)

# Dispatch the db-query workflow against any branch
curl -sS -X POST \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/TeneikaAskew/stocks/actions/workflows/db-query.yml/dispatches \
  -d '{"ref":"main","inputs":{"sql":"SELECT now()"}}'

# Poll most recent run
RUN_ID=$(curl -sS -H "Authorization: Bearer $GH_TOKEN" \
  "https://api.github.com/repos/TeneikaAskew/stocks/actions/workflows/db-query.yml/runs?per_page=1" \
  | python -c "import sys,json; print(json.load(sys.stdin)['workflow_runs'][0]['id'])")

# Download the artifact (returns a ZIP)
ARTIFACT_ID=$(curl -sS -H "Authorization: Bearer $GH_TOKEN" \
  "https://api.github.com/repos/TeneikaAskew/stocks/actions/runs/$RUN_ID/artifacts" \
  | python -c "import sys,json; print(json.load(sys.stdin)['artifacts'][0]['id'])")
curl -sS -L -H "Authorization: Bearer $GH_TOKEN" \
  -o /tmp/results.zip \
  "https://api.github.com/repos/TeneikaAskew/stocks/actions/artifacts/$ARTIFACT_ID/zip"
```

**Important caveats:**
- **Workflow registration**: GitHub registers `workflow_dispatch` workflows
  only after their file lands on the **default branch** (`main`). Until
  then both `gh workflow run` and the REST API return 404. To smoke-test a
  new workflow, the file must merge to `main` first.
- **Don't pass the PAT in argv** (`-H "Authorization: Bearer ghp_xxx"`
  inline). Other processes can read `/proc/<pid>/cmdline`. Always assign
  to a shell variable first and reference via `$GH_TOKEN`.
- **Don't echo or log the PAT.** It will land in shell history and Bash
  tool transcripts visible in conversation summaries.
- **Rotation**: rotate by writing a new version to the secret; consumers
  fetch `latest` and pick up the new value transparently.
  ```bash
  read -s NEW && echo -n "$NEW" | gcloud secrets versions add gh-stocks-repo-pat \
    --data-file=- --project=adept-mountain-474619-d4 && unset NEW
  ```

### Testing Commands
```bash
# Add project-specific test commands here
# npm test
# npm run lint
# npm run typecheck
```

### GitHub Actions Workflows

This project uses GitHub Actions for automated data fetching, analysis, and system maintenance. All workflows follow consistent patterns and include automated failure handling.

#### Workflow Development Best Practices

1. **Always Include Failure Handling**
   - Every workflow MUST include the `handle-failure` job
   - This ensures issues and PRs are automatically created on failure
   - See the "Automated Workflow Failure Handling" section below for details

2. **Use Consistent Permissions**
   - Main job: `contents: write` (for git operations), `issues: write` (for reporting)
   - Failure handler: Add `pull-requests: write` and `actions: read`

3. **Implement Continue-on-Error Strategically**
   - Use `continue-on-error: true` for non-critical steps
   - Track failures with step outputs and check them in a dedicated step
   - This allows workflows to complete partially while still reporting failures

4. **Use Proper Job Dependencies**
   - Use `needs:` to chain jobs that depend on each other
   - Use `if: always()` for jobs that should run regardless of previous job status
   - Use `if: failure()` for failure handling jobs

5. **Test Workflows Locally When Possible**
   - Use `act` tool to test GitHub Actions locally: https://github.com/nektos/act
   - Test scripts independently before integrating into workflows
   - Use `workflow_dispatch` for manual testing in GitHub

6. **Label Workflows Consistently**
   - Use descriptive, unique labels for each workflow type
   - Format: `workflow-failure,<specific-workflow-type>,automated`
   - Examples: `workflow-failure,etf-options,automated` or `workflow-failure,market-data,automated`

### GitHub Issue Management
Use GitHub CLI (`gh`) to manage repository issues:

#### Setup (One-time)
If `gh` is not installed:
```bash
# Windows (PowerShell)
winget install --id GitHub.cli

# Authenticate (required on first use)
gh auth login
```

#### Common Commands
```bash
# List all open issues
"C:\Program Files\GitHub CLI\gh.exe" issue list

# List issues with specific state
gh issue list --state open
gh issue list --state closed
gh issue list --state all

# View a specific issue
gh issue view <issue-number>

# Create a new issue
gh issue create --title "Issue title" --body "Issue description"

# Close an issue
gh issue close <issue-number>

# Reopen an issue
gh issue reopen <issue-number>

# Add labels to an issue
gh issue edit <issue-number> --add-label "bug,automated"

# Search issues
gh issue list --search "error"
gh issue list --label "bug"
```

**Note for Windows**: If PATH is not updated after installation, use the full path:
```powershell
& "C:\Program Files\GitHub CLI\gh.exe" issue list
```

### Automated Workflow Failure Handling

This project uses an automated system to handle workflow failures by creating/updating GitHub issues and pull requests.

#### How It Works

When any GitHub Actions workflow fails:
1. **Issue Creation**: An issue is automatically created (or updated if one already exists) with:
   - Workflow run details (run number, URL, timestamp)
   - Failed step information
   - Last 50 lines of error logs from failed steps
   - Link to the workflow logs for full details

2. **Pull Request Creation**: A draft PR is automatically created with:
   - Branch named `fix/workflow-{workflow-name}-{run-number}`
   - Link to the related issue
   - Error summary and diagnostic information
   - Checklist for fixing the issue

3. **Duplicate Prevention**: If an issue already exists for a workflow failure:
   - No new issue is created
   - A comment is added to the existing issue with the new failure details
   - This prevents issue clutter and keeps all related failures in one place

#### Architecture

The system consists of two main components:

1. **Reusable Workflow**: [`.github/workflows/handle-workflow-failure.yml`](.github/workflows/handle-workflow-failure.yml)
   - Called by other workflows when they fail
   - Receives workflow context and failure details
   - Orchestrates the failure handling process

2. **Python Script**: [`scripts/handle_workflow_failure.py`](scripts/handle_workflow_failure.py)
   - Fetches workflow run details via GitHub API
   - Extracts error logs from failed jobs
   - Creates/updates issues and PRs
   - Handles duplicate detection

#### Workflows Using This System

All major workflows in this project use automated failure handling:
- `fetch-market-data.yml` - Daily market data updates
- `earnings-options-analytics.yml` - Analytics pipeline
- `update_economic_events_calendar.yml` - Economic calendar updates
- `fetch-economic-events-calendar.yml` - Economic events calendar fetching
- `analyze-market-data.yml` - Market data analysis
- `download-google-sheets.yml` - Google Sheets data downloads

**Important**: When creating new workflows, always add the failure handler job to ensure consistent error tracking and automated issue creation.

#### Working with Auto-Created Issues and PRs

**When a workflow fails:**

1. **Check the Issue**: Navigate to the auto-created issue to see:
   - What failed and when
   - Error logs and diagnostics
   - Link to the related PR

2. **Review the Logs**: Click through to the workflow run to see complete logs:
   ```bash
   # Or use gh CLI to view the issue
   gh issue view <issue-number>
   ```

3. **Work on the Fix**: The auto-created PR provides a branch to work on:
   ```bash
   # Checkout the auto-created branch
   git fetch origin
   git checkout fix/workflow-{name}-{run-number}

   # Make your fixes
   # Test locally

   # Push your fixes
   git add .
   git commit -m "fix: resolve workflow failure"
   git push origin fix/workflow-{name}-{run-number}
   ```

4. **Mark as Ready**: Once fixed:
   - Convert the draft PR to ready for review
   - The PR will automatically close the issue when merged

**Managing Multiple Failures:**

If a workflow fails multiple times:
- All failures are tracked in a single issue (via comments)
- Each comment includes the specific run details
- The most recent PR link is shown in the issue
- Close old PRs if the fix is consolidated into a newer one

**Using gh CLI with Auto-Created Items:**

```bash
# List workflow failure issues
gh issue list --label "workflow-failure"

# View specific workflow failures
gh issue list --label "workflow-failure,etf-options"
gh issue list --label "workflow-failure,market-data"

# List auto-created PRs
gh pr list --label "automated"

# View a specific failure PR
gh pr view <pr-number>

# Close resolved issues
gh issue close <issue-number> --comment "Fixed in PR #<pr-number>"
```

#### Adding Failure Handling to New Workflows

When creating or updating workflows, always add the failure handler job. Here's the standard pattern:

```yaml
jobs:
  main-job:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      issues: write
    steps:
      # Your workflow steps here
      - name: Your step
        run: echo "Do work"

  # Always add this failure handler job
  handle-failure:
    needs: main-job
    if: failure()
    uses: ./.github/workflows/handle-workflow-failure.yml
    permissions:
      contents: write
      issues: write
      pull-requests: write
      actions: read  # Required to read workflow run details and logs
    with:
      workflow_name: "Human-readable name"
      failure_title: "❌ Descriptive failure title"
      issue_labels: "workflow-failure,specific-label,automated"
      workflow_file: "workflow-filename.yml"
      run_id: ${{ github.run_id }}
      run_number: ${{ github.run_number }}
      run_url: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
      event_name: ${{ github.event_name }}
      branch: ${{ github.ref }}
      commit_sha: ${{ github.sha }}
      create_pr: true  # Set to false to skip PR creation
```

**Key Points:**
- The `handle-failure` job must have `needs: main-job` (or whatever your main job is called)
- Use `if: failure()` to trigger only on failure
- Always include `actions: read` permission for log access
- Use descriptive, unique labels for each workflow type
- Set `create_pr: false` if you only want issue creation without a PR

#### Troubleshooting

**If failure handling itself fails:**
- Check the "handle-failure" job in the workflow run
- Verify `GITHUB_TOKEN` permissions are set correctly
- Ensure `scripts/handle_workflow_failure.py` is accessible
- Check that `requests` library is installed (in `requirements.txt`)

**If logs aren't being captured:**
- The script fetches logs via GitHub API
- Logs are limited to last 50 lines of errors
- Full logs are always available via the workflow run link

**If duplicate issues are created:**
- The system checks for open issues with matching labels
- Ensure label names are consistent in workflow configurations
- Check that the issue search is working correctly

## Example Workflow

1. User requests a feature
2. **READ AND SEARCH**: Explore all related existing files first
3. Identify if changes can be made to existing files
4. Use TodoWrite to create a detailed plan
5. Present plan for approval (mentioning which existing files will be modified)
6. Upon approval, create feature branch
7. Implement changes incrementally (preferring edits to existing files)
8. Test each change thoroughly
9. Report test results
10. Fix any issues found
11. Repeat testing until all passes
12. Commit with proper message (no Claude branding)
13. Create PR if requested

## Remember
- Quality over speed
- Test everything you change
- Communicate clearly and frequently
- Follow the existing patterns in the codebase
- When in doubt, ask for clarification