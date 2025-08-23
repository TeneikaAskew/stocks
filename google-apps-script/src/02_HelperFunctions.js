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

// ======= LOGGING AND DEBUGGING =======

/**
 * Super-logger: console + Logger + optional Log sheet
 * @param {string} scope - Log scope/category
 * @param {string} msg - Log message
 * @param {boolean} alsoSheet - Also write to Log sheet
 */
function EW_trace(scope, msg, alsoSheet = false) {
  const line = `[${new Date().toISOString()}] [${scope}] ${msg}`;
  try { console.log(line); } catch (_) {}
  // try { Logger.log(line); } catch (_) {}
  if (alsoSheet) {
    try {
      const ss = SpreadsheetApp.getActive();
      let log = ss.getSheetByName('Log');
      if (!log) log = ss.insertSheet('Log');
      log.appendRow([new Date(), scope, msg]);
    } catch (e) {
      console.error('Failed to write to Log sheet:', e);
    }
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
