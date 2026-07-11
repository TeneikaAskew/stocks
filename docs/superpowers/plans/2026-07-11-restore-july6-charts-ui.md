# Restore July-6 Charts UI (pre-#700 look, current backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the Charts page's July-6 look and teaching UX — full-height chart and the readable 5-condition Live Strategy Conditions card — while keeping every post-July-6 backend capability (server-side signal math, Cloud SQL per-user journal, replay trainer, seed layer, backtest-my-trades), plus recover the user's pre-migration journal trades and stop the Journal equity curve from silently vanishing.

**Architecture:** The July-6 UI came from client-side voter math in `platform/src/lib/indicators.ts::computeStrategySignals` (deleted by PR #700's one-source-of-truth migration). We restore the *presentation* by porting that exact voter to Python (`lib/chart_voter.py`), serving it from the existing `POST /api/live/indicators` endpoint as a new `chart_voter` key, and rendering it with the July-6 card markup. The one-source-of-truth rule stays intact — no math returns to TypeScript. Chart height is restored with a viewport-based container height, keeping the #700 overflow fix (CandlestickChart's ResizeObserver sizing is untouched).

**Tech Stack:** Python/FastAPI (`lib/`, `platform/api/routers/live.py`), React/TS (`platform/src`), pytest, Playwright, Cloud SQL via `./scripts/db_query_cr.sh`.

## Where the old code comes from (the "pull from main" mechanics)

The reference build is **commit `969187eb`** — the tip of `main` on **2026-07-06**, immediately before PR #700 merged. Every restored artifact is extracted from it with `git show`; nothing is reconstructed from memory:

| Restored artifact | Source of truth | How to view it |
|---|---|---|
| 5-condition voter (labels, details, fires rule) | `platform/src/lib/indicators.ts` lines ~225–345 (`computeStrategySignals`) | `git show 969187eb:platform/src/lib/indicators.ts` |
| Conditions-card markup (label + detail rows, N/5 ✓ fires header) | `platform/src/components/charts/StrategyConditionsCard.tsx` | `git show 969187eb:platform/src/components/charts/StrategyConditionsCard.tsx` |
| Page layout baseline (confirms wrappers unchanged; height loss = added toolbar rows) | `platform/src/routes/ChartsPage.tsx` | `git show 969187eb:platform/src/routes/ChartsPage.tsx` |

What is deliberately **not** pulled back: the client-side indicator/voter math itself (breaks the one-source-of-truth rule and would resurrect the #700 number bugs), the zustand localStorage trade store (Cloud SQL persistence stays), and the pre-#700 chart-overflow behavior.

## Global Constraints

- Reference commit for all restored UI: `969187eb` (main @ 2026-07-06). Extract with `git show 969187eb:<path>` — never retype from screenshots.
- CLAUDE.md one-source-of-truth: all financial/voter math lives in `lib/` (Python), served via FastAPI; the React app renders, never computes.
- CLAUDE.md Rule 3.7 (no silent fallbacks): missing indicator values render `--` and `met: false`; never fabricate numbers.
- Keep intact and functional: journal Cloud SQL persistence, replay trainer, seed layer, Backtest-my-trades, TickerCombobox — regression-tested by the existing Playwright suites (`charts-cards`, `replay-trainer`, `journal`, `ticker-combobox`).
- Do not reintroduce the pre-#700 candle-overflow bug: `CandlestickChart.tsx`'s ResizeObserver sizing logic must not change; the e2e overflow guard (Task 4) must pass.
- Exact condition labels, verbatim (CALL): `3 consecutive up moves`, `RSI 25–50 (bullish band)`, `StochRSI K < 80 (room to run)`, `Price > VWAP`, `Price > EMA9`. (PUT): `3 consecutive down moves`, `RSI 50–75 (bearish band)`, `StochRSI K > 20 (room to fall)`, `Price < VWAP`, `Price < EMA9`. (En-dash in the RSI labels, as in the original.)
- Fires rule, verbatim from the July-6 voter: a side fires iff `met_count >= 3` AND `met_count` strictly beats the other side.
- The existing `signals` key in the `/api/live/indicators` response is consumed by the Live page's shared card usage — it must remain byte-identical; `chart_voter` is additive.
- Branch: `feature/restore-july6-charts-ui` off `main` **after** the `fix/702-follow-ups` PR merges (both touch `ChartsPage.tsx` and `journal.spec.ts`; sequencing avoids a conflict storm).
- Commit messages: conventional format, no Claude branding, no Co-Authored-By trailers. Stage by explicit path only (`git add <paths>`); `docs/alphavantage/` and `model_analysis.txt` belong to another workstream — never stage them.

---

### Task 1: Port the July-6 chart voter to `lib/chart_voter.py`

**Files:**
- Create: `lib/chart_voter.py`
- Test: `tests/test_chart_voter.py`

**Interfaces:**
- Consumes: nothing (pure function; stdlib only).
- Produces: `evaluate_chart_voter(closes: list[float], rsi: float | None, stoch_k: float | None, ema9: float | None, vwap: float | None) -> dict` returning:
  ```python
  {
    "call": {"direction": "CALL", "conditions": [{"id": str, "label": str, "met": bool, "detail": str} × 5],
             "met_count": int, "total_count": 5, "fires": bool},
    "put":  {... mirror ...},
    "firing": "CALL" | "PUT" | None,
  }
  ```

The TypeScript original (reference — port this exactly; full text via `git show 969187eb:platform/src/lib/indicators.ts`):

```ts
// Last 3 bars' direction, matching trading_analysis.py's pct_change>0 semantics
let upRun = 0; let downRun = 0;
for (let i = closes.length - 3; i < closes.length; i += 1) {
  if (i <= 0) continue;
  const diff = closes[i] - closes[i - 1];
  if (diff > 0) upRun += 1;
  if (diff < 0) downRun += 1;
}
// ... conditions arrays with label/met/detail (labels in Global Constraints) ...
const callFires = callMet >= 3 && callMet > putMet;
const putFires  = putMet  >= 3 && putMet  > callMet;
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_chart_voter.py
"""Pins lib/chart_voter.py to the July-6 client voter it was ported from
(platform/src/lib/indicators.ts::computeStrategySignals @ 969187eb)."""
import math

from lib.chart_voter import evaluate_chart_voter


def test_call_fires_on_up_run_with_bullish_band():
    # 3 rising closes, RSI in 25-50 band, K<80, price above vwap & ema9
    closes = [100.0, 101.0, 102.0, 103.0]
    out = evaluate_chart_voter(closes, rsi=44.3, stoch_k=60.0, ema9=101.0, vwap=100.5)
    call = out["call"]
    assert call["met_count"] == 5
    assert call["fires"] is True
    assert out["firing"] == "CALL"
    labels = [c["label"] for c in call["conditions"]]
    assert labels == [
        "3 consecutive up moves",
        "RSI 25–50 (bullish band)",
        "StochRSI K < 80 (room to run)",
        "Price > VWAP",
        "Price > EMA9",
    ]


def test_detail_strings_match_july6_format():
    closes = [100.0, 101.0, 100.5, 101.5]  # 2 of last 3 up
    out = evaluate_chart_voter(closes, rsi=44.31, stoch_k=94.8, ema9=None, vwap=None)
    call = out["call"]
    by_id = {c["id"]: c for c in call["conditions"]}
    assert by_id["call_consec_up"]["detail"] == "2/3 last bars up"
    assert by_id["call_rsi_band"]["detail"] == "RSI 44.3"
    assert by_id["call_stoch_room"]["detail"] == "K 94.8"
    assert by_id["call_stoch_room"]["met"] is False        # 94.8 < 80 is False
    assert by_id["call_above_vwap"]["detail"] == "--"      # vwap None -> '--', met False
    assert by_id["call_above_vwap"]["met"] is False
    assert by_id["call_above_ema9"]["detail"] == "--"


def test_no_fire_below_three_and_ties_never_fire():
    # Flat closes: no up/down runs; rsi 50 is outside BOTH bands (strict bounds)
    closes = [100.0, 100.0, 100.0, 100.0]
    out = evaluate_chart_voter(closes, rsi=50.0, stoch_k=50.0, ema9=100.0, vwap=100.0)
    # call met: stoch K<80 only -> 1; put met: stoch K>20 only -> 1 (tie, both <3)
    assert out["call"]["met_count"] == 1
    assert out["put"]["met_count"] == 1
    assert out["call"]["fires"] is False and out["put"]["fires"] is False
    assert out["firing"] is None


def test_strictly_beats_rule():
    # Construct call_met=3, put_met=3 tie -> neither fires even though >=3
    # closes: up,down,up in last 3 -> upRun=2? build a real tie instead:
    # up run 3 (call consec met) + rsi 60 (put band met) + K=50 (both stoch met)
    # + price exactly between vwap/ema9 splits: price>vwap (call), price<ema9 (put)
    closes = [100.0, 101.0, 102.0, 103.0]
    out = evaluate_chart_voter(closes, rsi=60.0, stoch_k=50.0, ema9=104.0, vwap=102.5)
    assert out["call"]["met_count"] == 3   # consec_up, stoch<80, >vwap
    assert out["put"]["met_count"] == 3    # rsi 50-75, stoch>20, <ema9
    assert out["firing"] is None


def test_nan_rsi_treated_as_missing():
    closes = [100.0, 101.0, 102.0, 103.0]
    out = evaluate_chart_voter(closes, rsi=float("nan"), stoch_k=60.0, ema9=101.0, vwap=100.5)
    by_id = {c["id"]: c for c in out["call"]["conditions"]}
    assert by_id["call_rsi_band"]["met"] is False
    assert by_id["call_rsi_band"]["detail"] == "RSI --"


def test_short_series_counts_available_moves_only():
    out = evaluate_chart_voter([100.0, 101.0], rsi=None, stoch_k=None, ema9=None, vwap=None)
    by_id = {c["id"]: c for c in out["call"]["conditions"]}
    assert by_id["call_consec_up"]["detail"] == "1/3 last bars up"
    out_empty = evaluate_chart_voter([], rsi=None, stoch_k=None, ema9=None, vwap=None)
    assert out_empty["firing"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_chart_voter.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.chart_voter'`

- [ ] **Step 3: Implement `lib/chart_voter.py`**

```python
"""Chart-page teaching voter — the July-6 (pre-#700) 5-condition readout.

Ported line-for-line from the deleted client voter
(platform/src/lib/indicators.ts::computeStrategySignals @ commit 969187eb).
PR #700's one-source-of-truth migration removed the client math but also the
readable presentation; this module restores the math server-side so the
Charts page card can show the same five conditions per side.

Voter taxonomy (issue #701): this is the chart TEACHING voter (trend
confirmation in a pullback band). It is distinct from the production
alerting voter (lib/signals.py::evaluate_signal, mean-reversion) and from
the Live-page trend framework (platform/api/routers/live.py::_build_signals).
"""
from __future__ import annotations

import math
from typing import List, Optional


def _fmt(n: Optional[float], digits: int = 2) -> str:
    if n is None or not math.isfinite(n):
        return "--"
    return f"{n:.{digits}f}"


def _num(n: Optional[float]) -> Optional[float]:
    """None-ify NaN/inf so comparisons below can rely on `is not None`."""
    if n is None or not math.isfinite(n):
        return None
    return n


def evaluate_chart_voter(
    closes: List[float],
    rsi: Optional[float],
    stoch_k: Optional[float],
    ema9: Optional[float],
    vwap: Optional[float],
) -> dict:
    rsi, stoch_k, ema9, vwap = _num(rsi), _num(stoch_k), _num(ema9), _num(vwap)
    last = closes[-1] if closes else None

    # Last 3 bars' direction — pct_change>0 semantics from the TS original.
    up_run = 0
    down_run = 0
    n = len(closes)
    for i in range(n - 3, n):
        if i <= 0:
            continue
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            up_run += 1
        if diff < 0:
            down_run += 1

    call_conds = [
        {"id": "call_consec_up", "label": "3 consecutive up moves",
         "met": up_run >= 3, "detail": f"{up_run}/3 last bars up"},
        {"id": "call_rsi_band", "label": "RSI 25–50 (bullish band)",
         "met": rsi is not None and 25 < rsi < 50, "detail": f"RSI {_fmt(rsi, 1)}"},
        {"id": "call_stoch_room", "label": "StochRSI K < 80 (room to run)",
         "met": stoch_k is not None and stoch_k < 80, "detail": f"K {_fmt(stoch_k, 1)}"},
        {"id": "call_above_vwap", "label": "Price > VWAP",
         "met": last is not None and vwap is not None and last > vwap,
         "detail": (f"{_fmt(last)} {'>' if last > vwap else '<'} VWAP {_fmt(vwap)}"
                    if last is not None and vwap is not None else "--")},
        {"id": "call_above_ema9", "label": "Price > EMA9",
         "met": last is not None and ema9 is not None and last > ema9,
         "detail": (f"{_fmt(last)} {'>' if last > ema9 else '<'} EMA9 {_fmt(ema9)}"
                    if last is not None and ema9 is not None else "--")},
    ]
    put_conds = [
        {"id": "put_consec_down", "label": "3 consecutive down moves",
         "met": down_run >= 3, "detail": f"{down_run}/3 last bars down"},
        {"id": "put_rsi_band", "label": "RSI 50–75 (bearish band)",
         "met": rsi is not None and 50 < rsi < 75, "detail": f"RSI {_fmt(rsi, 1)}"},
        {"id": "put_stoch_room", "label": "StochRSI K > 20 (room to fall)",
         "met": stoch_k is not None and stoch_k > 20, "detail": f"K {_fmt(stoch_k, 1)}"},
        {"id": "put_below_vwap", "label": "Price < VWAP",
         "met": last is not None and vwap is not None and last < vwap,
         "detail": (f"{_fmt(last)} {'<' if last < vwap else '>'} VWAP {_fmt(vwap)}"
                    if last is not None and vwap is not None else "--")},
        {"id": "put_below_ema9", "label": "Price < EMA9",
         "met": last is not None and ema9 is not None and last < ema9,
         "detail": (f"{_fmt(last)} {'<' if last < ema9 else '>'} EMA9 {_fmt(ema9)}"
                    if last is not None and ema9 is not None else "--")},
    ]

    call_met = sum(1 for c in call_conds if c["met"])
    put_met = sum(1 for c in put_conds if c["met"])
    call_fires = call_met >= 3 and call_met > put_met
    put_fires = put_met >= 3 and put_met > call_met
    firing = "CALL" if call_fires else "PUT" if put_fires else None

    return {
        "call": {"direction": "CALL", "conditions": call_conds,
                 "met_count": call_met, "total_count": 5, "fires": call_fires},
        "put": {"direction": "PUT", "conditions": put_conds,
                "met_count": put_met, "total_count": 5, "fires": put_fires},
        "firing": firing,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_chart_voter.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add lib/chart_voter.py tests/test_chart_voter.py
git commit -m "feat(lib): restore July-6 chart teaching voter server-side"
```

---

### Task 2: Serve `chart_voter` from `POST /api/live/indicators`

**Files:**
- Modify: `platform/api/routers/live.py` (function `compute_live_indicators`, ~line 446)
- Test: `tests/test_live_chart_voter.py` (new; model the FastAPI TestClient wiring on `tests/test_live_signal_series.py`)

**Interfaces:**
- Consumes: `lib.chart_voter.evaluate_chart_voter` (Task 1 signature).
- Produces: the `/api/live/indicators` JSON response gains a top-level `"chart_voter"` key with exactly the Task-1 return shape. The existing `"indicators"` and `"signals"` keys are byte-identical to before.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_live_chart_voter.py
"""/api/live/indicators exposes the July-6 chart voter (additively)."""
# Copy the sys.path/platform-import/TestClient scaffold verbatim from
# tests/test_live_signal_series.py (it handles the platform/ dir import).

def _bars(closes):
    return [
        {"time": str(1_700_000_000 + i * 60), "open": c - 0.05,
         "high": c + 0.01, "low": c - 0.06, "close": c, "volume": 100_000}
        for i, c in enumerate(closes)
    ]


def test_indicators_response_includes_chart_voter(client):
    closes = [220.0 + i * 0.05 for i in range(30)]  # steady up-run
    resp = client.post("/api/live/indicators", json={"bars": _bars(closes)})
    assert resp.status_code == 200
    body = resp.json()
    assert "signals" in body                      # legacy key untouched
    cv = body["chart_voter"]
    assert cv["call"]["total_count"] == 5
    labels = [c["label"] for c in cv["call"]["conditions"]]
    assert labels[0] == "3 consecutive up moves"
    assert cv["call"]["conditions"][0]["met"] is True   # 3 rising closes
    assert isinstance(cv["firing"], (str, type(None)))


def test_empty_bars_returns_empty_voter(client):
    resp = client.post("/api/live/indicators", json={"bars": []})
    assert resp.status_code == 200
    cv = resp.json()["chart_voter"]
    assert cv["firing"] is None
    assert cv["call"]["met_count"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_live_chart_voter.py -q`
Expected: FAIL — `KeyError: 'chart_voter'`

- [ ] **Step 3: Implement**

In `compute_live_indicators` (read the whole function first): after the existing indicators/signals are computed, add — using the already-computed values, do NOT recompute:

```python
from lib.chart_voter import evaluate_chart_voter  # top of file with the other lib imports

# ... inside compute_live_indicators, before the return:
chart_voter = evaluate_chart_voter(
    closes=[b.close for b in bars],
    rsi=indicators_payload["rsi"],
    stoch_k=indicators_payload["stochK"],
    ema9=indicators_payload["ema9"],
    vwap=indicators_payload["vwap"],
)
return {"indicators": indicators_payload, "signals": signals_payload, "chart_voter": chart_voter}
```

(Variable names above are illustrative — bind to whatever the function actually names its indicator dict; the empty-bars early return at ~line 456 also gains `"chart_voter": evaluate_chart_voter([], None, None, None, None)`.)

- [ ] **Step 4: Run the new test + the endpoint's existing suites**

Run: `python -m pytest tests/test_live_chart_voter.py tests/test_live_signal_series.py -q`
Expected: all pass (legacy response asserted unchanged by existing tests)

- [ ] **Step 5: Commit**

```bash
git add platform/api/routers/live.py tests/test_live_chart_voter.py
git commit -m "feat(api): expose chart teaching voter on /api/live/indicators"
```

---

### Task 3: Restore the July-6 conditions-card presentation

**Files:**
- Modify: `platform/src/components/charts/StrategyConditionsCard.tsx` (render the `chart_voter` shape; restore label+detail rows and `N/5 ✓ fires` header from `git show 969187eb:platform/src/components/charts/StrategyConditionsCard.tsx`)
- Modify: `platform/src/routes/ChartsPage.tsx:1260` (`<StrategyConditionsCard signals={chartSignals} />` → pass the `chart_voter` slice of the same `/api/live/indicators` response the page already fetches)
- Modify: `platform/src/types/index.ts` (add `ChartVoter` types mirroring the Task-1 shape)
- Test: `platform/tests/charts-cards.spec.ts` (update the `/api/live/indicators` mock to include `chart_voter`; assert the July-6 labels render)

**Interfaces:**
- Consumes: `chart_voter` from Task 2 (shape in Task 1).
- Produces: `StrategyConditionsCard({ voter }: { voter: ChartVoter })` — prop renamed to make the data source unambiguous.

Key presentation requirements pulled from the July-6 component (verify against `git show` before writing):
- Two columns, CALL (green, up-trend icon) and PUT (red, down-trend icon).
- Each row: ✓ (accent) or ✗ (muted) + `label` + muted `detail` text (e.g. `RSI 44.3`, `1/3 last bars up`).
- Column header right side: `{met_count}/5` plus `✓ fires` suffix when `fires` is true.
- Card header badge (top right): `CALL · {met_count}/5` (green) / `PUT · {met_count}/5` (red) / `No setup` per `firing`.
- REMOVE the current subtitle "Trend framework — same conditions as the Live page"; restore the July-6 subtitle if present in the old component (check `git show`; if none, no subtitle).

- [ ] **Step 1: Update the Playwright spec first (failing)** — in `charts-cards.spec.ts`, extend `MOCK_LIVE_INDICATORS` with a `chart_voter` object (5 conditions per side, `call.met_count: 3`, `call.fires: true`, labels verbatim from Global Constraints) and change the assertions:

```ts
await expect(page.getByText('3 consecutive up moves').first()).toBeVisible();
await expect(page.getByText('RSI 25–50 (bullish band)').first()).toBeVisible();
await expect(page.getByText(/CALL · 3\/5/).first()).toBeVisible();
await expect(page.getByText(/3\/5 ✓ fires/).first()).toBeVisible();
```

- [ ] **Step 2: Run to verify it fails** — `cd platform && npx playwright test tests/charts-cards.spec.ts --project=chromium` (vite recipe: `npx vite --port 4321 --strictPort` + temporarily point `playwright.config.ts` baseURL at 4321; REVERT before commit). Expected: the new assertions fail.
- [ ] **Step 3: Implement** — rewrite the card against the old markup, add the `ChartVoter` type, rewire ChartsPage. TypeScript: `cd platform && npx tsc --noEmit` clean.
- [ ] **Step 4: Re-run** `charts-cards.spec.ts` — all tests pass (including the untouched persistence/similar-setups tests).
- [ ] **Step 5: Commit**

```bash
git add platform/src/components/charts/StrategyConditionsCard.tsx platform/src/routes/ChartsPage.tsx platform/src/types/index.ts platform/tests/charts-cards.spec.ts
git commit -m "feat(charts): restore July-6 strategy-conditions presentation"
```

---

### Task 4: Restore chart height without reintroducing overflow

**Files:**
- Modify: `platform/src/routes/ChartsPage.tsx` (chart wrapper div, currently `className="flex-1 rounded-lg border ..."` at ~line 1006)
- Test: `platform/tests/charts-cards.spec.ts` (add one sizing/overflow test)

**Interfaces:** none new — CSS/layout only. `CandlestickChart.tsx` must NOT be modified (its ResizeObserver + `minHeight: 400` carry the #700 overflow fix).

Approach (from the layout recon): the old and new wrappers are identical; the height loss comes from the toolbar wrapping to a second row (replay control + export + Mark Entry overflow at common widths) and the fixed `minHeight={400}` acting as the effective height. Fix both:

- [ ] **Step 1: Failing test** — add to `charts-cards.spec.ts`:

```ts
test('chart fills the viewport height without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto('/charts');
  await page.waitForLoadState('networkidle');
  const canvas = page.locator('canvas').first();
  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.height).toBeGreaterThan(450);           // was ~400 flat before
  // overflow guard: the #700 fix must hold — canvas never wider than its card
  const card = page.locator('[data-testid="chart-card"]');
  const cardBox = await card.boundingBox();
  expect(box!.width).toBeLessThanOrEqual(cardBox!.width + 1);
  // no page-level horizontal scrollbar
  const scrollW = await page.evaluate(() => document.documentElement.scrollWidth);
  const clientW = await page.evaluate(() => document.documentElement.clientWidth);
  expect(scrollW).toBeLessThanOrEqual(clientW + 1);
});
```

- [ ] **Step 2: Run to verify it fails** (height assertion fails at ~400).
- [ ] **Step 3: Implement** — on the chart wrapper: add `data-testid="chart-card"` and `style={{ height: 'clamp(400px, calc(100vh - 340px), 900px)' }}` (the CandlestickChart ResizeObserver already fills its container, so height flows through without touching the component). Compact the toolbar so it stays on one row at ≥1280px: export buttons become icon-only (`title` attrs keep discoverability), and the replay control's idle state stays the single "Start replay" pill it already is.
- [ ] **Step 4: Run** the new test + full `charts-cards.spec.ts` + `replay-trainer.spec.ts` (replay UI shares the toolbar). All pass.
- [ ] **Step 5: Commit**

```bash
git add platform/src/routes/ChartsPage.tsx platform/tests/charts-cards.spec.ts
git commit -m "fix(charts): viewport-height chart, single-row toolbar"
```

---

### Task 5: Journal equity-curve placeholder (kill the silent empty state)

**Files:**
- Modify: `platform/src/routes/JournalPage.tsx:366-378`
- Test: `platform/tests/journal.spec.ts`

- [ ] **Step 1: Failing test** — in `journal.spec.ts`, in the describe block whose GET mock returns ≤1 closed trade:

```ts
test('equity curve card shows a placeholder when under 2 closed trades', async ({ page }) => {
  await page.goto('/journal');
  await page.waitForLoadState('networkidle');
  await expect(page.getByText(/equity curve/i)).toBeVisible();
  await expect(page.getByText(/close 2\+ trades to see your equity curve/i)).toBeVisible();
});
```

- [ ] **Step 2: Run to verify it fails** (card currently unrendered).
- [ ] **Step 3: Implement** — replace the `{equityPoints.length > 1 && (` gate:

```tsx
<Card>
  <CardHeader title={`${activeTicker} equity curve`} meta="cumulative P&L %" />
  {equityPoints.length > 1 ? (
    <PriceAreaChart data={equityPoints} seriesLabel="Cumulative P&L" height={240}
      valueFormatter={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`}
      tooltipFormatter={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`} />
  ) : (
    <p className="py-8 text-center text-xs text-[var(--color-text-muted)]">
      Close 2+ trades to see your equity curve.
    </p>
  )}
</Card>
```

- [ ] **Step 4: Run** `journal.spec.ts` — all pass (existing curve-renders test still green with ≥2 closed trades).
- [ ] **Step 5: Commit**

```bash
git add platform/src/routes/JournalPage.tsx platform/tests/journal.spec.ts
git commit -m "fix(journal): equity curve shows placeholder instead of vanishing"
```

---

### Task 6: Recover the user's pre-migration journal trades (data task — needs explicit user OK + `gcloud auth login`)

**Files:** none in-repo (operational task via `./scripts/db_query_cr.sh`); findings recorded in the PR description.

This is gated on two things the controller must confirm before dispatching: (a) the user approved reading production `journal_entries` (surfaces user emails), and (b) `gcloud auth login` has been re-run.

- [ ] **Step 1: Inventory ownership** (read-only; rolls back by default):

```bash
./scripts/db_query_cr.sh -q "SELECT user_email, source, count(*) AS n, min(created_at) AS first, max(created_at) AS last FROM journal_entries GROUP BY user_email, source ORDER BY n DESC"
```

- [ ] **Step 2: Interpret.** Rows keyed to `local` are pre-auth writes (the router's owner fallback is `current_user_email(request) or "local"` — `platform/api/routers/journal.py:84`). Rows keyed to another email of the same person (e.g. an admin address) need the user to confirm which account should own them.
- [ ] **Step 3: Present the mapping to the user and get sign-off on the exact UPDATE.** Example (only after approval, with the real values):

```bash
./scripts/db_query_cr.sh -q "UPDATE journal_entries SET user_email='<confirmed-target-email>' WHERE user_email='local'" --commit
```

- [ ] **Step 4: Verify** — re-run the Step-1 inventory; then the user reloads `/journal` and confirms their trades are visible.

---

### Task 7: Whole-feature verification + deploy

**Files:** none new (verification + ops).

- [ ] **Step 1: Full local gates** — `python -m pytest tests/test_chart_voter.py tests/test_live_chart_voter.py tests/test_live_signal_series.py -q`; `cd platform && npx tsc --noEmit && npx vitest run`; Playwright: `charts-cards`, `journal`, `replay-trainer`, `ticker-combobox` suites green.
- [ ] **Step 2: Eyes-on screenshot parity** — run the Playwright screenshot harness against the local build and visually compare with the user's reference screenshot (chart height, card labels/details, fires badge). Send the screenshots to the user.
- [ ] **Step 3: PR** with capacity note (trivial: one pure function per request, no new queries) and the standard CI watch (`gh pr checks <N> --watch`).
- [ ] **Step 4: Deploy** — staging first, verify `/charts` live; then prod (deploys land at 0% traffic — attribute the revision via `gcloud builds list` timestamps, promote by NAME). Requires `gcloud auth login`.
- [ ] **Step 5: User acceptance** — user loads the deployed `/charts` and `/journal` and confirms the restoration before we close the loop.

---

## Self-Review

- **Spec coverage:** screenshot card (Tasks 1–3), chart height (Task 4), enhancements kept (Global Constraints + regression suites), old trades (Task 6), equity placeholder (Task 5), deploy+acceptance (Task 7). No gaps.
- **Placeholder scan:** none — every code step carries real code; Task 2's "illustrative names" note is an explicit read-the-function instruction, not a TBD.
- **Type consistency:** `chart_voter` shape identical across Task 1 return, Task 2 response, Task 3 `ChartVoter` type and card prop.
- **Known risks:** (1) `/api/live/indicators` is also called by historical-review flows — additive key is safe, and Task 2 Step 4 runs the legacy suite to prove it. (2) Toolbar compaction could shift other specs' selectors — Task 4 Step 4 runs `replay-trainer.spec.ts`. (3) Task 6 depends on external auth + user approval and can proceed independently of Tasks 1–5.
