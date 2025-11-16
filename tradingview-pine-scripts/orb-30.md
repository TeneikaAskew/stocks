# ORB 30 Alerts - Complete Guide

## Table of Contents
1. [Overview](#overview)
2. [What This Script Does](#what-this-script-does)
3. [How It Works](#how-it-works)
4. [Expected Outcomes](#expected-outcomes)
5. [How to Use](#how-to-use)
6. [Configuration Guide](#configuration-guide)
7. [Trading Strategies](#trading-strategies)
8. [Alert Setup](#alert-setup)
9. [Troubleshooting](#troubleshooting)

---

## Overview

**Script Name:** ORB 30 Alerts
**Version:** Pine Script v6
**Type:** Indicator (Overlay)
**Purpose:** Multi-symbol Opening Range Breakout scanner with automated alerts across global trading sessions

### Key Features
- ✅ Monitor up to 100+ symbols simultaneously
- ✅ Three global trading sessions (New York, London, Tokyo)
- ✅ Automated ORB calculation with 30-minute windows
- ✅ Target Profit (TP) levels automatically calculated
- ✅ Smart alert aggregation (prevents spam)
- ✅ Visual signals on chart for current symbol only
- ✅ Customizable watchlist via comma-separated input

---

## What This Script Does

### Core Functionality

#### 1. Multi-Symbol Watchlist Monitoring
Unlike most indicators that only track the current chart symbol, this script monitors an entire watchlist simultaneously.

**Default Watchlist:**
```
QQQ, SPY, IWM, GLD, MNQ1!, MES1!, M2K1!, MGC1!
```
- QQQ: Nasdaq 100 ETF
- SPY: S&P 500 ETF
- IWM: Russell 2000 ETF
- GLD: Gold ETF
- MNQ1!: Micro Nasdaq Futures
- MES1!: Micro S&P Futures
- M2K1!: Micro Russell Futures
- MGC1!: Micro Gold Futures

**How It Works:**
1. Script reads watchlist from comma-separated input
2. Creates arrays to store ORB data for each symbol
3. Fetches data for all symbols every bar using `request.security()`
4. Monitors all symbols for breakouts simultaneously
5. Triggers alerts when any symbol breaks its ORB

**Key Advantage:**
- One chart, many symbols monitored
- No need to create multiple alerts manually
- Catch opportunities across entire watchlist
- Ideal for traders managing multiple positions

#### 2. Global Session Support

The script supports three major trading sessions, all configured in Eastern Time (ET):

**New York Session:**
- ORB Window: 9:30 AM - 10:00 AM ET
- Full Session: 9:30 AM - 4:00 PM ET
- Best For: US stocks, ETFs, US futures

**London Session:**
- ORB Window: 3:00 AM - 3:30 AM ET
- Full Session: 3:00 AM - 11:30 AM ET
- Best For: European markets, Forex pairs, Gold

**Tokyo Session:**
- ORB Window: 8:00 PM - 8:30 PM ET
- Full Session: 8:00 PM - 5:00 AM ET (next day)
- Best For: Asian markets, Yen pairs, Nikkei

**Special Tokyo Logic:**
The Tokyo session spans midnight, requiring special handling:
```pinescript
tokyo_full_1 = "2000-2359"  // 8:00 PM to 11:59 PM
tokyo_full_2 = "0000-0500"  // 12:00 AM to 5:00 AM (next day)
```

#### 3. ORB Calculation

For each symbol in the watchlist, the script:

**During ORB Window (First 30 Minutes):**
1. Tracks the highest high
2. Tracks the lowest low
3. Stores these values in arrays

**After ORB Window:**
1. ORB levels are "captured" (locked in)
2. Monitors for price crossing these levels
3. Generates alerts on breakouts

**Example Calculation:**
```
Symbol: SPY
ORB Window: 9:30-10:00 AM

9:30 AM: Opens at $450.20
9:35 AM: High $450.50, Low $450.00
9:45 AM: High $450.80, Low $449.90
9:55 AM: High $451.00, Low $449.90
10:00 AM: ORB CAPTURED

ORB High: $451.00
ORB Low: $449.90
ORB Range: $1.10
ORB Mid: $450.45

TP Levels (0.5x multiplier):
TP1 High: $451.55 ($451.00 + $0.55)
TP2 High: $452.10 ($451.00 + $1.10)
TP3 High: $452.65 ($451.00 + $1.65)
TP1 Low: $449.35 ($449.90 - $0.55)
TP2 Low: $448.80 ($449.90 - $1.10)
TP3 Low: $448.25 ($449.90 - $1.65)
```

#### 4. Target Profit (TP) Levels

The script automatically calculates 3 TP levels above and below the ORB:

**Formula:**
```
ORB Range = ORB High - ORB Low
TP Increment = ORB Range × TP Multiplier

TP1 High = ORB High + (TP Increment × 1)
TP2 High = ORB High + (TP Increment × 2)
TP3 High = ORB High + (TP Increment × 3)

TP1 Low = ORB Low - (TP Increment × 1)
TP2 Low = ORB Low - (TP Increment × 2)
TP3 Low = ORB Low - (TP Increment × 3)
```

**Default TP Multiplier: 0.5**
- Conservative approach (TP levels = 50% of ORB range)
- Example: If ORB range is $1.00, each TP is $0.50 apart

**Adjustable TP Multiplier:**
- 0.25: Very tight TPs (quick profits, frequent fills)
- 0.50: Standard TPs (balanced)
- 0.75: Wider TPs (bigger targets, fewer fills)
- 1.00: Full ORB range per TP (aggressive)

#### 5. Alert System

**Breakout Detection:**
The script monitors for two types of breakouts:

**High Breakout (Buy Signal):**
```pinescript
// Triggered when:
close > orbHigh[i]              // Close above ORB High
close[1] <= orbHigh[i]          // Previous bar was below
not alertedHigh[i]              // Haven't alerted yet this session

// Action:
- Add symbol to buyList
- Set alertedHigh[i] = true (prevent duplicates)
- Generate alert message
```

**Low Breakdown (Sell Signal):**
```pinescript
// Triggered when:
close < orbLow[i]               // Close below ORB Low
close[1] >= orbLow[i]           // Previous bar was above
not alertedLow[i]               // Haven't alerted yet this session

// Action:
- Add symbol to sellList
- Set alertedLow[i] = true (prevent duplicates)
- Generate alert message
```

**Alert Aggregation:**
Instead of separate alert for each symbol, alerts are combined:

```
Individual Alerts (Bad):
"SPY ORB Buy Signal"
"QQQ ORB Buy Signal"
"IWM ORB Buy Signal"
→ 3 separate alerts = Spam!

Aggregated Alert (Good):
"ORB Buy: SPY, QQQ, IWM"
→ 1 alert with all symbols
```

#### 6. Visual Indicators (Chart Symbol Only)

The script only draws visual elements for the symbol currently on chart:

**Lines:**
- ORB High (green or user color)
- ORB Low (red or user color)
- ORB Mid (gray)
- TP1, TP2, TP3 High (blue, dashed)
- TP1, TP2, TP3 Low (blue, dashed)

**Labels:**
- "H" at ORB High
- "L" at ORB Low
- "M" at ORB Mid
- "T1", "T2", "T3" at TP levels

**Buy/Sell Markers (Optional):**
- Green label with custom emoji at breakout point
- Red label with custom emoji at breakdown point

**Debug Panel (Optional):**
- Shows mock alert display
- Lists symbols in Buy and Sell lists
- Useful for testing without real alerts

---

## How It Works

### Initialization Phase

**Step 1: Parse Watchlist**
```pinescript
symbols = str.split(watchlist, ",")
// Input: "QQQ,SPY,IWM,GLD"
// Output: ["QQQ", "SPY", "IWM", "GLD"]

num_symbols = array.size(symbols)
// Output: 4
```

**Step 2: Create Storage Arrays**
```pinescript
var float[] orbHighs = array.new_float(4, na)
// Stores ORB High for each symbol: [na, na, na, na]

var float[] orbLows = array.new_float(4, na)
// Stores ORB Low for each symbol: [na, na, na, na]

var bool[] orbCaptured = array.new_bool(4, false)
// Tracks if ORB is complete: [false, false, false, false]

var bool[] alertedHigh = array.new_bool(4, false)
// Tracks if High breakout alerted: [false, false, false, false]

var bool[] alertedLow = array.new_bool(4, false)
// Tracks if Low breakdown alerted: [false, false, false, false]
```

### ORB Capture Phase (9:30-10:00 AM for NY Session)

**Every Bar During ORB Window:**
```pinescript
for i = 0 to num_symbols - 1
    sym = array.get(symbols, i)

    // Fetch high/low for this symbol
    symHigh = request.security(sym, timeframe.period, high)
    symLow = request.security(sym, timeframe.period, low)

    // Update ORB High (track highest)
    currentORBHigh = array.get(orbHighs, i)
    if na(currentORBHigh) or symHigh > currentORBHigh
        array.set(orbHighs, i, symHigh)

    // Update ORB Low (track lowest)
    currentORBLow = array.get(orbLows, i)
    if na(currentORBLow) or symLow < currentORBLow
        array.set(orbLows, i, symLow)
```

**At End of ORB Window:**
```pinescript
for i = 0 to num_symbols - 1
    array.set(orbCaptured, i, true)
```

### Monitoring Phase (10:00 AM - 4:00 PM for NY Session)

**Every Bar After ORB:**
```pinescript
buyList := ""
sellList := ""

for i = 0 to num_symbols - 1
    if array.get(orbCaptured, i)
        sym = array.get(symbols, i)
        symClose = request.security(sym, timeframe.period, close)

        orbHi = array.get(orbHighs, i)
        orbLo = array.get(orbLows, i)

        // Check for High breakout
        if symClose > orbHi and not array.get(alertedHigh, i)
            buyList := buyList + sym + ","
            array.set(alertedHigh, i, true)

        // Check for Low breakdown
        if symClose < orbLo and not array.get(alertedLow, i)
            sellList := sellList + sym + ","
            array.set(alertedLow, i, true)

// Generate alerts if lists not empty
if buyList != ""
    alert("ORB Buy: " + buyList)

if sellList != ""
    alert("ORB Sell: " + sellList)
```

### Session End / Reset

**At Session End:**
```pinescript
if sessionJustEnded
    // Reset all arrays for next session
    for i = 0 to num_symbols - 1
        array.set(orbHighs, i, na)
        array.set(orbLows, i, na)
        array.set(orbCaptured, i, false)
        array.set(alertedHigh, i, false)
        array.set(alertedLow, i, false)

    // Clear alert lists
    buyList := ""
    sellList := ""
```

---

## Expected Outcomes

### Typical Trading Day (New York Session)

**9:00 AM:**
- Pre-market shows SPY at $450, up from $448 close
- Gap up scenario

**9:30 AM:**
- Session starts, ORB window begins
- Script starts tracking high/low for all symbols

**9:45 AM:**
- SPY: Range $450.20 - $451.50
- QQQ: Range $380.50 - $381.20
- IWM: Range $195.00 - $195.80
- Script continues updating

**10:00 AM:**
- ORB window ends, levels captured
- SPY ORB High: $451.50, Low: $450.20, Range: $1.30
- QQQ ORB High: $381.20, Low: $380.50, Range: $0.70
- IWM ORB High: $195.80, Low: $195.00, Range: $0.80

**10:15 AM:**
- SPY breaks $451.50 on close
- **ALERT**: "ORB Buy: SPY"
- Buy label appears on SPY chart (if viewing SPY)

**11:30 AM:**
- IWM breaks $195.80 on close
- **ALERT**: "ORB Buy: IWM"
- Buy label appears on IWM chart (if viewing IWM)

**2:00 PM:**
- QQQ drops below $380.50 on close
- **ALERT**: "ORB Sell: QQQ"
- Sell label appears on QQQ chart (if viewing QQQ)

**4:00 PM:**
- Session ends
- Script resets all tracking for tomorrow

### Multi-Breakout Scenario

**10:15 AM:**
- SPY, QQQ, and IWM all break ORB High simultaneously
- **ALERT**: "ORB Buy: SPY,QQQ,IWM"
- All three show buy signals
- Strong market-wide breakout

### False Breakout Scenario

**10:30 AM:**
- SPY touches $451.55 (briefly above ORB High $451.50)
- Bar closes at $451.40 (back below ORB High)
- **NO ALERT** (requires close beyond ORB High)
- Prevented false signal

**11:15 AM:**
- SPY closes at $451.60 (above ORB High)
- **ALERT**: "ORB Buy: SPY"
- True breakout confirmed

### Session-Specific Outcomes

**London Session (3:00-11:30 AM ET):**
- Good for: GLD, GC (Gold), EUR/USD
- Typically lower volatility
- Cleaner ORB breakouts
- Better follow-through

**Tokyo Session (8:00 PM - 5:00 AM ET):**
- Good for: NQ (Nasdaq Futures), ES (S&P Futures)
- Overnight positioning
- Gaps often form into NY open
- Lower volume, wider ranges

---

## How to Use

### Initial Setup

**Step 1: Add to Chart**
```
1. Open TradingView
2. Load any symbol from your watchlist (e.g., SPY)
3. Pine Editor → Paste script
4. Click "Add to Chart"
```

**Step 2: Configure Watchlist**
```
Settings → Watchlist Input:
"QQQ,SPY,IWM,AAPL,TSLA,NVDA,GLD,SLV"

Tips:
- No spaces after commas
- Use exact TradingView symbols
- Mix ETFs and stocks okay
- Can include futures (!  suffix)
```

**Step 3: Choose Session**
```
Settings → Trading Session:
- New York (for US stocks/ETFs)
- London (for GLD, Forex)
- Tokyo (for futures overnight)
```

**Step 4: Create Alerts**
```
Right-click chart → Add Alert
Condition: ORB 30 Alerts
Alert name: "ORB Breakouts"
Options:
☑ Once Per Bar Close
☑ Send Email
☑ Push Notification (mobile app)
☑ Play Sound
```

### Daily Trading Routine

**Example: Trading NY Session**

**8:00-9:25 AM:**
1. Review watchlist symbols pre-market
2. Note gaps, news, unusual movement
3. Identify which symbols likely to break ORB

**9:25-9:30 AM:**
4. Check alert is active
5. Ensure chart open (for visual reference)
6. Prepare trading platform

**9:30-10:00 AM:**
7. Watch ORB form
8. Note tight ranges (likely breakout) vs wide ranges (less likely)
9. Prepare orders near ORB levels

**10:00 AM:**
10. ORB captured
11. Place pending orders above/below ORB levels
12. Set stops on opposite ORB level

**10:00 AM - 12:00 PM:**
13. Monitor alerts
14. When alert triggers, check chart
15. Enter trade if setup confirmed
16. Use TP levels as targets

**12:00 PM - 4:00 PM:**
17. Manage open positions
18. Trail stops, scale out at TPs
19. Close any remaining before 3:50 PM

**4:00 PM:**
20. Review trades
21. Note which symbols had clean breakouts
22. Adjust watchlist if needed

### Using Multiple Sessions

**Global Coverage Strategy:**

**Tokyo Session (Night Watch):**
```
Watchlist: NQ1!, ES1!, YM1!, GC1!
Purpose: Overnight futures positioning
Alert: Phone notification
Action: Enter futures positions
```

**London Session (Early Morning):**
```
Watchlist: GLD, SLV, GC1!, SI1!, EUR/USD
Purpose: European open plays
Alert: Email notification
Action: Position for NY open continuation
```

**New York Session (Main Trading):**
```
Watchlist: SPY, QQQ, IWM, AAPL, TSLA, NVDA
Purpose: Primary day trading
Alert: Push notification + sound
Action: Active trading 10 AM - 2 PM
```

### Trade Execution

**Example Trade Flow:**

**Alert Received:**
```
10:15 AM: "ORB Buy: SPY,IWM"
```

**Step 1: Verify on Chart**
- Switch to SPY chart
- Confirm green buy label appeared
- Check TP levels are visible

**Step 2: Check Conditions**
- Volume increasing?
- Other indicators confirming? (if using additional)
- News/events clear?

**Step 3: Enter Trade**
```
Symbol: SPY
Entry: $451.60 (current price above ORB High $451.50)
Stop: $450.15 (below ORB Low $450.20)
Risk: $1.45

Position Size:
Account: $50,000
Risk: 1% = $500
Shares: $500 / $1.45 = 344 shares

Targets:
TP1: $452.15 (script shows TP1 High level)
TP2: $452.80 (script shows TP2 High level)
TP3: $453.45 (script shows TP3 High level)
```

**Step 4: Manage Trade**
```
11:00 AM: Price $452.20
Action: Close 33% at TP1 ($452.15)
        Move stop to breakeven ($451.60)

1:30 PM: Price $452.85
Action: Close 33% at TP2 ($452.80)
        Move stop to TP1 ($452.15)

3:00 PM: Price $453.50
Action: Close final 34% at TP3 ($453.45)
```

**Step 5: Repeat for IWM**
(Same process)

---

## Configuration Guide

### Watchlist Configuration

**Basic Watchlist (Beginner):**
```
"SPY,QQQ,IWM"
```
- 3 major index ETFs
- High liquidity
- Easier to manage

**Advanced Watchlist (Experienced):**
```
"SPY,QQQ,IWM,DIA,GLD,SLV,TLT,XLE,XLF,XLK"
```
- Index ETFs + sector ETFs
- Diversification
- More opportunities
- Requires faster decision-making

**Futures Watchlist:**
```
"MES1!,MNQ1!,M2K1!,MGC1!,MCL1!"
```
- Micro futures contracts
- Lower capital requirements
- 23-hour trading
- Use Tokyo or London sessions

**Stock Watchlist:**
```
"AAPL,TSLA,NVDA,GOOGL,AMZN,MSFT"
```
- High-volume stocks
- Use NY session only
- More volatile ORBs
- Bigger ranges

### Session Selection

**New York Session:**
```
Use For:
- US stocks (AAPL, TSLA, etc.)
- US ETFs (SPY, QQQ, IWM)
- US futures (ES, NQ, YM)

Characteristics:
- Highest volume
- Tightest spreads
- Most reliable breakouts
- 9:30 AM - 4:00 PM ET
```

**London Session:**
```
Use For:
- Gold/Silver (GLD, SLV, GC, SI)
- European stocks
- EUR currency pairs

Characteristics:
- Lower volume
- Wider initial ranges
- Good for commodities
- 3:00 AM - 11:30 AM ET
```

**Tokyo Session:**
```
Use For:
- Asian futures (Nikkei, Hang Seng)
- Currency pairs (JPY)
- Overnight futures positioning

Characteristics:
- Lowest volume (for US trader)
- Widest spreads
- Best for futures
- 8:00 PM - 5:00 AM ET
```

### TP Multiplier Settings

**0.25 (Conservative):**
```
ORB Range: $1.00
TP1: $0.25 away
TP2: $0.50 away
TP3: $0.75 away

Pros:
- Quick profit taking
- High fill rate
- Lower risk per trade

Cons:
- Miss big moves
- More trades needed
- Leave money on table
```

**0.50 (Standard):**
```
ORB Range: $1.00
TP1: $0.50 away
TP2: $1.00 away
TP3: $1.50 away

Pros:
- Balanced approach
- Good fill rate
- Captures extensions

Cons:
- May miss extremes
- Sometimes too tight
```

**1.0 (Aggressive):**
```
ORB Range: $1.00
TP1: $1.00 away (full range extension)
TP2: $2.00 away
TP3: $3.00 away

Pros:
- Catches big moves
- Lets winners run
- Better R:R

Cons:
- Lower fill rate
- May miss profits
- Requires patience
```

### Visual Customization

**Colors:**
```
ORB High Line: Green (bullish breakout expected)
ORB Low Line: Red (bearish breakdown expected)
ORB Mid Line: Gray (reference)
TP Lines: Blue (targets neutral)
```

**Line Styles:**
```
ORB Lines:
- Solid: Most visible
- Dashed: Less distracting
- Dotted: Subtle

TP Lines:
- Dashed (recommended): Differentiate from ORB
```

**Labels:**
```
Buy Label: "Buy🟢" (default)
Custom Options:
- "LONG ↑"
- "Call Entry"
- "Buy Setup"

Sell Label: "Sell🔴" (default)
Custom Options:
- "SHORT ↓"
- "Put Entry"
- "Sell Setup"

Label Size:
- Tiny: Subtle
- Small: Standard (recommended)
- Normal: Larger
```

### Debug Mode

**Enable Debug Panel:**
```
Show Mock-Alert Panel: ON

Displays:
- Current Buy List
- Current Sell List
- Symbols that broke ORB

Purpose:
- Test without real alerts
- Verify script working
- Check symbol names correct
```

---

## Trading Strategies

### Strategy 1: Pure ORB Breakout

**Entry Rules:**
1. Wait for alert: "ORB Buy: [SYMBOL]"
2. Verify on chart (visual confirmation)
3. Enter within 5 minutes of alert
4. Use market or limit order at current price

**Position Sizing:**
```
Risk per trade: 1%
Stop: Opposite ORB level
Entry: Current price after breakout

Example:
Account: $50,000
Risk: $500 (1%)
Entry: $451.60
Stop: $450.20
Risk per share: $1.40
Shares: $500 / $1.40 = 357
```

**Exit Rules:**
```
Scale out approach:
- 33% at TP1
- 33% at TP2
- 34% at TP3

Or:
- 50% at TP1
- 50% at TP2
- Let TP3 go (bonus target)
```

**Example:**
```
Symbol: SPY
Alert: 10:15 AM
Entry: $451.65
Stop: $450.15
Size: 350 shares

10:45 AM: TP1 hit ($452.25)
→ Sell 116 shares
→ Move stop to breakeven

12:30 PM: TP2 hit ($452.85)
→ Sell 117 shares
→ Move stop to TP1

2:15 PM: TP3 hit ($453.45)
→ Sell remaining 117 shares

Profit:
116 × ($452.25 - $451.65) = $69.60
117 × ($452.85 - $451.65) = $140.40
117 × ($453.45 - $451.65) = $210.60
Total: $420.60
```

### Strategy 2: Multiple Symbol Basket

**Concept:**
When multiple symbols break simultaneously, market-wide move likely.

**Entry Rules:**
1. Wait for alert with 3+ symbols
2. Enter ALL symbols that alerted
3. Equal weight each position
4. Same stops/targets for all

**Example:**
```
Alert: "ORB Buy: SPY,QQQ,IWM"

Allocate $3,000 total across 3 symbols
= $1,000 per symbol

SPY:
Entry: $451.60
Stop: $450.20
Risk: $1.40
Shares: $1,000 / $451.60 ≈ 2 shares
Actual risk: 2 × $1.40 = $2.80

QQQ:
Entry: $381.50
Stop: $380.50
Risk: $1.00
Shares: $1,000 / $381.50 ≈ 2 shares
Actual risk: 2 × $1.00 = $2.00

IWM:
Entry: $195.85
Stop: $195.00
Risk: $0.85
Shares: $1,000 / $195.85 ≈ 5 shares
Actual risk: 5 × $0.85 = $4.25

Total risk: $9.05 (0.018% of $50,000 account)
```

**Correlation Benefit:**
- If market moving up, all 3 likely to hit TP1
- Diversification across indices
- Lower individual position risk

### Strategy 3: ORB Fade (Contrarian)

**Concept:**
Fade (trade against) the ORB breakout.

**Entry Rules:**
1. Wait for ORB breakout alert
2. Wait 15-30 minutes
3. If price hasn't reached TP1, fade it
4. Enter opposite direction

**Example:**
```
10:15 AM: Alert "ORB Buy: SPY"
SPY breaks above $451.50

10:45 AM: SPY at $451.70 (only $0.20 follow-through)
TP1 is $452.25 (not reached)

Entry: $451.60 SHORT (fade the breakout)
Stop: $452.00 (above TP1)
Target: $451.00 (ORB Mid) or $450.20 (ORB Low)

Risk: $0.40
Reward: $0.60 to $1.40
R:R: 1.5:1 to 3.5:1
```

**When to Fade:**
- Low volume on breakout
- Price struggling to move
- Multiple failed breakouts same symbol
- End of day (3:00 PM+)

**When NOT to Fade:**
- High volume breakout
- Multiple symbols breaking same direction
- News catalyst
- Strong trend day

---

## Alert Setup

### Step-by-Step Alert Creation

**1. Create Alert:**
```
Right-click on chart
→ "Add Alert"
```

**2. Configure Condition:**
```
Condition: "ORB 30 Alerts"
(Should auto-populate with script name)
```

**3. Alert Message:**
```
Default: Uses script's built-in messages
"ORB Buy: SPY,QQQ,IWM"
"ORB Sell: GLD"

Custom (optional): Can add your own text
"⚡ORB BREAKOUT ⚡ {{ticker}} | {{interval}}"
```

**4. Settings:**
```
☑ Once Per Bar Close (important!)
☐ Only Once (do NOT check - need repeating alerts)

Expiration: Open-ended
(Or set to end at 4:00 PM if day trading only)
```

**5. Notifications:**
```
☑ Notify on App
☑ Send Email
☑ Play Sound

Email: your@email.com
Sound: Choose distinctive sound
```

**6. Save:**
```
Name: "ORB 30 - NY Session"
Create
```

### Alert Best Practices

**Separate Alerts by Session:**
```
Alert 1: "ORB 30 - NY Session"
Watchlist: SPY,QQQ,IWM,AAPL,TSLA

Alert 2: "ORB 30 - London Session"
Watchlist: GLD,SLV,GC1!

Alert 3: "ORB 30 - Tokyo Session"
Watchlist: NQ1!,ES1!,YM1!
```

**Time-Based Activation:**
```
For NY Session:
Activate: 9:25 AM
Deactivate: 4:05 PM

For London Session:
Activate: 2:55 AM
Deactivate: 11:35 AM

For Tokyo Session:
Activate: 7:55 PM
Deactivate: 5:05 AM
```

### Managing Alert Volume

**Problem:** Too many alerts overwhelming

**Solutions:**

**1. Reduce Watchlist:**
```
Instead of 20 symbols, use 5-10 best performers
Focus on most liquid
Remove symbols with low breakout frequency
```

**2. Use Debug Mode First:**
```
Enable "Show Mock-Alert Panel"
Watch for a week
Note which symbols alert most
Keep only active symbols
```

**3. Separate High/Low Priority:**
```
Priority Watchlist: SPY,QQQ,IWM
Secondary Watchlist: Stocks

Alert 1 (Priority): Push + Sound
Alert 2 (Secondary): Email only
```

---

## Troubleshooting

### Common Issues

**Issue 1: "No alerts triggering"**

**Check:**
1. Alert is active (not paused)
2. "Once Per Bar Close" is checked
3. Watchlist symbols spelled correctly
4. Currently in active session time
5. Market is open
6. Symbols actually breaking ORB

**Solution:**
```
Enable Debug Mode:
"Show Mock-Alert Panel" = ON

Watch the panel:
- Does it show symbols in Buy/Sell lists?
- If YES: Alert settings issue
- If NO: Symbols not breaking ORB (normal)
```

**Issue 2: "Too many alerts"**

**Likely Cause:**
Large watchlist + volatile day = many breakouts

**Solutions:**
```
1. Reduce watchlist size
2. Increase TP multiplier (make ORBs harder to break)
3. Add time filter (only alert 10 AM - 2 PM)
4. Use "Only Once" for whole day (not recommended)
```

**Issue 3: "Lines not showing on chart"**

**Cause:**
Lines only draw for current chart symbol

**Example:**
```
Your chart: AAPL
Your watchlist: SPY,QQQ,IWM

Result: No lines show (AAPL not in watchlist)

Solution: Add AAPL to watchlist
OR: Switch chart to SPY/QQQ/IWM
```

**Issue 4: "ORB levels seem wrong"**

**Check:**
1. Correct session selected
2. Using extended hours vs RTH data
3. Symbol has sufficient data
4. Session times match your timezone

**Example Issue:**
```
Your location: Pacific Time (PT)
Session setting: New York (ET)
ORB Window shows: 9:30-10:00 AM ET

On your chart (PT):
- Shows 6:30-7:00 AM (correct - time adjusted)

If levels wrong:
- May be using wrong session
- Check "Trading Session" setting
```

**Issue 5: "Futures symbols not working"**

**Check:**
1. Correct symbol format (ticker + "1!")
   - Correct: "ES1!", "NQ1!", "GC1!"
   - Wrong: "ES", "NQ", "GC"

2. Data feed includes futures
   - TradingView Free: Limited futures
   - Paid plans: Full futures access

3. Use extended session
   - Futures trade nearly 24 hours
   - Use Tokyo/London sessions for overnight

### Performance Issues

**Issue: "Script slow to load"**

**Causes:**
- Large watchlist (50+ symbols)
- Multiple `request.security()` calls
- Limited TradingView plan

**Solutions:**
```
1. Reduce watchlist to 10-20 symbols
2. Upgrade TradingView plan
3. Use separate alerts for separate watchlists
```

---

## Summary

### When to Use This Script

**Best For:**
- Multi-symbol monitoring
- ORB breakout trading
- Alert-based trading (not watching charts all day)
- Global session trading
- Systematic approach

**Not Ideal For:**
- Single symbol focus (use session-levels-trends instead)
- Scalping (too slow)
- Position trading (too short timeframe)
- Discretionary trading (too automated)

### Key Takeaways

1. **Efficiency**: Monitor many symbols with one alert
2. **Consistency**: Systematic ORB detection across watchlist
3. **Flexibility**: Works across global sessions
4. **Automation**: Set and forget (alerts handle monitoring)
5. **Scalability**: Easy to add/remove symbols

### Success Tips

1. Start with small watchlist (3-5 symbols)
2. Test with debug mode first
3. Keep TP multiplier at 0.5 initially
4. Use proper position sizing
5. Journal which symbols give best signals
6. Remove low-performers from watchlist monthly

---

**File:** `orb-30`
**Version:** Pine Script v6
**Last Updated:** 2025
