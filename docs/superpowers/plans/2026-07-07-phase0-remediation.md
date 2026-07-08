# Phase 0 Remediation Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the twelve correctness/layout/honesty defects catalogued in spec §4 of `docs/superpowers/specs/2026-07-07-platform-hardening-and-trade-journal-design.md` so every number the site shows is correct and every chart stays in its section.

**Architecture:** Small, independent fixes. Unit conversions move INTO Python (backend emits percent units); React only formats. Chart sizing moves to props owned by callers. One new backend endpoint (`POST /api/live/signal-series`) replaces the client-side signal voter.

**Tech Stack:** FastAPI + pandas (platform/api), React 19 + TS + recharts + lightweight-charts (platform/src), vitest (`cd platform && npx vitest run`), Playwright (`cd platform && npx playwright test`), pytest (`python -m pytest tests/ -k <name>`).

## Global Constraints

- No `?? 0` / `|| 0` on financial fields; missing values render "—" and are excluded from aggregates (Rule 3.7).
- All financial math lives in Python; the frontend renders (spec §3).
- Client indicator math must be replaced by production `lib/` paths, never re-implemented (Rule 3.6).
- Conventional commits, no AI branding. Branch: `feature/platform-hardening-journal`.
- Percent-unit convention (this plan establishes it): every API field named `*_pct` is in TRUE PERCENT units (0.29 means 0.29%). `win_rate` is a 0–1 fraction; UI multiplies by 100. Document this in `platform/api/routers/backtest.py` module docstring.
- Playwright specs use the hermetic auth mock: `page.route('**/api/config/firebase', r => r.fulfill({ status: 200, body: JSON.stringify({ authMode: 'open', firebase: null }) }))`.

---

### Task 1: Backtest API — percent units + run selection

**Files:**
- Modify: `platform/api/routers/backtest.py`
- Test: `tests/test_backtest_router_units.py` (create)

**Interfaces:**
- Produces: `_summarize_returns(df) -> dict` where `avg_return_pct`, `avg_win_pct`, `avg_loss_pct`, `total_return_pct` are ×100 percent values; `win_rate` stays a 0–1 fraction. Per-trade records gain `return_pct` in percent units via `_trades_to_percent_records(df)`. Endpoints `GET /api/backtest/results/{ticker}?run=`, `GET /api/backtest/equity/{ticker}?run=` accept an optional `run` timestamp (`YYYYMMDD_HHMMSS`); omitted → newest. `/api/backtest/all/{ticker}` run entries' `avg_return_pct` also percent units.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backtest_router_units.py
"""Backtest router unit-convention tests (spec §4 items 0.2, 0.6).

The BacktestEngine writes return_pct as a raw fraction (0.003 = 0.3%).
The router must emit TRUE PERCENT units for every *_pct field so the
frontend can render `${v.toFixed(2)}%` without unit knowledge.
win_rate stays a 0-1 fraction (UI multiplies by 100).
"""
import pandas as pd
import pytest

from platform_api_import_helper import import_router  # see step 3 note

backtest = import_router("backtest")


def _df():
    return pd.DataFrame({
        "return_pct": [0.003, -0.002, 0.004, -0.001],  # fractions from the engine
        "entry_time": ["2026-01-02 10:00"] * 4,
    })


def test_summarize_returns_emits_percent_units():
    s = backtest._summarize_returns(_df())
    assert s["avg_return_pct"] == pytest.approx(0.1)     # mean fraction 0.001 -> 0.1%
    assert s["avg_win_pct"] == pytest.approx(0.35)       # (0.3+0.4)/2 %
    assert s["avg_loss_pct"] == pytest.approx(-0.15)     # (-0.2+-0.1)/2 %
    assert s["total_return_pct"] == pytest.approx(0.4)
    assert s["win_rate"] == pytest.approx(0.5)           # stays a fraction


def test_trade_records_emit_percent_units():
    recs = backtest._trades_to_percent_records(_df())
    assert recs[0]["return_pct"] == pytest.approx(0.3)


def test_run_pattern_accepts_specific_timestamp():
    pat = backtest._backtest_pattern("SPY", run="20260222_231417")
    assert pat == r"^backtest_SPY_20260222_231417\.csv$"
```

If no `platform_api_import_helper` exists in `tests/`, inline the import the way existing platform tests do it (check `tests/test_platform_auth.py` for the established sys.path pattern and copy it — do NOT invent a new mechanism).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backtest_router_units.py -v`
Expected: FAIL (`_trades_to_percent_records` not defined; `avg_return_pct == 0.001`).

- [ ] **Step 3: Implement**

In `platform/api/routers/backtest.py`:

```python
def _backtest_pattern(ticker_upper: str, run: str | None = None) -> str:
    if run:
        return rf"^backtest_{re.escape(ticker_upper)}_{re.escape(run)}\.csv$"
    return rf"^backtest_{re.escape(ticker_upper)}_\d{{8}}_\d{{6}}\.csv$"

def _equity_pattern(ticker_upper: str, run: str | None = None) -> str:
    if run:
        return rf"^equity_{re.escape(ticker_upper)}_{re.escape(run)}\.csv$"
    return rf"^equity_{re.escape(ticker_upper)}_\d{{8}}_\d{{6}}\.csv$"
```

```python
def _summarize_returns(df: pd.DataFrame) -> dict:
    """Summary stats. UNITS: the engine writes return_pct as a raw fraction
    (0.003 = 0.3%). Every *_pct field emitted here is converted to TRUE
    PERCENT; win_rate stays a 0-1 fraction (UI renders *100)."""
    summary: dict = {}
    if "return_pct" not in df.columns:
        return summary
    returns = df["return_pct"].dropna().astype(float) * 100.0  # fraction -> percent
    if len(returns) == 0:
        return summary
    wins = returns[returns > 0]
    losses = returns[returns <= 0]
    return {
        "total_trades": len(returns),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(len(wins) / len(returns), 4),
        "avg_return_pct": round(returns.mean(), 4),
        "avg_win_pct": round(wins.mean(), 4) if len(wins) else None,
        "avg_loss_pct": round(losses.mean(), 4) if len(losses) else None,
        "total_return_pct": round(returns.sum(), 4),
    }


def _trades_to_percent_records(df: pd.DataFrame) -> list[dict]:
    """Per-trade records with return_pct converted fraction -> percent."""
    df = df.copy()
    if "return_pct" in df.columns:
        df["return_pct"] = df["return_pct"].astype(float) * 100.0
    return _dataframe_to_records(df)
```

- `get_backtest_results(ticker: str, run: str | None = None)`: pass `run` into `_backtest_pattern`, cache key `f"{ticker_upper}:{run or 'latest'}"`, and build `trades = _trades_to_percent_records(df)`.
- `get_equity_curve(ticker: str, run: str | None = None)`: same pattern/cache-key change (`_EQUITY_CACHE`).
- In `list_all_backtests`, the per-run stat becomes `info["avg_return_pct"] = round(returns.mean() * 100.0, 4) if len(returns) else None` (compute `returns` before multiplying win counts; `win_rate` unchanged).
- FastAPI turns the `run: str | None = None` keyword into a query param automatically. Validate: `if run and not re.fullmatch(r"\d{8}_\d{6}", run): raise HTTPException(422, "run must be YYYYMMDD_HHMMSS")`.
- Update the module docstring with the percent-unit convention paragraph from Global Constraints.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_backtest_router_units.py -v`
Expected: PASS (3/3).

- [ ] **Step 5: Commit**

```bash
git add platform/api/routers/backtest.py tests/test_backtest_router_units.py
git commit -m "fix(api): backtest *_pct fields emit true percent units; run query param selects a specific run"
```

---

### Task 2: BacktesterSection — correct formatting + run selector

**Files:**
- Modify: `platform/src/components/backtest/BacktesterSection.tsx`
- Test: `platform/src/components/backtest/BacktesterSection.format.test.ts` (create)

**Interfaces:**
- Consumes: Task 1's percent-unit contract and `?run=` params.
- Produces: exported pure helpers `fmtEquityTick(v: number, range: number): string` and `fmtRunDate(d: string): string` (unit-testable formatters).

- [ ] **Step 1: Write the failing test**

```ts
// platform/src/components/backtest/BacktesterSection.format.test.ts
import { describe, expect, it } from 'vitest';
import { fmtEquityTick, fmtRunDate } from './BacktesterSection';

describe('fmtEquityTick', () => {
  it('uses decimals on a normalized (~1.0) equity range so ticks never repeat', () => {
    // range 0.07 (e.g. 0.98..1.05): needs 3 decimals
    expect(fmtEquityTick(1.0123, 0.07)).toBe('$1.012');
    expect(fmtEquityTick(0.9871, 0.07)).toBe('$0.987');
  });
  it('uses whole dollars on account-scale ranges', () => {
    expect(fmtEquityTick(10500, 4000)).toBe('$10500');
  });
});

describe('fmtRunDate', () => {
  it('keeps the year so multi-year curves read chronologically', () => {
    expect(fmtRunDate('2023-04-21')).toBe('04/21/23');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd platform && npx vitest run src/components/backtest/BacktesterSection.format.test.ts`
Expected: FAIL — helpers not exported.

- [ ] **Step 3: Implement**

In `BacktesterSection.tsx`:

```ts
/** Adaptive-decimal equity tick: enough decimals for the visible range. */
export function fmtEquityTick(v: number, range: number): string {
  const dec = range > 50 ? 0 : range > 5 ? 1 : range > 0.5 ? 2 : 3;
  return `$${Number(v).toFixed(dec)}`;
}

/** YYYY-MM-DD -> MM/DD/YY (keeps year; fixes the jumbled multi-year axis). */
export function fmtRunDate(d: string): string {
  const s = String(d);
  return `${s.slice(5, 7)}/${s.slice(8, 10)}/${s.slice(2, 4)}`;
}
```

Apply in `EquityCurve` (compute `range` from values once with `Math.max(...vals) - Math.min(...vals)` over non-null values):
- `XAxis tickFormatter={fmtRunDate}` (replaces `String(d).slice(5)`, line 170)
- `YAxis tickFormatter={v => fmtEquityTick(Number(v), range)}` (replaces `$${Number(v).toFixed(0)}`, line 175)
- Tooltip formatter: `formatter={(v) => [v == null ? '—' : `$${Number(v).toFixed(2)}`, 'Value']}` (removes the `|| 0`).

Metric cards (backend now sends percent units — rendering stays `.toFixed(2)` and is now correct; no change needed at lines 355/360/365, but VERIFY against a live response). Trade-table `Return %` column (line 229) also now receives percent units — no code change, verify only.

Run selector: add local state `const [selectedRun, setSelectedRun] = useState<string | null>(null);` — a plain `<select>` styled like existing `.segctrl` controls, options from `runs.map(r => r.timestamp)`, value `selectedRun ?? latestRun?.timestamp`. Thread into the hooks: extend `useBacktestResults(ticker, enabled, run?: string | null)` and `useEquity(ticker, enabled, run?)` (they live in this file or `platform/src/hooks/` — follow where the imports point) to append `run ? `?run=${run}` : ''` to the fetch URL and include `run` in the queryKey. Header text: `most recent: ${latestRun?.timestamp}` becomes `viewing: ${selectedRun ?? latestRun?.timestamp ?? ''}`.

- [ ] **Step 4: Run tests**

Run: `cd platform && npx vitest run src/components/backtest/BacktesterSection.format.test.ts && npx tsc --noEmit`
Expected: PASS + clean compile.

- [ ] **Step 5: Commit**

```bash
git add platform/src/components/backtest/BacktesterSection.tsx platform/src/components/backtest/BacktesterSection.format.test.ts platform/src/hooks
git commit -m "fix(backtester): year-keeping x-axis, adaptive equity ticks, run selector, percent-unit alignment"
```

---

### Task 3: Dashboard — avg-return 100× fix + honest signals count

**Files:**
- Modify: `platform/src/routes/DashboardPage.tsx:467,573`
- Test: `platform/src/routes/DashboardPage.avgReturn.test.ts` (create)

**Interfaces:**
- Consumes: `/api/playbook/{ticker}` `top card avg_return` — ALREADY percent units (`playbook.py:312`).
- Produces: exported helper `topSetupAvgReturn(v: number | null | undefined): string`.

- [ ] **Step 1: Write the failing test**

```ts
// platform/src/routes/DashboardPage.avgReturn.test.ts
import { describe, expect, it } from 'vitest';
import { topSetupAvgReturn } from './DashboardPage';

describe('topSetupAvgReturn', () => {
  it('renders API percent units without re-multiplying (0.29 -> +0.29%)', () => {
    expect(topSetupAvgReturn(0.29)).toBe('+0.29%');
  });
  it('renders missing as em dash', () => {
    expect(topSetupAvgReturn(null)).toBe('—');
    expect(topSetupAvgReturn(undefined)).toBe('—');
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd platform && npx vitest run src/routes/DashboardPage.avgReturn.test.ts`
Expected: FAIL — not exported.

- [ ] **Step 3: Implement**

In `DashboardPage.tsx` add near the other helpers (~line 145):

```ts
/** Playbook avg_return arrives in PERCENT units (playbook.py _pct). Render as-is. */
export function topSetupAvgReturn(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}
```

Line 467 becomes:

```tsx
<Metric value={topSetupAvgReturn(topCard.avg_return)} tone={(topCard.avg_return ?? 0) >= 0 ? 'bull' : 'bear'} />
```

(the `?? 0` here selects a CSS tone, not a rendered financial value — allowed.)

Line 573 meta becomes honest while loading:

```tsx
meta={`${activeTicker} · ${signalsResp?.count != null ? signalsResp.count.toLocaleString() : '—'}`}
```

- [ ] **Step 4: Run tests**

Run: `cd platform && npx vitest run src/routes/DashboardPage.avgReturn.test.ts && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add platform/src/routes/DashboardPage.tsx platform/src/routes/DashboardPage.avgReturn.test.ts
git commit -m "fix(dashboard): stop 100x-inflating top-setup avg return; honest signals count while loading"
```

---

### Task 4: CandlestickChart minHeight prop + dashboard slot clip

**Files:**
- Modify: `platform/src/components/charts/CandlestickChart.tsx:306-312`, `platform/src/routes/DashboardPage.tsx:548`, `platform/src/routes/ChartsPage.tsx` (the `<CandlestickChart` usage ~line 688)
- Test: `platform/tests/dashboard-chart-fit.spec.ts` (create)

**Interfaces:**
- Produces: `CandlestickChart` prop `minHeight?: number` (default `undefined` = no floor).

- [ ] **Step 1: Write the failing test**

```ts
// platform/tests/dashboard-chart-fit.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Dashboard intraday candle chart', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/config/firebase', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ authMode: 'open', firebase: null }) })
    );
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
  });

  test('candle chart stays inside its 260px card slot', async ({ page }) => {
    // Switch to Candles if not default
    const candlesBtn = page.getByRole('button', { name: 'Candles', exact: true });
    if (await candlesBtn.isVisible()) await candlesBtn.click();
    await page.waitForTimeout(1500); // chart create
    const slot = page.locator('[data-testid="intraday-chart-slot"]');
    await expect(slot).toBeVisible();
    const slotBox = await slot.boundingBox();
    const canvas = slot.locator('canvas').first();
    const canvasBox = await canvas.boundingBox();
    expect(slotBox).not.toBeNull();
    expect(canvasBox).not.toBeNull();
    // Canvas must not extend below the slot.
    expect(canvasBox!.y + canvasBox!.height).toBeLessThanOrEqual(slotBox!.y + slotBox!.height + 2);
    expect(canvasBox!.height).toBeLessThanOrEqual(262);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd platform && npx playwright test tests/dashboard-chart-fit.spec.ts`
Expected: FAIL — no `data-testid="intraday-chart-slot"` yet (and once added without the fix, the height assertion fails at ~400px).

- [ ] **Step 3: Implement**

`CandlestickChart.tsx` — add to props interface: `minHeight?: number;` and change the return (lines 306–312):

```tsx
return (
  <div
    ref={containerRef}
    className="h-full w-full"
    style={minHeight != null ? { minHeight } : undefined}
  />
);
```

`ChartsPage.tsx` candle usage: add `minHeight={400}` (preserves /charts exactly as today).

`DashboardPage.tsx:548`:

```tsx
<div data-testid="intraday-chart-slot" className="overflow-hidden" style={{ height: 260 }}>
```

- [ ] **Step 4: Run tests**

Run: `cd platform && npx playwright test tests/dashboard-chart-fit.spec.ts && npx tsc --noEmit`
Expected: PASS. Also manually confirm /charts still renders a ≥400px chart (screenshot).

- [ ] **Step 5: Commit**

```bash
git add platform/src/components/charts/CandlestickChart.tsx platform/src/routes/DashboardPage.tsx platform/src/routes/ChartsPage.tsx platform/tests/dashboard-chart-fit.spec.ts
git commit -m "fix(charts): candle chart minHeight becomes caller-owned prop; dashboard slot clips at 260px"
```

---

### Task 5: PriceAreaChart formatter props

**Files:**
- Modify: `platform/src/components/charts/PriceAreaChart.tsx`
- Test: `platform/src/components/charts/priceAreaFormat.test.ts` (create)

**Interfaces:**
- Produces: props `valueFormatter?: (v: number) => string` (y-axis ticks) and `tooltipFormatter?: (v: number) => string`; exported `defaultPriceTick(v: number, range: number): string`. Task 6 consumes these on /journal.

- [ ] **Step 1: Write the failing test**

```ts
// platform/src/components/charts/priceAreaFormat.test.ts
import { describe, expect, it } from 'vitest';
import { defaultPriceTick } from './PriceAreaChart';

describe('defaultPriceTick', () => {
  it('keeps whole dollars for wide price ranges', () => {
    expect(defaultPriceTick(298.4, 8)).toBe('$298');
  });
  it('adds decimals for sub-dollar ranges so ticks never repeat', () => {
    expect(defaultPriceTick(1.012, 0.08)).toBe('$1.01');
    expect(defaultPriceTick(0.981, 0.08)).toBe('$0.98');
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd platform && npx vitest run src/components/charts/priceAreaFormat.test.ts`
Expected: FAIL — not exported.

- [ ] **Step 3: Implement**

In `PriceAreaChart.tsx`:

```ts
/** Default dollar tick with range-adaptive decimals (never repeated ticks). */
export function defaultPriceTick(v: number, range: number): string {
  const dec = range > 5 ? 0 : range > 0.5 ? 1 : 2;
  return `$${Number(v).toFixed(dec)}`;
}
```

Props interface additions:

```ts
  /** Y-axis tick formatter. Default: dollar with range-adaptive decimals. */
  valueFormatter?: (v: number) => string;
  /** Tooltip value formatter. Default: `$X.XX`. */
  tooltipFormatter?: (v: number) => string;
```

- Destructure with defaults: `valueFormatter`, `tooltipFormatter`.
- Compute `const range = yDomain[1] - yDomain[0];` after the existing `yDomain` memo.
- YAxis (line 154): `tickFormatter={(v) => (valueFormatter ?? ((x: number) => defaultPriceTick(x, range)))(Number(v))}`.
- `PriceTooltip` gains a `format` prop `(v: number) => string`; the body renders `value == null ? '—' : format(Number(value))` (kills the `?? 0` at line 69). Pass `format={tooltipFormatter ?? ((v) => `$${v.toFixed(2)}`)}` from the parent at the `<Tooltip content={...}>` site.

- [ ] **Step 4: Run tests**

Run: `cd platform && npx vitest run src/components/charts/priceAreaFormat.test.ts && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add platform/src/components/charts/PriceAreaChart.tsx platform/src/components/charts/priceAreaFormat.test.ts
git commit -m "fix(charts): PriceAreaChart formatter props; adaptive default ticks; no ?? 0 in tooltip"
```

---

### Task 6: Journal — exclude null returns + percent-labeled equity curve

**Files:**
- Modify: `platform/src/routes/JournalPage.tsx:169-185,293-296,304,436,450-452`
- Test: `platform/src/routes/journalStats.test.ts` (create), and extract pure logic to `platform/src/lib/journalStats.ts` (create)

**Interfaces:**
- Consumes: Task 5's `valueFormatter`/`tooltipFormatter` props.
- Produces: `computeJournalStats(entries: {return_pct?: number | null; exit_ts?: string; entry_ts: string}[]) -> { closedCount, totalCount, winRate, avgReturn, totalReturn, avgWin, equityPoints }` in `platform/src/lib/journalStats.ts` — null `return_pct` entries are EXCLUDED from every stat and from the equity curve.

- [ ] **Step 1: Write the failing test**

```ts
// platform/src/routes/journalStats.test.ts
import { describe, expect, it } from 'vitest';
import { computeJournalStats } from '@/lib/journalStats';

const E = (ret: number | null, ts: string) =>
  ({ return_pct: ret, entry_ts: ts, exit_ts: ts });

describe('computeJournalStats', () => {
  it('excludes null-return entries from every aggregate (no fake 0% trades)', () => {
    const s = computeJournalStats([E(2, '2026-01-02'), E(null, '2026-01-03'), E(-1, '2026-01-04')]);
    expect(s.closedCount).toBe(2);
    expect(s.totalCount).toBe(3);
    expect(s.winRate).toBeCloseTo(50);
    expect(s.avgReturn).toBeCloseTo(0.5);
    expect(s.totalReturn).toBeCloseTo(1);
    expect(s.equityPoints).toHaveLength(2); // null entry contributes NO point
  });
  it('returns null stats when no entry has a return', () => {
    const s = computeJournalStats([E(null, '2026-01-02')]);
    expect(s.winRate).toBeNull();
    expect(s.avgReturn).toBeNull();
    expect(s.equityPoints).toHaveLength(0);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd platform && npx vitest run src/routes/journalStats.test.ts`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`platform/src/lib/journalStats.ts`:

```ts
import type { PricePoint } from '@/components/charts/PriceAreaChart';

export interface JournalStatEntry {
  return_pct?: number | null;
  entry_ts: string;
  exit_ts?: string | null;
}

export interface JournalStats {
  closedCount: number;
  totalCount: number;
  winRate: number | null;      // percent 0-100
  avgReturn: number | null;    // percent units
  totalReturn: number | null;  // percent units
  avgWin: number | null;       // percent units
  equityPoints: PricePoint[];  // cumulative % across entries WITH returns
}

/** Aggregate journal stats. Entries with null/undefined return_pct are
 * excluded from every aggregate — a missing return is NOT a 0% trade. */
export function computeJournalStats(entries: JournalStatEntry[]): JournalStats {
  const withRet = entries.filter((e): e is JournalStatEntry & { return_pct: number } =>
    typeof e.return_pct === 'number' && !Number.isNaN(e.return_pct));
  const returns = withRet.map((e) => e.return_pct);
  const wins = returns.filter((r) => r > 0);
  const sum = returns.reduce((a, b) => a + b, 0);
  const sorted = [...withRet].sort((a, b) =>
    (a.exit_ts || a.entry_ts).localeCompare(b.exit_ts || b.entry_ts));
  let cum = 0;
  const equityPoints: PricePoint[] = sorted.map((e, i) => {
    cum += e.return_pct;
    return { time: i, price: cum, label: (e.exit_ts || e.entry_ts).slice(0, 10) };
  });
  return {
    closedCount: withRet.length,
    totalCount: entries.length,
    winRate: returns.length ? (wins.length / returns.length) * 100 : null,
    avgReturn: returns.length ? sum / returns.length : null,
    totalReturn: returns.length ? sum : null,
    avgWin: wins.length ? wins.reduce((a, b) => a + b, 0) / wins.length : null,
    equityPoints,
  };
}
```

`JournalPage.tsx`:
- Replace lines 169–185 with `const stats = computeJournalStats(entries);` and destructure.
- KPI tiles (lines 292–296): `Trades` value `String(stats.totalCount)` with sub `` `${stats.closedCount} closed · ${wins}` `` style; add a footer note when `stats.closedCount < stats.totalCount`: `<p className="text-[11px] text-[var(--on-surface-muted)]">{stats.totalCount - stats.closedCount} open/unreturned trade(s) excluded from stats</p>`.
- Equity curve (line 304): `<PriceAreaChart data={stats.equityPoints} seriesLabel="Cumulative P&L" height={240} valueFormatter={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`} tooltipFormatter={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`} />`.
- Table row (lines 436, 450–452): replace `const ret = e.return_pct ?? 0;` with `const ret = e.return_pct;` and render `{ret == null ? <span className="text-[var(--on-surface-muted)]">—</span> : <span className={...}>{ret >= 0 ? '+' : ''}{ret.toFixed(2)}%</span>}` (tone classes only when `ret != null`).

- [ ] **Step 4: Run tests**

Run: `cd platform && npx vitest run src/routes/journalStats.test.ts && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add platform/src/lib/journalStats.ts platform/src/routes/journalStats.test.ts platform/src/routes/JournalPage.tsx
git commit -m "fix(journal): null returns excluded from stats and equity curve; percent-labeled axis"
```

---

### Task 7: ET-correct "today" helper

**Files:**
- Create: `platform/src/lib/dates.ts`
- Modify: `platform/src/routes/DashboardPage.tsx:147-149`, `platform/src/routes/PlaybookPage.tsx:59-60`, `platform/src/routes/CatalystsPage.tsx:177,368,430`
- Test: `platform/src/lib/dates.test.ts` (create)

**Interfaces:**
- Produces: `todayET(): string` (YYYY-MM-DD in America/New_York), `toETDateString(d: Date): string`.

- [ ] **Step 1: Write the failing test**

```ts
// platform/src/lib/dates.test.ts
import { afterEach, describe, expect, it, vi } from 'vitest';
import { todayET, toETDateString } from './dates';

afterEach(() => vi.useRealTimers());

describe('todayET', () => {
  it('is still "today" in ET when UTC has rolled past midnight', () => {
    // 2026-07-08T02:30:00Z == 2026-07-07 22:30 ET
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-08T02:30:00Z'));
    expect(todayET()).toBe('2026-07-07');
  });
  it('matches UTC date during the overlapping hours', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-07T15:00:00Z'));
    expect(todayET()).toBe('2026-07-07');
  });
});

describe('toETDateString', () => {
  it('formats an arbitrary Date in ET', () => {
    expect(toETDateString(new Date('2026-01-01T03:00:00Z'))).toBe('2025-12-31');
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd platform && npx vitest run src/lib/dates.test.ts`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

```ts
// platform/src/lib/dates.ts
/** Market-calendar date helpers. The market lives in America/New_York;
 * `new Date().toISOString().slice(0,10)` is UTC and is WRONG for 4 hours
 * every evening (5 in winter). Always derive "today" through these. */
const ET_FMT = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/New_York',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

/** YYYY-MM-DD for an arbitrary instant, in Eastern Time. */
export function toETDateString(d: Date): string {
  return ET_FMT.format(d); // en-CA locale yields YYYY-MM-DD
}

/** Today's date (YYYY-MM-DD) on the US market calendar. */
export function todayET(): string {
  return toETDateString(new Date());
}
```

Adoption:
- `DashboardPage.tsx:147-149`: body of `todayISO()` becomes `return todayET();` (keep the local name so call sites don't churn), import from `@/lib/dates`.
- `PlaybookPage.tsx:59-60`: replace the `new Date().toISOString()`-derived date with `todayET()`.
- `CatalystsPage.tsx`: at lines 177/368/430 replace local-time `new Date()` date-string derivations with `todayET()` / `toETDateString(...)`. Read each site first; only replace DATE-string derivations, not time-of-day logic.

- [ ] **Step 4: Run tests**

Run: `cd platform && npx vitest run src/lib/dates.test.ts && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add platform/src/lib/dates.ts platform/src/lib/dates.test.ts platform/src/routes/DashboardPage.tsx platform/src/routes/PlaybookPage.tsx platform/src/routes/CatalystsPage.tsx
git commit -m "fix(dates): market 'today' computed in ET, not UTC"
```

---

### Task 8: Reports markdown sanitization

**Files:**
- Modify: `platform/src/routes/ReportsPage.tsx:58-61`, `platform/package.json` (add `dompurify`)
- Test: `platform/src/routes/reportsSanitize.test.ts` (create)

**Interfaces:**
- Produces: exported `renderReportHtml(markdown: string): string` (parse + sanitize).

- [ ] **Step 1: Install dep + write the failing test**

Run: `cd platform && npm install dompurify` (v3+; types are bundled).

```ts
// platform/src/routes/reportsSanitize.test.ts
import { describe, expect, it } from 'vitest';
import { renderReportHtml } from './ReportsPage';

describe('renderReportHtml', () => {
  it('strips script tags and inline handlers from report markdown', () => {
    const html = renderReportHtml('# Title\n\n<script>alert(1)</script>\n\n<img src=x onerror="alert(1)">');
    expect(html).not.toContain('<script');
    expect(html).not.toContain('onerror');
    expect(html).toContain('<h1');
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd platform && npx vitest run src/routes/reportsSanitize.test.ts`
Expected: FAIL — not exported.

- [ ] **Step 3: Implement**

`ReportsPage.tsx`:

```ts
import DOMPurify from 'dompurify';

/** Markdown -> sanitized HTML. Reports are pipeline-generated, but embedded
 * third-party text (news headlines etc.) must never execute in the app. */
export function renderReportHtml(markdown: string): string {
  return DOMPurify.sanitize(marked.parse(markdown) as string);
}
```

`ReportViewer` memo becomes `return renderReportHtml(content);`.

- [ ] **Step 4: Run tests**

Run: `cd platform && npx vitest run src/routes/reportsSanitize.test.ts && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add platform/src/routes/ReportsPage.tsx platform/src/routes/reportsSanitize.test.ts platform/package.json platform/package-lock.json
git commit -m "fix(reports): sanitize rendered markdown with DOMPurify"
```

---

### Task 9: Live review-mode change vs prior close

**Files:**
- Modify: `platform/src/routes/LiveMarketPage.tsx:181-201` (+ the quote display component in the same file)
- Test: `platform/src/routes/reviewQuote.test.ts` (create; extract pure builder to `platform/src/lib/reviewQuote.ts`)

**Interfaces:**
- Consumes: `useReferenceLevels(ticker, dateYYYYMMDD)` (exists — ChartsPage imports it; returns prev-day `{open, high, low, close}`).
- Produces: `buildReviewQuote(bars: Bar[], prevClose: number | null, ticker: string, label: string): Quote | undefined` in `platform/src/lib/reviewQuote.ts`, where `change`/`change_pct` are `null` when `prevClose` is null (type widened: `change: number | null`).

- [ ] **Step 1: Write the failing test**

```ts
// platform/src/routes/reviewQuote.test.ts
import { describe, expect, it } from 'vitest';
import { buildReviewQuote } from '@/lib/reviewQuote';

const bars = [
  { time: '1', open: 100, high: 102, low: 99, close: 101, volume: 1000 },
  { time: '2', open: 101, high: 103, low: 100, close: 102, volume: 1200 },
];

describe('buildReviewQuote', () => {
  it('bases change on PRIOR SESSION CLOSE, matching live-mode semantics', () => {
    const q = buildReviewQuote(bars, 100.5, 'SPY', '2026-07-02 16:00 ET');
    expect(q!.change).toBeCloseTo(1.5);          // 102 - 100.5
    expect(q!.change_pct).toBeCloseTo(1.4925, 3);
    expect(q!.prev_close).toBeCloseTo(100.5);
  });
  it('is honest when prior close is unavailable: change is null, never open-based', () => {
    const q = buildReviewQuote(bars, null, 'SPY', 'x');
    expect(q!.change).toBeNull();
    expect(q!.change_pct).toBeNull();
  });
  it('returns undefined with no bars', () => {
    expect(buildReviewQuote([], 100, 'SPY', 'x')).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd platform && npx vitest run src/routes/reviewQuote.test.ts`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement**

`platform/src/lib/reviewQuote.ts` (import the `Bar`/`Quote` types from where LiveMarketPage gets them — follow its imports; widen `Quote.change`/`change_pct`/`prev_close` to `number | null` at the type's definition and fix any display sites that assumed non-null by rendering '—'):

```ts
import type { Bar, Quote } from '@/types/live';

/** Synthetic review-mode quote. `change` is vs PRIOR SESSION CLOSE — the
 * same baseline live quotes use. If prior close is unknown the fields are
 * null (rendered as '—'), never silently rebased to the day's open. */
export function buildReviewQuote(
  bars: Bar[],
  prevClose: number | null,
  ticker: string,
  lastUpdated: string,
): Quote | undefined {
  if (bars.length === 0) return undefined;
  const first = bars[0];
  const last = bars[bars.length - 1];
  return {
    ticker,
    price: last.close,
    open: first.open,
    high: Math.max(...bars.map((b) => b.high)),
    low: Math.min(...bars.map((b) => b.low)),
    volume: bars.reduce((s, b) => s + b.volume, 0),
    change: prevClose != null ? last.close - prevClose : null,
    change_pct: prevClose != null ? ((last.close - prevClose) / prevClose) * 100 : null,
    prev_close: prevClose,
    last_updated: lastUpdated,
  };
}
```

`LiveMarketPage.tsx`: fetch prior close in review mode — `const { data: refLevels } = useReferenceLevels(activeTicker, isReview && reviewDate ? reviewDate.replace(/-/g, '') : '');` (hook is disabled on empty date — verify its `enabled` handling and mirror ChartsPage's usage). Replace the quote memo's review branch with `return buildReviewQuote(bars, refLevels?.close ?? null, activeTicker, reviewTime ? `${reviewDate} ${reviewTime} ET` : (reviewDate ?? ''));` — the `?? null` here converts undefined→null for an explicitly nullable param, allowed. Change/percent display sites render '—' when null and the label reads "vs prior close".

- [ ] **Step 4: Run tests**

Run: `cd platform && npx vitest run src/routes/reviewQuote.test.ts && npx tsc --noEmit`
Expected: PASS + compile catches every display site that needs the null guard — fix each honestly.

- [ ] **Step 5: Commit**

```bash
git add platform/src/lib/reviewQuote.ts platform/src/routes/reviewQuote.test.ts platform/src/routes/LiveMarketPage.tsx platform/src/types
git commit -m "fix(live): review-mode change re-based to prior session close; null-honest when unavailable"
```

---

### Task 10: ChartsPage server-side indicators + signal series

**Files:**
- Modify: `platform/api/routers/live.py` (new endpoint), `platform/src/routes/ChartsPage.tsx:183-196,226-240,785` (and every `computeIndicators`/`calculateVWAP`/`computeStrategySignals*` call site), `platform/src/lib/indicators.ts` (delete replaced functions), `platform/src/lib/strategySignals.test.ts` + `strategySignalsForSeries.test.ts` (delete alongside their subjects)
- Test: `tests/test_live_signal_series.py` (create), Playwright `platform/tests/phase1-charts.spec.ts` (extend)

**Interfaces:**
- Produces: `POST /api/live/signal-series` `{bars: [{time, open, high, low, close, volume}]}` → `{fires: [{time: string, direction: "CALL"|"PUT", score: number}], conditions: <same shape as /api/live/indicators signals block for the LAST bar>}`.
- Consumes: the SAME Python evaluation the production pipeline uses. Before writing any new logic, read `platform/api/routers/live.py`'s existing `/api/live/indicators` implementation and reuse whatever `lib/` functions it calls (`lib/indicators.py` etc.). The per-bar fire logic must be the pipeline's own (grep `lib/signals.py` and the module the TS comment names, `trading_analysis`, for the 5-condition voter). DO NOT re-derive conditions from the TS code.

- [ ] **Step 1: Write the failing pytest**

```python
# tests/test_live_signal_series.py
"""POST /api/live/signal-series — server-side per-bar signal fires (spec 0.12).

Replaces the client-side TS voter so the 5-condition logic exists in
exactly one place (lib/). Uses a synthetic ramp so at least the shape
contract is enforced without depending on signal-firing specifics.
"""
from fastapi.testclient import TestClient

# import the app the way tests/test_platform_auth.py does
from platform_api_import_helper import get_app  # or the established pattern

client = TestClient(get_app())


def _bars(n=40):
    out = []
    px = 100.0
    for i in range(n):
        px *= 1.001
        out.append({
            "time": f"2026-07-02 10:{i:02d}:00",
            "open": px / 1.001, "high": px * 1.001, "low": px * 0.999,
            "close": px, "volume": 10_000 + i,
        })
    return out


def test_signal_series_contract():
    r = client.post("/api/live/signal-series", json={"bars": _bars()})
    assert r.status_code == 200
    body = r.json()
    assert "fires" in body and isinstance(body["fires"], list)
    for f in body["fires"]:
        assert set(f) >= {"time", "direction"}
        assert f["direction"] in ("CALL", "PUT")


def test_signal_series_rejects_short_series():
    r = client.post("/api/live/signal-series", json={"bars": _bars(5)})
    assert r.status_code == 422  # need >= 14 bars for RSI; loud, not empty-success
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_live_signal_series.py -v`
Expected: FAIL — 404 (endpoint missing).

- [ ] **Step 3: Implement backend**

In `platform/api/routers/live.py`, add the endpoint next to the existing `/api/live/indicators` handler and REUSE its bar-parsing + indicator code path. Shape (adapt names to what you find — the constraint is reuse, not invention):

```python
@router.post("/api/live/signal-series")
async def signal_series(req: IndicatorsRequest):  # reuse/extend the existing request model
    if len(req.bars) < 14:
        raise HTTPException(status_code=422, detail="need >= 14 bars for indicator warm-up")
    df = _bars_to_dataframe(req.bars)          # the same helper /api/live/indicators uses
    df = <same indicator computation the existing endpoint calls>(df)
    fires = <the pipeline's per-bar strategy evaluation over df>   # lib/, vectorized
    return {
        "fires": [
            {"time": str(t), "direction": d, "score": float(s)}
            for t, d, s in fires
        ],
    }
```

Capacity note (Rule 0): one request = one in-memory pandas pass over ≤ ~400 rows; no DB, no external calls.

- [ ] **Step 4: Rewire the frontend**

In `ChartsPage.tsx`:
- Replace the `strategyState` memo (lines 183–196) with `useLiveIndicators({ bars, current_price: <last close>, current_volume: <last volume>, avg_volume_20d: null }, bars.length >= 14)` for the Live Strategy Conditions panel — mirror LiveMarketPage.tsx:205's exact usage.
- Replace `computeStrategySignalsForSeries` (line 226-240) with a `useQuery` POST to `/api/live/signal-series` (new hook `useSignalSeries(bars, enabled)` in `platform/src/hooks/useLiveIndicators.ts`, same file as the sibling hook), mapping `fires` to the same `SeriesMarker` objects.
- Grep for remaining consumers: `grep -rn "computeIndicators\|calculateVWAP\|computeStrategySignals" platform/src`. Delete the now-unused functions from `platform/src/lib/indicators.ts` AND their tests (`strategySignals.test.ts`, `strategySignalsForSeries.test.ts`) ONLY if nothing else imports them; if something else does (e.g. `playbookEvaluator`), leave that consumer's function in place and delete only what became dead, noting the survivor in the commit body.

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/test_live_signal_series.py -v && cd platform && npx tsc --noEmit && npx vitest run && npx playwright test tests/phase1-charts.spec.ts`
Expected: PASS (Playwright confirms Live Strategy Conditions still render on /charts).

- [ ] **Step 6: Commit**

```bash
git add platform/api/routers/live.py tests/test_live_signal_series.py platform/src
git commit -m "fix(charts): signal voter and indicators served by lib/ via API; client TS math removed"
```

---

### Task 11: Dead controls + render-phase side effects

**Files:**
- Modify: `platform/src/components/options/SwingMode.tsx:273-278`, `platform/src/routes/AdminPage.tsx:179`, `platform/src/routes/ChartsPage.tsx:113-116`
- Test: extend `platform/tests/navigation.spec.ts` (SwingMode buttons) — plus `npx tsc --noEmit`

**Interfaces:** none new.

- [ ] **Step 1: Write the failing Playwright assertions**

Append to the options coverage in `platform/tests/navigation.spec.ts` (or the existing options spec if one exists — check `platform/tests/` first and put it beside similar tests):

```ts
test('SwingMode toolbar Refresh refetches and Glossary navigates to /help', async ({ page }) => {
  await page.goto('/options');
  await page.waitForLoadState('networkidle');
  let gridCalls = 0;
  await page.route('**/api/options/**/grid**', (route) => { gridCalls += 1; route.continue(); });
  const before = gridCalls;
  await page.getByRole('button', { name: 'Refresh' }).click();
  await page.waitForTimeout(500);
  expect(gridCalls).toBeGreaterThan(before);
  await page.getByRole('button', { name: 'Glossary' }).click();
  await page.waitForURL('**/help');
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd platform && npx playwright test tests/navigation.spec.ts -g "SwingMode toolbar"`
Expected: FAIL — buttons do nothing.

- [ ] **Step 3: Implement**

`SwingMode.tsx` toolbar (lines 273–278): the component fetches the grid via a TanStack query — find its queryKey and invalidate:

```tsx
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
// inside the toolbar component:
const queryClient = useQueryClient();
const navigate = useNavigate();
...
<button className="icon-btn" title="Refresh" aria-label="Refresh" type="button"
        onClick={() => queryClient.invalidateQueries({ queryKey: ['options-grid'] })}>
  <RefreshCw size={15} />
</button>
<button className="icon-btn" title="Glossary" aria-label="Glossary" type="button"
        onClick={() => navigate('/help')}>
  <HelpCircle size={15} />
</button>
```

(Verify the actual grid queryKey by reading the hook the component uses and match it exactly; add `aria-label`s as shown so the Playwright name-matcher finds them.)

`AdminPage.tsx:179`: move the logout-on-unauthorized out of render:

```tsx
useEffect(() => {
  if (routesQuery.error?.message === 'unauthorized') logout();
}, [routesQuery.error, logout]);
```

`ChartsPage.tsx:113-116`: convert the bare render-phase auto-select into the documented render-adjustment pattern (track previous deps explicitly, mirroring ReplayControl's `lastCommitted` idiom):

```tsx
// Render-time adjustment (React docs pattern): adopt the newest date once
// per dates-list identity, without an effect.
const [seenDates, setSeenDates] = useState<string[] | null>(null);
if (dates.length > 0 && seenDates !== dates) {
  setSeenDates(dates);
  if (!localSelectedDate) setLocalSelectedDate(dates[0]);
}
```

- [ ] **Step 4: Run tests**

Run: `cd platform && npx playwright test tests/navigation.spec.ts -g "SwingMode toolbar" && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add platform/src/components/options/SwingMode.tsx platform/src/routes/AdminPage.tsx platform/src/routes/ChartsPage.tsx platform/tests/navigation.spec.ts
git commit -m "fix(ui): wire SwingMode refresh/glossary; move admin logout to effect; render-adjustment for charts date"
```

---

### Task 12: Demo-banner regression assertions

**Files:**
- Test only: `platform/tests/demo-banners.spec.ts` (create)

**Interfaces:** none — Flowseeker (`FlowseekerTab.tsx:114`), ContractDrilldown (`ContractDrilldown.tsx:111`), and the SwingMode tactical card (`SwingMode.tsx:877`) ALREADY render demo banners; this task pins that so they can't silently vanish while the tabs stay mock.

- [ ] **Step 1: Write the test**

```ts
// platform/tests/demo-banners.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Mock data surfaces stay banner-honest', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/config/firebase', (route) =>
      route.fulfill({ status: 200, body: JSON.stringify({ authMode: 'open', firebase: null }) })
    );
    await page.goto('/options');
    await page.waitForLoadState('networkidle');
  });

  test('Flowseeker tab shows the demo banner', async ({ page }) => {
    await page.getByRole('button', { name: /Flowseeker/i }).click();
    await expect(page.getByText('Demo data — not live.').first()).toBeVisible();
  });

  test('Heatseeker tactical card is banner-flagged', async ({ page }) => {
    await expect(page.locator('.hs-demo-banner').first()).toBeVisible();
  });
});
```

(If the tab control isn't a button role, inspect the tab markup in `OptionsFlowPage.tsx` and adjust the selector — assert on the banner text either way.)

- [ ] **Step 2: Run to verify it passes (regression pin, not a fix)**

Run: `cd platform && npx playwright test tests/demo-banners.spec.ts`
Expected: PASS immediately. If it FAILS, the banner genuinely regressed — treat as a real defect and fix in `FlowseekerTab.tsx`/`SwingMode.tsx` before committing.

- [ ] **Step 3: Commit**

```bash
git add platform/tests/demo-banners.spec.ts
git commit -m "test(options): pin demo-data banners on mock flow surfaces"
```

---

## Final verification (whole plan)

- [ ] `python -m pytest tests/ -k "backtest_router_units or live_signal_series" -v` → all pass
- [ ] `cd platform && npx vitest run` → all pass (including pre-existing suites)
- [ ] `cd platform && npx tsc --noEmit && npm run build` → clean
- [ ] `cd platform && npx playwright test` → all pass (backend on 8000 with `AUTH_MODE=open`, vite on the configured port)
- [ ] Screenshot pass: /dashboard candle fits; backtester shows non-zero percents + readable axes; /journal equity axis reads %; /charts unchanged visually.
