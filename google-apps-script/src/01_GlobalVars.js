/**
 * Global Variables and Configuration
 * Centralized configuration for EarningsWhispers Options Tracking
 */

// ======= MAIN CONFIGURATION OBJECT =======
const EW = {
  STRATEGY_ENDPOINTS: {
    'Long Calls':   '/api/getlongcalls', //Y
    'Long Puts':    '/api/getlongput', //E
    'Short Puts':   '/api/getshortput', //E
    'Bull Spreads': '/api/getbullcallspread', //Y
    'Strangles':    '/api/getstrangle',  //E
    'Covered Calls':'/api/getcoveredcall', //Y
    'Straddles':    '/api/getstraddle',   //E
    'Short Calls':  '/api/getshortcalls', //E
    'Bear Spreads': '/api/getbearputspread' //Y
  },

  BASE: 'https://www.earningswhispers.com',
  MATRIX_REFERRER: 'https://www.earningswhispers.com/optiontrades',
  PROPS: PropertiesService.getScriptProperties(),

  get p() {
    return {
      user: EW.PROPS.getProperty('EW_USER') || '',
      pass: EW.PROPS.getProperty('EW_PASS') || '',
      loginUrl: 'https://www.earningswhispers.com/login'
    };
  }
};

function EW_runSingle(tabName) {
  tabName = 'Long Puts'
  EW_trace('MAIN', `EW_runSingle(${tabName})`);
  const path = EW.STRATEGY_ENDPOINTS[tabName];
  if (!path) {
    EW_trace('MAIN', `Unknown tabName: ${tabName}`, true);
    return;
  }
  let cookies = {};
  if (EW.p.user && EW.p.pass) {
    try { cookies = EW_login(); } catch (e) {}
  }
  const ss = SpreadsheetApp.getActive();
  EW_runOneInternal(ss, tabName, path, cookies);
  EW_trace('MAIN', `EW_runSingle(${tabName}) done`, true);
}
// ======= GLOBAL CONSTANTS =======

// Default values for tracking
const EW_DEFAULTS = {
  SHEET_TIMEOUT: 30000,        // 30 seconds timeout for sheet operations
  MAX_RETRIES: 3,              // Maximum retry attempts for API calls
  BATCH_SIZE: 100,             // Default batch size for processing
  LOG_RETENTION_DAYS: 30,      // Days to keep logs
  AUTO_UPDATE_INTERVAL: 30     // Minutes between auto updates
};

// Column mapping constants
const EW_COLUMN_TYPES = {
  TEXT: 'text',
  NUMBER: 'number', 
  DATE: 'date',
  FORMULA: 'formula',
  BOOLEAN: 'boolean'
};

// Strategy type mappings
const EW_STRATEGY_TYPES = {
  BULLISH: ['Long Calls', 'Bull Spreads', 'Covered Calls'],
  BEARISH: ['Long Puts', 'Bear Spreads', 'Short Calls'], 
  NEUTRAL: ['Strangles', 'Straddles'],
  INCOME: ['Short Puts', 'Covered Calls']
};

// Success score thresholds
const EW_SCORE_THRESHOLDS = {
  EXCELLENT: 80,
  GOOD: 60,
  FAIR: 40,
  POOR: 20
};

// Error codes and messages
const EW_ERRORS = {
  API_TIMEOUT: 'API_TIMEOUT',
  INVALID_RESPONSE: 'INVALID_RESPONSE',
  SHEET_ACCESS: 'SHEET_ACCESS',
  LOGIN_FAILED: 'LOGIN_FAILED',
  QUOTA_EXCEEDED: 'QUOTA_EXCEEDED'
};

// Auto-tracking settings
const EW_AUTO_TRACKING = {
  TRIGGER_INTERVAL_MINUTES: 30,
  DAILY_DATA_HOUR: 8,           // 8 AM daily data fetch
  DAILY_REPORT_HOUR: 9,         // 9 AM daily reports
  MAX_HISTORICAL_DAYS: 365,
  CLEANUP_INTERVAL_DAYS: 7
};

// Trigger function names (for validation and management)
const EW_TRIGGER_FUNCTIONS = {
  AUTO_UPDATE: 'EW_autoUpdateTracking',
  DAILY_DATA: 'EW_dailyDataFetch',  // Wrapper for EW_runAll that suppresses UI alerts
  DAILY_REPORT: 'EW_generateSuccessReport',
  ACTIVE_TRACKING: 'EW_updateActiveStrikeHits', // 5 PM active position tracking
  // REMOVE_EMPTY_ROWS: 'EW_removeEmptyRowsDaily'  // DEPRECATED - now handled by EW_cleanupEmptyRows() before each data fetch
};
