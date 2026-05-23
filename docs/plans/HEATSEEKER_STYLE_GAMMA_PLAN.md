# Heatseeker-Style Gamma Heatmap — Architecture & Implementation Plan

> **Status:** Research + design only. No code changes proposed in this PR.
> **Created:** 2026-05-23
> **Trigger:** User asked whether we can build a Heatseeker-style tool that
> shows traders "high liquidation at 650" / "great entry vs not great
> entry" using dealer positioning data; whether we need to add Vanna
> Exposure (VEX); and how it fits into the existing strat-plus-options
> insight pipeline.
> **Audience:** product owner (you), then ops/eng for phased build-out.

---

## TL;DR

1. **We already have ~70% of the data and math.** `etf_options_snapshots`
   stores every Greek we'd need (δ, γ, θ, ν, ρ) per contract per
   expiration, refreshed every 5 min during RTH as of PR #536. `lib/gamma.py`
   already computes per-strike net GEX, per-strike call/put GEX, total VEX,
   gamma flip, regime classification, and a King/Gate/Spot/Flip taxonomy.
2. **What's missing is mostly aggregation surface area, not raw data.**
   We currently aggregate ACROSS all expirations into one 1-D heatmap.
   Heatseeker shows a 2-D `strike × expiration` grid. The contracts already
   carry an `expiration` column — we just don't group by it yet.
3. **VEX is genuinely useful but secondary.** We compute it as a single
   total today; per-strike VEX would let us answer "which strikes are most
   sensitive to a VIX spike?" That's a different question from gamma's
   "which strikes pin price?" Both matter on event days (FOMC, CPI,
   earnings) when IV regime changes are the dominant driver.
4. **Recommendation:** ship in 4 phases (data layer → API → UI → tactical
   overlay). Phase A is a single table view (materialized aggregate) plus
   one new gamma helper function — ~1 day. Phases B-D are 1-2 weeks each.
5. **No new fetcher work required.** The realtime fetcher is already
   writing the underlying contracts at the granularity the new views need.

---

## Part 1 — Heatseeker concepts decoded (and mapped to us)

The screenshots use terminology that's a mix of SqueezeMetrics/SpotGamma
research vocabulary and Stratalyst's branded layer on top of it. Here's
what each term actually means and what (if anything) we call it today.

| Heatseeker term | What it really is | Our equivalent | Have we got it? |
|---|---|---|---|
| **Node** | One cell in the heatmap: a (strike, expiration) pair with a net-exposure value | A row in `aggregate_by_strike()`'s output (but we collapse expirations) | ✅ raw data, ❌ per-expiration view |
| **Value** | The dollar-notional exposure at that cell (net GEX or net VEX) | `gex_by_strike()` returns `gex`, `call_gex`, `put_gex` per strike | ✅ for GEX, ❌ per-strike VEX |
| **Color** | Sign of the value: yellow/green = positive (calls dominant, pinning), purple/blue = negative (puts dominant, vol-amplifying) | Same sign convention; UI uses green/purple | ✅ |
| **Absolute value matters** | Largest \|value\| = strongest magnet, regardless of sign | `NODE_KING_PCT = 0.50` threshold in `lib/gamma.py:61` | ✅ |
| **King Node** ★ | Single largest \|value\| in the window. Dealer's preferred settlement target for EOD/EOW | `kind="king"` in `Level` dataclass | ✅ |
| **Gatekeeper Node** | Top-N secondary high-\|value\| levels that block price from reaching the King; failed test = trend shift | `kind="gate"` in `Level` (we call it "gate" — same thing) | ✅ (rename to "gatekeeper" optional) |
| **Spot/Current marker** ► | Strike row currently inhabited by price | `kind="spot"` (within 0.2% of estimated price) | ✅ |
| **Flip** | Where cumulative GEX crosses zero — regime divider | `flip` field on `GammaSummary` | ✅ |
| **Midpoint** | The middle of a range; "Market Maker's favorite trap" — worst R:R | `detect_nodes()` returns `midpoints` | ✅ (under-used in UI) |
| **Hedge Node** | Static, far-from-price node that's built before macro events (FOMC, CPI, NFP) and unwinds slowly. Insurance-positioning rather than active magnet | **No direct concept.** We'd detect this as "low-rate-of-change, far-distance, persistent across snapshots" | ❌ — would need event-window logic |
| **OPEX Node** | Any node tied to the monthly third-Friday expiration; loses weight as contracts expire | `expiration` column already on the contract — we just don't tag it | ❌ — easy add |
| **Rate of Change** | How fast a node's value is growing/shrinking between snapshots | Time-series of `gex_by_strike()` across our 5-min snapshots | ❌ — derived, not stored |
| **Reshuffle** | Sudden change in node positions — dealer book repositioning, often precedes trend change | Cross-snapshot diff of King/Gate positions | ❌ — derived |
| **Confluence** | When SPX, SPY, and QQQ agree on the same direction's nodes | Already implicit via FTFC scoring but not options-specific | 🟡 partial |
| **GEX (Gamma Exposure)** | Sum of (γ × OI × spot² × 100) flipped to dealer perspective | `total_gex_from_strikes()` | ✅ |
| **VEX (Vanna Exposure)** | Sum of (ν × OI × spot × 100) flipped to dealer perspective. Tells you how dealer hedging *changes* as IV moves | `total_vex()` — we have aggregate only | 🟡 aggregate, no per-strike |

### What is VEX (Vanna), really?

This deserves its own section because the user asked specifically.

**Vanna** is a second-order Greek: `∂Δ/∂σ` — how much the delta of an
option changes when implied volatility changes by 1%. **VEX** (Vanna
Exposure) is the per-contract vanna scaled by open interest, summed
across the chain, and flipped to dealer perspective.

**Why it matters in plain English:**

Imagine the VIX is at 18 in the morning. Dealers have hedged their book
based on that IV. If the VIX drops to 16 over the day (a "vol crush" —
common after FOMC, earnings, CPI), every option's delta changes — even
though the underlying didn't move. Dealers MUST re-hedge to stay
neutral, which generates buying or selling pressure on the underlying.

- **Positive VEX:** dealer book gets MORE bullish as IV drops → dealers
  need to **buy** the underlying to re-hedge → bullish flow on vol
  crushes.
- **Negative VEX:** dealer book gets MORE bearish as IV drops → dealers
  need to **sell** the underlying → bearish flow on vol crushes (and
  the reverse on IV spikes).

**When is VEX more important than GEX?**

| Day type | GEX matters | VEX matters |
|---|---|---|
| Normal trading day (no scheduled events, VIX stable) | 🟢 primary | ⚪ secondary |
| FOMC / CPI / NFP morning (everyone short vol heading in) | 🟢 primary | 🟢 primary |
| Post-FOMC vol crush (3-5 % VIX drop) | 🟡 still useful | 🟢 PRIMARY |
| Earnings day, single name | 🟡 less reliable | 🟢 PRIMARY |
| Quad-witch / OPEX Friday | 🟢 primary | 🟡 secondary |
| Calm range-bound midday | 🟢 primary | ⚪ negligible |

**Our use case:** the user trades the major ETFs (SPY/IWM/QQQ) and
runs the AI-insights pipeline on FOMC/CPI mornings already. VEX as a
SECOND heatmap layer (toggle: GEX ↔ VEX) on event days would directly
support a "dealers will be forced to BUY into the cash close because
VIX crushed" thesis — which the strat-plus-options agent currently has
no way to surface.

### What is a "Hedge Node," really?

Heatseeker's "Hedge Nodes" are nodes that:
1. Sit FAR from current spot (typically >5% away)
2. Built up before a macro event (FOMC, CPI, earnings)
3. Don't actively pull price intraday (they're insurance, not magnets)
4. Unwind SLOWLY across multiple sessions as the event passes

In our system, we'd detect these by:
- Joining recent snapshots against `economic_events` (the 8:30 AM ET
  high-impact event calendar) within ±2 trading days of each event
- Flagging strikes whose \|GEX\| grew >30% in the 5 sessions before the
  event AND sits >5% from spot
- Tagging them `kind="hedge"` in the `Level` taxonomy

Not strictly required for v1, but it's an answer to "why is there a
huge node at 4500 SPX when we're trading 4600 and it's not doing
anything?" — which the current taxonomy can't answer.

---

## Part 2 — Current state audit

This is what we have today, surveyed via the file references in
`docs/gamma_levels.md` and inspection of `lib/gamma.py` + the API +
the frontend.

### 2.1 Producer (data into Cloud SQL)

| Component | What it writes | Where | Cadence |
|---|---|---|---|
| `fetch_av_historical_options.py` | Full chain, all Greeks, EOD only | `etf_options_snapshots` rows with `market_session='EOD'` | Nightly at ~21:00 ET |
| `fetch_av_realtime_options.py` (PR #536) | Full chain, all Greeks, intraday | Same table, `market_session='REALTIME'` | Every 5 min, RTH only |

The `etf_options_snapshots` schema captures everything we'd need:

```sql
CREATE TABLE etf_options_snapshots (
    ticker              VARCHAR(10),
    snapshot_ts         TIMESTAMPTZ,        -- intraday timestamp
    snapshot_date       DATE,               -- session date
    market_session      VARCHAR(30),        -- 'EOD' | 'REALTIME'
    contract_symbol     VARCHAR(50),
    option_type         VARCHAR(5),         -- 'calls' | 'puts'
    expiration          DATE,               -- ✓ key for new per-expiration view
    strike              DOUBLE PRECISION,   -- ✓ key for per-strike view
    bid, ask, mark, last_price, change, percent_change,
    volume, open_interest,                  -- ✓ for OI weighting
    implied_volatility,                     -- ✓ for VEX context
    delta, gamma, theta, vega, rho,         -- ✓ all 5 first-order Greeks
    underlying_price,                       -- ⚠️ AV returns 0.0; we estimate
    data_source         VARCHAR(30),
    inserted_at         TIMESTAMPTZ
);
```

**Indices today:**
- `(ticker, snapshot_date DESC)` — covers freshness probes
- `(ticker, expiration, strike)` — exists but underused
- Partial: `(ticker, snapshot_ts DESC) WHERE market_session='REALTIME'`
  (added in PR #537 for the brief probe)

**Storage scale:** ~14 k contracts × 3 tickers × 84 intraday snapshots/day
\= ~3.5 M rows/day during RTH, plus 1 EOD row/ticker/day. Six months at
this rate = ~600 M rows / ~150 GB — Cloud SQL can handle it but we'll
want to start thinking about partition pruning by snapshot_date soon.

### 2.2 Math layer (`lib/gamma.py`)

| Function | What it does | Per-strike? | Per-expiration? |
|---|---|---|---|
| `aggregate_by_strike(options)` | Collapses chain to one row per strike with call/put gamma & OI | ✅ | ❌ (sums across exps) |
| `gex_by_strike(strikes, spot)` | Per-strike GEX in dollar-notional terms — returns `gex`, `call_gex`, `put_gex` | ✅ | ❌ |
| `total_gex_from_strikes(...)` | Sum of per-strike GEX | — | — |
| `total_vex(options, spot)` | Total VEX (aggregate single number) | ❌ | ❌ |
| `put_call_ratio(options)` | OI-weighted P/C ratio | — | — |
| `estimate_spot(options)` | Layered: parity → delta → median fallback | — | — |
| `compute_gamma_flip(strikes, spot)` | Cumulative-GEX zero crossing nearest spot | — | — |
| `detect_nodes(strikes, spot)` | Returns `kingNode`, `gatekeepers`, `midpoints` | ✅ | ❌ |
| `classify_levels(strikes, spot, flip)` | Per-strike `Level` with `kind` tag (king/gate/spot/flip/none) and composite `score` | ✅ | ❌ |
| `build_summary(ticker, snapshot_date, options)` | End-to-end producer of `GammaSummary` | — | — |

**Gap:** Every aggregation collapses the `expiration` dimension. The
contract-level data has it; the math layer drops it.

### 2.3 API layer (`platform/api/routers/options.py`)

| Endpoint | Returns | Per-strike? | Per-expiration? |
|---|---|---|---|
| `GET /api/options/dates/{ticker}` | List of snapshot dates available | — | — |
| `GET /api/options/{ticker}/{date}` | Raw chain (every contract row) | ✅ contract-level | ✅ via the `expiration` field on each row |
| `GET /api/options/{ticker}/{date}/levels` | `GammaSummary` JSON | ✅ in `levels[]` | ❌ collapsed |
| `POST /api/options/greeks` | Aggregates (king, gatekeepers, midpoints, gex_by_strike) | ✅ | ❌ |
| `GET /api/options/live/{ticker}/{date}` | Live AV proxy (fallback) | ✅ contract-level | ✅ via field |

**Gap:** No endpoint returns a `strike × expiration` 2-D grid. The raw
chain endpoint has every individual contract, so the frontend CAN
reconstruct the grid client-side, but it's expensive (~14 k rows
transferred per call) and the math should live server-side per the
"one source of truth" rule.

### 2.4 Frontend (`platform/src/routes/OptionsFlowPage.tsx`)

- D3.js horizontal bar heatmap, **one dimension only**: bar per strike,
  width = \|GEX\|, color by sign
- Toggle: GEX ↔ VEX (but VEX is the *total*, not per-strike — so the
  VEX view today is misleading; it doesn't reflect per-strike vanna)
- Toggle: net / calls / puts
- Date picker, manual spot override
- Renders ★ for King, ◆ for Gatekeeper, ● for Midpoint
- Display window ±8 % around spot by default

**Gap:** No way to select an expiration. No way to see the heat
distribution across the expiration cone (e.g., "is gamma stacked in
this week's expiry or pushed out to monthlies?"). No rate-of-change
indicator (you have to manually flip between dates).

### 2.5 Documentation (`docs/gamma_levels.md`)

Captures the King/Gate/Spot/Flip taxonomy + sign convention + spot
estimation. **Does not** discuss:
- Vanna / VEX beyond a passing mention
- Per-expiration aggregation
- Hedge Nodes / OPEX Nodes / Rate-of-change
- Strike-grid visualization

---

## Part 3 — Where the gaps actually are

Comparing Heatseeker's screenshots to our system, the missing pieces
in priority order:

| # | Gap | Difficulty | Trader value |
|---|---|---|---|
| 1 | **Per-expiration GEX/VEX breakdown** ("strike × expiration grid") | Easy — math is one extra `groupby('expiration')` | High — answers "is the pressure THIS week or next quarter?" |
| 2 | **Per-strike VEX** (not just total) | Easy — port `gex_by_strike` shape | High on event days |
| 3 | **Calls vs puts as separate rows** in the level taxonomy | Easy — already have `call_gex`, `put_gex` per strike | Medium — useful for "put wall at 640, call wall at 650" reading |
| 4 | **2-D heatmap UI** | Medium — D3 grid not bar chart | High — main user-visible deliverable |
| 5 | **Rate-of-change indicator** (5-min Δ \|GEX\|) | Medium — cross-snapshot diff | High during fast tape |
| 6 | **Hedge Node tag** (event-correlated, far-from-spot, persistent) | Hard — needs event-window logic | Medium — context for FOMC/CPI mornings |
| 7 | **OPEX Node tag** (expires within N trading days) | Trivial — date math | Low/Medium — calendar-driven, mostly a UI hint |
| 8 | **Tactical "great entry / not entry" overlay** | Hard — synthesis of all above | This IS the headline product |

---

## Part 4 — Proposal: data layer

We have two reasonable shapes for the new aggregates. **Recommendation:
both**, because they answer different questions and have very different
cost profiles.

### 4.1 Per-snapshot per-strike per-expiration aggregate (the cell)

This is the core "node" the heatmap renders. One row per (snapshot, ticker, strike, expiration).

**Option A — Materialized view (recommended for v1).** No new table.
A SQL view computes the aggregate on demand from `etf_options_snapshots`:

```sql
CREATE OR REPLACE VIEW v_etf_options_node AS
SELECT
    ticker,
    snapshot_ts,
    snapshot_date,
    market_session,
    expiration,
    strike,
    -- Per-strike aggregation (matches lib.gamma.aggregate_by_strike sign convention)
    SUM(CASE WHEN option_type = 'calls' THEN COALESCE(gamma,0) * COALESCE(open_interest,0)
             WHEN option_type = 'puts'  THEN -COALESCE(gamma,0) * COALESCE(open_interest,0)
             ELSE 0 END)                                          AS net_gamma,
    SUM(CASE WHEN option_type = 'calls' THEN COALESCE(gamma,0) * COALESCE(open_interest,0) ELSE 0 END) AS call_gamma_oi,
    SUM(CASE WHEN option_type = 'puts'  THEN COALESCE(gamma,0) * COALESCE(open_interest,0) ELSE 0 END) AS put_gamma_oi,
    SUM(CASE WHEN option_type = 'calls' THEN COALESCE(vega,0)  * COALESCE(open_interest,0) ELSE 0 END) AS call_vega_oi,
    SUM(CASE WHEN option_type = 'puts'  THEN COALESCE(vega,0)  * COALESCE(open_interest,0) ELSE 0 END) AS put_vega_oi,
    SUM(CASE WHEN option_type = 'calls' THEN COALESCE(open_interest,0) ELSE 0 END) AS call_oi,
    SUM(CASE WHEN option_type = 'puts'  THEN COALESCE(open_interest,0) ELSE 0 END) AS put_oi,
    SUM(CASE WHEN option_type = 'calls' THEN COALESCE(volume,0) ELSE 0 END)        AS call_volume,
    SUM(CASE WHEN option_type = 'puts'  THEN COALESCE(volume,0) ELSE 0 END)        AS put_volume
FROM etf_options_snapshots
WHERE data_source = 'alphavantage'
GROUP BY ticker, snapshot_ts, snapshot_date, market_session, expiration, strike;
```

- **No storage cost** (computed on read).
- **Read cost** = full table scan filtered to one ticker/snapshot — already what we do today.
- Postgres `MATERIALIZED VIEW` variant if read latency becomes a problem.

**Option B — Materialized table refreshed by the fetcher.** New table
`etf_options_node` populated immediately after each fetch:

```sql
CREATE TABLE etf_options_node (
    id              BIGSERIAL PRIMARY KEY,
    ticker          VARCHAR(10) NOT NULL,
    snapshot_ts     TIMESTAMPTZ NOT NULL,
    snapshot_date   DATE NOT NULL,
    market_session  VARCHAR(30) NOT NULL,
    expiration      DATE NOT NULL,
    strike          DOUBLE PRECISION NOT NULL,
    spot_at_snapshot DOUBLE PRECISION,        -- captured at write time
    -- Greeks aggregates (one row per cell)
    net_gamma       DOUBLE PRECISION,
    call_gamma_oi   DOUBLE PRECISION,
    put_gamma_oi    DOUBLE PRECISION,
    net_vega        DOUBLE PRECISION,
    call_vega_oi    DOUBLE PRECISION,
    put_vega_oi     DOUBLE PRECISION,
    call_oi         INTEGER,
    put_oi          INTEGER,
    call_volume     INTEGER,
    put_volume      INTEGER,
    -- Dollar-notional (computed)
    gex             DOUBLE PRECISION,         -- net_gamma × spot² × 0.01
    call_gex        DOUBLE PRECISION,
    put_gex         DOUBLE PRECISION,
    vex             DOUBLE PRECISION,         -- net_vega × spot × 0.01
    inserted_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_etf_options_node UNIQUE (ticker, snapshot_ts, expiration, strike)
);
CREATE INDEX idx_etf_options_node_ticker_ts ON etf_options_node (ticker, snapshot_ts DESC);
CREATE INDEX idx_etf_options_node_ticker_exp ON etf_options_node (ticker, expiration);
```

- **Storage cost:** for 3 tickers × ~80 strikes × ~20 expirations ×
  84 snapshots/day = ~400 k rows/day. ~150 MB/year per ticker — trivial.
- **Read cost:** index-covered for the two common queries.
- **Write cost:** one extra upsert per fetcher run. Currently the
  fetcher writes ~14 k rows; this would add another ~1.5 k aggregate rows.
- **Latency:** sub-100 ms per heatmap render once populated.

**Recommendation:** start with **Option A (view)** in Phase A. If
read latency exceeds 500 ms on SPY (likely once table grows), migrate
to **Option B (materialized table)** in Phase B with the fetcher
backfilling.

### 4.2 Per-snapshot per-strike (collapsed expiration) — the existing aggregate

This is what `aggregate_by_strike()` already computes. We keep it as
a degenerate case (sum over expirations) and either:
- Compute on the fly from the per-expiration aggregate when needed
- Add a `WHERE expiration IS NULL` row to the same materialized table
  (uglier; not recommended)

### 4.3 Time-series / rate-of-change

To answer "did the King at 650 just GROW in the last 15 min?" we need
the last N snapshots side by side. With the per-cell aggregate table
above, this is a simple window function:

```sql
SELECT strike, expiration,
       gex AS gex_now,
       LAG(gex, 1) OVER w AS gex_15min_ago,
       LAG(gex, 3) OVER w AS gex_45min_ago,
       gex - LAG(gex, 1) OVER w AS delta_gex_15min
FROM etf_options_node
WHERE ticker = 'SPY' AND snapshot_ts >= NOW() - INTERVAL '1 hour'
WINDOW w AS (PARTITION BY ticker, strike, expiration ORDER BY snapshot_ts);
```

No new table needed.

### 4.4 No new fetcher work

Both options live on the existing fetcher output. The realtime fetcher
already runs every 5 min during RTH; the EOD fetcher runs nightly. No
new ingest paths, no new external API calls, no scheduler changes.

---

## Part 5 — Proposal: math layer (`lib/gamma.py` additions)

Three new functions; one mild refactor of existing aggregator.

### 5.1 Add per-strike VEX (mirror existing GEX shape)

```python
def vex_by_strike(strikes: Sequence[dict], spot: float) -> list[dict]:
    """Per-strike VEX in dollar-notional terms.

    Mirror of gex_by_strike. Uses dealer-perspective negation on vega
    (matches total_vex). The convention:
        vex_per_strike = -(call_vega_oi - put_vega_oi) × spot × 100 × 0.01
    """
    return [
        {
            "strike": s["strike"],
            "vex":      -(s["call_vega"] - s["put_vega"]) * spot * SPOT_MULTIPLIER * VEX_MULTIPLIER,
            "call_vex": -s["call_vega"] * spot * SPOT_MULTIPLIER * VEX_MULTIPLIER,
            "put_vex":   s["put_vega"]  * spot * SPOT_MULTIPLIER * VEX_MULTIPLIER,
        }
        for s in strikes
    ]
```

Requires `aggregate_by_strike()` to also accumulate `call_vega` and
`put_vega` — one-line addition.

### 5.2 Add per-expiration aggregation

```python
def aggregate_by_strike_expiration(options: Sequence[dict]) -> list[dict]:
    """Group an options chain by (strike, expiration) instead of just strike.

    Returns the same shape as aggregate_by_strike, with an additional
    'expiration' key per row. This is the input to the 2-D heatmap.
    """
    # Same as aggregate_by_strike but keyed on (strike, expiration) tuple.
    ...
```

### 5.3 Add 2-D summary builder

```python
def build_grid_summary(
    ticker: str,
    snapshot_date: str,
    options: Sequence[dict],
    expirations: list[str] | None = None,   # filter; default = all
    strike_window_pct: float = DEFAULT_STRIKE_RANGE_PCT,
) -> GammaGridSummary:
    """Produce the 2-D strike × expiration GammaGridSummary."""
```

New dataclass:

```python
@dataclass
class GammaGridCell:
    strike: float
    expiration: str           # ISO date
    gex: float
    call_gex: float
    put_gex: float
    vex: float                # ← NEW: per-cell VEX
    call_vex: float
    put_vex: float
    net_gamma: float
    net_vega: float
    call_oi: int
    put_oi: int
    call_volume: int
    put_volume: int
    distance_pct: float
    dte: int                  # days to expiration (helpful tag for OPEX/0DTE/weekly)

@dataclass
class GammaGridSummary:
    ticker: str
    snapshot_date: str
    snapshot_ts: str          # ISO
    spot: SpotEstimate
    flip: float | None
    regime: str
    total_gex: float
    total_vex: float
    cells: list[GammaGridCell]
    expirations: list[str]    # for the column headers
    strikes: list[float]      # for the row headers
    warnings: list[str]
```

### 5.4 Optional: Hedge Node detection

```python
def detect_hedge_nodes(
    grid: GammaGridSummary,
    event_dates: list[date],          # from economic_events table
    persistence_lookback_days: int = 5,
) -> list[GammaGridCell]:
    """A cell is a Hedge Node if:
       - distance_pct > 5% from spot
       - |gex| grew >30% in the lookback_days BEFORE the nearest event_date
       - cell persisted across ≥3 of the last 5 sessions
    """
```

This pulls `economic_events.event_date` + `economic_events.importance =
'high'` for the lookback window. Easy join.

---

## Part 6 — Proposal: API layer

Three new endpoints, one breaking change.

### 6.1 `GET /api/options/{ticker}/{date}/grid` (NEW)

Returns the full 2-D `GammaGridSummary` for a given snapshot.

**Query params:**
- `snapshot_ts` — exact intraday ts (default: latest)
- `expirations` — comma-separated list (default: all in chain)
- `strike_window_pct` — strike band around spot (default: 0.15)
- `metric` — `gex` | `vex` | `both` (default: `both`)

**Response shape:** the `GammaGridSummary` dict from §5.3.

**Read cost:** ~80 strikes × ~10 expirations = 800 cells per ticker
per snapshot. JSON payload ~30 KB. Cached for the snapshot_ts.

### 6.2 `GET /api/options/{ticker}/{date}/grid/timeseries` (NEW)

Returns the last N snapshots of a particular (strike, expiration) cell
for rate-of-change visualization.

**Query params:**
- `strikes` — comma-separated list (default: top 10 by \|GEX\|)
- `expiration` — single expiration
- `lookback_hours` — default 1
- `metric` — `gex` | `vex`

**Response:** `[{snapshot_ts, strike, gex/vex, delta_from_prev}, ...]`

### 6.3 `GET /api/options/{ticker}/{date}/nodes` (NEW — semantic-layer)

Returns the *trader-facing* node taxonomy for the date: King, Gatekeepers,
Midpoints, Hedge Nodes, OPEX Nodes, Flip — each with the tactical
context the brief and the AI insight pipeline would want.

**Response:**
```json
{
  "ticker": "SPY",
  "snapshot_date": "2026-05-23",
  "spot": {"price": 502.10, "method": "parity"},
  "flip": 500.50,
  "regime": "positive_gamma",
  "data_source": "realtime",
  "kings": [{"strike": 505, "gex": 1.2e9, "call_oi": 50000, "put_oi": 2000, "distance_pct": 0.58, "dominant_side": "call"}],
  "gatekeepers": [...],
  "midpoints": [...],
  "hedge_nodes": [{"strike": 480, "gex": -800e6, "linked_event": "FOMC 2026-06-12", "distance_pct": -4.4, "persistence_days": 4}],
  "opex_nodes": [{"strike": 500, "expiration": "2026-05-30", "dte": 7}],
  "tactical_summary": {
    "current_state": "Pinning between 500 (flip) and 505 (King) — positive gamma regime",
    "long_setup": "Buy support at flip 500 / King 502 reclaim with target King 505",
    "short_setup": "Fade resistance at King 505 / break of flip 500 → trend to next gatekeeper 495",
    "invalidation": "Close < 498 = break of cluster, regime risk to negative gamma",
    "vex_note": "Vol crush of >2% IV today implies dealer-buy pressure of ~$4M per 1% drop"
  }
}
```

**This is the headline endpoint** — it's what powers the "great entry vs
not great entry" UX. The `tactical_summary` is the AI insight pipeline's
gamma analyst output, served fresh per snapshot.

### 6.4 Breaking change (small): `/levels` becomes a thin wrapper

`/api/options/{ticker}/{date}/levels` continues to return the existing
`GammaSummary` shape but is recomputed from the new grid → no consumer
change. New consumers should use `/nodes` instead.

---

## Part 7 — Proposal: frontend

Goals (re-stated from the conversation):
1. Show the trader where the magnets are
2. Show puts vs calls separately so "high put liquidation at 650" reads as one glance
3. Provide actionable entry/exit context, not just data
4. Visually distinct from Heatseeker — better dark mode, denser layout

### 7.1 New page: `/options-grid/:ticker`

Two-panel layout:

**Left panel (60% width): 2-D heatmap**

```
                  Exp →  May 30   Jun 6    Jun 13    Jun 20    Jul 18
                  DTE →    7d      14d      21d      28d      57d
   Strike ↓
   510             ░         ▒        ▒         ▒        ▒
   505 ★ King   →  ████      ███      ██        ██       █
   502 ► Spot     ▒░        ▒        ▒         ▒        ▒
   500 Flip     →  ░░░       ░░       ░         ░         ░
   495 Gate     →  ██        ██       ██        ██       ██
   490            ▒          ▒        ▒          ▒         ▒
   485            ░          ░        ░          ░         ░
   480 Hedge†  →             ▒░        ▒          ▒         ░
```

- Color: yellow/green = positive GEX, purple/blue = negative GEX
- Intensity: \|GEX\| as % of max in window
- Markers: ★ King, ◆ Gatekeeper, ► Spot, ⏷ Flip, 🛡 Hedge Node
- Toggle (top): **GEX layer** vs **VEX layer** vs **VEX-on-GEX overlay**
  (color = GEX, intensity-modifier = VEX magnitude)
- Toggle: **Net** vs **Calls** vs **Puts** vs **Calls+Puts split bars**
- Click a cell → time-series modal showing last 1h evolution
- Hover a cell → tooltip with `OI calls/puts, volume calls/puts, vega, IV`

**Right panel (40% width): "Tactical Read"**

- Sticky header with current spot, regime, total GEX/VEX, snapshot timestamp
- Per-level cards (one per King + Gatekeeper) showing:
  - Distance from spot
  - Dominant side (calls/puts)
  - Suggested action (from `/nodes` endpoint)
  - Invalidation level
- Bottom: "Hedge Node alerts" — if any present, with the linked
  `economic_events` row inline ("FOMC 2026-06-12 at 14:00 ET")
- Bottom: Rate-of-change sparkline for the King and top 2 Gatekeepers

### 7.2 OptionsFlowPage backward compat

Keep the existing 1-D bar chart at `/options-flow` for users who like
it. The new `/options-grid` is additive, not a replacement. Both pull
from the same Cloud SQL backend.

### 7.3 What it looks like at the data level — worked example

**Question:** "Show me high liquidation potential at 650 for SPY."

With the new endpoints:

```bash
GET /api/options/SPY/2026-05-23/grid?strike_window_pct=0.05&metric=both
```

returns a cell list. Find the row where `strike = 650`:

```json
{
  "strike": 650,
  "expiration": "2026-06-20",     // June monthly OPEX
  "dte": 28,
  "gex":      -180.5e6,            // negative = put-dominated
  "call_gex":   12.0e6,
  "put_gex":  -192.5e6,            // calls light, puts heavy
  "vex":       -8.2e6,             // vol-crush would generate dealer-sell
  "call_oi":   3200,
  "put_oi":   28500,                // 9x more puts than calls → "put wall"
  "call_volume": 800,
  "put_volume":  4100,
  "distance_pct": -1.2,            // 1.2% below spot
  "tags": ["gatekeeper", "opex"]
}
```

**Interpretation the platform surfaces in the right panel:**

> ⚠️ **650 (28 DTE, June OPEX)** — Put wall. 28.5k OI puts vs 3.2k OI
> calls → dealers short ~$180M gamma. If spot tests 650 from above
> with volume, expect amplified breakdown (negative gamma regime
> below) toward next Gatekeeper at 645. If 650 holds from below, it's
> a high-quality long setup with stop < 648.
>
> 💨 VEX: −$8M per 1% IV move. A vol spike alongside the test would
> magnify dealer selling.

This is exactly the "great entry / not great entry" UX. The frontend
just renders what `/nodes` returned.

---

## Part 8 — Implementation phases

Phase boundaries chosen so each phase is independently deployable and
provides user-visible value.

### Phase A — Math + view (1-2 days, no UI)

Goal: server-side data layer. No user-visible change yet.

- Add `aggregate_by_strike_expiration()` to `lib/gamma.py`
- Add `vex_by_strike()` to `lib/gamma.py` (requires `aggregate_by_strike`
  to also accumulate vega)
- Add `build_grid_summary()` + `GammaGridSummary` dataclass
- Create the `v_etf_options_node` view in `gcp/schema.sql`
- Unit tests: 4 new tests in `tests/test_gamma.py` covering the
  per-expiration aggregator + per-strike VEX
- No new fetcher work
- No API/UI change

Capacity: trivial. Adds zero query load.

### Phase B — API endpoints (2-3 days)

Goal: serve the data.

- Add `GET /api/options/{ticker}/{date}/grid`
- Add `GET /api/options/{ticker}/{date}/grid/timeseries`
- Add `GET /api/options/{ticker}/{date}/nodes` (with placeholder
  `tactical_summary = null` — wire to AI insights in Phase D)
- Tests in `tests/test_api_options.py`
- 12 h cache TTL on grid; 1 min cache on timeseries

Capacity: 800 cells per ticker × 3 tickers × ~84 reads/day from the
brief + insight pipeline + UI = ~200 k cell reads/day. ~6 KB per
read = 1.2 GB/day egress. Negligible cost.

### Phase C — Frontend (1 week)

Goal: user-visible 2-D heatmap + tactical panel.

- New route `platform/src/routes/OptionsGridPage.tsx`
- D3.js 2-D grid component
- Right-panel level cards with `/nodes` integration
- Vitest component tests
- Playwright e2e test (load SPY, click King cell, verify modal)

Capacity: pure client-side render of a ~30 KB JSON. No backend impact.

### Phase D — Tactical overlay & rate-of-change (1-2 weeks)

Goal: the "great entry" recommendations.

- Wire AI insights' gamma analyst to populate `tactical_summary` per
  ticker per snapshot (caches into `insight_reports` like today)
- Add Hedge Node detection (`detect_hedge_nodes` joining
  `economic_events`)
- Add rate-of-change sparklines in the right panel (uses the
  timeseries endpoint)
- Add `gamma_grid_alert` to `signal_alerts` (new alert_kind) for
  "King flipped to negative" / "new Gatekeeper formed within 1% of
  spot" / "VEX accelerating" — Discord-published

Capacity: AI insight cost ≈ $0.003/snapshot × 84/day × 3 tickers ≈
$0.75/day. Hedge Node detection is a small SQL join, free.

### Phase E (optional) — Materialize the view (1 day)

Goal: read latency.

- Convert `v_etf_options_node` to `etf_options_node` materialized
  table populated by the fetcher
- Backfill from `etf_options_snapshots`
- Drop the view

Triggered when read latency on the grid endpoint exceeds 500 ms on SPY
in production logs.

---

## Part 9 — Costs

| Phase | One-time eng | Monthly recurring | What you get |
|---|---|---|---|
| A | 1-2 days | $0 | Server-side data layer |
| B | 2-3 days | <$1 (egress) | Reachable from any consumer |
| C | 1 week | $0 | User-visible heatmap |
| D | 1-2 weeks | ~$22 (AI insights × 84 fires/day × 30 days) | Tactical recommendations |
| E | 1 day | ~$0.50 (extra storage) | Sub-100ms read latency |
| **Total** | ~3-4 weeks | ~$25/month | Heatseeker parity + AI-driven entry recos |

For comparison: Track 0's realtime fetcher is ~$5/mo. The full
Heatseeker subscription publicly listed is $99-149/mo. We can do
better at much lower cost because we own the platform.

---

## Part 10 — Open questions for product owner

1. **Tickers in scope.** Today realtime is SPY/IWM/QQQ. Heatseeker
   emphasizes "high-liquidity tickers" — would you also want NVDA, TSLA,
   META, etc.? Each adds ~$1/mo to realtime cost. (Answer affects the
   AV API budget and the per-snapshot row count.)
2. **VEX as separate layer or color-modifier?** Heatseeker uses a
   single GEX color and treats VEX as a confluence checker. I'd
   recommend giving VEX its own layer (toggle), because the use case
   for VEX is different (event days). The color-modifier overlay can
   be a Phase D nice-to-have.
3. **Hedge Node detection threshold.** I proposed >5% distance, >30%
   growth, >3 sessions persistence. These are inherited from
   Heatseeker's prose; we should backtest on the 2026-04-08 FOMC
   morning to tune.
4. **Push to Discord?** Phase D's `gamma_grid_alert` would fire on the
   existing Discord webhook (same channel as `signal_alerts`). Or a new
   `#gamma-watch` channel?
5. **Backfill horizon.** The new view scales fine across history, but
   the `tactical_summary` AI cost would balloon if we run it across
   months of historical snapshots. I'd default to "live snapshots only"
   and add an opt-in `--backfill --since=2026-05-22` flag for the
   insight-pipeline job.
6. **Stratalyst alignment.** The user mentioned strat-plus-options
   traders specifically. Should the Heatseeker terminology adopt
   Strat-native names (e.g., "Inside Pivot Node" instead of "Midpoint")
   to match the rest of the platform's brief vocabulary?

---

## Part 11 — Glossary

| Term | Meaning |
|---|---|
| **GEX** | Gamma Exposure. Dollar-notional that dealers must hedge per 1% move in spot. Per strike, summed across the chain, flipped to dealer-perspective. |
| **VEX** | Vanna Exposure. Dollar-notional dealer hedge required per 1% IV change. Different from GEX; matters on vol-regime-change days. |
| **Vanna** | The second-order Greek `∂Δ/∂σ` — how delta changes when IV moves. |
| **King** | The strike with the largest \|GEX\| in the display window. Dealer's preferred end-of-day pin target. |
| **Gatekeeper** | Secondary high-\|GEX\| strikes between current spot and the King. Block price from reaching the King; failure to defend → trend shift. |
| **Spot** | Current underlying price. Estimated via put-call parity → delta proxy → median strike fallback. |
| **Flip** | The price level where cumulative GEX crosses zero. Above the flip = positive gamma regime (pinning, range-bound). Below = negative gamma (trending, volatile). |
| **Midpoint** | The middle of a defined range; "Market Maker's favorite trap" — worst R:R for directional trades. |
| **Hedge Node** | A far-from-spot node built before macro events (FOMC/CPI/NFP/earnings); static, slow-unwinding. |
| **OPEX Node** | A node anchored to a monthly third-Friday expiration; loses weight as contracts expire. |
| **Rate of Change** | How fast a node's value is growing/shrinking between snapshots. Rapid accumulation = magnet strengthening. |
| **Reshuffle** | A snapshot-to-snapshot change in node positions; often precedes a trend change. |
| **Confluence** | When SPX, SPY, and QQQ agree on the same direction's nodes. |
| **Positive Gamma** | Spot is above the flip. Dealers buy dips / sell rips → suppresses vol → range-bound. |
| **Negative Gamma** | Spot is below the flip. Dealers sell dips / buy rips → amplifies vol → trending. |
| **DTE** | Days to expiration. |
| **OPEX** | Monthly options expiration (third Friday). |
| **0DTE** | Same-day expiration options; SPY/QQQ have these every weekday. |

---

## Appendix A — Where this aligns with the existing roadmap

The Realtime Options Multi-Track Plan
([`REALTIME_OPTIONS_MULTITRACK_PLAN.md`](REALTIME_OPTIONS_MULTITRACK_PLAN.md))
already lists five tracks that could fold into this:

- **Track 0** (merged) — Realtime fetcher. Required prerequisite. ✅
- **Track 1** (merged in PR #537) — Brief gamma section realtime-primary. ✅
- **Track 3** — Signal monitor gamma awareness (`gamma_king_approach`,
  `gamma_gate_break`, `gamma_flip_cross` alert types). Phase D of this
  plan overlaps strongly; the alert types defined here become the same
  `signal_alerts.alert_kind` values.
- **Track 4** — OptionsFlowPage freshness badge. Already complementary.
- **Track 5** (merged in PR #537) — AI insights gamma `data_source` awareness. ✅

This plan is essentially **the productization of Tracks 3 + 4 +
extensions**. We should consider folding it into the multi-track plan as
Tracks 6/7/8 once we agree on the design.
