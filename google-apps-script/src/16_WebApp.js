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
    indicatorEffectiveness: formatIndicatorData(
      insights.indicatorEffectiveness,
      insights.overview || {}
    ),
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
  const toNumber = (value) => {
    if (value === null || value === undefined) return 0;
    if (typeof value === 'number') {
      return isNaN(value) ? 0 : value;
    }
    if (typeof value === 'string') {
      const cleaned = value.replace(/[^0-9.-]/g, '');
      if (cleaned === '') return 0;
      const parsed = parseFloat(cleaned);
      return isNaN(parsed) ? 0 : parsed;
    }
    return 0;
  };

  const normalizeRate = (value) => {
    const num = toNumber(value);
    if (!isFinite(num)) return 0;
    return Math.abs(num) > 1 ? num / 100 : num;
  };

  const normalizePercentValue = (value) => {
    const num = toNumber(value);
    if (!isFinite(num)) return 0;
    return Math.abs(num) > 1 ? num : num * 100;
  };

  const profitabilitySource = multiDay?.profitabilityByDay || multiDay?.profitByDay || [];
  const profitabilityByDay = [];

  if (Array.isArray(profitabilitySource)) {
    profitabilitySource.forEach(item => {
      if (!item) return;
      const dayValue = toNumber(item.day ?? item.dayIndex);
      profitabilityByDay.push({
        day: dayValue,
        rate: normalizeRate(item.rate ?? item.successRate ?? item.profitableRate),
        count: Math.round(toNumber(item.count ?? item.totalTrades ?? item.total)),
        profitable: Math.round(toNumber(item.profitable ?? item.profitableCount)),
        avgProfit: normalizePercentValue(item.avgProfit ?? item.profit ?? item.avgReturn)
      });
    });
  } else if (profitabilitySource && typeof profitabilitySource === 'object') {
    Object.entries(profitabilitySource).forEach(([dayKey, stats]) => {
      if (!stats) return;
      const dayValue = toNumber(stats.day ?? dayKey);
      profitabilityByDay.push({
        day: dayValue,
        rate: normalizeRate(stats.rate ?? stats.successRate ?? stats.profitableRate),
        count: Math.round(toNumber(stats.count ?? stats.totalTrades ?? stats.total)),
        profitable: Math.round(toNumber(stats.profitable ?? stats.profitableCount)),
        avgProfit: normalizePercentValue(stats.avgProfit ?? stats.profit ?? stats.avgReturn)
      });
    });
  }

  profitabilityByDay.sort((a, b) => a.day - b.day);

  const rateByDay = profitabilityByDay.reduce((acc, entry) => {
    acc[entry.day] = entry.rate;
    return acc;
  }, {});

  const sustainedSource = multiDay?.sustainedProfitability || multiDay?.sustainedProfitable || multiDay?.sustainedWinners || [];
  let sustainedWinners = [];

  const mapAggregateEntry = (daysValue, stats = {}) => ({
    days: toNumber(daysValue),
    count: Math.round(toNumber(stats.count ?? stats.total ?? stats.tradeCount)),
    successRate: normalizeRate(stats.successRate ?? stats.rate ?? stats.profitableRate ?? stats.hitRate),
    avgProfit: normalizePercentValue(stats.avgProfit ?? stats.profit ?? stats.avgReturn)
  });

  if (Array.isArray(sustainedSource)) {
    const hasAggregateFields = sustainedSource.some(item => item && (item.days !== undefined || item.count !== undefined || item.successRate !== undefined));

    if (hasAggregateFields) {
      sustainedWinners = sustainedSource.map(item => mapAggregateEntry(item.days ?? item.day ?? item.consecutiveDays, item));
    } else {
      const grouped = {};

      sustainedSource.forEach(trade => {
        if (!trade) return;
        const days = toNumber(trade.days ?? trade.consecutiveDays);
        if (!isFinite(days) || days <= 0) return;

        if (!grouped[days]) {
          grouped[days] = {
            days: days,
            count: 0,
            totalProfit: 0,
            successRateSum: 0,
            successRateCount: 0,
            hitCount: 0,
            hitObservations: 0
          };
        }

        const group = grouped[days];
        group.count += 1;

        const profitValue = normalizePercentValue(trade.avgProfit ?? trade.peakValue ?? trade.maxProfit ?? trade.profit);
        if (isFinite(profitValue)) {
          group.totalProfit += profitValue;
        }

        if (trade.successRate !== undefined || trade.rate !== undefined || trade.hitRate !== undefined) {
          group.successRateSum += normalizeRate(trade.successRate ?? trade.rate ?? trade.hitRate);
          group.successRateCount += 1;
        } else if (typeof trade.wasHit === 'boolean') {
          group.hitCount += trade.wasHit ? 1 : 0;
          group.hitObservations += 1;
        }
      });

      sustainedWinners = Object.values(grouped).map(group => {
        let successRate = 0;
        if (group.successRateCount > 0) {
          successRate = group.successRateSum / group.successRateCount;
        } else if (group.hitObservations > 0) {
          successRate = group.hitObservations > 0 ? group.hitCount / group.hitObservations : 0;
        } else if (rateByDay[group.days] !== undefined) {
          successRate = rateByDay[group.days];
        }

        return {
          days: group.days,
          count: group.count,
          successRate: successRate,
          avgProfit: group.count > 0 ? group.totalProfit / group.count : 0
        };
      });
    }
  } else if (sustainedSource && typeof sustainedSource === 'object') {
    sustainedWinners = Object.entries(sustainedSource).map(([daysKey, stats]) => mapAggregateEntry(daysKey, stats));
  }

  sustainedWinners = sustainedWinners
    .filter(item => item && isFinite(item.days))
    .map(item => ({
      days: toNumber(item.days),
      count: Math.max(0, Math.round(toNumber(item.count))),
      successRate: normalizeRate(item.successRate),
      avgProfit: normalizePercentValue(item.avgProfit)
    }))
    .sort((a, b) => a.days - b.days);

  return {
    profitabilityByDay,
    sustainedWinners
  };
}

/**
 * Format indicator effectiveness data for web
 */
function formatIndicatorData(indicators, overviewStats) {
  if (!indicators) return [];

  const totalTrades = Number(overviewStats?.totalTrades) || 0;

  const formatIndicatorLabel = (value) => {
    if (!value) return '';
    const spaced = value
      .replace(/_/g, ' ')
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .trim();

    return spaced.split(/\s+/).map(part => {
      if (/^[A-Z0-9]+$/.test(part)) return part;
      if (/^[a-z0-9]+$/.test(part)) {
        if (part.length <= 4 || /\d/.test(part)) {
          return part.toUpperCase();
        }
        return part.charAt(0).toUpperCase() + part.slice(1).toLowerCase();
      }
      return part.charAt(0).toUpperCase() + part.slice(1).toLowerCase();
    }).join(' ');
  };

  const formatRange = (label, range) => {
    if (!range || !range.count) return '';

    const min = typeof range.min === 'number' ? range.min.toFixed(2) : range.min;
    const max = typeof range.max === 'number' ? range.max.toFixed(2) : range.max;
    const avgProfit = typeof range.avgProfit === 'number' ? range.avgProfit.toFixed(2) : null;
    const parts = [];

    if (min !== null && min !== undefined && max !== null && max !== undefined) {
      parts.push(`${min}-${max}`);
    }

    if (avgProfit !== null) {
      const prefix = range.avgProfit >= 0 ? '+' : '';
      parts.push(`${prefix}${avgProfit}% avg`);
    }

    parts.push(`${range.count} trades`);

    return `${label}: ${parts.join(' | ')}`;
  };

  const formatted = Object.entries(indicators).map(([key, data]) => {
    const rawCorrelation = data?.correlationWithProfit ?? data?.correlation ?? 0;
    const correlation = Number(rawCorrelation) || 0;
    const absCorrelation = Math.abs(correlation);
    const inferredSignificance = absCorrelation > 0.3 ? 'HIGH' : absCorrelation > 0.15 ? 'MEDIUM' : 'LOW';
    const significance = data?.significance || inferredSignificance;

    const keyParts = key.split('_');
    const typeFromKey = (data?.type || keyParts[0] || '').toLowerCase();
    const indicatorNameParts = keyParts.length > 1 ? keyParts.slice(1) : keyParts;
    const indicatorName = indicatorNameParts.join('_');
    const displayName = `${formatIndicatorLabel(indicatorName)}${typeFromKey ? ` (${typeFromKey.toUpperCase()})` : ''}`.trim();

    const ranges = data?.profitableRanges || {};
    const bullishRangeText = formatRange('Bullish', ranges.bullish);
    const bearishRangeText = formatRange('Bearish', ranges.bearish);
    const profitableRange = [bullishRangeText, bearishRangeText]
      .filter(text => text)
      .join(' | ')
      || 'N/A';

    const bullishCount = ranges?.bullish?.count || 0;
    const bearishCount = ranges?.bearish?.count || 0;
    const totalProfitableCount = bullishCount + bearishCount;

    const weightedProfitSum =
      (typeof ranges?.bullish?.avgProfit === 'number' ? ranges.bullish.avgProfit * bullishCount : 0) +
      (typeof ranges?.bearish?.avgProfit === 'number' ? ranges.bearish.avgProfit * bearishCount : 0);
    const avgProfit = totalProfitableCount > 0 ? weightedProfitSum / totalProfitableCount : 0;

    let hitRate = 0;
    if (typeof data?.hitRate === 'number') {
      hitRate = data.hitRate > 1 ? data.hitRate / 100 : data.hitRate;
    } else if (totalTrades > 0 && totalProfitableCount > 0) {
      hitRate = totalProfitableCount / totalTrades;
    }
    if (hitRate > 1) {
      hitRate = 1;
    }

    return {
      name: displayName || key,
      type: typeFromKey ? typeFromKey.toUpperCase() : 'GENERAL',
      correlation,
      significance,
      profitableRange,
      bullishRange: bullishRangeText || 'N/A',
      bearishRange: bearishRangeText || 'N/A',
      hitRate,
      avgProfit,
      sampleSize: totalProfitableCount,
      dataCompleteness: data?.dataCompleteness || 'N/A'
    };
  });

  return formatted.sort((a, b) => Math.abs(b.correlation) - Math.abs(a.correlation));
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
  if (!strategies) return [];

  const toNumber = value => {
    if (value === null || value === undefined || value === '') return 0;
    const num = Number(value);
    return Number.isFinite(num) ? num : 0;
  };

  const hasValue = value => value !== undefined && value !== null && value !== '';

  return Object.entries(strategies).map(([strategy, data]) => {
    const totalTrades = toNumber(data.totalTrades ?? data.tradeCount ?? data.count);
    const hitTrades = toNumber(data.hitTrades ?? data.hitCount ?? data.hits);
    const totalProfit = toNumber(data.totalProfit);
    const totalLoss = toNumber(data.totalLoss);

    const hitRate = hasValue(data.hitRate)
      ? toNumber(data.hitRate)
      : (totalTrades > 0 ? hitTrades / totalTrades : 0);

    const avgProfit = hasValue(data.avgProfit)
      ? toNumber(data.avgProfit)
      : (totalTrades > 0 ? totalProfit / totalTrades : 0);

    const avgLoss = hasValue(data.avgLoss)
      ? toNumber(data.avgLoss)
      : (totalTrades > 0 ? totalLoss / totalTrades : 0);

    const profitFactor = hasValue(data.profitFactor)
      ? toNumber(data.profitFactor)
      : (totalLoss > 0 ? totalProfit / totalLoss : (totalProfit > 0 ? totalTrades || hitTrades || 0 : 0));

    const avgDaysToHit = hasValue(data.avgDaysToHit)
      ? toNumber(data.avgDaysToHit)
      : (hitTrades > 0 ? toNumber(data.totalDaysToHit) / hitTrades : 0);

    return {
      strategy: strategy,
      tradeCount: totalTrades,
      hitCount: hitTrades,
      hitRate: hitRate,
      profitFactor: profitFactor,
      avgDaysToHit: avgDaysToHit,
      avgProfit: avgProfit,
      avgLoss: avgLoss,
      totalProfit: totalProfit,
      totalLoss: totalLoss,
      bestPerformers: Array.isArray(data.bestPerformers) ? data.bestPerformers : []
    };
  });
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
    indicatorEffectiveness: collectIndicatorsData(SpreadsheetApp.getActive()),
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

// collectIndicatorsData is defined in 17_SuccessReportWebApp.js. We call that version so
// both the stored report and dashboard fallback use the same normalization logic.