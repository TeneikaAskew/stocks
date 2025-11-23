// ===== Heatmap Renderer =====

const HeatmapRenderer = {
    svg: null,
    width: 0,
    height: 0,
    margin: CONFIG.HEATMAP.MARGIN,
    currentData: null,
    currentSpot: null,
    currentNodes: null,

    render(aggregatedStrikes, spotPrice, nodes) {
        this.currentData = aggregatedStrikes;
        this.currentSpot = spotPrice;
        this.currentNodes = nodes;

        const container = document.getElementById('heatmap-canvas');
        if (!container) return;

        // Clear existing content
        container.innerHTML = '';

        // Calculate dimensions
        const containerWidth = container.clientWidth;
        const containerHeight = Math.max(600, aggregatedStrikes.length * CONFIG.HEATMAP.BAR_HEIGHT);

        this.width = containerWidth - this.margin.left - this.margin.right;
        this.height = containerHeight - this.margin.top - this.margin.bottom;

        // Create SVG
        this.svg = d3.select(container)
            .append('svg')
            .attr('width', containerWidth)
            .attr('height', containerHeight)
            .attr('class', 'heatmap-svg');

        const g = this.svg.append('g')
            .attr('transform', `translate(${this.margin.left},${this.margin.top})`);

        // Create scales
        const yScale = d3.scaleBand()
            .domain(aggregatedStrikes.map(d => d.strike))
            .range([0, this.height])
            .padding(0.1);

        const maxAbsGamma = d3.max(aggregatedStrikes, d => Math.abs(d.net_gamma));

        const xScale = d3.scaleLinear()
            .domain([-maxAbsGamma, maxAbsGamma])
            .range([0, this.width]);

        // Create color scales
        const positiveColorScale = d3.scaleLinear()
            .domain([0, maxAbsGamma])
            .range([CONFIG.HEATMAP.COLORS.POSITIVE_LIGHT, CONFIG.HEATMAP.COLORS.POSITIVE_DARK]);

        const negativeColorScale = d3.scaleLinear()
            .domain([-maxAbsGamma, 0])
            .range([CONFIG.HEATMAP.COLORS.NEGATIVE_DARK, CONFIG.HEATMAP.COLORS.NEGATIVE_LIGHT]);

        // Add zero line
        g.append('line')
            .attr('x1', xScale(0))
            .attr('x2', xScale(0))
            .attr('y1', 0)
            .attr('y2', this.height)
            .attr('class', 'grid-line')
            .style('stroke-width', 2)
            .style('opacity', 0.5);

        // Add bars
        const bars = g.selectAll('.strike-row')
            .data(aggregatedStrikes)
            .enter()
            .append('g')
            .attr('class', 'strike-row')
            .attr('transform', d => `translate(0, ${yScale(d.strike)})`);

        // Add bar rectangles
        bars.append('rect')
            .attr('class', 'strike-bar')
            .attr('x', d => d.net_gamma >= 0 ? xScale(0) : xScale(d.net_gamma))
            .attr('width', d => Math.abs(xScale(d.net_gamma) - xScale(0)))
            .attr('height', yScale.bandwidth())
            .attr('fill', d => d.net_gamma >= 0 ?
                positiveColorScale(d.net_gamma) :
                negativeColorScale(d.net_gamma))
            .attr('opacity', 0.8)
            .on('mouseover', (event, d) => this.showTooltip(event, d))
            .on('mouseout', () => this.hideTooltip())
            .on('click', (event, d) => this.onStrikeClick(d));

        // Add strike labels
        bars.append('text')
            .attr('class', 'strike-label')
            .attr('x', -10)
            .attr('y', yScale.bandwidth() / 2)
            .attr('text-anchor', 'end')
            .attr('dominant-baseline', 'middle')
            .text(d => `$${d.strike.toFixed(2)}`);

        // Add value labels
        bars.append('text')
            .attr('class', 'strike-value')
            .attr('x', d => d.net_gamma >= 0 ?
                xScale(d.net_gamma) + 5 :
                xScale(d.net_gamma) - 5)
            .attr('y', yScale.bandwidth() / 2)
            .attr('text-anchor', d => d.net_gamma >= 0 ? 'start' : 'end')
            .attr('dominant-baseline', 'middle')
            .text(d => Utils.formatCurrency(d.net_gamma));

        // Add current price line
        if (spotPrice) {
            const spotY = yScale(this.findClosestStrike(spotPrice, aggregatedStrikes));

            g.append('line')
                .attr('class', 'current-price-line')
                .attr('x1', 0)
                .attr('x2', this.width)
                .attr('y1', spotY)
                .attr('y2', spotY);

            g.append('text')
                .attr('class', 'current-price-label')
                .attr('x', this.width + 10)
                .attr('y', spotY)
                .attr('dominant-baseline', 'middle')
                .text(`▶ $${spotPrice.toFixed(2)}`);
        }

        // Add node indicators
        if (nodes) {
            this.addNodeIndicators(g, nodes, yScale, aggregatedStrikes);
        }

        // Add axes
        const yAxis = d3.axisLeft(yScale)
            .tickValues(aggregatedStrikes.filter((d, i) => i % 5 === 0).map(d => d.strike));

        g.append('g')
            .attr('class', 'y-axis')
            .call(yAxis)
            .selectAll('text')
            .style('display', 'none'); // Hide axis labels since we have inline labels

        // Add legend
        this.addLegend(container);
    },

    findClosestStrike(price, strikes) {
        return strikes.reduce((prev, curr) =>
            Math.abs(curr.strike - price) < Math.abs(prev.strike - price) ? curr : prev
        ).strike;
    },

    addNodeIndicators(g, nodes, yScale, strikes) {
        const indicators = [];

        if (nodes.kingNode) {
            indicators.push({ ...nodes.kingNode, type: 'king' });
        }

        nodes.gatekeepers.forEach(node => {
            indicators.push({ ...node, type: 'gatekeeper' });
        });

        nodes.midpoints.slice(0, 3).forEach(node => {
            indicators.push({ ...node, type: 'midpoint' });
        });

        indicators.forEach(node => {
            const closestStrike = this.findClosestStrike(node.strike, strikes);
            const y = yScale(closestStrike) + yScale.bandwidth() / 2;

            // Add indicator circle
            g.append('circle')
                .attr('class', `node-indicator ${node.type}`)
                .attr('cx', -30)
                .attr('cy', y)
                .attr('r', 6)
                .style('fill', CONFIG.HEATMAP.COLORS[node.type.toUpperCase()] || '#888');

            // Add node label
            g.append('text')
                .attr('class', 'node-label')
                .attr('x', -40)
                .attr('y', y)
                .attr('text-anchor', 'end')
                .attr('dominant-baseline', 'middle')
                .style('font-size', '10px')
                .style('fill', CONFIG.HEATMAP.COLORS[node.type.toUpperCase()] || '#888')
                .text(node.type === 'king' ? '👑' : node.type === 'gatekeeper' ? '🛡️' : '⚠️');
        });
    },

    addLegend(container) {
        const legend = d3.select(container)
            .append('div')
            .attr('class', 'heatmap-legend')
            .style('position', 'absolute')
            .style('bottom', '20px')
            .style('right', '20px')
            .style('background', 'var(--bg-secondary)')
            .style('border', '1px solid var(--border-color)')
            .style('border-radius', '6px')
            .style('padding', '12px');

        legend.append('div')
            .attr('class', 'legend-title')
            .text('Dealer Gamma Exposure');

        // Positive gradient
        const posLegend = legend.append('div')
            .attr('class', 'legend-gradient')
            .style('display', 'flex')
            .style('align-items', 'center')
            .style('gap', '8px')
            .style('margin-top', '8px');

        posLegend.append('div')
            .attr('class', 'gradient-bar positive')
            .style('width', '100px')
            .style('height', '20px')
            .style('border-radius', '4px')
            .style('background', `linear-gradient(to right, ${CONFIG.HEATMAP.COLORS.POSITIVE_LIGHT}, ${CONFIG.HEATMAP.COLORS.POSITIVE_DARK})`);

        posLegend.append('span')
            .attr('class', 'legend-label')
            .style('font-size', '11px')
            .style('color', 'var(--text-secondary)')
            .text('Positive (Low Vol)');

        // Negative gradient
        const negLegend = legend.append('div')
            .attr('class', 'legend-gradient')
            .style('display', 'flex')
            .style('align-items', 'center')
            .style('gap', '8px')
            .style('margin-top', '4px');

        negLegend.append('div')
            .attr('class', 'gradient-bar negative')
            .style('width', '100px')
            .style('height', '20px')
            .style('border-radius', '4px')
            .style('background', `linear-gradient(to right, ${CONFIG.HEATMAP.COLORS.NEGATIVE_DARK}, ${CONFIG.HEATMAP.COLORS.NEGATIVE_LIGHT})`);

        negLegend.append('span')
            .attr('class', 'legend-label')
            .style('font-size', '11px')
            .style('color', 'var(--text-secondary)')
            .text('Negative (High Vol)');
    },

    showTooltip(event, data) {
        const content = `
            <strong>Strike: $${data.strike.toFixed(2)}</strong><br>
            <strong>Net Gamma: ${Utils.formatCurrency(data.net_gamma)}</strong><br>
            <hr style="margin: 8px 0; border: none; border-top: 1px solid var(--border-color);">
            Call OI: ${Utils.formatNumber(data.call_oi)}<br>
            Put OI: ${Utils.formatNumber(data.put_oi)}<br>
            Total OI: ${Utils.formatNumber(data.total_oi)}<br>
            Net Delta: ${Utils.formatCurrency(data.net_delta)}<br>
            Net Vega: ${Utils.formatCurrency(data.net_vega)}<br>
        `;

        TooltipManager.show(content, event.pageX, event.pageY);
    },

    hideTooltip() {
        TooltipManager.hide();
    },

    onStrikeClick(data) {
        // Update strike details panel
        const detailsPanel = document.getElementById('strike-details');
        if (!detailsPanel) return;

        detailsPanel.innerHTML = `
            <h4>Strike: $${data.strike.toFixed(2)}</h4>
            <div class="detail-row">
                <span class="detail-label">Net Gamma:</span>
                <span class="detail-value ${data.net_gamma >= 0 ? 'value-positive' : 'value-negative'}">
                    ${Utils.formatCurrency(data.net_gamma)}
                </span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Call OI:</span>
                <span class="detail-value">${Utils.formatNumber(data.call_oi)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Put OI:</span>
                <span class="detail-value">${Utils.formatNumber(data.put_oi)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Total OI:</span>
                <span class="detail-value">${Utils.formatNumber(data.total_oi)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Net Delta:</span>
                <span class="detail-value">${Utils.formatCurrency(data.net_delta)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Net Vega:</span>
                <span class="detail-value">${Utils.formatCurrency(data.net_vega)}</span>
            </div>
            <div class="detail-row">
                <span class="detail-label">Distance from Spot:</span>
                <span class="detail-value">
                    ${((data.strike - this.currentSpot) / this.currentSpot * 100).toFixed(2)}%
                </span>
            </div>
        `;
    }
};

Object.freeze(HeatmapRenderer);
