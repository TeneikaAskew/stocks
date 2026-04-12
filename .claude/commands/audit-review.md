# Audit & Review Command

You are the Audit & Review agent for the stocks trading platform. Perform a comprehensive production-readiness audit of the codebase, generate a scored report, and flag actionable findings.

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

After collecting all findings, produce:

### Scorecard (1-10 scale)

| Component | Score | Issues Found |
|-----------|-------|--------------|
| Core Libraries (`lib/`) | X/10 | ... |
| GCP Infrastructure (`gcp/`) | X/10 | ... |
| Data Fetchers (`gcp/fetchers/`) | X/10 | ... |
| Platform API (`platform/api/`) | X/10 | ... |
| Platform UI (`platform/src/`) | X/10 | ... |
| GitHub Actions Workflows | X/10 | ... |
| Test Coverage | X/10 | ... |
| Error Handling | X/10 | ... |
| Security & Secrets | X/10 | ... |
| Data Freshness | X/10 | ... |
| Code Style & Consistency | X/10 | ... |
| Documentation | X/10 | ... |
| **OVERALL** | **X/10** | ... |

Scoring rubric:
- 9-10: Production-grade, no significant issues
- 7-8: Good with minor issues
- 5-6: Functional but needs hardening
- 3-4: Significant gaps
- 1-2: Critical issues, not production-ready

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
