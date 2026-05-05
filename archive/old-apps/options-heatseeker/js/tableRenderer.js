// ===== Table Renderer =====

const TableRenderer = {
    currentMetric: 'gex', // 'gex' or 'vex'
    optionFilter: 'net', // 'calls', 'puts', or 'net'
    selectedStrike: null,

    render(dataByDate, spotPrice, nodes) {
        const table = document.getElementById('heatmap-table');
        const thead = table.querySelector('thead tr');
        const tbody = document.getElementById('heatmap-body');

        if (!table || !thead || !tbody) {
            console.error('Table elements not found');
            return;
        }

        // Get dates and sort them
        const dates = Object.keys(dataByDate).sort();

        // Clear existing content
        thead.innerHTML = '<th class="strike-header">Strike</th>';
        tbody.innerHTML = '';

        // Add date headers
        dates.forEach(date => {
            const th = document.createElement('th');
            th.textContent = this.formatDateHeader(date);
            thead.appendChild(th);
        });

        // Get all unique strikes across all dates
        const allStrikes = new Set();
        dates.forEach(date => {
            dataByDate[date].forEach(row => allStrikes.add(row.strike));
        });

        // Sort strikes descending
        const strikes = Array.from(allStrikes).sort((a, b) => b - a);

        // Build data matrix
        const matrix = {};
        strikes.forEach(strike => {
            matrix[strike] = {};
            dates.forEach(date => {
                const row = dataByDate[date].find(r => r.strike === strike);
                matrix[strike][date] = row ? this.getMetricValue(row) : null;
            });
        });

        // Find max absolute value for color scaling
        const allValues = strikes.flatMap(strike =>
            dates.map(date => matrix[strike][date]).filter(v => v !== null)
        );
        const maxAbs = Math.max(...allValues.map(Math.abs));

        // Render rows
        strikes.forEach(strike => {
            const tr = document.createElement('tr');
            tr.dataset.strike = strike;

            // Add click handler for strike selection
            tr.addEventListener('click', () => this.selectStrike(strike));

            // Strike cell
            const strikeCell = document.createElement('td');
            strikeCell.className = 'strike-cell';

            // Add current price indicator
            if (spotPrice && Math.abs(strike - spotPrice) < 2.5) {
                const indicator = document.createElement('span');
                indicator.className = 'price-indicator';
                indicator.textContent = '▶';
                strikeCell.appendChild(indicator);
            }

            // Check if this is a key node
            const nodeIndicator = this.getNodeIndicator(strike, nodes);
            if (nodeIndicator) {
                const indicator = document.createElement('span');
                indicator.className = 'strike-indicator';
                indicator.textContent = nodeIndicator;
                strikeCell.appendChild(indicator);
            }

            // Strike value
            const strikeText = document.createElement('span');
            strikeText.textContent = strike.toFixed(1);
            strikeCell.appendChild(strikeText);

            // Check if selected
            if (this.selectedStrike && Math.abs(this.selectedStrike - strike) < 0.1) {
                tr.classList.add('selected-strike');
                const star = document.createElement('span');
                star.className = 'selection-star';
                star.textContent = ' ★';
                strikeCell.appendChild(star);
            }

            tr.appendChild(strikeCell);

            // Value cells
            dates.forEach(date => {
                const td = document.createElement('td');
                const value = matrix[strike][date];

                if (value !== null) {
                    td.textContent = Utils.formatCurrency(value);
                    td.className = this.getCellClass(value, maxAbs, strike, nodes);
                } else {
                    td.textContent = '$0.0K';
                    td.style.opacity = '0.3';
                }

                tr.appendChild(td);
            });

            tbody.appendChild(tr);
        });
    },

    getMetricValue(row) {
        const baseValue = this.currentMetric === 'gex' ? row.net_gamma : row.net_vega;

        // Apply option filter
        if (this.optionFilter === 'calls') {
            return this.currentMetric === 'gex' ? row.call_gamma : row.call_vega || 0;
        } else if (this.optionFilter === 'puts') {
            return this.currentMetric === 'gex' ? row.put_gamma : row.put_vega || 0;
        }

        return baseValue; // 'net' - both calls and puts
    },

    formatDateHeader(dateStr) {
        // Convert YYYYMMDD to YYYY-MM-DD
        if (dateStr.length === 8) {
            return `${dateStr.substring(0, 4)}-${dateStr.substring(4, 6)}-${dateStr.substring(6, 8)}`;
        }
        return dateStr;
    },

    getCellClass(value, maxAbs, strike, nodes) {
        // Check if highlighted strike (King Node or Gatekeeper)
        if (nodes && this.isHighlightedStrike(strike, nodes)) {
            return 'cell-highlight';
        }

        const absValue = Math.abs(value);
        const ratio = absValue / maxAbs;

        if (value > 0) {
            if (ratio > 0.6) return 'cell-positive-high';
            if (ratio > 0.3) return 'cell-positive-med';
            return 'cell-positive-low';
        } else {
            if (ratio > 0.6) return 'cell-negative-high';
            if (ratio > 0.3) return 'cell-negative-med';
            return 'cell-negative-low';
        }
    },

    isHighlightedStrike(strike, nodes) {
        if (!nodes) return false;
        if (nodes.kingNode && Math.abs(nodes.kingNode.strike - strike) < 1) return true;
        return nodes.gatekeepers.some(g => Math.abs(g.strike - strike) < 1);
    },

    getNodeIndicator(strike, nodes) {
        if (!nodes) return null;
        if (nodes.kingNode && Math.abs(nodes.kingNode.strike - strike) < 1) return 'K';
        if (nodes.gatekeepers.some(g => Math.abs(g.strike - strike) < 1)) return 'G';
        return null;
    },

    selectStrike(strike) {
        this.selectedStrike = strike;
        // Trigger re-render (will be called from main app)
        if (window.App && window.App.render) {
            window.App.render();
        }
    },

    setMetric(metric) {
        this.currentMetric = metric;
    },

    setOptionFilter(filter) {
        this.optionFilter = filter; // 'calls', 'puts', or 'net'
    }
};

Object.freeze(TableRenderer);
