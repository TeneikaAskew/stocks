# Trading Chart Viewer

Interactive web-based trading chart visualization tool for marking trade entries/exits and analyzing trading patterns.

## Features

### 📊 Chart Visualization
- **TradingView Lightweight Charts** - Professional candlestick charts
- **Multiple timeframes** - 1min, 5min, 15min, 30min, 1hour
- **Volume overlay** - Real-time volume display
- **Interactive crosshair** - Hover to see price/time details

### 📍 Trade Marking
- **Click-to-mark entries** - Mark CALL or PUT entries directly on the chart
- **Multiple TP levels** - Set up to 3 take-profit targets with position sizing
- **Stop loss tracking** - Define stop loss levels
- **Exit marking** - Mark exits with reason (TP1, TP2, TP3, SL, Manual)
- **Visual markers** - Color-coded markers and price lines

### 💾 Data Persistence
- **LocalStorage** - Auto-save trades in browser
- **Export to CSV** - Export all trades for Excel analysis
- **Export to JSON** - Export for custom analysis tools

### 📈 Analytics
- **Win rate tracking** - Overall and by ticker/option type
- **P&L analysis** - Total, average, max win/loss
- **Pattern recognition** - Identify successful setups by tags
- **Time-based insights** - Best trading hours analysis
- **Profit factor** - Risk/reward metrics

## Setup

### Option 1: Local Development with Python API

1. **Install dependencies:**
   ```bash
   cd chart-viewer
   pip install -r requirements.txt
   ```

2. **Start the API server:**
   ```bash
   python api.py
   ```
   The API will start on `http://localhost:5000`

3. **Open the chart viewer:**
   - Simply open `index.html` in your browser
   - Or use a local server:
     ```bash
     python -m http.server 8080
     ```
   - Navigate to `http://localhost:8080`

4. **Configure data source:**
   - Ensure `CONFIG.USE_LOCAL_API = true` in `src/config.js`

### Option 2: GitHub Pages (Static Hosting)

1. **Pre-convert data to JSON:**
   ```bash
   python scripts/convert_parquet_to_json.py
   ```
   This will create JSON files in `chart-viewer/data/`

2. **Update configuration:**
   - Set `CONFIG.USE_LOCAL_API = false` in `src/config.js`

3. **Deploy to GitHub Pages:**
   - Push the `chart-viewer` directory to your repository
   - Enable GitHub Pages in repository settings
   - Point to the `chart-viewer` folder

4. **Access online:**
   - Your chart will be available at `https://yourusername.github.io/stocks/chart-viewer/`
   - Works 24/7 with no server needed!

## Usage

### Marking Trades

1. **Select ticker and date** from the toolbar
2. **Click on a candle** to select entry/exit point
3. **Click "Mark Entry"** button
4. **Fill in trade details:**
   - Option type (CALL/PUT)
   - Entry price (auto-filled from click)
   - Take profit levels (TP1, TP2, TP3) with position sizes
   - Stop loss price
   - Notes and tags

5. **Click "Mark Exit"** when closing a position:
   - Select the trade to exit
   - Exit price (auto-filled)
   - Exit reason

### Analyzing Performance

1. **Switch to Analytics tab** to see:
   - Total trades, win rate, avg P&L
   - Call vs Put performance
   - Pattern insights
   - Best trading times

2. **Export data** for deeper analysis:
   - CSV format for Excel/Google Sheets
   - JSON format for custom tools

### Trade Data Structure

Each trade includes:
```json
{
  "id": "trade_1234567890_abc123",
  "ticker": "SPY",
  "optionType": "CALL",
  "entryTime": 1700000000,
  "entryPrice": 450.25,
  "exitTime": 1700003600,
  "exitPrice": 452.50,
  "exitReason": "TP1",
  "pnl": 2.25,
  "pnlPercent": 0.5,
  "status": "win",
  "takeProfits": [
    {"price": 452.50, "size": 0.5},
    {"price": 454.00, "size": 0.3},
    {"price": 455.00, "size": 0.2}
  ],
  "stopLoss": {"price": 449.00},
  "notes": "Volume spike, breakout pattern",
  "tags": ["0DTE", "momentum", "breakout"]
}
```

## Data Requirements

The application uses **AlphaVantage** minute-level OHLCV data in parquet format:

**Directory structure:**
```
data/
├── iwm/intraday/
│   ├── iwm_av_1min_202511.parquet   # Monthly files (Nov 2025)
│   ├── iwm_av_1min_202510.parquet   # Oct 2025
│   ├── iwm_av_1min_combined.parquet # All data combined
│   ├── iwm_av_1min_summary.json     # Metadata
│   └── ...
├── spy/intraday/
│   ├── spy_av_1min_202511.parquet
│   └── ...
└── qqq/intraday/
    ├── qqq_av_1min_202511.parquet
    └── ...
```

**Data Format:**
- **Filename:** `{ticker}_av_1min_{YYYYMM}.parquet`
- **Coverage:** Monthly files with full month of 1-minute bars
- **Timestamp index:** datetime
- **Columns:** open, high, low, close, volume (lowercase)

**Fetching AlphaVantage Data:**

See the scripts included in this repository:
```bash
# Fetch IWM data for last 5 years
python scripts/fetch_alphavantage_intraday.py --symbol IWM --years 5

# Fetch single month
python scripts/fetch_alphavantage_intraday.py --symbol IWM --month 2025-11
```

For complete documentation, see:
- `docs/alpha-vantage-quickstart.md`
- `docs/alpha-vantage-data-fetching.md`

## API Endpoints

### GET /api/health
Health check

### GET /api/tickers
List available tickers

### GET /api/dates/{ticker}
Get available dates for a ticker

**Response:**
```json
{
  "dates": ["20251114", "20251113", "20251112"]
}
```

### GET /api/data/{ticker}/{date}?timeframe=1
Get OHLCV data

**Parameters:**
- `timeframe` (optional): 1, 5, 15, 30, 60 minutes (default: 1)

**Response:**
```json
[
  {
    "time": 1700000000,
    "open": 450.25,
    "high": 450.50,
    "low": 450.00,
    "close": 450.30,
    "volume": 100000
  }
]
```

## Configuration

Edit `src/config.js` to customize:

```javascript
const CONFIG = {
    USE_LOCAL_API: true,  // Set false for GitHub Pages
    LOCAL_API_URL: 'http://localhost:5000/api',
    TICKERS: ['IWM', 'SPY', 'QQQ'],
    CHART: {
        // Chart styling options
    }
};
```

## Keyboard Shortcuts

- `E` - Mark Entry
- `X` - Mark Exit
- `S` - Save Trades
- `Tab` - Switch between Trades/Analytics

## Browser Compatibility

- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Edge 90+

## Performance

- Handles 5000+ candles smoothly
- Stores 1000+ trades in localStorage
- Chart renders in <100ms

## Troubleshooting

### Chart not loading
- Check browser console for errors
- Verify API is running (if using local API)
- Check data files exist in correct path

### Trades not saving
- Check localStorage is enabled
- Clear browser cache if issues persist
- Try exporting to CSV as backup

### Data not showing
- Verify parquet files in correct directory
- Check file naming: `{ticker}_minute_{YYYYMMDD}.parquet`
- Ensure pandas and pyarrow are installed

## Future Enhancements

- [ ] Real-time data integration
- [ ] Backtesting engine
- [ ] Pattern recognition ML models
- [ ] Multi-ticker comparison
- [ ] Trade journal integration
- [ ] Social sharing features
- [ ] Mobile app (React Native)

## Contributing

Found a bug or have a feature request? Please open an issue!

## License

MIT License - feel free to use for your trading!

---

**Note:** This tool is for educational and analysis purposes only. Always do your own research before making trading decisions.
