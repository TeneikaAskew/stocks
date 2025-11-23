# Options Heatseeker - Live API Integration Plan v2
## Using Your Existing API Key Infrastructure

## Executive Summary

Use a **serverless backend proxy** to fetch live Alpha Vantage data using your existing API key (already in GitHub Secrets). The web app calls your proxy, which calls Alpha Vantage, eliminating the need for:
- ❌ Users to provide API keys
- ❌ Manual data conversion
- ❌ Storing large static JSON files in the repository

---

## Architecture

### Proposed Flow
```
User → GitHub Pages App → Your Proxy API → Alpha Vantage
                              ↓
                       (Uses your API key)
                              ↓
                        Client cache
```

### Components

**1. GitHub Pages Frontend** (existing)
- React/vanilla JS app
- Calls proxy API for data
- Caches responses locally

**2. Serverless Proxy API** (new)
- GitHub Actions workflow OR
- Cloudflare Workers OR
- Vercel Edge Functions
- Uses `${{ secrets.ALPHA_VANTAGE_API_KEY }}`
- Returns JSON to frontend

**3. Alpha Vantage API** (existing)
- Source of truth for options data
- Your API key already configured

---

## Option A: GitHub Actions as API Proxy (RECOMMENDED)

### Why This Option?
✅ **Zero cost** - Already using GitHub Actions
✅ **Existing setup** - API key already in secrets
✅ **Simple** - One workflow file
✅ **Secure** - API key never exposed to client

### Implementation

#### Step 1: Create API Endpoint Workflow

**File**: `.github/workflows/api-fetch-options.yml`

```yaml
name: API - Fetch Options Data

on:
  repository_dispatch:
    types: [fetch-options]
  workflow_dispatch:
    inputs:
      symbol:
        description: 'Symbol (IWM, QQQ, SPY)'
        required: true
        type: string
      date:
        description: 'Date (YYYY-MM-DD)'
        required: true
        type: string
      callback_url:
        description: 'Webhook URL for response'
        required: false
        type: string

jobs:
  fetch-and-respond:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install requests pyarrow pandas

      - name: Fetch options data
        id: fetch
        run: |
          python scripts/api_fetch_options.py \
            --symbol ${{ inputs.symbol }} \
            --date ${{ inputs.date }} \
            --output json

      - name: Upload result as artifact
        uses: actions/upload-artifact@v3
        with:
          name: options-data
          path: output/options_${{ inputs.symbol }}_${{ inputs.date }}.json
          retention-days: 1

      - name: Send webhook response (if callback provided)
        if: inputs.callback_url != ''
        run: |
          curl -X POST "${{ inputs.callback_url }}" \
            -H "Content-Type: application/json" \
            -d @output/options_${{ inputs.symbol }}_${{ inputs.date }}.json
```

#### Step 2: Create Python API Script

**File**: `scripts/api_fetch_options.py`

```python
#!/usr/bin/env python3
"""
API endpoint to fetch options data from Alpha Vantage
Returns JSON directly (no parquet conversion needed)
"""

import requests
import json
import argparse
import os
from pathlib import Path

ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY')
BASE_URL = 'https://www.alphavantage.co/query'

def fetch_options_chain(symbol, date):
    """Fetch options chain from Alpha Vantage"""
    params = {
        'function': 'HISTORICAL_OPTIONS',
        'symbol': symbol,
        'date': date,
        'apikey': ALPHA_VANTAGE_API_KEY
    }

    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    # Alpha Vantage returns data directly
    if data.get('message') == 'success':
        return {
            'ticker': symbol.upper(),
            'date': date,
            'snapshot_timestamp': date,
            'options': data.get('data', [])
        }
    else:
        raise Exception(f"API error: {data}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--date', required=True)
    parser.add_argument('--output', default='json')
    args = parser.parse_args()

    # Fetch data
    result = fetch_options_chain(args.symbol, args.date)

    # Create output directory
    output_dir = Path('output')
    output_dir.mkdir(exist_ok=True)

    # Write JSON
    output_file = output_dir / f'options_{args.symbol}_{args.date}.json'
    with open(output_file, 'w') as f:
        json.dump(result, f)

    print(f"✓ Wrote {output_file}")
```

#### Step 3: Frontend Integration

**File**: `options-heatseeker/js/githubAPIService.js`

```javascript
const GitHubAPIService = {
    owner: 'TeneikaAskew',
    repo: 'stocks',
    token: null, // GitHub token for API calls (optional)

    async fetchOptionsData(symbol, date) {
        // Trigger GitHub Actions workflow
        const workflowUrl = `https://api.github.com/repos/${this.owner}/${this.repo}/actions/workflows/api-fetch-options.yml/dispatches`;

        const payload = {
            ref: 'main',
            inputs: {
                symbol: symbol.toUpperCase(),
                date: date
            }
        };

        // Trigger workflow
        await fetch(workflowUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.token}`
            },
            body: JSON.stringify(payload)
        });

        // Wait for workflow to complete and fetch artifact
        // This requires polling or webhook callback
        return this.pollForResult(symbol, date);
    },

    async pollForResult(symbol, date, maxAttempts = 10) {
        // Poll workflow runs for completion
        // Then download artifact
        // This is complex - see Alternative below
    }
};
```

**Problem**: This approach requires polling, which is slow and complex.

---

## Option B: Simple Static API Files (BEST FOR YOU)

### Why This Option?
✅ **Zero complexity** - Just generate JSON files
✅ **Uses existing workflow** - Minor modification to daily fetch
✅ **Instant loading** - No API calls, just static files
✅ **No rate limits** - Serve from GitHub Pages CDN

### The Key Insight
You're already fetching options data daily via GitHub Actions! Just:
1. **Keep the daily fetch workflow** (already exists)
2. **Output to JSON instead of Parquet** (minor change)
3. **Serve JSON files from GitHub Pages** (already set up)
4. **Auto-update daily** (via existing schedule)

### Implementation

#### Step 1: Modify Existing Workflow

**File**: `.github/workflows/fetch-alphavantage-options-daily.yml` (modify)

```yaml
# Add these steps after fetching

- name: Convert to JSON for web app
  run: |
    python scripts/convert_for_web.py \
      --input data/*/options/*_av_options_*.parquet \
      --output options-heatseeker/data/

- name: Commit web app data
  run: |
    git add options-heatseeker/data/
    git commit -m "Update options data for web app - $(date +%Y-%m-%d)"
    git push
```

#### Step 2: Create Conversion Script

**File**: `scripts/convert_for_web.py`

```python
#!/usr/bin/env python3
"""
Convert parquet files to compact JSON for web app
Only convert latest ~30 days to keep repository small
"""

import pandas as pd
from pathlib import Path
import json
from datetime import datetime, timedelta

def convert_recent_data(days=30):
    """Convert recent parquet files to JSON"""
    cutoff_date = datetime.now() - timedelta(days=days)

    for ticker_dir in Path('data').iterdir():
        if not ticker_dir.is_dir():
            continue

        ticker = ticker_dir.name
        options_dir = ticker_dir / 'options'

        # Get recent parquet files
        parquet_files = sorted(options_dir.glob(f'{ticker}_av_options_*.parquet'))

        for parquet_file in parquet_files:
            # Extract date from filename
            date_str = parquet_file.stem.split('_')[-1]

            try:
                file_date = datetime.strptime(date_str, '%Y%m%d')
            except:
                continue

            # Skip old files
            if file_date < cutoff_date:
                continue

            # Read parquet
            df = pd.read_parquet(parquet_file)

            # Convert to JSON
            data = {
                'ticker': ticker.upper(),
                'date': date_str,
                'snapshot_timestamp': file_date.isoformat(),
                'options': df.to_dict(orient='records')
            }

            # Write to web app directory
            output_dir = Path('options-heatseeker/data') / ticker
            output_dir.mkdir(parents=True, exist_ok=True)

            output_file = output_dir / f'{ticker}_options_{date_str}.json'
            with open(output_file, 'w') as f:
                json.dump(data, f, separators=(',', ':'))  # Compact

            print(f"✓ Converted {parquet_file.name} -> {output_file.name}")

if __name__ == '__main__':
    convert_recent_data(days=30)
```

#### Step 3: Auto-Cleanup Old Files

```yaml
# Add to workflow

- name: Cleanup old web data (keep 30 days)
  run: |
    find options-heatseeker/data -name "*.json" -mtime +30 -delete
```

### Result
- ✅ **Auto-updates daily** at 9 PM EDT
- ✅ **Always has latest data**
- ✅ **Small repository** (only 30 days × 3 tickers)
- ✅ **Fast loading** (static files from CDN)
- ✅ **Zero user interaction** needed

---

## Option C: Cloudflare Workers Proxy (If You Want True "Live")

### Cloudflare Worker Code

```javascript
// Cloudflare Worker (deploy.workers.cloudflare.com)

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const symbol = url.searchParams.get('symbol');
    const date = url.searchParams.get('date');

    if (!symbol || !date) {
      return new Response('Missing symbol or date', { status: 400 });
    }

    // Fetch from Alpha Vantage using your API key
    const avUrl = `https://www.alphavantage.co/query?function=HISTORICAL_OPTIONS&symbol=${symbol}&date=${date}&apikey=${env.ALPHA_VANTAGE_API_KEY}`;

    const response = await fetch(avUrl);
    const data = await response.json();

    // Add CORS headers
    return new Response(JSON.stringify(data), {
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Cache-Control': 'public, max-age=3600'
      }
    });
  }
};
```

**Deployment**:
```bash
# One-time setup
npm install -g wrangler
wrangler login

# Deploy
wrangler secret put ALPHA_VANTAGE_API_KEY
# Enter your API key when prompted

wrangler deploy
# Returns: https://your-worker.workers.dev
```

**Frontend Integration**:
```javascript
// options-heatseeker/js/config.js
const CONFIG = {
    API_ENDPOINT: 'https://your-worker.workers.dev',
    ...
};

// options-heatseeker/js/dataLoader.js
async loadOptionsData(ticker, dateStr) {
    const url = `${CONFIG.API_ENDPOINT}?symbol=${ticker}&date=${dateStr}`;
    const response = await fetch(url);
    return response.json();
}
```

**Cost**: $0 (100,000 requests/day free)

---

## Recommendation: Option B (Static with Daily Updates)

### Why?
You're **already fetching the data daily**! Just:
1. Add JSON conversion step to existing workflow ✅
2. Serve files from GitHub Pages ✅
3. Auto-updates every night ✅
4. Users get "latest" data (updated daily)

### What Changes?
```diff
# Your existing workflow
fetch_alphavantage_options.py → writes parquet

+ # Add this step
+ convert_for_web.py → writes JSON to options-heatseeker/data/
+ git commit & push

# Result: GitHub Pages serves latest JSON
```

### Trade-offs

| Approach | Pros | Cons |
|----------|------|------|
| **Option A: GitHub Actions API** | Truly live, zero cost | Complex polling, slow (60+ seconds) |
| **Option B: Static + Daily Update** | Simple, fast, auto-updates | 1-day delay max |
| **Option C: Cloudflare Worker** | Truly live, fast (<1s) | Extra service to maintain |

---

## Implementation Timeline (Option B)

### Day 1: Modify Existing Workflow
- Add JSON conversion step to `fetch-alphavantage-options-daily.yml`
- Test conversion script
- Verify JSON files are committed

### Day 2: Update Frontend
- Remove static data from repo (if needed)
- Update dataLoader.js to use new JSON path
- Test loading

### Day 3: Cleanup & Deploy
- Add auto-cleanup of old files (30 days)
- Update README
- Deploy to production

**Total Time**: 3 days

---

## Next Steps

1. **Choose approach**: B (recommended) or C (if you want true live)
2. **For Option B**:
   - Modify existing daily fetch workflow
   - Add JSON conversion step
   - Test and deploy

3. **For Option C**:
   - Set up Cloudflare Workers account
   - Add API key as secret
   - Deploy worker
   - Update frontend to call worker

Which approach would you prefer?
