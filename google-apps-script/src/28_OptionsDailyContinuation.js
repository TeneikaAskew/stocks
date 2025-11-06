/**
 * Options Daily Continuation - Update historical tracking for active positions
 *
 * This function runs daily (ideally at 5 PM) to update existing positions with:
 * - Daily OHLC data for options premiums
 * - Strike_Hit array tracking
 * - Max_Favorable and Min_Unfavorable arrays
 * - Day0-Day5 closing premium checks
 * - Technical indicators at strike hit
 * - Expiration results when positions expire
 *
 * Similar to 09_HistoricalBackfill.js but for OPTIONS data
 */

/**
 * Main daily continuation function
 * Updates all active option positions across all strategy sheets
 */
function EW_updateOptionsDailyContinuation() {
  const startTime = new Date();
  EW_trace('OPTIONS_CONTINUATION', 'Starting daily options continuation update', true);

  const ss = SpreadsheetApp.getActive();

  // Find all "*Options" sheets (Long Calls Options, Long Puts Options, etc.)
  const allSheets = ss.getSheets();
  const optionSheets = allSheets.filter(sheet => sheet.getName().includes('Options'));

  if (optionSheets.length === 0) {
    EW_trace('OPTIONS_CONTINUATION', 'No options tracking sheets found', true);
    return;
  }

  let totalUpdated = 0;
  let errors = [];

  for (const sheet of optionSheets) {
    try {
      const updated = EW_updateOptionsSheetContinuation(sheet);
      if (updated > 0) {
        totalUpdated += updated;
        EW_trace('OPTIONS_CONTINUATION', `Updated ${updated} positions in ${sheet.getName()}`, true);
      }
    } catch (e) {
      const errorMsg = `${sheet.getName()}: ${e.message}`;
      errors.push(errorMsg);
      EW_trace('OPTIONS_CONTINUATION', `Error updating ${sheet.getName()}: ${e.message}`, true);
    }
  }

  const elapsed = Math.round((new Date() - startTime) / 1000);
  const msg = `Daily continuation complete in ${elapsed}s. Updated ${totalUpdated} positions across ${optionSheets.length} sheets.` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.slice(0, 5).join('\n')}` : '');

  EW_trace('OPTIONS_CONTINUATION', msg, true);

  if (EW_isSpreadsheetEnvironment()) {
    SpreadsheetApp.getUi().alert('Options Continuation Complete', msg, SpreadsheetApp.getUi().ButtonSet.OK);
  }
}

/**
 * Update a single options sheet with daily continuation data
 * @param {Sheet} sheet - The options tracking sheet
 * @returns {number} Number of positions updated
 */
function EW_updateOptionsSheetContinuation(sheet) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return 0;

  // Get header map
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_buildOptionsHeaderMap(headers);

  // Validate required columns
  if (!hdrMap.dateCol || !hdrMap.tickerCol || !hdrMap.strikeCol || !hdrMap.typeCol || !hdrMap.expDateCol) {
    EW_trace('OPTIONS_CONTINUATION', `${sheet.getName()}: Missing required columns`, true);
    return 0;
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // Get all data
  const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();

  let updatedCount = 0;
  const positionsToUpdate = [];

  // Find positions that need updates (not expired, and were tracked within last 5 trading days)
  for (let i = 0; i < data.length; i++) {
    const row = data[i];
    const entryDate = new Date(row[hdrMap.dateCol - 1]);
    entryDate.setHours(0, 0, 0, 0);

    const expDate = new Date(row[hdrMap.expDateCol - 1]);
    expDate.setHours(0, 0, 0, 0);

    // Skip if expired
    if (expDate < today) continue;

    // Calculate days since entry
    const daysSinceEntry = Math.floor((today - entryDate) / (1000 * 60 * 60 * 24));

    // Only update positions within first 5 days (Day0-Day5)
    if (daysSinceEntry < 0 || daysSinceEntry > 5) continue;

    const ticker = String(row[hdrMap.tickerCol - 1]);
    const strike = parseFloat(row[hdrMap.strikeCol - 1]);
    const optionType = String(row[hdrMap.typeCol - 1]);
    const entryPremium = hdrMap.entryPremiumCol ? parseFloat(row[hdrMap.entryPremiumCol - 1]) : null;

    if (!ticker || isNaN(strike)) continue;

    positionsToUpdate.push({
      rowNum: i + 2,
      ticker: ticker,
      strike: strike,
      optionType: optionType,
      entryDate: entryDate,
      expDate: expDate,
      daysSinceEntry: daysSinceEntry,
      entryPremium: entryPremium,
      existingRow: row
    });
  }

  if (positionsToUpdate.length === 0) {
    EW_trace('OPTIONS_CONTINUATION', `${sheet.getName()}: No active positions to update`, false);
    return 0;
  }

  EW_trace('OPTIONS_CONTINUATION', `${sheet.getName()}: Updating ${positionsToUpdate.length} active positions`, true);

  // Batch fetch all option premiums
  const premiumDataMap = EW_fetchOptionPremiumsBatch(positionsToUpdate);

  // Batch fetch all underlying stock OHLC data
  const stockDataMap = EW_fetchStockOHLCBatch(positionsToUpdate);

  // Process each position
  for (const position of positionsToUpdate) {
    try {
      const optionSymbol = EW_buildOptionSymbol(
        position.ticker,
        position.expDate,
        position.optionType,
        position.strike
      );

      const premiumData = premiumDataMap[optionSymbol];
      const stockData = stockDataMap[position.ticker];

      if (!premiumData || premiumData.price === null) {
        EW_trace('OPTIONS_CONTINUATION', `  ⚠ ${position.ticker} $${position.strike}: No premium data`, false);
        continue;
      }

      // Update the row with new daily data
      const updated = EW_updateOptionsDailyData(
        sheet,
        hdrMap,
        position,
        premiumData,
        stockData,
        today
      );

      if (updated) {
        updatedCount++;
        EW_trace('OPTIONS_CONTINUATION', `  ✓ ${position.ticker} $${position.strike} Day ${position.daysSinceEntry}: Premium $${premiumData.price.toFixed(2)}`, false);
      }

    } catch (error) {
      EW_trace('OPTIONS_CONTINUATION', `  ✗ ${position.ticker} $${position.strike}: ${error.message}`, true);
    }
  }

  if (updatedCount > 0) {
    SpreadsheetApp.flush();
  }

  return updatedCount;
}

/**
 * Update a single position's daily tracking data
 * @param {Sheet} sheet - The sheet
 * @param {Object} hdrMap - Header map
 * @param {Object} position - Position info
 * @param {Object} premiumData - Premium data from API
 * @param {Object} stockData - Stock OHLC data
 * @param {Date} today - Today's date
 * @returns {boolean} True if updated
 */
function EW_updateOptionsDailyData(sheet, hdrMap, position, premiumData, stockData, today) {
  let updated = false;
  const row = position.rowNum;
  const dayIndex = position.daysSinceEntry;

  // 1. Update Day0-Day5 Check columns with closing premium
  const dayCheckCols = [
    hdrMap.day0CheckCol,
    hdrMap.day1CheckCol,
    hdrMap.day2CheckCol,
    hdrMap.day3CheckCol,
    hdrMap.day4CheckCol,
    hdrMap.day5CheckCol
  ];

  if (dayIndex >= 0 && dayIndex <= 5 && dayCheckCols[dayIndex]) {
    const existingValue = position.existingRow[dayCheckCols[dayIndex] - 1];
    if (!existingValue || existingValue === '') {
      // Store closing premium (regularMarketPrice is the closing price)
      sheet.getRange(row, dayCheckCols[dayIndex]).setValue(premiumData.price);
      updated = true;
    }
  }

  // 2. Update OHLC_Volume array
  if (hdrMap.ohlcVolumeCol) {
    const existingOHLC = position.existingRow[hdrMap.ohlcVolumeCol - 1];
    const existingArray = EW_parseArrayFromCell(existingOHLC);

    // Create new OHLC entry for today
    const newOHLCEntry = {
      o: premiumData.dayOpen ? parseFloat(premiumData.dayOpen).toFixed(2) : null,
      h: premiumData.dayHigh ? parseFloat(premiumData.dayHigh).toFixed(2) : null,
      l: premiumData.dayLow ? parseFloat(premiumData.dayLow).toFixed(2) : null,
      c: premiumData.price ? parseFloat(premiumData.price).toFixed(2) : null,
      v: premiumData.volume || 0,
      src: 'YAHOO'
    };

    // Merge with existing array
    const updatedArray = [...existingArray];
    updatedArray[dayIndex] = newOHLCEntry;

    sheet.getRange(row, hdrMap.ohlcVolumeCol).setValue(JSON.stringify(updatedArray));
    updated = true;
  }

  // 3. Update Strike_Hit array
  if (hdrMap.strikeHitCol && position.entryPremium) {
    const existingStrikeHit = position.existingRow[hdrMap.strikeHitCol - 1];
    const existingArray = EW_parseStrikeHitArray(existingStrikeHit);

    // Calculate profit/loss at today's closing premium
    const pnl = (premiumData.price - position.entryPremium) * 100;
    const pnlPct = (pnl / (position.entryPremium * 100)) * 100;

    // Store percentage gain/loss
    const updatedArray = [...existingArray];
    updatedArray[dayIndex] = pnlPct.toFixed(6);

    sheet.getRange(row, hdrMap.strikeHitCol).setValue(JSON.stringify(updatedArray));
    updated = true;
  }

  // 4. Update Max_Favorable array (best profit potential each day)
  if (hdrMap.maxFavorableCol && position.entryPremium && premiumData.dayHigh) {
    const existingMax = position.existingRow[hdrMap.maxFavorableCol - 1];
    const existingArray = EW_parseArrayFromCell(existingMax);

    // Calculate best possible profit at day's high
    const maxPnl = (premiumData.dayHigh - position.entryPremium) * 100;
    const maxPnlPct = (maxPnl / (position.entryPremium * 100)) * 100;

    const updatedArray = [...existingArray];
    updatedArray[dayIndex] = Math.max(maxPnlPct, 0).toFixed(6);

    sheet.getRange(row, hdrMap.maxFavorableCol).setValue(JSON.stringify(updatedArray));
    updated = true;
  }

  // 5. Update Min_Unfavorable array (worst loss each day)
  if (hdrMap.minUnfavorableCol && position.entryPremium && premiumData.dayLow) {
    const existingMin = position.existingRow[hdrMap.minUnfavorableCol - 1];
    const existingArray = EW_parseArrayFromCell(existingMin);

    // Calculate worst possible loss at day's low
    const minPnl = (premiumData.dayLow - position.entryPremium) * 100;
    const minPnlPct = (minPnl / (position.entryPremium * 100)) * 100;

    const updatedArray = [...existingArray];
    updatedArray[dayIndex] = Math.min(minPnlPct, 0).toFixed(6);

    sheet.getRange(row, hdrMap.minUnfavorableCol).setValue(JSON.stringify(updatedArray));
    updated = true;
  }

  // 6. Update Hit_Date (day when first became profitable)
  if (hdrMap.hitDateCol) {
    const existingHitDate = position.existingRow[hdrMap.hitDateCol - 1];
    if (!existingHitDate || existingHitDate === '') {
      // Check if profitable today
      if (position.entryPremium && premiumData.price > position.entryPremium) {
        sheet.getRange(row, hdrMap.hitDateCol).setValue(dayIndex);
        updated = true;
      }
    }
  }

  // 7. Check if position expired today and update Exp_Result
  if (hdrMap.expResultCol && position.expDate.getTime() === today.getTime()) {
    const existingExpResult = position.existingRow[hdrMap.expResultCol - 1];
    if (!existingExpResult || existingExpResult === '') {
      if (position.entryPremium) {
        const finalPnl = (premiumData.price - position.entryPremium) * 100;
        sheet.getRange(row, hdrMap.expResultCol).setValue(finalPnl.toFixed(2));
        updated = true;
      }
    }
  }

  // 8. Update Risk_Reward calculation
  if (hdrMap.riskRewardCol && position.entryPremium) {
    const existingRR = position.existingRow[hdrMap.riskRewardCol - 1];
    if (!existingRR || existingRR === '') {
      // Risk = premium paid, Reward = potential profit at strike
      // For calls: reward = (strike distance / premium)
      // Simplified calculation
      const riskReward = ((position.strike * 0.1) / position.entryPremium).toFixed(2);
      sheet.getRange(row, hdrMap.riskRewardCol).setValue(riskReward);
      updated = true;
    }
  }

  return updated;
}

/**
 * Build header map for options sheet
 * @param {Array} headers - Header row
 * @returns {Object} Map of column names to indices
 */
function EW_buildOptionsHeaderMap(headers) {
  const map = {};

  for (let i = 0; i < headers.length; i++) {
    const header = String(headers[i]).trim();

    // Basic columns
    if (header === 'Date') map.dateCol = i + 1;
    if (header === 'Ticker') map.tickerCol = i + 1;
    if (header === 'Strike') map.strikeCol = i + 1;
    if (header === 'Type') map.typeCol = i + 1;
    if (header === 'ExpDate') map.expDateCol = i + 1;

    // Strike Hit tracking
    if (header === 'Strike_Hit') map.strikeHitCol = i + 1;
    if (header === 'Hit_Date') map.hitDateCol = i + 1;
    if (header === 'Max_Favorable') map.maxFavorableCol = i + 1;
    if (header === 'Min_Unfavorable') map.minUnfavorableCol = i + 1;

    // Daily check columns
    if (header === 'Day0_Check') map.day0CheckCol = i + 1;
    if (header === 'Day1_Check') map.day1CheckCol = i + 1;
    if (header === 'Day2_Check') map.day2CheckCol = i + 1;
    if (header === 'Day3_Check') map.day3CheckCol = i + 1;
    if (header === 'Day4_Check') map.day4CheckCol = i + 1;
    if (header === 'Day5_Check') map.day5CheckCol = i + 1;

    // Expiration
    if (header === 'Exp_Result') map.expResultCol = i + 1;
    if (header === 'Risk_Reward') map.riskRewardCol = i + 1;

    // OHLC and Entry premium
    if (header === 'OHLC_Volume') map.ohlcVolumeCol = i + 1;
    if (header === 'Entry_Premium') map.entryPremiumCol = i + 1;
  }

  return map;
}

/**
 * Parse array from cell (handles JSON arrays)
 * Reuses helper from 13_ArrayBuilders.js
 */
function EW_parseArrayFromCell(cellValue) {
  if (!cellValue) return [];

  if (Array.isArray(cellValue)) return cellValue;

  if (typeof cellValue === 'string') {
    // Try JSON parsing first
    if (cellValue.startsWith('[')) {
      try {
        return JSON.parse(cellValue);
      } catch (e) {
        return [];
      }
    }

    // Handle comma-separated format
    if (cellValue.includes(',')) {
      return cellValue.split(',').map(v => v.trim());
    }
  }

  // Single value - return as array
  return [cellValue];
}
