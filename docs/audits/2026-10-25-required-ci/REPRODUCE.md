# Reproduce the audit

Use a disposable checkout of audit base
`911d30a7427a8d3249ecd82a828952a3e4b639a0`, Python 3.12, and a local environment
with `requirements.txt`. Hosted jobs resolve unpinned manifests rather than
`requirements.lock`; local versions are recorded in inventory. Exact versions
may change future results. Never provide production credentials to these runs.
The examples retain the observed `/tmp/stocks-ci-audit` evidence destination.
Choose a different unused directory/container/port if already occupied.

```bash
mkdir -p /tmp/stocks-ci-audit
python -m pip install --no-deps --target /tmp/stocks-ci-audit/ml lightgbm==4.7.0
```

The local ML overlay is narrower than the workflow's complete
`pip install -r requirements.txt -r requirements-research.txt`. It exercises
LightGBM with the installed sklearn/numpy/scipy; it does not establish XGBoost
or installed SHAP parity. Hosted full-stack evidence is recorded separately.

Save each following fenced Python block under the indicated temporary filename.
These are observation/reproduction scripts, not new repository tests or CI code.
`collect_all.py` runs collection only; `run.py` removes inherited credential/DB
variables and `BASH_ENV`, then runs a bounded child pytest process. Only the
`integration_run` prefix sets credentials, for the local throwaway database.
The original first collection/run predated the BASH_ENV correction; this file
shows the corrected safe reproduction. Do not reproduce the shell failure by
reintroducing SDK initialization into a credentialed test process.

## Temporary file: `audit_collect.py`

```python
import json, os, pathlib, time
start=time.monotonic()
records=[]
errors=[]
def pytest_collection_finish(session):
    for item in session.items:
        records.append({'nodeid':item.nodeid,'path':str(item.path.relative_to(session.config.rootpath)),'line':item.location[1]+1,'fixtures':item.fixturenames,'markers':[{'name':m.name,'args':repr(m.args),'kwargs':repr(m.kwargs)} for m in item.iter_markers()]})
def pytest_collectreport(report):
    if report.failed or report.skipped:
        errors.append({'nodeid':report.nodeid,'outcome':report.outcome,'detail':str(report.longrepr)})
def pytest_sessionfinish(session,exitstatus):
    pathlib.Path(os.environ['AUDIT_COLLECTION']).write_text(json.dumps({'exitstatus':int(exitstatus),'elapsed_seconds':round(time.monotonic()-start,3),'items':records,'collection_reports':errors},indent=2)+'\n')
results=[]
def pytest_runtest_logreport(report):
    results.append({'nodeid':report.nodeid,'when':report.when,'outcome':report.outcome,'duration':report.duration,'detail':str(report.longrepr) if report.longrepr else None})
def pytest_terminal_summary(terminalreporter,exitstatus,config):
    if os.environ.get('AUDIT_RESULTS'):
        pathlib.Path(os.environ['AUDIT_RESULTS']).write_text(json.dumps({'exitstatus':int(exitstatus),'elapsed_seconds':round(time.monotonic()-start,3),'reports':results},indent=2)+'\n')
```

## Temporary file: `collect_all.py`

```python
import os,subprocess,json,glob,concurrent.futures,pathlib
root=pathlib.Path('/tmp/stocks-ci-audit')
env=os.environ.copy()
for k in list(env):
 if k.startswith(('GOOGLE_','CLOUDSDK_','DB_','GCS_','CLOUD_SQL_')): env.pop(k)
env['PYTHONPATH']=str(root)+':'+os.getcwd()
commands={'lean':['tests/','-x','--ignore=tests/integration'],'research_lean':sum([sorted(glob.glob(p)) for p in ['tests/*/test_strat*.py','tests/*/test_mag*.py']],[])+['tests/gcp/test_featurize_all_nan_robust.py','tests/gcp/test_feature_importance.py','tests/meta/test_import_coverage.py'],'integration':['tests/integration/'],'gate':['tests/scripts/test_spec_gate.py','--noconftest','-p','no:cacheprovider'],'exporter':['tests/scripts/test_export_model_registry.py','--noconftest','-p','no:cacheprovider']}
(root/'collection-commands.json').write_text(json.dumps(commands,indent=2))
def run(pair):
 name,args=pair;e=env.copy();e['AUDIT_COLLECTION']=str(root/f'{name}.json')
 with open(root/f'{name}-collection.log','w') as f:
  p=subprocess.run(['python','-m','pytest',*args,'-q','--collect-only','-p','audit_collect'],env=e,stdout=f,stderr=subprocess.STDOUT,timeout=120)
 r=json.loads((root/f'{name}.json').read_text());return name,p.returncode,len(r['items']),r['elapsed_seconds'],r['collection_reports']
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 for r in pool.map(run,commands.items()): print(r,flush=True)
```

## Temporary file: `run.py`

```python
import sys,os,pathlib,subprocess,json,time
name=sys.argv[1]; args=sys.argv[2:];root=pathlib.Path('/tmp/stocks-ci-audit');env=os.environ.copy()
for k in list(env):
 if k.startswith(('GOOGLE_','CLOUDSDK_','DB_','GCS_','CLOUD_SQL_')):env.pop(k)
ml=name.startswith(('research','ml','api'))
env.pop('BASH_ENV',None)
env['PYTHONPATH']=str(root)+(':'+str(root/'ml') if ml else '')+':'+os.getcwd()
if name.startswith('api_fixed'): env['PYTHONPATH']+=':'+os.getcwd()+'/platform'
env['OMP_NUM_THREADS']='2';env['OPENBLAS_NUM_THREADS']='2'
env['AUDIT_COLLECTION']=str(root/f'{name}.json');env['AUDIT_RESULTS']=str(root/f'{name}-results.json')
if name.startswith('integration_run'):
 env.update(DB_HOST='127.0.0.1',DB_PORT='55432',DB_USER='trading_user',DB_PASS='testpass',DB_NAME='trading')
t=time.monotonic()
try:
 with open(root/f'{name}.log','w') as f:
  p=subprocess.run(['python','-m','pytest',*args,'-p','audit_collect'],env=env,stdout=f,stderr=subprocess.STDOUT,timeout=180)
 print(name,'exit',p.returncode,'elapsed',round(time.monotonic()-t,2))
 print('\n'.join((root/f'{name}.log').read_text().splitlines()[-12:]))
except subprocess.TimeoutExpired:print(name,'TIMEOUT 180s')
```

## Temporary file: `mutate_defaults.py`

```python
import os

def pytest_configure(config):
    if os.environ['AUDIT_MUTATION']=='class_weight':
        from gcp.research.magnitude_engine.mag_pred_train import make_lgbm
        assert make_lgbm.__defaults__[0]=='balanced'
        make_lgbm.__defaults__=(None,*make_lgbm.__defaults__[1:])
    elif os.environ['AUDIT_MUTATION']=='inclusive_today':
        import lib.strat
        assert lib.strat.compute_strat_status.__defaults__[-1] is True
        lib.strat.compute_strat_status.__defaults__=(*lib.strat.compute_strat_status.__defaults__[:-1],False)
```

## Temporary file: `static_scan.py`

```python
import ast,pathlib,json,collections,hashlib
root=pathlib.Path('.')
functions=[];marks=[];fixtures=[];dupes=collections.defaultdict(list)
for p in sorted(root.glob('tests/**/*.py')):
 text=p.read_text();tree=ast.parse(text)
 for n in ast.walk(tree):
  if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
   loc={'path':str(p),'line':n.lineno,'name':n.name}
   if any('fixture' in ast.unparse(d) for d in n.decorator_list): fixtures.append({**loc,'decorators':[ast.unparse(d) for d in n.decorator_list]})
   if n.name.startswith('test_'):
    body=n.body[1:] if isinstance(n.body[0],ast.Expr) and isinstance(n.body[0].value,ast.Constant) and isinstance(n.body[0].value.value,str) else n.body
    digest=hashlib.sha256(ast.dump(ast.Module(body=body,type_ignores=[]),include_attributes=False).encode()).hexdigest()
    dupes[digest].append(loc)
    asserts=[x for x in ast.walk(n) if isinstance(x,ast.Assert)]
    functions.append({**loc,'assert_count':len(asserts),'calls':[ast.unparse(x.func) for x in ast.walk(n) if isinstance(x,ast.Call)],'suspicious_asserts':[{'line':x.lineno,'text':ast.unparse(x)} for x in asserts if isinstance(x.test,ast.Constant) or (isinstance(x.test,ast.Compare) and len(x.test.comparators)==1 and ast.dump(x.test.left)==ast.dump(x.test.comparators[0]))]})
  if isinstance(n,ast.Call) and any(s in ast.unparse(n.func) for s in ['skip','xfail']): marks.append({'path':str(p),'line':n.lineno,'call':ast.unparse(n)[:1000]})
result={'method':'AST heuristic; candidates only, not proof of redundancy or obsolescence. Fixture lookup can be dynamic. Nested functions counted. Strings containing code not parsed recursively.','test_functions':functions,'fixture_definitions':fixtures,'skip_xfail_calls':marks,'identical_function_bodies':[v for v in dupes.values() if len(v)>1]}
pathlib.Path('/tmp/stocks-ci-audit/static.json').write_text(json.dumps(result,indent=2)+'\n')
print('functions',len(functions),'fixtures',len(fixtures),'skip-like calls',len(marks),'exact body duplicates',result['identical_function_bodies'])
print('suspicious assertions',[(x['path'],x['name'],x['suspicious_asserts']) for x in functions if x['suspicious_asserts']])
```

## Temporary file: `build_inventory.py`

```python
import ast,collections,hashlib,importlib.metadata,json,pathlib,platform,subprocess,yaml
root=pathlib.Path('/tmp/stocks-ci-audit'); out=pathlib.Path('docs/audits/2026-10-25-required-ci');sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip();url=f'https://github.com/TeneikaAskew/stocks/blob/{sha}/'
collections_data={n:json.loads((root/f'{n}.json').read_text()) for n in ['lean','research_collect','research_lean','integration','gate','exporter','api_fixed']}
checks=[]
for label,wf,job,groups,kind,reqs,behavior in [
 ('Backtest Pipeline / Run Tests','backtest-pipeline.yml','test',['lean'],'behavior tests and repository invariants',['REQ-DATA-001','REQ-DATA-002','REQ-GOV-004'],'Unit/API/agents/research helpers, scripts, generated documentation and policy invariants; not a backtest execution'),
 ('Backtest Pipeline / Research Tests (heavy ML stack)','backtest-pipeline.yml','research-test',['research_collect'],'behavior tests and import check',['REQ-DATA-001','REQ-DATA-002'],'Real classifier fitting, calibration and leakage contracts; many non-ML strat/magnitude helpers also selected'),
 ('Backtest Pipeline / Integration Tests (ephemeral Postgres)','backtest-pipeline.yml','integration-tests',['integration'],'SQL integration tests',['REQ-DATA-001','REQ-DATA-002'],'Current schema/query compatibility, persistence, constraints, journal timestamps, options marks and watchlist history'),
 ('registry-check / registry','registry-check.yml','registry',['gate'],'policy smoke check, tests and generated-data check',['REQ-GOV-004'],'Head gate starts and reaches a verdict; own gate suite; model registry provenance and freshness'),
 ('spec-gate / base-suite','spec-gate.yml','base-suite',['gate','exporter'],'trusted-base regression tests',['REQ-GOV-001','REQ-GOV-004'],'Base-owned tests judge proposed gate/exporter; distinct trust boundary, not a duplicate authority'),
 ('spec-gate / gate','spec-gate.yml','gate',[],'specification/policy validator, not pytest',['REQ-GOV-001','REQ-REVIEW-001'],'Branch, approved specification, plan, immutable policy, PR metadata and close-out rules; does not itself fetch reviewer conversations')]:
 p=pathlib.Path('.github/workflows')/wf;doc=yaml.load(p.read_text(),Loader=yaml.BaseLoader);j=doc['jobs'][job]
 checks.append({'name':label,'workflow':str(p),'workflow_url':url+str(p),'job_id':job,'kind':kind,'triggers':doc.get('on'),'job_configuration':j,'collection_groups':groups,'current_local_selected_node_count':sum(len(collections_data[g]['items']) for g in groups),'requirement_links':[{'id':r,'url':url+'docs/product/01-PRODUCT-REQUIREMENTS.md','mapping':'audit interpretation; not complete per-test requirement traceability'} for r in reqs],'behavior':behavior})
files={}
for name,r in collections_data.items():
 for item in r['items']:
  p=item['path'];rec=files.setdefault(p,{'url':url+p,'collections':{},'fixture_closure':set(),'markers':[]})
  rec['collections'].setdefault(name,[]).append(item['nodeid'])
  rec['fixture_closure'].update(item['fixtures'])
  for mark in item['markers']:
   if mark['name'] in ['skipif','skip','xfail']:
    val={'nodeid':item['nodeid'],**mark}
    if val not in rec['markers']:rec['markers'].append(val)
for p,rec in files.items():
 rec['fixture_closure']=sorted(rec['fixture_closure']);rec['counts']={k:len(v) for k,v in rec['collections'].items()}
 tree=ast.parse(pathlib.Path(p).read_text());rec['imports']=sorted(set(ast.unparse(n) for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))))
 rec['sha256']=hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
stat=json.loads((root/'static.json').read_text());used=set(f for rec in files.values() for f in rec['fixture_closure'])
packages={}
for p in ['pytest','pandas','numpy','scikit-learn','fastapi','sqlalchemy','pyyaml','xgboost','shap']:
 try:packages[p]=importlib.metadata.version(p)
 except importlib.metadata.PackageNotFoundError:packages[p]=None
inv={'schema_version':1,'as_of':'2026-10-25','base_commit':sha,'required_names_source':'Parent inspected user screenshot; protection settings not independently queried','scope':'point-in-time audit; full collection plus sampled behavior verification; not exhaustive validity proof','environment':{'python':platform.python_version(),'platform':platform.platform(),'packages':packages,'research_overlay':{'lightgbm':'4.7.0','installation':'isolated /tmp target, --no-deps; not full requirements-research.txt parity'},'database':'throwaway pgvector/pgvector:pg15 digest sha256:47af0b65960b14f1c6945aa4ccae37836c632e9a6fe0eea9160936e616e5b2e9','sanitization':'remove GOOGLE_ CLOUDSDK_ DB_ GCS_ CLOUD_SQL_ variables; later corrected harness also unsets BASH_ENV; details in report'},'checks':checks,'collections':{n:{k:v for k,v in r.items() if k!='items'}|{'node_count':len(r['items']),'file_count':len(set(i['path'] for i in r['items']))} for n,r in collections_data.items()},'test_files':files,'static_screen':{'test_function_definitions':len(stat['test_functions']),'method':stat['method'],'identical_function_bodies':stat['identical_function_bodies'],'suspicious_assertions':[x for x in stat['test_functions'] if x['suspicious_asserts']],'skip_xfail_calls':stat['skip_xfail_calls'],'fixture_candidates_not_in_collected_closures':[f for f in stat['fixture_definitions'] if f['name'] not in used],'warning':'db_conn is reached dynamically through request.getfixturevalue. Nested local fixtures and lexical matches may produce false positives; see reviewed findings.'},'dependency_manifests':{p:{'url':url+p,'sha256':hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest(),'content':pathlib.Path(p).read_text()} for p in ['requirements.txt','requirements-research.txt']}}
(out/'inventory.json').write_text(json.dumps(inv,indent=2)+'\n')
results={}
for p in sorted(root.glob('*-results.json')):
 r=json.loads(p.read_text());r['counts']={f'{a}:{b}':n for (a,b),n in collections.Counter((x['when'],x['outcome']) for x in r['reports']).items()}
 r['reports']=[x for x in r['reports'] if x['when']=='call' or x['outcome']!='passed']
 for x in r['reports']:
  if x['detail']:x['detail']=x['detail'].replace('/workspace/stocks-ci-audit/','')
 results[p.name.removesuffix('-results.json')]=r
(out/'validation.json').write_text(json.dumps({'runs':results,'limitations':['The focused invocation named a nonexistent TestCandleTypeAsOf; exit 4, zero tests. Corrected invocation is separate.','The first inclusive-default mutation used __kwdefaults__; setup error. Corrected mutation uses __defaults__ and two tests fail for the intended reason.','research_run had four shell-environment failures; research_clean is the corrected isolated run.','No full local 7662-test execution; hosted full result used for context, not current local all-green proof.']},indent=2)+'\n')
print('inventory files',len(files),'bytes',(out/'inventory.json').stat().st_size)
```

## Collection and execution commands

Run from the disposable repository root. The collector preserves one record
per parametrized node and module-level skips independently. Inventory path
counts are actual collection, not AST function counts. The AST scanner
examines nested functions too and supplies candidates for manual review.

```bash
python /tmp/stocks-ci-audit/collect_all.py
python /tmp/stocks-ci-audit/run.py research_collect tests/*/test_strat*.py tests/*/test_mag*.py tests/gcp/test_featurize_all_nan_robust.py tests/gcp/test_feature_importance.py tests/meta/test_import_coverage.py --collect-only -q
python /tmp/stocks-ci-audit/run.py research_clean tests/*/test_strat*.py tests/*/test_mag*.py tests/gcp/test_featurize_all_nan_robust.py tests/gcp/test_feature_importance.py tests/meta/test_import_coverage.py -q -rs
python /tmp/stocks-ci-audit/run.py api_continuation tests/api/test_structure_continuation.py tests/api/test_strat_engine_predict.py -q -rs
python /tmp/stocks-ci-audit/run.py api_fixed tests/api/test_structure_continuation.py tests/api/test_strat_engine_predict.py -q -rs
python /tmp/stocks-ci-audit/run.py playbook_default tests/lib/test_strat_levels_playbook.py -q -rs
python /tmp/stocks-ci-audit/run.py focused_corrected tests/lib/test_strat_levels_playbook.py tests/scripts/test_docs_audit.py::test_the_real_traceability_line_reports_nothing tests/meta/test_http_status_classification.py -q -rs --mode=mock
python /tmp/stocks-ci-audit/run.py ml_baseline tests/gcp/test_magnitude_class_weight.py -q
AUDIT_MUTATION=class_weight python /tmp/stocks-ci-audit/run.py ml_mutation tests/gcp/test_magnitude_class_weight.py -q -p mutate_defaults
python /tmp/stocks-ci-audit/run.py duplicate_pairs tests/lib/test_strat.py tests/scripts/test_docs_audit.py tests/scripts/test_verify_docs_against_live.py -q -k 'naive_date_as_of_filters or inclusive_today_default_true_legacy_contract or the_pr_lookup_stops_once_every_pending_refresh_is_superseded or the_pr_walk_still_stops_once_the_current_generation_delivered or retired_service_is_caught or a_retired_service_is_reported_once_not_twice or the_free_tier_quota_is_not_read_as_a_fleet_count or the_free_tier_quota_is_still_not_a_fleet_count'
AUDIT_MUTATION=inclusive_today python /tmp/stocks-ci-audit/run.py duplicate_mutation_fixed tests/lib/test_strat.py -q -k 'naive_date_as_of_filters or inclusive_today_default_true_legacy_contract' -p mutate_defaults
python /tmp/stocks-ci-audit/run.py gate_controls tests/scripts/test_spec_gate.py -q --noconftest -p no:cacheprovider -k 'branch_names_exempt_no_code or a_superseded_spec_authorizes_nothing or the_gate_cannot_be_edited_outside_chore_and_ci_runs_the_base_copy'
python /tmp/stocks-ci-audit/run.py exporter_controls tests/scripts/test_export_model_registry.py -q --noconftest -p no:cacheprovider -k 'a_registry_without_model_rows_fails_closed or ci_checks_the_pr_head_commit or a_stale_main_fails_only_the_pr_that_made_it_stale'
python /tmp/stocks-ci-audit/static_scan.py
mkdir -p docs/audits/2026-10-25-required-ci
python /tmp/stocks-ci-audit/build_inventory.py
```

The mutation runner prints child exit status and saves reports; its own process
is an evidence wrapper, not a CI success gate. Expected mutations must have
pytest exit 1 and fail at the intended assertion; setup/collection failure is
not a killed mutation. No source/test files change through these mutations.

## Throwaway SQL control

Use only the named disposable container. Binding the port to loopback avoids
exposing this test database externally. Inspect readiness before applying schema.

```bash
docker pull pgvector/pgvector:pg15
docker run -d --name stocks-ci-audit-pg -e POSTGRES_USER=trading_user -e POSTGRES_PASSWORD=testpass -e POSTGRES_DB=trading -p 127.0.0.1:55432:5432 pgvector/pgvector:pg15
docker exec stocks-ci-audit-pg pg_isready -U trading_user
docker exec -i stocks-ci-audit-pg psql -U trading_user -d trading -v ON_ERROR_STOP=1 < gcp/schema.sql
python /tmp/stocks-ci-audit/run.py integration_run tests/integration/ -q -rs
docker rm -f stocks-ci-audit-pg
```

Image observed: `sha256:47af0b65960b14f1c6945aa4ccae37836c632e9a6fe0eea9160936e616e5b2e9`.
Use that digest to freeze the server image; the workflow currently uses a tag.
The constraint-drift negative control is already in the integration suite and
rolls back its transaction. Other fixtures truncate only this disposable DB.

## Hosted provenance and publication checks

Read-only GitHub job-log API endpoints for repository `TeneikaAskew/stocks`:
`actions/jobs/{job_id}/logs`. IDs and exact run URLs appear in
[hosted-sample.json](hosted-sample.json). The audit used the connected GitHub
job/log reader, not a new workflow dispatch. Source-equivalence check:

```bash
git diff 4a4cfe5460d80c5efed299c5171383a4aa697150 911d30a7427a8d3249ecd82a828952a3e4b639a0 -- .github/workflows/backtest-pipeline.yml .github/workflows/registry-check.yml .github/workflows/spec-gate.yml tests scripts/gate requirements.txt requirements-research.txt
```

Run full default docs audits on an actual base checkout and committed audit
branch, keeping existing findings visible. `--json` alone can exit zero with
findings; compare finding objects, not the exit code. No snapshot substitute,
`--no-owning-job-check`, stamping or suppression is used.

```bash
python scripts/maintenance/docs_audit.py --json
python scripts/gate/spec_gate.py --commit
python scripts/gate/spec_gate.py --pr origin/main
```

The source hash and per-file hashes bind the inventory. Runtime timings,
temporary paths, package versions and live GitHub issue state are observations
and need not regenerate byte-for-byte. The generator reproduces structure and
counts, not historical hosted evidence. It writes documentation artifacts only.
