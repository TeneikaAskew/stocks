# Journal One-Stop-Shop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Journal page as the complete journaling surface — layout B "Cockpit" (interactive chart + trade rail), Examples (admin trades) by default, full Mark-Entry flow, risk columns, broker CSV import — and strip ALL journal activity from the Charts page.

**Architecture:** The chart-marking machinery moves out of `ChartsPage.tsx` into shared modules consumed by the new Journal page; Charts keeps research features only. Two backend additions: an examples endpoint (admin's journal rows) and a broker-import pipeline (parse → pair → preview → commit) whose pairing math lives in `lib/` (one-source-of-truth). Everything renders from server data; no financial math in TS.

**Tech Stack:** FastAPI + pandas (`platform/api/routers/journal.py`, `lib/broker_import.py`), React/TS (`platform/src`), pytest, Playwright.

**Spec:** docs/superpowers/specs/2026-07-11-journal-one-stop-shop-design.md (binding). Mockup: https://claude.ai/code/artifact/b57f184d-15e2-4ca3-89d1-3cf78e4793af

## Global Constraints

- Branch: `feature/journal-one-stop` off current `main` (includes #713 + #715). Never commit to main; conventional commits; NO Claude branding / Co-Authored-By; stage by explicit path only; never stage `docs/alphavantage/`, `model_analysis.txt`, or `platform/playwright.config.ts`.
- Layout B exactly (spec §Approved layout): chart left, **trade rail right (~340px)**; rail card top row = direction (+ `EX` badge in Examples) left, **return % centered & prominent** (largest text on card, bull/bear color), time right; line 2 `Entry $X → Exit $Y`; line 3 `TP a / b · SL c · R:R n:1`.
- Examples = `journal_entries WHERE user_email = <server-side ADMIN_EMAIL> AND source != 'replay'`; read-only; default view when user's own journal for the ticker is empty; marking always writes to My journal and flips the view.
- Charts page: ZERO journal activity after this program (no Mark Entry, no trades panel, no Backtest-my-trades, no seed layer). KEEP: conditions card, similar setups, Sig overlay, replay trainer, date/review controls.
- Rule 3.7: no fabricated values anywhere — unpaired imports become `status='active'` with null exit; skipped rows always carry a reason; renders use "—".
- Unit conventions: `return_pct` is TRUE PERCENT; breakeven (0.0) counts as loss; journal timestamps are naive-ET wall clock (TIMESTAMPTZ round-trip pinned by tests/integration/test_journal_timestamptz_roundtrip.py).
- Import v1: options trades only; native parsers = Robinhood + Webull (header auto-detect); generic column-mapper for everything else; idempotent re-import (dedupe key: ticker + entry_ts + entry_price + direction); imported rows get `source='import:<broker>'`.
- R:R display math (`|entry−TP1| / |entry−stop|`) is display-layer arithmetic on two server values — computed in ONE exported TS helper with unit tests, rendered as `n:1` with 1 decimal, "—" when either input is null.
- Playwright local recipe: vite `--port 4321 --strictPort`; patch `playwright.config.ts` baseURL 5173→4321 temporarily; REVERT + kill vite before committing.
- Existing suites must stay green at every task boundary: `charts-cards`, `replay-trainer`, `journal`, `ticker-combobox` (updated where the task's scope explicitly changes behavior, never weakened to pass).

---

### Task 1: Examples endpoint

**Files:**
- Modify: `platform/api/routers/journal.py` (new GET; reuse `_rows_to_trades` + the trades-GET SQL shape at lines ~228-244)
- Test: `tests/test_journal_examples.py` (model scaffold on `tests/test_journal_phase2.py`)

**Interfaces:**
- Produces: `GET /api/journal/examples/{ticker}` → same JSON shape as `GET /api/journal/trades/{ticker}` (`{ticker, source, count, trades:[...]}`), rows scoped `user_email = ADMIN_EMAIL AND ticker = :t AND source IS DISTINCT FROM 'replay'`, ordered like the trades GET. ADMIN_EMAIL from the same config the admin gate uses (`api/config.py` / `api/auth.py` — read them; never from the client). DB unavailable → the same explicit-unavailable envelope the trades GET uses (read its except path; do NOT invent a new one, and do NOT return fabricated empty-success).

- [ ] Write failing tests: (a) returns admin rows for ticker, same field set as trades GET (assert key-set equality against a trades-GET response in the same test app); (b) excludes `source='replay'` rows; (c) another user's rows never appear; (d) requires auth exactly like the trades GET (compare status codes with/without the test auth header); (e) unknown ticker → empty trades, count 0.
- [ ] Run: `python -m pytest tests/test_journal_examples.py -q` → FAIL (404 route missing).
- [ ] Implement (reuse `_rows_to_trades`; one SQL query; no per-row queries).
- [ ] Run new tests + `tests/test_journal_phase2.py` → all green.
- [ ] Commit: `feat(api): journal examples endpoint — admin seed trades read-only`

---

### Task 2: Broker-import core in `lib/broker_import.py`

**Files:**
- Create: `lib/broker_import.py`
- Create: `tests/test_broker_import.py` + fixtures `tests/fixtures/broker_csv/robinhood_sample.csv`, `webull_sample.csv`
- Test command: `python -m pytest tests/test_broker_import.py -q`

**Interfaces (Produces — Task 3 and 6 depend on these exact names):**
```python
@dataclass
class NormalizedOrder:      # one option fill
    ticker: str             # underlying, e.g. "IWM"
    direction: str          # "CALL" | "PUT"
    action: str             # "open" | "close"  (BTO/STO->open? NO: v1 long-options only — BTO=open, STC=close; STO/BTC rows -> skipped "short options not supported")
    ts: str                 # naive-ET "YYYY-MM-DD HH:MM"
    price: float            # per-contract premium
    quantity: int
    raw_index: int          # source row for error messages

@dataclass
class PairedTrade:
    ticker: str; direction: str
    entry_ts: str; entry_price: float
    exit_ts: str | None; exit_price: float | None
    return_pct: float | None      # TRUE PERCENT: (exit-entry)/entry*100, None when open
    quantity: int
    status: str                   # "closed" | "active"

@dataclass
class ImportPreview:
    trades: list[PairedTrade]
    skipped: list[dict]           # {raw_index, reason} — EVERY dropped row appears here
    broker: str                   # "robinhood" | "webull" | "generic"

def detect_broker(header_line: str) -> str | None      # exact-header-set match
def parse_csv(text: str, broker: str, mapping: dict | None = None) -> list[NormalizedOrder]
def pair_orders(orders: list[NormalizedOrder]) -> ImportPreview   # FIFO per (ticker, direction, contract)
```
- Robinhood detection: header contains `Activity Date` + `Trans Code` + `Instrument`; option rows have `Trans Code` in {BTO, STC, STO, BTC} and a `Description` like `IWM 7/11/2026 Call $224.00`; parse underlying/type/strike/expiry from Description; timestamps from `Activity Date` (date-only → normalize to `09:30` with a skipped-note? NO — date-only rows keep `00:00` time and a per-row note in `skipped`? Neither: keep time `09:30` is fabrication. Resolution: Robinhood activity CSV has no fill time → `ts = "<date> 00:00"` and PairedTrade carries the real date with midnight time; document in module docstring; the journal already renders time and this shows `00:00` honestly).
- Webull detection: header contains `Symbol` + `Side` + `Avg Price` + `Filled Time`; options symbol like `IWM250711C00224000` (OCC) — parse via regex `^([A-Z.]+)(\d{6})([CP])(\d{8})$`; `Filled Time` is exchange (ET) local → naive-ET direct.
- Generic: caller supplies `mapping` dict `{ticker, direction, action, ts, price, quantity}` → column names; unmapped/missing → per-row skip with reason.
- Pairing: FIFO queue per contract key; close without open → skipped `"close without matching open"`; open without close → `status='active'`; equity rows (no option parse) → skipped `"shares — options only in v1"`.

- [ ] Write the fixtures (≥6 rows each: two round trips, one open lot, one equity row, one short-option row for RH) and failing tests: detection both brokers + None for random header; RH description parsing; Webull OCC parsing; FIFO pairing with partial closes (2 lots opened, 1 closed → 1 closed + 1 active); return_pct percent-units (entry 1.42 exit 1.71 → +20.42); every skip reason present; idempotence helper-free (pairing is pure — dedupe happens at commit in Task 3).
- [ ] Run → FAIL (module missing). Implement. Run → green.
- [ ] Commit: `feat(lib): broker CSV import core — parse, detect, FIFO round-trip pairing`

---

### Task 3: Import endpoints (preview + commit)

**Files:**
- Modify: `platform/api/routers/journal.py`
- Test: `tests/test_journal_import_endpoints.py`

**Interfaces (Produces):**
- `POST /api/journal/import/preview` — multipart file + optional `broker`/`mapping` JSON field → `{broker, trades:[PairedTrade-shaped dicts + duplicate: bool], skipped:[{raw_index, reason}]}`. Duplicate = existing journal row for THIS user matching (ticker, entry_ts, entry_price, direction).
- `POST /api/journal/import/commit` — `{trades: [selected PairedTrade dicts]}` → inserts rows (`source='import:<broker>'`, owner = current user) via the same insert path/validation as the existing POST; re-checks duplicates server-side (idempotent); returns `{imported, skipped_duplicates}`.
- Commit NEVER writes to Examples (owner is always the caller).

- [ ] Failing tests: preview parses fixture upload end-to-end (real router, TestClient multipart); duplicate flagged when a matching row pre-exists; commit inserts + second identical commit → `imported=0, skipped_duplicates=N`; active trades commit with null exit (and the GET returns them as active); auth required.
- [ ] Implement (reuse Task 2 lib; one INSERT per selected trade is acceptable at import scale ≤ a few hundred rows — bound with an explicit 5,000-row cap → 413).
- [ ] Run new tests + `tests/test_journal_phase2.py` + `tests/test_journal_examples.py` → green.
- [ ] Commit: `feat(api): broker import preview/commit endpoints — idempotent, options-only`

---

### Task 4: Extract the marking chart into shared modules

**Files:**
- Create: `platform/src/components/journal/TradeMarkingChart.tsx` (chart + drawing state machine + markers/price-lines) and `platform/src/components/journal/TradeRailCard.tsx`
- Create: `platform/src/hooks/useTradeMarking.ts` (the `DrawingStep` state machine extracted verbatim from `ChartsPage.tsx:78, ~600-700`)
- Modify: `platform/src/routes/ChartsPage.tsx` (consume the extracted modules — behavior identical this task; removal happens in Task 6)
- Test: existing `platform/tests/charts-cards.spec.ts` + `replay-trainer.spec.ts` must pass UNCHANGED (this is a pure refactor gate); vitest unit for `riskReward(entry, tp1, stop)` helper in `platform/src/lib/risk.ts` (create: returns number|null; null when any input null or stop==entry).

**Interfaces (Produces):**
- `<TradeMarkingChart bars volume trades onTradeCreated onTradeExited markersStyle="own"|"examples" ... />` — accepts journal-shaped trades, draws entry/exit markers + TP/SL lines, owns the Mark-Entry→CALL/PUT→TP1-3→SL→exit flow, calls back with the same payload ChartsPage currently POSTs.
- `<TradeRailCard trade example onExit onDelete onHover />` — layout per Global Constraints (return % centered/prominent).
- `riskReward(entry: number|null, tp1: number|null, stop: number|null): number|null`

- [ ] Extraction refactor with ChartsPage consuming the new modules; zero behavior change.
- [ ] Run FULL `charts-cards.spec.ts` (26 tests) + `replay-trainer.spec.ts` + `npx tsc --noEmit` → all green, no assertion edits.
- [ ] vitest: risk.ts cases (2.0:1 exact; null inputs; stop==entry → null).
- [ ] Commit: `refactor(charts): extract trade-marking chart, rail card, and risk helper into shared modules`

---

### Task 5: Journal page assembly (layout B)

**Files:**
- Modify: `platform/src/routes/JournalPage.tsx` (major rebuild), `platform/src/hooks/useJournalChartTrades.ts` (add examples fetch + view state)
- Test: `platform/tests/journal-onestop.spec.ts` (new; mocks per `tests/helpers/mocks.ts` conventions)

Layout (top→bottom, per spec + mockup — final user-refined version): header row (title, TickerCombobox, date picker using `/api/market/dates/{ticker}` with a clearable "Overview" state, `Mark Entry`, `Add Trade`, CSV/export buttons, `[Examples | My journal]` segmented toggle right-aligned); `row: TradeMarkingChart (flex-1, height clamp like Charts) + rail (w-[340px]: per-date TradeRailCards, then the EQUITY CURVE card — cumulative all-dates, placeholder preserved)`; scope label ("Overview — all dates" / "Session — MM/DD/YYYY") + **7 KPI tiles** (Trades, Win rate, Total P&L, Avg/trade, Avg win, **Avg R:R**, **TP1 hit**) + practice toggle + notes — tiles and the table scope to the selected date, Overview when none; full-width trade table + NEW columns Stop / TPs / R:R (riskReward helper; "—" honesty) + existing actions (disabled with tooltip in Examples view). TP1-hit = closed trades with TP1 set whose exit reached TP1, "—" when none qualify. No session-stats card (folded into KPIs).

View logic: `view = userOverride ?? (myTrades.length === 0 ? 'examples' : 'mine')`; examples data from `GET /api/journal/examples/{ticker}`; marking callbacks always POST to own journal then set view to 'mine'; Examples cards show `EX` badge, muted marker style, no exit/delete.

- [ ] Failing e2e first: examples default when own journal empty (tiles/curve/table populated from examples mock, `EX` badges visible); toggle to My journal shows own empty state without hiding the chart; Mark-Entry flow on the JOURNAL page POSTs `source:'chart'` and flips view (reuse the mark-entry interaction recipe from charts-cards.spec.ts:267-329 — RTH toggle, canvas clicks, ESC skips); risk columns render values and "—"; rail card shows centered return %.
- [ ] Implement; `npx tsc --noEmit` clean; new spec green; existing `journal.spec.ts` updated where the page structurally changed (equity/table tests stay, empty-state tests re-anchored) — no assertion weakened without a structural reason stated in the report.
- [ ] Commit: `feat(journal): one-stop cockpit — interactive chart, trade rail, examples default, risk columns`

---

### Task 6: Charts page strip-down

**Files:**
- Modify: `platform/src/routes/ChartsPage.tsx` — REMOVE: Mark Entry button/flow usage, Trades/Analytics side panel, TradeCard list, Backtest-my-trades, JSON/CSV trade export, journal-trades fetch, seed markers + Playbook-seed panel, scorecard footer tied to trade replay. KEEP: chart (full width now), toolbar research toggles, conditions card, similar setups, Sig overlay, replay trainer + its session controls/scorecard.
- Test: `platform/tests/charts-cards.spec.ts` (persistence/mark-entry/backtest describes REMOVED, research describes kept + new negative assertions: `Mark Entry` absent, `Trades (` absent), `replay-trainer.spec.ts` (must stay green — trainer kept).

- [ ] Update specs first (delete removed-feature tests, add the two negative assertions) → run → FAIL (UI still present).
- [ ] Strip the page; chart area takes the freed width; `npx tsc --noEmit` clean (remove now-unused imports/hooks — the extracted modules remain, consumed by Journal).
- [ ] Run charts-cards + replay-trainer + journal-onestop → green.
- [ ] Commit: `feat(charts): research-only — journal activity moved to the Journal page`

---

### Task 7: Import UI (button + 3-step modal)

**Files:**
- Create: `platform/src/components/journal/ImportTradesModal.tsx`
- Modify: `platform/src/routes/JournalPage.tsx` (Import button in trades section)
- Test: `platform/tests/journal-import.spec.ts` + fixture `platform/tests/fixtures/robinhood_sample.csv` (copy of the Task-2 fixture)

Steps in modal: (1) broker chips (Robinhood, Webull auto; Schwab/Fidelity/IBKR/Other → column-mapper with prefilled presets) + file drop; (2) preview table from `POST /api/journal/import/preview` — checkbox per row, duplicates pre-unchecked + labeled, skipped list with reasons, active-import rows amber-labeled; (3) result (`Imported N · M duplicates skipped`) and journal refetch.

- [ ] Failing e2e: upload fixture (Playwright `setInputFiles`, preview endpoint mocked with a realistic payload) → preview rows render with duplicate/active labels → commit (mocked) → success copy + refetch called (journal GET mock hit again).
- [ ] Implement; tsc clean; spec green.
- [ ] Commit: `feat(journal): broker CSV import UI — preview, duplicates, honest skip reasons`

---

### Task 8: Whole-feature verification + rollout

- [ ] Full gates: `python -m pytest tests/test_journal_examples.py tests/test_broker_import.py tests/test_journal_import_endpoints.py tests/test_journal_phase2.py -q`; `cd platform && npx tsc --noEmit && npx vitest run`; Playwright: journal-onestop, journal-import, journal, charts-cards, replay-trainer, ticker-combobox.
- [ ] Eyes-on screenshots of the assembled Journal (Examples view populated, rail cards, import preview) — compare against the approved mockup, send to user.
- [ ] PR with capacity note (examples GET = one indexed SELECT/page-load; import = user-initiated, ≤5,000-row cap; no schedulers) → CI → merge on green (standard squash).
- [ ] Deploy staging → user acceptance on the live page → prod deploy (0% traffic) → promote BY REVISION NAME after user OK.
- [ ] Close the loop: update spec status; note the two parked items (prod promotion of #715 if still parked; replay-trainer placement decision confirmed).

---

## Self-Review

- **Spec coverage:** layout B + rail card w/ centered % (T4/T5), examples default + read-only (T1/T5), marking on Journal (T4/T5), risk columns/snapshot (T4/T5), never-bare page (T5 e2e), Charts zero-journal (T6), import RH/Webull native + generic mapper, options-only, idempotent, honest skips (T2/T3/T7), deploy+acceptance (T8). No gaps found.
- **Placeholder scan:** none — every task carries exact interfaces, test cases, and commit messages; moved-code tasks name exact source locations.
- **Type consistency:** `PairedTrade` shape = preview/commit payloads = journal row fields; `riskReward` consumed in T5 as defined in T4; `TradeMarkingChart` props defined in T4 and consumed in T5 only.
- **Risks:** T4 is the pivot (refactor under an unchanged test suite) — its gate is "existing specs pass with zero assertion edits"; T5 is the largest UI task and owns the only intentional journal.spec.ts changes; Robinhood date-only timestamps documented as `00:00` (honest, not fabricated).
