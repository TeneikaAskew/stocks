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
      const newStatus = result.hit ? 'HIT' : 'NO';
      const currentStatus = data[result.rowIndex][hdrMap.strikeHitCol - 1];
      
      // Log if fallback was used
      if (result.fallbackUsed) {
        console.log(`ACTIVE TRACKING: ${strategyName} - ${result.ticker} used ${result.fallbackUsed} interval (fallback)`);
        Logger.log(`ACTIVE TRACKING FALLBACK: ${strategyName}/${result.ticker} used ${result.fallbackUsed} interval`);
      }
      
      // Calculate percentage move from Day0 to strike
      let percentMove = null;
      const position = positionsToCheck[results.indexOf(result)];
      const strike = position.strike || position.longStrike || 0;
      
      // Get Day0 price by fetching historical data for the entry date
      if (strike && position.startDate) {
        try {
          // Fetch day 0 closing price
          const entryDateData = EW_getYahooHistoricalRange(
            position.ticker,
            position.startDate,
            position.startDate
          );
          
          if (entryDateData && entryDateData.length > 0 && entryDateData[0].close) {
            const day0Price = entryDateData[0].close;
            const strategyUpper = position.strategy.toUpperCase();
            
            if (strategyUpper.includes('BULL') || strategyUpper.includes('LONG CALL')) {
              // For bullish strategies: (day0Price - strike) / strike (positive when above strike)
              percentMove = ((day0Price - strike) / strike).toFixed(6);
            } else if (strategyUpper.includes('BEAR') || strategyUpper.includes('LONG PUT')) {
              // For bearish strategies: (strike - day0Price) / strike (positive when below strike)
              percentMove = ((strike - day0Price) / strike).toFixed(6);
            } else {
              // Default for other strategies
              percentMove = ((day0Price - strike) / strike).toFixed(6);
            }
            
            console.log(`ACTIVE TRACKING: ${position.ticker} - Strike: ${strike}, Price: ${day0Price}, Move: ${percentMove}`);
          }
        } catch (e) {
          console.log(`ACTIVE TRACKING: Could not fetch Day0 price for ${position.ticker}: ${e.message}`);
        }
      }
      
      // Update Strike_Hit with array format
      let updatedValue;
      if (percentMove !== null) {
        // Append to existing array or create new one (no % suffix)
        updatedValue = EW_appendStrikeHit(currentStatus, percentMove);
      } else {
        // Fallback - create array with status
        updatedValue = EW_appendStrikeHit(currentStatus, newStatus);
      }
      
      // Only update if value changed
      if (currentStatus !== updatedValue) {
        dataRange.getCell(result.rowIndex + 1, hdrMap.strikeHitCol).setValue(updatedValue);
        
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
          
          // Update indicator arrays - always append for daily tracking
          if (result.indicators) {
            const ind = result.indicators;
            
            // Append to each indicator array
            if (hdrMap.hitRSICol && ind.rsi !== null) {
              const currentValue = row[hdrMap.hitRSICol - 1] || '';
              const updatedValue = EW_appendIndicatorValue(currentValue, ind.rsi);
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitRSICol).setValue(updatedValue);
            }
            if (hdrMap.hitSMA20Col && ind.sma20 !== null) {
              const currentValue = row[hdrMap.hitSMA20Col - 1] || '';
              const updatedValue = EW_appendIndicatorValue(currentValue, ind.sma20);
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitSMA20Col).setValue(updatedValue);
            }
            if (hdrMap.hitSMA50Col && ind.sma50 !== null) {
              const currentValue = row[hdrMap.hitSMA50Col - 1] || '';
              const updatedValue = EW_appendIndicatorValue(currentValue, ind.sma50);
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitSMA50Col).setValue(updatedValue);
            }
            if (hdrMap.hitEMA9Col && ind.ema9 !== null) {
              const currentValue = row[hdrMap.hitEMA9Col - 1] || '';
              const updatedValue = EW_appendIndicatorValue(currentValue, ind.ema9);
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitEMA9Col).setValue(updatedValue);
            }
            if (hdrMap.hitEMA21Col && ind.ema21 !== null) {
              const currentValue = row[hdrMap.hitEMA21Col - 1] || '';
              const updatedValue = EW_appendIndicatorValue(currentValue, ind.ema21);
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitEMA21Col).setValue(updatedValue);
            }
            if (hdrMap.hitVWAPCol && ind.vwap !== null) {
              const currentValue = row[hdrMap.hitVWAPCol - 1] || '';
              const updatedValue = EW_appendIndicatorValue(currentValue, ind.vwap);
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitVWAPCol).setValue(updatedValue);
            }
            if (hdrMap.hitRVOLCol && ind.rvol !== null) {
              const currentValue = row[hdrMap.hitRVOLCol - 1] || '';
              const updatedValue = EW_appendIndicatorValue(currentValue, ind.rvol);
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitRVOLCol).setValue(updatedValue);
            }
            if (hdrMap.hitATRCol && ind.atr !== null) {
              const currentValue = row[hdrMap.hitATRCol - 1] || '';
              const updatedValue = EW_appendIndicatorValue(currentValue, ind.atr.toFixed(4));
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitATRCol).setValue(updatedValue);
            }
            if (hdrMap.hitPriceVsSMA20Col && ind.priceVsSMA20 !== null) {
              const currentValue = row[hdrMap.hitPriceVsSMA20Col - 1] || '';
              const updatedValue = EW_appendIndicatorValue(currentValue, ind.priceVsSMA20.toFixed(2) + '%');
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitPriceVsSMA20Col).setValue(updatedValue);
            }
            if (hdrMap.hitPriceVsVWAPCol && ind.priceVsVWAP !== null) {
              const currentValue = row[hdrMap.hitPriceVsVWAPCol - 1] || '';
              const updatedValue = EW_appendIndicatorValue(currentValue, ind.priceVsVWAP.toFixed(2) + '%');
              dataRange.getCell(result.rowIndex + 1, hdrMap.hitPriceVsVWAPCol).setValue(updatedValue);
            }
            
            console.log(`ACTIVE TRACKING: Updated indicator arrays for ${result.ticker}`);
          }
        }
        
        updatedCount++;
        console.log(`ACTIVE TRACKING: ${strategyName} - Updated ${result.ticker} Strike_Hit`);
      }
      
      // Additional tracking updates (from 4:30 PM function)
      const row = position.row;
      
      // Update Day0_Check through Day5_Check
      const dayChecks = [
        { col: hdrMap.day0CheckCol, day: 0 },
        { col: hdrMap.day1CheckCol, day: 1 },
        { col: hdrMap.day2CheckCol, day: 2 },
        { col: hdrMap.day3CheckCol, day: 3 },
        { col: hdrMap.day4CheckCol, day: 4 },
        { col: hdrMap.day5CheckCol, day: 5 }
      ];
      
      for (const check of dayChecks) {
        if (check.col && position.daysSinceEntry >= check.day) {
          const existingCheck = row[check.col - 1];
          if (!existingCheck) {
            // Always show the actual closing price
            let dayCheckValue = 'None';
            
            // Use the last close price if available, otherwise average of high/low
            if (result.lastClose) {
              dayCheckValue = result.lastClose.toFixed(2);
            } else if (result.dayHigh && result.dayLow) {
              // If no close price, use average of high and low
              const avgPrice = (parseFloat(result.dayHigh) + parseFloat(result.dayLow)) / 2;
              dayCheckValue = avgPrice.toFixed(2);
            }
            
            dataRange.getCell(result.rowIndex + 1, check.col).setValue(dayCheckValue);
            updatedCount++;
          }
        }
      }
      
      // Update Max_Favorable and Min_Unfavorable based on Yahoo data
      if (hdrMap.maxFavorableCol && result.dayHigh) {
        const maxFav = EW_calculateMaxFavorable(strategyName, position.strike || position.longStrike, result.dayHigh, result.dayLow);
        const existing = row[hdrMap.maxFavorableCol - 1];
        if (!existing && maxFav !== null) {
          dataRange.getCell(result.rowIndex + 1, hdrMap.maxFavorableCol).setValue(maxFav);
          updatedCount++;
        }
      }
      
      if (hdrMap.minUnfavorableCol && result.dayLow) {
        const minUnfav = EW_calculateMinUnfavorable(strategyName, position.strike || position.longStrike, result.dayHigh, result.dayLow);
        const existing = row[hdrMap.minUnfavorableCol - 1];
        if (!existing && minUnfav !== null) {
          dataRange.getCell(result.rowIndex + 1, hdrMap.minUnfavorableCol).setValue(minUnfav);
          updatedCount++;
        }
      }
      
      // Update Exp_Result if position has expired
      if (hdrMap.expResultCol && position.expDate && today >= position.expDate) {
        const existing = row[hdrMap.expResultCol - 1];
        if (!existing && result.lastClose) {
          // Store the closing price at expiration
          const expResult = result.lastClose.toFixed(2);
          dataRange.getCell(result.rowIndex + 1, hdrMap.expResultCol).setValue(expResult);
          updatedCount++;
        }
      }
      
      // Removed Profit_Potential calculation - duplicates Max_Favorable
      
      // Calculate and update Risk_Reward if we have both favorable and unfavorable
      if (hdrMap.riskRewardCol && hdrMap.maxFavorableCol && hdrMap.minUnfavorableCol) {
        const existing = row[hdrMap.riskRewardCol - 1];
        if (!existing) {
          const favorable = parseFloat(row[hdrMap.maxFavorableCol - 1]) || 0;
          const unfavorable = parseFloat(row[hdrMap.minUnfavorableCol - 1]) || 0;
          if (favorable > 0 && unfavorable > 0) {
            const riskReward = (favorable / unfavorable).toFixed(2);
            dataRange.getCell(result.rowIndex + 1, hdrMap.riskRewardCol).setValue(riskReward);
            updatedCount++;
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