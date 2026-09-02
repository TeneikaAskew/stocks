// Trading Success Report Dashboard
// Main application logic

class TradingDashboard {
    constructor() {
        this.data = null;
        this.charts = {};
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadData();
    }

    setupEventListeners() {
        // Tab navigation
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.switchTab(e.target.dataset.tab));
        });

        // Refresh button
        document.getElementById('refreshData').addEventListener('click', () => this.loadData());
    }

    switchTab(tabId) {
        // Update active tab button
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabId);
        });

        // Update active tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('active', content.id === tabId);
        });

        // Initialize tab-specific content if needed
        this.initializeTabContent(tabId);
    }

    async loadData() {
        try {
            let response;
            
            if (CONFIG.DEV_MODE) {
                // Use local sample data in development
                response = await fetch('data/sample-report.json');
            } else {
                // Fetch from Google Apps Script Web App
                response = await fetch(`${CONFIG.WEB_APP_URL}?action=getReport`);
            }
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            this.data = await response.json();
            
            // Check for API errors
            if (this.data.error) {
                throw new Error(this.data.error);
            }
            
            this.updateLastUpdated();
            this.renderAllTabs();
            
            // Set up auto-refresh if configured
            if (CONFIG.AUTO_REFRESH_INTERVAL > 0) {
                this.setupAutoRefresh();
            }
        } catch (error) {
            console.error('Error loading data:', error);
            this.showError('Failed to load report data. Please check your connection and try again.');
        }
    }
    
    setupAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        
        this.refreshInterval = setInterval(() => {
            this.loadData();
        }, CONFIG.AUTO_REFRESH_INTERVAL);
    }
    
    showError(message) {
        // Create error message in the first tab content
        const activeContent = document.querySelector('.tab-content.active');
        if (activeContent) {
            activeContent.innerHTML = `
                <div style="text-align: center; padding: 40px; color: var(--danger-color);">
                    <h3>Error Loading Data</h3>
                    <p>${message}</p>
                    <button class="btn btn-primary" onclick="window.dashboard.loadData()">
                        Try Again
                    </button>
                </div>
            `;
        }
    }

    updateLastUpdated() {
        const lastUpdated = document.getElementById('lastUpdated');
        lastUpdated.textContent = `Last updated: ${new Date().toLocaleString()}`;
    }

    renderAllTabs() {
        if (!this.data) return;

        this.renderOverview();
        this.renderMultiDay();
        this.renderIndicators();
        this.renderEarnings();
        this.renderStrategies();
        this.renderTopPlays();
    }

    renderOverview() {
        const overview = this.data.overview;
        
        // Update metric cards
        document.getElementById('hitRate').textContent = `${(overview.hitRate * 100).toFixed(1)}%`;
        document.getElementById('profitableRate').textContent = `${(overview.profitableRate * 100).toFixed(1)}%`;
        document.getElementById('avgRiskReward').textContent = overview.avgRiskReward.toFixed(2);
        document.getElementById('avgDaysToHit').textContent = overview.avgDaysToHit.toFixed(1);

        // Create overview chart
        const ctx = document.getElementById('overviewChart').getContext('2d');
        
        if (this.charts.overview) {
            this.charts.overview.destroy();
        }

        this.charts.overview = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Total Trades', 'Hits', 'Profitable', 'Multi-Day Winners'],
                datasets: [{
                    label: 'Count',
                    data: [
                        overview.totalTrades,
                        overview.totalHits,
                        overview.profitableTrades,
                        overview.multiDayWinners
                    ],
                    backgroundColor: [
                        '#3b82f6',
                        '#10b981',
                        '#22c55e',
                        '#f59e0b'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }

    renderMultiDay() {
        const multiDay = this.data.multiDayProfitability;
        
        // Create multi-day chart
        const ctx = document.getElementById('multiDayChart').getContext('2d');
        
        if (this.charts.multiDay) {
            this.charts.multiDay.destroy();
        }

        this.charts.multiDay = new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['Day 0', 'Day 1', 'Day 2', 'Day 3', 'Day 4', 'Day 5'],
                datasets: [{
                    label: 'Profitability Rate',
                    data: multiDay.profitabilityByDay.map(d => d.rate * 100),
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        }
                    }
                }
            }
        });

        // Create table
        const tableHtml = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Days Profitable</th>
                        <th>Trade Count</th>
                        <th>Success Rate</th>
                        <th>Avg Profit</th>
                    </tr>
                </thead>
                <tbody>
                    ${multiDay.sustainedWinners.map(row => `
                        <tr>
                            <td>${row.days}+ days</td>
                            <td>${row.count}</td>
                            <td class="text-success">${(row.successRate * 100).toFixed(1)}%</td>
                            <td class="${row.avgProfit >= 0 ? 'text-success' : 'text-danger'}">
                                ${row.avgProfit.toFixed(2)}%
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        
        document.getElementById('multiDayTable').innerHTML = tableHtml;
    }

    renderIndicators() {
        const indicators = this.data.indicatorEffectiveness;
        
        const gridHtml = indicators.map(ind => {
            const significanceClass = 
                ind.correlation > 0.3 ? 'high' : 
                ind.correlation > 0.15 ? 'medium' : 'low';
            
            return `
                <div class="indicator-card ${significanceClass}">
                    <div class="indicator-name">${ind.name}</div>
                    <div class="indicator-correlation">
                        Correlation: ${ind.correlation.toFixed(3)}
                    </div>
                    <div class="indicator-range">
                        Profitable Range: ${ind.profitableRange}
                    </div>
                    <div class="indicator-stats">
                        <span>Hit Rate: ${(ind.hitRate * 100).toFixed(1)}%</span>
                        <span class="${ind.avgProfit >= 0 ? 'text-success' : 'text-danger'}">
                            Avg: ${ind.avgProfit.toFixed(2)}%
                        </span>
                    </div>
                </div>
            `;
        }).join('');
        
        document.getElementById('indicatorsGrid').innerHTML = gridHtml;
    }

    renderEarnings() {
        const earnings = this.data.earningsTiming;
        
        // Create earnings chart
        const ctx = document.getElementById('earningsChart').getContext('2d');
        
        if (this.charts.earnings) {
            this.charts.earnings.destroy();
        }

        this.charts.earnings = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Pre-Earnings', 'Post-Earnings'],
                datasets: [{
                    label: 'Hit Rate',
                    data: [
                        earnings.preEarnings.hitRate * 100,
                        earnings.postEarnings.hitRate * 100
                    ],
                    backgroundColor: ['#3b82f6', '#10b981']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        }
                    }
                }
            }
        });

        // Render insights
        const insightsHtml = `
            <div class="insight-item">
                <div class="insight-icon">📊</div>
                <div>
                    <strong>Pre-Earnings Performance:</strong> 
                    ${earnings.preEarnings.hitRate > earnings.postEarnings.hitRate ? 
                        'Higher hit rate before earnings announcements' : 
                        'Lower hit rate before earnings'}
                </div>
            </div>
            <div class="insight-item">
                <div class="insight-icon">⏱️</div>
                <div>
                    <strong>Optimal Entry:</strong> 
                    ${earnings.optimalDaysBeforeEarnings} days before earnings
                </div>
            </div>
            <div class="insight-item">
                <div class="insight-icon">💡</div>
                <div>
                    <strong>Recommendation:</strong> 
                    ${earnings.recommendation}
                </div>
            </div>
        `;
        
        document.getElementById('earningsInsights').innerHTML = insightsHtml;
    }

    renderStrategies() {
        const strategies = this.data.strategyPerformance;
        
        // Create strategy chart
        const ctx = document.getElementById('strategyChart').getContext('2d');
        
        if (this.charts.strategy) {
            this.charts.strategy.destroy();
        }

        this.charts.strategy = new Chart(ctx, {
            type: 'radar',
            data: {
                labels: strategies.map(s => s.strategy),
                datasets: [{
                    label: 'Hit Rate %',
                    data: strategies.map(s => s.hitRate * 100),
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.2)'
                }, {
                    label: 'Profit Factor',
                    data: strategies.map(s => s.profitFactor * 20), // Scale for visibility
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.2)'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    r: {
                        beginAtZero: true,
                        max: 100
                    }
                }
            }
        });

        // Create table
        const tableHtml = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Strategy</th>
                        <th>Trades</th>
                        <th>Hit Rate</th>
                        <th>Profit Factor</th>
                        <th>Avg Days to Hit</th>
                    </tr>
                </thead>
                <tbody>
                    ${strategies.map(row => `
                        <tr>
                            <td>${row.strategy}</td>
                            <td>${row.tradeCount}</td>
                            <td class="text-success">${(row.hitRate * 100).toFixed(1)}%</td>
                            <td class="${row.profitFactor >= 1 ? 'text-success' : 'text-danger'}">
                                ${row.profitFactor.toFixed(2)}
                            </td>
                            <td>${row.avgDaysToHit.toFixed(1)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        
        document.getElementById('strategyTable').innerHTML = tableHtml;
    }

    renderTopPlays() {
        const topPlays = this.data.topPlays;
        
        const tableHtml = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Entry Date</th>
                        <th>Strategy</th>
                        <th>Max Profit</th>
                        <th>Days to Hit</th>
                        <th>RSI</th>
                        <th>Price vs SMA20</th>
                        <th>RVOL</th>
                    </tr>
                </thead>
                <tbody>
                    ${topPlays.map(play => {
                        const maxProfit = Number(play.maxProfit);
                        const priceVsSMA20 = Number(play.priceVsSMA20);
                        const rsi = Number(play.rsi);
                        const rvol = Number(play.rvol);

                        return `
                        <tr>
                            <td><strong>${play.symbol}</strong></td>
                            <td>${new Date(play.entryDate).toLocaleDateString()}</td>
                            <td>${play.strategy}</td>
                            <td class="text-success">${Number.isFinite(maxProfit) ? maxProfit.toFixed(2) : '-'}%</td>
                            <td>${play.daysToHit ?? '-'}</td>
                            <td>${Number.isFinite(rsi) ? rsi.toFixed(1) : '-'}</td>
                            <td class="${Number.isFinite(priceVsSMA20) && priceVsSMA20 >= 0 ? 'text-success' : 'text-danger'}">
                                ${Number.isFinite(priceVsSMA20) ? priceVsSMA20.toFixed(2) : '-'}%
                            </td>
                            <td>${Number.isFinite(rvol) ? rvol.toFixed(2) : '-'}</td>
                        </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;
        
        document.getElementById('topPlaysTable').innerHTML = tableHtml;
    }

    initializeTabContent(tabId) {
        // Re-render specific tab if needed (e.g., to resize charts)
        if (this.data) {
            switch(tabId) {
                case 'overview':
                    this.renderOverview();
                    break;
                case 'multiday':
                    this.renderMultiDay();
                    break;
                case 'strategies':
                    this.renderStrategies();
                    break;
                case 'earnings':
                    this.renderEarnings();
                    break;
            }
        }
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new TradingDashboard();
});