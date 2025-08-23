/**
 * Tracking Updates - Functions to populate plain text tracking columns
 * These functions analyze positions and update tracking data for success reports
 */

/**
 * Main function to update all tracking data across all strategy sheets
 * This populates the plain text columns used by success reports
 * Should be run periodically (e.g., daily via trigger)
 */
function EW_updateAllTrackingData() {
  EW_trace('TRACKING', 'Starting comprehensive tracking data update', true);
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  let totalUpdated = 0;
  let errors = [];
  
  for (const strategy of strategies) {
    try {
      const updated = EW_updateStrategyTracking(ss, strategy);
      if (updated > 0) {
        totalUpdated += updated;
        EW_trace('TRACKING', `Updated ${updated} rows in ${strategy}`);
      }
    } catch (e) {
      errors.push(`${strategy}: ${e.message}`);
      EW_trace('TRACKING', `Error updating ${strategy}: ${e.message}`, true);
    }
  }
  
  const msg = `Tracking update complete. Updated ${totalUpdated} positions across ${strategies.length} strategies.` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');
  
  EW_trace('TRACKING', msg, true);
  if (EW_isSpreadsheetEnvironment()) {
    EW_safeAlert('Tracking Update Complete', msg);
  }
}

/**
 * Update tracking data for a specific strategy sheet
 * @param {SpreadsheetApp.Spreadsheet} ss - The spreadsheet
 * @param {string} strategyName - Name of the strategy/sheet
 * @returns {number} Number of rows updated
 */
function EW_updateStrategyTracking(ss, strategyName) {
  const sheet = ss.getSheetByName(strategyName);
  if (!sheet || sheet.getLastRow() < 2) {
    return 0;
  }
  
  // Get header map
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Check required columns exist
  const requiredCols = ['tickerCol', 'runDateCol', 'strikeCol', 'expDateCol'];
  for (const col of requiredCols) {
    if (!hdrMap[col]) {
      EW_trace('TRACKING', `${strategyName}: Missing required column ${col}`);
      return 0;
    }
  }
  
  // Get all data
  const lastRow = sheet.getLastRow();
  const dataRange = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
  const data = dataRange.getValues();
  
  let updatedCount = 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0); // Normalize to start of day
  
  // Process each row
  data.forEach((row, rowIndex) => {
    try {
      const ticker = row[hdrMap.tickerCol - 1];
      const runDateStr = row[hdrMap.runDateCol - 1];
      const strike = parseFloat(row[hdrMap.strikeCol - 1]) || 0;
      const expDateStr = row[hdrMap.expDateCol - 1];
      
      if (!ticker || !runDateStr || !strike) return;
      
      // Parse dates
      const runDate = new Date(runDateStr);
      runDate.setHours(0, 0, 0, 0);
      const expDate = expDateStr ? new Date(expDateStr) : null;
      if (expDate) expDate.setHours(0, 0, 0, 0);
      
      // Calculate days since entry
      const daysSinceEntry = Math.floor((today - runDate) / (1000 * 60 * 60 * 24));
      
      // Get current data from formula columns (if available)
      const currentPrice = hdrMap.priceCol ? parseFloat(row[hdrMap.priceCol - 1]) || 0 : 0;
      const strikeHit = hdrMap.strikeHitCol ? row[hdrMap.strikeHitCol - 1] : '';
      const historicalHigh = hdrMap.historicalHighCol ? parseFloat(row[hdrMap.historicalHighCol - 1]) || 0 : 0;
      const historicalLow = hdrMap.historicalLowCol ? parseFloat(row[hdrMap.historicalLowCol - 1]) || 0 : 0;
      
      // Skip if no price data
      if (currentPrice === 0) return;
      
      // Update Hit_Date if strike was hit and not already recorded
      if (hdrMap.hitDateCol && (strikeHit === 'HIT' || strikeHit === 'FAVORABLE')) {
        const existingHitDate = row[hdrMap.hitDateCol - 1];
        if (!existingHitDate) {
          // This is first time hit - record today's date
          dataRange.getCell(rowIndex + 1, hdrMap.hitDateCol).setValue(today.toISOString().split('T')[0]);
          updatedCount++;
        }
      }
      
      // Update Day1_Check, Day2_Check, Day3_Check, Day5_Check
      const dayChecks = [
        { col: hdrMap.day1CheckCol, day: 1 },
        { col: hdrMap.day2CheckCol, day: 2 },
        { col: hdrMap.day3CheckCol, day: 3 },
        { col: hdrMap.day5CheckCol, day: 5 }
      ];
      
      for (const check of dayChecks) {
        if (check.col && daysSinceEntry >= check.day) {
          const existingCheck = row[check.col - 1];
          if (!existingCheck) {
            // Check if strike was hit by this day
            const hitStatus = EW_checkStrikeHit(strategyName, currentPrice, strike, historicalHigh, historicalLow);
            dataRange.getCell(rowIndex + 1, check.col).setValue(hitStatus);
            updatedCount++;
          }
        }
      }
      
      // Update Max_Favorable and Min_Unfavorable
      if (hdrMap.maxFavorableCol && historicalHigh > 0) {
        const maxFav = EW_calculateMaxFavorable(strategyName, strike, historicalHigh, historicalLow);
        const existing = row[hdrMap.maxFavorableCol - 1];
        if (!existing && maxFav !== null) {
          dataRange.getCell(rowIndex + 1, hdrMap.maxFavorableCol).setValue(maxFav);
          updatedCount++;
        }
      }
      
      if (hdrMap.minUnfavorableCol && historicalLow > 0) {
        const minUnfav = EW_calculateMinUnfavorable(strategyName, strike, historicalHigh, historicalLow);
        const existing = row[hdrMap.minUnfavorableCol - 1];
        if (!existing && minUnfav !== null) {
          dataRange.getCell(rowIndex + 1, hdrMap.minUnfavorableCol).setValue(minUnfav);
          updatedCount++;
        }
      }
      
      // Update Exp_Result if position has expired
      if (hdrMap.expResultCol && expDate && today >= expDate) {
        const existing = row[hdrMap.expResultCol - 1];
        if (!existing) {
          const expResult = EW_checkStrikeHit(strategyName, currentPrice, strike, historicalHigh, historicalLow);
          dataRange.getCell(rowIndex + 1, hdrMap.expResultCol).setValue(expResult);
          updatedCount++;
        }
      }
      
      // Calculate Profit_Potential (simplified - you may want to enhance this)
      if (hdrMap.profitPotentialCol) {
        const existing = row[hdrMap.profitPotentialCol - 1];
        if (!existing && strike > 0) {
          const potential = EW_calculateProfitPotential(strategyName, currentPrice, strike);
          if (potential !== null) {
            dataRange.getCell(rowIndex + 1, hdrMap.profitPotentialCol).setValue(potential);
            updatedCount++;
          }
        }
      }
      
      // Calculate Risk_Reward (simplified)
      if (hdrMap.riskRewardCol) {
        const existing = row[hdrMap.riskRewardCol - 1];
        if (!existing) {
          const premium = row[hdrMap.byName['premium'] - 1] || row[hdrMap.byName['call_ask'] - 1] || row[hdrMap.byName['put_ask'] - 1] || 0;
          if (premium > 0) {
            const rr = EW_calculateRiskReward(strategyName, currentPrice, strike, premium);
            if (rr !== null) {
              dataRange.getCell(rowIndex + 1, hdrMap.riskRewardCol).setValue(rr);
              updatedCount++;
            }
          }
        }
      }
      
    } catch (e) {
      EW_trace('TRACKING', `Error processing row ${rowIndex + 2} in ${strategyName}: ${e.message}`);
    }
  });
  
  // Force spreadsheet to save changes
  if (updatedCount > 0) {
    SpreadsheetApp.flush();
  }
  
  return updatedCount;
}

/**
 * Check if strike was hit based on strategy type
 * @param {string} strategy - Strategy name
 * @param {number} currentPrice - Current stock price
 * @param {number} strike - Strike price
 * @param {number} historicalHigh - Historical high since entry
 * @param {number} historicalLow - Historical low since entry
 * @returns {string} 'HIT', 'NO', 'FAVORABLE', 'UNFAVORABLE', or ''
 */
function EW_checkStrikeHit(strategy, currentPrice, strike, historicalHigh, historicalLow) {
  if (!currentPrice || !strike) return '';
  
  const strategyUpper = strategy.toUpperCase();
  
  // For long calls and bullish strategies
  if (strategyUpper.includes('LONG CALL') || strategyUpper.includes('BULL')) {
    // Use historical high to check if ever hit
    const checkPrice = historicalHigh || currentPrice;
    return checkPrice >= strike ? 'HIT' : 'NO';
  }
  
  // For long puts and bearish strategies
  if (strategyUpper.includes('LONG PUT') || strategyUpper.includes('BEAR')) {
    // Use historical low to check if ever hit
    const checkPrice = historicalLow || currentPrice;
    return checkPrice <= strike ? 'HIT' : 'NO';
  }
  
  // For short calls and covered calls
  if (strategyUpper.includes('SHORT CALL') || strategyUpper.includes('COVERED')) {
    const checkPrice = historicalHigh || currentPrice;
    return checkPrice < strike ? 'FAVORABLE' : 'UNFAVORABLE';
  }
  
  // For short puts
  if (strategyUpper.includes('SHORT PUT')) {
    const checkPrice = historicalLow || currentPrice;
    return checkPrice > strike ? 'FAVORABLE' : 'UNFAVORABLE';
  }
  
  return '';
}

/**
 * Calculate maximum favorable excursion
 * @param {string} strategy - Strategy name
 * @param {number} strike - Strike price
 * @param {number} historicalHigh - Historical high
 * @param {number} historicalLow - Historical low
 * @returns {number|null} Max favorable percentage or null
 */
function EW_calculateMaxFavorable(strategy, strike, historicalHigh, historicalLow) {
  if (!strike) return null;
  
  const strategyUpper = strategy.toUpperCase();
  
  if (strategyUpper.includes('LONG CALL') || strategyUpper.includes('BULL')) {
    // Favorable is when price goes up
    return historicalHigh ? ((historicalHigh - strike) / strike * 100).toFixed(2) : null;
  }
  
  if (strategyUpper.includes('LONG PUT') || strategyUpper.includes('BEAR')) {
    // Favorable is when price goes down
    return historicalLow ? ((strike - historicalLow) / strike * 100).toFixed(2) : null;
  }
  
  return null;
}

/**
 * Calculate minimum unfavorable excursion
 * @param {string} strategy - Strategy name
 * @param {number} strike - Strike price
 * @param {number} historicalHigh - Historical high
 * @param {number} historicalLow - Historical low
 * @returns {number|null} Min unfavorable percentage or null
 */
function EW_calculateMinUnfavorable(strategy, strike, historicalHigh, historicalLow) {
  if (!strike) return null;
  
  const strategyUpper = strategy.toUpperCase();
  
  if (strategyUpper.includes('LONG CALL') || strategyUpper.includes('BULL')) {
    // Unfavorable is when price goes down
    return historicalLow ? ((strike - historicalLow) / strike * 100).toFixed(2) : null;
  }
  
  if (strategyUpper.includes('LONG PUT') || strategyUpper.includes('BEAR')) {
    // Unfavorable is when price goes up
    return historicalHigh ? ((historicalHigh - strike) / strike * 100).toFixed(2) : null;
  }
  
  return null;
}

/**
 * Calculate profit potential
 * @param {string} strategy - Strategy name
 * @param {number} currentPrice - Current price
 * @param {number} strike - Strike price
 * @returns {number|null} Profit potential percentage or null
 */
function EW_calculateProfitPotential(strategy, currentPrice, strike) {
  if (!currentPrice || !strike) return null;
  
  const strategyUpper = strategy.toUpperCase();
  
  if (strategyUpper.includes('LONG CALL') || strategyUpper.includes('BULL')) {
    // Potential if price rises 10%
    const targetPrice = currentPrice * 1.1;
    return ((targetPrice - strike) / strike * 100).toFixed(2);
  }
  
  if (strategyUpper.includes('LONG PUT') || strategyUpper.includes('BEAR')) {
    // Potential if price falls 10%
    const targetPrice = currentPrice * 0.9;
    return ((strike - targetPrice) / strike * 100).toFixed(2);
  }
  
  return null;
}

/**
 * Calculate risk/reward ratio
 * @param {string} strategy - Strategy name
 * @param {number} currentPrice - Current price
 * @param {number} strike - Strike price
 * @param {number} premium - Option premium paid
 * @returns {number|null} Risk/reward ratio or null
 */
function EW_calculateRiskReward(strategy, currentPrice, strike, premium) {
  if (!currentPrice || !strike || !premium) return null;
  
  const strategyUpper = strategy.toUpperCase();
  
  if (strategyUpper.includes('LONG CALL') || strategyUpper.includes('LONG PUT')) {
    // Risk is the premium paid
    // Reward is potential profit at 10% move
    const risk = premium;
    let reward = 0;
    
    if (strategyUpper.includes('LONG CALL')) {
      const targetPrice = currentPrice * 1.1;
      reward = Math.max(0, targetPrice - strike - premium);
    } else {
      const targetPrice = currentPrice * 0.9;
      reward = Math.max(0, strike - targetPrice - premium);
    }
    
    return risk > 0 ? (reward / risk).toFixed(2) : null;
  }
  
  return null;
}

// Note: Trigger functions have been moved to 03_Triggers.js