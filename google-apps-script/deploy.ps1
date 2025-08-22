# PowerShell deployment script for Google Apps Script
# deploy.ps1

Write-Host "🚀 Deploying to Google Apps Script..." -ForegroundColor Green

# Check if clasp is installed
try {
    clasp --version | Out-Null
} catch {
    Write-Host "❌ Google Apps Script CLI (clasp) not found!" -ForegroundColor Red
    Write-Host "Install it with: npm install -g @google/clasp" -ForegroundColor Yellow
    exit 1
}

# Check if logged in
try {
    clasp status | Out-Null
} catch {
    Write-Host "❌ Not logged in to Google Apps Script" -ForegroundColor Red
    Write-Host "Run: clasp login" -ForegroundColor Yellow
    exit 1
}

# Pull latest from Google Apps Script
Write-Host "📥 Pulling latest from Google Apps Script..." -ForegroundColor Cyan
clasp pull --force

# Push local changes
Write-Host "📤 Pushing local changes..." -ForegroundColor Cyan
clasp push --force

# Deploy new version
Write-Host "🚀 Creating new deployment..." -ForegroundColor Cyan
$deployment = clasp deploy
Write-Host $deployment -ForegroundColor White

# Open project in browser
Write-Host "📱 Opening project in browser..." -ForegroundColor Cyan
clasp open

Write-Host "✅ Deployment complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Go to the Apps Script editor" -ForegroundColor White
Write-Host "2. Set up triggers for checkTradingAlerts() to run every 5 minutes" -ForegroundColor White
Write-Host "3. Configure your email and spreadsheet settings in trading-alerts.js" -ForegroundColor White
Write-Host "4. Test the alerts with the testAlerts() function" -ForegroundColor White
