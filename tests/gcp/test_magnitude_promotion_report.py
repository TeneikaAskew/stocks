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
