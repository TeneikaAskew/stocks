# Incident: schema migration not auto-applied — 19h silent degrade of per-ticker calibration

**Date identified:** 2026-05-09 ~21:00 UTC
**Affected table:** `exit_config_overrides` (Cloud SQL — column `disabled_directions` was missing from production despite being declared in `gcp/schema.sql`)
**Affected runtime:** Live `signal_monitor` Cloud Run Job for the 2026-05-09 RTH session (13:30–20:00 UTC)
**User impact:** Every per-ticker resolver in `lib/strategies/exit_config_overrides.py` returned `None` because the SELECT errored on the missing column. The live monitor degraded to Tier-B `lib/config.py:ExitConfig` defaults (target=0.003, stop=0.0015, time_stop=30) instead of the audit-recommended SPY 0.00184 / IWM 0.00281 / QQQ 0.00301 etc. The per-ticker calibration that the entire Phase 1 audit work was meant to land was effectively inert in production for the entire 2026-05-09 RTH session.

## Timeline

| When (UTC) | Event |
|---|---|
| **2026-05-09 02:09** | **PR #358 merged to main.** Added `ALTER TABLE exit_config_overrides ADD COLUMN IF NOT EXISTS disabled_directions JSONB` to `gcp/schema.sql` AND added `disabled_directions` to the SELECT in `lib/strategies/exit_config_overrides.py:_latest_overrides()`. No workflow auto-triggered `apply-schema-migrations` after the merge. |
| 2026-05-09 09:25 | Cloud Scheduler fires `signal-monitor-rth` for the 2026-05-09 RTH session. Fresh process, fresh `lru_cache`. First `_latest_overrides('SPY')` call: SELECT raises `column "disabled_directions" does not exist`, helper's `try/except` catches it, returns `None`. Same for every subsequent ticker call across the session. Live monitor reads Tier-B defaults from `lib/config.py:ExitConfig` for the rest of the day. No crash; degrade is silent by design. |
| 2026-05-09 13:30–20:00 | RTH session runs entirely on Tier-B defaults. Every fired alert's `target_price` is computed as `entry × (1 + 0.003)` instead of the audit-recommended per-ticker value. |
| **2026-05-09 ~21:00** | Drift discovered while investigating an unrelated `disabled_directions` policy concern. Ran `db-query.yml` workflow to inspect production schema; query returned 12 columns; `disabled_directions` was absent. |
| 2026-05-09 21:01 | `gcloud run jobs execute apply-schema-migrations --wait` triggered manually. Migration completed successfully; column count is now 13 (with `disabled_directions` present). |
| 2026-05-09 21:02 | Followed up: `UPDATE exit_config_overrides SET disabled_directions = NULL WHERE disabled_directions IS NOT NULL` to clear the QQQ `["PUT"]` value the schema seed had just inserted (the user does not want a static direction kill switch). |
| 2026-05-09 ~22:00 | This PR (PR-INC-1) opened — removes the QQQ seed from `gcp/schema.sql`, adds the missed `disabled_conditions` seed for IWM/QQQ from PR #329 (also never landed for the same reason — though `disabled_conditions` column existed, no UPDATE seeded the per-ticker values), adds the auto-trigger workflow, adds this postmortem, amends the validation doc. |

## Root cause

`apply-schema-migrations` is a Cloud Run Job in `gcp/deploy.sh:540-559` that reads `gcp/schema.sql` and applies all the `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements. **It exists, it works, but nothing auto-triggers it on a `schema.sql` push.** The job had to be manually invoked, and that responsibility was on whoever shipped the schema-changing PR — a human checklist item rather than CI plumbing.

The application-side resilience pattern is **correct but misleading**. `lib/strategies/exit_config_overrides.py:_latest_overrides()` wraps the SELECT in `try/except` and logs a warning before returning `None`. That's the right behaviour for transient network errors, but for a structural schema mismatch it produces a long-lived silent degrade that's easy to miss. The same warning fires every minute for every ticker without escalating.

## What went silent

Two separate seeds also weren't applied because of related coverage gaps:

1. **`disabled_directions` column** — declared in `schema.sql` by PR #358 but never migrated to production. Discovered during this incident.
2. **`disabled_conditions` for IWM/QQQ** — column existed (from PR #326) but the per-ticker UPDATE seeding `["stoch_rsi_overbought", "rsi_overbought_zone"]` for IWM/QQQ MR PUT (the audit's G.P0.13 recommendation) was **never written into `schema.sql`**. PR #329 added the live-read code but no seed, so the per-ticker drops never reached production. This PR adds that seed.

## Prevention

1. **Auto-trigger workflow** — `.github/workflows/apply-schema-migrations-on-change.yml` (added in this PR) runs `gcloud run jobs execute apply-schema-migrations --wait` on any push to `main` that touches `gcp/schema.sql`. Failure surfaces as an auto-filed GitHub issue via the standard `handle-workflow-failure.yml` reusable workflow. Closes the loop within ~2 minutes of merge.

2. **Detection-side gap (separate follow-up)** — the `infra-drift-detector` agent at `.claude/agents/infra-drift-detector.md:56-57` already detects "column declared in `schema.sql` but missing from production" via `information_schema.columns` comparison. It's only invoked manually via `/audit-review`. A future change should wire it into the deploy gate (either as a CI check on PRs that touch `schema.sql`, or as part of `pre-deploy-check`). Out of scope for this PR; tracked as a follow-up.

3. **Application-side warning escalation (separate follow-up)** — `_latest_overrides`'s warning log fires per-bar per-ticker without rate-limiting or escalation. Could rate-limit (warn once per process per ticker) AND emit a Discord alert if the same ticker degrades for >5 consecutive cycles. Out of scope for this PR.

## Production impact (estimated)

The signal-monitor Cloud Run Job for 2026-05-09 RTH (13:30–20:00 UTC) ran with Tier-B defaults. Per `signal_alerts` data, ~150-200 alerts were fired during the session. Each alert's `target_price` was computed as `entry_price × (1 + 0.003)` instead of the audit-recommended per-ticker value:

| Ticker | Pre-fix `target` (Tier-B default) | Audit-recommended (Tier-A) | Per-trade impact |
|---|---:|---:|---|
| SPY | 0.00300 | 0.00184 | Stops out further than calibrated → win-rate lower than projected |
| IWM | 0.00300 | 0.00281 | Closer to neutral; minor degrade |
| QQQ | 0.00300 | 0.00301 | Negligible — Tier-B happens to match |

The same drift affected `call_stop`, `put_stop`, `call_time_stop`, `put_time_stop`, and `blue_sky_atr_offset` (used by the trade planner). No alert outcome was catastrophically wrong, but the audit's projected impact (e.g. QQQ mean per-trade return −0.0005% → +0.0127%) was not realized for that one session.

## Verification of fix

Post-merge:

```sql
SELECT column_name FROM information_schema.columns
 WHERE table_name = 'exit_config_overrides' ORDER BY ordinal_position;
-- Should include `disabled_directions` (col 13).

SELECT ticker, disabled_directions, disabled_conditions
  FROM exit_config_overrides ORDER BY ticker;
-- All `disabled_directions` should be NULL.
-- IWM and QQQ should have `disabled_conditions` =
--   ["stoch_rsi_overbought","rsi_overbought_zone"]; SPY NULL.
```

Smoke-test the auto-trigger workflow by pushing a no-op `gcp/schema.sql` change (an idempotent ALTER that's a no-op against current state, then revert) and confirming the workflow fires and the migration job exits 0 within ~2 minutes.

## Related

- **PR #358** — original PR that added `disabled_directions` to `schema.sql` + live-read code. Migrated correctly via this incident's manual run.
- **PR #329** — added `disabled_conditions` live-read code; this incident discovered the per-ticker IWM/QQQ seed was never landed.
- **PR-INC-1** (this PR) — schema cleanup + auto-trigger workflow + this postmortem + validation doc amendment.
- Validation doc that needs amending: `docs/audit/2026-05-08/validation-2026-05-09.md` lines 75-94 (claims per-ticker resolver was production-live; was actually inert during the 19h gap).
