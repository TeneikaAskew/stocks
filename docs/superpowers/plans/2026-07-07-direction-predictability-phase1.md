# Direction Predictability — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pure-prediction evaluation foundation — a slice ledger, a pre-registered success gate, a 3-axis (direction/size/type) walk-forward baseline runner that reuses the existing research engines, and a baseline chart — so later phases can add feature/target levers against a trustworthy, p-hacking-guarded harness.

**Architecture:** Reuse the existing purged/anchored walk-forward engines (`strat_dir_walk_forward.walk_forward_direction`, `mag_walk_forward`, `strat_walk_forward`). Add three small, focused modules: a slice ledger (persist one row per experiment slice), a success-gate function (encodes the pre-registered bar), and a baseline runner that orchestrates the three axes across IWM/SPY/QQQ and writes ledger rows. Chart via the already-merged `scripts/magnitude_result_charts.py`.

**Tech Stack:** Python, LightGBM, pandas, existing `gcp/research/` engines, pytest.

## Global Constraints

- **Pure prediction only** — no options/implied-vol/gate-7/cost/EV logic anywhere in this program.
- **Data boundary:** existing DB tables + features derived from raw 1-min `market_data_intraday`; **no new external data ingestion**.
- **Tickers:** IWM, SPY, QQQ. **Primary tf:** 5m.
- **Pre-registered success bar (verbatim):** a slice is PREDICTABLE iff it beats the base-rate constant (log-loss beat > 0) in **≥ 6 of 8 folds** AND replicates on **all three tickers**.
- **Leakage:** features strictly t-known (backward windows / shifts only); reuse the existing engines' fold-splitting; never reference next-bar or future 1-min bars in a feature.
- **New research code lives under** `gcp/research/direction_program/`; tests under `tests/`.
- Reuse existing engines; do not hand-roll a new walk-forward (Rule 3.6).

---

### Task 1: Success-gate function (the pre-registered bar)

**Files:**
- Create: `gcp/research/direction_program/__init__.py` (empty)
- Create: `gcp/research/direction_program/gate.py`
- Test: `tests/test_direction_gate.py`

**Interfaces:**
- Produces: `slice_passes_folds(fold_beats: list[float], min_folds: int = 6, total: int = 8) -> bool` — True iff ≥ min_folds of the fold `beat` values are > 0. `slice_predictable(per_ticker_beats: dict[str, list[float]], min_folds=6, total=8, tickers=("IWM","SPY","QQQ")) -> dict` — returns `{"predictable": bool, "per_ticker_pass": {tk: bool}, "n_tickers_pass": int}`; predictable True iff every required ticker's `slice_passes_folds` is True.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_direction_gate.py
from gcp.research.direction_program.gate import slice_passes_folds, slice_predictable

def test_passes_when_six_of_eight_beat():
    assert slice_passes_folds([0.1, 0.1, 0.1, 0.1, 0.1, 0.1, -0.1, -0.1]) is True

def test_fails_when_only_five_beat():
    assert slice_passes_folds([0.1]*5 + [-0.1]*3) is False

def test_predictable_requires_all_three_tickers():
    good = [0.1]*7 + [-0.1]
    bad = [0.1]*5 + [-0.1]*3
    r = slice_predictable({"IWM": good, "SPY": good, "QQQ": bad})
    assert r["predictable"] is False
    assert r["n_tickers_pass"] == 2
    r2 = slice_predictable({"IWM": good, "SPY": good, "QQQ": good})
    assert r2["predictable"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_direction_gate.py -q`
Expected: FAIL — `ModuleNotFoundError: gcp.research.direction_program.gate`

- [ ] **Step 3: Write minimal implementation**

```python
# gcp/research/direction_program/gate.py
"""Pre-registered success gate for the direction-predictability program.

A slice is PREDICTABLE iff it beats the base-rate constant (log-loss beat > 0)
in >= min_folds of `total` folds AND replicates on all required tickers.
"""
from __future__ import annotations


def slice_passes_folds(fold_beats, min_folds: int = 6, total: int = 8) -> bool:
    beats = [b for b in fold_beats if b is not None]
    return sum(1 for b in beats if b > 0) >= min_folds


def slice_predictable(per_ticker_beats, min_folds: int = 6, total: int = 8,
                      tickers=("IWM", "SPY", "QQQ")) -> dict:
    per = {tk: slice_passes_folds(per_ticker_beats.get(tk, []), min_folds, total)
           for tk in tickers}
    return {"predictable": all(per.values()),
            "per_ticker_pass": per,
            "n_tickers_pass": sum(per.values())}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_direction_gate.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add gcp/research/direction_program/__init__.py gcp/research/direction_program/gate.py tests/test_direction_gate.py
git commit -m "feat(direction): pre-registered success gate (>=6/8 folds, all 3 tickers)"
```

---

### Task 2: Slice ledger (the p-hacking guard)

**Files:**
- Create: `gcp/research/direction_program/slice_ledger.py`
- Test: `tests/test_slice_ledger.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `SliceLedger(path)` with `.record(slice_id: str, lever: str, target: str, conditioning: str, feature_set: str, ticker: str, fold_beats: list[float], meta: dict|None=None) -> None` (appends one JSONL row) and `.rows() -> list[dict]` (reads all rows back). Row schema keys: `slice_id, lever, target, conditioning, feature_set, ticker, fold_beats, n_folds_beat, meta`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_slice_ledger.py
from gcp.research.direction_program.slice_ledger import SliceLedger

def test_record_and_readback_roundtrip(tmp_path):
    p = tmp_path / "ledger.jsonl"
    led = SliceLedger(str(p))
    led.record("s1", lever="baseline", target="close_sign",
               conditioning="none", feature_set="strat248", ticker="IWM",
               fold_beats=[0.1, -0.1, 0.1, 0.1, 0.1, 0.1, 0.1, -0.1])
    led.record("s1", lever="baseline", target="close_sign",
               conditioning="none", feature_set="strat248", ticker="SPY",
               fold_beats=[0.1]*8)
    rows = led.rows()
    assert len(rows) == 2
    assert rows[0]["ticker"] == "IWM" and rows[0]["n_folds_beat"] == 6
    assert rows[1]["n_folds_beat"] == 8

def test_appends_across_instances(tmp_path):
    p = tmp_path / "ledger.jsonl"
    SliceLedger(str(p)).record("a", lever="l", target="t", conditioning="c",
                               feature_set="f", ticker="IWM", fold_beats=[0.1])
    SliceLedger(str(p)).record("b", lever="l", target="t", conditioning="c",
                               feature_set="f", ticker="SPY", fold_beats=[-0.1])
    assert len(SliceLedger(str(p)).rows()) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_slice_ledger.py -q`
Expected: FAIL — `ModuleNotFoundError: ...slice_ledger`

- [ ] **Step 3: Write minimal implementation**

```python
# gcp/research/direction_program/slice_ledger.py
"""Append-only JSONL ledger of every experiment slice tested, so the synthesis
step can apply a multiple-comparisons correction. One row per (slice, ticker)."""
from __future__ import annotations
import json
import os


class SliceLedger:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def record(self, slice_id, *, lever, target, conditioning, feature_set,
               ticker, fold_beats, meta=None) -> None:
        beats = [b for b in fold_beats if b is not None]
        row = {
            "slice_id": slice_id, "lever": lever, "target": target,
            "conditioning": conditioning, "feature_set": feature_set,
            "ticker": ticker, "fold_beats": list(fold_beats),
            "n_folds_beat": sum(1 for b in beats if b > 0),
            "meta": meta or {},
        }
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")

    def rows(self) -> list:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(ln) for ln in fh if ln.strip()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_slice_ledger.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add gcp/research/direction_program/slice_ledger.py tests/test_slice_ledger.py
git commit -m "feat(direction): append-only slice ledger for multiple-comparisons control"
```

---

### Task 3: 3-axis baseline runner (reuse existing engines)

**Files:**
- Create: `gcp/research/direction_program/baseline_runner.py`
- Test: `tests/test_baseline_runner.py`

**Interfaces:**
- Consumes: `SliceLedger` (Task 2), `slice_predictable` (Task 1); existing `gcp.research.strat_engine.strat_dir_walk_forward.walk_forward_direction(engine, ticker, tf, cutoffs=None) -> dict` (returns `{"folds": [ {"beat": float, ...}, ... ], ...}`).
- Produces: `extract_fold_beats(wf_result: dict) -> list[float]` (pull the per-fold `beat` values from a walk_forward result, skipping SKIP folds); `run_axis(engine, axis: str, ticker: str, tf: str, ledger: SliceLedger) -> list[float]` where `axis in {"direction","size","type"}` dispatches to the matching existing engine and records a ledger row; `run_baseline(engine, tf="5m", ledger_path=...) -> dict` runs all three axes × three tickers, returns `{axis: slice_predictable(...)}`.

**Note on reuse:** `walk_forward_direction` is the DIRECTION engine (close-sign — reproduces the 0/72 control). For SIZE use `gcp.research.magnitude_engine.mag_walk_forward.walk_forward` (per (ticker,tf), phase0), and for TYPE use `gcp.research.strat_engine.strat_walk_forward` — inspect each module's exact run function + returned fold key for "beat" during implementation and adapt `extract_fold_beats`/`run_axis` accordingly (all three return a folds list with a base-rate log-loss beat).

- [ ] **Step 1: Write the failing test** (unit-tests the pure helper; the full run is a documented smoke test, not a unit test, since it needs the DB)

```python
# tests/test_baseline_runner.py
from gcp.research.direction_program.baseline_runner import extract_fold_beats

def test_extract_fold_beats_skips_non_ok():
    wf = {"folds": [
        {"beat": 0.12, "status": "OK"},
        {"status": "SKIP_THIN"},          # no beat -> skipped
        {"beat": -0.03, "status": "OK"},
    ]}
    assert extract_fold_beats(wf) == [0.12, -0.03]

def test_extract_handles_empty():
    assert extract_fold_beats({"folds": []}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_baseline_runner.py -q`
Expected: FAIL — `ModuleNotFoundError: ...baseline_runner`

- [ ] **Step 3: Write minimal implementation**

```python
# gcp/research/direction_program/baseline_runner.py
"""Run direction/size/type through the existing walk-forward engines, pure
prediction, and record slice-ledger rows. The direction axis reproduces the
0/72 close-sign control as a harness-trust check."""
from __future__ import annotations
from gcp.research.direction_program.slice_ledger import SliceLedger
from gcp.research.direction_program.gate import slice_predictable

TICKERS = ("IWM", "SPY", "QQQ")


def extract_fold_beats(wf_result: dict) -> list:
    return [f["beat"] for f in wf_result.get("folds", []) if "beat" in f]


def _run_wf(engine, axis: str, ticker: str, tf: str) -> dict:
    if axis == "direction":
        from gcp.research.strat_engine.strat_dir_walk_forward import walk_forward_direction
        return walk_forward_direction(engine, ticker, tf)
    if axis == "size":
        from gcp.research.magnitude_engine.mag_walk_forward import walk_forward
        return walk_forward(engine, "phase0", ticker, tf)
    if axis == "type":
        from gcp.research.strat_engine.strat_walk_forward import walk_forward
        return walk_forward(engine, ticker, tf)
    raise ValueError(f"unknown axis {axis!r}")


def run_axis(engine, axis: str, ticker: str, tf: str, ledger: SliceLedger) -> list:
    wf = _run_wf(engine, axis, ticker, tf)
    beats = extract_fold_beats(wf)
    ledger.record(f"baseline:{axis}", lever="baseline", target=axis,
                  conditioning="none", feature_set="existing", ticker=ticker,
                  fold_beats=beats, meta={"tf": tf})
    return beats


def run_baseline(engine, tf: str = "5m",
                 ledger_path: str = "docs/research/direction_program_ledger.jsonl") -> dict:
    ledger = SliceLedger(ledger_path)
    out = {}
    for axis in ("direction", "size", "type"):
        per = {tk: run_axis(engine, axis, tk, tf, ledger) for tk in TICKERS}
        out[axis] = slice_predictable(per)
    return out
```

> Implementer note: adapt the `_run_wf` import names / call signatures to the actual functions in `mag_walk_forward.py` and `strat_walk_forward.py` (read them first; they may name the entry `run(...)` and take different args). Keep the `folds`→`beat` contract; if a module names the beat differently, normalize inside `extract_fold_beats`. Do NOT change the existing engines — only call them.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_baseline_runner.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Documented smoke run (manual, needs DB via IAM; not a unit test)**

Record in the task report (do not commit output): run `run_baseline` for tf=5m against Cloud SQL, confirm the DIRECTION axis fails the gate (reproduces the 0/72 control → predictable=False), and SIZE/TYPE behave as their docs say. This is the harness-trust check.

- [ ] **Step 6: Commit**

```bash
git add gcp/research/direction_program/baseline_runner.py tests/test_baseline_runner.py
git commit -m "feat(direction): 3-axis baseline runner reusing existing WF engines"
```

---

### Task 4: Baseline chart

**Files:**
- Create: `gcp/research/direction_program/chart_baseline.py`
- Test: `tests/test_chart_baseline.py`

**Interfaces:**
- Consumes: `scripts.magnitude_result_charts.small_multiples` (already in repo, PR #693); ledger rows (Task 2).
- Produces: `beats_to_panels(ledger_rows: list[dict]) -> dict` — shape ledger rows into `{ticker: {axis: [n_folds_beat, ...]}}`-style panels for charting (x = axis index or fold-beat count); `chart_baseline(ledger_path, out_path) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chart_baseline.py
import pytest
pytest.importorskip("matplotlib")
from gcp.research.direction_program.chart_baseline import beats_to_panels

def test_beats_to_panels_groups_by_ticker():
    rows = [
        {"ticker": "IWM", "target": "direction", "n_folds_beat": 1},
        {"ticker": "IWM", "target": "size", "n_folds_beat": 8},
        {"ticker": "SPY", "target": "direction", "n_folds_beat": 0},
    ]
    panels = beats_to_panels(rows)
    assert set(panels.keys()) == {"IWM", "SPY"}
    assert panels["IWM"]["direction"] == [1]
    assert panels["IWM"]["size"] == [8]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_chart_baseline.py -q`
Expected: FAIL — `ModuleNotFoundError: ...chart_baseline`

- [ ] **Step 3: Write minimal implementation**

```python
# gcp/research/direction_program/chart_baseline.py
"""Chart the 3-axis baseline (folds-beat per axis, per ticker) via the shared
small-multiples tool."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from scripts.magnitude_result_charts import small_multiples
from gcp.research.direction_program.slice_ledger import SliceLedger


def beats_to_panels(ledger_rows: list) -> dict:
    panels: dict = {}
    for r in ledger_rows:
        panels.setdefault(r["ticker"], {})[r["target"]] = [r["n_folds_beat"]]
    return panels


def chart_baseline(ledger_path: str, out_path: str) -> str:
    rows = SliceLedger(ledger_path).rows()
    panels = beats_to_panels(rows)
    axes = sorted({r["target"] for r in rows})
    return small_multiples(
        panels, axes, [0], out_path,
        title="Pure-prediction baseline — folds beating base rate (of 8)",
        subtitle="direction / size / type · purged walk-forward · pass bar = >=6/8 folds AND all 3 tickers",
        xlabel="", ylabel="folds beating base rate", pct=False, base_rate=6, ncols=3)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_chart_baseline.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add gcp/research/direction_program/chart_baseline.py tests/test_chart_baseline.py
git commit -m "feat(direction): 3-axis baseline chart via shared small-multiples tool"
```

---

## After Phase 1

Once the baseline runner reproduces the 0/72 direction control (harness trusted) and the baseline chart lands, the later phases get their own plans:
- **Phase 2** — feature levers ① (1-min microstructure builders + tests) and ③ (cross-asset lead-lag), re-measuring direction through this harness/ledger.
- **Phase 3** — target/conditioning levers ② (TYPE-conditioned/continuation) and ④ (one-sided/horizon/regime-gated).
- **Phase 4** — synthesis: multiple-comparisons correction over the ledger, ranked charts, and the honest verdict appended to `DIRECTION_RESEARCH_RESULTS.md`.

Each new feature builder ships with hermetic unit tests that assert t-known-ness (a next-bar reference must fail a test).

## Self-review notes

- Spec coverage: Part 1 (protocol/gate/ledger) → Tasks 1–2; Part 2 (3-axis baseline) → Task 3 + chart Task 4. Parts 3–4 deferred to their own plans (noted above) per the spec's phasing.
- No placeholders: every step has runnable code + exact commands. The one deferred detail (exact `mag_walk_forward`/`strat_walk_forward` entry signatures) is explicitly flagged as a read-first-then-adapt implementer note, with the normalization point (`extract_fold_beats`) named.
- Types consistent: `fold_beats: list[float]`, `beat` key, `slice_predictable`/`slice_passes_folds`, `SliceLedger.record/rows` used identically across tasks.
