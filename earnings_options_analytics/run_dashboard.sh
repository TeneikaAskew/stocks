#!/bin/bash
# Launcher script for Earnings Options Analytics Dashboard

echo "=========================================="
echo "  Earnings Options Analytics Dashboard"
echo "=========================================="
echo ""

# Check if streamlit is installed
if ! command -v streamlit &> /dev/null; then
    echo "⚠️  Streamlit not found. Installing dependencies..."
    pip install -r requirements.txt
fi

# Check if data exists
if [ ! -d "outputs/csv_reports" ] || [ -z "$(ls -A outputs/csv_reports 2>/dev/null)" ]; then
    echo "⚠️  No analysis data found."
    echo "📊 Running analysis first..."
    python earnings_options_analytics.py --export-csv --export-charts
    echo ""
fi

echo "🚀 Starting dashboard..."
echo "📊 Dashboard will open in your browser at http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop the dashboard"
echo ""

# Launch streamlit
streamlit run dashboard_app.py
