from gcp.research.magnitude_engine import mag_walk_forward as mwf


def _summary(ticker, tf, *, passed=True, alpha=0.0, **extra):
    gates = {f"g{i}_pass": passed for i in range(1, 8)}
    gates["cell_pass_gates_1_to_4"] = passed
    value = {
        "phase": "phase0",
        "ticker": ticker,
        "tf": tf,
        "label_mode": "body",
        "thresholds": [0.5, 1.0, 1.5],
        "class_weight_power": alpha,
        "features": "",
        "gates": gates,
        "run_id": f"{ticker}-{tf}",
    }
    value.update(extra)
    return value


def test_report_uses_atomic_cells_and_separate_ticker_scorecards():
    summaries = [_summary(ticker, tf) for ticker in ("IWM", "QQQ", "SPY")
                 for tf in ("5m", "15m", "30m")]

    report = mwf.build_promotion_report(summaries)

    assert report["decision_unit"] == [
        "ticker", "timeframe", "target", "feature_set", "label_version"]
    assert set(report["scorecards"]) == {"IWM", "QQQ", "SPY"}
    for ticker, cells in report["scorecards"].items():
        assert [cell["decision_key"]["timeframe"] for cell in cells] == [
            "5m", "15m", "30m"]
        assert all(cell["baseline_scope"]["ticker"] == ticker for cell in cells)


def test_failed_cell_cannot_be_rescued_by_fleet_counts():
    summaries = [
        _summary("IWM", "5m", passed=False),
        _summary("QQQ", "5m"),
        _summary("SPY", "5m"),
    ]

    report = mwf.build_promotion_report(summaries)

    assert report["fleet_diagnostics_non_decisioning"][
        "eligible_count_by_timeframe"]["5m"] == 2
    assert report["scorecards"]["IWM"][0]["status"] == "rejected"


def test_timeframe_can_be_disabled_for_only_one_ticker():
    summaries = [_summary("IWM", "5m"), _summary("IWM", "15m"),
                 _summary("QQQ", "15m")]
    report = mwf.build_promotion_report(
        summaries, disabled_timeframes={"IWM": {"15m"}})

    by_key = {
        (ticker, cell["decision_key"]["timeframe"]): cell
        for ticker, cells in report["scorecards"].items() for cell in cells
    }
    assert by_key[("IWM", "15m")]["status"] == "withdrawn"
    assert by_key[("IWM", "5m")]["status"] == "eligible"
    assert by_key[("QQQ", "15m")]["status"] == "rejected"


def test_higher_timeframes_need_new_preregistered_all_gate_pass():
    old = _summary("SPY", "15m")
    preregistered = _summary(
        "SPY", "30m", preregistered_experiment=True)
    missing_posthoc = _summary(
        "QQQ", "30m", preregistered_experiment=True)
    missing_posthoc["gates"].pop("g7_pass")

    report = mwf.build_promotion_report([old, preregistered, missing_posthoc])
    statuses = {
        (ticker, cell["decision_key"]["timeframe"]): cell["status"]
        for ticker, cells in report["scorecards"].items() for cell in cells
    }
    assert statuses[("SPY", "15m")] == "rejected"
    assert statuses[("SPY", "30m")] == "eligible"
    assert statuses[("QQQ", "30m")] == "rejected"


def test_only_unweighted_phase0_5m_reaches_eligibility_track():
    unweighted = _summary("IWM", "5m", alpha=0.0)
    weighted = _summary("QQQ", "5m", alpha=0.75)
    promoted = _summary(
        "SPY", "5m", alpha=0.0,
        production_model_uri="gs://bucket/model")

    report = mwf.build_promotion_report([unweighted, weighted, promoted])
    statuses = {
        ticker: cells[0]["status"]
        for ticker, cells in report["scorecards"].items() if cells
    }
    assert statuses == {"IWM": "eligible", "QQQ": "research", "SPY": "promoted"}


def test_archived_run_without_weight_metadata_fails_closed():
    archived = _summary("IWM", "5m")
    archived.pop("class_weight_power")
    archived.pop("feature_set", None)

    cell = mwf.build_promotion_report([archived])["scorecards"]["IWM"][0]

    assert cell["status"] == "research"
    assert "class_weight_alpha=unknown" in cell["decision_key"]["feature_set"]


def test_calibration_and_cv_are_part_of_training_variant_identity():
    none = _summary("IWM", "5m", calibration="none", cv=3)
    isotonic = _summary("IWM", "5m", calibration="isotonic", cv=5)

    cells = mwf.build_promotion_report([none, isotonic])["scorecards"]["IWM"]

    assert cells[0]["decision_key"] != cells[1]["decision_key"]
    assert "calibration=none:cv=3" in cells[0]["decision_key"]["feature_set"]
    assert "calibration=isotonic:cv=5" in cells[1]["decision_key"]["feature_set"]


def test_failed_artifact_gate_changes_eligible_cell_to_rejected():
    blocked = _summary(
        "SPY", "5m", promotion_blocked_reason="collapsed candidate")

    cell = mwf.build_promotion_report([blocked])["scorecards"]["SPY"][0]

    assert cell["status"] == "rejected"
    assert cell["reason"] == "collapsed candidate"


def test_disabled_cell_is_withdrawn_before_persistence_dispatch(monkeypatch):
    calls = []

    def fake_walk_forward(_engine, phase, ticker, tf, **kwargs):
        calls.append((ticker, tf, kwargs["disabled"]))
        return _summary(ticker, tf, phase=phase)

    monkeypatch.setattr(mwf, "TICKERS", ("IWM",))
    monkeypatch.setattr(mwf, "TIMEFRAMES", ("5m", "15m"))
    monkeypatch.setattr(mwf, "walk_forward", fake_walk_forward)

    report = mwf.run_all_cells(
        object(), "phase0", persist_production_model=True,
        disabled_timeframes={"IWM": {"5m"}})

    assert calls == [("IWM", "5m", True), ("IWM", "15m", False)]
    assert report["scorecards"]["IWM"][0]["status"] == "withdrawn"


def test_validated_higher_timeframe_has_an_independent_evidence_path():
    gates = {f"g{i}_pass": True for i in range(1, 5)}
    evidence = {
        "phase": "phase0", "ticker": "SPY", "tf": "15m",
        "preregistered_experiment": True,
        "gates": {f"g{i}_pass": True for i in range(5, 8)},
    }

    mwf._apply_promotion_evidence(gates, evidence, "phase0", "SPY", "15m")

    assert all(gates[f"g{i}_pass"] is True for i in range(1, 8))


def test_promotion_evidence_cannot_be_reused_for_another_cell():
    evidence = {
        "phase": "phase0", "ticker": "SPY", "tf": "15m",
        "preregistered_experiment": True,
        "gates": {f"g{i}_pass": True for i in range(5, 8)},
    }

    try:
        mwf._apply_promotion_evidence({}, evidence, "phase0", "QQQ", "15m")
    except ValueError as exc:
        assert "does not identify this cell" in str(exc)
    else:
        raise AssertionError("cross-cell evidence must fail closed")
