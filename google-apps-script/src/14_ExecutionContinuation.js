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
      processedStrategies.push(strategy);
      
      if (result.updated > 0) {
        EW_trace('ACTIVE_TRACKING', `Updated ${result.updated} of ${result.checked} active positions in ${strategy}`);
        console.log(`ACTIVE TRACKING: ${strategy} - Updated ${result.updated}/${result.checked} positions`);
      } else if (result.checked > 0) {
        console.log(`ACTIVE TRACKING: ${strategy} - Checked ${result.checked} positions, no updates needed`);
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
  // Clear state
  EW_clearContinuationState();
  console.log('Cleared continuation state');
  
  // Remove continuation triggers
  const triggers = ScriptApp.getProjectTriggers();
  let removed = 0;
  triggers.forEach(trigger => {
    if (trigger.getHandlerFunction() === 'EW_continuationTrigger') {
      ScriptApp.deleteTrigger(trigger);
      removed++;
    }
  });
  
  console.log(`Removed ${removed} continuation triggers`);
  
  return { stateCleared: true, triggersRemoved: removed };
}