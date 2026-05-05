# Options Heatseeker

A powerful visual tool for analyzing dealer gamma positioning in the options market. Visualize dealer exposure, detect key support/resistance levels, and understand market dynamics through GEX/VEX analysis.

## Features

### Core Visualizations
- **Strike Price Heatmap**: Color-coded visualization of dealer gamma exposure by strike
  - Green to yellow gradient for positive exposure (low volatility zones)
  - Blue to purple gradient for negative exposure (high volatility zones)
  - Real-time current price indicator

- **Node Detection & Analysis**:
  - **King Nodes**: Highest absolute gamma levels - dealer settlement targets
  - **Gatekeepers**: Defensive positions blocking price movement
  - **Midpoints**: Trap zones with poor risk/reward ratios
  - **Hedge Nodes**: Far OTM positions for major event protection

- **GEX/VEX Metrics**:
  - Total Gamma Exposure (GEX) - Market pinning vs. trending indicator
  - Total Vanna Exposure (VEX) - Volatility change impact
  - Put/Call Ratio analysis
  - Market regime interpretation

### Interactive Features
- Multi-ticker support (IWM, QQQ, SPY)
- Date range selection with historical playback
- Expiration filtering (by DTE ranges)
- Strike range controls
- Hover tooltips with detailed Greeks
- Export to PNG and CSV

### Analytics
- Automatic node detection and classification
- Magnetic pull strength calculations
- Accumulation vs. dissipation patterns
- Map reshuffle alerts
- Confluence detection across multiple tickers

## Project Structure

```
options-heatseeker/
├── index.html              # Main application
├── css/
│   ├── styles.css          # Core styles
│   └── heatmap.css         # Heatmap-specific styles
├── js/
│   ├── config.js           # Configuration
│   ├── utils.js            # Utility functions
│   ├── dataLoader.js       # Data loading & caching
│   ├── greeksCalculator.js # GEX/VEX calculations
│   ├── nodeAnalyzer.js     # Node detection
│   ├── heatmapRenderer.js  # D3.js heatmap (TODO)
│   ├── chartRenderer.js    # Price chart (TODO)
│   ├── filterManager.js    # Filter controls
│   ├── tooltipManager.js   # Tooltip handling
│   ├── exportManager.js    # Export functionality
│   └── main.js             # Application entry point
├── data/                   # JSON options data
│   ├── index.json          # Date index
│   └── {ticker}/           # Per-ticker data
└── convert_parquet_to_json.py  # Data conversion script
```

## Setup

### 1. Convert Data

Convert parquet files to JSON for web consumption:

```bash
cd options-heatseeker
python convert_parquet_to_json.py --days 30
```

This will:
- Convert the most recent 30 days of options data to JSON
- Create an index file for quick date lookup
- Optimize JSON for web delivery

### 2. Serve Locally

Use any web server to serve the application:

```bash
# Python
python -m http.server 8000

# Node.js
npx http-server

# VSCode Live Server extension
# Right-click index.html → "Open with Live Server"
```

Navigate to `http://localhost:8000`

### 3. Deploy to GitHub Pages

1. Push the `options-heatseeker/` folder to your repository
2. Go to Settings → Pages
3. Set source to `main` branch, `/options-heatseeker` folder
4. Access at: `https://[username].github.io/stocks/options-heatseeker/`

## Usage

### Basic Navigation

1. **Select Ticker**: Choose IWM, QQQ, or SPY from the dropdown
2. **Select Date**: Pick a date from the date picker
3. **View Heatmap**: See dealer gamma exposure by strike
4. **Analyze Nodes**: Check the sidebar for key levels (King, Gatekeepers, Midpoints)

### Filters

- **DTE Range**: Filter by days to expiration (0-7, 7-30, 30-60, 60+)
- **Option Type**: View calls only, puts only, or both
- **Strike Range**: Set custom min/max strikes or auto-range
- **Value Format**: Display as dollar amounts or percentages

### Interpreting the Data

#### GEX (Gamma Exposure)
- **Positive GEX**: Market likely to pin/chop (low volatility)
- **Negative GEX**: Larger swings expected (high volatility)

#### VEX (Vanna Exposure)
- **Positive VEX**: Bullish if volatility drops
- **Negative VEX**: Bearish if volatility drops

#### Nodes
- **King Node** (Gold): Strongest magnetic level - dealer target
- **Gatekeeper** (Light Blue): Defensive positions - likely rejection zones
- **Midpoint** (Purple): Trap zones - worst risk/reward

### Best Practices

1. **Look for Confluence**: Compare levels across SPX/SPY/QQQ
2. **Watch for Reshuffles**: Significant changes indicate dealer repositioning
3. **Node Strength**: First touch is strongest (~100%), weakens with retests
4. **Combine with TA**: Use nodes to validate technical analysis levels
5. **Power Hour (3:30 PM EST)**: Watch for forced flows from retail brokers

## Data Requirements

The application expects JSON data in this format:

```json
{
  "ticker": "IWM",
  "date": "20251114",
  "snapshot_timestamp": "2025-11-14",
  "options": [
    {
      "contractID": "...",
      "symbol": "IWM",
      "type": "call",
      "strike": 210.0,
      "expiration": "2025-11-15",
      "open_interest": 1000,
      "volume": 50,
      "delta": 0.5,
      "gamma": 0.01,
      "theta": -0.05,
      "vega": 0.1,
      "bid": 2.0,
      "ask": 2.2,
      "last": 2.1,
      "mark": 2.1,
      "implied_volatility": 0.25
    }
  ]
}
```

## Development Roadmap

### Phase 1 (Completed)
- [x] Project structure and configuration
- [x] Data loading and caching system
- [x] Greeks calculations (GEX, VEX)
- [x] Node detection algorithm
- [x] Basic UI and filters
- [x] Data conversion pipeline

### Phase 2 (In Progress)
- [ ] D3.js heatmap visualization
- [ ] Interactive tooltips and drill-downs
- [ ] Price chart with level overlays
- [ ] Data tables (sortable, filterable)

### Phase 3 (Planned)
- [ ] Multi-ticker side-by-side view
- [ ] Confluence detection
- [ ] Historical playback animation
- [ ] Reshuffle detection and alerts
- [ ] Export to PNG

### Phase 4 (Future)
- [ ] Real-time data integration
- [ ] Alert system (email/push notifications)
- [ ] Custom indicator overlays
- [ ] Mobile optimization
- [ ] User preferences and saved views

## Technical Details

### Technology Stack
- **Frontend**: Pure JavaScript (ES6+), HTML5, CSS3
- **Visualization**: D3.js (v7)
- **Data Format**: JSON (converted from Parquet)
- **Deployment**: GitHub Pages (static site)

### Performance Optimizations
- Client-side data caching (IndexedDB)
- Lazy loading of date ranges
- Debounced filter updates
- Virtual scrolling for large datasets

### Browser Support
- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

## Credits

Inspired by options flow analysis tools and market microstructure research. Built for educational and research purposes.

## License

MIT License - See LICENSE file for details

## Contributing

This is part of a larger stocks/trading analysis project. For issues or feature requests, please open a GitHub issue.

---

**Disclaimer**: This tool is for educational purposes only. Options trading carries significant risk. Always do your own research and consult with a financial advisor before making trading decisions.
