#!/bin/bash
# deploy.sh - Deploy updates to Google Apps Script

echo "🚀 Deploying to Google Apps Script..."

# Check if clasp is installed
if ! command -v clasp &> /dev/null; then
    echo "❌ Google Apps Script CLI (clasp) not found!"
    echo "Install it with: npm install -g @google/clasp"
    exit 1
fi

# Check if logged in
if ! clasp status &> /dev/null; then
    echo "❌ Not logged in to Google Apps Script"
    echo "Run: clasp login"
    exit 1
fi

# Pull latest from Google Apps Script (in case of changes)
echo "📥 Pulling latest from Google Apps Script..."
clasp pull --force

# Push local changes
echo "📤 Pushing local changes..."
clasp push --force

# Deploy new version
echo "🚀 Creating new deployment..."
DEPLOYMENT=$(clasp deploy)
echo "$DEPLOYMENT"

# Get the deployment URL
echo "📱 Opening project in browser..."
clasp open

echo "✅ Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Go to the Apps Script editor"
echo "2. Set up triggers for checkTradingAlerts() to run every 5 minutes"
echo "3. Configure your email and spreadsheet settings in trading-alerts.js"
echo "4. Test the alerts with the testAlerts() function"
