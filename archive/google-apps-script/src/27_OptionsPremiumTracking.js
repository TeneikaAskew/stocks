// /**
//  * Options Daily Tracking - DISABLED
//  *
//  * THIS FILE IS COMMENTED OUT - All functionality has been migrated to 27_OptionsPremiumBackfill.js
//  * The premium tracking is disabled to avoid conflicts with the backfill script.
//  *
//  * See 27_OptionsPremiumBackfill.js for the standalone, working version that includes all dependencies.
//  *
//  * Original functionality:
//  * - Fetched real options premium data from Yahoo Finance quote API
//  * - Calculated P/L based on premium changes
//  * - Wrote to "Strategy Options" sheets
//  *
//  * IMPORTANT:
//  * - All functions below are commented out
//  * - Use EW_backfillOptionsPremiumHistory() from 27_OptionsPremiumBackfill.js instead
//  */

// /*
// // COMMENTED OUT - See 27_OptionsPremiumBackfill.js for working version

// /**
//  * Update options tracking with actual premium data
//  * Runs for all active positions in "Long Calls" sheet
//  * /
// function EW_updateOptionsPremiums() {
//   const startTime = new Date();
//   EW_trace('OPTIONS_PREMIUM', 'Starting options premium update', true);

//   const ss = SpreadsheetApp.getActive();
//   const sourceSheet = ss.getSheetByName('Long Calls');

//   if (!sourceSheet) {
//     EW_trace('OPTIONS_PREMIUM', 'Long Calls sheet not found', true);
//     return;
//   }

//   // Detect strategy type for proper strike hit logic
//   const strategyName = sourceSheet.getName();
//   const strategyType = EW_detectStrategyType(strategyName);

//   EW_trace('OPTIONS_PREMIUM', `Strategy: ${strategyName}, Type: ${strategyType}`, true);

//   // Get or create output sheet
//   const outputSheetName = `${strategyName} Options`;
//   let outputSheet = ss.getSheetByName(outputSheetName);

//   if (!outputSheet) {
//     outputSheet = ss.insertSheet(outputSheetName);
//     EW_setupOptionsPremiumSheet(outputSheet);
//   }

//   // Read positions from source sheet (newest first - from bottom)
//   const positions = EW_readOptionsPositions(sourceSheet, strategyType);

//   if (positions.length === 0) {
//     EW_trace('OPTIONS_PREMIUM', 'No positions to process', true);
//     return;
//   }

//   EW_trace('OPTIONS_PREMIUM', `Found ${positions.length} positions to check`, true);

//   // Filter out positions already in output sheet (avoid duplicates)
//   const existingPositions = EW_getExistingPositions(outputSheet);
//   const newPositions = positions.filter(pos => {
//     const key = `${pos.ticker}_${pos.strike}_${Utilities.formatDate(pos.expDate, Session.getScriptTimeZone(), 'yyyy-MM-dd')}`;
//     return !existingPositions.has(key);
//   });

//   if (newPositions.length === 0) {
//     EW_trace('OPTIONS_PREMIUM', 'All positions already processed today - skipping', true);
//     return;
//   }

//   EW_trace('OPTIONS_PREMIUM', `Processing ${newPositions.length} new positions (${positions.length - newPositions.length} already exist)`, true);

//   let processed = 0;
//   let errors = [];

//   // Fetch all premiums in one batch call (much more efficient!)
//   const premiumDataMap = EW_fetchOptionPremiumsBatch(newPositions);

//   // Fetch underlying stock OHLC data for strike hit detection
//   const stockDataMap = EW_fetchStockOHLCBatch(newPositions);

//   // Process each NEW position with fetched data
//   for (let i = 0; i < newPositions.length; i++) {
//     const position = newPositions[i];
//     const optionSymbol = EW_buildOptionSymbol(
//       position.ticker,
//       position.expDate,
//       position.optionType,
//       position.strike
//     );

//     try {
//       const premiumData = premiumDataMap[optionSymbol];
//       const stockData = stockDataMap[position.ticker];

//       if (premiumData && premiumData.price !== null) {
//         // Check if strike was hit based on strategy type
//         let strikeHit = false;
//         if (stockData) {
//           if (strategyType === 'BULLISH') {
//             // Bullish: check if stock's dayHigh >= strike
//             strikeHit = stockData.dayHigh >= position.strike;
//           } else if (strategyType === 'BEARISH') {
//             // Bearish: check if stock's dayLow <= strike
//             strikeHit = stockData.dayLow <= position.strike;
//           }
//         }

//         EW_writeOptionPremiumRow(outputSheet, position, premiumData, stockData, strikeHit, strategyType);
//         processed++;

//         const hitStr = strikeHit ? '✓ STRIKE HIT' : '✗ No hit';
//         EW_trace('OPTIONS_PREMIUM', `  ✓ ${position.ticker} $${position.strike}: Premium $${premiumData.price.toFixed(2)}, Stock ${stockData ? `$${stockData.price.toFixed(2)}` : 'N/A'}, ${hitStr}`, false);
//       } else {
//         EW_trace('OPTIONS_PREMIUM', `  ⚠ ${position.ticker} $${position.strike}: No premium data available`, false);
//       }

//     } catch (error) {
//       const errorMsg = `${position.ticker} $${position.strike}: ${error.message}`;
//       errors.push(errorMsg);
//       EW_trace('OPTIONS_PREMIUM', `  ✗ Error: ${errorMsg}`, true);
//     }
//   }

//   // Sort by date descending (most recent first)
//   if (processed > 0) {
//     const lastRow = outputSheet.getLastRow();
//     if (lastRow > 1) {
//       const dataRange = outputSheet.getRange(2, 1, lastRow - 1, outputSheet.getLastColumn());
//       dataRange.sort({column: 1, ascending: false}); // Sort by date
//     }
//     SpreadsheetApp.flush();
//   }

//   const elapsed = Math.round((new Date() - startTime) / 1000);
//   const msg = `Premium update complete in ${elapsed}s. Processed ${processed} of ${positions.length} positions.` +
//     (errors.length > 0 ? `\n\nErrors:\n${errors.slice(0, 5).join('\n')}` : '');

//   EW_trace('OPTIONS_PREMIUM', msg, true);

//   if (EW_isSpreadsheetEnvironment()) {
//     SpreadsheetApp.getUi().alert('Premium Update Complete', msg, SpreadsheetApp.getUi().ButtonSet.OK);
//   }
// }

// /**
//  * Setup output sheet with premium tracking columns
//  * @param {Sheet} sheet - The output sheet
//  */
// function EW_setupOptionsPremiumSheet(sheet) {
//   const headers = [
//     // Basic Info
//     'Date',
//     'Run_Date',
//     'Ticker',
//     'Strike',
//     'Type',
//     'ExpDate',

//     // Strike Hit Tracking
//     'Strike_Hit',
//     'Hit_Date',
//     'Max_Favorable',
//     'Min_Unfavorable',

//     // Daily Check Values (premium at close each day)
//     'Day0_Check',
//     'Day1_Check',
//     'Day2_Check',
//     'Day3_Check',
//     'Day4_Check',
//     'Day5_Check',
//     'Day6_Check',
//     'Day7_Check',
//     'Day8_Check',
//     'Day9_Check',
//     'Day10_Check',
//     'Day11_Check',
//     'Day12_Check',
//     'Day13_Check',

//     // Expiration Results
//     'Exp_Result',
//     'Risk_Reward',

//     // Options OHLC and Volume
//     'OHLC_Volume',

//     // Real-time Current Data
//     'Bid',
//     'Ask',
//     'Spread',
//     'Volume',

//     // P/L Analysis (based on latest day's high/low)
//     'PnL_Current_High',
//     'PnL_Current_High_Pct',
//     'PnL_Current_Low',
//     'PnL_Current_Low_Pct',

//     'Days_To_Exp',

//     // API Metadata
//     'API_URL'
//   ];

//   const headerRange = sheet.getRange(1, 1, 1, headers.length);
//   headerRange.setValues([headers]);

//   // Set column widths for better readability
//   const widths = [
//     100,  // Date
//     100,  // Run_Date
//     80,   // Ticker
//     70,   // Strike
//     60,   // Type
//     100,  // ExpDate
//     120,  // Strike_Hit (array)
//     80,   // Hit_Date
//     120,  // Max_Favorable (array)
//     120,  // Min_Unfavorable (array)
//     90,   // Day0_Check
//     90,   // Day1_Check
//     90,   // Day2_Check
//     90,   // Day3_Check
//     90,   // Day4_Check
//     90,   // Day5_Check
//     90,   // Day6_Check
//     90,   // Day7_Check
//     90,   // Day8_Check
//     90,   // Day9_Check
//     90,   // Day10_Check
//     90,   // Day11_Check
//     90,   // Day12_Check
//     90,   // Day13_Check
//     90,   // Exp_Result
//     90,   // Risk_Reward
//     200,  // OHLC_Volume (JSON)
//     80,   // Bid
//     80,   // Ask
//     80,   // Spread
//     80,   // Volume
//     100,  // PnL_Current_High
//     100,  // PnL_Current_High_Pct
//     100,  // PnL_Current_Low
//     100,  // PnL_Current_Low_Pct
//     90,   // Days_To_Exp
//     400   // API_URL
//   ];

//   for (let i = 0; i < widths.length; i++) {
//     sheet.setColumnWidth(i + 1, widths[i]);
//   }

//   // Format columns with proper data types to prevent auto-detection issues
//   const maxRows = sheet.getMaxRows() - 1; // Exclude header row

//   // Date columns (Date, Run_Date, ExpDate) - columns 1, 2, 6
//   const dateColumns = [1, 2, 6];
//   dateColumns.forEach(col => {
//     sheet.getRange(2, col, maxRows, 1).setNumberFormat('yyyy-mm-dd');
//   });

//   // Text columns (Ticker, Type) - columns 3, 5
//   const textColumns = [3, 5];
//   textColumns.forEach(col => {
//     sheet.getRange(2, col, maxRows, 1).setNumberFormat('@'); // @ = text format
//   });

//   // Number columns (Strike) - column 4
//   sheet.getRange(2, 4, maxRows, 1).setNumberFormat('0.00');

//   // JSON array columns (Strike_Hit, Max_Favorable, Min_Unfavorable, OHLC_Volume) - columns 7, 9, 10, 23
//   const jsonColumns = [7, 9, 10, 23];
//   jsonColumns.forEach(col => {
//     sheet.getRange(2, col, maxRows, 1).setNumberFormat('@');
//   });

//   // Number/date columns (Hit_Date) - column 8
//   sheet.getRange(2, 8, maxRows, 1).setNumberFormat('0');

//   // Day Check columns (Day0-Day13) - columns 11-24
//   for (let col = 11; col <= 24; col++) {
//     sheet.getRange(2, col, maxRows, 1).setNumberFormat('0.00');
//   }

//   // Result columns (Exp_Result, Risk_Reward) - columns 25, 26
//   sheet.getRange(2, 25, maxRows, 1).setNumberFormat('@');
//   sheet.getRange(2, 26, maxRows, 1).setNumberFormat('0.00');

//   // Premium data columns (Bid, Ask, Spread) - columns 28, 29, 30
//   for (let col = 28; col <= 30; col++) {
//     sheet.getRange(2, col, maxRows, 1).setNumberFormat('0.00');
//   }

//   // Volume - column 31
//   sheet.getRange(2, 31, maxRows, 1).setNumberFormat('0');

//   // P/L dollar amounts (PnL_Current_High, PnL_Current_Low) - columns 32, 34
//   sheet.getRange(2, 32, maxRows, 1).setNumberFormat('0.00');
//   sheet.getRange(2, 34, maxRows, 1).setNumberFormat('0.00');

//   // P/L percentages (PnL_Current_High_Pct, PnL_Current_Low_Pct) - columns 33, 35
//   sheet.getRange(2, 33, maxRows, 1).setNumberFormat('0.00%');
//   sheet.getRange(2, 35, maxRows, 1).setNumberFormat('0.00%');

//   // Days to expiration - column 36
//   sheet.getRange(2, 36, maxRows, 1).setNumberFormat('0');

//   // API URL - column 37
//   sheet.getRange(2, 37, maxRows, 1).setNumberFormat('@');

//   // Freeze header row
//   sheet.setFrozenRows(1);
// }

// /**
//  * Get existing positions from output sheet (to avoid duplicates)
//  * @param {Sheet} sheet - Output sheet
//  * @returns {Set} Set of position keys (ticker_strike_expDate)
//  */
// function EW_getExistingPositions(sheet) {
//   const existingPositions = new Set();

//   const lastRow = sheet.getLastRow();
//   if (lastRow < 2) return existingPositions;

//   try {
//     // Get headers and map them dynamically
//     const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
//     const hdrMap = EW_headerMap(headers);

//     // Validate required columns exist
//     if (!hdrMap.tickerCol || !hdrMap.strikeCol || !hdrMap.expDateCol) {
//       EW_trace('OPTIONS_PREMIUM', 'Missing required columns in sheet (ticker, strike, expDate)', true);
//       return existingPositions;
//     }

//     // Get only the columns we need
//     const numCols = Math.max(hdrMap.tickerCol, hdrMap.strikeCol, hdrMap.expDateCol);
//     const data = sheet.getRange(2, 1, lastRow - 1, numCols).getValues();

//     for (const row of data) {
//       const ticker = String(row[hdrMap.tickerCol - 1]);
//       const strike = parseFloat(row[hdrMap.strikeCol - 1]);
//       const expDate = row[hdrMap.expDateCol - 1] instanceof Date ?
//         Utilities.formatDate(row[hdrMap.expDateCol - 1], Session.getScriptTimeZone(), 'yyyy-MM-dd') :
//         String(row[hdrMap.expDateCol - 1]);

//       if (ticker && !isNaN(strike) && expDate) {
//         const key = `${ticker}_${strike}_${expDate}`;
//         existingPositions.add(key);
//       }
//     }

//     if (existingPositions.size > 0) {
//       EW_trace('OPTIONS_PREMIUM', `Found ${existingPositions.size} existing positions in tracking sheet`, false);
//     }

//   } catch (error) {
//     EW_trace('OPTIONS_PREMIUM', `Error reading existing positions: ${error.message}`, false);
//   }

//   return existingPositions;
// }

// /**
//  * Read positions from source sheet (newest first - from bottom up)
//  * @param {Sheet} sheet - Source sheet
//  * @param {string} strategyType - Strategy type (BULLISH, BEARISH, NEUTRAL)
//  * @returns {Array} Array of position objects (newest first)
//  */
// function EW_readOptionsPositions(sheet, strategyType) {
//   const lastRow = sheet.getLastRow();
//   if (lastRow < 2) return [];

//   const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
//   const hdrMap = {};

//   // Build header map
//   for (let i = 0; i < headers.length; i++) {
//     const header = String(headers[i]).toLowerCase().trim().replace(/\s+/g, '');
//     if (header === 'ticker') hdrMap.ticker = i;
//     if (header === 'strike') hdrMap.strike = i;
//     if (header === 'expdate' || header === 'expiration') hdrMap.expDate = i;
//     if (header === 'rundate' || header === 'entrydate' || header === 'scandate') hdrMap.runDate = i;
//     if (header === 'entry_premium' || header === 'entrypremium' || header === 'bid' || header === 'ask') {
//       // Use bid or ask as entry premium if available
//       if (header === 'bid' && hdrMap.entryPremium === undefined) hdrMap.entryPremium = i;
//       if (header === 'entry_premium' || header === 'entrypremium') hdrMap.entryPremium = i;
//     }
//   }

//   // Validate required columns
//   if (hdrMap.ticker === undefined || hdrMap.strike === undefined || hdrMap.expDate === undefined) {
//     EW_trace('OPTIONS_PREMIUM', 'Missing required columns (ticker, strike, expDate)', true);
//     return [];
//   }

//   const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
//   const positions = [];
//   const today = new Date();
//   today.setHours(0, 0, 0, 0);

//   // Process rows in REVERSE order (bottom to top = newest first)
//   for (let i = data.length - 1; i >= 0; i--) {
//     const row = data[i];

//     const ticker = row[hdrMap.ticker];
//     const strike = parseFloat(row[hdrMap.strike]);
//     const expDate = new Date(row[hdrMap.expDate]);
//     const runDate = hdrMap.runDate !== undefined ? new Date(row[hdrMap.runDate]) : null;
//     const entryPremium = hdrMap.entryPremium !== undefined ? parseFloat(row[hdrMap.entryPremium]) : null;

//     // Skip if missing data or expired
//     if (!ticker || isNaN(strike) || !expDate) continue;
//     if (expDate < today) continue;

//     // Optional: Filter to only today's entries if runDate is available
//     if (runDate) {
//       runDate.setHours(0, 0, 0, 0);
//       // Uncomment to only process today's scans:
//       // if (runDate.getTime() !== today.getTime()) continue;
//     }

//     // Determine option type based on strategy
//     let optionType = 'C'; // Default to Call
//     if (strategyType === 'BEARISH') {
//       optionType = 'P'; // Put for bearish strategies
//     }

//     positions.push({
//       ticker: ticker,
//       strike: strike,
//       expDate: expDate,
//       runDate: runDate || today,  // Use runDate from sheet, fallback to today
//       optionType: optionType,
//       entryPremium: entryPremium,
//       rowNum: i + 2,
//       strategyType: strategyType
//     });
//   }

//   return positions;
// }

// /**
//  * Build Yahoo Finance option symbol
//  * Format: TICKER + YYMMDD + C/P + 8-digit strike
//  * Example: ROKU251107C00060000 (ROKU Nov 7 2025 $60 Call)
//  *
//  * @param {string} ticker - Underlying ticker
//  * @param {Date} expDate - Expiration date
//  * @param {string} optionType - 'C' for call, 'P' for put
//  * @param {number} strike - Strike price
//  * @returns {string} Yahoo option symbol
//  */
// function EW_buildOptionSymbol(ticker, expDate, optionType, strike) {
//   // Format: TICKER + YYMMDD + C/P + 8-digit strike

//   // Year (2 digits)
//   const year = String(expDate.getFullYear()).slice(-2);

//   // Month (2 digits, padded)
//   const month = String(expDate.getMonth() + 1).padStart(2, '0');

//   // Day (2 digits, padded)
//   const day = String(expDate.getDate()).padStart(2, '0');

//   // Strike price (8 digits: 5 before decimal, 3 after)
//   // Example: 60.00 -> 00060000, 125.50 -> 00125500
//   const strikePadded = String(Math.round(strike * 1000)).padStart(8, '0');

//   // Combine
//   const symbol = `${ticker}${year}${month}${day}${optionType}${strikePadded}`;

//   return symbol;
// }

// /**
//  * Fetch option premiums for multiple positions in ONE batch API call
//  * Much more efficient than individual calls!
//  *
//  * @param {Array} positions - Array of positions
//  * @returns {Object} Map of optionSymbol -> premium data
//  */
// function EW_getYahooQuoteSession(forceRefresh = false) {
//   const cache = (typeof CacheService !== 'undefined') ? CacheService.getScriptCache() : null;
//   const cacheKey = 'EW_YAHOO_QUOTE_SESSION';

//   if (!forceRefresh && cache) {
//     const cachedSession = cache.get(cacheKey);
//     if (cachedSession) {
//       try {
//         const parsed = JSON.parse(cachedSession);
//         if (parsed && parsed.crumb && parsed.cookie) {
//           return parsed;
//         }
//       } catch (error) {
//         // Ignore parse errors and refresh session
//       }
//     }
//   }

//   const userAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36';

//   // Step 1: hit fc.yahoo.com to obtain the auth cookies (B=, A1=, etc.)
//   const cookieResponse = UrlFetchApp.fetch('https://fc.yahoo.com', {
//     muteHttpExceptions: true,
//     followRedirects: false,
//     headers: {
//       'User-Agent': userAgent
//     }
//   });

//   const cookieHeaders = cookieResponse.getAllHeaders();
//   let initialCookie = EW_extractYahooCookie(cookieHeaders['Set-Cookie'] || cookieHeaders['set-cookie']);

//   if (!initialCookie) {
//     throw new Error(`Failed to obtain Yahoo Finance cookie: HTTP ${cookieResponse.getResponseCode()}`);
//   }

//   // Step 2: request a crumb using the cookies we just received. Retry across query1/query2 endpoints.
//   const crumbEndpoints = [
//     'https://query1.finance.yahoo.com/v1/test/getcrumb',
//     'https://query2.finance.yahoo.com/v1/test/getcrumb'
//   ];

//   let crumb = '';
//   let lastStatus = null;

//   for (let i = 0; i < crumbEndpoints.length && !crumb; i++) {
//     const endpoint = crumbEndpoints[i];
//     const response = UrlFetchApp.fetch(endpoint, {
//       muteHttpExceptions: true,
//       followRedirects: false,
//       headers: {
//         'User-Agent': userAgent,
//         'Cookie': initialCookie
//       }
//     });

//     lastStatus = response.getResponseCode();

//     if (lastStatus === 200) {
//       const responseCrumb = response.getContentText().trim();
//       if (responseCrumb) {
//         crumb = responseCrumb;
//         const crumbCookie = EW_extractYahooCookie(response.getAllHeaders()['Set-Cookie'] || response.getAllHeaders()['set-cookie']);
//         if (crumbCookie) {
//           initialCookie = [initialCookie, crumbCookie].filter(Boolean).join('; ');
//         }
//       }
//     }
//   }

//   if (!crumb) {
//     throw new Error(`Failed to obtain Yahoo Finance crumb: HTTP ${lastStatus}`);
//   }

//   const session = { crumb: crumb, cookie: initialCookie };

//   if (cache) {
//     try {
//       cache.put(cacheKey, JSON.stringify(session), 60 * 55); // Cache for ~55 minutes
//     } catch (error) {
//       // Ignore cache write errors
//     }
//   }

//   return session;
// }

// function EW_extractYahooCookie(setCookieHeader) {
//   if (!setCookieHeader) return '';

//   const cookies = Array.isArray(setCookieHeader) ? setCookieHeader : [setCookieHeader];
//   const parsed = cookies
//     .map(cookie => (cookie || '').split(';')[0])
//     .filter(Boolean);

//   return parsed.join('; ');
// }

// function EW_fetchOptionPremiumsBatch(positions) {
//   const premiumDataMap = {};

//   if (positions.length === 0) return premiumDataMap;

//   // Build all option symbols
//   const symbols = positions.map(pos =>
//     EW_buildOptionSymbol(pos.ticker, pos.expDate, pos.optionType, pos.strike)
//   );

//   // Batch API call - all symbols in one request!
//   const symbolsStr = symbols.join(',');
//   let session = null;

//   try {
//     session = EW_getYahooQuoteSession();
//   } catch (error) {
//     EW_trace('OPTIONS_PREMIUM', `Failed to initialize Yahoo session: ${error.message}`, true);
//     return premiumDataMap;
//   }

//   const buildUrl = crumb => `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbolsStr}&crumb=${encodeURIComponent(crumb)}`;
//   let url = buildUrl(session.crumb);

//   EW_trace('OPTIONS_PREMIUM', `Fetching ${symbols.length} option premiums in batch`, true);
//   EW_trace('OPTIONS_PREMIUM', `Symbols: ${symbols.slice(0, 5).join(', ')}${symbols.length > 5 ? '...' : ''}`, false);

//   try {
//     let response = UrlFetchApp.fetch(url, {
//       muteHttpExceptions: true,
//       headers: {
//         'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
//         'Cookie': session.cookie
//       }
//     });

//     let responseCode = response.getResponseCode();

//     if (responseCode === 401 || responseCode === 403) {
//       // Refresh crumb/cookie and retry once
//       try {
//         session = EW_getYahooQuoteSession(true);
//         url = buildUrl(session.crumb);
//         response = UrlFetchApp.fetch(url, {
//           muteHttpExceptions: true,
//           headers: {
//             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
//             'Cookie': session.cookie
//           }
//         });
//         responseCode = response.getResponseCode();
//       } catch (retryError) {
//         EW_trace('OPTIONS_PREMIUM', `Yahoo session refresh failed: ${retryError.message}`, true);
//         return premiumDataMap;
//       }
//     }

//     if (responseCode !== 200) {
//       EW_trace('OPTIONS_PREMIUM', `Batch fetch failed: HTTP ${responseCode}`, true);
//       return premiumDataMap;
//     }

//     const data = JSON.parse(response.getContentText());

//     if (!data.quoteResponse || !data.quoteResponse.result) {
//       EW_trace('OPTIONS_PREMIUM', `Batch fetch returned no results`, true);
//       return premiumDataMap;
//     }

//     // Process each result
//     const results = data.quoteResponse.result;
//     EW_trace('OPTIONS_PREMIUM', `Received ${results.length} of ${symbols.length} results`, false);

//     for (const quote of results) {
//       const symbol = quote.symbol;

//       // Extract premium data
//       premiumDataMap[symbol] = {
//         symbol: symbol,
//         price: quote.regularMarketPrice || null,
//         dayHigh: quote.regularMarketDayHigh || null,
//         dayLow: quote.regularMarketDayLow || null,
//         dayOpen: quote.regularMarketOpen || null,
//         bid: quote.bid || null,
//         ask: quote.ask || null,
//         volume: quote.regularMarketVolume || 0,
//         openInterest: quote.openInterest || 0,
//         underlyingSymbol: quote.underlyingSymbol || '',
//         strike: quote.strike || null,
//         expireDate: quote.expireDate ? new Date(quote.expireDate * 1000) : null
//       };
//     }

//   } catch (error) {
//     EW_trace('OPTIONS_PREMIUM', `Batch fetch error: ${error.message}`, true);
//   }

//   return premiumDataMap;
// }

// /**
//  * Fetch historical daily premiums for an option symbol using Yahoo Finance chart API
//  * Ensures the request uses the daily interval with 9:30 AM / 4:30 PM Eastern bounds
//  * @param {string} optionSymbol - Yahoo option symbol (e.g., ROKU251107C00060000)
//  * @param {Date} startDate - Inclusive start date
//  * @param {Date} endDate - Inclusive end date
//  * @returns {Array<Object>} Array of OHLC data ordered by day
//  */
// function EW_fetchOptionPremiumHistory(optionSymbol, startDate, endDate) {
//   const history = [];

//   if (!optionSymbol || !startDate || !endDate) {
//     return history;
//   }

//   const period1 = EW_getEasternUnixTimestamp(startDate, 9, 30, 0);
//   let period2 = EW_getEasternUnixTimestamp(endDate, 16, 30, 0);

//   if (period1 === null || period2 === null) {
//     return history;
//   }

//   // Ensure period2 is after period1; if not, extend to the following day at 4:30 PM ET
//   if (period2 <= period1) {
//     const adjustedEnd = new Date(endDate);
//     adjustedEnd.setDate(adjustedEnd.getDate() + 1);
//     period2 = EW_getEasternUnixTimestamp(adjustedEnd, 16, 30, 0);
//   }

//   const url = `https://query2.finance.yahoo.com/v8/finance/chart/${optionSymbol}?period1=${period1}&period2=${period2}&interval=1d&events=history`;

//   EW_trace('OPTIONS_PREMIUM', `Fetching daily premium history for ${optionSymbol}`, false);

//   try {
//     const response = UrlFetchApp.fetch(url, {
//       muteHttpExceptions: true,
//       headers: {
//         'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
//       }
//     });

//     const responseCode = response.getResponseCode();

//     if (responseCode === 401 || responseCode === 403) {
//       session = EW_getYahooQuoteSession(true);
//       const retryCrumb = session && session.crumb ? `&crumb=${encodeURIComponent(session.crumb)}` : '';
//       const retryUrl = `https://query2.finance.yahoo.com/v8/finance/chart/${optionSymbol}?period1=${period1}&period2=${period2}&interval=1d&events=history${retryCrumb}`;
//       const retryResponse = UrlFetchApp.fetch(retryUrl, {
//         muteHttpExceptions: true,
//         headers: {
//           'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
//           'Cookie': session.cookie
//         }
//       });
//       return EW_parsePremiumHistoryResponse(optionSymbol, retryResponse);
//     }

//     if (responseCode !== 200) {
//       EW_trace('OPTIONS_PREMIUM', `History fetch failed for ${optionSymbol}: HTTP ${responseCode}`, true);
//       return history;
//     }

//     return EW_parsePremiumHistoryResponse(optionSymbol, response);

//   } catch (error) {
//     EW_trace('OPTIONS_PREMIUM', `History fetch error for ${optionSymbol}: ${error.message}`, true);
//     return history;
//   }
// }

// function EW_parsePremiumHistoryResponse(optionSymbol, response) {
//   const history = [];

//   try {
//     const data = JSON.parse(response.getContentText());

//     if (!data.chart || !data.chart.result || data.chart.result.length === 0) {
//       return history;
//     }

//     const result = data.chart.result[0];
//     const timestamps = result.timestamp || [];
//     const quote = result.indicators && result.indicators.quote ? result.indicators.quote[0] : null;
//     const adjCloseContainer = result.indicators && result.indicators.adjclose ? result.indicators.adjclose[0] : null;
//     const adjCloseArray = adjCloseContainer && adjCloseContainer.adjclose ? adjCloseContainer.adjclose : [];

//     if (!quote || timestamps.length === 0) {
//       EW_trace('OPTIONS_PREMIUM', `No timestamps or quote data for ${optionSymbol}`, false);
//       return history;
//     }

//     EW_trace('OPTIONS_PREMIUM', `Parsing ${timestamps.length} data points for ${optionSymbol}`, false);

//     const sanitizeNumber = value => {
//       if (value === null || value === undefined || value === '') return null;
//       const num = Number(value);
//       return isNaN(num) ? null : num;
//     };

//     const getArrayValue = (arr, index) => {
//       if (!arr || !Array.isArray(arr) || index >= arr.length) return null;
//       return sanitizeNumber(arr[index]);
//     };

//     let lastClose = null;
//     let lastOpen = null;
//     let lastHigh = null;
//     let lastLow = null;

//     for (let i = 0; i < timestamps.length; i++) {
//       const rawClose = getArrayValue(quote.close, i);
//       const adjClose = getArrayValue(adjCloseArray, i);
//       let close = rawClose !== null ? rawClose : (adjClose !== null ? adjClose : lastClose);

//       if (close === null) {
//         continue; // Cannot record a candle without a close value
//       }

//       let open = getArrayValue(quote.open, i);
//       if (open === null) {
//         open = lastOpen !== null ? lastOpen : close;
//       }

//       let high = getArrayValue(quote.high, i);
//       if (high === null) {
//         high = Math.max(open, close, lastHigh !== null ? lastHigh : close);
//       }

//       let low = getArrayValue(quote.low, i);
//       if (low === null) {
//         low = Math.min(open, close, lastLow !== null ? lastLow : close);
//       }

//       const volume = getArrayValue(quote.volume, i);

//       history.push({
//         date: new Date(timestamps[i] * 1000),
//         open: open,
//         high: high,
//         low: low,
//         close: close,
//         volume: volume !== null ? volume : 0
//       });

//       lastClose = close;
//       lastOpen = open;
//       lastHigh = high;
//       lastLow = low;
//     }

//   } catch (error) {
//     EW_trace('OPTIONS_PREMIUM', `Failed to parse history for ${optionSymbol}: ${error.message}`, true);
//   }

//   return history;
// }

// /**
//  * Fetch single option premium (used for testing)
//  * For production, use batch fetch instead
//  * @param {Object} position - Position with ticker, strike, expDate, optionType
//  * @returns {Object} Premium data
//  */
// function EW_fetchOptionPremium(position) {
//   // Use batch fetch with single position
//   const premiumDataMap = EW_fetchOptionPremiumsBatch([position]);
//   const optionSymbol = EW_buildOptionSymbol(
//     position.ticker,
//     position.expDate,
//     position.optionType,
//     position.strike
//   );
//   return premiumDataMap[optionSymbol] || null;
// }

// /**
//  * Write premium data to output sheet
//  * Uses runDate from position to determine which DayN_Check column to populate
//  *
//  * @param {Sheet} sheet - Output sheet
//  * @param {Object} position - Position info (must include runDate)
//  * @param {Object} premiumData - Premium data from API
//  * @param {Object} stockData - Stock OHLC data
//  * @param {boolean} strikeHit - Whether strike was hit today
//  * @param {string} strategyType - Strategy type (BULLISH/BEARISH/NEUTRAL)
//  *
//  * Example: If position.runDate = Monday and today = Tuesday:
//  * - Entry Date = Monday (position.runDate)
//  * - Day0_Check = blank
//  * - Day1_Check = today's premium
//  */
// function EW_writeOptionPremiumRow(sheet, position, premiumData, stockData, strikeHit, strategyType) {
//   const today = new Date();
//   today.setHours(0, 0, 0, 0);

//   // Use runDate from position (entry date) instead of today
//   const entryDate = new Date(position.runDate);
//   entryDate.setHours(0, 0, 0, 0);
//   const dateStr = Utilities.formatDate(entryDate, Session.getScriptTimeZone(), 'yyyy-MM-dd');
//   const expDateStr = Utilities.formatDate(position.expDate, Session.getScriptTimeZone(), 'yyyy-MM-dd');

//   // Calculate which day index this is (0-13)
//   const daysSinceEntry = Math.floor((today - entryDate) / (1000 * 60 * 60 * 24));

//   // Skip if beyond our tracking window
//   if (daysSinceEntry < 0 || daysSinceEntry > 13) {
//     EW_trace('OPTIONS_PREMIUM', `Skipping ${position.ticker} - ${daysSinceEntry} days since entry (outside 0-13 range)`, false);
//     return;
//   }

//   const MAX_TRACKING_DAYS = 14;
//   const optionSymbol = EW_buildOptionSymbol(
//     position.ticker,
//     position.expDate,
//     position.optionType,
//     position.strike
//   );

//   // Prepare arrays with default placeholders
//   const strikeHitArray = Array(MAX_TRACKING_DAYS).fill('0.000000');
//   const maxFavorableArray = Array(MAX_TRACKING_DAYS).fill('0.000000');
//   const minUnfavorableArray = Array(MAX_TRACKING_DAYS).fill('0.000000');
//   const ohlcVolumeArray = Array(MAX_TRACKING_DAYS).fill(null);
//   const dayCheckValues = Array(MAX_TRACKING_DAYS).fill('');

//   // Fetch historical premiums for backfilling earlier days
//   let premiumHistoryMap = {};
//   const historyCutoff = new Date(entryDate);
//   historyCutoff.setDate(historyCutoff.getDate() + Math.min(daysSinceEntry, MAX_TRACKING_DAYS - 1));

//   if (daysSinceEntry > 0) {
//     const history = EW_fetchOptionPremiumHistory(optionSymbol, entryDate, historyCutoff);
//     const tz = Session.getScriptTimeZone();
//     for (const item of history) {
//       const key = Utilities.formatDate(new Date(item.date), tz, 'yyyy-MM-dd');
//       premiumHistoryMap[key] = item;
//     }
//   }

//   // Calculate spread
//   const spread = (premiumData.ask && premiumData.bid) ?
//     (premiumData.ask - premiumData.bid) : null;

//   // Calculate P/L at different times of day
//   let pnlAtOpen = null;
//   let pnlAtOpenPct = null;
//   let pnlAtHigh = null;
//   let pnlAtHighPct = null;
//   let pnlAtLow = null;
//   let pnlAtLowPct = null;
//   let pnlCurrent = null;
//   let pnlCurrentPct = null;

//   if (position.entryPremium) {
//     const entryCost = position.entryPremium * 100; // Cost per contract

//     // P/L at Open (would you have profited if you sold at open?)
//     if (premiumData.dayOpen) {
//       pnlAtOpen = (premiumData.dayOpen - position.entryPremium) * 100;
//       pnlAtOpenPct = pnlAtOpen / entryCost;
//     }

//     // P/L at High (best possible profit)
//     if (premiumData.dayHigh) {
//       pnlAtHigh = (premiumData.dayHigh - position.entryPremium) * 100;
//       pnlAtHighPct = pnlAtHigh / entryCost;
//     }

//     // P/L at Low (worst case)
//     if (premiumData.dayLow) {
//       pnlAtLow = (premiumData.dayLow - position.entryPremium) * 100;
//       pnlAtLowPct = pnlAtLow / entryCost;
//     }

//     // Current P/L (closing premium vs entry)
//     if (premiumData.price) {
//       pnlCurrent = (premiumData.price - position.entryPremium) * 100;
//       pnlCurrentPct = pnlCurrent / entryCost;
//     }
//   }

//   // Calculate days to expiration
//   const daysToExp = Math.ceil((position.expDate - today) / (1000 * 60 * 60 * 24));

//   const tz = Session.getScriptTimeZone();
//   const lastDayIndex = Math.min(daysSinceEntry, MAX_TRACKING_DAYS - 1);

//   for (let dayOffset = 0; dayOffset <= lastDayIndex; dayOffset++) {
//     const targetDate = new Date(entryDate);
//     targetDate.setDate(entryDate.getDate() + dayOffset);
//     targetDate.setHours(0, 0, 0, 0);
//     const key = Utilities.formatDate(targetDate, tz, 'yyyy-MM-dd');

//     let dayData = null;

//     if (dayOffset === daysSinceEntry) {
//       dayData = {
//         open: premiumData.dayOpen || null,
//         high: premiumData.dayHigh || null,
//         low: premiumData.dayLow || null,
//         close: premiumData.price || null,
//         volume: premiumData.volume || 0
//       };
//     } else if (premiumHistoryMap[key]) {
//       dayData = premiumHistoryMap[key];
//     }

//     if (dayData && dayData.close !== null && dayData.close !== undefined) {
//       dayCheckValues[dayOffset] = dayData.close;
//     }

//     const ohlcEntry = {
//       o: dayData && dayData.open !== null && dayData.open !== undefined ? parseFloat(dayData.open).toFixed(2) : null,
//       h: dayData && dayData.high !== null && dayData.high !== undefined ? parseFloat(dayData.high).toFixed(2) : null,
//       l: dayData && dayData.low !== null && dayData.low !== undefined ? parseFloat(dayData.low).toFixed(2) : null,
//       c: dayData && dayData.close !== null && dayData.close !== undefined ? parseFloat(dayData.close).toFixed(2) : null,
//       v: dayData ? (dayData.volume || 0) : 0,
//       src: 'YAHOO'
//     };

//     ohlcVolumeArray[dayOffset] = ohlcEntry;

//     if (position.entryPremium && dayData && dayData.close !== null && dayData.close !== undefined) {
//       const entryCost = position.entryPremium * 100;
//       const pnl = (dayData.close - position.entryPremium) * 100;
//       const pnlPct = pnl / entryCost;
//       strikeHitArray[dayOffset] = pnlPct.toFixed(6);

//       if (dayData.high !== null && dayData.high !== undefined) {
//         const maxPnl = (dayData.high - position.entryPremium) * 100;
//         const maxPct = maxPnl / entryCost;
//         maxFavorableArray[dayOffset] = Math.max(maxPct, 0).toFixed(6);
//       }

//       if (dayData.low !== null && dayData.low !== undefined) {
//         const minPnl = (dayData.low - position.entryPremium) * 100;
//         const minPct = minPnl / entryCost;
//         minUnfavorableArray[dayOffset] = Math.min(minPct, 0).toFixed(6);
//       }
//     }
//   }

//   // Default any uninitialized OHLC entries up to tracking window
//   for (let i = 0; i < MAX_TRACKING_DAYS; i++) {
//     if (!ohlcVolumeArray[i]) {
//       ohlcVolumeArray[i] = { o: null, h: null, l: null, c: null, v: 0, src: 'YAHOO' };
//     }
//   }

//   // Determine first profitable day for Hit_Date
//   let hitDate = '';
//   if (position.entryPremium) {
//     for (let i = 0; i <= lastDayIndex; i++) {
//       const value = strikeHitArray[i];
//       if (value !== '0.000000' && value !== '' && !isNaN(parseFloat(value)) && parseFloat(value) > 0) {
//         hitDate = i;
//         break;
//       }
//     }
//   }

//   const row = [
//     dateStr,                                  // Entry date (runDate, not today!)
//     position.ticker,
//     position.strike,
//     position.optionType,
//     expDateStr,
//     stockData ? stockData.price || '' : '',
//     stockData ? stockData.dayHigh || '' : '',
//     stockData ? stockData.dayLow || '' : '',
//     JSON.stringify(strikeHitArray),           // Strike_Hit array
//     hitDate,                                   // Hit_Date (day number if profitable)
//     JSON.stringify(maxFavorableArray),        // Max_Favorable array
//     JSON.stringify(minUnfavorableArray),      // Min_Unfavorable array
//     ...dayCheckValues,                         // Day0-13 Check columns (only correct day populated)
//     '',                                        // Exp_Result (empty initially)
//     '',                                        // Risk_Reward (empty initially)
//     JSON.stringify(ohlcVolumeArray),          // OHLC_Volume array
//     position.entryPremium || '',              // Entry_Premium
//     premiumData.dayOpen || '',                // Premium_Open
//     premiumData.dayHigh || '',                // Premium_High
//     premiumData.dayLow || '',                 // Premium_Low
//     premiumData.price || '',                  // Premium_Current
//     premiumData.bid || '',                    // Bid
//     premiumData.ask || '',                    // Ask
//     spread !== null ? spread : '',            // Spread
//     premiumData.volume || 0,                  // Volume
//     premiumData.openInterest || 0,            // Open_Interest
//     pnlAtOpen !== null ? pnlAtOpen : '',      // PnL_At_Open
//     pnlAtOpenPct !== null ? Number(pnlAtOpenPct.toFixed(6)) : '',// PnL_At_Open_Pct
//     pnlAtHigh !== null ? pnlAtHigh : '',      // PnL_At_High
//     pnlAtHighPct !== null ? Number(pnlAtHighPct.toFixed(6)) : '',// PnL_At_High_Pct
//     pnlAtLow !== null ? pnlAtLow : '',        // PnL_At_Low
//     pnlAtLowPct !== null ? Number(pnlAtLowPct.toFixed(6)) : '',  // PnL_At_Low_Pct
//     pnlCurrent !== null ? pnlCurrent : '',    // PnL_Current
//     pnlCurrentPct !== null ? Number(pnlCurrentPct.toFixed(6)) : '',// PnL_Current_Pct
//     daysToExp                                  // Days_To_Exp
//   ];

//   // Append row
//   const lastRow = sheet.getLastRow();
//   const outputRange = sheet.getRange(lastRow + 1, 1, 1, row.length);
//   outputRange.setValues([row]);

//   // Format numbers
//   sheet.getRange(lastRow + 1, 6, 1, 3).setNumberFormat('$#,##0.00');    // Stock Price, High, Low (cols 6-8)
//   sheet.getRange(lastRow + 1, 13, 1, 14).setNumberFormat('$#,##0.00');  // Day0-13 Check (cols 13-26)
//   sheet.getRange(lastRow + 1, 30, 1, 5).setNumberFormat('$#,##0.00');   // Entry, Open, High, Low, Current (cols 30-34)
//   sheet.getRange(lastRow + 1, 35, 1, 2).setNumberFormat('$#,##0.00');   // Bid, Ask (cols 35-36)
//   sheet.getRange(lastRow + 1, 37, 1, 1).setNumberFormat('$#,##0.00');   // Spread (col 37)
//   sheet.getRange(lastRow + 1, 40, 1, 1).setNumberFormat('$#,##0.00');   // PnL_At_Open (col 40)
//   sheet.getRange(lastRow + 1, 41, 1, 1).setNumberFormat('0.00%');       // PnL_At_Open_Pct (col 41)
//   sheet.getRange(lastRow + 1, 42, 1, 1).setNumberFormat('$#,##0.00');   // PnL_At_High (col 42)
//   sheet.getRange(lastRow + 1, 43, 1, 1).setNumberFormat('0.00%');       // PnL_At_High_Pct (col 43)
//   sheet.getRange(lastRow + 1, 44, 1, 1).setNumberFormat('$#,##0.00');   // PnL_At_Low (col 44)
//   sheet.getRange(lastRow + 1, 45, 1, 1).setNumberFormat('0.00%');       // PnL_At_Low_Pct (col 45)
//   sheet.getRange(lastRow + 1, 46, 1, 1).setNumberFormat('$#,##0.00');   // PnL_Current (col 46)
//   sheet.getRange(lastRow + 1, 47, 1, 1).setNumberFormat('0.00%');       // PnL_Current_Pct (col 47)

//   // Conditional formatting for Hit_Date (col 10)
//   if (hitDate !== '') {
//     sheet.getRange(lastRow + 1, 10, 1, 1).setBackground('#D9EAD3').setFontWeight('bold'); // Green if hit
//   }

//   // Conditional formatting for PnL_At_Open (cols 40-41)
//   if (pnlAtOpen !== null) {
//     if (pnlAtOpen > 0) {
//       sheet.getRange(lastRow + 1, 40, 1, 2).setBackground('#D9EAD3'); // Light green
//     } else if (pnlAtOpen < 0) {
//       sheet.getRange(lastRow + 1, 40, 1, 2).setBackground('#F4CCCC'); // Light red
//     }
//   }

//   // Conditional formatting for PnL_At_High (cols 42-43)
//   if (pnlAtHigh !== null) {
//     if (pnlAtHigh > 0) {
//       sheet.getRange(lastRow + 1, 42, 1, 2).setBackground('#D9EAD3'); // Light green
//       sheet.getRange(lastRow + 1, 42, 1, 2).setFontWeight('bold'); // Bold for best case
//     } else if (pnlAtHigh < 0) {
//       sheet.getRange(lastRow + 1, 42, 1, 2).setBackground('#F4CCCC'); // Light red
//     }
//   }

//   // Conditional formatting for PnL_At_Low (cols 44-45)
//   if (pnlAtLow !== null) {
//     if (pnlAtLow > 0) {
//       sheet.getRange(lastRow + 1, 44, 1, 2).setBackground('#D9EAD3'); // Light green
//     } else if (pnlAtLow < 0) {
//       sheet.getRange(lastRow + 1, 44, 1, 2).setBackground('#F4CCCC'); // Light red
//       sheet.getRange(lastRow + 1, 44, 1, 2).setFontWeight('bold'); // Bold for worst case
//     }
//   }

//   // Conditional formatting for PnL_Current (cols 46-47) - most important
//   if (pnlCurrent !== null) {
//     if (pnlCurrent > 0) {
//       sheet.getRange(lastRow + 1, 46, 1, 2).setBackground('#B7E1CD'); // Darker green
//       sheet.getRange(lastRow + 1, 46, 1, 2).setFontWeight('bold');
//     } else if (pnlCurrent < 0) {
//       sheet.getRange(lastRow + 1, 46, 1, 2).setBackground('#EA9999'); // Darker red
//       sheet.getRange(lastRow + 1, 46, 1, 2).setFontWeight('bold');
//     } else {
//       sheet.getRange(lastRow + 1, 46, 1, 2).setBackground('#FFE599'); // Yellow for breakeven
//       sheet.getRange(lastRow + 1, 46, 1, 2).setFontWeight('bold');
//     }
//   }
// }

// /**
//  * Update selected positions only
//  */
// function EW_updateOptionsPremiumsSelected() {
//   const ss = SpreadsheetApp.getActive();
//   const sourceSheet = ss.getActiveSheet();
//   const selection = sourceSheet.getActiveRange();

//   if (sourceSheet.getName() !== 'Long Calls') {
//     SpreadsheetApp.getUi().alert('Please select rows in the Long Calls sheet');
//     return;
//   }

//   const startRow = selection.getRow();
//   const numRows = selection.getNumRows();

//   if (startRow === 1) {
//     SpreadsheetApp.getUi().alert('Please select data rows (not the header)');
//     return;
//   }

//   // Get output sheet
//   const outputSheetName = 'Long Calls Options';
//   let outputSheet = ss.getSheetByName(outputSheetName);

//   if (!outputSheet) {
//     outputSheet = ss.insertSheet(outputSheetName);
//     EW_setupOptionsPremiumSheet(outputSheet);
//   }

//   // Read headers
//   const headers = sourceSheet.getRange(1, 1, 1, sourceSheet.getLastColumn()).getValues()[0];
//   const hdrMap = {};

//   for (let i = 0; i < headers.length; i++) {
//     const header = String(headers[i]).toLowerCase().trim().replace(/\s+/g, '');
//     if (header === 'ticker') hdrMap.ticker = i;
//     if (header === 'strike') hdrMap.strike = i;
//     if (header === 'expdate' || header === 'expiration') hdrMap.expDate = i;
//     if (header === 'entry_premium' || header === 'entrypremium') hdrMap.entryPremium = i;
//   }

//   // Read selected rows
//   const data = sourceSheet.getRange(startRow, 1, numRows, sourceSheet.getLastColumn()).getValues();

//   let processed = 0;
//   let errors = [];

//   for (let i = 0; i < data.length; i++) {
//     const row = data[i];

//     const ticker = row[hdrMap.ticker];
//     const strike = parseFloat(row[hdrMap.strike]);
//     const expDate = new Date(row[hdrMap.expDate]);
//     const entryPremium = hdrMap.entryPremium !== undefined ? parseFloat(row[hdrMap.entryPremium]) : null;

//     if (!ticker || isNaN(strike) || !expDate) continue;

//     const position = {
//       ticker: ticker,
//       strike: strike,
//       expDate: expDate,
//       optionType: 'C',
//       entryPremium: entryPremium
//     };

//     try {
//       const premiumData = EW_fetchOptionPremium(position);

//       if (premiumData && premiumData.price !== null) {
//         EW_writeOptionPremiumRow(outputSheet, position, premiumData);
//         processed++;
//       }

//     } catch (error) {
//       errors.push(`${ticker}: ${error.message}`);
//     }
//   }

//   SpreadsheetApp.flush();

//   const msg = `Processed ${processed} of ${numRows} selected positions.` +
//     (errors.length > 0 ? `\n\nErrors:\n${errors.slice(0, 3).join('\n')}` : '');

//   SpreadsheetApp.getUi().alert('Update Complete', msg, SpreadsheetApp.getUi().ButtonSet.OK);
// }

// /**
//  * Test option symbol building and premium fetch
//  */
// function EW_testOptionPremiumFetch(sheetName) {
//   const ss = SpreadsheetApp.getActive();
//   const targetSheetName = sheetName || 'Long Calls';
//   const sheet = ss.getSheetByName(targetSheetName);

//   if (!sheet) {
//     Logger.log(`ERROR: Sheet "${targetSheetName}" not found`);
//     return [];
//   }

//   // Check if UI is available (fails in headless/testing contexts)
//   let ui = null;
//   try {
//     ui = SpreadsheetApp.getUi();
//   } catch (error) {
//     Logger.log('Running without UI');
//   }

//   const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
//   const hdrMap = {};

//   Logger.log('Headers found:');
//   for (let i = 0; i < headers.length; i++) {
//     Logger.log(`Column ${i}: "${headers[i]}"`);
//   }

//   for (let i = 0; i < headers.length; i++) {
//     const header = String(headers[i]).toLowerCase().trim().replace(/\s+/g, '');
//     if (header === 'ticker') hdrMap.ticker = i;
//     if (header === 'strike') hdrMap.strike = i;
//     if (header === 'expdate' || header === 'expiration') hdrMap.expDate = i;
//     if (header === 'rundate') hdrMap.runDate = i;
//   }

//   Logger.log('\nMapped columns:');
//   Logger.log(`ticker: ${hdrMap.ticker}`);
//   Logger.log(`strike: ${hdrMap.strike}`);
//   Logger.log(`expDate: ${hdrMap.expDate}`);
//   Logger.log(`runDate: ${hdrMap.runDate}`);

//   if (hdrMap.runDate === undefined) {
//     Logger.log('ERROR: Could not find Run Date column');
//     Logger.log('Looking for header that becomes "rundate" when lowercased and spaces removed');
//     return [];
//   }

//   const rowsToProcess = [];
//   let useLastDate = false;

//   if (ui) {
//     try {
//       const selection = ss.getSelection();
//       const activeRange = selection ? selection.getActiveRange() : null;

//       if (activeRange && activeRange.getSheet().getName() === sheet.getName()) {
//         const row = activeRange.getRow();
//         if (row > 1 && activeRange.getA1Notation() !== 'A1') {
//           rowsToProcess.push(row);
//         } else {
//           useLastDate = true;
//         }
//       } else {
//         useLastDate = true;
//       }
//     } catch (error) {
//       useLastDate = true;
//     }
//   } else {
//     useLastDate = true;
//   }

//   if (useLastDate) {
//     const lastRow = sheet.getLastRow();
//     if (lastRow <= 1) {
//       Logger.log('No data rows found');
//       return [];
//     }

//     const allData = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();

//     Logger.log('\nFirst 5 Run Date values:');
//     for (let i = 0; i < Math.min(5, allData.length); i++) {
//       const runDate = allData[i][hdrMap.runDate];
//       Logger.log(`Row ${i + 2}: ${runDate} (type: ${typeof runDate})`);
//     }

//     let latestDate = null;
//     let dateCount = 0;

//     for (let i = 0; i < allData.length; i++) {
//       const runDate = allData[i][hdrMap.runDate];
//       if (runDate) {
//         const dateValue = runDate instanceof Date ? runDate : new Date(runDate);
//         if (!isNaN(dateValue.getTime())) {
//           dateCount++;
//           if (!latestDate || dateValue > latestDate) {
//             latestDate = dateValue;
//           }
//         } else {
//           Logger.log(`Row ${i + 2}: Invalid date value: ${runDate}`);
//         }
//       }
//     }

//     Logger.log(`\nFound ${dateCount} valid dates`);

//     if (!latestDate) {
//       Logger.log('No valid dates found in Run Date column');
//       return [];
//     }

//     Logger.log(`Latest date: ${Utilities.formatDate(latestDate, Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss')}`);

//     for (let i = 0; i < allData.length; i++) {
//       const runDate = allData[i][hdrMap.runDate];
//       if (runDate) {
//         const dateValue = runDate instanceof Date ? runDate : new Date(runDate);
//         if (!isNaN(dateValue.getTime()) && dateValue.getTime() === latestDate.getTime()) {
//           rowsToProcess.push(i + 2);
//         }
//       }
//     }

//     Logger.log(`Processing ${rowsToProcess.length} rows from ${Utilities.formatDate(latestDate, Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss')}`);
//   }

//   if (rowsToProcess.length === 0) {
//     Logger.log('No rows selected for processing');
//     return [];
//   }

//   let yahooSession = null;
//   try {
//     yahooSession = EW_getYahooQuoteSession();
//   } catch (error) {
//     Logger.log(`WARNING: Unable to retrieve Yahoo session for debugging: ${error.message}`);
//   }

//   const results = [];

//   for (const row of rowsToProcess) {
//     const data = sheet.getRange(row, 1, 1, sheet.getLastColumn()).getValues()[0];

//     const ticker = data[hdrMap.ticker];
//     const strike = parseFloat(data[hdrMap.strike]);
//     const expDate = new Date(data[hdrMap.expDate]);

//     if (!ticker || isNaN(strike) || isNaN(expDate.getTime())) {
//       Logger.log(`Row ${row}: Invalid data (Ticker: ${ticker}, Strike: ${strike}, ExpDate: ${data[hdrMap.expDate]})`);
//       continue;
//     }

//     const position = {
//       ticker: ticker,
//       strike: strike,
//       expDate: expDate,
//       optionType: 'C'
//     };

//     const optionSymbol = EW_buildOptionSymbol(ticker, expDate, 'C', strike);
//     Logger.log(`Row ${row}: Option Symbol: ${optionSymbol}`);

//     if (yahooSession) {
//       Logger.log('\n=== API CALL DEBUG ===');
//       Logger.log(`URL: https://query1.finance.yahoo.com/v7/finance/quote`);
//       Logger.log(`Params: ${JSON.stringify({ symbols: optionSymbol, crumb: yahooSession.crumb })}`);
//       Logger.log(`Full URL: https://query1.finance.yahoo.com/v7/finance/quote?symbols=${optionSymbol}&crumb=${yahooSession.crumb}`);
//       Logger.log(`Headers: ${JSON.stringify({ 'User-Agent': 'Mozilla/5.0...', Cookie: yahooSession.cookie })}`);
//       Logger.log('======================\n');
//     }

//     const premiumData = EW_fetchOptionPremium(position);

//     if (!premiumData) {
//       Logger.log(`No data returned for ${ticker} ${strike} Call`);
//       continue;
//     }

//     const result = {
//       row: row,
//       ticker: ticker,
//       strike: strike,
//       expDate: expDate,
//       optionSymbol: optionSymbol,
//       premium: premiumData.price,
//       dayHigh: premiumData.dayHigh,
//       dayLow: premiumData.dayLow,
//       bid: premiumData.bid,
//       ask: premiumData.ask,
//       volume: premiumData.volume,
//       openInterest: premiumData.openInterest
//     };

//     results.push(result);

//     Logger.log(`${ticker} Premium: $${premiumData.price}`);
//     Logger.log(`Day Range: $${premiumData.dayLow} - $${premiumData.dayHigh}`);
//     Logger.log(`Bid/Ask: $${premiumData.bid} / $${premiumData.ask}`);
//   }

//   if (results.length === 0) {
//     Logger.log('No data could be fetched');
//     return [];
//   }

//   Logger.log('\n========== OPTION PREMIUM RESULTS ==========');
//   for (const result of results) {
//     Logger.log(`\n${result.ticker} $${result.strike} Call (${result.optionSymbol})`);
//     Logger.log(`  Premium: $${result.premium.toFixed(2)}`);
//     Logger.log(`  Day Range: $${result.dayLow.toFixed(2)} - $${result.dayHigh.toFixed(2)}`);
//     Logger.log(`  Bid/Ask: $${result.bid.toFixed(2)} / $${result.ask.toFixed(2)}`);
//     Logger.log(`  Volume: ${result.volume}, OI: ${result.openInterest}`);
//   }
//   Logger.log('============================================\n');

//   if (ui) {
//     if (results.length === 1) {
//       const result = results[0];
//       const msg = `${result.ticker} $${result.strike} Call (${Utilities.formatDate(result.expDate, Session.getScriptTimeZone(), 'MMM dd yyyy')})\n\n` +
//         `Option Symbol: ${result.optionSymbol}\n\n` +
//         `Premium: $${result.premium.toFixed(2)}\n` +
//         `Day High: $${result.dayHigh.toFixed(2)}\n` +
//         `Day Low: $${result.dayLow.toFixed(2)}\n` +
//         `Bid/Ask: $${result.bid.toFixed(2)} / $${result.ask.toFixed(2)}\n` +
//         `Volume: ${result.volume}\n` +
//         `Open Interest: ${result.openInterest}`;

//       ui.alert('Premium Data', msg, ui.ButtonSet.OK);
//     } else {
//       let msg = `Fetched ${results.length} option premiums:\n\n`;

//       for (const result of results) {
//         const expDateStr = Utilities.formatDate(result.expDate, Session.getScriptTimeZone(), 'MM/dd');
//         msg += `${result.ticker} $${result.strike} (${expDateStr}): $${result.premium.toFixed(2)} `;
//         msg += `[${result.dayLow.toFixed(2)}-${result.dayHigh.toFixed(2)}]\n`;
//       }

//       msg += '\nCheck logs for detailed data (View > Logs).';

//       ui.alert('Premium Data Summary', msg, ui.ButtonSet.OK);
//     }
//   }

//   return results;
// }
// */

// // END OF COMMENTED OUT CODE
// // All functions have been migrated to 27_OptionsPremiumBackfill.js
// // Use that file for all options premium backfilling functionality
