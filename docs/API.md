# Platform API Reference

FastAPI app: [platform/api/main.py](../platform/api/main.py)
Routers registered: [platform/api/main.py:47-58](../platform/api/main.py#L47-L58)
Live OpenAPI: `http://localhost:8000/docs` · `http://localhost:8000/openapi.json`

## Start the API

```bash
cd platform
set -a && source ../.env && set +a
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

## Routers (12)

All routers mount at root (`prefix=""`); `admin` carries its own `/api/admin` prefix.

| Router | File | Endpoints |
|---|---|---|
| admin | [admin.py](../platform/api/routers/admin.py) | 3 |
| analytics | [analytics.py](../platform/api/routers/analytics.py) | 2 |
| backtest | [backtest.py](../platform/api/routers/backtest.py) | 3 |
| catalysts | [catalysts.py](../platform/api/routers/catalysts.py) | 3 |
| config | [config.py](../platform/api/routers/config.py) | 2 |
| dashboard | [dashboard.py](../platform/api/routers/dashboard.py) | 1 |
| insights | [insights.py](../platform/api/routers/insights.py) | 6 |
| journal | [journal.py](../platform/api/routers/journal.py) | 4 |
| live | [live.py](../platform/api/routers/live.py) | 5 |
| options | [options.py](../platform/api/routers/options.py) | 3 |
| playbook | [playbook.py](../platform/api/routers/playbook.py) | 4 |
| signals | [signals.py](../platform/api/routers/signals.py) | 1 |

**Total: 37 endpoints**

---

## Endpoint Index

### admin — [admin.py](../platform/api/routers/admin.py)
Requires `X-Admin-Token` header.
- `GET  /api/admin/routes` — list role→model routes
- `PUT  /api/admin/routes/{role}` — update model for a role
- `GET  /api/admin/models` — list available models

### analytics — [analytics.py](../platform/api/routers/analytics.py)
- `POST /api/analytics/trade-stats` — compute stats from posted trade rows
- `GET  /api/analytics/summary/{ticker}?days=90` — summary from `trades` table

### backtest — [backtest.py](../platform/api/routers/backtest.py)
- `GET  /api/backtest/results/{ticker}` — most recent backtest CSV
- `GET  /api/backtest/equity/{ticker}` — most recent equity curve
- `GET  /api/backtest/all/{ticker}` — all runs, newest first

### catalysts — [catalysts.py](../platform/api/routers/catalysts.py)
- `GET  /api/catalysts/events` — events grouped by date
- `GET  /api/catalysts/ticker/{ticker}` — events for one ticker
- `GET  /api/catalysts/types` — available types + WSH upgrade info

### config — [config.py](../platform/api/routers/config.py)
- `GET  /api/config/indicators` — indicator periods, thresholds, RSI zone labels
- `GET  /api/config/market-hours` — US session windows + 2026 holidays

### dashboard — [dashboard.py](../platform/api/routers/dashboard.py)
- `GET  /api/dashboard/brief/{ticker}` — daily bias + strat status

### insights — [insights.py](../platform/api/routers/insights.py)
- `GET  /api/insights/report/{ticker}` — latest InsightReport
- `GET  /api/insights/report/{ticker}/history?limit=20` — recent reports list
- `GET  /api/insights/reports/{report_id}` — single report by id
- `POST /api/insights/report/{ticker}/refresh` — enqueue pipeline run
- `GET  /api/insights/runs/{run_id}` — poll refresh run status
- `POST /api/insights/chat` — streamed Gemini chat

### journal — [journal.py](../platform/api/routers/journal.py)
- `GET  /api/journal/trades/{ticker}` — entries for ticker, newest first
- `POST /api/journal/trades` — create entry
- `DELETE /api/journal/trades/{trade_id}?ticker=` — delete by UUID
- `POST /api/journal/export/{ticker}` — write `{ticker}_trade_tracker.csv`

### live — [live.py](../platform/api/routers/live.py)
- `GET  /api/live/status` — market open/closed (ET)
- `GET  /api/live/quote/{ticker}` — AV GLOBAL_QUOTE
- `GET  /api/live/history/{ticker}` — last 100 1-min bars (AV intraday)
- `GET  /api/live/avg-volume/{ticker}` — 20-day avg volume for RVOL
- `POST /api/live/indicators` — compute indicators + CALL/PUT signals from bars

### options — [options.py](../platform/api/routers/options.py)
- `GET  /api/options/dates/{ticker}` — recent snapshot dates with AV data
- `GET  /api/options/{ticker}/{date_str}` — AV option chain for date
- `POST /api/options/greeks` — GEX/VEX/max-pain/implied-move/nodes

### playbook — [playbook.py](../platform/api/routers/playbook.py)
- `GET  /api/playbook/{ticker}` — phase6 playbook from GCS as setup cards
- `GET  /api/reports/list/{ticker}` — phase reports available in GCS
- `GET  /api/reports/{ticker}/{phase}` — raw markdown of a phase report
- `POST /api/playbook/evaluate` — eval condition strings vs live snapshot

### signals — [signals.py](../platform/api/routers/signals.py)
- `GET  /api/signals/{ticker}?limit=&direction=&min_score=&end_date=&end_time=` — historical signals from GCS parquet

---

## Conventions

- All endpoints live under `/api/*` except admin (`/api/admin/*`).
- Path params: `{ticker}` is uppercased symbol (SPY, QQQ, IWM, ^SPX). `{date_str}` is `YYYY-MM-DD`.
- Data sources: Cloud SQL (`market_data_*`, `etf_options_snapshots`, `journal_entries`, `trades`), GCS (parquets, phase reports, playbook md), Alpha Vantage (live quote/intraday/global-quote).
- Auth: only `admin` router checks `X-Admin-Token`. Other routes are open inside the codespace; `vite.config.ts` proxies `/api → :8000`.

## Regenerating this doc

This file is hand-maintained. To refresh, list endpoints with:

```bash
grep -nE "^@router\.(get|post|put|delete|patch)" platform/api/routers/*.py
```

Or hit the live spec: `curl localhost:8000/openapi.json | jq '.paths | keys'`.
