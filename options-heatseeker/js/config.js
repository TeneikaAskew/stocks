// ===== Configuration =====

const CONFIG = {
    // API Configuration
    // Set this to your Cloudflare Worker URL after deployment
    // Leave empty to use static data files (fallback mode)
    API_ENDPOINT: '',  // e.g., 'https://options-heatseeker-api.your-subdomain.workers.dev'

    // Data paths (fallback for static files)
    DATA_BASE_PATH: '../data',
    TICKERS: ['iwm', 'qqq', 'spy'],

    // Heatmap visualization
    HEATMAP: {
        HEIGHT: 600,
        BAR_HEIGHT: 24,
        MARGIN: { top: 20, right: 120, bottom: 30, left: 80 },

        // Color schemes
        COLORS: {
            POSITIVE_LIGHT: '#90EE90',  // Light green
            POSITIVE_DARK: '#FFD700',   // Gold
            NEGATIVE_LIGHT: '#87CEEB',  // Light blue
            NEGATIVE_DARK: '#9370DB',   // Purple
            CURRENT_PRICE: '#ff4444',
            KING_NODE: '#FFD700',
            GATEKEEPER: '#87CEEB',
            MIDPOINT: '#9370DB'
        },

        // Display options
        MAX_STRIKES_VISIBLE: 50,
        STRIKE_RANGE_PERCENT: 0.15  // +/- 15% from current price
    },

    // Chart
    CHART: {
        HEIGHT: 400,
        MARGIN: { top: 20, right: 60, bottom: 30, left: 60 }
    },

    // Greeks calculations
    GREEKS: {
        // GEX multiplier (gamma * OI * 100 * spot^2 * 0.01)
        GEX_MULTIPLIER: 0.01,
        // VEX multiplier (vanna * OI * 100 * spot * 0.01)
        VEX_MULTIPLIER: 0.01,
        // Spot price multiplier for notional
        SPOT_MULTIPLIER: 100
    },

    // Node detection
    NODES: {
        // Minimum exposure threshold for node detection (in millions)
        MIN_THRESHOLD: 5000000,
        // Number of top nodes to track
        TOP_NODES_COUNT: 5,
        // King node is the largest absolute value
        // Gatekeepers are next largest
        // Midpoints are between competing nodes
        MIDPOINT_THRESHOLD: 0.3  // Ratio for midpoint detection
    },

    // Filters
    FILTERS: {
        DTE_RANGES: {
            'all': [0, Infinity],
            '0-7': [0, 7],
            '7-30': [7, 30],
            '30-60': [30, 60],
            '60+': [60, Infinity]
        },
        DEFAULT_DTE: 'all',
        DEFAULT_OPTION_TYPE: 'both',  // 'calls', 'puts', 'both'
        DEFAULT_VALUE_FORMAT: 'dollar'  // 'dollar', 'percent'
    },

    // Performance
    CACHE: {
        ENABLED: true,
        MAX_SIZE: 50,  // Max cached datasets
        TTL: 3600000   // 1 hour in milliseconds
    },

    // Export
    EXPORT: {
        IMAGE_WIDTH: 1920,
        IMAGE_HEIGHT: 1080,
        IMAGE_FORMAT: 'png'
    },

    // UI
    UI: {
        TOOLTIP_OFFSET: { x: 10, y: 10 },
        ANIMATION_DURATION: 300,
        DEBOUNCE_DELAY: 250
    }
};

// Freeze config to prevent modifications
Object.freeze(CONFIG);
