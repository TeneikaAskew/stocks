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
