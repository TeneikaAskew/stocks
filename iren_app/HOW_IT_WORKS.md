# How the IREN Dashboard Works

A detailed technical explanation of the AI-powered market insights dashboard.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER BROWSER                            │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  index.html (UI Structure)                                │ │
│  │  ├── Header with title & last updated                     │ │
│  │  ├── Metrics cards (price, market cap, changes)           │ │
│  │  ├── Interactive chart (Chart.js)                         │ │
│  │  ├── Volume analysis section                              │ │
│  │  ├── Technical indicators                                 │ │
│  │  ├── AI-generated insights (3 cards)                      │ │
│  │  └── AI-generated predictions (3 cards)                   │ │
│  └───────────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  app.js (Frontend Logic)                                  │ │
│  │  ├── Fetches data from backend                            │ │
│  │  ├── Updates all UI elements                              │ │
│  │  ├── Renders Chart.js visualization                       │ │
│  │  └── Auto-refreshes every 5 minutes                       │ │
│  └───────────────────────────────────────────────────────────┘ │
│                              ↓                                  │
│                    HTTP GET /api/market-data/IREN               │
└──────────────────────────────┬──────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                   FLASK BACKEND SERVER                          │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  server.py (Python Flask)                                 │ │
│  │  ├── Receives API request                                 │ │
│  │  ├── Calls Yahoo Finance API                              │ │
│  │  ├── Processes & calculates metrics                       │ │
│  │  ├── Generates AI prompts                                 │ │
│  │  ├── Calls Gemini AI                                      │ │
│  │  └── Returns combined JSON response                       │ │
│  └───────────────────────────────────────────────────────────┘ │
│                              ↓                                  │
│                    ┌─────────┴─────────┐                        │
│                    ↓                   ↓                        │
│    ┌───────────────────────┐  ┌──────────────────────┐         │
│    │  Yahoo Finance API    │  │   Google Gemini AI   │         │
│    │  - Real-time quotes   │  │   - Insights gen.    │         │
│    │  - Historical data    │  │   - Predictions      │         │
│    │  - Market metadata    │  │   - Risk analysis    │         │
│    └───────────────────────┘  └──────────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow: Step-by-Step

### Step 1: User Opens Dashboard

```
User opens index.html
    ↓
DOM loads completely
    ↓
DOMContentLoaded event fires
    ↓
IrenDashboard class instantiated
    ↓
init() method called
```

### Step 2: Frontend Initialization

**File: app.js**

```javascript
async init() {
    await this.fetchData();        // Get data from backend
    this.updateUI();               // Update all metrics
    this.createChart();            // Render price chart
    this.generateInsights();       // Display AI insights
    this.generatePredictions();    // Display AI predictions
    setInterval(() => this.refresh(), 300000);  // Auto-refresh every 5 min
}
```

### Step 3: API Request to Backend

**Frontend makes HTTP request:**

```javascript
async fetchData() {
    const response = await fetch('http://localhost:5000/api/market-data/IREN');
    const data = await response.json();

    this.data = data;                    // Store market data
    this.historicalData = data.historical_data;  // Store price history
    this.insights = data.insights;       // Store AI insights
    this.predictions = data.predictions; // Store AI predictions
}
```

### Step 4: Backend Processes Request

**File: server.py**

```python
@app.route('/api/market-data/<symbol>', methods=['GET'])
def get_market_data(symbol):
    # 1. Fetch from Yahoo Finance
    chart_data = fetch_yahoo_quote(symbol.upper())
    summary_data = fetch_yahoo_summary(symbol.upper())

    # 2. Calculate metrics
    market_data = calculate_metrics(chart_data, summary_data)

    # 3. Generate AI insights
    insights = generate_ai_insights(market_data)

    # 4. Generate AI predictions
    predictions = generate_ai_predictions(market_data)

    # 5. Combine and return
    response_data = {
        **market_data,
        'insights': insights,
        'predictions': predictions
    }

    return jsonify(response_data)
```

### Step 5: Yahoo Finance API Call

**Backend fetches real-time data:**

```python
def fetch_yahoo_quote(symbol, interval='1d', range='3mo'):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        'interval': interval,    # Daily candles
        'range': range,          # 3 months of data
        'includePrePost': 'true' # Include pre/post market
    }

    response = requests.get(url, params=params, headers=headers)
    return response.json()
```

**Yahoo Finance returns:**
```json
{
  "chart": {
    "result": [{
      "meta": {
        "symbol": "IREN",
        "regularMarketPrice": 67.98,
        "previousClose": 69.56,
        ...
      },
      "timestamp": [1720000000, 1720086400, ...],
      "indicators": {
        "quote": [{
          "open": [68.50, 69.20, ...],
          "high": [70.15, 71.30, ...],
          "low": [67.80, 68.95, ...],
          "close": [69.56, 70.45, ...],
          "volume": [45000000, 52000000, ...]
        }]
      }
    }]
  }
}
```

### Step 6: Metric Calculation

**Backend processes raw data:**

```python
def calculate_metrics(chart_data, summary_data):
    # Extract values
    current_price = meta['regularMarketPrice']
    prev_close = meta['previousClose']

    # Calculate changes
    daily_change = ((current_price - prev_close) / prev_close * 100)

    # Calculate 30-day change
    price_30d_ago = close_prices[-30]
    change_30d = ((current_price - price_30d_ago) / price_30d_ago * 100)

    # Calculate 90-day change
    price_90d_ago = close_prices[0]
    change_90d = ((current_price - price_90d_ago) / price_90d_ago * 100)

    # Volume analysis
    avg_volume = sum(volumes[-30:]) / len(volumes[-30:])
    volume_ratio = current_volume / avg_volume

    return {
        'current_price': 67.98,
        'daily_change': -2.27,
        'change_30d': 160.16,
        'change_90d': 278.93,
        'volume_ratio': 1.11,
        'beta': 4.199,
        ...
    }
```

### Step 7: AI Insights Generation

**Backend creates structured prompt for Gemini:**

```python
def generate_ai_insights(market_data):
    prompt = f"""
Analyze the following market data for IREN (Iris Energy Limited):

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

Return ONLY a JSON object with these three keys. Be specific with numbers.
"""

    response = model.generate_content(prompt)
    insights = json.loads(response.text)
    return insights
```

**Gemini AI returns:**
```json
{
  "momentum_insight": "IREN has demonstrated exceptional momentum with a staggering 278.93% gain over 90 days, more than tripling in value. The recent 30-day surge of 160.16% suggests accelerating bullish sentiment. However, today's -2.27% pullback may indicate profit-taking after the dramatic run-up.",

  "volume_insight": "Trading volume is slightly elevated at 1.11x the 30-day average (47.7M shares), showing sustained investor interest without extreme speculative activity. This moderate volume increase alongside massive price gains suggests institutional participation rather than purely retail-driven momentum.",

  "volatility_insight": "With a beta of 4.199, IREN exhibits extreme volatility, moving over 4 times more than the broader market. The P/E ratio of 174.31 indicates a premium valuation. Investors should expect significant price swings in both directions and consider this a high-risk, high-reward opportunity requiring careful position sizing."
}
```

### Step 8: AI Predictions Generation

**Backend creates prediction prompt:**

```python
def generate_ai_predictions(market_data):
    prompt = f"""
Based on this market data for IREN, provide trading predictions:

Current Price: ${market_data['current_price']}
Daily Change: {market_data['daily_change']}%
30-Day Change: {market_data['change_30d']}%
90-Day Change: {market_data['change_90d']}%
Volume Ratio: {market_data['volume_ratio']}x
Beta: {market_data['beta']}
Distance from 52W High: {((market_data['high_52w'] - market_data['current_price']) / market_data['current_price'] * 100):.1f}%

Generate predictions as JSON:
{{
  "short_term": {{
    "direction": "Brief prediction with emoji",
    "confidence": 65-85,
    "prediction": "7-day outlook with price targets (3-4 sentences)"
  }},
  "medium_term": {{
    "direction": "Brief prediction with emoji",
    "confidence": 60-80,
    "prediction": "30-day outlook with risks (3-4 sentences)"
  }},
  "risk_assessment": {{
    "level": "HIGH RISK/MODERATE-HIGH RISK/MODERATE RISK",
    "icon": "🔴/🟡/🟢",
    "assessment": "Comprehensive risk analysis (4-5 sentences)"
  }}
}}

Be specific with price levels and technical factors.
"""

    response = model.generate_content(prompt)
    predictions = json.loads(response.text)
    return predictions
```

**Gemini AI returns:**
```json
{
  "short_term": {
    "direction": "📉 Consolidation Expected",
    "confidence": 72,
    "prediction": "After today's -2.27% decline, IREN may enter a consolidation phase between $65-$72. The stock needs to digest recent massive gains. Key support at $65; if broken, could test $60. Resistance at previous high of $74.15. Watch for stabilization over next 3-5 days before next directional move."
  },

  "medium_term": {
    "direction": "⚠️ Cautiously Bullish with Pullback Risk",
    "confidence": 68,
    "prediction": "While the 279% quarterly gain is exceptional, IREN is trading near 52-week highs with elevated valuation (P/E 174). Expect volatility with potential pullback to $55-$62 range before next leg up. If consolidation holds above $65, targets $80-$90 within 30 days. High beta means large swings likely. Momentum remains positive but overextension risk is elevated."
  },

  "risk_assessment": {
    "level": "HIGH RISK",
    "icon": "🔴",
    "assessment": "IREN presents very high risk due to multiple factors: Beta of 4.199 indicates extreme volatility (4x market moves). Recent 279% gain creates significant pullback risk as early investors take profits. Premium P/E of 174 suggests the stock is priced for perfection - any earnings miss could trigger sharp decline. This is suitable only for risk-tolerant traders with strict stop-losses. Position sizing is critical - consider limiting to 1-3% of portfolio. The high volatility creates both massive opportunity and substantial downside risk."
  }
}
```

### Step 9: Response Assembly & Return

**Backend combines all data:**

```python
response_data = {
    # Market data
    'company': 'IREN Limited',
    'ticker': 'IREN',
    'current_price': 67.98,
    'daily_change': -2.27,
    'change_30d': 160.16,
    'change_90d': 278.93,
    'market_cap': 18489233408,
    'volume': 47676286,
    'avg_volume': 42945686,
    'volume_ratio': 1.11,
    'high_52w': 74.15,
    'low_52w': 14.72,
    'pe_ratio': 174.31,
    'beta': 4.199,

    # Historical data for chart
    'historical_data': [
        {'date': '2025-07-15', 'price': 18.50, 'volume': 25000000},
        {'date': '2025-07-16', 'price': 19.20, 'volume': 28000000},
        ...
        {'date': '2025-10-15', 'price': 67.98, 'volume': 47676286}
    ],

    # AI-generated insights
    'insights': {
        'momentum_insight': 'IREN has demonstrated exceptional momentum...',
        'volume_insight': 'Trading volume is slightly elevated...',
        'volatility_insight': 'With a beta of 4.199, IREN exhibits...'
    },

    # AI-generated predictions
    'predictions': {
        'short_term': { ... },
        'medium_term': { ... },
        'risk_assessment': { ... }
    }
}

return jsonify(response_data)
```

### Step 10: Frontend Updates UI

**JavaScript updates all elements:**

```javascript
updateUI() {
    // Update metrics
    document.getElementById('currentPrice').textContent = `$${this.data.current_price}`;
    document.getElementById('dailyChange').textContent = `${this.data.daily_change}%`;
    document.getElementById('change30d').textContent = `+${this.data.change_30d}%`;

    // Update volume
    document.getElementById('currentVolume').textContent = this.formatNumber(this.data.volume);
    document.getElementById('volumeRatio').textContent = `${this.data.volume_ratio}x`;

    // Update technical indicators
    document.getElementById('beta').textContent = this.data.beta;
    document.getElementById('peRatio').textContent = this.data.pe_ratio;
}
```

### Step 11: Chart Rendering

**Create interactive chart with Chart.js:**

```javascript
createChart() {
    const ctx = document.getElementById('priceChart').getContext('2d');

    this.chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: this.historicalData.map(d => d.date),  // X-axis dates
            datasets: [{
                label: 'Price ($)',
                data: this.historicalData.map(d => d.price),  // Y-axis prices
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                fill: true,
                tension: 0.4  // Smooth curves
            }]
        },
        options: {
            responsive: true,
            plugins: {
                tooltip: {
                    mode: 'index',
                    callbacks: {
                        label: (context) => `$${context.parsed.y.toFixed(2)}`
                    }
                }
            }
        }
    });
}
```

### Step 12: Display AI Content

**Show AI-generated insights:**

```javascript
generateInsights() {
    document.getElementById('momentumInsight').textContent =
        this.insights.momentum_insight;

    document.getElementById('volumeInsight').textContent =
        this.insights.volume_insight;

    document.getElementById('volatilityInsight').textContent =
        this.insights.volatility_insight;
}
```

**Show AI-generated predictions:**

```javascript
generatePredictions() {
    // Short-term
    document.getElementById('shortTermDirection').textContent =
        this.predictions.short_term.direction;  // "📉 Consolidation Expected"

    document.getElementById('shortTermConfidence').textContent =
        `${this.predictions.short_term.confidence}% Confidence`;  // "72% Confidence"

    document.getElementById('shortTermPrediction').textContent =
        this.predictions.short_term.prediction;

    // Medium-term (similar)
    // Risk assessment (similar)
}
```

## Key Components Explained

### 1. Yahoo Finance API Integration

**Why Yahoo Finance?**
- Free, no API key required
- Real-time data
- Historical data available
- Comprehensive metadata

**Endpoint Used:**
```
https://query1.finance.yahoo.com/v8/finance/chart/IREN?interval=1d&range=3mo
```

**What We Get:**
- Current price
- Previous close
- 90 days of OHLCV data (Open, High, Low, Close, Volume)
- Market metadata

### 2. Google Gemini AI Integration

**Why Gemini?**
- Powerful language model
- Structured JSON output
- Free tier (60 RPM, 1500 RPD)
- Fast response times

**How We Use It:**
- Create detailed prompts with market context
- Request specific JSON structure
- Parse and validate responses
- Handle errors gracefully

**Prompt Engineering:**
- Include all relevant metrics
- Request specific format (JSON)
- Ask for concrete numbers
- Limit length (2-3 sentences per insight)

### 3. Frontend Architecture

**Class-Based Design:**
```javascript
class IrenDashboard {
    constructor()           // Initialize
    init()                  // Setup
    fetchData()             // Get API data
    updateUI()              // Update elements
    createChart()           // Render chart
    generateInsights()      // Show AI insights
    generatePredictions()   // Show AI predictions
    refresh()               // Auto-refresh logic
}
```

**Why This Design?**
- Encapsulation (all logic in one class)
- Easy state management
- Simple to extend
- Clear separation of concerns

## Performance Characteristics

### Latency Breakdown

1. **Frontend Request**: < 10ms (localhost)
2. **Yahoo Finance API**: 2-5 seconds
3. **Metric Calculation**: < 100ms
4. **Gemini AI Insights**: 3-8 seconds
5. **Gemini AI Predictions**: 3-8 seconds
6. **Response Assembly**: < 50ms
7. **Frontend Rendering**: < 200ms

**Total: 8-20 seconds** (mostly AI generation)

### Optimization Strategies

**Caching:**
- Cache responses for 30-60 seconds
- Same data for multiple users
- Reduce API calls

**Parallel Processing:**
- Fetch Yahoo data while generating insights
- Generate insights and predictions in parallel

**Rate Limiting:**
- Prevent abuse
- Protect API quotas
- Queue requests if needed

## Error Handling

### Backend Errors

```python
try:
    chart_data = fetch_yahoo_quote(symbol)
except Exception as e:
    return jsonify({'error': 'Failed to fetch market data'}), 500
```

### Frontend Errors

```javascript
try {
    const response = await fetch('...');
    if (!response.ok) throw new Error('HTTP error');
} catch (error) {
    this.showError('Failed to fetch data. Please try again.');
}
```

## Security Considerations

1. **API Key Protection**
   - Stored in `.env` (not committed to git)
   - Never exposed to frontend
   - Backend makes all AI calls

2. **Input Validation**
   - Sanitize stock symbols
   - Validate request parameters
   - Prevent injection attacks

3. **Rate Limiting**
   - Protect against abuse
   - Preserve API quotas
   - Use Flask-Limiter

4. **CORS**
   - Restrict to specific origins in production
   - Currently open for development

## Conclusion

This dashboard demonstrates:
- **Real-time data integration** (Yahoo Finance)
- **AI-powered analysis** (Google Gemini)
- **Modern web architecture** (Flask + JavaScript)
- **Interactive visualization** (Chart.js)
- **Responsive design** (CSS Grid + Flexbox)

The system provides traders with:
- Up-to-date market data
- Intelligent insights from AI
- Actionable predictions
- Risk assessment
- Beautiful, intuitive interface

All in a single, cohesive application! 🚀
