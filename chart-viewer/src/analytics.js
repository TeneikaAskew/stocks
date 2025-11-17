// Analytics - Calculate trading performance metrics and patterns

class Analytics {
    constructor(tradeMarker) {
        this.tradeMarker = tradeMarker;
    }

    /**
     * Expand trades with TPs into individual exit points
     * This treats each TP level as a separate exit for analytics
     */
    expandTradesToExits(trades) {
        const expandedTrades = [];
        for (const trade of trades) {
            if (trade.takeProfits && trade.takeProfits.length > 0) {
                // Create a separate "trade" for each TP level
                trade.takeProfits.forEach((tp, index) => {
                    if (tp.price) {
                        const pnl = Utils.calculatePnL(trade.entryPrice, tp.price, trade.optionType);
                        const pnlPercent = Utils.calculatePnLPercent(trade.entryPrice, tp.price, trade.optionType);
                        expandedTrades.push({
                            ...trade,
                            exitPrice: tp.price,
                            exitReason: `TP${index + 1}`,
                            pnl: pnl,
                            pnlPercent: pnlPercent,
                            status: pnl > 0 ? 'win' : pnl < 0 ? 'loss' : 'breakeven',
                            size: tp.size || (1 / trade.takeProfits.length), // Default to equal size if not specified
                        });
                    }
                });
            } else if (trade.exitPrice) {
                // Regular closed trade with explicit exit
                expandedTrades.push(trade);
            }
        }
        return expandedTrades;
    }

    /**
     * Calculate overall statistics
     */
    calculateStats() {
        const allTrades = this.tradeMarker.getAllTrades();
        const closedTrades = this.expandTradesToExits(allTrades);

        if (closedTrades.length === 0) {
            return {
                totalTrades: allTrades.length,
                activeTrades: this.tradeMarker.getActiveTrades().length,
                closedTrades: 0,
                winCount: 0,
                lossCount: 0,
                winRate: 0,
                totalPnL: 0,
                avgPnL: 0,
                maxWin: 0,
                maxLoss: 0,
                avgWin: 0,
                avgLoss: 0,
                profitFactor: 0,
                callCount: 0,
                putCount: 0,
                avgMovement: 0,
                medianMovement: 0,
                maxMovement: 0,
                minMovement: 0,
            };
        }

        const wins = closedTrades.filter(t => t.status === 'win');
        const losses = closedTrades.filter(t => t.status === 'loss');

        const totalPnL = closedTrades.reduce((sum, t) => sum + (t.pnl || 0), 0);
        const totalWinPnL = wins.reduce((sum, t) => sum + (t.pnl || 0), 0);
        const totalLossPnL = Math.abs(losses.reduce((sum, t) => sum + (t.pnl || 0), 0));

        const calls = allTrades.filter(t => t.optionType === 'CALL');
        const puts = allTrades.filter(t => t.optionType === 'PUT');

        // Calculate movement statistics (point movement from entry to exit)
        const movements = closedTrades.map(t => Math.abs(t.exitPrice - t.entryPrice));
        const avgMovement = movements.reduce((sum, m) => sum + m, 0) / movements.length;

        // Calculate median movement
        const sortedMovements = [...movements].sort((a, b) => a - b);
        const medianMovement = sortedMovements.length % 2 === 0
            ? (sortedMovements[sortedMovements.length / 2 - 1] + sortedMovements[sortedMovements.length / 2]) / 2
            : sortedMovements[Math.floor(sortedMovements.length / 2)];

        return {
            totalTrades: allTrades.length,
            activeTrades: this.tradeMarker.getActiveTrades().length,
            closedTrades: closedTrades.length,
            winCount: wins.length,
            lossCount: losses.length,
            winRate: (wins.length / closedTrades.length) * 100,
            totalPnL: totalPnL,
            avgPnL: totalPnL / closedTrades.length,
            maxWin: wins.length > 0 ? Math.max(...wins.map(t => t.pnl)) : 0,
            maxLoss: losses.length > 0 ? Math.min(...losses.map(t => t.pnl)) : 0,
            avgWin: wins.length > 0 ? totalWinPnL / wins.length : 0,
            avgLoss: losses.length > 0 ? totalLossPnL / losses.length : 0,
            profitFactor: totalLossPnL > 0 ? totalWinPnL / totalLossPnL : 0,
            callCount: calls.length,
            putCount: puts.length,
            avgMovement: avgMovement,
            medianMovement: medianMovement,
            maxMovement: Math.max(...movements),
            minMovement: Math.min(...movements),
        };
    }

    /**
     * Calculate performance by option type
     */
    analyzeByOptionType() {
        const allTrades = this.tradeMarker.getAllTrades();
        const trades = this.expandTradesToExits(allTrades);

        const calls = trades.filter(t => t.optionType === 'CALL');
        const puts = trades.filter(t => t.optionType === 'PUT');

        return {
            CALL: this.calculateGroupStats(calls),
            PUT: this.calculateGroupStats(puts),
        };
    }

    /**
     * Calculate performance by ticker
     */
    analyzeByTicker() {
        const allTrades = this.tradeMarker.getAllTrades();
        const trades = this.expandTradesToExits(allTrades);
        const tickers = [...new Set(trades.map(t => t.ticker))];

        const results = {};

        for (const ticker of tickers) {
            const tickerTrades = trades.filter(t => t.ticker === ticker);
            results[ticker] = this.calculateGroupStats(tickerTrades);
        }

        return results;
    }

    /**
     * Calculate stats for a group of trades
     */
    calculateGroupStats(trades) {
        if (trades.length === 0) {
            return {
                count: 0,
                wins: 0,
                losses: 0,
                winRate: 0,
                totalPnL: 0,
                avgPnL: 0,
            };
        }

        const wins = trades.filter(t => t.status === 'win');
        const losses = trades.filter(t => t.status === 'loss');
        const totalPnL = trades.reduce((sum, t) => sum + (t.pnl || 0), 0);

        return {
            count: trades.length,
            wins: wins.length,
            losses: losses.length,
            winRate: (wins.length / trades.length) * 100,
            totalPnL: totalPnL,
            avgPnL: totalPnL / trades.length,
        };
    }

    /**
     * Find patterns in winning trades
     */
    findWinningPatterns() {
        const allTrades = this.tradeMarker.getAllTrades();
        const expandedTrades = this.expandTradesToExits(allTrades);
        const wins = expandedTrades.filter(t => t.status === 'win');

        if (wins.length === 0) {
            return [];
        }

        const patterns = [];

        // Analyze by tags
        const tagCounts = {};
        wins.forEach(trade => {
            trade.tags.forEach(tag => {
                if (!tagCounts[tag]) {
                    tagCounts[tag] = { count: 0, totalPnL: 0 };
                }
                tagCounts[tag].count++;
                tagCounts[tag].totalPnL += trade.pnl || 0;
            });
        });

        for (const [tag, data] of Object.entries(tagCounts)) {
            if (data.count >= 3) { // Minimum 3 occurrences to be a pattern
                patterns.push({
                    type: 'tag',
                    value: tag,
                    count: data.count,
                    avgPnL: data.totalPnL / data.count,
                    confidence: (data.count / wins.length) * 100,
                });
            }
        }

        // Sort by confidence
        patterns.sort((a, b) => b.confidence - a.confidence);

        return patterns.slice(0, 5); // Top 5 patterns
    }

    /**
     * Analyze time-based patterns
     */
    analyzeTimePatterns() {
        const allTrades = this.tradeMarker.getAllTrades();
        const trades = this.expandTradesToExits(allTrades);

        if (trades.length === 0) {
            return null;
        }

        const hourlyStats = {};

        trades.forEach(trade => {
            const hour = new Date(trade.entryTime * 1000).getHours();

            if (!hourlyStats[hour]) {
                hourlyStats[hour] = {
                    count: 0,
                    wins: 0,
                    totalPnL: 0,
                };
            }

            hourlyStats[hour].count++;
            if (trade.status === 'win') {
                hourlyStats[hour].wins++;
            }
            hourlyStats[hour].totalPnL += trade.pnl || 0;
        });

        // Find best hours
        const bestHours = Object.entries(hourlyStats)
            .map(([hour, stats]) => ({
                hour: parseInt(hour),
                ...stats,
                winRate: (stats.wins / stats.count) * 100,
                avgPnL: stats.totalPnL / stats.count,
            }))
            .filter(h => h.count >= 2) // Minimum 2 trades
            .sort((a, b) => b.winRate - a.winRate)
            .slice(0, 3);

        return bestHours;
    }

    /**
     * Generate insights
     */
    generateInsights() {
        const stats = this.calculateStats();
        const patterns = this.findWinningPatterns();
        const timePatterns = this.analyzeTimePatterns();
        const byType = this.analyzeByOptionType();

        const insights = [];

        // Win rate insight
        if (stats.closedTrades > 0) {
            if (stats.winRate >= 60) {
                insights.push(`Strong win rate of ${stats.winRate.toFixed(1)}% across ${stats.closedTrades} trades`);
            } else if (stats.winRate >= 50) {
                insights.push(`Moderate win rate of ${stats.winRate.toFixed(1)}%`);
            } else {
                insights.push(`Win rate of ${stats.winRate.toFixed(1)}% - review losing patterns`);
            }
        }

        // Profit factor insight
        if (stats.profitFactor > 2) {
            insights.push(`Excellent profit factor of ${stats.profitFactor.toFixed(2)}`);
        } else if (stats.profitFactor > 1.5) {
            insights.push(`Good profit factor of ${stats.profitFactor.toFixed(2)}`);
        }

        // Call vs Put performance
        if (byType.CALL.count > 0 && byType.PUT.count > 0) {
            if (byType.CALL.winRate > byType.PUT.winRate + 15) {
                insights.push(`CALL trades perform ${(byType.CALL.winRate - byType.PUT.winRate).toFixed(1)}% better than PUTs`);
            } else if (byType.PUT.winRate > byType.CALL.winRate + 15) {
                insights.push(`PUT trades perform ${(byType.PUT.winRate - byType.CALL.winRate).toFixed(1)}% better than CALLs`);
            }
        }

        // Pattern insights
        if (patterns.length > 0) {
            const topPattern = patterns[0];
            insights.push(`Top setup: "${topPattern.value}" with ${topPattern.count} wins (${topPattern.confidence.toFixed(0)}% of wins)`);
        }

        // Time-based insights
        if (timePatterns && timePatterns.length > 0) {
            const bestHour = timePatterns[0];
            insights.push(`Best trading hour: ${bestHour.hour}:00 with ${bestHour.winRate.toFixed(0)}% win rate`);
        }

        return insights;
    }
}
