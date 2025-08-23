/**
 * Historical Backfill - Functions to populate tracking data for historical positions
 * Uses Yahoo Finance historical data to retroactively fill tracking columns
 * Only processes positions with Days_To_Exp < 0 (expired positions)
 */

/**
 * Main function to backfill historical tracking data for all sheets
 * This analyzes historical prices from run date to expiration/today
 */
function EW_backfillHistoricalTracking() {
  EW_trace('BACKFILL', 'Starting historical tracking backfill', true);
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  let totalBackfilled = 0;
  let errors = [];
  
  for (const strategy of strategies) {
    try {
      const backfilled = EW_backfillStrategyTracking(ss, strategy);
      if (backfilled > 0) {
        totalBackfilled += backfilled;
        EW_trace('BACKFILL', `Backfilled ${backfilled} positions in ${strategy}`);
      }
    } catch (e) {
      errors.push(`${strategy}: ${e.message}`);
      EW_trace('BACKFILL', `Error backfilling ${strategy}: ${e.message}`, true);
    }
  }
  
  const msg = `Historical backfill complete. Processed ${totalBackfilled} positions across ${strategies.length} strategies.` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');
  
  EW_trace('BACKFILL', msg, true);
  if (EW_isSpreadsheetEnvironment()) {
    EW_safeAlert('Historical Backfill Complete', msg);
  }
}

/**
 * Backfill historical tracking data for a specific strategy
 * @param {SpreadsheetApp.Spreadsheet} ss - The spreadsheet
 * @param {string} strategyName - Name of the strategy/sheet
 * @returns {number} Number of positions processed
 */
function EW_backfillStrategyTracking(ss, strategyName) {
  const sheet = ss.getSheetByName(strategyName);
  if (!sheet || sheet.getLastRow() < 2) {
    return 0;
  }
  
  // Get header map
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Check required columns
  const requiredCols = ['tickerCol', 'runDateCol', 'strikeCol', 'daysToExpCol'];
  for (const col of requiredCols) {
    if (!hdrMap[col]) {
      EW_trace('BACKFILL', `${strategyName}: Missing required column ${col}`);
      return 0;
    }
  }
  
  // Get all data
  const lastRow = sheet.getLastRow();
  const dataRange = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
  const data = dataRange.getValues();
  
  let processedCount = 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  
  // Process each row
  data.forEach((row, rowIndex) => {
    try {
      const ticker = row[hdrMap.tickerCol - 1];
      const runDateStr = row[hdrMap.runDateCol - 1];
      const strike = parseFloat(row[hdrMap.strikeCol - 1]) || 0;
      const expDateStr = hdrMap.expDateCol ? row[hdrMap.expDateCol - 1] : null;
      const daysToExp = parseFloat(row[hdrMap.daysToExpCol - 1]) || 0;
      
      if (!ticker || !runDateStr || !strike) return;
      
      // ONLY process expired positions (Days_To_Exp < 0)
      if (daysToExp >= 0) {
        return; // Skip positions that haven't expired yet
      }
      
      // Parse dates
      const runDate = new Date(runDateStr);
      runDate.setHours(0, 0, 0, 0);
      const expDate = expDateStr ? new Date(expDateStr) : null;
      if (expDate) expDate.setHours(0, 0, 0, 0);
      
      // Determine end date (expiration or today, whichever is earlier)
      const endDate = expDate && expDate < today ? expDate : today;
      
      // Skip if run date is in the future or invalid
      if (runDate > today || runDate > endDate) return;
      
      EW_trace('BACKFILL', `Processing expired position: ${ticker} from ${runDate.toISOString().split('T')[0]} to ${endDate.toISOString().split('T')[0]}`);
      
      // Get historical price data using Yahoo Finance
      const historicalData = EW_getYahooHistoricalRange(ticker, runDate, endDate);
      if (!historicalData || historicalData.length === 0) {
        EW_trace('BACKFILL', `No historical data for ${ticker}`);
        return;
      }
      
      // Analyze historical data
      const analysis = EW_analyzeHistoricalData(strategyName, strike, historicalData, runDate);
      
      // Update tracking columns with historical analysis
      let updated = false;
      
      // Update Strike_Hit column based on analysis
      if (hdrMap.strikeHitCol) {
        const strikeHitStatus = analysis.firstHitDate ? 'HIT' : 'NO';
        dataRange.getCell(rowIndex + 1, hdrMap.strikeHitCol).setValue(strikeHitStatus);
        updated = true;
      }
      
      // Update Hit_Date
      if (hdrMap.hitDateCol && analysis.firstHitDate) {
        const existing = row[hdrMap.hitDateCol - 1];
        if (!existing) {
          dataRange.getCell(rowIndex + 1, hdrMap.hitDateCol).setValue(analysis.firstHitDate);
          updated = true;
        }
      }
      
      // Update Day1_Check through Day5_Check
      const dayChecks = [
        { col: hdrMap.day1CheckCol, day: 1, value: analysis.day1Hit },
        { col: hdrMap.day2CheckCol, day: 2, value: analysis.day2Hit },
        { col: hdrMap.day3CheckCol, day: 3, value: analysis.day3Hit },
        { col: hdrMap.day5CheckCol, day: 5, value: analysis.day5Hit }
      ];
      
      for (const check of dayChecks) {
        if (check.col && check.value !== null) {
          const existing = row[check.col - 1];
          if (!existing) {
            dataRange.getCell(rowIndex + 1, check.col).setValue(check.value);
            updated = true;
          }
        }
      }
      
      // Update Max_Favorable
      if (hdrMap.maxFavorableCol && analysis.maxFavorable !== null) {
        const existing = row[hdrMap.maxFavorableCol - 1];
        if (!existing) {
          dataRange.getCell(rowIndex + 1, hdrMap.maxFavorableCol).setValue(analysis.maxFavorable);
          updated = true;
        }
      }
      
      // Update Min_Unfavorable
      if (hdrMap.minUnfavorableCol && analysis.minUnfavorable !== null) {
        const existing = row[hdrMap.minUnfavorableCol - 1];
        if (!existing) {
          dataRange.getCell(rowIndex + 1, hdrMap.minUnfavorableCol).setValue(analysis.minUnfavorable);
          updated = true;
        }
      }
      
      // Update Exp_Result if expired
      if (hdrMap.expResultCol && expDate && expDate <= today && analysis.expResult) {
        const existing = row[hdrMap.expResultCol - 1];
        if (!existing) {
          dataRange.getCell(rowIndex + 1, hdrMap.expResultCol).setValue(analysis.expResult);
          updated = true;
        }
      }
      
      // Update Peak_Profit_Date
      if (hdrMap.peakProfitDateCol && analysis.peakProfitDate) {
        const existing = row[hdrMap.peakProfitDateCol - 1];
        if (!existing) {
          dataRange.getCell(rowIndex + 1, hdrMap.peakProfitDateCol).setValue(analysis.peakProfitDate);
          updated = true;
        }
      }
      
      if (updated) {
        processedCount++;
        
        // Update Historical_High and Historical_Low if needed
        if (hdrMap.historicalHighCol) {
          const existing = row[hdrMap.historicalHighCol - 1];
          if (!existing || existing < analysis.historicalHigh) {
            dataRange.getCell(rowIndex + 1, hdrMap.historicalHighCol).setValue(analysis.historicalHigh);
          }
        }
        
        if (hdrMap.historicalLowCol) {
          const existing = row[hdrMap.historicalLowCol - 1];
          if (!existing || existing > analysis.historicalLow) {
            dataRange.getCell(rowIndex + 1, hdrMap.historicalLowCol).setValue(analysis.historicalLow);
          }
        }
      }
      
    } catch (e) {
      EW_trace('BACKFILL', `Error processing row ${rowIndex + 2} in ${strategyName}: ${e.message}`);
    }
  });
  
  // Force save
  if (processedCount > 0) {
    SpreadsheetApp.flush();
  }
  
  return processedCount;
}

// Note: Historical price fetching has been moved to 10_YahooHistorical.js
// using EW_getYahooHistoricalRange() function

/**
 * Analyze historical price data to determine tracking values
 * @param {string} strategy - Strategy name
 * @param {number} strike - Strike price
 * @param {Array} historicalData - Array of price data
 * @param {Date} runDate - Entry date
 * @returns {Object} Analysis results
 */
function EW_analyzeHistoricalData(strategy, strike, historicalData, runDate) {
  const analysis = {
    firstHitDate: null,
    day1Hit: null,
    day2Hit: null,
    day3Hit: null,
    day5Hit: null,
    maxFavorable: null,
    minUnfavorable: null,
    expResult: null,
    peakProfitDate: null,
    historicalHigh: 0,
    historicalLow: Infinity
  };
  
  if (!historicalData || historicalData.length === 0) return analysis;
  
  const strategyUpper = strategy.toUpperCase();
  const isBullish = strategyUpper.includes('LONG CALL') || strategyUpper.includes('BULL');
  const isBearish = strategyUpper.includes('LONG PUT') || strategyUpper.includes('BEAR');
  
  let maxProfit = -Infinity;
  let maxLoss = Infinity;
  let hitDetected = false;
  
  historicalData.forEach((dayData, index) => {
    const daysSinceEntry = Math.floor((dayData.date - runDate) / (1000 * 60 * 60 * 24));
    
    // Track historical high/low
    analysis.historicalHigh = Math.max(analysis.historicalHigh, dayData.high);
    analysis.historicalLow = Math.min(analysis.historicalLow, dayData.low);
    
    // Check if strike was hit
    let dayHit = false;
    if (isBullish) {
      dayHit = dayData.high >= strike;
    } else if (isBearish) {
      dayHit = dayData.low <= strike;
    }
    
    // Record first hit date
    if (dayHit && !hitDetected) {
      analysis.firstHitDate = dayData.date.toISOString().split('T')[0];
      hitDetected = true;
    }
    
    // Check specific day milestones
    if (daysSinceEntry === 1) {
      analysis.day1Hit = dayHit ? 'HIT' : 'NO';
    } else if (daysSinceEntry === 2) {
      analysis.day2Hit = dayHit ? 'HIT' : 'NO';
    } else if (daysSinceEntry === 3) {
      analysis.day3Hit = dayHit ? 'HIT' : 'NO';
    } else if (daysSinceEntry === 5) {
      analysis.day5Hit = dayHit ? 'HIT' : 'NO';
    }
    
    // Calculate profit/loss for the day
    let dayProfit = 0;
    if (isBullish) {
      dayProfit = ((dayData.high - strike) / strike) * 100;
      const dayLoss = ((strike - dayData.low) / strike) * 100;
      maxLoss = Math.min(maxLoss, -dayLoss);
    } else if (isBearish) {
      dayProfit = ((strike - dayData.low) / strike) * 100;
      const dayLoss = ((dayData.high - strike) / strike) * 100;
      maxLoss = Math.min(maxLoss, -dayLoss);
    }
    
    // Track peak profit
    if (dayProfit > maxProfit) {
      maxProfit = dayProfit;
      analysis.peakProfitDate = dayData.date.toISOString().split('T')[0];
    }
  });
  
  // Set max favorable and min unfavorable
  analysis.maxFavorable = maxProfit > 0 ? maxProfit.toFixed(2) : '0.00';
  analysis.minUnfavorable = maxLoss < 0 ? Math.abs(maxLoss).toFixed(2) : '0.00';
  
  // Set expiration result (last day's status)
  if (historicalData.length > 0) {
    const lastDay = historicalData[historicalData.length - 1];
    if (isBullish) {
      analysis.expResult = lastDay.close >= strike ? 'HIT' : 'NO';
    } else if (isBearish) {
      analysis.expResult = lastDay.close <= strike ? 'HIT' : 'NO';
    }
  }
  
  return analysis;
}

/**
 * Backfill tracking for a single position (can be called from cell)
 * @param {string} ticker - Ticker symbol
 * @param {string} strategy - Strategy name
 * @param {number} strike - Strike price
 * @param {string} runDate - Run date as string
 * @param {string} expDate - Expiration date as string (optional)
 * @returns {Object} Tracking data object
 */
function EW_backfillSinglePosition(ticker, strategy, strike, runDate, expDate) {
  const startDate = new Date(runDate);
  const endDate = expDate ? new Date(expDate) : new Date();
  
  const historicalData = EW_getHistoricalPrices(ticker, startDate, endDate);
  const analysis = EW_analyzeHistoricalData(strategy, strike, historicalData, startDate);
  
  return analysis;
}

/**
 * Menu function to backfill selected rows only
 */
function EW_backfillSelectedRows() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const range = sheet.getActiveRange();
  
  if (!range) {
    EW_safeAlert('No Selection', 'Please select rows to backfill');
    return;
  }
  
  const startRow = range.getRow();
  const numRows = range.getNumRows();
  
  // Skip if header row is selected
  if (startRow === 1) {
    EW_safeAlert('Invalid Selection', 'Please select data rows, not the header row');
    return;
  }
  
  EW_trace('BACKFILL', `Backfilling ${numRows} selected rows starting at row ${startRow}`, true);
  
  // Get headers
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Process selected rows
  let processedCount = 0;
  for (let i = 0; i < numRows; i++) {
    const rowNum = startRow + i;
    const rowData = sheet.getRange(rowNum, 1, 1, sheet.getLastColumn()).getValues()[0];
    
    // Get required data
    const ticker = hdrMap.tickerCol ? rowData[hdrMap.tickerCol - 1] : null;
    const runDate = hdrMap.runDateCol ? rowData[hdrMap.runDateCol - 1] : null;
    const strike = hdrMap.strikeCol ? parseFloat(rowData[hdrMap.strikeCol - 1]) : null;
    const expDate = hdrMap.expDateCol ? rowData[hdrMap.expDateCol - 1] : null;
    
    if (ticker && runDate && strike) {
      const analysis = EW_backfillSinglePosition(ticker, sheet.getName(), strike, runDate, expDate);
      
      // Update cells
      if (hdrMap.hitDateCol && analysis.firstHitDate) {
        sheet.getRange(rowNum, hdrMap.hitDateCol).setValue(analysis.firstHitDate);
      }
      if (hdrMap.day1CheckCol && analysis.day1Hit) {
        sheet.getRange(rowNum, hdrMap.day1CheckCol).setValue(analysis.day1Hit);
      }
      if (hdrMap.day2CheckCol && analysis.day2Hit) {
        sheet.getRange(rowNum, hdrMap.day2CheckCol).setValue(analysis.day2Hit);
      }
      if (hdrMap.day5CheckCol && analysis.day5Hit) {
        sheet.getRange(rowNum, hdrMap.day5CheckCol).setValue(analysis.day5Hit);
      }
      if (hdrMap.maxFavorableCol && analysis.maxFavorable) {
        sheet.getRange(rowNum, hdrMap.maxFavorableCol).setValue(analysis.maxFavorable);
      }
      if (hdrMap.minUnfavorableCol && analysis.minUnfavorable) {
        sheet.getRange(rowNum, hdrMap.minUnfavorableCol).setValue(analysis.minUnfavorable);
      }
      
      processedCount++;
    }
  }
  
  SpreadsheetApp.flush();
  EW_safeAlert('Backfill Complete', `Processed ${processedCount} of ${numRows} selected rows`);
}