"""Unit tests for lib.agents.ranker.

All tests monkey-patch `_query` with a fake that returns canned
DataFrames per SQL substring — same pattern as
tests/test_agent_summarizers.py. No live DB or network.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest


# ──────────────────────────────────────────────────────────────────────
# scoring.py — pure aggregation logic, no I/O
# ──────────────────────────────────────────────────────────────────────


def test_scoring_sums_weighted_contributions():
    from lib.agents.ranker.scoring import weighted_score

    signal_results = {
        "alpha": {"available": True, "score_0_to_1": 0.5,
                  "reason": "x", "raw": {}},
        "beta":  {"available": True, "score_0_to_1": 1.0,
                  "reason": "y", "raw": {}},
    }
    weights = {"alpha": 2.0, "beta": 3.0}
    res = weighted_score(signal_results, weights, gate_signal="liquidity")
    # 0.5 × 2.0 + 1.0 × 3.0 = 4.0
    assert res.total == 4.0
    assert res.max_possible == 5.0
    assert abs(res.pct_of_max - 0.8) < 1e-9
    assert res.excluded_reason is None


def test_scoring_unavailable_signals_contribute_zero_and_dont_inflate_max():
    from lib.agents.ranker.scoring import weighted_score

    signal_results = {
        "ok":      {"available": True, "score_0_to_1": 0.5,
                    "reason": "", "raw": {}},
        "missing": {"available": False, "score_0_to_1": 0.0,
                    "reason": "no data", "raw": {}},
    }
    weights = {"ok": 2.0, "missing": 4.0}
    res = weighted_score(signal_results, weights, gate_signal="liquidity")
    assert res.total == 1.0           # only `ok` counts
    assert res.max_possible == 2.0    # `missing` doesn't inflate the cap
    assert res.pct_of_max == 0.5


def test_scoring_gate_signal_failure_marks_excluded():
    from lib.agents.ranker.scoring import weighted_score

    res = weighted_score(
        {
            "liquidity": {"available": True, "score_0_to_1": 0.0,
                          "reason": "thin", "raw": {"passes": False}},
            "strat_alignment": {"available": True, "score_0_to_1": 1.0,
                                "reason": "perfect", "raw": {}},
        },
        {"liquidity": 0.0, "strat_alignment": 3.0},
        gate_signal="liquidity",
    )
    assert res.excluded_reason is not None
    assert "liquidity" in res.excluded_reason.lower()


# ──────────────────────────────────────────────────────────────────────
# signals.py — each signal queries a table; we monkey-patch _query
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def patch_signal_query(monkeypatch):
    """Install a fake _query that returns canned DataFrames per SQL substring."""
    from lib.agents.ranker import signals

    store: dict[str, pd.DataFrame] = {}

    def set_result(needle: str, df: pd.DataFrame) -> None:
        store[needle] = df

    def fake_query(sql: str, params=None):
        for needle, df in store.items():
            if needle in sql:
                return df
        return pd.DataFrame()

    monkeypatch.setattr(signals, "_query", fake_query)
    return set_result


def test_strat_alignment_full_score(patch_signal_query):
    from lib.agents.ranker.signals import signal_strat_alignment

    patch_signal_query("market_data_daily", pd.DataFrame([{
        "strat_setup": True, "ftfc_score": 1.0, "ftfc_direction": "bull",
        "strat_combo": "2-1-2",
    }]))
    res = signal_strat_alignment("AAPL")
    assert res["available"] is True
    # 0.34 (setup) + 0.33 (ftfc) + 0.33 (direction) = 1.00
    assert res["score_0_to_1"] == 1.0


def test_strat_alignment_mixed_direction_loses_direction_points(patch_signal_query):
    from lib.agents.ranker.signals import signal_strat_alignment

    patch_signal_query("market_data_daily", pd.DataFrame([{
        "strat_setup": False, "ftfc_score": 0.5, "ftfc_direction": "mixed",
        "strat_combo": None,
    }]))
    res = signal_strat_alignment("AAPL")
    # 0 (no setup) + 0.5×0.33=0.165 (ftfc) + 0 (mixed) = 0.165
    assert res["available"] is True
    assert abs(res["score_0_to_1"] - 0.165) < 1e-3


def test_strat_alignment_no_data(patch_signal_query):
    from lib.agents.ranker.signals import signal_strat_alignment

    res = signal_strat_alignment("ZZZ")  # no canned result
    assert res["available"] is False
    assert res["score_0_to_1"] == 0.0


def test_news_topic_score_counts_catalyst_articles(patch_signal_query):
    from lib.agents.ranker.signals import signal_news_topic_score

    # AV NEWS_SENTIMENT topics arrive as lowercase snake_case slugs;
    # CATALYST_TOPICS was tightened to that set so only real catalysts
    # (M&A / earnings / IPO / FOMC / energy_transportation) score.
    patch_signal_query("FROM news_sentiment", pd.DataFrame([
        {"topics": ["mergers_and_acquisitions", "technology"],
         "overall_sentiment_score": 0.4, "relevance_score": 0.9},
        {"topics": ["earnings"],
         "overall_sentiment_score": 0.2, "relevance_score": 0.8},
        {"topics": ["technology"],  # sector tag only; not a catalyst
         "overall_sentiment_score": 0.1, "relevance_score": 0.5},
    ]))
    res = signal_news_topic_score("AVGO")
    assert res["available"] is True
    assert res["raw"]["article_count"] == 3
    assert res["raw"]["catalyst_count"] == 2
    assert res["score_0_to_1"] > 0


def test_news_topic_score_zero_when_no_catalyst_topics(patch_signal_query):
    from lib.agents.ranker.signals import signal_news_topic_score

    patch_signal_query("FROM news_sentiment", pd.DataFrame([
        {"topics": ["technology"],   # sector-only, no catalyst tag
         "overall_sentiment_score": 0.0, "relevance_score": 0.5},
    ]))
    res = signal_news_topic_score("XOM")
    assert res["score_0_to_1"] == 0.0


def test_liquidity_gate_pass_and_fail(patch_signal_query):
    from lib.agents.ranker.signals import signal_liquidity

    patch_signal_query("AVG(volume)", pd.DataFrame([{"avg_vol": 2_000_000}]))
    res = signal_liquidity("AAPL", min_avg_volume=1_000_000)
    assert res["score_0_to_1"] == 1.0
    assert res["raw"]["passes"] is True

    patch_signal_query("AVG(volume)", pd.DataFrame([{"avg_vol": 50_000}]))
    res = signal_liquidity("XYZ", min_avg_volume=1_000_000)
    assert res["score_0_to_1"] == 0.0
    assert res["raw"]["passes"] is False


def test_historical_earnings_reaction_consistent_movers(patch_signal_query):
    from lib.agents.ranker.signals import signal_historical_earnings_reaction

    patch_signal_query("earnings_history eh", pd.DataFrame([
        {"reported_date": date(2025, 10, 30), "pre_close": 100.0, "post_close": 106.0},
        {"reported_date": date(2025, 7, 31),  "pre_close": 90.0,  "post_close": 95.0},
        {"reported_date": date(2025, 4, 30),  "pre_close": 80.0,  "post_close": 84.0},
    ]))
    res = signal_historical_earnings_reaction("AAPL")
    assert res["available"] is True
    assert res["raw"]["n_earnings"] == 3
    # All three were positive moves → 100% same-direction
    assert res["raw"]["same_direction_pct"] == 100.0
    # Avg abs move ~5% → magnitude pts maxed (~0.6)
    # Direction consistency 100% → 0.4
    # Total ~1.0
    assert res["score_0_to_1"] >= 0.95


def test_historical_earnings_reaction_no_data(patch_signal_query):
    from lib.agents.ranker.signals import signal_historical_earnings_reaction

    res = signal_historical_earnings_reaction("ZZZ")
    assert res["available"] is False


def test_insider_buying_three_insiders(patch_signal_query):
    """signal_insider_cluster was split into _buying / _selling so the
    ranker can reward buys and penalize sells separately. This covers
    the buying side."""
    from lib.agents.ranker.signals import signal_insider_buying, signal_insider_selling

    patch_signal_query("insider_transactions", pd.DataFrame([
        {"executive": "Alice", "transaction_type": "A",
         "shares": 1000, "share_price": 100, "value": 100_000},
        {"executive": "Bob",   "transaction_type": "A",
         "shares": 500,  "share_price": 100, "value": 50_000},
        {"executive": "Carol", "transaction_type": "A",
         "shares": 200,  "share_price": 100, "value": 20_000},
    ]))
    buy = signal_insider_buying("AVGO")
    sell = signal_insider_selling("AVGO")
    # 3 buyers → cluster_pts maxed (0.6); no big txn → big_pts = 0
    assert buy["raw"]["unique_insiders"] == 3
    assert buy["score_0_to_1"] == 0.6
    assert buy["raw"]["side"] == "buy"
    # No sells in the window — selling signal returns 0 with the
    # 'no insider selling' reason from the side-specific helper.
    assert sell["score_0_to_1"] == 0.0
    assert "no insider selling" in sell["reason"]


def test_insider_selling_penalizes_disposals(patch_signal_query):
    """The AVGO Apr 2026 case: 5 insiders disposing several million
    each. Selling signal should fire at full strength so the ranker's
    negative weight subtracts from total score."""
    from lib.agents.ranker.signals import signal_insider_selling

    patch_signal_query("insider_transactions", pd.DataFrame([
        {"executive": "Alice", "transaction_type": "D",
         "shares": 5000, "share_price": 350, "value": 1_750_000},
        {"executive": "Bob",   "transaction_type": "D",
         "shares": 4000, "share_price": 350, "value": 1_400_000},
        {"executive": "Carol", "transaction_type": "D",
         "shares": 3000, "share_price": 350, "value": 1_050_000},
    ]))
    res = signal_insider_selling("AVGO")
    assert res["raw"]["side"] == "sell"
    assert res["raw"]["unique_insiders"] == 3
    assert res["raw"]["big_transactions"] == 3
    # 3 distinct sellers → cluster_pts 0.6, ≥1 big sale → big_pts 0.4
    assert res["score_0_to_1"] == 1.0


def test_recent_8k_high_impact_items(patch_signal_query):
    from lib.agents.ranker.signals import signal_recent_8k

    patch_signal_query("FROM sec_filings", pd.DataFrame([
        {"filing_date": date(2026, 4, 24), "items": ["1.01", "7.01"]},
        {"filing_date": date(2026, 4, 22), "items": ["8.01"]},
    ]))
    res = signal_recent_8k("AVGO")
    assert res["available"] is True
    assert res["raw"]["high_impact_count"] == 3  # 1.01, 7.01, 8.01
    assert res["score_0_to_1"] == 1.0  # 3/2 capped at 1


def test_recent_8k_irrelevant_items_get_low_score(patch_signal_query):
    from lib.agents.ranker.signals import signal_recent_8k

    patch_signal_query("FROM sec_filings", pd.DataFrame([
        {"filing_date": date(2026, 4, 24), "items": ["3.01"]},  # not in HIGH_IMPACT
    ]))
    res = signal_recent_8k("AVGO")
    assert res["score_0_to_1"] == 0.2  # filing exists but no high-impact items


def test_top_mover_today(patch_signal_query):
    from lib.agents.ranker.signals import signal_is_top_mover

    patch_signal_query("top_movers_daily", pd.DataFrame([
        {"category": "top_gainers", "rank": 1,
         "change_pct": 12.5, "volume": 50_000_000},
    ]))
    res = signal_is_top_mover("AVGO")
    assert res["score_0_to_1"] == 1.0  # rank 1 → max score


# ──────────────────────────────────────────────────────────────────────
# rank.py — orchestration
# ──────────────────────────────────────────────────────────────────────


def test_rank_tickers_sorts_descending_and_drops_excluded(monkeypatch):
    """End-to-end rank: 3 candidates; 1 fails liquidity; remaining 2
    sorted by score descending."""
    from lib.agents.ranker import rank as rank_module
    from lib.agents.ranker.candidates import CandidateTicker

    candidates = [
        CandidateTicker(ticker="AAA", catalyst_types=["earnings"]),
        CandidateTicker(ticker="BBB", catalyst_types=["sec_8k"]),
        CandidateTicker(ticker="CCC", catalyst_types=["manual"]),
    ]
    monkeypatch.setattr(rank_module, "gather_candidates",
                        lambda **kw: candidates)

    # Per-ticker fake signal results
    per_ticker = {
        "AAA": {  # high score, passes liquidity
            "strat_alignment": {"available": True, "score_0_to_1": 1.0,
                                "reason": "", "raw": {}},
            "liquidity":       {"available": True, "score_0_to_1": 1.0,
                                "reason": "", "raw": {"passes": True}},
        },
        "BBB": {  # mid score, passes
            "strat_alignment": {"available": True, "score_0_to_1": 0.5,
                                "reason": "", "raw": {}},
            "liquidity":       {"available": True, "score_0_to_1": 1.0,
                                "reason": "", "raw": {"passes": True}},
        },
        "CCC": {  # liquidity fails — must be excluded
            "strat_alignment": {"available": True, "score_0_to_1": 1.0,
                                "reason": "", "raw": {}},
            "liquidity":       {"available": True, "score_0_to_1": 0.0,
                                "reason": "thin", "raw": {"passes": False}},
        },
    }
    monkeypatch.setattr(rank_module, "_run_signals_for",
                        lambda tk: per_ticker[tk])
    monkeypatch.setattr(rank_module, "_persist_audit",
                        lambda run_id, result: None)

    result = rank_module.rank_tickers(
        weights={"strat_alignment": 3.0, "liquidity": 0.0},
        limit=10,
        persist_audit=False,
    )
    assert result["candidate_count"] == 3
    assert result["excluded_count"] == 1
    tickers_in_order = [r["ticker"] for r in result["ranked"]]
    assert tickers_in_order == ["AAA", "BBB"]


# ──────────────────────────────────────────────────────────────────────
# candidates.py — minimal smoke
# ──────────────────────────────────────────────────────────────────────


def test_candidate_dedups_by_ticker_and_merges_catalyst_types():
    from lib.agents.ranker.candidates import CandidateTicker

    c = CandidateTicker(ticker="AAPL")
    c.add_catalyst("earnings", date="2026-04-30")
    c.add_catalyst("sec_8k", filing_date="2026-04-24", items=["1.01"])
    c.add_catalyst("earnings", date="2026-04-30")  # dup type
    assert c.catalyst_types == ["earnings", "sec_8k"]
    # Both earnings entries kept under metadata key
    assert len(c.metadata["earnings"]) == 2


# ──────────────────────────────────────────────────────────────────────
# RankerConfig — alert_config.json loader
# ──────────────────────────────────────────────────────────────────────


def test_ranker_config_loads_from_alert_config(tmp_path):
    from lib.config import RankerConfig

    cfg_path = tmp_path / "alert_config.json"
    cfg_path.write_text(
        '{"ranker": {"weights": {"strat_alignment": 5.0}, '
        '"news_lookback_hours": 48}}'
    )
    cfg = RankerConfig.from_alert_config(str(cfg_path))
    assert cfg.weights["strat_alignment"] == 5.0
    assert cfg.news_lookback_hours == 48
    # Untouched defaults preserved
    assert cfg.liquidity_min_volume == 500_000


def test_ranker_config_returns_defaults_when_file_missing(tmp_path):
    from lib.config import RankerConfig

    missing = tmp_path / "nope.json"
    cfg = RankerConfig.from_alert_config(str(missing))
    assert cfg.weights == {}  # falls back to in-code DEFAULT_WEIGHTS
    assert cfg.liquidity_min_volume == 500_000
