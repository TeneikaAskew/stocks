/**
 * Menu Sheet - Mobile-Friendly Menu Interface
 * Creates a sheet with all menu options accessible via dropdowns
 * Useful for mobile access where custom menus aren't available
 */

/**
 * Parse menu structure from onOpen() and create menu sheet
 */
function EW_createMenuSheet() {
  const ss = SpreadsheetApp.getActive();

  // Get or create the Menu sheet
  let menuSheet = ss.getSheetByName('📱 Menu');
  if (!menuSheet) {
    menuSheet = ss.insertSheet('📱 Menu', 0); // Insert at beginning
  } else {
    menuSheet.clear();
  }

  // Get menu structure by parsing onOpen function
  const menuStructure = EW_parseMenuStructure();

  // Set up headers
  const headers = ['Category', 'Function', 'Description', 'Action'];
  menuSheet.getRange(1, 1, 1, headers.length)
    .setValues([headers])
    .setFontWeight('bold')
    .setBackground('#4285f4')
    .setFontColor('#ffffff');

  // Build menu rows
  const rows = [];
  menuStructure.forEach(category => {
    if (category.items && category.items.length > 0) {
      category.items.forEach((item, index) => {
        rows.push([
          index === 0 ? category.name : '', // Only show category on first item
          item.label,
          item.description || '',
          '▶️ Run' // Action indicator
        ]);
      });
    }
  });

  // Write data
  if (rows.length > 0) {
    menuSheet.getRange(2, 1, rows.length, headers.length).setValues(rows);
  }

  // Format the sheet
  EW_formatMenuSheet(menuSheet, rows.length);

  // Set up data validation for Action column
  EW_setupMenuActions(menuSheet, menuStructure, rows.length);

  // Protect the sheet except Action column
  EW_protectMenuSheet(menuSheet);

  return menuSheet;
}

/**
 * Parse the menu structure from onOpen function
 */
function EW_parseMenuStructure() {
  // Define menu structure manually (matches onOpen())
  // This needs to be kept in sync with onOpen() or we could parse it dynamically

  const menuStructure = [
    {
      name: '🏃 Run',
      items: [
        { label: 'Run Selected Strategy', function: 'EW_runSelectedStrategy', description: 'Run calculations for selected strategy sheet' },
        { label: 'Run All Strategies', function: 'EW_runAllStrategies', description: 'Run calculations for all strategy sheets' },
        { label: 'Run One (Debug)', function: 'EW_debugOne', description: 'Interactive single strategy runner for debugging' }
      ]
    },
    {
      name: '📊 Reports',
      items: [
        { label: 'Open Success Report', function: 'EW_openSuccessReport', description: 'Open the success tracking report' },
        { label: 'Update Success Report', function: 'EW_updateSuccessReport', description: 'Refresh success report data' },
        { label: 'Success Report Dashboard', function: 'EW_showSuccessReportDashboard', description: 'View interactive dashboard' }
      ]
    },
    {
      name: '🔄 Backfill',
      items: [
        { label: 'Start Historical Backfill', function: 'EW_startHistoricalBackfill', description: 'Fill historical data for all positions' },
        { label: 'Backfill Selected Rows', function: 'EW_backfillSelectedRows', description: 'Fill historical data for selected rows only' },
        { label: 'Continue Backfill', function: 'EW_continueBackfill', description: 'Resume interrupted backfill process' },
        { label: 'Check Backfill Status', function: 'EW_checkBackfillStatus', description: 'View current backfill progress' },
        { label: 'Reset Backfill State', function: 'EW_resetBackfillState', description: 'Clear backfill continuation state' }
      ]
    },
    {
      name: '📈 Options Backfill',
      items: [
        { label: 'Backfill Options Premium History', function: 'EW_backfillOptionsPremiumHistory', description: 'Fill historical premium data for all option positions (includes expired)' },
        { label: 'Update Daily Options Premium', function: 'EW_updateDailyOptionsPremiumHistory', description: 'Daily update for active options only (skips expired)' },
        { label: 'Backfill Selected Options', function: 'EW_backfillOptionsPremiumsSelected', description: 'Fill premium history for selected option rows' },
        { label: 'Check Options Backfill Status', function: 'EW_checkOptionsPremiumBackfillStatus', description: 'View options backfill progress' }
      ]
    },
    {
      name: '⚙️ Setup & Config',
      items: [
        { label: 'Set Script Properties', function: 'EW_setScriptProperties', description: 'Configure API keys and folder IDs' },
        { label: 'Test Login', function: 'EW_testLogin', description: 'Verify API credentials' },
        { label: 'Setup Triggers', function: 'EW_setupTriggers', description: 'Configure automated triggers' },
        { label: 'Delete All Triggers', function: 'EW_deleteTriggers', description: 'Remove all automated triggers' },
        { label: 'List Triggers', function: 'EW_listTriggers', description: 'View configured triggers' }
      ]
    },
    {
      name: '🔧 Calculations & Data Fixes',
      items: [
        { label: 'Fix Options Premium P/L (All Sheets)', function: 'EW_fixOptionsPremiumPnL', description: 'Recalculate PnL_High and PnL_Low from historical OHLC data for all Options Premium sheets' },
        { label: 'Fix Options Premium P/L (Current Sheet)', function: 'EW_fixOptionsPremiumPnLCurrentSheet', description: 'Recalculate PnL_High and PnL_Low from historical OHLC data for the active sheet only' },
        { label: 'Fix Options Premium Arrays (All Sheets)', function: 'EW_fixOptionsPremiumArrays', description: 'Recalculate Bid_Hit_Pct, Day check values, and First_Hit_Date from OHLC data for all Options Premium sheets (uses HIGH for profit tracking)' },
        { label: 'Fix Options Premium Arrays (Current Sheet)', function: 'EW_fixOptionsPremiumArraysCurrentSheet', description: 'Recalculate Bid_Hit_Pct, Day check values, and First_Hit_Date from OHLC data for the active sheet only (uses HIGH for profit tracking)' }
      ]
    },
    {
      name: '🔧 Utilities - Formatting',
      items: [
        { label: 'Format Current Sheet', function: 'EW_formatCurrentSheet', description: 'Apply formatting to active sheet' },
        { label: 'Format All Sheets', function: 'EW_formatAllSheets', description: 'Apply formatting to all sheets' }
      ]
    },
    {
      name: '🔧 Utilities - API Logging',
      items: [
        { label: 'Check Missing (All)', function: 'EW_checkMissingApiLogs', description: 'Find missing API logs across all sheets' },
        { label: 'Check Missing (Selected)', function: 'EW_checkMissingLogsForSelected', description: 'Find missing logs for selected rows' },
        { label: 'View Today\'s Summary', function: 'EW_showApiSummary', description: 'Show today\'s API call summary' },
        { label: 'Create Daily Report', function: 'EW_createDailyApiReport', description: 'Generate daily API usage report' },
        { label: 'Open Log Folders', function: 'EW_getApiResponsesFolderUrl', description: 'Get URLs to log folders' },
        { label: 'Cleanup Old Logs', function: 'EW_cleanupOldApiLogs', description: 'Delete logs older than 30 days' }
      ]
    },
    {
      name: '🔧 Utilities - Cache',
      items: [
        { label: 'Validate Recent Cache (All)', function: 'EW_validateAndFixRecentCache', description: 'Check recent cache data (last 7 days)' },
        { label: 'Validate Historical Cache (All)', function: 'EW_validateAndFixHistoricalCache', description: 'Check historical cache data (>7 days)' },
        { label: 'Validate Selected Rows', function: 'EW_validateSelectedRowsCache', description: 'Check cache for selected rows only' },
        { label: 'Clear File List Cache', function: 'EW_clearFileListCache', description: 'Clear in-memory file list cache' }
      ]
    },
    {
      name: '🔄 Continuation',
      items: [
        { label: 'Check All States', function: 'EW_checkAllContinuationStates', description: 'View all continuation states' },
        { label: 'Reset Continuation States', function: 'EW_resetContinuation', description: 'Clear all continuation states' }
      ]
    }
  ];

  return menuStructure;
}

/**
 * Format the menu sheet for better UX
 */
function EW_formatMenuSheet(sheet, dataRows) {
  // Set column widths
  sheet.setColumnWidth(1, 200); // Category
  sheet.setColumnWidth(2, 300); // Function
  sheet.setColumnWidth(3, 350); // Description
  sheet.setColumnWidth(4, 100); // Action

  // Freeze header row
  sheet.setFrozenRows(1);

  // Alternate row colors for better readability
  const dataRange = sheet.getRange(2, 1, dataRows, 4);

  // Apply banding
  dataRange.applyRowBanding(SpreadsheetApp.BandingTheme.LIGHT_GREY, true, false);

  // Center align action column
  sheet.getRange(2, 4, dataRows, 1).setHorizontalAlignment('center');

  // Bold category names
  for (let i = 2; i <= dataRows + 1; i++) {
    const categoryCell = sheet.getRange(i, 1);
    if (categoryCell.getValue()) {
      categoryCell.setFontWeight('bold');
    }
  }
}

/**
 * Set up data validation for action dropdowns
 */
function EW_setupMenuActions(sheet, menuStructure, dataRows) {
  // Create dropdown with Run/Clear options
  const rule = SpreadsheetApp.newDataValidation()
    .requireValueInList(['', '▶️ Run'], true)
    .setAllowInvalid(false)
    .build();

  sheet.getRange(2, 4, dataRows, 1).setDataValidation(rule);
}

/**
 * Protect menu sheet except for action column
 */
function EW_protectMenuSheet(sheet) {
  // Remove existing protections
  const protections = sheet.getProtections(SpreadsheetApp.ProtectionType.SHEET);
  protections.forEach(p => p.remove());

  // Protect entire sheet
  const protection = sheet.protect().setDescription('Menu Sheet - Protected');

  // Allow editing only in Action column (column 4)
  const actionRange = sheet.getRange(2, 4, sheet.getMaxRows() - 1, 1);
  protection.setUnprotectedRanges([actionRange]);

  // Remove all editors except owner
  protection.setWarningOnly(false);

  const me = Session.getEffectiveUser();
  protection.removeEditors(protection.getEditors());
  if (protection.canDomainEdit()) {
    protection.setDomainEdit(false);
  }
}

/**
 * OnEdit trigger handler for menu sheet
 * Executes functions when user selects "▶️ Run"
 */
function EW_onMenuSheetEdit(e) {
  if (!e || !e.range) return;

  const sheet = e.range.getSheet();
  if (sheet.getName() !== '📱 Menu') return;

  const row = e.range.getRow();
  const col = e.range.getColumn();

  // Check if Action column (column 4) was edited
  if (col !== 4 || row < 2) return;

  const value = e.value;
  if (value !== '▶️ Run') return;

  // Get the function name from column 2
  const functionName = sheet.getRange(row, 2).getValue();

  // Parse menu structure to find function
  const menuStructure = EW_parseMenuStructure();
  let functionToRun = null;

  for (const category of menuStructure) {
    const item = category.items.find(i => i.label === functionName);
    if (item) {
      functionToRun = item.function;
      break;
    }
  }

  if (!functionToRun) {
    SpreadsheetApp.getUi().alert(`Function not found: ${functionName}`);
    e.range.setValue('');
    return;
  }

  // Clear the dropdown
  e.range.setValue('');

  // Show running status
  sheet.getRange(row, 4).setValue('⏳ Running...');
  SpreadsheetApp.flush();

  try {
    // Execute the function
    if (typeof this[functionToRun] === 'function') {
      this[functionToRun]();
      sheet.getRange(row, 4).setValue('✅ Done');
    } else {
      throw new Error(`Function ${functionToRun} not found`);
    }
  } catch (error) {
    sheet.getRange(row, 4).setValue('❌ Error');
    SpreadsheetApp.getUi().alert(`Error running ${functionName}:\n${error.message}`);
  }

  // Clear status after 2 seconds
  Utilities.sleep(2000);
  sheet.getRange(row, 4).setValue('');
}

/**
 * Install menu sheet edit trigger
 */
function EW_installMenuSheetTrigger() {
  // Remove existing trigger if any
  const triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(trigger => {
    if (trigger.getHandlerFunction() === 'EW_onMenuSheetEdit') {
      ScriptApp.deleteTrigger(trigger);
    }
  });

  // Install new trigger
  ScriptApp.newTrigger('EW_onMenuSheetEdit')
    .forSpreadsheet(SpreadsheetApp.getActive())
    .onEdit()
    .create();

  console.log('Menu sheet edit trigger installed');
}

/**
 * Create or update menu sheet (call from onOpen or manually)
 */
function EW_updateMenuSheet() {
  const sheet = EW_createMenuSheet();
  EW_installMenuSheetTrigger();

  SpreadsheetApp.getUi().alert(
    'Menu Sheet Updated',
    'The 📱 Menu sheet has been created/updated with all available functions.\n\n' +
    'How to use:\n' +
    '1. Find the function you want to run in the list\n' +
    '2. Click the Action dropdown in that row\n' +
    '3. Select "▶️ Run"\n' +
    '4. The function will execute automatically\n\n' +
    'This is especially useful for mobile access!',
    SpreadsheetApp.getUi().ButtonSet.OK
  );

  return sheet;
}
