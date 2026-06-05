# Options Flow — backend data contract (Skylit-aligned UI)

The redesigned Options Flow page (`src/routes/OptionsFlowPage.tsx`) follows
Skylit's product model. Three views are **real-data backed today**; three are
built against **labeled demo mocks** because no backend endpoint exists yet.
This doc specifies the endpoints needed to make the mocked views real.

| View | Tab · Mode | Data today | Real source needed |
|------|-----------|-----------|--------------------|
| GEX/VEX profile | Profiles | **Real** — `/api/options/{t}/{date}/levels` + `POST /api/options/greeks` | — |
| Trinity 3-panel | Heatseeker · Trinity | **Real** — `useGammaLevels` for SPX/SPY/QQQ | — |
| Swing 2D heatmap | Heatseeker · Swing | Mock `src/data/heatseekerSwingMock.ts` | **(A)** per-expiration GEX/VEX surface |
| Live flow tape | Flowseeker · Live Feed | Mock `src/data/optionsFlowMock.ts` | **(B)** options-flow feed |
| Contract drilldown | Flowseeker · Drilldown | Mock `src/data/contractDrilldownMock.ts` | **(C)** per-contract tape |

## (A) Per-expiration dealer-exposure surface — Swing Mode
The current chain endpoints return a single snapshot collapsed across
expirations, so per-cell (strike × expiration) GEX/VEX can't be computed
client-side. Proposed:

```
GET /api/options/{ticker}/{date}/surface?metric=gex|vex
→ {
    ticker, date, spot, spot_method,
    expirations: [{ label, date, dte }],         # columns
    strikes: [number],                            # rows (desc)
    cells: [{ strike, expiration, gex, vex,       # $ exposure per 1% move
              call_oi, put_oi, dominant: "call"|"put" }],
    nodes: { king: number, gates: number[], spot_row: number }
  }
```
Compute server-side in `lib/gamma.py` (one source of truth for the math),
grouping the chain by `expiration` before the existing per-strike GEX/VEX
reduction. Color semantics per Skylit docs: **yellow = vol-suppressing (Pika,
positive/pinning)**, **purple = vol-amplifying (Barney, negative gamma)**.

## (B) Options-flow feed — Live Feed
No order-flow source exists in the pipeline today. Needs a trade-tape provider
(sweeps/blocks/splits) persisted to a `options_flow` table, then:

```
GET /api/flow/feed?tickers=&min_premium=&dte_max=&side=&sentiment=&limit=
→ [{ ts, sym, strike, cp, otm_pct, expiry, dte, price,
     bid, mid, ask, side, sentiment, size, chain_side, chain_pct,
     premium, is_sweep }]
```

## (C) Per-contract tape — Contract Drilldown
Drill-in from a Live Feed row. Needs the same flow source bucketed per contract:

```
GET /api/flow/contract/{occ_symbol}?window=
→ { contract: { sym, strike, cp, expiry, dte },
    stats: { volume, oi, avg_fill, total_premium, otm_pct, multi_pct },
    chain_ratio: { bid_pct, ask_pct, bid_premium, ask_premium },
    buckets: [{ ts, bid, mid, ask, no_side, avg_fill, iv, rvol,
                volume, bid_premium, mid_premium, ask_premium }] }
```

When each endpoint lands, swap the matching `src/data/*Mock.ts` import for a
TanStack Query hook and remove the "Demo data" banner in that view.
