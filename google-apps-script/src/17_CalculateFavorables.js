/**
 * Calculate Missing Favorable/Unfavorable Values
 * Functions to calculate and fill in Max_Favorable and Min_Unfavorable arrays
 * for rows that have blank or null values in these columns
 * UPDATED: Now uses OHLC_Volume column data instead of making API calls
 */

/**
 * Main function to calculate missing Max_Favorable and Min_Unfavorable values
 * This can be run from the menu to fill in blank values
 * Now uses OHLC_Volume data for much faster processing
 */
function EW_calculateMissingFavorables() {
  const startTime = new Date();
  EW_trace('FAVORABLES', 'Starting calculation using OHLC_Volume data (no API calls)', true);
  console.log(`FAVORABLES: Starting calculation at ${startTime.toISOString()}`);
  
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  
  let processedCount = 0;
  let updatedCount = 0;
  let skippedNoOHLC = 0;
  let recalculatedZeros = 0;
  let errors = [];
  
  for (const strategy of strategies) {
    try {
      const sheet = ss.getSheetByName(strategy);
      if (!sheet || sheet.getLastRow() < 2) {
        continue;
      }
      
      const result = EW_calculateFavorablesFromOHLC(sheet, strategy);
      processedCount += result.processed;
      updatedCount += result.updated;
      skippedNoOHLC += result.skippedNoOHLC || 0;
      recalculatedZeros += result.recalculatedZeros || 0;
      
      if (result.errors.length > 0) {
        errors.push(...result.errors.map(e => `${strategy}: ${e}`));
      }
      
      EW_trace('FAVORABLES', `${strategy}: Processed ${result.processed} rows, updated ${result.updated}, skipped ${result.skippedNoOHLC || 0} (no OHLC)`);
      
    } catch (e) {
      errors.push(`${strategy}: ${e.message}`);
      EW_trace('FAVORABLES', `Error processing ${strategy}: ${e.message}`, true);
      console.error(`FAVORABLES ERROR: ${strategy} - ${e.message}`);
    }
  }
  
  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);
  
  const msg = `Favorable calculation complete (using OHLC data).\n` +
    `Processed: ${processedCount} rows\n` +
    `Updated: ${updatedCount} rows\n` +
    (recalculatedZeros > 0 ? `Recalculated (all zeros): ${recalculatedZeros} rows\n` : '') +
    `Skipped (no OHLC): ${skippedNoOHLC} rows\n` +
    `Duration: ${duration} seconds` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');
  
  EW_trace('FAVORABLES', msg, true);
  console.log(`FAVORABLES: Completed in ${duration} seconds - Updated ${updatedCount}/${processedCount} rows`);
  
  EW_safeAlert('Calculation Complete', msg);
  
  return { processed: processedCount, updated: updatedCount, duration: duration, errors: errors, skippedNoOHLC: skippedNoOHLC, recalculatedZeros: recalculatedZeros };
}

/**
 * Calculate favorables for selected rows only using OHLC data
 */
function EW_calculateFavorablesForSelected() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const range = sheet.getActiveRange();
  
  if (!range) {
    EW_safeAlert('No Selection', 'Please select rows to process');
    return;
  }
  
  const startRow = range.getRow();
  const numRows = range.getNumRows();
  
  // Skip if header row is selected
  if (startRow === 1) {
    EW_safeAlert('Invalid Selection', 'Please select data rows (not the header row)');
    return;
  }
  
  const result = EW_calculateFavorablesFromOHLC(sheet, sheet.getName(), startRow, numRows);
  
  const msg = `Processing complete (using OHLC data).\n` +
    `Processed: ${result.processed} rows\n` +
    `Updated: ${result.updated} rows\n` +
    `Skipped (no OHLC): ${result.skippedNoOHLC || 0} rows` +
    (result.errors.length > 0 ? `\n\nErrors:\n${result.errors.join('\n')}` : '');
  
  EW_safeAlert('Calculation Complete', msg);
}

/**
 * Calculate favorables from OHLC_Volume data (fast, no API calls)
 * @param {Sheet} sheet - The sheet to process
 * @param {string} strategyName - Name of the strategy
 * @param {number} startRow - Optional starting row (default: 2)
 * @param {number} numRows - Optional number of rows to process (default: all)
 */
function EW_calculateFavorablesFromOHLC(sheet, strategyName, startRow = 2, numRows = null) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return { processed: 0, updated: 0, errors: [] };
  }
  
  // Get header mapping
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Add OHLC_Volume column to header map
  for (let i = 0; i < headers.length; i++) {
    if (headers[i] === 'OHLC_Volume' || headers[i] === 'Peak_Profit_Date') {
      hdrMap.ohlcVolumeCol = i + 1;
      break;
    }
  }
  
  // Check if sheet has the necessary columns
  if (!hdrMap.maxFavorableCol || !hdrMap.minUnfavorableCol) {
    EW_trace('FAVORABLES', `${strategyName}: Missing Max_Favorable or Min_Unfavorable columns`);
    return { processed: 0, updated: 0, errors: ['Missing required columns'] };
  }
  
  if (!hdrMap.ohlcVolumeCol) {
    EW_trace('FAVORABLES', `${strategyName}: Missing OHLC_Volume column - cannot calculate from OHLC data`);
    return { processed: 0, updated: 0, errors: ['OHLC_Volume column not found'] };
  }
  
  // Determine strike column
  const strikeCol = hdrMap.strikeCol || hdrMap.longStrikeCol;
  if (!strikeCol) {
    return { processed: 0, updated: 0, errors: ['Missing strike column'] };
  }
  
  const shortStrikeCol = hdrMap.shortStrikeCol; // For spreads
  
  // Calculate rows to process
  const endRow = numRows ? Math.min(startRow + numRows - 1, lastRow) : lastRow;
  const rowsToProcess = endRow - startRow + 1;
  
  // Get all data at once
  const dataRange = sheet.getRange(startRow, 1, rowsToProcess, sheet.getLastColumn());
  const data = dataRange.getValues();
  
  let processedCount = 0;
  let updatedCount = 0;
  let skippedNoOHLC = 0;
  let recalculatedZeros = 0;
  let errors = [];
  
  // Batch arrays for updates
  const maxFavUpdates = [];
  const minUnfavUpdates = [];
  const rowsToUpdate = [];
  
  // Process each row
  for (let i = 0; i < data.length; i++) {
    const rowNum = startRow + i;
    const rowData = data[i];
    
    processedCount++;
    
    try {
      // Get current values
      const currentMaxFav = rowData[hdrMap.maxFavorableCol - 1];
      const currentMinUnfav = rowData[hdrMap.minUnfavorableCol - 1];
      
      // Helper function to check if array has all zeros
      const hasAllZeros = (arrayStr) => {
        if (!arrayStr || arrayStr === '') return false;
        try {
          const parsed = typeof arrayStr === 'string' ? JSON.parse(arrayStr) : arrayStr;
          if (!Array.isArray(parsed)) return false;
          // Check if all values are zero or "0.000000"
          return parsed.every(val => val === null || parseFloat(val) === 0);
        } catch (e) {
          return false;
        }
      };
      
      // Check if either needs calculation
      const needsMaxFav = !currentMaxFav || currentMaxFav === '' || 
                         (typeof currentMaxFav === 'string' && currentMaxFav === '[]') ||
                         hasAllZeros(currentMaxFav);
      const needsMinUnfav = !currentMinUnfav || currentMinUnfav === '' || 
                           (typeof currentMinUnfav === 'string' && currentMinUnfav === '[]') ||
                           hasAllZeros(currentMinUnfav);
      
      if (!needsMaxFav && !needsMinUnfav) {
        continue; // Skip rows that already have proper values
      }
      
      // Log if we're recalculating due to all zeros
      let isRecalcZeros = false;
      if (hasAllZeros(currentMaxFav)) {
        EW_trace('FAVORABLES', `Row ${rowNum}: Recalculating Max_Favorable due to all zero values`);
        isRecalcZeros = true;
      }
      if (hasAllZeros(currentMinUnfav)) {
        EW_trace('FAVORABLES', `Row ${rowNum}: Recalculating Min_Unfavorable due to all zero values`);
        isRecalcZeros = true;
      }
      
      // Get strike price(s)
      const strike = parseFloat(rowData[strikeCol - 1]);
      const shortStrike = shortStrikeCol ? parseFloat(rowData[shortStrikeCol - 1]) : null;
      
      if (!strike || isNaN(strike)) {
        errors.push(`Row ${rowNum}: Invalid strike price`);
        continue;
      }
      
      // Get OHLC data instead of day check values
      const ohlcData = rowData[hdrMap.ohlcVolumeCol - 1];
      if (!ohlcData || ohlcData === '' || ohlcData === '[]') {
        skippedNoOHLC++;
        continue; // No OHLC data available
      }
      
      // Parse OHLC array
      let ohlcArray;
      try {
        ohlcArray = typeof ohlcData === 'string' ? JSON.parse(ohlcData) : ohlcData;
      } catch (e) {
        errors.push(`Row ${rowNum}: Invalid OHLC format`);
        continue;
      }
      
      // Check if we have any valid OHLC data
      const hasData = ohlcArray && ohlcArray.length > 0 && 
                     ohlcArray.some(day => day && day.h && day.l);
      if (!hasData) {
        skippedNoOHLC++;
        continue;
      }
      
      // Calculate arrays
      const maxFavArray = [];
      const minUnfavArray = [];
      
      // Determine strategy type
      const strategyUpper = strategyName.toUpperCase();
      const isBullish = strategyUpper.includes('LONG CALL') || strategyUpper.includes('BULL');
      const isBearish = strategyUpper.includes('LONG PUT') || strategyUpper.includes('BEAR');
      const isBullSpread = strategyUpper.includes('BULL SPREAD');
      const isBearSpread = strategyUpper.includes('BEAR SPREAD');
      
      // Process each day using OHLC data
      for (let day = 0; day < ohlcArray.length && day <= 5; day++) {
        const dayOHLC = ohlcArray[day];
        
        if (!dayOHLC || dayOHLC === null) {
          maxFavArray.push(null);
          minUnfavArray.push(null);
          continue;
        }
        
        // Extract high and low from OHLC data
        const dayHigh = parseFloat(dayOHLC.h);
        const dayLow = parseFloat(dayOHLC.l);
        
        if (isNaN(dayHigh) || isNaN(dayLow)) {
          maxFavArray.push(null);
          minUnfavArray.push(null);
          continue;
        }
        
        // Now we have actual high/low data, so use the proper calculation functions
        const maxFav = EW_calculateMaxFavorableForDay(strategyName, strike, dayHigh, dayLow);
        const minUnfav = EW_calculateMinUnfavorableForDay(strategyName, strike, dayHigh, dayLow);
        
        maxFavArray.push(maxFav);
        minUnfavArray.push(minUnfav);
      }
      
      // Pad with nulls if we have less than 6 days
      while (maxFavArray.length < 6) {
        maxFavArray.push(null);
        minUnfavArray.push(null);
      }
      
      // Store updates for batch processing
      if (needsMaxFav && maxFavArray.some(v => v !== null)) {
        maxFavUpdates.push(JSON.stringify(maxFavArray));
        if (needsMinUnfav && minUnfavArray.some(v => v !== null)) {
          minUnfavUpdates.push(JSON.stringify(minUnfavArray));
        } else {
          minUnfavUpdates.push(currentMinUnfav); // Keep existing value
        }
        rowsToUpdate.push(rowNum);
        updatedCount++;
        if (isRecalcZeros) recalculatedZeros++;
      } else if (needsMinUnfav && minUnfavArray.some(v => v !== null)) {
        maxFavUpdates.push(currentMaxFav); // Keep existing value
        minUnfavUpdates.push(JSON.stringify(minUnfavArray));
        rowsToUpdate.push(rowNum);
        updatedCount++;
        if (isRecalcZeros) recalculatedZeros++;
      }
      
    } catch (e) {
      errors.push(`Row ${rowNum}: ${e.message}`);
      EW_trace('FAVORABLES', `Error processing row ${rowNum}: ${e.message}`);
    }
  }
  
  // Apply batch updates
  if (rowsToUpdate.length > 0) {
    for (let i = 0; i < rowsToUpdate.length; i++) {
      const row = rowsToUpdate[i];
      if (maxFavUpdates[i] && maxFavUpdates[i] !== '') {
        sheet.getRange(row, hdrMap.maxFavorableCol).setValue(maxFavUpdates[i]);
      }
      if (minUnfavUpdates[i] && minUnfavUpdates[i] !== '') {
        sheet.getRange(row, hdrMap.minUnfavorableCol).setValue(minUnfavUpdates[i]);
      }
    }
    
    EW_trace('FAVORABLES', `${strategyName}: Updated ${updatedCount} rows with favorable/unfavorable values`);
  }
  
  return {
    processed: processedCount,
    updated: updatedCount,
    skippedNoOHLC: skippedNoOHLC,
    recalculatedZeros: recalculatedZeros,
    errors: errors
  };
}

