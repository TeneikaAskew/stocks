/**
 * Success Report Web App - Complete Dashboard
 * Serves HTML interface and handles data requests
 */

function parseNumber(value) {
  if (value === null || value === undefined || value === '') return 0;
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const cleaned = value.replace(/[,%]/g, '').trim();
    const num = parseFloat(cleaned);
    return isNaN(num) ? 0 : num;
  }
  return 0;
}

function parsePercentToDecimal(value) {
  if (value === null || value === undefined || value === '') return 0;
  if (typeof value === 'number') {
    // If already in range 0-1 assume decimal
    return value > 1 ? value / 100 : value;
  }
  if (typeof value === 'string') {
    const cleaned = value.replace('%', '').trim();
    const num = parseFloat(cleaned);
    if (isNaN(num)) return 0;
    return num / 100;
  }
  return 0;
}

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
      const timestamp = scriptProperties.getProperty('SUCCESS_REPORT_TIMESTAMP') || new Date().toISOString();
      const completeData = ensureSuccessReportShape(data);
      completeData.lastUpdated = timestamp;
      return completeData;
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
 * Collect fresh report data from individual analysis sheets
 */
function collectFreshReportData() {
  const ss = SpreadsheetApp.getActive();
  
  // First check if individual sheets exist, if not generate report
  const requiredSheets = ['SR_Overview', 'SR_MultiDay', 'SR_Indicators', 'SR_Earnings', 'SR_Strategies', 'SR_TopPlays'];
  const missingSheets = requiredSheets.filter(sheetName => !ss.getSheetByName(sheetName));
  
  if (missingSheets.length > 0) {
    console.log('Missing analysis sheets, generating report...');
    EW_generateSuccessReport();
  }
  
  // Now collect data from individual sheets
  const webData = {
    overview: collectOverviewData(ss),
    dataQuality: collectDataQualityData(ss),
    holdingPeriod: collectHoldingPeriodData(ss),
    multiDayProfitability: collectMultiDayData(ss),
    indicatorEffectiveness: collectIndicatorsData(ss),
    earningsTiming: collectEarningsData(ss),
    strategyPerformance: collectStrategiesData(ss),
    topPlays: collectTopPlaysData(ss),
    lastUpdated: new Date().toISOString()
  };

  const riskReward = collectRiskRewardData(ss);
  const kellySizing = calculateKellySizingFromStrategies(webData.strategyPerformance);
  webData.riskManagement = {
    riskReward: riskReward,
    kellySizing: kellySizing
  };
  webData.riskReward = riskReward; // Backwards compatibility
  webData.incompleteTrades = collectIncompleteTradesData(ss);
  webData.tradeRecords = collectTradeRecords(ss);

  // Store for next time
  const scriptProperties = PropertiesService.getScriptProperties();
  scriptProperties.setProperty('SUCCESS_REPORT_DATA', JSON.stringify(webData));
  scriptProperties.setProperty('SUCCESS_REPORT_TIMESTAMP', webData.lastUpdated);
  
  return webData;
}

/**
 * Collect overview data from SR_Overview sheet
 */
function collectOverviewData(ss) {
  const sheet = ss.getSheetByName('SR_Overview');
  if (!sheet) return {};
  
  const data = sheet.getDataRange().getValues();
  const overview = {};
  
  // Parse main metrics (rows 2-11)
  for (let i = 1; i < Math.min(11, data.length); i++) {
    const metric = data[i][0];
    const value = data[i][1];

    switch(metric) {
      case 'Total Trades':
        overview.totalTrades = value;
        break;
      case 'Total Observations':
        overview.totalObservations = value;
        break;
      case 'Hit Rate':
        overview.hitRate = parsePercentToDecimal(value);
        break;
      case 'Profitable Rate':
        overview.profitableRate = parsePercentToDecimal(value);
        break;
      case 'Profit Factor':
        overview.profitFactor = parseNumber(value);
        break;
      case 'Avg Profit':
        overview.avgProfit = parsePercentToDecimal(value);
        break;
      case 'Avg Loss':
        overview.avgLoss = parsePercentToDecimal(value);
        break;
      case 'Avg Risk/Reward':
        overview.avgRiskReward = parseNumber(value);
        break;
      case 'Avg Days to Hit':
        overview.avgDaysToHit = parseNumber(value);
        break;
      case 'Best Holding Day':
        overview.bestHoldingDay = value;
        break;
    }
  }
  
  // Parse strategy breakdown
  overview.byStrategy = {};
  let strategyStartRow = -1;
  
  for (let i = 0; i < data.length; i++) {
    if (data[i][0] === 'STRATEGY BREAKDOWN') {
      strategyStartRow = i + 2; // Skip header row
      break;
    }
  }
  
  if (strategyStartRow > 0) {
    for (let i = strategyStartRow; i < data.length && data[i][0]; i++) {
      const strategy = data[i][0];
      overview.byStrategy[strategy] = {
        trades: data[i][1],
        observations: data[i][2],
        hitRate: parsePercentToDecimal(data[i][3]),
        profitableRate: parsePercentToDecimal(data[i][4]),
        profitFactor: parseNumber(data[i][5]),
        avgWin: parsePercentToDecimal(data[i][6]),
        avgLoss: parsePercentToDecimal(data[i][7])
      };
    }
  }

  overview.avgWin = overview.avgProfit;
  overview.avgPremiumEstimate = 200;

  return overview;
}

/**
 * Collect data quality data from SR_DataQuality sheet
 */
function collectDataQualityData(ss) {
  const sheet = ss.getSheetByName('SR_DataQuality');
  if (!sheet) return {};
  
  const data = sheet.getDataRange().getValues();
  const quality = {
    overallScore: parseNumber(data[0][1]),
    fieldCompleteness: {},
    recommendations: []
  };
  
  // Find field completeness section
  let fieldStartRow = -1;
  for (let i = 0; i < data.length; i++) {
    if (data[i][0] === 'FIELD COMPLETENESS') {
      fieldStartRow = i + 2; // Skip header
      break;
    }
  }
  
  if (fieldStartRow > 0) {
    for (let i = fieldStartRow; i < data.length && data[i][0]; i++) {
      const field = data[i][0];
      if (field === 'RECOMMENDATIONS') break;

      quality.fieldCompleteness[field] = {
        percentage: parseNumber(data[i][1]),
        missing: parseNumber(data[i][2]),
        status: data[i][3]
      };
    }
  }
  
  // Find recommendations
  let recStartRow = -1;
  for (let i = 0; i < data.length; i++) {
    if (data[i][0] === 'RECOMMENDATIONS') {
      recStartRow = i + 1;
      break;
    }
  }
  
  if (recStartRow > 0) {
    for (let i = recStartRow; i < data.length && data[i][0]; i++) {
      quality.recommendations.push(data[i][0]);
    }
  }
  
  return quality;
}

/**
 * Collect holding period data from SR_HoldingPeriod sheet
 */
function collectHoldingPeriodData(ss) {
  const sheet = ss.getSheetByName('SR_HoldingPeriod');
  if (!sheet) return {};
  
  const data = sheet.getDataRange().getValues();
  const holding = {
    optimalExit: {},
    byDay: [],
    decayAnalysis: {}
  };
  
  // Parse optimal exit
  holding.optimalExit = {
    bestDay: data[1][1] || 'N/A',
    profitableRate: parsePercentToDecimal(data[2][1]) || 0,
    recommendation: data[3][1] || 'N/A'
  };
  
  // Find day-by-day section
  let dayStartRow = -1;
  for (let i = 0; i < data.length; i++) {
    if (data[i][0] === 'DAY-BY-DAY PERFORMANCE') {
      dayStartRow = i + 2; // Skip header
      break;
    }
  }
  
  if (dayStartRow > 0) {
    for (let i = dayStartRow; i < data.length && data[i][0]; i++) {
      if (data[i][0] === 'PROFIT DECAY ANALYSIS') break;
      
      holding.byDay.push({
        day: data[i][0],
        totalObs: data[i][1],
        profitable: data[i][2],
        hitRate: parsePercentToDecimal(data[i][3]),
        profitableRate: parsePercentToDecimal(data[i][4]),
        avgWin: parsePercentToDecimal(data[i][5]),
        avgLoss: parsePercentToDecimal(data[i][6]),
        profitFactor: parseNumber(data[i][7]),
        avgMove: parsePercentToDecimal(data[i][8])
      });
    }
  }
  
  return holding;
}

/**
 * Collect multi-day data from SR_MultiDay sheet
 */
function collectMultiDayData(ss) {
  const sheet = ss.getSheetByName('SR_MultiDay');
  if (!sheet) return {};
  
  const data = sheet.getDataRange().getValues();
  const multiDay = {
    sustainedProfitable: [],
    profitabilityByDay: []
  };
  
  // Parse sustained profitable trades
  let sustainedStartRow = 2; // After header
  for (let i = sustainedStartRow; i < data.length && data[i][0]; i++) {
    if (data[i][0] === 'PROFITABILITY BY DAY') break;
    
    multiDay.sustainedProfitable.push({
      ticker: data[i][0],
      strategy: data[i][1],
      consecutiveDays: data[i][2],
      peakDay: data[i][3],
      peakValue: data[i][4],
      strike: data[i][5]
    });
  }
  
  // Find profitability by day section
  let dayStartRow = -1;
  for (let i = 0; i < data.length; i++) {
    if (data[i][0] === 'PROFITABILITY BY DAY') {
      dayStartRow = i + 2; // Skip header
      break;
    }
  }
  
  if (dayStartRow > 0) {
    for (let i = dayStartRow; i < data.length && data[i][0]; i++) {
      multiDay.profitabilityByDay.push({
        day: data[i][0],
        totalTrades: data[i][1],
        profitable: data[i][2],
        successRate: parsePercentToDecimal(data[i][3]),
        avgProfit: parsePercentToDecimal(data[i][4])
      });
    }
  }

  return multiDay;
}

/**
 * Collect indicators data from SR_Indicators sheet
 */
function collectIndicatorsData(ss) {
  const sheet = ss.getSheetByName('SR_Indicators');
  if (!sheet) return {};
  
  const data = sheet.getDataRange().getValues();
  const indicators = {
    highImpact: [],
    mediumImpact: []
  };
  
  // Parse high impact indicators
  let highStartRow = 2; // After header
  for (let i = highStartRow; i < data.length && data[i][0]; i++) {
    if (data[i][0] === 'MEDIUM IMPACT INDICATORS') break;

    indicators.highImpact.push({
      type: data[i][0],
      indicator: data[i][1],
      correlation: parseNumber(data[i][2]),
      dataCompleteness: parsePercentToDecimal(data[i][3]),
      bullishRange: data[i][4],
      bearishRange: data[i][5]
    });
  }
  
  // Find medium impact section
  let medStartRow = -1;
  for (let i = 0; i < data.length; i++) {
    if (data[i][0] === 'MEDIUM IMPACT INDICATORS') {
      medStartRow = i + 2; // Skip header
      break;
    }
  }
  
  if (medStartRow > 0) {
    for (let i = medStartRow; i < data.length && data[i][0]; i++) {
      indicators.mediumImpact.push({
        type: data[i][0],
        indicator: data[i][1],
        correlation: parseNumber(data[i][2]),
        dataCompleteness: parsePercentToDecimal(data[i][3])
      });
    }
  }

  return indicators;
}

/**
 * Collect earnings data from SR_Earnings sheet
 */
function collectEarningsData(ss) {
  const sheet = ss.getSheetByName('SR_Earnings');
  if (!sheet) return {};
  
  const data = sheet.getDataRange().getValues();
  const earnings = {
    summary: {},
    byDaysToEarnings: [],
    byReleaseTime: []
  };
  
  // Parse summary
  for (let i = 1; i < Math.min(15, data.length); i++) {
    if (data[i][0] === 'PERFORMANCE BY DAYS TO EARNINGS') break;
    const key = data[i][0];
    const value = data[i][1];
    earnings.summary[key] = value;
  }
  
  // Find performance by days section
  let daysStartRow = -1;
  for (let i = 0; i < data.length; i++) {
    if (data[i][0] === 'PERFORMANCE BY DAYS TO EARNINGS') {
      daysStartRow = i + 2; // Skip header
      break;
    }
  }
  
  if (daysStartRow > 0) {
    for (let i = daysStartRow; i < data.length && data[i][0]; i++) {
      if (data[i][0] === 'PERFORMANCE BY RELEASE TIME') break;

      earnings.byDaysToEarnings.push({
        window: data[i][0],
        trades: data[i][1],
        hits: data[i][2],
        hitRate: parsePercentToDecimal(data[i][3]),
        avgProfit: parsePercentToDecimal(data[i][4]),
        avgDaysToHit: parseNumber(data[i][5])
      });
    }
  }
  
  // Find release time section
  let timeStartRow = -1;
  for (let i = 0; i < data.length; i++) {
    if (data[i][0] === 'PERFORMANCE BY RELEASE TIME') {
      timeStartRow = i + 2; // Skip header
      break;
    }
  }
  
  if (timeStartRow > 0) {
    for (let i = timeStartRow; i < data.length && data[i][0]; i++) {
      earnings.byReleaseTime.push({
        releaseTime: data[i][0],
        total: data[i][1],
        hits: data[i][2],
        hitRate: parsePercentToDecimal(data[i][3]),
        avgProfit: parsePercentToDecimal(data[i][4]),
        avgDays: parseNumber(data[i][5])
      });
    }
  }

  return earnings;
}

/**
 * Collect strategies data from SR_Strategies sheet
 */
function collectStrategiesData(ss) {
  const sheet = ss.getSheetByName('SR_Strategies');
  if (!sheet) return [];
  
  const data = sheet.getDataRange().getValues();
  const strategies = [];
  
  // Start from row 3 (after header)
  for (let i = 2; i < data.length && data[i][0]; i++) {
    strategies.push({
      strategy: data[i][0],
      totalTrades: data[i][1],
      hitCount: data[i][2],
      hitRate: parsePercentToDecimal(data[i][3]),
      avgProfit: parsePercentToDecimal(data[i][4]),
      avgLoss: parsePercentToDecimal(data[i][5]),
      profitFactor: parseNumber(data[i][6]),
      avgDaysToHit: parseNumber(data[i][7]),
      totalProfit: parseNumber(data[i][8]),
      totalLoss: parseNumber(data[i][9])
    });
  }

  return strategies;
}

/**
 * Collect top plays data from SR_TopPlays sheet
 */
function collectTopPlaysData(ss) {
  const sheet = ss.getSheetByName('SR_TopPlays');
  if (!sheet) return [];
  
  const data = sheet.getDataRange().getValues();
  const topPlays = [];
  
  // Start from row 3 (after header)
  for (let i = 2; i < data.length && data[i][0]; i++) {
    if (data[i][0] === 'INDICATOR PROFILES (TOP 5)') break;
    
    topPlays.push({
      rank: data[i][0],
      ticker: data[i][1],
      strategy: data[i][2],
      entryDate: data[i][3],
      strike: data[i][4],
      hitPrice: data[i][5],
      maxProfit: parsePercentToDecimal(data[i][6]),
      daysToHit: data[i][7],
      riskReward: parseNumber(data[i][8]),
      profitableDays: data[i][9]
    });
  }
  
  // Find indicator profiles
  let profileStartRow = -1;
  for (let i = 0; i < data.length; i++) {
    if (data[i][0] === 'INDICATOR PROFILES (TOP 5)') {
      profileStartRow = i + 2; // Skip header
      break;
    }
  }
  
  if (profileStartRow > 0 && topPlays.length >= 5) {
    for (let i = 0; i < 5 && profileStartRow + i < data.length; i++) {
      if (topPlays[i]) {
        topPlays[i].indicatorProfile = data[profileStartRow + i][2];
        topPlays[i].multiDayProfile = data[profileStartRow + i][3];
      }
    }
  }
  
  return topPlays;
}

/**
 * Collect risk/reward data from SR_RiskReward sheet
 */
function collectRiskRewardData(ss) {
  const sheet = ss.getSheetByName('SR_RiskReward');
  if (!sheet) return {};

  const data = sheet.getDataRange().getValues();
  const riskReward = {
    overview: {},
    distribution: []
  };
  
  // Parse overview
  for (let i = 1; i < data.length; i++) {
    if (data[i][0] === 'RISK/REWARD DISTRIBUTION') break;
    const key = data[i][0];
    const value = data[i][1];
    if (key) riskReward.overview[key] = parseNumber(value);
  }
  
  // Find distribution section
  let distStartRow = -1;
  for (let i = 0; i < data.length; i++) {
    if (data[i][0] === 'RISK/REWARD DISTRIBUTION') {
      distStartRow = i + 2; // Skip header
      break;
    }
  }
  
  if (distStartRow > 0) {
    for (let i = distStartRow; i < data.length && data[i][0]; i++) {
      riskReward.distribution.push({
        range: data[i][0],
        count: parseNumber(data[i][1]),
        percentage: parseNumber(data[i][2])
      });
    }
  }

  return riskReward;
}

function collectIncompleteTradesData(ss) {
  // Try to reuse stored data if available
  try {
    const scriptProperties = PropertiesService.getScriptProperties();
    const stored = scriptProperties.getProperty('SUCCESS_REPORT_DATA');
    if (stored) {
      const parsed = JSON.parse(stored);
      if (parsed && parsed.incompleteTrades) {
        return parsed.incompleteTrades;
      }
    }
  } catch (err) {
    console.warn('Unable to reuse stored incomplete trades:', err);
  }

  const sheet = ss.getSheetByName('SR_IncompleteTrades');
  if (!sheet) {
    return {
      totalCount: 0,
      byStrategy: [],
      sample: [],
      message: 'No incomplete trades sheet found. Run the full success report to generate details.'
    };
  }

  const data = sheet.getDataRange().getValues();
  if (!data || data.length < 2) {
    return {
      totalCount: 0,
      byStrategy: [],
      sample: [],
      message: 'Incomplete trades sheet is empty.'
    };
  }

  const headers = data[0];
  const rows = data.slice(1).filter(row => row.some(cell => cell !== ''));

  const strategyIndex = headers.indexOf('Strategy');
  const tickerIndex = headers.indexOf('Ticker');
  const runDateIndex = headers.indexOf('Run Date');
  const expDateIndex = headers.indexOf('Exp Date');
  const strikeIndex = headers.indexOf('Strike');
  const longStrikeIndex = headers.indexOf('Long Strike');

  const strategyCounts = {};
  const sample = [];

  rows.forEach((row, idx) => {
    const strategy = strategyIndex >= 0 ? row[strategyIndex] : 'Unknown';
    if (strategy) {
      strategyCounts[strategy] = (strategyCounts[strategy] || 0) + 1;
    }

    if (idx < 25) {
      sample.push({
        strategy: strategy,
        ticker: tickerIndex >= 0 ? row[tickerIndex] : '',
        runDate: runDateIndex >= 0 ? row[runDateIndex] : '',
        expDate: expDateIndex >= 0 ? row[expDateIndex] : '',
        strike: strikeIndex >= 0 ? row[strikeIndex] : '',
        longStrike: longStrikeIndex >= 0 ? row[longStrikeIndex] : ''
      });
    }
  });

  const byStrategy = Object.entries(strategyCounts)
    .map(([strategy, count]) => ({ strategy, count }))
    .sort((a, b) => b.count - a.count);

  return {
    totalCount: rows.length,
    byStrategy: byStrategy,
    sample: sample
  };
}

function collectTradeRecords(ss) {
  try {
    const scriptProperties = PropertiesService.getScriptProperties();
    const stored = scriptProperties.getProperty('SUCCESS_REPORT_DATA');
    if (stored) {
      const parsed = JSON.parse(stored);
      if (parsed && parsed.tradeRecords) {
        return parsed.tradeRecords;
      }
    }
  } catch (err) {
    console.warn('Unable to reuse stored trade records:', err);
  }

  return [];
}

function ensureSuccessReportShape(data) {
  const base = {
    overview: {
      totalTrades: 0,
      totalObservations: 0,
      totalHits: 0,
      profitableTrades: 0,
      hitRate: 0,
      profitableRate: 0,
      profitFactor: 0,
      avgProfit: 0,
      avgLoss: 0,
      avgRiskReward: 0,
      avgDaysToHit: 0,
      avgPremiumEstimate: 200
    },
    dataQuality: {
      overallScore: 0,
      fieldCompleteness: {},
      recommendations: []
    },
    holdingPeriod: {
      optimalExit: { bestDay: 'Day 1', profitableRate: 0, recommendation: '' },
      byDay: [],
      decayAnalysis: {}
    },
    multiDayProfitability: { profitabilityByDay: [], sustainedWinners: [] },
    indicatorEffectiveness: [],
    earningsTiming: {
      summary: {},
      byDaysToEarnings: [],
      byReleaseTime: []
    },
    strategyPerformance: [],
    riskManagement: {
      riskReward: { buckets: [], exitTiming: [] },
      kellySizing: []
    },
    topPlays: [],
    incompleteTrades: { totalCount: 0, byStrategy: [], sample: [] },
    tradeRecords: []
  };

  const merged = Object.assign({}, base, data || {});
  merged.overview = Object.assign({}, base.overview, data?.overview || {});
  merged.dataQuality = Object.assign({}, base.dataQuality, data?.dataQuality || {});
  merged.holdingPeriod = Object.assign({}, base.holdingPeriod, data?.holdingPeriod || {});
  merged.multiDayProfitability = Object.assign({}, base.multiDayProfitability, data?.multiDayProfitability || {});
  merged.earningsTiming = Object.assign({}, base.earningsTiming, data?.earningsTiming || {});
  merged.riskManagement = Object.assign({}, base.riskManagement, data?.riskManagement || {});
  merged.riskManagement.riskReward = Object.assign({}, base.riskManagement.riskReward, data?.riskManagement?.riskReward || {});
  merged.incompleteTrades = Object.assign({}, base.incompleteTrades, data?.incompleteTrades || {});
  merged.tradeRecords = Array.isArray(data?.tradeRecords) ? data.tradeRecords : [];

  if (!merged.riskReward) {
    merged.riskReward = merged.riskManagement.riskReward;
  }

  return merged;
}

function calculateKellySizingFromStrategies(strategies) {
  if (!strategies || strategies.length === 0) return [];

  return strategies.map(strategy => {
    const winRate = strategy.hitRate || 0;
    const avgWin = Math.abs(strategy.avgProfit || 0);
    const avgLoss = Math.abs(strategy.avgLoss || 0);
    const payoutRatio = avgLoss > 0 ? avgWin / avgLoss : 0;
    const fullKelly = payoutRatio > 0
      ? Math.max(0, winRate - ((1 - winRate) / payoutRatio))
      : 0;

    return {
      strategy: strategy.strategy,
      fullKelly: fullKelly * 100,
      halfKelly: fullKelly * 50,
      winRate: winRate * 100,
      avgWin: avgWin * 100,
      avgLoss: avgLoss * 100
    };
  }).sort((a, b) => b.fullKelly - a.fullKelly);
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