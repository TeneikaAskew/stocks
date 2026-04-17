# AI Insights Multi-Agent Pipeline — Phase 2 Gap Analysis & Remediation Plan

## Context

The multi-agent AI Insights implementation (17 commits, 41 files, ~7,600 lines) has been built on branch `claude/research-trading-agents-LFNT2`. It replaces the old chat-only Gemini tab with a structured, auto-generated report powered by an 11-node async agent pipeline (4 analysts, bull/bear researchers, judge, trader, 3 risk personas, portfolio manager).

This plan addresses gaps between the original design goals and what was actually shipped, plus critical runtime bugs found in the audit, plus visual design inconsistencies.

---

## Part 1: Feature Gaps (Original Assessment vs Implementation)

### Gap 1: News/Sentiment Data Source — MISSING
**Planned**: AlphaVantage NEWS_SENTIMENT fetcher, `news_sentiment` Cloud SQL table, `fetch-news-sentiment.yml` workflow, Sentiment Analyst agent.
**Actual**: None of these exist. The pipeline has 4 analysts (market, strat, options, catalyst) but no sentiment analyst.

**Files to create:**
- `gcp/fetchers/fetch_news_sentiment.py` — Poll AV `NEWS_SENTIMENT` endpoint for IWM/SPY/QQQ/SPX. Pattern matches `gcp/fetchers/fetch_economic_events.py` (argparse, `AV_API_KEY` from env, `gcp.database.execute_sql` batch upsert).
- `.github/workflows/fetch-news-sentiment.yml` — Cron `0 */4 * * 1-5`. Follow `fetch-market-data.yml` pattern + `handle-workflow-failure.yml`.
- Append to `gcp/schema.sql`:
  ```sql
  CREATE TABLE IF NOT EXISTS news_sentiment (
      id BIGSERIAL PRIMARY KEY,
      ticker VARCHAR(10) NOT NULL,
      published_ts TIMESTAMPTZ NOT NULL,
      title TEXT,
      url TEXT,
      summary TEXT,
      sentiment_score DOUBLE PRECISION,
      relevance_score DOUBLE PRECISION,
      source VARCHAR(100),
      inserted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT uq_news UNIQUE (ticker, published_ts, url)
  );
  CREATE INDEX IF NOT EXISTS idx_news_sentiment_ticker_ts ON news_sentiment (ticker, published_ts DESC);
  ```
- Add `summarize_news_sentiment(ticker, as_of)` to `lib/agents/summarizers.py`. Query `news_sentiment` for rows in last 48 hours, aggregate sentiment_score, return top headlines + overall score.
- Add `"sentiment"` section to `build_context_bundle()`.
- Add `ANALYST_PROMPTS["sentiment"]` to `lib/agents/prompts.py`.
- Add `"sentiment"` to analyst_sections tuple in `lib/agents/orchestrator.py:300`.

**Reuse**: `gcp/database.py:query_to_dataframe`, `gcp/database.py:execute_sql`, existing AV_API_KEY secret.

### Gap 2: Earnings Plays Expansion — MISSING
**Planned**: Daily pipeline covers core 4 ETFs + any ticker with earnings in next 7 days from `earnings_calendar`.
**Actual**: `gcp/insight_pipeline_job.py` reads `INSIGHT_TICKERS` env var (hardcoded to SPY/IWM/QQQ).

**Files to modify:**
- `gcp/insight_pipeline_job.py` — After the hardcoded tickers loop, query `earnings_calendar` for tickers with `earnings_date BETWEEN NOW() AND NOW() + interval '7 days'` and append to the ticker list (deduplicated). Reuse `gcp.database.query_to_dataframe`.
- `.github/workflows/daily-insight-reports.yml` — No change needed (job handles ticker resolution internally).

### Gap 3: Chat Sub-Tab — REMOVED
**Planned**: Preserve old Gemini chat as secondary tab at `/insights/chat` with tool access.
**Actual**: Chat endpoint completely removed. `InsightsPage.tsx` has Report + History tabs only.

**Files to modify:**
- `platform/api/routers/insights.py` — Add back `POST /api/insights/chat` endpoint (restore from git history of the old `insights.py`). Uses `google-genai` streaming Gemini, same as before. This is independent of the agent pipeline.
- `platform/src/routes/InsightsPage.tsx` — Add third tab "Chat" that renders the old streaming chat UI. Extract as `InsightsChatView` component.
- `platform/src/App.tsx` — No change needed (tab is within the page, not a separate route).

### Gap 4: Anthropic Adapter — MISSING (Expected)
**Planned**: Provider-agnostic interface with Anthropic adapter ready for day-two.
**Actual**: Only `lib/agents/vertex_adapter.py` exists. No `anthropic_adapter.py`.

**Files to create:**
- `lib/agents/anthropic_adapter.py` — Implements `LLMClient` using `anthropic` SDK. Structured output via forced tool-use (wraps Pydantic schema as `tools=[{"input_schema": model_json_schema()}]`). Async via `asyncio.to_thread`. Registers as `"anthropic"` in adapter registry. Requires `ANTHROPIC_API_KEY` env var; skips registration if absent.
- Add `anthropic>=0.40.0` to `requirements-gcp.txt` (optional dep).
- Add upgrade comments to `lib/agents/prompts.py` at bull/bear/judge/PM prompts: `# UPGRADE: Route this role to anthropic:claude-sonnet-4-6 for stronger adversarial reasoning`

---

## Part 2: Critical Runtime Bugs

### Bug 1: Cloud SQL Connector Leak — CRITICAL
**File**: `lib/agents/model_routing.py:51`
**Problem**: `_connect()` creates a new `Connector()` instance per call. The Connector manages a connection pool internally; creating one per request leaks pools and will exhaust Cloud SQL max connections under load.
**Fix**: Create a module-level singleton `_CONNECTOR` (lazy-initialized), reuse across all `_connect()` calls. Add `atexit` handler to close it.

```python
_CONNECTOR = None

def _get_connector():
    global _CONNECTOR
    if _CONNECTOR is None:
        from google.cloud.sql.connector import Connector
        _CONNECTOR = Connector()
    return _CONNECTOR
```

### Bug 2: No Connection Pooling in Insights Router — CRITICAL
**File**: `platform/api/routers/insights.py:80-252`
**Problem**: 7 DB helper functions each call `_connect()` → new connection per call. FastAPI handles requests concurrently; under load this means dozens of simultaneous connections.
**Fix**: Refactor DB helpers to use `gcp.database.get_engine()` with SQLAlchemy, which already has connection pooling configured (pool_size=5, max_overflow=2). Alternatively, at minimum ensure the singleton Connector from Bug 1 fix is shared.

### Bug 3: Bull/Bear Researchers Not Error-Protected — IMPORTANT
**File**: `lib/agents/orchestrator.py:354`
**Problem**: `asyncio.gather(bull_task, bear_task)` without `return_exceptions=True`. If either fails, the entire pipeline crashes with no graceful degradation.
**Fix**: Add `return_exceptions=True`, handle failed researcher by substituting a default `ResearcherOutput` with stance="bull"/"bear", case="Analysis unavailable due to LLM error", key_points=[].

### Bug 4: Trader + Portfolio Manager Not Error-Protected — IMPORTANT
**Files**: `lib/agents/orchestrator.py:369,405`
**Problem**: Direct `await` on trader and PM nodes. If either fails, pipeline crashes.
**Fix**: Wrap each in try/except. If trader fails, construct a default flat TraderOutput. If PM fails, construct InsightReport directly from trader output + risk flags (bypass PM).

### Bug 5: `_connect` is Private but Imported Externally — IMPORTANT
**File**: `platform/api/routers/insights.py:33`
**Problem**: `from lib.agents.model_routing import _connect` — private function imported across module boundaries.
**Fix**: Rename to `connect()` (public) or better: refactor insights router DB helpers to use `gcp.database` (solves Bug 2 simultaneously).

### Bug 6: Anthropic Models Selectable but Crash at Runtime — IMPORTANT
**File**: `lib/agents/pricing.py:52-70`, `lib/agents/model_routing.py`
**Problem**: The pricing table defines 3 Anthropic models (claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001) and the admin UI allows routing any role to them. But no `anthropic_adapter.py` exists, so `get_adapter('anthropic')` raises `KeyError` and the entire pipeline crashes.
**Fix (immediate)**: Add a guard in `model_routing.py` `list_available_models()` that only exposes providers with registered adapters. The admin UI dropdown should only show providers where `get_adapter(provider)` won't raise. This prevents users from selecting Anthropic until the adapter ships.
**Fix (Phase E)**: Create `lib/agents/anthropic_adapter.py` to make the selection actually work.

---

## Part 3: Important Improvements

### Improvement 1: Schema Migration Idempotency — VERIFIED SAFE
**File**: `gcp/schema.sql`
All new tables use `CREATE TABLE IF NOT EXISTS`. `INSERT INTO model_routing` seed data uses `ON CONFLICT (role) DO NOTHING`. pgvector uses `CREATE EXTENSION IF NOT EXISTS vector`. No action needed.

### Improvement 2: UTC Normalization in `_as_datetime`
**File**: `lib/agents/orchestrator.py:536-541`
Add `value.astimezone(timezone.utc)` for timezone-aware datetime inputs to normalize to UTC.

### Improvement 3: `sys.path.insert` Fragility
**Files**: `platform/api/routers/insights.py:30-31`, `scripts/generate_historical_report.py:40-41`
Low risk for now (works in all current deployment contexts). Document in CLAUDE.md that `PYTHONPATH` should include project root, or add a `pyproject.toml` with `[tool.setuptools.packages.find]` for editable installs.

---

## Part 4: Visual Design Inconsistencies

The Insights page uses `emerald-*` and `rose-*` Tailwind colors while the entire rest of the platform uses `green-*` and `red-*`. The platform's design tokens map to:
- `--color-accent-green: #22c55e` = Tailwind `green-500` (NOT emerald-500 #10b981)
- `--color-accent-red: #ef4444` = Tailwind `red-500` (NOT rose-500 #f43f5e)

### Must-Fix (Visual Breaks — wrong color family)

**File: `platform/src/components/insights/ReportCards.tsx`**
| Line | Element | Current | Fix |
|------|---------|---------|-----|
| 28 | Direction badge (long) | `bg-emerald-500/20 text-emerald-400 border-emerald-500/40` | `bg-green-500/20 text-green-400 border-green-500/40` |
| 29 | Direction badge (short) | `bg-rose-500/20 text-rose-400 border-rose-500/40` | `bg-red-500/20 text-red-400 border-red-500/40` |
| 123 | Stop price | `text-rose-400` | `text-red-400` |
| 127 | Target prices | `text-emerald-400` | `text-green-400` |
| 155-158 | Strat bullish/bearish | `text-emerald-400` / `text-rose-400` | `text-green-400` / `text-red-400` |
| 230 | Bull Case card border | `border-emerald-500/30` | `border-green-500/30` |
| 233 | Bear Case card border | `border-rose-500/30` | `border-red-500/30` |
| 257 | Catalyst high impact | `bg-rose-400` | `bg-red-400` |
| 295-298 | Risk block severity | `text-rose-400` | `text-red-400` |
| 331 | Signal direction | `text-emerald-400` / `text-rose-400` | `text-green-400` / `text-red-400` |
| 364 | Similar trades direction | `text-emerald-400` / `text-rose-400` | `text-green-400` / `text-red-400` |

**File: `platform/src/routes/InsightsPage.tsx`**
| Line | Element | Current | Fix |
|------|---------|---------|-----|
| 203 | Error message | `border-rose-500/40 bg-rose-500/10 text-rose-300` | `border-red-500/40 bg-red-500/10 text-red-300` |
| 310-313 | History direction badges | `emerald-500/*` / `rose-500/*` | `green-500/*` / `red-500/*` |

**Fix approach**: Global find-replace in both files:
- `emerald-` → `green-` (all occurrences)
- `rose-` → `red-` (all occurrences)

Everything else is consistent: card containers use `var(--color-border)` + `var(--color-bg-secondary)`, tabs match platform patterns, font sizes follow the `text-xs`/`text-sm`/`text-[10px]` hierarchy, loading/empty states are consistent.

---

## Implementation Order

### Phase 0: Visual Design Fixes — DONE
1. [x] In `platform/src/components/insights/ReportCards.tsx`: replaced all `emerald-` with `green-`, all `rose-` with `red-`
2. [x] In `platform/src/routes/InsightsPage.tsx`: same replacements

### Phase A: Critical Bug Fixes — DONE
1. [x] Fix Connector singleton in `lib/agents/model_routing.py` (added `_get_connector()` + `atexit` handler)
2. [x] Renamed `_connect` → `connect` across all 7 files that imported it
3. [x] Add `return_exceptions=True` to bull/bear gather in `lib/agents/orchestrator.py` (+ fallback `ResearcherOutput`)
4. [x] Add try/except around trader + PM nodes in orchestrator (+ sensible defaults)
5. [x] Guard `set_route()` against selecting unregistered providers (Bug 6)
6. [x] Fix UTC normalization in `_as_datetime` (Improvement 2)

### Phase B: News/Sentiment Feature — DONE
1. [x] Create `news_sentiment` table in `gcp/schema.sql`
2. [x] Create `gcp/fetchers/fetch_news_sentiment.py`
3. [x] Create `.github/workflows/fetch-news-sentiment.yml`
4. [x] Add `summarize_news_sentiment()` to `lib/agents/summarizers.py`
5. [x] Add `"sentiment"` analyst prompt to `lib/agents/prompts.py`
6. [x] Wire `"sentiment"` into `orchestrator.py` analyst_sections
7. [x] Update `build_context_bundle()` to include sentiment

### Phase C: Earnings Expansion — DONE
1. [x] Add `_earnings_tickers_next_7d()` to `gcp/insight_pipeline_job.py` — dynamic ticker resolution from `earnings_calendar`

### Phase D: Chat Sub-Tab Restoration — DONE
1. [x] Add `POST /api/insights/chat` back to `platform/api/routers/insights.py` (streaming Gemini, 4 modes)
2. [x] Add Chat tab + `ChatView` component to `InsightsPage.tsx`

### Phase E: Anthropic Adapter — DONE
1. [x] Create `lib/agents/anthropic_adapter.py` (forced tool-use structured output, conditional registration)
2. [x] Add `anthropic>=0.40.0` to `requirements-gcp.txt`

### Phase F: Codex Review Fixes (post-review)
1. [x] Bug 7: Add `"sentiment"` to `AnalystOutput.section` Literal in `lib/agents/schema.py` — Pydantic was rejecting every sentiment analyst response
2. [x] Bug 8: Fix `DB_PASSWORD` → `DB_PASS` in `.github/workflows/fetch-news-sentiment.yml` — writes were silently skipping
3. [x] Bug 9: Fix `str(as_of)` midnight cutoff in `lib/agents/summarizers.py` — historical reports excluded all same-day intraday data
4. [x] Bug 10: Add missing `PR_WORKFLOW_TOKEN` secret to `.github/workflows/daily-insight-reports.yml` handle-failure job
5. [x] Bug 11: Fix cron schedule in `fetch-news-sentiment.yml` — removed `0` hour (was firing Sunday night UTC)
6. [x] Add `fetch-news-sentiment` Cloud Run Job + 3 Cloud Scheduler triggers (8am/noon/4pm ET) to `gcp/deploy.sh`

### Phase G: Actionability Improvements (post-evaluation)
1. [x] Add R:R ratio calculation + color-coded display to TradePlanCard (green ≥2:1, amber ≥1:1, red <1:1)
2. [x] Add risk-per-share and position sizing hint ("Shares @ $500 Risk") to TradePlanCard
3. [x] Persist judge weights (`weight_bull`, `weight_bear`) in InsightReport schema + display as percentages on DebateCard
4. [x] Persist researcher key_points (`bull_key_points`, `bear_key_points`) in InsightReport schema + display as structured bullets on DebateCard
5. [x] Add Judge node fallback — was the only unprotected node in the pipeline
6. [x] Pass bull/bear key_points to Trader payload for richer entry/stop/target reasoning

### Deferred
- Bug 2: Insights router DB helpers create individual connections per request. Mitigated by the Connector singleton (Bug 1 fix) but not fully pooled via SQLAlchemy engine. Low-priority optimization.

---

## Verification

### Visual fix verification (Phase 0):
- Open `/insights` in browser, confirm direction badges use the platform's green/red (not emerald/rose)
- Compare side-by-side with Signals page to confirm color match

### Bug fix verification (Phase A):
- `python -c "from lib.agents.model_routing import connect; c = connect(); c.close(); print('OK')"` — singleton Connector works
- `pytest tests/test_agent_orchestrator.py -v` — orchestrator tests pass with mocked failures in bull/bear/trader/PM
- Load test: 10 concurrent `POST /api/insights/report/SPY/refresh` — no connection exhaustion
- Admin UI: Anthropic models should not appear in dropdown until adapter is registered

### News/sentiment verification (Phase B):
- `python gcp/fetchers/fetch_news_sentiment.py --tickers SPY --dry-run` — fetches and prints without DB write
- `psql -c "SELECT COUNT(*) FROM news_sentiment WHERE ticker='SPY'"` — rows populated after real run
- Run full pipeline: `python -m lib.agents.orchestrator --ticker SPY` — sentiment section appears in report

### Earnings expansion verification (Phase C):
- Insert a test row into `earnings_calendar` with `earnings_date = NOW() + interval '3 days'`
- Run `python gcp/insight_pipeline_job.py` — verify it processes the earnings ticker

### Chat verification (Phase D):
- `curl -X POST localhost:8000/api/insights/chat -d '{"message":"test","mode":"chat","ticker":"SPY"}'` — streams Gemini response
- Open `/insights` → Chat tab → send message → streaming response renders

### Full regression:
- `pytest tests/test_agent_*.py -v` — all agent tests pass
- `pytest tests/test_routers_insights_admin.py -v` — router tests pass
- `cd platform && npx playwright test tests/insights.spec.ts tests/admin.spec.ts` — E2E passes
- Existing tabs (Dashboard, Live, Charts, Options, Playbook, Signals, Journal) unaffected — spot-check navigation

---

## Files Summary

### Create (new):
| File | Purpose |
|------|---------|
| `gcp/fetchers/fetch_news_sentiment.py` | AV NEWS_SENTIMENT fetcher |
| `.github/workflows/fetch-news-sentiment.yml` | 4-hourly sentiment fetch workflow |
| `lib/agents/anthropic_adapter.py` | Claude adapter for LLMClient |

### Modify (existing):
| File | Change |
|------|--------|
| `platform/src/components/insights/ReportCards.tsx` | Fix emerald→green, rose→red color classes |
| `platform/src/routes/InsightsPage.tsx` | Fix colors, add Chat tab |
| `lib/agents/model_routing.py` | Singleton Connector, rename `_connect` → `connect`, guard unregistered providers |
| `lib/agents/orchestrator.py` | Error handling for bull/bear/trader/PM nodes, add sentiment analyst, UTC fix |
| `lib/agents/summarizers.py` | Add `summarize_news_sentiment()`, update `build_context_bundle()` |
| `lib/agents/prompts.py` | Add `ANALYST_PROMPTS["sentiment"]`, add upgrade comments |
| `platform/api/routers/insights.py` | Fix DB connection pooling, restore chat endpoint, update `_connect` import |
| `gcp/schema.sql` | Add `news_sentiment` table |
| `gcp/insight_pipeline_job.py` | Dynamic earnings ticker resolution |
| `requirements-gcp.txt` | Add `anthropic>=0.40.0` (optional) |

### Reuse (existing utilities — do NOT reimplement):
| Utility | File |
|---------|------|
| `query_to_dataframe()` | `gcp/database.py` |
| `execute_sql()` | `gcp/database.py` |
| `get_engine()` | `gcp/database.py` |
| `StratClassifier` | `lib/strat.py` |
| AV_API_KEY secret | GitHub Actions secrets |
| `handle-workflow-failure.yml` | `.github/workflows/` |
