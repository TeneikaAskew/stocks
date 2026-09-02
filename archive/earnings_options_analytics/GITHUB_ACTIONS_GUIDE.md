# GitHub Actions Quick Start Guide

## 🚀 Running Analytics via GitHub Actions

This guide shows you how to use the automated GitHub Actions workflow to run earnings options analytics.

---

## ✨ Quick Start

### Option 1: Manual Trigger (Recommended for Testing)

1. **Navigate to GitHub Actions**
   - Go to your repository on GitHub
   - Click **Actions** tab at the top

2. **Select Workflow**
   - Click **Earnings Options Analytics** in the left sidebar

3. **Run Workflow**
   - Click **Run workflow** button (right side)
   - Configure options:
     - **Analysis Type**: Select `quick` for fast run, `full` for complete analysis
     - **Export Charts**: Check to generate PNG visualizations
     - **Export CSV**: Check to export detailed CSV reports
   - Click **Run workflow** (green button)

4. **Monitor Progress**
   - Click on the running workflow to see live logs
   - Jobs run in sequence: Test → Analyze → Notify
   - Estimated time: 2-3 minutes for full analysis

5. **Download Results**
   - Wait for workflow to complete (green checkmark)
   - Scroll to bottom of workflow run page
   - Click on artifacts to download:
     - `csv-reports-###` - All CSV analysis files
     - `charts-###` - PNG visualizations
     - `html-report-###` - Comprehensive HTML report

### Option 2: Automatic on Push

Simply push changes to analytics code or data files:

```bash
# Make changes to analytics code
git add earnings_options_analytics/
git commit -m "Update analytics"
git push origin main

# Workflow automatically triggers
# Check Actions tab to monitor
```

### Option 3: Automatic Daily Schedule

- Workflow runs automatically at 2 AM UTC daily
- Full analysis with all outputs
- Check Actions tab next morning for results
- Artifacts available for download (30-day retention)

---

## 📊 Analysis Modes

### Quick Mode
**Use when:** Testing changes, rapid validation
**Runtime:** ~30 seconds
**Outputs:** CSV reports only
**Command:** `python earnings_options_analytics.py --quick --export-csv`

### Full Mode
**Use when:** Production insights, comprehensive analysis
**Runtime:** ~2 minutes
**Outputs:** CSV reports + Charts + HTML report
**Command:** `python earnings_options_analytics.py --full --export-csv --export-charts`

### Test-Only Mode
**Use when:** Validating system without running analysis
**Runtime:** ~10 seconds
**Outputs:** Test results only
**Command:** `python test_system.py`

---

## 📁 Understanding Artifacts

### CSV Reports (`csv-reports-{run_number}`)
**Contains:** 15+ CSV files
**Location after download:** `csv_reports/` folder
**Files include:**
- `overall.csv` - Overall performance metrics
- `strategy_breakdown.csv` - Per-strategy analysis
- `earnings_timing_entry_window.csv` - Optimal entry timing
- `indicator_correlation.csv` - Indicator effectiveness
- `risk_kelly.csv` - Position sizing recommendations
- And 10+ more detailed reports

**Use for:** Detailed data analysis, Excel importing, custom visualizations

### Charts (`charts-{run_number}`)
**Contains:** 7 PNG images (300 DPI)
**Location after download:** `charts/` folder
**Files include:**
- `strategy_comparison.png` - Multi-metric strategy comparison
- `earnings_timing.png` - Entry window performance
- `indicator_heatmap.png` - Indicator correlation matrix
- `risk_reward_distribution.png` - Risk/reward analysis
- And 3+ more visualizations

**Use for:** Presentations, reports, quick insights

### HTML Report (`html-report-{run_number}`)
**Contains:** Single HTML file
**Location after download:** `earnings_options_report.html`
**Features:**
- Executive summary dashboard
- All analysis sections with tables
- Embedded charts
- Actionable recommendations
- Professional styling

**Use for:** Comprehensive review, sharing with stakeholders, archiving

### Analysis Log (`analysis-log-{run_number}`)
**Contains:** Full console output
**Location after download:** `analysis_output.log`
**Retention:** 7 days
**Use for:** Debugging, verifying execution, troubleshooting

### Run Summary (`run-summary-{run_number}`)
**Contains:** Markdown summary
**Location after download:** `run_summary.md`
**Features:**
- File counts and sizes
- Execution metadata
- Output listings

**Use for:** Quick reference, status checking

---

## ⚙️ Configuration Guide

### Changing Schedule

Edit `.github/workflows/earnings-options-analytics.yml`:

```yaml
schedule:
  - cron: '0 2 * * *'  # Change this line
```

**Examples:**
```yaml
- cron: '0 6 * * *'      # Daily at 6 AM UTC
- cron: '0 */6 * * *'    # Every 6 hours
- cron: '0 0 * * 1'      # Every Monday at midnight
- cron: '0 12 * * 1-5'   # Weekdays at noon UTC
- cron: '0 20 * * 0'     # Sundays at 8 PM UTC
```

### Changing Retention Period

Edit artifact upload steps:

```yaml
- name: Upload CSV reports
  uses: actions/upload-artifact@v4
  with:
    retention-days: 30  # Change to 7, 14, 60, or 90
```

### Adding Notifications

Add to the notify job:

```yaml
- name: Send email notification
  uses: dawidd6/action-send-mail@v3
  with:
    server_address: smtp.gmail.com
    server_port: 465
    username: ${{ secrets.EMAIL_USERNAME }}
    password: ${{ secrets.EMAIL_PASSWORD }}
    subject: Analytics Complete - ${{ steps.check_results.outputs.status }}
    body: ${{ steps.check_results.outputs.message }}
    to: your-email@example.com
```

---

## 🔍 Monitoring & Troubleshooting

### Check Workflow Status

1. Go to **Actions** tab
2. Look for status icons:
   - ✅ Green checkmark = Success
   - ❌ Red X = Failed
   - 🟡 Yellow circle = Running
   - ⚪ Gray circle = Queued

3. Click on workflow run to see details

### View Logs

1. Click on failed/running workflow
2. Click on job name (e.g., "Test" or "Analyze")
3. Expand step to see output
4. Look for error messages (usually in red)

### Common Issues

**Issue:** Workflow doesn't start
**Solution:**
- Check if changes are in monitored paths
- Verify workflow file is valid YAML
- Check repository Actions settings are enabled

**Issue:** Test job fails
**Solution:**
- Review test output in logs
- Check data quality score (target >80%)
- Verify CSV files are properly formatted

**Issue:** Analyze job skipped
**Solution:**
- Ensure CSV files exist in `google-apps-script/data/`
- Check that test job passed
- Verify not running on pull request (analyze skips PRs)

**Issue:** No artifacts generated
**Solution:**
- Check if analysis completed successfully
- Review job logs for errors
- Verify outputs directory was created

**Issue:** Charts missing
**Solution:**
- Ensure `export_charts` input is `true`
- Check matplotlib dependencies installed
- Review analysis log for chart generation errors

### Enable Debug Logging

1. Go to repository **Settings**
2. Click **Secrets and variables** → **Actions**
3. Click **Variables** tab
4. Add new variable:
   - Name: `ACTIONS_STEP_DEBUG`
   - Value: `true`
5. Re-run workflow for detailed logs

---

## 📈 Best Practices

### For Development

1. **Use Quick Mode** for testing code changes
2. **Enable PR checks** to catch issues early
3. **Review test results** before merging
4. **Download artifacts** for manual verification

### For Production

1. **Use Full Mode** for scheduled runs
2. **Set appropriate schedule** (daily recommended)
3. **Monitor daily runs** for failures
4. **Archive important artifacts** beyond 30-day retention
5. **Review recommendations** in HTML reports regularly

### For Performance

1. **Use Quick Mode** when charts not needed
2. **Disable test-only runs** unless debugging
3. **Adjust retention** based on needs (7 days for logs, 30 for reports)
4. **Clean up old artifacts** manually if needed

---

## 🔗 Integration Examples

### Trigger After Google Sheets Download

Add to `download-google-sheets.yml`:

```yaml
jobs:
  download:
    # ... existing download steps ...

  trigger-analytics:
    needs: download
    runs-on: ubuntu-latest
    steps:
      - name: Trigger analytics workflow
        run: |
          gh workflow run earnings-options-analytics.yml \
            -f analysis_type=full \
            -f export_charts=true \
            -f export_csv=true
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### Post Results to Slack

Add to notify job:

```yaml
- name: Post to Slack
  uses: slackapi/slack-github-action@v1
  with:
    payload: |
      {
        "text": "Analytics Complete",
        "blocks": [
          {
            "type": "section",
            "text": {
              "type": "mrkdwn",
              "text": "*Status:* ${{ steps.check_results.outputs.status }}\n*Message:* ${{ steps.check_results.outputs.message }}\n*Run:* <https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }}|View Details>"
            }
          }
        ]
      }
  env:
    SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}
```

### Save to Cloud Storage

Add after analysis completes:

```yaml
- name: Upload to S3
  uses: aws-actions/configure-aws-credentials@v4
  with:
    aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
    aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
    aws-region: us-east-1

- name: Sync to S3
  run: |
    aws s3 sync earnings_options_analytics/outputs/ \
      s3://my-bucket/analytics/$(date +%Y%m%d)/
```

---

## 📞 Getting Help

### Resources

- **Workflow File:** `.github/workflows/earnings-options-analytics.yml`
- **Workflow README:** `.github/workflows/README.md`
- **Project Summary:** `earnings_options_analytics/PROJECT_SUMMARY.md`
- **Main README:** `earnings_options_analytics/README.md`

### Check Workflow Syntax

```bash
# Install actionlint
brew install actionlint  # macOS
# or download from: https://github.com/rhysd/actionlint

# Validate workflow
actionlint .github/workflows/earnings-options-analytics.yml
```

### Test Locally

```bash
# Navigate to analytics directory
cd earnings_options_analytics

# Run tests
python test_system.py

# Run quick analysis
python earnings_options_analytics.py --quick --export-csv

# Run full analysis
python earnings_options_analytics.py --full --export-csv --export-charts
```

---

## 💡 Tips & Tricks

### Download All Artifacts at Once

1. Install GitHub CLI: `brew install gh` (macOS) or from https://cli.github.com
2. Run: `gh run download <run-number> -D ./downloads/`
3. All artifacts downloaded to `./downloads/` folder

### View HTML Report Online

1. Download `html-report-###` artifact
2. Extract `earnings_options_report.html`
3. Upload to GitHub Gist or similar
4. Share link with team

### Compare Runs

1. Download artifacts from multiple runs
2. Compare CSV files in Excel or Python
3. Track performance trends over time
4. Identify strategy improvements

### Automate Report Distribution

1. Add email notification step (see examples above)
2. Attach HTML report to email
3. Schedule for daily delivery
4. Team receives insights automatically

---

## 📋 Checklist for First Run

- [ ] Verify CSV data files exist in `google-apps-script/data/`
- [ ] Check Python version is 3.11 in workflow file
- [ ] Enable Actions in repository settings
- [ ] Test locally first (`python test_system.py`)
- [ ] Trigger manual run with `quick` mode
- [ ] Review test job results
- [ ] Download and inspect artifacts
- [ ] Verify CSV reports open correctly
- [ ] Check HTML report renders properly
- [ ] Enable scheduled runs once validated

---

**Last Updated:** 2025-10-09
**Workflow Version:** 1.0.0
