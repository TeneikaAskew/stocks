/**
 * Debug function to understand Success Report data issues
 */
function EW_debugSuccessReport() {
  console.log('=== DEBUGGING SUCCESS REPORT DATA ISSUES ===');
  
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getSheetByName('Long Calls');
  if (!sheet) {
    console.log('No Long Calls sheet found');
    return;
  }
  
  // Get header mapping
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Sample a few rows
  const data = sheet.getRange(2, 1, Math.min(5, sheet.getLastRow() - 1), sheet.getLastColumn()).getValues();
  
  console.log('\n=== SAMPLE DATA ANALYSIS ===');
  data.forEach((row, idx) => {
    console.log(`\nRow ${idx + 2}:`);
    const ticker = row[hdrMap.tickerCol - 1];
    const strike = parseFloat(row[hdrMap.strikeCol - 1]) || parseFloat(row[hdrMap.longStrikeCol - 1]) || 0;
    const maxFavArray = EW_parseArrayFromCell(row[hdrMap.maxFavorableCol - 1]);
    const strikeHitArray = EW_parseArrayFromCell(row[hdrMap.strikeHitCol - 1]);
    const nextEPSDate = row[hdrMap.nextEPSDateCol - 1];
    const releaseTime = row[hdrMap.releaseTimeCol - 1];
    const company = row[hdrMap.companyCol - 1];
    
    console.log(`  Ticker: ${ticker}`);
    console.log(`  Strike: ${strike}`);
    console.log(`  Company: ${company} (is empty: ${!company || company === ''})`);
    console.log(`  NextEPSDate: ${nextEPSDate} (type: ${typeof nextEPSDate}, is empty: ${!nextEPSDate})`);
    console.log(`  ReleaseTime: ${releaseTime} (type: ${typeof releaseTime}, value: ${releaseTime === 0 ? 'zero' : releaseTime})`);
    console.log(`  Max Favorable Array: ${JSON.stringify(maxFavArray)}`);
    console.log(`  Strike Hit Array: ${JSON.stringify(strikeHitArray)}`);
    
    // Calculate max favorable value
    const maxFavValue = Math.max(...maxFavArray.filter(v => v !== null).map(v => parseFloat(v) || 0));
    console.log(`  Max Favorable Value: ${maxFavValue} (as %: ${(maxFavValue * 100).toFixed(2)}%)`);
    
    // Check if this could produce extreme percentages
    if (maxFavValue > 10) {
      console.log(`  ⚠️ EXTREME VALUE DETECTED! This would show as ${(maxFavValue * 100).toFixed(2)}%`);
    }
    
    // Test hit price calculation
    const firstHitIndex = strikeHitArray.findIndex(val => val !== null && val !== undefined && val !== "");
    if (firstHitIndex !== -1) {
      const pctMove = parseFloat(strikeHitArray[firstHitIndex]);
      const hitPrice = strike * (1 + pctMove);
      console.log(`  First hit on day ${firstHitIndex}: pctMove=${pctMove}, hitPrice=${hitPrice.toFixed(2)}`);
      
      if (pctMove > 10) {
        console.log(`  ⚠️ EXTREME PERCENTAGE MOVE: ${pctMove} (${(pctMove * 100).toFixed(2)}%)`);
      }
    }
  });
  
  // Check earnings data detection
  console.log('\n=== EARNINGS DATA CHECK ===');
  let tradesWithEPS = 0;
  let tradesWithRelease = 0;
  let tradesWithBoth = 0;
  
  const allData = sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).getValues();
  allData.forEach(row => {
    const eps = row[hdrMap.nextEPSDateCol - 1];
    const release = row[hdrMap.releaseTimeCol - 1];
    
    if (eps && eps !== '') tradesWithEPS++;
    if (release && release !== 0) tradesWithRelease++;
    if (eps && eps !== '' && release && release !== 0) tradesWithBoth++;
  });
  
  console.log(`Total rows: ${allData.length}`);
  console.log(`Rows with EPS date: ${tradesWithEPS} (${(tradesWithEPS/allData.length*100).toFixed(1)}%)`);
  console.log(`Rows with Release time: ${tradesWithRelease} (${(tradesWithRelease/allData.length*100).toFixed(1)}%)`);
  console.log(`Rows with both: ${tradesWithBoth} (${(tradesWithBoth/allData.length*100).toFixed(1)}%)`);
}

/**
 * Test max favorable calculation
 */
function EW_testMaxFavorableCalculation() {
  console.log('=== TESTING MAX FAVORABLE CALCULATION ===');
  
  // Test case 1: Long Call with strike 172.50, day high 178.13
  const strike1 = 172.50;
  const dayHigh1 = 178.13;
  const maxFav1 = EW_calculateMaxFavorableForDay('Long Calls', strike1, dayHigh1, 0);
  console.log(`\nTest 1: Long Call, Strike=${strike1}, DayHigh=${dayHigh1}`);
  console.log(`  Calculation: (${dayHigh1} - ${strike1}) / ${strike1} = ${maxFav1}`);
  console.log(`  As percentage: ${(parseFloat(maxFav1) * 100).toFixed(2)}%`);
  console.log(`  Expected: ~3.26%`);
  
  // Test case 2: Check if values are being stored incorrectly
  const strike2 = 710.00;
  const dayHigh2 = 720.09;
  const maxFav2 = EW_calculateMaxFavorableForDay('Long Calls', strike2, dayHigh2, 0);
  console.log(`\nTest 2: Long Call, Strike=${strike2}, DayHigh=${dayHigh2}`);
  console.log(`  Calculation: (${dayHigh2} - ${strike2}) / ${strike2} = ${maxFav2}`);
  console.log(`  As percentage: ${(parseFloat(maxFav2) * 100).toFixed(2)}%`);
  console.log(`  Expected: ~1.42%`);
  
  // Test what could cause 1642%
  console.log('\n=== REVERSE ENGINEERING EXTREME VALUES ===');
  
  // For 1642% (16.42 as decimal), with strike 172.50
  const extremePct1 = 16.42;
  const impliedHigh1 = 172.50 * (1 + extremePct1);
  console.log(`\nFor 1642% profit with strike 172.50:`);
  console.log(`  Implied day high would be: ${impliedHigh1.toFixed(2)}`);
  console.log(`  This is unrealistic for a day move!`);
  
  // Check if the value might already be a percentage
  const possibleStoredValue = 178.13 - 172.50; // 5.63
  console.log(`\nPossible stored value issue:`);
  console.log(`  If storing price difference: ${possibleStoredValue}`);
  console.log(`  As percentage of strike: ${(possibleStoredValue / 172.50 * 100).toFixed(2)}%`);
  
  // Most likely issue: Values are stored as percentages (3.26) instead of decimals (0.0326)
  console.log(`\n⚠️ MOST LIKELY ISSUE:`);
  console.log(`  If backfill stored 3.26 instead of 0.0326:`);
  console.log(`  Success Report would show: ${(3.26 * 100).toFixed(2)}% = 326%`);
  console.log(`  If backfill stored 16.42 instead of 0.1642:`);
  console.log(`  Success Report would show: ${(16.42 * 100).toFixed(2)}% = 1642%`);
  console.log(`\n  SOLUTION: The backfill process needs to store decimals, not percentages!`);
}

/**
 * Check actual spreadsheet data format
 */
function EW_checkDataFormat() {
  console.log('=== CHECKING ACTUAL DATA FORMAT IN SPREADSHEET ===');
  
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getSheetByName('Long Calls');
  if (!sheet) return;
  
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Find a row with extreme values
  const data = sheet.getRange(2, 1, Math.min(20, sheet.getLastRow() - 1), sheet.getLastColumn()).getValues();
  
  console.log('\nLooking for trades with large max favorable values...');
  
  data.forEach((row, idx) => {
    const maxFavArray = EW_parseArrayFromCell(row[hdrMap.maxFavorableCol - 1]);
    const maxValue = Math.max(...maxFavArray.filter(v => v !== null).map(v => parseFloat(v) || 0));
    
    if (maxValue > 1) {  // Values greater than 1 are likely percentages
      const ticker = row[hdrMap.tickerCol - 1];
      const strike = parseFloat(row[hdrMap.strikeCol - 1]) || parseFloat(row[hdrMap.longStrikeCol - 1]) || 0;
      
      console.log(`\nRow ${idx + 2} (${ticker}):`);
      console.log(`  Strike: ${strike}`);
      console.log(`  Max Favorable Array: ${JSON.stringify(maxFavArray)}`);
      console.log(`  Max Value: ${maxValue}`);
      console.log(`  If decimal: ${(maxValue * 100).toFixed(2)}% profit`);
      console.log(`  If already %: ${maxValue.toFixed(2)}% profit`);
      console.log(`  ⚠️ This appears to be stored as a percentage, not a decimal!`);
    }
  });
}