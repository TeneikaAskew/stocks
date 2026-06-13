# Strat Engine — Frontend Design Brief

**For:** the designer / design agent that will lay out the frontend surfaces.
**From:** the backend + product close-out.
**Status:** the strat-engine candle-type prediction model is shipped as a shelf-ready deliverable. The frontend surfaces below are all built and reachable today; this brief gives the designer the data, the information hierarchy, and — most importantly — the language constraints. Visual polish + interaction details are open for design judgment.

---

## 1. What you're designing for

### What the model predicts
For each (ticker, timeframe) cell, the model produces a calibrated probability distribution over the **next bar's strat candle type**: `1` (inside), `2U` (two up), `2D` (two down), or `3` (outside). This is a structure prediction — **not** a price-direction prediction, **not** a P&L signal.

### What was validated (over a 24-fold walk-forward, 2019–2026)
- ✅ Native softmax probabilities are regime-stable on the structure target (raw ECE 0.013–0.049 by cell)
- ❌ Bar-body direction (`next_close > next_open`) is NOT learnable from the feature set
- ❌ The strat methodology's execution playbook (stop-buy at trigger, 1.5R target, time stop) does NOT produce positive net expectancy after realistic friction

### The language guarantee (LOAD-BEARING — read twice)
The model surfaces structure only. Language that implies direction, P&L, or trade-edge is **prohibited** in the UI copy, microcopy, button labels, tooltips, and headings.

**Verbatim scope statement that must appear on every surface that shows model output:**

> Calibrated structure prediction. Not a directional or P&L edge. Use with discretion.

**Banned words/phrases** (do not use anywhere in the UI, even in placeholders or empty states):

- `entry`, `buy`, `sell`
- `signal`, `trade signal`, `trade this`
- `predicts upside`, `predicts downside`
- `buy at`, `sell at`
- `directional edge`

**Acceptable framing** (use these):

- "structure prediction"
- "calibrated probability"
- "next bar X% likely to be type Y"
- "use with discretion"
- "model muted, ECE breach"

The existing brief enforces this via a vitest unit test that source-scans the component for banned words. Any new copy must pass the same audit.

---

## 2. Surfaces in scope

| Surface | Route | Auth | Built? | Design opportunity |
|---|---|---|---|---|
| **Structure Brief** | `/admin` (section) | IAP email or admin token | ✅ scaffolded | Polish layout, mute state, info hierarchy |
| **Model State Snapshot** | `/dev` (section) | IAP email | ✅ scaffolded | Convert from text-table to a richer ops dashboard |
| **On-Demand Predict** | `POST /api/admin/strat-engine/predict` (API) | admin token | ✅ live | NEW: build a UI form for the API |
| **Cell Detail / Drill-down** | — | — | — | NEW: per-cell drill-down with reliability curve, recent predictions, fold history |

The first two are already on the page (basic scaffolding). The last two are opportunities for design to define.

---

## 3. Data contract per surface

### 3a. Structure Brief — `GET /api/admin/structure-brief`

Returns 9 cells (3 tickers × 3 timeframes):

```typescript
{
  scope_statement: string;          // ALWAYS the verbatim quote above
  ece_ceiling: 0.05;                // per-cell ECE limit (constant)
  cells: Array<{
    ticker: 'IWM' | 'SPY' | 'QQQ';
    timeframe: '5m' | '15m' | '30m';
    available: boolean;
    top_class: '1' | '2U' | '2D' | '3' | null;
    top_prob: number | null;        // 0..1
    distribution: Array<{ cls: '1' | '2U' | '2D' | '3'; prob: number }>;
    live_ece: number | null;
    ece_ceiling: 0.05;
    muted: boolean;
    mute_reason: string | null;     // "model muted, ECE breach (live ECE 0.073 > ceiling 0.050)"
    refreshed_at: string | null;    // ISO 8601 UTC
    note: string | null;            // populated when `available: false`
  }>;
}
```

**Cell states to design:**

1. **Available, not muted** (the normal happy path) — render the 4-class bar distribution, top class + probability, refresh timestamp, ECE reading
2. **Available, muted** — hide the prediction values; render the mute reason prominently with a warning color
3. **Unavailable** (no snapshot data) — render the cell as muted-grey with the `note` text
4. **Loading** — skeleton placeholder

### 3b. Model State — `GET /dev` section (HTML, but the data shape is clear)

Per cell:

```typescript
{
  ticker: string;
  tf: string;
  available: boolean;
  model_version: string | null;     // e.g. "epoch-1779781975"
  last_train_date: string | null;   // ISO 8601 UTC
  live_ece: number | null;
}
```

This is operational state, not consumer state — show the designer it's an internal health dashboard, not a trading product.

### 3c. On-Demand Predict — `POST /api/admin/strat-engine/predict`

**Request:**
```typescript
{
  ticker: 'IWM' | 'SPY' | 'QQQ';
  timeframe: '5m' | '15m' | '30m';
  as_of_timestamp?: string;  // ISO 8601, optional — defaults to most recent bar
}
```

**Response:**
```typescript
{
  ticker: string;
  timeframe: string;
  ts: string | null;                // the bar this prediction is based on
  available: boolean;
  top_class: '1' | '2U' | '2D' | '3' | null;
  top_prob: number | null;          // 0..1
  class_probs: Record<'1' | '2U' | '2D' | '3', number>;
  model_version: string | null;
  last_train_date: string | null;
  live_ece: number | null;
  muted: boolean;
  mute_reason: string | null;
  scope_statement: string;          // verbatim
  note: string | null;
}
```

**Form states to design:**
1. **Empty** — three dropdowns (ticker, timeframe), optional timestamp picker, submit button
2. **Loading** — submit button shows spinner, "Predicting…" microcopy
3. **Success** — show response in the same card layout as a Structure Brief cell, but full-width / single
4. **Error** — show the `note` field, maintain admin-friendly tone (no user-facing error pages here, this is dev tool)

---

## 4. Layout — Structure Brief (highest priority)

The brief is the lead surface. It's currently rendered as a 3-column grid (one per ticker) with cells stacked vertically (one per timeframe). Open for redesign.

### Information hierarchy (top → bottom)

1. **Scope statement** — visible on every page load, never collapsed, never hidden. Treat it like a regulatory disclosure.
2. **Per-cell card** containing:
   - **Header strip**: `ticker · timeframe` (e.g. `IWM · 15m`), refresh timestamp on the right
   - **Primary line**: `next bar 62% likely to be type 2U` (the most prominent claim)
   - **Distribution bars**: horizontal bar chart for all 4 classes (`1`, `2U`, `2D`, `3`) with percentages on the right
   - **Footer**: `live ECE 0.023 / ceiling 0.050` left-aligned, `model version` or `refreshed_at` right-aligned

### Layout options (designer's call)

- **Option A — 3 × 3 grid** (current): one column per ticker, three rows of timeframes per column. Pros: scannable horizontally across tickers. Cons: hard on narrow viewports.
- **Option B — accordion per ticker**: each ticker is collapsible; expanded shows all 3 timeframes inline. Pros: mobile-friendly; users typically focus on one ticker. Cons: hides cross-ticker comparison.
- **Option C — table** (rows = cells, columns = ticker + tf + top class + prob + ECE + refresh): denser, less visual. Pros: fastest scan for ops. Cons: harder to make distribution bars work.

I'd recommend Option A on desktop, Option B on mobile. The designer should choose.

### Muted state design (CRITICAL)

When `muted: true`:

- Do NOT show `top_class`, `top_prob`, or the distribution bars
- DO show the `mute_reason` text prominently (e.g. red/warning tone)
- DO keep the header strip visible so the user knows which cell is muted
- DO keep the footer ECE reading visible so the user understands WHY it's muted

Example muted card:

```
┌──────────────────────────────────────────┐
│ IWM · 15m                       (no time)│
│                                          │
│ ⚠ model muted, ECE breach                │
│   (live ECE 0.073 > ceiling 0.050)       │
│                                          │
│ live ECE 0.073 / ceiling 0.050           │
└──────────────────────────────────────────┘
```

### Unavailable state design

When `available: false`:

- Render the cell as a subdued grey placeholder
- Show the `note` text (currently: "No live snapshot available. Production data source is blocked behind the Track B / Track C deploy gate.")
- No bars, no header, just the dim placeholder

---

## 5. Layout — On-Demand Predict (NEW, design opportunity)

Currently the predict endpoint exists at `POST /api/admin/strat-engine/predict` but there's no UI form. Building one would let admins call the model from the browser.

Suggested form layout:

```
┌──────────────────────────────────────────┐
│ Run a structure prediction               │
│                                          │
│ Ticker:       [IWM ▼]                    │
│ Timeframe:    [15m ▼]                    │
│ Bar timestamp [optional, datetime picker]│
│                                          │
│ ──────────────                           │
│ [ Predict ]                              │
└──────────────────────────────────────────┘
```

After submit, results render in a card that mirrors the Structure Brief cell design — same distribution bars, same scope statement at top, same mute state if applicable. Single-cell layout instead of grid.

Place this on `/admin` directly below the Structure Brief, or as a separate `/admin/structure-brief/predict` sub-route.

---

## 6. Layout — Model State Snapshot (`/dev` upgrade)

Currently rendered as plain text rows. Opportunity to convert into a cleaner ops dashboard:

```
┌──────────────────────────────────────────────────────────────┐
│ STRAT ENGINE — Model State (on shelf, no scheduler)          │
├──────────┬────┬────────────────┬──────────────────┬──────────┤
│ Ticker   │ TF │ Model Version  │ Last Train Date  │ Live ECE │
├──────────┼────┼────────────────┼──────────────────┼──────────┤
│ IWM      │ 5m │ epoch-...      │ 2026-05-26 07:52 │ —        │
│ IWM      │15m │ epoch-...      │ 2026-05-26 07:52 │ —        │
│ ...                                                          │
└──────────────────────────────────────────────────────────────┘
```

Plus a status banner at the top: `9 cells · 9 models trained · 0 muted · last refresh: never live` and a link to `docs/STRAT_ENGINE_OPERATIONS.md`.

Designer should treat this as the **operator** view (vs. the brief which is the **consumer/dev** view).

---

## 7. Visual tokens — reuse existing platform palette

The existing `/admin` page uses CSS variables from `platform/src/index.css`:

| Token | Use |
|---|---|
| `var(--color-bg-primary)` | page background |
| `var(--color-bg-secondary)` | section background |
| `var(--color-bg-card)` | card background |
| `var(--color-bg-muted)` | distribution bar track, subdued chips |
| `var(--color-border)` | card borders |
| `var(--color-text-primary)` | top-line text, top class |
| `var(--color-text-secondary)` | TF labels, axis labels |
| `var(--color-text-muted)` | ECE / timestamp footers, captions |
| `var(--color-warning)` | mute reason text, ECE breach indicator |
| `var(--color-text-secondary)` (filled bars) | distribution bar fill |

Class type color encoding (optional, designer's call):
- `1` (inside) → grey/neutral
- `2U` (up) → green / brand bull
- `2D` (down) → red / brand bear
- `3` (outside) → orange / vol-expansion

If you use color-coded classes, the muted state should drop ALL color to grey to reinforce that no prediction is being claimed.

---

## 8. Mobile considerations

The Structure Brief is read primarily on desktop today (developer admins). Mobile is nice-to-have, not required.

Constraints if you support mobile:
- Distribution bars at ~150px wide minimum — readable bars
- Header strip should never wrap
- 3-column grid collapses to 1-column at <640px (Tailwind `sm:` breakpoint)
- Mute reason text wraps; do NOT truncate or ellipsis it

---

## 9. Loading and error states

| State | What to render |
|---|---|
| Initial load | Skeleton: 9 cells with shimmer placeholders |
| Auth failure (401) | Don't render the brief; show the existing admin-token gate UI |
| Network error | Single retry button, error message in `var(--color-text-muted)`, "Structure brief unavailable: <message>" |
| Cell-specific unavailable | The dim grey placeholder with the `note` text (already specified above) |
| Mute | The mute card design (already specified above) |

---

## 10. Non-goals (do NOT design)

- Trading UI elements (buy/sell buttons, position sizing inputs, stop/target inputs)
- Price chart overlays of model predictions (the activation gate §8 blocks this)
- Notifications, alerts, or push interfaces (no scheduler, no triggers, no autonomous fires)
- Subscription/email subscribe flows (no broadcast, no user list)
- Anything that could be read as a directional or P&L claim

---

## 11. Activation gate (designer should know)

The current design surfaces are admin-gated. To move ANY of them to a user-facing route requires:

1. A documented use case naming the consumer and the action they take
2. A fresh walk-forward validation pass
3. Explicit deploy approval

The designer doesn't need to enforce this — but should be aware that **what you're designing today is the production-ready surface for the admin/operator. The user-facing surface is a SEPARATE design that doesn't exist yet** and is intentionally not on the roadmap until the gate opens.

---

## 12. Files to reference

| File | What it tells the designer |
|---|---|
| `platform/src/components/structure_brief/StructureBrief.tsx` | Current component implementation (cells, mute logic, distribution bars) — use as the starting code |
| `platform/src/components/structure_brief/StructureBrief.test.tsx` | The language audit + mute logic tests — any new copy must pass these |
| `platform/api/routers/admin.py` (lines 173+) | API contracts for both `/structure-brief` and `/strat-engine/predict` |
| `platform/api/main.py` (the `/dev` section) | The current /dev model-state rendering |
| `docs/STRUCTURE_BRIEF_DESIGN.md` | Track A's design rationale and deploy gate definition |
| `docs/STRAT_ENGINE_OPERATIONS.md` | The full operations doc — designer should skim §1–§3 and §8 |

---

## 13. Open design questions for you to resolve

The designer should treat these as choices, not requirements:

1. **Distribution bar style** — horizontal bars vs. stacked bars vs. a 100% stacked bar (single row, 4 segments)?
2. **Color encoding of classes** — color-coded by class semantic, or all-neutral with prob magnitude only?
3. **Refresh timestamp display** — relative time ("3 min ago") or absolute ("14:23 ET")?
4. **Mobile collapse strategy** — accordion per ticker, swipeable cards, or 1-column scroll?
5. **Empty/loading skeletons** — match cell shape, or use a simpler "placeholder" treatment?
6. **Predict form placement** — same page as brief (below) or separate sub-route?

When in doubt, lean toward the design choice that makes the **structural-only** framing harder to misread. The brief should never look like a trading dashboard.

---

## Summary for Claude Design

You're designing 3 surfaces:

1. **Structure Brief** (lead, exists in scaffold) — 9-cell grid, prediction + distribution + ECE per cell, muted state, scope statement always visible
2. **Predict Form** (new, design opportunity) — admin form to call the API on-demand, single-card response
3. **Model State Snapshot** (`/dev`, exists as plain text) — operator-facing health dashboard

The hard constraint: **structural-only language**. The scope statement and the banned word list are load-bearing. Everything else is design judgment.

Reuse the existing platform palette, follow the existing Tailwind patterns from `AdminPage.tsx`, and the design must pass the existing vitest language audit.
