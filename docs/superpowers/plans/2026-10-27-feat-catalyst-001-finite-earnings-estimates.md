---
feat_id: FEAT-CATALYST-001
spec: docs/superpowers/specs/2026-10-27-feat-catalyst-001-optional-earnings-estimate.md
branch: fix/feat-catalyst-001-finite-earnings-estimates
pr: null
status: ready
---

# Finite Nullable Earnings Estimates Implementation Plan

> For agentic workers: use the preserved native sole-writer execution method, task-by-task, then independent review. No competing author.

Goal: preserve unknown estimates as nullable values through the existing producer/storage/API path, retaining all legitimate finite EPS and events.
Architecture: existing producer scalar helper and API optional-estimate normalization use the same literal conformance fixtures, without a new COMMON API or parallel pipeline. The API must tolerate SQL NULL even after a correct producer.
Tech stack: existing Python/pandas/FastAPI/PostgreSQL/pytest.
Spec: docs/superpowers/specs/2026-10-27-feat-catalyst-001-optional-earnings-estimate.md.

## Global constraints

- Actual approved specification MAIN before implementation branch/code. This document is preparation outside the repository until that gate clears.
- Ownership clarification relayed at2026-10-27T16:30UTC: STRAT,earnings,score and gate worktrees have no producer-file edits/plans; STRAT/score child confirmed no _safe_num/direct-test work and relinquished any claim. This same root is sole writer for scripts/fetch_earnings_calendar.py::_safe_num, catalysts.py optionalEPS block and their named tests. No additional handoff/external contact is needed; score/OpenAPI/frontend hooks stay with their existing owner.
- No production/provider/SQL request, new table, schema, retry, schedule, formula or financial-data rewrite. Real PostgreSQL below is strictly local and fail-closed against any production/Cloud SQL endpoint.
- Preserve finite0,negative and positive values plus supported finite numeric strings; unknown/malformed/nonfinite/bool=>None, not0; keep event identity, date/source/as-of and valid siblings.
- Required source verification remains5seconds/8MiB/20000entries; normal review budgets/current-head checks/protected merge; no synthetic deployment proof.

## Review focus

- pandas nullable pd.NA must not trigger ambiguous truth evaluation (Task1 actualadapter controls).
- SQLNULL becomes floatNaN in a mixed numeric column (Task3 actual localPG/pandas test).
- native/NumPy boolean scalar must not become1/0 EPS (Task1/2 sharedliteralvectors).
- malformed optional estimate must not discard its event or another source (Task1 actualAPI sibling test).
- positive and negative infinity and numeric string representations must be unavailable while finite negative/zero retain meaning (Task1/2 conformance).

### Task 1: actual shared API event boundary — spec done_when0,2

Spec: § Smallest correct shared-layer repair and § Required conformance and evidence; advances done_when[0,2].

Files: platform/api/routers/catalysts.py earnings-only normalization block; new tests/api/test_catalyst_earnings_estimate_numbers.py; literal tests/fixtures/catalyst_finite_nullable_numbers.json. Consume current _db_catalyst_events(d_from,d_to,ticker_list)->list[dict], actual get_catalyst_events, no new endpoint. Produce local private _finite_earnings_estimate(value:object)->float|None; do not expose a COMMON interface.

- [x] Create literal input/expected fixture covering None,empty string,pandasNA,floatNaN/DecimalNaN,±inf/numericstrings,malformed scalar,bool/NumPybool, finite0/-1.25/1.25 and finite numericstring. Serialization maps named sentinel fixture tokens to actual native values; expected results are literal, not computed by implementation helper.
- [x] Add actualadapter test_nullable_estimate_contract_at_actual_response and parametrized real routed TestClient response test; seed safe cache and forbid all provider/cache-fetch/realSQL seams. Assert event retained, no nan/inf suffix, optional unavailable EPS omitted exactly like existingNone,0.00/-1.25/1.25 preserved and unrelated source/date/ticker/sibling fields unchanged. Assert nullable missing and malformed inputs do not raise.
- [x] Run only affected new tests against actual MAIN; retain failing cases, not just the earlier AST probe.
- [x] Implement minimal scalar normalization before float formatting; expected conversion errors only; preserve unrelated code/SQL/error paths and no string replacement of a completed title.
- [x] Run new controls and existing tests/api/test_catalysts_news_filter.py; verify query count/params and no calls to external seams. Run local spec gate before commit.

### Task 2: producer conformance, this same sole writer — spec done_when1,2

Spec: § Smallest correct shared-layer repair and § Ownership and sequencing; advances done_when[1,2].

Files: scripts/fetch_earnings_calendar.py::_safe_num under the verified sole-writer clarification; tests/scripts/test_earnings_calendar_finite_numbers.py; same shared literal fixture. Interface remains _safe_num(value)->float|None; existing valid consumers/fields unchanged.

- [x] Preserve exact owner clarification: the parent checked actual other-owned paths/plans and explicitly assigns this producer correction here. No competing writer is inferred from unrelated calendar1546. Full producer/API acceptance still requires the actual tests, not this ownership receipt.
- [x] Root adds test_safe_num_finite_nullable_contract using the same expected vectors and actual helper; red controls include admittedinfinity, bool and nullable missing. Add valid finite helper-caller controls because _safe_int delegates to _safe_num. No financial threshold/clamp or source collection change.
- [x] Root repairs only normalization and runs targeted producer/helper/persist tests; preserve exact source/result bytes, existing unrelated work and no schema changes.
- [x] Keep both disjoint helper corrections in the same approved implementation branch from actualMAIN, with one writer and normal independent review; do not stack on or copy another owner's private work.

### Task 3: genuine local PostgreSQL boundary — spec done_when1,2

Spec: § Required conformance and evidence and § Validation and release; advances done_when[1,2].

File tests/integration/test_catalyst_earnings_estimate_numbers_pg.py::test_sql_null_dataframe_roundtrip_preserves_missing.

- [x] Use existing ephemeral PostgreSQL fixture; explicit localhost/local socket allowlist and injected localengine; block CloudSQL/proxy/provider calls. No GCP environment credential use. Create isolated local fixture table/transaction, not any future av_options table or production migration.
- [x] Persist normalized null/valid finite producer rows through actual relevant local write/read path, obtain real local commit then query with actual pandas/SQL adapter; assert mixedNULL/finite read and API semantics. Baseline actualformatter fails, repairedAPI passes; unknown remainsNULL, finite0/negative unchanged, no event/sibling loss.
- [x] Tear down only fixture namespace; run existing relevant localPG suite. Retain command/source identity, no skips disguised as pass and no claim that local SQL proves production persistence.

### Task 4: current-head review and existing API/producer release — spec done_when3

Spec: § Validation and release and § Risks and exclusions; advances done_when[3].

- [ ] Own unique ready plan/PR, CAT catalog/traceability and only declaredCATALYSTS-04 note; coordinate record writes with earnings owner. Preserve foreign records, raw SITE body and upstreamMAIN changes.
- [ ] Regenerate committed source proof last against actualMAIN, fixed-bounds verify, matched main/branch audit with no new findings and local gates. One coherent review request when first fully ready, complete first independent review; no repeated loops or quota/options budget consumption.
- [ ] Existing API source path and only the verified existing fetch-earnings-calendar producer job, not a new pipeline or blanket image update. Before release map the actual producer command/image/config to the owner-adopted correction, preserve its schedule/args/resources/retries, inspect automatic migration default flags/historywrite/viewsweep and immutable old/new API and producer images/rollback targets. No deployment/DB/provider action on this preparation turn; normal release authorization/gates still govern later actions.
- [ ] After normal actual protected release, match exact deployed revision/image/source; parent-owned websiteQA checks real current served titles and finite0/negative controls where existing legitimate data permits. Use no providerrefresh or unapprovedSQL to manufacture evidence. Writer qualification requires a real approved writer receipt; job success/ACK alone is not persisted completeness.
- [ ] Post-merge record plan done separately, only after actual source merge; deployed verification/unknown source gaps remain explicit.

Self-review: all four specification acceptance clauses map to tasks; no named shared interface is invented. The localAST7red/5green reproduction is evidence for the starting defect, not a replacement for Task1ASGI or Task3PG. Producer ownership has been explicitly cleared here; score/hooks remain external existing owners.
