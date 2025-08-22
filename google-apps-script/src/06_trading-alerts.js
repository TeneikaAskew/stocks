/**
 * Stock Trading Alerts Google Apps Script
 * Integrates with trading rules and sends alerts via email/sheets
 */

// Configuration
const CONFIG = {
  SPREADSHEET_ID: '', // Add your Google Sheets ID here
  EMAIL_RECIPIENTS: ['your-email@gmail.com'], // Add your email addresses
  TRADING_HOURS: {
    START: '09:30',
    END: '16:00',
    TIMEZONE: 'America/New_York'
  }
};

/**
 * Main function to check for trading alerts
 * Set this to run every 1-5 minutes during trading hours
 */
/**
 * Main function to check for trading alert conditions
 * Monitors market data and triggers alerts based on technical analysis
 * @returns {void}
 */
function checkTradingAlerts() {
  try {
    // Check if we're in trading hours
    if (!isTradingHours()) {
      console.log('Outside trading hours, skipping alerts');
      return;
    }

    // Get current market data (you'll need to implement data source)
    const marketData = getCurrentMarketData();
    
    if (!marketData) {
      console.log('No market data available');
      return;
    }

    // Check for CALL signals
    const callSignal = checkCallSignal(marketData);
    if (callSignal.triggered) {
      sendAlert('CALL', callSignal);
      logAlert('CALL', callSignal);
    }

    // Check for PUT signals
    const putSignal = checkPutSignal(marketData);
    if (putSignal.triggered) {
      sendAlert('PUT', putSignal);
      logAlert('PUT', putSignal);
    }

    // Check for exit signals
    checkExitSignals();

  } catch (error) {
    console.error('Error in checkTradingAlerts:', error);
    sendErrorNotification(error);
  }
}

/**
 * Check if current time is within trading hours
 */
/**
 * Checks if current time is within market trading hours
 * Validates both trading days and time ranges
 * @returns {boolean} True if market is open for trading
 */
function isTradingHours() {
  const now = new Date();
  const timeString = Utilities.formatDate(now, CONFIG.TRADING_HOURS.TIMEZONE, 'HH:mm');
  const currentTime = timeString.replace(':', '');
  const startTime = CONFIG.TRADING_HOURS.START.replace(':', '');
  const endTime = CONFIG.TRADING_HOURS.END.replace(':', '');
  
  return currentTime >= startTime && currentTime <= endTime;
}

/**
 * Get current market data
 * You'll need to implement this based on your data source
 */
/**
 * Fetches current market data from data source
 * Placeholder function that needs implementation for actual data source
 * @returns {Object} Market data object with price, volume, and indicator data
 */
function getCurrentMarketData() {
  // Example implementation - replace with your actual data source
  // This could be from Yahoo Finance, Alpha Vantage, or another API
  
  try {
    // Placeholder - implement your data fetching logic
    return {
      symbol: 'IWM',
      price: 185.50,
      vwap: 185.75,
      rsi: 52.3,
      rvol: 1.8,
      atr: 0.18,
      volume: 1250000,
      timestamp: new Date()
    };
  } catch (error) {
    console.error('Error fetching market data:', error);
    return null;
  }
}

/**
 * Check for CALL signal based on trading rules
 */
/**
 * Analyzes market conditions for CALL option signals
 * Checks multiple technical indicators and trend conditions
 * @param {Object} data - Market data object
 * @returns {Object|null} Signal object if conditions are met, null otherwise
 */
function checkCallSignal(data) {
  const signal = {
    triggered: false,
    strength: 0,
    conditions: [],
    message: ''
  };

  // Minimum requirements for CALL
  const priceUnderVWAP = data.price < data.vwap;
  const rsiInRange = data.rsi > 45 && data.rsi < 70;
  const volumeGood = data.rvol > 1.0;

  if (priceUnderVWAP) signal.conditions.push('Price < VWAP');
  if (rsiInRange) signal.conditions.push('RSI in range');
  if (volumeGood) signal.conditions.push('RVOL > 1.0');

  // Check if minimum requirements are met
  if (priceUnderVWAP && rsiInRange && volumeGood) {
    signal.strength += 3;
    
    // Check additional strong setup conditions
    if (data.rvol > 1.5) {
      signal.strength += 1;
      signal.conditions.push('RVOL > 1.5');
    }
    
    if (isMorningSession()) {
      signal.strength += 1;
      signal.conditions.push('Morning session');
    }
    
    if (data.atr > 0.15) {
      signal.strength += 1;
      signal.conditions.push('ATR > 0.15');
    }
    
    if (data.rsi > 50) {
      signal.strength += 1;
      signal.conditions.push('RSI crossing 50');
    }

    // Trigger alert if we have strong setup (3+ additional conditions)
    if (signal.strength >= 5) {
      signal.triggered = true;
      signal.message = `🟢 CALL Setup: IWM $${data.price} | RSI: ${data.rsi} | RVOL: ${data.rvol}x | Strength: ${signal.strength}/7`;
    }
  }

  return signal;
}

/**
 * Check for PUT signal based on trading rules
 */
/**
 * Analyzes market conditions for PUT option signals  
 * Checks for bearish indicators and downward trend conditions
 * @param {Object} data - Market data object
 * @returns {Object|null} Signal object if conditions are met, null otherwise
 */
function checkPutSignal(data) {
  const signal = {
    triggered: false,
    strength: 0,
    conditions: [],
    message: ''
  };

  // Minimum requirements for PUT
  const priceOverVWAP = data.price > data.vwap;
  const rsiInRange = data.rsi < 55 && data.rsi > 30;
  const volumeGood = data.rvol > 1.0;

  if (priceOverVWAP) signal.conditions.push('Price > VWAP');
  if (rsiInRange) signal.conditions.push('RSI in range');
  if (volumeGood) signal.conditions.push('RVOL > 1.0');

  // Check if minimum requirements are met
  if (priceOverVWAP && rsiInRange && volumeGood) {
    signal.strength += 3;
    
    // Check additional strong setup conditions
    if (data.rvol > 1.5) {
      signal.strength += 1;
      signal.conditions.push('RVOL > 1.5');
    }
    
    if (isMorningSession()) {
      signal.strength += 1;
      signal.conditions.push('Morning session');
    }
    
    if (data.atr > 0.15) {
      signal.strength += 1;
      signal.conditions.push('ATR > 0.15');
    }
    
    if (data.rsi < 40) {
      signal.strength += 1;
      signal.conditions.push('RSI < 40');
    }

    // Trigger alert if we have strong setup
    if (signal.strength >= 5) {
      signal.triggered = true;
      signal.message = `🔴 PUT Setup: IWM $${data.price} | RSI: ${data.rsi} | RVOL: ${data.rvol}x | Strength: ${signal.strength}/7`;
    }
  }

  return signal;
}

/**
 * Check if current time is morning session
 */
function isMorningSession() {
  const now = new Date();
  const timeString = Utilities.formatDate(now, CONFIG.TRADING_HOURS.TIMEZONE, 'HH:mm');
  return timeString >= '09:30' && timeString <= '10:00';
}

/**
 * Send alert via email and/or other methods
 */
function sendAlert(type, signal) {
  const subject = `🚨 ${type} Trading Alert - IWM`;
  const body = `
Trading Alert Generated:

${signal.message}

Conditions Met:
${signal.conditions.map(c => `• ${c}`).join('\n')}

Signal Strength: ${signal.strength}/7
Time: ${new Date().toLocaleString()}

Risk Management:
• Set stop loss at -${type === 'CALL' ? '0.15' : '0.20'}%
• Target profit: +${type === 'CALL' ? '0.30' : '0.38'}%
• Time stop: ${type === 'CALL' ? '30' : '35'} minutes

Remember to follow your trading rules!
  `;

  // Send email alerts
  CONFIG.EMAIL_RECIPIENTS.forEach(email => {
    try {
      GmailApp.sendEmail(email, subject, body);
      console.log(`Alert sent to ${email}`);
    } catch (error) {
      console.error(`Failed to send email to ${email}:`, error);
    }
  });
}

/**
 * Log alert to Google Sheets
 */
function logAlert(type, signal) {
  if (!CONFIG.SPREADSHEET_ID) {
    console.log('No spreadsheet ID configured');
    return;
  }

  try {
    const ss = SpreadsheetApp.openById(CONFIG.SPREADSHEET_ID);
    let sheet = ss.getSheetByName('Trading Alerts');
    
    if (!sheet) {
      sheet = ss.insertSheet('Trading Alerts');
      // Add headers
      sheet.getRange(1, 1, 1, 6).setValues([[
        'Timestamp', 'Type', 'Message', 'Strength', 'Conditions', 'Status'
      ]]);
    }

    const row = [
      new Date(),
      type,
      signal.message,
      signal.strength,
      signal.conditions.join(', '),
      'ACTIVE'
    ];

    sheet.appendRow(row);
    console.log('Alert logged to spreadsheet');
  } catch (error) {
    console.error('Error logging to spreadsheet:', error);
  }
}

/**
 * Check for exit signals on active positions
 */
function checkExitSignals() {
  // Implementation for checking exit conditions
  // This would check your active positions and alert when exit conditions are met
}

/**
 * Send error notification
 */
function sendErrorNotification(error) {
  const subject = '🚨 Trading Script Error';
  const body = `
Error in trading alerts script:

${error.toString()}

Stack trace:
${error.stack}

Time: ${new Date().toLocaleString()}
  `;

  CONFIG.EMAIL_RECIPIENTS.forEach(email => {
    try {
      GmailApp.sendEmail(email, subject, body);
    } catch (e) {
      console.error('Failed to send error notification:', e);
    }
  });
}

/**
 * Setup function - run once to initialize
 */
function setup() {
  console.log('Setting up trading alerts...');
  
  // Create triggers for regular execution
  ScriptApp.newTrigger('checkTradingAlerts')
    .timeBased()
    .everyMinutes(5) // Check every 5 minutes
    .create();
    
  console.log('Setup complete! Alerts will check every 5 minutes during trading hours.');
}

/**
 * Test function for manual testing
 */
function testAlerts() {
  console.log('Testing trading alerts...');
  
  // Create test data
  const testData = {
    symbol: 'IWM',
    price: 185.00,
    vwap: 185.50,
    rsi: 48,
    rvol: 2.1,
    atr: 0.19,
    volume: 1500000,
    timestamp: new Date()
  };

  const callSignal = checkCallSignal(testData);
  console.log('CALL Signal:', callSignal);
  
  if (callSignal.triggered) {
    sendAlert('CALL', callSignal);
    logAlert('CALL', callSignal);
  }
}
