"""
Configuration file for Earnings Options Analytics System
"""
import os

# Paths
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(PROJECT_ROOT, '..', 'google-apps-script', 'data')
OUTPUT_PATH = os.path.join(PROJECT_ROOT, 'outputs')
CSV_REPORTS_PATH = os.path.join(OUTPUT_PATH, 'csv_reports')
CHARTS_PATH = os.path.join(OUTPUT_PATH, 'charts')
DASHBOARDS_PATH = os.path.join(OUTPUT_PATH, 'dashboards')

# Strategy names (must match CSV file names or sheet names)
STRATEGIES = [
    'Long Calls',
    'Bull Spreads',
    'Covered Calls',
    'Long Puts',
    'Bear Spreads',
    'Short Calls',
    'Strangles',
    'Straddles',
    'Short Puts'
]

# Strategy categories
BULLISH_STRATEGIES = ['Long Calls', 'Bull Spreads', 'Covered Calls']
BEARISH_STRATEGIES = ['Long Puts', 'Bear Spreads', 'Short Calls']
NEUTRAL_STRATEGIES = ['Strangles', 'Straddles', 'Short Puts']

# Column mappings
TRACKING_COLUMNS = {
    'entry': ['Run Date', 'Strategy', 'company', 'ticker', 'strike', 'expDate', 'nextEPSDate', 'releaseTime'],
    'daily_checks': ['Day0_Check', 'Day1_Check', 'Day2_Check', 'Day3_Check', 'Day4_Check', 'Day5_Check'],
    'arrays': ['Strike_Hit', 'Max_Favorable', 'Min_Unfavorable', 'OHLC_Volume'],
    'indicators': ['Hit_RSI', 'Hit_SMA20', 'Hit_SMA50', 'Hit_EMA9', 'Hit_EMA21',
                   'Hit_VWAP', 'Hit_RVOL', 'Hit_ATR', 'Hit_PriceVsSMA20', 'Hit_PriceVsVWAP'],
    'metrics': ['Risk_Reward', 'Days_To_Exp', 'Success_Score', 'avgEPSMove', 'epsImpact']
}

# Spread-specific columns
SPREAD_COLUMNS = ['longStrike', 'shortStrike', 'maxProfit', 'maxLoss', 'breakeven']

# Analysis parameters
MIN_TRADES_FOR_ANALYSIS = 30  # Minimum trades needed for statistical significance
MIN_SAMPLE_SIZE = 5  # Minimum sample size for per-day analysis
TOP_N_PLAYS = 50  # Number of top plays to profile
INDICATOR_BINS = 10  # Number of bins for indicator histograms
ML_TEST_SPLIT = 0.2  # Train/test split for ML models
ML_RANDOM_STATE = 42

# Earnings timing windows (days before earnings)
EARNINGS_WINDOWS = [
    (0, 2, '0-2 days'),
    (3, 5, '3-5 days'),
    (6, 10, '6-10 days'),
    (11, 20, '11-20 days'),
    (21, 999, '21+ days')
]

# Indicator thresholds (based on provided reports)
INDICATOR_RANGES = {
    'RSI': {
        'oversold': (0, 30),
        'neutral': (30, 70),
        'overbought': (70, 100),
        'winning_range': (38.3, 78.6)  # From indicator profiles report
    },
    'PriceVsSMA20': {
        'below': (-5, 0),
        'at': (0, 0.5),
        'above': (0.5, 3),
        'winning_range': (-0.41, 1.51)  # From indicator profiles report
    },
    'PriceVsVWAP': {
        'below': (-5, 0),
        'at': (0, 0.5),
        'above': (0.5, 5),
        'winning_range': (-0.11, 11.76)  # From indicator profiles report
    },
    'RVOL': {
        'low': (0, 1),
        'normal': (1, 2),
        'high': (2, 5),
        'very_high': (5, 100)
    }
}

# Risk/Reward buckets
RISK_REWARD_BUCKETS = [
    (0, 1.0, 'Under 1.0'),
    (1.0, 2.0, '1.0-2.0'),
    (2.0, 3.0, '2.0-3.0'),
    (3.0, 999, 'Over 3.0')
]

# Visualization settings
CHART_STYLE = 'seaborn-v0_8-darkgrid'
CHART_DPI = 300
CHART_FIGSIZE = (12, 8)
COLOR_PALETTE = 'viridis'

# Report settings
REPORT_FORMAT = 'pdf'  # 'pdf' or 'html'
REPORT_TITLE = 'Earnings Options Trading Analytics Report'
REPORT_AUTHOR = 'Earnings Options Analytics System'

# Performance thresholds
HIGH_CONFIDENCE_THRESHOLD = 70  # Success score >= 70%
MODERATE_CONFIDENCE_THRESHOLD = 50  # Success score 50-69%
LOW_CONFIDENCE_THRESHOLD = 30  # Success score 30-49%

# Profitability thresholds
MIN_PROFIT_PCT = 5  # Minimum profit % to consider "good" trade
HIGH_PROFIT_PCT = 20  # High profit threshold
EXCELLENT_PROFIT_PCT = 50  # Excellent profit threshold

# Days for holding period analysis
HOLDING_DAYS = [0, 1, 2, 3, 4, 5]  # Day0 through Day5

# Feature engineering for ML
ML_FEATURES = [
    # Indicator features
    'entry_rsi', 'entry_sma20', 'entry_sma50', 'entry_rvol',
    'entry_price_vs_sma20', 'entry_price_vs_vwap',

    # Earnings timing features
    'days_to_earnings', 'is_before_open', 'is_after_close',

    # Strategy features
    'is_bullish', 'is_bearish', 'is_neutral',

    # Market context
    'avg_eps_move', 'eps_impact',

    # Strike positioning
    'strike_otm_pct'  # Out-of-the-money percentage
]

# ML target variables
ML_TARGETS = {
    'strike_hit': 'binary',  # Did strike get hit?
    'max_profit': 'continuous',  # Maximum profit achieved
    'days_to_hit': 'continuous',  # Days until strike hit
    'holding_day_profit': 'continuous'  # Profit if held X days
}

# Export formats
EXPORT_FORMATS = ['csv', 'excel', 'json']
