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
