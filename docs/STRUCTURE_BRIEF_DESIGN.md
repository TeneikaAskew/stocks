# Structure Brief — Design Document

**Status:** dev-only PR queued. **Deploy is blocked** until Track B (execution-system backtest) and Track C (direction features R&D) both report verdicts, after which we decide together what final language the brief takes.

## What this is

A read-only surface that shows the strat-engine type model's per-cell predictions to a developer / reviewer. For each (ticker, timeframe), it renders:

- The top predicted class (1 / 2U / 2D / 3)
- The calibrated probability of that class
- The full four-class probability distribution
- The cell's most recent rolling live ECE
- The last refresh timestamp

The verbatim scope statement is rendered above every set of cells:

> Calibrated structure prediction. Not a directional or P&L edge. Use with discretion.

## What this is NOT

This is **not** a trading product. It is a structure-prediction readout. The 24-fold walk-forward verdict (see `gcp/research/strat_engine/strat_dir_walk_forward.py` results) showed that:

- The type model has a real, regime-stable edge on **what kind of bar comes next** (1 / 2U / 2D / 3)
- The type model does **not** translate to a regime-stable edge on **which way the next bar's body closes** (separate direction-target experiment, 24/24 folds negative log-loss beat)

The brief surfaces the validated quantity (structure) and explicitly does not claim the unvalidated quantity (direction or P&L). The language audit (see below) enforces this.

## Scope and surfaces

| Scope | Detail |
|---|---|
| Tickers | IWM, SPY, QQQ |
| Timeframes | 5m, 15m, 30m only (1m and 60m excluded per the locked FTFC config) |
| Auth | Sits behind the existing admin auth (IAP email match OR `X-Admin-Token` header). See `platform/api/routers/admin.py:_require_admin`. |
| Mount | Tab inside `/admin`. NOT wired into `/dashboard`, `/signals`, `/live`, `/premarket_brief`, `/playbook`, or any user nav. |
| Trigger | User-triggered on dev route load. NOT triggered by any scheduler, cron, or workflow. |

## Data flow

```
GCS snapshot file (research/strat_engine/structure_brief_latest.json)
        │
        ▼
GET /api/admin/structure-brief  (admin-auth gated)
        │
        ▼
React: useStructureBrief() (sessionStorage admin token)
        │
        ▼
<StructureBrief enabled={authed} />
```

The GCS snapshot file format expected by `_load_structure_brief_snapshot`:

```json
{
  "cells": {
    "IWM_15m": {
      "distribution": {"1": 0.10, "2U": 0.62, "2D": 0.23, "3": 0.05},
      "live_ece": 0.025,
      "refreshed_at": "2026-05-27T13:00:00Z"
    },
    "IWM_5m": { ... },
    "SPY_15m": { ... },
    ...
  }
}
```

If the snapshot file does not exist (the upstream writer is **out of scope** for Track A — it is part of the production pipeline blocked behind the deploy gate), every cell is returned with `available: false`. The component renders an "unavailable" placeholder. This is intentional: the dev route works end-to-end against either presence or absence of the snapshot.

## Self-mute logic (the key safety guarantee)

The brief MUST self-mute a cell when that cell's most recent rolling live ECE exceeds the per-cell ceiling (`STRUCTURE_BRIEF_ECE_CEILING = 0.05`).

When a cell is muted:

- `top_class`, `top_prob`, and `distribution` are NOT rendered
- The cell shows only the mute reason: `model muted, ECE breach (live ECE X.XXX > ceiling Y.YYY)`

This is enforced in `_build_brief_cell` server-side (which strips the prediction fields before returning) AND in `Cell` client-side (which renders the mute message instead of the prediction). The vitest tests in `StructureBrief.test.tsx` assert both branches.

The point of the safety guarantee: backtest-stable through 2019-2026 does NOT mean regime-invariant forever. If a 2027 regime makes the type model's calibration drift above the ceiling, the brief hides the prediction rather than show miscalibrated probabilities. The reviewer sees the silence, not lies.

## Language audit (disallowed term list)

This is the load-bearing guarantee of Track A. The brief and this design doc MUST NOT contain the following terms / phrases:

- `entry` (as a noun referring to a trade)
- two-letter actions: `buy`, `sell`
- `signal` (as in "trade signal")
- `trade this`, `trade signal`
- `predicts upside`, `predicts downside`
- `buy at`, `sell at`
- `directional edge`

Acceptable language (and the only allowed framing):

- `structure prediction`
- `calibrated probability`
- `next bar X% likely to be type Y`
- `use with discretion`
- `model muted, ECE breach`

The vitest tests assert the disallowed list does not appear in the component's source. If a future PR introduces any disallowed term, those tests fail.

## Deploy gate (the non-negotiable part)

This PR sits open. The brief is reachable ONLY at `/admin` (auth-gated). It is not linked from any user-facing nav. It is not triggered by any scheduler.

The deploy gate opens when BOTH of the following report a verdict:

1. **Track B — execution-system backtest** reports PASS, FAIL, or MIXED. The backtest applies the strat methodology's execution rules (stop-buy at trigger high, stop at opposite extreme, 1.5× target, time-stop) to the type model's confident calls on intrabar 1m data with realistic costs. PASS bar: net expectancy per trade > 2¢/share on IWM, in at least 6/8 walk-forward folds, hit rate > 40%, no single fold > 50% of total.

2. **Track C — direction features R&D** reports PASS, FAIL, or PARTIAL. C tests up to 4 non-structural feature families (news sentiment, cross-asset, options-derived, volatility regime) on top of the 143-col baseline for the direction target. PASS bar: ≥ 6/8 folds positive log-loss beat, ECE within ceiling, monotonic confidence discrimination.

After both report:

- **If B passes**: revise the brief's framing to incorporate the execution playbook (still no disallowed terms; still structural, but the brief becomes a setup-stalker for the validated execution rules).
- **If B fails**: keep the brief structural and never promote it to a user route. Decide whether to keep it as a dev tool or remove it.
- **If C passes**: a direction product becomes feasible separately — that becomes a different brief and a different PR.
- **If C fails**: the structure-brief framing in this PR is final; the brief never claims direction.

This document and the brief itself stay frozen until that joint decision lands.

## Reuse of existing patterns

- **FastAPI router pattern** — added to `platform/api/routers/admin.py` rather than a new router file, since the auth and conventions match exactly. Endpoint is `GET /api/admin/structure-brief`.
- **React + Tailwind** — component lives under `platform/src/components/structure_brief/`. Tailwind class tokens follow the existing `var(--color-*)` palette already used in `AdminPage.tsx`.
- **React Query hook** — `useStructureBrief` follows the same shape as `useAdminRoutes`, `useAdminModels`.
- **Vitest** — tests follow the pattern of the existing `platform/src/lib/*.test.ts` files, runnable via `npm test` inside `platform/`.

## Test plan

- [x] `useStructureBrief` hook contract typed
- [x] `Cell` renders prediction when ECE is below ceiling
- [x] `Cell` hides prediction and renders mute reason when ECE exceeds ceiling
- [x] `Cell` falls back to default mute language when server omits a reason
- [x] `Cell` renders unavailable state when snapshot is missing
- [x] `ScopeStatement` renders the verbatim language exactly
- [x] Language audit: no disallowed term appears in the rendered DOM of any test case
- [ ] Production snapshot writer (out of scope; deferred to post-gate phase)

## Files changed in this PR

| File | Change |
|---|---|
| `platform/api/routers/admin.py` | Added `GET /api/admin/structure-brief` endpoint + Pydantic models + GCS snapshot loader |
| `platform/src/hooks/useAdmin.ts` | Added `useStructureBrief` hook + types |
| `platform/src/components/structure_brief/StructureBrief.tsx` | New component (cells, mute logic, scope statement, distribution bars) |
| `platform/src/components/structure_brief/StructureBrief.test.tsx` | Vitest tests: mute logic + scope statement + disallowed-term audit |
| `platform/src/routes/AdminPage.tsx` | Mount the brief as a dev-only section inside the existing `/admin` page |
| `docs/STRUCTURE_BRIEF_DESIGN.md` | This document |

## Out of scope (explicitly)

- The upstream snapshot writer (the process that updates `structure_brief_latest.json` in GCS). That belongs in a follow-on PR after the deploy gate opens.
- Any integration with `/dashboard`, `/signals`, `/live`, `/premarket_brief`. None. Zero. Not until the gate opens AND the language is renegotiated.
- Any scheduler trigger or cron. None.
- Any change to the type model itself. The model is FROZEN in this and the other two tracks.
