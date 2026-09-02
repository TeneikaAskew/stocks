# IWM Trading Dashboard Website

This folder contains the web-based trading dashboard for monitoring IWM (iShares Russell 2000 ETF) with technical indicators and trade signals.

## Files

- `trading-dashboard.html` - Main dashboard application (working version)
- `trading-dashboard-broken.html` - Backup of previous version

## Features

- Real-time data updates via Polygon.io REST API (free tier)
- Technical indicators: EMA9/20/50, RSI, StochRSI, ATR, VWAP
- Call/Put signal detection with strength meters
- Audio alerts for trade signals
- Trade history tracking
- Customizable alert thresholds
- Extended hours support (9 AM - 9 PM ET)

## Usage

1. Open `trading-dashboard.html` in a web browser
2. Click ⚙️ Settings to configure your Polygon.io API key
3. Click 🔌 Connect to start fetching data
4. Monitor indicators and wait for trade signals

## API Requirements

- Polygon.io API key (free tier supported)
- Rate limit: 5 API calls per minute
- Data delay: 1-minute bars (not real-time on free tier)

## Browser Requirements

- Modern browser with JavaScript enabled
- Audio support for alerts
- LocalStorage for saving settings

## Notes

- The dashboard polls every 15 seconds to stay within rate limits
- Historical data is fetched every 2.5 minutes
- Volume calculations accumulate throughout the trading day
- Settings and trade history are saved locally