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
