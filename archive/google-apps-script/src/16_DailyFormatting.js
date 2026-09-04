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

  // Build list of all sheets to format (strategy sheets + options premium sheets)
  const sheetsToFormat = [...strategies];

  // Add Options Premium sheets (e.g., "Long Calls Options", "Bull Spreads Options")
  const optionStrategies = ['Long Calls', 'Bull Spreads', 'Bear Spreads', 'Strangles', 'Covered Calls'];
  optionStrategies.forEach(strategyName => {
    sheetsToFormat.push(`${strategyName} Options`);
  });

  for (const sheetName of sheetsToFormat) {
    try {
      const sheet = ss.getSheetByName(sheetName);
      if (!sheet || sheet.getLastRow() < 2) {
        continue;
      }

      // Get header map
      const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      const hdrMap = EW_headerMap(headers);

      // Check if sheet has Day Check columns to format
      if (hdrMap.day0CheckCol || hdrMap.day1CheckCol || hdrMap.day2CheckCol ||
          hdrMap.day3CheckCol || hdrMap.day4CheckCol || hdrMap.day5CheckCol ||
          hdrMap.day6CheckCol || hdrMap.day7CheckCol || hdrMap.day8CheckCol ||
          hdrMap.day9CheckCol || hdrMap.day10CheckCol || hdrMap.day11CheckCol ||
          hdrMap.day12CheckCol || hdrMap.day13CheckCol) {

        EW_formatDayCheckColumns(sheet, hdrMap, sheetName);
        formattedCount++;
        EW_trace('FORMATTING', `Applied formatting to ${sheetName}`);
        console.log(`FORMATTING: Formatted ${sheetName} sheet`);
      }
    } catch (e) {
      errors.push(`${sheetName}: ${e.message}`);
      EW_trace('FORMATTING', `Error formatting ${sheetName}: ${e.message}`, true);
      console.error(`FORMATTING ERROR: ${sheetName} - ${e.message}`);
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

  // Check if this is an Options Premium sheet (has Bid column)
  const isOptionsPremiumSheet = hdrMap.bidCol !== null && hdrMap.bidCol !== undefined;

  // Define colors
  const GREEN = '#d4edda';  // Light green for hits
  const RED = '#f8d7da';    // Light red for misses
  const GRAY = '#e2e3e5';   // Light gray for no data

  // Text colors
  const TEXT_DARK_GREEN = '#155724';  // Dark green text for hits
  const TEXT_DARK_RED = '#721c24';    // Dark red text for misses
  const TEXT_GRAY = '#6c757d';        // Gray text for no data

  // Format each Day Check column (Day0-Day13)
  const dayCheckCols = [
    hdrMap.day0CheckCol,
    hdrMap.day1CheckCol,
    hdrMap.day2CheckCol,
    hdrMap.day3CheckCol,
    hdrMap.day4CheckCol,
    hdrMap.day5CheckCol,
    hdrMap.day6CheckCol,
    hdrMap.day7CheckCol,
    hdrMap.day8CheckCol,
    hdrMap.day9CheckCol,
    hdrMap.day10CheckCol,
    hdrMap.day11CheckCol,
    hdrMap.day12CheckCol,
    hdrMap.day13CheckCol
  ];

  dayCheckCols.forEach((col, dayIndex) => {
    if (!col) return;

    // Get the range for this column (excluding header)
    const range = sheet.getRange(2, col, lastRow - 1, 1);
    const values = range.getValues();
    const backgrounds = [];
    const fontWeights = [];
    const fontColors = [];

    // For Options Premium sheets, compare to Bid price
    // For regular sheets, compare to Strike price
    let comparisonCol;
    let comparisonValues;

    if (isOptionsPremiumSheet && hdrMap.bidCol) {
      // Options Premium: compare premium to bid (profit when premium > bid)
      comparisonCol = hdrMap.bidCol;
      comparisonValues = sheet.getRange(2, comparisonCol, lastRow - 1, 1).getValues();
    } else {
      // Regular sheets: compare price to strike
      comparisonCol = hdrMap.strikeCol || hdrMap.longStrikeCol;
      if (!comparisonCol) return;
      comparisonValues = sheet.getRange(2, comparisonCol, lastRow - 1, 1).getValues();
    }

    values.forEach((row, rowIndex) => {
      const value = row[0];
      const comparisonValue = parseFloat(comparisonValues[rowIndex][0]);

      if (!value || value === '' || value === null) {
        // No data - gray background
        backgrounds.push([GRAY]);
        fontWeights.push(['normal']);
        fontColors.push([TEXT_GRAY]);
      } else {
        const price = parseFloat(value);

        if (isNaN(price) || isNaN(comparisonValue)) {
          // Invalid data
          backgrounds.push([GRAY]);
          fontWeights.push(['normal']);
          fontColors.push([TEXT_GRAY]);
        } else {
          let isHit = false;

          if (isOptionsPremiumSheet) {
            // Options Premium: GREEN if premium > bid (profit), RED if premium <= bid (loss/no profit)
            // Since premium tracking: premium increases = profit (always use HIGH)
            isHit = price > comparisonValue;
          } else if (isBullish) {
            // Bullish: green if price >= strike, red if price < strike
            isHit = price >= comparisonValue;
          } else if (isBearish) {
            // Bearish: green if price <= strike, red if price > strike
            isHit = price <= comparisonValue;
          } else {
            // Neutral strategy - no specific formatting
            backgrounds.push([null]);
            fontWeights.push(['normal']);
            fontColors.push([null]);
            return;
          }

          // Apply hit/miss formatting
          if (isHit) {
            backgrounds.push([GREEN]);
            fontWeights.push(['bold']);
            fontColors.push([TEXT_DARK_GREEN]);
          } else {
            backgrounds.push([RED]);
            fontWeights.push(['normal']);
            fontColors.push([TEXT_DARK_RED]);
          }
        }
      }
    });

    // Apply formatting in batch
    if (backgrounds.length > 0) {
      range.setBackgrounds(backgrounds);
      range.setFontWeights(fontWeights);
      range.setFontColors(fontColors);
    }
  });
  
  // Format Strike_Hit column if it exists
  if (hdrMap.strikeHitCol) {
    const range = sheet.getRange(2, hdrMap.strikeHitCol, lastRow - 1, 1);
    const values = range.getValues();
    const backgrounds = [];
    const fontWeights = [];
    const fontColors = [];
    
    values.forEach(row => {
      const value = row[0];
      
      if (!value || value === '') {
        backgrounds.push([null]);
        fontWeights.push(['normal']);
        fontColors.push([null]);
      } else if (typeof value === 'string' && value.startsWith('[')) {
        // Array format - check if any values are non-null
        try {
          const arr = JSON.parse(value);
          const hasHit = arr.some(v => v !== null && v !== 'null');
          
          if (hasHit) {
            backgrounds.push([GREEN]);
            fontWeights.push(['bold']);
            fontColors.push([TEXT_DARK_GREEN]);
          } else {
            backgrounds.push([GRAY]);
            fontWeights.push(['normal']);
            fontColors.push([TEXT_GRAY]);
          }
        } catch (e) {
          backgrounds.push([null]);
          fontWeights.push(['normal']);
          fontColors.push([null]);
        }
      } else {
        // Legacy format
        const upperValue = String(value).toUpperCase();
        if (upperValue === 'HIT' || upperValue === 'FAVORABLE') {
          backgrounds.push([GREEN]);
          fontWeights.push(['bold']);
          fontColors.push([TEXT_DARK_GREEN]);
        } else if (upperValue === 'NO' || upperValue === 'UNFAVORABLE') {
          backgrounds.push([RED]);
          fontWeights.push(['normal']);
          fontColors.push([TEXT_DARK_RED]);
        } else {
          backgrounds.push([null]);
          fontWeights.push(['normal']);
          fontColors.push([null]);
        }
      }
    });
    
    // Apply formatting
    if (backgrounds.length > 0) {
      range.setBackgrounds(backgrounds);
      range.setFontWeights(fontWeights);
      range.setFontColors(fontColors);
    }
  }
  
  // Format Hit_Date column if it exists
  if (hdrMap.hitDateCol) {
    const range = sheet.getRange(2, hdrMap.hitDateCol, lastRow - 1, 1);
    const values = range.getValues();
    const backgrounds = [];
    const fontColors = [];

    values.forEach(row => {
      const value = row[0];
      if (value && value !== '') {
        backgrounds.push([GREEN]);
        fontColors.push([TEXT_DARK_GREEN]);
      } else {
        backgrounds.push([null]);
        fontColors.push([null]);
      }
    });

    // Apply formatting
    if (backgrounds.length > 0) {
      range.setBackgrounds(backgrounds);
      range.setFontColors(fontColors);
    }
  }

  // Format Bid_Hit_Pct column if it exists (Options Premium sheets)
  if (hdrMap.bidHitPctCol) {
    const range = sheet.getRange(2, hdrMap.bidHitPctCol, lastRow - 1, 1);
    const values = range.getValues();
    const backgrounds = [];
    const fontWeights = [];
    const fontColors = [];

    values.forEach(row => {
      const value = row[0];

      if (!value || value === '') {
        backgrounds.push([null]);
        fontWeights.push(['normal']);
        fontColors.push([null]);
      } else if (typeof value === 'string' && value.startsWith('[')) {
        // Array format - check if any values show profit (> 0)
        try {
          const arr = JSON.parse(value);
          const hasProfit = arr.some(v => v !== null && v !== 'null' && parseFloat(v) > 0);

          if (hasProfit) {
            backgrounds.push([GREEN]);
            fontWeights.push(['bold']);
            fontColors.push([TEXT_DARK_GREEN]);
          } else {
            backgrounds.push([GRAY]);
            fontWeights.push(['normal']);
            fontColors.push([TEXT_GRAY]);
          }
        } catch (e) {
          backgrounds.push([null]);
          fontWeights.push(['normal']);
          fontColors.push([null]);
        }
      } else {
        backgrounds.push([null]);
        fontWeights.push(['normal']);
        fontColors.push([null]);
      }
    });

    // Apply formatting
    if (backgrounds.length > 0) {
      range.setBackgrounds(backgrounds);
      range.setFontWeights(fontWeights);
      range.setFontColors(fontColors);
    }
  }

  // Format First_Hit_Date column if it exists (Options Premium sheets)
  if (hdrMap.firstHitDateCol) {
    const range = sheet.getRange(2, hdrMap.firstHitDateCol, lastRow - 1, 1);
    const values = range.getValues();
    const backgrounds = [];
    const fontColors = [];

    values.forEach(row => {
      const value = row[0];
      if (value && value !== '') {
        backgrounds.push([GREEN]);
        fontColors.push([TEXT_DARK_GREEN]);
      } else {
        backgrounds.push([null]);
        fontColors.push([null]);
      }
    });

    // Apply formatting
    if (backgrounds.length > 0) {
      range.setBackgrounds(backgrounds);
      range.setFontColors(fontColors);
    }
  }

  // Format PnL_High column if it exists
  if (hdrMap.pnlHighCol) {
    const range = sheet.getRange(2, hdrMap.pnlHighCol, lastRow - 1, 1);
    const values = range.getValues();
    const backgrounds = [];
    const fontColors = [];

    values.forEach(row => {
      const value = row[0];
      if (!value || value === '') {
        backgrounds.push([null]);
        fontColors.push([null]);
      } else {
        const numValue = parseFloat(value);
        if (numValue > 0) {
          backgrounds.push([GREEN]);
          fontColors.push([TEXT_DARK_GREEN]);
        } else if (numValue < 0) {
          backgrounds.push([RED]);
          fontColors.push([TEXT_DARK_RED]);
        } else {
          backgrounds.push([null]);
          fontColors.push([null]);
        }
      }
    });

    // Apply formatting
    if (backgrounds.length > 0) {
      range.setBackgrounds(backgrounds);
      range.setFontColors(fontColors);
    }
  }

  // Format PnL_High_Pct column if it exists
  if (hdrMap.pnlHighPctCol) {
    const range = sheet.getRange(2, hdrMap.pnlHighPctCol, lastRow - 1, 1);
    const values = range.getValues();
    const backgrounds = [];
    const fontColors = [];

    values.forEach(row => {
      const value = row[0];
      if (!value || value === '') {
        backgrounds.push([null]);
        fontColors.push([null]);
      } else {
        const numValue = parseFloat(value);
        if (numValue > 0) {
          backgrounds.push([GREEN]);
          fontColors.push([TEXT_DARK_GREEN]);
        } else if (numValue < 0) {
          backgrounds.push([RED]);
          fontColors.push([TEXT_DARK_RED]);
        } else {
          backgrounds.push([null]);
          fontColors.push([null]);
        }
      }
    });

    // Apply formatting
    if (backgrounds.length > 0) {
      range.setBackgrounds(backgrounds);
      range.setFontColors(fontColors);
    }
  }

  // Format PnL_Low column if it exists
  if (hdrMap.pnlLowCol) {
    const range = sheet.getRange(2, hdrMap.pnlLowCol, lastRow - 1, 1);
    const values = range.getValues();
    const backgrounds = [];
    const fontColors = [];

    values.forEach(row => {
      const value = row[0];
      if (!value || value === '') {
        backgrounds.push([null]);
        fontColors.push([null]);
      } else {
        const numValue = parseFloat(value);
        if (numValue > 0) {
          backgrounds.push([GREEN]);
          fontColors.push([TEXT_DARK_GREEN]);
        } else if (numValue < 0) {
          backgrounds.push([RED]);
          fontColors.push([TEXT_DARK_RED]);
        } else {
          backgrounds.push([null]);
          fontColors.push([null]);
        }
      }
    });

    // Apply formatting
    if (backgrounds.length > 0) {
      range.setBackgrounds(backgrounds);
      range.setFontColors(fontColors);
    }
  }

  // Format PnL_Low_Pct column if it exists
  if (hdrMap.pnlLowPctCol) {
    const range = sheet.getRange(2, hdrMap.pnlLowPctCol, lastRow - 1, 1);
    const values = range.getValues();
    const backgrounds = [];
    const fontColors = [];

    values.forEach(row => {
      const value = row[0];
      if (!value || value === '') {
        backgrounds.push([null]);
        fontColors.push([null]);
      } else {
        const numValue = parseFloat(value);
        if (numValue > 0) {
          backgrounds.push([GREEN]);
          fontColors.push([TEXT_DARK_GREEN]);
        } else if (numValue < 0) {
          backgrounds.push([RED]);
          fontColors.push([TEXT_DARK_RED]);
        } else {
          backgrounds.push([null]);
          fontColors.push([null]);
        }
      }
    });

    // Apply formatting
    if (backgrounds.length > 0) {
      range.setBackgrounds(backgrounds);
      range.setFontColors(fontColors);
    }
  }

  // Format Exp_Result column if it exists
  if (hdrMap.expResultCol) {
    const range = sheet.getRange(2, hdrMap.expResultCol, lastRow - 1, 1);
    const values = range.getValues();
    const backgrounds = [];
    const fontColors = [];
    
    // Get strike prices for comparison
    const strikeCol = hdrMap.strikeCol || hdrMap.longStrikeCol;
    if (strikeCol) {
      const strikes = sheet.getRange(2, strikeCol, lastRow - 1, 1).getValues();
      
      values.forEach((row, rowIndex) => {
        const value = row[0];
        const strike = parseFloat(strikes[rowIndex][0]);
        
        if (!value || value === '') {
          backgrounds.push([null]);
          fontColors.push([null]);
        } else {
          const price = parseFloat(value);
          
          if (isNaN(price) || isNaN(strike)) {
            backgrounds.push([null]);
            fontColors.push([null]);
          } else {
            let isSuccess = false;
            
            if (isBullish) {
              isSuccess = price >= strike;
            } else if (isBearish) {
              isSuccess = price <= strike;
            }
            
            backgrounds.push([isSuccess ? GREEN : RED]);
            fontColors.push([isSuccess ? TEXT_DARK_GREEN : TEXT_DARK_RED]);
          }
        }
      });
      
      // Apply formatting
      if (backgrounds.length > 0) {
        range.setBackgrounds(backgrounds);
        range.setFontColors(fontColors);
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