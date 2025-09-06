/**
 * API Call Logging - Functions to log Yahoo Finance API calls to Google Drive
 * Stores detailed logs in JSON format for tracking and analysis
 */

// Get Drive folder IDs from Script Properties
function getApiLogFolderId() {
  const scriptProperties = PropertiesService.getScriptProperties();
  const folderId = scriptProperties.getProperty('API_LOGS_FOLDER_ID');
  if (!folderId) {
    // Log all script properties for debugging
    const allProps = scriptProperties.getProperties();
    console.error('API_LOGS_FOLDER_ID not found. All Script Properties:', JSON.stringify(allProps, null, 2));
    throw new Error('API_LOGS_FOLDER_ID not set in Script Properties');
  }
  console.log(`Using API_LOGS_FOLDER_ID: ${folderId}`);
  return folderId;
}

function getApiSummaryFolderId() {
  const scriptProperties = PropertiesService.getScriptProperties();
  const folderId = scriptProperties.getProperty('DAILY_REPORTS_FOLDER_ID');
  if (!folderId) {
    // Log all script properties for debugging
    const allProps = scriptProperties.getProperties();
    console.error('DAILY_REPORTS_FOLDER_ID not found. All Script Properties:', JSON.stringify(allProps, null, 2));
    throw new Error('DAILY_REPORTS_FOLDER_ID not set in Script Properties');
  }
  console.log(`Using DAILY_REPORTS_FOLDER_ID: ${folderId}`);
  return folderId;
}

/**
 * Initialize or get today's API log file
 * @returns {Object} File object for today's log
 */
function EW_getApiLogFile() {
  try {
    const folderId = getApiSummaryFolderId();
    console.log(`Attempting to access DAILY_REPORTS folder with ID: ${folderId}`);
    
    const folder = DriveApp.getFolderById(folderId);  // Use summary folder
    console.log(`Successfully accessed folder: ${folder.getName()}`);
    
    const today = new Date();
    const fileName = `yahoo_api_log_${today.toISOString().split('T')[0]}.json`;
    console.log(`Looking for or creating file: ${fileName}`);
    
    // Check if today's log file already exists
    const files = folder.getFilesByName(fileName);
    if (files.hasNext()) {
      const existingFile = files.next();
      console.log(`Found existing log file: ${existingFile.getName()}`);
      return existingFile;
    }
    
    // Create new log file for today
    console.log(`Creating new log file: ${fileName}`);
    const initialData = {
      date: today.toISOString().split('T')[0],
      created: today.toISOString(),
      calls: []
    };
    
    const blob = Utilities.newBlob(JSON.stringify(initialData, null, 2), 'application/json', fileName);
    const newFile = folder.createFile(blob);
    console.log(`Created new log file: ${newFile.getName()} with ID: ${newFile.getId()}`);
    return newFile;
    
  } catch (error) {
    console.error(`API LOG ERROR: Failed to get/create log file: ${error.message}`);
    console.error(`Error stack: ${error.stack}`);
    
    // Log all Script Properties when there's an error
    const scriptProperties = PropertiesService.getScriptProperties();
    const allProps = scriptProperties.getProperties();
    console.error('Current Script Properties:', JSON.stringify(allProps, null, 2));
    
    EW_trace('API_LOG', `Failed to get/create log file: ${error.message}`);
    return null;
  }
}

/**
 * Log an API call to the JSON file
 * @param {Object} callData - Data about the API call
 * @param {Object} rawResponse - Raw JSON response from Yahoo API (optional)
 */
function EW_logApiCall(callData, rawResponse = null) {
  try {
    const file = EW_getApiLogFile();
    if (!file) return;
    
    // Get existing content
    const content = file.getBlob().getDataAsString();
    const logData = JSON.parse(content);
    
    // Add timestamp to call data
    callData.timestamp = new Date().toISOString();
    
    // Add the new call
    logData.calls.push(callData);
    
    // Update file
    file.setContent(JSON.stringify(logData, null, 2));
    
    // If we have a raw response, save it separately (save for both success and failure)
    if (rawResponse && callData.ticker) {
      EW_trace('API_LOG', `Saving raw response for ${callData.ticker}, success=${callData.success}`);
      EW_saveApiResponse(callData.ticker, callData.timestamp, rawResponse, callData);
    } else {
      EW_trace('API_LOG', `Not saving raw response - rawResponse=${!!rawResponse}, ticker=${callData.ticker}, success=${callData.success}`);
    }
    
  } catch (error) {
    console.error(`API LOG ERROR: Failed to log API call: ${error.message}`);
    EW_trace('API_LOG', `Failed to log API call: ${error.message}`);
  }
}

/**
 * Create a summary of API calls for a specific date
 * @param {Date} date - Date to summarize (defaults to today)
 * @returns {Object} Summary statistics
 */
function EW_getApiCallSummary(date = new Date()) {
  try {
    const folder = DriveApp.getFolderById(getApiSummaryFolderId());  // Use summary folder
    const fileName = `yahoo_api_log_${date.toISOString().split('T')[0]}.json`;
    
    const files = folder.getFilesByName(fileName);
    if (!files.hasNext()) {
      return { error: 'No log file found for this date' };
    }
    
    const file = files.next();
    const content = file.getBlob().getDataAsString();
    const logData = JSON.parse(content);
    
    // Calculate summary statistics
    const summary = {
      date: logData.date,
      totalCalls: logData.calls.length,
      byInterval: {},
      byTicker: {},
      byStatus: {
        success: 0,
        error: 0,
        fallback: 0
      },
      errors: [],
      fallbacks: []
    };
    
    // Process each call
    logData.calls.forEach(call => {
      // Count by interval
      summary.byInterval[call.interval] = (summary.byInterval[call.interval] || 0) + 1;
      
      // Count by ticker
      summary.byTicker[call.ticker] = (summary.byTicker[call.ticker] || 0) + 1;
      
      // Count by status
      if (call.error) {
        summary.byStatus.error++;
        summary.errors.push({
          ticker: call.ticker,
          interval: call.interval,
          error: call.error,
          timestamp: call.timestamp
        });
      } else {
        summary.byStatus.success++;
      }
      
      if (call.fallbackUsed) {
        summary.byStatus.fallback++;
        summary.fallbacks.push({
          ticker: call.ticker,
          originalInterval: call.requestedInterval || '1m',
          fallbackInterval: call.fallbackUsed,
          timestamp: call.timestamp
        });
      }
    });
    
    return summary;
    
  } catch (error) {
    console.error(`API LOG ERROR: Failed to get summary: ${error.message}`);
    return { error: error.message };
  }
}

/**
 * Create a daily summary report and save to Drive
 */
function EW_createDailyApiReport() {
  try {
    const summary = EW_getApiCallSummary();
    if (summary.error) {
      console.error(`API REPORT ERROR: ${summary.error}`);
      return;
    }
    
    const folder = DriveApp.getFolderById(getApiSummaryFolderId());  // Use summary folder
    const today = new Date();
    const reportName = `yahoo_api_summary_${today.toISOString().split('T')[0]}.txt`;
    
    // Create report content
    let report = `Yahoo Finance API Call Summary\n`;
    report += `Date: ${summary.date}\n`;
    report += `Generated: ${today.toISOString()}\n`;
    report += `\n`;
    report += `Total API Calls: ${summary.totalCalls}\n`;
    report += `Successful: ${summary.byStatus.success}\n`;
    report += `Errors: ${summary.byStatus.error}\n`;
    report += `Fallbacks Used: ${summary.byStatus.fallback}\n`;
    report += `\n`;
    
    report += `Calls by Interval:\n`;
    Object.entries(summary.byInterval).forEach(([interval, count]) => {
      report += `  ${interval}: ${count}\n`;
    });
    report += `\n`;
    
    report += `Top 10 Tickers by Call Count:\n`;
    const topTickers = Object.entries(summary.byTicker)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);
    topTickers.forEach(([ticker, count]) => {
      report += `  ${ticker}: ${count}\n`;
    });
    
    if (summary.fallbacks.length > 0) {
      report += `\nFallback Details:\n`;
      summary.fallbacks.forEach(fb => {
        report += `  ${fb.ticker}: ${fb.originalInterval} → ${fb.fallbackInterval} at ${fb.timestamp}\n`;
      });
    }
    
    if (summary.errors.length > 0) {
      report += `\nError Details:\n`;
      summary.errors.forEach(err => {
        report += `  ${err.ticker} (${err.interval}): ${err.error} at ${err.timestamp}\n`;
      });
    }
    
    // Save report
    const blob = Utilities.newBlob(report, 'text/plain', reportName);
    folder.createFile(blob);
    
    console.log(`API REPORT: Daily summary saved as ${reportName}`);
    EW_trace('API_LOG', `Daily API report created: ${reportName}`);
    
  } catch (error) {
    console.error(`API REPORT ERROR: Failed to create report: ${error.message}`);
    EW_trace('API_LOG', `Failed to create API report: ${error.message}`);
  }
}

/**
 * Clean up old log files (keep last 30 days)
 */
function EW_cleanupOldApiLogs() {
  try {
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - 30);
    let deletedCount = 0;
    
    // Clean up detailed response files in main folder
    const mainFolder = DriveApp.getFolderById(getApiLogFolderId());
    const mainFiles = mainFolder.getFiles();
    
    while (mainFiles.hasNext()) {
      const file = mainFiles.next();
      const fileName = file.getName();
      
      // Check if it's a response JSON file (format: TICKER_YYYY-MM-DD_HH-MM-SS.json)
      if (fileName.endsWith('.json') && fileName.includes('_')) {
        const fileDateStr = fileName.match(/\d{4}-\d{2}-\d{2}/);
        if (fileDateStr) {
          const fileDate = new Date(fileDateStr[0]);
          if (fileDate < cutoffDate) {
            file.setTrashed(true);
            deletedCount++;
          }
        }
      }
    }
    
    // Clean up summary logs in summary folder
    const summaryFolder = DriveApp.getFolderById(getApiSummaryFolderId());
    const summaryFiles = summaryFolder.getFiles();
    
    while (summaryFiles.hasNext()) {
      const file = summaryFiles.next();
      const fileName = file.getName();
      
      // Check if it's a log or summary file
      if (fileName.startsWith('yahoo_api_log_') || fileName.startsWith('yahoo_api_summary_')) {
        const fileDateStr = fileName.match(/\d{4}-\d{2}-\d{2}/);
        if (fileDateStr) {
          const fileDate = new Date(fileDateStr[0]);
          if (fileDate < cutoffDate) {
            file.setTrashed(true);
            deletedCount++;
          }
        }
      }
    }
    
    if (deletedCount > 0) {
      console.log(`API LOG CLEANUP: Deleted ${deletedCount} old log/response files`);
      EW_trace('API_LOG', `Cleaned up ${deletedCount} old API log/response files`);
    }
    
    EW_safeAlert('Cleanup Complete', `Deleted ${deletedCount} files older than 30 days`);
    
  } catch (error) {
    console.error(`API LOG CLEANUP ERROR: ${error.message}`);
    EW_trace('API_LOG', `Failed to cleanup old logs: ${error.message}`);
  }
}

/**
 * Save the raw API response to a separate JSON file
 * @param {string} ticker - The ticker symbol
 * @param {string} timestamp - ISO timestamp
 * @param {Object} response - Raw API response
 * @param {Object} metadata - Additional metadata about the call
 */
function EW_saveApiResponse(ticker, timestamp, response, metadata = {}) {
  try {
    // Get the API logs folder
    const folderId = getApiLogFolderId();
    EW_trace('API_LOG', `Getting folder with ID: ${folderId}`);
    const folder = DriveApp.getFolderById(folderId);  // Main folder for detailed responses
    
    // Create filename with ticker and timestamp
    const date = new Date(timestamp);
    const dateStr = date.toISOString().split('T')[0];
    const timeStr = date.toISOString().split('T')[1].replace(/:/g, '-').split('.')[0];
    const fileName = `${ticker}_${dateStr}_${timeStr}.json`;
    
    EW_trace('API_LOG', `Creating file: ${fileName} in folder: ${folder.getName()}`);
    
    // Create response object with metadata
    const responseData = {
      metadata: {
        ticker: ticker,
        timestamp: timestamp,
        date: dateStr,
        interval: metadata.interval || '1m',
        targetPrice: metadata.targetPrice || null,
        success: metadata.success !== undefined ? metadata.success : true,
        dataPoints: metadata.dataPoints || 0,
        hitDetected: metadata.hitDetected || false,
        fallbackUsed: metadata.fallbackUsed || false
      },
      response: response
    };
    
    // Save the file to main folder
    const blob = Utilities.newBlob(JSON.stringify(responseData, null, 2), 'application/json', fileName);
    const file = folder.createFile(blob);
    
    console.log(`API RESPONSE SAVED: ${fileName} (ID: ${file.getId()})`);
    EW_trace('API_LOG', `Successfully saved API response to ${fileName}`);
    
  } catch (error) {
    console.error(`API RESPONSE SAVE ERROR: ${error.message}`);
    console.error(`Stack trace: ${error.stack}`);
    EW_trace('API_LOG', `Failed to save API response: ${error.message}`);
    // Don't throw - this is supplementary logging
  }
}

/**
 * Show API summary in a UI dialog
 */
function EW_showApiSummary() {
  try {
    const summary = EW_getApiCallSummary();
    if (summary.error) {
      EW_safeAlert('API Log Error', `Failed to get summary: ${summary.error}`);
      return;
    }
    
    let message = `API Call Summary for ${summary.date}\n\n`;
    message += `Total Calls: ${summary.totalCalls}\n`;
    message += `Successful: ${summary.byStatus.success}\n`;
    message += `Errors: ${summary.byStatus.error}\n`;
    message += `Fallbacks Used: ${summary.byStatus.fallback}\n\n`;
    
    message += `Calls by Interval:\n`;
    Object.entries(summary.byInterval).forEach(([interval, count]) => {
      message += `  ${interval}: ${count}\n`;
    });
    
    if (summary.fallbacks.length > 0) {
      message += `\nRecent Fallbacks:\n`;
      summary.fallbacks.slice(0, 5).forEach(fb => {
        message += `  ${fb.ticker}: ${fb.originalInterval} → ${fb.fallbackInterval}\n`;
      });
    }
    
    EW_safeAlert('API Call Summary', message);
    
  } catch (error) {
    console.error(`API SUMMARY ERROR: ${error.message}`);
    EW_safeAlert('Error', `Failed to show API summary: ${error.message}`);
  }
}

/**
 * Get the API folders URLs for easy access
 */
function EW_getApiResponsesFolderUrl() {
  try {
    const mainFolder = DriveApp.getFolderById(getApiLogFolderId());
    const summaryFolder = DriveApp.getFolderById(getApiSummaryFolderId());
    
    const mainUrl = mainFolder.getUrl();
    const summaryUrl = summaryFolder.getUrl();
    
    EW_safeAlert('API Logging Folders', 
      `Your API files are organized in two folders:\n\n` +
      `📁 Detailed Responses:\n${mainUrl}\n` +
      `Contains full JSON responses from each API call\n\n` +
      `📊 Summary Logs:\n${summaryUrl}\n` +
      `Contains daily summaries and statistics`
    );
    
    return { mainUrl, summaryUrl };
  } catch (error) {
    console.error(`API FOLDER ERROR: ${error.message}`);
    EW_safeAlert('Error', `Failed to get folder URLs: ${error.message}`);
  }
}

/**
 * Check if an API log already exists for a ticker and date
 * @param {string} ticker - The ticker symbol
 * @param {Date} date - The date to check
 * @returns {Object|null} The existing log data if found, null otherwise
 */
function EW_checkExistingApiLog(ticker, date) {
  try {
    const folderId = getApiLogFolderId();
    const folder = DriveApp.getFolderById(folderId);
    
    // Format date string
    const dateStr = date.toISOString().split('T')[0];
    const filePattern = `${ticker}_${dateStr}_`;
    
    // Search for existing files
    const files = folder.getFiles();
    while (files.hasNext()) {
      const file = files.next();
      const fileName = file.getName();
      
      // Check if this is a match for our ticker and date
      if (fileName.startsWith(filePattern) && fileName.endsWith('.json')) {
        // Skip RECREATED files as they might be incomplete
        if (fileName.includes('RECREATED')) {
          continue;
        }
        
        console.log(`Found existing API log: ${fileName}`);
        
        // Read and parse the file
        const content = file.getBlob().getDataAsString();
        const logData = JSON.parse(content);
        
        // Return the response data
        return logData;
      }
    }
    
    return null;
    
  } catch (error) {
    console.error(`Error checking existing API log: ${error.message}`);
    return null;
  }
}

/**
 * Get cached API data if available, otherwise return null
 * @param {string} ticker - The ticker symbol
 * @param {Date} date - The date to check
 * @returns {Object|null} Object with dayHigh, dayLow, etc. if found
 */
function EW_getCachedApiData(ticker, date) {
  try {
    const existingLog = EW_checkExistingApiLog(ticker, date);
    
    if (!existingLog) {
      return null;
    }
    
    // Extract the data from the log
    if (existingLog.response && existingLog.response.chart && existingLog.response.chart.result) {
      const result = existingLog.response.chart.result[0];
      if (result.indicators && result.indicators.quote && result.indicators.quote[0]) {
        const quote = result.indicators.quote[0];
        
        // Find the high and low for the day
        const highs = quote.high || [];
        const lows = quote.low || [];
        const opens = quote.open || [];
        const closes = quote.close || [];
        const volumes = quote.volume || [];
        
        // Get the day's data (aggregate if multiple data points)
        const dayHigh = highs.length > 0 ? Math.max(...highs.filter(h => h != null)) : null;
        const dayLow = lows.length > 0 ? Math.min(...lows.filter(l => l != null)) : null;
        const dayOpen = opens.length > 0 ? opens[0] : null;
        const dayClose = closes.length > 0 ? closes[closes.length - 1] : null;
        const dayVolume = volumes.length > 0 ? volumes.reduce((sum, v) => sum + (v || 0), 0) : 0;
        
        console.log(`Using cached data for ${ticker} on ${date.toISOString().split('T')[0]}`);
        
        return {
          dayHigh: dayHigh,
          dayLow: dayLow,
          dayOpen: dayOpen,
          dayClose: dayClose,
          dayVolume: dayVolume,
          fromCache: true,
          cacheFile: existingLog.metadata?.timestamp || 'cached'
        };
      }
    }
    
    // If we have metadata with day high/low (from recreated logs)
    if (existingLog.metadata) {
      const meta = existingLog.metadata;
      if (meta.dayHigh && meta.dayLow) {
        console.log(`Using cached metadata for ${ticker} on ${date.toISOString().split('T')[0]}`);
        return {
          dayHigh: meta.dayHigh,
          dayLow: meta.dayLow,
          dayOpen: meta.dayOpen || null,
          dayClose: meta.dayClose || null,
          dayVolume: meta.dayVolume || 0,
          fromCache: true,
          cacheFile: 'metadata'
        };
      }
    }
    
    return null;
    
  } catch (error) {
    console.error(`Error getting cached API data: ${error.message}`);
    return null;
  }
}

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