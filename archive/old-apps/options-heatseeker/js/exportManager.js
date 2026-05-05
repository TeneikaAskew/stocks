// ===== Export Manager =====

const ExportManager = {
    exportAsCSV(aggregatedStrikes, ticker, date) {
        if (!aggregatedStrikes || aggregatedStrikes.length === 0) {
            Utils.showError('No data to export');
            return;
        }

        // Create CSV header
        const headers = ['Strike', 'Net Gamma', 'Call OI', 'Put OI', 'Total OI', 'Net Delta', 'Net Vega'];
        const rows = [headers.join(',')];

        // Add data rows
        aggregatedStrikes.forEach(strike => {
            const row = [
                strike.strike,
                strike.net_gamma,
                strike.call_oi,
                strike.put_oi,
                strike.total_oi,
                strike.net_delta,
                strike.net_vega
            ];
            rows.push(row.join(','));
        });

        const csv = rows.join('\n');
        const filename = `${ticker}_strikes_${date}.csv`;

        Utils.downloadFile(csv, filename, 'text/csv');
    },

    exportAsPNG() {
        // TODO: Implement PNG export using canvas
        Utils.showError('PNG export coming soon');
    }
};

Object.freeze(ExportManager);
