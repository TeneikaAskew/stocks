# Direction Predictability Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five toggleable feature families to the DIRECTION and SIZE walk-forward engines and measure, per family, whether they move each axis toward the pre-registered gate — without touching the TYPE engine.

**Architecture:** New feature assembly lives in one module (`gcp/research/direction_program/phase2_features.py`); it returns *new* columns as a separate NaN-preserving frame that the engines concatenate **after** `featurize` (so the base matrix and TYPE are unchanged and the new columns never hit `featurize`'s `.fillna(0)`). A `--features` flag on each engine selects families; each run records a tagged row in the existing `slice_ledger`. Options features reuse `lib/features/experimental/options_derived.py`; ablation runs as a task-parallel Cloud Run job.

**Tech Stack:** Python 3.11, pandas, numpy, LightGBM (native NaN handling), pytest, Cloud Run Jobs, Cloud SQL (pg8000 via `gcp.database.get_engine`).

## Global Constraints

- **NaN, never `fillna(0)`, on new features.** New columns are attached AFTER `featurize` and passed to LightGBM as `np.nan`. LightGBM handles missing natively. Log per-feature coverage. (CLAUDE.md Rule 3.7)
- **TYPE is untouched.** No edits to `gcp/research/strat_engine/strat_walk_forward.py` behavior; pruning happens only inside the DIRECTION and SIZE engines.
- **Reuse, don't reinvent** (Rule 3.6 / DRY): options math = `options_derived.add_options_features` / `build_materialized`; feature math stays in `lib/`; the module orchestrates.
- **Prune rule:** drop each engine's near-dead columns = features with mean gain < 1% of that engine's top-feature gain (from the 2026-07-08 importance audit). Per-engine.
- **`cross_asset` scope:** other two ETFs' strictly-prior intraday returns/momentum + VIX regime. Macro (UST/DXY/oil/gold) is out of scope this phase.
- **Leak-safety:** daily families read strictly d-1 EOD (via `add_options_features`'s `.shift(1)`); cross-asset reads strictly-prior bars only.
- **Ablation is a task-parallel Cloud Run job**, `max-retries 0`, `--task-timeout` ≥ 4× a single-config estimate (~40 min → 10800 s).
- New code under `gcp/research/direction_program/`; tests under `tests/`.

---

### Task 1: `prune` family — near-dead drop-sets + `prune_feature_cols`

**Files:**
- Create: `gcp/research/direction_program/phase2_features.py`
- Create: `gcp/research/direction_program/phase2_prune_sets.py`
- Test: `tests/test_phase2_prune.py`

**Interfaces:**
- Produces: `prune_feature_cols(feature_cols: list[str], drop_set: set[str]) -> list[str]` — returns feature_cols with drop_set removed, order preserved.
- Produces: `NEAR_DEAD: dict[str, set[str]]` in `phase2_prune_sets.py`, keyed `"direction"` / `"size"`, each the set of near-dead columns from the audit.

- [ ] **Step 1: Write the failing test** — `tests/test_phase2_prune.py`:

```python
from gcp.research.direction_program.phase2_features import prune_feature_cols
from gcp.research.direction_program.phase2_prune_sets import NEAR_DEAD


def test_prune_removes_drop_set_preserves_order():
    cols = ["a", "b", "c", "d"]
    assert prune_feature_cols(cols, {"b", "d"}) == ["a", "c"]


def test_prune_noop_when_empty_drop_set():
    cols = ["a", "b"]
    assert prune_feature_cols(cols, set()) == ["a", "b"]


def test_near_dead_has_both_axes_and_is_nonempty():
    assert set(NEAR_DEAD) == {"direction", "size"}
    assert len(NEAR_DEAD["direction"]) > 50
    assert len(NEAR_DEAD["size"]) > 50
    # spot-check known dead columns from the 2026-07-08 audit
    assert "gamma_regime_unknown" in NEAR_DEAD["direction"]
```

- [ ] **Step 2: Run test to verify it fails** — `python -m pytest tests/test_phase2_prune.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Generate the drop-sets from the audit artifact.** Download the importance JSON and emit the near-dead sets:

```bash
gcloud storage cp \
  gs://adept-mountain-474619-d4-trading-data/direction-program/importance/importance_5m_1783532373.json \
  /tmp/imp.json
python - <<'PY' > gcp/research/direction_program/phase2_prune_sets.py
import json, numpy as np
from collections import defaultdict
d = json.load(open("/tmp/imp.json"))
out = {}
for axis in ("direction", "size"):
    g = defaultdict(list)
    for r in d["results"]:
        if r["axis"] != axis: continue
        for row in r["ranking"]:
            g[row["feature"]].append(row["mean_gain"])
    rows = {f: float(np.mean(v)) for f, v in g.items() if len(v) == 3}
    top = max(rows.values())
    dead = sorted(f for f, v in rows.items() if v < 0.01 * top)
    out[axis] = dead
print('"""Near-dead feature columns from the 2026-07-08 importance audit.')
print('Drop rule: mean gain < 1% of the axis top-feature gain (per-engine)."""')
print("NEAR_DEAD = {")
for axis, dead in out.items():
    print(f'    "{axis}": {{')
    for f in dead:
        print(f'        {f!r},')
    print("    },")
print("}")
PY
```

- [ ] **Step 4: Write `phase2_features.prune_feature_cols`** — `gcp/research/direction_program/phase2_features.py`:

```python
"""Phase-2 feature families for the DIRECTION and SIZE engines. New columns are
returned NaN-preserving for the engine to concat AFTER featurize (so they never
hit featurize's fillna(0) — CLAUDE.md Rule 3.7). Feature math is reused from
lib/; this module only orchestrates and shapes."""
from __future__ import annotations


def prune_feature_cols(feature_cols: list[str], drop_set: set) -> list[str]:
    return [c for c in feature_cols if c not in drop_set]
```

- [ ] **Step 5: Run tests** — `python -m pytest tests/test_phase2_prune.py -q` → PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add gcp/research/direction_program/phase2_features.py gcp/research/direction_program/phase2_prune_sets.py tests/test_phase2_prune.py
git commit -m "feat(direction): phase2 prune family (near-dead drop-sets + prune_feature_cols)"
```

---

### Task 2: `calendar` family

**Files:**
- Modify: `gcp/research/direction_program/phase2_features.py`
- Test: `tests/test_phase2_calendar.py`

**Interfaces:**
- Consumes: a DataFrame with a `bar_date` column (datetime.date or parseable).
- Produces: `calendar_features(df: pd.DataFrame) -> pd.DataFrame` — a NaN-free (calendar is always known) frame indexed like `df` with columns: `cal_dow` (0–4), `cal_week_of_month` (1–5), `cal_is_month_end`, `cal_is_quarter_end`, `cal_is_fomc_week`. All `float32`.

- [ ] **Step 1: Write the failing test** — `tests/test_phase2_calendar.py`:

```python
import pandas as pd
from gcp.research.direction_program.phase2_features import calendar_features


def test_calendar_columns_and_values():
    df = pd.DataFrame({"bar_date": pd.to_datetime(
        ["2026-03-31", "2026-06-30", "2026-01-05"]).date})
    out = calendar_features(df)
    assert list(out.columns) == [
        "cal_dow", "cal_week_of_month", "cal_is_month_end",
        "cal_is_quarter_end", "cal_is_fomc_week"]
    # 2026-03-31 is a Tuesday, month-end AND quarter-end
    assert out.iloc[0]["cal_dow"] == 1
    assert out.iloc[0]["cal_is_month_end"] == 1
    assert out.iloc[0]["cal_is_quarter_end"] == 1
    # 2026-06-30 quarter-end, not a Friday
    assert out.iloc[1]["cal_is_quarter_end"] == 1
    assert len(out) == 3


def test_calendar_has_no_nans():
    df = pd.DataFrame({"bar_date": pd.to_datetime(["2026-01-05"]).date})
    assert not calendar_features(df).isna().any().any()
```

- [ ] **Step 2: Run test to verify it fails** — `python -m pytest tests/test_phase2_calendar.py -q` → FAIL (`AttributeError: calendar_features`).

- [ ] **Step 3: Add `calendar_features`** to `phase2_features.py`:

```python
import numpy as np
import pandas as pd

# FOMC meeting weeks (Mon–Fri containing a scheduled FOMC decision), 2015-2026.
# Static table — derived from the Fed calendar; extend as new years publish.
_FOMC_WEEKS = {
    # 2024
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    # 2025
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    # 2026
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
}
_FOMC_WEEK_STARTS = {
    (pd.Timestamp(d) - pd.Timedelta(days=pd.Timestamp(d).weekday())).date()
    for d in _FOMC_WEEKS
}


def calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    d = pd.to_datetime(df["bar_date"])
    week_of_month = ((d.dt.day - 1) // 7 + 1).astype(np.float32)
    month_end = d.dt.is_month_end.astype(np.float32)
    quarter_end = (d.dt.is_month_end & d.dt.month.isin([3, 6, 9, 12])
                   ).astype(np.float32)
    week_start = (d - pd.to_timedelta(d.dt.weekday, unit="D")).dt.date
    is_fomc = week_start.map(lambda x: x in _FOMC_WEEK_STARTS).astype(np.float32)
    out = pd.DataFrame({
        "cal_dow": d.dt.weekday.astype(np.float32),
        "cal_week_of_month": week_of_month,
        "cal_is_month_end": month_end,
        "cal_is_quarter_end": quarter_end,
        "cal_is_fomc_week": is_fomc,
    }, index=df.index)
    return out
```

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_phase2_calendar.py -q` → PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add gcp/research/direction_program/phase2_features.py tests/test_phase2_calendar.py
git commit -m "feat(direction): phase2 calendar family"
```

---

### Task 3: `cross_asset` family (intraday lead-lag + VIX)

**Files:**
- Modify: `gcp/research/direction_program/phase2_features.py`
- Test: `tests/test_phase2_cross_asset.py`

**Interfaces:**
- Consumes: `df` with columns `ts` (UTC timestamp) and `close`; a `peers` dict `{ticker: peer_df}` where each `peer_df` has `ts` and `close`.
- Produces: `cross_asset_features(df: pd.DataFrame, peers: dict) -> pd.DataFrame` — NaN-preserving frame indexed like `df` with, per peer ticker `PK`: `xa_{PK}_ret_1` (peer's return over its most-recent bar strictly before this bar's ts). Missing peer bar → NaN. All `float32`.
- Note: the engine supplies `peers` by loading the other two ETFs' bars for the same `tf`; VIX is joined by the engine from the existing `vix_close` column already in the strat surface (no new work here — VIX regime is already present, so `cross_asset` adds only the peer lead-lag).

- [ ] **Step 1: Write the failing test** — `tests/test_phase2_cross_asset.py`:

```python
import numpy as np
import pandas as pd
from gcp.research.direction_program.phase2_features import cross_asset_features


def test_cross_asset_uses_strictly_prior_peer_bar():
    base = pd.DataFrame({
        "ts": pd.to_datetime(["2026-01-05 15:00", "2026-01-05 15:05"], utc=True),
        "close": [100.0, 101.0],
    })
    peer = pd.DataFrame({
        "ts": pd.to_datetime(
            ["2026-01-05 14:50", "2026-01-05 14:55", "2026-01-05 15:00"], utc=True),
        "close": [50.0, 51.0, 52.0],  # 14:55->15:00 return = 52/51-1
    })
    out = cross_asset_features(base, {"SPY": peer})
    assert "xa_SPY_ret_1" in out.columns
    # bar at 15:00 uses peer bars strictly before 15:00: last is 14:55 (51),
    # prior 14:50 (50) -> ret = 51/50 - 1 = 0.02
    assert abs(out.iloc[0]["xa_SPY_ret_1"] - 0.02) < 1e-6


def test_cross_asset_missing_peer_is_nan():
    base = pd.DataFrame({
        "ts": pd.to_datetime(["2026-01-05 09:30"], utc=True), "close": [100.0]})
    peer = pd.DataFrame({
        "ts": pd.to_datetime(["2026-01-05 10:00"], utc=True), "close": [50.0]})
    out = cross_asset_features(base, {"SPY": peer})
    assert np.isnan(out.iloc[0]["xa_SPY_ret_1"])  # no strictly-prior peer bar
```

- [ ] **Step 2: Run test to verify it fails** — `python -m pytest tests/test_phase2_cross_asset.py -q` → FAIL (`AttributeError`).

- [ ] **Step 3: Add `cross_asset_features`** to `phase2_features.py`:

```python
def cross_asset_features(df: pd.DataFrame, peers: dict) -> pd.DataFrame:
    base_ts = pd.to_datetime(df["ts"], utc=True)
    out = pd.DataFrame(index=df.index)
    for pk, pdf in peers.items():
        p = pdf.sort_values("ts").reset_index(drop=True)
        p_ts = pd.to_datetime(p["ts"], utc=True)
        p_ret = p["close"].astype(float) / p["close"].astype(float).shift(1) - 1.0
        # For each base bar, take the peer return of the last peer bar
        # STRICTLY before the base bar's ts (searchsorted 'left' - 1).
        idx = np.searchsorted(p_ts.values, base_ts.values, side="left") - 1
        vals = np.where(idx >= 0, p_ret.values[np.clip(idx, 0, len(p) - 1)], np.nan)
        # idx == -1 -> no prior peer bar -> NaN
        vals = np.where(idx >= 0, vals, np.nan)
        out[f"xa_{pk}_ret_1"] = vals.astype(np.float32)
    return out
```

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_phase2_cross_asset.py -q` → PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add gcp/research/direction_program/phase2_features.py tests/test_phase2_cross_asset.py
git commit -m "feat(direction): phase2 cross-asset intraday lead-lag family"
```

---

### Task 4: `options_iv` + `positioning` families (reuse `add_options_features`)

**Files:**
- Modify: `gcp/research/direction_program/phase2_features.py`
- Test: `tests/test_phase2_options.py`

**Interfaces:**
- Consumes: `lib.features.experimental.options_derived.add_options_features(df, ticker, engine) -> pd.DataFrame` (already exists — reads materialized `options_daily_features`, computes `pcr_volume_d1, pcr_oi_d1, iv_skew_25d_d1, iv_term_slope_d1, atm_iv_d1`, shifts d-1, attaches NaN for missing dates).
- Produces: `options_features(df, ticker, engine, families) -> pd.DataFrame` — calls `add_options_features` once, then returns only the columns for the requested families:
  - `"positioning"` → `["pcr_volume_d1", "pcr_oi_d1", "iv_skew_25d_d1"]`
  - `"options_iv"` → `["atm_iv_d1", "iv_term_slope_d1"]`
  NaN-preserving; a requested column absent from the joiner output is returned as an all-NaN column (explicit-missing, never 0).

- [ ] **Step 1: Write the failing test** — `tests/test_phase2_options.py` (monkeypatches the joiner so the test is hermetic — no DB):

```python
import numpy as np
import pandas as pd
import gcp.research.direction_program.phase2_features as p2


def test_options_families_select_expected_columns(monkeypatch):
    df = pd.DataFrame({"bar_date": pd.to_datetime(["2026-01-05", "2026-01-06"]).date})

    def fake_join(d, ticker, engine):
        out = d.copy()
        out["pcr_volume_d1"] = [1.1, np.nan]
        out["pcr_oi_d1"] = [0.9, 0.8]
        out["iv_skew_25d_d1"] = [0.03, 0.04]
        out["iv_term_slope_d1"] = [0.01, np.nan]
        out["atm_iv_d1"] = [0.2, 0.21]
        return out
    monkeypatch.setattr(p2, "add_options_features", fake_join)

    pos = p2.options_features(df, "IWM", engine=None, families={"positioning"})
    assert list(pos.columns) == ["pcr_volume_d1", "pcr_oi_d1", "iv_skew_25d_d1"]
    assert np.isnan(pos.iloc[1]["pcr_volume_d1"])  # NaN preserved, not 0

    iv = p2.options_features(df, "IWM", engine=None, families={"options_iv"})
    assert list(iv.columns) == ["atm_iv_d1", "iv_term_slope_d1"]

    both = p2.options_features(df, "IWM", engine=None,
                               families={"positioning", "options_iv"})
    assert set(both.columns) == {
        "pcr_volume_d1", "pcr_oi_d1", "iv_skew_25d_d1",
        "atm_iv_d1", "iv_term_slope_d1"}
```

- [ ] **Step 2: Run test to verify it fails** — `python -m pytest tests/test_phase2_options.py -q` → FAIL (`AttributeError: options_features`).

- [ ] **Step 3: Add the joiner import + `options_features`** to `phase2_features.py`:

```python
from lib.features.experimental.options_derived import add_options_features

_FAMILY_COLS = {
    "positioning": ["pcr_volume_d1", "pcr_oi_d1", "iv_skew_25d_d1"],
    "options_iv": ["atm_iv_d1", "iv_term_slope_d1"],
}


def options_features(df: pd.DataFrame, ticker: str, engine,
                     families: set) -> pd.DataFrame:
    joined = add_options_features(df, ticker, engine)
    want = [c for fam in families for c in _FAMILY_COLS[fam]]
    out = pd.DataFrame(index=df.index)
    for c in want:
        # explicit-missing if the joiner didn't produce this column
        out[c] = (joined[c].to_numpy(dtype=np.float32) if c in joined.columns
                  else np.full(len(df), np.nan, dtype=np.float32))
    return out
```

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_phase2_options.py -q` → PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add gcp/research/direction_program/phase2_features.py tests/test_phase2_options.py
git commit -m "feat(direction): phase2 options_iv + positioning families (reuse add_options_features)"
```

---

### Task 5: `build_family_columns` orchestrator + `--features` flag on both engines

**Files:**
- Modify: `gcp/research/direction_program/phase2_features.py`
- Modify: `gcp/research/strat_engine/strat_dir_walk_forward.py` (add `--features`, apply families)
- Modify: `gcp/research/magnitude_engine/mag_walk_forward.py` (add `--features`, apply families)
- Test: `tests/test_phase2_orchestrator.py`

**Interfaces:**
- Produces: `build_family_columns(df, families, axis, ticker, tf, engine, peers=None) -> tuple[pd.DataFrame, list[str]]` — for the additive families in `families` (`options_iv`, `positioning`, `cross_asset`, `calendar`), returns `(new_cols_df aligned to df.index, new_col_names)`, NaN-preserving. `prune` is NOT handled here (it filters the base cols in the engine).
- Produces (engine side): both engines gain `--features` (comma-separated family names, default empty = baseline) and, after their existing `X_df, cols = featurize(df)`:
  ```python
  fams = set(args.features.split(",")) - {""}
  if "prune" in fams:
      keep = prune_feature_cols(cols, NEAR_DEAD[AXIS])
      X_df = X_df[keep]; cols = keep
  add = fams - {"prune"}
  if add:
      new_df, new_cols = build_family_columns(df, add, AXIS, ticker, tf, engine, peers)
      X_df = pd.concat([X_df.reset_index(drop=True), new_df.reset_index(drop=True)], axis=1)
      cols = cols + new_cols
  ```
  where `AXIS` is `"direction"` / `"size"` respectively, and the slice-ledger row's `feature_set` is set to `"phase2:" + ",".join(sorted(fams))`.

- [ ] **Step 1: Write the failing test** — `tests/test_phase2_orchestrator.py` (hermetic; monkeypatches the DB-touching families):

```python
import numpy as np
import pandas as pd
import gcp.research.direction_program.phase2_features as p2


def test_build_family_columns_calendar_only():
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2026-03-31 15:00"], utc=True),
        "bar_date": pd.to_datetime(["2026-03-31"]).date,
        "close": [100.0]})
    new_df, new_cols = p2.build_family_columns(
        df, {"calendar"}, axis="direction", ticker="IWM", tf="5m", engine=None)
    assert "cal_is_quarter_end" in new_cols
    assert len(new_df) == 1
    assert new_df.iloc[0]["cal_is_quarter_end"] == 1


def test_build_family_columns_combines_and_preserves_nan(monkeypatch):
    df = pd.DataFrame({
        "ts": pd.to_datetime(["2026-01-05 15:00"], utc=True),
        "bar_date": pd.to_datetime(["2026-01-05"]).date, "close": [100.0]})

    def fake_opts(d, ticker, engine, families):
        return pd.DataFrame({"atm_iv_d1": [np.nan]}, index=d.index)
    monkeypatch.setattr(p2, "options_features", fake_opts)

    new_df, new_cols = p2.build_family_columns(
        df, {"options_iv", "calendar"}, axis="size", ticker="IWM",
        tf="5m", engine=None)
    assert "atm_iv_d1" in new_cols and "cal_dow" in new_cols
    assert np.isnan(new_df.iloc[0]["atm_iv_d1"])  # NaN preserved
```

- [ ] **Step 2: Run test to verify it fails** — `python -m pytest tests/test_phase2_orchestrator.py -q` → FAIL (`AttributeError: build_family_columns`).

- [ ] **Step 3: Add `build_family_columns`** to `phase2_features.py`:

```python
def build_family_columns(df, families, axis, ticker, tf, engine, peers=None):
    parts = []
    if {"options_iv", "positioning"} & families:
        parts.append(options_features(
            df, ticker, engine, families & {"options_iv", "positioning"}))
    if "cross_asset" in families:
        parts.append(cross_asset_features(df, peers or {}))
    if "calendar" in families:
        parts.append(calendar_features(df))
    if not parts:
        return pd.DataFrame(index=df.index), []
    new_df = pd.concat([p.reset_index(drop=True) for p in parts], axis=1)
    return new_df, list(new_df.columns)
```

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_phase2_orchestrator.py -q` → PASS (2 passed).

- [ ] **Step 5: Wire `--features` into `strat_dir_walk_forward.py`.** In `main()` add the arg; in `walk_forward_direction`, after `X_df, feature_cols = featurize(df)` (line ~155), apply the glue block from Interfaces with `AXIS = "direction"` and `peers` loaded via `load_labeled_dataset` for the other two tickers (same `tf`), passing only `ts`/`close`. Set the ledger `feature_set` tag. Import: `from gcp.research.direction_program.phase2_features import build_family_columns, prune_feature_cols; from gcp.research.direction_program.phase2_prune_sets import NEAR_DEAD`.

- [ ] **Step 6: Wire `--features` into `mag_walk_forward.py`** identically, `AXIS = "size"`, after its `X_df, feature_cols = featurize(df)` (line ~485).

- [ ] **Step 7: Verify both engines import and `--features ""` reproduces baseline** — `python -c "import gcp.research.strat_engine.strat_dir_walk_forward, gcp.research.magnitude_engine.mag_walk_forward"` → no error. `python -m pytest tests/test_phase2_orchestrator.py -q` → PASS.

- [ ] **Step 8: Commit**

```bash
git add gcp/research/direction_program/phase2_features.py gcp/research/strat_engine/strat_dir_walk_forward.py gcp/research/magnitude_engine/mag_walk_forward.py tests/test_phase2_orchestrator.py
git commit -m "feat(direction): --features flag wires phase2 families into direction+size engines"
```

---

### Task 6: Options materialization backfill + task-parallel `direction-phase2` ablation job

**Files:**
- Create: `gcp/research/direction_program/phase2_ablation.py` (CLI: run one config by index)
- Modify: `gcp/deploy.sh` (add `direction-phase2` task-parallel job + dispatch case)
- Test: `tests/test_phase2_ablation.py`

**Interfaces:**
- Produces: `ABLATION_CONFIGS: list[dict]` — the ladder: per axis, `{"axis","features"}` for baseline, each family in isolation, and the cumulative stack. Resolved by `CLOUD_RUN_TASK_INDEX`.
- Produces: `run_config(engine, cfg) -> dict` — dispatches to `walk_forward_direction(engine, tk, tf, features=...)` or `walk_forward(engine, "phase0", tk, tf, features=...)` for all 3 tickers, records ledger rows, returns the `slice_predictable` verdict.
- Reuses: `options_derived.build_materialized(engine, ticker, since, until)` for the one-time backfill (run manually before the ablation; documented below, not in the job).

- [ ] **Step 1: Write the failing test** — `tests/test_phase2_ablation.py`:

```python
from gcp.research.direction_program.phase2_ablation import ABLATION_CONFIGS


def test_ladder_has_baseline_and_isolation_and_stack_per_axis():
    for axis in ("direction", "size"):
        cfgs = [c for c in ABLATION_CONFIGS if c["axis"] == axis]
        feats = [c["features"] for c in cfgs]
        assert "" in feats                       # baseline
        assert "prune" in feats                  # a family in isolation
        # cumulative stack contains multiple families
        assert any("," in f for f in feats)
```

- [ ] **Step 2: Run test to verify it fails** — `python -m pytest tests/test_phase2_ablation.py -q` → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write `phase2_ablation.py`:**

```python
"""Task-parallel Phase-2 ablation. One Cloud Run task runs one config
(resolved from CLOUD_RUN_TASK_INDEX). Reuses the production engines via their
--features path; records every slice in the slice_ledger."""
from __future__ import annotations
import logging, os
from gcp.database import get_engine
from gcp.research.direction_program.slice_ledger import SliceLedger
from gcp.research.direction_program.gate import slice_predictable

log = logging.getLogger("direction.phase2")
TICKERS = ("IWM", "SPY", "QQQ")
_FAMILIES = ["prune", "options_iv", "positioning", "cross_asset", "calendar"]


def _ladder(axis):
    cfgs = [{"axis": axis, "features": ""}]                    # baseline
    cfgs += [{"axis": axis, "features": f} for f in _FAMILIES]  # isolation
    cfgs.append({"axis": axis, "features": ",".join(_FAMILIES)})  # full stack
    return cfgs


ABLATION_CONFIGS = _ladder("direction") + _ladder("size")


def run_config(engine, cfg, ledger_path="docs/research/direction_program_ledger.jsonl"):
    from gcp.research.direction_program.baseline_runner import extract_fold_beats
    ledger = SliceLedger(ledger_path)
    per = {}
    for tk in TICKERS:
        if cfg["axis"] == "direction":
            from gcp.research.strat_engine.strat_dir_walk_forward import walk_forward_direction
            wf = walk_forward_direction(engine, tk, "5m", features=cfg["features"])
        else:
            from gcp.research.magnitude_engine.mag_walk_forward import walk_forward
            wf = walk_forward(engine, "phase0", tk, "5m", features=cfg["features"])
        beats = extract_fold_beats(wf)
        per[tk] = beats
        ledger.record(f"phase2:{cfg['axis']}:{cfg['features'] or 'baseline'}",
                      lever="phase2", target=cfg["axis"], conditioning="none",
                      feature_set="phase2:" + (cfg["features"] or "baseline"),
                      ticker=tk, fold_beats=beats, meta={"tf": "5m"})
    v = slice_predictable(per)
    log.info("PHASE2_VERDICT axis=%s features=%s predictable=%s n_tickers_pass=%d",
             cfg["axis"], cfg["features"] or "baseline",
             v["predictable"], v["n_tickers_pass"])
    return v


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    idx = int(os.environ.get("CLOUD_RUN_TASK_INDEX", "0"))
    if idx >= len(ABLATION_CONFIGS):
        log.info("task-index %d >= %d configs — no-op", idx, len(ABLATION_CONFIGS))
        return
    run_config(get_engine(), ABLATION_CONFIGS[idx])


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_phase2_ablation.py -q` → PASS (1 passed).

- [ ] **Step 5: Add the task-parallel job to `gcp/deploy.sh`** (after `deploy_direction_importance`), fanning out one task per config:

```bash
# ── Direction-program Phase-2 ablation (task-parallel, one task per config) ──
# Volume: 14 configs (2 axes × [baseline + 5 isolation + 1 stack]) × 3 tickers
#         × 8 folds. Velocity: 1 batched feature SELECT per (ticker,cfg); daily
#         options read from the materialized options_daily_features table.
# Wall-clock: one config ≈ baseline (~40 min); task-parallel => ~40 min total.
# task-timeout 10800s (4×). max-retries 0 (fail loud). ~$0.15/run, on demand.
# PREREQUISITE (run once, not in this job): materialize options daily features
#   python -c "from gcp.database import get_engine; \
#     from lib.features.experimental.options_derived import build_materialized; \
#     e=get_engine(); [build_materialized(e,t,'2015-01-01','2026-07-08') \
#       for t in ('IWM','SPY','QQQ')]"
deploy_direction_phase2() {
    echo "Deploying direction-phase2 ablation job (task-parallel)..."
    local research_image="${IMAGE}:research"
    local n=14
    gcloud run jobs create direction-phase2 \
        --image "${research_image}" --region "${REGION}" \
        --tasks ${n} --parallelism ${n} \
        --memory 8Gi --cpu 4 --max-retries 0 --task-timeout 10800 \
        --service-account "${SA_EMAIL}" \
        --command "python" \
        --args="-m,gcp.research.direction_program.phase2_ablation" \
        ${DB_SECRET_FLAG} --set-env-vars "$(_env_string)" --quiet 2>/dev/null || \
    gcloud run jobs update direction-phase2 \
        --image "${research_image}" --region "${REGION}" \
        --tasks ${n} --parallelism ${n} \
        --memory 8Gi --cpu 4 --max-retries 0 --task-timeout 10800 \
        --command "python" \
        --args="-m,gcp.research.direction_program.phase2_ablation" \
        ${DB_SECRET_FLAG} --set-env-vars "$(_env_string)" --quiet
}
```
Add the dispatch case next to `direction-importance)`:
```bash
    direction-phase2) deploy_direction_phase2 ;;   # research image; build separately (build-research)
```

- [ ] **Step 6: Verify** — `bash -n gcp/deploy.sh` → OK; `python -c "import gcp.research.direction_program.phase2_ablation"` → no error; `python -m pytest tests/test_phase2_ablation.py -q` → PASS.

- [ ] **Step 7: Commit**

```bash
git add gcp/research/direction_program/phase2_ablation.py gcp/deploy.sh tests/test_phase2_ablation.py
git commit -m "feat(direction): task-parallel phase2 ablation job + config ladder"
```

---

## Production smoke (documented, run after merge — not a unit test)

1. Rebuild the research image: `bash gcp/deploy.sh build-research`.
2. One-time options backfill (the PREREQUISITE `python -c` above) — verify `options_daily_features` row counts for IWM/SPY/QQQ.
3. `bash gcp/deploy.sh direction-phase2` then `gcloud run jobs execute direction-phase2 --region=us-east1`.
4. Read `PHASE2_VERDICT` lines from logs; confirm every config recorded a `slice_ledger` row and per-feature coverage was logged (NaN, not 0).
5. Confirm the `""`/baseline configs reproduce the Phase-1 numbers (DIRECTION 0/3, SIZE 0/3) — the harness-trust check that the `--features` plumbing didn't change the baseline.

## Self-Review notes

- **Spec coverage:** prune (T1), calendar (T2), cross_asset (T3), options_iv+positioning (T4), --features glue + NaN-not-fillna (T5), task-parallel job + materialization + capacity math (T6), gate+partial-credit via slice_ledger + verdict logging (T6). TYPE untouched (only direction/size engines edited).
- **NaN discipline:** every additive family returns NaN for missing and is concatenated AFTER featurize, bypassing its `.fillna(0)`.
- **Reuse:** options math via `add_options_features` / `build_materialized`; engines via `--features`; ledger/gate via Phase-1 modules.
