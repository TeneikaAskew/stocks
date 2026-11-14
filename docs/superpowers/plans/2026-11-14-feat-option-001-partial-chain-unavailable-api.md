---
feat_id: FEAT-OPTION-001
spec: docs/superpowers/specs/2026-11-05-feat-option-001-partial-chain-unavailable-api.md
branch: feature/feat-option-001-partial-chain-unavailable-api
pr: 1916
status: ready
---

# Partial options chains are unavailable through lib and every options route: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task cites a spec section and the `done_when` item it advances; indices are 0-based against the spec's list.

**Goal:** A calls-only or puts-only options chain reads as unavailable (unknown regime, null totals, a named reason) through `lib.gamma` and every options route, and the feature builders select the latest gamma snapshot strictly before the bar date whether or not the bar date has a snapshot of its own.

**Architecture:** One side-completeness helper in `lib/gamma.py` is called by `build_summary`, `build_grid_summary` and the chain, live-chain and Greeks routes, so every surface agrees on what "partial" means. The response models make the affected metrics nullable and add the two owner-approved chain fields with no server-side default. One `merge_asof`-based prior-snapshot lookup in the strat data builder replaces the two shift-joins. Both-sided behaviour is proved byte-identical against payloads captured from `main` before any code changes.

**Tech Stack:** Python 3, pandas, FastAPI + Pydantic v2 (`platform/api`), pytest with `TestClient` (`tests/api/`), the real-SQL harness (`tests/integration/`, ephemeral Postgres from `gcp/schema.sql`), `scripts/export_openapi.py`.

**Spec:** `docs/superpowers/specs/2026-11-05-feat-option-001-partial-chain-unavailable-api.md` (approved on main at `74840ddc`).

## Global Constraints

- No change to GEX, VEX, flip or balance formulas or sign conventions; no new eligibility threshold, source selector, cache policy or provider call; no collector, cursor, marker, ledger or recovery change; no production data write; no deployment claim (spec § Non-goals).
- Public chain field names are exactly `sides_present` (`"both" | "calls_only" | "puts_only"`) on `metadata` and top-level `chain_state` (`"available" | "unavailable"`) with a `reason` only when unavailable (spec § Design 2).
- `platform/api/openapi.json` changes only through `python3 scripts/export_openapi.py`; no operation added or removed (spec § Design 6, done_when[2]).
- Both-sided fixtures through every route keep every pre-existing field and numerical payload byte-identical to the baseline captured from `main`; new fields are asserted separately (done_when[0]).
- The feature-builder change is confined to the prior-snapshot selection in `gcp/research/strat_engine/strat_data_builder.py` and `gcp/research/p7_build_multi_tf_features.py` (spec § Design 5); those files belong to the STRAT lane, and the diff stays inside `_add_context` plus the one helper it calls.
- `0` is never written where a value is missing: `None` / `NaN` end to end (CLAUDE.md Rule 3.7, REQ-DATA-001).
- Spec-declared SITE notes `OPTIONS-01`, `OPTIONS-02`, `OPTIONS-05`: because this PR changes watched source, the gate requires each declared row in `docs/product/03-SITE-TRACEABILITY.md`'s `## Implementation-source notes` table to be added or updated with the current `source_identity_sha256`, and the sidecar regenerated with the reserved tool (product-delivery SKILL, committed-source identity). No other SITE byte changes.
- Every commit passes `python3 scripts/gate/spec_gate.py --commit`; commit messages carry no AI branding (CLAUDE.md § Git Commit Guidelines).

## Review Focus

Inputs the spec implies but does not name, each pinned to the task that owns it:

1. **A stored frame whose rows all carry an unrecognised `option_type`** normalises to zero contracts; `sides_present` has no value for it. Decision: the chain route answers the existing 404 ("No AlphaVantage options data…"), since nothing usable is stored; `option_type` is `VARCHAR(5) NOT NULL` without a CHECK, so the case is reachable. Test in Task 5.
2. **The two unavailable returns already inside `lib`** (no usable spot; vendor gamma missing on every contract) report `total_gex = 0.0` today. With `total_gex` nullable, leaving them at `0.0` keeps a fabricated zero beside a null one. Decision: they return `None` under the same contract; the two existing tests that assert `0.0` are rewritten to assert `None`. Tasks 1 and 2.
3. **A prior snapshot whose row is an unavailable marker** (every context column NULL, as the recovery part will write) must be selected and left NaN, never skipped for an older complete snapshot. Hermetic test in Task 8.
4. **A Greeks request with both sides but `spot_price <= 0`** has no measurable spot; today it returns `0.0` totals. It returns null metrics with `reason: "spot_unavailable"`, never `0.0`. Task 6.
5. **Consumers of `GammaSummary.total_gex`** that call `round()` or `float(x or 0.0)` on it (`lib/agents/summarizers.py:926`, `gcp/research/p2_build_gamma_levels.py:181`, `scripts/show_gamma_levels.py:87`) would raise or write `0.0` once it is `None`. Task 3 makes each one null-safe and tests the analyst path.

---

## Baseline (read from the tree at `960a9090`, the branch point; its code is identical to the spec merge `74840ddc`, which it follows by one docs-only commit)

- `lib/gamma.py`: `GammaSummary` L104-126 (`total_gex: float`), `GammaGridSummary` L176-200 (`total_gex: float`, `total_vex: float`); `put_call_ratio` L451-456 returns `0.0` when call OI is zero; `estimate_spot` L462-527 (parity needs both sides, then delta from calls, then median strike); `build_summary` L1014-1136 with the no-spot return at L1044-1049 and the full-outage return at L1058-1069, both `total_gex=0.0`; `build_grid_summary` L1156-1337 with the no-spot return at L1225-1241 (`total_gex=0.0, total_vex=0.0`).
- `platform/api/routers/options.py`: `_load_chain_entry` L531-648 (SELECT L577-593, `_df_to_contracts` L622, payload dict L631-641, cache store L647); `get_options` L651-657; `get_options_live` L663-759 (`_av_to_contracts` L722, 404 on empty L724-730, payload L732-741); `_GreeksRequest` L772-775; `compute_options_greeks` L783-836 with the `0.0` degenerate return at L798-811; `get_gamma_levels` L839-897.
- `platform/api/routers/grid.py`: `_df_to_contracts` L144-184; `_unavailable_envelope` L199-224 (`total_gex: 0.0`, `total_vex: 0.0` at L214-215); grid routes build the summary at L761 and L837; `_build_nodes_payload` L875-972 (`total_gex` L962, `total_vex` L963); nodes unavailable bodies at L1012-1032 and L1083-1103 (`0.0` at L1021-1022 and L1092-1093).
- `platform/api/schemas.py`: `ApiModel` is `extra="allow"` L43-46; `OptionsChainMetadata` L867-870; `OptionsChainResponse` L873-879; `OptionsMetrics` L903-909 (`total_gex: float`, `total_vex: float`, `put_call_ratio: float`); `GreeksResponse` L936-941; `GammaLevelsResponse` L982-998 (`total_gex: float`); `GammaGridResponse` L1024-1043; `GammaNodesResponse` L1067-1084. Routes use `response_model_exclude_unset=True`, so a key must be present in the payload dict to be emitted.
- `gcp/research/strat_engine/strat_data_builder.py`: `_load_gamma_levels` L226-255 (one row per `snapshot_date`, NULL `total_gex` preserved as `None`); `_add_context` L566-620 with the shift-join at L577-591 (`prior_gamma`, `prior_vex`) keyed on the snapshot dates themselves. `gcp/research/p7_build_multi_tf_features.py`: `_add_context` L375-425, same shift-join at L386-400; its `_load_gamma_levels` L122-151 still writes `float(first["total_gex"] or 0.0)` at L143 (an existing Rule 3.7 fallback, not touched here; `AUDIT` comment added beside it). Neither module imports the other, so p7 can import the new helper from the strat builder.
- `gamma_levels_eod` is created by `gcp/research/p2_build_gamma_levels.py:CREATE_TABLE_SQL` (L80-102), not by `gcp/schema.sql`; the integration job applies `gcp/schema.sql` only, so the real-SQL fixture creates the table from that constant.
- Tests: `tests/lib/test_gamma.py` (`_fixed_rate_and_yield` autouse L20-23; `TestBuildSummary` L283; `TestBuildGridSummary._build_chain` L585-620; outage tests L1090-1143); `tests/api/test_options_router.py` (`_opt` L39, `TestGreeksDegenerateInputs` L166-187 asserting `0.0`, `_chain_frame` L232-264, `chain_client`/`chain_clock` L266-283, `_install_chain_query` L285, `BASELINE_CHAIN_KEYS` L217); `tests/api/test_options_live.py` (`client` L31, `_FAKE_AV_OK` L45, `_patch_av` L107); `tests/api/test_grid_router.py` (`_chain_df` L39, `client` L102, `_install_query_router` L123, `BASELINE_GRID` L951, `BASELINE_ENVELOPE_KEYS` L974); `tests/gcp/test_strat_data_builder_gamma.py` (`test_dealer_regime_null_when_gex_missing` L73-117 builds `gamma_df`, `vex_df`, `vix_df`, bars); `tests/integration/conftest.py` (`db_engine`, `clean_db`, `seed`, `run_sql`); `tests/agents/test_agent_summarizers.py` (`patch_query` L19, `_eod_chain_fixture` L482).
- Branches sharing the contract files (read 2026-11-14 03:40 UTC): none of the recent remote branches changes `platform/api/openapi.json`, `platform/api/schemas.py`, `lib/gamma.py` or the two routers except two FEAT-INSIGHT watchlist branches and one FEAT-REPLAY branch, which touch `openapi.json`/`schemas.py` only. Whichever lands second regenerates the snapshot (spec § Delivery).

## done_when map

| done_when | Item (abridged) | Tasks |
|---|---|---|
| [0] | lib, chain, live chain, Greeks, levels, grid, nodes: partial is unavailable; both-sided byte-identical to main | 0, 1, 2, 3, 4, 5, 6, 7 |
| [1] | PostgreSQL strict-prior fixture, both cases; NaN never 0 | 8, 9 |
| [2] | OpenAPI regenerated, snapshot test passes, no operation added or removed, hunks in PR body | 10 |
| [3] | Tests, review, CI, records, gate, docs audit without waivers | 11, 12 |

## Capacity (CLAUDE.md rule 0; copied into the PR body)

- **Volume:** 0 new rows read or written; the side check runs over the rows the existing statements already select (about 5K contracts per chain, 6 in fixtures).
- **Velocity:** 0 additional SQL statements, 0 provider calls, 0 network round trips per request.
- **Wall-clock:** one pass over the selected rows' `type` field per request (sub-millisecond at 5K rows); the feature builders' `merge_asof` replaces a `shift` over the same frame; no Cloud Run job, scheduler or task-timeout change.
- **Cost:** $0 per run × 0 runs/day × 30 = $0/month.

---

### Task 0: Branch, baseline capture and draft PR

Spec: § Verification ("baseline numerics for both-sided fixtures are captured from main"). Advances done_when[0].

**Files:**
- Create: `tests/api/_options_baseline_capture.py` (not collected by pytest: underscore prefix)
- Create: `tests/fixtures/options_routes_baseline_960a9090.json`
- Modify: this plan (`pr:` after the PR exists)

**Interfaces:**
- Produces: `tests/fixtures/options_routes_baseline_960a9090.json`, a JSON object keyed `chain`, `live_chain`, `greeks`, `levels`, `grid_live`, `grid_dated`, `nodes_live`, `nodes_dated`, each the exact `response.json()` of the named route on `960a9090` for the fixture inputs below.
- Produces: `capture(repo_root: Path) -> dict` in `_options_baseline_capture.py`, and `python3 tests/api/_options_baseline_capture.py --repo <path> --out <file>`.

Fixture inputs (the ones the existing test modules already use, so later tasks reuse them unchanged):
- `chain`, `levels`: `tests/api/test_options_router.py::_chain_frame()` installed as the only `query_to_dataframe` result; `GET /api/options/SPY/2026-06-01`, `GET /api/options/SPY/2026-06-01/levels`.
- `live_chain`: `tests/api/test_options_live.py::_FAKE_AV_OK` through `_patch_av`; `GET /api/options/live/SPY/2025-01-17`.
- `greeks`: `POST /api/options/greeks` with `spot_price=100.05` and the six `_chain_frame()` contracts as `_OptionRecord`s (`type`, `strike`, `open_interest`, `gamma`, `vega`, `delta`, `volume`).
- `grid_live`, `nodes_live`: `tests/api/test_grid_router.py::_chain_df(date(2026, 6, 1), "REALTIME", tz="UTC")` as the REALTIME result; `GET /api/options/SPY/grid`, `GET /api/options/SPY/nodes`.
- `grid_dated`, `nodes_dated`: the same frame as the EOD result; `GET /api/options/SPY/2026-06-01/grid`, `GET /api/options/SPY/2026-06-01/nodes`.
- Clock: `_now_utc` patched to `datetime(2026, 6, 3, 14, 0, tzinfo=UTC)` in both routers so `snapshot_provenance.observed_at` is stable.

- [ ] **Step 1: Create the branch from main and commit this plan**

```bash
git fetch origin main && git checkout -b feature/feat-option-001-partial-chain-unavailable-api origin/main
python3 scripts/gate/spec_gate.py --commit
git add docs/superpowers/plans/2026-11-14-feat-option-001-partial-chain-unavailable-api.md
git commit -m "docs(plan): FEAT-OPTION-001 partial-chain unavailable API implementation plan"
```

- [ ] **Step 2: Write `capture(repo_root)`**: insert `repo_root`, `repo_root/platform`, `repo_root/platform/api` and `repo_root/tests/api` on `sys.path`, set `gcp.database.is_cloud_sql_configured` to `lambda: True`, build one `FastAPI()` with both routers, install the fixtures above per route, call each route, and return the dict. `main()` parses `--repo` and `--out` and writes `json.dumps(payload, indent=2, sort_keys=True) + "\n"`.

- [ ] **Step 3: Capture from a main worktree, not from this branch**

```bash
git worktree add /tmp/claude-0/-home-user-stocks/440ccc5b-c0c7-5698-9057-db082f2722d0/scratchpad/main-960a9090 960a9090
python3 tests/api/_options_baseline_capture.py --repo /tmp/claude-0/-home-user-stocks/440ccc5b-c0c7-5698-9057-db082f2722d0/scratchpad/main-960a9090 --out tests/fixtures/options_routes_baseline_960a9090.json
git worktree remove /tmp/claude-0/-home-user-stocks/440ccc5b-c0c7-5698-9057-db082f2722d0/scratchpad/main-960a9090
```
Expected: the file holds eight keys; `levels.total_gex == 600.60015` and `grid_live.total_gex == 600.60015` (the values `BASELINE_LEVELS` and `BASELINE_GRID` already pin); `chain.metadata` has exactly `source`, `data_source`, `row_count`; `greeks.metrics.put_call_ratio` is a number.

- [ ] **Step 4: Commit, push, open the draft PR, record its number**

```bash
git add tests/api/_options_baseline_capture.py tests/fixtures/options_routes_baseline_960a9090.json
git commit -m "test(options): pin main's both-sided route payloads as the compatibility baseline"
git push -u origin feature/feat-option-001-partial-chain-unavailable-api
```
Open the draft PR titled `FEAT-OPTION-001: partial options chains are unavailable through lib and every options route`, body per product-delivery Phase 4 (spec and plan paths, the four `done_when` items as unticked `- [ ]` lines, the Capacity section above). Set `pr:` in this plan to the number and commit `docs(plan): record PR number`.

---

### Task 1: Side completeness in `lib.gamma.build_summary`

Spec: § Design 1. Advances done_when[0].

**Files:**
- Modify: `lib/gamma.py` (constants after `GEX_MULTIPLIER`; helpers after `greeks_coverage` L203-229; `GammaSummary.total_gex` L117; `build_summary` L1014-1136)
- Test: `tests/lib/test_gamma.py`

**Interfaces:**
- Produces, in `lib/gamma.py`:
  - `SIDES_BOTH = "both"`, `SIDES_CALLS_ONLY = "calls_only"`, `SIDES_PUTS_ONLY = "puts_only"`, `SIDES_EMPTY = "empty"`
  - `chain_sides(options: Sequence[dict]) -> str`: one of the four constants, from `o.get("type") in ("call", "put")` over the records.
  - `partial_chain_reason(sides: str) -> str | None`: `"puts_missing"` for `calls_only`, `"calls_missing"` for `puts_only`, `"empty_chain"` for `empty`, `None` for `both`.
  - `partial_chain_warning(sides: str) -> str`: `"Chain has no put contracts: GEX, VEX, gamma balance and gamma flip are unavailable for this snapshot, not zero."` (calls_only) and the `call contracts` counterpart (puts_only).
  - `GammaSummary.total_gex: float | None`.
- `build_summary` order: expiry filter, spot resolution (unchanged), **side check**, no-spot return, coverage gate, aggregation. A partial chain returns `GammaSummary(spot=spot, gamma_balance=None, gamma_flip=None, regime="unknown", total_gex=None, levels=[], kings=[], gates=[], gamma_balance_levels=[], warnings=warnings + [partial_chain_warning(sides)])`. The no-spot return and the full-outage return set `total_gex=None` (Review Focus 2). An empty chain reaches the no-spot return as today (`estimate_spot([])` is `method="none"`).

- [ ] **Step 1: Write the failing tests** in a new `class TestPartialChainIsUnavailable` in `tests/lib/test_gamma.py`, using `_chain_row` (L1062) with `typ="call"` / `typ="put"` and `expiration="2026-06-19"`:

```python
def test_calls_only_chain_is_unavailable_with_spot_from_delta(self):
    rows = [_chain_row(s, typ="call", delta=d) for s, d in ((98, 0.7), (100, 0.5), (102, 0.3))]
    s = gamma.build_summary("SPY", "2026-06-01", rows)
    assert (s.regime, s.total_gex, s.gamma_balance, s.gamma_flip) == ("unknown", None, None, None)
    assert s.levels == [] and s.kings == [] and s.gates == []
    assert s.spot.method == "delta" and s.spot.price == 100.0
    assert gamma.partial_chain_warning("calls_only") in s.warnings

def test_puts_only_chain_is_unavailable_with_median_spot(self):
    rows = [_chain_row(s, typ="put") for s in (98, 100, 102)]
    s = gamma.build_summary("SPY", "2026-06-01", rows)
    assert s.total_gex is None and s.regime == "unknown"
    assert s.spot.method == "median_strike"
    assert gamma.partial_chain_warning("puts_only") in s.warnings

def test_both_sided_no_crossing_keeps_its_own_warning_not_the_partial_one(self):
    # the TestBuildSummary fixtures: flip None via the hermetic rate, regime from sign
    opts = [{"type": "put", "strike": 95, "open_interest": 500, "gamma": 0.05, "expiration": "2025-01-01"},
            {"type": "call", "strike": 105, "open_interest": 2000, "gamma": 0.05, "expiration": "2025-01-01"}]
    s = gamma.build_summary("XYZ", "2025-01-01", opts, spot_override=100)
    assert s.regime == "positive_gamma" and s.total_gex > 0
    assert not any("no put contracts" in w or "no call contracts" in w for w in s.warnings)

def test_chain_sides_and_reasons(self):
    assert gamma.chain_sides([]) == "empty"
    assert gamma.chain_sides([{"type": "call"}]) == "calls_only"
    assert gamma.chain_sides([{"type": "put"}]) == "puts_only"
    assert gamma.chain_sides([{"type": "call"}, {"type": "put"}]) == "both"
    assert [gamma.partial_chain_reason(s) for s in ("both", "calls_only", "puts_only", "empty")] == [None, "puts_missing", "calls_missing", "empty_chain"]
```
Rewrite `test_build_summary_all_gamma_missing_is_unavailable_not_zero` (L1090) and `test_build_summary_nan_outage_is_unavailable_and_not_nan` (L1129) to assert `s.total_gex is None` (Review Focus 2), keeping their warning assertions.

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/lib/test_gamma.py -k "PartialChain or outage or all_gamma_missing" -v`
Expected: FAIL (`chain_sides` undefined; `total_gex == 0.0`).

- [ ] **Step 3: Implement** the constants, the three helpers and the `build_summary` order above; change `GammaSummary.total_gex` to `float | None`.

- [ ] **Step 4: Run the whole module**

Run: `python3 -m pytest tests/lib/test_gamma.py tests/lib/test_gamma_never_null.py tests/lib/test_gamma_proximity.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/gamma.py tests/lib/test_gamma.py
git commit -m "feat(gamma): a one-sided chain is unavailable, not a one-sided total"
```

---

### Task 2: Side completeness in `build_grid_summary`, nullable grid totals

Spec: § Design 1, § Design 4 (lib half). Advances done_when[0].

**Files:**
- Modify: `lib/gamma.py` (`GammaGridSummary.total_gex`, `total_vex` L188-189; `build_grid_summary` L1156-1337)
- Test: `tests/lib/test_gamma.py`

**Interfaces:**
- Consumes: `chain_sides`, `partial_chain_warning` from Task 1.
- Produces: `GammaGridSummary.total_gex: float | None`, `total_vex: float | None`. `build_grid_summary` applies the side check right after spot resolution (same position as Task 1) and returns `cells=[]`, `expirations=[]`, `strikes=[]`, `regime="unknown"`, `total_gex=None`, `total_vex=None`, `gamma_balance=None`, `gamma_flip=None`, the partial warning appended, the spot preserved. Its no-spot return (L1225-1241) sets both totals to `None`.

- [ ] **Step 1: Write the failing tests** in `TestBuildGridSummary`:

```python
def test_calls_only_grid_is_unavailable(self):
    opts = [o for o in self._build_chain() if o["type"] == "call"]
    g = gamma.build_grid_summary("XYZ", "2026-05-23", opts, window_pct=15.0)
    assert (g.regime, g.total_gex, g.total_vex, g.gamma_balance, g.gamma_flip) == ("unknown", None, None, None, None)
    assert g.cells == [] and g.expirations == [] and g.strikes == []
    assert g.spot.method == "delta"
    assert gamma.partial_chain_warning("calls_only") in g.warnings

def test_puts_only_grid_is_unavailable(self):
    opts = [o for o in self._build_chain() if o["type"] == "put"]
    g = gamma.build_grid_summary("XYZ", "2026-05-23", opts, window_pct=15.0)
    assert g.total_gex is None and g.total_vex is None and g.cells == []

def test_both_sided_grid_numerics_unchanged(self):
    g = gamma.build_grid_summary("XYZ", "2026-05-23", self._build_chain(), window_pct=15.0)
    assert len(g.cells) == 5 and g.total_gex == sum(c.gex for c in g.cells) and g.total_vex == sum(c.vex for c in g.cells)

def test_grid_no_spot_returns_null_totals(self):
    g = gamma.build_grid_summary("XYZ", "2026-05-23", [], window_pct=15.0)
    assert g.spot.method == "none" and g.total_gex is None and g.total_vex is None
```

- [ ] **Step 2: Run to verify they fail**: `python3 -m pytest tests/lib/test_gamma.py -k "grid_is_unavailable or no_spot_returns_null" -v` → FAIL.
- [ ] **Step 3: Implement** as in Interfaces.
- [ ] **Step 4: Run**: `python3 -m pytest tests/lib/ -q` → PASS.
- [ ] **Step 5: Commit**: `git commit -am "feat(gamma): grid summary reports a one-sided chain as unavailable with null totals"`

---

### Task 3: Consumers of a nullable `total_gex`

Spec: § Design 1 ("analyst" in done_when[0]); Review Focus 5. Advances done_when[0].

**Files:**
- Modify: `lib/agents/summarizers.py:926` (`"total_gex": round(summary.total_gex, 0)`)
- Modify: `gcp/research/p2_build_gamma_levels.py:181` (`total_gex=float(summary.total_gex or 0.0)`)
- Modify: `scripts/show_gamma_levels.py:87` (`fmt_gex(summary.total_gex)`)
- Modify: `gcp/research/p7_build_multi_tf_features.py:143` (comment only)
- Test: `tests/agents/test_agent_summarizers.py`, `tests/lib/test_gamma.py` (p2 row builder)

**Interfaces:**
- `summarize_gamma_levels` emits `"total_gex": None` when the summary's total is `None`, otherwise the existing rounding; the rest of its payload is unchanged (`available` stays `True`: the chain was read; the warning names why the gamma fields are null).
- `p2._process_one_day` writes `total_gex=None` when the summary's total is `None` (`gamma_levels_eod.total_gex` is nullable `DOUBLE PRECISION`; `_load_gamma_levels` already reads NULL as `None`). For a partial chain `summary.kings`/`gates` are empty and `gamma_balance` is `None`, so no level rows are emitted and the function returns `[]` as it does for a thin chain today.
- `show_gamma_levels.render` prints `unavailable` for a `None` total.
- `p7._load_gamma_levels` L143 gets the comment `# AUDIT-2026-05-13: silent fallback (or 0.0 on NULL total_gex); see docs/audits/FALLBACK_AUDIT_2026-05-13.md` and no code change.

- [ ] **Step 1: Write the failing analyst test** beside `test_gamma_levels_extracts_kings_and_regime`:

```python
def test_gamma_levels_calls_only_chain_is_unavailable_not_zero(patch_query):
    chain = _eod_chain_fixture(date(2026, 5, 12))
    patch_query("market_session = 'EOD'", chain[chain["option_type"] == "calls"])
    out = summarizers.summarize_gamma_levels("XYZ", as_of=date(2026, 5, 13))
    assert out["available"] is True
    assert out["total_gex"] is None and out["regime"] == "unknown"
    assert out["gamma_balance"] is None and out["gamma_flip"] is None
    assert out["kings"] == [] and out["gates"] == []
    assert any("no put contracts" in w for w in out["warnings"])
```
And a p2 test in `tests/lib/test_gamma.py` (the module already imports the research builders in sibling tests) or a new `tests/gcp/test_p2_build_gamma_levels_partial.py` if `tests/gcp/` has no p2 module yet:

```python
def test_partial_chain_emits_no_level_rows_and_no_zero_total(monkeypatch):
    from gcp.research import p2_build_gamma_levels as p2
    rows = pd.DataFrame([{"option_type": "calls", "strike": s, "expiration": date(2026, 6, 19), "open_interest": 100,
                          "gamma": 0.05, "vega": 0.1, "delta": d, "bid": 1.0, "ask": 1.1, "mark": 1.05, "last_price": 1.05}
                         for s, d in ((98.0, 0.7), (100.0, 0.5), (102.0, 0.3))])
    assert p2._process_one_day("SPY", date(2026, 6, 1), rows) == []
```

- [ ] **Step 2: Run to verify failure**: `python3 -m pytest tests/agents/test_agent_summarizers.py -k calls_only -v` → FAIL with `TypeError: type NoneType doesn't define __round__`.
- [ ] **Step 3: Implement** the three null-safe sites and the AUDIT comment.
- [ ] **Step 4: Run**: `python3 -m pytest tests/agents/test_agent_summarizers.py tests/lib/test_gamma.py tests/gcp/test_strat_data_builder_gamma.py -q` → PASS.
- [ ] **Step 5: Commit**: `git commit -am "fix(gamma): consumers carry a null total_gex instead of rounding or zeroing it"`

---

### Task 4: Response models

Spec: § Design 2, 3, 4 (schema half). Advances done_when[0]; prepares done_when[2].

**Files:**
- Modify: `platform/api/schemas.py` (`OptionsChainMetadata` L867-870, `OptionsChainResponse` L873-879, `OptionsMetrics` L903-909, `GreeksResponse` L936-941, `GammaLevelsResponse` L989, `GammaGridResponse` L1036-1037, `GammaNodesResponse` L1075-1076)
- Test: `tests/api/test_partial_chain_unavailable.py` (new module; also hosts Tasks 5 to 7)

**Interfaces:**
- `OptionsChainMetadata.sides_present: Literal["both", "calls_only", "puts_only"]` (required, no default).
- `OptionsChainResponse.chain_state: Literal["available", "unavailable"]` (required, no default); `reason: Optional[str] = None`.
- `OptionsMetrics.total_gex: Optional[float]`, `total_vex: Optional[float]`, `put_call_ratio: Optional[float]` (required, nullable: no default).
- `GreeksResponse.reason: Optional[str] = None`.
- `GammaLevelsResponse.total_gex: Optional[float]`; `GammaGridResponse.total_gex`, `total_vex: Optional[float]`; `GammaNodesResponse.total_gex`, `total_vex: Optional[float]` (all required, nullable).

- [ ] **Step 1: Write the failing schema tests** at the top of `tests/api/test_partial_chain_unavailable.py` (same import preamble as `test_options_router.py`, plus `from api import schemas` under `platform/` on `sys.path`):

```python
def test_chain_fields_have_no_server_default():
    assert schemas.OptionsChainMetadata.model_fields["sides_present"].is_required()
    assert schemas.OptionsChainResponse.model_fields["chain_state"].is_required()
    assert schemas.OptionsChainResponse.model_fields["reason"].default is None

def test_metrics_and_totals_are_nullable_but_required():
    for model, field in ((schemas.OptionsMetrics, "total_gex"), (schemas.OptionsMetrics, "total_vex"),
                         (schemas.OptionsMetrics, "put_call_ratio"), (schemas.GammaLevelsResponse, "total_gex"),
                         (schemas.GammaGridResponse, "total_gex"), (schemas.GammaGridResponse, "total_vex"),
                         (schemas.GammaNodesResponse, "total_gex"), (schemas.GammaNodesResponse, "total_vex")):
        info = model.model_fields[field]
        assert info.is_required(), (model, field)
        assert model.model_validate({**_minimal(model), field: None}).model_dump()[field] is None
```
where `_minimal(model)` builds the smallest valid payload per model from the fixture file of Task 0 (`chain`, `greeks`, `levels`, `grid_live`, `nodes_live` keys) with the new required fields added.

- [ ] **Step 2: Run to verify failure**: `PYTHONPATH=platform python3 -m pytest tests/api/test_partial_chain_unavailable.py -k "no_server_default or nullable" -v` → FAIL (`KeyError: 'sides_present'`).
- [ ] **Step 3: Implement** the model changes.
- [ ] **Step 4: Run**: same command → PASS; `python3 -m pytest tests/api/test_openapi_snapshot.py -q` → FAIL (stale snapshot, expected until Task 10).
- [ ] **Step 5: Commit**: `git commit -am "feat(api): chain sides_present and chain_state, nullable gamma metrics on the options models"`

---

### Task 5: Chain route and live chain route

Spec: § Design 2; Review Focus 1. Advances done_when[0].

**Files:**
- Modify: `platform/api/routers/options.py` (`_load_chain_entry` L622-648; `get_options_live` L722-741)
- Test: `tests/api/test_partial_chain_unavailable.py`, `tests/api/test_options_router.py` (`BASELINE_CHAIN_KEYS` L217, `BASELINE_CHAIN_METADATA` L218 and the two tests that use them)

**Interfaces:**
- Produces, in `options.py`: `_chain_state_fields(contracts: list[dict]) -> tuple[str, str, str | None]` returning `(sides_present, chain_state, reason)` from `gamma.chain_sides`; for `both` → `("both", "available", None)`; for `calls_only`/`puts_only` → `(sides, "unavailable", gamma.partial_chain_reason(sides))`. It is never called with an empty list.
- `_load_chain_entry`: after `contracts = _df_to_contracts(df)`, if `contracts` is empty raise the existing 404 (Review Focus 1); else set `response["metadata"]["sides_present"]`, `response["chain_state"]`, and `response["reason"]` only when unavailable. The cached payload carries them, so hits are identical to misses.
- `get_options_live`: after the existing 404 on empty `contracts`, the same three fields on `payload`.
- Nothing else in either route changes: `snapshot_timestamp`, `cached`, `source`, `data_source`, `row_count`, caches, 404 text.

- [ ] **Step 1: Write the failing tests** (fixtures imported from `test_options_router` and `test_options_live`; `BASELINE = json.loads(Path("tests/fixtures/options_routes_baseline_960a9090.json").read_text())`):

```python
def _without(d, *keys): return {k: v for k, v in d.items() if k not in keys}
def _canon(d): return json.dumps(d, sort_keys=True)

class TestChainRoute:
    def test_both_sided_chain_byte_identical_plus_new_fields(self, chain_client, chain_clock, monkeypatch):
        _install_chain_query(monkeypatch, _chain_frame())
        data = chain_client.get("/api/options/SPY/2026-06-01").json()
        assert _canon({**_without(data, "chain_state"), "metadata": _without(data["metadata"], "sides_present")}) == _canon(BASELINE["chain"])
        assert data["metadata"]["sides_present"] == "both" and data["chain_state"] == "available" and "reason" not in data

    def test_calls_only_chain_keeps_rows_and_is_unavailable(self, chain_client, chain_clock, monkeypatch):
        df = _chain_frame(); _install_chain_query(monkeypatch, df[df["option_type"] == "calls"])
        data = chain_client.get("/api/options/SPY/2026-06-01").json()
        assert data["metadata"]["sides_present"] == "calls_only" and data["chain_state"] == "unavailable"
        assert data["reason"] == "puts_missing" and len(data["options"]) == 3 and data["metadata"]["row_count"] == 3

    def test_puts_only_chain_reason_names_calls(self, ...): ... assert data["reason"] == "calls_missing"

    def test_warm_hit_carries_the_same_state(self, chain_client, chain_clock, monkeypatch):
        df = _chain_frame(); calls = _install_chain_query(monkeypatch, df[df["option_type"] == "puts"])
        first = chain_client.get("/api/options/SPY/2026-06-01").json(); second = chain_client.get("/api/options/SPY/2026-06-01").json()
        assert len(calls) == 1 and _without(first, "cached") == _without(second, "cached") and second["cached"] is True

    def test_unrecognised_option_type_rows_answer_404(self, chain_client, chain_clock, monkeypatch):
        df = _chain_frame(); df["option_type"] = "junk"; _install_chain_query(monkeypatch, df)
        r = chain_client.get("/api/options/SPY/2026-06-01"); assert r.status_code == 404 and "No AlphaVantage options data" in r.json()["detail"]

class TestLiveChainRoute:
    def test_both_sided_live_byte_identical_plus_new_fields(self, client, monkeypatch):  # `client` from test_options_live
        _patch_av(monkeypatch, _FakeResponse(200, _FAKE_AV_OK)); data = client.get("/api/options/live/SPY/2025-01-17").json()
        assert _canon({**_without(data, "chain_state", "snapshot_timestamp"), "metadata": _without(data["metadata"], "sides_present")}) == _canon(_without(BASELINE["live_chain"], "snapshot_timestamp"))
        assert data["metadata"]["sides_present"] == "both" and data["chain_state"] == "available"

    def test_calls_only_live_is_unavailable(self, client, monkeypatch):
        body = {**_FAKE_AV_OK, "data": [r for r in _FAKE_AV_OK["data"] if r["type"] == "call"]}
        _patch_av(monkeypatch, _FakeResponse(200, body)); data = client.get("/api/options/live/SPY/2025-01-17").json()
        assert data["metadata"]["sides_present"] == "calls_only" and data["chain_state"] == "unavailable" and data["reason"] == "puts_missing" and len(data["options"]) == 1
```
(The live route stamps `snapshot_timestamp` from `datetime.utcnow()`, so that key is excluded from the byte comparison and asserted present.) Update `test_options_router.py::BASELINE_CHAIN_KEYS` to include `chain_state`, `BASELINE_CHAIN_METADATA` to include `"sides_present": "both"`, and keep `test_chain_http_shape_unchanged_no_provenance_key` asserting that `snapshot_provenance` is absent.

- [ ] **Step 2: Run to verify failure**: `PYTHONPATH=platform python3 -m pytest tests/api/test_partial_chain_unavailable.py -k "Chain" -v` → FAIL (`KeyError: 'sides_present'` / `ResponseValidationError`).
- [ ] **Step 3: Implement** `_chain_state_fields` and the two route edits.
- [ ] **Step 4: Run**: `PYTHONPATH=platform python3 -m pytest tests/api/test_partial_chain_unavailable.py tests/api/test_options_router.py tests/api/test_options_live.py tests/api/test_threadpool_races.py tests/api/test_api_handler_dispatch.py -q` → PASS.
- [ ] **Step 5: Commit**: `git commit -am "feat(options): chain and live chain report sides_present and chain_state"`

---

### Task 6: Greeks route

Spec: § Design 3; Review Focus 4. Advances done_when[0].

**Files:**
- Modify: `platform/api/routers/options.py` (`compute_options_greeks` L783-836)
- Test: `tests/api/test_partial_chain_unavailable.py`, `tests/api/test_options_router.py::TestGreeksDegenerateInputs` L166-187

**Interfaces:**
- `compute_options_greeks`: `opts = _opts_to_dicts(req.options)`; `sides = gamma.chain_sides(opts)`; when `sides != gamma.SIDES_BOTH` or `req.spot_price <= 0`, return `{"aggregated": [], "gex_by_strike": [], "metrics": {"total_gex": None, "total_vex": None, "zero_gamma": None, "max_pain": None, "implied_move": None, "put_call_ratio": None}, "nodes": {"kingNode": None, "gatekeepers": [], "midpoints": [], "allNodes": []}, "config": config, "reason": reason}` with `reason = gamma.partial_chain_reason(sides) or "spot_unavailable"` (the side reason wins when both apply). The both-sided path is unchanged and carries no `reason` key.

- [ ] **Step 1: Write the failing tests**:

```python
class TestGreeksRoute:
    def test_both_sided_byte_identical(self, chain_client):
        r = chain_client.post("/api/options/greeks", json={"spot_price": 100.05, "options": _baseline_option_records()})
        assert _canon(r.json()) == _canon(BASELINE["greeks"]) and "reason" not in r.json()

    @pytest.mark.parametrize("side,reason", [("call", "puts_missing"), ("put", "calls_missing")])
    def test_one_sided_chain_null_metrics_with_reason(self, chain_client, side, reason):
        recs = [o for o in _baseline_option_records() if o["type"] == side]
        data = chain_client.post("/api/options/greeks", json={"spot_price": 100.05, "options": recs}).json()
        assert data["metrics"] == {"total_gex": None, "total_vex": None, "zero_gamma": None, "max_pain": None, "implied_move": None, "put_call_ratio": None}
        assert data["reason"] == reason and data["aggregated"] == [] and data["gex_by_strike"] == [] and data["nodes"]["kingNode"] is None

    def test_empty_chain_reason(self, chain_client):
        assert chain_client.post("/api/options/greeks", json={"spot_price": 100.05, "options": []}).json()["reason"] == "empty_chain"

    def test_non_positive_spot_reason(self, chain_client):
        data = chain_client.post("/api/options/greeks", json={"spot_price": 0.0, "options": _baseline_option_records()}).json()
        assert data["reason"] == "spot_unavailable" and data["metrics"]["total_gex"] is None and data["metrics"]["put_call_ratio"] is None
```
`_baseline_option_records()` builds the six `_chain_frame()` contracts as plain dicts with `type`, `strike`, `open_interest`, `gamma`, `vega`, `delta`, `volume` (the same records Task 0 captured). Rewrite `TestGreeksDegenerateInputs` (L166-187) so the three tests assert `["metrics"]["total_gex"] is None` and the matching `reason` (`empty_chain`, `spot_unavailable`, `spot_unavailable`).

- [ ] **Step 2: Run to verify failure**: `PYTHONPATH=platform python3 -m pytest tests/api/test_partial_chain_unavailable.py -k Greeks tests/api/test_options_router.py -k Degenerate -v` → FAIL (`0.0 is not None`).
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run**: `PYTHONPATH=platform python3 -m pytest tests/api/test_partial_chain_unavailable.py tests/api/test_options_router.py tests/api/test_route_coverage.py -q` → PASS (`test_route_coverage` keeps its 422 for a body without `spot_price`).
- [ ] **Step 5: Commit**: `git commit -am "feat(options): Greeks route returns null metrics with a reason for a one-sided or spotless chain"`

---

### Task 7: Levels, grid and nodes routes

Spec: § Design 4. Advances done_when[0].

**Files:**
- Modify: `platform/api/routers/grid.py` (`_unavailable_envelope` L214-215; nodes unavailable bodies L1021-1022, L1092-1093)
- Test: `tests/api/test_partial_chain_unavailable.py`, `tests/api/test_grid_router.py` (`test_unavailable_envelope_when_no_data` L170, `test_unavailable_envelope_shape` L318: add `total_gex is None` assertions; `BASELINE_GRID`, `BASELINE_ENVELOPE_KEYS` unchanged)

**Interfaces:**
- `_unavailable_envelope` and both nodes unavailable bodies carry `"total_gex": None, "total_vex": None`; keys unchanged. The levels, grid and nodes routes need no code change for partial chains: `build_summary`/`build_grid_summary` now return the unavailable result and the models accept it. `_build_nodes_payload` passes `summary_1d.total_gex` and `grid.total_vex` through unchanged (now `None` for a partial chain); its `spot` block already handles `price > 0`.

- [ ] **Step 1: Write the failing tests** (grid fixtures from `test_grid_router`: `client`, `clock`, `_install_query_router`, `_chain_df`; levels fixtures from `test_options_router`):

```python
class TestLevelsRoute:
    def test_both_sided_byte_identical(self, chain_client, chain_clock, monkeypatch):
        _install_chain_query(monkeypatch, _chain_frame())
        assert _canon(chain_client.get("/api/options/SPY/2026-06-01/levels").json()) == _canon(BASELINE["levels"])
    def test_puts_only_levels_unknown_regime_null_total_with_warning(self, chain_client, chain_clock, monkeypatch):
        df = _chain_frame(); _install_chain_query(monkeypatch, df[df["option_type"] == "puts"])
        data = chain_client.get("/api/options/SPY/2026-06-01/levels").json()
        assert data["regime"] == "unknown" and data["total_gex"] is None and data["gamma_balance"] is None and data["gamma_flip"] is None
        assert data["kings"] == [] and data["levels"] == [] and data["chain_size"] == 3
        assert gamma.partial_chain_warning("puts_only") in data["warnings"]

class TestGridRoutes:
    def test_live_and_dated_both_sided_byte_identical(self, client, clock, monkeypatch):
        _install_query_router(monkeypatch, realtime_df=_chain_df(FIX_DATE, "REALTIME", tz="UTC"), eod_df=_chain_df(FIX_DATE, "REALTIME", tz="UTC"))
        assert _canon(client.get("/api/options/SPY/grid").json()) == _canon(BASELINE["grid_live"])
        assert _canon(client.get("/api/options/SPY/2026-06-01/grid").json()) == _canon(BASELINE["grid_dated"])
    def test_calls_only_live_grid_is_unavailable_with_rows_selected(self, client, clock, monkeypatch):
        df = _chain_df(FIX_DATE, "REALTIME", tz="UTC"); _install_query_router(monkeypatch, realtime_df=df[df["option_type"] == "calls"])
        data = client.get("/api/options/SPY/grid").json()
        assert data["data_source"] == "realtime" and data["regime"] == "unknown" and data["total_gex"] is None and data["total_vex"] is None and data["cells"] == []
        assert gamma.partial_chain_warning("calls_only") in data["warnings"] and data["snapshot_provenance"] is not None
    def test_unavailable_envelope_totals_are_null(self, client, clock, monkeypatch):
        _install_query_router(monkeypatch); data = client.get("/api/options/RANDOM/grid?allow_on_demand=false").json()
        assert data["total_gex"] is None and data["total_vex"] is None and sorted(k for k in data if k != "snapshot_provenance") == BASELINE_ENVELOPE_KEYS

class TestNodesRoutes:
    def test_live_and_dated_both_sided_byte_identical(self, client, clock, monkeypatch): ... BASELINE["nodes_live"], BASELINE["nodes_dated"]
    def test_puts_only_nodes_unknown_with_null_totals(self, client, clock, monkeypatch):
        df = _chain_df(FIX_DATE, "REALTIME", tz="UTC"); _install_query_router(monkeypatch, realtime_df=df[df["option_type"] == "puts"])
        data = client.get("/api/options/SPY/nodes").json()
        assert data["regime"] == "unknown" and data["total_gex"] is None and data["total_vex"] is None and data["king"] is None and data["gates"] == [] and data["opex_nodes"] == []
    def test_unavailable_nodes_totals_are_null(self, client, monkeypatch):
        _install_query_router(monkeypatch); data = client.get("/api/options/RANDOM/nodes").json()
        assert data["total_gex"] is None and data["total_vex"] is None
```

- [ ] **Step 2: Run to verify failure**: `PYTHONPATH=platform python3 -m pytest tests/api/test_partial_chain_unavailable.py -k "Levels or Grid or Nodes" -v` → the two `unavailable…totals_are_null` tests FAIL (`0.0`); the partial-chain tests may already pass from Tasks 1, 2 and 4 (the lib and models carry them): record which.
- [ ] **Step 3: Implement** the three `None` edits in `grid.py`; add the `total_gex is None` assertions to the two existing envelope tests in `test_grid_router.py`.
- [ ] **Step 4: Run**: `PYTHONPATH=platform python3 -m pytest tests/api/ -q --ignore=tests/api/test_openapi_snapshot.py` → PASS.
- [ ] **Step 5: Commit**: `git commit -am "feat(grid): unavailable envelopes and partial chains carry null totals through levels, grid and nodes"`

---

### Task 8: Strict-prior snapshot selection in the feature builders (hermetic)

Spec: § Design 5; Review Focus 3. Advances done_when[1].

**Files:**
- Modify: `gcp/research/strat_engine/strat_data_builder.py` (new helper before `_add_context` L566; `_add_context` L577-591 and the VEX lines L612-616)
- Modify: `gcp/research/p7_build_multi_tf_features.py` (import; `_add_context` L386-400 and its VEX lines)
- Test: `tests/gcp/test_strat_data_builder_gamma.py`

**Interfaces:**
- Produces, in `strat_data_builder.py`: `prior_snapshot_context(levels: pd.DataFrame, bar_dates: pd.Series) -> pd.DataFrame`. `levels` is indexed by `snapshot_date` (as `_load_gamma_levels` returns it, one row per date); the result has one row per element of `bar_dates`, in order, with `levels`' columns holding the row of the latest `snapshot_date` strictly before that bar date, and NaN in every column when no such date exists. Implementation: `pd.merge_asof(left=bars sorted by date, right=levels.sort_index().reset_index(), left_on="bar_date", right_on="snapshot_date", direction="backward", allow_exact_matches=False)`, restored to the input order. A present marker date with NULL columns is selected like any other row (NaN context), so the lookup never reaches past it.
- Both `_add_context` bodies replace `prior_gamma`/`prior_vex` with `prior_snapshot_context(gamma_df, out["bar_date"])` and `prior_snapshot_context(vex_df, out["bar_date"])` (the latter only when `vex_df` is non-empty) and read the context columns from the result instead of the `bd.map(...)` dictionaries; every column name, the `fillna("unknown")` on `gamma_regime`, the distance formulas and the VIX join are unchanged. p7 imports the helper: `from gcp.research.strat_engine.strat_data_builder import prior_snapshot_context`.

- [ ] **Step 1: Write the failing tests**, parametrized over both builders like `test_research_featurize_tf_retains_legacy_valid_minute_features` (L197), with a shared `_levels(rows)` helper that builds `gamma_df` with the columns `total_gex`, `gamma_balance_price`, `gamma_flip`, `regime`, `spot`, `min_king_strike`, `min_gate_strike` indexed by `snapshot_date`, and bars `pd.DataFrame({"bar_date": [D, D], "close": [500.0, 501.0]})`, `vix_df` as in L96-100, `vex_df = pd.DataFrame()`, terciles `(1e7, 3e7), (4e6, 7e6)`. Dates: `D2 = date(2026, 10, 6)`, `D1 = date(2026, 10, 7)` (absent), `D = date(2026, 10, 8)`, `D3 = date(2026, 10, 9)`. D-2 row: `total_gex=1.5e7, gamma_balance_price=498.0, gamma_flip=NaN, regime="positive_gamma", min_king_strike=505.0, min_gate_strike=495.0`; D and D+1 rows carry distinct values (`2.5e7`, `600.0`, `610.0`, `"negative_gamma"`, `620.0`, `590.0`).

```python
@pytest.mark.parametrize("builder", ["p7", "strat"])
def test_strict_prior_with_bar_date_snapshot_present(builder): ...  # D present: context equals D-2's values, gamma_flip NaN, regime positive_gamma
@pytest.mark.parametrize("builder", ["p7", "strat"])
def test_strict_prior_with_bar_date_snapshot_absent(builder): ...   # D absent (the baseline failure): same assertions; FAILS on the shift-join
@pytest.mark.parametrize("builder", ["p7", "strat"])
def test_strict_prior_never_reads_same_day_or_later(builder): ...   # no value equals D's or D+1's distinct values; dist_to_gamma_flip_pct is NaN
@pytest.mark.parametrize("builder", ["p7", "strat"])
def test_marker_row_on_prior_day_blocks_older_snapshot(builder): ...  # D-1 row with every context column NaN: D's context is NaN, not D-2's
@pytest.mark.parametrize("builder", ["p7", "strat"])
def test_no_prior_snapshot_is_nan_never_zero(builder): ...          # only D and D+1 rows: total_gex NaN, gamma_regime "unknown", distance columns NaN
```

- [ ] **Step 2: Run to verify failure**: `python3 -m pytest tests/gcp/test_strat_data_builder_gamma.py -k strict_prior -v` → `..._absent` FAILS on both builders with `total_gex` NaN (reproduced on main 2026-11-14: D present → `1e9`, D absent → `nan`), `..._present` passes on both (the baseline behaviour), the marker test fails on `prior_gamma` keying.
- [ ] **Step 3: Implement** the helper and both `_add_context` edits.
- [ ] **Step 4: Run**: `python3 -m pytest tests/gcp/test_strat_data_builder_gamma.py -q` → PASS, including `test_dealer_regime_null_when_gex_missing`.
- [ ] **Step 5: Commit**: `git commit -am "fix(strat): gamma context comes from the latest snapshot strictly before the bar date"`

---

### Task 9: Strict-prior fixture in real PostgreSQL

Spec: § Design 5, § Verification ("the strict-prior fixture runs in the real-SQL harness"). Advances done_when[1].

**Files:**
- Create: `tests/integration/test_gamma_strict_prior_pg.py`

**Interfaces:**
- Consumes: `db_engine` from `tests/integration/conftest.py`; `p2_build_gamma_levels.CREATE_TABLE_SQL`; `strat_data_builder._load_gamma_levels(engine, ticker)` and `p7_build_multi_tf_features._load_gamma_levels(engine, ticker)`; both `_add_context`s.
- Fixture `gamma_levels(db_engine)`: executes `CREATE_TABLE_SQL`, `TRUNCATE gamma_levels_eod`, inserts the rows below, yields, truncates. Rows per date (one `king` row `level_strike=505`, one `gate` row `level_strike=495`): D-2 `(regime='positive_gamma', total_gex=1.5e7, gamma_balance_price=498.0, gamma_flip=NULL, spot_estimate=500.0)`; D `(regime='negative_gamma', total_gex=2.5e7, gamma_balance_price=600.0, gamma_flip=610.0, spot_estimate=601.0, strikes 620/590)`; D+1 likewise with `3.5e7`. Dates as in Task 8.

- [ ] **Step 1: Write the test**

```python
@pytest.mark.parametrize("module", ["strat", "p7"])
def test_features_on_d_select_d_minus_2_with_null_flip(gamma_levels, db_engine, module):
    mod = _module(module); gamma_df = mod._load_gamma_levels(db_engine, "SPY")
    out = mod._add_context(_bars_on(D), "SPY", _vix(), gamma_df, pd.DataFrame(), (1e7, 3e7), (4e6, 7e6))
    assert out["total_gex"].tolist() == [1.5e7, 1.5e7] and out["gamma_balance_price"].tolist() == [498.0, 498.0]
    assert out["gamma_flip"].isna().all() and out["dist_to_gamma_flip_pct"].isna().all()
    assert (out["gamma_regime"] == "positive_gamma").all()
    assert out["distance_to_king_pct"].iloc[0] == pytest.approx((500.0 - 505.0) / 500.0 * 100)

@pytest.mark.parametrize("module", ["strat", "p7"])
def test_features_on_d_without_a_d_snapshot_still_select_d_minus_2(gamma_levels, db_engine, module):
    with db_engine.begin() as conn: conn.execute(text("DELETE FROM gamma_levels_eod WHERE snapshot_date = :d"), {"d": D})
    ... same assertions ...

def test_missing_prior_is_null_never_zero(gamma_levels, db_engine):
    with db_engine.begin() as conn: conn.execute(text("DELETE FROM gamma_levels_eod WHERE snapshot_date < :d"), {"d": D})
    out = sdb._add_context(_bars_on(D), ...); assert out["total_gex"].isna().all() and (out["gamma_regime"] == "unknown").all()
```

- [ ] **Step 2: Run against a local Postgres when one is available** (`DB_HOST=localhost DB_NAME=trading DB_USER=trading_user DB_PASSWORD=… python3 -m pytest tests/integration/test_gamma_strict_prior_pg.py -v`); otherwise push and read the `Integration Tests (ephemeral Postgres)` job on the PR, which applies `gcp/schema.sql` and runs `tests/integration/` (`.github/workflows/backtest-pipeline.yml:90-163`). Expected: PASS on the branch; the `..._without_a_d_snapshot…` test is the one that fails on main's shift-join.
- [ ] **Step 3: Commit**: `git add tests/integration/test_gamma_strict_prior_pg.py && git commit -m "test(integration): strict-prior gamma context against real PostgreSQL"`

---

### Task 10: Regenerate the OpenAPI snapshot

Spec: § Design 6. Closes done_when[2].

**Files:**
- Modify: `platform/api/openapi.json` (generated only)

- [ ] **Step 1: Regenerate and diff**

```bash
python3 scripts/export_openapi.py
git diff --stat platform/api/openapi.json
git diff platform/api/openapi.json | grep -E '^[+-] +"(/api/|operationId)' ; echo "operations changed: $?"
```
Expected: changes only inside `components.schemas` for `OptionsChainMetadata` (`sides_present` required enum), `OptionsChainResponse` (`chain_state` required enum, `reason`), `OptionsMetrics` (three `anyOf` number/null), `GreeksResponse` (`reason`), `GammaLevelsResponse`, `GammaGridResponse`, `GammaNodesResponse` (nullable totals); no `paths` hunk; `grep` finds no operation line.
- [ ] **Step 2: Run**: `python3 -m pytest tests/api/test_openapi_snapshot.py -q` → PASS.
- [ ] **Step 3: Commit**: `git commit -am "chore(api): regenerate the OpenAPI snapshot for sides_present, chain_state and nullable gamma metrics"`; paste the component hunk list (schema name and changed properties) into the PR body under `done_when[2]`.

---

### Task 11: Declared SITE implementation-source notes and the sidecar

Spec: frontmatter `site_source_notes: [OPTIONS-01, OPTIONS-02, OPTIONS-05]`; product-delivery SKILL § Committed-source documentation identity. Advances done_when[3].

**Files:**
- Modify: `docs/product/03-SITE-TRACEABILITY.md` (`## Implementation-source notes` table at L1297: update the existing `| FEAT-OPTION-001 | OPTIONS-01 |` row, add `OPTIONS-02` and `OPTIONS-05` rows; no other byte)
- Modify: `docs/review-evidence/site-source-snapshot.json` (regenerated by the reserved tool only)

- [ ] **Step 1: Preflight for the source identity**

```bash
python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json
```
Expected: refuses to install (notes not yet eligible) and reports the current `source_identity_sha256`; copy it.
- [ ] **Step 2: Write the three rows**, each cell `source_identity_sha256=<hash>; ` followed by prose on backend source and local tests only (no deployed-availability claim): OPTIONS-01 (Swing: `/grid`, `/nodes`, `/levels` return unknown regime and null totals for a one-sided chain; the unavailable envelopes carry null totals; tests `tests/api/test_partial_chain_unavailable.py::TestGridRoutes/TestNodesRoutes/TestLevelsRoute`, `tests/lib/test_gamma.py::TestPartialChainIsUnavailable`), OPTIONS-02 (Trinity: `/levels` as above), OPTIONS-05 (Profiles: chain and live chain `metadata.sides_present` and `chain_state`, Greeks null metrics with a reason; `TestChainRoute`, `TestLiveChainRoute`, `TestGreeksRoute`). Keep the existing OPTIONS-01 text from #1743 and append this PR's sentence after it, so the row is updated, not replaced. Commit: `docs(site): FEAT-OPTION-001 implementation-source notes for the partial-chain contract`.
- [ ] **Step 3: Produce, commit and verify the sidecar**

```bash
python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json
git add docs/review-evidence/site-source-snapshot.json && git commit -m "docs(site): regenerate the committed-source identity record"
python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 8388608 --max-entries 20000
```
Expected: verify prints the matched-identity verdict (`implementation-source identity matched; external CODE review under existing rules; rollout pending`). If `origin/main`'s sidecar moves before merge (another lane's record), rebase and repeat this step; the record is reproduced, never hand-edited.

---

### Task 12: Close

Spec: § Done when, § Delivery and close-out. Closes done_when[3].

- [ ] Update the `### FEAT-OPTION-001` record in `docs/product/02-FEATURE-CATALOG.md` (L159-180): `Status` adds "Partial-chain unavailable contract ([spec](../superpowers/specs/2026-11-05-feat-option-001-partial-chain-unavailable-api.md)) implemented on `feature/feat-option-001-partial-chain-unavailable-api`; review, solyra consumer re-sync and API rollout pending"; `Last reviewed` → the commit date; `Evidence status` adds "Partial chains: lib, hermetic API and real-SQL strict-prior tests only; no deployment, stored-row or signed-in screen claim." No other row or record.
- [ ] Add this PR to `docs/product/12-PR-ISSUE-TRACEABILITY.md` under `### FEAT-OPTION-001` (L352-357) as a new **PR lineage** paragraph naming the spec and that it is the first half of the #1913 pair; no other FEAT's lines.
- [ ] Re-render the inventory blocks if `scripts/maintenance/doc_inventory.py` reports drift: `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-11-09.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md` and `python3 -m pytest tests/scripts/test_check_generated_docs.py -q`.
- [ ] `python3 scripts/maintenance/docs_audit.py` on the branch and on `origin/main`: no finding on the branch that main lacks.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` → `spec gate ok`.
- [ ] `make test` → PASS (the integration suite ran in CI in Task 9).
- [ ] Tick the four `done_when` boxes in the PR body with evidence beside each: [0] the test classes of Tasks 1 to 7 and the fixture file name; [1] `tests/gcp/test_strat_data_builder_gamma.py::test_strict_prior_*` and the Integration Tests job URL for `tests/integration/test_gamma_strict_prior_pg.py`; [2] the component hunk list and `tests/api/test_openapi_snapshot.py`; [3] the CI run, the docs-audit and gate outputs, and the records above. Mark the PR ready for review; post the Rule 2.5 receipts when each Codex row first reads Completed; two review rounds at most.
- [ ] After the merge, on `docs/feat-option-001-partial-chain-plan-closeout`: set this plan's `status: done` (nothing else).

## Self-review

- Spec coverage: Design 1 → Tasks 1, 2; Design 2 → Tasks 4, 5; Design 3 → Tasks 4, 6; Design 4 → Tasks 2, 4, 7; Design 5 → Tasks 8, 9; Design 6 → Task 10; Verification (baseline from main, direct and ASGI tests, real-SQL fixture) → Tasks 0, 5 to 9; Non-goals → Global Constraints; Capacity → section above; Delivery (serial on the contract files) → Baseline note and Task 10.
- Names used across tasks: `chain_sides`, `partial_chain_reason`, `partial_chain_warning`, `SIDES_BOTH`, `_chain_state_fields`, `prior_snapshot_context`, `_options_baseline_capture.capture`, fixture key names `chain`, `live_chain`, `greeks`, `levels`, `grid_live`, `grid_dated`, `nodes_live`, `nodes_dated`; reason strings `puts_missing`, `calls_missing`, `empty_chain`, `spot_unavailable`.
- Review Focus 1 to 5 each have a test in Tasks 5, 1/2, 8, 6, 3.
- Thirteen tasks (0 to 12), under the fifteen-task ceiling.
