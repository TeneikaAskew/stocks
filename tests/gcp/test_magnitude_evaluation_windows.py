from datetime import date

import pandas as pd
import pytest

from gcp.research.magnitude_engine.evaluation_windows import (
    EASTERN, WINDOWS, assert_disjoint, assert_window_complete,
    eastern_sessions, purged_session_masks,
)


def test_windows_are_immutable_non_overlapping_and_eastern():
    ordered = list(WINDOWS.values())
    assert ordered[0].end <= ordered[1].start
    assert ordered[1].end <= ordered[2].start
    assert ordered[2].final
    assert ordered[0].start_eastern.tzinfo == EASTERN
    with pytest.raises(Exception):
        ordered[0].start = date(2020, 1, 1)


def test_sessions_are_eastern_and_embargo_whole_session():
    timestamps = pd.to_datetime([
        "2025-01-02T14:30:00Z", "2025-01-02T20:00:00Z",
        "2025-01-03T15:00:00Z", "2025-01-06T15:00:00Z",
    ])
    sessions = eastern_sessions(timestamps)
    train, test = purged_session_masks(
        sessions, "2025-01-06", "2025-01-07", embargo_sessions=1)
    assert train.tolist() == [True, True, False, False]
    assert test.tolist() == [False, False, False, True]


def test_rejects_overlap_and_short_embargo():
    sessions = pd.to_datetime(["2025-01-02", "2025-01-03"])
    with pytest.raises(ValueError, match="overlap"):
        assert_disjoint(sessions, sessions[-1:])
    with pytest.raises(ValueError, match="prediction horizon"):
        purged_session_masks(sessions, "2025-01-03", "2025-01-04", 0)


def test_final_window_cannot_run_until_it_is_complete():
    with pytest.raises(ValueError, match="incomplete"):
        assert_window_complete(WINDOWS["final_test"], date(2026, 9, 27))
    assert_window_complete(WINDOWS["final_test"], date(2027, 1, 1))


def test_gate_threshold_scales_from_six_of_eight_to_window_fold_count():
    from gcp.research.magnitude_engine.mag_walk_forward import _evaluate_phase_gate

    passing = {
        "status": "OK", "beat": 0.1, "ece_pass": True,
        "explosive": {"lift": 2.0},
        "decisive_hit": {
            "0.40": {"accuracy": 0.5}, "0.50": {"accuracy": 0.6},
            "0.60": {"accuracy": 0.7}, "0.70": {"accuracy": 0.8},
        },
    }
    gates = _evaluate_phase_gate([passing.copy(), passing.copy()], "5m")
    assert gates["min_folds_required"] == 2
    assert gates["cell_pass_gates_1_to_4"] is True


# ═══════════════ Codex review of #1193 (bd944c5) ═══════════════
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

REPO = Path(__file__).resolve().parents[2]


def _fold(ok: bool = True, *, beat: float = 0.01, ece_pass: bool = True,
          lift: float = 2.0, mono: bool = True) -> dict:
    accs = [0.5, 0.6, 0.7, 0.8] if mono else [0.8, 0.5, 0.6, 0.4]
    return {"status": "OK" if ok else "SKIP_THIN", "beat": beat,
            "ece_pass": ece_pass, "explosive": {"lift": lift},
            "decisive_hit": {f"{t:.2f}": {"accuracy": a}
                             for t, a in zip((0.40, 0.50, 0.60, 0.70), accs)}}


_FAILING = _fold(beat=-0.01, ece_pass=False, lift=1.0, mono=False)


# ── P1: gates must be attainable in every window ──────────────────────────

def test_the_six_of_eight_bar_scales_to_the_folds_a_window_holds():
    """Development holds five yearly folds, validation two, final_test one.
    A fixed 6-fold requirement made every default run FAIL and left
    --persist-production-model unable to promote anything (Codex P1)."""
    from gcp.research.magnitude_engine.mag_config import min_folds_required
    assert [min_folds_required(n) for n in (8, 5, 2, 1)] == [6, 4, 2, 1]
    with pytest.raises(ValueError):
        min_folds_required(0)


def test_gates_use_the_scaled_bar_and_report_it():
    from gcp.research.magnitude_engine.mag_walk_forward import _evaluate_phase_gate
    g = _evaluate_phase_gate([_fold()] * 4 + [_FAILING], "15m")
    assert (g["n_folds"], g["min_folds_required"]) == (5, 4)
    assert g["cell_pass_gates_1_to_4"] is True
    assert _evaluate_phase_gate([_fold()] * 3 + [_FAILING] * 2, "15m")[
        "cell_pass_gates_1_to_4"] is False
    # the historical eight-fold bar is unchanged
    assert _evaluate_phase_gate([_fold()] * 6 + [_FAILING] * 2, "15m")[
        "cell_pass_gates_1_to_4"] is True
    assert _evaluate_phase_gate([_fold()] * 5 + [_FAILING] * 3, "15m")[
        "cell_pass_gates_1_to_4"] is False
    # a thin fold still counts toward the bar it cannot help pass
    assert _evaluate_phase_gate([_fold()] * 3 + [_fold(ok=False)] * 2, "15m")[
        "cell_pass_gates_1_to_4"] is False


def test_the_bootstrap_applies_the_same_scaled_bar():
    import scripts.bootstrap_gate_fragility as bs
    from gcp.research.magnitude_engine.mag_config import min_folds_required
    rng = np.random.default_rng(3)
    rows = []
    for fold in ("a", "b"):
        y = rng.choice(4, size=120, p=[0.64, 0.27, 0.07, 0.02])
        proba = np.tile([0.64, 0.27, 0.07, 0.02], (120, 1))
        rows.append(pd.DataFrame({
            "fold": fold, "ts": "2025-01-02T15:00:00Z", "true_bucket_idx": y,
            "pred_bucket_idx": 0, "max_proba": 0.64,
            "p_TIGHT": proba[:, 0], "p_NORMAL": proba[:, 1],
            "p_EXPANDED": proba[:, 2], "p_EXPLOSIVE": proba[:, 3]}))
    r = bs.bootstrap_one_cell(pd.concat(rows, ignore_index=True), "5m", n_iter=3)
    assert r["n_folds"] == 2
    assert r["min_folds_required"] == min_folds_required(2) == 2
    for key in ("p_below_bar", "p_at_bar", "p_above_bar"):
        assert len(r[key]) == 4


# ── P1: the dataset load stops at the selected window ─────────────────────

class _Stop(Exception):
    pass


def _stop(*a, **kw):
    raise _Stop


def test_the_dataset_load_stops_at_the_window_end(monkeypatch):
    """Development and validation runs loaded the whole table, so the
    final-test rows were labelled, class-balanced and fingerprinted during
    configuration work without consuming the final-test marker (Codex P1)."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    seen: dict = {}

    def fake_load(engine, ticker, tf, phase, **kw):
        seen.update(kw)
        raise _Stop

    monkeypatch.setattr(mwf, "load_magnitude_dataset", fake_load)
    for window, end in (("development", "2024-01-01"),
                        ("validation", "2026-01-01")):
        seen.clear()
        with pytest.raises(_Stop):
            mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m",
                             evaluation_window=window)
        assert seen["until"] == end, window


_FINAL_SESSIONS = [date(2026, 1, 2), date(2026, 6, 30), date(2026, 12, 31)]


def _complete_window(monkeypatch, mwf, missing=(), short=(), extra=()):
    """Stub the unlabelled preflight: the calendar expects 78 bars on each of
    _FINAL_SESSIONS; the table holds them all unless `missing`, `short`
    (count 9) or `extra` (a non-session date) say otherwise."""
    expected = {d: 78 for d in _FINAL_SESSIONS}
    observed = {d: (9 if d in short else 78) for d in _FINAL_SESSIONS if d not in missing}
    for d in extra:
        observed[d] = 78
    monkeypatch.setattr(mwf, "expected_session_bars", lambda *a, **k: dict(expected))
    monkeypatch.setattr(mwf, "_session_bar_counts", lambda *a, **k: dict(observed))


# ── P1: the final test cannot be claimed on a partial window ──────────────

def test_the_final_test_is_refused_until_its_window_has_closed(monkeypatch):
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    claimed: list = []
    monkeypatch.setattr(mwf, "_claim_final_test",
                        lambda *a, **k: claimed.append(a))
    monkeypatch.setattr(mwf, "load_magnitude_dataset", _stop)
    monkeypatch.setattr(mwf, "market_today", lambda: date(2026, 12, 31))
    with pytest.raises(ValueError, match="2027-01-01"):
        mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m",
                         evaluation_window="final_test")
    assert claimed == [], "the one-time version must not be consumed"
    monkeypatch.setattr(mwf, "market_today", lambda: date(2027, 1, 1))
    # (round 5) the coverage preflight is unlabelled and precedes the claim
    _complete_window(monkeypatch, mwf, missing=[date(2026, 12, 31)])
    with pytest.raises(ValueError, match="2026-12-31"):
        mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m",
                         evaluation_window="final_test")
    assert claimed == [], "a stale source table must not consume the version"
    _complete_window(monkeypatch, mwf)
    with pytest.raises(_Stop):
        mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m",
                         evaluation_window="final_test")
    assert len(claimed) == 1, "covered and closed: the claim precedes the load"
    # the order is the guarantee: refuse while open, preflight, claim, load
    import inspect
    src = inspect.getsource(mwf.walk_forward)
    assert (src.index("_require_closed_window(") < src.index("_session_bar_counts(")
            < src.index("_claim_final_test(") < src.index("load_magnitude_dataset("))


# ── P1/P2: provenance without git, with a real digest ─────────────────────

_X = np.zeros((2, 2), np.float32)
_Y = np.zeros(2, np.int64)
_TS = np.array(["2025-01-02T15:00"], "datetime64[ns]")


def test_provenance_survives_a_container_without_git(monkeypatch, tmp_path):
    """The research image copies lib/ gcp/ scripts/ and no .git, and the job
    sets neither GIT_COMMIT nor CONTAINER_IMAGE_DIGEST, so every Cloud Run
    walk-forward raised before its first fold (Codex P1). K_REVISION is not a
    digest and must not be recorded as one (Codex P2)."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.delenv("CONTAINER_IMAGE_DIGEST", raising=False)
    monkeypatch.setenv("K_REVISION", "magnitude-engine-00042")
    monkeypatch.setattr(mwf, "BUILD_INFO_PATH", tmp_path / "build_info.json")

    def no_git(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(mwf.subprocess, "run", no_git)
    p = mwf._execution_provenance(_X, _Y, _TS)
    assert p["code_commit"] is None
    assert p["container_digest"] is None
    assert p["criteria_version"]


def test_provenance_prefers_the_image_stamp_then_the_deploy_env(monkeypatch, tmp_path):
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    stamp = tmp_path / "build_info.json"
    monkeypatch.setattr(mwf, "BUILD_INFO_PATH", stamp)
    monkeypatch.setenv("GIT_COMMIT", "fff000")
    monkeypatch.setenv("CONTAINER_IMAGE_DIGEST",
                       "us-east1-docker.pkg.dev/p/r/trading-system@sha256:deadbeef")
    p = mwf._execution_provenance(_X, _Y, _TS)
    assert p["code_commit"] == "fff000"
    assert p["container_digest"].endswith("@sha256:deadbeef")
    stamp.write_text(json.dumps({"git_commit": "abc123", "git_dirty": False}))
    assert mwf._execution_provenance(_X, _Y, _TS)["code_commit"] == "abc123"


def _deploy_fn(name: str) -> str:
    code = "\n".join(l for l in (REPO / "gcp/deploy.sh").read_text().splitlines()
                     if not l.lstrip().startswith("#"))
    m = re.search(r"^" + name + r"\(\)\s*\{(.*?)^\}", code, re.M | re.S)
    assert m, name
    return m.group(1)


def test_the_research_build_stamps_the_commit_into_the_image():
    body = _deploy_fn("build_research_image")
    assert "_stamp_build_info" in body
    stamp = _deploy_fn("_stamp_build_info")
    assert "git rev-parse HEAD" in stamp and "gcp/build_info.json" in stamp
    assert "gcp/build_info.json" in (REPO / ".gitignore").read_text()


def test_the_magnitude_job_is_deployed_with_the_digest_it_records():
    body = _deploy_fn("deploy_magnitude_engine")
    assert "_resolve_image_ref" in body
    assert "CONTAINER_IMAGE_DIGEST=${image_digest}" in body
    # the env names the image the job runs, not the tag it was resolved from
    assert '--image "${image_digest}"' in body
    assert '--image "${research_image}"' not in body


# ── P2: provenance timestamps bind as TIMESTAMPTZ ─────────────────────────

def test_results_dataframe_binds_provenance_timestamps_as_timestamps():
    """ISO strings landed as object dtype, to_sql bound them as text, and
    PostgreSQL rejected text for TIMESTAMPTZ, dropping every fold row from
    magnitude_walk_forward_results inside the caught persist error."""
    from gcp.research.magnitude_engine.mag_walk_forward import _results_dataframe
    folds = [
        {"fold": "a", "status": "OK",
         "train_data_max_ts": "2023-12-29T20:59:00+00:00",
         "evaluation_data_min_ts": "2024-01-02T14:30:00+00:00",
         "evaluation_data_max_ts": None},
        {"fold": "b", "status": "SKIP_THIN"},
    ]
    df = _results_dataframe("phase0", "QQQ", "15m", folds, "run-x")
    for col in ("train_data_max_ts", "evaluation_data_min_ts",
                "evaluation_data_max_ts"):
        assert str(df[col].dtype) == "datetime64[ns, UTC]", col
    assert df["train_data_max_ts"].iloc[0] == pd.Timestamp("2023-12-29T20:59:00Z")
    assert df["evaluation_data_max_ts"].isna().all()


# ── P2: artifacts are namespaced by window and consumers verify it ────────

def test_evaluation_windows_get_their_own_artifact_root():
    from gcp.research.magnitude_engine.mag_config import gcs_run_prefix
    sys.path.insert(0, str(REPO / "scripts"))
    from _magnitude_analysis_helpers import research_prefix

    canonical = gcs_run_prefix("phase0", "SPY", "15m")
    assert gcs_run_prefix("phase0", "SPY", "15m",
                          evaluation_window="development") == canonical
    v = gcs_run_prefix("phase0", "SPY", "15m", evaluation_window="validation")
    assert v != canonical and not v.startswith(canonical)
    assert "/_windows/validation/" in v
    both = gcs_run_prefix("phase0", "SPY", "15m", label_mode="excursion",
                          evaluation_window="final_test")
    assert "/_windows/final_test/" in both and "/_research/excursion/" in both
    assert research_prefix("phase0", "SPY", "15m",
                           evaluation_window="validation") == v + "/"
    assert research_prefix("phase0", "SPY", "15m", "excursion",
                           evaluation_window="final_test") == both + "/"
    with pytest.raises(ValueError):
        gcs_run_prefix("phase0", "SPY", "15m", evaluation_window="nope")


def test_walk_forward_writes_both_artifacts_under_its_window():
    import inspect
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    src = inspect.getsource(mwf.walk_forward)
    assert src.count("evaluation_window=window.name)") == 2


def test_the_report_refuses_a_summary_from_another_window(monkeypatch):
    import scripts.assemble_magnitude_results as am
    listed: list = []

    def fake_ls(prefix):
        listed.append(prefix)
        return [prefix + "walk_forward_r1.json"]

    monkeypatch.setattr(am, "_ls", fake_ls)
    monkeypatch.setattr(am, "_cat", lambda uri: {"split_name": "validation", "gates": {}})
    with pytest.raises(RuntimeError, match="validation"):
        am.latest_result("phase0", "SPY", "15m", "b")
    got = am.latest_result("phase0", "SPY", "15m", "b", evaluation_window="validation")
    assert got["split_name"] == "validation"
    assert "/_windows/validation/" in listed[-1]
    # summaries written before windows existed carry no split_name: they are
    # development only when their own schedule proves it (round 5)
    monkeypatch.setattr(am, "_cat", lambda uri: {
        "gates": {}, "cutoffs": ["2019-01-01", "2020-01-01", "2021-01-01"],
        "folds": [{"test_end": "2020-01-01"}, {"test_end": "2021-01-01"},
                  {"test_end": "2023-12-29"}]})
    assert am.latest_result("phase0", "SPY", "15m", "b") is not None


# ═══════════════ Codex review of #1193, second round (32fba58) ═══════════════

def test_final_test_folds_cannot_be_overridden(monkeypatch):
    """`--evaluation-window=final_test --cutoffs=2026-06-01` passed the range
    check, trained on the first half of the holdout and evaluated the rest,
    then consumed the marker: a leak and a silently changed final-test
    population (Codex P1)."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    monkeypatch.setattr(mwf, "load_magnitude_dataset", _stop)
    monkeypatch.setattr(mwf, "market_today", lambda: date(2027, 1, 1))
    monkeypatch.setattr(mwf, "_claim_final_test", lambda *a, **k: None)
    _complete_window(monkeypatch, mwf)
    with pytest.raises(ValueError, match="holdout"):
        mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m",
                         evaluation_window="final_test", cutoffs=["2026-06-01"])
    with pytest.raises(ValueError, match="holdout"):
        mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m",
                         evaluation_window="final_test",
                         cutoffs=["2026-01-01", "2026-06-01"])
    # the window's own start is the one accepted spelling
    with pytest.raises(_Stop):
        mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m",
                         evaluation_window="final_test", cutoffs=["2026-01-01"])


def test_the_final_test_version_is_a_constant_not_a_flag():
    """A CLI value defeated the one-time marker: after consuming v1 the same
    operator could pass v2 and re-read the identical holdout (Codex P1)."""
    import inspect
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    assert "final_test_version" not in inspect.signature(mwf.walk_forward).parameters
    assert "final_test_version" not in inspect.signature(mwf.run_all_cells).parameters
    assert "--final-test-version" not in inspect.getsource(mwf.main)
    assert "_claim_final_test(FINAL_TEST_VERSION," in inspect.getsource(mwf.walk_forward)


def test_only_the_final_window_may_promote_a_production_model():
    """The deployed job defaults to development with
    MAG_PERSIST_PRODUCTION_MODEL=true; with the bounded read, a routine
    passing run would have flipped LATEST to a model missing every session
    after 2023 (Codex P1)."""
    import inspect
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    assert mwf.production_persist_refusal(WINDOWS["final_test"]) is None
    for name in ("development", "validation"):
        reason = mwf.production_persist_refusal(WINDOWS[name])
        assert name in reason and "final_test" in reason
    src = inspect.getsource(mwf.walk_forward)
    assert (src.index("production_persist_refusal(window)")
            < src.index("_persist_production_model_artifact("))
    assert 'summary["production_model_refused"]' in src


# ═══════════════ Codex review of #1193, third round (70430ca) ═══════════════

def test_window_cutoffs_is_the_single_fold_schedule():
    """The harness and the naive baseline evaluated different fold
    schedules; both now read one rule."""
    import inspect
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    from gcp.research.magnitude_engine.evaluation_windows import window_cutoffs
    assert window_cutoffs(WINDOWS["development"]) == [
        "2019-01-01", "2020-01-01", "2021-01-01", "2022-01-01", "2023-01-01"]
    assert window_cutoffs(WINDOWS["validation"]) == ["2024-01-01", "2025-01-01"]
    assert window_cutoffs(WINDOWS["final_test"]) == ["2026-01-01"]
    assert window_cutoffs(WINDOWS["validation"], ["2024-07-01"]) == ["2024-07-01"]
    with pytest.raises(ValueError, match="outside"):
        window_cutoffs(WINDOWS["validation"], ["2023-07-01"])
    with pytest.raises(ValueError, match="holdout"):
        window_cutoffs(WINDOWS["final_test"], ["2026-06-01"])
    assert "window_cutoffs(window, cutoffs)" in inspect.getsource(mwf.walk_forward)


def test_the_final_test_refuses_data_that_stops_short_of_its_last_session():
    """The date check proves the window has ended, not that the table holds
    it: a stale source still consumed the one-time version and then found
    a thin or empty final fold (Codex P1)."""
    import inspect
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    from gcp.research.magnitude_engine.evaluation_windows import (
        assert_window_covered, last_expected_session)
    final = WINDOWS["final_test"]
    assert last_expected_session(final) == date(2026, 12, 31)
    short = pd.to_datetime(["2026-01-02", "2026-12-24"]).values.astype("datetime64[D]")
    with pytest.raises(ValueError, match="2026-12-31"):
        assert_window_covered(final, short)
    full = pd.to_datetime(["2026-01-02", "2026-12-31"]).values.astype("datetime64[D]")
    assert_window_covered(final, full)
    src = inspect.getsource(mwf.walk_forward)
    assert src.index("assert_window_covered(") < src.index("_claim_final_test(")


def test_provenance_records_a_dirty_build(monkeypatch, tmp_path):
    """The image copies the modified working tree, so a bare HEAD would
    attribute code that is not reproducible from that commit to a clean
    revision (Codex P2)."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    stamp = tmp_path / "build_info.json"
    monkeypatch.setattr(mwf, "BUILD_INFO_PATH", stamp)
    stamp.write_text(json.dumps({"git_commit": "abc123", "git_dirty": True}))
    assert mwf._execution_provenance(_X, _Y, _TS)["code_commit"] == "abc123-dirty"
    stamp.write_text(json.dumps({"git_commit": "abc123", "git_dirty": False}))
    assert mwf._execution_provenance(_X, _Y, _TS)["code_commit"] == "abc123"


def test_the_naive_baseline_honours_the_window_it_accepts():
    """It took --evaluation-window through the shared helper and ignored it:
    unbounded load, every DEFAULT_CUTOFFS fold including 2026, a fixed
    six-fold verdict (Codex P1)."""
    src = (REPO / "scripts/naive_calendar_lookup_baseline.py").read_text()
    assert "until=window.end.isoformat()" in src
    assert "window_cutoffs(window)" in src
    assert "min_folds_required(len(cutoffs))" in src
    assert "c >= 6 " not in src and "list(DEFAULT_CUTOFFS)" not in src


# ═══════════════ Codex review of #1193, fourth round (96d2396) ═══════════════

def test_the_naive_baseline_refuses_the_final_window_and_purges_like_the_harness():
    """A baseline run under final_test scored the holdout without the
    completion check or the one-time claim, and could be rerun forever; and
    its masks kept the session the harness purges, so a marginal comparison
    could be a mask artefact (Codex P1 + P2)."""
    src = (REPO / "scripts/naive_calendar_lookup_baseline.py").read_text()
    assert "if window.final:" in src and "SystemExit" in src
    assert "purged_session_masks(" in src and "eastern_sessions(" in src
    assert "bar_dates_arr < train_end_dt" not in src


def test_the_dispatch_wrapper_forwards_the_window():
    src = (REPO / "scripts/dispatch_magnitude_phase.sh").read_text()
    assert "--evaluation-window=*)" in src
    assert '--evaluation-window=${evaluation_window}' in src


def test_the_build_stamp_counts_untracked_source_as_dirty():
    """`git diff --quiet HEAD` ignores untracked files, but `cp -r` ships them
    (Codex P2)."""
    stamp = _deploy_fn("_stamp_build_info")
    assert "git status --porcelain" in stamp
    assert "git diff --quiet" not in stamp
    # (round 6) every copied build input, not only the three source trees
    deploy = (REPO / "gcp/deploy.sh").read_text()
    for name in ("requirements-gcp.txt", "requirements-research.txt",
                 "requirements-gcp.lock", "alert_config.json"):
        assert name in stamp, name
        assert f"cp {name}" in deploy or f"{name} " in deploy, name


def test_the_bootstrap_bar_counts_scheduled_folds_not_prediction_rows():
    """An ERROR or SKIP_THIN fold has no prediction rows, so a bar derived from
    the CSV lowered itself by omission: min_folds_required(4) == 3 where the
    evaluator required min_folds_required(5) == 4 (Codex P1)."""
    import inspect
    import scripts.bootstrap_gate_fragility as bs
    rng = np.random.default_rng(3)
    y = rng.choice(4, size=120, p=[0.64, 0.27, 0.07, 0.02])
    proba = np.tile([0.64, 0.27, 0.07, 0.02], (120, 1))
    preds = pd.DataFrame({
        "fold": "a", "ts": "2025-01-02T15:00:00Z", "true_bucket_idx": y,
        "pred_bucket_idx": 0, "max_proba": 0.64,
        "p_TIGHT": proba[:, 0], "p_NORMAL": proba[:, 1],
        "p_EXPANDED": proba[:, 2], "p_EXPLOSIVE": proba[:, 3]})
    r = bs.bootstrap_one_cell(preds, "5m", n_iter=3, n_folds_scheduled=2)
    assert (r["n_folds"], r["n_folds_scheduled"], r["min_folds_required"]) == (1, 2, 2)
    assert r["cell_pass_rate"] == 0.0, "one fold of two can never reach a 2-fold bar"
    src = inspect.getsource(bs.main)
    assert "load_run_summary(" in src and "n_folds_scheduled=" in src


def test_the_run_summary_loader_is_the_one_reader_of_walk_forward_json(monkeypatch):
    sys.path.insert(0, str(REPO / "scripts"))
    import _magnitude_analysis_helpers as helpers
    name = helpers.research_prefix("phase1", "IWM", "5m") + "walk_forward_r1.json"
    store = {name: json.dumps({"cutoffs": ["2019-01-01", "2020-01-01"],
                               "production_readiness_version": "v1"}).encode()}

    class _Blob:
        def __init__(self, n): self.n = n
        def exists(self): return self.n in store
        def download_as_bytes(self): return store[self.n]

    client = type("C", (), {"bucket": lambda self, _b: type(
        "B", (), {"blob": lambda self, n: _Blob(n)})()})()
    monkeypatch.setattr(helpers.gcs, "Client", lambda: client)
    summary = helpers.load_run_summary("phase1", "IWM", "5m", "b", "r1")
    assert summary["cutoffs"] == ["2019-01-01", "2020-01-01"]
    assert helpers.load_run_readiness_version("phase1", "IWM", "5m", "b", "r1") == "v1"


def test_a_passing_final_test_cell_is_staged_not_promoted(monkeypatch):
    """Gates 1-4 are preliminary; 5-7 run after the walk-forward on its
    predictions. A final-test pass therefore must not move LATEST (Codex P1):
    the candidate is uploaded with a PROMOTION_STAGED marker instead."""
    from tests.gcp.test_mag_persist_production_model import (
        _capture_blob_uploads, _passing_gates, _promotable_model, _toy_data)
    from unittest.mock import patch
    import joblib
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    monkeypatch.setattr(joblib, "dump", lambda obj, buf: buf.write(b"m"))
    X, y = _toy_data()
    fake_client, captured = _capture_blob_uploads()
    with patch.object(mwf, "make_lgbm", return_value=_promotable_model(y)), \
         patch.object(mwf.gcs, "Client", return_value=fake_client):
        uri = mwf._persist_production_model_artifact(
            "QQQ", "15m", run_id="final-001", X_full=X, y_full=y,
            feature_cols=["x"], gates=_passing_gates(), label_mode="body",
            thresholds=(0.5, 1.0, 1.5), calibration="none", stage_only=True)
    assert uri == "gs://test-bucket/magnitude-models/production/QQQ/15m/final-001/"
    assert "magnitude-models/production/QQQ/15m/LATEST" not in captured
    marker = json.loads(
        captured["magnitude-models/production/QQQ/15m/final-001/PROMOTION_STAGED"].decode())
    assert marker["verdict"]["ok"] is True and "gates 5-7" in marker["promote"]
    src = (REPO / "gcp/research/magnitude_engine/mag_walk_forward.py").read_text()
    assert "stage_only=window.final" in src
    assert 'summary["production_model_staged"]' in src


def test_inference_reads_a_staged_only_prefix_as_never_promoted():
    from unittest.mock import patch
    from tests.gcp.test_magnitude_inference import _never_promoted_bucket
    from gcp.research.magnitude_engine import mag_inference as mod
    from gcp.research.magnitude_engine.mag_config import NeverPromoted
    pfx = "magnitude-models/production/SPY/15m"
    client = _never_promoted_bucket(blob_names=[
        f"{pfx}/run-1/model.joblib", f"{pfx}/run-1/PROMOTION_BLOCKED",
        f"{pfx}/run-2/model.joblib", f"{pfx}/run-2/PROMOTION_STAGED"])
    with patch("google.cloud.storage.Client", return_value=client):
        with pytest.raises(NeverPromoted, match="PROMOTION_STAGED"):
            mod._load_model_and_version("SPY", "15m")


# ═══════════════ Codex review of #1193, fifth round (b77c303) ═══════════════

def test_gate_7_requirements_scale_with_the_scheduled_folds():
    """Fixed 6-passing / 4-covered made development (5 folds) unpassable and
    validation / final_test INSUFFICIENT_DATA, so no staged candidate could
    ever complete promotion (Codex P1)."""
    from gcp.research.magnitude_engine.mag_config import gate7_requirements
    assert [gate7_requirements(n) for n in (8, 5, 2, 1)] == [
        (6, 4), (4, 3), (2, 1), (1, 1)]
    with pytest.raises(ValueError):
        gate7_requirements(0)
    src = (REPO / "scripts/implied_vs_realized_check.py").read_text()
    assert "gate7_requirements(len(cutoffs))" in src
    assert 'summary["cutoffs"]' in src and "load_run_summary(" in src
    assert "list(DEFAULT_CUTOFFS)" not in src
    assert "test_end = window.end.isoformat()" in src


def test_every_post_hoc_consumer_reads_only_through_its_window():
    """A validation-window analysis reloaded the whole table and so built
    final-test labels without the claim (Codex P1)."""
    for name in ("implied_vs_realized_check", "model_vs_calendar_explosive_decomp",
                 "magnitude_movement_sim"):
        src = (REPO / f"scripts/{name}.py").read_text()
        assert "until=window.end.isoformat()" in src or \
            "until=WINDOWS[args.evaluation_window].end.isoformat()" in src, name


def test_legacy_summaries_are_development_only_when_their_cutoffs_prove_it(monkeypatch):
    """A pre-window summary ran all eight cutoffs, 2024-2026 included, so it
    is not development evidence by default (Codex P2)."""
    import scripts.assemble_magnitude_results as am
    monkeypatch.setattr(am, "_ls", lambda prefix: [prefix + "walk_forward_r0.json"])
    eight = ["2019-01-01", "2020-01-01", "2021-01-01", "2022-01-01",
             "2023-01-01", "2024-01-01", "2025-01-01", "2026-01-01"]
    monkeypatch.setattr(am, "_cat", lambda uri: {"gates": {}, "cutoffs": eight})
    with pytest.raises(RuntimeError, match="reach past the development window"):
        am.latest_result("phase0", "SPY", "15m", "b")
    monkeypatch.setattr(am, "_cat", lambda uri: {"gates": {}})
    with pytest.raises(RuntimeError, match="neither split_name nor cutoffs"):
        am.latest_result("phase0", "SPY", "15m", "b")
    # (round 9) the cutoffs bound fold STARTS; the old harness ended the last
    # fold at bar_date.max() + 1, so the folds' test_end must be inside too
    monkeypatch.setattr(am, "_cat", lambda uri: {"gates": {}, "cutoffs": eight[:5]})
    with pytest.raises(RuntimeError, match="records no folds"):
        am.latest_result("phase0", "SPY", "15m", "b")
    monkeypatch.setattr(am, "_cat", lambda uri: {
        "gates": {}, "cutoffs": eight[:5],
        "folds": [{"test_end": "2020-01-01"}, {"test_end": "2026-09-16"}]})
    with pytest.raises(RuntimeError, match="folds end at.*2026-09-16"):
        am.latest_result("phase0", "SPY", "15m", "b")
    monkeypatch.setattr(am, "_cat", lambda uri: {
        "gates": {}, "cutoffs": eight[:5],
        "folds": [{"test_end": "2020-01-01"}, {"test_end": "2024-01-01"}]})
    assert am.latest_result("phase0", "SPY", "15m", "b")["cutoffs"] == eight[:5]


def test_the_final_test_is_claimed_before_any_holdout_label_exists(monkeypatch):
    """A rerun after the marker existed still loaded, labelled, logged and
    fingerprinted the holdout before the conditional write refused it; so did
    the loser of a concurrent claim (Codex P1). The claim now follows an
    UNLABELLED coverage preflight and precedes the labelled load."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    order: list[str] = []
    monkeypatch.setattr(mwf, "market_today", lambda: date(2027, 1, 1))
    _complete_window(monkeypatch, mwf)
    real_counts = mwf._session_bar_counts
    monkeypatch.setattr(mwf, "_session_bar_counts",
                        lambda *a, **k: order.append("preflight") or real_counts())

    def refused(*a, **k):
        order.append("claim")
        raise RuntimeError("already been consumed")
    monkeypatch.setattr(mwf, "_claim_final_test", refused)
    monkeypatch.setattr(mwf, "load_magnitude_dataset",
                        lambda *a, **k: order.append("load") or _stop())
    with pytest.raises(RuntimeError, match="consumed"):
        mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m",
                         evaluation_window="final_test")
    assert order == ["preflight", "claim"], "the refused rerun read no holdout row"
    # and the preflight itself carries no label: one MAX(bar_date) below `until`
    src = (REPO / "gcp/research/magnitude_engine/mag_walk_forward.py").read_text()
    assert "COUNT(*)" in src and "bar_date < :until" in src and "GROUP BY bar_date" in src


def test_a_phase0_final_test_stages_its_candidate_without_the_flag():
    """The run consumes the one-time version; without the artifact there is
    nothing for gates 5-7 to promote and no second run to produce it (Codex
    P1), so a phase-0 final run stages unconditionally."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    src = inspect.getsource(mwf.walk_forward)
    assert 'stage_final = window.final and phase == "phase0"' in src
    assert "or stage_final:" in src
    assert src.index("stage_final = ") < src.index("_persist_production_model_artifact(")


# ═══════════════ Codex review of #1193, sixth round (d348107) ═══════════════

def test_a_non_serving_contract_cannot_consume_the_final_test(monkeypatch):
    """`--evaluation-window=final_test --label-mode=put` reached the claim,
    consumed the cell's sole version, and was then refused staging by
    serving_contract_reason, so the body-label decision could never run
    (Codex P1)."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    claimed: list = []
    monkeypatch.setattr(mwf, "market_today", lambda: date(2027, 1, 1))
    _complete_window(monkeypatch, mwf)
    monkeypatch.setattr(mwf, "_claim_final_test", lambda *a, **k: claimed.append(a))
    monkeypatch.setattr(mwf, "load_magnitude_dataset", _stop)
    with pytest.raises(ValueError, match="serving contract"):
        mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m",
                         evaluation_window="final_test", label_mode="put")
    assert claimed == []
    monkeypatch.setenv("MAG_THRESHOLDS", "0.35,0.75,1.25")
    with pytest.raises(ValueError, match="serving contract"):
        mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m",
                         evaluation_window="final_test")
    assert claimed == []
    monkeypatch.delenv("MAG_THRESHOLDS")
    with pytest.raises(_Stop):
        mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m",
                         evaluation_window="final_test")
    assert len(claimed) == 1, "the serving contract still claims and loads"
    src = inspect.getsource(mwf.walk_forward)
    assert src.index("serving_contract_reason(") < src.index("_claim_final_test(")


# ═══════════════ Codex review of #1193, seventh round (bccbc84) ═══════════════

def test_every_final_session_must_be_present_and_whole_before_the_claim(monkeypatch):
    """Round 7: MAX(bar_date) accepted a still-ingesting last session. Round
    9: checking the newest date and count still let a wholly missing or
    partially loaded earlier session pass (Codex P1). The preflight now
    compares the WHOLE window against the NYSE schedule: every session
    present, each holding at least its regular-hours bars, no rows on a
    non-session date."""
    from gcp.research.magnitude_engine.evaluation_windows import (
        assert_final_window_complete)
    final = WINDOWS["final_test"]
    expected = {d: 78 for d in _FINAL_SESSIONS}
    with pytest.raises(ValueError, match="missing sessions.*2026-06-30"):
        assert_final_window_complete(final, expected, {
            d: 78 for d in _FINAL_SESSIONS if d != date(2026, 6, 30)})
    with pytest.raises(ValueError, match="incomplete sessions.*2026-01-02: 9 < 78"):
        assert_final_window_complete(final, expected, {**{d: 78 for d in _FINAL_SESSIONS},
                                                       date(2026, 1, 2): 9})
    with pytest.raises(ValueError, match="non-session dates.*2026-07-04"):
        assert_final_window_complete(final, expected, {**{d: 78 for d in _FINAL_SESSIONS},
                                                       date(2026, 7, 4): 78})
    assert_final_window_complete(final, expected, {d: 80 for d in _FINAL_SESSIONS})

    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    claimed: list = []
    monkeypatch.setattr(mwf, "market_today", lambda: date(2027, 1, 1))
    monkeypatch.setattr(mwf, "_claim_final_test", lambda *a, **k: claimed.append(a))
    monkeypatch.setattr(mwf, "load_magnitude_dataset", _stop)
    for kw in ({"missing": [date(2026, 6, 30)]}, {"short": [date(2026, 1, 2)]},
               {"extra": [date(2026, 7, 4)]}):
        _complete_window(monkeypatch, mwf, **kw)
        with pytest.raises(ValueError, match="not complete in the source table"):
            mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m",
                             evaluation_window="final_test")
    assert claimed == []
    src = inspect.getsource(mwf.walk_forward)
    assert (src.index("_session_bar_counts(") < src.index("assert_final_window_complete(")
            < src.index("_claim_final_test("))
    # the query covers the window, not the newest N sessions
    q = (REPO / "gcp/research/magnitude_engine/mag_walk_forward.py").read_text()
    q = q[q.index("def _session_bar_counts("):q.index("def final_test_config_refusal(")]
    assert "bar_date >= :since AND bar_date < :until" in q and "LIMIT" not in q


def test_expected_session_bars_follows_the_nyse_schedule():
    pytest.importorskip("pandas_market_calendars")
    from gcp.research.magnitude_engine.evaluation_windows import expected_session_bars
    exp = expected_session_bars(WINDOWS["final_test"], 5)
    assert exp[date(2026, 11, 27)] == 42, "early close: 210 regular minutes"
    assert exp[date(2026, 11, 30)] == 78
    assert date(2026, 11, 26) not in exp and date(2026, 7, 4) not in exp
    assert min(exp) == date(2026, 1, 2) and max(exp) == date(2026, 12, 31)


def test_a_failed_final_staging_is_recovered_from_the_recorded_verdict(monkeypatch):
    """A staging failure after the claim left no candidate and every rerun
    refused (Codex P1, round 7). Round 8: the same-run resume re-evaluated
    the holdout, so recovery now stages FROM the claimed run's durable
    summary: the claim is strict for every run id, and resume_final_staging
    scores no fold and writes no prediction (Codex P1)."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf

    class Taken(Exception):
        code = 412

    class _Blob:
        def upload_from_string(self, *a, **k): raise Taken()
        def download_as_text(self): return json.dumps({"run_id": "r1"})
        def exists(self): return True
    client = MagicMock()
    client.bucket.return_value.blob.return_value = _Blob()
    monkeypatch.setattr(mwf.gcs, "Client", lambda: client)
    for run_id in ("r1", "r2"):  # the holder itself may not re-run the holdout
        with pytest.raises(RuntimeError, match="--resume-staging=r1"):
            mwf._claim_final_test("v1", "phase0", "IWM", "15m", run_id)
    src = inspect.getsource(mwf.walk_forward)
    assert src.count("--resume-staging={run_id}") == 2

    # resume: holder must match, summary must exist, nothing is re-evaluated
    monkeypatch.setattr(mwf, "_final_claim_holder", lambda *a: "r1")
    monkeypatch.setattr(mwf, "_final_run_summary", lambda *a: None)
    with pytest.raises(RuntimeError, match="no recorded verdict"):
        mwf.resume_final_staging(MagicMock(), "IWM", "15m", "r1")
    with pytest.raises(RuntimeError, match="held by run 'r1'"):
        mwf.resume_final_staging(MagicMock(), "IWM", "15m", "r2")
    gates = {"cell_pass_gates_1_to_4": True}
    recorded = {
        "gates": gates, "split_name": "final_test", "label_mode": "body",
        "thresholds": list(mwf.MAGNITUDE_THRESHOLDS), "calibration": "none", "cv": 3,
        "dataset_fingerprint": "fp1", "code_commit": "c1", "random_seed": 42,
        "class_weight_power": 0.75, "feature_cols": ["x"]}
    monkeypatch.setattr(mwf, "_final_run_summary", lambda *a: dict(recorded))
    monkeypatch.setattr(mwf, "_execution_provenance",
                        lambda *a, **k: {"dataset_fingerprint": "fp1", "code_commit": "c1"})
    monkeypatch.delenv("MAG_SEED", raising=False)
    monkeypatch.delenv("MAG_CLASS_WEIGHT_POWER", raising=False)
    df = pd.DataFrame({"ts": pd.to_datetime(["2026-12-31T15:00:00Z"] * 4),
                       mwf.LABEL_COL: ["TIGHT", "NORMAL", "EXPANDED", "EXPLOSIVE"]})
    seen: dict = {}
    monkeypatch.setattr(mwf, "load_magnitude_dataset",
                        lambda *a, **k: seen.update(load=k) or df)
    monkeypatch.setattr(mwf, "featurize", lambda d: (pd.DataFrame({"x": [1.0] * 4}), ["x"]))
    monkeypatch.setattr(mwf, "train_and_evaluate_fold", _stop)
    monkeypatch.setattr(mwf, "_persist_production_model_artifact",
                        lambda *a, **k: seen.update(persist=k) or "gs://b/p/")
    assert mwf.resume_final_staging(MagicMock(), "IWM", "15m", "r1") == "gs://b/p/"
    assert seen["load"]["until"] == "2027-01-01"
    assert seen["persist"]["stage_only"] is True and seen["persist"]["gates"] == gates
    # (round 9) the staged model must be THE recorded candidate: a different
    # dataset, commit, seed, class weighting or column set refuses
    for drift in ({"dataset_fingerprint": "fp2"}, {"code_commit": "c2"},
                  {"random_seed": 7}, {"class_weight_power": 0.5},
                  {"feature_cols": ["x", "y"]}):
        monkeypatch.setattr(mwf, "_final_run_summary", lambda *a, d=drift: {**recorded, **d})
        with pytest.raises(RuntimeError, match="cannot be reproduced here"):
            mwf.resume_final_staging(MagicMock(), "IWM", "15m", "r1")
    # the CLI exposes it and stops there
    assert "--resume-staging" in inspect.getsource(mwf.main)


# ═══════════════ Codex review of #1193, eighth round (e3200e8) ═══════════════

def test_the_final_claim_is_one_per_cell_and_reserved_for_the_serving_phase(monkeypatch):
    """A per-phase marker let the no_backfill plan's phase0, phase1 and
    phase3 tasks each score the same holdout and pick a model family after
    the one-time test (Codex P1)."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    assert mwf._final_claim_path("v1", "IWM", "15m").endswith("/v1/IWM_15m.json")
    assert "phase" not in mwf._final_claim_path("v1", "IWM", "15m").split("/")[-1]
    claimed: list = []
    monkeypatch.setattr(mwf, "market_today", lambda: date(2027, 1, 1))
    _complete_window(monkeypatch, mwf)
    monkeypatch.setattr(mwf, "_claim_final_test", lambda *a, **k: claimed.append(a))
    monkeypatch.setattr(mwf, "load_magnitude_dataset", _stop)
    for phase in ("phase1", "phase3"):
        with pytest.raises(ValueError, match="serving phase"):
            mwf.walk_forward(MagicMock(), phase, "IWM", "15m",
                             evaluation_window="final_test")
    assert claimed == []
    with pytest.raises(_Stop):
        mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m",
                         evaluation_window="final_test")
    assert len(claimed) == 1
    wrapper = (REPO / "scripts/dispatch_magnitude_phase.sh").read_text()
    assert '"$evaluation_window" = "final_test" ] && [ "$plan" != "phase0" ]' in wrapper


def test_a_non_serving_feature_set_cannot_consume_the_final_test(monkeypatch):
    """`--features=options_iv` staged a model whose columns mag_inference
    never constructs, after consuming the version (Codex P1)."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    claimed: list = []
    monkeypatch.setattr(mwf, "market_today", lambda: date(2027, 1, 1))
    _complete_window(monkeypatch, mwf)
    monkeypatch.setattr(mwf, "_claim_final_test", lambda *a, **k: claimed.append(a))
    monkeypatch.setattr(mwf, "load_magnitude_dataset", _stop)
    for feats in ("options_iv", "prune,calendar", "bogus"):
        with pytest.raises(ValueError, match="serving feature set"):
            mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m",
                             evaluation_window="final_test", features=feats)
    assert claimed == []
    src = inspect.getsource(mwf.walk_forward)
    assert src.index("features.strip()") < src.index("_claim_final_test(")


def test_the_decomposition_reads_the_analyzed_runs_fold_schedule():
    """Predictions of a run with custom --cutoffs are labelled by that
    schedule, so DEFAULT_CUTOFFS lookups found no predictions (Codex P2)."""
    src = (REPO / "scripts/model_vs_calendar_explosive_decomp.py").read_text()
    assert "load_run_summary(" in src and 'summary["cutoffs"]' in src
    assert "test_end = window.end.isoformat()" in src
    assert "list(DEFAULT_CUTOFFS)" not in src
    assert "purged_session_masks(sessions, cut, test_end)" in src


# ═══════════════ Codex review of #1193, ninth round (4b2997a) ═══════════════

def test_the_frozen_serving_configuration_is_required_before_the_claim(monkeypatch):
    """`--calibration`, MAG_CLASS_WEIGHT_POWER and MAG_SEED were unrestricted,
    so a final run could consume the holdout for a configuration validation
    never selected (Codex P1)."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    monkeypatch.delenv("MAG_SEED", raising=False)
    monkeypatch.delenv("MAG_CLASS_WEIGHT_POWER", raising=False)
    assert mwf.final_test_config_refusal(mwf.DEFAULT_CALIBRATION, mwf.DEFAULT_CV) is None
    assert "calibration" in mwf.final_test_config_refusal("isotonic", mwf.DEFAULT_CV)
    assert "cv=5" in mwf.final_test_config_refusal(mwf.DEFAULT_CALIBRATION, 5)
    monkeypatch.setenv("MAG_SEED", "7")
    assert "MAG_SEED" in mwf.final_test_config_refusal(mwf.DEFAULT_CALIBRATION, mwf.DEFAULT_CV)
    monkeypatch.delenv("MAG_SEED")
    monkeypatch.setenv("MAG_CLASS_WEIGHT_POWER", "0.5")
    assert "MAG_CLASS_WEIGHT_POWER" in mwf.final_test_config_refusal(
        mwf.DEFAULT_CALIBRATION, mwf.DEFAULT_CV)

    claimed: list = []
    monkeypatch.setattr(mwf, "market_today", lambda: date(2027, 1, 1))
    _complete_window(monkeypatch, mwf)
    monkeypatch.setattr(mwf, "_claim_final_test", lambda *a, **k: claimed.append(a))
    monkeypatch.setattr(mwf, "load_magnitude_dataset", _stop)
    with pytest.raises(ValueError, match="frozen serving configuration"):
        mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m", evaluation_window="final_test")
    monkeypatch.delenv("MAG_CLASS_WEIGHT_POWER")
    with pytest.raises(ValueError, match="frozen serving configuration"):
        mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m",
                         evaluation_window="final_test", calibration="isotonic")
    assert claimed == []
    src = inspect.getsource(mwf.walk_forward)
    assert src.index("final_test_config_refusal(") < src.index("_claim_final_test(")


def test_a_claim_whose_holder_died_before_any_output_can_be_reclaimed_once(monkeypatch):
    """The marker was consumed before the load, folds and summary, so a
    worker dying in between lost the cell's one-time test for good (Codex
    P1). The claim is now a state machine: 'claimed' -> 'evaluated' once the
    summary is durable; a 'claimed' holder with NO durable output may be
    reclaimed, audited immutably, at most FINAL_RECLAIM_LIMIT times."""
    from gcp.research.magnitude_engine import mag_walk_forward as mwf
    store: dict = {}
    gens: dict = {}

    class Conflict(Exception):
        code = 412

    class _Blob:
        def __init__(self, name): self.name = name
        def exists(self): return self.name in store
        def reload(self): self.generation = gens.get(self.name)
        def download_as_text(self): return store[self.name]
        def upload_from_string(self, data, content_type=None, if_generation_match=None):
            if if_generation_match == 0 and self.name in store:
                raise Conflict("exists")
            if if_generation_match not in (None, 0) and gens.get(self.name) != if_generation_match:
                raise Conflict("generation moved")
            store[self.name] = data
            gens[self.name] = gens.get(self.name, 0) + 1

    class _Bucket:
        def blob(self, name): return _Blob(name)

    class _Client:
        def bucket(self, _): return _Bucket()
        def list_blobs(self, _, prefix=""):
            return [type("B", (), {"name": n})() for n in store if n.startswith(prefix)]
    monkeypatch.setattr(mwf.gcs, "Client", lambda: _Client())
    monkeypatch.setenv("GCS_BUCKET", "b")
    monkeypatch.setattr(mwf, "FINAL_TEST_VERSION", "v")

    mwf._claim_final_test("v", "phase0", "IWM", "15m", "r1")
    path = mwf._final_claim_path("v", "IWM", "15m")
    assert json.loads(store[path])["state"] == "claimed"

    # r1 died with nothing durable: r2 may take over, once per holder
    mwf.reclaim_incomplete_final_test("IWM", "15m", "r1", "r2")
    marker = json.loads(store[path])
    assert marker["run_id"] == "r2" and marker["history"][0]["run_id"] == "r1"
    assert f"{path}.reclaims/r1.json" in store, "immutable audit of the transition"
    with pytest.raises(RuntimeError, match="held by 'r2', not 'r1'"):
        mwf.reclaim_incomplete_final_test("IWM", "15m", "r1", "r3")
    # the limit bounds how often a cell can be re-taken
    mwf.reclaim_incomplete_final_test("IWM", "15m", "r2", "r3")
    with pytest.raises(RuntimeError, match="limit is 2"):
        mwf.reclaim_incomplete_final_test("IWM", "15m", "r3", "r4")
    # a holder that left durable output is not incomplete
    monkeypatch.setattr(mwf, "FINAL_RECLAIM_LIMIT", 9)
    pred = mwf.gcs_run_prefix("phase0", "IWM", "15m", label_mode="body",
                              thresholds=mwf.MAGNITUDE_THRESHOLDS,
                              evaluation_window="final_test") + "/predictions_r3.csv"
    store[pred] = "x"
    with pytest.raises(RuntimeError, match="left durable output"):
        mwf.reclaim_incomplete_final_test("IWM", "15m", "r3", "r4")
    del store[pred]
    # (round 10) a reclaim that died between its audit write and the marker
    # CAS left the audit in place and the marker on the dead holder; the
    # retry reconciles against that audit instead of being refused forever
    store[f"{path}.reclaims/r3.json"] = json.dumps({
        "from_run_id": "r3", "to_run_id": "r4-died", "reclaimed_at": "t",
        "prior_history": json.loads(store[path])["history"]})
    mwf.reclaim_incomplete_final_test("IWM", "15m", "r3", "r4")
    marker = json.loads(store[path])
    assert marker["run_id"] == "r4"
    assert marker["history"][-1] == {"run_id": "r3", "reclaimed_at": "t",
                                     "reconciled_from": "r4-died"}
    # but an audit that records a DIFFERENT transition is not reconciled
    store[f"{path}.reclaims/r4.json"] = json.dumps({
        "from_run_id": "zz", "to_run_id": "q", "reclaimed_at": "t", "prior_history": []})
    with pytest.raises(RuntimeError, match="different transition"):
        mwf.reclaim_incomplete_final_test("IWM", "15m", "r4", "r5")
    del store[f"{path}.reclaims/r4.json"]
    mwf.reclaim_incomplete_final_test("IWM", "15m", "r4", "r5")
    # once the summary is durable the claim is 'evaluated' and final
    mwf._mark_final_test_evaluated("v", "IWM", "15m", "r5", "some/summary.json")
    assert json.loads(store[path])["state"] == "evaluated"
    with pytest.raises(RuntimeError, match="cannot be reclaimed"):
        mwf.reclaim_incomplete_final_test("IWM", "15m", "r5", "r6")
    with pytest.raises(RuntimeError, match="not held by 'zz'"):
        mwf._mark_final_test_evaluated("v", "IWM", "15m", "zz", "s")
    # the transition is written after the summary upload, on the final path only
    src = inspect.getsource(mwf.walk_forward)
    assert src.index("_gcs_upload(json.dumps(summary") < src.index("_mark_final_test_evaluated(")
    assert "--reclaim-incomplete" in inspect.getsource(mwf.main)
    assert "claim_held=True" in inspect.getsource(mwf.main)
