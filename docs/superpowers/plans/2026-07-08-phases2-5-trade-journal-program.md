# Phases 2–5: Trade Journal, Labeled Backtest, Style Mining, Replay Trainer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chart-marked trades persist per-user in `journal_entries`, can be backtested against the production engine with a system benchmark, feed a style miner whose learned pattern is walk-forward validated into a playbook staging seam, and a bar-replay trainer lets users practice on historical sessions (spec §6–§9 of `docs/superpowers/specs/2026-07-07-platform-hardening-and-trade-journal-design.md`).

**Architecture:** Four sequential phases, ONE BRANCH + PR + DEPLOY EACH (schema migrations ship in the phase that needs them, applied via the `apply-schema-migrations` job BEFORE the service revision that reads them). Approach A throughout: `journal_entries` is the single per-user trade store; the pipeline `trades` table stays pure and serves as the read-only admin seed layer.

**Tech Stack:** FastAPI + pandas + SQLAlchemy-text over pg8000 (`= ANY(:list)` binding only), React 19 + TS + TanStack Query + zustand + lightweight-charts v5, pytest / vitest / Playwright (hermetic mocks; local vite on port 4321 with playwright.config.ts baseURL patched then REVERTED).

## Global Constraints

- **Branches:** `feature/phase2-journal-unification`, `feature/phase3-labeled-backtest`, `feature/phase4-style-mining`, `feature/phase5-replay-trainer` — each cut from main after the prior phase merges. BRANCH GUARD on every dispatch (concurrent session switches branches).
- **Commits:** single-line conventional, NO Co-Authored-By trailer, NO AI branding.
- **UNIT CONVENTION (load-bearing):** `journal_entries.return_pct` is TRUE PERCENT (`journal.py:88-92` multiplies ×100; Phase 0 established `*_pct` = percent). `lib/backtest.py` computes `return_pct` as a RAW FRACTION internally (`backtest.py:531`). Every new boundary converts explicitly and says so in a comment. API responses always emit percent.
- **TIME CONVENTION:** frontend chart times are UNIX SECONDS encoding NAIVE ET WALL CLOCK (main.py strips tz before epoch conversion — see live.py `_normalize_bar_time`). journal `entry_ts/exit_ts` are TIMESTAMPTZ built from naive ISO strings. Convert epoch→ISO via `pd.Timestamp(epoch, unit='s').strftime('%Y-%m-%d %H:%M:%S')` server-side or `new Date(epoch*1000).toISOString()`-free client code — the plan's tasks specify the exact helper each time. Never `tz_convert`.
- **Per-user scoping:** every new endpoint reuses `_journal_owner(request)` (`journal.py:43-52`; open mode → `"local"`) and the same fail-loud rule (Cloud SQL error + non-local owner → 503, never a silent local fallback).
- **Rule 3.7:** no `?? 0`/`|| 0` on rendered financials; explicit unavailable states; strict queries (`query_to_dataframe_strict` + 503) for new single-source endpoints.
- **Rule 3.6:** style-mining indicator snapshots go through the production lib indicator path (`lib.indicators.add_signal_indicators`, as `/api/live/signal-series` does) — never hand-rolled.
- **Playbook stays admin-only:** Phase 4 writes candidates to a STAGING table; the playbook UI does not read it (flag `PLAYBOOK_USER_CARDS` hardcoded off).
- **TDD everywhere.** Reviewer gates per task; capacity notes (Rule 0) in each PR.

---

# PHASE 2 — One trade log (branch `feature/phase2-journal-unification`)

### Task 2.1: Schema migration — journal_entries grows chart-trade fields

**Files:** Modify `gcp/schema.sql` (journal_entries block, ~line 1095); Test `tests/test_schema_journal_migration.py` (create)

**Interfaces — Produces (later tasks rely on these exact columns):** `stop_loss DOUBLE PRECISION NULL`, `tp1/tp2/tp3 DOUBLE PRECISION NULL`, `status VARCHAR(10) NOT NULL DEFAULT 'closed'` (values: active|win|loss|breakeven|closed), `source VARCHAR(10) NOT NULL DEFAULT 'manual'` (chart|manual|replay), `session_id UUID NULL`; `exit_ts`/`exit_price` become NULLABLE.

- [ ] **Step 1: Failing test** — the repo has schema tests (grep `tests/` for schema/DDL test precedents; if a pattern exists for asserting schema.sql contains idempotent migrations, follow it; otherwise):

```python
# tests/test_schema_journal_migration.py
"""Phase 2 journal_entries migration is present and idempotent-by-construction."""
from pathlib import Path

SCHEMA = Path("gcp/schema.sql").read_text(encoding="utf-8")

def test_journal_migration_columns_added_idempotently():
    for col in ("stop_loss", "tp1", "tp2", "tp3", "status", "source", "session_id"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in SCHEMA, col

def test_exit_columns_made_nullable():
    assert "ALTER COLUMN exit_ts    DROP NOT NULL" in SCHEMA.replace("  ", " ").replace("  ", " ") or \
           "ALTER COLUMN exit_ts DROP NOT NULL" in SCHEMA
    assert "ALTER COLUMN exit_price DROP NOT NULL" in SCHEMA

def test_source_index_exists():
    assert "idx_journal_entries_user_source" in SCHEMA
```

- [ ] **Step 2: fail → Step 3: implement** — append AFTER the existing journal_entries block (keep the existing CREATE TABLE untouched — new deployments then apply the ALTERs as no-ops):

```sql
-- ── Phase 2 (2026-07): chart-marked trades unify into the journal ──────────
-- Chart trades carry TP/SL levels, an ACTIVE (un-exited) state, a source
-- discriminator, and (for replay-trainer sessions) a grouping id. Additive
-- and idempotent; exit columns become nullable because active trades have
-- no exit yet. return_pct stays NULL until a trade closes (Rule 3.7 —
-- missing is never 0).
ALTER TABLE journal_entries
    ADD COLUMN IF NOT EXISTS stop_loss   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS tp1         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS tp2         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS tp3         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS status      VARCHAR(10) NOT NULL DEFAULT 'closed',
    ADD COLUMN IF NOT EXISTS source      VARCHAR(10) NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS session_id  UUID;
ALTER TABLE journal_entries ALTER COLUMN exit_ts    DROP NOT NULL;
ALTER TABLE journal_entries ALTER COLUMN exit_price DROP NOT NULL;
CREATE INDEX IF NOT EXISTS idx_journal_entries_user_source
    ON journal_entries (user_email, source, entry_ts DESC);
```

- [ ] **Step 4: pass → Step 5: commit** `feat(schema): journal_entries gains chart-trade fields; nullable exits for active trades`

### Task 2.2: Journal API — create-with-levels, PATCH close, seed layer

**Files:** Modify `platform/api/routers/journal.py`; Test `tests/test_journal_phase2.py` (create)

**Interfaces — Produces:**
- `JournalTradeCreate` gains OPTIONAL fields: `exit_date/exit_time/exit_price` become `Optional[...] = None` (active trades), plus `stop_loss: Optional[float] = None`, `take_profits: Optional[list[float]] = None` (≤3, maps to tp1..tp3), `status: Optional[str] = None` (derived if omitted: active when no exit, else win/loss/breakeven from return_pct), `source: str = "manual"`, `session_id: Optional[str] = None`.
- `PATCH /api/journal/trades/{trade_id}` body `{exit_date, exit_time, exit_price}` → closes an ACTIVE trade: server computes `return_pct` via the existing `_return_pct` (percent units) and status win/loss/breakeven; 404 if not owner's trade; 409 if already closed.
- `GET /api/journal/seed/{ticker}?date=YYYY-MM-DD` → read-only admin seed from the pipeline `trades` table: `{ticker, date, count, trades: [{id, direction, entry_time, entry_price, exit_time, exit_price, return_pct, strat_combo, exit_reason}]}` with `return_pct` CONVERTED fraction→percent (×100, commented — pipeline stores fractions). Strict query + 503; ANY-bind not needed (single ticker + date equality).
- `GET /api/journal/trades/{ticker}` response rows gain the new columns (nullable passthrough).

- [ ] **Step 1: Failing tests** (import/TestClient mechanics: copy tests/test_market_coverage.py's established pattern; monkeypatch the module's query/execute indirections — journal.py uses `query_to_dataframe`/`execute_sql` directly, so add module-level `_journal_query = query_to_dataframe` / `_journal_exec = execute_sql` indirections in the implementation and patch those):

```python
# tests/test_journal_phase2.py — substance to keep, adapt mechanics:
def test_create_active_trade_without_exit_returns_null_return_pct(client_local_owner):
    r = client.post("/api/journal/trades", json={
        "ticker": "SPY", "direction": "CALL",
        "entry_date": "2026-07-02", "entry_time": "10:15", "entry_price": 620.5,
        "stop_loss": 619.0, "take_profits": [621.2, 622.0, 623.1], "source": "chart",
    })
    assert r.status_code == 200
    assert r.json()["return_pct"] is None
    assert r.json()["status"] == "active"

def test_patch_close_computes_percent_return_and_status():
    # create active (as above), then:
    r = client.patch(f"/api/journal/trades/{tid}", json={
        "exit_date": "2026-07-02", "exit_time": "10:45", "exit_price": 621.74,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "win"
    assert body["return_pct"] == pytest.approx((621.74 - 620.5) / 620.5 * 100, rel=1e-6)

def test_patch_close_conflicts_on_already_closed():
    ... assert second PATCH returns 409

def test_seed_endpoint_converts_fraction_to_percent(monkeypatch):
    # monkeypatch the seed query to return one pipeline row with return_pct=0.003
    ... assert resp trade["return_pct"] == pytest.approx(0.3)

def test_take_profits_capped_at_three():
    ... 4 TPs -> 422
```

- [ ] **Step 2-3: fail → implement.** Keep the local-file (open dev) branch working for create/list (new fields flow into the JSON file rows too); PATCH + seed are Cloud-SQL-only (open dev: PATCH updates the JSON file row; seed returns `{status:"unavailable", reason:"no Cloud SQL"}`-shaped honest empty in local mode — decide by reading how get_trades handles local vs SQL and stay consistent). Derive status: no exit → `active`; else sign of return_pct → win/loss/breakeven.
- [ ] **Step 4: `python -m pytest tests/test_journal_phase2.py -v` all pass.** Step 5: commit `feat(api): journal supports active trades, close PATCH, and admin seed layer`

### Task 2.3: ChartsPage persistence — tradeStore → journal API

**Files:** Create `platform/src/hooks/useJournalChartTrades.ts`; Modify `platform/src/routes/ChartsPage.tsx`, delete `platform/src/stores/tradeStore.ts` (after all consumers swapped — grep `useTradeStore`); Test `platform/src/hooks/journalChartTrades.test.ts` (vitest, pure mappers) + extend `platform/tests/charts-cards.spec.ts`

**Interfaces — Produces:** pure mappers (exported, unit-tested):

```ts
/** Chart epoch-seconds encode naive-ET wall clock (main.py convention).
 * Render the wall-clock fields WITHOUT timezone conversion. */
export function epochToJournalDateTime(epochSec: number): { date: string; time: string } {
  const d = new Date(epochSec * 1000);
  const p = (n: number) => String(n).padStart(2, '0');
  return {
    date: `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}`,
    time: `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`,
  };
}
export function journalRowToTradeEntry(row: JournalRow): TradeEntry { ... } // ISO ts -> epoch via Date.parse(row.entry_ts)/1000 with the same naive convention: parse the 'YYYY-MM-DDTHH:MM:SS' prefix manually + Date.UTC — spell out in implementation
```

Hook: `useJournalChartTrades(ticker, date)` → TanStack query on `GET /api/journal/trades/{ticker}` filtered client-side to the chart date, plus `useCreateChartTrade()` (POST with `source:'chart'`, optimistic add), `useCloseChartTrade()` (PATCH, optimistic), `useDeleteChartTrade()`.

- [ ] **Step 1: vitest first** for the two mappers (epoch 1751463300 → `{date:'2026-07-02', time:'13:35'}` — verify the expected wall-clock values by computing from the naive-ET convention; round-trip journalRowToTradeEntry∘create-body ≈ identity).
- [ ] **Step 2-3: implement + rewire ChartsPage:** `completeTrade` POSTs (with TP/SL/source), the exit click PATCHes, delete calls DELETE; `currentTrades` comes from the hook (review-cutoff filter stays); markers/price-lines/TradeCard consume the same `TradeEntry` shape via `journalRowToTradeEntry`. Active-trade P&L display before close: unchanged client calc is display-only — keep, but the PERSISTED return comes from the server PATCH response (percent). Remove `tradeStore.ts` when `grep -rn useTradeStore platform/src` is empty.
- [ ] **Step 4: Playwright** — extend charts-cards.spec.ts with mocked journal routes: mark-entry flow POSTs the right body (assert `source:'chart'`, TP array, epoch→date/time mapping); reload-persistence is inherently covered by the GET mock rendering saved trades.
- [ ] **Step 5: gates (`vitest`, `tsc`, targeted Playwright) → commit** `feat(charts): trades persist per-user through the journal API`

### Task 2.4: Seed layer UI + benchmark row

**Files:** Modify `platform/src/routes/ChartsPage.tsx` (+ small `useSeedTrades` hook beside the others); Test: extend `platform/tests/charts-cards.spec.ts`

**Interfaces — Consumes:** Task 2.2's `GET /api/journal/seed/{ticker}?date=` (percent units). **Produces:** seed trades render as MUTED/dashed markers (distinct color, `text: 'SEED ' + ...`), a "Playbook seed" tag in the side panel list (read-only rows — no exit/delete buttons), a `Show seed trades` toggle (default ON, local state), and an analytics benchmark row: "Seed benchmark (same day): W% · avg +X%" computed from the seed response client-side by COUNTING (win = return_pct > 0) — display-only aggregation of already-server-computed percents, not financial math.

- [ ] Playwright-first (mock seed route with 2 trades → assert muted markers/panel tag/toggle hides them), implement, gates, commit `feat(charts): admin seed trades render as a read-only teaching layer`.

**PHASE 2 wrap:** final whole-branch review → PR (schema note: apply-schema-migrations BEFORE deploy; capacity: journal endpoints are single-row/single-ticker queries) → CI → merge → apply schema job → deploy staging/prod → verify (create+close+seed live) → ledger.

---

# PHASE 3 — Labeled backtest + benchmark (branch `feature/phase3-labeled-backtest`)

### Task 3.1: Extract reusable exit simulation in BacktestEngine

**Files:** Modify `lib/backtest.py` (run() ~lines 521-578); Test `tests/test_backtest_exit_extraction.py` (create)

**Interfaces — Produces:** method `BacktestEngine.simulate_exit(trade: Trade, bars: pd.DataFrame, entry_idx: int, close_col: str = 'Close') -> Trade` — walks bars after `entry_idx`, per bar calls the EXISTING `_check_exit`, tracks MAE/MFE identically to run(), applies the same eod_close force-close on the last bar, fills `exit_time/exit_price/exit_reason/return_pct` (RAW FRACTION — engine-internal convention, documented) and returns the trade. `run()` is refactored to call it (behavior-identical).

- [ ] **Step 1: Characterization test FIRST** — before refactoring, pin current behavior: build a small synthetic day DataFrame + a Trade, run the CURRENT inline loop logic via `engine.run()` on a df crafted so exactly one signal fires (hard to control) — INSTEAD pin at the unit level: construct the engine, a Trade(entry at bar 3), call the NEW `simulate_exit` and assert target/stop/time-stop/eod outcomes on four crafted bar series (rising to target; falling to stop; flat past time_stop minutes; flat to EOD). Also add an integration guard: run `engine.run()` on a fixture day BEFORE refactor, serialize the resulting trades DataFrame to the test as expected values, then assert equality AFTER refactor (write the test by first printing the pre-refactor output — document this in the test docstring).
- [ ] **Step 2-4: red (method missing) → extract → green + the pinned run() output unchanged.** Existing backtest tests (grep tests/ for backtest) must stay green.
- [ ] **Step 5: commit** `refactor(backtest): extract simulate_exit for reuse by labeled-trade replay (behavior pinned)`

### Task 3.2: `replay_labeled_trades` + POST /api/backtest/replay-trades

**Files:** Modify `lib/backtest.py` (new module-level function), `platform/api/routers/backtest.py` (new endpoint); Test `tests/test_replay_labeled_trades.py` (create)

**Interfaces — Produces:**

```python
def replay_labeled_trades(labeled: list[dict], bars_by_date: dict[str, pd.DataFrame],
                          exit_config: ExitConfig | None = None,
                          ticker: str | None = None) -> dict:
    """Score user-labeled trades against actual bars + benchmark vs the system.
    labeled: [{id, direction CALL|PUT, entry_ts ISO, entry_price, exit_ts ISO|None, exit_price|None}]
    Returns {"trades": [...per-trade scorecards...], "aggregate": {...}} — ALL *_pct
    fields in TRUE PERCENT (journal convention; engine fractions converted here)."""
```

Per-trade scorecard: `{id, status: "ok"|"unavailable", reason?, actual_return_pct (user's, percent), fill_check: "ok"|"price_outside_bar_range", system_signal_at_entry: {direction|None, score}|{"status":"unavailable"}, system_exit: {exit_reason, return_pct (percent), exit_time}, exit_edge_bps: (user_return - system_return)*100}`. Aggregate: `{n, scored_n, win_rate (0-1), avg_return_pct, system_agreement_rate, avg_exit_edge_bps}`. Missing bars for a trade's date → that trade `unavailable` with reason (never zero-filled).
- System signal at entry: reuse `lib.indicators.add_signal_indicators` + `lib.signals.evaluate_signal` on the day's bars at the entry bar (the exact production path `/api/live/signal-series` uses — cite live.py). System exit: build a `Trade` from the labeled entry and call `BacktestEngine.simulate_exit` (Task 3.1), engine configs from `load_config(ticker=...)`.
- Endpoint `POST /api/backtest/replay-trades` body `{ticker, trade_ids: [..] | session_id}` → loads the caller's journal rows via `_journal_owner` scoping (import the owner helper or duplicate the 3-line pattern — prefer importing from `..journal`), loads bars per involved date via main.py's existing `_load_date_data` (follow how /api/market/data builds bars; timeframe 1-min), calls `replay_labeled_trades`, returns the dict. 404 when no trades matched; strict fail-loud on DB errors.

- [ ] **Step 1: pytest first** — fixture bars (40 synthetic 1-min bars), 3 labeled trades: (a) clean win whose user exit beats the system's stop, (b) trade whose entry_price is outside the entry bar's [low,high] → `fill_check:"price_outside_bar_range"`, (c) trade on a date with no bars → unavailable. Assert percent units end-to-end (0.3-style values, not 0.003) and agreement fields present.
- [ ] **Steps 2-5:** red → implement lib fn → wire endpoint (+ TestClient test with monkeypatched bar loader + journal query) → green → commit `feat(backtest): labeled-trade replay with system benchmark` 

### Task 3.3: Charts UI — "Backtest my trades" scorecard

**Files:** Modify `platform/src/routes/ChartsPage.tsx` (+ `useReplayTrades` mutation hook); Test: extend `platform/tests/charts-cards.spec.ts`

- [ ] Playwright-first (mock endpoint → button in side panel Trades tab enabled when ≥1 closed trade → modal renders per-trade rows: your return vs system exit, agreement badge, aggregate footer; unavailable rows render reason). Implement modal (follow an existing modal/overlay pattern in the codebase — grep for a dialog precedent). Gates → commit `feat(charts): backtest-my-trades scorecard`.

**PHASE 3 wrap:** review → PR (capacity: replay endpoint = per-request pandas over ≤ trades×390 bars, no new jobs) → merge → deploy → verify live with a real journal trade → ledger.

---

# PHASE 4 — Style mining → walk-forward → playbook seam (branch `feature/phase4-style-mining`)

### Task 4.1: Schema — `user_style_results` + `playbook_cards_staging`

**Files:** Modify `gcp/schema.sql`; Test `tests/test_schema_style_tables.py` (same pattern as 2.1)

```sql
CREATE TABLE IF NOT EXISTS user_style_results (
    id                  BIGSERIAL PRIMARY KEY,
    user_email          TEXT         NOT NULL,
    ticker              VARCHAR(10)  NOT NULL,
    profile             JSONB        NOT NULL,   -- mined StyleProfile
    trained_on_trades   INTEGER      NOT NULL,
    avg_expectancy_pct  DOUBLE PRECISION,        -- TRUE PERCENT
    avg_win_rate        DOUBLE PRECISION,        -- 0..1 fraction
    stability_score     DOUBLE PRECISION,
    total_folds         INTEGER,
    total_trades        INTEGER,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_user_style_results_user
    ON user_style_results (user_email, ticker, created_at DESC);

-- Staging seam: playbook stays admin-only; candidates land here behind
-- PLAYBOOK_USER_CARDS (hardcoded off) until a future program flips it.
CREATE TABLE IF NOT EXISTS playbook_cards_staging (
    user_email       TEXT             NOT NULL,
    ticker           VARCHAR(10)      NOT NULL,
    name             TEXT             NOT NULL,
    direction        VARCHAR(8)       NOT NULL,
    conditions       JSONB            NOT NULL DEFAULT '[]'::jsonb,
    win_rate         DOUBLE PRECISION,
    avg_return_bps   DOUBLE PRECISION,
    sample_n         INTEGER,
    status           VARCHAR(16)      NOT NULL DEFAULT 'candidate',
    generated_at     TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_playbook_cards_staging PRIMARY KEY (user_email, ticker, name)
);
```

- [ ] Test asserts both CREATE TABLEs + index present → commit `feat(schema): user style results + playbook staging tables`.

### Task 4.2: `lib/style_miner.py`

**Files:** Create `lib/style_miner.py`; Test `tests/test_style_miner.py`

**Interfaces — Produces:**

```python
@dataclass
class StyleProfile:
    direction: str                    # CALL | PUT
    conditions: list[str]             # e.g. ["rsi_25_50", "above_vwap", "consec_up_2plus"]
    support: int                      # entries matching all conditions
    total: int                        # entries of this direction

def snapshot_entry_conditions(bars: pd.DataFrame, entry_idx: int) -> dict:
    """Indicator/state snapshot at one entry bar via the PRODUCTION path
    (lib.indicators.add_signal_indicators — Rule 3.6). Returns the condition
    vocabulary dict: rsi_band, vwap_side, consec_moves, stoch_zone, ..."""

def mine_style(entries: list[dict], bars_by_date: dict[str, pd.DataFrame],
               min_support_frac: float = 0.6) -> list[StyleProfile]:
    """Frequency-threshold mining: per direction, keep conditions true at
    >= min_support_frac of that direction's entries. Deterministic."""
```

Condition vocabulary maps 1:1 onto `SignalConfig`'s tunables so a profile converts to an engine config (Task 4.3): rsi bands (25-50 / 50-75), vwap side, consecutive up/down count >= signal default, stoch K thresholds. Keep the vocabulary SMALL and documented.

- [ ] pytest first: synthetic bars + 5 CALL entries engineered so 4/5 share {rsi_25_50, above_vwap} → profile has exactly those two conditions, support 4, total 5; determinism (same input → same output); <10 closed trades → empty list (honest minimum, mirrors spec §8).
- [ ] Implement → green → commit `feat(lib): style miner derives condition profiles from labeled entries`.

### Task 4.3: Labeled walk-forward + persistence + run endpoint

**Files:** Modify `lib/walk_forward.py` (new method), `platform/api/routers/backtest.py` (or a new small router `platform/api/routers/style.py` — prefer extending backtest.py); Test `tests/test_style_walk_forward.py`

**Interfaces — Produces:**
- `WalkForwardValidator.run_profile(self, df, profile: StyleProfile, close_col='Close') -> WalkForwardResult` — converts the profile to a `SignalConfig` override (map each condition to its tunable; conditions outside the vocabulary raise ValueError) and runs the EXISTING fold loop with engines built from that config. No engine changes needed — the profile becomes configuration, which is exactly how the sweep already parameterizes (`walk_forward_sweep` precedent, walk_forward.py:253-347).
- `POST /api/style/mine-and-validate` body `{ticker}` → loads the caller's closed chart/manual journal trades (≥10 else 200 `{status:"unavailable", reason:"need >= 10 closed trades, have N"}`), snapshots + mines, walk-forwards the top profile over the ticker's daily-bars history (reuse whatever data loader run_backtest.py uses — cite it in code), persists one `user_style_results` row + upserts `playbook_cards_staging` candidates (status 'candidate'), returns `{profile, aggregate_metrics (percent units), stability_score, staged: true}`. This runs SYNCHronously per request over ~months of bars — measure: if wall-clock > ~20s in the test env, cut scope to the last 6 months of data and note it (capacity honesty beats silent timeouts; Cloud Run request timeout is 300s — document actual measured time in the PR).
- [ ] pytest first (profile→SignalConfig mapping incl. unknown-condition ValueError; endpoint contract with monkeypatched loaders; <10-trades honest path; persistence upsert conflict-safe) → implement → commit `feat(style): labeled walk-forward validates mined profiles into the playbook staging seam`.

### Task 4.4: "My style" panel

**Files:** Modify `platform/src/routes/ChartsPage.tsx` Analytics tab; Test: extend charts-cards.spec.ts

- [ ] Playwright-first (mock endpoint: unavailable state shows "need ≥10 closed trades"; ok state renders conditions as chips + win rate/expectancy WITH sample sizes + "Validated across N folds · stability X%"), "Mine my style" button triggers the POST. Implement, gates, commit `feat(charts): my-style panel with walk-forward validated stats`.

**PHASE 4 wrap:** review → PR (schema-before-traffic; capacity: mine-and-validate measured wall-clock documented; no scheduled jobs) → merge → apply schema → deploy → verify → ledger.

---

# PHASE 5 — Replay trainer (branch `feature/phase5-replay-trainer`)

### Task 5.1: CandlestickChart incremental append

**Files:** Modify `platform/src/components/charts/CandlestickChart.tsx`; Test `platform/src/components/charts/candlestickIncremental.test.ts` (pure helper) + existing specs stay green

**Interfaces — Produces:** new optional prop `appendMode?: boolean`. When true, the data effect diffs: if the new `candlestick` array extends the previous one (same leading bars, ≥1 new tail bar — exported pure helper `isAppendExtension(prev, next): boolean`), call `series.update(bar)` per new tail bar and DO NOT call `fitContent()` (zoom preserved); otherwise fall back to full `setData` (+ fitContent only when NOT appendMode). Volume series mirrors.

- [ ] vitest first for `isAppendExtension` (extension true; divergent bar false; shrink false; identical false). Implement with a `prevDataRef`. All existing chart specs (dashboard-chart-fit, charts-cards) must stay green — appendMode defaults false so nothing changes for current callers. Commit `feat(charts): incremental append mode preserving zoom for replay playback`.

### Task 5.2: Replay session mode on /charts

**Files:** Create `platform/src/components/charts/ReplaySessionControls.tsx` + `platform/src/hooks/useReplaySession.ts`; Modify `platform/src/routes/ChartsPage.tsx`; Test `platform/src/hooks/replaySession.test.ts` (reducer/pure logic) + new `platform/tests/replay-trainer.spec.ts`

**Interfaces — Produces:** `useReplaySession(allBars)` → `{active, revealedCount, playing, speed (1|5|20), start(), play(), pause(), step(), stop(), revealedBars}` — a timer (bars-per-second = speed) advancing `revealedCount`; `revealedBars = allBars.slice(0, revealedCount)`. HARD CONSTRAINT (leakage): while active, the chart receives ONLY `revealedBars` (appendMode), signal/indicator overlays are HIDDEN (Sig toggle disabled with title "unavailable during replay"), reference/gamma lines stay (they derive from PRIOR days). Mark Entry works mid-playback: entry epoch = last revealed bar's time. Session id: `crypto.randomUUID()` at start(); trades created during the session POST with `source:'replay', session_id`. stop() → summary state.

- [ ] vitest-first for the reveal reducer (start/step/pause boundaries; never exceeds allBars.length; stop resets). Playwright: mocked market-data day (fixture bars) → Start replay → assert only N bars' worth of markers/chart present after 2 steps (assert via a data-testid revealing `revealedCount`), Mark Entry mid-replay POSTs `source:'replay'` with the last revealed bar's epoch, Sig button disabled. Implement (controls UI beside the timeframe buttons). Commit `feat(charts): bar-replay trainer with leakage-free reveal`.

### Task 5.3: Session scorecard + analytics hygiene

**Files:** Modify `platform/src/routes/ChartsPage.tsx` (+ JournalPage filter); Test: extend replay-trainer.spec.ts + journalStats vitest

**Interfaces:** on stop(), if the session created ≥1 closed trade → POST `/api/backtest/replay-trades` with `{ticker, session_id}` (Phase 3 endpoint already accepts session_id) and show the scorecard modal (reuse Task 3.3's component). Journal/Charts analytics DEFAULT to excluding `source==='replay'` trades with a visible toggle "Include practice sessions" (extend `computeJournalStats` with an options arg `{includeReplay: boolean}` — update its vitest; the exclusion note text mentions practice trades separately).

- [ ] Tests first (stats exclude replay by default + toggle includes; scorecard fires on stop with session_id body) → implement → gates → commit `feat(charts): replay session scorecard; practice trades excluded from stats by default`.

**PHASE 5 wrap:** review → PR (no schema, no new endpoints; capacity: pure client playback) → merge → deploy → verify → ledger. Program complete: update memory (deploy/test gotchas learned), close the loop on issue #701 context (Phase 4 landed the seam), final report to user.

---

## Final program verification (after Phase 5 deploys)

- [ ] Live: create a chart trade on staging, close it, backtest it, mine style (with seeded ≥10 trades if needed), run a replay session end-to-end.
- [ ] `python -m pytest tests/ -k "journal_phase2 or replay_labeled or style or schema_journal or schema_style or backtest_exit" -v` all green on main.
- [ ] All four phase PRs list capacity notes; schema migrations applied before their consuming revisions took traffic.
- [ ] Ledger complete; memory updated; user-facing wrap-up with what shipped per phase.
