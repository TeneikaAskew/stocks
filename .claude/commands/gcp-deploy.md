# GCP Deploy Command

This command runs the full GCP deployment pipeline:
0. **Pre-deploy gate** — invoke the `pre-deploy-check` agent and refuse to proceed on any CRITICAL blocker
1. Run the test suite and capture results
2. Stage and commit all GCP-related changes with a proper commit message
3. Update the implementation status tracker and guide
4. Submit the Docker image to Cloud Build
5. **Post-deploy verification** — confirm the new Cloud Run revision is actually serving, surface any errors from the first 2 minutes of runtime, and print the rollback command on failure

## Steps to Execute

### Step 0 — Pre-Deploy Gate

Invoke the `pre-deploy-check` agent via the Agent tool:

```
Agent(subagent_type="pre-deploy-check", prompt="Run pre-deploy-check against the current repo state. Deploy target: trading-pipeline on Cloud Run us-east1.")
```

Parse the agent output for the final `PRE_DEPLOY_EXIT=<N>` line:

- **Exit 0 (clean)** — proceed to Step 1.
- **Exit 1 (warnings)** — print the warnings, ask the user for explicit confirmation ("warnings found — continue? [y/N]"), proceed only on `y`.
- **Exit 2 (blockers)** — STOP. Print the blocker list. Do NOT proceed unless the user explicitly passes `--force` to `/gcp-deploy` (in which case log `[pre-deploy-check overridden: <reason>]` into the commit body).

The most common blocker this gate catches: **stale `platform/dist/`** (the exact regression from 2026-04-14). In that case, the gate tells the user to run `cd platform && npm run build` — do that, then re-run the gate.

### Step 1 — Run Tests

Run the full test suite and capture the output:

```bash
make test 2>&1 | tee /tmp/test_output.txt; echo "EXIT:$?"
```

Always proceed to commit regardless of test outcome. However:

**If all tests pass**: note it in the summary and continue normally.

**If any tests fail**:
- Extract the list of failed test names and the files they live in from the output
- Identify the root cause of each failure (read the relevant source files as needed)
- Produce a numbered **Fix Plan** section in the summary listing:
  - The failing test(s) with file path and line number
  - The specific error message
  - A concrete action to resolve it (e.g., "update column name in lib/indicators.py:42")
- Continue with the commit — include `[test failures]` at the end of the commit message body so failures are visible in git log

### Step 2 — Inspect Changes

Check what has changed since the last commit:

```bash
git status
git diff --stat
```

Identify which files are GCP-related (anything in `gcp/`, `docs/GCP_*.md`, `lib/data_loader.py` GCP changes, `requirements.txt` GCP additions, `gcp/Dockerfile`, `.claude/commands/gcp-deploy.md`).

### Step 3 — Update Status Tracker

Read `docs/GCP_IMPLEMENTATION_STATUS.md` and update it to reflect the current state:
- Mark any newly completed items as `[x]`
- Update the "Last Updated" date at the top to today's date
- Update the Test Results table with the latest test run results (pass count, fail count, date)
- If there were test failures, add a "Known Failures" subsection under Test Results listing each failing test and its Fix Plan item

### Step 4 — Update Guide Last-Updated Date

Update the "Last Updated" line in `docs/GCP_IMPLEMENTATION_GUIDE.md` to today's date.

### Step 5 — Stage and Commit

Stage GCP-related files and create a commit. Use conventional commit format. Do NOT include Claude branding or robot emoji.

Example commit message format:
```
feat(gcp): <short description of what changed>

<optional body explaining why if needed>
```

Stage files selectively — do not use `git add -A`. Only add files that are actually part of the GCP implementation work.

### Step 5.5 — Pre-Deploy Validation

Before submitting the build, run these checks:

1. **Data validation** (if any fetcher or data_loader files changed):
   ```bash
   set -a && source .env && set +a && python scripts/validate_market_data.py 2>&1
   ```
   If critical data is missing or stale, warn before proceeding. Do NOT block the deploy for stale data caused by market closures.

2. **Platform build** (if any `platform/` files changed):
   ```bash
   cd platform && npm run build 2>&1; echo "EXIT:$?"
   ```
   If the frontend build fails, STOP and report the error. Do NOT deploy a broken frontend.

### Step 6 — Submit Build to Cloud Build

After a successful commit and pre-deploy validation, run the deploy build command:

```bash
./gcp/deploy.sh build
```

This submits the Docker image to Cloud Build using the project `adept-mountain-474619-d4`. Report the build URL and status when complete.

If the build fails, report the Cloud Build log URL and the error output. Do NOT force-push or attempt destructive git operations.

### Step 7 — Post-Deploy Verification

After Cloud Build completes successfully and Cloud Run has rolled out the new revision, verify the deployment actually works:

1. **Wait for rollout** — poll until the new revision is serving:
   ```bash
   gcloud run services describe trading-pipeline \
     --region=us-east1 --project=adept-mountain-474619-d4 \
     --format='value(status.latestReadyRevisionName,status.traffic[0].revisionName)'
   ```
   Both values should match and point to the new revision.

2. **Health check** — hit `/api/health`:
   ```bash
   SERVICE_URL=$(gcloud run services describe trading-pipeline \
     --region=us-east1 --project=adept-mountain-474619-d4 \
     --format='value(status.url)')
   curl -sS -o /tmp/health.json -w "HTTP:%{http_code}\n" "$SERVICE_URL/api/health"
   cat /tmp/health.json
   ```
   Expect HTTP 200. If non-200, do NOT mark the deploy successful.

3. **Verify new bundle is serving** — hit `/` and confirm the HTML references the new revision's build hash:
   ```bash
   curl -sS "$SERVICE_URL/" | grep -oE '<script[^>]*src="/assets/index-[^"]+\.js"' | head -1
   ```
   Compare the bundle filename against the one in the newly committed `platform/dist/index.html`. A mismatch means Cloud Run is still serving the old revision — wait 30s and retry, then bail.

4. **Check for runtime errors in the first 2 minutes**:
   ```bash
   gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=trading-pipeline AND severity>=ERROR' \
     --limit=20 --freshness=2m \
     --project=adept-mountain-474619-d4 \
     --format='value(textPayload,jsonPayload.message)'
   ```
   If any ERROR-severity logs appear, surface them loudly in the summary and consider rollback.

5. **On any failure in steps 1-4**, print the rollback command below AND do NOT mark the deploy as successful. Leave it to the user to decide whether to roll back.

### Rollback Guidance

If the new deployment causes issues:
1. List recent revisions: `gcloud run revisions list --service=trading-pipeline --project=adept-mountain-474619-d4 --region=us-east1`
2. Route traffic to previous revision: `gcloud run services update-traffic trading-pipeline --to-revisions=<previous-revision>=100 --project=adept-mountain-474619-d4 --region=us-east1`
3. Investigate logs: `gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=trading-pipeline" --limit=50 --project=adept-mountain-474619-d4`

## Summary Report

After completing all steps, provide a brief summary:
- Test results (N passed, N failed)
- Files committed and commit SHA
- Build status (success/failure + URL)
- Any items updated in the status tracker

If there were test failures, include a **Fix Plan** section:

```
## Fix Plan

1. [test_name] in tests/test_foo.py:42
   Error: <exact error message>
   Fix: <specific change needed, with file:line reference>

2. [test_name] in tests/test_bar.py:17
   Error: <exact error message>
   Fix: <specific change needed, with file:line reference>
```
