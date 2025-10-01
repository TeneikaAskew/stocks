/**
 * Cache Data Validation and Repair
 * Validates that cached API data matches the run dates in spreadsheet rows
 * Fixes mismatches by refetching data from Yahoo Finance
 */

/**
 * Validate and fix cache data for positions within last 7 days (1-minute data)
 * Checks each row's run date against cached data and refetches if mismatch
 */
function EW_validateAndFixRecentCache() {
  const startTime = new Date();
  console.log('===== VALIDATING RECENT CACHE (Last 7 Days) =====');

  const ss = SpreadsheetApp.getActive();
  const ui = SpreadsheetApp.getUi();

  // Get current active sheet only
  const sheet = ss.getActiveSheet();
  const strategyName = sheet.getName();

  // Validate this is a strategy sheet
  if (!EW.STRATEGY_ENDPOINTS[strategyName]) {
    ui.alert('Invalid Sheet', `"${strategyName}" is not a valid strategy sheet.`, ui.ButtonSet.OK);
    return;
  }

  if (sheet.getLastRow() < 2) {
    ui.alert('No Data', `No data rows found in ${strategyName}.`, ui.ButtonSet.OK);
    return;
  }

  console.log(`Processing ${strategyName}...`);

  const results = {
    totalRows: 0,
    validCache: 0,
    invalidCache: 0,
    refetched: 0,
    errors: 0,
    skipped: 0,
    details: []
  };

  // Get headers
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);

  // Check required columns
  if (!hdrMap.tickerCol || !hdrMap.runDateCol) {
    ui.alert('Missing Columns', `${strategyName} is missing required columns (ticker, runDate).`, ui.ButtonSet.OK);
    return;
  }

  // Get all data
  const lastRow = sheet.getLastRow();
  const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();

  // Determine strike column (handle spreads)
  const isSpread = strategyName.toUpperCase().includes('SPREAD');
  const strikeCol = isSpread ? hdrMap.longStrikeCol : hdrMap.strikeCol;

  if (!strikeCol) {
    ui.alert('Missing Column', `${strategyName} is missing strike column.`, ui.ButtonSet.OK);
    return;
  }

  // Check each row
  for (let i = 0; i < data.length; i++) {
      const rowNum = i + 2;
      const row = data[i];

      const ticker = row[hdrMap.tickerCol - 1];
      const runDateStr = row[hdrMap.runDateCol - 1];
      const strike = parseFloat(row[strikeCol - 1]);

      if (!ticker || !runDateStr || !strike) {
        results.skipped++;
        continue;
      }

      const runDate = new Date(runDateStr);
      const today = new Date();
      const daysSinceRun = Math.floor((today - runDate) / (1000 * 60 * 60 * 24));

      // Skip if older than 7 days (handled by separate function)
      if (daysSinceRun > 7) {
        results.skipped++;
        continue;
      }

      results.totalRows++;

      // Validate cache for this row
      const validation = EW_validateRowCache(ticker, runDate, '1m');

      if (validation.isValid) {
        results.validCache++;
      } else {
        results.invalidCache++;
        console.log(`INVALID: ${strategyName} Row ${rowNum} - ${ticker} - ${validation.reason}`);

        // Refetch the data
        try {
          const refetchResult = EW_refetchPositionData(ticker, runDate, strike, strategyName, rowNum, hdrMap, sheet, false, row);

          if (refetchResult.success) {
            results.refetched++;
            results.details.push({
              sheet: strategyName,
              row: rowNum,
              ticker: ticker,
              runDate: EW_formatDate(runDate),
              status: 'Refetched',
              reason: validation.reason
            });
          } else {
            results.errors++;
            results.details.push({
              sheet: strategyName,
              row: rowNum,
              ticker: ticker,
              runDate: EW_formatDate(runDate),
              status: 'Error',
              reason: refetchResult.error
            });
          }
        } catch (error) {
          results.errors++;
          console.error(`Error refetching ${ticker}: ${error.message}`);
        }
      }

    // Check execution time (29.5 min limit for premium account)
    if (new Date() - startTime > 29.5 * 60 * 1000) {
      console.log('Approaching time limit, stopping...');
      break;
    }
  }

  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);

  // Print summary
  console.log('\n===== RECENT CACHE VALIDATION SUMMARY =====');
  console.log(`Total rows checked: ${results.totalRows}`);
  console.log(`Valid cache: ${results.validCache}`);
  console.log(`Invalid cache: ${results.invalidCache}`);
  console.log(`Refetched: ${results.refetched}`);
  console.log(`Errors: ${results.errors}`);
  console.log(`Skipped: ${results.skipped}`);
  console.log(`Duration: ${duration} seconds`);

  // Show UI dialog
  let message = `Recent Cache Validation Complete!\n\n`;
  message += `Rows checked: ${results.totalRows}\n`;
  message += `Valid: ${results.validCache}\n`;
  message += `Invalid: ${results.invalidCache}\n`;
  message += `Refetched: ${results.refetched}\n`;
  message += `Errors: ${results.errors}\n`;
  message += `Duration: ${duration}s`;

  if (results.details.length > 0 && results.details.length <= 5) {
    message += `\n\nDetails:\n`;
    results.details.forEach(d => {
      message += `${d.sheet} Row ${d.row}: ${d.ticker} - ${d.status}\n`;
    });
  }

  ui.alert('Cache Validation', message, ui.ButtonSet.OK);

  return results;
}

/**
 * Validate and fix cache data for positions older than 7 days (daily data)
 * Checks each row's run date against cached data and refetches if mismatch
 */
function EW_validateAndFixHistoricalCache() {
  const startTime = new Date();
  console.log('===== VALIDATING HISTORICAL CACHE (>7 Days Old) =====');

  const ss = SpreadsheetApp.getActive();
  const ui = SpreadsheetApp.getUi();

  // Get current active sheet only
  const sheet = ss.getActiveSheet();
  const strategyName = sheet.getName();

  // Validate this is a strategy sheet
  if (!EW.STRATEGY_ENDPOINTS[strategyName]) {
    ui.alert('Invalid Sheet', `"${strategyName}" is not a valid strategy sheet.`, ui.ButtonSet.OK);
    return;
  }

  if (sheet.getLastRow() < 2) {
    ui.alert('No Data', `No data rows found in ${strategyName}.`, ui.ButtonSet.OK);
    return;
  }

  console.log(`Processing ${strategyName}...`);

  const results = {
    totalRows: 0,
    validCache: 0,
    invalidCache: 0,
    refetched: 0,
    errors: 0,
    skipped: 0,
    details: []
  };

  // Get headers
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);

  // Check required columns
  if (!hdrMap.tickerCol || !hdrMap.runDateCol) {
    ui.alert('Missing Columns', `${strategyName} is missing required columns (ticker, runDate).`, ui.ButtonSet.OK);
    return;
  }

  // Get all data
  const lastRow = sheet.getLastRow();
  const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();

  // Determine strike column (handle spreads)
  const isSpread = strategyName.toUpperCase().includes('SPREAD');
  const strikeCol = isSpread ? hdrMap.longStrikeCol : hdrMap.strikeCol;

  if (!strikeCol) {
    ui.alert('Missing Column', `${strategyName} is missing strike column.`, ui.ButtonSet.OK);
    return;
  }

  // Check each row
  for (let i = 0; i < data.length; i++) {
      const rowNum = i + 2;
      const row = data[i];

      const ticker = row[hdrMap.tickerCol - 1];
      const runDateStr = row[hdrMap.runDateCol - 1];
      const strike = parseFloat(row[strikeCol - 1]);

      if (!ticker || !runDateStr || !strike) {
        results.skipped++;
        continue;
      }

      const runDate = new Date(runDateStr);
      const today = new Date();
      const daysSinceRun = Math.floor((today - runDate) / (1000 * 60 * 60 * 24));

      // Skip if within 7 days (handled by separate function)
      if (daysSinceRun <= 7) {
        results.skipped++;
        continue;
      }

      results.totalRows++;

      // Validate cache for this row (daily data)
      const validation = EW_validateRowCache(ticker, runDate, '1d');

      if (validation.isValid) {
        results.validCache++;
      } else {
        results.invalidCache++;
        console.log(`INVALID: ${strategyName} Row ${rowNum} - ${ticker} - ${validation.reason}`);

        // Refetch the data
        try {
          const refetchResult = EW_refetchPositionData(ticker, runDate, strike, strategyName, rowNum, hdrMap, sheet, true, row);

          if (refetchResult.success) {
            results.refetched++;
            results.details.push({
              sheet: strategyName,
              row: rowNum,
              ticker: ticker,
              runDate: EW_formatDate(runDate),
              status: 'Refetched',
              reason: validation.reason
            });
          } else {
            results.errors++;
            results.details.push({
              sheet: strategyName,
              row: rowNum,
              ticker: ticker,
              runDate: EW_formatDate(runDate),
              status: 'Error',
              reason: refetchResult.error
            });
          }
        } catch (error) {
          results.errors++;
          console.error(`Error refetching ${ticker}: ${error.message}`);
        }
      }

    // Check execution time (29.5 min limit for premium account)
    if (new Date() - startTime > 29.5 * 60 * 1000) {
      console.log('Approaching time limit, stopping...');
      break;
    }
  }

  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);

  // Print summary
  console.log('\n===== HISTORICAL CACHE VALIDATION SUMMARY =====');
  console.log(`Total rows checked: ${results.totalRows}`);
  console.log(`Valid cache: ${results.validCache}`);
  console.log(`Invalid cache: ${results.invalidCache}`);
  console.log(`Refetched: ${results.refetched}`);
  console.log(`Errors: ${results.errors}`);
  console.log(`Skipped: ${results.skipped}`);
  console.log(`Duration: ${duration} seconds`);

  // Show UI dialog
  let message = `Historical Cache Validation Complete!\n\n`;
  message += `Rows checked: ${results.totalRows}\n`;
  message += `Valid: ${results.validCache}\n`;
  message += `Invalid: ${results.invalidCache}\n`;
  message += `Refetched: ${results.refetched}\n`;
  message += `Errors: ${results.errors}\n`;
  message += `Duration: ${duration}s`;

  if (results.details.length > 0 && results.details.length <= 5) {
    message += `\n\nDetails:\n`;
    results.details.forEach(d => {
      message += `${d.sheet} Row ${d.row}: ${d.ticker} - ${d.status}\n`;
    });
  }

  ui.alert('Cache Validation', message, ui.ButtonSet.OK);

  return results;
}

/**
 * Validate cache data for a specific row's run date
 * @param {string} ticker - Ticker symbol
 * @param {Date} runDate - Run date from spreadsheet
 * @param {string} interval - Data interval ('1m' or '1d')
 * @returns {Object} Validation result {isValid: boolean, reason: string}
 */
function EW_validateRowCache(ticker, runDate, interval) {
  try {
    const runDateStr = EW_formatDate(runDate);

    // Check if cache file exists
    const cachedData = EW_getCachedApiData(ticker, runDate);

    if (!cachedData) {
      return { isValid: false, reason: 'No cache file found' };
    }

    // Get the cache file to check data range
    const folderId = getApiLogFolderId();
    const folder = DriveApp.getFolderById(folderId);
    const filePattern = `${ticker}_${runDateStr}`;

    const searchQuery = `title contains '${filePattern}' and mimeType = 'application/json' and trashed = false`;
    const files = folder.searchFiles(searchQuery);

    if (!files.hasNext()) {
      return { isValid: false, reason: 'Cache file not found in search' };
    }

    const file = files.next();
    const content = file.getBlob().getDataAsString();
    const logData = JSON.parse(content);

    // Check if response has data
    if (!logData.response?.chart?.result?.[0]?.timestamp) {
      return { isValid: false, reason: 'Cache file has no timestamp data' };
    }

    const timestamps = logData.response.chart.result[0].timestamp;
    if (timestamps.length === 0) {
      return { isValid: false, reason: 'Cache file has empty timestamps' };
    }

    // Get data date range
    const firstTimestamp = timestamps[0];
    const lastTimestamp = timestamps[timestamps.length - 1];
    const firstDate = new Date(firstTimestamp * 1000);
    const lastDate = new Date(lastTimestamp * 1000);

    const firstDateStr = EW_formatDate(firstDate);
    const lastDateStr = EW_formatDate(lastDate);

    // Compare dates only (ignore time component)
    // Set all times to midnight for date-only comparison
    const runDateOnly = new Date(runDate);
    runDateOnly.setHours(0, 0, 0, 0);

    const firstDateOnly = new Date(firstDate);
    firstDateOnly.setHours(0, 0, 0, 0);

    const lastDateOnly = new Date(lastDate);
    lastDateOnly.setHours(0, 0, 0, 0);

    if (runDateOnly < firstDateOnly || runDateOnly > lastDateOnly) {
      return {
        isValid: false,
        reason: `Run date ${runDateStr} not in data range ${firstDateStr} to ${lastDateStr}`
      };
    }

    // Valid!
    return { isValid: true, reason: 'Cache data matches run date' };

  } catch (error) {
    console.error(`Error validating cache for ${ticker}: ${error.message}`);
    return { isValid: false, reason: `Validation error: ${error.message}` };
  }
}

/**
 * Refetch position data by deleting cache and running backfill
 * Uses the exact same logic as EW_backfillSelectedRows for consistency
 * @param {string} ticker - Ticker symbol
 * @param {Date} runDate - Run date
 * @param {number} strike - Strike price
 * @param {string} strategyName - Strategy name
 * @param {number} rowNum - Row number in sheet
 * @param {Object} hdrMap - Header map
 * @param {Sheet} sheet - Sheet object
 * @param {boolean} useDailyData - Not used, kept for compatibility
 * @param {Array} row - Row data
 * @returns {Object} Result {success: boolean, error: string}
 */
function EW_refetchPositionData(ticker, runDate, strike, strategyName, rowNum, hdrMap, sheet, useDailyData = false, row = null) {
  try {
    console.log(`Refetching ${ticker} for run date ${EW_formatDate(runDate)}...`);

    // Delete the invalid cache file first
    const runDateStr = EW_formatDate(runDate);
    EW_deleteInvalidCacheFile(ticker, runDateStr);

    // Clear the file list cache so we don't use stale data
    EW_clearFileListCache();

    // Clear existing backfill values before refetching
    EW_clearBackfillColumns(sheet, rowNum, hdrMap);

    // Re-read the row data to ensure we have current values
    const rowData = sheet.getRange(rowNum, 1, 1, sheet.getLastColumn()).getValues()[0];

    // Extract required fields from row (same as EW_backfillSelectedRows)
    const expDateStr = hdrMap.expDateCol ? rowData[hdrMap.expDateCol - 1] : null;
    const shortStrike = hdrMap.shortStrikeCol ? parseFloat(rowData[hdrMap.shortStrikeCol - 1]) : null;
    const isSpread = strategyName.toUpperCase().includes('SPREAD');

    // Use the same processBackfillPosition call as EW_backfillSelectedRows
    const params = {
      ticker: ticker,
      strategyName: strategyName,
      strike: strike,
      runDateStr: runDateStr,
      expDateStr: expDateStr,
      shortStrike: shortStrike,
      hdrMap: hdrMap,
      row: rowData,
      rowIndex: rowNum - 2,  // Convert to 0-based index
      sheet: sheet,
      isSpread: isSpread
    };

    const result = EW_processBackfillPosition(params);

    if (result.success && result.analysis) {
      // Update the sheet with the new analysis (same as EW_backfillSelectedRows)
      const expDateObj = expDateStr ? new Date(expDateStr) : null;
      const wasUpdated = EW_updateBackfillColumns(sheet, rowNum, result.analysis, hdrMap, ticker, expDateObj, rowData);

      if (wasUpdated) {
        console.log(`Successfully refetched and updated ${ticker} row ${rowNum}`);
        return { success: true };
      } else {
        return { success: false, error: 'Failed to update columns' };
      }
    } else {
      return {
        success: false,
        error: result.error || 'Process failed'
      };
    }

  } catch (error) {
    console.error(`Refetch error for ${ticker}: ${error.message}`);
    return { success: false, error: error.message };
  }
}

/**
 * Clear backfill columns before refetching data
 * @param {Sheet} sheet - Sheet object
 * @param {number} rowNum - Row number
 * @param {Object} hdrMap - Header map
 */
function EW_clearBackfillColumns(sheet, rowNum, hdrMap) {
  const columnsToClear = [
    'strikeHitCol',
    'hitDateCol',
    'maxFavorableCol',
    'minUnfavorableCol',
    'day0CheckCol',
    'day1CheckCol',
    'day2CheckCol',
    'day3CheckCol',
    'day4CheckCol',
    'day5CheckCol',
    'expResultCol',
    'riskRewardCol',
    'ohlcVolumeCol',
    'hitRSICol',
    'hitSMA20Col',
    'hitSMA50Col',
    'hitEMA9Col',
    'hitEMA21Col',
    'hitVWAPCol',
    'hitRVOLCol',
    'hitATRCol',
    'hitPriceVsSMA20Col',
    'hitPriceVsVWAPCol'
  ];

  columnsToClear.forEach(colKey => {
    if (hdrMap[colKey]) {
      sheet.getRange(rowNum, hdrMap[colKey]).clearContent();
    }
  });

  console.log(`Cleared backfill columns for row ${rowNum}`);
}

/**
 * Delete invalid cache file for a ticker and date
 * @param {string} ticker - Ticker symbol
 * @param {string} dateStr - Date string (YYYY-MM-DD)
 */
function EW_deleteInvalidCacheFile(ticker, dateStr) {
  try {
    const folderId = getApiLogFolderId();
    const folder = DriveApp.getFolderById(folderId);
    const filePattern = `${ticker}_${dateStr}`;

    const searchQuery = `title contains '${filePattern}' and mimeType = 'application/json' and trashed = false`;
    const files = folder.searchFiles(searchQuery);

    while (files.hasNext()) {
      const file = files.next();
      const fileName = file.getName();

      if (fileName.startsWith(filePattern) && fileName.endsWith('.json')) {
        console.log(`Deleting invalid cache file: ${fileName}`);
        file.setTrashed(true);
      }
    }
  } catch (error) {
    console.error(`Error deleting cache file for ${ticker}_${dateStr}: ${error.message}`);
  }
}

/**
 * Validate selected rows only
 */
function EW_validateSelectedRowsCache() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const range = sheet.getActiveRange();

  if (!range || range.getRow() === 1) {
    EW_safeAlert('Invalid Selection', 'Please select data rows to validate');
    return;
  }

  const strategyName = sheet.getName();
  const startRow = range.getRow();
  const numRows = range.getNumRows();

  console.log(`Validating ${numRows} selected rows in ${strategyName}...`);

  // Get headers
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);

  if (!hdrMap.tickerCol || !hdrMap.runDateCol) {
    EW_safeAlert('Error', 'Missing required columns (ticker, runDate)');
    return;
  }

  const isSpread = strategyName.toUpperCase().includes('SPREAD');
  const strikeCol = isSpread ? hdrMap.longStrikeCol : hdrMap.strikeCol;

  if (!strikeCol) {
    EW_safeAlert('Error', 'Missing strike column');
    return;
  }

  // Get selected data
  const data = sheet.getRange(startRow, 1, numRows, sheet.getLastColumn()).getValues();

  const results = {
    total: 0,
    valid: 0,
    invalid: 0,
    refetched: 0,
    errors: 0
  };

  for (let i = 0; i < data.length; i++) {
    const rowNum = startRow + i;
    const row = data[i];

    const ticker = row[hdrMap.tickerCol - 1];
    const runDateStr = row[hdrMap.runDateCol - 1];
    const strike = parseFloat(row[strikeCol - 1]);

    if (!ticker || !runDateStr || !strike) continue;

    results.total++;

    const runDate = new Date(runDateStr);
    const today = new Date();
    const daysSinceRun = Math.floor((today - runDate) / (1000 * 60 * 60 * 24));
    const interval = daysSinceRun <= 7 ? '1m' : '1d';

    const validation = EW_validateRowCache(ticker, runDate, interval);

    if (validation.isValid) {
      results.valid++;
    } else {
      results.invalid++;
      console.log(`Row ${rowNum}: ${ticker} - ${validation.reason}`);

      // Refetch
      try {
        const refetch = EW_refetchPositionData(
          ticker,
          runDate,
          strike,
          strategyName,
          rowNum,
          hdrMap,
          sheet,
          daysSinceRun > 7,
          row
        );

        if (refetch.success) {
          results.refetched++;
        } else {
          results.errors++;
        }
      } catch (error) {
        results.errors++;
      }
    }
  }

  const message = `Validation Complete!\n\n` +
    `Total: ${results.total}\n` +
    `Valid: ${results.valid}\n` +
    `Invalid: ${results.invalid}\n` +
    `Refetched: ${results.refetched}\n` +
    `Errors: ${results.errors}`;

  EW_safeAlert('Selected Rows Validation', message);

  return results;
}
