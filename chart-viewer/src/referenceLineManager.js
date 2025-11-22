/**
 * Reference Line Manager
 * Manages historical period OHLC reference lines for support/resistance analysis
 */

class ReferenceLineManager {
    constructor(dataLoader) {
        this.dataLoader = dataLoader;
        this.cache = new Map(); // Cache calculated period OHLC
    }

    /**
     * Get previous period OHLC values
     * @param {string} ticker - Symbol (IWM, SPY, QQQ)
     * @param {string} currentDate - Current viewing date in YYYYMMDD format
     * @param {string} period - 'day' | 'week' | 'month' | 'year'
     * @returns {Promise<{open: number, high: number, low: number, close: number, startDate: string, endDate: string}>}
     */
    async getPreviousPeriodOHLC(ticker, currentDate, period) {
        const cacheKey = `${ticker}_${period}_${currentDate}`;

        // Check cache first
        if (this.cache.has(cacheKey)) {
            return this.cache.get(cacheKey);
        }

        // Get all available dates
        const availableDates = await this.dataLoader.fetchAvailableMonths(ticker);

        // Find dates for the previous period
        const periodDates = this.findPreviousPeriodDates(currentDate, period, availableDates);

        if (periodDates.length === 0) {
            console.warn(`No dates found for previous ${period} from ${currentDate}`);
            return null;
        }

        // Load data for all dates in the period
        const periodData = await this.loadPeriodData(ticker, periodDates);

        if (!periodData || periodData.length === 0) {
            console.warn(`No data loaded for previous ${period}`);
            return null;
        }

        // Calculate OHLC from all candles in the period
        const ohlc = this.aggregateCandles(periodData);

        // Add date range for reference
        ohlc.startDate = periodDates[0];
        ohlc.endDate = periodDates[periodDates.length - 1];
        ohlc.period = period;

        // Cache the result
        this.cache.set(cacheKey, ohlc);

        return ohlc;
    }

    /**
     * Find dates for the previous period
     * @param {string} currentDate - Current date in YYYYMMDD format
     * @param {string} period - 'day' | 'week' | 'month' | 'year'
     * @param {Array<string>} availableDates - Sorted array of available dates
     * @returns {Array<string>} Array of dates in the previous period
     */
    findPreviousPeriodDates(currentDate, period, availableDates) {
        const currentIndex = availableDates.indexOf(currentDate);

        if (currentIndex === -1) {
            console.warn(`Current date ${currentDate} not found in available dates`);
            return [];
        }

        switch (period) {
            case 'day':
                // Just the previous trading day
                return currentIndex > 0 ? [availableDates[currentIndex - 1]] : [];

            case 'week':
                // Previous week: 5 trading days ending the day before current
                // If current is Nov 14, get Nov 7-13 (5 days)
                const weekEnd = currentIndex - 1;
                const weekStart = Math.max(0, weekEnd - 4);
                return availableDates.slice(weekStart, weekEnd + 1);

            case 'month':
                // Previous month: ~20-22 trading days ending the day before current
                const monthEnd = currentIndex - 1;
                const monthStart = Math.max(0, monthEnd - 21);
                return availableDates.slice(monthStart, monthEnd + 1);

            case 'year':
                // Previous year: ~252 trading days ending the day before current
                const yearEnd = currentIndex - 1;
                const yearStart = Math.max(0, yearEnd - 251);
                return availableDates.slice(yearStart, yearEnd + 1);

            default:
                console.warn(`Unknown period: ${period}`);
                return [];
        }
    }

    /**
     * Load data for multiple dates
     * @param {string} ticker - Symbol
     * @param {Array<string>} dates - Array of dates in YYYYMMDD format
     * @returns {Promise<Array>} Array of all candles from all dates
     */
    async loadPeriodData(ticker, dates) {
        const allCandles = [];

        for (const date of dates) {
            try {
                const data = await this.dataLoader.fetchData(ticker, date, '1');

                if (data && data.candlestick && data.candlestick.length > 0) {
                    allCandles.push(...data.candlestick);
                }
            } catch (error) {
                console.warn(`Failed to load data for ${ticker} ${date}:`, error);
                // Continue with other dates even if one fails
            }
        }

        return allCandles;
    }

    /**
     * Aggregate candles to calculate OHLC
     * @param {Array} candles - Array of candle objects {time, open, high, low, close}
     * @returns {{open: number, high: number, low: number, close: number}}
     */
    aggregateCandles(candles) {
        if (!candles || candles.length === 0) {
            return null;
        }

        // Sort by time to ensure correct order
        const sortedCandles = [...candles].sort((a, b) => a.time - b.time);

        // Open = first candle's open
        const open = sortedCandles[0].open;

        // Close = last candle's close
        const close = sortedCandles[sortedCandles.length - 1].close;

        // High = maximum of all highs
        const high = Math.max(...sortedCandles.map(c => c.high));

        // Low = minimum of all lows
        const low = Math.min(...sortedCandles.map(c => c.low));

        return { open, high, low, close };
    }

    /**
     * Clear cache
     */
    clearCache() {
        this.cache.clear();
    }

    /**
     * Format period name for display
     * @param {string} period - 'day' | 'week' | 'month' | 'year'
     * @returns {string} Formatted period name
     */
    formatPeriodName(period) {
        const names = {
            'day': 'Previous Day',
            'week': 'Previous Week',
            'month': 'Previous Month',
            'year': 'Previous Year'
        };
        return names[period] || period;
    }
}
