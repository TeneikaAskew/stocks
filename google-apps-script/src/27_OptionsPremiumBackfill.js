/**
 * Options Premium Historical Backfill - STANDALONE VERSION
 * Mirrors 09_HistoricalBackfill.js pattern but for OPTIONS premium data
 *
 * This file is SELF-CONTAINED with all necessary dependencies migrated from 27_OptionsPremiumTracking.js
 * to make the backfill script independent and not rely on the premium tracking functions.
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
    // Include runDate in key so each scan date gets its own tracking row
    const runDateStr = Utilities.formatDate(pos.runDate, Session.getScriptTimeZone(), 'yyyy-MM-dd');
    const key = `${pos.ticker}_${pos.strike}_${Utilities.formatDate(pos.expDate, Session.getScriptTimeZone(), 'yyyy-MM-dd')}_${runDateStr}`;
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
      // Weekend adjustment happens inside EW_fetchOptionPremiumHistory
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
    const posRunDateStr = Utilities.formatDate(position.runDate, Session.getScriptTimeZone(), 'yyyy-MM-dd');

    for (const row of data) {
      const ticker = String(row[hdrMap.tickerCol - 1]);
      const strike = parseFloat(row[hdrMap.strikeCol - 1]);
      const rowExpDateStr = row[hdrMap.expDateCol - 1] instanceof Date ?
        Utilities.formatDate(row[hdrMap.expDateCol - 1], Session.getScriptTimeZone(), 'yyyy-MM-dd') :
        String(row[hdrMap.expDateCol - 1]);

      // Also check runDate to match the exact position
      const rowRunDate = hdrMap.runDateCol ? row[hdrMap.runDateCol - 1] : null;
      const rowRunDateStr = rowRunDate instanceof Date ?
        Utilities.formatDate(rowRunDate, Session.getScriptTimeZone(), 'yyyy-MM-dd') :
        (rowRunDate ? String(rowRunDate) : '');

      if (ticker === position.ticker &&
          Math.abs(strike - position.strike) < 0.01 &&
          rowExpDateStr === expDateStr &&
          rowRunDateStr === posRunDateStr) {

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

  EW_trace('OPTIONS_BACKFILL', `Premium history for ${position.ticker}: ${premiumHistory.length} days, keys: ${Object.keys(premiumMap).join(', ')}`, false);

  // Get entry premium (first day's close)
  const entryKey = Utilities.formatDate(entryDate, tz, 'yyyy-MM-dd');
  const entryPremium = premiumMap[entryKey] ? premiumMap[entryKey].close : position.entryPremium;

  EW_trace('OPTIONS_BACKFILL', `Looking for entry key: ${entryKey}, found: ${premiumMap[entryKey] ? 'yes' : 'no'}, entryPremium: ${entryPremium}`, false);

  let hitDate = '';

  // Populate arrays for each trading day since entry (skip weekends)
  let tradingDayIndex = 0;
  let calendarDayOffset = 0;

  // EW_trace('OPTIONS_BACKFILL', `Starting day iteration for ${position.ticker}:`, false);
  // EW_trace('OPTIONS_BACKFILL', `  entryDate: ${Utilities.formatDate(entryDate, tz, 'yyyy-MM-dd')} (${entryDate.getTime()})`, false);
  // EW_trace('OPTIONS_BACKFILL', `  today: ${Utilities.formatDate(today, tz, 'yyyy-MM-dd')} (${today.getTime()})`, false);
  // EW_trace('OPTIONS_BACKFILL', `  expDate: ${Utilities.formatDate(position.expDate, tz, 'yyyy-MM-dd')} (${position.expDate.getTime()})`, false);

  while (tradingDayIndex < MAX_TRACKING_DAYS) {
    const targetDate = new Date(entryDate);
    targetDate.setDate(entryDate.getDate() + calendarDayOffset);
    targetDate.setHours(0, 0, 0, 0);
    calendarDayOffset++;

    // Log first 5 iterations
    // if (calendarDayOffset <= 5) {
    //   EW_trace('OPTIONS_BACKFILL', `  Iteration ${calendarDayOffset}: targetDate=${Utilities.formatDate(targetDate, tz, 'yyyy-MM-dd')}, dow=${targetDate.getDay()}, tradingDay=${tradingDayIndex}`, false);
    // }

    // Stop if we're past today or expiration
    if (targetDate > today || targetDate > position.expDate) {
      // EW_trace('OPTIONS_BACKFILL', `  BREAK: targetDate ${Utilities.formatDate(targetDate, tz, 'yyyy-MM-dd')} > today ${Utilities.formatDate(today, tz, 'yyyy-MM-dd')} OR > expDate ${Utilities.formatDate(position.expDate, tz, 'yyyy-MM-dd')}`, false);
      break;
    }

    // Skip weekends
    const dayOfWeek = targetDate.getDay();
    if (dayOfWeek === 0 || dayOfWeek === 6) {
      // if (calendarDayOffset <= 5) {
      //   EW_trace('OPTIONS_BACKFILL', `  SKIP WEEKEND: ${Utilities.formatDate(targetDate, tz, 'yyyy-MM-dd')}`, false);
      // }
      continue;
    }

    const key = Utilities.formatDate(targetDate, tz, 'yyyy-MM-dd');
    const dayData = premiumMap[key];

    // if (calendarDayOffset <= 5) {
    //   EW_trace('OPTIONS_BACKFILL', `  Looking for key: ${key}, found: ${dayData ? 'YES' : 'NO'}, tradingDayIndex=${tradingDayIndex}`, false);
    // }

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
    today,                                    // Date (today - when script runs) - Date object
    runDate,                                  // Run_Date (entry date from source sheet) - Date object
    position.ticker,                          // Ticker
    position.strike,                          // Strike
    position.optionType,                      // Type
    expDate,                                  // ExpDate - Date object
    JSON.stringify(strikeHitArray),           // Bid_Hit_Pct array
    hitDate,                                   // First_Hit_Date
    '',                                        // Bid_Hit_Days (placeholder)
    '',                                        // Ask_Hit_Days (placeholder)
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
    pnlCurrentHigh,                            // PnL_High
    pnlCurrentHighPct,                         // PnL_High_Pct
    pnlCurrentLow,                             // PnL_Low
    pnlCurrentLowPct,                          // PnL_Low_Pct
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

// ========================================
// MIGRATED DEPENDENCIES FROM 27_OptionsPremiumTracking.js
// These functions are needed by the backfill script to work independently
// ========================================

/**
 * Read positions from source sheet (FOR BACKFILL - includes expired positions)
 * Migrated from 27_OptionsPremiumTracking.js with modification to include expired positions
 * @param {Sheet} sheet - Source sheet
 * @param {string} strategyType - Strategy type (BULLISH, BEARISH, NEUTRAL)
 * @returns {Array} Array of position objects (newest first)
 */
function EW_readOptionsPositions(sheet, strategyType) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];

  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = {};

  // Build header map
  for (let i = 0; i < headers.length; i++) {
    const header = String(headers[i]).toLowerCase().trim().replace(/\s+/g, '');
    if (header === 'ticker') hdrMap.ticker = i;
    if (header === 'strike') hdrMap.strike = i;
    if (header === 'expdate' || header === 'expiration') hdrMap.expDate = i;
    if (header === 'rundate' || header === 'entrydate' || header === 'scandate') hdrMap.runDate = i;
    if (header === 'entry_premium' || header === 'entrypremium' || header === 'bid' || header === 'ask') {
      // Use bid or ask as entry premium if available
      if (header === 'bid' && hdrMap.entryPremium === undefined) hdrMap.entryPremium = i;
      if (header === 'entry_premium' || header === 'entrypremium') hdrMap.entryPremium = i;
    }
  }

  // Validate required columns
  if (hdrMap.ticker === undefined || hdrMap.strike === undefined || hdrMap.expDate === undefined) {
    EW_trace('OPTIONS_BACKFILL', 'Missing required columns (ticker, strike, expDate)', true);
    return [];
  }

  const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  const positions = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // Process rows in REVERSE order (bottom to top = newest first)
  for (let i = data.length - 1; i >= 0; i--) {
    const row = data[i];

    const ticker = row[hdrMap.ticker];
    const strike = parseFloat(row[hdrMap.strike]);
    const expDate = new Date(row[hdrMap.expDate]);
    const runDate = hdrMap.runDate !== undefined ? new Date(row[hdrMap.runDate]) : null;
    const entryPremium = hdrMap.entryPremium !== undefined ? parseFloat(row[hdrMap.entryPremium]) : null;

    // Skip if missing data
    if (!ticker || isNaN(strike) || !expDate) continue;

    // FOR BACKFILL: Include expired positions (unlike the tracking version)
    // if (expDate < today) continue;  // <-- COMMENTED OUT FOR BACKFILL

    // Filter out weekend runDates - skip positions from Saturday/Sunday scans
    if (runDate) {
      runDate.setHours(0, 0, 0, 0);
      const dayOfWeek = runDate.getDay();
      // const runDateStr = Utilities.formatDate(runDate, Session.getScriptTimeZone(), 'yyyy-MM-dd (EEE)');

      if (dayOfWeek === 0 || dayOfWeek === 6) {
        // Skip weekend entries - they cause API errors
        // EW_trace('OPTIONS_BACKFILL', `FILTERED OUT weekend runDate: ${ticker} ${runDateStr}`, false);
        continue;
      }

      // EW_trace('OPTIONS_BACKFILL', `ACCEPTED runDate: ${ticker} ${runDateStr}`, false);

      // Uncomment to only process today's scans:
      // if (runDate.getTime() !== today.getTime()) continue;
    }

    // Determine option type based on strategy
    let optionType = 'C'; // Default to Call
    if (strategyType === 'BEARISH') {
      optionType = 'P'; // Put for bearish strategies
    }

    positions.push({
      ticker: ticker,
      strike: strike,
      expDate: expDate,
      runDate: runDate || today,  // Use runDate from sheet, fallback to today
      optionType: optionType,
      entryPremium: entryPremium,
      rowNum: i + 2,
      strategyType: strategyType
    });
  }

  return positions;
}

/**
 * Get existing positions from output sheet (to avoid duplicates)
 * Migrated from 27_OptionsPremiumTracking.js
 * @param {Sheet} sheet - Output sheet
 * @returns {Set} Set of position keys (ticker_strike_expDate_runDate)
 */
function EW_getExistingPositions(sheet) {
  const existingPositions = new Set();

  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return existingPositions;

  try {
    // Get headers and map them dynamically
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const hdrMap = EW_headerMap(headers);

    // Validate required columns exist
    if (!hdrMap.tickerCol || !hdrMap.strikeCol || !hdrMap.expDateCol) {
      EW_trace('OPTIONS_BACKFILL', 'Missing required columns in sheet (ticker, strike, expDate)', true);
      return existingPositions;
    }

    // Get only the columns we need (including Run_Date)
    const numCols = Math.max(hdrMap.tickerCol, hdrMap.strikeCol, hdrMap.expDateCol, hdrMap.runDateCol || 0);
    const data = sheet.getRange(2, 1, lastRow - 1, numCols).getValues();

    for (const row of data) {
      const ticker = String(row[hdrMap.tickerCol - 1]);
      const strike = parseFloat(row[hdrMap.strikeCol - 1]);
      const expDate = row[hdrMap.expDateCol - 1] instanceof Date ?
        Utilities.formatDate(row[hdrMap.expDateCol - 1], Session.getScriptTimeZone(), 'yyyy-MM-dd') :
        String(row[hdrMap.expDateCol - 1]);

      // Include runDate in key to distinguish positions scanned on different dates
      const runDate = hdrMap.runDateCol ? row[hdrMap.runDateCol - 1] : null;
      const runDateStr = runDate instanceof Date ?
        Utilities.formatDate(runDate, Session.getScriptTimeZone(), 'yyyy-MM-dd') :
        (runDate ? String(runDate) : '');

      if (ticker && !isNaN(strike) && expDate) {
        const key = `${ticker}_${strike}_${expDate}_${runDateStr}`;
        existingPositions.add(key);
      }
    }

    if (existingPositions.size > 0) {
      EW_trace('OPTIONS_BACKFILL', `Found ${existingPositions.size} existing positions in tracking sheet`, false);
    }

  } catch (error) {
    EW_trace('OPTIONS_BACKFILL', `Error reading existing positions: ${error.message}`, false);
  }

  return existingPositions;
}

/**
 * Setup output sheet with premium tracking columns
 * Migrated from 27_OptionsPremiumTracking.js
 * @param {Sheet} sheet - The output sheet
 */
function EW_setupOptionsPremiumSheet(sheet) {
  const headers = [
    // Basic Info
    'Date',
    'Run_Date',
    'Ticker',
    'Strike',
    'Type',
    'ExpDate',

    // Strike Hit Tracking
    'Bid_Hit_Pct',
    'First_Hit_Date',
    'Bid_Hit_Days',
    'Ask_Hit_Days',
    'Max_Favorable',
    'Min_Unfavorable',

    // Daily Check Values (premium at close each day)
    'Day0_Check',
    'Day1_Check',
    'Day2_Check',
    'Day3_Check',
    'Day4_Check',
    'Day5_Check',
    'Day6_Check',
    'Day7_Check',
    'Day8_Check',
    'Day9_Check',
    'Day10_Check',
    'Day11_Check',
    'Day12_Check',
    'Day13_Check',

    // Expiration Results
    'Exp_Result',
    'Risk_Reward',

    // Options OHLC and Volume
    'OHLC_Volume',

    // Real-time Current Data
    'Bid',
    'Ask',
    'Spread',
    'Volume',

    // P/L Analysis (based on latest day's high/low)
    'PnL_High',
    'PnL_High_Pct',
    'PnL_Low',
    'PnL_Low_Pct',

    'Days_To_Exp',

    // API Metadata
    'API_URL'
  ];

  const headerRange = sheet.getRange(1, 1, 1, headers.length);
  headerRange.setValues([headers]);

  // Set column widths for better readability
  const widths = [
    100,  // Date
    100,  // Run_Date
    80,   // Ticker
    70,   // Strike
    60,   // Type
    100,  // ExpDate
    120,  // Bid_Hit_Pct (array)
    80,   // First_Hit_Date
    120,  // Bid_Hit_Days (array)
    120,  // Ask_Hit_Days (array)
    120,  // Max_Favorable (array)
    120,  // Min_Unfavorable (array)
    90,   // Day0_Check
    90,   // Day1_Check
    90,   // Day2_Check
    90,   // Day3_Check
    90,   // Day4_Check
    90,   // Day5_Check
    90,   // Day6_Check
    90,   // Day7_Check
    90,   // Day8_Check
    90,   // Day9_Check
    90,   // Day10_Check
    90,   // Day11_Check
    90,   // Day12_Check
    90,   // Day13_Check
    90,   // Exp_Result
    90,   // Risk_Reward
    200,  // OHLC_Volume (JSON)
    80,   // Bid
    80,   // Ask
    80,   // Spread
    80,   // Volume
    100,  // PnL_High
    100,  // PnL_High_Pct
    100,  // PnL_Low
    100,  // PnL_Low_Pct
    90,   // Days_To_Exp
    400   // API_URL
  ];

  for (let i = 0; i < widths.length; i++) {
    sheet.setColumnWidth(i + 1, widths[i]);
  }

  // Format columns with proper data types - use header positions instead of hardcoded indexes
  const maxRows = sheet.getMaxRows() - 1;

  // Get column indexes from headers
  const dateCol = headers.indexOf('Date') + 1;
  const runDateCol = headers.indexOf('Run_Date') + 1;
  const tickerCol = headers.indexOf('Ticker') + 1;
  const strikeCol = headers.indexOf('Strike') + 1;
  const typeCol = headers.indexOf('Type') + 1;
  const expDateCol = headers.indexOf('ExpDate') + 1;
  const bidHitPctCol = headers.indexOf('Bid_Hit_Pct') + 1;
  const firstHitDateCol = headers.indexOf('First_Hit_Date') + 1;
  const bidHitDaysCol = headers.indexOf('Bid_Hit_Days') + 1;
  const askHitDaysCol = headers.indexOf('Ask_Hit_Days') + 1;
  const maxFavCol = headers.indexOf('Max_Favorable') + 1;
  const minUnfavCol = headers.indexOf('Min_Unfavorable') + 1;
  const day0Col = headers.indexOf('Day0_Check') + 1;
  const day13Col = headers.indexOf('Day13_Check') + 1;
  const expResultCol = headers.indexOf('Exp_Result') + 1;
  const riskRewardCol = headers.indexOf('Risk_Reward') + 1;
  const ohlcCol = headers.indexOf('OHLC_Volume') + 1;
  const bidCol = headers.indexOf('Bid') + 1;
  const askCol = headers.indexOf('Ask') + 1;
  const spreadCol = headers.indexOf('Spread') + 1;
  const volumeCol = headers.indexOf('Volume') + 1;
  const pnlHighCol = headers.indexOf('PnL_High') + 1;
  const pnlHighPctCol = headers.indexOf('PnL_High_Pct') + 1;
  const pnlLowCol = headers.indexOf('PnL_Low') + 1;
  const pnlLowPctCol = headers.indexOf('PnL_Low_Pct') + 1;
  const daysToExpCol = headers.indexOf('Days_To_Exp') + 1;
  const apiUrlCol = headers.indexOf('API_URL') + 1;

  // Date columns
  [dateCol, runDateCol, expDateCol].forEach(col => {
    if (col > 0) sheet.getRange(2, col, maxRows, 1).setNumberFormat('yyyy-mm-dd');
  });

  // Text columns
  [tickerCol, typeCol].forEach(col => {
    if (col > 0) sheet.getRange(2, col, maxRows, 1).setNumberFormat('@');
  });

  // Number columns
  if (strikeCol > 0) sheet.getRange(2, strikeCol, maxRows, 1).setNumberFormat('0.00');

  // JSON array columns
  [bidHitPctCol, bidHitDaysCol, askHitDaysCol, maxFavCol, minUnfavCol, ohlcCol].forEach(col => {
    if (col > 0) sheet.getRange(2, col, maxRows, 1).setNumberFormat('@');
  });

  // First_Hit_Date
  if (firstHitDateCol > 0) sheet.getRange(2, firstHitDateCol, maxRows, 1).setNumberFormat('0');

  // Day Check columns (Day0-Day13)
  if (day0Col > 0 && day13Col > 0) {
    for (let col = day0Col; col <= day13Col; col++) {
      sheet.getRange(2, col, maxRows, 1).setNumberFormat('0.00');
    }
  }

  // Result columns
  if (expResultCol > 0) sheet.getRange(2, expResultCol, maxRows, 1).setNumberFormat('@');
  if (riskRewardCol > 0) sheet.getRange(2, riskRewardCol, maxRows, 1).setNumberFormat('0.00');

  // Premium data columns
  [bidCol, askCol, spreadCol].forEach(col => {
    if (col > 0) sheet.getRange(2, col, maxRows, 1).setNumberFormat('0.00');
  });

  // Volume
  if (volumeCol > 0) sheet.getRange(2, volumeCol, maxRows, 1).setNumberFormat('0');

  // P/L dollar amounts
  [pnlHighCol, pnlLowCol].forEach(col => {
    if (col > 0) sheet.getRange(2, col, maxRows, 1).setNumberFormat('0.00');
  });

  // P/L percentages
  [pnlHighPctCol, pnlLowPctCol].forEach(col => {
    if (col > 0) sheet.getRange(2, col, maxRows, 1).setNumberFormat('0.00%');
  });

  // Days to expiration
  if (daysToExpCol > 0) sheet.getRange(2, daysToExpCol, maxRows, 1).setNumberFormat('0');

  // API URL
  if (apiUrlCol > 0) sheet.getRange(2, apiUrlCol, maxRows, 1).setNumberFormat('@');

  // Freeze header row
  sheet.setFrozenRows(1);
}

/**
 * Build Yahoo Finance option symbol
 * Migrated from 27_OptionsPremiumTracking.js
 * Format: TICKER + YYMMDD + C/P + 8-digit strike
 * Example: ROKU251107C00060000 (ROKU Nov 7 2025 $60 Call)
 *
 * @param {string} ticker - Underlying ticker
 * @param {Date} expDate - Expiration date
 * @param {string} optionType - 'C' for call, 'P' for put
 * @param {number} strike - Strike price
 * @returns {string} Yahoo option symbol
 */
function EW_buildOptionSymbol(ticker, expDate, optionType, strike) {
  // Year (2 digits)
  const year = String(expDate.getFullYear()).slice(-2);

  // Month (2 digits, padded)
  const month = String(expDate.getMonth() + 1).padStart(2, '0');

  // Day (2 digits, padded)
  const day = String(expDate.getDate()).padStart(2, '0');

  // Strike price (8 digits: 5 before decimal, 3 after)
  const strikePadded = String(Math.round(strike * 1000)).padStart(8, '0');

  // Combine
  const symbol = `${ticker}${year}${month}${day}${optionType}${strikePadded}`;

  return symbol;
}

/**
 * Fetch historical daily premiums for an option symbol using Yahoo Finance chart API
 * Migrated from 27_OptionsPremiumTracking.js
 * @param {string} optionSymbol - Yahoo option symbol
 * @param {Date} startDate - Inclusive start date
 * @param {Date} endDate - Inclusive end date
 * @returns {Array<Object>} Array of OHLC data ordered by day
 */
function EW_fetchOptionPremiumHistory(optionSymbol, startDate, endDate) {
  const history = [];

  if (!optionSymbol || !startDate || !endDate) {
    return history;
  }

  // Adjust start date forward to next trading day (Monday) if it's a weekend
  const adjustedStart = new Date(startDate);
  while (adjustedStart.getDay() === 0 || adjustedStart.getDay() === 6) {
    adjustedStart.setDate(adjustedStart.getDate() + 1);
  }

  // Adjust end date backward to previous trading day (Friday) if it's a weekend
  let adjustedEnd = new Date(endDate);
  while (adjustedEnd.getDay() === 0 || adjustedEnd.getDay() === 6) {
    adjustedEnd.setDate(adjustedEnd.getDate() - 1);
  }

  const period1 = EW_getEasternUnixTimestamp(adjustedStart, 9, 30, 0);
  let period2 = EW_getEasternUnixTimestamp(adjustedEnd, 16, 30, 0);

  // Debug: log the adjusted dates
  const tz = Session.getScriptTimeZone();
  EW_trace('OPTIONS_BACKFILL', `  After weekend adjustment: ${Utilities.formatDate(adjustedStart, tz, 'yyyy-MM-dd')} to ${Utilities.formatDate(adjustedEnd, tz, 'yyyy-MM-dd')}`, false);
  EW_trace('OPTIONS_BACKFILL', `  adjustedEnd day of week: ${adjustedEnd.getDay()} (0=Sun, 6=Sat)`, false);

  if (period1 === null || period2 === null) {
    return history;
  }

  // Ensure period2 is after period1; if not, extend to the next trading day at 4:30 PM ET
  if (period2 <= period1) {
    adjustedEnd = new Date(adjustedEnd);
    adjustedEnd.setDate(adjustedEnd.getDate() + 1);
    // Skip weekends using while loop
    while (adjustedEnd.getDay() === 0 || adjustedEnd.getDay() === 6) {
      adjustedEnd.setDate(adjustedEnd.getDate() + 1);
    }
    period2 = EW_getEasternUnixTimestamp(adjustedEnd, 16, 30, 0);
  }

  const url = `https://query2.finance.yahoo.com/v8/finance/chart/${optionSymbol}?period1=${period1}&period2=${period2}&interval=1d&events=history`;

  // Log detailed date information
  const startDateStr = Utilities.formatDate(adjustedStart, Session.getScriptTimeZone(), 'yyyy-MM-dd');
  const endDateStr = Utilities.formatDate(adjustedEnd, Session.getScriptTimeZone(), 'yyyy-MM-dd');
  EW_trace('OPTIONS_BACKFILL', `Fetching ${optionSymbol} from ${startDateStr} to ${endDateStr}`, false);
  EW_trace('OPTIONS_BACKFILL', `  Original dates: ${Utilities.formatDate(startDate, Session.getScriptTimeZone(), 'yyyy-MM-dd')} to ${Utilities.formatDate(endDate, Session.getScriptTimeZone(), 'yyyy-MM-dd')}`, false);
  EW_trace('OPTIONS_BACKFILL', `  Unix timestamps: period1=${period1}, period2=${period2}`, false);
  EW_trace('OPTIONS_BACKFILL', `  API URL: ${url}`, false);

  try {
    const response = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });

    const responseCode = response.getResponseCode();
    EW_trace('OPTIONS_BACKFILL', `  Response code: ${responseCode}`, false);

    if (responseCode === 401 || responseCode === 403) {
      // Retry with session
      const session = EW_getYahooQuoteSession(true);
      const retryCrumb = session && session.crumb ? `&crumb=${encodeURIComponent(session.crumb)}` : '';
      const retryUrl = `https://query2.finance.yahoo.com/v8/finance/chart/${optionSymbol}?period1=${period1}&period2=${period2}&interval=1d&events=history${retryCrumb}`;
      const retryResponse = UrlFetchApp.fetch(retryUrl, {
        muteHttpExceptions: true,
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
          'Cookie': session.cookie
        }
      });
      return EW_parsePremiumHistoryResponse(optionSymbol, retryResponse);
    }

    if (responseCode !== 200) {
      const responseText = response.getContentText().substring(0, 500); // First 500 chars
      EW_trace('OPTIONS_BACKFILL', `History fetch failed for ${optionSymbol}: HTTP ${responseCode}`, true);
      EW_trace('OPTIONS_BACKFILL', `  Response body: ${responseText}`, false);
      return history;
    }

    return EW_parsePremiumHistoryResponse(optionSymbol, response);

  } catch (error) {
    EW_trace('OPTIONS_BACKFILL', `History fetch error for ${optionSymbol}: ${error.message}`, true);
    return history;
  }
}

/**
 * Parse premium history response from Yahoo Finance
 * Migrated from 27_OptionsPremiumTracking.js
 */
function EW_parsePremiumHistoryResponse(optionSymbol, response) {
  const history = [];

  try {
    const data = JSON.parse(response.getContentText());

    if (!data.chart || !data.chart.result || data.chart.result.length === 0) {
      return history;
    }

    const result = data.chart.result[0];
    const timestamps = result.timestamp || [];
    const quote = result.indicators && result.indicators.quote ? result.indicators.quote[0] : null;
    const adjCloseContainer = result.indicators && result.indicators.adjclose ? result.indicators.adjclose[0] : null;
    const adjCloseArray = adjCloseContainer && adjCloseContainer.adjclose ? adjCloseContainer.adjclose : [];

    if (!quote || timestamps.length === 0) {
      EW_trace('OPTIONS_BACKFILL', `No timestamps or quote data for ${optionSymbol}`, false);
      return history;
    }

    EW_trace('OPTIONS_BACKFILL', `Parsing ${timestamps.length} data points for ${optionSymbol}`, false);

    // Log the dates we received from Yahoo
    const tz = Session.getScriptTimeZone();
    for (let i = 0; i < Math.min(timestamps.length, 5); i++) {
      const date = new Date(timestamps[i] * 1000);
      EW_trace('OPTIONS_BACKFILL', `  Yahoo data point ${i}: ${Utilities.formatDate(date, tz, 'yyyy-MM-dd HH:mm:ss')}`, false);
    }

    const sanitizeNumber = value => {
      if (value === null || value === undefined || value === '') return null;
      const num = Number(value);
      return isNaN(num) ? null : num;
    };

    const getArrayValue = (arr, index) => {
      if (!arr || !Array.isArray(arr) || index >= arr.length) return null;
      return sanitizeNumber(arr[index]);
    };

    let lastClose = null;
    let lastOpen = null;
    let lastHigh = null;
    let lastLow = null;

    for (let i = 0; i < timestamps.length; i++) {
      const rawClose = getArrayValue(quote.close, i);
      const adjClose = getArrayValue(adjCloseArray, i);
      let close = rawClose !== null ? rawClose : (adjClose !== null ? adjClose : lastClose);

      if (close === null) {
        continue;
      }

      let open = getArrayValue(quote.open, i);
      if (open === null) {
        open = lastOpen !== null ? lastOpen : close;
      }

      let high = getArrayValue(quote.high, i);
      if (high === null) {
        high = Math.max(open, close, lastHigh !== null ? lastHigh : close);
      }

      let low = getArrayValue(quote.low, i);
      if (low === null) {
        low = Math.min(open, close, lastLow !== null ? lastLow : close);
      }

      const volume = getArrayValue(quote.volume, i);

      history.push({
        date: new Date(timestamps[i] * 1000),
        open: open,
        high: high,
        low: low,
        close: close,
        volume: volume !== null ? volume : 0
      });

      lastClose = close;
      lastOpen = open;
      lastHigh = high;
      lastLow = low;
    }

  } catch (error) {
    EW_trace('OPTIONS_BACKFILL', `Failed to parse history for ${optionSymbol}: ${error.message}`, true);
  }

  return history;
}

/**
 * Get Yahoo Finance quote session (cookies + crumb)
 * Migrated from 27_OptionsPremiumTracking.js
 */
function EW_getYahooQuoteSession(forceRefresh = false) {
  const cache = (typeof CacheService !== 'undefined') ? CacheService.getScriptCache() : null;
  const cacheKey = 'EW_YAHOO_QUOTE_SESSION';

  if (!forceRefresh && cache) {
    const cachedSession = cache.get(cacheKey);
    if (cachedSession) {
      try {
        const parsed = JSON.parse(cachedSession);
        if (parsed && parsed.crumb && parsed.cookie) {
          return parsed;
        }
      } catch (error) {
        // Ignore parse errors and refresh session
      }
    }
  }

  const userAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36';

  // Step 1: Get cookies
  const cookieResponse = UrlFetchApp.fetch('https://fc.yahoo.com', {
    muteHttpExceptions: true,
    followRedirects: false,
    headers: {
      'User-Agent': userAgent
    }
  });

  const cookieHeaders = cookieResponse.getAllHeaders();
  let initialCookie = EW_extractYahooCookie(cookieHeaders['Set-Cookie'] || cookieHeaders['set-cookie']);

  if (!initialCookie) {
    throw new Error(`Failed to obtain Yahoo Finance cookie: HTTP ${cookieResponse.getResponseCode()}`);
  }

  // Step 2: Get crumb
  const crumbEndpoints = [
    'https://query1.finance.yahoo.com/v1/test/getcrumb',
    'https://query2.finance.yahoo.com/v1/test/getcrumb'
  ];

  let crumb = '';
  let lastStatus = null;

  for (let i = 0; i < crumbEndpoints.length && !crumb; i++) {
    const endpoint = crumbEndpoints[i];
    const response = UrlFetchApp.fetch(endpoint, {
      muteHttpExceptions: true,
      followRedirects: false,
      headers: {
        'User-Agent': userAgent,
        'Cookie': initialCookie
      }
    });

    lastStatus = response.getResponseCode();

    if (lastStatus === 200) {
      const responseCrumb = response.getContentText().trim();
      if (responseCrumb) {
        crumb = responseCrumb;
        const crumbCookie = EW_extractYahooCookie(response.getAllHeaders()['Set-Cookie'] || response.getAllHeaders()['set-cookie']);
        if (crumbCookie) {
          initialCookie = [initialCookie, crumbCookie].filter(Boolean).join('; ');
        }
      }
    }
  }

  if (!crumb) {
    throw new Error(`Failed to obtain Yahoo Finance crumb: HTTP ${lastStatus}`);
  }

  const session = { crumb: crumb, cookie: initialCookie };

  if (cache) {
    try {
      cache.put(cacheKey, JSON.stringify(session), 60 * 55);
    } catch (error) {
      // Ignore cache write errors
    }
  }

  return session;
}

/**
 * Extract Yahoo cookies from Set-Cookie header
 * Migrated from 27_OptionsPremiumTracking.js
 */
function EW_extractYahooCookie(setCookieHeader) {
  if (!setCookieHeader) return '';

  const cookies = Array.isArray(setCookieHeader) ? setCookieHeader : [setCookieHeader];
  const parsed = cookies
    .map(cookie => (cookie || '').split(';')[0])
    .filter(Boolean);

  return parsed.join('; ');
}
