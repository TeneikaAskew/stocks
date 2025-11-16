#!/bin/bash
# Start the Trading Chart Viewer locally

echo "================================================"
echo "  Trading Chart Viewer - Local Development"
echo "================================================"
echo ""

# Check if Python dependencies are installed
python3 -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  Flask not found. Installing dependencies..."
    pip3 install -r requirements.txt
    echo ""
fi

# Start the API server in background
echo "🚀 Starting API server on http://localhost:5000..."
python3 api.py &
API_PID=$!

# Wait for API to start
sleep 2

# Start HTTP server for frontend
echo "🌐 Starting frontend server on http://localhost:8080..."
echo ""
echo "================================================"
echo "  Chart Viewer is running!"
echo "================================================"
echo ""
echo "  📊 Open: http://localhost:8080"
echo "  📡 API:  http://localhost:5000/api/health"
echo ""
echo "  Press Ctrl+C to stop"
echo ""

# Start simple HTTP server
python3 -m http.server 8080

# Cleanup on exit
trap "kill $API_PID 2>/dev/null" EXIT
