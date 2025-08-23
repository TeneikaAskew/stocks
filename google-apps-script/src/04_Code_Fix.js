/**
 * Replace the buggy EW_completeSheetRepair function with this fixed version
 * Copy this entire function over the existing one in 04_Code.js
 */

/**
 * Complete sheet repair - safer version that preserves data
 * 1. Removes all duplicate/error columns
 * 2. Removes all corrupted columns (#ERROR!, #REF!)
 * 3. Adds Strategy column if missing
 * 4. Re-applies all formulas fresh
 * @returns {void}
 */
function EW_completeSheetRepair() {
  EW_trace('REPAIR', 'Starting complete sheet repair', true);
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
      let lastCol = sheet.getLastColumn();
      
      if (lastRow === 0 || lastCol === 0) {
        EW_trace('REPAIR', `${tabName} has no data, skipping`);
        continue;
      }
      
      // Get all data INCLUDING formulas
      let allData = sheet.getRange(1, 1, lastRow, lastCol).getValues();
      let headers = allData[0];
      
      // List of all formula columns to remove
      const formulaColumns = [...EW_GF_LABELS, ...EW_TRACKING_LABELS];
      const formulaColumnsLower = formulaColumns.map(c => c.toLowerCase());
      
      // Step 1: Identify columns to keep (not GF/tracking/error columns)
      const columnsToKeep = [];
      headers.forEach((header, index) => {
        const headerStr = header ? header.toString() : '';
        const headerLower = headerStr.toLowerCase();
        
        // Skip if it's a formula column, error, or duplicate
        if (headerStr.startsWith('#') || 
            formulaColumnsLower.includes(headerLower)) {
          EW_trace('REPAIR', `${tabName}: Removing column "${header}" at position ${index + 1}`);
          return;
        }
        
        // Keep this column
        columnsToKeep.push(index);
      });
      
      // Step 2: Rebuild data with only kept columns
      if (columnsToKeep.length === 0) {
        EW_trace('REPAIR', `${tabName}: No data columns to keep!`);
        continue;
      }
      
      if (columnsToKeep.length < lastCol) {
        EW_trace('REPAIR', `${tabName}: Keeping ${columnsToKeep.length} of ${lastCol} columns`);
        
        // Filter data to keep only selected columns
        const filteredData = allData.map(row => columnsToKeep.map(i => row[i]));
        
        // Clear sheet and write filtered data
        sheet.clear();
        sheet.getRange(1, 1, lastRow, columnsToKeep.length).setValues(filteredData);
        
        // Update references
        lastCol = columnsToKeep.length;
        headers = filteredData[0];
      }
      
      // Step 3: Ensure Strategy column exists
      let currentData = sheet.getDataRange().getValues();
      let currentHeaders = currentData[0];
      let hdrMap = EW_headerMap(currentHeaders);
      
      if (!hdrMap.strategyCol) {
        EW_trace('REPAIR', `${tabName}: Adding Strategy column`);
        
        // Insert Strategy as second column
        const updatedData = currentData.map((row, rowIndex) => {
          const newRow = [...row];
          if (rowIndex === 0) {
            newRow.splice(1, 0, 'Strategy');
          } else {
            newRow.splice(1, 0, tabName);
          }
          return newRow;
        });
        
        // Update sheet with Strategy column
        sheet.clear();
        lastCol = lastCol + 1;
        sheet.getRange(1, 1, updatedData.length, lastCol).setValues(updatedData);
      }
      
      // Step 4: Add GF headers and apply formulas
      // Get current headers after modifications
      const finalCurrentHeaders = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      const withGFHeaders = EW_addGFHeaders(finalCurrentHeaders);
      
      // Update header row with GF columns added
      sheet.getRange(1, 1, 1, withGFHeaders.length).setValues([withGFHeaders]);
      
      // Now apply the formulas
      const finalHdrMap = EW_headerMap(withGFHeaders);
      EW_setGFArrayFormulas(sheet, finalHdrMap);
      
      sheetsRepaired++;
      EW_trace('REPAIR', `Repaired ${tabName} successfully`);
      
    } catch (e) {
      EW_trace('REPAIR', `Error repairing ${tabName}: ${e.message}`, true);
    }
  }
  
  const msg = sheetsRepaired > 0 ? 
    `Successfully repaired ${sheetsRepaired} sheets - removed all GF/error columns and recreated formulas` :
    'No sheets needed repair';
  
  EW_safeAlert('Complete Sheet Repair', msg);
  EW_trace('REPAIR', msg, true);
}

/**
 * Fixed version of EW_appendToTab that properly adds Google Finance columns
 * Replace the existing function in 04_Code.js with this version
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
    const headerWithGF = EW_addGFHeaders(baseHeader);
    const width = headerWithGF.length;
    
    // Write headers first
    sheet.getRange(1, 1, 1, width).setValues([headerWithGF]);
    EW_trace('SHEET', `Wrote header (${width} cols)`);
    
    // Prepare data rows with Run Date and Strategy
    const dataRows = incomingData.map(r => {
      const row = [runDate, tabName, ...r];
      // Pad row to match header width
      while (row.length < width) {
        row.push('');
      }
      return row;
    });
    
    // Write data rows
    if (dataRows.length) {
      sheet.getRange(2, 1, dataRows.length, width).setValues(dataRows);
      EW_trace('SHEET', `Wrote ${dataRows.length} data rows`);
    }
    
    // IMPORTANT: Set formulas AFTER writing headers
    // This ensures the header map can find all columns
    const hdrMap = EW_headerMap(headerWithGF);
    EW_trace('SHEET', `Header map created, applying formulas...`);
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
  
  // Rest of the function continues as normal...
  // (Include the rest of the original function here)
}

/**
 * Test function to verify Google Finance columns are being added correctly
 * Creates a test sheet and simulates the full flow
 */
function EW_testGoogleFinanceColumns() {
  EW_trace('TEST', 'Testing Google Finance column creation', true);
  const ss = SpreadsheetApp.getActive();
  
  // Create test sheet
  const testSheetName = '_TEST_GF_Columns';
  let testSheet = ss.getSheetByName(testSheetName);
  if (testSheet) {
    ss.deleteSheet(testSheet);
  }
  testSheet = ss.insertSheet(testSheetName);
  
  try {
    // Simulate incoming data
    const testData = [
      ['ticker', 'strike', 'exp', 'Call_Bid', 'Call_Ask'],
      ['AAPL', '150', '2025-01-17', '5.50', '5.60'],
      ['GOOGL', '140', '2025-01-17', '3.20', '3.30']
    ];
    
    // Step 1: Test EW_ensureRequiredHeaders
    const baseHeader = EW_ensureRequiredHeaders(testData[0], 'Long Calls');
    EW_trace('TEST', `Base header: ${baseHeader.join(', ')}`);
    
    // Step 2: Test EW_addGFHeaders
    const withGFHeaders = EW_addGFHeaders(baseHeader);
    EW_trace('TEST', `With GF headers: ${withGFHeaders.join(', ')}`);
    
    // Step 3: Write headers and data
    testSheet.getRange(1, 1, 1, withGFHeaders.length).setValues([withGFHeaders]);
    
    // Prepare data rows with Run Date and Strategy
    const runDate = EW_getRunStamp();
    const dataRows = testData.slice(1).map(row => {
      return [runDate, 'Long Calls', ...row];
    });
    
    if (dataRows.length > 0) {
      testSheet.getRange(2, 1, dataRows.length, withGFHeaders.length).setValues(dataRows);
    }
    
    // Step 4: Apply formulas
    const hdrMap = EW_headerMap(withGFHeaders);
    EW_trace('TEST', `Header map: ${JSON.stringify(hdrMap)}`);
    EW_setGFArrayFormulas(testSheet, hdrMap);
    
    // Step 5: Verify formulas were applied
    const formulasApplied = [];
    for (let col = 1; col <= withGFHeaders.length; col++) {
      const cellValue = testSheet.getRange(1, col).getValue();
      const cellFormula = testSheet.getRange(1, col).getFormula();
      if (cellFormula) {
        formulasApplied.push(`${withGFHeaders[col-1]}: Has formula`);
      }
    }
    
    EW_trace('TEST', `Formulas applied: ${formulasApplied.join(', ')}`);
    
    const msg = `Test complete! Check sheet "${testSheetName}" to verify formulas are working.\\n\\nFormulas found: ${formulasApplied.length}`;
    EW_safeAlert('Test Complete', msg);
    
  } catch (e) {
    EW_trace('TEST', `Error in test: ${e.message}`, true);
    EW_safeAlert('Test Failed', `Error: ${e.message}`);
  }
}

/**
 * Simple function to just add Google Finance columns to existing sheets
 * This doesn't remove any data, just adds the formula columns
 */
function EW_addGoogleFinanceColumnsOnly() {
  EW_trace('GF_ADD', 'Adding Google Finance columns to all sheets', true);
  const ss = SpreadsheetApp.getActive();
  const endpoints = EW.STRATEGY_ENDPOINTS;
  let sheetsUpdated = 0;
  
  for (const tabName of Object.keys(endpoints)) {
    const sheet = ss.getSheetByName(tabName);
    if (!sheet || sheet.getLastRow() === 0) {
      EW_trace('GF_ADD', `Skipping ${tabName} - sheet empty or doesn't exist`);
      continue;
    }
    
    try {
      // Get current headers
      const currentHeaders = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      let hdrMap = EW_headerMap(currentHeaders);
      
      // Check if we already have GF columns
      if (hdrMap.priceCol || hdrMap.nameCol) {
        EW_trace('GF_ADD', `${tabName} already has GF columns, skipping`);
        continue;
      }
      
      // Add GF headers
      const withGFHeaders = EW_addGFHeaders(currentHeaders);
      
      // Update header row
      sheet.getRange(1, 1, 1, withGFHeaders.length).setValues([withGFHeaders]);
      
      // Get new header map and apply formulas
      const newHdrMap = EW_headerMap(withGFHeaders);
      EW_setGFArrayFormulas(sheet, newHdrMap);
      
      sheetsUpdated++;
      EW_trace('GF_ADD', `Added GF columns to ${tabName}`);
      
    } catch (e) {
      EW_trace('GF_ADD', `Error updating ${tabName}: ${e.message}`, true);
    }
  }
  
  const msg = sheetsUpdated > 0 ? 
    `Successfully added Google Finance columns to ${sheetsUpdated} sheets` :
    'No sheets needed Google Finance columns';
  
  EW_safeAlert('Add GF Columns', msg);
  EW_trace('GF_ADD', msg, true);
}

/**
 * Debug function to check why EW_runAll isn't adding GF columns
 * Runs a single strategy with detailed logging
 */
function EW_debugRunAllIssue() {
  EW_trace('DEBUG', 'Debugging EW_runAll GF column issue', true);
  const ss = SpreadsheetApp.getActive();
  
  // Test with Long Calls strategy
  const testStrategy = 'Long Calls';
  const testSheet = ss.getSheetByName(testStrategy);
  
  if (testSheet) {
    // Clear the sheet to test fresh run
    const response = EW_safeConfirm('Debug Test', `Clear "${testStrategy}" sheet for testing?`);
    if (response === 'YES') {
      testSheet.clear();
      EW_trace('DEBUG', `Cleared ${testStrategy} sheet`);
    }
  }
  
  // Run single strategy with debug logging
  EW_trace('DEBUG', `Running EW_runSingle("${testStrategy}")...`);
  
  try {
    EW_runSingle(testStrategy);
    
    // Check results
    const sheet = ss.getSheetByName(testStrategy);
    if (!sheet) {
      EW_trace('DEBUG', 'Sheet was not created!', true);
      return;
    }
    
    const lastRow = sheet.getLastRow();
    const lastCol = sheet.getLastColumn();
    EW_trace('DEBUG', `Sheet has ${lastRow} rows and ${lastCol} columns`);
    
    if (lastRow > 0) {
      const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
      EW_trace('DEBUG', `Headers: ${headers.join(', ')}`);
      
      // Check for formulas
      const formulasFound = [];
      for (let col = 1; col <= lastCol; col++) {
        const formula = sheet.getRange(1, col).getFormula();
        if (formula) {
          formulasFound.push(`Col ${col} (${headers[col-1]})`);
        }
      }
      
      EW_trace('DEBUG', `Formulas found in: ${formulasFound.join(', ')}`);
    }
    
  } catch (e) {
    EW_trace('DEBUG', `Error: ${e.message}`, true);
  }
}