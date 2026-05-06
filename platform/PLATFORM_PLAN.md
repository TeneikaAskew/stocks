# Unified Trading Education Platform

## Context

We have **4 separate vanilla JS web apps** that each solve a piece of the trading workflow but share no code, use different chart libraries (TradingView, D3.js, Chart.js), and have no unified navigation. Meanwhile, a powerful Python analysis engine (`lib/`, `scripts/analysis/`, `trade_analysis_pipeline.py`) produces reports, backtests, signals, and playbook cards that are only accessible via CLI. The goal is to merge everything into a single **production-grade React/TypeScript platform** where users can learn trading setups, run backtests, view live market data, analyze options flow (heatseeker), and journal trades — all powered by the existing Python backend.

**Reference platforms:** LuxAlgo (AI strategy search, no-code backtesting, equity curves) and TradrLab (natural language strategies, expert feedback, scenario plotting).

A key differentiator: **AI-powered quant/trader insights via Google Vertex AI (Gemini)**. Users can chat with an AI that acts as a Wall Street quant — reviewing trades, critiquing setups, explaining market structure, and providing institutional-grade feedback grounded in the user's own data (signals, backtests, playbook, options flow).

---

## Current Apps Being Merged

| App | Key Tech | Features | Status |
|-----|----------|----------|--------|
| **chart-viewer/** | TradingView Lightweight Charts | Candlestick charts, trade marking (entry/TP/SL), multi-TF (1/5/15/30/60), analytics panel, reference levels | Working |
| **options-heatseeker/** | D3.js + Cloudflare Workers | GEX/VEX heatmaps by strike, king nodes/gatekeepers/midpoints, Greeks calculator, ticker/date navigation | Working (live API) |
| **website/trading-dashboard.html** | Polygon.io REST | Live price, RSI/EMA/StochRSI/ATR, signal detection (CALL/PUT), sound alerts, trade history | Working |
| **success-report-site/** | Chart.js + Google Apps Script | 6-tab report: Overview, Multi-Day, Indicator Effectiveness, Earnings Timing, Strategy Performance, Top Plays | Dev mode only |

---

## Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Frontend | **Vite 6 + React 19 + TypeScript** | No SSR needed (private tool), fastest DX, lightest bundle |
| State | **Zustand** (client) + **TanStack Query v5** (server) | Minimal boilerplate, built-in caching/refetch |
| Styling | **Tailwind CSS 4** | Dark theme matching existing aesthetic, rapid iteration |
| Charts | **TradingView Lightweight Charts** (candlesticks) + **Recharts** (metrics) + **D3.js** (options heatmap) | Reuse existing chart-viewer + heatseeker code |
| Tables | **TanStack Table v8** | Sorting, filtering, virtual scrolling for 330K+ signals |
| Routing | **React Router v7** | Lazy-loaded routes for code splitting |
| AI | **Google Vertex AI (Gemini 2.0 Flash)** | Low-latency, GCP-native, existing service account ready |
| Backend | **FastAPI** wrapping existing `lib/` modules | Zero logic duplication — imports `lib/` directly |

---

## Project Location

New directory: **`/workspaces/stocks/platform/`**

---

## Route Structure

| Route | Page | Replaces | Core Features |
|-------|------|----------|---------------|
| `/` | Dashboard | New | Market status, today's signals, playbook quick-ref, backtest KPIs |
| `/live` | Live Market | `website/trading-dashboard.html` | Polygon.io polling, real-time indicators, signal detection, sound alerts |
| `/charts` | Chart Viewer | `chart-viewer/` | TradingView candlestick charts, trade marking, multi-TF, analytics panel |
| `/options` | Options Flow | `options-heatseeker/` | **D3.js GEX/VEX heatmaps, king nodes/gatekeepers/midpoints, Greeks, Net/Calls/Puts filter, date navigation, Cloudflare Worker API** |
| `/playbook` | Playbook | `reports/phase6_playbook_*.md` | 12 decision cards per ticker, interactive condition checklists |
| `/backtest` | Backtester | `data/backtest_results/` | Equity curves, trade table, metrics grid, run backtests on demand |
| `/reports` | Reports | `success-report-site/` | 6-tab report dashboard (Chart.js migrated to Recharts) |
| `/signals` | Signal Explorer | `data/signals/` | Browse 330K+ historical signals with filters |
| `/journal` | Trade Journal | Phase 7 + `trade_tracker` | Cloud SQL-backed CRUD (local JSON fallback), export to pipeline CSV |
| `/insights` | AI Insights | New | Chat with a quant/trader AI powered by Vertex AI Gemini, grounded in your data |

---

## FastAPI Backend (`platform/api/`)

Thin wrapper — imports directly from `lib/`, never duplicates analysis logic.

### Key Endpoints

| Endpoint | Method | Wraps |
|----------|--------|-------|
| `/api/market/data/{ticker}/{date}` | GET | Cloud SQL `market_data_intraday` (local parquet fallback) |
| `/api/market/dates/{ticker}` | GET | Cloud SQL `DISTINCT DATE(ts)` query (local parquet fallback) |
| `/api/market/reference/{ticker}/{date}` | GET | Cloud SQL `market_data_daily` prev-day OHLC (local parquet fallback) |
| `/api/backtest/results/{ticker}` | GET | Reads `data/backtest_results/backtest_{ticker}_*.csv` |
| `/api/backtest/run` | POST | `lib/backtest.py` BacktestEngine.run() |
| `/api/signals/{ticker}` | GET | Reads `data/signals/historical_{ticker}_*_signals.parquet` |
| `/api/playbook/{ticker}` | GET | Parses `reports/phase6_playbook_{ticker}.md` into JSON cards |
| `/api/reports/phases/{phase}/{ticker}` | GET | Reads `reports/phase{N}_*_{ticker}.md` |
| `/api/reports/trade-analysis/{ticker}` | GET | Reads `data/signals/{ticker}_trade_analysis_report.md` |
| `/api/options/{ticker}/{date}` | GET | Alpha Vantage proxy (replaces Cloudflare Worker) + local parquet fallback |
| `/api/options/dates/{ticker}` | GET | Available options dates from `data/index.json` or filesystem |
| `/api/analysis/similar-trades/{ticker}` | GET | Reads `data/signals/{ticker}_similar_trades_pipeline.parquet` |
| `/api/analysis/criteria/{ticker}` | GET | Reads `data/signals/{ticker}_criteria_effectiveness.parquet` |
| `/api/analysis/pipeline/{ticker}` | POST | Runs `trade_analysis_pipeline.py` TradeAnalysisPipeline |
| `/api/insights/chat` | POST | Vertex AI Gemini chat with trading context injection |
| `/api/insights/review-trade` | POST | AI critique of a specific trade (entry/exit/setup quality) |
| `/api/insights/market-brief/{ticker}` | GET | AI-generated market structure summary for today |
| `/api/insights/strategy-feedback` | POST | AI feedback on a strategy's backtest results |

---

## Options Flow Page Detail (Heatseeker Integration)

The options-heatseeker is one of the most sophisticated apps and requires careful porting.

### What Gets Ported

| Source File | Target | What It Does |
|-------------|--------|-------------|
| `options-heatseeker/js/greeksCalculator.js` | `src/lib/greeksCalculator.ts` | GEX/VEX calculation, zero gamma level, max pain, implied move |
| `options-heatseeker/js/nodeAnalyzer.js` | `src/lib/nodeAnalyzer.ts` | King node, gatekeeper, midpoint detection from exposure data |
| `options-heatseeker/js/heatmapRenderer.js` | `src/components/charts/OptionsHeatmap.tsx` | D3.js strike-level bar rendering, color scales (green→gold positive, blue→purple negative), current price marker |
| `options-heatseeker/js/tableRenderer.js` | Merged into OptionsHeatmap | Per-cell coloring, node highlight badges |
| `options-heatseeker/js/filterManager.js` | `src/components/options/OptionsFilters.tsx` | GEX/VEX metric toggle, Net/Calls/Puts filter, DTE ranges |
| `options-heatseeker/js/dataLoader.js` | `src/hooks/useOptionsData.ts` | Cloudflare Worker fetch with caching (1hr TTL, max 50 datasets) |
| `options-heatseeker/worker.js` | **Absorbed into FastAPI** (`api/options.py`) | API proxy moves from Cloudflare to GCP — same logic, consolidated vendor |

### OptionsFlowPage Layout

```
+---------------------------------------------------+
| Header: [GEX] [VEX]  SPY/QQQ/IWM  Date: [picker] |
|         Price: $XXX.XX (+0.XX%)  [Net|Calls|Puts] |
+---------------------------------------------------+
|                                                     |
|  D3.js Heatmap (strike x exposure bars)            |
|  - Green/Gold bars = positive gamma/vanna           |
|  - Blue/Purple bars = negative gamma/vanna          |
|  - Red line = current price                         |
|  - Star badges = king nodes                         |
|  - Shield badges = gatekeepers                      |
|  - Diamond badges = midpoints                       |
|                                                     |
+---------------------------------------------------+
| Metrics: Zero Gamma | Max Pain | Implied Move | GEX|
+---------------------------------------------------+
| Options Chain Table (optional expand)               |
|  Strike | Call OI | Put OI | GEX | Delta | Gamma  |
+---------------------------------------------------+
```

### Cloudflare Worker → GCP Migration ✅ DONE (2026-05-04)

The Cloudflare Worker (`options-heatseeker/worker.js`, archived to
`archive/old-apps/options-heatseeker/`) was a simple API proxy that:
- Validated inputs (ticker: SPY/IWM/QQQ, date: YYYY-MM-DD format)
- Forwarded to Alpha Vantage options API (hid API key)
- Added CORS headers + 1-hour HTTP cache
- Returned standardized `{ ticker, date, options[], metadata }` response

It is now absorbed into FastAPI as two endpoints in
`platform/api/routers/options.py`:
- `GET /api/options/{ticker}/{date_str}` — Cloud SQL EOD reader (primary)
- `GET /api/options/live/{ticker}/{date_str}` — AlphaVantage live proxy
  (fallback for today's intraday chain before the 9 PM EOD fetcher runs)

Both share the same response shape (`_av_to_contracts` mirrors
`_df_to_contracts`). API key resolved from `AV_API_KEY` /
`ALPHA_VANTAGE_API_KEY` env (Secret Manager-injected). The React page
(`OptionsFlowPage.tsx`) calls Cloud SQL first and falls back to live on
404 — no other call sites reference Cloudflare.

**Decommission step (run by user):** `wrangler delete options-heatseeker-api`

### D3.js Integration Strategy

D3.js is kept (not replaced with React) because the heatmap uses direct DOM manipulation for:
- Per-cell color interpolation based on exposure magnitude
- SVG bar rendering with bidirectional extension (left=negative, right=positive)
- Node badge overlays at specific strike rows
- Responsive resizing based on strike range

Implementation: React `useRef` + `useEffect` pattern:
```typescript
// OptionsHeatmap.tsx
const svgRef = useRef<SVGSVGElement>(null);

useEffect(() => {
  if (!svgRef.current || !data) return;
  // D3 renders into the ref'd SVG element
  renderHeatmap(svgRef.current, data, nodes, metric, filter);
}, [data, nodes, metric, filter]);
```

---

## AI Quant/Trader Insights (Vertex AI Gemini)

### Concept

An `/insights` page that gives users access to a **conversational AI acting as a Wall Street quant/institutional trader**. Not generic ChatGPT — it's grounded in the user's own data: their trades, their backtests, their signals, their playbook. Every response is contextualized with real numbers from the platform.

### Architecture

```
Frontend (React)                    FastAPI                         Vertex AI
┌─────────────┐     POST /api/     ┌──────────────┐    Gemini API  ┌───────────┐
│ Chat UI     │────insights/chat──→│ Context       │──────────────→│ Gemini    │
│ (streaming) │                    │ Builder       │               │ 2.0 Flash │
│             │◀───SSE stream──────│ + Prompt      │◀──────────────│           │
└─────────────┘                    │ Templates     │               └───────────┘
                                   └──────┬───────┘
                                          │ reads
                                   ┌──────▼───────┐
                                   │ User's Data  │
                                   │ - signals/   │
                                   │ - backtests/ │
                                   │ - playbook   │
                                   │ - journal    │
                                   └──────────────┘
```

### GCP Setup Required

- Enable Vertex AI API on project `adept-mountain-474619-d4`
- Add `roles/aiplatform.user` to existing service account `trading-runner@...`
- Install `google-cloud-aiplatform` Python package
- No new credentials needed — uses existing `.gcp-key.json`

### Prompt Templates (Real Examples)

Each conversation mode uses a **system prompt persona** + **data context injection**:

**1. Trade Review Mode** (`/api/insights/review-trade`)
```
You are a senior quantitative trader at a top-tier prop desk reviewing a junior
trader's work. Be direct, specific, and constructive. Reference the actual numbers.

TRADE CONTEXT:
- Ticker: {ticker}, Direction: {direction}
- Entry: {entry_time} @ ${entry_price} | Exit: {exit_time} @ ${exit_price}
- Return: {return_pct}% | Duration: {duration_min} minutes
- Entry RSI: {rsi} | VWAP deviation: {vwap_dev}% | Volume ratio: {rvol}
- Signal score at entry: {signal_score}/10
- Similar historical trades (win rate): {similar_win_rate}%

PLAYBOOK ALIGNMENT:
- Matched playbook card: {playbook_card_name}
- Conditions met: {conditions_met}/{conditions_total}
- Conditions missed: {missed_conditions}

Review this trade: Was the entry well-timed? Was the exit optimal or premature?
What would you have done differently? Grade it A-F with specific reasoning.
```

**2. Strategy Feedback Mode** (`/api/insights/strategy-feedback`)
```
You are a quantitative portfolio manager reviewing a retail trader's systematic
strategy. Analyze it as if evaluating an allocation decision. Be rigorous.

STRATEGY BACKTEST RESULTS:
- Ticker: {ticker} | Period: {start_date} to {end_date}
- Total trades: {total_trades} | Win rate: {win_rate}%
- Profit factor: {pf} | Sharpe: {sharpe} | Max drawdown: {max_dd}%
- Avg winner: {avg_win}% | Avg loser: {avg_loss}%
- Best trade: {best}% | Worst trade: {worst}%

TOP PERFORMING CONDITIONS:
{criteria_effectiveness_table}

Evaluate: Is this strategy tradeable? What are the risks? How would you improve
the entry criteria? Would you allocate capital to this?
```

**3. Market Structure Mode** (`/api/insights/market-brief/{ticker}`)
```
You are a derivatives market maker explaining the current market structure to a
trader on your desk. Be precise about levels, flows, and what matters today.

CURRENT MARKET DATA:
- {ticker} last: ${last} | Day range: ${low}-${high}
- Options GEX: {total_gex} | Zero gamma: ${zero_gamma}
- Max pain: ${max_pain} | Implied move: ±{implied_move}%
- King node: ${king_strike} | Gatekeepers: ${gk_low}-${gk_high}
- RSI(14): {rsi} | VWAP: ${vwap} | ATR: ${atr}
- Today's signals: {signal_count} ({call_count} CALL / {put_count} PUT)

Explain: What's the market structure telling us? Where are the key levels?
What setups should we be watching for today?
```

**4. Open Chat Mode** (`/api/insights/chat`)
```
You are a senior quant/trader with 20 years of institutional experience across
equities, options, and systematic strategies. You're mentoring a developing trader.

Available context the user may ask about:
- Their trade journal and historical performance
- Backtest results for IWM/SPY/QQQ strategies
- 330K+ historical signals with indicator data
- Options flow (GEX/VEX) analysis
- 12 playbook decision cards per ticker

Respond conversationally but always tie advice back to their actual data when
possible. Don't give generic advice — reference their specific metrics, trades,
and patterns. Challenge their assumptions constructively.
```

### InsightsPage Layout

```
+---------------------------------------------------+
| Mode: [Trade Review] [Strategy] [Market] [Chat]   |
+---------------------------------------------------+
| ┌─────────────────────────────────────────────┐   |
| │ AI: "Looking at your IWM CALL from 9:35    │   |
| │ on 2024-10-15 — your entry was solid, RSI  │   |
| │ at 42 with RVOL 1.8x confirms momentum.    │   |
| │ However, you exited at +1.2% when similar  │   |
| │ trades historically run +2.1% median. The  │   |
| │ playbook 'Momentum Breakout' card says hold │   |
| │ until VWAP rejection, which didn't happen  │   |
| │ for another 4 minutes. Grade: B-"          │   |
| └─────────────────────────────────────────────┘   |
| ┌─────────────────────────────────────────────┐   |
| │ You: "What about the options flow that day?"│   |
| └─────────────────────────────────────────────┘   |
| ┌─────────────────────────────────────────────┐   |
| │ AI: "GEX was net negative at -$2.1M with   │   |
| │ the zero gamma level at $218.50 — you       │   |
| │ entered below it, which means dealer        │   |
| │ hedging was amplifying moves in your        │   |
| │ direction. Good structural read. The king   │   |
| │ node was at $220 strike with $4.2M GEX,    │   |
| │ acting as a magnet..."                      │   |
| └─────────────────────────────────────────────┘   |
| [Type a message...                         ] [Send]|
+---------------------------------------------------+
| Quick actions: [Review last trade] [Today's brief] |
+---------------------------------------------------+
```

### Streaming Implementation

```typescript
// useInsightsChat.ts
const sendMessage = async (message: string, mode: string, context: TradeContext) => {
  const response = await fetch('/api/insights/chat', {
    method: 'POST',
    body: JSON.stringify({ message, mode, context }),
  });

  // SSE streaming for real-time token display
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    appendToResponse(decoder.decode(value));
  }
};
```

```python
# api/insights.py (FastAPI)
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel
from fastapi.responses import StreamingResponse

model = GenerativeModel("gemini-2.0-flash")

@router.post("/api/insights/chat")
async def chat(request: ChatRequest):
    # Build context from user's data
    context = await build_context(request.mode, request.context)
    prompt = PROMPT_TEMPLATES[request.mode].format(**context)

    async def generate():
        response = model.generate_content(
            [prompt, request.message],
            stream=True
        )
        for chunk in response:
            yield chunk.text

    return StreamingResponse(generate(), media_type="text/plain")
```

---

## Comparison Testing & Old App Cleanup

### Strategy: Test First, Clean After

Old apps (`chart-viewer/`, `options-heatseeker/`, `website/`, `success-report-site/`) are **NOT deleted** until the new platform passes comprehensive comparison testing proving feature parity.

### Comparison Testing Process (per phase)

After each implementation phase, we run **side-by-side Playwright tests** comparing old app behavior to new platform behavior:

**Step 1: Launch both apps simultaneously**
```bash
# Old app (original port)
cd chart-viewer && npx serve -p 8103 &

# New platform
cd platform && npm run dev -- --port 5173 &
cd platform/api && uvicorn main:app --port 8000 &
```

**Step 2: Feature parity test suite**

Each old app gets a dedicated Playwright comparison spec:

```typescript
// tests/comparison/chart-viewer.spec.ts
test.describe('Chart Viewer: Feature Parity', () => {
  const OLD = 'http://localhost:8103';
  const NEW = 'http://localhost:5173/charts';

  test('candlestick chart renders with same data', async ({ page }) => {
    // Load old app, screenshot the chart
    await page.goto(OLD);
    await page.waitForSelector('.tv-lightweight-charts');
    const oldScreenshot = await page.screenshot();

    // Load new app, screenshot the chart
    await page.goto(NEW);
    await page.waitForSelector('[data-testid="candlestick-chart"]');
    const newScreenshot = await page.screenshot();

    // Visual comparison (pixel diff threshold)
    expect(await compareImages(oldScreenshot, newScreenshot)).toBeLessThan(0.05);
  });

  test('trade marking creates same data structure', async ({ page }) => {
    // Click to mark in old app → capture JSON output
    // Click to mark in new app → capture JSON output
    // Compare structure and values
  });

  test('timeframe switching preserves aggregation', async ({ page }) => {
    // Switch to 5m in old → capture bar count
    // Switch to 5m in new → compare bar count matches
  });

  test('all timeframes available (1/5/15/30/60)', async ({ page }) => { ... });
  test('analytics panel shows same metrics', async ({ page }) => { ... });
  test('reference levels render correctly', async ({ page }) => { ... });
});
```

Similar specs for:
- `tests/comparison/options-heatseeker.spec.ts` — GEX/VEX heatmap rendering, node detection, filter toggling, date navigation
- `tests/comparison/trading-dashboard.spec.ts` — Live data polling, indicator values, signal detection, sound alerts
- `tests/comparison/success-report.spec.ts` — 6-tab navigation, metric card values, chart rendering

**Step 3: Feature checklist per app**

| chart-viewer | Status |
|---|---|
| Candlestick chart renders | |
| Trade marking (entry/TP/SL) | |
| Multi-TF (1/5/15/30/60) | |
| Volume histogram | |
| Reference levels | |
| RTH filter | |
| Analytics panel (win rate, P&L) | |
| Date selector | |
| Dark theme | |

| options-heatseeker | Status |
|---|---|
| GEX heatmap renders | |
| VEX heatmap renders | |
| King node detection + badge | |
| Gatekeeper detection + badge | |
| Midpoint detection + badge | |
| Net/Calls/Puts filter | |
| Date navigation (arrows) | |
| Ticker switching (SPY/QQQ/IWM) | |
| Zero gamma level line | |
| Max pain indicator | |
| Implied move calculation | |
| Color scales (green→gold, blue→purple) | |

| trading-dashboard | Status |
|---|---|
| Live price polling (Polygon) | |
| RSI indicator | |
| EMA indicators | |
| StochRSI indicator | |
| ATR indicator | |
| CALL signal detection | |
| PUT signal detection | |
| Sound alerts | |
| Market status bar | |
| Trade history | |

| success-report-site | Status |
|---|---|
| Overview tab | |
| Multi-Day tab | |
| Indicator Effectiveness tab | |
| Earnings Timing tab | |
| Strategy Performance tab | |
| Top Plays tab | |
| Metric cards | |
| Chart rendering | |

**Step 4: Cleanup criteria (ALL must be true)**

1. All comparison Playwright tests pass (zero failures)
2. Feature checklist 100% complete for the app being retired
3. New platform tested end-to-end with real user workflow
4. Old app data/config files migrated or preserved
5. Git tag created marking the last known-good state of old apps

**Step 5: Cleanup execution**

```bash
# Tag the old apps before removal
git tag archive/pre-platform-cleanup

# Move old apps to archive (not delete — recoverable)
mkdir -p archive/old-apps
mv chart-viewer/ archive/old-apps/
mv options-heatseeker/ archive/old-apps/
mv website/ archive/old-apps/
mv success-report-site/ archive/old-apps/

# Update .gitignore, remove old Playwright configs
# Update README to point to platform/
```

Old apps are **archived, not deleted** — always recoverable from git history or `archive/` directory.

---

## Chart-Viewer → Trade Tracker → Pipeline Data Flow

The chart-viewer already exports trades as JSON (`tradeMarker.js:exportToJSON()`). The pipeline reads `{ticker}_trade_tracker.csv`. A converter bridges the gap.

### Current Chart-Viewer Trade JSON Structure
```json
{
  "id": "trade_1725813600_abc",
  "ticker": "IWM",
  "optionType": "CALL",
  "entryTime": 1725813600,           // Unix seconds
  "entryPrice": 218.50,
  "exitTime": 1725817200,            // Unix seconds (if exited)
  "exitPrice": 219.75,
  "stopLoss": { "price": 217.80 },   // PRICE, not time
  "takeProfits": [
    { "price": 219.50, "size": 0.5 },
    { "price": 220.50, "size": 0.5 }  // Runner
  ],
  "status": "win",
  "pnl": 1.25, "pnlPercent": 0.57
}
```

### Required Pipeline CSV Format
```csv
ID,Time,Trade_Type,Exit_Time,Stop_Loss_Time,Runner_Time
1,2025-08-08 15:21:00,CALL,2025-08-08 15:35:00,2025-08-08 15:29:00,2025-08-08 15:50:00
```

### Conversion Logic (built into FastAPI + `/journal` page)

| JSON field | CSV column | Conversion |
|---|---|---|
| `id` | `ID` | Keep or auto-increment |
| `entryTime` (unix) | `Time` | `datetime.fromtimestamp(ts).strftime(...)` |
| `optionType` | `Trade_Type` | Direct map (CALL/PUT) |
| `exitTime` (unix) | `Exit_Time` | `datetime.fromtimestamp(ts).strftime(...)` |
| `stopLoss.price` | `Stop_Loss_Time` | **Lookup**: scan 1-min bars after entry to find when price hit SL level |
| `takeProfits[-1].price` | `Runner_Time` | **Lookup**: scan 1-min bars after entry to find when price hit highest TP |

The SL/Runner time lookup uses the existing `lib/data_loader.py` DataLoader to load 1-min bars and find the first bar where price crossed the target level.

### End-to-End Flow
```
Mark trades in /charts → Auto-save to journal store
    → /journal page shows all trades with enrichment
    → "Export to Pipeline" button runs converter
    → Writes {ticker}_trade_tracker.csv
    → Click "Run Analysis" → calls /api/analysis/pipeline/{ticker}
    → View results in /reports
```

### Key Source Files
- `chart-viewer/src/tradeMarker.js` lines 79-142 (trade object definition)
- `chart-viewer/src/tradeMarker.js` lines 310-332 (`exportToJSON()`)
- `data/signals/trade_examples/create_trade_tracker.py` (existing template creator — will be extended)
- `trade_analysis_pipeline.py` lines 123-157 (`step1_update_trade_tracker` — reads CSV)

---

## Key Files to Port

| Source File | Target | What to Preserve |
|-------------|--------|-----------------|
| `chart-viewer/src/chartManager.js` | `src/components/charts/CandlestickChart.tsx` | TradingView chart creation, data binding, markers, themes |
| `chart-viewer/src/tradeMarker.js` | `src/components/charts/TradeMarkers.tsx` | Click-to-mark entry, TP levels, stop loss, notes |
| `chart-viewer/src/dataLoader.js` | `src/lib/timeframeAggregator.ts` | 1m→5m→15m→30m→60m bar aggregation |
| `chart-viewer/src/analytics.js` | `src/hooks/useTradeAnalytics.ts` | Win rate, avg P&L, call/put ratio |
| `options-heatseeker/js/greeksCalculator.js` | `src/lib/greeksCalculator.ts` | GEX/VEX, zero gamma, max pain, implied move |
| `options-heatseeker/js/nodeAnalyzer.js` | `src/lib/nodeAnalyzer.ts` | King nodes, gatekeepers, midpoints |
| `options-heatseeker/js/heatmapRenderer.js` | `src/components/charts/OptionsHeatmap.tsx` | D3.js cell rendering, color scales, node indicators |
| `options-heatseeker/js/dataLoader.js` | `src/hooks/useOptionsData.ts` | Cloudflare Worker fetch + caching logic |
| `website/trading-dashboard.html` (JS) | `src/hooks/usePolygonData.ts` + `src/lib/indicators.ts` | Polygon polling, RSI/EMA/StochRSI calc, signal thresholds |
| `success-report-site/src/app.js` | `src/routes/ReportsPage.tsx` | 6-tab layout, metric cards (Chart.js→Recharts) |

---

## Shared Component Library

| Component | Source | Library |
|-----------|--------|---------|
| `CandlestickChart` | Port from chart-viewer | TradingView Lightweight Charts |
| `OptionsHeatmap` | Port from options-heatseeker | D3.js (useRef wrapper) |
| `EquityCurve` | New | Recharts (line + area for drawdown) |
| `MetricCard` | New | Tailwind (value, label, trend arrow) |
| `DataTable` | New | TanStack Table v8 (sort, filter, paginate, virtual scroll) |
| `PlaybookCard` | New | Tailwind card (conditions checklist, entry rules, warnings) |
| `TickerSelector` | New | IWM/SPY/QQQ toggle in sidebar (global Zustand state) |
| `TimeframeSelector` | Port from chart-viewer | 1m/5m/15m/30m/1h toggle |
| `SignalDetector` | Port from trading-dashboard | Client-side indicator evaluation |
| `SoundAlerts` | Port from trading-dashboard | Web Audio API |
| `OptionsFilters` | Port from options-heatseeker | GEX/VEX toggle, Net/Calls/Puts, DTE ranges |

---

## Phased Implementation

### Phase 0: Foundation -- COMPLETE
- [x] Initialize Vite 7 + React 19 + TypeScript project in `platform/`
- [x] Tailwind CSS 4 dark theme setup (custom tokens: bg-primary, accent-green/red/blue)
- [x] AppShell layout: collapsible sidebar + header + main content area
- [x] Zustand stores: tickerStore, settingsStore, tradeStore, marketStore
- [x] TanStack Query provider (staleTime: 5min, retry: 1)
- [x] React Router with lazy-loaded route stubs (all 10 routes render placeholder)
- [x] Shared components: MetricCard, DataTable, Tabs, Modal, LoadingSpinner
- [x] FastAPI skeleton: `platform/api/main.py` with CORS + health check (200 OK)
- [x] Vite proxy: `/api` → `localhost:8000`
- [ ] Playwright test infrastructure: comparison test harness for old vs new apps (deferred to Phase 1)

### Phase 1: Chart Viewer (core MVP) -- COMPLETE ✅
- [x] Port CandlestickChart from `chartManager.js` → TypeScript React component (TradingView LWC v5)
- [x] FastAPI `GET /api/market/data/{ticker}/{date}` wrapping DataLoader (1m/5m/15m/30m/1h aggregation)
- [x] FastAPI `GET /api/market/dates/{ticker}` — lists 81 available IWM dates
- [x] FastAPI `GET /api/market/reference/{ticker}/{date}` — previous day OHLC for reference levels
- [x] Trade marking system: entry → CALL/PUT selection → TP1/TP2/TP3 (ESC to skip) → SL (ESC to skip) → complete
- [x] Trade exit marking: LogOut button on each TradeCard, click chart to set exit price + auto P&L calc
- [x] Trade deletion per card
- [x] TP/SL price lines drawn on chart (green for TP, red for SL, dotted, auto-cleanup on change)
- [x] Reference levels toggle (Ref button): prev day H/L/O/C shown as dashed lines on chart
- [x] Volume histogram, RTH filter (9:30-16:00 ET), Vol toggle, timeframe buttons
- [x] Trade analytics side panel: Trades tab (cards) + Analytics tab (8 metrics)
- [x] Export trades to JSON (pipeline-compatible format matching `create_trade_tracker.py` schema)
- [x] Export trades to CSV (full OHLC + TP1-3 + SL + P&L)
- [x] ESC key cancels/advances drawing mode (document-level listener, works regardless of focus)
- [x] OHLCV crosshair info bar + prev-day levels shown inline
- [x] **18/18 Playwright tests passing** (`tests/phase1-charts.spec.ts`)

### Phase 2: Live Market -- COMPLETE ✅
- [x] Alpha Vantage as primary real-time data source (`api/routers/live.py`)
- [x] `GET /api/live/status` — market session detection (pre/regular/after/closed)
- [x] `GET /api/live/quote/{ticker}` — GLOBAL_QUOTE, 15s refetch
- [x] `GET /api/live/history/{ticker}` — TIME_SERIES_INTRADAY 1min compact, 60s refetch
- [x] `src/lib/indicators.ts` — EMA, RSI, StochRSI, ATR calculations (TypeScript)
- [x] `computeSignals()` — 10 conditions per CALL/PUT, strength 0-100%, fires at ≥70%
- [x] `src/routes/LiveMarketPage.tsx` — quote card, 6 metric cards, CALL/PUT signal cards with condition rows
- [x] Sound alerts (AudioContext, 880Hz CALL / 440Hz PUT, 2-min cooldown)
- [x] Polling toggle, market status bar, last-update display

### Phase 3: Options Flow (Heatseeker) + Cloudflare → GCP Migration -- COMPLETE ✅
- [x] `src/lib/greeksCalculator.ts` — TypeScript port of GEX/VEX calculations, aggregateByStrike, calculateGEXByStrike, computeAllMetrics
- [x] `src/lib/nodeAnalyzer.ts` — TypeScript port of king node, gatekeeper, midpoint detection
- [x] `api/routers/options.py` — Alpha Vantage HISTORICAL_OPTIONS proxy (replaces Cloudflare Worker)
  - `GET /api/options/dates/{ticker}` — last 10 trading dates
  - `GET /api/options/{ticker}/{date}` — full options chain with normalized greeks
- [x] `src/routes/OptionsFlowPage.tsx` — D3.js GEX/VEX heatmap (useRef + useEffect)
  - Horizontal bars per strike (green/emerald positive, purple negative)
  - Current price red line, node badges (★ king, ◆ gatekeeper, ● midpoint)
  - GEX/VEX metric toggle, Net/Calls/Puts filter
  - Date navigation with ← → arrows
  - Metrics bar: Total GEX/VEX, Zero Gamma, Max Pain, Put/Call Ratio
  - ±15% strike range focus, spot price override input

### Phase 4: Playbook + Reports -- COMPLETE ✅
- [x] `api/routers/playbook.py` — markdown playbook parser → JSON cards
  - `GET /api/playbook/{ticker}` — phase6 markdown → name/description/conditions/win_rate/avg_return
  - `GET /api/reports/list/{ticker}` — all phase reports for a ticker
  - `GET /api/reports/{ticker}/{phase}` — raw markdown text
- [x] `src/routes/PlaybookPage.tsx` — interactive condition checklists with progress bars
  - CheckCircle/Circle toggle per condition
  - Win rate + avg return stats per card
  - CALL/PUT/NEUTRAL direction badges
- [x] `src/routes/ReportsPage.tsx` — sidebar report list + markdown viewer
  - Simple in-app markdown renderer (no external dep)
  - Lazy-load report content via TanStack Query

### Phase 5: Backtest + Signals -- COMPLETE ✅
- [x] `api/routers/backtest.py` — backtest CSV reader
  - `GET /api/backtest/results/{ticker}` — most recent backtest CSV + summary
  - `GET /api/backtest/equity/{ticker}` — equity curve CSV
  - `GET /api/backtest/all/{ticker}` — list all backtest files with metadata
- [x] `api/routers/signals.py` — historical signals parquet reader
  - `GET /api/signals/{ticker}` — up to 50K rows, direction/score/date filters
  - Reads `data/signals/historical_{ticker}_*_signals.parquet` (336K rows for IWM)
- [x] `src/routes/BacktestPage.tsx` — equity curve (Recharts AreaChart) + trade table (TanStack Table)
  - Metrics: total trades, win rate, avg return, best/worst
  - Sortable trade log with direction coloring, exit reason, score
- [x] `src/routes/SignalsPage.tsx` — Signal Explorer with filters
  - Direction (ALL/CALL/PUT), min score, date range filters
  - Sortable table: time, direction, score, price, RSI, EMA9, volume
  - Shows up to 500 rows, reports total count

### Phase 6: Journal + Dashboard -- COMPLETE ✅
- [x] `api/routers/journal.py` — Cloud SQL-backed trade journal with local fallback
  - `GET /api/journal/trades/{ticker}` — read from `journal_entries` Cloud SQL table (or local JSON)
  - `POST /api/journal/trades` — insert entry into Cloud SQL (or local JSON fallback)
  - `DELETE /api/journal/trades/{id}` — delete by UUID
  - `POST /api/journal/export/{ticker}` — write `{ticker}_trade_tracker.csv` to `data/signals/`
  - **Graceful degradation**: Cloud SQL when `CLOUD_SQL_CONNECTION_NAME` is set; local `data/journal/` JSON otherwise
  - **Production persistence**: `journal_entries` table in Cloud SQL (UUID PK, TIMESTAMPTZ, DOUBLE PRECISION prices, return_pct, notes, created_at/updated_at)
- [x] `src/routes/JournalPage.tsx` — TanStack Query-backed journal (Cloud SQL primary, localStorage as optimistic cache)
  - `useJournalTrades()` — Query hook with localStorage placeholder data
  - `useAddTrade()` / `useDeleteTrade()` — Mutations with cache invalidation
  - Source indicator: `Database` icon (Cloud SQL) vs `HardDrive` icon (local)
  - Add-trade form, stats bar, trade table with delete, CSV download, pipeline export
- [x] `src/routes/DashboardPage.tsx` — real KPI aggregation
  - Pulls from `/api/backtest/results/{ticker}` (win rate, avg return, total return)
  - Pulls from `/api/signals/{ticker}?limit=200` (recent signals)
  - Pulls from `/api/playbook/{ticker}` (card list)
  - Recent signals list + playbook card list + total return banner

### Phase 7: AI Insights (Vertex AI Gemini) -- COMPLETE ✅
- [x] `api/routers/insights.py` — Gemini streaming endpoint
  - `POST /api/insights/chat` — SSE streaming with 4 system prompt personas
  - Uses `google.genai` SDK (not deprecated `vertexai.generative_models`)
  - Loads SA credentials from `.gcp-key.json`, project `adept-mountain-474619-d4`
  - Graceful fallback if `google-genai` not installed or SA lacks `roles/aiplatform.user`
  - 4 modes: Open Chat, Market Brief, Strategy Feedback, Trade Review
- [x] Vertex AI API enabled on `adept-mountain-474619-d4`; `roles/aiplatform.user` granted to `trading-runner` SA
- [x] `src/routes/InsightsPage.tsx` — streaming chat UI
  - Mode selector tabs with mode-specific quick actions
  - Real-time token streaming via ReadableStream
  - Typing indicator, auto-scroll, Shift+Enter for newlines
  - Clears conversation on mode/ticker change

### Phase 7.5: Production-Grade Infrastructure -- COMPLETE ✅
- [x] `platform/vite.config.ts` — `host: true` (listen on `0.0.0.0` for GitHub Codespace port forwarding)
- [x] `platform/api/main.py` — `allow_origin_regex=r"https://.*\.app\.github\.dev"` (Codespace CORS)
- [x] `platform/api/main.py` — `StaticFiles` mount for `platform/dist/` (single-port production serving)
  - If `platform/dist/` exists (after `npm run build`), FastAPI serves the full SPA on port 8000
  - API routes always take priority over the static file catch-all
  - Enables production workflow: `npm run build && uvicorn api.main:app --host 0.0.0.0 --port 8000`
- [x] `gcp/schema.sql` — `journal_entries` table added (UUID PK, Cloud SQL journal backend)
- [x] `docs/GCP_IMPLEMENTATION_STATUS.md` — Platform section added

**Architecture summary (production-grade)**:

| Concern | Dev | Production |
|---------|-----|-----------|
| Frontend | `npm run dev` on :5173 (Vite proxy to :8000) | `npm run build` → FastAPI `StaticFiles` on :8000 |
| Journal | Cloud SQL `journal_entries` (local JSON fallback) | Same — Cloud SQL is already production |
| API host | `0.0.0.0` (Codespace-ready) | `0.0.0.0` via `--host 0.0.0.0` |
| CORS | `*.app.github.dev` + localhost | Same |
| AI | Vertex AI Gemini 2.0 Flash | Same (SA key in env) |
| Chart data | Cloud SQL `market_data_intraday` (3,115 dates, 2015–2026) | Same |
| Reference levels | Cloud SQL `market_data_daily` | Same |
| Data | Cloud SQL + GCS parquets | Same |
| Pipeline | Cloud Run Jobs (22 schedulers) | Same |

**Pending (Phase 9)**:
- [ ] Cloud Run deployment for `platform/api/` (Dockerfile in `gcp/`)
- [ ] Auth gate (Firebase Auth or GCP IAP) if multi-user access needed
- [ ] Journal → AI context injection (pass recent journal entries as Gemini prompt context)
- [ ] SL/Runner time lookup: scan `market_data_intraday` to find price crossing times for pipeline export

### Phase 8: Comparison Testing + Old App Cleanup
- Run full comparison test suite across all 4 old apps vs new platform
- Complete feature parity checklists (chart-viewer, heatseeker, dashboard, reports)
- Git tag `archive/pre-platform-cleanup` for recovery point
- Archive old app directories to `archive/old-apps/` (not deleted)
- Update project README, remove old Playwright port configs
- Final E2E regression suite on platform-only (no old apps running)

### Phase 9: Polish + Deploy
- Responsive design (mobile sidebar collapse)
- Keyboard shortcuts (T=ticker cycle, 1-5=TF, Esc=close)
- CSV/PNG export across all pages
- Full Playwright E2E test suite (all 10 routes)
- Deploy workflow (Vite static → GitHub Pages, FastAPI → Cloud Run)

---

## Verification

1. **Phase 0**: `cd platform && npm run dev` renders AppShell with sidebar nav and all 10 route stubs; FastAPI health check returns 200
2. **Phase 1**: `/charts` → select IWM + date → candlestick chart renders, trade marking works, JSON export matches expected structure; **comparison tests pass vs old chart-viewer**
3. **Phase 2**: `/live` → real-time price updates via Alpha Vantage, indicators compute, signals fire with sound; **comparison tests pass vs old trading-dashboard**
4. **Phase 3**: `/options` → select IWM → GEX heatmap renders with king nodes/gatekeepers/midpoints; GEX/VEX toggle, date navigation; Alpha Vantage proxy works via FastAPI (Cloudflare Worker decommissioned); **comparison tests pass vs old heatseeker**
5. **Phase 4**: `/playbook` → 12 cards for IWM with checkable conditions; `/reports` → 6-tab dashboard; **comparison tests pass vs old success-report-site**
6. **Phase 5**: `/backtest` → equity curve + trade table; `/signals` → filterable signal browser with 330K+ rows
7. **Phase 6**: `/journal` → mark trade in /charts → appears in journal → click "Export to Pipeline" → `iwm_trade_tracker.csv` written → "Run Analysis" → view report; **full chart-viewer → pipeline data flow works**
8. **Phase 7**: `/insights` → select "Market Brief" → AI streams real-time analysis grounded in user's data; Trade Review mode grades a specific trade A-F with references to actual metrics
9. **Phase 8**: All 4 comparison test suites pass (chart-viewer, heatseeker, dashboard, reports); feature parity checklists 100% complete; old apps archived to `archive/old-apps/`
10. **Phase 9**: Full Playwright E2E suite passes all 10 routes; responsive design works on mobile viewport; keyboard shortcuts functional
