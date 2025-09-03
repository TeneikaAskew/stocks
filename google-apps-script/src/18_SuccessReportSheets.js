/**
 * Success Report Individual Sheets
 * Creates separate sheets for each analysis section
 */

/**
 * Helper function to pad data arrays to consistent column count
 * @param {Array} data - The data array
 * @return {Array} Padded data array
 */
function padDataArray(data) {
  const maxCols = Math.max(...data.map(row => row.length));
  return data.map(row => {
    while (row.length < maxCols) {
      row.push('');
    }
    return row;
  });
}

/**
 * Create individual sheets for each report section
 * @param {SpreadsheetApp.Spreadsheet} ss - The spreadsheet
 * @param {Object} insights - The analysis insights object
 */
function EW_createIndividualSheets(ss, insights) {
  console.log('Creating individual report sheets...');
  
  // Create comprehensive overview sheet with merged data
  EW_createOverviewSheet(ss, insights);
  
  // Create remaining analysis sheets (not merged into overview)
  EW_createEarningsSheet(ss, insights.earningsTiming);
  EW_createTopPlaysSheet(ss, insights.topPlays);
  
  // These sheets are now merged into SR_Overview:
  // - EW_createDataQualitySheet (merged)
  // - EW_createHoldingPeriodSheet (merged) 
  // - EW_createMultiDaySheet (merged)
  // - EW_createIndicatorsSheet (merged)
  // - EW_createStrategiesSheet (merged)
  // - EW_createRiskRewardSheet (merged)
  
  console.log('Individual report sheets created successfully');
}

/**
 * Create or update Overview sheet
 */
function EW_createOverviewSheet(ss, insights) {
  const sheetName = 'SR_Overview';
  let sheet = ss.getSheetByName(sheetName);
  
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
  } else {
    sheet.clear();
  }
  
  const overview = insights.overview || {};
  const trades = insights.allTrades || [];
  const totalTrades = trades.length;
  
  // Start with main performance metrics
  const data = [
    ['OVERALL PERFORMANCE METRICS', '', ''],
    ['Total Trades', overview.totalTrades || 0, ''],
    ['Total Observations', overview.totalObservations || 0, 'Total data points across all days'],
    ['Hit Rate', `${((overview.hitRate || 0) * 100).toFixed(1)}%`, 'Percentage of trades where strike was hit'],
    ['Profitable Rate', `${((overview.profitableRate || 0) * 100).toFixed(1)}%`, 'Percentage of observations with positive profit'],
    ['Profit Factor', (overview.profitFactor || 0).toFixed(2), `$${(overview.profitFactor || 0).toFixed(2)} profit for every $1 loss`],
    ['Avg Profit', `${((overview.avgProfit || 0) * 100).toFixed(2)}%`, 'Average profit on winning trades'],
    ['Avg Loss', `${((overview.avgLoss || 0) * 100).toFixed(2)}%`, 'Average loss on losing trades'],
    ['Avg Risk/Reward', (overview.avgRiskReward || 0).toFixed(2), `Risk $1 to gain $${(overview.avgRiskReward || 0).toFixed(2)}`],
    ['Avg Days to Hit', (overview.avgDaysToHit || 0).toFixed(1), 'Average days to reach strike'],
    ['Best Holding Day', overview.bestHoldingDay || 'Day 1', 'Optimal day to exit positions'],
    ['', '', '']
  ];
  
  // Add DATA QUALITY section
  const fieldCompleteness = {
    strikeHit: trades.filter(t => t.strikeHit && t.strikeHit.length > 0).length,
    maxFavorable: trades.filter(t => t.maxFavorable && t.maxFavorable.length > 0).length,
    minUnfavorable: trades.filter(t => t.minUnfavorable && t.minUnfavorable.length > 0).length,
    indicators: trades.filter(t => t.rsi && t.rsi.length > 0).length
  };
  
  const overallDataScore = totalTrades > 0 ? 
    Math.round(Object.values(fieldCompleteness).reduce((sum, count) => sum + count, 0) / 
    (Object.keys(fieldCompleteness).length * totalTrades) * 100) : 0;
  
  data.push(['DATA QUALITY', '', '', '']);
  data.push(['Overall Score', `${overallDataScore}%`, overallDataScore >= 80 ? '✅ Good' : overallDataScore >= 60 ? '⚠️ Fair' : '❌ Poor', '']);
  data.push(['Strike Hit Data', `${totalTrades > 0 ? Math.round(fieldCompleteness.strikeHit / totalTrades * 100) : 0}%`, '', '']);
  data.push(['Price Movement Data', `${totalTrades > 0 ? Math.round(fieldCompleteness.maxFavorable / totalTrades * 100) : 0}%`, '', '']);
  data.push(['Indicator Data', `${totalTrades > 0 ? Math.round(fieldCompleteness.indicators / totalTrades * 100) : 0}%`, '', '']);
  data.push(['', '', '', '']);
  
  // Add STRATEGY BREAKDOWN
  data.push(['STRATEGY BREAKDOWN', 'Total Trades', 'Hit Count', 'Hit Rate', 'Avg Profit', 'Avg Loss', 'Profit Factor', 'Avg Days to Hit', 'Total Profit', 'Total Loss']);
  
  if (overview.byStrategy) {
    const sortedStrategies = Object.entries(overview.byStrategy)
      .sort((a, b) => (b[1].hitRate || 0) - (a[1].hitRate || 0));
    
    sortedStrategies.forEach(([strategy, stats]) => {
      data.push([
        strategy,
        stats.totalTrades || stats.count || 0,
        stats.hitTrades || stats.hits || 0,
        `${((stats.hitRate || 0) * 100).toFixed(1)}%`,
        `${((Number(stats.avgProfit || stats.avgWin) || 0) * 100).toFixed(2)}%`,
        `${((Number(stats.avgLoss) || 0) * 100).toFixed(2)}%`,
        (Number(stats.profitFactor) || 0).toFixed(2),
        (Number(stats.avgDaysToHit) || 0).toFixed(1),
        (Number(stats.totalProfit) || 0).toFixed(2),
        (Number(stats.totalLoss) || 0).toFixed(2)
      ]);
    });
  }
  data.push(['', '', '', '', '', '', '', '', '', '']);
  
  // Add HOLDING PERIOD ANALYSIS
  data.push(['HOLDING PERIOD ANALYSIS', 'Day 0', 'Day 1', 'Day 2', 'Day 3', 'Day 4', 'Day 5']);
  
  // Calculate day-by-day performance
  const dayPerformance = [];
  for (let day = 0; day <= 5; day++) {
    const dayTrades = trades.filter(t => t.profitDays && t.profitDays[day] !== undefined);
    const profitable = dayTrades.filter(t => t.profitDays[day] > 0);
    if (dayTrades.length > 0) {
      dayPerformance.push(`${(profitable.length / dayTrades.length * 100).toFixed(0)}%`);
    } else {
      dayPerformance.push('N/A');
    }
  }
  data.push(['Profitable Rate'].concat(dayPerformance));
  
  // Add strike hit rates by day
  const hitRates = [];
  for (let day = 0; day <= 5; day++) {
    const dayTrades = trades.filter(t => t.strikeHit && t.strikeHit[day] !== undefined);
    const hits = dayTrades.filter(t => t.strikeHit[day] && t.strikeHit[day] !== 'NO');
    if (dayTrades.length > 0) {
      hitRates.push(`${(hits.length / dayTrades.length * 100).toFixed(0)}%`);
    } else {
      hitRates.push('N/A');
    }
  }
  data.push(['Hit Rate'].concat(hitRates));
  data.push(['', '', '', '', '', '', '']);
  
  // Add MULTI-DAY PROFITABILITY
  if (insights.multiDayProfitability) {
    const multiDay = insights.multiDayProfitability;
    data.push(['MULTI-DAY PROFITABILITY', '', '', '']);
    data.push(['Consecutive Win Days (Avg)', multiDay.avgConsecutiveDays ? multiDay.avgConsecutiveDays.toFixed(1) : '0', '', '']);
    data.push(['Peak Value Day (Avg)', multiDay.avgPeakDay ? multiDay.avgPeakDay.toFixed(1) : '0', '', '']);
    data.push(['Peak Value (Avg)', multiDay.avgPeakValue ? `${(multiDay.avgPeakValue * 100).toFixed(2)}%` : '0%', '', '']);
    data.push(['Multi-Day Win Rate', multiDay.multiDayWinRate ? `${(multiDay.multiDayWinRate * 100).toFixed(1)}%` : '0%', '', '']);
    data.push(['', '', '', '']);
  }
  
  // Add KEY INDICATORS section
  if (insights.indicatorEffectiveness) {
    const indicators = insights.indicatorEffectiveness;
    data.push(['KEY INDICATORS', 'Bullish Success', 'Bearish Success', 'Impact']);
    
    // Find top performing indicator setups
    const topIndicators = [];
    if (indicators.rsi) {
      const oversold = indicators.rsi.ranges?.['Under 30'] || {};
      const overbought = indicators.rsi.ranges?.['70-100'] || {};
      if (oversold.winRate > 0.6) {
        topIndicators.push(['RSI < 30 (Oversold)', `${(oversold.winRate * 100).toFixed(0)}%`, '-', 'High']);
      }
      if (overbought.winRate > 0.6) {
        topIndicators.push(['RSI > 70 (Overbought)', '-', `${(overbought.winRate * 100).toFixed(0)}%`, 'High']);
      }
    }
    
    if (indicators.priceVsSMA20) {
      const below = indicators.priceVsSMA20.ranges?.['Below -5%'] || {};
      const above = indicators.priceVsSMA20.ranges?.['Above 5%'] || {};
      if (below.winRate > 0.6) {
        topIndicators.push(['Price < SMA20 -5%', `${(below.winRate * 100).toFixed(0)}%`, '-', 'Medium']);
      }
      if (above.winRate > 0.6) {
        topIndicators.push(['Price > SMA20 +5%', '-', `${(above.winRate * 100).toFixed(0)}%`, 'Medium']);
      }
    }
    
    // Add top indicators or default message
    if (topIndicators.length > 0) {
      topIndicators.forEach(ind => data.push(ind));
    } else {
      data.push(['No strong indicator signals found', '-', '-', '-']);
    }
    data.push(['', '', '', '']);
  }
  
  // Add RISK/REWARD DISTRIBUTION  
  if (insights.riskRewardPatterns) {
    const rrData = insights.riskRewardPatterns;
    data.push(['RISK/REWARD DISTRIBUTION', 'Count', 'Win Rate', '']);
    
    if (rrData.byRiskRewardRatio) {
      Object.entries(rrData.byRiskRewardRatio).forEach(([range, stats]) => {
        if (stats.count > 0) {
          data.push([
            range,
            stats.count,
            `${((stats.winRate || 0) * 100).toFixed(0)}%`,
            ''
          ]);
        }
      });
    }
    data.push(['', '', '', '']);
  }
  
  // Find the maximum number of columns
  const maxCols = Math.max(...data.map(row => row.length));
  
  // Pad rows to have consistent column count
  const paddedData = data.map(row => {
    while (row.length < maxCols) {
      row.push('');
    }
    return row;
  });
  
  sheet.getRange(1, 1, paddedData.length, maxCols).setValues(paddedData);
  
  // Format the sheet with multiple header rows
  sheet.getRange(1, 1).setFontSize(14).setFontWeight('bold');
  
  // Format section headers
  const headerRows = [];
  paddedData.forEach((row, index) => {
    if (row[0] && row[0].toString().match(/^[A-Z\s/]+$/) && row[0].length > 10) {
      headerRows.push(index + 1);
    }
  });
  
  headerRows.forEach(rowNum => {
    sheet.getRange(rowNum, 1, 1, maxCols).setFontWeight('bold').setBackground('#374151').setFontColor('white');
  });
  
  sheet.autoResizeColumns(1, maxCols);
}

/**
 * Create Data Quality sheet
 */
function EW_createDataQualitySheet(ss, insights) {
  const sheetName = 'SR_DataQuality';
  let sheet = ss.getSheetByName(sheetName);
  
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
  } else {
    sheet.clear();
  }
  
  const trades = insights.allTrades || [];
  const totalTrades = trades.length;
  
  // Calculate field completeness
  const fieldCompleteness = {
    strikeHit: trades.filter(t => t.strikeHit && t.strikeHit.length > 0).length,
    maxFavorable: trades.filter(t => t.maxFavorable && t.maxFavorable.length > 0).length,
    minUnfavorable: trades.filter(t => t.minUnfavorable && t.minUnfavorable.length > 0).length,
    profitDays: trades.filter(t => t.profitDays && t.profitDays.length > 0).length,
    rsi: trades.filter(t => t.rsi && t.rsi.length > 0).length,
    priceVsSMA20: trades.filter(t => t.priceVsSMA20 && t.priceVsSMA20.length > 0).length,
    priceVsVWAP: trades.filter(t => t.priceVsVWAP && t.priceVsVWAP.length > 0).length,
    rvol: trades.filter(t => t.rvol && t.rvol.length > 0).length
  };
  
  const overallScore = totalTrades > 0 ? 
    Math.round(Object.values(fieldCompleteness).reduce((sum, count) => sum + count, 0) / 
    (Object.keys(fieldCompleteness).length * totalTrades) * 100) : 0;
  
  const data = [
    ['Data Quality Score', `${overallScore}%`],
    [''],
    ['FIELD COMPLETENESS', 'Percentage', 'Missing', 'Status']
  ];
  
  Object.entries(fieldCompleteness).forEach(([field, count]) => {
    const percentage = totalTrades > 0 ? Math.round(count / totalTrades * 100) : 0;
    const missing = totalTrades - count;
    const status = percentage >= 90 ? 'Good' : percentage >= 70 ? 'Fair' : 'Poor';
    data.push([field, `${percentage}%`, missing, status]);
  });
  
  data.push(['']);
  data.push(['RECOMMENDATIONS']);
  
  // Add recommendations based on data quality
  if (overallScore < 70) {
    data.push(['⚠️ Data quality is below 70%. Run historical backfill to improve accuracy.']);
  }
  
  Object.entries(fieldCompleteness).forEach(([field, count]) => {
    const percentage = totalTrades > 0 ? Math.round(count / totalTrades * 100) : 0;
    if (percentage < 70) {
      data.push([`📊 ${field} is only ${percentage}% complete. Check data collection for this field.`]);
    }
  });
  
  if (data[data.length - 1][0] === 'RECOMMENDATIONS') {
    data.push(['✅ All fields have good data quality!']);
  }
  
  // Pad data array to ensure consistent columns
  const paddedData = padDataArray(data);
  sheet.getRange(1, 1, paddedData.length, paddedData[0].length).setValues(paddedData);
  
  // Format the sheet
  sheet.getRange(1, 1).setFontSize(14).setFontWeight('bold');
  sheet.getRange(3, 1, 1, 4).setFontWeight('bold').setBackground('#374151').setFontColor('white');
  sheet.autoResizeColumns(1, 4);
}

/**
 * Create Holding Period Analysis sheet
 */
function EW_createHoldingPeriodSheet(ss, insights) {
  const sheetName = 'SR_HoldingPeriod';
  let sheet = ss.getSheetByName(sheetName);
  
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
  } else {
    sheet.clear();
  }
  
  const trades = insights.allTrades || [];
  
  // Analyze performance by holding period
  const dayAnalysis = [];
  for (let day = 0; day <= 5; day++) {
    const dayTrades = trades.filter(t => t.profitDays && t.profitDays[day] !== undefined);
    const profitable = dayTrades.filter(t => t.profitDays[day] > 0);
    const hits = dayTrades.filter(t => t.strikeHit && t.strikeHit[day] && t.strikeHit[day] !== 'NO');
    
    if (dayTrades.length > 0) {
      const winners = profitable.map(t => t.profitDays[day]);
      const losers = dayTrades.filter(t => t.profitDays[day] <= 0).map(t => t.profitDays[day]);
      
      dayAnalysis.push({
        day: `Day ${day}`,
        totalObs: dayTrades.length,
        profitable: profitable.length,
        hitRate: (hits.length / dayTrades.length * 100).toFixed(1) + '%',
        profitableRate: (profitable.length / dayTrades.length * 100).toFixed(1) + '%',
        avgWin: winners.length > 0 ? (winners.reduce((a, b) => a + b, 0) / winners.length).toFixed(2) : 0,
        avgLoss: losers.length > 0 ? (losers.reduce((a, b) => a + b, 0) / losers.length).toFixed(2) : 0,
        profitFactor: losers.length > 0 && winners.length > 0 ? 
          Math.abs((winners.reduce((a, b) => a + b, 0) / losers.reduce((a, b) => a + b, 0))).toFixed(2) : 0,
        avgMove: dayTrades.map(t => t.profitDays[day]).reduce((a, b) => a + b, 0) / dayTrades.length
      });
    }
  }
  
  // Find best day
  const bestDay = dayAnalysis.reduce((best, current) => 
    parseFloat(current.profitableRate) > parseFloat(best.profitableRate) ? current : best
  , dayAnalysis[0] || {});
  
  const data = [
    ['OPTIMAL EXIT TIMING ANALYSIS'],
    ['Best Holding Day', bestDay.day || 'Day 1'],
    ['Profitable Rate at Best Day', bestDay.profitableRate || '0%'],
    ['Recommendation', `Exit positions on ${bestDay.day || 'Day 1'} for optimal results`],
    [''],
    ['DAY-BY-DAY PERFORMANCE', 'Total Obs', 'Profitable', 'Hit Rate', 'Profitable Rate', 'Avg Win', 'Avg Loss', 'Profit Factor', 'Avg Move']
  ];
  
  dayAnalysis.forEach(day => {
    data.push([
      day.day,
      day.totalObs,
      day.profitable,
      day.hitRate,
      day.profitableRate,
      day.avgWin,
      day.avgLoss,
      day.profitFactor,
      day.avgMove.toFixed(2)
    ]);
  });
  
  data.push(['']);
  data.push(['PROFIT DECAY ANALYSIS']);
  
  // Add decay analysis
  if (dayAnalysis.length >= 2) {
    const day0Profit = parseFloat(dayAnalysis[0].profitableRate);
    const day1Profit = parseFloat(dayAnalysis[1].profitableRate);
    const decayRate = day0Profit > 0 ? ((day0Profit - day1Profit) / day0Profit * 100).toFixed(1) : 0;
    
    data.push([`Profit decay from Day 0 to Day 1: ${decayRate}%`]);
    data.push([decayRate > 20 ? '⚠️ High decay rate suggests taking profits early' : '✅ Moderate decay rate allows for flexible exit timing']);
  }
  
  // Pad data array to ensure consistent columns
  const paddedData = padDataArray(data);
  sheet.getRange(1, 1, paddedData.length, paddedData[0].length).setValues(paddedData);
  
  // Format the sheet
  sheet.getRange(1, 1).setFontSize(14).setFontWeight('bold');
  sheet.getRange(6, 1, 1, 9).setFontWeight('bold').setBackground('#374151').setFontColor('white');
  sheet.autoResizeColumns(1, 9);
}

/**
 * Create Multi-Day Profitability sheet
 */
function EW_createMultiDaySheet(ss, multiDay) {
  const sheetName = 'SR_MultiDay';
  let sheet = ss.getSheetByName(sheetName);
  
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
  } else {
    sheet.clear();
  }
  
  const data = [
    ['TRADES PROFITABLE FOR MULTIPLE CONSECUTIVE DAYS'],
    ['Ticker', 'Strategy', 'Consecutive Days', 'Peak Day', 'Peak Value', 'Strike']
  ];
  
  // Add sustained profitable trades
  if (multiDay.sustainedProfitable && multiDay.sustainedProfitable.length > 0) {
    multiDay.sustainedProfitable.forEach(trade => {
      data.push([
        trade.ticker,
        trade.strategy,
        trade.consecutiveDays,
        `Day ${trade.peakDay}`,
        `${(Number(trade.peakValue) || 0).toFixed(2)}%`,
        trade.strike
      ]);
    });
  }
  
  data.push(['']);
  data.push(['PROFITABILITY BY DAY']);
  data.push(['Day', 'Total Trades', 'Profitable', 'Success Rate', 'Avg Profit']);
  
  // Add profitability by day
  if (multiDay.profitByDay) {
    multiDay.profitByDay.forEach(day => {
      data.push([
        `Day ${day.day}`,
        day.count,
        day.profitable,
        `${(day.rate * 100).toFixed(1)}%`,
        `${(Number(day.avgProfit) || 0).toFixed(2)}%`
      ]);
    });
  }
  
  // Pad data array to ensure consistent columns
  const paddedData = padDataArray(data);
  sheet.getRange(1, 1, paddedData.length, paddedData[0].length).setValues(paddedData);
  
  // Format the sheet
  sheet.getRange(1, 1).setFontSize(14).setFontWeight('bold');
  sheet.getRange(2, 1, 1, 6).setFontWeight('bold').setBackground('#374151').setFontColor('white');
  const profByDayRow = data.findIndex(row => row[0] === 'PROFITABILITY BY DAY') + 1;
  if (profByDayRow > 0) {
    sheet.getRange(profByDayRow + 1, 1, 1, 5).setFontWeight('bold').setBackground('#374151').setFontColor('white');
  }
  sheet.autoResizeColumns(1, 6);
}

/**
 * Create Indicator Effectiveness sheet
 */
function EW_createIndicatorsSheet(ss, indicators) {
  const sheetName = 'SR_Indicators';
  let sheet = ss.getSheetByName(sheetName);
  
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
  } else {
    sheet.clear();
  }
  
  const data = [
    ['HIGH IMPACT INDICATORS (Correlation > 0.15)'],
    ['Type', 'Indicator', 'Correlation', 'Data Completeness', 'Bullish Range', 'Bearish Range']
  ];
  
  const highImpact = [];
  const mediumImpact = [];
  
  // Sort indicators by correlation
  if (indicators) {
    Object.entries(indicators).forEach(([name, stats]) => {
      // Handle the actual data structure from EW_analyzeIndicatorEffectiveness
      const correlation = stats.correlationWithProfit || stats.correlation || 0;
      const dataCompleteness = stats.dataCompleteness || 
        (stats.dataPoints && stats.totalTrades ? 
          `${Math.round(stats.dataPoints / stats.totalTrades * 100)}%` : 'N/A');
      
      // Format profitable ranges if available
      let profitableRange = 'N/A';
      if (stats.profitableRanges) {
        if (stats.profitableRanges.bullish && stats.profitableRanges.bullish.count > 0) {
          profitableRange = `${(stats.profitableRanges.bullish.min || 0).toFixed(2)}-${(stats.profitableRanges.bullish.max || 0).toFixed(2)}`;
        } else if (stats.profitableRanges.bearish && stats.profitableRanges.bearish.count > 0) {
          profitableRange = `${(stats.profitableRanges.bearish.min || 0).toFixed(2)}-${(stats.profitableRanges.bearish.max || 0).toFixed(2)}`;
        }
      }
      
      const indicator = {
        type: name.includes('rsi') || name.includes('RSI') ? 'Momentum' : 
              name.includes('sma') || name.includes('SMA') || name.includes('vwap') || name.includes('VWAP') ? 'Trend' : 
              name.includes('rvol') || name.includes('RVOL') ? 'Volume' : 'Other',
        name: name.replace('hit_', '').replace('entry_', '').toUpperCase(),
        correlation: correlation,
        dataCompleteness: dataCompleteness,
        profitableRange: profitableRange,
        profitableRanges: stats.profitableRanges,
        hitRate: stats.hitRate || 0
      };
      
      if (Math.abs(indicator.correlation) > 0.15) {
        highImpact.push(indicator);
      } else if (Math.abs(indicator.correlation) > 0.05) {
        mediumImpact.push(indicator);
      }
    });
  }
  
  // Add high impact indicators
  highImpact.sort((a, b) => Math.abs(b.correlation) - Math.abs(a.correlation));
  highImpact.forEach(ind => {
    let bullishRange = 'N/A';
    let bearishRange = 'N/A';
    
    if (ind.profitableRanges) {
      if (ind.profitableRanges.bullish && ind.profitableRanges.bullish.count > 0) {
        bullishRange = `${(ind.profitableRanges.bullish.min || 0).toFixed(2)}-${(ind.profitableRanges.bullish.max || 0).toFixed(2)}`;
        if (ind.profitableRanges.bullish.avgProfit) {
          bullishRange += ` (${(ind.profitableRanges.bullish.avgProfit || 0).toFixed(1)}%)`;
        }
      }
      if (ind.profitableRanges.bearish && ind.profitableRanges.bearish.count > 0) {
        bearishRange = `${(ind.profitableRanges.bearish.min || 0).toFixed(2)}-${(ind.profitableRanges.bearish.max || 0).toFixed(2)}`;
        if (ind.profitableRanges.bearish.avgProfit) {
          bearishRange += ` (${(ind.profitableRanges.bearish.avgProfit || 0).toFixed(1)}%)`;
        }
      }
    }
    
    data.push([
      ind.type,
      ind.name,
      (Number(ind.correlation) || 0).toFixed(3),
      ind.dataCompleteness,
      bullishRange,
      bearishRange
    ]);
  });
  
  if (mediumImpact.length > 0) {
    data.push(['']);
    data.push(['MEDIUM IMPACT INDICATORS (Correlation 0.05-0.15)']);
    data.push(['Type', 'Indicator', 'Correlation', 'Data Completeness']);
    
    mediumImpact.forEach(ind => {
      data.push([
        ind.type,
        ind.name,
        (Number(ind.correlation) || 0).toFixed(3),
        ind.dataCompleteness
      ]);
    });
  }
  
  // Pad data array to ensure consistent columns
  const paddedData = padDataArray(data);
  sheet.getRange(1, 1, paddedData.length, paddedData[0].length).setValues(paddedData);
  
  // Format the sheet
  sheet.getRange(1, 1).setFontSize(14).setFontWeight('bold');
  sheet.getRange(2, 1, 1, 6).setFontWeight('bold').setBackground('#374151').setFontColor('white');
  
  const medRow = data.findIndex(row => row[0] === 'MEDIUM IMPACT INDICATORS (Correlation 0.05-0.15)') + 1;
  if (medRow > 1) {
    sheet.getRange(medRow, 1).setFontSize(14).setFontWeight('bold');
    sheet.getRange(medRow + 1, 1, 1, 4).setFontWeight('bold').setBackground('#374151').setFontColor('white');
  }
  
  sheet.autoResizeColumns(1, 6);
}

/**
 * Create Earnings Timing sheet
 */
function EW_createEarningsSheet(ss, earnings) {
  const sheetName = 'SR_Earnings';
  let sheet = ss.getSheetByName(sheetName);
  
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
  } else {
    sheet.clear();
  }
  
  const data = [
    ['EARNINGS TIMING ANALYSIS'],
    ['Total Trades with Earnings Data', earnings.earningsImpact?.tradesWithEarningsData || earnings.totalWithEarnings || 0],
    ['Pre-Earnings Trades', earnings.earningsImpact?.preEarningsHits || earnings.preEarnings?.count || 0],
    ['Post-Earnings Trades', earnings.earningsImpact?.postEarningsHits || earnings.postEarnings?.count || 0],
    [''],
    ['Pre-Earnings Hit Rate', earnings.earningsImpact?.preEarningsHitRate || `${((earnings.preEarnings?.hitRate || 0) * 100).toFixed(1)}%`],
    ['Post-Earnings Hit Rate', earnings.earningsImpact?.postEarningsHitRate || `${((earnings.postEarnings?.hitRate || 0) * 100).toFixed(1)}%`],
    [''],
    ['Optimal Days Before Earnings', earnings.earningsImpact?.optimalEntryWindow || earnings.optimalDays || '3-5 days'],
    ['Recommendation', earnings.earningsImpact?.recommendation || earnings.recommendation || 'Enter 2-4 days before earnings for best results'],
    [''],
    ['PERFORMANCE BY DAYS TO EARNINGS'],
    ['Window', 'Trades', 'Hits', 'Hit Rate', 'Avg Profit', 'Avg Days to Hit']
  ];
  
  // Add performance by days to earnings
  if (earnings.byDaysToEarnings) {
    Object.entries(earnings.byDaysToEarnings).forEach(([bucket, bucketData]) => {
      if (bucketData.trades > 0) {
        data.push([
          bucket + ' days',
          bucketData.trades,
          bucketData.hits,
          bucketData.hitRate.toFixed(1) + '%',
          bucketData.avgProfit > 0 ? (bucketData.avgProfit * 100).toFixed(2) + '%' : 'N/A',
          bucketData.avgDaysToHit > 0 ? bucketData.avgDaysToHit.toFixed(1) : 'N/A'
        ]);
      }
    });
  }
  
  data.push(['']);
  data.push(['PERFORMANCE BY RELEASE TIME']);
  data.push(['Release Time', 'Total', 'Hits', 'Hit Rate', 'Avg Profit', 'Avg Days']);
  
  // Add performance by release time
  if (earnings.byReleaseTime) {
    Object.entries(earnings.byReleaseTime).forEach(([time, stats]) => {
      data.push([
        time,
        stats.total || stats.count || 0,  // Check both field names
        stats.hits || 0,
        stats.hitRate ? `${stats.hitRate.toFixed(1)}%` : '0%',
        stats.avgProfit ? `${(stats.avgProfit * 100).toFixed(2)}%` : '0%',
        stats.avgDaysToHit ? stats.avgDaysToHit.toFixed(1) : '0'
      ]);
    });
  }
  
  // Pad data array to ensure consistent columns
  const paddedData = padDataArray(data);
  sheet.getRange(1, 1, paddedData.length, paddedData[0].length).setValues(paddedData);
  
  // Format the sheet
  sheet.getRange(1, 1).setFontSize(14).setFontWeight('bold');
  sheet.getRange(12, 1, 1, 6).setFontWeight('bold').setBackground('#374151').setFontColor('white');
  
  const releaseRow = data.findIndex(row => row[0] === 'PERFORMANCE BY RELEASE TIME') + 1;
  if (releaseRow > 1) {
    sheet.getRange(releaseRow, 1).setFontSize(12).setFontWeight('bold');
    sheet.getRange(releaseRow + 1, 1, 1, 6).setFontWeight('bold').setBackground('#374151').setFontColor('white');
  }
  
  sheet.autoResizeColumns(1, 6);
}

/**
 * Create Strategy Performance sheet - DEPRECATED: Combined with SR_Overview
 */
// function EW_createStrategiesSheet(ss, strategies) {
//   const sheetName = 'SR_Strategies';
//   let sheet = ss.getSheetByName(sheetName);
//   
//   if (!sheet) {
//     sheet = ss.insertSheet(sheetName);
//   } else {
//     sheet.clear();
//   }
//   
//   const data = [
//     ['STRATEGY PERFORMANCE COMPARISON'],
//     ['Strategy', 'Total Trades', 'Hit Count', 'Hit Rate', 'Avg Profit', 'Avg Loss', 'Profit Factor', 'Avg Days to Hit', 'Total Profit', 'Total Loss']
//   ];
//   
//   // Add strategy data sorted by hit rate
//   if (strategies) {
//     const sortedStrategies = Object.entries(strategies)
//       .sort((a, b) => (b[1].hitRate || 0) - (a[1].hitRate || 0));
//     
//     sortedStrategies.forEach(([strategy, stats]) => {
//       data.push([
//         strategy,
//         stats.totalTrades || stats.count || 0,  // Check both field names
//         stats.hitTrades || stats.hits || 0,      // Check both field names
//         `${((stats.hitRate || 0) * 100).toFixed(1)}%`,
//         `${((Number(stats.avgProfit) || 0) * 100).toFixed(2)}%`,  // Convert to percentage
//         `${((Number(stats.avgLoss) || 0) * 100).toFixed(2)}%`,    // Convert to percentage
//         (Number(stats.profitFactor) || 0).toFixed(2),
//         (Number(stats.avgDaysToHit) || 0).toFixed(1),
//         (Number(stats.totalProfit) || 0).toFixed(2),
//         (Number(stats.totalLoss) || 0).toFixed(2)
//       ]);
//     });
//   }
//   
//   // Pad data array to ensure consistent columns
//   const paddedData = padDataArray(data);
//   sheet.getRange(1, 1, paddedData.length, paddedData[0].length).setValues(paddedData);
//   
//   // Format the sheet
//   sheet.getRange(1, 1).setFontSize(14).setFontWeight('bold');
//   sheet.getRange(2, 1, 1, 10).setFontWeight('bold').setBackground('#374151').setFontColor('white');
//   sheet.autoResizeColumns(1, 10);
//   
//   // Apply conditional formatting to hit rate column
//   if (data.length > 2) {
//     const hitRateRange = sheet.getRange(3, 4, data.length - 2, 1);
//     
//     // Green for hit rate > 20%
//     const highRule = SpreadsheetApp.newConditionalFormatRule()
//       .whenTextContains('2')
//       .setBackground('#D4EDDA')
//       .setFontColor('#155724')
//       .setRanges([hitRateRange])
//       .build();
//     
//     // Yellow for hit rate 10-20%
//     const midRule = SpreadsheetApp.newConditionalFormatRule()
//       .whenTextContains('1')
//       .setBackground('#FFF3CD')
//       .setFontColor('#856404')
//       .setRanges([hitRateRange])
//       .build();
//     
//     sheet.setConditionalFormatRules([highRule, midRule]);
//   }
// }

/**
 * Create Top Plays sheet
 */
function EW_createTopPlaysSheet(ss, topPlays) {
  const sheetName = 'SR_TopPlays';
  let sheet = ss.getSheetByName(sheetName);
  
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
  } else {
    sheet.clear();
  }
  
  const data = [
    ['TOP 20 WINNING PLAYS'],
    ['Rank', 'Ticker', 'Strategy', 'Entry Date', 'Strike', 'Hit Price', 'Max Profit %', 'Days to Hit', 'Risk/Reward', 'Profitable Days']
  ];
  
  // Add top plays
  if (topPlays && topPlays.length > 0) {
    topPlays.slice(0, 20).forEach((play, index) => {
      data.push([
        index + 1,
        play.symbol,
        play.strategy,
        play.entryDate,
        play.strike,
        play.hitPrice || 'N/A',
        `${(Number(play.maxProfit) || 0).toFixed(2)}%`,
        play.daysToHit || 'N/A',
        (Number(play.riskReward) || 0).toFixed(2),
        play.profitableDays || 0
      ]);
    });
  }
  
  data.push(['']);
  data.push(['INDICATOR PROFILES (TOP 5)']);
  data.push(['Rank', 'Ticker', 'Indicator Values at Entry', 'Multi-Day Performance']);
  
  // Add indicator profiles for top 5
  if (topPlays && topPlays.length > 0) {
    topPlays.slice(0, 5).forEach((play, index) => {
      const indicators = [];
      if (play.rsi) indicators.push(`RSI: ${(Number(play.rsi) || 0).toFixed(1)}`);
      if (play.priceVsSMA20) indicators.push(`SMA20: ${(Number(play.priceVsSMA20) || 0).toFixed(2)}%`);
      if (play.rvol) indicators.push(`RVOL: ${(Number(play.rvol) || 0).toFixed(2)}`);
      
      const multiDay = [];
      if (play.profitDays) {
        play.profitDays.forEach((profit, day) => {
          if (profit > 0) multiDay.push(`Day ${day}: ${(Number(profit) || 0).toFixed(2)}%`);
        });
      }
      
      data.push([
        index + 1,
        play.symbol,
        indicators.join(', ') || 'N/A',
        multiDay.join(', ') || 'N/A'
      ]);
    });
  }
  
  // Pad data array to ensure consistent columns
  const paddedData = padDataArray(data);
  sheet.getRange(1, 1, paddedData.length, paddedData[0].length).setValues(paddedData);
  
  // Format the sheet
  sheet.getRange(1, 1).setFontSize(14).setFontWeight('bold');
  sheet.getRange(2, 1, 1, 10).setFontWeight('bold').setBackground('#374151').setFontColor('white');
  
  const indicatorRow = data.findIndex(row => row[0] === 'INDICATOR PROFILES (TOP 5)') + 1;
  if (indicatorRow > 1) {
    sheet.getRange(indicatorRow, 1).setFontSize(12).setFontWeight('bold');
    sheet.getRange(indicatorRow + 1, 1, 1, 4).setFontWeight('bold').setBackground('#374151').setFontColor('white');
  }
  
  sheet.autoResizeColumns(1, 10);
}

/**
 * Create Risk/Reward Analysis sheet
 */
function EW_createRiskRewardSheet(ss, riskReward) {
  const sheetName = 'SR_RiskReward';
  let sheet = ss.getSheetByName(sheetName);
  
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
  } else {
    sheet.clear();
  }
  
  const data = [
    ['RISK/REWARD PATTERN ANALYSIS'],
    ['Average Risk/Reward Ratio', (riskReward.avgRiskReward || 0).toFixed(2)],
    ['Median Risk/Reward Ratio', (riskReward.medianRiskReward || 0).toFixed(2)],
    ['Best Risk/Reward Ratio', (riskReward.bestRiskReward || 0).toFixed(2)],
    ['Worst Risk/Reward Ratio', (riskReward.worstRiskReward || 0).toFixed(2)],
    [''],
    ['Trades with R/R > 2.0', riskReward.highRRCount || 0],
    ['Trades with R/R 1.0-2.0', riskReward.mediumRRCount || 0],
    ['Trades with R/R < 1.0', riskReward.lowRRCount || 0],
    [''],
    ['RISK/REWARD DISTRIBUTION'],
    ['Range', 'Count', 'Percentage']
  ];
  
  // Add distribution data
  if (riskReward.distribution) {
    const ranges = ['< 0.5', '0.5-1.0', '1.0-1.5', '1.5-2.0', '2.0-3.0', '> 3.0'];
    ranges.forEach(range => {
      const count = riskReward.distribution[range] || 0;
      const percentage = riskReward.totalTrades > 0 ? 
        (count / riskReward.totalTrades * 100).toFixed(1) + '%' : '0%';
      data.push([range, count, percentage]);
    });
  }
  
  // Pad data array to ensure consistent columns
  const paddedData = padDataArray(data);
  sheet.getRange(1, 1, paddedData.length, paddedData[0].length).setValues(paddedData);
  
  // Format the sheet
  sheet.getRange(1, 1).setFontSize(14).setFontWeight('bold');
  sheet.getRange(11, 1, 1, 3).setFontWeight('bold').setBackground('#374151').setFontColor('white');
  sheet.autoResizeColumns(1, 3);
}