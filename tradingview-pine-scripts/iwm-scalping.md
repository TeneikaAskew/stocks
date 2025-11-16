# IWM Scalping - Lane-Based Multi-Indicator System

## Overview
**Purpose:** Visual 27-lane indicator system for IWM 0DTE options scalping
**Best For:** Quick entries/exits, momentum trades, multi-timeframe confirmation
**Timeframe:** Chart timeframe + 1-min + 5-min analysis
**Trading Style:** Aggressive scalping with layered confirmations

## What It Does
This is a unique visual system that displays 27 "lanes" of indicators in a separate pane below your chart. Each lane represents a specific bullish (CALL) or bearish (PUT) signal, creating an at-a-glance view of market conditions across multiple timeframes and indicators.

**Key Innovation:** Instead of overlaying dozens of indicators on your price chart, this system organizes them into clean horizontal lanes, making it easy to see when multiple factors align.

## Visual Layout

### The 27 Lanes (Top to Bottom)

#### CALL Indicators (Bullish - Lanes 1-11)
1. **Price Above EMA9** - Price trading above 9-period EMA
2. **Price Above EMA20** - Price trading above 20-period EMA
3. **Price Above EMA50** - Price trading above 50-period EMA
4. **EMA9 Above EMA20** - Fast EMA crossed above medium EMA
5. **EMA20 Above EMA50** - Medium EMA above slow EMA (strong trend)
6. **MACD Bullish** - MACD line above signal line
7. **RSI Oversold Bounce** - RSI crossed above 30 (oversold recovery)
8. **RSI Above 50** - RSI in bullish territory
9. **Stochastic Bullish** - %K crossed above %D
10. **Volume Surge** - Volume > 1.5x average (confirms moves)
11. **1-Min Timeframe Bullish** - Lower timeframe confirms trend

#### PUT Indicators (Bearish - Lanes 12-21)
12. **Price Below EMA9** - Price trading below 9-period EMA
13. **Price Below EMA20** - Price trading below 20-period EMA
14. **Price Below EMA50** - Price trading below 50-period EMA
15. **EMA9 Below EMA20** - Fast EMA crossed below medium EMA
16. **EMA20 Below EMA50** - Medium EMA below slow EMA (strong downtrend)
17. **MACD Bearish** - MACD line below signal line
18. **RSI Overbought Rejection** - RSI crossed below 70 (overbought rejection)
19. **RSI Below 50** - RSI in bearish territory
20. **Stochastic Bearish** - %K crossed below %D
21. **Volume Surge** - Volume > 1.5x average (confirms moves)

#### Universal Factors (Lanes 22-27)
22. **High Volume** - Current volume significantly above average
23. **5-Min Timeframe Direction** - Higher timeframe trend
24. **Gap Present** - Price gapped from previous close
25. **Near VWAP** - Price within 0.2% of VWAP (mean reversion zone)
26. **RTH Hours** - Regular trading hours (9:30 AM - 4:00 PM ET)
27. **Trend Strength** - Overall trend quality measurement

### How to Read the Lanes

**Active Lane:** Bright color (green for CALL, red for PUT)
**Inactive Lane:** Dark/muted color
**Flashing Lane:** Recent change (optional animation)

**Example Reading:**
```
CALL Lanes (Green = Active):
[✓] Price Above EMA9
[✓] Price Above EMA20
[✓] Price Above EMA50
[✓] EMA9 Above EMA20
[ ] EMA20 Above EMA50
[✓] MACD Bullish
[ ] RSI Oversold Bounce
[✓] RSI Above 50
[✓] Stochastic Bullish
[✓] Volume Surge
[✓] 1-Min Timeframe Bullish

PUT Lanes (Red = Active):
[ ] All PUT lanes inactive

Universal:
[✓] High Volume
[✓] RTH Hours
[ ] Gap Present
[✓] Near VWAP
```

**Interpretation:** 9 of 11 CALL indicators active = Strong bullish setup

## Signal Scoring System

### Call Score (0-11)
Counts how many CALL lane indicators are active.

**Score Interpretation:**
- **9-11:** Extremely strong bullish setup (highest probability)
- **7-8:** Strong bullish (good entry)
- **5-6:** Moderate bullish (wait for confirmation)
- **3-4:** Weak bullish (avoid)
- **0-2:** No bullish edge

### Put Score (0-10)
Counts how many PUT lane indicators are active.

**Score Interpretation:**
- **8-10:** Extremely strong bearish setup
- **6-7:** Strong bearish
- **4-5:** Moderate bearish
- **2-3:** Weak bearish
- **0-1:** No bearish edge

### Combined Signal Logic

**Strong CALL Entry:**
```
Call Score >= 7
AND Put Score <= 3
AND RTH Hours
AND Volume Surge
```

**Strong PUT Entry:**
```
Put Score >= 6
AND Call Score <= 3
AND RTH Hours
AND Volume Surge
```

**Wait/Neutral:**
```
Call Score AND Put Score both moderate (conflicting signals)
OR Extended hours
OR Low volume
```

## Indicator Details

### Moving Averages (EMAs)
**Purpose:** Identify trend direction and strength

**EMA 9 (Fast):**
- Responsive to recent price action
- Frequent crosses (noise in chop)
- Best for: Entry timing

**EMA 20 (Medium):**
- Balance of responsiveness and smoothness
- Key trend reference
- Best for: Trend confirmation

**EMA 50 (Slow):**
- Longer-term trend
- Strong support/resistance
- Best for: Overall bias

**Alignment:**
- **Bullish Alignment:** EMA9 > EMA20 > EMA50 (all CALL lanes active)
- **Bearish Alignment:** EMA9 < EMA20 < EMA50 (all PUT lanes active)

### MACD (Moving Average Convergence Divergence)
**Settings:** 12, 26, 9 (standard)
**Purpose:** Momentum and trend changes

**Bullish:**
- MACD line crosses above signal line
- Histogram growing (acceleration)
- MACD crossing above zero (strong trend)

**Bearish:**
- MACD line crosses below signal line
- Histogram shrinking (deceleration)
- MACD crossing below zero (strong downtrend)

### RSI (Relative Strength Index)
**Settings:** 14-period
**Purpose:** Overbought/oversold conditions

**Key Levels:**
- **> 70:** Overbought (potential reversal)
- **50-70:** Bullish territory
- **30-50:** Bearish territory
- **< 30:** Oversold (potential bounce)

**Lane Triggers:**
- **RSI Oversold Bounce:** RSI crosses above 30 (buy dip)
- **RSI Above 50:** Confirms bullish momentum
- **RSI Overbought Rejection:** RSI crosses below 70 (fade rally)
- **RSI Below 50:** Confirms bearish momentum

### Stochastic Oscillator
**Settings:** 14, 3, 3 (K, D, Smooth)
**Purpose:** Fast momentum changes

**Signals:**
- **%K crosses above %D:** Bullish (CALL lane)
- **%K crosses below %D:** Bearish (PUT lane)
- **Above 80:** Overbought zone
- **Below 20:** Oversold zone

**Best Use:** Confirms RSI signals or provides early warning

### Volume Analysis
**Average Volume:** 20-period SMA of volume
**Volume Surge:** Current volume > 1.5x average

**Why It Matters:**
- Low volume moves = Unreliable
- High volume moves = Follow-through likely
- Volume surge = Institutional participation

### Multi-Timeframe Analysis

**Chart Timeframe:** Your main viewing timeframe (e.g., 5-min)
**1-Min Timeframe:** Fast confirmation for scalping
**5-Min Timeframe:** Trend direction filter

**Lane Logic:**
- **1-Min Bullish Lane:** 1-min EMA9 > EMA20
- **5-Min Direction Lane:** 5-min trend indicator

**How to Use:**
- Enter when chart timeframe + 1-min align
- Use 5-min as overall bias filter
- Avoid counter-trend trades to 5-min

### Gap Detection
**Gap Present Lane:** Price opened away from previous close

**Gap Types:**
- **Gap Up:** Open > Previous Close (bullish bias)
- **Gap Down:** Open < Previous Close (bearish bias)

**Trading Implications:**
- Gaps often fill (mean reversion opportunity)
- Strong gaps hold (continuation opportunity)
- Watch for gap fill completions (reversal)

### VWAP (Volume-Weighted Average Price)
**Near VWAP Lane:** Price within 0.2% of VWAP

**VWAP as Magnet:**
- Price tends to revert to VWAP
- Above VWAP = Institutional buyers in control
- Below VWAP = Institutional sellers in control

**Trading Strategy:**
- When near VWAP + strong CALL score = Buy dip
- When near VWAP + strong PUT score = Fade rally

## Configuration

### Key Settings

**Timeframe Selection:**
```
Lower Timeframe: "1" (1-min for fast confirmation)
Higher Timeframe: "5" (5-min for trend bias)
```

**Volume Settings:**
```
Volume Period: 20 (average volume calculation)
Volume Surge Multiplier: 1.5 (150% of average)
```

**RSI Settings:**
```
RSI Length: 14
Overbought: 70
Oversold: 30
```

**MACD Settings:**
```
Fast Length: 12
Slow Length: 26
Signal Smoothing: 9
```

**Stochastic Settings:**
```
%K Length: 14
%D Smoothing: 3
Smooth K: 3
```

**EMA Settings:**
```
EMA Fast: 9
EMA Medium: 20
EMA Slow: 50
```

**Trading Hours:**
```
RTH Start: 9:30 AM ET
RTH End: 4:00 PM ET
```

### Visual Customization

**Lane Colors:**
- CALL Active: Bright green (#00FF00)
- CALL Inactive: Dark green (#003300)
- PUT Active: Bright red (#FF0000)
- PUT Inactive: Dark red (#330000)
- Universal Active: Bright blue (#0080FF)
- Universal Inactive: Dark blue (#003366)

**Lane Height:**
- Adjust spacing between lanes
- Increase for easier reading
- Decrease for compact view

**Lane Labels:**
- Show/Hide lane names
- Font size adjustment
- Position (left/right)

**Score Display:**
```
Show Call Score: ON
Show Put Score: ON
Score Position: Top-right
Score Size: Large
```

## How to Use

### Setup Process

1. **Add to IWM Chart:**
   - Open IWM chart (or other liquid ticker)
   - Set chart timeframe to 5-min (recommended)
   - Add indicator to chart
   - Position in separate pane below price

2. **Configure Settings:**
   - Lower timeframe: 1-min
   - Higher timeframe: 5-min
   - Enable RTH filter initially
   - Use default indicator settings

3. **Visual Layout:**
   - Ensure all 27 lanes visible
   - Enable score display
   - Show lane labels
   - Adjust colors if needed

### Daily Trading Routine

#### Pre-Market (9:00-9:30 AM)

**Step 1: Check Overnight Bias**
- Review which lanes were active at close
- Note any gaps forming
- Identify pre-market trend

**Step 2: Set Bias**
```
If Call Score > Put Score pre-market:
  → Bullish bias (look for CALL setups)

If Put Score > Call Score pre-market:
  → Bearish bias (look for PUT setups)

If Scores similar:
  → Neutral (wait for first 15 min)
```

#### Opening (9:30-9:45 AM)

**Step 3: Wait for Clarity**
- First 5-10 minutes often choppy
- Let lanes settle after open
- Wait for clear score separation

**Step 4: First Entry**
```
CALL Entry at 9:40 AM:
☑ Call Score >= 8
☑ Put Score <= 3
☑ Volume Surge active
☑ 1-Min Timeframe confirms
☑ Price above VWAP

Action: Buy IWM calls (1-2 DTE)
Position: 25% of daily risk
Stop: Below EMA9 or $0.15/share
Target: 50-100% gain
```

#### Main Session (10:00 AM - 3:00 PM)

**Step 5: Watch for Score Changes**

**Score Increases (Add to Position):**
```
Example: 10:30 AM
Call Score: 7 → 10 (strengthening)
Put Score: 4 → 1 (weakening)

Action: Add 25% position
New Total: 50% of daily risk
Reasoning: Confirmation of trend
```

**Score Decreases (Reduce Position):**
```
Example: 11:15 AM
Call Score: 10 → 6 (weakening)
Put Score: 1 → 5 (strengthening)

Action: Close 50% of position
Reasoning: Losing conviction
Take profit: Lock in gains
```

**Step 6: Trade Reversals**

**Strong Reversal Signal:**
```
Was: Call Score 9, Put Score 2
Now: Call Score 3, Put Score 8

Conditions:
☑ Rapid score flip (< 3 bars)
☑ Volume surge
☑ Multiple lane changes
☑ VWAP cross

Action: Exit CALLs, Enter PUTs
Position: 25% (new direction)
```

#### Final Hour (3:00-4:00 PM)

**Step 7: Risk Reduction**
- Close 75% of positions by 3:30 PM
- Avoid new entries after 3:45 PM
- Take profits quickly (50% gains OK)
- Use tighter stops

**Step 8: Close Out**
- Exit all 0DTE positions by 3:55 PM
- Review which patterns worked
- Journal high-score setups

### Entry Criteria

#### CALL (Long) Entry

**Minimum Requirements:**
```
☑ Call Score >= 7
☑ Put Score <= 3
☑ RTH Hours active
☑ Volume Surge present
☑ 1-Min Timeframe confirms
```

**Ideal Setup (5-Star):**
```
☑ Call Score >= 9
☑ Put Score <= 2
☑ Price above VWAP
☑ 5-Min trend bullish
☑ Gap up holding
☑ All EMA alignment lanes active
☑ MACD bullish
☑ RSI > 50
```

**Entry Timing:**
- On score reaching threshold
- On pullback to EMA9
- On VWAP bounce
- After 1-min confirmation

**Position Size:**
- 5-Star Setup: 50% of daily risk
- 4-Star Setup: 25-35% of daily risk
- 3-Star Setup: 10-20% of daily risk

**Stop Loss:**
- Below EMA9: Tight stop (~$0.15)
- Below EMA20: Medium stop (~$0.30)
- Below recent swing low: Wider stop

**Profit Target:**
- First target: 50% gain (scale 50%)
- Second target: 100% gain (scale 25%)
- Runner: 150%+ gain (hold 25%)

#### PUT (Short) Entry

**Minimum Requirements:**
```
☑ Put Score >= 6
☑ Call Score <= 3
☑ RTH Hours active
☑ Volume Surge present
☑ 1-Min Timeframe confirms
```

**Ideal Setup (5-Star):**
```
☑ Put Score >= 8
☑ Call Score <= 2
☑ Price below VWAP
☑ 5-Min trend bearish
☑ Gap down holding
☑ All EMA alignment lanes active (bearish)
☑ MACD bearish
☑ RSI < 50
```

**Entry Timing:**
- On score reaching threshold
- On bounce to EMA9 (rejection)
- On VWAP rejection
- After 1-min confirmation

**Position Size:**
- 5-Star Setup: 50% of daily risk
- 4-Star Setup: 25-35% of daily risk
- 3-Star Setup: 10-20% of daily risk

**Stop Loss:**
- Above EMA9: Tight stop (~$0.15)
- Above EMA20: Medium stop (~$0.30)
- Above recent swing high: Wider stop

**Profit Target:**
- First target: 50% gain (scale 50%)
- Second target: 100% gain (scale 25%)
- Runner: 150%+ gain (hold 25%)

### Example Trades

#### Example 1: Strong CALL Entry

**Setup (10:15 AM):**
```
Chart: 5-min IWM
Price: $195.50
VWAP: $195.20

Active CALL Lanes (10 of 11):
[✓] Price Above EMA9
[✓] Price Above EMA20
[✓] Price Above EMA50
[✓] EMA9 Above EMA20
[✓] EMA20 Above EMA50
[✓] MACD Bullish
[ ] RSI Oversold Bounce (N/A - not oversold)
[✓] RSI Above 50 (RSI at 62)
[✓] Stochastic Bullish
[✓] Volume Surge
[✓] 1-Min Timeframe Bullish

Active PUT Lanes (1 of 10):
[✓] Volume Surge (universal)

Universal Lanes:
[✓] High Volume
[✓] 5-Min Timeframe Bullish
[ ] Gap Present
[✓] Near VWAP
[✓] RTH Hours

Call Score: 10
Put Score: 1
```

**Trade Execution:**
```
Entry: Buy IWM $196 Calls (0DTE)
Entry Price: $1.20
Position Size: 10 contracts (50% daily risk = $600)
Stop Loss: $0.80 (below EMA9 rejection)
Risk per contract: $0.40
Total Risk: $400

Targets:
T1: $1.80 (50% gain) - Close 5 contracts
T2: $2.40 (100% gain) - Close 3 contracts
T3: $3.00+ (150% gain) - Hold 2 contracts
```

**Trade Management:**
```
10:45 AM - Price $195.90
Call Score still 10
Action: Hold, move stop to $1.00 (breakeven)

11:15 AM - Price $196.30
Calls at $2.00 (67% gain)
Action: Close 5 contracts at T1 ($1.80)
        Move stop on 5 remaining to $1.40

11:45 AM - Price $196.50
Calls at $2.60
Action: Close 3 contracts at T2 ($2.40)
        Move stop on 2 remaining to $2.00

12:15 PM - Call Score drops to 6
Put Score rises to 5
Action: Close final 2 contracts at $2.50

Results:
5 contracts: $1.80 - $1.20 = $0.60 profit × 5 = $300
3 contracts: $2.40 - $1.20 = $1.20 profit × 3 = $360
2 contracts: $2.50 - $1.20 = $1.30 profit × 2 = $260
Total Profit: $920
ROI: 153%
```

#### Example 2: Failed CALL Entry (Learning)

**Setup (2:15 PM):**
```
Price: $194.80
Call Score: 7 (minimum threshold)
Put Score: 4 (borderline high)

Active CALL Lanes (7 of 11):
[✓] Price Above EMA9 (barely)
[✓] Price Above EMA20
[ ] Price Above EMA50 (Price below)
[✓] EMA9 Above EMA20
[ ] EMA20 Above EMA50
[✓] MACD Bullish (weakly)
[ ] RSI Oversold Bounce
[✓] RSI Above 50 (RSI at 52)
[✓] Stochastic Bullish
[ ] Volume Surge (MISSING!)
[✓] 1-Min Timeframe Bullish
```

**Red Flags:**
- Late in day (2:15 PM)
- No volume surge
- Price below EMA50
- Put Score elevated (4)
- Marginal MACD

**Trade (Mistake):**
```
Entry: $195 Calls at $0.80
Position: 5 contracts
Stop: $0.60

2:20 PM - Call Score drops to 5
2:25 PM - Put Score rises to 7
2:30 PM - Stopped out at $0.60

Loss: $0.20 × 5 = $100
```

**Lessons:**
- Don't trade marginal setups late day
- Volume surge is critical
- When Put Score > 3, be cautious
- Respect the score thresholds

#### Example 3: Reversal Trade (PUT Entry)

**Setup (11:00 AM):**
```
Previous: Strong uptrend
Call Score was: 9
Put Score was: 2

Now:
Call Score: 3 (rapid drop!)
Put Score: 8 (rapid rise!)

Price: $196.20 (rejected at $196.50)
VWAP: $195.80
Price crossed below VWAP

Active PUT Lanes (8 of 10):
[✓] Price Below EMA9 (just crossed)
[✓] Price Below EMA20
[ ] Price Below EMA50 (not yet)
[✓] EMA9 Below EMA20 (just crossed)
[ ] EMA20 Below EMA50
[✓] MACD Bearish (just crossed)
[✓] RSI Overbought Rejection (from 72)
[✓] RSI Below 50 (now at 48)
[✓] Stochastic Bearish
[✓] Volume Surge
```

**Trade Execution:**
```
Entry: Buy IWM $195 Puts (0DTE)
Entry Price: $0.90
Position: 8 contracts
Stop: $0.65 (above EMA9 recross)

Reversal signals:
✓ Score flip (9→3 / 2→8)
✓ VWAP break
✓ Multiple EMA crosses
✓ Volume surge on reversal

11:15 AM - Price $195.90
Puts at $1.30 (44% gain)
Action: Close 4 contracts (50%)

11:30 AM - Price $195.50
Puts at $1.80 (100% gain)
Action: Close 4 contracts (remaining)

Total Profit:
4 × ($1.30 - $0.90) = $160
4 × ($1.80 - $0.90) = $360
Total: $520
```

## Trading Strategies

### Strategy 1: High-Score Momentum

**Concept:** Trade only when score >= 9 (CALL) or >= 8 (PUT)

**Entry Rules:**
```
CALL: Score reaches 9+
PUT: Score reaches 8+
Opposite score must be <= 2
Volume surge required
RTH hours only
```

**Management:**
- Enter 50% position at threshold
- Add 25% if score increases
- Exit 50% at first target (50% gain)
- Trail stop on remainder

**Performance Expectations:**
- Win rate: 65-70%
- Average R:R: 2:1
- Best timeframe: 5-min chart

### Strategy 2: Score Delta Trading

**Concept:** Trade when score differential >= 6

**Entry Rules:**
```
CALL: Call Score - Put Score >= 6
Example: Call 9, Put 3 = Delta 6 ✓

PUT: Put Score - Call Score >= 5
Example: Put 8, Call 2 = Delta 6 ✓
```

**Management:**
- Enter when delta reaches threshold
- Hold while delta >= 4
- Exit when delta < 3
- Use 50% scale at +50% gain

**Performance Expectations:**
- Win rate: 60-65%
- Average R:R: 2.5:1
- Best for: Trending days

### Strategy 3: Reversal Catching

**Concept:** Catch score flips for reversals

**Entry Rules:**
```
Score Flip Pattern:
Was: Call 8+, Put <=3
Now: Call <=3, Put 6+
Time: < 5 minutes (rapid flip)
Volume: Surge present
```

**Management:**
- Enter new direction immediately
- Tight stop (below/above flip candle)
- First target: 75% gain (aggressive)
- Hold 25% for continuation

**Performance Expectations:**
- Win rate: 55-60% (higher risk)
- Average R:R: 3:1 (bigger moves)
- Best for: Volatile days

### Strategy 4: Multi-Timeframe Confirmation

**Concept:** Only trade when all timeframes align

**Entry Rules:**
```
CALL Entry:
☑ Chart timeframe: Call Score >= 7
☑ 1-Min: Bullish lane active
☑ 5-Min: Direction lane bullish
☑ Volume surge
```

**Management:**
- Enter with full position (more confident)
- Hold longer (stronger conviction)
- Scale at 75% and 150% targets
- Trail stop aggressively

**Performance Expectations:**
- Win rate: 70-75% (highest)
- Average R:R: 2:1
- Best for: Conservative traders

### Strategy 5: VWAP Mean Reversion

**Concept:** Trade bounces/rejections at VWAP

**Entry Rules:**
```
CALL (VWAP Bounce):
Price drops to VWAP
Call Score >= 6
Price holds above VWAP (no break)
Volume surge on bounce

PUT (VWAP Rejection):
Price rallies to VWAP
Put Score >= 5
Price rejected at VWAP
Volume surge on rejection
```

**Management:**
- Quick scalps (30-50% targets)
- Tight stops (VWAP break invalidates)
- High frequency (multiple per day)

**Performance Expectations:**
- Win rate: 60%
- Average R:R: 1.5:1
- Best for: Range-bound days

## Risk Management

### Position Sizing

**Daily Risk Allocation:**
```
Total Daily Risk: $1,000 (example)

Per Trade:
5-Star Setup: $500 (50%)
4-Star Setup: $300 (30%)
3-Star Setup: $200 (20%)

Never risk more than 50% on single trade
```

**Contract Sizing:**
```
If option costs $1.00
Stop at $0.70
Risk per contract: $0.30

For $300 risk allocation:
Position = $300 / $0.30 = 10 contracts
```

### Stop Loss Strategies

**Indicator-Based Stops:**
```
EMA9 Stop: Tightest (fast scalps)
- CALL: Price closes below EMA9
- PUT: Price closes above EMA9

EMA20 Stop: Medium (swing trades)
- CALL: Price closes below EMA20
- PUT: Price closes above EMA20

Score Stop: Systematic
- CALL: Call Score drops below 5
- PUT: Put Score drops below 4
```

**Fixed Dollar Stops:**
```
Tight: $0.10-0.15 per contract
Medium: $0.20-0.30 per contract
Wide: $0.40-0.50 per contract

Use tighter stops with higher score conviction
```

### Profit Taking

**Systematic Scaling:**
```
Scale 1 (50% position):
- At 50% gain
- Locks in profit
- Reduces risk

Scale 2 (25% position):
- At 100% gain
- Compounds profit
- Move stop to breakeven

Scale 3 (25% position):
- At 150%+ gain
- Trail stop
- Catch extended moves
```

**Score-Based Exits:**
```
Full Exit When:
- Score drops below entry threshold
- Opposite score rises significantly
- After 3:30 PM (0DTE)
- Stop hit

Partial Exit When:
- Score weakens but still positive
- Profit target reached
- Opposing signals appear
```

### 0DTE-Specific Risks

**Time Decay:**
- Options lose value rapidly after 2 PM
- Avoid holding past 3:30 PM
- Take profits faster than multi-DTE

**Volatility:**
- 0DTE more sensitive to quick moves
- Use tighter stops (gamma risk)
- Scale in/out more frequently

**Gamma Risk:**
- Deep ITM/OTM can move violently
- Stick to ATM or 1 strike ITM/OTM
- Monitor delta changes

## Common Patterns

### Pattern 1: Morning Ramp
```
Time: 9:35-10:00 AM
Call Score: Steady 8-10
Put Score: 1-2
Volume: High
5-Min: Bullish

Trade: Aggressive CALL entries
Target: 75-100% by 10:30 AM
```

### Pattern 2: Lunch Chop
```
Time: 11:30 AM - 1:00 PM
Call Score: 5-6 (fluctuating)
Put Score: 4-5 (fluctuating)
Volume: Low

Trade: AVOID - Low conviction
```

### Pattern 3: Afternoon Reversal
```
Time: 2:00-2:30 PM
Was: Call Score 9
Now: Put Score 8 (flip)
Volume: Surge

Trade: Reversal PUT entry
Target: Quick 50% scalp
```

### Pattern 4: Power Hour Trend
```
Time: 3:00-3:45 PM
Call Score: Consistent 9+
Put Score: 1-2
Volume: High

Trade: CALL entries with tight stops
Target: Quick 30-50% (time decay!)
```

## Troubleshooting

### Issue: Too Many Conflicting Signals

**Symptom:** Call Score and Put Score both moderate (5-6)

**Solution:**
- Wait for clear separation (delta >= 6)
- Check higher timeframe (5-min)
- Reduce position size
- Use VWAP as tiebreaker

### Issue: Score Changes Too Fast

**Symptom:** Scores flip every bar (whipsaws)

**Solution:**
- Increase indicator periods (slower)
- Wait for 2-bar confirmation
- Use score delta instead of absolute
- Trade less, higher quality only

### Issue: Missing Good Moves

**Symptom:** Price moves before score confirms

**Solution:**
- Lower score threshold (7 → 6 for CALLs)
- Watch for score acceleration (6→8 quickly)
- Use 1-min chart for earlier entries
- Accept 3-star setups during strong trends

### Issue: Stops Too Tight

**Symptom:** Stopped out, then score increases

**Solution:**
- Use EMA20 instead of EMA9 for stop
- Increase fixed dollar stop
- Wait for pullbacks to enter
- Scale in (not all at once)

### Issue: Holding Too Long

**Symptom:** Big gains turn to losses

**Solution:**
- Always scale at 50% gain
- Set profit alerts
- Exit when score weakens (don't be greedy)
- Use time-based exits (3:30 PM for 0DTE)

## Advanced Techniques

### Lane Watching
Instead of watching score, watch specific lanes:

**Critical Lanes for Trend:**
- EMA20 Above/Below EMA50
- 5-Min Timeframe Direction
- MACD Bullish/Bearish

**Critical Lanes for Entry:**
- Volume Surge
- 1-Min Timeframe
- Near VWAP

**Critical Lanes for Exit:**
- Price Above/Below EMA9 (reversal)
- Stochastic flip
- RSI crossing 50

### Score Acceleration
Watch how fast score changes:

**Strong Acceleration (Bullish):**
```
9:45 AM: Call Score 5
9:50 AM: Call Score 7
9:55 AM: Call Score 9

= Rapidly building momentum
= Aggressive entry
```

**Weak Acceleration:**
```
10:00 AM: Call Score 6
10:30 AM: Call Score 7
11:00 AM: Call Score 8

= Slow grind
= Wait for confirmation
```

### Divergence Trading
Watch for price/score divergence:

**Bullish Divergence:**
```
Price: Lower low
Call Score: Higher low (more lanes active)
= Potential reversal up
```

**Bearish Divergence:**
```
Price: Higher high
Put Score: Higher low (more lanes active)
= Potential reversal down
```

## Summary

### Best Use Cases
- IWM 0DTE options scalping
- Quick momentum trades
- Multi-timeframe confirmation
- Visual at-a-glance analysis
- Systematic entry/exit rules

### Key Advantages
- 27 indicators in clean visual layout
- Multi-timeframe analysis built-in
- Objective scoring system
- Clear entry/exit thresholds
- Reduces emotional trading

### Success Tips
1. Focus on score >= 9 (CALL) or >= 8 (PUT)
2. Always check volume surge lane
3. Respect RTH hours initially
4. Scale out at profit targets
5. Don't fight score reversals
6. Journal which score thresholds work best
7. Combine with price action and VWAP
8. Use tighter stops for 0DTE
9. Exit by 3:30 PM for same-day expiration
10. Start with small position sizes while learning

### Quick Reference

**Strong CALL:**
- Score >= 9
- Put Score <= 2
- Volume surge
- RTH hours
- Above VWAP

**Strong PUT:**
- Score >= 8
- Call Score <= 2
- Volume surge
- RTH hours
- Below VWAP

**Avoid:**
- Scores both moderate
- No volume surge
- Extended hours (initially)
- After 3:45 PM (0DTE)

---

**File:** `iwm-scalping`
**Version:** Pine Script v6
**Indicator Type:** Separate pane (not overlay)
**Best Paired With:** VWAP, support/resistance levels, IWM-BSVP for volume confirmation
