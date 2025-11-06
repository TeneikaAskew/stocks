/**
 * Options Intraday Tracking
 * Fetch today's 1-minute stock data and calculate real-time options P/L
 *
 * For each position in "Long Calls" sheet:
 * 1. Fetch today's 1-minute stock price data from Yahoo Finance
 * 2. Calculate intrinsic value at each minute: max(0, stock_price - strike) * 100
 * 3. Calculate P/L from market open to current time
 * 4. Write detailed 1-minute data to "Long Calls Options" sheet
 *
 * Usage:
 * - Run EW_updateOptionsIntraday() to capture current intraday data
 * - Schedule this to run throughout the day (e.g., every 30 minutes)
 * - View minute-by-minute P/L in the "{Strategy} Options" sheet
 */

/**
 * Main function to update intraday options tracking
 * Reads positions from "Long Calls" sheet and writes 1-minute data to "Long Calls Options"
 */
function EW_updateOptionsIntraday() {
  const startTime = new Date();
  EW_trace('OPTIONS_INTRADAY', 'Starting intraday options update', true);

  const ss = SpreadsheetApp.getActive();
  const sourceSheet = ss.getSheetByName('Long Calls');

  if (!sourceSheet) {
    EW_trace('OPTIONS_INTRADAY', 'Long Calls sheet not found', true);
    return;
  }

  // Get or create output sheet
  const outputSheetName = 'Long Calls Options';
  let outputSheet = ss.getSheetByName(outputSheetName);

  if (!outputSheet) {
    outputSheet = ss.insertSheet(outputSheetName);
    EW_setupOptionsIntradaySheet(outputSheet);
  }

  // Read positions from source sheet
  const positions = EW_readOptionsPositions(sourceSheet);

  if (positions.length === 0) {
    EW_trace('OPTIONS_INTRADAY', 'No positions to process', true);
    return;
  }

  EW_trace('OPTIONS_INTRADAY', `Processing ${positions.length} positions`, true);

  let totalBarsWritten = 0;
  let errors = [];

  // Clear previous data from today
  EW_clearTodayIntradayData(outputSheet);

  // Process each position
  for (let i = 0; i < positions.length; i++) {
    const position = positions[i];

    try {
      EW_trace('OPTIONS_INTRADAY', `Processing ${i + 1}/${positions.length}: ${position.ticker} $${position.strike}`, false);

      const intradayData = EW_fetchOptionsIntradayData(position);

      if (intradayData && intradayData.bars.length > 0) {
        EW_writeIntradayBars(outputSheet, position, intradayData);
        totalBarsWritten += intradayData.bars.length;
        EW_trace('OPTIONS_INTRADAY', `  ✓ ${position.ticker}: Wrote ${intradayData.bars.length} 1-minute bars`, false);
      } else {
        EW_trace('OPTIONS_INTRADAY', `  ⚠ ${position.ticker}: No intraday data available`, false);
      }

    } catch (error) {
      const errorMsg = `${position.ticker}: ${error.message}`;
      errors.push(errorMsg);
      EW_trace('OPTIONS_INTRADAY', `  ✗ Error: ${errorMsg}`, true);
    }
  }

  // Sort output sheet by timestamp descending (most recent first)
  if (totalBarsWritten > 0) {
    const lastRow = outputSheet.getLastRow();
    if (lastRow > 1) {
      const dataRange = outputSheet.getRange(2, 1, lastRow - 1, outputSheet.getLastColumn());
      dataRange.sort({column: 4, ascending: false}); // Sort by timestamp column
    }
    SpreadsheetApp.flush();
  }

  const elapsed = Math.round((new Date() - startTime) / 1000);
  const msg = `Intraday update complete in ${elapsed}s. Wrote ${totalBarsWritten} 1-minute bars for ${positions.length} positions.` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.slice(0, 5).join('\n')}` : '');

  EW_trace('OPTIONS_INTRADAY', msg, true);

  if (EW_isSpreadsheetEnvironment()) {
    SpreadsheetApp.getUi().alert('Intraday Update Complete', msg, SpreadsheetApp.getUi().ButtonSet.OK);
  }
}

/**
 * Setup the output sheet with proper headers
 * @param {Sheet} sheet - The output sheet to setup
 */
function EW_setupOptionsIntradaySheet(sheet) {
  const headers = [
    'Ticker',
    'Strike',
    'ExpDate',
    'Timestamp',
    'Time',
    'Stock_Price',
    'Intrinsic_Value',
    'PnL_From_Open',
    'Cumulative_PnL',
    'Percent_Change',
    'Volume',
    'Session'
  ];

  const headerRange = sheet.getRange(1, 1, 1, headers.length);
  headerRange.setValues([headers]);
  headerRange.setFontWeight('bold');
  headerRange.setBackground('#4A86E8');
  headerRange.setFontColor('white');

  // Set column widths
  sheet.setColumnWidth(1, 80);  // Ticker
  sheet.setColumnWidth(2, 70);  // Strike
  sheet.setColumnWidth(3, 100); // ExpDate
  sheet.setColumnWidth(4, 180); // Timestamp
  sheet.setColumnWidth(5, 80);  // Time
  sheet.setColumnWidth(6, 100); // Stock_Price
  sheet.setColumnWidth(7, 120); // Intrinsic_Value
  sheet.setColumnWidth(8, 110); // PnL_From_Open
  sheet.setColumnWidth(9, 120); // Cumulative_PnL
  sheet.setColumnWidth(10, 120); // Percent_Change
  sheet.setColumnWidth(11, 90);  // Volume
  sheet.setColumnWidth(12, 120); // Session

  // Freeze header row
  sheet.setFrozenRows(1);
}

/**
 * Read positions from source sheet
 * @param {Sheet} sheet - The source sheet (Long Calls)
 * @returns {Array} Array of position objects
 */
function EW_readOptionsPositions(sheet) {
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
    if (header === 'rundate' || header === 'entrydate') hdrMap.runDate = i;
  }

  // Validate required columns
  if (hdrMap.ticker === undefined || hdrMap.strike === undefined || hdrMap.expDate === undefined) {
    EW_trace('OPTIONS_INTRADAY', 'Missing required columns (ticker, strike, expDate)', true);
    return [];
  }

  const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  const positions = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  for (let i = 0; i < data.length; i++) {
    const row = data[i];

    const ticker = row[hdrMap.ticker];
    const strike = parseFloat(row[hdrMap.strike]);
    const expDate = new Date(row[hdrMap.expDate]);

    // Skip if missing data or expired
    if (!ticker || isNaN(strike) || !expDate) continue;
    if (expDate < today) continue; // Skip expired positions

    positions.push({
      ticker: ticker,
      strike: strike,
      expDate: expDate,
      optionType: 'C', // Long Calls sheet = Calls
      rowNum: i + 2
    });
  }

  return positions;
}

/**
 * Fetch today's 1-minute intraday data for a position
 * @param {Object} position - Position object with ticker, strike, optionType
 * @returns {Object} Intraday data with 1-minute bars
 */
function EW_fetchOptionsIntradayData(position) {
  const today = new Date();
  const startDate = new Date(today);
  const endDate = new Date(today);

  // Set to market hours (9:30 AM - 4:00 PM ET)
  startDate.setHours(9, 30, 0, 0);
  endDate.setHours(16, 0, 0, 0);

  // If before market open, don't fetch
  if (today < startDate) {
    EW_trace('OPTIONS_INTRADAY', `${position.ticker}: Market not yet open`, false);
    return null;
  }

  // Fetch 1-minute data for today using existing Yahoo function
  const historicalData = EW_getYahooHistoricalRange(
    position.ticker,
    startDate,
    endDate,
    false // Don't need raw data
  );

  if (!historicalData || historicalData.length === 0) {
    return null;
  }

  // Calculate intrinsic value and P/L for each 1-minute bar
  const bars = [];
  let openIntrinsicValue = null;

  for (let i = 0; i < historicalData.length; i++) {
    const bar = historicalData[i];
    const stockPrice = bar.close;

    // Calculate intrinsic value
    let intrinsicValue = 0;
    if (position.optionType === 'C') {
      intrinsicValue = Math.max(0, stockPrice - position.strike) * 100;
    } else if (position.optionType === 'P') {
      intrinsicValue = Math.max(0, position.strike - stockPrice) * 100;
    }

    // First bar establishes baseline
    if (openIntrinsicValue === null) {
      openIntrinsicValue = intrinsicValue;
    }

    // Calculate P/L from open
    const pnlFromOpen = intrinsicValue - openIntrinsicValue;
    const percentChange = openIntrinsicValue > 0 ?
      (pnlFromOpen / openIntrinsicValue) * 100 : 0;

    // Determine market session
    const barTime = bar.date;
    const hours = barTime.getHours();
    const minutes = barTime.getMinutes();
    let session = 'REGULAR';

    if (hours < 9 || (hours === 9 && minutes < 30)) {
      session = 'PRE_MARKET';
    } else if (hours < 10) {
      session = 'OPEN';
    } else if (hours < 12) {
      session = 'MORNING';
    } else if (hours < 14) {
      session = 'MIDDAY';
    } else if (hours < 15 || (hours === 15 && minutes < 30)) {
      session = 'AFTERNOON';
    } else if (hours < 16) {
      session = 'POWER_HOUR';
    } else {
      session = 'AFTER_HOURS';
    }

    bars.push({
      timestamp: bar.date,
      stockPrice: stockPrice,
      intrinsicValue: intrinsicValue,
      pnlFromOpen: pnlFromOpen,
      percentChange: percentChange,
      volume: bar.volume || 0,
      session: session
    });
  }

  return {
    ticker: position.ticker,
    strike: position.strike,
    expDate: position.expDate,
    openIntrinsicValue: openIntrinsicValue,
    bars: bars,
    totalBars: bars.length
  };
}

/**
 * Write intraday bars to output sheet
 * @param {Sheet} sheet - Output sheet
 * @param {Object} position - Position info
 * @param {Object} intradayData - Intraday data with bars
 */
function EW_writeIntradayBars(sheet, position, intradayData) {
  if (!intradayData.bars || intradayData.bars.length === 0) return;

  const rows = [];
  let cumulativePnL = 0;

  for (const bar of intradayData.bars) {
    cumulativePnL = bar.pnlFromOpen; // Same as pnlFromOpen for intraday tracking

    const timeStr = Utilities.formatDate(bar.timestamp, Session.getScriptTimeZone(), 'HH:mm:ss');

    rows.push([
      position.ticker,
      position.strike,
      Utilities.formatDate(position.expDate, Session.getScriptTimeZone(), 'yyyy-MM-dd'),
      bar.timestamp,
      timeStr,
      bar.stockPrice.toFixed(2),
      bar.intrinsicValue.toFixed(2),
      bar.pnlFromOpen.toFixed(2),
      cumulativePnL.toFixed(2),
      bar.percentChange.toFixed(2),
      bar.volume,
      bar.session
    ]);
  }

  // Append rows to sheet
  const lastRow = sheet.getLastRow();
  const outputRange = sheet.getRange(lastRow + 1, 1, rows.length, rows[0].length);
  outputRange.setValues(rows);

  // Format numbers
  const priceCol = 6;
  const intrinsicCol = 7;
  const pnlCol = 8;
  const cumPnlCol = 9;
  const pctCol = 10;

  sheet.getRange(lastRow + 1, priceCol, rows.length, 1).setNumberFormat('$#,##0.00');
  sheet.getRange(lastRow + 1, intrinsicCol, rows.length, 1).setNumberFormat('$#,##0.00');
  sheet.getRange(lastRow + 1, pnlCol, rows.length, 1).setNumberFormat('$#,##0.00');
  sheet.getRange(lastRow + 1, cumPnlCol, rows.length, 1).setNumberFormat('$#,##0.00');
  sheet.getRange(lastRow + 1, pctCol, rows.length, 1).setNumberFormat('0.00%');

  // Conditional formatting for P/L columns
  for (let i = 0; i < rows.length; i++) {
    const rowNum = lastRow + 1 + i;
    const pnl = parseFloat(rows[i][pnlCol - 1]);

    if (pnl > 0) {
      sheet.getRange(rowNum, pnlCol, 1, 2).setBackground('#D9EAD3'); // Light green
    } else if (pnl < 0) {
      sheet.getRange(rowNum, pnlCol, 1, 2).setBackground('#F4CCCC'); // Light red
    }
  }
}

/**
 * Clear today's data from the output sheet before updating
 * @param {Sheet} sheet - Output sheet
 */
function EW_clearTodayIntradayData(sheet) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);

  // Get all timestamps (column 4)
  const timestampRange = sheet.getRange(2, 4, lastRow - 1, 1);
  const timestamps = timestampRange.getValues();

  // Find rows to delete (today's data)
  const rowsToDelete = [];
  for (let i = 0; i < timestamps.length; i++) {
    const timestamp = new Date(timestamps[i][0]);
    if (timestamp >= today && timestamp < tomorrow) {
      rowsToDelete.push(i + 2); // +2 for header and 0-based index
    }
  }

  // Delete in reverse order to maintain row numbers
  for (let i = rowsToDelete.length - 1; i >= 0; i--) {
    sheet.deleteRow(rowsToDelete[i]);
  }

  if (rowsToDelete.length > 0) {
    EW_trace('OPTIONS_INTRADAY', `Cleared ${rowsToDelete.length} existing rows from today`, false);
  }
}

/**
 * Run intraday update for selected positions only
 * Select rows in "Long Calls" sheet before running
 */
function EW_updateOptionsIntradaySelected() {
  const ss = SpreadsheetApp.getActive();
  const sourceSheet = ss.getActiveSheet();
  const selection = sourceSheet.getActiveRange();

  if (sourceSheet.getName() !== 'Long Calls') {
    SpreadsheetApp.getUi().alert('Please select rows in the Long Calls sheet');
    return;
  }

  const startRow = selection.getRow();
  const numRows = selection.getNumRows();

  if (startRow === 1) {
    SpreadsheetApp.getUi().alert('Please select data rows (not the header)');
    return;
  }

  // Get output sheet
  const outputSheetName = 'Long Calls Options';
  let outputSheet = ss.getSheetByName(outputSheetName);

  if (!outputSheet) {
    outputSheet = ss.insertSheet(outputSheetName);
    EW_setupOptionsIntradaySheet(outputSheet);
  }

  // Read headers
  const headers = sourceSheet.getRange(1, 1, 1, sourceSheet.getLastColumn()).getValues()[0];
  const hdrMap = {};

  for (let i = 0; i < headers.length; i++) {
    const header = String(headers[i]).toLowerCase().trim().replace(/\s+/g, '');
    if (header === 'ticker') hdrMap.ticker = i;
    if (header === 'strike') hdrMap.strike = i;
    if (header === 'expdate' || header === 'expiration') hdrMap.expDate = i;
  }

  // Read selected rows
  const data = sourceSheet.getRange(startRow, 1, numRows, sourceSheet.getLastColumn()).getValues();

  let totalBars = 0;
  let processed = 0;

  for (let i = 0; i < data.length; i++) {
    const row = data[i];

    const ticker = row[hdrMap.ticker];
    const strike = parseFloat(row[hdrMap.strike]);
    const expDate = new Date(row[hdrMap.expDate]);

    if (!ticker || isNaN(strike) || !expDate) continue;

    const position = {
      ticker: ticker,
      strike: strike,
      expDate: expDate,
      optionType: 'C'
    };

    try {
      const intradayData = EW_fetchOptionsIntradayData(position);

      if (intradayData && intradayData.bars.length > 0) {
        EW_writeIntradayBars(outputSheet, position, intradayData);
        totalBars += intradayData.bars.length;
        processed++;
      }

    } catch (error) {
      Logger.log(`Error processing ${ticker}: ${error.message}`);
    }
  }

  SpreadsheetApp.flush();

  const msg = `Processed ${processed} of ${numRows} selected positions.\nWrote ${totalBars} 1-minute bars.`;
  SpreadsheetApp.getUi().alert('Update Complete', msg, SpreadsheetApp.getUi().ButtonSet.OK);
}

/**
 * Clear all intraday data from output sheet
 * Use this to reset the sheet
 */
function EW_clearAllIntradayData() {
  const ss = SpreadsheetApp.getActive();
  const outputSheet = ss.getSheetByName('Long Calls Options');

  if (!outputSheet) {
    SpreadsheetApp.getUi().alert('Long Calls Options sheet not found');
    return;
  }

  const lastRow = outputSheet.getLastRow();
  if (lastRow > 1) {
    outputSheet.deleteRows(2, lastRow - 1);
  }

  SpreadsheetApp.getUi().alert('All intraday data cleared');
}
