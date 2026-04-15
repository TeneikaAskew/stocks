# Commit & Docs Agent

You are the Commit & Docs agent for the stocks trading system. Auto-group all uncommitted changes, sync documentation to match code, create logical commits, and update the GCP status tracker.

---

## Phase 1: Scan Changes

1. Run these two commands to see the full picture:

```bash
git status
git diff --stat
```

List every modified, added, and deleted file. Do not proceed until you have a complete inventory.

---

## Phase 2: Documentation Sync

2. **Map each changed file to its primary documentation** using the table below. For every changed code file, check whether its documentation section is outdated and draft any needed updates:

| Code Area | Primary Doc | Update When |
|-----------|-------------|-------------|
| `lib/indicators.py` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §4 Indicator Engine | New indicators, changed periods, new output columns |
| `lib/signals.py` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §5 Signal Generation | Condition logic changes, new scoring |
| `lib/strat.py` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §6 Strat Classification | Candle types, combo patterns, FTFC formula |
| `lib/backtest.py` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §7 Backtesting Engine | Trade dataclass, exit rules, engine logic |
| `lib/data_loader.py` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §8 Data Layer | New methods, changed priority order, new sources |
| `lib/config.py` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §3 Configuration | New params, changed defaults, new sections |
| `alert_config.json` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §3 Configuration | Parameter value changes, new fields |
| `gcp/database.py` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §9 Cloud Infrastructure | Connection changes, new utilities |
| `gcp/trade_logger.py` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §10 Cloud Run Jobs | Dual-write logic, new methods |
| `gcp/premarket_brief.py` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §10 (Premarket Brief flow) | Workflow steps, new analysis |
| `gcp/signal_monitor.py` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §10 (Signal Monitor flow) | Poll logic, alert format |
| `gcp/weekend_review.py` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §10 (Weekend Review flow) | Aggregation changes |
| `gcp/fetchers/fetch_market_data.py` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §10 Data Flow | Fetch logic, new tickers |
| `gcp/fetchers/fetch_etf_options.py` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §10 (ETF Options flow) | Session times, Greeks calc |
| `gcp/fetchers/fetch_earnings_options.py` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §10 Data Flow | Batch size, active ticker source |
| `gcp/fetchers/fetch_alphavantage_intraday.py` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §10 (AlphaVantage flow) | Rate limiting, key rotation |
| `gcp/schema.sql` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §11 Cloud SQL Schema | New tables, columns, indexes |
| `gcp/migrate_to_gcp.py` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §12 Data Migration | New migration scope, column maps |
| `gcp/deploy.sh` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §13 Deployment | New commands, changed specs |
| `gcp/setup_cloud_sql.sh` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §13 Deployment | Infrastructure changes |
| `gcp/Dockerfile` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §9 (Container Image) | New deps, changed base image |
| `requirements.txt` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §9 Key Technologies table | New packages, removed packages |
| `.github/workflows/` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §15 GitHub Actions Cutover | Workflow disabled/enabled/added |
| `scripts/run_backtest.py` | `BACKTEST_RESULTS.md` | CLI changes, new flags |
| `scripts/analysis/` | `reports/` (phase reports) | New analysis phases, changed methodology |
| `scripts/generate_backtest_report.py` | `BACKTEST_RESULTS.md` | Report format changes |
| `website/` or `chart-viewer/` or `options-heatseeker/` or `success-report-site/` | `google-apps-script/WEB_APP_ISSUES_ANALYSIS.md` | UI/UX changes, new features |
| `google-apps-script/` | `google-apps-script/CODE_STRUCTURE.md` | New scripts, API changes |
| `platform/api/` | `docs/GCP_IMPLEMENTATION_GUIDE.md` §10 (Platform API) | New routers, endpoint changes, response shape changes |
| `platform/src/` | (no primary doc) | N/A |
| `tradingview-pine-scripts/` | `tradingview-pine-scripts/README.md` | New indicators, version upgrades, parameter changes |
| `.claude/agents/` or `.claude/commands/` | (no primary doc) | N/A |
| `tests/` | `docs/GCP_IMPLEMENTATION_STATUS.md` (Test Results table) | After every test run |
| **Any commit** | `docs/GCP_IMPLEMENTATION_STATUS.md` | Every commit — update Last Updated date + add one-line entry to a running change log |

3. **Staleness check**: Read the relevant doc section for each changed file. If the doc no longer matches the code, write the updated text now using these templates:

   - **New feature or method**: Add a subsection with: Purpose, API signature, key parameters, example
   - **Changed parameter or config**: Update the table row or code block with new value + note
   - **Bug fix**: Add a bullet: `- Fixed [issue] in [file:line]: [brief explanation]`
   - **Removed feature**: Strike the section or delete it and note removal date

4. Apply all doc edits using the Edit tool **before** creating any commit (doc updates go in the same commit as the code they document).

---

## Phase 3: Group and Commit

5. **Group related changes** by these categories. Files that are functionally related go in the same commit even if in different directories. Doc updates always go with the code they document.

   | Group | What belongs |
   |-------|-------------|
   | `feat(lib)` | `lib/` changes + corresponding `docs/GCP_IMPLEMENTATION_GUIDE.md` section updates |
   | `feat(gcp)` | `gcp/` changes + docs updates |
   | `feat(fetchers)` | `gcp/fetchers/` changes + docs updates |
   | `feat(backtest)` | `lib/backtest.py`, `lib/walk_forward.py`, `scripts/run_backtest.py`, `BACKTEST_RESULTS.md` |
   | `feat(signals)` | `lib/signals.py`, `lib/strat.py`, `alert_config.json` |
   | `feat(indicators)` | `lib/indicators.py` changes |
   | `feat(scripts)` | `scripts/` CLI scripts |
   | `feat(analysis)` | `scripts/analysis/` + `reports/phase*.md` together |
   | `feat(web)` | Web app directories (options-heatseeker, chart-viewer, website, success-report-site) |
   | `feat(platform-api)` | `platform/api/` changes (FastAPI routers, endpoints) |
   | `feat(platform-ui)` | `platform/src/` changes (React components, hooks, routes) |
   | `feat(platform)` | Cross-cutting platform changes spanning both `platform/api/` and `platform/src/` |
   | `feat(pine)` | `tradingview-pine-scripts/` indicator changes |
   | `feat(workflows)` | `.github/workflows/` changes + docs |
   | `feat(config)` | `alert_config.json`, `lib/config.py` together |
   | `chore(agents)` | `.claude/agents/` or `.claude/commands/` changes |
   | `chore(deps)` | `requirements.txt` alone (unless paired with feature) |
   | `docs` | Standalone doc-only changes with no corresponding code change |

6. **Grouping rules** (enforce strictly):
   - NEVER mix unrelated feature changes in one commit
   - NEVER use `git add -A` or `git add .`; always `git add <specific files>`
   - Doc updates for a feature go in the SAME commit as that feature
   - `docs/GCP_IMPLEMENTATION_STATUS.md` (Last Updated + change log) goes in EVERY commit
   - If a file touches multiple groups, put it with the group that owns its primary purpose

7. **Commit message format**:
   ```
   type(scope): short description (imperative mood, ≤72 chars)

   Optional body: one or two sentences explaining WHY, not WHAT.

   [test failures]    ← include this line only if tests are failing
   ```

   - Types: `feat`, `fix`, `refactor`, `chore`, `docs`, `test`
   - **Imperative mood required**: First word MUST be an imperative verb (add, fix, update, remove, refactor, implement, improve, simplify, extract, rename) — NOT past tense ("added", "fixed") or gerund ("updating", "removing")
   - Subject line must NOT end with a period
   - Body lines wrap at 72 characters
   - NEVER include `Co-Authored-By:`, email addresses, or AI attribution
   - NEVER use the 🤖 emoji

8. **Execute in order**:
   1. Apply all doc edits first (Edit tool)
   2. Stage specific files: `git add path/to/file1 path/to/file2`
   3. Commit: `git commit -m "$(cat <<'EOF' ... EOF)"`
   4. Repeat for each logical group
   5. Run `git status` at the end to confirm nothing was missed

---

## Phase 3.5: Update Changelog

**MANDATORY** — Every commit must be reflected in the changelog.

8b. **Prepend to the single changelog** at `docs/changelog/CHANGELOG.md`:
   - There is ONE canonical changelog file: `docs/changelog/CHANGELOG.md`. Do NOT create weekly `CHANGELOG_*.md` files.
   - If `docs/changelog/CHANGELOG.md` does not exist, create it with a `# Changelog` header.
   - New entries go at the TOP of the file (reverse chronological), under a `## Session (YYYY-MM-DD)` heading.
   - For each commit group, add a section with: **Commit(s)**, **Files**, **What Changed**, **Why**, **Benefit**.
   - If an existing section under today's date already covers this area, append to it instead of duplicating.
   - Include the changelog file in the same commit as the code it documents (or as a separate `docs` commit if the code was already committed).

---

## Phase 4: Status Tracker Update

9. After all commits are done, read `docs/GCP_IMPLEMENTATION_STATUS.md` and:
   - Update the **Last Updated** date at the top to today
   - Update the **Test Results** table row with current pass/fail counts and date (run `make test` if you don't have a recent result)
   - Add a one-line entry to the Change Log section:
     ```
     - YYYY-MM-DD: <one-line summary of what this session changed>
     ```
   - Mark any newly completed checklist items as `[x]`

---

## Phase 5: Report

10. After all commits and status updates, output a summary:

```
## Commit Summary

| # | Commit SHA | Message | Files |
|---|-----------|---------|-------|
| 1 | abc1234   | feat(signals): ... | lib/signals.py, docs/... |
| 2 | def5678   | feat(gcp): ...     | gcp/fetchers/..., docs/... |

## Documentation Updates
- docs/GCP_IMPLEMENTATION_GUIDE.md §5: updated [what changed]
- docs/GCP_IMPLEMENTATION_STATUS.md: updated Last Updated, test results

## Test Results
N/N passed  (or: N passed, N failed — see Fix Plan below)
```

If any tests failed, append a **Fix Plan** section:

```
## Fix Plan

1. [test_name] in tests/test_foo.py:42
   Error: <exact message>
   Fix: <specific file:line change needed>
```

---

## Agent Memory

After completing the session, read `/home/codespace/.claude/projects/-workspaces-stocks/memory/MEMORY.md`. If you discovered a new stable pattern (e.g., a new code area → doc mapping, a recurring commit grouping rule, a project convention), append it to the relevant memory file using the Edit tool. Do NOT write session-specific context into memory.

$ARGUMENTS
