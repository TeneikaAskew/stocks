/**
 * Add missing tracking columns to strategy sheets
 * This function adds all the required tracking columns for backfill and active tracking
 */

/**
 * Add all tracking columns to a sheet if they don't exist
 * @param {string} sheetName - Name of the sheet to update
 */
function EW_addTrackingColumns(sheetName) {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getSheetByName(sheetName);
  
  if (!sheet) {
    EW_trace('ADD_COLUMNS', `Sheet ${sheetName} not found`);
    return false;
  }
  
  // Get current headers
  const lastCol = sheet.getLastColumn();
  const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Define all tracking columns that should exist
  const trackingColumns = [
    // Core tracking columns
    'Strike_Hit',           // Array of strike hit percentages by day
    'Max_Favorable',        // Array of max favorable moves by day
    'Min_Unfavorable',      // Array of min unfavorable moves by day
    'Hit_Date',             // Date when strike was first hit
    'First_Hit_Date',       // Redundant with Hit_Date but some functions use it
    
    // Day check columns
    'Day0_Check',           // Price on entry day
    'Day1_Check',           // Price on day 1
    'Day2_Check',           // Price on day 2
    'Day3_Check',           // Price on day 3
    'Day4_Check',           // Price on day 4
    'Day5_Check',           // Price on day 5
    
    // Result columns
    'Exp_Result',           // Result at expiration
    'Success_Score',        // Success score calculation
    'Risk_Reward',          // Risk/reward ratio
    
    // Historical tracking
    'Historical_High',      // Highest price since entry
    'Historical_Low',       // Lowest price since entry
    'Ever_Hit_Strike',      // Whether strike was ever hit
    'Total_Hit_Days',       // Number of days strike was hit
    'Last_Update',          // Last update timestamp
    
    // Entry indicators (populated at entry time)
    'Entry_RSI',
    'Entry_SMA20',
    'Entry_SMA50',
    'Entry_EMA9',
    'Entry_EMA21',
    'Entry_VWAP',
    'Entry_RVOL',
    'Entry_ATR',
    'Entry_PriceVsSMA20',
    'Entry_PriceVsVWAP',
    
    // Hit indicators (arrays - populated by backfill)
    'Hit_RSI',              // RSI values array for days 0-5
    'Hit_SMA20',            // SMA20 values array for days 0-5
    'Hit_SMA50',            // SMA50 values array for days 0-5
    'Hit_EMA9',             // EMA9 values array for days 0-5
    'Hit_EMA21',            // EMA21 values array for days 0-5
    'Hit_VWAP',             // VWAP values array for days 0-5
    'Hit_RVOL',             // RVOL values array for days 0-5
    'Hit_ATR',              // ATR values array for days 0-5
    'Hit_PriceVsSMA20',     // Price vs SMA20 array for days 0-5
    'Hit_PriceVsVWAP',      // Price vs VWAP array for days 0-5
    
    // Additional tracking columns
    'Days_To_Exp',          // Days until expiration
    
    // GoogleFinance columns (if not already present)
    'GF_Price',             // Current price from GoogleFinance
    'GF_ChangePct',         // Change percentage
    'GF_High',              // Today's high
    'GF_Low',               // Today's low
    'GF_High52',            // 52-week high
    'GF_Low52',             // 52-week low
    'GF_Volume',            // Volume
    'GF_AvgVol10',          // 10-day average volume
    'GF_MktCap',            // Market cap
    'GF_PE',                // P/E ratio
    'GF_Beta',              // Beta
    'GF_Name',              // Company name
    
    // Additional metrics
    'HV_30D',               // 30-day historical volatility
    'RVOL_10',              // 10-day relative volume
    'Ret_5D',               // 5-day return
    'Ret_20D',              // 20-day return
    'GapPct'                // Gap percentage
  ];
  
  // Find which columns need to be added
  const columnsToAdd = [];
  const normalizedHeaders = headers.map(h => EW_norm(String(h || '').trim()));
  
  for (const colName of trackingColumns) {
    const normalizedColName = EW_norm(colName);
    // Check if column doesn't exist
    if (!normalizedHeaders.includes(normalizedColName)) {
      columnsToAdd.push(colName);
    }
  }
  
  if (columnsToAdd.length === 0) {
    EW_trace('ADD_COLUMNS', `${sheetName}: All tracking columns already exist`);
    return true;
  }
  
  // Add the missing columns
  const startCol = lastCol + 1;
  const numColsToAdd = columnsToAdd.length;
  
  // Insert columns at the end
  sheet.insertColumnsAfter(lastCol, numColsToAdd);
  
  // Set the headers for the new columns
  const headerRange = sheet.getRange(1, startCol, 1, numColsToAdd);
  headerRange.setValues([columnsToAdd]);
  
  // Format the header row
  headerRange.setBackground('#f0f0f0')
             .setFontWeight('bold')
             .setBorder(true, true, true, true, true, true);
  
  EW_trace('ADD_COLUMNS', `${sheetName}: Added ${numColsToAdd} tracking columns: ${columnsToAdd.join(', ')}`, true);
  
  // Apply formulas to GoogleFinance columns if they were added
  const newHeaders = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const newHdrMap = EW_headerMap(newHeaders);
  
  // Apply GoogleFinance formulas to all existing rows
  if (sheet.getLastRow() > 1) {
    EW_applyGoogleFinanceFormulas(sheet, newHdrMap, 2, sheet.getLastRow());
  }
  
  return true;
}

/**
 * Apply GoogleFinance formulas to the specified rows
 * @param {Sheet} sheet - The sheet to update
 * @param {Object} hdrMap - Header map object
 * @param {number} startRow - First row to update
 * @param {number} endRow - Last row to update
 */
function EW_applyGoogleFinanceFormulas(sheet, hdrMap, startRow, endRow) {
  const tickerCol = hdrMap.tickerCol;
  if (!tickerCol) {
    EW_trace('ADD_COLUMNS', 'No ticker column found, cannot apply GoogleFinance formulas');
    return;
  }
  
  const numRows = endRow - startRow + 1;
  
  // Define GoogleFinance formulas
  const gfFormulas = [
    { col: hdrMap.nameCol, formula: row => `=IFERROR(GOOGLEFINANCE($${String.fromCharCode(64 + tickerCol)}${row},"name"),"")` },
    { col: hdrMap.priceCol, formula: row => `=IFERROR(GOOGLEFINANCE($${String.fromCharCode(64 + tickerCol)}${row},"price"),"")` },
    { col: hdrMap.chgPctCol, formula: row => `=IFERROR(GOOGLEFINANCE($${String.fromCharCode(64 + tickerCol)}${row},"changepct"),"")` },
    { col: hdrMap.highCol, formula: row => `=IFERROR(GOOGLEFINANCE($${String.fromCharCode(64 + tickerCol)}${row},"high"),"")` },
    { col: hdrMap.lowCol, formula: row => `=IFERROR(GOOGLEFINANCE($${String.fromCharCode(64 + tickerCol)}${row},"low"),"")` },
    { col: hdrMap.high52Col, formula: row => `=IFERROR(GOOGLEFINANCE($${String.fromCharCode(64 + tickerCol)}${row},"high52"),"")` },
    { col: hdrMap.low52Col, formula: row => `=IFERROR(GOOGLEFINANCE($${String.fromCharCode(64 + tickerCol)}${row},"low52"),"")` },
    { col: hdrMap.volCol, formula: row => `=IFERROR(GOOGLEFINANCE($${String.fromCharCode(64 + tickerCol)}${row},"volume"),"")` },
    { col: hdrMap.avgVol10Col, formula: row => `=IFERROR(GOOGLEFINANCE($${String.fromCharCode(64 + tickerCol)}${row},"volumeavg"),"")` },
    { col: hdrMap.mcapCol, formula: row => `=IFERROR(GOOGLEFINANCE($${String.fromCharCode(64 + tickerCol)}${row},"marketcap"),"")` },
    { col: hdrMap.peCol, formula: row => `=IFERROR(GOOGLEFINANCE($${String.fromCharCode(64 + tickerCol)}${row},"pe"),"")` },
    { col: hdrMap.betaCol, formula: row => `=IFERROR(GOOGLEFINANCE($${String.fromCharCode(64 + tickerCol)}${row},"beta"),"")` }
  ];
  
  // Apply formulas in batch
  for (const gf of gfFormulas) {
    if (gf.col) {
      const formulas = [];
      for (let row = startRow; row <= endRow; row++) {
        formulas.push([gf.formula(row)]);
      }
      sheet.getRange(startRow, gf.col, numRows, 1).setFormulas(formulas);
    }
  }
  
  EW_trace('ADD_COLUMNS', `Applied GoogleFinance formulas to rows ${startRow}-${endRow}`);
}

/**
 * Add tracking columns to all strategy sheets
 */
function EW_addTrackingColumnsToAll() {
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  let successCount = 0;
  let failedSheets = [];
  
  for (const strategy of strategies) {
    try {
      if (EW_addTrackingColumns(strategy)) {
        successCount++;
      } else {
        failedSheets.push(strategy);
      }
    } catch (e) {
      EW_trace('ADD_COLUMNS', `Error adding columns to ${strategy}: ${e.message}`);
      failedSheets.push(strategy);
    }
  }
  
  const message = `Added tracking columns to ${successCount}/${strategies.length} sheets` +
    (failedSheets.length > 0 ? `\n\nFailed sheets: ${failedSheets.join(', ')}` : '');
  
  EW_trace('ADD_COLUMNS', message, true);
  EW_safeAlert('Tracking Columns Added', message);
}

/**
 * Check which columns are missing from a sheet
 * @param {string} sheetName - Name of the sheet to check
 * @returns {Array} Array of missing column names
 */
function EW_checkMissingColumns(sheetName) {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getSheetByName(sheetName);
  
  if (!sheet) {
    return null;
  }
  
  // Get current headers
  const lastCol = sheet.getLastColumn();
  const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  const normalizedHeaders = headers.map(h => EW_norm(String(h || '').trim()));
  
  // All expected tracking columns
  const expectedColumns = [
    'Strike_Hit', 'Max_Favorable', 'Min_Unfavorable', 'Hit_Date', 'First_Hit_Date',
    'Day0_Check', 'Day1_Check', 'Day2_Check', 'Day3_Check', 'Day4_Check', 'Day5_Check',
    'Exp_Result', 'Success_Score', 'Risk_Reward',
    'Historical_High', 'Historical_Low', 'Ever_Hit_Strike', 'Total_Hit_Days', 'Last_Update',
    'Entry_RSI', 'Entry_SMA20', 'Entry_SMA50', 'Entry_EMA9', 'Entry_EMA21', 
    'Entry_VWAP', 'Entry_RVOL', 'Entry_ATR', 'Entry_PriceVsSMA20', 'Entry_PriceVsVWAP',
    'Hit_RSI', 'Hit_SMA20', 'Hit_SMA50', 'Hit_EMA9', 'Hit_EMA21',
    'Hit_VWAP', 'Hit_RVOL', 'Hit_ATR', 'Hit_PriceVsSMA20', 'Hit_PriceVsVWAP',
    'Days_To_Exp',
    'GF_Price', 'GF_ChangePct', 'GF_High', 'GF_Low', 'GF_High52', 'GF_Low52',
    'GF_Volume', 'GF_AvgVol10', 'GF_MktCap', 'GF_PE', 'GF_Beta', 'GF_Name',
    'HV_30D', 'RVOL_10', 'Ret_5D', 'Ret_20D', 'GapPct'
  ];
  
  const missingColumns = [];
  for (const colName of expectedColumns) {
    const normalizedColName = EW_norm(colName);
    if (!normalizedHeaders.includes(normalizedColName)) {
      missingColumns.push(colName);
    }
  }
  
  return missingColumns;
}

/**
 * Menu function to add columns to current sheet
 */
function EW_addColumnsToCurrentSheet() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const sheetName = sheet.getName();
  
  if (EW_addTrackingColumns(sheetName)) {
    EW_safeAlert('Success', `Added tracking columns to ${sheetName}`);
  } else {
    EW_safeAlert('Error', `Failed to add columns to ${sheetName}`);
  }
}