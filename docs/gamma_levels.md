# Gamma Levels — Taxonomy, Math, and Pipeline

This is the reference for how gamma exposure analytics work in this
codebase. Read this when you want to understand: what King/Gate/Spot/Flip
mean, why values look the way they do, and where the numbers come from.

The math is implemented in [`lib/gamma.py`](../lib/gamma.py) and consumed
by the API, the React UI, the AI insights pipeline, the standalone CLI,
and the Pine Script overlay — all from one place, per the architectural
rule established in [`HARDCODED_VALUES_REMEDIATION.md`](HARDCODED_VALUES_REMEDIATION.md).

---

## Vocabulary

The terms come from SqueezeMetrics / SpotGamma's research and the
Stratalyst trading community's branded layer on top. They're descriptive
English (a "king node" is the highest one) and not proprietary —
matching the names lets the AI gamma analyst produce paragraphs that
read like the community recaps.

| Term | Math definition | Trading meaning |
|---|---|---|
| **Net GEX** | `Σ(call_gamma×call_oi − put_gamma×put_oi) × spot²` per strike | Dollar gamma dealers carry. Positive = call-dominated, negative = put-dominated |
| **King** | Strike where \|Net GEX\| ≥ 50% of max in window | Primary magnet/defense level. First touches react ~80% in positive gamma |
| **Gate (Gatekeeper)** | Strike where \|Net GEX\| ≥ 20% of max | Secondary level — must break before price reaches the King |
| **Spot** | Strike within 0.2% of current price | Visual marker, no trading meaning by itself |
| **Flip** | Cumulative-GEX zero crossing nearest spot | Regime divider |
| **Regime — Positive gamma** | Spot above flip | Dealers buy dips/sell rips → vol suppressed → range-bound, pinning |
| **Regime — Negative gamma** | Spot below flip | Dealers sell dips/buy rips → vol amplified → trending |

---

## Sign convention (locked)

The convention used throughout the codebase:

```
net_gamma_per_strike = call_gamma_oi − put_gamma_oi
gex_per_strike       = net_gamma_per_strike × spot² × 0.01
total_gex            = Σ(gex_per_strike)
```

This matches:
- [`options-heatseeker/js/dataLoader.js:261`](../options-heatseeker/js/dataLoader.js)
  ("Dealer perspective: opposite of customer")
- The deleted `platform/src/lib/greeksCalculator.ts:52-57` (call add,
  puts subtract)
- The new `lib/gamma.py:aggregate_by_strike`

### What was wrong before

Three different sign conventions existed across the codebase pre-`cdda6b0`:
1. Standalone heatseeker JS used `dealerGamma = -gamma` unconditionally
   for total GEX, but `calls add / puts subtract` for per-strike — so
   the total had the *opposite* sign from the per-strike sum.
2. Platform TS replicated that internal inconsistency.
3. The `scripts/show_gamma_levels.py` CLI had `sign = +1` for puts (the
   inverted convention), producing positive +6.8B at QQQ 590 instead of
   the correct −67.7M.

After `cdda6b0`/`d2b5817`, all paths share `lib.gamma` and total GEX is
derived from the per-strike sum, so it's algebraically guaranteed to
have the same sign as what the heatmap shows.

---

## Spot estimation (layered)

Cloud SQL's `etf_options_snapshots.underlying_price` is set to `0.0` by
the AlphaVantage fetcher (the API doesn't expose underlying on the
options endpoint). So `lib.gamma.estimate_spot()` runs three fallbacks:

1. **Put-call parity at smallest \|C−P\| pair** on the nearest expiration:
   `S ≈ K + C_mid − P_mid`. Most accurate. Returns `method = "parity"`.
2. **Delta proxy:** strike of the call whose `|delta|` is closest to
   0.5. Returns `method = "delta"`. Fragile if delta is missing.
3. **Median strike** of the chain. Last resort. Returns
   `method = "median_strike"` plus a warning so the UI can surface it.

The frontend's `useGammaLevels` hook surfaces `spot.method` as a chip
next to the spot input. If you see "median_strike" the chain is too
thin to trust; manually override the spot.

---

## Pipeline overview

```
   AlphaVantage EOD            GitHub Actions (daily)
        │
        ▼
   Cloud SQL: etf_options_snapshots
        │
        ▼
   ┌───────────────────────────────────┐
   │  lib/gamma.py                     │   ◄── one canonical implementation
   │   aggregate_by_strike             │
   │   gex_by_strike                   │
   │   estimate_spot (parity→δ→median) │
   │   compute_gamma_flip              │
   │   classify_levels                 │
   │   build_summary                   │
   └───────────────────────────────────┘
        │
        ├─────────► POST /api/options/greeks    (heatmap consumer)
        │           [platform/api/routers/options.py]
        │
        ├─────────► GET  /api/options/{tk}/{date}/levels
        │           [chain-source-aware, returns full GammaSummary]
        │
        ├─────────► lib/agents/summarizers.summarize_gamma_levels
        │           └─► AI gamma analyst → bull/bear/judge/PM
        │
        ├─────────► scripts/show_gamma_levels.py  (CLI, dev tool)
        │
        └─────────► (manual paste) → tradingview-pine-scripts/gamma-levels-overlay-v2
```

---

## API contracts

### `POST /api/options/greeks`
Heatmap-driving endpoint. Frontend posts the full chain + spot, server
returns aggregated/gex/metrics/nodes/config. Backwards-compatible
contract — the React heatmap consumes it as-is.

### `GET /api/options/{ticker}/{date}/levels`
Chain-source-aware endpoint added in `d2b5817`. Loads the chain from
Cloud SQL itself, runs `gamma.build_summary`, returns:

```json
{
  "ticker": "QQQ",
  "snapshot_date": "2025-11-21",
  "spot": { "price": 590.36, "method": "parity", "note": "K=590 …" },
  "flip": null,
  "regime": "unknown",
  "total_gex": -91035104,
  "kings": [{ "strike": 590, "gex": -67700665, "distance_pct": -0.06,
              "score": 0.92, "kind": "king", "tags": ["king","spot"] }],
  "gates": [...],
  "flip_levels": [...],
  "warnings": [],
  "snapshot_timestamp": "...",
  "chain_size": 435
}
```

Optional query params: `?window_pct=8` (default 8% around spot),
`?spot=590.50` (manual override).

---

## Common questions

### "Why is my Flip null?"
Cumulative net GEX never strictly crosses zero in the visible window.
Either the chain is one-sided (heavy puts everywhere or heavy calls
everywhere), or the window is too narrow. Try `?window_pct=15`. If it's
still null, there's no clear regime divider — the analyst will report
`regime: "unknown"` with reduced confidence.

### "Why does the King have a tiny GEX number?"
GEX is in dollar-notional terms (gamma × OI × spot²). For a low-priced
stock or a thin chain, the absolute dollars are small even if the
strike is the dominant one. The taxonomy is *relative* — the King is
whatever has the largest \|GEX\| in the window, regardless of absolute
size.

### "I see different GEX numbers in two places."
Pre-`cdda6b0` this happened because per-strike and total were computed
with opposite sign conventions. After the consolidation, every surface
uses `lib.gamma`. If you see a discrepancy now, it's almost certainly:
- One surface is using the spot from the local delta proxy and another
  from server parity (1-2% off can flip Kings)
- One is filtered to a single expiration, the other isn't
- A stale cache (the API has a 12h TTL on chain queries)

### "I want to tune the King/Gate thresholds."
They live as module constants in `lib/gamma.py:42-50`:

```python
NODE_KING_PCT = 0.50           # ≥50% of max → KING
NODE_GATE_PCT = 0.20           # ≥20% of max → GATE
SPOT_PROXIMITY_PCT = 0.002     # within 0.2% → SPOT
```

If we end up wanting per-ticker tuning (SPX wider window, IWM tighter),
move these to a `gamma_config` table in Cloud SQL like the indicator
config — same pattern as `/api/config/indicators`.

---

## Related files

- [`lib/gamma.py`](../lib/gamma.py) — canonical math
- [`lib/agents/summarizers.py:summarize_gamma_levels`](../lib/agents/summarizers.py) — AI input
- [`lib/agents/prompts.py:ANALYST_PROMPTS["gamma"]`](../lib/agents/prompts.py) — analyst directive
- [`platform/api/routers/options.py`](../platform/api/routers/options.py) — `/greeks` and `/levels` endpoints
- [`platform/src/hooks/useGammaLevels.ts`](../platform/src/hooks/useGammaLevels.ts) — React hook
- [`platform/src/routes/OptionsFlowPage.tsx`](../platform/src/routes/OptionsFlowPage.tsx) — Levels panel
- [`platform/src/routes/ChartsPage.tsx`](../platform/src/routes/ChartsPage.tsx) — chart overlay toggle
- [`scripts/show_gamma_levels.py`](../scripts/show_gamma_levels.py) — CLI
- [`tradingview-pine-scripts/gamma-levels-overlay-v2`](../tradingview-pine-scripts/gamma-levels-overlay-v2) — Pine companion
- [`tests/test_gamma.py`](../tests/test_gamma.py) — sign convention regressions
