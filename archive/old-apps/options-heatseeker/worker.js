/**
 * Cloudflare Worker - Alpha Vantage Options Data Proxy
 *
 * This worker acts as a secure proxy between the Options Heatseeker app
 * and the Alpha Vantage API, keeping the API key hidden from users.
 *
 * Deploy to Cloudflare Workers and set ALPHA_VANTAGE_API_KEY as a secret.
 */

export default {
  async fetch(request, env) {
    // Enable CORS for GitHub Pages
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };

    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    // Only allow GET requests
    if (request.method !== 'GET') {
      return new Response('Method not allowed', {
        status: 405,
        headers: corsHeaders
      });
    }

    try {
      const url = new URL(request.url);
      const symbol = url.searchParams.get('symbol');
      const date = url.searchParams.get('date');

      // Validate inputs
      if (!symbol || !date) {
        return new Response(
          JSON.stringify({
            error: 'Missing required parameters',
            message: 'Both symbol and date are required',
            usage: '?symbol=SPY&date=2024-01-15'
          }),
          {
            status: 400,
            headers: {
              'Content-Type': 'application/json',
              ...corsHeaders
            }
          }
        );
      }

      // Validate symbol format
      const validSymbols = ['SPY', 'IWM', 'QQQ'];
      if (!validSymbols.includes(symbol.toUpperCase())) {
        return new Response(
          JSON.stringify({
            error: 'Invalid symbol',
            message: `Symbol must be one of: ${validSymbols.join(', ')}`,
            provided: symbol
          }),
          {
            status: 400,
            headers: {
              'Content-Type': 'application/json',
              ...corsHeaders
            }
          }
        );
      }

      // Validate date format (YYYY-MM-DD)
      const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
      if (!dateRegex.test(date)) {
        return new Response(
          JSON.stringify({
            error: 'Invalid date format',
            message: 'Date must be in YYYY-MM-DD format',
            provided: date
          }),
          {
            status: 400,
            headers: {
              'Content-Type': 'application/json',
              ...corsHeaders
            }
          }
        );
      }

      // Build Alpha Vantage API URL
      const avUrl = new URL('https://www.alphavantage.co/query');
      avUrl.searchParams.set('function', 'HISTORICAL_OPTIONS');
      avUrl.searchParams.set('symbol', symbol.toUpperCase());
      avUrl.searchParams.set('date', date);
      avUrl.searchParams.set('apikey', env.ALPHA_VANTAGE_API_KEY);

      console.log(`Fetching options data for ${symbol} on ${date}`);

      // Call Alpha Vantage API
      const avResponse = await fetch(avUrl.toString(), {
        headers: {
          'User-Agent': 'Options-Heatseeker/1.0'
        }
      });

      if (!avResponse.ok) {
        throw new Error(`Alpha Vantage API error: ${avResponse.status}`);
      }

      const data = await avResponse.json();

      // Check for API errors
      if (data['Error Message']) {
        return new Response(
          JSON.stringify({
            error: 'Alpha Vantage API Error',
            message: data['Error Message']
          }),
          {
            status: 400,
            headers: {
              'Content-Type': 'application/json',
              ...corsHeaders
            }
          }
        );
      }

      if (data['Note']) {
        // Rate limit hit
        return new Response(
          JSON.stringify({
            error: 'Rate Limit Exceeded',
            message: data['Note'],
            retry_after: 60
          }),
          {
            status: 429,
            headers: {
              'Content-Type': 'application/json',
              'Retry-After': '60',
              ...corsHeaders
            }
          }
        );
      }

      // Transform the response to match our expected format
      const transformedData = {
        ticker: symbol.toUpperCase(),
        date: date,
        snapshot_timestamp: new Date().toISOString(),
        options: data.data || [],
        metadata: {
          source: 'Alpha Vantage',
          fetched_at: new Date().toISOString()
        }
      };

      // Return successful response with caching
      return new Response(
        JSON.stringify(transformedData),
        {
          status: 200,
          headers: {
            'Content-Type': 'application/json',
            'Cache-Control': 'public, max-age=3600', // Cache for 1 hour
            ...corsHeaders
          }
        }
      );

    } catch (error) {
      console.error('Worker error:', error);

      return new Response(
        JSON.stringify({
          error: 'Internal Server Error',
          message: error.message || 'An unexpected error occurred'
        }),
        {
          status: 500,
          headers: {
            'Content-Type': 'application/json',
            ...corsHeaders
          }
        }
      );
    }
  }
};
