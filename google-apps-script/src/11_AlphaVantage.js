/**
 * Alpha Vantage API Integration
 * Fetches 1-minute intraday historical data for strike analysis
 * API Documentation: https://www.alphavantage.co/documentation/#intraday
 *
 * Key Differences from Yahoo Finance:
 * - Requires API key (stored in Script Properties as ALPHA_VANTAGE_API_KEY)
 * - Free tier limits: 25 requests/day, 5 requests/minute
 * - Returns data in different JSON format
 * - Cache strategy is per ticker/date (no strike needed in API call)
 */

/**
 * Check if cached Alpha Vantage data exists for a ticker and date
 * @param {string} ticker - Ticker symbol
 * @param {Date} date - Target date
 * @returns {Object|null} Cached data if found and valid, null otherwise
 */
function AV_checkCachedData(ticker, date) {
  try {
    const dateStr = EW_formatDate(date);
    const folderIdProp = EW.PROPS.getProperty('API_LOGS_FOLDER_ID');

    if (!folderIdProp) {
      console.log('AV CACHE: API_LOGS_FOLDER_ID not set, skipping cache check');
      return null;
    }

    const folder = DriveApp.getFolderById(folderIdProp);
    const filePattern = `AV_${ticker}_${dateStr}`;
    const files = folder.getFilesByName(filePattern + '.json');

    if (files.hasNext()) {
      const file = files.next();
      const content = file.getBlob().getDataAsString();
      const cachedData = JSON.parse(content);

      // Validate cached data structure
      if (cachedData.response && cachedData.response['Time Series (1min)']) {
        console.log(`AV CACHE HIT: Found cached data for ${ticker} on ${dateStr}`);
        return cachedData;
      } else {
        console.log(`AV CACHE INVALID: Cached file for ${ticker} on ${dateStr} has invalid structure`);
        // Delete invalid cache file
        file.setTrashed(true);
        return null;
      }
    }

    console.log(`AV CACHE MISS: No cached data for ${ticker} on ${dateStr}`);
    return null;
  } catch (error) {
    console.error(`AV CACHE ERROR: Error checking cache for ${ticker}: ${error.message}`);
    return null;
  }
}

/**
 * Save Alpha Vantage API response to cache
 * @param {string} ticker - Ticker symbol
 * @param {Date} date - Target date
 * @param {Object} response - API response to cache
 * @param {Object} metadata - Additional metadata
 * @returns {boolean} True if saved successfully
 */
function AV_saveApiResponse(ticker, date, response, metadata = {}) {
  try {
    const dateStr = EW_formatDate(date);
    const timestamp = EW_formatDateTime(new Date());
    const folderIdProp = EW.PROPS.getProperty('API_LOGS_FOLDER_ID');

    if (!folderIdProp) {
      console.log('AV CACHE: API_LOGS_FOLDER_ID not set, skipping cache save');
      return false;
    }

    const folder = DriveApp.getFolderById(folderIdProp);
    const fileName = `AV_${ticker}_${dateStr}.json`;

    // Check if file already exists and delete it
    const existingFiles = folder.getFilesByName(fileName);
    while (existingFiles.hasNext()) {
      existingFiles.next().setTrashed(true);
    }

    // Create cache data structure
    const cacheData = {
      ticker: ticker,
      date: dateStr,
      timestamp: timestamp,
      source: 'alphavantage',
      interval: '1min',
      metadata: metadata,
      response: response
    };

    // Save to Drive
    folder.createFile(
      fileName,
      JSON.stringify(cacheData, null, 2),
      MimeType.PLAIN_TEXT
    );

    console.log(`AV CACHE: Saved response for ${ticker} on ${dateStr}`);
    return true;
  } catch (error) {
    console.error(`AV CACHE ERROR: Failed to save cache for ${ticker}: ${error.message}`);
    return false;
  }
}

/**
 * Fetch intraday data from Alpha Vantage API
 * @param {string} ticker - Ticker symbol
 * @param {Date} date - Target date (for cache key and logging only)
 * @returns {Object} API response or error object
 */
function AV_fetchIntradayData(ticker, date) {
  try {
    const apiKey = EW.ALPHA_VANTAGE.API_KEY;

    if (!apiKey) {
      return {
        error: true,
        message: 'Alpha Vantage API key not configured',
        ticker: ticker,
        date: date
      };
    }

    // Check cache first
    const cachedData = AV_checkCachedData(ticker, date);
    if (cachedData) {
      return {
        data: AV_parseApiResponse(cachedData.response),
        fromCache: true,
        ticker: ticker,
        date: date
      };
    }

    // Build API URL
    const url = `${EW.ALPHA_VANTAGE.BASE_URL}?function=TIME_SERIES_INTRADAY&symbol=${ticker}&interval=${EW.ALPHA_VANTAGE.DEFAULT_INTERVAL}&apikey=${apiKey}&outputsize=${EW.ALPHA_VANTAGE.OUTPUT_SIZE}`;

    console.log(`AV API: Fetching intraday data for ${ticker} on ${EW_formatDate(date)}`);

    // Make API request
    const response = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });

    const responseCode = response.getResponseCode();

    if (responseCode !== 200) {
      return {
        error: true,
        message: `API returned status code ${responseCode}`,
        ticker: ticker,
        date: date,
        responseCode: responseCode
      };
    }

    const jsonResponse = JSON.parse(response.getContentText());

    // Check for API errors
    if (jsonResponse['Error Message']) {
      return {
        error: true,
        message: jsonResponse['Error Message'],
        ticker: ticker,
        date: date
      };
    }

    if (jsonResponse['Note']) {
      // Rate limit hit
      return {
        error: true,
        message: 'Alpha Vantage API rate limit exceeded',
        note: jsonResponse['Note'],
        ticker: ticker,
        date: date,
        rateLimited: true
      };
    }

    // Save to cache
    AV_saveApiResponse(ticker, date, jsonResponse, {
      fetchedAt: EW_formatDateTime(new Date()),
      responseCode: responseCode
    });

    // Log the API call
    EW_logApiCall({
      source: 'alphavantage',
      ticker: ticker,
      interval: '1min',
      dateRequested: EW_formatDate(date),
      timestamp: EW_formatDateTime(new Date()),
      responseCode: responseCode,
      success: true
    });

    return {
      data: AV_parseApiResponse(jsonResponse),
      fromCache: false,
      ticker: ticker,
      date: date
    };

  } catch (error) {
    console.error(`AV API ERROR: ${ticker} - ${error.message}`);

    // Log the failed API call
    EW_logApiCall({
      source: 'alphavantage',
      ticker: ticker,
      interval: '1min',
      dateRequested: EW_formatDate(date),
      timestamp: EW_formatDateTime(new Date()),
      success: false,
      error: error.message
    });

    return {
      error: true,
      message: error.message,
      ticker: ticker,
      date: date
    };
  }
}

/**
 * Parse Alpha Vantage API response into standardized format
 * @param {Object} apiResponse - Raw Alpha Vantage API response
 * @returns {Array} Array of {timestamp, open, high, low, close, volume}
 */
function AV_parseApiResponse(apiResponse) {
  try {
    const timeSeries = apiResponse['Time Series (1min)'];

    if (!timeSeries) {
      console.error('AV PARSE ERROR: No time series data in response');
      return [];
    }

    const dataPoints = [];

    // Alpha Vantage format: "2024-01-15 09:30:00": { "1. open": "150.00", ... }
    for (const timestamp in timeSeries) {
      const point = timeSeries[timestamp];
      dataPoints.push({
        timestamp: new Date(timestamp + ' EST'), // Alpha Vantage uses EST
        open: parseFloat(point['1. open']),
        high: parseFloat(point['2. high']),
        low: parseFloat(point['3. low']),
        close: parseFloat(point['4. close']),
        volume: parseInt(point['5. volume'])
      });
    }

    // Sort by timestamp (oldest first)
    dataPoints.sort((a, b) => a.timestamp - b.timestamp);

    console.log(`AV PARSE: Parsed ${dataPoints.length} data points`);
    return dataPoints;

  } catch (error) {
    console.error(`AV PARSE ERROR: ${error.message}`);
    return [];
  }
}

/**
 * Filter intraday data to a specific date
 * @param {Array} dataPoints - Array of parsed data points
 * @param {Date} targetDate - Date to filter for
 * @returns {Array} Filtered data points for the target date
 */
function AV_filterDataByDate(dataPoints, targetDate) {
  const targetDateStr = EW_formatDate(targetDate);

  const filtered = dataPoints.filter(point => {
    const pointDateStr = EW_formatDate(point.timestamp);
    return pointDateStr === targetDateStr;
  });

  console.log(`AV FILTER: Filtered to ${filtered.length} points for ${targetDateStr}`);
  return filtered;
}

/**
 * Analyze if strike was hit based on intraday data
 * @param {Array} dataPoints - Intraday data points
 * @param {number} strike - Strike price to check
 * @param {string} strategyType - Strategy type (bullish/bearish)
 * @returns {Object} Analysis result with hit status, day high/low, etc.
 */
function AV_analyzeStrikeHit(dataPoints, strike, strategyType) {
  try {
    if (!dataPoints || dataPoints.length === 0) {
      return {
        hit: false,
        error: 'No data points available',
        dayHigh: null,
        dayLow: null,
        dayOpen: null,
        dayClose: null,
        dayVolume: 0
      };
    }

    // Calculate day aggregates
    const dayHigh = Math.max(...dataPoints.map(p => p.high));
    const dayLow = Math.min(...dataPoints.map(p => p.low));
    const dayOpen = dataPoints[0].open;
    const dayClose = dataPoints[dataPoints.length - 1].close;
    const dayVolume = dataPoints.reduce((sum, p) => sum + p.volume, 0);

    // Determine if strike was hit based on strategy type
    let hit = false;
    let hitTime = null;

    // Determine if strategy is bullish or bearish
    const isBullish = EW_STRATEGY_TYPES.BULLISH.includes(strategyType);
    const isBearish = EW_STRATEGY_TYPES.BEARISH.includes(strategyType);

    for (const point of dataPoints) {
      if (isBullish) {
        // Bullish: strike is hit if price >= strike
        if (point.high >= strike) {
          hit = true;
          hitTime = point.timestamp;
          break;
        }
      } else if (isBearish) {
        // Bearish: strike is hit if price <= strike
        if (point.low <= strike) {
          hit = true;
          hitTime = point.timestamp;
          break;
        }
      } else {
        // Neutral or other: check if price touched strike
        if (point.low <= strike && point.high >= strike) {
          hit = true;
          hitTime = point.timestamp;
          break;
        }
      }
    }

    return {
      hit: hit,
      hitTime: hitTime,
      dayHigh: dayHigh,
      dayLow: dayLow,
      dayOpen: dayOpen,
      dayClose: dayClose,
      dayVolume: dayVolume,
      dataPoints: dataPoints.length,
      strike: strike,
      strategyType: strategyType
    };

  } catch (error) {
    console.error(`AV ANALYSIS ERROR: ${error.message}`);
    return {
      hit: false,
      error: error.message,
      dayHigh: null,
      dayLow: null,
      dayOpen: null,
      dayClose: null,
      dayVolume: 0
    };
  }
}

/**
 * Main function to check if strike was hit on a specific date
 * Combines fetch and analysis
 * @param {string} ticker - Ticker symbol
 * @param {number} strike - Strike price
 * @param {Date} date - Target date
 * @param {string} strategyType - Strategy type
 * @returns {Object} Complete analysis result
 */
function AV_checkStrikeHit(ticker, strike, date, strategyType) {
  try {
    // Check if date is a weekend
    const dayOfWeek = date.getDay();
    if (dayOfWeek === 0 || dayOfWeek === 6) {
      const dayName = dayOfWeek === 0 ? 'Sunday' : 'Saturday';
      console.log(`AV: Skipping ${ticker} on ${EW_formatDate(date)} (${dayName}) - markets closed`);
      return {
        ticker: ticker,
        strike: strike,
        date: date,
        skipped: true,
        reason: 'weekend',
        dayOfWeek: dayName,
        hit: false
      };
    }

    // Fetch intraday data (from cache or API)
    const fetchResult = AV_fetchIntradayData(ticker, date);

    if (fetchResult.error) {
      return {
        ticker: ticker,
        strike: strike,
        date: date,
        error: true,
        message: fetchResult.message,
        hit: false
      };
    }

    // Filter data to target date
    const dayData = AV_filterDataByDate(fetchResult.data, date);

    // Analyze if strike was hit
    const analysis = AV_analyzeStrikeHit(dayData, strike, strategyType);

    return {
      ticker: ticker,
      strike: strike,
      date: date,
      fromCache: fetchResult.fromCache,
      ...analysis
    };

  } catch (error) {
    console.error(`AV CHECK ERROR: ${ticker} - ${error.message}`);
    return {
      ticker: ticker,
      strike: strike,
      date: date,
      error: true,
      message: error.message,
      hit: false
    };
  }
}

/**
 * Process multiple positions from spreadsheet using Alpha Vantage
 * @param {Sheet} sheet - Spreadsheet sheet
 * @param {string} strategyName - Strategy name
 * @param {Array} rowNumbers - Array of row numbers to process (optional, processes all if not provided)
 * @returns {Object} Processing results summary
 */
function AV_processSpreadsheetPositions(sheet, strategyName, rowNumbers = null) {
  try {
    console.log(`AV PROCESS: Starting processing for ${strategyName}`);

    const hdrMap = EW_getHeaderMap(sheet);

    // Validate required columns
    if (!hdrMap.tickerCol) {
      return { error: true, message: 'Missing Ticker column' };
    }

    if (!hdrMap.runDateCol) {
      return { error: true, message: 'Missing Run Date column' };
    }

    // Determine strike column (handle spreads)
    const isSpread = strategyName.includes('Spread');
    const strikeCol = isSpread ? hdrMap.longStrikeCol : hdrMap.strikeCol;

    if (!strikeCol) {
      return { error: true, message: 'Missing Strike column' };
    }

    const lastRow = sheet.getLastRow();
    const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();

    let processed = 0;
    let updated = 0;
    let errors = [];
    let cached = 0;
    let fetched = 0;

    // Determine which rows to process
    const rowsToProcess = rowNumbers || Array.from({ length: data.length }, (_, i) => i + 2);

    for (const rowNum of rowsToProcess) {
      const rowIndex = rowNum - 2;
      if (rowIndex < 0 || rowIndex >= data.length) continue;

      const row = data[rowIndex];

      // Get required fields
      const ticker = row[hdrMap.tickerCol - 1];
      const runDateStr = row[hdrMap.runDateCol - 1];
      const strike = parseFloat(row[strikeCol - 1]);

      if (!ticker || !runDateStr || !strike || isNaN(strike)) {
        continue;
      }

      const runDate = new Date(runDateStr);

      // Check strike using Alpha Vantage
      const result = AV_checkStrikeHit(ticker, strike, runDate, strategyName);

      processed++;

      if (result.error) {
        errors.push(`Row ${rowNum}: ${ticker} - ${result.message}`);
        continue;
      }

      if (result.skipped) {
        continue;
      }

      if (result.fromCache) {
        cached++;
      } else {
        fetched++;
      }

      // Update spreadsheet with results
      // Update Day0_Check column if available
      if (hdrMap.day0CheckCol && result.dayClose) {
        sheet.getRange(rowNum, hdrMap.day0CheckCol).setValue(result.dayClose);
        updated++;
      }

      // Log the result
      console.log(`Row ${rowNum}: ${ticker} Strike ${strike} - Hit: ${result.hit}, High: ${result.dayHigh}, Low: ${result.dayLow}`);
    }

    return {
      success: true,
      processed: processed,
      updated: updated,
      cached: cached,
      fetched: fetched,
      errors: errors
    };

  } catch (error) {
    console.error(`AV PROCESS ERROR: ${error.message}`);
    return {
      error: true,
      message: error.message
    };
  }
}
