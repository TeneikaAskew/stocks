# Expected-Move Card Affordances — Design

**Date:** 2026-07-13
**Status:** approved design → implementation plan next

## Goal

Make the validated SIZE read on the movement-statement / Expected-Move card
*actionable* for day-to-day trading, in three tiers, without ever implying a
directional signal we don't have. All affordances hang off the existing
`expected_move` block (validated 15m magnitude model, live) plus the current
ATR-20 — derived, never fabricated.

## Context

The card (`platform/src/components/dashboard/MovementRead.tsx`, endpoint
`GET /api/movement-statement`, assembler `lib/movement_statement.py`) is LIVE
(2026-07-12) showing: TYPE continuation headline + validated 15m SIZE bucket +
levels-to-go with reach-rates + gamma regime + the "not a directional edge"
scope guard. Magnitude buckets are defined in ATR-20 units (`mag_config.py`):

| bucket | |next_close−next_open| / ATR-20 |
|---|---|
| TIGHT | < 0.5× |
| NORMAL | 0.5–1.0× |
| EXPANDED | 1.0–1.5× |
| EXPLOSIVE | ≥ 1.5× |

## Non-goals

- No direction prediction (closed axis) — every tier reinforces "you supply direction."
- No options *cost/EV* modelling (per the 2026-07 reframe).
- Tier-3 numbers are a user-pulled calculator, NOT pushed trade advice.
- No change to the headline (TYPE continuation still the only headline driver).

## Architecture — three tiers, one card

**Tier 1 — Informational (always shown; the honest core).** Additive to the
existing `context-modifiers` block:
- **Size-light chip** — a glanceable 🟢/🟡/🔴 from the calibrated tail
  probability `p_tail = p_expanded + p_explosive`:
  - 🟢 `big move likely` — `p_tail ≥ 0.25`
  - 🟡 `normal` — `0.12 ≤ p_tail < 0.25`
  - 🔴 `tight` — `p_tail < 0.12`
  Thresholds are named constants (tunable; documented as calibrated to the
  observed 15m distribution where big moves are genuinely rare — so 🟢 is
  correctly uncommon).
- **Expected-move magnitude label** — the bucket's ATR range: e.g. EXPANDED →
  "≈ 1.0–1.5× ATR". No ATR *value* needed (label only).
- **Direction line** — explicit, muted: "Direction: not predicted — you supply
  it from your levels/read." Reinforces the scope guard.

**Tier 2 — Soft suggestions (inline, labeled "suggestion").**
- **Risk hint** (qualitative, from the bucket): EXPANDED/EXPLOSIVE →
  "bigger move likely → consider wider stops / smaller size"; TIGHT →
  "quiet → tighter stops OK". Labeled `suggestion`, not advice.
- **Options idea** (only when `p_explosive` elevated, `p_explosive ≥ 0.10`):
  "non-directional structure (straddle/strangle) favored — profits from size
  regardless of direction." An idea, not strikes; carries the same
  not-a-recommendation label.

**Tier 3 — Prescriptive, opt-in (collapsed by default).** A "size this trade"
expander the user opens:
- Inputs: account size + risk-% (persisted in `localStorage`; no server state).
- Computes, from the predicted bucket and current ATR-20:
  - **suggested stop distance** = `k × ATR20` where `k` = the bucket's upper
    edge (TIGHT 0.5, NORMAL 1.0, EXPANDED 1.5, EXPLOSIVE 2.0 as a capped
    proxy for the open-ended top bucket),
  - **suggested share size** = `floor((account × risk%) / stop_distance)`.
- Rendered with an explicit "calculator, not a recommendation — sizing math on
  the model's expected move; verify against your own plan" note.
- Requires the current **ATR-20** and **price**, which Tier 1/2 do not — so the
  backend adds them to the `expected_move` block (below).

## Data flow / backend change

`lib/movement_statement._build_expected_move` currently returns the bucket +
probabilities + model_version + ts. Add two fields for Tier 3:
- `atr_20`: the current ATR-20 for the (ticker, tf) — read from the same
  `strat_features_{tf}` row the magnitude prediction was scored on (join on
  ts). Rule 3.7: if unavailable, `null` + status note; Tier 3 then shows "—"
  and disables the calculator (never fabricates a stop).
- `current_price`: the latest close for context (the levels block already
  carries `current_price`; reuse it if present, else the same features row).

Everything else is frontend-only (`MovementRead.tsx`).

## Components (frontend)

- `SizeLightChip` — pure function `sizeLight(p_tail) → {level, label, color}`;
  small, unit-tested.
- `ExpectedMoveMagnitude` — bucket → ATR-range label (pure).
- `DirectionLine` — static muted line.
- `RiskHint` / `OptionsIdea` — pure, bucket/`p_explosive`-driven, labeled.
- `SizeCalculator` — the Tier-3 expander (localStorage inputs → stop/size),
  disabled when `atr_20` is null.
All render inside `MovementReadView`, below the existing context-modifiers, and
inherit the Rule-3.7 "—/unavailable" discipline.

## Error handling (Rule 3.7)

- `expected_move.status !== 'OK'` → the whole affordance block renders "—"
  (no chip, no calculator), same as today.
- `atr_20 == null` → Tier 1/2 still render (they only need the bucket); Tier 3
  calculator is disabled with "ATR unavailable" — never a fabricated stop.
- Chip/label/hint are pure functions of already-present fields; no new fetches.

## Testing

- **vitest (pure):** `sizeLight` thresholds (boundaries 0.12/0.25), bucket→ATR
  label, stop/size math (`k×ATR`, `floor(risk/stop)`), `atr_20=null` → disabled.
- **Playwright e2e (extend `movement-read.spec.ts`):** mock `expected_move`
  with a high-`p_tail` payload → assert 🟢 chip + risk hint + options idea
  render; a TIGHT payload → 🔴 chip, no options idea; open the Tier-3 expander,
  enter risk %, assert a computed stop/size appears; `atr_20:null` → calculator
  disabled. Screenshot each state and share before requesting verification
  (per the standing UI-verification rule).

## Deliverables

1. Backend: `atr_20` + `current_price` on the `expected_move` block (+ tests).
2. Frontend: the five components + wiring into `MovementReadView` (+ vitest).
3. Extended Playwright e2e with screenshots for the new states.
4. No flag change — the card is already enabled; affordances ship additively.
