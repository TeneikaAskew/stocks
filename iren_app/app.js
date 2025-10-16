// IREN Market Insights Dashboard
// This application fetches and displays real-time market data for IREN Limited

class IrenDashboard {
    constructor() {
        this.data = null;
        this.chart = null;
        this.init();
    }

    async init() {
        await this.fetchData();
        this.updateUI();
        this.createChart();
        this.generateInsights();
        this.generatePredictions();

        // Auto-refresh every 5 minutes
        setInterval(() => this.refresh(), 300000);
    }

    async fetchData() {
        try {
            // Show loading state
            this.showLoading();

            // Fetch real-time data from backend API
            const response = await fetch('http://localhost:5000/api/market-data/IREN');

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            // Store market data
            this.data = data;

            // Use historical data from API
            this.historicalData = data.historical_data || [];

            // Store AI-generated insights and predictions
            this.insights = data.insights || {};
            this.predictions = data.predictions || {};

            this.hideLoading();
        } catch (error) {
            console.error('Error fetching data:', error);
            this.showError('Failed to fetch market data. Please ensure the backend server is running.');
        }
    }

    showLoading() {
        document.body.classList.add('loading');
        console.log('Loading market data...');
    }

    hideLoading() {
        document.body.classList.remove('loading');
        console.log('Data loaded successfully');
    }

    showError(message) {
        alert(message);
        console.error(message);
    }

    updateUI() {
        // Update last updated time
        document.getElementById('lastUpdated').textContent =
            new Date(this.data.updated).toLocaleString();

        // Update key metrics
        document.getElementById('currentPrice').textContent =
            `$${this.data.current_price.toFixed(2)}`;

        const changeEl = document.getElementById('dailyChange');
        const changeText = `${this.data.daily_change > 0 ? '+' : ''}${this.data.daily_change.toFixed(2)}%`;
        changeEl.textContent = changeText;
        changeEl.className = `metric-change ${this.data.daily_change >= 0 ? 'positive' : 'negative'}`;

        document.getElementById('marketCap').textContent =
            `$${(this.data.market_cap / 1e9).toFixed(2)}B`;

        document.getElementById('change30d').textContent =
            `+${this.data.change_30d.toFixed(2)}%`;

        document.getElementById('change90d').textContent =
            `+${this.data.change_90d.toFixed(2)}%`;

        // Update volume analysis
        document.getElementById('currentVolume').textContent =
            this.formatNumber(this.data.volume);

        document.getElementById('avgVolume').textContent =
            this.formatNumber(this.data.avg_volume);

        const volumeRatioEl = document.getElementById('volumeRatio');
        volumeRatioEl.textContent = `${this.data.volume_ratio.toFixed(2)}x`;

        const volumeStatus = document.getElementById('volumeStatus');
        if (this.data.volume_ratio > 1.5) {
            volumeStatus.textContent = 'High Activity';
            volumeStatus.style.color = 'var(--success-color)';
        } else if (this.data.volume_ratio < 0.7) {
            volumeStatus.textContent = 'Low Activity';
            volumeStatus.style.color = 'var(--danger-color)';
        } else {
            volumeStatus.textContent = 'Normal Activity';
            volumeStatus.style.color = 'var(--warning-color)';
        }

        // Update technical indicators
        document.getElementById('high52w').textContent = `$${this.data.high_52w.toFixed(2)}`;
        document.getElementById('low52w').textContent = `$${this.data.low_52w.toFixed(2)}`;

        // Handle beta and PE ratio which might be "N/A"
        const beta = typeof this.data.beta === 'number' ? this.data.beta.toFixed(2) : this.data.beta;
        const peRatio = typeof this.data.pe_ratio === 'number' ? this.data.pe_ratio.toFixed(2) : this.data.pe_ratio;

        document.getElementById('beta').textContent = beta;
        document.getElementById('peRatio').textContent = peRatio;
    }

    createChart() {
        const ctx = document.getElementById('priceChart').getContext('2d');

        this.chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: this.historicalData.map(d => d.date),
                datasets: [{
                    label: 'Price ($)',
                    data: this.historicalData.map(d => d.price),
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: 'rgba(15, 23, 42, 0.9)',
                        titleColor: '#f1f5f9',
                        bodyColor: '#cbd5e1',
                        borderColor: '#475569',
                        borderWidth: 1,
                        padding: 12,
                        displayColors: false
                    }
                },
                scales: {
                    x: {
                        display: true,
                        grid: {
                            color: 'rgba(71, 85, 105, 0.3)'
                        },
                        ticks: {
                            color: '#cbd5e1',
                            maxRotation: 45,
                            minRotation: 45,
                            maxTicksLimit: 10
                        }
                    },
                    y: {
                        display: true,
                        grid: {
                            color: 'rgba(71, 85, 105, 0.3)'
                        },
                        ticks: {
                            color: '#cbd5e1',
                            callback: function(value) {
                                return '$' + value.toFixed(2);
                            }
                        }
                    }
                },
                interaction: {
                    mode: 'nearest',
                    axis: 'x',
                    intersect: false
                }
            }
        });
    }

    generateInsights() {
        // Use AI-generated insights from Gemini
        if (this.insights) {
            document.getElementById('momentumInsight').textContent =
                this.insights.momentum_insight || 'Analyzing momentum...';

            document.getElementById('volumeInsight').textContent =
                this.insights.volume_insight || 'Analyzing volume...';

            document.getElementById('volatilityInsight').textContent =
                this.insights.volatility_insight || 'Analyzing volatility...';
        }
    }

    generatePredictions() {
        // Use AI-generated predictions from Gemini
        if (this.predictions) {
            // Short-term prediction
            const shortTerm = this.predictions.short_term || {};
            document.getElementById('shortTermConfidence').textContent =
                `${shortTerm.confidence || 0}% Confidence`;
            document.getElementById('shortTermDirection').textContent =
                shortTerm.direction || 'Analyzing...';
            document.getElementById('shortTermPrediction').textContent =
                shortTerm.prediction || 'Generating prediction...';

            // Medium-term prediction
            const mediumTerm = this.predictions.medium_term || {};
            document.getElementById('mediumTermConfidence').textContent =
                `${mediumTerm.confidence || 0}% Confidence`;
            document.getElementById('mediumTermDirection').textContent =
                mediumTerm.direction || 'Analyzing...';
            document.getElementById('mediumTermPrediction').textContent =
                mediumTerm.prediction || 'Generating prediction...';

            // Risk assessment
            const risk = this.predictions.risk_assessment || {};
            document.getElementById('riskLevel').textContent =
                risk.level || 'UNKNOWN';
            document.getElementById('riskDirection').textContent =
                risk.icon || '⚠️';
            document.getElementById('riskAssessment').textContent =
                risk.assessment || 'Evaluating risk...';
        }
    }

    formatNumber(num) {
        if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
        if (num >= 1e6) return (num / 1e6).toFixed(2) + 'M';
        if (num >= 1e3) return (num / 1e3).toFixed(2) + 'K';
        return num.toString();
    }

    async refresh() {
        console.log('Refreshing data...');
        await this.fetchData();
        this.updateUI();
        this.chart.data.labels = this.historicalData.map(d => d.date);
        this.chart.data.datasets[0].data = this.historicalData.map(d => d.price);
        this.chart.update();
        this.generateInsights();
        this.generatePredictions();
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new IrenDashboard();
});
