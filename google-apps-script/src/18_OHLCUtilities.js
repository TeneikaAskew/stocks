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