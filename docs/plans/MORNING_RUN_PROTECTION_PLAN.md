# Plan: Morning-run protection + history tables + idempotent /replay

## Problem

Today's `premarket_analysis` and `insight_reports` tables UPSERT on
`(analysis_date, ticker)` and `(ticker, as_of)`. Any re-run on the
same day destructively overwrites the canonical morning row. Today
(4/29 EDT) we observed five different timing situations across five
tickers:

| Ticker | brief written at | reason |
|---|---|---|
| QQQ | 08:30 EDT today ✓ | scheduled 8:30 intact |
| SPY | 08:30 EDT today ✓ | scheduled 8:30 intact |
| ASTX | 12:51 EDT | manual lunchtime re-run overwrote |
| AVGO | 14:35 EDT | manual afternoon re-run overwrote |
| IWM | 4/28 21:56 EDT | replay/test from night before |

There is no way to query "what did the 8:30 brief actually send for
AVGO?" once it has been overwritten. `/replay TICKER DATE` from
Discord *also* destructively re-writes the historical row, so every
replay corrupts the historical record further.

## Goal

After this PR:
- The canonical morning run is protected by default; only an explicit
  `--update` flag overwrites it.
- Every run (scheduled, manual, replay, retry) appends an immutable
  row to a history table.
- `/replay` returns cached data instantly by default; `refresh:true`
  re-runs and overwrites.
- All existing readers (Discord push, dashboard, validators, API)
  keep working without changes.

## Out of scope

- Refactoring `insight_runs` (already-existing audit table). This
  plan adds `insight_reports_history` alongside it; the `insight_runs`
  schema gap (no row when validation fails before INSERT) is a
  separate fix.
- Migrating the `dashboard.py` or `insights.py` API routers to expose
  history. They keep reading current. New endpoints can be added
  later if needed.
- Cleaning up the throwaway audit scripts in `scripts/_audit_*.py`.

## Schema

Two new tables, additive only. No changes to existing tables.

```sql
-- gcp/schema.sql additions

-- Brief audit / history. INSERT-only. One row per actual brief run
-- attempt. Columns mirror premarket_analysis except `id` is a
-- BIGSERIAL of its own (not a copy of premarket_analysis.id) and
-- `written_at` / `run_kind` / `triggered_by` are added.
CREATE TABLE IF NOT EXISTS premarket_analysis_history (
    id              BIGSERIAL PRIMARY KEY,
    analysis_date   DATE NOT NULL,
    ticker          VARCHAR(10) NOT NULL,
    -- Identical to the columns persisted in premarket_analysis.
    -- Keep the column list synced when premarket_analysis evolves.
    price           DOUBLE PRECISION,
    rsi             DOUBLE PRECISION,
    rsi_direction   VARCHAR(10),
    consecutive_up  INTEGER,
    consecutive_down INTEGER,
    signal_status   VARCHAR(40),
    strat_candle    VARCHAR(10),
    strat_combo     VARCHAR(30),
    strat_setup     BOOLEAN,
    ftfc_score      DOUBLE PRECISION,
    ftfc_direction  VARCHAR(10),
    ftfc_labels     JSONB,
    prev_day_high   DOUBLE PRECISION,
    prev_day_low    DOUBLE PRECISION,
    change_pct      DOUBLE PRECISION,
    rvol            DOUBLE PRECISION,
    sma200          DOUBLE PRECISION,
    bb_upper        DOUBLE PRECISION,
    bb_lower        DOUBLE PRECISION,
    ema9            DOUBLE PRECISION,
    ema20           DOUBLE PRECISION,
    atr14           DOUBLE PRECISION,
    volatility_20d  DOUBLE PRECISION,
    macd_cross      VARCHAR(10),
    vol_regime      VARCHAR(10),
    above_sma200    BOOLEAN,
    stoch_rsi_k     DOUBLE PRECISION,
    stoch_rsi_d     DOUBLE PRECISION,
    recommended_orb_window VARCHAR(10),
    recommended_orb_reason TEXT,
    playbook        TEXT,
    -- Audit metadata
    written_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    run_kind        VARCHAR(20) NOT NULL,
        -- 'scheduled' | 'manual_replay' | 'manual_update' | 'backfill'
    triggered_by    VARCHAR(64),
        -- 'cloud-scheduler' | 'discord:replay:<user_id>' | 'cli:<user>'
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_pmah_date_ticker_written
    ON premarket_analysis_history (analysis_date, ticker, written_at DESC);
CREATE INDEX IF NOT EXISTS idx_pmah_run_kind
    ON premarket_analysis_history (run_kind, written_at DESC);


-- Pipeline audit / history. INSERT-only. The existing insight_runs
-- table captures (id, ticker, status, trigger, started_at, ...) but
-- its report_id points to insight_reports.id which is UPSERTed in
-- place. This table snapshots the actual report payload per run.
CREATE TABLE IF NOT EXISTS insight_reports_history (
    id              BIGSERIAL PRIMARY KEY,
    insight_run_id  UUID REFERENCES insight_runs(id) ON DELETE SET NULL,
        -- Optional FK; survives deletion of the insight_runs row.
    ticker          VARCHAR(10) NOT NULL,
    as_of           TIMESTAMPTZ NOT NULL,
    report          JSONB NOT NULL,        -- frozen snapshot
    model_versions  JSONB,
    cost_usd        DOUBLE PRECISION,
    latency_ms      INTEGER,
    -- Audit metadata
    written_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    run_kind        VARCHAR(20) NOT NULL,
    triggered_by    VARCHAR(64),
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_irh_ticker_as_of_written
    ON insight_reports_history (ticker, as_of, written_at DESC);
CREATE INDEX IF NOT EXISTS idx_irh_run_kind
    ON insight_reports_history (run_kind, written_at DESC);
```

### `run_kind` enum (string, no DB constraint — easier to extend)

| Value | Meaning |
|---|---|
| `scheduled` | Cloud Scheduler fired the canonical morning slot |
| `manual_update` | Manual run with `--update` (current row overwritten) |
| `manual_replay` | Manual run without `--update` (history only, current skipped) |
| `replay_refresh` | `/replay` with `refresh:true` (overwrite + push to Discord) |
| `replay_cached` | `/replay` returned cached data (no DB write — but logged here for completeness as a no-op marker? See "Open question 1" below) |
| `backfill` | One-shot migration script populating history from existing rows |
| `auto_refresh` | Triggered by `auto_refresh_top_n.py` |

### `triggered_by` examples

- `cloud-scheduler:premarket-brief-daily`
- `discord:replay:user_id_123456789`
- `cli:teneika@bictech.org`
- `cron:auto-refresh-top-n`

## Code changes

### 1. `gcp/database.py` — add helper

```python
def row_exists(table: str, where: dict) -> bool:
    """Return True if at least one row matches the where-dict."""
    if not is_cloud_sql_configured():
        return False
    cols = ' AND '.join(f"{k} = :{k}" for k in where)
    sql = f"SELECT 1 FROM {table} WHERE {cols} LIMIT 1"
    df = query_to_dataframe(sql, where)
    return not df.empty
```

### 2. `gcp/premarket_brief.py` — `--update` flag + history write

```python
# CLI arg
parser.add_argument(
    '--update', action='store_true',
    help='Allow overwriting today\'s canonical premarket_analysis '
         'row. Without this flag, re-runs only write to history.',
)

# Resolve allow_update from env (Cloud Run job invocation) or arg
allow_update = (
    args.update
    or os.environ.get('BRIEF_UPDATE') == 'true'
    or os.environ.get('BRIEF_AS_OF') is not None  # replay implies update
)

# In persist_to_cloud_sql:
def persist_to_cloud_sql(brief, allow_update=False, run_kind='scheduled',
                        triggered_by=None):
    ...
    rows = [...]  # same row-building as today

    # Always write to history first (append-only, never skipped)
    history_rows = [
        {**row, 'written_at': now, 'run_kind': run_kind,
         'triggered_by': triggered_by, 'notes': notes}
        for row in rows
    ]
    insert_dataframe(history_df, 'premarket_analysis_history')

    # Conditional write to current
    if allow_update:
        # Old behavior: UPSERT every row
        upsert_dataframe(df, 'premarket_analysis', ['analysis_date', 'ticker'])
    else:
        # New behavior: per-ticker INSERT-if-missing, skip-if-exists
        for row in rows:
            sql = """
                INSERT INTO premarket_analysis (...) VALUES (...)
                ON CONFLICT (analysis_date, ticker) DO NOTHING
            """
            execute(sql, row)
            # Log a warning if no row was written (means it existed)
```

### 3. `gcp/insight_pipeline_job.py` — same pattern

```python
parser.add_argument('--update', action='store_true', ...)

allow_update = (
    args.update
    or os.environ.get('INSIGHT_UPDATE') == 'true'
    or os.environ.get('INSIGHT_AS_OF') is not None  # replay implies update
)

# After computing the report dict:
# 1. Always insert into insight_reports_history
# 2. Conditionally INSERT/UPSERT insight_reports
```

### 4. `gcp/premarket_brief.py` — new `render_existing` entry point

```python
def render_existing_brief(ticker: str, analysis_date: date) -> bool:
    """Pull the existing premarket_analysis row, render it as a
    Discord embed, and post via DISCORD_WEBHOOK_URL.

    Returns True on success. Returns False if no row exists.
    Used by /replay for instant cache hits.
    """
    row = fetch_premarket_analysis(ticker, analysis_date)
    if row is None:
        return False
    embeds = build_brief_embeds_from_row(row)
    post_to_discord(embeds)
    return True
```

CLI invocation: `python -m gcp.premarket_brief --post-existing TICKER DATE`.

### 5. `gcp/insight_discord_push.py` — new `push_one` entry point

```python
def push_one(ticker: str, as_of: datetime) -> bool:
    """Pull the existing insight_reports row for (ticker, as_of),
    render via format_report_embed, post via webhook.

    Returns True on success. Returns False if no row exists.
    """
    row = fetch_insight_report(ticker, as_of)
    if row is None:
        return False
    embed = format_report_embed(row)
    post_to_discord({'embeds': [embed]})
    return True
```

CLI invocation:
`python -m gcp.insight_discord_push --push-one TICKER AS_OF`.

### 6. `gcp/discord_interactions/main.py` — `/replay` restructure

```python
def handle_replay(ticker, date_arg, refresh: bool, ...):
    d = parse_date_arg(date_arg)
    ticker_u = ticker.upper().strip()

    if not refresh:
        # Try cache hit first
        brief_present = row_exists('premarket_analysis',
                                   {'analysis_date': d, 'ticker': ticker_u})
        canonical_as_of = datetime(d.year, d.month, d.day, 13, 15,
                                   tzinfo=timezone.utc)
        insight_present = row_exists('insight_reports',
                                     {'ticker': ticker_u,
                                      'as_of': canonical_as_of})
        if brief_present and insight_present:
            # Cache hit — render existing rows in-process
            render_existing_brief(ticker_u, d)
            push_one(ticker_u, canonical_as_of)
            return f"✅ Replayed cached data for **{ticker_u}** {d.isoformat()}"

    # Cache miss OR explicit refresh — dispatch the jobs (existing
    # path, but pass --update so the row gets written/overwritten).
    if not ticker_has_daily_data(ticker_u):
        # Auto-backfill (existing logic)
        ...

    brief_ok = execute_cloud_run_job("premarket-brief", {
        "BRIEF_AS_OF": d.isoformat(),
        "BRIEF_TICKERS": ticker_u,
        "BRIEF_UPDATE": "true",                  # NEW
        "BRIEF_TRIGGERED_BY": f"discord:replay:{user_id}",  # NEW
    })
    insight_ok = execute_cloud_run_job("insight-pipeline", {
        "INSIGHT_AS_OF": insight_as_of_iso,
        "INSIGHT_TICKERS": ticker_u,
        "INSIGHT_UPDATE": "true",                # NEW
        "INSIGHT_TRIGGERED_BY": f"discord:replay:{user_id}",  # NEW
    })

    return f"✅ Replay queued for {ticker_u} (refresh) — brief and insight will post when complete (~90s)."
```

### 7. `/replay` slash-command schema update

In the registration command (likely `scripts/register_discord_commands.py`):

```python
{
    "name": "replay",
    "description": "Replay the brief + insight for a ticker on a date",
    "options": [
        {"name": "ticker", "type": 3, "required": True, ...},
        {"name": "date", "type": 3, "required": True, ...},
        {
            "name": "refresh",
            "type": 5,  # boolean
            "description": "Re-run with latest code instead of returning cached data",
            "required": False,
        },
    ],
}
```

### 8. Cloud Scheduler arg passing (no scheduler config change)

The scheduled brief/pipeline jobs already pass `BRIEF_AS_OF`/`INSIGHT_AS_OF`
empty (the canonical morning run uses today's date). They'll naturally
land in the "INSERT-if-missing" path on first run, which is correct.

If a Cloud Scheduler retry fires (because the first attempt failed
mid-run), the per-ticker check ensures only missing tickers are
inserted, never overwriting already-written ones. ✅

To make the audit cleaner, set `BRIEF_TRIGGERED_BY=cloud-scheduler:premarket-brief-daily`
in the scheduler env vars.

## Backfill — populate history from existing data

`scripts/backfill_history_tables.py` (one-shot, idempotent, dry-run mode):

```python
"""
One-shot: populate premarket_analysis_history and insight_reports_history
from the existing current tables.

Idempotent — uses ON CONFLICT DO NOTHING on a unique constraint over
(analysis_date, ticker, written_at) for the brief and (ticker, as_of,
written_at) for the pipeline.

Run via: python -m scripts.backfill_history_tables [--dry-run]
"""
```

For each row:
- `premarket_analysis_history.written_at = premarket_analysis.analysis_ts`
  (the original write time — preserves IWM-style "row written night
   before" anomalies as factual history)
- `insight_reports_history.written_at = insight_reports.created_at`
- `run_kind = 'backfill'` for all backfilled rows
- `triggered_by = 'backfill-script'`

Estimated rows: ~250 days × 6-25 tickers ≈ 1500-6000 rows total.
Runtime: <1 second.

## Tests

### `tests/test_premarket_brief_history.py` (new)

1. **First run inserts both current and history**
   - Run brief for SPY with no row in either table
   - Assert `premarket_analysis` has 1 row, `premarket_analysis_history` has 1 row
   - Both rows have matching content
2. **Re-run without `--update` skips current, writes history**
   - Brief once → 1 in current, 1 in history
   - Brief again → 1 in current (timestamp UNCHANGED), 2 in history
3. **Re-run with `--update` UPSERTs current and writes history**
   - Brief once → 1, 1
   - Brief with `--update` → 1 in current (timestamp UPDATED), 2 in history
4. **Replay (BRIEF_AS_OF set) implies `--update`**
   - Existing row for 2026-04-15
   - Run with `BRIEF_AS_OF=2026-04-15` (no `--update` arg)
   - Asserts current row was overwritten + 2 history rows
5. **Per-ticker conditional UPSERT (Cloud Scheduler retry simulation)**
   - First brief: SPY succeeds, QQQ kill-switched
   - Re-run brief for [SPY, QQQ]: SPY skipped, QQQ inserted
   - Assert SPY's `analysis_ts` is unchanged from first run
6. **Backfill is idempotent**
   - Run backfill twice — second run inserts 0 new rows

### `tests/test_insight_pipeline_history.py` (new)

Mirrors the brief tests for `insight_reports` + `insight_reports_history`.
Plus:
- **`insight_runs.report_id` correctness after history table exists**
  - Run pipeline → `insight_runs` row points to `insight_reports.id`
  - Re-run with `--update` → `insight_runs` row 2 created, points to
    same `insight_reports.id` (UPSERT). `insight_reports_history`
    has 2 rows, both reachable via `insight_run_id`.

### `tests/test_replay_command.py` (new or extend existing)

1. **`/replay` cache hit posts existing rows without job dispatch**
   - Pre-populate brief + insight rows for AAPL 2026-04-15
   - `/replay AAPL 2026-04-15` (refresh=False)
   - Assert `execute_cloud_run_job` was NOT called
   - Assert Discord webhook received 2 posts (brief + insight)
2. **`/replay refresh:true` dispatches jobs with `--update` env vars**
   - Pre-populate rows
   - `/replay AAPL 2026-04-15 refresh:true`
   - Assert `execute_cloud_run_job("premarket-brief", env)` was called
     with `BRIEF_UPDATE=true`
3. **`/replay` cache miss falls back to dispatch**
   - No rows for ZZZZ
   - `/replay ZZZZ 2026-04-15`
   - Assert auto-backfill was triggered, then jobs dispatched

All new tests use the `pytest --mode=live|mock` infrastructure already
in place. Live mode hits Cloud SQL; mock mode uses the IWM JSON
fixture (and we'll add an ASTX fixture for the staleness corner).

## Rollout plan

### Phase 1 — schema + backfill (additive, no risk to existing flows)

1. Apply the schema migration to live Cloud SQL (idempotent).
2. Run `scripts/backfill_history_tables.py --dry-run` to validate.
3. Run for real. History tables now mirror current tables.

After Phase 1, history is being captured from this point forward
(once code lands), and existing reads/writes are unchanged.

### Phase 2 — code changes (require Cloud Run image rebuild)

4. Land `--update` flag + history write paths in brief and pipeline.
5. Land `render_existing_brief` and `push_one` entry points.
6. Restructure `/replay` to check cache first.
7. Update `/replay` slash command schema.

Deploy via standard pattern:
```bash
"$GCLOUD" builds submit --tag <image>
for job in premarket-brief insight-pipeline insight-discord-push; do
  "$GCLOUD" run jobs update "$job" --image=<image> --region=us-east1
done
```

### Phase 3 — verify (no traffic change)

8. Wait for tomorrow's scheduled 8:30 / 8:45 runs to fire.
9. Query `premarket_analysis_history WHERE run_kind='scheduled'` —
   should have 1 row per ticker per day.
10. Manually trigger a re-run without `--update`. Confirm
    current table unchanged, history table grew.
11. Test `/replay AAPL 2026-04-15` from Discord. Confirm cache-hit
    path returns existing data without dispatching jobs.

### Rollback

- If Phase 2 ships a regression, revert the code changes. Schema
  stays (additive — no harm). History accumulates from the next
  good deploy.
- If Phase 1 misbehaves (unlikely — additive only), drop the new
  tables. Existing tables are untouched.

## Open questions (decide before implementation)

### Q1. Do `replay_cached` events get a row?

The plan as written doesn't write a history row when `/replay`
returns cached data (no compute happened). Should we still log it
somewhere — maybe a `replay_audits` table, or extend
`insight_runs.trigger='cache_hit'`?

**Recommendation:** add to `insight_runs` (extend the existing audit
schema) with `status='cache_hit'`. Reuses an existing table; surfaces
"who ran replay and got cached data" in the existing Discord
audit-trail tooling.

### Q2. Naming — `--update` vs `--force` vs `--refresh`?

`--update` matches the user's spec language. `--force` reads as more
destructive. `--refresh` is the Discord-side flag name.

**Recommendation:** keep `--update` for the CLI flag (matches user's
language), keep `refresh` as the Discord option name (more natural
in slash-command UX), document both.

### Q3. Should `auto_refresh_top_n.py` set `--update`?

This script triggers insight pipelines when a top-mover is detected.
Without `--update` it would skip already-written rows.

**Recommendation:** does NOT pass `--update` — the dedupe-via-skip
behavior is exactly what `auto_refresh` wants. The
`run_kind='auto_refresh'` tag in history captures the attempt
regardless.

### Q4. History retention?

History tables grow ~6-25 rows/day. After 1 year: 1500-6000 rows.
Negligible for now.

**Recommendation:** no retention policy this PR. Add a
`scripts/prune_old_history.py` later if size becomes a problem
(>1M rows).

## Pickup instructions for implementation

1. **Read** this plan top to bottom and confirm the open questions.
2. **Branch off `main`** after PR #150 lands:
   ```
   git checkout main && git pull
   git checkout -b feat/morning-run-protection
   ```
3. **Phase 1 first** — schema migration + backfill. Land as one PR.
   Verify on live before continuing.
4. **Phase 2** — code changes. Land as a second PR with the test
   suite. Each commit isolated by file:
   - Commit 1: `lib/database.py` row_exists helper
   - Commit 2: brief `--update` flag + history write
   - Commit 3: pipeline `--update` flag + history write
   - Commit 4: `render_existing_brief` + `push_one` entry points
   - Commit 5: `/replay` cache-first restructure + schema update
   - Commit 6: tests
5. **Phase 3** — deploy + verify (manual checklist in this doc).

PR titles:
- Phase 1: `feat(schema): add premarket_analysis_history + insight_reports_history`
- Phase 2: `feat(brief, pipeline, replay): protect canonical morning runs + cached /replay`

## Why now

- Today (4/29 EDT) only 2/5 watchlist tickers retain their canonical
  8:30 brief. The corruption rate is real and observable.
- Every Discord `/replay` makes it worse.
- The fix is purely additive at the schema level — zero risk to
  existing readers.
- The user has already audited the proposal and called out the
  edge cases (Cloud Scheduler retries, BRIEF_AS_OF replay,
  /replay cached behavior).
