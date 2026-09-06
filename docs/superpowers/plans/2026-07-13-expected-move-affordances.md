# Expected-Move Card Affordances Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three tiers of actionable affordances (size-light chip, expected-move magnitude, direction line, risk hint, options idea, opt-in sizing calculator) to the live Expected-Move card, driven by the validated 15m SIZE model + ATR — never implying direction.

**Architecture:** Backend adds `atr_20` + `current_price` to the `expected_move` block (Rule 3.7 null-safe). Frontend pure logic lives in a new `expectedMove.ts` (unit-tested); small presentational components render it inside the existing `MovementReadView`. No flag change (card already enabled). No new fetches (all fields already on the payload).

**Tech Stack:** Python (FastAPI assembler), pandas; React + TypeScript; vitest (pure logic); Playwright (e2e + screenshots).

## Global Constraints

- **No direction prediction** — every tier reinforces "you supply direction." Copy must never imply a buy/sell.
- **Rule 3.7 — no fabrication**: `expected_move.status !== 'OK'` → whole block "—"; `atr_20 == null` → Tier 1/2 still render, Tier-3 calculator disabled with "ATR unavailable"; never a fabricated stop/size.
- **Bucket→ATR boundaries (mag_config MAGNITUDE_THRESHOLDS)**: TIGHT <0.5×, NORMAL 0.5–1.0×, EXPANDED 1.0–1.5×, EXPLOSIVE ≥1.5× ATR-20.
- **Chip thresholds on `p_tail = p_expanded + p_explosive`**: 🟢 ≥ 0.20, 🟡 0.10–0.20, 🔴 < 0.10 (base-rate grounded; named constants).
- **Stop calc**: `stop = k × atr_20`, `k` = bucket upper edge `{TIGHT:0.5, NORMAL:1.0, EXPANDED:1.5, EXPLOSIVE:2.0}`; `shares = floor((account × riskPct) / stop)`.
- **Options idea** shows only when `p_explosive >= 0.10`.
- Tier-3 inputs persist in `localStorage`; no server state.
- Prescriptive text labeled "calculator, not a recommendation."

---

### Task 1: Backend — `atr_20` + `current_price` on the expected_move block

**Files:**
- Modify: `lib/movement_statement.py` (`_build_expected_move`)
- Modify: `platform/src/types/index.ts` (`MovementExpectedMove`)
- Test: `tests/lib/test_movement_statement.py`

**Interfaces:**
- Produces: `expected_move.atr_20: float | None` and `expected_move.current_price: float | None` (added to the existing OK envelope; both `None` when the ATR/price row is missing — never fabricated).

- [ ] **Step 1: Write the failing test** — append to `tests/lib/test_movement_statement.py`:

```python
def test_expected_move_includes_atr_and_price():
    import pandas as pd
    from lib.movement_statement import _build_expected_move
    calls = {"n": 0}

    def fake_query(sql, params):
        calls["n"] += 1
        if "magnitude_per_bar_predictions" in sql:
            return pd.DataFrame([{
                "ticker": "IWM", "tf": "15m", "ts": pd.Timestamp("2026-07-10T19:45:00Z"),
                "p_tight": 0.2, "p_normal": 0.3, "p_expanded": 0.3, "p_explosive": 0.2,
                "pred_bucket": 2, "max_proba": 0.3,
                "model_version": "m1", "source": "inference", "computed_at": pd.Timestamp("2026-07-10T20:00:00Z"),
            }])
        # ATR/price lookup on strat_features
        return pd.DataFrame([{"atr_20": 1.85, "close": 218.4}])

    em = _build_expected_move("IWM", "15m", fake_query)
    assert em["status"] == "OK"
    assert em["atr_20"] == 1.85
    assert em["current_price"] == 218.4


def test_expected_move_atr_none_when_features_missing():
    import pandas as pd
    from lib.movement_statement import _build_expected_move

    def fake_query(sql, params):
        if "magnitude_per_bar_predictions" in sql:
            return pd.DataFrame([{
                "ticker": "IWM", "tf": "15m", "ts": pd.Timestamp("2026-07-10T19:45:00Z"),
                "p_tight": 0.7, "p_normal": 0.2, "p_expanded": 0.07, "p_explosive": 0.03,
                "pred_bucket": 0, "max_proba": 0.7,
                "model_version": "m1", "source": "inference", "computed_at": pd.Timestamp("2026-07-10T20:00:00Z"),
            }])
        return pd.DataFrame()  # no ATR row

    em = _build_expected_move("IWM", "15m", fake_query)
    assert em["status"] == "OK"
    assert em["atr_20"] is None
    assert em["current_price"] is None
```

- [ ] **Step 2: Run to verify it fails** — `python -m pytest tests/lib/test_movement_statement.py -k expected_move_includes_atr -q` → FAIL (KeyError 'atr_20').

- [ ] **Step 3: Implement** — in `_build_expected_move`, after building `row` and before the `return _ok(...)`, fetch ATR/price and pass them through:

```python
    # ATR-20 + current price for the Tier-3 sizing calculator. Read from the
    # same strat_features_{tf} bar the prediction was scored on (join on ts).
    # Rule 3.7: missing -> None (the calculator disables; never a fabricated
    # stop). This is a small indexed single-row lookup.
    atr_20 = None
    current_price = None
    try:
        feat_sql = (
            f"SELECT atr_20, close FROM strat_features_{tf} "
            "WHERE ticker = :ticker AND ts = :ts LIMIT 1"
        )
        fdf = query_fn(feat_sql, {"ticker": ticker.upper(), "ts": ts})
        if fdf is not None and not getattr(fdf, "empty", True):
            frow = fdf.iloc[0].to_dict()
            av = frow.get("atr_20"); cv = frow.get("close")
            atr_20 = float(av) if av is not None and not pd.isna(av) else None
            current_price = float(cv) if cv is not None and not pd.isna(cv) else None
    except Exception as e:  # EXTERNAL: surface, don't fabricate
        log.warning("expected_move ATR lookup failed for %s %s: %s", ticker, tf, e)

    return _ok(
        role="context",
        size_class=_MAG_BUCKET_LABELS[bucket],
        pred_bucket=bucket,
        probabilities={
            "p_tight": float(row["p_tight"]),
            "p_normal": float(row["p_normal"]),
            "p_expanded": float(row["p_expanded"]),
            "p_explosive": float(row["p_explosive"]),
        },
        max_proba=float(row["max_proba"]),
        model_version=row.get("model_version"),
        ts=ts.isoformat() if hasattr(ts, "isoformat") else ts,
        atr_20=atr_20,
        current_price=current_price,
        usage_guidance=_MAG_USAGE,
    )
```
Ensure `import pandas as pd` is present at module top (it is).

- [ ] **Step 4: Run tests** — `python -m pytest tests/lib/test_movement_statement.py -k expected_move -q` → PASS.

- [ ] **Step 5: TS type** — in `platform/src/types/index.ts`, add to `MovementExpectedMove` (after `current_price` is not there — it's a new field on this interface):

```ts
export interface MovementExpectedMove {
  status: MovementFieldStatus;
  reason?: string | null;
  role?: string | null;
  size_class?: string | null;
  pred_bucket?: number | null;
  probabilities?: {
    p_tight: number; p_normal: number; p_expanded: number; p_explosive: number;
  } | null;
  max_proba?: number | null;
  model_version?: string | null;
  ts?: string | null;
  atr_20?: number | null;       // NEW — Tier-3 sizing calculator
  current_price?: number | null; // NEW
  usage_guidance?: string | null;
}
```
(Keep any existing fields not shown; only ADD `atr_20` + `current_price`.)

- [ ] **Step 6: Commit**

```bash
git add lib/movement_statement.py platform/src/types/index.ts tests/lib/test_movement_statement.py
git commit -m "feat(movement-statement): add atr_20 + current_price to expected_move (Tier-3 sizing input)"
```

---

### Task 2: `sizeLight` + `<SizeLightChip>`

**Files:**
- Create: `platform/src/components/dashboard/expectedMove.ts`
- Create: `platform/src/components/dashboard/expectedMove.test.ts`

**Interfaces:**
- Produces: `sizeLight(pTail: number | null | undefined): { level: 'big'|'elevated'|'tight'|'unknown'; label: string; tone: 'green'|'amber'|'red'|'muted' }`.

- [ ] **Step 1: Write the failing test** — `platform/src/components/dashboard/expectedMove.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { sizeLight } from './expectedMove';

describe('sizeLight', () => {
  it('green at/above 0.20', () => {
    expect(sizeLight(0.20).level).toBe('big');
    expect(sizeLight(0.35).tone).toBe('green');
  });
  it('amber in [0.10, 0.20)', () => {
    expect(sizeLight(0.10).level).toBe('elevated');
    expect(sizeLight(0.19).tone).toBe('amber');
  });
  it('red below 0.10', () => {
    expect(sizeLight(0.06).level).toBe('tight');
    expect(sizeLight(0.0).tone).toBe('red');
  });
  it('unknown on null (never fabricated)', () => {
    expect(sizeLight(null).level).toBe('unknown');
    expect(sizeLight(undefined).tone).toBe('muted');
  });
});
```

- [ ] **Step 2: Run to verify it fails** — `cd platform && npx vitest run src/components/dashboard/expectedMove.test.ts` → FAIL (module not found).

- [ ] **Step 3: Implement** — `platform/src/components/dashboard/expectedMove.ts`:

```ts
// Pure logic for the Expected-Move card affordances. No React, no fetches —
// unit-tested in expectedMove.test.ts. p_tail thresholds are base-rate grounded
// (see docs/superpowers/specs/2026-07-13-expected-move-affordances-design.md).
export const SIZE_LIGHT_GREEN = 0.20;
export const SIZE_LIGHT_AMBER = 0.10;

export type SizeLevel = 'big' | 'elevated' | 'tight' | 'unknown';
export type Tone = 'green' | 'amber' | 'red' | 'muted';

export function sizeLight(
  pTail: number | null | undefined,
): { level: SizeLevel; label: string; tone: Tone } {
  if (pTail == null || Number.isNaN(pTail)) {
    return { level: 'unknown', label: '—', tone: 'muted' };
  }
  if (pTail >= SIZE_LIGHT_GREEN) return { level: 'big', label: 'big move likely', tone: 'green' };
  if (pTail >= SIZE_LIGHT_AMBER) return { level: 'elevated', label: 'elevated', tone: 'amber' };
  return { level: 'tight', label: 'tight', tone: 'red' };
}
```

- [ ] **Step 4: Run tests** — `npx vitest run src/components/dashboard/expectedMove.test.ts` → PASS (4).

- [ ] **Step 5: Commit**

```bash
git add platform/src/components/dashboard/expectedMove.ts platform/src/components/dashboard/expectedMove.test.ts
git commit -m "feat(expected-move): sizeLight pure logic (base-rate p_tail thresholds)"
```

---

### Task 3: `bucketToAtrLabel` + `riskHint` + `showOptionsIdea`

**Files:**
- Modify: `platform/src/components/dashboard/expectedMove.ts`
- Modify: `platform/src/components/dashboard/expectedMove.test.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `bucketToAtrLabel(sizeClass: string | null | undefined): string` — e.g. `'EXPANDED' -> '≈ 1.0–1.5× ATR'`, unknown/null -> `'—'`.
  - `riskHint(sizeClass: string | null | undefined): string | null` — TIGHT -> "quiet — tighter stops OK"; NORMAL -> null (no hint); EXPANDED/EXPLOSIVE -> "bigger move likely — consider wider stops / smaller size"; null -> null.
  - `showOptionsIdea(pExplosive: number | null | undefined): boolean` — `>= 0.10`.

- [ ] **Step 1: Write the failing test** — append to `expectedMove.test.ts`:

```ts
import { bucketToAtrLabel, riskHint, showOptionsIdea } from './expectedMove';

describe('bucketToAtrLabel', () => {
  it('maps each bucket to its ATR range', () => {
    expect(bucketToAtrLabel('TIGHT')).toBe('≈ < 0.5× ATR');
    expect(bucketToAtrLabel('NORMAL')).toBe('≈ 0.5–1.0× ATR');
    expect(bucketToAtrLabel('EXPANDED')).toBe('≈ 1.0–1.5× ATR');
    expect(bucketToAtrLabel('EXPLOSIVE')).toBe('≈ ≥ 1.5× ATR');
    expect(bucketToAtrLabel(null)).toBe('—');
  });
});
describe('riskHint', () => {
  it('warns on big buckets, quiet on tight, silent on normal', () => {
    expect(riskHint('EXPANDED')).toMatch(/wider stops/);
    expect(riskHint('EXPLOSIVE')).toMatch(/wider stops/);
    expect(riskHint('TIGHT')).toMatch(/tighter stops/);
    expect(riskHint('NORMAL')).toBeNull();
    expect(riskHint(null)).toBeNull();
  });
});
describe('showOptionsIdea', () => {
  it('true only when p_explosive >= 0.10', () => {
    expect(showOptionsIdea(0.10)).toBe(true);
    expect(showOptionsIdea(0.09)).toBe(false);
    expect(showOptionsIdea(null)).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify it fails** — `npx vitest run src/components/dashboard/expectedMove.test.ts` → FAIL (exports missing).

- [ ] **Step 3: Implement** — append to `expectedMove.ts`:

```ts
const _ATR_LABEL: Record<string, string> = {
  TIGHT: '≈ < 0.5× ATR',
  NORMAL: '≈ 0.5–1.0× ATR',
  EXPANDED: '≈ 1.0–1.5× ATR',
  EXPLOSIVE: '≈ ≥ 1.5× ATR',
};
export function bucketToAtrLabel(sizeClass: string | null | undefined): string {
  return (sizeClass && _ATR_LABEL[sizeClass]) || '—';
}
export function riskHint(sizeClass: string | null | undefined): string | null {
  if (sizeClass === 'EXPANDED' || sizeClass === 'EXPLOSIVE')
    return 'bigger move likely — consider wider stops / smaller size';
  if (sizeClass === 'TIGHT') return 'quiet — tighter stops OK';
  return null;
}
export const OPTIONS_IDEA_MIN_P_EXPLOSIVE = 0.10;
export function showOptionsIdea(pExplosive: number | null | undefined): boolean {
  return pExplosive != null && !Number.isNaN(pExplosive) && pExplosive >= OPTIONS_IDEA_MIN_P_EXPLOSIVE;
}
```

- [ ] **Step 4: Run tests** — `npx vitest run src/components/dashboard/expectedMove.test.ts` → PASS.

- [ ] **Step 5: Commit**

```bash
git add platform/src/components/dashboard/expectedMove.ts platform/src/components/dashboard/expectedMove.test.ts
git commit -m "feat(expected-move): bucket ATR label, risk hint, options-idea gate (pure)"
```

---

### Task 4: `sizeCalc` (stop + share math)

**Files:**
- Modify: `platform/src/components/dashboard/expectedMove.ts`
- Modify: `platform/src/components/dashboard/expectedMove.test.ts`

**Interfaces:**
- Produces: `sizeCalc(args: { sizeClass: string | null | undefined; atr20: number | null | undefined; account: number; riskPct: number }): { stop: number; shares: number } | null` — returns `null` (calculator disabled) when `atr20` is null/≤0 or `sizeClass` unknown or `account/riskPct` non-positive. `stop = k × atr20`; `shares = floor((account × riskPct/100) / stop)`.

- [ ] **Step 1: Write the failing test** — append to `expectedMove.test.ts`:

```ts
import { sizeCalc } from './expectedMove';

describe('sizeCalc', () => {
  it('stop = k*ATR and shares = floor(risk$/stop)', () => {
    // EXPANDED k=1.5, ATR=2 -> stop=3; account 10000 * 1% = 100 -> floor(100/3)=33
    const r = sizeCalc({ sizeClass: 'EXPANDED', atr20: 2, account: 10000, riskPct: 1 });
    expect(r).not.toBeNull();
    expect(r!.stop).toBeCloseTo(3.0, 6);
    expect(r!.shares).toBe(33);
  });
  it('EXPLOSIVE uses capped k=2.0', () => {
    const r = sizeCalc({ sizeClass: 'EXPLOSIVE', atr20: 1, account: 1000, riskPct: 2 });
    expect(r!.stop).toBeCloseTo(2.0, 6);   // k=2.0 * ATR 1
    expect(r!.shares).toBe(10);            // 20 risk$ / 2 stop
  });
  it('disabled (null) when ATR missing or inputs invalid', () => {
    expect(sizeCalc({ sizeClass: 'EXPANDED', atr20: null, account: 1000, riskPct: 1 })).toBeNull();
    expect(sizeCalc({ sizeClass: 'EXPANDED', atr20: 2, account: 0, riskPct: 1 })).toBeNull();
    expect(sizeCalc({ sizeClass: null, atr20: 2, account: 1000, riskPct: 1 })).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify it fails** — `npx vitest run src/components/dashboard/expectedMove.test.ts` → FAIL.

- [ ] **Step 3: Implement** — append to `expectedMove.ts`:

```ts
// Bucket upper edge (mag_config MAGNITUDE_THRESHOLDS); EXPLOSIVE's top bucket is
// open-ended, so 2.0 is a capped proxy for a stop-distance suggestion.
const _BUCKET_K: Record<string, number> = {
  TIGHT: 0.5, NORMAL: 1.0, EXPANDED: 1.5, EXPLOSIVE: 2.0,
};
export function sizeCalc(args: {
  sizeClass: string | null | undefined;
  atr20: number | null | undefined;
  account: number;
  riskPct: number;
}): { stop: number; shares: number } | null {
  const { sizeClass, atr20, account, riskPct } = args;
  const k = sizeClass ? _BUCKET_K[sizeClass] : undefined;
  if (k == null) return null;
  if (atr20 == null || Number.isNaN(atr20) || atr20 <= 0) return null;
  if (!(account > 0) || !(riskPct > 0)) return null;
  const stop = k * atr20;
  const shares = Math.floor((account * (riskPct / 100)) / stop);
  return { stop, shares };
}
```

- [ ] **Step 4: Run tests** — `npx vitest run src/components/dashboard/expectedMove.test.ts` → PASS.

- [ ] **Step 5: Commit**

```bash
git add platform/src/components/dashboard/expectedMove.ts platform/src/components/dashboard/expectedMove.test.ts
git commit -m "feat(expected-move): sizeCalc stop/share math (ATR-null disables)"
```

---

### Task 5: Wire affordances into `MovementReadView`

**Files:**
- Modify: `platform/src/components/dashboard/MovementRead.tsx`
- Test: (source-invariant vitest already exists; behavior covered by Task 6 e2e)

**Interfaces:**
- Consumes: `sizeLight`, `bucketToAtrLabel`, `riskHint`, `showOptionsIdea`, `sizeCalc` from `./expectedMove`; `MovementStatement` / `MovementExpectedMove` from `@/types` (now with `atr_20`, `current_price`).
- Produces: an `<ExpectedMoveAffordances expectedMove={em} />` block rendered inside `MovementReadView`, BELOW the existing context-modifiers, gated on `isOk(em)`.

- [ ] **Step 1** — In `MovementRead.tsx`, add the affordances block component. It reads `em.probabilities`, `em.size_class`, `em.atr_20`, `em.current_price` and renders, in order:
  1. `<SizeLightChip>` — `sizeLight(p_expanded+p_explosive)`; colored dot + label; `data-testid="size-light-chip"`.
  2. Expected-move magnitude: `bucketToAtrLabel(size_class)`; `data-testid="expected-move-atr"`.
  3. Direction line (static, muted): "Direction: not predicted — you supply it from your levels/read." `data-testid="direction-line"`.
  4. `riskHint(size_class)` if non-null, prefixed "Suggestion:"; `data-testid="risk-hint"`.
  5. `showOptionsIdea(p_explosive)` → "Suggestion: non-directional structure (straddle/strangle) favored — profits from size, not direction." `data-testid="options-idea"`.
  6. `<SizeCalculator>` — a `<details>`/expander (`data-testid="size-calculator"`) with account + risk% inputs (localStorage keys `em.account`, `em.riskPct`), calling `sizeCalc(...)`; renders stop/shares when non-null, else "ATR unavailable — sizing disabled". Include the muted note "calculator, not a recommendation."
  Gate the whole block on `isOk(em)`; when not OK, render nothing extra (existing "—" handling stays).

- [ ] **Step 2: Type-check + lint** — `cd platform && npx tsc --noEmit && npx eslint src/components/dashboard/MovementRead.tsx` → no errors.

- [ ] **Step 3: Commit**

```bash
git add platform/src/components/dashboard/MovementRead.tsx
git commit -m "feat(expected-move): render 3-tier affordances in MovementReadView"
```

---

### Task 6: Extend Playwright e2e + screenshots per state

**Files:**
- Modify: `platform/tests/movement-read.spec.ts`

**Interfaces:**
- Consumes: the testids from Task 5.

- [ ] **Step 1: Add tests** — extend `movement-read.spec.ts`:
  - **Big-move state**: mock `expected_move` with `size_class:'EXPLOSIVE'`, `p_expanded:0.25, p_explosive:0.20` (p_tail 0.45), `atr_20:1.85, current_price:218.4`. Assert `size-light-chip` visible + text `big move likely`; `expected-move-atr` contains `1.5× ATR`; `risk-hint` contains `wider stops`; `options-idea` visible. Open `size-calculator`, fill account `10000` + risk `1`, assert a computed shares value appears. Screenshot → `${outDir}/affordances-bigmove.png`.
  - **Tight state**: `size_class:'TIGHT'`, `p_expanded:0.05, p_explosive:0.01`, `atr_20:1.85`. Assert chip text `tight`; `options-idea` NOT visible; `risk-hint` contains `tighter stops`. Screenshot → `affordances-tight.png`.
  - **ATR-null state**: `size_class:'EXPANDED'`, valid probs, `atr_20:null`. Assert chip + risk-hint render; open `size-calculator`, assert it shows `ATR unavailable`. Screenshot → `affordances-atrnull.png`.

- [ ] **Step 2: Run** — `cd platform && MOVEMENT_SHOT_DIR=<local-tmp> PLAYWRIGHT_START_VITE=1 npx playwright test tests/movement-read.spec.ts --project=chromium --reporter=list` → all pass; 3 screenshots produced.

- [ ] **Step 3: Commit**

```bash
git add platform/tests/movement-read.spec.ts
git commit -m "test(expected-move): e2e for chip/hint/options/calculator states + screenshots"
```

---

## Post-build (before requesting user verification)

Per the standing rule, after Task 6: run the e2e, collect the three state screenshots (bigmove / tight / atr-null) to a stable local path, and SHARE them with the user before asking them to verify. Then finish-branch → PR → (deploy is a separate op; card already enabled, so this is additive).

## Self-Review notes

- **Spec coverage:** Tier-1 chip (T2)+magnitude label+direction line (T3, T5), Tier-2 risk hint + options idea (T3, T5), Tier-3 calculator (T4, T5), backend atr_20/current_price (T1), Rule-3.7 null paths (T1 atr-null, T4 disabled, T5 gating), e2e+screenshots (T6). No flag change (card already enabled).
- **Type consistency:** `sizeLight`/`bucketToAtrLabel`/`riskHint`/`showOptionsIdea`/`sizeCalc` signatures match between definition (T2–T4) and consumption (T5/T6); `MovementExpectedMove.atr_20`/`current_price` added in T1 and consumed in T5.
- **No placeholders:** every code/test step has real content.
