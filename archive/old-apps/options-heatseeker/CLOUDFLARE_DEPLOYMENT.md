# Cloudflare Worker Deployment Guide

This guide shows how to deploy the Alpha Vantage API proxy to Cloudflare Workers.

## Prerequisites

- Cloudflare account (free tier works)
- Node.js installed locally
- Your Alpha Vantage API key

## One-Time Setup

### 1. Install Wrangler CLI

```bash
npm install -g wrangler
```

### 2. Login to Cloudflare

```bash
wrangler login
```

This will open a browser window to authenticate.

### 3. Create wrangler.toml Configuration

Create a file named `wrangler.toml` in the `options-heatseeker/` directory:

```toml
name = "options-heatseeker-api"
main = "worker.js"
compatibility_date = "2024-01-15"

[vars]
# No public variables needed
```

## Deployment Steps

### 1. Set the API Key as a Secret

From the `options-heatseeker/` directory:

```bash
wrangler secret put ALPHA_VANTAGE_API_KEY
```

When prompted, paste your Alpha Vantage API key (the same one from GitHub Secrets).

### 2. Deploy the Worker

```bash
wrangler deploy
```

You'll see output like:

```
✨  Built successfully!
✨  Successfully published your script to
 https://options-heatseeker-api.<your-subdomain>.workers.dev
```

### 3. Copy the Worker URL

Copy the URL that looks like:
```
https://options-heatseeker-api.<your-subdomain>.workers.dev
```

You'll need this for the next step.

### 4. Update config.js

Edit `options-heatseeker/js/config.js` and update the `API_ENDPOINT`:

```javascript
const CONFIG = {
    API_ENDPOINT: 'https://options-heatseeker-api.<your-subdomain>.workers.dev',
    // ... rest of config
};
```

### 5. Test the Worker

Test the API directly in your browser or with curl:

```bash
# Test with SPY data
curl "https://options-heatseeker-api.<your-subdomain>.workers.dev?symbol=SPY&date=2024-01-15"
```

You should see JSON response with options data.

## Update the Worker

To update the worker after making changes to `worker.js`:

```bash
cd options-heatseeker
wrangler deploy
```

Changes are live immediately (no git commit needed for the worker).

## Monitoring

View logs in real-time:

```bash
wrangler tail
```

Then use the app - you'll see requests logged.

## Cost

- **Free tier**: 100,000 requests/day
- **Paid tier**: $5/month for 10 million requests

For typical usage (a few users), free tier is more than enough.

## Troubleshooting

### "Error: No API key found"

Make sure you ran:
```bash
wrangler secret put ALPHA_VANTAGE_API_KEY
```

### "CORS error in browser"

The worker includes CORS headers for all origins. If you still see errors, check browser console for the exact error.

### "Rate limit exceeded"

Alpha Vantage free tier limits:
- 5 API calls per minute
- 500 API calls per day

The worker returns a 429 status with retry information when this happens.

## Security Notes

- ✅ API key is stored as a Cloudflare secret (encrypted)
- ✅ API key never exposed to users
- ✅ Worker validates all inputs before calling Alpha Vantage
- ✅ CORS headers restrict usage to your GitHub Pages domain (optional - can be configured)

## Alternative: Restrict to Your Domain Only

To only allow requests from your GitHub Pages site, edit `worker.js`:

```javascript
const corsHeaders = {
  'Access-Control-Allow-Origin': 'https://teneikaaskew.github.io',  // Your domain only
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};
```

Then redeploy:
```bash
wrangler deploy
```
