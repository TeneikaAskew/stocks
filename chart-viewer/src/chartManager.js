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

        this.initializeChart();
    }

    /**
     * Initialize the chart
     */
    initializeChart() {
        if (!this.container) {
            console.error('Chart container not found');
            return;
        }

        // Create chart
        this.chart = LightweightCharts.createChart(this.container, {
            ...CONFIG.CHART,
            width: this.container.clientWidth,
            height: this.container.clientHeight,
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

        this.currentData = data;
        this.currentTicker = ticker;
        this.currentDate = date;

        // Set candlestick data
        this.candlestickSeries.setData(data.candlestick);

        // Set volume data
        this.volumeSeries.setData(data.volume);

        // Fit content
        this.chart.timeScale().fitContent();

        Utils.notify(`Chart loaded with ${data.candlestick.length} candles`, 'success');
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
        if (!param.time) {
            return;
        }

        const data = param.seriesData.get(this.candlestickSeries);

        if (data) {
            // Store click data for trade marking
            this.lastClickData = {
                time: param.time,
                price: data.close,
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
                shape: 'arrowUp',
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
}
