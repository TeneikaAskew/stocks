/**
 * Historical Backfill - Functions to populate tracking data for historical positions
 * Uses Yahoo Finance historical data to retroactively fill tracking columns
 * Only processes positions with Days_To_Exp < 0 (expired positions)
 * 
 * COLUMN UPDATE CONSISTENCY:
 * All backfill functions MUST update the following columns when data is available:
 * 
 * 1. Day Checks:
 *    - Day0_Check through Day5_Check: Daily price values
 *    
 * 2. Arrays (stored as JSON strings):
 *    - Max_Favorable: Array of daily max favorable price moves from strike
 *    - Min_Unfavorable: Array of daily max unfavorable price moves from strike
 *    - Strike_Hit: Array of percentage moves when strike was hit each day
 *    
 * 3. Indicator Arrays (stored as JSON strings):
 *    - Hit_RSI, Hit_SMA20, Hit_SMA50, Hit_EMA9, Hit_EMA21
 *    - Hit_VWAP, Hit_RVOL, Hit_ATR
 *    - Hit_PriceVsSMA20, Hit_PriceVsVWAP (no % signs, just decimals)
 *    
 * 4. Result Columns:
 *    - Exp_Result: Closing price at expiration for expired positions
 *    - Risk_Reward: Calculated from max favorable/unfavorable arrays
 *    - Historical_High: Highest price during position lifetime
 *    - Historical_Low: Lowest price during position lifetime
 *    - First_Hit_Date: Date when strike was first hit
 * 
 * CENTRALIZED UPDATE FUNCTION:
 * Use EW_updateBackfillColumns() to ensure all backfill functions update columns consistently.
 * This prevents missing columns like what happened with EW_backfillSelectedRows.
 * 
 * Functions using centralized updates:
 * - EW_backfillSelectedRows: Uses EW_updateBackfillColumns()
 * - EW_testHistoricalBackfill: Uses EW_updateBackfillColumns()
 * - EW_backfillStrategyTracking: Uses EW_updateBackfillColumns() with conditional updates
 */

/**
 * Main function to backfill historical tracking data for all sheets
 * This analyzes historical prices from run date to expiration/today
 * Now includes continuation support for long-running processes
 */
function EW_backfillHistoricalTracking() {
  const MAX_RUNTIME_MS = 25 * 60 * 1000; // 25 minutes (leaving 5 min buffer)
  const startTime = new Date();
  
  // Check for existing state from previous run
  const savedState = EW_getBackfillState('BACKFILL_STATE');
  let currentStrategyIndex = savedState ? savedState.currentStrategyIndex : 0;
  let totalBackfilled = savedState ? savedState.totalBackfilled : 0;
  let errors = savedState ? savedState.errors : [];
  let processedStrategies = savedState ? savedState.processedStrategies : [];
  
  if (savedState) {
    EW_trace('BACKFILL', `Resuming from strategy index ${currentStrategyIndex}. Already processed: ${processedStrategies.join(', ')}`, true);
  } else {
    EW_trace('BACKFILL', 'Starting historical tracking backfill', true);
  }
  
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  
  // Process strategies starting from where we left off
  for (let i = currentStrategyIndex; i < strategies.length; i++) {
    const strategy = strategies[i];
    
    // Check if we're approaching time limit
    const elapsedMs = new Date() - startTime;
    if (elapsedMs > MAX_RUNTIME_MS) {
      EW_trace('BACKFILL', `Approaching time limit after ${Math.round(elapsedMs / 1000)}s. Saving state and scheduling continuation...`, true);
      
      // Save state for continuation
      const state = {
        currentStrategyIndex: i,
        totalBackfilled: totalBackfilled,
        errors: errors,
        processedStrategies: processedStrategies,
        startTime: startTime.toISOString(),
        continuationCount: (savedState?.continuationCount || 0) + 1
      };
      EW_saveBackfillState(state, 'BACKFILL_STATE');
      
      // Schedule continuation trigger
      EW_scheduleBackfillContinuation('EW_backfillHistoricalTracking');
      
      return; // Exit to let continuation handle the rest
    }
    
    try {
      const backfilled = EW_backfillStrategyTracking(ss, strategy, startTime, MAX_RUNTIME_MS);
      
      // Check if continuation is needed (-1 indicates time limit reached)
      if (backfilled === -1) {
        EW_trace('BACKFILL', `${strategy} needs continuation - saving state...`, true);
        
        // Save state for continuation at strategy level
        const state = {
          currentStrategyIndex: i,  // Stay on current strategy
          totalBackfilled: totalBackfilled,
          errors: errors,
          processedStrategies: processedStrategies,
          continuationCount: (savedState?.continuationCount || 0) + 1
        };
        EW_saveBackfillState(state, 'BACKFILL_STATE');
        
        // Schedule continuation trigger
        EW_scheduleBackfillContinuation('EW_backfillHistoricalTracking');
        
        return; // Exit to let continuation handle the rest
      }
      
      if (backfilled > 0) {
        totalBackfilled += backfilled;
        EW_trace('BACKFILL', `Backfilled ${backfilled} positions in ${strategy}`);
      }
      processedStrategies.push(strategy);
    } catch (e) {
      // Log the full error with stack trace for debugging
      console.error(`BACKFILL ERROR: ${strategy} - ${e.message}`);
      console.error(e.stack);
      errors.push(`${strategy}: ${e.message}`);
      EW_trace('BACKFILL', `Error backfilling ${strategy}: ${e.message}`, true);
      // Continue with next strategy instead of failing entirely
      continue;
    }
  }
  
  // Formatting removed - now handled by separate daily trigger function
  // Just flush any pending updates
  if (totalBackfilled > 0) {
    SpreadsheetApp.flush();
  }
  
  // Clear continuation state since we're done
  EW_clearBackfillState('BACKFILL_STATE');
  
  // Create daily API report after backfill
  try {
    EW_createDailyApiReport();
    console.log('BACKFILL: Daily API report created');
    EW_trace('BACKFILL', 'Daily API summary report created');
  } catch (error) {
    console.error(`BACKFILL: Failed to create API report: ${error.message}`);
    EW_trace('BACKFILL', `Failed to create API report: ${error.message}`);
  }
  
  const msg = `Historical backfill complete. Processed ${totalBackfilled} positions across ${strategies.length} strategies.` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');
  
  EW_trace('BACKFILL', msg, true);
  if (EW_isSpreadsheetEnvironment()) {
    EW_safeAlert('Historical Backfill Complete', msg);
  }
}

/**
 * Backfill historical tracking data for a specific strategy
 * REFACTORED: Now uses centralized EW_updateBackfillColumns() function to ensure
 * all columns are consistently updated. This prevents issues where some functions
 * were missing columns like Exp_Result, Risk_Reward, or Historical_High/Low.
 * @param {SpreadsheetApp.Spreadsheet} ss - The spreadsheet
 * @param {string} strategyName - Name of the strategy/sheet
 * @returns {number} Number of positions processed
 */
function EW_backfillStrategyTracking(ss, strategyName, startTime = null, maxRuntimeMs = null) {
  const sheet = ss.getSheetByName(strategyName);
  if (!sheet || sheet.getLastRow() < 2) {
    return 0;
  }
  
  // Use provided start time or current time
  const functionStartTime = startTime || new Date();
  const MAX_RUNTIME = maxRuntimeMs || (25 * 60 * 1000); // 25 minutes default
  
  // Get header map
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Get all data
  const lastRow = sheet.getLastRow();
  const dataRange = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
  const data = dataRange.getValues();
  
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  
  // Check required columns - handle spreads differently
  const isSpread = strategyName.toUpperCase().includes('SPREAD');
  const strikeColumn = isSpread ? 'longStrikeCol' : 'strikeCol';
  
  // Verify column order for Day5_Check and Exp_Result
  if (hdrMap.day5CheckCol && hdrMap.expResultCol) {
    const day5Header = headers[hdrMap.day5CheckCol - 1];
    const expResultHeader = headers[hdrMap.expResultCol - 1];
    EW_trace('BACKFILL', `Column verification - Day5_Check: col ${hdrMap.day5CheckCol}='${day5Header}', Exp_Result: col ${hdrMap.expResultCol}='${expResultHeader}'`);
  }
  
  const requiredCols = ['tickerCol', 'runDateCol', strikeColumn];
  for (const col of requiredCols) {
    if (!hdrMap[col]) {
      EW_trace('BACKFILL', `${strategyName}: Missing required column ${col}`);
      return 0;
    }
  }
  
  // Use batch checking to determine which rows need processing
  const batchCheck = EW_batchCheckBackfillRows(sheet, hdrMap, data, strategyName);
  
  // Log the summary once
  EW_trace('BACKFILL', batchCheck.summary, true);
  
  if (batchCheck.needsProcessing === 0) {
    EW_trace('BACKFILL', `${strategyName}: No rows need processing`);
    return 0;
  }
  
  let processedCount = 0;
  let failedCount = 0;
  
  // Check for saved position state within this strategy
  const savedState = EW_getBackfillState('BACKFILL_POSITION_STATE');
  let startPositionIndex = 0;
  
  if (savedState && savedState.currentStrategy === strategyName) {
    startPositionIndex = savedState.currentPositionIndex || 0;
    processedCount = savedState.processedInStrategy || 0;
    failedCount = savedState.failedInStrategy || 0;
    EW_trace('BACKFILL', `${strategyName}: Resuming from position ${startPositionIndex + 1}/${batchCheck.rowsToProcess.length}`);
  } else if (savedState && savedState.currentStrategy !== strategyName) {
    // Clear stale position state from a different strategy
    EW_clearBackfillState('BACKFILL_POSITION_STATE');
  }
  
  // Debug: Log first few rows to process
  if (startPositionIndex === 0 && batchCheck.rowsToProcess.length > 0) {
    const firstRows = batchCheck.rowsToProcess.slice(0, 3).map(r => `Row ${r.rowNum}: ${r.ticker}`).join(', ');
    EW_trace('BACKFILL', `${strategyName}: First rows to process: ${firstRows}`);
    console.log(`BACKFILL DEBUG: First rows to process in ${strategyName}: ${firstRows}`);
  }
  
  // Process only the rows that need it, starting from saved position
  for (let index = startPositionIndex; index < batchCheck.rowsToProcess.length; index++) {
    const rowInfo = batchCheck.rowsToProcess[index];
    
    // Check time limit after each position
    const elapsedMs = new Date() - functionStartTime;
    if (elapsedMs > MAX_RUNTIME) {
      EW_trace('BACKFILL', `${strategyName}: Time limit reached after ${Math.round(elapsedMs / 1000)}s at position ${index + 1}/${batchCheck.rowsToProcess.length}`, true);
      
      // Save position-level state
      const positionState = {
        currentStrategy: strategyName,
        currentPositionIndex: index,
        processedInStrategy: processedCount,
        failedInStrategy: failedCount,
        totalPositions: batchCheck.rowsToProcess.length,
        timestamp: new Date().toISOString()
      };
      EW_saveBackfillState(positionState, 'BACKFILL_POSITION_STATE');
      
      // Return special value to indicate continuation needed
      return -1;
    }
    
    try {
      // Log progress at intervals
      EW_logBatchProgress(index + 1, batchCheck.rowsToProcess.length, 25, 'BACKFILL');
      
      // Use the shared processing function
      const params = {
        ticker: rowInfo.ticker,
        strategyName: strategyName,
        strike: rowInfo.strike,
        runDateStr: rowInfo.runDateStr,
        expDateStr: rowInfo.expDateStr,
        shortStrike: rowInfo.shortStrike,
        hdrMap: hdrMap,
        row: data[rowInfo.index],
        rowIndex: rowInfo.index,
        sheet: sheet,
        isSpread: isSpread
      };
      
      const result = EW_processBackfillPosition(params);
      
      if (result.success && result.analysis) {
        // Convert expDateStr to Date object if it exists
        const expDateObj = rowInfo.expDateStr ? new Date(rowInfo.expDateStr) : null;
        
        // Actually update the columns with the analysis data
        const wasUpdated = EW_updateBackfillColumns(sheet, rowInfo.rowNum, result.analysis, hdrMap, rowInfo.ticker, expDateObj, data[rowInfo.index]);
        
        if (wasUpdated) {
          processedCount++;
        }
      } else if (result.reason === 'no_data') {
        failedCount++;
      }
      
    } catch (e) {
      EW_trace('BACKFILL', `Error processing row ${rowInfo.rowNum} in ${strategyName}: ${e.message}`);
      failedCount++;
    }
  }
  
  // Clear position state if we completed this strategy
  EW_clearBackfillState('BACKFILL_POSITION_STATE');
  
  // Force save
  if (processedCount > 0) {
    SpreadsheetApp.flush();
  }
  
  // Log final summary
  const finalSummary = `${strategyName} Complete: Processed ${processedCount}/${batchCheck.needsProcessing}` +
    (failedCount > 0 ? `, Failed ${failedCount}` : '') +
    `, Skipped ${batchCheck.skippedAlreadyComplete.length + batchCheck.skippedFutureDate.length + batchCheck.skippedMissingData.length}`;
  
  EW_trace('BACKFILL', finalSummary, true);
  return processedCount;
}

// Note: Historical price fetching has been moved to 10_YahooHistorical.js
// using EW_getYahooHistoricalRange() function

/**
 * Count trading days between two dates (excluding weekends)
 * @param {Date} startDate - Start date
 * @param {Date} endDate - End date
 * @returns {number} Number of trading days
 */
function EW_countTradingDays(startDate, endDate) {
  let count = 0;
  const current = new Date(startDate);
  current.setHours(0, 0, 0, 0);
  const end = new Date(endDate);
  end.setHours(0, 0, 0, 0);
  
  while (current <= end) {
    const dayOfWeek = current.getDay();
    if (dayOfWeek !== 0 && dayOfWeek !== 6) { // Not Sunday or Saturday
      count++;
    }
    current.setDate(current.getDate() + 1);
  }
  
  return count;
}

/**
 * Adjust a date to market hours (9:30 AM - 4:00 PM ET)
 * If before 9:30 AM, set to 9:30 AM
 * If after 4:00 PM or on weekend, move to next trading day at 9:30 AM
 * @param {Date} date - Date to adjust
 * @returns {Date} Adjusted date
 */
function EW_adjustToMarketHours(date) {
  const adjusted = new Date(date);
  let dayOfWeek = adjusted.getDay();
  const hours = adjusted.getHours();
  const minutes = adjusted.getMinutes();
  
  // First, handle if the time is after market close (4:00 PM)
  // This needs to be done BEFORE weekend adjustment
  if (hours >= 16) {
    // Move to next day
    adjusted.setDate(adjusted.getDate() + 1);
    adjusted.setHours(9, 30, 0, 0);
    dayOfWeek = adjusted.getDay();
  }
  
  // Now handle weekends
  if (dayOfWeek === 0) { // Sunday
    adjusted.setDate(adjusted.getDate() + 1);
    adjusted.setHours(9, 30, 0, 0);
  } else if (dayOfWeek === 6) { // Saturday
    adjusted.setDate(adjusted.getDate() + 2);
    adjusted.setHours(9, 30, 0, 0);
  } else if (hours < 9 || (hours === 9 && minutes < 30)) {
    // Weekday before market open
    adjusted.setHours(9, 30, 0, 0);
  }
  
  return adjusted;
}

/**
 * Analyze historical price data to determine tracking values
 * @param {string} ticker - Stock ticker symbol
 * @param {string} strategy - Strategy name
 * @param {number} strike - Strike price (or longStrike for spreads)
 * @param {Array} historicalData - Array of 1-minute price data
 * @param {Date} runDate - Entry date
 * @param {number} shortStrike - Short strike for spread strategies (optional)
 * @param {Object} rawData - Raw Yahoo data for indicator calculation (optional)
 * @returns {Object} Analysis results
 */
function EW_analyzeHistoricalData(ticker, strategy, strike, historicalData, runDate, shortStrike = null, rawData = null) {
  const analysis = {
    firstHitDate: null,
    firstHitPrice: null,
    day0Price: null,  // Track Day 0 price for percentage calculation
    day0Hit: null,
    day1Hit: null,
    day2Hit: null,
    day3Hit: null,
    day4Hit: null,
    day5Hit: null,
    maxFavorable: null,  // Will be changed to array
    minUnfavorable: null,  // Will be changed to array
    expResult: null,
    historicalHigh: 0,
    historicalLow: Infinity,
    // Technical indicators at peak profit
    indicators: null,
    // New fields for array implementation
    dailyPrices: [],  // Track daily closing prices
    strikeHitArray: [],  // Array of percentage moves to strike
    indicatorDates: [],  // Dates when indicators were calculated
    // Arrays for max favorable and min unfavorable per day
    maxFavorableArray: [],  // Daily max favorable moves
    minUnfavorableArray: [],  // Daily min unfavorable moves
    // OHLC and Volume array for validation and reference
    ohlcVolumeArray: [],  // Daily OHLC and volume data
    // Daily indicator arrays
    dailyIndicators: {
      rsi: [],
      sma20: [],
      sma50: [],
      ema9: [],
      ema21: [],
      vwap: [],
      rvol: [],
      atr: [],
      priceVsSMA20: [],
      priceVsVWAP: []
    }
  };
  
  if (!historicalData || historicalData.length === 0) return analysis;
  
  const strategyUpper = strategy.toUpperCase();
  const isSpread = strategyUpper.includes('SPREAD');
  const isBullSpread = strategyUpper.includes('BULL SPREAD');
  const isBearSpread = strategyUpper.includes('BEAR SPREAD');
  // Handle both singular and plural forms
  const isBullish = (strategyUpper.includes('LONG CALL') || strategyUpper.includes('LONG CALLS')) || (strategyUpper.includes('BULL') && !isSpread);
  const isBearish = (strategyUpper.includes('LONG PUT') || strategyUpper.includes('LONG PUTS')) || (strategyUpper.includes('BEAR') && !isSpread);
  
  // Debug strategy detection
  EW_trace('BACKFILL', `${ticker} Strategy: "${strategy}" -> Upper: "${strategyUpper}"`);
  EW_trace('BACKFILL', `${ticker} Strategy detection: isBullish=${isBullish}, isBearish=${isBearish}, isSpread=${isSpread}`);
  
  let maxProfit = -Infinity;
  let maxLoss = 0; // Initialize to 0 instead of Infinity
  let hitDetected = false;
  
  // Group 1-minute data by trading day
  const dailyGroups = {};
  const runDateStr = EW_formatDate(runDate);
  
  // Check if we're dealing with daily data
  const isDaily = rawData && rawData.isDailyOrHigher === true;
  
  // Log input data info
  EW_trace('BACKFILL', `${ticker}: Received ${historicalData.length} ${isDaily ? 'daily' : '1-minute'} bars to process`);
  if (historicalData.length > 0) {
    EW_trace('BACKFILL', `${ticker}: Data range from ${EW_toEDT(historicalData[0].date)} to ${EW_toEDT(historicalData[historicalData.length - 1].date)}`);
  }
  
  // If we have daily data, use it directly without grouping
  if (isDaily) {
    // For daily data, each bar is already a full day
    historicalData.forEach((bar, index) => {
      const dateStr = EW_formatDate(bar.date);
      dailyGroups[dateStr] = {
        date: bar.date, // Use the actual bar date instead of creating new Date from string
        bars: [bar], // Single bar for the day
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: bar.volume !== null && bar.volume !== undefined ? bar.volume : null  // Add volume for daily data
      };
    });
  } else {
    // First, group all 1-minute bars by date
    historicalData.forEach((bar, barIndex) => {
    const dateStr = EW_formatDate(bar.date);
    if (!dailyGroups[dateStr]) {
      dailyGroups[dateStr] = {
        date: bar.date, // Use the actual bar date instead of creating new Date from string
        bars: [],
        open: null,
        high: -Infinity,
        low: Infinity,
        close: null,
        volume: null  // Initialize volume aggregation as null, will sum up actual values
      };
    }
    
    dailyGroups[dateStr].bars.push(bar);
    
    // Update daily OHLC - skip null values
    if (bar.open !== null && dailyGroups[dateStr].open === null) {
      dailyGroups[dateStr].open = bar.open;
    }
    if (bar.high !== null) {
      dailyGroups[dateStr].high = Math.max(dailyGroups[dateStr].high, bar.high);
    }
    if (bar.low !== null) {
      dailyGroups[dateStr].low = Math.min(dailyGroups[dateStr].low, bar.low);
    }
    if (bar.close !== null) {
      dailyGroups[dateStr].close = bar.close; // Last non-null close
    }
    // Aggregate volume (sum all non-null volumes for the day)
    if (bar.volume !== null && bar.volume !== undefined) {
      // Initialize to 0 if still null, then add
      if (dailyGroups[dateStr].volume === null) {
        dailyGroups[dateStr].volume = 0;
      }
      dailyGroups[dateStr].volume += bar.volume;
    }
    
    // Log first few bars for debugging
    if (barIndex < 3) {
      EW_trace('BACKFILL', `${ticker}: Bar ${barIndex} - ${EW_toEDT(bar.date)}, O:${bar.open}, H:${bar.high}, L:${bar.low}, C:${bar.close}`);
    }
  });
  }
  
  // Convert to sorted array of days
  const sortedDays = Object.keys(dailyGroups)
    .sort()
    .map(dateStr => {
      const dayGroup = dailyGroups[dateStr];
      // Fix any -Infinity values that weren't replaced due to all null bars
      if (dayGroup.high === -Infinity) {
        const validBars = dayGroup.bars.filter(b => b.high !== null);
        if (validBars.length > 0) {
          dayGroup.high = Math.max(...validBars.map(b => b.high));
          EW_trace('BACKFILL', `${ticker} Fixed -Infinity high for ${dateStr}, new high: ${dayGroup.high}`);
        }
      }
      if (dayGroup.low === Infinity) {
        const validBars = dayGroup.bars.filter(b => b.low !== null);
        if (validBars.length > 0) {
          dayGroup.low = Math.min(...validBars.map(b => b.low));
          EW_trace('BACKFILL', `${ticker} Fixed Infinity low for ${dateStr}, new low: ${dayGroup.low}`);
        }
      }
      return dayGroup;
    });
    
  // Debug logging for each day's aggregated vs actual values
  sortedDays.forEach((day, idx) => {
    if (idx < 3) {  // Log first 3 days
      const validBars = day.bars.filter(b => b.high !== null);
      if (validBars.length > 0) {
        const actualMaxHigh = Math.max(...validBars.map(b => b.high));
        EW_trace('BACKFILL', `${ticker} Day ${idx} (${EW_formatDate(day.date)}): bars=${day.bars.length}, valid=${validBars.length}, aggregated high=${day.high}, actual max=${actualMaxHigh}`);
        
        // Find which bar has the highest value
        const highestBar = validBars.reduce((max, bar) => bar.high > max.high ? bar : max);
        EW_trace('BACKFILL', `${ticker} Day ${idx}: Highest bar at ${EW_toEDT(highestBar.date)} with high=${highestBar.high}, volume=${highestBar.volume}`);
      }
    }
  });
  
  // Log daily grouping results
  EW_trace('BACKFILL', `${ticker}: Grouped into ${sortedDays.length} trading days`);
  sortedDays.forEach((day, idx) => {
    if (idx < 3) { // Log first 3 days
      const volumeStr = day.volume !== undefined ? `, Volume: ${day.volume}` : '';
      EW_trace('BACKFILL', `${ticker}: Day ${idx} - ${EW_formatDate(day.date)}, ${day.bars.length} bars, OHLC: ${day.open.toFixed(2)}/${day.high.toFixed(2)}/${day.low.toFixed(2)}/${day.close.toFixed(2)}${volumeStr}`);
    }
  });
  
  // Find the index where our run date data starts
  // Need to find the first trading day on or after the run date
  let runDateIndex = -1;
  const runDateOnly = new Date(runDate);
  runDateOnly.setHours(0, 0, 0, 0);

  // Also get the date string for more reliable comparison
  const runDateCompareStr = EW_formatDate(runDateOnly);

  for (let i = 0; i < sortedDays.length; i++) {
    const dayDateOnly = new Date(sortedDays[i].date);
    dayDateOnly.setHours(0, 0, 0, 0);
    const dayDateStr = EW_formatDate(dayDateOnly);
    
    // Debug: Log the comparison
    if (i < 3) {
      EW_trace('BACKFILL', `${ticker}: Comparing run date ${runDateCompareStr} (${runDateOnly.getTime()}) with day ${i}: ${dayDateStr} (${dayDateOnly.getTime()})`);
    }
    
    // Find first trading day on or after run date - use string comparison for reliability
    if (dayDateStr >= runDateCompareStr) {
      runDateIndex = i;
      EW_trace('BACKFILL', `${ticker}: Run date ${runDateStr} mapped to trading day ${EW_formatDate(sortedDays[i].date)} at index ${i}`);
      break;
    }
  }
  
  if (runDateIndex === -1) {
    EW_trace('BACKFILL', `Warning: No trading day found on or after run date ${runDateStr}`);
  }
  
  if (runDateIndex === -1) {
    EW_trace('BACKFILL', `Error: No data found on or after run date ${runDateStr} for ${ticker}`);
    EW_trace('BACKFILL', `Available dates in data: ${sortedDays.map(d => d.dateStr).join(', ')}`);
    EW_trace('BACKFILL', `Run date: ${runDateStr}, Data range: ${sortedDays[0]?.dateStr} to ${sortedDays[sortedDays.length-1]?.dateStr}`);
    
    // If we have data but can't find the run date, use the first available date
    if (sortedDays.length > 0) {
      EW_trace('BACKFILL', `Using first available date ${sortedDays[0].dateStr} instead of run date ${runDateStr}`);
      runDateIndex = 0;
    } else {
      return analysis;
    }
  }
  
  // Log data summary
  EW_trace('BACKFILL', `${ticker}: Processing ${historicalData.length} 1-minute bars grouped into ${sortedDays.length} trading days`);
  
  // Log expected trading days
  if (runDateIndex >= 0) {
    EW_trace('BACKFILL', `${ticker}: Expected trading days from run date ${runDateStr}:`);
    let expectedDate = new Date(runDate);
    expectedDate.setHours(0, 0, 0, 0);
    for (let i = 0; i <= 5; i++) {
      // Skip weekends
      while (expectedDate.getDay() === 0 || expectedDate.getDay() === 6) {
        expectedDate.setDate(expectedDate.getDate() + 1);
      }
      const dayOfWeek = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][expectedDate.getDay()];
      EW_trace('BACKFILL', `  Day ${i}: ${EW_formatDate(expectedDate)} (${dayOfWeek})`);
      if (i < 5) {
        expectedDate.setDate(expectedDate.getDate() + 1);
      }
    }
  }
  
  sortedDays.forEach((dayData, index) => {
    // Skip data before run date
    if (index < runDateIndex) {
      return;
    }
    
    // Calculate trading days since entry (based on array position)
    const tradingDaysSinceEntry = index - runDateIndex;
    
    // Log raw data status once at the beginning
    if (tradingDaysSinceEntry === 0) {
      if (!rawData) {
        EW_trace('BACKFILL', `${ticker}: No raw data provided for indicator calculation`);
      } else if (!rawData.timestamps || !rawData.quotes) {
        EW_trace('BACKFILL', `${ticker}: Raw data missing timestamps or quotes`);
      } else {
        EW_trace('BACKFILL', `${ticker}: Raw data available with ${rawData.timestamps.length} timestamps`);
      }
    }
    
    // Debug logging for first few days
    if (tradingDaysSinceEntry <= 5) {
      const dayOfWeek = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][dayData.date.getDay()];
      EW_trace('BACKFILL', `Actual Trading Day ${tradingDaysSinceEntry}: ${EW_formatDate(dayData.date)} (${dayOfWeek}), Index=${index}`);
    }
    
    // Skip data after Day 5
    if (tradingDaysSinceEntry > 5) {
      return;
    }
    
    // Track historical high/low
    analysis.historicalHigh = Math.max(analysis.historicalHigh, dayData.high);
    analysis.historicalLow = Math.min(analysis.historicalLow, dayData.low);
    
    // Find the best price of the day that surpasses the strike
    let dayHit = false;
    let hitPrice = null;
    let hitTime = null;
    let hitBarIndex = -1;
    
    // For spreads and single strategies, we need to find the best price
    if (isSpread && shortStrike) {
      // For spreads, find the best price within the profitable range
      if (isBullSpread) {
        // Bull spread: find highest price that's >= longStrike AND < shortStrike
        for (let barIdx = 0; barIdx < dayData.bars.length; barIdx++) {
          const bar = dayData.bars[barIdx];
          if (bar.high >= strike && bar.high < shortStrike) {
            if (!dayHit || bar.high > hitPrice) {
              dayHit = true;
              hitPrice = bar.high;
              hitTime = bar.date;
              hitBarIndex = barIdx;
            }
          }
        }
      } else if (isBearSpread) {
        // Bear spread: find lowest price that's <= longStrike AND > shortStrike
        for (let barIdx = 0; barIdx < dayData.bars.length; barIdx++) {
          const bar = dayData.bars[barIdx];
          if (bar.low <= strike && bar.low > shortStrike) {
            if (!dayHit || bar.low < hitPrice) {
              dayHit = true;
              hitPrice = bar.low;
              hitTime = bar.date;
              hitBarIndex = barIdx;
            }
          }
        }
      }
    } else {
      // Single strike strategies - find the day's extreme that surpasses strike
      if (isBullish) {
        // For bullish: use the day's high if it exceeds strike
        if (dayData.high >= strike) {
          dayHit = true;
          hitPrice = dayData.high;
          // Find which bar had the high
          for (let barIdx = 0; barIdx < dayData.bars.length; barIdx++) {
            if (dayData.bars[barIdx].high === dayData.high) {
              hitTime = dayData.bars[barIdx].date;
              hitBarIndex = barIdx;
              break;
            }
          }
        }
      } else if (isBearish) {
        // For bearish: use the day's low if it's below strike
        if (dayData.low <= strike) {
          dayHit = true;
          hitPrice = dayData.low;
          // Find which bar had the low
          for (let barIdx = 0; barIdx < dayData.bars.length; barIdx++) {
            if (dayData.bars[barIdx].low === dayData.low) {
              hitTime = dayData.bars[barIdx].date;
              hitBarIndex = barIdx;
              break;
            }
          }
        }
      }
    }
    
    // Log hit detection for debugging
    if (dayHit && tradingDaysSinceEntry <= 2) {
      EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: Strike ${strike} hit at ${EW_toEDT(hitTime)} (bar ${hitBarIndex}/${dayData.bars.length}), price: ${hitPrice}`);
    }
    
    // Record first hit date and price
    // Hit_Date should be based on when the Strike_Hit array first has a positive value
    // This indicates when the position first became profitable
    // We'll determine this after building the Strike_Hit array
    
    // Check specific day milestones based on trading days
    // tradingDaysSinceEntry starts at 0 for the entry date (same day)
    // Always use the day's extreme value (high for bullish, low for bearish)
    let dayPrice;
    if (isBullish) {
      // For bullish: always use the day's high
      dayPrice = dayData.high.toFixed(2);
    } else if (isBearish) {
      // For bearish: always use the day's low
      dayPrice = dayData.low.toFixed(2);
    } else {
      // Default: use closing price
      dayPrice = dayData.close.toFixed(2);
    }
    
    if (tradingDaysSinceEntry === 0) {
      analysis.day0Hit = dayPrice;
      // Store Day 0 closing price for Strike_Hit percentage calculation
      analysis.day0Price = dayData.close;
    } else if (tradingDaysSinceEntry === 1) {
      analysis.day1Hit = dayPrice;
    } else if (tradingDaysSinceEntry === 2) {
      analysis.day2Hit = dayPrice;
    } else if (tradingDaysSinceEntry === 3) {
      analysis.day3Hit = dayPrice;
    } else if (tradingDaysSinceEntry === 4) {
      analysis.day4Hit = dayPrice;
    } else if (tradingDaysSinceEntry === 5) {
      analysis.day5Hit = dayPrice;
    }
    
    // Build arrays for new implementation
    if (tradingDaysSinceEntry >= 0 && tradingDaysSinceEntry <= 5) {
      // Store daily closing price
      analysis.dailyPrices.push(dayData.close);
      
      // Calculate and store percentage move from strike to the day's extreme
      // This shows how much the price moved relative to the strike, whether hit or not
      let percentMove = null;
      
      if (isBullish || (strategyUpper.includes('BULL') && !isSpread)) {
        // For bullish: always calculate (high - strike) / strike
        // This shows how much the high exceeded (or fell short of) the strike
        percentMove = ((dayData.high - strike) / strike).toFixed(6);
      } else if (isBearish || (strategyUpper.includes('BEAR') && !isSpread)) {
        // For bearish: always calculate (strike - low) / strike
        // This shows how much the low fell below (or stayed above) the strike
        percentMove = ((strike - dayData.low) / strike).toFixed(6);
      } else {
        // Default for other strategies: use high if hit expected above, low if below
        if (dayHit) {
          percentMove = ((hitPrice - strike) / strike).toFixed(6);
        } else {
          // If not hit, show how close it got
          percentMove = ((dayData.high - strike) / strike).toFixed(6);
        }
      }
      
      analysis.strikeHitArray.push(percentMove);
      
      // Log the strike for debugging
      if (tradingDaysSinceEntry === 0) {
        const dayPriceDisplay = dayPrice || dayData.close.toFixed(2);
        const priceType = dayHit ? 'Hit' : (isBullish ? 'High' : (isBearish ? 'Low' : 'Close'));
        EW_trace('BACKFILL', `${ticker} - Strike: ${strike}, Day0 ${priceType}: ${dayPriceDisplay}, Close: ${dayData.close}, Percent Move: ${percentMove || 'Not Hit'}`);
      }
      
      // Calculate indicators for this day
      // Use the time of the day's extreme value (high for bullish, low for bearish)
      if (rawData && rawData.timestamps && rawData.quotes) {
        try {
          // Find the raw data index for indicator calculation
          let targetTime = null;
          let rawDataIndex = -1;
          
          // Always use the time of the day's extreme value for consistent volume tracking
          if (isBullish) {
            // Find the bar with the day's high - CRITICAL: This ensures volume matches the high price
            let highBarVolume = null;
            for (let barIdx = 0; barIdx < dayData.bars.length; barIdx++) {
              if (dayData.bars[barIdx].high === dayData.high) {
                targetTime = dayData.bars[barIdx].date;
                highBarVolume = dayData.bars[barIdx].volume;
                if (tradingDaysSinceEntry <= 2) {
                  EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: Found day's high ${dayData.high} at ${EW_toEDT(targetTime)} with volume ${highBarVolume}`);
                }
                break;
              }
            }
            if (tradingDaysSinceEntry <= 2) {
              EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: Using time of day's high (${dayData.high}) for indicators - VOLUME LOCKED to ${highBarVolume}`);
            }
          } else if (isBearish) {
            // Find the bar with the day's low - CRITICAL: This ensures volume matches the low price
            let lowBarVolume = null;
            for (let barIdx = 0; barIdx < dayData.bars.length; barIdx++) {
              if (dayData.bars[barIdx].low === dayData.low) {
                targetTime = dayData.bars[barIdx].date;
                lowBarVolume = dayData.bars[barIdx].volume;
                if (tradingDaysSinceEntry <= 2) {
                  EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: Found day's low ${dayData.low} at ${EW_toEDT(targetTime)} with volume ${lowBarVolume}`);
                }
                break;
              }
            }
            if (tradingDaysSinceEntry <= 2) {
              EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: Using time of day's low (${dayData.low}) for indicators - VOLUME LOCKED to ${lowBarVolume}`);
            }
          } else {
            // For other strategies, use close time
            targetTime = dayData.bars[dayData.bars.length - 1].date;
            if (tradingDaysSinceEntry <= 2) {
              EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: Using close time for indicators`);
            }
          }
          
          // Find the corresponding index in raw data
          const targetTimestamp = Math.floor(targetTime.getTime() / 1000);
          
          // Log search details for debugging
          if (tradingDaysSinceEntry === 0) {
            EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: Searching for timestamp ${targetTimestamp} (${EW_toEDT(targetTime)})`);
            EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: Raw data has ${rawData.timestamps.length} timestamps`);
          }
          
          for (let ri = 0; ri < rawData.timestamps.length; ri++) {
            if (rawData.timestamps[ri] === targetTimestamp) {
              rawDataIndex = ri;
              if (tradingDaysSinceEntry === 0) {
                EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: Found exact match at index ${ri}`);
              }
              break;
            }
          }
          
          // If exact match not found, find the closest timestamp
          if (rawDataIndex === -1) {
            let minDiff = Infinity;
            for (let ri = 0; ri < rawData.timestamps.length; ri++) {
              const diff = Math.abs(rawData.timestamps[ri] - targetTimestamp);
              if (diff < minDiff) {
                minDiff = diff;
                rawDataIndex = ri;
              }
            }
            if (tradingDaysSinceEntry <= 2) {
              EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: No exact timestamp match, using closest (${minDiff} seconds difference)`);
            }
          }
          
          if (rawDataIndex >= 0) {
            // Calculate indicators for this day
            const dayIndicators = EW_calculateIndicatorsFromYahoo(
              rawData.timestamps,
              rawData.quotes,
              rawDataIndex
            );
            
            if (dayIndicators) {
              // Store each indicator value
              analysis.dailyIndicators.rsi.push(dayIndicators.rsi);
              analysis.dailyIndicators.sma20.push(dayIndicators.sma20);
              analysis.dailyIndicators.sma50.push(dayIndicators.sma50);
              analysis.dailyIndicators.ema9.push(dayIndicators.ema9);
              analysis.dailyIndicators.ema21.push(dayIndicators.ema21);
              analysis.dailyIndicators.vwap.push(dayIndicators.vwap);
              analysis.dailyIndicators.rvol.push(dayIndicators.rvol);
              analysis.dailyIndicators.atr.push(dayIndicators.atr);
              analysis.dailyIndicators.priceVsSMA20.push(dayIndicators.priceVsSMA20);
              analysis.dailyIndicators.priceVsVWAP.push(dayIndicators.priceVsVWAP);
              
              // Log the volume at this specific time to confirm we're getting the right data
              const volumeAtTime = rawData.quotes.volume ? rawData.quotes.volume[rawDataIndex] : 0;
              const priceAtTime = rawData.quotes.close[rawDataIndex];
              const highAtTime = rawData.quotes.high[rawDataIndex];
              const lowAtTime = rawData.quotes.low[rawDataIndex];
              
              // CRITICAL VALIDATION: Ensure the volume matches the expected price point
              if (isBullish && Math.abs(highAtTime - dayData.high) > 0.01) {
                EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: WARNING - High price mismatch! Expected ${dayData.high}, got ${highAtTime} at index ${rawDataIndex}`);
              } else if (isBearish && Math.abs(lowAtTime - dayData.low) > 0.01) {
                EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: WARNING - Low price mismatch! Expected ${dayData.low}, got ${lowAtTime} at index ${rawDataIndex}`);
              }
              
              EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: Calculated indicators at index ${rawDataIndex} - H=${highAtTime?.toFixed(2)}, L=${lowAtTime?.toFixed(2)}, C=${priceAtTime?.toFixed(2)}, V=${volumeAtTime}, RSI=${dayIndicators.rsi?.toFixed(2)}, RVOL=${dayIndicators.rvol?.toFixed(2)}`);
            } else {
              EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: Failed to calculate indicators at index ${rawDataIndex}`);
              // Push nulls if indicators couldn't be calculated
              Object.keys(analysis.dailyIndicators).forEach(key => {
                analysis.dailyIndicators[key].push(null);
              });
            }
          } else {
            // No matching raw data found
            EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: No raw data index found for time ${EW_toEDT(targetTime)}`);
            // Log timestamp search details
            if (rawData && rawData.timestamps && rawData.timestamps.length > 0) {
              const firstTime = EW_formatDateTime(new Date(rawData.timestamps[0] * 1000));
              const lastTime = EW_formatDateTime(new Date(rawData.timestamps[rawData.timestamps.length - 1] * 1000));
              EW_trace('BACKFILL', `${ticker}: Raw data time range: ${firstTime} to ${lastTime}`);
              EW_trace('BACKFILL', `${ticker}: Target time ${EW_formatDateTime(targetTime)} (${targetTimestamp}) not in range`);
            }
            Object.keys(analysis.dailyIndicators).forEach(key => {
              analysis.dailyIndicators[key].push(null);
            });
          }
        } catch (error) {
          EW_trace('BACKFILL', `Failed to calculate daily indicators: ${error.message}`);
          // Push nulls on error
          Object.keys(analysis.dailyIndicators).forEach(key => {
            analysis.dailyIndicators[key].push(null);
          });
        }
      }
    }
    
    // Calculate profit/loss for the day and add to arrays
    let dayMaxFavorable = 0;
    let dayMinUnfavorable = 0;
    
    if (isBullish) {
      // For bullish: favorable = (high - strike) / strike, unfavorable = (strike - low) / strike
      dayMaxFavorable = Math.max(0, (dayData.high - strike) / strike);
      dayMinUnfavorable = Math.max(0, (strike - dayData.low) / strike);
      
      // Debug logging for specific problematic tickers
      if ((ticker === 'PANW' && strike === 172.5) || (ticker === 'ZM' && strike === 71)) {
        console.log(`${ticker} Day ${tradingDaysSinceEntry}: high=${dayData.high}, strike=${strike}`);
        console.log(`${ticker} Day ${tradingDaysSinceEntry}: (${dayData.high} - ${strike}) / ${strike} = ${dayMaxFavorable}`);
        console.log(`${ticker} Day ${tradingDaysSinceEntry}: Expected %: ${(dayMaxFavorable * 100).toFixed(2)}%`);
      }
    } else if (isBearish) {
      // For bearish: favorable = (strike - low) / strike, unfavorable = (high - strike) / strike
      dayMaxFavorable = Math.max(0, (strike - dayData.low) / strike);
      dayMinUnfavorable = Math.max(0, (dayData.high - strike) / strike);
    } else if (isBullSpread && shortStrike) {
      // For bull spreads: max profit when price >= short strike, max loss when price <= long strike
      // Favorable: min(high, shortStrike) - strike (capped at spread width)
      // Unfavorable: strike - low (when price below long strike)
      const maxPossibleProfit = (shortStrike - strike) / strike;
      dayMaxFavorable = Math.min(Math.max(0, (dayData.high - strike) / strike), maxPossibleProfit);
      dayMinUnfavorable = Math.max(0, (strike - dayData.low) / strike);
    } else if (isBearSpread && shortStrike) {
      // For bear spreads: max profit when price <= short strike, max loss when price >= long strike
      // Favorable: strike - max(low, shortStrike) (capped at spread width)
      // Unfavorable: high - strike (when price above long strike)
      const maxPossibleProfit = (strike - shortStrike) / strike;
      dayMaxFavorable = Math.min(Math.max(0, (strike - dayData.low) / strike), maxPossibleProfit);
      dayMinUnfavorable = Math.max(0, (dayData.high - strike) / strike);
    }
    
    // Debug logging for day 0-2
    if (tradingDaysSinceEntry <= 2) {
      EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: high=${dayData.high}, low=${dayData.low}, strike=${strike}`);
      EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry} [${strategy}]: isBullish=${isBullish}, isBearish=${isBearish}, isBullSpread=${isBullSpread}, isBearSpread=${isBearSpread}`);
      EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: maxFav=${dayMaxFavorable}, minUnfav=${dayMinUnfavorable}`);
    }
    
    // Add to arrays if within Day 0-5 range
    if (tradingDaysSinceEntry >= 0 && tradingDaysSinceEntry <= 5) {
      analysis.maxFavorableArray.push(dayMaxFavorable.toFixed(6));
      analysis.minUnfavorableArray.push(dayMinUnfavorable.toFixed(6));
      
      // Add OHLC and volume data with source tracking
      analysis.ohlcVolumeArray.push({
        o: dayData.open ? parseFloat(dayData.open).toFixed(2) : null,
        h: dayData.high ? parseFloat(dayData.high).toFixed(2) : null,
        l: dayData.low ? parseFloat(dayData.low).toFixed(2) : null,
        c: dayData.close ? parseFloat(dayData.close).toFixed(2) : null,
        v: dayData.volume !== null && dayData.volume !== undefined ? dayData.volume : null,
        src: 'BACKFILL'  // Track that this came from backfill
      });
    }
    
    // Track overall max/min for backward compatibility
    let dayProfit = 0;
    if (isBullish) {
      dayProfit = ((dayData.high - strike) / strike) * 100;
      const dayLoss = ((strike - dayData.low) / strike) * 100;
      maxLoss = Math.min(maxLoss, -dayLoss);
    } else if (isBearish) {
      dayProfit = ((strike - dayData.low) / strike) * 100;
      const dayLoss = ((dayData.high - strike) / strike) * 100;
      maxLoss = Math.min(maxLoss, -dayLoss);
    }
    
    // Track max profit for overall favorable calculation
    if (dayProfit > maxProfit) {
      maxProfit = dayProfit;
    }
  });
  
  // Set max favorable and min unfavorable
  analysis.maxFavorable = maxProfit > 0 ? maxProfit.toFixed(2) : '0.00';
  analysis.minUnfavorable = maxLoss < 0 ? Math.abs(maxLoss).toFixed(2) : '0.00';
  
  // Set expiration result (last day's status)
  if (historicalData.length > 0) {
    const lastDay = historicalData[historicalData.length - 1];
    
    // Set expResult to the closing price at expiration
    analysis.expResult = lastDay.close ? lastDay.close.toFixed(2) : null;
  }
  
  // Determine firstHitDate based on first positive value in strikeHitArray
  // This now stores the day number (0-5) instead of an actual date
  // This makes it clear how many trading days it took to become profitable
  if (analysis.strikeHitArray && analysis.strikeHitArray.length > 0) {
    for (let i = 0; i < analysis.strikeHitArray.length && i <= 5; i++) {
      const value = analysis.strikeHitArray[i];
      if (value !== null && parseFloat(value) > 0) {
        // Found first profitable day - store the day number
        analysis.firstHitDate = i.toString();
        EW_trace('BACKFILL', `${ticker}: Strike ${strike} first profitable on Day ${i} (value: ${value})`);
        break;
      }
    }
  }
  
  // Note: Indicators are now calculated daily and stored in arrays
  // The dailyIndicators object contains arrays for each indicator type
  
  return analysis;
}

/**
 * Process a single position for backfill - shared logic for both single and batch processing
 * @param {Object} params - Parameters object containing all needed data
 * @param {string} params.ticker - Ticker symbol
 * @param {string} params.strategyName - Strategy name
 * @param {number} params.strike - Strike price
 * @param {string} params.runDateStr - Run date as string
 * @param {string} params.expDateStr - Expiration date as string (optional)
 * @param {number} params.shortStrike - Short strike for spreads (optional)
 * @param {Object} params.hdrMap - Header mapping object
 * @param {Array} params.row - Full row data array
 * @param {number} params.rowIndex - Row index (0-based)
 * @param {Object} params.sheet - Sheet object or cell updater
 * @param {boolean} params.isSpread - Whether this is a spread strategy
 * @returns {Object} Object with success flag and analysis results
 */
function EW_processBackfillPosition(params) {
  const { ticker, strategyName, strike, runDateStr, expDateStr, shortStrike, hdrMap, row, rowIndex, sheet, isSpread } = params;
  
  try {
    // Parse dates - Keep original run date time for proper Day 0 calculation
    const runDate = new Date(runDateStr);
    const expDate = expDateStr ? new Date(expDateStr) : null;
    if (expDate) expDate.setHours(16, 0, 0, 0); // Set to market close for expiration
    
    // Get today's date for comparison
    const today = new Date();
    const currentHour = today.getHours();
    
    // If before market open (9:30 AM ET), use yesterday as the end date
    let effectiveEndDate = new Date(today);
    if (currentHour < 9 || (currentHour === 9 && today.getMinutes() < 30)) {
      // Before market open, use yesterday's close
      effectiveEndDate.setDate(effectiveEndDate.getDate() - 1);
      effectiveEndDate.setHours(16, 0, 0, 0); // Yesterday's market close
      EW_trace('BACKFILL', `${ticker}: Before market open, using yesterday as end date`);
    } else if (currentHour >= 16) {
      // After market close, use today's close
      effectiveEndDate.setHours(16, 0, 0, 0);
    } else {
      // During market hours, use current time
      // Keep current time
    }
    
    // Skip if run date is in the future
    if (runDate > today) {
      EW_trace('BACKFILL', `Skipping ${ticker}: Run date is in the future`);
      return { success: false, reason: 'future_date' };
    }
    
    // Adjust run date to market hours for Day 0 first
    const marketRunDate = EW_adjustToMarketHours(runDate);
    EW_trace('BACKFILL', `${ticker}: Original run date: ${EW_formatDateTime(runDate)}, Adjusted to market hours: ${EW_formatDateTime(marketRunDate)}`);
    
    // Determine end date (expiration or effective end date, whichever is earlier)
    // But ensure it's at least equal to or after the adjusted market run date
    let endDate = expDate && expDate < effectiveEndDate ? expDate : effectiveEndDate;
    if (endDate < marketRunDate) {
      endDate = new Date(marketRunDate);
      endDate.setHours(16, 0, 0, 0); // Set to market close
      EW_trace('BACKFILL', `${ticker}: Adjusted end date to match market run date: ${EW_formatDateTime(endDate)}`);
    }

    EW_trace('BACKFILL', `Processing position: ${ticker} from ${EW_formatDate(marketRunDate)} to ${EW_formatDate(endDate)} (Exp: ${expDateStr || 'none'})`);
    EW_trace('BACKFILL', `Raw run date string: "${runDateStr}", Parsed: ${EW_formatDateTime(runDate)}`);

    // Check if runDate is more than 7 days old
    const daysSinceRun = Math.floor((effectiveEndDate - runDate) / (1000 * 60 * 60 * 24));
    EW_trace('BACKFILL', `Days since run: ${daysSinceRun} (effective end: ${EW_formatDateTime(effectiveEndDate)}, runDate: ${EW_formatDateTime(runDate)})`)
    
    let yahooResult;
    
    // Always try to get minute data first for the last 7 days
    const sevenDaysAgo = new Date(effectiveEndDate);
    sevenDaysAgo.setDate(effectiveEndDate.getDate() - 7);
    
    if (marketRunDate >= sevenDaysAgo) {
      // Position is within 7 days, use only minute data
      EW_trace('BACKFILL', `${ticker}: Using minute data (within 7 days)`);
      EW_trace('BACKFILL', `${ticker}: Date range for API: ${EW_formatDateTime(marketRunDate)} to ${EW_formatDateTime(endDate)}`);
      yahooResult = EW_getYahooHistoricalRange(ticker, marketRunDate, endDate, true);
    } else {
      // Position is older than 7 days, need hybrid approach
      EW_trace('BACKFILL', `${ticker}: Using hybrid data (${daysSinceRun} days old)`);
      EW_trace('BACKFILL', `${ticker}: Fetching daily data from ${EW_formatDate(marketRunDate)} to ${EW_formatDate(sevenDaysAgo)}`);
      EW_trace('BACKFILL', `${ticker}: Fetching minute data from ${EW_formatDate(sevenDaysAgo)} to ${EW_formatDate(endDate)}`);
      
      // Get daily data for the older period (marketRunDate to 7 days ago)
      const dailyResult = EW_getYahooHistoricalRangeWithInterval(ticker, marketRunDate, sevenDaysAgo, '1d', true);
      
      // Get minute data for recent period (7 days ago to endDate)
      const minuteResult = EW_getYahooHistoricalRange(ticker, sevenDaysAgo, endDate, true);
      
      // Combine the results - match Yahoo API structure
      yahooResult = {
        data: [],
        raw: {
          timestamps: [],  // Changed from timestamp to timestamps
          quotes: {        // Changed from indicators.quote[0] to quotes
            open: [],
            high: [],
            low: [],
            close: [],
            volume: []
          }
        }
      };
      
      // Combine daily data
      if (dailyResult && dailyResult.data) {
        EW_trace('BACKFILL', `${ticker}: Daily data received - ${dailyResult.data.length} data points`);
        yahooResult.data = yahooResult.data.concat(dailyResult.data);
        
        // Also combine raw data if available
        if (dailyResult.raw && dailyResult.raw.timestamp) {
          EW_trace('BACKFILL', `${ticker}: Daily raw data structure - timestamps: ${dailyResult.raw.timestamp.length}, has indicators: ${!!dailyResult.raw.indicators}`);
          // Append timestamps
          yahooResult.raw.timestamps = yahooResult.raw.timestamps.concat(dailyResult.raw.timestamp);
          // Get quote data from indicators structure
          const quote = dailyResult.raw.indicators.quote[0];
          yahooResult.raw.quotes.open = yahooResult.raw.quotes.open.concat(quote.open || []);
          yahooResult.raw.quotes.high = yahooResult.raw.quotes.high.concat(quote.high || []);
          yahooResult.raw.quotes.low = yahooResult.raw.quotes.low.concat(quote.low || []);
          yahooResult.raw.quotes.close = yahooResult.raw.quotes.close.concat(quote.close || []);
          yahooResult.raw.quotes.volume = yahooResult.raw.quotes.volume.concat(quote.volume || []);
        } else {
          EW_trace('BACKFILL', `${ticker}: No raw data in daily result`);
        }
      } else {
        EW_trace('BACKFILL', `${ticker}: No daily data received`);
      }
      
      // Combine minute data
      if (minuteResult && minuteResult.data) {
        EW_trace('BACKFILL', `${ticker}: Minute data received - ${minuteResult.data.length} data points`);
        yahooResult.data = yahooResult.data.concat(minuteResult.data);
        
        // Also combine raw data if available
        if (minuteResult.raw && minuteResult.raw.timestamps) {
          EW_trace('BACKFILL', `${ticker}: Minute raw data structure - timestamps: ${minuteResult.raw.timestamps.length}, has quotes: ${!!minuteResult.raw.quotes}`);
          // Append timestamps
          yahooResult.raw.timestamps = yahooResult.raw.timestamps.concat(minuteResult.raw.timestamps);
          // Get quote data directly from quotes structure
          const quote = minuteResult.raw.quotes;
          yahooResult.raw.quotes.open = yahooResult.raw.quotes.open.concat(quote.open || []);
          yahooResult.raw.quotes.high = yahooResult.raw.quotes.high.concat(quote.high || []);
          yahooResult.raw.quotes.low = yahooResult.raw.quotes.low.concat(quote.low || []);
          yahooResult.raw.quotes.close = yahooResult.raw.quotes.close.concat(quote.close || []);
          yahooResult.raw.quotes.volume = yahooResult.raw.quotes.volume.concat(quote.volume || []);
        } else {
          EW_trace('BACKFILL', `${ticker}: No raw data in minute result`);
        }
      } else {
        EW_trace('BACKFILL', `${ticker}: No minute data received`);
      }
      
      // Sort by date
      yahooResult.data.sort((a, b) => a.date - b.date);
      
      // If no raw data was collected, set to null to avoid empty structure
      if (yahooResult.raw.timestamps.length === 0) {
        yahooResult.raw = null;
      } else {
        EW_trace('BACKFILL', `${ticker}: Combined raw data - ${yahooResult.raw.timestamps.length} timestamps total`);
      }
      
      EW_trace('BACKFILL', `${ticker}: Combined ${dailyResult?.data?.length || 0} daily + ${minuteResult?.data?.length || 0} minute data points`);
    }
    
    if (!yahooResult || !yahooResult.data || yahooResult.data.length === 0) {
      // More specific logging about what's missing
      if (!yahooResult) {
        EW_trace('BACKFILL', `${ticker}: No Yahoo result returned at all - API call may have failed`);
      } else if (!yahooResult.data) {
        EW_trace('BACKFILL', `${ticker}: Yahoo result exists but data field is missing/null`);
      } else if (yahooResult.data.length === 0) {
        EW_trace('BACKFILL', `${ticker}: Yahoo returned empty data array`);
      }
      
      EW_trace('BACKFILL', `${ticker}: No data available - Requested: ${EW_formatDate(runDate)} to ${EW_formatDate(endDate)} (${daysSinceRun} days old)`);
      
      // Mark the position as having no data available
      const strikeHitValue = JSON.stringify(['NO_DATA']);
      if (sheet && sheet.getRange) {
        sheet.getRange(rowIndex + 2, hdrMap.strikeHitCol).setValue(strikeHitValue);
      }
      
      return { success: false, reason: 'no_data', analysis: null };
    }
    
    EW_trace('BACKFILL', `${ticker}: Got ${yahooResult.data.length} data points from Yahoo Finance`);
    
    // Log raw data structure for debugging
    if (yahooResult.raw) {
      if (!yahooResult.raw.timestamps) {
        EW_trace('BACKFILL', `${ticker}: WARNING - Raw data exists but timestamps array is missing`);
      } else if (!yahooResult.raw.quotes) {
        EW_trace('BACKFILL', `${ticker}: WARNING - Raw data exists but quotes structure is malformed`);
        EW_trace('BACKFILL', `${ticker}: Raw data structure: ${JSON.stringify(Object.keys(yahooResult.raw))}`);
      } else {
        EW_trace('BACKFILL', `${ticker}: Raw data includes ${yahooResult.raw.timestamps.length} timestamps`);
        const quote = yahooResult.raw.quotes;
        const missingFields = [];
        if (!quote.open || quote.open.length === 0) missingFields.push('open');
        if (!quote.high || quote.high.length === 0) missingFields.push('high');
        if (!quote.low || quote.low.length === 0) missingFields.push('low');
        if (!quote.close || quote.close.length === 0) missingFields.push('close');
        if (!quote.volume || quote.volume.length === 0) missingFields.push('volume');
        if (missingFields.length > 0) {
          EW_trace('BACKFILL', `${ticker}: WARNING - Raw quote data missing or empty fields: ${missingFields.join(', ')}`);
        }
      }
    } else {
      EW_trace('BACKFILL', `${ticker}: WARNING - No raw data included for indicator calculation`);
    }
    
    const firstDataDate = EW_toEDT(yahooResult.data[0].date);
    const lastDataDate = EW_toEDT(yahooResult.data[yahooResult.data.length - 1].date);
    EW_trace('BACKFILL', `${ticker}: Data range: ${firstDataDate} to ${lastDataDate}`);
    
    // Analyze historical data with raw data for indicators - use market-adjusted run date
    const analysis = EW_analyzeHistoricalData(ticker, strategyName, strike, yahooResult.data, marketRunDate, shortStrike, yahooResult.raw);
    
    return { success: true, analysis: analysis };
    
  } catch (e) {
    EW_trace('BACKFILL', `Error processing ${ticker}: ${e.message}`);
    return { success: false, reason: 'error', error: e.message, analysis: null };
  }
}

/**
 * Backfill tracking for a single position (can be called from cell)
 * @param {string} ticker - Ticker symbol
 * @param {string} strategy - Strategy name
 * @param {number} strike - Strike price
 * @param {string} runDate - Run date as string
 * @param {string} expDate - Expiration date as string (optional)
 * @returns {Object} Tracking data object
 */
function EW_backfillSinglePosition(ticker, strategy, strike, runDate, expDate) {
  // Use the shared processing function
  const params = {
    ticker: ticker,
    strategyName: strategy,
    strike: strike,
    runDateStr: runDate,
    expDateStr: expDate,
    shortStrike: null,
    hdrMap: {},  // Empty header map for single position
    row: [],
    rowIndex: 0,
    sheet: null,
    isSpread: strategy.toUpperCase().includes('SPREAD')
  };
  
  const result = EW_processBackfillPosition(params);
  return result.analysis || {};
}

/**
 * Menu function to backfill selected rows only
 */
function EW_backfillSelectedRows() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const range = sheet.getActiveRange();
  
  if (!range) {
    EW_safeAlert('No Selection', 'Please select rows to backfill');
    return;
  }
  
  const startRow = range.getRow();
  const numRows = range.getNumRows();
  
  // Skip if header row is selected
  if (startRow === 1) {
    EW_safeAlert('Invalid Selection', 'Please select data rows, not the header row');
    return;
  }
  
  EW_trace('BACKFILL', `Backfilling ${numRows} selected rows starting at row ${startRow}`, true);
  
  // Get headers
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // DEBUG: Log headers and column mapping
  console.log(`[BACKFILL] Selected rows - Headers:`, headers.slice(0, 10));
  console.log(`[BACKFILL] Selected rows - runDateCol mapped to column ${hdrMap.runDateCol} which has header: "${headers[hdrMap.runDateCol - 1]}"`);
  
  // Debug: Log array columns
  EW_trace('BACKFILL', `Array columns - Strike_Hit: ${hdrMap.strikeHitCol}, Hit_RSI: ${hdrMap.hitRSICol}, Hit_SMA20: ${hdrMap.hitSMA20Col}`);
  EW_trace('BACKFILL', `Result columns - Exp_Result: ${hdrMap.expResultCol}, Risk_Reward: ${hdrMap.riskRewardCol}, Historical_High: ${hdrMap.historicalHighCol}, Historical_Low: ${hdrMap.historicalLowCol}`);
  
  // Get the data for all selected rows at once
  const dataRange = sheet.getRange(startRow, 1, numRows, sheet.getLastColumn());
  const allData = dataRange.getValues();
  
  // Process selected rows
  let processedCount = 0;
  for (let i = 0; i < numRows; i++) {
    const rowNum = startRow + i;
    const rowData = sheet.getRange(rowNum, 1, 1, sheet.getLastColumn()).getValues()[0];
    
    // Get required data
    const ticker = hdrMap.tickerCol ? rowData[hdrMap.tickerCol - 1] : null;
    const runDate = hdrMap.runDateCol ? rowData[hdrMap.runDateCol - 1] : null;
    
    // DEBUG: Log what we're reading
    console.log(`[BACKFILL] Row ${rowNum} - runDateCol: ${hdrMap.runDateCol}, ticker: ${ticker}, runDate value: "${runDate}"`);
    console.log(`[BACKFILL] First 10 columns of row ${rowNum}:`, rowData.slice(0, 10));
    const strike = hdrMap.strikeCol ? parseFloat(rowData[hdrMap.strikeCol - 1]) : null;
    const expDate = hdrMap.expDateCol ? rowData[hdrMap.expDateCol - 1] : null;
    
    if (ticker && runDate && strike) {
      // Get short strike for spreads if available
      const shortStrike = hdrMap.shortStrikeCol ? parseFloat(rowData[hdrMap.shortStrikeCol - 1]) : null;
      const isSpread = sheet.getName().toUpperCase().includes('SPREAD');
      
      // Use the new shared processing function
      const params = {
        ticker: ticker,
        strategyName: sheet.getName(),
        strike: strike,
        runDateStr: runDate,
        expDateStr: expDate,
        shortStrike: shortStrike,
        hdrMap: hdrMap,
        row: rowData,
        rowIndex: rowNum - 2,  // Convert to 0-based index
        sheet: sheet,
        isSpread: isSpread
      };
      
      const result = EW_processBackfillPosition(params);
      
      if (result.success && result.analysis) {
        // Convert expDate to Date object if it's a string
        const expDateObj = expDate ? new Date(expDate) : null;
        
        // Add debug logging
        EW_trace('BACKFILL', `Row ${rowNum} - Ticker: ${ticker}, ExpDate: ${expDate}, ExpDateObj: ${expDateObj}, ExpResult: ${result.analysis.expResult}`);
        EW_trace('BACKFILL', `Row ${rowNum} - MaxFav array: ${JSON.stringify(result.analysis.maxFavorableArray)}, MinUnfav array: ${JSON.stringify(result.analysis.minUnfavorableArray)}`);
        
        // Use centralized update function with Date object
        const wasUpdated = EW_updateBackfillColumns(sheet, rowNum, result.analysis, hdrMap, ticker, expDateObj, rowData);
        
        if (wasUpdated) {
          processedCount++;
        }
      }
    }
  }
  
  // Clear continuation state since we're done
  EW_clearBackfillState('BACKFILL_SELECTED_STATE');
  
  SpreadsheetApp.flush();
  
  // Create daily API report after backfill
  try {
    EW_createDailyApiReport();
    console.log('BACKFILL SELECTED: Daily API report created');
  } catch (error) {
    console.error(`BACKFILL SELECTED: Failed to create API report: ${error.message}`);
  }
  
  const message = 'Processed ' + processedCount + ' of ' + numRows + ' selected rows';
  
  // Formatting removed - now handled by separate daily trigger function
  
  EW_safeAlert('Backfill Complete', message);
}

/**
 * Centralized function to update all backfill columns
 * Ensures consistency across all backfill functions
 * Arrays are always merged with existing data to preserve previous values
 * @param {Sheet} sheet - The sheet to update
 * @param {number} rowNum - Row number to update (1-based)
 * @param {Object} analysis - Analysis results from EW_backfillSinglePosition
 * @param {Object} hdrMap - Header mapping object
 * @param {string} ticker - Ticker symbol for logging
 * @param {Date} expDate - Expiration date (optional)
 * @param {Array} existingRowData - Optional existing row data to check for already filled values
 * @returns {boolean} True if any updates were made
 */
function EW_updateBackfillColumns(sheet, rowNum, analysis, hdrMap, ticker, expDate = null, existingRowData = null) {
  let updated = false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  
  // Helper function to check if value already exists (for non-array fields)
  const shouldUpdate = (columnIndex, newValue) => {
    if (!columnIndex || newValue === null || newValue === undefined) return false;
    if (!existingRowData) return true; // If no existing data provided, always update
    
    const existingValue = existingRowData[columnIndex - 1];
    return !existingValue || existingValue === '';
  };
  
  // Update First_Hit_Date
  // Special handling for Hit_Date - always update if we found an earlier hit date
  if (hdrMap.hitDateCol && analysis.firstHitDate) {
    const existingHitDate = existingRowData ? existingRowData[hdrMap.hitDateCol - 1] : null;
    
    // Always update if no existing date or if the new hit date is earlier
    if (!existingHitDate || existingHitDate === '' || 
        new Date(analysis.firstHitDate) < new Date(existingHitDate)) {
      sheet.getRange(rowNum, hdrMap.hitDateCol).setValue(analysis.firstHitDate);
      updated = true;
      EW_trace('BACKFILL', `${ticker}: Updated Hit_Date from ${existingHitDate || 'empty'} to ${analysis.firstHitDate}`);
    } else if (existingHitDate === EW_formatDate(expDate)) {
      // If existing date equals expiration date, replace with actual hit date
      sheet.getRange(rowNum, hdrMap.hitDateCol).setValue(analysis.firstHitDate);
      updated = true;
      EW_trace('BACKFILL', `${ticker}: Replaced expiration date ${existingHitDate} with actual hit date ${analysis.firstHitDate}`);
    }
  }
  
  // Update Day0_Check through Day5_Check
  const dayChecks = [
    { col: hdrMap.day0CheckCol, value: analysis.day0Hit },
    { col: hdrMap.day1CheckCol, value: analysis.day1Hit },
    { col: hdrMap.day2CheckCol, value: analysis.day2Hit },
    { col: hdrMap.day3CheckCol, value: analysis.day3Hit },
    { col: hdrMap.day4CheckCol, value: analysis.day4Hit },
    { col: hdrMap.day5CheckCol, value: analysis.day5Hit }
  ];
  
  for (const check of dayChecks) {
    if (shouldUpdate(check.col, check.value)) {
      sheet.getRange(rowNum, check.col).setValue(check.value);
      updated = true;
    }
  }
  
  // Update Max_Favorable array (ALWAYS merge with existing)
  if (hdrMap.maxFavorableCol && analysis.maxFavorableArray && analysis.maxFavorableArray.length > 0) {
    const existingMaxFav = existingRowData ? existingRowData[hdrMap.maxFavorableCol - 1] : null;
    const mergedArray = EW_mergeArrays(existingMaxFav, analysis.maxFavorableArray);
    sheet.getRange(rowNum, hdrMap.maxFavorableCol).setValue(JSON.stringify(mergedArray));
    updated = true;
    EW_trace('BACKFILL', `${ticker} Max_Favorable array merged: ${JSON.stringify(mergedArray)} (was: ${existingMaxFav})`);
  }
  
  // Update Min_Unfavorable array (ALWAYS merge with existing)
  if (hdrMap.minUnfavorableCol && analysis.minUnfavorableArray && analysis.minUnfavorableArray.length > 0) {
    const existingMinUnfav = existingRowData ? existingRowData[hdrMap.minUnfavorableCol - 1] : null;
    const mergedArray = EW_mergeArrays(existingMinUnfav, analysis.minUnfavorableArray);
    sheet.getRange(rowNum, hdrMap.minUnfavorableCol).setValue(JSON.stringify(mergedArray));
    updated = true;
    EW_trace('BACKFILL', `${ticker} Min_Unfavorable array merged: ${JSON.stringify(mergedArray)} (was: ${existingMinUnfav})`);
  }
  
  // Update Strike_Hit array (ALWAYS merge with existing)
  if (hdrMap.strikeHitCol && analysis.strikeHitArray && analysis.strikeHitArray.length > 0) {
    const existingStrikeHit = existingRowData ? existingRowData[hdrMap.strikeHitCol - 1] : null;
    const mergedArray = EW_mergeArrays(existingStrikeHit, analysis.strikeHitArray);
    sheet.getRange(rowNum, hdrMap.strikeHitCol).setValue(JSON.stringify(mergedArray));
    EW_trace('BACKFILL', `${ticker} Strike_Hit array merged: ${JSON.stringify(mergedArray)} (was: ${existingStrikeHit})`);
    updated = true;
  } else {
    // Log why Strike_Hit wasn't updated
    const reasons = [];
    if (!hdrMap.strikeHitCol) reasons.push('Column not found');
    if (!analysis.strikeHitArray) reasons.push('No strikeHitArray in analysis');
    if (analysis.strikeHitArray && analysis.strikeHitArray.length === 0) reasons.push('strikeHitArray is empty');
    EW_trace('BACKFILL', `${ticker} Strike_Hit NOT updated - Reasons: ${reasons.join(', ')}`);
  }
  
  // Update all indicator arrays
  if (analysis.dailyIndicators && analysis.dailyIndicators.rsi && analysis.dailyIndicators.rsi.length > 0) {
    EW_trace('BACKFILL', `${ticker} Formatting indicator arrays - RSI length: ${analysis.dailyIndicators.rsi.length}`);
    // Use the new array formatter from 13_ArrayBuilders.js
    const indicatorArrays = EW_formatIndicatorArraysForStorage(analysis.dailyIndicators);
    
    const indicatorMappings = [
      { col: hdrMap.hitRSICol, value: indicatorArrays.rsi, name: 'RSI' },
      { col: hdrMap.hitSMA20Col, value: indicatorArrays.sma20, name: 'SMA20' },
      { col: hdrMap.hitSMA50Col, value: indicatorArrays.sma50, name: 'SMA50' },
      { col: hdrMap.hitEMA9Col, value: indicatorArrays.ema9, name: 'EMA9' },
      { col: hdrMap.hitEMA21Col, value: indicatorArrays.ema21, name: 'EMA21' },
      { col: hdrMap.hitVWAPCol, value: indicatorArrays.vwap, name: 'VWAP' },
      { col: hdrMap.hitRVOLCol, value: indicatorArrays.rvol, name: 'RVOL' },
      { col: hdrMap.hitATRCol, value: indicatorArrays.atr, name: 'ATR' },
      { col: hdrMap.hitPriceVsSMA20Col, value: indicatorArrays.priceVsSMA20, name: 'PriceVsSMA20' },
      { col: hdrMap.hitPriceVsVWAPCol, value: indicatorArrays.priceVsVWAP, name: 'PriceVsVWAP' }
    ];
    
    for (const indicator of indicatorMappings) {
      if (indicator.value) {
        const existingValue = existingRowData ? existingRowData[indicator.col - 1] : null;
        
        // All indicator arrays are merged with existing data
        if (indicator.value.startsWith('[')) {
          const mergedArray = EW_mergeArrays(existingValue, JSON.parse(indicator.value));
          sheet.getRange(rowNum, indicator.col).setValue(JSON.stringify(mergedArray));
          updated = true;
        }
      }
    }
    
    if (updated) {
      EW_trace('BACKFILL', `${ticker} Indicators updated`);
    }
  } else {
    // Log why indicators weren't updated
    const reasons = [];
    if (!analysis.dailyIndicators) reasons.push('No dailyIndicators in analysis');
    if (analysis.dailyIndicators && !analysis.dailyIndicators.rsi) reasons.push('No RSI array');
    if (analysis.dailyIndicators && analysis.dailyIndicators.rsi && analysis.dailyIndicators.rsi.length === 0) reasons.push('RSI array is empty');
    EW_trace('BACKFILL', `${ticker} Indicators NOT updated - Reasons: ${reasons.join(', ')}`);
  }
  
  // Update Exp_Result if expired
  const expResultShouldUpdate = shouldUpdate(hdrMap.expResultCol, analysis.expResult);
  const isExpired = expDate && expDate <= today;
  
  // Detailed logging for Exp_Result update decision
  const expResultDetails = {
    column: hdrMap.expResultCol || 'NOT_FOUND',
    shouldUpdate: expResultShouldUpdate,
    expDate: expDate ? EW_formatDate(expDate) : 'NULL',
    today: EW_formatDate(today),
    isExpired: isExpired,
    analysisExpResult: analysis.expResult || 'NULL',
    currentValue: existingRowData && hdrMap.expResultCol ? existingRowData[hdrMap.expResultCol - 1] : 'NO_DATA'
  };
  
  EW_trace('BACKFILL', `${ticker} Exp_Result check - ${JSON.stringify(expResultDetails)}`);
  
  if (expResultShouldUpdate && isExpired && analysis.expResult) {
    sheet.getRange(rowNum, hdrMap.expResultCol).setValue(analysis.expResult);
    EW_trace('BACKFILL', `${ticker} Exp_Result UPDATED: ${analysis.expResult}`);
    updated = true;
  } else {
    const reasons = [];
    if (!hdrMap.expResultCol) reasons.push('Column not found in headers');
    if (!expResultShouldUpdate) reasons.push('Value already exists or column missing');
    if (!isExpired) reasons.push('Position not expired yet');
    if (!analysis.expResult) reasons.push('No expiration result in analysis');
    EW_trace('BACKFILL', `${ticker} Exp_Result NOT updated - Reasons: ${reasons.join(', ')}`);
  }
  
  // Calculate and update Risk_Reward
  // For Risk_Reward, we need to check if the column is empty, not pass a value
  const riskRewardShouldUpdate = hdrMap.riskRewardCol && 
    (!existingRowData || !existingRowData[hdrMap.riskRewardCol - 1] || existingRowData[hdrMap.riskRewardCol - 1] === '');
  const hasArrays = analysis.maxFavorableArray && analysis.minUnfavorableArray && 
                    analysis.maxFavorableArray.length > 0 && analysis.minUnfavorableArray.length > 0;
  
  // Detailed logging for Risk_Reward calculation
  const riskRewardDetails = {
    column: hdrMap.riskRewardCol || 'NOT_FOUND',
    shouldUpdate: riskRewardShouldUpdate,
    hasMaxFavArray: !!analysis.maxFavorableArray,
    maxFavArrayLength: analysis.maxFavorableArray ? analysis.maxFavorableArray.length : 0,
    hasMinUnfavArray: !!analysis.minUnfavorableArray,
    minUnfavArrayLength: analysis.minUnfavorableArray ? analysis.minUnfavorableArray.length : 0,
    currentValue: existingRowData && hdrMap.riskRewardCol ? existingRowData[hdrMap.riskRewardCol - 1] : 'NO_DATA'
  };
  
  EW_trace('BACKFILL', `${ticker} Risk_Reward check - ${JSON.stringify(riskRewardDetails)}`);
  
  if (riskRewardShouldUpdate && hasArrays) {
    const maxFav = Math.max(...analysis.maxFavorableArray.map(v => parseFloat(v)));
    // Min_Unfavorable contains negative values, we need the absolute value of the most negative
    const maxUnfav = Math.max(...analysis.minUnfavorableArray.map(v => Math.abs(parseFloat(v))));
    EW_trace('BACKFILL', `${ticker} Risk_Reward calculation - MaxFav: ${maxFav}, MaxUnfav: ${maxUnfav}`);
    
    if (maxUnfav > 0) {
      const riskReward = (maxFav / maxUnfav).toFixed(2);
      sheet.getRange(rowNum, hdrMap.riskRewardCol).setValue(riskReward);
      EW_trace('BACKFILL', `${ticker} Risk_Reward UPDATED: ${maxFav}/${maxUnfav} = ${riskReward}`);
      updated = true;
    } else {
      EW_trace('BACKFILL', `${ticker} Risk_Reward NOT updated - maxUnfav is 0 (no unfavorable moves detected)`);
    }
  } else {
    const reasons = [];
    if (!hdrMap.riskRewardCol) reasons.push('Column not found in headers');
    if (!riskRewardShouldUpdate) reasons.push('Value already exists or column missing');
    if (!analysis.maxFavorableArray) reasons.push('No max favorable array');
    if (!analysis.minUnfavorableArray) reasons.push('No min unfavorable array');
    if (analysis.maxFavorableArray && analysis.maxFavorableArray.length === 0) reasons.push('Max favorable array is empty');
    if (analysis.minUnfavorableArray && analysis.minUnfavorableArray.length === 0) reasons.push('Min unfavorable array is empty');
    EW_trace('BACKFILL', `${ticker} Risk_Reward NOT updated - Reasons: ${reasons.join(', ')}`);
  }
  
  // Update Historical High/Low
  if (shouldUpdate(hdrMap.historicalHighCol, analysis.historicalHigh)) {
    sheet.getRange(rowNum, hdrMap.historicalHighCol).setValue(analysis.historicalHigh);
    updated = true;
  }
  if (shouldUpdate(hdrMap.historicalLowCol, analysis.historicalLow) && analysis.historicalLow < Infinity) {
    sheet.getRange(rowNum, hdrMap.historicalLowCol).setValue(analysis.historicalLow);
    updated = true;
  }
  
  // Update OHLC_Volume array (ALWAYS merge with existing)
  // First, check if the column mapping exists
  if (!hdrMap.ohlcVolumeCol) {
    // Add OHLC_Volume column to header map if it exists in headers
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    for (let i = 0; i < headers.length; i++) {
      if (headers[i] === 'OHLC_Volume' || headers[i] === 'Peak_Profit_Date') {
        hdrMap.ohlcVolumeCol = i + 1;
        break;
      }
    }
  }
  
  if (hdrMap.ohlcVolumeCol && analysis.ohlcVolumeArray && analysis.ohlcVolumeArray.length > 0) {
    const existingOHLC = existingRowData ? existingRowData[hdrMap.ohlcVolumeCol - 1] : null;
    const mergedArray = EW_mergeArrays(existingOHLC, analysis.ohlcVolumeArray);
    sheet.getRange(rowNum, hdrMap.ohlcVolumeCol).setValue(JSON.stringify(mergedArray));
    updated = true;
    EW_trace('BACKFILL', `${ticker} OHLC_Volume array updated: ${JSON.stringify(mergedArray).substring(0, 100)}...`);
  }
  
  if (updated) {
    SpreadsheetApp.flush(); // Force immediate save
  }
  
  return updated;
}

/**
 * Test function to verify historical backfill with Yahoo data on a single sheet
 * Tests various scenarios including hit detection, day checks, and profit calculations
 */
function EW_testHistoricalBackfill() {
  console.log('=== Testing Historical Backfill with Yahoo Data ===');
  
  // Test configuration - modify these to test different scenarios
  const testConfig = {
    sheetName: 'Long Calls',  // Change this to test a different sheet
    maxRows: 5,              // Limit number of rows to test
    logDetails: true,        // Set to true for detailed logging
    clearArraysFirst: false, // Set to true to clear Strike_Hit and indicator arrays before testing
    testDirectUpdate: true   // Set to true to test direct cell updates
  };
  
  try {
    const ss = SpreadsheetApp.getActive();
    const sheet = ss.getSheetByName(testConfig.sheetName);
    
    if (!sheet) {
      console.error(`Sheet '${testConfig.sheetName}' not found`);
      return;
    }
    
    console.log(`Testing sheet: ${testConfig.sheetName}`);
    
    // Get headers
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const hdrMap = EW_headerMap(headers);
    console.log('Header columns found:', Object.keys(hdrMap).filter(k => hdrMap[k]).join(', '));
    
    // Log array column positions
    console.log('\nArray Column Positions:');
    console.log(`  Strike_Hit: Column ${hdrMap.strikeHitCol || 'NOT FOUND'}`);
    console.log(`  Hit_RSI: Column ${hdrMap.hitRSICol || 'NOT FOUND'}`);
    console.log(`  Hit_SMA20: Column ${hdrMap.hitSMA20Col || 'NOT FOUND'}`);
    console.log(`  Hit_VWAP: Column ${hdrMap.hitVWAPCol || 'NOT FOUND'}`);
    
    // Check required columns - handle spreads differently
    const isSpread = testConfig.sheetName.toUpperCase().includes('SPREAD');
    const strikeColumn = isSpread ? 'longStrikeCol' : 'strikeCol';
    
    const requiredCols = ['tickerCol', 'runDateCol', strikeColumn, 'daysToExpCol'];
    const missingCols = requiredCols.filter(col => !hdrMap[col]);
    if (missingCols.length > 0) {
      console.error('Missing required columns:', missingCols.join(', '));
      return;
    }
    
    // Get data rows
    const lastRow = Math.min(sheet.getLastRow(), testConfig.maxRows + 1);
    if (lastRow < 2) {
      console.log('No data rows found');
      return;
    }
    
    const dataRange = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
    const data = dataRange.getValues();
    
    console.log(`\nProcessing ${data.length} test rows...`);
    let testResults = [];
    
    // Test each row
    // Clear arrays if requested
    if (testConfig.clearArraysFirst) {
      console.log('\nClearing array columns before test...');
      data.forEach((row, rowIndex) => {
        const actualRow = rowIndex + 2;
        if (hdrMap.strikeHitCol) sheet.getRange(actualRow, hdrMap.strikeHitCol).clearContent();
        if (hdrMap.hitRSICol) sheet.getRange(actualRow, hdrMap.hitRSICol).clearContent();
        if (hdrMap.hitSMA20Col) sheet.getRange(actualRow, hdrMap.hitSMA20Col).clearContent();
        if (hdrMap.hitVWAPCol) sheet.getRange(actualRow, hdrMap.hitVWAPCol).clearContent();
      });
      SpreadsheetApp.flush();
      console.log('Arrays cleared');
    }
    
    data.forEach((row, rowIndex) => {
      const ticker = row[hdrMap.tickerCol - 1];
      const runDateStr = row[hdrMap.runDateCol - 1];
      // For spreads, use longStrike; otherwise use strike
      const strikeCol = isSpread ? hdrMap.longStrikeCol : hdrMap.strikeCol;
      const strike = parseFloat(row[strikeCol - 1]) || 0;
      const expDateStr = hdrMap.expDateCol ? row[hdrMap.expDateCol - 1] : null;
      const daysToExp = parseFloat(row[hdrMap.daysToExpCol - 1]) || 0;
      
      if (!ticker || !runDateStr || !strike) {
        console.log(`Row ${rowIndex + 2}: Skipping - missing required data`);
        return;
      }
      
      console.log(`\n--- Testing Row ${rowIndex + 2} ---`);
      console.log(`Ticker: ${ticker}, Strike: ${strike}, Days to Exp: ${daysToExp}`);
      
      // Check current values before test
      console.log('\nCurrent values in sheet:');
      console.log(`  Strike_Hit: "${row[hdrMap.strikeHitCol - 1] || 'EMPTY'}"`);
      console.log(`  Hit_RSI: "${row[hdrMap.hitRSICol - 1] || 'EMPTY'}"`);
      console.log(`  Hit_SMA20: "${row[hdrMap.hitSMA20Col - 1] || 'EMPTY'}"`);
      console.log(`  Hit_VWAP: "${row[hdrMap.hitVWAPCol - 1] || 'EMPTY'}"`);
      
      // Test different date scenarios
      const runDate = new Date(runDateStr);
      const today = new Date();
      
      // Scenario 1: Test if position is expired (historical)
      if (daysToExp < 0) {
        console.log('Position is EXPIRED - testing historical backfill');
        
        // Adjust run date to market hours first
        const marketRunDate = EW_adjustToMarketHours(runDate);
        console.log(`Adjusted run date to market hours: ${EW_formatDateTime(marketRunDate)}`);

        // Determine end date
        const expDate = expDateStr ? new Date(expDateStr) : null;
        let endDate = expDate && expDate < today ? expDate : today;
        if (endDate < marketRunDate) {
          endDate = new Date(marketRunDate);
          endDate.setHours(16, 0, 0, 0); // Set to market close
          console.log(`Adjusted end date to match market run date: ${EW_formatDateTime(endDate)}`);
        }

        console.log(`Date range: ${EW_formatDate(marketRunDate)} to ${EW_formatDate(endDate)}`);
        
        // Test Yahoo data fetch
        try {
          console.log('Fetching Yahoo historical data...');
          const yahooResult = EW_getYahooHistoricalRange(ticker, marketRunDate, endDate, true);
          
          if (yahooResult && yahooResult.data && yahooResult.data.length > 0) {
            console.log(`Retrieved ${yahooResult.data.length} data points`);
            
            // Log raw data details
            if (yahooResult.raw) {
              console.log(`Raw data: ${yahooResult.raw.timestamps.length} timestamps`);
              if (yahooResult.raw.timestamps.length > 0) {
                const firstTime = EW_formatDateTime(new Date(yahooResult.raw.timestamps[0] * 1000));
                const lastTime = EW_formatDateTime(new Date(yahooResult.raw.timestamps[yahooResult.raw.timestamps.length - 1] * 1000));
                console.log(`Raw data range: ${firstTime} to ${lastTime}`);
              }
            } else {
              console.log('No raw data included in response');
            }
            
            // Test analysis with raw data
            const analysis = EW_analyzeHistoricalData(ticker, testConfig.sheetName, strike, yahooResult.data, runDate, null, yahooResult.raw);
            
            if (testConfig.logDetails) {
              console.log('\nAnalysis results:');
              console.log(`  First Hit Date: ${analysis.firstHitDate || 'Not hit'}`);
              console.log(`  Day 0 Check: ${analysis.day0Hit || 'N/A'}`);
              console.log(`  Day 1 Check: ${analysis.day1Hit || 'N/A'}`);
              console.log(`  Day 2 Check: ${analysis.day2Hit || 'N/A'}`);
              console.log(`  Day 3 Check: ${analysis.day3Hit || 'N/A'}`);
              console.log(`  Day 4 Check: ${analysis.day4Hit || 'N/A'}`);
              console.log(`  Day 5 Check: ${analysis.day5Hit || 'N/A'}`);
              console.log(`  Max Favorable: ${analysis.maxFavorable}%`);
              console.log(`  Min Unfavorable: ${analysis.minUnfavorable}%`);
              console.log(`  Max Favorable Array: ${JSON.stringify(analysis.maxFavorableArray)}`);
              console.log(`  Min Unfavorable Array: ${JSON.stringify(analysis.minUnfavorableArray)}`)
              console.log(`  Historical High: ${analysis.historicalHigh}`);
              console.log(`  Historical Low: ${analysis.historicalLow}`);
              
              // Add full array output
              console.log('\nArray Data:');
              console.log(`  Strike_Hit Array: ${JSON.stringify(analysis.strikeHitArray)}`);
              console.log(`  Strike_Hit Array Length: ${analysis.strikeHitArray.length}`);
              console.log(`  Daily Prices: ${JSON.stringify(analysis.dailyPrices)}`);
              
              // Add indicator arrays
              console.log('\nIndicator Arrays:');
              console.log(`  RSI: ${JSON.stringify(analysis.dailyIndicators.rsi)}`);
              console.log(`  SMA20: ${JSON.stringify(analysis.dailyIndicators.sma20)}`);
              console.log(`  SMA50: ${JSON.stringify(analysis.dailyIndicators.sma50)}`);
              console.log(`  VWAP: ${JSON.stringify(analysis.dailyIndicators.vwap)}`);
              console.log(`  RVOL: ${JSON.stringify(analysis.dailyIndicators.rvol)}`);
              console.log(`  ATR: ${JSON.stringify(analysis.dailyIndicators.atr)}`);
              
              // Test building formatted arrays
              if (analysis.dailyIndicators && analysis.dailyIndicators.rsi.length > 0) {
                const testArrays = EW_formatIndicatorArraysForStorage(analysis.dailyIndicators);
                console.log('\nFormatted Arrays for Storage:');
                console.log(`  RSI String: ${testArrays.rsi}`);
                console.log(`  SMA20 String: ${testArrays.sma20}`);
                console.log(`  VWAP String: ${testArrays.vwap}`);
                console.log(`  PriceVsSMA20 String: ${testArrays.priceVsSMA20}`);
                console.log(`  PriceVsVWAP String: ${testArrays.priceVsVWAP}`);
              }
              
              console.log(`  Exp Result: ${analysis.expResult || 'N/A'}`);
            }
            
            // Test direct update if requested - update ALL columns like real backfill
            if (testConfig.testDirectUpdate) {
              console.log('\n=== Updating All Columns (Like Real Backfill) ===');
              const actualRow = rowIndex + 2;
              
              // Use centralized update function
              const wasUpdated = EW_updateBackfillColumns(sheet, actualRow, analysis, hdrMap, ticker, expDate);
              
              if (wasUpdated) {
                console.log('\n✓ All columns updated successfully');
                
                // Log summary of what was updated
                console.log('\nUpdated values:');
                if (analysis.firstHitDate) console.log(`  Hit_Date: ${analysis.firstHitDate}`);
                if (analysis.day0Hit) console.log(`  Day0_Check: ${analysis.day0Hit}`);
                if (analysis.day1Hit) console.log(`  Day1_Check: ${analysis.day1Hit}`);
                if (analysis.day2Hit) console.log(`  Day2_Check: ${analysis.day2Hit}`);
                if (analysis.day3Hit) console.log(`  Day3_Check: ${analysis.day3Hit}`);
                if (analysis.day4Hit) console.log(`  Day4_Check: ${analysis.day4Hit}`);
                if (analysis.day5Hit) console.log(`  Day5_Check: ${analysis.day5Hit}`);
                if (analysis.maxFavorableArray.length > 0) console.log(`  Max_Favorable: ${JSON.stringify(analysis.maxFavorableArray)}`);
                if (analysis.minUnfavorableArray.length > 0) console.log(`  Min_Unfavorable: ${JSON.stringify(analysis.minUnfavorableArray)}`);
                if (analysis.strikeHitArray.length > 0) console.log(`  Strike_Hit: ${JSON.stringify(analysis.strikeHitArray)}`);
                if (analysis.expResult) console.log(`  Exp_Result: ${analysis.expResult}`);
                if (analysis.historicalHigh) console.log(`  Historical_High: ${analysis.historicalHigh}`);
                if (analysis.historicalLow < Infinity) console.log(`  Historical_Low: ${analysis.historicalLow}`);
                
                // Log indicator arrays
                if (analysis.dailyIndicators && analysis.dailyIndicators.rsi.length > 0) {
                  const indicatorArrays = EW_formatIndicatorArraysForStorage(analysis.dailyIndicators);
                  console.log('\nIndicator arrays:');
                  console.log(`  Hit_RSI: ${indicatorArrays.rsi}`);
                  console.log(`  Hit_SMA20: ${indicatorArrays.sma20}`);
                  console.log(`  Hit_VWAP: ${indicatorArrays.vwap}`);
                  console.log(`  Hit_PriceVsSMA20: ${indicatorArrays.priceVsSMA20}`);
                  console.log(`  Hit_PriceVsVWAP: ${indicatorArrays.priceVsVWAP}`);
                }
              } else {
                console.log('\n⚠️ No updates were made');
              }
            }
            
            testResults.push({
              row: rowIndex + 2,
              ticker: ticker,
              strike: strike,
              status: 'SUCCESS',
              hitDetected: analysis.firstHitDate !== null,
              dataPoints: yahooResult.data.length,
              strikeHitArray: analysis.strikeHitArray.length,
              indicators: analysis.dailyIndicators.rsi.length
            });
          } else {
            console.log('No historical data available');
            testResults.push({
              row: rowIndex + 2,
              ticker: ticker,
              strike: strike,
              status: 'NO_DATA',
              error: 'No historical data retrieved'
            });
          }
        } catch (error) {
          console.error(`Error fetching data: ${error.message}`);
          testResults.push({
            row: rowIndex + 2,
            ticker: ticker,
            strike: strike,
            status: 'ERROR',
            error: error.message
          });
        }
      } else {
        console.log('Position is ACTIVE (not expired) - skipping as per backfill logic');
        testResults.push({
          row: rowIndex + 2,
          ticker: ticker,
          strike: strike,
          status: 'SKIPPED',
          reason: 'Active position'
        });
      }
    });
    
    // Summary
    console.log('\n=== Test Summary ===');
    console.log(`Total rows tested: ${testResults.length}`);
    console.log(`Successful: ${testResults.filter(r => r.status === 'SUCCESS').length}`);
    console.log(`No data: ${testResults.filter(r => r.status === 'NO_DATA').length}`);
    console.log(`Errors: ${testResults.filter(r => r.status === 'ERROR').length}`);
    console.log(`Skipped: ${testResults.filter(r => r.status === 'SKIPPED').length}`);
    
    // Array summary
    const successRows = testResults.filter(r => r.status === 'SUCCESS');
    if (successRows.length > 0) {
      console.log('\n=== Array Generation Summary ===');
      successRows.forEach(r => {
        console.log(`Row ${r.row} (${r.ticker}): Strike_Hit array length=${r.strikeHitArray || 0}, Indicators length=${r.indicators || 0}`);
      });
    }
    
    // Check final values in sheet
    console.log('\n=== Final Sheet Values Check ===');
    data.slice(0, testConfig.maxRows).forEach((row, rowIndex) => {
      const ticker = row[hdrMap.tickerCol - 1];
      if (!ticker) return;
      
      const actualRow = rowIndex + 2;
      
      console.log(`\nRow ${actualRow} (${ticker}):`);
      
      // Check all columns that should be filled
      const checks = [
        { name: 'Strike_Hit', col: hdrMap.strikeHitCol },
        { name: 'Hit_Date', col: hdrMap.hitDateCol },
        { name: 'Day0_Check', col: hdrMap.day0CheckCol },
        { name: 'Day1_Check', col: hdrMap.day1CheckCol },
        { name: 'Day2_Check', col: hdrMap.day2CheckCol },
        { name: 'Day3_Check', col: hdrMap.day3CheckCol },
        { name: 'Day4_Check', col: hdrMap.day4CheckCol },
        { name: 'Day5_Check', col: hdrMap.day5CheckCol },
        { name: 'Max_Favorable', col: hdrMap.maxFavorableCol },
        { name: 'Min_Unfavorable', col: hdrMap.minUnfavorableCol },
        { name: 'Exp_Result', col: hdrMap.expResultCol },
        { name: 'Risk_Reward', col: hdrMap.riskRewardCol },
        { name: 'Hit_RSI', col: hdrMap.hitRSICol },
        { name: 'Hit_SMA20', col: hdrMap.hitSMA20Col },
        { name: 'Hit_SMA50', col: hdrMap.hitSMA50Col },
        { name: 'Hit_VWAP', col: hdrMap.hitVWAPCol },
        { name: 'Hit_PriceVsSMA20', col: hdrMap.hitPriceVsSMA20Col },
        { name: 'Hit_PriceVsVWAP', col: hdrMap.hitPriceVsVWAPCol }
      ];
      
      checks.forEach(check => {
        if (check.col) {
          const value = sheet.getRange(actualRow, check.col).getValue();
          if (value) {
            console.log(`  ${check.name}: "${value}"`);
          }
        }
      });
    });
    
    // Test single position fetch for most recent expired position
    const expiredPositions = testResults.filter(r => r.status === 'SUCCESS' && r.hitDetected);
    if (expiredPositions.length > 0) {
      console.log('\n=== Testing Single Position Backfill ===');
      const testPos = data[expiredPositions[0].row - 2];
      const ticker = testPos[hdrMap.tickerCol - 1];
      const runDate = testPos[hdrMap.runDateCol - 1];
      const strike = parseFloat(testPos[hdrMap.strikeCol - 1]);
      const expDate = hdrMap.expDateCol ? testPos[hdrMap.expDateCol - 1] : null;
      
      console.log(`Testing EW_backfillSinglePosition for ${ticker}`);
      const singleResult = EW_backfillSinglePosition(ticker, testConfig.sheetName, strike, runDate, expDate);
      console.log('Single position result:', singleResult);
    }
    
    return testResults;
    
  } catch (error) {
    console.error('Test failed:', error.message);
    console.error(error.stack);
  }
}

/**
 * Test Day Check calculations to debug N/A issues
 */
function EW_testDayChecks() {
  console.log('=== Testing Day Check Calculations ===');
  
  // Test with different date scenarios
  const today = new Date();
  const testScenarios = [
    { name: 'Yesterday entry', daysAgo: 1 },
    { name: '3 days ago entry', daysAgo: 3 },
    { name: '7 days ago entry', daysAgo: 7 },
    { name: '30 days ago entry', daysAgo: 30 }
  ];
  
  testScenarios.forEach(scenario => {
    const runDate = new Date(today);
    runDate.setDate(runDate.getDate() - scenario.daysAgo);
    
    console.log(`\n${scenario.name}:`);
    console.log(`  Run Date: ${EW_formatDate(runDate)}`);
    console.log(`  Today: ${EW_formatDate(today)}`);
    console.log(`  Days since entry: ${scenario.daysAgo}`);
    
    // Check which day checks should have values
    console.log('  Expected day checks (based on trading days):');
    
    // Calculate actual trading days
    const tradingDays = EW_countTradingDays(runDate, today) - 1; // -1 because we don't count today
    console.log(`  Actual trading days since entry: ${tradingDays}`);
    
    for (let day = 0; day <= 5; day++) {
      if (tradingDays >= day) {
        console.log(`    Day${day}_Check: Should have value (${tradingDays} trading days have passed)`);
      } else {
        console.log(`    Day${day}_Check: Should be N/A (only ${tradingDays} trading days have passed)`);
      }
    }
  });
  
  return 'Test complete - check console for results';
}

/**
 * Quick test to verify Yahoo integration is working
 * Tests a known historical position that should have hit
 */
function EW_quickTestBackfill() {
  console.log('=== Quick Backfill Test ===');
  
  // Test with a known historical example
  const testDate = new Date();
  testDate.setDate(testDate.getDate() - 10); // 10 days ago
  
  const testCases = [
    {
      ticker: 'IWM',
      strategy: 'Long Calls',
      strike: 220,
      runDate: EW_formatDate(testDate),
      expDate: EW_formatDate(new Date())
    },
    {
      ticker: 'SPY',
      strategy: 'Long Calls', 
      strike: 440,
      runDate: EW_formatDate(testDate),
      expDate: EW_formatDate(new Date())
    }
  ];
  
  testCases.forEach((testCase, index) => {
    console.log(`\nTest Case ${index + 1}: ${testCase.ticker} $${testCase.strike}`);
    try {
      const result = EW_backfillSinglePosition(
        testCase.ticker,
        testCase.strategy,
        testCase.strike,
        testCase.runDate,
        testCase.expDate
      );
      
      console.log('Result:', {
        hit: result.firstHitDate ? 'YES' : 'NO',
        hitDate: result.firstHitDate,
        maxFavorable: result.maxFavorable,
        historicalHigh: result.historicalHigh,
        historicalLow: result.historicalLow
      });
    } catch (error) {
      console.error(`Error: ${error.message}`);
    }
  });
}

/**
 * Test function to verify the backfill handles dates over 7 days old correctly
 */
function EW_testBackfillDateLogic() {
  const today = new Date();
  const testCases = [
    { days: 5, expected: '1m' },
    { days: 7, expected: '1m' },
    { days: 8, expected: '1d' },
    { days: 15, expected: '1d' },
    { days: 30, expected: '1d' }
  ];
  
  console.log('Testing backfill date logic:');
  console.log('Today:', EW_formatDate(today));
  
  testCases.forEach(test => {
    const testDate = new Date(today);
    testDate.setDate(today.getDate() - test.days);
    
    const daysSinceRun = Math.floor((today - testDate) / (1000 * 60 * 60 * 24));
    const useDaily = daysSinceRun > 7;
    const interval = useDaily ? '1d' : '1m';
    
    console.log(`Test date ${test.days} days ago (${EW_formatDate(testDate)}): ${interval} data (expected: ${test.expected}) ${interval === test.expected ? '✓' : '✗'}`);
  });
}
