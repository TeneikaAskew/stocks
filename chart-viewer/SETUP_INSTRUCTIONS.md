# Setup Instructions

## Quick Start - GitHub Pages (Recommended)

This is the easiest way to get started. Your chart viewer will be available 24/7 online with no server needed!

### Step 1: Prepare Data

Run the deployment script to convert parquet files to JSON:

```bash
cd chart-viewer
python3 deploy_github_pages.py
```

This will:
- Convert all parquet files in `../data/iwm/minute/`, `../data/spy/minute/`, `../data/qqq/minute/` to JSON
- Create `data/iwm/`, `data/spy/`, `data/qqq/` directories with JSON files
- Update `src/config.js` to use GitHub Pages mode

### Step 2: Commit and Push

```bash
git add chart-viewer/
git commit -m "add: Trading Chart Viewer with data"
git push origin claude/alphavantage-chart-display-01LmDuxmwN7LcyMDta3cAT5D
```

### Step 3: Enable GitHub Pages

1. Go to your repository on GitHub
2. Click **Settings** → **Pages**
3. Under "Source", select your branch: `claude/alphavantage-chart-display-01LmDuxmwN7LcyMDta3cAT5D`
4. Set directory to `/chart-viewer` (if option available) or `/` (root)
5. Click **Save**

### Step 4: Access Your Chart

Your chart viewer will be available at:
```
https://TeneikaAskew.github.io/stocks/chart-viewer/
```

(Replace `TeneikaAskew` with your GitHub username)

It may take a few minutes for GitHub Pages to build and deploy.

---

## Alternative - Local Development

If you want to test locally with the Python API:

### Prerequisites

- Python 3.8+
- pip3

### Step 1: Install Dependencies

```bash
cd chart-viewer
pip3 install -r requirements.txt
```

### Step 2: Start Servers

#### Option A: Use start script (Linux/Mac)
```bash
./start_local.sh
```

#### Option B: Manual start (All platforms)

**Terminal 1 - Start API:**
```bash
cd chart-viewer
python3 api.py
```

**Terminal 2 - Start Frontend:**
```bash
cd chart-viewer
python3 -m http.server 8080
```

### Step 3: Open Browser

Navigate to: `http://localhost:8080`

---

## Switching Between Modes

### GitHub Pages → Local API

Edit `src/config.js`:
```javascript
USE_LOCAL_API: true,  // Change to true
```

### Local API → GitHub Pages

Edit `src/config.js`:
```javascript
USE_LOCAL_API: false,  // Change to false
```

Or run the deployment script again:
```bash
python3 deploy_github_pages.py
```

---

## Troubleshooting

### Chart not loading

**Check 1: Data files**
- Ensure parquet files exist in `../data/{ticker}/minute/`
- File naming: `{ticker}_minute_YYYYMMDD.parquet`
- Example: `iwm_minute_20251114.parquet`

**Check 2: Browser console**
- Press F12 to open Developer Tools
- Check Console tab for errors
- Common issues:
  - CORS errors → Make sure API is running
  - 404 errors → Check data files exist
  - JSON parse errors → Re-run deployment script

**Check 3: API (if using local mode)**
```bash
# Test API health
curl http://localhost:5000/api/health

# Test dates endpoint
curl http://localhost:5000/api/dates/IWM

# Test data endpoint
curl http://localhost:5000/api/data/IWM/20251114
```

### No dates showing in dropdown

- Run deployment script to generate `dates.json` files
- Check that JSON files were created in `chart-viewer/data/{ticker}/`

### Trades not saving

- Check browser localStorage is enabled
- Try different browser
- Export to CSV as backup before clearing cache

---

## Data Management

### Adding New Data

1. Add new parquet files to `../data/{ticker}/minute/`
2. Re-run deployment script: `python3 deploy_github_pages.py`
3. Commit and push to update GitHub Pages

### Data Format

Parquet files must have:
- Datetime index
- Columns: Open, High, Low, Close, Volume (case-insensitive)

Example structure:
```
                        Open     High      Low    Close      Volume
Datetime
2025-11-14 09:30:00  220.50  220.75  220.45  220.60     1500000
2025-11-14 09:31:00  220.60  220.85  220.55  220.70     1200000
```

---

## GitHub Pages Benefits

✅ **Always Online** - 24/7 availability, no server maintenance
✅ **Fast** - Served via GitHub's global CDN
✅ **Free** - No hosting costs
✅ **Secure** - HTTPS by default
✅ **Simple** - Just push code, no configuration needed

You can use the chart viewer from anywhere with internet!

---

## Next Steps

Once your chart viewer is live:

1. **Mark some trades** to test the functionality
2. **Review analytics** to ensure calculations work
3. **Export data** to verify CSV generation
4. **Share the URL** with your team (if desired)

Happy trading! 📈
