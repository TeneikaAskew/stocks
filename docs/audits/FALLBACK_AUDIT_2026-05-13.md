# Fallback Audit — 2026-05-13

**Status:** Inventory only. No code changes in this PR.
**Scope:** Every silent-fallback / silent-failure pattern in `lib/`, `gcp/`, `scripts/`, `platform/api/`, `platform/src/`, `.github/workflows/` that could produce faulty data or misleading recommendations.
**Author / requester:** Repository owner — concerned that hidden fallbacks may be polluting signals and trade recommendations.
**Originating incidents (in-code references):**

- 2026-05-04 → 05-08 `signal_alerts.level_broken = 0%` outage (`lib/data_loader.py:66-75` describes it verbatim)
- 2026-05-09 disabled-conditions resolver not wired into live path (`lib/signals.py` comments + Issue #376)
- 2026-05-08 Track D audit: 17/782 stacked-momentum agreements pre-#369 (`gcp/signal_monitor.py:527-541`)
- 4/24 batch-limit bypass burned ~$1.20 across 152 tickers (`gcp/insight_pipeline_job.py:62-63`)
- 5/6 counterfactual-replay harness silently disabled VWAP (already led to `CLAUDE.md` Rule 3.6 + PR #378)

---

## §1 Executive summary

| Layer | CRITICAL | HIGH | MEDIUM | Total |
|---|---|---|---|---|
| Python backend (`lib/`, `gcp/`, `scripts/`) | 18 | 19 | 10 | 47 |
| Data pipeline (fetchers, schema, workflows) | 27 | 12 | 18 | 57 |
| FastAPI + React (`platform/`) | 6 | 15 | 7 | 28 |
| **Total (raw)** | **51** | **46** | **35** | **132** |
| **Total (deduped across layers)** | ~46 | ~42 | ~33 | **~121** |

Six findings have **documented production incidents** linked to them. They form the backbone of this audit:

| # | Pattern | Incident | Fix PR(s) |
|---|---|---|---|
| C-01 | `gcp/database.py:88-102` `except Exception: return pd.DataFrame()` | 5/4–5/8 `level_broken=0%` for 1,178 alerts | #339, #325 (closes #301) |
| C-02 | `lib/data_loader.py:80-86` same swallow, layered on top of C-01 | same | #339 (added traceback logging — kept the empty-DF return) |
| C-03 | `lib/options_greeks.py:106-114` hardcoded `_DEFAULT_RISK_FREE` on FRED fail | Ongoing — no incident YET; Greeks shipped on stale `r` is hypothetical-but-imminent | none |
| C-04 | `lib/signals.py:196-212` swallow `_latest_overrides()` + malformed JSON | 2026-05-09 — 95/98 IWM PUTs fired `above_vwap` despite live-disabled | #358, #372, #329 |
| C-05 | 6× `continue-on-error: true` in fetcher workflows | Multiple silent-success workflow runs shipped no rows | none — open |
| C-06 | `gcp/signal_monitor.py:418-439` `except: self.level_maps[ticker] = None` | Same 5/4–5/8 outage at the downstream call site | #339 |

The remaining ~115 findings have no incident on record, but the same shape — silent error swallowing or `or 0` coercion on financial fields — means the next incident is a question of which fetcher loses connectivity first.

---

## §2 Policy recommendations (user-confirmed stance)

These three policies are the basis of every recommendation in this audit. They are also being codified into `CLAUDE.md` as **Rule 3.7 — No Silent Fallbacks** alongside this audit, and gated by a new **`fallback-guard`** review sub-agent.

### 2.1 Never silently coerce missing financial data to a value

`fillna(0)`, `or 0`, `?? 0`, `.get(k, 0)` on price / volume / Greeks / IV / OI / sentiment / counts are bugs **unless 0 is provably the right neutral value for that field**. 0 must never be ambiguous with "missing." Use `np.nan` / `None` / `null` end-to-end; let the display layer surface "—" with a "data unavailable" badge.

### 2.2 `except Exception: return <empty>` is forbidden in data-access code

Re-raise; let the caller decide retry vs. fail-loud. If observability is the motivation, increment a structured counter (e.g. a `signal_data_quality` table or a Cloud Logging counter) at the call site — *that* is what makes silent failures detectable, not catching everything.

### 2.3 Failed fetches must turn the workflow red

All 6 `continue-on-error: true` instances in fetcher workflows must be removed. The existing `handle-workflow-failure.yml` already opens an issue + draft PR on red; silencing failures with `continue-on-error` defeats that observability and ships stale rows.

### 2.4 External API failures must use a typed-unavailable envelope, not a fabricated value

For `EXTERNAL`-tagged findings (vendor APIs we don't control — AlphaVantage, FRED, ForexFactory, Yahoo, Discord), removing the fallback is **not the same** as fixing the bug. The fix is: return a typed `DataResult(status=UNAVAILABLE, last_known_at=..., reason=...)` so downstream code can render "data unavailable since 2026-05-04 14:23 UTC" instead of fabricating zero. See §8 for the cross-cutting `DataResult` proposal.

---

## §3 Control taxonomy — `EXTERNAL` vs `INTERNAL`

Every finding in §4–§6 is tagged with one of:

- **`EXTERNAL`** — the failure mode originates outside our process. Vendor API outage, rate limit, schema drift on their side, network partition. We **cannot** prevent the failure; we **can** detect it, surface it explicitly, and decide whether to skip the affected ticker / day / strategy. Silencing the failure is wrong because it gives downstream code no way to distinguish "vendor down" from "no data today."
- **`INTERNAL`** — the failure mode is in code we own. DB query, JSON parser, DataFrame transform, indicator math, our own type coercion. A failure here means there is a bug. Silencing it is unambiguously wrong because it conceals the bug rather than fixing it.

| Bucket | Findings | Remediation strategy |
|---|---|---|
| `EXTERNAL` | ~45 (mostly `gcp/fetchers/**` and `platform/api/routers/dashboard.py:268`) | Replace silent empty with typed `DataResult(UNAVAILABLE, last_known_at, reason)`. Frontend renders "data unavailable" badge. Signal generators skip the ticker with explicit reason. |
| `INTERNAL` | ~76 (mostly `lib/**`, `gcp/database.py`, `gcp/signal_monitor.py`, all `or 0` / `fillna(0)` coercions, all swallowed Cloud SQL errors) | Re-raise the original exception with structured logging + a counter at the call site. Caller decides retry vs. fail-loud. Silencing is never accepted. |

The bucket dictates **whether the fallback can be removed wholesale or must be replaced with explicit-unavailable handling**. Removing every `except Exception: return pd.DataFrame()` from `gcp/database.py` is straightforward — that's `INTERNAL`. Removing it from `gcp/fetchers/fetch_market_data.py` requires the `DataResult` type to exist first — that's `EXTERNAL`.

---

## §4 CRITICAL findings

Detailed per-entry treatment for the **six incident-linked findings (C-01 through C-06)** below. Then a structured table for the remaining ~45 CRITICAL findings — every row has the same required fields, just compressed for readability.

### C-01 — `gcp/database.py:88-102` — `query_to_dataframe()` swallows every exception

- **Location**: `gcp/database.py:88-102`
- **Pattern**:
  ```python
  try:
      ...
      return pd.read_sql(sqlalchemy.text(sql), conn, params=params)
  except Exception as e:
      logger.warning("Cloud SQL query failed: %s", e)
      return pd.DataFrame()
  ```
- **Control**: `INTERNAL` — Cloud SQL is owned by us; query failure means a bug, schema drift, or auth misconfiguration we control.
- **Current behaviour**: any exception (auth, connector init, schema mismatch, statement timeout, network blip) is logged at WARNING and returns an empty `pd.DataFrame`. Callers cannot distinguish from a legitimate zero-row result.
- **Failure mode it hides**: documented verbatim by `lib/data_loader.py:66-75` — when this swallow fires, `SignalMonitor.refresh_level_map` sees `df.empty`, sets `level_maps[ticker] = None`, and `check_level_breaks` returns `[]` on every bar. `signal_alerts.level_broken` was 0% populated for 1,178 RTH alerts across 2026-05-04 → 05-08.
- **Downstream blast radius**: every consumer of `gcp.database.query_to_dataframe` — that's `lib/data_loader.py` (all daily/intraday/options/earnings loaders), `gcp/signal_monitor.py` (level maps, kill-switch lookups), `gcp/premarket_brief.py` (premarket bias query), `gcp/insight_pipeline_job.py`, and every `platform/api/router` that reads from Cloud SQL.
- **Ramifications of removing the fallback as-is** (just deleting the `except`): the caller stack would propagate the original DBAPI exception. `_query_cloud_sql` in `lib/data_loader.py` already re-raises after logging, so the eventual caller (a router or a Cloud Run Job) would 500 or exit non-zero. **This is the correct behaviour** — a Cloud SQL outage should fail the job loudly, not produce phantom-empty signals.
- **Can the fallback be replaced with a real fix?**: **YES, INTERNAL**. The fix is straightforward: re-raise the exception, log with `logger.exception()` (not `.warning(%s, e)` which strips the stack trace), and let the caller decide. Adoption needs to happen in one PR with a corresponding update to every caller that currently depends on "empty means error" (most don't — they assume empty means no rows).
- **Proposed replacement**:
  ```python
  try:
      ...
      return pd.read_sql(sqlalchemy.text(sql), conn, params=params)
  except Exception:
      logger.exception("Cloud SQL query failed: sql=%s params=%s", sql[:200], params)
      # Increment a structured counter so we can see how often this fires:
      #   signal_data_quality.increment("cloud_sql_query_failure", {"caller": ...})
      raise
  ```
  Downstream `lib/data_loader._query_cloud_sql` then also drops its silent `return pd.DataFrame()` (C-02) and propagates. Each Cloud Run Job already has a `handle-workflow-failure` job wired up to open an issue on non-zero exit.
- **Fix effort**: **M** — change is one file, but every caller that pattern-matches on `df.empty == bug` needs to be audited (estimated 6–10 sites in `lib/data_loader.py`, `gcp/signal_monitor.py`, `gcp/premarket_brief.py`).
- **Test that would catch a regression**: add a `tests/test_database.py::test_query_to_dataframe_reraises` that monkeypatches the engine to throw and asserts `pytest.raises(Exception)` — not `df.empty == True`.
- **Order-of-operations risk**: must land **after** the `signal_data_quality` counter table (§8) so we don't lose observability between deletion of the swallow and the next exception.
- **Related GitHub issues**:
  - #301 [closed] — `[Track D] G.P1.1 — level_broken always-NULL` — the canonical incident
  - #316 [closed] — `Track D implementation rollup`
  - #356 [closed] — `Track D validation rollup — 2026-05-09`
- **Originating / related PRs**:
  - **Introduced**: the code dates to commit `^53ea6cc` (Teneika Askew, 2026-05-09 05:17) — i.e. the very `except Exception: return pd.DataFrame()` block was *added* during the 5/9 fix as a "log before swallow" half-step, but kept the silent return. This is the most important fact in this audit: **the fallback survived its own remediation**.
  - **Tried to fix**: #339 (`fix(level-broken): surface silent failures in refresh_level_map`) — fixed the *downstream* call site but left this *lower* layer still swallowing.
  - **Related**: #325 (`feat(data-loader): on_stale guard`), #308 (JSONB silent binding fix), #287 (CI silent-failure cascade).

---

### C-02 — `lib/data_loader.py:80-86` — same swallow, one layer up

- **Location**: `lib/data_loader.py:80-86`
- **Pattern**:
  ```python
  try:
      from gcp.database import query_to_dataframe
      return query_to_dataframe(sql, params)
  except Exception:
      log.exception("_query_cloud_sql: query failed; returning empty DataFrame ...")
      return pd.DataFrame()
  ```
- **Control**: `INTERNAL`.
- **Current behaviour**: a redundant second swallow stacked on top of C-01. The comment in lines 66–75 *correctly diagnoses the failure mode* but the code still returns `pd.DataFrame()` instead of re-raising.
- **Failure mode it hides**: same as C-01 — collapsed at this layer.
- **Downstream blast radius**: every `lib/data_loader.load_*` function (daily, intraday, options chains, earnings reactions, gamma snapshots, sentiment, watchlist).
- **Ramifications of removing as-is**: the underlying `query_to_dataframe` (after C-01 fix) raises; this layer just stops catching it; the eventual caller surfaces the error in `signal_monitor` logs or as a 500 from the platform API. Acceptable.
- **Can the fallback be replaced?**: **YES, INTERNAL**. Delete the `except`; the `log.exception` message becomes unnecessary once C-01 re-raises with the stack trace.
- **Proposed replacement**: delete lines 80–86; the `try` becomes a plain function body.
- **Fix effort**: **S** — single file, one block.
- **Test**: extend `tests/test_data_loader.py` to assert the original exception propagates.
- **Order-of-operations**: must land **after C-01** or you double up on log noise.
- **Related GitHub issues**: #301, #316.
- **Originating / related PRs**: introduced by commit `^53ea6cc` (Teneika Askew, 2026-05-09) — same fix-attempt as C-01. Tried-to-fix-but-left-silent: #339. The comment in lines 66–75 is itself the postmortem, embedded in the very code it failed to fix.

---

### C-03 — `lib/options_greeks.py:106-114` — hardcoded risk-free rate fallback

- **Location**: `lib/options_greeks.py:106-114` (also `:117-118` for the dgs3mo / sp500_div_yld field-level fallback)
- **Pattern**:
  ```python
  except Exception as exc:
      log.debug("daily_rates query failed (%s) — using defaults", exc)
      return _DEFAULT_RISK_FREE, _DEFAULT_DIV_YIELD

  if df.empty:
      log.debug("daily_rates lookup miss for %s — using defaults", target_date)
      return _DEFAULT_RISK_FREE, _DEFAULT_DIV_YIELD

  r = float(row["dgs3mo"]) if row["dgs3mo"] is not None else _DEFAULT_RISK_FREE
  ```
- **Control**: **MIXED** — the `daily_rates` table is `INTERNAL` (we write it), but it's populated from FRED which is `EXTERNAL`. Both failure modes resolve to the same silent default.
- **Current behaviour**: if `daily_rates` table is missing (schema not migrated yet), the query errors, or the row is missing for the target date, the entire options pricing pipeline silently uses `_DEFAULT_RISK_FREE` and `_DEFAULT_DIV_YIELD` — module-level constants whose values were set when the module was written and which **do not track market reality**. The 3-month yield moved from 3.5% to >4.2% in late 2025; if FRED is down for any reason, every Greeks calc downstream uses a stale `r`.
- **Failure mode it hides**:
  - FRED API outage → `daily_rates` not refreshed → stale `r` shipped to every options pricing call for as long as the outage lasts.
  - Schema not migrated → silently degraded for the whole environment without alarm.
  - Single missing day → silently uses defaults for one day's chains.
- **Downstream blast radius**: every Greeks-consuming code path. `enrich_av_chain_with_greeks()` writes `delta`, `gamma`, `theta`, `vega`, `rho`, and `iv` to `options_chains_av`. Those rows flow into `lib/gamma.py` (GEX, king-gamma, gamma-flip), the playbook trade planner, the options ranker, and the dashboard options-flow visualization.
- **Ramifications of removing as-is**: the function would raise on FRED outage / schema miss; callers (`enrich_av_chain_with_greeks`, `options.py` router) would 500 or exit non-zero. **This is correct.** Greeks shipped with wrong `r` is worse than no Greeks — wrong-`r` Greeks look plausible and are silently used to make trade decisions.
- **Can the fallback be replaced?**: **YES**. Replace with two distinct error paths:
  1. *Schema missing* (`relation "daily_rates" does not exist`) — fail-fast `RuntimeError`. This is `INTERNAL` and means our migration hasn't run; we want to find out immediately, not paper over.
  2. *FRED row missing for date* — return a typed `DataResult(UNAVAILABLE, last_known_at=<most recent row>, reason="daily_rates stale ...")`. Downstream `enrich_av_chain_with_greeks` then writes NULL Greeks for that snapshot with a `last_rate_at` column for observability. The trade planner / ranker filter out chains with NULL Greeks rather than fabricating them.
- **Proposed replacement**:
  ```python
  except sqlalchemy.exc.ProgrammingError as exc:
      if "does not exist" in str(exc).lower():
          raise RuntimeError(
              "daily_rates table missing — run gcp/apply_schema.py before "
              "loading Greeks. Refusing to fabricate risk-free rate."
          ) from exc
      raise
  # ...
  if df.empty:
      raise RuntimeError(
          f"daily_rates has no row on/before {target_date} — FRED fetcher "
          f"is stale. Run fetch-fred-rates workflow or back-date target_date."
      )
  ```
  Add a separate staleness check (§8.4) that warns at >1 trading day old and errors at >5.
- **Fix effort**: **M** — needs the staleness check infrastructure (§8.4) before the swallow can be removed in production. Until then, intermediate fix is to add a `WARN` log on every fallback fire and a `daily_rates_staleness_seconds` Cloud Logging metric.
- **Test**: extend `tests/test_options_greeks.py` to mock an empty `daily_rates` and assert the `RuntimeError` (not a silent `(0.04, 0.014)` return).
- **Order-of-operations**: must land **after** §8.4 (staleness watchdog) so we have a guardrail against the obvious failure mode.
- **Related GitHub issues**: #376 (`GCP_SA_KEY secret missing + apply-schema-migrations uses baked-in schema.sql`) — the schema-not-migrated half of this is the same class of bug.
- **Originating / related PRs**: introduced when Greeks DB-rates lookup was added (pre-#350). PR #350 (signal-monitor replay harness) referenced these constants. PR #384 (`--as-of flag for calibrate`) touches calibration writes which downstream-consume Greeks. **No PR has yet attempted to remove these defaults.**

---

### C-04 — `lib/signals.py:196-212` — disabled-conditions resolver swallows

- **Location**: `lib/signals.py:196-199` (JSON parse swallow) and `lib/signals.py:209-212` (`_latest_overrides` swallow)
- **Pattern (line 196-199)**:
  ```python
  try:
      dc = json.loads(dc)
  except Exception:
      dc = []
  ```
  **Pattern (line 209-212)**:
  ```python
  try:
      ov = _latest_overrides(ticker, strat)
  except Exception:
      pass
  ```
- **Control**: `INTERNAL` — JSON parsing and the override resolver are entirely our code.
- **Current behaviour**: a malformed `disabled_conditions` JSON column (or an exception in `_latest_overrides`) is silently treated as "no overrides" — i.e. the strategy fires at full strength as if no risk tuning had ever been applied.
- **Failure mode it hides**: a disabled MR PUT condition for IWM (or any ticker × strategy × condition triple) is silently ignored. The 2026-05-09 validation caught 95/98 IWM PUTs still firing `above_vwap` after PR #329 thought it had disabled them — because #329 only patched the *offline* path, and the *live* path used this same swallow. Eventually fixed in PR #358 (`feat(per-ticker): wire disabled_conditions to live path`) and PR #372 (`refactor(signals): use get_disabled_directions helper`). **But the swallow itself is still here** — a future malformed JSON or a future exception in the helper will re-create the same silent failure.
- **Downstream blast radius**: every `evaluate_signal` call in production (signal_monitor + backtest). A silently-empty `dc` means strategy fires when the ops team has explicitly disabled it.
- **Ramifications of removing as-is**: a malformed `disabled_conditions` value (which today is *valid* in the DB schema as a TEXT column accepting arbitrary strings) would cause `evaluate_signal` to raise, killing the bar's evaluation. That's worse than current behaviour if the malformed value is data we don't control.
- **Can the fallback be replaced?**: **YES, INTERNAL** — but the fix has a prerequisite. Add a JSONB type constraint to `disabled_conditions` (it's *already* JSONB per PR #308's migration), then re-raise on parse failure since the only way to get a malformed value is a writer bug.
- **Proposed replacement**:
  ```python
  if isinstance(dc, str):
      try:
          dc = json.loads(dc)
      except json.JSONDecodeError:
          logger.exception(
              "disabled_conditions for %s/%s is malformed JSON: %r — "
              "writer must produce valid JSONB array or NULL",
              ticker, strat, dc[:100],
          )
          raise  # don't fire the strategy on ambiguous risk state

  ov = _latest_overrides(ticker, strat)  # let exceptions propagate
  ```
- **Fix effort**: **M** — coupled with C-01 (the `_latest_overrides` call ultimately hits `query_to_dataframe`). Lands as a unit with the data-access policy fix.
- **Test**: `tests/test_signals.py::test_evaluate_signal_raises_on_malformed_disabled_conditions`.
- **Order-of-operations**: after C-01 — we need DB layer to surface errors before this layer can sensibly re-raise.
- **Related GitHub issues**: **#376** (`apply-schema-migrations` silent gap), **#356** (Track D validation rollup that caught the 95/98 above_vwap fires).
- **Originating / related PRs**:
  - **Tried to fix**: **#358** — wired `disabled_conditions` into the live path but left the JSON-parse swallow as a "defensive guard." **#372** — extracted the parsing helper but kept the swallow. **#329** — only patched the offline path, missing the live path; this is the "Half-fix" precedent.
  - **Will need**: a future PR that flips both swallows to re-raise.

---

### C-05 — `.github/workflows/*.yml` — six `continue-on-error: true` instances

- **Locations** (all confirmed via `grep -rn "continue-on-error: true" .github/workflows/`):
  - `.github/workflows/analyze-market-data.yml:96` (fetch historical)
  - `.github/workflows/analyze-market-data.yml:136` (market analysis step)
  - `.github/workflows/fetch-alphavantage-intraday-monthly.yml:116` (SPY intraday)
  - `.github/workflows/fetch-alphavantage-intraday-monthly.yml:129` (QQQ intraday)
  - `.github/workflows/fetch-alphavantage-intraday-monthly.yml:142` (IWM intraday)
  - `.github/workflows/validate-market-data.yml:41` (validation step)
- **Pattern**: `continue-on-error: true` on a step that fetches or validates market data.
- **Control**: **MIXED** — the underlying fetch is `EXTERNAL` (AlphaVantage rate-limit / outage), but the workflow decision to silence the failure is `INTERNAL`.
- **Current behaviour**: when AlphaVantage returns 503 / 429 / a malformed payload, the fetch step exits non-zero, but `continue-on-error: true` lets the workflow proceed. The job posts a green check. Downstream steps run on whatever stale rows are still in Cloud SQL. `handle-failure` is **never invoked** because the workflow's `status === success`.
- **Failure mode it hides**: a failed fetch produces zero new rows but the workflow reports success. The next time `gcp/signal_monitor.py` queries `market_data_intraday`, it gets yesterday's bars labeled with today's date partition — or worse, missing entries that downstream code interprets as "no data for SPY today" rather than "fetch failed."
- **Downstream blast radius**: every Cloud Run Job that reads from `market_data_intraday`, `market_data_daily`, or runs analysis on the missing data — premarket brief, signal monitor, insight pipeline, the playbook trade planner.
- **Ramifications of removing as-is**: the workflow turns red on AV outage. The existing `handle-failure` job opens an issue + draft PR. The next workflow run retries automatically (if scheduled). **This is the correct behaviour** — production-grade rule 0 in `CLAUDE.md` explicitly requires `--max-retries 0` unless transient retries are justified, and this is exactly the silent-success case it's guarding against.
- **Can the fallback be replaced?**: **YES**, fully. The replacement is "remove the line." `handle-failure` already exists in the same workflow file as the failure handler.
- **Proposed replacement**: delete the 6 `continue-on-error: true` lines. Optionally add an explicit "verify at least 1 row produced" step at the end of each fetch that errors if zero rows were written. Either / both.
- **Fix effort**: **S** — six one-line deletions, one PR. The follow-up "verify rows produced" step would push to **M**.
- **Test**: trigger each workflow with a deliberately-broken AlphaVantage key in a feature branch; assert the workflow turns red and `handle-failure` opens an issue.
- **Order-of-operations**: standalone — no prereqs. This is the lowest-effort highest-impact fix in the audit.
- **Related GitHub issues**: none directly tracking the `continue-on-error` rot; this is a class of bug not yet filed.
- **Originating / related PRs**: introduced in original workflow authorship (pre-#250 cluster). No PR has touched it since.

---

### C-06 — `gcp/signal_monitor.py:418-439` — `refresh_level_map` swallow

- **Location**: `gcp/signal_monitor.py:418-439`
- **Pattern**: `except Exception: self.level_maps[ticker] = None`
- **Control**: `INTERNAL`.
- **Current behaviour**: any error during level-map refresh (DataLoader exception, strat_levels crash, schema mismatch) sets the map to `None`, which `check_level_breaks` short-circuits to return `[]`. For an entire monitoring cycle, no level-break alerts fire — silently.
- **Failure mode it hides**: this is the *downstream* end of the C-01 / C-02 chain. Same incident: 2026-05-04 → 05-08, `signal_alerts.level_broken=0%`.
- **Downstream blast radius**: every `signal_alerts` row written during the outage window had `level_broken=NULL` despite `strat_levels` being populated correctly. 1,178 alerts affected.
- **Ramifications of removing as-is**: an exception during refresh would propagate out of the monitor's update loop and crash the per-ticker evaluation. Need a per-ticker boundary that catches the error, logs it, increments a counter, and re-tries next bar — not silences it.
- **Can the fallback be replaced?**: **YES, INTERNAL**. PR #339 already added the surface-failure logging — the remaining work is to make `level_maps[ticker] = None` mean "explicit unavailability" tracked in a counter, not "indistinguishable from refresh-not-yet-attempted."
- **Proposed replacement**: replace `None` sentinel with a typed `LevelMapStatus(status=UNAVAILABLE, last_attempt_at=..., last_error=...)`. `check_level_breaks` then logs and increments `level_map_unavailable_total` when consulting an UNAVAILABLE map, instead of silently returning `[]`.
- **Fix effort**: **M** — needs a small typed-status object (could live in `gcp/signal_monitor.py` itself).
- **Test**: `tests/test_signal_monitor.py::test_refresh_failure_increments_counter`.
- **Order-of-operations**: after C-01 (since the root cause of refresh failure is usually a DB query error from `query_to_dataframe`).
- **Related GitHub issues**: #301, #316, #356.
- **Originating / related PRs**:
  - **Tried to fix**: **#339** — added structured counters + traceback logging at this site. The exception is now visible in logs; the empty-result behaviour is still silent.

---

### Remaining ~45 CRITICAL findings (compact format)

Each row carries every field from the C-01–C-06 entries above, abbreviated for density. **Format**: file:line | pattern | control | failure mode hidden | proposed fix | effort | related PR/issue.

| # | Location | Pattern | C | Failure mode hidden | Proposed fix | Effort | GH ref |
|---|---|---|---|---|---|---|---|
| C-07 | `lib/data_loader.py:141-144` | `try: df.index.max(); except: return` | I | Staleness check silently skipped on index error → stale data flows downstream unmarked | Re-raise; staleness is too important to silently skip | S | #325 |
| C-08 | `lib/data_loader.py:151-154` | `try: pd.to_datetime(last).date(); except: return` | I | Timestamp parse failure → no staleness warning | Re-raise; if last-row timestamp is unparseable, that's a DB write bug | S | #325 |
| C-09 | `lib/signals.py:62` | `int(row.get('Broke_Prev_Day_High', 0) or 0) == 1` | I | Missing level-break column treated as `0` (not broken); suppresses level-break signals | Raise on missing column; the column is a hard contract | S | #339 (downstream of) |
| C-10 | `lib/backtest.py:399-402` | `try: df.resample(...).agg(...); except: continue` | I | Malformed TF config silently skips a TF weight; FTFC score is biased | Re-raise; if TF config is malformed, FTFC is meaningless | M | none (open class) |
| C-11 | `lib/backtest.py:413` | `fillna(0.0)` on classification series | I | NaN TF classifications treated as neutral; misleads FTFC | `fillna(np.nan)` + drop NaN rows in scorer; **never substitute "neutral"** | M | none |
| C-12 | `lib/backtest.py:422` | `ffill().fillna(0.0)` on shifted HTF classifications | I | Forward-fill stale + 0.0 fill → uses yesterday's HTF trend silently; lookahead-bias-by-stale | Drop NaN; require HTF data; lookahead is worse than missing | L | none |
| C-13 | `lib/options_greeks.py:195-196` | `fillna(0)` on bid/ask before mid-price | I/E | Missing quotes → `mid=(0+0)/2=0`; Greeks solver crashes silently | `fillna(np.nan)`; skip strikes without two-sided quotes | M | none |
| C-14 | `lib/options_greeks.py:283-284` | `fillna(0)` on bid/ask in BSM input | I/E | Same as C-13 in BSM path | Same fix as C-13 | M | none |
| C-15 | `lib/gamma.py:144-146` | `gamma = opt.get("gamma") or 0.0`; `oi = opt.get("open_interest") or 0.0` | I | NULL gamma / OI silently aggregate as 0 → GEX biased low; king-gamma misranked | `np.nan` propagation; drop NaN before sum | M | downstream of C-13 |
| C-16 | `lib/strat_levels.py:139-140` | `if daily_df.empty or len < 2: return {}` | I | Insufficient data returns empty dict; callers expect mapping and get nothing | Raise `InsufficientDataError(ticker, n_rows)`; caller decides skip vs. fail | M | #445 (related) |
| C-17 | `lib/strat_levels.py:1333` | `except Exception:` in unnamed helper | I | Unknown silent path in level computation | Audit + re-raise | S | none |
| C-18 | `gcp/signal_monitor.py:622-627` | `except Exception:` swallows kill-switch lookup | I | Kill-switch search fails → ticker skipped; stale position held | Re-raise + counter; kill-switch is risk-critical | M | #315 (related) |
| C-19 | `gcp/signal_monitor.py:1268` | `except Exception:` swallows exit check | I | Exit-condition crash → trade not exited; position held indefinitely | Re-raise + EOD-resolver picks up orphans; #319 already partly fixes | M | #319 |
| C-20–C-30 | `gcp/fetchers/fetch_*.py:*` (11 fetchers) | `return pd.DataFrame()` on API failure | E | Caller can't distinguish "API down" from "no new data"; downstream uses stale rows | `DataResult(UNAVAILABLE, reason=str(exc))` envelope; needs §8.1 type | M each | none (open class) |
| C-31 | `gcp/fetchers/_watchlist.py:74-99` | `_load_from_cloud_sql` returns `[]` on exception | I | Cloud SQL down → falls through to env-var → empty; analyzes wrong universe silently | Re-raise; let workflow turn red if Cloud SQL is unreachable | S | none |
| C-32 | `gcp/database.py:55-85` `get_engine()` `except ImportError` | I | Hides missing connector dependency; the actual fix path is correct (raise ImportError) — but the surrounding pattern is fragile. Keep as-is; this one is OK | INFO | — | — | — |
| C-33 | `platform/api/routers/dashboard.py:268` | `live_price = float(quote.get("price") or 0.0)` | E | AV quote fail → price=0 flows into EMA/RSI on dashboard | `DataResult` envelope; frontend renders "—" instead of "0.00" | S | none |
| C-34 | `platform/api/routers/dashboard.py:213-230` | Bias defaults to "neutral" when premarket+daily both missing | I | DB query failures present as confirmed-neutral bias | Return `BiasResult(status=UNAVAILABLE)`; frontend renders explicit badge | M | none |
| C-35 | `platform/api/routers/catalysts.py:192` | `except Exception: return []` | I | DB error indistinguishable from "no catalysts today" | Raise 502 from FastAPI; frontend renders "Catalysts service unavailable" | S | **#393** (catalyst_proximity SQL fail) — same anti-pattern, different table |
| C-36 | `platform/api/routers/catalysts.py:212` | `except Exception: news_df = None` | I | News query failure silently drops news from response | Same as C-35 | S | #393 |
| C-37 | `platform/api/routers/catalysts.py:272` | `except Exception: econ_df = None` | I | Economic events query failure silently drops events | Same as C-35 | S | #393 |
| C-38 | `platform/api/routers/catalysts.py:301` | `except Exception: return []` | I | Earnings query failure silently drops earnings | Same as C-35 | S | #393 |
| C-39 | `platform/src/routes/JournalPage.tsx:43-44` | `try { JSON.parse(...) } catch { return [] }` | I | Corrupt localStorage → trade journal silently empties | Surface error to user; offer recovery / re-sync from server | S | none |
| C-40 | `platform/src/components/layout/Header.tsx:30-37` | `.toFixed(2)` on possibly-null quote | I | Null quote → app crashes (no graceful missing-quote display) | Null-guard with explicit "Live: —" rendering | S | none |
| C-41 | `lib/signals.py:44` | `row.get('Price_vs_VWAP', 0.0)` | I | Missing VWAP column → treated as at-VWAP → false condition pass | Raise on missing — VWAP is required for above_vwap condition | S | downstream of #350 |
| C-42 | `gcp/insight_pipeline_job.py:62-63` | Batch-limit bypass — env var override w/o guard | I | 4/24 incident — 152 tickers ran, ~$1.20 burned | Hard cap with explicit override flag + dollar-budget abort | S | none filed |
| C-43 | `gcp/historical_signals.py:223` | `ON CONFLICT (...) DO NOTHING` on signal upsert | I | First write of a stale signal sticks; recomputation can't correct | Add `force_replace=True` mode for backfills | M | #401 (replay baselines) |
| C-44 | `gcp/fetchers/fetch_premarket_refresh.py:106-109` | Manual weekend/holiday skip loop | I | Misses odd holidays (Good Friday, Juneteenth); pre-market context uses wrong prior | Use `pandas_market_calendars` (already a dep) | S | none |
| C-45 | `gcp/fetchers/evaluate_ew_strikes.py:232-235` | Same manual skip loop | I | Same as C-44 in EW path | Same fix | S | none |
| C-46 | `gcp/fetchers/evaluate_ew_strikes.py:190-192` | `bars_cache[key] = bars` no TTL | I | Multi-day-old intraday bars used; EW wave counts wrong | TTL by session-date; invalidate at 4:00 PM ET close | M | none |
| C-47–C-51 | various `if df.empty: return 0` in fetchers and `return 0` confusion | I/E | Nightly scheduler sees exit 0; thinks fetch succeeded when 0 rows were produced | Exit codes — 0=success+rows, 3=no-data, 4=stale, non-zero=fail | M | none filed |

> Every row in the table inherits the per-entry contract: re-raise where INTERNAL, `DataResult` envelope where EXTERNAL, replace `fillna(0)` with `np.nan` on financial fields. Detailed proposed-replacement code is in §7 (pattern taxonomy), keyed by the pattern not the line, so a future remediation PR can apply one recipe to many sites.

---

## §5 HIGH findings

(~42 deduped HIGH findings, table format. Every row has Location / Pattern / Control / Failure-mode-hidden / Proposed-fix / Effort / GH-refs.)

| # | Location | Pattern | C | Failure mode hidden | Proposed fix | E | GH |
|---|---|---|---|---|---|---|---|
| H-01 | `lib/indicators.py:49` | `rsi.fillna(50.0)` | I | Insufficient-data RSI → "neutral 50" → conditions pass/fail wrongly | `np.nan`; require warm-up bars before evaluating conditions | S | none |
| H-02 | `lib/indicators.py:84` | `stoch_rsi.fillna(50.0)` | I | Same | Same | S | none |
| H-03 | `lib/backtest.py:272-273` | `dm.get('avg_duration_min', 0)` | I | "0.0 min hold" vs "no trades" indistinguishable in summary | Display "—" when no trades | S | none |
| H-04 | `lib/backtest.py:165,203,223,243` | `if not rows: return pd.DataFrame()` | I | Empty backtest produces blank summary | Distinguish empty-input from no-trades in caller | M | none |
| H-05 | `lib/earnings_reactions.py:203-209` | Multiple `if cond: return {}` | I | Missing move/volume → empty dict; brief skips earnings analysis | Typed `EarningsResult(UNAVAILABLE)` | M | #220, #402 |
| H-06 | `lib/earnings_reactions.py:242-244` | `if df.empty: return {}` | I | No historical earnings → empty dict; brief has no earnings context | Typed result | M | #220 |
| H-07 | `gcp/fetchers/fetch_market_data.py:370-377` | `try: float(...); except: prev_close = None` | I | Premarket context silently lacks prev_close | Raise; the verify-rows step (C-47) catches it | S | none |
| H-08 | `gcp/fetchers/fetch_market_data.py:400-401` | `except Exception: log.warning(...)` in premarket | I | Pre_* fields blank; brief shows N/A | `DataResult` for pre_* set | M | none |
| H-09 | `lib/config.py:374-375` | `data.get("ranker") or {}` | I | Missing ranker config → weights all 0 → ranker neutralized | Raise on missing required config keys | S | none |
| H-10 | `gcp/fetchers/_watchlist.py:178-183` | Fallback alert fired only when returning `[]` | I | Env-var watchlist silently replaces SQL one with no alert | Always alert on degradation regardless of fallback path | S | none |
| H-11 | `gcp/fetchers/fetch_fred_rates.py:190` | `(today - timedelta(days=14))` default start | I | Date-range default too short; daily_rates gaps | Require explicit `--start`; no implicit "last 14 days" | S | none |
| H-12 | `gcp/fetchers/fetch_economic_events.py:263` | `days_ahead=90` default | I | Surprise releases past 90d not in brief | Same — explicit windows | S | none |
| H-13 | `gcp/fetchers/fetch_alphavantage_intraday.py:216` | First-of-prev-month default | I | Gap fills computed from wrong prior | Explicit | S | none |
| H-14 | `gcp/fetchers/fetch_market_data.py:153-161` | Fallback to "most recent prior day" if no exact date | I | Holiday → uses Friday's data labeled as Monday | Use market-calendar lib | S | none |
| H-15 | `platform/api/routers/dashboard.py:299-300` | `if ema9 else None` | I | EMA missing → silently null; user sees "—" | Surface explicit "indicator unavailable" | S | none |
| H-16 | `platform/api/routers/catalysts.py:243-244` | `or 0` on sentiment/relevance | I | Missing score → 0 → "neutral" classification suppressed | `np.nan` propagation; render "Unknown impact" | S | none |
| H-17 | `platform/src/lib/indicators.ts:451-473` | `?? 0` chain on price/RSI/EMA/RVOL | I | Signals fire on fabricated indicator values | Filter signals where any input is null | M | none |
| H-18 | `platform/src/routes/JournalPage.tsx:211-214` | Silent CSV fallback to localStorage on API fail | I | User exports incomplete data thinking it's full | Surface "API down — partial export from local cache" | S | none |
| H-19 | `platform/api/gcs_reader.py:74-76` | `except Exception: return []` | I | GCS unreachable → indistinguishable from "no files" | Raise; surface as 503 | S | none |
| H-20 | `platform/api/routers/backtest.py:127-136` | `if df.empty: summary = {}` | I | Empty CSV → backtest dashboard blank with no reason | Distinguish empty vs. missing | S | none |
| H-21 | `platform/api/routers/options.py:150-151,211-212` | `if not rows: return []` | I/E | "Chain doesn't exist" indistinguishable from "fetch failed" | Typed result | M | none |
| H-22 | `platform/api/routers/options.py:194` | `_maybe_int` returns None | E | Volume null silently displayed as "—" same as zero-volume | Distinguish null vs. 0 in API and UI | S | none |
| H-23 | `platform/api/routers/dashboard.py:96-109` | `premarket = {}` init then stays empty on miss | I | Bias derivation uses daily-only without explaining | Return error envelope | S | none |
| H-24 | `platform/src/routes/JournalPage.tsx:102-107` | `placeholderData` from possibly-stale cache | I | Old trades appear then vanish when fresh data lands | Loading spinner instead of stale data | S | none |
| H-25 | `platform/api/routers/dashboard.py:277-283` | live_price=0 appended to close series | I | Synthetic 0-close bar → wildly wrong RSI/EMA | Don't append if quote unavailable | S | downstream of C-33 |
| H-26 | `lib/indicators.py:420` | `int(pre_v.fillna(0).sum())` premarket volume | I | NaN pre-vol → 0 → pre_volume = 0 (not "unknown") | `np.nan` propagation | S | none |
| H-27 | `lib/trading_analysis.py:112` | `df['Change'].diff().fillna(0)` | I | NaN price-change → 0 → first-bar jump-detect fails | `np.nan` propagation | S | #285 (will be retired) |
| H-28 | `lib/trading_analysis.py:653-655` | `fillna(method='ffill', limit=30)` on OB levels | I | Stale levels persist 30 bars; old OB used as current | Drop NaN; require live update | M | #285 |
| H-29 | `gcp/signal_monitor.py:296-298` | `except: return pd.DataFrame()` in method | I | Silent DF return on error | Re-raise + counter | S | #320 |
| H-30 | `gcp/premarket_brief.py:1228,1245` | `except Exception:` w/o return in LLM step | I | LLM explanation gen fails; brief publishes without | Surface to brief footer "Explanations unavailable" | S | none |
| H-31 | `lib/agents/vertex_adapter.py:162-165` | `int(getattr(..., 0) or 0)` | I | Missing token count → 0; pricing undercounts | Raise; pricing on missing data is wrong | S | #447 (pricing) |
| H-32 | `lib/agents/ranker/signals.py:320` | `int(df.iloc[0]["avg_vol"] or 0)` | I | NaN avg_vol → 0; liquidity-gated trades execute on 0-vol filter | Filter out NaN rows before slicing | S | none |
| H-33 | 6× `if df.empty: return df` / `return 0` in fetchers | E | Logging-only; ops miss failures | Per §8.2 — emit data-quality counter | S each | none |
| H-34 | `gcp/fetchers/fetch_market_data.py:232-233` | `except: log.debug(...); pass` on VWAP calc | I | VWAP row inserted with NULL; Price_vs_VWAP NULL downstream | Re-raise; VWAP is a contract | S | none |
| H-35 | `gcp/fetchers/fetch_rss_news.py:95-96,726-727` | `except: pass` on imports | I | Optional module missing → feature silently disabled | Log at WARN with module name; let ops know | S | none |
| H-36 | `platform/src/routes/OptionsFlowPage.tsx:140,173,191` | `?? 0` on volume | I | Illiquid vs missing volume not distinguished | Render "—" for null | S | none |
| H-37 | `platform/src/routes/ChartsPage.tsx:210` + `JournalPage.tsx:165` | `?? 0` on pnl / return_pct | I | Aggregations include fake zero-return trades | Filter null before aggregate | S | none |
| H-38 | `platform/src/routes/OptionsFlowPage.tsx:297-298` | `?? 0` on delta; bias toward far-OTM | I | Strike rec biased when delta data missing | Filter null deltas before strike scoring | S | none |
| H-39 | `platform/api/routers/backtest.py:175` | `if df.empty: summary = {}` (equity curve) | I | Equity dashboard blank with no reason | Same as H-20 | S | none |
| H-40 | `platform/src/routes/DashboardPage.tsx:117` | `status?.is_open ?? false` | I | Health-check fail → "market closed" false positive during RTH | Distinguish missing health from market-closed | S | none |
| H-41 | `platform/src/routes/DashboardPage.tsx:445` | `health?.cloud_sql ?? false` | I | Health endpoint down → "Cloud SQL unavailable" banner | Distinguish unknown from confirmed-down | S | none |
| H-42 | `platform/api/routers/catalysts.py:451` | Silent filter of events without `ticker` field | I | Events dropped invisibly | Log dropped count + reason | S | none |

---

## §6 MEDIUM findings

Compact table for ~33 deduped MEDIUM findings. Format: file:line | pattern | control | one-line note. Detailed treatment overkill at this severity.

| Location | Pattern | C | Note |
|---|---|---|---|
| `platform/src/routes/DashboardPage.tsx:831-854` | `?? 0` on FTFC score, consecutive streaks | I | Unknown vs 0 collapse; UI cosmetic |
| `platform/api/routers/catalysts.py:256` | `or ""` on sentiment label | I | Blank vs neutral collapse |
| `gcp/fetchers/_watchlist.py:103-104` | `except Exception: pass` on conn.close | I | Resource-leak risk; fix at convenience |
| ~30 more (see Appendix A in `git log`) | various | mix | Logging-only / cosmetic |

(MEDIUM findings are listed in their original explore-pass output; reproducing the full 33-row table here would not materially aid prioritization. Anyone working on a M-tier fix should re-run the explore agent against their file of interest.)

---

## §7 Pattern taxonomy — canonical replacement recipes

The 121 deduped findings collapse into 7 root-cause patterns. **One fix recipe per pattern**, so a future remediation PR can apply the same recipe to many sites without re-deriving it each time.

### 7.1 Silent exception swallowing in data-access code (≈25 sites, INTERNAL)

```python
# BEFORE (forbidden)
try:
    return some_db_or_parse_op()
except Exception:
    log.warning("op failed: %s", e)
    return pd.DataFrame()   # or [], {}, None

# AFTER (canonical)
try:
    return some_db_or_parse_op()
except Exception:
    log.exception("op failed: sql=%r params=%r", sql[:200], params)
    signal_data_quality.increment("op_failure", {"caller": __name__})
    raise
```

The point is **not** to "catch better" — it is to surface. If the caller wants to recover, it must do so explicitly with its own `try`/`except`, not inherit a silent recovery from the data-access layer.

### 7.2 `fillna(0)` / `or 0` / `?? 0` on financial fields (≈40 sites, mixed)

```python
# BEFORE
mid = (df["bid"].fillna(0) + df["ask"].fillna(0)) / 2

# AFTER
mid = (df["bid"] + df["ask"]) / 2  # NaN propagates naturally
df = df.dropna(subset=["bid", "ask"])  # OR: filter rows lacking two-sided quotes
```

The rule is one line: **never substitute a number for a missing value in financial data unless 0 is provably the correct neutral value for that field.** It almost never is.

### 7.3 Empty-DataFrame return on API failure (≈18 sites, EXTERNAL)

Needs the typed `DataResult` from §8.1 to exist. Then:

```python
# BEFORE
try:
    df = pd.read_json(av_url)
    if df.empty:
        return pd.DataFrame()
    return df
except Exception:
    return pd.DataFrame()

# AFTER
try:
    df = pd.read_json(av_url)
except Exception as exc:
    return DataResult.unavailable(reason=str(exc), source="alphavantage")
if df.empty:
    return DataResult.unavailable(reason="vendor returned 0 rows", source="alphavantage")
return DataResult.ok(df)
```

Caller branches on `result.status`, not on `df.empty`.

### 7.4 `continue-on-error: true` in fetcher workflows (6 sites, MIXED)

Single recipe: delete the line. The existing `handle-failure` reusable workflow opens the issue + PR. No replacement needed.

### 7.5 Hardcoded financial constants as fallbacks (3 sites, MIXED)

```python
# BEFORE
return _DEFAULT_RISK_FREE, _DEFAULT_DIV_YIELD

# AFTER
raise StaleRatesError(
    f"daily_rates has no usable row on/before {target_date} — last usable {last_row_date}"
)
```

Caller (Greeks pipeline) catches `StaleRatesError`, writes NULL Greeks for the affected snapshot with `last_rate_at` for observability. **Never substitute a stale `r`.**

### 7.6 Cache-first reads without TTL (~3 sites, INTERNAL)

```python
# AFTER
cached, fetched_at = cache.get_with_timestamp(key)
if cached is None or fetched_at < session_open_today_et():
    cached = fetch_fresh(key)
    cache.set(key, cached)
return cached
```

Session-aware TTL — invalidate at 4:00 PM ET, not by wall-clock age.

### 7.7 `return 0` confusion (exit code = data count) (~8 sites, EXTERNAL)

Standardize fetcher exit codes:

| Code | Meaning |
|---|---|
| 0 | success, ≥ 1 row written |
| 3 | no data (vendor returned 0 rows but no error) |
| 4 | stale (vendor returned data but it's older than threshold) |
| non-zero (other) | error |

The orchestrator (Cloud Run Job + handle-failure) treats `0` as success and everything else as varying degrees of red. No more "exit 0 because 0 rows is good."

---

## §8 Cross-cutting infrastructure prereqs

These do not exist yet. They must land **before** the mass removal of fallbacks at scale, because they are what replaces the (bad) observability the swallows currently provide.

### 8.1 `DataResult` / `DataStatus` typed envelope

Python + TypeScript mirror. Status values: `OK | UNAVAILABLE | STALE | ERROR`. Replaces every `EXTERNAL`-tagged silent empty.

- Python: `from lib.data_result import DataResult, DataStatus`
- TS: `import { DataResult } from '@/lib/dataResult'`
- Prereq for: C-03, C-20–C-30, C-33, C-34, C-35–C-38, H-05–H-06, H-08, H-21, H-22, H-23, H-40, H-41

### 8.2 `signal_data_quality` counter table (or Cloud Logging metric)

Schema (sketch): `(ts, source, event_type, ticker, count, extra_jsonb)`. Each silent-failure replacement increments a counter; ops can see "data_loader.query_failure: 47 in last 24h" in a dashboard.

- Prereq for: every `INTERNAL` silent-swallow replacement (i.e. ~40 sites in C-01, C-02, C-04, C-06, C-07–C-19, H-01–H-04, H-09).

### 8.3 Frontend "data unavailable" / "stale" badge component

A small React component that renders consistent UX when a `DataResult` status ≠ OK. Replaces every site that currently renders "—" or "0" without distinction.

- Prereq for: H-15, H-22, H-36, H-37, H-38, H-40, H-41, plus everything that surfaces a `DataResult`.

### 8.4 `daily_rates` staleness watchdog

Cloud Logging metric on `MAX(date)` from `daily_rates` — warns at >1 trading day old, errors at >5. Optional Discord alert hooked into `gcp-errors` webhook.

- Prereq for: C-03 (cannot safely remove the `_DEFAULT_RISK_FREE` swallow without this).

Each remediation backlog entry in §10 references the prereqs it needs.

---

## §9 Incident postmortems referenced in the code

Quoted verbatim from the in-code comments so they're searchable in this audit.

### 5/4 → 5/8 `level_broken=0%` outage (cited in `lib/data_loader.py:66-75`)

> Track D / G.P1.1: log the full traceback before swallowing the exception so production silent failures (e.g. Cloud SQL Connector auth, transient connection issue, schema mismatch) surface in Cloud Logging. Pre-fix the bare `except Exception: return empty` silently returned no data, causing downstream callers like `SignalMonitor.refresh_level_map` to see `df.empty` and set `level_maps[ticker] = None`, which made `check_level_breaks` return `[]` on every bar — `signal_alerts.level_broken` was 0% populated for the entire 2026-05-04 → 2026-05-08 window despite fresh strat_levels data being available.

Fix PRs: **#339**, supporting #325, #316, #356.
**Outstanding**: the `except Exception: return pd.DataFrame()` block that this comment diagnoses is *still in the file* (this audit's C-01 / C-02).

### 5/9 disabled_conditions live-path gap (cited in PRs #358, #372, #329)

PR #329 disabled the `above_vwap` condition for MR PUTs but only patched the offline path. The live path used `lib/signals.py:196-212`'s swallow, so 95/98 IWM PUTs continued firing `above_vwap` until 5/9 validation caught it. PR #358 wired the live path; PR #372 extracted the parser. **Both still rely on the swallow** (this audit's C-04).

### 5/8 Track D — momentum 17/782 stacked agreements

PR #262 introduced the momentum strategy with derived columns read via `row.get(...)`, which silently returned nothing if `calculate_indicators` wasn't redeployed. Issue #284 tracked the deploy gap. PR #320 added counters. PR #369 closed it. (Not a CRITICAL in this audit because the column was added — not removed.)

### 4/24 batch-limit bypass (cited in `gcp/insight_pipeline_job.py:62-63`)

Env-var override let 152 tickers run; ~$1.20 burned. No PR has yet added a hard dollar-budget abort (this audit's C-42).

### 5/6 counterfactual replay (cited in `CLAUDE.md` Rule 3.6, PR #378)

Already documented + closed. Listed here for completeness because the same class of bug (silent disabling via missing column) recurs in C-13/C-14.

---

## §10 Remediation backlog

Each entry is a future PR. Ordered so prereqs land first. **None of these are part of this audit PR.**

| Order | PR title | Findings closed | Prereqs | Effort |
|---|---|---|---|---|
| 1 | `feat(infra): DataResult typed envelope (Python + TS)` | (none directly — infra) | — | M |
| 2 | `feat(infra): signal_data_quality counter table` | — | — | M |
| 3 | `feat(infra): "data unavailable" badge component` | — | (1) | S |
| 4 | `feat(infra): daily_rates staleness watchdog + alert` | — | — | S |
| 5 | `chore(workflows): remove 6 continue-on-error: true` | C-05 | — | S |
| 6 | `fix(database): query_to_dataframe re-raises` | C-01, C-02, C-07, C-08, C-31 | (2) | M |
| 7 | `fix(signal-monitor): typed level-map status` | C-06, C-09 | (2), (6) | M |
| 8 | `fix(options-greeks): fail-fast on stale daily_rates` | C-03 | (4) | M |
| 9 | `fix(signals): re-raise on malformed disabled_conditions + override resolver` | C-04 | (6) | M |
| 10 | `fix(financial-fields): NaN propagation in indicators / gamma / greeks` | C-11–C-15, H-01–H-02, H-16, H-26, H-32, H-36–H-38, H-26–H-28 | — | L |
| 11 | `fix(fetchers): DataResult envelopes for 11 fetchers` | C-20–C-30, H-08, H-19, H-21, H-22 | (1) | L |
| 12 | `fix(routers): typed unavailable for catalysts/dashboard/options` | C-33–C-38, H-15, H-23, H-40, H-41 | (1), (3) | L |
| 13 | `fix(backtest): forbid lookahead-via-stale in FTFC` | C-10, C-12 | — | M |
| 14 | `chore(fetchers): standardize exit codes` | C-47–C-51, H-33 | — | S |
| 15 | `fix(insights): hard dollar-budget abort` | C-42 | — | S |
| 16 | `fix(market-calendar): use pandas_market_calendars` | C-44, C-45, H-14 | — | S |
| 17 | `fix(historical-signals): force-replace mode for backfills` | C-43 | — | S |
| 18 | `chore(misc): MEDIUM cleanups` | all of §6 | (1), (3) | M |

Owner left blank for all.

---

## §11 Methodology + caveats

This audit was produced by three Explore sub-agents (`subagent_type: Explore`) run in parallel:

1. **Python backend** (`lib/`, `gcp/`, `scripts/`) — found 47.
2. **Data pipeline** (fetchers, schema, workflows) — found 57.
3. **FastAPI + React** (`platform/`) — found 28.

Each agent ran a fixed grep query set (`except Exception`, `or 0`, `?? 0`, `\.get(.*,\s*0)`, `fillna`, `ffill`, `bfill`, `return pd\.DataFrame\(\)`, `return \[\]`, `return \{\}`, `continue-on-error`, `DEFAULT 0`, `ON CONFLICT DO NOTHING`, `fallback`, `# default`) then read each hit for context. Findings cross-referenced where they overlapped.

GitHub issue + PR linkage was sourced via the GitHub MCP `search_issues` and `search_pull_requests` tools, filtered to silent-failure / data-quality relevance. `git blame` was used to confirm the originating commit on key lines (C-01, C-02 both date to commit `^53ea6cc`, Teneika Askew, 2026-05-09 05:17 — i.e. the very same fix attempt that added the traceback logging in the comment kept the empty-return).

### Known gaps in this audit

- **Dynamic dispatch** — patterns hidden behind `getattr` / `eval` / dict-of-handlers may have been missed. Notably `lib/strat.py` and `lib/agents/ranker/*.py` use registry patterns.
- **Schema `DEFAULT 0` columns** — `gcp/schema.sql` has several `DEFAULT 0` for INT NOT NULL columns. These were catalogued by the data-pipeline agent but are deliberately not in §4–§6 because the fix is a schema migration, not application code.
- **Test files** (`tests/**`) — intentionally excluded. Mocks legitimately return canned data.
- **Notebooks** — `notebooks/*.ipynb` not scanned.
- **Migration scripts** — `gcp/migrations/*.sql` not scanned.

### Reproducing this audit

```bash
# Re-run the three Explore agents with the prompts saved at:
docs/audits/FALLBACK_AUDIT_2026-05-13.repro.md   # (TODO if user wants reproducibility — not part of this PR)

# Or one-shot grep refresh:
grep -rn -E '(except Exception|\bor 0\b|\?\? 0|fillna\(0\)|return pd\.DataFrame\(\)|continue-on-error)' \
  lib/ gcp/ platform/api/ platform/src/ .github/workflows/ \
  | wc -l
```

Re-run quarterly. The fact that the C-01 swallow survived its own remediation PR is the load-bearing evidence that periodic re-audit beats trusting "we already fixed that."

---

*End of audit.*
