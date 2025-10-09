# Google Sheets Download Setup

This guide explains how to set up automated downloads of your Google Sheets data to this repository.

## Overview

The GitHub Action workflow downloads your Google Sheets as CSV files daily and commits them to the repository. This allows the earnings options analytics system to analyze your trading data.

## Prerequisites

- Access to a Google Cloud account
- Your Google Sheets spreadsheet with strategy data
- Admin access to this GitHub repository

## Step-by-Step Setup

### 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Click "Select a project" → "New Project"
3. Name it (e.g., "Stocks Trading Sheets API")
4. Click "Create"

### 2. Enable Google Sheets API

1. In your project, go to **APIs & Services** → **Library**
2. Search for "Google Sheets API"
3. Click on it and press **Enable**

### 3. Create Service Account

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **Service Account**
3. Fill in the details:
   - **Service account name**: `github-actions-sheets`
   - **Service account ID**: (auto-filled)
   - **Description**: "Service account for GitHub Actions to read Google Sheets"
4. Click **Create and Continue**
5. Skip the optional steps and click **Done**

### 4. Create Service Account Key

1. On the **Credentials** page, find your service account in the list
2. Click on the service account email
3. Go to the **Keys** tab
4. Click **Add Key** → **Create new key**
5. Select **JSON** format
6. Click **Create**
7. A JSON file will download to your computer - **keep this safe!**

### 5. Share Your Google Sheet

1. Open the JSON file you just downloaded
2. Find the `client_email` field (looks like: `github-actions-sheets@your-project.iam.gserviceaccount.com`)
3. Copy this email address
4. Open your Google Sheets spreadsheet
5. Click **Share** in the top right
6. Paste the service account email
7. Give it **Viewer** access
8. Uncheck "Notify people"
9. Click **Share**

### 6. Get Your Spreadsheet ID

Your spreadsheet ID is in the URL:
```
https://docs.google.com/spreadsheets/d/[SPREADSHEET_ID]/edit
                                      ^^^^^^^^^^^^^^^^^^^
                                      This is your ID
```

Copy this ID - you'll need it for the next step.

### 7. Add GitHub Secrets

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**

**Create these two secrets:**

#### Secret 1: `GOOGLE_SHEETS_CREDENTIALS`
- Name: `GOOGLE_SHEETS_CREDENTIALS`
- Value: Open the JSON file you downloaded in step 4, copy the **entire contents**, and paste it here
- Click **Add secret**

#### Secret 2: `GOOGLE_SPREADSHEET_ID`
- Name: `GOOGLE_SPREADSHEET_ID`
- Value: Paste the spreadsheet ID you copied in step 6
- Click **Add secret**

## Usage

### Automatic Daily Downloads

The workflow runs automatically at 6:00 PM EST (11:00 PM UTC) every weekday.

### Manual Trigger

To manually download sheets:

1. Go to **Actions** tab in GitHub
2. Click **Download Google Sheets Data**
3. Click **Run workflow**
4. (Optional) Specify specific sheets to download: `Long Calls Bull Spreads`
5. Click **Run workflow**

### Local Testing

To test the download script locally:

```bash
# Install dependencies
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client

# Download your service account JSON and save it
mkdir -p credentials
# Place your JSON file at: credentials/google-sheets-credentials.json

# Run the script
python scripts/download_google_sheets.py \
  --spreadsheet-id YOUR_SPREADSHEET_ID \
  --credentials credentials/google-sheets-credentials.json

# Download specific sheets only
python scripts/download_google_sheets.py \
  --spreadsheet-id YOUR_SPREADSHEET_ID \
  --sheets "Long Calls" "Bull Spreads"
```

## Verify Setup

After the first run, check:

1. **Actions** tab shows a successful workflow run (green checkmark)
2. New CSV files appear in `google-apps-script/data/`:
   - `LongCalls.csv`
   - `BullSpreads.csv`
   - `CoveredCalls.csv`
   - etc.
3. A new commit appears with message like: `update: Google Sheets data - 2025-10-09`

## Troubleshooting

### Error: "The caller does not have permission"

- Make sure you shared the spreadsheet with the service account email
- Check that the service account has at least **Viewer** access

### Error: "Credentials file not found"

- Verify the `GOOGLE_SHEETS_CREDENTIALS` secret is set correctly
- Make sure you copied the **entire** JSON content including `{` and `}`

### Error: "API has not been used in project"

- Go back to Google Cloud Console
- Make sure the Google Sheets API is enabled for your project
- Wait a few minutes and try again

### Empty or Missing Sheets

- Verify your sheet names match exactly (case-sensitive):
  - `Long Calls`
  - `Bull Spreads`
  - `Covered Calls`
  - `Long Puts`
  - `Bear Spreads`
  - `Short Calls`
  - `Strangles`
  - `Straddles`
  - `Short Puts`

## Security Notes

- **Never** commit the service account JSON file to the repository
- The credentials are stored securely in GitHub Secrets
- The workflow cleans up the credentials file after each run
- Service account has read-only access to your sheets

## Sheet Requirements

Each strategy sheet should have these columns (at minimum):

- `Run Date` - Date the trade was entered
- `ticker` - Stock ticker symbol
- `strike` - Option strike price
- `expDate` - Option expiration date
- `nextEPSDate` - Next earnings date
- `Strike_Hit` - JSON array of daily strike hit data
- Indicator columns: `Hit_RSI`, `Hit_SMA20`, etc.

See [data_loader.py](../earnings_options_analytics/modules/data_loader.py) for full column list.
