// ===== Chart Renderer =====

const ChartRenderer = {
    render(aggregatedStrikes, spotPrice, nodes) {
        const container = document.getElementById('price-chart');
        if (!container) return;

        // Create mock price data for demonstration
        // In production, this would load actual historical price data
        const dates = this.generateMockDates(30);
        const prices = this.generateMockPrices(spotPrice, 30);

        // Extract key levels from aggregatedStrikes
        const levels = this.extractKeyLevels(aggregatedStrikes, nodes);

        // Create price trace
        const priceTrace = {
            x: dates,
            y: prices,
            type: 'scatter',
            mode: 'lines',
            name: 'Price',
            line: {
                color: '#2196F3',
                width: 2
            }
        };

        // Create shapes for horizontal levels
        const shapes = levels.map(level => ({
            type: 'line',
            x0: dates[0],
            x1: dates[dates.length - 1],
            y0: level.strike,
            y1: level.strike,
            line: {
                color: level.color,
                width: level.width || 1.5,
                dash: level.dash || 'solid'
            }
        }));

        // Add current price line
        shapes.push({
            type: 'line',
            x0: dates[0],
            x1: dates[dates.length - 1],
            y0: spotPrice,
            y1: spotPrice,
            line: {
                color: '#ff4444',
                width: 2,
                dash: 'dash'
            }
        });

        const layout = {
            title: {
                text: 'Price Chart with Key Levels',
                font: { size: 14, color: 'var(--text-primary)' }
            },
            xaxis: {
                title: 'Date',
                color: 'var(--text-secondary)',
                gridcolor: 'var(--border-color)'
            },
            yaxis: {
                title: 'Price',
                color: 'var(--text-secondary)',
                gridcolor: 'var(--border-color)'
            },
            shapes: shapes,
            plot_bgcolor: 'var(--bg-secondary)',
            paper_bgcolor: 'var(--bg-secondary)',
            font: {
                family: 'var(--font-family)',
                color: 'var(--text-primary)'
            },
            margin: { l: 60, r: 30, t: 40, b: 40 },
            hovermode: 'x unified',
            showlegend: true,
            legend: {
                x: 0,
                y: 1,
                bgcolor: 'var(--bg-tertiary)',
                bordercolor: 'var(--border-color)',
                borderwidth: 1
            }
        };

        const config = {
            responsive: true,
            displayModeBar: true,
            displaylogo: false,
            modeBarButtonsToRemove: ['select2d', 'lasso2d']
        };

        Plotly.newPlot(container, [priceTrace], layout, config);

        // Add annotations for key levels
        this.addLevelAnnotations(container, levels);
    },

    extractKeyLevels(aggregatedStrikes, nodes) {
        const levels = [];

        // King Node
        if (nodes && nodes.kingNode) {
            levels.push({
                strike: nodes.kingNode.strike,
                label: 'King Node',
                color: CONFIG.HEATMAP.COLORS.KING_NODE,
                width: 2
            });
        }

        // Gatekeepers
        if (nodes && nodes.gatekeepers) {
            nodes.gatekeepers.slice(0, 2).forEach(node => {
                levels.push({
                    strike: node.strike,
                    label: 'Gatekeeper',
                    color: CONFIG.HEATMAP.COLORS.GATEKEEPER,
                    width: 1.5
                });
            });
        }

        // Top 3 strikes by absolute gamma
        const topStrikes = [...aggregatedStrikes]
            .sort((a, b) => Math.abs(b.net_gamma) - Math.abs(a.net_gamma))
            .slice(0, 3);

        topStrikes.forEach(strike => {
            if (!levels.find(l => l.strike === strike.strike)) {
                levels.push({
                    strike: strike.strike,
                    label: 'High Gamma',
                    color: strike.net_gamma >= 0 ?
                        CONFIG.HEATMAP.COLORS.POSITIVE_DARK :
                        CONFIG.HEATMAP.COLORS.NEGATIVE_DARK,
                    width: 1,
                    dash: 'dot'
                });
            }
        });

        return levels;
    },

    addLevelAnnotations(container, levels) {
        // Add text annotations for the most important levels
        const annotations = levels.slice(0, 5).map(level => ({
            x: 1,
            y: level.strike,
            xref: 'paper',
            yref: 'y',
            text: `$${level.strike.toFixed(2)}`,
            showarrow: false,
            xanchor: 'left',
            font: {
                size: 10,
                color: level.color
            },
            bgcolor: 'var(--bg-secondary)',
            bordercolor: level.color,
            borderwidth: 1,
            borderpad: 2
        }));

        Plotly.relayout(container, { annotations });
    },

    generateMockDates(days) {
        const dates = [];
        const today = new Date();

        for (let i = days - 1; i >= 0; i--) {
            const date = new Date(today);
            date.setDate(date.getDate() - i);
            dates.push(date.toISOString().split('T')[0]);
        }

        return dates;
    },

    generateMockPrices(spotPrice, days) {
        const prices = [];
        let currentPrice = spotPrice * 0.95; // Start slightly below current

        for (let i = 0; i < days; i++) {
            // Random walk with drift toward spot price
            const drift = (spotPrice - currentPrice) * 0.05;
            const randomChange = (Math.random() - 0.5) * spotPrice * 0.02;
            currentPrice += drift + randomChange;

            prices.push(currentPrice);
        }

        return prices;
    }
};

Object.freeze(ChartRenderer);
