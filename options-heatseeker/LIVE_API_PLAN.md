# Options Heatseeker - Live API Integration Plan

## Executive Summary

Transform Options Heatseeker from static JSON files to live Alpha Vantage API integration. This will provide real-time options data without the need for data conversion scripts, making the application truly dynamic.

## Current vs. Proposed Architecture

### Current Architecture (Static)
```
User → App → Load JSON files → Display
               ↑
        Pre-converted from Parquet
        (15min conversion, 500MB+ files)
```

**Problems:**
- ✗ Requires manual data conversion (15+ minutes)
- ✗ Large file sizes (500MB combined files)
- ✗ Static data (not live)
- ✗ GitHub storage limits (100MB per file)
- ✗ Deployment includes all data files

### Proposed Architecture (Live API)
```
User → App → Alpha Vantage API → Cache → Display
                  ↓
          localStorage/IndexedDB
          (instant subsequent loads)
```

**Benefits:**
- ✅ **Live data** - Always current
- ✅ **Simpler** - No conversion scripts needed
- ✅ **Smaller deployment** - No data files in repository
- ✅ **User-provided API key** - No server costs
- ✅ **Client-side caching** - Fast repeat visits
- ✅ **On-demand loading** - Only fetch what's needed

---

## Alpha Vantage API Details

### Endpoint
```
https://www.alphavantage.co/query
```

### Parameters
```javascript
{
  function: 'HISTORICAL_OPTIONS',
  symbol: 'IWM',        // Stock ticker
  date: '2025-11-14',   // YYYY-MM-DD format
  apikey: 'YOUR_KEY_HERE'
}
```

### Response Format
```json
{
  "endpoint": "Historical Options",
  "message": "success",
  "data": [
    {
      "contractID": "IWM251121C00210000",
      "symbol": "IWM",
      "type": "call",
      "strike": "210.00",
      "expiration": "2025-11-21",
      "last": "2.10",
      "mark": "2.15",
      "bid": "2.10",
      "bid_size": 150,
      "ask": "2.20",
      "ask_size": 100,
      "volume": 5000,
      "open_interest": 12500,
      "date": "2025-11-14",
      "implied_volatility": "0.25",
      "delta": "0.50",
      "gamma": "0.05",
      "theta": "-0.02",
      "vega": "0.10",
      "rho": "0.01"
    }
    // ... hundreds more contracts
  ]
}
```

### Rate Limits
- **Free Tier**: 5 calls/minute, 500 calls/day
- **Premium**: Higher limits available
- **Strategy**: Aggressive client-side caching

---

## Implementation Plan

### Phase 1: API Service Module (Priority: HIGH)

**File**: `options-heatseeker/js/apiService.js`

**Features**:
- Alpha Vantage API integration
- Rate limiting (5 calls/min)
- Request queuing
- Error handling
- Retry logic with exponential backoff

**Code Structure**:
```javascript
const APIService = {
    // Configuration
    apiKey: null,
    baseURL: 'https://www.alphavantage.co/query',
    requestQueue: [],
    isProcessing: false,
    rateLimitDelay: 12000, // 12 seconds (5 calls/min)

    // Methods
    setAPIKey(key),
    fetchOptionsChain(symbol, date),
    processQueue(),
    handleRateLimit(),
    parseResponse(data),
    validateResponse(data)
};
```

### Phase 2: Client-Side Caching (Priority: HIGH)

**File**: `options-heatseeker/js/cacheService.js`

**Strategy**: Multi-layer caching for performance

**Cache Layers**:
1. **Memory Cache** (fastest)
   - In-memory object store
   - Clears on page refresh
   - Size limit: 50MB

2. **LocalStorage** (persistent, simple)
   - For small datasets (<5MB)
   - Survives page refreshes
   - 5-10MB total limit

3. **IndexedDB** (persistent, large)
   - For full options chains
   - No practical size limit
   - Survives page refreshes

**Cache Keys**:
```javascript
`options_${symbol}_${date}` // e.g., "options_iwm_20251114"
```

**Cache Expiry**:
- **Same day**: Cache for 1 hour (data may update)
- **Historical**: Cache for 7 days (unlikely to change)
- **Manual clear**: User can clear cache via settings

**Code Structure**:
```javascript
const CacheService = {
    memoryCache: new Map(),

    async get(key),
    async set(key, data, ttl),
    async has(key),
    async delete(key),
    async clear(),
    async getSize(),

    // Helper methods
    isExpired(timestamp, ttl),
    shouldCache(date),
    getCacheTTL(date)
};
```

### Phase 3: Update DataLoader (Priority: HIGH)

**File**: `options-heatseeker/js/dataLoader.js`

**Changes**:
```javascript
// OLD: Load from static JSON
async loadOptionsData(ticker, dateStr) {
    const url = `data/${ticker}/${ticker}_options_${dateStr}.json`;
    const response = await fetch(url);
    return response.json();
}

// NEW: Load from API with caching
async loadOptionsData(ticker, dateStr) {
    // 1. Check cache first
    const cacheKey = `options_${ticker}_${dateStr}`;
    const cached = await CacheService.get(cacheKey);

    if (cached) {
        console.log(`Cache hit: ${cacheKey}`);
        return this.processOptionsData(cached);
    }

    // 2. Fetch from API
    const data = await APIService.fetchOptionsChain(ticker, dateStr);

    // 3. Cache the response
    await CacheService.set(cacheKey, data, this.getCacheTTL(dateStr));

    // 4. Process and return
    return this.processOptionsData(data);
}
```

### Phase 4: API Key Configuration UI (Priority: MEDIUM)

**File**: `options-heatseeker/index.html` + CSS

**Features**:
- Settings modal/panel
- API key input (password field)
- Save to localStorage
- Test connection button
- Rate limit status display
- Usage statistics

**UI Flow**:
```
1. User opens app
2. If no API key → Show welcome modal
3. User enters API key
4. Test connection (fetch a sample date)
5. Save key to localStorage (encrypted)
6. App loads normally
```

**Settings Panel**:
```html
<div id="settings-modal">
    <h3>API Settings</h3>

    <div class="form-group">
        <label>Alpha Vantage API Key</label>
        <input type="password" id="api-key-input"
               placeholder="Enter your API key">
        <button id="test-api-key">Test Connection</button>
        <p class="help-text">
            Get your free API key at
            <a href="https://www.alphavantage.co/support/#api-key">
                Alpha Vantage
            </a>
        </p>
    </div>

    <div class="api-status">
        <h4>API Status</h4>
        <p>Calls today: <span id="calls-today">0</span> / 500</p>
        <p>Rate limit: <span id="rate-limit-status">OK</span></p>
    </div>

    <div class="cache-stats">
        <h4>Cache Statistics</h4>
        <p>Cached datasets: <span id="cache-count">0</span></p>
        <p>Cache size: <span id="cache-size">0 MB</span></p>
        <button id="clear-cache">Clear Cache</button>
    </div>
</div>
```

### Phase 5: Error Handling (Priority: HIGH)

**Scenarios to Handle**:

1. **No API Key**
   ```javascript
   if (!APIService.apiKey) {
       showAPIKeyModal();
       throw new Error('API key required');
   }
   ```

2. **Invalid API Key**
   ```javascript
   if (response.contains('Invalid API call')) {
       showError('Invalid API key. Please check your settings.');
       showAPIKeyModal();
   }
   ```

3. **Rate Limit Exceeded**
   ```javascript
   if (response.contains('rate limit')) {
       const retryAfter = 60; // seconds
       showNotification(`Rate limit exceeded. Retry in ${retryAfter}s`);
       queueRequest(symbol, date, retryAfter);
   }
   ```

4. **Network Error**
   ```javascript
   try {
       const data = await fetch(...);
   } catch (error) {
       // Try cache first
       const cached = await CacheService.get(cacheKey);
       if (cached) return cached;

       // Show error
       showError('Network error. Please check your connection.');
   }
   ```

5. **No Data for Date**
   ```javascript
   if (response.data.length === 0) {
       showWarning('No options data available for this date (market closed?)');
       // Suggest nearest trading day
   }
   ```

### Phase 6: Request Queue System (Priority: MEDIUM)

**Purpose**: Respect rate limits, queue multiple requests

**Implementation**:
```javascript
const RequestQueue = {
    queue: [],
    processing: false,
    lastRequestTime: 0,
    minDelay: 12000, // 12 seconds

    async add(request) {
        this.queue.push(request);
        if (!this.processing) {
            this.process();
        }
    },

    async process() {
        this.processing = true;

        while (this.queue.length > 0) {
            const timeSinceLastRequest = Date.now() - this.lastRequestTime;

            if (timeSinceLastRequest < this.minDelay) {
                const waitTime = this.minDelay - timeSinceLastRequest;
                await this.sleep(waitTime);
            }

            const request = this.queue.shift();
            await this.execute(request);
            this.lastRequestTime = Date.now();
        }

        this.processing = false;
    },

    async execute(request) {
        try {
            const data = await APIService.fetchOptionsChain(
                request.symbol,
                request.date
            );
            request.resolve(data);
        } catch (error) {
            request.reject(error);
        }
    },

    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
};
```

### Phase 7: Progressive Enhancement (Priority: LOW)

**Features for Future**:

1. **Prefetching**
   - Prefetch nearby dates when user selects a date
   - Background loading during idle time

2. **Service Worker**
   - Offline support
   - Background sync
   - Push notifications for rate limit reset

3. **WebWorker**
   - Move heavy calculations to background thread
   - Don't block UI during data processing

4. **Batch Requests**
   - If multiple dates needed, queue them efficiently
   - Show progress indicator

---

## Deployment Changes

### Remove from Repository
```bash
# Delete static data files
rm -rf options-heatseeker/data/

# Delete conversion script (no longer needed)
rm options-heatseeker/convert_parquet_to_json.py

# Update .gitignore
echo "data/" >> options-heatseeker/.gitignore
```

### Update Workflow
```yaml
# .github/workflows/deploy-trading-apps.yml
# Remove data file copying steps
# App now fetches data via API
```

### Repository Size
- **Before**: ~2GB (with data files)
- **After**: ~5MB (code only)

---

## Testing Strategy

### Unit Tests
```javascript
// Test API service
test('APIService.fetchOptionsChain returns data', async () => {
    const data = await APIService.fetchOptionsChain('IWM', '2025-11-14');
    expect(data).toBeDefined();
    expect(data.data).toBeArray();
});

// Test caching
test('CacheService stores and retrieves data', async () => {
    await CacheService.set('test', { foo: 'bar' });
    const retrieved = await CacheService.get('test');
    expect(retrieved.foo).toBe('bar');
});

// Test rate limiting
test('RequestQueue respects rate limits', async () => {
    const start = Date.now();
    await RequestQueue.add({ symbol: 'IWM', date: '2025-11-14' });
    await RequestQueue.add({ symbol: 'QQQ', date: '2025-11-14' });
    const duration = Date.now() - start;
    expect(duration).toBeGreaterThan(12000); // 12 second delay
});
```

### Integration Tests
1. Load app without API key → Should show setup modal
2. Enter valid API key → Should fetch data successfully
3. Select different dates → Should queue requests properly
4. Clear cache → Should refetch data
5. Go offline → Should use cached data

### Performance Benchmarks
- **First load**: <5 seconds (including API call)
- **Cached load**: <500ms
- **Date switching**: <2 seconds (with cache)

---

## Migration Path

### Step 1: Add New Files (No Breaking Changes)
```bash
git add options-heatseeker/js/apiService.js
git add options-heatseeker/js/cacheService.js
git commit -m "Add API and cache services"
```

### Step 2: Feature Flag
```javascript
// config.js
const CONFIG = {
    USE_LIVE_API: false, // Toggle this to switch modes
    ...
};
```

### Step 3: Parallel Implementation
```javascript
// dataLoader.js
async loadOptionsData(ticker, dateStr) {
    if (CONFIG.USE_LIVE_API) {
        return this.loadFromAPI(ticker, dateStr);
    } else {
        return this.loadFromStaticFiles(ticker, dateStr);
    }
}
```

### Step 4: Test & Enable
```javascript
// Once tested, flip the flag
const CONFIG = {
    USE_LIVE_API: true, // Now using live API
    ...
};
```

### Step 5: Remove Static Files
```bash
git rm -r options-heatseeker/data/
git commit -m "Remove static data files, using live API"
```

---

## Cost Analysis

### Current (Static Files)
- **Developer time**: 15 minutes per data update
- **GitHub storage**: ~2GB
- **Bandwidth**: High (serving large JSON files)
- **Cost**: $0 (but painful workflow)

### Proposed (Live API)
- **API cost**: $0 (using user's free Alpha Vantage key)
- **Storage**: ~5MB (no data files)
- **Bandwidth**: Minimal (user fetches from Alpha Vantage)
- **Developer time**: 0 (fully automated)
- **Cost**: $0 + much better UX!

---

## Success Metrics

✅ **Deployment size** reduced from 2GB to 5MB
✅ **No manual data conversion** required
✅ **Live data** always current
✅ **Cache hit rate** > 80% for repeat visits
✅ **First load time** < 5 seconds
✅ **Cached load time** < 500ms
✅ **Rate limit errors** < 1% of requests

---

## Timeline

### Week 1: Core Implementation
- Day 1-2: apiService.js + cacheService.js
- Day 3-4: Update dataLoader.js with API calls
- Day 5: Testing & bug fixes

### Week 2: UI & Polish
- Day 1-2: API key configuration UI
- Day 3: Error handling & user feedback
- Day 4-5: Testing & optimization

### Week 3: Deployment
- Day 1: Remove static files
- Day 2: Update workflows
- Day 3: Final testing
- Day 4: Deploy to production
- Day 5: Monitor & iterate

**Total**: 3 weeks from start to production

---

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Rate limits hit frequently | High | Aggressive caching, request queuing, show clear feedback |
| Users don't have API key | High | Clear onboarding, free key signup link, demo mode with sample data |
| API changes format | Medium | Versioned API calls, error handling, fallback to cached data |
| Network errors | Medium | Offline mode with cache, clear error messages, retry logic |
| Cache bugs | Low | Extensive testing, manual clear cache option |

---

## Next Steps

1. **Review this plan** with stakeholders
2. **Get Alpha Vantage API key** for testing
3. **Start implementation** with apiService.js
4. **Test thoroughly** before removing static files
5. **Deploy incrementally** with feature flag

---

## Questions to Answer

1. Should we support **demo mode** with sample data for users without API keys?
2. Do we need **multiple API key support** (for power users with premium accounts)?
3. Should we **prefetch** common date ranges to improve UX?
4. What's the **fallback** if Alpha Vantage changes their API?
5. Do we want **analytics** on cache hit rates and API usage?

---

This plan provides a **clear path** from static files to live API integration while maintaining a **great user experience** and **zero backend costs**!
