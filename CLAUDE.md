# Project Instructions for Claude Code

## Project Overview
This is a stocks/trading application project that includes Google Apps Script components for market data fetching, historical data backfilling, and continuation systems for long-running operations.

## Critical Rules - MUST FOLLOW

### 0. Production-Grade Architecture — NON-NEGOTIABLE

**You only ship production-grade solutions. Every design must explicitly account for cloud and data capacity at design time, NOT as future work.**

This rule was added on **2026-05-01** after a Phase 0.5 incident where I shipped a script with a known per-signal-query architecture, flagged it as "future-work, non-blocking" in my own PR review, then watched it time out repeatedly in production while sending the user a stream of failure emails. The runbook I wrote alongside the PR explicitly told the user to run the exact workload my script couldn't handle. That cost real GCP money, real attention, and real trust.

#### Rules

1. **No "future-work, non-blocking" perf flags on workloads in the runbook.** If a PR's runbook says "kick off this backfill", the code in that PR must handle that backfill. Either fix the perf concern before merging or remove the workload from the runbook with an explicit "do not run X until Y lands."

2. **Always do a back-of-envelope capacity calculation BEFORE merging.** Three numbers, written in the PR description:
   - **Volume**: how many input rows × bytes/row
   - **Velocity**: SQL queries / API calls / network round-trips per input row × total
   - **Wall-clock**: queries × per-query latency at production driver speeds (pg8000 + Cloud SQL Connector ≈ 0.5–2 s per round-trip; psycopg2 ≈ 50–200 ms)
   If wall-clock exceeds the configured Cloud Run task-timeout, the architecture is wrong, not the timeout.

3. **Hermetic tests are necessary but not sufficient.** Synthetic in-memory DataFrames run in microseconds; production runs against the network. A test suite of pure-helper unit tests proves correctness, not deployability. Every PR that touches a Cloud Run job must include either:
   - A test that asserts the I/O shape (e.g. "N source rows of K tickers triggers exactly K queries"), or
   - A documented production smoke test in the test plan with the actual data volume the runbook will hit.

4. **Default architectural patterns for this stack:**
   - **Batch SQL queries by partition/grouping key** (ticker, date, etc.) — never per-row when N could exceed 100. Pull one query covering the union range, slice in memory.
   - **Bound memory** — write to DB in per-group chunks rather than accumulating all results before any commit. A crash mid-job should leave partial progress durable, not lose everything.
   - **Observable progress** — log per-group counts so a 30-minute job is debuggable, not a black box. `logger.info("ticker=%s processed=%d/%d", ...)` is the bar.
   - **Resilient to bad data** — one missing partition logs a warning and skips, doesn't crash the batch.
   - **Idempotent re-runs** — `ON CONFLICT DO UPDATE` so a re-run after a partial failure converges, not duplicates.
   - **Bounded retries** — Cloud Run can't distinguish transient from permanent failures. `--max-retries 0` is the default unless you can prove transient retries help and double-emails are acceptable.

5. **Cloud Run Job sizing checklist:**
   - **task-timeout**: ≥ 4× the wall-clock estimate. Cloud Run charges runtime, not the cap, so headroom is free.
   - **memory**: ≥ 512 MiB (gen2 minimum with always-allocated CPU). Estimate peak working-set, double it.
   - **max-retries**: 0 unless explicitly justified.
   - **--args**: use `--args="--mode=foo"` (with `=`) when the value starts with `-`, otherwise gcloud parses it as a new flag.

6. **Cost discipline:**
   - Estimate **$/run × runs/day × 30** in the PR description for any new scheduled job.
   - A scheduler firing a failing job is a slow leak — paused/disabled-on-failure beats endless-retry-on-failure.
   - Cloud SQL queries are free (instance is always-on); Cloud Run round-trips are cheap individually but expensive in aggregate. Optimize round-trips, not query cost.

7. **When you find yourself writing "non-blocking", "future-work", or "for now" in a perf-related context — stop and re-read rule 1.** Those phrases are how shipping happens with known-broken architecture. They are only acceptable when the slow path is genuinely unreachable from the runbook in the same PR.

### 1. File Management Philosophy - READ FIRST, CREATE LAST
- **ALWAYS** read and understand existing files before making any changes
- **SEARCH** thoroughly for related files using Grep, Glob, and Read tools
- **NEVER** create new files if functionality can be added to existing files
- **PREFER** modifying/extending existing modules over creating new ones
- When addressing a problem:
  1. First: Read ALL related files to understand current implementation
  2. Second: Check if similar functionality already exists
  3. Third: Consider if changes can be made to existing files
  4. Last resort: Only create new files when absolutely necessary
- Before creating any file, ask yourself:
  - Have I read all related existing files?
  - Can this be added to an existing module?
  - Is there a similar pattern already in the codebase?
  - Would modifying an existing file be more appropriate?

### 2. Git Commit Guidelines
- **NEVER** include Claude branding in commits (no "built by Claude", "generated by Claude", etc.)
- **NEVER** use the 🤖 emoji or Claude-specific signatures in commit messages
- Write commit messages as if you are a human developer on the team
- Use conventional commit format: `type: description` (e.g., `fix: resolve API timeout issue`)
- Keep commit messages concise and focused on the change itself

### 2. Branching Strategy

**REMINDER: never edit on `main` directly. Always start on a feature branch.**
This is a guardrail for consistency and reliability — `main` is shared,
deployed, and reviewed; commits there bypass CI / PR review and create
drift between local and origin.

#### First action of every session

Before touching ANY file, run:
```bash
git status                    # confirm current branch
git rev-parse --abbrev-ref HEAD
```

If the result is `main`, STOP and create a feature branch first:
```bash
git checkout -b feature/short-description    # for new features
git checkout -b fix/short-description        # for bug fixes
git checkout -b docs/short-description       # for doc-only changes
```

Then push with upstream tracking on the first push:
```bash
git push -u origin feature/short-description
```

#### Naming convention

- `feature/<description>` — new features
- `fix/<description>` — bug fixes
- `docs/<description>` — doc-only changes
- `chore/<description>` — refactors, deps, build tooling
- `fix/workflow-{name}-{run-number}` — auto-created failure-handler branches

Use kebab-case, keep under ~40 chars, no emoji, no PR/issue numbers.

#### Hard rules (no exceptions without explicit user authorization)

- **Never commit directly to `main`** for any non-trivial change
- **Never `git push origin main`** without explicit user authorization
- **Never `git push --force` to `main`** under any circumstances
- **Never `git rebase` or `git reset --hard` on `main`** when others may pull
- All non-trivial changes go through a PR to `main`, even one-author repos

#### What "trivial" means (the only acceptable direct-to-main edits)

Only these may go straight to `main`:
- Single-line typo fixes in markdown
- README link corrections
- `.gitignore` additions for already-ignored locally-generated files
- The auto-status-tracker bumps that the `/commit` skill writes

Everything else — code, schema, workflows, agent docs, briefing deck
edits, dependency bumps — goes through a feature branch + PR.

#### How to recover when work has accidentally landed on `main`

If you've already committed to `main` locally (haven't pushed):
```bash
git branch feature/short-description    # save the work
git reset --hard origin/main             # rewind main locally
git checkout feature/short-description   # switch to the saved branch
git push -u origin feature/short-description
gh pr create --base main --head feature/short-description ...
```

Never `git push origin main` to "just publish what I already did" — that
defeats the entire purpose of the branch protection.

### 3. Planning & Approval Process
For major changes:
1. **PLAN FIRST**: Create a detailed plan using the TodoWrite tool
2. **GET APPROVAL**: Present the plan to the user and wait for explicit approval before executing
3. **DOCUMENT**: Explain what you're about to do and why
4. Major changes include:
   - Architectural modifications
   - Database schema changes
   - API interface changes
   - Dependency updates
   - Security-related modifications
   - Performance optimizations affecting core functionality

### 3.5. Never Wait for the Next Session — Always Backtest

**This rule was added on 2026-05-09 after I repeatedly punted
verification to "next session" or "wait one trading day" instead of
replaying historical data immediately.**

The premarket-brief / AI-insights / signal-monitor / EOD-resolver
pipeline is **fully replayable** against any historical date. Every
verification I postpone to "the next live run" can be done NOW
against an arbitrary day with the existing job-override env vars and
the historical 1-min bars in `market_data_intraday`.

#### The replay recipe (apply to ANY "wait for next session" question)

Pick a historical date `D`. Treat `D` as if it were today:

```bash
# 1. Premarket brief AS-OF D — uses only data through D-1
gcloud run jobs execute premarket-brief \
  --update-env-vars="BRIEF_AS_OF=2026-05-08" --async

# 2. AI insights AS-OF D — uses only data through D-1
gcloud run jobs execute insight-pipeline \
  --update-env-vars="^|^INSIGHT_AS_OF=2026-05-08|INSIGHT_TICKERS=SPY,IWM,QQQ" \
  --args="--update" --async

# 3. Signal monitor — replay the day's intraday bars one-by-one
#    (use the existing intraday CSVs OR pull market_data_intraday).
#    Read the new structured logs to see counters / failures.
gcloud logging read 'resource.type=cloud_run_job
  AND labels."run.googleapis.com/execution_name"="<exec_id>"' \
  --project=adept-mountain-474619-d4 --limit=100

# 4. EOD reconciler — process the day's signal_alerts post-close
gcloud run jobs execute signal-monitor-eod-resolver \
  --args="--lookback-days=N" --wait

# 5. Verify via SQL — db-query.yml workflow:
gh workflow run db-query.yml \
  -f sql="SELECT ... FROM signal_alerts WHERE alert_date='2026-05-08' ..."
```

#### Forbidden phrases (rewrite the answer)

If you find yourself typing any of these about a verification step,
**stop and replay instead**:

- "waiting for the next session"
- "needs next-session confirmation"
- "1-week clock starts now"
- "verification window opens YYYY-MM-DD"
- "will be visible in next live run"
- "pending live data"

Every one of these is a request you should fulfill RIGHT NOW by
replaying historical data. The only legitimate "wait" is when:

- The historical data physically doesn't exist yet (e.g. waiting for
  the 5/12 daily bar to land if today is 5/9). In that case, replay
  against the most recent available date and explicitly note the
  data window.
- The replay would re-run a billable workload that already ran in
  production and the user hasn't approved the spend.

#### Open question on each issue you'd otherwise close-and-wait

Before filing "verification pending", ask:

1. Can I dispatch the same Cloud Run Job with `*_AS_OF=D-1` to
   reproduce the failure mode on yesterday's data?
2. Can I read `market_data_intraday` for date D and replay the
   strategy against it without touching the live monitor?
3. Can I dispatch a SQL via `db-query.yml` that would already show
   me the answer from the existing schema?

If any answer is yes, do that first. Only file "waiting" if all
three are no.

#### Operator escape hatches (when the replay can't be safely re-run)

If the replay would side-effect on a shared system (e.g. write to
the `insight_reports` canonical row), use the existing `--update`
flag, dry-run flag, or output-to-stdout flag for that job. Never
skip the replay because of a side-effect concern when there's a
flag designed to sandbox the run.

### 3.6. Use Production Replay Paths — No Throwaway Harnesses

**Added 2026-05-10 after the 5/6 counterfactual replay incident.**
I built `/tmp/may6_replay.py` and `_v2.py` to simulate signal_monitor
against cached intraday CSVs. Both had bugs production never had —
V1 mis-set the RTH window against a UTC index (selecting pre-market
hours instead of RTH); V2 omitted the `Time` column, silently
disabling VWAP and reporting "0 above_vwap fires" while production
had been correctly firing 46+ above_vwap PUTs the whole time. I
spent compute + user attention debugging harness bugs and almost
shipped a code change ("drop above_vwap globally") based on the
lying numbers. The lesson: throwaway harnesses introduce parity
bugs that don't exist in production.

#### Rule

ALL replays — counterfactuals, what-ifs, audit verifications,
calibration backtests, "what would 5/6 look like with the new seed"
questions — MUST run through one of these production-grade paths.

| Workload | Replay mechanism | Source |
|---|---|---|
| **Signal-monitor** (1-min RTH bar fires) | `gcloud run jobs execute signal-monitor --update-env-vars="REPLAY_DATE=YYYY-MM-DD,REPLAY_TICKERS=SPY,IWM,QQQ" --wait`, OR hermetic local: `python -m scripts.replay_signal_monitor --date YYYY-MM-DD --tickers SPY,IWM,QQQ`. Runs the EXACT production code path: `update_window` → `calculate_indicators` → `evaluate_ticker` → `_evaluate_strategies_for_bar` → `fire_alert`. DB upsert + Discord webhook are mocked, so it's hermetic. | `gcp/signal_monitor.py` (PR #350), `scripts/replay_signal_monitor.py` |
| **Premarket brief** | `BRIEF_AS_OF=YYYY-MM-DD` env var | `gcp/premarket_brief.py:617` |
| **Insight pipeline** | `INSIGHT_AS_OF=YYYY-MM-DD` env var + `parse_as_of()` helper | `gcp/insight_pipeline_job.py:108` |
| **Backtest** | `lib/backtest.py:BacktestEngine` for offline strategy replay; `lib/walk_forward.py` for rolling-window validation | shared backend |
| **Daily fetcher backfill** | `python -m gcp.fetchers.fetch_market_data --date YYYY-MM-DD` | `gcp/fetchers/fetch_market_data.py:12` |

#### Forbidden

- New throwaway scripts in `/tmp/` or `scripts/one_off/` that hand-roll
  bar iteration, indicator calculation, or signal scoring against
  cached CSVs.
- Mocking `_latest_overrides` or any production resolver in a script
  that won't ship — instead seed/unseed `exit_config_overrides` via
  `db-query.yml commit=true`, run the production replay, then revert.
- Using `add_all_indicators` directly in a replay script — let
  `signal_monitor.calculate_indicators` (lib/strategies + production
  glue) do it. The production indicator contract is more than just
  `add_all_indicators` (e.g. signal_monitor sets `Time` from the
  index before VWAP runs; cached CSVs don't carry `Time`).

#### Coverage gaps (as of 2026-05-10)

If your audit needs as-of replay against one of these and the flag
isn't shipped yet, add the as-of flag to the production job in a
small PR BEFORE running the audit. Don't write a throwaway harness
"just for this one investigation."

- `gcp/signal_monitor_eod_resolver.py` — only `--lookback-days N`
  from "now"; no `--date` or `EOD_AS_OF`.
- `gcp/fetchers/fetch_alphavantage_intraday.py` — only fetches "today
  minus 1"; no `--date` flag.
- Earnings / calendar / options fetchers — verify before relying on
  them for historical replay.

#### When throwaway is allowed

Only for one-shot read-only inspection that doesn't touch the
strategy / indicator / signal pipeline:
- "How many rows in `signal_alerts` for ticker X on date Y" — use
  `db-query.yml`.
- "What's the schema of `exit_config_overrides`" — use `db-query.yml`.

Anything that simulates a fire decision goes through the production
replay paths.

### 3.7. No Silent Fallbacks — Production-Grade Data Discipline

**Added 2026-05-13 after the fallback audit that found ~121 silent-failure
patterns across the codebase, six of which had documented production
incidents already attached to them — most damningly, the
`except Exception: return pd.DataFrame()` block in `gcp/database.py:88-102`
and `lib/data_loader.py:80-86` is the *same* block whose own in-line comment
diagnoses the 2026-05-04 → 05-08 `signal_alerts.level_broken = 0%` outage.
The swallow survived its own remediation PR (#339). Periodic re-audit beats
trusting "we already fixed that."**

See `docs/audits/FALLBACK_AUDIT_2026-05-13.md` for the full inventory,
incident postmortems, and remediation backlog.

#### Rule

A "silent fallback" is any code path that, on failure or missing input,
returns a numeric / empty / sentinel value the caller cannot distinguish
from a legitimate result. They lie to downstream code and conceal
bugs, stale data, and vendor outages. They are forbidden in this repo
except under the narrow conditions in **Allowed exceptions** below.

The five forbidden patterns:

1. **`except Exception: return <empty>`** in data-access code (DB, API
   clients, fetchers). Re-raise; let the caller decide retry vs.
   fail-loud. If observability is the motivation, increment a
   structured counter at the call site instead of swallowing.

2. **`fillna(0)` / `or 0` / `?? 0` / `.get(k, 0)` on financial fields.**
   Price, volume, Greeks (delta/gamma/theta/vega/rho/iv), open interest,
   sentiment scores, P&L, win rate, return %, RSI, stochK, RVOL, ATR,
   FTFC score, consecutive streaks, durations. `0` must never be
   ambiguous with "missing." Use `np.nan` / `None` / `null` end-to-end;
   the display layer renders "—" with a "data unavailable" badge.

3. **`continue-on-error: true` in fetcher workflows.** A failed fetch
   must turn the workflow red and trigger the existing
   `handle-workflow-failure.yml` reusable workflow (it opens an issue +
   draft PR automatically). Silencing the failure ships stale or
   missing rows to Cloud SQL and makes the next downstream consumer
   look like the bug source.

4. **Hardcoded financial-constant defaults** (`_DEFAULT_RISK_FREE`,
   `_DEFAULT_DIV_YIELD`, neutral RSI = 50, neutral classification = 0,
   etc.) used when a real value cannot be computed. Greeks shipped with
   wrong `r` look plausible and are silently used to make trade
   decisions — worse than no Greeks. Fail-fast `RuntimeError`;
   downstream caller (Greeks pipeline) catches it and writes NULL with
   a `last_rate_at` column for observability.

5. **External API failure returning a fabricated value instead of an
   explicit-unavailable envelope.** Vendor outages are a fact (we don't
   control AlphaVantage / FRED / ForexFactory / Yahoo / Discord), but
   the *response* must be `DataResult(status=UNAVAILABLE,
   last_known_at=..., reason=...)`, never a synthetic 0 or empty
   DataFrame. The frontend renders "data unavailable since X" badge;
   signal generators skip the affected ticker with explicit reason.

#### Rationale — `INTERNAL` vs `EXTERNAL` control

The five rules collapse into one principle. Every failure mode is one of:

- **`INTERNAL`** — code we own. A failure means there is a bug. Silencing
  it conceals the bug. Always re-raise.
- **`EXTERNAL`** — vendor API / network we don't control. We can't
  prevent the failure; we *can* detect it, surface it explicitly, and
  decide whether to skip the affected ticker / day / strategy. Always
  return a typed `UNAVAILABLE` envelope, never fabricate a value.

If you find yourself adding a `try`/`except` that returns an empty
container "just in case," stop and ask: which bucket is this? Either
answer leads away from the silent fallback.

#### Allowed exceptions

The only acceptable silent fallbacks:

- **Cleanup paths in `finally:` blocks** (e.g.
  `try: conn.close(); except Exception: pass`). The original error
  has already propagated; the cleanup catch only prevents the cleanup
  from masking the real error. Comment as `# cleanup — original
  error already propagated`.
- **Display-layer rendering of a `null` / `NaN` value as "—".** The
  fallback is in the React component, not the data layer. Required
  because the DOM cannot render `null`.
- **Test fixtures and mocks.** Tests legitimately return canned data
  on failure to exercise specific branches.

#### Forbidden phrases (rewrite the code)

If you find yourself writing any of these, the new code is wrong:

- `except Exception: return pd.DataFrame()` / `return []` / `return {}` /
  `return None` / `return 0`
- `value or 0` / `value or []` / `value or {}` on a financial field
- `df["price"].fillna(0)` / `df["delta"].fillna(0.5)` /
  `df["rsi"].fillna(50)`
- `.get("volume", 0)` / `.get("delta", 0.5)`
- `?? 0` / `?? 0.5` / `?? ''` on a financial field in TS/JS
- `continue-on-error: true` on a fetch / validation step
- `if df.empty: return df` *as the only handling* — pair with an explicit
  data-quality counter or raise
- `_DEFAULT_RISK_FREE` / any module-level "if we can't fetch, use this"
  constant on a value that has to track market reality

#### Enforcement

A new `fallback-guard` sub-agent (`.claude/agents/fallback-guard.md`)
auto-triggers on edits to `lib/**`, `gcp/**`, `platform/api/**`,
`platform/src/**`, `.github/workflows/fetch-*.yml`. It blocks PRs
that introduce any of the five forbidden patterns. It is also wired
into `/audit-review` as a gate and `/gcp-deploy` Step 0 via
`pre-deploy-check` so production cannot ship new fallbacks.

The agent is read-only — it flags and explains, it doesn't rewrite.
Reviewer judgment is required because the rule has narrow legitimate
exceptions (see above).

#### When you find an *existing* fallback while doing other work

You are not obligated to fix it in your current PR (the audit catalogues
~121 of them; remediation is staged in `docs/audits/FALLBACK_AUDIT_2026-05-13.md`
§10). But:

- **Don't pattern-match off it** when writing new code. The fact that
  `_query_cloud_sql` returns empty on error is a bug, not a contract.
- **Don't extend it** ("I'll add one more `except` to be safe"). Every
  new layer of swallowing makes the eventual fix harder.
- **Do** add a comment `# AUDIT-2026-05-13: silent fallback — see
  docs/audits/FALLBACK_AUDIT_2026-05-13.md §C-NN` if you touch a line
  adjacent to one. This makes the remediation backlog trivially
  greppable.

### 4. Testing Strategy Pattern
Follow this rigorous testing approach:

1. **Test What You Suggest**:
   - Before suggesting any code change, understand its impact
   - Write or run tests to validate your suggestions

2. **Provide Specific Feedback**:
   - Clearly state what's broken (with error messages)
   - Explain what was fixed (with specific code references)
   - Show test results proving the fix works

3. **Iterate Until Working**:
   - Run tests after each change
   - If tests fail, analyze the failure
   - Fix the issue and test again
   - Repeat until all tests pass
   - Document each iteration's findings

4. **Testing Checklist**:
   - [ ] Unit tests pass
   - [ ] Integration tests pass (if applicable)
   - [ ] No regressions in existing functionality
   - [ ] Edge cases handled
   - [ ] Error scenarios tested
   - [ ] Performance impact assessed

### 5. Code Quality Standards
- **Read before writing**: Thoroughly explore existing code before making changes
- **Extend, don't duplicate**: Add to existing modules rather than creating similar new ones
- **One place, one purpose**: Keep related functionality together in existing files
- Always run linting before committing
- Ensure TypeScript compilation succeeds (if applicable)
- Follow existing code style and patterns in the project
- Don't introduce new patterns without discussion
- Maintain or improve test coverage

### 6. Communication Protocol
- Be explicit about what you're doing at each step
- Report test results clearly with pass/fail status
- When encountering issues, provide:
  - The exact error message
  - The file and line number
  - Your analysis of the problem
  - Your proposed solution
- Ask for clarification when requirements are ambiguous

## Project-Specific Context

### Technology Stack
- Google Apps Script for spreadsheet automation
- JavaScript/TypeScript for core logic
- Yahoo Finance API integration
- Caching mechanisms for API optimization
- Continuation patterns for long-running operations

### Key Components
- Historical data backfilling system
- Yahoo API fetching with cache-first approach
- Execution continuation for Google Apps Script timeout handling
- Cloud Console logging integration
- Strat methodology (`lib/strat.py`) — candle classification (1/2U/2D/3),
  combo detection (Failed_2U/2D, RevStrat reversals, continuations),
  FTFC scoring across timeframes
- Gamma analytics (`lib/gamma.py`) — per-strike GEX, King/Gate/Spot/Flip
  taxonomy, gamma flip detection, regime classification. See
  [`docs/gamma_levels.md`](docs/gamma_levels.md) for the full reference.

### Architectural rules

- **One source of truth for math.** Per `docs/HARDCODED_VALUES_REMEDIATION.md`,
  the React app never duplicates financial math. Indicators, gamma,
  playbook conditions, trade analytics — all live in `lib/` (Python) and
  are exposed via FastAPI endpoints. The frontend consumes them.
- **`lib/` is the shared backend spine.** All three consumer surfaces
  (FastAPI router, AI agents, CLI scripts) import from the same `lib/`
  modules so behaviour can't drift.

### Sandbox network constraints (Claude Code on the web)

The Claude Code on the web sandbox enforces a strict outbound egress policy:
**only TCP port 443 is allowed.** Anything else — 5432 (Postgres), 3307
(Cloud SQL Auth Proxy backend), 22 (SSH), arbitrary TCP — silently times out
at the sandbox firewall. This is by design and **cannot be bypassed by
changing the destination's inbound ACLs, authorized networks, or VPC
peering** — the binding constraint is on the sandbox side, not the
destination's. If a connection times out, the answer is almost never "fix the
firewall" — it's "find the 443-based escape hatch for this operation."

| Operation | Mechanism | Port | Works in sandbox? |
|---|---|---|---|
| `gcloud …` (Asset, IAM, Run, SQL admin, Build, Scheduler, Logging) | REST API | 443 | ✅ |
| `gh …` (GitHub: PRs, issues, runs, workflows, secrets, releases) | REST + GraphQL API | 443 | ✅ |
| `gcloud secrets versions access` | Secret Manager API | 443 | ✅ |
| `gcloud run jobs execute` / `deploy` (job itself runs in GCP, not the sandbox) | Cloud Run control-plane API | 443 | ✅ |
| `gcloud builds submit` (build runs in Cloud Build, not the sandbox) | Cloud Build API | 443 | ✅ |
| `git push` / `git fetch` over HTTPS remotes | git-over-HTTPS | 443 | ✅ |
| `curl` / `WebFetch` to any HTTPS endpoint (incl. signed GCS URLs) | HTTPS | 443 | ✅ |
| **Direct** psycopg2 / pg8000 / SQLAlchemy → Cloud SQL | TCP | 5432 | ❌ |
| **Direct** Cloud SQL Auth Proxy → Cloud SQL backend | TCP | 3307 | ❌ |
| **Direct** `psql` → Cloud SQL | TCP | 5432 | ❌ |
| SSH to Cloud Run / Compute / IAP tunnel | TCP | 22 (or 22-over-IAP) | ❌ |
| Anything binding raw TCP outbound on a non-443 port | TCP | * | ❌ |

The two patterns documented below — `db-query.yml` for DB access, and the
PAT-via-Secret-Manager pattern for GitHub API — exist specifically to route
work over 443 for operations that would otherwise need a blocked port. The
GH Actions runner has unrestricted egress, so dispatching a workflow is the
canonical way to "run something on a real network" from inside the sandbox.

If a tool's job appears to *run in GCP* but you're calling it from the
sandbox (e.g. `gcloud run jobs execute`, `gcloud builds submit`,
`gcloud sql import`), the local CLI is just hitting the 443 control-plane
API — the actual work happens in GCP and has full network access. That's
why these work even though direct SQL on 5432 doesn't.

#### Concrete command patterns (copy-paste reference)

**Working — these all go over 443 from the sandbox:**

```bash
# ── Secrets ────────────────────────────────────────────────────────────
gcloud secrets versions access latest \
  --secret=<name> --project=adept-mountain-474619-d4

# ── Inspect GCP state ──────────────────────────────────────────────────
gcloud run jobs describe <job> --region=us-east1
gcloud run jobs list --region=us-east1
gcloud scheduler jobs list --location=us-east1
gcloud projects get-iam-policy adept-mountain-474619-d4 \
  --flatten=bindings --filter="bindings.members:serviceAccount:<email>" \
  --format="value(bindings.role)"

# ── Mutate GCP state (control-plane is 443; the work runs in GCP) ──────
gcloud run jobs execute <job> --region=us-east1 --wait
gcloud builds submit --tag us-east1-docker.pkg.dev/<project>/<repo>/<image>
gcloud projects add-iam-policy-binding <project> \
  --member="serviceAccount:<email>" --role="<role>" --condition=None

# ── Read Cloud Run / GCP logs ──────────────────────────────────────────
gcloud beta run jobs executions logs read <execution-id> --region=us-east1
gcloud logging read 'resource.type="cloud_run_job"' --limit=50 --format=json

# ── GitHub (all `gh` subcommands work) ─────────────────────────────────
gh pr view <num> --repo TeneikaAskew/stocks --json state,mergedAt
gh pr merge <num> --repo TeneikaAskew/stocks --admin --squash
gh workflow run <workflow.yml> --repo TeneikaAskew/stocks -f key=value
gh run list --repo TeneikaAskew/stocks --workflow=<wf.yml> --limit=5 \
  --json databaseId,status,conclusion,createdAt
gh run view <id> --repo TeneikaAskew/stocks --log-failed
gh run download <id> --repo TeneikaAskew/stocks --name <artifact-name> -D /tmp/x
gh secret set <NAME> --body "<value>" --repo TeneikaAskew/stocks

# ── Git over HTTPS (push/fetch/pull all work) ──────────────────────────
git fetch origin <branch>
git push -u origin <branch>
```

**Blocked — these will hang for 30-60 s and then time out. Don't debug the
firewall; use the documented escape hatch:**

| If you tried | You'll get | Use instead |
|---|---|---|
| `psql -h <cloud-sql-ip>` | timeout on 5432 | `gh workflow run db-query.yml -f sql='...'` (see [Database access](#database-access) below) |
| `psycopg2.connect(host=...)` / `pg8000.connect(...)` / `SQLAlchemy create_engine(...)` against Cloud SQL | timeout on 5432 | same — dispatch `db-query.yml`, then `gh run download` the artifact |
| `cloud-sql-proxy` / `cloud_sql_proxy <conn>` | timeout on 3307 | same — dispatch `db-query.yml` |
| `ssh user@<cloud-run-host>` | timeout on 22 | n/a — Cloud Run has no SSH. Use `gcloud beta run jobs executions logs read` (443) for inspection |
| `gcloud compute ssh <vm>` | timeout on 22 (over IAP) | for shells, switch to a desktop session; for inspection, use `gcloud compute instances describe` (443) |
| Direct `redis-cli`, `mongosh`, etc. against any GCP-hosted DB | timeout on whatever the DB port is | route the work into a Cloud Run Job (controlled via 443) or a workflow runner |

The mental rule: **if the connection target is in GCP and the port isn't 443,
you need a 443-based intermediary.** The two intermediaries this repo has
already wired up are `db-query.yml` (for ad-hoc SQL) and Cloud Run Jobs (for
anything else that needs production network access — they're triggered from
443 but execute with full GCP networking).

### Database access

> **See also: [`docs/CLAUDE_CODE_ON_WEB.md`](docs/CLAUDE_CODE_ON_WEB.md)** — the
> full field guide for working from a Claude Code on the web sandbox: the
> SessionStart bootstrap script, PAT-via-Secret-Manager pattern, GH Actions
> gotchas, MCP caveats, and the rationale behind the patterns documented
> below.

**Two paths exist:** the original `db-query.yml` GitHub Actions workflow
(documented below) and a Cloud Run Job named `db-query` (added 2026-05-30).
The two run the SAME `gcp/queries/run_query.py` so behaviour is identical;
the difference is the dispatch mechanism. Prefer the Cloud Run path when:

- GitHub Actions hosted runners are degraded
- You're already in a dispatch-via-`gcloud` workflow and don't want to
  context-switch to `gh`
- You need results in GCS (not a GH artifact) — e.g. for a downstream
  Cloud Run Job to consume

Dispatch the Cloud Run path:

```bash
gcloud run jobs execute db-query \
  --update-env-vars="^|^SQL=SELECT count(*) FROM trades|RESULT_GCS_URI=gs://${PROJECT}-trading-data/query-results/my-run/" \
  --region=us-east1 --project=adept-mountain-474619-d4 --wait
# Or with a .sql file shipped in the image:
gcloud run jobs execute db-query \
  --update-env-vars="^|^SQL_FILE=gcp/queries/audit_ticker_coverage.sql|RESULT_GCS_URI=gs://${PROJECT}-trading-data/query-results/audit/|STATEMENT_TIMEOUT_SECONDS=300" \
  --wait --region=us-east1
# Fetch results:
gcloud storage cp 'gs://${PROJECT}-trading-data/query-results/my-run/*' /tmp/results/
```

Env vars: `SQL` OR `SQL_FILE` (one required); `COMMIT=true` to persist
writes (default rollback); `STATEMENT_TIMEOUT_SECONDS=120`; `RESULT_GCS_URI`
(optional — defaults to `gs://${GCS_BUCKET}/query-results/${EXECUTION_ID}/`).
Same row caps + rollback semantics as `db-query.yml`. Artifacts written:
`results.json`, `result_NNN.csv`, `summary.md`, `summary_for_comment.md`.

Direct DB connections from Claude Code on the web sandbox are blocked: the
sandbox firewall only allows outbound TCP on port 443, and Cloud SQL needs
5432 (Postgres) or 3307 (Auth Proxy backend). Both time out. Adding the
sandbox IP to authorized networks does not help — the binding constraint is
the sandbox's outbound firewall, not the DB's inbound ACL.

To query Cloud SQL Postgres (`trading` database) from any session, dispatch
the `.github/workflows/db-query.yml` workflow. It runs the SQL inside a
GitHub Actions runner (which has unrestricted egress to Cloud SQL via the
project's existing `gcp/database.py` connector), captures structured results,
posts a phone-friendly summary as a comment on a tracking issue if specified,
and uploads the full results as a workflow artifact.

#### Invocation patterns

**Single read query** (default — transaction is rolled back, which is a no-op
for SELECT):
```bash
gh workflow run db-query.yml \
  -f sql='SELECT count(*) FROM trades WHERE date > current_date - 7' \
  -f issue_number=<TRACKING_ISSUE>
```

**Multi-statement in one dispatch** — this is the answer to "varying amounts
of queries." Batch into one dispatch instead of dispatching N times. Each
statement runs in its own transaction:
```bash
gh workflow run db-query.yml \
  -f sql='SELECT count(*) FROM trades; SELECT count(*) FROM signal_alerts; SELECT max(date) FROM market_data_daily' \
  -f issue_number=<TRACKING_ISSUE>
```

**File-based** (for SQL too large for a dispatch input or DDL with embedded
semicolons like `DO $$ ... $$` blocks or `CREATE FUNCTION ... LANGUAGE
plpgsql`):
```bash
# Commit the .sql file to gcp/queries/ first, then:
gh workflow run db-query.yml \
  -f sql_file=gcp/queries/check_freshness.sql \
  -f issue_number=<TRACKING_ISSUE>
```
The file content is sent as **one** statement. Multi-statement splitting
only happens for the inline `sql` input. For DO blocks or function
definitions, always use `sql_file`.

**Write query** (must explicitly opt in to commit):
```bash
gh workflow run db-query.yml \
  -f sql="UPDATE trades SET status='reviewed' WHERE id IN (1,2,3)" \
  -f commit=true \
  -f issue_number=<TRACKING_ISSUE>
```
Without `commit=true`, every transaction rolls back at the end. A write
without `commit=true` is a deliberate no-op — the summary will show
`↩️ rolled back` so the user knows. This is the load-bearing safety
guarantee: a typo'd UPDATE/DELETE without `commit=true` cannot persist.

#### Reading results

Each dispatch takes ~30–90 s end-to-end (queue + cold runner + connection +
query + summary). After dispatch:
```bash
sleep 5
RUN_ID=$(gh run list --workflow=db-query.yml --limit=1 --json databaseId -q '.[0].databaseId')
gh run watch $RUN_ID                                       # blocks until done
gh issue view <TRACKING_ISSUE> --comments | tail -120      # phone-friendly summary
# OR for full results:
gh run download $RUN_ID --name "query-results-$RUN_ID"
```

Artifact contents:
- `results.json` — structured per-statement results (columns, rows,
  row_count, truncated, duration_ms, mode, error, sqlstate,
  row_cap_strategy)
- `result_NNN.csv` — per-statement CSV (only for statements that returned
  rows)
- `summary.md` — full markdown summary, untruncated
- `summary_for_comment.md` — same content, hard-truncated to 60 KB for the
  issue comment

#### Inputs reference

| Input | Default | Notes |
|---|---|---|
| `sql` | `""` | Inline SQL; multi-statement separated by `;`. Exclusive with `sql_file`. |
| `sql_file` | `""` | Path to `.sql` file in repo. Sent as one statement. Exclusive with `sql`. |
| `commit` | `false` | `true` to persist writes; otherwise transaction rolls back. |
| `issue_number` | `""` | Issue # to post summary comment to. Empty → falls back to `vars.DB_QUERY_TRACKING_ISSUE`, then to artifact-only. |
| `statement_timeout_seconds` | `120` | Per-statement Postgres `statement_timeout`. |

If you create a single tracking issue once and set the repo variable
`DB_QUERY_TRACKING_ISSUE` to its number (`gh variable set
DB_QUERY_TRACKING_ISSUE -b <num>`), every dispatch posts there by default
without needing `issue_number=` each time.

#### Limits

- **Statement timeout**: 120 s default (override with
  `statement_timeout_seconds`).
- **Row cap**: 50,000 per statement in the artifact, top 50 in the issue
  comment. For single-SELECT statements the cap is enforced server-side via
  subquery wrap (`row_cap_strategy: server_limit`); for multi-statement,
  non-SELECT, or queries with `FOR UPDATE`/`FOR SHARE`/`SELECT INTO` it's
  enforced client-side via `fetchmany(50001)` (`row_cap_strategy:
  client_fetchmany`). The latter is slower for huge result sets but the
  timeout caps wall-time.
- **Issue comment**: 60 KB hard truncation (GitHub's limit is 65 KB);
  truncated comments link to the artifact.
- **Concurrency**: all dispatches serialize through one queue (group
  `db-query`) with `cancel-in-progress: false` — verified in
  `.github/workflows/db-query.yml`. A read dispatched while a write
  is in flight waits ~30–60 s for the queue.

#### Known limitation: rapid-burst dispatches

Audit 2026-05-08 G.P2.24 flagged that during multi-track audits,
dispatches fired within the same ~5 s window can show as cancelled in
the GitHub Actions UI even though `cancel-in-progress: false` is set.
This is GitHub-side queue scheduling behaviour — the workflow YAML is
correct; the cancellations are GitHub deciding multiple
queue-position-zero dispatches with the same group key collide on
intake.

Mitigation:

- For human-paced ad-hoc queries: just wait 30 s between dispatches
  (the typical run takes 30–90 s anyway, so back-to-back dispatches
  are rarely needed).
- For programmatic batch use: combine N statements into ONE dispatch
  via the `sql` input multi-statement syntax (`-f sql='SELECT 1;
  SELECT 2; ...'`) or commit a `.sql` file and pass `sql_file=`. Each
  dispatch is one workflow run; one run can execute many statements.
- For the audit-style scenario where N tracks each need to query
  Cloud SQL: stagger by track owner and rely on the queue rather
  than firing all at once.

The cancellation never causes data loss (every statement runs in its
own transaction, default rollback) — it just means a dispatched run
may not produce results when GitHub silently cancels it on intake.
Re-dispatch when that happens.

#### What not to do

- **Don't paste secrets, API keys, or passwords as SQL string literals** in
  `inputs.sql`. The `sql` input is recorded in plaintext in the workflow
  run history and is visible to anyone with **read** access to the repo.
- **Don't dispatch the workflow N times for N queries.** Batch into
  multi-statement SQL (`-f sql='SELECT 1; SELECT 2; ...'`) or commit a
  `.sql` file with the full batch and use `sql_file`. Each dispatch costs
  30–90 s.
- **Don't use this for production migrations.** For schema changes,
  `gcp/schema.sql` + `gcp/apply_schema.py` is the source of truth. This
  workflow is for ad-hoc inspection and one-off data fixes.

#### Why this exists

Phone-only sessions on Claude Code on the web cannot reach Cloud SQL on any
port (sandbox blocks all egress except 443). A GH-Actions-mediated query
workflow is the only path that works without a desktop fallback. The
runner reuses `gcp/database.py:get_engine()` and the existing
`CLOUD_SQL_CONNECTION_NAME` / `DB_USER` / `DB_PASS` / `DB_NAME` repo
secrets. Auth uses **`CLAUDE_CODE_WEB_GCP_SA_KEY`** — the same SA key
used by every other data-pipeline workflow in this repo since the
2026-05-10 consolidation. The original "web-sandbox vs data-pipeline"
key split was paranoia-tier separation that didn't buy anything in
this single-owner / single-project setup; both surfaces share blast
radius. The `claude-web@` SA holds `roles/editor` at the project
level which is sufficient for every workflow that touches GCP.

A consequence of the consolidation: a `CLAUDE_CODE_WEB_GCP_SA_KEY`
compromise now affects every workflow in this repo. Mitigations: rotate
via `gcloud iam service-accounts keys` + GitHub repo secret update;
keep the SA scoped to a single GCP project; rely on Cloud Audit Logs
for forensics. The dual-key option remains available if a future
threat model justifies the operational cost; today it doesn't.

### Backup and disaster recovery

Cloud SQL `trading-db` is moving to a 3-layer backup posture. **As of
2026-05-10**, the first two layers are live and the third is in flight
on a PR — see the status column. The doc reflects the target state so
it's ready to use the moment the third layer lands; check the status
before relying on a layer that isn't yet deployed.

| Layer | What | Retention | Recovery granularity | Status |
|---|---|---|---|---|
| **Daily PD snapshots** | Cloud SQL automated snapshots | 7 most recent | One restore point per day at ~03:00 UTC | ✅ live (always was) |
| **Point-in-time recovery (PITR)** | WAL archive | 7 days of transaction log | Any second within last 7 days | ✅ live (enabled 2026-05-10) |
| **Weekly `pg_dump`** | Logical SQL dump (gzipped) | 30 days (lifecycle rule) | Whole-DB snapshot, target Sunday 04:00 UTC | 🚧 in flight on PR #389 — `cloud-sql-weekly-export` Job + scheduler not yet deployed; `gs://${PROJECT_ID}-trading-data/sql-dumps/` is empty until then |

The first two are managed by Cloud SQL itself. The third (once PR #389
merges + `./gcp/deploy.sh setup-pg-dump-iam && ./gcp/deploy.sh build &&
./gcp/deploy.sh pg-dump && ./gcp/deploy.sh schedulers` runs) will be the
`cloud-sql-weekly-export` Cloud Run Job in `gcp/deploy.sh`
(`deploy_weekly_pg_dump` + `setup_pg_dump_iam`). The pg_dump survives
instance deletion or a region-wide GCP issue — the snapshots and PITR
don't. **Check `gs://${PROJECT_ID}-trading-data/sql-dumps/` before
relying on a pg_dump-based recovery path.**

#### When to reach for which

| Scenario | Use |
|---|---|
| `DROP TABLE` or `DELETE FROM` mistake; need to restore to 5 minutes ago | **PITR** — fine-grained, no row loss within the recovery window |
| Schema migration corrupted yesterday's data; need to restore to before the migration | **Daily snapshot** from 24h ago |
| Cloud SQL instance accidentally deleted, or a hypothetical region outage in `us-east1` | **Weekly pg_dump** (once PR #389 lands and a dump exists). Until then this scenario has NO recovery path — daily snapshots and PITR don't survive instance deletion. Treat any instance-delete operation as sev-1 until the pg_dump layer is live. |
| Audit a row's history (timestamps, who-wrote-what) | None of the above — no row-level audit log; rely on application-side write logs and `created_at` columns |

#### Restore commands (read-only reference — run with care)

```bash
# 1. List available daily snapshots
gcloud sql backups list --instance=trading-db --project=adept-mountain-474619-d4

# 2. Restore a daily snapshot into a fresh instance (preferred over
#    in-place — gives you a chance to validate before swapping)
gcloud sql backups restore <BACKUP_ID> \
    --restore-instance=trading-db-restore-test \
    --backup-instance=trading-db \
    --project=adept-mountain-474619-d4

# 3. PITR restore to a specific timestamp (creates a new instance,
#    point-in-time = anywhere in the last 7 days)
gcloud sql instances clone trading-db trading-db-pitr-test \
    --point-in-time=2026-05-09T14:30:00.000Z \
    --project=adept-mountain-474619-d4

# 4. Pull the latest weekly pg_dump and restore to a local Postgres
#    or a throwaway Cloud SQL instance.
#    NOTE: only valid once PR #389 lands and at least one dump has run.
#    Run step (a) first; an empty listing means the layer isn't live yet.
gcloud storage ls gs://adept-mountain-474619-d4-trading-data/sql-dumps/   # (a)
gcloud storage cp gs://adept-mountain-474619-d4-trading-data/sql-dumps/trading-YYYYMMDD-HHMMSS.sql.gz - \
    | gunzip \
    | psql "<connection-string-of-target-db>"
```

**Always restore to a fresh instance first**, validate, then promote.
Never run `gcloud sql import sql` directly into the live `trading-db`.

#### What is NOT backed up

- **GCS objects** under `gs://${PROJECT_ID}-trading-data/raw/` (legacy
  parquet snapshots) — these were the old shadow-copy. Slated for
  cleanup, but **do not delete this prefix until** (1) PR #389 has
  merged + deployed, (2) at least one weekly pg_dump has succeeded
  and been verified to gunzip cleanly, and (3) you've confirmed the
  parquets aren't read by anything via
  `grep -rEn "raw/" lib/ gcp/ scripts/ platform/`. Don't add new
  dependencies on this prefix in the meantime.
- **`platform/` build artifacts**, **Docker images** in Artifact Registry
  (rebuildable from source), **GitHub Actions logs / artifacts** (kept
  by GitHub, not by us).
- **Discord channel history** — Discord retains it; we don't.

#### Verifying backups are healthy

A weekly cron healthcheck would be ideal but isn't yet implemented.
Until then, on-demand:

```bash
# 1. Verify PITR is still enabled (currently live as of 2026-05-10)
gcloud sql instances describe trading-db --format='value(settings.backupConfiguration.pointInTimeRecoveryEnabled)'
# Should print: True

# 2. Verify the daily snapshot ran today (currently live)
gcloud sql backups list --instance=trading-db --limit=1 \
    --format='value(startTime,status)'
# startTime should be within last 24h, status SUCCESSFUL

# 3. Verify last pg_dump landed and is non-empty
#    (only meaningful once PR #389 is deployed; before then, empty
#    listing is expected and is NOT a healthcheck failure)
gcloud storage ls -l gs://adept-mountain-474619-d4-trading-data/sql-dumps/ \
    | sort -k2 | tail -2

# 4. Verify the latest pg_dump gunzips cleanly (integrity smoke test).
#    Same caveat — only after #389 is live.
gcloud storage cp gs://.../trading-LATEST.sql.gz - | gzip -t && echo "OK"
```

If any of the live-today checks (1, 2) fails, treat as a sev-2
incident: backups are the floor under every other safety mechanism.

### GitHub API access from the sandbox

The sandbox cannot run `gh` (not installed). To dispatch workflows, read
runs, download artifacts, or post comments via the REST API, fetch the
GitHub PAT from GCP Secret Manager and use `curl` against `api.github.com`.

The PAT lives at `projects/adept-mountain-474619-d4/secrets/gh-stocks-repo-pat`.
The `claude-web@` SA already has `roles/editor` at the project level, which
includes `secretmanager.secretAccessor` on every secret in the project, so
no per-secret IAM binding is needed.

```bash
# Fetch once per session (avoid embedding in argv where it'd land in process listings)
GH_TOKEN=$(gcloud secrets versions access latest \
  --secret=gh-stocks-repo-pat \
  --project=adept-mountain-474619-d4)

# Dispatch the db-query workflow against any branch
curl -sS -X POST \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/TeneikaAskew/stocks/actions/workflows/db-query.yml/dispatches \
  -d '{"ref":"main","inputs":{"sql":"SELECT now()"}}'

# Poll most recent run
RUN_ID=$(curl -sS -H "Authorization: Bearer $GH_TOKEN" \
  "https://api.github.com/repos/TeneikaAskew/stocks/actions/workflows/db-query.yml/runs?per_page=1" \
  | python -c "import sys,json; print(json.load(sys.stdin)['workflow_runs'][0]['id'])")

# Download the artifact (returns a ZIP)
ARTIFACT_ID=$(curl -sS -H "Authorization: Bearer $GH_TOKEN" \
  "https://api.github.com/repos/TeneikaAskew/stocks/actions/runs/$RUN_ID/artifacts" \
  | python -c "import sys,json; print(json.load(sys.stdin)['artifacts'][0]['id'])")
curl -sS -L -H "Authorization: Bearer $GH_TOKEN" \
  -o /tmp/results.zip \
  "https://api.github.com/repos/TeneikaAskew/stocks/actions/artifacts/$ARTIFACT_ID/zip"
```

**Important caveats:**
- **Workflow registration**: GitHub registers `workflow_dispatch` workflows
  only after their file lands on the **default branch** (`main`). Until
  then both `gh workflow run` and the REST API return 404. To smoke-test a
  new workflow, the file must merge to `main` first.
- **Don't pass the PAT in argv** (`-H "Authorization: Bearer ghp_xxx"`
  inline). Other processes can read `/proc/<pid>/cmdline`. Always assign
  to a shell variable first and reference via `$GH_TOKEN`.
- **Don't echo or log the PAT.** It will land in shell history and Bash
  tool transcripts visible in conversation summaries.
- **Rotation**: rotate by writing a new version to the secret; consumers
  fetch `latest` and pick up the new value transparently.
  ```bash
  read -s NEW && echo -n "$NEW" | gcloud secrets versions add gh-stocks-repo-pat \
    --data-file=- --project=adept-mountain-474619-d4 && unset NEW
  ```

### Testing Commands
```bash
# Add project-specific test commands here
# npm test
# npm run lint
# npm run typecheck
```

### GitHub Actions Workflows

This project uses GitHub Actions for automated data fetching, analysis, and system maintenance. All workflows follow consistent patterns and include automated failure handling.

#### Workflow Development Best Practices

1. **Always Include Failure Handling**
   - Every workflow MUST include the `handle-failure` job
   - This ensures issues and PRs are automatically created on failure
   - See the "Automated Workflow Failure Handling" section below for details

2. **Use Consistent Permissions**
   - Main job: `contents: write` (for git operations), `issues: write` (for reporting)
   - Failure handler: Add `pull-requests: write` and `actions: read`

3. **Implement Continue-on-Error Strategically**
   - Use `continue-on-error: true` for non-critical steps
   - Track failures with step outputs and check them in a dedicated step
   - This allows workflows to complete partially while still reporting failures

4. **Use Proper Job Dependencies**
   - Use `needs:` to chain jobs that depend on each other
   - Use `if: always()` for jobs that should run regardless of previous job status
   - Use `if: failure()` for failure handling jobs

5. **Test Workflows Locally When Possible**
   - Use `act` tool to test GitHub Actions locally: https://github.com/nektos/act
   - Test scripts independently before integrating into workflows
   - Use `workflow_dispatch` for manual testing in GitHub

6. **Label Workflows Consistently**
   - Use descriptive, unique labels for each workflow type
   - Format: `workflow-failure,<specific-workflow-type>,automated`
   - Examples: `workflow-failure,etf-options,automated` or `workflow-failure,market-data,automated`

### GitHub Issue Management
Use GitHub CLI (`gh`) to manage repository issues:

#### Setup (One-time)
If `gh` is not installed:
```bash
# Windows (PowerShell)
winget install --id GitHub.cli

# Authenticate (required on first use)
gh auth login
```

#### Common Commands
```bash
# List all open issues
"C:\Program Files\GitHub CLI\gh.exe" issue list

# List issues with specific state
gh issue list --state open
gh issue list --state closed
gh issue list --state all

# View a specific issue
gh issue view <issue-number>

# Create a new issue
gh issue create --title "Issue title" --body "Issue description"

# Close an issue
gh issue close <issue-number>

# Reopen an issue
gh issue reopen <issue-number>

# Add labels to an issue
gh issue edit <issue-number> --add-label "bug,automated"

# Search issues
gh issue list --search "error"
gh issue list --label "bug"
```

**Note for Windows**: If PATH is not updated after installation, use the full path:
```powershell
& "C:\Program Files\GitHub CLI\gh.exe" issue list
```

### Automated Workflow Failure Handling

This project uses an automated system to handle workflow failures by creating/updating GitHub issues and pull requests.

#### How It Works

When any GitHub Actions workflow fails:
1. **Issue Creation**: An issue is automatically created (or updated if one already exists) with:
   - Workflow run details (run number, URL, timestamp)
   - Failed step information
   - Last 50 lines of error logs from failed steps
   - Link to the workflow logs for full details

2. **Pull Request Creation**: A draft PR is automatically created with:
   - Branch named `fix/workflow-{workflow-name}-{run-number}`
   - Link to the related issue
   - Error summary and diagnostic information
   - Checklist for fixing the issue

3. **Duplicate Prevention**: If an issue already exists for a workflow failure:
   - No new issue is created
   - A comment is added to the existing issue with the new failure details
   - This prevents issue clutter and keeps all related failures in one place

#### Architecture

The system consists of two main components:

1. **Reusable Workflow**: [`.github/workflows/handle-workflow-failure.yml`](.github/workflows/handle-workflow-failure.yml)
   - Called by other workflows when they fail
   - Receives workflow context and failure details
   - Orchestrates the failure handling process

2. **Python Script**: [`scripts/handle_workflow_failure.py`](scripts/handle_workflow_failure.py)
   - Fetches workflow run details via GitHub API
   - Extracts error logs from failed jobs
   - Creates/updates issues and PRs
   - Handles duplicate detection

#### Workflows Using This System

All major workflows in this project use automated failure handling:
- `fetch-market-data.yml` - Daily market data updates
- `earnings-options-analytics.yml` - Analytics pipeline
- `update_economic_events_calendar.yml` - Economic calendar updates
- `fetch-economic-events-calendar.yml` - Economic events calendar fetching
- `analyze-market-data.yml` - Market data analysis
- `download-google-sheets.yml` - Google Sheets data downloads

**Important**: When creating new workflows, always add the failure handler job to ensure consistent error tracking and automated issue creation.

#### Working with Auto-Created Issues and PRs

**When a workflow fails:**

1. **Check the Issue**: Navigate to the auto-created issue to see:
   - What failed and when
   - Error logs and diagnostics
   - Link to the related PR

2. **Review the Logs**: Click through to the workflow run to see complete logs:
   ```bash
   # Or use gh CLI to view the issue
   gh issue view <issue-number>
   ```

3. **Work on the Fix**: The auto-created PR provides a branch to work on:
   ```bash
   # Checkout the auto-created branch
   git fetch origin
   git checkout fix/workflow-{name}-{run-number}

   # Make your fixes
   # Test locally

   # Push your fixes
   git add .
   git commit -m "fix: resolve workflow failure"
   git push origin fix/workflow-{name}-{run-number}
   ```

4. **Mark as Ready**: Once fixed:
   - Convert the draft PR to ready for review
   - The PR will automatically close the issue when merged

**Managing Multiple Failures:**

If a workflow fails multiple times:
- All failures are tracked in a single issue (via comments)
- Each comment includes the specific run details
- The most recent PR link is shown in the issue
- Close old PRs if the fix is consolidated into a newer one

**Using gh CLI with Auto-Created Items:**

```bash
# List workflow failure issues
gh issue list --label "workflow-failure"

# View specific workflow failures
gh issue list --label "workflow-failure,etf-options"
gh issue list --label "workflow-failure,market-data"

# List auto-created PRs
gh pr list --label "automated"

# View a specific failure PR
gh pr view <pr-number>

# Close resolved issues
gh issue close <issue-number> --comment "Fixed in PR #<pr-number>"
```

#### Adding Failure Handling to New Workflows

When creating or updating workflows, always add the failure handler job. Here's the standard pattern:

```yaml
jobs:
  main-job:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      issues: write
    steps:
      # Your workflow steps here
      - name: Your step
        run: echo "Do work"

  # Always add this failure handler job
  handle-failure:
    needs: main-job
    if: failure()
    uses: ./.github/workflows/handle-workflow-failure.yml
    permissions:
      contents: write
      issues: write
      pull-requests: write
      actions: read  # Required to read workflow run details and logs
    with:
      workflow_name: "Human-readable name"
      failure_title: "❌ Descriptive failure title"
      issue_labels: "workflow-failure,specific-label,automated"
      workflow_file: "workflow-filename.yml"
      run_id: ${{ github.run_id }}
      run_number: ${{ github.run_number }}
      run_url: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
      event_name: ${{ github.event_name }}
      branch: ${{ github.ref }}
      commit_sha: ${{ github.sha }}
      create_pr: true  # Set to false to skip PR creation
```

**Key Points:**
- The `handle-failure` job must have `needs: main-job` (or whatever your main job is called)
- Use `if: failure()` to trigger only on failure
- Always include `actions: read` permission for log access
- Use descriptive, unique labels for each workflow type
- Set `create_pr: false` if you only want issue creation without a PR

#### Troubleshooting

**If failure handling itself fails:**
- Check the "handle-failure" job in the workflow run
- Verify `GITHUB_TOKEN` permissions are set correctly
- Ensure `scripts/handle_workflow_failure.py` is accessible
- Check that `requests` library is installed (in `requirements.txt`)

**If logs aren't being captured:**
- The script fetches logs via GitHub API
- Logs are limited to last 50 lines of errors
- Full logs are always available via the workflow run link

**If duplicate issues are created:**
- The system checks for open issues with matching labels
- Ensure label names are consistent in workflow configurations
- Check that the issue search is working correctly

## Example Workflow

1. User requests a feature
2. **READ AND SEARCH**: Explore all related existing files first
3. Identify if changes can be made to existing files
4. Use TodoWrite to create a detailed plan
5. Present plan for approval (mentioning which existing files will be modified)
6. Upon approval, create feature branch
7. Implement changes incrementally (preferring edits to existing files)
8. Test each change thoroughly
9. Report test results
10. Fix any issues found
11. Repeat testing until all passes
12. Commit with proper message (no Claude branding)
13. Create PR if requested

## Remember
- Quality over speed
- Test everything you change
- Communicate clearly and frequently
- Follow the existing patterns in the codebase
- When in doubt, ask for clarification