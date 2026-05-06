// ===== Main Application =====

const App = {
    state: {
        currentTicker: 'iwm',
        currentDate: null,
        currentData: null,
        aggregatedStrikes: null,
        nodes: null,
        filters: {
            dteRange: 'all',
            optionType: 'both',
            valueFormat: 'dollar',
            strikeMin: null,
            strikeMax: null
        }
    },

    async init() {
        console.log('Initializing Options Heatseeker...');

        // Set up event listeners
        this.setupEventListeners();

        // Load initial data
        await this.loadInitialData();

        // Initialize visualizations
        this.render();

        console.log('App initialized successfully');
    },

    setupEventListeners() {
        // Ticker selector
        document.getElementById('ticker-selector')?.addEventListener('change', (e) => {
            this.state.currentTicker = e.target.value;
            this.loadData();
        });

        // Date selector
        document.getElementById('date-selector')?.addEventListener('change', (e) => {
            this.state.currentDate = e.target.value.replace(/-/g, '');
            this.loadData();
        });

        // Refresh button
        document.getElementById('refresh-btn')?.addEventListener('click', () => {
            this.loadData();
        });

        // Theme toggle
        document.getElementById('theme-toggle')?.addEventListener('click', () => {
            document.body.classList.toggle('theme-dark');
            document.body.classList.toggle('theme-light');
        });

        // DTE filters
        document.querySelectorAll('.dte-filter').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.dte-filter').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.state.filters.dteRange = e.target.dataset.dte;
                this.applyFilters();
            });
        });

        // Option type filters
        document.querySelectorAll('input[name="option-type"]').forEach(radio => {
            radio.addEventListener('change', (e) => {
                this.state.filters.optionType = e.target.value;
                this.applyFilters();
            });
        });

        // Value format filters
        document.querySelectorAll('input[name="value-format"]').forEach(radio => {
            radio.addEventListener('change', (e) => {
                this.state.filters.valueFormat = e.target.value;
                this.render();
            });
        });

        // Strike range inputs
        document.getElementById('strike-min')?.addEventListener('change', (e) => {
            this.state.filters.strikeMin = parseFloat(e.target.value) || null;
            this.applyFilters();
        });

        document.getElementById('strike-max')?.addEventListener('change', (e) => {
            this.state.filters.strikeMax = parseFloat(e.target.value) || null;
            this.applyFilters();
        });

        document.getElementById('reset-range')?.addEventListener('click', () => {
            this.state.filters.strikeMin = null;
            this.state.filters.strikeMax = null;
            document.getElementById('strike-min').value = '';
            document.getElementById('strike-max').value = '';
            this.applyFilters();
        });

        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                const viewName = e.target.dataset.view;
                this.switchView(viewName);
            });
        });

        // Export buttons
        document.getElementById('export-png')?.addEventListener('click', () => {
            ExportManager.exportAsPNG();
        });

        document.getElementById('export-csv')?.addEventListener('click', () => {
            ExportManager.exportAsCSV(this.state.aggregatedStrikes, this.state.currentTicker, this.state.currentDate);
        });
    },

    async loadInitialData() {
        Utils.showLoading('Loading index...');

        try {
            // Load most recent date
            const mostRecentDate = await DataLoader.getMostRecentDate(this.state.currentTicker);

            if (!mostRecentDate) {
                throw new Error('No data available');
            }

            // Set date picker - mostRecentDate is already in YYYYMMDD format
            const formattedDate = Utils.formatDate(mostRecentDate, 'YYYY-MM-DD');
            const dateSelector = document.getElementById('date-selector');
            if (dateSelector) {
                dateSelector.value = formattedDate;
            }

            // Store date in YYYYMMDD format
            this.state.currentDate = mostRecentDate;

            // Load data
            await this.loadData();

        } catch (error) {
            Utils.hideLoading();
            Utils.showError(`Failed to load initial data: ${error.message}`);
        }
    },

    async loadData() {
        Utils.showLoading(`Loading ${this.state.currentTicker.toUpperCase()} options data...`);

        try {
            // Load options data
            const data = await DataLoader.loadOptionsData(
                this.state.currentTicker,
                this.state.currentDate
            );

            this.state.currentData = data;

            // Apply filters and aggregate
            this.applyFilters();

            Utils.hideLoading();

        } catch (error) {
            Utils.hideLoading();
            Utils.showError(`Failed to load data: ${error.message}`);
        }
    },

    applyFilters() {
        if (!this.state.currentData) return;

        // Filter options
        const filtered = DataLoader.filterOptions(
            this.state.currentData.options,
            this.state.filters
        );

        // Aggregate by strike
        this.state.aggregatedStrikes = DataLoader.aggregateByStrike(filtered);

        // Auto-set strike range if not manually set
        if (!this.state.filters.strikeMin && !this.state.filters.strikeMax) {
            const spot = this.state.currentData.spot_price;
            const range = spot * CONFIG.HEATMAP.STRIKE_RANGE_PERCENT;
            this.state.aggregatedStrikes = this.state.aggregatedStrikes.filter(s =>
                s.strike >= spot - range && s.strike <= spot + range
            );
        }

        // Detect nodes
        this.state.nodes = NodeAnalyzer.detectNodes(
            this.state.aggregatedStrikes,
            this.state.currentData.spot_price
        );

        // Render
        this.render();
    },

    render() {
        if (!this.state.currentData || !this.state.aggregatedStrikes) {
            console.warn('Cannot render: missing data');
            return;
        }

        try {
            // Calculate metrics
            const gex = GreeksCalculator.calculateGEX(
                this.state.currentData.options,
                this.state.currentData.spot_price
            );

            const vex = GreeksCalculator.calculateVEX(
                this.state.currentData.options,
                this.state.currentData.spot_price
            );

            const pcRatio = GreeksCalculator.calculatePutCallRatio(
                this.state.currentData.options
            );

            // Update metrics panel
            const gexEl = document.getElementById('total-gex');
            if (gexEl) {
                gexEl.textContent = Utils.formatCurrency(gex);
                gexEl.className = `metric-value ${gex >= 0 ? 'value-positive' : 'value-negative'}`;
            }

            const vexEl = document.getElementById('total-vex');
            if (vexEl) {
                vexEl.textContent = Utils.formatCurrency(vex);
                vexEl.className = `metric-value ${vex >= 0 ? 'value-positive' : 'value-negative'}`;
            }

            const pcEl = document.getElementById('pc-ratio');
            if (pcEl) pcEl.textContent = pcRatio.oi_ratio.toFixed(2);

            const spotEl = document.getElementById('spot-price');
            if (spotEl) spotEl.textContent = Utils.formatCurrency(this.state.currentData.spot_price, 2);

            // Update key nodes panel
            this.renderKeyNodes();

            // Render heatmap
            HeatmapRenderer.render(
                this.state.aggregatedStrikes,
                this.state.currentData.spot_price,
                this.state.nodes
            );

            // Render expiration breakdown
            this.renderExpirationBreakdown();
        } catch (error) {
            console.error('Error during render:', error);
            Utils.showError(`Rendering error: ${error.message}`);
        }
    },

    renderKeyNodes() {
        const container = document.getElementById('key-nodes');
        if (!container || !this.state.nodes) return;

        container.innerHTML = '';

        // King Node
        if (this.state.nodes.kingNode) {
            const kingEl = this.createNodeElement(this.state.nodes.kingNode);
            container.appendChild(kingEl);
        }

        // Gatekeepers
        this.state.nodes.gatekeepers.forEach(node => {
            const nodeEl = this.createNodeElement(node);
            container.appendChild(nodeEl);
        });

        // Midpoints
        this.state.nodes.midpoints.slice(0, 2).forEach(node => {
            const nodeEl = this.createNodeElement(node);
            container.appendChild(nodeEl);
        });
    },

    createNodeElement(node) {
        const div = document.createElement('div');
        div.className = `node-item ${node.type}`;

        div.innerHTML = `
            <div class="node-label">${node.type}</div>
            <div class="node-strike">$${node.strike.toFixed(2)}</div>
            <div class="node-value">${Utils.formatCurrency(node.gamma)}</div>
            <div class="node-value">${node.distance_percent > 0 ? '+' : ''}${node.distance_percent.toFixed(2)}%</div>
        `;

        return div;
    },

    renderExpirationBreakdown() {
        const container = document.getElementById('expiration-breakdown');
        if (!container || !this.state.currentData) return;

        const breakdown = DataLoader.getExpirationBreakdown(this.state.currentData.options);

        container.innerHTML = '';

        breakdown.slice(0, 10).forEach(exp => {
            const div = document.createElement('div');
            div.className = 'expiration-item';

            div.innerHTML = `
                <strong>${Utils.formatDate(exp.expiration, 'MMM DD')}</strong> (${exp.dte} DTE)<br>
                <small>OI: ${Utils.formatNumber(exp.total_oi)} | P/C: ${exp.pc_ratio.toFixed(2)}</small>
            `;

            container.appendChild(div);
        });
    },

    switchView(viewName) {
        // Update tabs
        document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
        document.querySelector(`.tab[data-view="${viewName}"]`)?.classList.add('active');

        // Update views
        document.querySelectorAll('.view-container').forEach(view => view.classList.remove('active'));
        document.getElementById(`${viewName}-view`)?.classList.add('active');
    }
};

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});
