# Google Apps Script Integration

This folder contains the integration setup for Google Apps Script project:
**Project ID**: `1Qa8BmLGqRC2vp1lJtBWyxlXJUbD69rbTgcHkSWAxGxlKYKIHFwvrQaHy`

## Setup Instructions

### 1. Install Google Apps Script CLI (clasp)
```bash
npm install -g @google/clasp
```

### 2. Login to Google Account
```bash
clasp login
```

### 3. Clone the existing project
```bash
cd google-apps-script
clasp clone 1Qa8BmLGqRC2vp1lJtBWyxlXJUbD69rbTgcHkSWAxGxlKYKIHFwvrQaHy
```

### 4. Pull current files from Google Apps Script
```bash
clasp pull
```

### 5. Push updates to Google Apps Script
```bash
clasp push
```

### 6. Deploy the project
```bash
clasp deploy
```

## Files Structure
- `setup.js` - Initial setup and configuration
- `trading-alerts.js` - Trading alerts functionality
- `data-sync.js` - Data synchronization with external APIs
- `appsscript.json` - Project configuration

## Usage
Run `npm run setup` to initialize the Google Apps Script integration.
