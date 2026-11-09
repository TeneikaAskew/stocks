-- FEAT-STRAT-001 #1753 done_when 13: read-only export of the brief's daily input.
-- Same columns as lib/data_loader.py DataLoader.load_daily (without the
-- premarket provenance columns, which production does not have yet).
SELECT ticker, date, open AS "Open", high AS "High", low AS "Low",
       close AS "Close", adjusted_close, volume AS "Volume",
       rsi_14, rsi_9, ema_9, ema_20, ema_50, ma_5, ma_10, ma_20, ma_50, sma_200,
       atr_14, atr_20, macd, macd_signal, macd_histogram,
       bb_upper, bb_lower, bb_width, bb_pct,
       stoch_rsi_k AS "StochRSI_K", stoch_rsi_d AS "StochRSI_D",
       obv, rvol, volatility_20d,
       consecutive_up AS "Consecutive_Up", consecutive_down AS "Consecutive_Down",
       vwap, price_vs_vwap AS "Price_vs_VWAP", price_vs_ema9, price_vs_ema20,
       strat_candle, strat_combo, strat_setup, ftfc_score, ftfc_direction,
       pre_high, pre_low, pre_vwap, pre_volume, gap_pct, pre_range_atr
FROM market_data_daily
WHERE ticker IN ('SPY', 'QQQ', 'IWM')
  AND date BETWEEN '2013-01-01' AND '2026-11-06'
ORDER BY ticker, date
