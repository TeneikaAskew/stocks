// Data Loader - Handles loading parquet data from Python API or pre-converted JSON

class DataLoader {
    constructor() {
        this.cache = new Map();
        this.availableDates = new Map();
    }

    /**
     * Get API URL based on configuration
     */
    getApiUrl() {
        return CONFIG.USE_LOCAL_API ? CONFIG.LOCAL_API_URL : CONFIG.GITHUB_DATA_URL;
    }

    /**
     * Fetch available months for a ticker (returns YYYYMM format)
     */
    async fetchAvailableMonths(ticker) {
        console.log('[DataLoader] fetchAvailableMonths:', ticker);

        if (this.availableDates.has(ticker)) {
            console.log('[DataLoader] Returning cached dates');
            return this.availableDates.get(ticker);
        }

        try {
            const url = CONFIG.USE_LOCAL_API
                ? `${this.getApiUrl()}/dates/${ticker}`
                : `${this.getApiUrl()}/${ticker.toLowerCase()}/dates.json`;

            console.log('[DataLoader] Fetching from URL:', url);
            console.log('[DataLoader] USE_LOCAL_API:', CONFIG.USE_LOCAL_API);

            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            const months = CONFIG.USE_LOCAL_API ? data.dates : data;

            console.log('[DataLoader] Received dates count:', months.length);
            console.log('[DataLoader] First 5 dates:', months.slice(0, 5));
            console.log('[DataLoader] Last 5 dates:', months.slice(-5));

            this.availableDates.set(ticker, months);
            return months;
        } catch (error) {
            console.error('[DataLoader] Error fetching available months:', error);
            Utils.notify('Error loading available months', 'error');
            return [];
        }
    }

    /**
     * Generate list of trading days from a month (YYYYMM)
     */
    getTradingDaysInMonth(month) {
        const year = parseInt(month.substring(0, 4));
        const monthNum = parseInt(month.substring(4, 6));

        const days = [];
        const date = new Date(year, monthNum - 1, 1);
        const lastDay = new Date(year, monthNum, 0).getDate();

        for (let day = 1; day <= lastDay; day++) {
            const d = new Date(year, monthNum - 1, day);
            // Only include weekdays (Mon-Fri)
            if (d.getDay() !== 0 && d.getDay() !== 6) {
                const dayStr = String(day).padStart(2, '0');
                days.push(`${month}${dayStr}`); // YYYYMMDD
            }
        }

        return days;
    }

    /**
     * Fetch OHLCV data for a specific ticker and date (YYYYMMDD format)
     */
    async fetchData(ticker, date, timeframe = 1) {
        console.log('[DataLoader] fetchData called:', { ticker, date, timeframe });
        console.log('[DataLoader] Date length:', date ? date.length : 'null');
        console.log('[DataLoader] Date value:', date);

        const cacheKey = `${ticker}_${date}_${timeframe}`;

        // Check cache first
        if (this.cache.has(cacheKey)) {
            console.log('[DataLoader] Returning cached data');
            return this.cache.get(cacheKey);
        }

        try {
            // Extract month from date (YYYYMMDD -> YYYYMM)
            const month = date.substring(0, 6);
            console.log('[DataLoader] Extracted month:', month);

            Utils.notify(`Loading ${ticker} data for ${date}...`, 'info');

            const url = CONFIG.USE_LOCAL_API
                ? `${this.getApiUrl()}/data/${ticker}/${month}?date=${date}&timeframe=${timeframe}`
                : `${this.getApiUrl()}/${ticker.toLowerCase()}/${date}_1min.json`;  // Always load 1min data

            console.log('[DataLoader] Fetching data from URL:', url);

            const response = await fetch(url);
            if (!response.ok) {
                console.error('[DataLoader] HTTP error:', response.status, response.statusText);
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            // Check if data is already in the correct format (GitHub Pages)
            let chartData;
            if (data.candlestick && data.volume) {
                // GitHub Pages format - data is already transformed
                console.log('[DataLoader] Data already in correct format (GitHub Pages)');
                console.log('[DataLoader] Candlestick data points:', data.candlestick.length);
                chartData = data;
            } else {
                // API format - needs transformation
                console.log('[DataLoader] Received data points:', data.length);
                chartData = this.transformData(data);
                console.log('[DataLoader] Transformed candles:', chartData.candlestick.length);
            }

            // Aggregate to requested timeframe if needed (GitHub Pages mode)
            if (!CONFIG.USE_LOCAL_API && timeframe > 1) {
                console.log(`[DataLoader] Aggregating to ${timeframe}min timeframe`);
                chartData = this.aggregateTimeframe(chartData, timeframe);
                console.log('[DataLoader] Aggregated candles:', chartData.candlestick.length);
            }

            // Cache the data
            this.cache.set(cacheKey, chartData);

            Utils.notify(`Loaded ${chartData.candlestick.length} candles`, 'success');

            return chartData;
        } catch (error) {
            console.error('[DataLoader] Error fetching data:', error);
            Utils.notify(`Error loading data: ${error.message}`, 'error');
            return null;
        }
    }

    /**
     * Transform raw data to chart format
     */
    transformData(rawData) {
        // Expected format from API:
        // [{ time: timestamp, open: number, high: number, low: number, close: number, volume: number }, ...]

        const candlestick = [];
        const volume = [];

        for (const row of rawData) {
            // Convert timestamp to seconds if needed
            let time = row.time;
            if (typeof time === 'string') {
                time = Math.floor(new Date(time).getTime() / 1000);
            }

            candlestick.push({
                time: time,
                open: parseFloat(row.open),
                high: parseFloat(row.high),
                low: parseFloat(row.low),
                close: parseFloat(row.close),
            });

            volume.push({
                time: time,
                value: parseFloat(row.volume),
                color: row.close >= row.open
                    ? CONFIG.VOLUME_COLORS.upColor
                    : CONFIG.VOLUME_COLORS.downColor,
            });
        }

        return { candlestick, volume };
    }

    /**
     * Aggregate data to different timeframes
     */
    aggregateTimeframe(data, timeframeMinutes) {
        if (timeframeMinutes === 1) {
            return data; // No aggregation needed
        }

        const aggregated = {
            candlestick: [],
            volume: [],
        };

        const timeframeSeconds = timeframeMinutes * 60;
        const buckets = new Map();

        // Group candles by timeframe
        for (let i = 0; i < data.candlestick.length; i++) {
            const candle = data.candlestick[i];
            const bucketTime = Math.floor(candle.time / timeframeSeconds) * timeframeSeconds;

            if (!buckets.has(bucketTime)) {
                buckets.set(bucketTime, {
                    time: bucketTime,
                    open: candle.open,
                    high: candle.high,
                    low: candle.low,
                    close: candle.close,
                    volume: data.volume[i].value,
                });
            } else {
                const bucket = buckets.get(bucketTime);
                bucket.high = Math.max(bucket.high, candle.high);
                bucket.low = Math.min(bucket.low, candle.low);
                bucket.close = candle.close;
                bucket.volume += data.volume[i].value;
            }
        }

        // Convert buckets to arrays
        for (const [time, bucket] of buckets.entries()) {
            aggregated.candlestick.push({
                time: bucket.time,
                open: bucket.open,
                high: bucket.high,
                low: bucket.low,
                close: bucket.close,
            });

            aggregated.volume.push({
                time: bucket.time,
                value: bucket.volume,
                color: bucket.close >= bucket.open
                    ? CONFIG.VOLUME_COLORS.upColor
                    : CONFIG.VOLUME_COLORS.downColor,
            });
        }

        return aggregated;
    }

    /**
     * Clear cache
     */
    clearCache() {
        this.cache.clear();
        Utils.notify('Cache cleared', 'info');
    }
}
