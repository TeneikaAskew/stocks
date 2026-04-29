# Plan: Migrate the full test suite to DB-backed data

## Goal

Make every test that currently uses synthetic OHLCV / hand-built level
maps / hand-built signal rows pull from real Cloud SQL data instead.
Tests must remain deterministic when run repeatedly on the same day,
and must run in two modes:

- `pytest --mode=live` — pull from Cloud SQL `market_data_daily`,
  `strat_levels`, `signal_alerts`, `news_sentiment`, etc. As-of date
  defaults to the last business day with data for each ticker.
- `pytest --mode=mock` — read from frozen JSON fixtures under
  `tests/fixtures/`. IWM is the only test ticker for mock mode (per
  user direction); fixtures are snapshots of real Cloud SQL data so
  shape and edge cases match production exactly.

## Status

The infrastructure is in place on branch
`feat/replay-auto-backfill-v2`:
- `tests/conftest.py` exposes `--mode=live|mock`, `db_conn`,
  `market_data`, `market_data_factory`.
- `tests/fixtures/iwm_market_data.json` holds the IWM snapshot
  (266 rows, 2025-03-25 → 2026-04-27, all OHLCV + atr_14 + strat
  fields). Re-snapshot procedure documented below.

What this plan covers: rewriting the existing ~40 test files that
predate this infrastructure to use it.

## Inventory — what needs to change

Run `grep -lE "sample_ohlcv|sample_daily|known_strat_sequence" tests/`
to enumerate. As of writing, the synthetic-fixture consumers are
roughly:

| Test file | Synthetic data used | Migration shape |
|---|---|---|
| `tests/test_indicators.py` | `sample_ohlcv`, `sample_daily` | Replace with `market_data` + add property-style assertions (e.g. RSI ∈ [0,100]) instead of pinned numeric values |
| `tests/test_strat.py` | `known_strat_sequence`, `strat_combo_sequence` | Find real bars in IWM history that exhibit each candle/combo and use those |
| `tests/test_strat_levels.py` | hand-built daily DataFrames | Use `market_data` directly — the existing behavior tests become structural assertions |
| `tests/test_signals.py` | hand-built rows | Pull recent `signal_alerts` rows for IWM |
| `tests/test_premarket_brief.py` | mocked Cloud SQL queries | Replace mocks with real `db_conn` + on-the-fly `build_level_map` calls |
| `tests/test_signal_monitor.py` | hand-crafted level breaks | Drive from persisted `strat_levels` table for IWM at fixed `as_of` |
| `tests/test_backtest.py` | synthetic price series | Use IWM 400d window |
| `tests/test_data_loader.py` | hand-rolled minute data | Pull from `market_data_intraday_iwm` |
| `tests/test_options_*` | mocked option chains | Pull from `etf_options_snapshots` for IWM |
| `tests/test_routers_*` | FastAPI test client + mocks | Wire test client to `db_conn` so the router queries hit the real DB |

Estimated scope: ~25 files, ~600 test functions, 2–3 days of focused
work. The `tests/fixtures/iwm_market_data.json` covers daily; we'll
need 3 more fixture files for full coverage:
- `tests/fixtures/iwm_market_data_intraday.json` — last 5 trading
  days of 1-min bars, ~2000 rows
- `tests/fixtures/iwm_signal_alerts.json` — last 30 days of
  `signal_alerts` for IWM
- `tests/fixtures/iwm_options_snapshot.json` — one full options chain
  for IWM at a fixed date (the snapshot used by the day's brief)

## Migration shape (copy-paste pattern)

For each test that consumes synthetic data:

```python
# BEFORE
def test_compute_X(sample_daily):
    result = compute_X(sample_daily)
    assert result.iloc[-1] == 0.123  # pinned to synthetic seed

# AFTER
def test_compute_X(market_data):
    df, _, _ = market_data
    result = compute_X(df)
    # Property-style assertions — what must hold for ANY real input
    assert result.iloc[-1] >= 0
    assert result.iloc[-1] <= 100
    assert not result.isna().all()
    # If you need a pinned number, derive it from the same df:
    assert result.iloc[-1] == pytest.approx(
        compute_X_reference(df), rel=1e-6)
```

Three rules:
1. **No hardcoded numeric values** in assertions. Either derive the
   expected from the input (`pytest.approx`), or assert structural
   properties (range, monotonicity, non-NaN).
2. **No hardcoded ticker symbols outside of `parametrize` lists**. The
   parametrize list itself is data — pull from a `_WATCHLIST` constant
   or from the `watchlists` table in live mode.
3. **No hardcoded dates**. Use `as_of=None` (last business day) by
   default; if a test must pin a date, pull it from a small
   `tests/fixtures/known_dates.json` so the date is data, not code.

## Fixture-snapshot script

`scripts/snapshot_test_fixtures.py` (TO BE WRITTEN — part of this
migration). One-shot tool that re-pulls all test fixtures from Cloud
SQL into `tests/fixtures/`. Run when:
- The schema changes and existing fixtures go stale.
- A new test ticker is added (right now: IWM only).
- A bug case needs to be captured and pinned (e.g. ASTX 2026-04-28
  for the level-staleness regression).

```bash
# Re-snapshot all fixtures
python -m scripts.snapshot_test_fixtures --ticker IWM

# Force a specific as_of for the fixture (e.g. capture the day a bug
# was observed)
python -m scripts.snapshot_test_fixtures --ticker IWM --as-of 2026-04-28
```

The script writes JSON in the same shape as the existing
`iwm_market_data.json` and updates the `snapshot_taken_at` field.

## Order of migration (smallest blast radius first)

1. **`test_indicators.py`** — pure functions, no DB writes, easy to
   verify with property-style assertions.
2. **`test_strat.py`** — same (pure classification).
3. **`test_strat_levels.py`** — depends on indicators; tests already
   exist for the structural properties from this branch's work.
4. **`test_signals.py`** — uses indicators output.
5. **`test_premarket_brief.py`** — replace the giant mock blocks with
   `db_conn`.
6. **`test_signal_monitor.py`** — needs `strat_levels` snapshot.
7. **`test_routers_*`** — FastAPI tests, last because they need the
   most plumbing.
8. **`test_options_*`** — needs the options fixture.
9. **`test_backtest.py`** — needs price-series fixture.
10. **`test_data_loader.py`** — needs intraday fixture.

Each batch lands as its own PR titled
`test(<area>): migrate to DB-backed data`. Each PR is independently
mergeable — synthetic fixtures and DB-backed fixtures coexist during
the migration.

## Acceptance criteria for "done"

- `make test` runs in both `--mode=live` and `--mode=mock` with all
  assertions passing.
- `tests/conftest.py` exposes `sample_ohlcv` / `sample_daily` /
  `known_strat_sequence` / `strat_combo_sequence` as DEPRECATED with
  a deprecation warning, but they still work for any leftover tests.
- `grep -E "np\.random|pd\.DataFrame\(\{['\"](Open|High|Low)" tests/`
  returns zero matches (no inline synthetic OHLCV).
- `grep -E "assert .* == [0-9]+\.[0-9]+" tests/` returns minimal
  results, all of which are structural (e.g. `assert sum == 100.0`).

## Risks and mitigation

- **CI doesn't have Cloud SQL access** → CI runs `--mode=mock`
  exclusively. Keep IWM fixture committed and small.
- **Fixture drift** when production data is corrected upstream →
  `snapshot_taken_at` field documents staleness; regenerate when
  meaningful drift detected.
- **Test runtime increases** with DB calls → cache `db_conn` at
  session scope; keep fixture loaders at function scope but lazy.
- **Live mode flakiness** if Cloud SQL is briefly unavailable → tests
  use `pytest.skip()` not `xfail`; transient network errors don't
  fail the suite.

## Out of scope (separate plans)

- Tests that hit external APIs (AlphaVantage, FRED, ForexFactory).
  Those should keep their existing recorded-cassette fixtures in
  `tests/cassettes/`.
- `tests/e2e/*.spec.ts` Playwright suite — unrelated stack.
- `tests/test_scripts_*.py` — script integration tests; lighter touch
  needed.

## Pickup instructions for the next branch

1. Branch off `main` after `feat/replay-auto-backfill-v2` lands
   (so the `--mode` flag and IWM fixture are present):
   ```
   git checkout main && git pull
   git checkout -b test/migrate-suite-to-db-backed
   ```
2. Read `tests/conftest.py` to understand the fixture API
   (`db_conn`, `market_data`, `market_data_factory`, `data_mode`).
3. Read `tests/fixtures/iwm_market_data.json` for the JSON shape.
4. Pick the first batch (`test_indicators.py`) and rewrite using the
   shape in "Migration shape" above.
5. Verify with `make test --mode=live` AND `make test --mode=mock`
   before committing. (Note: the Makefile target may need a
   `--mode=$(MODE)` pass-through; add it if missing.)
6. One PR per batch. Keep PRs small.
