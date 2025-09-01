/**
 * EarningsWhispers OptionTrades — Apps Script (sheet-bound, verbose)
 * - Fetches JSON from /api/get* endpoints for each strategy
 * - Normalizes JSON -> header row + data rows
 * - Appends to tabs named after strategies (creates if missing)
 * - Logs to console, Logger, and a "Log" sheet
 * - Optional login (set Script Properties: EW_USER, EW_PASS) if API needs session
 * https://hackernoon.com/writing-google-apps-script-code-locally-in-vscode
 * 
 * Dependencies:
 * - GlobalVars.js: Configuration constants and global variables
 * - HelperFunctions.js: Utility functions and helpers
 */

// ======= EXPOSE HELPER FUNCTIONS ON EW OBJECT =======
// Make URL helper available on EW object for backwards compatibility
EW.url = EW_url;

// ======= UI MENU =======

/**
 * Creates the EarningsWhispers menu in the Google Sheets UI
 * Automatically executed when the spreadsheet is opened
 * Sets up the main menu with options for running strategies, reports, and automation
 * @returns {void}
 */
function onOpen() {
  if (!EW_isSpreadsheetEnvironment()) {
    EW_trace('MENU', 'Not in spreadsheet environment, skipping menu creation');
    return;
  }
  
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('EarningsWhispers')
    .addItem('Run all strategies', 'EW_runAll')
    .addItem('Debug one (prompt)', 'EW_debugOne')
    .addSeparator()
    .addItem('Test Login', 'EW_testLogin')
    .addSeparator()
    .addItem('Generate Success Report', 'EW_generateSuccessReport')
    .addItem('Update Success Report', 'EW_updateSuccessReport')
    .addItem('Update Tracking Data (Formulas)', 'EW_updateTrackingData')
    .addItem('Update Tracking Data (Fill Columns)', 'EW_updateAllTrackingData')
    .addItem('Fix: Add Strategy column (one-time)', 'EW_fixAddStrategyColumn')
    .addItem('Fix: Complete sheet repair', 'EW_completeSheetRepair')
    .addSeparator()
    .addSubMenu(ui.createMenu('Analysis & Reports')
      .addItem('Comprehensive Success Report', 'EW_generateSuccessReport')
      .addItem('Export ML Data', 'EW_exportMLData')
      .addSeparator()
      .addItem('Top 20 Winning Plays', 'EW_showTopWinningPlays')
      .addItem('Multi-Day Profitability', 'EW_showMultiDayReport')
      .addItem('Indicator Effectiveness', 'EW_showIndicatorAnalysis')
      .addItem('Earnings Timing Analysis', 'EW_showEarningsTimingReport')
      .addItem('Strategy Performance Summary', 'EW_showStrategyPerformance')
    )
    .addSeparator()
    .addItem('Backfill Historical Tracking (All)', 'EW_backfillHistoricalTracking')
    .addItem('Backfill Selected Rows', 'EW_backfillSelectedRows')
    .addSeparator()
    .addItem('Recalculate Indicators (Selected)', 'EW_recalculateIndicatorsForSelected')
    .addItem('Recalculate Indicators (Sheet)', 'EW_recalculateIndicatorsForSheet')
    .addItem('Check Missing Indicators', 'EW_checkMissingIndicators')
    .addSeparator()
    .addItem('Apply Day Check Formatting (Current)', 'EW_applyDayCheckFormatting')
    .addItem('Apply Day Check Formatting (All)', 'EW_applyDayCheckFormattingToAll')
    .addSeparator()
    .addItem('Update Active Position Strikes', 'EW_updateActiveStrikeHits')
    .addSeparator()
    .addItem('Add Tracking Columns (Current Sheet)', 'EW_addColumnsToCurrentSheet')
    .addItem('Add Tracking Columns (All Sheets)', 'EW_addTrackingColumnsToAll')
    .addSeparator()
    .addItem('Reset All Continuation States', 'EW_resetContinuation')
    .addSeparator()
    .addSubMenu(ui.createMenu('API Logging & Debug')
      .addItem('View Today\'s API Summary', 'EW_showApiSummary')
      .addItem('Create Daily API Report', 'EW_createDailyApiReport')
      .addItem('Open API Logging Folders', 'EW_getApiResponsesFolderUrl')
      .addItem('Cleanup Old Logs (>30 days)', 'EW_cleanupOldApiLogs')
      .addSeparator()
      .addItem('Debug Yahoo API', 'EW_debugYahooApi')
      .addItem('Test Yahoo Data', 'EW_testYahooData')
    )
    .addSeparator()
    .addSubMenu(ui.createMenu('Automation & Triggers')
      .addItem('Setup Full Auto Tracking', 'EW_setupAutoTracking')
      .addItem('Setup Daily Data Fetch (8AM)', 'EW_setupDailyDataTrigger')
      // Note: 4:30PM tracking has been consolidated into 5PM Yahoo function
      .addItem('Setup Active Position Tracking (5PM)', 'EW_setupActiveTrackingTrigger')
      .addItem('Setup Missing Triggers Only', 'EW_setupTriggersIfMissing')
      .addSeparator()
      .addItem('Stop All Auto Tracking', 'EW_stopAutoTracking')
      .addItem('Stop Daily Data Fetch', 'EW_stopDailyDataTrigger')
      // Note: 4:30PM tracking has been consolidated into 5PM Yahoo function
      .addItem('Stop Active Position Tracking', 'EW_removeActiveTrackingTrigger')
      .addSeparator()
      .addItem('List Active Triggers', 'EW_listActiveTriggers')
      .addItem('Validate Triggers', 'EW_validateTriggers')
      .addItem('Verify & Repair Triggers', 'EW_verifyAndRepairTriggers')
      .addSeparator()
      .addItem('Test Environment Detection', 'EW_testEnvironmentDetection')
    )
    .addToUi();
    
  // Auto-create success report on first run
  EW_ensureSuccessReportExists();
}

/**
 * Interactive prompt to run a single strategy for quick debugging
 * Shows a popup dialog with available strategies for selection
 * @returns {void}
 */
function EW_debugOne() {
  const ui = SpreadsheetApp.getUi();
  const names = Object.keys(EW.STRATEGY_ENDPOINTS);
  const res = ui.prompt(
    'Debug one strategy',
    `Type one of:\n${names.join(', ')}`,
    ui.ButtonSet.OK_CANCEL
  );
  if (res.getSelectedButton() !== ui.Button.OK) return;
  const name = res.getResponseText().trim();
  if (!EW.STRATEGY_ENDPOINTS[name]) {
    EW_safeAlert('Unknown Strategy', `Unknown strategy: "${name}"`);
    return;
  }
  EW_runSingle(name);
}

/**
 * Debug function to test authentication and report login status
 * @returns {void}
 */
function EW_testLogin() {
  try {
    EW_trace('TEST', 'Testing login credentials...', true);
    
    if (!EW.p.user || !EW.p.pass) {
      EW_safeAlert('No credentials found. Please set EW_USER and EW_PASS in Script Properties.');
      return;
    }
    
    EW_trace('TEST', `Found credentials for user: ${EW.p.user}`, true);
    
    const cookies = EW_login();
    EW_trace('TEST', `Login attempt completed. Cookies received: ${Object.keys(cookies).length}`, true);
    
    if (Object.keys(cookies).length === 0) {
      EW_safeAlert('Login failed - no cookies received. Check your credentials.');
    } else {
      EW_safeAlert(`Login appears successful. Received ${Object.keys(cookies).length} cookies.`);
    }
    
  } catch (e) {
    EW_trace('TEST', `Login test failed: ${e.message}`, true);
    EW_safeAlert(`Login test failed: ${e.message}`);
  }
}

// ======= MAIN STRATEGY EXECUTION =======

/**
 * Runs all configured EarningsWhispers strategies sequentially
 * Fetches data from each strategy endpoint and populates corresponding sheets
 * Creates sheets automatically if they don't exist
 * Handles authentication and session management
 * @returns {void}
 */
function EW_runAll() {
  EW_trace('MAIN', 'EW_runAll() started', true);

  let cookies = {};
  if (EW.p.user && EW.p.pass) {
    try {
      EW_trace('LOGIN', `Attempting login as ${EW.p.user}`);
      cookies = EW_login();
      EW_trace('LOGIN', `Login complete; cookies=${Object.keys(cookies).length}`);
      Utilities.sleep(600);
    } catch (e) {
      EW_trace('LOGIN', `Login failed: ${e && e.message ? e.message : e}`, true);
    }
  } else {
    EW_trace('LOGIN', 'No EW_USER/EW_PASS set; skipping login');
  }

  const ss = SpreadsheetApp.getActive();
  const endpoints = EW.STRATEGY_ENDPOINTS;
  EW_trace('MAIN', `Fetching ${Object.keys(endpoints).length} endpoints`);

  for (const [tabName, path] of Object.entries(endpoints)) {
    EW_runOneInternal(ss, tabName, path, cookies);
  }

  // Clean up empty rows after starting to prevent accumulation
  EW_trace('MAIN', 'Cleaning up empty rows after data fetch...', false);
  EW_cleanupEmptyRows();

  EW_trace('MAIN', 'EW_runAll() finished', true);
}

/**
 * Runs a single EarningsWhispers strategy by name
 * @param {string} tabName - Name of the strategy to run (must match keys in EW.STRATEGY_ENDPOINTS)
 * @returns {void}
 */
function EW_runSingle(tabName) {
  EW_trace('MAIN', `EW_runSingle(${tabName})`);
  const path = EW.STRATEGY_ENDPOINTS[tabName];
  if (!path) {
    EW_trace('MAIN', `Unknown tabName: ${tabName}`, true);
    return;
  }
  let cookies = {};
  if (EW.p.user && EW.p.pass) {
    try { cookies = EW_login(); } catch (e) {}
  }
  const ss = SpreadsheetApp.getActive();
  EW_runOneInternal(ss, tabName, path, cookies);
  EW_trace('MAIN', `EW_runSingle(${tabName}) done`, true);
}

/**
 * Internal function to execute a strategy against a specific sheet
 * Handles the complete flow: API call, data processing, and sheet updates
 * @param {Spreadsheet} ss - The Google Sheets spreadsheet object
 * @param {string} tabName - Name of the strategy/tab
 * @param {string} path - API endpoint path for the strategy
 * @param {Object} cookies - Authentication cookies object
 * @returns {void}
 */
function EW_runOneInternal(ss, tabName, path, cookies) {
  try {
    const url = EW.url(path);
    EW_trace(tabName, `GET ${url}`);
    const json = EW_fetchJson(url, cookies);
    EW_trace(tabName, `HTTP OK; JSON=${EW_summarizeJson(json)}`);
    const rows = EW_jsonToRows(json);
    EW_trace(tabName, `Parsed rows=${rows ? rows.length : 0}`);

    if (!rows || rows.length === 0) {
      EW_trace(tabName, 'Empty table or parse failure', true);
      return;
    }

    const before = ss.getSheetByName(tabName)?.getLastRow() || 0;
    EW_appendToTab(ss, tabName, rows, true);
    const after = ss.getSheetByName(tabName)?.getLastRow() || 0;
    EW_trace(tabName, `Wrote to sheet "${tabName}": +${Math.max(0, after - before)} rows`, true);

    Utilities.sleep(300);
  } catch (err) {
    const msg = (err && err.stack) ? err.stack : (err && err.message ? err.message : String(err));
    EW_trace(tabName, `ERROR: ${msg}`, true);
    
    // If it's an authentication-related error, log it and continue with other endpoints
    if (msg.includes('HTML page instead of JSON') || msg.includes('authentication')) {
      EW_trace(tabName, `Skipping ${tabName} due to authentication issue - endpoint may require login`, true);
    }
  }
}

// ======= API COMMUNICATION =======

/**
 * Fetches JSON data from EarningsWhispers API endpoint
 * Handles HTTP requests with proper headers and cookie management
 * @param {string} url - Full URL to fetch from
 * @param {Object} cookiesObj - Cookies object for authentication
 * @returns {Object|null} Parsed JSON response or null if error
 */
function EW_fetchJson(url, cookiesObj) {
  const headers = {
    'accept': 'application/json, text/javascript, */*; q=0.01',
    'x-requested-with': 'XMLHttpRequest',
    'User-Agent': 'Mozilla/5.0 (compatible; AppsScript)',
    'Referer': EW.MATRIX_REFERRER
  };
  if (cookiesObj && Object.keys(cookiesObj).length) {
    headers['Cookie'] = EW_cookieHeader(cookiesObj);
  }

  EW_trace('HTTP', `Fetching ${url}`);
  const res = UrlFetchApp.fetch(url, {
    method: 'get',
    headers,
    muteHttpExceptions: true,
    followRedirects: true
  });

  const code = res.getResponseCode();
  EW_trace('HTTP', `Response ${code} for ${url}`);
  if (code >= 400) {
    const snippet = (res.getContentText() || '').slice(0, 300).replace(/\s+/g, ' ');
    throw new Error(`HTTP ${code} for ${url}; body[0..300]: ${snippet}`);
  }

  const text = res.getContentText();
  
  // Check if response is HTML (likely an error page)
  if (text.trim().startsWith('<!DOCTYPE') || text.trim().startsWith('<html')) {
    EW_trace('HTTP', `Received HTML instead of JSON for ${url} - possible authentication issue`);
    // Extract title from HTML for better error reporting
    const titleMatch = text.match(/<title[^>]*>([^<]+)</i);
    const title = titleMatch ? titleMatch[1] : 'Unknown HTML page';
    throw new Error(`API returned HTML page instead of JSON for ${url}. Page title: "${title}". This usually indicates authentication failure.`);
  }
  
  try {
    const parsed = JSON.parse(text);
    return parsed;
  } catch (e) {
    EW_trace('HTTP', `JSON parse error for ${url}: ${(e && e.message) || e}`);
    const snippet = text.slice(0, 200).replace(/\s+/g, ' ');
    throw new Error(`JSON parse error for ${url}: ${e.message || e}. Response start: ${snippet}`);
  }
}

/**
 * Performs login authentication to EarningsWhispers
 * Fetches credentials from Script Properties and handles CSRF tokens
 * @returns {Object} Cookies object containing session information
 */
function EW_login() {
  const { user, pass, loginUrl } = EW.p;
  if (!user || !pass) {
    EW_trace('LOGIN', 'No credentials provided; returning empty cookies');
    return {};
  }

  EW_trace('LOGIN', `GET ${loginUrl}`);
  const res1 = UrlFetchApp.fetch(loginUrl, {
    method: 'get',
    muteHttpExceptions: true,
    followRedirects: false,
    headers: {
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'User-Agent': 'Mozilla/5.0 (compatible; AppsScript)'
    }
  });
  const c1 = EW_collectSetCookies(res1);
  EW_trace('LOGIN', `res1 code=${res1.getResponseCode()} cookies=${Object.keys(c1).length}`);

  const html = res1.getContentText() || '';
  const csrf = EW_extractCsrf(html);
  if (csrf) EW_trace('LOGIN', `Found CSRF token`);

  const payload = { Email: user, Password: pass };
  if (csrf) payload['__RequestVerificationToken'] = csrf;

  EW_trace('LOGIN', `POST ${loginUrl}`);
  const res2 = UrlFetchApp.fetch(loginUrl, {
    method: 'post',
    payload,
    muteHttpExceptions: true,
    followRedirects: false,
    headers: {
      'Cookie': EW_cookieHeader(c1),
      'Content-Type': 'application/x-www-form-urlencoded',
      'User-Agent': 'Mozilla/5.0 (compatible; AppsScript)',
      'Origin': EW.BASE,
      'Referer': loginUrl
    }
  });
  let cookies = EW_mergeCookies(c1, EW_collectSetCookies(res2));
  EW_trace('LOGIN', `res2 code=${res2.getResponseCode()} cookies now=${Object.keys(cookies).length}`);

  if (res2.getResponseCode() >= 300 && res2.getResponseCode() < 400) {
    const loc = res2.getHeaders()['Location'];
    EW_trace('LOGIN', `Redirect -> ${loc || '(none)'}`);
    
    // Check if redirect indicates login failure
    if (loc && (loc.includes('/doh') || loc.includes('error') || loc.includes('failed'))) {
      const errorMsg = `Login failed: Bad request: ${EW.BASE}${loc}`;
      EW_trace('LOGIN', errorMsg);
      throw new Error(errorMsg);
    }
    
    if (loc) {
      const res3 = UrlFetchApp.fetch(EW.BASE + loc, {
        method: 'get',
        muteHttpExceptions: true,
        followRedirects: true,
        headers: {
          'Cookie': EW_cookieHeader(cookies),
          'User-Agent': 'Mozilla/5.0 (compatible; AppsScript)'
        }
      });
      cookies = EW_mergeCookies(cookies, EW_collectSetCookies(res3));
      EW_trace('LOGIN', `res3 code=${res3.getResponseCode()} cookies now=${Object.keys(cookies).length}`);
    }
  }
  
  // Validate login success by checking for typical authentication cookies
  const hasAuthCookie = Object.keys(cookies).some(key => 
    key.toLowerCase().includes('auth') || 
    key.toLowerCase().includes('session') || 
    key.toLowerCase().includes('login') ||
    key.toLowerCase().includes('token')
  );
  
  if (!hasAuthCookie && Object.keys(cookies).length < 2) {
    EW_trace('LOGIN', 'Warning: Login may have failed - no authentication cookies found');
  }

  return cookies;
}

// ======= DATA PROCESSING =======

/**
 * Converts raw JSON data to spreadsheet rows format
 * Handles both array and object-based JSON structures
 * @param {Array|Object} data - Raw JSON data from API
 * @returns {Array} Array of arrays suitable for Google Sheets
 */
function EW_jsonToRows(data) {
  if (!data) return [];

  if (Array.isArray(data)) {
    EW_trace('PARSE', `Array detected len=${data.length}`);
    return EW_objectsToRows(data);
  }
  if (data && Array.isArray(data.data)) {
    EW_trace('PARSE', `Object with data[] len=${data.data.length}`);
    return EW_objectsToRows(data.data);
  }
  if (data && Array.isArray(data.rows) && Array.isArray(data.headers)) {
    EW_trace('PARSE', `Already {headers,rows} with rows=${data.rows.length}`);
    return [data.headers, ...data.rows];
  }

  if (typeof data === 'object') {
    EW_trace('PARSE', 'Single object -> one row');
    return EW_objectsToRows([data]);
  }

  EW_trace('PARSE', 'Unknown shape -> empty');
  return [];
}

/**
 * Converts array of objects to rows format with headers
 * Extracts all unique keys as headers and creates data rows
 * @param {Array} arr - Array of objects from JSON
 * @returns {Array} Array where first element is headers, rest are data rows
 */
function EW_objectsToRows(arr) {
  if (!arr || arr.length === 0) return [];
  const preferred = [
    'company','ticker','strategy','earningsDate','earningsTime','price',
    'strike','expiration','delta','iv','rvol','rsi','atr','premium','maxProfit',
    'breakeven','probITM','probOTM','notes','date','time'
  ];
  const keySet = new Set(preferred);
  arr.forEach(obj => {
    Object.keys(obj || {}).forEach(k => { if (!keySet.has(k)) keySet.add(k); });
  });
  const headers = Array.from(keySet).filter(k =>
    arr.some(o => Object.prototype.hasOwnProperty.call(o || {}, k))
  );

  const rows = arr.map(o => headers.map(h => {
    const v = (o && o[h] != null) ? o[h] : '';
    return (typeof v === 'object') ? JSON.stringify(v) : String(v);
  }));

  EW_trace('PARSE', `headers=${headers.length} dataRows=${rows.length}`);
  return [headers, ...rows];
}

// ======= SHEET MANAGEMENT =======

/**
 * Removes empty rows from all strategy sheets
 * OPTIMIZED: Uses batch operations to avoid individual deleteRow calls
 * @returns {void}
 */
function EW_cleanupEmptyRows() {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const endpoints = EW.STRATEGY_ENDPOINTS;
    let totalRemoved = 0;
    
    for (const tabName of Object.keys(endpoints)) {
      const sheet = ss.getSheetByName(tabName);
      if (!sheet || sheet.getLastRow() <= 1) continue; // Skip if no sheet or only header
      
      const lastRow = sheet.getLastRow();
      const lastCol = sheet.getLastColumn();
      
      if (lastRow <= 1) continue; // Only header, nothing to clean
      
      // Get ALL data at once for efficiency
      const allData = sheet.getRange(1, 1, lastRow, lastCol).getValues();
      const headers = allData[0];
      const hdrMap = EW_headerMap(headers);
      
      // Determine which columns are formula columns to ignore
      const formulaColumns = new Set();
      headers.forEach((header, idx) => {
        if (header && (header.toString().startsWith('GF_') || 
                      header.toString().includes('Days_To_Exp') ||
                      header.toString().includes('Success_Score') ||
                      header.toString().includes('Historical_') ||
                      header.toString().includes('Ever_Hit') ||
                      header.toString().includes('First_Hit') ||
                      header.toString().includes('Last_Update') ||
                      header.toString().includes('Total_Hit'))) {
          formulaColumns.add(idx);
        }
      });
      
      // Use ticker column as the primary indicator of real data
      const checkCol = (hdrMap.tickerCol || hdrMap.runDateCol || 1) - 1; // Convert to 0-based
      
      // Find non-empty rows to keep
      const rowsToKeep = [allData[0]]; // Always keep header
      
      for (let i = 1; i < allData.length; i++) {
        const row = allData[i];
        
        // Quick check: if ticker/primary column has data, keep the row
        if (row[checkCol] !== '' && row[checkCol] !== null) {
          rowsToKeep.push(row);
          continue;
        }
        
        // Detailed check: see if any non-formula columns have data
        let hasData = false;
        for (let j = 0; j < row.length; j++) {
          if (!formulaColumns.has(j) && row[j] !== '' && row[j] !== null) {
            hasData = true;
            break;
          }
        }
        
        if (hasData) {
          rowsToKeep.push(row);
        } else {
          totalRemoved++;
        }
      }
      
      // Only update sheet if we removed rows
      if (rowsToKeep.length < allData.length) {
        const removedCount = allData.length - rowsToKeep.length;
        
        // Clear the entire sheet
        sheet.clear();
        
        // Write back only the rows we want to keep in one batch operation
        if (rowsToKeep.length > 0) {
          sheet.getRange(1, 1, rowsToKeep.length, lastCol).setValues(rowsToKeep);
        }
        
        EW_trace('CLEANUP', `Removed ${removedCount} empty rows from ${tabName} (batch operation)`);
        
        // Re-apply formulas if we have the header map
        if (rowsToKeep.length > 1) { // Has data rows, not just header
          const newHdrMap = EW_headerMap(rowsToKeep[0]);
          EW_setGFArrayFormulas(sheet, newHdrMap);
        }
      }
    }
    
    if (totalRemoved > 0) {
      EW_trace('CLEANUP', `Total empty rows removed: ${totalRemoved} (using batch operations)`, false);
    }
  } catch (error) {
    EW_trace('CLEANUP', `Error during empty row cleanup: ${error.toString()}`, false);
  }
}

/**
 * Main function to append data rows to a strategy sheet
 * Handles sheet creation, header management, and GOOGLEFINANCE formula setup
 * @param {Spreadsheet} ss - Google Sheets spreadsheet object
 * @param {string} tabName - Name of the sheet/tab to append to
 * @param {Array} rows - Array of arrays containing headers and data
 * @param {boolean} writeHeaderIfEmpty - Whether to write headers if sheet is empty
 * @returns {void}
 */
function EW_appendToTab(ss, tabName, rows, writeHeaderIfEmpty) {
  EW_trace('SHEET', `Append -> "${tabName}" rows=${rows.length}`);
  let sheet = ss.getSheetByName(tabName);
  if (!sheet) {
    EW_trace('SHEET', `Creating sheet "${tabName}"`);
    sheet = ss.insertSheet(tabName);
  }
  if (!rows || rows.length === 0) return;

  const incomingHeader = Array.isArray(rows[0]) ? rows[0].slice() : [];
  const incomingData = rows.slice(1).map(r => r.slice());
  const runDate = EW_getRunStamp();

  const lastRow = sheet.getLastRow();

  // First run on this tab
  if (writeHeaderIfEmpty && lastRow === 0) {
    const baseHeader = EW_ensureRequiredHeaders(incomingHeader, tabName);
    // Don't use EW_addGFHeaders - it adds plain text headers

    const width = baseHeader.length;
    const dataRows = incomingData.map(r => {
      // Add Run Date and Strategy at the beginning
      const row = [runDate, tabName, ...r];
      if (row.length < width) row.push(...Array(width - row.length).fill(''));
      return row;
    });

    sheet.getRange(1, 1, 1, width).setValues([baseHeader]);
    EW_trace('SHEET', `Wrote header (${width} cols)`);

    if (dataRows.length) {
      sheet.getRange(2, 1, dataRows.length, width).setValues(dataRows);
      EW_trace('SHEET', `Wrote ${dataRows.length} data rows`);
    }

    // Don't add GF headers as plain text - let the formulas create them
    // Create a header map that includes all expected columns
    const allLabels = [...EW_GF_LABELS, ...EW_TRACKING_LABELS];
    const fullHeaders = [...baseHeader, ...allLabels];
    const hdrMap = EW_headerMap(fullHeaders);
    
    // Plant ARRAYFORMULAs which will create the column headers
    EW_setGFArrayFormulas(sheet, hdrMap);
    EW_trace('SHEET', 'Applied Google Finance formulas');
    return;
  }



  // Subsequent runs: align to existing header
  // First ensure all columns exist
  const updatedHdrMap = EW_ensureAllColumnsExist(sheet);
  if (!updatedHdrMap) {
    EW_trace('SHEET', 'Failed to ensure columns exist', true);
    return;
  }
  
  // Re-read headers after potential column additions
  const sheetHeader = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(sheetHeader);
  const width = sheetHeader.length;

  // Ensure the sheet already has "Run Date" as first column (created on first run)
  const hasRunDate = (hdrMap.runDateCol === 1); // we create it as first col initially
  if (!hasRunDate) {
    EW_trace('SHEET', `Warning: "Run Date" not found as first column. Appending anyway.`, true);
  }

  const mapFromIncoming = EW_headerMap(incomingHeader);
  const aligned = incomingData.map(src => {
    const dst = Array(width).fill('');
    
    // Set Run Date - try mapped column first, then fallback to column 1
    if (hdrMap.runDateCol) {
      dst[hdrMap.runDateCol - 1] = runDate;
    } else if (sheetHeader[0] && String(sheetHeader[0]).toLowerCase().includes('run')) {
      // Fallback: if first column looks like Run Date but wasn't detected
      dst[0] = runDate;
    }
    
    // Set Strategy - try mapped column first, then fallback to column 2
    if (hdrMap.strategyCol) {
      dst[hdrMap.strategyCol - 1] = tabName;
    } else if (sheetHeader[1] && String(sheetHeader[1]).toLowerCase() === 'strategy') {
      dst[1] = tabName;
    }
    
    for (const [name, src1] of Object.entries(mapFromIncoming.byName)) {
      const dst1 = hdrMap.byName[name];
      if (!dst1) continue;
      dst[dst1 - 1] = src[src1 - 1] != null ? src[src1 - 1] : '';
    }
    return dst;
  });

  if (!aligned.length) return;

    // If any GF header exists but row 1 cell is empty (formula removed), replant
  if (hdrMap.tickerCol && (
      (hdrMap.priceCol && !sheet.getRange(1, hdrMap.priceCol).getFormula()) ||
      (hdrMap.volCol   && !sheet.getRange(1, hdrMap.volCol).getFormula())
    )) {
    EW_trace('GF', 'Detected missing GF formulas; replanting');
    EW_setGFArrayFormulas(sheet, hdrMap);
  }

  // Find the actual last row with data (not just formulas)
  // Check first few columns for actual data to determine the real last row
  let actualLastRow = 1; // Start at header row
  if (sheet.getLastRow() > 1) {
    // Get data from columns that should have actual values (not formulas)
    // Check columns like Run Date, Strategy, Ticker which are actual data columns
    const checkCols = [hdrMap.runDateCol, hdrMap.strategyCol, hdrMap.tickerCol].filter(c => c);
    if (checkCols.length > 0) {
      const maxRows = sheet.getLastRow();
      const checkCol = checkCols[0]; // Use first available column
      const colData = sheet.getRange(2, checkCol, maxRows - 1, 1).getValues();
      
      // Find last non-empty row
      for (let i = colData.length - 1; i >= 0; i--) {
        if (colData[i][0] !== '' && colData[i][0] !== null) {
          actualLastRow = i + 2; // +2 because we started at row 2
          break;
        }
      }
    }
  }

  const start = actualLastRow + 1;
  sheet.getRange(start, 1, aligned.length, width).setValues(aligned);
  EW_trace('SHEET', `Appended ${aligned.length} rows at row ${start} (actual last data row: ${actualLastRow})`);

  // Do NOT call any filler here; array formulas spill automatically.
}




// ======= HEADER MANAGEMENT =======

// Add our evaluation columns (exact labels used everywhere below)
const EW_GF_LABELS = [
  'GF_Name','GF_Price','GF_ChangePct','GF_High','GF_Low','GF_High52','GF_Low52',
  'GF_Volume','GF_AvgVol10','GF_MktCap','GF_PE','GF_Beta',
  'HV_30D','RVOL_10','Ret_5D','Ret_20D','GapPct'
];

// Add tracking columns for strategy success monitoring
const EW_TRACKING_LABELS = [
  'Days_To_Exp','Strike_Hit','Hit_Date','Max_Favorable','Min_Unfavorable',
  'Day0_Check','Day1_Check','Day2_Check','Day3_Check','Day4_Check','Day5_Check','Exp_Result',
  'Success_Score','Profit_Potential','Risk_Reward','Historical_High','Historical_Low',
  'Ever_Hit_Strike','First_Hit_Date','Last_Update','Total_Hit_Days',
  // Technical indicators (now arrays for Day0-Day5)
  'Hit_RSI','Hit_SMA20','Hit_SMA50','Hit_EMA9','Hit_EMA21','Hit_VWAP',
  'Hit_RVOL','Hit_ATR','Hit_PriceVsSMA20','Hit_PriceVsVWAP'
];

/**
 * Creates a mapping object from header row for easy column access
 * Maps header names to 1-based column indices and provides friendly column references
 * @param {Array} headerRow - Array of header names from first row
 * @returns {Object} Object with byName mapping and specific column references
 */
function EW_headerMap(headerRow) {
  const byName = {};               // raw key -> 1-based index
  const byNorm = {};               // normalized key -> 1-based index
  headerRow.forEach((h, i) => {
    const raw  = String(h || '').trim();
    const norm = EW_norm(raw);
    if (raw)  byName[raw.toLowerCase()] = i + 1;
    if (norm) byNorm[norm] = i + 1;
  });

  // Helper: first match among aliases (by normalized name)
  function find(aliases) {
    for (const a of aliases) {
      const ix = byNorm[EW_norm(a)];
      if (ix) return ix;
    }
    return null;
  }

  // Common aliases for upstream data
  const tickerCol   = find(['ticker','symbol','sym','underlying','root']);
  const runDateCol  = find(['Run Date','run date','rundate','dateadded','RunDate','RUNDATE']);
  // (add more if needed: expiration/strike/etc for dedupe later)

  // GF/derived columns we ourselves add — locate by exact labels or normalized
  const nameCol     = find(['GF_Name']);
  const priceCol    = find(['GF_Price']);
  const chgPctCol   = find(['GF_ChangePct']);
  const highCol     = find(['GF_High']);
  const lowCol      = find(['GF_Low']);
  const high52Col   = find(['GF_High52','GF_52w High']);
  const low52Col    = find(['GF_Low52','GF_52w Low']);
  const volCol      = find(['GF_Volume']);
  const avgVol10Col = find(['GF_AvgVol10','GF_Avg Vol 10']);
  const mcapCol     = find(['GF_MktCap','GF_Market Cap']);
  const peCol       = find(['GF_PE']);
  const betaCol     = find(['GF_Beta']);

  const hv30Col     = find(['HV_30D']);
  const rvol10Col   = find(['RVOL_10']);
  const ret5Col     = find(['Ret_5D']);
  const ret20Col    = find(['Ret_20D']);
  const gapPctCol   = find(['GapPct','Gap %']);

  // Tracking columns
  const daysToExpCol    = find(['Days_To_Exp']);
  const strikeHitCol    = find(['Strike_Hit']);
  const hitDateCol      = find(['Hit_Date']);
  const maxFavorableCol = find(['Max_Favorable']);
  const minUnfavorableCol = find(['Min_Unfavorable']);
  const day0CheckCol    = find(['Day0_Check']);
  const day1CheckCol    = find(['Day1_Check']);
  const day2CheckCol    = find(['Day2_Check']);
  const day3CheckCol    = find(['Day3_Check']);
  const day4CheckCol    = find(['Day4_Check']);
  const day5CheckCol    = find(['Day5_Check']);
  const expResultCol    = find(['Exp_Result']);
  const successScoreCol = find(['Success_Score']);
  // Removed profitPotentialCol - duplicates Max_Favorable
  const riskRewardCol   = find(['Risk_Reward']);
  
  // Enhanced historical tracking columns
  const historicalHighCol = find(['Historical_High']);
  const historicalLowCol  = find(['Historical_Low']);
  const everHitStrikeCol  = find(['Ever_Hit_Strike']);
  const firstHitDateCol   = find(['First_Hit_Date']);
  const lastUpdateCol     = find(['Last_Update']);
  const totalHitDaysCol   = find(['Total_Hit_Days']);
  // Peak_Profit_Date removed - using daily indicator arrays instead
  
  // Technical indicators at strike hit
  const hitRSICol         = find(['Hit_RSI']);
  const hitSMA20Col       = find(['Hit_SMA20']);
  const hitSMA50Col       = find(['Hit_SMA50']);
  const hitEMA9Col        = find(['Hit_EMA9']);
  const hitEMA21Col       = find(['Hit_EMA21']);
  const hitVWAPCol        = find(['Hit_VWAP']);
  const hitRVOLCol        = find(['Hit_RVOL']);
  const hitATRCol         = find(['Hit_ATR']);
  const hitPriceVsSMA20Col = find(['Hit_PriceVsSMA20']);
  const hitPriceVsVWAPCol = find(['Hit_PriceVsVWAP']);

  // Strategy and core data columns
  const strategyCol     = find(['strategy','Strategy']);
  const strikeCol       = find(['strike','Strike']);
  const expDateCol      = find(['expDate','expiration','Expiration']);
  
  // Spread-specific columns
  const longStrikeCol   = find(['longStrike','long strike','Long Strike']);
  const shortStrikeCol  = find(['shortStrike','short strike','Short Strike']);
  const breakevenCol    = find(['breakeven','Breakeven']);
  const maxProfitCol    = find(['maxProfit','max profit','Max Profit']);
  const maxLossCol      = find(['maxLoss','max loss','Max Loss']);
  
  // API columns that vary by strategy
  const companyCol      = find(['company','Company']);
  const lastTradeCol    = find(['lastTrade','last trade','Last Trade']);
  const bidCol          = find(['bid','Bid']);
  const askCol          = find(['ask','Ask']);
  const openInterestCol = find(['openInterest','open interest','Open Interest']);
  const volumeCol       = find(['volume','Volume']);
  const nextEPSDateCol  = find(['earningsDate','earnings date','Earnings Date','nextEPSDate','next eps date','Next EPS Date']);
  const releaseTimeCol  = find(['earningsTime','earnings time','Earnings Time','releaseTime','release time','Release Time']);
  const lastEPSTimeCol  = find(['lastEPSTime','last eps time','Last EPS Time']);
  const confirmDateCol  = find(['confirmDate','confirm date','Confirm Date']);
  const optionDateCol   = find(['optionDate','option date','Option Date']);
  const scoreCol        = find(['score','Score']);
  const epsImpactCol    = find(['epsImpact','eps impact','EPS Impact']);
  const avgEPSMoveCol   = find(['avgEPSMove','avg eps move','Avg EPS Move']);
  const avgVolumeCol    = find(['avgVolume','avg volume','Avg Volume']);
  
  // Covered Call specific
  const cushionCol      = find(['cushion','Cushion']);
  const upTargetCol     = find(['upTarget','up target','Up Target']);
  const callAwayCol     = find(['callAway','call away','Call Away']);
  const downTargetCol   = find(['downTarget','down target','Down Target']);
  const callAwayReturnCol = find(['callAwayReturn','call away return','Call Away Return']);
  const ewRatingCol     = find(['ewRating','ew rating','EW Rating']);
  const exDivDateCol    = find(['exDivDate','ex div date','Ex Div Date']);
  const payoutCol       = find(['payout','Payout']);
  
  // Bull/Bear Spread specific
  const maxReturnCol    = find(['maxReturn','max return','Max Return']);
  const maxRiskCol      = find(['maxRisk','max risk','Max Risk']);
  const shortBidCol     = find(['shortBid','short bid','Short Bid']);
  const longAskCol      = find(['longAsk','long ask','Long Ask']);
  const totRatingsCol   = find(['totRatings','tot ratings','Tot Ratings']);
  const netRatingsCol   = find(['netRatings','net ratings','Net Ratings']);
  
  // Entry indicators (not from API, added by our processing)
  const entryRSICol     = find(['Entry_RSI']);
  const entryEMA9Col    = find(['Entry_EMA9']);
  const entryEMA21Col   = find(['Entry_EMA21']);
  const entrySMA20Col   = find(['Entry_SMA20']);
  const entrySMA50Col   = find(['Entry_SMA50']);
  const entryVWAPCol    = find(['Entry_VWAP']);
  const entryRVOLCol    = find(['Entry_RVOL']);
  const entryATRCol     = find(['Entry_ATR']);
  const entryPriceVsSMA20Col = find(['Entry_PriceVsSMA20']);
  const entryPriceVsVWAPCol = find(['Entry_PriceVsVWAP']);

  return {
    byName, byNorm,
    runDateCol, tickerCol, strategyCol, strikeCol, expDateCol,
    longStrikeCol, shortStrikeCol, breakevenCol, maxProfitCol, maxLossCol,
    nameCol, priceCol, chgPctCol, highCol, lowCol, high52Col, low52Col,
    volCol, avgVol10Col, mcapCol, peCol, betaCol,
    hv30Col, rvol10Col, ret5Col, ret20Col, gapPctCol,
    daysToExpCol, strikeHitCol, hitDateCol, maxFavorableCol, minUnfavorableCol,
    day0CheckCol, day1CheckCol, day2CheckCol, day3CheckCol, day4CheckCol, day5CheckCol, expResultCol,
    successScoreCol, riskRewardCol,
    historicalHighCol, historicalLowCol, everHitStrikeCol, firstHitDateCol,
    lastUpdateCol, totalHitDaysCol,
    hitRSICol, hitSMA20Col, hitSMA50Col, hitEMA9Col, hitEMA21Col,
    hitVWAPCol, hitRVOLCol, hitATRCol, hitPriceVsSMA20Col, hitPriceVsVWAPCol,
    // API columns
    companyCol, lastTradeCol, bidCol, askCol, openInterestCol, volumeCol,
    nextEPSDateCol, releaseTimeCol, lastEPSTimeCol, confirmDateCol, optionDateCol,
    scoreCol, epsImpactCol, avgEPSMoveCol, avgVolumeCol,
    // Covered Call specific
    cushionCol, upTargetCol, callAwayCol, downTargetCol, callAwayReturnCol,
    ewRatingCol, exDivDateCol, payoutCol,
    // Bull/Bear Spread specific
    maxReturnCol, maxRiskCol, shortBidCol, longAskCol, totRatingsCol, netRatingsCol,
    // Entry indicators
    entryRSICol, entryEMA9Col, entryEMA21Col, entrySMA20Col, entrySMA50Col,
    entryVWAPCol, entryRVOLCol, entryATRCol, entryPriceVsSMA20Col, entryPriceVsVWAPCol,
    width: headerRow.length
  };
}


// ======= GOOGLEFINANCE ARRAY FORMULAS =======

/**
 * Ensures all Google Finance and tracking columns exist in the sheet
 * Adds any missing columns and preserves existing data
 * @param {SpreadsheetSheet} sheet - The sheet to check and update
 * @returns {Object} Updated header map after adding columns
 */
function EW_ensureAllColumnsExist(sheet) {
  if (!sheet || sheet.getLastRow() === 0) {
    return null;
  }
  
  const lastCol = sheet.getLastColumn();
  const lastRow = sheet.getLastRow();
  const currentHeaders = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  let hdrMap = EW_headerMap(currentHeaders);
  
  // Check if we need to add columns
  // IMPORTANT: Don't add Google Finance columns here - they should be formulas, not plain text
  const nonFormulaColumns = ['Strategy', 'Run Date']; // Only add non-formula columns as plain text
  const missingColumns = [];
  
  // Check each expected non-formula column
  for (const label of nonFormulaColumns) {
    let found = false;
    
    // Check if column exists (case-insensitive)
    const colIndex = hdrMap.byName[label.toLowerCase()];
    if (colIndex) {
      // Check if the header is corrupted (#ERROR!, #REF!, etc)
      const actualHeader = currentHeaders[colIndex - 1];
      if (actualHeader && !actualHeader.toString().startsWith('#')) {
        found = true;
      }
    }
    
    if (!found) {
      missingColumns.push(label);
    }
  }
  
  if (missingColumns.length === 0) {
    EW_trace('COLUMNS', 'All columns already exist');
    return hdrMap;
  }
  
  EW_trace('COLUMNS', `Adding ${missingColumns.length} missing columns: ${missingColumns.join(', ')}`);
  
  // Get all existing data
  const allData = lastRow > 1 ? 
    sheet.getRange(1, 1, lastRow, lastCol).getValues() : 
    [currentHeaders];
  
  // Add new columns to each row
  const updatedData = allData.map((row, rowIndex) => {
    const newRow = [...row];
    if (rowIndex === 0) {
      // Header row - add missing column names
      newRow.push(...missingColumns);
    } else {
      // Data rows - add empty cells
      newRow.push(...new Array(missingColumns.length).fill(''));
    }
    return newRow;
  });
  
  // Clear sheet and write updated data
  sheet.clear();
  const newWidth = lastCol + missingColumns.length;
  sheet.getRange(1, 1, lastRow, newWidth).setValues(updatedData);
  
  // Return updated header map
  const newHeaders = sheet.getRange(1, 1, 1, newWidth).getValues()[0];
  return EW_headerMap(newHeaders);
}

/**
 * Set up ARRAYFORMULA functions for GOOGLEFINANCE data and tracking columns
 * Plants formulas in row 1 that automatically populate down for all rows
 * @param {Sheet} sheet - The Google Sheets sheet object
 * @param {Object} hdrMap - Header mapping object from EW_headerMap function
 * @returns {void}
 */
function EW_setGFArrayFormulas(sheet, hdrMap) {
  if (!hdrMap.tickerCol) {
    EW_trace('GF', 'No "ticker" column found; skipping ARRAYFORMULAs');
    return;
  }
  const tLtr   = EW_columnToLetter(hdrMap.tickerCol);
  const tRange = `$${tLtr}2:$${tLtr}`;

  function setHeaderArray(colIndex, headerLabel, innerExpr) {
    if (!colIndex) return;
    const cell = sheet.getRange(1, colIndex);
    // Use SEQUENCE to get row indices for proper column access
    const numRows = `ROWS(${tRange})`;
    cell.setFormula(`={"${headerLabel}"; MAP(SEQUENCE(${numRows}), LAMBDA(i, LET(t, INDEX(${tRange}, i), IF(t="",,${innerExpr}))))}`);
  }
  
  // Helper for formulas that need to access multiple columns
  function setHeaderArrayMultiCol(colIndex, headerLabel, formula) {
    if (!colIndex) return;
    const cell = sheet.getRange(1, colIndex);
    const numRows = `ROWS(${tRange})`;
    cell.setFormula(`={"${headerLabel}"; MAP(SEQUENCE(${numRows}), LAMBDA(i, ${formula}))}`);
  }

  // GOOGLEFINANCE attributes
  setHeaderArray(hdrMap.nameCol,   'GF_Name',      `IFERROR(GOOGLEFINANCE(t,"name"),)`);
  setHeaderArray(hdrMap.priceCol,  'GF_Price',     `IFERROR(GOOGLEFINANCE(t,"price"),)`);
  setHeaderArray(hdrMap.chgPctCol, 'GF_ChangePct', `IFERROR(GOOGLEFINANCE(t,"changepct"),)`);
  setHeaderArray(hdrMap.highCol,   'GF_High',      `IFERROR(GOOGLEFINANCE(t,"high"),)`);
  setHeaderArray(hdrMap.lowCol,    'GF_Low',       `IFERROR(GOOGLEFINANCE(t,"low"),)`);
  setHeaderArray(hdrMap.high52Col, 'GF_High52',    `IFERROR(GOOGLEFINANCE(t,"high52"),)`);
  setHeaderArray(hdrMap.low52Col,  'GF_Low52',     `IFERROR(GOOGLEFINANCE(t,"low52"),)`);
  setHeaderArray(hdrMap.volCol,    'GF_Volume',    `IFERROR(GOOGLEFINANCE(t,"volume"),)`);
  setHeaderArray(hdrMap.mcapCol,   'GF_MktCap',    `IFERROR(GOOGLEFINANCE(t,"marketcap"),)`);
  setHeaderArray(hdrMap.peCol,     'GF_PE',        `IFERROR(GOOGLEFINANCE(t,"pe"),)`);
  setHeaderArray(hdrMap.betaCol,   'GF_Beta',      `IFERROR(GOOGLEFINANCE(t,"beta"),)`);

  // 10-day average volume
  setHeaderArray(
    hdrMap.avgVol10Col, 'GF_AvgVol10',
    `LET(
       vh, IFERROR(GOOGLEFINANCE(t,"volume",TODAY()-30,TODAY()),),
       n, ROWS(vh)-1,
       IF(n<10,,AVERAGE(INDEX(vh,SEQUENCE(10,1,n-8),2)))
     )`
  );

  // HV_30D (annualized, %)
  setHeaderArray(
    hdrMap.hv30Col, 'HV_30D',
    `LET(
       data, IFERROR(GOOGLEFINANCE(t,"price",TODAY()-60,TODAY()),),
       n, ROWS(data),
       IF(n<32,,LET(
         returns, MAP(SEQUENCE(30), LAMBDA(i, LN(INDEX(data,n-i+1,2)/INDEX(data,n-i,2)))),
         SQRT(252)*STDEV(returns)*100
       ))
     )`
  );

  // RVOL_10 (current vol / 10-day avg vol)
  setHeaderArray(
    hdrMap.rvol10Col, 'RVOL_10',
    `LET(
       cv, IFERROR(GOOGLEFINANCE(t,"volume"),),
       vh, IFERROR(GOOGLEFINANCE(t,"volume",TODAY()-30,TODAY()),),
       n, ROWS(vh)-1,
       av, IF(n<10,,AVERAGE(INDEX(vh,SEQUENCE(10,1,n-8),2))),
       IF(OR(cv="",av=""),,cv/av)
     )`
  );

  // Ret_5D
  setHeaderArray(
    hdrMap.ret5Col, 'Ret_5D',
    `LET(
       d, IFERROR(GOOGLEFINANCE(t,"price",TODAY()-20,TODAY()),),
       n, ROWS(d),
       IF(n<7,,(INDEX(d,n,2)/INDEX(d,n-5,2)-1)*100)
     )`
  );

  // Ret_20D
  setHeaderArray(
    hdrMap.ret20Col, 'Ret_20D',
    `LET(
       d, IFERROR(GOOGLEFINANCE(t,"price",TODAY()-45,TODAY()),),
       n, ROWS(d),
       IF(n<22,,(INDEX(d,n,2)/INDEX(d,n-20,2)-1)*100)
     )`
  );

  // GapPct unchanged
  setHeaderArray(
    hdrMap.gapPctCol, 'GapPct',
    `LET(px, IFERROR(GOOGLEFINANCE(t,"price"),),
         op, IFERROR(GOOGLEFINANCE(t,"priceopen"),),
         IF(OR(px="",op=""),,(px-op)/op*100))`
  );

  // ===== ENHANCED HISTORICAL TRACKING FORMULAS =====
  
  // Historical High (never resets - captures peak favorable price)
  setHeaderArrayMultiCol(
    hdrMap.historicalHighCol, 'Historical_High',
    `LET(
       ticker, INDEX(${tRange}, i),
       currentPrice, IFERROR(GOOGLEFINANCE(ticker,"price"),0),
       prevHigh, INDEX($${EW_columnToLetter(hdrMap.historicalHighCol)}2:$${EW_columnToLetter(hdrMap.historicalHighCol)}, i),
       IF(OR(ticker="", currentPrice=0), prevHigh, MAX(IF(prevHigh="", currentPrice, prevHigh), currentPrice))
     )`
  );

  // Historical Low (never resets - captures worst unfavorable price)
  setHeaderArrayMultiCol(
    hdrMap.historicalLowCol, 'Historical_Low',
    `LET(
       ticker, INDEX(${tRange}, i),
       currentPrice, IFERROR(GOOGLEFINANCE(ticker,"price"),0),
       prevLow, INDEX($${EW_columnToLetter(hdrMap.historicalLowCol)}2:$${EW_columnToLetter(hdrMap.historicalLowCol)}, i),
       IF(OR(ticker="", currentPrice=0), prevLow, MIN(IF(prevLow="", currentPrice, prevLow), currentPrice))
     )`
  );

  // Ever Hit Strike (handles both single strikes and spreads)
  setHeaderArrayMultiCol(
    hdrMap.everHitStrikeCol, 'Ever_Hit_Strike',
    `LET(
       ticker, INDEX(${tRange}, i),
       strategy, UPPER(INDEX($${EW_columnToLetter(hdrMap.strategyCol)}2:$${EW_columnToLetter(hdrMap.strategyCol)}, i)),
       strike, IF(${hdrMap.strikeCol ? 'TRUE' : 'FALSE'}, INDEX($${EW_columnToLetter(hdrMap.strikeCol || 1)}2:$${EW_columnToLetter(hdrMap.strikeCol || 1)}, i), ""),
       longStrike, IF(${hdrMap.longStrikeCol ? 'TRUE' : 'FALSE'}, INDEX($${EW_columnToLetter(hdrMap.longStrikeCol || 1)}2:$${EW_columnToLetter(hdrMap.longStrikeCol || 1)}, i), ""),
       shortStrike, IF(${hdrMap.shortStrikeCol ? 'TRUE' : 'FALSE'}, INDEX($${EW_columnToLetter(hdrMap.shortStrikeCol || 1)}2:$${EW_columnToLetter(hdrMap.shortStrikeCol || 1)}, i), ""),
       currentPrice, IFERROR(GOOGLEFINANCE(ticker,"price"),0),
       historicalHigh, INDEX($${EW_columnToLetter(hdrMap.historicalHighCol)}2:$${EW_columnToLetter(hdrMap.historicalHighCol)}, i),
       historicalLow, INDEX($${EW_columnToLetter(hdrMap.historicalLowCol)}2:$${EW_columnToLetter(hdrMap.historicalLowCol)}, i),
       strikeHit, INDEX($${EW_columnToLetter(hdrMap.strikeHitCol)}2:$${EW_columnToLetter(hdrMap.strikeHitCol)}, i),
       
       IF(ticker="", "",
         IF(strikeHit="HIT", "TRUE",
           IF(OR(REGEXMATCH(strategy, "BULL SPREAD"), REGEXMATCH(strategy, "BEAR SPREAD")),
             LET(
               primaryStrike, IF(longStrike<>"", longStrike, strike),
               secondaryStrike, shortStrike,
               IF(REGEXMATCH(strategy, "BULL SPREAD"),
                 IF(AND(historicalHigh >= primaryStrike, historicalHigh < secondaryStrike), "TRUE", "FALSE"),
                 IF(REGEXMATCH(strategy, "BEAR SPREAD"),
                   IF(AND(historicalLow <= primaryStrike, historicalLow > secondaryStrike), "TRUE", "FALSE"),
                   "FALSE"
                 )
               )
             ),
             IF(OR(REGEXMATCH(strategy, "LONG CALL"), REGEXMATCH(strategy, "BULL")),
               IF(historicalHigh >= strike, "TRUE", "FALSE"),
               IF(OR(REGEXMATCH(strategy, "LONG PUT"), REGEXMATCH(strategy, "BEAR")),
                 IF(historicalLow <= strike, "TRUE", "FALSE"),
                 IF(OR(REGEXMATCH(strategy, "SHORT CALL"), REGEXMATCH(strategy, "COVERED")),
                   IF(historicalHigh < strike, "FAVORABLE", "UNFAVORABLE"),
                   IF(REGEXMATCH(strategy, "SHORT PUT"),
                     IF(historicalLow > strike, "FAVORABLE", "UNFAVORABLE"),
                     "UNKNOWN"
                   )
                 )
               )
             )
           )
         )
       )
     )`
  );

  // First Hit Date (permanent - never changes once set)
  setHeaderArrayMultiCol(
    hdrMap.firstHitDateCol, 'First_Hit_Date',
    `LET(
       ticker, INDEX(${tRange}, i),
       everHit, INDEX($${EW_columnToLetter(hdrMap.everHitStrikeCol)}2:$${EW_columnToLetter(hdrMap.everHitStrikeCol)}, i),
       prevFirstHit, INDEX($${EW_columnToLetter(hdrMap.firstHitDateCol)}2:$${EW_columnToLetter(hdrMap.firstHitDateCol)}, i),
       
       IF(ticker="", "",
         IF(AND(OR(everHit="TRUE", everHit="FAVORABLE"), prevFirstHit=""), 
           TEXT(TODAY(), "yyyy-mm-dd"), 
           prevFirstHit
         )
       )
     )`
  );

  // Last Update timestamp
  setHeaderArray(
    hdrMap.lastUpdateCol, 'Last_Update',
    `TEXT(NOW(), "yyyy-mm-dd hh:mm:ss")`
  );

  // Total Hit Days (count of days strike was favorable)
  setHeaderArrayMultiCol(
    hdrMap.totalHitDaysCol, 'Total_Hit_Days',
    `LET(
       ticker, INDEX(${tRange}, i),
       everHit, INDEX($${EW_columnToLetter(hdrMap.everHitStrikeCol)}2:$${EW_columnToLetter(hdrMap.everHitStrikeCol)}, i),
       prevTotal, INDEX($${EW_columnToLetter(hdrMap.totalHitDaysCol)}2:$${EW_columnToLetter(hdrMap.totalHitDaysCol)}, i),
       currentHit, INDEX($${EW_columnToLetter(hdrMap.strikeHitCol)}2:$${EW_columnToLetter(hdrMap.strikeHitCol)}, i),
       
       IF(ticker="", "",
         IF(OR(currentHit="HIT", currentHit="FAVORABLE"), 
           IF(prevTotal="", 1, prevTotal + 1), 
           IF(prevTotal="", 0, prevTotal)
         )
       )
     )`
  );

  // Days to Expiration
  setHeaderArrayMultiCol(
    hdrMap.daysToExpCol, 'Days_To_Exp',
    `LET(
       ticker, INDEX(${tRange}, i),
       expDate, INDEX($${EW_columnToLetter(hdrMap.expDateCol)}2:$${EW_columnToLetter(hdrMap.expDateCol)}, i),
       IF(OR(ticker="", expDate=""), "", 
         IF(ISNUMBER(expDate), 
           MAX(expDate - TODAY()), 
           IFERROR(MAX(DATEVALUE(expDate) - TODAY()), 0)
         )
       )
     )`
  );

  // Strike_Hit is now populated by scripts (not a formula column)
  // See EW_updateActiveStrikeHits() for active positions
  // See EW_backfillHistoricalTracking() for expired positions

  // Enhanced Success Score with historical data
  setHeaderArrayMultiCol(
    hdrMap.successScoreCol, 'Success_Score',
    `LET(
       ticker, INDEX(${tRange}, i),
       everHit, INDEX($${EW_columnToLetter(hdrMap.everHitStrikeCol)}2:$${EW_columnToLetter(hdrMap.everHitStrikeCol)}, i),
       daysToExp, INDEX($${EW_columnToLetter(hdrMap.daysToExpCol)}2:$${EW_columnToLetter(hdrMap.daysToExpCol)}, i),
       totalHitDays, INDEX($${EW_columnToLetter(hdrMap.totalHitDaysCol)}2:$${EW_columnToLetter(hdrMap.totalHitDaysCol)}, i),
       rvol, INDEX($${EW_columnToLetter(hdrMap.rvol10Col)}2:$${EW_columnToLetter(hdrMap.rvol10Col)}, i),
       
       IF(OR(ticker="", everHit="", daysToExp=""), "",
         LET(
           hitScore, IF(OR(everHit="TRUE", everHit="FAVORABLE"), 60, 
                        IF(everHit="UNFAVORABLE", 20, 40)),
           timeScore, MIN(30, MAX(0, daysToExp * 2)),
           volScore, MIN(10, MAX(0, (rvol - 1) * 10)),
           consistencyScore, MIN(20, totalHitDays * 2),
           hitScore + timeScore + volScore + consistencyScore
         )
       )
     )`
  );

  EW_trace('GF', 'ARRAYFORMULAs set (no DROP/TAKE)');
}

// ===== SUCCESS TRACKING & REPORTING FUNCTIONS =====



/**
 * One-time fix function to add Strategy column to all existing sheets
 * This will insert Strategy as the second column and populate it with the sheet name
 * @returns {void}
 */
function EW_fixAddStrategyColumn() {
  EW_trace('FIX', 'Starting one-time fix to add Strategy column', true);
  const ss = SpreadsheetApp.getActive();
  const endpoints = EW.STRATEGY_ENDPOINTS;
  let sheetsFixed = 0;
  
  for (const tabName of Object.keys(endpoints)) {
    const sheet = ss.getSheetByName(tabName);
    if (!sheet || sheet.getLastRow() === 0) {
      EW_trace('FIX', `Skipping ${tabName} - sheet empty or doesn't exist`);
      continue;
    }
    
    try {
      const lastRow = sheet.getLastRow();
      const lastCol = sheet.getLastColumn();
      const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
      const hdrMap = EW_headerMap(headers);
      
      // Check if Strategy column already exists
      if (hdrMap.strategyCol) {
        EW_trace('FIX', `${tabName} already has Strategy column at position ${hdrMap.strategyCol}`);
        continue;
      }
      
      EW_trace('FIX', `Adding Strategy column to ${tabName}`);
      
      // Get all existing data
      const allData = sheet.getRange(1, 1, lastRow, lastCol).getValues();
      
      // Insert Strategy as second column
      const newData = allData.map((row, rowIndex) => {
        const newRow = [...row];
        if (rowIndex === 0) {
          // Header row - insert "Strategy" after Run Date
          newRow.splice(1, 0, 'Strategy');
        } else {
          // Data rows - insert the sheet name (strategy)
          newRow.splice(1, 0, tabName);
        }
        return newRow;
      });
      
      // Clear sheet and write updated data
      sheet.clear();
      const newWidth = lastCol + 1;
      sheet.getRange(1, 1, lastRow, newWidth).setValues(newData);
      
      // Update header map with new columns
      const newHeaders = sheet.getRange(1, 1, 1, newWidth).getValues()[0];
      const newHdrMap = EW_headerMap(newHeaders);
      
      // Ensure all other columns exist
      const finalHdrMap = EW_ensureAllColumnsExist(sheet);
      
      // Re-apply formulas with updated header map
      if (finalHdrMap) {
        EW_setGFArrayFormulas(sheet, finalHdrMap);
      }
      
      sheetsFixed++;
      EW_trace('FIX', `Fixed ${tabName} - added Strategy column and refreshed formulas`);
      
    } catch (e) {
      EW_trace('FIX', `Error fixing ${tabName}: ${e.message}`, true);
    }
  }
  
  const msg = sheetsFixed > 0 ? 
    `Fixed ${sheetsFixed} sheets - added Strategy column and refreshed formulas` : 
    'All sheets already have Strategy column or no sheets needed fixing';
  
  EW_trace('FIX', msg, true);
  EW_safeAlert('Strategy Column Fix Complete', msg);
}

/**
 * Complete sheet repair - removes all GF/error columns and recreates them
 * 1. Removes all Google Finance columns
 * 2. Removes all corrupted columns (#ERROR!, #REF!)
 * 3. Adds Strategy column if missing
 * 4. Re-applies all formulas fresh
 * @returns {void}
 */
function EW_completeSheetRepair() {
  EW_trace('REPAIR', 'Starting sheet repair - delete and recreate all GF columns', true);
  const ss = SpreadsheetApp.getActive();
  const endpoints = EW.STRATEGY_ENDPOINTS;
  let sheetsRepaired = 0;
  
  for (const tabName of Object.keys(endpoints)) {
    const sheet = ss.getSheetByName(tabName);
    if (!sheet || sheet.getLastRow() === 0) {
      EW_trace('REPAIR', `Skipping ${tabName} - sheet empty or doesn't exist`);
      continue;
    }
    
    try {
      const lastRow = sheet.getLastRow();
      const lastCol = sheet.getLastColumn();
      
      if (lastRow === 0 || lastCol === 0) {
        EW_trace('REPAIR', `${tabName} has no data, skipping`);
        continue;
      }
      
      // Get headers
      const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
      
      // List of ALL Google Finance and tracking columns (both formula and plain text)
      // These will be removed and re-added in the correct order
      const allGFAndTrackingColumns = [
        // Google Finance columns (with formulas)
        'GF_Name', 'GF_Price', 'GF_ChangePct', 'GF_High', 'GF_Low', 
        'GF_High52', 'GF_Low52', 'GF_Volume', 'GF_AvgVol10', 'GF_MktCap', 
        'GF_PE', 'GF_Beta', 'HV_30D', 'RVOL_10', 'Ret_5D', 'Ret_20D', 'GapPct',
        // Tracking columns with formulas
        'Historical_High', 'Historical_Low', 'Ever_Hit_Strike', 
        'First_Hit_Date', 'Last_Update', 'Total_Hit_Days',
        'Days_To_Exp', 'Success_Score',
        // Plain text tracking columns (for success reports and scripts)
        'Strike_Hit', 'Hit_Date', 'Max_Favorable', 'Min_Unfavorable', 
        'Day0_Check', 'Day1_Check', 'Day2_Check', 'Day3_Check', 'Day4_Check', 'Day5_Check',
        'Exp_Result', 'Profit_Potential', 'Risk_Reward', 
        // Technical indicators (now arrays for Day0-Day5)
        'Hit_RSI','Hit_SMA20','Hit_SMA50','Hit_EMA9','Hit_EMA21','Hit_VWAP',
        'Hit_RVOL','Hit_ATR','Hit_PriceVsSMA20','Hit_PriceVsVWAP'
      ];
      const columnsToRemoveLower = allGFAndTrackingColumns.map(c => c.toLowerCase());
      
      // Delete columns from right to left to maintain column indexes
      const columnsToDelete = [];
      headers.forEach((header, index) => {
        const headerStr = header ? header.toString() : '';
        const headerLower = headerStr.toLowerCase();
        
        if (headerStr.startsWith('#') || columnsToRemoveLower.includes(headerLower)) {
          columnsToDelete.push(index + 1); // 1-based column number
          EW_trace('REPAIR', `${tabName}: Will delete column "${header}" at position ${index + 1}`);
        }
      });
      
      // Sort columns to delete in reverse order (right to left)
      columnsToDelete.sort((a, b) => b - a);
      
      // Delete columns one by one from right to left
      columnsToDelete.forEach(colNum => {
        sheet.deleteColumn(colNum);
      });
      
      EW_trace('REPAIR', `${tabName}: Deleted ${columnsToDelete.length} columns`);
      
      // Ensure Strategy column exists
      let currentHeaders = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      let hdrMap = EW_headerMap(currentHeaders);
      
      if (!hdrMap.strategyCol) {
        EW_trace('REPAIR', `${tabName}: Adding Strategy column`);
        
        // Insert Strategy column as the second column
        sheet.insertColumnBefore(2);
        
        // Set header
        sheet.getRange(1, 2).setValue('Strategy');
        
        // Fill Strategy column with the tab name
        const dataRows = sheet.getLastRow() - 1;
        if (dataRows > 0) {
          const strategyValues = Array(dataRows).fill([tabName]);
          sheet.getRange(2, 2, dataRows, 1).setValues(strategyValues);
        }
      }
      
      // Get current headers after modifications
      const cleanedHeaders = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      
      // Define all columns in the correct order
      const allGFColumns = [
        'GF_Name','GF_Price','GF_ChangePct','GF_High','GF_Low','GF_High52','GF_Low52',
        'GF_Volume','GF_AvgVol10','GF_MktCap','GF_PE','GF_Beta',
        'HV_30D','RVOL_10','Ret_5D','Ret_20D','GapPct'
      ];
      
      const trackingFormulaColumns = [
        'Days_To_Exp','Success_Score','Historical_High','Historical_Low',
        'Ever_Hit_Strike','First_Hit_Date','Last_Update','Total_Hit_Days'
      ];
      
      const trackingPlainTextColumns = [
        'Strike_Hit','Hit_Date','Max_Favorable','Min_Unfavorable',
        'Day0_Check','Day1_Check','Day2_Check','Day3_Check','Day4_Check','Day5_Check',
        'Exp_Result','Profit_Potential','Risk_Reward',
        // Technical indicators (now arrays for Day0-Day5)
        'Hit_RSI','Hit_SMA20','Hit_SMA50','Hit_EMA9','Hit_EMA21','Hit_VWAP',
        'Hit_RVOL','Hit_ATR','Hit_PriceVsSMA20','Hit_PriceVsVWAP'
      ];
      
      // Add plain text headers first (these won't have formulas)
      const currentColCount = sheet.getLastColumn();
      const newHeaders = [...trackingPlainTextColumns];
      
      if (newHeaders.length > 0) {
        // Append the new headers
        sheet.getRange(1, currentColCount + 1, 1, newHeaders.length).setValues([newHeaders]);
      }
      
      // Create header map with all columns for formula application
      const updatedHeaders = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      const withAllColumns = [...updatedHeaders, ...allGFColumns, ...trackingFormulaColumns];
      const finalHdrMap = EW_headerMap(withAllColumns);
      
      // Apply formulas - this will create the formula column headers
      EW_setGFArrayFormulas(sheet, finalHdrMap);
      
      sheetsRepaired++;
      EW_trace('REPAIR', `${tabName}: Successfully repaired`);
      
    } catch (e) {
      EW_trace('REPAIR', `Error repairing ${tabName}: ${e.message}`, true);
    }
  }
  
  const msg = sheetsRepaired > 0 ? 
    `Successfully repaired ${sheetsRepaired} sheets - deleted and recreated all GF columns` :
    'No sheets needed repair';
  
  EW_safeAlert('Sheet Repair Complete', msg);
  EW_trace('REPAIR', msg, true);
}

/**
 * Targeted column removal - removes only specific formula columns without touching data
 * This is a safer alternative to complete sheet repair
 * @param {string} sheetName - Optional specific sheet name to repair
 * @returns {void}
 */
function EW_removeFormulaColumns(sheetName = null) {
  EW_trace('REMOVE_COLS', 'Starting targeted formula column removal', true);
  const ss = SpreadsheetApp.getActive();
  const endpoints = EW.STRATEGY_ENDPOINTS;
  let sheetsProcessed = 0;
  let totalColumnsRemoved = 0;
  
  const sheetsToProcess = sheetName ? [sheetName] : Object.keys(endpoints);
  
  for (const tabName of sheetsToProcess) {
    const sheet = ss.getSheetByName(tabName);
    if (!sheet || sheet.getLastRow() === 0) {
      EW_trace('REMOVE_COLS', `Skipping ${tabName} - sheet empty or doesn't exist`);
      continue;
    }
    
    try {
      const lastRow = sheet.getLastRow();
      const lastCol = sheet.getLastColumn();
      
      if (lastRow === 0 || lastCol === 0) {
        EW_trace('REMOVE_COLS', `${tabName} has no data, skipping`);
        continue;
      }
      
      // Get headers
      const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
      
      // Only formula columns to remove (not plain text tracking columns)
      const formulaColumnsToRemove = [
        // Google Finance columns (with formulas)
        'GF_Name', 'GF_Price', 'GF_ChangePct', 'GF_High', 'GF_Low', 
        'GF_High52', 'GF_Low52', 'GF_Volume', 'GF_AvgVol10', 'GF_MktCap', 
        'GF_PE', 'GF_Beta', 'HV_30D', 'RVOL_10', 'Ret_5D', 'Ret_20D', 'GapPct',
        // Tracking columns with formulas only
        'Historical_High', 'Historical_Low', 'Ever_Hit_Strike', 
        'First_Hit_Date', 'Last_Update', 'Total_Hit_Days',
        'Days_To_Exp', 'Success_Score'
      ];
      const columnsToRemoveLower = formulaColumnsToRemove.map(c => c.toLowerCase());
      
      // Identify columns to delete
      const columnsToDelete = [];
      headers.forEach((header, index) => {
        const headerStr = header ? header.toString() : '';
        const headerLower = headerStr.toLowerCase();
        
        // Only remove formula columns or error columns
        if (headerStr.startsWith('#') || columnsToRemoveLower.includes(headerLower)) {
          columnsToDelete.push(index + 1); // 1-based column number
          EW_trace('REMOVE_COLS', `${tabName}: Will delete column "${header}" at position ${index + 1}`);
        }
      });
      
      if (columnsToDelete.length === 0) {
        EW_trace('REMOVE_COLS', `${tabName}: No formula columns found to remove`);
        continue;
      }
      
      // Sort columns to delete in reverse order (right to left)
      columnsToDelete.sort((a, b) => b - a);
      
      // Delete columns one by one from right to left
      columnsToDelete.forEach(colNum => {
        sheet.deleteColumn(colNum);
      });
      
      totalColumnsRemoved += columnsToDelete.length;
      sheetsProcessed++;
      EW_trace('REMOVE_COLS', `${tabName}: Removed ${columnsToDelete.length} formula columns`);
      
    } catch (e) {
      EW_trace('REMOVE_COLS', `Error processing ${tabName}: ${e.message}`, true);
    }
  }
  
  const msg = sheetsProcessed > 0 ? 
    `Successfully removed ${totalColumnsRemoved} formula columns from ${sheetsProcessed} sheets` :
    'No formula columns found to remove';
  
  EW_trace('REMOVE_COLS', msg, true);
  EW_safeAlert('Formula Column Removal Complete', msg);
}

/**
 * Updates the Success Report by first refreshing all formulas
 * @returns {void}
 */
function EW_updateSuccessReport() {
  EW_trace('REPORT', 'Updating success report - refreshing formulas first...', true);
  
  // First ensure all columns exist and formulas are up to date
  const ss = SpreadsheetApp.getActive();
  const endpoints = EW.STRATEGY_ENDPOINTS;
  
  for (const tabName of Object.keys(endpoints)) {
    const sheet = ss.getSheetByName(tabName);
    if (!sheet || sheet.getLastRow() === 0) continue;
    
    const updatedHdrMap = EW_ensureAllColumnsExist(sheet);
    if (updatedHdrMap) {
      // Re-apply Google Finance formulas with updated header map
      EW_setGFArrayFormulas(sheet, updatedHdrMap);
    }
  }
  
  // Force recalculation by refreshing formulas
  SpreadsheetApp.flush();
  
  // Give formulas time to calculate
  Utilities.sleep(2000);
  
  // Now generate the report
  EW_generateSuccessReport();
}

/**
 * Generates comprehensive success analysis report for all strategies
 * Creates or updates the "Success Report" sheet with performance metrics
 * Analyzes hit rates, success scores, and strategy effectiveness
 * @returns {void}
 */
function EW_generateSuccessReport() {
  EW_trace('REPORT', 'Generating success report...', true);
  
  const ss = SpreadsheetApp.getActive();
  let reportSheet = ss.getSheetByName('Success_Report');
  if (!reportSheet) {
    reportSheet = ss.insertSheet('Success_Report');
  }
  
  // Clear existing content
  reportSheet.clear();
  
  // Create report header
  const reportHeaders = [
    'Strategy', 'Total_Positions', 'Hits', 'Hit_Rate_%', 'Avg_Success_Score',
    'Day0_Hit_Rate', 'Day1_Hit_Rate', 'Day2_Hit_Rate', 'Day3_Hit_Rate', 'Day4_Hit_Rate', 'Day5_Hit_Rate', 'Avg_Days_To_Hit',
    'Best_Performers', 'Worst_Performers', 'Recommendations'
  ];
  
  reportSheet.getRange(1, 1, 1, reportHeaders.length).setValues([reportHeaders]);
  
  // Get data from all strategy sheets
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  const reportData = [];
  
  strategies.forEach(strategy => {
    const sheet = ss.getSheetByName(strategy);
    if (!sheet || sheet.getLastRow() < 2) {
      EW_trace('REPORT', `Skipping ${strategy} - no sheet or no data`);
      return;
    }
    
    try {
      const data = sheet.getDataRange().getValues();
      const headers = data[0];
      const rows = data.slice(1);
      
      EW_trace('REPORT', `Processing ${strategy} with ${rows.length} rows`);
      
      const hdrMap = EW_headerMap(headers);
      if (!hdrMap.strikeHitCol || !hdrMap.successScoreCol) {
        EW_trace('REPORT', `Skipping ${strategy} - missing Strike_Hit or Success_Score columns`);
        // Try to add missing columns
        const updatedHdrMap = EW_ensureAllColumnsExist(sheet);
        if (updatedHdrMap) {
          // Re-apply formulas
          EW_setGFArrayFormulas(sheet, updatedHdrMap);
          EW_trace('REPORT', `Added missing columns to ${strategy}, please run report again`);
        }
        return;
      }
      
      // Calculate statistics
      const stats = EW_calculateStrategyStats(rows, hdrMap, strategy);
      reportData.push(stats);
      
    } catch (e) {
      EW_trace('REPORT', `Error processing ${strategy}: ${e.message}`, true);
    }
  });
  
  // Write report data
  if (reportData.length > 0) {
    const reportRows = reportData.map(stat => [
      stat.strategy,
      stat.totalPositions,
      stat.hits,
      stat.hitRate,
      stat.avgSuccessScore,
      stat.day0HitRate,
      stat.day1HitRate,
      stat.day2HitRate,
      stat.day3HitRate,
      stat.day4HitRate,
      stat.day5HitRate,
      stat.avgDaysToHit,
      stat.bestPerformers,
      stat.worstPerformers,
      stat.recommendations
    ]);
    
    reportSheet.getRange(2, 1, reportRows.length, reportHeaders.length).setValues(reportRows);
    
    // Format the report
    reportSheet.getRange(1, 1, 1, reportHeaders.length).setFontWeight('bold');
    reportSheet.autoResizeColumns(1, reportHeaders.length);
    
    EW_trace('REPORT', `Success report generated with ${reportData.length} strategies!`, true);
    EW_safeAlert('Success Report', `Strategy success report has been generated with data from ${reportData.length} strategies.`);
  } else {
    EW_trace('REPORT', 'No data found for success report - sheets may be missing required columns', true);
    EW_safeAlert('No Data Found', 'No strategy data found for report. Please ensure sheets have Strike_Hit and Success_Score columns, then run "Fix: Complete sheet repair" to add missing columns.');
  }
}

/**
 * Calculates performance statistics for a specific strategy
 * Analyzes hit rates, success scores, timing, and generates recommendations
 * @param {Array} rows - Data rows from strategy sheet
 * @param {Object} hdrMap - Header mapping object
 * @param {string} strategyName - Name of the strategy being analyzed
 * @returns {Object} Statistics object with performance metrics
 */
function EW_calculateStrategyStats(rows, hdrMap, strategyName) {
  const stats = {
    strategy: strategyName,
    totalPositions: rows.length,
    hits: 0,
    hitRate: 0,
    avgSuccessScore: 0,
    day0HitRate: 0,
    day1HitRate: 0,
    day2HitRate: 0,
    day3HitRate: 0,
    day4HitRate: 0,
    day5HitRate: 0,
    avgDaysToHit: 0,
    bestPerformers: '',
    worstPerformers: '',
    recommendations: ''
  };
  
  let totalSuccess = 0;
  let day0Hits = 0, day1Hits = 0, day2Hits = 0, day3Hits = 0, day4Hits = 0, day5Hits = 0;
  let daysToHitSum = 0, hitCount = 0;
  const performers = [];
  
  rows.forEach((row, i) => {
    const ticker = row[hdrMap.tickerCol - 1] || '';
    const strikeHitRaw = row[hdrMap.strikeHitCol - 1] || '';
    const strikeHitArray = EW_parseStrikeHitArray(strikeHitRaw);
    const strikeHit = strikeHitArray.length > 0 ? 'HIT' : '';  // Consider hit if array has values
    const successScore = parseFloat(row[hdrMap.successScoreCol - 1]) || 0;
    const day0Check = row[hdrMap.day0CheckCol - 1] || '';
    const day1Check = row[hdrMap.day1CheckCol - 1] || '';
    const day2Check = row[hdrMap.day2CheckCol - 1] || '';
    const day3Check = row[hdrMap.day3CheckCol - 1] || '';
    const day4Check = row[hdrMap.day4CheckCol - 1] || '';
    const day5Check = row[hdrMap.day5CheckCol - 1] || '';
    const hitDate = row[hdrMap.hitDateCol - 1] || '';
    const runDate = row[hdrMap.runDateCol - 1] || '';
    
    // Count hits
    if (strikeHit === 'HIT' || strikeHit === 'FAVORABLE' || strikeHitArray.length > 0) {
      stats.hits++;
      if (hitDate && runDate) {
        const days = (new Date(hitDate) - new Date(runDate)) / (1000 * 60 * 60 * 24);
        daysToHitSum += days;
        hitCount++;
      }
    }
    
    // Daily hit rates
    if (day0Check === 'HIT' || day0Check === 'FAVORABLE') day0Hits++;
    if (day1Check === 'HIT' || day1Check === 'FAVORABLE') day1Hits++;
    if (day2Check === 'HIT' || day2Check === 'FAVORABLE') day2Hits++;
    if (day3Check === 'HIT' || day3Check === 'FAVORABLE') day3Hits++;
    if (day4Check === 'HIT' || day4Check === 'FAVORABLE') day4Hits++;
    if (day5Check === 'HIT' || day5Check === 'FAVORABLE') day5Hits++;
    
    totalSuccess += successScore;
    
    performers.push({
      ticker: ticker,
      score: successScore,
      hit: strikeHit
    });
  });
  
  // Calculate percentages
  stats.hitRate = stats.totalPositions > 0 ? Math.round((stats.hits / stats.totalPositions) * 100) : 0;
  stats.day0HitRate = stats.totalPositions > 0 ? Math.round((day0Hits / stats.totalPositions) * 100) : 0;
  stats.day1HitRate = stats.totalPositions > 0 ? Math.round((day1Hits / stats.totalPositions) * 100) : 0;
  stats.day2HitRate = stats.totalPositions > 0 ? Math.round((day2Hits / stats.totalPositions) * 100) : 0;
  stats.day3HitRate = stats.totalPositions > 0 ? Math.round((day3Hits / stats.totalPositions) * 100) : 0;
  stats.day4HitRate = stats.totalPositions > 0 ? Math.round((day4Hits / stats.totalPositions) * 100) : 0;
  stats.day5HitRate = stats.totalPositions > 0 ? Math.round((day5Hits / stats.totalPositions) * 100) : 0;
  stats.avgSuccessScore = stats.totalPositions > 0 ? Math.round(totalSuccess / stats.totalPositions) : 0;
  stats.avgDaysToHit = hitCount > 0 ? Math.round(daysToHitSum / hitCount * 10) / 10 : 0;
  
  // Best and worst performers
  performers.sort((a, b) => b.score - a.score);
  stats.bestPerformers = performers.slice(0, 3).map(p => `${p.ticker}(${p.score})`).join(', ');
  stats.worstPerformers = performers.slice(-3).map(p => `${p.ticker}(${p.score})`).join(', ');
  
  // Generate recommendations
  if (stats.hitRate >= 70) {
    stats.recommendations = 'HIGH CONFIDENCE - Continue strategy';
  } else if (stats.hitRate >= 50) {
    stats.recommendations = 'MODERATE - Monitor closely';
  } else if (stats.hitRate >= 30) {
    stats.recommendations = 'LOW CONFIDENCE - Review parameters';
  } else {
    stats.recommendations = 'POOR PERFORMANCE - Revise strategy';
  }
  
  return stats;
}

/**
 * Forces recalculation of tracking formulas across all strategy sheets
 * Updates GOOGLEFINANCE data and tracking metrics by triggering formula refresh
 * @returns {void}
 */
function EW_updateTrackingData() {
  EW_trace('UPDATE', 'Updating tracking data for all sheets...', true);
  
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  let updatedSheets = 0;
  
  strategies.forEach(strategy => {
    const sheet = ss.getSheetByName(strategy);
    if (!sheet || sheet.getLastRow() < 2) return;
    
    try {
      // Force recalculation of tracking formulas
      const lastRow = sheet.getLastRow();
      const lastCol = sheet.getLastColumn();
      
      // Touch a cell to trigger recalculation
      const tempCell = sheet.getRange(lastRow + 1, 1);
      tempCell.setValue('REFRESH');
      tempCell.clear();
      
      SpreadsheetApp.flush(); // Force calculation
      updatedSheets++;
      
      EW_trace('UPDATE', `Updated tracking for ${strategy}`, false);
      
    } catch (e) {
      EW_trace('UPDATE', `Error updating ${strategy}: ${e.message}`, true);
    }
  });
  
  EW_trace('UPDATE', `Tracking data updated for ${updatedSheets} sheets`, true);
  EW_safeAlert('Update Complete', `Tracking data has been refreshed for ${updatedSheets} strategy sheets.`);
}

