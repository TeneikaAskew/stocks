/**
 * Options Historical Backfill
 * Calculate daily P/L for options positions based on historical stock prices
 *
 * For call options: Intrinsic Value = max(0, stock_price - strike) * 100
 * For put options: Intrinsic Value = max(0, strike - stock_price) * 100
 *
 * Daily P/L = Current Intrinsic Value - Previous Day Intrinsic Value
 *
 * This script:
 * 1. Reads ticker, strike, expDate, and optionType from sheet
 * 2. Fetches historical stock prices from Yahoo Finance
 * 3. Calculates daily intrinsic value and P/L
 * 4. Updates sheet with daily P/L columns
 *
 * Usage:
 * - Run EW_backfillOptionsHistorical() to process all incomplete positions
 * - Run EW_backfillOptionsSelected() to process selected rows only
 *
 * Note: This calculates intrinsic value P/L, not actual options premium P/L,
 * since historical options premiums are not readily available from free APIs.
 */

/**
 * Main function to backfill options historical P/L data for Long Calls sheet
 * Processes incomplete positions with continuation support
 */
function EW_backfillOptionsHistorical() {
  const MAX_RUNTIME_MS = 25 * 60 * 1000; // 25 minutes
  const startTime = new Date();

  EW_trace('OPTIONS_BACKFILL', 'Starting options historical backfill', true);

  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getSheetByName('Long Calls');

  if (!sheet) {
    EW_trace('OPTIONS_BACKFILL', 'Long Calls sheet not found', true);
    return;
  }

  // Check for saved state from previous run
  const savedState = EW_getBackfillState('OPTIONS_BACKFILL_STATE');
  let startRowIndex = savedState ? savedState.currentRowIndex : 0;
  let totalProcessed = savedState ? savedState.totalProcessed : 0;
  let errors = savedState ? savedState.errors : [];

  if (savedState) {
    EW_trace('OPTIONS_BACKFILL', `Resuming from row ${startRowIndex + 2}. Already processed: ${totalProcessed}`, true);
  }

  const result = EW_processOptionsBackfill(sheet, startRowIndex, startTime, MAX_RUNTIME_MS);

  totalProcessed += result.processed;
  errors = errors.concat(result.errors);

  // Check if continuation is needed
  if (result.needsContinuation) {
    EW_trace('OPTIONS_BACKFILL', `Time limit reached. Saving state at row ${result.nextRowIndex + 2}...`, true);

    const state = {
      currentRowIndex: result.nextRowIndex,
      totalProcessed: totalProcessed,
      errors: errors,
      timestamp: new Date().toISOString(),
      continuationCount: (savedState?.continuationCount || 0) + 1
    };
    EW_saveBackfillState(state, 'OPTIONS_BACKFILL_STATE');

    // Schedule continuation
    EW_scheduleBackfillContinuation('EW_backfillOptionsHistorical');
    return;
  }

  // Clear state when complete
  EW_clearBackfillState('OPTIONS_BACKFILL_STATE');

  const msg = `Options backfill complete. Processed ${totalProcessed} positions.` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');

  EW_trace('OPTIONS_BACKFILL', msg, true);
  if (EW_isSpreadsheetEnvironment()) {
    EW_safeAlert('Options Backfill Complete', msg);
  }
}

/**
 * Process options backfill for a sheet
 * @param {Sheet} sheet - The sheet to process
 * @param {number} startRowIndex - Row index to start from (0-based, excluding header)
 * @param {Date} startTime - Function start time
 * @param {number} maxRuntimeMs - Maximum runtime in milliseconds
 * @returns {Object} Result with processed count and continuation info
 */
function EW_processOptionsBackfill(sheet, startRowIndex, startTime, maxRuntimeMs) {
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_buildOptionsHeaderMap(headers);

  // Validate required columns
  const requiredCols = ['ticker', 'strike', 'expDate', 'runDate'];
  for (const col of requiredCols) {
    if (!hdrMap[col]) {
      EW_trace('OPTIONS_BACKFILL', `Missing required column: ${col}`, true);
      return { processed: 0, errors: [`Missing column: ${col}`], needsContinuation: false };
    }
  }

  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    EW_trace('OPTIONS_BACKFILL', 'No data rows to process', true);
    return { processed: 0, errors: [], needsContinuation: false };
  }

  const dataRange = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
  const data = dataRange.getValues();

  let processed = 0;
  let errors = [];

  for (let i = startRowIndex; i < data.length; i++) {
    // Check time limit
    const elapsedMs = new Date() - startTime;
    if (elapsedMs > maxRuntimeMs) {
      EW_trace('OPTIONS_BACKFILL', `Time limit reached after ${Math.round(elapsedMs / 1000)}s`, true);
      return {
        processed: processed,
        errors: errors,
        needsContinuation: true,
        nextRowIndex: i
      };
    }

    const row = data[i];
    const rowNum = i + 2; // +2 because: +1 for 0-based index, +1 for header

    try {
      // Skip if already has P/L data
      if (EW_hasOptionsPnLData(row, hdrMap)) {
        continue;
      }

      // Extract position data
      const ticker = row[hdrMap.ticker - 1];
      const strike = parseFloat(row[hdrMap.strike - 1]);
      const expDate = new Date(row[hdrMap.expDate - 1]);
      const runDate = new Date(row[hdrMap.runDate - 1]);
      const optionType = 'C'; // Long Calls sheet, so always calls

      // Validate data
      if (!ticker || isNaN(strike) || !expDate || !runDate) {
        EW_trace('OPTIONS_BACKFILL', `Row ${rowNum}: Missing or invalid data - ticker:${ticker}, strike:${strike}`, false);
        continue;
      }

      // Skip future positions
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      if (runDate > today) {
        continue;
      }

      // Log progress
      if (processed % 10 === 0 && processed > 0) {
        EW_trace('OPTIONS_BACKFILL', `Processed ${processed} positions...`, false);
      }

      // Calculate P/L
      const pnlData = EW_calculateOptionsPnL(ticker, strike, optionType, runDate, expDate);

      if (pnlData && pnlData.dailyPnL && pnlData.dailyPnL.length > 0) {
        // Update sheet with P/L data
        EW_updateOptionsPnLColumns(sheet, rowNum, pnlData, hdrMap);
        processed++;
        EW_trace('OPTIONS_BACKFILL', `Row ${rowNum}: ${ticker} $${strike} - Updated ${pnlData.dailyPnL.length} days`, false);
      }

    } catch (error) {
      const errorMsg = `Row ${rowNum}: ${error.message}`;
      errors.push(errorMsg);
      EW_trace('OPTIONS_BACKFILL', `Error: ${errorMsg}`, true);
    }
  }

  if (processed > 0) {
    SpreadsheetApp.flush();
  }

  return {
    processed: processed,
    errors: errors,
    needsContinuation: false
  };
}

/**
 * Backfill selected rows only
 * Use this when you want to update specific positions
 */
function EW_backfillOptionsSelected() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();
  const selection = sheet.getActiveRange();

  if (!sheet.getName().includes('Long Calls')) {
    SpreadsheetApp.getUi().alert('Please select rows in the Long Calls sheet');
    return;
  }

  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_buildOptionsHeaderMap(headers);

  const startRow = selection.getRow();
  const numRows = selection.getNumRows();

  if (startRow === 1) {
    SpreadsheetApp.getUi().alert('Please select data rows (not the header)');
    return;
  }

  const data = sheet.getRange(startRow, 1, numRows, sheet.getLastColumn()).getValues();
  let processed = 0;
  let errors = [];

  for (let i = 0; i < data.length; i++) {
    const row = data[i];
    const rowNum = startRow + i;

    try {
      const ticker = row[hdrMap.ticker - 1];
      const strike = parseFloat(row[hdrMap.strike - 1]);
      const expDate = new Date(row[hdrMap.expDate - 1]);
      const runDate = new Date(row[hdrMap.runDate - 1]);
      const optionType = 'C';

      if (!ticker || isNaN(strike) || !expDate || !runDate) {
        continue;
      }

      const pnlData = EW_calculateOptionsPnL(ticker, strike, optionType, runDate, expDate);

      if (pnlData && pnlData.dailyPnL && pnlData.dailyPnL.length > 0) {
        EW_updateOptionsPnLColumns(sheet, rowNum, pnlData, hdrMap);
        processed++;
      }

    } catch (error) {
      errors.push(`Row ${rowNum}: ${error.message}`);
    }
  }

  SpreadsheetApp.flush();

  const msg = `Processed ${processed} of ${numRows} selected rows` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.slice(0, 5).join('\n')}` : '');

  SpreadsheetApp.getUi().alert('Backfill Complete', msg, SpreadsheetApp.getUi().ButtonSet.OK);
}

/**
 * Calculate daily P/L for an option position
 * @param {string} ticker - Stock ticker
 * @param {number} strike - Strike price
 * @param {string} optionType - 'C' for calls, 'P' for puts
 * @param {Date} runDate - Position entry date
 * @param {Date} expDate - Option expiration date
 * @returns {Object} P/L data with daily values
 */
function EW_calculateOptionsPnL(ticker, strike, optionType, runDate, expDate) {
  // Determine end date (expiration or today, whichever is earlier)
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const endDate = expDate < today ? expDate : today;

  // Fetch historical stock prices
  const historicalData = EW_getYahooHistoricalRangeWithInterval(
    ticker,
    runDate,
    endDate,
    '1d',  // Daily interval
    false  // Don't need raw data
  );

  if (!historicalData || !historicalData.data || historicalData.data.length === 0) {
    EW_trace('OPTIONS_BACKFILL', `${ticker}: No historical data available for ${EW_formatDate(runDate)} to ${EW_formatDate(endDate)}`, false);
    return null;
  }

  const priceData = historicalData.data;
  const dailyPnL = [];
  let previousIntrinsicValue = 0;
  let entryIntrinsicValue = 0;
  let cumulativePnL = 0;

  // Calculate daily intrinsic value and P/L
  for (let i = 0; i < priceData.length; i++) {
    const dayData = priceData[i];
    const stockPrice = dayData.close;

    // Calculate intrinsic value
    let intrinsicValue = 0;
    if (optionType === 'C') {
      // Call option: max(0, stock_price - strike)
      intrinsicValue = Math.max(0, stockPrice - strike) * 100; // * 100 for per contract
    } else if (optionType === 'P') {
      // Put option: max(0, strike - stock_price)
      intrinsicValue = Math.max(0, strike - stockPrice) * 100;
    }

    // First day establishes baseline
    if (i === 0) {
      entryIntrinsicValue = intrinsicValue;
      previousIntrinsicValue = intrinsicValue;
      dailyPnL.push({
        date: dayData.date,
        stockPrice: stockPrice,
        intrinsicValue: intrinsicValue,
        dailyPnL: 0, // No P/L on first day
        cumulativePnL: 0,
        percentChange: 0
      });
      continue;
    }

    // Calculate daily P/L (change from previous day)
    const dayPnL = intrinsicValue - previousIntrinsicValue;
    cumulativePnL += dayPnL;

    // Calculate percent change from entry
    const percentChange = entryIntrinsicValue > 0 ?
      ((intrinsicValue - entryIntrinsicValue) / entryIntrinsicValue) * 100 : 0;

    dailyPnL.push({
      date: dayData.date,
      stockPrice: stockPrice,
      intrinsicValue: intrinsicValue,
      dailyPnL: dayPnL,
      cumulativePnL: cumulativePnL,
      percentChange: percentChange
    });

    previousIntrinsicValue = intrinsicValue;
  }

  // Calculate summary statistics
  const maxPnL = Math.max(...dailyPnL.map(d => d.cumulativePnL));
  const minPnL = Math.min(...dailyPnL.map(d => d.cumulativePnL));
  const finalPnL = dailyPnL[dailyPnL.length - 1].cumulativePnL;
  const maxPercentGain = Math.max(...dailyPnL.map(d => d.percentChange));
  const maxPercentLoss = Math.min(...dailyPnL.map(d => d.percentChange));

  return {
    ticker: ticker,
    strike: strike,
    optionType: optionType,
    entryDate: runDate,
    entryIntrinsicValue: entryIntrinsicValue,
    dailyPnL: dailyPnL,
    summary: {
      maxPnL: maxPnL,
      minPnL: minPnL,
      finalPnL: finalPnL,
      maxPercentGain: maxPercentGain,
      maxPercentLoss: maxPercentLoss,
      totalDays: dailyPnL.length
    }
  };
}

/**
 * Build header map for options sheet
 * @param {Array} headers - Array of header values
 * @returns {Object} Map of column names to indices (1-based)
 */
function EW_buildOptionsHeaderMap(headers) {
  const map = {};

  for (let i = 0; i < headers.length; i++) {
    const header = String(headers[i]).toLowerCase().trim();

    // Standard columns
    if (header === 'ticker') map.ticker = i + 1;
    if (header === 'strike') map.strike = i + 1;
    if (header === 'expdate' || header === 'exp date' || header === 'expiration') map.expDate = i + 1;
    if (header === 'rundate' || header === 'run date' || header === 'entry date') map.runDate = i + 1;
    if (header === 'optiontype' || header === 'option type' || header === 'type') map.optionType = i + 1;

    // P/L columns
    if (header === 'entry_intrinsic' || header === 'entry intrinsic value') map.entryIntrinsic = i + 1;
    if (header === 'current_intrinsic' || header === 'current intrinsic value') map.currentIntrinsic = i + 1;
    if (header === 'daily_pnl_array' || header === 'daily p&l') map.dailyPnLArray = i + 1;
    if (header === 'cumulative_pnl' || header === 'total p&l') map.cumulativePnL = i + 1;
    if (header === 'max_pnl' || header === 'max profit') map.maxPnL = i + 1;
    if (header === 'min_pnl' || header === 'max loss') map.minPnL = i + 1;
    if (header === 'percent_return' || header === '% return') map.percentReturn = i + 1;
  }

  return map;
}

/**
 * Check if row already has P/L data
 * @param {Array} row - Row data
 * @param {Object} hdrMap - Header map
 * @returns {boolean} True if row has P/L data
 */
function EW_hasOptionsPnLData(row, hdrMap) {
  // Check if any P/L column has data
  if (hdrMap.cumulativePnL && row[hdrMap.cumulativePnL - 1]) {
    return true;
  }
  if (hdrMap.dailyPnLArray && row[hdrMap.dailyPnLArray - 1]) {
    return true;
  }
  return false;
}

/**
 * Update sheet with P/L data
 * @param {Sheet} sheet - The sheet to update
 * @param {number} rowNum - Row number (1-based)
 * @param {Object} pnlData - P/L data object
 * @param {Object} hdrMap - Header map
 */
function EW_updateOptionsPnLColumns(sheet, rowNum, pnlData, hdrMap) {
  const updates = [];

  // Entry intrinsic value
  if (hdrMap.entryIntrinsic) {
    updates.push({
      range: sheet.getRange(rowNum, hdrMap.entryIntrinsic),
      value: pnlData.entryIntrinsicValue.toFixed(2)
    });
  }

  // Current intrinsic value (last day)
  if (hdrMap.currentIntrinsic && pnlData.dailyPnL.length > 0) {
    const currentValue = pnlData.dailyPnL[pnlData.dailyPnL.length - 1].intrinsicValue;
    updates.push({
      range: sheet.getRange(rowNum, hdrMap.currentIntrinsic),
      value: currentValue.toFixed(2)
    });
  }

  // Cumulative P/L (final)
  if (hdrMap.cumulativePnL) {
    updates.push({
      range: sheet.getRange(rowNum, hdrMap.cumulativePnL),
      value: pnlData.summary.finalPnL.toFixed(2)
    });
  }

  // Max P/L
  if (hdrMap.maxPnL) {
    updates.push({
      range: sheet.getRange(rowNum, hdrMap.maxPnL),
      value: pnlData.summary.maxPnL.toFixed(2)
    });
  }

  // Min P/L
  if (hdrMap.minPnL) {
    updates.push({
      range: sheet.getRange(rowNum, hdrMap.minPnL),
      value: pnlData.summary.minPnL.toFixed(2)
    });
  }

  // Percent return
  if (hdrMap.percentReturn && pnlData.entryIntrinsicValue > 0) {
    const percentReturn = ((pnlData.summary.finalPnL) / pnlData.entryIntrinsicValue) * 100;
    updates.push({
      range: sheet.getRange(rowNum, hdrMap.percentReturn),
      value: percentReturn.toFixed(2)
    });
  }

  // Daily P/L array (as JSON string)
  if (hdrMap.dailyPnLArray) {
    const pnlArray = pnlData.dailyPnL.map(d => ({
      date: EW_formatDate(d.date),
      price: d.stockPrice.toFixed(2),
      intrinsic: d.intrinsicValue.toFixed(2),
      dailyPnL: d.dailyPnL.toFixed(2),
      cumPnL: d.cumulativePnL.toFixed(2),
      pctChange: d.percentChange.toFixed(2)
    }));

    updates.push({
      range: sheet.getRange(rowNum, hdrMap.dailyPnLArray),
      value: JSON.stringify(pnlArray)
    });
  }

  // Apply all updates
  for (const update of updates) {
    update.range.setValue(update.value);
  }
}

/**
 * Add P/L tracking columns to Long Calls sheet
 * Run this once to set up the necessary columns
 */
function EW_addOptionsPnLColumns() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getSheetByName('Long Calls');

  if (!sheet) {
    SpreadsheetApp.getUi().alert('Long Calls sheet not found');
    return;
  }

  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const lastCol = sheet.getLastColumn();

  // Define new columns to add
  const newColumns = [
    'Entry_Intrinsic',
    'Current_Intrinsic',
    'Cumulative_PnL',
    'Max_PnL',
    'Min_PnL',
    'Percent_Return',
    'Daily_PnL_Array'
  ];

  // Check which columns already exist
  const existingHeaders = headers.map(h => String(h).toLowerCase().replace(/[_\s]/g, ''));
  const columnsToAdd = newColumns.filter(col =>
    !existingHeaders.includes(col.toLowerCase().replace(/[_\s]/g, ''))
  );

  if (columnsToAdd.length === 0) {
    SpreadsheetApp.getUi().alert('All P/L columns already exist');
    return;
  }

  // Insert new columns
  sheet.insertColumnsAfter(lastCol, columnsToAdd.length);

  const headerRange = sheet.getRange(1, lastCol + 1, 1, columnsToAdd.length);
  headerRange.setValues([columnsToAdd]);
  headerRange.setFontWeight('bold');
  headerRange.setBackground('#E8E8E8');

  SpreadsheetApp.getUi().alert(
    'Columns Added',
    `Added ${columnsToAdd.length} new P/L tracking columns:\n${columnsToAdd.join(', ')}`,
    SpreadsheetApp.getUi().ButtonSet.OK
  );
}

/**
 * Test function - run on a single position to verify calculation
 */
function EW_testOptionsBackfill() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();

  if (!sheet.getName().includes('Long Calls')) {
    SpreadsheetApp.getUi().alert('Please select a row in the Long Calls sheet');
    return;
  }

  const selection = sheet.getActiveRange();
  const row = selection.getRow();

  if (row === 1) {
    SpreadsheetApp.getUi().alert('Please select a data row (not the header)');
    return;
  }

  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_buildOptionsHeaderMap(headers);
  const data = sheet.getRange(row, 1, 1, sheet.getLastColumn()).getValues()[0];

  const ticker = data[hdrMap.ticker - 1];
  const strike = parseFloat(data[hdrMap.strike - 1]);
  const expDate = new Date(data[hdrMap.expDate - 1]);
  const runDate = new Date(data[hdrMap.runDate - 1]);
  const optionType = 'C';

  Logger.log(`Testing: ${ticker} $${strike} Call`);
  Logger.log(`Entry: ${runDate}, Expiration: ${expDate}`);

  const pnlData = EW_calculateOptionsPnL(ticker, strike, optionType, runDate, expDate);

  if (!pnlData) {
    SpreadsheetApp.getUi().alert('No data returned - check logs');
    return;
  }

  Logger.log(`Entry Intrinsic: $${pnlData.entryIntrinsicValue.toFixed(2)}`);
  Logger.log(`Final P/L: $${pnlData.summary.finalPnL.toFixed(2)}`);
  Logger.log(`Max P/L: $${pnlData.summary.maxPnL.toFixed(2)}`);
  Logger.log(`Min P/L: $${pnlData.summary.minPnL.toFixed(2)}`);
  Logger.log(`Days tracked: ${pnlData.summary.totalDays}`);

  // Show first few days
  Logger.log('\nFirst 5 days:');
  for (let i = 0; i < Math.min(5, pnlData.dailyPnL.length); i++) {
    const day = pnlData.dailyPnL[i];
    Logger.log(`${EW_formatDate(day.date)}: Stock $${day.stockPrice.toFixed(2)}, ` +
      `Intrinsic $${day.intrinsicValue.toFixed(2)}, ` +
      `Daily P/L $${day.dailyPnL.toFixed(2)}, ` +
      `Cum P/L $${day.cumulativePnL.toFixed(2)}`);
  }

  const msg = `${ticker} $${strike} Call\n\n` +
    `Entry Intrinsic: $${pnlData.entryIntrinsicValue.toFixed(2)}\n` +
    `Final P/L: $${pnlData.summary.finalPnL.toFixed(2)}\n` +
    `Max P/L: $${pnlData.summary.maxPnL.toFixed(2)}\n` +
    `Min P/L: $${pnlData.summary.minPnL.toFixed(2)}\n` +
    `Days tracked: ${pnlData.summary.totalDays}\n\n` +
    `Check execution log for detailed daily breakdown.`;

  SpreadsheetApp.getUi().alert('Test Complete', msg, SpreadsheetApp.getUi().ButtonSet.OK);
}
