"""Contract tests for the magnitude feature-research registry."""

import pytest

from gcp.research.magnitude_engine.mag_config import (
    DEFAULT_CUTOFFS,
    FEATURE_FAMILIES,
    FEATURE_REGISTRY,
    FEATURE_REGISTRY_VERSION,
    FEATURE_SELECTION_PROTOCOL,
    TICKERS,
    candidates_for_ticker,
)


def test_registry_is_versioned_complete_and_disjoint():
    assert FEATURE_REGISTRY_VERSION == "magnitude-features-v2"
    assert tuple(FEATURE_REGISTRY) == FEATURE_FAMILIES
    assert all(FEATURE_REGISTRY.values())
    names = [candidate.name for group in FEATURE_REGISTRY.values()
             for candidate in group]
    assert len(names) == len(set(names))
    with pytest.raises(TypeError):
        FEATURE_REGISTRY["price_volume"] = ()


def test_protocol_locks_final_test_out_of_selection():
    protocol = FEATURE_SELECTION_PROTOCOL
    assert protocol.benchmark_phase == "phase0"
    assert protocol.benchmark_class_weight is None
    assert protocol.fold_boundaries == tuple(DEFAULT_CUTOFFS)
    assert protocol.selection_fold_starts == tuple(DEFAULT_CUTOFFS[:-1])
    assert protocol.final_test_cutoff == DEFAULT_CUTOFFS[-1]
    assert protocol.final_test_cutoff not in protocol.selection_fold_starts
    assert protocol.fold_boundaries[-2:] == (
        protocol.selection_fold_starts[-1], protocol.final_test_cutoff)
    assert protocol.importance_split == "held_out_only"
    assert protocol.identical_samples_within_fold
    assert protocol.chronological_folds
    assert "timestamp_leakage" in protocol.rejection_reasons
    assert protocol.min_improving_folds == 5
    assert protocol.min_median_log_loss_improvement == 0.001


@pytest.mark.parametrize("ticker", TICKERS)
def test_candidates_are_ticker_specific_and_hide_unavailable_data(ticker):
    candidates = candidates_for_ticker(ticker)
    assert tuple(candidates) == FEATURE_FAMILIES
    assert not candidates["market_breadth"]
    assert not candidates["cross_asset"]
    event_names = {candidate.name for candidate in candidates["calendar_event"]}
    assert "cal_day_of_week" in event_names
    assert "hours_until_next_hi_event" not in event_names
    assert all(ticker in candidate.tickers
               for family in candidates.values() for candidate in family)
    assert candidates_for_ticker(ticker, include_unavailable=True)["market_breadth"]
    assert candidates_for_ticker(ticker, include_unavailable=True)["cross_asset"]
    all_event_names = {
        candidate.name for candidate in
        candidates_for_ticker(ticker, include_unavailable=True)["calendar_event"]
    }
    assert "hours_until_next_hi_event" in all_event_names


def test_candidates_reject_unknown_ticker():
    with pytest.raises(ValueError, match="unsupported magnitude ticker"):
        candidates_for_ticker("DIA")
