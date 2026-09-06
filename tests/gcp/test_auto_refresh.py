"""Unit tests for gcp.auto_refresh_top_n.

Mocks the ranker, the cache check, the run-insert, and the Cloud Tasks
enqueue — verifies the orchestration logic without touching DB or GCP.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _fake_rank(tickers_with_scores: list[tuple[str, float]]) -> dict:
    """Build a fake rank_tickers() return shape."""
    return {
        "run_id": "test-run-id",
        "as_of": "2026-04-25T12:10:00Z",
        "candidate_count": len(tickers_with_scores),
        "excluded_count": 0,
        "ranked": [
            {
                "ticker": tk,
                "score": sc,
                "pct_of_max": sc / 10.0,
                "catalyst_types": ["earnings"],
                "catalyst_metadata": {},
                "score_breakdown": [],
            }
            for tk, sc in tickers_with_scores
        ],
        "weights_used": {},
        "duration_ms": 50,
    }


# ──────────────────────────────────────────────────────────────────────
# Top-N selection + cache filter
# ──────────────────────────────────────────────────────────────────────


def test_top_n_selects_highest_scored_and_skips_cached(monkeypatch):
    """End-to-end: 5 ranked tickers, top_n=3, 1 cached → 2 enqueued.
    Sort order is preserved (the ranker returns descending)."""
    from gcp import auto_refresh_top_n as ar

    monkeypatch.setattr(
        ar, "rank_tickers",
        lambda **kw: _fake_rank([("AVGO", 9.0), ("NVDA", 8.0), ("AAPL", 7.0),
                                  ("TSLA", 5.0), ("META", 3.0)]),
    )
    # AAPL has today's report cached → skip
    cache_hits = {"AAPL": True}
    monkeypatch.setattr(ar, "_is_cached_today",
                        lambda tk: cache_hits.get(tk, False))

    inserted: list[tuple[str, str]] = []
    monkeypatch.setattr(ar, "_insert_queued_run",
                        lambda tk, trigger: f"run-{tk}")
    enqueued: list[tuple[str, str]] = []
    def fake_enqueue(run_id, ticker):
        enqueued.append((run_id, ticker))
        return True
    monkeypatch.setattr(ar, "_enqueue_cloud_task", fake_enqueue)

    rc = ar.main.__wrapped__() if hasattr(ar.main, "__wrapped__") else None
    # main() uses argparse defaults (top_n=3 from env or fallback)
    monkeypatch.setattr("sys.argv", ["prog"])
    rc = ar.main()
    assert rc == 0

    # Top 3 by score = AVGO, NVDA, AAPL. AAPL is cached → skipped.
    # AVGO and NVDA enqueued (in score-desc order).
    assert [tk for _, tk in enqueued] == ["AVGO", "NVDA"]


def test_top_n_zero_when_ranker_empty(monkeypatch):
    from gcp import auto_refresh_top_n as ar

    monkeypatch.setattr(ar, "rank_tickers", lambda **kw: _fake_rank([]))
    monkeypatch.setattr(ar, "_is_cached_today", lambda tk: False)
    enqueued: list = []
    monkeypatch.setattr(ar, "_enqueue_cloud_task",
                        lambda r, t: enqueued.append((r, t)) or True)

    monkeypatch.setattr("sys.argv", ["prog"])
    rc = ar.main()
    assert rc == 0
    assert enqueued == []


def test_top_n_dry_run_skips_db_writes(monkeypatch):
    """--dry-run must not insert runs or call enqueue."""
    from gcp import auto_refresh_top_n as ar

    monkeypatch.setattr(
        ar, "rank_tickers",
        lambda **kw: _fake_rank([("AVGO", 9.0), ("NVDA", 8.0)]),
    )
    monkeypatch.setattr(ar, "_is_cached_today", lambda tk: False)

    insert_calls: list = []
    monkeypatch.setattr(ar, "_insert_queued_run",
                        lambda tk, trigger: insert_calls.append((tk, trigger)) or "x")
    enqueue_calls: list = []
    monkeypatch.setattr(ar, "_enqueue_cloud_task",
                        lambda r, t: enqueue_calls.append((r, t)) or True)

    monkeypatch.setattr("sys.argv", ["prog", "--dry-run"])
    rc = ar.main()
    assert rc == 0
    assert insert_calls == []
    assert enqueue_calls == []


def test_enqueue_failure_does_not_block_other_tickers(monkeypatch):
    """If one ticker's enqueue fails, the others must still try."""
    from gcp import auto_refresh_top_n as ar

    monkeypatch.setattr(
        ar, "rank_tickers",
        lambda **kw: _fake_rank([("AVGO", 9.0), ("NVDA", 8.0), ("AAPL", 7.0)]),
    )
    monkeypatch.setattr(ar, "_is_cached_today", lambda tk: False)
    monkeypatch.setattr(ar, "_insert_queued_run",
                        lambda tk, trigger: f"run-{tk}")

    attempted: list[str] = []
    def flaky_enqueue(run_id, ticker):
        attempted.append(ticker)
        return ticker != "NVDA"  # fail on NVDA
    monkeypatch.setattr(ar, "_enqueue_cloud_task", flaky_enqueue)

    monkeypatch.setattr("sys.argv", ["prog"])
    rc = ar.main()
    # Job exits 0 even on partial failure
    assert rc == 0
    # All three were attempted; NVDA failed but AVGO and AAPL succeeded
    assert attempted == ["AVGO", "NVDA", "AAPL"]


def test_top_n_respects_env_var(monkeypatch):
    """INSIGHT_AUTO_REFRESH_TOP_N env var caps the slice."""
    from gcp import auto_refresh_top_n as ar

    monkeypatch.setenv("INSIGHT_AUTO_REFRESH_TOP_N", "1")
    monkeypatch.setattr(
        ar, "rank_tickers",
        lambda **kw: _fake_rank([("AVGO", 9.0), ("NVDA", 8.0), ("AAPL", 7.0)]),
    )
    monkeypatch.setattr(ar, "_is_cached_today", lambda tk: False)
    monkeypatch.setattr(ar, "_insert_queued_run",
                        lambda tk, trigger: f"run-{tk}")
    enqueued: list[str] = []
    monkeypatch.setattr(ar, "_enqueue_cloud_task",
                        lambda r, t: enqueued.append(t) or True)

    monkeypatch.setattr("sys.argv", ["prog"])
    ar.main()
    # Only top 1 was enqueued
    assert enqueued == ["AVGO"]


def test_catalyst_filter_passed_to_ranker(monkeypatch):
    """--catalyst-filter / INSIGHT_AUTO_REFRESH_FILTER reaches rank_tickers."""
    from gcp import auto_refresh_top_n as ar

    captured: dict = {}
    def fake_rank(**kw):
        captured.update(kw)
        return _fake_rank([])
    monkeypatch.setattr(ar, "rank_tickers", fake_rank)

    monkeypatch.setattr("sys.argv", ["prog", "--catalyst-filter",
                                     "earnings,sec_8k", "--dry-run"])
    ar.main()
    assert captured.get("catalyst_filter") == {"earnings", "sec_8k"}
