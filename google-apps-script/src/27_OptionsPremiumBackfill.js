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
 * Main function to backfill options premium history for all strategy sheets (INCLUDES EXPIRED)
 * Use this for initial backfill to get historical data
 * Mirrors EW_backfillHistoricalTracking() from 09_HistoricalBackfill.js
 */
function EW_backfillOptionsPremiumHistory() {
  return EW_backfillOptionsPremiumHistoryInternal(true); // includeExpired = true
}

/**
 * Daily update function - only processes non-expired options
 * Use this for regular daily updates
 */
function EW_updateDailyOptionsPremiumHistory() {
  return EW_backfillOptionsPremiumHistoryInternal(false); // includeExpired = false
}

/**
 * Internal function to backfill options premium history
 * @param {boolean} includeExpired - Whether to include expired options
 */
function EW_backfillOptionsPremiumHistoryInternal(includeExpired) {
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
      const backfilled = EW_backfillStrategyOptionsPremium(ss, strategyName, startTime, MAX_RUNTIME_MS, includeExpired);

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
 * @param {boolean} includeExpired - Whether to include expired options
 * @returns {number} Number of positions processed, or -1 if continuation needed
 */
function EW_backfillStrategyOptionsPremium(ss, strategyName, startTime = null, maxRuntimeMs = null, includeExpired = true) {
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

  // Read positions from source sheet
  const positions = EW_readOptionsPositions(sourceSheet, strategyName, includeExpired);

  if (positions.length === 0) {
    EW_trace('OPTIONS_BACKFILL', `${strategyName}: No positions to process`, false);
    return 0;
  }

  // Get existing positions in output sheet to avoid duplicates
  const existingPositions = EW_getExistingPositions(outputSheet);

  // For this backfill script, we only process NEW positions (not in tracking sheet yet)
  // This is different from daily tracking which updates existing positions
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

      // Adjust entry date to market hours (9:30 AM - 4:00 PM ET)
      // This uses the same EW_adjustToMarketHours function from 09_HistoricalBackfill.js
      const marketEntryDate = EW_adjustToMarketHours(position.runDate);

      const tz = Session.getScriptTimeZone();
      EW_trace('OPTIONS_BACKFILL', `[${position.ticker}] Original entry date: ${Utilities.formatDate(position.runDate, tz, 'yyyy-MM-dd HH:mm:ss')}, Adjusted to market hours: ${Utilities.formatDate(marketEntryDate, tz, 'yyyy-MM-dd HH:mm:ss')}`, false);

      // Calculate end date: use expiration or today (whichever is earlier)
      // This mirrors the logic in 09_HistoricalBackfill.js to fetch full date range
      const today = new Date();
      today.setHours(0, 0, 0, 0);

      let endDate;
      if (position.expDate && position.expDate < today) {
        // Option has expired, use expiration date
        endDate = new Date(position.expDate);
        endDate.setHours(16, 0, 0, 0); // Market close on expiration
      } else {
        // Option is still active or expiration is in future, use today
        endDate = new Date(today);
        endDate.setHours(16, 0, 0, 0); // Market close
      }

      // Cap end date at today's market close if needed
      const todayMarketClose = new Date();
      const currentHour = todayMarketClose.getHours();
      if (currentHour < 9 || (currentHour === 9 && todayMarketClose.getMinutes() < 30)) {
        // Before market open, use yesterday's close
        todayMarketClose.setDate(todayMarketClose.getDate() - 1);
        todayMarketClose.setHours(16, 0, 0, 0);
      } else if (currentHour >= 16) {
        // After market close, use today's close
        todayMarketClose.setHours(16, 0, 0, 0);
      }

      if (endDate > todayMarketClose) {
        endDate = todayMarketClose;
      }

      // DIAGNOSTIC: Log the dates being used for API call
      EW_trace('OPTIONS_BACKFILL', `[${position.ticker}] API call: from ${Utilities.formatDate(marketEntryDate, tz, 'yyyy-MM-dd HH:mm:ss')} to ${Utilities.formatDate(endDate, tz, 'yyyy-MM-dd HH:mm:ss')}`, false);

      // Fetch historical premium data for the full date range
      // Yahoo API will automatically skip weekends and return only trading days
      const premiumHistory = EW_fetchOptionPremiumHistory(optionSymbol, marketEntryDate, endDate);

      if (premiumHistory && premiumHistory.length > 0) {
        // Update or create tracking row
        EW_updateOptionsPremiumBackfillRow(
          outputSheet,
          position,
          premiumHistory,
          strategyName
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
 *
 * IMPORTANT: Premium tracking logic
 * - This tracks OPTION PREMIUM prices (not underlying stock prices)
 * - Profit occurs when premium INCREASES (sell at higher premium than entry)
 * - Loss occurs when premium DECREASES (premium falls below entry)
 * - Therefore: ALWAYS use HIGH for best profit, LOW for worst loss
 * - Strategy (Call/Put/Bull/Bear) only determines which option to fetch, not tracking logic
 *
 * @param {Sheet} outputSheet - Output sheet
 * @param {Object} position - Position info
 * @param {Array} premiumHistory - Array of historical OHLC premium data
 * @param {string} strategyType - Strategy type
 */
function EW_updateOptionsPremiumBackfillRow(outputSheet, position, premiumHistory, strategyType) {
  const tz = Session.getScriptTimeZone();

  // Use dates directly from position (already normalized when read from sheet)
  const entryDate = position.runDate;  // Already normalized to midnight
  const expDate = position.expDate;    // Already normalized
  const runDate = position.runDate;    // Already normalized

  // Get today's date normalized to midnight
  const todayRaw = new Date();
  const today = new Date(todayRaw.getFullYear(), todayRaw.getMonth(), todayRaw.getDate(), 0, 0, 0, 0);

  // DIAGNOSTIC: Log what we're using
  EW_trace('OPTIONS_BACKFILL', `[${position.ticker}] Using runDate: ${Utilities.formatDate(runDate, tz, 'yyyy-MM-dd')}`, false);
  EW_trace('OPTIONS_BACKFILL', `[${position.ticker}] Strategy: ${strategyType}`, false);

  const MAX_TRACKING_DAYS = 14;

  // Prepare arrays
  const strikeHitArray = Array(MAX_TRACKING_DAYS).fill('0.000000');
  const maxFavorableArray = Array(MAX_TRACKING_DAYS).fill('0.000000');
  const minUnfavorableArray = Array(MAX_TRACKING_DAYS).fill('0.000000');
  const bidHitDaysArray = Array(MAX_TRACKING_DAYS).fill('0.000000');
  const askHitDaysArray = Array(MAX_TRACKING_DAYS).fill('0.000000');
  const ohlcVolumeArray = Array(MAX_TRACKING_DAYS).fill(null);
  const dayCheckValues = Array(MAX_TRACKING_DAYS).fill('');

  // Build map for easy lookup
  const premiumMap = {};

  for (const item of premiumHistory) {
    const key = Utilities.formatDate(new Date(item.date), tz, 'yyyy-MM-dd');
    premiumMap[key] = item;
  }

  EW_trace('OPTIONS_BACKFILL', `Premium history for ${position.ticker}: ${premiumHistory.length} days, keys: ${Object.keys(premiumMap).join(', ')}`, false);
  EW_trace('OPTIONS_BACKFILL', `Using entry price from position.bid: ${position.bid}`, false);

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
      // Premium tracking: ALWAYS use HIGH for best profit opportunity
      // Premium increases = profit, regardless of Call/Put strategy
      dayCheckValues[tradingDayIndex] = dayData.high;

      // Build OHLC entry - match format from 09_HistoricalBackfill.js
      ohlcVolumeArray[tradingDayIndex] = {
        o: dayData.open ? parseFloat(dayData.open).toFixed(2) : null,
        h: dayData.high ? parseFloat(dayData.high).toFixed(2) : null,
        l: dayData.low ? parseFloat(dayData.low).toFixed(2) : null,
        c: dayData.close ? parseFloat(dayData.close).toFixed(2) : null,
        v: dayData.volume !== null && dayData.volume !== undefined ? dayData.volume : null,
        src: 'YAHOO'
      };

      // Calculate P/L arrays if we have entry price
      if (position.bid) {
        const entryCost = position.bid * 100;

        // Premium tracking: ALWAYS use HIGH for best profit opportunity
        // Premium increases = profit, regardless of Call/Put strategy
        const exitPrice = dayData.high;

        // Bid_Hit_Pct: Daily profit/loss percentage
        if (exitPrice !== null) {
          const pnl = (exitPrice - position.bid) * 100;
          const pnlPct = pnl / entryCost;
          strikeHitArray[tradingDayIndex] = pnlPct.toFixed(6);

          // Check for first profitable day
          if (hitDate === '' && pnlPct > 0) {
            hitDate = tradingDayIndex;
          }
        }

        // Max favorable (highest premium during the day - actual value, not forced to 0)
        if (dayData.high !== null) {
          const maxPnl = (dayData.high - position.bid) * 100;
          const maxPct = maxPnl / entryCost;
          maxFavorableArray[tradingDayIndex] = maxPct.toFixed(6);
        }

        // Min unfavorable (lowest premium during the day - actual value, not forced to 0)
        if (dayData.low !== null) {
          const minPnl = (dayData.low - position.bid) * 100;
          const minPct = minPnl / entryCost;
          minUnfavorableArray[tradingDayIndex] = minPct.toFixed(6);
        }

        // TODO: Bid_Hit_Days and Ask_Hit_Days logic removed because position.bid is the entry price
        // If these arrays need to track something else (e.g., current bid/ask from source sheet),
        // the logic needs to be redesigned with different target values
      }
    }

    tradingDayIndex++;
  }

  // Default any uninitialized OHLC entries
  for (let i = 0; i < MAX_TRACKING_DAYS; i++) {
    if (!ohlcVolumeArray[i]) {
      ohlcVolumeArray[i] = { o: null, h: null, l: null, c: null, v: null, src: 'YAHOO' };
    }
  }

  // Calculate expiration result if position is expired
  let expResult = '';
  let riskReward = '';

  if (position.expDate < today) {
    const expKey = Utilities.formatDate(position.expDate, tz, 'yyyy-MM-dd');
    const expData = premiumMap[expKey];

    if (expData && position.bid) {
      expResult = expData.close;

      // Calculate risk/reward from arrays
      const maxFav = parseFloat(Math.max(...maxFavorableArray.map(v => parseFloat(v) || 0)));
      const minUnfav = parseFloat(Math.min(...minUnfavorableArray.map(v => parseFloat(v) || 0)));

      if (Math.abs(minUnfav) > 0) {
        riskReward = (maxFav / Math.abs(minUnfav)).toFixed(2);
      }
    }
  }

  // Calculate P/L (high and low) based on historical OHLC data
  // PnL_High = best possible profit from historical highs
  // PnL_Low = worst possible loss from historical lows
  let pnlCurrentHigh = '';
  let pnlCurrentHighPct = '';
  let pnlCurrentLow = '';
  let pnlCurrentLowPct = '';

  if (position.bid) {
    const entryCost = position.bid * 100;

    // Find the highest and lowest premium across all days
    let historicalHigh = null;
    let historicalLow = null;

    for (const ohlc of ohlcVolumeArray) {
      if (ohlc && ohlc.h !== null) {
        const high = parseFloat(ohlc.h);
        if (historicalHigh === null || high > historicalHigh) {
          historicalHigh = high;
        }
      }
      if (ohlc && ohlc.l !== null) {
        const low = parseFloat(ohlc.l);
        if (historicalLow === null || low < historicalLow) {
          historicalLow = low;
        }
      }
    }

    // Calculate P/L based on historical extremes
    if (historicalHigh !== null) {
      pnlCurrentHigh = (historicalHigh - position.bid) * 100;
      pnlCurrentHighPct = Number((pnlCurrentHigh / entryCost).toFixed(6));
    }

    if (historicalLow !== null) {
      pnlCurrentLow = (historicalLow - position.bid) * 100;
      pnlCurrentLowPct = Number((pnlCurrentLow / entryCost).toFixed(6));
    }
  }

  // Calculate days to expiration
  const daysToExp = Math.ceil((expDate - today) / (1000 * 60 * 60 * 24));

  // Build option symbol for API URL
  const optionSymbol = EW_buildOptionSymbol(position.ticker, expDate, position.optionType, position.strike);

  // Build Yahoo Finance API URL for historical premium data
  // Use the same date range logic as the actual fetch (runDate to earlier of today/expiration)
  let apiEndDate = today;
  if (expDate < today) {
    apiEndDate = expDate;
  }

  const period1 = Math.floor(entryDate.getTime() / 1000);
  const period2 = Math.floor(apiEndDate.getTime() / 1000);
  const apiUrl = `https://query2.finance.yahoo.com/v8/finance/chart/${optionSymbol}?period1=${period1}&period2=${period2}&interval=1d&events=history`;

  // DIAGNOSTIC: Log what's about to be written
  const runDateStr = Utilities.formatDate(runDate, tz, 'yyyy-MM-dd');
  EW_trace('OPTIONS_BACKFILL', `[${position.ticker}] WRITING TO SHEET: runDate=${runDateStr}`, false);

  // Build row - use formatted date strings to avoid timezone issues
  const todayStr = Utilities.formatDate(today, tz, 'yyyy-MM-dd');
  const expDateStr = Utilities.formatDate(expDate, tz, 'yyyy-MM-dd');

  const row = [
    todayStr,                                 // Date (today - when script runs) - String
    runDateStr,                               // Run_Date (entry date from source sheet) - String
    position.ticker,                          // Ticker
    position.strike,                          // Strike
    position.optionType,                      // Type
    expDateStr,                               // ExpDate - String
    JSON.stringify(strikeHitArray),           // Bid_Hit_Pct array
    hitDate,                                   // First_Hit_Date
    JSON.stringify(bidHitDaysArray),          // Bid_Hit_Days array
    JSON.stringify(askHitDaysArray),          // Ask_Hit_Days array
    JSON.stringify(maxFavorableArray),        // Max_Favorable array
    JSON.stringify(minUnfavorableArray),      // Min_Unfavorable array
    ...dayCheckValues,                         // Day0-Day13 Check columns
    expResult,                                 // Exp_Result
    riskReward,                                // Risk_Reward
    JSON.stringify(ohlcVolumeArray),          // OHLC_Volume array
    position.bid || '',                       // Bid (from source sheet)
    position.ask || '',                       // Ask (from source sheet)
    (position.ask && position.bid) ? (position.ask - position.bid) : '', // Spread
    position.volume || 0,                     // Volume (from source sheet)
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
    if (hdrMap.bidCol) outputSheet.getRange(existingRowNum, hdrMap.bidCol).setValue(position.bid || '');
    if (hdrMap.askCol) outputSheet.getRange(existingRowNum, hdrMap.askCol).setValue(position.ask || '');
    if (hdrMap.spreadCol && position.bid && position.ask) {
      outputSheet.getRange(existingRowNum, hdrMap.spreadCol).setValue(position.ask - position.bid);
    }
    if (hdrMap.volumeCol) {
      const volumeRange = outputSheet.getRange(existingRowNum, hdrMap.volumeCol);
      volumeRange.setNumberFormat('0');
      volumeRange.setValue(position.volume || 0);
    }
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

    // Get only the columns we need for matching (including runDate)
    const numCols = Math.max(hdrMap.tickerCol, hdrMap.strikeCol, hdrMap.expDateCol, hdrMap.runDateCol || 0);
    const data = outputSheet.getRange(2, 1, lastRow - 1, numCols).getValues();
    const expDateStr = Utilities.formatDate(position.expDate, Session.getScriptTimeZone(), 'yyyy-MM-dd');
    const posRunDateStr = Utilities.formatDate(position.runDate, Session.getScriptTimeZone(), 'yyyy-MM-dd');

    EW_trace('OPTIONS_BACKFILL', `Finding row for ${position.ticker}: runDateCol=${hdrMap.runDateCol}, posRunDate=${posRunDateStr}`, false);

    let matchCount = 0;
    for (let i = 0; i < data.length; i++) {
      const ticker = String(data[i][hdrMap.tickerCol - 1]);
      const strike = parseFloat(data[i][hdrMap.strikeCol - 1]);
      const rowExpDateStr = data[i][hdrMap.expDateCol - 1] instanceof Date ?
        Utilities.formatDate(data[i][hdrMap.expDateCol - 1], Session.getScriptTimeZone(), 'yyyy-MM-dd') :
        String(data[i][hdrMap.expDateCol - 1]);

      // Also check runDate to match the exact position
      const rowRunDate = hdrMap.runDateCol ? data[i][hdrMap.runDateCol - 1] : null;
      const rowRunDateStr = rowRunDate instanceof Date ?
        Utilities.formatDate(rowRunDate, Session.getScriptTimeZone(), 'yyyy-MM-dd') :
        (rowRunDate ? String(rowRunDate) : '');

      // Log potential partial matches for this ticker
      if (ticker === position.ticker && Math.abs(strike - position.strike) < 0.01) {
        EW_trace('OPTIONS_BACKFILL', `  Checking row ${i+2}: ticker=${ticker}, strike=${strike}, rowRunDate=${rowRunDateStr}, rowExp=${rowExpDateStr}, posExp=${expDateStr}`, false);
        matchCount++;
      }

      if (ticker === position.ticker &&
          Math.abs(strike - position.strike) < 0.01 &&
          rowExpDateStr === expDateStr &&
          rowRunDateStr === posRunDateStr) {
        EW_trace('OPTIONS_BACKFILL', `  MATCH FOUND at row ${i+2}: rowRunDate=${rowRunDateStr}`, false);
        return i + 2; // Row number (data starts at row 2)
      }
    }

    EW_trace('OPTIONS_BACKFILL', `  NO MATCH found for ${position.ticker} (checked ${matchCount} rows with matching ticker/strike)`, false);
  } catch (error) {
    EW_trace('OPTIONS_BACKFILL', `Error finding row: ${error.message}`, false);
  }

  return null;
}

/**
 * Apply formatting to option premium row using dynamic header mapping
 * @param {Sheet} sheet - Output sheet
 * @param {number} rowNum - Row number to format
 */
function EW_formatOptionsPremiumRow(sheet, rowNum) {
  // Get headers and create column map dynamically
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);

  // Date columns
  if (hdrMap.dateCol) sheet.getRange(rowNum, hdrMap.dateCol).setNumberFormat('yyyy-mm-dd');
  if (hdrMap.runDateCol) sheet.getRange(rowNum, hdrMap.runDateCol).setNumberFormat('yyyy-mm-dd');
  if (hdrMap.expDateCol) sheet.getRange(rowNum, hdrMap.expDateCol).setNumberFormat('yyyy-mm-dd');

  // Text columns
  if (hdrMap.tickerCol) sheet.getRange(rowNum, hdrMap.tickerCol).setNumberFormat('@');
  if (hdrMap.typeCol) sheet.getRange(rowNum, hdrMap.typeCol).setNumberFormat('@');

  // Number (Strike)
  if (hdrMap.strikeCol) sheet.getRange(rowNum, hdrMap.strikeCol).setNumberFormat('0.00');

  // JSON arrays
  if (hdrMap.bidHitPctCol) sheet.getRange(rowNum, hdrMap.bidHitPctCol).setNumberFormat('@');
  if (hdrMap.bidHitDaysCol) sheet.getRange(rowNum, hdrMap.bidHitDaysCol).setNumberFormat('@');
  if (hdrMap.askHitDaysCol) sheet.getRange(rowNum, hdrMap.askHitDaysCol).setNumberFormat('@');
  if (hdrMap.maxFavorableCol) sheet.getRange(rowNum, hdrMap.maxFavorableCol).setNumberFormat('@');
  if (hdrMap.minUnfavorableCol) sheet.getRange(rowNum, hdrMap.minUnfavorableCol).setNumberFormat('@');
  if (hdrMap.ohlcVolumeCol) sheet.getRange(rowNum, hdrMap.ohlcVolumeCol).setNumberFormat('@');

  // Hit_Date
  if (hdrMap.firstHitDateCol) sheet.getRange(rowNum, hdrMap.firstHitDateCol).setNumberFormat('0');

  // Day Check columns (Day0-Day13)
  if (hdrMap.day0CheckCol && hdrMap.day13CheckCol) {
    const numDayCols = hdrMap.day13CheckCol - hdrMap.day0CheckCol + 1;
    sheet.getRange(rowNum, hdrMap.day0CheckCol, 1, numDayCols).setNumberFormat('0.00');
  }

  // Result columns
  if (hdrMap.expResultCol) sheet.getRange(rowNum, hdrMap.expResultCol).setNumberFormat('@');
  if (hdrMap.riskRewardCol) sheet.getRange(rowNum, hdrMap.riskRewardCol).setNumberFormat('0.00');

  // Premium data (Bid, Ask, Spread)
  if (hdrMap.bidCol) sheet.getRange(rowNum, hdrMap.bidCol).setNumberFormat('0.00');
  if (hdrMap.askCol) sheet.getRange(rowNum, hdrMap.askCol).setNumberFormat('0.00');
  if (hdrMap.spreadCol) sheet.getRange(rowNum, hdrMap.spreadCol).setNumberFormat('0.00');

  // Volume
  if (hdrMap.volumeCol) sheet.getRange(rowNum, hdrMap.volumeCol).setNumberFormat('0');

  // P/L dollar amounts
  if (hdrMap.pnlHighCol) sheet.getRange(rowNum, hdrMap.pnlHighCol).setNumberFormat('0.00');
  if (hdrMap.pnlLowCol) sheet.getRange(rowNum, hdrMap.pnlLowCol).setNumberFormat('0.00');

  // P/L percentages
  if (hdrMap.pnlHighPctCol) sheet.getRange(rowNum, hdrMap.pnlHighPctCol).setNumberFormat('0.00%');
  if (hdrMap.pnlLowPctCol) sheet.getRange(rowNum, hdrMap.pnlLowPctCol).setNumberFormat('0.00%');

  // Days to expiration
  if (hdrMap.daysToExpCol) sheet.getRange(rowNum, hdrMap.daysToExpCol).setNumberFormat('0');

  // API URL
  if (hdrMap.apiUrlCol) sheet.getRange(rowNum, hdrMap.apiUrlCol).setNumberFormat('@');
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

  // Determine option type based on strategy: Calls for bullish, Puts for bearish
  const strategyUpper = strategyName.toUpperCase();
  const isSpread = strategyUpper.includes('SPREAD');
  const usesPuts = (strategyUpper.includes('LONG PUT') || strategyUpper.includes('LONG PUTS'))
                   || (strategyUpper.includes('BEAR') && !isSpread)
                   || strategyUpper.includes('COVERED');

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

    // Determine option type: C for calls (bullish), P for puts (bearish)
    let optionType = usesPuts ? 'P' : 'C';

    const position = {
      ticker: ticker,
      strike: strike,
      expDate: expDate,
      runDate: runDate,
      optionType: optionType,
      entryPremium: entryPremium,
      strategyType: strategyName
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
          strategyName
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
/**
 * Read options positions from a strategy sheet
 * @param {Sheet} sheet - Source strategy sheet
 * @param {string} strategyName - Strategy name (e.g., "Long Calls", "Bear Spreads")
 * @param {boolean} includeExpired - Whether to include expired options (default: true for backfill)
 * @returns {Array} Array of position objects
 */
function EW_readOptionsPositions(sheet, strategyName, includeExpired = true) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];

  // Determine option type based on strategy: Calls for bullish, Puts for bearish
  const strategyUpper = strategyName.toUpperCase();
  const isSpread = strategyUpper.includes('SPREAD');
  const usesPuts = (strategyUpper.includes('LONG PUT') || strategyUpper.includes('LONG PUTS'))
                   || (strategyUpper.includes('BEAR') && !isSpread)
                   || strategyUpper.includes('COVERED');

  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = {};

  // Build header map
  for (let i = 0; i < headers.length; i++) {
    const header = String(headers[i]).toLowerCase().trim().replace(/\s+/g, '');
    if (header === 'ticker') hdrMap.ticker = i;
    if (header === 'strike') hdrMap.strike = i;
    if (header === 'expdate' || header === 'expiration') hdrMap.expDate = i;
    if (header === 'rundate' || header === 'entrydate' || header === 'scandate') hdrMap.runDate = i;
    if (header === 'bid') hdrMap.bid = i;
    if (header === 'ask') hdrMap.ask = i;
    if (header === 'volume') hdrMap.volume = i;
    if (header === 'entry_premium' || header === 'entrypremium') {
      hdrMap.entryPremium = i;
    } else if (header === 'bid' && hdrMap.entryPremium === undefined) {
      // Fallback: use bid as entry premium if no explicit entry_premium column
      hdrMap.entryPremium = i;
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

    // Normalize expDate to date-only (strip time)
    const rawExpDate = row[hdrMap.expDate];
    const tempExpDate = new Date(rawExpDate);
    const expDate = new Date(tempExpDate.getFullYear(), tempExpDate.getMonth(), tempExpDate.getDate(), 0, 0, 0, 0);

    // Read and normalize runDate - handle both Date objects and date strings
    const rawRunDate = hdrMap.runDate !== undefined ? row[hdrMap.runDate] : null;
    let runDate = null;
    if (rawRunDate) {
      // Create a new Date and normalize to midnight using year/month/date constructor
      // This avoids timezone issues with setHours
      const tempDate = new Date(rawRunDate);
      runDate = new Date(tempDate.getFullYear(), tempDate.getMonth(), tempDate.getDate(), 0, 0, 0, 0);
    }

    if (runDate && i === data.length - 1) {  // Log only first position (newest)
      EW_trace('OPTIONS_BACKFILL', `[${ticker}] RAW runDate from sheet: ${rawRunDate} (type: ${typeof rawRunDate})`, false);
      EW_trace('OPTIONS_BACKFILL', `[${ticker}] runDate AFTER normalization: ${Utilities.formatDate(runDate, Session.getScriptTimeZone(), 'yyyy-MM-dd')}`, false);
    }

    const entryPremium = hdrMap.entryPremium !== undefined ? parseFloat(row[hdrMap.entryPremium]) : null;
    const bid = hdrMap.bid !== undefined ? parseFloat(row[hdrMap.bid]) : null;
    const ask = hdrMap.ask !== undefined ? parseFloat(row[hdrMap.ask]) : null;
    const volume = hdrMap.volume !== undefined ? parseFloat(row[hdrMap.volume]) : null;

    // Skip if missing data
    if (!ticker || isNaN(strike) || !expDate) continue;

    // Check expiration based on mode
    if (!includeExpired && expDate < today) {
      // Daily mode: Skip expired options
      continue;
    }
    // Backfill mode: Include expired positions for historical data

    // Filter out weekend runDates - skip positions from Saturday/Sunday scans
    if (runDate) {
      const dayOfWeek = runDate.getDay();
      // const runDateStr = Utilities.formatDate(runDate, Session.getScriptTimeZone(), 'yyyy-MM-dd (EEE)');

      if (dayOfWeek === 0 || dayOfWeek === 6) {
        // Skip weekend entries - they cause API errors
        // EW_trace('OPTIONS_BACKFILL', `FILTERED OUT weekend runDate: ${ticker} ${runDateStr}`, false);
        continue;
      }

      // Skip today's positions unless it's after 4:30 PM EDT (market close + settlement time)
      if (runDate.getTime() === today.getTime()) {
        const now = new Date();
        const edtOffset = -4 * 60; // EDT is UTC-4
        const currentHourEDT = now.getUTCHours() + (edtOffset / 60);
        const currentMinuteEDT = now.getUTCMinutes();
        const currentTimeEDT = currentHourEDT + (currentMinuteEDT / 60);

        // Market closes at 4:00 PM, data available after 4:30 PM EDT
        const marketDataAvailableTime = 16.5; // 4:30 PM in decimal hours

        if (currentTimeEDT < marketDataAvailableTime) {
          // Skip today's positions - market data not yet available
          continue;
        }
      }

      // EW_trace('OPTIONS_BACKFILL', `ACCEPTED runDate: ${ticker} ${runDateStr} (day ${dayOfWeek})`, false);

      // Uncomment to only process today's scans:
      // if (runDate.getTime() !== today.getTime()) continue;
    }

    // Determine option type: C for calls (bullish), P for puts (bearish)
    let optionType = usesPuts ? 'P' : 'C';

    const finalRunDate = runDate || today;

    // EW_trace('OPTIONS_BACKFILL', `Adding position: ${ticker} runDate=${finalRunDate ? Utilities.formatDate(finalRunDate, Session.getScriptTimeZone(), 'yyyy-MM-dd') : 'NULL'} (from sheet: ${runDate ? 'YES' : 'NO, using today'})`, false);

    positions.push({
      ticker: ticker,
      strike: strike,
      expDate: expDate,
      runDate: finalRunDate,  // Use runDate from sheet, fallback to today
      optionType: optionType,
      entryPremium: entryPremium,
      bid: bid,
      ask: ask,
      volume: volume,
      rowNum: i + 2,
      strategyType: strategyName
    });
  }

  EW_trace('OPTIONS_BACKFILL', `Total positions read: ${positions.length}`, false);

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

  // Format columns with proper data types - use header map for consistency
  const maxRows = sheet.getMaxRows() - 1;

  // Get column indexes using EW_headerMap
  const hdrMap = EW_headerMap(headers);

  // Date columns
  [hdrMap.dateCol, hdrMap.runDateCol, hdrMap.expDateCol].forEach(col => {
    if (col) sheet.getRange(2, col, maxRows, 1).setNumberFormat('yyyy-mm-dd');
  });

  // Text columns
  [hdrMap.tickerCol, hdrMap.typeCol].forEach(col => {
    if (col) sheet.getRange(2, col, maxRows, 1).setNumberFormat('@');
  });

  // Number columns
  if (hdrMap.strikeCol) sheet.getRange(2, hdrMap.strikeCol, maxRows, 1).setNumberFormat('0.00');

  // JSON array columns
  [hdrMap.bidHitPctCol, hdrMap.bidHitDaysCol, hdrMap.askHitDaysCol, hdrMap.maxFavorableCol, hdrMap.minUnfavorableCol, hdrMap.ohlcVolumeCol].forEach(col => {
    if (col) sheet.getRange(2, col, maxRows, 1).setNumberFormat('@');
  });

  // First_Hit_Date
  if (hdrMap.firstHitDateCol) sheet.getRange(2, hdrMap.firstHitDateCol, maxRows, 1).setNumberFormat('0');

  // Day Check columns (Day0-Day13)
  if (hdrMap.day0CheckCol && hdrMap.day13CheckCol) {
    for (let col = hdrMap.day0CheckCol; col <= hdrMap.day13CheckCol; col++) {
      sheet.getRange(2, col, maxRows, 1).setNumberFormat('0.00');
    }
  }

  // Result columns
  if (hdrMap.expResultCol) sheet.getRange(2, hdrMap.expResultCol, maxRows, 1).setNumberFormat('@');
  if (hdrMap.riskRewardCol) sheet.getRange(2, hdrMap.riskRewardCol, maxRows, 1).setNumberFormat('0.00');

  // Premium data columns
  [hdrMap.bidCol, hdrMap.askCol, hdrMap.spreadCol].forEach(col => {
    if (col) sheet.getRange(2, col, maxRows, 1).setNumberFormat('0.00');
  });

  // Volume
  if (hdrMap.volumeCol) sheet.getRange(2, hdrMap.volumeCol, maxRows, 1).setNumberFormat('0');

  // P/L dollar amounts
  [hdrMap.pnlHighCol, hdrMap.pnlLowCol].forEach(col => {
    if (col) sheet.getRange(2, col, maxRows, 1).setNumberFormat('0.00');
  });

  // P/L percentages
  [hdrMap.pnlHighPctCol, hdrMap.pnlLowPctCol].forEach(col => {
    if (col) sheet.getRange(2, col, maxRows, 1).setNumberFormat('0.00%');
  });

  // Days to expiration
  if (hdrMap.daysToExpCol) sheet.getRange(2, hdrMap.daysToExpCol, maxRows, 1).setNumberFormat('0');

  // API URL
  if (hdrMap.apiUrlCol) sheet.getRange(2, hdrMap.apiUrlCol, maxRows, 1).setNumberFormat('@');

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

// ========================================
// DATA FIX FUNCTIONS
// ========================================

/**
 * Fix PnL_High and PnL_Low columns to use historical OHLC highs/lows instead of current bid/ask
 * This function recalculates P/L based on the OHLC_Volume array data
 */
function EW_fixOptionsPremiumPnL() {
  const ss = SpreadsheetApp.getActive();
  const optionStrategies = ['Long Calls', 'Bull Spreads', 'Bear Spreads', 'Strangles', 'Covered Calls'];

  let totalFixed = 0;
  const errors = [];

  for (const strategyName of optionStrategies) {
    const outputSheetName = `${strategyName} Options`;
    const outputSheet = ss.getSheetByName(outputSheetName);

    if (!outputSheet || outputSheet.getLastRow() < 2) {
      continue;
    }

    try {
      const fixed = EW_fixSheetPnL(outputSheet, strategyName);
      totalFixed += fixed;
      EW_trace('OPTIONS_PNL_FIX', `Fixed ${fixed} rows in ${strategyName}`);
    } catch (error) {
      const errorMsg = `${strategyName}: ${error.message}`;
      errors.push(errorMsg);
      EW_trace('OPTIONS_PNL_FIX', errorMsg, true);
    }
  }

  SpreadsheetApp.flush();

  const msg = `Fixed PnL columns for ${totalFixed} positions across ${optionStrategies.length} strategies.` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');

  EW_trace('OPTIONS_PNL_FIX', msg, true);
  if (EW_isSpreadsheetEnvironment()) {
    EW_safeAlert('P/L Fix Complete', msg);
  }

  return msg;
}

/**
 * Fix PnL columns for a single sheet
 * @param {Sheet} sheet - Options tracking sheet
 * @param {string} strategyName - Strategy name for logging
 * @returns {number} Number of rows fixed
 */
function EW_fixSheetPnL(sheet, strategyName) {
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);

  // Validate required columns
  if (!hdrMap.ohlcVolumeCol || !hdrMap.pnlHighCol || !hdrMap.pnlLowCol) {
    EW_trace('OPTIONS_PNL_FIX', `${strategyName}: Missing required columns`, true);
    return 0;
  }

  const lastRow = sheet.getLastRow();
  const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();

  let fixedCount = 0;

  for (let i = 0; i < data.length; i++) {
    const rowNum = i + 2;
    const row = data[i];

    // Get entry price from Bid column
    const entryPrice = hdrMap.bidCol ? parseFloat(row[hdrMap.bidCol - 1]) : null;
    if (!entryPrice) continue;

    // Get OHLC_Volume array
    const ohlcVolumeJson = row[hdrMap.ohlcVolumeCol - 1];
    if (!ohlcVolumeJson) continue;

    let ohlcVolumeArray;
    try {
      ohlcVolumeArray = JSON.parse(ohlcVolumeJson);
    } catch (error) {
      continue;
    }

    // Find historical high and low
    let historicalHigh = null;
    let historicalLow = null;

    for (const ohlc of ohlcVolumeArray) {
      if (ohlc && ohlc.h !== null) {
        const high = parseFloat(ohlc.h);
        if (historicalHigh === null || high > historicalHigh) {
          historicalHigh = high;
        }
      }
      if (ohlc && ohlc.l !== null) {
        const low = parseFloat(ohlc.l);
        if (historicalLow === null || low < historicalLow) {
          historicalLow = low;
        }
      }
    }

    // Calculate new P/L values
    const entryCost = entryPrice * 100;
    let pnlHigh = '';
    let pnlHighPct = '';
    let pnlLow = '';
    let pnlLowPct = '';

    if (historicalHigh !== null) {
      pnlHigh = (historicalHigh - entryPrice) * 100;
      pnlHighPct = Number((pnlHigh / entryCost).toFixed(6));
    }

    if (historicalLow !== null) {
      pnlLow = (historicalLow - entryPrice) * 100;
      pnlLowPct = Number((pnlLow / entryCost).toFixed(6));
    }

    // Update the cells
    if (pnlHigh !== '') {
      sheet.getRange(rowNum, hdrMap.pnlHighCol).setValue(pnlHigh);
      if (hdrMap.pnlHighPctCol) {
        sheet.getRange(rowNum, hdrMap.pnlHighPctCol).setValue(pnlHighPct);
      }
    }

    if (pnlLow !== '') {
      sheet.getRange(rowNum, hdrMap.pnlLowCol).setValue(pnlLow);
      if (hdrMap.pnlLowPctCol) {
        sheet.getRange(rowNum, hdrMap.pnlLowPctCol).setValue(pnlLowPct);
      }
    }

    fixedCount++;
  }

  return fixedCount;
}

/**
 * Fix Bid_Hit_Pct, Day check values, and First_Hit_Date using strategy-specific high/low logic
 * This recalculates arrays from existing OHLC_Volume data
 */
function EW_fixOptionsPremiumArrays() {
  const ss = SpreadsheetApp.getActive();
  const optionStrategies = ['Long Calls', 'Bull Spreads', 'Bear Spreads', 'Strangles', 'Covered Calls'];

  let totalFixed = 0;
  const errors = [];

  for (const strategyName of optionStrategies) {
    const outputSheetName = `${strategyName} Options`;
    const outputSheet = ss.getSheetByName(outputSheetName);

    if (!outputSheet || outputSheet.getLastRow() < 2) {
      continue;
    }

    try {
      const fixed = EW_fixSheetArrays(outputSheet, strategyName);
      totalFixed += fixed;
      EW_trace('OPTIONS_ARRAY_FIX', `Fixed ${fixed} rows in ${strategyName}`, false);
    } catch (error) {
      const errorMsg = `${strategyName}: ${error.message}`;
      errors.push(errorMsg);
      EW_trace('OPTIONS_ARRAY_FIX', errorMsg, true);
    }
  }

  SpreadsheetApp.flush();

  const msg = `Fixed arrays for ${totalFixed} positions across ${optionStrategies.length} strategies.` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');

  EW_trace('OPTIONS_ARRAY_FIX', msg, true);
  if (EW_isSpreadsheetEnvironment()) {
    EW_safeAlert('Array Fix Complete', msg);
  }

  return msg;
}

/**
 * Fix arrays for a single sheet
 */
function EW_fixSheetArrays(sheet, strategyName) {
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);

  // Validate required columns
  if (!hdrMap.ohlcVolumeCol || !hdrMap.bidHitPctCol || !hdrMap.bidCol) {
    EW_trace('OPTIONS_ARRAY_FIX', `${strategyName}: Missing required columns`, true);
    return 0;
  }

  const lastRow = sheet.getLastRow();
  const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();

  let fixedCount = 0;

  for (let i = 0; i < data.length; i++) {
    const rowNum = i + 2;
    const row = data[i];

    // Get entry price from Bid column
    const entryPrice = hdrMap.bidCol ? parseFloat(row[hdrMap.bidCol - 1]) : null;
    if (!entryPrice) continue;

    // Get OHLC_Volume array
    const ohlcVolumeJson = row[hdrMap.ohlcVolumeCol - 1];
    if (!ohlcVolumeJson) continue;

    let ohlcVolumeArray;
    try {
      ohlcVolumeArray = JSON.parse(ohlcVolumeJson);
    } catch (error) {
      continue;
    }

    const entryCost = entryPrice * 100;
    const MAX_TRACKING_DAYS = 14;
    const bidHitPctArray = Array(MAX_TRACKING_DAYS).fill('0.000000');
    const maxFavorableArray = Array(MAX_TRACKING_DAYS).fill('0.000000');
    const minUnfavorableArray = Array(MAX_TRACKING_DAYS).fill('0.000000');
    let firstHitDate = '';

    // Recalculate arrays using strategy-specific logic
    for (let dayIndex = 0; dayIndex < ohlcVolumeArray.length && dayIndex < MAX_TRACKING_DAYS; dayIndex++) {
      const ohlc = ohlcVolumeArray[dayIndex];
      if (!ohlc) continue;

      // Premium tracking: ALWAYS use HIGH for best profit opportunity
      // Premium increases = profit, regardless of Call/Put strategy
      const exitPrice = ohlc.h !== null ? parseFloat(ohlc.h) : null;

      if (exitPrice !== null) {
        const pnl = (exitPrice - entryPrice) * 100;
        const pnlPct = pnl / entryCost;
        bidHitPctArray[dayIndex] = pnlPct.toFixed(6);

        // Check for first profitable day
        if (firstHitDate === '' && pnlPct > 0) {
          firstHitDate = dayIndex;
        }

        // Update Day check columns (Day0_Check through Day13_Check)
        const dayCheckCol = dayIndex === 0 ? hdrMap.day0CheckCol :
                            dayIndex === 1 ? hdrMap.day1CheckCol :
                            dayIndex === 2 ? hdrMap.day2CheckCol :
                            dayIndex === 3 ? hdrMap.day3CheckCol :
                            dayIndex === 4 ? hdrMap.day4CheckCol :
                            dayIndex === 5 ? hdrMap.day5CheckCol :
                            dayIndex === 6 ? hdrMap.day6CheckCol :
                            dayIndex === 7 ? hdrMap.day7CheckCol :
                            dayIndex === 8 ? hdrMap.day8CheckCol :
                            dayIndex === 9 ? hdrMap.day9CheckCol :
                            dayIndex === 10 ? hdrMap.day10CheckCol :
                            dayIndex === 11 ? hdrMap.day11CheckCol :
                            dayIndex === 12 ? hdrMap.day12CheckCol :
                            dayIndex === 13 ? hdrMap.day13CheckCol : null;

        if (dayCheckCol) {
          sheet.getRange(rowNum, dayCheckCol).setValue(exitPrice);
        }
      }

      // Max favorable (highest premium during the day - actual value, not forced to 0)
      const high = ohlc.h !== null ? parseFloat(ohlc.h) : null;
      if (high !== null) {
        const maxPnl = (high - entryPrice) * 100;
        const maxPct = maxPnl / entryCost;
        maxFavorableArray[dayIndex] = maxPct.toFixed(6);
      }

      // Min unfavorable (lowest premium during the day - actual value, not forced to 0)
      const low = ohlc.l !== null ? parseFloat(ohlc.l) : null;
      if (low !== null) {
        const minPnl = (low - entryPrice) * 100;
        const minPct = minPnl / entryCost;
        minUnfavorableArray[dayIndex] = minPct.toFixed(6);
      }
    }

    // Update Bid_Hit_Pct array
    sheet.getRange(rowNum, hdrMap.bidHitPctCol).setValue(JSON.stringify(bidHitPctArray));

    // Update Max_Favorable array
    if (hdrMap.maxFavorableCol) {
      sheet.getRange(rowNum, hdrMap.maxFavorableCol).setValue(JSON.stringify(maxFavorableArray));
    }

    // Update Min_Unfavorable array
    if (hdrMap.minUnfavorableCol) {
      sheet.getRange(rowNum, hdrMap.minUnfavorableCol).setValue(JSON.stringify(minUnfavorableArray));
    }

    // Update First_Hit_Date (FIXED: was using hitDateCol instead of firstHitDateCol)
    if (hdrMap.firstHitDateCol) {
      sheet.getRange(rowNum, hdrMap.firstHitDateCol).setValue(firstHitDate);
    }

    fixedCount++;
  }

  return fixedCount;
}
