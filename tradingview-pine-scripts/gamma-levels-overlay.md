# Gamma Levels Overlay v2

Pine Script v6 indicator that overlays King / Gate / Flip levels on any
TradingView chart. Companion to the gamma analytics produced by
`lib/gamma.py` and exposed via `/api/options/{ticker}/{date}/levels`.

## Why this exists

The `/charts` page in the React app already overlays gamma levels on
intraday charts via the `Gamma` toggle. This Pine companion is for:

1. **Pro charts** — multi-monitor TradingView setups, replay mode,
   custom drawing layers, alerts.
2. **Mobile** — the TradingView mobile app on the same chart.
3. **Backtesting** — TradingView's bar-replay tool, which our React
   chart doesn't have.

TradingView can't fetch from our API, so values are entered manually.
The script holds up to 3 Kings, 5 Gates, and 1 Flip — matching the
typical taxonomy for an SPY/IWM/QQQ window.

## How to use

1. **Get today's levels.** Either:
   - Open `/options` in the platform UI for SPY/IWM/QQQ/SPX. The chip
     row above the heatmap lists the King(s), Gate(s), and Flip with
     prices.
   - Or run from the repo root:
     ```
     python3 scripts/show_gamma_levels.py qqq
     ```

2. **Paste into the indicator inputs:**
   - `Levels date (YYYY-MM-DD)` — the snapshot date the levels are from
   - `King 1 strike`, `King 2 strike`, `King 3 strike` — top kings
   - `Gate 1` … `Gate 5` — gates
   - `Flip price` — the gamma flip
   - Leave any unused slots at `0.0`.

3. **Read the chart:**
   - **Solid orange** lines = Kings (primary support/resistance)
   - **Dotted blue** lines = Gates (secondary, must break before reaching King)
   - **Dashed purple** line = Flip (regime divider)
   - **Green tint** above flip = positive gamma regime (pinning, range-bound)
   - **Red tint** below flip = negative gamma regime (trending, vol-amplifying)

## Alerts

Three built-in alert conditions:
- King 1 crossed
- King 2 crossed
- Flip crossed (regime change)

Set up via the alert dialog → Condition → "Gamma Levels Overlay v2".

## Updating levels

EOD options snapshots are immutable, so for backtesting on a specific
historical date you'll want to fetch the levels for *that* date:

```
python3 scripts/show_gamma_levels.py qqq --date 20251121
```

The output's `KINGS:` / `GATES:` / `FLIPS:` lines map directly to the
indicator inputs. The `Levels date` field is just a label — it's
shown next to the Flip line so you remember which session the values
are valid for.

## Repo conventions

- Pine v6 only (`@version=6`)
- Single-file scripts (no folder)
- Companion `.md` colocated in `tradingview-pine-scripts/`
- See `tradingview-pine-scripts/UPGRADE-PLAN.md` for v1→v2 history
