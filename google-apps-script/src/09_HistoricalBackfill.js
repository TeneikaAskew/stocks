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
  let skippedCount = 0;
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
      
      // Skip if already has COMPLETE tracking data (all key columns filled)
      const hasStrikeHit = hdrMap.strikeHitCol && row[hdrMap.strikeHitCol - 1];
      const hasDay5Check = hdrMap.day5CheckCol && row[hdrMap.day5CheckCol - 1];
      const hasIndicators = hdrMap.hitRSICol && row[hdrMap.hitRSICol - 1];
      const hasLastUpdate = hdrMap.lastUpdateCol && row[hdrMap.lastUpdateCol - 1];
      
      // Only skip if ALL critical columns are already filled
      if (hasStrikeHit && hasDay5Check && hasIndicators && hasLastUpdate) {
        EW_trace('BACKFILL', `Skipping ${ticker} - already has complete tracking data`);
        return; // Skip only if fully processed
      }
      
      // Parse dates
      const runDate = new Date(runDateStr);
      runDate.setHours(0, 0, 0, 0);
      const expDate = expDateStr ? new Date(expDateStr) : null;
      if (expDate) expDate.setHours(0, 0, 0, 0);
      
      // Determine end date (expiration or today, whichever is earlier)
      const endDate = expDate && expDate < today ? expDate : today;
      
      // Skip if run date is in the future or invalid
      if (runDate > today || runDate > endDate) {
        EW_trace('BACKFILL', `Skipping ${ticker}: Invalid date range`);
        return;
      }
      
      EW_trace('BACKFILL', `Processing expired position: ${ticker} from ${runDate.toISOString().split('T')[0]} to ${endDate.toISOString().split('T')[0]} (Exp: ${expDateStr || 'none'})`);
      
      // Get historical price data using Yahoo Finance with raw data for indicators
      const yahooResult = EW_getYahooHistoricalRange(ticker, runDate, endDate, true);
      if (!yahooResult || !yahooResult.data || yahooResult.data.length === 0) {
        EW_trace('BACKFILL', `No 1-minute data available for ${ticker} - skipping position`);
        
        // Mark the position as having no data available
        const strikeHitValue = JSON.stringify(['NO_DATA']);
        dataRange.getCell(rowIndex + 1, hdrMap.strikeHitCol).setValue(strikeHitValue);
        
        // Add note about data unavailability
        if (hdrMap.notesCol) {
          dataRange.getCell(rowIndex + 1, hdrMap.notesCol).setValue('1-minute data unavailable (>7 days old)');
        }
        
        skippedCount++;
        return;
      }
      
      EW_trace('BACKFILL', `${ticker}: Got ${yahooResult.data.length} data points from Yahoo Finance`);
      if (yahooResult.raw) {
        EW_trace('BACKFILL', `${ticker}: Raw data includes ${yahooResult.raw.timestamps.length} timestamps`);
      }
      const firstDataDate = yahooResult.data[0].date.toISOString();
      const lastDataDate = yahooResult.data[yahooResult.data.length - 1].date.toISOString();
      EW_trace('BACKFILL', `${ticker}: Data range: ${firstDataDate} to ${lastDataDate}`);
      
      // Get short strike for spreads
      const shortStrike = isSpread && hdrMap.shortStrikeCol ? 
        parseFloat(row[hdrMap.shortStrikeCol - 1]) || null : null;
      
      // Analyze historical data with raw data for indicators
      const analysis = EW_analyzeHistoricalData(ticker, strategyName, strike, yahooResult.data, runDate, shortStrike, yahooResult.raw);
      
      // Update tracking columns with historical analysis
      let updated = false;
      
      // Update Strike_Hit column with array of percentage moves
      if (hdrMap.strikeHitCol) {
        const existing = row[hdrMap.strikeHitCol - 1];
        EW_trace('BACKFILL', `${ticker} Strike_Hit update check - Column: ${hdrMap.strikeHitCol}, Existing: "${existing}", Array length: ${analysis.strikeHitArray.length}`);
        if (!existing && analysis.strikeHitArray.length > 0) {
          // Store as JSON array
          const strikeHitJson = JSON.stringify(analysis.strikeHitArray);
          dataRange.getCell(rowIndex + 1, hdrMap.strikeHitCol).setValue(strikeHitJson);
          EW_trace('BACKFILL', `${ticker} Strike_Hit updated with: ${strikeHitJson}`);
          updated = true;
        }
      } else {
        EW_trace('BACKFILL', `${ticker} No Strike_Hit column found in header map`);
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
      
      // Peak_Profit_Date removed - using daily indicator arrays instead
      
      
      // Calculate and update Risk_Reward
      if (hdrMap.riskRewardCol && analysis.maxFavorable !== null && analysis.minUnfavorable !== null) {
        const existing = row[hdrMap.riskRewardCol - 1];
        if (!existing) {
          const favorable = parseFloat(analysis.maxFavorable);
          const unfavorable = parseFloat(analysis.minUnfavorable);
          if (unfavorable > 0) {
            const riskReward = (favorable / unfavorable).toFixed(2);
            dataRange.getCell(rowIndex + 1, hdrMap.riskRewardCol).setValue(riskReward);
            updated = true;
          }
        }
      }
      
      // Update indicator columns with arrays
      if (analysis.dailyIndicators && analysis.dailyIndicators.rsi.length > 0) {
        // Build indicator arrays using helper function
        const indicatorArrays = EW_buildIndicatorArrays(analysis.dailyIndicators);
        EW_trace('BACKFILL', `${ticker} Indicator arrays built - RSI length: ${analysis.dailyIndicators.rsi.length}`);
        
        if (hdrMap.hitRSICol && !row[hdrMap.hitRSICol - 1] && indicatorArrays.rsi) {
          dataRange.getCell(rowIndex + 1, hdrMap.hitRSICol).setValue(indicatorArrays.rsi);
          EW_trace('BACKFILL', `${ticker} RSI updated with: ${indicatorArrays.rsi.substring(0, 50)}...`);
          updated = true;
        }
        if (hdrMap.hitSMA20Col && !row[hdrMap.hitSMA20Col - 1] && indicatorArrays.sma20) {
          dataRange.getCell(rowIndex + 1, hdrMap.hitSMA20Col).setValue(indicatorArrays.sma20);
          updated = true;
        }
        if (hdrMap.hitSMA50Col && !row[hdrMap.hitSMA50Col - 1] && indicatorArrays.sma50) {
          dataRange.getCell(rowIndex + 1, hdrMap.hitSMA50Col).setValue(indicatorArrays.sma50);
          updated = true;
        }
        if (hdrMap.hitEMA9Col && !row[hdrMap.hitEMA9Col - 1] && indicatorArrays.ema9) {
          dataRange.getCell(rowIndex + 1, hdrMap.hitEMA9Col).setValue(indicatorArrays.ema9);
          updated = true;
        }
        if (hdrMap.hitEMA21Col && !row[hdrMap.hitEMA21Col - 1] && indicatorArrays.ema21) {
          dataRange.getCell(rowIndex + 1, hdrMap.hitEMA21Col).setValue(indicatorArrays.ema21);
          updated = true;
        }
        if (hdrMap.hitVWAPCol && !row[hdrMap.hitVWAPCol - 1] && indicatorArrays.vwap) {
          dataRange.getCell(rowIndex + 1, hdrMap.hitVWAPCol).setValue(indicatorArrays.vwap);
          updated = true;
        }
        if (hdrMap.hitRVOLCol && !row[hdrMap.hitRVOLCol - 1] && indicatorArrays.rvol) {
          dataRange.getCell(rowIndex + 1, hdrMap.hitRVOLCol).setValue(indicatorArrays.rvol);
          updated = true;
        }
        if (hdrMap.hitATRCol && !row[hdrMap.hitATRCol - 1] && indicatorArrays.atr) {
          dataRange.getCell(rowIndex + 1, hdrMap.hitATRCol).setValue(indicatorArrays.atr);
          updated = true;
        }
        if (hdrMap.hitPriceVsSMA20Col && !row[hdrMap.hitPriceVsSMA20Col - 1] && indicatorArrays.priceVsSMA20) {
          dataRange.getCell(rowIndex + 1, hdrMap.hitPriceVsSMA20Col).setValue(indicatorArrays.priceVsSMA20);
          updated = true;
        }
        if (hdrMap.hitPriceVsVWAPCol && !row[hdrMap.hitPriceVsVWAPCol - 1] && indicatorArrays.priceVsVWAP) {
          dataRange.getCell(rowIndex + 1, hdrMap.hitPriceVsVWAPCol).setValue(indicatorArrays.priceVsVWAP);
          updated = true;
        }
      }
      
      if (updated) {
        processedCount++;
        EW_trace('BACKFILL', `${ticker} Successfully updated tracking data`);
        
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
    
    // Apply formatting to Day Check columns
    try {
      EW_formatDayCheckColumns(sheet, hdrMap, strategyName);
      EW_trace('BACKFILL', `Applied Day Check formatting for ${strategyName}`);
    } catch (e) {
      EW_trace('BACKFILL', `Failed to apply formatting: ${e.message}`);
    }
  }
  
  EW_trace('BACKFILL', `${strategyName}: Processed ${processedCount} positions, skipped ${skippedCount} (no 1-minute data)`);
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
 * @param {string} ticker - Stock ticker symbol
 * @param {string} strategy - Strategy name
 * @param {number} strike - Strike price (or longStrike for spreads)
 * @param {Array} historicalData - Array of 1-minute price data
 * @param {Date} runDate - Entry date
 * @param {number} shortStrike - Short strike for spread strategies (optional)
 * @param {Object} rawData - Raw Yahoo data for indicator calculation (optional)
 * @returns {Object} Analysis results
 */
function EW_analyzeHistoricalData(ticker, strategy, strike, historicalData, runDate, shortStrike = null, rawData = null) {
  const analysis = {
    firstHitDate: null,
    firstHitPrice: null,
    day0Price: null,  // Track Day 0 price for percentage calculation
    day0Hit: null,
    day1Hit: null,
    day2Hit: null,
    day3Hit: null,
    day4Hit: null,
    day5Hit: null,
    maxFavorable: null,
    minUnfavorable: null,
    expResult: null,
    historicalHigh: 0,
    historicalLow: Infinity,
    // Technical indicators at peak profit
    indicators: null,
    // New fields for array implementation
    dailyPrices: [],  // Track daily closing prices
    strikeHitArray: [],  // Array of percentage moves to strike
    indicatorDates: [],  // Dates when indicators were calculated
    // Daily indicator arrays
    dailyIndicators: {
      rsi: [],
      sma20: [],
      sma50: [],
      ema9: [],
      ema21: [],
      vwap: [],
      rvol: [],
      atr: [],
      priceVsSMA20: [],
      priceVsVWAP: []
    }
  };
  
  if (!historicalData || historicalData.length === 0) return analysis;
  
  const strategyUpper = strategy.toUpperCase();
  const isSpread = strategyUpper.includes('SPREAD');
  const isBullSpread = strategyUpper.includes('BULL SPREAD');
  const isBearSpread = strategyUpper.includes('BEAR SPREAD');
  const isBullish = strategyUpper.includes('LONG CALL') || (strategyUpper.includes('BULL') && !isSpread);
  const isBearish = strategyUpper.includes('LONG PUT') || (strategyUpper.includes('BEAR') && !isSpread);
  
  let maxProfit = -Infinity;
  let maxLoss = 0; // Initialize to 0 instead of Infinity
  let hitDetected = false;
  
  // Group 1-minute data by trading day
  const dailyGroups = {};
  const runDateStr = runDate.toISOString().split('T')[0];
  
  // Log input data info
  EW_trace('BACKFILL', `${ticker}: Received ${historicalData.length} 1-minute bars to process`);
  if (historicalData.length > 0) {
    EW_trace('BACKFILL', `${ticker}: Data range from ${historicalData[0].date.toISOString()} to ${historicalData[historicalData.length - 1].date.toISOString()}`);
  }
  
  // First, group all 1-minute bars by date
  historicalData.forEach((bar, barIndex) => {
    const dateStr = bar.date.toISOString().split('T')[0];
    if (!dailyGroups[dateStr]) {
      dailyGroups[dateStr] = {
        date: new Date(dateStr),
        bars: [],
        open: null,
        high: -Infinity,
        low: Infinity,
        close: null
      };
    }
    
    dailyGroups[dateStr].bars.push(bar);
    
    // Update daily OHLC
    if (dailyGroups[dateStr].open === null) {
      dailyGroups[dateStr].open = bar.open;
    }
    dailyGroups[dateStr].high = Math.max(dailyGroups[dateStr].high, bar.high);
    dailyGroups[dateStr].low = Math.min(dailyGroups[dateStr].low, bar.low);
    dailyGroups[dateStr].close = bar.close; // Last bar's close
    
    // Log first few bars for debugging
    if (barIndex < 3) {
      EW_trace('BACKFILL', `${ticker}: Bar ${barIndex} - ${bar.date.toISOString()}, O:${bar.open}, H:${bar.high}, L:${bar.low}, C:${bar.close}`);
    }
  });
  
  // Convert to sorted array of days
  const sortedDays = Object.keys(dailyGroups)
    .sort()
    .map(dateStr => dailyGroups[dateStr]);
  
  // Log daily grouping results
  EW_trace('BACKFILL', `${ticker}: Grouped into ${sortedDays.length} trading days`);
  sortedDays.forEach((day, idx) => {
    if (idx < 3) { // Log first 3 days
      EW_trace('BACKFILL', `${ticker}: Day ${idx} - ${day.date.toISOString().split('T')[0]}, ${day.bars.length} bars, OHLC: ${day.open.toFixed(2)}/${day.high.toFixed(2)}/${day.low.toFixed(2)}/${day.close.toFixed(2)}`);
    }
  });
  
  // Find the index where our run date data starts
  let runDateIndex = -1;
  for (let i = 0; i < sortedDays.length; i++) {
    if (sortedDays[i].date.toISOString().split('T')[0] === runDateStr) {
      runDateIndex = i;
      EW_trace('BACKFILL', `${ticker}: Found run date ${runDateStr} at index ${i}`);
      break;
    }
  }
  
  if (runDateIndex === -1) {
    EW_trace('BACKFILL', `Warning: Run date ${runDateStr} not found in historical data`);
    // Try to find the first date after run date
    for (let i = 0; i < sortedDays.length; i++) {
      if (sortedDays[i].date >= runDate) {
        runDateIndex = i;
        break;
      }
    }
  }
  
  if (runDateIndex === -1) {
    EW_trace('BACKFILL', `Error: No data found on or after run date ${runDateStr}`);
    return analysis;
  }
  
  // Log data summary
  EW_trace('BACKFILL', `${ticker}: Processing ${historicalData.length} 1-minute bars grouped into ${sortedDays.length} trading days`);
  
  sortedDays.forEach((dayData, index) => {
    // Skip data before run date
    if (index < runDateIndex) {
      return;
    }
    
    // Calculate trading days since entry (based on array position)
    const tradingDaysSinceEntry = index - runDateIndex;
    
    // Log raw data status once at the beginning
    if (tradingDaysSinceEntry === 0) {
      if (!rawData) {
        EW_trace('BACKFILL', `${ticker}: No raw data provided for indicator calculation`);
      } else if (!rawData.timestamps || !rawData.quotes) {
        EW_trace('BACKFILL', `${ticker}: Raw data missing timestamps or quotes`);
      } else {
        EW_trace('BACKFILL', `${ticker}: Raw data available with ${rawData.timestamps.length} timestamps`);
      }
    }
    
    // Debug logging for first few days
    if (tradingDaysSinceEntry <= 5) {
      const dayOfWeek = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][dayData.date.getDay()];
      EW_trace('BACKFILL', `Trading Day ${tradingDaysSinceEntry}: ${dayData.date.toISOString().split('T')[0]} (${dayOfWeek}), Index=${index}`);
    }
    
    // Skip data after Day 5
    if (tradingDaysSinceEntry > 5) {
      return;
    }
    
    // Track historical high/low
    analysis.historicalHigh = Math.max(analysis.historicalHigh, dayData.high);
    analysis.historicalLow = Math.min(analysis.historicalLow, dayData.low);
    
    // Check if strike was hit by examining all 1-minute bars for this day
    let dayHit = false;
    let hitPrice = null;
    let hitTime = null;
    let hitBarIndex = -1;
    
    // Loop through all 1-minute bars for this day
    for (let barIdx = 0; barIdx < dayData.bars.length; barIdx++) {
      const bar = dayData.bars[barIdx];
      
      if (isSpread && shortStrike) {
        // For spreads, check if price is in the profitable range
        if (isBullSpread) {
          // Bull spread: profitable when price >= longStrike AND < shortStrike
          if (bar.high >= strike && bar.high < shortStrike) {
            dayHit = true;
            hitPrice = bar.high;
            hitTime = bar.date;
            hitBarIndex = barIdx;
            break; // Stop at first hit
          }
        } else if (isBearSpread) {
          // Bear spread: profitable when price <= longStrike AND > shortStrike  
          if (bar.low <= strike && bar.low > shortStrike) {
            dayHit = true;
            hitPrice = bar.low;
            hitTime = bar.date;
            hitBarIndex = barIdx;
            break;
          }
        }
      } else {
        // Single strike strategies
        if (isBullish) {
          if (bar.high >= strike) {
            dayHit = true;
            hitPrice = bar.high;
            hitTime = bar.date;
            hitBarIndex = barIdx;
            break;
          }
        } else if (isBearish) {
          if (bar.low <= strike) {
            dayHit = true;
            hitPrice = bar.low;
            hitTime = bar.date;
            hitBarIndex = barIdx;
            break;
          }
        }
      }
    }
    
    // Log hit detection for debugging
    if (dayHit && tradingDaysSinceEntry <= 2) {
      EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: Strike ${strike} hit at ${hitTime.toISOString()} (bar ${hitBarIndex}/${dayData.bars.length}), price: ${hitPrice}`);
    }
    
    // Record first hit date and price
    if (dayHit && !hitDetected) {
      analysis.firstHitDate = dayData.date.toISOString().split('T')[0];
      analysis.firstHitPrice = hitPrice;
      hitDetected = true;
    }
    
    // Check specific day milestones based on trading days
    // tradingDaysSinceEntry starts at 0 for the entry date (same day)
    // Store the most favorable price (high for bullish, low for bearish, or close)
    let dayPrice;
    if (dayHit && hitPrice) {
      // If strike was hit, use the hit price
      dayPrice = hitPrice.toFixed(2);
    } else if (isBullish) {
      // For bullish: show the high (best possible price)
      dayPrice = dayData.high.toFixed(2);
    } else if (isBearish) {
      // For bearish: show the low (best possible price)
      dayPrice = dayData.low.toFixed(2);
    } else {
      // Default: use closing price
      dayPrice = dayData.close.toFixed(2);
    }
    
    if (tradingDaysSinceEntry === 0) {
      analysis.day0Hit = dayPrice;
      // Store Day 0 closing price for Strike_Hit percentage calculation
      analysis.day0Price = dayData.close;
    } else if (tradingDaysSinceEntry === 1) {
      analysis.day1Hit = dayPrice;
    } else if (tradingDaysSinceEntry === 2) {
      analysis.day2Hit = dayPrice;
    } else if (tradingDaysSinceEntry === 3) {
      analysis.day3Hit = dayPrice;
    } else if (tradingDaysSinceEntry === 4) {
      analysis.day4Hit = dayPrice;
    } else if (tradingDaysSinceEntry === 5) {
      analysis.day5Hit = dayPrice;
    }
    
    // Build arrays for new implementation
    if (tradingDaysSinceEntry >= 0 && tradingDaysSinceEntry <= 5) {
      // Store daily closing price
      analysis.dailyPrices.push(dayData.close);
      
      // Calculate and store decimal move from close to strike (no percentage conversion)
      let percentMove;
      if (isBullish || (strategyUpper.includes('BULL') && !isSpread)) {
        // For bullish: (close - strike) / strike (positive when above strike)
        percentMove = ((dayData.close - strike) / strike).toFixed(6);
      } else if (isBearish || (strategyUpper.includes('BEAR') && !isSpread)) {
        // For bearish: (strike - close) / strike (positive when below strike)
        percentMove = ((strike - dayData.close) / strike).toFixed(6);
      } else {
        // Default: (close - strike) / strike
        percentMove = ((dayData.close - strike) / strike).toFixed(6);
      }
      analysis.strikeHitArray.push(percentMove);
      
      // Log the strike for debugging
      if (tradingDaysSinceEntry === 0) {
        const dayPriceDisplay = dayPrice || dayData.close.toFixed(2);
        const priceType = dayHit ? 'Hit' : (isBullish ? 'High' : (isBearish ? 'Low' : 'Close'));
        EW_trace('BACKFILL', `${ticker} - Strike: ${strike}, Day0 ${priceType}: ${dayPriceDisplay}, Close: ${dayData.close}, Move: ${percentMove}`);
      }
      
      // Calculate indicators for this day
      // Since we have 1-minute data, calculate indicators at the time of strike hit (if hit) or at market close
      if (rawData && rawData.timestamps && rawData.quotes) {
        try {
          // Find the raw data index for indicator calculation
          let targetTime = null;
          let rawDataIndex = -1;
          
          if (dayHit && hitTime) {
            // If strike was hit, calculate indicators at that exact time
            targetTime = hitTime;
            EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: Calculating indicators at strike hit time ${targetTime.toISOString()}`);
          } else {
            // Otherwise use the last bar of the day (market close)
            targetTime = dayData.bars[dayData.bars.length - 1].date;
            if (tradingDaysSinceEntry <= 2) {
              EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: No strike hit, using close time ${targetTime.toISOString()}`);
            }
          }
          
          // Find the corresponding index in raw data
          const targetTimestamp = Math.floor(targetTime.getTime() / 1000);
          for (let ri = 0; ri < rawData.timestamps.length; ri++) {
            if (rawData.timestamps[ri] === targetTimestamp) {
              rawDataIndex = ri;
              break;
            }
          }
          
          // If exact match not found, find the closest timestamp
          if (rawDataIndex === -1) {
            let minDiff = Infinity;
            for (let ri = 0; ri < rawData.timestamps.length; ri++) {
              const diff = Math.abs(rawData.timestamps[ri] - targetTimestamp);
              if (diff < minDiff) {
                minDiff = diff;
                rawDataIndex = ri;
              }
            }
            if (tradingDaysSinceEntry <= 2) {
              EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: No exact timestamp match, using closest (${minDiff} seconds difference)`);
            }
          }
          
          if (rawDataIndex >= 0) {
            // Calculate indicators for this day
            const dayIndicators = EW_calculateIndicatorsFromYahoo(
              rawData.timestamps,
              rawData.quotes,
              rawDataIndex
            );
            
            if (dayIndicators) {
              // Store each indicator value
              analysis.dailyIndicators.rsi.push(dayIndicators.rsi);
              analysis.dailyIndicators.sma20.push(dayIndicators.sma20);
              analysis.dailyIndicators.sma50.push(dayIndicators.sma50);
              analysis.dailyIndicators.ema9.push(dayIndicators.ema9);
              analysis.dailyIndicators.ema21.push(dayIndicators.ema21);
              analysis.dailyIndicators.vwap.push(dayIndicators.vwap);
              analysis.dailyIndicators.rvol.push(dayIndicators.rvol);
              analysis.dailyIndicators.atr.push(dayIndicators.atr);
              analysis.dailyIndicators.priceVsSMA20.push(dayIndicators.priceVsSMA20);
              analysis.dailyIndicators.priceVsVWAP.push(dayIndicators.priceVsVWAP);
              
              EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: Calculated indicators at index ${rawDataIndex} - RSI=${dayIndicators.rsi?.toFixed(2)}, SMA20=${dayIndicators.sma20?.toFixed(2)}, VWAP=${dayIndicators.vwap?.toFixed(2)}`);
            } else {
              EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: Failed to calculate indicators at index ${rawDataIndex}`);
              // Push nulls if indicators couldn't be calculated
              Object.keys(analysis.dailyIndicators).forEach(key => {
                analysis.dailyIndicators[key].push(null);
              });
            }
          } else {
            // No matching raw data found
            EW_trace('BACKFILL', `${ticker} Day ${tradingDaysSinceEntry}: No raw data index found for time ${targetTime.toISOString()}`);
            Object.keys(analysis.dailyIndicators).forEach(key => {
              analysis.dailyIndicators[key].push(null);
            });
          }
        } catch (error) {
          EW_trace('BACKFILL', `Failed to calculate daily indicators: ${error.message}`);
          // Push nulls on error
          Object.keys(analysis.dailyIndicators).forEach(key => {
            analysis.dailyIndicators[key].push(null);
          });
        }
      }
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
    
    // Track max profit for favorable calculation
    if (dayProfit > maxProfit) {
      maxProfit = dayProfit;
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
          lastDay.close.toFixed(2) : 'Not profitable at closing';
      } else if (isBearSpread) {
        analysis.expResult = (lastDay.close <= strike && lastDay.close > shortStrike) ? 
          lastDay.close.toFixed(2) : 'Not profitable at closing';
      }
    } else {
      // Single strike strategies
      if (isBullish) {
        analysis.expResult = lastDay.close >= strike ? lastDay.close.toFixed(2) : 'Not profitable at closing';
      } else if (isBearish) {
        analysis.expResult = lastDay.close <= strike ? lastDay.close.toFixed(2) : 'Not profitable at closing';
      }
    }
  }
  
  // Note: Indicators are now calculated daily and stored in arrays
  // The dailyIndicators object contains arrays for each indicator type
  
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
  
  // Get historical data with raw data for indicators
  const yahooResult = EW_getYahooHistoricalRange(ticker, startDate, endDate, true);
  
  if (yahooResult && yahooResult.data) {
    const analysis = EW_analyzeHistoricalData(ticker, strategy, strike, yahooResult.data, startDate, null, yahooResult.raw);
    return analysis;
  } else {
    // Fallback if includeRaw not supported
    const historicalData = EW_getYahooHistoricalRange(ticker, startDate, endDate);
    const analysis = EW_analyzeHistoricalData(ticker, strategy, strike, historicalData, startDate);
    return analysis;
  }
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
  const message = 'Processed ' + processedCount + ' of ' + numRows + ' selected rows';
  EW_safeAlert('Backfill Complete', message);
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
          const yahooResult = EW_getYahooHistoricalRange(ticker, runDate, endDate, true);
          
          if (yahooResult && yahooResult.data && yahooResult.data.length > 0) {
            console.log(`Retrieved ${yahooResult.data.length} data points`);
            
            // Log raw data details
            if (yahooResult.raw) {
              console.log(`Raw data: ${yahooResult.raw.timestamps.length} timestamps`);
              if (yahooResult.raw.timestamps.length > 0) {
                console.log(`Raw data range: ${new Date(yahooResult.raw.timestamps[0] * 1000).toISOString()} to ${new Date(yahooResult.raw.timestamps[yahooResult.raw.timestamps.length - 1] * 1000).toISOString()}`);
              }
            } else {
              console.log('No raw data included in response');
            }
            
            // Test analysis with raw data
            const analysis = EW_analyzeHistoricalData(testConfig.ticker, testConfig.sheetName, strike, yahooResult.data, runDate, null, yahooResult.raw);
            
            if (testConfig.logDetails) {
              console.log('\nAnalysis results:');
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
              
              // Add full array output
              console.log('\nArray Data:');
              console.log(`  Strike_Hit Array: ${JSON.stringify(analysis.strikeHitArray)}`);
              console.log(`  Daily Prices: ${JSON.stringify(analysis.dailyPrices)}`);
              
              // Add indicator arrays
              console.log('\nIndicator Arrays:');
              console.log(`  RSI: ${JSON.stringify(analysis.dailyIndicators.rsi)}`);
              console.log(`  SMA20: ${JSON.stringify(analysis.dailyIndicators.sma20)}`);
              console.log(`  SMA50: ${JSON.stringify(analysis.dailyIndicators.sma50)}`);
              console.log(`  VWAP: ${JSON.stringify(analysis.dailyIndicators.vwap)}`);
              console.log(`  RVOL: ${JSON.stringify(analysis.dailyIndicators.rvol)}`);
              console.log(`  ATR: ${JSON.stringify(analysis.dailyIndicators.atr)}`);
              console.log(`  Exp Result: ${analysis.expResult || 'N/A'}`);
            }
            
            testResults.push({
              row: rowIndex + 2,
              ticker: ticker,
              strike: strike,
              status: 'SUCCESS',
              hitDetected: analysis.firstHitDate !== null,
              dataPoints: yahooResult.data.length
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