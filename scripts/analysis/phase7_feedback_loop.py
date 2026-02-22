#!/usr/bin/env python3
"""
Phase 7: Ongoing Scoring & Feedback Loop

Produces:
  7A. Setup tracker template and scoring system
  7B. Weekly performance review template
  7C. Pre-market regime check template

Output: reports/phase7_feedback_loop.md
"""

import sys
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.analysis.shared_utils import (
    TICKERS, REPORTS_DIR,
    load_ticker_1m, enrich_with_indicators, classify_strat_series,
    md_header, md_table, fmt_pct, fmt_bps, fmt_num, save_report,
    timestamp_str, progress,
    IndicatorConfig,
)


# ---------------------------------------------------------------------------
# 7A. Setup Tracker
# ---------------------------------------------------------------------------

def generate_setup_tracker() -> str:
    """Generate the setup tracking system."""
    report = md_header("7A. Setup Tracker — Live Trade Tagging System", 2)

    report += """
Every trade gets tagged with the following attributes for ongoing learning.

### Trade Entry Log

For each trade, record:

| Field | Description | Example |
|-------|-------------|---------|
| Date/Time | Entry timestamp | 2026-02-20 10:15 |
| Ticker | IWM / SPY / QQQ | IWM |
| Direction | CALL / PUT | PUT |
| Card # | Which playbook card matched | Card 2 |
| Strat Pattern | Current Strat sequence | 2D-2D-2D |
| RSI at Entry | RSI14 value | 62.3 |
| VWAP Position | Above / Below / At | Above |
| EMA Cross | Bullish / Bearish | Bearish |
| ORB Status | Bullish / Bearish / Within / Failed | Bearish |
| RVOL | Relative volume | 1.8 |
| StochRSI | Oversold / Neutral / Overbought | Overbought |
| FTFC Alignment | All Bull / All Bear / Mixed | All Bear |
| Regime | Low Vol / Normal / High Vol | Normal |
| Signal Score | 1-8 | 6 |

### Trade Exit Log

| Field | Description | Example |
|-------|-------------|---------|
| Exit Time | Exit timestamp | 2026-02-20 10:28 |
| Exit Reason | target / stop / time_stop / manual | target |
| Hold Duration | Minutes | 13 |
| Return (bps) | Actual P/L in basis points | +32 |
| Return ($) | Dollar P/L | +$48 |
| Result | WIN / LOSS | WIN |
| Notes | What worked / what didn't | Clean 2D-2D setup, VWAP rejection confirmed |

### Cumulative Tracking

Over time, this builds a database that answers:
- Which playbook cards have the highest REAL win rate?
- Are theoretical probabilities holding up in live trading?
- Which conditions am I consistently reading correctly/incorrectly?
- Is there a pattern to my losing trades (time of day, ticker, setup type)?

"""

    # CSV template
    report += md_header("Trade Log CSV Template", 3)
    report += """
Save each trade in `data/trade_log.csv` with these columns:

```
date,time,ticker,direction,card_num,strat_pattern,rsi,vwap_pos,ema_cross,orb_status,rvol,stoch_rsi,ftfc,regime,signal_score,exit_time,exit_reason,hold_min,return_bps,return_usd,result,notes
```

Example row:
```
2026-02-20,10:15,IWM,PUT,2,2D-2D-2D,62.3,Above,Bearish,Bearish,1.8,Overbought,All Bear,Normal,6,10:28,target,13,32,48,WIN,Clean setup
```

"""
    return report


# ---------------------------------------------------------------------------
# 7B. Weekly Performance Review
# ---------------------------------------------------------------------------

def generate_weekly_review_template() -> str:
    """Generate the weekly review template."""
    report = md_header("7B. Weekly Performance Review Template", 2)

    report += """
Copy this template each week and fill in the actual numbers.

---

## Week of [DATE]

### IWM Performance
| Metric | Value |
|--------|-------|
| Trades taken | ___ |
| Win rate | ___% |
| Total P/L (bps) | ___ |
| Best setup | Card ___ (description) |
| Worst setup | Card ___ (description) |
| Setups used | Card ___ (x___), Card ___ (x___) |

**Notes:** ___

### SPY Performance
| Metric | Value |
|--------|-------|
| Trades taken | ___ |
| Win rate | ___% |
| Total P/L (bps) | ___ |
| Best setup | Card ___ (description) |
| Worst setup | Card ___ (description) |
| Setups used | Card ___ (x___), Card ___ (x___) |

**Notes:** ___

### QQQ Performance
| Metric | Value |
|--------|-------|
| Trades taken | ___ |
| Win rate | ___% |
| Total P/L (bps) | ___ |
| Best setup | Card ___ (description) |
| Worst setup | Card ___ (description) |
| Setups used | Card ___ (x___), Card ___ (x___) |

**Notes:** ___

### Cross-Ticker Analysis
| Metric | Value |
|--------|-------|
| Days all tickers agreed | ___/5 |
| Agreement days WR | ___% |
| Conflict days WR | ___% |
| Best performing ticker | ___ |
| Ticker to reduce size on | ___ |

### Regime This Week
| Metric | Value |
|--------|-------|
| VIX avg | ___ |
| Regime | Low Vol / Normal / High Vol |
| Dominant trend | Bullish / Bearish / Range |
| Did regime affect results? | ___ |

### Key Learnings
1. ___
2. ___
3. ___

### Adjustments for Next Week
1. ___
2. ___

---

"""
    return report


# ---------------------------------------------------------------------------
# 7C. Pre-Market Regime Check
# ---------------------------------------------------------------------------

def generate_regime_check() -> str:
    """Generate the pre-market regime check template."""
    report = md_header("7C. Pre-Market Regime Check — Daily Checklist", 2)

    report += """
Complete this BEFORE each trading session.

---

## Pre-Market Checklist for [DATE]

### Market Regime
- [ ] VIX level: ___ (Low < 15 / Normal 15-25 / High > 25)
- [ ] ATR regime: Low Vol / Normal / High Vol
- [ ] Regime action: Standard targets / Wider targets / Tighter targets / Sit out

### Daily Strat Check
| Ticker | Daily Strat | 1h Strat | 15m Strat (premarket) |
|--------|-------------|----------|------------------------|
| IWM | ___ | ___ | ___ |
| SPY | ___ | ___ | ___ |
| QQQ | ___ | ___ | ___ |

### FTFC Alignment
| Ticker | FTFC Score | Direction | Quality |
|--------|------------|-----------|---------|
| IWM | ___ | Bull/Bear/Mixed | Strong/Weak |
| SPY | ___ | Bull/Bear/Mixed | Strong/Weak |
| QQQ | ___ | Bull/Bear/Mixed | Strong/Weak |

### Event Check
- [ ] FOMC today? Y/N — If Y: reduce size, avoid 2:00-2:30 PM
- [ ] Major earnings? Y/N — Which tickers affected?
- [ ] Economic data (CPI, NFP, etc.)? Y/N — Time: ___
- [ ] Options expiration? Y/N — Weekly / Monthly / Quarterly
- [ ] Unusual VIX move? Y/N — Direction: ___

### Active Cards Today

Based on the regime and Strat alignment, which cards are active?

**IWM:**
- [ ] Card ___ : ___
- [ ] Card ___ : ___

**SPY:**
- [ ] Card ___ : ___
- [ ] Card ___ : ___

**QQQ:**
- [ ] Card ___ : ___
- [ ] Card ___ : ___

### Risk Decisions
- [ ] Which ticker has cleanest setup? ___
- [ ] Max trades today: ___ (reduce on high-event days)
- [ ] Position size: Standard / Reduced / Increased
- [ ] Hard stop time: ___ PM (no new trades after this)

### After Market Close
- [ ] Log all trades in trade_log.csv
- [ ] Update running performance tracker
- [ ] Note anything unusual about today's session

---

"""
    return report


# ---------------------------------------------------------------------------
# Probability Update System
# ---------------------------------------------------------------------------

def generate_probability_update_system() -> str:
    """Generate the system for updating probabilities with live trade data."""
    report = md_header("7D. Probability Update System", 2)

    report += """
### How to Update Playbook Probabilities

As you accumulate trade data in `data/trade_log.csv`, run the probability
update script to see how REAL results compare to backtest expectations.

#### Update Frequencies
- **Daily**: Log trades
- **Weekly**: Run weekly review
- **Monthly**: Compare real vs backtest probabilities per card
- **Quarterly**: Full playbook recalibration

#### When to Adjust a Card

| Scenario | Action |
|----------|--------|
| Real WR > Backtest WR + 5pp for 50+ trades | Increase position size |
| Real WR < Backtest WR - 5pp for 50+ trades | Decrease position size or suspend card |
| Real WR matches Backtest WR +/- 3pp | Keep current parameters |
| Card never triggers (< 5 trades/month) | Keep but don't count on it |
| Card triggers too often (> 20 trades/week) | Tighten entry criteria |

#### Decay-Weighted Updates

Recent trades should matter more than old ones:

```
Adjusted WR = 0.7 * (last 30 days WR) + 0.3 * (all-time WR)
```

This ensures the system adapts to changing market conditions while still
respecting the larger sample of backtest data.

#### Red Flags (Stop Trading a Card)
1. 5+ consecutive losses on the same card
2. Real WR drops below 35% after 30+ trades
3. Average return goes negative after 50+ trades
4. Card contradicts current market regime
5. You don't understand WHY a card is winning/losing

"""

    report += md_header("Automation Script", 3)
    report += """
To automate the probability update, run:

```bash
python scripts/analysis/update_probabilities.py --trade-log data/trade_log.csv
```

This will:
1. Load your trade log
2. Group by playbook card and ticker
3. Calculate real win rates vs backtest expectations
4. Flag cards that need attention
5. Generate an updated probability report

"""
    return report


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------

def run_phase7():
    """Run Phase 7 — generate all templates and systems."""
    progress("Generating Phase 7: Ongoing Scoring & Feedback Loop")

    report = md_header("Phase 7: Ongoing Scoring & Feedback Loop", 1)
    report += f"\nGenerated: {timestamp_str()}\n"
    report += "\nTemplates and systems for live trading feedback.\n\n"

    # 7A: Setup tracker
    progress("  7A: Setup tracker...")
    report += generate_setup_tracker()

    # 7B: Weekly review
    progress("  7B: Weekly performance review template...")
    report += generate_weekly_review_template()

    # 7C: Regime check
    progress("  7C: Pre-market regime check...")
    report += generate_regime_check()

    # 7D: Probability update system
    progress("  7D: Probability update system...")
    report += generate_probability_update_system()

    save_report(report, 'phase7_feedback_loop.md')
    progress("Phase 7 complete!")


if __name__ == '__main__':
    run_phase7()
