# 01 — Security Scan (whole repo)

**Result: 0 critical / 2 medium / 4 low.** Nothing externally
exploitable. Scope: `gcp/`, `lib/`, `platform/api/`, `platform/src/`,
`scripts/`, `tradingview-pine-scripts/`, `.github/workflows/`,
`.claude/`, `.env.example`, plus git-history spot checks. Excluded
`node_modules/`, `.venv/`, `data/`, `dist/`, `__pycache__/`.

## MEDIUM

### M1 — No technical control stops a secret pasted into ad-hoc SQL from being logged

- `gcp/queries/run_query.py:178` — `out['sql'] = stmt` is written
  verbatim into `results.json` / `summary.md` under
  `gs://<project>-trading-data/query-results/<exec>/`.
- `scripts/db_query_cr.sh:81,88` passes raw SQL as a
  `gcloud run jobs execute --update-env-vars=DB_QUERY_SQL=...`
  argument, which Cloud Audit Logs record as part of the API call.

**Correction to the review brief:** `gcp/db_query_job.py:107` does
*not* log full SQL at INFO — it logs a char count
(`--sql=<%d chars>`). So the exposure surface is Cloud Audit Logs and
the GCS artifact, not stdout. Same practical risk; the brief's stated
mechanism was wrong.

Exploitability requires `roles/run.viewer` / Logging Viewer / Storage
read — internal blast radius only, no anonymous path. CLAUDE.md already
documents the operator rule ("don't paste secrets into SQL"); this is
the observation that nothing *enforces* it.

**Fix:** regex reject in `run_query.py` before execution, or tighten
`roles/storage.objectViewer` on the `query-results/` prefix.

### M2 — Pervasive `SELECT *` (data minimization)

47 occurrences across 24 files, most on user-facing paths:

- `platform/api/routers/earnings.py` — 8 (lines 219, 238, 270, 295, 309+)
- `platform/api/routers/dashboard.py` — 2
- `platform/api/routers/signals.py:127` — 1 (inner subquery)
- `lib/data_loader.py:556,615`
- `gcp/database.py`, `gcp/trade_logger.py`, `gcp/premarket_brief.py`,
  `gcp/refresh_earnings_views.py`, `gcp/research/**`

Every column added to `trades`, `earnings_ticker_lean`,
`earnings_options_strategy_*` is silently serialized to API consumers.

**Fix:** enumerate columns explicitly, prioritizing
`platform/api/routers/*` where results go straight into an HTTP
response.

## LOW

### L1 — Non-constant-time admin token comparison
`platform/api/routers/admin.py:74` —
`if not x_admin_token or x_admin_token != expected:`
Timing side-channel; low real-world exploitability over HTTPS + Cloud
Run jitter. **Fix:** `hmac.compare_digest`.

> **VERIFIED BY CLAUDE:** read `admin.py:70-76` directly — exact match.

### L2 — Token in `run:` argv in a retired workflow
`.github/workflows/fetch-market-data.yml.disabled:77` —
`curl -s -H "Authorization: token ${{ github.token }}"`.
Inert (GitHub never executes `.yml.disabled`) and uses the ephemeral
per-run token, not a PAT. Flagged only so the pattern isn't copied if
the file is ever revived.

All three **live** workflows (`backtest-pipeline.yml`,
`handle-workflow-failure.yml`, `refresh-architecture-docs.yml`) pass
tokens correctly via `env:` blocks — no argv leakage in anything that
runs.

### L3 — CI log dump committed into the workflows directory
`.github/workflows/logs.txt` — 442 lines of captured Actions log for the
retired `fetch-market-data` workflow. **No secrets present** (runner-side
masking already replaced the token with `***`; re-verified with a pattern
scan for ALPHAVANTAGE/API_KEY/SECRET/TOKEN/PASSWORD/WEBHOOK/AIza/ghp_/
sk-/postgres:// — zero hits). Housekeeping, not a leak.
**Fix:** `git rm .github/workflows/logs.txt`.

> **VERIFIED BY CLAUDE:** `git ls-files` confirms it is tracked;
> `wc -l` confirms 442 lines.

### L4 — Broad exception handling (counted, not itemized)
`except Exception:` — gcp/ 56, lib/ 23, platform/ 36, scripts/ 23
(140 across 65 files). Bare `except:` — 1
(`scripts/match_earnings_strategy.py`). Not evaluated individually for
Rule 3.7 here; that is report 02's job. Several are the explicitly
allowed `finally`-block cleanup pattern.

## Clean

- No `debug=True` in `gcp/` or `platform/api/`.
- No `eval(` / `exec(` / `subprocess(shell=True)` / `pickle.load(`
  anywhere in scope.
- No `.env`, `.gcp-key.json`, or `service-account*.json` tracked in git.

## False positives explicitly ruled out

- **f-string SQL in `gcp/database.py:529,545-547,605,614` and
  `gcp/research/strat_engine/*`** — every caller passes a hardcoded
  literal for `table`; column lists derive from `df.columns` intersected
  against the live schema via `MetaData().reflect()`, so a column name
  can't smuggle SQL. Not reachable from any external request, and
  identifiers can't be parameterized anyway.
- **`gcp/discord_interactions/main.py:650`** — `col_sql` built from a
  fixed 3-5 literal whitelist; the only Discord-supplied value
  (`ticker`) is bound via `:t` and validated with `isalnum()` at :612.
  `execute_cloud_run_job()` uses the structured `RunJobRequest`/`EnvVar`
  client API, not a shelled-out `gcloud` — no command-injection path.
- **Router f-strings** (`signals.py:115,126,306,351`,
  `earnings.py:218,270,295`, `backtest.py:447`, `grid.py:965`) — splice
  only pre-validated structural fragments (WHERE-clause lists from
  literals, ORDER BY from a fixed `Literal[...]`); all values bound.
- **`lib/data_loader.py:538,556,615`** — `table` from a 2-way literal
  ternary, never the raw `source` string.
- **`gcp/deploy.sh` `_env_string()` :459-478** — `CLOUD_SQL_CONNECTION_NAME`
  and `DB_USER` in `--set-env-vars` is intentional and documented
  (connection name and the literal role label aren't sensitive). All
  real secrets route through `--set-secrets`. *(See report 04 — three
  genuine exceptions to this were found there.)*
- `BEGIN PRIVATE KEY` in `docs/CLAUDE_CODE_ON_WEB.md:102` — `<redacted>`
  placeholder.
- `apiKey: 'AIzaSyFAKE-key-for-tests-...'` in `platform/tests/*.spec.ts`
  — fake fixture, fake since first commit (`git log -S` confirmed).
