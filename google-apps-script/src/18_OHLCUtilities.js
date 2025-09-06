/**
 * OHLC_Volume Column Utilities
 * Essential functions for working with the OHLC_Volume column
 * The actual population is handled by backfill and active position tracking
 */

/**
 * Build or update OHLC array with new data for a specific day
 * Preserves existing data and adds source tracking
 * @param {Array} existingArray - Existing OHLC array (or empty array)
 * @param {number} dayIndex - Day index (0-5)
 * @param {Object} ohlcData - Object with open, high, low, close, volume
 * @param {string} source - Source of the data ('BACKFILL', 'ACTIVE', etc)
 * @returns {Array} Updated array
 */
function EW_buildOHLCArray(existingArray = [], dayIndex, ohlcData, source = 'UNKNOWN') {
  // Ensure array is at least 6 elements (for days 0-5)
  const array = Array.isArray(existingArray) ? [...existingArray] : [];
  while (array.length < 6) {
    array.push(null);
  }
  
  // Create OHLC object for this day
  if (ohlcData.open !== null && ohlcData.open !== undefined) {
    const dayOHLC = {
      o: parseFloat(ohlcData.open).toFixed(2),
      h: parseFloat(ohlcData.high).toFixed(2),
      l: parseFloat(ohlcData.low).toFixed(2),
      c: parseFloat(ohlcData.close).toFixed(2),
      v: ohlcData.volume !== null && ohlcData.volume !== undefined ? ohlcData.volume : null,
      src: source  // Track the source of this data
    };
    array[dayIndex] = dayOHLC;
  } else if (ohlcData.close !== null && ohlcData.close !== undefined) {
    // If we only have close price (from Day_Check), still store it with source
    const dayOHLC = {
      o: null,
      h: null,
      l: null,
      c: parseFloat(ohlcData.close).toFixed(2),
      v: null,  // Use null instead of 0 when we don't have volume data
      src: source  // Track the source
    };
    array[dayIndex] = dayOHLC;
  } else {
    array[dayIndex] = null;
  }
  
  return array;
}

/**
 * Parse existing OHLC array from cell value
 * Handles both JSON string and array formats
 * @param {string|Array} cellValue - Cell value that may be JSON string or array
 * @returns {Array} Parsed array
 */
function EW_parseOHLCArray(cellValue) {
  if (!cellValue) return [];
  
  // If already an array, return it
  if (Array.isArray(cellValue)) return cellValue;
  
  // If JSON string, parse it
  if (typeof cellValue === 'string' && cellValue.startsWith('[')) {
    try {
      return JSON.parse(cellValue);
    } catch (e) {
      console.log('Failed to parse OHLC array from cell:', e);
      return [];
    }
  }
  
  return [];
}

/**
 * Update header mapping to include OHLC_Volume column
 * This extends the existing EW_headerMap function
 */
function EW_addOHLCToHeaderMap(hdrMap, headers) {
  // Find OHLC_Volume column
  for (let i = 0; i < headers.length; i++) {
    if (headers[i] === 'OHLC_Volume') {
      hdrMap.ohlcVolumeCol = i + 1;
      break;
    }
  }
  return hdrMap;
}

/**
 * Validate favorables calculations against OHLC data
 * Ensures Max_Favorable and Min_Unfavorable arrays match OHLC high/low values
 */
function EW_validateFavorablesAgainstOHLC() {
  const startTime = new Date();
  EW_trace('OHLC_VALIDATE', 'Starting validation of favorables against OHLC data', true);
  
  const sheet = SpreadsheetApp.getActiveSheet();
  const lastRow = sheet.getLastRow();
  
  if (lastRow < 2) {
    EW_safeAlert('No Data', 'No data rows to validate');
    return;
  }
  
  // Get headers
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  let hdrMap = EW_headerMap(headers);
  hdrMap = EW_addOHLCToHeaderMap(hdrMap, headers);
  
  // Check required columns
  if (!hdrMap.ohlcVolumeCol || !hdrMap.maxFavorableCol || !hdrMap.minUnfavorableCol) {
    EW_safeAlert('Missing Columns', 'Required columns not found');
    return;
  }
  
  // Get data
  const dataRange = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
  const data = dataRange.getValues();
  
  let discrepancies = [];
  let checked = 0;
  
  for (let i = 0; i < data.length; i++) {
    const rowNum = i + 2;
    const rowData = data[i];
    
    // Get OHLC data
    const ohlcData = rowData[hdrMap.ohlcVolumeCol - 1];
    const ohlcArray = EW_parseOHLCArray(ohlcData);
    
    // Get favorables arrays
    const maxFavData = rowData[hdrMap.maxFavorableCol - 1];
    const minUnfavData = rowData[hdrMap.minUnfavorableCol - 1];
    
    if (!ohlcArray || ohlcArray.length === 0) continue;
    if (!maxFavData || !minUnfavData) continue;
    
    checked++;
    
    // Parse favorables arrays
    let maxFavArray = [];
    let minUnfavArray = [];
    
    try {
      maxFavArray = typeof maxFavData === 'string' ? JSON.parse(maxFavData) : maxFavData;
      minUnfavArray = typeof minUnfavData === 'string' ? JSON.parse(minUnfavData) : minUnfavData;
    } catch (e) {
      discrepancies.push(`Row ${rowNum}: Failed to parse favorables arrays`);
      continue;
    }
    
    // Get strike price and strategy
    const strike = parseFloat(rowData[hdrMap.strikeCol - 1] || rowData[hdrMap.longStrikeCol - 1]);
    const strategy = rowData[hdrMap.strategyCol - 1] || sheet.getName();
    
    // Check each day
    for (let day = 0; day < Math.min(ohlcArray.length, maxFavArray.length); day++) {
      const ohlc = ohlcArray[day];
      if (!ohlc || !ohlc.h || !ohlc.l) continue;
      
      const dayHigh = parseFloat(ohlc.h);
      const dayLow = parseFloat(ohlc.l);
      const maxFav = parseFloat(maxFavArray[day]);
      const minUnfav = parseFloat(minUnfavArray[day]);
      
      // Recalculate expected values based on strategy
      const expectedMaxFav = EW_calculateMaxFavorableForDay(strategy, strike, dayHigh, dayLow);
      const expectedMinUnfav = EW_calculateMinUnfavorableForDay(strategy, strike, dayHigh, dayLow);
      
      // Check for discrepancies (allow small float differences)
      if (Math.abs(maxFav - expectedMaxFav) > 0.01) {
        discrepancies.push(`Row ${rowNum}, Day ${day}: MaxFav mismatch - stored: ${maxFav}, expected: ${expectedMaxFav}`);
      }
      if (Math.abs(minUnfav - expectedMinUnfav) > 0.01) {
        discrepancies.push(`Row ${rowNum}, Day ${day}: MinUnfav mismatch - stored: ${minUnfav}, expected: ${expectedMinUnfav}`);
      }
    }
  }
  
  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);
  
  // Report results
  let msg = `Validation complete.\nChecked: ${checked} rows\nDuration: ${duration} seconds\n\n`;
  
  if (discrepancies.length === 0) {
    msg += 'No discrepancies found! All favorables match OHLC data.';
  } else {
    msg += `Found ${discrepancies.length} discrepancies:\n\n${discrepancies.slice(0, 10).join('\n')}`;
    if (discrepancies.length > 10) {
      msg += `\n... and ${discrepancies.length - 10} more`;
    }
  }
  
  EW_safeAlert('Validation Results', msg);
  console.log(`OHLC_VALIDATE: Completed - checked ${checked} rows, found ${discrepancies.length} discrepancies`);
  
  return {
    checked: checked,
    discrepancies: discrepancies.length,
    duration: duration
  };
}

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