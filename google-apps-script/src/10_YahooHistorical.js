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
        
        // Log the fallback usage
        EW_logApiCall({
          ticker: ticker,
          interval: interval,
          targetPrice: targetPrice,
          dateRequested: date.toISOString().split('T')[0],
          type: 'fallback_success',
          originalInterval: '1m',
          fallbackInterval: interval,
          reason: 'Original 1m interval failed',
          timestamp: new Date().toISOString()
        });
        
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
    // For intraday data, check if date is recent enough
    const today = new Date();
    const daysSinceDate = Math.floor((today - date) / (1000 * 60 * 60 * 24));
    
    // 1-minute data is typically only available for last 7 days
    if (interval === '1m' && daysSinceDate > 7) {
      EW_trace('YAHOO', `1-minute data not available for ${ticker} on ${date.toISOString()} (${daysSinceDate} days ago)`);
      throw new Error(`1-minute data only available for last 7 days`);
    }
    
    // For intraday data, use the simplified approach
    // Always get full trading day data
    startDate = new Date(date);
    endDate = new Date(date);
    
    if (interval === '1m') {
      // For 1-minute data, use regular trading hours only
      startDate.setHours(9, 30, 0, 0);   // 9:30 AM
      endDate.setHours(16, 0, 0, 0);     // 4:00 PM
    } else {
      // For other intervals, include extended hours
      startDate.setHours(4, 0, 0, 0);    // 4:00 AM pre-market
      endDate.setHours(20, 0, 0, 0);     // 8:00 PM after-hours
    }
    
    // Important: Don't adjust end time for today - always request full day
    // Yahoo will return whatever data is available up to current time
  }
  
  const period1 = Math.floor(startDate.getTime() / 1000);
  const period2 = Math.floor(endDate.getTime() / 1000);
  
  // Ensure start is before end
  if (period1 >= period2) {
    console.error(`YAHOO ERROR: Start time (${startDate.toISOString()}) is after end time (${endDate.toISOString()})`);
    // If we're checking today and it's before market open, adjust to yesterday
    if (interval !== '1d' && date.toDateString() === new Date().toDateString()) {
      const yesterday = new Date(date);
      yesterday.setDate(yesterday.getDate() - 1);
      console.log(`YAHOO: Adjusting to previous trading day: ${yesterday.toISOString()}`);
      return EW_fetchYahooData(ticker, targetPrice, yesterday, interval);
    }
    throw new Error(`Invalid date range: start ${period1} >= end ${period2}`);
  }
  
  const url = `https://query2.finance.yahoo.com/v8/finance/chart/${ticker}?period1=${period1}&period2=${period2}&interval=${interval}&events=history`;
  
  console.log(`YAHOO API: ${url}`);
  EW_trace('YAHOO', `Fetching ${ticker} with ${interval} interval from ${startDate.toISOString()} to ${endDate.toISOString()}`);
  EW_trace('YAHOO', `URL: ${url}`);
  
  // Log API call attempt
  const callStartTime = new Date();
  const logEntry = {
    ticker: ticker,
    interval: interval,
    targetPrice: targetPrice,
    dateRequested: date.toISOString().split('T')[0],
    startDate: startDate.toISOString(),
    endDate: endDate.toISOString(),
    period1: period1,
    period2: period2,
    url: url,
    requestedInterval: interval
  };
  
  try {
    const response = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });
    
    const responseCode = response.getResponseCode();
    logEntry.responseCode = responseCode;
    logEntry.duration = new Date() - callStartTime;
    
    if (responseCode !== 200) {
      const responseText = response.getContentText();
      console.error(`YAHOO API ERROR: HTTP ${responseCode} for ${ticker}`);
      console.error(`Response: ${responseText.substring(0, 500)}`);
      EW_trace('YAHOO', `HTTP ${responseCode} for ${ticker} - ${responseText.substring(0, 200)}`);
      logEntry.error = `HTTP ${responseCode}`;
      logEntry.errorDetails = responseText.substring(0, 500);
      logEntry.success = false;
      EW_logApiCall(logEntry, null);
      return { hit: false, error: `HTTP ${responseCode}` };
    }
    
    const data = JSON.parse(response.getContentText());
    
    // Check for errors in response
    if (data.chart && data.chart.error) {
      EW_trace('YAHOO', `API Error: ${data.chart.error.description}`);
      logEntry.error = data.chart.error.description;
      logEntry.success = false;
      EW_logApiCall(logEntry, data);
      return { hit: false, error: data.chart.error.description };
    }
    
    if (!data.chart || !data.chart.result || data.chart.result.length === 0) {
      EW_trace('YAHOO', 'No data in response');
      logEntry.error = 'No data available';
      logEntry.success = false;
      EW_logApiCall(logEntry, data);
      return { hit: false, error: 'No data available' };
    }
    
    const result = data.chart.result[0];
    const timestamps = result.timestamp;
    const quotes = result.indicators.quote[0];
    
    if (!timestamps || timestamps.length === 0) {
      EW_trace('YAHOO', 'No timestamps in response');
      logEntry.error = 'No price data available';
      logEntry.success = false;
      EW_logApiCall(logEntry, data);
      return { hit: false, error: 'No price data available' };
    }
    
    // Log successful data retrieval
    logEntry.success = true;
    logEntry.dataPoints = timestamps.length;
    
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
              close: close,
              index: i  // Store index for indicator calculation
            };
            EW_trace('YAHOO', `🎯 TARGET HIT! ${ticker} hit ${targetPrice} at ${hitTime.toISOString()}`);
          }
        }
      }
    }
    
    // Calculate indicators for the last data point of the day
    // This ensures we have indicators even if exact hit moment wasn't captured
    let lastValidIndex = -1;
    for (let i = timestamps.length - 1; i >= 0; i--) {
      const dataTime = new Date(timestamps[i] * 1000);
      if (dataTime >= targetDateStart && dataTime <= targetDateEnd && quotes.close[i] !== null) {
        lastValidIndex = i;
        break;
      }
    }
    
    let indicators = null;
    if (lastValidIndex >= 0) {
      indicators = EW_calculateIndicatorsFromYahoo(timestamps, quotes, lastValidIndex);
    }
    
    if (hitTime) {
      // Calculate indicators at the point where strike was hit
      const hitIndicators = EW_calculateIndicatorsFromYahoo(timestamps, quotes, hitData.index);
      
      logEntry.hitDetected = true;
      logEntry.hitPrice = targetPrice;
      logEntry.hitTime = hitTime.toISOString();
      logEntry.dayHigh = dayHigh;
      logEntry.dayLow = dayLow;
      if (hitIndicators) {
        logEntry.indicatorsAtHit = {
          rsi: hitIndicators.rsi,
          vwap: hitIndicators.vwap,
          rvol: hitIndicators.rvol,
          priceVsSMA20: hitIndicators.priceVsSMA20
        };
      }
      EW_logApiCall(logEntry, data);
      
      return {
        hit: true,
        timestamp: hitTime,
        high: hitData.high,
        low: hitData.low,
        close: hitData.close,
        dayHigh: dayHigh,
        dayLow: dayLow,
        interval: interval,
        indicators: hitIndicators  // Include full indicators object
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
    
    // Log the call result
    logEntry.hitDetected = false;
    logEntry.dayHigh = dayHigh === 0 ? null : dayHigh;
    logEntry.dayLow = dayLow === Infinity ? null : dayLow;
    logEntry.lastClose = lastClose;
    EW_logApiCall(logEntry, data);
    
    return { 
      hit: false, 
      dayHigh: dayHigh === 0 ? null : dayHigh,
      dayLow: dayLow === Infinity ? null : dayLow,
      lastClose: lastClose,
      interval: interval,
      dataPoints: timestamps.length,
      indicators: indicators,  // Include indicators even when no exact hit
      message: `Target ${targetPrice} not hit. Range: ${dayLow.toFixed(2)} - ${dayHigh.toFixed(2)}`
    };
    
  } catch (error) {
    EW_trace('YAHOO', `Fetch error: ${error.message}`);
    logEntry.error = error.message;
    logEntry.success = false;
    logEntry.duration = new Date() - callStartTime;
    EW_logApiCall(logEntry);
    throw error;
  }
}

/**
 * Get historical price data for a date range
 * @param {string} ticker - Stock ticker symbol
 * @param {Date} startDate - Start date
 * @param {Date} endDate - End date
 * @param {boolean} includeRaw - Whether to include raw data for indicators
 * @returns {Array|Object} Array of daily price data or object with data and raw
 */
function EW_getYahooHistoricalRange(ticker, startDate, endDate, includeRaw = false) {
  const period1 = Math.floor(startDate.getTime() / 1000);
  const period2 = Math.floor(endDate.getTime() / 1000);
  
  const url = `https://query2.finance.yahoo.com/v8/finance/chart/${ticker}?period1=${period1}&period2=${period2}&interval=1m&events=history`;
  
  // Log API call attempt
  const callStartTime = new Date();
  const logEntry = {
    ticker: ticker,
    interval: '1m',
    startDate: startDate.toISOString().split('T')[0],
    endDate: endDate.toISOString().split('T')[0],
    url: url,
    type: 'historical_range'
  };
  
  try {
    const response = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });
    
    const responseCode = response.getResponseCode();
    logEntry.responseCode = responseCode;
    logEntry.duration = new Date() - callStartTime;
    
    if (responseCode !== 200) {
      logEntry.error = `HTTP ${responseCode}`;
      logEntry.success = false;
      EW_logApiCall(logEntry, data);
      return [];
    }
    
    const data = JSON.parse(response.getContentText());
    
    if (!data.chart || !data.chart.result || data.chart.result.length === 0) {
      logEntry.error = 'No 1-minute data available';
      logEntry.success = false;
      EW_logApiCall(logEntry, data);
      
      // Calculate days since start date to provide context
      const daysSince = Math.floor((new Date() - startDate) / (1000 * 60 * 60 * 24));
      EW_trace('BACKFILL', `${ticker}: No 1-minute data available for period ${startDate.toISOString().split('T')[0]} to ${endDate.toISOString().split('T')[0]} (${daysSince} days ago). 1-minute data typically available for last 7 days only.`);
      
      return [];
    }
    
    const result = data.chart.result[0];
    const timestamps = result.timestamp || [];
    const quotes = result.indicators.quote[0];
    
    // Keep 1-minute data as-is for detailed analysis
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
    
    // Log successful call
    logEntry.success = true;
    logEntry.dataPoints = historicalData.length;
    EW_logApiCall(logEntry, data);
    
    // Log data retrieval details
    if (historicalData.length > 0) {
      const firstDate = historicalData[0].date.toISOString();
      const lastDate = historicalData[historicalData.length - 1].date.toISOString();
      EW_trace('BACKFILL', `${ticker}: Retrieved ${historicalData.length} 1-minute data points from ${firstDate} to ${lastDate}`);
    }
    
    // Return with raw data if requested
    if (includeRaw) {
      return {
        data: historicalData,
        raw: {
          timestamps: timestamps,
          quotes: quotes
        },
        interval: '1m'
      };
    }
    
    return historicalData;
    
  } catch (error) {
    EW_trace('YAHOO', `Error getting historical range for ${ticker}: ${error.message}`);
    logEntry.error = error.message;
    logEntry.success = false;
    logEntry.duration = new Date() - callStartTime;
    EW_logApiCall(logEntry);
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
        const strategyUpper = position.strategy.toUpperCase();
        const isSpread = strategyUpper.includes('SPREAD');
        const isBullSpread = strategyUpper.includes('BULL SPREAD');
        const isBearSpread = strategyUpper.includes('BEAR SPREAD');
        
        let hit = false;
        let hitDate = null;
        let indicators = null;
        
        if (isSpread && position.longStrike && position.shortStrike) {
          // For spreads, we need to check if price is in the profitable range
          const longStrike = parseFloat(position.longStrike);
          const shortStrike = parseFloat(position.shortStrike);
          
          // Get current price data
          const intradayResult = EW_checkStockIntraday(
            position.ticker, 
            longStrike, // Use long strike as target for data fetch
            position.endDate
          );
          
          if (intradayResult.dayHigh && intradayResult.dayLow) {
            if (isBullSpread) {
              // Bull spread is profitable when price is above long strike but below short strike
              hit = intradayResult.dayHigh >= longStrike && intradayResult.dayHigh < shortStrike;
            } else if (isBearSpread) {
              // Bear spread is profitable when price is below long strike but above short strike
              hit = intradayResult.dayLow <= longStrike && intradayResult.dayLow > shortStrike;
            }
            
            if (hit) {
              hitDate = intradayResult.timestamp || position.endDate;
              indicators = intradayResult.indicators;
            } else if (intradayResult.indicators) {
              // Even if spread wasn't hit, keep indicators for potential use
              indicators = intradayResult.indicators;
            }
          }
        } else {
          // Single strike strategies
          const strike = position.strike || position.longStrike || 0;
          
          // Use checkStockIntraday to get 1m data with fallback tracking
          const intradayResult = EW_checkStockIntraday(
            position.ticker, 
            strike, 
            position.endDate
          );
          
          // Determine if strike was hit based on strategy
          const isBullish = strategyUpper.includes('LONG CALL') || (strategyUpper.includes('BULL') && !isSpread);
          const isBearish = strategyUpper.includes('LONG PUT') || (strategyUpper.includes('BEAR') && !isSpread);
          
          if (intradayResult.hit) {
            hit = true;
            hitDate = intradayResult.timestamp;
            indicators = intradayResult.indicators;
          } else if (intradayResult.dayHigh && intradayResult.dayLow) {
            // Check based on day's range
            if (isBullish && intradayResult.dayHigh >= strike) {
              hit = true;
              hitDate = position.endDate;
            } else if (isBearish && intradayResult.dayLow <= strike) {
              hit = true;
              hitDate = position.endDate;
            }
            
            if (hit && !indicators) {
              // Use indicators from the intraday result even if exact hit wasn't detected
              indicators = intradayResult.indicators;
            }
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
          error: intradayResult.error,
          indicators: intradayResult.indicators  // Pass through indicators
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
  
  // Test with previous trading day (not today which may not have data yet)
  const previousTradingDay = new Date();
  const day = previousTradingDay.getDay();
  
  // Adjust to previous trading day
  if (day === 0) previousTradingDay.setDate(previousTradingDay.getDate() - 2); // Sunday -> Friday
  else if (day === 6) previousTradingDay.setDate(previousTradingDay.getDate() - 1); // Saturday -> Friday
  else if (day === 1) previousTradingDay.setDate(previousTradingDay.getDate() - 3); // Monday -> Friday
  else previousTradingDay.setDate(previousTradingDay.getDate() - 1); // Any other day -> previous day
  
  console.log(`Testing with previous trading day: ${previousTradingDay.toDateString()}`);
  
  // Test 1: Check if a strike was hit on previous trading day
  const result1 = EW_checkStockIntraday('IWM', 235.00, previousTradingDay);
  console.log('IWM $235 previous trading day:', result1);
  
  // Test 2: Historical hit from a week ago
  const weekAgo = new Date(previousTradingDay);
  weekAgo.setDate(weekAgo.getDate() - 7);
  const result2 = EW_checkStockIntraday('SPY', 450.00, weekAgo);
  console.log('SPY $450 from week ago:', result2);
  
  // Test 3: Range data for last 30 days
  const rangeStart = new Date();
  rangeStart.setDate(rangeStart.getDate() - 30);
  const rangeEnd = new Date();
  const rangeData = EW_getYahooHistoricalRange('AAPL', rangeStart, rangeEnd);
  console.log(`AAPL historical data points (30 days): ${rangeData.length}`);
  
  // Test 4: Direct API test with known working date
  console.log('\n=== Direct API Test ===');
  const testResult = EW_fetchYahooData('IWM', 235, previousTradingDay, '1m');
  console.log('Direct fetch result:', testResult);
  
  return {
    previousTradingDay: result1,
    historical: result2,
    rangeDataPoints: rangeData.length,
    directApiTest: testResult
  };
}

/**
 * Calculate technical indicators from Yahoo price data
 * @param {Array} timestamps - Array of timestamps
 * @param {Object} quotes - Quote data with high, low, close, volume arrays
 * @param {number} targetIndex - Index where strike was hit (optional)
 * @returns {Object} Technical indicators at target time or latest values
 */
function EW_calculateIndicatorsFromYahoo(timestamps, quotes, targetIndex = null) {
  try {
    const closes = quotes.close || [];
    const highs = quotes.high || [];
    const lows = quotes.low || [];
    const volumes = quotes.volume || [];
    
    if (closes.length < 20) {
      return null; // Not enough data for meaningful indicators
    }
    
    // If targetIndex provided, calculate indicators up to that point
    const endIndex = targetIndex !== null ? Math.min(targetIndex + 1, closes.length) : closes.length;
    
    // Get data up to target point
    const closesSlice = closes.slice(0, endIndex);
    const highsSlice = highs.slice(0, endIndex);
    const lowsSlice = lows.slice(0, endIndex);
    const volumesSlice = volumes.slice(0, endIndex);
    
    // Calculate indicators
    const rsi = EW_calculateRSI(closesSlice, 14);
    const sma20 = EW_calculateSMA(closesSlice, 20);
    const sma50 = EW_calculateSMA(closesSlice, 50);
    const ema9 = EW_calculateEMA(closesSlice, 9);
    const ema21 = EW_calculateEMA(closesSlice, 21);
    const vwap = EW_calculateVWAP(closesSlice, highsSlice, lowsSlice, volumesSlice);
    const atr = EW_calculateATR(highsSlice, lowsSlice, closesSlice, 14);
    
    // Calculate relative volume (current vs 20-period average)
    const currentVolume = volumesSlice[volumesSlice.length - 1];
    const avgVolume = volumesSlice.slice(-20).reduce((a, b) => a + b, 0) / Math.min(20, volumesSlice.length);
    const rvol = currentVolume / avgVolume;
    
    // Price position relative to indicators
    const currentPrice = closesSlice[closesSlice.length - 1];
    const priceVsSMA20 = sma20 ? ((currentPrice - sma20) / sma20) * 100 : null;
    const priceVsVWAP = vwap ? ((currentPrice - vwap) / vwap) * 100 : null;
    
    return {
      price: currentPrice,
      rsi: rsi,
      sma20: sma20,
      sma50: sma50,
      ema9: ema9,
      ema21: ema21,
      vwap: vwap,
      rvol: rvol,
      atr: atr,
      priceVsSMA20: priceVsSMA20,
      priceVsVWAP: priceVsVWAP,
      volume: currentVolume,
      timestamp: targetIndex !== null ? new Date(timestamps[targetIndex] * 1000) : new Date()
    };
    
  } catch (error) {
    EW_trace('YAHOO', `Error calculating indicators: ${error.message}`);
    return null;
  }
}

/**
 * Calculate Simple Moving Average
 * @param {Array} prices - Array of prices
 * @param {number} period - Period for SMA
 * @returns {number} SMA value
 */
function EW_calculateSMA(prices, period) {
  if (prices.length < period) return null;
  const slice = prices.slice(-period);
  return slice.reduce((a, b) => a + b, 0) / period;
}

/**
 * Calculate Exponential Moving Average
 * @param {Array} prices - Array of prices
 * @param {number} period - Period for EMA
 * @returns {number} EMA value
 */
function EW_calculateEMA(prices, period) {
  if (prices.length < period) return null;
  
  const multiplier = 2 / (period + 1);
  let ema = prices.slice(0, period).reduce((a, b) => a + b, 0) / period;
  
  for (let i = period; i < prices.length; i++) {
    ema = (prices[i] - ema) * multiplier + ema;
  }
  
  return ema;
}

/**
 * Calculate RSI (Relative Strength Index)
 * @param {Array} closes - Array of closing prices
 * @param {number} period - RSI period (default: 14)
 * @returns {number} RSI value between 0 and 100
 */
function EW_calculateRSI(closes, period = 14) {
  if (closes.length < period + 1) return null;
  
  const changes = [];
  for (let i = 1; i < closes.length; i++) {
    changes.push(closes[i] - closes[i - 1]);
  }
  
  let avgGain = 0;
  let avgLoss = 0;
  
  // Initial calculation
  for (let i = 0; i < period; i++) {
    if (changes[i] > 0) avgGain += changes[i];
    else avgLoss -= changes[i];
  }
  
  avgGain /= period;
  avgLoss /= period;
  
  // Calculate RSI for the latest period
  for (let i = period; i < changes.length; i++) {
    const change = changes[i];
    const gain = change > 0 ? change : 0;
    const loss = change < 0 ? -change : 0;
    
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
  }
  
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

/**
 * Calculate VWAP (Volume Weighted Average Price)
 * @param {Array} closes - Array of closing prices
 * @param {Array} highs - Array of high prices  
 * @param {Array} lows - Array of low prices
 * @param {Array} volumes - Array of volume data
 * @returns {number} VWAP value
 */
function EW_calculateVWAP(closes, highs, lows, volumes) {
  if (closes.length !== highs.length || closes.length !== lows.length || closes.length !== volumes.length) {
    return null;
  }
  
  let totalVolume = 0;
  let totalVolumePrice = 0;
  
  for (let i = 0; i < closes.length; i++) {
    const typicalPrice = (highs[i] + lows[i] + closes[i]) / 3;
    const volume = volumes[i];
    
    totalVolumePrice += typicalPrice * volume;
    totalVolume += volume;
  }
  
  return totalVolume > 0 ? totalVolumePrice / totalVolume : null;
}

/**
 * Calculate ATR (Average True Range)
 * @param {Array} highs - Array of high prices
 * @param {Array} lows - Array of low prices
 * @param {Array} closes - Array of closing prices
 * @param {number} period - ATR period (default: 14)
 * @returns {number} ATR value
 */
function EW_calculateATR(highs, lows, closes, period = 14) {
  if (highs.length < period + 1) return null;
  
  const trueRanges = [];
  
  for (let i = 1; i < highs.length; i++) {
    const high = highs[i];
    const low = lows[i];
    const prevClose = closes[i - 1];
    
    const tr1 = high - low;
    const tr2 = Math.abs(high - prevClose);
    const tr3 = Math.abs(low - prevClose);
    
    trueRanges.push(Math.max(tr1, tr2, tr3));
  }
  
  // Calculate simple moving average of true ranges
  const recentTR = trueRanges.slice(-period);
  return recentTR.reduce((a, b) => a + b, 0) / recentTR.length;
}