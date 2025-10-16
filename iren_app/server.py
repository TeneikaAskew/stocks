"""
IREN Market Insights Backend Server
Provides real-time data from Yahoo Finance and AI-powered analysis from Gemini
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import os
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend access

# Configure Gemini AI
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    print("WARNING: GEMINI_API_KEY not found in environment variables")
    model = None

# Yahoo Finance API endpoints
YAHOO_BASE_URL = "https://query1.finance.yahoo.com/v8/finance"
YAHOO_QUOTE_URL = f"{YAHOO_BASE_URL}/chart"
YAHOO_QUOTESUMMARY_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary"


def fetch_yahoo_quote(symbol, interval='1d', range='3mo'):
    """Fetch real-time quote data from Yahoo Finance"""
    try:
        url = f"{YAHOO_QUOTE_URL}/{symbol}"
        params = {
            'interval': interval,
            'range': range,
            'includePrePost': 'true'
        }

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching quote for {symbol}: {e}")
        return None


def fetch_yahoo_summary(symbol):
    """Fetch detailed summary data from Yahoo Finance"""
    try:
        url = f"{YAHOO_QUOTESUMMARY_URL}/{symbol}"
        params = {
            'modules': 'price,summaryDetail,defaultKeyStatistics,financialData'
        }

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching summary for {symbol}: {e}")
        return None


def calculate_metrics(chart_data, summary_data):
    """Calculate key metrics from Yahoo Finance data"""
    try:
        result = chart_data['chart']['result'][0]
        meta = result['meta']
        timestamps = result['timestamp']
        quote = result['indicators']['quote'][0]

        # Current price data
        current_price = meta.get('regularMarketPrice', 0)
        prev_close = meta.get('previousClose', current_price)
        daily_change = ((current_price - prev_close) / prev_close * 100) if prev_close else 0

        # Historical prices
        close_prices = [p for p in quote['close'] if p is not None]
        volumes = [v for v in quote['volume'] if v is not None]

        # Calculate period changes
        change_30d = 0
        change_90d = 0

        if len(close_prices) >= 30:
            price_30d_ago = close_prices[-30]
            change_30d = ((current_price - price_30d_ago) / price_30d_ago * 100) if price_30d_ago else 0

        if len(close_prices) >= 60:
            price_90d_ago = close_prices[0]
            change_90d = ((current_price - price_90d_ago) / price_90d_ago * 100) if price_90d_ago else 0

        # Volume analysis
        avg_volume = sum(volumes[-30:]) / len(volumes[-30:]) if len(volumes) >= 30 else sum(volumes) / len(volumes)
        current_volume = volumes[-1] if volumes else 0
        volume_ratio = current_volume / avg_volume if avg_volume else 1

        # Price ranges
        high_52w = max(quote['high']) if quote.get('high') else current_price
        low_52w = min([p for p in quote['low'] if p is not None]) if quote.get('low') else current_price

        # Summary data
        summary_result = summary_data.get('quoteSummary', {}).get('result', [{}])[0] if summary_data else {}
        summary_detail = summary_result.get('summaryDetail', {})
        key_stats = summary_result.get('defaultKeyStatistics', {})
        price_info = summary_result.get('price', {})

        return {
            'company': price_info.get('longName', 'IREN Limited'),
            'ticker': meta.get('symbol', 'IREN'),
            'sector': price_info.get('sector', 'Financial Services'),
            'industry': price_info.get('industry', 'Capital Markets'),
            'current_price': round(current_price, 2),
            'daily_change': round(daily_change, 2),
            'change_30d': round(change_30d, 2),
            'change_90d': round(change_90d, 2),
            'market_cap': price_info.get('marketCap', {}).get('raw', 0),
            'volume': int(current_volume),
            'avg_volume': int(avg_volume),
            'volume_ratio': round(volume_ratio, 2),
            'high_52w': round(high_52w, 2),
            'low_52w': round(low_52w, 2),
            'pe_ratio': summary_detail.get('trailingPE', {}).get('raw', 'N/A'),
            'beta': key_stats.get('beta', {}).get('raw', 'N/A'),
            'updated': datetime.now().isoformat(),
            'historical_data': [
                {
                    'date': datetime.fromtimestamp(timestamps[i]).strftime('%Y-%m-%d'),
                    'price': round(close_prices[i], 2),
                    'volume': int(volumes[i]) if i < len(volumes) else 0
                }
                for i in range(len(close_prices))
            ]
        }
    except Exception as e:
        print(f"Error calculating metrics: {e}")
        return None


def generate_ai_insights(market_data):
    """Generate AI-powered insights using Gemini"""
    if not model:
        return {
            'momentum_insight': 'AI analysis unavailable - Gemini API key not configured',
            'volume_insight': 'AI analysis unavailable - Gemini API key not configured',
            'volatility_insight': 'AI analysis unavailable - Gemini API key not configured'
        }

    try:
        prompt = f"""
Analyze the following market data for IREN (Iris Energy Limited) and provide three concise insights:

Stock: {market_data['company']} ({market_data['ticker']})
Current Price: ${market_data['current_price']}
Daily Change: {market_data['daily_change']}%
30-Day Change: {market_data['change_30d']}%
90-Day Change: {market_data['change_90d']}%
Market Cap: ${market_data['market_cap'] / 1e9:.2f}B
Volume: {market_data['volume']:,} (Ratio: {market_data['volume_ratio']}x average)
Beta: {market_data['beta']}
P/E Ratio: {market_data['pe_ratio']}
52-Week Range: ${market_data['low_52w']} - ${market_data['high_52w']}

Provide exactly three insights in JSON format:
1. momentum_insight: Analyze the price momentum and trend strength (2-3 sentences)
2. volume_insight: Analyze trading volume and investor activity (2-3 sentences)
3. volatility_insight: Analyze risk profile and volatility (2-3 sentences)

Return ONLY a JSON object with these three keys. Be specific with numbers and actionable.
"""

        response = model.generate_content(prompt)

        # Parse the response
        text = response.text.strip()
        # Remove markdown code blocks if present
        if text.startswith('```json'):
            text = text[7:]
        if text.startswith('```'):
            text = text[3:]
        if text.endswith('```'):
            text = text[:-3]

        insights = json.loads(text.strip())
        return insights
    except Exception as e:
        print(f"Error generating AI insights: {e}")
        beta_val = market_data.get("beta", "N/A")
        beta_str = f"{beta_val:.2f}" if isinstance(beta_val, (int, float)) else str(beta_val)
        return {
            'momentum_insight': f'Analyzing {market_data["change_90d"]:.0f}% quarterly performance...',
            'volume_insight': f'Trading volume is {market_data["volume_ratio"]:.1f}x average...',
            'volatility_insight': f'Beta of {beta_str} indicates volatility profile...'
        }


def generate_ai_predictions(market_data):
    """Generate AI-powered predictions using Gemini"""
    if not model:
        return {
            'short_term': {
                'direction': 'AI predictions unavailable',
                'confidence': 0,
                'prediction': 'Gemini API key not configured'
            },
            'medium_term': {
                'direction': 'AI predictions unavailable',
                'confidence': 0,
                'prediction': 'Gemini API key not configured'
            },
            'risk_assessment': {
                'level': 'UNKNOWN',
                'icon': '⚠️',
                'assessment': 'AI risk assessment unavailable'
            }
        }

    try:
        prompt = f"""
Based on this market data for IREN (Iris Energy Limited), provide trading predictions:

Current Price: ${market_data['current_price']}
Daily Change: {market_data['daily_change']}%
30-Day Change: {market_data['change_30d']}%
90-Day Change: {market_data['change_90d']}%
Volume Ratio: {market_data['volume_ratio']}x
Beta: {market_data['beta']}
P/E Ratio: {market_data['pe_ratio']}
52-Week High: ${market_data['high_52w']}
Distance from High: {((market_data['high_52w'] - market_data['current_price']) / market_data['current_price'] * 100):.1f}%

Generate predictions as JSON with this structure:
{{
  "short_term": {{
    "direction": "Brief prediction title with emoji (e.g., '🚀 Bullish Continuation')",
    "confidence": 65-85,
    "prediction": "Detailed 7-day outlook with specific price targets and key levels (3-4 sentences)"
  }},
  "medium_term": {{
    "direction": "Brief prediction title with emoji",
    "confidence": 60-80,
    "prediction": "Detailed 30-day outlook with targets and risks (3-4 sentences)"
  }},
  "risk_assessment": {{
    "level": "HIGH RISK/MODERATE-HIGH RISK/MODERATE RISK",
    "icon": "🔴/🟡/🟢",
    "assessment": "Comprehensive risk analysis with specific risk factors and recommendations (4-5 sentences)"
  }}
}}

Be specific with price levels, technical factors, and actionable insights. Return ONLY valid JSON.
"""

        response = model.generate_content(prompt)

        # Parse the response
        text = response.text.strip()
        if text.startswith('```json'):
            text = text[7:]
        if text.startswith('```'):
            text = text[3:]
        if text.endswith('```'):
            text = text[:-3]

        predictions = json.loads(text.strip())
        return predictions
    except Exception as e:
        print(f"Error generating AI predictions: {e}")
        beta_val = market_data.get("beta", "N/A")
        beta_str = f"{beta_val:.2f}" if isinstance(beta_val, (int, float)) else str(beta_val)
        return {
            'short_term': {
                'direction': '📊 Analyzing',
                'confidence': 70,
                'prediction': 'Short-term analysis in progress...'
            },
            'medium_term': {
                'direction': '📈 Evaluating',
                'confidence': 65,
                'prediction': 'Medium-term outlook being calculated...'
            },
            'risk_assessment': {
                'level': 'MODERATE-HIGH RISK',
                'icon': '🟡',
                'assessment': f'Beta of {beta_str} indicates volatility profile. Further analysis required for complete risk assessment.'
            }
        }


@app.route('/api/market-data/<symbol>', methods=['GET'])
def get_market_data(symbol):
    """Fetch real-time market data and AI analysis"""
    try:
        # Fetch data from Yahoo Finance
        chart_data = fetch_yahoo_quote(symbol.upper())
        summary_data = fetch_yahoo_summary(symbol.upper())

        if not chart_data:
            return jsonify({'error': 'Failed to fetch market data'}), 500

        # Calculate metrics
        market_data = calculate_metrics(chart_data, summary_data)

        if not market_data:
            return jsonify({'error': 'Failed to calculate metrics'}), 500

        # Generate AI insights and predictions
        insights = generate_ai_insights(market_data)
        predictions = generate_ai_predictions(market_data)

        # Combine all data
        response_data = {
            **market_data,
            'insights': insights,
            'predictions': predictions
        }

        return jsonify(response_data)

    except Exception as e:
        print(f"Error in get_market_data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'gemini_configured': GEMINI_API_KEY is not None,
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    print(f"Starting IREN Market Insights Server...")
    print(f"Gemini API configured: {GEMINI_API_KEY is not None}")
    app.run(debug=True, port=5000)
