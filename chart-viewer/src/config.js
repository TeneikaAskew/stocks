// Configuration for Trading Chart Viewer

const CONFIG = {
    // Data source - switch between local API and GitHub Pages
    USE_LOCAL_API: false, // Set to false for GitHub Pages (uses pre-converted JSON)

    // API endpoints
    LOCAL_API_URL: 'http://localhost:5000/api',
    GITHUB_DATA_URL: './data',  // For GitHub Pages deployment

    // Data paths (relative to project root)
    DATA_PATHS: {
        IWM: '../data/iwm/minute',
        SPY: '../data/spy/minute',
        QQQ: '../data/qqq/minute'
    },

    // Chart settings
    CHART: {
        layout: {
            background: { color: '#0f0f1e' },
            textColor: '#e0e0e0',
        },
        grid: {
            vertLines: { color: '#1a1a2e' },
            horzLines: { color: '#1a1a2e' },
        },
        crosshair: {
            mode: 0, // LightweightCharts.CrosshairMode.Normal
        },
        timeScale: {
            timeVisible: true,
            secondsVisible: false,
            borderColor: '#2a2a3e',
        },
        rightPriceScale: {
            borderColor: '#2a2a3e',
        },
    },

    // Candlestick colors
    CANDLE_COLORS: {
        upColor: '#10b981',
        downColor: '#ef4444',
        borderUpColor: '#10b981',
        borderDownColor: '#ef4444',
        wickUpColor: '#10b981',
        wickDownColor: '#ef4444',
    },

    // Volume colors
    VOLUME_COLORS: {
        upColor: 'rgba(16, 185, 129, 0.5)',
        downColor: 'rgba(239, 68, 68, 0.5)',
    },

    // Trade marker colors
    MARKER_COLORS: {
        CALL_ENTRY: '#10b981',
        PUT_ENTRY: '#ef4444',
        EXIT: '#6366f1',
        TP: '#10b981',
        SL: '#ef4444',
    },

    // Local storage keys
    STORAGE_KEYS: {
        TRADES: 'tradingChartViewer_trades',
        SETTINGS: 'tradingChartViewer_settings',
    },

    // Date format
    DATE_FORMAT: 'YYYY-MM-DD',
    DATETIME_FORMAT: 'YYYY-MM-DD HH:mm:ss',

    // Available tickers
    TICKERS: ['IWM', 'SPY', 'QQQ'],

    // Timeframes (in minutes)
    TIMEFRAMES: {
        '1': '1min',
        '5': '5min',
        '15': '15min',
        '30': '30min',
        '60': '1hour',
    },

    // GitHub API settings for trade storage
    // NOTE: The token should be set via environment or injected at build time
    // For GitHub Pages, this will be replaced during the deployment process
    GITHUB_OWNER: 'TeneikaAskew',
    GITHUB_REPO: 'stocks',
    GITHUB_BRANCH: 'main',
    GITHUB_TOKEN: '', // Will be injected by GitHub Actions during deployment
};

// Helper functions
const Utils = {
    /**
     * Format date to YYYY-MM-DD
     */
    formatDate(date) {
        if (typeof date === 'string') {
            date = new Date(date);
        }
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}${month}${day}`;
    },

    /**
     * Format datetime to readable string in Eastern Time
     */
    formatDateTime(timestamp) {
        const date = new Date(timestamp * 1000);
        // Always display in Eastern Time (America/New_York) with timezone abbreviation
        const dateStr = date.toLocaleString('en-US', {
            timeZone: 'America/New_York',
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });

        // Get timezone abbreviation (EDT or EST)
        const tzStr = date.toLocaleTimeString('en-US', {
            timeZone: 'America/New_York',
            timeZoneName: 'short'
        }).split(' ').pop();

        return `${dateStr} ${tzStr}`;
    },

    /**
     * Parse parquet filename to get date
     */
    parseFilename(filename) {
        // Format: iwm_minute_20251114.parquet
        const match = filename.match(/(\d{8})/);
        return match ? match[1] : null;
    },

    /**
     * Generate unique ID
     */
    generateId() {
        return `trade_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    },

    /**
     * Calculate P&L
     */
    calculatePnL(entry, exit, type) {
        if (type === 'CALL') {
            return exit - entry;
        } else {
            return entry - exit;
        }
    },

    /**
     * Calculate P&L percentage
     */
    calculatePnLPercent(entry, exit, type) {
        const pnl = this.calculatePnL(entry, exit, type);
        return (pnl / entry) * 100;
    },

    /**
     * Format currency
     */
    formatCurrency(value) {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD',
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }).format(value);
    },

    /**
     * Format percentage
     */
    formatPercent(value) {
        return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
    },

    /**
     * Show notification
     */
    notify(message, type = 'info') {
        // Simple notification (can be enhanced with a library)
        console.log(`[${type.toUpperCase()}] ${message}`);

        // Update status indicator
        const statusText = document.querySelector('.status-text');
        if (statusText) {
            statusText.textContent = message;
            setTimeout(() => {
                statusText.textContent = 'Ready';
            }, 3000);
        }
    },
};
