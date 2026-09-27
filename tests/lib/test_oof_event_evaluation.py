import pandas as pd
import pytest

from lib.oof_event_evaluation import EvaluationConfig, evaluate_oof_events


def _candidates(times=("2025-01-02 14:30Z",), predictions=("long",)):
    return pd.DataFrame({
        "alert_id": range(1, len(times) + 1),
        "timestamp": times,
        "session": [pd.Timestamp(t).date() for t in times],
        "instrument": "SPY",
        "prediction": predictions,
        "prediction_fold": "wf-2025",
        "trained_through": "2024-12-31 23:59Z",
        "spot": 500.0,
        "target_dte": 0,
        "class_prior_prediction": "long",
        "buy_hold_prediction": "long",
        "volatility_prediction": "flat",
    })


def _quotes(entry_asks=(2.10,), exit_bids=(2.40,), sessions=("2025-01-02",)):
    rows = []
    for i, (ask, bid, session) in enumerate(zip(entry_asks, exit_bids, sessions)):
        start = pd.Timestamp(f"{session} 14:31Z")
        contract = f"SPY-{session}-C500"
        common = {"instrument": "SPY", "contract": contract,
                  "expiration": f"{session} 21:00Z", "strike": 500,
                  "option_type": "call"}
        rows.extend([
            {**common, "timestamp": start, "bid": ask - .10, "ask": ask},
            {**common, "timestamp": start + pd.Timedelta(minutes=30),
             "bid": bid, "ask": bid + .10},
        ])
    return pd.DataFrame(rows)


def test_uses_executable_ask_and_bid_and_reports_gross_and_net():
    report = evaluate_oof_events(
        _candidates(), _quotes(),
        EvaluationConfig(slippage_per_contract_side=1.0, fee_per_contract_side=.65,
                         bootstrap_samples=50, max_acceptable_drawdown=100),
    )
    event = report.events.iloc[0]
    # Quoted ask-to-bid earns $30 gross; $2 slippage and $1.30 fees leave $26.70.
    assert event.gross_pnl == pytest.approx(30.0)
    assert event.net_pnl == pytest.approx(26.70)
    assert report.metrics["gross"]["expected_value_per_alert"] == pytest.approx(30.0)
    assert report.metrics["net"]["expected_value_per_alert"] == pytest.approx(26.70)
    assert report.metrics["net"]["turnover"] == pytest.approx(450.0)
    assert report.evidence_classification == "trading-performance evidence"
    assert report.production_eligible


def test_rejects_predictions_that_are_not_strictly_out_of_fold():
    candidates = _candidates()
    candidates["trained_through"] = candidates["timestamp"]
    with pytest.raises(ValueError, match="non-OOF predictions"):
        evaluate_oof_events(candidates, _quotes())


def test_overlapping_alerts_share_position_capacity():
    candidates = _candidates(
        ("2025-01-02 14:30Z", "2025-01-02 14:35Z"), ("long", "long")
    )
    report = evaluate_oof_events(
        candidates, _quotes(), EvaluationConfig(bootstrap_samples=20, max_open_positions=1)
    )
    assert report.events.status.tolist() == ["filled", "position_limit"]
    # EV is per alert, so rejected overlap remains in the denominator.
    assert report.metrics["net"]["expected_value_per_alert"] == pytest.approx(
        report.events.net_pnl.sum() / 2
    )


def test_missing_execution_data_can_never_claim_trading_performance():
    report = evaluate_oof_events(_candidates(), None, EvaluationConfig(bootstrap_samples=20))
    assert report.evidence_classification == "model-quality evidence only"
    assert not report.production_eligible
    assert "options execution data unavailable" in report.eligibility_reasons
    assert report.events.status.tolist() == ["no_execution_data"]


def test_session_bootstrap_and_drawdown_gate_net_utility():
    sessions = ("2025-01-02", "2025-01-03", "2025-01-06")
    times = tuple(f"{d} 14:30Z" for d in sessions)
    report = evaluate_oof_events(
        _candidates(times, ("long",) * 3),
        _quotes((2.10, 2.10, 2.10), (1.00, 1.00, 3.00), sessions),
        EvaluationConfig(bootstrap_samples=200, max_acceptable_drawdown=50),
    )
    assert report.metrics["net"]["max_drawdown"] > 50
    assert not report.production_eligible
    assert "net drawdown exceeds configured limit" in report.eligibility_reasons
    assert report.metrics["net"]["session_bootstrap_ci_low"] < 0


def test_contract_selection_is_nearest_strike_not_underlying_return():
    quotes = _quotes()
    farther = quotes.copy()
    farther["contract"] = "SPY-FAR-C510"
    farther["strike"] = 510
    farther["ask"] = .10
    farther["bid"] = 10.0
    report = evaluate_oof_events(
        _candidates(), pd.concat([farther, quotes], ignore_index=True),
        EvaluationConfig(bootstrap_samples=20),
    )
    assert report.events.iloc[0].contract == "SPY-2025-01-02-C500"
    assert report.baselines.keys() == {
        "abstention", "class_prior", "buy_and_hold", "simple_volatility"
    }
