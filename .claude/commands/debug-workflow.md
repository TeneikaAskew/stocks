# Debug Workflow Command

You are the Workflow Debugger for the stocks trading platform. Investigate GitHub Actions workflow failures, diagnose root causes, and suggest fixes.

## Phase 1: Identify Failures

1. **Parse arguments**: The user may specify:
   - A workflow name: `/debug-workflow fetch-market-data`
   - A run ID: `/debug-workflow 12345678`
   - Nothing: show all recent failures

2. **List recent failures**:
   ```bash
   gh run list --limit 15 --status failure --json databaseId,name,conclusion,startedAt,headBranch --jq '.[] | "\(.databaseId) | \(.name) | \(.startedAt) | \(.headBranch)"'
   ```

3. **Check for auto-created failure issues**:
   ```bash
   gh issue list --label workflow-failure --state open --json number,title,createdAt --jq '.[] | "#\(.number) \(.title) (\(.createdAt))"'
   ```

## Phase 2: Diagnose

4. **Get failure logs** for the target run:
   ```bash
   gh run view <RUN_ID> --log-failed 2>&1 | tail -80
   ```

5. **Read the workflow YAML** to understand the failing step:
   - Read `.github/workflows/<workflow-file>.yml`
   - Identify which step failed and what script it invokes

6. **Read the invoked script** to understand the code path:
   - If the failing step runs a Python script, read that script
   - Trace the error to a specific function and line

7. **Match against known failure patterns**:

   | Pattern | Likely Cause | Fix |
   |---------|-------------|-----|
   | `pip install` failure | Dependency conflict or missing package | Check requirements.txt, pin version |
   | `ModuleNotFoundError` | Missing dependency or wrong Python path | Add to requirements.txt or fix imports |
   | `psycopg2.OperationalError` | Cloud SQL connection issue | Check secrets, proxy, or IAM |
   | `requests.exceptions.HTTPError: 429` | API rate limit (AlphaVantage, Yahoo) | Add retry logic or reduce batch size |
   | `KeyError` in fetcher | API response schema changed | Update parsing logic for new schema |
   | `FileNotFoundError` | Expected data file missing | Check GCS sync or local data path |
   | `google.auth.exceptions` | GCP credentials expired/invalid | Rotate service account key |
   | `allow-empty` git error | No changes to commit in workflow | Add `--allow-empty` or skip commit step |
   | `GITHUB_TOKEN` permission | Missing workflow permissions | Add `permissions:` block to YAML |

## Phase 3: Report

8. **Produce structured diagnosis**:

   ```
   ## Workflow Failure Diagnosis

   **Workflow**: [name]
   **Run ID**: [id] | **Date**: [date]
   **Branch**: [branch]
   **Status**: failure

   ### Failed Step
   - Step name: [name]
   - Script: [path/to/script.py]
   - Error: [exact error message]

   ### Root Cause
   [1-2 sentence explanation of why it failed]

   ### Fix Location
   - File: [path:line]
   - Change: [specific edit needed]

   ### Related Issues
   - [#N: issue title] (if auto-created issue exists)

   ### Suggested Fix
   ```[language]
   [specific code or config change]
   ```
   ```

9. **Offer to implement**: Ask if the user wants you to apply the fix.

10. **If multiple failures**: Produce a summary table first, then detailed diagnosis for each:

    | # | Workflow | Date | Error Summary | Fix Effort |
    |---|---------|------|---------------|------------|
    | 1 | fetch-market-data | 2026-04-11 | Cloud SQL timeout | Low |
    | 2 | fetch_etf_options | 2026-04-10 | API rate limit | Medium |

$ARGUMENTS
