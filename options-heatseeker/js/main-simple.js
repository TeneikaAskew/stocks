// ===== Simple Main Application =====

const App = {
    state: {
        currentTicker: 'spy',
        currentMetric: 'gex',
        dataByDate: {},
        spotPrice: null,
        nodes: null
    },

    async init() {
        console.log('Initializing Options Heatseeker (Simple View)...');

        // Set up event listeners
        this.setupEventListeners();

        // Load data
        await this.loadMultipleDates();

        console.log('App initialized');
    },

    setupEventListeners() {
        // Ticker selector
        document.getElementById('ticker-selector')?.addEventListener('change', (e) => {
            this.state.currentTicker = e.target.value;
            this.loadMultipleDates();
        });

        // Metric toggles
        document.querySelectorAll('.metric-toggle').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.metric-toggle').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.state.currentMetric = e.target.dataset.metric;
                TableRenderer.setMetric(this.state.currentMetric);
                this.render();
            });
        });
    },

    async loadMultipleDates() {
        Utils.showLoading('Loading options data...');

        try {
            // Get available dates
            const dates = await DataLoader.getAvailableDates(this.state.currentTicker);

            if (!dates || dates.length === 0) {
                throw new Error('No data available');
            }

            // Load last 5 dates
            const recentDates = dates.slice(-5);
            this.state.dataByDate = {};

            for (const date of recentDates) {
                try {
                    const data = await DataLoader.loadOptionsData(this.state.currentTicker, date);
                    const aggregated = DataLoader.aggregateByStrike(data.options);
                    this.state.dataByDate[date] = aggregated;

                    // Use most recent spot price
                    if (!this.state.spotPrice) {
                        this.state.spotPrice = data.spot_price;
                    }
                } catch (error) {
                    console.warn(`Failed to load ${date}:`, error.message);
                }
            }

            // Detect nodes from most recent date
            const mostRecentDate = recentDates[recentDates.length - 1];
            if (this.state.dataByDate[mostRecentDate]) {
                this.state.nodes = NodeAnalyzer.detectNodes(
                    this.state.dataByDate[mostRecentDate],
                    this.state.spotPrice
                );
            }

            // Update price display
            this.updatePriceDisplay();

            // Render table
            this.render();

            Utils.hideLoading();

        } catch (error) {
            Utils.hideLoading();
            Utils.showError(`Failed to load data: ${error.message}`);
        }
    },

    updatePriceDisplay() {
        const priceEl = document.getElementById('current-price');
        if (priceEl && this.state.spotPrice) {
            priceEl.textContent = `$${this.state.spotPrice.toFixed(2)}`;
        }
    },

    render() {
        if (Object.keys(this.state.dataByDate).length === 0) {
            console.warn('No data to render');
            return;
        }

        TableRenderer.render(
            this.state.dataByDate,
            this.state.spotPrice,
            this.state.nodes
        );
    }
};

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});
