SELECT ticker, date, open, high, low, close, atr_14, sma_200, pre_high, pre_low, pre_vwap, gap_pct FROM market_data_daily WHERE ticker IN ('SPY', 'QQQ', 'IWM') AND date >= DATE '2025-03-01' ORDER BY date, ticker;
SELECT event_date, event_time, event_name, country, importance FROM economic_events WHERE event_date >= DATE '2025-03-01' AND importance = 'high' ORDER BY event_date, event_time;
