/**
 * Web App for Success Report Data Export
 * Provides API endpoints for the responsive dashboard
 */

/**
 * Handle GET requests to the web app
 * @param {Object} e - Event object with parameters
 * @return {TextOutput} JSON response
 */
function doGet(e) {
  const params = e.parameter;
  const action = params.action || 'getReport';
  
  try {
    let result;
    
    switch(action) {
      case 'getReport':
        result = getSuccessReportData();
        break;
      case 'getLatestUpdate':
        result = getLatestUpdateTime();
        break;
      case 'refreshReport':
        result = refreshSuccessReport();
        break;
      default:
        result = { error: 'Unknown action' };
    }
    
    return ContentService
      .createTextOutput(JSON.stringify(result))
      .setMimeType(ContentService.MimeType.JSON);
      
  } catch (error) {
    console.error('Web App Error:', error);
    return ContentService
      .createTextOutput(JSON.stringify({ 
        error: error.toString(),
        timestamp: new Date().toISOString()
      }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * Get the complete success report data
 * @return {Object} Success report data
 */
function getSuccessReportData() {
  const ss = SpreadsheetApp.getActive();
  const reportSheet = ss.getSheetByName('Success_Report');
  
  if (!reportSheet) {
    // Generate report if it doesn't exist
    EW_generateSuccessReport();
    return getSuccessReportData(); // Recursive call after generation
  }
  
  // Get stored report data
  const scriptProperties = PropertiesService.getScriptProperties();
  const storedData = scriptProperties.getProperty('SUCCESS_REPORT_DATA');
  
  if (storedData) {
    const data = JSON.parse(storedData);
    data.lastUpdated = scriptProperties.getProperty('SUCCESS_REPORT_TIMESTAMP') || new Date().toISOString();
    return data;
  }
  
  // If no stored data, generate from sheet
  return extractReportDataFromSheet(reportSheet);
}

/**
 * Get the last update timestamp
 * @return {Object} Timestamp info
 */
function getLatestUpdateTime() {
  const scriptProperties = PropertiesService.getScriptProperties();
  const timestamp = scriptProperties.getProperty('SUCCESS_REPORT_TIMESTAMP');
  
  return {
    lastUpdated: timestamp || null,
    nextUpdate: calculateNextUpdateTime()
  };
}

/**
 * Manually refresh the success report
 * @return {Object} Status of refresh operation
 */
function refreshSuccessReport() {
  try {
    EW_generateSuccessReport();
    return {
      success: true,
      message: 'Report refreshed successfully',
      timestamp: new Date().toISOString()
    };
  } catch (error) {
    return {
      success: false,
      error: error.toString(),
      timestamp: new Date().toISOString()
    };
  }
}

/**
 * Store success report data for web access
 * Called from EW_generateSuccessReport
 * @param {Object} insights - The insights object from report generation
 */
function storeSuccessReportData(insights) {
  const scriptProperties = PropertiesService.getScriptProperties();

  // Format data for web consumption
  const webData = {
    overview: formatOverviewData(insights.overview, insights.allTrades || []),
    dataQuality: formatDataQualityForWeb(insights.dataQuality),
    holdingPeriod: formatHoldingPeriodForWeb(insights.holdingPeriod),
    multiDayProfitability: formatMultiDayData(insights.multiDayProfitability),
    indicatorEffectiveness: formatIndicatorData(insights.indicatorEffectiveness),
    earningsTiming: formatEarningsData(insights.earningsTiming),
    strategyPerformance: formatStrategyData(insights.strategyPerformance),
    riskManagement: formatRiskManagementForWeb(insights.riskRewardPatterns, insights.strategyPerformance),
    topPlays: formatTopPlays(insights.topPlays),
    incompleteTrades: formatIncompleteTradesForWeb(insights.allTrades || []),
    tradeRecords: formatTradeRecordsForWeb(insights.allTrades || [])
  };

  // Backwards compatibility for existing clients expecting riskReward key
  if (!webData.riskReward) {
    webData.riskReward = webData.riskManagement.riskReward;
  }

  // Store as string (Properties have size limits)
  scriptProperties.setProperty('SUCCESS_REPORT_DATA', JSON.stringify(webData));
  scriptProperties.setProperty('SUCCESS_REPORT_TIMESTAMP', new Date().toISOString());
}

function toIsoString(dateValue) {
  if (!dateValue) return '';
  let date = dateValue instanceof Date ? dateValue : new Date(dateValue);
  if (!(date instanceof Date) || isNaN(date.getTime())) {
    return '';
  }
  return Utilities.formatDate(date, Session.getScriptTimeZone(), "yyyy-MM-dd'T'HH:mm:ssXXX");
}

function sanitizePercentageValue(value, strikePrice) {
  if (value === null || value === undefined || value === '') return null;
  let num = parseFloat(value);
  if (isNaN(num)) return null;

  if (strikePrice && Math.abs(num) > 10 && Math.abs(num) < strikePrice * 3) {
    num = num / strikePrice;
  }

  return num;
}

function calculateDaysBetween(startDate, endDate) {
  if (!startDate || !endDate) return null;
  const start = startDate instanceof Date ? startDate : new Date(startDate);
  const end = endDate instanceof Date ? endDate : new Date(endDate);
  if (isNaN(start.getTime()) || isNaN(end.getTime())) return null;
  const diffMs = end.getTime() - start.getTime();
  return Math.round(diffMs / (1000 * 60 * 60 * 24));
}

function formatTradeRecordsForWeb(trades) {
  if (!Array.isArray(trades)) return [];

  return trades.map(trade => {
    const strikePrice = trade.longStrike || trade.strike || 0;
    const favorable = Array.isArray(trade.maxFavorable)
      ? trade.maxFavorable.map(value => sanitizePercentageValue(value, strikePrice))
      : [];
    const unfavorable = Array.isArray(trade.minUnfavorable)
      ? trade.minUnfavorable.map(value => sanitizePercentageValue(value, strikePrice))
      : [];

    const peakProfit = typeof trade.maxFavorableValue === 'number'
      ? trade.maxFavorableValue
      : Math.max(...favorable.filter(value => value !== null), 0);

    const maxDrawdown = typeof trade.maxUnfavorableValue === 'number'
      ? trade.maxUnfavorableValue
      : Math.min(...unfavorable.filter(value => value !== null), 0);

    const runDateIso = toIsoString(trade.runDate);
    const daysBeforeEarnings = calculateDaysBetween(trade.runDate, trade.nextEPSDate);

    const profitableDays = Array.isArray(trade.maxFavorable)
      ? trade.maxFavorable.filter(value => sanitizePercentageValue(value, strikePrice) > 0).length
      : (trade.profitableDays || 0);

    return {
      strategy: trade.strategy || '',
      ticker: trade.ticker || '',
      runDate: runDateIso,
      expDate: toIsoString(trade.expDate) || '',
      strike: trade.strike || null,
      longStrike: trade.longStrike || null,
      strikeHit: Boolean(trade.wasHit),
      daysToHit: typeof trade.daysToHit === 'number' ? trade.daysToHit : null,
      peakProfit: peakProfit || 0,
      maxDrawdown: maxDrawdown || 0,
      profitableDays: profitableDays || 0,
      daysBeforeEarnings: daysBeforeEarnings,
      maxFavorable: favorable,
      minUnfavorable: unfavorable
    };
  });
}

/**
 * Format overview metrics for web dashboard
 */
function formatOverviewData(overview, trades) {
  if (!overview) {
    return {
      totalTrades: 0,
      totalHits: 0,
      profitableTrades: 0,
      multiDayWinners: 0,
      hitRate: 0,
      profitableRate: 0,
      avgRiskReward: 0,
      avgDaysToHit: 0,
      profitFactor: 0,
      avgProfit: 0,
      avgLoss: 0,
      bestHoldingDay: 'Day 1',
      avgPremiumEstimate: 200
    };
  }

  const totalTrades = overview.totalTrades || trades.length || 0;
  const strikeHits = overview.strikeHits || 0;
  const profitableTrades = overview.profitableTrades || 0;
  const avgDaysToHit = overview.avgDaysToHit || 0;
  const avgRiskReward = overview.avgRiskReward || 0;

  // Estimate average premium using strike or long strike values
  let premiumEstimate = 200;
  const validPremiumTrades = trades
    .map(trade => trade.longStrike || trade.strike || 0)
    .filter(strike => strike && !isNaN(strike));

  if (validPremiumTrades.length > 0) {
    const avgStrike = validPremiumTrades.reduce((sum, strike) => sum + strike, 0) / validPremiumTrades.length;
    if (avgStrike > 0) {
      premiumEstimate = Math.round(avgStrike * 0.02 * 100); // Approx 2% ATM premium * contract multiplier
    }
  }

  return {
    totalTrades: totalTrades,
    totalHits: strikeHits,
    profitableTrades: profitableTrades,
    multiDayWinners: overview.totalSustainedWinners || overview.multiDayWinners || 0,
    hitRate: overview.hitRate || 0,
    profitableRate: overview.profitableRate || 0,
    avgRiskReward: avgRiskReward,
    avgDaysToHit: avgDaysToHit,
    profitFactor: overview.profitFactor || 0,
    avgProfit: overview.avgProfit || 0,
    avgLoss: overview.avgLoss || 0,
    avgWin: overview.avgWin || overview.avgProfit || 0,
    bestHoldingDay: overview.bestHoldingDay || 'Day 1',
    totalObservations: overview.totalObservations || 0,
    avgPremiumEstimate: premiumEstimate
  };
}

/**
 * Format multi-day profitability data for web
 */
function formatMultiDayData(multiDay) {
  return {
    profitabilityByDay: multiDay.profitByDay || [],
    sustainedWinners: multiDay.sustainedWinners || []
  };
}

/**
 * Format indicator effectiveness data for web
 */
function formatIndicatorData(indicators) {
  return Object.entries(indicators || {}).map(([name, data]) => ({
    name: name,
    correlation: data.correlation || 0,
    significance: data.significance || 'LOW',
    profitableRange: data.profitableRange || 'N/A',
    hitRate: data.hitRate || 0,
    avgProfit: data.avgProfit || 0
  }));
}

/**
 * Format earnings timing data for web
 */
function formatEarningsData(earnings) {
  return {
    preEarnings: {
      hitRate: earnings.preEarnings?.hitRate || 0,
      avgProfit: earnings.preEarnings?.avgProfit || 0,
      tradeCount: earnings.preEarnings?.count || 0
    },
    postEarnings: {
      hitRate: earnings.postEarnings?.hitRate || 0,
      avgProfit: earnings.postEarnings?.avgProfit || 0,
      tradeCount: earnings.postEarnings?.count || 0
    },
    optimalDaysBeforeEarnings: earnings.optimalDays || 3,
    recommendation: earnings.recommendation || 'Analyze more data for recommendations'
  };
}

/**
 * Format strategy performance data for web
 */
function formatStrategyData(strategies) {
  return Object.entries(strategies || {}).map(([strategy, data]) => ({
    strategy: strategy,
    tradeCount: data.count || 0,
    hitRate: data.hitRate || 0,
    profitFactor: data.profitFactor || 1,
    avgDaysToHit: data.avgDaysToHit || 0,
    avgWin: data.avgProfit || 0,
    avgLoss: data.avgLoss || 0,
    totalProfit: data.totalProfit || 0,
    totalLoss: data.totalLoss || 0
  }));
}

function formatDataQualityForWeb(dataQuality) {
  if (!dataQuality) {
    return {
      overallScore: 0,
      fieldCompleteness: [],
      recommendations: []
    };
  }

  const fieldCompleteness = Object.entries(dataQuality.dataCompleteness || {}).map(([field, value]) => ({
    field: field,
    completeness: parsePercentageToNumber(value)
  }));

  return {
    overallScore: parsePercentageToNumber(dataQuality.overallScore),
    fieldCompleteness: fieldCompleteness,
    recommendations: dataQuality.recommendations || []
  };
}

function formatHoldingPeriodForWeb(holdingPeriod) {
  if (!holdingPeriod) {
    return {
      optimalExit: {},
      byDay: [],
      decayAnalysis: {}
    };
  }

  const byDay = Object.entries(holdingPeriod.byDay || {}).map(([day, stats]) => ({
    day: day,
    profitableRate: stats.profitableRate || 0,
    hitRate: stats.hitRate || 0,
    avgProfit: stats.avgProfit || 0,
    avgLoss: stats.avgLoss || 0,
    profitFactor: typeof stats.profitFactor === 'string' ? parseFloat(stats.profitFactor) || 0 : stats.profitFactor || 0
  }));

  return {
    optimalExit: {
      bestDay: holdingPeriod.optimalExitTiming?.bestDay || 'Day 1',
      profitableRate: holdingPeriod.optimalExitTiming?.profitableRate || 0,
      recommendation: holdingPeriod.recommendations?.[0] || 'Maintain consistent exit reviews'
    },
    byDay: byDay,
    decayAnalysis: holdingPeriod.averageDecayRate || {}
  };
}

function formatRiskManagementForWeb(riskRewardPatterns, strategyPerformance) {
  const riskReward = formatRiskRewardForWeb(riskRewardPatterns);
  const kellySizing = calculateKellySizingForWeb(strategyPerformance);

  return {
    riskReward: riskReward,
    kellySizing: kellySizing
  };
}

function formatRiskRewardForWeb(riskRewardPatterns) {
  if (!riskRewardPatterns) {
    return {
      buckets: [],
      exitTiming: []
    };
  }

  const buckets = Object.entries(riskRewardPatterns.byRiskRewardRatio || {}).map(([range, data]) => ({
    range: range,
    count: data.count || 0,
    hitRate: data.hitRate || 0,
    avgMaxProfit: data.avgMaxProfit || 0,
    recommendation: data.recommendation || 'REVIEW'
  }));

  const exitTiming = Object.entries(riskRewardPatterns.exitTimingAnalysis || {}).map(([day, data]) => ({
    day: day,
    avgProfit: data.avgProfit || 0,
    profitableTrades: data.profitableTrades || 0,
    totalTrades: data.totalTrades || 0
  }));

  return { buckets, exitTiming };
}

function calculateKellySizingForWeb(strategyPerformance) {
  if (!strategyPerformance) return [];

  const entries = Array.isArray(strategyPerformance)
    ? strategyPerformance
    : Object.entries(strategyPerformance || {}).map(([strategy, data]) => ({ strategy, ...data }));

  return entries.map(entry => {
    const winRate = entry.hitRate || 0;
    const avgWin = Math.abs(entry.avgProfit || entry.avgWin || 0);
    const avgLoss = Math.abs(entry.avgLoss || 0);
    const payoutRatio = avgLoss > 0 ? avgWin / avgLoss : 0;
    const fullKelly = payoutRatio > 0
      ? Math.max(0, winRate - ((1 - winRate) / payoutRatio))
      : 0;

    return {
      strategy: entry.strategy || entry.name || 'Unknown',
      fullKelly: fullKelly * 100,
      halfKelly: fullKelly * 50,
      winRate: winRate * 100,
      avgWin: avgWin * 100,
      avgLoss: avgLoss * 100
    };
  }).sort((a, b) => b.fullKelly - a.fullKelly);
}

function formatIncompleteTradesForWeb(trades) {
  if (!trades || !trades.length) {
    return {
      totalCount: 0,
      byStrategy: [],
      sample: []
    };
  }

  const incomplete = trades.filter(trade => {
    const hasProfitArray = trade.maxFavorable && trade.maxFavorable.some(v => v !== null && v !== '' && !isNaN(parseFloat(v)));
    const hasStrikeData = trade.strikeHit && trade.strikeHit.some(v => v !== null && v !== '' && !isNaN(parseFloat(v)));
    return !hasProfitArray || !hasStrikeData;
  });

  const strategyCounts = incomplete.reduce((acc, trade) => {
    const key = trade.strategy || 'Unknown';
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  const byStrategy = Object.entries(strategyCounts)
    .map(([strategy, count]) => ({ strategy, count }))
    .sort((a, b) => b.count - a.count);

  const sample = incomplete.slice(0, 25).map(trade => ({
    strategy: trade.strategy,
    ticker: trade.ticker,
    runDate: trade.runDate,
    expDate: trade.expDate,
    strike: trade.strike,
    longStrike: trade.longStrike,
    missingFields: deriveMissingFields(trade)
  }));

  return {
    totalCount: incomplete.length,
    byStrategy: byStrategy,
    sample: sample
  };
}

function deriveMissingFields(trade) {
  const missing = [];
  if (!trade.maxFavorable || trade.maxFavorable.every(v => v === null || v === '' || isNaN(parseFloat(v)))) {
    missing.push('Profit by Day');
  }
  if (!trade.strikeHit || trade.strikeHit.every(v => v === null || v === '' || isNaN(parseFloat(v)))) {
    missing.push('Strike Hit');
  }
  if (!trade.dayChecks || trade.dayChecks.every(v => !v)) {
    missing.push('Day Checks');
  }
  if (!trade.entryIndicators || Object.values(trade.entryIndicators).every(v => v === null || v === '')) {
    missing.push('Entry Indicators');
  }
  return missing;
}

function parsePercentageToNumber(value) {
  if (value === null || value === undefined) return 0;
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const cleaned = value.replace('%', '').trim();
    const num = parseFloat(cleaned);
    if (isNaN(num)) return 0;
    return value.includes('%') ? num : num;
  }
  return 0;
}

/**
 * Format top plays data for web
 */
function formatTopPlays(topPlays) {
  return (topPlays || []).slice(0, 20).map(play => ({
    symbol: play.symbol,
    entryDate: play.entryDate,
    strategy: play.strategy,
    maxProfit: play.maxProfit,
    daysToHit: play.daysToHit,
    rsi: play.rsi,
    priceVsSMA20: play.priceVsSMA20,
    rvol: play.rvol
  }));
}

/**
 * Calculate next scheduled update time
 */
function calculateNextUpdateTime() {
  const now = new Date();
  const next = new Date(now);
  
  // Next update is 9 AM tomorrow
  next.setDate(next.getDate() + 1);
  next.setHours(9, 0, 0, 0);
  
  // If it's before 9 AM today, next update is today
  if (now.getHours() < 9) {
    next.setDate(now.getDate());
  }
  
  return next.toISOString();
}

/**
 * Extract report data from sheet (fallback method)
 */
function extractReportDataFromSheet(reportSheet) {
  // This is a simplified extraction - you'd need to parse the actual sheet structure
  const data = reportSheet.getDataRange().getValues();
  
  // Basic structure - would need proper parsing based on your sheet layout
  return {
    overview: {
      totalTrades: 0,
      totalHits: 0,
      profitableTrades: 0,
      multiDayWinners: 0,
      hitRate: 0,
      profitableRate: 0,
      avgRiskReward: 0,
      avgDaysToHit: 0,
      avgProfit: 0,
      avgLoss: 0,
      avgWin: 0,
      profitFactor: 0,
      avgPremiumEstimate: 200
    },
    dataQuality: {
      overallScore: 0,
      fieldCompleteness: [],
      recommendations: []
    },
    holdingPeriod: {
      optimalExit: {},
      byDay: [],
      decayAnalysis: {}
    },
    multiDayProfitability: {
      profitabilityByDay: [],
      sustainedWinners: []
    },
    indicatorEffectiveness: [],
    earningsTiming: {
      preEarnings: {},
      postEarnings: {},
      optimalDaysBeforeEarnings: 3,
      recommendation: 'Generate report for analysis'
    },
    strategyPerformance: [],
    riskManagement: {
      riskReward: { buckets: [], exitTiming: [] },
      kellySizing: []
    },
    topPlays: [],
    incompleteTrades: {
      totalCount: 0,
      byStrategy: [],
      sample: []
    },
    lastUpdated: new Date().toISOString()
  };
}