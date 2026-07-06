"""Tests for the magnitude result-charts small-multiples plotter."""
import os
import pytest

pytest.importorskip("matplotlib")
from scripts.magnitude_result_charts import small_multiples


def _panels():
    return {
        "IWM": {"body": [0.10, 0.20, 0.30], "range": [0.50, 0.55, 0.60]},
        "SPY": {"body": [0.12, 0.18, 0.22], "range": [0.47, 0.54, 0.62]},
    }


def test_writes_nonempty_png(tmp_path):
    out = tmp_path / "chart.png"
    p = small_multiples(_panels(), ["body", "range"], [0.25, 0.45, 0.65], str(out),
                        title="t", ylabel="precision", pct=True, base_rate=0.05)
    assert p == str(out)
    assert os.path.exists(out) and os.path.getsize(out) > 1000


def test_series_length_must_match_x(tmp_path):
    bad = {"IWM": {"body": [0.1, 0.2]}}  # 2 y-values but 3 x positions
    with pytest.raises(ValueError):
        small_multiples(bad, ["body"], [0.25, 0.45, 0.65], str(tmp_path / "x.png"))


def test_empty_panels_raises(tmp_path):
    with pytest.raises(ValueError):
        small_multiples({}, ["body"], [0.25, 0.45], str(tmp_path / "e.png"))
