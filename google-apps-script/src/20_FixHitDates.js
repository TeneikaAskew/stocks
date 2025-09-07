/**
 * Fix Hit_Date Values Based on Strike_Hit Array
 * This utility corrects Hit_Date values to show the day number (0-5)
 * when the position first became profitable
 */

/**
 * Main function to fix Hit_Date values across all strategy sheets
 * Updates Hit_Date to show day number (0-5) instead of actual date
 */
function EW_fixHitDates() {
  const startTime = new Date();
  EW_trace('FIX_HIT_DATES', 'Starting Hit_Date correction to day numbers', true);
  console.log(`FIX_HIT_DATES: Starting at ${startTime.toISOString()}`);
  
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  
  let totalProcessed = 0;
  let totalCorrected = 0;
  let errors = [];
  
  for (const strategy of strategies) {
    try {
      const sheet = ss.getSheetByName(strategy);
      if (!sheet || sheet.getLastRow() < 2) {
        continue;
      }
      
      const result = EW_fixHitDatesForSheet(sheet, strategy);
      totalProcessed += result.processed;
      totalCorrected += result.corrected;
      
      if (result.errors.length > 0) {
        errors.push(...result.errors.map(e => `${strategy}: ${e}`));
      }
      
      EW_trace('FIX_HIT_DATES', `${strategy}: Processed ${result.processed} rows, corrected ${result.corrected}`);
      
    } catch (e) {
      errors.push(`${strategy}: ${e.message}`);
      EW_trace('FIX_HIT_DATES', `Error processing ${strategy}: ${e.message}`, true);
    }
  }
  
  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);
  
  const msg = `Hit_Date correction complete.\n` +
    `Processed: ${totalProcessed} rows\n` +
    `Corrected: ${totalCorrected} rows\n` +
    `Duration: ${duration} seconds` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');
  
  EW_trace('FIX_HIT_DATES', msg, true);
  console.log(`FIX_HIT_DATES: Completed in ${duration} seconds - Corrected ${totalCorrected}/${totalProcessed} rows`);
  
  EW_safeAlert('Hit_Date Correction Complete', msg);
  
  return { processed: totalProcessed, corrected: totalCorrected, duration: duration, errors: errors };
}

/**
 * Fix Hit_Date values for a specific sheet
 * Sets Hit_Date to the day number (0-5) when strike was first hit
 */
function EW_fixHitDatesForSheet(sheet, strategyName) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return { processed: 0, corrected: 0, errors: [] };
  }
  
  // Get header mapping
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Check required columns
  if (!hdrMap.hitDateCol || !hdrMap.strikeHitCol) {
    return { processed: 0, corrected: 0, errors: ['Missing required columns'] };
  }
  
  // Get all data at once
  const dataRange = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
  const data = dataRange.getValues();
  
  let processedCount = 0;
  let correctedCount = 0;
  let errors = [];
  
  // Process each row
  for (let i = 0; i < data.length; i++) {
    const rowNum = i + 2;
    const rowData = data[i];
    
    processedCount++;
    
    try {
      // Get current values
      const currentHitDate = rowData[hdrMap.hitDateCol - 1];
      const strikeHitArray = rowData[hdrMap.strikeHitCol - 1];
      
      // Skip if no Strike_Hit data
      if (!strikeHitArray) {
        continue;
      }
      
      // Parse Strike_Hit array
      let strikeHitParsed;
      try {
        strikeHitParsed = typeof strikeHitArray === 'string' ? JSON.parse(strikeHitArray) : strikeHitArray;
      } catch (e) {
        errors.push(`Row ${rowNum}: Invalid Strike_Hit format`);
        continue;
      }
      
      // Find first day with a positive value in Strike_Hit array
      // Positive value means the position is profitable
      let firstHitDay = -1;
      for (let day = 0; day < strikeHitParsed.length && day <= 5; day++) {
        const value = strikeHitParsed[day];
        // Check for positive value (profitable position)
        if (value !== null && parseFloat(value) > 0) {
          firstHitDay = day;
          break;
        }
      }
      
      // If strike was never hit, leave Hit_Date empty
      if (firstHitDay === -1) {
        // Clear Hit_Date if it had a value but strike was never hit
        if (currentHitDate !== '' && currentHitDate !== null) {
          sheet.getRange(rowNum, hdrMap.hitDateCol).setValue('');
          correctedCount++;
          const ticker = rowData[hdrMap.tickerCol - 1] || `Row ${rowNum}`;
          EW_trace('FIX_HIT_DATES', `${ticker}: Cleared Hit_Date (strike never hit)`);
        }
        continue;
      }
      
      // Check if correction is needed
      // Hit_Date should be the day number (0-5)
      const expectedValue = firstHitDay.toString();
      
      if (currentHitDate !== expectedValue) {
        sheet.getRange(rowNum, hdrMap.hitDateCol).setValue(expectedValue);
        correctedCount++;
        
        const ticker = rowData[hdrMap.tickerCol - 1] || `Row ${rowNum}`;
        EW_trace('FIX_HIT_DATES', 
          `${ticker}: Updated Hit_Date from '${currentHitDate || 'empty'}' to '${expectedValue}' ` +
          `(first profitable on day ${firstHitDay})`);
      }
      
    } catch (e) {
      errors.push(`Row ${rowNum}: ${e.message}`);
      EW_trace('FIX_HIT_DATES', `Error processing row ${rowNum}: ${e.message}`);
    }
  }
  
  return {
    processed: processedCount,
    corrected: correctedCount,
    errors: errors
  };
}

/**
 * Fix Hit_Date for selected rows only
 * Sets Hit_Date to the day number (0-5) when strike was first hit
 */
function EW_fixHitDatesForSelected() {
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
  
  // Get header mapping
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Check required columns
  if (!hdrMap.hitDateCol || !hdrMap.strikeHitCol) {
    EW_safeAlert('Missing Columns', 'Required columns (Hit_Date, Strike_Hit) not found');
    return;
  }
  
  // Process selected rows
  const dataRange = sheet.getRange(startRow, 1, numRows, sheet.getLastColumn());
  const data = dataRange.getValues();
  
  let correctedCount = 0;
  let processedCount = 0;
  
  for (let i = 0; i < data.length; i++) {
    const rowNum = startRow + i;
    const rowData = data[i];
    
    processedCount++;
    
    // Get current values
    const currentHitDate = rowData[hdrMap.hitDateCol - 1];
    const strikeHitArray = rowData[hdrMap.strikeHitCol - 1];
    
    if (!strikeHitArray) continue;
    
    // Parse Strike_Hit array
    let strikeHitParsed;
    try {
      strikeHitParsed = typeof strikeHitArray === 'string' ? JSON.parse(strikeHitArray) : strikeHitArray;
    } catch (e) {
      continue;
    }
    
    // Find first day with positive value
    let firstHitDay = -1;
    for (let day = 0; day < strikeHitParsed.length && day <= 5; day++) {
      const value = strikeHitParsed[day];
      if (value !== null && parseFloat(value) > 0) {
        firstHitDay = day;
        break;
      }
    }
    
    // Update Hit_Date if needed
    if (firstHitDay === -1) {
      // Clear if strike was never hit
      if (currentHitDate !== '' && currentHitDate !== null) {
        sheet.getRange(rowNum, hdrMap.hitDateCol).setValue('');
        correctedCount++;
      }
    } else {
      // Set to day number
      const expectedValue = firstHitDay.toString();
      if (currentHitDate !== expectedValue) {
        sheet.getRange(rowNum, hdrMap.hitDateCol).setValue(expectedValue);
        correctedCount++;
      }
    }
  }
  
  const msg = `Processing complete.\n` +
    `Processed: ${processedCount} rows\n` +
    `Corrected: ${correctedCount} rows\n\n` +
    `Hit_Date now shows day number (0-5) when position first became profitable`;
  
  EW_safeAlert('Hit_Date Correction Complete', msg);
}

// ========== FIX STRIKE_HIT VALUES ==========

/**
 * Fix Strike_Hit values that are showing incorrect data
 * This addresses the issue where Strike_Hit may be showing Min_Unfavorable values
 * or incorrect calculations for below-strike prices
 */
function EW_fixStrikeHitValues() {
  const sheet = SpreadsheetApp.getActiveSheet();
  if (!sheet) return;
  
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return;
  
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Check required columns
  if (!hdrMap.strikeHitCol || !hdrMap.ohlcVolumeCol || !hdrMap.strategyCol || !hdrMap.strikeCol) {
    EW_safeAlert('Missing Columns', 'Required columns not found (Strike_Hit, OHLC_Volume, Strategy, Strike)');
    return;
  }
  
  const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  
  let fixedCount = 0;
  const updates = [];
  
  data.forEach((row, index) => {
    const rowNum = index + 2;
    const strategy = row[hdrMap.strategyCol - 1];
    const strike = parseFloat(row[hdrMap.strikeCol - 1]);
    const ohlcData = row[hdrMap.ohlcVolumeCol - 1];
    const currentStrikeHit = row[hdrMap.strikeHitCol - 1];
    const ticker = row[hdrMap.tickerCol - 1] || 'Unknown';
    
    if (!strategy || !strike || !ohlcData) return;
    
    try {
      const ohlcArray = JSON.parse(ohlcData);
      const strategyType = EW_getStrategyType(strategy);
      const newStrikeHit = [];
      
      ohlcArray.forEach(dayData => {
        if (dayData && dayData.h && dayData.l) {
          const high = parseFloat(dayData.h);
          const low = parseFloat(dayData.l);
          
          let percentMove = null;
          
          if (strategyType === 'bullish') {
            // For bullish: (high - strike) / strike
            // Negative when high < strike, positive when high > strike
            percentMove = ((high - strike) / strike).toFixed(6);
          } else if (strategyType === 'bearish') {
            // For bearish: (strike - low) / strike
            // Negative when low > strike, positive when low < strike
            percentMove = ((strike - low) / strike).toFixed(6);
          } else {
            // For neutral: use the extreme that gives larger absolute move
            const upMove = (high - strike) / strike;
            const downMove = (strike - low) / strike;
            percentMove = Math.abs(upMove) > Math.abs(downMove) ? upMove.toFixed(6) : downMove.toFixed(6);
          }
          
          newStrikeHit.push(percentMove);
        } else {
          newStrikeHit.push(null);
        }
      });
      
      // Limit to 6 days
      while (newStrikeHit.length > 6) newStrikeHit.pop();
      
      // Check if update is needed
      let needsUpdate = false;
      try {
        const currentArray = JSON.parse(currentStrikeHit);
        // Check if values are different
        if (currentArray.length !== newStrikeHit.length) {
          needsUpdate = true;
        } else {
          for (let i = 0; i < newStrikeHit.length; i++) {
            if (currentArray[i] !== newStrikeHit[i]) {
              // Allow for small rounding differences
              const current = parseFloat(currentArray[i]);
              const newVal = parseFloat(newStrikeHit[i]);
              if (isNaN(current) && isNaN(newVal)) continue;
              if (Math.abs(current - newVal) > 0.00001) {
                needsUpdate = true;
                EW_trace('FIX_STRIKE_HIT', `${ticker} Day ${i}: Current=${currentArray[i]}, New=${newStrikeHit[i]}`);
                break;
              }
            }
          }
        }
      } catch (e) {
        needsUpdate = true;
      }
      
      if (needsUpdate) {
        updates.push({
          row: rowNum,
          col: hdrMap.strikeHitCol,
          value: JSON.stringify(newStrikeHit),
          ticker: ticker,
          strike: strike,
          strategy: strategyType
        });
        fixedCount++;
      }
      
    } catch (e) {
      EW_trace('FIX_STRIKE_HIT', `Error processing row ${rowNum} (${ticker}): ${e.toString()}`);
    }
  });
  
  // Apply updates in batch
  if (updates.length > 0) {
    updates.forEach(update => {
      sheet.getRange(update.row, update.col).setValue(update.value);
      EW_trace('FIX_STRIKE_HIT', `Fixed ${update.ticker} (${update.strategy}, strike=${update.strike})`);
    });
    
    SpreadsheetApp.flush();
    
    EW_trace('FIX_STRIKE_HIT', `Fixed ${fixedCount} Strike_Hit values`)
    EW_safeAlert('Strike_Hit Fixed', `Corrected ${fixedCount} Strike_Hit values that were showing incorrect data`);
  } else {
    EW_safeAlert('No Issues Found', 'All Strike_Hit values appear to be correct');
  }
}

