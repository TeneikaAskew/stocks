# IREN Dashboard - Quick Setup Guide

This guide will get you up and running in 5 minutes.

## Step 1: Install Python Dependencies

```bash
cd iren_app
pip install -r requirements.txt
```

**Dependencies installed:**
- Flask (web server)
- Flask-CORS (cross-origin support)
- Requests (HTTP library for Yahoo Finance)
- python-dotenv (environment variables)
- google-generativeai (Gemini AI SDK)

## Step 2: Get Your Gemini API Key

1. Visit: https://makersuite.google.com/app/apikey
2. Sign in with your Google account
3. Click **"Create API Key"**
4. Copy the key (starts with `AIza...`)

**Note**: Gemini offers a generous free tier:
- 60 requests per minute
- 1500 requests per day
- Perfect for this dashboard!

## Step 3: Configure Your API Key

Copy the example environment file:

```bash
cp .env.example .env
```

Or on Windows:
```powershell
copy .env.example .env
```

Edit `.env` and add your key:

```
GEMINI_API_KEY=AIzaSy...your_actual_key_here
```

**Important**: Never commit `.env` to git! It's already in `.gitignore`.

## Step 4: Start the Backend Server

```bash
python server.py
```

You should see:
```
Starting IREN Market Insights Server...
Gemini API configured: True
 * Running on http://127.0.0.1:5000
```

**Keep this terminal open!** The server must be running for the app to work.

## Step 5: Open the Frontend

### Option A: Direct File Open
Simply double-click `index.html` or open it in your browser.

### Option B: Local Server (Recommended)
Open a **new terminal** and run:

```bash
cd iren_app
python -m http.server 8000
```

Then visit: **http://localhost:8000**

## Step 6: Verify Everything Works

You should see:

1. ✅ **Price Data Loading** - Current IREN price appears
2. ✅ **Chart Rendering** - 90-day price chart displays
3. ✅ **AI Insights** - Three insights appear (Momentum, Volume, Volatility)
4. ✅ **AI Predictions** - Short-term and medium-term forecasts display
5. ✅ **Risk Assessment** - Risk level appears with detailed analysis

**Check Browser Console:**
- Press F12 to open Developer Tools
- Look for: "Data loaded successfully"
- No red errors should appear

**Check Server Terminal:**
- Should show request logs
- Should say "Gemini API configured: True"

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'flask'"

**Solution:**
```bash
pip install -r requirements.txt
```

### Issue: "Failed to fetch market data"

**Possible causes:**
1. Backend server not running → Start with `python server.py`
2. Wrong port → Ensure server is on port 5000
3. CORS issue → Use `http://localhost:8000` instead of `file://`

### Issue: "AI analysis unavailable"

**Possible causes:**
1. Missing API key → Check `.env` file exists and has `GEMINI_API_KEY`
2. Invalid API key → Verify key at https://makersuite.google.com/app/apikey
3. Rate limit exceeded → Wait 1 minute and refresh

### Issue: "GEMINI_API_KEY not found"

**Solution:**
```bash
# Verify .env file exists
ls -la .env  # Mac/Linux
dir .env     # Windows

# Verify it contains your key
cat .env     # Mac/Linux
type .env    # Windows

# Should show:
# GEMINI_API_KEY=AIzaSy...
```

### Issue: Chart not displaying

**Solution:**
1. Check internet connection (Chart.js loads from CDN)
2. Check browser console for errors
3. Verify historical_data is in API response

### Issue: Slow first load

**This is normal!**
- Yahoo Finance API: 2-5 seconds
- Gemini AI generation: 5-10 seconds
- Total first load: ~15 seconds

Subsequent refreshes use cached data and are faster.

## Testing the API Directly

Test backend without frontend:

```bash
# Health check
curl http://localhost:5000/api/health

# Get IREN data
curl http://localhost:5000/api/market-data/IREN
```

You should see JSON responses with data.

## Next Steps

### Customize for Other Stocks

Edit `app.js` line 28:
```javascript
const response = await fetch('http://localhost:5000/api/market-data/TSLA');
// Change IREN to any ticker: TSLA, AAPL, NVDA, etc.
```

### Adjust Refresh Rate

Edit `app.js` line 19:
```javascript
setInterval(() => this.refresh(), 60000);  // 1 minute instead of 5
```

### Modify AI Personality

Edit `server.py` prompts to change AI tone:
```python
prompt = f"""
You are a conservative financial analyst. Be cautious in predictions...
OR
You are an aggressive trader. Focus on momentum plays...
"""
```

## Development Tips

### Watch Server Logs
The server terminal shows:
- API requests from frontend
- Yahoo Finance API calls
- Gemini AI requests
- Any errors

### Browser Console
Press F12 and check:
- Network tab: See API calls
- Console tab: See JavaScript logs
- Elements tab: Inspect live data

### Testing Different Scenarios

Test with different stocks to see AI adapt:
- **High volatility**: TSLA, GME
- **Stable**: MSFT, JNJ
- **Different sectors**: XLE (energy), XLF (finance)

## Production Checklist

Before deploying to production:

- [ ] Use production WSGI server (gunicorn)
- [ ] Enable HTTPS
- [ ] Set up rate limiting
- [ ] Add caching layer
- [ ] Monitor API usage
- [ ] Set up error logging
- [ ] Use environment variables (not .env file)
- [ ] Add health check monitoring
- [ ] Configure CORS for specific domains only
- [ ] Add request validation

## Resources

- **Yahoo Finance API**: https://query1.finance.yahoo.com/v8/finance
- **Gemini API Docs**: https://ai.google.dev/docs
- **Chart.js Docs**: https://www.chartjs.org/docs/
- **Flask Docs**: https://flask.palletsprojects.com/

## Getting Help

If you're stuck:

1. **Check server terminal** - Look for error messages
2. **Check browser console** - Press F12 and look for errors
3. **Test API directly** - Use curl to test endpoints
4. **Verify API key** - Ensure it's valid and has quota
5. **Check network** - Ensure you can reach Yahoo Finance and Gemini

## Success! 🎉

If you see the dashboard with live data and AI-generated insights, you're all set!

The app will:
- Auto-refresh every 5 minutes
- Generate new AI insights on each refresh
- Update all metrics in real-time
- Provide intelligent trading predictions

**Happy Trading!** 📈

Remember: This is for educational purposes. Always do your own research before making investment decisions.
