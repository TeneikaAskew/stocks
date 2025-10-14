/**
 * Web App Debug Tools
 * Run these functions to diagnose web app data issues
 */

/**
 * Check all sheets and their data
 */
function debugCheckAllSheets() {
  const ss = SpreadsheetApp.getActive();
  const output = [];

  output.push('=== STRATEGY SHEETS ===\n');
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS || {});
  if (strategies.length === 0) {
    output.push('WARNING: No strategies found in EW.STRATEGY_ENDPOINTS\n');
  }

  strategies.forEach(strategy => {
    const sheet = ss.getSheetByName(strategy);
    if (!sheet) {
      output.push(`❌ ${strategy}: MISSING\n`);
    } else {
      const rows = sheet.getLastRow() - 1; // Exclude header
      output.push(`✅ ${strategy}: ${rows} positions\n`);

      // Check for Strike_Hit column
      const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      const hasStrikeHit = headers.some(h => h === 'Strike_Hit');
      const hasMaxFav = headers.some(h => h === 'Max_Favorable');
      const hasExpResult = headers.some(h => h === 'Exp_Result');

      if (!hasStrikeHit) output.push(`   ⚠️ Missing Strike_Hit column\n`);
      if (!hasMaxFav) output.push(`   ⚠️ Missing Max_Favorable column\n`);
      if (!hasExpResult) output.push(`   ⚠️ Missing Exp_Result column\n`);
    }
  });

  output.push('\n=== SUCCESS REPORT SHEETS ===\n');
  const srSheets = ['SR_Overview', 'SR_Indicators', 'SR_Strategies', 'SR_TopPlays',
                    'SR_MultiDay', 'SR_Earnings', 'SR_RiskReward', 'SR_DataQuality'];

  srSheets.forEach(name => {
    const sheet = ss.getSheetByName(name);
    if (!sheet) {
      output.push(`❌ ${name}: MISSING\n`);
    } else {
      const rows = sheet.getLastRow();
      const cols = sheet.getLastColumn();
      output.push(`✅ ${name}: ${rows} rows x ${cols} cols\n`);

      // Show headers
      if (rows > 0 && cols > 0) {
        const headers = sheet.getRange(1, 1, 1, Math.min(cols, 10)).getValues()[0];
        output.push(`   Headers: ${headers.filter(h => h).join(', ')}\n`);

        // Show first data row if it exists
        if (rows > 1) {
          const firstRow = sheet.getRange(2, 1, 1, Math.min(cols, 5)).getValues()[0];
          output.push(`   First row: ${firstRow.map(v => v || '(empty)').join(' | ')}\n`);
        }
      }
    }
  });

  const result = output.join('');
  console.log(result);
  Logger.log(result);

  // Also try to show in UI
  if (EW_isSpreadsheetEnvironment()) {
    const ui = SpreadsheetApp.getUi();
    ui.alert('Sheet Debug Info', result, ui.ButtonSet.OK);
  }

  return result;
}

/**
 * Test the web app data collection
 */
function debugTestWebAppData() {
  const output = [];

  output.push('=== TESTING WEB APP DATA COLLECTION ===\n\n');

  try {
    output.push('Testing getSuccessReportDataForWeb()...\n');
    const data = getSuccessReportDataForWeb();

    output.push(`\n📊 OVERVIEW:\n`);
    output.push(`  Total Trades: ${data.overview?.totalTrades || 0}\n`);
    output.push(`  Hit Rate: ${(data.overview?.hitRate * 100 || 0).toFixed(1)}%\n`);
    output.push(`  Profitable Rate: ${(data.overview?.profitableRate * 100 || 0).toFixed(1)}%\n`);
    output.push(`  Avg Risk/Reward: ${data.overview?.avgRiskReward || 0}\n`);

    output.push(`\n📈 STRATEGIES:\n`);
    if (data.strategyPerformance && data.strategyPerformance.length > 0) {
      data.strategyPerformance.forEach(s => {
        output.push(`  ${s.strategy}: ${s.totalTrades || 0} trades, ${(s.hitRate * 100).toFixed(1)}% hit rate\n`);
      });
    } else {
      output.push(`  ❌ NO STRATEGY DATA\n`);
    }

    output.push(`\n🎯 TOP PLAYS:\n`);
    if (data.topPlays && data.topPlays.length > 0) {
      data.topPlays.slice(0, 5).forEach((p, i) => {
        output.push(`  ${i+1}. ${p.ticker || 'undefined'} - ${p.strategy || 'N/A'} - ${(p.maxProfit * 100).toFixed(2)}%\n`);
      });
    } else {
      output.push(`  ❌ NO TOP PLAYS DATA\n`);
    }

    output.push(`\n📊 INDICATORS:\n`);
    if (data.indicatorEffectiveness && data.indicatorEffectiveness.length > 0) {
      data.indicatorEffectiveness.slice(0, 5).forEach(ind => {
        output.push(`  ${ind.name}: Correlation ${ind.correlation.toFixed(3)}, Hit Rate ${(ind.hitRate * 100).toFixed(1)}%\n`);
      });
    } else {
      output.push(`  ❌ NO INDICATOR DATA\n`);
    }

    output.push(`\n📅 MULTI-DAY:\n`);
    if (data.multiDayProfitability?.profitabilityByDay && data.multiDayProfitability.profitabilityByDay.length > 0) {
      output.push(`  ${data.multiDayProfitability.profitabilityByDay.length} days of data\n`);
    } else {
      output.push(`  ❌ NO MULTI-DAY DATA\n`);
    }

  } catch (error) {
    output.push(`\n❌ ERROR: ${error.toString()}\n`);
    output.push(`Stack: ${error.stack}\n`);
  }

  const result = output.join('');
  console.log(result);
  Logger.log(result);

  if (EW_isSpreadsheetEnvironment()) {
    const ui = SpreadsheetApp.getUi();
    ui.alert('Web App Data Test', result, ui.ButtonSet.OK);
  }

  return result;
}

/**
 * Check specific SR sheet structure
 */
function debugCheckSRSheet(sheetName) {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getSheetByName(sheetName);

  if (!sheet) {
    Logger.log(`Sheet ${sheetName} does not exist`);
    return;
  }

  const data = sheet.getDataRange().getValues();
  Logger.log(`\n=== ${sheetName} ===`);
  Logger.log(`Dimensions: ${data.length} rows x ${data[0].length} columns`);
  Logger.log('\nFirst 5 rows:');

  data.slice(0, 5).forEach((row, i) => {
    Logger.log(`Row ${i}: ${row.slice(0, 10).map(v => v || '(empty)').join(' | ')}`);
  });
}

/**
 * Force regenerate success report and test
 */
function debugForceRegenAndTest() {
  const output = [];

  output.push('=== FORCING SUCCESS REPORT REGENERATION ===\n\n');

  try {
    output.push('Step 1: Generating success report...\n');
    EW_generateSuccessReport();
    output.push('✅ Success report generated\n\n');

    output.push('Step 2: Checking SR sheets...\n');
    const ss = SpreadsheetApp.getActive();
    const srSheets = ['SR_Overview', 'SR_TopPlays', 'SR_Indicators', 'SR_Strategies'];

    srSheets.forEach(name => {
      const sheet = ss.getSheetByName(name);
      if (sheet) {
        output.push(`  ✅ ${name}: ${sheet.getLastRow()} rows\n`);
      } else {
        output.push(`  ❌ ${name}: MISSING\n`);
      }
    });

    output.push('\nStep 3: Testing web app data...\n');
    const data = getSuccessReportDataForWeb();
    output.push(`  Strategies: ${data.strategyPerformance?.length || 0}\n`);
    output.push(`  Top Plays: ${data.topPlays?.length || 0}\n`);
    output.push(`  Indicators: ${data.indicatorEffectiveness?.length || 0}\n`);

  } catch (error) {
    output.push(`\n❌ ERROR: ${error.toString()}\n`);
  }

  const result = output.join('');
  console.log(result);
  Logger.log(result);

  if (EW_isSpreadsheetEnvironment()) {
    const ui = SpreadsheetApp.getUi();
    ui.alert('Regeneration Test', result, ui.ButtonSet.OK);
  }

  return result;
}

/**
 * Check what data is actually in stored properties
 */
function debugCheckStoredData() {
  const scriptProperties = PropertiesService.getScriptProperties();
  const stored = scriptProperties.getProperty('SUCCESS_REPORT_DATA');

  if (!stored) {
    Logger.log('No stored SUCCESS_REPORT_DATA found');
    return;
  }

  try {
    const data = JSON.parse(stored);
    Logger.log('\n=== STORED DATA SUMMARY ===');
    Logger.log(`Last Updated: ${data.lastUpdated || 'Unknown'}`);
    Logger.log(`Overview Total Trades: ${data.overview?.totalTrades || 0}`);
    Logger.log(`Strategy Performance: ${data.strategyPerformance?.length || 0} strategies`);
    Logger.log(`Top Plays: ${data.topPlays?.length || 0} plays`);
    Logger.log(`Indicators: ${data.indicatorEffectiveness?.length || 0} indicators`);

    // Show first top play to check ticker
    if (data.topPlays && data.topPlays.length > 0) {
      Logger.log('\nFirst Top Play:');
      Logger.log(JSON.stringify(data.topPlays[0], null, 2));
    }

  } catch (error) {
    Logger.log(`Error parsing stored data: ${error}`);
  }
}

/**
 * Clear stored data and force fresh collection
 */
function debugClearAndRecollect() {
  Logger.log('Clearing stored data...');
  const scriptProperties = PropertiesService.getScriptProperties();
  scriptProperties.deleteProperty('SUCCESS_REPORT_DATA');
  scriptProperties.deleteProperty('SUCCESS_REPORT_TIMESTAMP');

  Logger.log('Regenerating success report...');
  EW_generateSuccessReport();

  Logger.log('Collecting fresh data...');
  const data = collectFreshReportData();

  Logger.log('\n=== FRESH DATA SUMMARY ===');
  Logger.log(`Top Plays: ${data.topPlays?.length || 0}`);
  if (data.topPlays && data.topPlays.length > 0) {
    Logger.log('First 3 top plays:');
    data.topPlays.slice(0, 3).forEach((p, i) => {
      Logger.log(`  ${i+1}. Ticker: ${p.ticker || 'undefined'}, Strategy: ${p.strategy}, Profit: ${p.maxProfit}`);
    });
  }

  Logger.log(`\nStrategies: ${data.strategyPerformance?.length || 0}`);
  if (data.strategyPerformance && data.strategyPerformance.length > 0) {
    data.strategyPerformance.forEach(s => {
      Logger.log(`  ${s.strategy}: ${s.totalTrades} trades`);
    });
  }

  return data;
}
