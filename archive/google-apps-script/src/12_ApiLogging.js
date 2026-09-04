/**
 * API Call Logging - Functions to log Yahoo Finance API calls to Google Drive
 * Stores detailed logs in JSON format for tracking and analysis
 *
 * PERFORMANCE OPTIMIZATIONS:
 * - Uses Drive search queries for specific file lookups
 * - Maintains file list cache for batch operations
 * - Avoids iterating through all files unnecessarily
 */

// File list caching for batch operations
let _cachedFileList = null;
let _cacheTimestamp = null;
const CACHE_LIFETIME_MS = 5 * 60 * 1000; // 5 minutes

/**
 * Get cached list of files in the API logs folder
 * Used for batch operations like checking multiple missing logs
 * @returns {Array} Array of file objects with name and id
 */
function EW_getCachedFileList(folderId) {
  const now = Date.now();

  // Check if cache is still valid
  if (_cachedFileList && _cacheTimestamp && (now - _cacheTimestamp) < CACHE_LIFETIME_MS) {
    console.log(`CACHE: Using cached file list (${_cachedFileList.length} files, age: ${Math.round((now - _cacheTimestamp)/1000)}s)`);
    return _cachedFileList;
  }

  // Refresh cache
  console.log('CACHE: Refreshing file list cache...');
  const startTime = new Date();
  _cachedFileList = [];

  try {
    const folder = DriveApp.getFolderById(folderId);
    const files = folder.getFiles();

    while (files.hasNext()) {
      const file = files.next();
      _cachedFileList.push({
        name: file.getName(),
        id: file.getId()
      });
    }

    _cacheTimestamp = now;
    const duration = new Date() - startTime;
    console.log(`CACHE: Refreshed file list (${_cachedFileList.length} files, took ${duration}ms)`);

    return _cachedFileList;
  } catch (error) {
    console.error(`CACHE ERROR: Failed to refresh file list: ${error.message}`);
    return [];
  }
}

/**
 * Clear the file list cache (useful after adding new files)
 */
function EW_clearFileListCache() {
  _cachedFileList = null;
  _cacheTimestamp = null;
  console.log('CACHE: File list cache cleared');
}

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
 * Validates file is not corrupted and recreates if needed
 * @param {boolean} forceNew - Force creation of new file (for corruption recovery)
 * @returns {Object} File object for today's log
 */
function EW_getApiLogFile(forceNew = false) {
  try {
    const folderId = getApiSummaryFolderId();
    console.log(`Attempting to access DAILY_REPORTS folder with ID: ${folderId}`);

    const folder = DriveApp.getFolderById(folderId);  // Use summary folder
    console.log(`Successfully accessed folder: ${folder.getName()}`);

    const today = new Date();
    const dateStr = Utilities.formatDate(today, Session.getScriptTimeZone(), 'yyyy-MM-dd');
    const fileName = `yahoo_api_log_${dateStr}.json`;
    console.log(`Looking for or creating file: ${fileName}`);

    // Check if today's log file already exists
    if (!forceNew) {
      const files = folder.getFilesByName(fileName);
      if (files.hasNext()) {
        const existingFile = files.next();
        console.log(`Found existing log file: ${existingFile.getName()}`);

        // Validate the file is not corrupted
        try {
          const content = existingFile.getBlob().getDataAsString();

          // Check if empty
          if (!content || content.trim().length === 0) {
            console.error(`API LOG: File is empty, will recreate`);
            existingFile.setTrashed(true);
            // Continue to create new file below
          } else {
            JSON.parse(content); // Will throw if corrupted JSON
            return existingFile;
          }
        } catch (parseError) {
          console.error(`API LOG: File corrupted - ${parseError.message}`);
          console.error(`Corruption reasons could be:`);
          console.error(`  1. Incomplete write (script timeout)`);
          console.error(`  2. Concurrent modification by multiple executions`);
          console.error(`  3. Drive sync issue`);
          console.error(`  4. Invalid JSON syntax`);

          // Delete the corrupted file
          existingFile.setTrashed(true);
          // Continue to create new file below
        }
      }
    }

    // Create new log file for today
    console.log(`Creating new log file: ${fileName}`);
    const initialData = {
      date: dateStr,
      created: Utilities.formatDate(today, Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss'),
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
    let logData;

    try {
      logData = JSON.parse(content);
    } catch (parseError) {
      // File is corrupted or empty - recreate it
      console.error(`API LOG ERROR: Corrupted log file detected, recreating: ${parseError.message}`);
      const today = new Date();
      const dateStr = Utilities.formatDate(today, Session.getScriptTimeZone(), 'yyyy-MM-dd');
      logData = {
        date: dateStr,
        created: Utilities.formatDate(today, Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss'),
        calls: [],
        note: 'File was corrupted and recreated'
      };
    }

    // Add timestamp to call data
    const now = new Date();
    callData.timestamp = Utilities.formatDate(now, Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss');

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
    const dateStr = Utilities.formatDate(date, Session.getScriptTimeZone(), 'yyyy-MM-dd');
    const fileName = `yahoo_api_log_${dateStr}.json`;
    
    const files = folder.getFilesByName(fileName);
    if (!files.hasNext()) {
      return { error: 'No log file found for this date' };
    }
    
    const file = files.next();
    const content = file.getBlob().getDataAsString();

    let logData;
    try {
      logData = JSON.parse(content);
    } catch (parseError) {
      console.error(`API SUMMARY ERROR: Corrupted log file: ${parseError.message}`);
      return { error: `Corrupted log file: ${parseError.message}` };
    }

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
    const dateStr = Utilities.formatDate(today, Session.getScriptTimeZone(), 'yyyy-MM-dd');
    const reportName = `yahoo_api_summary_${dateStr}.txt`;

    // Create report content
    let report = `Yahoo Finance API Call Summary\n`;
    report += `Date: ${summary.date}\n`;
    report += `Generated: ${Utilities.formatDate(today, Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss')}\n`;
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
 * Clean up old log files (keep last 180 days)
 */
function EW_cleanupOldApiLogs() {
  try {
    const cutoffDate = new Date();
    const retentionDays = 180;
    cutoffDate.setDate(cutoffDate.getDate() - retentionDays);
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
    
    EW_safeAlert('Cleanup Complete', `Deleted ${deletedCount} files older than ${retentionDays} days`);
    
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
    // Handle both ISO string timestamps and Date objects
    const date = typeof timestamp === 'string' && timestamp.match(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)
      ? new Date(timestamp.replace(' ', 'T'))
      : new Date(timestamp);

    // Use dateRequested from metadata if provided, otherwise use timestamp date
    // This allows cache files to be named by the data date, not the fetch date
    const dateStr = metadata.dateRequested || Utilities.formatDate(date, Session.getScriptTimeZone(), 'yyyy-MM-dd');
    const timeStr = Utilities.formatDate(date, Session.getScriptTimeZone(), 'HH-mm-ss');
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

    // Clear the file list cache after adding a new file
    EW_clearFileListCache();

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
 * OPTIMIZED: Uses Drive search query to find specific files
 * @param {string} ticker - The ticker symbol
 * @param {Date} date - The date to check
 * @returns {Object|null} The existing log data if found, null otherwise
 */
function EW_checkExistingApiLog(ticker, date) {
  try {
    const folderId = getApiLogFolderId();
    const folder = DriveApp.getFolderById(folderId);

    // Format date string
    const dateStr = Utilities.formatDate(date, Session.getScriptTimeZone(), 'yyyy-MM-dd');
    const filePattern = `${ticker}_${dateStr}`;

    // Use Drive's search to find specific files
    // Search for files with name containing the pattern
    const searchQuery = `title contains '${filePattern}' and mimeType = 'application/json' and trashed = false`;
    console.log(`CACHE: Searching for API log with pattern: ${filePattern}`);

    // Search specifically in this folder
    const files = folder.searchFiles(searchQuery);

    // Check the results
    while (files.hasNext()) {
      const file = files.next();
      const fileName = file.getName();

      // Verify it matches our exact pattern (starts with ticker_date and ends with .json)
      if (fileName.startsWith(`${filePattern}_`) && fileName.endsWith('.json')) {
        // Skip RECREATED files as they might be incomplete
        if (fileName.includes('RECREATED')) {
          continue;
        }

        console.log(`Found existing API log: ${fileName}`);

        // STEP 1: Read and parse the file with JSON validation
        let logData;
        try {
          const content = file.getBlob().getDataAsString();
          logData = JSON.parse(content);
        } catch (parseError) {
          console.log(`CACHE REJECTED: ${fileName} - Corrupted JSON: ${parseError.message}. Deleting file.`);
          file.setTrashed(true);
          continue; // Try next file
        }

        // STEP 2: Validate completeness of data structure
        if (!logData.response) {
          console.log(`CACHE REJECTED: ${fileName} - Missing response object. Deleting file.`);
          file.setTrashed(true);
          continue;
        }

        if (!logData.response.chart) {
          console.log(`CACHE REJECTED: ${fileName} - Missing chart object. Deleting file.`);
          file.setTrashed(true);
          continue;
        }

        if (!logData.response.chart.result || !Array.isArray(logData.response.chart.result) || logData.response.chart.result.length === 0) {
          console.log(`CACHE REJECTED: ${fileName} - Missing or empty result array. Deleting file.`);
          file.setTrashed(true);
          continue;
        }

        const result = logData.response.chart.result[0];

        if (!result.timestamp || !Array.isArray(result.timestamp) || result.timestamp.length === 0) {
          console.log(`CACHE REJECTED: ${fileName} - Missing or empty timestamp array. Deleting file.`);
          file.setTrashed(true);
          continue;
        }

        if (!result.indicators || !result.indicators.quote || !Array.isArray(result.indicators.quote) || result.indicators.quote.length === 0) {
          console.log(`CACHE REJECTED: ${fileName} - Missing or empty quote data. Deleting file.`);
          file.setTrashed(true);
          continue;
        }

        const quote = result.indicators.quote[0];
        const requiredFields = ['open', 'high', 'low', 'close', 'volume'];
        const missingFields = requiredFields.filter(field => !quote[field] || quote[field].length === 0);

        if (missingFields.length > 0) {
          console.log(`CACHE REJECTED: ${fileName} - Missing required quote fields: ${missingFields.join(', ')}. Deleting file.`);
          file.setTrashed(true);
          continue;
        }

        // STEP 3: Check for API errors in metadata
        if (logData.metadata && logData.metadata.success === false) {
          console.log(`CACHE REJECTED: ${fileName} - Metadata indicates API failure. Deleting file.`);
          file.setTrashed(true);
          continue;
        }

        if (logData.response.chart.error) {
          console.log(`CACHE REJECTED: ${fileName} - Contains API error: ${JSON.stringify(logData.response.chart.error)}. Deleting file.`);
          file.setTrashed(true);
          continue;
        }

        // STEP 4: Validate the cached data actually contains the requested date
        // The filename might say 2025-09-22, but the actual data might be from 2025-09-23+
        // This happens when Yahoo no longer has data for the requested date
        const firstTimestamp = result.timestamp[0] * 1000; // Convert to milliseconds
        const lastTimestamp = result.timestamp[result.timestamp.length - 1] * 1000;
        const firstDataDate = new Date(firstTimestamp);
        const lastDataDate = new Date(lastTimestamp);

        // Normalize both dates to midnight for comparison
        const requestedDate = new Date(date);
        requestedDate.setHours(0, 0, 0, 0);
        const actualDate = new Date(firstDataDate);
        actualDate.setHours(0, 0, 0, 0);

        // If the actual data is for a different date than requested, delete and skip
        if (actualDate.getTime() !== requestedDate.getTime()) {
          console.log(`CACHE REJECTED: ${fileName} - Date mismatch: contains data for ${actualDate.toISOString().split('T')[0]}, not ${dateStr}. Deleting file.`);
          file.setTrashed(true);
          continue; // Try next file
        }

        // STEP 5: Log success and return validated data
        const dataRangeStr = `${firstDataDate.toISOString().split('T')[0]} to ${lastDataDate.toISOString().split('T')[0]}`;
        const dataPointCount = result.timestamp.length;
        console.log(`CACHE ACCEPTED: ${fileName} - Valid data with ${dataPointCount} points spanning ${dataRangeStr}`);

        return logData;
      }
    }

    // No matching file found
    console.log(`CACHE: No API log found for ${ticker} on ${dateStr}`);
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
        
        const dateStr = Utilities.formatDate(date, Session.getScriptTimeZone(), 'yyyy-MM-dd');
        console.log(`Using cached data for ${ticker} on ${dateStr}`);
        
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
        const dateStr = Utilities.formatDate(date, Session.getScriptTimeZone(), 'yyyy-MM-dd');
        console.log(`Using cached metadata for ${ticker} on ${dateStr}`);
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
  
  // Get all existing log files using cached list for batch operation
  const fileList = EW_getCachedFileList(apiLogsFolder.getId());
  const existingFiles = new Set(fileList.map(f => f.name));
  console.log(`Found ${existingFiles.size} existing API log files in cache`);
  
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
      const dateStr = Utilities.formatDate(checkDate, Session.getScriptTimeZone(), 'yyyy-MM-dd');
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
          const now = new Date();
          const logEntry = {
            ticker: ticker,
            timestamp: Utilities.formatDate(now, Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss'),
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
            recreatedAt: Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss'),
            originalRunDate: Utilities.formatDate(log.runDate, Session.getScriptTimeZone(), 'yyyy-MM-dd'),
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
    const now = new Date();
    const dateStr = Utilities.formatDate(date, Session.getScriptTimeZone(), 'yyyy-MM-dd');
    const timeStr = Utilities.formatDate(now, Session.getScriptTimeZone(), 'HH-mm-ss');
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

    // Clear the file list cache after adding a new file
    EW_clearFileListCache();

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
 * Test the cache performance improvements
 * Compares old vs new cache checking methods
 */
function EW_testCachePerformance() {
  console.log('===== TESTING CACHE PERFORMANCE =====');

  const ticker = 'AAPL';
  const testDate = new Date('2025-09-25');

  // Test 1: New optimized method (Drive search)
  const start1 = new Date();
  const result1 = EW_checkExistingApiLog(ticker, testDate);
  const duration1 = new Date() - start1;
  console.log(`NEW METHOD (Drive search): ${duration1}ms - Found: ${!!result1}`);

  // Test 2: Cached file list method (for batch operations)
  const start2 = new Date();
  const folderId = getApiLogFolderId();
  const fileList = EW_getCachedFileList(folderId);
  const duration2 = new Date() - start2;
  console.log(`CACHED LIST METHOD: ${duration2}ms - Files in cache: ${fileList.length}`);

  // Test 3: Second call to cached list (should be instant)
  const start3 = new Date();
  const fileList2 = EW_getCachedFileList(folderId);
  const duration3 = new Date() - start3;
  console.log(`CACHED LIST (2nd call): ${duration3}ms - Files: ${fileList2.length}`);

  // Summary
  console.log('\n===== PERFORMANCE SUMMARY =====');
  console.log(`Drive Search Query: ${duration1}ms`);
  console.log(`File List Cache (1st): ${duration2}ms`);
  console.log(`File List Cache (2nd): ${duration3}ms`);
  console.log(`Cache speedup: ${Math.round(duration2/duration3)}x faster on cached calls`);

  return {
    driveSearch: duration1,
    cacheFirst: duration2,
    cacheSecond: duration3,
    speedup: Math.round(duration2/duration3)
  };
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
  
  // Get existing files using cached list for batch operation
  const fileList = EW_getCachedFileList(apiLogsFolder.getId());
  const existingFiles = new Set(fileList.map(f => f.name));
  
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

      const dateStr = Utilities.formatDate(checkDate, Session.getScriptTimeZone(), 'yyyy-MM-dd');
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