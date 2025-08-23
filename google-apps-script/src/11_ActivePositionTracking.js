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
  
  // Create daily API report after tracking update
  try {
    EW_createDailyApiReport();
    console.log('ACTIVE TRACKING: Daily API report created');
  } catch (error) {
    console.error(`ACTIVE TRACKING: Failed to create API report: ${error.message}`);
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
    const strike = hdrMap.strikeCol ? parseFloat(row[hdrMap.strikeCol - 1]) || 0 : 0;
    const longStrike = hdrMap.longStrikeCol ? parseFloat(row[hdrMap.longStrikeCol - 1]) || 0 : 0;
    const shortStrike = hdrMap.shortStrikeCol ? parseFloat(row[hdrMap.shortStrikeCol - 1]) || 0 : 0;
    const daysToExp = parseFloat(row[hdrMap.daysToExpCol - 1]) || 0;
    const currentStrikeHit = row[hdrMap.strikeHitCol - 1];
    
    // Check if position has valid strike data
    const hasValidStrike = strike || (longStrike && shortStrike);
    
    if (!ticker || !runDateStr || !hasValidStrike) return;
    
    // ONLY process active positions (Days_To_Exp > 0) that haven't hit yet
    if (daysToExp > 0 && currentStrikeHit !== 'HIT') {
      const runDate = new Date(runDateStr);
      runDate.setHours(0, 0, 0, 0);
      
      positionsToCheck.push({
        rowIndex: rowIndex,
        ticker: ticker,
        strike: strike,
        longStrike: longStrike,
        shortStrike: shortStrike,
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
        
        // If hit, also update Hit_Date and indicators
        if (result.hit) {
          // Update Hit_Date if column exists
          if (hdrMap.hitDateCol) {
            const existingHitDate = data[result.rowIndex][hdrMap.hitDateCol - 1];
            if (!existingHitDate) {
              const hitDateStr = result.hitDate.toISOString().split('T')[0];
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitDateCol).setValue(hitDateStr);
            }
          }
          
          // Update indicator values at strike hit
          if (result.indicators) {
            const ind = result.indicators;
            
            if (hdrMap.hitRSICol && ind.rsi !== null) {
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitRSICol).setValue(ind.rsi.toFixed(2));
            }
            if (hdrMap.hitSMA20Col && ind.sma20 !== null) {
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitSMA20Col).setValue(ind.sma20.toFixed(2));
            }
            if (hdrMap.hitSMA50Col && ind.sma50 !== null) {
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitSMA50Col).setValue(ind.sma50.toFixed(2));
            }
            if (hdrMap.hitEMA9Col && ind.ema9 !== null) {
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitEMA9Col).setValue(ind.ema9.toFixed(2));
            }
            if (hdrMap.hitEMA21Col && ind.ema21 !== null) {
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitEMA21Col).setValue(ind.ema21.toFixed(2));
            }
            if (hdrMap.hitVWAPCol && ind.vwap !== null) {
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitVWAPCol).setValue(ind.vwap.toFixed(2));
            }
            if (hdrMap.hitRVOLCol && ind.rvol !== null) {
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitRVOLCol).setValue(ind.rvol.toFixed(2));
            }
            if (hdrMap.hitATRCol && ind.atr !== null) {
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitATRCol).setValue(ind.atr.toFixed(4));
            }
            if (hdrMap.hitPriceVsSMA20Col && ind.priceVsSMA20 !== null) {
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitPriceVsSMA20Col).setValue(ind.priceVsSMA20.toFixed(2) + '%');
            }
            if (hdrMap.hitPriceVsVWAPCol && ind.priceVsVWAP !== null) {
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitPriceVsVWAPCol).setValue(ind.priceVsVWAP.toFixed(2) + '%');
            }
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