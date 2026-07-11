"""Pins lib/chart_voter.py to the July-6 client voter it was ported from
(platform/src/lib/indicators.ts::computeStrategySignals @ 969187eb)."""
import math

from lib.chart_voter import evaluate_chart_voter


def test_call_fires_on_up_run_with_bullish_band():
    # 3 rising closes, RSI in 25-50 band, K<80, price above vwap & ema9
    closes = [100.0, 101.0, 102.0, 103.0]
    out = evaluate_chart_voter(closes, rsi=44.3, stoch_k=60.0, ema9=101.0, vwap=100.5)
    call = out["call"]
    assert call["met_count"] == 5
    assert call["fires"] is True
    assert out["firing"] == "CALL"
    labels = [c["label"] for c in call["conditions"]]
    assert labels == [
        "3 consecutive up moves",
        "RSI 25–50 (bullish band)",
        "StochRSI K < 80 (room to run)",
        "Price > VWAP",
        "Price > EMA9",
    ]


def test_detail_strings_match_july6_format():
    closes = [100.0, 101.0, 100.5, 101.5]  # 2 of last 3 up
    out = evaluate_chart_voter(closes, rsi=44.31, stoch_k=94.8, ema9=None, vwap=None)
    call = out["call"]
    by_id = {c["id"]: c for c in call["conditions"]}
    assert by_id["call_consec_up"]["detail"] == "2/3 last bars up"
    assert by_id["call_rsi_band"]["detail"] == "RSI 44.3"
    assert by_id["call_stoch_room"]["detail"] == "K 94.8"
    assert by_id["call_stoch_room"]["met"] is False        # 94.8 < 80 is False
    assert by_id["call_above_vwap"]["detail"] == "--"      # vwap None -> '--', met False
    assert by_id["call_above_vwap"]["met"] is False
    assert by_id["call_above_ema9"]["detail"] == "--"


def test_no_fire_below_three_and_ties_never_fire():
    # Flat closes: no up/down runs; rsi 50 is outside BOTH bands (strict bounds)
    closes = [100.0, 100.0, 100.0, 100.0]
    out = evaluate_chart_voter(closes, rsi=50.0, stoch_k=50.0, ema9=100.0, vwap=100.0)
    # call met: stoch K<80 only -> 1; put met: stoch K>20 only -> 1 (tie, both <3)
    assert out["call"]["met_count"] == 1
    assert out["put"]["met_count"] == 1
    assert out["call"]["fires"] is False and out["put"]["fires"] is False
    assert out["firing"] is None


def test_strictly_beats_rule():
    # Construct call_met=3, put_met=3 tie -> neither fires even though >=3
    # closes: up,down,up in last 3 -> upRun=2? build a real tie instead:
    # up run 3 (call consec met) + rsi 60 (put band met) + K=50 (both stoch met)
    # + price exactly between vwap/ema9 splits: price>vwap (call), price<ema9 (put)
    closes = [100.0, 101.0, 102.0, 103.0]
    out = evaluate_chart_voter(closes, rsi=60.0, stoch_k=50.0, ema9=104.0, vwap=102.5)
    assert out["call"]["met_count"] == 3   # consec_up, stoch<80, >vwap
    assert out["put"]["met_count"] == 3    # rsi 50-75, stoch>20, <ema9
    assert out["firing"] is None


def test_nan_rsi_treated_as_missing():
    closes = [100.0, 101.0, 102.0, 103.0]
    out = evaluate_chart_voter(closes, rsi=float("nan"), stoch_k=60.0, ema9=101.0, vwap=100.5)
    by_id = {c["id"]: c for c in out["call"]["conditions"]}
    assert by_id["call_rsi_band"]["met"] is False
    assert by_id["call_rsi_band"]["detail"] == "RSI --"


def test_short_series_counts_available_moves_only():
    out = evaluate_chart_voter([100.0, 101.0], rsi=None, stoch_k=None, ema9=None, vwap=None)
    by_id = {c["id"]: c for c in out["call"]["conditions"]}
    assert by_id["call_consec_up"]["detail"] == "1/3 last bars up"
    out_empty = evaluate_chart_voter([], rsi=None, stoch_k=None, ema9=None, vwap=None)
    assert out_empty["firing"] is None
