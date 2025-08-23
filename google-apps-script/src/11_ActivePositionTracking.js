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
 * REFACTORED: Now uses array building functions from 13_ArrayBuilders.js
 * This ensures consistency with backfill functions and properly builds arrays day-by-day
 * 
 * Updates performed:
 * - Strike_Hit, Max_Favorable, Min_Unfavorable arrays (by day index)
 * - All indicator arrays (RSI, SMA20, etc.) for the current day
 * - Historical_High/Low tracking
 * - Day checks for the current day only
 * - Exp_Result (closing price) for expired positions
 * - Risk_Reward calculated from arrays
 * - First_Hit_Date (in addition to Hit_Date)
 * 
 * @param {SpreadsheetApp.Spreadsheet} ss - The spreadsheet
 * @param {string} strategyName - Name of the strategy/sheet
 * @returns {Object} Object with checked and updated counts
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
  
  // Process all positions (both active and recently expired)
  data.forEach((row, rowIndex) => {
    const ticker = row[hdrMap.tickerCol - 1];
    const runDateStr = row[hdrMap.runDateCol - 1];
    const strike = hdrMap.strikeCol ? parseFloat(row[hdrMap.strikeCol - 1]) || 0 : 0;
    const longStrike = hdrMap.longStrikeCol ? parseFloat(row[hdrMap.longStrikeCol - 1]) || 0 : 0;
    const shortStrike = hdrMap.shortStrikeCol ? parseFloat(row[hdrMap.shortStrikeCol - 1]) || 0 : 0;
    const daysToExp = parseFloat(row[hdrMap.daysToExpCol - 1]) || 0;
    const currentStrikeHit = row[hdrMap.strikeHitCol - 1];
    const expDateStr = hdrMap.expDateCol ? row[hdrMap.expDateCol - 1] : null;
    
    // Check if position has valid strike data
    const hasValidStrike = strike || (longStrike && shortStrike);
    
    if (!ticker || !runDateStr || !hasValidStrike) return;
    
    const runDate = new Date(runDateStr);
    runDate.setHours(0, 0, 0, 0);
    const expDate = expDateStr ? new Date(expDateStr) : null;
    const daysSinceEntry = Math.floor((today - runDate) / (1000 * 60 * 60 * 24));
    
    // Process active positions and recently expired (within last 7 days)
    if (daysToExp > -7) {
      positionsToCheck.push({
        rowIndex: rowIndex,
        ticker: ticker,
        strike: strike,
        longStrike: longStrike,
        shortStrike: shortStrike,
        strategy: strategyName,
        startDate: runDate,
        endDate: today,
        daysToExp: daysToExp,
        daysSinceEntry: daysSinceEntry,
        expDate: expDate,
        currentStrikeHit: currentStrikeHit,
        row: row  // Pass entire row for additional updates
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
      const position = positionsToCheck[results.indexOf(result)];
      const row = position.row;
      const strike = position.strike || position.longStrike || 0;
      const dayIndex = Math.min(position.daysSinceEntry, 5); // Cap at day 5
      
      // Log if fallback was used
      if (result.fallbackUsed) {
        console.log(`ACTIVE TRACKING: ${strategyName} - ${result.ticker} used ${result.fallbackUsed} interval (fallback)`);
        Logger.log(`ACTIVE TRACKING FALLBACK: ${strategyName}/${result.ticker} used ${result.fallbackUsed} interval`);
      }
      
      // Parse existing arrays from cells
      const existingMaxFav = EW_parseArrayFromCell(row[hdrMap.maxFavorableCol - 1]);
      const existingMinUnfav = EW_parseArrayFromCell(row[hdrMap.minUnfavorableCol - 1]);
      const existingStrikeHit = EW_parseArrayFromCell(row[hdrMap.strikeHitCol - 1]);
      const existingHistoricalHigh = parseFloat(row[hdrMap.historicalHighCol - 1]) || 0;
      const existingHistoricalLow = parseFloat(row[hdrMap.historicalLowCol - 1]) || Infinity;
      
      // Parse existing indicator arrays
      const existingIndicators = {
        rsi: EW_parseArrayFromCell(row[hdrMap.hitRSICol - 1]),
        sma20: EW_parseArrayFromCell(row[hdrMap.hitSMA20Col - 1]),
        sma50: EW_parseArrayFromCell(row[hdrMap.hitSMA50Col - 1]),
        ema9: EW_parseArrayFromCell(row[hdrMap.hitEMA9Col - 1]),
        ema21: EW_parseArrayFromCell(row[hdrMap.hitEMA21Col - 1]),
        vwap: EW_parseArrayFromCell(row[hdrMap.hitVWAPCol - 1]),
        rvol: EW_parseArrayFromCell(row[hdrMap.hitRVOLCol - 1]),
        atr: EW_parseArrayFromCell(row[hdrMap.hitATRCol - 1]),
        priceVsSMA20: EW_parseArrayFromCell(row[hdrMap.hitPriceVsSMA20Col - 1]),
        priceVsVWAP: EW_parseArrayFromCell(row[hdrMap.hitPriceVsVWAPCol - 1])
      };
      
      // Build/update arrays for current day
      const updatedMaxFav = EW_buildMaxFavorableArray(
        existingMaxFav, dayIndex, strategyName, strike, result.dayHigh, result.dayLow
      );
      
      const updatedMinUnfav = EW_buildMinUnfavorableArray(
        existingMinUnfav, dayIndex, strategyName, strike, result.dayHigh, result.dayLow
      );
      
      const updatedStrikeHit = EW_buildStrikeHitArray(
        existingStrikeHit, dayIndex, strategyName, strike, result.dayHigh, result.dayLow, result.hit
      );
      
      // Update indicator arrays if we have indicator data
      let updatedIndicators = existingIndicators;
      if (result.indicators) {
        updatedIndicators = EW_buildIndicatorArraysForDay(
          existingIndicators, dayIndex, result.indicators
        );
      }
      
      // Update historical high/low
      const updatedHistorical = EW_updateHistoricalHighLow(
        { high: existingHistoricalHigh, low: existingHistoricalLow },
        result.dayHigh, result.dayLow
      );
      
      // Update arrays in sheet
      if (hdrMap.maxFavorableCol) {
        dataRange.getCell(result.rowIndex + 1, hdrMap.maxFavorableCol)
          .setValue(EW_arrayToJson(updatedMaxFav));
      }
      
      if (hdrMap.minUnfavorableCol) {
        dataRange.getCell(result.rowIndex + 1, hdrMap.minUnfavorableCol)
          .setValue(EW_arrayToJson(updatedMinUnfav));
      }
      
      if (hdrMap.strikeHitCol) {
        dataRange.getCell(result.rowIndex + 1, hdrMap.strikeHitCol)
          .setValue(EW_arrayToJson(updatedStrikeHit));
      }
      
      // Update historical high/low
      if (hdrMap.historicalHighCol && updatedHistorical.high !== existingHistoricalHigh) {
        dataRange.getCell(result.rowIndex + 1, hdrMap.historicalHighCol)
          .setValue(updatedHistorical.high);
      }
      
      if (hdrMap.historicalLowCol && updatedHistorical.low !== existingHistoricalLow) {
        dataRange.getCell(result.rowIndex + 1, hdrMap.historicalLowCol)
          .setValue(updatedHistorical.low);
      }
      
      // Update indicator arrays (store as JSON)
      const indicatorMappings = [
        { col: hdrMap.hitRSICol, data: updatedIndicators.rsi },
        { col: hdrMap.hitSMA20Col, data: updatedIndicators.sma20 },
        { col: hdrMap.hitSMA50Col, data: updatedIndicators.sma50 },
        { col: hdrMap.hitEMA9Col, data: updatedIndicators.ema9 },
        { col: hdrMap.hitEMA21Col, data: updatedIndicators.ema21 },
        { col: hdrMap.hitVWAPCol, data: updatedIndicators.vwap },
        { col: hdrMap.hitRVOLCol, data: updatedIndicators.rvol },
        { col: hdrMap.hitATRCol, data: updatedIndicators.atr },
        { col: hdrMap.hitPriceVsSMA20Col, data: updatedIndicators.priceVsSMA20 },
        { col: hdrMap.hitPriceVsVWAPCol, data: updatedIndicators.priceVsVWAP }
      ];
      
      indicatorMappings.forEach(mapping => {
        if (mapping.col && mapping.data.length > 0) {
          dataRange.getCell(result.rowIndex + 1, mapping.col)
            .setValue(EW_arrayToJson(mapping.data));
        }
      });
      
      // Update Hit_Date and First_Hit_Date if strike was hit
      if (result.hit) {
        const hitDateStr = result.hitDate.toISOString().split('T')[0];
        
        // Update Hit_Date (most recent hit)
        if (hdrMap.hitDateCol) {
          dataRange.getCell(result.rowIndex + 1, hdrMap.hitDateCol).setValue(hitDateStr);
        }
        
        // Update First_Hit_Date (only if not already set)
        if (hdrMap.firstHitDateCol) {
          const existingFirstHit = row[hdrMap.firstHitDateCol - 1];
          if (!existingFirstHit) {
            dataRange.getCell(result.rowIndex + 1, hdrMap.firstHitDateCol).setValue(hitDateStr);
          }
        }
      }
      
      updatedCount++;
      console.log(`ACTIVE TRACKING: ${strategyName} - Updated ${result.ticker} arrays for day ${dayIndex}`);
      
      // Update Day0_Check through Day5_Check
      const dayChecks = [
        { col: hdrMap.day0CheckCol, day: 0 },
        { col: hdrMap.day1CheckCol, day: 1 },
        { col: hdrMap.day2CheckCol, day: 2 },
        { col: hdrMap.day3CheckCol, day: 3 },
        { col: hdrMap.day4CheckCol, day: 4 },
        { col: hdrMap.day5CheckCol, day: 5 }
      ];
      
      // Update the specific day check for today
      for (const check of dayChecks) {
        if (check.col && position.daysSinceEntry === check.day) {
          // Update today's day check with closing price
          let dayCheckValue = 'None';
          
          if (result.lastClose) {
            dayCheckValue = result.lastClose.toFixed(2);
          } else if (result.dayHigh && result.dayLow) {
            // If no close price, use average of high and low
            const avgPrice = (parseFloat(result.dayHigh) + parseFloat(result.dayLow)) / 2;
            dayCheckValue = avgPrice.toFixed(2);
          }
          
          dataRange.getCell(result.rowIndex + 1, check.col).setValue(dayCheckValue);
        }
      }
      
      // Update Exp_Result if position has expired
      if (hdrMap.expResultCol && position.expDate && today >= position.expDate) {
        const existing = row[hdrMap.expResultCol - 1];
        if (!existing && result.lastClose) {
          // Store the closing price at expiration
          const expResult = result.lastClose.toFixed(2);
          dataRange.getCell(result.rowIndex + 1, hdrMap.expResultCol).setValue(expResult);
        }
      }
      
      // Calculate and update Risk_Reward from arrays
      if (hdrMap.riskRewardCol) {
        const existing = row[hdrMap.riskRewardCol - 1];
        if (!existing) {
          const riskReward = EW_calculateRiskRewardFromArrays(updatedMaxFav, updatedMinUnfav);
          if (riskReward) {
            dataRange.getCell(result.rowIndex + 1, hdrMap.riskRewardCol).setValue(riskReward);
          }
        }
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