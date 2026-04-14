# Audit & Review Command

You are the Audit & Review agent for the stocks trading platform. Perform a comprehensive production-readiness audit of the codebase, generate a **100-point scored report** (7 categories), and flag actionable findings.

## Phase 0: Delegate to Specialized Agents

Before running the in-line checks, invoke these agents in parallel and collect their findings. Each owns a specific category of the final scorecard:

1. **`security-scan`** → owns the Security category (15 pts)
2. **`test-coverage-analyzer`** → owns the Testing category (20 pts)
3. **`pre-deploy-check`** → owns the Deploy Readiness category (10 pts)
4. **`data-pipeline-validator`** → owns the Data Integrity category (15 pts)
5. **`infra-drift-detector`** → contributes to the Monitoring category (15 pts)

For each agent, parse the `_EXIT=<N>` line it prints and the finding counts in its output. Collect them into a working scratchpad; you'll assemble the scorecard in Phase 4.

If Cloud SQL proxy or `gcloud` isn't authenticated locally, some agents will emit `[SKIP]` lines — treat those as "could not evaluate, score 50% of max for that sub-check" rather than a hard failure.

## Phase 1: Run Automated Tests

1. Run the full test suite and capture results:
   ```bash
   make test 2>&1 | tee /tmp/test_output.txt; echo "EXIT:$?"
   ```
   Note pass/fail/skip counts. Failures are HIGH severity findings.

2. Run script CLI tests:
   ```bash
   make test-scripts 2>&1 | tail -20
   ```

3. Run market data validation:
   ```bash
   set -a && source .env && set +a && python scripts/validate_market_data.py 2>&1
   ```
   Any validation errors = HIGH severity finding.

## Phase 2: Code Quality Checks

Run these grep-based scans and record counts:

4. **Silent exception handling** (HIGH risk):
   ```bash
   grep -rn "except Exception.*pass\|except:$\|except Exception:$" lib/ gcp/ platform/api/ scripts/ --include="*.py" 2>&1
   ```

5. **Hardcoded secrets or credentials** (CRITICAL):
   ```bash
   grep -rn "API_KEY.*=.*['\"].\+['\"]\|password.*=.*['\"].\+['\"]" lib/ gcp/ platform/ scripts/ --include="*.py" 2>&1 | grep -v "\.env\|config\|#\|test"
   ```

6. **SQL injection risk — string formatting in queries** (HIGH):
   ```bash
   grep -rn "f\".*SELECT\|f\".*INSERT\|f\".*UPDATE\|f\".*DELETE\|%s.*execute\|\.format.*execute" lib/ gcp/ platform/api/ --include="*.py" 2>&1
   ```

7. **Deprecated or wrong API usage** (MEDIUM):
   ```bash
   grep -rn "yfinance\|yahoo_fin\|from yahoo" lib/ gcp/ scripts/ --include="*.py" 2>&1
   ```

8. **Missing error handling on external calls** (MEDIUM):
   ```bash
   grep -rn "requests\.get\|requests\.post\|urlopen" lib/ gcp/ scripts/ --include="*.py" -l 2>&1
   ```
   For each file, check if it has try/except around the call.

9. **TODO/FIXME/HACK comments in production code** (LOW):
   ```bash
   grep -rn "TODO\|FIXME\|HACK\|XXX" lib/ gcp/ platform/ --include="*.py" --include="*.ts" --include="*.tsx" 2>&1 | head -30
   ```

10. **TypeScript `any` usage** (MEDIUM):
    ```bash
    grep -rn ": any\|as any" platform/src/ --include="*.ts" --include="*.tsx" 2>&1 | wc -l
    ```

11. **Console.log left in production code** (LOW):
    ```bash
    grep -rn "console\.log" platform/src/ --include="*.ts" --include="*.tsx" 2>&1 | grep -v "test\|spec\|__test" | head -20
    ```

## Phase 3: Architecture & Data Checks

12. **Check Cloud SQL schema vs code alignment**:
    - Read `gcp/schema.sql`
    - Grep for table names in `lib/data_loader.py` and `platform/api/routers/*.py`
    - Flag any table referenced in code that is missing from schema.sql

13. **Check GitHub Actions workflow health**:
    ```bash
    gh run list --limit 15 --json name,status,conclusion,startedAt --jq '.[] | "\(.name) | \(.conclusion) | \(.startedAt)"'
    ```
    Any recent failures = note which data pipeline is affected.

14. **Check for uncommitted changes**:
    ```bash
    git status --short
    git stash list
    ```

15. **Review dependency security**:
    ```bash
    pip audit 2>&1 | head -30 || echo "pip-audit not installed"
    ```

16. **Platform build check**:
    ```bash
    cd platform && npx tsc -b --noEmit 2>&1 | tail -20; echo "EXIT:$?"
    ```

## Phase 4: Generate Scorecard & Report

After collecting all findings from Phase 0 (delegated agents) and Phases 1-3 (in-line checks), produce a **100-point scorecard** across 7 categories:

### Category Scorecard (100 points total)

| Category | Points | Source | Score |
|---|---|---|---|
| **Security** | 15 | `security-scan` agent | X/15 |
| **Performance** | 15 | N+1 Cloud SQL patterns, pandas memory in fetchers, slow routers | X/15 |
| **Monitoring** | 15 | `gcloud logging` coverage, `freshness-watchdog.yml` present, Cloud Run alerts, `infra-drift-detector` findings | X/15 |
| **Data Integrity** | 15 | `data-pipeline-validator` agent | X/15 |
| **Documentation** | 10 | `CLAUDE.md` present and current, `docs/` comprehensive, `CHANGELOG_*.md` freshness (last entry <7 days old) | X/10 |
| **Testing** | 20 | `test-coverage-analyzer` agent | X/20 |
| **Deploy Readiness** | 10 | `pre-deploy-check` agent | X/10 |
| **OVERALL** | **100** | sum of above | **X/100** |

### Scoring rubric

- **90-100**: Production-grade, safe to deploy continuously
- **80-89**: Good with minor issues, address before next major release
- **70-79**: Functional but needs hardening — top 3 fixes should ship soon
- **60-69**: Significant gaps — pause new feature work until hardened
- **<60**: Critical issues — do not deploy until resolved

### How to calculate each category

Security (15 pts):
- 15 if `security-scan` exits 0
- 10 if exits 1 (medium/low findings only)
- 5 if exits 2 and has ≤2 critical findings
- 0 if exits 2 with >2 critical findings

Testing (20 pts):
- Use `test-coverage-analyzer` score directly, mapped: 100→20, 80→16, 60→12, 40→8, <40→4
- Subtract 4 pts for any `make test` failure

Deploy Readiness (10 pts):
- 10 if `pre-deploy-check` exits 0
- 6 if exits 1
- 0 if exits 2

Data Integrity (15 pts):
- 15 if `data-pipeline-validator` reports no issues
- 10 if minor issues (stale daily data on a market closure day = OK)
- 5 if actual fetcher failures or schema drift
- 0 if core tables missing data for >48 hours

Monitoring (15 pts):
- Start at 15. Subtract:
  - 3 if `freshness-watchdog.yml` missing or disabled
  - 3 if no Cloud Run error alerts configured
  - 3 if `infra-drift-detector` reports drift
  - 3 if `gcloud logging read` shows no entries in last 24h (nothing being logged)

Performance (15 pts):
- Start at 15. Subtract:
  - 3 per N+1 query pattern found in routers
  - 3 per pandas `.apply` on >10k rows without vectorization
  - 3 per unbounded `SELECT` in a fetcher (no `LIMIT`, no `WHERE date`)

Documentation (10 pts):
- 4 for `CLAUDE.md` current and accurate (touched within last 30 days or known-stable)
- 2 for `docs/GCP_IMPLEMENTATION_GUIDE.md` current
- 2 for most recent `CHANGELOG_*.md` updated within last 7 days
- 2 for `docs/incidents/` having postmortems for recent incidents

### Top 3 Action Items

After the scorecard, list the 3 highest-impact fixes (weighted: criticality × ease-of-fix):

1. **[category]** description — File:line — specific fix — estimated effort
2. ...
3. ...

### Exit signal

If overall score <70 OR any CRITICAL finding exists, print `AUDIT_BLOCK=true` at the end. This tells `/gcp-deploy` callers that a deploy should not proceed without remediation.

### Legacy component scorecard (kept for reference)

The old per-directory scorecard can still be useful as a supplementary view. Include it under a `## Legacy Component Scorecard` heading after the 100-point scorecard:

| Component | Score | Issues Found |
|-----------|-------|--------------|
| Core Libraries (`lib/`) | X/10 | ... |
| GCP Infrastructure (`gcp/`) | X/10 | ... |
| Data Fetchers (`gcp/fetchers/`) | X/10 | ... |
| Platform API (`platform/api/`) | X/10 | ... |
| Platform UI (`platform/src/`) | X/10 | ... |
| GitHub Actions Workflows | X/10 | ... |

### Findings by Severity

**CRITICAL** (must fix immediately):
- What | File:Line | Risk | Recommended Fix

**HIGH** (significant risk):
- What | File:Line | Risk | Recommended Fix

**MEDIUM** (should fix):
- What | File:Line | Risk | Recommended Fix

**LOW / INFO** (monitor):
- Brief list

### Test Results Summary

| Suite | Total | Passed | Failed | Skipped |
|-------|-------|--------|--------|---------|
| Unit/Integration (`make test`) | - | - | - | - |
| Script CLI (`make test-scripts`) | - | - | - | - |
| **TOTAL** | - | - | - | - |

### Workflow Health

| Workflow | Last Status | Last Run | Affected Data |
|----------|-------------|----------|---------------|
| fetch-market-data | success/failure | date | market_data_daily/intraday |
| fetch_etf_options | success/failure | date | etf_options_snapshots |
| ... | ... | ... | ... |

### Delta from Previous Audit

If a previous audit score exists in `docs/GCP_IMPLEMENTATION_STATUS.md`, note what improved, regressed, or stayed the same.

### Action Items

Number and prioritize all CRITICAL and HIGH findings:
1. Item description — File:line — Specific fix

## Phase 5: Save Results

After reporting:
- Update `docs/GCP_IMPLEMENTATION_STATUS.md` with:
  - Today's audit score in the Test Results section
  - Any newly discovered issues in the Notes section
- Offer to implement each CRITICAL and HIGH fix

$ARGUMENTS
