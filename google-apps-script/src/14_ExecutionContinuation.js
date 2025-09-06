/**
 * Execution Continuation System
 * Handles long-running processes that exceed Google Apps Script's 30-minute execution limit
 * Stores progress in PropertiesService and automatically re-triggers to continue
 */

/**
 * Save continuation state for active position tracking
 * @param {Object} state - Current execution state
 */
function EW_saveContinuationState(state) {
  const scriptProperties = PropertiesService.getScriptProperties();
  scriptProperties.setProperty('ACTIVE_TRACKING_STATE', JSON.stringify({
    ...state,
    lastSaved: new Date().toISOString()
  }));
}

/**
 * Get continuation state
 * @returns {Object|null} Saved state or null if none exists
 */
function EW_getContinuationState() {
  const scriptProperties = PropertiesService.getScriptProperties();
  const stateStr = scriptProperties.getProperty('ACTIVE_TRACKING_STATE');
  
  if (!stateStr) return null;
  
  try {
    const state = JSON.parse(stateStr);
    
    // Check if state is too old (more than 2 hours)
    const lastSaved = new Date(state.lastSaved);
    const now = new Date();
    const hoursElapsed = (now - lastSaved) / (1000 * 60 * 60);
    
    if (hoursElapsed > 2) {
      console.log('Continuation state is too old, discarding');
      EW_clearContinuationState();
      return null;
    }
    
    return state;
  } catch (error) {
    console.error('Error parsing continuation state:', error);
    return null;
  }
}

/**
 * Clear continuation state
 */
function EW_clearContinuationState() {
  const scriptProperties = PropertiesService.getScriptProperties();
  scriptProperties.deleteProperty('ACTIVE_TRACKING_STATE');
}

/**
 * Enhanced version of EW_updateActiveStrikeHits with continuation support
 * Automatically resumes from where it left off if time limit is approaching
 */
function EW_updateActiveStrikeHitsWithContinuation() {
  const MAX_RUNTIME_MS = 25 * 60 * 1000; // 25 minutes (leaving 5 min buffer)
  const startTime = new Date();
  
  // Check for existing state
  const savedState = EW_getContinuationState();
  let currentStrategyIndex = savedState ? savedState.currentStrategyIndex : 0;
  let totalChecked = savedState ? savedState.totalChecked : 0;
  let totalUpdated = savedState ? savedState.totalUpdated : 0;
  let totalSkipped = savedState ? savedState.totalSkipped : 0;
  let totalExpired = savedState ? savedState.totalExpired : 0;
  let processedStrategies = savedState ? savedState.processedStrategies : [];
  
  if (savedState) {
    console.log(`ACTIVE TRACKING: Resuming from strategy index ${currentStrategyIndex}`);
    console.log(`ACTIVE TRACKING: Already processed: ${processedStrategies.join(', ')}`);
    EW_trace('ACTIVE_TRACKING', `Resuming from saved state. Already checked ${totalChecked} positions`, true);
  } else {
    console.log(`ACTIVE TRACKING: Starting fresh run at ${startTime.toISOString()}`);
    Logger.log(`ACTIVE TRACKING: Strike_Hit update started at ${startTime.toISOString()}`);
    EW_trace('ACTIVE_TRACKING', 'Starting Strike_Hit updates for active positions', true);
  }
  
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  let errors = [];
  
  // Process strategies starting from where we left off
  for (let i = currentStrategyIndex; i < strategies.length; i++) {
    const strategy = strategies[i];
    
    // Check if we're approaching time limit
    const elapsedMs = new Date() - startTime;
    if (elapsedMs > MAX_RUNTIME_MS) {
      console.log(`ACTIVE TRACKING: Approaching time limit after ${Math.round(elapsedMs / 1000)}s`);
      
      // Save state
      const state = {
        currentStrategyIndex: i,
        totalChecked: totalChecked,
        totalUpdated: totalUpdated,
        totalSkipped: totalSkipped,
        totalExpired: totalExpired,
        processedStrategies: processedStrategies,
        errors: errors,
        startTime: savedState ? savedState.startTime : startTime.toISOString(),
        continuationCount: (savedState?.continuationCount || 0) + 1
      };
      
      EW_saveContinuationState(state);
      
      // Schedule continuation trigger
      EW_scheduleContinuation();
      
      const msg = `Partial update due to time limit.\n` +
        `Processed: ${processedStrategies.length} of ${strategies.length} strategies\n` +
        `Checked: ${totalChecked} positions\n` +
        `Updated: ${totalUpdated} positions\n` +
        `Skipped: ${totalSkipped} positions (already updated)\n` +
        `Continuation scheduled for remaining strategies`;
      
      console.log(`ACTIVE TRACKING: ${msg}`);
      EW_trace('ACTIVE_TRACKING', msg, true);
      
      if (EW_isSpreadsheetEnvironment()) {
        EW_safeAlert('Active Position Update - Partial', msg);
      }
      
      return { 
        checked: totalChecked, 
        updated: totalUpdated, 
        partial: true,
        continuationScheduled: true 
      };
    }
    
    try {
      console.log(`ACTIVE TRACKING: Processing ${strategy} sheet...`);
      const result = EW_updateStrategyActiveStrikes(ss, strategy);
      totalChecked += result.checked;
      totalUpdated += result.updated;
      totalSkipped += (result.skipped || 0);
      totalExpired += (result.expired || 0);
      processedStrategies.push(strategy);
      
      if (result.updated > 0) {
        EW_trace('ACTIVE_TRACKING', `Updated ${result.updated} of ${result.checked} active positions in ${strategy}` + 
          (result.skipped > 0 ? ` (skipped ${result.skipped} already updated)` : ''));
        console.log(`ACTIVE TRACKING: ${strategy} - Updated ${result.updated}/${result.checked} positions` +
          (result.skipped > 0 ? `, skipped ${result.skipped}` : ''));
      } else if (result.checked > 0) {
        console.log(`ACTIVE TRACKING: ${strategy} - Checked ${result.checked} positions, no updates needed`);
      } else if (result.skipped > 0) {
        console.log(`ACTIVE TRACKING: ${strategy} - All ${result.skipped} positions already updated today`);
      }
      
      // Update current index for next iteration
      currentStrategyIndex = i + 1;
      
    } catch (e) {
      errors.push(`${strategy}: ${e.message}`);
      EW_trace('ACTIVE_TRACKING', `Error updating ${strategy}: ${e.message}`, true);
      console.error(`ACTIVE TRACKING ERROR: ${strategy} - ${e.message}`);
    }
  }
  
  // All strategies processed - clear state
  EW_clearContinuationState();
  
  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);
  
  const msg = `Active position update complete.\n` +
    `Checked: ${totalChecked} positions\n` +
    `Updated: ${totalUpdated} positions\n` +
    `Skipped: ${totalSkipped} positions (already updated)\n` +
    `Expired: ${totalExpired} positions (>7 days old)\n` +
    `Strategies: ${processedStrategies.length}\n` +
    `Duration: ${duration} seconds` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');
  
  console.log(`ACTIVE TRACKING: Completed in ${duration} seconds`);
  Logger.log(`ACTIVE TRACKING: Completed - Checked ${totalChecked}, Updated ${totalUpdated}, Duration ${duration}s`);
  
  EW_trace('ACTIVE_TRACKING', msg, true);
  if (EW_isSpreadsheetEnvironment()) {
    EW_safeAlert('Active Position Update Complete', msg);
  }
  
  // Create daily API report after tracking update
  try {
    EW_createDailyApiReport();
    console.log('ACTIVE TRACKING: Daily API report created');
  } catch (error) {
    console.error(`ACTIVE TRACKING: Failed to create API report: ${error.message}`);
  }
  
  return { checked: totalChecked, updated: totalUpdated, duration: duration, complete: true };
}

/**
 * Schedule a continuation trigger
 * Creates a time-based trigger to run again in 1 minute
 */
function EW_scheduleContinuation() {
  // Delete any existing continuation triggers first
  const triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(trigger => {
    if (trigger.getHandlerFunction() === 'EW_continuationTrigger') {
      ScriptApp.deleteTrigger(trigger);
    }
  });
  
  // Create new trigger to run in 1 minute
  ScriptApp.newTrigger('EW_continuationTrigger')
    .timeBased()
    .after(1 * 60 * 1000) // 1 minute
    .create();
    
  console.log('ACTIVE TRACKING: Continuation trigger scheduled for 1 minute from now');
}

/**
 * Continuation trigger function
 * Called by time-based trigger to resume processing
 */
function EW_continuationTrigger() {
  console.log('ACTIVE TRACKING: Continuation trigger fired');
  
  // Check if there's a state to continue from
  const state = EW_getContinuationState();
  if (!state) {
    console.log('ACTIVE TRACKING: No continuation state found, trigger removed');
    return;
  }
  
  console.log(`ACTIVE TRACKING: Continuing from strategy index ${state.currentStrategyIndex}`);
  console.log(`ACTIVE TRACKING: This is continuation #${state.continuationCount + 1}`);
  
  // Continue the update process
  EW_updateActiveStrikeHitsWithContinuation();
}

/**
 * Modified trigger setup to use continuation version
 * Updates the 5 PM daily trigger to use the continuation-aware function
 */
function EW_updateDailyTriggerForContinuation() {
  // Remove old trigger
  const triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(trigger => {
    if (trigger.getHandlerFunction() === 'EW_updateActiveStrikeHits') {
      ScriptApp.deleteTrigger(trigger);
      console.log('Removed old EW_updateActiveStrikeHits trigger');
    }
  });
  
  // Create new trigger with continuation support
  ScriptApp.newTrigger('EW_updateActiveStrikeHitsWithContinuation')
    .timeBased()
    .everyDays(1)
    .atHour(17) // 5 PM
    .nearMinute(0)
    .inTimezone('America/New_York')
    .create();
    
  console.log('Created new trigger with continuation support for 5 PM ET daily');
}

/**
 * Manual function to test continuation
 * Simulates a timeout after processing a few strategies
 */
function EW_testContinuation() {
  // Set a very short max runtime for testing (2 minutes)
  const TEST_MAX_RUNTIME_MS = 2 * 60 * 1000;
  const startTime = new Date();
  
  const savedState = EW_getContinuationState();
  let currentStrategyIndex = savedState ? savedState.currentStrategyIndex : 0;
  
  console.log(`TEST: Starting at strategy index ${currentStrategyIndex}`);
  
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  
  // Process only a few strategies then simulate timeout
  for (let i = currentStrategyIndex; i < Math.min(currentStrategyIndex + 2, strategies.length); i++) {
    console.log(`TEST: Processing ${strategies[i]}`);
    Utilities.sleep(1000); // Simulate work
  }
  
  // Save state
  const state = {
    currentStrategyIndex: Math.min(currentStrategyIndex + 2, strategies.length),
    totalChecked: 100,
    totalUpdated: 50,
    processedStrategies: strategies.slice(0, Math.min(currentStrategyIndex + 2, strategies.length)),
    errors: [],
    startTime: startTime.toISOString(),
    continuationCount: (savedState?.continuationCount || 0) + 1
  };
  
  EW_saveContinuationState(state);
  console.log('TEST: State saved, would schedule continuation');
  
  return state;
}

/**
 * Clear any stuck continuation state and triggers
 * Use this if the system gets stuck
 */
function EW_resetContinuation() {
  // Clear all continuation states
  const scriptProperties = PropertiesService.getScriptProperties();
  scriptProperties.deleteProperty('ACTIVE_TRACKING_STATE');
  scriptProperties.deleteProperty('BACKFILL_STATE');
  scriptProperties.deleteProperty('BACKFILL_SELECTED_STATE');
  console.log('Cleared all continuation states');
  
  // Remove continuation triggers
  const triggers = ScriptApp.getProjectTriggers();
  let removed = 0;
  triggers.forEach(trigger => {
    const func = trigger.getHandlerFunction();
    if (func === 'EW_continuationTrigger' || 
        func === 'EW_backfillContinuationTrigger' || 
        func === 'EW_backfillSelectedContinuationTrigger') {
      ScriptApp.deleteTrigger(trigger);
      removed++;
    }
  });
  
  console.log(`Removed ${removed} continuation triggers`);
  
  return { stateCleared: true, triggersRemoved: removed };
}

/**
 * Save continuation state for backfill
 * @param {Object} state - Current execution state
 * @param {string} stateKey - Key to identify the state (BACKFILL_STATE or BACKFILL_SELECTED_STATE)
 */
function EW_saveBackfillState(state, stateKey = 'BACKFILL_STATE') {
  const scriptProperties = PropertiesService.getScriptProperties();
  scriptProperties.setProperty(stateKey, JSON.stringify({
    ...state,
    lastSaved: new Date().toISOString()
  }));
}

/**
 * Get backfill continuation state
 * @param {string} stateKey - Key to identify the state
 * @returns {Object|null} Saved state or null if none exists
 */
function EW_getBackfillState(stateKey = 'BACKFILL_STATE') {
  const scriptProperties = PropertiesService.getScriptProperties();
  const stateStr = scriptProperties.getProperty(stateKey);
  
  if (!stateStr) return null;
  
  try {
    const state = JSON.parse(stateStr);
    
    // Check if state is too old (more than 2 hours)
    const lastSaved = new Date(state.lastSaved);
    const now = new Date();
    const hoursElapsed = (now - lastSaved) / (1000 * 60 * 60);
    
    if (hoursElapsed > 2) {
      console.log('Backfill state is too old, discarding');
      scriptProperties.deleteProperty(stateKey);
      return null;
    }
    
    return state;
  } catch (error) {
    console.error('Error parsing backfill state:', error);
    return null;
  }
}

/**
 * Clear backfill continuation state
 * @param {string} stateKey - Key to identify the state
 */
function EW_clearBackfillState(stateKey = 'BACKFILL_STATE') {
  const scriptProperties = PropertiesService.getScriptProperties();
  scriptProperties.deleteProperty(stateKey);
}

/**
 * Enhanced version of EW_backfillHistoricalTracking with continuation support
 * Automatically resumes from where it left off if time limit is approaching
 */
function EW_backfillHistoricalTrackingWithContinuation() {
  const MAX_RUNTIME_MS = 25 * 60 * 1000; // 25 minutes (leaving 5 min buffer)
  const startTime = new Date();
  
  // Check for existing state
  const savedState = EW_getBackfillState('BACKFILL_STATE');
  let currentStrategyIndex = savedState ? savedState.currentStrategyIndex : 0;
  let totalBackfilled = savedState ? savedState.totalBackfilled : 0;
  let processedStrategies = savedState ? savedState.processedStrategies : [];
  
  if (savedState) {
    console.log(`BACKFILL: Resuming from strategy index ${currentStrategyIndex}`);
    console.log(`BACKFILL: Already processed: ${processedStrategies.join(', ')}`);
    EW_trace('BACKFILL', `Resuming from saved state. Already backfilled ${totalBackfilled} positions`, true);
  } else {
    console.log(`BACKFILL: Starting fresh run at ${startTime.toISOString()}`);
    EW_trace('BACKFILL', 'Starting historical tracking backfill', true);
  }
  
  const ss = SpreadsheetApp.getActive();
  const strategies = Object.keys(EW.STRATEGY_ENDPOINTS);
  let errors = [];
  
  // Process strategies starting from where we left off
  for (let i = currentStrategyIndex; i < strategies.length; i++) {
    const strategy = strategies[i];
    
    // Check if we're approaching time limit
    const elapsedMs = new Date() - startTime;
    if (elapsedMs > MAX_RUNTIME_MS) {
      console.log(`BACKFILL: Approaching time limit after ${Math.round(elapsedMs / 1000)}s`);
      
      // Save state
      const state = {
        currentStrategyIndex: i,
        totalBackfilled: totalBackfilled,
        processedStrategies: processedStrategies,
        errors: errors,
        startTime: savedState ? savedState.startTime : startTime.toISOString(),
        continuationCount: (savedState?.continuationCount || 0) + 1
      };
      
      EW_saveBackfillState(state, 'BACKFILL_STATE');
      
      // Schedule continuation trigger
      EW_scheduleBackfillContinuation();
      
      const msg = `Partial backfill due to time limit.\n` +
        `Processed: ${processedStrategies.length} of ${strategies.length} strategies\n` +
        `Backfilled: ${totalBackfilled} positions\n` +
        `Continuation scheduled for remaining strategies`;
      
      console.log(`BACKFILL: ${msg}`);
      EW_trace('BACKFILL', msg, true);
      
      if (EW_isSpreadsheetEnvironment()) {
        EW_safeAlert('Historical Backfill - Partial', msg);
      }
      
      return { 
        backfilled: totalBackfilled,
        partial: true,
        continuationScheduled: true 
      };
    }
    
    try {
      console.log(`BACKFILL: Processing ${strategy} sheet...`);
      const backfilled = EW_backfillStrategyTracking(ss, strategy);
      if (backfilled > 0) {
        totalBackfilled += backfilled;
        processedStrategies.push(strategy);
        EW_trace('BACKFILL', `Backfilled ${backfilled} positions in ${strategy}`);
        console.log(`BACKFILL: ${strategy} - Backfilled ${backfilled} positions`);
      } else {
        console.log(`BACKFILL: ${strategy} - No positions to backfill`);
      }
      
      // Update current index for next iteration
      currentStrategyIndex = i + 1;
      
    } catch (e) {
      errors.push(`${strategy}: ${e.message}`);
      EW_trace('BACKFILL', `Error backfilling ${strategy}: ${e.message}`, true);
      console.error(`BACKFILL ERROR: ${strategy} - ${e.message}`);
    }
  }
  
  // All strategies processed - clear state
  EW_clearBackfillState('BACKFILL_STATE');
  
  // Create daily API report after backfill
  try {
    EW_createDailyApiReport();
    console.log('BACKFILL: Daily API report created');
    EW_trace('BACKFILL', 'Daily API summary report created');
  } catch (error) {
    console.error(`BACKFILL: Failed to create API report: ${error.message}`);
    EW_trace('BACKFILL', `Failed to create API report: ${error.message}`);
  }
  
  // Apply formatting to all processed sheets
  if (totalBackfilled > 0) {
    EW_trace('BACKFILL', 'Applying Day Check formatting to all processed sheets...', true);
    for (const strategy of processedStrategies) {
      try {
        const sheet = ss.getSheetByName(strategy);
        if (sheet && sheet.getLastRow() > 1) {
          const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
          const hdrMap = EW_headerMap(headers);
          if (hdrMap.day0CheckCol || hdrMap.day1CheckCol) {
            EW_formatDayCheckColumns(sheet, hdrMap, strategy);
            EW_trace('BACKFILL', `Applied formatting to ${strategy}`);
          }
        }
      } catch (e) {
        EW_trace('BACKFILL', `Failed to apply formatting to ${strategy}: ${e.message}`);
      }
    }
    SpreadsheetApp.flush();
  }
  
  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);
  
  const msg = `Historical backfill complete.\n` +
    `Processed ${totalBackfilled} positions across ${processedStrategies.length} strategies.\n` +
    `Duration: ${duration} seconds` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.join('\n')}` : '');
  
  console.log(`BACKFILL: Completed in ${duration} seconds`);
  EW_trace('BACKFILL', msg, true);
  
  if (EW_isSpreadsheetEnvironment()) {
    EW_safeAlert('Historical Backfill Complete', msg);
  }
  
  return { backfilled: totalBackfilled, duration: duration, complete: true };
}

/**
 * Schedule a backfill continuation trigger
 * @param {string} functionName - The function to continue (used for logging and state management)
 */
function EW_scheduleBackfillContinuation(functionName = 'EW_backfillHistoricalTracking') {
  // Delete any existing backfill continuation triggers first
  const triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(trigger => {
    if (trigger.getHandlerFunction() === 'EW_backfillContinuationTrigger') {
      ScriptApp.deleteTrigger(trigger);
    }
  });
  
  // Store the function name in properties so the trigger knows what to call
  const scriptProperties = PropertiesService.getScriptProperties();
  scriptProperties.setProperty('BACKFILL_FUNCTION', functionName);
  
  // Create new trigger to run in 1 minute
  ScriptApp.newTrigger('EW_backfillContinuationTrigger')
    .timeBased()
    .after(1 * 60 * 1000) // 1 minute
    .create();
    
  console.log(`BACKFILL: Continuation trigger scheduled for ${functionName} in 1 minute`);
}

/**
 * Backfill continuation trigger function
 */
function EW_backfillContinuationTrigger() {
  console.log('BACKFILL: Continuation trigger fired');
  
  // Get the function name to continue
  const scriptProperties = PropertiesService.getScriptProperties();
  const functionName = scriptProperties.getProperty('BACKFILL_FUNCTION') || 'EW_backfillHistoricalTracking';
  
  // Check if there's a state to continue from
  const state = EW_getBackfillState('BACKFILL_STATE');
  if (!state) {
    console.log('BACKFILL: No continuation state found, trigger removed');
    scriptProperties.deleteProperty('BACKFILL_FUNCTION');
    return;
  }
  
  console.log(`BACKFILL: Continuing ${functionName} from strategy index ${state.currentStrategyIndex}`);
  console.log(`BACKFILL: This is continuation #${state.continuationCount + 1}`);
  
  // Continue the appropriate backfill process
  if (functionName === 'EW_backfillHistoricalTracking') {
    EW_backfillHistoricalTracking();
  } else if (functionName === 'EW_backfillHistoricalTrackingWithContinuation') {
    EW_backfillHistoricalTrackingWithContinuation();
  }
  
  // Clean up the function name property after use
  scriptProperties.deleteProperty('BACKFILL_FUNCTION');
}

/**
 * Enhanced version of EW_backfillSelectedRows with continuation support
 * Processes selected rows with automatic resume if time limit is reached
 */
function EW_backfillSelectedRowsWithContinuation() {
  const MAX_RUNTIME_MS = 25 * 60 * 1000; // 25 minutes (leaving 5 min buffer)
  const startTime = new Date();
  
  // Get saved state or initialize new selection
  const savedState = EW_getBackfillState('BACKFILL_SELECTED_STATE');
  
  let sheet, startRow, numRows, currentRowIndex;
  
  if (savedState) {
    // Resuming from saved state
    sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(savedState.sheetName);
    startRow = savedState.startRow;
    numRows = savedState.numRows;
    currentRowIndex = savedState.currentRowIndex;
    
    console.log(`BACKFILL SELECTED: Resuming from row ${currentRowIndex + 1} of ${numRows}`);
    EW_trace('BACKFILL', `Resuming selected rows backfill from row ${currentRowIndex + 1} of ${numRows}`, true);
  } else {
    // New selection
    sheet = SpreadsheetApp.getActiveSheet();
    const range = sheet.getActiveRange();
    
    if (!range) {
      EW_safeAlert('No Selection', 'Please select rows to backfill');
      return;
    }
    
    startRow = range.getRow();
    numRows = range.getNumRows();
    currentRowIndex = 0;
    
    // Skip if header row is selected
    if (startRow === 1) {
      EW_safeAlert('Invalid Selection', 'Please select data rows, not the header row');
      return;
    }
    
    console.log(`BACKFILL SELECTED: Starting backfill of ${numRows} rows from row ${startRow}`);
    EW_trace('BACKFILL', `Backfilling ${numRows} selected rows starting at row ${startRow}`, true);
  }
  
  // Get headers
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const hdrMap = EW_headerMap(headers);
  
  // Get the data range
  const dataRange = sheet.getRange(startRow, 1, numRows, sheet.getLastColumn());
  
  // Process rows starting from where we left off
  let processedCount = savedState ? savedState.processedCount : 0;
  let errors = savedState ? savedState.errors : [];
  
  for (let i = currentRowIndex; i < numRows; i++) {
    // Check if we're approaching time limit
    const elapsedMs = new Date() - startTime;
    if (elapsedMs > MAX_RUNTIME_MS) {
      console.log(`BACKFILL SELECTED: Approaching time limit after ${Math.round(elapsedMs / 1000)}s`);
      
      // Save state
      const state = {
        sheetName: sheet.getName(),
        startRow: startRow,
        numRows: numRows,
        currentRowIndex: i,
        processedCount: processedCount,
        errors: errors,
        startTime: savedState ? savedState.startTime : startTime.toISOString(),
        continuationCount: (savedState?.continuationCount || 0) + 1
      };
      
      EW_saveBackfillState(state, 'BACKFILL_SELECTED_STATE');
      
      // Schedule continuation
      EW_scheduleSelectedBackfillContinuation();
      
      const msg = `Partial backfill due to time limit.\n` +
        `Processed: ${processedCount} of ${numRows} rows\n` +
        `Continuation scheduled to resume at row ${i + 1}`;
      
      console.log(`BACKFILL SELECTED: ${msg}`);
      EW_trace('BACKFILL', msg, true);
      
      if (EW_isSpreadsheetEnvironment()) {
        EW_safeAlert('Selected Rows Backfill - Partial', msg);
      }
      
      return {
        processed: processedCount,
        partial: true,
        continuationScheduled: true
      };
    }
    
    const rowNum = startRow + i;
    const rowData = sheet.getRange(rowNum, 1, 1, sheet.getLastColumn()).getValues()[0];
    
    try {
      // Get required data
      const ticker = hdrMap.tickerCol ? rowData[hdrMap.tickerCol - 1] : null;
      const runDate = hdrMap.runDateCol ? rowData[hdrMap.runDateCol - 1] : null;
      const strike = hdrMap.strikeCol ? parseFloat(rowData[hdrMap.strikeCol - 1]) : null;
      const expDate = hdrMap.expDateCol ? rowData[hdrMap.expDateCol - 1] : null;
      const strategy = sheet.getName();
      
      if (!ticker || !runDate) {
        console.log(`Row ${rowNum}: Skipping - missing ticker or run date`);
        continue;
      }
      
      // Process the row (existing backfill logic)
      const runDateObj = new Date(runDate);
      const expDateObj = expDate ? new Date(expDate) : new Date();
      
      // Get historical data from Yahoo
      const yahoData = EW_getYahooHistoricalRange(ticker, runDateObj, expDateObj, true);
      
      if (yahoData && yahoData.data && yahoData.data.length > 0) {
        // Analyze the data
        const analysis = EW_analyzeHistoricalData(
          ticker, strategy, strike, yahoData.data, runDateObj, null, yahoData.raw
        );
        
        // Update the row using centralized function
        EW_updateBackfillColumns(dataRange, i, hdrMap, analysis);
        
        processedCount++;
        console.log(`Row ${rowNum}: Backfilled ${ticker}`);
      } else {
        console.log(`Row ${rowNum}: No data available for ${ticker}`);
      }
      
    } catch (error) {
      const errorMsg = `Row ${rowNum}: Error - ${error.message}`;
      errors.push(errorMsg);
      console.error(errorMsg);
      EW_trace('BACKFILL', errorMsg);
    }
    
    // Update for next iteration
    currentRowIndex = i + 1;
  }
  
  // All rows processed - clear state
  EW_clearBackfillState('BACKFILL_SELECTED_STATE');
  
  // Create daily API report after backfill
  try {
    EW_createDailyApiReport();
    console.log('BACKFILL SELECTED: Daily API report created');
  } catch (error) {
    console.error(`BACKFILL SELECTED: Failed to create API report: ${error.message}`);
  }
  
  // Apply formatting to the sheet if any rows were processed
  if (processedCount > 0) {
    try {
      EW_formatDayCheckColumns(sheet, hdrMap, sheet.getName());
      EW_trace('BACKFILL', `Applied Day Check formatting for selected rows`);
    } catch (e) {
      EW_trace('BACKFILL', `Failed to apply formatting: ${e.message}`);
    }
    SpreadsheetApp.flush();
  }
  
  const endTime = new Date();
  const duration = Math.round((endTime - startTime) / 1000);
  
  const msg = `Selected rows backfill complete.\n` +
    `Processed: ${processedCount} of ${numRows} rows\n` +
    `Duration: ${duration} seconds` +
    (errors.length > 0 ? `\n\nErrors:\n${errors.slice(0, 5).join('\n')}` : '');
  
  console.log(`BACKFILL SELECTED: Completed in ${duration} seconds`);
  EW_trace('BACKFILL', msg, true);
  
  if (EW_isSpreadsheetEnvironment()) {
    EW_safeAlert('Selected Rows Backfill Complete', msg);
  }
  
  // Force sheet refresh
  SpreadsheetApp.flush();
  
  return { processed: processedCount, duration: duration, complete: true };
}

/**
 * Schedule a continuation trigger for selected rows backfill
 */
function EW_scheduleSelectedBackfillContinuation() {
  // Delete any existing triggers first
  const triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(trigger => {
    if (trigger.getHandlerFunction() === 'EW_backfillSelectedContinuationTrigger') {
      ScriptApp.deleteTrigger(trigger);
    }
  });
  
  // Create new trigger to run in 1 minute
  ScriptApp.newTrigger('EW_backfillSelectedContinuationTrigger')
    .timeBased()
    .after(1 * 60 * 1000) // 1 minute
    .create();
    
  console.log('BACKFILL SELECTED: Continuation trigger scheduled for 1 minute from now');
}

/**
 * Continuation trigger for selected rows backfill
 */
function EW_backfillSelectedContinuationTrigger() {
  console.log('BACKFILL SELECTED: Continuation trigger fired');
  
  // Check if there's a state to continue from
  const state = EW_getBackfillState('BACKFILL_SELECTED_STATE');
  if (!state) {
    console.log('BACKFILL SELECTED: No continuation state found, trigger removed');
    return;
  }
  
  console.log(`BACKFILL SELECTED: Continuing from row ${state.currentRowIndex + 1} of ${state.numRows}`);
  console.log(`BACKFILL SELECTED: This is continuation #${state.continuationCount + 1}`);
  
  // Continue the backfill process
  EW_backfillSelectedRowsWithContinuation();
}