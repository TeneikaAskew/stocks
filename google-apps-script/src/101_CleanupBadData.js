// Removed EW_cleanupStrikeHitArrays function
// Negative values in Strike_Hit array are valuable data showing when positions moved against us
// The Success Report has been fixed to only treat appropriate values as "hits"

/**
 * Convert percentage values to decimals in Max_Favorable and Min_Unfavorable arrays
 */
function EW_convertPercentagesToDecimals() {
  console.log('=== CONVERTING PERCENTAGES TO DECIMALS ===');
  
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  let totalConverted = 0;
  
  for (const strategy of strategies) {
    const sheet = ss.getSheetByName(strategy);
    if (!sheet || sheet.getLastRow() < 2) continue;
    
    console.log(`\nProcessing ${strategy}...`);
    
    const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    const hdrMap = EW_headerMap(headers);
    
    const lastRow = sheet.getLastRow();
    const data = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
    
    let convertedInSheet = 0;
    
    data.forEach((row, idx) => {
      let needsUpdate = false;
      const updates = {};
      
      // Check Max_Favorable
      if (hdrMap.maxFavorableCol) {
        const maxFavValue = row[hdrMap.maxFavorableCol - 1];
        if (maxFavValue) {
          const maxFavArray = EW_parseArrayFromCell(maxFavValue);
          const convertedArray = maxFavArray.map(value => {
            if (value === null || value === undefined || value === '') return null;
            const numValue = parseFloat(value);
            if (isNaN(numValue)) return null;
            
            // If value > 1, it's likely a percentage, convert to decimal
            if (numValue > 1) {
              needsUpdate = true;
              return (numValue / 100).toFixed(6);
            }
            return value;
          });
          
          if (needsUpdate) {
            updates.maxFavorable = JSON.stringify(convertedArray);
          }
        }
      }
      
      // Check Min_Unfavorable
      if (hdrMap.minUnfavorableCol) {
        const minUnfavValue = row[hdrMap.minUnfavorableCol - 1];
        if (minUnfavValue) {
          const minUnfavArray = EW_parseArrayFromCell(minUnfavValue);
          const convertedArray = minUnfavArray.map(value => {
            if (value === null || value === undefined || value === '') return null;
            const numValue = parseFloat(value);
            if (isNaN(numValue)) return null;
            
            // If value > 1, it's likely a percentage, convert to decimal
            if (numValue > 1) {
              needsUpdate = true;
              return (numValue / 100).toFixed(6);
            }
            return value;
          });
          
          if (needsUpdate || updates.maxFavorable) {
            updates.minUnfavorable = JSON.stringify(convertedArray);
          }
        }
      }
      
      // Apply updates
      if (Object.keys(updates).length > 0) {
        const rowNum = idx + 2;
        
        if (updates.maxFavorable && hdrMap.maxFavorableCol) {
          sheet.getRange(rowNum, hdrMap.maxFavorableCol).setValue(updates.maxFavorable);
        }
        if (updates.minUnfavorable && hdrMap.minUnfavorableCol) {
          sheet.getRange(rowNum, hdrMap.minUnfavorableCol).setValue(updates.minUnfavorable);
        }
        
        convertedInSheet++;
        const ticker = row[hdrMap.tickerCol - 1];
        console.log(`  Converted row ${rowNum} (${ticker}): percentages to decimals`);
      }
    });
    
    console.log(`  Converted ${convertedInSheet} rows in ${strategy}`);
    totalConverted += convertedInSheet;
  }
  
  console.log(`\nTotal rows converted: ${totalConverted}`);
  return totalConverted;
}

/**
 * Run all cleanup operations
 */
function EW_runFullCleanup() {
  console.log('=== RUNNING FULL DATA CLEANUP ===');
  console.log('This will convert percentage values that should be decimals\n');
  
  // Convert percentages to decimals
  const convertedValues = EW_convertPercentagesToDecimals();
  
  console.log('\n=== CLEANUP COMPLETE ===');
  console.log(`Converted ${convertedValues} percentage values to decimals`);
  
  // Show alert if in spreadsheet
  if (EW_isSpreadsheetEnvironment()) {
    SpreadsheetApp.getUi().alert(
      'Data Cleanup Complete',
      `Converted ${convertedValues} percentage values to decimals\n\nPlease regenerate the Success Report.`,
      SpreadsheetApp.getUi().ButtonSet.OK
    );
  }
}