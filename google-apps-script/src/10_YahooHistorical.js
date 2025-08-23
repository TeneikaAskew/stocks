/**
 * Yahoo Finance Historical Data Functions
 * Fetches intraday and daily historical price data to check if strike prices were hit
 */

/**
 * Check if a stock hit a target price on a specific date
 * Uses 1-minute interval data to capture full trading day
 * @param {string} ticker - Stock ticker symbol
 * @param {number} targetPrice - Target/strike price to check
 * @param {Date} date - Date to check
 * @returns {Object} Result object with hit status and details
 */
function EW_checkStockIntraday(ticker, targetPrice, date = new Date()) {
  // Default to 1-minute intervals for full day data
  const defaultInterval = '1m';
  
  try {
    const result = EW_fetchYahooData(ticker, targetPrice, date, defaultInterval);
    if (result && !result.error) {
      return result;
    }
  } catch (error) {
    EW_trace('YAHOO', `Failed with default interval ${defaultInterval}: ${error.message}`);
    console.log(`YAHOO FALLBACK: Failed to get 1m data for ${ticker}, trying fallback intervals...`);
    Logger.log(`YAHOO FALLBACK: Failed to get 1m data for ${ticker}, error: ${error.message}`);
  }
  
  // Only try fallbacks if 1m fails
  const fallbackIntervals = ['5m', '1h', '1d'];
  
  for (const interval of fallbackIntervals) {
    try {
      console.log(`YAHOO FALLBACK: Trying ${interval} interval for ${ticker}`);
      Logger.log(`YAHOO FALLBACK: Attempting ${interval} interval for ${ticker} on ${date.toISOString()}`);
      
      const result = EW_fetchYahooData(ticker, targetPrice, date, interval);
      if (result && !result.error) {
        console.log(`YAHOO FALLBACK SUCCESS: Got data using ${interval} interval for ${ticker}`);
        Logger.log(`YAHOO FALLBACK SUCCESS: Retrieved data using ${interval} interval for ${ticker}`);
        result.fallbackUsed = interval;
        return result;
      }
    } catch (error) {
      EW_trace('YAHOO', `Failed with fallback interval ${interval}: ${error.message}`);
      console.log(`YAHOO FALLBACK FAILED: ${interval} interval failed for ${ticker}`);
      Logger.log(`YAHOO FALLBACK FAILED: ${interval} interval error for ${ticker}: ${error.message}`);
      continue;
    }
  }
  
  console.log(`YAHOO ERROR: No data available for ${ticker} on ${date.toISOString()} with any interval`);
  Logger.log(`YAHOO ERROR: Failed to retrieve data for ${ticker} on ${date.toISOString()} with all intervals`);
  return { hit: false, error: 'No data available for any interval' };
}

/**
 * Fetch Yahoo Finance data for a specific ticker and date
 * @param {string} ticker - Stock ticker symbol
 * @param {number} targetPrice - Target price to check
 * @param {Date} date - Date to check
 * @param {string} interval - Time interval (1m, 5m, 1h, 1d)
 * @returns {Object} Result with hit status and price data
 */
function EW_fetchYahooData(ticker, targetPrice, date, interval) {
  // Set time range based on interval
  let startDate, endDate;
  
  if (interval === '1d') {
    // For daily data, get last 30 days to ensure we have the date
    startDate = new Date(date);
    startDate.setDate(startDate.getDate() - 30);
    endDate = new Date(date);
    endDate.setDate(endDate.getDate() + 1);
  } else {
    // For intraday data, get current day only
    startDate = new Date(date);
    startDate.setHours(4, 0, 0, 0); // Pre-market start (4 AM ET)
    
    endDate = new Date(date);
    endDate.setHours(20, 0, 0, 0); // After-hours end (8 PM ET)
  }
  
  const period1 = Math.floor(startDate.getTime() / 1000);
  const period2 = Math.floor(endDate.getTime() / 1000);
  
  const url = `https://query2.finance.yahoo.com/v8/finance/chart/${ticker}?period1=${period1}&period2=${period2}&interval=${interval}&events=history`;
  
  EW_trace('YAHOO', `Fetching ${ticker} with ${interval} interval from ${startDate.toISOString()} to ${endDate.toISOString()}`);
  
  try {
    const response = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });
    
    const responseCode = response.getResponseCode();
    if (responseCode !== 200) {
      EW_trace('YAHOO', `HTTP ${responseCode} for ${ticker}`);
      return { hit: false, error: `HTTP ${responseCode}` };
    }
    
    const data = JSON.parse(response.getContentText());
    
    // Check for errors in response
    if (data.chart && data.chart.error) {
      EW_trace('YAHOO', `API Error: ${data.chart.error.description}`);
      return { hit: false, error: data.chart.error.description };
    }
    
    if (!data.chart || !data.chart.result || data.chart.result.length === 0) {
      EW_trace('YAHOO', 'No data in response');
      return { hit: false, error: 'No data available' };
    }
    
    const result = data.chart.result[0];
    const timestamps = result.timestamp;
    const quotes = result.indicators.quote[0];
    
    if (!timestamps || timestamps.length === 0) {
      EW_trace('YAHOO', 'No timestamps in response');
      return { hit: false, error: 'No price data available' };
    }
    
    EW_trace('YAHOO', `Got ${timestamps.length} data points for ${ticker} (${interval})`);
    
    // Filter data points to the specific date we're checking
    const targetDateStart = new Date(date);
    targetDateStart.setHours(0, 0, 0, 0);
    const targetDateEnd = new Date(date);
    targetDateEnd.setHours(23, 59, 59, 999);
    
    // Check each data point to see if target price was hit
    let dayHigh = 0;
    let dayLow = Infinity;
    let hitTime = null;
    let hitData = null;
    
    for (let i = 0; i < timestamps.length; i++) {
      const dataTime = new Date(timestamps[i] * 1000);
      
      // Only check data points on the target date
      if (dataTime >= targetDateStart && dataTime <= targetDateEnd) {
        const high = quotes.high[i];
        const low = quotes.low[i];
        const close = quotes.close[i];
        
        if (high !== null && high !== undefined) {
          dayHigh = Math.max(dayHigh, high);
        }
        if (low !== null && low !== undefined) {
          dayLow = Math.min(dayLow, low);
        }
        
        // Check if target price was hit in this candle
        if (high !== null && low !== null && low <= targetPrice && targetPrice <= high) {
          if (!hitTime) {
            hitTime = dataTime;
            hitData = {
              timestamp: hitTime,
              high: high,
              low: low,
              close: close
            };
            EW_trace('YAHOO', `🎯 TARGET HIT! ${ticker} hit ${targetPrice} at ${hitTime.toISOString()}`);
          }
        }
      }
    }
    
    if (hitTime) {
      return {
        hit: true,
        timestamp: hitTime,
        high: hitData.high,
        low: hitData.low,
        close: hitData.close,
        dayHigh: dayHigh,
        dayLow: dayLow,
        interval: interval
      };
    }
    
    // Get last close for the day
    let lastClose = null;
    for (let i = timestamps.length - 1; i >= 0; i--) {
      const dataTime = new Date(timestamps[i] * 1000);
      if (dataTime >= targetDateStart && dataTime <= targetDateEnd && quotes.close[i] !== null) {
        lastClose = quotes.close[i];
        break;
      }
    }
    
    EW_trace('YAHOO', `${ticker} range: ${dayLow.toFixed(2)} - ${dayHigh.toFixed(2)}, Target ${targetPrice} NOT hit`);
    
    return { 
      hit: false, 
      dayHigh: dayHigh === 0 ? null : dayHigh,
      dayLow: dayLow === Infinity ? null : dayLow,
      lastClose: lastClose,
      interval: interval,
      dataPoints: timestamps.length,
      message: `Target ${targetPrice} not hit. Range: ${dayLow.toFixed(2)} - ${dayHigh.toFixed(2)}`
    };
    
  } catch (error) {
    EW_trace('YAHOO', `Fetch error: ${error.message}`);
    throw error;
  }
}

/**
 * Get historical price data for a date range
 * @param {string} ticker - Stock ticker symbol
 * @param {Date} startDate - Start date
 * @param {Date} endDate - End date
 * @returns {Array} Array of daily price data
 */
function EW_getYahooHistoricalRange(ticker, startDate, endDate) {
  const period1 = Math.floor(startDate.getTime() / 1000);
  const period2 = Math.floor(endDate.getTime() / 1000);
  
  const url = `https://query2.finance.yahoo.com/v8/finance/chart/${ticker}?period1=${period1}&period2=${period2}&interval=1d&events=history`;
  
  try {
    const response = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });
    
    if (response.getResponseCode() !== 200) {
      return [];
    }
    
    const data = JSON.parse(response.getContentText());
    
    if (!data.chart || !data.chart.result || data.chart.result.length === 0) {
      return [];
    }
    
    const result = data.chart.result[0];
    const timestamps = result.timestamp || [];
    const quotes = result.indicators.quote[0];
    
    const historicalData = [];
    
    for (let i = 0; i < timestamps.length; i++) {
      if (quotes.high[i] !== null && quotes.low[i] !== null) {
        historicalData.push({
          date: new Date(timestamps[i] * 1000),
          high: quotes.high[i],
          low: quotes.low[i],
          open: quotes.open[i] || quotes.close[i],
          close: quotes.close[i] || quotes.open[i],
          volume: quotes.volume[i] || 0
        });
      }
    }
    
    return historicalData;
    
  } catch (error) {
    EW_trace('YAHOO', `Error getting historical range for ${ticker}: ${error.message}`);
    return [];
  }
}

/**
 * Check if a strike was hit during a date range using Yahoo Finance data
 * @param {string} ticker - Stock ticker
 * @param {number} strike - Strike price
 * @param {string} strategy - Strategy type
 * @param {Date} startDate - Start date
 * @param {Date} endDate - End date
 * @returns {Object} Hit analysis with date and status
 */
function EW_checkStrikeHitYahoo(ticker, strike, strategy, startDate, endDate) {
  const strategyUpper = strategy.toUpperCase();
  const isBullish = strategyUpper.includes('LONG CALL') || strategyUpper.includes('BULL');
  const isBearish = strategyUpper.includes('LONG PUT') || strategyUpper.includes('BEAR');
  
  // Get historical data for the range
  const historicalData = EW_getYahooHistoricalRange(ticker, startDate, endDate);
  
  let hitDate = null;
  let hitPrice = null;
  
  for (const dayData of historicalData) {
    let dayHit = false;
    
    if (isBullish) {
      // For bullish strategies, check if high >= strike
      if (dayData.high >= strike) {
        dayHit = true;
        hitPrice = dayData.high;
      }
    } else if (isBearish) {
      // For bearish strategies, check if low <= strike
      if (dayData.low <= strike) {
        dayHit = true;
        hitPrice = dayData.low;
      }
    }
    
    if (dayHit && !hitDate) {
      hitDate = dayData.date;
      break; // Found first hit
    }
  }
  
  return {
    hit: hitDate !== null,
    hitDate: hitDate,
    hitPrice: hitPrice,
    status: hitDate ? 'HIT' : 'NO',
    ticker: ticker
  };
}

/**
 * Batch check multiple positions for strike hits
 * @param {Array} positions - Array of position objects with ticker, strike, strategy, dates
 * @returns {Array} Results for each position
 */
function EW_batchCheckStrikeHits(positions) {
  const results = [];
  const batchSize = 10; // Process in batches to avoid rate limits
  
  for (let i = 0; i < positions.length; i += batchSize) {
    const batch = positions.slice(i, i + batchSize);
    
    for (const position of batch) {
      try {
        // Use checkStockIntraday to get 1m data with fallback tracking
        const intradayResult = EW_checkStockIntraday(
          position.ticker, 
          position.strike, 
          position.endDate
        );
        
        // Determine if strike was hit based on strategy
        const strategyUpper = position.strategy.toUpperCase();
        const isBullish = strategyUpper.includes('LONG CALL') || strategyUpper.includes('BULL');
        const isBearish = strategyUpper.includes('LONG PUT') || strategyUpper.includes('BEAR');
        
        let hit = false;
        let hitDate = null;
        
        if (intradayResult.hit) {
          hit = true;
          hitDate = intradayResult.timestamp;
        } else if (intradayResult.dayHigh && intradayResult.dayLow) {
          // Check based on day's range
          if (isBullish && intradayResult.dayHigh >= position.strike) {
            hit = true;
            hitDate = position.endDate;
          } else if (isBearish && intradayResult.dayLow <= position.strike) {
            hit = true;
            hitDate = position.endDate;
          }
        }
        
        results.push({
          ...position,
          hit: hit,
          hitDate: hitDate,
          status: hit ? 'HIT' : 'NO',
          fallbackUsed: intradayResult.fallbackUsed,
          dayHigh: intradayResult.dayHigh,
          dayLow: intradayResult.dayLow,
          error: intradayResult.error
        });
        
      } catch (error) {
        EW_trace('YAHOO', `Error checking ${position.ticker}: ${error.message}`);
        results.push({
          ...position,
          hit: false,
          error: error.message
        });
      }
    }
    
    // Rate limiting between batches
    if (i + batchSize < positions.length) {
      Utilities.sleep(1000);
    }
  }
  
  return results;
}

/**
 * Test function for Yahoo Finance data
 */
function EW_testYahooData() {
  console.log('=== Testing Yahoo Finance Data ===');
  
  // Test current day hit
  const today = new Date();
  const result1 = EW_checkStockIntraday('IWM', 235.00, today);
  console.log('IWM $235 today:', result1);
  
  // Test historical hit
  const pastDate = new Date();
  pastDate.setDate(pastDate.getDate() - 7);
  const result2 = EW_checkStockIntraday('SPY', 450.00, pastDate);
  console.log('SPY $450 last week:', result2);
  
  // Test range data
  const rangeStart = new Date();
  rangeStart.setDate(rangeStart.getDate() - 30);
  const rangeData = EW_getYahooHistoricalRange('AAPL', rangeStart, today);
  console.log(`AAPL historical data points: ${rangeData.length}`);
  
  return {
    currentDay: result1,
    historical: result2,
    rangeDataPoints: rangeData.length
  };
}