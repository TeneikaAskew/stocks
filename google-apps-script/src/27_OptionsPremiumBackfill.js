/**
 * Options Premium Historical Backfill
 * Mirrors 09_HistoricalBackfill.js pattern but for OPTIONS premium data
 *
 * Uses ACTUAL Yahoo Finance premium data (NOT intrinsic values)
 * Follows exact same pattern as stock backfill:
 * - Batch processing with continuation support
 * - 25-minute runtime limit
 * - State management via File 14 (ExecutionContinuation.js)
 * - Updates Day0-Day13 columns, arrays, Exp_Result
 */

/**
 * Main function to backfill options premium history for all strategy sheets
 * Mirrors EW_backfillHistoricalTracking() from 09_HistoricalBackfill.js
 */
function EW_backfillOptionsPremiumHistory() {
  const MAX_RUNTIME_MS = 25 * 60 * 1000; // 25 minutes
  const startTime = new Date();

  // Check for existing state from previous run
  const savedState = EW_getBackfillState('OPTIONS_BACKFILL_STATE');
  let currentStrategyIndex = savedState ? savedState.currentStrategyIndex : 0;
  let totalBackfilled = savedState ? savedState.totalBackfilled : 0;
  let errors = savedState ? savedState.errors : [];
  let processedStrategies = savedState ? savedState.processedStrategies : [];

  if (savedState) {
    EW_trace('OPTIONS_BACKFILL', `Resuming from strategy index ${currentStrategyIndex}. Already processed: ${processedStrategies.join(', ')}`, true);
  } else {
    EW_trace('OPTIONS_BACKFILL', 'Starting options premium historical backfill', true);
  }

  const ss = SpreadsheetApp.getActive();

  // Define which strategy sheets to process for options
  const optionStrategies = ['Long Calls', 'Bull Spreads', 'Bear Spreads', 'Strangles', 'Covered Calls'];

  // Process strategies starting from where we left off
  for (let i = currentStrategyIndex; i < optionStrategies.length; i++) {
    const strategyName = optionStrategies[i];

    // Check if we're approaching time limit
    const elapsedMs = new Date() - startTime;
    if (elapsedMs > MAX_RUNTIME_MS) {
      EW_trace('OPTIONS_BACKFILL', `Approaching time limit after ${Math.round(elapsedMs / 1000)}s. Saving state and scheduling continuation...`, true);

      // Save state for continuation
      const state = {
        currentStrategyIndex: i,
        totalBackfilled: totalBackfilled,
        errors: errors,
        processedStrategies: processedStrategies,
        startTime: startTime.toISOString(),
        continuationCount: (savedState?.continuationCount || 0) + 1
      };
      EW_saveBackfillState(state, 'OPTIONS_BACKFILL_STATE');

      // Schedule continuation trigger
      EW_scheduleBackfillContinuation('EW_backfillOptionsPremiumHistory');

      return; // Exit to let continuation handle the rest
    }

    try {
      const backfilled = EW_backfillStrategyOptionsPremium(ss, strategyName, startTime, MAX_RUNTIME_MS);

      // Check if continuation is needed (-1 indicates time limit reached)
      if (backfilled === -1) {
        EW_trace('OPTIONS_BACKFILL', `${strategyName} needs continuation - saving state...`, true);

        // Save state for continuation at strategy level
        const state = {
          currentStrategyIndex: i,  // Stay on current strategy
          totalBackfilled: totalBackfilled,
          errors: errors,
          processedStrategies: processedStrategies,
          continuationCount: (savedState?.continuationCount || 0) + 1
        };
        EW_saveBackfillState(state, 'OPTIONS_BACKFILL_STATE');

        // Schedule continuation trigger
        EW_scheduleBackfillContinuation('EW_backfillOptionsPremiumHistory');

        return; // Exit to let continuation handle the rest
      }

      if (backfilled > 0) {
        totalBackfilled += backfilled;
        EW_trace('OPTIONS_BACKFILL', `Backfilled ${backfilled} positions in ${strategyName}`);
      }
      processedStrategies.push(strategyName);
    } catch (e) {
      console.error(`OPTIONS_BACKFILL ERROR: ${strategyName} - ${e.message}`);
      console.error(e.stack);
      errors.push(`${strategyName}: ${e.message}`);
      EW_trace('OPTIONS_BACKFILL', `Error backfilling ${strategyName}: ${e.message}`, true);
      // Continue with next strategy instead of failing entirely
      continue;
    }
  }

  // Flush any pending updates
  if (totalBackfilled > 0) {
    SpreadsheetApp.flush();
  }

  // Clear continuation state since we're done
  EW_clearBackfillState('OPTIONS_BACKFILL_STATE');

  const msg = `Options premium backfill complete. Processed ${totalBackfilled} positions across ${optionStrategies.length} strategies.` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');

  EW_trace('OPTIONS_BACKFILL', msg, true);
  if (EW_isSpreadsheetEnvironment()) {
    EW_safeAlert('Options Premium Backfill Complete', msg);
  }
}

/**
 * Backfill premium history for a specific strategy
 * Mirrors EW_backfillStrategyTracking() from 09_HistoricalBackfill.js
 *
 * @param {SpreadsheetApp.Spreadsheet} ss - The spreadsheet
 * @param {string} strategyName - Name of the strategy/sheet
 * @param {Date} startTime - Function start time for timeout checking
 * @param {number} maxRuntimeMs - Maximum runtime in milliseconds
 * @returns {number} Number of positions processed, or -1 if continuation needed
 */
function EW_backfillStrategyOptionsPremium(ss, strategyName, startTime = null, maxRuntimeMs = null) {
  const sourceSheet = ss.getSheetByName(strategyName);
  if (!sourceSheet || sourceSheet.getLastRow() < 2) {
    return 0;
  }

  // Use provided start time or current time
  const functionStartTime = startTime || new Date();
  const MAX_RUNTIME = maxRuntimeMs || (25 * 60 * 1000); // 25 minutes default

  // Get or create output sheet
  const outputSheetName = `${strategyName} Options`;
  let outputSheet = ss.getSheetByName(outputSheetName);

  if (!outputSheet) {
    outputSheet = ss.insertSheet(outputSheetName);
    EW_setupOptionsPremiumSheet(outputSheet);
  }

  // Detect strategy type
  const strategyType = EW_detectStrategyType(strategyName);

  // Read positions from source sheet
  const positions = EW_readOptionsPositions(sourceSheet, strategyType);

  if (positions.length === 0) {
    EW_trace('OPTIONS_BACKFILL', `${strategyName}: No positions to process`, false);
    return 0;
  }

  // Get existing positions in output sheet to avoid duplicates
  const existingPositions = EW_getExistingPositions(outputSheet);

  // Filter to positions that need backfilling
  const positionsToBackfill = positions.filter(pos => {
    const key = `${pos.ticker}_${pos.strike}_${Utilities.formatDate(pos.expDate, Session.getScriptTimeZone(), 'yyyy-MM-dd')}`;
    const exists = existingPositions.has(key);

    if (!exists) {
      return true; // New position, needs processing
    }

    // Check if existing position has incomplete data
    const needsBackfill = EW_needsOptionsPremiumBackfill(outputSheet, key, pos);
    return needsBackfill;
  });

  if (positionsToBackfill.length === 0) {
    EW_trace('OPTIONS_BACKFILL', `${strategyName}: All positions already backfilled`, false);
    return 0;
  }

  EW_trace('OPTIONS_BACKFILL', `${strategyName}: Processing ${positionsToBackfill.length} of ${positions.length} positions`, true);

  let processedCount = 0;
  let failedCount = 0;

  // Check for saved position state within this strategy
  const savedState = EW_getBackfillState('OPTIONS_BACKFILL_POSITION_STATE');
  let startPositionIndex = 0;

  if (savedState && savedState.currentStrategy === strategyName) {
    startPositionIndex = savedState.currentPositionIndex || 0;
    processedCount = savedState.processedInStrategy || 0;
    failedCount = savedState.failedInStrategy || 0;
    EW_trace('OPTIONS_BACKFILL', `${strategyName}: Resuming from position ${startPositionIndex + 1}/${positionsToBackfill.length}`, false);
  } else if (savedState && savedState.currentStrategy !== strategyName) {
    // Clear stale position state from a different strategy
    EW_clearBackfillState('OPTIONS_BACKFILL_POSITION_STATE');
  }

  // Process positions starting from saved position
  for (let index = startPositionIndex; index < positionsToBackfill.length; index++) {
    const position = positionsToBackfill[index];

    // Check time limit after each position
    const elapsedMs = new Date() - functionStartTime;
    if (elapsedMs > MAX_RUNTIME) {
      EW_trace('OPTIONS_BACKFILL', `${strategyName}: Time limit reached after ${Math.round(elapsedMs / 1000)}s at position ${index + 1}/${positionsToBackfill.length}`, true);

      // Save position-level state
      const state = {
        currentStrategy: strategyName,
        currentPositionIndex: index,
        processedInStrategy: processedCount,
        failedInStrategy: failedCount,
        continuationCount: (savedState?.continuationCount || 0) + 1
      };
      EW_saveBackfillState(state, 'OPTIONS_BACKFILL_POSITION_STATE');

      return -1; // Signal continuation needed
    }

    try {
      const optionSymbol = EW_buildOptionSymbol(
        position.ticker,
        position.expDate,
        position.optionType,
        position.strike
      );

      // Calculate date range for backfill
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const entryDate = new Date(position.runDate);
      entryDate.setHours(0, 0, 0, 0);

      // Determine end date (earlier of today or expiration)
      let endDate = new Date(today);
      if (position.expDate < today) {
        endDate = new Date(position.expDate);
      }

      // Fetch historical premium data
      const premiumHistory = EW_fetchOptionPremiumHistory(optionSymbol, entryDate, endDate);

      if (premiumHistory && premiumHistory.length > 0) {
        // Update or create tracking row
        EW_updateOptionsPremiumBackfillRow(
          outputSheet,
          position,
          premiumHistory,
          strategyType
        );

        processedCount++;
        EW_trace('OPTIONS_BACKFILL', `  ✓ ${position.ticker} $${position.strike}: ${premiumHistory.length} days backfilled`, false);
      } else {
        EW_trace('OPTIONS_BACKFILL', `  ⚠ ${position.ticker} $${position.strike}: No premium history available`, false);
        failedCount++;
      }

    } catch (error) {
      EW_trace('OPTIONS_BACKFILL', `  ✗ ${position.ticker} $${position.strike}: ${error.message}`, true);
      failedCount++;
    }

    // Small delay to avoid rate limiting
    if (index % 10 === 0 && index > 0) {
      Utilities.sleep(500); // 0.5 second pause every 10 positions
    }
  }

  // Clear position-level state when strategy is complete
  EW_clearBackfillState('OPTIONS_BACKFILL_POSITION_STATE');

  if (processedCount > 0) {
    SpreadsheetApp.flush();
  }

  return processedCount;
}

/**
 * Check if a position needs premium backfill
 * @param {Sheet} outputSheet - Output sheet with tracking data
 * @param {string} positionKey - Position identifier
 * @param {Object} position - Position object
 * @returns {boolean} True if backfill needed
 */
function EW_needsOptionsPremiumBackfill(outputSheet, positionKey, position) {
  // Check if position exists but has empty day columns
  // Returns true if Day0_Check is empty or position not found

  const lastRow = outputSheet.getLastRow();
  if (lastRow < 2) return true;

  try {
    // Get headers and map them dynamically
    const headers = outputSheet.getRange(1, 1, 1, outputSheet.getLastColumn()).getValues()[0];
    const hdrMap = EW_headerMap(headers);

    // Validate required columns exist
    if (!hdrMap.tickerCol || !hdrMap.strikeCol || !hdrMap.expDateCol || !hdrMap.day0CheckCol) {
      EW_trace('OPTIONS_BACKFILL', 'Missing required columns in output sheet', true);
      return true;
    }

    // Get all data
    const data = outputSheet.getRange(2, 1, lastRow - 1, outputSheet.getLastColumn()).getValues();
    const expDateStr = Utilities.formatDate(position.expDate, Session.getScriptTimeZone(), 'yyyy-MM-dd');

    for (const row of data) {
      const ticker = String(row[hdrMap.tickerCol - 1]);
      const strike = parseFloat(row[hdrMap.strikeCol - 1]);
      const rowExpDateStr = row[hdrMap.expDateCol - 1] instanceof Date ?
        Utilities.formatDate(row[hdrMap.expDateCol - 1], Session.getScriptTimeZone(), 'yyyy-MM-dd') :
        String(row[hdrMap.expDateCol - 1]);

      if (ticker === position.ticker &&
          Math.abs(strike - position.strike) < 0.01 &&
          rowExpDateStr === expDateStr) {

        // Position exists - check if it needs updating
        // Always update if not expired yet (to get new daily data)
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        if (position.expDate >= today) {
          return true; // Not expired yet - update with latest data
        }

        // Expired - check if Day0_Check has data
        const day0Value = row[hdrMap.day0CheckCol - 1];
        if (!day0Value || day0Value === '') {
          return true; // Missing data - needs backfill
        }

        return false; // Expired and has data - skip
      }
    }

    return true; // Position not found, needs processing

  } catch (error) {
    EW_trace('OPTIONS_BACKFILL', `Error checking backfill status: ${error.message}`, false);
    return true; // Assume needs backfill on error
  }
}

/**
 * Update or create option premium tracking row with backfilled historical data
 * @param {Sheet} outputSheet - Output sheet
 * @param {Object} position - Position info
 * @param {Array} premiumHistory - Array of historical OHLC premium data
 * @param {string} strategyType - Strategy type
 */
function EW_updateOptionsPremiumBackfillRow(outputSheet, position, premiumHistory, strategyType) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const entryDate = new Date(position.runDate);
  entryDate.setHours(0, 0, 0, 0);

  const expDate = new Date(position.expDate);
  expDate.setHours(0, 0, 0, 0);

  const runDate = new Date(position.runDate);
  runDate.setHours(0, 0, 0, 0);

  const tz = Session.getScriptTimeZone();

  const MAX_TRACKING_DAYS = 14;

  // Prepare arrays
  const strikeHitArray = Array(MAX_TRACKING_DAYS).fill('0.000000');
  const maxFavorableArray = Array(MAX_TRACKING_DAYS).fill('0.000000');
  const minUnfavorableArray = Array(MAX_TRACKING_DAYS).fill('0.000000');
  const ohlcVolumeArray = Array(MAX_TRACKING_DAYS).fill(null);
  const dayCheckValues = Array(MAX_TRACKING_DAYS).fill('');

  // Build map for easy lookup
  const premiumMap = {};

  for (const item of premiumHistory) {
    const key = Utilities.formatDate(new Date(item.date), tz, 'yyyy-MM-dd');
    premiumMap[key] = item;
  }

  // Get entry premium (first day's close)
  const entryKey = Utilities.formatDate(entryDate, tz, 'yyyy-MM-dd');
  const entryPremium = premiumMap[entryKey] ? premiumMap[entryKey].close : position.entryPremium;

  let hitDate = '';

  // Populate arrays for each trading day since entry (skip weekends)
  let tradingDayIndex = 0;
  let calendarDayOffset = 0;

  while (tradingDayIndex < MAX_TRACKING_DAYS) {
    const targetDate = new Date(entryDate);
    targetDate.setDate(entryDate.getDate() + calendarDayOffset);
    targetDate.setHours(0, 0, 0, 0);
    calendarDayOffset++;

    // Stop if we're past today or expiration
    if (targetDate > today || targetDate > position.expDate) {
      break;
    }

    // Skip weekends
    const dayOfWeek = targetDate.getDay();
    if (dayOfWeek === 0 || dayOfWeek === 6) {
      continue;
    }

    const key = Utilities.formatDate(targetDate, tz, 'yyyy-MM-dd');
    const dayData = premiumMap[key];

    if (dayData && dayData.close !== null && dayData.close !== undefined) {
      dayCheckValues[tradingDayIndex] = dayData.close;

      // Build OHLC entry
      ohlcVolumeArray[tradingDayIndex] = {
        o: dayData.open !== null ? parseFloat(dayData.open).toFixed(2) : null,
        h: dayData.high !== null ? parseFloat(dayData.high).toFixed(2) : null,
        l: dayData.low !== null ? parseFloat(dayData.low).toFixed(2) : null,
        c: parseFloat(dayData.close).toFixed(2),
        v: dayData.volume || 0,
        src: 'YAHOO'
      };

      // Calculate P/L arrays if we have entry premium
      if (entryPremium) {
        const entryCost = entryPremium * 100;
        const pnl = (dayData.close - entryPremium) * 100;
        const pnlPct = pnl / entryCost;
        strikeHitArray[tradingDayIndex] = pnlPct.toFixed(6);

        // Check for first profitable day
        if (hitDate === '' && pnlPct > 0) {
          hitDate = tradingDayIndex;
        }

        // Max favorable (highest premium during the day)
        if (dayData.high !== null) {
          const maxPnl = (dayData.high - entryPremium) * 100;
          const maxPct = maxPnl / entryCost;
          maxFavorableArray[tradingDayIndex] = Math.max(maxPct, 0).toFixed(6);
        }

        // Min unfavorable (lowest premium during the day)
        if (dayData.low !== null) {
          const minPnl = (dayData.low - entryPremium) * 100;
          const minPct = minPnl / entryCost;
          minUnfavorableArray[tradingDayIndex] = Math.min(minPct, 0).toFixed(6);
        }
      }
    }

    tradingDayIndex++;
  }

  // Default any uninitialized OHLC entries
  for (let i = 0; i < MAX_TRACKING_DAYS; i++) {
    if (!ohlcVolumeArray[i]) {
      ohlcVolumeArray[i] = { o: null, h: null, l: null, c: null, v: 0, src: 'YAHOO' };
    }
  }

  // Calculate expiration result if position is expired
  let expResult = '';
  let riskReward = '';

  if (position.expDate < today) {
    const expKey = Utilities.formatDate(position.expDate, tz, 'yyyy-MM-dd');
    const expData = premiumMap[expKey];

    if (expData && entryPremium) {
      expResult = expData.close;

      // Calculate risk/reward from arrays
      const maxFav = parseFloat(Math.max(...maxFavorableArray.map(v => parseFloat(v) || 0)));
      const minUnfav = parseFloat(Math.min(...minUnfavorableArray.map(v => parseFloat(v) || 0)));

      if (Math.abs(minUnfav) > 0) {
        riskReward = (maxFav / Math.abs(minUnfav)).toFixed(2);
      }
    }
  }

  // Get latest premium data for current columns
  const latestKey = Utilities.formatDate(today < position.expDate ? today : position.expDate, tz, 'yyyy-MM-dd');
  const latestData = premiumMap[latestKey] || {};

  // Calculate current P/L (high and low)
  let pnlCurrentHigh = '';
  let pnlCurrentHighPct = '';
  let pnlCurrentLow = '';
  let pnlCurrentLowPct = '';

  if (entryPremium && latestData.high && latestData.low) {
    const entryCost = entryPremium * 100;

    // High P/L (best case based on latest day's high)
    pnlCurrentHigh = (latestData.high - entryPremium) * 100;
    pnlCurrentHighPct = Number((pnlCurrentHigh / entryCost).toFixed(6));

    // Low P/L (worst case based on latest day's low)
    pnlCurrentLow = (latestData.low - entryPremium) * 100;
    pnlCurrentLowPct = Number((pnlCurrentLow / entryCost).toFixed(6));
  }

  // Calculate days to expiration
  const daysToExp = Math.ceil((position.expDate - today) / (1000 * 60 * 60 * 24));

  // Build option symbol for API URL
  const optionSymbol = EW_buildOptionSymbol(position.ticker, position.expDate, position.optionType, position.strike);

  // Build Yahoo Finance API URL for historical premium data
  // Use the same date range logic as the actual fetch (runDate to earlier of today/expiration)
  let apiEndDate = new Date(today);
  if (position.expDate < today) {
    apiEndDate = new Date(position.expDate);
  }

  const period1 = Math.floor(entryDate.getTime() / 1000);
  const period2 = Math.floor(apiEndDate.getTime() / 1000);
  const apiUrl = `https://query2.finance.yahoo.com/v8/finance/chart/${optionSymbol}?period1=${period1}&period2=${period2}&interval=1d&events=history`;

  // Build row - use Date objects for date columns so they display correctly
  const row = [
    entryDate,                                // Date (entry date) - Date object
    runDate,                                  // Run_Date (from source sheet) - Date object
    position.ticker,                          // Ticker
    position.strike,                          // Strike
    position.optionType,                      // Type
    expDate,                                  // ExpDate - Date object
    JSON.stringify(strikeHitArray),           // Strike_Hit array
    hitDate,                                   // Hit_Date
    JSON.stringify(maxFavorableArray),        // Max_Favorable array
    JSON.stringify(minUnfavorableArray),      // Min_Unfavorable array
    ...dayCheckValues,                         // Day0-Day13 Check columns
    expResult,                                 // Exp_Result
    riskReward,                                // Risk_Reward
    JSON.stringify(ohlcVolumeArray),          // OHLC_Volume array
    latestData.bid || '',                     // Bid
    latestData.ask || '',                     // Ask
    (latestData.ask && latestData.bid) ? (latestData.ask - latestData.bid) : '', // Spread
    latestData.volume || 0,                   // Volume
    pnlCurrentHigh,                            // PnL_Current_High
    pnlCurrentHighPct,                         // PnL_Current_High_Pct
    pnlCurrentLow,                             // PnL_Current_Low
    pnlCurrentLowPct,                          // PnL_Current_Low_Pct
    daysToExp,                                 // Days_To_Exp
    apiUrl                                     // API_URL
  ];

  // Check if position already exists in output sheet
  const existingRowNum = EW_findOptionsPremiumRow(outputSheet, position);

  if (existingRowNum) {
    // Update existing row - merge arrays with existing data
    const headers = outputSheet.getRange(1, 1, 1, outputSheet.getLastColumn()).getValues()[0];
    const hdrMap = EW_headerMap(headers);
    const existingData = outputSheet.getRange(existingRowNum, 1, 1, outputSheet.getLastColumn()).getValues()[0];

    // Merge arrays (Strike_Hit, Max_Favorable, Min_Unfavorable, OHLC_Volume)
    const existingStrikeHit = existingData[hdrMap.strikeHitCol - 1];
    const existingMaxFav = existingData[hdrMap.maxFavorableCol - 1];
    const existingMinUnfav = existingData[hdrMap.minUnfavorableCol - 1];
    const existingOHLC = existingData[hdrMap.ohlcVolumeCol - 1];

    const mergedStrikeHit = EW_mergeArrays(existingStrikeHit, strikeHitArray);
    const mergedMaxFav = EW_mergeArrays(existingMaxFav, maxFavorableArray);
    const mergedMinUnfav = EW_mergeArrays(existingMinUnfav, minUnfavorableArray);
    const mergedOHLC = EW_mergeArrays(existingOHLC, ohlcVolumeArray);

    // Update Strike_Hit, Max_Favorable, Min_Unfavorable, OHLC_Volume with merged arrays
    outputSheet.getRange(existingRowNum, hdrMap.strikeHitCol).setValue(JSON.stringify(mergedStrikeHit));
    outputSheet.getRange(existingRowNum, hdrMap.maxFavorableCol).setValue(JSON.stringify(mergedMaxFav));
    outputSheet.getRange(existingRowNum, hdrMap.minUnfavorableCol).setValue(JSON.stringify(mergedMinUnfav));
    outputSheet.getRange(existingRowNum, hdrMap.ohlcVolumeCol).setValue(JSON.stringify(mergedOHLC));

    // Update Day0-Day13 Check values (only update if new value exists)
    for (let i = 0; i < dayCheckValues.length; i++) {
      const dayCol = hdrMap[`day${i}CheckCol`];
      if (dayCol && dayCheckValues[i]) {
        outputSheet.getRange(existingRowNum, dayCol).setValue(dayCheckValues[i]);
      }
    }

    // Update current premium data (always overwrite with latest)
    if (hdrMap.daysToExpCol) outputSheet.getRange(existingRowNum, hdrMap.daysToExpCol).setValue(daysToExp);
    if (hdrMap.pnlCurrentHighCol) outputSheet.getRange(existingRowNum, hdrMap.pnlCurrentHighCol).setValue(pnlCurrentHigh);
    if (hdrMap.pnlCurrentHighPctCol) outputSheet.getRange(existingRowNum, hdrMap.pnlCurrentHighPctCol).setValue(pnlCurrentHighPct);
    if (hdrMap.pnlCurrentLowCol) outputSheet.getRange(existingRowNum, hdrMap.pnlCurrentLowCol).setValue(pnlCurrentLow);
    if (hdrMap.pnlCurrentLowPctCol) outputSheet.getRange(existingRowNum, hdrMap.pnlCurrentLowPctCol).setValue(pnlCurrentLowPct);

    // Update Hit_Date if we have one and existing is empty
    if (hitDate && hdrMap.hitDateCol) {
      const existingHitDate = existingData[hdrMap.hitDateCol - 1];
      if (!existingHitDate || existingHitDate === '') {
        outputSheet.getRange(existingRowNum, hdrMap.hitDateCol).setValue(hitDate);
      }
    }

    // Update Risk_Reward
    if (riskReward && hdrMap.riskRewardCol) {
      outputSheet.getRange(existingRowNum, hdrMap.riskRewardCol).setValue(riskReward);
    }

    // Update Exp_Result if expired
    if (expResult && hdrMap.expResultCol) {
      outputSheet.getRange(existingRowNum, hdrMap.expResultCol).setValue(expResult);
    }

    EW_formatOptionsPremiumRow(outputSheet, existingRowNum);
  } else {
    // Append new row
    const lastRow = outputSheet.getLastRow();
    const outputRange = outputSheet.getRange(lastRow + 1, 1, 1, row.length);
    outputRange.setValues([row]);
    EW_formatOptionsPremiumRow(outputSheet, lastRow + 1);
  }
}

/**
 * Find existing row for a position in output sheet
 * @param {Sheet} outputSheet - Output sheet
 * @param {Object} position - Position info
 * @returns {number|null} Row number if found, null otherwise
 */
function EW_findOptionsPremiumRow(outputSheet, position) {
  const lastRow = outputSheet.getLastRow();
  if (lastRow < 2) return null;

  try {
    // Get headers and map them dynamically
    const headers = outputSheet.getRange(1, 1, 1, outputSheet.getLastColumn()).getValues()[0];
    const hdrMap = EW_headerMap(headers);

    // Validate required columns exist
    if (!hdrMap.tickerCol || !hdrMap.strikeCol || !hdrMap.expDateCol) {
      EW_trace('OPTIONS_BACKFILL', 'Missing required columns in output sheet (ticker, strike, expDate)', true);
      return null;
    }

    // Get only the columns we need for matching
    const numCols = Math.max(hdrMap.tickerCol, hdrMap.strikeCol, hdrMap.expDateCol);
    const data = outputSheet.getRange(2, 1, lastRow - 1, numCols).getValues();
    const expDateStr = Utilities.formatDate(position.expDate, Session.getScriptTimeZone(), 'yyyy-MM-dd');

    for (let i = 0; i < data.length; i++) {
      const ticker = String(data[i][hdrMap.tickerCol - 1]);
      const strike = parseFloat(data[i][hdrMap.strikeCol - 1]);
      const rowExpDateStr = data[i][hdrMap.expDateCol - 1] instanceof Date ?
        Utilities.formatDate(data[i][hdrMap.expDateCol - 1], Session.getScriptTimeZone(), 'yyyy-MM-dd') :
        String(data[i][hdrMap.expDateCol - 1]);

      if (ticker === position.ticker &&
          Math.abs(strike - position.strike) < 0.01 &&
          rowExpDateStr === expDateStr) {
        return i + 2; // Row number (data starts at row 2)
      }
    }
  } catch (error) {
    EW_trace('OPTIONS_BACKFILL', `Error finding row: ${error.message}`, false);
  }

  return null;
}

/**
 * Apply formatting to option premium row
 * @param {Sheet} sheet - Output sheet
 * @param {number} rowNum - Row number to format
 */
function EW_formatOptionsPremiumRow(sheet, rowNum) {
  // Format row data to match column types
  // Date columns (Date, Run_Date, ExpDate) - columns 1, 2, 6
  sheet.getRange(rowNum, 1).setNumberFormat('yyyy-mm-dd');
  sheet.getRange(rowNum, 2).setNumberFormat('yyyy-mm-dd');
  sheet.getRange(rowNum, 6).setNumberFormat('yyyy-mm-dd');

  // Text columns (Ticker, Type) - columns 3, 5
  sheet.getRange(rowNum, 3).setNumberFormat('@');
  sheet.getRange(rowNum, 5).setNumberFormat('@');

  // Number (Strike) - column 4
  sheet.getRange(rowNum, 4).setNumberFormat('0.00');

  // JSON arrays (Strike_Hit, Max_Favorable, Min_Unfavorable, OHLC_Volume) - columns 7, 9, 10, 27
  sheet.getRange(rowNum, 7).setNumberFormat('@');
  sheet.getRange(rowNum, 9).setNumberFormat('@');
  sheet.getRange(rowNum, 10).setNumberFormat('@');
  sheet.getRange(rowNum, 27).setNumberFormat('@');

  // Hit_Date - column 8
  sheet.getRange(rowNum, 8).setNumberFormat('0');

  // Day Check columns (Day0-Day13) - columns 11-24
  sheet.getRange(rowNum, 11, 1, 14).setNumberFormat('0.00');

  // Result columns (Exp_Result, Risk_Reward) - columns 25, 26
  sheet.getRange(rowNum, 25).setNumberFormat('@');
  sheet.getRange(rowNum, 26).setNumberFormat('0.00');

  // Premium data (Bid, Ask, Spread) - columns 28, 29, 30
  sheet.getRange(rowNum, 28, 1, 3).setNumberFormat('0.00');

  // Volume - column 31
  sheet.getRange(rowNum, 31).setNumberFormat('0');

  // P/L dollar amounts - columns 32, 34
  sheet.getRange(rowNum, 32).setNumberFormat('0.00');
  sheet.getRange(rowNum, 34).setNumberFormat('0.00');

  // P/L percentages - columns 33, 35
  sheet.getRange(rowNum, 33).setNumberFormat('0.00%');
  sheet.getRange(rowNum, 35).setNumberFormat('0.00%');

  // Days to expiration - column 36
  sheet.getRange(rowNum, 36).setNumberFormat('0');

  // API URL - column 37
  sheet.getRange(rowNum, 37).setNumberFormat('@');
}

/**
 * Fetch stock OHLC data for a date range
 * @param {string} ticker - Stock ticker
 * @param {Date} startDate - Start date
 * @param {Date} endDate - End date
 * @returns {Array} Array of OHLC data
 */
function EW_fetchStockOHLCForDateRange(ticker, startDate, endDate) {
  try {
    // Use existing helper function from 10_YahooHistorical.js if available
    if (typeof EW_fetchHistoricalData === 'function') {
      return EW_fetchHistoricalData(ticker, startDate, endDate);
    }

    // Fallback: simple Yahoo Finance chart API call
    const period1 = Math.floor(startDate.getTime() / 1000);
    const period2 = Math.floor(endDate.getTime() / 1000);
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?period1=${period1}&period2=${period2}&interval=1d`;

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
    const result = data.chart.result[0];
    const timestamps = result.timestamp || [];
    const quote = result.indicators.quote[0];

    const history = [];
    for (let i = 0; i < timestamps.length; i++) {
      history.push({
        date: new Date(timestamps[i] * 1000),
        open: quote.open[i],
        high: quote.high[i],
        low: quote.low[i],
        close: quote.close[i],
        volume: quote.volume[i] || 0
      });
    }

    return history;
  } catch (error) {
    EW_trace('OPTIONS_BACKFILL', `Error fetching stock history for ${ticker}: ${error.message}`, false);
    return [];
  }
}

/**
 * Backfill selected positions only (for manual runs)
 * Mirrors EW_backfillSelectedRows() from 09_HistoricalBackfill.js
 */
function EW_backfillOptionsPremiumsSelected() {
  const ss = SpreadsheetApp.getActive();
  const sourceSheet = ss.getActiveSheet();
  const selection = sourceSheet.getActiveRange();

  // Validate selection
  const strategyName = sourceSheet.getName();
  const optionStrategies = ['Long Calls', 'Bull Spreads', 'Bear Spreads', 'Strangles', 'Covered Calls'];

  if (!optionStrategies.includes(strategyName)) {
    SpreadsheetApp.getUi().alert('Please select rows in an options strategy sheet (Long Calls, Bull Spreads, etc.)');
    return;
  }

  const startRow = selection.getRow();
  const numRows = selection.getNumRows();

  if (startRow === 1) {
    SpreadsheetApp.getUi().alert('Please select data rows (not the header)');
    return;
  }

  // Get output sheet
  const outputSheetName = `${strategyName} Options`;
  let outputSheet = ss.getSheetByName(outputSheetName);

  if (!outputSheet) {
    outputSheet = ss.insertSheet(outputSheetName);
    EW_setupOptionsPremiumSheet(outputSheet);
  }

  // Detect strategy type
  const strategyType = EW_detectStrategyType(strategyName);

  // Read headers
  const headers = sourceSheet.getRange(1, 1, 1, sourceSheet.getLastColumn()).getValues()[0];
  const hdrMap = {};

  for (let i = 0; i < headers.length; i++) {
    const header = String(headers[i]).toLowerCase().trim().replace(/\s+/g, '');
    if (header === 'ticker') hdrMap.ticker = i;
    if (header === 'strike') hdrMap.strike = i;
    if (header === 'expdate' || header === 'expiration') hdrMap.expDate = i;
    if (header === 'rundate' || header === 'entrydate' || header === 'scandate') hdrMap.runDate = i;
    if (header === 'entry_premium' || header === 'entrypremium' || header === 'bid') {
      if (header === 'bid' && hdrMap.entryPremium === undefined) hdrMap.entryPremium = i;
      if (header === 'entry_premium' || header === 'entrypremium') hdrMap.entryPremium = i;
    }
  }

  const data = sourceSheet.getRange(startRow, 1, numRows, sourceSheet.getLastColumn()).getValues();
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  let processed = 0;
  let errors = [];

  for (let i = 0; i < data.length; i++) {
    const row = data[i];

    const ticker = row[hdrMap.ticker];
    const strike = parseFloat(row[hdrMap.strike]);
    const expDate = new Date(row[hdrMap.expDate]);
    const runDate = hdrMap.runDate !== undefined ? new Date(row[hdrMap.runDate]) : today;
    const entryPremium = hdrMap.entryPremium !== undefined ? parseFloat(row[hdrMap.entryPremium]) : null;

    if (!ticker || isNaN(strike) || !expDate) continue;

    // Determine option type
    let optionType = 'C';
    if (strategyType === 'BEARISH') {
      optionType = 'P';
    }

    const position = {
      ticker: ticker,
      strike: strike,
      expDate: expDate,
      runDate: runDate,
      optionType: optionType,
      entryPremium: entryPremium,
      strategyType: strategyType
    };

    try {
      const optionSymbol = EW_buildOptionSymbol(ticker, expDate, optionType, strike);

      // Calculate date range
      const entryDateNorm = new Date(runDate);
      entryDateNorm.setHours(0, 0, 0, 0);

      let endDate = new Date(today);
      if (expDate < today) {
        endDate = new Date(expDate);
      }

      // Fetch premium history
      const premiumHistory = EW_fetchOptionPremiumHistory(optionSymbol, entryDateNorm, endDate);

      if (premiumHistory && premiumHistory.length > 0) {
        // Update row
        EW_updateOptionsPremiumBackfillRow(
          outputSheet,
          position,
          premiumHistory,
          strategyType
        );

        processed++;
        EW_trace('OPTIONS_BACKFILL', `✓ ${ticker} $${strike}: ${premiumHistory.length} days backfilled`, false);
      } else {
        EW_trace('OPTIONS_BACKFILL', `⚠ ${ticker} $${strike}: No premium history`, false);
      }

    } catch (error) {
      const errorMsg = `${ticker}: ${error.message}`;
      errors.push(errorMsg);
      EW_trace('OPTIONS_BACKFILL', `✗ ${ticker}: ${error.message}`, true);
    }
  }

  if (processed > 0) {
    SpreadsheetApp.flush();
  }

  const msg = `Backfilled ${processed} of ${numRows} selected positions.` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.slice(0, 3).join('\n')}` : '');

  SpreadsheetApp.getUi().alert('Backfill Complete', msg, SpreadsheetApp.getUi().ButtonSet.OK);
}

/**
 * Check backfill status (for debugging)
 */
function EW_checkOptionsPremiumBackfillStatus() {
  const savedState = EW_getBackfillState('OPTIONS_BACKFILL_STATE');
  const positionState = EW_getBackfillState('OPTIONS_BACKFILL_POSITION_STATE');

  let msg = 'Options Premium Backfill Status:\n\n';

  if (!savedState) {
    msg += 'No active backfill process.';
  } else {
    msg += `Strategy: ${savedState.processedStrategies?.join(', ') || 'None'}\n`;
    msg += `Total Processed: ${savedState.totalBackfilled || 0}\n`;
    msg += `Continuation Count: ${savedState.continuationCount || 0}\n`;
    msg += `Last Saved: ${savedState.lastSaved || 'N/A'}`;
  }

  if (positionState) {
    msg += `\n\nPosition State:\n`;
    msg += `Current Strategy: ${positionState.currentStrategy || 'N/A'}\n`;
    msg += `Position Index: ${positionState.currentPositionIndex || 0}\n`;
    msg += `Processed: ${positionState.processedInStrategy || 0}`;
  }

  if (EW_isSpreadsheetEnvironment()) {
    SpreadsheetApp.getUi().alert('Backfill Status', msg, SpreadsheetApp.getUi().ButtonSet.OK);
  }

  Logger.log(msg);
  return msg;
}
