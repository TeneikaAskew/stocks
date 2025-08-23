/**
 * Trigger Management and Automation Functions
 * Centralized trigger setup, management, and automated execution functions
 */

// ===== TRIGGER SETUP AND MANAGEMENT =====

/**
 * Setup triggers only if they don't already exist (safe initialization)
 */
function EW_setupTriggersIfMissing() {
  try {
    console.log('Checking existing triggers...');
    EW_trace('TRIGGERS', 'Starting safe trigger setup - checking existing triggers');
    
    let triggers = ScriptApp.getProjectTriggers();
    let existingFunctions = triggers.map(t => t.getHandlerFunction());
    
    let setupCount = 0;
    let skippedCount = 0;
    let messages = [];
    
    // Check and setup 30-minute tracking trigger
    if (!EW_triggerExists(EW_TRIGGER_FUNCTIONS.AUTO_UPDATE)) {
      ScriptApp.newTrigger(EW_TRIGGER_FUNCTIONS.AUTO_UPDATE)
        .timeBased()
        .everyMinutes(EW_AUTO_TRACKING.TRIGGER_INTERVAL_MINUTES)
        .create();
      setupCount++;
      messages.push(`✅ Created: 30-minute tracking updates`);
      console.log(`Created trigger: ${EW_TRIGGER_FUNCTIONS.AUTO_UPDATE}`);
    } else {
      skippedCount++;
      messages.push(`⏭️ Exists: 30-minute tracking updates`);
      console.log(`Skipped existing trigger: ${EW_TRIGGER_FUNCTIONS.AUTO_UPDATE}`);
    }
    
    // Check and setup daily data fetch trigger (8 AM)
    if (!EW_triggerExists(EW_TRIGGER_FUNCTIONS.DAILY_DATA)) {
      ScriptApp.newTrigger(EW_TRIGGER_FUNCTIONS.DAILY_DATA)
        .timeBased()
        .everyDays(1)
        .atHour(EW_AUTO_TRACKING.DAILY_DATA_HOUR)
        .create();
      setupCount++;
      messages.push(`✅ Created: Daily data fetch (${EW_AUTO_TRACKING.DAILY_DATA_HOUR} AM)`);
      console.log(`Created trigger: ${EW_TRIGGER_FUNCTIONS.DAILY_DATA}`);
    } else {
      skippedCount++;
      messages.push(`⏭️ Exists: Daily data fetch (${EW_AUTO_TRACKING.DAILY_DATA_HOUR} AM)`);
      console.log(`Skipped existing trigger: ${EW_TRIGGER_FUNCTIONS.DAILY_DATA}`);
    }
    
    // Check and setup daily report trigger (9 AM)
    if (!EW_triggerExists(EW_TRIGGER_FUNCTIONS.DAILY_REPORT)) {
      ScriptApp.newTrigger(EW_TRIGGER_FUNCTIONS.DAILY_REPORT)
        .timeBased()
        .everyDays(1)
        .atHour(EW_AUTO_TRACKING.DAILY_REPORT_HOUR)
        .create();
      setupCount++;
      messages.push(`✅ Created: Daily success reports (${EW_AUTO_TRACKING.DAILY_REPORT_HOUR} AM)`);
      console.log(`Created trigger: ${EW_TRIGGER_FUNCTIONS.DAILY_REPORT}`);
    } else {
      skippedCount++;
      messages.push(`⏭️ Exists: Daily success reports (${EW_AUTO_TRACKING.DAILY_REPORT_HOUR} AM)`);
      console.log(`Skipped existing trigger: ${EW_TRIGGER_FUNCTIONS.DAILY_REPORT}`);
    }
    
    // Ensure success report exists
    EW_ensureSuccessReportExists();
    
    // Show results
    const summary = `Trigger Setup Summary:\n\n${messages.join('\n')}\n\n` +
                   `📊 Results: ${setupCount} created, ${skippedCount} already existed\n\n` +
                   `Total active triggers: ${triggers.length + setupCount}`;
    
    EW_safeAlert(
      'Smart Trigger Setup Complete',
      summary,
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    
    console.log(`Trigger setup complete: ${setupCount} created, ${skippedCount} skipped`);
    EW_trace('TRIGGERS', `Smart setup complete - ${setupCount} created, ${skippedCount} existed, ${setupCount + skippedCount} total managed`);
    
    return {
      created: setupCount,
      skipped: skippedCount,
      total: setupCount + skippedCount,
      messages: messages
    };
    
  } catch (error) {
    console.error('Error in smart trigger setup:', error);
    EW_trace('TRIGGERS', `Error in smart trigger setup: ${error.toString()}`);
    
    // Only show UI alerts if called from spreadsheet environment
    EW_safeAlert('Error', 'Failed to setup triggers: ' + error.toString());
    return { error: error.toString() };
  }
}

/**
 * Setup automated tracking with 30-minute intervals
 */
function EW_setupAutoTracking() {
  try {
    // First ensure success report exists
    EW_ensureSuccessReportExists();
    
    // Delete existing triggers to avoid duplicates
    EW_stopAutoTracking();
    
    // Create new 30-minute tracking trigger
    ScriptApp.newTrigger(EW_TRIGGER_FUNCTIONS.AUTO_UPDATE)
      .timeBased()
      .everyMinutes(EW_AUTO_TRACKING.TRIGGER_INTERVAL_MINUTES)
      .create();
    
    // Create daily report update trigger
    ScriptApp.newTrigger(EW_TRIGGER_FUNCTIONS.DAILY_REPORT)
      .timeBased()
      .everyDays(1)
      .atHour(EW_AUTO_TRACKING.DAILY_REPORT_HOUR)
      .create();
    
    // Create daily data fetch trigger
    ScriptApp.newTrigger(EW_TRIGGER_FUNCTIONS.DAILY_DATA)
      .timeBased()
      .everyDays(1)
      .atHour(EW_AUTO_TRACKING.DAILY_DATA_HOUR)
      .create();
    
    EW_safeAlert(
      'Auto Tracking Setup Complete',
      'Automated schedule created:\n\n' +
      `• ${EW_AUTO_TRACKING.DAILY_DATA_HOUR}:00 AM: Daily data fetch (EW_runAll)\n` +
      `• ${EW_AUTO_TRACKING.DAILY_REPORT_HOUR}:00 AM: Daily success report update\n` +
      `• Every ${EW_AUTO_TRACKING.TRIGGER_INTERVAL_MINUTES} minutes: Tracking data refresh\n\n` +
      'Historical data will be preserved permanently.',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    
    console.log('Auto tracking triggers created successfully');
    EW_trace('TRIGGERS', 'Auto tracking setup complete - 8AM daily runAll, 9AM reports, 30min updates');
    
  } catch (error) {
    console.error('Error setting up auto tracking:', error);
    EW_trace('TRIGGERS', `Error setting up auto tracking: ${error.toString()}`);
    
    // Only show UI alerts if called from spreadsheet environment
    EW_safeAlert('Error', 'Failed to setup auto tracking: ' + error.toString());
    throw error; // Re-throw for programmatic handling
  }
}

/**
 * Setup only the daily data fetch trigger (8 AM)
 */
function EW_setupDailyDataTrigger() {
  try {
    // Remove existing daily data triggers
    EW_stopDailyDataTrigger();
    
    // Create daily data fetch trigger
    ScriptApp.newTrigger(EW_TRIGGER_FUNCTIONS.DAILY_DATA)
      .timeBased()
      .everyDays(1)
      .atHour(EW_AUTO_TRACKING.DAILY_DATA_HOUR)
      .create();
    
    EW_safeAlert(
      'Daily Data Trigger Setup',
      `Daily data fetch scheduled for ${EW_AUTO_TRACKING.DAILY_DATA_HOUR}:00 AM.\n\n` +
      'This will run EW_runAll() every day to fetch fresh strategy data.',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    
    console.log('Daily data trigger created for 8 AM');
    EW_trace('TRIGGERS', `Daily data fetch trigger setup - ${EW_AUTO_TRACKING.DAILY_DATA_HOUR}AM EW_runAll`);
    
  } catch (error) {
    console.error('Error setting up daily data trigger:', error);
    EW_trace('TRIGGERS', `Error setting up daily data trigger: ${error.toString()}`);
    
    // Only show UI alerts if called from spreadsheet environment
    EW_safeAlert('Error', 'Failed to setup daily data trigger: ' + error.toString());
    throw error; // Re-throw for programmatic handling
  }
}

/**
 * Stop automated tracking by removing all triggers
 */
function EW_stopAutoTracking() {
  try {
    let triggers = ScriptApp.getProjectTriggers();
    let deletedCount = 0;
    
    triggers.forEach(trigger => {
      let handlerFunction = trigger.getHandlerFunction();
      if (handlerFunction === EW_TRIGGER_FUNCTIONS.AUTO_UPDATE || 
          handlerFunction === EW_TRIGGER_FUNCTIONS.DAILY_REPORT ||
          handlerFunction === EW_TRIGGER_FUNCTIONS.DAILY_DATA) {
        ScriptApp.deleteTrigger(trigger);
        deletedCount++;
        console.log(`Deleted trigger: ${handlerFunction}`);
      }
    });
    
    if (deletedCount > 0) {
      SpreadsheetApp.getUi().alert(
        'Auto Tracking Stopped',
        `Removed ${deletedCount} automated trigger(s).\n\n` +
        'All automated functions have been disabled:\n' +
        `• Daily data fetch (${EW_AUTO_TRACKING.DAILY_DATA_HOUR} AM)\n` +
        `• Daily reports (${EW_AUTO_TRACKING.DAILY_REPORT_HOUR} AM)\n` +
        `• ${EW_AUTO_TRACKING.TRIGGER_INTERVAL_MINUTES}-minute tracking updates\n\n` +
        'You can restart using "Setup Auto Tracking" from the menu.',
        SpreadsheetApp.getUi().ButtonSet.OK
      );
      console.log(`Deleted ${deletedCount} auto tracking triggers`);
      EW_trace('TRIGGERS', `Stopped auto tracking - removed ${deletedCount} triggers`);
    } else {
      SpreadsheetApp.getUi().alert(
        'No Auto Tracking Found',
        'No automated tracking triggers were found to remove.',
        SpreadsheetApp.getUi().ButtonSet.OK
      );
    }
  } catch (error) {
    console.error('Error stopping auto tracking:', error);
    EW_trace('TRIGGERS', `Error stopping auto tracking: ${error.toString()}`);
    
    // Only show UI alerts if called from spreadsheet environment
    EW_safeAlert('Error', 'Failed to stop auto tracking: ' + error.toString());
    throw error; // Re-throw for programmatic handling
  }
}

/**
 * Stop only the daily data fetch trigger
 */
function EW_stopDailyDataTrigger() {
  try {
    let triggers = ScriptApp.getProjectTriggers();
    let deletedCount = 0;
    
    triggers.forEach(trigger => {
      let handlerFunction = trigger.getHandlerFunction();
      if (handlerFunction === EW_TRIGGER_FUNCTIONS.DAILY_DATA) {
        ScriptApp.deleteTrigger(trigger);
        deletedCount++;
        console.log(`Deleted daily data trigger: ${handlerFunction}`);
      }
    });
    
    if (deletedCount > 0) {
      console.log(`Deleted ${deletedCount} daily data triggers`);
      EW_trace('TRIGGERS', `Stopped daily data fetch - removed ${deletedCount} triggers`);
    }
  } catch (error) {
    console.error('Error stopping daily data trigger:', error);
  }
}

/**
 * List all active triggers for debugging
 */
function EW_listActiveTriggers() {
  try {
    let triggers = ScriptApp.getProjectTriggers();
    console.log(`\n=== ACTIVE TRIGGERS (${triggers.length} total) ===`);
    
    if (triggers.length === 0) {
      console.log('No triggers found');
      SpreadsheetApp.getUi().alert('Active Triggers', 'No automated triggers are currently active.');
      return;
    }
    
    let triggerInfo = [];
    triggers.forEach((trigger, index) => {
      let handlerFunction = trigger.getHandlerFunction();
      let eventType = trigger.getEventType();
      let triggerSource = trigger.getTriggerSource();
      
      let description = `${index + 1}. ${handlerFunction}`;
      
      if (eventType === ScriptApp.EventType.CLOCK) {
        // Time-based trigger
        description += ` (Time-based)`;
      } else if (eventType === ScriptApp.EventType.ON_OPEN) {
        description += ` (On Open)`;
      } else if (eventType === ScriptApp.EventType.ON_EDIT) {
        description += ` (On Edit)`;
      } else {
        description += ` (${eventType})`;
      }
      
      triggerInfo.push(description);
      console.log(description);
    });
    
    SpreadsheetApp.getUi().alert(
      'Active Triggers',
      `Found ${triggers.length} active trigger(s):\n\n` + triggerInfo.join('\n'),
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    
  } catch (error) {
    console.error('Error listing triggers:', error);
  }
}

// ===== AUTOMATED EXECUTION FUNCTIONS =====

/**
 * Automated update function called by 30-minute trigger
 */
function EW_autoUpdateTracking() {
  try {
    console.log('Auto tracking update started at:', new Date());
    EW_trace('AUTO_UPDATE', 'Starting 30-minute tracking update');
    
    // Update all formulas to refresh data
    EW_setGFArrayFormulas();
    
    // Force recalculation
    SpreadsheetApp.flush();
    
    console.log('Auto tracking update completed successfully');
    EW_trace('AUTO_UPDATE', 'Completed 30-minute tracking update successfully');
    
  } catch (error) {
    console.error('Error in auto tracking update:', error);
    EW_trace('AUTO_UPDATE', `Error in tracking update: ${error.toString()}`);
    // Don't show UI alerts for automated functions to avoid interrupting users
  }
}

/**
 * Ensure Success Report sheet exists, create if not
 */
function EW_ensureSuccessReportExists() {
  try {
    let ss = SpreadsheetApp.getActiveSpreadsheet();
    let reportSheet = ss.getSheetByName('Success_Report');
    
    if (!reportSheet) {
      console.log('Creating Success Report sheet...');
      EW_trace('REPORT', 'Auto-creating Success Report sheet');
      EW_generateSuccessReport();
    } else {
      console.log('Success Report sheet already exists');
    }
  } catch (error) {
    console.error('Error ensuring Success Report exists:', error);
    EW_trace('REPORT', `Error ensuring Success Report exists: ${error.toString()}`);
  }
}

/**
 * Automated daily data fetch function (called by 8 AM trigger)
 */
function EW_dailyDataFetch() {
  try {
    console.log('Daily data fetch started at:', new Date());
    EW_trace('DAILY_FETCH', 'Starting automated daily data fetch at 8 AM');
    
    // Run all strategy data fetches
    EW_runAll();
    
    console.log('Daily data fetch completed successfully');
    EW_trace('DAILY_FETCH', 'Completed automated daily data fetch successfully');
    
  } catch (error) {
    console.error('Error in daily data fetch:', error);
    EW_trace('DAILY_FETCH', `Error in daily data fetch: ${error.toString()}`);
    // Don't show UI alerts for automated functions to avoid interrupting users
  }
}

/**
 * Verify and repair triggers - fix any missing triggers
 */
function EW_verifyAndRepairTriggers() {
  try {
    console.log('Verifying trigger health...');
    EW_trace('TRIGGERS', 'Starting trigger verification and repair');
    
    // First get validation results
    const validation = EW_validateTriggers();
    
    if (validation.isValid) {
      SpreadsheetApp.getUi().alert(
        'Triggers Healthy',
        '✅ All expected triggers are properly configured.\n\n' +
        `Found ${validation.total} active triggers.\n\n` +
        'No repairs needed.',
        SpreadsheetApp.getUi().ButtonSet.OK
      );
      return { status: 'healthy', total: validation.total };
    }
    
    // If there are missing triggers, offer to repair
    if (validation.missing && validation.missing.length > 0) {
      const response = SpreadsheetApp.getUi().alert(
        'Missing Triggers Detected',
        `❌ Found ${validation.missing.length} missing trigger(s):\n` +
        `${validation.missing.join(', ')}\n\n` +
        'Would you like to create the missing triggers?',
        SpreadsheetApp.getUi().ButtonSet.YES_NO
      );
      
      if (response === SpreadsheetApp.getUi().Button.YES) {
        // Setup missing triggers using the smart setup function
        const result = EW_setupTriggersIfMissing();
        
        if (result.created > 0) {
          SpreadsheetApp.getUi().alert(
            'Triggers Repaired',
            `✅ Successfully created ${result.created} missing trigger(s).\n\n` +
            'All triggers are now properly configured.',
            SpreadsheetApp.getUi().ButtonSet.OK
          );
          EW_trace('TRIGGERS', `Repair complete - created ${result.created} missing triggers`);
          return { status: 'repaired', created: result.created };
        } else {
          SpreadsheetApp.getUi().alert(
            'Repair Complete',
            'All triggers were already properly configured.',
            SpreadsheetApp.getUi().ButtonSet.OK
          );
          return { status: 'no_action_needed' };
        }
      } else {
        return { status: 'user_cancelled' };
      }
    }
    
    // Handle unexpected triggers
    if (validation.unexpected && validation.unexpected.length > 0) {
      SpreadsheetApp.getUi().alert(
        'Unexpected Triggers Found',
        `⚠️ Found ${validation.unexpected.length} unexpected trigger(s):\n` +
        `${validation.unexpected.join(', ')}\n\n` +
        'These may be from other scripts or manual setup.\n' +
        'Use "Stop All Auto Tracking" if you want to remove them.',
        SpreadsheetApp.getUi().ButtonSet.OK
      );
      return { status: 'unexpected_found', unexpected: validation.unexpected };
    }
    
  } catch (error) {
    console.error('Error in trigger verification:', error);
    EW_trace('TRIGGERS', `Error in trigger verification: ${error.toString()}`);
    
    // Only show UI alerts if called from spreadsheet environment
    EW_safeAlert('Error', 'Failed to verify triggers: ' + error.toString());
    return { status: 'error', error: error.toString() };
  }
}

/**
 * Test function to demonstrate environment detection and safe alerts
 * Can be called from script editor or spreadsheet
 */
function EW_testEnvironmentDetection() {
  try {
    console.log('=== ENVIRONMENT DETECTION TEST ===');
    
    const isSpreadsheet = EW_isSpreadsheetEnvironment();
    console.log(`Spreadsheet environment detected: ${isSpreadsheet}`);
    EW_trace('TEST', `Environment test - spreadsheet: ${isSpreadsheet}`);
    
    if (isSpreadsheet) {
      console.log('UI available - showing spreadsheet alert');
      EW_safeAlert(
        'Environment Test',
        '✅ Running in spreadsheet environment.\n\nUI alerts are available.',
        SpreadsheetApp.getUi().ButtonSet.OK
      );
    } else {
      console.log('UI not available - logging only');
      EW_safeAlert(
        'Environment Test', 
        'Running outside spreadsheet (script editor, trigger, etc.)\n\nThis message logged to console only.'
      );
    }
    
    return {
      environment: isSpreadsheet ? 'spreadsheet' : 'script_editor',
      uiAvailable: isSpreadsheet,
      timestamp: new Date().toISOString()
    };
    
  } catch (error) {
    console.error('Error in environment test:', error);
    EW_trace('TEST', `Environment test error: ${error.toString()}`);
    return { error: error.toString() };
  }
}

// ===== TRIGGER VALIDATION AND HEALTH CHECK =====

/**
 * Validate that all expected triggers are in place
 */
function EW_validateTriggers() {
  try {
    let triggers = ScriptApp.getProjectTriggers();
    let expectedTriggers = [
      EW_TRIGGER_FUNCTIONS.DAILY_DATA, 
      EW_TRIGGER_FUNCTIONS.DAILY_REPORT, 
      EW_TRIGGER_FUNCTIONS.AUTO_UPDATE
    ];
    let foundTriggers = triggers.map(t => t.getHandlerFunction());
    
    let missing = expectedTriggers.filter(expected => !foundTriggers.includes(expected));
    let unexpected = foundTriggers.filter(found => !expectedTriggers.includes(found));
    
    let report = `=== TRIGGER VALIDATION ===\n`;
    report += `Expected: ${expectedTriggers.length} triggers\n`;
    report += `Found: ${foundTriggers.length} triggers\n\n`;
    
    if (missing.length > 0) {
      report += `❌ Missing triggers: ${missing.join(', ')}\n`;
    }
    
    if (unexpected.length > 0) {
      report += `⚠️ Unexpected triggers: ${unexpected.join(', ')}\n`;
    }
    
    if (missing.length === 0 && unexpected.length === 0) {
      report += `✅ All expected triggers are properly configured`;
    }
    
    console.log(report);
    EW_trace('VALIDATION', report.replace(/\n/g, ' | '));
    
    return {
      isValid: missing.length === 0,
      missing,
      unexpected,
      total: foundTriggers.length
    };
    
  } catch (error) {
    console.error('Error validating triggers:', error);
    return { isValid: false, error: error.toString() };
  }
}
