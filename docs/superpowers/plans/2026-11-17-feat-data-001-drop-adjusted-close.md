---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-17-feat-data-001-drop-adjusted-close.md
branch: feature/feat-data-001-drop-adjusted-close
pr: null
status: ready
---

# Drop `adjusted_close`: the schema stops creating what is dropped, and the drops wait in Close-out files (spec B): implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the order of the spec's frontmatter, [0] (the schema test) to [6] (catalog, site notes, audit and gate). The map below names each.

**Goal:** `gcp/schema.sql` stops declaring `market_data_daily.adjusted_close` and stops creating the two Yahoo price archives, two one-statement files under `gcp/queries/` hold the column drop and the archive drop for the owner's Close-out, the no-adjusted guard's only `.sql` allowance becomes the drop file's `ALTER TABLE` line, and `scripts/archive_yahoo_data.py` is retired; nothing changes live when this merges.

**Architecture:** No `DROP` goes into `gcp/schema.sql`: after this change no unit `gcp.apply_schema.split_statement_groups` returns for it names the column or either archive, so every later apply (including the one the merge itself triggers through `apply-schema-on-change`) neither re-creates nor drops them. The live drops are `DO` blocks the owner sends with `./scripts/db_query_cr.sh -f` at Close-out, after the readers are redeployed, the column is cleared and a writer probe reads zero. A prerequisite `docs/` PR rewords the backticked script paths the docs audit would otherwise report as dead links.

**Tech Stack:** Postgres 15 DDL (`DO $$ ... $$`, `set_config('lock_timeout', '5s', true)`), Python 3 and pytest (hermetic: no database, no git command in a test), `gcp.apply_schema.split_statement_groups` and `_code_of`, `scripts/maintenance/doc_inventory.py`, `scripts/maintenance/doc_source_snapshot.py`, `scripts/maintenance/docs_audit.py`, `scripts/gate/spec_gate.py`.

**Spec:** docs/superpowers/specs/2026-11-17-feat-data-001-drop-adjusted-close.md (approved; stocks #2081, merged as d338c8ed4). Companion specs it cites: `docs/superpowers/specs/2026-11-16-feat-data-001-spy-qqq-iwm-only-r2.md` (r2: Design 10, Decisions 11, 14 and 15, Close-out steps 6 to 8) and `docs/superpowers/specs/2026-11-16-feat-data-001-no-adjusted-prices-r2.md` (no-adjusted, implemented by #2047 as f5a9fd018: its guard and its Close-out steps 1 and 2). r2's plan, `docs/superpowers/plans/2026-11-17-feat-data-001-spy-qqq-iwm-only.md` (`status: ready`, Task 13), writes the same column drop file.

## Global Constraints

- Base: `origin/main` at or after d338c8ed4. Branch `feature/feat-data-001-drop-adjusted-close`. This plan is committed alone on `docs/plan-feat-data-001-drop-adjusted-close` and merged before the code branch opens. Line anchors below are d338c8ed4 (read); Task 1 re-reads them on the merge base.
- No live effect. `gcp/schema.sql` gains no `DROP` statement and no `ALTER`; `gcp/apply_schema.py`, the `apply-schema-migrations` job, `gcp/deploy.sh` and every file under `platform/api` are not in the diff (done_when[5]). The merge fires `apply-schema-on-change` (`gcp/cloudbuild/apply-schema-cloudbuild.yaml:2`, "push to main touching gcp/schema.sql", read), which then applies a file that names none of the three targets.
- The column drop file is exactly r2 Design 10's statement, one `DO` block: `PERFORM set_config('lock_timeout', '5s', true);` then `ALTER TABLE market_data_daily DROP COLUMN adjusted_close;`, and no other relation or column. The archive drop file is one `DO` block: the same lock timeout, then `DROP TABLE IF EXISTS archive_yahoo_market_data_daily, archive_yahoo_market_data_intraday;`, and no other relation. No `CASCADE`. Whichever of r2's implementation and this one merges second keeps the column file unchanged.
- The guard (`tests/gcp/test_no_adjusted_prices.py`) loses its `gcp/schema.sql` allowance and keeps one `.sql` allowance: the `ALTER TABLE` line of `gcp/queries/drop_adjusted_close.sql`. Never widen it beyond that line.
- Kept (spec Non-goals): the DEFAULT partition of `market_data_intraday`; `archive_yahoo_etf_options_snapshots` and `archive_yahoo_earnings_options_snapshots`; every row; no `VACUUM FULL`; no API, job, scheduler or deploy change.
- `docs/product/` on the feature branch: only the FEAT-DATA-001 record of `02-FEATURE-CATALOG.md`, the FEAT-DATA-001 lineage of `12-PR-ISSUE-TRACEABILITY.md`, the three declared rows of `03-SITE-TRACEABILITY.md`'s implementation-source notes (CHARTS-03, DASHBOARD-03, LIVE-04), and the inventory blocks and renderer-owned counts of `infrastructure/05-a-ARCHITECTURE.md` and `05-c-DATA_DEPENDENCIES.md` as `doc_inventory.py` renders them. The hand-written pages (`06-DATA-ARCHITECTURE.md`, `05-b`, `05-g`, `05-h`, `05-i`, `05-j`, `manual/05-a`, `manual/05-c`) wait for Close-out step 8, except the prerequisite rewording of Task 2.
- **The render step.** Every commit that moves lines in `gcp/`, `lib/` or `scripts/` ends with `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --insert docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`, then `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all passed), staging whichever docs changed. `--insert`, not `--restore`: this change moves the declared relation count, which only `--insert` renders (Choices, item 6).
- Production access: no task reads or writes production; the implementation needs no GCP read. No `--commit`, no deploy, no schema apply. The Close-out steps are the owner's, each on its own yes, listed at the end and never run from this plan.
- Tests are hermetic. CI's Run Tests job checks out one commit with no `origin/main`: no test runs git.
- Commits: conventional `type(scope): description`, imperative, no AI attribution, no `Co-Authored-By`. Every new or changed test has a red then green record in the PR body. No em or en dash in code, comments, SQL or docs written for this change.

## Review Focus

Inputs the spec implies and no done_when test pins, most likely first. Each has a test in Task 3.

- **A comment in a drop file that names the column, the column file or the spec's path.** The guard's `.sql` scan reads every line, comments included, and `ADJUSTED_NAME` matches `drop_adjusted_close.sql` and `drop-adjusted-close.md` as well as the column (run on a draft header that cited the spec path and the `-f` command: three lines flagged, two of them comments). A reasonable person expects a usage comment to be harmless; here it fails the guard. Seeded case: a comment naming `gcp/queries/drop_adjusted_close.sql` inside that file counts 1.
- **r2's column file already on the base.** Its comments and layout may differ from this plan's. The check compares the code with comments removed and whitespace collapsed, so a file that differs only there passes and the file is never edited; a different statement fails. Seeded case: the column statement under other comments and on one line gives no problem.
- **The drop sent as two statements.** A bare `SET lock_timeout = '5s';` before the `ALTER` would run in its own transaction under the dispatcher's `-q` split, so the timeout would not hold for the DDL. Seeded case: that two-statement file is refused as "not one unit".
- **A session-level timeout or a wider drop.** `set_config(..., false)`, a `CASCADE`, an options archive, or `market_data_daily` itself in the archive drop. Seeded cases: each is refused.
- **A dropped name left elsewhere in the schema.** An index, a grant or a comment outside any statement naming an archive or the column would survive the unit check (a comment before a statement is in no unit). The schema test also asserts the whole file names none of the three.

---

## Order: the prerequisite docs PR, r2, and this PR

1. **This plan** merges on its `docs/` branch.
2. **Task 2's `docs/` PR** (rewording the backticked script paths) can open at once and merges before this plan's implementation PR is marked ready. The implementation branch merges `origin/main` after it lands (a merge, never a rebase), so the branch audit and `main`'s are compared on the same docs.
3. **The implementation PR** (Tasks 1 and 3 to 6) opens as a draft once its tasks are done; it is marked ready only after step 2.

**r2's implementation, either order.** Read on d338c8ed4 (2026-11-17): r2's plan is `status: ready`, `pr: null`; no `feature/feat-data-001-spy-qqq-iwm-only` branch is on origin (`git ls-remote`); no open PR names it; `gcp/queries/drop_adjusted_close.sql` does not exist on `main`; `SQL_ALLOWANCE` (`tests/gcp/test_no_adjusted_prices.py:353-356`) holds only the two schema lines. So r2 has not been implemented, and today this PR would merge first. Task 1 Step 2 reads which order holds on the merge base; the plan does this:

| On the merge base | `gcp/queries/drop_adjusted_close.sql` | Guard allowance |
|---|---|---|
| **B first** (no file; today) | created with Task 3's text | `SQL_ALLOWANCE` becomes the file's one `ALTER TABLE` line, replacing the schema lines |
| **r2 first** (file present, r2's Task 13 merged) | kept byte for byte; Task 3's test must pass on it, or stop and report (never edit r2's file) | the schema entry is removed; r2's entry for the file is kept as r2 wrote it |
| **r2 merges while this PR is open** | merge `origin/main` in; resolve to r2's bytes if the two differ only in comments or layout; if the statement differs, stop and report | as the row above |

If this PR merges first, r2's Task 13 finds the file and the allowance present and keeps both (spec Design 2: "whichever merges second keeps it unchanged", "the guard's allowance ... is added by whichever merges first"). r2's Task 13 Step 3 says "spec B removes both allowances with the schema line"; spec B Design 3 keeps the drop line's allowance, and spec B governs (reported, "Found while planning", item 4).

## Capacity (CLAUDE.md Rule 0; spec Design 6), copied into the PR body

The PR itself runs nothing: no job, schedule, image or query changes, and the apply its merge triggers changes no relation. The workload is the owner's Close-out:

- **Volume:** the clear, 34,993 non-NULL values today in a 5,830,927-row, 4,211,539,968-byte table (`db-query-pzfr8`, `-l4c9f`), about 8,092 if r2's deletes run first, plus the nights between; the column drop, catalog only; the archive drop, 0 and 51,471 rows (5,920 kB for the second).
- **Velocity:** one `UPDATE` dispatch (the clear), one `SELECT` per writer probe, one `ALTER` dispatch, one `DROP TABLE` dispatch, each with a dry run first: four to six `db-query` dispatches.
- **Wall-clock:** the clear is a sequential scan (no index on the column): the count over it took 13.3 s, a full scan 29.8 s; its rewrite of at most 34,993 rows is not measured; bound `--timeout 300`. Each probe about 13 s under the 120 s default. The two drops: the lock wait plus a catalog update, not measured; bound by the 5 s lock timeout.
- **Cost:** under $0.01 in all (estimate, list prices not re-read); no new job, schedule or vendor call. About 6 MB freed by the archive drop; the column's bytes stay in the heap until each row is rewritten.
- **I/O shape:** no new code path performs I/O; the tests read files only.

## Choices this plan makes where the spec leaves one open (each reported to the owner with the plan)

1. **The column drop file's text, B first** (Task 3). Its comments name neither the column, nor the file, nor the spec's path, since the guard's scan reads comment lines (Review Focus 1).
2. **"The file r2's Design 10 gives" is checked on its code**: comments removed with `gcp.apply_schema._code_of` (the applier's own reader of quotes, dollar bodies and `--`), whitespace runs collapsed, then compared with one expected string; and `split_statement_groups` must return exactly one unit of one statement. A byte pin would refuse r2's file in the r2-first order.
3. **The allowance keeps its shape**, `SQL_ALLOWANCE = (path, (line, ...))` compared on `line.strip()`, so `sql_adjusted_lines` changes only its docstring.
4. **Two tests are renamed** because their names state what stops being true: `test_the_sql_scan_allows_only_the_schema_lines` becomes `test_the_sql_scan_allows_only_the_drop_line`, and `test_the_yahoo_archive_is_the_one_named_deleter` becomes `test_the_variable_table_writers_are_the_named_ones` (its name is also cited in the comment at `tests/meta/test_production_writers.py:1361`).
5. **The schema comment above the options archives** (`gcp/schema.sql:547-555`) names those two only, says they are empty and that their copy script was retired by FEAT-DATA-001 spec B, and names neither dropped archive (done_when[3]'s grep reads comments) nor any adjusted name.
6. **The render uses `--insert`.** Removing two declared tables moves three renderer-owned prose counts, which `--restore` (counts off) leaves stale: run on a scratch tree of this change, `--restore` re-rendered seven blocks and `test_committed_docs_pass_every_gate` then failed with 11 findings ("claims 79 declared relations ... declares 77", "claims 76 tables ... declares 74", "claims 26 runtime relations; 95 live minus 77 declared is 28"). `--insert` renders them (`05-a:111`, `:143`, `:1142`, `05-c:1534`), and the whole file then passed but for one test, `test_the_runtime_relation_count_must_match_the_snapshot` (`tests/scripts/test_check_generated_docs.py:333-341`), which seeds the wrong count 28 against a true 26 by text; with 28 now true it finds nothing. Task 3 makes it seed `n + 2`, with `n = len(doc_inventory.runtime_relations(repo, live))`, and expect "claims {n+2} runtime relations" and "is {n}". Those counts are renderer-owned substitutions the feature branch may change (product-delivery skill, Never). Run in PR mode (`PR_HEAD_REF=feature/feat-data-001-drop-adjusted-close python3 scripts/gate/spec_gate.py --pr origin/main`) on a scratch commit of this plan, the schema edit, the two files, the deleted script and the `--insert`-rendered 05-a and 05-c, the gate refused only the missing site notes Task 6 adds; with a 05-h edit added it also refused 05-h by name. Task 6 Step 7 runs it on the real head.
7. **`SCHEMA_SHA256` is re-pinned** (`tests/gcp/test_premarket_filter_params.py:335-339`, `test_schema_is_unchanged` at `:626`), with its comment naming this change and the old and new hash in the PR body: the pin moves on any schema change on purpose.
8. **The writer list of done_when[4]** is built from what the repo's own inventory already computes (`doc_inventory --markdown blast`, the "Tables written" column, code reachable from each job's entry module through the names it imports), checked against a pinned grep, with schedules from `doc_inventory.deploy_schedulers` and their `gcp/deploy.sh` lines (Task 5). A plain import closure over-reports: run on d338c8ed4 it listed 26 jobs, among them `signal-monitor`, because most entry modules import `gcp/fetchers/fetch_market_data.py` somewhere.
9. **Task 2's docs PR also rewords `docs/BRIEFING_DECK.md:1090`** ("Found while planning", item 1).
10. **The new test module is the spec's `tests/gcp/test_drop_adjusted_close.py`**; it imports nothing from the guard module, so either can change alone.

## Found while planning (reported to the owner; none is resolved silently)

1. **A third dead link, in a document the spec keeps as written.** On a scratch tree of d338c8ed4 with `scripts/archive_yahoo_data.py` deleted (and on 9d862b05c with the schema edited too), the docs audit reported three findings `origin/main` does not: `docs/product/infrastructure/05-i-GCP_IMPLEMENTATION_GUIDE.md:1052`, `05-j-GCP_IMPLEMENTATION_STATUS.md:508` (both named by the spec) and **`docs/BRIEFING_DECK.md:1090`** ("backticked path -> scripts/archive_yahoo_data.py", P2). Spec Design 4 lists `docs/BRIEFING_DECK.md` among the dated records that "stay as written", but done_when[6] requires the branch audit to report nothing `main` does not. `DOC_REGISTRY.md:267` registers it as Class D (watched, hand-written), and #1758 (82967a886) edited it for a retirement before. The plan rewords that one line's path in Task 2's PR (Choices, item 9). **Owner:** yes to that line's rewording, or accept one new P2 finding, which leaves done_when[6] unticked.
2. **The render moves prose counts.** See Choices, item 6. Not a spec conflict (done_when[5] asks for the re-render and `test_check_generated_docs.py` to pass), but the spec does not say the counts move from 79 to 77 declared relations, 76 to 74 tables and 26 to 28 runtime relations, nor that one test pins 26 by text. After the render the `dbtables` blocks still list both archives, now marked "**runtime-created** (not in schema.sql)": they come from the 2026-09-07 live snapshot fixture, which still holds them (scratch run). That stays true until a snapshot is taken after Close-out step 6.
3. **`backfill-ticker` writes `market_data_daily` and has no schedule.** `doc_inventory.deploy_schedulers` lists no scheduler for it (run on d338c8ed4); it runs by hand (`deploy_backfill_ticker`, `gcp/deploy.sh:1294`, `./gcp/deploy.sh discord`; `tests/meta/test_production_writers.py`, `test_no_code_dispatches_backfill_ticker`). Close-out step 4 "waits for one successful execution of each" listed job, which for this one never comes unless the owner runs it. **Owner:** run it once by hand on the new image before step 4, or let its image digest (no-adjusted Close-out step 2) stand for it. The PR body lists it with "no schedule".
4. **r2's plan disagrees with spec B on the allowance.** r2 plan Task 13 Step 3 ends "(spec B removes both allowances with the schema line)"; spec B Design 3 keeps the drop line's allowance, since the file still names the column. r2's Task 13 also says "Write the two files" without the keep-if-present rule. Its plan is edited only from its own branch, so this plan does not touch it; whoever executes r2 is told to keep this PR's file and allowance when this PR merges first.
5. **More hand-written pages for Close-out step 8.** Besides Design 4's list, `docs/product/infrastructure/05-g-DATA_PIPELINE.md:17` names `archive_yahoo_*`, and two prose lines outside the inventory blocks, `05-a-ARCHITECTURE.md:238` ("`archive_yahoo_*` (4, frozen, 0 rows live)") and `05-c-DATA_DEPENDENCIES.md:1026` ("the four `archive_yahoo_*` tables are frozen forensics"), stay until that PR.
6. **A stale anchor.** The spec cites `tests/meta/test_production_writers.py:2459-2463` for the case that imports the script; the case is `:2441-2485` on d338c8ed4 (read).

## done_when map

| done_when | What | Task |
|---|---|---|
| [0] | the schema creates and names none of the three | 3 |
| [1] | the two drop files name only their targets | 3 |
| [2] | the guard's only `.sql` allowance is the drop line | 3 |
| [3] | the script is gone; the writers test passes; the archive grep | 4 |
| [4] | the PR body lists every job writing `market_data_daily` | 5 |
| [5] | `make test`; the re-render; `deploy.sh` and `platform/api` not in the diff | 3, 4, 5 |
| [6] | catalog, traceability, site notes, snapshot, audit, gate | 2, 6 |

Design sections: Design 1, 2 and 3 in Task 3; Design 4 in Tasks 2 and 4 and Close-out step 8; Design 5 in Task 6; Design 6 in the Capacity section above and the PR body.

## File map

| File | Change | Task |
|---|---|---|
| `docs/product/infrastructure/05-i-GCP_IMPLEMENTATION_GUIDE.md:1052`, `05-j-GCP_IMPLEMENTATION_STATUS.md:508`, `docs/BRIEFING_DECK.md:1090` | the backticked script path reworded, on its own `docs/` branch | 2 |
| `gcp/schema.sql` | `:110-111` removed; `:547-561`: comment rewritten, two `CREATE TABLE` removed | 3 |
| `gcp/queries/drop_adjusted_close.sql` | new (B first) or kept (r2 first) | 3 |
| `gcp/queries/drop_yahoo_price_archives.sql` | new | 3 |
| `tests/gcp/test_drop_adjusted_close.py` | new | 3 |
| `tests/gcp/test_no_adjusted_prices.py` | `:340-342`, `:353-356`, `:489-491`, `:533-537`, `:583-591` | 3 |
| `tests/gcp/test_premarket_filter_params.py` | `SCHEMA_SHA256` and its comment, `:335-339` | 3 |
| `tests/scripts/test_check_generated_docs.py` | `:333-341` | 3 |
| `scripts/archive_yahoo_data.py` | deleted | 4 |
| `tests/meta/test_production_writers.py` | `:1361`, `:2345-2353`, `:2365-2368`, `:2441-2485` | 4 |
| rendered `docs/product/infrastructure/05-a-ARCHITECTURE.md`, `05-c-DATA_DEPENDENCIES.md` | render step | 3, 4, 6 |
| `docs/product/02-FEATURE-CATALOG.md` (FEAT-DATA-001 record, `:515`), `12-PR-ISSUE-TRACEABILITY.md` (lineage, `:346`), `03-SITE-TRACEABILITY.md` (`:1309`, `:1312`, `:1324`), `docs/review-evidence/site-source-snapshot.json`, this plan's `pr:` | close | 6 |

---

### Task 1: Preconditions, the order, and the branch

Spec: Where this comes from (r2 Split item B, Design 10); Design 2 ("whichever merges second"); Close-out step 1 (second bullet). Supplies done_when[1] and [2].

**Files:** none changed.

**Interfaces:**
- Produces: the order ("B first" or "r2 first") that Task 3 follows, and the merge base's line anchors, both recorded in the PR body.

- [ ] **Step 1: The spec and this plan on `main`.** `git fetch origin`; on `origin/main`, `grep -n '^status' docs/superpowers/specs/2026-11-17-feat-data-001-drop-adjusted-close.md` reads `approved` and `grep -n '^status\|^branch' docs/superpowers/plans/2026-11-17-feat-data-001-drop-adjusted-close.md` reads `ready` and this branch. If either is missing, stop.
- [ ] **Step 2: Which order.** On `origin/main`: `git ls-tree origin/main gcp/queries/drop_adjusted_close.sql` and `git show origin/main:tests/gcp/test_no_adjusted_prices.py | grep -n -A6 '^SQL_ALLOWANCE'`. No file and two schema lines: **B first**. A file and an allowance for its line: **r2 first**; record the file's sha256 and r2's allowance text. Paste both outputs into the PR body.
- [ ] **Step 3: Cut the branch.** `git worktree add -b feature/feat-data-001-drop-adjusted-close <dir> origin/main`. Re-read and paste the anchors the tasks name: `grep -n 'adjusted_close\|archive_yahoo' gcp/schema.sql` (d338c8ed4: `:111`, `:555`, `:557`, `:560`, `:563`, `:566`), `grep -n '^SQL_ALLOWANCE\|^def sql_adjusted_lines\|^def test_nothing_in_the_repo\|^def test_the_sql_scan' tests/gcp/test_no_adjusted_prices.py` (`:353`, `:489`, `:526`, `:590`), `grep -n 'archive_yahoo_data\|^VARIABLE_TABLE_WRITERS\|^def test_the_yahoo_archive' tests/meta/test_production_writers.py` (`:1361` by name, `:2347`, `:2365`, `:2441`, `:2459`), `grep -n '^SCHEMA_SHA256' tests/gcp/test_premarket_filter_params.py` (`:339`). Where one moved, the base's line is used and the difference listed.

### Task 2: The prerequisite docs PR: no dead path to the retired script

Spec: Design 4 (the exception that "cannot wait"). Advances done_when[6] (the branch audit reports nothing `main` does not). Its own branch and PR, not the feature branch; it merges before Task 6 marks the implementation PR ready.

**Files:**
- Modify (branch `docs/retired-archive-script-links`): `docs/product/infrastructure/05-i-GCP_IMPLEMENTATION_GUIDE.md:1052`, `docs/product/infrastructure/05-j-GCP_IMPLEMENTATION_STATUS.md:508`, `docs/BRIEFING_DECK.md:1090` (Choices, item 9; owner's yes, "Found while planning", item 1)

**Interfaces:**
- Produces: on `main`, no backticked path with a directory to `scripts/archive_yahoo_data.py` outside dated plans and specs, so Task 4's deletion adds no dead-link finding.

- [ ] **Step 1: List what the deletion flags.** In a scratch detached worktree of `origin/main`: `git rm -q scripts/archive_yahoo_data.py`, then `LC_ALL=C python3 scripts/maintenance/docs_audit.py | grep -E '^\s*\[P' | sed -E 's/:[0-9]+//g; s/^\s+//' | sort > branch.txt`, the same on a clean `origin/main` into `main.txt`, and `comm -23 branch.txt main.txt`. Expected on d338c8ed4 (run 2026-11-17, 316 findings on `main`, 319 with the deletion): exactly the three `[P2] dead-link: ... backticked path -> scripts/archive_yahoo_data.py` lines for the three files above. Any other line is reworded in this PR too and listed in its body. Remove the scratch worktree.
- [ ] **Step 2: Reword each line**, keeping its sense and naming the script as retired, with no backticked path that has a directory. The wording run on the scratch tree: "the archive script (`archive_yahoo_data.py` under `scripts/`, retired by FEAT-DATA-001 spec B)" (05-i reads "which implemented:" after it). The bare file name is not a root file, so the audit does not resolve it.
- [ ] **Step 3: Check.** The audit comparison of Step 1 on this branch, with and without the script deleted, gives an empty `comm -23` both times (run 2026-11-17 on the three lines above: 316 and 316, empty). `python3 scripts/gate/spec_gate.py --commit` and, after the commit, `python3 scripts/gate/spec_gate.py --pr origin/main` print `spec gate ok (branch=docs/retired-archive-script-links, 3 changed file(s))` (both run on a scratch commit of the same three lines: exit 0).
- [ ] **Step 4: Commit and open the PR:** `docs: name the retired Yahoo archive script without a dead path`. Body: the three lines, Step 1's list, the two audit counts, the gate outputs, "Capacity: n/a: documentation only", and that FEAT-DATA-001 spec B's implementation PR waits for this merge. Merge under the repo's review rules.

### Task 3: The schema, the two Close-out files and the guard

Spec: Design 1, Design 2, Design 3; Approaches 1 and 4. Closes done_when[0], [1] and [2]; advances done_when[5] (render).

**Files:**
- Modify: `gcp/schema.sql` (`:110-111` removed with the blank line after them; `:547-555` comment rewritten per Choices, item 5; `:557-561` removed)
- Create (B first; r2 first: keep): `gcp/queries/drop_adjusted_close.sql`
- Create: `gcp/queries/drop_yahoo_price_archives.sql`
- Create: `tests/gcp/test_drop_adjusted_close.py`
- Modify: `tests/gcp/test_no_adjusted_prices.py`, `tests/gcp/test_premarket_filter_params.py`, `tests/scripts/test_check_generated_docs.py`

**Interfaces:**
- Consumes: `gcp.apply_schema.split_statement_groups(sql_text: str) -> list[list[str]]` (comment lines before a statement belong to no unit; comment lines inside one are kept); `gcp.apply_schema._code_of(line: str, tag: Optional[str]) -> tuple[str, Optional[str]]`.
- Produces, in `tests/gcp/test_drop_adjusted_close.py`: `REPO`, `SCHEMA`, `DROP_COLUMN_FILE`, `DROP_ARCHIVES_FILE` (paths); `DROPPED_NAMES = ("adjusted_close", "archive_yahoo_market_data_daily", "archive_yahoo_market_data_intraday")`; `sql_code(text: str) -> str` (each line through `_code_of`, carrying the dollar tag, joined, whitespace runs collapsed to one space, stripped); `DROP_COLUMN_CODE = "DO $$ BEGIN PERFORM set_config('lock_timeout', '5s', true); ALTER TABLE market_data_daily DROP COLUMN adjusted_close; END $$;"`; `DROP_ARCHIVES_CODE = "DO $$ BEGIN PERFORM set_config('lock_timeout', '5s', true); DROP TABLE IF EXISTS archive_yahoo_market_data_daily, archive_yahoo_market_data_intraday; END $$;"`; `drop_file_problems(text: str, expected: str) -> list[str]` (`"not one unit: <n>"` unless `split_statement_groups` gives one unit of one statement; `"code differs: <sql_code(text)>"` unless it equals `expected`).
- Produces, in `tests/gcp/test_no_adjusted_prices.py` (B first): `SQL_ALLOWANCE = ("gcp/queries/drop_adjusted_close.sql", ("ALTER TABLE market_data_daily DROP COLUMN adjusted_close;",))`. r2 first: r2's entry for that file, unchanged, and no `gcp/schema.sql` entry.

- [ ] **Step 1: Write the failing tests.**
  - `test_the_schema_no_longer_creates_what_is_dropped`: over `[s for u in split_statement_groups(SCHEMA.read_text()) for s in u]`, exactly one statement starts with `CREATE TABLE IF NOT EXISTS market_data_daily (` and it does not contain `adjusted_close`; no statement contains any of `DROPPED_NAMES` (case-insensitive); and the whole file's text contains none of them (Review Focus 5).
  - `test_the_drop_files_name_only_their_targets`: `drop_file_problems(DROP_COLUMN_FILE.read_text(), DROP_COLUMN_CODE) == []` and the same for the archive file; then each seeded text below gives a non-empty list: the archive code with `, market_data_daily` added to the `DROP TABLE` list (done_when[1]'s case); the same with `archive_yahoo_etf_options_snapshots` added; the same ending `CASCADE;`; the column code with `true` replaced by `false`; the column code with `DROP COLUMN adjusted_close, DROP COLUMN close`; the two-statement text `SET lock_timeout = '5s';\nALTER TABLE market_data_daily DROP COLUMN adjusted_close;\n` (Review Focus 3 and 4). And one seeded text gives `[]`: `"-- another layout\n" + DROP_COLUMN_CODE + "\n"` (Review Focus 2).
  - In `tests/gcp/test_no_adjusted_prices.py`: the allowance assertion of `test_nothing_in_the_repo_fetches_stores_or_reads_an_adjusted_price` (`:533-537`) reads `SQL_ALLOWANCE[0]` instead of `gcp/schema.sql` and requires each allowed line exactly once there; rename `test_the_sql_scan_allows_only_the_schema_lines` to `test_the_sql_scan_allows_only_the_drop_line` with these cases: the two former schema lines in `gcp/schema.sql`, **2** (was 0; done_when[2]); `"    ALTER TABLE market_data_daily DROP COLUMN adjusted_close;\n"` in `gcp/queries/drop_adjusted_close.sql`, 0; the same line in `gcp/queries/other.sql`, 1; `"-- sent with -f gcp/queries/drop_adjusted_close.sql\n"` in `gcp/queries/drop_adjusted_close.sql`, 1 (Review Focus 1); and the two kept cases (`x.sql` NaN filter, 1; `adj_close NUMERIC` in `gcp/schema.sql`, 1).
- [ ] **Step 2: Run** `python3 -m pytest tests/gcp/test_drop_adjusted_close.py tests/gcp/test_no_adjusted_prices.py -q`. Expected FAIL: the schema test on unit 0 (`adjusted_close`) and units 26 and 27 (the two archives; `split_statement_groups` gives 288 units on d338c8ed4, run); the drop files test with `FileNotFoundError` (B first); the seeded case expecting 2 gets 0. Paste as the red record.
- [ ] **Step 3: Implement.** The schema edit. B first, the column file:

```sql
-- FEAT-DATA-001 spec B, Close-out step 5 (r2's Close-out step 8): drop the
-- column the two companion specs retired from market_data_daily. One DO
-- block, so the dispatcher sends it as one statement and the 5 s lock
-- timeout holds for the ALTER. Sent with ./scripts/db_query_cr.sh -f and
-- this file's path: dry run first, then --commit on the owner's yes.
DO $$
BEGIN
    PERFORM set_config('lock_timeout', '5s', true);
    ALTER TABLE market_data_daily DROP COLUMN adjusted_close;
END
$$;
```

  The archive file, the same shape: a header naming Close-out step 6 and the two archives "once the second is empty", then the `DO` block with `DROP TABLE IF EXISTS archive_yahoo_market_data_daily, archive_yahoo_market_data_intraday;`. Both headers were checked against `ADJUSTED_NAME` and `ADJUSTED_FUNCTION` (no line flagged but the `ALTER`), and each file gives one unit (run). Then `SQL_ALLOWANCE`, the comment at `:340-342` ("the one `ALTER TABLE` line of gcp/queries/drop_adjusted_close.sql, the Close-out drop of the column") and the `sql_adjusted_lines` docstring.
- [ ] **Step 4: Run again** (expect PASS), then `python3 -m pytest tests/gcp/test_apply_schema.py tests/gcp/test_apply_schema_trigger.py -q` (expect pass).
- [ ] **Step 5: The pins.** `python3 -m pytest tests/gcp/test_premarket_filter_params.py::test_schema_is_unchanged -q` fails on the hash; re-pin `SCHEMA_SHA256` to `sha256sum gcp/schema.sql`, the comment naming this change, old and new in the PR body. Render step: `test_the_runtime_relation_count_must_match_the_snapshot` fails (Choices, item 6); change it to derive `n = len(doc_inventory.runtime_relations(repo, live))`, assert the copied 05-a holds `f"Live table drift ({n} runtime relations)"` (so the replace cannot miss), replace it with `n + 2`, and assert a finding holding `f"claims {n + 2} runtime relations"` and `f"is {n}"`; record its red (the unchanged test on the rendered docs) and green after. Expect `tests/scripts/test_check_generated_docs.py` all passed and the render to change `05-a` (tables and dbtables blocks; `:111`, `:143`, `:1142`) and `05-c` (tables, writes, reads, orphans, dbtables; `:1534`).
- [ ] **Step 6: Commit:** `fix(data): stop declaring adjusted_close and the Yahoo price archives` (the queries, the schema, the tests, the rendered docs).

### Task 4: The archive script is retired

Spec: Design 4 (the script and its test), Problem 3. Closes done_when[3]; advances done_when[5] (render).

**Files:**
- Delete: `scripts/archive_yahoo_data.py`
- Modify: `tests/meta/test_production_writers.py` (`:1361`, `:2345-2353`, `:2365-2368`, `:2441-2485`)

**Interfaces:**
- Consumes: `holds_variable_table_write(src: str) -> bool`, `_py_files(SCAN_ROOTS)`, `_rel(path)` (unchanged).
- Produces: `VARIABLE_TABLE_WRITERS = {"gcp/database.py"}`; `test_the_variable_table_writers_are_the_named_ones` (renamed).

- [ ] **Step 1: Write the failing test.** `VARIABLE_TABLE_WRITERS` loses the script's entry; the renamed test keeps `assert found == VARIABLE_TABLE_WRITERS` and the six seeded `holds_variable_table_write` cases at `:2449-2457` exactly; the `import scripts.archive_yahoo_data`, the `TABLES` and `YAHOO_PREDICATE` assertions and the `_Recorder`/`delete_chunk` case go. The comment at `:2345-2353` keeps what the variable-table check still does not see and the dispatch paragraph, and says the one file of that shape was the Yahoo archive script, retired by FEAT-DATA-001 spec B; `:1361` names the new test.
- [ ] **Step 2: Run** `python3 -m pytest tests/meta/test_production_writers.py -k variable_table_writers -q` (expect FAIL: `found` still holds `scripts/archive_yahoo_data.py`).
- [ ] **Step 3: Delete** `scripts/archive_yahoo_data.py` (`git rm`).
- [ ] **Step 4: Run again** (expect PASS), then `python3 -m pytest tests/meta/test_production_writers.py -q` (expect all passed).
- [ ] **Step 5: The grep of done_when[3]:** `grep -rn -E 'archive_yahoo_market_data_(daily|intraday)' gcp lib scripts platform` prints only lines of `gcp/queries/drop_yahoo_price_archives.sql` (on d338c8ed4 it prints `gcp/schema.sql:557`, `:560` and `scripts/archive_yahoo_data.py:59`, `:64`). Then `git grep -n 'archive_yahoo_data' -- ':!docs/superpowers' ':!docs/changelog' ':!docs/audit*'` lists what still names the script: expected only Task 2's three reworded lines (bare file name), the comments of Step 1 if they name it, and `docs/review-evidence/site-source-snapshot.json`, which Task 6 regenerates. Paste both.
- [ ] **Step 6: Render step, then commit:** `chore(data): retire the Yahoo archive script` (the deletion, the test, any rendered doc).

### Task 5: The whole suite, the scope, and the writer list

Spec: Design 4 (render), Close-out step 4, What was not verified (the writer list). Closes done_when[4] and [5].

**Files:** none but rendered docs if the render moves.

**Interfaces:**
- Consumes: `scripts.maintenance.doc_inventory.render_markdown("blast", repo, live)`, `deploy_schedulers(root) -> list[dict]` (keys `name`, `cron`, `target_job`, `time_zone`).
- Produces: the PR body's "Writers of market_data_daily" table: job, entry module, write sites (file:line), each scheduler with cron, zone and its `gcp/deploy.sh` line.

- [ ] **Step 1: Run** `make test`. Expected: exit 0. A failure that `origin/main` also has is shown with its run on `main`; any other is fixed in the task that owns the file. Measured on a scratch tree of d338c8ed4 with the schema edit, the deletion, Task 2's rewording and the `--insert` render but no test change (`pytest tests/ --ignore=tests/integration -n 3`, 2026-11-17): 11,475 passed, 58 skipped, 4 failed, exactly the four tests Tasks 3 and 4 change: `test_schema_is_unchanged`, `test_nothing_in_the_repo_fetches_stores_or_reads_an_adjusted_price`, `test_the_runtime_relation_count_must_match_the_snapshot` and `test_the_yahoo_archive_is_the_one_named_deleter`. No test under `tests/integration` (which CI runs on pg15 with `gcp/schema.sql` applied) names the column or either archive (grep).
- [ ] **Step 2: Scope.** `git diff --name-only origin/main...HEAD -- gcp/deploy.sh platform/api` prints nothing; `git diff --name-only origin/main...HEAD -- docs/product` prints only the files the Global Constraints allow.
- [ ] **Step 3: The writer list (done_when[4]).** Paste three outputs and the table built from them:
  - the grep: `grep -rnE "(INSERT INTO|UPDATE|DELETE FROM|MERGE INTO|COPY)[[:space:]]+\"?market_data_daily\b|['\"]market_data_daily['\"]" gcp lib scripts --include=*.py --include=*.sql | grep -v /tests/`, each hit marked a write or not (on d338c8ed4: 31 lines, 30 once the script is gone; the non-writes are `gcp/discord_interactions/main.py:337` (a probe), `gcp/db_maintenance.py:55` (the VACUUM and ANALYZE allow-list), `gcp/fetchers/fetch_premarket_refresh.py:381`, `gcp/bar_recompute.py:517` and `lib/data_loader.py:186` (`information_schema` reads), `gcp/queries/nan_triage.sql:31` (a SELECT), and labels in `lib/options_greeks.py:614`, `scripts/backfill_and_replay.py:113`, `:145` and `scripts/audit_data_freshness.py:110`);
  - `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --markdown blast`, the rows whose "Tables written" holds `market_data_daily`;
  - `python3 -c "from scripts.maintenance import doc_inventory as i; [print(s['target_job'], s['name'], repr(s['cron']), s['time_zone']) for s in i.deploy_schedulers()]"`, and `grep -n '"<scheduler>"' gcp/deploy.sh` for each.
  Read on d338c8ed4 (run), to be confirmed on the head:

  | Job | Entry | Writes (file:line) | Schedule (`gcp/deploy.sh`) |
  |---|---|---|---|
  | `fetch-market-data` | `gcp/fetchers/fetch_market_data.py` | `:647` (`compute_and_upsert_daily_indicators`), `:722` (`process_ticker`), `:770` (`fetch_and_upsert_vix`, `data_source` `yahoo`), `:1180` (`_run_backfill`); `gcp/bar_recompute.py:479` (`DAILY_PREMARKET`, `--recompute-premarket` by hand) | `fetch-market-data-daily` `0 23 * * 1-5` ET (`:4676`) |
  | `fetch-earnings-history` | `gcp/fetchers/fetch_earnings_history.py` | `fetch_market_data._run_backfill` (`:1180`) | `daily-earnings-refresh-history` `15 19 * * 1-5` (`:4828`), `weekly-earnings-refresh-history` `15 19 * * 0` (`:4832`) |
  | `fetch-premarket-refresh` | `gcp/fetchers/fetch_premarket_refresh.py` | `:408` | `premarket-refresh-daily` `20 8 * * 1-5` (`:4894`), `premarket-refresh-late` `20 9 * * 1-5` (`:4897`) |
  | `backfill-daily-indicators` | `gcp/fetchers/backfill_daily_indicators.py` | `:416` | `backfill-indicators-daily` `30 2 * * 1-6` (`:5097`), `backfill-indicators-weekly` `0 3 * * 0` (`:5102`) |
  | `premarket-brief` | `gcp/premarket_brief.py` | `:328` (`DELETE` of rows with no close) | `premarket-brief-daily` `30 8 * * 1-5` (`:4499`), `premarket-brief-late` `20 9 * * 1-5` (`:4502`), `premarket-brief-sunday` `0 21 * * 0` (`:4508`) |
  | `backfill-ticker` | `gcp/backfill_ticker.py` | `:387`, `:556`, `:634` | none: run by hand (`deploy_backfill_ticker`, `:1294`); "Found while planning", item 3 |

  Writers that are not jobs, listed under the table: `gcp/migrate_to_gcp.py:170`, `:588` (run locally by `gcp/deploy.sh:76`), `scripts/backfill_watchlist_data.py:235` (by hand), `gcp/queries/p1_vix_backfill.sql` (by hand; names no adjusted column). All times America/New_York. Close-out step 4 waits for one successful execution of each scheduled job.
- [ ] **Step 4: No commit** unless the render moved; then `docs(data): re-render the inventory`.

### Task 6: Close: product record, site notes, audit and gate

Spec: Design 5; done_when "02-FEATURE-CATALOG ...". Closes done_when[6]. Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/` or `tests/` changes without redoing them.

**Files:**
- Modify: this plan (`pr:`), `docs/product/02-FEATURE-CATALOG.md` (FEAT-DATA-001 record, Status `:522` and Last reviewed `:526`), `docs/product/12-PR-ISSUE-TRACEABILITY.md` (FEAT-DATA-001 PR lineage, `:346`), `docs/product/03-SITE-TRACEABILITY.md` (`:1309` CHARTS-03, `:1312` DASHBOARD-03, `:1324` LIVE-04, no other byte), `docs/review-evidence/site-source-snapshot.json`

- [ ] **Step 1: The draft PR.** `git push -u origin feature/feat-data-001-drop-adjusted-close`; open a **draft** titled `FEAT-DATA-001: drop adjusted_close and the two Yahoo price archives from the schema, with their Close-out drop files`. Body: the spec's and this plan's paths; the seven done_when items as `- [ ]` lines, each starting with the item's text; `Red then green` (Task 3 Step 2, Task 4 Step 2, the count test); the Capacity section above; Task 1's order and anchors; Task 5's writer table and grep; the old and new `SCHEMA_SHA256`; the choices and findings of this plan; `Canvas check pending (report-only): https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN` (`mode: report-only`, `docs/product/canvases.yml:52-56`); "No change a page shows (spec Design 5: no response the three components read changes), so no Playwright evidence is owed"; and "The merge applies gcp/schema.sql through apply-schema-on-change; no unit of it names the column or either archive, so nothing live changes. The drops are the owner's Close-out steps."
- [ ] **Step 2: Records.** This plan's `pr:` set to the number. The 02 record: Status gains a clause (`gcp/schema.sql` no longer declares `adjusted_close` nor creates the two Yahoo price archives, their drops are Close-out files run on the owner's yes, the archive script is retired (#<PR>; implementation under review, not deployed; nothing live changes until Close-out)) and Last reviewed the date. The 12 lineage gains `[#<PR>](...) *remediation: the schema stops declaring adjusted_close and the two Yahoo price archives; Close-out drop files; archive script retired* · specification [#2081](https://github.com/TeneikaAskew/stocks/pull/2081)`. Commit `docs(product): record the adjusted_close schema change under FEAT-DATA-001`.
- [ ] **Step 3: Site notes.** Clean tree; `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`; copy the reported source identity. In each of the three rows: `source_identity_sha256=<hash>; ` then this change's prose, then ` Earlier: ` and the row's earlier prose unchanged (its own earlier hash included). Prose, the same for the three (spec Design 5): "`gcp/schema.sql` no longer declares `market_data_daily.adjusted_close` nor creates `archive_yahoo_market_data_daily` and `archive_yahoo_market_data_intraday`; `gcp/queries/drop_adjusted_close.sql` and `gcp/queries/drop_yahoo_price_archives.sql` hold the Close-out drops, run on the owner's yes; no response this component reads changes. Tests: `tests/gcp/test_drop_adjusted_close.py`, `tests/gcp/test_no_adjusted_prices.py`. Source and local tests only; rollout pending." Commit `docs(site): note the adjusted_close schema change on three components`.
- [ ] **Step 4: Snapshot.** `produce` again, commit `docs(site): regenerate the source snapshot`, then `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 16777216 --max-entries 20000` (expect exit 0). If it refuses on size, stop and report the measured size; never raise a ceiling. If `origin/main` moved, merge it in (never a rebase), render, and redo Steps 3 and 4.
- [ ] **Step 5: Task 2's PR is merged** and in this branch (`git merge origin/main` if not). Render step once more.
- [ ] **Step 6: Audit.** `LC_ALL=C python3 scripts/maintenance/docs_audit.py | grep -E '^\s*\[P' | sed -E 's/:[0-9]+//g; s/^\s+//' | sort` on the branch and on a detached `origin/main` worktree; `comm -23 branch main` is empty. Paste both counts.
- [ ] **Step 7: Gate.** `python3 scripts/gate/spec_gate.py --pr origin/main` (expect `spec gate ok`), and the same with `PR_HEAD_REF=feature/feat-data-001-drop-adjusted-close` set, as CI sets it. No gate file is touched, so no red-team pass is owed.
- [ ] **Step 8: Ready.** Push; tick each done_when box with its evidence (test names, outputs, the writer table, the audit counts, the gate line); mark the PR ready. Review under CLAUDE.md 2.5 and the review cap; the merge changes nothing live.

## Close-out (not tasks; the owner's steps, each on its own yes, never run from this plan)

From the spec's Close-out. Each is recorded as a comment on the implementation PR, and steps 3 and 5 also on r2's implementation PR. Every command runs from a checkout of `main`, `gcloud` prefixed `env -u CLOUDSDK_AUTH_ACCESS_TOKEN`.

1. **Preconditions.** No-adjusted Close-out steps 1 and 2 are done: every job and service on #2047's reader list runs an image built from a `main` at or after f5a9fd018 (`gcloud run jobs describe <job> --region=us-east1`, `gcloud run services describe <service> --region=us-east1`); that list waits for r2's implementation and spec C. This PR is on `main`.
2. **Baseline, read only:** the four statements of spec Close-out step 2 (non-NULL values by `data_source`, the tables holding the column, the two archive counts).
3. **Clear** (r2's step 7), outside the 23:00 ET weekday fetch: `./scripts/db_query_cr.sh --timeout 300 -q "UPDATE market_data_daily SET adjusted_close = NULL WHERE adjusted_close IS NOT NULL"`, without, then with `--commit`. Check `SELECT count(adjusted_close) FROM market_data_daily` is 0.
4. **Writer probe.** After one successful execution of each scheduled job in Task 5's table (`gcloud run jobs executions list --job=<job> --region=us-east1`), and for `backfill-ticker` as the owner decides ("Found while planning", item 3), the same count is still 0. Non-zero: name the writer from `data_source` and `updated_at`, redeploy it from `main`, repeat steps 3 and 4. The column is never dropped with a writer left.
5. **Drop the column** (r2's step 8): `./scripts/db_query_cr.sh -f gcp/queries/drop_adjusted_close.sql`, then with `--commit`. Check the `information_schema.columns` count for `market_data_daily.adjusted_close` is 0.
6. **Drop the archives**, once r2's step 6 has truncated `archive_yahoo_market_data_intraday` (count 0) or on the owner's word that its rows go here: `./scripts/db_query_cr.sh -f gcp/queries/drop_yahoo_price_archives.sql`, then with `--commit`. Check both `to_regclass` are NULL and no column `ILIKE '%adj%'` remains.
7. **One day later, read only:** every scheduled job's executions in the 24 hours after step 5 succeeded or failed for another reason, and `gcloud logging read 'textPayload:"adjusted_close"' --freshness=1d --project=adept-mountain-474619-d4` holds no `does not exist`. A job failing on the column is redeployed from `main`; the column is never re-added.
8. **Records**, on a `docs/` branch after step 7: the hand-written docs of Design 4 (`05-h-DATA_DICTIONARY.md:68` and `:1597` among them) and those of "Found while planning", item 5, no longer describe the column, the two archives or the script as present; this plan's `status: done` (Phase 5 step 7). A later `doc_inventory` live snapshot drops the two archives from the `dbtables` blocks.
