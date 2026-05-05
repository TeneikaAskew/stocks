// ===== Utility Functions =====

const Utils = {
    /**
     * Format number as currency
     */
    formatCurrency(value, decimals = 1) {
        if (value === null || value === undefined) return '-';

        const absValue = Math.abs(value);
        const sign = value < 0 ? '-' : '';

        if (absValue >= 1e9) {
            return `${sign}$${(absValue / 1e9).toFixed(decimals)}B`;
        } else if (absValue >= 1e6) {
            return `${sign}$${(absValue / 1e6).toFixed(decimals)}M`;
        } else if (absValue >= 1e3) {
            return `${sign}$${(absValue / 1e3).toFixed(decimals)}K`;
        } else {
            return `${sign}$${absValue.toFixed(decimals)}`;
        }
    },

    /**
     * Format number as percentage
     */
    formatPercent(value, decimals = 2) {
        if (value === null || value === undefined) return '-';
        return `${(value * 100).toFixed(decimals)}%`;
    },

    /**
     * Format number with commas
     */
    formatNumber(value, decimals = 0) {
        if (value === null || value === undefined) return '-';
        return value.toFixed(decimals).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    },

    /**
     * Format date
     */
    formatDate(date, format = 'YYYY-MM-DD') {
        if (!date) return '-';

        // Handle YYYYMMDD string format
        let d;
        if (typeof date === 'string' && date.length === 8 && /^\d{8}$/.test(date)) {
            const year = date.substring(0, 4);
            const month = date.substring(4, 6);
            const day = date.substring(6, 8);
            d = new Date(`${year}-${month}-${day}`);
        } else {
            d = new Date(date);
        }

        if (isNaN(d.getTime())) return '-';

        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');

        if (format === 'YYYY-MM-DD') {
            return `${year}-${month}-${day}`;
        } else if (format === 'MMM DD' || format === 'MMM DD, YYYY') {
            const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
            if (format === 'MMM DD') {
                return `${monthNames[d.getMonth()]} ${day}`;
            }
            return `${monthNames[d.getMonth()]} ${day}, ${year}`;
        }
        return date.toString();
    },

    /**
     * Calculate days to expiration
     */
    calculateDTE(expirationDate, fromDate = new Date()) {
        const exp = new Date(expirationDate);
        const from = new Date(fromDate);
        const diffTime = exp - from;
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        return Math.max(0, diffDays);
    },

    /**
     * Parse parquet filename to extract date
     */
    parseDateFromFilename(filename) {
        // Format: {ticker}_av_options_YYYYMMDD.parquet
        const match = filename.match(/(\d{8})/);
        if (match) {
            const dateStr = match[1];
            const year = dateStr.substring(0, 4);
            const month = dateStr.substring(4, 6);
            const day = dateStr.substring(6, 8);
            return `${year}-${month}-${day}`;
        }
        return null;
    },

    /**
     * Generate color gradient between two colors
     */
    getColorGradient(value, minValue, maxValue, startColor, endColor) {
        if (maxValue === minValue) return startColor;

        const ratio = Math.abs((value - minValue) / (maxValue - minValue));
        const start = this.hexToRgb(startColor);
        const end = this.hexToRgb(endColor);

        const r = Math.round(start.r + ratio * (end.r - start.r));
        const g = Math.round(start.g + ratio * (end.g - start.g));
        const b = Math.round(start.b + ratio * (end.b - start.b));

        return `rgb(${r}, ${g}, ${b})`;
    },

    /**
     * Convert hex color to RGB
     */
    hexToRgb(hex) {
        const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        } : { r: 0, g: 0, b: 0 };
    },

    /**
     * Debounce function
     */
    debounce(func, delay) {
        let timeoutId;
        return function (...args) {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => func.apply(this, args), delay);
        };
    },

    /**
     * Throttle function
     */
    throttle(func, limit) {
        let inThrottle;
        return function (...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },

    /**
     * Deep clone object
     */
    deepClone(obj) {
        return JSON.parse(JSON.stringify(obj));
    },

    /**
     * Sort array of objects by key
     */
    sortBy(array, key, ascending = true) {
        return array.sort((a, b) => {
            const aVal = a[key];
            const bVal = b[key];
            if (aVal < bVal) return ascending ? -1 : 1;
            if (aVal > bVal) return ascending ? 1 : -1;
            return 0;
        });
    },

    /**
     * Group array by key
     */
    groupBy(array, key) {
        return array.reduce((result, item) => {
            const groupKey = item[key];
            if (!result[groupKey]) {
                result[groupKey] = [];
            }
            result[groupKey].push(item);
            return result;
        }, {});
    },

    /**
     * Calculate sum of array values
     */
    sum(array, key = null) {
        if (key) {
            return array.reduce((sum, item) => sum + (item[key] || 0), 0);
        }
        return array.reduce((sum, val) => sum + (val || 0), 0);
    },

    /**
     * Calculate average of array values
     */
    average(array, key = null) {
        if (array.length === 0) return 0;
        return this.sum(array, key) / array.length;
    },

    /**
     * Find min/max values in array
     */
    minMax(array, key = null) {
        if (array.length === 0) return { min: 0, max: 0 };

        const values = key ? array.map(item => item[key]) : array;
        return {
            min: Math.min(...values),
            max: Math.max(...values)
        };
    },

    /**
     * Check if value is within range
     */
    inRange(value, min, max) {
        return value >= min && value <= max;
    },

    /**
     * Clamp value between min and max
     */
    clamp(value, min, max) {
        return Math.min(Math.max(value, min), max);
    },

    /**
     * Show loading overlay
     */
    showLoading(message = 'Loading data...') {
        const overlay = document.getElementById('loading-overlay');
        const text = overlay.querySelector('p');
        if (text) text.textContent = message;
        overlay.classList.remove('hidden');
    },

    /**
     * Hide loading overlay
     */
    hideLoading() {
        const overlay = document.getElementById('loading-overlay');
        overlay.classList.add('hidden');
    },

    /**
     * Show error message
     */
    showError(message) {
        alert(`Error: ${message}`);
        console.error(message);
    },

    /**
     * Generate unique ID
     */
    generateId() {
        return `id_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    },

    /**
     * Download data as file
     */
    downloadFile(data, filename, mimeType = 'text/plain') {
        const blob = new Blob([data], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    },

    /**
     * Copy text to clipboard
     */
    async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (err) {
            console.error('Failed to copy:', err);
            return false;
        }
    },

    /**
     * Get query parameters from URL
     */
    getQueryParams() {
        const params = new URLSearchParams(window.location.search);
        const result = {};
        for (const [key, value] of params) {
            result[key] = value;
        }
        return result;
    },

    /**
     * Update URL with query parameters
     */
    updateQueryParams(params) {
        const url = new URL(window.location);
        Object.keys(params).forEach(key => {
            if (params[key] !== null && params[key] !== undefined) {
                url.searchParams.set(key, params[key]);
            } else {
                url.searchParams.delete(key);
            }
        });
        window.history.pushState({}, '', url);
    }
};

// Freeze Utils to prevent modifications
Object.freeze(Utils);
