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
      EW_logApiCall(logEntry);
      return { hit: false, error: `HTTP ${responseCode}` };
    }
    
    const data = JSON.parse(response.getContentText());
    
    // Check for errors in response
    if (data.chart && data.chart.error) {
      EW_trace('YAHOO', `API Error: ${data.chart.error.description}`);
      logEntry.error = data.chart.error.description;
      logEntry.success = false;
      EW_logApiCall(logEntry);
      return { hit: false, error: data.chart.error.description };
    }
    
    if (!data.chart || !data.chart.result || data.chart.result.length === 0) {
      EW_trace('YAHOO', 'No data in response');
      logEntry.error = 'No data available';
      logEntry.success = false;
      EW_logApiCall(logEntry);
      return { hit: false, error: 'No data available' };
    }
    
    const result = data.chart.result[0];
    const timestamps = result.timestamp;
    const quotes = result.indicators.quote[0];
    
    if (!timestamps || timestamps.length === 0) {
      EW_trace('YAHOO', 'No timestamps in response');
      logEntry.error = 'No price data available';
      logEntry.success = false;
      EW_logApiCall(logEntry);
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
              close: close
            };
            EW_trace('YAHOO', `🎯 TARGET HIT! ${ticker} hit ${targetPrice} at ${hitTime.toISOString()}`);
          }
        }
      }
    }
    
    if (hitTime) {
      logEntry.hitDetected = true;
      logEntry.hitPrice = targetPrice;
      logEntry.hitTime = hitTime.toISOString();
      logEntry.dayHigh = dayHigh;
      logEntry.dayLow = dayLow;
      EW_logApiCall(logEntry);
      
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
    
    // Log the call result
    logEntry.hitDetected = false;
    logEntry.dayHigh = dayHigh === 0 ? null : dayHigh;
    logEntry.dayLow = dayLow === Infinity ? null : dayLow;
    logEntry.lastClose = lastClose;
    EW_logApiCall(logEntry);
    
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
 * @returns {Array} Array of daily price data
 */
function EW_getYahooHistoricalRange(ticker, startDate, endDate) {
  const period1 = Math.floor(startDate.getTime() / 1000);
  const period2 = Math.floor(endDate.getTime() / 1000);
  
  const url = `https://query2.finance.yahoo.com/v8/finance/chart/${ticker}?period1=${period1}&period2=${period2}&interval=1d&events=history`;
  
  // Log API call attempt
  const callStartTime = new Date();
  const logEntry = {
    ticker: ticker,
    interval: '1d',
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
      EW_logApiCall(logEntry);
      return [];
    }
    
    const data = JSON.parse(response.getContentText());
    
    if (!data.chart || !data.chart.result || data.chart.result.length === 0) {
      logEntry.error = 'No data available';
      logEntry.success = false;
      EW_logApiCall(logEntry);
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
    
    // Log successful call
    logEntry.success = true;
    logEntry.dataPoints = historicalData.length;
    EW_logApiCall(logEntry);
    
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
  const result1 = EW_checkStockIntraday('IWM', 233.00, today);
  console.log('IWM $233 today:', result1);
  
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

/**
 * Debug function to test direct API call
 */
function EW_debugYahooApi() {
  console.log('=== Debug Yahoo API Call ===');
  
  // Test with exact timestamps like in the example
  const ticker = 'IWM';
  const period1 = 1755849600; // Example timestamp from user
  const period2 = 1755936000; // Example timestamp from user
  const interval = '1m';
  
  // Convert timestamps to dates to see what they represent
  console.log(`Period1: ${new Date(period1 * 1000).toISOString()} (${period1})`);
  console.log(`Period2: ${new Date(period2 * 1000).toISOString()} (${period2})`);
  
  const url = `https://query2.finance.yahoo.com/v8/finance/chart/${ticker}?period1=${period1}&period2=${period2}&interval=${interval}&events=history`;
  console.log(`Debug URL: ${url}`);
  
  try {
    const response = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });
    
    const responseCode = response.getResponseCode();
    console.log(`Response Code: ${responseCode}`);
    
    if (responseCode === 200) {
      const data = JSON.parse(response.getContentText());
      console.log(`Success! Got ${data.chart.result[0].timestamp.length} data points`);
      console.log(`First timestamp: ${new Date(data.chart.result[0].timestamp[0] * 1000).toISOString()}`);
      console.log(`Last timestamp: ${new Date(data.chart.result[0].timestamp[data.chart.result[0].timestamp.length - 1] * 1000).toISOString()}`);
      
      // Check if target price was hit
      const quotes = data.chart.result[0].indicators.quote[0];
      let targetHit = false;
      const targetPrice = 235;
      
      for (let i = 0; i < data.chart.result[0].timestamp.length; i++) {
        if (quotes.high[i] >= targetPrice && quotes.low[i] <= targetPrice) {
          console.log(`Target ${targetPrice} was hit at ${new Date(data.chart.result[0].timestamp[i] * 1000).toISOString()}`);
          targetHit = true;
          break;
        }
      }
      
      if (!targetHit) {
        console.log(`Target ${targetPrice} was NOT hit during this period`);
      }
    } else {
      console.error(`Failed with status ${responseCode}`);
      console.error(`Response: ${response.getContentText()}`);
    }
  } catch (error) {
    console.error(`Error: ${error.message}`);
  }
  
  // Test with yesterday to ensure we have market data
  console.log('\n=== Testing with yesterday ===');
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  // Skip weekends
  if (yesterday.getDay() === 0) yesterday.setDate(yesterday.getDate() - 2); // Sunday -> Friday
  if (yesterday.getDay() === 6) yesterday.setDate(yesterday.getDate() - 1); // Saturday -> Friday
  
  console.log(`Testing date: ${yesterday.toISOString()}`);
  const result = EW_fetchYahooData('IWM', 235, yesterday, '1m');
  console.log('Result:', result);
}