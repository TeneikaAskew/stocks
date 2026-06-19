# Feature-Adoption Roadmap — "Stock Insights"

**Goal (user's words):** *take what I like from other platforms and make it my own.*

**Inspiration sources** (other apps the user likes — **not** this product):
- **Stratalyst** (lab.learnthestrat.com) — a Strat-methodology stock app; closest north-star.
- **Skylit** — options/GEX terminal.
- **@Glitch social-trading app** — community/profile features (**deferred**).

**Priorities (set by the user):** the **GEX Terminal**, **Heatseeker**, and **Flowseeker** are all
**high**; **social/community is deferred entirely**. Reuse existing branch work
(`feat/gamma-grid-phase-*`, `docs/heatseeker-style-gamma-research`, merged redesign) before building
net-new. See [`PLATFORM_AUDIT_2026-06-19.md`](PLATFORM_AUDIT_2026-06-19.md) for current state.

## Top-3 (confirmed) — Skylit options/GEX

| # | Feature (source) | Today in Stock Insights | Adoption path | Notes |
|---|---|---|---|---|
| 1 | **GEX Terminal** — candles + GEX-node overlay, Orbs/Heatmap modes, **Replay**, expirations/nodes/exposure (Skylit) | `/charts` has gamma King/Gate/Flip/Balance overlays; no replay terminal | Extend `/charts` (or a new Dealer-GEX surface): overlay nodes on candles + a **Replay scrubber** over `market_data_intraday`; later add **AUTO-3D**. Reuse `lib/gamma.py`, `grid` router, `intraday_gex_15m`/`realtime_gex_15m` | Data exists; mostly frontend + a replay endpoint |
| 2 | **Heatseeker** — strike×date 2-D gamma heatmap incl. multi-ticker "Trinity" 3-up (Skylit) | `/options` Heatseeker-Swing is **mock**; Profiles real | Replace mock with real 2-D heatmap from `etf_options_daily_greeks`/`intraday_gex_15m`; add 3-up multi-ticker view | Build on the `grid` router |
| 3 | **Flowseeker** — live flow tape / scanner / tracker + **Contract Drilldown** (flow histogram, chain-ratio, RVOL/IV) (Skylit) | `/options` Flowseeker is **mock** | Build tape + drilldown UI | **Gated on an options-flow / time-&-sales data feed** — confirm a source first (see Open Decisions) |

## Deferred

| Feature (source) | Decision |
|---|---|
| **Social trader profile / radar trade-stats / shareable trades / leaderboard** (@Glitch) | **Deferred entirely** per user. If revisited later, builds on a `users` table + per-user `trades`/`journal_entries`. |

## Additional candidates (Stratalyst north-star) — confirm priority/order

| Feature (Stratalyst) | Today | Adoption path |
|---|---|---|
| **Strat Scanner** — multi-TF (15m→W) with presets (FTFC Reversals, Inside Day, Failed 2U/2D, Bull/Bear Momentum), FTFC/In-Force/Watchlist filters | `/signals` + `/playbook` exist; no preset-driven scanner page | New scanner surface over `signals` / `lib/strat.py` / `strat_features_*`; presets as saved filters |
| **Dealer GEX dashboard** — Spot / GEX-Flip / Call-Put Wall / Regime cards, King/Gate/Flip nodes, Gatekeepers, Session Range, Expected Move, Air Pockets, GEX-by-strike, Node Retest Rules | `/charts` gamma overlays + `/options` Profiles; no dedicated dashboard | New Dealer-GEX page over `lib/gamma.py` + `grid` + `realtime_gex_15m` (post-#600 dedup). Pairs with Top-3 #1 |
| **Gappers Radar** — Gap ≥1% + Strat-pattern overlay + FTFC, premarket | none | New surface over `top_movers_daily` / `market_data_daily` + strat overlay |
| **Catalyst conviction cards** — conviction score, sentiment, options-play, related tickers, Today's Breakers, Intraday Movers | `/catalysts` timeline exists | Extend `catalysts` router/UI with conviction scoring + card layout |
| **Earnings Season UI** — Conviction Rankings, Drift Strangle, S/A/B/C grades (2hr / >1×ATR / Cont%) | backend ready via **#624** (3 mat-views + 8 endpoints); **no UI** | Build the earnings UI on #624's endpoints |
| **"Ask Pluto"-style AI copilot** on analytics surfaces | `/insights` Chat exists | Surface the existing chat as a context-aware copilot on Dealer-GEX / Scanner |

## Sequencing (suggested)
1. **Top-3 #1 GEX Terminal + Dealer GEX dashboard** (same data/area; biggest visible win; data ready).
2. **Top-3 #2 Heatseeker real heatmap** (replace mock; `grid` router ready).
3. **Earnings Season UI** (backend already merged via #624 — high ROI, just needs UI).
4. **Strat Scanner**, **Gappers Radar**, **Catalyst conviction cards** (Stratalyst parity).
5. **Top-3 #3 Flowseeker** — once an options-flow data feed is confirmed.
6. **AUTO-3D** GEX view — last (heaviest net-new).

## Open decisions
1. **Options-flow data feed** — is there a time-&-sales/flow source for Flowseeker, or defer it?
2. **Order of the Stratalyst-derived candidates** vs. the Top-3.
3. **Per-user watchlist** (audit finding #1) — fix now or already handled in your session?
