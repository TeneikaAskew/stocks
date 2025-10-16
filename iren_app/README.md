# IREN Market Insights Dashboard

A real-time web application providing comprehensive market insights, analysis, and **AI-powered predictions** for IREN Limited (Iris Energy). Powered by **Yahoo Finance API** for live market data and **Google Gemini AI** for intelligent analysis.

## Overview

This dashboard provides traders and investors with:
- **Real-time market data** from Yahoo Finance API
- **AI-generated insights** using Google Gemini's generative models
- **Intelligent predictions** for short-term (7-day) and medium-term (30-day) outlooks
- **Dynamic risk assessment** based on current market conditions
- Modern, responsive design with auto-refresh capabilities

## Key Technologies

- **Backend**: Python Flask REST API
- **Data Source**: Yahoo Finance API (`query1.finance.yahoo.com`)
- **AI Engine**: Google Gemini 1.5 Flash
- **Frontend**: Vanilla JavaScript with Chart.js
- **Styling**: Modern CSS with dark theme

## Architecture

### System Flow

```
User Browser
     ↓
Frontend (index.html + app.js)
     ↓ HTTP Request
Backend Server (server.py)
     ↓
  ┌──┴──┐
  ↓     ↓
Yahoo   Gemini
Finance  AI API
  API
```

## Quick Start

### 1. Install Dependencies

```bash
cd iren_app
pip install -r requirements.txt
```

### 2. Configure API Key

```bash
cp .env.example .env
# Edit .env and add your Gemini API key
```

Get your free Gemini API key: https://makersuite.google.com/app/apikey

### 3. Start Backend Server

```bash
python server.py
```

### 4. Open Frontend

Open `index.html` in your browser or use:

```bash
python -m http.server 8000
# Visit: http://localhost:8000
```

## Features

### Real-Time Market Data (Yahoo Finance)
- Current price with live updates
- Daily, 30-day, and 90-day performance
- Market cap, volume, and volume ratios
- 52-week ranges, Beta, P/E ratio
- Complete 90-day price history

### AI-Powered Analysis (Gemini)

#### Three Dynamic Insights
1. **Momentum Analysis** - AI evaluates price trends and strength
2. **Volume Activity** - Intelligent volume pattern detection
3. **Volatility Profile** - Risk assessment with context

#### Intelligent Predictions
1. **Short-Term (7 days)** - Direction, confidence, price targets
2. **Medium-Term (30 days)** - Outlook with volatility estimates
3. **Risk Assessment** - Multi-factor risk scoring and recommendations

## API Endpoints

### GET `/api/market-data/<symbol>`

Returns real-time data + AI analysis.

**Example:**
```bash
curl http://localhost:5000/api/market-data/IREN
```

**Response:**
```json
{
  "company": "IREN Limited",
  "current_price": 67.98,
  "daily_change": -2.27,
  "change_30d": 160.16,
  "change_90d": 278.93,
  "historical_data": [...],
  "insights": {
    "momentum_insight": "AI-generated analysis...",
    "volume_insight": "AI-generated analysis...",
    "volatility_insight": "AI-generated analysis..."
  },
  "predictions": {
    "short_term": {
      "direction": "🚀 Bullish Continuation",
      "confidence": 75,
      "prediction": "Detailed forecast..."
    },
    "medium_term": {...},
    "risk_assessment": {...}
  }
}
```

## File Structure

```
iren_app/
├── server.py              # Flask backend (Yahoo Finance + Gemini AI)
├── index.html             # Frontend structure
├── app.js                 # Frontend logic (API consumer)
├── styles.css             # Modern dark theme styling
├── requirements.txt       # Python dependencies
├── .env.example           # Environment template
├── .env                   # Your API keys (git-ignored)
├── .gitignore             # Git ignore rules
└── README.md              # This file
```

## How It Works

### Backend Process

1. **Receive Request** - Frontend requests data for IREN
2. **Fetch Market Data** - Query Yahoo Finance API for real-time data
3. **Calculate Metrics** - Process price changes, volumes, ranges
4. **Generate AI Prompts** - Create structured prompts with market context
5. **Get AI Analysis** - Send to Gemini for insights and predictions
6. **Return Response** - Combine all data and send to frontend

### Frontend Process

1. **Initialize** - Load dashboard on page load
2. **Fetch Data** - Call backend API endpoint
3. **Update UI** - Display all metrics and data
4. **Render Chart** - Create interactive price chart
5. **Show AI Content** - Display insights and predictions
6. **Auto-Refresh** - Repeat every 5 minutes

## Customization

### Change Stock Symbol

In `app.js`:
```javascript
const response = await fetch('http://localhost:5000/api/market-data/TSLA');
```

### Adjust Refresh Rate

In `app.js`:
```javascript
setInterval(() => this.refresh(), 60000);  // 1 minute
```

### Modify AI Prompts

In `server.py`, edit `generate_ai_insights()` or `generate_ai_predictions()`:

```python
prompt = f"""
Focus analysis on crypto mining sector...
Consider Bitcoin price correlation...
"""
```

### Change Data Range

In `server.py`:
```python
chart_data = fetch_yahoo_quote(symbol, interval='1d', range='6mo')
# Options: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, ytd, max
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Failed to fetch" | Ensure backend server is running on port 5000 |
| "AI unavailable" | Check `GEMINI_API_KEY` in `.env` file |
| CORS errors | Use `http://` not `file://` to open HTML |
| Chart not showing | Verify Chart.js CDN is accessible |
| Slow responses | Normal for AI generation (3-10 seconds) |

## Performance Tips

### Add Caching

```python
cache = {}
CACHE_DURATION = 60  # seconds

if symbol in cache and (time.time() - cache[symbol]['time']) < CACHE_DURATION:
    return cache[symbol]['data']
```

### Rate Limiting

```python
from flask_limiter import Limiter
limiter = Limiter(app)

@limiter.limit("10 per minute")
def get_market_data(symbol):
    # ...
```

## API Rate Limits

- **Yahoo Finance**: No official limit, recommended < 2000/hour
- **Gemini (Free)**: 60 requests/minute
- Use caching to minimize requests

## Production Deployment

### Use Production WSGI Server

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 server:app
```

### Environment Variables

Use platform-specific methods:
- **Heroku**: Config Vars
- **AWS**: Systems Manager
- **Docker**: docker-compose environment

### Enable HTTPS

Use reverse proxy (Nginx, Caddy, Apache)

## Future Enhancements

- Multi-stock support with dropdown selector
- Advanced technical indicators (RSI, MACD, Bollinger Bands)
- Real-time news feed with sentiment analysis
- Price/volume alerts via email/SMS
- Historical backtesting of AI predictions
- Social sentiment from Twitter/Reddit
- Multi-turn AI conversations about stocks

## Security Best Practices

1. Never commit `.env` file (use `.gitignore`)
2. Validate and sanitize all user input
3. Implement rate limiting to protect API keys
4. Use HTTPS in production
5. Monitor API usage and costs

## Browser Compatibility

- Chrome 90+ ✓
- Firefox 88+ ✓
- Safari 14+ ✓
- Edge 90+ ✓

## Disclaimer

This dashboard is for **informational and educational purposes only**. It does not constitute financial advice.

**Important:**
- AI predictions are based on historical patterns
- Past performance does not guarantee future results
- Market conditions can change rapidly
- Always conduct your own research
- Consult financial advisors for investment decisions
- Never invest more than you can afford to lose
- High volatility stocks carry significant risk

## Support

For issues:
1. Check browser console for frontend errors
2. Review server terminal for backend errors
3. Verify API keys are configured correctly
4. Ensure all dependencies are installed
5. Test API endpoint directly: `curl http://localhost:5000/api/health`

---

**Built with**: Python Flask, JavaScript, Chart.js, Yahoo Finance API, Google Gemini AI

**Last Updated**: October 15, 2025
