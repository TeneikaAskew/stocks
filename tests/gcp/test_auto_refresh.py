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


# ──────────────────────────────────────────────────────────────────────
# Both producers share one ceiling on concurrent executions.
#
# Codex P2 on #1094. FANOUT_MAX_TICKERS exists because N enqueued tickers
# become N concurrent Cloud Run executions hitting Vertex at once — the
# pressure that produced the 429 this branch started from. The scheduled
# pipeline respects it; auto-refresh called the shared enqueuer directly
# in its own loop, so the ceiling did not apply to this producer at all.
#
# Not reachable on defaults (top_n is 3), and Codex's "up to 20" overstates
# it — `--ranker-limit` sizes the CANDIDATE POOL, and `top = ranked[:top_n]`
# is what bounds the enqueue. The exposure is the knob: the module docstring
# advertises N as "the only knob", so raising it is the expected way to use
# this job, and nothing stopped it launching 10 at once.
# ──────────────────────────────────────────────────────────────────────


def _count_enqueued(monkeypatch, tickers: list[str], top_n: int) -> list[str]:
    from gcp import auto_refresh_top_n as ar

    sent: list[str] = []
    monkeypatch.setattr(
        ar, "rank_tickers",
        lambda **kw: _fake_rank([(tk, 9.0 - i) for i, tk in enumerate(tickers)]),
    )
    monkeypatch.setattr(ar, "_is_cached_today", lambda tk: False)
    monkeypatch.setattr(ar, "_insert_queued_run", lambda tk, trigger: f"run-{tk}")

    def record(run_id, ticker, **kwargs):
        sent.append(ticker)
        return ar.EnqueueOutcome.ENQUEUED
    monkeypatch.setattr(ar, "enqueue_insight_task", record)
    monkeypatch.setattr("sys.argv", ["prog", "--top-n", str(top_n)])
    ar.main()
    return sent


def test_auto_refresh_does_not_exceed_the_shared_fanout_ceiling(monkeypatch):
    """A raised knob must not launch an unbounded wave at Vertex."""
    from gcp.insight_tasks import FANOUT_MAX_TICKERS

    over = [f"T{i}" for i in range(FANOUT_MAX_TICKERS + 5)]
    sent = _count_enqueued(monkeypatch, over, top_n=len(over))

    assert len(sent) == FANOUT_MAX_TICKERS
    # The highest-ranked survive — this job exists to pre-warm the top.
    assert sent == over[:FANOUT_MAX_TICKERS]


def test_auto_refresh_at_the_ceiling_is_not_clamped(monkeypatch):
    from gcp.insight_tasks import FANOUT_MAX_TICKERS

    at_cap = [f"T{i}" for i in range(FANOUT_MAX_TICKERS)]
    assert _count_enqueued(monkeypatch, at_cap, top_n=len(at_cap)) == at_cap


def test_auto_refresh_default_top_n_is_untouched(monkeypatch):
    """The daily 3 must behave exactly as before."""
    sent = _count_enqueued(monkeypatch, ["SPY", "IWM", "QQQ"], top_n=3)
    assert sent == ["SPY", "IWM", "QQQ"]


def test_the_fanout_ceiling_is_one_constant_both_producers_read(monkeypatch):
    """A second copy would drift. insight_pipeline_job must read the same
    object, not a same-valued literal of its own."""
    from gcp import insight_pipeline_job as job
    from gcp import insight_tasks

    assert job.FANOUT_MAX_TICKERS is insight_tasks.FANOUT_MAX_TICKERS


# ──────────────────────────────────────────────────────────────────────
# A negative top-N must not slice its way around the ceiling.
#
# Codex P2 on the clamp added in 6566876. `min(args.top_n, FANOUT_MAX_TICKERS)`
# bounds only the upper end, and Python's negative slicing then reads
# `ranked[:-1]` as "everything but the last" — measured: top_n=-1 yields 19
# tickers against a ranker_limit of 20, defeating the 5-ticker ceiling the
# clamp exists to enforce.
#
# Rejected rather than clamped to 0. A negative N is unambiguously a
# misconfiguration, not an intent, and clamping it to "enqueue nothing"
# would be the same quiet no-op this job was just fixed for. Exit 2 marks
# it as a config error, distinct from exit 1 (dispatched nothing it had
# work for) and exit 0 (dispatch succeeded).
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_n", [-1, -3, -20])
def test_a_negative_top_n_is_rejected_not_sliced(monkeypatch, bad_n):
    from gcp import auto_refresh_top_n as ar

    sent: list[str] = []
    monkeypatch.setattr(
        ar, "rank_tickers",
        lambda **kw: _fake_rank([(f"T{i}", 9.0) for i in range(20)]),
    )
    monkeypatch.setattr(ar, "_is_cached_today", lambda tk: False)
    monkeypatch.setattr(ar, "_insert_queued_run", lambda tk, trigger: f"run-{tk}")

    def record(run_id, ticker, **kwargs):
        sent.append(ticker)
        return ar.EnqueueOutcome.ENQUEUED
    monkeypatch.setattr(ar, "enqueue_insight_task", record)
    monkeypatch.setattr("sys.argv", ["prog", "--top-n", str(bad_n)])

    rc = ar.main()

    assert rc != 0, "a negative top-N must not report success"
    assert sent == [], f"nothing may be enqueued; got {len(sent)}"


def test_a_negative_top_n_is_rejected_before_the_ranker_runs(monkeypatch):
    """Validation happens up front — a misconfigured run must not pay for
    a ranker pass or write its audit row."""
    from gcp import auto_refresh_top_n as ar

    ranked_called: list[bool] = []

    def spy(**kw):
        ranked_called.append(True)
        return _fake_rank([("SPY", 9.0)])
    monkeypatch.setattr(ar, "rank_tickers", spy)
    monkeypatch.setattr("sys.argv", ["prog", "--top-n", "-1"])

    assert ar.main() != 0
    assert ranked_called == []


def test_zero_top_n_is_a_legitimate_disable(monkeypatch):
    """0 means "pre-warm nothing" and is a valid way to turn this off —
    it must not be swept up by the negative check."""
    from gcp import auto_refresh_top_n as ar

    monkeypatch.setattr(
        ar, "rank_tickers", lambda **kw: _fake_rank([("SPY", 9.0)])
    )
    monkeypatch.setattr(ar, "_is_cached_today", lambda tk: False)
    monkeypatch.setattr("sys.argv", ["prog", "--top-n", "0"])
    assert ar.main() == 0
