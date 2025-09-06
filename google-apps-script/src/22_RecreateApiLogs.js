/**
 * Recreate Missing API Log Files
 * Functions to check for missing API log files and recreate them by fetching data
 */

/**
 * Check for missing API log files for all positions in a sheet
 * @param {string} sheetName - Optional specific sheet name, otherwise checks active sheet
 */
function EW_checkMissingApiLogs(sheetName = null) {
  const startTime = new Date();
  console.log('===== CHECKING FOR MISSING API LOGS =====');
  
  const ss = SpreadsheetApp.getActive();
  const sheet = sheetName ? ss.getSheetByName(sheetName) : ss.getActiveSheet();
  
  if (!sheet || sheet.getLastRow() < 2) {
    EW_safeAlert('No Data', 'Sheet has no data to check');
    return;
  }
  
  // Get headers
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Check required columns
  if (!hdrMap.tickerCol || !hdrMap.runDateCol) {
    EW_safeAlert('Missing Columns', 'Required columns (ticker, runDate) not found');
    return;
  }
  
  // Get API logs folder
  let apiLogsFolder;
  try {
    const folderId = getApiLogFolderId();
    apiLogsFolder = DriveApp.getFolderById(folderId);
    console.log(`Checking logs in folder: ${apiLogsFolder.getName()}`);
  } catch (error) {
    EW_safeAlert('Folder Error', `Cannot access API logs folder: ${error.message}`);
    return;
  }
  
  // Get all existing log files
  const existingFiles = new Set();
  const files = apiLogsFolder.getFiles();
  while (files.hasNext()) {
    const file = files.next();
    existingFiles.add(file.getName());
  }
  console.log(`Found ${existingFiles.size} existing API log files`);
  
  // Check each row for missing logs
  const lastRow = sheet.getLastRow();
  const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  
  const missingLogs = [];
  const checkedPositions = [];
  
  for (let i = 0; i < data.length; i++) {
    const rowNum = i + 2;
    const rowData = data[i];
    
    const ticker = rowData[hdrMap.tickerCol - 1];
    const runDate = rowData[hdrMap.runDateCol - 1];
    
    if (!ticker || !runDate) continue;
    
    const runDateObj = new Date(runDate);
    
    // Check for logs for each day (Day 0-5)
    for (let day = 0; day <= 5; day++) {
      const checkDate = new Date(runDateObj);
      checkDate.setDate(checkDate.getDate() + day);
      
      // Skip weekends
      if (checkDate.getDay() === 0 || checkDate.getDay() === 6) continue;
      
      // Generate expected filename pattern
      const dateStr = checkDate.toISOString().split('T')[0];
      const filePattern = `${ticker}_${dateStr}_`;
      
      // Check if any file exists for this ticker and date
      let foundFile = false;
      for (const fileName of existingFiles) {
        if (fileName.startsWith(filePattern)) {
          foundFile = true;
          break;
        }
      }
      
      if (!foundFile) {
        missingLogs.push({
          row: rowNum,
          ticker: ticker,
          date: checkDate,
          dateStr: dateStr,
          day: day,
          runDate: runDateObj
        });
      }
    }
    
    checkedPositions.push({
      row: rowNum,
      ticker: ticker,
      runDate: runDateObj
    });
  }
  
  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);
  
  // Report results
  console.log(`\n===== MISSING LOGS SUMMARY =====`);
  console.log(`Checked ${checkedPositions.length} positions`);
  console.log(`Found ${missingLogs.length} missing log files`);
  console.log(`Duration: ${duration} seconds`);
  
  if (missingLogs.length > 0) {
    console.log('\nMissing logs (first 20):');
    missingLogs.slice(0, 20).forEach(log => {
      console.log(`  Row ${log.row}: ${log.ticker} - ${log.dateStr} (Day ${log.day})`);
    });
    
    if (missingLogs.length > 20) {
      console.log(`  ... and ${missingLogs.length - 20} more`);
    }
  }
  
  // Show UI dialog with options
  const ui = SpreadsheetApp.getUi();
  if (missingLogs.length === 0) {
    ui.alert('Log Check Complete', 
      `All API logs are present!\n\n` +
      `Checked: ${checkedPositions.length} positions\n` +
      `Duration: ${duration} seconds`,
      ui.ButtonSet.OK);
  } else {
    const response = ui.alert('Missing API Logs Found',
      `Found ${missingLogs.length} missing API log files.\n\n` +
      `Checked: ${checkedPositions.length} positions\n` +
      `Duration: ${duration} seconds\n\n` +
      `Do you want to recreate the missing logs?\n` +
      `(This will fetch data from Yahoo Finance)`,
      ui.ButtonSet.YES_NO);
    
    if (response === ui.Button.YES) {
      return EW_recreateMissingLogs(missingLogs);
    }
  }
  
  return {
    checked: checkedPositions.length,
    missing: missingLogs.length,
    duration: duration,
    missingLogs: missingLogs
  };
}

/**
 * Recreate missing API log files by fetching data
 * @param {Array} missingLogs - Array of missing log entries
 */
function EW_recreateMissingLogs(missingLogs) {
  const MAX_LOGS_TO_CREATE = 50; // Limit to prevent timeout
  const logsToCreate = missingLogs.slice(0, MAX_LOGS_TO_CREATE);
  
  console.log(`\n===== RECREATING MISSING LOGS =====`);
  console.log(`Will create up to ${MAX_LOGS_TO_CREATE} log files`);
  
  const startTime = new Date();
  let createdCount = 0;
  let failedCount = 0;
  const errors = [];
  
  // Group by ticker to minimize API calls
  const groupedByTicker = {};
  logsToCreate.forEach(log => {
    if (!groupedByTicker[log.ticker]) {
      groupedByTicker[log.ticker] = [];
    }
    groupedByTicker[log.ticker].push(log);
  });
  
  // Process each ticker
  for (const ticker in groupedByTicker) {
    const tickerLogs = groupedByTicker[ticker];
    console.log(`\nProcessing ${ticker} - ${tickerLogs.length} missing logs`);
    
    for (const log of tickerLogs) {
      try {
        console.log(`  Fetching data for ${log.dateStr}...`);
        
        // Fetch historical data for this date
        const result = EW_fetchYahooHistoricalForDate(ticker, log.date, true);
        
        if (result && result.dayHigh && result.dayLow) {
          // Create the API log entry
          const logEntry = {
            ticker: ticker,
            timestamp: new Date().toISOString(),
            date: log.dateStr,
            interval: '1d',
            targetPrice: null,
            success: true,
            dataPoints: 1,
            dayHigh: result.dayHigh,
            dayLow: result.dayLow,
            dayOpen: result.dayOpen || null,
            dayClose: result.dayClose || null,
            dayVolume: result.dayVolume || 0,
            recreated: true,
            recreatedAt: new Date().toISOString(),
            originalRunDate: log.runDate.toISOString().split('T')[0],
            dayIndex: log.day
          };
          
          // Save the recreated log
          EW_saveRecreatedApiLog(ticker, log.date, logEntry, result);
          createdCount++;
          console.log(`    ✅ Created log for ${log.dateStr}`);
          
        } else {
          failedCount++;
          errors.push(`${ticker} ${log.dateStr}: No data available`);
          console.log(`    ❌ No data available for ${log.dateStr}`);
        }
        
        // Add small delay to avoid rate limiting
        Utilities.sleep(100);
        
      } catch (error) {
        failedCount++;
        errors.push(`${ticker} ${log.dateStr}: ${error.message}`);
        console.error(`    ❌ Error: ${error.message}`);
      }
      
      // Check for timeout
      const elapsed = new Date() - startTime;
      if (elapsed > 4 * 60 * 1000) { // 4 minutes
        console.log('Approaching timeout limit, stopping...');
        break;
      }
    }
  }
  
  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);
  
  // Summary
  console.log(`\n===== RECREATION SUMMARY =====`);
  console.log(`Created: ${createdCount} log files`);
  console.log(`Failed: ${failedCount}`);
  console.log(`Duration: ${duration} seconds`);
  
  if (errors.length > 0 && errors.length <= 10) {
    console.log('\nErrors:');
    errors.forEach(err => console.log(`  ${err}`));
  }
  
  // Show UI summary
  const ui = SpreadsheetApp.getUi();
  let message = `Log Recreation Complete!\n\n` +
    `Created: ${createdCount} log files\n` +
    `Failed: ${failedCount}\n` +
    `Duration: ${duration} seconds`;
  
  if (missingLogs.length > MAX_LOGS_TO_CREATE) {
    message += `\n\nNote: Only processed first ${MAX_LOGS_TO_CREATE} of ${missingLogs.length} missing logs.`;
    message += `\nRun again to process more.`;
  }
  
  if (errors.length > 0 && errors.length <= 5) {
    message += `\n\nErrors:\n${errors.slice(0, 5).join('\n')}`;
  }
  
  ui.alert('Recreation Complete', message, ui.ButtonSet.OK);
  
  return {
    created: createdCount,
    failed: failedCount,
    duration: duration,
    errors: errors
  };
}

/**
 * Save a recreated API log file
 * @param {string} ticker - Stock ticker
 * @param {Date} date - Date of the data
 * @param {Object} logEntry - Log entry metadata
 * @param {Object} data - Full data from Yahoo
 */
function EW_saveRecreatedApiLog(ticker, date, logEntry, data) {
  try {
    const folderId = getApiLogFolderId();
    const folder = DriveApp.getFolderById(folderId);
    
    // Create filename
    const dateStr = date.toISOString().split('T')[0];
    const timeStr = new Date().toISOString().split('T')[1].replace(/:/g, '-').split('.')[0];
    const fileName = `${ticker}_${dateStr}_${timeStr}_RECREATED.json`;
    
    // Create full log object
    const logData = {
      metadata: logEntry,
      response: {
        chart: {
          result: [{
            meta: {
              symbol: ticker,
              exchangeName: 'NYSE',
              regularMarketTime: date.getTime() / 1000,
              regularMarketPrice: data.dayClose || data.lastClose
            },
            timestamp: [date.getTime() / 1000],
            indicators: {
              quote: [{
                open: [data.dayOpen],
                high: [data.dayHigh],
                low: [data.dayLow],
                close: [data.dayClose || data.lastClose],
                volume: [data.dayVolume || 0]
              }]
            }
          }],
          error: null
        },
        recreated: true,
        recreatedFrom: 'Historical data fetch',
        originalData: data
      }
    };
    
    // Save file
    const blob = Utilities.newBlob(JSON.stringify(logData, null, 2), 'application/json', fileName);
    const file = folder.createFile(blob);
    
    console.log(`    Saved recreated log: ${fileName}`);
    
    // Also update the daily summary log
    EW_updateDailySummaryLog(logEntry);
    
    return file;
    
  } catch (error) {
    console.error(`Failed to save recreated log: ${error.message}`);
    throw error;
  }
}

/**
 * Update the daily summary log with recreated entry
 */
function EW_updateDailySummaryLog(logEntry) {
  try {
    const file = EW_getApiLogFile();
    if (!file) return;
    
    // Get existing content
    const content = file.getBlob().getDataAsString();
    const logData = JSON.parse(content);
    
    // Add the recreated entry
    logData.calls.push({
      ...logEntry,
      note: 'Recreated from historical data'
    });
    
    // Update file
    file.setContent(JSON.stringify(logData, null, 2));
    
  } catch (error) {
    console.error(`Failed to update summary log: ${error.message}`);
    // Don't throw - this is supplementary
  }
}

/**
 * Check missing logs for selected rows only
 */
function EW_checkMissingLogsForSelected() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const range = sheet.getActiveRange();
  
  if (!range || range.getRow() === 1) {
    EW_safeAlert('Invalid Selection', 'Please select data rows to check');
    return;
  }
  
  // Get headers
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  if (!hdrMap.tickerCol || !hdrMap.runDateCol) {
    EW_safeAlert('Missing Columns', 'Required columns (ticker, runDate) not found');
    return;
  }
  
  // Get API logs folder
  let apiLogsFolder;
  try {
    const folderId = getApiLogFolderId();
    apiLogsFolder = DriveApp.getFolderById(folderId);
  } catch (error) {
    EW_safeAlert('Folder Error', `Cannot access API logs folder: ${error.message}`);
    return;
  }
  
  // Get existing files
  const existingFiles = new Set();
  const files = apiLogsFolder.getFiles();
  while (files.hasNext()) {
    const file = files.next();
    existingFiles.add(file.getName());
  }
  
  // Check selected rows
  const startRow = range.getRow();
  const numRows = range.getNumRows();
  const data = sheet.getRange(startRow, 1, numRows, sheet.getLastColumn()).getValues();
  
  const missingLogs = [];
  
  for (let i = 0; i < data.length; i++) {
    const rowNum = startRow + i;
    const rowData = data[i];
    
    const ticker = rowData[hdrMap.tickerCol - 1];
    const runDate = rowData[hdrMap.runDateCol - 1];
    
    if (!ticker || !runDate) continue;
    
    const runDateObj = new Date(runDate);
    
    // Check each day
    for (let day = 0; day <= 5; day++) {
      const checkDate = new Date(runDateObj);
      checkDate.setDate(checkDate.getDate() + day);
      
      if (checkDate.getDay() === 0 || checkDate.getDay() === 6) continue;
      
      const dateStr = checkDate.toISOString().split('T')[0];
      const filePattern = `${ticker}_${dateStr}_`;
      
      let foundFile = false;
      for (const fileName of existingFiles) {
        if (fileName.startsWith(filePattern)) {
          foundFile = true;
          break;
        }
      }
      
      if (!foundFile) {
        missingLogs.push({
          row: rowNum,
          ticker: ticker,
          date: checkDate,
          dateStr: dateStr,
          day: day,
          runDate: runDateObj
        });
      }
    }
  }
  
  // Show results
  const ui = SpreadsheetApp.getUi();
  if (missingLogs.length === 0) {
    ui.alert('Check Complete', 
      `All API logs present for selected rows!\n\n` +
      `Checked: ${numRows} rows`,
      ui.ButtonSet.OK);
  } else {
    const response = ui.alert('Missing Logs Found',
      `Found ${missingLogs.length} missing API logs.\n\n` +
      `Checked: ${numRows} rows\n\n` +
      `Do you want to recreate them?`,
      ui.ButtonSet.YES_NO);
    
    if (response === ui.Button.YES) {
      return EW_recreateMissingLogs(missingLogs);
    }
  }
}