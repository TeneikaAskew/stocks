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
    `Skipped (no OHLC): ${skippedNoOHLC} rows\n` +
    `Duration: ${duration} seconds` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');
  
  EW_trace('FAVORABLES', msg, true);
  console.log(`FAVORABLES: Completed in ${duration} seconds - Updated ${updatedCount}/${processedCount} rows`);
  
  EW_safeAlert('Calculation Complete', msg);
  
  return { processed: processedCount, updated: updatedCount, duration: duration, errors: errors, skippedNoOHLC: skippedNoOHLC };
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
  
  // Check if sheet has the necessary columns
  if (!hdrMap.maxFavorableCol || !hdrMap.minUnfavorableCol) {
    EW_trace('FAVORABLES', `${strategyName}: Missing Max_Favorable or Min_Unfavorable columns`);
    return { processed: 0, updated: 0, errors: ['Missing required columns'] };
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
      
      // Check if either needs calculation
      const needsMaxFav = !currentMaxFav || currentMaxFav === '' || 
                         (typeof currentMaxFav === 'string' && currentMaxFav === '[]');
      const needsMinUnfav = !currentMinUnfav || currentMinUnfav === '' || 
                           (typeof currentMinUnfav === 'string' && currentMinUnfav === '[]');
      
      if (!needsMaxFav && !needsMinUnfav) {
        continue; // Skip rows that already have values
      }
      
      // Get strike price(s)
      const strike = parseFloat(rowData[strikeCol - 1]);
      const shortStrike = shortStrikeCol ? parseFloat(rowData[shortStrikeCol - 1]) : null;
      
      if (!strike || isNaN(strike)) {
        errors.push(`Row ${rowNum}: Invalid strike price`);
        continue;
      }
      
      // Get day check values to calculate from
      const dayChecks = [];
      for (let day = 0; day <= 5; day++) {
        const dayCol = hdrMap[`day${day}CheckCol`];
        if (dayCol) {
          const value = rowData[dayCol - 1];
          if (value && value !== '' && value !== null) {
            dayChecks.push(parseFloat(value));
          } else {
            dayChecks.push(null);
          }
        } else {
          dayChecks.push(null);
        }
      }
      
      // Check if we have any data to work with
      const hasData = dayChecks.some(v => v !== null && !isNaN(v));
      if (!hasData) {
        // No day check data available, skip
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
      
      // Process each day
      for (let day = 0; day <= 5; day++) {
        const dayPrice = dayChecks[day];
        
        if (dayPrice === null || isNaN(dayPrice)) {
          maxFavArray.push(null);
          minUnfavArray.push(null);
          continue;
        }
        
        // For day checks, we only have the closing price, not high/low
        // So we'll calculate based on the closing price relative to strike
        let maxFav = null;
        let minUnfav = null;
        
        if (isBullish) {
          // Bullish: favorable when price > strike, unfavorable when price < strike
          if (dayPrice >= strike) {
            maxFav = ((dayPrice - strike) / strike).toFixed(6);
            minUnfav = "0.000000"; // No unfavorable move if price is above strike
          } else {
            maxFav = "0.000000"; // No favorable move if price is below strike
            minUnfav = ((strike - dayPrice) / strike).toFixed(6);
          }
        } else if (isBearish) {
          // Bearish: favorable when price < strike, unfavorable when price > strike
          if (dayPrice <= strike) {
            maxFav = ((strike - dayPrice) / strike).toFixed(6);
            minUnfav = "0.000000"; // No unfavorable move if price is below strike
          } else {
            maxFav = "0.000000"; // No favorable move if price is above strike
            minUnfav = ((dayPrice - strike) / strike).toFixed(6);
          }
        } else if (isBullSpread && shortStrike) {
          // Bull spread: capped profit at short strike
          const maxProfit = (shortStrike - strike) / strike;
          if (dayPrice >= shortStrike) {
            maxFav = maxProfit.toFixed(6);
            minUnfav = "0.000000";
          } else if (dayPrice >= strike) {
            maxFav = ((dayPrice - strike) / strike).toFixed(6);
            minUnfav = "0.000000";
          } else {
            maxFav = "0.000000";
            minUnfav = ((strike - dayPrice) / strike).toFixed(6);
          }
        } else if (isBearSpread && shortStrike) {
          // Bear spread: capped profit at short strike
          const maxProfit = (strike - shortStrike) / strike;
          if (dayPrice <= shortStrike) {
            maxFav = maxProfit.toFixed(6);
            minUnfav = "0.000000";
          } else if (dayPrice <= strike) {
            maxFav = ((strike - dayPrice) / strike).toFixed(6);
            minUnfav = "0.000000";
          } else {
            maxFav = "0.000000";
            minUnfav = ((dayPrice - strike) / strike).toFixed(6);
          }
        } else {
          // Neutral or other strategies - calculate both directions
          const upMove = Math.max(0, (dayPrice - strike) / strike);
          const downMove = Math.max(0, (strike - dayPrice) / strike);
          maxFav = Math.max(upMove, downMove).toFixed(6);
          minUnfav = Math.min(upMove, downMove).toFixed(6);
        }
        
        maxFavArray.push(maxFav);
        minUnfavArray.push(minUnfav);
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
      } else if (needsMinUnfav && minUnfavArray.some(v => v !== null)) {
        maxFavUpdates.push(currentMaxFav); // Keep existing value
        minUnfavUpdates.push(JSON.stringify(minUnfavArray));
        rowsToUpdate.push(rowNum);
        updatedCount++;
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
    errors: errors
  };
}

/**
 * Calculate favorables using historical data (more accurate)
 * This version fetches actual high/low data from Yahoo Finance
 */
function EW_calculateFavorablesWithHistorical() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const range = sheet.getActiveRange();
  
  if (!range) {
    EW_safeAlert('No Selection', 'Please select rows to process');
    return;
  }
  
  const startRow = range.getRow();
  const numRows = range.getNumRows();
  
  if (startRow === 1) {
    EW_safeAlert('Invalid Selection', 'Please select data rows (not the header row)');
    return;
  }
  
  EW_trace('FAVORABLES', `Starting historical calculation for ${numRows} rows`, true);
  
  // Get header mapping
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Use backfill logic for more accurate calculation
  const tickerCol = hdrMap.tickerCol;
  const runDateCol = hdrMap.runDateCol;
  const strikeCol = hdrMap.strikeCol || hdrMap.longStrikeCol;
  
  if (!tickerCol || !runDateCol || !strikeCol) {
    EW_safeAlert('Missing Columns', 'Required columns (ticker, runDate, strike) not found');
    return;
  }
  
  let updatedCount = 0;
  
  for (let i = 0; i < numRows; i++) {
    const rowNum = startRow + i;
    const ticker = sheet.getRange(rowNum, tickerCol).getValue();
    const runDate = sheet.getRange(rowNum, runDateCol).getValue();
    const strike = sheet.getRange(rowNum, strikeCol).getValue();
    
    if (!ticker || !runDate || !strike) continue;
    
    try {
      // Fetch 6 days of historical data starting from runDate
      const dates = [];
      const startDate = new Date(runDate);
      
      for (let day = 0; day <= 5; day++) {
        const checkDate = new Date(startDate);
        checkDate.setDate(checkDate.getDate() + day);
        dates.push(checkDate);
      }
      
      const maxFavArray = [];
      const minUnfavArray = [];
      const strategyName = sheet.getName();
      
      for (const date of dates) {
        const result = EW_fetchYahooHistoricalForDate(ticker, date, true);
        
        if (result && result.dayHigh && result.dayLow) {
          // Use the array builder functions for consistency
          const maxFav = EW_calculateMaxFavorableForDay(
            strategyName, strike, result.dayHigh, result.dayLow
          );
          const minUnfav = EW_calculateMinUnfavorableForDay(
            strategyName, strike, result.dayHigh, result.dayLow
          );
          
          maxFavArray.push(maxFav);
          minUnfavArray.push(minUnfav);
        } else {
          maxFavArray.push(null);
          minUnfavArray.push(null);
        }
      }
      
      // Update the sheet
      if (maxFavArray.some(v => v !== null)) {
        sheet.getRange(rowNum, hdrMap.maxFavorableCol).setValue(JSON.stringify(maxFavArray));
        sheet.getRange(rowNum, hdrMap.minUnfavorableCol).setValue(JSON.stringify(minUnfavArray));
        updatedCount++;
      }
      
    } catch (e) {
      EW_trace('FAVORABLES', `Error processing row ${rowNum}: ${e.message}`);
    }
  }
  
  const msg = `Historical calculation complete.\nUpdated ${updatedCount} of ${numRows} rows with accurate high/low data.`;
  EW_safeAlert('Calculation Complete', msg);
}