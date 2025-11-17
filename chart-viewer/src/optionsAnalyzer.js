// Options Analyzer - Matches trades with real options contracts and calculates actual P&L

class OptionsAnalyzer {
    constructor() {
        this.contractsCache = new Map();
    }

    /**
     * Load options contracts for a specific ticker and date
     */
    async loadContracts(ticker, date) {
        const cacheKey = `${ticker}_${date}`;

        if (this.contractsCache.has(cacheKey)) {
            return this.contractsCache.get(cacheKey);
        }

        try {
            // In GitHub Pages mode, we need to fetch from a JSON file
            // For now, we'll use the API endpoint if available
            const url = CONFIG.USE_LOCAL_API
                ? `${CONFIG.LOCAL_API_URL}/options/${ticker}/${date}`
                : `${CONFIG.GITHUB_DATA_URL}/${ticker.toLowerCase()}/options/${date}_options.json`;

            console.log('[OptionsAnalyzer] Fetching contracts from:', url);

            const response = await fetch(url);
            if (!response.ok) {
                console.warn('[OptionsAnalyzer] No options data available for', date);
                return [];
            }

            const contracts = await response.json();
            this.contractsCache.set(cacheKey, contracts);

            console.log('[OptionsAnalyzer] Loaded', contracts.length, 'contracts');
            return contracts;
        } catch (error) {
            console.error('[OptionsAnalyzer] Error loading contracts:', error);
            return [];
        }
    }

    /**
     * Find the closest matching contract for a trade
     *
     * @param {Object} trade - Trade object with entryTime, entryPrice, optionType, ticker
     * @param {Array} contracts - Array of options contracts
     * @returns {Object|null} - Matching contract or null
     */
    findMatchingContract(trade, contracts, timestamp) {
        if (!contracts || contracts.length === 0) {
            return null;
        }

        // Filter contracts by option type (call/put)
        const typeFiltered = contracts.filter(c =>
            c.type.toLowerCase() === trade.optionType.toLowerCase()
        );

        if (typeFiltered.length === 0) {
            return null;
        }

        // Convert timestamp to date (YYYY-MM-DD format)
        const tradeDate = new Date(timestamp * 1000);
        const tradeDateStr = tradeDate.toISOString().split('T')[0];

        // Filter contracts for 0DTE (same-day expiration)
        // Must match: snapshot date = trade date AND expiration date = trade date
        const dateFiltered = typeFiltered.filter(c =>
            c.date === tradeDateStr && c.expiration === tradeDateStr
        );

        if (dateFiltered.length === 0) {
            console.warn('[OptionsAnalyzer] No 0DTE contracts found for date:', tradeDateStr);
            console.warn('[OptionsAnalyzer] Looking for expiration === date ===', tradeDateStr);
            return null;
        }

        console.log('[OptionsAnalyzer] Found', dateFiltered.length, '0DTE contracts for', tradeDateStr);

        // Find the closest strike based on underlying price (trade.entryPrice is stock price)
        // For calls: ATM or slightly OTM is typical (strike >= stock price)
        // For puts: ATM or slightly OTM is typical (strike <= stock price)
        const underlyingPrice = trade.entryPrice;

        let bestContract = null;
        let minDelta = Infinity;

        for (const contract of dateFiltered) {
            const strikeDiff = Math.abs(contract.strike - underlyingPrice);

            // Also consider delta - options traders often look for specific delta ranges
            // ATM options typically have delta around 0.50
            // Slightly OTM calls: delta 0.30-0.50
            // Slightly OTM puts: delta -0.30 to -0.50
            const deltaTarget = trade.optionType.toLowerCase() === 'call' ? 0.40 : -0.40;
            const deltaDiff = Math.abs(contract.delta - deltaTarget);

            // Weighted scoring: strike proximity (70%) + delta proximity (30%)
            const score = (strikeDiff / underlyingPrice) * 0.7 + deltaDiff * 0.3;

            if (score < minDelta) {
                minDelta = score;
                bestContract = contract;
            }
        }

        if (bestContract) {
            console.log('[OptionsAnalyzer] Matched contract:', bestContract.contractID,
                'Strike:', bestContract.strike, 'Delta:', bestContract.delta);
        }

        return bestContract;
    }

    /**
     * Find an ITM/ATM contract for comparison
     * @param {Object} trade - Trade object
     * @param {Array} contracts - Filtered contracts (same type and date)
     * @returns {Object|null} - ITM/ATM contract
     */
    findITMATMContract(trade, contracts) {
        const underlyingPrice = trade.entryPrice;
        const isCall = trade.optionType.toLowerCase() === 'call';

        // For calls: ITM = strike < stock price, ATM = strike ≈ stock price
        // For puts: ITM = strike > stock price, ATM = strike ≈ stock price

        // Find contract closest to ATM (strike nearest to stock price)
        let bestContract = null;
        let minDiff = Infinity;

        for (const contract of contracts) {
            const strikeDiff = Math.abs(contract.strike - underlyingPrice);

            // Prefer slightly ITM contracts (better than deep OTM)
            // For calls: strike just below stock price
            // For puts: strike just above stock price
            let score = strikeDiff;

            if (isCall && contract.strike <= underlyingPrice) {
                // Call ITM/ATM - prefer strikes at or below stock price
                score = strikeDiff * 0.5; // Give preference to ITM
            } else if (!isCall && contract.strike >= underlyingPrice) {
                // Put ITM/ATM - prefer strikes at or above stock price
                score = strikeDiff * 0.5;
            }

            if (score < minDiff) {
                minDiff = score;
                bestContract = contract;
            }
        }

        return bestContract;
    }

    /**
     * Determine if a contract is ITM, ATM, or OTM
     * @param {Object} contract - Options contract
     * @param {number} underlyingPrice - Stock price
     * @param {string} optionType - 'call' or 'put'
     * @returns {string} - 'ITM', 'ATM', or 'OTM'
     */
    getMoneyness(contract, underlyingPrice, optionType) {
        const strike = contract.strike;
        const diff = Math.abs(strike - underlyingPrice);
        const isCall = optionType.toLowerCase() === 'call';

        // Consider ATM if within $0.50 of stock price
        if (diff <= 0.5) {
            return 'ATM';
        }

        if (isCall) {
            return strike < underlyingPrice ? 'ITM' : 'OTM';
        } else {
            return strike > underlyingPrice ? 'ITM' : 'OTM';
        }
    }

    /**
     * Calculate actual P&L using real options contract prices
     *
     * @param {Object} trade - Trade object
     * @returns {Object} - Enhanced trade with actual contract data and P&L
     */
    async calculateActualPnL(trade) {
        try {
            // Convert timestamps to dates
            const entryDate = new Date(trade.entryTime * 1000).toISOString().split('T')[0].replace(/-/g, '');

            // Load contracts for the entry date
            const contracts = await this.loadContracts(trade.ticker, entryDate);

            if (!contracts || contracts.length === 0) {
                console.warn('[OptionsAnalyzer] No contracts available for', trade.ticker, entryDate);
                return {
                    ...trade,
                    optionsAnalysis: {
                        status: 'no_data',
                        message: 'No options data available for this date'
                    }
                };
            }

            // Filter contracts by type and date for reuse
            const typeFiltered = contracts.filter(c =>
                c.type.toLowerCase() === trade.optionType.toLowerCase()
            );
            const tradeDate = new Date(trade.entryTime * 1000);
            const tradeDateStr = tradeDate.toISOString().split('T')[0];
            const dateFiltered = typeFiltered.filter(c =>
                c.date === tradeDateStr && c.expiration === tradeDateStr
            );

            // Find matching contract at entry (OTM contract based on delta target)
            const entryContract = this.findMatchingContract(trade, contracts, trade.entryTime);

            if (!entryContract) {
                return {
                    ...trade,
                    optionsAnalysis: {
                        status: 'no_match',
                        message: 'Could not find matching contract'
                    }
                };
            }

            // Also find ITM/ATM contract for comparison
            const itmAtmContract = this.findITMATMContract(trade, dateFiltered);

            // Determine moneyness of matched contract
            const moneyness = this.getMoneyness(entryContract, trade.entryPrice, trade.optionType);

            // Calculate entry price (use mark price as it's the mid-point)
            const entryOptionPrice = entryContract.mark || (entryContract.bid + entryContract.ask) / 2;
            const itmAtmOptionPrice = itmAtmContract
                ? (itmAtmContract.mark || (itmAtmContract.bid + itmAtmContract.ask) / 2)
                : null;

            // If trade has an exit, calculate exit P&L
            let exitOptionPrice = null;
            let actualPnL = null;
            let actualPnLPercent = null;

            if (trade.exitTime) {
                // For simplicity, we'll use the same contract but could load new data
                // In a real scenario, you'd load contracts for the exit time
                const exitContract = this.findMatchingContract(trade, contracts, trade.exitTime);

                if (exitContract) {
                    exitOptionPrice = exitContract.mark || (exitContract.bid + exitContract.ask) / 2;

                    // P&L calculation for options
                    // Calls: profit when price goes up
                    // Puts: profit when price goes down
                    actualPnL = exitOptionPrice - entryOptionPrice;
                    actualPnLPercent = (actualPnL / entryOptionPrice) * 100;
                }
            }

            // Calculate theoretical P&L for take profit levels
            const takeProfitAnalysis = (trade.takeProfits || []).map((tp, index) => {
                if (!tp.price) return null;

                // Find contract at TP price level
                const tpContract = this.findMatchingContract(trade, contracts, trade.entryTime);
                if (!tpContract) return null;

                // Estimate option price at TP level using delta
                // This is a simplified calculation - real pricing would need Black-Scholes
                const underlyingMove = tp.price - trade.entryPrice;
                const optionPriceChange = underlyingMove * Math.abs(entryContract.delta);
                const estimatedOptionPrice = entryOptionPrice + optionPriceChange;

                const tpPnL = estimatedOptionPrice - entryOptionPrice;
                const tpPnLPercent = (tpPnL / entryOptionPrice) * 100;

                return {
                    level: index + 1,
                    targetPrice: tp.price,
                    size: tp.size,
                    estimatedOptionPrice: estimatedOptionPrice,
                    estimatedPnL: tpPnL,
                    estimatedPnLPercent: tpPnLPercent
                };
            }).filter(tp => tp !== null);

            // Calculate stop loss analysis
            let stopLossAnalysis = null;
            if (trade.stopLoss && trade.stopLoss.price) {
                const underlyingMove = trade.stopLoss.price - trade.entryPrice;
                const optionPriceChange = underlyingMove * Math.abs(entryContract.delta);
                const estimatedOptionPrice = entryOptionPrice + optionPriceChange;

                const slPnL = estimatedOptionPrice - entryOptionPrice;
                const slPnLPercent = (slPnL / entryOptionPrice) * 100;

                stopLossAnalysis = {
                    targetPrice: trade.stopLoss.price,
                    estimatedOptionPrice: estimatedOptionPrice,
                    estimatedPnL: slPnL,
                    estimatedPnLPercent: slPnLPercent
                };
            }

            return {
                ...trade,
                optionsAnalysis: {
                    status: 'analyzed',
                    moneyness: moneyness, // ITM, ATM, or OTM
                    entryContract: {
                        contractID: entryContract.contractID,
                        strike: entryContract.strike,
                        expiration: entryContract.expiration,
                        delta: entryContract.delta,
                        gamma: entryContract.gamma,
                        theta: entryContract.theta,
                        vega: entryContract.vega,
                        impliedVolatility: entryContract.implied_volatility
                    },
                    entryOptionPrice: entryOptionPrice,
                    exitOptionPrice: exitOptionPrice,
                    actualPnL: actualPnL,
                    actualPnLPercent: actualPnLPercent,
                    // ITM/ATM contract for comparison
                    itmAtmContract: itmAtmContract ? {
                        contractID: itmAtmContract.contractID,
                        strike: itmAtmContract.strike,
                        delta: itmAtmContract.delta,
                        moneyness: this.getMoneyness(itmAtmContract, trade.entryPrice, trade.optionType)
                    } : null,
                    itmAtmOptionPrice: itmAtmOptionPrice,
                    takeProfitAnalysis: takeProfitAnalysis,
                    stopLossAnalysis: stopLossAnalysis,
                    // Original P&L was based on stock price, now we have option price P&L
                    originalPnL: trade.pnl,
                    originalPnLPercent: trade.pnlPercent
                }
            };

        } catch (error) {
            console.error('[OptionsAnalyzer] Error calculating actual P&L:', error);
            return {
                ...trade,
                optionsAnalysis: {
                    status: 'error',
                    message: error.message
                }
            };
        }
    }

    /**
     * Analyze all trades and add options contract data
     *
     * @param {Array} trades - Array of trades
     * @returns {Array} - Enhanced trades with options analysis
     */
    async analyzeAllTrades(trades) {
        const analyzedTrades = [];

        for (const trade of trades) {
            const analyzed = await this.calculateActualPnL(trade);
            analyzedTrades.push(analyzed);
        }

        return analyzedTrades;
    }

    /**
     * Get summary statistics for analyzed trades
     */
    getAnalysisSummary(analyzedTrades) {
        const withAnalysis = analyzedTrades.filter(t =>
            t.optionsAnalysis && t.optionsAnalysis.status === 'analyzed'
        );

        if (withAnalysis.length === 0) {
            return {
                totalTrades: analyzedTrades.length,
                analyzedTrades: 0,
                message: 'No trades could be analyzed (missing options data)'
            };
        }

        const closedTrades = withAnalysis.filter(t => t.optionsAnalysis.actualPnL !== null);

        const totalPnL = closedTrades.reduce((sum, t) => sum + t.optionsAnalysis.actualPnL, 0);
        const avgPnL = closedTrades.length > 0 ? totalPnL / closedTrades.length : 0;

        const winners = closedTrades.filter(t => t.optionsAnalysis.actualPnL > 0);
        const losers = closedTrades.filter(t => t.optionsAnalysis.actualPnL < 0);

        const winRate = closedTrades.length > 0
            ? (winners.length / closedTrades.length) * 100
            : 0;

        return {
            totalTrades: analyzedTrades.length,
            analyzedTrades: withAnalysis.length,
            closedTrades: closedTrades.length,
            totalPnL: totalPnL,
            avgPnL: avgPnL,
            winners: winners.length,
            losers: losers.length,
            winRate: winRate,
            avgWin: winners.length > 0
                ? winners.reduce((sum, t) => sum + t.optionsAnalysis.actualPnL, 0) / winners.length
                : 0,
            avgLoss: losers.length > 0
                ? losers.reduce((sum, t) => sum + t.optionsAnalysis.actualPnL, 0) / losers.length
                : 0
        };
    }
}
