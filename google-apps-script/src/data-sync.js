/**
 * Data synchronization functions for external APIs
 * Handles fetching real-time market data for trading alerts
 */

/**
 * Fetch data from Yahoo Finance (free, no API key required)
 */
function fetchYahooFinanceData(symbol = 'IWM') {
  try {
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}?interval=1m&range=1d`;
    const response = UrlFetchApp.fetch(url);
    const data = JSON.parse(response.getContentText());
    
    if (!data.chart || !data.chart.result || data.chart.result.length === 0) {
      throw new Error('No data returned from Yahoo Finance');
    }

    const result = data.chart.result[0];
    const meta = result.meta;
    const quote = result.indicators.quote[0];
    const timestamps = result.timestamp;
    
    // Get the latest data point
    const latestIndex = timestamps.length - 1;
    
    return {
      symbol: symbol,
      price: quote.close[latestIndex] || meta.regularMarketPrice,
      open: quote.open[latestIndex],
      high: quote.high[latestIndex],
      low: quote.low[latestIndex],
      volume: quote.volume[latestIndex],
      previousClose: meta.previousClose,
      regularMarketPrice: meta.regularMarketPrice,
      timestamp: new Date(timestamps[latestIndex] * 1000)
    };
  } catch (error) {
    console.error('Error fetching Yahoo Finance data:', error);
    return null;
  }
}

/**
 * Calculate technical indicators from price data
 */
function calculateTechnicalIndicators(symbol = 'IWM', period = '5d') {
  try {
    // Fetch historical data for calculations
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}?interval=1m&range=${period}`;
    const response = UrlFetchApp.fetch(url);
    const data = JSON.parse(response.getContentText());
    
    if (!data.chart || !data.chart.result || data.chart.result.length === 0) {
      throw new Error('No historical data available');
    }

    const result = data.chart.result[0];
    const quote = result.indicators.quote[0];
    const timestamps = result.timestamp;
    
    // Extract price arrays
    const closes = quote.close.filter(price => price !== null);
    const highs = quote.high.filter(price => price !== null);
    const lows = quote.low.filter(price => price !== null);
    const volumes = quote.volume.filter(vol => vol !== null);
    
    if (closes.length < 14) {
      throw new Error('Insufficient data for technical indicators');
    }

    // Calculate RSI
    const rsi = calculateRSI(closes, 14);
    
    // Calculate VWAP (for current day)
    const vwap = calculateVWAP(closes, highs, lows, volumes);
    
    // Calculate Relative Volume
    const currentVolume = volumes[volumes.length - 1];
    const avgVolume = volumes.slice(-20).reduce((a, b) => a + b, 0) / Math.min(20, volumes.length);
    const rvol = currentVolume / avgVolume;
    
    // Calculate ATR
    const atr = calculateATR(highs, lows, closes, 14);
    
    return {
      rsi: rsi,
      vwap: vwap,
      rvol: rvol,
      atr: atr,
      currentPrice: closes[closes.length - 1],
      volume: currentVolume,
      timestamp: new Date()
    };
    
  } catch (error) {
    console.error('Error calculating technical indicators:', error);
    return null;
  }
}

/**
 * Calculate RSI (Relative Strength Index)
 */
function calculateRSI(closes, period = 14) {
  if (closes.length < period + 1) return null;
  
  const changes = [];
  for (let i = 1; i < closes.length; i++) {
    changes.push(closes[i] - closes[i - 1]);
  }
  
  let avgGain = 0;
  let avgLoss = 0;
  
  // Initial calculation
  for (let i = 0; i < period; i++) {
    if (changes[i] > 0) avgGain += changes[i];
    else avgLoss -= changes[i];
  }
  
  avgGain /= period;
  avgLoss /= period;
  
  // Calculate RSI for the latest period
  for (let i = period; i < changes.length; i++) {
    const change = changes[i];
    const gain = change > 0 ? change : 0;
    const loss = change < 0 ? -change : 0;
    
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
  }
  
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

/**
 * Calculate VWAP (Volume Weighted Average Price)
 */
function calculateVWAP(closes, highs, lows, volumes) {
  if (closes.length !== highs.length || closes.length !== lows.length || closes.length !== volumes.length) {
    return null;
  }
  
  let totalVolume = 0;
  let totalVolumePrice = 0;
  
  for (let i = 0; i < closes.length; i++) {
    const typicalPrice = (highs[i] + lows[i] + closes[i]) / 3;
    const volume = volumes[i];
    
    totalVolumePrice += typicalPrice * volume;
    totalVolume += volume;
  }
  
  return totalVolume > 0 ? totalVolumePrice / totalVolume : null;
}

/**
 * Calculate ATR (Average True Range)
 */
function calculateATR(highs, lows, closes, period = 14) {
  if (highs.length < period + 1) return null;
  
  const trueRanges = [];
  
  for (let i = 1; i < highs.length; i++) {
    const high = highs[i];
    const low = lows[i];
    const prevClose = closes[i - 1];
    
    const tr1 = high - low;
    const tr2 = Math.abs(high - prevClose);
    const tr3 = Math.abs(low - prevClose);
    
    trueRanges.push(Math.max(tr1, tr2, tr3));
  }
  
  // Calculate simple moving average of true ranges
  const recentTR = trueRanges.slice(-period);
  return recentTR.reduce((a, b) => a + b, 0) / recentTR.length;
}

/**
 * Get comprehensive market data with technical indicators
 */
function getMarketDataWithIndicators(symbol = 'IWM') {
  try {
    const priceData = fetchYahooFinanceData(symbol);
    const indicators = calculateTechnicalIndicators(symbol);
    
    if (!priceData || !indicators) {
      console.log('Failed to fetch complete market data');
      return null;
    }
    
    return {
      symbol: symbol,
      price: priceData.price,
      volume: priceData.volume,
      previousClose: priceData.previousClose,
      vwap: indicators.vwap,
      rsi: indicators.rsi,
      rvol: indicators.rvol,
      atr: indicators.atr,
      timestamp: new Date()
    };
    
  } catch (error) {
    console.error('Error getting market data with indicators:', error);
    return null;
  }
}

/**
 * Cache market data to reduce API calls
 */
function getCachedMarketData(symbol = 'IWM', maxAgeMinutes = 1) {
  const cache = CacheService.getScriptCache();
  const cacheKey = `market_data_${symbol}`;
  
  try {
    const cached = cache.get(cacheKey);
    if (cached) {
      const data = JSON.parse(cached);
      const age = (new Date() - new Date(data.timestamp)) / (1000 * 60);
      
      if (age < maxAgeMinutes) {
        console.log(`Using cached data for ${symbol} (${age.toFixed(1)} min old)`);
        return data;
      }
    }
    
    // Fetch fresh data
    console.log(`Fetching fresh data for ${symbol}`);
    const freshData = getMarketDataWithIndicators(symbol);
    
    if (freshData) {
      // Cache for 5 minutes
      cache.put(cacheKey, JSON.stringify(freshData), 300);
    }
    
    return freshData;
    
  } catch (error) {
    console.error('Error with cached market data:', error);
    return getMarketDataWithIndicators(symbol);
  }
}

/**
 * Test function for data synchronization
 */
function testDataSync() {
  console.log('Testing data synchronization...');
  
  const data = getCachedMarketData('IWM');
  console.log('Market Data:', data);
  
  if (data) {
    console.log(`Price: $${data.price}`);
    console.log(`RSI: ${data.rsi?.toFixed(2)}`);
    console.log(`VWAP: $${data.vwap?.toFixed(2)}`);
    console.log(`RVOL: ${data.rvol?.toFixed(2)}x`);
    console.log(`ATR: ${data.atr?.toFixed(4)}`);
  }
}
