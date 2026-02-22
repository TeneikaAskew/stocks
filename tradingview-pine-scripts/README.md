# TradingView Pine Scripts Documentation

This directory contains custom TradingView Pine Script indicators for trading analysis and automation. All scripts are written in Pine Script v6.

## Table of Contents

- [Session Levels + ORB + Supertrend](#session-levels--orb--supertrend)
- [ORB 30 Alerts](#orb-30-alerts)
- [IWM Buy & Sell Volume Pressure (BSVP)](#iwm-buy--sell-volume-pressure-bsvp)
- [Scalping IWM](#scalping-iwm)
- [Performance Optimization](#performance-optimization)

---

## Session Levels + ORB + Supertrend

**File:** `session-levels-trends`

### Overview
A comprehensive multi-indicator script combining session levels, opening range breakout (ORB), and Supertrend indicators. This is the most feature-rich script in the collection.

### Features

#### 1. Session Levels
Displays key price levels from previous trading sessions:

- **Previous Day (PD)**: PDH (High), PDL (Low), PDC (Close)
- **Previous Week (PW)**: PWH (High), PWL (Low), PWC (Close)
- **Previous Month (PMO)**: PMOH (High), PMOL (Low), PMOC (Close)
- **Pre-Market (PmM)**: PmMH (High), PmML (Low)

Each level includes optional **50% midpoint levels** (dashed lines) that can be toggled on/off.

#### 2. Opening Range Breakout (ORB)
Tracks the opening range and identifies breakouts:

- **Two Modes**:
  - First Bar Only: Uses only the first bar of regular session
  - Time Period: Uses configurable duration (default 30 minutes)
- **Visual Elements**:
  - ORB High/Low lines (extend across entire chart)
  - Shaded box showing the opening range period
  - Breakout signals when price crosses ORB levels
  - Dynamic line colors (changes on breakout/breakdown)

#### 3. Supertrend
Trend-following indicator using ATR-based bands:

- **Components**:
  - Dynamic trend lines (green for uptrend, red for downtrend)
  - Buy/Sell signal markers
  - Background highlighting for trend direction
  - Configurable ATR period and multiplier

#### 4. Gap Zones
Tracks overnight gaps:

- Draws shaded box between previous close and current open
- Changes color when gap is filled
- Labels filled gaps on the chart

#### 5. Psychological Levels
Round number support/resistance levels:

- Automatically centers around current price
- Configurable step size (default $1.00)
- Configurable number of levels above/below (default 6)
- **Optimized**: Only recreates when price moves to new zone

### Configuration Options

#### Session Levels Settings
- Toggle each session level type on/off
- Enable/disable 50% midpoint levels
- Choose RTH-only or 24-hour data
- Customize pre-market and regular session times

#### Color Customization
- Independent colors for each level type
- Adjustable opacity for low lines
- Separate colors for breakout/breakdown states

#### ORB Settings
- ORB type selection (First Bar vs Time Period)
- Duration in minutes (for Time Period mode)
- Enable/disable breakout signals

#### Supertrend Settings
- ATR calculation method toggle
- ATR period and multiplier
- Buy/Sell signal display toggle
- Trend highlighting on/off

### Performance Optimizations

This script uses **advanced performance patterns** to minimize resource usage:

1. **Create-Once Pattern**: Lines are created once when values change, not updated every bar
2. **Change Detection**: Uses tracked variables to detect when values actually change
3. **Extend Both**: Lines extend in both directions to span entire chart
4. **Label Optimization**: Labels update only on last bar to stay positioned correctly
5. **Psychological Levels**: Array-based management, recreates only when price zone changes

### Line/Label Limits
- Maximum lines: 140
- Maximum boxes: 60
- Maximum labels: 140

### Use Cases
- Intraday trading: Use session levels for support/resistance
- Breakout trading: Monitor ORB breakouts with alerts
- Trend following: Use Supertrend for directional bias
- Gap trading: Track and trade gap fills

---

## ORB 30 Alerts

**File:** `orb-30`

### Overview
Multi-symbol Opening Range Breakout (ORB) scanner with automated alerts. Monitors a watchlist of symbols simultaneously and generates alerts when breakouts occur.

### Features

#### 1. Multi-Symbol Monitoring
- **Watchlist Support**: Monitor up to 100+ symbols simultaneously
- **Default Watchlist**: QQQ, SPY, IWM, GLD, MNQ1!, MES1!, M2K1!, MGC1!
- **Comma-Separated Input**: Easy customization via settings

#### 2. Multi-Session Support
Three pre-configured trading sessions (all in Eastern Time):

- **New York**: 9:30 AM - 4:00 PM (ORB: 9:30-10:00 AM)
- **London**: 3:00 AM - 11:30 AM (ORB: 3:00-3:30 AM)
- **Tokyo**: 8:00 PM - 5:00 AM next day (ORB: 8:00-8:30 PM)

#### 3. ORB Calculation
- **30-Minute Window**: First 30 minutes of selected session
- **High/Low/Mid Lines**: Visual reference levels
- **Target Profit (TP) Lines**:
  - 3 levels above ORB High
  - 3 levels below ORB Low
  - Configurable TP multiplier (default 0.5x ORB range)

#### 4. Alert System
- **Breakout Detection**: Monitors all symbols for ORB breakouts
- **Dual Alerts**:
  - High breakouts (buy signals)
  - Low breakdowns (sell signals)
- **Alert Aggregation**:
  - Groups multiple symbol alerts into single messages
  - Prevents alert spam
  - Shows all triggered symbols in one notification

#### 5. Visual Features
- **Lines**: ORB High, Low, Mid, and 6 TP levels
- **Labels**: Price levels with customizable text and emojis
- **Buy/Sell Markers**: Optional chart annotations
- **Debug Panel**: Mock alert display for testing

### Configuration Options

#### Watchlist Settings
- Custom symbol list (comma-separated)
- Automatic array sizing based on symbol count

#### Session Settings
- Choose between NY, London, or Tokyo
- Proper midnight-spanning logic for Tokyo session

#### Visual Customization
- Line styles: Solid, Dashed, or Dotted
- Independent colors for High, Low, Mid, and TP lines
- Label size: Tiny, Small, Normal, Large, Huge
- Custom buy/sell label text with emoji support

#### Alert Settings
- Toggle buy/sell labels on chart
- Debug mode for testing alerts
- Configurable TP fraction of ORB range

### Performance Features
- **Storage Arrays**: Efficient multi-symbol data management
- **Single Chart Rendering**: Only draws lines for current chart symbol
- **Label Persistence**: Creates labels once per session (not every bar)
- **Alert Tracking**: Prevents duplicate alerts per session

### Use Cases
- **Multi-Market Monitoring**: Track major indices and futures simultaneously
- **Session-Based Trading**: Trade specific market sessions (NY/London/Tokyo)
- **Breakout Trading**: Automated alerts for ORB breakouts across watchlist
- **Risk Management**: Pre-calculated TP levels for trade planning

---

## IWM Buy & Sell Volume Pressure (BSVP)

**File:** `iwm-bsvp`

### Overview
Advanced volume pressure indicator specifically designed for IWM (Russell 2000 ETF). Uses the Vadim Gimelfarb "Power-Balance" algorithm to analyze buying and selling pressure.

### Features

#### 1. Volume Pressure Calculation
Two calculation modes:

- **Raw Mode**: Direct volume data
  - Buy Pressure Volume (BPV)
  - Sell Pressure Volume (SPV)
  - Total Pressure Volume (TPV)

- **Normalized Mode** (Karthik Marar's version):
  - Filters noise from HFT and daily variations
  - Normalizes against EMAs and volume averages
  - More stable signals

#### 2. Visual Components

##### Main Histogram
- **Buy Pressure Bars**: Green bars above zero
- **Sell Pressure Bars**: Red bars below zero
- **Transparency Control**: Adjustable (0-100%)

##### Volume Pressure Oscillator (VPO)
- **VPO1 Line**: Fast-moving pressure indicator
- **VPO2 Signal Line**: Slower signal line
- **Convergence/Divergence**: Optional MACD-style oscillator

#### 3. Advanced Signals

##### Divergence Detection
- **Bullish Divergence**: Price makes lower low, VPO makes higher low
- **Bearish Divergence**: Price makes higher high, VPO makes lower high
- **Lookback Period**: Configurable (default 14 bars)

##### Trend Strength
- Background color intensity shows trend strength
- Based on VPO histogram magnitude

##### Momentum Acceleration
- Arrows showing acceleration in buying/selling pressure
- Detects when pressure is increasing rapidly

##### Entry Quality Score
- Rates potential entry points (1-5 stars)
- Combines multiple factors:
  - VPO divergence
  - RSI levels
  - Trend strength
  - Volume confirmation

#### 4. Signal Generation

##### Buy Signals (Green)
- VPO crosses above signal line
- Bullish divergence detected
- Strong buy pressure + volume confirmation
- RTH (Regular Trading Hours) validation

##### Sell Signals (Red)
- VPO crosses below signal line
- Bearish divergence detected
- Strong sell pressure + volume confirmation
- RTH validation

##### Neutral/Wait Signals (Gray)
- Conflicting indicators
- Low volume periods
- Extended hours (lower confidence)

#### 5. Data Quality Filtering
Automatically reduces signal confidence during:
- Extended hours (outside RTH)
- Low volume bars
- Narrow range bars
- Applies 0.5x quality multiplier to signals

### Configuration Options

#### Calculation Settings
- Fast MA period (default 3)
- Buy/Sell convergence lookback (default 27)
- Enable/disable VPO oscillator
- Choose cumulative vs oscillator mode
- Toggle normalized vs raw mode

#### Visual Settings
- Bar transparency control
- Show/hide info table
- Table position (4 corners)
- Signal icon display (💡)
- Tooltip detail level (Simple/Detailed/Expert)
- Show/hide signal labels

#### Advanced Signals
- Toggle divergence signals
- Toggle trend strength background
- Toggle momentum arrows
- Toggle entry quality scores
- Divergence lookback period

#### Session Settings
- RTH hours (default 9:30 AM - 4:00 PM ET)
- Override RTH for always-on labels

#### Color Customization
- Bullish/Buy color
- Bearish/Sell color
- Neutral/Wait color
- VPO1 and VPO2 line colors
- Histogram colors with transparency

### Use Cases
- **Scalping IWM**: Identify short-term pressure shifts
- **Volume Confirmation**: Validate price moves with volume analysis
- **Divergence Trading**: Catch trend reversals early
- **Entry Timing**: Use entry quality score to pick best setups
- **RTH Focus**: Avoid low-quality extended hours signals

---

## Scalping IWM

**File:** `iwm-scalping`

### Overview
Multi-timeframe scalping indicator for IWM with lane-based signal visualization. Displays multiple technical indicators as color-coded dots across horizontal lanes.

### Features

#### 1. Multi-Timeframe Analysis
Analyzes data across three timeframes:

- **Chart Timeframe**: Primary analysis
- **1-Minute**: Fast micro-trend detection
- **5-Minute**: Broader context and breakouts

#### 2. Indicator Lanes

##### CALL Indicators (Bullish - 📈 Green)
1. **Price Above EMA9**: Close > 9-period EMA
2. **Price Above EMA20**: Close > 20-period EMA
3. **Price Above VWAP**: Close > Volume-Weighted Average Price
4. **RSI Above 50**: RSI crossed bullish threshold
5. **RSI Above 60**: Strong bullish RSI
6. **Stochastic RSI Above 70**: Overbought momentum
7. **EMA9 Above EMA20**: Fast EMA crossed slow
8. **EMA20 Above EMA50**: Mid EMA above slow
9. **ATR High**: Volatility sufficient (≥ 0.15)
10. **5min Breakup**: 5-min close above previous 5-min high
11. **1min Reject Up**: 1-min wick rejection off EMA9/VWAP with bullish close

##### PUT Indicators (Bearish - 📉 Red)
1. **Price Below EMA9**: Close < 9-period EMA
2. **Price Below EMA20**: Close < 20-period EMA
3. **Price Below VWAP**: Close < VWAP
4. **RSI Below 50**: RSI crossed bearish threshold
5. **RSI Below 40**: Strong bearish RSI
6. **Stochastic RSI Below 30**: Oversold momentum
7. **EMA9 Below EMA20**: Fast EMA crossed below slow
8. **EMA20 Below EMA50**: Mid EMA below slow
9. **5min Breakdown**: 5-min close below previous 5-min low
10. **1min Reject Down**: 1-min wick rejection off EMA9/VWAP with bearish close

##### Universal Factors (⚡ Neutral)
1. **RVOL Normal**: Relative volume ≥ 1.0
2. **RVOL High**: Relative volume ≥ 1.5 (configurable)
3. **Time Window**: Inside RTH trading hours (9:35 AM - 2:30 PM ET)

#### 3. Signal Visualization
- **Lane System**: 27 horizontal lanes (one per indicator)
- **Dot Colors**:
  - Green: Bullish condition TRUE
  - Red: Bearish condition TRUE
  - Gray: Condition FALSE (if neutral dots enabled)
- **Tooltips**: Hover over dots for detailed information

#### 4. Configuration Options

##### Indicator Settings
- EMA Fast length (default 9)
- EMA Mid length (default 20)
- EMA Slow length (default 50)
- RVOL lookback period (default 50)
- RVOL minimum threshold (default 1.5)
- ATR minimum threshold (default 0.15)

##### Session Settings
- Trading window in ET (default 9:35 AM - 2:30 PM)
- Avoids first 5 minutes and last 30 minutes of RTH

##### Display Settings
- Show/hide tooltips on TRUE bars
- Show/hide neutral dots when conditions FALSE

### How to Use

#### Reading the Signals
1. **Strong CALL Setup**: Multiple green dots in CALL section + RVOL high + time window
2. **Strong PUT Setup**: Multiple red dots in PUT section + RVOL high + time window
3. **Confirmation**: Look for alignment across multiple indicators
4. **Volume Validation**: Ensure RVOL lanes are active (green)
5. **Time Filter**: Ensure time window lane is active

#### Trade Entry Criteria
**For Calls (Bullish Trades):**
- Minimum 6-7 green dots in CALL section
- RVOL High lane active (green)
- Time Window lane active (green)
- ATR High lane active (green)
- Bonus: 5min Breakup or 1min Reject Up

**For Puts (Bearish Trades):**
- Minimum 6-7 red dots in PUT section
- RVOL High lane active (green)
- Time Window lane active (green)
- Bonus: 5min Breakdown or 1min Reject Down

#### Avoiding False Signals
- Ignore signals outside time window (gray time lane)
- Require RVOL confirmation (at least RVOL Normal)
- Look for multi-timeframe alignment (5min and 1min signals)
- Avoid when ATR is low (insufficient volatility)

### Use Cases
- **Scalping**: Quick 0DTE options trades on IWM
- **Entry Confirmation**: Multi-factor validation before entry
- **Trend Alignment**: Ensure all timeframes agree
- **Volume Validation**: Confirm sufficient participation
- **Time-Based Trading**: Focus on high-probability hours

---

## Performance Optimization

### Line/Label Management
All scripts use efficient patterns to stay within TradingView limits:

#### Create-Once Pattern
```pinescript
// BAD: Creates new line every bar
if condition
    line.new(bar_index, price, bar_index, price, extend=extend.right, ...)

// GOOD: Creates once, only when needed
var line myLine = na
if changed or na(myLine)
    myLine := deleteLine(myLine)
    myLine := line.new(bar_index, price, bar_index + 1, price, extend=extend.both, ...)
```

#### Change Detection
```pinescript
var float prev_value = na
current_value = security("D", high[1])
valueChanged = current_value != prev_value

if valueChanged or na(myLine)
    // Recreate line
    prev_value := current_value
```

#### Label Updates
```pinescript
// Update labels only on last bar to stay on right edge
if barstate.islast
    label.delete(myLabel)
    myLabel := label.new(bar_index + 10, price, "Label Text", ...)
```

### Array Management
For multiple similar objects (e.g., psychological levels):

```pinescript
var array<line> psychLines = array.new<line>()

// Delete all old lines
if array.size(psychLines) > 0
    for i = 0 to array.size(psychLines) - 1
        line.delete(array.get(psychLines, i))
    array.clear(psychLines)

// Create new lines
for i = -6 to 6
    newLine = line.new(...)
    array.push(psychLines, newLine)
```

### Resource Limits
Be aware of TradingView limits:
- **Lines**: Typically 50-500 depending on indicator
- **Labels**: Typically 50-500 depending on indicator
- **Boxes**: Typically 50-500 depending on indicator

Optimize by:
1. Only creating objects when values change
2. Deleting old objects before creating new ones
3. Using `extend=extend.both` to span chart without multiple objects
4. Limiting array sizes to actual needs

---

## Installation

### TradingView
1. Open TradingView and navigate to Pine Editor
2. Copy the content of the desired script file
3. Paste into Pine Editor
4. Click "Add to Chart"
5. Configure settings via indicator settings panel

### File Organization
```
tradingview-pine-scripts/
├── README.md (this file)
├── session-levels-trends (comprehensive indicator)
├── orb-30 (multi-symbol ORB scanner)
├── iwm-bsvp (volume pressure analysis)
└── iwm-scalping (lane-based multi-indicator)
```

---

## Best Practices

### Combining Scripts
- **ORB + Session Levels**: Use together for complete intraday picture
- **BSVP + Scalping**: Volume confirmation + multi-factor entries
- **ORB 30 Alerts + BSVP**: Watchlist scanning + detailed analysis on specific symbols

### Chart Setup Recommendations
1. **Main Chart**: session-levels-trends (overlay=true)
2. **Lower Pane 1**: iwm-bsvp (volume analysis)
3. **Lower Pane 2**: iwm-scalping (signal lanes)
4. **Alerts**: orb-30 (for multi-symbol monitoring)

### Resource Management
- Don't run all scripts simultaneously on same chart
- Use separate charts for separate scripts
- Monitor script execution time in Pine Editor
- Disable unused features to improve performance

---

## Changelog

### Session Levels Script
- **v1.3**: Added psychological levels with optimized array management
- **v1.2**: Changed all lines to extend in both directions
- **v1.1**: Optimized line creation (create-once pattern)
- **v1.0**: Initial release with session levels, ORB, and Supertrend

### Other Scripts
- All scripts maintained at v6 Pine Script compatibility
- Regular updates for bug fixes and TradingView API changes

---

## Support & Contributing

### Issues
Report issues via GitHub Issues at: `https://github.com/TeneikaAskew/stocks/issues`

### Contributing
Contributions welcome! Please:
1. Test thoroughly on TradingView
2. Follow existing code style
3. Document all new features
4. Optimize for performance (line/label limits)

---

## License

These scripts are provided for personal trading use. Modify and distribute as needed, but please credit original authors where applicable.

---

## Disclaimer

These indicators are for educational and informational purposes only. Trading involves substantial risk of loss. Past performance does not guarantee future results. Always do your own research and consider consulting with a licensed financial advisor before making trading decisions.
