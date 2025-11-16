// Main Application - Trading Chart Viewer

class App {
    constructor() {
        this.dataLoader = new DataLoader();
        this.chartManager = new ChartManager('chartContainer');
        this.tradeMarker = new TradeMarker();
        this.analytics = new Analytics(this.tradeMarker);

        this.currentTicker = 'IWM';
        this.currentDate = null;
        this.currentTimeframe = 1;

        this.initializeUI();
        this.attachEventListeners();
        this.loadInitialData();
    }

    /**
     * Initialize UI elements
     */
    initializeUI() {
        // Set up tabs
        this.setupTabs();

        // Populate ticker selector
        this.populateTickerSelector();
    }

    /**
     * Attach event listeners
     */
    attachEventListeners() {
        // Ticker selection
        document.getElementById('tickerSelect').addEventListener('change', (e) => {
            this.currentTicker = e.target.value;
            this.loadAvailableDates();
        });

        // Date selection
        document.getElementById('dateSelect').addEventListener('change', (e) => {
            this.currentDate = e.target.value;
            this.loadChartData();
        });

        // Timeframe selection
        document.getElementById('timeframeSelect').addEventListener('change', (e) => {
            this.currentTimeframe = parseInt(e.target.value);
            this.loadChartData();
        });

        // Mark entry button
        document.getElementById('markEntryBtn').addEventListener('click', () => {
            this.openTradeModal('entry');
        });

        // Mark exit button
        document.getElementById('markExitBtn').addEventListener('click', () => {
            this.openTradeModal('exit');
        });

        // Save trades button
        document.getElementById('saveDataBtn').addEventListener('click', () => {
            this.tradeMarker.saveTrades();
        });

        // Export button
        document.getElementById('exportBtn').addEventListener('click', () => {
            this.tradeMarker.exportToCSV();
        });

        // Chart click event
        window.addEventListener('chartClick', (e) => {
            console.log('Chart clicked:', e.detail);
        });

        // Modal events
        this.setupModalEvents();
    }

    /**
     * Setup tab switching
     */
    setupTabs() {
        const tabBtns = document.querySelectorAll('.tab-btn');
        const tabContents = document.querySelectorAll('.tab-content');

        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                // Remove active class from all
                tabBtns.forEach(b => b.classList.remove('active'));
                tabContents.forEach(c => c.classList.remove('active'));

                // Add active class to clicked tab
                btn.classList.add('active');

                const tabId = btn.dataset.tab;
                const tabContent = document.getElementById(`${tabId}Tab`);
                if (tabContent) {
                    tabContent.classList.add('active');

                    // Update analytics when switching to analytics tab
                    if (tabId === 'analytics') {
                        this.updateAnalytics();
                    }
                }
            });
        });
    }

    /**
     * Populate ticker selector
     */
    populateTickerSelector() {
        const select = document.getElementById('tickerSelect');
        select.innerHTML = CONFIG.TICKERS.map(ticker =>
            `<option value="${ticker}">${ticker}</option>`
        ).join('');
    }

    /**
     * Load initial data
     */
    async loadInitialData() {
        Utils.notify('Loading data...', 'info');
        await this.loadAvailableDates();
    }

    /**
     * Load available dates for current ticker
     */
    async loadAvailableDates() {
        const dates = await this.dataLoader.fetchAvailableMonths(this.currentTicker);

        if (dates.length === 0) {
            Utils.notify('No data available for this ticker', 'warning');
            return;
        }

        // Check if we have YYYYMMDD dates (GitHub Pages) or YYYYMM months (Local API)
        const firstItem = dates[0];
        const isIndividualDates = firstItem && firstItem.length === 8; // YYYYMMDD format

        let allDays = [];

        if (isIndividualDates) {
            // GitHub Pages mode - dates.json already has individual trading days
            // Use the last 60 days (about 3 months of trading days)
            allDays = dates.slice(-60);
        } else {
            // Local API mode - generate trading days from months
            const recentMonths = dates.slice(-3);
            for (const month of recentMonths) {
                const days = this.dataLoader.getTradingDaysInMonth(month);
                allDays.push(...days);
            }
        }

        if (allDays.length === 0) {
            Utils.notify('No trading days found', 'warning');
            return;
        }

        // Populate date selector (in reverse order - most recent first)
        const select = document.getElementById('dateSelect');
        select.innerHTML = allDays.reverse().map(date =>
            `<option value="${date}">${this.formatDateDisplay(date)}</option>`
        ).join('');

        // Select most recent date (now first in list after reverse)
        this.currentDate = allDays[0];
        select.value = this.currentDate;

        // Load chart data
        await this.loadChartData();
    }

    /**
     * Load chart data for current ticker and date
     */
    async loadChartData() {
        if (!this.currentTicker || !this.currentDate) {
            return;
        }

        const data = await this.dataLoader.fetchData(
            this.currentTicker,
            this.currentDate,
            this.currentTimeframe
        );

        if (data) {
            this.chartManager.loadData(data, this.currentTicker, this.currentDate);

            // Load and display trades for this date
            this.refreshTradesList();
        }
    }

    /**
     * Open trade modal
     */
    openTradeModal(action) {
        const modal = document.getElementById('tradeModal');
        const modalTitle = document.getElementById('modalTitle');
        const tradeAction = document.getElementById('tradeAction');
        const entryFields = document.getElementById('entryFields');
        const exitFields = document.getElementById('exitFields');

        // Set action
        tradeAction.value = action;

        if (action === 'entry') {
            modalTitle.textContent = 'Mark Trade Entry';
            entryFields.style.display = 'block';
            exitFields.style.display = 'none';

            // Get last click data
            const clickData = this.chartManager.getLastClickData();
            if (clickData) {
                document.getElementById('tradePrice').value = clickData.price;
                document.getElementById('tradeTime').value = clickData.time;
                document.getElementById('entryPrice').value = clickData.price.toFixed(2);
            }
        } else {
            modalTitle.textContent = 'Mark Trade Exit';
            entryFields.style.display = 'none';
            exitFields.style.display = 'block';

            // Populate active trades
            this.populateActiveTradesSelect();

            // Get last click data
            const clickData = this.chartManager.getLastClickData();
            if (clickData) {
                document.getElementById('exitPrice').value = clickData.price.toFixed(2);
                document.getElementById('tradePrice').value = clickData.price;
                document.getElementById('tradeTime').value = clickData.time;
            }
        }

        modal.classList.add('active');
    }

    /**
     * Close trade modal
     */
    closeTradeModal() {
        const modal = document.getElementById('tradeModal');
        modal.classList.remove('active');

        // Reset form
        document.getElementById('tradeForm').reset();
    }

    /**
     * Setup modal event listeners
     */
    setupModalEvents() {
        const modal = document.getElementById('tradeModal');
        const modalClose = document.getElementById('modalClose');
        const modalCancel = document.getElementById('modalCancel');
        const tradeForm = document.getElementById('tradeForm');

        modalClose.addEventListener('click', () => this.closeTradeModal());
        modalCancel.addEventListener('click', () => this.closeTradeModal());

        // Close on outside click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                this.closeTradeModal();
            }
        });

        // Handle form submission
        tradeForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleTradeFormSubmit();
        });
    }

    /**
     * Handle trade form submission
     */
    handleTradeFormSubmit() {
        const action = document.getElementById('tradeAction').value;

        if (action === 'entry') {
            this.submitTradeEntry();
        } else {
            this.submitTradeExit();
        }
    }

    /**
     * Submit trade entry
     */
    submitTradeEntry() {
        const optionType = document.querySelector('input[name="optionType"]:checked').value;
        const price = parseFloat(document.getElementById('tradePrice').value);
        const time = parseInt(document.getElementById('tradeTime').value);
        const notes = document.getElementById('tradeNotes').value;
        const tags = document.getElementById('tradeTags').value.split(',').map(t => t.trim()).filter(t => t);

        // Get TP/SL values
        const takeProfits = [];
        for (let i = 1; i <= 3; i++) {
            const tpPrice = document.getElementById(`tp${i}Price`).value;
            const tpSize = document.getElementById(`tp${i}Size`).value;

            if (tpPrice) {
                takeProfits.push({
                    price: parseFloat(tpPrice),
                    size: parseFloat(tpSize) / 100,
                });
            }
        }

        const stopLoss = document.getElementById('stopLoss').value
            ? { price: parseFloat(document.getElementById('stopLoss').value) }
            : null;

        // Add trade
        const trade = this.tradeMarker.addEntry({
            ticker: this.currentTicker,
            optionType: optionType,
            price: price,
            time: time,
            takeProfits: takeProfits,
            stopLoss: stopLoss,
            notes: notes,
            tags: tags,
        });

        if (trade) {
            this.refreshTradesList();
            this.closeTradeModal();
        }
    }

    /**
     * Submit trade exit
     */
    submitTradeExit() {
        const tradeId = document.getElementById('exitTrade').value;
        const price = parseFloat(document.getElementById('tradePrice').value);
        const time = parseInt(document.getElementById('tradeTime').value);
        const reason = document.getElementById('exitReason').value;

        if (!tradeId) {
            Utils.notify('Please select a trade to exit', 'warning');
            return;
        }

        const trade = this.tradeMarker.addExit(tradeId, {
            price: price,
            time: time,
            reason: reason,
        });

        if (trade) {
            this.refreshTradesList();
            this.closeTradeModal();
        }
    }

    /**
     * Populate active trades select
     */
    populateActiveTradesSelect() {
        const select = document.getElementById('exitTrade');
        const activeTrades = this.tradeMarker.getActiveTrades();

        select.innerHTML = '<option value="">Select a trade to exit...</option>' +
            activeTrades.map(trade =>
                `<option value="${trade.id}">${trade.ticker} ${trade.optionType} @ ${Utils.formatCurrency(trade.entryPrice)} - ${Utils.formatDateTime(trade.entryTime)}</option>`
            ).join('');
    }

    /**
     * Refresh trades list
     */
    refreshTradesList() {
        const tradesContainer = document.getElementById('tradesList');
        const tradeCount = document.getElementById('tradeCount');

        const trades = this.tradeMarker.getTradesForDate(this.currentTicker, this.currentDate);

        tradeCount.textContent = trades.length;

        if (trades.length === 0) {
            tradesContainer.innerHTML = `
                <div class="empty-state">
                    <p>No trades marked yet</p>
                    <small>Click "Mark Entry" to start</small>
                </div>
            `;
        } else {
            tradesContainer.innerHTML = trades.map(trade => this.createTradeCard(trade)).join('');
        }

        // Update chart markers
        this.chartManager.addMarkers(trades);
    }

    /**
     * Create trade card HTML
     */
    createTradeCard(trade) {
        const pnlText = trade.exitPrice
            ? `${Utils.formatCurrency(trade.pnl)} (${Utils.formatPercent(trade.pnlPercent)})`
            : 'Active';

        const pnlClass = trade.pnl > 0 ? 'positive' : trade.pnl < 0 ? 'negative' : '';

        return `
            <div class="trade-card">
                <div class="trade-card-header">
                    <span class="trade-type ${trade.optionType}">${trade.optionType}</span>
                    <small>${Utils.formatDateTime(trade.entryTime)}</small>
                </div>
                <div class="trade-card-body">
                    <div class="trade-detail">
                        <span class="label">Entry:</span>
                        <span class="value">${Utils.formatCurrency(trade.entryPrice)}</span>
                    </div>
                    ${trade.exitPrice ? `
                        <div class="trade-detail">
                            <span class="label">Exit:</span>
                            <span class="value">${Utils.formatCurrency(trade.exitPrice)}</span>
                        </div>
                    ` : ''}
                    ${trade.takeProfits.length > 0 ? `
                        <div class="trade-detail">
                            <span class="label">Targets:</span>
                            <span class="value">${trade.takeProfits.map((tp, i) => `TP${i+1}: ${Utils.formatCurrency(tp.price)}`).join(', ')}</span>
                        </div>
                    ` : ''}
                    ${trade.stopLoss ? `
                        <div class="trade-detail">
                            <span class="label">Stop Loss:</span>
                            <span class="value">${Utils.formatCurrency(trade.stopLoss.price)}</span>
                        </div>
                    ` : ''}
                </div>
                <div class="trade-pnl ${pnlClass}">
                    P&L: ${pnlText}
                </div>
            </div>
        `;
    }

    /**
     * Update analytics panel
     */
    updateAnalytics() {
        const stats = this.analytics.calculateStats();
        const insights = this.analytics.generateInsights();

        // Update metrics
        document.getElementById('totalTrades').textContent = stats.totalTrades;
        document.getElementById('winRate').textContent = `${stats.winRate.toFixed(1)}%`;
        document.getElementById('avgPnL').textContent = Utils.formatCurrency(stats.avgPnL);
        document.getElementById('callPutRatio').textContent = `${stats.callCount}:${stats.putCount}`;

        // Update insights
        const insightsContainer = document.getElementById('patternInsights');
        if (insights.length === 0) {
            insightsContainer.innerHTML = '<p class="insight-item">Mark trades to see pattern analysis</p>';
        } else {
            insightsContainer.innerHTML = insights.map(insight =>
                `<p class="insight-item">${insight}</p>`
            ).join('');
        }
    }

    /**
     * Format date for display
     */
    formatDateDisplay(dateStr) {
        // Format: YYYYMMDD -> Nov 14, 2025
        if (dateStr.length === 8) {
            const year = dateStr.substring(0, 4);
            const month = dateStr.substring(4, 6);
            const day = dateStr.substring(6, 8);

            const date = new Date(`${year}-${month}-${day}`);
            return date.toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric'
            });
        } else if (dateStr.length === 6) {
            // Format: YYYYMM -> Nov 2025
            const year = dateStr.substring(0, 4);
            const month = dateStr.substring(4, 6);

            const date = new Date(`${year}-${month}-01`);
            return date.toLocaleDateString('en-US', {
                month: 'short',
                year: 'numeric'
            });
        }
        return dateStr;
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new App();
});
