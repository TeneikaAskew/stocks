/**
 * Debug function to investigate why strikeHit arrays have missing values
 */
function EW_debugStrikeHitIssue() {
  console.log('=== DEBUGGING STRIKE HIT ARRAY ISSUE ===');
  
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Strategy_Tracking');
  if (!sheet) {
    console.log('Strategy_Tracking sheet not found');
    return;
  }
  
  const dataRange = sheet.getDataRange();
  const data = dataRange.getValues();
  const headers = data[0];
  const hdrMap = EW_getHeaderMap(headers);
  
  // Check first 20 rows
  let totalRows = 0;
  let rowsWithStrikeHit = 0;
  let rowsWithFullArray = 0;
  let rowsWithPartialArray = 0;
  let rowsWithNoData = 0;
  
  console.log('\n=== Analyzing Strike_Hit Arrays ===');
  
  for (let i = 1; i <= Math.min(20, data.length - 1); i++) {
    const row = data[i];
    const ticker = row[hdrMap.tickerCol - 1];
    const runDate = row[hdrMap.runDateCol - 1];
    const strategy = row[hdrMap.strategyCol - 1];
    const strike = parseFloat(row[hdrMap.strikeCol - 1]) || parseFloat(row[hdrMap.longStrikeCol - 1]) || 0;
    const strikeHitRaw = row[hdrMap.strikeHitCol - 1];
    const expDate = row[hdrMap.expDateCol - 1];
    const firstHitDate = row[hdrMap.firstHitDateCol - 1];
    
    if (!ticker) continue;
    
    totalRows++;
    
    // Parse the Strike_Hit array
    let strikeHitArray = [];
    try {
      if (strikeHitRaw && typeof strikeHitRaw === 'string') {
        if (strikeHitRaw.startsWith('[')) {
          strikeHitArray = JSON.parse(strikeHitRaw);
        } else if (strikeHitRaw === 'NO_DATA') {
          strikeHitArray = ['NO_DATA'];
        }
      }
    } catch (e) {
      console.log(`Row ${i}: Error parsing Strike_Hit array: ${e.message}`);
    }
    
    // Analyze the array
    const nonNullValues = strikeHitArray.filter(v => v !== null && v !== undefined && v !== "");
    const hasAnyHit = nonNullValues.length > 0;
    const arrayLength = strikeHitArray.length;
    
    if (hasAnyHit) rowsWithStrikeHit++;
    if (arrayLength === 6 && nonNullValues.length === 6) rowsWithFullArray++;
    else if (arrayLength > 0 && nonNullValues.length < arrayLength) rowsWithPartialArray++;
    
    if (strikeHitRaw === 'NO_DATA' || strikeHitArray[0] === 'NO_DATA') {
      rowsWithNoData++;
    }
    
    // Log details for rows with issues
    if (arrayLength < 6 || nonNullValues.length < arrayLength) {
      console.log(`\nRow ${i} - ${ticker}:`);
      console.log(`  Run Date: ${runDate}`);
      console.log(`  Exp Date: ${expDate}`);
      console.log(`  Strategy: ${strategy}`);
      console.log(`  Strike: ${strike}`);
      console.log(`  First Hit Date: ${firstHitDate || 'Not hit'}`);
      console.log(`  Array Length: ${arrayLength}`);
      console.log(`  Non-null values: ${nonNullValues.length}`);
      console.log(`  Array contents: ${JSON.stringify(strikeHitArray)}`);
      
      // Calculate days since run date to understand the issue
      if (runDate) {
        const runDateObj = new Date(runDate);
        const today = new Date();
        const daysSinceRun = Math.floor((today - runDateObj) / (1000 * 60 * 60 * 24));
        console.log(`  Days since run: ${daysSinceRun}`);
        
        // Check if position is still active
        if (expDate) {
          const expDateObj = new Date(expDate);
          const isExpired = expDateObj < today;
          console.log(`  Status: ${isExpired ? 'EXPIRED' : 'ACTIVE'}`);
          
          if (!isExpired) {
            // For active positions, calculate expected array length
            const tradingDaysSinceRun = Math.min(daysSinceRun, 5); // Max 6 days (0-5)
            console.log(`  Expected array length: ${tradingDaysSinceRun + 1}`);
            
            if (arrayLength < tradingDaysSinceRun + 1) {
              console.log(`  ⚠️ ISSUE: Array shorter than expected`);
            }
          }
        }
      }
    }
  }
  
  console.log('\n=== Summary ===');
  console.log(`Total rows analyzed: ${totalRows}`);
  console.log(`Rows with any strike hit: ${rowsWithStrikeHit}`);
  console.log(`Rows with full 6-day array: ${rowsWithFullArray}`);
  console.log(`Rows with partial array (nulls): ${rowsWithPartialArray}`);
  console.log(`Rows with NO_DATA: ${rowsWithNoData}`);
  console.log(`Hit rate based on rows: ${(rowsWithStrikeHit / totalRows * 100).toFixed(1)}%`);
  
  // Also check the daily columns to compare
  console.log('\n=== Comparing with Day Check Columns ===');
  let dayHitCounts = [0, 0, 0, 0, 0, 0];
  
  for (let i = 1; i <= Math.min(20, data.length - 1); i++) {
    const row = data[i];
    const ticker = row[hdrMap.tickerCol - 1];
    if (!ticker) continue;
    
    // Check each day's hit status
    for (let day = 0; day < 6; day++) {
      const dayCheckCol = hdrMap[`day${day}CheckCol`];
      if (dayCheckCol) {
        const dayCheck = row[dayCheckCol - 1];
        if (dayCheck === 'HIT' || dayCheck === 'FAVORABLE') {
          dayHitCounts[day]++;
        }
      }
    }
  }
  
  console.log('\nDay Check Column Hit Counts:');
  dayHitCounts.forEach((count, day) => {
    console.log(`  Day ${day}: ${count} hits`);
  });
  
  return {
    totalRows,
    rowsWithStrikeHit,
    rowsWithFullArray,
    rowsWithPartialArray,
    rowsWithNoData
  };
}

/**
 * Check a specific row's strikeHit array status
 */
function EW_checkSpecificRowStrikeHit(rowNumber) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Strategy_Tracking');
  if (!sheet) {
    console.log('Strategy_Tracking sheet not found');
    return;
  }
  
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_getHeaderMap(headers);
  const row = sheet.getRange(rowNumber, 1, 1, sheet.getLastColumn()).getValues()[0];
  
  const ticker = row[hdrMap.tickerCol - 1];
  const strikeHitRaw = row[hdrMap.strikeHitCol - 1];
  const maxFavRaw = row[hdrMap.maxFavorableCol - 1];
  
  console.log(`\n=== Row ${rowNumber} - ${ticker} ===`);
  console.log(`Strike_Hit raw value: ${strikeHitRaw}`);
  console.log(`Max_Favorable raw value: ${maxFavRaw}`);
  
  // Parse arrays
  const strikeHitArray = EW_parseArrayFromCell(strikeHitRaw);
  const maxFavArray = EW_parseArrayFromCell(maxFavRaw);
  
  console.log(`Strike_Hit parsed array: ${JSON.stringify(strikeHitArray)}`);
  console.log(`Max_Favorable parsed array: ${JSON.stringify(maxFavArray)}`);
  
  // Check each day
  for (let day = 0; day < 6; day++) {
    const dayCheckCol = hdrMap[`day${day}CheckCol`];
    const dayCheck = dayCheckCol ? row[dayCheckCol - 1] : '';
    const strikeHitValue = strikeHitArray[day];
    const maxFavValue = maxFavArray[day];
    
    console.log(`\nDay ${day}:`);
    console.log(`  Day Check: ${dayCheck}`);
    console.log(`  Strike Hit: ${strikeHitValue}`);
    console.log(`  Max Favorable: ${maxFavValue}`);
    
    if (dayCheck === 'HIT' || dayCheck === 'FAVORABLE') {
      if (strikeHitValue === null || strikeHitValue === undefined) {
        console.log(`  ⚠️ ISSUE: Day check shows HIT but Strike_Hit is null`);
      }
    }
  }
}