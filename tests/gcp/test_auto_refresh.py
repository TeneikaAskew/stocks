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
    def fake_enqueue(run_id, ticker, **kwargs):
        enqueued.append((run_id, ticker))
        # The child classifies itself from this alone (container overrides
        # replace its env), so assert it is forwarded rather than trusting it.
        assert kwargs.get("triggered_by") == ar.AUTO_REFRESH_TRIGGERED_BY
        return ar.EnqueueOutcome.ENQUEUED
    monkeypatch.setattr(ar, "enqueue_insight_task", fake_enqueue)

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
    monkeypatch.setattr(ar, "enqueue_insight_task",
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
    monkeypatch.setattr(ar, "enqueue_insight_task",
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
    def flaky_enqueue(run_id, ticker, **kwargs):
        attempted.append(ticker)
        return (ar.EnqueueOutcome.NOT_ENQUEUED if ticker == "NVDA"
                else ar.EnqueueOutcome.ENQUEUED)
    monkeypatch.setattr(ar, "enqueue_insight_task", flaky_enqueue)

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
    monkeypatch.setattr(
        ar, "enqueue_insight_task",
        lambda r, t, **k: enqueued.append(t) or ar.EnqueueOutcome.ENQUEUED,
    )

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


# ──────────────────────────────────────────────────────────────────────
# Import-target regression (#1005)
# ──────────────────────────────────────────────────────────────────────
#
# Both DB helpers lazily import `connect`. `gcp.database` has never
# exported one, so `from gcp.database import connect` raised ImportError
# at call time. _is_cached_today swallows every exception and fails open,
# so the wrong target read as "not cached" rather than as an error, and
# _insert_queued_run's failure was caught by the per-ticker handler.
# The job exited 0 every morning while enqueuing nothing: production logs
# show `enqueued=0 ... failed=3` on every run from 2026-08-28 to
# 2026-09-14. These tests stub the CORRECT module, so a regression to a
# module that lacks `connect` fails them.


class _FakeCursor:
    def __init__(self, calls, row):
        self._calls = calls
        self._row = row

    def execute(self, *args):
        self._calls.append(args)

    def fetchone(self):
        return self._row


class _FakeConn:
    def __init__(self, calls, row=None):
        self._calls = calls
        self._row = row

    def cursor(self):
        return _FakeCursor(self._calls, self._row)

    def commit(self):
        self._calls.append(("commit",))

    def close(self):
        pass


def test_cache_check_reaches_a_connect_that_actually_exists(monkeypatch):
    from gcp import auto_refresh_top_n as ar

    calls: list = []
    monkeypatch.setattr(
        "lib.agents.model_routing.connect", lambda: _FakeConn(calls, row=(1,))
    )
    assert ar._is_cached_today("SPY") is True
    # Fails open on ImportError, so "reached the DB" is the real assertion.
    assert calls, "connect() was never reached — import target is wrong"


def test_insert_queued_run_reaches_a_connect_that_actually_exists(monkeypatch):
    from gcp import auto_refresh_top_n as ar

    calls: list = []
    monkeypatch.setattr(
        "lib.agents.model_routing.connect", lambda: _FakeConn(calls)
    )
    run_id = ar._insert_queued_run("SPY", "scheduled")
    assert run_id
    assert any("INSERT INTO insight_runs" in str(c) for c in calls)


# ──────────────────────────────────────────────────────────────────────
# Trigger constraint + queued-row cleanup (Codex, PR #1094)
# ──────────────────────────────────────────────────────────────────────

# Verified against the live constraint on 2026-09-14:
#   CHECK (trigger IN ('on_demand','scheduled','local_dev','manual_batch',
#                      'cache_hit','replay_refresh'))
# 'auto_refresh' is not a member, so the insert raised, the per-ticker
# handler swallowed it, and fixing only the import would have left the
# outage in place behind a different exception.
LIVE_TRIGGER_VALUES = frozenset(
    {"on_demand", "scheduled", "local_dev", "manual_batch",
     "cache_hit", "replay_refresh"}
)


def test_the_trigger_written_is_one_the_constraint_permits(monkeypatch):
    from gcp import auto_refresh_top_n as ar

    seen: list[str] = []
    monkeypatch.setattr(
        ar, "rank_tickers",
        lambda **kw: _fake_rank([("SPY", 5.0)]),
    )
    monkeypatch.setattr(ar, "_is_cached_today", lambda tk: False)
    monkeypatch.setattr(
        ar, "_insert_queued_run",
        lambda tk, trigger: seen.append(trigger) or f"run-{tk}",
    )
    monkeypatch.setattr(ar, "enqueue_insight_task",
                        lambda *a, **k: ar.EnqueueOutcome.ENQUEUED)
    monkeypatch.setattr("sys.argv", ["prog"])
    ar.main()
    assert seen, "no run was inserted"
    assert set(seen) <= LIVE_TRIGGER_VALUES, (
        f"trigger {seen!r} violates insight_runs_trigger_check"
    )


def test_a_failed_enqueue_does_not_leave_the_run_queued_forever(monkeypatch):
    """Nothing will ever pick up a queued row whose enqueue failed, and the
    job exits 0 so Cloud Run never retries. Operators and the UI would see a
    permanently pending run."""
    from gcp import auto_refresh_top_n as ar

    failed: list[tuple[str, str]] = []
    monkeypatch.setattr(
        ar, "rank_tickers", lambda **kw: _fake_rank([("SPY", 5.0)])
    )
    monkeypatch.setattr(ar, "_is_cached_today", lambda tk: False)
    monkeypatch.setattr(ar, "_insert_queued_run", lambda tk, trigger: f"run-{tk}")
    monkeypatch.setattr(ar, "enqueue_insight_task",
                        lambda *a, **k: ar.EnqueueOutcome.NOT_ENQUEUED)
    monkeypatch.setattr(
        ar, "_mark_run_failed",
        lambda run_id, error: failed.append((run_id, error)),
    )
    monkeypatch.setattr("sys.argv", ["prog"])
    ar.main()
    assert failed == [("run-SPY", "Cloud Tasks enqueue failed")]


def test_a_successful_enqueue_leaves_the_run_alone(monkeypatch):
    from gcp import auto_refresh_top_n as ar

    failed: list = []
    monkeypatch.setattr(
        ar, "rank_tickers", lambda **kw: _fake_rank([("SPY", 5.0)])
    )
    monkeypatch.setattr(ar, "_is_cached_today", lambda tk: False)
    monkeypatch.setattr(ar, "_insert_queued_run", lambda tk, trigger: f"run-{tk}")
    monkeypatch.setattr(ar, "enqueue_insight_task",
                        lambda *a, **k: ar.EnqueueOutcome.ENQUEUED)
    monkeypatch.setattr(
        ar, "_mark_run_failed", lambda run_id, error: failed.append(run_id)
    )
    monkeypatch.setattr("sys.argv", ["prog"])
    ar.main()
    assert failed == []


def test_an_unknown_enqueue_is_not_marked_failed(monkeypatch):
    """A child may be running it. Marking the row failed would label a live
    run dead, and the UI would show a failure for a report that then
    appears."""
    from gcp import auto_refresh_top_n as ar

    failed: list = []
    monkeypatch.setattr(
        ar, "rank_tickers", lambda **kw: _fake_rank([("SPY", 5.0)])
    )
    monkeypatch.setattr(ar, "_is_cached_today", lambda tk: False)
    monkeypatch.setattr(ar, "_insert_queued_run", lambda tk, trigger: f"run-{tk}")
    monkeypatch.setattr(
        ar, "enqueue_insight_task", lambda *a, **k: ar.EnqueueOutcome.UNKNOWN
    )
    monkeypatch.setattr(
        ar, "_mark_run_failed", lambda run_id, error: failed.append(run_id)
    )
    monkeypatch.setattr("sys.argv", ["prog"])
    ar.main()
    assert failed == []


# ──────────────────────────────────────────────────────────────────────
# Exit code: a total dispatch failure is a job failure.
#
# Codex P1 on #1094. `setup_insight_tasks_queue` is deliberately non-fatal
# when it cannot grant roles/cloudtasks.enqueuer (setIamPolicy is owner-only
# and the documented deploy identity holds roles/editor), so a deploy can
# succeed with the binding still absent. The insight-pipeline job survives
# that: `_dispatch_fanout` hands NOT_ENQUEUED tickers back and runs them
# in-process. This job does not — it marks each run failed and moves on.
#
# Returning 0 from that state tells Cloud Scheduler the pre-warm succeeded
# while producing zero reports, which is exactly the shape of the 30-day
# `enqueued=0` outage this PR exists to fix. A ticker that fails alone is
# still a partial failure and still exits 0; a run that dispatches NOTHING
# it had work for is a failed run.
# ──────────────────────────────────────────────────────────────────────


def _dispatch_scenario(monkeypatch, outcomes: dict[str, object]):
    """Rank exactly the given tickers, none cached, each with its outcome."""
    from gcp import auto_refresh_top_n as ar

    monkeypatch.setattr(
        ar, "rank_tickers",
        lambda **kw: _fake_rank([(tk, 9.0 - i)
                                 for i, tk in enumerate(outcomes)]),
    )
    monkeypatch.setattr(ar, "_is_cached_today", lambda tk: False)
    monkeypatch.setattr(ar, "_insert_queued_run", lambda tk, trigger: f"run-{tk}")
    monkeypatch.setattr(ar, "enqueue_insight_task",
                        lambda run_id, ticker, **k: outcomes[ticker])
    monkeypatch.setattr(ar, "_mark_run_failed", lambda run_id, error: None)
    monkeypatch.setattr("sys.argv", ["prog"])
    return ar


def test_a_run_that_enqueued_nothing_at_all_exits_nonzero(monkeypatch):
    """The missing-IAM-grant case: every ticker refused, zero reports."""
    from gcp.insight_tasks import EnqueueOutcome

    ar = _dispatch_scenario(monkeypatch, {
        "SPY": EnqueueOutcome.NOT_ENQUEUED,
        "IWM": EnqueueOutcome.NOT_ENQUEUED,
        "QQQ": EnqueueOutcome.NOT_ENQUEUED,
    })
    assert ar.main() != 0


def test_one_ticker_enqueued_still_exits_zero(monkeypatch):
    """Partial failure keeps the old contract — one bad ticker must not
    fail the run for the others."""
    from gcp.insight_tasks import EnqueueOutcome

    ar = _dispatch_scenario(monkeypatch, {
        "SPY": EnqueueOutcome.NOT_ENQUEUED,
        "IWM": EnqueueOutcome.ENQUEUED,
        "QQQ": EnqueueOutcome.NOT_ENQUEUED,
    })
    assert ar.main() == 0


def test_an_unknown_outcome_is_not_counted_as_a_dispatch_failure(monkeypatch):
    """UNKNOWN means a child may be running it, so the run is not empty and
    the job must not claim failure."""
    from gcp.insight_tasks import EnqueueOutcome

    ar = _dispatch_scenario(monkeypatch, {
        "SPY": EnqueueOutcome.NOT_ENQUEUED,
        "IWM": EnqueueOutcome.UNKNOWN,
    })
    assert ar.main() == 0


def test_an_all_cached_run_still_exits_zero(monkeypatch):
    """Nothing to dispatch is not a dispatch failure — the cache is warm,
    which is the outcome this job exists to produce."""
    from gcp import auto_refresh_top_n as ar

    monkeypatch.setattr(
        ar, "rank_tickers", lambda **kw: _fake_rank([("SPY", 9.0)])
    )
    monkeypatch.setattr(ar, "_is_cached_today", lambda tk: True)
    monkeypatch.setattr("sys.argv", ["prog"])
    assert ar.main() == 0
