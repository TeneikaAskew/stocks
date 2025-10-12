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
    overview: {
      totalTrades: insights.overview.totalTrades,
      totalHits: insights.overview.strikeHits,
      profitableTrades: insights.overview.profitableTrades,
      multiDayWinners: insights.multiDayProfitability.totalSustainedWinners || 0,
      hitRate: insights.overview.hitRate,
      profitableRate: insights.overview.profitableRate,
      avgRiskReward: insights.riskRewardPatterns.avgRiskReward || 2.0,
      avgDaysToHit: insights.overview.avgDaysToHit
    },
    multiDayProfitability: formatMultiDayData(insights.multiDayProfitability),
    indicatorEffectiveness: formatIndicatorData(insights.indicatorEffectiveness),
    earningsTiming: formatEarningsData(insights.earningsTiming),
    strategyPerformance: formatStrategyData(insights.strategyPerformance),
    topPlays: formatTopPlays(insights.topPlays)
  };
  
  // Store as string (Properties have size limits)
  scriptProperties.setProperty('SUCCESS_REPORT_DATA', JSON.stringify(webData));
  scriptProperties.setProperty('SUCCESS_REPORT_TIMESTAMP', new Date().toISOString());
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
    avgDaysToHit: data.avgDaysToHit || 0
  }));
}

/**
 * Format top plays data for web
 */
function formatTopPlays(topPlays) {
  return (topPlays || []).slice(0, 20).map(play => {
    const rawProfit = typeof play.maxProfit === 'number'
      ? play.maxProfit
      : (typeof play.maxFavorableValue === 'number' ? play.maxFavorableValue : parseFloat(play.maxProfit) || 0);

    return {
      symbol: play.ticker || play.symbol || 'N/A',
      entryDate: play.entryDate,
      strategy: play.strategy,
      maxProfit: rawProfit * 100,
      daysToHit: play.daysToHit,
      rsi: play.rsi,
      priceVsSMA20: play.priceVsSMA20,
      rvol: play.rvol
    };
  });
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
      avgDaysToHit: 0
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
    topPlays: [],
    lastUpdated: new Date().toISOString()
  };
}