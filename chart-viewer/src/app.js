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

        // Interactive drawing mode
        this.drawingMode = null; // 'entry', 'tp', 'sl', null
        this.drawingStep = 0; // Current step in drawing sequence
        this.tempTradeData = {}; // Temporary storage for trade being drawn

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
            this.startDrawingMode('entry');
        });

        // Save trades button
        document.getElementById('saveDataBtn').addEventListener('click', () => {
            this.tradeMarker.saveTrades();
        });

        // Export button
        document.getElementById('exportBtn').addEventListener('click', () => {
            this.tradeMarker.exportToCSV();
        });

        // Refresh button
        document.getElementById('refreshBtn').addEventListener('click', () => {
            // Clear cache and hard reload
            this.dataLoader.clearCache();
            window.location.reload(true);
        });

        // Chart click event
        window.addEventListener('chartClick', (e) => {
            console.log('Chart clicked:', e.detail);
            this.handleChartClickInDrawingMode(e.detail);
        });

        // Modal events
        this.setupModalEvents();

        // ESC key to cancel or skip drawing steps
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.drawingMode) {
                if (this.drawingStep === 0) {
                    // Cancel entirely
                    this.cancelDrawingMode();
                    Utils.notify('Drawing mode cancelled', 'info');
                } else if (this.drawingStep >= 1 && this.drawingStep <= 3) {
                    // Skip to stop loss
                    this.drawingStep = 4;
                    const btn = document.getElementById('markEntryBtn');
                    btn.textContent = '📍 Click chart for Stop Loss';
                    Utils.notify('Skipped to Stop Loss. Click to mark SL (or ESC to finish)', 'info');
                } else if (this.drawingStep === 4) {
                    // Skip SL and complete
                    this.completeDrawingMode();
                }
            }
        });
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
        console.log('[App] loadInitialData called');
        console.log('[App] Current ticker:', this.currentTicker);
        console.log('[App] Config TICKERS:', CONFIG.TICKERS);
        Utils.notify('Loading data...', 'info');
        await this.loadAvailableDates();
    }

    /**
     * Load available dates for current ticker
     */
    async loadAvailableDates() {
        console.log('[App] loadAvailableDates called');
        const dates = await this.dataLoader.fetchAvailableMonths(this.currentTicker);

        console.log('[App] Received dates:', dates.length);
        if (dates.length === 0) {
            Utils.notify('No data available for this ticker', 'warning');
            return;
        }

        // Check if we have YYYYMMDD dates (GitHub Pages) or YYYYMM months (Local API)
        const firstItem = dates[0];
        console.log('[App] First item:', firstItem, 'length:', firstItem?.length);
        const isIndividualDates = firstItem && firstItem.length === 8; // YYYYMMDD format
        console.log('[App] Is individual dates:', isIndividualDates);

        let allDays = [];

        if (isIndividualDates) {
            // GitHub Pages mode - dates.json already has individual trading days
            // Use the last 60 days (about 3 months of trading days)
            allDays = dates.slice(-60);
            console.log('[App] GitHub Pages mode - using last 60 days');
        } else {
            // Local API mode - generate trading days from months
            const recentMonths = dates.slice(-3);
            console.log('[App] Local API mode - generating days from months:', recentMonths);
            for (const month of recentMonths) {
                const days = this.dataLoader.getTradingDaysInMonth(month);
                allDays.push(...days);
            }
        }

        console.log('[App] All days count:', allDays.length);
        console.log('[App] First 5 days:', allDays.slice(0, 5));

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
        console.log('[App] Selected date:', this.currentDate);

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
     * Open trade modal for entry
     */
    openTradeModal() {
        const modal = document.getElementById('tradeModal');
        const modalTitle = document.getElementById('modalTitle');
        const tradeAction = document.getElementById('tradeAction');
        const entryFields = document.getElementById('entryFields');

        // Set action to entry
        tradeAction.value = 'entry';
        modalTitle.textContent = 'Mark Trade Entry';
        entryFields.style.display = 'block';

        // Get last click data
        const clickData = this.chartManager.getLastClickData();
        if (clickData) {
            document.getElementById('tradePrice').value = clickData.price;
            document.getElementById('tradeTime').value = clickData.time;
            document.getElementById('entryPrice').value = clickData.price.toFixed(2);
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
     * Handle trade form submission (entry only)
     */
    handleTradeFormSubmit() {
        this.submitTradeEntry();
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
     * Refresh trades list
     */
    async refreshTradesList() {
        const tradesContainer = document.getElementById('tradesList');
        const tradeCount = document.getElementById('tradeCount');

        let trades = this.tradeMarker.getTradesForDate(this.currentTicker, this.currentDate);

        tradeCount.textContent = trades.length;

        if (trades.length === 0) {
            tradesContainer.innerHTML = `
                <div class="empty-state">
                    <p>No trades marked yet</p>
                    <small>Click "Mark Entry" to start</small>
                </div>
            `;
        } else {
            // Analyze trades with options contracts
            const analyzedTrades = await Promise.all(
                trades.map(async (trade) => {
                    // Skip if already analyzed
                    if (trade.optionsAnalysis) {
                        return trade;
                    }
                    // Analyze and return
                    try {
                        return await this.analytics.optionsAnalyzer.calculateActualPnL(trade);
                    } catch (error) {
                        console.error('[App] Error analyzing trade:', error);
                        return trade; // Return original trade if analysis fails
                    }
                })
            );

            tradesContainer.innerHTML = analyzedTrades.map(trade => this.createTradeCard(trade)).join('');
        }

        // Update chart markers
        this.chartManager.addMarkers(trades);
    }

    /**
     * Create trade card HTML
     */
    createTradeCard(trade) {
        // Format take profits each on a new line
        const takeProfitsHtml = trade.takeProfits.length > 0
            ? `<div class="trade-detail">
                    <span class="label">Targets:</span>
                    <span class="value targets-list">${trade.takeProfits.map((tp, i) => `TP${i+1}: ${Utils.formatCurrency(tp.price)}`).join('<br>')}</span>
                </div>`
            : '';

        // Options contract info (if available)
        const optionsHtml = trade.optionsAnalysis && trade.optionsAnalysis.status === 'analyzed'
            ? `<div class="trade-detail options-contract">
                    <span class="label">Contract:</span>
                    <span class="value contract-info">
                        <strong>${trade.optionsAnalysis.entryContract.contractID}</strong><br>
                        Strike: ${Utils.formatCurrency(trade.optionsAnalysis.entryContract.strike)} |
                        Δ: ${trade.optionsAnalysis.entryContract.delta.toFixed(3)}<br>
                        Entry: ${Utils.formatCurrency(trade.optionsAnalysis.entryOptionPrice)}
                        ${trade.optionsAnalysis.exitOptionPrice
                            ? ` → ${Utils.formatCurrency(trade.optionsAnalysis.exitOptionPrice)}<br>
                               P&L: ${Utils.formatCurrency(trade.optionsAnalysis.actualPnL)}
                               (${trade.optionsAnalysis.actualPnLPercent.toFixed(1)}%)`
                            : ''}
                    </span>
                </div>`
            : '';

        return `
            <div class="trade-card" data-trade-id="${trade.id}">
                <div class="trade-card-header">
                    <span class="trade-type ${trade.optionType}">${trade.optionType}</span>
                    <button class="btn-delete" onclick="app.handleDeleteTrade('${trade.id}')" title="Delete trade">
                        ✕
                    </button>
                </div>
                <div class="trade-card-body">
                    <div class="trade-detail">
                        <small>${Utils.formatDateTime(trade.entryTime)}</small>
                    </div>
                    <div class="trade-detail">
                        <span class="label">Stock Entry:</span>
                        <span class="value">${Utils.formatCurrency(trade.entryPrice)}</span>
                    </div>
                    ${optionsHtml}
                    ${takeProfitsHtml}
                    ${trade.stopLoss ? `
                        <div class="trade-detail">
                            <span class="label">Stop Loss:</span>
                            <span class="value">${Utils.formatCurrency(trade.stopLoss.price)}</span>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }

    /**
     * Handle trade deletion
     */
    handleDeleteTrade(tradeId) {
        const success = this.tradeMarker.deleteTrade(tradeId);
        if (success) {
            this.refreshTradesList();
        }
    }

    /**
     * Update analytics panel
     */
    updateAnalytics() {
        const stats = this.analytics.calculateStats();
        const insights = this.analytics.generateInsights();

        // Update metrics
        document.getElementById('totalTrades').textContent = `${stats.totalTrades} (${stats.closedTrades} closed)`;
        document.getElementById('winRate').textContent = `${stats.winRate.toFixed(1)}%`;
        document.getElementById('avgPnL').textContent = Utils.formatCurrency(stats.avgPnL);
        document.getElementById('callPutRatio').textContent = `${stats.callCount}:${stats.putCount}`;
        document.getElementById('avgMovement').textContent = `${stats.avgMovement.toFixed(2)} pts`;
        document.getElementById('medianMovement').textContent = `${stats.medianMovement.toFixed(2)} pts`;

        // Update insights
        const insightsContainer = document.getElementById('patternInsights');
        if (insights.length === 0) {
            if (stats.closedTrades === 0 && stats.totalTrades > 0) {
                insightsContainer.innerHTML = '<p class="insight-item">Mark exits on your trades to see analytics. You have ' + stats.totalTrades + ' active trade(s).</p>';
            } else {
                insightsContainer.innerHTML = '<p class="insight-item">Mark trades to see pattern analysis</p>';
            }
        } else {
            insightsContainer.innerHTML = insights.map(insight =>
                `<p class="insight-item">${insight}</p>`
            ).join('');
        }
    }

    /**
     * Start interactive drawing mode
     */
    startDrawingMode(mode) {
        this.drawingMode = mode;
        this.drawingStep = 0;
        this.tempTradeData = {
            ticker: this.currentTicker,
            takeProfits: [],
        };

        // Update UI to show drawing mode is active
        const btn = document.getElementById('markEntryBtn');
        btn.classList.add('active-drawing');
        btn.textContent = '📍 Click chart for Entry';

        Utils.notify('Click on the chart to mark entry price', 'info');
    }

    /**
     * Cancel drawing mode
     */
    cancelDrawingMode() {
        this.drawingMode = null;
        this.drawingStep = 0;
        this.tempTradeData = {};

        // Reset UI
        const btn = document.getElementById('markEntryBtn');
        btn.classList.remove('active-drawing');
        btn.textContent = '📍 Mark Entry';

        // Clear temporary lines from chart
        this.chartManager.clearTempLines();
    }

    /**
     * Handle chart clicks when in drawing mode
     */
    handleChartClickInDrawingMode(clickData) {
        if (!this.drawingMode) {
            return; // Not in drawing mode
        }

        const { time, price } = clickData;
        console.log('[Drawing Mode] Chart clicked at step', this.drawingStep, '- Price:', price, 'Time:', time);

        switch (this.drawingStep) {
            case 0: // Entry price
                console.log('[Drawing Mode] Marking entry at price:', price);
                this.tempTradeData.entryPrice = price;
                this.tempTradeData.entryTime = time;

                // Ask for option type
                this.promptOptionType();
                break;

            case 1: // TP1
            case 2: // TP2
            case 3: // TP3
                const tpIndex = this.drawingStep - 1;
                this.tempTradeData.takeProfits.push({
                    price: price,
                    size: tpIndex === 0 ? 0.5 : tpIndex === 1 ? 0.3 : 0.2, // Default sizes
                });

                // Draw temporary TP line
                this.chartManager.addTempPriceLine(price, '#22c55e', `TP${tpIndex + 1}`);

                if (this.drawingStep === 3) {
                    // After TP3, ask for stop loss
                    const btn = document.getElementById('markEntryBtn');
                    btn.textContent = '📍 Click chart for Stop Loss';
                    Utils.notify('Click to mark Stop Loss (or press ESC to skip)', 'info');
                } else {
                    // Ask for next TP
                    const btn = document.getElementById('markEntryBtn');
                    btn.textContent = `📍 Click chart for TP${this.drawingStep}`;
                    Utils.notify(`Click to mark Take Profit ${this.drawingStep} (or press ESC to skip to SL)`, 'info');
                }

                this.drawingStep++;
                break;

            case 4: // Stop Loss
                this.tempTradeData.stopLoss = { price: price };

                // Draw temporary SL line
                this.chartManager.addTempPriceLine(price, '#ef4444', 'SL');

                // Complete the trade entry
                this.completeDrawingMode();
                break;
        }
    }

    /**
     * Prompt for option type (CALL or PUT)
     */
    promptOptionType() {
        console.log('[Drawing Mode] Showing option type modal...');
        console.log('[Drawing Mode] Entry price:', this.tempTradeData.entryPrice);

        // Show the option type modal
        const modal = document.getElementById('optionTypeModal');
        modal.style.display = 'flex';

        // Setup button handlers
        const handleSelection = (optionType) => {
            console.log('[Drawing Mode] User selected:', optionType);
            this.tempTradeData.optionType = optionType;

            // Hide modal
            modal.style.display = 'none';

            // Draw entry line
            const color = optionType === 'CALL' ? '#22c55e' : '#ef4444';
            this.chartManager.addTempPriceLine(this.tempTradeData.entryPrice, color, 'Entry');

            // Move to TP step
            this.drawingStep = 1;
            const btn = document.getElementById('markEntryBtn');
            btn.textContent = '📍 Click chart for TP1';
            Utils.notify(`${optionType} trade - Click to mark Take Profit 1 (or press ESC to skip)`, 'info');

            // Remove event listeners
            document.getElementById('selectCallBtn').removeEventListener('click', callHandler);
            document.getElementById('selectPutBtn').removeEventListener('click', putHandler);
        };

        const callHandler = () => handleSelection('CALL');
        const putHandler = () => handleSelection('PUT');

        document.getElementById('selectCallBtn').addEventListener('click', callHandler);
        document.getElementById('selectPutBtn').addEventListener('click', putHandler);
    }

    /**
     * Complete drawing mode and create the trade
     */
    completeDrawingMode() {
        // Add the trade
        const trade = this.tradeMarker.addEntry({
            ticker: this.tempTradeData.ticker,
            optionType: this.tempTradeData.optionType,
            price: this.tempTradeData.entryPrice,
            time: this.tempTradeData.entryTime,
            takeProfits: this.tempTradeData.takeProfits,
            stopLoss: this.tempTradeData.stopLoss,
            notes: '',
            tags: [],
        });

        if (trade) {
            Utils.notify('Trade entry marked successfully!', 'success');
            this.refreshTradesList();
        }

        // Exit drawing mode
        this.cancelDrawingMode();
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
    console.log('='.repeat(60));
    console.log('Trading Chart Viewer - Initializing');
    console.log('='.repeat(60));
    console.log('Config:', {
        USE_LOCAL_API: CONFIG.USE_LOCAL_API,
        TICKERS: CONFIG.TICKERS,
        GITHUB_DATA_URL: CONFIG.GITHUB_DATA_URL,
    });
    window.app = new App();
});
