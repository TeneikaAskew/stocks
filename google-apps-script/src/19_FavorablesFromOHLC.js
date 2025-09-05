/**
 * Calculate Max_Favorable and Min_Unfavorable from OHLC_Volume Data
 * This file provides functions to recalculate favorable/unfavorable values
 * using the comprehensive OHLC data stored in OHLC_Volume column
 */

/**
 * Recalculate Max_Favorable and Min_Unfavorable using OHLC_Volume data
 * This is more accurate than using Day_Check values since we have actual high/low
 */
function EW_recalculateFavorablesFromOHLC() {
  const startTime = new Date();
  EW_trace('OHLC_FAVORABLES', 'Starting favorable recalculation from OHLC data', true);
  console.log(`OHLC_FAVORABLES: Starting recalculation at ${startTime.toISOString()}`);
  
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  
  let processedCount = 0;
  let updatedCount = 0;
  let errors = [];
  
  for (const strategy of strategies) {
    try {
      const sheet = ss.getSheetByName(strategy);
      if (!sheet || sheet.getLastRow() < 2) {
        continue;
      }
      
      const result = EW_recalculateFavorablesForSheet(sheet, strategy);
      processedCount += result.processed;
      updatedCount += result.updated;
      
      if (result.errors.length > 0) {
        errors.push(...result.errors.map(e => `${strategy}: ${e}`));
      }
      
      EW_trace('OHLC_FAVORABLES', `${strategy}: Processed ${result.processed} rows, updated ${result.updated}`);
      
    } catch (e) {
      errors.push(`${strategy}: ${e.message}`);
      EW_trace('OHLC_FAVORABLES', `Error processing ${strategy}: ${e.message}`, true);
    }
  }
  
  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);
  
  const msg = `OHLC favorable recalculation complete.\n` +
    `Processed: ${processedCount} rows\n` +
    `Updated: ${updatedCount} rows\n` +
    `Duration: ${duration} seconds` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');
  
  EW_trace('OHLC_FAVORABLES', msg, true);
  console.log(`OHLC_FAVORABLES: Completed in ${duration} seconds - Updated ${updatedCount}/${processedCount} rows`);
  
  EW_safeAlert('Recalculation Complete', msg);
  
  return { processed: processedCount, updated: updatedCount, duration: duration, errors: errors };
}

/**
 * Recalculate favorables for a specific sheet using OHLC data
 */
function EW_recalculateFavorablesForSheet(sheet, strategyName) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return { processed: 0, updated: 0, errors: [] };
  }
  
  // Get header mapping
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  let hdrMap = EW_headerMap(headers);
  
  // Add OHLC_Volume column to header map
  for (let i = 0; i < headers.length; i++) {
    if (headers[i] === 'OHLC_Volume' || headers[i] === 'Peak_Profit_Date') {
      hdrMap.ohlcVolumeCol = i + 1;
      break;
    }
  }
  
  // Check required columns
  if (!hdrMap.ohlcVolumeCol) {
    return { processed: 0, updated: 0, errors: ['OHLC_Volume column not found'] };
  }
  
  if (!hdrMap.maxFavorableCol || !hdrMap.minUnfavorableCol) {
    return { processed: 0, updated: 0, errors: ['Max_Favorable or Min_Unfavorable columns not found'] };
  }
  
  const strikeCol = hdrMap.strikeCol || hdrMap.longStrikeCol;
  if (!strikeCol) {
    return { processed: 0, updated: 0, errors: ['Strike column not found'] };
  }
  
  const shortStrikeCol = hdrMap.shortStrikeCol; // For spreads
  
  // Get all data at once
  const dataRange = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
  const data = dataRange.getValues();
  
  let processedCount = 0;
  let updatedCount = 0;
  let errors = [];
  
  // Process each row
  for (let i = 0; i < data.length; i++) {
    const rowNum = i + 2;
    const rowData = data[i];
    
    processedCount++;
    
    try {
      // Get OHLC data
      const ohlcData = rowData[hdrMap.ohlcVolumeCol - 1];
      if (!ohlcData || ohlcData === '' || ohlcData === '[]') {
        continue; // Skip rows without OHLC data
      }
      
      // Parse OHLC array
      let ohlcArray;
      try {
        ohlcArray = typeof ohlcData === 'string' ? JSON.parse(ohlcData) : ohlcData;
      } catch (e) {
        errors.push(`Row ${rowNum}: Invalid OHLC format`);
        continue;
      }
      
      // Get strike price(s)
      const strike = parseFloat(rowData[strikeCol - 1]);
      const shortStrike = shortStrikeCol ? parseFloat(rowData[shortStrikeCol - 1]) : null;
      
      if (!strike || isNaN(strike)) {
        errors.push(`Row ${rowNum}: Invalid strike price`);
        continue;
      }
      
      // Build new favorable/unfavorable arrays using OHLC data
      const maxFavArray = [];
      const minUnfavArray = [];
      
      for (let day = 0; day < ohlcArray.length && day <= 5; day++) {
        const dayOHLC = ohlcArray[day];
        
        if (!dayOHLC || dayOHLC === null) {
          maxFavArray.push(null);
          minUnfavArray.push(null);
          continue;
        }
        
        const dayHigh = parseFloat(dayOHLC.h);
        const dayLow = parseFloat(dayOHLC.l);
        
        if (isNaN(dayHigh) || isNaN(dayLow)) {
          maxFavArray.push(null);
          minUnfavArray.push(null);
          continue;
        }
        
        // Use the centralized calculation functions for consistency
        const maxFav = EW_calculateMaxFavorableForDay(strategyName, strike, dayHigh, dayLow);
        const minUnfav = EW_calculateMinUnfavorableForDay(strategyName, strike, dayHigh, dayLow);
        
        maxFavArray.push(maxFav);
        minUnfavArray.push(minUnfav);
      }
      
      // Update the arrays if we have valid data
      if (maxFavArray.some(v => v !== null)) {
        sheet.getRange(rowNum, hdrMap.maxFavorableCol).setValue(JSON.stringify(maxFavArray));
        sheet.getRange(rowNum, hdrMap.minUnfavorableCol).setValue(JSON.stringify(minUnfavArray));
        updatedCount++;
        
        EW_trace('OHLC_FAVORABLES', `Row ${rowNum}: Updated favorables from OHLC data`);
      }
      
    } catch (e) {
      errors.push(`Row ${rowNum}: ${e.message}`);
      EW_trace('OHLC_FAVORABLES', `Error processing row ${rowNum}: ${e.message}`);
    }
  }
  
  return {
    processed: processedCount,
    updated: updatedCount,
    errors: errors
  };
}

/**
 * Validate Max_Favorable and Min_Unfavorable against OHLC data
 * This function compares existing favorable values with what they should be based on OHLC
 */
function EW_validateFavorablesAgainstOHLC() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const lastRow = sheet.getLastRow();
  
  if (lastRow < 2) {
    EW_safeAlert('No Data', 'Sheet has no data rows to validate');
    return;
  }
  
  // Get header mapping
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  let hdrMap = EW_headerMap(headers);
  
  // Add OHLC_Volume column
  for (let i = 0; i < headers.length; i++) {
    if (headers[i] === 'OHLC_Volume' || headers[i] === 'Peak_Profit_Date') {
      hdrMap.ohlcVolumeCol = i + 1;
      break;
    }
  }
  
  if (!hdrMap.ohlcVolumeCol || !hdrMap.maxFavorableCol || !hdrMap.minUnfavorableCol) {
    EW_safeAlert('Missing Columns', 'Required columns not found (OHLC_Volume, Max_Favorable, Min_Unfavorable)');
    return;
  }
  
  const strikeCol = hdrMap.strikeCol || hdrMap.longStrikeCol;
  if (!strikeCol) {
    EW_safeAlert('Missing Strike', 'Strike column not found');
    return;
  }
  
  const strategyName = sheet.getName();
  let discrepancies = [];
  let checkedCount = 0;
  
  // Check each row
  const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  
  for (let i = 0; i < data.length && i < 20; i++) { // Limit to first 20 rows for validation
    const rowNum = i + 2;
    const rowData = data[i];
    
    const ohlcData = rowData[hdrMap.ohlcVolumeCol - 1];
    const currentMaxFav = rowData[hdrMap.maxFavorableCol - 1];
    const currentMinUnfav = rowData[hdrMap.minUnfavorableCol - 1];
    const strike = parseFloat(rowData[strikeCol - 1]);
    
    if (!ohlcData || !currentMaxFav || !strike) continue;
    
    checkedCount++;
    
    try {
      const ohlcArray = typeof ohlcData === 'string' ? JSON.parse(ohlcData) : ohlcData;
      const maxFavArray = typeof currentMaxFav === 'string' ? JSON.parse(currentMaxFav) : currentMaxFav;
      const minUnfavArray = typeof currentMinUnfav === 'string' ? JSON.parse(currentMinUnfav) : currentMinUnfav;
      
      // Check each day
      for (let day = 0; day < Math.min(ohlcArray.length, maxFavArray.length); day++) {
        const dayOHLC = ohlcArray[day];
        if (!dayOHLC) continue;
        
        const dayHigh = parseFloat(dayOHLC.h);
        const dayLow = parseFloat(dayOHLC.l);
        
        if (isNaN(dayHigh) || isNaN(dayLow)) continue;
        
        // Calculate what the values should be
        const expectedMaxFav = EW_calculateMaxFavorableForDay(strategyName, strike, dayHigh, dayLow);
        const expectedMinUnfav = EW_calculateMinUnfavorableForDay(strategyName, strike, dayHigh, dayLow);
        
        // Compare with current values
        const currentMax = maxFavArray[day];
        const currentMin = minUnfavArray[day];
        
        if (currentMax !== null && expectedMaxFav !== null) {
          const diff = Math.abs(parseFloat(currentMax) - parseFloat(expectedMaxFav));
          if (diff > 0.000001) { // Allow for small rounding differences
            discrepancies.push({
              row: rowNum,
              day: day,
              type: 'Max_Favorable',
              current: currentMax,
              expected: expectedMaxFav,
              ohlc: `H:${dayHigh} L:${dayLow}`
            });
          }
        }
        
        if (currentMin !== null && expectedMinUnfav !== null) {
          const diff = Math.abs(parseFloat(currentMin) - parseFloat(expectedMinUnfav));
          if (diff > 0.000001) {
            discrepancies.push({
              row: rowNum,
              day: day,
              type: 'Min_Unfavorable',
              current: currentMin,
              expected: expectedMinUnfav,
              ohlc: `H:${dayHigh} L:${dayLow}`
            });
          }
        }
      }
    } catch (e) {
      console.log(`Validation error for row ${rowNum}: ${e.message}`);
    }
  }
  
  // Report results
  if (discrepancies.length === 0) {
    EW_safeAlert('Validation Complete', 
      `Checked ${checkedCount} rows.\nAll Max_Favorable and Min_Unfavorable values match OHLC data.`);
  } else {
    let report = `Found ${discrepancies.length} discrepancies in ${checkedCount} rows:\n\n`;
    discrepancies.slice(0, 10).forEach(d => {
      report += `Row ${d.row}, Day ${d.day} (${d.type}):\n`;
      report += `  Current: ${d.current}\n`;
      report += `  Expected: ${d.expected}\n`;
      report += `  OHLC: ${d.ohlc}\n\n`;
    });
    
    if (discrepancies.length > 10) {
      report += `... and ${discrepancies.length - 10} more discrepancies.`;
    }
    
    EW_safeAlert('Validation Results', report);
  }
}