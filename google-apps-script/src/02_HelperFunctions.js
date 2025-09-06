/**
 * Helper Functions and Utilities
 * Common utility functions used across the EarningsWhispers system
 */

// ======= URL AND STRING UTILITIES =======

/**
 * Build full URL from path
 * @param {string} path - API path or full URL
 * @returns {string} Full URL
 */
function EW_url(path) {
  if (/^https?:\/\//i.test(path)) return path;
  return EW.BASE.replace(/\/+$/, '') + '/' + path.replace(/^\/+/, '');
}

/**
 * Normalize strings for comparison
 * @param {string} s - String to normalize
 * @returns {string} Normalized string
 */
/**
 * Normalizes string for comparison (lowercase, trimmed)
 * Used for case-insensitive string matching
 * @param {string} s - String to normalize
 * @returns {string} Normalized string
 */
function EW_norm(s) {
  if (typeof s !== 'string') return '';
  return s.toString()
    .replace(/["']/g, '')       // Remove quotes
    .replace(/\s+/g, ' ')       // Normalize whitespace
    .replace(/[^\w\s.-]/g, '')  // Keep only word chars, spaces, dots, hyphens
    .toLowerCase()              // Convert to lowercase for case-insensitive matching
    .trim();
}

// ======= DATE AND TIME UTILITIES =======

/**
 * Convert UTC Date to EDT/EST string
 * @param {Date} date - UTC date to convert
 * @returns {string} Formatted EDT/EST datetime string
 */
function EW_toEDT(date) {
  if (!date || !(date instanceof Date)) return '';
  
  // Create formatter for Eastern Time
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  });
  
  const parts = formatter.formatToParts(date);
  const values = {};
  parts.forEach(part => {
    values[part.type] = part.value;
  });
  
  // Format as YYYY-MM-DD HH:MM:SS EDT
  return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second} ET`;
}

// ======= LOGGING AND DEBUGGING =======

/**
 * Super-logger: console + Logger + optional Log sheet
 * @param {string} scope - Log scope/category
 * @param {string} msg - Log message
 * @param {boolean} alsoSheet - Also write to Log sheet
 */
/**
 * Enhanced standardized logging function
 * @param {string} scope - Log category/scope (e.g., 'API', 'ERROR', 'INFO', 'BACKFILL')
 * @param {string} msg - Log message
 * @param {boolean} alsoSheet - Whether to log to sheet (default: false)
 * @param {string} level - Log level: 'ERROR', 'WARN', 'INFO', 'DEBUG' (default: 'INFO')
 */
function EW_trace(scope, msg, alsoSheet = false, level = 'INFO') {
  const timestamp = new Date().toISOString();
  const line = `[${timestamp}] [${level}] [${scope}] ${msg}`;
  
  // Always log to console with appropriate method
  try {
    switch(level) {
      case 'ERROR':
        console.error(line);
        break;
      case 'WARN':
        console.warn(line);
        break;
      case 'DEBUG':
        // Only log debug messages if debug mode is enabled
        if (EW.DEBUG_MODE || false) {
          console.log(line);
        }
        break;
      default:
        console.log(line);
    }
  } catch (_) {}
  
  // Also log to Google's Logger for Stackdriver
  try {
    Logger.log(line);
  } catch (_) {}
  
  // Log to sheet if requested and in spreadsheet environment
  if (alsoSheet && EW_isSpreadsheetEnvironment()) {
    try {
      const ss = SpreadsheetApp.getActive();
      let log = ss.getSheetByName('Log');
      if (!log) log = ss.insertSheet('Log');
      
      // Add level column for better filtering
      log.appendRow([new Date(), level, scope, msg]);
      
      // Keep log sheet size manageable (max 5000 rows)
      if (log.getLastRow() > 5000) {
        log.deleteRows(2, 1000); // Delete oldest 1000 rows (keep header)
      }
    } catch (e) {
      // Use console.error directly to avoid recursion
      console.error('Failed to write to Log sheet:', e.message);
    }
  }
  
  // For errors, also track in properties for debugging
  if (level === 'ERROR') {
    try {
      EW_trackError(scope, msg);
    } catch (_) {}
  }
}

/**
 * Track errors in ScriptProperties for debugging
 * @param {string} scope - Error scope
 * @param {string} msg - Error message
 */
function EW_trackError(scope, msg) {
  try {
    const scriptProperties = PropertiesService.getScriptProperties();
    const errors = JSON.parse(scriptProperties.getProperty('ERROR_LOG') || '[]');
    
    errors.push({
      timestamp: new Date().toISOString(),
      scope: scope,
      message: msg
    });
    
    // Keep only last 100 errors
    if (errors.length > 100) {
      errors.splice(0, errors.length - 100);
    }
    
    scriptProperties.setProperty('ERROR_LOG', JSON.stringify(errors));
  } catch (e) {
    // Silent fail - don't want error tracking to cause errors
  }
}

/**
 * Summarize JSON object for logging
 * @param {Object} j - JSON object to summarize
 * @returns {string} Summary string
 */
function EW_summarizeJson(j) {
  if (!j || typeof j !== 'object') return 'null/non-object';
  try {
    const keys = Object.keys(j);
    return `{${keys.length} keys: ${keys.slice(0, 3).join(', ')}${keys.length > 3 ? '...' : ''}}`;
  } catch (e) {
    return 'error-summarizing';
  }
}

// ======= SPREADSHEET UTILITIES =======

/**
 * Convert column number to letter (A, B, C, ..., AA, AB, etc.)
 * @param {number} col - Column number (1-based)
 * @returns {string} Column letter
 */
function EW_columnToLetter(col) {
  let s = '';
  while (col > 0) {
    const m = (col - 1) % 26;
    s = String.fromCharCode(65 + m) + s;
    col = Math.floor((col - 1) / 26);
  }
  return s;
}

/**
 * Get timestamp for current run
 * @returns {string} Formatted timestamp
 */
function EW_getRunStamp() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss');
}

/**
 * Ensure "Run Date" is first header column
 * @param {Array} header - Header array
 * @returns {Array} Header with Run Date first
 */
function EW_ensureRunDateInHeader(header) {
  const ix = header.findIndex(h => String(h).toLowerCase() === 'run date');
  if (ix === 0) return header;
  if (ix > 0) {
    const copy = header.slice();
    const [rd] = copy.splice(ix, 1);
    return [rd, ...copy];
  }
  return ['Run Date', ...header];
}

/**
 * Ensure required columns (Run Date, Strategy) are in header
 * @param {Array} header - Header array
 * @param {string} strategyName - Strategy name for the sheet
 * @returns {Array} Header with required columns
 */
function EW_ensureRequiredHeaders(header, strategyName) {
  let result = [...header];
  
  // Ensure Run Date is first
  const runDateIx = result.findIndex(h => String(h).toLowerCase() === 'run date');
  if (runDateIx === -1) {
    result = ['Run Date', ...result];
  } else if (runDateIx > 0) {
    const [rd] = result.splice(runDateIx, 1);
    result = [rd, ...result];
  }
  
  // Ensure Strategy is second
  const strategyIx = result.findIndex(h => String(h).toLowerCase() === 'strategy');
  if (strategyIx === -1) {
    // Insert Strategy as second column
    result.splice(1, 0, 'Strategy');
  } else if (strategyIx !== 1) {
    // Move it to position 1
    const [strat] = result.splice(strategyIx, 1);
    result.splice(1, 0, strat);
  }
  
  return result;
}

/**
 * Add Google Finance headers to existing header
 * @param {Array} header - Original header
 * @returns {Array} Header with GF columns added
 */
function EW_addGFHeaders(header) {
  const gfHeaders = [
    'Days_To_Exp', 'HV_30D', 'RVOL_10D', 'Strike_Hit', 
    'Success_Score', 'Historical_High', 'Historical_Low', 'Ever_Hit_Strike',
    'First_Hit_Date', 'Last_Update', 'Total_Hit_Days', 'Peak_Profit_Date'
  ];
  return [...header, ...gfHeaders];
}

/**
 * Get all headers from each options strategy sheet
 * Returns a 2D array showing sheet names and their headers for debugging/analysis
 * Useful for verifying column consistency across different strategy sheets
 * @returns {Array} 2D array with [sheet name, headers] for each strategy sheet
 */
function getOptionsSheetHeaders() {
  const sheets = [
    'Long Calls', 'Bull Spreads', 'Covered Calls',
    'Long Puts', 'Bear Spreads', 'Short Calls', 
    'Strangles', 'Straddles', 'Short Puts'
  ];
  
  const result = [["Sheet Name", "Headers"]];
  
  console.log('=== Options Sheet Headers Analysis ===');
  
  sheets.forEach(sheetName => {
    try {
      const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(sheetName);
      if (sheet) {
        const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
        const headerText = headers.filter(h => h !== "").join(" | ");
        result.push([sheetName, headerText]);
        
        // Console logging
        console.log(`\n${sheetName}:`);
        console.log(`  Total columns: ${headers.length}`);
        console.log(`  Non-empty columns: ${headers.filter(h => h !== "").length}`);
        console.log(`  Headers: ${headerText}`);
        
        // Check for critical columns
        const hasStrikeHit = headers.some(h => h === 'Strike_Hit');
        const hasStrategy = headers.some(h => h === 'Strategy');
        const hasRunDate = headers.some(h => h === 'Run Date');
        
        if (!hasStrikeHit) console.log(`  ⚠️ WARNING: Missing Strike_Hit column`);
        if (!hasStrategy) console.log(`  ⚠️ WARNING: Missing Strategy column`);
        if (!hasRunDate) console.log(`  ⚠️ WARNING: Missing Run Date column`);
        
      } else {
        result.push([sheetName, "Sheet not found"]);
        console.log(`\n${sheetName}: ❌ Sheet not found`);
      }
    } catch (e) {
      result.push([sheetName, "Error: " + e.toString()]);
      console.log(`\n${sheetName}: ❌ Error - ${e.toString()}`);
    }
  });
  
  console.log('\n=== Summary ===');
  console.log(`Total sheets checked: ${sheets.length}`);
  console.log(`Sheets found: ${result.filter(r => r[1] !== "Sheet not found" && !r[1].startsWith("Error")).length - 1}`);
  
  return result;
}

// ======= COOKIE AND SESSION UTILITIES =======

/**
 * Merge two cookie objects
 * @param {Object} a - First cookie object
 * @param {Object} b - Second cookie object  
 * @returns {Object} Merged cookies
 */
function EW_mergeCookies(a, b) { 
  return Object.assign({}, a || {}, b || {}); 
}

/**
 * Convert cookie object to header string
 * @param {Object} obj - Cookie object
 * @returns {string} Cookie header string
 */
function EW_cookieHeader(obj) { 
  return Object.entries(obj || {}).map(([k, v]) => `${k}=${v}`).join('; '); 
}

/**
 * Extract CSRF token from HTML
 * @param {string} html - HTML content
 * @returns {string} CSRF token or empty string
 */
function EW_extractCsrf(html) {
  if (!html || typeof html !== 'string') return '';
  try {
    // Look for csrf-token in meta tags (Laravel style)
    let m = html.match(/<meta\s+name=["']?csrf-token["']?\s+content=["']?([^"'>\s]+)/i);
    if (m && m[1]) {
      EW_trace('CSRF', `Found CSRF token in meta tag: ${m[1].substring(0, 8)}...`);
      return m[1];
    }
    
    // Look for _token in hidden inputs (Laravel style)
    m = html.match(/<input[^>]+name=["']?_token["']?[^>]+value=["']?([^"'>\s]+)/i);
    if (m && m[1]) {
      EW_trace('CSRF', `Found CSRF token in hidden input: ${m[1].substring(0, 8)}...`);
      return m[1];
    }
    
    // Look for __RequestVerificationToken (ASP.NET style)
    m = html.match(/<input[^>]+name=["']?__RequestVerificationToken["']?[^>]+value=["']?([^"'>\s]+)/i);
    if (m && m[1]) {
      EW_trace('CSRF', `Found ASP.NET verification token: ${m[1].substring(0, 8)}...`);
      return m[1];
    }
    
    // Alternative pattern for _token
    m = html.match(/name=["']?_token["']?[^>]+value=["']?([^"'>\s]+)/i);
    if (m && m[1]) {
      EW_trace('CSRF', `Found CSRF token (alt pattern): ${m[1].substring(0, 8)}...`);
      return m[1];
    }
    
    // Look for form token in any input
    m = html.match(/<input[^>]+name=["']?[^"']*token[^"']*["']?[^>]+value=["']?([^"'>\s]+)/i);
    if (m && m[1]) {
      EW_trace('CSRF', `Found generic token: ${m[1].substring(0, 8)}...`);
      return m[1];
    }
    
    EW_trace('CSRF', 'No CSRF token found in HTML');
    return '';
  } catch (e) {
    EW_trace('CSRF', `Error extracting CSRF: ${e}`);
    return '';
  }
}

/**
 * Collect Set-Cookie headers from response
 * @param {HTTPResponse} res - HTTP response object
 * @returns {Object} Cookie object
 */
function EW_collectSetCookies(res) {
  const cookies = {};
  const headers = res.getAllHeaders();
  const setCookieHeaders = headers['Set-Cookie'] || headers['set-cookie'] || [];
  
  (Array.isArray(setCookieHeaders) ? setCookieHeaders : [setCookieHeaders])
    .forEach(header => {
      if (header) {
        const [nameValue] = header.split(';');
        const [name, value] = nameValue.split('=');
        if (name && value) {
          cookies[name.trim()] = value.trim();
        }
      }
    });
  
  return cookies;
}

// ======= DATA VALIDATION UTILITIES =======

/**
 * Validate strategy name
 * @param {string} strategy - Strategy name to validate
 * @returns {boolean} True if valid strategy
 */
function EW_isValidStrategy(strategy) {
  return Object.keys(EW.STRATEGY_ENDPOINTS).includes(strategy);
}

/**
 * Get strategy type (bullish, bearish, etc.)
 * @param {string} strategy - Strategy name
 * @returns {string} Strategy type
 */
function EW_getStrategyType(strategy) {
  for (const [type, strategies] of Object.entries(EW_STRATEGY_TYPES)) {
    if (strategies.includes(strategy)) {
      return type.toLowerCase();
    }
  }
  return 'unknown';
}

/**
 * Check if a strategy is a spread (has multiple strikes)
 * @param {string} strategy - Strategy name
 * @returns {boolean} True if strategy is a spread
 */
function EW_isSpreadStrategy(strategy) {
  if (!strategy) return false;
  const strategyUpper = strategy.toUpperCase();
  return strategyUpper.includes('SPREAD') || 
         strategyUpper.includes('STRANGLE') || 
         strategyUpper.includes('STRADDLE') ||
         strategyUpper.includes('IRON CONDOR') ||
         strategyUpper.includes('BUTTERFLY');
}

/**
 * Get strike columns for a strategy
 * @param {string} strategy - Strategy name
 * @returns {Object} Object with strike column names
 */
function EW_getStrikeColumns(strategy) {
  if (EW_isSpreadStrategy(strategy)) {
    return {
      primary: 'longStrike',
      secondary: 'shortStrike',
      isSpread: true
    };
  } else {
    return {
      primary: 'strike',
      secondary: null,
      isSpread: false
    };
  }
}

/**
 * Validate date string
 * @param {string} dateStr - Date string to validate
 * @returns {boolean} True if valid date
 */
function EW_isValidDate(dateStr) {
  if (!dateStr) return false;
  const date = new Date(dateStr);
  return date instanceof Date && !isNaN(date);
}

/**
 * Parse numeric value safely
 * @param {any} value - Value to parse
 * @returns {number|null} Parsed number or null
 */
function EW_parseNumber(value) {
  if (value === null || value === undefined || value === '') return null;
  const num = Number(value);
  return isNaN(num) ? null : num;
}

// ======= ERROR HANDLING UTILITIES =======

/**
 * Create standardized error object
 * @param {string} code - Error code
 * @param {string} message - Error message
 * @param {Object} details - Additional error details
 * @returns {Object} Error object
 */
function EW_createError(code, message, details = {}) {
  return {
    code,
    message,
    details,
    timestamp: new Date().toISOString()
  };
}

/**
 * Handle API response errors
 * @param {HTTPResponse} response - HTTP response
 * @param {string} context - Context where error occurred
 * @returns {Object|null} Error object or null if no error
 */
function EW_handleResponseError(response, context = 'API call') {
  if (!response) {
    return EW_createError(EW_ERRORS.INVALID_RESPONSE, 'No response received', { context });
  }
  
  const code = response.getResponseCode();
  if (code >= 400) {
    return EW_createError(EW_ERRORS.API_TIMEOUT, `HTTP ${code} error`, { 
      context, 
      statusCode: code,
      response: response.getContentText()?.substring(0, 500) 
    });
  }
  
  return null;
}

// ======= BATCH PROCESSING UTILITIES =======

/**
 * Process array in batches
 * @param {Array} array - Array to process
 * @param {number} batchSize - Size of each batch
 * @param {Function} processor - Function to process each batch
 * @returns {Array} Results from all batches
 */
function EW_processBatches(array, batchSize, processor) {
  const results = [];
  for (let i = 0; i < array.length; i += batchSize) {
    const batch = array.slice(i, i + batchSize);
    const batchResult = processor(batch, i);
    results.push(batchResult);
  }
  return results;
}

/**
 * Get trigger information for debugging
 * @param {string} functionName - Function name to check
 * @returns {Object|null} Trigger info or null if not found
 */
function EW_getTriggerInfo(functionName) {
  try {
    const triggers = ScriptApp.getProjectTriggers();
    const trigger = triggers.find(t => t.getHandlerFunction() === functionName);
    
    if (!trigger) return null;
    
    return {
      handlerFunction: trigger.getHandlerFunction(),
      eventType: trigger.getEventType().toString(),
      triggerSource: trigger.getTriggerSource().toString(),
      triggerId: trigger.getUniqueId()
    };
  } catch (error) {
    EW_trace('HELPER', `Error getting trigger info for ${functionName}: ${error}`);
    return null;
  }
}

/**
 * Check if running in spreadsheet environment (UI available)
 * @returns {boolean} True if UI is available
 */
function EW_isSpreadsheetEnvironment() {
  try {
    return typeof SpreadsheetApp !== 'undefined' && 
           SpreadsheetApp.getActiveSpreadsheet && 
           SpreadsheetApp.getActiveSpreadsheet() !== null;
  } catch (error) {
    return false;
  }
}

/**
 * Show UI alert only if in spreadsheet environment
 * @param {string} title - Alert title
 * @param {string} message - Alert message
 * @param {Object} buttonSet - Button set (optional)
 * @returns {Object|null} Button response or null if no UI
 */
function EW_safeAlert(title, message, buttonSet = null) {
  try {
    // Ensure parameters are strings
    const safeTitle = String(title || 'Alert');
    const safeMessage = String(message || '');
    
    if (EW_isSpreadsheetEnvironment()) {
      const ui = SpreadsheetApp.getUi();
      if (buttonSet) {
        return ui.alert(safeTitle, safeMessage, buttonSet);
      } else {
        // Use single parameter alert as fallback
        try {
          return ui.alert(safeTitle, safeMessage);
        } catch (e) {
          // Fallback to single parameter if two-parameter fails
          return ui.alert(safeTitle + ': ' + safeMessage);
        }
      }
    } else {
      console.log(`[UI Alert] ${safeTitle}: ${safeMessage}`);
      return null;
    }
  } catch (error) {
    console.log(`[UI Alert Failed] ${title}: ${message}`);
    EW_trace('UI', `Alert failed: ${error.toString()}`);
    return null;
  }
}

/**
 * Safe alert with Yes/No buttons
 * @param {string} title - Alert title
 * @param {string} message - Alert message
 * @returns {string|null} Button clicked or null if not in spreadsheet environment
 */
function EW_safeConfirm(title, message) {
  try {
    if (EW_isSpreadsheetEnvironment()) {
      const response = SpreadsheetApp.getUi().alert(title, message, SpreadsheetApp.getUi().ButtonSet.YES_NO);
      return response === SpreadsheetApp.getUi().Button.YES ? 'YES' : 'NO';
    } else {
      console.log(`[UI Confirm] ${title}: ${message} [Auto: YES in script environment]`);
      return 'YES'; // Default to YES in script environment
    }
  } catch (error) {
    console.log(`[UI Confirm Failed] ${title}: ${message} [Auto: YES due to error]`);
    EW_trace('UI', `Confirm failed: ${error.toString()}`);
    return 'YES'; // Default to YES on error
  }
}

/**
 * Check if a specific trigger exists
 * @param {string} functionName - Function name to check
 * @returns {boolean} True if trigger exists
 */
function EW_triggerExists(functionName) {
  try {
    const triggers = ScriptApp.getProjectTriggers();
    return triggers.some(t => t.getHandlerFunction() === functionName);
  } catch (error) {
    EW_trace('HELPER', `Error checking trigger existence for ${functionName}: ${error}`);
    return false;
  }
}

/**
 * Retry function with exponential backoff
 * @param {Function} fn - Function to retry
 * @param {number} maxRetries - Maximum retry attempts
 * @param {number} delay - Initial delay in ms
 * @returns {any} Function result
 */
function EW_retryWithBackoff(fn, maxRetries = EW_DEFAULTS.MAX_RETRIES, delay = 1000) {
  let attempts = 0;
  
  function attempt() {
    try {
      return fn();
    } catch (error) {
      attempts++;
      if (attempts >= maxRetries) {
        throw error;
      }
      
      const backoffDelay = delay * Math.pow(2, attempts - 1);
      EW_trace('RETRY', `Attempt ${attempts} failed, retrying in ${backoffDelay}ms`);
      Utilities.sleep(backoffDelay);
      return attempt();
    }
  }
  
  return attempt();
}

/**
 * Parse Strike_Hit array from cell value
 * Handles both array format and legacy single values
 * @param {string|Array} value - Cell value
 * @returns {Array} Array of strike hit values
 */
function EW_parseStrikeHitArray(value) {
  if (!value) return [];
  
  // If already an array, return it
  if (Array.isArray(value)) return value;
  
  // If JSON string, parse it
  if (typeof value === 'string' && value.startsWith('[')) {
    try {
      return JSON.parse(value);
    } catch (e) {
      console.log('Failed to parse Strike_Hit array:', e);
      return [value]; // Fallback to single value
    }
  }
  
  // Handle comma-separated format
  if (typeof value === 'string' && value.includes(',')) {
    return value.split(',').map(v => v.trim());
  }
  
  // Handle legacy single value
  return [value];
}

/**
 * Append new value to Strike_Hit array
 * @param {string|Array} currentValue - Current cell value
 * @param {string} newValue - New value to append
 * @returns {string} JSON string of updated array
 */
function EW_appendStrikeHit(currentValue, newValue) {
  const array = EW_parseStrikeHitArray(currentValue);
  array.push(newValue);
  return JSON.stringify(array);
}

/**
 * Get Strike_Hit value for specific day
 * @param {string|Array} strikeHitValue - Strike_Hit cell value
 * @param {number} dayIndex - Day index (0-based)
 * @returns {string|null} Strike hit value for that day
 */
function EW_getStrikeHitForDay(strikeHitValue, dayIndex) {
  const array = EW_parseStrikeHitArray(strikeHitValue);
  return array[dayIndex] || null;
}

/**
 * Check if indicators should be recalculated based on price history
 * Uses "high water mark" approach - only recalculate when current price exceeds all previous prices
 * @param {Array<number>} priceHistory - Array of daily closing prices
 * @returns {boolean} True if indicators should be recalculated
 */
function EW_shouldRecalculateIndicators(priceHistory) {
  if (!priceHistory || priceHistory.length < 2) return true;
  
  const currentPrice = priceHistory[priceHistory.length - 1];
  const previousPrices = priceHistory.slice(0, -1);
  const highWaterMark = Math.max(...previousPrices);
  
  return currentPrice > highWaterMark;
}

/**
 * Track price history for a position
 * @param {Object} row - Row data
 * @param {Object} hdrMap - Header mapping
 * @returns {Array<number>} Array of daily prices
 */
function EW_getPriceHistory(row, hdrMap) {
  const priceHistory = [];
  
  // Extract prices from Day0_Check through Day5_Check
  const dayChecks = [
    hdrMap.day0CheckCol,
    hdrMap.day1CheckCol,
    hdrMap.day2CheckCol,
    hdrMap.day3CheckCol,
    hdrMap.day4CheckCol,
    hdrMap.day5CheckCol
  ];
  
  for (const col of dayChecks) {
    if (col) {
      const value = row[col - 1];
      if (value && value !== null && value !== '') {
        const price = parseFloat(value);
        if (!isNaN(price)) {
          priceHistory.push(price);
        }
      }
    }
  }
  
  return priceHistory;
}

/**
 * Parse indicator array from cell value (similar to Strike_Hit)
 * @param {string|Array} value - Cell value containing indicator array
 * @returns {Array} Array of indicator values
 */
function EW_parseIndicatorArray(value) {
  if (!value) return [];
  
  // If already an array, return it
  if (Array.isArray(value)) return value;
  
  // If JSON string, parse it
  if (typeof value === 'string' && value.startsWith('[')) {
    try {
      return JSON.parse(value);
    } catch (e) {
      console.log('Failed to parse indicator array:', e);
      return [value]; // Fallback to single value
    }
  }
  
  // Handle comma-separated format
  if (typeof value === 'string' && value.includes(',')) {
    return value.split(',').map(v => v.trim());
  }
  
  // Handle legacy single value
  return [value];
}

/**
 * Append new indicator value to array
 * @param {string|Array} currentValue - Current cell value
 * @param {string|number} newValue - New indicator value to append
 * @returns {string} JSON string of updated array
 */
function EW_appendIndicatorValue(currentValue, newValue) {
  const array = EW_parseIndicatorArray(currentValue);
  // Format the value if it's a number
  const formattedValue = typeof newValue === 'number' ? newValue.toFixed(2) : newValue;
  array.push(formattedValue);
  return JSON.stringify(array);
}

/**
 * Build indicator arrays for all indicators from Day0 to Day5
 * @param {Object} dailyIndicators - Object with arrays of daily indicator values
 * @returns {Object} Object with JSON strings for each indicator array
 * @deprecated Use EW_buildIndicatorArrays from 13_ArrayBuilders.js instead
 */
function EW_buildIndicatorArrays(dailyIndicators) {
  const arrays = {};
  
  // Process each indicator type
  const indicatorTypes = ['rsi', 'sma20', 'sma50', 'ema9', 'ema21', 'vwap', 'rvol', 'atr', 'priceVsSMA20', 'priceVsVWAP'];
  
  for (const type of indicatorTypes) {
    if (dailyIndicators[type]) {
      // Format values appropriately
      const formattedArray = dailyIndicators[type].map(val => {
        if (val === null || val === undefined) return null;
        if (type === 'atr') return val.toFixed(4);
        // Keep priceVsSMA20 and priceVsVWAP as decimals without % sign
        if (type === 'priceVsSMA20' || type === 'priceVsVWAP') return val.toFixed(2);
        return val.toFixed(2);
      });
      arrays[type] = JSON.stringify(formattedArray);
    }
  }
  
  return arrays;
}

/**
 * Apply conditional formatting to Day Check columns
 * Red text for prices that haven't hit the strike
 * @param {Sheet} sheet - The sheet to format
 * @param {Object} hdrMap - Header mapping
 * @param {string} strategy - Strategy name
 */
function EW_formatDayCheckColumns(sheet, hdrMap, strategy) {
  if (!sheet || !hdrMap) return;
  
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return;
  
  const strategyUpper = strategy.toUpperCase();
  const isBullish = strategyUpper.includes('BULL') || strategyUpper.includes('LONG CALL') || strategyUpper.includes('COVERED CALL');
  const isBearish = strategyUpper.includes('BEAR') || strategyUpper.includes('LONG PUT') || strategyUpper.includes('SHORT CALL');
  
  // Get data range
  const dataRange = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
  const data = dataRange.getValues();
  
  // Process each row
  data.forEach((row, rowIndex) => {
    const strike = row[hdrMap.strikeCol - 1] || row[hdrMap.longStrikeCol - 1] || 0;
    if (!strike) return;
    
    // Format each day check column
    const dayCheckCols = [
      hdrMap.day0CheckCol, hdrMap.day1CheckCol, hdrMap.day2CheckCol,
      hdrMap.day3CheckCol, hdrMap.day4CheckCol, hdrMap.day5CheckCol
    ];
    
    dayCheckCols.forEach(col => {
      if (col) {
        const value = row[col - 1];
        if (value && value !== 'None') {
          const price = parseFloat(value);
          if (!isNaN(price)) {
            let shouldBeRed = false;
            
            if (isBullish) {
              // For bullish: red if price < strike
              shouldBeRed = price < strike;
            } else if (isBearish) {
              // For bearish: red if price > strike
              shouldBeRed = price > strike;
            }
            
            if (shouldBeRed) {
              sheet.getRange(rowIndex + 2, col).setFontColor('#ff0000');
            } else {
              sheet.getRange(rowIndex + 2, col).setFontColor('#00aa00'); // Green
            }
          }
        }
      }
    });
  });
}

/**
 * Apply Day Check formatting to the current sheet
 * Can be called from menu to apply colors without running backfill
 */
function EW_applyDayCheckFormatting() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const sheetName = sheet.getName();
  
  // Get headers
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Check if we have day check columns
  if (!hdrMap.day0CheckCol && !hdrMap.day1CheckCol) {
    EW_safeAlert('No Day Check Columns', 'This sheet does not have Day Check columns to format');
    return;
  }
  
  // Apply formatting
  try {
    EW_formatDayCheckColumns(sheet, hdrMap, sheetName);
    SpreadsheetApp.flush();
    EW_safeAlert('Formatting Applied', 'Day Check columns have been formatted with colors');
  } catch (e) {
    EW_safeAlert('Formatting Error', 'Failed to apply formatting: ' + e.message);
  }
}

/**
 * Apply Day Check formatting to all strategy sheets
 */
function EW_applyDayCheckFormattingToAll() {
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  let formatted = 0;
  let errors = [];
  
  for (const strategy of strategies) {
    const sheet = ss.getSheetByName(strategy);
    if (!sheet || sheet.getLastRow() < 2) continue;
    
    try {
      const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      const hdrMap = EW_headerMap(headers);
      
      if (hdrMap.day0CheckCol || hdrMap.day1CheckCol) {
        EW_formatDayCheckColumns(sheet, hdrMap, strategy);
        formatted++;
        EW_trace('FORMAT', `Applied Day Check formatting to ${strategy}`);
      }
    } catch (e) {
      errors.push(`${strategy}: ${e.message}`);
    }
  }
  
  SpreadsheetApp.flush();
  
  const message = `Formatted ${formatted} sheets` + 
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');
  EW_safeAlert('Formatting Complete', message);
}

// ======= BATCH ROW CHECKING UTILITIES =======

/**
 * Check which rows need backfill processing in batch
 * Returns an object with row indices to process and summary statistics
 * @param {Sheet} sheet - The sheet to check
 * @param {Object} hdrMap - Header mapping object
 * @param {Array} data - All row data
 * @param {string} strategyName - Name of the strategy for logging
 * @returns {Object} Object with arrays of rows to process and statistics
 */
function EW_batchCheckBackfillRows(sheet, hdrMap, data, strategyName) {
  const rowsToProcess = [];
  const skippedAlreadyComplete = [];
  const skippedFutureDate = [];
  const skippedMissingData = [];
  const skippedEmptyStrike = [];
  
  const today = new Date();
  today.setHours(23, 59, 59, 999);
  
  const isSpread = strategyName.toUpperCase().includes('SPREAD');
  const strikeCol = isSpread ? hdrMap.longStrikeCol : hdrMap.strikeCol;
  
  // Check each row to determine if it needs processing
  data.forEach((row, rowIndex) => {
    const ticker = row[hdrMap.tickerCol - 1];
    const runDateStr = row[hdrMap.runDateCol - 1];
    const strike = parseFloat(row[strikeCol - 1]) || 0;
    const expDateStr = hdrMap.expDateCol ? row[hdrMap.expDateCol - 1] : null;
    
    // Debug first row
    if (rowIndex === 0) {
      console.log(`BACKFILL DEBUG: Checking row 2 (index 0): ticker="${ticker}", runDate="${runDateStr}", strike=${strike}`);
    }
    
    // Skip if missing required data
    if (!ticker || !runDateStr || !strike) {
      if (!ticker && !runDateStr && !strike) {
        // Completely empty row, skip silently
        return;
      }
      skippedMissingData.push(rowIndex + 2);
      return;
    }
    
    // Check if run date is in the future
    const runDate = new Date(runDateStr);
    if (runDate > today) {
      skippedFutureDate.push(rowIndex + 2);
      return;
    }
    
    // Check which day values are already filled
    const hasDay0 = hdrMap.day0CheckCol && row[hdrMap.day0CheckCol - 1];
    const hasDay1 = hdrMap.day1CheckCol && row[hdrMap.day1CheckCol - 1];
    const hasDay2 = hdrMap.day2CheckCol && row[hdrMap.day2CheckCol - 1];
    const hasDay3 = hdrMap.day3CheckCol && row[hdrMap.day3CheckCol - 1];
    const hasDay4 = hdrMap.day4CheckCol && row[hdrMap.day4CheckCol - 1];
    const hasDay5 = hdrMap.day5CheckCol && row[hdrMap.day5CheckCol - 1];
    const hasStrikeHit = hdrMap.strikeHitCol && row[hdrMap.strikeHitCol - 1];
    const hasIndicators = hdrMap.hitRSICol && row[hdrMap.hitRSICol - 1];
    
    // Check if OHLC_Volume has proper OHLC data (no zero values for prices)
    let hasProperOHLC = false;
    if (hdrMap.ohlcVolumeCol && row[hdrMap.ohlcVolumeCol - 1]) {
      const ohlcData = row[hdrMap.ohlcVolumeCol - 1];
      try {
        const ohlcArray = typeof ohlcData === 'string' ? JSON.parse(ohlcData) : ohlcData;
        // Check if we have valid OHLC data:
        // 1. Array exists and has elements
        // 2. At least one entry has non-zero/non-null OHLC values (prices should never be 0)
        // 3. At least one entry has non-zero/non-null volume
        hasProperOHLC = ohlcArray && Array.isArray(ohlcArray) && ohlcArray.length > 0 &&
          ohlcArray.some(day => {
            if (!day || day === null) return false;
            // Check that OHLC prices are not zero or null (parseFloat handles string values)
            const hasValidPrices = parseFloat(day.o) > 0 || parseFloat(day.h) > 0 || 
                                  parseFloat(day.l) > 0 || parseFloat(day.c) > 0;
            // Volume should be greater than 0 (not null, not 0)
            const hasValidVolume = day.v !== null && day.v !== undefined && parseFloat(day.v) > 0;
            return hasValidPrices && hasValidVolume;
          });
      } catch (e) {
        hasProperOHLC = false;
      }
    }
    
    // Debug first row to see why it might be skipped
    if (rowIndex === 0) {
      console.log(`BACKFILL DEBUG: Row 2 data check: Day0=${!!hasDay0}, Day1=${!!hasDay1}, Day2=${!!hasDay2}, Day3=${!!hasDay3}, Day4=${!!hasDay4}, Day5=${!!hasDay5}, StrikeHit=${!!hasStrikeHit}, Indicators=${!!hasIndicators}, ProperOHLC=${hasProperOHLC}`);
    }
    
    // Skip if ALL day values AND arrays are already filled AND OHLC has proper volume
    if (hasDay0 && hasDay1 && hasDay2 && hasDay3 && hasDay4 && hasDay5 && hasStrikeHit && hasIndicators && hasProperOHLC) {
      skippedAlreadyComplete.push(rowIndex + 2);
      if (rowIndex === 0) {
        console.log(`BACKFILL DEBUG: Row 2 marked as already complete with proper volume, skipping`);
      }
      return;
    }
    
    // Row needs processing
    const rowItem = {
      index: rowIndex,
      rowNum: rowIndex + 2,
      ticker: ticker,
      runDateStr: runDateStr,
      strike: strike,
      expDateStr: expDateStr,
      shortStrike: isSpread && hdrMap.shortStrikeCol ? parseFloat(row[hdrMap.shortStrikeCol - 1]) || null : null,
      hasPartialData: hasDay0 || hasDay1 || hasDay2 || hasDay3 || hasDay4 || hasDay5 || hasStrikeHit
    };
    
    if (rowIndex === 0) {
      console.log(`BACKFILL DEBUG: Row 2 added to processing queue as row ${rowItem.rowNum}`);
    }
    
    rowsToProcess.push(rowItem);
  });
  
  // Create summary message
  const summary = EW_createBatchCheckSummary(
    strategyName,
    data.length,
    rowsToProcess.length,
    skippedAlreadyComplete.length,
    skippedFutureDate.length,
    skippedMissingData.length,
    skippedAlreadyComplete  // Pass the actual array for row number grouping
  );
  
  return {
    rowsToProcess: rowsToProcess,
    skippedAlreadyComplete: skippedAlreadyComplete,
    skippedFutureDate: skippedFutureDate,
    skippedMissingData: skippedMissingData,
    summary: summary,
    totalRows: data.length,
    needsProcessing: rowsToProcess.length
  };
}

/**
 * Check which active positions need updating in batch
 */
function EW_batchCheckActivePositions(sheet, hdrMap, data, strategyName) {
  const positionsToCheck = [];
  const skippedExpired = [];
  const skippedAlreadyUpdated = [];
  const skippedMissingData = [];
  
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const todayStr = today.toISOString().split('T')[0];
  const sevenDaysAgo = new Date(today);
  sevenDaysAgo.setDate(today.getDate() - 7);
  
  // Determine if this is a spread strategy
  const isSpread = strategyName.toUpperCase().includes('SPREAD');
  
  data.forEach((row, index) => {
    const ticker = row[hdrMap.tickerCol - 1];
    const runDateStr = row[hdrMap.runDateCol - 1];
    const daysToExp = hdrMap.daysToExpCol ? parseFloat(row[hdrMap.daysToExpCol - 1]) : null;
    
    // Skip if missing required data
    if (!ticker || !runDateStr) {
      if (!ticker && !runDateStr) {
        // Completely empty row, skip silently
        return;
      }
      skippedMissingData.push(index + 2);
      return;
    }
    
    // Skip expired positions (> 7 days old or daysToExp < -7)
    const runDate = new Date(runDateStr);
    if (runDate < sevenDaysAgo || (daysToExp !== null && daysToExp < -7)) {
      skippedExpired.push(index + 2);
      return;
    }
    
    // For active positions, check the arrays to see if today's data exists
    const strikeHitArray = hdrMap.strikeHitCol ? row[hdrMap.strikeHitCol - 1] : null;
    const maxFavArray = hdrMap.maxFavorableCol ? row[hdrMap.maxFavorableCol - 1] : null;
    
    // Calculate which day index today represents
    const daysSinceRun = Math.floor((today - runDate) / (1000 * 60 * 60 * 24));
    
    // Check if today's data already exists
    let alreadyHasToday = false;
    if (strikeHitArray || maxFavArray) {
      try {
        const strikeData = strikeHitArray ? JSON.parse(strikeHitArray) : [];
        const maxFavData = maxFavArray ? JSON.parse(maxFavArray) : [];
        
        // Check if the array has data for today's index
        if (daysSinceRun >= 0 && daysSinceRun < 6) {
          alreadyHasToday = (strikeData[daysSinceRun] !== null && strikeData[daysSinceRun] !== undefined) ||
                           (maxFavData[daysSinceRun] !== null && maxFavData[daysSinceRun] !== undefined);
        }
      } catch (e) {
        // Invalid JSON, needs update
      }
    }
    
    if (alreadyHasToday) {
      skippedAlreadyUpdated.push(index + 2);
      return;
    }
    
    // Get strike prices based on strategy type
    let strike, shortStrike;
    if (isSpread) {
      strike = hdrMap.longStrikeCol ? parseFloat(row[hdrMap.longStrikeCol - 1]) : null;
      shortStrike = hdrMap.shortStrikeCol ? parseFloat(row[hdrMap.shortStrikeCol - 1]) : null;
    } else {
      strike = hdrMap.strikeCol ? parseFloat(row[hdrMap.strikeCol - 1]) : null;
      shortStrike = null;
    }
    
    // Position needs checking
    positionsToCheck.push({
      ticker: ticker,
      strike: strike,
      shortStrike: shortStrike,
      runDate: runDate,
      runDateStr: runDateStr,
      daysToExp: daysToExp,
      rowIndex: index,
      rowNum: index + 2,
      dayIndex: daysSinceRun
    });
  });
  
  // Create summary message
  const summary = EW_createActiveCheckSummary(
    strategyName,
    data.length,
    positionsToCheck.length,
    skippedAlreadyUpdated.length,
    skippedExpired.length,
    skippedMissingData.length
  );
  
  return {
    positionsToCheck: positionsToCheck,
    skippedAlreadyUpdated: skippedAlreadyUpdated,
    skippedExpired: skippedExpired,
    skippedMissingData: skippedMissingData,
    summary: summary,
    totalRows: data.length,
    needsChecking: positionsToCheck.length
  };
}

/**
 * Create a consolidated summary message for batch checking
 */
function EW_createBatchCheckSummary(strategyName, totalRows, toProcess, alreadyCompleteCount, futureDateCount, missingDataCount, alreadyCompleteRows) {
  const parts = [`${strategyName}: Checking ${totalRows} rows`];
  
  if (toProcess > 0) {
    parts.push(`${toProcess} need processing`);
  }
  
  const skipped = [];
  if (alreadyCompleteCount > 0) {
    // Group consecutive rows for better readability if array provided
    if (alreadyCompleteRows && alreadyCompleteRows.length > 0) {
      const ranges = EW_groupConsecutiveNumbers(alreadyCompleteRows);
      if (ranges.length <= 3) {
        skipped.push(`${alreadyCompleteCount} already complete (rows ${ranges.join(', ')})`);
      } else {
        skipped.push(`${alreadyCompleteCount} already complete`);
      }
    } else {
      skipped.push(`${alreadyCompleteCount} already complete`);
    }
  }
  
  if (futureDateCount > 0) {
    skipped.push(`${futureDateCount} future dated`);
  }
  
  if (missingDataCount > 0) {
    skipped.push(`${missingDataCount} missing data`);
  }
  
  if (skipped.length > 0) {
    parts.push(`Skipped: ${skipped.join(', ')}`);
  }
  
  return parts.join(' - ');
}

/**
 * Create a summary for active position checking
 */
function EW_createActiveCheckSummary(strategyName, totalRows, toCheck, alreadyUpdatedCount, expiredCount, missingDataCount) {
  const parts = [`${strategyName}: Checking ${totalRows} positions`];
  
  if (toCheck > 0) {
    parts.push(`${toCheck} active positions to update`);
  }
  
  const skipped = [];
  if (alreadyUpdatedCount > 0) {
    skipped.push(`${alreadyUpdatedCount} already updated today`);
  }
  
  if (expiredCount > 0) {
    skipped.push(`${expiredCount} expired (>7 days)`);
  }
  
  if (missingDataCount > 0) {
    skipped.push(`${missingDataCount} missing data`);
  }
  
  if (skipped.length > 0) {
    parts.push(`Skipped: ${skipped.join(', ')}`);
  }
  
  return parts.join(' - ');
}

/**
 * Group consecutive numbers into ranges for display
 * e.g., [1,2,3,5,6,8] becomes ["1-3", "5-6", "8"]
 */
function EW_groupConsecutiveNumbers(numbers) {
  if (!numbers || numbers.length === 0) return [];
  
  // Ensure we have an array of numbers
  if (!Array.isArray(numbers)) {
    console.error('EW_groupConsecutiveNumbers: Expected array, got:', typeof numbers, numbers);
    return [];
  }
  
  // Filter out any non-numeric values and ensure all are numbers
  const validNumbers = numbers.filter(n => typeof n === 'number' && !isNaN(n));
  if (validNumbers.length === 0) return [];
  
  const sorted = validNumbers.sort((a, b) => a - b);
  const ranges = [];
  let start = sorted[0];
  let end = sorted[0];
  
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] === end + 1) {
      end = sorted[i];
    } else {
      if (start === end) {
        ranges.push(start.toString());
      } else if (end === start + 1) {
        ranges.push(`${start},${end}`);
      } else {
        ranges.push(`${start}-${end}`);
      }
      start = sorted[i];
      end = sorted[i];
    }
  }
  
  // Add the last range
  if (start === end) {
    ranges.push(start.toString());
  } else if (end === start + 1) {
    ranges.push(`${start},${end}`);
  } else {
    ranges.push(`${start}-${end}`);
  }
  
  return ranges;
}

/**
 * Log batch processing progress at intervals
 * Only logs every N rows to reduce log spam
 */
function EW_logBatchProgress(current, total, interval = 50, prefix = 'BACKFILL') {
  if (current % interval === 0 || current === total) {
    const percent = Math.round((current / total) * 100);
    EW_trace(prefix, `Progress: ${current}/${total} (${percent}%)`, true);
  }
}

// ======= INDICATOR RECALCULATION UTILITIES =======

/**
 * Recalculate indicators for selected rows using existing Strike_Hit data
 * This is much faster than re-running the entire backfill
 */
function EW_recalculateIndicatorsForSelected() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const range = sheet.getActiveRange();
  
  if (!range) {
    EW_safeAlert('No Selection', 'Please select rows to recalculate indicators');
    return;
  }
  
  const startRow = range.getRow();
  const numRows = range.getNumRows();
  
  if (startRow === 1) {
    EW_safeAlert('Invalid Selection', 'Please select data rows, not the header row');
    return;
  }
  
  EW_trace('INDICATORS', `Recalculating indicators for ${numRows} selected rows`, true);
  
  // Get headers
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Check required columns exist
  const requiredCols = ['tickerCol', 'runDateCol', 'strikeCol', 'strikeHitCol'];
  
  for (const col of requiredCols) {
    if (!hdrMap[col]) {
      EW_safeAlert('Missing Column', `Required column ${col} not found`);
      return;
    }
  }
  
  let processedCount = 0;
  let skippedCount = 0;
  
  // Process each selected row
  for (let i = 0; i < numRows; i++) {
    const rowNum = startRow + i;
    const rowData = sheet.getRange(rowNum, 1, 1, sheet.getLastColumn()).getValues()[0];
    
    const ticker = rowData[hdrMap.tickerCol - 1];
    const runDateStr = rowData[hdrMap.runDateCol - 1];
    const strike = parseFloat(rowData[hdrMap.strikeCol - 1]);
    const strikeHitData = rowData[hdrMap.strikeHitCol - 1];
    
    if (!ticker || !runDateStr || !strike) {
      EW_trace('INDICATORS', `Row ${rowNum}: Missing required data, skipping`);
      skippedCount++;
      continue;
    }
    
    if (!strikeHitData || strikeHitData === '["NO_DATA"]') {
      EW_trace('INDICATORS', `Row ${rowNum} (${ticker}): No Strike_Hit data available, skipping`);
      skippedCount++;
      continue;
    }
    
    try {
      // Parse the Strike_Hit array to determine which days had hits
      let strikeHitArray;
      try {
        strikeHitArray = JSON.parse(strikeHitData);
      } catch (e) {
        EW_trace('INDICATORS', `Row ${rowNum} (${ticker}): Invalid Strike_Hit JSON, skipping`);
        skippedCount++;
        continue;
      }
      
      // Count how many days have data (non-null entries)
      const daysWithData = strikeHitArray.filter(val => val !== null && val !== 'NO_DATA').length;
      
      if (daysWithData === 0) {
        EW_trace('INDICATORS', `Row ${rowNum} (${ticker}): Strike_Hit array has no valid data`);
        skippedCount++;
        continue;
      }
      
      EW_trace('INDICATORS', `Row ${rowNum} (${ticker}): Found ${daysWithData} days with strike hit data`);
      
      // Parse dates
      const runDate = new Date(runDateStr);
      const marketRunDate = EW_adjustToMarketHours(runDate);
      
      // Calculate the date range we need data for
      const endDate = new Date();
      endDate.setHours(16, 0, 0, 0);
      
      // Fetch the historical data with indicators
      EW_trace('INDICATORS', `Fetching data for ${ticker} from ${marketRunDate.toISOString().split('T')[0]} to ${endDate.toISOString().split('T')[0]}`);
      
      const yahooResult = EW_getYahooHistoricalRange(ticker, marketRunDate, endDate, true);
      
      if (!yahooResult || !yahooResult.data || yahooResult.data.length === 0) {
        EW_trace('INDICATORS', `Row ${rowNum} (${ticker}): Unable to fetch Yahoo data`);
        skippedCount++;
        continue;
      }
      
      // Analyze the data to get indicators at strike hit points
      const analysis = EW_analyzeHistoricalData(
        ticker, 
        sheet.getName(), 
        strike, 
        yahooResult.data, 
        marketRunDate, 
        null, // shortStrike
        yahooResult.raw
      );
      
      if (!analysis || !analysis.dailyIndicators) {
        EW_trace('INDICATORS', `Row ${rowNum} (${ticker}): No indicators calculated`);
        skippedCount++;
        continue;
      }
      
      // Format the indicator arrays
      const indicatorArrays = EW_formatIndicatorArraysForStorage(analysis.dailyIndicators);
      
      // Update only the indicator columns
      let updated = false;
      
      if (hdrMap.hitRSICol && indicatorArrays.rsi) {
        sheet.getRange(rowNum, hdrMap.hitRSICol).setValue(indicatorArrays.rsi);
        updated = true;
      }
      if (hdrMap.hitSMA20Col && indicatorArrays.sma20) {
        sheet.getRange(rowNum, hdrMap.hitSMA20Col).setValue(indicatorArrays.sma20);
        updated = true;
      }
      if (hdrMap.hitSMA50Col && indicatorArrays.sma50) {
        sheet.getRange(rowNum, hdrMap.hitSMA50Col).setValue(indicatorArrays.sma50);
        updated = true;
      }
      if (hdrMap.hitEMA9Col && indicatorArrays.ema9) {
        sheet.getRange(rowNum, hdrMap.hitEMA9Col).setValue(indicatorArrays.ema9);
        updated = true;
      }
      if (hdrMap.hitEMA21Col && indicatorArrays.ema21) {
        sheet.getRange(rowNum, hdrMap.hitEMA21Col).setValue(indicatorArrays.ema21);
        updated = true;
      }
      if (hdrMap.hitVWAPCol && indicatorArrays.vwap) {
        sheet.getRange(rowNum, hdrMap.hitVWAPCol).setValue(indicatorArrays.vwap);
        updated = true;
      }
      if (hdrMap.hitRVOLCol && indicatorArrays.rvol) {
        sheet.getRange(rowNum, hdrMap.hitRVOLCol).setValue(indicatorArrays.rvol);
        updated = true;
      }
      if (hdrMap.hitATRCol && indicatorArrays.atr) {
        sheet.getRange(rowNum, hdrMap.hitATRCol).setValue(indicatorArrays.atr);
        updated = true;
      }
      if (hdrMap.hitPriceVsSMA20Col && indicatorArrays.priceVsSMA20) {
        sheet.getRange(rowNum, hdrMap.hitPriceVsSMA20Col).setValue(indicatorArrays.priceVsSMA20);
        updated = true;
      }
      if (hdrMap.hitPriceVsVWAPCol && indicatorArrays.priceVsVWAP) {
        sheet.getRange(rowNum, hdrMap.hitPriceVsVWAPCol).setValue(indicatorArrays.priceVsVWAP);
        updated = true;
      }
      
      if (updated) {
        processedCount++;
        EW_trace('INDICATORS', `Row ${rowNum} (${ticker}): Indicators updated successfully`);
      } else {
        EW_trace('INDICATORS', `Row ${rowNum} (${ticker}): No indicator columns found to update`);
        skippedCount++;
      }
      
    } catch (e) {
      EW_trace('INDICATORS', `Row ${rowNum} (${ticker}): Error - ${e.message}`);
      skippedCount++;
    }
  }
  
  SpreadsheetApp.flush();
  const message = `Recalculated indicators for ${processedCount} rows\nSkipped ${skippedCount} rows`;
  EW_safeAlert('Indicator Recalculation Complete', message);
}

/**
 * Batch recalculate indicators for all rows with Strike_Hit data
 * Processes an entire sheet at once
 */
function EW_recalculateIndicatorsForSheet() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const sheetName = sheet.getName();
  
  EW_trace('INDICATORS', `Starting indicator recalculation for sheet: ${sheetName}`, true);
  
  // Get headers
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Check if we have the Strike_Hit column
  if (!hdrMap.strikeHitCol) {
    EW_safeAlert('Missing Column', 'Strike_Hit column not found in this sheet');
    return;
  }
  
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    EW_safeAlert('No Data', 'No data rows found in sheet');
    return;
  }
  
  // Get all Strike_Hit data to find rows that need processing
  const strikeHitRange = sheet.getRange(2, hdrMap.strikeHitCol, lastRow - 1, 1);
  const strikeHitData = strikeHitRange.getValues();
  
  // Find rows with valid Strike_Hit data but missing indicators
  const rowsToProcess = [];
  for (let i = 0; i < strikeHitData.length; i++) {
    const strikeHit = strikeHitData[i][0];
    if (strikeHit && strikeHit !== '' && strikeHit !== '["NO_DATA"]') {
      // Check if indicators are missing
      const rowNum = i + 2;
      const indicatorData = hdrMap.hitRSICol ? 
        sheet.getRange(rowNum, hdrMap.hitRSICol).getValue() : null;
      
      if (!indicatorData || indicatorData === '') {
        rowsToProcess.push(rowNum);
      }
    }
  }
  
  if (rowsToProcess.length === 0) {
    EW_safeAlert('No Processing Needed', 'All rows with Strike_Hit data already have indicators');
    return;
  }
  
  const response = Browser.msgBox(
    'Confirm Recalculation',
    `Found ${rowsToProcess.length} rows that need indicator calculation. Continue?`,
    Browser.Buttons.YES_NO
  );
  
  if (response !== Browser.Buttons.YES) {
    return;
  }
  
  // Process in batches to avoid timeout
  const BATCH_SIZE = 10;
  let processedCount = 0;
  
  for (let batch = 0; batch < rowsToProcess.length; batch += BATCH_SIZE) {
    const batchRows = rowsToProcess.slice(batch, batch + BATCH_SIZE);
    
    EW_trace('INDICATORS', `Processing batch ${Math.floor(batch/BATCH_SIZE) + 1} of ${Math.ceil(rowsToProcess.length/BATCH_SIZE)}`);
    
    // Process each row in the batch
    for (const rowNum of batchRows) {
      // Set the range for this specific row
      const range = sheet.getRange(rowNum, 1, 1, sheet.getLastColumn());
      sheet.setActiveRange(range);
      
      // Process this row
      EW_recalculateIndicatorsForSelected();
      processedCount++;
    }
    
    // Add a small delay between batches
    Utilities.sleep(1000);
  }
  
  EW_trace('INDICATORS', `Completed indicator recalculation for ${processedCount} rows`, true);
}

/**
 * Quick function to check which rows are missing indicators
 * Useful for diagnostics
 */
function EW_checkMissingIndicators() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  if (!hdrMap.strikeHitCol || !hdrMap.hitRSICol) {
    EW_safeAlert('Missing Columns', 'Strike_Hit or Hit_RSI column not found');
    return;
  }
  
  const lastRow = sheet.getLastRow();
  const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  
  const missingRows = [];
  
  data.forEach((row, index) => {
    const strikeHit = row[hdrMap.strikeHitCol - 1];
    const hitRSI = row[hdrMap.hitRSICol - 1];
    const ticker = row[hdrMap.tickerCol - 1];
    
    if (strikeHit && strikeHit !== '' && strikeHit !== '["NO_DATA"]' && (!hitRSI || hitRSI === '')) {
      missingRows.push({
        row: index + 2,
        ticker: ticker,
        strikeHit: strikeHit
      });
    }
  });
  
  if (missingRows.length === 0) {
    EW_safeAlert('Check Complete', 'All rows with Strike_Hit data have indicators');
  } else {
    const sample = missingRows.slice(0, 10).map(r => `Row ${r.row}: ${r.ticker}`).join('\n');
    const message = `Found ${missingRows.length} rows missing indicators:\n\n${sample}${missingRows.length > 10 ? '\n...' : ''}`;
    EW_safeAlert('Missing Indicators Found', message);
  }
}
