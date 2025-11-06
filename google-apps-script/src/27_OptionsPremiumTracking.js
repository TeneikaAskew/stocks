/**
 * Options Daily Tracking - Using ACTUAL Yahoo Finance Options Premiums
 *
 * Fetches real options premium data from Yahoo Finance quote API
 * (NOT calculated intrinsic value - actual market premiums!)
 *
 * For each position:
 * 1. Build option symbol: ROKU251107C00060000 format
 * 2. Fetch actual premium from Yahoo: regularMarketPrice, dayHigh, dayLow, bid, ask
 * 3. Calculate real P/L based on premium changes
 * 4. Write to "Long Calls Options" sheet
 *
 * Yahoo Finance Options Quote API:
 * https://query1.finance.yahoo.com/v7/finance/quote?symbols=ROKU251107C00060000
 *
 * Response includes:
 * - regularMarketPrice: Current premium
 * - regularMarketDayHigh/Low: Day's high/low premium
 * - bid/ask: Current bid-ask spread
 * - regularMarketOpen: Opening premium
 * - strike, expireDate, underlyingSymbol
 *
 * Run once daily at 5 PM to capture day's high/low/close premium data.
 */

/**
 * Update options tracking with actual premium data
 * Runs for all active positions in "Long Calls" sheet
 */
function EW_updateOptionsPremiums() {
  const startTime = new Date();
  EW_trace('OPTIONS_PREMIUM', 'Starting options premium update', true);

  const ss = SpreadsheetApp.getActive();
  const sourceSheet = ss.getSheetByName('Long Calls');

  if (!sourceSheet) {
    EW_trace('OPTIONS_PREMIUM', 'Long Calls sheet not found', true);
    return;
  }

  // Get or create output sheet
  const outputSheetName = 'Long Calls Options';
  let outputSheet = ss.getSheetByName(outputSheetName);

  if (!outputSheet) {
    outputSheet = ss.insertSheet(outputSheetName);
    EW_setupOptionsPremiumSheet(outputSheet);
  }

  // Read positions from source sheet
  const positions = EW_readOptionsPositions(sourceSheet);

  if (positions.length === 0) {
    EW_trace('OPTIONS_PREMIUM', 'No positions to process', true);
    return;
  }

  EW_trace('OPTIONS_PREMIUM', `Processing ${positions.length} positions`, true);

  let processed = 0;
  let errors = [];

  // Fetch all premiums in one batch call (much more efficient!)
  const premiumDataMap = EW_fetchOptionPremiumsBatch(positions);

  // Process each position with fetched data
  for (let i = 0; i < positions.length; i++) {
    const position = positions[i];
    const optionSymbol = EW_buildOptionSymbol(
      position.ticker,
      position.expDate,
      position.optionType,
      position.strike
    );

    try {
      const premiumData = premiumDataMap[optionSymbol];

      if (premiumData && premiumData.price !== null) {
        EW_writeOptionPremiumRow(outputSheet, position, premiumData);
        processed++;
        EW_trace('OPTIONS_PREMIUM', `  ✓ ${position.ticker} $${position.strike}: Premium $${premiumData.price.toFixed(2)}, Day Range $${premiumData.dayLow.toFixed(2)}-$${premiumData.dayHigh.toFixed(2)}`, false);
      } else {
        EW_trace('OPTIONS_PREMIUM', `  ⚠ ${position.ticker} $${position.strike}: No premium data available`, false);
      }

    } catch (error) {
      const errorMsg = `${position.ticker} $${position.strike}: ${error.message}`;
      errors.push(errorMsg);
      EW_trace('OPTIONS_PREMIUM', `  ✗ Error: ${errorMsg}`, true);
    }
  }

  // Sort by date descending (most recent first)
  if (processed > 0) {
    const lastRow = outputSheet.getLastRow();
    if (lastRow > 1) {
      const dataRange = outputSheet.getRange(2, 1, lastRow - 1, outputSheet.getLastColumn());
      dataRange.sort({column: 1, ascending: false}); // Sort by date
    }
    SpreadsheetApp.flush();
  }

  const elapsed = Math.round((new Date() - startTime) / 1000);
  const msg = `Premium update complete in ${elapsed}s. Processed ${processed} of ${positions.length} positions.` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.slice(0, 5).join('\n')}` : '');

  EW_trace('OPTIONS_PREMIUM', msg, true);

  if (EW_isSpreadsheetEnvironment()) {
    SpreadsheetApp.getUi().alert('Premium Update Complete', msg, SpreadsheetApp.getUi().ButtonSet.OK);
  }
}

/**
 * Setup output sheet with premium tracking columns
 * @param {Sheet} sheet - The output sheet
 */
function EW_setupOptionsPremiumSheet(sheet) {
  const headers = [
    'Date',
    'Ticker',
    'Strike',
    'Type',
    'ExpDate',
    'Premium',
    'Day_High',
    'Day_Low',
    'Day_Open',
    'Bid',
    'Ask',
    'Spread',
    'Volume',
    'Open_Interest',
    'Entry_Premium',
    'PnL',
    'PnL_Percent',
    'Max_Profit',
    'Max_Loss',
    'Was_Profitable',
    'Days_To_Exp'
  ];

  const headerRange = sheet.getRange(1, 1, 1, headers.length);
  headerRange.setValues([headers]);
  headerRange.setFontWeight('bold');
  headerRange.setBackground('#4A86E8');
  headerRange.setFontColor('white');

  // Set column widths
  sheet.setColumnWidth(1, 100);  // Date
  sheet.setColumnWidth(2, 80);   // Ticker
  sheet.setColumnWidth(3, 70);   // Strike
  sheet.setColumnWidth(4, 60);   // Type
  sheet.setColumnWidth(5, 100);  // ExpDate
  sheet.setColumnWidth(6, 90);   // Premium
  sheet.setColumnWidth(7, 90);   // Day_High
  sheet.setColumnWidth(8, 90);   // Day_Low
  sheet.setColumnWidth(9, 90);   // Day_Open
  sheet.setColumnWidth(10, 80);  // Bid
  sheet.setColumnWidth(11, 80);  // Ask
  sheet.setColumnWidth(12, 80);  // Spread
  sheet.setColumnWidth(13, 80);  // Volume
  sheet.setColumnWidth(14, 100); // Open_Interest
  sheet.setColumnWidth(15, 110); // Entry_Premium
  sheet.setColumnWidth(16, 90);  // PnL
  sheet.setColumnWidth(17, 100); // PnL_Percent
  sheet.setColumnWidth(18, 100); // Max_Profit
  sheet.setColumnWidth(19, 100); // Max_Loss
  sheet.setColumnWidth(20, 110); // Was_Profitable
  sheet.setColumnWidth(21, 90);  // Days_To_Exp

  // Freeze header row
  sheet.setFrozenRows(1);
}

/**
 * Read positions from source sheet
 * @param {Sheet} sheet - Source sheet
 * @returns {Array} Array of position objects
 */
function EW_readOptionsPositions(sheet) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];

  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = {};

  // Build header map
  for (let i = 0; i < headers.length; i++) {
    const header = String(headers[i]).toLowerCase().trim().replace(/\s+/g, '');
    if (header === 'ticker') hdrMap.ticker = i;
    if (header === 'strike') hdrMap.strike = i;
    if (header === 'expdate' || header === 'expiration') hdrMap.expDate = i;
    if (header === 'rundate' || header === 'entrydate') hdrMap.runDate = i;
    if (header === 'entry_premium' || header === 'entrypremium') hdrMap.entryPremium = i;
  }

  // Validate required columns
  if (hdrMap.ticker === undefined || hdrMap.strike === undefined || hdrMap.expDate === undefined) {
    EW_trace('OPTIONS_PREMIUM', 'Missing required columns (ticker, strike, expDate)', true);
    return [];
  }

  const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  const positions = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  for (let i = 0; i < data.length; i++) {
    const row = data[i];

    const ticker = row[hdrMap.ticker];
    const strike = parseFloat(row[hdrMap.strike]);
    const expDate = new Date(row[hdrMap.expDate]);
    const entryPremium = hdrMap.entryPremium !== undefined ? parseFloat(row[hdrMap.entryPremium]) : null;

    // Skip if missing data or expired
    if (!ticker || isNaN(strike) || !expDate) continue;
    if (expDate < today) continue;

    positions.push({
      ticker: ticker,
      strike: strike,
      expDate: expDate,
      optionType: 'C', // Long Calls sheet
      entryPremium: entryPremium,
      rowNum: i + 2
    });
  }

  return positions;
}

/**
 * Build Yahoo Finance option symbol
 * Format: TICKER + YYMMDD + C/P + 8-digit strike
 * Example: ROKU251107C00060000 (ROKU Nov 7 2025 $60 Call)
 *
 * @param {string} ticker - Underlying ticker
 * @param {Date} expDate - Expiration date
 * @param {string} optionType - 'C' for call, 'P' for put
 * @param {number} strike - Strike price
 * @returns {string} Yahoo option symbol
 */
function EW_buildOptionSymbol(ticker, expDate, optionType, strike) {
  // Format: TICKER + YYMMDD + C/P + 8-digit strike

  // Year (2 digits)
  const year = String(expDate.getFullYear()).slice(-2);

  // Month (2 digits, padded)
  const month = String(expDate.getMonth() + 1).padStart(2, '0');

  // Day (2 digits, padded)
  const day = String(expDate.getDate()).padStart(2, '0');

  // Strike price (8 digits: 5 before decimal, 3 after)
  // Example: 60.00 -> 00060000, 125.50 -> 00125500
  const strikePadded = String(Math.round(strike * 1000)).padStart(8, '0');

  // Combine
  const symbol = `${ticker}${year}${month}${day}${optionType}${strikePadded}`;

  return symbol;
}

/**
 * Fetch option premiums for multiple positions in ONE batch API call
 * Much more efficient than individual calls!
 *
 * @param {Array} positions - Array of positions
 * @returns {Object} Map of optionSymbol -> premium data
 */
function EW_fetchOptionPremiumsBatch(positions) {
  const premiumDataMap = {};

  if (positions.length === 0) return premiumDataMap;

  // Build all option symbols
  const symbols = positions.map(pos =>
    EW_buildOptionSymbol(pos.ticker, pos.expDate, pos.optionType, pos.strike)
  );

  // Batch API call - all symbols in one request!
  const symbolsStr = symbols.join(',');
  const url = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbolsStr}`;

  EW_trace('OPTIONS_PREMIUM', `Fetching ${symbols.length} option premiums in batch`, true);
  EW_trace('OPTIONS_PREMIUM', `Symbols: ${symbols.slice(0, 5).join(', ')}${symbols.length > 5 ? '...' : ''}`, false);

  try {
    const response = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });

    const responseCode = response.getResponseCode();

    if (responseCode !== 200) {
      EW_trace('OPTIONS_PREMIUM', `Batch fetch failed: HTTP ${responseCode}`, true);
      return premiumDataMap;
    }

    const data = JSON.parse(response.getContentText());

    if (!data.quoteResponse || !data.quoteResponse.result) {
      EW_trace('OPTIONS_PREMIUM', `Batch fetch returned no results`, true);
      return premiumDataMap;
    }

    // Process each result
    const results = data.quoteResponse.result;
    EW_trace('OPTIONS_PREMIUM', `Received ${results.length} of ${symbols.length} results`, false);

    for (const quote of results) {
      const symbol = quote.symbol;

      // Extract premium data
      premiumDataMap[symbol] = {
        symbol: symbol,
        price: quote.regularMarketPrice || null,
        dayHigh: quote.regularMarketDayHigh || null,
        dayLow: quote.regularMarketDayLow || null,
        dayOpen: quote.regularMarketOpen || null,
        bid: quote.bid || null,
        ask: quote.ask || null,
        volume: quote.regularMarketVolume || 0,
        openInterest: quote.openInterest || 0,
        underlyingSymbol: quote.underlyingSymbol || '',
        strike: quote.strike || null,
        expireDate: quote.expireDate ? new Date(quote.expireDate * 1000) : null
      };
    }

  } catch (error) {
    EW_trace('OPTIONS_PREMIUM', `Batch fetch error: ${error.message}`, true);
  }

  return premiumDataMap;
}

/**
 * Fetch single option premium (used for testing)
 * For production, use batch fetch instead
 * @param {Object} position - Position with ticker, strike, expDate, optionType
 * @returns {Object} Premium data
 */
function EW_fetchOptionPremium(position) {
  // Use batch fetch with single position
  const premiumDataMap = EW_fetchOptionPremiumsBatch([position]);
  const optionSymbol = EW_buildOptionSymbol(
    position.ticker,
    position.expDate,
    position.optionType,
    position.strike
  );
  return premiumDataMap[optionSymbol] || null;
}

/**
 * Write premium data to output sheet
 * @param {Sheet} sheet - Output sheet
 * @param {Object} position - Position info
 * @param {Object} premiumData - Premium data from API
 */
function EW_writeOptionPremiumRow(sheet, position, premiumData) {
  const today = new Date();
  const dateStr = Utilities.formatDate(today, Session.getScriptTimeZone(), 'yyyy-MM-dd');
  const expDateStr = Utilities.formatDate(position.expDate, Session.getScriptTimeZone(), 'yyyy-MM-dd');

  // Calculate spread
  const spread = (premiumData.ask && premiumData.bid) ?
    (premiumData.ask - premiumData.bid) : null;

  // Calculate P/L and profitability analysis
  let pnl = null;
  let pnlPercent = null;
  let maxProfit = null;  // Best possible exit using Day_High
  let maxLoss = null;    // Worst case using Day_Low
  let wouldHaveBeenProfitable = null;  // Was there profit opportunity today?

  if (position.entryPremium && premiumData.price) {
    // Current P/L (closing premium vs entry)
    pnl = (premiumData.price - position.entryPremium) * 100; // * 100 for contract
    pnlPercent = (pnl / (position.entryPremium * 100)) * 100;

    // Best possible P/L if sold at day's high
    if (premiumData.dayHigh) {
      maxProfit = (premiumData.dayHigh - position.entryPremium) * 100;
    }

    // Worst case P/L if sold at day's low
    if (premiumData.dayLow) {
      maxLoss = (premiumData.dayLow - position.entryPremium) * 100;
    }

    // Check if there was profit opportunity at any point today
    if (premiumData.dayHigh) {
      wouldHaveBeenProfitable = premiumData.dayHigh > position.entryPremium ? 'YES' : 'NO';
    }
  }

  // Calculate days to expiration
  const daysToExp = Math.ceil((position.expDate - today) / (1000 * 60 * 60 * 24));

  const row = [
    dateStr,
    position.ticker,
    position.strike,
    position.optionType,
    expDateStr,
    premiumData.price || '',
    premiumData.dayHigh || '',
    premiumData.dayLow || '',
    premiumData.dayOpen || '',
    premiumData.bid || '',
    premiumData.ask || '',
    spread !== null ? spread : '',
    premiumData.volume || 0,
    premiumData.openInterest || 0,
    position.entryPremium || '',
    pnl !== null ? pnl : '',
    pnlPercent !== null ? pnlPercent : '',
    maxProfit !== null ? maxProfit : '',
    maxLoss !== null ? maxLoss : '',
    wouldHaveBeenProfitable || '',
    daysToExp
  ];

  // Append row
  const lastRow = sheet.getLastRow();
  const outputRange = sheet.getRange(lastRow + 1, 1, 1, row.length);
  outputRange.setValues([row]);

  // Format numbers
  sheet.getRange(lastRow + 1, 6, 1, 6).setNumberFormat('$#,##0.00'); // Premium, High, Low, Open, Bid, Ask
  sheet.getRange(lastRow + 1, 12, 1, 1).setNumberFormat('$#,##0.00'); // Spread
  sheet.getRange(lastRow + 1, 16, 1, 1).setNumberFormat('$#,##0.00'); // PnL
  sheet.getRange(lastRow + 1, 17, 1, 1).setNumberFormat('0.00%'); // PnL %
  sheet.getRange(lastRow + 1, 18, 1, 2).setNumberFormat('$#,##0.00'); // Max_Profit, Max_Loss

  // Conditional formatting for P/L
  if (pnl !== null) {
    if (pnl > 0) {
      sheet.getRange(lastRow + 1, 16, 1, 2).setBackground('#D9EAD3'); // Light green
    } else if (pnl < 0) {
      sheet.getRange(lastRow + 1, 16, 1, 2).setBackground('#F4CCCC'); // Light red
    }
  }

  // Conditional formatting for Max_Profit
  if (maxProfit !== null) {
    if (maxProfit > 0) {
      sheet.getRange(lastRow + 1, 18, 1, 1).setBackground('#D9EAD3'); // Light green
    } else if (maxProfit < 0) {
      sheet.getRange(lastRow + 1, 18, 1, 1).setBackground('#F4CCCC'); // Light red
    }
  }

  // Conditional formatting for Was_Profitable
  if (wouldHaveBeenProfitable === 'YES') {
    sheet.getRange(lastRow + 1, 20, 1, 1).setBackground('#D9EAD3').setFontWeight('bold');
  } else if (wouldHaveBeenProfitable === 'NO') {
    sheet.getRange(lastRow + 1, 20, 1, 1).setBackground('#F4CCCC').setFontWeight('bold');
  }
}

/**
 * Update selected positions only
 */
function EW_updateOptionsPremiumsSelected() {
  const ss = SpreadsheetApp.getActive();
  const sourceSheet = ss.getActiveSheet();
  const selection = sourceSheet.getActiveRange();

  if (sourceSheet.getName() !== 'Long Calls') {
    SpreadsheetApp.getUi().alert('Please select rows in the Long Calls sheet');
    return;
  }

  const startRow = selection.getRow();
  const numRows = selection.getNumRows();

  if (startRow === 1) {
    SpreadsheetApp.getUi().alert('Please select data rows (not the header)');
    return;
  }

  // Get output sheet
  const outputSheetName = 'Long Calls Options';
  let outputSheet = ss.getSheetByName(outputSheetName);

  if (!outputSheet) {
    outputSheet = ss.insertSheet(outputSheetName);
    EW_setupOptionsPremiumSheet(outputSheet);
  }

  // Read headers
  const headers = sourceSheet.getRange(1, 1, 1, sourceSheet.getLastColumn()).getValues()[0];
  const hdrMap = {};

  for (let i = 0; i < headers.length; i++) {
    const header = String(headers[i]).toLowerCase().trim().replace(/\s+/g, '');
    if (header === 'ticker') hdrMap.ticker = i;
    if (header === 'strike') hdrMap.strike = i;
    if (header === 'expdate' || header === 'expiration') hdrMap.expDate = i;
    if (header === 'entry_premium' || header === 'entrypremium') hdrMap.entryPremium = i;
  }

  // Read selected rows
  const data = sourceSheet.getRange(startRow, 1, numRows, sourceSheet.getLastColumn()).getValues();

  let processed = 0;
  let errors = [];

  for (let i = 0; i < data.length; i++) {
    const row = data[i];

    const ticker = row[hdrMap.ticker];
    const strike = parseFloat(row[hdrMap.strike]);
    const expDate = new Date(row[hdrMap.expDate]);
    const entryPremium = hdrMap.entryPremium !== undefined ? parseFloat(row[hdrMap.entryPremium]) : null;

    if (!ticker || isNaN(strike) || !expDate) continue;

    const position = {
      ticker: ticker,
      strike: strike,
      expDate: expDate,
      optionType: 'C',
      entryPremium: entryPremium
    };

    try {
      const premiumData = EW_fetchOptionPremium(position);

      if (premiumData && premiumData.price !== null) {
        EW_writeOptionPremiumRow(outputSheet, position, premiumData);
        processed++;
      }

    } catch (error) {
      errors.push(`${ticker}: ${error.message}`);
    }
  }

  SpreadsheetApp.flush();

  const msg = `Processed ${processed} of ${numRows} selected positions.` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.slice(0, 3).join('\n')}` : '');

  SpreadsheetApp.getUi().alert('Update Complete', msg, SpreadsheetApp.getUi().ButtonSet.OK);
}

/**
 * Test option symbol building and premium fetch
 */
function EW_testOptionPremiumFetch() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();
  const selection = sheet.getActiveRange();
  const row = selection.getRow();

  if (sheet.getName() !== 'Long Calls' || row === 1) {
    SpreadsheetApp.getUi().alert('Please select a data row in the Long Calls sheet');
    return;
  }

  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = {};

  for (let i = 0; i < headers.length; i++) {
    const header = String(headers[i]).toLowerCase().trim().replace(/\s+/g, '');
    if (header === 'ticker') hdrMap.ticker = i;
    if (header === 'strike') hdrMap.strike = i;
    if (header === 'expdate' || header === 'expiration') hdrMap.expDate = i;
  }

  const data = sheet.getRange(row, 1, 1, sheet.getLastColumn()).getValues()[0];

  const ticker = data[hdrMap.ticker];
  const strike = parseFloat(data[hdrMap.strike]);
  const expDate = new Date(data[hdrMap.expDate]);

  const position = {
    ticker: ticker,
    strike: strike,
    expDate: expDate,
    optionType: 'C'
  };

  const optionSymbol = EW_buildOptionSymbol(ticker, expDate, 'C', strike);
  Logger.log(`Option Symbol: ${optionSymbol}`);

  const premiumData = EW_fetchOptionPremium(position);

  if (!premiumData) {
    SpreadsheetApp.getUi().alert('No data returned - check logs');
    return;
  }

  Logger.log(`Premium: $${premiumData.price}`);
  Logger.log(`Day Range: $${premiumData.dayLow} - $${premiumData.dayHigh}`);
  Logger.log(`Bid/Ask: $${premiumData.bid} / $${premiumData.ask}`);

  const msg = `${ticker} $${strike} Call (${Utilities.formatDate(expDate, Session.getScriptTimeZone(), 'MMM dd yyyy')})\n\n` +
    `Option Symbol: ${optionSymbol}\n\n` +
    `Premium: $${premiumData.price.toFixed(2)}\n` +
    `Day High: $${premiumData.dayHigh.toFixed(2)}\n` +
    `Day Low: $${premiumData.dayLow.toFixed(2)}\n` +
    `Bid/Ask: $${premiumData.bid.toFixed(2)} / $${premiumData.ask.toFixed(2)}\n` +
    `Volume: ${premiumData.volume}\n` +
    `Open Interest: ${premiumData.openInterest}`;

  SpreadsheetApp.getUi().alert('Premium Data', msg, SpreadsheetApp.getUi().ButtonSet.OK);
}
