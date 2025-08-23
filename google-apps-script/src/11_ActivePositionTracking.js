/**
 * Active Position Tracking - Functions to update Strike_Hit for active positions
 * Uses Yahoo Finance data to check if strikes have been hit for positions with Days_To_Exp > 0
 */

/**
 * Update Strike_Hit column for all active positions across all sheets
 * Only processes positions with Days_To_Exp > 0
 * Runs at 5 PM ET to capture full day's 1-minute interval data
 */
function EW_updateActiveStrikeHits() {
  const startTime = new Date();
  console.log(`ACTIVE TRACKING: Started at ${startTime.toISOString()}`);
  Logger.log(`ACTIVE TRACKING: Strike_Hit update started at ${startTime.toISOString()}`);
  EW_trace('ACTIVE_TRACKING', 'Starting Strike_Hit updates for active positions', true);
  
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  let totalUpdated = 0;
  let totalChecked = 0;
  let errors = [];
  
  for (const strategy of strategies) {
    try {
      console.log(`ACTIVE TRACKING: Processing ${strategy} sheet...`);
      const result = EW_updateStrategyActiveStrikes(ss, strategy);
      totalChecked += result.checked;
      totalUpdated += result.updated;
      
      if (result.updated > 0) {
        EW_trace('ACTIVE_TRACKING', `Updated ${result.updated} of ${result.checked} active positions in ${strategy}`);
        console.log(`ACTIVE TRACKING: ${strategy} - Updated ${result.updated}/${result.checked} positions`);
      } else if (result.checked > 0) {
        console.log(`ACTIVE TRACKING: ${strategy} - Checked ${result.checked} positions, no updates needed`);
      }
    } catch (e) {
      errors.push(`${strategy}: ${e.message}`);
      EW_trace('ACTIVE_TRACKING', `Error updating ${strategy}: ${e.message}`, true);
      console.error(`ACTIVE TRACKING ERROR: ${strategy} - ${e.message}`);
    }
  }
  
  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);
  
  const msg = `Active position update complete.\n` +
    `Checked: ${totalChecked} positions\n` +
    `Updated: ${totalUpdated} positions\n` +
    `Strategies: ${strategies.length}\n` +
    `Duration: ${duration} seconds` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');
  
  console.log(`ACTIVE TRACKING: Completed in ${duration} seconds`);
  Logger.log(`ACTIVE TRACKING: Completed - Checked ${totalChecked}, Updated ${totalUpdated}, Duration ${duration}s`);
  
  EW_trace('ACTIVE_TRACKING', msg, true);
  if (EW_isSpreadsheetEnvironment()) {
    EW_safeAlert('Active Position Update Complete', msg);
  }
  
  return { checked: totalChecked, updated: totalUpdated, duration: duration };
}

/**
 * Update Strike_Hit for active positions in a specific strategy sheet
 * @param {SpreadsheetApp.Spreadsheet} ss - The spreadsheet
 * @param {string} strategyName - Name of the strategy/sheet
 * @returns {number} Number of positions updated
 */
function EW_updateStrategyActiveStrikes(ss, strategyName) {
  const sheet = ss.getSheetByName(strategyName);
  if (!sheet || sheet.getLastRow() < 2) {
    return 0;
  }
  
  // Get header map
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Check required columns
  const requiredCols = ['tickerCol', 'runDateCol', 'strikeCol', 'daysToExpCol', 'strikeHitCol'];
  for (const col of requiredCols) {
    if (!hdrMap[col]) {
      EW_trace('ACTIVE_TRACKING', `${strategyName}: Missing required column ${col}`);
      return 0;
    }
  }
  
  // Get all data
  const lastRow = sheet.getLastRow();
  const dataRange = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
  const data = dataRange.getValues();
  
  let updatedCount = 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  
  // Batch positions for efficiency
  const positionsToCheck = [];
  
  // First pass: collect positions that need checking
  data.forEach((row, rowIndex) => {
    const ticker = row[hdrMap.tickerCol - 1];
    const runDateStr = row[hdrMap.runDateCol - 1];
    const strike = parseFloat(row[hdrMap.strikeCol - 1]) || 0;
    const daysToExp = parseFloat(row[hdrMap.daysToExpCol - 1]) || 0;
    const currentStrikeHit = row[hdrMap.strikeHitCol - 1];
    
    if (!ticker || !runDateStr || !strike) return;
    
    // ONLY process active positions (Days_To_Exp > 0) that haven't hit yet
    if (daysToExp > 0 && currentStrikeHit !== 'HIT') {
      const runDate = new Date(runDateStr);
      runDate.setHours(0, 0, 0, 0);
      
      positionsToCheck.push({
        rowIndex: rowIndex,
        ticker: ticker,
        strike: strike,
        strategy: strategyName,
        startDate: runDate,
        endDate: today
      });
    }
  });
  
  if (positionsToCheck.length === 0) {
    return { checked: 0, updated: 0 };
  }
  
  console.log(`ACTIVE TRACKING: ${strategyName} - Checking ${positionsToCheck.length} active positions`);
  EW_trace('ACTIVE_TRACKING', `Checking ${positionsToCheck.length} active positions in ${strategyName}`);
  
  // Batch check strike hits
  const results = EW_batchCheckStrikeHits(positionsToCheck);
  
  // Update cells with results
  results.forEach(result => {
    if (!result.error) {
      const newStatus = result.hit ? 'HIT' : 'NO';
      const currentStatus = data[result.rowIndex][hdrMap.strikeHitCol - 1];
      
      // Log if fallback was used
      if (result.fallbackUsed) {
        console.log(`ACTIVE TRACKING: ${strategyName} - ${result.ticker} used ${result.fallbackUsed} interval (fallback)`);
        Logger.log(`ACTIVE TRACKING FALLBACK: ${strategyName}/${result.ticker} used ${result.fallbackUsed} interval`);
      }
      
      // Only update if status changed
      if (currentStatus !== newStatus) {
        dataRange.getCell(result.rowIndex + 1, hdrMap.strikeHitCol).setValue(newStatus);
        
        // If hit, also update Hit_Date
        if (result.hit && hdrMap.hitDateCol) {
          const existingHitDate = data[result.rowIndex][hdrMap.hitDateCol - 1];
          if (!existingHitDate) {
            const hitDateStr = result.hitDate.toISOString().split('T')[0];
            dataRange.getCell(result.rowIndex + 1, hdrMap.hitDateCol).setValue(hitDateStr);
          }
        }
        
        updatedCount++;
        console.log(`ACTIVE TRACKING: ${strategyName} - Updated ${result.ticker} to ${newStatus}`);
      }
    } else {
      console.error(`ACTIVE TRACKING ERROR: ${strategyName} - ${result.ticker}: ${result.error}`);
    }
  });
  
  // Force save
  if (updatedCount > 0) {
    SpreadsheetApp.flush();
  }
  
  return { checked: positionsToCheck.length, updated: updatedCount };
}

// Note: Trigger functions have been moved to 03_Triggers.js

/**
 * Test function to check a single position
 */
function EW_testActivePositionCheck() {
  const ticker = 'IWM';
  const strike = 235;
  const strategy = 'Bull Spreads';
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - 7);
  const endDate = new Date();
  
  console.log(`Testing ${ticker} @ ${strike} for ${strategy}`);
  
  const result = EW_checkStrikeHitYahoo(ticker, strike, strategy, startDate, endDate);
  console.log('Result:', result);
  
  return result;
}