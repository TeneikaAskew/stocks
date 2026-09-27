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
    with pytest.raises(_Stop):
        mwf.walk_forward(MagicMock(), "phase0", "IWM", "15m",
                         evaluation_window="final_test")
    assert claimed == [], "a failed load must not consume the version either"
    # the order is the guarantee: refuse while open, load, then claim
    import inspect
    src = inspect.getsource(mwf.walk_forward)
    assert (src.index("_require_closed_window(") < src.index("load_magnitude_dataset(")
            < src.index("_claim_final_test("))


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
    # summaries written before windows existed carry no split_name: development
    monkeypatch.setattr(am, "_cat", lambda uri: {"gates": {}})
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
