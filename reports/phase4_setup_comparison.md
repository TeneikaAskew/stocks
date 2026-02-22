# Phase 4: Cross-Ticker Setup Comparison

Generated: 2026-02-22 23:42:35

## Universal vs Ticker-Specific Setups
Setups found in multiple tickers (potential universal edges):

| Setup | IWM | SPY | QQQ | Avg WR | Universal? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| RSI 30-50 + Above EMA20 + StochRSI Oversold | 69.1% | 70.1% | N/A | 69.6% | Partial |
| Above EMA20 + EMA9 < EMA20 + StochRSI Oversold | N/A | 68.7% | 66.7% | 67.7% | Partial |
| Above OB + No OB Test | 60.7% | N/A | 71.7% | 66.2% | Partial |
| EMA9 > EMA20 + Above OB + No OB Test | 60.0% | N/A | 71.7% | 65.8% | Partial |
| Above EMA20 + Above OB + No OB Test | 60.0% | N/A | 71.7% | 65.8% | Partial |
| RSI > 70 + StochRSI Oversold + Prev 2D | 70.0% | N/A | 61.5% | 65.7% | Partial |
| Above EMA9 + EMA9 < EMA20 + StochRSI Oversold | N/A | 66.1% | 65.3% | 65.7% | Partial |
| RSI 30-50 + Above EMA9 + StochRSI Oversold | 65.2% | 65.7% | N/A | 65.5% | Partial |
| RSI > 70 + StochRSI Oversold + Prev 2U | 60.8% | N/A | 68.4% | 64.6% | Partial |
| RSI > 70 + StochRSI Oversold + Strat 2D | 67.9% | 61.1% | 63.5% | 64.2% | Yes |
| StochRSI Neutral + ATR High (>1.5x) + Strat 1 | 63.7% | 62.6% | N/A | 63.2% | Partial |
| RSI > 70 + RVOL > 1.5 + ATR High (>1.5x) | N/A | 61.2% | 64.1% | 62.7% | Partial |
| RSI > 70 + StochRSI Oversold + OBV Falling | 64.5% | N/A | 60.1% | 62.3% | Partial |
| ATR High (>1.5x) + Strat 1 + Prev 2D | 61.0% | 62.3% | N/A | 61.7% | Partial |
| RVOL > 1.5 + StochRSI Overbought + ATR High (>1.5x) | 60.0% | N/A | 62.9% | 61.5% | Partial |
| Below EMA9 + StochRSI Overbought + Strat 3 | 60.2% | 62.0% | N/A | 61.1% | Partial |
| Below EMA20 + Below OB | N/A | 60.8% | 61.1% | 60.9% | Partial |
| RSI 30-50 + RVOL 0.8-1.5 + ATR High (>1.5x) | 60.0% | N/A | 61.0% | 60.5% | Partial |
| RSI < 30 + RVOL > 1.5 + OBV Rising | N/A | 60.7% | 60.0% | 60.4% | Partial |

## Per-Ticker Best Setups
**IWM** (47 setups):
- RSI > 70 + StochRSI Oversold + Prev 2D [15m] — WR: 70.0%, n=80, Bullish
- RSI 30-50 + Above EMA20 + StochRSI Oversold — WR: 69.1%, n=123, Bullish
- RSI > 70 + StochRSI Oversold + Strat 2D [15m] — WR: 67.9%, n=56, Bullish
- RSI < 30 + Above EMA9 + ATR High (>1.5x) — WR: 67.7%, n=31, Bullish
- RVOL 0.8-1.5 + ATR High (>1.5x) + Strat 1 [15m] — WR: 67.2%, n=67, Bullish

**SPY** (39 setups):
- RSI > 70 + Below EMA9 + Prev 2U — WR: 74.2%, n=31, Bearish
- RSI 30-50 + Above EMA20 + StochRSI Oversold — WR: 70.1%, n=107, Bullish
- Above EMA20 + EMA9 < EMA20 + StochRSI Oversold — WR: 68.7%, n=1318, Bullish
- Below EMA20 + ATR Low (<0.5x) + Within OB [5m] — WR: 66.7%, n=54, Bullish
- Above EMA9 + EMA9 < EMA20 + StochRSI Oversold — WR: 66.1%, n=3552, Bullish

**QQQ** (99 setups):
- Above OB + No OB Test [5m] — WR: 71.7%, n=53, Bullish
- Above EMA20 + Above OB + No OB Test [5m] — WR: 71.7%, n=53, Bullish
- EMA9 > EMA20 + Above OB + No OB Test [5m] — WR: 71.7%, n=53, Bullish
- Above EMA20 + Above OB [5m] — WR: 70.7%, n=75, Bullish
- Above EMA20 + EMA9 > EMA20 + Above OB [5m] — WR: 70.7%, n=75, Bullish

