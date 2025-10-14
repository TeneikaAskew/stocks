/**
 * Trigger Management and Automation Functions
 * Centralized trigger setup, management, and automated execution functions
 */


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
    
    // DEPRECATED: 30-minute tracking updates (was for Google Finance formulas)
    // if (!EW_triggerExists(EW_TRIGGER_FUNCTIONS.AUTO_UPDATE)) {
    //   ScriptApp.newTrigger(EW_TRIGGER_FUNCTIONS.AUTO_UPDATE)
    //     .timeBased()
    //     .everyMinutes(EW_AUTO_TRACKING.TRIGGER_INTERVAL_MINUTES)
    //     .create();
    //   setupCount++;
    //   messages.push(`✅ Created: 30-minute tracking updates`);
    //   console.log(`Created trigger: ${EW_TRIGGER_FUNCTIONS.AUTO_UPDATE}`);
    // } else {
    //   skippedCount++;
    //   messages.push(`⏭️ Exists: 30-minute tracking updates`);
    //   console.log(`Skipped existing trigger: ${EW_TRIGGER_FUNCTIONS.AUTO_UPDATE}`);
    // }
    
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
    
    // Check and setup daily backfill trigger (5 PM)
    // Backfill processes ALL positions (active and expired) with incomplete data
    const backfillFunction = 'EW_backfillHistoricalTracking';

    // Remove old active tracking triggers if they exist
    triggers.forEach(trigger => {
      const funcName = trigger.getHandlerFunction();
      if (funcName === 'EW_updateActiveStrikeHits' || funcName === 'EW_updateActiveStrikeHitsWithContinuation') {
        ScriptApp.deleteTrigger(trigger);
        console.log(`Removed old active tracking trigger: ${funcName}`);
      }
    });

    if (!EW_triggerExists(backfillFunction)) {
      ScriptApp.newTrigger(backfillFunction)
        .timeBased()
        .everyDays(1)
        .atHour(17) // 5 PM
        .inTimezone('America/New_York')
        .create();
      setupCount++;
      messages.push(`✅ Created: Daily backfill (processes all incomplete positions, 5 PM ET)`);
      console.log(`Created trigger: ${backfillFunction}`);
    } else {
      skippedCount++;
      messages.push(`⏭️ Exists: Daily backfill (5 PM ET)`);
      console.log(`Skipped existing trigger: ${backfillFunction}`);
    }

    // Check and setup daily formatting trigger (8 PM)
    const formattingFunction = 'EW_applyDailyFormatting';
    if (!EW_triggerExists(formattingFunction)) {
      ScriptApp.newTrigger(formattingFunction)
        .timeBased()
        .everyDays(1)
        .atHour(20) // 8 PM
        .inTimezone('America/New_York')
        .create();
      setupCount++;
      messages.push(`✅ Created: Daily formatting (8 PM ET)`);
      console.log(`Created trigger: ${formattingFunction}`);
    } else {
      skippedCount++;
      messages.push(`⏭️ Exists: Daily formatting (8 PM ET)`);
      console.log(`Skipped existing trigger: ${formattingFunction}`);
    }
    
    // Empty row removal is now handled by EW_cleanupEmptyRows() before each data fetch
    // No separate trigger needed
    
    // Ensure success report exists
    EW_ensureSuccessReportExists();
    
    // Show results
    const summary = `Trigger Setup Summary:\n\n${messages.join('\n')}\n\n` +
                   `📊 Results: ${setupCount} created, ${skippedCount} already existed\n\n` +
                   `Total active triggers: ${triggers.length + setupCount}`;
    
    EW_safeAlert(
      'Smart Trigger Setup Complete',
      summary
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

    // DEPRECATED: 30-minute tracking trigger (was for Google Finance formulas)
    // ScriptApp.newTrigger(EW_TRIGGER_FUNCTIONS.AUTO_UPDATE)
    //   .timeBased()
    //   .everyMinutes(EW_AUTO_TRACKING.TRIGGER_INTERVAL_MINUTES)
    //   .create();

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
    
    // Create daily backfill trigger (5 PM ET)
    ScriptApp.newTrigger(EW_TRIGGER_FUNCTIONS.DAILY_BACKFILL)
      .timeBased()
      .everyDays(1)
      .atHour(17) // 5 PM
      .inTimezone('America/New_York')
      .create();
    
    // Empty row removal is now handled by EW_cleanupEmptyRows() before each data fetch
    
    EW_safeAlert(
      'Auto Tracking Setup Complete',
      'Automated schedule created:\n\n' +
      `• ${EW_AUTO_TRACKING.DAILY_DATA_HOUR}:00 AM: Daily data fetch\n` +
      `• ${EW_AUTO_TRACKING.DAILY_REPORT_HOUR}:00 AM: Daily success report update\n` +
      `• 5:00 PM ET: Daily backfill (processes all incomplete positions)\n\n` +
      'Historical data will be preserved permanently.'
    );
    
    console.log('Auto tracking triggers created successfully');
    EW_trace('TRIGGERS', 'Auto tracking setup complete - 8AM daily runAll, 9AM reports, 5PM backfill');
    
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
      'This will run EW_runAll() every day to fetch fresh strategy data.'
    );
    
    console.log('Daily data trigger created for 8 AM');
    EW_trace('TRIGGERS', `Daily data fetch trigger setup - ${EW_AUTO_TRACKING.DAILY_DATA_HOUR}AM EW_dailyDataFetch`);
    
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
    if (// handlerFunction === EW_TRIGGER_FUNCTIONS.AUTO_UPDATE || // DEPRECATED
      handlerFunction === EW_TRIGGER_FUNCTIONS.DAILY_REPORT ||
      handlerFunction === EW_TRIGGER_FUNCTIONS.DAILY_DATA ||
      handlerFunction === EW_TRIGGER_FUNCTIONS.DAILY_BACKFILL ||
      handlerFunction === 'EW_updateActiveStrikeHits' || // Remove old active tracking
      handlerFunction === 'EW_autoUpdateTracking') { // Remove old tracking updates
        ScriptApp.deleteTrigger(trigger);
        deletedCount++;
        console.log(`Deleted trigger: ${handlerFunction}`);
      }
    });
    
    if (deletedCount > 0) {
      EW_safeAlert(
        'Auto Tracking Stopped',
        `Removed ${deletedCount} automated trigger(s).\n\n` +
        'All automated functions have been disabled:\n' +
        `• Daily data fetch (${EW_AUTO_TRACKING.DAILY_DATA_HOUR} AM)\n` +
        `• Daily reports (${EW_AUTO_TRACKING.DAILY_REPORT_HOUR} AM)\n` +
        `• Daily backfill (5 PM ET)\n\n` +
        'You can restart using "Setup Auto Tracking" from the menu.'
      );
      console.log(`Deleted ${deletedCount} auto tracking triggers`);
      EW_trace('TRIGGERS', `Stopped auto tracking - removed ${deletedCount} triggers`);
    } else {
      EW_safeAlert(
        'No Auto Tracking Found',
        'No automated tracking triggers were found to remove.'
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
      EW_safeAlert('Active Triggers', 'No automated triggers are currently active.');
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
    
    EW_safeAlert(
      'Active Triggers',
      `Found ${triggers.length} active trigger(s):\n\n` + triggerInfo.join('\n')
    );
    
  } catch (error) {
    console.error('Error listing triggers:', error);
  }
}

// ===== AUTOMATED EXECUTION FUNCTIONS =====

/**
 * Automated update function called by 30-minute trigger
 * Only runs during market hours (9 AM - 5 PM ET)
 */
function EW_autoUpdateTracking() {
  try {
    const now = new Date();
    console.log('Auto tracking update started at:', now);
    
    // Check if current time is within market hours (9 AM - 5 PM ET)
    const easternTime = new Date(now.toLocaleString("en-US", {timeZone: "America/New_York"}));
    const hour = easternTime.getHours();
    const dayOfWeek = easternTime.getDay();
    
    // Skip if outside market hours (before 9 AM or after 5 PM) or on weekends
    if (hour < 9 || hour >= 17 || dayOfWeek === 0 || dayOfWeek === 6) {
      console.log(`Skipping update - outside market hours. ET: ${easternTime.toLocaleString()}, Hour: ${hour}, Day: ${dayOfWeek}`);
      EW_trace('AUTO_UPDATE', `Skipped - outside market hours (${hour}:00 ET, Day ${dayOfWeek})`);
      return;
    }
    
    EW_trace('AUTO_UPDATE', 'Starting 30-minute tracking update (market hours)');
    
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
 * This is a wrapper around EW_runAll() that suppresses UI alerts for automated execution
 * Use this for triggers to avoid interrupting users with popup dialogs
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
      EW_safeAlert(
        'Triggers Healthy',
        '✅ All expected triggers are properly configured.\n\n' +
        `Found ${validation.total} active triggers.\n\n` +
        'No repairs needed.'
      );
      return { status: 'healthy', total: validation.total };
    }
    
    // If there are missing triggers, offer to repair
    if (validation.missing && validation.missing.length > 0) {
      const response = EW_safeConfirm(
        'Missing Triggers Detected',
        `❌ Found ${validation.missing.length} missing trigger(s):\n` +
        `${validation.missing.join(', ')}\n\n` +
        'Would you like to create the missing triggers?'
      );
      
      if (response === 'YES') {
        // Setup missing triggers using the smart setup function
        const result = EW_setupTriggersIfMissing();
        
        if (result.created > 0) {
          EW_safeAlert(
            'Triggers Repaired',
            `✅ Successfully created ${result.created} missing trigger(s).\n\n` +
            'All triggers are now properly configured.'
          );
          EW_trace('TRIGGERS', `Repair complete - created ${result.created} missing triggers`);
          return { status: 'repaired', created: result.created };
        } else {
          EW_safeAlert(
            'Repair Complete',
            'All triggers were already properly configured.'
          );
          return { status: 'no_action_needed' };
        }
      } else {
        return { status: 'user_cancelled' };
      }
    }
    
    // Handle unexpected triggers
    if (validation.unexpected && validation.unexpected.length > 0) {
      EW_safeAlert(
        'Unexpected Triggers Found',
        `⚠️ Found ${validation.unexpected.length} unexpected trigger(s):\n` +
        `${validation.unexpected.join(', ')}\n\n` +
        'These may be from other scripts or manual setup.\n' +
        'Use "Stop All Auto Tracking" if you want to remove them.'
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
      timestamp: EW_formatDateTime(new Date())
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
      // EW_TRIGGER_FUNCTIONS.AUTO_UPDATE, // DEPRECATED - was for Google Finance formulas
      EW_TRIGGER_FUNCTIONS.DAILY_BACKFILL
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


    /**
     * Remove empty rows from all strategy sheets
     * Runs daily at 6 AM ET
     * DEPRECATED: Now handled by EW_cleanupEmptyRows() in main code which runs before each data fetch
     */
    // function EW_removeEmptyRowsDaily() {
    //   try {
    //     const ss = SpreadsheetApp.getActiveSpreadsheet();
    //     const sheets = ss.getSheets();
    //     let totalRemoved = 0;
    //     sheets.forEach(sheet => {
    //       // Skip non-strategy sheets (e.g., Success_Report)
    //       const name = sheet.getName();
    //       if (name === 'Success_Report' || name.startsWith('Config') || name.startsWith('Log')) return;
    //       const data = sheet.getDataRange().getValues();
    //       let rowsToDelete = [];
    //       for (let i = 1; i < data.length; i++) { // skip header row
    //         if (data[i].every(cell => cell === '' || cell === null)) {
    //           rowsToDelete.push(i + 1); // 1-based row index
    //         }
    //       }
    //       // Delete from bottom up to avoid shifting
    //       rowsToDelete.reverse().forEach(rowNum => {
    //         sheet.deleteRow(rowNum);
    //         totalRemoved++;
    //       });
    //     });
    //     EW_trace('EMPTY_ROW_REMOVAL', `Removed ${totalRemoved} empty rows from all sheets.`);
    //     console.log(`Removed ${totalRemoved} empty rows from all sheets.`);
    //   } catch (error) {
    //     EW_trace('EMPTY_ROW_REMOVAL', `Error removing empty rows: ${error.toString()}`);
    //     console.error('Error removing empty rows:', error);
    //   }
    // }
// Note: Active tracking consolidated into daily backfill.
// All tracking updates are now handled by EW_backfillHistoricalTracking which runs at 5 PM ET.

/**
 * Test function to verify all triggers are properly configured
 * Shows detailed information about each trigger
 */
function EW_testAllTriggers() {
  console.log('=== TRIGGER CONFIGURATION TEST ===');
  
  const expectedTriggers = [
    { name: EW_TRIGGER_FUNCTIONS.DAILY_DATA, desc: '8 AM Daily data fetch', time: '8:00 AM' },
    { name: EW_TRIGGER_FUNCTIONS.DAILY_REPORT, desc: '9 AM Success reports', time: '9:00 AM' },
    // { name: EW_TRIGGER_FUNCTIONS.AUTO_UPDATE, desc: '30-min updates (market hours)', time: 'Every 30 min (9-5 ET)' }, // DEPRECATED
    { name: EW_TRIGGER_FUNCTIONS.DAILY_BACKFILL, desc: '5 PM Daily backfill', time: '5:00 PM ET' }
  ];
  
  const triggers = ScriptApp.getProjectTriggers();
  const foundFunctions = triggers.map(t => t.getHandlerFunction());
  
  console.log(`\nExpected triggers: ${expectedTriggers.length}`);
  console.log(`Found triggers: ${triggers.length}\n`);
  
  // Check each expected trigger
  expectedTriggers.forEach(expected => {
    const exists = foundFunctions.includes(expected.name);
    const status = exists ? '✅ EXISTS' : '❌ MISSING';
    console.log(`${status} | ${expected.desc} | Function: ${expected.name} | Schedule: ${expected.time}`);
  });
  
  // Show any unexpected triggers
  const unexpectedTriggers = foundFunctions.filter(func => 
    !expectedTriggers.map(e => e.name).includes(func)
  );
  
  if (unexpectedTriggers.length > 0) {
    console.log('\n⚠️ Unexpected triggers found:');
    unexpectedTriggers.forEach(func => {
      console.log(`  - ${func}`);
    });
  }
  
  // Detailed trigger information
  console.log('\n=== DETAILED TRIGGER INFO ===');
  triggers.forEach((trigger, index) => {
    console.log(`\nTrigger ${index + 1}:`);
    console.log(`  Function: ${trigger.getHandlerFunction()}`);
    console.log(`  Type: ${trigger.getEventType()}`);
    console.log(`  Source: ${trigger.getTriggerSource()}`);
    
    // Try to get more details if possible
    try {
      console.log(`  ID: ${trigger.getUniqueId()}`);
    } catch (e) {
      // Some properties might not be accessible
    }
  });
  
  return {
    expected: expectedTriggers.length,
    found: triggers.length,
    missing: expectedTriggers.filter(e => !foundFunctions.includes(e.name)).map(e => e.name),
    unexpected: unexpectedTriggers
  };
}
