// Configuration for the Trading Success Report Dashboard

const CONFIG = {
    // Replace with your Google Apps Script Web App URL
    WEB_APP_URL: 'https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec',
    
    // Refresh interval in milliseconds (0 = no auto-refresh)
    AUTO_REFRESH_INTERVAL: 0, // 300000 for 5 minutes
    
    // Chart colors
    CHART_COLORS: {
        primary: '#3b82f6',
        success: '#10b981',
        danger: '#ef4444',
        warning: '#f59e0b',
        info: '#6366f1'
    },
    
    // Development mode (uses local sample data)
    DEV_MODE: true // Set to false in production
};