// Chart Manager - Handles TradingView Lightweight Charts

class ChartManager {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.chart = null;
        this.candlestickSeries = null;
        this.volumeSeries = null;
        this.markers = [];
        this.currentData = null;
        this.currentTicker = null;
        this.currentDate = null;
        this.volumeVisible = false; // Default to hidden
        this.rthOnly = true; // Default to regular trading hours only
        this.tempPriceLines = []; // Temporary price lines for drawing mode
        this.tradePriceLines = []; // Price lines for trades (TP/SL)

        this.initializeChart();
        this.setupVolumeToggle();
        this.setupRTHToggle();
    }

    /**
     * Initialize the chart
     */
    initializeChart() {
        if (!this.container) {
            console.error('Chart container not found');
            return;
        }

        // Create chart with Eastern Time localization
        this.chart = LightweightCharts.createChart(this.container, {
            ...CONFIG.CHART,
            width: this.container.clientWidth,
            height: this.container.clientHeight,
            localization: {
                timeFormatter: (timestamp) => {
                    // Convert Unix timestamp to Eastern Time
                    const date = new Date(timestamp * 1000);
                    const etTime = date.toLocaleString('en-US', {
                        timeZone: 'America/New_York',
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: false
                    });
                    // Return just HH:MM
                    return etTime;
                },
            },
        });

        // Create candlestick series
        this.candlestickSeries = this.chart.addCandlestickSeries(CONFIG.CANDLE_COLORS);

        // Create volume series
        this.volumeSeries = this.chart.addHistogramSeries({
            priceFormat: {
                type: 'volume',
            },
            priceScaleId: '',
            scaleMargins: {
                top: 0.8,
                bottom: 0,
            },
        });

        // Handle window resize
        window.addEventListener('resize', () => {
            this.resize();
        });

        // Subscribe to crosshair move for price/time display
        this.chart.subscribeCrosshairMove((param) => {
            this.updatePriceInfo(param);
        });

        // Subscribe to click events for trade marking
        this.chart.subscribeClick((param) => {
            this.handleChartClick(param);
        });
    }

    /**
     * Load data into the chart
     */
    loadData(data, ticker, date) {
        if (!data || !data.candlestick || !data.volume) {
            console.error('Invalid data format');
            return;
        }

        // Store original data
        this.currentData = data;
        this.currentTicker = ticker;
        this.currentDate = date;

        // Apply RTH filter if enabled
        const filteredData = this.rthOnly ? this.filterRTH(data) : data;

        // Set candlestick data
        this.candlestickSeries.setData(filteredData.candlestick);

        // Set volume data only if volume is visible
        if (this.volumeVisible) {
            this.volumeSeries.setData(filteredData.volume);
        } else {
            this.volumeSeries.setData([]);
        }

        // Fit content
        this.chart.timeScale().fitContent();

        const totalCandles = data.candlestick.length;
        const displayedCandles = filteredData.candlestick.length;
        const message = this.rthOnly
            ? `Chart loaded with ${displayedCandles} candles (RTH only, ${totalCandles - displayedCandles} filtered)`
            : `Chart loaded with ${totalCandles} candles`;

        Utils.notify(message, 'success');
    }

    /**
     * Filter data to regular trading hours (9:30 AM - 4:00 PM ET)
     */
    filterRTH(data) {
        const filterByTime = (items) => {
            // Debug: log first few items to understand timestamp format
            if (items.length > 0) {
                console.log('[RTH Filter] Analyzing timestamps...');
                for (let i = 0; i < Math.min(3, items.length); i++) {
                    const date = new Date(items[i].time * 1000);

                    // Try interpreting as if it's already in ET (not UTC)
                    const etHours = date.getUTCHours();
                    const etMinutes = date.getUTCMinutes();

                    console.log(`  Timestamp ${items[i].time}:`);
                    console.log(`    - If interpreted as ET: ${etHours}:${String(etMinutes).padStart(2, '0')}`);
                    console.log(`    - UTC ISO: ${date.toISOString()}`);
                    console.log(`    - Your local: ${date.toLocaleString()}`);
                }
            }

            return items.filter(item => {
                const date = new Date(item.time * 1000);

                // The timestamps appear to be stored as if they're in ET timezone
                // but marked as UTC. So we read them as UTC hours/minutes which
                // actually represent ET hours/minutes.
                const etHours = date.getUTCHours();
                const etMinutes = date.getUTCMinutes();
                const etTimeInMinutes = etHours * 60 + etMinutes;

                // RTH is 9:30 AM - 4:00 PM ET
                const rthStart = 9 * 60 + 30;  // 9:30 AM = 570 minutes
                const rthEnd = 16 * 60;         // 4:00 PM = 960 minutes

                const isRTH = etTimeInMinutes >= rthStart && etTimeInMinutes < rthEnd;

                // Debug log for first item
                if (item === items[0]) {
                    console.log(`[RTH Filter] First candle: ${etHours}:${String(etMinutes).padStart(2, '0')} ET -> ${isRTH ? 'KEEP (RTH)' : 'FILTER (not RTH)'}`);
                    console.log(`[RTH Filter] RTH range: 9:30 AM - 4:00 PM ET (${rthStart} - ${rthEnd} minutes)`);
                }

                return isRTH;
            });
        };

        const filtered = {
            candlestick: filterByTime(data.candlestick),
            volume: filterByTime(data.volume)
        };

        console.log(`[RTH Filter] Filtered ${data.candlestick.length} -> ${filtered.candlestick.length} candles`);

        return filtered;
    }

    /**
     * Update price and time info on crosshair move
     */
    updatePriceInfo(param) {
        const priceInfo = document.getElementById('priceInfo');
        const timeInfo = document.getElementById('timeInfo');

        if (!param.time || !priceInfo || !timeInfo) {
            return;
        }

        const data = param.seriesData.get(this.candlestickSeries);

        if (data) {
            const price = data.close || data.value || 0;
            const time = Utils.formatDateTime(param.time);

            priceInfo.querySelector('.value').textContent = Utils.formatCurrency(price);
            timeInfo.querySelector('.value').textContent = time;
        }
    }

    /**
     * Handle chart click events
     */
    handleChartClick(param) {
        if (!param.time || !param.point) {
            return;
        }

        const data = param.seriesData.get(this.candlestickSeries);

        if (data) {
            // Convert the Y coordinate to a price using the price scale
            // This gives us the exact price at the crosshair position
            let clickedPrice;

            try {
                // Use coordinateToPrice to get the price at the Y coordinate
                clickedPrice = this.candlestickSeries.coordinateToPrice(param.point.y);
            } catch (e) {
                console.warn('Could not convert coordinate to price, using close:', e);
                clickedPrice = data.close;
            }

            console.log('[Chart Click] Y coordinate:', param.point.y, '-> Price:', clickedPrice);

            // Store click data for trade marking
            this.lastClickData = {
                time: param.time,
                price: clickedPrice || data.close,
                candle: data,
            };

            // Dispatch custom event for trade marking
            window.dispatchEvent(new CustomEvent('chartClick', {
                detail: this.lastClickData
            }));
        }
    }

    /**
     * Add markers to the chart
     */
    addMarkers(trades) {
        // Clear all existing trade price lines
        this.tradePriceLines.forEach(line => {
            this.candlestickSeries.removePriceLine(line);
        });
        this.tradePriceLines = [];

        if (!trades || trades.length === 0) {
            this.candlestickSeries.setMarkers([]);
            return;
        }

        const markers = [];

        for (const trade of trades) {
            // Entry marker
            markers.push({
                time: trade.entryTime,
                position: trade.optionType === 'CALL' ? 'belowBar' : 'aboveBar',
                color: trade.optionType === 'CALL'
                    ? CONFIG.MARKER_COLORS.CALL_ENTRY
                    : CONFIG.MARKER_COLORS.PUT_ENTRY,
                shape: trade.optionType === 'CALL' ? 'arrowUp' : 'arrowDown',
                text: `${trade.optionType} @ ${Utils.formatCurrency(trade.entryPrice)}`,
            });

            // Exit marker (if exists)
            if (trade.exitPrice && trade.exitTime) {
                const pnl = Utils.calculatePnL(trade.entryPrice, trade.exitPrice, trade.optionType);
                const isProfit = pnl > 0;

                markers.push({
                    time: trade.exitTime,
                    position: isProfit ? 'aboveBar' : 'belowBar',
                    color: isProfit
                        ? CONFIG.MARKER_COLORS.TP
                        : CONFIG.MARKER_COLORS.SL,
                    shape: 'arrowDown',
                    text: `Exit: ${Utils.formatCurrency(trade.exitPrice)} (${Utils.formatPercent(Utils.calculatePnLPercent(trade.entryPrice, trade.exitPrice, trade.optionType))})`,
                });
            }

            // TP/SL markers (as price lines)
            if (trade.takeProfits && trade.takeProfits.length > 0) {
                trade.takeProfits.forEach((tp, index) => {
                    if (tp.price) {
                        this.addPriceLine(tp.price, CONFIG.MARKER_COLORS.TP, `TP${index + 1}`, 'dotted');
                    }
                });
            }

            if (trade.stopLoss && trade.stopLoss.price) {
                this.addPriceLine(trade.stopLoss.price, CONFIG.MARKER_COLORS.SL, 'SL', 'dotted');
            }
        }

        this.candlestickSeries.setMarkers(markers);
        this.markers = markers;
    }

    /**
     * Add horizontal price line
     */
    addPriceLine(price, color, title, lineStyle = 'solid') {
        const priceLine = this.candlestickSeries.createPriceLine({
            price: price,
            color: color,
            lineWidth: 1,
            lineStyle: lineStyle === 'dotted' ? LightweightCharts.LineStyle.Dotted : LightweightCharts.LineStyle.Solid,
            axisLabelVisible: true,
            title: title,
        });

        // Store in tradePriceLines array so we can remove them later
        this.tradePriceLines.push(priceLine);

        return priceLine;
    }

    /**
     * Get last click data
     */
    getLastClickData() {
        return this.lastClickData;
    }

    /**
     * Resize chart
     */
    resize() {
        if (this.chart && this.container) {
            this.chart.applyOptions({
                width: this.container.clientWidth,
                height: this.container.clientHeight,
            });
        }
    }

    /**
     * Clear chart
     */
    clear() {
        if (this.candlestickSeries) {
            this.candlestickSeries.setData([]);
        }
        if (this.volumeSeries) {
            this.volumeSeries.setData([]);
        }
        this.currentData = null;
        this.currentTicker = null;
        this.currentDate = null;
    }

    /**
     * Destroy chart
     */
    destroy() {
        if (this.chart) {
            this.chart.remove();
            this.chart = null;
        }
    }

    /**
     * Setup volume toggle listener
     */
    setupVolumeToggle() {
        const volumeToggle = document.getElementById('volumeToggle');
        if (volumeToggle) {
            volumeToggle.addEventListener('change', (e) => {
                this.toggleVolume(e.target.checked);
            });
        }
    }

    /**
     * Setup RTH toggle listener
     */
    setupRTHToggle() {
        const rthToggle = document.getElementById('rthToggle');
        if (rthToggle) {
            rthToggle.addEventListener('change', (e) => {
                this.toggleRTH(e.target.checked);
            });
        }
    }

    /**
     * Toggle volume visibility
     */
    toggleVolume(visible) {
        this.volumeVisible = visible;

        if (this.volumeSeries && this.chart) {
            if (visible) {
                // Show volume by setting the data
                if (this.currentData && this.currentData.volume) {
                    const filteredData = this.rthOnly ? this.filterRTH(this.currentData) : this.currentData;
                    this.volumeSeries.setData(filteredData.volume);
                }
            } else {
                // Hide volume by clearing the data
                this.volumeSeries.setData([]);
            }
        }
    }

    /**
     * Toggle RTH (Regular Trading Hours) filter
     */
    toggleRTH(enabled) {
        this.rthOnly = enabled;

        // Reload the chart with the filter applied/removed
        if (this.currentData) {
            const filteredData = enabled ? this.filterRTH(this.currentData) : this.currentData;

            // Update candlestick data
            this.candlestickSeries.setData(filteredData.candlestick);

            // Update volume data if visible
            if (this.volumeVisible) {
                this.volumeSeries.setData(filteredData.volume);
            }

            // Fit content
            this.chart.timeScale().fitContent();

            const totalCandles = this.currentData.candlestick.length;
            const displayedCandles = filteredData.candlestick.length;
            const message = enabled
                ? `RTH filter enabled: showing ${displayedCandles} of ${totalCandles} candles`
                : `RTH filter disabled: showing all ${totalCandles} candles`;

            Utils.notify(message, 'info');
        }
    }

    /**
     * Add temporary price line (for drawing mode)
     */
    addTempPriceLine(price, color, title) {
        const priceLine = this.candlestickSeries.createPriceLine({
            price: price,
            color: color,
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: title,
        });

        this.tempPriceLines.push(priceLine);
        return priceLine;
    }

    /**
     * Clear all temporary price lines
     */
    clearTempLines() {
        this.tempPriceLines.forEach(line => {
            this.candlestickSeries.removePriceLine(line);
        });
        this.tempPriceLines = [];
    }
}
