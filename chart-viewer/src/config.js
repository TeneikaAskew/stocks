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

    // Theme colors
    THEMES: {
        light: {
            chart: {
                layout: {
                    background: { color: '#ffffff' },
                    textColor: '#191919',
                },
                grid: {
                    vertLines: { color: '#e6e6e6' },
                    horzLines: { color: '#e6e6e6' },
                },
                timeScale: {
                    borderColor: '#d1d4dc',
                },
                rightPriceScale: {
                    borderColor: '#d1d4dc',
                },
            },
            candles: {
                upColor: '#089981',
                downColor: '#f23645',
                borderUpColor: '#089981',
                borderDownColor: '#f23645',
                wickUpColor: '#089981',
                wickDownColor: '#f23645',
            },
            volume: {
                upColor: 'rgba(8, 153, 129, 0.5)',
                downColor: 'rgba(242, 54, 69, 0.5)',
            },
            markers: {
                CALL_ENTRY: '#089981',
                PUT_ENTRY: '#f23645',
                EXIT: '#2962ff',
                TP: '#089981',
                SL: '#f23645',
            },
        },
        dark: {
            chart: {
                layout: {
                    background: { color: '#131722' },
                    textColor: '#d1d4dc',
                },
                grid: {
                    vertLines: { color: '#1e222d' },
                    horzLines: { color: '#1e222d' },
                },
                timeScale: {
                    borderColor: '#2b2b43',
                },
                rightPriceScale: {
                    borderColor: '#2b2b43',
                },
            },
            candles: {
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderUpColor: '#26a69a',
                borderDownColor: '#ef5350',
                wickUpColor: '#26a69a',
                wickDownColor: '#ef5350',
            },
            volume: {
                upColor: 'rgba(38, 166, 154, 0.5)',
                downColor: 'rgba(239, 83, 80, 0.5)',
            },
            markers: {
                CALL_ENTRY: '#26a69a',
                PUT_ENTRY: '#ef5350',
                EXIT: '#2962ff',
                TP: '#26a69a',
                SL: '#ef5350',
            },
        },
    },

    // Default theme (will be overridden by user preference)
    currentTheme: 'light',

    // Chart settings (use light theme by default, will be updated dynamically)
    CHART: {
        layout: {
            background: { color: '#ffffff' },
            textColor: '#191919',
        },
        grid: {
            vertLines: { color: '#e6e6e6' },
            horzLines: { color: '#e6e6e6' },
        },
        crosshair: {
            mode: 0,
        },
        timeScale: {
            timeVisible: true,
            secondsVisible: false,
            borderColor: '#d1d4dc',
        },
        rightPriceScale: {
            borderColor: '#d1d4dc',
        },
    },

    // Candlestick colors (light theme default)
    CANDLE_COLORS: {
        upColor: '#089981',
        downColor: '#f23645',
        borderUpColor: '#089981',
        borderDownColor: '#f23645',
        wickUpColor: '#089981',
        wickDownColor: '#f23645',
    },

    // Volume colors (light theme default)
    VOLUME_COLORS: {
        upColor: 'rgba(8, 153, 129, 0.5)',
        downColor: 'rgba(242, 54, 69, 0.5)',
    },

    // Trade marker colors (light theme default)
    MARKER_COLORS: {
        CALL_ENTRY: '#089981',
        PUT_ENTRY: '#f23645',
        EXIT: '#2962ff',
        TP: '#089981',
        SL: '#f23645',
    },

    // Reference line colors for previous period OHLC
    REFERENCE_LINE_COLORS: {
        HIGH: '#FFD700',      // Yellow-gold for all lines
        LOW: '#FFD700',       // Yellow-gold for all lines
        OPEN: '#FFD700',      // Yellow-gold for all lines
        CLOSE: '#FFD700',     // Yellow-gold for all lines
    },

    // Local storage keys
    STORAGE_KEYS: {
        TRADES: 'tradingSimulator_trades',
        SETTINGS: 'tradingSimulator_settings',
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
        // Timestamps in our data are stored as "naive" ET times (not true UTC)
        // They represent ET hours/minutes but are stored as UTC epoch seconds
        const date = new Date(timestamp * 1000);

        // Read the UTC components directly - these represent the actual ET time
        const year = date.getUTCFullYear();
        const month = String(date.getUTCMonth() + 1).padStart(2, '0');
        const day = String(date.getUTCDate()).padStart(2, '0');
        const hours = String(date.getUTCHours()).padStart(2, '0');
        const minutes = String(date.getUTCMinutes()).padStart(2, '0');
        const seconds = String(date.getUTCSeconds()).padStart(2, '0');

        // Determine if it's EDT or EST based on date (approximate)
        // EDT: March - November, EST: December - February
        const isEDT = date.getUTCMonth() >= 2 && date.getUTCMonth() <= 10;
        const tzStr = isEDT ? 'EDT' : 'EST';

        return `${month}/${day}/${year}, ${hours}:${minutes}:${seconds} ${tzStr}`;
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
