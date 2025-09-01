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
  
  // Check if today is a weekend - skip if Saturday (6) or Sunday (0)
  const dayOfWeek = startTime.getDay();
  if (dayOfWeek === 0 || dayOfWeek === 6) {
    const dayName = dayOfWeek === 0 ? 'Sunday' : 'Saturday';
    const msg = `Skipping active position tracking - Today is ${dayName}, markets are closed`;
    console.log(`ACTIVE TRACKING: ${msg}`);
    Logger.log(`ACTIVE TRACKING: ${msg}`);
    EW_trace('ACTIVE_TRACKING', msg, true);
    return { checked: 0, updated: 0, duration: 0, skipped: true, reason: 'weekend' };
  }
  
  EW_trace('ACTIVE_TRACKING', 'Starting Strike_Hit updates for active positions', true);
  
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  let totalUpdated = 0;
  let totalChecked = 0;
  let totalSkipped = 0;
  let totalExpired = 0;
  let errors = [];
  
  for (const strategy of strategies) {
    try {
      console.log(`ACTIVE TRACKING: Processing ${strategy} sheet...`);
      const result = EW_updateStrategyActiveStrikes(ss, strategy);
      totalChecked += result.checked;
      totalUpdated += result.updated;
      totalSkipped += (result.skipped || 0);
      totalExpired += (result.expired || 0);
      
      if (result.updated > 0) {
        EW_trace('ACTIVE_TRACKING', `Updated ${result.updated} of ${result.checked} active positions in ${strategy}` + 
          (result.skipped > 0 ? ` (skipped ${result.skipped} already updated)` : ''));
        console.log(`ACTIVE TRACKING: ${strategy} - Updated ${result.updated}/${result.checked} positions` +
          (result.skipped > 0 ? `, skipped ${result.skipped}` : ''));
      } else if (result.checked > 0) {
        console.log(`ACTIVE TRACKING: ${strategy} - Checked ${result.checked} positions, no updates needed`);
      } else if (result.skipped > 0) {
        console.log(`ACTIVE TRACKING: ${strategy} - All ${result.skipped} positions already updated today`);
      }
    } catch (e) {
      errors.push(`${strategy}: ${e.message}`);
      EW_trace('ACTIVE_TRACKING', `Error updating ${strategy}: ${e.message}`, true);
      console.error(`ACTIVE TRACKING ERROR: ${strategy} - ${e.message}`);
    }
  }
  
  // Don't clear continuation state here - this function doesn't use continuation
  // and clearing it could interfere with other functions that do
  
  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);
  
  const msg = `Active position update complete.\n` +
    `Checked: ${totalChecked} positions\n` +
    `Updated: ${totalUpdated} positions\n` +
    `Skipped: ${totalSkipped} positions (already updated)\n` +
    `Expired: ${totalExpired} positions (>7 days old)\n` +
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
    return { checked: 0, updated: 0 };
  }
  
  // Get header map
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Check required columns - handle spreads that have longStrike/shortStrike instead of strike
  const baseRequiredCols = ['tickerCol', 'runDateCol', 'daysToExpCol', 'strikeHitCol'];
  for (const col of baseRequiredCols) {
    if (!hdrMap[col]) {
      EW_trace('ACTIVE_TRACKING', `${strategyName}: Missing required column ${col}`);
      return { checked: 0, updated: 0 };
    }
  }
  
  // Check for strike columns - must have either strike OR (longStrike AND shortStrike)
  const hasStrikeCol = hdrMap.strikeCol;
  const hasSpreadCols = hdrMap.longStrikeCol && hdrMap.shortStrikeCol;
  
  if (!hasStrikeCol && !hasSpreadCols) {
    EW_trace('ACTIVE_TRACKING', `${strategyName}: Missing strike column(s) - needs either 'strike' or both 'longStrike' and 'shortStrike'`);
    return { checked: 0, updated: 0 };
  }
  
  // Get all data
  const lastRow = sheet.getLastRow();
  const dataRange = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
  const data = dataRange.getValues();
  
  // Use batch checking to determine which positions need updating
  const batchCheck = EW_batchCheckActivePositions(sheet, hdrMap, data, strategyName);
  
  // Log the summary once
  EW_trace('ACTIVE_TRACKING', batchCheck.summary, true);
  
  if (batchCheck.needsChecking === 0) {
    EW_trace('ACTIVE_TRACKING', `${strategyName}: No active positions need updating`);
    return { 
      checked: batchCheck.totalRows, 
      updated: 0,
      skipped: batchCheck.skippedAlreadyUpdated.length,
      expired: batchCheck.skippedExpired.length
    };
  }
  
  let updatedCount = 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  
  // Process all positions that need checking
  const positionsToCheck = batchCheck.positionsToCheck.map(pos => ({
    ...pos,
    strategy: strategyName,
    startDate: pos.runDate,
    endDate: today,
    daysSinceEntry: pos.dayIndex,
    currentStrikeHit: data[pos.rowIndex][hdrMap.strikeHitCol - 1],
    row: data[pos.rowIndex],
    expDate: data[pos.rowIndex][hdrMap.expDateCol - 1] ? new Date(data[pos.rowIndex][hdrMap.expDateCol - 1]) : null
  }));
  
  // Batch check strike hits
  const results = EW_batchCheckStrikeHits(positionsToCheck);
  
  // Update cells with results
  results.forEach((result, index) => {
    if (!result.error) {
      const position = positionsToCheck[index];
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
        dataRange.getCell(position.rowIndex + 1, hdrMap.maxFavorableCol)
          .setValue(EW_arrayToJson(updatedMaxFav));
      }
      
      if (hdrMap.minUnfavorableCol) {
        dataRange.getCell(position.rowIndex + 1, hdrMap.minUnfavorableCol)
          .setValue(EW_arrayToJson(updatedMinUnfav));
      }
      
      if (hdrMap.strikeHitCol) {
        dataRange.getCell(position.rowIndex + 1, hdrMap.strikeHitCol)
          .setValue(EW_arrayToJson(updatedStrikeHit));
      }
      
      // Update historical high/low
      if (hdrMap.historicalHighCol && updatedHistorical.high !== existingHistoricalHigh) {
        dataRange.getCell(position.rowIndex + 1, hdrMap.historicalHighCol)
          .setValue(updatedHistorical.high);
      }
      
      if (hdrMap.historicalLowCol && updatedHistorical.low !== existingHistoricalLow) {
        dataRange.getCell(position.rowIndex + 1, hdrMap.historicalLowCol)
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
          dataRange.getCell(position.rowIndex + 1, mapping.col)
            .setValue(EW_arrayToJson(mapping.data));
        }
      });
      
      // Update Hit_Date and First_Hit_Date if strike was hit
      if (result.hit) {
        const hitDateStr = result.hitDate.toISOString().split('T')[0];
        
        // Update Hit_Date (most recent hit)
        if (hdrMap.hitDateCol) {
          dataRange.getCell(position.rowIndex + 1, hdrMap.hitDateCol).setValue(hitDateStr);
        }
        
        // Update First_Hit_Date (only if not already set)
        if (hdrMap.firstHitDateCol) {
          const existingFirstHit = row[hdrMap.firstHitDateCol - 1];
          if (!existingFirstHit) {
            dataRange.getCell(position.rowIndex + 1, hdrMap.firstHitDateCol).setValue(hitDateStr);
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
          
          dataRange.getCell(position.rowIndex + 1, check.col).setValue(dayCheckValue);
        }
      }
      
      // Update Exp_Result if position has expired
      if (hdrMap.expResultCol && position.expDate && today >= position.expDate) {
        const existing = row[hdrMap.expResultCol - 1];
        if (!existing && result.lastClose) {
          // Store the closing price at expiration
          const expResult = result.lastClose.toFixed(2);
          dataRange.getCell(position.rowIndex + 1, hdrMap.expResultCol).setValue(expResult);
        }
      }
      
      // Calculate and update Risk_Reward from arrays
      if (hdrMap.riskRewardCol) {
        const existing = row[hdrMap.riskRewardCol - 1];
        if (!existing) {
          const riskReward = EW_calculateRiskRewardFromArrays(updatedMaxFav, updatedMinUnfav);
          if (riskReward) {
            dataRange.getCell(position.rowIndex + 1, hdrMap.riskRewardCol).setValue(riskReward);
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
  
  // Log final summary with progress
  const finalSummary = `${strategyName} Complete: Updated ${updatedCount}/${positionsToCheck.length} positions`;
  EW_trace('ACTIVE_TRACKING', finalSummary, true);
  
  return { 
    checked: positionsToCheck.length, 
    updated: updatedCount,
    skipped: batchCheck.skippedAlreadyUpdated.length,
    expired: batchCheck.skippedExpired.length
  };
}

// Note: Trigger functions have been moved to 03_Triggers.js

/**
 * Test function for active position tracking
 * Similar to EW_testHistoricalBackfill but for active positions
 * Updates all columns including arrays for a test position
 */
function EW_testActivePositionTracking() {
  console.log('\n=== ACTIVE POSITION TRACKING TEST ===');
  const startTime = new Date();
  
  // Test configuration - simulates an active position
  const testConfig = {
    ticker: 'IWM',
    strategy: 'Long Calls',
    strike: 230,
    runDate: new Date('2025-01-20'),  // 3 days ago
    expDate: new Date('2025-01-27'),  // 4 days from now
  };
  
  // Calculate days since entry
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const runDate = new Date(testConfig.runDate);
  runDate.setHours(0, 0, 0, 0);
  const daysSinceEntry = Math.floor((today - runDate) / (1000 * 60 * 60 * 24));
  const dayIndex = Math.min(daysSinceEntry, 5);
  
  console.log(`\nTest Configuration:`);
  console.log(`  Ticker: ${testConfig.ticker}`);
  console.log(`  Strategy: ${testConfig.strategy}`);
  console.log(`  Strike: ${testConfig.strike}`);
  console.log(`  Run Date: ${testConfig.runDate.toISOString().split('T')[0]}`);
  console.log(`  Exp Date: ${testConfig.expDate.toISOString().split('T')[0]}`);
  console.log(`  Days Since Entry: ${daysSinceEntry}`);
  console.log(`  Current Day Index: ${dayIndex}`);
  
  // Simulate existing arrays (as if we've been tracking for previous days)
  const existingArrays = {
    maxFavorable: dayIndex > 0 ? Array(dayIndex).fill(null).map((_, i) => (Math.random() * 5).toFixed(2)) : [],
    minUnfavorable: dayIndex > 0 ? Array(dayIndex).fill(null).map((_, i) => (Math.random() * 3).toFixed(2)) : [],
    strikeHit: dayIndex > 0 ? Array(dayIndex).fill(null) : [],
    indicators: {
      rsi: dayIndex > 0 ? Array(dayIndex).fill(null).map(() => (40 + Math.random() * 40).toFixed(2)) : [],
      sma20: dayIndex > 0 ? Array(dayIndex).fill(null).map(() => (225 + Math.random() * 10).toFixed(2)) : [],
      sma50: dayIndex > 0 ? Array(dayIndex).fill(null).map(() => (220 + Math.random() * 10).toFixed(2)) : [],
      ema9: dayIndex > 0 ? Array(dayIndex).fill(null).map(() => (227 + Math.random() * 10).toFixed(2)) : [],
      ema21: dayIndex > 0 ? Array(dayIndex).fill(null).map(() => (223 + Math.random() * 10).toFixed(2)) : [],
      vwap: dayIndex > 0 ? Array(dayIndex).fill(null).map(() => (226 + Math.random() * 10).toFixed(2)) : [],
      rvol: dayIndex > 0 ? Array(dayIndex).fill(null).map(() => (0.8 + Math.random() * 0.4).toFixed(2)) : [],
      atr: dayIndex > 0 ? Array(dayIndex).fill(null).map(() => (2 + Math.random()).toFixed(4)) : [],
      priceVsSMA20: dayIndex > 0 ? Array(dayIndex).fill(null).map(() => (-2 + Math.random() * 4).toFixed(2)) : [],
      priceVsVWAP: dayIndex > 0 ? Array(dayIndex).fill(null).map(() => (-1 + Math.random() * 2).toFixed(2)) : []
    }
  };
  
  console.log('\nExisting Arrays (simulated):');
  console.log(`  Max_Favorable: ${JSON.stringify(existingArrays.maxFavorable)}`);
  console.log(`  Min_Unfavorable: ${JSON.stringify(existingArrays.minUnfavorable)}`);
  console.log(`  Strike_Hit: ${JSON.stringify(existingArrays.strikeHit)}`);
  
  // Get today's data from Yahoo
  console.log('\nFetching today\'s data from Yahoo...');
  const result = EW_checkStrikeHitYahoo(
    testConfig.ticker,
    testConfig.strike,
    testConfig.strategy,
    today,
    today
  );
  
  if (result.error) {
    console.error(`ERROR: ${result.error}`);
    return;
  }
  
  console.log('\nToday\'s Market Data:');
  console.log(`  High: ${result.dayHigh}`);
  console.log(`  Low: ${result.dayLow}`);
  console.log(`  Close: ${result.lastClose || 'N/A'}`);
  console.log(`  Strike Hit: ${result.hit}`);
  if (result.hit) {
    console.log(`  Hit Time: ${result.hitTime}`);
    console.log(`  Hit Price: ${result.hitPrice}`);
  }
  
  // Build updated arrays using array builder functions
  console.log('\nBuilding updated arrays...');
  
  const updatedMaxFav = EW_buildMaxFavorableArray(
    existingArrays.maxFavorable, dayIndex, testConfig.strategy, testConfig.strike, result.dayHigh, result.dayLow
  );
  console.log(`  Updated Max_Favorable: ${JSON.stringify(updatedMaxFav)}`);
  
  const updatedMinUnfav = EW_buildMinUnfavorableArray(
    existingArrays.minUnfavorable, dayIndex, testConfig.strategy, testConfig.strike, result.dayHigh, result.dayLow
  );
  console.log(`  Updated Min_Unfavorable: ${JSON.stringify(updatedMinUnfav)}`);
  
  const updatedStrikeHit = EW_buildStrikeHitArray(
    existingArrays.strikeHit, dayIndex, testConfig.strategy, testConfig.strike, result.dayHigh, result.dayLow, result.hit
  );
  console.log(`  Updated Strike_Hit: ${JSON.stringify(updatedStrikeHit)}`);
  
  // Update indicator arrays if we have data
  let updatedIndicators = existingArrays.indicators;
  if (result.indicators) {
    updatedIndicators = EW_buildIndicatorArraysForDay(
      existingArrays.indicators, dayIndex, result.indicators
    );
    console.log('\nUpdated Indicator Arrays:');
    console.log(`  RSI: ${JSON.stringify(updatedIndicators.rsi)}`);
    console.log(`  SMA20: ${JSON.stringify(updatedIndicators.sma20)}`);
    console.log(`  Price vs SMA20: ${JSON.stringify(updatedIndicators.priceVsSMA20)}`);
    console.log(`  Price vs VWAP: ${JSON.stringify(updatedIndicators.priceVsVWAP)}`);
  }
  
  // Calculate Risk/Reward from arrays
  const riskReward = EW_calculateRiskRewardFromArrays(updatedMaxFav, updatedMinUnfav);
  console.log(`\nRisk/Reward: ${riskReward || 'N/A'}`);
  
  // Historical tracking
  const historicalHigh = result.dayHigh;
  const historicalLow = result.dayLow;
  console.log(`\nHistorical High: ${historicalHigh}`);
  console.log(`Historical Low: ${historicalLow}`);
  
  // Day check value (closing price)
  const dayCheckValue = result.lastClose ? result.lastClose.toFixed(2) : 
    ((parseFloat(result.dayHigh) + parseFloat(result.dayLow)) / 2).toFixed(2);
  console.log(`\nDay ${dayIndex} Check: ${dayCheckValue}`);
  
  // Summary of what would be updated in the sheet
  console.log('\n=== SUMMARY OF UPDATES ===');
  console.log('Arrays (stored as JSON):');
  console.log(`  Max_Favorable: ${EW_arrayToJson(updatedMaxFav)}`);
  console.log(`  Min_Unfavorable: ${EW_arrayToJson(updatedMinUnfav)}`);
  console.log(`  Strike_Hit: ${EW_arrayToJson(updatedStrikeHit)}`);
  console.log(`  Hit_RSI: ${EW_arrayToJson(updatedIndicators.rsi)}`);
  console.log(`  Hit_SMA20: ${EW_arrayToJson(updatedIndicators.sma20)}`);
  console.log(`  Hit_Price_vs_SMA20: ${EW_arrayToJson(updatedIndicators.priceVsSMA20)}`);
  console.log(`  Hit_Price_vs_VWAP: ${EW_arrayToJson(updatedIndicators.priceVsVWAP)}`);
  
  console.log('\nSingle Values:');
  console.log(`  Historical_High: ${historicalHigh}`);
  console.log(`  Historical_Low: ${historicalLow}`);
  console.log(`  Risk_Reward: ${riskReward || ''}`);
  console.log(`  Day${dayIndex}_Check: ${dayCheckValue}`);
  if (result.hit) {
    console.log(`  Hit_Date: ${result.hitDate.toISOString().split('T')[0]}`);
    console.log(`  First_Hit_Date: ${result.hitDate.toISOString().split('T')[0]} (if not already set)`);
  }
  
  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);
  console.log(`\nTest completed in ${duration} seconds`);
  console.log('=== END ACTIVE POSITION TRACKING TEST ===\n');
  
  return {
    success: true,
    ticker: testConfig.ticker,
    dayIndex: dayIndex,
    arrays: {
      maxFavorable: updatedMaxFav,
      minUnfavorable: updatedMinUnfav,
      strikeHit: updatedStrikeHit,
      indicators: updatedIndicators
    },
    riskReward: riskReward,
    dayCheck: dayCheckValue,
    duration: duration
  };
}