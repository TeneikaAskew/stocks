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
        this.referenceLines = []; // Price lines for previous period OHLC
        this.currentReferencePeriod = null; // Track current period

        this.initializeChart();
        this.setupVolumeToggle();
        this.setupRTHToggle();
        this.setupDarkModeToggle();
        this.setupReferenceLinesToggle();
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
                    // Timestamps are stored as "naive" ET times (not true UTC)
                    // Read UTC components directly - they represent the actual ET time
                    const date = new Date(timestamp * 1000);
                    const hours = String(date.getUTCHours()).padStart(2, '0');
                    const minutes = String(date.getUTCMinutes()).padStart(2, '0');

                    // Determine if it's EDT or EST based on date (approximate)
                    const isEDT = date.getUTCMonth() >= 2 && date.getUTCMonth() <= 10;
                    const tzStr = isEDT ? 'EDT' : 'EST';

                    return `${hours}:${minutes} ${tzStr}`;
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

    /**
     * Setup dark mode toggle listener
     */
    setupDarkModeToggle() {
        const darkModeToggle = document.getElementById('darkModeToggle');
        if (darkModeToggle) {
            // Load saved theme preference
            const savedTheme = localStorage.getItem('chartTheme') || 'light';
            const isDark = savedTheme === 'dark';
            darkModeToggle.checked = isDark;

            // Apply theme on load
            if (isDark) {
                this.applyTheme('dark');
            }

            darkModeToggle.addEventListener('change', (e) => {
                const theme = e.target.checked ? 'dark' : 'light';
                this.applyTheme(theme);
                localStorage.setItem('chartTheme', theme);
            });
        }
    }

    /**
     * Apply theme to chart and update CONFIG
     */
    applyTheme(theme) {
        const themeColors = CONFIG.THEMES[theme];

        // Toggle body class for full app theming
        if (theme === 'dark') {
            document.body.classList.add('dark-theme');
        } else {
            document.body.classList.remove('dark-theme');
        }

        // Update CONFIG with new theme
        CONFIG.currentTheme = theme;
        Object.assign(CONFIG.CHART.layout, themeColors.chart.layout);
        Object.assign(CONFIG.CHART.grid, themeColors.chart.grid);
        CONFIG.CHART.timeScale.borderColor = themeColors.chart.timeScale.borderColor;
        CONFIG.CHART.rightPriceScale.borderColor = themeColors.chart.rightPriceScale.borderColor;
        Object.assign(CONFIG.CANDLE_COLORS, themeColors.candles);
        Object.assign(CONFIG.VOLUME_COLORS, themeColors.volume);
        Object.assign(CONFIG.MARKER_COLORS, themeColors.markers);

        // Apply layout changes to chart
        this.chart.applyOptions({
            layout: themeColors.chart.layout,
            grid: themeColors.chart.grid,
            timeScale: {
                ...this.chart.options().timeScale,
                borderColor: themeColors.chart.timeScale.borderColor,
            },
            rightPriceScale: {
                ...this.chart.options().rightPriceScale,
                borderColor: themeColors.chart.rightPriceScale.borderColor,
            },
        });

        // Update candlestick colors
        this.candlestickSeries.applyOptions(themeColors.candles);

        // Reload volume data with new colors if visible
        if (this.volumeVisible && this.currentData) {
            const filteredData = this.rthOnly ? this.filterRTH(this.currentData) : this.currentData;
            const volumeData = filteredData.volume.map(v => ({
                ...v,
                color: v.value > 0 ? themeColors.volume.upColor : themeColors.volume.downColor,
            }));
            this.volumeSeries.setData(volumeData);
        }

        // Reload markers with new colors if they exist
        const trades = this.currentData ? window.app?.tradeMarker?.getTradesForDate(this.currentTicker, this.currentDate) : [];
        if (trades && trades.length > 0) {
            this.addMarkers(trades);
        }

        Utils.notify(`${theme === 'dark' ? 'Dark' : 'Light'} mode enabled`, 'info');
    }

    /**
     * Setup reference lines toggle listener
     */
    setupReferenceLinesToggle() {
        const referenceToggle = document.getElementById('referenceLinesToggle');
        if (referenceToggle) {
            referenceToggle.addEventListener('change', async (e) => {
                if (e.target.checked) {
                    // Checkbox is ON - show ALL period OHLC lines + order blocks
                    await this.addReferenceLines('day');
                    await this.addReferenceLines('week');
                    await this.addReferenceLines('month');
                    await this.addReferenceLines('year');
                    await this.addOrderBlocks();
                } else {
                    // Checkbox is OFF - remove all reference lines
                    this.clearReferenceLines();
                    this.currentReferencePeriod = null;
                }
            });
        }
    }

    /**
     * Add reference lines for a specific period
     * @param {string} period - 'day' | 'week' | 'month' | 'year'
     */
    async addReferenceLines(period) {
        if (!this.currentTicker || !this.currentDate) {
            Utils.notify('Please load chart data first', 'error');
            return;
        }

        // Note: Don't clear existing lines here - we want to show ALL periods at once
        Utils.notify(`Loading previous ${period} reference lines...`, 'info');

        try {
            // Get reference line manager from app
            const referenceManager = window.app?.referenceLineManager;
            if (!referenceManager) {
                console.error('ReferenceLineManager not initialized');
                Utils.notify('Reference line manager not available', 'error');
                return;
            }

            // Get previous period OHLC
            const ohlc = await referenceManager.getPreviousPeriodOHLC(
                this.currentTicker,
                this.currentDate,
                period
            );

            if (!ohlc) {
                Utils.notify(`No data available for previous ${period}`, 'error');
                return;
            }

            // Add price lines for each OHLC value
            const periodName = referenceManager.formatPeriodName(period);

            // Log the OHLC values
            console.log(`[ChartManager] Adding reference lines for ${periodName}:`);
            console.log(`  Period: ${ohlc.startDate} - ${ohlc.endDate}`);
            console.log(`  Open:  ${ohlc.open.toFixed(2)}`);
            console.log(`  High:  ${ohlc.high.toFixed(2)}`);
            console.log(`  Low:   ${ohlc.low.toFixed(2)}`);
            console.log(`  Close: ${ohlc.close.toFixed(2)}`);

            // High line (resistance)
            console.log(`[ChartManager] Creating HIGH line at ${ohlc.high.toFixed(2)}`);
            const highLine = this.candlestickSeries.createPriceLine({
                price: ohlc.high,
                color: CONFIG.REFERENCE_LINE_COLORS.HIGH,
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `${periodName} High: ${ohlc.high.toFixed(2)}`,
            });
            this.referenceLines.push(highLine);
            console.log(`[ChartManager] HIGH line created, total lines: ${this.referenceLines.length}`);

            // Low line (support)
            console.log(`[ChartManager] Creating LOW line at ${ohlc.low.toFixed(2)}`);
            const lowLine = this.candlestickSeries.createPriceLine({
                price: ohlc.low,
                color: CONFIG.REFERENCE_LINE_COLORS.LOW,
                lineWidth: 2,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `${periodName} Low: ${ohlc.low.toFixed(2)}`,
            });
            this.referenceLines.push(lowLine);
            console.log(`[ChartManager] LOW line created, total lines: ${this.referenceLines.length}`);

            // Open line
            console.log(`[ChartManager] Creating OPEN line at ${ohlc.open.toFixed(2)}`);
            const openLine = this.candlestickSeries.createPriceLine({
                price: ohlc.open,
                color: CONFIG.REFERENCE_LINE_COLORS.OPEN,
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `${periodName} Open: ${ohlc.open.toFixed(2)}`,
            });
            this.referenceLines.push(openLine);
            console.log(`[ChartManager] OPEN line created, total lines: ${this.referenceLines.length}`);

            // Close line
            console.log(`[ChartManager] Creating CLOSE line at ${ohlc.close.toFixed(2)}`);
            const closeLine = this.candlestickSeries.createPriceLine({
                price: ohlc.close,
                color: CONFIG.REFERENCE_LINE_COLORS.CLOSE,
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: true,
                title: `${periodName} Close: ${ohlc.close.toFixed(2)}`,
            });
            this.referenceLines.push(closeLine);
            console.log(`[ChartManager] CLOSE line created, total lines: ${this.referenceLines.length}`);

            this.currentReferencePeriod = period;
            console.log(`[ChartManager] ✅ ALL 4 LINES CREATED SUCCESSFULLY`);
            console.log(`[ChartManager] Reference lines array:`, this.referenceLines);

            Utils.notify(`${periodName} reference lines added (${ohlc.startDate} - ${ohlc.endDate})`, 'success');
        } catch (error) {
            console.error('Error adding reference lines:', error);
            Utils.notify(`Error adding reference lines: ${error.message}`, 'error');
        }
    }

    /**
     * Add order block lines (high and low of first candle based on timeframe)
     */
    async addOrderBlocks() {
        if (!this.currentData || !this.currentData.candlestick || this.currentData.candlestick.length === 0) {
            console.warn('[ChartManager] No candle data available for order blocks');
            return;
        }

        // Get the first candle from the current data
        const firstCandle = this.currentData.candlestick[0];

        console.log('[ChartManager] Adding Order Blocks:');
        console.log(`  First Candle High: ${firstCandle.high.toFixed(2)}`);
        console.log(`  First Candle Low:  ${firstCandle.low.toFixed(2)}`);

        // Order Block High line
        const obHighLine = this.candlestickSeries.createPriceLine({
            price: firstCandle.high,
            color: CONFIG.REFERENCE_LINE_COLORS.HIGH, // Yellow-gold
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: `Order Block High: ${firstCandle.high.toFixed(2)}`,
        });
        this.referenceLines.push(obHighLine);
        console.log(`[ChartManager] Order Block HIGH line created, total lines: ${this.referenceLines.length}`);

        // Order Block Low line
        const obLowLine = this.candlestickSeries.createPriceLine({
            price: firstCandle.low,
            color: CONFIG.REFERENCE_LINE_COLORS.LOW, // Yellow-gold
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: `Order Block Low: ${firstCandle.low.toFixed(2)}`,
        });
        this.referenceLines.push(obLowLine);
        console.log(`[ChartManager] Order Block LOW line created, total lines: ${this.referenceLines.length}`);

        Utils.notify('Order block lines added', 'success');
    }

    /**
     * Clear all reference lines
     */
    clearReferenceLines() {
        this.referenceLines.forEach(line => {
            this.candlestickSeries.removePriceLine(line);
        });
        this.referenceLines = [];
    }
}
