/**
 * API Call Logging - Functions to log Yahoo Finance API calls to Google Drive
 * Stores detailed logs in JSON format for tracking and analysis
 */

// Drive folder ID for storing logs
const API_LOG_FOLDER_ID = '1fUcRfi6y-JoWPlMO2jGAJOutapihfUUd';

/**
 * Initialize or get today's API log file
 * @returns {Object} File object for today's log
 */
function EW_getApiLogFile() {
  try {
    const folder = DriveApp.getFolderById(API_LOG_FOLDER_ID);
    const today = new Date();
    const fileName = `yahoo_api_log_${today.toISOString().split('T')[0]}.json`;
    
    // Check if today's log file already exists
    const files = folder.getFilesByName(fileName);
    if (files.hasNext()) {
      return files.next();
    }
    
    // Create new log file for today
    const initialData = {
      date: today.toISOString().split('T')[0],
      created: today.toISOString(),
      calls: []
    };
    
    const blob = Utilities.newBlob(JSON.stringify(initialData, null, 2), 'application/json', fileName);
    return folder.createFile(blob);
    
  } catch (error) {
    console.error(`API LOG ERROR: Failed to get/create log file: ${error.message}`);
    EW_trace('API_LOG', `Failed to get/create log file: ${error.message}`);
    return null;
  }
}

/**
 * Log an API call to the JSON file
 * @param {Object} callData - Data about the API call
 */
function EW_logApiCall(callData) {
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
    const folder = DriveApp.getFolderById(API_LOG_FOLDER_ID);
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
    
    const folder = DriveApp.getFolderById(API_LOG_FOLDER_ID);
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
    const folder = DriveApp.getFolderById(API_LOG_FOLDER_ID);
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - 30);
    
    const files = folder.getFiles();
    let deletedCount = 0;
    
    while (files.hasNext()) {
      const file = files.next();
      const fileName = file.getName();
      
      // Check if it's a log file
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
      console.log(`API LOG CLEANUP: Deleted ${deletedCount} old log files`);
      EW_trace('API_LOG', `Cleaned up ${deletedCount} old API log files`);
    }
    
  } catch (error) {
    console.error(`API LOG CLEANUP ERROR: ${error.message}`);
    EW_trace('API_LOG', `Failed to cleanup old logs: ${error.message}`);
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