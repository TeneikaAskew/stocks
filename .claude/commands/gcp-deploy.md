# GCP Deploy Command

This command runs the full GCP deployment pipeline:
1. Run the test suite and capture results
2. Stage and commit all GCP-related changes with a proper commit message
3. Update the implementation status tracker and guide
4. Submit the Docker image to Cloud Build

## Steps to Execute

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
