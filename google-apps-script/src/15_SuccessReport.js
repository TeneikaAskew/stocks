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
  
  const duration = Math.round((new Date() - startTime) / 1000);
  console.log(`Success report generated in ${duration} seconds`);
  
  // Only show alert if in spreadsheet environment (not triggered)
  if (EW_isSpreadsheetEnvironment()) {
    SpreadsheetApp.getUi().alert(
      'Success Report Generated',
      `Analysis complete. Processed ${allTrades.length} trades in ${duration} seconds.\n\n` +
      `Check the "Success_Report" sheet for insights.`,
      SpreadsheetApp.getUi().ButtonSet.OK
    );
  }
}

/**
 * Update success report - alias for generate
 * This is called from the menu for clarity
 */
function EW_updateSuccessReport() {
  EW_generateSuccessReport();
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
  const trades = [];
  
  data.forEach((row, idx) => {
    try {
      const trade = {
        // Basic info
        strategy: strategy,
        ticker: row[hdrMap.tickerCol - 1],
        runDate: row[hdrMap.runDateCol - 1],
        expDate: row[hdrMap.expDateCol - 1],
        strike: parseFloat(row[hdrMap.strikeCol - 1]) || 0,
        longStrike: parseFloat(row[hdrMap.longStrikeCol - 1]) || 0,
        shortStrike: parseFloat(row[hdrMap.shortStrikeCol - 1]) || 0,
        
        // Dates
        nextEPSDate: row[hdrMap.nextEPSDateCol - 1],
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
        
        // Indicators (parsed arrays)
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
      trade.wasHit = trade.strikeHit.some(hit => hit !== "NO" && hit !== null);
      trade.maxFavorableValue = Math.max(...trade.maxFavorable.filter(v => v !== null).map(v => parseFloat(v) || 0));
      trade.maxUnfavorableValue = Math.max(...trade.minUnfavorable.filter(v => v !== null).map(v => parseFloat(v) || 0));
      trade.profitableDays = trade.maxFavorable.filter(v => v !== null && parseFloat(v) > 0).length;
      
      // Days to hit
      if (trade.firstHitDate && trade.runDate) {
        const hit = new Date(trade.firstHitDate);
        const run = new Date(trade.runDate);
        trade.daysToHit = Math.floor((hit - run) / (1000 * 60 * 60 * 24));
      }
      
      trades.push(trade);
    } catch (e) {
      console.error(`Error parsing trade at row ${idx + 2}: ${e.message}`);
    }
  });
  
  return trades;
}

/**
 * Analyze overview statistics
 */
function EW_analyzeOverview(trades) {
  const totalTrades = trades.length;
  const hitTrades = trades.filter(t => t.wasHit).length;
  const profitableTrades = trades.filter(t => t.maxFavorableValue > t.maxUnfavorableValue).length;
  
  return {
    totalTrades: totalTrades,
    hitRate: (hitTrades / totalTrades * 100).toFixed(2) + '%',
    profitableRate: (profitableTrades / totalTrades * 100).toFixed(2) + '%',
    avgRiskReward: (trades.reduce((sum, t) => sum + (t.riskReward || 0), 0) / totalTrades).toFixed(2),
    avgDaysToHit: (trades.filter(t => t.daysToHit !== undefined)
      .reduce((sum, t) => sum + t.daysToHit, 0) / hitTrades).toFixed(1)
  };
}

/**
 * Analyze multi-day profitability patterns
 */
function EW_analyzeMultiDayProfitability(trades) {
  const analysis = {
    sustainedProfitability: [],
    profitabilityByDay: {},
    bestHoldingPeriod: {}
  };
  
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
      analysis.sustainedProfitability.push({
        ticker: trade.ticker,
        strategy: trade.strategy,
        consecutiveDays: maxConsecutive,
        peakDay: peakDay,
        peakValue: peakValue.toFixed(2) + '%',
        strike: trade.strike || trade.longStrike
      });
    }
  });
  
  // Sort by consecutive days
  analysis.sustainedProfitability.sort((a, b) => b.consecutiveDays - a.consecutiveDays);
  
  // Profitability by day
  for (let day = 0; day <= 5; day++) {
    const dayTrades = trades.filter(t => 
      t.maxFavorable[day] !== null && t.maxFavorable[day] !== undefined
    );
    
    const profitable = dayTrades.filter(t => parseFloat(t.maxFavorable[day]) > 0).length;
    const avgProfit = dayTrades.reduce((sum, t) => sum + (parseFloat(t.maxFavorable[day]) || 0), 0) / dayTrades.length;
    
    analysis.profitabilityByDay[`Day${day}`] = {
      totalTrades: dayTrades.length,
      profitableCount: profitable,
      profitableRate: (profitable / dayTrades.length * 100).toFixed(2) + '%',
      avgProfit: avgProfit.toFixed(2) + '%'
    };
  }
  
  return analysis;
}

/**
 * Analyze indicator effectiveness
 */
function EW_analyzeIndicatorEffectiveness(trades) {
  const indicators = ['rsi', 'sma20', 'sma50', 'ema9', 'ema21', 'vwap', 'rvol', 'atr', 'priceVsSMA20', 'priceVsVWAP'];
  const analysis = {};
  
  indicators.forEach(indicator => {
    const profitableRanges = EW_findProfitableIndicatorRanges(trades, indicator);
    const correlation = EW_calculateIndicatorCorrelation(trades, indicator);
    
    analysis[indicator] = {
      profitableRanges: profitableRanges,
      correlationWithProfit: correlation,
      significance: Math.abs(correlation) > 0.3 ? 'HIGH' : (Math.abs(correlation) > 0.15 ? 'MEDIUM' : 'LOW')
    };
  });
  
  return analysis;
}

/**
 * Find profitable ranges for an indicator
 */
function EW_findProfitableIndicatorRanges(trades, indicatorName) {
  const ranges = {
    bullish: { min: null, max: null, count: 0, avgProfit: 0 },
    bearish: { min: null, max: null, count: 0, avgProfit: 0 }
  };
  
  const profitableTrades = trades.filter(t => 
    t.wasHit && t.maxFavorableValue > t.maxUnfavorableValue
  );
  
  profitableTrades.forEach(trade => {
    const indicatorValues = trade.indicators[indicatorName];
    if (!indicatorValues || indicatorValues.length === 0) return;
    
    // Get value at hit time (first non-null value)
    const hitValue = indicatorValues.find(v => v !== null);
    if (!hitValue) return;
    
    const value = parseFloat(hitValue);
    const isBullish = trade.strategy.toUpperCase().includes('BULL') || 
                      trade.strategy.toUpperCase().includes('LONG CALL');
    
    const range = isBullish ? ranges.bullish : ranges.bearish;
    
    if (range.min === null || value < range.min) range.min = value;
    if (range.max === null || value > range.max) range.max = value;
    range.count++;
    range.avgProfit += trade.maxFavorableValue;
  });
  
  // Calculate averages
  if (ranges.bullish.count > 0) {
    ranges.bullish.avgProfit = (ranges.bullish.avgProfit / ranges.bullish.count).toFixed(2);
  }
  if (ranges.bearish.count > 0) {
    ranges.bearish.avgProfit = (ranges.bearish.avgProfit / ranges.bearish.count).toFixed(2);
  }
  
  return ranges;
}

/**
 * Calculate correlation between indicator and profitability
 */
function EW_calculateIndicatorCorrelation(trades, indicatorName) {
  const pairs = [];
  
  trades.forEach(trade => {
    const indicatorValues = trade.indicators[indicatorName];
    if (!indicatorValues || indicatorValues.length === 0) return;
    
    const firstValue = indicatorValues.find(v => v !== null);
    if (!firstValue) return;
    
    pairs.push({
      indicator: parseFloat(firstValue),
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
  
  return isNaN(correlation) ? 0 : correlation.toFixed(3);
}

/**
 * Analyze earnings timing patterns
 */
function EW_analyzeEarningsTiming(trades) {
  const analysis = {
    preEarningsHits: [],
    postEarningsHits: [],
    earningsImpact: {},
    optimalEntryTiming: {}
  };
  
  trades.forEach(trade => {
    if (!trade.nextEPSDate || !trade.firstHitDate) return;
    
    const epsDate = new Date(trade.nextEPSDate);
    const hitDate = new Date(trade.firstHitDate);
    const runDate = new Date(trade.runDate);
    
    const daysToEarnings = Math.floor((epsDate - runDate) / (1000 * 60 * 60 * 24));
    const hitBeforeEarnings = hitDate < epsDate;
    
    const tradeInfo = {
      ticker: trade.ticker,
      strategy: trade.strategy,
      daysToEarnings: daysToEarnings,
      daysToHit: trade.daysToHit,
      maxProfit: trade.maxFavorableValue,
      hitBeforeEarnings: hitBeforeEarnings
    };
    
    if (hitBeforeEarnings) {
      analysis.preEarningsHits.push(tradeInfo);
    } else {
      analysis.postEarningsHits.push(tradeInfo);
    }
  });
  
  // Analyze patterns
  const preEarningsAvgDays = analysis.preEarningsHits.length > 0 ?
    analysis.preEarningsHits.reduce((sum, t) => sum + t.daysToHit, 0) / analysis.preEarningsHits.length : 0;
  
  const postEarningsAvgDays = analysis.postEarningsHits.length > 0 ?
    analysis.postEarningsHits.reduce((sum, t) => sum + t.daysToHit, 0) / analysis.postEarningsHits.length : 0;
  
  analysis.earningsImpact = {
    preEarningsHitRate: (analysis.preEarningsHits.length / (analysis.preEarningsHits.length + analysis.postEarningsHits.length) * 100).toFixed(2) + '%',
    avgDaysToHitPreEarnings: preEarningsAvgDays.toFixed(1),
    avgDaysToHitPostEarnings: postEarningsAvgDays.toFixed(1),
    recommendation: preEarningsAvgDays < postEarningsAvgDays ? 
      'Enter positions 3-5 days before earnings for faster hits' : 
      'Consider post-earnings entries for more predictable outcomes'
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
      hitRate: (hitRate * 100).toFixed(2) + '%',
      avgMaxProfit: avgProfit.toFixed(2) + '%',
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
        avgProfit: (dayProfits.reduce((sum, p) => sum + p, 0) / dayProfits.length).toFixed(2) + '%',
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
    if (netProfit > 5) { // Over 5% profit
      stats.bestPerformers.push({
        ticker: trade.ticker,
        profit: netProfit.toFixed(2) + '%',
        daysHeld: trade.profitableDays
      });
    }
  });
  
  // Calculate final stats
  Object.entries(strategies).forEach(([strategy, stats]) => {
    stats.hitRate = (stats.hitTrades / stats.totalTrades * 100).toFixed(2) + '%';
    stats.avgProfit = (stats.totalProfit / stats.totalTrades).toFixed(2) + '%';
    stats.avgLoss = (stats.totalLoss / stats.totalTrades).toFixed(2) + '%';
    stats.profitFactor = stats.totalLoss > 0 ? (stats.totalProfit / stats.totalLoss).toFixed(2) : 'N/A';
    stats.avgDaysToHit = stats.hitTrades > 0 ? (stats.avgDaysToHit / stats.hitTrades).toFixed(1) : 'N/A';
    
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
  // Filter for successful trades
  const successfulTrades = trades.filter(t => 
    t.wasHit && t.maxFavorableValue > 5 // Over 5% profit
  );
  
  // Sort by profitability
  successfulTrades.sort((a, b) => b.maxFavorableValue - a.maxFavorableValue);
  
  // Get top 20
  const topPlays = successfulTrades.slice(0, 20).map(trade => {
    // Find common patterns in indicators
    const indicatorSnapshot = {};
    Object.entries(trade.indicators).forEach(([name, values]) => {
      if (values && values.length > 0) {
        const firstValue = values.find(v => v !== null);
        if (firstValue) indicatorSnapshot[name] = parseFloat(firstValue).toFixed(2);
      }
    });
    
    return {
      ticker: trade.ticker,
      strategy: trade.strategy,
      entryDate: trade.runDate,
      strike: trade.strike || trade.longStrike,
      maxProfit: trade.maxFavorableValue.toFixed(2) + '%',
      daysToHit: trade.daysToHit || 'N/A',
      profitableDays: trade.profitableDays,
      riskReward: trade.riskReward.toFixed(2),
      indicators: indicatorSnapshot,
      multiDayProfile: trade.maxFavorable.map((v, i) => 
        v !== null ? `D${i}:${parseFloat(v).toFixed(1)}%` : null
      ).filter(v => v !== null).join(', ')
    };
  });
  
  return topPlays;
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
  
  Object.entries(insights.overview).forEach(([key, value]) => {
    reportSheet.getRange(currentRow, 1).setValue(key.replace(/([A-Z])/g, ' $1').trim());
    reportSheet.getRange(currentRow, 2).setValue(value);
    currentRow++;
  });
  currentRow += 2;
  
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
      reportSheet.getRange(currentRow, 1, 1, 6).setValues([[
        trade.ticker, trade.strategy, trade.consecutiveDays,
        `Day ${trade.peakDay}`, trade.peakValue, trade.strike
      ]]);
      currentRow++;
    });
  }
  currentRow += 2;
  
  // Profitability by Day
  reportSheet.getRange(currentRow, 1).setValue('Profitability by Holding Period').setFontWeight('bold');
  currentRow++;
  
  const dayHeaders = ['Day', 'Total Trades', 'Profitable', 'Success Rate', 'Avg Profit'];
  reportSheet.getRange(currentRow, 1, 1, dayHeaders.length).setValues([dayHeaders]).setFontWeight('bold');
  currentRow++;
  
  Object.entries(insights.multiDayProfitability.profitabilityByDay).forEach(([day, stats]) => {
    reportSheet.getRange(currentRow, 1, 1, 5).setValues([[
      day, stats.totalTrades, stats.profitableCount, stats.profitableRate, stats.avgProfit
    ]]);
    currentRow++;
  });
  currentRow += 2;
  
  // Indicator Effectiveness Section
  reportSheet.getRange(currentRow, 1).setValue('INDICATOR EFFECTIVENESS ANALYSIS').setFontSize(14).setFontWeight('bold');
  currentRow++;
  
  const significantIndicators = Object.entries(insights.indicatorEffectiveness)
    .filter(([name, data]) => data.significance === 'HIGH')
    .sort((a, b) => Math.abs(b[1].correlationWithProfit) - Math.abs(a[1].correlationWithProfit));
  
  if (significantIndicators.length > 0) {
    reportSheet.getRange(currentRow, 1).setValue('High-Impact Indicators').setFontWeight('bold');
    currentRow++;
    
    significantIndicators.forEach(([name, data]) => {
      reportSheet.getRange(currentRow, 1).setValue(name.toUpperCase());
      reportSheet.getRange(currentRow, 2).setValue(`Correlation: ${data.correlationWithProfit}`);
      reportSheet.getRange(currentRow, 3).setValue(`Significance: ${data.significance}`);
      currentRow++;
      
      if (data.profitableRanges.bullish.count > 0) {
        reportSheet.getRange(currentRow, 2).setValue(
          `Bullish Range: ${data.profitableRanges.bullish.min?.toFixed(2)}-${data.profitableRanges.bullish.max?.toFixed(2)} ` +
          `(${data.profitableRanges.bullish.count} trades, avg ${data.profitableRanges.bullish.avgProfit}% profit)`
        );
        currentRow++;
      }
    });
  }
  currentRow += 2;
  
  // Earnings Timing Analysis
  reportSheet.getRange(currentRow, 1).setValue('EARNINGS TIMING ANALYSIS').setFontSize(14).setFontWeight('bold');
  currentRow++;
  
  Object.entries(insights.earningsTiming.earningsImpact).forEach(([key, value]) => {
    reportSheet.getRange(currentRow, 1).setValue(key.replace(/([A-Z])/g, ' $1').trim());
    reportSheet.getRange(currentRow, 2).setValue(value);
    currentRow++;
  });
  currentRow += 2;
  
  // Strategy Performance
  reportSheet.getRange(currentRow, 1).setValue('STRATEGY PERFORMANCE BREAKDOWN').setFontSize(14).setFontWeight('bold');
  currentRow++;
  
  const stratHeaders = ['Strategy', 'Total', 'Hit Rate', 'Avg Profit', 'Avg Loss', 'Profit Factor', 'Avg Days to Hit'];
  reportSheet.getRange(currentRow, 1, 1, stratHeaders.length).setValues([stratHeaders]).setFontWeight('bold');
  currentRow++;
  
  Object.entries(insights.strategyPerformance).forEach(([strategy, stats]) => {
    reportSheet.getRange(currentRow, 1, 1, 7).setValues([[
      strategy, stats.totalTrades, stats.hitRate, stats.avgProfit,
      stats.avgLoss, stats.profitFactor, stats.avgDaysToHit
    ]]);
    currentRow++;
  });
  currentRow += 2;
  
  // Top Plays
  reportSheet.getRange(currentRow, 1).setValue('TOP 20 WINNING PLAYS').setFontSize(14).setFontWeight('bold');
  currentRow++;
  
  const topHeaders = ['Ticker', 'Strategy', 'Entry Date', 'Strike', 'Max Profit', 'Days to Hit', 'Risk/Reward', 'Multi-Day Profile'];
  reportSheet.getRange(currentRow, 1, 1, topHeaders.length).setValues([topHeaders]).setFontWeight('bold');
  currentRow++;
  
  insights.topPlays.forEach(play => {
    reportSheet.getRange(currentRow, 1, 1, 8).setValues([[
      play.ticker, play.strategy, play.entryDate, play.strike,
      play.maxProfit, play.daysToHit, play.riskReward, play.multiDayProfile
    ]]);
    currentRow++;
  });
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
  const profitRanges = reportSheet.getDataRange();
  const rule = SpreadsheetApp.newConditionalFormatRule()
    .whenTextContains('%')
    .setGradientMinpoint('#FF0000', SpreadsheetApp.InterpolationType.NUMBER, '-5')
    .setGradientMidpoint('#FFFFFF', SpreadsheetApp.InterpolationType.NUMBER, '0')
    .setGradientMaxpoint('#00FF00', SpreadsheetApp.InterpolationType.NUMBER, '5')
    .setRanges([profitRanges])
    .build();
  
  const rules = reportSheet.getConditionalFormatRules();
  rules.push(rule);
  reportSheet.setConditionalFormatRules(rules);
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
  
  SpreadsheetApp.getUi().alert(
    'ML Data Exported',
    `Exported ${mlData.data.length} trades to "ML_Export" sheet.\n\n` +
    `Features: ${mlData.features.length}\n` +
    `Ready for analysis in Python, R, or your preferred ML platform.`,
    SpreadsheetApp.getUi().ButtonSet.OK
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
  const headers = ['Rank', 'Ticker', 'Strategy', 'Entry Date', 'Strike', 'Max Profit', 
                   'Days to Hit', 'Profitable Days', 'Risk/Reward', 'Multi-Day Profile'];
  sheet.getRange(3, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
  
  // Data
  topPlays.forEach((play, idx) => {
    sheet.getRange(idx + 4, 1, 1, 10).setValues([[
      idx + 1, play.ticker, play.strategy, play.entryDate, play.strike,
      play.maxProfit, play.daysToHit, play.profitableDays, play.riskReward,
      play.multiDayProfile
    ]]);
  });
  
  // Add key indicators for top plays
  sheet.getRange(25, 1).setValue('KEY INDICATORS AT ENTRY').setFontWeight('bold');
  
  let indicatorRow = 26;
  topPlays.slice(0, 5).forEach(play => {
    sheet.getRange(indicatorRow, 1).setValue(`${play.ticker} (${play.maxProfit}):`);
    let indicatorStr = Object.entries(play.indicators)
      .map(([key, value]) => `${key}: ${value}`)
      .join(', ');
    sheet.getRange(indicatorRow, 2).setValue(indicatorStr);
    indicatorRow++;
  });
  
  sheet.autoResizeColumns(1, 10);
  SpreadsheetApp.setActiveSheet(sheet);
  
  SpreadsheetApp.getUi().alert(
    'Top Plays Report Generated',
    `Found ${topPlays.length} winning plays with >5% profit.\n\nCheck the "Top_Winning_Plays" sheet.`,
    SpreadsheetApp.getUi().ButtonSet.OK
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
      `Day ${trade.peakDay}`, trade.peakValue, trade.strike
    ]]);
  });
  
  // Day-by-day profitability
  const dayRow = Math.max(25, analysis.sustainedProfitability.length + 7);
  sheet.getRange(dayRow, 1).setValue('Profitability by Holding Period').setFontWeight('bold');
  
  const dayHeaders = ['Day', 'Total Trades', 'Profitable', 'Success Rate', 'Avg Profit'];
  sheet.getRange(dayRow + 1, 1, 1, dayHeaders.length).setValues([dayHeaders]).setFontWeight('bold');
  
  Object.entries(analysis.profitabilityByDay).forEach(([day, stats], idx) => {
    sheet.getRange(dayRow + 2 + idx, 1, 1, 5).setValues([[
      day, stats.totalTrades, stats.profitableCount, stats.profitableRate, stats.avgProfit
    ]]);
  });
  
  sheet.autoResizeColumns(1, 6);
  SpreadsheetApp.setActiveSheet(sheet);
  
  SpreadsheetApp.getUi().alert(
    'Multi-Day Analysis Complete',
    `Found ${analysis.sustainedProfitability.length} trades with sustained profitability.\n\n` +
    `Check the "Multi_Day_Analysis" sheet.`,
    SpreadsheetApp.getUi().ButtonSet.OK
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
  
  // High impact indicators
  sheet.getRange(3, 1).setValue('High-Impact Indicators (Correlation > 0.3)').setFontWeight('bold');
  
  let row = 4;
  const headers = ['Indicator', 'Correlation', 'Significance', 'Bullish Range', 'Bearish Range'];
  sheet.getRange(row, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
  row++;
  
  Object.entries(analysis)
    .filter(([name, data]) => data.significance === 'HIGH')
    .sort((a, b) => Math.abs(b[1].correlationWithProfit) - Math.abs(a[1].correlationWithProfit))
    .forEach(([name, data]) => {
      const bullishRange = data.profitableRanges.bullish.count > 0 ?
        `${data.profitableRanges.bullish.min?.toFixed(2)}-${data.profitableRanges.bullish.max?.toFixed(2)} (${data.profitableRanges.bullish.avgProfit}%)` : 'N/A';
      const bearishRange = data.profitableRanges.bearish.count > 0 ?
        `${data.profitableRanges.bearish.min?.toFixed(2)}-${data.profitableRanges.bearish.max?.toFixed(2)} (${data.profitableRanges.bearish.avgProfit}%)` : 'N/A';
      
      sheet.getRange(row, 1, 1, 5).setValues([[
        name.toUpperCase(), data.correlationWithProfit, data.significance,
        bullishRange, bearishRange
      ]]);
      row++;
    });
  
  // Medium impact indicators
  row += 2;
  sheet.getRange(row, 1).setValue('Medium-Impact Indicators (0.15 < Correlation < 0.3)').setFontWeight('bold');
  row++;
  
  Object.entries(analysis)
    .filter(([name, data]) => data.significance === 'MEDIUM')
    .forEach(([name, data]) => {
      sheet.getRange(row, 1).setValue(name.toUpperCase());
      sheet.getRange(row, 2).setValue(data.correlationWithProfit);
      sheet.getRange(row, 3).setValue(data.significance);
      row++;
    });
  
  sheet.autoResizeColumns(1, 5);
  SpreadsheetApp.setActiveSheet(sheet);
  
  const highImpact = Object.values(analysis).filter(d => d.significance === 'HIGH').length;
  
  SpreadsheetApp.getUi().alert(
    'Indicator Analysis Complete',
    `Found ${highImpact} high-impact indicators with strong correlation to profitability.\n\n` +
    `Check the "Indicator_Analysis" sheet.`,
    SpreadsheetApp.getUi().ButtonSet.OK
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
        trade.daysToHit, trade.maxProfit.toFixed(2) + '%'
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
        trade.daysToHit, trade.maxProfit.toFixed(2) + '%'
      ]]);
      row++;
    });
  
  sheet.autoResizeColumns(1, 5);
  SpreadsheetApp.setActiveSheet(sheet);
  
  SpreadsheetApp.getUi().alert(
    'Earnings Timing Analysis Complete',
    `Analyzed ${analysis.preEarningsHits.length + analysis.postEarningsHits.length} trades with earnings data.\n\n` +
    `${analysis.earningsImpact.recommendation}\n\n` +
    `Check the "Earnings_Timing" sheet.`,
    SpreadsheetApp.getUi().ButtonSet.OK
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
  
  SpreadsheetApp.getUi().alert(
    'Strategy Performance Analysis Complete',
    `Best performing strategy: ${bestStrategy[0]} with profit factor ${bestStrategy[1].profitFactor}\n\n` +
    `Check the "Strategy_Performance" sheet.`,
    SpreadsheetApp.getUi().ButtonSet.OK
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