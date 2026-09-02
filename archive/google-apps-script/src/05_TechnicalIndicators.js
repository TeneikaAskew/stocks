/**
 * Technical Indicators Module
 * Consolidated library of technical indicator calculations
 * Eliminates duplication across the codebase
 */

/**
 * Technical Indicators class with all indicator calculations
 */
class TechnicalIndicators {
  
  /**
   * Calculate Simple Moving Average (SMA)
   * @param {number[]} prices - Array of prices
   * @param {number} period - Period for SMA calculation
   * @returns {number|null} SMA value or null if insufficient data
   */
  static SMA(prices, period) {
    if (!prices || prices.length < period) return null;
    
    const validPrices = prices.filter(p => p !== null && !isNaN(p));
    if (validPrices.length < period) return null;
    
    const sum = validPrices.slice(-period).reduce((a, b) => a + b, 0);
    return sum / period;
  }
  
  /**
   * Calculate Exponential Moving Average (EMA)
   * @param {number[]} prices - Array of prices
   * @param {number} period - Period for EMA calculation
   * @returns {number|null} EMA value or null if insufficient data
   */
  static EMA(prices, period) {
    if (!prices || prices.length < period) return null;
    
    const validPrices = prices.filter(p => p !== null && !isNaN(p));
    if (validPrices.length < period) return null;
    
    const multiplier = 2 / (period + 1);
    
    // Start with SMA for initial EMA
    let ema = this.SMA(validPrices.slice(0, period), period);
    if (ema === null) return null;
    
    // Calculate EMA for remaining prices
    for (let i = period; i < validPrices.length; i++) {
      ema = (validPrices[i] - ema) * multiplier + ema;
    }
    
    return ema;
  }
  
  /**
   * Calculate Relative Strength Index (RSI)
   * @param {number[]} closes - Array of closing prices
   * @param {number} period - Period for RSI calculation (default: 14)
   * @returns {number|null} RSI value (0-100) or null if insufficient data
   */
  static RSI(closes, period = 14) {
    if (!closes || closes.length < period + 1) return null;
    
    const validCloses = closes.filter(c => c !== null && !isNaN(c));
    if (validCloses.length < period + 1) return null;
    
    const changes = [];
    for (let i = 1; i < validCloses.length; i++) {
      changes.push(validCloses[i] - validCloses[i - 1]);
    }
    
    let gains = 0;
    let losses = 0;
    
    // Initial average gain/loss
    for (let i = 0; i < period; i++) {
      if (changes[i] > 0) {
        gains += changes[i];
      } else {
        losses -= changes[i];
      }
    }
    
    let avgGain = gains / period;
    let avgLoss = losses / period;
    
    // Smooth the averages
    for (let i = period; i < changes.length; i++) {
      if (changes[i] > 0) {
        avgGain = (avgGain * (period - 1) + changes[i]) / period;
        avgLoss = (avgLoss * (period - 1)) / period;
      } else {
        avgGain = (avgGain * (period - 1)) / period;
        avgLoss = (avgLoss * (period - 1) - changes[i]) / period;
      }
    }
    
    if (avgLoss === 0) return 100;
    
    const rs = avgGain / avgLoss;
    const rsi = 100 - (100 / (1 + rs));
    
    return rsi;
  }
  
  /**
   * Calculate Volume Weighted Average Price (VWAP)
   * @param {number[]} closes - Array of closing prices
   * @param {number[]} highs - Array of high prices
   * @param {number[]} lows - Array of low prices
   * @param {number[]} volumes - Array of volumes
   * @returns {number|null} VWAP value or null if insufficient data
   */
  static VWAP(closes, highs, lows, volumes) {
    if (!closes || !highs || !lows || !volumes) return null;
    if (closes.length === 0 || highs.length === 0 || lows.length === 0 || volumes.length === 0) return null;
    
    // Ensure all arrays have same length
    const minLength = Math.min(closes.length, highs.length, lows.length, volumes.length);
    if (minLength === 0) return null;
    
    let totalPV = 0;  // Price * Volume
    let totalVolume = 0;
    
    for (let i = 0; i < minLength; i++) {
      if (closes[i] !== null && highs[i] !== null && lows[i] !== null && volumes[i] !== null) {
        const typicalPrice = (parseFloat(highs[i]) + parseFloat(lows[i]) + parseFloat(closes[i])) / 3;
        const volume = parseFloat(volumes[i]);
        
        if (!isNaN(typicalPrice) && !isNaN(volume)) {
          totalPV += typicalPrice * volume;
          totalVolume += volume;
        }
      }
    }
    
    if (totalVolume === 0) return null;
    
    return totalPV / totalVolume;
  }
  
  /**
   * Calculate Average True Range (ATR)
   * @param {number[]} highs - Array of high prices
   * @param {number[]} lows - Array of low prices
   * @param {number[]} closes - Array of closing prices
   * @param {number} period - Period for ATR calculation (default: 14)
   * @returns {number|null} ATR value or null if insufficient data
   */
  static ATR(highs, lows, closes, period = 14) {
    if (!highs || !lows || !closes) return null;
    if (highs.length < period + 1 || lows.length < period + 1 || closes.length < period + 1) return null;
    
    const trueRanges = [];
    
    // Calculate True Range for each period
    for (let i = 1; i < highs.length; i++) {
      if (highs[i] !== null && lows[i] !== null && closes[i-1] !== null) {
        const high = parseFloat(highs[i]);
        const low = parseFloat(lows[i]);
        const prevClose = parseFloat(closes[i-1]);
        
        const tr = Math.max(
          high - low,
          Math.abs(high - prevClose),
          Math.abs(low - prevClose)
        );
        
        trueRanges.push(tr);
      }
    }
    
    if (trueRanges.length < period) return null;
    
    // Calculate initial ATR (simple average)
    let atr = trueRanges.slice(0, period).reduce((a, b) => a + b, 0) / period;
    
    // Smooth the ATR (Wilder's smoothing)
    for (let i = period; i < trueRanges.length; i++) {
      atr = ((atr * (period - 1)) + trueRanges[i]) / period;
    }
    
    return atr;
  }
  
  /**
   * Calculate Relative Volume (RVOL)
   * @param {number} currentVolume - Current volume
   * @param {number[]} historicalVolumes - Array of historical volumes for same time period
   * @returns {number|null} RVOL ratio or null if insufficient data
   */
  static RVOL(currentVolume, historicalVolumes) {
    if (!currentVolume || !historicalVolumes || historicalVolumes.length === 0) return null;
    
    const validVolumes = historicalVolumes.filter(v => v !== null && !isNaN(v) && v > 0);
    if (validVolumes.length === 0) return null;
    
    const avgVolume = validVolumes.reduce((a, b) => a + b, 0) / validVolumes.length;
    if (avgVolume === 0) return null;
    
    return currentVolume / avgVolume;
  }
  
  /**
   * Calculate all indicators at once
   * @param {Object} data - Object containing price and volume data
   * @returns {Object} Object with all calculated indicators
   */
  static calculateAll(data) {
    const { closes, highs, lows, volumes } = data;
    
    if (!closes || closes.length === 0) {
      return {
        rsi: null,
        sma20: null,
        sma50: null,
        ema9: null,
        ema21: null,
        vwap: null,
        atr: null,
        priceVsSMA20: null,
        priceVsVWAP: null
      };
    }
    
    const lastClose = closes[closes.length - 1];
    const sma20 = this.SMA(closes, 20);
    const sma50 = this.SMA(closes, 50);
    const vwap = this.VWAP(closes, highs, lows, volumes);
    
    return {
      rsi: this.RSI(closes, 14),
      sma20: sma20,
      sma50: sma50,
      ema9: this.EMA(closes, 9),
      ema21: this.EMA(closes, 21),
      vwap: vwap,
      atr: this.ATR(highs, lows, closes, 14),
      priceVsSMA20: sma20 ? ((lastClose - sma20) / sma20 * 100) : null,
      priceVsVWAP: vwap ? ((lastClose - vwap) / vwap * 100) : null
    };
  }
  
  /**
   * Validate indicator values are within expected ranges
   * @param {Object} indicators - Object with indicator values
   * @returns {Object} Object with validated indicators
   */
  static validate(indicators) {
    const validated = { ...indicators };
    
    // RSI should be between 0 and 100
    if (validated.rsi !== null && (validated.rsi < 0 || validated.rsi > 100)) {
      console.warn(`Invalid RSI value: ${validated.rsi}`);
      validated.rsi = Math.max(0, Math.min(100, validated.rsi));
    }
    
    // Price-based indicators should be positive
    ['sma20', 'sma50', 'ema9', 'ema21', 'vwap', 'atr'].forEach(key => {
      if (validated[key] !== null && validated[key] < 0) {
        console.warn(`Invalid ${key} value: ${validated[key]}`);
        validated[key] = null;
      }
    });
    
    // Percentage differences can be negative but should be reasonable
    ['priceVsSMA20', 'priceVsVWAP'].forEach(key => {
      if (validated[key] !== null && Math.abs(validated[key]) > 100) {
        console.warn(`Unusual ${key} value: ${validated[key]}%`);
      }
    });
    
    return validated;
  }
}

// Make functions available globally for backward compatibility
function EW_calculateRSI(closes, period = 14) {
  return TechnicalIndicators.RSI(closes, period);
}

function EW_calculateSMA(prices, period) {
  return TechnicalIndicators.SMA(prices, period);
}

function EW_calculateEMA(prices, period) {
  return TechnicalIndicators.EMA(prices, period);
}

function EW_calculateVWAP(closes, highs, lows, volumes) {
  return TechnicalIndicators.VWAP(closes, highs, lows, volumes);
}

function EW_calculateATR(highs, lows, closes, period = 14) {
  return TechnicalIndicators.ATR(highs, lows, closes, period);
}

/**
 * Calculate indicators for a specific ticker using Yahoo data
 * @param {string} ticker - Stock ticker symbol
 * @param {Date} date - Date to calculate indicators for
 * @returns {Object} Calculated indicators or error
 */
function EW_getIndicatorsForDate(ticker, date) {
  try {
    // Get 50 days of data to calculate indicators properly
    const endDate = new Date(date);
    const startDate = new Date(date);
    startDate.setDate(startDate.getDate() - 50);
    
    // Fetch Yahoo data
    const data = EW_fetchYahooHistoricalData(ticker, startDate, endDate);
    
    if (!data || data.length === 0) {
      return { error: 'No data available' };
    }
    
    // Extract price arrays
    const closes = data.map(d => d.close);
    const highs = data.map(d => d.high);
    const lows = data.map(d => d.low);
    const volumes = data.map(d => d.volume);
    
    // Calculate all indicators
    const indicators = TechnicalIndicators.calculateAll({
      closes: closes,
      highs: highs,
      lows: lows,
      volumes: volumes
    });
    
    // Validate and return
    return TechnicalIndicators.validate(indicators);
    
  } catch (error) {
    console.error(`Error calculating indicators for ${ticker}: ${error.message}`);
    return { error: error.message };
  }
}

/**
 * Test function to verify indicator calculations
 */
function TEST_TechnicalIndicators() {
  console.log('Testing Technical Indicators Module...\n');
  
  // Test data
  const testPrices = [100, 102, 101, 103, 105, 104, 106, 108, 107, 109, 110, 108, 111, 112, 110];
  const testVolumes = [1000, 1100, 900, 1200, 1300, 1000, 1400, 1500, 1100, 1600, 1700, 1200, 1800, 1900, 1300];
  
  console.log('Test Data:', testPrices);
  
  // Test SMA
  const sma5 = TechnicalIndicators.SMA(testPrices, 5);
  console.log(`SMA(5): ${sma5?.toFixed(2)}`);
  
  // Test EMA
  const ema5 = TechnicalIndicators.EMA(testPrices, 5);
  console.log(`EMA(5): ${ema5?.toFixed(2)}`);
  
  // Test RSI
  const rsi = TechnicalIndicators.RSI(testPrices, 14);
  console.log(`RSI(14): ${rsi?.toFixed(2)}`);
  
  // Test VWAP
  const vwap = TechnicalIndicators.VWAP(
    testPrices,
    testPrices.map(p => p + 1), // highs
    testPrices.map(p => p - 1), // lows
    testVolumes
  );
  console.log(`VWAP: ${vwap?.toFixed(2)}`);
  
  // Test ATR
  const atr = TechnicalIndicators.ATR(
    testPrices.map(p => p + 1), // highs
    testPrices.map(p => p - 1), // lows
    testPrices,
    14
  );
  console.log(`ATR(14): ${atr?.toFixed(2)}`);
  
  // Test calculateAll
  console.log('\nCalculating all indicators:');
  const allIndicators = TechnicalIndicators.calculateAll({
    closes: testPrices,
    highs: testPrices.map(p => p + 1),
    lows: testPrices.map(p => p - 1),
    volumes: testVolumes
  });
  
  console.log(JSON.stringify(allIndicators, null, 2));
  
  console.log('\n✅ Technical Indicators Test Complete');
}