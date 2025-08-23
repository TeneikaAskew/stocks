/**
 * Array Building Functions
 * Shared functions for building and managing arrays used in both active tracking and backfill
 * These functions ensure consistency in how arrays are built and formatted across the system
 * 
 * KEY CONCEPTS:
 * 1. All arrays are Day0-Day5 indexed (6 days total)
 * 2. Arrays can be built incrementally (day by day) or all at once
 * 3. JSON strings are used for storage in Google Sheets
 * 4. Null values indicate days not yet reached or no data
 * 
 * USAGE PATTERNS:
 * 
 * For Active Tracking (day by day):
 *   - Use EW_buildMaxFavorableArray() to add each day's value
 *   - Use EW_buildMinUnfavorableArray() for unfavorable moves
 *   - Use EW_buildStrikeHitArray() to track strike hits
 *   - Use EW_buildIndicatorArraysForDay() for daily indicators
 * 
 * For Backfill (all at once):
 *   - Use EW_formatIndicatorArraysForStorage() to convert complete arrays
 *   - Analysis functions already provide complete arrays
 * 
 * For Both:
 *   - Use EW_updateHistoricalHighLow() to track lifetime high/low
 *   - Use EW_calculateRiskRewardFromArrays() for risk/reward ratio
 *   - Use EW_determineExpResult() for WIN/LOSS determination
 */

/**
 * Build or update Max_Favorable array for a position
 * @param {Array} existingArray - Current array of max favorable values (can be empty)
 * @param {number} dayIndex - Day index (0-5)
 * @param {string} strategy - Strategy name
 * @param {number} strike - Strike price
 * @param {number} dayHigh - Day's high price
 * @param {number} dayLow - Day's low price
 * @returns {Array} Updated array with new value at dayIndex
 */
function EW_buildMaxFavorableArray(existingArray = [], dayIndex, strategy, strike, dayHigh, dayLow) {
  if (!strike || dayIndex < 0 || dayIndex > 5) return existingArray;
  
  // Ensure array has correct length
  const array = existingArray.slice();
  while (array.length <= dayIndex) {
    array.push(null);
  }
  
  // Calculate max favorable for this day
  const maxFav = EW_calculateMaxFavorableForDay(strategy, strike, dayHigh, dayLow);
  if (maxFav !== null) {
    array[dayIndex] = maxFav;
  }
  
  return array;
}

/**
 * Build or update Min_Unfavorable array for a position
 * @param {Array} existingArray - Current array of min unfavorable values (can be empty)
 * @param {number} dayIndex - Day index (0-5)
 * @param {string} strategy - Strategy name
 * @param {number} strike - Strike price
 * @param {number} dayHigh - Day's high price
 * @param {number} dayLow - Day's low price
 * @returns {Array} Updated array with new value at dayIndex
 */
function EW_buildMinUnfavorableArray(existingArray = [], dayIndex, strategy, strike, dayHigh, dayLow) {
  if (!strike || dayIndex < 0 || dayIndex > 5) return existingArray;
  
  // Ensure array has correct length
  const array = existingArray.slice();
  while (array.length <= dayIndex) {
    array.push(null);
  }
  
  // Calculate min unfavorable for this day
  const minUnfav = EW_calculateMinUnfavorableForDay(strategy, strike, dayHigh, dayLow);
  if (minUnfav !== null) {
    array[dayIndex] = minUnfav;
  }
  
  return array;
}

/**
 * Build or update Strike_Hit array with percentage moves
 * @param {Array} existingArray - Current strike hit array (can be empty)
 * @param {number} dayIndex - Day index (0-5)
 * @param {string} strategy - Strategy name
 * @param {number} strike - Strike price
 * @param {number} dayHigh - Day's high price
 * @param {number} dayLow - Day's low price
 * @param {boolean} strikeHit - Whether strike was hit this day
 * @returns {Array} Updated array with new value at dayIndex
 */
function EW_buildStrikeHitArray(existingArray = [], dayIndex, strategy, strike, dayHigh, dayLow, strikeHit) {
  if (!strike || dayIndex < 0 || dayIndex > 5) return existingArray;
  
  // Ensure array has correct length
  const array = existingArray.slice();
  while (array.length <= dayIndex) {
    array.push(null);
  }
  
  if (strikeHit) {
    // Calculate percentage move when strike was hit
    const strategyUpper = strategy.toUpperCase();
    const isBullish = strategyUpper.includes('BULL') || strategyUpper.includes('LONG CALL');
    const isBearish = strategyUpper.includes('BEAR') || strategyUpper.includes('LONG PUT');
    
    let percentMove = null;
    if (isBullish) {
      // For bullish: use high price vs strike
      percentMove = ((dayHigh - strike) / strike * 100).toFixed(2);
    } else if (isBearish) {
      // For bearish: use low price vs strike
      percentMove = ((strike - dayLow) / strike * 100).toFixed(2);
    }
    
    array[dayIndex] = percentMove || "HIT";
  } else {
    array[dayIndex] = "NO";
  }
  
  return array;
}

/**
 * Build complete indicator arrays object for a position (day by day)
 * @param {Object} existingIndicators - Current indicator arrays object
 * @param {number} dayIndex - Day index (0-5)
 * @param {Object} dayIndicators - Indicators for this specific day
 * @returns {Object} Updated indicators object with all arrays
 */
function EW_buildIndicatorArraysForDay(existingIndicators = {}, dayIndex, dayIndicators) {
  if (dayIndex < 0 || dayIndex > 5 || !dayIndicators) return existingIndicators;
  
  // Initialize arrays if not present
  const indicators = {
    rsi: existingIndicators.rsi || [],
    sma20: existingIndicators.sma20 || [],
    sma50: existingIndicators.sma50 || [],
    ema9: existingIndicators.ema9 || [],
    ema21: existingIndicators.ema21 || [],
    vwap: existingIndicators.vwap || [],
    rvol: existingIndicators.rvol || [],
    atr: existingIndicators.atr || [],
    priceVsSMA20: existingIndicators.priceVsSMA20 || [],
    priceVsVWAP: existingIndicators.priceVsVWAP || []
  };
  
  // Ensure all arrays have correct length
  Object.keys(indicators).forEach(key => {
    while (indicators[key].length <= dayIndex) {
      indicators[key].push(null);
    }
  });
  
  // Update values for this day
  if (dayIndicators.rsi !== null && dayIndicators.rsi !== undefined) {
    indicators.rsi[dayIndex] = parseFloat(dayIndicators.rsi).toFixed(2);
  }
  if (dayIndicators.sma20 !== null && dayIndicators.sma20 !== undefined) {
    indicators.sma20[dayIndex] = parseFloat(dayIndicators.sma20).toFixed(2);
  }
  if (dayIndicators.sma50 !== null && dayIndicators.sma50 !== undefined) {
    indicators.sma50[dayIndex] = parseFloat(dayIndicators.sma50).toFixed(2);
  }
  if (dayIndicators.ema9 !== null && dayIndicators.ema9 !== undefined) {
    indicators.ema9[dayIndex] = parseFloat(dayIndicators.ema9).toFixed(2);
  }
  if (dayIndicators.ema21 !== null && dayIndicators.ema21 !== undefined) {
    indicators.ema21[dayIndex] = parseFloat(dayIndicators.ema21).toFixed(2);
  }
  if (dayIndicators.vwap !== null && dayIndicators.vwap !== undefined) {
    indicators.vwap[dayIndex] = parseFloat(dayIndicators.vwap).toFixed(2);
  }
  if (dayIndicators.rvol !== null && dayIndicators.rvol !== undefined) {
    indicators.rvol[dayIndex] = parseFloat(dayIndicators.rvol).toFixed(2);
  }
  if (dayIndicators.atr !== null && dayIndicators.atr !== undefined) {
    indicators.atr[dayIndex] = parseFloat(dayIndicators.atr).toFixed(4);
  }
  // No % sign for priceVsSMA20 and priceVsVWAP (as per requirements)
  if (dayIndicators.priceVsSMA20 !== null && dayIndicators.priceVsSMA20 !== undefined) {
    indicators.priceVsSMA20[dayIndex] = parseFloat(dayIndicators.priceVsSMA20).toFixed(2);
  }
  if (dayIndicators.priceVsVWAP !== null && dayIndicators.priceVsVWAP !== undefined) {
    indicators.priceVsVWAP[dayIndex] = parseFloat(dayIndicators.priceVsVWAP).toFixed(2);
  }
  
  return indicators;
}

/**
 * Calculate max favorable for a specific day
 * @param {string} strategy - Strategy name
 * @param {number} strike - Strike price
 * @param {number} dayHigh - Day's high price
 * @param {number} dayLow - Day's low price
 * @returns {number|null} Max favorable percentage or null
 */
function EW_calculateMaxFavorableForDay(strategy, strike, dayHigh, dayLow) {
  if (!strike || !dayHigh) return null;
  
  const strategyUpper = strategy.toUpperCase();
  
  if (strategyUpper.includes('LONG CALL') || strategyUpper.includes('BULL')) {
    // Favorable is when price goes up - use day high
    return ((dayHigh - strike) / strike * 100).toFixed(2);
  }
  
  if (strategyUpper.includes('LONG PUT') || strategyUpper.includes('BEAR')) {
    // Favorable is when price goes down - use day low
    return dayLow ? ((strike - dayLow) / strike * 100).toFixed(2) : null;
  }
  
  return null;
}

/**
 * Calculate min unfavorable for a specific day
 * @param {string} strategy - Strategy name
 * @param {number} strike - Strike price
 * @param {number} dayHigh - Day's high price
 * @param {number} dayLow - Day's low price
 * @returns {number|null} Min unfavorable percentage or null
 */
function EW_calculateMinUnfavorableForDay(strategy, strike, dayHigh, dayLow) {
  if (!strike || !dayLow) return null;
  
  const strategyUpper = strategy.toUpperCase();
  
  if (strategyUpper.includes('LONG CALL') || strategyUpper.includes('BULL')) {
    // Unfavorable is when price goes down - use day low
    return ((strike - dayLow) / strike * 100).toFixed(2);
  }
  
  if (strategyUpper.includes('LONG PUT') || strategyUpper.includes('BEAR')) {
    // Unfavorable is when price goes up - use day high
    return dayHigh ? ((dayHigh - strike) / strike * 100).toFixed(2) : null;
  }
  
  return null;
}

/**
 * Update Historical High/Low tracking
 * @param {Object} current - Current historical values {high, low}
 * @param {number} dayHigh - Day's high price
 * @param {number} dayLow - Day's low price
 * @returns {Object} Updated historical values {high, low}
 */
function EW_updateHistoricalHighLow(current = {}, dayHigh, dayLow) {
  const result = {
    high: current.high || 0,
    low: current.low || Infinity
  };
  
  if (dayHigh && dayHigh > result.high) {
    result.high = dayHigh;
  }
  
  if (dayLow && dayLow < result.low) {
    result.low = dayLow;
  }
  
  return result;
}

/**
 * Parse existing array from cell value
 * @param {string|Array} cellValue - Cell value that may be JSON string or array
 * @returns {Array} Parsed array
 */
function EW_parseArrayFromCell(cellValue) {
  if (!cellValue) return [];
  
  // If already an array, return it
  if (Array.isArray(cellValue)) return cellValue;
  
  // If JSON string, parse it
  if (typeof cellValue === 'string' && cellValue.startsWith('[')) {
    try {
      return JSON.parse(cellValue);
    } catch (e) {
      console.log('Failed to parse array from cell:', e);
      return [];
    }
  }
  
  // Handle comma-separated format
  if (typeof cellValue === 'string' && cellValue.includes(',')) {
    return cellValue.split(',').map(v => v.trim());
  }
  
  // Single value - return as array
  return [cellValue];
}

/**
 * Merge two arrays, preserving existing data and adding new data
 * This is the standard behavior for all array updates (backfill and active)
 * @param {Array|string} existingArray - Existing array (may be JSON string)
 * @param {Array} newArray - New array with updates
 * @returns {Array} Merged array
 */
function EW_mergeArrays(existingArray, newArray) {
  if (!existingArray || (typeof existingArray === 'string' && existingArray === '')) return newArray || [];
  if (!newArray || newArray.length === 0) return EW_parseArrayFromCell(existingArray);
  
  // Parse existing array
  const existing = EW_parseArrayFromCell(existingArray);
  
  // Create merged array, using new values where available
  const merged = [...existing];
  for (let i = 0; i < newArray.length; i++) {
    if (newArray[i] !== null && newArray[i] !== undefined) {
      merged[i] = newArray[i];
    }
  }
  
  return merged;
}

/**
 * Convert array to JSON string for storage
 * @param {Array} array - Array to convert
 * @returns {string} JSON string
 */
function EW_arrayToJson(array) {
  return JSON.stringify(array);
}

/**
 * Calculate Risk/Reward ratio from favorable and unfavorable arrays
 * @param {Array} maxFavorableArray - Array of max favorable values
 * @param {Array} minUnfavorableArray - Array of min unfavorable values
 * @returns {string|null} Risk/Reward ratio or null
 */
function EW_calculateRiskRewardFromArrays(maxFavorableArray, minUnfavorableArray) {
  if (!maxFavorableArray || !minUnfavorableArray || 
      maxFavorableArray.length === 0 || minUnfavorableArray.length === 0) {
    return null;
  }
  
  // Find the maximum values from each array
  const maxFav = Math.max(...maxFavorableArray.filter(v => v !== null).map(v => parseFloat(v)));
  const maxUnfav = Math.max(...minUnfavorableArray.filter(v => v !== null).map(v => parseFloat(v)));
  
  if (maxUnfav > 0) {
    return (maxFav / maxUnfav).toFixed(2);
  }
  
  return null;
}

/**
 * Determine if position was profitable based on strike hit array
 * Note: Exp_Result stores the closing price, this function determines WIN/LOSS
 * @param {Array} strikeHitArray - Array of strike hit values
 * @param {boolean} isExpired - Whether position has expired
 * @returns {string|null} WIN/LOSS or null if not expired
 */
function EW_determineWinLoss(strikeHitArray, isExpired) {
  if (!isExpired || !strikeHitArray || strikeHitArray.length === 0) {
    return null;
  }
  
  // Check if any day had a hit (not "NO")
  const hasHit = strikeHitArray.some(value => value && value !== "NO" && value !== null);
  
  return hasHit ? "WIN" : "LOSS";
}

/**
 * Convert indicator arrays from old format (used in backfill) to JSON strings
 * This maintains compatibility with existing backfill functions
 * @param {Object} dailyIndicators - Object with arrays of daily indicator values
 * @returns {Object} Object with JSON strings for each indicator array
 */
function EW_formatIndicatorArraysForStorage(dailyIndicators) {
  const arrays = {};
  
  // Process each indicator type
  const indicatorTypes = ['rsi', 'sma20', 'sma50', 'ema9', 'ema21', 'vwap', 'rvol', 'atr', 'priceVsSMA20', 'priceVsVWAP'];
  
  for (const type of indicatorTypes) {
    if (dailyIndicators[type]) {
      // Format values appropriately
      const formattedArray = dailyIndicators[type].map(val => {
        if (val === null || val === undefined) return null;
        if (type === 'atr') return val.toFixed(4);
        // Keep priceVsSMA20 and priceVsVWAP as decimals without % sign
        if (type === 'priceVsSMA20' || type === 'priceVsVWAP') return val.toFixed(2);
        return val.toFixed(2);
      });
      arrays[type] = JSON.stringify(formattedArray);
    }
  }
  
  return arrays;
}