/**
 * Debug function to test why certain columns aren't updating
 */
function EW_debugBackfillIssue() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const range = sheet.getActiveRange();
  
  if (!range || range.getRow() === 1) {
    SpreadsheetApp.getUi().alert('Please select a data row (not header)');
    return;
  }
  
  const rowNum = range.getRow();
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  const rowData = sheet.getRange(rowNum, 1, 1, sheet.getLastColumn()).getValues()[0];
  
  console.log('=== DEBUG BACKFILL ISSUE ===');
  console.log(`Selected row: ${rowNum}`);
  console.log(`Sheet: ${sheet.getName()}`);
  
  // Log column mappings
  console.log('\nColumn Mappings:');
  console.log(`  Exp_Result column: ${hdrMap.expResultCol}`);
  console.log(`  Risk_Reward column: ${hdrMap.riskRewardCol}`);
  console.log(`  Days_To_Exp column: ${hdrMap.daysToExpCol}`);
  
  // Get row data
  const ticker = hdrMap.tickerCol ? rowData[hdrMap.tickerCol - 1] : null;
  const runDate = hdrMap.runDateCol ? rowData[hdrMap.runDateCol - 1] : null;
  const strike = hdrMap.strikeCol ? parseFloat(rowData[hdrMap.strikeCol - 1]) : null;
  const expDate = hdrMap.expDateCol ? rowData[hdrMap.expDateCol - 1] : null;
  const daysToExp = hdrMap.daysToExpCol ? rowData[hdrMap.daysToExpCol - 1] : null;
  
  console.log('\nRow Data:');
  console.log(`  Ticker: ${ticker}`);
  console.log(`  Run Date: ${runDate} (type: ${typeof runDate})`);
  console.log(`  Strike: ${strike}`);
  console.log(`  Exp Date: ${expDate} (type: ${typeof expDate})`);
  console.log(`  Days to Exp: ${daysToExp}`);
  
  // Check existing values
  const existingExpResult = hdrMap.expResultCol ? rowData[hdrMap.expResultCol - 1] : null;
  const existingRiskReward = hdrMap.riskRewardCol ? rowData[hdrMap.riskRewardCol - 1] : null;
  const existingMaxFav = hdrMap.maxFavorableCol ? rowData[hdrMap.maxFavorableCol - 1] : null;
  const existingMinUnfav = hdrMap.minUnfavorableCol ? rowData[hdrMap.minUnfavorableCol - 1] : null;
  
  console.log('\nExisting Values:');
  console.log(`  Exp_Result: "${existingExpResult}" (empty: ${!existingExpResult})`);
  console.log(`  Risk_Reward: "${existingRiskReward}" (empty: ${!existingRiskReward})`);
  console.log(`  Max_Favorable: "${existingMaxFav}"`);
  console.log(`  Min_Unfavorable: "${existingMinUnfav}"`);
  
  // Run backfill analysis
  if (ticker && runDate && strike) {
    console.log('\nRunning backfill analysis...');
    const analysis = EW_backfillSinglePosition(ticker, sheet.getName(), strike, runDate, expDate);
    
    console.log('\nAnalysis Results:');
    console.log(`  expResult: ${analysis.expResult}`);
    console.log(`  maxFavorableArray: ${JSON.stringify(analysis.maxFavorableArray)}`);
    console.log(`  minUnfavorableArray: ${JSON.stringify(analysis.minUnfavorableArray)}`);
    console.log(`  strikeHitArray: ${JSON.stringify(analysis.strikeHitArray)}`);
    console.log(`  historicalHigh: ${analysis.historicalHigh}`);
    console.log(`  historicalLow: ${analysis.historicalLow}`);
    
    // Test date comparison
    const expDateObj = expDate ? new Date(expDate) : null;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    console.log('\nDate Comparison:');
    console.log(`  expDate as Date: ${expDateObj}`);
    console.log(`  Today: ${today}`);
    console.log(`  Is expired: ${expDateObj && expDateObj <= today}`);
    
    // Test shouldUpdate logic
    const shouldUpdateExpResult = !existingExpResult || existingExpResult === '';
    const shouldUpdateRiskReward = !existingRiskReward || existingRiskReward === '';
    
    console.log('\nShould Update Logic:');
    console.log(`  Should update Exp_Result: ${shouldUpdateExpResult}`);
    console.log(`  Should update Risk_Reward: ${shouldUpdateRiskReward}`);
    
    // Test risk/reward calculation
    if (analysis.maxFavorableArray && analysis.minUnfavorableArray && 
        analysis.maxFavorableArray.length > 0 && analysis.minUnfavorableArray.length > 0) {
      const maxFav = Math.max(...analysis.maxFavorableArray.map(v => parseFloat(v)));
      const maxUnfav = Math.max(...analysis.minUnfavorableArray.map(v => parseFloat(v)));
      console.log('\nRisk/Reward Calculation:');
      console.log(`  Max Favorable: ${maxFav}`);
      console.log(`  Max Unfavorable: ${maxUnfav}`);
      console.log(`  Risk/Reward: ${maxUnfav > 0 ? (maxFav / maxUnfav).toFixed(2) : 'N/A'}`);
    }
    
    // Try updating with the centralized function
    console.log('\n=== Testing Centralized Update Function ===');
    const wasUpdated = EW_updateBackfillColumns(sheet, rowNum, analysis, hdrMap, ticker, expDateObj, rowData);
    console.log(`Update result: ${wasUpdated}`);
    
    // Force flush
    SpreadsheetApp.flush();
    
    // Check values after update
    const newRowData = sheet.getRange(rowNum, 1, 1, sheet.getLastColumn()).getValues()[0];
    const newExpResult = hdrMap.expResultCol ? newRowData[hdrMap.expResultCol - 1] : null;
    const newRiskReward = hdrMap.riskRewardCol ? newRowData[hdrMap.riskRewardCol - 1] : null;
    
    console.log('\nValues After Update:');
    console.log(`  Exp_Result: "${newExpResult}" (changed: ${newExpResult !== existingExpResult})`);
    console.log(`  Risk_Reward: "${newRiskReward}" (changed: ${newRiskReward !== existingRiskReward})`);
    
  } else {
    console.log('\nMissing required data for backfill');
  }
  
  console.log('\n=== END DEBUG ===');
}

/**
 * Add debug function to menu
 */
function EW_addDebugMenu() {
  const ui = SpreadsheetApp.getUi();
  const menu = ui.createMenu('Debug Backfill');
  menu.addItem('Debug Selected Row', 'EW_debugBackfillIssue');
  menu.addToUi();
}