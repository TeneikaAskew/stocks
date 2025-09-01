/**
 * Comprehensive Success Report Analysis
 * Analyzes trading performance across multiple dimensions to identify winning patterns
 * 
 * KEY INSIGHTS GENERATED:
 * 1. Multi-day profitability analysis - tracks plays that stay profitable over time
 * 2. Indicator effectiveness - identifies which indicators correlate with success
 * 3. Earnings timing analysis - pre/post earnings play performance
 * 4. Risk/reward optimization - identifies optimal entry/exit patterns
 * 5. Strategy-specific insights - performance by strategy type
 * 
 * DATA ANALYZED:
 * - Max_Favorable/Min_Unfavorable arrays (day-by-day price movements)
 * - Day0-Day5 checks (actual prices at each day)
 * - All indicator arrays (RSI, SMA, EMA, VWAP, etc.)
 * - Earnings dates vs hit dates
 * - Risk/reward ratios
 */

/**
 * Helper function to format dates for report display
 */
function EW_formatDateForReport(dateValue) {
  if (!dateValue) return 'N/A';
  
  try {
    if (dateValue instanceof Date) {
      return dateValue.toISOString().split('T')[0]; // YYYY-MM-DD format
    } else if (typeof dateValue === 'string') {
      // If already a string, try to parse and reformat
      const date = new Date(dateValue);
      if (!isNaN(date.getTime())) {
        return date.toISOString().split('T')[0];
      }
      return dateValue; // Return as-is if can't parse
    }
    return 'N/A';
  } catch (e) {
    return 'N/A';
  }
}


/**
 * Calculate profit factor from observations
 */
function SR_calculateProfitFactor(observations) {
  let sumWins = 0;
  let sumLosses = 0;
  
  observations.forEach(obs => {
    if (obs.profit > 0) {
      sumWins += obs.profit;
    } else {
      sumLosses += Math.abs(obs.profit);
    }
  });
  
  return sumLosses > 0 ? sumWins / sumLosses : null;
}

/**
 * Main function to generate comprehensive success report
 * Creates a new sheet with deep insights and analysis
 */
function EW_generateSuccessReport() {
  const startTime = new Date();
  console.log('=== GENERATING COMPREHENSIVE SUCCESS REPORT ===');
  
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  
  // Collect all data
  const allTrades = [];
  
  for (const strategy of strategies) {
    const sheet = ss.getSheetByName(strategy);
    if (!sheet || sheet.getLastRow() < 2) continue;
    
    const trades = EW_extractTradeData(sheet, strategy);
    allTrades.push(...trades);
  }
  
  console.log(`Collected ${allTrades.length} trades for analysis`);
  
  // Perform analyses
  const insights = {
    overview: EW_analyzeOverview(allTrades),
    dataQuality: EW_analyzeDataQuality(allTrades),
    holdingPeriod: EW_analyzeHoldingPeriod(allTrades),
    multiDayProfitability: EW_analyzeMultiDayProfitability(allTrades),
    indicatorEffectiveness: EW_analyzeIndicatorEffectiveness(allTrades),
    earningsTiming: EW_analyzeEarningsTiming(allTrades),
    riskRewardPatterns: EW_analyzeRiskRewardPatterns(allTrades),
    strategyPerformance: EW_analyzeStrategyPerformance(allTrades),
    topPlays: EW_identifyTopPlays(allTrades),
    mlReadyData: EW_prepareMachineLearningData(allTrades)
  };
  
  // Create report sheet
  EW_createReportSheet(ss, insights, allTrades);
  
  // Create individual analysis sheets
  insights.allTrades = allTrades; // Add trades to insights for data quality analysis
  EW_createIndividualSheets(ss, insights);
  
  // Create indicator profiles sheet
  EW_createIndicatorProfilesSheet(ss, insights.topPlays);
  
  // Store data for web app access
  if (typeof storeSuccessReportData === 'function') {
    storeSuccessReportData(insights);
  }
  
  const duration = Math.round((new Date() - startTime) / 1000);
  console.log(`Success report generated in ${duration} seconds`);
  
  // Use safe alert that handles trigger context properly
  EW_safeAlert(
    'Success Report Generated',
    `Analysis complete. Processed ${allTrades.length} trades in ${duration} seconds.\n\n` +
    `Check the "Success_Report" sheet for insights.`
  );
}

/**
 * Update success report - alias for generate
 * This is called from the menu for clarity
 */
function EW_updateSuccessReport() {
  EW_generateSuccessReport();
}

/**
 * Create a separate sheet for indicator profiles
 * This prevents the main report from becoming too wide
 */
function EW_createIndicatorProfilesSheet(ss, topPlays) {
  const sheetName = 'Indicator_Profiles';
  let sheet = ss.getSheetByName(sheetName);
  
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
  } else {
    sheet.clear();
  }
  
  // Title
  sheet.getRange(1, 1).setValue('TOP WINNING PLAYS - INDICATOR PROFILES').setFontSize(16).setFontWeight('bold');
  sheet.getRange(1, 6).setValue(new Date().toLocaleString());
  
  let row = 3;
  
  // Headers for the detailed view
  const headers = ['Rank', 'Ticker', 'Max Profit %', 'Strategy', 'Days to Hit', 'Strike'];
  sheet.getRange(row, 1, 1, headers.length).setValues([headers]).setFontWeight('bold').setBackground('#f0f0f0');
  row++;
  
  topPlays.slice(0, 20).forEach((play, index) => {
    // Basic info row
    sheet.getRange(row, 1).setValue(index + 1);
    sheet.getRange(row, 2).setValue(play.ticker).setFontWeight('bold');
    sheet.getRange(row, 3).setValue((play.maxProfit || 0).toFixed(2) + '%');  // Already in percentage form
    sheet.getRange(row, 4).setValue(play.strategy);
    sheet.getRange(row, 5).setValue(play.daysToHit || 'N/A');
    sheet.getRange(row, 6).setValue(play.strike);
    
    // Apply alternating row colors
    if (index % 2 === 0) {
      sheet.getRange(row, 1, 1, 6).setBackground('#f9f9f9');
    }
    row++;
    
    // Indicator movement (Entry → Hit)
    sheet.getRange(row, 2).setValue('Entry → Hit:').setFontStyle('italic');
    sheet.getRange(row, 3, 1, 4).merge().setValue(play.indicatorProfile || 'N/A');
    row++;
    
    // Multi-day profit profile
    sheet.getRange(row, 2).setValue('Profit Profile:').setFontStyle('italic');
    sheet.getRange(row, 3, 1, 4).merge().setValue(play.multiDayProfile || 'N/A');
    row++;
    
    // Risk/Reward info if available
    if (play.riskReward) {
      sheet.getRange(row, 2).setValue('Risk/Reward:').setFontStyle('italic');
      sheet.getRange(row, 3).setValue(play.riskReward).setNumberFormat('0.00');
      row++;
    }
    
    // Add spacing between entries
    row++;
  });
  
  // Add summary section at the bottom
  row += 2;
  sheet.getRange(row, 1).setValue('KEY INSIGHTS').setFontSize(14).setFontWeight('bold');
  row += 2;
  
  // Analyze common patterns
  const patterns = analyzeIndicatorPatterns(topPlays.slice(0, 20));
  
  sheet.getRange(row, 1).setValue('Common Winning Patterns:').setFontWeight('bold');
  row++;
  
  if (patterns.rsiRange) {
    sheet.getRange(row, 2).setValue(`• RSI Range: ${patterns.rsiRange}`);
    row++;
  }
  if (patterns.sma20Range) {
    sheet.getRange(row, 2).setValue(`• Price vs SMA20: ${patterns.sma20Range}`);
    row++;
  }
  if (patterns.vwapRange) {
    sheet.getRange(row, 2).setValue(`• Price vs VWAP: ${patterns.vwapRange}`);
    row++;
  }
  if (patterns.bestDayToExit) {
    sheet.getRange(row, 2).setValue(`• Best Day to Exit: ${patterns.bestDayToExit}`);
    row++;
  }
  
  // Auto-resize columns
  sheet.autoResizeColumns(1, 6);
  
  // Set column widths for better readability
  sheet.setColumnWidth(1, 50);  // Rank
  sheet.setColumnWidth(2, 100); // Ticker
  sheet.setColumnWidth(3, 400); // Expanded for merged cells
  
  console.log(`Created Indicator Profiles sheet with ${topPlays.slice(0, 20).length} trades`);
}

/**
 * Analyze common patterns in winning trades
 */
function analyzeIndicatorPatterns(trades) {
  const patterns = {};
  const rsiValues = [];
  const sma20Values = [];
  const vwapValues = [];
  const profitDays = [];
  
  trades.forEach(trade => {
    // Extract RSI values from indicator profile
    if (trade.indicatorProfile && trade.indicatorProfile.includes('RSI:')) {
      const rsiMatch = trade.indicatorProfile.match(/RSI:\s*[^→]*→([\d.]+)/);
      if (rsiMatch) rsiValues.push(parseFloat(rsiMatch[1]));
    }
    
    // Extract SMA20 values
    if (trade.indicatorProfile && trade.indicatorProfile.includes('PRICEVSSMA20:')) {
      const smaMatch = trade.indicatorProfile.match(/PRICEVSSMA20:\s*[^→]*→([\-\d.]+)/);
      if (smaMatch) sma20Values.push(parseFloat(smaMatch[1]));
    }
    
    // Extract VWAP values
    if (trade.indicatorProfile && trade.indicatorProfile.includes('PRICEVSVWAP:')) {
      const vwapMatch = trade.indicatorProfile.match(/PRICEVSVWAP:\s*[^→]*→([\-\d.]+)/);
      if (vwapMatch) vwapValues.push(parseFloat(vwapMatch[1]));
    }
    
    // Find best profit day
    if (trade.multiDayProfile) {
      const dayMatches = trade.multiDayProfile.matchAll(/D(\d):[\-\d.]+%/g);
      for (const match of dayMatches) {
        profitDays.push(parseInt(match[1]));
      }
    }
  });
  
  // Calculate ranges
  if (rsiValues.length > 0) {
    const minRsi = Math.min(...rsiValues);
    const maxRsi = Math.max(...rsiValues);
    patterns.rsiRange = `${minRsi.toFixed(1)} - ${maxRsi.toFixed(1)}`;
  }
  
  if (sma20Values.length > 0) {
    const minSma = Math.min(...sma20Values);
    const maxSma = Math.max(...sma20Values);
    patterns.sma20Range = `${minSma.toFixed(2)}% - ${maxSma.toFixed(2)}%`;
  }
  
  if (vwapValues.length > 0) {
    const minVwap = Math.min(...vwapValues);
    const maxVwap = Math.max(...vwapValues);
    patterns.vwapRange = `${minVwap.toFixed(2)}% - ${maxVwap.toFixed(2)}%`;
  }
  
  if (profitDays.length > 0) {
    const dayCount = {};
    profitDays.forEach(day => {
      dayCount[day] = (dayCount[day] || 0) + 1;
    });
    const bestDay = Object.entries(dayCount).sort((a, b) => b[1] - a[1])[0];
    patterns.bestDayToExit = `Day ${bestDay[0]} (${bestDay[1]} occurrences)`;
  }
  
  return patterns;
}

/**
 * Extract and parse all trade data from a sheet
 */
function EW_extractTradeData(sheet, strategy) {
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Get all data
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];
  
  const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  console.log(`Extracting data from ${strategy} sheet: ${lastRow} total rows, ${data.length} data rows`);
  
  const trades = [];
  
  let skippedRows = 0;
  let emptyRows = 0;
  
  data.forEach((row, idx) => {
    // Skip empty rows (no ticker)
    if (!row[hdrMap.tickerCol - 1] || row[hdrMap.tickerCol - 1] === '') {
      emptyRows++;
      return;
    }
    
    // Skip rows without Run Date (these are not valid trades)
    if (!row[hdrMap.runDateCol - 1] || row[hdrMap.runDateCol - 1] === '') {
      skippedRows++;
      return;
    }
    
    try {
      const trade = {
        // Basic info
        strategy: strategy,
        ticker: row[hdrMap.tickerCol - 1],
        company: row[hdrMap.companyCol - 1] || row[hdrMap.tickerCol - 1], // Fallback to ticker if no company
        runDate: row[hdrMap.runDateCol - 1],
        expDate: row[hdrMap.expDateCol - 1],
        strike: parseFloat(row[hdrMap.strikeCol - 1]) || 0,
        longStrike: parseFloat(row[hdrMap.longStrikeCol - 1]) || 0,
        shortStrike: parseFloat(row[hdrMap.shortStrikeCol - 1]) || 0,
        
        // Pricing context at entry
        price: parseFloat(row[hdrMap.priceCol - 1]) || 0,
        lastTrade: parseFloat(row[hdrMap.lastTradeCol - 1]) || 0,
        bid: parseFloat(row[hdrMap.bidCol - 1]) || 0,
        ask: parseFloat(row[hdrMap.askCol - 1]) || 0,
        openInterest: parseFloat(row[hdrMap.openInterestCol - 1]) || 0,
        volume: parseFloat(row[hdrMap.volumeCol - 1]) || 0,
        
        // GoogleFinance snapshot fields
        gfPrice: parseFloat(row[hdrMap.priceCol - 1]) || 0,
        gfChangePct: parseFloat(row[hdrMap.chgPctCol - 1]) || 0,
        gfVolume: parseFloat(row[hdrMap.volCol - 1]) || 0,
        gfAvgVol10: parseFloat(row[hdrMap.avgVol10Col - 1]) || 0,
        gfHigh52: parseFloat(row[hdrMap.high52Col - 1]) || 0,
        gfLow52: parseFloat(row[hdrMap.low52Col - 1]) || 0,
        gfMktCap: parseFloat(row[hdrMap.mcapCol - 1]) || 0,
        gfPE: parseFloat(row[hdrMap.peCol - 1]) || 0,
        gfBeta: parseFloat(row[hdrMap.betaCol - 1]) || 0,
        
        // Volatility & returns
        hv30D: parseFloat(row[hdrMap.hv30Col - 1]) || 0,
        rvol10: parseFloat(row[hdrMap.rvol10Col - 1]) || 0,
        ret5D: parseFloat(row[hdrMap.ret5Col - 1]) || 0,
        ret20D: parseFloat(row[hdrMap.ret20Col - 1]) || 0,
        gapPct: parseFloat(row[hdrMap.gapPctCol - 1]) || 0,
        
        // Dates
        nextEPSDate: row[hdrMap.nextEPSDateCol - 1],
        releaseTime: parseFloat(row[hdrMap.releaseTimeCol - 1]) || 0,
        hitDate: row[hdrMap.hitDateCol - 1],
        firstHitDate: row[hdrMap.firstHitDateCol - 1],
        
        // Arrays (parsed)
        maxFavorable: EW_parseArrayFromCell(row[hdrMap.maxFavorableCol - 1]),
        minUnfavorable: EW_parseArrayFromCell(row[hdrMap.minUnfavorableCol - 1]),
        strikeHit: EW_parseArrayFromCell(row[hdrMap.strikeHitCol - 1]),
        
        // Day checks
        dayChecks: [
          row[hdrMap.day0CheckCol - 1],
          row[hdrMap.day1CheckCol - 1],
          row[hdrMap.day2CheckCol - 1],
          row[hdrMap.day3CheckCol - 1],
          row[hdrMap.day4CheckCol - 1],
          row[hdrMap.day5CheckCol - 1]
        ],
        
        // Results
        expResult: row[hdrMap.expResultCol - 1],
        riskReward: parseFloat(row[hdrMap.riskRewardCol - 1]) || 0,
        
        // Entry-time indicators (single values)
        entryIndicators: {
          rsi: parseFloat(row[hdrMap.entryRSICol - 1]) || null,
          ema9: parseFloat(row[hdrMap.entryEMA9Col - 1]) || null,
          ema21: parseFloat(row[hdrMap.entryEMA21Col - 1]) || null,
          sma20: parseFloat(row[hdrMap.entrySMA20Col - 1]) || null,
          sma50: parseFloat(row[hdrMap.entrySMA50Col - 1]) || null,
          vwap: parseFloat(row[hdrMap.entryVWAPCol - 1]) || null,
          rvol: parseFloat(row[hdrMap.entryRVOLCol - 1]) || null,
          atr: parseFloat(row[hdrMap.entryATRCol - 1]) || null,
          priceVsSMA20: parseFloat(row[hdrMap.entryPriceVsSMA20Col - 1]) || null,
          priceVsVWAP: parseFloat(row[hdrMap.entryPriceVsVWAPCol - 1]) || null
        },
        
        // Hit-time indicators (parsed arrays)
        indicators: {
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
        },
        
        // Row reference
        sheetName: sheet.getName(),
        rowNum: idx + 2
      };
      
      // Calculate derived fields
      // Check for hits - Strike_Hit contains decimal percentage values or null when not hit
      // For bullish: positive values are hits (price went above strike)
      // For bearish: positive values are hits (price went below strike - stored as positive in backfill)
      // For neutral: any non-null value is a hit
      const strategyType = EW_getStrategyType(trade.strategy);
      
      trade.wasHit = trade.strikeHit && trade.strikeHit.length > 0 && 
        trade.strikeHit.some(hit => {
          // Null means strike was not hit on that day
          if (hit === null || hit === undefined || hit === "") return false;
          
          const pctMove = parseFloat(hit);
          if (isNaN(pctMove)) return false;
          
          // Any non-null, non-zero value indicates a hit occurred
          // The backfill stores positive values when strike is hit regardless of direction
          return pctMove !== 0;
        });
      
      // Calculate max favorable value - handle both decimal and percentage formats
      const maxFavValues = trade.maxFavorable.filter(v => v !== null).map(v => {
        const val = parseFloat(v) || 0;
        // If value is greater than 1, it's likely stored as percentage, convert to decimal
        return val > 1 ? val / 100 : val;
      });
      trade.maxFavorableValue = maxFavValues.length > 0 ? Math.max(...maxFavValues) : 0;
      
      // Same for unfavorable
      const minUnfavValues = trade.minUnfavorable.filter(v => v !== null).map(v => {
        const val = parseFloat(v) || 0;
        return val > 1 ? val / 100 : val;
      });
      trade.maxUnfavorableValue = minUnfavValues.length > 0 ? Math.max(...minUnfavValues) : 0;
      trade.profitableDays = trade.maxFavorable.filter(v => v !== null && parseFloat(v) > 0).length;
      
      // Days to hit
      if (trade.firstHitDate && trade.runDate) {
        const hit = new Date(trade.firstHitDate);
        const run = new Date(trade.runDate);
        trade.daysToHit = Math.floor((hit - run) / (1000 * 60 * 60 * 24));
      } else if (trade.wasHit && trade.strikeHit) {
        // Alternative: find first day with a hit percentage in Strike_Hit array
        const firstHitIndex = trade.strikeHit.findIndex(pct => pct !== null && pct !== undefined && pct !== "");
        if (firstHitIndex !== -1) {
          trade.daysToHit = firstHitIndex; // Day 0 = same day, Day 1 = next day, etc.
        }
      }
      
      trades.push(trade);
    } catch (e) {
      console.error(`Error parsing trade at row ${idx + 2}: ${e.message}`);
      skippedRows++;
    }
  });
  
  if (emptyRows > 0 || skippedRows > 0) {
    console.log(`  ${strategy}: Skipped ${emptyRows} empty rows (no ticker) and ${skippedRows} rows without Run Date`);
  }
  
  // Debug logging for hit rates
  const hitCount = trades.filter(t => t.wasHit).length;
  console.log(`Strategy: ${strategy}, Total trades: ${trades.length}, Hit trades: ${hitCount}, Hit rate: ${(hitCount/trades.length*100).toFixed(1)}%`);
  
  // Additional debug info for first few trades and hit analysis
  if (trades.length > 0) {
    // Sample trades for debugging
    const sampleTrades = trades.slice(0, 3);
    sampleTrades.forEach((trade, idx) => {
      const strikeHitPreview = trade.strikeHit.slice(0, 3).map(v => v === null ? 'null' : v).join(',');
      console.log(`  Sample trade ${idx + 1}: Strike=${trade.strike || trade.longStrike}, StrikeHit=[${strikeHitPreview}...], wasHit=${trade.wasHit}`);
    });
    
    // Analyze hit patterns
    const tradesWithArrays = trades.filter(t => t.strikeHit && t.strikeHit.length > 0);
    const tradesWithNonNullValues = trades.filter(t => 
      t.strikeHit && t.strikeHit.some(v => v !== null && v !== undefined && v !== "")
    );
    const tradesWithPositiveValues = trades.filter(t => 
      t.strikeHit && t.strikeHit.some(v => v !== null && parseFloat(v) > 0)
    );
    
    console.log(`  Strike_Hit array stats: ${tradesWithArrays.length} have arrays, ${tradesWithNonNullValues.length} have non-null values, ${tradesWithPositiveValues.length} have positive values`);
    
    // Check for trades that might be duplicates or haven't been backfilled
    const tradesWithoutArrays = trades.filter(t => !t.strikeHit || t.strikeHit.length === 0);
    if (tradesWithoutArrays.length > 0) {
      console.log(`  WARNING: ${tradesWithoutArrays.length} trades have no Strike_Hit data (not backfilled yet?)`);
      // Show a few examples
      const examples = tradesWithoutArrays.slice(0, 3);
      examples.forEach((trade, idx) => {
        console.log(`    Example ${idx + 1}: ${trade.ticker}, Strike=${trade.strike || trade.longStrike}, RunDate=${trade.runDate}`);
      });
    }
  }
  
  return trades;
}

/**
 * Analyze overview statistics
 */
function EW_analyzeOverview(trades) {
  const totalTrades = trades.length;
  
  // Calculate based on day-observations, not just trades
  let totalObservations = 0;
  let profitableObservations = 0;
  let hitObservations = 0;
  let sumProfits = 0;
  let sumLosses = 0;
  let profitCount = 0;
  let lossCount = 0;
  
  // Collect all observations
  const observations = [];
  
  trades.forEach(trade => {
    // Use array length to determine how many days have been tracked
    // Arrays like ["0.038494"] have 1 observation (day0)
    // Arrays like ["0.002500","0.011000","-0.024167","-0.025611","-0.027939","-0.011167"] have 6 observations (day0-day5)
    const observationCount = Math.max(
      trade.maxFavorable.filter(v => v !== null && v !== undefined).length,
      trade.minUnfavorable.filter(v => v !== null && v !== undefined).length,
      trade.strikeHit.filter(v => v !== null && v !== undefined && v !== "").length
    );
    
    // Process each observation based on array length
    for (let i = 0; i < observationCount; i++) {
      totalObservations++;
      
      const favorable = parseFloat(trade.maxFavorable[i]) || 0;
      const unfavorable = parseFloat(trade.minUnfavorable[i]) || 0;
      const netProfit = favorable - unfavorable;
      
      observations.push({
        trade: trade,
        day: i,
        favorable: favorable,
        unfavorable: unfavorable,
        profit: netProfit,
        strikeHit: trade.strikeHit[i] !== null && trade.strikeHit[i] !== undefined && trade.strikeHit[i] !== "",
        dayCheck: trade.dayChecks[i] // Keep for reference but don't use for counting
      });
      
      // Count profitable observations (favorable > unfavorable)
      if (favorable > unfavorable) {
        profitableObservations++;
        sumProfits += netProfit;
        profitCount++;
      } else if (unfavorable > favorable) {
        sumLosses += Math.abs(netProfit);
        lossCount++;
      }
      
      // Count hit observations (strike was reached)
      if (trade.strikeHit[i] !== null && trade.strikeHit[i] !== undefined && trade.strikeHit[i] !== "") {
        hitObservations++;
      }
    }
  });
  
  // Calculate metrics
  const profitFactor = sumLosses > 0 ? sumProfits / sumLosses : null;
  const avgProfit = profitCount > 0 ? sumProfits / profitCount : 0;
  const avgLoss = lossCount > 0 ? sumLosses / lossCount : 0;
  const avgRiskReward = avgLoss > 0 ? avgProfit / avgLoss : null;
  
  // Count trades that hit their strike at any point
  const tradesWithHits = trades.filter(trade => {
    if (!trade.strikeHit || !Array.isArray(trade.strikeHit)) return false;
    
    const strategyUpper = (trade.strategy || '').toUpperCase();
    const isBullish = strategyUpper.includes('BULL') || strategyUpper.includes('LONG CALL') || strategyUpper.includes('CALL');
    const isBearish = strategyUpper.includes('BEAR') || strategyUpper.includes('LONG PUT') || strategyUpper.includes('PUT');
    
    // Check if any day has a valid hit based on strategy
    return trade.strikeHit.some(hit => {
      if (hit === null || hit === undefined || hit === "" || hit === "NO" || hit === "NO_DATA") {
        return false;
      }
      
      // Parse the hit value (it's stored as a decimal percentage)
      const hitValue = parseFloat(hit);
      if (isNaN(hitValue)) return false;
      
      // The backfill stores positive values for both bullish and bearish hits
      // Any non-zero value indicates a hit occurred
      return hitValue !== 0;
    });
  }).length;
  
  // Calculate average days to hit
  const tradesWithDaysToHit = trades.filter(t => t.daysToHit !== undefined && t.daysToHit !== null);
  const avgDaysToHit = tradesWithDaysToHit.length > 0 ? 
    tradesWithDaysToHit.reduce((sum, t) => sum + t.daysToHit, 0) / tradesWithDaysToHit.length : 0;
  
  // Calculate by strategy type using observations
  const byStrategy = {};
  const strategies = [...new Set(trades.map(t => t.strategy))];
  
  strategies.forEach(strategy => {
    const strategyTrades = trades.filter(t => t.strategy === strategy);
    let strategyObservations = 0;
    let strategyProfitableObs = 0;
    
    // Count trades that hit (not observations)
    const strategyHits = strategyTrades.filter(trade => {
      if (!trade.strikeHit || !Array.isArray(trade.strikeHit)) return false;
      
      // Check if any day has a valid hit (non-null, non-zero value)
      // The backfill stores positive values for both bullish and bearish hits
      return trade.strikeHit.some(hit => {
        if (hit === null || hit === undefined || hit === "" || hit === "NO" || hit === "NO_DATA") {
          return false;
        }
        
        const hitValue = parseFloat(hit);
        return !isNaN(hitValue) && hitValue !== 0;
      });
    }).length;
    
    strategyTrades.forEach(trade => {
      // Use array length to determine observation count
      const observationCount = Math.max(
        trade.maxFavorable.filter(v => v !== null && v !== undefined).length,
        trade.minUnfavorable.filter(v => v !== null && v !== undefined).length,
        trade.strikeHit.filter(v => v !== null && v !== undefined && v !== "").length
      );
      
      for (let i = 0; i < observationCount; i++) {
        strategyObservations++;
        
        const favorable = parseFloat(trade.maxFavorable[i]) || 0;
        const unfavorable = parseFloat(trade.minUnfavorable[i]) || 0;
        
        if (favorable > unfavorable) {
          strategyProfitableObs++;
        }
      }
    });
    
    // Calculate profit factor and avg win/loss for strategy
    let strategyWins = 0;
    let strategyLosses = 0;
    let strategyWinCount = 0;
    let strategyLossCount = 0;
    
    const strategyObs = observations.filter(o => o.trade.strategy === strategy);
    strategyObs.forEach(o => {
      if (o.profit > 0) {
        strategyWins += o.profit;
        strategyWinCount++;
      } else if (o.profit < 0) {
        strategyLosses += Math.abs(o.profit);
        strategyLossCount++;
      }
    });
    
    const strategyProfitFactor = strategyLosses > 0 ? strategyWins / strategyLosses : 0;
    const strategyAvgWin = strategyWinCount > 0 ? strategyWins / strategyWinCount : 0;
    const strategyAvgLoss = strategyLossCount > 0 ? strategyLosses / strategyLossCount : 0;
    
    // Calculate additional strategy metrics
    let strategyTotalProfit = 0;
    let strategyTotalLoss = 0;
    let strategyAvgDaysToHit = 0;
    let strategyHitCount = 0;
    
    strategyTrades.forEach(trade => {
      if (trade.wasHit) {
        strategyHitCount++;
        if (trade.daysToHit !== undefined) {
          strategyAvgDaysToHit += trade.daysToHit;
        }
      }
      
      const netProfit = (trade.maxFavorableValue || 0) - (trade.maxUnfavorableValue || 0);
      if (netProfit > 0) {
        strategyTotalProfit += netProfit;
      } else {
        strategyTotalLoss += Math.abs(netProfit);
      }
    });
    
    byStrategy[strategy] = {
      totalTrades: strategyTrades.length,
      totalObservations: strategyObservations,
      hitTrades: strategyHitCount,  // Added for compatibility
      hitRate: strategyTrades.length > 0 ? strategyHits / strategyTrades.length : 0, // Keep as decimal
      profitableRate: strategyObservations > 0 ? strategyProfitableObs / strategyObservations : 0,
      profitFactor: strategyProfitFactor,
      avgProfit: strategyAvgWin,  // Using avgWin as avgProfit for consistency
      avgWin: strategyAvgWin,  // Keep as decimal
      avgLoss: strategyAvgLoss,  // Keep as decimal
      avgRiskReward: strategyTrades.length > 0 ? strategyTrades.reduce((sum, t) => sum + (t.riskReward || 0), 0) / strategyTrades.length : 0,
      totalProfit: strategyTotalProfit,  // Added
      totalLoss: strategyTotalLoss,  // Added
      avgDaysToHit: strategyHitCount > 0 ? strategyAvgDaysToHit / strategyHitCount : 0  // Added
    };
  });
  
  // Find best holding day
  const holdingDayStats = {};
  for (let day = 0; day < 6; day++) {
    const dayObs = observations.filter(o => o.day === day);
    if (dayObs.length > 0) {
      const dayProfitable = dayObs.filter(o => o.profit > 0).length;
      holdingDayStats[day] = {
        profitableRate: (dayProfitable / dayObs.length * 100).toFixed(2),
        avgProfit: dayObs.reduce((sum, o) => sum + o.profit, 0) / dayObs.length
      };
    }
  }
  
  const bestHoldingDay = Object.entries(holdingDayStats)
    .sort((a, b) => parseFloat(b[1].profitableRate) - parseFloat(a[1].profitableRate))[0];
  
  return {
    totalTrades: totalTrades,
    totalObservations: totalObservations,
    strikeHits: tradesWithHits,
    profitableTrades: profitableObservations,
    hitRate: totalTrades > 0 ? tradesWithHits / totalTrades : 0, // Changed to trade-based calculation
    profitableRate: totalObservations > 0 ? profitableObservations / totalObservations : 0,
    profitFactor: profitFactor || 0,
    avgProfit: avgProfit,
    avgLoss: avgLoss,
    avgRiskReward: avgRiskReward || 0,
    avgDaysToHit: avgDaysToHit,
    bestHoldingDay: bestHoldingDay ? `Day ${bestHoldingDay[0]}` : 'Day 1',
    byStrategy: byStrategy,
    observations: observations // For use in other analyses
  };
}

/**
 * Analyze multi-day profitability patterns
 */
function EW_analyzeMultiDayProfitability(trades) {
  const analysis = {
    sustainedProfitability: [],
    profitabilityByDay: {},
    profitabilityByStrategy: {},
    bestHoldingPeriod: {}
  };
  
  // Get unique strategies
  const strategies = [...new Set(trades.map(t => t.strategy))];
  strategies.forEach(strategy => {
    analysis.profitabilityByStrategy[strategy] = {
      byDay: {},
      sustainedProfitable: []
    };
  });
  
  // Analyze trades that stayed profitable for multiple days
  trades.forEach(trade => {
    if (!trade.maxFavorable || trade.maxFavorable.length === 0) return;
    
    let consecutiveProfitableDays = 0;
    let maxConsecutive = 0;
    let peakDay = -1;
    let peakValue = 0;
    
    trade.maxFavorable.forEach((value, day) => {
      if (value !== null && parseFloat(value) > 0) {
        consecutiveProfitableDays++;
        if (parseFloat(value) > peakValue) {
          peakValue = parseFloat(value);
          peakDay = day;
        }
      } else {
        maxConsecutive = Math.max(maxConsecutive, consecutiveProfitableDays);
        consecutiveProfitableDays = 0;
      }
    });
    maxConsecutive = Math.max(maxConsecutive, consecutiveProfitableDays);
    
    if (maxConsecutive >= 3) {
      const sustainedTrade = {
        ticker: trade.ticker,
        strategy: trade.strategy,
        consecutiveDays: maxConsecutive,
        peakDay: peakDay,
        peakValue: peakValue,  // Already in percentage form
        strike: trade.strike || trade.longStrike
      };
      
      analysis.sustainedProfitability.push(sustainedTrade);
      
      // Add to strategy-specific list
      if (analysis.profitabilityByStrategy[trade.strategy]) {
        analysis.profitabilityByStrategy[trade.strategy].sustainedProfitable.push(sustainedTrade);
      }
    }
  });
  
  // Sort by consecutive days
  analysis.sustainedProfitability.sort((a, b) => b.consecutiveDays - a.consecutiveDays);
  
  // Profitability by day - overall and by strategy
  for (let day = 0; day <= 5; day++) {
    const dayTrades = trades.filter(t => 
      t.maxFavorable[day] !== null && t.maxFavorable[day] !== undefined
    );
    
    const profitable = dayTrades.filter(t => {
      const fav = parseFloat(t.maxFavorable[day]) || 0;
      const unfav = parseFloat(t.minUnfavorable[day]) || 0;
      return fav > unfav;
    }).length;
    
    const avgProfit = dayTrades.reduce((sum, t) => sum + (parseFloat(t.maxFavorable[day]) || 0), 0) / dayTrades.length;
    
    analysis.profitabilityByDay[`Day${day}`] = {
      totalTrades: dayTrades.length,
      profitableCount: profitable,
      profitableRate: (profitable / dayTrades.length) * 100,  // Keep as number
      avgProfit: avgProfit * 100  // Keep as number
    };
    
    // By strategy
    strategies.forEach(strategy => {
      const strategyDayTrades = dayTrades.filter(t => t.strategy === strategy);
      if (strategyDayTrades.length > 0) {
        const stratProfitable = strategyDayTrades.filter(t => {
          const fav = parseFloat(t.maxFavorable[day]) || 0;
          const unfav = parseFloat(t.minUnfavorable[day]) || 0;
          return fav > unfav;
        }).length;
        
        const stratAvgProfit = strategyDayTrades.reduce((sum, t) => 
          sum + (parseFloat(t.maxFavorable[day]) || 0), 0) / strategyDayTrades.length;
        
        analysis.profitabilityByStrategy[strategy].byDay[`Day${day}`] = {
          totalTrades: strategyDayTrades.length,
          profitableCount: stratProfitable,
          profitableRate: (stratProfitable / strategyDayTrades.length) * 100,  // Keep as number
          avgProfit: stratAvgProfit * 100  // Keep as number
        };
      }
    });
  }
  
  return analysis;
}

/**
 * Analyze indicator effectiveness with enhanced insights
 */
function EW_analyzeIndicatorEffectiveness(trades) {
  const hitIndicators = ['rsi', 'sma20', 'sma50', 'ema9', 'ema21', 'vwap', 'rvol', 'atr', 'priceVsSMA20', 'priceVsVWAP'];
  const entryIndicators = ['rsi', 'sma20', 'sma50', 'ema9', 'ema21', 'vwap', 'rvol', 'atr', 'priceVsSMA20', 'priceVsVWAP'];
  const analysis = {};
  
  // Analyze hit-time indicators
  hitIndicators.forEach(indicator => {
    const profitableRanges = EW_findProfitableIndicatorRanges(trades, indicator, 'hit');
    const correlation = EW_calculateIndicatorCorrelation(trades, indicator, 'hit');
    
    analysis[`hit_${indicator}`] = {
      type: 'hit',
      profitableRanges: profitableRanges,
      correlationWithProfit: correlation,
      significance: Math.abs(correlation) > 0.3 ? 'HIGH' : (Math.abs(correlation) > 0.15 ? 'MEDIUM' : 'LOW'),
      dataCompleteness: EW_calculateDataCompleteness(trades, indicator, 'hit')
    };
  });
  
  // Analyze entry-time indicators
  entryIndicators.forEach(indicator => {
    const profitableRanges = EW_findProfitableIndicatorRanges(trades, indicator, 'entry');
    const correlation = EW_calculateIndicatorCorrelation(trades, indicator, 'entry');
    
    analysis[`entry_${indicator}`] = {
      type: 'entry',
      profitableRanges: profitableRanges,
      correlationWithProfit: correlation,
      significance: Math.abs(correlation) > 0.3 ? 'HIGH' : (Math.abs(correlation) > 0.15 ? 'MEDIUM' : 'LOW'),
      dataCompleteness: EW_calculateDataCompleteness(trades, indicator, 'entry')
    };
  });
  
  return analysis;
}

/**
 * Find profitable ranges for an indicator
 */
function EW_findProfitableIndicatorRanges(trades, indicatorName, type = 'hit') {
  const ranges = {
    bullish: { min: null, max: null, count: 0, avgProfit: 0 },
    bearish: { min: null, max: null, count: 0, avgProfit: 0 }
  };
  
  const profitableTrades = trades.filter(t => 
    t.wasHit && t.maxFavorableValue > t.maxUnfavorableValue
  );
  
  profitableTrades.forEach(trade => {
    let value;
    
    if (type === 'entry') {
      // Get entry-time indicator value
      if (!trade.entryIndicators || trade.entryIndicators[indicatorName] === null) return;
      value = parseFloat(trade.entryIndicators[indicatorName]);
    } else {
      // Get hit-time indicator value (first non-null value)
      const indicatorValues = trade.indicators[indicatorName];
      if (!indicatorValues || indicatorValues.length === 0) return;
      
      const hitValue = indicatorValues.find(v => v !== null);
      if (!hitValue) return;
      value = parseFloat(hitValue);
    }
    
    if (isNaN(value)) return;
    
    const isBullish = trade.strategy.toUpperCase().includes('BULL') || 
                      trade.strategy.toUpperCase().includes('LONG CALL');
    
    const range = isBullish ? ranges.bullish : ranges.bearish;
    
    if (range.min === null || value < range.min) range.min = value;
    if (range.max === null || value > range.max) range.max = value;
    range.count++;
    range.avgProfit += trade.maxFavorableValue;
  });
  
  // Calculate averages (keep as numbers)
  if (ranges.bullish.count > 0) {
    ranges.bullish.avgProfit = (ranges.bullish.avgProfit / ranges.bullish.count) * 100;  // Keep as number
  }
  if (ranges.bearish.count > 0) {
    ranges.bearish.avgProfit = (ranges.bearish.avgProfit / ranges.bearish.count) * 100;  // Keep as number
  }
  
  return ranges;
}

/**
 * Calculate correlation between indicator and profitability
 */
function EW_calculateIndicatorCorrelation(trades, indicatorName, type = 'hit') {
  const pairs = [];
  
  trades.forEach(trade => {
    let value;
    
    if (type === 'entry') {
      // Get entry-time indicator value
      if (!trade.entryIndicators || trade.entryIndicators[indicatorName] === null) return;
      value = parseFloat(trade.entryIndicators[indicatorName]);
    } else {
      // Get hit-time indicator value
      const indicatorValues = trade.indicators[indicatorName];
      if (!indicatorValues || indicatorValues.length === 0) return;
      
      const firstValue = indicatorValues.find(v => v !== null);
      if (!firstValue) return;
      value = parseFloat(firstValue);
    }
    
    if (isNaN(value)) return;
    
    pairs.push({
      indicator: value,
      profit: trade.maxFavorableValue - trade.maxUnfavorableValue
    });
  });
  
  if (pairs.length < 5) return 0;
  
  // Calculate Pearson correlation
  const n = pairs.length;
  const sumX = pairs.reduce((sum, p) => sum + p.indicator, 0);
  const sumY = pairs.reduce((sum, p) => sum + p.profit, 0);
  const sumXY = pairs.reduce((sum, p) => sum + p.indicator * p.profit, 0);
  const sumX2 = pairs.reduce((sum, p) => sum + p.indicator * p.indicator, 0);
  const sumY2 = pairs.reduce((sum, p) => sum + p.profit * p.profit, 0);
  
  const correlation = (n * sumXY - sumX * sumY) / 
    Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
  
  return isNaN(correlation) ? 0 : parseFloat(correlation.toFixed(3));
}

/**
 * Calculate data completeness for an indicator
 */
function EW_calculateDataCompleteness(trades, indicatorName, type = 'hit') {
  let withData = 0;
  let total = trades.length;
  
  trades.forEach(trade => {
    if (type === 'entry') {
      if (trade.entryIndicators && trade.entryIndicators[indicatorName] !== null) {
        withData++;
      }
    } else {
      if (trade.indicators && trade.indicators[indicatorName]) {
        const hasData = trade.indicators[indicatorName].some(v => v !== null);
        if (hasData) withData++;
      }
    }
  });
  
  return ((withData / total) * 100).toFixed(1) + '%';
}

/**
 * Analyze data quality and completeness
 */
function EW_analyzeDataQuality(trades) {
  const quality = {
    totalTrades: trades.length,
    missingData: {
      company: 0,
      nextEPSDate: 0,
      releaseTime: 0,
      entryIndicators: 0,
      hitIndicators: 0,
      maxFavorable: 0,
      strikeHit: 0,
      dayChecks: 0,
      firstHitDate: 0
    },
    dataCompleteness: {},
    recommendations: []
  };
  
  // Check each trade for missing data
  trades.forEach(trade => {
    // Basic fields
    if (!trade.company || trade.company === trade.ticker) quality.missingData.company++;
    if (!trade.nextEPSDate || trade.nextEPSDate === '') quality.missingData.nextEPSDate++;
    if (trade.releaseTime === undefined || trade.releaseTime === null || trade.releaseTime === '') quality.missingData.releaseTime++;
    if (!trade.firstHitDate && trade.wasHit) quality.missingData.firstHitDate++;
    
    // Entry indicators
    const hasEntryIndicators = trade.entryIndicators && 
      Object.values(trade.entryIndicators).some(v => v !== null);
    if (!hasEntryIndicators) quality.missingData.entryIndicators++;
    
    // Hit indicators
    const hasHitIndicators = trade.indicators && 
      Object.values(trade.indicators).some(arr => arr && arr.some(v => v !== null));
    if (!hasHitIndicators) quality.missingData.hitIndicators++;
    
    // Arrays
    if (!trade.maxFavorable || trade.maxFavorable.every(v => v === null)) {
      quality.missingData.maxFavorable++;
    }
    if (!trade.strikeHit || trade.strikeHit.every(v => v === null)) {
      quality.missingData.strikeHit++;
    }
    if (!trade.dayChecks || trade.dayChecks.every(v => !v)) {
      quality.missingData.dayChecks++;
    }
  });
  
  // Calculate completeness percentages
  Object.entries(quality.missingData).forEach(([field, count]) => {
    const percentage = ((quality.totalTrades - count) / quality.totalTrades * 100).toFixed(1);
    quality.dataCompleteness[field] = percentage + '%';
  });
  
  // Generate recommendations
  if (quality.missingData.company > quality.totalTrades * 0.5) {
    quality.recommendations.push('Company names are missing for >50% of trades. Consider adding company lookup.');
  }
  if (quality.missingData.nextEPSDate > quality.totalTrades * 0.3) {
    quality.recommendations.push('Earnings dates missing for >30% of trades. This limits earnings timing analysis.');
  }
  if (quality.missingData.entryIndicators > quality.totalTrades * 0.2) {
    quality.recommendations.push('Entry indicators missing for >20% of trades. Run indicator calculation on entry.');
  }
  if (quality.missingData.strikeHit > quality.totalTrades * 0.1) {
    quality.recommendations.push('Strike hit data missing. Ensure backfill is running properly.');
  }
  
  // Calculate overall data quality score
  const totalFields = Object.keys(quality.missingData).length;
  const totalMissing = Object.values(quality.missingData).reduce((sum, count) => sum + count, 0);
  const maxPossibleMissing = quality.totalTrades * totalFields;
  quality.overallScore = ((1 - totalMissing / maxPossibleMissing) * 100).toFixed(1) + '%';
  
  return quality;
}

/**
 * Analyze holding period performance
 */
function EW_analyzeHoldingPeriod(trades) {
  const analysis = {
    byDay: {},
    byStrategy: {},
    optimalExitTiming: {},
    averageDecayRate: {},
    recommendations: []
  };
  
  // Initialize day analysis
  for (let day = 0; day <= 5; day++) {
    analysis.byDay[`Day${day}`] = {
      totalObservations: 0,
      profitable: 0,
      avgProfit: 0,
      avgLoss: 0,
      hitRate: 0,
      avgMove: 0,
      profitSum: 0,
      lossSum: 0,
      profitCount: 0,
      lossCount: 0
    };
  }
  
  // Analyze each trade's performance by day
  trades.forEach(trade => {
    if (!trade.maxFavorable || !trade.minUnfavorable) return;
    
    // Use array length to determine how many observations exist
    const observationCount = Math.max(
      trade.maxFavorable.filter(v => v !== null && v !== undefined).length,
      trade.minUnfavorable.filter(v => v !== null && v !== undefined).length,
      trade.strikeHit.filter(v => v !== null && v !== undefined && v !== "").length
    );
    
    for (let day = 0; day < observationCount; day++) {
      const favorable = parseFloat(trade.maxFavorable[day]) || 0;
      const unfavorable = parseFloat(trade.minUnfavorable[day]) || 0;
      
      // Only count if we have data for this day (at least one array has a value)
      if (trade.maxFavorable[day] !== null || trade.minUnfavorable[day] !== null || 
          (trade.strikeHit[day] !== null && trade.strikeHit[day] !== "")) {
        const dayKey = `Day${day}`;
        const dayStats = analysis.byDay[dayKey];
        const netMove = favorable - unfavorable;
        
        dayStats.totalObservations++;
        dayStats.avgMove += netMove;
        
        if (netMove > 0) {
          dayStats.profitable++;
          dayStats.profitSum += netMove;
          dayStats.profitCount++;
        } else {
          dayStats.lossSum += Math.abs(netMove);
          dayStats.lossCount++;
        }
        
        // Track hit rate
        if (trade.strikeHit && trade.strikeHit[day] !== null && trade.strikeHit[day] !== "") {
          dayStats.hitRate++;
        }
      }
    }
  });
  
  // Calculate averages and rates
  Object.entries(analysis.byDay).forEach(([day, stats]) => {
    if (stats.totalObservations > 0) {
      stats.profitableRate = (stats.profitable / stats.totalObservations) * 100;  // Keep as number
      stats.hitRate = (stats.hitRate / stats.totalObservations) * 100;  // Keep as number
      stats.avgMove = (stats.avgMove / stats.totalObservations) * 100;  // Keep as number
      
      if (stats.profitCount > 0) {
        stats.avgProfit = (stats.profitSum / stats.profitCount) * 100;  // Keep as number
      }
      if (stats.lossCount > 0) {
        stats.avgLoss = (stats.lossSum / stats.lossCount) * 100;  // Keep as number
      }
      
      stats.profitFactor = stats.lossSum > 0 ? (stats.profitSum / stats.lossSum).toFixed(2) : 'N/A';
    }
  });
  
  // Analyze by strategy
  const strategies = [...new Set(trades.map(t => t.strategy))];
  strategies.forEach(strategy => {
    analysis.byStrategy[strategy] = {
      byDay: {}
    };
    
    // Initialize days for this strategy
    for (let day = 0; day <= 5; day++) {
      analysis.byStrategy[strategy].byDay[`Day${day}`] = {
        totalObservations: 0,
        profitable: 0,
        profitableRate: '0%',
        avgMove: 0
      };
    }
    
    // Process trades for this strategy
    const strategyTrades = trades.filter(t => t.strategy === strategy);
    strategyTrades.forEach(trade => {
      if (!trade.maxFavorable || !trade.minUnfavorable) return;
      
      // Use array length to determine observation count
      const observationCount = Math.max(
        trade.maxFavorable.filter(v => v !== null && v !== undefined).length,
        trade.minUnfavorable.filter(v => v !== null && v !== undefined).length,
        trade.strikeHit.filter(v => v !== null && v !== undefined && v !== "").length
      );
      
      for (let day = 0; day < observationCount; day++) {
        const favorable = parseFloat(trade.maxFavorable[day]) || 0;
        const unfavorable = parseFloat(trade.minUnfavorable[day]) || 0;
        
        if (favorable !== 0 || unfavorable !== 0) {
          const dayKey = `Day${day}`;
          const dayStats = analysis.byStrategy[strategy].byDay[dayKey];
          const netMove = favorable - unfavorable;
          
          dayStats.totalObservations++;
          dayStats.avgMove += netMove;
          
          if (netMove > 0) {
            dayStats.profitable++;
          }
        }
      }
    });
    
    // Calculate averages for this strategy
    Object.entries(analysis.byStrategy[strategy].byDay).forEach(([day, stats]) => {
      if (stats.totalObservations > 0) {
        stats.profitableRate = ((stats.profitable / stats.totalObservations) * 100).toFixed(2) + '%';
        stats.avgMove = ((stats.avgMove / stats.totalObservations) * 100).toFixed(2) + '%';
      }
    });
  });
  
  // Find optimal exit timing
  let maxProfitDay = null;
  let maxProfitRate = 0;
  
  Object.entries(analysis.byDay).forEach(([day, stats]) => {
    const rate = parseFloat(stats.profitableRate) || 0;
    if (rate > maxProfitRate) {
      maxProfitRate = rate;
      maxProfitDay = day;
    }
  });
  
  analysis.optimalExitTiming = {
    bestDay: maxProfitDay,
    profitableRate: maxProfitRate,  // Keep as number
    recommendation: maxProfitDay ? `Consider exiting positions on ${maxProfitDay} for optimal profit rate` : 'Insufficient data'
  };
  
  // Calculate average decay rate (how profit deteriorates over time)
  const profitRates = [];
  for (let day = 0; day <= 5; day++) {
    const rate = parseFloat(analysis.byDay[`Day${day}`].profitableRate) || 0;
    profitRates.push(rate);
  }
  
  // Find peak and calculate decay
  const peakDay = profitRates.indexOf(Math.max(...profitRates));
  if (peakDay < 5) {
    const decayRates = [];
    for (let i = peakDay + 1; i < profitRates.length; i++) {
      const decay = profitRates[peakDay] - profitRates[i];
      decayRates.push(decay);
    }
    
    if (decayRates.length > 0) {
      const avgDecay = decayRates.reduce((sum, d) => sum + d, 0) / decayRates.length;
      analysis.averageDecayRate = {
        peakDay: `Day${peakDay}`,
        avgDecayPerDay: avgDecay,  // Keep as number
        recommendation: avgDecay > 5 ? 'Significant profit decay after peak - consider earlier exits' : 'Profits hold relatively well over time'
      };
    }
  }
  
  // Generate recommendations
  if (maxProfitDay) {
    analysis.recommendations.push(`Optimal exit timing appears to be ${maxProfitDay} with ${maxProfitRate.toFixed(2)}% profitable rate`);
  }
  
  if (analysis.averageDecayRate && analysis.averageDecayRate.avgDecayPerDay) {
    const decay = parseFloat(analysis.averageDecayRate.avgDecayPerDay);
    if (decay > 10) {
      analysis.recommendations.push('Profit decay is significant - consider tighter exit rules');
    }
  }
  
  // Check for strategies that perform better with longer holds
  Object.entries(analysis.byStrategy).forEach(([strategy, data]) => {
    const day0Rate = parseFloat(data.byDay.Day0.profitableRate) || 0;
    const day3Rate = parseFloat(data.byDay.Day3.profitableRate) || 0;
    
    if (day3Rate > day0Rate * 1.2) {
      analysis.recommendations.push(`${strategy} performs better with longer holds (3+ days)`);
    }
  });
  
  return analysis;
}

/**
 * Analyze earnings timing patterns with enhanced insights
 */
function EW_analyzeEarningsTiming(trades) {
  const analysis = {
    preEarningsHits: [],
    postEarningsHits: [],
    noEarningsData: 0,
    earningsImpact: {},
    optimalEntryTiming: {},
    byReleaseTime: {
      beforeOpen: { hits: 0, total: 0, avgProfit: 0, avgDaysToHit: 0 },
      afterClose: { hits: 0, total: 0, avgProfit: 0, avgDaysToHit: 0 },
      unknown: { hits: 0, total: 0, avgProfit: 0, avgDaysToHit: 0 }
    },
    byDaysToEarnings: {}
  };
  
  // Initialize days to earnings buckets
  const dayBuckets = ['0-2', '3-5', '6-10', '11-20', '21+'];
  dayBuckets.forEach(bucket => {
    analysis.byDaysToEarnings[bucket] = {
      trades: 0,
      hits: 0,
      avgProfit: 0,
      avgDaysToHit: 0,
      profitSum: 0,
      daysSum: 0
    };
  });
  
  trades.forEach(trade => {
    // Skip if no earnings date
    if (!trade.nextEPSDate || trade.nextEPSDate === '' || trade.nextEPSDate === 'N/A') {
      analysis.noEarningsData++;
      return;
    }
    
    // Try to parse the earnings date
    let epsDate;
    try {
      epsDate = new Date(trade.nextEPSDate);
      if (isNaN(epsDate.getTime())) {
        analysis.noEarningsData++;
        return;
      }
    } catch (e) {
      analysis.noEarningsData++;
      return;
    }
    
    const runDate = new Date(trade.runDate);
    const daysToEarnings = Math.floor((epsDate - runDate) / (1000 * 60 * 60 * 24));
    
    // Determine bucket
    let bucket;
    if (daysToEarnings <= 2) bucket = '0-2';
    else if (daysToEarnings <= 5) bucket = '3-5';
    else if (daysToEarnings <= 10) bucket = '6-10';
    else if (daysToEarnings <= 20) bucket = '11-20';
    else bucket = '21+';
    
    analysis.byDaysToEarnings[bucket].trades++;
    
    // Analyze release time impact
    const releaseTime = trade.releaseTime || 0;
    let timeCategory = 'unknown';
    if (releaseTime === 1) timeCategory = 'beforeOpen';
    else if (releaseTime === 3) timeCategory = 'afterClose';
    
    analysis.byReleaseTime[timeCategory].total++;
    
    if (trade.wasHit) {
      analysis.byDaysToEarnings[bucket].hits++;
      analysis.byDaysToEarnings[bucket].profitSum += trade.maxFavorableValue || 0;
      analysis.byDaysToEarnings[bucket].daysSum += trade.daysToHit || 0;
      
      analysis.byReleaseTime[timeCategory].hits++;
    }
    
    // Analyze pre/post earnings for all trades with data
    // releaseTime: 1 = before market open, 3 = after market close
    // For releaseTime = 1: earnings affect same day
    // For releaseTime = 3: earnings affect next trading day
    
    // Calculate which days are pre/post earnings
    const earningsImpactDay = (() => {
      // How many days from run date until earnings impact trading
      if (releaseTime === 1) {
        // Before open: impacts same day as earnings
        return daysToEarnings;
      } else if (releaseTime === 3) {
        // After close: impacts next trading day
        return daysToEarnings + 1;
      }
      return daysToEarnings; // Default
    })();
    
    // Track pre/post earnings observations
    let preEarningsObservations = [];
    let postEarningsObservations = [];
    
    // Use array length to determine observation count
    const observationCount = Math.max(
      trade.maxFavorable.filter(v => v !== null && v !== undefined).length,
      trade.minUnfavorable.filter(v => v !== null && v !== undefined).length,
      trade.strikeHit.filter(v => v !== null && v !== undefined && v !== "").length
    );
    
    // Check each day's data based on array length
    for (let dayIndex = 0; dayIndex < observationCount; dayIndex++) {
      if (trade.maxFavorable[dayIndex] !== null && trade.maxFavorable[dayIndex] !== undefined) {
        const favorable = parseFloat(trade.maxFavorable[dayIndex]) || 0;
        const unfavorable = parseFloat(trade.minUnfavorable[dayIndex]) || 0;
        const profit = favorable - unfavorable;
        
        // Day 0 = run date, Day 1 = run date + 1, etc.
        // If earnings impact day is 2, then Day 0 and Day 1 are pre-earnings
        if (dayIndex < earningsImpactDay) {
          preEarningsObservations.push({
            day: dayIndex,
            profit: profit,
            favorable: favorable,
            hit: trade.strikeHit[dayIndex] !== null && trade.strikeHit[dayIndex] !== ''
          });
        } else {
          postEarningsObservations.push({
            day: dayIndex,
            profit: profit,
            favorable: favorable,
            hit: trade.strikeHit[dayIndex] !== null && trade.strikeHit[dayIndex] !== ''
          });
        }
      }
    }
    
    // Add pre-earnings observations to analysis
    if (preEarningsObservations.length > 0 && trade.wasHit) {
      // Check if any pre-earnings day had a hit
      const preEarningsHit = preEarningsObservations.some(obs => obs.hit);
      if (preEarningsHit) {
        const hitDay = preEarningsObservations.find(obs => obs.hit)?.day || 0;
        analysis.preEarningsHits.push({
          ticker: trade.ticker,
          strategy: trade.strategy,
          daysToEarnings: daysToEarnings,
          daysToHit: hitDay,
          maxProfit: Math.max(...preEarningsObservations.map(o => o.favorable)),  // Already in percentage
          releaseTime: releaseTime,
          releaseTimeCategory: timeCategory,
          earningsImpactDay: earningsImpactDay
        });
      }
    }
    
    // Add post-earnings observations to analysis
    if (postEarningsObservations.length > 0 && trade.wasHit) {
      // Check if any post-earnings day had a hit
      const postEarningsHit = postEarningsObservations.some(obs => obs.hit);
      if (postEarningsHit) {
        const hitDay = postEarningsObservations.find(obs => obs.hit)?.day || 0;
        analysis.postEarningsHits.push({
          ticker: trade.ticker,
          strategy: trade.strategy,
          daysToEarnings: daysToEarnings,
          daysToHit: hitDay,
          maxProfit: Math.max(...postEarningsObservations.map(o => o.favorable)),  // Already in percentage
          releaseTime: releaseTime,
          releaseTimeCategory: timeCategory,
          earningsImpactDay: earningsImpactDay
        });
      }
    }
  });
  
  // Calculate averages for buckets
  Object.keys(analysis.byDaysToEarnings).forEach(bucket => {
    const data = analysis.byDaysToEarnings[bucket];
    if (data.hits > 0) {
      data.avgProfit = data.profitSum / data.hits;
      data.avgDaysToHit = data.daysSum / data.hits;
    }
    data.hitRate = data.trades > 0 ? (data.hits / data.trades * 100) : 0;
  });
  
  // Calculate averages for release times
  Object.keys(analysis.byReleaseTime).forEach(timeCategory => {
    const data = analysis.byReleaseTime[timeCategory];
    if (data.total > 0) {
      data.hitRate = (data.hits / data.total * 100);
      // Calculate avg profit and days for this category
      const relevantTrades = trades.filter(t => {
        const rt = t.releaseTime || 0;
        return (timeCategory === 'beforeOpen' && rt === 1) ||
               (timeCategory === 'afterClose' && rt === 3) ||
               (timeCategory === 'unknown' && rt !== 1 && rt !== 3);
      });
      
      const hitTrades = relevantTrades.filter(t => t.wasHit);
      if (hitTrades.length > 0) {
        data.avgProfit = hitTrades.reduce((sum, t) => sum + (t.maxFavorableValue || 0), 0) / hitTrades.length;
        data.avgDaysToHit = hitTrades.reduce((sum, t) => sum + (t.daysToHit || 0), 0) / hitTrades.length;
      }
    }
  });
  
  // Existing analysis calculations
  const preEarningsAvgDays = analysis.preEarningsHits.length > 0 ?
    analysis.preEarningsHits.reduce((sum, t) => sum + t.daysToHit, 0) / analysis.preEarningsHits.length : 0;
  
  const postEarningsAvgDays = analysis.postEarningsHits.length > 0 ?
    analysis.postEarningsHits.reduce((sum, t) => sum + t.daysToHit, 0) / analysis.postEarningsHits.length : 0;
  
  const totalEarningsTrades = analysis.preEarningsHits.length + analysis.postEarningsHits.length;
  const totalTradesAnalyzed = trades.length;
  const tradesWithoutEarnings = analysis.noEarningsData;
  
  // Calculate average profits
  const avgProfitPreEarnings = analysis.preEarningsHits.length > 0 ?
    analysis.preEarningsHits.reduce((sum, t) => sum + t.maxProfit, 0) / analysis.preEarningsHits.length : 0;
  const avgProfitPostEarnings = analysis.postEarningsHits.length > 0 ?
    analysis.postEarningsHits.reduce((sum, t) => sum + t.maxProfit, 0) / analysis.postEarningsHits.length : 0;
  
  // Find optimal entry timing
  let optimalBucket = '';
  let maxScore = 0;
  Object.entries(analysis.byDaysToEarnings).forEach(([bucket, data]) => {
    if (data.trades >= 5) { // Minimum sample size
      // Score based on hit rate and avg profit
      const score = (data.hitRate * 0.4) + (data.avgProfit * 100 * 0.6);
      if (score > maxScore) {
        maxScore = score;
        optimalBucket = bucket;
      }
    }
  });
  
  analysis.earningsImpact = {
    totalTradesAnalyzed: totalTradesAnalyzed,
    tradesWithEarningsData: totalEarningsTrades,
    tradesWithoutEarningsData: tradesWithoutEarnings,
    dataCompleteness: ((totalEarningsTrades / totalTradesAnalyzed) * 100).toFixed(1) + '%',
    preEarningsHits: analysis.preEarningsHits.length,
    postEarningsHits: analysis.postEarningsHits.length,
    preEarningsHitRate: totalEarningsTrades > 0 ? 
      (analysis.preEarningsHits.length / totalEarningsTrades * 100).toFixed(2) + '%' : 'N/A',
    avgDaysToHitPreEarnings: preEarningsAvgDays > 0 ? preEarningsAvgDays.toFixed(1) + ' days' : 'N/A',
    avgDaysToHitPostEarnings: postEarningsAvgDays > 0 ? postEarningsAvgDays.toFixed(1) + ' days' : 'N/A',
    avgProfitPreEarnings: avgProfitPreEarnings,  // Already in percentage
    avgProfitPostEarnings: avgProfitPostEarnings,  // Already in percentage
    optimalEntryWindow: optimalBucket ? `${optimalBucket} days before earnings` : 'Insufficient data',
    recommendation: totalEarningsTrades > 10 ? 
      (preEarningsAvgDays < postEarningsAvgDays && avgProfitPreEarnings > avgProfitPostEarnings ? 
        'Enter positions 3-5 days before earnings for faster hits and higher profits' : 
        (avgProfitPostEarnings > avgProfitPreEarnings ?
          'Consider post-earnings entries for higher profit potential' :
          'Mixed results - analyze individual earnings events')) : 
      `Need more data (only ${totalEarningsTrades} trades with earnings info)`
  };
  
  return analysis;
}

/**
 * Analyze risk/reward patterns
 */
function EW_analyzeRiskRewardPatterns(trades) {
  const analysis = {
    byRiskRewardRatio: {},
    optimalRatios: [],
    exitTimingAnalysis: {}
  };
  
  // Group by risk/reward ratios
  const rrGroups = {
    'Under 1.0': trades.filter(t => t.riskReward < 1),
    '1.0-2.0': trades.filter(t => t.riskReward >= 1 && t.riskReward < 2),
    '2.0-3.0': trades.filter(t => t.riskReward >= 2 && t.riskReward < 3),
    'Over 3.0': trades.filter(t => t.riskReward >= 3)
  };
  
  Object.entries(rrGroups).forEach(([range, groupTrades]) => {
    if (groupTrades.length === 0) return;
    
    const hitRate = groupTrades.filter(t => t.wasHit).length / groupTrades.length;
    const avgProfit = groupTrades.reduce((sum, t) => sum + t.maxFavorableValue, 0) / groupTrades.length;
    
    analysis.byRiskRewardRatio[range] = {
      count: groupTrades.length,
      hitRate: hitRate * 100,  // Keep as number
      avgMaxProfit: avgProfit * 100,  // Keep as number
      recommendation: hitRate > 0.7 ? 'FAVORABLE' : (hitRate > 0.5 ? 'MODERATE' : 'RISKY')
    };
  });
  
  // Find optimal exit timing
  for (let day = 0; day <= 5; day++) {
    const dayProfits = trades
      .filter(t => t.maxFavorable[day] !== null)
      .map(t => parseFloat(t.maxFavorable[day]));
    
    if (dayProfits.length > 0) {
      analysis.exitTimingAnalysis[`Day${day}`] = {
        avgProfit: (dayProfits.reduce((sum, p) => sum + p, 0) / dayProfits.length) * 100,  // Keep as number
        profitableTrades: dayProfits.filter(p => p > 0).length,
        totalTrades: dayProfits.length
      };
    }
  }
  
  return analysis;
}

/**
 * Analyze performance by strategy
 */
function EW_analyzeStrategyPerformance(trades) {
  const strategies = {};
  
  trades.forEach(trade => {
    if (!strategies[trade.strategy]) {
      strategies[trade.strategy] = {
        totalTrades: 0,
        hitTrades: 0,
        totalProfit: 0,
        totalLoss: 0,
        avgDaysToHit: 0,
        bestPerformers: []
      };
    }
    
    const stats = strategies[trade.strategy];
    stats.totalTrades++;
    
    if (trade.wasHit) {
      stats.hitTrades++;
      if (trade.daysToHit !== undefined) {
        stats.avgDaysToHit += trade.daysToHit;
      }
    }
    
    const netProfit = trade.maxFavorableValue - trade.maxUnfavorableValue;
    if (netProfit > 0) {
      stats.totalProfit += netProfit;
    } else {
      stats.totalLoss += Math.abs(netProfit);
    }
    
    // Track best performers
    if (netProfit > 0.05) { // Over 5% profit (decimal)
      stats.bestPerformers.push({
        ticker: trade.ticker,
        profit: (netProfit * 100).toFixed(2) + '%',
        daysHeld: trade.profitableDays
      });
    }
  });
  
  // Calculate final stats (keep as numbers for further processing)
  Object.entries(strategies).forEach(([strategy, stats]) => {
    stats.hitRate = stats.hitTrades / stats.totalTrades;  // Keep as decimal (0.18 instead of "18%")
    stats.avgProfit = stats.totalProfit / stats.totalTrades;  // Keep as decimal
    stats.avgLoss = stats.totalLoss / stats.totalTrades;  // Keep as decimal  
    stats.profitFactor = stats.totalLoss > 0 ? stats.totalProfit / stats.totalLoss : 0;
    stats.avgDaysToHit = stats.hitTrades > 0 ? stats.avgDaysToHit / stats.hitTrades : 0;
    
    // Sort and limit best performers
    stats.bestPerformers.sort((a, b) => parseFloat(b.profit) - parseFloat(a.profit));
    stats.bestPerformers = stats.bestPerformers.slice(0, 5);
  });
  
  return strategies;
}

/**
 * Identify top performing plays
 */
function EW_identifyTopPlays(trades) {
  // Filter for successful trades - values are stored as decimals so > 0.05 for 5%
  const successfulTrades = trades.filter(t => {
    if (!t.wasHit) return false;
    // Check if any day had > 5% profit (values stored as decimals)
    return t.maxFavorable.some(v => v !== null && parseFloat(v) > 0.05);
  });
  
  // Sort by max profitability
  successfulTrades.sort((a, b) => b.maxFavorableValue - a.maxFavorableValue);
  
  // Get top 20
  const topPlays = successfulTrades.slice(0, 20).map(trade => {
    // Get comprehensive indicator profiles (both entry and hit)
    const entryIndicators = {};
    const hitIndicators = {};
    
    // Entry indicators
    if (trade.entryIndicators) {
      Object.entries(trade.entryIndicators).forEach(([name, value]) => {
        if (value !== null && value !== undefined) {
          entryIndicators[name] = parseFloat(value).toFixed(2);
        }
      });
    }
    
    // Hit indicators (first non-null value)
    Object.entries(trade.indicators).forEach(([name, values]) => {
      if (values && values.length > 0) {
        const firstValue = values.find(v => v !== null);
        if (firstValue) hitIndicators[name] = parseFloat(firstValue).toFixed(2);
      }
    });
    
    // Create indicator profile string
    const keyIndicators = ['rsi', 'priceVsSMA20', 'priceVsVWAP', 'rvol'];
    const indicatorProfile = keyIndicators
      .map(ind => {
        const entry = entryIndicators[ind] || 'N/A';
        const hit = hitIndicators[ind] || 'N/A';
        return `${ind.toUpperCase()}: ${entry}→${hit}`;
      })
      .join(', ');
    
    // Get the strike price
    const strikePrice = trade.strike > 0 ? parseFloat(trade.strike).toFixed(2) : 
                       (trade.longStrike > 0 ? parseFloat(trade.longStrike).toFixed(2) : 'N/A');
    
    // Calculate the hit price based on strike and percentage move
    let hitPrice = 'N/A';
    if (trade.strikeHit && trade.strikeHit.length > 0 && trade.wasHit) {
      const strategyType = EW_getStrategyType(trade.strategy);
      
      // Find the first day where strike was hit
      // The backfill stores positive values for both bullish and bearish hits
      const hitDayIndex = trade.strikeHit.findIndex(val => {
        if (val === null || val === undefined || val === "") return false;
        const pctMove = parseFloat(val);
        if (isNaN(pctMove)) return false;
        
        // Any non-zero value indicates a hit
        return pctMove !== 0;
      });
      
      if (hitDayIndex !== -1) {
        const strike = parseFloat(strikePrice);
        const pctMove = parseFloat(trade.strikeHit[hitDayIndex]);
        
        if (!isNaN(strike) && !isNaN(pctMove) && strike > 0) {
          // Calculate hit price based on strategy type and how percentMove was calculated
          if (strategyType === 'bullish') {
            // For bullish: percentMove = (hitPrice - strike) / strike
            // So: hitPrice = strike * (1 + percentMove)
            hitPrice = (strike * (1 + pctMove)).toFixed(2);
          } else if (strategyType === 'bearish') {
            // For bearish: percentMove = (strike - hitPrice) / strike  
            // So: hitPrice = strike * (1 - percentMove)
            hitPrice = (strike * (1 - pctMove)).toFixed(2);
          } else {
            // For neutral/other: use bullish formula as default
            hitPrice = (strike * (1 + pctMove)).toFixed(2);
          }
        }
      }
    }
    
    return {
      ticker: trade.ticker || 'N/A',
      strategy: trade.strategy || 'N/A',
      entryDate: EW_formatDateForReport(trade.runDate),
      strike: strikePrice,
      hitPrice: hitPrice,
      strikeAndHit: `${strikePrice} → ${hitPrice}`, // Combined display
      maxProfit: trade.maxFavorableValue || 0,  // Already in percentage form
      daysToHit: trade.daysToHit !== undefined && trade.daysToHit !== null ? trade.daysToHit : 'N/A',
      profitableDays: trade.profitableDays || 0,
      riskReward: trade.riskReward && !isNaN(trade.riskReward) ? trade.riskReward.toFixed(2) : 'N/A',
      indicators: hitIndicators,
      entryIndicators: entryIndicators,
      indicatorProfile: indicatorProfile,
      multiDayProfile: trade.maxFavorable && trade.maxFavorable.length > 0 ? 
        trade.maxFavorable.map((v, i) => 
          v !== null && !isNaN(parseFloat(v)) ? `D${i}:${(parseFloat(v) * 100).toFixed(1)}%` : null
        ).filter(v => v !== null).join(', ') : 'N/A'
    };
  });
  
  return topPlays;
}

/**
 * Create individual sheets for each analysis section
 */
function EW_createIndividualSheets(ss, insights, allTrades) {
  console.log('Creating individual analysis sheets...');
  
  // Create each specialized sheet
  EW_createOverviewSheet(ss, insights.overview);
  EW_createDataQualitySheet(ss, insights.dataQuality);
  EW_createHoldingPeriodSheet(ss, insights.holdingPeriod);
  EW_createMultiDaySheet(ss, insights.multiDayProfitability);
  EW_createIndicatorsSheet(ss, insights.indicatorEffectiveness);
  EW_createEarningsSheet(ss, insights.earningsTiming);
  // EW_createStrategiesSheet(ss, insights.strategyPerformance); // Combined with SR_Overview
  EW_createTopPlaysSheet(ss, insights.topPlays);
  EW_createRiskRewardSheet(ss, insights.riskRewardPatterns);
}

/**
 * Create Overview sheet with structured data
 */
function EW_createOverviewSheet(ss, overviewData) {
  let sheet = ss.getSheetByName('SR_Overview');
  if (!sheet) {
    sheet = ss.insertSheet('SR_Overview');
  } else {
    sheet.clear();
  }
  
  // Headers for main metrics
  const headers = ['Metric', 'Value', 'Description'];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
  
  // Write main metrics
  const metrics = [
    ['Total Trades', overviewData.totalTrades, 'Number of unique trades analyzed'],
    ['Total Observations', overviewData.totalObservations, 'Total day-observations (trades × days)'],
    ['Hit Rate', overviewData.hitRate, 'Percentage of observations where strike was hit'],
    ['Profitable Rate', overviewData.profitableRate, 'Percentage of profitable observations'],
    ['Profit Factor', overviewData.profitFactor, `$${(overviewData.profitFactor || 0).toFixed(2)} profit for every $1 loss`],
    ['Avg Profit', overviewData.avgProfit, 'Average profit when profitable'],
    ['Avg Loss', overviewData.avgLoss, 'Average loss when unprofitable'],
    ['Avg Risk/Reward', overviewData.avgRiskReward, `Risk $1 to gain $${(overviewData.avgRiskReward || 0).toFixed(2)}`],
    ['Avg Days to Hit', overviewData.avgDaysToHit, 'Average days until strike hit'],
    ['Best Holding Day', overviewData.bestHoldingDay, 'Optimal day to exit positions']
  ];
  
  sheet.getRange(2, 1, metrics.length, 3).setValues(metrics);
  
  // Strategy breakdown section
  let row = metrics.length + 4;
  sheet.getRange(row, 1).setValue('STRATEGY BREAKDOWN').setFontWeight('bold');
  row++;
  
  const stratHeaders = ['Strategy', 'Trades', 'Observations', 'Hit Rate', 'Profitable', 'Profit Factor', 'Avg Win', 'Avg Loss'];
  sheet.getRange(row, 1, 1, stratHeaders.length).setValues([stratHeaders]).setFontWeight('bold');
  row++;
  
  Object.entries(overviewData.byStrategy).forEach(([strategy, stats]) => {
    sheet.getRange(row, 1, 1, 8).setValues([[
      strategy,
      stats.totalTrades,
      stats.totalObservations,
      stats.hitRate,
      stats.profitableRate,
      stats.profitFactor || 'N/A',
      stats.avgProfit || 'N/A',
      stats.avgLoss || 'N/A'
    ]]);
    row++;
  });
  
  sheet.autoResizeColumns(1, 8);
}

/**
 * Create Data Quality sheet
 */
function EW_createDataQualitySheet(ss, qualityData) {
  let sheet = ss.getSheetByName('SR_DataQuality');
  if (!sheet) {
    sheet = ss.insertSheet('SR_DataQuality');
  } else {
    sheet.clear();
  }
  
  // Overall score
  sheet.getRange(1, 1).setValue('Overall Data Quality Score').setFontWeight('bold');
  sheet.getRange(1, 2).setValue(qualityData.overallScore);
  
  // Field completeness
  sheet.getRange(3, 1).setValue('FIELD COMPLETENESS').setFontWeight('bold');
  const headers = ['Field', 'Completeness %', 'Missing Count', 'Status'];
  sheet.getRange(4, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
  
  let row = 5;
  Object.entries(qualityData.dataCompleteness).forEach(([field, percentage]) => {
    const pct = parseFloat(percentage);
    const missing = qualityData.missingData[field];
    const status = pct >= 90 ? 'Good' : pct >= 70 ? 'Fair' : 'Poor';
    
    sheet.getRange(row, 1, 1, 4).setValues([[
      field.replace(/([A-Z])/g, ' $1').trim(),
      percentage,
      missing,
      status
    ]]);
    
    // Color code status
    const statusCell = sheet.getRange(row, 4);
    if (status === 'Good') statusCell.setBackground('#ccffcc');
    else if (status === 'Fair') statusCell.setBackground('#ffffcc');
    else statusCell.setBackground('#ffcccc');
    
    row++;
  });
  
  // Recommendations
  row += 2;
  sheet.getRange(row, 1).setValue('RECOMMENDATIONS').setFontWeight('bold');
  row++;
  
  qualityData.recommendations.forEach((rec, idx) => {
    sheet.getRange(row + idx, 1).setValue(`${idx + 1}. ${rec}`);
  });
  
  sheet.autoResizeColumns(1, 4);
}

/**
 * Create Holding Period sheet
 */
function EW_createHoldingPeriodSheet(ss, holdingData) {
  let sheet = ss.getSheetByName('SR_HoldingPeriod');
  if (!sheet) {
    sheet = ss.insertSheet('SR_HoldingPeriod');
  } else {
    sheet.clear();
  }
  
  // Optimal exit
  sheet.getRange(1, 1).setValue('OPTIMAL EXIT TIMING').setFontWeight('bold');
  sheet.getRange(2, 1).setValue('Best Day');
  sheet.getRange(2, 2).setValue(holdingData.optimalExitTiming.bestDay);
  sheet.getRange(3, 1).setValue('Profitable Rate');
  sheet.getRange(3, 2).setValue(holdingData.optimalExitTiming.profitableRate.toFixed(2) + '%');
  sheet.getRange(4, 1).setValue('Recommendation');
  sheet.getRange(4, 2).setValue(holdingData.optimalExitTiming.recommendation);
  
  // Day-by-day analysis
  sheet.getRange(6, 1).setValue('DAY-BY-DAY PERFORMANCE').setFontWeight('bold');
  const headers = ['Day', 'Total Obs', 'Profitable', 'Hit Rate', 'Profitable %', 'Avg Win', 'Avg Loss', 'Profit Factor', 'Avg Move'];
  sheet.getRange(7, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
  
  let row = 8;
  Object.entries(holdingData.byDay).forEach(([day, stats]) => {
    if (stats.totalObservations > 0) {
      sheet.getRange(row, 1, 1, 9).setValues([[
        day,
        stats.totalObservations,
        stats.profitable,
        stats.hitRate,
        stats.profitableRate,
        stats.avgProfit || 'N/A',
        stats.avgLoss || 'N/A',
        stats.profitFactor || 'N/A',
        stats.avgMove
      ]]);
      row++;
    }
  });
  
  // Decay analysis
  if (holdingData.averageDecayRate) {
    row += 2;
    sheet.getRange(row, 1).setValue('PROFIT DECAY ANALYSIS').setFontWeight('bold');
    row++;
    sheet.getRange(row, 1).setValue('Peak Day');
    sheet.getRange(row, 2).setValue(holdingData.averageDecayRate.peakDay);
    row++;
    sheet.getRange(row, 1).setValue('Avg Decay/Day');
    sheet.getRange(row, 2).setValue(holdingData.averageDecayRate.avgDecayPerDay);
    row++;
    sheet.getRange(row, 1).setValue('Analysis');
    sheet.getRange(row, 2).setValue(holdingData.averageDecayRate.recommendation);
  }
  
  sheet.autoResizeColumns(1, 9);
}

/**
 * Create Multi-Day Profitability sheet
 */
function EW_createMultiDaySheet(ss, multiDayData) {
  let sheet = ss.getSheetByName('SR_MultiDay');
  if (!sheet) {
    sheet = ss.insertSheet('SR_MultiDay');
  } else {
    sheet.clear();
  }
  
  // Sustained profitable trades
  sheet.getRange(1, 1).setValue('SUSTAINED PROFITABLE TRADES').setFontWeight('bold');
  const headers = ['Ticker', 'Strategy', 'Consecutive Days', 'Peak Day', 'Peak Value', 'Strike'];
  sheet.getRange(2, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
  
  let row = 3;
  multiDayData.sustainedProfitability.forEach(trade => {
    // Set values individually to ensure proper formatting
    sheet.getRange(row, 1).setValue(trade.ticker);
    sheet.getRange(row, 2).setValue(trade.strategy);
    sheet.getRange(row, 3).setValue(trade.consecutiveDays).setNumberFormat('0');  // Whole number
    sheet.getRange(row, 4).setValue(`Day ${trade.peakDay}`);
    sheet.getRange(row, 5).setValue(trade.peakValue.toFixed(2) + '%');  // Already percentage, just add %
    sheet.getRange(row, 6).setValue(trade.strike);
    row++;
  });
  
  // Overall profitability by day
  row += 2;
  sheet.getRange(row, 1).setValue('PROFITABILITY BY DAY').setFontWeight('bold');
  row++;
  
  const dayHeaders = ['Day', 'Total Trades', 'Profitable', 'Success Rate', 'Avg Profit'];
  sheet.getRange(row, 1, 1, dayHeaders.length).setValues([dayHeaders]).setFontWeight('bold');
  row++;
  
  Object.entries(multiDayData.profitabilityByDay).forEach(([day, stats]) => {
    sheet.getRange(row, 1, 1, 5).setValues([[
      day,
      stats.totalTrades,
      stats.profitableCount,
      stats.profitableRate.toFixed(1) + '%',
      stats.avgProfit.toFixed(2) + '%'
    ]]);
    row++;
  });
  
  sheet.autoResizeColumns(1, 6);
}

/**
 * Create Indicators sheet
 */
function EW_createIndicatorsSheet(ss, indicatorData) {
  let sheet = ss.getSheetByName('SR_Indicators');
  if (!sheet) {
    sheet = ss.insertSheet('SR_Indicators');
  } else {
    sheet.clear();
  }
  
  // High impact indicators
  sheet.getRange(1, 1).setValue('HIGH IMPACT INDICATORS').setFontWeight('bold');
  const headers = ['Type', 'Indicator', 'Correlation', 'Data %', 'Bullish Range', 'Bearish Range'];
  sheet.getRange(2, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
  
  let row = 3;
  Object.entries(indicatorData)
    .filter(([name, data]) => data.significance === 'HIGH')
    .sort((a, b) => Math.abs(b[1].correlationWithProfit) - Math.abs(a[1].correlationWithProfit))
    .forEach(([name, data]) => {
      const [type, ...indicatorParts] = name.split('_');
      const indicatorName = indicatorParts.join('_').toUpperCase();
      
      const bullishRange = data.profitableRanges.bullish.count > 0 ?
        `${data.profitableRanges.bullish.min?.toFixed(2)}-${data.profitableRanges.bullish.max?.toFixed(2)} (${(data.profitableRanges.bullish.avgProfit || 0).toFixed(2)}%)` : 'N/A';
      const bearishRange = data.profitableRanges.bearish.count > 0 ?
        `${data.profitableRanges.bearish.min?.toFixed(2)}-${data.profitableRanges.bearish.max?.toFixed(2)} (${(data.profitableRanges.bearish.avgProfit || 0).toFixed(2)}%)` : 'N/A';
      
      sheet.getRange(row, 1, 1, 6).setValues([[
        type.toUpperCase(),
        indicatorName,
        data.correlationWithProfit,
        data.dataCompleteness,
        bullishRange,
        bearishRange
      ]]);
      row++;
    });
  
  // Medium impact indicators
  row += 2;
  sheet.getRange(row, 1).setValue('MEDIUM IMPACT INDICATORS').setFontWeight('bold');
  row++;
  
  const medHeaders = ['Type', 'Indicator', 'Correlation', 'Data %'];
  sheet.getRange(row, 1, 1, medHeaders.length).setValues([medHeaders]).setFontWeight('bold');
  row++;
  
  Object.entries(indicatorData)
    .filter(([name, data]) => data.significance === 'MEDIUM')
    .forEach(([name, data]) => {
      const [type, ...indicatorParts] = name.split('_');
      const indicatorName = indicatorParts.join('_').toUpperCase();
      
      sheet.getRange(row, 1, 1, 4).setValues([[
        type.toUpperCase(),
        indicatorName,
        data.correlationWithProfit,
        data.dataCompleteness
      ]]);
      row++;
    });
  
  sheet.autoResizeColumns(1, 6);
}

/**
 * Create Earnings sheet
 */
function EW_createEarningsSheet(ss, earningsData) {
  let sheet = ss.getSheetByName('SR_Earnings');
  if (!sheet) {
    sheet = ss.insertSheet('SR_Earnings');
  } else {
    sheet.clear();
  }
  
  // Summary metrics
  sheet.getRange(1, 1).setValue('EARNINGS TIMING SUMMARY').setFontWeight('bold');
  
  let row = 2;
  Object.entries(earningsData.earningsImpact).forEach(([key, value]) => {
    const label = key.replace(/([A-Z])/g, ' $1').trim();
    sheet.getRange(row, 1).setValue(label);
    sheet.getRange(row, 2).setValue(value);
    row++;
  });
  
  // Performance by days to earnings
  row += 2;
  sheet.getRange(row, 1).setValue('PERFORMANCE BY DAYS TO EARNINGS').setFontWeight('bold');
  row++;
  
  const bucketHeaders = ['Entry Window', 'Total Trades', 'Hits', 'Hit Rate', 'Avg Profit', 'Avg Days to Hit'];
  sheet.getRange(row, 1, 1, bucketHeaders.length).setValues([bucketHeaders]).setFontWeight('bold');
  row++;
  
  Object.entries(earningsData.byDaysToEarnings).forEach(([bucket, data]) => {
    if (data.trades > 0) {
      sheet.getRange(row, 1, 1, 6).setValues([[
        bucket + ' days',
        data.trades,
        data.hits,
        data.hitRate.toFixed(1) + '%',
        data.avgProfit > 0 ? (data.avgProfit * 100).toFixed(2) + '%' : 'N/A',
        data.avgDaysToHit > 0 ? data.avgDaysToHit.toFixed(1) : 'N/A'
      ]]);
      row++;
    }
  });
  
  // Release time analysis
  row += 2;
  sheet.getRange(row, 1).setValue('PERFORMANCE BY RELEASE TIME').setFontWeight('bold');
  row++;
  
  const timeHeaders = ['Release Time', 'Total', 'Hits', 'Hit Rate', 'Avg Profit', 'Avg Days'];
  sheet.getRange(row, 1, 1, timeHeaders.length).setValues([timeHeaders]).setFontWeight('bold');
  row++;
  
  Object.entries(earningsData.byReleaseTime).forEach(([timeCategory, data]) => {
    if (data.total > 0) {
      const displayName = timeCategory === 'beforeOpen' ? 'Before Market Open' :
                         timeCategory === 'afterClose' ? 'After Market Close' : 'Unknown';
      sheet.getRange(row, 1, 1, 6).setValues([[
        displayName,
        data.total,
        data.hits,
        data.hitRate.toFixed(1) + '%',
        data.avgProfit > 0 ? (data.avgProfit * 100).toFixed(2) + '%' : 'N/A',
        data.avgDaysToHit > 0 ? data.avgDaysToHit.toFixed(1) : 'N/A'
      ]]);
      row++;
    }
  });
  
  sheet.autoResizeColumns(1, 6);
}

/**
 * Create Strategies sheet - DEPRECATED: Combined with SR_Overview
 */
// function EW_createStrategiesSheet(ss, strategyData) {
//   let sheet = ss.getSheetByName('SR_Strategies');
//   if (!sheet) {
//     sheet = ss.insertSheet('SR_Strategies');
//   } else {
//     sheet.clear();
//   }
//   
//   // Strategy performance
//   sheet.getRange(1, 1).setValue('STRATEGY PERFORMANCE ANALYSIS').setFontWeight('bold');
//   
//   const headers = ['Strategy', 'Total Trades', 'Hit Count', 'Hit Rate', 'Avg Profit', 'Avg Loss', 
//                    'Profit Factor', 'Avg Days to Hit', 'Total Profit', 'Total Loss'];
//   sheet.getRange(2, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
//   
//   let row = 3;
//   Object.entries(strategyData).forEach(([strategy, stats]) => {
//     sheet.getRange(row, 1, 1, 10).setValues([[
//       strategy,
//       stats.totalTrades,
//       stats.hitTrades,
//       stats.hitRate,
//       stats.avgProfit,
//       stats.avgLoss,
//       stats.profitFactor || 'N/A',
//       stats.avgDaysToHit || 'N/A',
//       stats.totalProfit.toFixed(2) + '%',
//       stats.totalLoss.toFixed(2) + '%'
//     ]]);
//     row++;
//   });
//   
//   sheet.autoResizeColumns(1, 10);
// }

/**
 * Create Top Plays sheet
 */
function EW_createTopPlaysSheet(ss, topPlaysData) {
  let sheet = ss.getSheetByName('SR_TopPlays');
  if (!sheet) {
    sheet = ss.insertSheet('SR_TopPlays');
  } else {
    sheet.clear();
  }
  
  // Top plays
  sheet.getRange(1, 1).setValue('TOP 20 WINNING PLAYS').setFontWeight('bold');
  
  const headers = ['Rank', 'Ticker', 'Strategy', 'Entry Date', 'Strike', 'Hit Price', 
                   'Max Profit', 'Days to Hit', 'Risk/Reward', 'Profitable Days'];
  sheet.getRange(2, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
  
  let row = 3;
  topPlaysData.forEach((play, idx) => {
    sheet.getRange(row, 1, 1, 10).setValues([[
      idx + 1,
      play.ticker,
      play.strategy,
      play.entryDate,
      play.strike,
      play.hitPrice,
      (play.maxProfit || 0).toFixed(2) + '%',
      play.daysToHit !== undefined && play.daysToHit !== null ? play.daysToHit : 'N/A',
      play.riskReward,
      play.profitableDays
    ]]);
    row++;
  });
  
  // Indicator profiles section
  row += 2;
  sheet.getRange(row, 1).setValue('INDICATOR PROFILES (TOP 5)').setFontWeight('bold');
  row++;
  
  const indHeaders = ['Ticker', 'Max Profit', 'Entry→Hit Indicators', 'Multi-Day Profile'];
  sheet.getRange(row, 1, 1, indHeaders.length).setValues([indHeaders]).setFontWeight('bold');
  row++;
  
  topPlaysData.slice(0, 5).forEach(play => {
    sheet.getRange(row, 1, 1, 4).setValues([[
      play.ticker,
      (play.maxProfit || 0).toFixed(2) + '%',
      play.indicatorProfile,
      play.multiDayProfile
    ]]);
    row++;
  });
  
  sheet.autoResizeColumns(1, 10);
}

/**
 * Create Risk/Reward sheet
 */
function EW_createRiskRewardSheet(ss, riskRewardData) {
  let sheet = ss.getSheetByName('SR_RiskReward');
  if (!sheet) {
    sheet = ss.insertSheet('SR_RiskReward');
  } else {
    sheet.clear();
  }
  
  // Risk/Reward analysis
  sheet.getRange(1, 1).setValue('RISK/REWARD ANALYSIS').setFontWeight('bold');
  
  let row = 2;
  Object.entries(riskRewardData.overview).forEach(([key, value]) => {
    const label = key.replace(/([A-Z])/g, ' $1').trim();
    sheet.getRange(row, 1).setValue(label);
    sheet.getRange(row, 2).setValue(value);
    row++;
  });
  
  // Distribution
  row += 2;
  sheet.getRange(row, 1).setValue('RISK/REWARD DISTRIBUTION').setFontWeight('bold');
  row++;
  
  const distHeaders = ['Range', 'Count', 'Percentage'];
  sheet.getRange(row, 1, 1, distHeaders.length).setValues([distHeaders]).setFontWeight('bold');
  row++;
  
  Object.entries(riskRewardData.distribution).forEach(([range, count]) => {
    const total = Object.values(riskRewardData.distribution).reduce((sum, c) => sum + c, 0);
    const percentage = ((count / total) * 100).toFixed(1) + '%';
    
    sheet.getRange(row, 1, 1, 3).setValues([[range, count, percentage]]);
    row++;
  });
  
  sheet.autoResizeColumns(1, 3);
}

/**
 * Prepare data for machine learning export
 */
function EW_prepareMachineLearningData(trades) {
  // Structure data for ML analysis
  const mlData = trades.map(trade => {
    // Flatten all data into ML-ready format
    return {
      // Target variables
      wasHit: trade.wasHit ? 1 : 0,
      maxProfit: trade.maxFavorableValue,
      daysToHit: trade.daysToHit || -1,
      profitableDays: trade.profitableDays,
      
      // Features
      strategy: trade.strategy,
      daysToExpiry: trade.expDate ? Math.floor((new Date(trade.expDate) - new Date(trade.runDate)) / (1000 * 60 * 60 * 24)) : -1,
      daysToEarnings: trade.nextEPSDate ? Math.floor((new Date(trade.nextEPSDate) - new Date(trade.runDate)) / (1000 * 60 * 60 * 24)) : -1,
      
      // Indicator values at entry (first values)
      rsi_entry: trade.indicators.rsi[0] || null,
      sma20_entry: trade.indicators.sma20[0] || null,
      sma50_entry: trade.indicators.sma50[0] || null,
      ema9_entry: trade.indicators.ema9[0] || null,
      ema21_entry: trade.indicators.ema21[0] || null,
      vwap_entry: trade.indicators.vwap[0] || null,
      rvol_entry: trade.indicators.rvol[0] || null,
      atr_entry: trade.indicators.atr[0] || null,
      priceVsSMA20_entry: trade.indicators.priceVsSMA20[0] || null,
      priceVsVWAP_entry: trade.indicators.priceVsVWAP[0] || null,
      
      // Day-by-day profit profile
      profit_day0: trade.maxFavorable[0] || null,
      profit_day1: trade.maxFavorable[1] || null,
      profit_day2: trade.maxFavorable[2] || null,
      profit_day3: trade.maxFavorable[3] || null,
      profit_day4: trade.maxFavorable[4] || null,
      profit_day5: trade.maxFavorable[5] || null
    };
  });
  
  return {
    data: mlData,
    features: [
      'strategy', 'daysToExpiry', 'daysToEarnings',
      'rsi_entry', 'sma20_entry', 'sma50_entry', 'ema9_entry', 'ema21_entry',
      'vwap_entry', 'rvol_entry', 'atr_entry', 'priceVsSMA20_entry', 'priceVsVWAP_entry'
    ],
    targets: ['wasHit', 'maxProfit', 'daysToHit', 'profitableDays'],
    recommendations: [
      'Use Random Forest or XGBoost for hit prediction',
      'Consider LSTM for multi-day profit trajectory prediction',
      'Feature importance analysis to identify key indicators',
      'Cluster analysis to find similar winning trade patterns'
    ]
  };
}

/**
 * Create the report sheet with all insights
 */
function EW_createReportSheet(ss, insights, allTrades) {
  // Create or clear report sheet
  let reportSheet = ss.getSheetByName('Success_Report');
  if (reportSheet) {
    reportSheet.clear();
  } else {
    reportSheet = ss.insertSheet('Success_Report');
  }
  
  let currentRow = 1;
  
  // Title
  reportSheet.getRange(currentRow, 1).setValue('COMPREHENSIVE SUCCESS REPORT').setFontSize(16).setFontWeight('bold');
  reportSheet.getRange(currentRow, 2).setValue(new Date().toLocaleString());
  currentRow += 2;
  
  // Overview Section
  reportSheet.getRange(currentRow, 1).setValue('OVERVIEW STATISTICS').setFontSize(14).setFontWeight('bold');
  currentRow++;
  
  // Add explanation
  reportSheet.getRange(currentRow, 1).setValue('Note: Rates are calculated based on day-observations (trades × days with data)').setFontStyle('italic');
  currentRow++;
  
  // Show overall stats first
  const mainStats = ['totalTrades', 'totalObservations', 'hitRate', 'profitableRate', 
                    'profitFactor', 'avgProfit', 'avgLoss', 'avgRiskReward', 
                    'avgDaysToHit', 'bestHoldingDay'];
  mainStats.forEach(key => {
    if (insights.overview[key] !== undefined) {
      let label = key.replace(/([A-Z])/g, ' $1').trim();
      let value = insights.overview[key];
      let formattedValue = value;
      
      // Format specific fields appropriately
      if (key === 'totalTrades' || key === 'totalObservations') {
        // Keep as plain number, no percentage
        formattedValue = value;
        reportSheet.getRange(currentRow, 1).setValue(label);
        reportSheet.getRange(currentRow, 2).setValue(formattedValue).setNumberFormat('#,##0'); // Format as number with commas
      } else if (key === 'hitRate' || key === 'profitableRate') {
        label += ' (by observation)';
        formattedValue = (value * 100).toFixed(2) + '%';
        reportSheet.getRange(currentRow, 1).setValue(label);
        reportSheet.getRange(currentRow, 2).setValue(formattedValue);
      } else if (key === 'avgProfit' || key === 'avgLoss') {
        formattedValue = (value * 100).toFixed(2) + '%';
        reportSheet.getRange(currentRow, 1).setValue(label);
        reportSheet.getRange(currentRow, 2).setValue(formattedValue);
      } else if (key === 'profitFactor' || key === 'avgRiskReward' || key === 'avgDaysToHit') {
        formattedValue = typeof value === 'number' ? value.toFixed(2) : value;
        reportSheet.getRange(currentRow, 1).setValue(label);
        reportSheet.getRange(currentRow, 2).setValue(formattedValue);
      } else {
        reportSheet.getRange(currentRow, 1).setValue(label);
        reportSheet.getRange(currentRow, 2).setValue(value);
      }
      currentRow++;
    }
  });
  currentRow += 1;
  
  // BY STRATEGY section removed - now shown comprehensively in SR_Overview sheet
  // SR_Overview contains full strategy breakdown with all metrics
  currentRow += 1;
  
  // Multi-Day Profitability Section
  reportSheet.getRange(currentRow, 1).setValue('MULTI-DAY PROFITABILITY ANALYSIS').setFontSize(14).setFontWeight('bold');
  currentRow++;
  
  reportSheet.getRange(currentRow, 1).setValue('Top Sustained Profitable Trades').setFontWeight('bold');
  currentRow++;
  
  if (insights.multiDayProfitability.sustainedProfitability.length > 0) {
    const headers = ['Ticker', 'Strategy', 'Consecutive Days', 'Peak Day', 'Peak Value', 'Strike'];
    reportSheet.getRange(currentRow, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
    currentRow++;
    
    insights.multiDayProfitability.sustainedProfitability.slice(0, 10).forEach(trade => {
      // Set values individually to avoid formatting issues
      reportSheet.getRange(currentRow, 1).setValue(trade.ticker);
      reportSheet.getRange(currentRow, 2).setValue(trade.strategy);
      reportSheet.getRange(currentRow, 3).setValue(trade.consecutiveDays).setNumberFormat('0');  // Ensure whole number
      reportSheet.getRange(currentRow, 4).setValue(`Day ${trade.peakDay}`);
      reportSheet.getRange(currentRow, 5).setValue(trade.peakValue.toFixed(2) + '%');  // Already percentage, just add %
      reportSheet.getRange(currentRow, 6).setValue(trade.strike);
      currentRow++;
    });
  }
  currentRow += 2;
  
  // Overall Profitability by Day
  reportSheet.getRange(currentRow, 1).setValue('Overall Profitability by Holding Period').setFontWeight('bold');
  currentRow++;
  
  const dayHeaders = ['Day', 'Total Trades', 'Profitable', 'Success Rate', 'Avg Profit'];
  reportSheet.getRange(currentRow, 1, 1, dayHeaders.length).setValues([dayHeaders]).setFontWeight('bold');
  currentRow++;
  
  Object.entries(insights.multiDayProfitability.profitabilityByDay).forEach(([day, stats]) => {
    // Format individual cells to prevent percentage formatting issues
    reportSheet.getRange(currentRow, 1).setValue(day);
    reportSheet.getRange(currentRow, 2).setValue(stats.totalTrades).setNumberFormat('#,##0');
    reportSheet.getRange(currentRow, 3).setValue(stats.profitableCount).setNumberFormat('#,##0');
    reportSheet.getRange(currentRow, 4).setValue(stats.profitableRate.toFixed(1) + '%');
    reportSheet.getRange(currentRow, 5).setValue(stats.avgProfit.toFixed(2) + '%');
    currentRow++;
  });
  currentRow += 2;
  
  // Multi-Day Profitability by Strategy
  reportSheet.getRange(currentRow, 1).setValue('PROFITABILITY BY STRATEGY & DAY').setFontSize(14).setFontWeight('bold');
  currentRow++;
  
  Object.entries(insights.multiDayProfitability.profitabilityByStrategy).forEach(([strategy, data]) => {
    if (Object.keys(data.byDay).length > 0) {
      reportSheet.getRange(currentRow, 1).setValue(strategy).setFontWeight('bold').setFontSize(12);
      currentRow++;
      
      // Day headers
      reportSheet.getRange(currentRow, 1, 1, dayHeaders.length).setValues([dayHeaders]).setFontWeight('bold');
      currentRow++;
      
      // Day data
      for (let day = 0; day <= 5; day++) {
        const dayKey = `Day${day}`;
        if (data.byDay[dayKey]) {
          const stats = data.byDay[dayKey];
          // Format individual cells to prevent percentage formatting issues
          reportSheet.getRange(currentRow, 1).setValue(dayKey);
          reportSheet.getRange(currentRow, 2).setValue(stats.totalTrades).setNumberFormat('#,##0');
          reportSheet.getRange(currentRow, 3).setValue(stats.profitableCount).setNumberFormat('#,##0');
          reportSheet.getRange(currentRow, 4).setValue(stats.profitableRate.toFixed(1) + '%');
          reportSheet.getRange(currentRow, 5).setValue(stats.avgProfit.toFixed(2) + '%');
          currentRow++;
        }
      }
      
      // Sustained profitable trades for this strategy
      if (data.sustainedProfitable && data.sustainedProfitable.length > 0) {
        currentRow++;
        reportSheet.getRange(currentRow, 1).setValue(`Top Sustained Profitable ${strategy} Trades:`).setFontStyle('italic');
        currentRow++;
        
        data.sustainedProfitable.slice(0, 5).forEach(trade => {
          reportSheet.getRange(currentRow, 2).setValue(
            `${trade.ticker} - ${trade.consecutiveDays} days, peak: ${trade.peakValue.toFixed(2)}%`
          );
          currentRow++;
        });
      }
      
      currentRow += 1;
    }
  });
  currentRow += 2;
  
  // Holding Period Analysis Section
  reportSheet.getRange(currentRow, 1).setValue('HOLDING PERIOD ANALYSIS').setFontSize(14).setFontWeight('bold');
  currentRow++;
  
  // Optimal exit timing
  if (insights.holdingPeriod.optimalExitTiming) {
    const profitRate = typeof insights.holdingPeriod.optimalExitTiming.profitableRate === 'number' 
      ? insights.holdingPeriod.optimalExitTiming.profitableRate.toFixed(2) + '%'
      : insights.holdingPeriod.optimalExitTiming.profitableRate;
    reportSheet.getRange(currentRow, 1).setValue('Optimal Exit: ' + insights.holdingPeriod.optimalExitTiming.bestDay + 
      ' (' + profitRate + ')').setFontWeight('bold');
    currentRow++;
  }
  
  // Day-by-day performance
  reportSheet.getRange(currentRow, 1).setValue('Performance by Holding Day:');
  currentRow++;
  
  const holdingHeaders = ['Day', 'Total Obs', 'Hit Rate', 'Profitable', 'Avg Win', 'Avg Loss', 'Profit Factor'];
  reportSheet.getRange(currentRow, 1, 1, holdingHeaders.length).setValues([holdingHeaders]).setFontWeight('bold');
  currentRow++;
  
  Object.entries(insights.holdingPeriod.byDay).forEach(([day, stats]) => {
    if (stats.totalObservations > 0) {
      // Format individual cells with proper number formats
      reportSheet.getRange(currentRow, 1).setValue(day);
      reportSheet.getRange(currentRow, 2).setValue(stats.totalObservations).setNumberFormat('#,##0');
      reportSheet.getRange(currentRow, 3).setValue(stats.hitRate / 100).setNumberFormat('0.00%');  // Convert back to decimal for percentage format
      reportSheet.getRange(currentRow, 4).setValue(stats.profitableRate / 100).setNumberFormat('0.00%');  // Convert back to decimal
      reportSheet.getRange(currentRow, 5).setValue((stats.avgProfit || 0) / 100).setNumberFormat('0.00%');  // Convert back to decimal
      reportSheet.getRange(currentRow, 6).setValue((stats.avgLoss || 0) / 100).setNumberFormat('0.00%');  // Convert back to decimal
      reportSheet.getRange(currentRow, 7).setValue(stats.profitFactor || 0).setNumberFormat('0.00');
      currentRow++;
    }
  });
  
  // Decay rate analysis
  if (insights.holdingPeriod.averageDecayRate && insights.holdingPeriod.averageDecayRate.peakDay) {
    currentRow++;
    reportSheet.getRange(currentRow, 1).setValue('Profit Decay Analysis:').setFontWeight('bold');
    currentRow++;
    reportSheet.getRange(currentRow, 1).setValue('Peak Day: ' + insights.holdingPeriod.averageDecayRate.peakDay);
    reportSheet.getRange(currentRow, 2).setValue('Avg Decay/Day: ' + (insights.holdingPeriod.averageDecayRate.avgDecayPerDay || 0).toFixed(2) + '%');
    currentRow++;
    reportSheet.getRange(currentRow, 1).setValue(insights.holdingPeriod.averageDecayRate.recommendation).setFontStyle('italic');
    currentRow++;
  }
  
  // Holding period recommendations
  if (insights.holdingPeriod.recommendations.length > 0) {
    currentRow++;
    reportSheet.getRange(currentRow, 1).setValue('Recommendations:').setFontWeight('bold');
    currentRow++;
    insights.holdingPeriod.recommendations.forEach(rec => {
      reportSheet.getRange(currentRow, 1).setValue('• ' + rec);
      currentRow++;
    });
  }
  
  currentRow += 2;
  
  // Data Quality Section
  reportSheet.getRange(currentRow, 1).setValue('DATA QUALITY ANALYSIS').setFontSize(14).setFontWeight('bold');
  currentRow++;
  
  reportSheet.getRange(currentRow, 1).setValue('Overall Data Quality Score: ' + insights.dataQuality.overallScore).setFontWeight('bold');
  currentRow++;
  
  // Data completeness table
  reportSheet.getRange(currentRow, 1).setValue('Field Completeness:');
  currentRow++;
  
  Object.entries(insights.dataQuality.dataCompleteness).forEach(([field, percentage]) => {
    const displayName = field.replace(/([A-Z])/g, ' $1').trim();
    reportSheet.getRange(currentRow, 1).setValue(displayName);
    reportSheet.getRange(currentRow, 2).setValue(percentage);
    // Color code based on completeness
    const pct = parseFloat(percentage);
    if (pct < 50) {
      reportSheet.getRange(currentRow, 2).setBackground('#ffcccc'); // Red
    } else if (pct < 80) {
      reportSheet.getRange(currentRow, 2).setBackground('#ffffcc'); // Yellow
    } else {
      reportSheet.getRange(currentRow, 2).setBackground('#ccffcc'); // Green
    }
    currentRow++;
  });
  
  // Recommendations
  if (insights.dataQuality.recommendations.length > 0) {
    currentRow++;
    reportSheet.getRange(currentRow, 1).setValue('Recommendations:').setFontWeight('bold');
    currentRow++;
    
    insights.dataQuality.recommendations.forEach(rec => {
      reportSheet.getRange(currentRow, 1).setValue('• ' + rec);
      currentRow++;
    });
  }
  
  // INDICATOR EFFECTIVENESS ANALYSIS removed - now shown in SR_Indicators sheet
  // The SR_Indicators sheet contains comprehensive indicator analysis
  currentRow += 2;
  
  // Earnings Timing Analysis
  reportSheet.getRange(currentRow, 1).setValue('EARNINGS TIMING ANALYSIS').setFontSize(14).setFontWeight('bold');
  currentRow++;
  
  Object.entries(insights.earningsTiming.earningsImpact).forEach(([key, value]) => {
    const label = key.replace(/([A-Z])/g, ' $1').trim();
    const cell = reportSheet.getRange(currentRow, 2);
    
    // Format based on the field type
    if (key === 'totalTradesAnalyzed' || key === 'tradesWithEarningsData' || 
        key === 'tradesWithoutEarningsData' || key === 'preEarningsHits' || 
        key === 'postEarningsHits') {
      // These should be numbers, not percentages
      cell.setValue(value).setNumberFormat('#,##0');
    } else if (key.includes('Rate') || key === 'dataCompleteness') {
      // These are percentages
      cell.setValue(value);
    } else if (key.includes('avgProfit')) {
      // Format profit as percentage (already in percentage form)
      const numValue = typeof value === 'number' ? value.toFixed(2) + '%' : value;
      cell.setValue(numValue);
    } else {
      cell.setValue(value);
    }
    
    reportSheet.getRange(currentRow, 1).setValue(label);
    currentRow++;
  });
  currentRow += 2;
  
  // STRATEGY PERFORMANCE BREAKDOWN removed - now shown in SR_Overview sheet
  // The SR_Overview sheet contains comprehensive strategy metrics including:
  // - Total Trades, Hit Count, Hit Rate
  // - Avg Profit, Avg Loss, Profit Factor
  // - Avg Days to Hit, Total Profit, Total Loss
  
  // Top Plays
  reportSheet.getRange(currentRow, 1).setValue('TOP 20 WINNING PLAYS').setFontSize(14).setFontWeight('bold');
  currentRow++;
  
  const topHeaders = ['Ticker', 'Strategy', 'Entry Date', 'Strike → Hit', 'Max Profit', 'Days to Hit', 'Risk/Reward'];
  reportSheet.getRange(currentRow, 1, 1, topHeaders.length).setValues([topHeaders]).setFontWeight('bold');
  currentRow++;
  
  insights.topPlays.forEach(play => {
    reportSheet.getRange(currentRow, 1, 1, 7).setValues([[
      play.ticker || '', 
      play.strategy || '', 
      play.entryDate || 'N/A', 
      play.strikeAndHit || 'N/A',
      play.maxProfit ? play.maxProfit.toFixed(2) + '%' : 'N/A', 
      play.daysToHit !== undefined && play.daysToHit !== null ? play.daysToHit : 'N/A', 
      play.riskReward || 'N/A'
    ]]);
    currentRow++;
  });
  
  // Note about indicator profiles being on separate sheet
  currentRow++;
  reportSheet.getRange(currentRow, 1).setValue('INDICATOR PROFILES').setFontWeight('bold');
  reportSheet.getRange(currentRow, 2).setValue('See "Indicator_Profiles" sheet for detailed analysis').setFontStyle('italic');
  currentRow += 2;
  
  // ML Recommendations
  reportSheet.getRange(currentRow, 1).setValue('MACHINE LEARNING RECOMMENDATIONS').setFontSize(14).setFontWeight('bold');
  currentRow++;
  
  reportSheet.getRange(currentRow, 1).setValue(`Dataset: ${insights.mlReadyData.data.length} trades ready for ML analysis`);
  currentRow++;
  
  insights.mlReadyData.recommendations.forEach(rec => {
    reportSheet.getRange(currentRow, 1).setValue(`• ${rec}`);
    currentRow++;
  });
  
  // Format the sheet
  reportSheet.autoResizeColumns(1, 8);
  reportSheet.setFrozenRows(3);
  
  // Add conditional formatting for profit values
  try {
    const profitColumns = [4, 5, 6, 7]; // Columns D, E, F, G
    const rules = [];
    
    profitColumns.forEach(col => {
      const range = reportSheet.getRange(4, col, reportSheet.getLastRow() - 3, 1);
      
      // Green for positive values
      const positiveRule = SpreadsheetApp.newConditionalFormatRule()
        .whenNumberGreaterThan(0)
        .setBackground('#D4EDDA')
        .setFontColor('#155724')
        .setRanges([range])
        .build();
      
      // Red for negative values
      const negativeRule = SpreadsheetApp.newConditionalFormatRule()
        .whenNumberLessThan(0)
        .setBackground('#F8D7DA')
        .setFontColor('#721C24')
        .setRanges([range])
        .build();
      
      rules.push(positiveRule, negativeRule);
    });
    
    reportSheet.setConditionalFormatRules(rules);
  } catch (e) {
    console.log('Failed to apply conditional formatting:', e);
  }
}

/**
 * Export ML-ready data to CSV
 */
function EW_exportMLData() {
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  
  // Collect all data
  const allTrades = [];
  for (const strategy of strategies) {
    const sheet = ss.getSheetByName(strategy);
    if (!sheet || sheet.getLastRow() < 2) continue;
    const trades = EW_extractTradeData(sheet, strategy);
    allTrades.push(...trades);
  }
  
  const mlData = EW_prepareMachineLearningData(allTrades);
  
  // Create CSV content
  const headers = Object.keys(mlData.data[0]);
  let csv = headers.join(',') + '\n';
  
  mlData.data.forEach(row => {
    csv += headers.map(h => row[h] !== null ? row[h] : '').join(',') + '\n';
  });
  
  // Create a new sheet for ML data
  let mlSheet = ss.getSheetByName('ML_Export');
  if (mlSheet) {
    mlSheet.clear();
  } else {
    mlSheet = ss.insertSheet('ML_Export');
  }
  
  // Parse CSV back to array for sheet
  const rows = csv.split('\n').map(row => row.split(','));
  if (rows.length > 0 && rows[0].length > 0) {
    mlSheet.getRange(1, 1, rows.length, rows[0].length).setValues(rows);
  }
  
  EW_safeAlert(
    'ML Data Exported',
    `Exported ${mlData.data.length} trades to "ML_Export" sheet.\n\n` +
    `Features: ${mlData.features.length}\n` +
    `Ready for analysis in Python, R, or your preferred ML platform.`
  );
}

// ===== QUICK ACCESS ANALYSIS FUNCTIONS =====
// These provide focused views of specific analyses from the menu

/**
 * Show top 20 winning plays in a quick report
 */
function EW_showTopWinningPlays() {
  const ss = SpreadsheetApp.getActive();
  const allTrades = EW_collectAllTrades(ss);
  const topPlays = EW_identifyTopPlays(allTrades);
  
  // Create or clear sheet
  let sheet = ss.getSheetByName('Top_Winning_Plays');
  if (sheet) {
    sheet.clear();
  } else {
    sheet = ss.insertSheet('Top_Winning_Plays');
  }
  
  // Title
  sheet.getRange(1, 1).setValue('TOP 20 WINNING PLAYS').setFontSize(16).setFontWeight('bold');
  sheet.getRange(1, 2).setValue(new Date().toLocaleString());
  
  // Headers
  const headers = ['Rank', 'Ticker', 'Strategy', 'Entry Date', 'Strike → Hit', 'Max Profit', 
                   'Days to Hit', 'Profitable Days', 'Risk/Reward', 'Multi-Day Profile'];
  sheet.getRange(3, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
  
  // Data
  topPlays.forEach((play, idx) => {
    sheet.getRange(idx + 4, 1, 1, 10).setValues([[
      idx + 1, 
      play.ticker || '', 
      play.strategy || '', 
      play.entryDate || 'N/A', 
      play.strikeAndHit || 'N/A',
      play.maxProfit ? play.maxProfit.toFixed(2) + '%' : 'N/A', 
      play.daysToHit !== undefined && play.daysToHit !== null ? play.daysToHit : 'N/A', 
      play.profitableDays !== undefined && play.profitableDays !== null ? play.profitableDays : 0, 
      play.riskReward || 'N/A',
      play.multiDayProfile || 'N/A'
    ]]);
  });
  
  // Add key indicators for top plays
  sheet.getRange(25, 1).setValue('KEY INDICATORS AT ENTRY').setFontWeight('bold');
  
  let indicatorRow = 26;
  topPlays.slice(0, 5).forEach(play => {
    sheet.getRange(indicatorRow, 1).setValue(`${play.ticker} (${play.maxProfit.toFixed(2)}%):`);
    let indicatorStr = Object.entries(play.indicators)
      .map(([key, value]) => `${key}: ${value}`)
      .join(', ');
    sheet.getRange(indicatorRow, 2).setValue(indicatorStr);
    indicatorRow++;
  });
  
  sheet.autoResizeColumns(1, 10);
  SpreadsheetApp.setActiveSheet(sheet);
  
  EW_safeAlert(
    'Top Plays Report Generated',
    `Found ${topPlays.length} winning plays with >5% profit.\n\nCheck the "Top_Winning_Plays" sheet.`
  );
}

/**
 * Show multi-day profitability analysis
 */
function EW_showMultiDayReport() {
  const ss = SpreadsheetApp.getActive();
  const allTrades = EW_collectAllTrades(ss);
  const analysis = EW_analyzeMultiDayProfitability(allTrades);
  
  // Create or clear sheet
  let sheet = ss.getSheetByName('Multi_Day_Analysis');
  if (sheet) {
    sheet.clear();
  } else {
    sheet = ss.insertSheet('Multi_Day_Analysis');
  }
  
  // Title
  sheet.getRange(1, 1).setValue('MULTI-DAY PROFITABILITY ANALYSIS').setFontSize(16).setFontWeight('bold');
  sheet.getRange(1, 2).setValue(new Date().toLocaleString());
  
  // Sustained profitability
  sheet.getRange(3, 1).setValue('Trades with 3+ Consecutive Profitable Days').setFontWeight('bold');
  const headers = ['Ticker', 'Strategy', 'Consecutive Days', 'Peak Day', 'Peak Value', 'Strike'];
  sheet.getRange(4, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
  
  analysis.sustainedProfitability.slice(0, 20).forEach((trade, idx) => {
    sheet.getRange(idx + 5, 1, 1, 6).setValues([[
      trade.ticker, trade.strategy, trade.consecutiveDays,
      `Day ${trade.peakDay}`, trade.peakValue.toFixed(2) + '%', trade.strike
    ]]);
  });
  
  // Day-by-day profitability
  const dayRow = Math.max(25, analysis.sustainedProfitability.length + 7);
  sheet.getRange(dayRow, 1).setValue('Profitability by Holding Period').setFontWeight('bold');
  
  const dayHeaders = ['Day', 'Total Trades', 'Profitable', 'Success Rate', 'Avg Profit'];
  sheet.getRange(dayRow + 1, 1, 1, dayHeaders.length).setValues([dayHeaders]).setFontWeight('bold');
  
  Object.entries(analysis.profitabilityByDay).forEach(([day, stats], idx) => {
    sheet.getRange(dayRow + 2 + idx, 1, 1, 5).setValues([[
      day, stats.totalTrades, stats.profitableCount, stats.profitableRate.toFixed(1) + '%', stats.avgProfit.toFixed(2) + '%'
    ]]);
  });
  
  sheet.autoResizeColumns(1, 6);
  SpreadsheetApp.setActiveSheet(sheet);
  
  EW_safeAlert(
    'Multi-Day Analysis Complete',
    `Found ${analysis.sustainedProfitability.length} trades with sustained profitability.\n\n` +
    `Check the "Multi_Day_Analysis" sheet.`
  );
}

/**
 * Show indicator effectiveness analysis
 */
function EW_showIndicatorAnalysis() {
  const ss = SpreadsheetApp.getActive();
  const allTrades = EW_collectAllTrades(ss);
  const analysis = EW_analyzeIndicatorEffectiveness(allTrades);
  
  // Create or clear sheet
  let sheet = ss.getSheetByName('Indicator_Analysis');
  if (sheet) {
    sheet.clear();
  } else {
    sheet = ss.insertSheet('Indicator_Analysis');
  }
  
  // Title
  sheet.getRange(1, 1).setValue('INDICATOR EFFECTIVENESS ANALYSIS').setFontSize(16).setFontWeight('bold');
  sheet.getRange(1, 2).setValue(new Date().toLocaleString());
  
  // Entry-time indicators
  sheet.getRange(3, 1).setValue('Entry-Time Indicators (High Impact)').setFontWeight('bold');
  
  let row = 4;
  const headers = ['Indicator', 'Correlation', 'Data %', 'Bullish Range', 'Bearish Range'];
  sheet.getRange(row, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
  row++;
  
  Object.entries(analysis)
    .filter(([name, data]) => data.type === 'entry' && data.significance === 'HIGH')
    .sort((a, b) => Math.abs(b[1].correlationWithProfit) - Math.abs(a[1].correlationWithProfit))
    .forEach(([name, data]) => {
      const indicatorName = name.replace('entry_', '').toUpperCase();
      const bullishRange = data.profitableRanges.bullish.count > 0 ?
        `${data.profitableRanges.bullish.min?.toFixed(2)}-${data.profitableRanges.bullish.max?.toFixed(2)} (${(data.profitableRanges.bullish.avgProfit || 0).toFixed(2)}%)` : 'N/A';
      const bearishRange = data.profitableRanges.bearish.count > 0 ?
        `${data.profitableRanges.bearish.min?.toFixed(2)}-${data.profitableRanges.bearish.max?.toFixed(2)} (${(data.profitableRanges.bearish.avgProfit || 0).toFixed(2)}%)` : 'N/A';
      
      sheet.getRange(row, 1, 1, 5).setValues([[
        indicatorName, data.correlationWithProfit, data.dataCompleteness,
        bullishRange, bearishRange
      ]]);
      row++;
    });
  
  // Hit-time indicators
  row += 2;
  sheet.getRange(row, 1).setValue('Hit-Time Indicators (High Impact)').setFontWeight('bold');
  row++;
  
  sheet.getRange(row, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
  row++;
  
  Object.entries(analysis)
    .filter(([name, data]) => data.type === 'hit' && data.significance === 'HIGH')
    .sort((a, b) => Math.abs(b[1].correlationWithProfit) - Math.abs(a[1].correlationWithProfit))
    .forEach(([name, data]) => {
      const indicatorName = name.replace('hit_', '').toUpperCase();
      const bullishRange = data.profitableRanges.bullish.count > 0 ?
        `${data.profitableRanges.bullish.min?.toFixed(2)}-${data.profitableRanges.bullish.max?.toFixed(2)} (${(data.profitableRanges.bullish.avgProfit || 0).toFixed(2)}%)` : 'N/A';
      const bearishRange = data.profitableRanges.bearish.count > 0 ?
        `${data.profitableRanges.bearish.min?.toFixed(2)}-${data.profitableRanges.bearish.max?.toFixed(2)} (${(data.profitableRanges.bearish.avgProfit || 0).toFixed(2)}%)` : 'N/A';
      
      sheet.getRange(row, 1, 1, 5).setValues([[
        indicatorName, data.correlationWithProfit, data.dataCompleteness,
        bullishRange, bearishRange
      ]]);
      row++;
    });
  
  // Medium impact summary
  row += 2;
  sheet.getRange(row, 1).setValue('Medium-Impact Indicators Summary').setFontWeight('bold');
  row++;
  
  const mediumHeaders = ['Type', 'Indicator', 'Correlation', 'Data %'];
  sheet.getRange(row, 1, 1, mediumHeaders.length).setValues([mediumHeaders]).setFontWeight('bold');
  row++;
  
  Object.entries(analysis)
    .filter(([name, data]) => data.significance === 'MEDIUM')
    .sort((a, b) => Math.abs(b[1].correlationWithProfit) - Math.abs(a[1].correlationWithProfit))
    .forEach(([name, data]) => {
      const [type, ...indicatorParts] = name.split('_');
      const indicatorName = indicatorParts.join('_').toUpperCase();
      sheet.getRange(row, 1, 1, 4).setValues([[
        type.toUpperCase(), indicatorName, data.correlationWithProfit, data.dataCompleteness
      ]]);
      row++;
    });
  
  sheet.autoResizeColumns(1, 5);
  SpreadsheetApp.setActiveSheet(sheet);
  
  const highImpact = Object.values(analysis).filter(d => d.significance === 'HIGH').length;
  
  EW_safeAlert(
    'Indicator Analysis Complete',
    `Found ${highImpact} high-impact indicators with strong correlation to profitability.\n\n` +
    `Check the "Indicator_Analysis" sheet.`
  );
}

/**
 * Show earnings timing analysis
 */
function EW_showEarningsTimingReport() {
  const ss = SpreadsheetApp.getActive();
  const allTrades = EW_collectAllTrades(ss);
  const analysis = EW_analyzeEarningsTiming(allTrades);
  
  // Create or clear sheet
  let sheet = ss.getSheetByName('Earnings_Timing');
  if (sheet) {
    sheet.clear();
  } else {
    sheet = ss.insertSheet('Earnings_Timing');
  }
  
  // Title
  sheet.getRange(1, 1).setValue('EARNINGS TIMING ANALYSIS').setFontSize(16).setFontWeight('bold');
  sheet.getRange(1, 2).setValue(new Date().toLocaleString());
  
  // Summary
  sheet.getRange(3, 1).setValue('Summary').setFontWeight('bold');
  let row = 4;
  
  Object.entries(analysis.earningsImpact).forEach(([key, value]) => {
    sheet.getRange(row, 1).setValue(key.replace(/([A-Z])/g, ' $1').trim());
    sheet.getRange(row, 2).setValue(value);
    row++;
  });
  
  // Performance by Days to Earnings
  row += 2;
  sheet.getRange(row, 1).setValue('Performance by Days to Earnings').setFontWeight('bold');
  row++;
  
  const bucketHeaders = ['Entry Window', 'Total Trades', 'Hit Rate', 'Avg Profit', 'Avg Days to Hit'];
  sheet.getRange(row, 1, 1, bucketHeaders.length).setValues([bucketHeaders]).setFontWeight('bold');
  row++;
  
  Object.entries(analysis.byDaysToEarnings).forEach(([bucket, data]) => {
    if (data.trades > 0) {
      sheet.getRange(row, 1, 1, 5).setValues([[
        bucket + ' days',
        data.trades,
        data.hitRate.toFixed(1) + '%',
        data.avgProfit > 0 ? (data.avgProfit * 100).toFixed(2) + '%' : 'N/A',
        data.avgDaysToHit > 0 ? data.avgDaysToHit.toFixed(1) : 'N/A'
      ]]);
      row++;
    }
  });
  
  // Performance by Release Time
  row += 2;
  sheet.getRange(row, 1).setValue('Performance by Release Time').setFontWeight('bold');
  row++;
  
  const timeHeaders = ['Release Time', 'Total Trades', 'Hit Rate', 'Avg Profit', 'Avg Days to Hit'];
  sheet.getRange(row, 1, 1, timeHeaders.length).setValues([timeHeaders]).setFontWeight('bold');
  row++;
  
  Object.entries(analysis.byReleaseTime).forEach(([timeCategory, data]) => {
    if (data.total > 0) {
      const displayName = timeCategory === 'beforeOpen' ? 'Before Market Open' :
                         timeCategory === 'afterClose' ? 'After Market Close' : 'Unknown';
      sheet.getRange(row, 1, 1, 5).setValues([[
        displayName,
        data.total,
        data.hitRate.toFixed(1) + '%',
        data.avgProfit > 0 ? (data.avgProfit * 100).toFixed(2) + '%' : 'N/A',
        data.avgDaysToHit > 0 ? data.avgDaysToHit.toFixed(1) : 'N/A'
      ]]);
      row++;
    }
  });
  
  // Pre-earnings hits
  row += 2;
  sheet.getRange(row, 1).setValue('Top Pre-Earnings Hits').setFontWeight('bold');
  row++;
  
  const preHeaders = ['Ticker', 'Strategy', 'Days to Earnings', 'Days to Hit', 'Max Profit'];
  sheet.getRange(row, 1, 1, preHeaders.length).setValues([preHeaders]).setFontWeight('bold');
  row++;
  
  analysis.preEarningsHits
    .sort((a, b) => b.maxProfit - a.maxProfit)
    .slice(0, 10)
    .forEach(trade => {
      sheet.getRange(row, 1, 1, 5).setValues([[
        trade.ticker, trade.strategy, trade.daysToEarnings,
        trade.daysToHit !== undefined && trade.daysToHit !== null ? trade.daysToHit : 'N/A', 
        trade.maxProfit.toFixed(2) + '%'
      ]]);
      row++;
    });
  
  // Post-earnings hits
  row += 2;
  sheet.getRange(row, 1).setValue('Top Post-Earnings Hits').setFontWeight('bold');
  row++;
  
  sheet.getRange(row, 1, 1, preHeaders.length).setValues([preHeaders]).setFontWeight('bold');
  row++;
  
  analysis.postEarningsHits
    .sort((a, b) => b.maxProfit - a.maxProfit)
    .slice(0, 10)
    .forEach(trade => {
      sheet.getRange(row, 1, 1, 5).setValues([[
        trade.ticker, trade.strategy, trade.daysToEarnings,
        trade.daysToHit !== undefined && trade.daysToHit !== null ? trade.daysToHit : 'N/A', 
        trade.maxProfit.toFixed(2) + '%'
      ]]);
      row++;
    });
  
  sheet.autoResizeColumns(1, 5);
  SpreadsheetApp.setActiveSheet(sheet);
  
  EW_safeAlert(
    'Earnings Timing Analysis Complete',
    `Analyzed ${analysis.preEarningsHits.length + analysis.postEarningsHits.length} trades with earnings data.\n\n` +
    `${analysis.earningsImpact.recommendation}\n\n` +
    `Check the "Earnings_Timing" sheet.`
  );
}

/**
 * Show strategy performance summary
 */
function EW_showStrategyPerformance() {
  const ss = SpreadsheetApp.getActive();
  const allTrades = EW_collectAllTrades(ss);
  const analysis = EW_analyzeStrategyPerformance(allTrades);
  
  // Create or clear sheet
  let sheet = ss.getSheetByName('Strategy_Performance');
  if (sheet) {
    sheet.clear();
  } else {
    sheet = ss.insertSheet('Strategy_Performance');
  }
  
  // Title
  sheet.getRange(1, 1).setValue('STRATEGY PERFORMANCE SUMMARY').setFontSize(16).setFontWeight('bold');
  sheet.getRange(1, 2).setValue(new Date().toLocaleString());
  
  // Performance table
  sheet.getRange(3, 1).setValue('Performance by Strategy').setFontWeight('bold');
  
  const headers = ['Strategy', 'Total Trades', 'Hit Rate', 'Avg Profit', 'Avg Loss', 
                   'Profit Factor', 'Avg Days to Hit'];
  sheet.getRange(4, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
  
  let row = 5;
  Object.entries(analysis).forEach(([strategy, stats]) => {
    sheet.getRange(row, 1, 1, 7).setValues([[
      strategy, stats.totalTrades, stats.hitRate, stats.avgProfit,
      stats.avgLoss, stats.profitFactor, stats.avgDaysToHit
    ]]);
    row++;
  });
  
  // Best performers by strategy
  row += 2;
  sheet.getRange(row, 1).setValue('Top Performers by Strategy').setFontWeight('bold');
  row++;
  
  Object.entries(analysis).forEach(([strategy, stats]) => {
    if (stats.bestPerformers.length > 0) {
      sheet.getRange(row, 1).setValue(strategy).setFontWeight('bold');
      row++;
      
      stats.bestPerformers.forEach(performer => {
        sheet.getRange(row, 2).setValue(`${performer.ticker}: ${performer.profit} (${performer.daysHeld} days)`);
        row++;
      });
      row++;
    }
  });
  
  sheet.autoResizeColumns(1, 7);
  SpreadsheetApp.setActiveSheet(sheet);
  
  const bestStrategy = Object.entries(analysis)
    .sort((a, b) => parseFloat(b[1].profitFactor) - parseFloat(a[1].profitFactor))[0];
  
  EW_safeAlert(
    'Strategy Performance Analysis Complete',
    `Best performing strategy: ${bestStrategy[0]} with profit factor ${bestStrategy[1].profitFactor}\n\n` +
    `Check the "Strategy_Performance" sheet.`
  );
}

/**
 * Helper function to collect all trades
 */
function EW_collectAllTrades(ss) {
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  const allTrades = [];
  
  for (const strategy of strategies) {
    const sheet = ss.getSheetByName(strategy);
    if (!sheet || sheet.getLastRow() < 2) continue;
    const trades = EW_extractTradeData(sheet, strategy);
    allTrades.push(...trades);
  }
  
  return allTrades;
}

/**
 * Test observation counting logic
 * This function verifies that observation counting is working correctly
 * based on array lengths instead of Day_Check fields
 */
function EW_testObservationCounting() {
  console.log('=== Testing Observation Counting Logic ===');
  
  // Sample test data
  const testTrade = {
    ticker: 'TEST',
    strategy: 'Long Calls',
    maxFavorable: ["0.0485", "0.0563", "0.1642", "0.1515", "0.1180", "0.1338"],
    minUnfavorable: ["0.0100", "0.0200", "0.0150", "0.0250", "0.0300", "0.0180"],
    strikeHit: ["0.0485", "0.0563", "0.1642", null, null, null],
    dayChecks: ["238.50", "239.20", "243.40", null, null, null] // Only 3 days of Day_Check data
  };
  
  // Calculate observation count using array length
  const observationCount = Math.max(
    testTrade.maxFavorable.filter(v => v !== null && v !== undefined).length,
    testTrade.minUnfavorable.filter(v => v !== null && v !== undefined).length,
    testTrade.strikeHit.filter(v => v !== null && v !== undefined && v !== "").length
  );
  
  console.log(`Test trade arrays:`);
  console.log(`  maxFavorable length: ${testTrade.maxFavorable.length}`);
  console.log(`  minUnfavorable length: ${testTrade.minUnfavorable.length}`);
  console.log(`  strikeHit non-null values: ${testTrade.strikeHit.filter(v => v !== null && v !== undefined && v !== "").length}`);
  console.log(`  dayChecks non-null values: ${testTrade.dayChecks.filter(v => v !== null && v !== undefined && v !== "").length}`);
  console.log(`\nCalculated observation count: ${observationCount} (should be 6)`);
  
  // Test with partial data
  const partialTrade = {
    ticker: 'PARTIAL',
    strategy: 'Long Calls',
    maxFavorable: ["0.038494"],
    minUnfavorable: ["0.005000"],
    strikeHit: ["0.038494"],
    dayChecks: ["235.00", null, null, null, null, null]
  };
  
  const partialObservationCount = Math.max(
    partialTrade.maxFavorable.filter(v => v !== null && v !== undefined).length,
    partialTrade.minUnfavorable.filter(v => v !== null && v !== undefined).length,
    partialTrade.strikeHit.filter(v => v !== null && v !== undefined && v !== "").length
  );
  
  console.log(`\nPartial trade arrays:`);
  console.log(`  maxFavorable length: ${partialTrade.maxFavorable.length}`);
  console.log(`  minUnfavorable length: ${partialTrade.minUnfavorable.length}`);
  console.log(`  strikeHit non-null values: ${partialTrade.strikeHit.filter(v => v !== null && v !== undefined && v !== "").length}`);
  console.log(`  dayChecks non-null values: ${partialTrade.dayChecks.filter(v => v !== null && v !== undefined && v !== "").length}`);
  console.log(`\nCalculated observation count: ${partialObservationCount} (should be 1)`);
  
  // Test observation counting with real data
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName('Long Calls');
    if (sheet) {
      const allTrades = EW_extractTradesFromSheets(['Long Calls']);
      const analysis = EW_analyzeOverview(allTrades);
      
      console.log(`\nReal data analysis:`);
      console.log(`  Total trades: ${analysis.totalTrades}`);
      console.log(`  Total observations: ${analysis.totalObservations}`);
      console.log(`  Expected ratio: Each trade can have 1-6 observations`);
      
      // Count trades by observation count
      const observationCounts = {};
      allTrades.forEach(trade => {
        const count = Math.max(
          trade.maxFavorable.filter(v => v !== null && v !== undefined).length,
          trade.minUnfavorable.filter(v => v !== null && v !== undefined).length,
          trade.strikeHit.filter(v => v !== null && v !== undefined && v !== "").length
        );
        observationCounts[count] = (observationCounts[count] || 0) + 1;
      });
      
      console.log(`\nTrades by observation count:`);
      Object.entries(observationCounts).sort((a, b) => a[0] - b[0]).forEach(([count, trades]) => {
        console.log(`  ${count} observations: ${trades} trades`);
      });
    }
  } catch (e) {
    console.log(`Error testing with real data: ${e.message}`);
  }
  
  console.log('\n=== Test Complete ===');
}