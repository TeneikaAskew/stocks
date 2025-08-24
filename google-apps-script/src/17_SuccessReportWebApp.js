/**
 * Success Report Web App - Complete Dashboard
 * Serves HTML interface and handles data requests
 */

/**
 * Main entry point for GET requests
 */
function doGet(e) {
  const params = e.parameter;
  const action = params.action || 'dashboard';
  
  if (action === 'dashboard') {
    // Serve the HTML dashboard
    return HtmlService.createTemplateFromFile('SuccessReportDashboard')
      .evaluate()
      .setTitle('Trading Success Report Dashboard')
      .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
      .addMetaTag('viewport', 'width=device-width, initial-scale=1');
  } else {
    // Handle data requests
    return handleDataRequest(params);
  }
}

/**
 * Handle data API requests
 */
function handleDataRequest(params) {
  try {
    let result;
    
    switch(params.action) {
      case 'getData':
        result = getSuccessReportDataForWeb();
        break;
      case 'refreshData':
        result = refreshAndGetData();
        break;
      default:
        result = { error: 'Unknown action' };
    }
    
    return ContentService
      .createTextOutput(JSON.stringify(result))
      .setMimeType(ContentService.MimeType.JSON);
      
  } catch (error) {
    console.error('Data request error:', error);
    return ContentService
      .createTextOutput(JSON.stringify({ 
        error: error.toString()
      }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * Get success report data formatted for web display
 */
function getSuccessReportDataForWeb() {
  const ss = SpreadsheetApp.getActive();
  const reportSheet = ss.getSheetByName('Success_Report');
  
  // If no report exists, generate it
  if (!reportSheet) {
    console.log('No Success_Report sheet found, generating...');
    EW_generateSuccessReport();
    return getSuccessReportDataForWeb(); // Recursive call
  }
  
  // Try to get from stored properties first
  const scriptProperties = PropertiesService.getScriptProperties();
  const storedData = scriptProperties.getProperty('SUCCESS_REPORT_DATA');
  
  if (storedData) {
    try {
      const data = JSON.parse(storedData);
      data.lastUpdated = scriptProperties.getProperty('SUCCESS_REPORT_TIMESTAMP') || new Date().toISOString();
      return data;
    } catch (e) {
      console.error('Error parsing stored data:', e);
    }
  }
  
  // If no stored data, collect it fresh
  console.log('No stored data found, collecting fresh data...');
  return collectFreshReportData();
}

/**
 * Refresh data and return it
 */
function refreshAndGetData() {
  try {
    EW_generateSuccessReport();
    return {
      success: true,
      data: getSuccessReportDataForWeb(),
      message: 'Report refreshed successfully'
    };
  } catch (error) {
    return {
      success: false,
      error: error.toString()
    };
  }
}

/**
 * Collect fresh report data from sheets
 */
function collectFreshReportData() {
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  const allTrades = [];
  
  // Collect all trades
  for (const strategy of strategies) {
    const sheet = ss.getSheetByName(strategy);
    if (!sheet || sheet.getLastRow() < 2) continue;
    
    const trades = EW_extractTradeData(sheet, strategy);
    allTrades.push(...trades);
  }
  
  console.log(`Collected ${allTrades.length} trades for web display`);
  
  if (allTrades.length === 0) {
    return {
      overview: {
        totalTrades: 0,
        totalHits: 0,
        profitableTrades: 0,
        multiDayWinners: 0,
        hitRate: 0,
        profitableRate: 0,
        avgRiskReward: 0,
        avgDaysToHit: 0
      },
      multiDayProfitability: {
        profitabilityByDay: [],
        sustainedWinners: []
      },
      indicatorEffectiveness: [],
      earningsTiming: {
        preEarnings: { hitRate: 0, avgProfit: 0, tradeCount: 0 },
        postEarnings: { hitRate: 0, avgProfit: 0, tradeCount: 0 },
        optimalDaysBeforeEarnings: 3,
        recommendation: 'Need more data for analysis'
      },
      strategyPerformance: [],
      topPlays: [],
      lastUpdated: new Date().toISOString()
    };
  }
  
  // Perform analyses
  const insights = {
    overview: EW_analyzeOverview(allTrades),
    multiDayProfitability: EW_analyzeMultiDayProfitability(allTrades),
    indicatorEffectiveness: EW_analyzeIndicatorEffectiveness(allTrades),
    earningsTiming: EW_analyzeEarningsTiming(allTrades),
    strategyPerformance: EW_analyzeStrategyPerformance(allTrades),
    topPlays: EW_identifyTopPlays(allTrades)
  };
  
  // Format for web
  const webData = {
    overview: {
      totalTrades: insights.overview.totalTrades || 0,
      totalHits: insights.overview.strikeHits || 0,
      profitableTrades: insights.overview.profitableTrades || 0,
      multiDayWinners: countMultiDayWinners(allTrades),
      hitRate: insights.overview.hitRate || 0,
      profitableRate: insights.overview.profitableRate || 0,
      avgRiskReward: calculateAvgRiskReward(allTrades),
      avgDaysToHit: insights.overview.avgDaysToHit || 0
    },
    multiDayProfitability: formatMultiDayForWeb(insights.multiDayProfitability, allTrades),
    indicatorEffectiveness: formatIndicatorsForWeb(insights.indicatorEffectiveness),
    earningsTiming: formatEarningsForWeb(insights.earningsTiming),
    strategyPerformance: formatStrategiesForWeb(insights.strategyPerformance),
    topPlays: formatTopPlaysForWeb(insights.topPlays),
    lastUpdated: new Date().toISOString()
  };
  
  // Store for next time
  const scriptProperties = PropertiesService.getScriptProperties();
  scriptProperties.setProperty('SUCCESS_REPORT_DATA', JSON.stringify(webData));
  scriptProperties.setProperty('SUCCESS_REPORT_TIMESTAMP', webData.lastUpdated);
  
  return webData;
}

/**
 * Helper functions for data formatting
 */
function countMultiDayWinners(trades) {
  return trades.filter(trade => {
    const profitDays = trade.profitDays || [];
    return profitDays.filter(day => day > 0).length >= 3;
  }).length;
}

function calculateAvgRiskReward(trades) {
  const validTrades = trades.filter(t => t.risk && t.reward);
  if (validTrades.length === 0) return 0;
  
  const totalRR = validTrades.reduce((sum, t) => sum + (t.reward / t.risk), 0);
  return totalRR / validTrades.length;
}

function formatMultiDayForWeb(multiDay, trades) {
  // Create profitability by day data
  const profitabilityByDay = [];
  for (let day = 0; day <= 5; day++) {
    const tradesWithDay = trades.filter(t => t.profitDays && t.profitDays[day] !== undefined);
    const profitableCount = tradesWithDay.filter(t => t.profitDays[day] > 0).length;
    
    profitabilityByDay.push({
      day: day,
      rate: tradesWithDay.length > 0 ? profitableCount / tradesWithDay.length : 0,
      count: tradesWithDay.length
    });
  }
  
  // Create sustained winners data
  const sustainedWinners = [];
  for (let days = 1; days <= 4; days++) {
    const sustained = trades.filter(trade => {
      if (!trade.profitDays) return false;
      const consecutiveDays = trade.profitDays.slice(0, days).filter(p => p > 0).length;
      return consecutiveDays === days;
    });
    
    if (sustained.length > 0) {
      const avgProfit = sustained.reduce((sum, t) => sum + (t.maxProfit || 0), 0) / sustained.length;
      sustainedWinners.push({
        days: days,
        count: sustained.length,
        successRate: sustained.filter(t => t.strikeHit).length / sustained.length,
        avgProfit: avgProfit
      });
    }
  }
  
  return { profitabilityByDay, sustainedWinners };
}

function formatIndicatorsForWeb(indicators) {
  if (!indicators) return [];
  
  return Object.entries(indicators).map(([name, data]) => ({
    name: name,
    correlation: data.correlation || 0,
    significance: data.significance || 'LOW',
    profitableRange: data.profitableRange || 'N/A',
    hitRate: data.hitRate || 0,
    avgProfit: data.avgProfit || 0
  })).sort((a, b) => Math.abs(b.correlation) - Math.abs(a.correlation));
}

function formatEarningsForWeb(earnings) {
  if (!earnings) {
    return {
      preEarnings: { hitRate: 0, avgProfit: 0, tradeCount: 0 },
      postEarnings: { hitRate: 0, avgProfit: 0, tradeCount: 0 },
      optimalDaysBeforeEarnings: 3,
      recommendation: 'Need more data for analysis'
    };
  }
  
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

function formatStrategiesForWeb(strategies) {
  if (!strategies) return [];
  
  return Object.entries(strategies).map(([strategy, data]) => ({
    strategy: strategy,
    tradeCount: data.count || 0,
    hitRate: data.hitRate || 0,
    profitFactor: data.profitFactor || 1,
    avgDaysToHit: data.avgDaysToHit || 0
  })).sort((a, b) => b.hitRate - a.hitRate);
}

function formatTopPlaysForWeb(topPlays) {
  if (!topPlays || !Array.isArray(topPlays)) return [];
  
  return topPlays.slice(0, 20).map(play => ({
    symbol: play.symbol || 'N/A',
    entryDate: play.entryDate || new Date().toISOString(),
    strategy: play.strategy || 'N/A',
    maxProfit: play.maxProfit || 0,
    daysToHit: play.daysToHit || 0,
    rsi: play.rsi || null,
    priceVsSMA20: play.priceVsSMA20 || null,
    rvol: play.rvol || null
  }));
}

/**
 * Include function for CSS and JS in HTML template
 */
function include(filename) {
  return HtmlService.createHtmlOutputFromFile(filename).getContent();
}