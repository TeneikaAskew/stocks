# IWM Trading Rules & Alert System
Based on Analysis of 36,547 Profitable Trades

## 🎯 TRADING RULES

### ⏰ PRIME TRADING WINDOWS
1. **BEST**: 9:30-10:00 AM ET (0.480% avg return)
2. **GOOD**: 10:00 AM-2:00 PM ET (0.328% avg return)
3. **AVOID**: After 2:00 PM ET (0.298% avg return)

### 📈 CALL ENTRY RULES (Contrarian Approach)

**MINIMUM REQUIREMENTS** (Need ALL 3):
1. ✅ Price < VWAP (contrarian signal)
2. ✅ RSI > 45 but < 70
3. ✅ RVOL > 1.0

**STRONG SETUP** (3+ of these):
- 🟢 Price < EMA9
- 🟢 Morning session (9:30-10:00 AM)
- 🟢 RVOL > 1.5
- 🟢 RSI crossing above 50
- 🟢 ATR > 0.15

**BEST SETUP** (5+ indicators):
- All minimum requirements PLUS
- EMA9 starting to curve up
- StochRSI > 70 (momentum building)
- OBV in bottom 20% of daily range

**EXIT RULES**:
- 🎯 TARGET: 0.30% profit (average for CALLs)
- ⏱️ TIME STOP: 30 minutes max
- 🛑 STOP LOSS: -0.15% (half of target)

### 📉 PUT ENTRY RULES (Contrarian Approach)

**MINIMUM REQUIREMENTS** (Need ALL 3):
1. ✅ Price > VWAP (contrarian signal)
2. ✅ RSI < 55 and > 30
3. ✅ RVOL > 1.0

**STRONG SETUP** (3+ of these):
- 🟢 Price > EMA9
- 🟢 RSI < 40 (stronger signal)
- 🟢 RVOL > 1.5
- 🟢 Morning session preferred
- 🟢 ATR > 0.15

**BEST SETUP** (5+ indicators):
- All minimum requirements PLUS
- EMA9 < EMA20 (downward momentum)
- StochRSI < 30
- Exit RSI targeting < 30

**EXIT RULES**:
- 🎯 TARGET: 0.38% profit (average for PUTs)
- ⏱️ TIME STOP: 35 minutes max
- 🛑 STOP LOSS: -0.20% (half of target)

## 🚨 ALERT CONDITIONS

### 🔔 PRIMARY ALERTS (High Priority)

**CALL ALERT**:
```
TRIGGER WHEN:
- Time between 9:30-10:00 AM ET
- Price < VWAP
- RSI > 45 AND RSI < 70
- RVOL > 1.5
- At least 3 "Strong Setup" conditions met

ALERT MESSAGE: "🟢 CALL Setup: IWM ${price} | RSI: ${rsi} | RVOL: ${rvol}x | Signal Strength: ${strength}%"
```

**PUT ALERT**:
```
TRIGGER WHEN:
- Time between 9:30-10:00 AM ET
- Price > VWAP
- RSI < 55 AND RSI > 30
- RVOL > 1.5
- At least 3 "Strong Setup" conditions met

ALERT MESSAGE: "🔴 PUT Setup: IWM ${price} | RSI: ${rsi} | RVOL: ${rvol}x | Signal Strength: ${strength}%"
```

### 🔔 SECONDARY ALERTS (Medium Priority)

**HIGH VOLATILITY ALERT**:
```
TRIGGER: ATR > 0.2 AND RVOL > 3.0
MESSAGE: "⚡ High Volatility: ATR ${atr} | RVOL ${rvol}x - Larger moves possible"
```

**EXIT SIGNAL ALERTS**:
```
CALL EXIT: Price hits +0.30% from entry OR 30 min elapsed OR RSI > 80
PUT EXIT: Price hits +0.38% from entry OR 35 min elapsed OR RSI < 20
```

### 🔔 WARNING ALERTS

**AVOID TRADING**:
```
TRIGGER: After 2:00 PM ET OR RVOL < 0.5 OR ATR < 0.05
MESSAGE: "⚠️ Poor conditions - Consider avoiding trades"
```

## 📊 POSITION SIZING RULES

### Signal Strength Calculation:
- **Weak** (3 indicators): 25% position size
- **Medium** (4 indicators): 50% position size  
- **Strong** (5+ indicators): 75% position size
- **Perfect** (7+ indicators): 100% position size

### Maximum Risk Per Trade:
- Never risk more than 1% of account per trade
- Scale position size based on signal strength
- Reduce size by 50% after 2:00 PM

## 📈 TRADE TRACKING TEMPLATE

```csv
Entry_Time,Type,Entry_Price,Entry_RSI,Entry_RVOL,Signal_Strength,Exit_Time,Exit_Price,Result,Notes
```

## 🎯 QUICK REFERENCE CHECKLIST

### Before Taking Any Trade:
- [ ] Is it between 9:30 AM - 2:00 PM ET?
- [ ] Is RVOL > 1.0?
- [ ] Are minimum requirements met?
- [ ] Do I have 3+ setup conditions?
- [ ] Is my stop loss set?
- [ ] Is position size appropriate?

### During The Trade:
- [ ] Set timer for time stop (30 min CALL / 35 min PUT)
- [ ] Set price alerts for profit target
- [ ] Monitor RSI for extreme exit signals
- [ ] Watch RVOL for momentum confirmation

### After The Trade:
- [ ] Log all details immediately
- [ ] Note what worked/didn't work
- [ ] Update running statistics

## 🚀 ADVANCED PATTERNS

### Ultra-High Probability Setups:

**MORNING MOMENTUM CALL** (Rare but powerful):
- Time: 9:30-9:45 AM
- Price just crossed below VWAP
- RSI between 50-60
- RVOL > 5.0
- OBV in bottom 20%
- Expected return: 0.45%+

**OVERSOLD BOUNCE PUT** (Contrarian excellence):
- RSI < 35 but rising
- Price > VWAP
- StochRSI < 20
- High ATR (> 0.2)
- Expected return: 0.50%+

## 📱 ALERT IMPLEMENTATION CODE

### TradingView Pine Script Example:
```pinescript
//@version=5
indicator("IWM Contrarian Alerts", overlay=true)

// Inputs
rsi_length = input(14, "RSI Length")
rvol_threshold = input(1.5, "RVOL Threshold")

// Calculations
rsi_val = ta.rsi(close, rsi_length)
vwap_val = ta.vwap(hlc3)
rvol = volume / ta.sma(volume, 20)

// Time check
is_prime_time = (hour == 9 and minute >= 30) or (hour >= 10 and hour < 14)
is_morning = hour == 9 and minute >= 30

// CALL conditions (contrarian)
call_setup = close < vwap_val and rsi_val > 45 and rsi_val < 70 and rvol > 1.0
call_strong = call_setup and is_prime_time and rvol > rvol_threshold

// PUT conditions (contrarian)  
put_setup = close > vwap_val and rsi_val < 55 and rsi_val > 30 and rvol > 1.0
put_strong = put_setup and is_prime_time and rvol > rvol_threshold

// Alerts
alertcondition(call_strong, title="CALL Setup", message="CALL Setup: IWM {{close}} | RSI: {{plot_0}} | RVOL: {{plot_1}}x")
alertcondition(put_strong, title="PUT Setup", message="PUT Setup: IWM {{close}} | RSI: {{plot_0}} | RVOL: {{plot_1}}x")

// Plots for alert messages
plot(rsi_val, display=display.none)
plot(rvol, display=display.none)
```

## 📊 PERFORMANCE TRACKING

### Weekly Goals (Based on Historical Data):
- **Target**: 3-5 trades per week
- **Win Rate Goal**: 75%+ (your data shows 100% but be realistic)
- **Average Return Target**: 0.25% per trade
- **Weekly Target**: 0.75-1.25%

### Monthly Review Metrics:
1. Win rate by time of day
2. Average return by setup strength  
3. Performance CALL vs PUT
4. Best and worst performing setups

## 🛡️ RISK MANAGEMENT RULES

### NEVER BREAK THESE:
1. **No revenge trading** - One loss doesn't predict the next trade
2. **No trading after 2 PM** - Statistics show diminishing returns
3. **No forcing trades** - Wait for your setup
4. **No increasing size after losses** - Stick to the plan
5. **No trading without stops** - Always define risk

### ALWAYS DO THESE:
1. **Log every trade** - Data is your edge
2. **Review weekly** - Identify patterns in your execution
3. **Update rules** - Refine based on real results
4. **Stay humble** - Markets change, adapt accordingly

---

*Remember: These rules are based on historical profitable trades. Real trading includes losses. Start small, track everything, and refine based on YOUR actual results.*