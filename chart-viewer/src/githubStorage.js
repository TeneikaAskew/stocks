// GitHub Storage - Save and load trades from GitHub repository

class GitHubStorage {
    constructor() {
        this.owner = CONFIG.GITHUB_OWNER;
        this.repo = CONFIG.GITHUB_REPO;
        this.token = CONFIG.GITHUB_TOKEN;
        this.branch = CONFIG.GITHUB_BRANCH || 'main';
        this.tradesPath = 'chart-viewer/data/trades.json';
        this.apiBase = 'https://api.github.com';
    }

    /**
     * Check if GitHub storage is enabled and configured
     */
    isEnabled() {
        return !CONFIG.USE_LOCAL_API && this.token && this.owner && this.repo;
    }

    /**
     * Load trades from GitHub repository
     */
    async loadTrades() {
        if (!this.isEnabled()) {
            console.log('[GitHubStorage] Not enabled, using localStorage');
            return null;
        }

        try {
            console.log('[GitHubStorage] Loading trades from GitHub...');
            const url = `${this.apiBase}/repos/${this.owner}/${this.repo}/contents/${this.tradesPath}?ref=${this.branch}`;

            const response = await fetch(url, {
                headers: {
                    'Authorization': `token ${this.token}`,
                    'Accept': 'application/vnd.github.v3+json',
                },
            });

            if (response.status === 404) {
                // File doesn't exist yet - that's okay for first time
                console.log('[GitHubStorage] Trades file does not exist yet');
                return [];
            }

            if (!response.ok) {
                throw new Error(`GitHub API error: ${response.status} ${response.statusText}`);
            }

            const data = await response.json();

            // Decode base64 content
            const content = atob(data.content);
            const trades = JSON.parse(content);

            console.log(`[GitHubStorage] Loaded ${trades.length} trades from GitHub`);
            return trades;
        } catch (error) {
            console.error('[GitHubStorage] Error loading trades:', error);
            Utils.notify('Error loading trades from GitHub', 'error');
            return null;
        }
    }

    /**
     * Save trades to GitHub repository
     */
    async saveTrades(trades) {
        if (!this.isEnabled()) {
            console.log('[GitHubStorage] Not enabled, using localStorage');
            return false;
        }

        try {
            console.log(`[GitHubStorage] Saving ${trades.length} trades to GitHub...`);

            // First, get the current file SHA (required for updates)
            const getUrl = `${this.apiBase}/repos/${this.owner}/${this.repo}/contents/${this.tradesPath}?ref=${this.branch}`;

            let sha = null;
            const getResponse = await fetch(getUrl, {
                headers: {
                    'Authorization': `token ${this.token}`,
                    'Accept': 'application/vnd.github.v3+json',
                },
            });

            if (getResponse.ok) {
                const fileData = await getResponse.json();
                sha = fileData.sha;
            }

            // Prepare the content
            const content = JSON.stringify(trades, null, 2);
            const contentBase64 = btoa(content);

            // Create or update the file
            const putUrl = `${this.apiBase}/repos/${this.owner}/${this.repo}/contents/${this.tradesPath}`;

            const body = {
                message: `update: save ${trades.length} trades`,
                content: contentBase64,
                branch: this.branch,
            };

            if (sha) {
                body.sha = sha; // Required for updates
            }

            const putResponse = await fetch(putUrl, {
                method: 'PUT',
                headers: {
                    'Authorization': `token ${this.token}`,
                    'Accept': 'application/vnd.github.v3+json',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(body),
            });

            if (!putResponse.ok) {
                const errorData = await putResponse.json();
                throw new Error(`GitHub API error: ${putResponse.status} - ${errorData.message}`);
            }

            console.log('[GitHubStorage] Trades saved successfully to GitHub');
            Utils.notify('Trades saved to GitHub', 'success');
            return true;
        } catch (error) {
            console.error('[GitHubStorage] Error saving trades:', error);
            Utils.notify(`Error saving trades to GitHub: ${error.message}`, 'error');
            return false;
        }
    }

    /**
     * Export trades as CSV
     */
    exportTradesAsCSV(trades) {
        const headers = [
            'ID',
            'Ticker',
            'Option Type',
            'Entry Time',
            'Entry Price',
            'Exit Time',
            'Exit Price',
            'Exit Reason',
            'P&L',
            'P&L %',
            'Status',
            'Notes',
            'Tags',
        ];

        const rows = [headers.join(',')];

        for (const trade of trades) {
            const row = [
                trade.id,
                trade.ticker,
                trade.optionType,
                Utils.formatDateTime(trade.entryTime),
                trade.entryPrice,
                trade.exitTime ? Utils.formatDateTime(trade.exitTime) : '',
                trade.exitPrice || '',
                trade.exitReason || '',
                trade.pnl || '',
                trade.pnlPercent || '',
                trade.status || 'active',
                `"${(trade.notes || '').replace(/"/g, '""')}"`, // Escape quotes
                `"${(trade.tags || []).join(';')}"`,
            ];
            rows.push(row.join(','));
        }

        return rows.join('\n');
    }
}
