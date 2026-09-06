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
