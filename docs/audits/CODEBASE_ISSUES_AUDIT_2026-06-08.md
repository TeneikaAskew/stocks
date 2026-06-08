# Codebase Issues & Historical-Bug-Pattern Audit — 2026-06-08

**Status: LIVING DOCUMENT (iteration 1).** This is a standing inventory of
known issues, active bugs, and the *patterns of behaviour* that have
historically produced bugs in this repo. It is built to be extended across
multiple passes — each iteration deepens the root-cause analysis and closes
gaps flagged in §9 (Open investigation backlog).

## Scope & method

Three evidence sources were cross-referenced:

1. **GitHub issues** — all 56 open issues (read in full via the failure
   notifier's JSON dump), categorised by failure family.
2. **GitHub PRs** — open PRs (in-flight work) + merged-PR archaeology via
   `git log` to establish fix-state of each recurring bug.
3. **The codebase itself** — grepped for the five forbidden silent-fallback
   patterns (CLAUDE.md §3.7), pandas-2/3 API misuse, pg8000/psycopg2 driver
   mismatches, and capacity-vs-timeout smells (CLAUDE.md Rule 0).

It consolidates and extends the prior point-in-time audits:
`docs/incidents/2026-06-01-pipeline-failures-audit.md`,
`docs/audits/FALLBACK_AUDIT_2026-05-13.md`,
`docs/incidents/2026-05-09-schema-migration-not-auto-applied.md`,
`docs/incidents/2026-04-14-market-data-daily-gap.md`, and
`docs/HARDCODED_VALUES_REMEDIATION.md`.

---

## 1. Branch & PR landscape

- **Remote branches**: only `main` and the audit branch
  `claude/ecstatic-wozniak-AaTYw`. Feature branches behind open PRs
  (`feature/trading-platform`, `claude/strat-engine-directional-calibration-wHAis`,
  `feature/earnings-frontend-data`, `claude/pipeline-indicator-failures-fG5Eh`)
  exist on the remote but were not in the default fetch refspec at audit time.
- **Open PRs of note**:
  | PR | Branch | State | Note |
  |---|---|---|---|
  | #589 | feature/trading-platform | open | Platform redesign Phase 1 (shell only) |
  | #588 | strat-engine-directional | open | Direction leg research → **DEAD-END verdict**; ships TYPE walk-forward fix |
  | #585 | feature/earnings-frontend-data | open | Earnings mat views + 8-endpoint router |
  | #577 **and** #578 | claude/pipeline-indicator-failures-fG5Eh | open | **Duplicate PRs of the same branch/SHA** — see §8 process smells |

---

## 2. Active production bugs (GitHub issues → root cause → fix-state)

The failure notifier (`gcp/failure_notifier.py`) opens a **new issue per
failing execution**, so one bug surfaces as several open issues plus a long
comment trail. Comment count (`c=N`) is the best recurrence proxy. Sorted by
recurrence.

| Issue(s) | Job | Symptom (SQLSTATE / exc) | Root cause | Fix-state |
|---|---|---|---|---|
| **#571** (c=83), #569, #570 | magnitude-engine | `42601 syntax error at or near ":"` (pg8000) | Unescaped `:` in raw SQL parsed by pg8000 as a bind param | **Likely fixed** on main — `mag_dataset.py:260` now uses proper `:t` params; magnitude touched by #586/#575. **Verify + close issues** (§9-A) |
| **#584** (c=77), #583 | historical-signals-watchlist | `TypeError: NDFrame.fillna() got unexpected kwarg 'method'` | pandas-3 removed `fillna(method=)`; call site in `lib/trading_analysis.py` order-block ffill | **FIXED** on main, commit `397041e` (2026-06-02) → `.ffill(limit=30)`. **Issues still open = alert noise; close them** (§9-A) |
| **#563** (c=75), #562, #561, #560, #558 | strat-engine | `23502 null value in column "ticker" of strat_features_4h` | featurize emits rows with null `ticker` for the 4h timeframe | Touched by #580/#581/#586 — **verify** the null-ticker path is closed |
| **#559**, #557 | strat-engine | `AttributeError: 'Cursor' has no attribute 'copy_from'` | psycopg2-ism on a pg8000 cursor | `gcp/database.py:413-426` documents pg8000 has no `copy_from` and routes COPY natively — **verify all writers use the wrapper, not raw `cur.copy_from`** |
| **#449** (c=43), #576, #538, #587 | freshness-watchdog / premarket-brief / db-query | `task-timeout` exceeded (300/600s) | Capacity-vs-timeout (CLAUDE.md Rule 0.5) | freshness-watchdog bump to 3600s prescribed in 2026-06-01 audit F2 — **verify deployed** |
| **#471** (c=30), #467–#470 | fetch-earnings-history | `ConnectionResetError 104` / `pg8000 InterfaceError network error` | External/transient + pre-#580 image drift | PR #580 fixed pacing/timeout; **image re-pin** required (2026-06-01 audit F1) |
| #517, #516 | backtest-pipeline | `22P02 invalid input for integer: "-0.75"` | float written to an int column | **Open — verify** which column; either widen schema to numeric or round at write |
| #487, #486 | fetch-news-sentiment | `22001 value too long for varchar(10)` | column too narrow for the sentiment label/source | **Open — widen column** in schema.sql + migration |
| #572 | options-exec-backtest | `ModuleNotFoundError: lightgbm` | dep missing from the image that this job uses | **Open — add to requirements** of the relevant image |
| #485, #484 | backtest-playability | `ImportError/ModuleNotFoundError: tabulate` | dep missing | **Open — add `tabulate` to requirements** |
| #573 | fetch-av-options-historical-intraday | `Cannot pass tz-aware Timestamp with tz param; use tz_convert` | double tz-localize | **Open — switch to `.tz_convert`** |
| #554 | p7b-next-candle-classifier | `RuntimeError: no saved classifier … run --mode=train first` | inference scheduled before training ran | **Open — ordering/guard**: train must precede inference, or skip-with-reason |
| #531/#530/#529/#528/#526/#525/#524 (×7) | intraday-bulk-backfill | 18000s (5h) timeout | Single-shot full-history in-memory backfill | **Architecture — Rule 0**: chunk by ticker/date, bound memory (mirrors strat-engine OOM, 2026-06-01 audit F3) |
| #520 | param-sweep | 28800s (8h) timeout | sweep too large for one task | **Architecture** — task-parallel fan-out |
| #590 | build-options-greeks | 3600s timeout | capacity | **Verify** per-row vs batched Greeks compute |
| #574 | backfill-daily-indicators | 10800s (3h) timeout | capacity | **Verify** batch-by-ticker path |
| #472–#479 (×8) | fetch-market-data | `ssl.SSLError BAD_LENGTH` | External vendor TLS (transient) | **EXTERNAL** — should retry/skip-with-reason, not red-alert ×8 |

---

## 3. Cross-cutting root-cause families

These are the *patterns* — fixing the family prevents the next instance.

### 3.1 pg8000 ≠ psycopg2 driver mismatches (highest-yield family)
The production driver is **pg8000** (Cloud SQL Python Connector), but code is
repeatedly written against **psycopg2** idioms:
- `cur.copy_from(...)` — doesn't exist on pg8000 (#559, #557).
- `:` literals in raw SQL parsed as bind params → `42601` (#571 cluster).
- int columns fed Python floats → `22P02` (#517).
- varchar widths too narrow for real data → `22001` (#487).

**Systemic fix**: a thin DB-write helper that (a) wraps COPY for pg8000,
(b) forbids raw `:` in non-parameterised SQL, (c) coerces dtypes to the
target column types before write. `gcp/database.py:413` already has the COPY
wrapper — the gap is that not every writer uses it.

### 3.2 pandas-2 → pandas-3 migration gaps
`fillna(method=)` removed (#584, now fixed). **Audit the rest**: `df.append`,
`.iteritems`, positional `.fillna`, `is_categorical`, `DataFrame.mad`, and
silent-downcasting deprecations are the usual co-travellers. (§9-B)

### 3.3 Capacity-vs-task-timeout (CLAUDE.md Rule 0)
The single largest *category* of open issues. Every "full-history rebuild /
backfill / sweep" job that loads-all-then-processes eventually exceeds its
task-timeout or OOMs: intraday-bulk-backfill (#524–#531), param-sweep (#520),
backfill-daily-indicators (#574), strat-engine `--rebuild` OOM
(2026-06-01 F3), build-options-greeks (#590). **Pattern fix**: chunk by
partition key (ticker/date), write per-chunk, bound memory, observable
per-chunk logging — exactly Rule 0's "default architectural patterns."

### 3.4 Image drift (deployed digest ≠ merged code)
Cloud Run pins a digest at *job-update* time, not execute time. A merged fix
does **not** reach a job until `./gcp/deploy.sh <job>` re-pins (2026-06-01 F1,
fetch-earnings-history ran pre-#580 code for days). **Pattern fix**: a
post-merge deploy step or a digest-vs-`:latest` drift check
(`infra-drift-detector` exists — wire it to alert on job-digest staleness).

### 3.5 Missing optional dependencies per image
`lightgbm` (#572), `tabulate` (#484/#485). Research/backtest jobs import libs
not in their image's requirements. **Pattern fix**: import-smoke test per
job entrypoint in CI, or a single consolidated requirements set per image tag.

---

## 4. Silent-fallback inventory (CLAUDE.md §3.7)

The canonical inventory is `docs/audits/FALLBACK_AUDIT_2026-05-13.md` (~121
patterns). Re-grep at audit time confirms the surface is still large and
**must not be pattern-matched off when writing new code**:

- `fillna(0)` / `.get(k, 0)` on financial fields — heavy concentration in
  `lib/trading_analysis.py` (34), `lib/earnings_reactions.py` (9),
  `lib/insights.py` (3), `lib/options_greeks.py` (4), `lib/signals.py` (4),
  `lib/backtest.py` (4). Each needs the INTERNAL-vs-EXTERNAL triage from §3.7
  — not all are bugs, but each is a place a missing value silently becomes 0.
- `except Exception:` bare swallows in `lib/` — 21 occurrences across 14 files
  (`data_loader.py` ×4 is the one whose own comment diagnoses the 5/4–5/8
  `level_broken=0%` outage; still present).
- **Good news**: no `continue-on-error: true` remains in
  `.github/workflows/` fetch steps (that forbidden pattern is clean).

**This audit does not re-derive the 121** — it defers to the FALLBACK_AUDIT
and flags that remediation there is still staged/incomplete (§9-C).

---

## 5. Historical incident patterns (what has bitten before)

From `docs/incidents/` + `docs/audits/` + CLAUDE.md incident annotations:

| Date | Incident | Pattern | Guardrail added |
|---|---|---|---|
| 2026-04-14 | market_data_daily gap | fetcher silently shipped fewer rows | freshness watchdog |
| 2026-05-01 | Phase 0.5 per-signal-query timeout | "future-work non-blocking" perf flag on a runbook workload | **CLAUDE.md Rule 0** |
| 2026-05-04→08 | `signal_alerts.level_broken = 0%` outage | `except: return pd.DataFrame()` silent fallback | **CLAUDE.md §3.7** |
| 2026-05-06 | counterfactual replay lied (0 above_vwap) | throwaway harness with parity bugs vs production | **CLAUDE.md §3.6** |
| 2026-05-09 | schema migration not auto-applied | migration used baked-in schema.sql, not live diff | incident doc + issue #376 |
| 2026-05-13 | fallback audit (~121 patterns) | silent fallbacks repo-wide | fallback-guard sub-agent |
| 2026-06-01 | pipeline failures audit | image drift + undersized timeouts + rebuild OOM | this doc extends it |

The throughline: **silent data-discipline failures** and **capacity assumed
rather than computed**. Both now have written rules; the open issues in §2
are mostly *instances that predate or slipped the rules*, plus driver
mismatches (§3.1) that no rule yet covers.

---

## 6. Recommended new guardrails (pattern-level, not instance-level)

1. **pg8000 lint** — a CI check / sub-agent rule that flags `cur.copy_from`,
   raw `:` in `text()` without a matching param, and float→int-column writes.
   This family (§3.1) has produced the most recurring open issues and has
   **no rule yet**.
2. **Job-digest drift alert** — extend `infra-drift-detector` to compare each
   Cloud Run job's pinned digest against `:latest` and alert when a merge
   hasn't been deployed (kills the §3.4 class).
3. **Per-image import-smoke test** — CI imports every job entrypoint to catch
   missing deps (§3.5) before they fail in production.
4. **Failure-notifier dedup** — append to the existing open issue for a job
   surface instead of opening a new issue per execution (§8).

---

## 7. Fix-state summary (what's already done vs outstanding)

- **Done on main**: #584 fillna(method=) (`397041e`); no `continue-on-error`
  in fetch workflows; pg8000 COPY wrapper exists in `database.py`.
- **Likely done, needs verify + issue-close**: #571 magnitude `:`,
  #563/#559 strat-engine cluster (touched by #580/#581/#586).
- **Outstanding code fixes**: #517 (int/float), #487 (varchar width), #572
  (lightgbm), #484/#485 (tabulate), #573 (tz double-localize), #554 (train
  before infer).
- **Outstanding architecture (Rule 0)**: intraday-bulk-backfill, param-sweep,
  backfill-daily-indicators, build-options-greeks, strat-engine `--rebuild`.

---

## 8. Process / operational smells

- **Duplicate PRs #577 and #578** — identical branch
  (`claude/pipeline-indicator-failures-fG5Eh`) and SHA (`5b02f9b`). One should
  be closed.
- **Failure-notifier issue spam** — opens N issues for one bug surface
  (intraday-bulk-backfill = 7 issues, fetch-market-data = 8, strat-engine = 7).
  Inflates the open-issue count and buries signal. Dedup recommended (§6.4).
- **Issues stay open after the fix merges** — #584 fixed 2026-06-02, issue
  still open. No auto-close on the fixing commit. Many of the 56 "open" issues
  are already-fixed noise.

---

## 9. Open investigation backlog (next iterations)

This is iteration 1. Subsequent loop passes should close these:

- **9-A · Verify-and-close**: confirm #571 (magnitude `:`), #563/#559
  (strat-engine) are fixed on main; close the stale issues. Reproduce via the
  production replay paths (CLAUDE.md §3.6), not throwaway harnesses.
- **9-B · pandas-3 sweep**: grep the full codebase for the co-traveller
  deprecations (§3.2) beyond `fillna(method=)`.
- **9-C · FALLBACK_AUDIT delta**: diff the current tree against the 5/13
  inventory — how many of the 121 are remediated, how many remain, any new
  ones introduced since.
- **9-D · Closed-issue / merged-PR archaeology**: mine closed issues & merged
  PRs for *recurring* fix titles (same bug fixed more than once = a pattern
  the codebase keeps re-growing).
- **9-E · Branch sweep**: fetch the open-PR feature branches and check whether
  any carry an unmerged fix for an open issue (e.g. does #577/#578 close
  #574-class indicator nulls?).
- **9-F · Per-job capacity table**: for every Rule-0 timeout issue, compute
  the back-of-envelope volume × velocity × wall-clock and the corrective
  chunking strategy.
- **9-G · pg8000 writer audit**: enumerate every `.to_sql` / raw-COPY /
  `execute(text(...))` write site and confirm dtype coercion + param binding.

---

## 10. Iteration 2 — fix-state reconciliation (2026-06-08)

Mining merged PRs + `git log -S` against each open issue's symptom shows that
**most of the 56 "open" issues are already fixed** — the failure notifier
opens issues but never closes them when the fixing commit lands. Verified
fix-states:

| Issue(s) | Symptom | Fix | Fix date | Issue created | Verdict |
|---|---|---|---|---|---|
| #584/#583 | `fillna(method=)` | `397041e` → `.ffill(limit=30)` | 2026-06-02 | 2026-06-02 | **FIXED-but-open** |
| #517/#516 | `22P02` int/float | **#518** `_coerce_int_columns` in `upsert_dataframe`+`bulk_insert_dataframe` (b481d74) — "kill the 22P02 bug class" | 2026-05-17 | 2026-05-17 | **FIXED-but-open** (bug *class* killed) |
| #487/#486 | `22001` varchar(10) | schema widened to `VARCHAR(20)` in #514 (dfd2395) | 2026-05-17 | 2026-05-14 | **FIXED-but-open** |
| #484/#485 | `ModuleNotFoundError: tabulate` | `tabulate>=0.9.0` added to `requirements-gcp.txt` (8f6bb22) | 2026-05-30 | 2026-05-14 | **FIXED-but-open** |
| #572 | `ModuleNotFoundError: lightgbm` | job uses `:research` image; `lightgbm>=4.1.0` in `requirements-research.txt` | (pre-existing) | 2026-05-27 | **FIXED or image-drift** — verify pinned digest |
| #571/#569/#570 | magnitude `:` `42601` | `mag_dataset.py` uses `:t` params; magnitude touched by #586/#575 | ~2026-06 | 2026-05-27 | **Likely fixed** — verify + close |
| #563…#557 | strat-engine null-ticker / `copy_from` | touched by #580/#581/#586; COPY wrapper in `database.py:413` | ~2026-05/06 | 2026-05-26 | **Likely fixed** — verify + close |

### 10.1 The headline finding
**Stale-issue noise dominates the open-issue list.** At least 7 distinct bug
*classes* (≈24 of the 56 open issues) are already remediated on `main`; they
remain "open" only because the notifier has no close-on-fix step. The true
backlog is far smaller than "56 open issues" suggests. **Action**: a reconcile
pass that closes fixed issues, and a notifier enhancement to auto-close (or
at least de-duplicate) — see §6.4 / §8.

### 10.2 Residual risks behind the "fixed" label (real, narrow)
1. **INT-coercion only guards two write paths.** `_coerce_int_columns` runs
   inside `upsert_dataframe` and `bulk_insert_dataframe`. Any writer using raw
   `COPY`, `.to_sql`, or a hand-rolled `execute(text(...))` INSERT **bypasses
   it** and can resurrect the 22P02 class. This is exactly the §9-G writer
   audit — still open and now higher priority.
2. **`VARCHAR(20)` is a bigger bucket, not an unbounded one.** A sentiment
   source emitting a >20-char label re-triggers 22001. Prefer `TEXT` for
   free-form vendor labels, or validate-and-truncate-with-warning at the
   writer.
3. **#572/#590-class "fixed" depends on the deployed digest.** Because Cloud
   Run pins digests at job-update time (§3.4), a dep present in
   `requirements-*.txt` is only *actually* available if the job was
   re-deployed after the requirement landed. The dep-in-requirements check is
   necessary but not sufficient — pair it with a digest-freshness check.

### 10.3 What is genuinely still open (the real backlog)
After removing fixed-but-open noise, the substantive remaining work is:

- **Capacity / Rule-0 timeout class** (the largest real category):
  intraday-bulk-backfill (#524–#531), param-sweep (#520),
  backfill-daily-indicators (#574), build-options-greeks (#590), and the
  strat-engine `--rebuild` OOM. These need *architecture* (chunk-by-partition,
  bounded memory), not another timeout bump. Several have already been
  whack-a-moled with timeout bumps in history (premarket-brief #552, AV
  intraday → 8h, freshness-watchdog → 15min) — bumps buy time but don't fix
  the load-all-then-process shape.
- **§9-G pg8000 writer audit** — the one structural gap that keeps the
  driver-mismatch family (§3.1) alive despite the #518 systemic fix.
- **#573 tz double-localize**, **#554 train-before-infer ordering** — small,
  genuinely-open code fixes.
- **Process**: notifier close-on-fix + dedup; close duplicate PR #577/#578.

### 10.4 pandas-3 migration — cleared
Full sweep of `lib/ gcp/ scripts/` found **no** `DataFrame.append`,
`.iteritems`, `.ix`, `is_categorical`, `.mad`, or `pd.np` usage. The only
pandas-3 break was the now-fixed `fillna(method=)`. `inplace=True` usage is
minimal (`trading_analysis.py` ×3, `backfill_signals.py` ×2) and not a
correctness risk. **§9-B is closed: pandas-3 migration is effectively clean.**

