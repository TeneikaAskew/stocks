# Journal One-Stop-Shop Redesign — Design Spec

**Date:** 2026-07-11
**Status:** design approved via mockups (layout B "Cockpit"; CSV import v1, options-only) — see https://claude.ai/code/artifact/b57f184d-15e2-4ca3-89d1-3cf78e4793af
**Driver:** The Journal page must be the complete, self-contained trading-journal surface — chart, trade marking, examples, analytics, risk — on ONE page. The Charts page must carry ZERO journal activity (user directive, 2026-07-11: "charts should NOT be used for any journal activities at all, that is completely separate"). Examples dataset = the admin's real journal trades.

## The problem being fixed

Today the journaling experience is split: trade marking (Mark Entry → CALL/PUT → TP1/TP2/TP3 → stop-loss), the trades side panel, and Backtest-my-trades live on `/charts`; the Journal page is a form + table + equity curve that renders nearly empty until the user has logged trades. New users see a bare page and no path to understanding trades, risk, or the marking workflow. The seed/examples layer (admin trades as teaching data) exists only as muted markers on the Charts page.

## Target design

### Approved layout: Option B — "Cockpit"

Chart with a **trade rail pinned beside it** (right column, ~340px): one card per trade of the active view on the selected date. Card layout (user-refined): top row = direction badge (+ EX badge in Examples) on the left, **return % centered and prominent** (e.g. `+1.14%`, bull/bear colored, largest text on the card), time on the right; second line = Entry $ → Exit $; third line = TP prices · SL · R:R. Hovering a card highlights its markers on the chart.

**Rail refinements (user, 2026-07-11):** the **equity curve card sits in the rail, under the trade cards** (cumulative P&L %, all dates). There is NO separate session-stats card — its metrics fold into the KPI row, which gains **Avg R:R** and **TP1 hit** tiles (7 tiles total).

**KPI/table scoping (user, 2026-07-11):** the KPI tiles and the full trade table open in **Overview scope (all dates)**; the moment a date is selected they re-scope to that session's trades. The active scope is always labeled next to the tiles ("Overview — all dates" / "Session — MM/DD/YYYY"), and clearing the date returns to Overview. The equity curve is always cumulative across all dates. TP1-hit = share of closed trades with TP1 set whose exit price reached TP1 ("—" when no closed trade has TP1 set — no fabricated rates).

Below the chart+rail row: scope label + 7 KPI tiles, then the full-width trade table.

### Trade import (user addition, 2026-07-11)

An **Import from broker** button joins the trades section (all views; writes to My journal only):
- **V1 = CSV/statement upload.** Native auto-detected parsers for **Robinhood and Webull** (header-row detection); **Schwab / Fidelity / IBKR / other platforms** import via a generic column-mapper with prefilled per-broker presets (user confirms the mapping once; preset saved). Every exporting platform works; the named two are zero-configuration.
- **Options trades only** (fits the CALL/PUT journal model). Stock/share rows appear in the preview as "skipped: shares" — never silently dropped.
- Buys/sells are paired into round-trip trades; unpaired opens import as `status='active'` with no fabricated exit (Rule 3.7). Preview step before commit; duplicate detection makes re-importing the same file idempotent (match on ticker + entry_ts + entry_price + direction).
- Imported rows carry `source='import:<broker>'`.
- Live broker sync (aggregator API, OAuth) is explicitly out of scope for v1 — separate decision later.

### Journal page (`/journal`) — top to bottom

1. **Header row:** `{ticker} Trade Journal`, TickerCombobox, trading-date picker (same dates API as Charts), view toggle **[ Examples | My journal ]**, Add Trade (manual form kept), CSV / Export-to-Pipeline (existing).
2. **Interactive chart card** (the one-stop centerpiece):
   - Same `CandlestickChart` component and market-data hooks as Charts; timeframe buttons (1m/5m/15m/30m/1h), Vol + RTH toggles; viewport-based height (same clamp as the restored Charts page).
   - **Full Mark Entry flow lives HERE**: Mark Entry → click chart (entry price) → CALL/PUT → click TP1 → TP2 → TP3 (ESC skips) → click Stop Loss (ESC skips); later "exit" per trade. Identical state machine to today's ChartsPage implementation — moved, not rewritten.
   - Trades of the **active view** (Examples or My journal) whose entry/exit fall on the selected date are drawn: entry/exit markers + TP/SL price lines. Example trades draw in the muted seed style; own trades in the standard style.
3. **KPI tiles + notes** (existing): Trades, Win rate, Total P&L, Avg/trade, Avg win, include-practice toggle, exclusion notes — computed over the ACTIVE VIEW's trades. Rendered whenever the view has ≥1 trade.
4. **Equity curve** (existing card with placeholder).
5. **Trade table** (existing) **+ risk columns**: Stop, TPs (e.g. "223 / 225"), and R:R (|entry−TP1| / |entry−stop|, "—" when either is missing; display-layer only, no fabricated values per Rule 3.7). Per-trade actions: exit-on-chart, delete — disabled in Examples view.

### Views

- **Examples** = the admin's real journal trades (`journal_entries WHERE user_email = ADMIN_EMAIL`), read-only for everyone (including admin — admin edits via My journal, which IS the same data).
- **My journal** = the signed-in user's trades (current behavior).
- **Default view**: Examples when the user's own journal for the ticker is empty; otherwise My journal. Manual toggle always available and sticky per session.
- **Marking always writes to MY journal.** If the user marks a trade while viewing Examples, the view flips to My journal to show it. For the admin, own trades and Examples are the same dataset.
- **Nothing is gated on having trades.** Chart renders with market data regardless; Examples populate tiles/curve/table by default; a truly empty Examples set shows honest empty states inside each card (never a bare page).

### Charts page (`/charts`) — journal activity removed

- **REMOVE:** Mark Entry flow + drawing state machine, Trades/Analytics side panel (TradeCard list, Backtest-my-trades, trade analytics tab), trade JSON/CSV export, journal-trade fetching, seed-trade markers + Playbook-seed panel.
- **KEEP:** chart + toolbar (timeframes, Vol/RTH/Ref/Gamma/Sig), restored Live Strategy Conditions card, Similar Past Setups, signal overlay, historical review/date selection, **bar-replay trainer**.
- **Flagged decision (recommend keep-as-is):** the replay trainer stays on Charts as a practice/research tool. Its practice sessions still persist as `source='replay'` journal rows (excluded from stats by default) — that storage is an implementation detail, not user-facing journaling. Veto if you want the trainer moved to Journal too.
- Layout after removal: chart keeps full width (side panel gone → more chart), cards below unchanged.

### Backend

- **New:** `GET /api/journal/examples/{ticker}` — returns the admin's journal rows for the ticker in exactly the shape of `GET /api/journal/trades/{ticker}`. Admin identity from server config (`ADMIN_EMAIL`), never from the client. Read-only; no write variant. Auth: any signed-in user may read (it's teaching data). Excludes `source='replay'` rows (practice noise is not teaching material).
- Everything else exists: per-user trades CRUD, market data/dates, replay/backtest endpoints.
- Capacity (Rule 0): one additional indexed SELECT per journal page load (`user_email = ADMIN_EMAIL AND ticker = X`, same query shape/index as the existing per-user GET). No new jobs, no schedulers.

### What does NOT change

- Cloud SQL per-user persistence, TIMESTAMPTZ naive-ET conventions, stats math (`computeJournalStats`), breakeven=loss convention, practice-session exclusion, the restored Charts conditions card/height, Live/Signals/Playbook pages.

## Testing

- Backend: pytest for the examples endpoint (admin-scoping, shape parity with trades GET, replay exclusion, unavailable-DB envelope).
- Frontend: Playwright — journal one-stop flow (examples default when own journal empty, toggle, mark-a-trade-on-journal-chart writes to own journal and flips view, risk columns render with "—" honesty), charts-no-journal (Mark Entry absent, side panel absent, research cards intact), regression suites (charts-cards, replay-trainer, journal) updated.
- Eyes-on parity screenshots (populated Examples view) sent to user before deploy.

## Rollout

Single program, SDD task-per-slice: (1) examples endpoint, (2) extract the marking/chart module from ChartsPage into a shared component, (3) Journal page assembly, (4) Charts strip-down, (5) e2e + screenshots, (6) deploy staging → user acceptance → prod promote by revision name.
