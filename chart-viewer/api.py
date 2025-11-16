#!/usr/bin/env python3
"""
Trading Chart Viewer - Data API Server
Serves parquet files as JSON for the chart viewer
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
from pathlib import Path
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)  # Enable CORS for local development

# Data paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_PATHS = {
    'IWM': PROJECT_ROOT / 'data' / 'iwm' / 'minute',
    'SPY': PROJECT_ROOT / 'data' / 'spy' / 'minute',
    'QQQ': PROJECT_ROOT / 'data' / 'qqq' / 'minute',
}


def get_available_files(ticker):
    """Get list of available parquet files for a ticker"""
    ticker_path = DATA_PATHS.get(ticker.upper())

    if not ticker_path or not ticker_path.exists():
        return []

    files = sorted(ticker_path.glob('*.parquet'))
    return files


def parse_filename_date(filename):
    """Extract date from filename: ticker_minute_YYYYMMDD.parquet"""
    parts = filename.stem.split('_')
    if len(parts) >= 3:
        date_str = parts[2]  # YYYYMMDD
        return date_str
    return None


def load_parquet_file(file_path):
    """Load parquet file and convert to JSON-ready format"""
    try:
        df = pd.read_parquet(file_path)

        # Ensure required columns exist
        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']

        # Handle different column name formats
        df.columns = [col.capitalize() if col.lower() in ['open', 'high', 'low', 'close', 'volume']
                      else col for col in df.columns]

        # Rename if needed
        column_mapping = {
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        }
        df = df.rename(columns=lambda x: column_mapping.get(x.lower(), x))

        # Reset index to make timestamp a column
        df = df.reset_index()

        # Convert timestamp to Unix timestamp (seconds)
        if 'Datetime' in df.columns:
            timestamp_col = 'Datetime'
        elif 'datetime' in df.columns:
            timestamp_col = 'datetime'
        elif 'index' in df.columns:
            timestamp_col = 'index'
        else:
            timestamp_col = df.columns[0]

        # Convert to timestamp
        df['time'] = pd.to_datetime(df[timestamp_col]).astype(int) // 10**9

        # Select and order columns
        result = df[['time', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
        result.columns = ['time', 'open', 'high', 'low', 'close', 'volume']

        # Convert to list of dicts
        return result.to_dict('records')

    except Exception as e:
        print(f"Error loading parquet file {file_path}: {e}")
        return None


@app.route('/api/dates/<ticker>', methods=['GET'])
def get_dates(ticker):
    """Get available dates for a ticker"""
    files = get_available_files(ticker)

    if not files:
        return jsonify({'dates': [], 'error': 'No data found for ticker'})

    dates = []
    for file in files:
        date_str = parse_filename_date(file)
        if date_str:
            dates.append(date_str)

    return jsonify({'dates': sorted(dates)})


@app.route('/api/data/<ticker>/<date>', methods=['GET'])
def get_data(ticker, date):
    """Get OHLCV data for a specific ticker and date"""
    ticker_path = DATA_PATHS.get(ticker.upper())

    if not ticker_path:
        return jsonify({'error': 'Invalid ticker'}), 400

    # Find file for the specified date
    filename = f"{ticker.lower()}_minute_{date}.parquet"
    file_path = ticker_path / filename

    if not file_path.exists():
        return jsonify({'error': f'No data found for {ticker} on {date}'}), 404

    # Load data
    data = load_parquet_file(file_path)

    if data is None:
        return jsonify({'error': 'Error loading data'}), 500

    # Apply timeframe aggregation if requested
    timeframe = request.args.get('timeframe', 1, type=int)

    if timeframe > 1:
        data = aggregate_timeframe(data, timeframe)

    return jsonify(data)


def aggregate_timeframe(data, timeframe_minutes):
    """Aggregate 1-minute data to specified timeframe"""
    if timeframe_minutes == 1:
        return data

    df = pd.DataFrame(data)

    # Convert time back to datetime for resampling
    df['datetime'] = pd.to_datetime(df['time'], unit='s')
    df = df.set_index('datetime')

    # Resample to specified timeframe
    rule = f'{timeframe_minutes}T'

    aggregated = df.resample(rule).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()

    # Convert back to timestamp
    aggregated = aggregated.reset_index()
    aggregated['time'] = (aggregated['datetime'].astype(int) // 10**9)

    # Drop the datetime column and return
    result = aggregated[['time', 'open', 'high', 'low', 'close', 'volume']]

    return result.to_dict('records')


@app.route('/api/tickers', methods=['GET'])
def get_tickers():
    """Get list of available tickers"""
    tickers = []
    for ticker in DATA_PATHS.keys():
        files = get_available_files(ticker)
        if files:
            tickers.append({
                'ticker': ticker,
                'fileCount': len(files)
            })

    return jsonify({'tickers': tickers})


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'message': 'Trading Chart Viewer API is running',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/', methods=['GET'])
def index():
    """API documentation"""
    return jsonify({
        'name': 'Trading Chart Viewer API',
        'version': '1.0.0',
        'endpoints': {
            'GET /api/health': 'Health check',
            'GET /api/tickers': 'List available tickers',
            'GET /api/dates/<ticker>': 'Get available dates for a ticker',
            'GET /api/data/<ticker>/<date>': 'Get OHLCV data for a ticker and date',
            'GET /api/data/<ticker>/<date>?timeframe=5': 'Get aggregated data (1, 5, 15, 30, 60 minutes)'
        },
        'examples': {
            'dates': '/api/dates/IWM',
            'data': '/api/data/IWM/20251114',
            'data_5min': '/api/data/IWM/20251114?timeframe=5'
        }
    })


if __name__ == '__main__':
    print("=" * 60)
    print("Trading Chart Viewer API Server")
    print("=" * 60)
    print(f"Server starting on http://localhost:5000")
    print(f"Project root: {PROJECT_ROOT}")
    print("\nAvailable tickers:")
    for ticker, path in DATA_PATHS.items():
        file_count = len(list(path.glob('*.parquet'))) if path.exists() else 0
        print(f"  - {ticker}: {file_count} files")
    print("\nAPI Endpoints:")
    print("  - http://localhost:5000/api/health")
    print("  - http://localhost:5000/api/tickers")
    print("  - http://localhost:5000/api/dates/IWM")
    print("  - http://localhost:5000/api/data/IWM/20251114")
    print("=" * 60)

    app.run(debug=True, host='0.0.0.0', port=5000)
