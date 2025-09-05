/**
 * OHLC_Volume Column Management
 * Functions to populate the OHLC_Volume column with comprehensive daily data
 * Note: Day_Checks method deprecated as it only provides close prices (unreliable)
 * Always use backfill for complete OHLC data needed for accurate calculations
 */

/**
 * Main function to rename Peak_Profit_Date column to OHLC_Volume across all sheets
 * This should be run once to update all column headers
 */
function EW_renamePeakProfitToOHLC() {
  const startTime = new Date();
  EW_trace('OHLC_RENAME', 'Starting column rename from Peak_Profit_Date to OHLC_Volume', true);
  console.log(`OHLC_RENAME: Starting rename process at ${startTime.toISOString()}`);
  
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  
  let renamedCount = 0;
  let errors = [];
  
  for (const strategy of strategies) {
    try {
      const sheet = ss.getSheetByName(strategy);
      if (!sheet || sheet.getLastRow() < 1) {
        continue;
      }
      
      // Get headers
      const headerRow = 1;
      const lastCol = sheet.getLastColumn();
      const headers = sheet.getRange(headerRow, 1, 1, lastCol).getValues()[0];
      
      // Find Peak_Profit_Date column
      let foundCol = -1;
      for (let i = 0; i < headers.length; i++) {
        if (headers[i] === 'Peak_Profit_Date') {
          foundCol = i + 1; // Convert to 1-based index
          break;
        }
      }
      
      if (foundCol > 0) {
        // Rename the column
        sheet.getRange(headerRow, foundCol).setValue('OHLC_Volume');
        renamedCount++;
        EW_trace('OHLC_RENAME', `${strategy}: Renamed column ${foundCol} from Peak_Profit_Date to OHLC_Volume`);
        console.log(`OHLC_RENAME: Renamed column in ${strategy} sheet`);
      } else {
        EW_trace('OHLC_RENAME', `${strategy}: Peak_Profit_Date column not found, checking for OHLC_Volume`);
        
        // Check if OHLC_Volume already exists
        const hasOHLC = headers.some(h => h === 'OHLC_Volume');
        if (!hasOHLC) {
          errors.push(`${strategy}: Neither Peak_Profit_Date nor OHLC_Volume column found`);
        }
      }
      
    } catch (e) {
      errors.push(`${strategy}: ${e.message}`);
      EW_trace('OHLC_RENAME', `Error renaming in ${strategy}: ${e.message}`, true);
      console.error(`OHLC_RENAME ERROR: ${strategy} - ${e.message}`);
    }
  }
  
  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);
  
  const msg = `Column rename complete.\n` +
    `Renamed: ${renamedCount} sheets\n` +
    `Total strategies: ${strategies.length}\n` +
    `Duration: ${duration} seconds` +
    (errors.length > 0 ? `\n\nIssues:\n${errors.join('\n')}` : '');
  
  EW_trace('OHLC_RENAME', msg, true);
  console.log(`OHLC_RENAME: Completed in ${duration} seconds - Renamed ${renamedCount} columns`);
  
  EW_safeAlert('Rename Complete', msg);
  
  return { renamed: renamedCount, duration: duration, errors: errors };
}

/**
 * Build OHLC_Volume array for a specific day
 * @param {Array} existingArray - Current OHLC array (can be empty)
 * @param {number} dayIndex - Day index (0-5)
 * @param {Object} ohlcData - Object with open, high, low, close, volume
 * @param {string} source - Source of the data (e.g., 'BACKFILL', 'ACTIVE', 'DAY_CHECK')
 * @returns {Array} Updated array with new OHLC data at dayIndex
 */
function EW_buildOHLCArray(existingArray = [], dayIndex, ohlcData, source = 'UNKNOWN') {
  if (dayIndex < 0 || dayIndex > 5 || !ohlcData) return existingArray;
  
  // Ensure array has correct length (6 days)
  const array = existingArray.slice();
  while (array.length <= dayIndex) {
    array.push(null);
  }
  
  // Create OHLC object for this day
  if (ohlcData.open !== null && ohlcData.open !== undefined) {
    const dayOHLC = {
      o: parseFloat(ohlcData.open).toFixed(2),
      h: parseFloat(ohlcData.high).toFixed(2),
      l: parseFloat(ohlcData.low).toFixed(2),
      c: parseFloat(ohlcData.close).toFixed(2),
      v: ohlcData.volume || 0,
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
      v: 0,
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
 * DEPRECATED: Populate from Day_Checks (unreliable - only has close prices)
 * @deprecated Use EW_populateOHLCWithBackfill() instead
 */
function EW_populateOHLCFromDayChecks() {
  const startTime = new Date();
  EW_trace('OHLC_POPULATE', 'Starting OHLC_Volume population from Day_Check data only', true);
  console.log(`OHLC_POPULATE: Populating from Day_Check data (close prices only)`);
  
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
      
      const result = EW_populateOHLCForSheet(sheet, strategy, 'DAY_CHECK');
      processedCount += result.processed;
      updatedCount += result.updated;
      
      if (result.errors.length > 0) {
        errors.push(...result.errors.map(e => `${strategy}: ${e}`));
      }
      
      EW_trace('OHLC_POPULATE', `${strategy}: Processed ${result.processed} rows, updated ${result.updated}`);
      
    } catch (e) {
      errors.push(`${strategy}: ${e.message}`);
      EW_trace('OHLC_POPULATE', `Error processing ${strategy}: ${e.message}`, true);
      console.error(`OHLC_POPULATE ERROR: ${strategy} - ${e.message}`);
    }
  }
  
  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);
  
  const msg = `OHLC population from Day_Check complete.\n` +
    `Processed: ${processedCount} rows\n` +
    `Updated: ${updatedCount} rows\n` +
    `Duration: ${duration} seconds\n` +
    `Note: Only close prices populated from Day_Check data` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');
  
  EW_trace('OHLC_POPULATE', msg, true);
  console.log(`OHLC_POPULATE: Completed in ${duration} seconds - Updated ${updatedCount}/${processedCount} rows with Day_Check data`);
  
  EW_safeAlert('Day_Check Population Complete', msg);
  
  return { processed: processedCount, updated: updatedCount, duration: duration, errors: errors };
}

/**
 * Populate OHLC for a specific sheet from Day_Check data
 * @param {Sheet} sheet - The sheet to process
 * @param {string} strategyName - Name of the strategy
 * @param {string} source - Source identifier for logging
 */
function EW_populateOHLCForSheet(sheet, strategyName, source = 'DAY_CHECK') {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return { processed: 0, updated: 0, errors: [] };
  }
  
  // Get header mapping
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  let hdrMap = EW_headerMap(headers);
  hdrMap = EW_addOHLCToHeaderMap(hdrMap, headers);
  
  // Check if sheet has OHLC_Volume column
  if (!hdrMap.ohlcVolumeCol) {
    return { processed: 0, updated: 0, errors: ['OHLC_Volume column not found'] };
  }
  
  // Get ticker and run date columns
  const tickerCol = hdrMap.tickerCol;
  const runDateCol = hdrMap.runDateCol;
  
  if (!tickerCol || !runDateCol) {
    return { processed: 0, updated: 0, errors: ['Missing required columns (ticker, runDate)'] };
  }
  
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
      // Check if OHLC already populated
      const currentOHLC = rowData[hdrMap.ohlcVolumeCol - 1];
      if (currentOHLC && currentOHLC !== '' && currentOHLC !== '[]') {
        continue; // Skip rows that already have OHLC data
      }
      
      // Get ticker and run date
      const ticker = rowData[tickerCol - 1];
      const runDate = rowData[runDateCol - 1];
      
      if (!ticker || !runDate) {
        continue;
      }
      
      // Build OHLC array from existing day check data if available
      const ohlcArray = [];
      let hasData = false;
      
      // Try to get data from day checks first (they might have close prices)
      for (let day = 0; day <= 5; day++) {
        const dayCol = hdrMap[`day${day}CheckCol`];
        if (dayCol) {
          const dayPrice = rowData[dayCol - 1];
          if (dayPrice && dayPrice !== '' && dayPrice !== 'None' && dayPrice !== null) {
            // We only have closing price from day checks
            ohlcArray.push({
              o: null, // No open price from day checks
              h: null, // No high price from day checks
              l: null, // No low price from day checks
              c: parseFloat(dayPrice).toFixed(2),
              v: 0, // No volume from day checks
              src: source // Track that this came from Day_Check data
            });
            hasData = true;
          } else {
            ohlcArray.push(null);
          }
        } else {
          ohlcArray.push(null);
        }
      }
      
      // If we have any data, save it with source tracking
      if (hasData) {
        const jsonData = JSON.stringify(ohlcArray);
        sheet.getRange(rowNum, hdrMap.ohlcVolumeCol).setValue(jsonData);
        updatedCount++;
        EW_trace('OHLC_POPULATE', `Row ${rowNum}: Populated with ${source} data`);
      }
      
    } catch (e) {
      errors.push(`Row ${rowNum}: ${e.message}`);
      EW_trace('OHLC_POPULATE', `Error processing row ${rowNum}: ${e.message}`);
    }
  }
  
  return {
    processed: processedCount,
    updated: updatedCount,
    errors: errors
  };
}

/**
 * Populate OHLC_Volume with full historical data using backfill
 * This gets actual OHLC data from Yahoo Finance, not just closing prices
 */
function EW_populateOHLCWithBackfill() {
  const startTime = new Date();
  EW_trace('OHLC_BACKFILL', 'Starting OHLC_Volume population using backfill (full OHLC data)', true);
  console.log(`OHLC_BACKFILL: Starting backfill to populate full OHLC data`);
  
  // Use the backfill function which will populate OHLC_Volume with full data
  EW_trace('OHLC_BACKFILL', 'Triggering backfill to populate OHLC_Volume column with full historical data');
  
  // Call backfill which now populates OHLC_Volume automatically
  const result = EW_backfillHistoricalTracking();
  
  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);
  
  const msg = `OHLC backfill population complete.\n` +
    `This ran the full backfill process which populates:\n` +
    `- OHLC_Volume with full open/high/low/close/volume data\n` +
    `- All other tracking columns\n` +
    `Duration: ${duration} seconds\n` +
    `Note: Data source logged as 'BACKFILL' in OHLC entries`;
  
  EW_trace('OHLC_BACKFILL', msg, true);
  console.log(`OHLC_BACKFILL: Completed in ${duration} seconds`);
  
  EW_safeAlert('OHLC Backfill Complete', msg);
  
  return result;
}

/**
 * Main function to populate OHLC_Volume - always uses backfill for reliable data
 * Day_Checks method removed as it only provides close prices (unreliable for favorables)
 */
function EW_populateOHLCVolume() {
  // Always use backfill for reliable OHLC data
  EW_trace('OHLC_POPULATE', 'Populating OHLC_Volume using backfill for complete data');
  return EW_populateOHLCWithBackfill();
}

/**
 * Test function to verify OHLC array building
 */
function EW_testOHLCArrayBuilder() {
  console.log('Testing OHLC array builder...');
  
  // Test data
  const testOHLC = {
    open: 100.5,
    high: 102.3,
    low: 99.8,
    close: 101.2,
    volume: 1500000
  };
  
  // Build array
  let array = [];
  array = EW_buildOHLCArray(array, 0, testOHLC);
  array = EW_buildOHLCArray(array, 1, {
    open: 101.2,
    high: 103.5,
    low: 100.9,
    close: 102.8,
    volume: 1800000
  });
  
  console.log('Built OHLC array:', JSON.stringify(array, null, 2));
  
  // Test parsing
  const jsonString = JSON.stringify(array);
  const parsed = EW_parseOHLCArray(jsonString);
  console.log('Parsed OHLC array:', JSON.stringify(parsed, null, 2));
  
  return array;
}