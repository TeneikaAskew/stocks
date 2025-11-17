// Trade Marker - Handles trade marking and storage

class TradeMarker {
    constructor() {
        this.trades = [];
        this.currentTrade = null;
        this.githubStorage = new GitHubStorage();
        this.loadTrades();
    }

    /**
     * Load trades from storage (GitHub or localStorage)
     */
    async loadTrades() {
        try {
            // Try loading from GitHub first if enabled
            if (this.githubStorage.isEnabled()) {
                console.log('[TradeMarker] Loading from GitHub...');
                const githubTrades = await this.githubStorage.loadTrades();

                if (githubTrades !== null) {
                    this.trades = githubTrades;
                    Utils.notify(`Loaded ${this.trades.length} trades from GitHub`, 'success');

                    // Sync to localStorage as backup
                    localStorage.setItem(CONFIG.STORAGE_KEYS.TRADES, JSON.stringify(this.trades));
                    return;
                }
            }

            // Fallback to localStorage
            console.log('[TradeMarker] Loading from localStorage...');
            const stored = localStorage.getItem(CONFIG.STORAGE_KEYS.TRADES);
            if (stored) {
                this.trades = JSON.parse(stored);
                Utils.notify(`Loaded ${this.trades.length} trades from local storage`, 'info');
            }
        } catch (error) {
            console.error('Error loading trades:', error);
            this.trades = [];
        }
    }

    /**
     * Save trades to storage (GitHub or localStorage)
     */
    async saveTrades() {
        try {
            // Always save to localStorage as backup
            localStorage.setItem(CONFIG.STORAGE_KEYS.TRADES, JSON.stringify(this.trades));

            // Try saving to GitHub if enabled
            if (this.githubStorage.isEnabled()) {
                console.log('[TradeMarker] Saving to GitHub...');
                const success = await this.githubStorage.saveTrades(this.trades);

                if (success) {
                    return true;
                }

                // If GitHub save failed, still notify about local save
                Utils.notify('Trades saved locally (GitHub save failed)', 'warning');
                return false;
            }

            // Local storage only
            Utils.notify('Trades saved locally', 'success');
            return true;
        } catch (error) {
            console.error('Error saving trades:', error);
            Utils.notify('Error saving trades', 'error');
            return false;
        }
    }

    /**
     * Add a new trade entry
     */
    addEntry(entryData) {
        const trade = {
            id: Utils.generateId(),
            ticker: entryData.ticker,
            optionType: entryData.optionType,
            entryTime: entryData.time,
            entryPrice: entryData.price,
            takeProfits: entryData.takeProfits || [],
            stopLoss: entryData.stopLoss || null,
            notes: entryData.notes || '',
            tags: entryData.tags || [],
            exitTime: null,
            exitPrice: null,
            exitReason: null,
            pnl: null,
            pnlPercent: null,
            status: 'active',
            createdAt: Date.now(),
        };

        this.trades.push(trade);
        this.saveTrades();

        Utils.notify(`${trade.optionType} trade marked at ${Utils.formatCurrency(trade.entryPrice)}`, 'success');

        return trade;
    }

    /**
     * Add exit to an existing trade
     */
    addExit(tradeId, exitData) {
        const trade = this.trades.find(t => t.id === tradeId);

        if (!trade) {
            Utils.notify('Trade not found', 'error');
            return null;
        }

        if (trade.exitPrice) {
            Utils.notify('Trade already has an exit', 'warning');
            return null;
        }

        // Calculate P&L
        const pnl = Utils.calculatePnL(trade.entryPrice, exitData.price, trade.optionType);
        const pnlPercent = Utils.calculatePnLPercent(trade.entryPrice, exitData.price, trade.optionType);

        trade.exitTime = exitData.time;
        trade.exitPrice = exitData.price;
        trade.exitReason = exitData.reason;
        trade.pnl = pnl;
        trade.pnlPercent = pnlPercent;
        trade.status = pnl > 0 ? 'win' : pnl < 0 ? 'loss' : 'breakeven';

        this.saveTrades();

        Utils.notify(
            `Trade closed: ${Utils.formatCurrency(pnl)} (${Utils.formatPercent(pnlPercent)})`,
            pnl > 0 ? 'success' : 'error'
        );

        return trade;
    }

    /**
     * Update a trade
     */
    updateTrade(tradeId, updates) {
        const index = this.trades.findIndex(t => t.id === tradeId);

        if (index === -1) {
            Utils.notify('Trade not found', 'error');
            return null;
        }

        this.trades[index] = {
            ...this.trades[index],
            ...updates,
        };

        this.saveTrades();

        return this.trades[index];
    }

    /**
     * Delete a trade
     */
    deleteTrade(tradeId) {
        const index = this.trades.findIndex(t => t.id === tradeId);

        if (index === -1) {
            Utils.notify('Trade not found', 'error');
            return false;
        }

        this.trades.splice(index, 1);
        this.saveTrades();

        Utils.notify('Trade deleted', 'info');

        return true;
    }

    /**
     * Get all trades
     */
    getAllTrades() {
        return this.trades;
    }

    /**
     * Get trades for a specific ticker and date
     */
    getTradesForDate(ticker, date) {
        return this.trades.filter(trade => {
            const tradeDate = Utils.formatDate(new Date(trade.entryTime * 1000));
            const targetDate = typeof date === 'string' ? date : Utils.formatDate(date);
            return trade.ticker === ticker && tradeDate === targetDate;
        });
    }

    /**
     * Get active trades (no exit yet)
     */
    getActiveTrades() {
        return this.trades.filter(t => t.status === 'active');
    }

    /**
     * Get closed trades
     */
    getClosedTrades() {
        return this.trades.filter(t => t.status !== 'active');
    }

    /**
     * Export trades to CSV
     */
    exportToCSV() {
        if (this.trades.length === 0) {
            Utils.notify('No trades to export', 'warning');
            return;
        }

        // CSV headers
        const headers = [
            'ID',
            'Ticker',
            'Option Type',
            'Entry Time',
            'Entry Price',
            'Exit Time',
            'Exit Price',
            'Exit Reason',
            'P&L',
            'P&L %',
            'Status',
            'TP1 Price',
            'TP1 Size',
            'TP2 Price',
            'TP2 Size',
            'TP3 Price',
            'TP3 Size',
            'Stop Loss',
            'Notes',
            'Tags',
        ];

        // CSV rows
        const rows = this.trades.map(trade => {
            return [
                trade.id,
                trade.ticker,
                trade.optionType,
                Utils.formatDateTime(trade.entryTime),
                trade.entryPrice,
                trade.exitTime ? Utils.formatDateTime(trade.exitTime) : '',
                trade.exitPrice || '',
                trade.exitReason || '',
                trade.pnl || '',
                trade.pnlPercent || '',
                trade.status,
                trade.takeProfits[0]?.price || '',
                trade.takeProfits[0]?.size || '',
                trade.takeProfits[1]?.price || '',
                trade.takeProfits[1]?.size || '',
                trade.takeProfits[2]?.price || '',
                trade.takeProfits[2]?.size || '',
                trade.stopLoss?.price || '',
                trade.notes || '',
                trade.tags.join(';') || '',
            ];
        });

        // Convert to CSV string
        const csvContent = [
            headers.join(','),
            ...rows.map(row => row.map(cell => `"${cell}"`).join(','))
        ].join('\n');

        // Download CSV
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);

        link.setAttribute('href', url);
        link.setAttribute('download', `trades_export_${Date.now()}.csv`);
        link.style.visibility = 'hidden';

        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        Utils.notify('Trades exported to CSV', 'success');
    }

    /**
     * Export trades to JSON
     */
    exportToJSON() {
        if (this.trades.length === 0) {
            Utils.notify('No trades to export', 'warning');
            return;
        }

        const jsonContent = JSON.stringify(this.trades, null, 2);

        // Download JSON
        const blob = new Blob([jsonContent], { type: 'application/json;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);

        link.setAttribute('href', url);
        link.setAttribute('download', `trades_export_${Date.now()}.json`);
        link.style.visibility = 'hidden';

        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        Utils.notify('Trades exported to JSON', 'success');
    }

    /**
     * Clear all trades
     */
    clearAllTrades() {
        if (confirm('Are you sure you want to delete all trades? This cannot be undone.')) {
            this.trades = [];
            this.saveTrades();
            Utils.notify('All trades cleared', 'info');
            return true;
        }
        return false;
    }
}
