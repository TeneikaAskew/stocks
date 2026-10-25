---
feat_id: FEAT-DEPLOY-001
spec: docs/superpowers/specs/2026-10-11-feat-deploy-001-retired-service-leftovers.md
branch: feature/feat-deploy-001-retired-service-leftovers
pr: 1384
status: ready
---

# Stop drawing and describing the retired API service: implementation plan

> For agentic workers: REQUIRED SUB-SKILL: superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans. Steps use `- [ ]` checkboxes. Every task cites a spec section and the
> done_when item it advances; done_when[n] counts from 0 in the spec's frontmatter order (r2, 12 items).

**Goal:** Nothing the stocks repo generates or serves (the two drawio diagrams and their generator,
the OpenAPI description, the `/dev` page) names `solyra-api-prod` as live; the diagrams are
regenerated from a fresh, complete live snapshot; and the generator refuses a snapshot it would turn
into "0 relations".

**Architecture:** The generator gains a `db_tables` guard in `main()` and a short label for
digest-pinned images. Its REPLACEMENTS get new entries whose sources are today's committed labels,
two cells leave by id, and `check()` / `check_icons()` reject the old names. A fresh live snapshot,
read through `db_query_cr.sh` and `doc_inventory --live`, becomes the drawio test's fixture, and both
diagrams are regenerated from it as the monthly workflow regenerates them. The ping docstring change
flows into `platform/api/openapi.json`, which solyra vendors, so a solyra feature PR carries the sync.

**Tech Stack:** Python 3.11, pytest, `xml.etree.ElementTree`, FastAPI `TestClient`, `gcloud`, `jq`.

**Spec:** `docs/superpowers/specs/2026-10-11-feat-deploy-001-retired-service-leftovers.md` (r2,
stocks#1381). This plan lands on its own `docs/` branch after #1381 merges, at
`docs/superpowers/plans/2026-10-11-feat-deploy-001-retired-service-leftovers.md`; the implementation
branch is cut from `origin/main` after that.

## Global Constraints

- Branch `feature/feat-deploy-001-retired-service-leftovers`, cut from `origin/main` once #1381 and
  this plan are on it. Never commit to `main`; never force-push; no `git rebase` / `reset --hard` on
  the pushed branch.
- Run `python3 scripts/gate/spec_gate.py --commit` before every commit. Conventional, imperative
  commit messages; no AI attribution or Co-Authored-By line (CLAUDE.md §2 overrides any harness
  default).
- PR title `FEAT-DEPLOY-001: stop drawing and describing the retired API service`. Body: the spec and
  plan paths; each done_when item as a `- [ ]` line starting with its exact text;
  `Canvas check pending (report-only): https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN`; the
  db-query execution name; and `Capacity: n/a: no workload changes. The snapshot recipe is one
  read-only db-query execution (one pg_class scan, about 100 rows) and the list calls doc_inventory
  --live already makes. The merge redeploys solyra-api-staging through deploy-solyra-api-staging (it
  fires on a push to main touching platform/, lib/, requirements.txt or gcp/database.py) with the same
  behaviour.`
- Unchanged by this branch: `tests/fixtures/live_gcp_snapshot_2026-09-07.json`; 05-a, 05-c, 05-d,
  05-e and their `manual/` copies; `gcp/schema.sql`; the deploy scripts' retirement lines; the `iap`
  auth mode; the monthly workflow.
- `platform/api/main.py` keeps its line count (1731 on `089f271e`): 05-a and 05-e cite its lines
  607-1510 and a feature branch may not re-render those blocks (`check_product_scope`). The ping
  docstring keeps its first line, which those blocks render as the route summary.
- Every `gcloud` call, and `db_query_cr.sh`, runs as `env -u CLOUDSDK_AUTH_ACCESS_TOKEN ...` in a
  Remote session (stocks CLAUDE.md, "GCP credentials").
- Review cap: two rounds, then split, re-cut or discard.

## Review Focus

1. `ic_tp`'s label (`solyra-api-staging / -prod`) is the first line of `p4_tp`'s. If the `ic_tp`
   entry ran first, `p4_tp`'s full-label entry would stop matching and "prod is IAP" would survive.
   Pinned by `test_the_api_cells_describe_no_prod_or_iap_service[p4_tp]` (Task 3).
2. A count the regeneration cannot reach stays stale beside the fresh ones. Measured on the
   2026-10-11 snapshot: the icon subtitle `sub` kept `95-relation Cloud SQL` while every note read 98,
   because `refresh_icons` and `check_icons` know `N relations` but not `N-relation`. Pinned by
   `test_a_stale_relation_count_on_the_icon_page_is_caught_and_rewritten` (Task 3).
3. A reference carrying both a tag and a digest (`name:tag@sha256:...`) is pinned by the digest and
   must be labelled by it; before this change it printed `research@sha256`. Pinned by the third job in
   `test_an_add_on_job_is_labelled_by_digest_prefix_or_tag` (Task 2).
4. A second regeneration must change nothing: a REPLACEMENTS target that contains a source rewrites
   a label on every monthly run. Pinned by Task 3 Step 9 (re-run on the committed head, `git diff
   --exit-code`), not by a permanent byte-equality test: the output also depends on `gcp/schema.sql`
   (declared relations), `gcp/deploy.sh` (★ marks) and the workflow count, so such a test would fail
   every unrelated PR that adds a table or a `deploy_*` function.
5. The snapshot file must be named for its `read_at` date, and the shared 2026-09-07 fixture must stay
   byte-identical with its readers green. Pinned by Task 3 Step 4 (date and key check) and Step 8
   (`git diff --exit-code` on the shared file) and Step 9 (its readers run).

---

## Task 1: the generator refuses a snapshot without table statistics

Spec: § Design, "Relations fallback"; § Problem, third bullet. Advances done_when[2].

**Files:**
- Modify: `scripts/maintenance/refresh_architecture_drawio.py` (`main()` after line 560; the three
  `db_tables` reads at lines 260, 334 and 441)
- Test: `tests/scripts/test_refresh_architecture_drawio.py`

**Interfaces:**
- Produces (test module): `DIAGRAMS = ("Architecture.drawio", "Architecture-icons.drawio")` and
  `_diagram_copies(tmp_path, monkeypatch) -> list[tuple[Path, Path]]`, which copies both committed
  diagrams into `tmp_path`, monkeypatches `dw.MAIN` / `dw.ICONS` to the copies and returns
  `(committed, copy)` pairs.
- Produces (generator): `main()` returns `2` after printing
  `::error::<snapshot> has no db_tables; rebuild it with --db-tables (DB_TABLES_SQL through scripts/db_query_cr.sh). Neither diagram was written.`
  when `live.get("db_tables")` is falsy, before either diagram is parsed.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.parametrize("tables", [None, {}], ids=["missing", "empty"])
def test_main_refuses_a_snapshot_without_db_tables(tmp_path, monkeypatch, tables):
    snap = json.loads(SNAPSHOT.read_text())
    if tables is None:
        del snap["db_tables"]
    else:
        snap["db_tables"] = tables
    path = tmp_path / "live.json"
    path.write_text(json.dumps(snap))
    pairs = _diagram_copies(tmp_path, monkeypatch)
    assert dw.main(["--snapshot", str(path)]) != 0
    for committed, copy in pairs:
        assert copy.read_bytes() == committed.read_bytes(), committed.name
```

- [ ] **Step 2: Run (RED)**

Run: `python3 -m pytest tests/scripts/test_refresh_architecture_drawio.py -k refuses -q`
Expected: 2 failed, `AssertionError: assert 0 != 0` (origin/main writes "0 relations" and exits 0).

- [ ] **Step 3: Implement** the guard right after `live = json.loads(...)` in `main()`, with a comment
  naming Rule 3.7 and the monthly workflow's own guard; replace `len(live.get('db_tables', {}))`
  (lines 260, 334) and `len(live.get("db_tables") or {})` (line 441) with `len(live["db_tables"])`.

- [ ] **Step 4: Run (GREEN)** — `python3 -m pytest tests/scripts/test_refresh_architecture_drawio.py -q`,
  all pass.

- [ ] **Step 5: Commit** `fix(drawio): refuse a snapshot without table statistics`

## Task 2: a digest-pinned image gets a short label

Spec: § Design, "Digest-pinned images"; § Risks, second bullet. Advances done_when[4].

**Files:**
- Modify: `scripts/maintenance/refresh_architecture_drawio.py` (lines 319-320; new helper above
  `_cells`)
- Test: `tests/scripts/test_refresh_architecture_drawio.py`

**Interfaces:**
- Produces: `image_label(image: str) -> str`. On the last path segment of the reference: with an
  `@`, the algorithm, `:` and the digest's first 12 characters (`sha256:0123456789ab`); else the text
  after the first `:`; else `latest`. The grid sets `tag = image_label(j["image"])`; the research fill
  (line 323) keeps reading `tag`.

- [ ] **Step 1: Write the failing test**

```python
def test_an_add_on_job_is_labelled_by_digest_prefix_or_tag(main_root, live):
    page = main_root.findall("diagram")[0]

    def cards() -> dict[str, str]:
        return {c.get("value").split("\n")[0].replace(" ★", ""): c.get("value")
                for c in page.iter("mxCell") if (c.get("id") or "").startswith("addon_job_")}

    pinned, tagged, both = sorted(cards())[:3]
    digest = "0123456789ab" + "c" * 52
    repo = "us-east1-docker.pkg.dev/p/trading/trading-system"
    jobs = dict(live["jobs"])
    jobs[pinned] = dict(jobs[pinned], image=f"{repo}@sha256:{digest}")
    jobs[tagged] = dict(jobs[tagged], image=f"{repo}:research")
    jobs[both] = dict(jobs[both], image=f"{repo}:research@sha256:{digest}")
    dw.refresh_main(main_root, dict(live, jobs=jobs))
    assert "• sha256:0123456789ab •" in cards()[pinned]
    assert digest not in cards()[pinned]
    assert "• research •" in cards()[tagged]
    assert "• sha256:0123456789ab •" in cards()[both]
```

- [ ] **Step 2: Run (RED)**

Run: `python3 -m pytest tests/scripts/test_refresh_architecture_drawio.py -k digest -q`
Expected: 1 failed, `assert '• sha256:0123456789ab •' in 'audit-brief-bias\npython -m gcp.audit_job_runner\n1Gi/1cpu • 0123456789abccc… • last 2026-09-06'`.

- [ ] **Step 3: Implement** `image_label`, its docstring saying the 64-character digest overflowed its
  240-pixel box, and use it at line 320.

- [ ] **Step 4: Run (GREEN)** — `python3 -m pytest tests/scripts/test_refresh_architecture_drawio.py -q`:
  `13 passed` (the 2026-09-07 fixture is still `SNAPSHOT` here).

- [ ] **Step 5: Commit** `fix(drawio): label a digest-pinned image by its digest prefix`

## Task 3: a fresh snapshot, one API service, and both diagrams regenerated

Spec: § Design, "Fresh snapshot" and "Drawio generator and diagrams"; § Problem, first and second
bullets. Advances done_when[0], done_when[1] and done_when[3].

**Files:**
- Create: `tests/fixtures/live_gcp_snapshot_<read date>.json`
- Modify: `tests/scripts/test_refresh_architecture_drawio.py`
- Modify: `scripts/maintenance/refresh_architecture_drawio.py` (REPLACEMENTS lines 39-91,
  DELETE_IDS line 94, NEW_CELLS lines 96-106, docstring line 12, banner line 337, `ICON_STALE` lines
  364-365, `refresh_icons` patterns lines 475-482, `check_icons` patterns lines 501-507, `check()`
  lines 533-541)
- Regenerate: `Architecture.drawio`, `Architecture-icons.drawio`

**Interfaces:**
- Consumes: the `main()` guard (Task 1), which the new snapshot passes, and `image_label` (Task 2),
  which the regeneration applies to every add-on card.
- Produces (test module): `SNAPSHOT` = the new fixture; `RETIRED_SERVICE = "solyra-api-prod"`,
  `RETIRED_TRIGGER = "deploy-solyra-api-prod"`,
  `API_SERVICE_EDGES = {"e_browser_tp", "e_tp_sql", "e_tp_ct", "e_lib_tp"}`,
  `FORBIDDEN = ("solyra-api-prod", "staging / -prod", "IAP", "AUTH_MODE iap", "AUTH_MODE=iap")`.
- Produces (generator): `NEW_CELLS: list[tuple[str, str, str, int, int, int, int]] = []`;
  `DELETE_IDS` gains `"svc_st"`, `"gha_dep"`; `check()` reports `stale label still present: <s>` and
  `check_icons()` reports `icons: stale label '<s>'` for `s` in `solyra-api-prod`, `staging / -prod`;
  `refresh_icons` rewrites and `check_icons` checks `N-relation` as it does `N relations`.

- [ ] **Step 1: Write the snapshot test against the 2026-09-07 fixture**

Add `import re` and the constants above (`SNAPSHOT` still the 2026-09-07 file), and:

```python
def test_the_snapshot_lists_no_retired_service(live):
    assert RETIRED_SERVICE not in live["services"]
    assert RETIRED_TRIGGER not in {t["name"] for t in live["cloudbuild_triggers"]}
```

- [ ] **Step 2: Run it (RED)**

Run: `python3 -m pytest tests/scripts/test_refresh_architecture_drawio.py -k snapshot_lists -q`
Expected: FAIL, `assert 'solyra-api-prod' not in {'discord-interactions': ..., 'solyra-api-prod': ...}`.
Keep this output: it is the only run that shows this assertion failing on `origin/main`, because from
Step 5 on it reads the new file.

- [ ] **Step 3: Read the fresh snapshot**

```bash
W="$(mktemp -d)"
SQL="$(python3 -c 'from scripts.maintenance.doc_inventory import DB_TABLES_SQL; print(DB_TABLES_SQL)')"
env -u CLOUDSDK_AUTH_ACCESS_TOKEN ./scripts/db_query_cr.sh -q "$SQL"   # logs "execution: db-query-xxxxx"
EXEC=db-query-xxxxx                                                    # the name it logged
env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud storage cp \
  "gs://adept-mountain-474619-d4-trading-data/query-results/$EXEC/result_001.csv" "$W/db_tables.csv"
SNAP="tests/fixtures/live_gcp_snapshot_$(date -u +%F).json"
env -u CLOUDSDK_AUTH_ACCESS_TOKEN python3 -m scripts.maintenance.doc_inventory --live \
  --db-tables "$W/db_tables.csv" --write-snapshot "$SNAP"
```

Expected on the 2026-10-11 read (`db-query-qwhjn`): `wrote ...: {'jobs': 76, 'paused_schedulers': 0,
'schedulers': 65, 'secrets': 22, 'services': 3}` and 98 CSV rows. A later read may differ in counts;
the steps below hold for whatever it reads. Record `$EXEC` for the PR body.

- [ ] **Step 4: Check the snapshot before using it**

```bash
python3 - "$SNAP" <<'EOF'
import json, sys, pathlib
new = json.loads(pathlib.Path(sys.argv[1]).read_text())
old = json.loads(pathlib.Path("tests/fixtures/live_gcp_snapshot_2026-09-07.json").read_text())
assert sorted(new) == sorted(old), set(new) ^ set(old)
assert sys.argv[1].endswith(new["read_at"][:10] + ".json"), new["read_at"]
assert new["db_tables"] and all(isinstance(s, str) for s in new["secrets"])
print(new["read_at"], new["counts"], len(new["db_tables"]), sorted(new["services"]),
      [t["name"] for t in new["cloudbuild_triggers"]])
EOF
```

Expected: no assertion error; services `['discord-interactions', 'failure-notifier',
'solyra-api-staging']`, triggers `['deploy-solyra-api-staging', 'apply-schema-on-change']`. If the
read crossed UTC midnight, rename the file to its `read_at` date.

- [ ] **Step 5: Point the test at it and write the remaining tests**

`SNAPSHOT = REPO / "tests/fixtures/live_gcp_snapshot_<read date>.json"`; the `live` fixture is
unchanged (it reads `SNAPSHOT`).

Changed tests:
- `test_the_committed_diagram_agrees_with_the_snapshot`: add
  `assert dw.check_icons(ET.parse(dw.ICONS).getroot(), live) == []`.
- `test_a_stale_service_count_is_caught` (lines 125-133): `n = live["counts"]["services"]` and
  `live_plus` with `services=n + 1`; assert `f"svc_group says {n} Cloud Run Services, live is {n + 1}"`
  is in a problem and `f"Cloud Run Services ({n + 1};"` is in `svc_group` after `_rewrite_main_counts`.
- `test_the_deleted_prod_service_name_is_rejected` (line 140): replace `"solyra-api-staging"` with
  `"trading-platform"` in `svc_tp`.

New tests:

```python
def test_no_generated_text_names_the_retired_service(main_root, live):
    dw.refresh_main(main_root, live)
    notes = [c.get("value") for c in main_root.iter("mxCell")
             if (c.get("id") or "").startswith(dw.ADDON_PREFIX)]
    icons = ET.parse(dw.ICONS).getroot()
    dw.refresh_icons(icons, live)
    notes += [c.get("value") for c in icons.iter("mxCell")
              if "reconciliation note" in (c.get("value") or "").lower()]
    written = [rep for _old, rep in dw.REPLACEMENTS] + [cell[1] for cell in dw.NEW_CELLS] + notes
    assert [(bad, t) for t in written for bad in FORBIDDEN if bad in t] == []

@pytest.mark.parametrize("stale", ["solyra-api-prod", "staging / -prod"])
def test_check_reports_a_cell_naming_the_retired_service(main_root, live, stale):
    c = _cell(main_root, "svc_tp")
    c.set("value", c.get("value") + "\n" + stale)
    assert f"stale label still present: {stale}" in dw.check(main_root, live)

@pytest.mark.parametrize("stale", ["solyra-api-prod", "staging / -prod"])
def test_check_icons_reports_a_cell_naming_the_retired_service(live, stale):
    icons = ET.parse(dw.ICONS).getroot()
    c = _cell(icons, "ic_tp")
    c.set("value", c.get("value") + " " + stale)
    assert f"icons: stale label {stale!r}" in dw.check_icons(icons, live)

@pytest.mark.parametrize("name", DIAGRAMS)
def test_the_committed_diagrams_do_not_draw_the_retired_service(name):
    text = (REPO / name).read_text(encoding="utf-8")
    for gone in ("solyra-api-prod", "staging / -prod", "2026-09-07"):
        assert gone not in text, gone

@pytest.mark.parametrize("path,cid", [(dw.MAIN, "p4_tp"), (dw.ICONS, "tp_txt")], ids=["p4_tp", "tp_txt"])
def test_the_api_cells_describe_no_prod_or_iap_service(path, cid):
    value = _cell(ET.parse(path).getroot(), cid).get("value")
    assert not re.search(r"\bprod\b|IAP", value), value

def test_a_stale_relation_count_on_the_icon_page_is_caught_and_rewritten(live):
    icons = ET.parse(dw.ICONS).getroot()
    n = len(live["db_tables"])
    sub = _cell(icons, "sub")
    sub.set("value", re.sub(r"\b\d+-relation\b", f"{n - 1}-relation", sub.get("value")))
    assert f"icons: cell sub says {n - 1} relations, live is {n}" in dw.check_icons(icons, live)
    dw.refresh_icons(icons, live)
    assert f"{n}-relation Cloud SQL" in sub.get("value")
    assert dw.check_icons(icons, live) == []
```

`test_the_main_page_draws_one_box_per_live_api_service(main_root, live)`: on page 0, the ids of
`vertex="1"` cells whose first label line is a live `solyra-api-*` service equal `["svc_tp"]`;
`API_SERVICE_EDGES` is a subset of the ids of cells with `svc_tp` as source or target; the ids of
cells whose value starts with `"Cloud Build: deploy-solyra-api-staging"` equal `["gha_ds"]`.

- [ ] **Step 6: Run the file (RED against `origin/main`'s diagrams and REPLACEMENTS)**

Run: `python3 -m pytest tests/scripts/test_refresh_architecture_drawio.py -q --tb=line`
Expected: `15 failed, 10 passed` (Tasks 1-2's three tests now pass). The 15: the four tests that call `check()` on the committed page
(`test_the_committed_diagram_agrees_with_the_snapshot`, `test_a_stale_service_count_is_caught`,
`test_the_deleted_prod_service_name_is_rejected`,
`test_the_service_account_name_is_not_mistaken_for_the_service`, each seeing `cell subtitle says 4
Cloud Run Services, live is 3` and `cell gha_group says 3 triggers, live is 2`),
`test_no_generated_text_names_the_retired_service` (first offender: the line-49 target
`▸ IAP-gated, AUTH_MODE=iap, ...`), both `test_check_reports_...`, both `test_check_icons_reports_...`
(`assert "icons: stale label 'solyra-api-prod'" in []`), both
`test_the_committed_diagrams_do_not_draw_...`, both `test_the_api_cells_describe_...`,
`test_the_main_page_draws_one_box_per_live_api_service` (`assert ['svc_st'] == ['svc_tp']`) and
`test_a_stale_relation_count_...`. Save the output for the PR.

- [ ] **Step 7: Edit the generator**

Retarget these REPLACEMENTS entries (sources unchanged):

| Line | Source (unchanged) | New target |
|---|---|---|
| 40-41 | `"solyra-api-prod\nCloud Run Service\nFastAPI API (IAP)"` | `"solyra-api-staging\nCloud Run Service\nFastAPI only; the browser signs in with Firebase"` |
| 48-49 | `"▸ prod domain: stocks.insightscollective.org (IAP + managed TLS)\n▸ deploy: staging revision → promote workflow"` | `"▸ public, Firebase login (AUTH_MODE=firebase), SA trading-platform-svc@\n▸ deploy: deploy-solyra-api-staging Cloud Build trigger on push to main"` |
| 50 | `"Cloud Run Service\nFastAPI + React"` | `"Cloud Run Service\nFastAPI API"` |
| 54 | `"trading-platform\nFastAPI API only"` | `"solyra-api-staging\nFastAPI API only"` |
| 55 | `"trading-platform\nCloud Run Service"` | `"solyra-api-staging\nCloud Run Service"` |
| 56 | `"Browser → trading-platform Cloud Run Service"` | `"Browser → solyra-api-staging Cloud Run Service"` |
| 80 | `"Browser → solyra-api-prod Cloud Run Service"` | `"solyra UI → solyra-api-staging (Firebase)"` |

Delete the two entries at lines 71-72 (`deploy-trading-apps.yml ...` → `Cloud Build:
deploy-solyra-api-prod ...`): they fed only `gha_dep`, which now leaves by id, and neither source is
in either committed file, so no target of theirs can be drawn. Rewrite the comment at lines 51-53:
`trading-platform` was deleted, and so was its successor `solyra-api-prod` (2026-10-10, #1366); both
map to `solyra-api-staging`.

Append after the `(fix/workflow-{name}-{run})` entry, in this order, under a comment naming #1366,
FEAT-DEPLOY-001 and why `p4_tp` precedes `ic_tp`. Sources are the labels committed on `089f271e`:

```python
    # svc_tp (Architecture.drawio, main page)
    ('solyra-api-prod\nFastAPI API only — no SPA since #957 (20 routers:\nlive, grid, options, playbook, backtest, signals,\ninsights, journal, dashboard, catalysts, admin,\nanalytics, config, health, glossary, magnitude,\nearnings, waitlist, preferences, profile)\n▸ IAP-gated, AUTH_MODE=iap, SA trading-platform-svc@\n▸ deploy: deploy-solyra-api-prod Cloud Build trigger (manual digest promote)\n▸ --no-cpu-throttling (PR #507) for BackgroundTasks',
     'solyra-api-staging\nFastAPI API only — no SPA since #957 (20 routers:\nlive, grid, options, playbook, backtest, signals,\ninsights, journal, dashboard, catalysts, admin,\nanalytics, config, health, glossary, magnitude,\nearnings, waitlist, preferences, profile)\n▸ public, Firebase login (AUTH_MODE=firebase), SA trading-platform-svc@\n▸ open self-signup over production data (#943)\n▸ api.stocks.insightscollective.org → this service (since 2026-09-06)\n▸ deploy: deploy-solyra-api-staging Cloud Build trigger on push to main'),
    # p4_tp (Architecture.drawio page 4, "⚡ Insight Refresh"); before ic_tp, whose label is this one's first line
    ('solyra-api-staging / -prod\nCloud Run Services\nFastAPI only; the browser reaches staging (Firebase), prod is IAP',
     'solyra-api-staging\nCloud Run Service\nFastAPI only; the browser signs in with Firebase'),
    # ic_tp (Architecture-icons.drawio, "1 · System Overview")
    ('solyra-api-staging / -prod', 'solyra-api-staging'),
    # flow_c (main page) and ref_s2 (icons, "4 · Insight Refresh") carry this as a substring
    ('solyra UI → solyra-api-staging (Firebase) or solyra-api-prod (IAP)',
     'solyra UI → solyra-api-staging (Firebase)'),
    # tp_txt (icons, "1 · System Overview")
    ('FastAPI only — no React in the image since #957 (13 routers)\napi.stocks.insightscollective.org → solyra-api-staging (managed TLS, 2026-09-06)\nstocks.insightscollective.org = Firebase auth-email domain / reserved for the SPA\nstaging AUTH_MODE=firebase · prod IAP-gated · --no-cpu-throttling (PR #507) · min-instances=0',
     'FastAPI only — no React in the image since #957 (20 routers)\napi.stocks.insightscollective.org → solyra-api-staging (managed TLS, 2026-09-06)\nstocks.insightscollective.org = the solyra SPA and the Firebase auth-email domain\nAUTH_MODE=firebase · open self-signup · --cpu-throttling · min-instances=0'),
    # gh_txt (icons, "1 · System Overview")
    ('db-query.yml sandbox SQL access  ·  deploy-solyra-api-staging → solyra-api-staging (auto on main)  ·  deploy-solyra-api-prod → solyra-api-prod (manual only)  ·  auth CLAUDE_CODE_WEB_GCP_SA_KEY',
     'db-query.yml sandbox SQL access  ·  deploy-solyra-api-staging → solyra-api-staging (auto on main)  ·  auth CLAUDE_CODE_WEB_GCP_SA_KEY'),
```

The new `svc_tp` and `tp_txt` texts drop `--no-cpu-throttling (PR #507)`, since the staging service
is deployed with `--cpu-throttling` (`platform/deploy.sh:355`; snapshot `cpu_throttling: "true"`),
fold in what `svc_st` said except "reserved for the SPA", and give the 20 `app.include_router` calls
in `platform/api/main.py`.

Then:
- `DELETE_IDS = {"ext_ghpages", "ext_gas", "svc_sm_orphan", "svc_st", "gha_dep"}`, with a comment:
  `svc_st` because `svc_tp` draws the staging service and keeps its four edges; `gha_dep` because the
  prod promote trigger is deleted and `gha_ds` draws the staging one.
- `NEW_CELLS: list[tuple[str, str, str, int, int, int, int]] = []`; the module docstring bullet at
  line 12 becomes `* adds any cell listed in NEW_CELLS (none today: svc_tp draws the API service);`.
- `addon_auth_box` text (line 337), exactly:
  `"★ Auth: AUTH_MODE firebase (solyra-api-staging) / open (local) • roles from user_roles (admin, user, dev) • /api/me → is_admin, is_dev • CORS Lovable hosts and stocks.insightscollective.org"`.
  The banner names only the deployed and local modes, so the old `outside iap` qualifier goes with
  `iap`. The custom domain is the exact host `_cors_origin_regex` admits (`platform/api/main.py:130`).
- `ICON_STALE` gains `"solyra-api-prod", "staging / -prod"`; so does the stale tuple in `check()`
  (lines 533-534). `check()`'s line 541 message becomes
  `"stale label still present: trading-platform (the service is deleted)"`.
- `refresh_icons` gains `(r"\b\d+-relation\b", f"{vals['relations']}-relation")` after its
  `relations` pattern; `check_icons` gains `(r"\b(\d+)-relation\b", vals["relations"], "relations")`.

- [ ] **Step 8: Regenerate both diagrams as the monthly workflow does**

In the shell of Step 3 (or with `W` and `SNAP` set again):

```bash
python3 -m scripts.maintenance.doc_inventory --snapshot "$SNAP" --json > "$W/repo_inventory.json"
jq '[.repo.jobs[].name]' "$W/repo_inventory.json" > "$W/repo_jobs.json"     # workflow line 499
python3 scripts/maintenance/refresh_architecture_drawio.py --snapshot "$SNAP" --repo-jobs "$W/repo_jobs.json"
git diff --exit-code origin/main -- tests/fixtures/live_gcp_snapshot_2026-09-07.json
```

Expected on the 2026-10-11 snapshot: 68 job names;
`Architecture.drawio: 3 labels replaced, main page regenerated`,
`Architecture-icons.drawio: 14 labels replaced`, `drawio check: 0 problem(s)`; the shared fixture
unchanged. The diff touches, on the main page, `svc_tp`, `flow_c`, `p4_tp`, `addon_auth_box`,
`subtitle`, `sched_group`, `svc_group`, `gha_group`, `ext_gh`, `addon_group`, `addon_schema_box`,
`addon_note` and the 37 add-on cards (last-execution dates, `sha256:<12 hex>` labels, ★ on jobs with
no `deploy_*` function, no research fill), and removes `svc_st` and `gha_dep`. In the icon file it
touches `f_sql`, `ic_sql`, `ic_tp`, `tp_txt`, `gh_txt`, `ref_s2`, `sub` (3 Services, 98-relation) and
the seven reconciliation notes. No `2026-09-07` remains in either file.

- [ ] **Step 9: Run (GREEN), commit, and prove the regeneration is stable**

Run: `python3 -m pytest tests/scripts/test_refresh_architecture_drawio.py -q` (expect `25 passed`)
and `python3 -m pytest tests/scripts/test_doc_inventory.py tests/scripts/test_check_generated_docs.py tests/meta/test_render_doc_prompts.py tests/scripts/test_docs_audit.py tests/meta/test_refresh_architecture_docs_pr_token.py -q`
(expect no failures). Commit:

```bash
git add "$SNAP" tests/scripts/test_refresh_architecture_drawio.py scripts/maintenance/refresh_architecture_drawio.py Architecture.drawio Architecture-icons.drawio
git commit -m "fix(drawio): draw the one live API service, regenerated from a fresh snapshot"
```

On that head, re-run Step 8's generator command, then
`git diff --exit-code -- Architecture.drawio Architecture-icons.drawio`. Expected: `0 labels
replaced` for both files and exit 0. Keep the output for done_when[3].

## Task 4: the ping description in the API contract

Spec: § Design, "OpenAPI" and "Line-cited files"; § Problem, fourth bullet. Advances done_when[5]
and done_when[6].

**Files:**
- Modify: `tests/api/test_openapi_snapshot.py`
- Modify: `platform/api/routers/earnings.py:327-330` (the docstring's second paragraph only)
- Regenerate: `platform/api/openapi.json`

**Interfaces:**
- Produces: the regenerated `platform/api/openapi.json`, whose only change is the
  `GET /api/earnings/health/ping` description. Task 7 and the solyra plan's sync task consume it.

- [ ] **Step 1: Write the failing test**

```python
def test_the_ping_description_does_not_name_the_retired_service():
    spec = json.loads(_load_exporter().SNAPSHOT.read_text(encoding="utf-8"))
    description = spec["paths"]["/api/earnings/health/ping"]["get"]["description"]
    assert "solyra-api-prod" not in description
    assert "sits behind IAP" not in description
    assert "kept for manual and in-cluster warm-up" in description
```

- [ ] **Step 2: Run (RED)**

Run: `python3 -m pytest tests/api/test_openapi_snapshot.py -q`
Expected: 1 failed, `assert 'solyra-api-prod' not in 'Lightweight...a stale 200.'`.

- [ ] **Step 3: Rewrite the paragraph and regenerate**

Keep the first line (`Lightweight warm-up probe. NOT called by a scheduler.`), which 05-a:504 and
05-e:84 render. Replace the second paragraph with these four lines (the same count):

```text
    The keep-warm Cloud Scheduler was dropped (gcp/deploy.sh, "Platform
    keep-warm — DROPPED") while the API sat behind IAP, where an
    unauthenticated GET was rejected at the edge and never reached the app.
    The endpoint is kept for manual and in-cluster warm-up.
```

Run `python3 scripts/export_openapi.py --check` (exit 1, `is stale`), `python3
scripts/export_openapi.py` (`wrote platform/api/openapi.json (393208 bytes)`), then `--check` again
(exit 0, `is up to date`). `git diff --stat platform/api/openapi.json`: 1 insertion, 1 deletion.

- [ ] **Step 4: Run (GREEN)**

`python3 -m pytest tests/api/test_openapi_snapshot.py tests/scripts/test_check_generated_docs.py -q`:
all pass, `test_committed_docs_pass_every_gate` included.

- [ ] **Step 5: Commit** `fix(api): describe the ping probe without the retired service`

## Task 5: the `/dev` proxy recipe names the running service, in place

Spec: § Design, "`/dev` page" and "Line-cited files"; § Problem, fifth bullet. Advances done_when[7]
and done_when[6].

**Files:**
- Modify: `platform/api/main.py:529` (that line only)
- Test: `tests/api/test_dev_page_auth.py`

**Interfaces:**
- Consumes: `_get(monkeypatch, mode, header)` from the test module.

- [ ] **Step 1: Write the failing tests**

```python
def test_dev_proxy_line_names_the_service_it_runs_on(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "solyra-api-staging")
    r = _get(monkeypatch, "open", None)
    assert r.status_code == 200
    assert "gcloud run services proxy solyra-api-staging --region us-east1" in r.text
    assert "solyra-api-prod" not in r.text

def test_dev_proxy_line_shows_a_visible_placeholder_without_k_service(monkeypatch):
    monkeypatch.delenv("K_SERVICE", raising=False)
    r = _get(monkeypatch, "open", None)
    assert "gcloud run services proxy &lt;service&gt; --region us-east1" in r.text
```

- [ ] **Step 2: Run (RED)**

Run: `python3 -m pytest tests/api/test_dev_page_auth.py -q`
Expected: 2 failed, each `assert 'gcloud run services proxy ...' in '<!doctype html>...'`.

- [ ] **Step 3: Replace line 529 in place**

`<pre>gcloud run services proxy {os.environ.get('K_SERVICE', '&lt;service&gt;')} --region us-east1`
(single quotes inside the triple-double-quoted f-string, valid on Python 3.11). No line is added:
a variable above the f-string shifts the lines 05-a and 05-e cite. Measured on this plan's dry run,
one extra line beside `revision = ...` fails `test_committed_docs_pass_every_gate` and
`test_a_model_edited_block_is_restored_from_the_fresh_render_by_name` (`inventory:routes block differs
from a fresh render`). The escaped default is the visible placeholder, since a bare `<service>` is
parsed as a tag.

- [ ] **Step 4: Run (GREEN) and check the line-cited documents**

```bash
python3 -m pytest tests/api/test_dev_page_auth.py tests/scripts/test_check_generated_docs.py -q
test "$(git show origin/main:platform/api/main.py | wc -l)" -eq "$(wc -l < platform/api/main.py)" && echo same-lines
git diff --exit-code origin/main -- docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md
```

Expected: all pass (`test_committed_docs_pass_every_gate` included), `same-lines`, exit 0. Keep the
output for done_when[6].

- [ ] **Step 5: Commit** `fix(api): name the running service in the /dev proxy recipe`

## Task 6: the Run 28 note in the past tense

Spec: § Design, "Run 28 comment"; § Problem, sixth bullet. Advances done_when[8].

**Files:**
- Modify: `scripts/maintenance/render_doc_prompts.py:74-76`

- [ ] **Step 1: Show the grep before the edit**

Run: `git grep -n solyra-api-prod -- platform/api scripts/maintenance/render_doc_prompts.py`
Expected after Tasks 4-5: one line, `scripts/maintenance/render_doc_prompts.py:74`, which does not say
retired.

- [ ] **Step 2: Rewrite lines 74-76 as these four**

```text
    # `solyra-api` into 05-d twice; the live services were then
    # `solyra-api-prod` (retired 2026-10-10, #1366) and `solyra-api-staging`,
    # and verify_docs_against_live failed the run on a service that does not
    # exist. The prompt already warned against inventing
```

- [ ] **Step 3: Run the grep and the module's tests**

`git grep -n solyra-api-prod -- platform/api scripts/maintenance/render_doc_prompts.py` prints exactly
`scripts/maintenance/render_doc_prompts.py:75:    # \`solyra-api-prod\` (retired 2026-10-10, #1366) and \`solyra-api-staging\`,`;
`python3 -m pytest tests/meta/test_render_doc_prompts.py -q` passes.

- [ ] **Step 4: Commit** `docs(maintenance): keep the Run 28 service note in the past tense`

## Task 7: open the PR, show it red on main, and hand the contract to solyra

Spec: § Design, "OpenAPI" (merge order) and "Canvas"; § Risks, fourth bullet. Advances done_when[9]
and the first half of done_when[10].

- [ ] **Step 1: Push and open a draft PR**

`git push -u origin feature/feat-deploy-001-retired-service-leftovers`; open the PR as a draft with
the title and body in Global Constraints. In the next commit set this plan's `pr:`
(`docs(plan): record the FEAT-DEPLOY-001 leftovers PR number`).

- [ ] **Step 2: RED evidence comment, as the PR opens**

From the PR head, run the PR's three test files against `origin/main`'s code and diagrams:

```bash
RED="$(mktemp -d)/red" && git worktree add --detach "$RED" origin/main
cp tests/fixtures/live_gcp_snapshot_<read date>.json "$RED/tests/fixtures/"
cp tests/scripts/test_refresh_architecture_drawio.py "$RED/tests/scripts/"
cp tests/api/test_openapi_snapshot.py tests/api/test_dev_page_auth.py "$RED/tests/api/"
(cd "$RED" && python3 -m pytest tests/scripts/test_refresh_architecture_drawio.py tests/api/test_openapi_snapshot.py tests/api/test_dev_page_auth.py -q --tb=line)
git worktree remove --force "$RED"
```

Expected: `21 failed, 16 passed`: the 15 of Task 3 Step 6, the two refusal tests, the digest test,
the ping test and the two `/dev` tests. Post it with Task 3 Step 2's output (the snapshot assertion,
which passes against `origin/main`'s generator because its fixture is test data this PR brings) and
Task 6 Step 1's grep.

- [ ] **Step 3: Confirm the branch serves the new description**

```bash
curl -sS https://raw.githubusercontent.com/TeneikaAskew/stocks/feature/feat-deploy-001-retired-service-leftovers/platform/api/openapi.json \
  | python3 -c "import json,sys; d=json.load(sys.stdin)['paths']['/api/earnings/health/ping']['get']['description']; print('solyra-api-prod' in d or 'sits behind IAP' in d)"
```

Expected: `False`. `True` means the CDN still serves the old copy; wait and repeat before Step 4.

- [ ] **Step 4: The solyra sync**

The solyra plan for `feature/feat-auth-001-confirm-on-return` (its Task 6) runs
`STOCKS_OPENAPI_REF=feature/feat-deploy-001-retired-service-leftovers npm run contract:sync`
(`scripts/sync-api-contract.mjs:28-29` builds
`https://raw.githubusercontent.com/TeneikaAskew/stocks/<ref>/platform/api/openapi.json`; a ref with
slashes resolves). Its diff is one line of `tests/fixtures/stocks-openapi.json` and three comment
lines of `src/types/stocksOpenApi.gen.d.ts`. Once that PR is open, add to this PR's body:
`Contract sync: TeneikaAskew/solyra#<n> (tests/fixtures/stocks-openapi.json synced with STOCKS_OPENAPI_REF=feature/feat-deploy-001-retired-service-leftovers; differs from solyra main only in the /api/earnings/health/ping description).`

- [ ] **Step 5: Merge order, in the PR body**

The solyra PR is open first (its `contract:check` is red against stocks `main` until this merges).
This PR merges; the solyra PR's CI is re-run; it merges.

## Task 8: close

Spec: § Done when. Advances the CI half of done_when[10] and done_when[11]; ticks the rest with
evidence.

- [ ] **Step 1: Product records**

- `docs/product/02-FEATURE-CATALOG.md`, FEAT-DEPLOY-001 record only: Status stays `Production but
  needs remediation`; Last reviewed = the PR head commit's date (`git show -s --format=%cs HEAD`);
  its Tests row gains that `tests/scripts/test_refresh_architecture_drawio.py` asserts the diagrams
  and generator draw no retired service and refuse a snapshot without table statistics, and that
  `tests/api/test_dev_page_auth.py` covers the `/dev` proxy line
  (`[#<n>](https://github.com/TeneikaAskew/stocks/pull/<n>)`). The record already reads 2026-10-11 and
  the gate refuses an unchanged record on the same day, so this addition is required.
- `docs/product/12-PR-ISSUE-TRACEABILITY.md`: append
  `· [#<n>](https://github.com/TeneikaAskew/stocks/pull/<n>) *remediation*` to the FEAT-DEPLOY-001
  `**PR lineage:**` line.
- A commit on a later day moves Last reviewed to that commit's date.

- [ ] **Step 2: Docs audit and gate**

`python3 scripts/maintenance/docs_audit.py --json` on `origin/main` (a detached worktree) with
`--write-issues-snapshot <f>`, then on the branch with `--issues-snapshot <f>`: the branch reports no
finding `main` does not (285 and 285 on this plan's dry run of the r1 change set). Then
`python3 scripts/gate/spec_gate.py --pr origin/main` (no errors).

- [ ] **Step 3: Tick and mark ready**

Tick each done_when box with its evidence: test names, the snapshot command and `$EXEC`, Task 3 Step
9's stable re-run, the `--check` output, Task 5 Step 4's output, the grep line, the solyra PR link,
the Task 7 Step 2 comment, the catalog and lineage lines. Mark the PR ready. The Backtest Pipeline
`Run Tests` job (`python -m pytest tests/ -x -q --ignore=tests/integration`) is green on the head.
Read every review thread before CI and resolve each per CLAUDE.md §2.5.

- [ ] **Step 4: After the merge (Phase 5 step 7, not a done_when item)**

On a `docs/` branch set this plan's `status: done`. Tell the solyra PR's author to re-run its CI. The
canvas check runs from chat with the refresh-canvas skill.
