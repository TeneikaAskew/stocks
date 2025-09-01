/**
 * Daily Formatting Functions
 * Separate functions to handle formatting of tracking columns
 * Runs as a daily trigger at 8 PM to format all sheets
 */

/**
 * Main function to apply formatting to all strategy sheets
 * This should be run as a daily trigger at 8 PM
 */
function EW_applyDailyFormatting() {
  const startTime = new Date();
  EW_trace('FORMATTING', 'Starting daily formatting for all sheets', true);
  console.log(`FORMATTING: Daily formatting started at ${startTime.toISOString()}`);
  
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  let formattedCount = 0;
  let errors = [];
  
  for (const strategy of strategies) {
    try {
      const sheet = ss.getSheetByName(strategy);
      if (!sheet || sheet.getLastRow() < 2) {
        continue;
      }
      
      // Get header map
      const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      const hdrMap = EW_headerMap(headers);
      
      // Check if sheet has Day Check columns to format
      if (hdrMap.day0CheckCol || hdrMap.day1CheckCol || hdrMap.day2CheckCol || 
          hdrMap.day3CheckCol || hdrMap.day4CheckCol || hdrMap.day5CheckCol) {
        
        EW_formatDayCheckColumns(sheet, hdrMap, strategy);
        formattedCount++;
        EW_trace('FORMATTING', `Applied formatting to ${strategy}`);
        console.log(`FORMATTING: Formatted ${strategy} sheet`);
      }
    } catch (e) {
      errors.push(`${strategy}: ${e.message}`);
      EW_trace('FORMATTING', `Error formatting ${strategy}: ${e.message}`, true);
      console.error(`FORMATTING ERROR: ${strategy} - ${e.message}`);
    }
  }
  
  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);
  
  const msg = `Daily formatting complete.\n` +
    `Formatted: ${formattedCount} sheets\n` +
    `Total strategies: ${strategies.length}\n` +
    `Duration: ${duration} seconds` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');
  
  EW_trace('FORMATTING', msg, true);
  console.log(`FORMATTING: Completed in ${duration} seconds - Formatted ${formattedCount} sheets`);
  
  // Don't show alert for automated trigger
  return { formatted: formattedCount, duration: duration };
}

/**
 * Format Day Check columns for a specific sheet
 * Applies conditional formatting to highlight hits and misses
 * @param {Sheet} sheet - The sheet to format
 * @param {Object} hdrMap - Header mapping object
 * @param {string} strategyName - Name of the strategy for determining formatting rules
 */
function EW_formatDayCheckColumns(sheet, hdrMap, strategyName) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return;
  
  const strategyUpper = strategyName.toUpperCase();
  const isBullish = strategyUpper.includes('LONG CALL') || strategyUpper.includes('BULL');
  const isBearish = strategyUpper.includes('LONG PUT') || strategyUpper.includes('BEAR');
  
  // Define colors
  const GREEN = '#d4edda';  // Light green for hits
  const RED = '#f8d7da';    // Light red for misses
  const YELLOW = '#fff3cd'; // Light yellow for close calls
  const GRAY = '#e2e3e5';   // Light gray for no data
  
  // Format each Day Check column
  const dayCheckCols = [
    hdrMap.day0CheckCol,
    hdrMap.day1CheckCol,
    hdrMap.day2CheckCol,
    hdrMap.day3CheckCol,
    hdrMap.day4CheckCol,
    hdrMap.day5CheckCol
  ];
  
  dayCheckCols.forEach((col, dayIndex) => {
    if (!col) return;
    
    // Get the range for this column (excluding header)
    const range = sheet.getRange(2, col, lastRow - 1, 1);
    const values = range.getValues();
    const backgrounds = [];
    const fontWeights = [];
    
    // Get strike prices for comparison
    const strikeCol = hdrMap.strikeCol || hdrMap.longStrikeCol;
    if (!strikeCol) return;
    
    const strikes = sheet.getRange(2, strikeCol, lastRow - 1, 1).getValues();
    
    values.forEach((row, rowIndex) => {
      const value = row[0];
      const strike = parseFloat(strikes[rowIndex][0]);
      
      if (!value || value === '' || value === 'None') {
        // No data - gray background
        backgrounds.push([GRAY]);
        fontWeights.push(['normal']);
      } else {
        const price = parseFloat(value);
        
        if (isNaN(price) || isNaN(strike)) {
          // Invalid data
          backgrounds.push([GRAY]);
          fontWeights.push(['normal']);
        } else {
          // Compare price to strike
          let isHit = false;
          let isClose = false;
          
          if (isBullish) {
            // Bullish: green if price >= strike
            isHit = price >= strike;
            isClose = price >= strike * 0.98 && price < strike; // Within 2% of strike
          } else if (isBearish) {
            // Bearish: green if price <= strike
            isHit = price <= strike;
            isClose = price <= strike * 1.02 && price > strike; // Within 2% of strike
          } else {
            // Neutral strategy - no specific formatting
            backgrounds.push([null]);
            fontWeights.push(['normal']);
            continue;
          }
          
          if (isHit) {
            backgrounds.push([GREEN]);
            fontWeights.push(['bold']);
          } else if (isClose) {
            backgrounds.push([YELLOW]);
            fontWeights.push(['normal']);
          } else {
            backgrounds.push([RED]);
            fontWeights.push(['normal']);
          }
        }
      }
    });
    
    // Apply formatting in batch
    if (backgrounds.length > 0) {
      range.setBackgrounds(backgrounds);
      range.setFontWeights(fontWeights);
    }
  });
  
  // Format Strike_Hit column if it exists
  if (hdrMap.strikeHitCol) {
    const range = sheet.getRange(2, hdrMap.strikeHitCol, lastRow - 1, 1);
    const values = range.getValues();
    const backgrounds = [];
    const fontWeights = [];
    
    values.forEach(row => {
      const value = row[0];
      
      if (!value || value === '') {
        backgrounds.push([null]);
        fontWeights.push(['normal']);
      } else if (typeof value === 'string' && value.startsWith('[')) {
        // Array format - check if any values are non-null
        try {
          const arr = JSON.parse(value);
          const hasHit = arr.some(v => v !== null && v !== 'null');
          
          if (hasHit) {
            backgrounds.push([GREEN]);
            fontWeights.push(['bold']);
          } else {
            backgrounds.push([GRAY]);
            fontWeights.push(['normal']);
          }
        } catch (e) {
          backgrounds.push([null]);
          fontWeights.push(['normal']);
        }
      } else {
        // Legacy format
        const upperValue = String(value).toUpperCase();
        if (upperValue === 'HIT' || upperValue === 'FAVORABLE') {
          backgrounds.push([GREEN]);
          fontWeights.push(['bold']);
        } else if (upperValue === 'NO' || upperValue === 'UNFAVORABLE') {
          backgrounds.push([RED]);
          fontWeights.push(['normal']);
        } else {
          backgrounds.push([null]);
          fontWeights.push(['normal']);
        }
      }
    });
    
    // Apply formatting
    if (backgrounds.length > 0) {
      range.setBackgrounds(backgrounds);
      range.setFontWeights(fontWeights);
    }
  }
  
  // Format Hit_Date column if it exists
  if (hdrMap.hitDateCol) {
    const range = sheet.getRange(2, hdrMap.hitDateCol, lastRow - 1, 1);
    const values = range.getValues();
    const backgrounds = [];
    
    values.forEach(row => {
      const value = row[0];
      if (value && value !== '') {
        backgrounds.push([GREEN]);
      } else {
        backgrounds.push([null]);
      }
    });
    
    // Apply formatting
    if (backgrounds.length > 0) {
      range.setBackgrounds(backgrounds);
    }
  }
  
  // Format Exp_Result column if it exists
  if (hdrMap.expResultCol) {
    const range = sheet.getRange(2, hdrMap.expResultCol, lastRow - 1, 1);
    const values = range.getValues();
    const backgrounds = [];
    
    // Get strike prices for comparison
    const strikeCol = hdrMap.strikeCol || hdrMap.longStrikeCol;
    if (strikeCol) {
      const strikes = sheet.getRange(2, strikeCol, lastRow - 1, 1).getValues();
      
      values.forEach((row, rowIndex) => {
        const value = row[0];
        const strike = parseFloat(strikes[rowIndex][0]);
        
        if (!value || value === '') {
          backgrounds.push([null]);
        } else {
          const price = parseFloat(value);
          
          if (isNaN(price) || isNaN(strike)) {
            backgrounds.push([null]);
          } else {
            let isSuccess = false;
            
            if (isBullish) {
              isSuccess = price >= strike;
            } else if (isBearish) {
              isSuccess = price <= strike;
            }
            
            backgrounds.push([isSuccess ? GREEN : RED]);
          }
        }
      });
      
      // Apply formatting
      if (backgrounds.length > 0) {
        range.setBackgrounds(backgrounds);
      }
    }
  }
}

/**
 * Menu function to manually trigger formatting for current sheet
 */
function EW_formatCurrentSheet() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const sheetName = sheet.getName();
  
  // Get header map
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  try {
    EW_formatDayCheckColumns(sheet, hdrMap, sheetName);
    EW_safeAlert('Formatting Complete', `Applied formatting to ${sheetName}`);
  } catch (e) {
    EW_safeAlert('Formatting Error', `Failed to format ${sheetName}: ${e.message}`);
  }
}

/**
 * Menu function to manually trigger formatting for all sheets
 */
function EW_formatAllSheets() {
  const result = EW_applyDailyFormatting();
  EW_safeAlert('Formatting Complete', `Formatted ${result.formatted} sheets in ${result.duration} seconds`);
}