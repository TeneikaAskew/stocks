/**
 * Detect strategy type from sheet name
 * @param {string} strategyName - Sheet name (e.g., 'Long Calls', 'Long Puts', 'Bull Spreads')
 * @returns {string} 'BULLISH', 'BEARISH', or 'NEUTRAL'
 */
function EW_detectStrategyType(strategyName) {
  const strategyUpper = strategyName.toUpperCase();

  // Bullish strategies
  if (strategyUpper.includes('LONG CALL') ||
      strategyUpper.includes('BULL') ||
      strategyUpper.includes('COVERED CALL')) {
    return 'BULLISH';
  }

  // Bearish strategies
  if (strategyUpper.includes('LONG PUT') ||
      strategyUpper.includes('BEAR') ||
      strategyUpper.includes('SHORT CALL')) {
    return 'BEARISH';
  }

  // Neutral strategies
  if (strategyUpper.includes('STRANGLE') ||
      strategyUpper.includes('STRADDLE') ||
      strategyUpper.includes('SHORT PUT')) {
    return 'NEUTRAL';
  }

  // Default to bullish if unknown
  return 'BULLISH';
}

/**
 * Fetch underlying stock OHLC data for multiple tickers in one batch call
 * @param {Array} positions - Array of positions
 * @returns {Object} Map of ticker -> stock OHLC data
 */
function EW_fetchStockOHLCBatch(positions) {
  const stockDataMap = {};

  if (positions.length === 0) return stockDataMap;

  // Get unique tickers
  const tickers = [...new Set(positions.map(pos => pos.ticker))];

  // Batch API call for stock quotes
  const symbolsStr = tickers.join(',');
  const url = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbolsStr}`;

  EW_trace('OPTIONS_PREMIUM', `Fetching ${tickers.length} stock OHLC in batch`, false);

  try {
    const response = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });

    const responseCode = response.getResponseCode();

    if (responseCode !== 200) {
      EW_trace('OPTIONS_PREMIUM', `Stock batch fetch failed: HTTP ${responseCode}`, false);
      return stockDataMap;
    }

    const data = JSON.parse(response.getContentText());

    if (!data.quoteResponse || !data.quoteResponse.result) {
      return stockDataMap;
    }

    // Process each stock result
    const results = data.quoteResponse.result;

    for (const quote of results) {
      const ticker = quote.symbol;

      stockDataMap[ticker] = {
        ticker: ticker,
        price: quote.regularMarketPrice || null,
        dayHigh: quote.regularMarketDayHigh || null,
        dayLow: quote.regularMarketDayLow || null,
        dayOpen: quote.regularMarketOpen || null,
        volume: quote.regularMarketVolume || 0
      };
    }

    EW_trace('OPTIONS_PREMIUM', `Received stock data for ${Object.keys(stockDataMap).length} tickers`, false);

  } catch (error) {
    EW_trace('OPTIONS_PREMIUM', `Stock batch fetch error: ${error.message}`, false);
  }

  return stockDataMap;
}
