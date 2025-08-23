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
  
  // Verify column order for Day5_Check and Exp_Result
  if (hdrMap.day5CheckCol && hdrMap.expResultCol) {
    const day5Header = headers[hdrMap.day5CheckCol - 1];
    const expResultHeader = headers[hdrMap.expResultCol - 1];
    EW_trace('BACKFILL', `Column verification - Day5_Check: col ${hdrMap.day5CheckCol}='${day5Header}', Exp_Result: col ${hdrMap.expResultCol}='${expResultHeader}'`);
  }
  
  // Check required columns - handle spreads differently
  const isSpread = strategyName.toUpperCase().includes('SPREAD');
  const strikeColumn = isSpread ? 'longStrikeCol' : 'strikeCol';
  
  const requiredCols = ['tickerCol', 'runDateCol', strikeColumn, 'daysToExpCol'];
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
      // For spreads, use longStrike; otherwise use strike
      const strikeCol = isSpread ? hdrMap.longStrikeCol : hdrMap.strikeCol;
      const strike = parseFloat(row[strikeCol - 1]) || 0;
      const expDateStr = hdrMap.expDateCol ? row[hdrMap.expDateCol - 1] : null;
      const daysToExp = parseFloat(row[hdrMap.daysToExpCol - 1]) || 0;
      
      if (!ticker || !runDateStr || !strike) return;
      
      // ONLY process expired positions (Days_To_Exp < 0)
      if (daysToExp >= 0) {
        return; // Skip positions that haven't expired yet
      }
      
      // Skip if already has tracking data (check key tracking columns)
      const hasStrikeHit = hdrMap.strikeHitCol && row[hdrMap.strikeHitCol - 1];
      const hasDay1Check = hdrMap.day1CheckCol && row[hdrMap.day1CheckCol - 1];
      const hasLastUpdate = hdrMap.lastUpdateCol && row[hdrMap.lastUpdateCol - 1];
      
      if (hasStrikeHit && hasDay1Check && hasLastUpdate) {
        EW_trace('BACKFILL', `Skipping ${ticker} - already has tracking data`);
        return; // Skip if already processed
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
      
      // Get short strike for spreads
      const shortStrike = isSpread && hdrMap.shortStrikeCol ? 
        parseFloat(row[hdrMap.shortStrikeCol - 1]) || null : null;
      
      // Analyze historical data
      const analysis = EW_analyzeHistoricalData(strategyName, strike, historicalData, runDate, shortStrike);
      
      // Update tracking columns with historical analysis
      let updated = false;
      
      // Update Strike_Hit column with actual price or 'None'
      if (hdrMap.strikeHitCol) {
        const strikeHitValue = analysis.firstHitPrice ? analysis.firstHitPrice.toFixed(2) : 'None';
        dataRange.getCell(rowIndex + 1, hdrMap.strikeHitCol).setValue(strikeHitValue);
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
        { col: hdrMap.day0CheckCol, day: 0, value: analysis.day0Hit },
        { col: hdrMap.day1CheckCol, day: 1, value: analysis.day1Hit },
        { col: hdrMap.day2CheckCol, day: 2, value: analysis.day2Hit },
        { col: hdrMap.day3CheckCol, day: 3, value: analysis.day3Hit },
        { col: hdrMap.day4CheckCol, day: 4, value: analysis.day4Hit },
        { col: hdrMap.day5CheckCol, day: 5, value: analysis.day5Hit }
      ];
      
      for (const check of dayChecks) {
        if (check.col && check.value !== null) {
          const existing = row[check.col - 1];
          if (!existing) {
            // Add debug logging for Day5_Check specifically
            if (check.day === 5) {
              EW_trace('BACKFILL', `Setting Day5_Check: col=${check.col}, value=${check.value}, rowIndex=${rowIndex + 1}`);
            }
            // Ensure clean value writing
            const cleanValue = String(check.value).trim();
            dataRange.getCell(rowIndex + 1, check.col).setValue(cleanValue);
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
          // Debug log to check column alignment
          EW_trace('BACKFILL', `Setting Exp_Result: col=${hdrMap.expResultCol}, value=${analysis.expResult}, day5Col=${hdrMap.day5CheckCol}`);
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
 * Count trading days between two dates (excluding weekends)
 * @param {Date} startDate - Start date
 * @param {Date} endDate - End date
 * @returns {number} Number of trading days
 */
function EW_countTradingDays(startDate, endDate) {
  let count = 0;
  const current = new Date(startDate);
  current.setHours(0, 0, 0, 0);
  const end = new Date(endDate);
  end.setHours(0, 0, 0, 0);
  
  while (current <= end) {
    const dayOfWeek = current.getDay();
    if (dayOfWeek !== 0 && dayOfWeek !== 6) { // Not Sunday or Saturday
      count++;
    }
    current.setDate(current.getDate() + 1);
  }
  
  return count;
}

/**
 * Analyze historical price data to determine tracking values
 * @param {string} strategy - Strategy name
 * @param {number} strike - Strike price (or longStrike for spreads)
 * @param {Array} historicalData - Array of price data
 * @param {Date} runDate - Entry date
 * @param {number} shortStrike - Short strike for spread strategies (optional)
 * @returns {Object} Analysis results
 */
function EW_analyzeHistoricalData(strategy, strike, historicalData, runDate, shortStrike = null) {
  const analysis = {
    firstHitDate: null,
    firstHitPrice: null,
    day0Hit: null,
    day1Hit: null,
    day2Hit: null,
    day3Hit: null,
    day4Hit: null,
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
  const isSpread = strategyUpper.includes('SPREAD');
  const isBullSpread = strategyUpper.includes('BULL SPREAD');
  const isBearSpread = strategyUpper.includes('BEAR SPREAD');
  const isBullish = strategyUpper.includes('LONG CALL') || (strategyUpper.includes('BULL') && !isSpread);
  const isBearish = strategyUpper.includes('LONG PUT') || (strategyUpper.includes('BEAR') && !isSpread);
  
  let maxProfit = -Infinity;
  let maxLoss = Infinity;
  let hitDetected = false;
  
  // Find the index where our run date data starts
  let runDateIndex = -1;
  const runDateStr = runDate.toISOString().split('T')[0];
  
  for (let i = 0; i < historicalData.length; i++) {
    if (historicalData[i].date.toISOString().split('T')[0] === runDateStr) {
      runDateIndex = i;
      break;
    }
  }
  
  if (runDateIndex === -1) {
    EW_trace('BACKFILL', `Warning: Run date ${runDateStr} not found in historical data`);
    // Try to find the first date after run date
    for (let i = 0; i < historicalData.length; i++) {
      if (historicalData[i].date >= runDate) {
        runDateIndex = i;
        break;
      }
    }
  }
  
  if (runDateIndex === -1) {
    EW_trace('BACKFILL', `Error: No data found on or after run date ${runDateStr}`);
    return analysis;
  }
  
  historicalData.forEach((dayData, index) => {
    // Skip data before run date
    if (index < runDateIndex) {
      return;
    }
    
    // Calculate trading days since entry (based on array position)
    const tradingDaysSinceEntry = index - runDateIndex;
    
    // Debug logging for first few days
    if (tradingDaysSinceEntry <= 5) {
      EW_trace('BACKFILL', `Trading Day ${tradingDaysSinceEntry}: Date=${dayData.date.toISOString().split('T')[0]}, Index=${index}, RunDateIndex=${runDateIndex}`);
    }
    
    // Track historical high/low
    analysis.historicalHigh = Math.max(analysis.historicalHigh, dayData.high);
    analysis.historicalLow = Math.min(analysis.historicalLow, dayData.low);
    
    // Check if strike was hit
    let dayHit = false;
    let hitPrice = null;
    
    if (isSpread && shortStrike) {
      // For spreads, check if price is in the profitable range
      if (isBullSpread) {
        // Bull spread: profitable when price >= longStrike AND < shortStrike
        if (dayData.high >= strike && dayData.high < shortStrike) {
          dayHit = true;
          hitPrice = dayData.high;
        }
      } else if (isBearSpread) {
        // Bear spread: profitable when price <= longStrike AND > shortStrike  
        if (dayData.low <= strike && dayData.low > shortStrike) {
          dayHit = true;
          hitPrice = dayData.low;
        }
      }
    } else {
      // Single strike strategies
      if (isBullish) {
        if (dayData.high >= strike) {
          dayHit = true;
          hitPrice = dayData.high;
        }
      } else if (isBearish) {
        if (dayData.low <= strike) {
          dayHit = true;
          hitPrice = dayData.low;
        }
      }
    }
    
    // Record first hit date and price
    if (dayHit && !hitDetected) {
      analysis.firstHitDate = dayData.date.toISOString().split('T')[0];
      analysis.firstHitPrice = hitPrice;
      hitDetected = true;
    }
    
    // Check specific day milestones based on trading days
    // tradingDaysSinceEntry starts at 0 for the entry date (same day)
    // Store the actual hit price or 'None' instead of HIT/NO
    if (tradingDaysSinceEntry === 0) {
      analysis.day0Hit = dayHit && hitPrice ? String(hitPrice.toFixed(2)) : 'None';
    } else if (tradingDaysSinceEntry === 1) {
      analysis.day1Hit = dayHit && hitPrice ? String(hitPrice.toFixed(2)) : 'None';
    } else if (tradingDaysSinceEntry === 2) {
      analysis.day2Hit = dayHit && hitPrice ? String(hitPrice.toFixed(2)) : 'None';
    } else if (tradingDaysSinceEntry === 3) {
      analysis.day3Hit = dayHit && hitPrice ? String(hitPrice.toFixed(2)) : 'None';
    } else if (tradingDaysSinceEntry === 4) {
      analysis.day4Hit = dayHit && hitPrice ? String(hitPrice.toFixed(2)) : 'None';
    } else if (tradingDaysSinceEntry === 5) {
      analysis.day5Hit = dayHit && hitPrice ? String(hitPrice.toFixed(2)) : 'None';
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
    
    if (isSpread && shortStrike) {
      // For spreads, check if closing price is in profitable range
      if (isBullSpread) {
        analysis.expResult = (lastDay.close >= strike && lastDay.close < shortStrike) ? 
          lastDay.close.toFixed(2) : 'None';
      } else if (isBearSpread) {
        analysis.expResult = (lastDay.close <= strike && lastDay.close > shortStrike) ? 
          lastDay.close.toFixed(2) : 'None';
      }
    } else {
      // Single strike strategies
      if (isBullish) {
        analysis.expResult = lastDay.close >= strike ? lastDay.close.toFixed(2) : 'None';
      } else if (isBearish) {
        analysis.expResult = lastDay.close <= strike ? lastDay.close.toFixed(2) : 'None';
      }
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
  
  const historicalData = EW_getYahooHistoricalRange(ticker, startDate, endDate);
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
      if (hdrMap.day0CheckCol && analysis.day0Hit) {
        sheet.getRange(rowNum, hdrMap.day0CheckCol).setValue(analysis.day0Hit);
      }
      if (hdrMap.day1CheckCol && analysis.day1Hit) {
        sheet.getRange(rowNum, hdrMap.day1CheckCol).setValue(analysis.day1Hit);
      }
      if (hdrMap.day2CheckCol && analysis.day2Hit) {
        sheet.getRange(rowNum, hdrMap.day2CheckCol).setValue(analysis.day2Hit);
      }
      if (hdrMap.day3CheckCol && analysis.day3Hit) {
        sheet.getRange(rowNum, hdrMap.day3CheckCol).setValue(analysis.day3Hit);
      }
      if (hdrMap.day4CheckCol && analysis.day4Hit) {
        sheet.getRange(rowNum, hdrMap.day4CheckCol).setValue(analysis.day4Hit);
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

/**
 * Test function to verify historical backfill with Yahoo data on a single sheet
 * Tests various scenarios including hit detection, day checks, and profit calculations
 */
function EW_testHistoricalBackfill() {
  console.log('=== Testing Historical Backfill with Yahoo Data ===');
  
  // Test configuration - modify these to test different scenarios
  const testConfig = {
    sheetName: 'Long Calls',  // Change this to test a different sheet
    maxRows: 5,              // Limit number of rows to test
    logDetails: true         // Set to true for detailed logging
  };
  
  try {
    const ss = SpreadsheetApp.getActive();
    const sheet = ss.getSheetByName(testConfig.sheetName);
    
    if (!sheet) {
      console.error(`Sheet '${testConfig.sheetName}' not found`);
      return;
    }
    
    console.log(`Testing sheet: ${testConfig.sheetName}`);
    
    // Get headers
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const hdrMap = EW_headerMap(headers);
    console.log('Header columns found:', Object.keys(hdrMap).filter(k => hdrMap[k]).join(', '));
    
    // Check required columns - handle spreads differently
    const isSpread = testConfig.sheetName.toUpperCase().includes('SPREAD');
    const strikeColumn = isSpread ? 'longStrikeCol' : 'strikeCol';
    
    const requiredCols = ['tickerCol', 'runDateCol', strikeColumn, 'daysToExpCol'];
    const missingCols = requiredCols.filter(col => !hdrMap[col]);
    if (missingCols.length > 0) {
      console.error('Missing required columns:', missingCols.join(', '));
      return;
    }
    
    // Get data rows
    const lastRow = Math.min(sheet.getLastRow(), testConfig.maxRows + 1);
    if (lastRow < 2) {
      console.log('No data rows found');
      return;
    }
    
    const dataRange = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
    const data = dataRange.getValues();
    
    console.log(`\nProcessing ${data.length} test rows...`);
    let testResults = [];
    
    // Test each row
    data.forEach((row, rowIndex) => {
      const ticker = row[hdrMap.tickerCol - 1];
      const runDateStr = row[hdrMap.runDateCol - 1];
      // For spreads, use longStrike; otherwise use strike
      const strikeCol = isSpread ? hdrMap.longStrikeCol : hdrMap.strikeCol;
      const strike = parseFloat(row[strikeCol - 1]) || 0;
      const expDateStr = hdrMap.expDateCol ? row[hdrMap.expDateCol - 1] : null;
      const daysToExp = parseFloat(row[hdrMap.daysToExpCol - 1]) || 0;
      
      if (!ticker || !runDateStr || !strike) {
        console.log(`Row ${rowIndex + 2}: Skipping - missing required data`);
        return;
      }
      
      console.log(`\n--- Testing Row ${rowIndex + 2} ---`);
      console.log(`Ticker: ${ticker}, Strike: ${strike}, Days to Exp: ${daysToExp}`);
      
      // Test different date scenarios
      const runDate = new Date(runDateStr);
      const today = new Date();
      
      // Scenario 1: Test if position is expired (historical)
      if (daysToExp < 0) {
        console.log('Position is EXPIRED - testing historical backfill');
        
        // Determine end date
        const expDate = expDateStr ? new Date(expDateStr) : null;
        const endDate = expDate && expDate < today ? expDate : today;
        
        console.log(`Date range: ${runDate.toISOString().split('T')[0]} to ${endDate.toISOString().split('T')[0]}`);
        
        // Test Yahoo data fetch
        try {
          console.log('Fetching Yahoo historical data...');
          const historicalData = EW_getYahooHistoricalRange(ticker, runDate, endDate);
          
          if (historicalData && historicalData.length > 0) {
            console.log(`Retrieved ${historicalData.length} days of data`);
            
            // Test analysis
            const analysis = EW_analyzeHistoricalData(testConfig.sheetName, strike, historicalData, runDate);
            
            if (testConfig.logDetails) {
              console.log('Analysis results:');
              console.log(`  First Hit Date: ${analysis.firstHitDate || 'Not hit'}`);
              console.log(`  Day 0 Check: ${analysis.day0Hit || 'N/A'}`);
              console.log(`  Day 1 Check: ${analysis.day1Hit || 'N/A'}`);
              console.log(`  Day 2 Check: ${analysis.day2Hit || 'N/A'}`);
              console.log(`  Day 3 Check: ${analysis.day3Hit || 'N/A'}`);
              console.log(`  Day 4 Check: ${analysis.day4Hit || 'N/A'}`);
              console.log(`  Day 5 Check: ${analysis.day5Hit || 'N/A'}`);
              console.log(`  Max Favorable: ${analysis.maxFavorable}%`);
              console.log(`  Min Unfavorable: ${analysis.minUnfavorable}%`);
              console.log(`  Historical High: ${analysis.historicalHigh}`);
              console.log(`  Historical Low: ${analysis.historicalLow}`);
              console.log(`  Exp Result: ${analysis.expResult || 'N/A'}`);
            }
            
            testResults.push({
              row: rowIndex + 2,
              ticker: ticker,
              strike: strike,
              status: 'SUCCESS',
              hitDetected: analysis.firstHitDate !== null,
              dataPoints: historicalData.length
            });
          } else {
            console.log('No historical data available');
            testResults.push({
              row: rowIndex + 2,
              ticker: ticker,
              strike: strike,
              status: 'NO_DATA',
              error: 'No historical data retrieved'
            });
          }
        } catch (error) {
          console.error(`Error fetching data: ${error.message}`);
          testResults.push({
            row: rowIndex + 2,
            ticker: ticker,
            strike: strike,
            status: 'ERROR',
            error: error.message
          });
        }
      } else {
        console.log('Position is ACTIVE (not expired) - skipping as per backfill logic');
        testResults.push({
          row: rowIndex + 2,
          ticker: ticker,
          strike: strike,
          status: 'SKIPPED',
          reason: 'Active position'
        });
      }
    });
    
    // Summary
    console.log('\n=== Test Summary ===');
    console.log(`Total rows tested: ${testResults.length}`);
    console.log(`Successful: ${testResults.filter(r => r.status === 'SUCCESS').length}`);
    console.log(`No data: ${testResults.filter(r => r.status === 'NO_DATA').length}`);
    console.log(`Errors: ${testResults.filter(r => r.status === 'ERROR').length}`);
    console.log(`Skipped: ${testResults.filter(r => r.status === 'SKIPPED').length}`);
    
    // Test single position fetch for most recent expired position
    const expiredPositions = testResults.filter(r => r.status === 'SUCCESS' && r.hitDetected);
    if (expiredPositions.length > 0) {
      console.log('\n=== Testing Single Position Backfill ===');
      const testPos = data[expiredPositions[0].row - 2];
      const ticker = testPos[hdrMap.tickerCol - 1];
      const runDate = testPos[hdrMap.runDateCol - 1];
      const strike = parseFloat(testPos[hdrMap.strikeCol - 1]);
      const expDate = hdrMap.expDateCol ? testPos[hdrMap.expDateCol - 1] : null;
      
      console.log(`Testing EW_backfillSinglePosition for ${ticker}`);
      const singleResult = EW_backfillSinglePosition(ticker, testConfig.sheetName, strike, runDate, expDate);
      console.log('Single position result:', singleResult);
    }
    
    return testResults;
    
  } catch (error) {
    console.error('Test failed:', error.message);
    console.error(error.stack);
  }
}

/**
 * Test Day Check calculations to debug N/A issues
 */
function EW_testDayChecks() {
  console.log('=== Testing Day Check Calculations ===');
  
  // Test with different date scenarios
  const today = new Date();
  const testScenarios = [
    { name: 'Yesterday entry', daysAgo: 1 },
    { name: '3 days ago entry', daysAgo: 3 },
    { name: '7 days ago entry', daysAgo: 7 },
    { name: '30 days ago entry', daysAgo: 30 }
  ];
  
  testScenarios.forEach(scenario => {
    const runDate = new Date(today);
    runDate.setDate(runDate.getDate() - scenario.daysAgo);
    
    console.log(`\n${scenario.name}:`);
    console.log(`  Run Date: ${runDate.toISOString().split('T')[0]}`);
    console.log(`  Today: ${today.toISOString().split('T')[0]}`);
    console.log(`  Days since entry: ${scenario.daysAgo}`);
    
    // Check which day checks should have values
    console.log('  Expected day checks (based on trading days):');
    
    // Calculate actual trading days
    const tradingDays = EW_countTradingDays(runDate, today) - 1; // -1 because we don't count today
    console.log(`  Actual trading days since entry: ${tradingDays}`);
    
    for (let day = 0; day <= 5; day++) {
      if (tradingDays >= day) {
        console.log(`    Day${day}_Check: Should have value (${tradingDays} trading days have passed)`);
      } else {
        console.log(`    Day${day}_Check: Should be N/A (only ${tradingDays} trading days have passed)`);
      }
    }
  });
  
  return 'Test complete - check console for results';
}

/**
 * Quick test to verify Yahoo integration is working
 * Tests a known historical position that should have hit
 */
function EW_quickTestBackfill() {
  console.log('=== Quick Backfill Test ===');
  
  // Test with a known historical example
  const testDate = new Date();
  testDate.setDate(testDate.getDate() - 10); // 10 days ago
  
  const testCases = [
    {
      ticker: 'IWM',
      strategy: 'Long Calls',
      strike: 220,
      runDate: testDate.toISOString().split('T')[0],
      expDate: new Date().toISOString().split('T')[0]
    },
    {
      ticker: 'SPY',
      strategy: 'Long Calls', 
      strike: 440,
      runDate: testDate.toISOString().split('T')[0],
      expDate: new Date().toISOString().split('T')[0]
    }
  ];
  
  testCases.forEach((testCase, index) => {
    console.log(`\nTest Case ${index + 1}: ${testCase.ticker} $${testCase.strike}`);
    try {
      const result = EW_backfillSinglePosition(
        testCase.ticker,
        testCase.strategy,
        testCase.strike,
        testCase.runDate,
        testCase.expDate
      );
      
      console.log('Result:', {
        hit: result.firstHitDate ? 'YES' : 'NO',
        hitDate: result.firstHitDate,
        maxFavorable: result.maxFavorable,
        historicalHigh: result.historicalHigh,
        historicalLow: result.historicalLow
      });
    } catch (error) {
      console.error(`Error: ${error.message}`);
    }
  });
}