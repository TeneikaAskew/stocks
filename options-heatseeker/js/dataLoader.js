// ===== Data Loader =====

const DataLoader = {
    // Cache for loaded data
    cache: new Map(),
    cacheTimestamps: new Map(),

    /**
     * Load index file with available dates
     */
    async loadIndex() {
        try {
            const response = await fetch('data/index.json');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const index = await response.json();
            return index;
        } catch (error) {
            console.error('Error loading index:', error);
            return null;
        }
    },

    /**
     * Load options data for a specific ticker and date
     */
    async loadOptionsData(ticker, dateStr) {
        const cacheKey = `${ticker}_${dateStr}`;

        // Check cache first
        if (CONFIG.CACHE.ENABLED && this.cache.has(cacheKey)) {
            const timestamp = this.cacheTimestamps.get(cacheKey);
            const age = Date.now() - timestamp;

            if (age < CONFIG.CACHE.TTL) {
                console.log(`Cache hit: ${cacheKey}`);
                return this.cache.get(cacheKey);
            } else {
                // Cache expired
                this.cache.delete(cacheKey);
                this.cacheTimestamps.delete(cacheKey);
            }
        }

        // Load from server
        try {
            const url = `data/${ticker}/${ticker}_options_${dateStr}.json`;
            console.log(`Loading: ${url}`);

            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

            const data = await response.json();

            // Parse and enhance data
            const processedData = this.processOptionsData(data);

            // Cache the data
            if (CONFIG.CACHE.ENABLED) {
                this.cache.set(cacheKey, processedData);
                this.cacheTimestamps.set(cacheKey, Date.now());

                // Enforce cache size limit
                if (this.cache.size > CONFIG.CACHE.MAX_SIZE) {
                    const oldestKey = this.cache.keys().next().value;
                    this.cache.delete(oldestKey);
                    this.cacheTimestamps.delete(oldestKey);
                }
            }

            return processedData;

        } catch (error) {
            console.error(`Error loading options data for ${ticker} ${dateStr}:`, error);
            throw error;
        }
    },

    /**
     * Process raw options data
     */
    processOptionsData(rawData) {
        const { ticker, date, snapshot_timestamp, options } = rawData;

        // Parse and enhance each option
        const processedOptions = options.map(option => {
            // Calculate days to expiration
            const dte = Utils.calculateDTE(option.expiration, snapshot_timestamp);

            // Calculate moneyness (strike / spot)
            const spot = this.estimateSpotPrice(options);
            const moneyness = option.strike / spot;

            // Calculate notional exposure
            const notional = option.open_interest * CONFIG.GREEKS.SPOT_MULTIPLIER;

            return {
                ...option,
                dte,
                moneyness,
                notional,
                gamma_notional: option.gamma * notional,
                vanna_notional: option.vega * notional  // Simplified vanna calc
            };
        });

        return {
            ticker: ticker.toUpperCase(),
            date,
            snapshot_timestamp,
            spot_price: this.estimateSpotPrice(options),
            options: processedOptions
        };
    },

    /**
     * Estimate spot price from ATM options
     */
    estimateSpotPrice(options) {
        // Find the strike closest to delta 0.5 for calls (approximate ATM)
        const atmCalls = options.filter(o =>
            o.type === 'call' &&
            o.delta > 0.4 &&
            o.delta < 0.6 &&
            o.open_interest > 0
        );

        if (atmCalls.length > 0) {
            // Use strike of ATM option with highest OI
            const atmCall = atmCalls.reduce((prev, curr) =>
                curr.open_interest > prev.open_interest ? curr : prev
            );
            return atmCall.strike;
        }

        // Fallback: use median strike
        const strikes = options.map(o => o.strike);
        strikes.sort((a, b) => a - b);
        return strikes[Math.floor(strikes.length / 2)];
    },

    /**
     * Get available dates for a ticker
     */
    async getAvailableDates(ticker) {
        const index = await this.loadIndex();
        if (!index || !index[ticker]) {
            return [];
        }
        return index[ticker].dates;
    },

    /**
     * Get most recent date for a ticker
     */
    async getMostRecentDate(ticker) {
        const dates = await this.getAvailableDates(ticker);
        if (dates.length === 0) return null;
        return dates[dates.length - 1];
    },

    /**
     * Filter options by criteria
     */
    filterOptions(options, filters = {}) {
        let filtered = [...options];

        // Filter by option type
        if (filters.optionType && filters.optionType !== 'both') {
            filtered = filtered.filter(o =>
                filters.optionType === 'calls' ? o.type === 'call' : o.type === 'put'
            );
        }

        // Filter by DTE range
        if (filters.dteRange) {
            const [minDTE, maxDTE] = CONFIG.FILTERS.DTE_RANGES[filters.dteRange] || [0, Infinity];
            filtered = filtered.filter(o => o.dte >= minDTE && o.dte < maxDTE);
        }

        // Filter by strike range
        if (filters.strikeMin !== undefined) {
            filtered = filtered.filter(o => o.strike >= filters.strikeMin);
        }
        if (filters.strikeMax !== undefined) {
            filtered = filtered.filter(o => o.strike <= filters.strikeMax);
        }

        // Filter by minimum open interest
        if (filters.minOpenInterest) {
            filtered = filtered.filter(o => o.open_interest >= filters.minOpenInterest);
        }

        return filtered;
    },

    /**
     * Aggregate options by strike
     */
    aggregateByStrike(options) {
        const grouped = Utils.groupBy(options, 'strike');
        const aggregated = [];

        for (const [strike, strikeOptions] of Object.entries(grouped)) {
            const calls = strikeOptions.filter(o => o.type === 'call');
            const puts = strikeOptions.filter(o => o.type === 'put');

            // Sum up Greeks across all expirations for this strike
            const callGamma = Utils.sum(calls, 'gamma_notional');
            const putGamma = Utils.sum(puts, 'gamma_notional');
            const netGamma = callGamma - putGamma;  // Dealer perspective: opposite of customer

            const callOI = Utils.sum(calls, 'open_interest');
            const putOI = Utils.sum(puts, 'open_interest');

            const callDelta = Utils.sum(calls, 'delta') * Utils.sum(calls, 'open_interest');
            const putDelta = Utils.sum(puts, 'delta') * Utils.sum(puts, 'open_interest');
            const netDelta = callDelta + putDelta;

            const callVega = Utils.sum(calls, 'vega') * Utils.sum(calls, 'open_interest');
            const putVega = Utils.sum(puts, 'vega') * Utils.sum(puts, 'open_interest');
            const netVega = callVega + putVega;

            aggregated.push({
                strike: parseFloat(strike),
                call_oi: callOI,
                put_oi: putOI,
                total_oi: callOI + putOI,
                net_gamma: netGamma,
                net_delta: netDelta,
                net_vega: netVega,
                call_gamma: callGamma,
                put_gamma: putGamma,
                expirations: strikeOptions.map(o => o.expiration).filter((v, i, a) => a.indexOf(v) === i)
            });
        }

        // Sort by strike
        aggregated.sort((a, b) => a.strike - b.strike);

        return aggregated;
    },

    /**
     * Get expiration breakdown
     */
    getExpirationBreakdown(options) {
        const grouped = Utils.groupBy(options, 'expiration');
        const breakdown = [];

        for (const [expiration, expirationOptions] of Object.entries(grouped)) {
            const dte = expirationOptions[0].dte;
            const totalOI = Utils.sum(expirationOptions, 'open_interest');
            const totalVolume = Utils.sum(expirationOptions, 'volume');

            const calls = expirationOptions.filter(o => o.type === 'call');
            const puts = expirationOptions.filter(o => o.type === 'put');

            breakdown.push({
                expiration,
                dte,
                total_oi: totalOI,
                total_volume: totalVolume,
                call_oi: Utils.sum(calls, 'open_interest'),
                put_oi: Utils.sum(puts, 'open_interest'),
                pc_ratio: Utils.sum(puts, 'open_interest') / Utils.sum(calls, 'open_interest')
            });
        }

        // Sort by expiration date
        breakdown.sort((a, b) => new Date(a.expiration) - new Date(b.expiration));

        return breakdown;
    },

    /**
     * Clear cache
     */
    clearCache() {
        this.cache.clear();
        this.cacheTimestamps.clear();
        console.log('Cache cleared');
    }
};

// Freeze DataLoader to prevent modifications
Object.freeze(DataLoader);
