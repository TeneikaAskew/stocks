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
     * Fetch available dates for a ticker
     */
    async fetchAvailableDates(ticker) {
        if (this.availableDates.has(ticker)) {
            return this.availableDates.get(ticker);
        }

        try {
            const url = CONFIG.USE_LOCAL_API
                ? `${this.getApiUrl()}/dates/${ticker}`
                : `${this.getApiUrl()}/${ticker.toLowerCase()}/dates.json`;

            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            const dates = CONFIG.USE_LOCAL_API ? data.dates : data;

            this.availableDates.set(ticker, dates);
            return dates;
        } catch (error) {
            console.error('Error fetching available dates:', error);
            Utils.notify('Error loading available dates', 'error');
            return [];
        }
    }

    /**
     * Fetch OHLCV data for a specific ticker and date
     */
    async fetchData(ticker, date, timeframe = 1) {
        const cacheKey = `${ticker}_${date}_${timeframe}`;

        // Check cache first
        if (this.cache.has(cacheKey)) {
            return this.cache.get(cacheKey);
        }

        try {
            Utils.notify(`Loading ${ticker} data for ${date}...`, 'info');

            const url = CONFIG.USE_LOCAL_API
                ? `${this.getApiUrl()}/data/${ticker}/${date}?timeframe=${timeframe}`
                : `${this.getApiUrl()}/${ticker.toLowerCase()}/${date}_${timeframe}min.json`;

            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            // Transform data for TradingView Lightweight Charts
            const chartData = this.transformData(data);

            // Cache the data
            this.cache.set(cacheKey, chartData);

            Utils.notify(`Loaded ${chartData.candlestick.length} candles`, 'success');

            return chartData;
        } catch (error) {
            console.error('Error fetching data:', error);
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
