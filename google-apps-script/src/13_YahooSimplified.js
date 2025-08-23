/**
 * Simplified Yahoo Finance Functions
 * Uses the exact format that works from the example
 */

/**
 * Get 1-minute data for a specific date
 * @param {string} ticker - Stock ticker
 * @param {Date} date - Date to check
 * @returns {Object} Price data for the day
 */
function EW_getYahoo1MinuteData(ticker, date) {
  // Set date to start of trading day (9:30 AM ET)
  const startDate = new Date(date);
  startDate.setHours(9, 30, 0, 0);
  
  // Set to end of trading day (4:00 PM ET)  
  const endDate = new Date(date);
  endDate.setHours(16, 0, 0, 0);
  
  // Convert to Unix timestamps
  const period1 = Math.floor(startDate.getTime() / 1000);
  const period2 = Math.floor(endDate.getTime() / 1000);
  
  const url = `https://query2.finance.yahoo.com/v8/finance/chart/${ticker}?period1=${period1}&period2=${period2}&interval=1m&events=history`;
  
  console.log(`Fetching ${ticker} for ${date.toDateString()}`);
  console.log(`URL: ${url}`);
  
  try {
    const response = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });
    
    const responseCode = response.getResponseCode();
    if (responseCode !== 200) {
      console.error(`HTTP ${responseCode}: ${response.getContentText()}`);
      return null;
    }
    
    const data = JSON.parse(response.getContentText());
    
    if (!data.chart || !data.chart.result || data.chart.result.length === 0) {
      console.error('No data in response');
      return null;
    }
    
    const result = data.chart.result[0];
    const timestamps = result.timestamp;
    const quotes = result.indicators.quote[0];
    
    if (!timestamps || timestamps.length === 0) {
      console.error('No price data available');
      return null;
    }
    
    // Find day's high and low
    let dayHigh = 0;
    let dayLow = Infinity;
    
    for (let i = 0; i < timestamps.length; i++) {
      if (quotes.high[i] !== null) dayHigh = Math.max(dayHigh, quotes.high[i]);
      if (quotes.low[i] !== null) dayLow = Math.min(dayLow, quotes.low[i]);
    }
    
    return {
      ticker: ticker,
      date: date.toDateString(),
      dataPoints: timestamps.length,
      dayHigh: dayHigh,
      dayLow: dayLow,
      firstTime: new Date(timestamps[0] * 1000),
      lastTime: new Date(timestamps[timestamps.length - 1] * 1000),
      quotes: quotes,
      timestamps: timestamps
    };
    
  } catch (error) {
    console.error(`Error fetching ${ticker}: ${error.message}`);
    return null;
  }
}

/**
 * Check if a strike price was hit on a specific date
 * @param {string} ticker - Stock ticker
 * @param {number} strikePrice - Strike price to check
 * @param {Date} date - Date to check
 * @returns {Object} Hit status and details
 */
function EW_checkStrikeSimple(ticker, strikePrice, date) {
  const data = EW_getYahoo1MinuteData(ticker, date);
  
  if (!data) {
    return {
      hit: false,
      error: 'No data available',
      ticker: ticker,
      date: date.toDateString()
    };
  }
  
  // Check if strike was hit
  let hitTime = null;
  let hitIndex = -1;
  
  for (let i = 0; i < data.timestamps.length; i++) {
    const high = data.quotes.high[i];
    const low = data.quotes.low[i];
    
    if (high !== null && low !== null && low <= strikePrice && strikePrice <= high) {
      hitTime = new Date(data.timestamps[i] * 1000);
      hitIndex = i;
      break;
    }
  }
  
  return {
    hit: hitTime !== null,
    hitTime: hitTime,
    dayHigh: data.dayHigh,
    dayLow: data.dayLow,
    strikePrice: strikePrice,
    ticker: ticker,
    date: date.toDateString(),
    dataPoints: data.dataPoints,
    message: hitTime ? 
      `Strike ${strikePrice} hit at ${hitTime.toLocaleTimeString()}` : 
      `Strike ${strikePrice} not hit. Day range: ${data.dayLow.toFixed(2)} - ${data.dayHigh.toFixed(2)}`
  };
}

/**
 * Test the simplified functions
 */
function EW_testSimplified() {
  console.log('=== Testing Simplified Yahoo Functions ===');
  
  // Test with last Friday (or previous trading day)
  const testDate = new Date();
  const day = testDate.getDay();
  
  // Adjust to last Friday if today is weekend or Monday
  if (day === 0) testDate.setDate(testDate.getDate() - 2); // Sunday -> Friday
  else if (day === 6) testDate.setDate(testDate.getDate() - 1); // Saturday -> Friday  
  else if (day === 1) testDate.setDate(testDate.getDate() - 3); // Monday -> Friday
  else testDate.setDate(testDate.getDate() - 1); // Any other day -> previous day
  
  console.log(`Testing with date: ${testDate.toDateString()}`);
  
  // Test data fetch
  const data = EW_getYahoo1MinuteData('IWM', testDate);
  if (data) {
    console.log(`Got ${data.dataPoints} data points`);
    console.log(`Day range: ${data.dayLow.toFixed(2)} - ${data.dayHigh.toFixed(2)}`);
    console.log(`Trading hours: ${data.firstTime.toLocaleTimeString()} - ${data.lastTime.toLocaleTimeString()}`);
  }
  
  // Test strike check
  const strikeTest = EW_checkStrikeSimple('IWM', 235, testDate);
  console.log('\nStrike test result:', strikeTest);
  
  return strikeTest;
}