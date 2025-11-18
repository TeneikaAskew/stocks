# Alpha Vantage GitHub Actions Workflows

This document describes the automated GitHub Actions workflows for fetching Alpha Vantage data.

## Overview

Two workflows automatically fetch data from Alpha Vantage API:

1. **Daily Options Data** - Fetches options chains for SPY, IWM, QQQ
2. **Monthly Intraday Data** - Fetches 1-minute intraday OHLCV data for SPY, IWM, QQQ

## Workflows

### 1. Daily Options Data (`fetch-alphavantage-options-daily.yml`)

**Schedule**: Every day at 9:00 PM EDT (1:00 AM UTC)

**What it fetches**:
- SPY options chain (previous day to today)
- IWM options chain (previous day to today)
- QQQ options chain (previous day to today)

**Manual trigger options**:
- `start_date`: Custom start date (YYYY-MM-DD), default: yesterday
- `end_date`: Custom end date (YYYY-MM-DD), default: today
- `symbols`: Which symbols to fetch (SPY, IWM, QQQ, or ALL), default: ALL

**Usage**:
```bash
# Via GitHub Actions UI
Go to Actions → Fetch Daily Alpha Vantage Options Data → Run workflow
# Specify start_date, end_date, and symbols as needed

# Via gh CLI
gh workflow run fetch-alphavantage-options-daily.yml
gh workflow run fetch-alphavantage-options-daily.yml -f symbols="SPY IWM" -f start_date="2025-01-01" -f end_date="2025-01-15"
```

**Output**:
- Daily parquet files: `data/{symbol}/options/{symbol}_av_options_{YYYYMMDD}.parquet`
- Combined file: `data/{symbol}/options/{symbol}_av_options_combined.parquet`
- Summary JSON: `data/{symbol}/options/{symbol}_av_options_summary.json`

**API Usage**:
- ~2 API calls per symbol per day (if fetching 2 days)
- Daily: ~6 API calls total (2 days × 3 symbols)

---

### 2. Monthly Intraday Data (`fetch-alphavantage-intraday-monthly.yml`)

**Schedule**: 1st of each month at 9:00 PM EDT (1:00 AM UTC)

**What it fetches**:
- SPY 1-minute intraday data (previous month to today)
- QQQ 1-minute intraday data (previous month to today)
- IWM 1-minute intraday data (previous month to today)

**Manual trigger options**:
- `start_date`: Custom start date (YYYY-MM-DD), default: first day of previous month
- `end_date`: Custom end date (YYYY-MM-DD), default: today
- `symbols`: Which symbols to fetch (SPY, IWM, QQQ, or ALL), default: ALL
- `interval`: Time interval (1min, 5min, 15min, 30min, 60min), default: 1min

**Usage**:
```bash
# Via GitHub Actions UI
Go to Actions → Fetch Monthly Alpha Vantage Intraday Data → Run workflow
# Specify start_date, end_date, symbols, and interval as needed

# Via gh CLI
gh workflow run fetch-alphavantage-intraday-monthly.yml
gh workflow run fetch-alphavantage-intraday-monthly.yml -f symbols="SPY" -f interval="5min" -f start_date="2025-01-01"
```

**Output**:
- Monthly parquet files: `data/{symbol}/intraday/{symbol}_av_{interval}_{YYYYMM}.parquet`
- Combined file: `data/{symbol}/intraday/{symbol}_av_{interval}_combined.parquet`
- Summary JSON: `data/{symbol}/intraday/{symbol}_av_{interval}_summary.json`

**API Usage**:
- ~1 API call per month per symbol
- Monthly run: ~3 API calls total (1 month × 3 symbols)
- Backfilling multiple months: ~N API calls per symbol

---

## Configuration

### Required Secrets

Both workflows require the `ALPHA_VANTAGE_API_KEY` secret to be set in GitHub:

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `ALPHA_VANTAGE_API_KEY`
4. Value: Your Alpha Vantage API key
5. Click **Add secret**

The scripts support multiple API keys for failover (configured in the Python scripts):
- Primary key (from GitHub secret)
- 4 backup keys (hardcoded in scripts)

### Optional Secrets

- `PR_WORKFLOW_TOKEN`: GitHub token for creating PRs on workflow failures (optional, uses `GITHUB_TOKEN` by default)

---

## Features

### Automatic Caching
Both workflows leverage the caching built into the Python scripts:
- Re-running workflows won't re-download existing data
- Only fetches new data that doesn't already exist locally
- Creates `.nodata` marker files to skip dates with no data

### Failure Handling
Both workflows include automated failure handling:
- **Continue-on-error**: If one symbol fails, others continue
- **Partial commits**: Successfully fetched data is committed even if some symbols fail
- **Issue creation**: Auto-creates GitHub issues on failure with error logs
- **PR creation**: Auto-creates draft PRs with fix branches

### Retry Logic
Robust git push retry with exponential backoff:
- Handles concurrent workflow pushes gracefully
- Attempts rebase and merge strategies
- Up to 8 retry attempts with jitter

---

## Monitoring

### Check Workflow Status

**Via GitHub UI**:
1. Go to **Actions** tab
2. Select workflow from left sidebar
3. View recent runs

**Via gh CLI**:
```bash
# List recent workflow runs
gh run list --workflow=fetch-alphavantage-options-daily.yml
gh run list --workflow=fetch-alphavantage-intraday-monthly.yml

# View specific run
gh run view <run-id>

# Watch a running workflow
gh run watch
```

### Check for Failures

```bash
# List workflow failure issues
gh issue list --label "workflow-failure,alpha-vantage"

# List all automated issues
gh issue list --label "automated"
```

---

## API Rate Limits

**Alpha Vantage Free Tier**:
- 5 API calls per minute
- 500 API calls per day (per API key)

**With Multi-Key Failover** (5 keys):
- Effective limit: ~2,500 API calls per day
- Scripts automatically switch keys when limits hit

**Estimated Usage**:
- **Daily options workflow**: ~6 calls/day (well within limits)
- **Monthly intraday workflow**: ~3 calls/month (well within limits)
- **Combined**: ~190 calls/month (well within limits)

**Backfilling Considerations**:
If manually backfilling large date ranges:
- 1 year of daily options = ~252 trading days × 3 symbols = 756 calls
- 5 years of monthly intraday = 60 months × 3 symbols = 180 calls
- May need to spread backfills across multiple days or use multiple API keys

---

## Troubleshooting

### Workflow Not Running

**Check schedule**:
- Cron uses UTC time (EDT = UTC-4, EST = UTC-5)
- Scheduled workflows may have up to 15-minute delay
- GitHub Actions may skip scheduled runs during high load

**Manual trigger**:
```bash
gh workflow run fetch-alphavantage-options-daily.yml
```

### API Key Exhausted

**Symptoms**:
- Workflow logs show "ALL API KEYS EXHAUSTED"
- Script exits with status code 1

**Solution**:
1. Wait 24 hours for rate limits to reset
2. Add more backup API keys to the Python scripts
3. Re-run the workflow manually

### Data Not Committing

**Check**:
1. Workflow logs for "No changes to commit" message
2. Whether data was actually fetched successfully
3. If files were created in correct location

**Common causes**:
- Weekend/holiday (no trading data)
- Data already exists (caching working correctly)
- API returned no data for date range

### Merge Conflicts

**Automatic handling**:
- Workflows use "ours" strategy (prefer newer data)
- Up to 8 retry attempts with exponential backoff

**Manual resolution**:
If workflow still fails after retries:
1. Check the auto-created issue/PR
2. Manually resolve conflicts in the PR branch
3. Merge the PR

---

## Best Practices

### Regular Monitoring
- Check workflow runs weekly
- Review auto-created issues monthly
- Verify data completeness quarterly

### Backfilling Data
When backfilling historical data:
1. **Test with small range first**:
   ```bash
   gh workflow run fetch-alphavantage-options-daily.yml -f start_date="2025-01-01" -f end_date="2025-01-05" -f symbols="SPY"
   ```

2. **Monitor API usage**: Check workflow logs for API key switching

3. **Spread large backfills across days**: Don't exceed daily rate limits

4. **Use manual triggers**: More control than scheduled runs

### API Key Management
- Rotate API keys periodically
- Monitor usage via Alpha Vantage dashboard
- Add backup keys to Python scripts as needed

---

## Related Documentation

- [Alpha Vantage Quick Start Guide](./alpha-vantage-quickstart.md)
- [Alpha Vantage Data Fetching Guide](./alpha-vantage-data-fetching.md)
- [Workflow Failure Handling System](../CLAUDE.md#automated-workflow-failure-handling)
