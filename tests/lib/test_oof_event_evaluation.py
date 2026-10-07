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


@pytest.mark.parametrize("column", ["timestamp", "trained_through", "session"])
def test_rejects_missing_oof_boundaries(column):
    candidates = _candidates()
    candidates.loc[0, column] = None
    with pytest.raises(ValueError, match="non-OOF predictions"):
        evaluate_oof_events(candidates, _quotes())


def test_rejects_negative_latency():
    with pytest.raises(ValueError, match="latency_ms"):
        EvaluationConfig(latency_ms=-1)


def test_rejects_invalid_multiplier_and_null_alert_id():
    with pytest.raises(ValueError, match="multiplier"):
        EvaluationConfig(multiplier=0)
    candidates = _candidates()
    candidates.loc[0, "alert_id"] = None
    with pytest.raises(ValueError, match="alert_id"):
        evaluate_oof_events(candidates, _quotes())


def test_overlapping_alerts_share_position_capacity():
    candidates = _candidates(
        ("2025-01-02 14:30Z", "2025-01-02 14:35Z"), ("long", "long")
    )
    quotes = _quotes()
    quotes = pd.concat([quotes, pd.DataFrame([{**quotes.iloc[0].to_dict(),
        "timestamp": pd.Timestamp("2025-01-02 14:36Z")}])], ignore_index=True)
    report = evaluate_oof_events(
        candidates, quotes, EvaluationConfig(bootstrap_samples=20, max_open_positions=1)
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


def test_contract_selection_freezes_first_eligible_chain_snapshot():
    quotes = _quotes()
    quotes["strike"] = 505
    quotes["contract"] = "SPY-EARLY-C505"
    late = _quotes()
    late["timestamp"] = pd.to_datetime(late["timestamp"], utc=True) + pd.Timedelta(hours=1)
    report = evaluate_oof_events(
        _candidates(), pd.concat([quotes, late], ignore_index=True),
        EvaluationConfig(bootstrap_samples=20),
    )
    assert report.events.iloc[0].contract == "SPY-EARLY-C505"


def test_entry_without_exit_is_not_censored_and_blocks_eligibility():
    quotes = _quotes().iloc[:1]
    report = evaluate_oof_events(_candidates(), quotes, EvaluationConfig(bootstrap_samples=20))
    assert report.events.iloc[0].status == "open_no_exit_quote"
    assert report.events.iloc[0].notional_in > 0
    assert report.metrics["net"]["fills"] == 1
    assert report.metrics["net"]["turnover"] > 0
    assert not report.production_eligible
    assert "lack an executable exit quote" in report.eligibility_reasons[-1]


def test_invalid_quotes_are_not_trading_performance_evidence():
    quotes = _quotes()
    quotes["bid"] = quotes["ask"] + 1
    report = evaluate_oof_events(_candidates(), quotes, EvaluationConfig(bootstrap_samples=20))
    assert report.evidence_classification == "model-quality evidence only"
    assert not report.production_eligible


def test_missing_strike_is_not_an_executable_contract():
    quotes = _quotes()
    quotes["strike"] = None
    report = evaluate_oof_events(_candidates(), quotes, EvaluationConfig(bootstrap_samples=20))
    assert report.evidence_classification == "model-quality evidence only"


def test_bid_only_exit_is_executable_and_scoped_to_instrument():
    quotes = _quotes()
    quotes.loc[1, "ask"] = None
    collision = quotes.iloc[[1]].copy()
    collision["instrument"] = "QQQ"
    collision["bid"] = 99.0
    collision["timestamp"] = pd.Timestamp("2025-01-02 15:00Z")
    report = evaluate_oof_events(
        _candidates(), pd.concat([quotes, collision], ignore_index=True),
        EvaluationConfig(bootstrap_samples=20),
    )
    assert report.events.iloc[0].status == "filled"
    assert report.events.iloc[0].gross_pnl == pytest.approx(30.0)


@pytest.mark.parametrize("prediction, expected", [(1.0, 1), (-1.0, -1)])
def test_float_predictions_are_directional(prediction, expected):
    candidates = _candidates(predictions=(prediction,))
    report = evaluate_oof_events(candidates, _quotes(), EvaluationConfig(bootstrap_samples=20))
    assert report.events.iloc[0].direction == expected


def test_missed_fill_draw_is_paired_by_alert_across_baselines():
    sessions = ("2025-01-02", "2025-01-03")
    candidates = _candidates(
        tuple(f"{d} 14:30Z" for d in sessions), ("flat", "long")
    )
    report = evaluate_oof_events(
        candidates, _quotes((2.1, 2.1), (2.4, 2.4), sessions),
        EvaluationConfig(bootstrap_samples=20, fill_probability=.8, random_seed=7),
    )
    # Seed 7 draws ~.625 for alert 1 and ~.897 for alert 2. The model
    # abstains on alert 1, but must still use alert 2's draw just as the prior
    # baseline does, rather than shifting the RNG stream.
    assert report.metrics["net"]["fills"] == 0
    assert report.baselines["class_prior"]["fills"] == 1


def test_drawdown_preserves_intraday_loss_before_recovery():
    events = _candidates(
        ("2025-01-02 14:30Z", "2025-01-02 15:30Z"), ("long", "long")
    )
    quotes = _quotes((2.0, 2.0), (1.0, 3.1), ("2025-01-02", "2025-01-02"))
    # Move the second chain one hour later so both alerts select distinct trades.
    quotes.loc[2:, "timestamp"] = pd.to_datetime(quotes.loc[2:, "timestamp"], utc=True) + pd.Timedelta(hours=1)
    report = evaluate_oof_events(
        events, quotes, EvaluationConfig(bootstrap_samples=20, max_open_positions=1)
    )
    assert report.metrics["net"]["total_pnl"] > 0
    assert report.metrics["net"]["max_drawdown"] > 100


def test_capacity_is_processed_in_actual_entry_order():
    candidates = _candidates(
        ("2025-01-02 14:30Z", "2025-01-02 15:00Z"), ("long", "long")
    )
    early = _quotes()
    early["timestamp"] = [pd.Timestamp("2025-01-02 15:01Z"),
                          pd.Timestamp("2025-01-02 15:31Z")]
    # The earlier alert sees no quote until 15:01 too in a shared chain, so use
    # a different instrument to give it a genuinely delayed 16:00 entry.
    candidates.loc[0, "instrument"] = "QQQ"
    late = _quotes()
    late["instrument"] = "QQQ"
    late["timestamp"] = [pd.Timestamp("2025-01-02 16:00Z"),
                         pd.Timestamp("2025-01-02 16:30Z")]
    report = evaluate_oof_events(
        candidates, pd.concat([early, late], ignore_index=True),
        EvaluationConfig(bootstrap_samples=20, max_open_positions=1),
    )
    assert report.events.status.tolist() == ["filled", "filled"]
