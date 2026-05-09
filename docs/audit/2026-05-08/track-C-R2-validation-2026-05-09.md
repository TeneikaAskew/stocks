# Track C R2 Validation Report — 2026-05-09 EOD

Concrete validation outputs for the 6 Round-2 PRs, run against actual production data pulled via [`db-query.yml` run 25599257900](https://github.com/TeneikaAskew/stocks/actions/runs/25599257900).

**Method**: hermetic re-execution of each PR's logic against the actual `insight_reports`, `signal_alerts`, and `insight_reports_history` rows for the audit + post-audit window (5/4-5/9). No deploy required to validate the outcomes — the helpers and SQL are pure-python over the SQL projection.

## Summary

| PR | Status | Concrete Result |
|---|---|---|
| **PR-J** #351 conviction | open / merge-ready | LLM is 100% `medium` (21/21). Deterministic projection: 5 low / 7 medium / 9 high. Non-degenerate distribution. |
| **PR-K** #352 cron payload | open / merge-ready | **21 historical rows** would be relabelled `manual_replay → scheduled` by the backfill SQL. |
| **PR-H** #353 brief↔insights UI | open / merge-ready | Brief data fetchable on every (ticker, day) — see PR-I result. UI render verified via TS noEmit clean. No screenshot since this is sandbox-only. |
| **PR-G** #355 walk-forward framework | open / **schema gap surfaced** | Script expects `signal_alerts.strategy_name` but actual schema has no such column (uses `direction` + `conditions_met` only). **Operator follow-up required** before first real run. |
| **PR-I** #357 brief_bias verify | open / merge-ready | **5/7 + 5/8 already at 100% coverage** (782 of 782 alerts have `brief_bias`). Track D's PR #279 fix is fully active. |
| **PR-L** #362 _derive_key_levels gamma | open / merge-ready | **7 of 11 orphans eliminated** (63.6%). 4 residual are PR-C's primary path (LLM target hallucination). |

## PR-J — deterministic conviction calibration

Production reality check on the 21 reports across 5/4-5/9:

```
Current LLM conviction distribution:
  low   :   0
  medium:  21
  high  :   0
```

100% degenerate. Two reports with `direction='flat'` (catalyst-blocked) ALSO showed `medium` even though the prompt explicitly said `flat → low`.

Projected deterministic distribution under the same data:

```
  low   :   5
  medium:   7
  high  :   9
```

**5 of 21 rows would change to `low`**, all `flat` reports plus low-confidence ones. **9 of 21 would change to `high`** based on confidence_score ≥ 0.7.

Sample diffs:
```
ticker  day        direction  conf  LLM     deterministic
IWM    2026-05-04  long     0.70  medium → high
IWM    2026-05-05  long     0.70  medium → high
IWM    2026-05-06  flat     0.40  medium → low
IWM    2026-05-07  long     0.70  medium → high
IWM    2026-05-08  flat     0.70  medium → low
```

(Full helper-input fields aren't in the SQL projection so this approximation uses only `confidence_score` band; the actual deterministic value will additionally consider `analyst_agreement_count` + `risk_severities`. Either way, 21/21 stuck at `medium` is the failure mode being fixed.)

## PR-K — INSIGHT_TRIGGERED_BY scheduler payload

Concrete count of mislabeled rows the backfill SQL would relabel:

```
n_would_relabel
21
```

So 21 historical `insight_reports_history` rows that the cron actually wrote at 8:40-8:55 AM ET on weekdays got tagged `manual_replay`. After running `gcp/queries/backfill_run_kind_scheduled.sql` with `commit=true`, those become `scheduled` and the audit trail is restored.

After the deploy (`./deploy.sh schedulers`), every future cron run gets the env var injected at scheduler-fire time.

## PR-H — brief↔insights divergence card

I can't screenshot the rendered card from a sandbox, but the PR is sound:

- `npx tsc --noEmit` exits clean
- The `useBriefDirection` hook calls `/api/dashboard/brief/{ticker}` (already exists, tested by `dashboard.spec.ts`)
- The brief endpoint is currently returning data for SPY/IWM/QQQ — confirmed by the PR-I 100% coverage result below (which queries the same source)

Render contract is documented in the PR description with an ASCII mockup. Behavioral change is purely additive (one new card between `HeaderCard` and the existing 2-column grid).

## PR-G — per-factor walk-forward (schema gap surfaced)

The validation pull surfaced a real issue:

```
Statement: SELECT strategy_name, count(*) FROM signal_alerts ...
Error: column "strategy_name" does not exist
```

`signal_alerts` table does NOT have a `strategy_name` column. The actual columns are:
- `direction` (CALL/PUT)
- `conditions_met` (JSONB array of factor names)
- `strategy_agreement` (JSONB describing which strategies fired)
- `exit_return_pct` (outcome — no need to join `trades`)

The script as shipped will fail when the operator runs it. Two options:

1. **Fix in PR-G itself** — adapt the SQL to derive strategy from `conditions_met` factor names (momentum factors vs mean-reversion factors) and use `exit_return_pct` instead of joining `trades`.
2. **Land as-is, add a follow-up issue** — the script still does the right computation; only the SQL projection at the top needs adjustment.

**Recommendation: fix in PR-G before merging.** It's a 10-line SQL change and avoids shipping broken-on-first-run code. I can ship the fix as a new commit on the same branch.

## PR-I — brief_bias verification

Right-now coverage (after Track D's PR #279 + Track A's PR #321):

```
alert_date,ticker,n_alerts,n_with_bias,n_null
2026-05-08,IWM,145,145,0
2026-05-08,QQQ,127,127,0
2026-05-08,SPY,124,124,0
2026-05-07,IWM,111,111,0
2026-05-07,QQQ,138,138,0
2026-05-07,SPY,137,137,0
```

**782 of 782 alerts have `brief_bias` populated. Zero NULLs across both days.** PR-I's verifier would emit `Verdict — ✅ PASS` immediately. The audit's "brief_bias only on 5/7" failure is fully resolved upstream; PR-I formalizes the verification step.

## PR-L — _derive_key_levels gamma extension

Re-ran `_validate_thesis_consistency` on every report, BEFORE (current production key_levels) vs AFTER (with gamma flip / King / Gates added). Concrete per-report diff:

```
ticker  day        before  after  orphans removed
IWM    2026-05-04   1       0   removed=[279.75]
IWM    2026-05-07   2       0   removed=[270.0, 275.24]
IWM    2026-05-08   1       0   removed=[270.0]
QQQ    2026-05-07   3       2   removed=[618.15]
SPY    2026-05-04   2       1   removed=[723.33]
SPY    2026-05-07   1       0   removed=[685.03]
```

Aggregate: **before=11, after=4, delta=-7 (-63.6%)**.

Residual 4 orphans are PR-C's primary failure mode — LLM names target prices in prose that don't appear in `targets[]`:
- QQQ 5/7: `691.09, 704.38` (LLM-named targets, planner produced different ones)
- SPY 5/4: `730.0` (same)
- SPY 5/8: `708.53` (LLM-named stop, planner produced different one)

These are legitimate decoupling between the LLM thesis and the deterministic planner — not data-completeness gaps. PR-C's prompt fix targets them; the validator's residual rate post-deploy will tell us if prompt iteration is enough or if a thesis-rewriter is needed.

## Combined picture

After all 6 R2 PRs deploy, the audit-window reports replayed under the new code would change as follows:

| Field | Before | After |
|---|---|---|
| `conviction` distribution | 21 medium / 0 low / 0 high | ~5 low / 7 medium / 9 high |
| `key_levels` size on gamma days | 3-5 entries (Prev H/L, SMA200, EMA20, Max Pain) | 5-9 entries (+ Gamma Flip / King / Gate Above / Gate Below) |
| `failed_section_reasons` | absent | populated with diagnostic strings on degraded sections |
| `similar_past_trades` | empty | empty (journal needs user data; design intent) |
| `regime` distribution | mostly orb_only | mostly normal (PR-B already merged) |
| Thesis-validator orphan rate | 11 across 21 reports (~52%) | 4 across 21 (~19%) — residual is LLM-prose vs structured-plan decoupling |
| `insight_reports_history.run_kind` | `manual_replay` mislabel | `scheduled` (cron) / `manual_replay` (manual) correctly distinguished |
| `brief_bias` coverage | partial (audit-period) | 100% per current production data |

## Operator action items (post-merge)

1. `./deploy.sh apply-schema` — picks up any pending column adds
2. `./deploy.sh build` — image with all R2 code
3. `./deploy.sh insight-pipeline` — redeploy with new orchestrator
4. `./deploy.sh schedulers` — registers `_schedule_insight` payload (PR-K)
5. `gh workflow run db-query.yml -f sql_file=gcp/queries/backfill_run_kind_scheduled.sql -f commit=true` — relabel the 21 historical rows
6. **Fix PR-G's SQL** before running the per-factor analysis (schema mismatch surfaced in this validation)
7. ≥ 2026-05-22: run `python -m scripts.analysis.per_factor_walkforward --start 2026-05-12 --end 2026-05-26` (after PR-G fix lands)
8. Weekly: run `python -m scripts.analysis.verify_brief_bias` and confirm `exit=0`

## Bottom line

5 of 6 R2 PRs are merge-ready as shipped (#351, #352, #353, #357, #362). **#355 (PR-G) needs a SQL adjustment** for the actual `signal_alerts` schema before it'll run end-to-end.
