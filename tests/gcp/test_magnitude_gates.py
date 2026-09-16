"""Hermetic tests for the magnitude_engine gate logic.

The validation chain is now load-bearing for any future signal-research
project (it produced the magnitude FAIL verdict and the four harness
lessons in mag_config.py). Tests below pin the gate implementations
against synthetic ground-truth so a regression flips a test, not a
production-cell verdict.

NO Cloud SQL, NO GCS, NO LightGBM training — pure-numpy/pandas
inputs, pure-python outputs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gcp.research.magnitude_engine.mag_config import (
    LABEL_CLASSES, LABEL_TO_IDX, MAGNITUDE_THRESHOLDS,
    SUCCESS_BAR_GATE7_RATIO_MIN,
    SUCCESS_BAR_BOOTSTRAP_PASS_MIN,
    SUCCESS_BAR_MECHANISM_RATIO_MIN,
)
from gcp.research.magnitude_engine.mag_dataset import _bucket_magnitude
from gcp.research.magnitude_engine.mag_pred_train import (
    expected_calibration_error, decisive_call_hit_rate, explosive_lift,
    decide_bucket, class_weight_power,
)


# ─────────────────────── Target bucketing ───────────────────────

class TestBucketMagnitude:
    """The 4-class bucketing of |next_close - next_open| / atr_20."""

    def test_thresholds_are_unchanged(self):
        # If this test fires, someone moved the bucket boundaries and the
        # entire walk-forward needs re-running. Locked at (0.5, 1.0, 1.5).
        assert MAGNITUDE_THRESHOLDS == (0.5, 1.0, 1.5)

    def test_tight_bucket(self):
        move = pd.Series([0.1, 0.3, 0.49])
        atr = pd.Series([1.0, 1.0, 1.0])
        result = _bucket_magnitude(move, atr)
        assert list(result.dropna()) == ["TIGHT"] * 3

    def test_normal_bucket(self):
        move = pd.Series([0.5, 0.75, 0.99])
        atr = pd.Series([1.0, 1.0, 1.0])
        result = _bucket_magnitude(move, atr)
        assert list(result.dropna()) == ["NORMAL"] * 3

    def test_expanded_bucket(self):
        move = pd.Series([1.0, 1.25, 1.49])
        atr = pd.Series([1.0, 1.0, 1.0])
        result = _bucket_magnitude(move, atr)
        assert list(result.dropna()) == ["EXPANDED"] * 3

    def test_explosive_bucket(self):
        move = pd.Series([1.5, 2.0, 10.0])
        atr = pd.Series([1.0, 1.0, 1.0])
        result = _bucket_magnitude(move, atr)
        assert list(result.dropna()) == ["EXPLOSIVE"] * 3

    def test_nan_atr_yields_nan_bucket(self):
        # Critical: rows with NaN atr_20 (warmup, gaps) must NOT default
        # to any bucket. Caller drops them. Silent-fallback would
        # contaminate training labels.
        move = pd.Series([0.5, 1.0])
        atr = pd.Series([np.nan, np.nan])
        result = _bucket_magnitude(move, atr)
        assert result.isna().all()

    def test_zero_atr_yields_nan_bucket(self):
        # atr=0 would mean infinite ratio; must not assign a bucket.
        move = pd.Series([0.5, 1.0])
        atr = pd.Series([0.0, 0.0])
        result = _bucket_magnitude(move, atr)
        assert result.isna().all()

    def test_nan_move_yields_nan_bucket(self):
        move = pd.Series([np.nan, np.nan])
        atr = pd.Series([1.0, 1.0])
        result = _bucket_magnitude(move, atr)
        assert result.isna().all()


# ─────────────────────── ECE ───────────────────────

class TestExpectedCalibrationError:
    """Multiclass ECE — binned by max-proba confidence."""

    def test_perfectly_calibrated_gives_zero_ece(self):
        # Every prediction at 100% confidence + correct → ECE = 0
        y_true = np.array([0, 1, 2, 3, 0, 1, 2, 3])
        # One-hot probabilities matching y_true
        proba = np.eye(4)[y_true]
        ece, bins = expected_calibration_error(y_true, proba, n_bins=10)
        assert ece == pytest.approx(0.0, abs=1e-9)

    def test_completely_miscalibrated_gives_high_ece(self):
        # 100% confidence in always-wrong predictions → ECE = 1.0
        y_true = np.array([0, 0, 0, 0])
        proba = np.array([
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ])
        ece, bins = expected_calibration_error(y_true, proba, n_bins=10)
        assert ece == pytest.approx(1.0, abs=1e-9)

    def test_uniform_probabilities(self):
        # Uniform 0.25 across 4 classes; confidence = 0.25; accuracy by
        # luck is ~0.25 if y_true is random → ECE close to 0.
        rng = np.random.default_rng(42)
        n = 1000
        y_true = rng.integers(0, 4, size=n)
        proba = np.full((n, 4), 0.25)
        ece, _ = expected_calibration_error(y_true, proba, n_bins=10)
        # All confidences = 0.25 land in bin 2 (0.2-0.3); accuracy is
        # ~0.25 by random sampling. ECE = |0.25 - acc|.
        assert ece < 0.05

    def test_empty_bins_handled(self):
        # n_bins = 100; only a few predictions → most bins empty.
        # Should not raise; should return finite number.
        y_true = np.array([0, 1])
        proba = np.array([[0.6, 0.2, 0.1, 0.1], [0.1, 0.7, 0.1, 0.1]])
        ece, _ = expected_calibration_error(y_true, proba, n_bins=100)
        assert np.isfinite(ece)
        assert 0.0 <= ece <= 1.0


# ─────────────────────── Decisive-call hit rate ───────────────────────

class TestDecisiveCallHitRate:
    """gate 3 input — accuracy conditional on max-proba ≥ threshold."""

    def test_all_correct_at_high_threshold(self):
        y_true = np.array([0, 1, 2, 3])
        # All predictions correct at 100% confidence
        proba = np.eye(4)[y_true]
        result = decisive_call_hit_rate(y_true, proba, (0.50, 0.90, 0.99))
        for t in ("0.50", "0.90", "0.99"):
            assert result[t]["accuracy"] == 1.0
            assert result[t]["n"] == 4

    def test_no_bars_above_threshold(self):
        y_true = np.array([0, 1])
        # Both predictions at 0.3 max-proba — below 0.5 threshold
        proba = np.array([[0.3, 0.3, 0.2, 0.2], [0.2, 0.3, 0.3, 0.2]])
        result = decisive_call_hit_rate(y_true, proba, (0.50,))
        assert result["0.50"]["n"] == 0
        assert result["0.50"]["accuracy"] is None

    def test_monotone_accuracy_with_threshold(self):
        # As threshold rises, more confident predictions remain. Monotone
        # check: accuracy should not decrease as threshold rises if the
        # model is well-calibrated.
        rng = np.random.default_rng(0)
        n = 500
        y_true = rng.integers(0, 4, size=n)
        # Construct probabilities such that high-confidence picks are
        # systematically MORE correct than low-confidence picks.
        proba = np.zeros((n, 4))
        for i in range(n):
            if i % 3 == 0:
                # high-confidence + correct
                proba[i, y_true[i]] = 0.9
                others = [c for c in range(4) if c != y_true[i]]
                for c in others:
                    proba[i, c] = 0.1 / 3
            else:
                # low-confidence; random
                proba[i] = rng.dirichlet([1, 1, 1, 1])
        accs = []
        for t in (0.40, 0.50, 0.60, 0.70):
            r = decisive_call_hit_rate(y_true, proba, (t,))
            a = r[f"{t:.2f}"]["accuracy"]
            if a is not None:
                accs.append(a)
        # The constructed dataset is biased toward high-confidence correctness,
        # so accuracy should be monotone non-decreasing.
        assert accs == sorted(accs), f"accuracy not monotone: {accs}"


# ─────────────────────── The served decision rule ───────────────────────

# A ~64/27/7/2 label set, the real magnitude balance.
_PRIORS = np.array([0.64, 0.27, 0.07, 0.02])


class TestDecideBucket:
    """decide_bucket names the highest bucket whose probability clears
    lift_min x its prior, else TIGHT. It replaced argmax everywhere a
    bucket is named (2026-09-14)."""

    def test_a_constant_output_model_names_tight_everywhere(self):
        # The c49qf / calibrated-but-signal-free shape: every row emits the
        # base rates. No bucket reaches 2x its own prior, so every decision
        # is TIGHT and the tail-call share is exactly zero.
        proba = np.tile(_PRIORS, (50, 1))
        d = decide_bucket(proba, _PRIORS, 2.0)
        assert d.tolist() == [0] * 50

    def test_argmax_and_decision_disagree_on_a_calibrated_tail_bar(self):
        # A bar the model thinks is 3x its base rate of EXPLOSIVE. Argmax
        # still says TIGHT (0.60 is the largest entry); the decision names
        # EXPLOSIVE. This is the whole point of the change.
        row = np.array([[0.60, 0.27, 0.07, 0.06]])
        assert row.argmax() == 0
        assert decide_bucket(row, _PRIORS, 2.0).tolist() == [3]

    def test_the_highest_clearing_bucket_wins(self):
        # Clears both EXPANDED (0.20 >= 0.14) and EXPLOSIVE (0.05 >= 0.04).
        row = np.array([[0.50, 0.25, 0.20, 0.05]])
        assert decide_bucket(row, _PRIORS, 2.0).tolist() == [3]
        # Clears EXPANDED only.
        row = np.array([[0.55, 0.25, 0.17, 0.03]])
        assert decide_bucket(row, _PRIORS, 2.0).tolist() == [2]
        # Clears NORMAL only (0.54 >= 0.54, inclusive).
        row = np.array([[0.40, 0.54, 0.05, 0.01]])
        assert decide_bucket(row, _PRIORS, 2.0).tolist() == [1]

    def test_the_bar_is_inclusive(self):
        at = np.array([[0.90, 0.05, 0.01, 0.04]])      # exactly 2 x 0.02
        under = np.array([[0.90, 0.05, 0.01, 0.0399]])
        assert decide_bucket(at, _PRIORS, 2.0).tolist() == [3]
        assert decide_bucket(under, _PRIORS, 2.0).tolist() == [0]

    def test_a_zero_prior_makes_a_bucket_unnameable_not_always_named(self):
        # A training slice with no EXPLOSIVE examples: 0 x lift is 0, and a
        # bare >= would fire on every row. It must fire on none.
        priors = np.array([0.70, 0.25, 0.05, 0.0])
        proba = np.array([[0.7, 0.2, 0.05, 0.05], [0.9, 0.05, 0.03, 0.02]])
        assert decide_bucket(proba, priors, 2.0).tolist() == [0, 0]

    def test_malformed_inputs_raise(self):
        with pytest.raises(ValueError, match="one entry per class"):
            decide_bucket(np.tile(_PRIORS, (3, 1)), np.array([0.5, 0.5]), 2.0)
        with pytest.raises(ValueError, match="must be \\(n, 4\\)"):
            decide_bucket(np.ones((3, 3)) / 3, _PRIORS, 2.0)
        for bad in (1.0, 0.5, float("nan"), float("inf")):
            with pytest.raises(ValueError, match="above 1.0"):
                decide_bucket(np.tile(_PRIORS, (3, 1)), _PRIORS, bad)

    def test_the_operating_point_is_the_config_default(self):
        from gcp.research.magnitude_engine.mag_config import DECISION_LIFT_MIN
        assert DECISION_LIFT_MIN == 2.0
        row = np.array([[0.60, 0.27, 0.07, 0.06]])
        assert decide_bucket(row, _PRIORS).tolist() == [3]


# ─────────────────────── EXPLOSIVE lift ───────────────────────

class TestExplosiveLift:
    """gate 4 input — precision of the bars the DECISION RULE names EXPLOSIVE
    over the base rate. Argmax until 2026-09-14; on a calibrated model that
    was a dozen bars per fold and passed on noise."""

    def test_perfect_explosive_calls_give_high_lift(self):
        # 4 bars, 1 truly EXPLOSIVE, and the model puts 0.7 on it: clears
        # 2 x 0.25 by a mile; the other three sit at 0.1 < 0.5 and are not
        # named. precision 1.0, base rate 0.25, lift 4.0.
        y_true = np.array([0, 1, 2, 3])
        proba = np.array([
            [0.7, 0.1, 0.1, 0.1],
            [0.1, 0.7, 0.1, 0.1],
            [0.1, 0.1, 0.7, 0.1],
            [0.1, 0.1, 0.1, 0.7],
        ])
        priors = np.array([0.25, 0.25, 0.25, 0.25])
        result = explosive_lift(y_true, proba,
                                 explosive_idx=LABEL_TO_IDX["EXPLOSIVE"],
                                 class_priors=priors)
        assert result["n_predicted"] == 1
        assert result["precision"] == 1.0
        assert result["base_rate"] == 0.25
        assert result["lift"] == 4.0
        assert result["decision_lift_min"] == 2.0

    def test_no_explosive_calls_returns_none_lift(self):
        # Every row emits its base rate: nothing clears 2x, nothing is named.
        # Lift is None and the gate fails -- a signal-free model cannot pass
        # gate 4 by construction.
        y_true = np.array([3, 3, 3, 0])
        priors = np.array([0.5, 0.2, 0.2, 0.1])
        proba = np.tile(priors, (4, 1))
        result = explosive_lift(y_true, proba,
                                 explosive_idx=LABEL_TO_IDX["EXPLOSIVE"],
                                 class_priors=priors)
        assert result["n_predicted"] == 0
        assert result["lift"] is None

    def test_all_explosive_calls_wrong_gives_zero_precision(self):
        y_true = np.array([0, 1, 2, 0])
        proba = np.array([[0.1, 0.1, 0.1, 0.7]] * 4)
        priors = np.array([0.25, 0.25, 0.25, 0.25])
        result = explosive_lift(y_true, proba,
                                 explosive_idx=LABEL_TO_IDX["EXPLOSIVE"],
                                 class_priors=priors)
        assert result["n_predicted"] == 4
        assert result["precision"] == 0.0
        # Base rate = 0 (no EXPLOSIVE bars in y_true) -- lift undefined
        assert result["lift"] is None

    def test_the_gate_measures_a_population_not_a_dozen_bars(self):
        """The regression this change is for. A calibrated model that argmax-
        names EXPLOSIVE on 1 of 1000 bars and gets it right had lift = 1/base
        under argmax: enormous, and from one bar. Under the decision rule the
        same model is scored on every bar it thinks is 2x its prior."""
        rng = np.random.default_rng(3)
        n = 1000
        y_true = rng.choice(4, size=n, p=[0.64, 0.27, 0.07, 0.02])
        # calibrated-ish rows around the priors, with EXPLOSIVE nudged up on
        # a tenth of the bars (the model has weak but real tail signal)
        proba = np.tile(_PRIORS, (n, 1)) + rng.normal(0, 0.01, (n, 4))
        bump = rng.random(n) < 0.10
        proba[bump, 3] += 0.05
        proba = np.clip(proba, 1e-3, None); proba /= proba.sum(1, keepdims=True)
        assert (proba.argmax(1) == 3).sum() == 0, "argmax never names EXPLOSIVE here"
        result = explosive_lift(y_true, proba,
                                 explosive_idx=LABEL_TO_IDX["EXPLOSIVE"],
                                 class_priors=_PRIORS)
        assert result["n_predicted"] > 50, result


# ─────────────────────── class_weight_power ───────────────────────

class TestClassWeightPower:
    """The exponent the training used, recorded rather than inferred."""

    def test_default_when_unset(self, monkeypatch):
        from gcp.research.magnitude_engine.mag_pred_train import (
            MAG_CLASS_WEIGHT_POWER_DEFAULT)
        monkeypatch.delenv("MAG_CLASS_WEIGHT_POWER", raising=False)
        assert class_weight_power() == MAG_CLASS_WEIGHT_POWER_DEFAULT
        monkeypatch.setenv("MAG_CLASS_WEIGHT_POWER", "   ")
        assert class_weight_power() == MAG_CLASS_WEIGHT_POWER_DEFAULT

    def test_the_named_value_is_the_one_used(self, monkeypatch):
        from gcp.research.magnitude_engine.mag_pred_train import resolve_class_weight
        y = np.array([0] * 64 + [1] * 27 + [2] * 7 + [3] * 2)
        monkeypatch.setenv("MAG_CLASS_WEIGHT_POWER", "0.0")
        assert class_weight_power() == 0.0
        assert resolve_class_weight(y) is None
        monkeypatch.setenv("MAG_CLASS_WEIGHT_POWER", "1.0")
        assert resolve_class_weight(y) == "balanced"
        monkeypatch.setenv("MAG_CLASS_WEIGHT_POWER", "0.3")
        w = resolve_class_weight(y)
        assert isinstance(w, dict) and w[3] > w[0]

    def test_a_malformed_value_raises_rather_than_training_under_the_default(self, monkeypatch):
        # Silently training under a different exponent than the operator
        # named is the unrecorded configuration this exists to end.
        for bad in ("abc", "nan", "inf"):
            monkeypatch.setenv("MAG_CLASS_WEIGHT_POWER", bad)
            with pytest.raises(ValueError, match="MAG_CLASS_WEIGHT_POWER"):
                class_weight_power()

    @pytest.mark.parametrize("bad", ["10", "1.5", "-0.5", "-1"])
    def test_a_value_outside_zero_to_one_raises(self, monkeypatch, bad):
        """resolve_class_weight clamps >= 1 to 'balanced' and <= 0 to
        unweighted, so `--class-weight-power=10` would train balanced while
        the summary recorded 10 (Codex P2 on #1117). The bounds are part of
        the value's meaning, so 0 and 1 stay valid."""
        from gcp.research.magnitude_engine.mag_pred_train import class_weight_power
        monkeypatch.setenv("MAG_CLASS_WEIGHT_POWER", bad)
        with pytest.raises(ValueError, match="outside \\[0, 1\\]"):
            class_weight_power()
        for ok in ("0", "1", "0.75"):
            monkeypatch.setenv("MAG_CLASS_WEIGHT_POWER", ok)
            assert class_weight_power() == float(ok)


        """Every summary before 2026-09-14 lacked it, which is why c49qf's
        setting is unrecoverable."""
        import inspect
        from gcp.research.magnitude_engine import mag_walk_forward as mwf
        src = inspect.getsource(mwf.walk_forward)
        summary = src[src.index("summary = {"):src.index("run_id = (")]
        assert '"class_weight_power": class_weight_power()' in summary
        assert '"decision_lift_min"' in summary


# ─────────────────────── Gate constants live in mag_config ───────────────

class TestGateConstants:
    """Ensures all seven gates have constants in mag_config — the doc
    references them by name."""

    def test_gate_7_threshold_locked(self):
        # If this changes someone moved the gate-7 ratio after seeing
        # the actual ratios (0.83-0.92). The whole project's anti-fitting
        # rule says NO. Locked at 1.25.
        assert SUCCESS_BAR_GATE7_RATIO_MIN == 1.25

    def test_gate_5_threshold_locked(self):
        assert SUCCESS_BAR_BOOTSTRAP_PASS_MIN == 0.80

    def test_gate_6_threshold_locked(self):
        assert SUCCESS_BAR_MECHANISM_RATIO_MIN == 2.0

    def test_label_classes_unchanged(self):
        # The 4 buckets are the project's locked target. If they change,
        # walk-forward and all gate analyses need re-running.
        assert LABEL_CLASSES == ("TIGHT", "NORMAL", "EXPANDED", "EXPLOSIVE")
        assert LABEL_TO_IDX["EXPLOSIVE"] == 3


# ─────────────────────── analysis scripts follow the harness ───────────────

class TestAnalysisScriptsUseTheDecisionRule:
    """gate 5 recomputes gate 4 from the prediction CSV. It has to name
    EXPLOSIVE the way the harness does or it resamples a different
    population than the one the gate counted."""

    def test_bootstrap_fold_gates_runs_under_the_decision_rule(self):
        from scripts.bootstrap_gate_fragility import fold_gates
        rng = np.random.default_rng(5)
        n = 400
        y = rng.choice(4, size=n, p=[0.64, 0.27, 0.07, 0.02])
        proba = np.tile(_PRIORS, (n, 1)) + rng.normal(0, 0.01, (n, 4))
        proba[rng.random(n) < 0.15, 3] += 0.05
        proba = np.clip(proba, 1e-3, None); proba /= proba.sum(1, keepdims=True)
        df = pd.DataFrame({
            "fold": "2020..2021", "ts": "t",
            "true_bucket_idx": y,
            "pred_bucket_idx": decide_bucket(proba, _PRIORS),
            "max_proba": proba.max(1),
            "p_TIGHT": proba[:, 0], "p_NORMAL": proba[:, 1],
            "p_EXPANDED": proba[:, 2], "p_EXPLOSIVE": proba[:, 3],
        })
        g = fold_gates(df, "5m")
        assert set(g) == {"beat", "ece", "ece_pass", "monotone", "lift", "lift_pass"}
        # argmax never names EXPLOSIVE on these rows; the decision rule does,
        # so gate 4 is evaluated on a real population rather than None
        assert (proba.argmax(1) == 3).sum() == 0
        assert g["lift"] is not None

    def test_bootstrap_resamples_are_scored_under_the_original_fold_prior(self):
        """The substitute prior is a property of the ORIGINAL fold. Recomputing
        it from each resample moved the decision threshold with every draw
        (Codex on #1117): a draw that happened to hold more EXPLOSIVE bars
        raised the bar those same bars had to clear."""
        from scripts.bootstrap_gate_fragility import fold_gates, fold_prior
        n = 200
        # Original fold: 2% EXPLOSIVE, so the rule names it at P >= 0.04.
        y = np.array([0] * 128 + [1] * 54 + [2] * 14 + [3] * 4)
        proba = np.tile(_PRIORS, (n, 1)).astype(float)
        proba[:, 3] = 0.06            # every bar clears 2 x 0.02, not 2 x 0.05
        proba[:, 0] -= 0.04
        prior = fold_prior(y)
        assert prior[3] == pytest.approx(0.02)
        # A resample that drew EXPLOSIVE bars five times over.
        idx = np.concatenate([np.arange(0, 190), np.repeat(np.arange(196, 200), 5)])
        sample = pd.DataFrame({
            "fold": "f", "ts": "t", "true_bucket_idx": y[idx],
            "pred_bucket_idx": 3, "max_proba": proba[idx].max(1),
            "p_TIGHT": proba[idx, 0], "p_NORMAL": proba[idx, 1],
            "p_EXPANDED": proba[idx, 2], "p_EXPLOSIVE": proba[idx, 3],
        })
        held = fold_gates(sample, "5m", prior=prior)
        assert held["lift"] is not None       # named under the fold's own rule
        recomputed = fold_gates(sample, "5m")   # the pre-fix behaviour
        assert recomputed["lift"] is None      # 0.06 < 2 x 0.095: nothing named

    def test_bootstrap_one_cell_passes_one_prior_per_fold(self, monkeypatch):
        import scripts.bootstrap_gate_fragility as bs
        rng = np.random.default_rng(3)
        rows = []
        for fold, seed in (("a", 1), ("b", 2)):
            y = rng.choice(4, size=120, p=[0.64, 0.27, 0.07, 0.02])
            proba = np.tile(_PRIORS, (120, 1))
            rows.append(pd.DataFrame({
                "fold": fold, "ts": "t", "true_bucket_idx": y,
                "pred_bucket_idx": 0, "max_proba": 0.64,
                "p_TIGHT": proba[:, 0], "p_NORMAL": proba[:, 1],
                "p_EXPANDED": proba[:, 2], "p_EXPLOSIVE": proba[:, 3],
            }))
        preds = pd.concat(rows, ignore_index=True)
        seen: dict[str, list] = {}
        real = bs.fold_gates

        def spy(fold_df, tf, prior=None):
            seen.setdefault(fold_df["fold"].iloc[0], []).append(prior)
            return real(fold_df, tf, prior=prior)

        monkeypatch.setattr(bs, "fold_gates", spy)
        bs.bootstrap_one_cell(preds, "5m", n_iter=7, seed=1)
        for fold, group in preds.groupby("fold"):
            expect = bs.fold_prior(group["true_bucket_idx"].to_numpy())
            assert len(seen[fold]) == 8          # deterministic pass + 7 resamples
            for got in seen[fold]:
                assert got is not None
                np.testing.assert_array_equal(got, expect)

    def test_gate7_matches_the_open_ended_last_fold_by_prefix(self):
        """implied_vs_realized_check relabels folds from today's dataset; the
        harness labelled the last fold with the day after ITS newest bar.
        One day later the labels differ and the fold reported NO_COVERAGE
        (2026-09-16, 6hp7l). The last fold joins by its start date."""
        import inspect
        from scripts import implied_vs_realized_check as g7
        src = inspect.getsource(g7.main)
        assert 'join["fold"].str.startswith(f"{cut}..")' in src

    def test_bootstrap_constant_fold_has_no_lift(self):
        from scripts.bootstrap_gate_fragility import fold_gates
        n = 200
        y = np.array([0] * 128 + [1] * 54 + [2] * 14 + [3] * 4)
        proba = np.tile(_PRIORS, (n, 1))
        df = pd.DataFrame({
            "fold": "f", "ts": "t", "true_bucket_idx": y,
            "pred_bucket_idx": 0, "max_proba": 0.64,
            "p_TIGHT": proba[:, 0], "p_NORMAL": proba[:, 1],
            "p_EXPANDED": proba[:, 2], "p_EXPLOSIVE": proba[:, 3],
        })
        g = fold_gates(df, "5m")
        assert g["lift"] is None and g["lift_pass"] is False
