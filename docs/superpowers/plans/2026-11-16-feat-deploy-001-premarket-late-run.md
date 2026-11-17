---
feat_id: FEAT-DEPLOY-001
spec: docs/superpowers/specs/2026-11-14-feat-deploy-001-premarket-late-run.md
branch: feature/feat-deploy-001-premarket-late-run
pr: 2020
status: done
---

# The late premarket run's two scheduler entries, implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances (done_when[0] is the first item).

**Goal:** `gcp/deploy.sh deploy_schedulers()` declares `premarket-refresh-late` and `premarket-brief-late` at `20 9 * * 1-5` America/New_York, each created or updated and read back, so the owner's deploy can add a 09:20 ET refresh and a late brief beside the untouched 08:20 and 08:30 run.

**Architecture:** one new helper, `_schedule_brief_slot`, beside `_schedule_brief`; two entries in `deploy_schedulers()`; tests in `tests/gcp/test_deploy_reachability.py` that run `deploy_schedulers()` against a recording `gcloud` that keeps scheduler state; then the documents the suites and the gate require (model registry rows and JSON, the 05-a inventory render, one 03-SITE note with its source snapshot, the catalog record and the traceability entry). No job, image, flag or existing entry changes.

**Tech Stack:** bash (`gcp/deploy.sh`, `bash -n`), pytest, `scripts/gate/export_model_registry.py`, `scripts/maintenance/doc_inventory.py`, `scripts/maintenance/doc_source_snapshot.py`, `scripts/maintenance/docs_audit.py`, `scripts/gate/spec_gate.py`.

**Spec:** `docs/superpowers/specs/2026-11-14-feat-deploy-001-premarket-late-run.md` (approved through #1929). Executors read it with this plan.

**How claims are marked:** "read" is code on `origin/main` at `c9a2b984` (line numbers are that commit's); "run" was executed for this plan on 2026-11-16 in a scratch copy of that commit and then reverted (nothing but this plan is committed); "live" is a read-only `gcloud` call on 2026-11-16; "given" was handed to the planning session; "not checked" means that.

**State confirmed before planning:**

- The wiring is not built. `git grep -n "premarket-refresh-late\|premarket-brief-late\|_schedule_brief_slot" origin/main -- gcp/ tests/` returns only the prerequisite's tests (`tests/gcp/test_premarket_brief_late_slot.py:311`, `:1239`, `tests/integration/test_premarket_brief_late_slot_pg.py:127`, `:179`), and the last commit to `gcp/deploy.sh` is #1813 (run).
- The prerequisite is on main: `RUN_SLOTS = ('early', 'late')` at `gcp/premarket_brief.py:3070`, `BRIEF_RUN_SLOT` read at `:3090`, from #1961 (`cbb672c48`) (read).
- Neither late entry exists in the project. `gcloud scheduler jobs list --location=us-east1` shows 65 entries; the premarket ones are `premarket-refresh-daily` `20 8 * * 1-5`, `premarket-brief-daily` `30 8 * * 1-5`, `premarket-brief-sunday` `0 21 * * 0` and `premarket-playbook-resolver-daily` `15 21 * * 1-5`, all America/New_York and ENABLED (live).
- No other plan names this spec or this branch, on main or on any fetched remote branch (run).

**Order:** this plan lands on main through its own `docs/` PR before the feature branch opens. Between Task 1 and Task 3 four tests outside Task 1's file are red by design (Task 2 and Task 3 turn them green); the PR is opened as a draft after Task 1 and is not marked ready before Task 5.

## Global Constraints

Copied from the spec; every task carries them.

- Names and values, verbatim: `premarket-refresh-late`, `premarket-brief-late`, cron `20 9 * * 1-5`, `--time-zone America/New_York`, jobs `fetch-premarket-refresh` and `premarket-brief`, fourth argument `BRIEF_RUN_SLOT=late`, body env exactly `BRIEF_TRIGGERED_BY=cloud-scheduler:NAME` followed by the one `KEY=VALUE` pair.
- `premarket-refresh-late` goes through the existing `_schedule_verified`; `premarket-brief-late` through the new `_schedule_brief_slot NAME CRON JOB ENV_KV`. Each call ends `|| SCHEDULER_FAILURES=$((SCHEDULER_FAILURES + 1))`.
- The diff of `gcp/deploy.sh` holds added lines only (the helper, the two entries, their comments). No existing scheduler entry's name, cron, target or helper changes; `_schedule_brief` and the two entries that use it are not edited.
- These seven stay declared with these crons and targets: `premarket-refresh-daily` (`20 8 * * 1-5`), `premarket-brief-daily` (`30 8 * * 1-5`), `premarket-brief-sunday` (`0 21 * * 0`), `earnings-reactions-brief-daily` (`35 8 * * 1-5`), `insight-pipeline-daily` (`45 8 * * 1-5`), `insight-discord-push-daily` (`15 9 * * 1-5`), `signal-monitor-daily` (`25 9 * * 1-5`).
- No job flag, image, memory, timeout or retry setting changes. No new deploy function, no new test file.
- No change to `gcp/premarket_brief.py`, the insight pipeline, its Discord push or the signal monitor.
- Running the deploy and creating the entries in the project are the owner's close-out steps, not tasks (section "Owner's close-out steps").
- Model registry lines this change edits may name only MODEL-BRIEF-001, MODEL-LEVEL-001 and MODEL-IND-001, and every edited line names at least one of them (`scripts/gate/spec_gate.py:4419-4449`, `check_registry_rows`; read).
- `docs/product/02-FEATURE-CATALOG.md` line 36 ("76 jobs, 65 schedulers") is not edited here: the count describes the live fleet and moves on a `docs/` branch after the deploy (spec, Close-out step 7).
- No em or en dashes in added text. No AI attribution in commits or the PR.

## Capacity

From the spec's Capacity section; the PR body carries it. The job settings were re-read on 2026-11-16 (live): `fetch-premarket-refresh` 1 vCPU, 512Mi, task timeout 300 s, maxRetries 1; `premarket-brief` 1 vCPU, 1Gi, task timeout 1800 s, maxRetries 0. The timings and rates below are the spec's and were not re-measured.

- Runs: each late entry fires once per weekday, about 21 a month; the spec prices 30. The change itself runs nothing until the owner's deploy.
- Late refresh. Volume: up to 50 tickers, one vendor reply each, up to 50 rows upserted. Velocity: 50 vendor calls, about 105 SQL round-trips. Wall-clock: 26 to 54 s over nine executions; the 300 s task timeout is 5.5 times the slowest.
- Late brief. Volume: 3 tickers; 3 canonical rows rewritten, 3 history rows appended. Velocity: the early brief's reads and writes, at most 84 keyed wait queries (one per 5 s for 7 minutes), up to 8 model calls. Wall-clock: 44 to 79 s plus the wait, bounded at 499 s by the 09:27 deadline; the 1800 s task timeout is 3.6 times that worst case.
- Cost per late run, and times 30: refresh compute 0.0010 USD (0.03); brief compute typical 0.0028 USD (0.08), worst case 0.0100 USD (0.30); brief model calls about 0.012 USD (about 0.36; estimate, owner's explicit yes in decision 4); total typical about 0.016 USD a run, about 0.48 USD a month.
- Vendor calls: 50 more a day on a flat subscription. A retried late refresh doubles its calls (maxRetries 1, left as is). Which vendor limit is in force: not checked (spec).
- A late brief that fails every day is stopped by pausing `premarket-brief-late` (owner step 6); the early run is a separate entry.

## Review Focus

Conditions the spec implies and a person running `./gcp/deploy.sh schedulers` will meet, most likely first, each with the test that pins it.

1. A late entry that already exists (every deploy after the first). It must be updated with the same cron, zone, uri and body, not passed over as "already exists" the way `_schedule_brief` does (`gcp/deploy.sh:4287-4300`, read). Pinned in Task 1, the "existing" block.
2. A late entry the owner has paused (owner step 6), then a later `schedulers` deploy. The read back says PAUSED, so the helper returns nonzero and the deploy ends with the error line, never "All schedulers configured." over a late run that is not firing. Pinned in Task 1, the "paused" block. That a real `gcloud scheduler jobs update` leaves a paused entry paused: not checked; the stub models it so.
3. One late entry converges and the other does not. The deploy exits nonzero and names the one that failed, for either entry. Pinned in Task 1, the "drift" block, once per entry.
4. `_schedule_brief_slot` called with a fourth argument that is not `KEY=VALUE`. It refuses before any `gcloud` call; a body with an empty variable name would create an entry that runs the brief in the early slot at 09:20, which is a second full Discord post. Pinned in Task 1 by `test_schedule_brief_slot_refuses_a_fourth_argument_that_is_not_key_value`.
5. The registry row for `premarket-brief-late` copied from its neighbours. The `premarket-brief-daily` row names MODEL-STRAT-001 and MODEL-EARN-001 and the Sunday row names no model; either wording on the new line fails `check_registry_rows` in CI. Pinned by Task 2's exact row text and Task 5's gate run.

Known limit, kept as the spec has it: the helper reads back schedule, uri and state, not the body (done_when[1]). The body is asserted as sent on both branches in Task 1 and read live in owner step 2.

---

### Task 1: The helper, the two entries and their tests

Spec: § Design, "What this spec's change contains"; § Prerequisite, "Order". Advances done_when[0], [1], [2], [3].

**Files:**
- Modify: `tests/gcp/test_deploy_reachability.py` (imports; one appended section)
- Modify: `gcp/deploy.sh` (helper after `_schedule_brief`, which ends at `:4300`; one entry after `:4449`; one entry after `:4840`)

**Interfaces:**
- Consumes: `FNS`, `_closure`, `REPO` of the test file (`:47`, `:52`, `:29`); `_job_uri` (`gcp/deploy.sh:4097`), `_schedule_verified` (`:4183`), `SCHEDULER_FAILURES` (`:4443`, tested at `:5082`).
- Produces: `_schedule_brief_slot NAME CRON JOB ENV_KV` (returns 0 after a verified create or update, 1 otherwise); test helper `_run_schedulers(tmp_path, call="deploy_schedulers", **stub_env) -> (CompletedProcess, list[list[str]], dict[str, dict])`.

- [ ] **Step 1: Add the imports and the stub.** Extend the file's imports to `json`, `os`, `re`, `stat`, `subprocess`. Append a section holding this recording `gcloud` (the answer-yes stub of `tests/gcp/test_deploy_ew_evaluator.py:88-91` cannot serve: a read back from it is empty, so every verified helper fails; run):

```python
_STATEFUL_GCLOUD = r'''#!/usr/bin/env python3
import base64, json, os, pathlib, sys
a = sys.argv[1:]
out = pathlib.Path(os.environ["OUT"])
with (out / "argv.jsonl").open("a") as f:
    f.write(json.dumps(a) + "\n")
if a[:2] != ["scheduler", "jobs"]:
    sys.exit(0)
store = out / "sched"
store.mkdir(exist_ok=True)
def flag(name):
    for i, x in enumerate(a):
        if x == name:
            return a[i + 1]
        if x.startswith(name + "="):
            return x.split("=", 1)[1]
    return None
verb = a[2]
name = a[4] if verb in ("create", "update") else a[3]
path = store / (name + ".json")
seeded = name in os.environ.get("STUB_EXISTING", "").split(",")
if verb in ("create", "update"):
    old = json.loads(path.read_text()) if path.exists() else {}
    headers = flag("--headers") or flag("--update-headers") or ""
    paused = seeded and name in os.environ.get("STUB_PAUSED", "").split(",")
    path.write_text(json.dumps({
        "schedule": flag("--schedule"), "time_zone": flag("--time-zone"),
        "uri": flag("--uri"), "body": flag("--message-body") or "",
        "override": dict(h.split("=", 1) for h in headers.split(",") if h).get("X-HTTP-Method-Override", ""),
        "state": old.get("state", "PAUSED" if paused else "ENABLED"),
    }))
    sys.exit(0)
if verb == "describe":
    if not path.exists():
        if not seeded:
            sys.stderr.write("ERROR: NOT_FOUND: job not found\n")
            sys.exit(1)
        sys.exit(0)
    row = json.loads(path.read_text())
    if os.environ.get("STUB_DRIFT_CRON") == name:
        row["schedule"] = "0 0 * * *"
    fmt = flag("--format") or ""
    fields = {"schedule": row["schedule"], "httpTarget.uri": row["uri"], "state": row["state"],
              "httpTarget.headers.X-HTTP-Method-Override": row["override"],
              "httpTarget.body": base64.b64encode(row["body"].encode()).decode()}
    if fmt.startswith("value(") and fmt.endswith(")"):
        print("\t".join(fields.get(k, "") for k in fmt[6:-1].split(",")))
sys.exit(0)
'''
```

  `STUB_EXISTING` (comma list) makes `describe` succeed before any write; `STUB_PAUSED` makes such an entry read back PAUSED after its update; `STUB_DRIFT_CRON=NAME` makes that entry read back another cron.

- [ ] **Step 2: Add the runner and the constants.** `_run_schedulers` writes the stub to `tmp_path/"bin"/"gcloud"` (executable), runs `bash -c` with `PATH` led by that folder and `OUT=tmp_path` plus `stub_env`, on this script: `set -uo pipefail`, `PROJECT_ID=proj; REGION=us-east1; SA_EMAIL=sa@proj.iam.gserviceaccount.com`, the definition of every function in `_closure({"deploy_schedulers"})` built as `f"{n}() {{{FNS[n]}}}"`, then `call`, then `echo "rc=$?"`. It returns the process, the argv lists from `argv.jsonl` (empty list when the file is absent) and the state files of `sched/` keyed by entry name.

```python
_URI = "https://us-east1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/proj/jobs/{}:run"
_LATE = {"premarket-refresh-late": "fetch-premarket-refresh", "premarket-brief-late": "premarket-brief"}
_LATE_BODY = {"overrides": {"containerOverrides": [{"env": [
    {"name": "BRIEF_TRIGGERED_BY", "value": "cloud-scheduler:premarket-brief-late"},
    {"name": "BRIEF_RUN_SLOT", "value": "late"}]}]}}
_UNCHANGED = {
    "premarket-refresh-daily": ("20 8 * * 1-5", "fetch-premarket-refresh"),
    "premarket-brief-daily": ("30 8 * * 1-5", "premarket-brief"),
    "premarket-brief-sunday": ("0 21 * * 0", "premarket-brief"),
    "earnings-reactions-brief-daily": ("35 8 * * 1-5", "earnings-reactions-brief"),
    "insight-pipeline-daily": ("45 8 * * 1-5", "insight-pipeline"),
    "insight-discord-push-daily": ("15 9 * * 1-5", "insight-discord-push"),
    "signal-monitor-daily": ("25 9 * * 1-5", "signal-monitor"),
}

def _writes(argv, name):
    return [a for a in argv if a[:2] == ["scheduler", "jobs"] and a[2] in ("create", "update") and a[4] == name]
```

- [ ] **Step 3: Write the three tests.**

```python
def test_late_premarket_schedulers_are_declared_and_converge(tmp_path):
    # a project without the entries: both are created, read back and reported verified
    r, argv, sched = _run_schedulers(tmp_path / "fresh")
    assert r.stdout.endswith("All schedulers configured.\nrc=0\n"), r.stdout[-800:] + r.stderr[-800:]
    for name, job in _LATE.items():
        assert (sched[name]["schedule"], sched[name]["time_zone"], sched[name]["uri"], sched[name]["state"]) == \
            ("20 9 * * 1-5", "America/New_York", _URI.format(job), "ENABLED"), name
        assert [a[2] for a in _writes(argv, name)] == ["create"], name
        assert f"  {name}: verified 20 9 * * 1-5" in r.stdout, name
    body = sched["premarket-brief-late"]["body"]
    assert json.loads(body) == _LATE_BODY
    assert body.index("BRIEF_TRIGGERED_BY") < body.index("BRIEF_RUN_SLOT")
    assert sched["premarket-refresh-late"]["body"] == ""
    for name, (cron, job) in _UNCHANGED.items():
        assert (sched[name]["schedule"], sched[name]["time_zone"], sched[name]["uri"]) == \
            (cron, "America/New_York", _URI.format(job)), name

    # entries that already exist: one update each, carrying the same cron, zone, uri and body
    r, argv, sched = _run_schedulers(tmp_path / "existing", STUB_EXISTING=",".join(_LATE))
    assert r.stdout.endswith("rc=0\n"), r.stderr[-800:]
    for name, job in _LATE.items():
        assert [a[2] for a in _writes(argv, name)] == ["update"], name
        assert (sched[name]["schedule"], sched[name]["time_zone"], sched[name]["uri"]) == \
            ("20 9 * * 1-5", "America/New_York", _URI.format(job)), name
    assert json.loads(sched["premarket-brief-late"]["body"]) == _LATE_BODY

    # a read back that differs: the helper returns nonzero and deploy_schedulers counts it
    for name in _LATE:
        r, _, _ = _run_schedulers(tmp_path / f"drift-{name}", STUB_DRIFT_CRON=name)
        assert r.stdout.endswith("rc=1\n") and "All schedulers configured." not in r.stdout, name
        assert f"ERROR: {name} read back as [0 0 * * *" in r.stderr, r.stderr[-800:]

    # a paused entry is reported, not passed over as configured
    r, _, sched = _run_schedulers(tmp_path / "paused", STUB_EXISTING="premarket-brief-late",
                                  STUB_PAUSED="premarket-brief-late")
    assert sched["premarket-brief-late"]["state"] == "PAUSED"
    assert r.stdout.endswith("rc=1\n") and "ERROR: premarket-brief-late read back as" in r.stderr


def test_schedule_brief_slot_refuses_a_fourth_argument_that_is_not_key_value(tmp_path):
    for i, bad in enumerate(("BRIEF_RUN_SLOT", "=late", "")):
        r, argv, sched = _run_schedulers(
            tmp_path / str(i), call=f"_schedule_brief_slot n '20 9 * * 1-5' premarket-brief '{bad}'")
        assert r.stdout.endswith("rc=1\n") and argv == [] and sched == {}, (bad, r.stdout, r.stderr)
        assert "must be KEY=VALUE" in r.stderr, bad


def test_late_brief_scheduler_needs_the_late_slot_in_the_image():
    from gcp import premarket_brief
    assert "late" in premarket_brief.RUN_SLOTS
```

  Compare `rc` with `endswith`, never `"rc=1" in`: a missing function ends `rc=127`, which contains `rc=1` (run).

- [ ] **Step 4: Run** `python3 -m pytest tests/gcp/test_deploy_reachability.py -q`. Expected (run): 2 failed, 31 passed. `test_late_premarket_schedulers_are_declared_and_converge` fails with `KeyError: 'premarket-refresh-late'` (its first assertion passes, which shows every existing verified helper converges under the stub on main); the refusal test fails on `_schedule_brief_slot: command not found`. `test_late_brief_scheduler_needs_the_late_slot_in_the_image` passes at once: it is not a failing-first test but the merge-order guard of done_when[3], green because #1961 is on main.

- [ ] **Step 5: Implement `_schedule_brief_slot NAME CRON JOB ENV_KV`** in `gcp/deploy.sh`, between the closing brace of `_schedule_brief` (`:4300`) and the comment that opens `_schedule_insight` (`:4302`), under a comment saying what it does differently from `_schedule_brief`. In order:
  - `local NAME=$1 CRON=$2 JOB=$3 ENV_KV=$4 uri live`.
  - Refusal first: unless `ENV_KV` matches the `case` pattern `[A-Z_]*=?*`, print `  ERROR: ${NAME}: the fourth argument must be KEY=VALUE, got [${ENV_KV}]` to stderr and `return 1`.
  - The body, exactly: `local BODY='{"overrides":{"containerOverrides":[{"env":[{"name":"BRIEF_TRIGGERED_BY","value":"cloud-scheduler:'"${NAME}"'"},{"name":"'"${ENV_KV%%=*}"'","value":"'"${ENV_KV#*=}"'"}]}]}}'`.
  - The describe, update, create and three-field read back of `_schedule_with_args_verified` (`:4393-4423`), unchanged in shape: `--update-headers "Content-Type=application/json"` on update, `--headers "Content-Type=application/json"` on create, `--message-body "${BODY}"`, `--time-zone "America/New_York"`, `--uri "$(_job_uri "${JOB}")"` held in `uri`, the same four `ERROR:` lines, each with `return 1`. No body read back (done_when[1] names schedule, uri and state).
  - Last line: `echo "  ${NAME}: verified ${CRON} ${ENV_KV}"`.

- [ ] **Step 6: Add the two entries**, each with the comment the spec gives (§ "What this spec's change contains"):
  - directly after `_schedule_brief "premarket-brief-daily" ...` (`:4449`): `_schedule_brief_slot "premarket-brief-late" "20 9 * * 1-5" "premarket-brief" "BRIEF_RUN_SLOT=late" \` and on the next line `|| SCHEDULER_FAILURES=$((SCHEDULER_FAILURES + 1))`;
  - directly after `_schedule "premarket-refresh-daily" ...` (`:4840`): `_schedule_verified "premarket-refresh-late" "20 9 * * 1-5" "fetch-premarket-refresh" \` and the same counter line.

- [ ] **Step 7: Run and check.**
  - `bash -n gcp/deploy.sh`: no output.
  - `git diff origin/main -- gcp/deploy.sh | grep -c '^-[^-]'`: prints `0` (added lines only; run on the scratch copy, 55 added lines).
  - `python3 -m pytest tests/gcp/test_deploy_reachability.py tests/gcp/test_deploy_ew_evaluator.py tests/gcp/test_phase6_playbook_scheduler.py tests/gcp/test_strat_engine_scheduler.py -q`: all pass (run on the scratch copy: the reachability file 33 passed in about 20 s, the convergence test running `deploy_schedulers()` five times).
  - Expected and left for Tasks 2 and 3 (run: exactly these four fail, 430 pass, 2 skipped across `tests/meta`, the four files above and `tests/scripts/test_doc_inventory.py`): `test_every_scheduled_model_bearing_job_is_listed`, `test_every_live_scheduler_is_classified`, `test_reconcile_against_snapshot_reports_the_known_deltas`, `test_the_committed_05a_renders_byte_identically_with_the_retry_split`.

- [ ] **Step 8: Commit** `python3 scripts/gate/spec_gate.py --commit`, then `git add gcp/deploy.sh tests/gcp/test_deploy_reachability.py` and `git commit -m "feat(deploy): declare the late premarket refresh and brief schedulers at 09:20 ET"`. Push and open the PR as a draft titled `FEAT-DEPLOY-001: a late premarket run, refresh and brief schedulers at 09:20 ET`.

### Task 2: Model registry rows and the generated JSON

Spec: § Design, "Documents the change must carry"; § Intake, "Models named". Advances done_when[4].

**Files:**
- Modify: `docs/product/07-MODEL-REGISTRY.md` (one added row after `:362`; the first cell of the row at `:395`)
- Modify: `docs/product/generated/model-registry.json` (regenerated)

- [ ] **Step 1: Run** `python3 -m pytest tests/meta/test_model_registry_consistency.py -q -k "model_bearing_job_is_listed or live_scheduler_is_classified"`; expected FAIL, naming `premarket-brief-late -> premarket-brief` and both late names as unclassified.
- [ ] **Step 2: Add the row** after the `premarket-brief-sunday` row of the scheduler table (`:362`), exactly:

  `` | `premarket-brief-late` | `20 9 * * 1-5` | `premarket-brief` | MODEL-BRIEF-001 and MODEL-LEVEL-001: the same job in its late slot (`BRIEF_RUN_SLOT=late`), which waits for the 09:20 premarket refresh, rebuilds the levels from that snapshot and rewrites the session's canonical `premarket_analysis` row before the open | ``

- [ ] **Step 3: Name the late refresh on the existing exclusion row** (`:395`, the one that cites MODEL-IND-001): its first cell becomes `` `premarket-refresh-daily` · `premarket-refresh-late` `` (the middle-dot form the `av-intraday-nightly` row at `:396` uses, which `_table_schedulers` reads from the first cell; `tests/meta/test_model_registry_consistency.py:2060-2068`, read). No other byte of that row changes. Neither edit carries a date, so the document's Last reviewed stamp stays valid.
- [ ] **Step 4: Regenerate** `python3 scripts/gate/export_model_registry.py`; expected output ends `35 schedulers` (34 on main; run).
- [ ] **Step 5: Run** `python3 -m pytest tests/meta/test_model_registry_consistency.py -q`; expected PASS (run with Task 3's changes also applied).
- [ ] **Step 6: Commit** `git add docs/product/07-MODEL-REGISTRY.md docs/product/generated/model-registry.json` and `git commit -m "docs(registry): classify the two late premarket schedulers"`.

### Task 3: The inventory render and its reconcile expectation

Spec: § Design, "Documents the change must carry". Advances done_when[5].

**Files:**
- Modify: `docs/product/infrastructure/05-a-ARCHITECTURE.md` (inventory blocks only, by the renderer)
- Modify: `tests/scripts/test_doc_inventory.py:275`

- [ ] **Step 1: Change the expectation** at `:275` to `assert rec["schedulers_repo_only"] == ["earnings-sweep-sunday", "premarket-brief-late", "premarket-refresh-late"]`, and add to the comment above it one sentence: both late entries are repo-only until the owner's deploy and a fresher snapshot (FEAT-DEPLOY-001, late premarket run).
- [ ] **Step 2: Run** `python3 -m pytest tests/scripts/test_doc_inventory.py -q -k "reconcile_against_snapshot or committed_05a"`; expected: the reconcile test passes, `test_the_committed_05a_renders_byte_identically_with_the_retry_split` still fails.
- [ ] **Step 3: Render** `python3 scripts/maintenance/doc_inventory.py --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --insert docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`. Expected (run): `05-a-ARCHITECTURE.md: updated`, the other two `unchanged`. The 05-a diff is four lines: two added scheduler rows (`premarket-brief-late` with args cell `BRIEF_RUN_SLOT=late`, `premarket-refresh-late`, both `**not live** (declared in deploy.sh)`), `Repo declares 67 jobs / 67 schedulers; live has 76 / 65`, and `**Schedulers in deploy.sh but not live** (3)` naming the three. If 05-c or 05-e reports `updated`, stop: another input changed and that is not this change's.
- [ ] **Step 4: Run** `python3 -m pytest tests/scripts/test_doc_inventory.py tests/scripts/test_check_generated_docs.py tests/meta/test_model_registry_consistency.py -q`; expected PASS (run with Tasks 1 and 2 applied: these three files with the two deploy test files, 395 passed, 2 skipped).
- [ ] **Step 5: Commit** `git add docs/product/infrastructure/05-a-ARCHITECTURE.md tests/scripts/test_doc_inventory.py` and `git commit -m "docs(inventory): render the two late premarket schedulers into 05-a"`.

### Task 4: The DASHBOARD-01 implementation-source note and the source snapshot

Spec: frontmatter `site_source_notes: [DASHBOARD-01]`; § Design, last line of "Documents the change must carry". Advances done_when[6]. Protocol: `.claude/skills/product-delivery/SKILL.md`, "Committed-source documentation identity".

**Depends on PR #2011 (another lane).** `scripts/maintenance/doc_source_snapshot.py verify` refuses a counted input over 12,582,912 bytes (`MAX_BYTES`, `:35`; read), and no caller may raise the cap. Given by the coordinating session, not checked from the planning session (no GitHub access): the tree is currently refused as over 12 MiB and #2011 is the fix. Run on `origin/main` `c9a2b984` on 2026-11-16: `verify` returned `identity-matched` with `counted_bytes` 12233575, 349,337 bytes under the cap, so the planning session did not reproduce the refusal at that commit. If `produce` or `verify` refuses on size here, this task waits for #2011 on main and then uses the verify command main documents; the cap is never raised from this branch and the task is never skipped.

**Files:**
- Modify: `docs/product/03-SITE-TRACEABILITY.md` (one added row in the `## Implementation-source notes` table, `:1297`)
- Modify: `docs/review-evidence/site-source-snapshot.json` (produced)

- [ ] **Step 1: Preflight** `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`; copy the reported `source_identity_sha256`. (Run on the plan's docs branch it answers `ordinary production requires its actual named feature branch/source`, so this step was not exercised for the plan.)
- [ ] **Step 2: Add one row** in sorted position, after the last FEAT-DATA-001 row and before `| FEAT-DEPLOY-001 | SHARED-01 |`:

  `` | FEAT-DEPLOY-001 | DASHBOARD-01 | source_identity_sha256=<identity from Step 1>; `gcp/deploy.sh` (`deploy_schedulers`) declares two Cloud Scheduler entries at `20 9 * * 1-5` America/New_York as this element's backend source: `premarket-refresh-late` runs `fetch-premarket-refresh` again through `_schedule_verified`, and `premarket-brief-late` runs `premarket-brief` with `BRIEF_RUN_SLOT=late` through `_schedule_brief_slot`, the slot that rewrites the canonical `premarket_analysis` row the brief endpoint reads. Test: `tests/gcp/test_deploy_reachability.py` (`test_late_premarket_schedulers_are_declared_and_converge`, `test_late_brief_scheduler_needs_the_late_slot_in_the_image`). Implementation source only: neither entry exists in the project until the owner's deploy. | ``

  No other byte of the document changes. Commit `docs(site): DASHBOARD-01 implementation-source note for the late premarket schedulers`.
- [ ] **Step 3: Produce** with the Step 1 command and commit the sidecar: `docs(evidence): site source snapshot for the late premarket schedulers`.
- [ ] **Step 4: Verify** `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000`; expected exit 0 with `"status": "identity-matched"`. After any later commit that changes watched code, the document body or the policy, repeat Steps 1 to 4.

### Task 5: Close

Spec: § Done when. Closes done_when[7] and re-checks [0] to [6].

**Files:**
- Modify: `docs/product/02-FEATURE-CATALOG.md` (the FEAT-DEPLOY-001 record at `:536`: Status and Last reviewed only)
- Modify: `docs/product/12-PR-ISSUE-TRACEABILITY.md` (the FEAT-DEPLOY-001 PR lineage line at `:318`)
- Modify: this plan (`pr`)

- [ ] **Catalog record:** append to the Status cell `; late premarket run declared: `premarket-refresh-late` and `premarket-brief-late` at `20 9 * * 1-5` America/New_York ([#<this PR>](https://github.com/TeneikaAskew/stocks/pull/<this PR>), spec [#1929](https://github.com/TeneikaAskew/stocks/pull/1929)), creating them in the project is the owner's close-out`; set Last reviewed to the day of the edit. Line 36 of the table is not touched.
- [ ] **Traceability:** append ` · [#<this PR>](https://github.com/TeneikaAskew/stocks/pull/<this PR>) *remediation*` to the line at `:318`. Set this plan's `pr` to the number.
- [ ] **Suites:** `bash -n gcp/deploy.sh`; `python3 -m pytest tests/gcp/test_deploy_reachability.py tests/gcp/test_phase6_playbook_scheduler.py tests/gcp/test_strat_engine_scheduler.py tests/meta/test_model_registry_consistency.py tests/scripts/test_doc_inventory.py -q`; all pass.
- [ ] **Docs audit:** `python3 scripts/maintenance/docs_audit.py` on the branch and on `origin/main`; the branch reports nothing main does not. (Not run for this plan.)
- [ ] **Gate:** `python3 scripts/gate/spec_gate.py --pr origin/main`; ok. (`check_registry_rows` runs only here and in CI; not run for this plan.)
- [ ] **PR body:** the spec and this plan by path; each done_when item as a `- [ ]` line starting with its text, ticked with its evidence (test name, command output, file); the Capacity section above with Volume, Velocity, Wall-clock and cost; the line `Canvas check pending (report-only): https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN` (`docs/product/canvases.yml:53-55`, read); the owner's close-out steps below, as not done. Then mark the PR ready and follow CLAUDE.md 2.5 for review.
- [ ] **After the merge**, on a `docs/` branch: this plan's `status: done`.

## Owner's close-out steps (not tasks; on the owner's yes, after the merge)

From the spec's Close-out section, with what was read live on 2026-11-16.

1. Deploys, in this order: `./gcp/deploy.sh premarket` (`build_image deploy_premarket`, `gcp/deploy.sh:5370`), `./gcp/deploy.sh market-data` (the one single target that calls `deploy_fetch_premarket_refresh`, `:5397`), `./gcp/deploy.sh schedulers` (`:5398`). Live: `premarket-brief` was last updated 2026-11-15T22:41Z, after #1961 merged (07:33Z); `fetch-premarket-refresh` was last updated 2026-11-15T05:34Z, before it, so by that timestamp its image predates the newest-bar log line. Which commit either image was built from: not checked. A deploy is dropped only when the job's image digest and build commit are read and recorded as holding the prerequisite.
2. `gcloud scheduler jobs describe premarket-refresh-late --location=us-east1` and the same for `premarket-brief-late`: `20 9 * * 1-5`, `America/New_York`, `ENABLED`, and for the brief the decoded body with both variables. `gcloud run jobs describe` for both jobs: the image is the digest step 1 built. Record the output on the PR.
3. On a session day, at or after 09:35 ET and never before 09:20: `gcloud scheduler jobs run` for both entries once. Expected: a late brief that logs its slot and refuses the canonical write as past the cutoff; the refresh log holds the newest-bar line for each brief ticker.
4. The prerequisite's replay of a past date in the late slot, per its own spec (CLAUDE.md 3.5).
5. After the first scheduled late run: `gcloud run jobs executions list` for both jobs; a query showing history rows with `triggered_by = 'cloud-scheduler:premarket-brief-late'` written before 09:29:30 ET, the canonical `level_basis` premarket `fetched_at` at or after 09:20 ET, and its `pre_high` and `pre_low` beside the maximum and minimum of `market_data_intraday` through 09:19; the signal monitor's log showing its first level use after that write. Record the date as the start of the late-levels series.
6. To stop the late run: `gcloud scheduler jobs pause premarket-brief-late --location=us-east1` (and `premarket-refresh-late`). The early run is untouched. A later `./gcp/deploy.sh schedulers` then reports the paused entry and exits nonzero (Review Focus 2).
7. On a `docs/` branch after the deploy: the scheduler count where documents state it (65 today, 67 after) and a fresh live snapshot, after which the two names leave `schedulers_repo_only` in `tests/scripts/test_doc_inventory.py`.

## Not checked for this plan

- GitHub: PR #2011's content and state, open issues, open PRs. Only fetched refs and the local clone were read.
- `doc_source_snapshot.py produce` and the note cycle on a feature branch; `docs_audit.py`; `spec_gate.py --pr` against the built change.
- The entries against a real Cloud Scheduler: the create, update and read back were run against the stub only. No write was made to the project.
- The spec's measurements (run times, costs, vendor limits) were copied, not re-measured.
