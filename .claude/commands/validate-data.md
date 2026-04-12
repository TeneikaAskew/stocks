# Validate Data Command

You are the Data Validation agent. Run a comprehensive health check on the trading data pipeline and report freshness, completeness, and pipeline status.

## Phase 1: Run Validation Script

1. Source environment and run the validator:
   ```bash
   set -a && source .env && set +a && python scripts/validate_market_data.py 2>&1
   ```
   Capture the output. If the script exits with code 1, there are data issues.

2. If the validation script produces `data/market_data_validation.json`, read it for structured results.

## Phase 2: Check Workflow Health

3. Check recent GitHub Actions runs for data fetcher workflows:
   ```bash
   gh run list --limit 20 --json name,status,conclusion,startedAt --jq '.[] | select(.name | test("fetch|market|options|earnings|economic")) | "\(.name) | \(.conclusion) | \(.startedAt)"'
   ```

4. For any failed workflows, get the error summary:
   ```bash
   gh run view <RUN_ID> --log-failed 2>&1 | tail -30
   ```

## Phase 3: Check Data Freshness (if Cloud SQL accessible)

5. If `.env` and `.gcp-key.json` exist, spot-check data freshness:
   ```bash
   python -c "
   from gcp.database import get_connection
   import datetime
   conn = get_connection()
   cur = conn.cursor()
   tables = [
       ('market_data_daily', 'date'),
       ('etf_options_snapshots', 'snapshot_ts'),
       ('earnings_options_snapshots', 'snapshot_ts'),
       ('economic_events', 'date'),
   ]
   for table, col in tables:
       try:
           cur.execute(f'SELECT MAX({col}) FROM {table}')
           latest = cur.fetchone()[0]
           print(f'{table}: latest={latest}')
       except Exception as e:
           print(f'{table}: ERROR {e}')
   conn.close()
   " 2>&1
   ```

## Phase 4: Report

6. Produce a structured health report:

   ```
   ## Data Pipeline Health Report — YYYY-MM-DD

   ### Data Freshness

   | Table | Latest Record | Expected | Status |
   |-------|--------------|----------|--------|
   | market_data_daily | YYYY-MM-DD | YYYY-MM-DD | FRESH/STALE |
   | market_data_intraday | YYYY-MM-DD HH:MM | today | FRESH/STALE |
   | etf_options_snapshots | YYYY-MM-DD HH:MM | today (market hours) | FRESH/STALE |
   | earnings_options_snapshots | YYYY-MM-DD | YYYY-MM-DD | FRESH/STALE |
   | economic_events | YYYY-MM-DD | this week | FRESH/STALE |

   ### Workflow Status

   | Workflow | Last Run | Status | Affected Table |
   |----------|----------|--------|----------------|
   | fetch-market-data | date | success/failure | market_data_* |
   | fetch_etf_options | date | success/failure | etf_options_snapshots |
   | fetch-earnings-options | date | success/failure | earnings_options_snapshots |

   ### Issues Found
   - [issue description — responsible fetcher — suggested action]

   ### Recommended Actions
   1. [action with specific command to run]
   ```

7. If all data is fresh and workflows are healthy, report:
   ```
   All data pipelines healthy. No action needed.
   ```

$ARGUMENTS
