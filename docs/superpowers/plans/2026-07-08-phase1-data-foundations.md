# Phase 1 Data Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the ticker type-ahead with auto-ingest, a real Sector-rotation card fed by the 11 SPDR ETFs, and a News card that actually shows news (spec §5 of `docs/superpowers/specs/2026-07-07-platform-hardening-and-trade-journal-design.md`).

**Architecture:** Reuse existing seams: SYMBOL_SEARCH proxy (`GET /api/insights/ticker/search`) and watchlist-add (`POST /api/insights/watchlist/add`) already exist; the daily fetcher already unions the watchlist. New surface is small: one coverage endpoint, one sectors endpoint, one combobox component, one SQL-window fix.

**Tech Stack:** FastAPI + pandas (platform/api, gcp), React 19 + TS + HeroUI + TanStack Query (platform/src), pytest / vitest / Playwright.

## Global Constraints

- Branch: `feature/phase1-data-foundations` cut from main AFTER PR #700 merges.
- Rule 3.7: no `?? 0`/`|| 0` on financial fields; explicit unavailable states; loud API errors (503 + reason when AV key missing — never fabricated suggestions).
- Financial math in Python only. `*_pct` fields are TRUE PERCENT units.
- Single-line conventional commits, NO Co-Authored-By trailer, NO AI branding.
- Playwright specs hermetic via `page.route('**/api/config/firebase', …authMode open…)` + route mocks; local runs: vite on port 4321 with playwright.config.ts baseURL temporarily patched and REVERTED before commit.
- DB-facts already verified (2026-07-08, execution db-query-vjfwb): news fetcher healthy (1,681 articles/48h); current news filter returns 0 rows (forward-window bug); backward-48h + expanded topics returns 598 rows; `topics` values carry MIXED CASING across sources ("financial_markets" vs "Financial Markets") → filters must match case-insensitively.
- Capacity notes (Rule 0) in the PR: +11 tickers on the existing batched daily fetch job (negligible); sectors endpoint = 1 SQL query per request over ≤ ~11×30 rows; coverage endpoint = 2 batched queries per request.

---

### Task 1: `GET /api/market/coverage` (backend)

**Files:**
- Modify: `platform/api/main.py` (add next to the other `/api/market/*` handlers)
- Test: `tests/test_market_coverage.py` (create)

**Interfaces:**
- Produces: `GET /api/market/coverage?symbols=SPY,AAPL,ZZZZ` → `{"coverage": {"SPY": {"intraday": true, "daily": true}, "AAPL": {"intraday": false, "daily": true}, "ZZZZ": {"intraday": false, "daily": false}}}`. Pure helper `_coverage_from_frames(symbols: list[str], daily_tickers: set[str], intraday_tickers: set[str]) -> dict`.
- Consumes: `gcp.database.query_to_dataframe` (same import pattern as the reference endpoint in main.py).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_market_coverage.py
"""Coverage endpoint: which tickers have daily/intraday data (spec §5.1).
Pure-helper tests only — SQL is exercised by the I/O-shape assertion that
the endpoint issues exactly TWO batched queries (never per-symbol)."""
import pytest

# Import the app module the way tests/test_backtest_router_units.py does.
from tests.test_backtest_router_units import _import_platform_api  # reuse if exposed;
# otherwise copy that file's import block verbatim.
main = _import_platform_api("main")


def test_coverage_from_frames_shapes():
    cov = main._coverage_from_frames(
        ["SPY", "AAPL", "ZZZZ"],
        daily_tickers={"SPY", "AAPL"},
        intraday_tickers={"SPY"},
    )
    assert cov == {
        "SPY": {"intraday": True, "daily": True},
        "AAPL": {"intraday": False, "daily": True},
        "ZZZZ": {"intraday": False, "daily": False},
    }


def test_coverage_uppercases_and_dedupes():
    cov = main._coverage_from_frames(["spy", "SPY"], {"SPY"}, {"SPY"})
    assert list(cov) == ["SPY"]


def test_coverage_endpoint_batches_queries(monkeypatch):
    calls = []
    import pandas as pd
    def fake_query(sql, params=None):
        calls.append(sql)
        return pd.DataFrame({"ticker": ["SPY"]})
    # Patch at the site the handler imports from (adjust to actual import).
    monkeypatch.setattr(main, "_coverage_query", fake_query, raising=True)
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    r = client.get("/api/market/coverage", params={"symbols": "SPY,AAPL,IWM,QQQ,XLK"})
    assert r.status_code == 200
    assert len(calls) == 2  # one daily, one intraday — regardless of symbol count
```

Adapt import/monkeypatch mechanics to the file's real structure (read `tests/test_backtest_router_units.py` and `platform/api/main.py` first); keep the three assertions' substance.

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_market_coverage.py -v` → FAIL (helper missing).

- [ ] **Step 3: Implement**

In `platform/api/main.py`, near the other market endpoints:

```python
def _coverage_from_frames(symbols, daily_tickers, intraday_tickers):
    """Shape the coverage map. Uppercases + dedupes, preserving order."""
    out = {}
    for s in symbols:
        u = s.strip().upper()
        if not u or u in out:
            continue
        out[u] = {"intraday": u in intraday_tickers, "daily": u in daily_tickers}
    return out


def _coverage_query(sql, params=None):
    from gcp.database import query_to_dataframe
    return query_to_dataframe(sql, params)


@app.get("/api/market/coverage")
async def market_coverage(symbols: str):
    """Data coverage per symbol — drives the type-ahead's full/daily/new badges.
    Exactly two batched queries regardless of symbol count (Rule 0)."""
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()][:50]
    if not syms:
        raise HTTPException(status_code=422, detail="symbols query param required")
    daily = _coverage_query(
        "SELECT DISTINCT ticker FROM market_data_daily WHERE ticker = ANY(:syms)",
        {"syms": syms},
    )
    intraday = _coverage_query(
        "SELECT DISTINCT ticker FROM market_data_intraday WHERE ticker = ANY(:syms)",
        {"syms": syms},
    )
    return {"coverage": _coverage_from_frames(
        syms,
        set(daily["ticker"]) if daily is not None and not daily.empty else set(),
        set(intraday["ticker"]) if intraday is not None and not intraday.empty else set(),
    )}
```

Check how main.py's existing endpoints bind SQL params (`:name` + dict via SQLAlchemy text vs psycopg style) and match it; `ANY(:syms)` array binding must follow the repo's working pattern (grep for `= ANY(` in platform/api and gcp/ for a precedent; if none, use `WHERE ticker IN :syms` with `tuple(syms)` per the repo's established idiom). If the intraday table is partitioned per ticker (market_data_intraday_spy etc.), query the parent table `market_data_intraday` — it is declared in gcp/schema.sql:100 and the partitions attach to it.

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_market_coverage.py -v` → PASS.
- [ ] **Step 5: Commit** — `feat(api): market coverage endpoint for ticker type-ahead badges`

---

### Task 2: `TickerCombobox` + debounce + string ticker type

**Files:**
- Create: `platform/src/hooks/useDebouncedValue.ts`, `platform/src/components/shared/TickerCombobox.tsx`, `platform/src/components/shared/tickerCombobox.test.ts`
- Modify: `platform/src/types/index.ts:1` (`export type Ticker = string;` — keep the alias so imports don't churn), `platform/src/stores/tickerStore.ts` (add `recentTickers: string[]` + `pushRecent(t)` persisted via zustand `persist`, max 8; `availableTickers` renamed semantics → `quickPicks: ['IWM','SPY','QQQ']`), every `TickerSelect` call site (grep `<TickerSelect` — Dashboard, Signals, OptionsFlow, Journal, Insights, SwingMode) swaps to `TickerCombobox`, delete `TickerSelect.tsx`.

**Interfaces:**
- Produces: `useDebouncedValue<T>(value: T, ms: number): T`; `<TickerCombobox className?>` — input-with-chevron trigger showing `activeTicker`; opens a popover with: quick-pick row (IWM/SPY/QQQ), recents, and (≥1 typed char) suggestions from `GET /api/insights/ticker/search?keywords=&limit=8` merged with `GET /api/market/coverage?symbols=<suggestion symbols>` to render a badge per row: `full` (intraday && daily), `daily`, `new` (neither).
- Consumes: Task 1's coverage endpoint; existing search endpoint (response `{results: [{symbol, name, type, region, currency, match_score}]}`).

- [ ] **Step 1: Write the failing tests**

```ts
// platform/src/components/shared/tickerCombobox.test.ts
import { describe, expect, it } from 'vitest';
import { coverageBadge, mergeSuggestions } from './TickerCombobox';

describe('coverageBadge', () => {
  it('maps coverage to badges', () => {
    expect(coverageBadge({ intraday: true, daily: true })).toBe('full');
    expect(coverageBadge({ intraday: false, daily: true })).toBe('daily');
    expect(coverageBadge({ intraday: false, daily: false })).toBe('new');
    expect(coverageBadge(undefined)).toBe('new'); // coverage still loading/unknown → honest "new"
  });
});

describe('mergeSuggestions', () => {
  it('attaches badges to search results by symbol', () => {
    const merged = mergeSuggestions(
      [{ symbol: 'AAPL', name: 'Apple Inc', type: 'Equity', region: 'United States', currency: 'USD', match_score: 0.9 }],
      { AAPL: { intraday: false, daily: true } },
    );
    expect(merged[0]).toMatchObject({ symbol: 'AAPL', badge: 'daily' });
  });
});
```

Also add a debounce test in the same file: fake timers, assert `useDebouncedValue` only propagates after the delay — use `renderHook` from `@testing-library/react` if present in devDependencies (check package.json; MovementRead.test.tsx shows the component-testing setup); if renderHook isn't available, test the debounce logic as an extracted pure scheduler function instead.

- [ ] **Step 2: Run to verify failure** — `cd platform && npx vitest run src/components/shared/tickerCombobox.test.ts` → FAIL.

- [ ] **Step 3: Implement**

`useDebouncedValue.ts`:

```ts
import { useEffect, useState } from 'react';

/** Returns `value` after it has been stable for `ms` — for network-backed type-aheads. */
export function useDebouncedValue<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}
```

`TickerCombobox.tsx` — exported pure helpers + component:

```ts
export type CoverageBadge = 'full' | 'daily' | 'new';
export interface Coverage { intraday: boolean; daily: boolean }
export interface Suggestion { symbol: string; name: string; type: string; region: string; currency: string; match_score: number }

export function coverageBadge(c: Coverage | undefined): CoverageBadge {
  if (c?.intraday && c.daily) return 'full';
  if (c?.daily) return 'daily';
  return 'new';
}

export function mergeSuggestions(results: Suggestion[], coverage: Record<string, Coverage>) {
  return results.map((r) => ({ ...r, badge: coverageBadge(coverage[r.symbol.toUpperCase()]) }));
}
```

Component structure (follow ReplayControl.tsx's popover idiom in the same directory — trigger button + `useState(open)` + outside-click/Escape document listeners + fixed-width panel):
- Trigger: bordered button showing `activeTicker` with `<ChevronDown size={12}/>` (the affordance the old chip lacked), `data-testid="ticker-combobox"`.
- Panel: `<input autoFocus>` (styled like CommandPalette's input), quick-pick chips (IWM/SPY/QQQ from `quickPicks`), recents row, results list with name + badge chip (`full` green / `daily` blue / `new` amber), keyboard nav (ArrowUp/Down/Enter/Escape — copy CommandPalette.tsx:77-90's clamped-selection pattern).
- Data: `const debounced = useDebouncedValue(query, 300);` → TanStack `useQuery({ queryKey: ['ticker-search', debounced], enabled: debounced.length >= 1, queryFn: fetch search })`; second `useQuery({ queryKey: ['ticker-coverage', symbolsCsv], enabled: !!symbolsCsv })` over the returned symbols. Search errors render an inline error line (e.g. "search unavailable (503)") — never an empty list masquerading as no-matches.
- Selection: `setTicker(symbol)` + `pushRecent(symbol)` + close. (Auto-ingest is Task 3 — leave a `onPickNew?: (symbol: string) => void` prop hook.)

Store change (`tickerStore.ts`):

```ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface TickerState {
  activeTicker: string;
  quickPicks: string[];
  recentTickers: string[];
  setTicker: (t: string) => void;
  pushRecent: (t: string) => void;
}

export const useTickerStore = create<TickerState>()(
  persist(
    (set) => ({
      activeTicker: 'IWM',
      quickPicks: ['IWM', 'SPY', 'QQQ'],
      recentTickers: [],
      setTicker: (t) => set({ activeTicker: t.toUpperCase() }),
      pushRecent: (t) =>
        set((s) => ({
          recentTickers: [t.toUpperCase(), ...s.recentTickers.filter((x) => x !== t.toUpperCase())].slice(0, 8),
        })),
    }),
    { name: 'ticker-store', partialize: (s) => ({ activeTicker: s.activeTicker, recentTickers: s.recentTickers }) },
  ),
);
```

`availableTickers` consumers: grep for it (CommandPalette filters it) — repoint CommandPalette's Tickers group to `[...quickPicks, ...recentTickers]` deduped. `types/index.ts`: `export type Ticker = string;` — then `npx tsc --noEmit` and fix any comparisons that relied on the union (e.g. exhaustive switches) honestly.

- [ ] **Step 4: Playwright** — new `platform/tests/ticker-combobox.spec.ts`: hermetic mocks for `/api/insights/ticker/search**` (return AAPL suggestion) + `/api/market/coverage**` (AAPL daily-only) + the dashboard's other routes (copy mockCommon usage from dashboard.spec.ts); assert: combobox opens, typing "aa" shows "AAPL" with a `daily` badge, Enter sets the header ticker. Run with vite on 4321 (config patched + REVERTED).
- [ ] **Step 5: Full gates** — `npx vitest run`, `npx tsc --noEmit`, targeted Playwright — all green.
- [ ] **Step 6: Commit** — `feat(ui): ticker type-ahead combobox with coverage badges; string ticker type + persisted recents`

---

### Task 3: Auto-ingest on picking a `new` symbol

**Files:**
- Modify: `platform/src/components/shared/TickerCombobox.tsx` (implement `onPickNew` internally), the page-level notice surface (a small toast/inline notice — follow JournalPage's `exportStatus` toast pattern)
- Test: extend `platform/tests/ticker-combobox.spec.ts`

**Interfaces:**
- Consumes: existing `POST /api/insights/watchlist/add` (`insights.py:507`, body `WatchlistAddRequest` — read the model at insights.py:439 for exact field name, likely `{ticker}`), which persists to the `watchlists` Cloud SQL table that `gcp/fetchers/fetch_market_data.py` unions into the nightly universe.

- [ ] **Step 1: Playwright test first** — mock `POST /api/insights/watchlist/add` (assert it gets called with AAPL) after selecting a `new`-badged suggestion; assert the notice "Tracking AAPL — daily data lands after tonight's fetch" appears; assert selecting a `full` ticker does NOT call it.
- [ ] **Step 2: Implement** — on selection where `badge === 'new'`: fire the POST via `useMutation`; on success show the notice; on failure show a loud inline error ("couldn't add AAPL to tracking — HTTP 503: <detail>") and STILL set the active ticker (browsing is allowed; pages show their unavailable states). Never swallow the error.
- [ ] **Step 3: Gates + commit** — `feat(ui): picking an untracked ticker auto-adds it to the watchlist with an honest ingest notice`

---

### Task 4: SPDR sector ETFs into the daily fetch universe

**Files:**
- Modify: `gcp/fetchers/fetch_market_data.py:33` and the `AV_SYMBOL_MAP` at `:37-42`
- Test: `tests/test_fetch_market_data_universe.py` (create)

**Interfaces:**
- Produces: module constant `SECTOR_ETFS = ['XLK','XLF','XLE','XLV','XLI','XLY','XLP','XLU','XLB','XLRE','XLC']`; `TICKERS = ['IWM','SPY','QQQ','SPX'] + SECTOR_ETFS`; each sector ETF present in `AV_SYMBOL_MAP` mapping to itself.

- [ ] **Step 1: Failing test**

```python
# tests/test_fetch_market_data_universe.py
"""The 11 SPDR sector ETFs ride the existing daily fetch (spec §5.2)."""
from gcp.fetchers import fetch_market_data as f

SECTORS = {'XLK','XLF','XLE','XLV','XLI','XLY','XLP','XLU','XLB','XLRE','XLC'}

def test_sector_etfs_in_universe():
    assert SECTORS <= set(f.TICKERS)
    assert {'IWM','SPY','QQQ','SPX'} <= set(f.TICKERS)

def test_sector_etfs_have_av_symbols():
    for t in SECTORS:
        assert f.AV_SYMBOL_MAP.get(t) == t
```

(If importing the fetcher pulls heavy deps at module import, mirror however existing fetcher tests import it — check tests/ for a fetch_market_data test precedent first.)

- [ ] **Step 2-4: fail → implement (two-line constant change) → pass.**
- [ ] **Step 5: Commit** — `feat(fetchers): add 11 SPDR sector ETFs to the daily universe` with capacity note in the body: `+11 symbols on the existing batched daily job; ~11 extra AV calls/day, well under key limits`.
- [ ] **Runbook note (PR description, not code):** after deploy, backfill ≥30 trading days: dispatch the market-data Cloud Run job (or workflow fallback) with `--tickers "XLK XLF XLE XLV XLI XLY XLP XLU XLB XLRE XLC"` per its existing backfill flags — verify the exact flag names from `fetch_market_data.py main()` before running.

---

### Task 5: `GET /api/market/sectors` (backend)

**Files:**
- Modify: `platform/api/main.py` (beside coverage endpoint)
- Test: `tests/test_market_sectors.py` (create)

**Interfaces:**
- Produces: `{"as_of": "YYYY-MM-DD" | null, "sectors": [{"symbol": "XLK", "name": "Technology", "close": 245.1, "chg_1d_pct": 0.42, "chg_5d_pct": -1.3, "status": "ok"} | {"symbol": "XLRE", "name": "Real Estate", "status": "unavailable", "reason": "no rows"}], "status": "ok" | "unavailable"}` — `*_pct` in TRUE PERCENT. Pure helper `_sector_rotation_from_df(df) -> tuple[str | None, list[dict]]` where df has columns ticker/date/close (last 6 trading days per ticker).
- Name map constant: `SECTOR_NAMES = {"XLK": "Technology", "XLF": "Financials", "XLE": "Energy", "XLV": "Health Care", "XLI": "Industrials", "XLY": "Cons. Discretionary", "XLP": "Cons. Staples", "XLU": "Utilities", "XLB": "Materials", "XLRE": "Real Estate", "XLC": "Communication"}`.

- [ ] **Step 1: Failing test**

```python
# tests/test_market_sectors.py
import pandas as pd
import pytest
# import main per the established pattern

def _df():
    rows = []
    for i, close in enumerate([100, 101, 102, 103, 104, 105]):  # 6 sessions, oldest first
        rows.append({"ticker": "XLK", "date": f"2026-07-0{i+1}", "close": close})
    rows.append({"ticker": "XLF", "date": "2026-07-06", "close": 50})  # only 1 row → 1d/5d unavailable
    return pd.DataFrame(rows)

def test_sector_rotation_math():
    as_of, sectors = main._sector_rotation_from_df(_df())
    assert as_of == "2026-07-06"
    xlk = next(s for s in sectors if s["symbol"] == "XLK")
    assert xlk["status"] == "ok"
    assert xlk["chg_1d_pct"] == pytest.approx((105 - 104) / 104 * 100, abs=1e-6)
    assert xlk["chg_5d_pct"] == pytest.approx((105 - 100) / 100 * 100, abs=1e-6)
    xlf = next(s for s in sectors if s["symbol"] == "XLF")
    assert xlf["status"] == "unavailable"  # one row: no prior close → no fabricated 0
    missing = next(s for s in sectors if s["symbol"] == "XLE")
    assert missing["status"] == "unavailable"

def test_sector_rotation_all_missing():
    as_of, sectors = main._sector_rotation_from_df(pd.DataFrame(columns=["ticker","date","close"]))
    assert as_of is None
    assert all(s["status"] == "unavailable" for s in sectors)
```

- [ ] **Step 2-4: fail → implement → pass.** Implementation: one SQL pulling the last 6 trading dates of closes for the 11 symbols (`SELECT ticker, date, close FROM market_data_daily WHERE ticker = ANY(...) AND date >= (SELECT max(date) FROM market_data_daily) - INTERVAL '10 days' ORDER BY ticker, date`), then per-symbol pandas: `chg_1d_pct = (last - prev)/prev*100` (needs ≥2 rows), `chg_5d_pct = (last - first_of_window)/first*100` (needs ≥6 rows else omit field, keep status ok if 1d present — decide: status "ok" requires 1d; 5d nullable `None` rendered as —). All-missing → top-level `status: "unavailable"` with reason `"sector ETFs not ingested yet — run the SPDR backfill"`. Endpoint caches via TTLCache 10 min (copy backtest.py's pattern).
- [ ] **Step 5: Commit** — `feat(api): sector rotation endpoint computed from market_data_daily SPDR closes`

---

### Task 6: Dashboard Sector-rotation card

**Files:**
- Modify: `platform/src/routes/DashboardPage.tsx:630-636` (the hardcoded `<Unavailable>` card)
- Test: `platform/tests/dashboard.spec.ts` (extend) or a new sector-card spec; vitest for the bar-scaling helper.

**Interfaces:**
- Consumes: Task 5's response shape verbatim.
- Produces: exported `sectorBarWidthPct(chg: number, maxAbs: number): number` (0-100, sign handled by CSS side).

- [ ] **Step 1: vitest first** — `sectorBarWidthPct(2, 4) === 50`, `sectorBarWidthPct(-4, 4) === 100`, `maxAbs === 0` → 0 (no NaN).
- [ ] **Step 2: Implement** — `useFetch(['market-sectors'], '/api/market/sectors')` (same helper other cards use); render ranked by `chg_1d_pct` desc: name, signed percent (2 decimals, tone bull/bear via comparison — allowed), horizontal bar scaled by `sectorBarWidthPct`; per-row `status: "unavailable"` renders the symbol with "—"; top-level unavailable keeps an honest `<Unavailable msg={reason}>`; header meta gets `as of {as_of}` and a 1D/5D segctrl toggle (5D uses `chg_5d_pct`, rows missing it show "—").
- [ ] **Step 3: Playwright** — mocked `/api/market/sectors` with 3 ok rows + 1 unavailable: assert ranked order, an em-dash row, and the toggle switching values.
- [ ] **Step 4: Gates + commit** — `feat(dashboard): real sector rotation card fed by SPDR daily closes`

---

### Task 7: News window + topic fix

**Files:**
- Modify: `platform/api/routers/catalysts.py:196-259` (news block), `platform/src/routes/DashboardPage.tsx` news card (~lines 345-348 newsFeed memo + card at 657-679)
- Test: `tests/test_catalysts_news_filter.py` (create)

**Interfaces:**
- Produces: news rows in the catalysts response gain `"catalyst_type": "NEWS_*"` as today PLUS reliable presence when recent news exists: the news SQL becomes backward-looking and case-insensitive, DECOUPLED from the forward event window. New module constants `NEWS_LOOKBACK_HOURS = 48` and `NEWS_TOPICS = ['mergers_and_acquisitions','earnings','ipo','economy_monetary','technology','financial_markets','life_sciences']`.

- [ ] **Step 1: Failing test**

```python
# tests/test_catalysts_news_filter.py
"""News is inherently backward-looking; the catalyst window is forward.
DB-verified 2026-07-08 (exec db-query-vjfwb): the old shared-window filter
returned 0 rows while 1,681 articles existed in the trailing 48h; topics
carry mixed casing across sources, so matching must be case-insensitive."""
# import catalysts router module per established pattern

def test_news_sql_is_backward_looking_and_case_insensitive():
    sql = catalysts._news_sql()
    assert "NEWS_LOOKBACK_HOURS" not in sql          # interpolated, not literal
    assert ":lookback_hours" in sql or "INTERVAL" in sql
    assert "published_ts >=" in sql                   # backward window
    assert ":d_from" not in sql                       # decoupled from event window
    assert "lower(" in sql.lower()                    # case-insensitive topic match

def test_news_topics_constant_covers_fetcher_topics():
    assert {"technology", "financial_markets", "life_sciences"} <= set(catalysts.NEWS_TOPICS)
```

- [ ] **Step 2-3: fail → implement.** Extract the news SQL into `_news_sql()` returning:

```sql
SELECT ticker, published_ts::date AS date, title,
       overall_sentiment_label, sentiment_score,
       relevance_score, topics, url
FROM news_sentiment
WHERE published_ts >= NOW() - (:lookback_hours || ' hours')::interval
  AND relevance_score >= 0.7
  AND EXISTS (
    SELECT 1 FROM unnest(topics) AS t
    WHERE lower(t) = ANY(:topics)
  )
```

with `params = {"lookback_hours": NEWS_LOOKBACK_HOURS, "topics": NEWS_TOPICS}` (all NEWS_TOPICS lowercase; verify the array-bind idiom works with the repo's query_to_dataframe — if `= ANY(:topics)` binding fails, fall back to the `&&` operator against a lowercased array expression and prove it with the test). The topic→catalyst_type mapping keeps its precedence and stays case-insensitive (`topics_lower = [t.lower() for t in topics]`). The rest of `_db_catalyst_events` (econ/8-K, forward window) is untouched.
- [ ] **Step 4: Frontend** — the news card already filters `catalystFeed` for `sentiment_label || catalyst_type === 'NEWS'`; update the memo to match on `catalyst_type.startsWith('NEWS') || catalyst_type in {MERGER_ACQUISITION, IPO, ECONOMIC, EARNINGS_NEWS}` OR simply `e.source === 'AV news'` (cleanest — the field already exists); render `source` + relative published-time on each row; drop news rows from crowding: build `newsFeed` from the FULL events array (not the top-5 `catalystFeed` slice) filtered to AV-news rows, slice(0, 4).
- [ ] **Step 5: Playwright** — mocked catalysts response containing 2 news rows dated yesterday + 3 forward events: assert the News card shows "2 fresh" and both headlines (would show "0 fresh" pre-fix since news is backward-dated).
- [ ] **Step 6: Gates + commit** — `fix(catalysts): news gets its own backward-looking window with case-insensitive topics`

---

## Final verification

- [ ] `python -m pytest tests/test_market_coverage.py tests/test_market_sectors.py tests/test_catalysts_news_filter.py tests/test_fetch_market_data_universe.py -v` → all pass
- [ ] `cd platform && npx tsc --noEmit && npx vitest run && npm run build` → clean
- [ ] Playwright: ticker-combobox + dashboard sector/news specs green (mocked)
- [ ] PR carries the Rule-0 capacity notes and the SPDR backfill runbook step gated on deploy
