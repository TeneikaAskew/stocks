/**
 * Simple repair function that deletes all Google Finance columns and re-adds them
 * This completely removes and recreates all formula columns
 */
function EW_simpleRepairGoogleFinanceColumns() {
  EW_trace('REPAIR', 'Starting simple GF column repair - delete and recreate', true);
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
      
      // Get all headers
      const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
      
      // List of ALL formula columns from EW_setGFArrayFormulas
      const formulaColumns = [
        'GF_Name', 'GF_Price', 'GF_ChangePct', 'GF_High', 'GF_Low', 
        'GF_High52', 'GF_Low52', 'GF_Volume', 'GF_AvgVol10', 'GF_MktCap', 
        'GF_PE', 'GF_Beta', 'HV_30D', 'RVOL_10', 'Ret_5D', 'Ret_20D', 
        'GapPct', 'Historical_High', 'Historical_Low', 'Ever_Hit_Strike',
        'First_Hit_Date', 'Last_Update', 'Total_Hit_Days', 'Peak_Profit_Date',
        'Days_To_Exp', 'Strike_Hit', 'Hit_Date', 'Max_Favorable', 
        'Min_Unfavorable', 'Day1_Check', 'Day2_Check', 'Day3_Check', 
        'Day5_Check', 'Exp_Result', 'Success_Score', 'Profit_Potential', 
        'Risk_Reward', 'Stock_Price'
      ];
      
      // Also remove any #ERROR! or #REF! columns
      const columnsToDelete = [];
      
      headers.forEach((header, index) => {
        const headerStr = header ? header.toString() : '';
        const headerLower = headerStr.toLowerCase();
        
        // Check if it's a formula column or an error
        if (headerStr.startsWith('#') || 
            formulaColumns.some(fc => fc.toLowerCase() === headerLower)) {
          columnsToDelete.push(index + 1); // Store 1-based column index
          EW_trace('REPAIR', `${tabName}: Will delete column "${header}" at position ${index + 1}`);
        }
      });
      
      // Delete columns from right to left to maintain indices
      columnsToDelete.sort((a, b) => b - a);
      
      for (const colIndex of columnsToDelete) {
        sheet.deleteColumn(colIndex);
        EW_trace('REPAIR', `${tabName}: Deleted column at position ${colIndex}`);
      }
      
      // Now get the cleaned headers and add GF columns back
      const cleanedHeaders = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      const withGFHeaders = EW_addGFHeaders(cleanedHeaders);
      
      // Update header row with GF columns
      sheet.getRange(1, 1, 1, withGFHeaders.length).setValues([withGFHeaders]);
      EW_trace('REPAIR', `${tabName}: Added GF headers, total columns: ${withGFHeaders.length}`);
      
      // Apply formulas
      const hdrMap = EW_headerMap(withGFHeaders);
      EW_setGFArrayFormulas(sheet, hdrMap);
      
      sheetsRepaired++;
      EW_trace('REPAIR', `${tabName}: Successfully repaired`);
      
    } catch (e) {
      EW_trace('REPAIR', `Error repairing ${tabName}: ${e.message}`, true);
    }
  }
  
  const msg = sheetsRepaired > 0 ? 
    `Successfully repaired ${sheetsRepaired} sheets - deleted and recreated all GF columns` :
    'No sheets needed repair';
  
  EW_safeAlert('Simple GF Repair Complete', msg);
  EW_trace('REPAIR', msg, true);
}

/**
 * Alternative version using clear and rewrite instead of deleteColumn
 * This might be more stable for some sheets
 */
function EW_simpleRepairGoogleFinanceColumns_v2() {
  EW_trace('REPAIR', 'Starting simple GF column repair v2 - filter and recreate', true);
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
      
      // Get all data
      const allData = sheet.getRange(1, 1, lastRow, lastCol).getValues();
      const headers = allData[0];
      
      // List of ALL formula columns
      const formulaColumns = [
        'GF_Name', 'GF_Price', 'GF_ChangePct', 'GF_High', 'GF_Low', 
        'GF_High52', 'GF_Low52', 'GF_Volume', 'GF_AvgVol10', 'GF_MktCap', 
        'GF_PE', 'GF_Beta', 'HV_30D', 'RVOL_10', 'Ret_5D', 'Ret_20D', 
        'GapPct', 'Historical_High', 'Historical_Low', 'Ever_Hit_Strike',
        'First_Hit_Date', 'Last_Update', 'Total_Hit_Days', 'Peak_Profit_Date',
        'Days_To_Exp', 'Strike_Hit', 'Hit_Date', 'Max_Favorable', 
        'Min_Unfavorable', 'Day1_Check', 'Day2_Check', 'Day3_Check', 
        'Day5_Check', 'Exp_Result', 'Success_Score', 'Profit_Potential', 
        'Risk_Reward', 'Stock_Price'
      ];
      const formulaColumnsLower = formulaColumns.map(c => c.toLowerCase());
      
      // Identify columns to keep (not formula columns or errors)
      const columnsToKeep = [];
      headers.forEach((header, index) => {
        const headerStr = header ? header.toString() : '';
        const headerLower = headerStr.toLowerCase();
        
        if (!headerStr.startsWith('#') && !formulaColumnsLower.includes(headerLower)) {
          columnsToKeep.push(index);
        }
      });
      
      // Filter data to keep only non-formula columns
      const filteredData = allData.map(row => columnsToKeep.map(i => row[i]));
      
      // Clear sheet and write filtered data
      sheet.clear();
      sheet.getRange(1, 1, lastRow, columnsToKeep.length).setValues(filteredData);
      
      // Now add GF headers back
      const cleanedHeaders = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      const withGFHeaders = EW_addGFHeaders(cleanedHeaders);
      
      // Update header row
      sheet.getRange(1, 1, 1, withGFHeaders.length).setValues([withGFHeaders]);
      
      // Apply formulas
      const hdrMap = EW_headerMap(withGFHeaders);
      EW_setGFArrayFormulas(sheet, hdrMap);
      
      sheetsRepaired++;
      EW_trace('REPAIR', `${tabName}: Successfully repaired using filter method`);
      
    } catch (e) {
      EW_trace('REPAIR', `Error repairing ${tabName}: ${e.message}`, true);
    }
  }
  
  const msg = sheetsRepaired > 0 ? 
    `Successfully repaired ${sheetsRepaired} sheets - filtered and recreated all GF columns` :
    'No sheets needed repair';
  
  EW_safeAlert('Simple GF Repair v2 Complete', msg);
  EW_trace('REPAIR', msg, true);
}