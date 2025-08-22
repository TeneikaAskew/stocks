# EarningsWhispers Google Apps Script - Code Structure

## Overview
The EarningsWhispers Options Tracking system has been refactored into modular components for better maintainability and organization. Files are prefixed with numbers to ensure proper loading order and prevent "not defined" errors.

## File Structure (Loading Order)

### 📁 `src/01_GlobalVars.js`
**Purpose**: Centralized configuration and global constants
- `EW` object with API endpoints and configuration
- Default values and thresholds
- Strategy type mappings
- Error codes and auto-tracking settings

**Key Objects**:
- `EW.STRATEGY_ENDPOINTS`: API endpoint mappings
- `EW_DEFAULTS`: Default configuration values
- `EW_STRATEGY_TYPES`: Strategy categorization
- `EW_SCORE_THRESHOLDS`: Success score ranges
- `EW_AUTO_TRACKING`: Automated monitoring settings
- `EW_TRIGGER_FUNCTIONS`: Trigger function name constants

### 📁 `src/02_HelperFunctions.js`
**Purpose**: Common utility functions used across the system
- URL and string utilities
- Logging and debugging functions
- Spreadsheet utilities
- Cookie and session management
- Data validation helpers
- Error handling utilities
- Batch processing functions

**Key Functions**:
- `EW_url()`: Build full URLs from paths
- `EW_trace()`: Unified logging system
- `EW_columnToLetter()`: Convert column numbers to letters
- `EW_norm()`: Normalize strings for comparison
- `EW_mergeCookies()`: Cookie management
- `EW_extractCsrf()`: CSRF token extraction
- `EW_retryWithBackoff()`: Retry mechanism with exponential backoff
- `EW_getTriggerInfo()`: Get detailed trigger information for debugging
- `EW_triggerExists()`: Check if a specific trigger exists
- `EW_isSpreadsheetEnvironment()`: Check if running in spreadsheet (UI available)
- `EW_safeAlert()`: Show UI alerts only when appropriate (safe for all environments)
- `EW_safeConfirm()`: Show Yes/No confirmation dialogs safely across environments

### 📁 `src/03_Triggers.js`
**Purpose**: Trigger management and automated execution functions
- Setup and management of Google Apps Script triggers
- Automated execution functions called by triggers
- Trigger validation and health checking
- Environment-safe UI handling

**Key Functions**:
- `EW_setupAutoTracking()`: Complete automation setup (8AM data + 9AM reports + 30min updates)
- `EW_setupDailyDataTrigger()`: Daily data fetch only (8AM)
- `EW_setupTriggersIfMissing()`: Smart setup - only create missing triggers
- `EW_stopAutoTracking()`: Remove all automated triggers
- `EW_autoUpdateTracking()`: 30-minute automated tracking updates
- `EW_listActiveTriggers()`: Debug and list all active triggers
- `EW_validateTriggers()`: Validate expected triggers are in place
- `EW_verifyAndRepairTriggers()`: Check health and repair missing triggers
- `EW_testEnvironmentDetection()`: Test function for environment detection
- `EW_testEnvironmentDetection()`: Test function for environment detection

**Automation Schedule**:
- **8:00 AM Daily**: `EW_runAll()` - Fetch fresh strategy data
- **9:00 AM Daily**: `EW_generateSuccessReport()` - Update success analytics
- **Every 30 minutes**: `EW_autoUpdateTracking()` - Refresh tracking formulas

### 📁 `src/04_Code.js`
**Purpose**: Main application logic and business functions
- Menu functions (`onOpen`)
- Data fetching and processing
- Strategy execution
- Google Finance formula generation
- Success tracking and reporting

**Key Functions**:
- `EW_runAll()`: Execute all strategy data fetches
- `EW_setGFArrayFormulas()`: Set up Google Finance tracking formulas
- `EW_generateSuccessReport()`: Create comprehensive success analysis
- `EW_updateTrackingData()`: Manual tracking data updates

### 📁 `src/05_data-sync.js`
**Purpose**: Data synchronization utilities (existing)

### 📁 `src/06_trading-alerts.js`
**Purpose**: Trading alert functionality (existing)

## Dependencies and Loading Order

Google Apps Script loads files alphabetically by filename, so the numbered prefixes ensure proper dependency order:

1. **01_GlobalVars.js** - Global configuration and constants (must load first)
2. **02_HelperFunctions.js** - Utility functions (depends on #1)
3. **03_Triggers.js** - Trigger management and automation (depends on #1 & #2)
4. **04_Code.js** - Main application logic (depends on #1, #2 & #3)
5. **05_data-sync.js, 06_trading-alerts.js** - Additional modules (depend on all above)

This prevents "function not defined" errors that can occur when functions are called before they're loaded.

## Benefits of Refactoring

### ✅ **Improved Maintainability**
- Clear separation of concerns
- Easier to locate and modify specific functionality
- Reduced code duplication

### ✅ **Enhanced Automation**
- Centralized trigger management in dedicated module
- Flexible automation options (full automation vs. daily data only)
- Built-in trigger validation and health checking
- Clear scheduling with configurable times

### ✅ **Better Organization**
- Configuration centralized in one place
- Helper functions reusable across modules
- Main logic focused on business operations

### ✅ **Enhanced Debugging**
- Easier to trace issues to specific modules
- Consistent logging through centralized functions
- Better error handling with standardized utilities

### ✅ **Future Extensibility**
- Easy to add new helper functions
- Simple to modify configuration without touching core logic
- Modular structure supports additional feature modules

## Usage Notes

### **Global Variable Access**
```javascript
// Access strategy endpoints
const endpoints = EW.STRATEGY_ENDPOINTS;

// Use default values
const timeout = EW_DEFAULTS.SHEET_TIMEOUT;

// Check strategy type
const type = EW_STRATEGY_TYPES.BULLISH;
```

### **Trigger Management**
```javascript
// Smart setup - only create missing triggers (safe for repeated use)
EW_setupTriggersIfMissing();

// Setup full automation (removes existing, creates new)
EW_setupAutoTracking();

// Setup only daily data fetch at 8 AM
EW_setupDailyDataTrigger();

// Health check and repair
EW_verifyAndRepairTriggers();

// Test environment detection (works in both spreadsheet and script editor)
EW_testEnvironmentDetection();

// Safe UI alerts (automatically detects environment)
EW_safeAlert('Title', 'Message'); // Shows UI in spreadsheet, logs in script editor

// Check environment
const isSpreadsheet = EW_isSpreadsheetEnvironment();

// Stop all automation
EW_stopAutoTracking();

// Check if specific trigger exists
const exists = EW_triggerExists('EW_runAll');

// Get trigger details
const info = EW_getTriggerInfo('EW_autoUpdateTracking');

// List and validate triggers
EW_listActiveTriggers();
EW_validateTriggers();

// Access trigger configuration
const dataHour = EW_AUTO_TRACKING.DAILY_DATA_HOUR; // 8
const reportHour = EW_AUTO_TRACKING.DAILY_REPORT_HOUR; // 9
const updateInterval = EW_AUTO_TRACKING.TRIGGER_INTERVAL_MINUTES; // 30
```

### **Helper Function Usage**
```javascript
// Build URLs
const url = EW_url('/api/getlongcalls');

// Log with different scopes
EW_trace('API', 'Fetching data...');
EW_trace('ERROR', 'Something failed', true); // Also log to sheet

// Convert column numbers
const colLetter = EW_columnToLetter(5); // Returns 'E'

// Normalize strings
const normalized = EW_norm('Strike Price'); // Returns 'strikeprice'
```

### **Configuration Updates**
To modify configuration:
1. Edit `GlobalVars.js` for constants and endpoints
2. Use `HelperFunctions.js` for new utility functions
3. Keep business logic in `Code.js`

## Migration Notes

All existing functionality has been preserved. The refactoring:
- ✅ Files renamed with numeric prefixes for proper loading order
- ✅ Moves trigger functions to `03_Triggers.js`
- ✅ Adds environment detection for UI-safe operation
- ✅ Adds daily 8 AM data fetch trigger (`EW_runAll`)
- ✅ Enhances menu with trigger management submenu
- ✅ Moves helper functions to `02_HelperFunctions.js`
- ✅ Moves global variables to `01_GlobalVars.js`
- ✅ Maintains all existing API compatibility
- ✅ Preserves all Google Finance formulas and tracking logic
- ✅ Keeps existing success monitoring system intact
- ✅ Adds trigger validation and health checking

**File Loading Order**: 01 → 02 → 03 → 04 → 05 → 06

**New Automation Schedule:**
- **8:00 AM**: Daily data fetch (all strategies)
- **9:00 AM**: Daily success report generation  
- **Every 30 minutes**: Tracking data refresh

No changes are required to existing Google Sheets or manual processes.
