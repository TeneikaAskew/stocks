"""FEAT-INSIGHT-001: the conservative short plan GET /api/insights/report serves.

The consumer-gate unit tests call the planner directly. This one follows the
conservative persona plan the insights page shows, end to end:

  canned summarizer data (the orchestrator suite's canned_bundle, with the
  strat section's FTFC score set per case)
  -> lib.agents.orchestrator.run_insight_pipeline (the real bundle build,
     context_from_bundle and compute_persona_plans; only the LLM is mocked,
     and it returns a short)
  -> gcp.insight_pipeline_job._upsert_report (the real row writer; the
     connection is captured in memory)
  -> GET /api/insights/report/{ticker} (the real router, reading the captured
     row through a fake connection that applies the router's own
     ticker / run_kind = 'live' filter)

On origin/main the conservative short takes a bullish +0.60 reading and
stands aside on a bearish -0.60 one, because its minimum reads +0.30 whatever
the trade's direction. Here the minimum follows the direction: the short
stands aside on +0.60 and sizes on -0.60.

No network and no database.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.agents.test_agent_orchestrator import (  # noqa: E402
    _MockLLM,
    _mock_factory_ctor,
    canned_bundle,  # noqa: F401  (pytest fixture)
    seven_role_snapshot,  # noqa: F401  (pytest fixture)
)

TICKER = 'SPY'


class _ShortMockLLM(_MockLLM):
    """The orchestrator suite's mock, turned to a short at every stage that
    sets the direction (judge, trader, portfolio manager)."""

    async def complete(self, *args, **kwargs):  # type: ignore[override]
        from lib.agents.schema import (
            EntryZone, JudgeOutput, PortfolioManagerOutput, TraderOutput,
        )
        result = await super().complete(*args, **kwargs)
        parsed = result.parsed
        if isinstance(parsed, JudgeOutput):
            result.parsed = parsed.model_copy(update={'verdict': 'short'})
        elif isinstance(parsed, TraderOutput):
            result.parsed = parsed.model_copy(update={
                'direction': 'short', 'entry_zone': EntryZone(low=498.5, high=500.0),
                'stop': 503.5, 'targets': [496.0, 492.0],
                'invalidation': 'Close above 503.5.'})
        elif isinstance(parsed, PortfolioManagerOutput):
            result.parsed = parsed.model_copy(update={
                'direction': 'short', 'entry_zone': EntryZone(low=498.5, high=500.0),
                'stop': 503.5, 'targets': [496.0, 492.0],
                'invalidation': 'Close above 503.5.',
                'thesis': 'Short against the trigger low.'})
        return result


@pytest.fixture(scope="module")
def client():
    original_cwd = os.getcwd()
    platform_dir = str(PROJECT_ROOT / "platform")
    if platform_dir not in sys.path:
        sys.path.insert(0, platform_dir)
    os.chdir(platform_dir)
    from starlette.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:
        yield c
    os.chdir(original_cwd)


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError('external I/O attempted in an isolated API test')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket, 'create_connection', refuse)


def _set_strat_score(monkeypatch, score: float) -> None:
    import lib.strat as lib_strat
    real = lib_strat.compute_strat_status

    def with_score(ticker, *args, **kwargs):
        out = dict(real(ticker, *args, **kwargs))
        out['ftfc_score'] = score
        out['ftfc_direction'] = 'bullish' if score > 0 else 'bearish'
        return out
    monkeypatch.setattr(lib_strat, 'compute_strat_status', with_score)


class _Cursor:
    def __init__(self, store: list):
        self.store = store
        self._row = None

    def execute(self, sql, params=None):
        if 'INSERT INTO insight_reports' in sql:
            row_id, ticker, as_of, report, model_versions, cost, _per_role, latency, run_kind = params
            self.store.append((row_id, ticker, as_of, json.loads(report),
                               json.loads(model_versions), cost, latency, run_kind))
            self._row = (row_id,)
        elif 'FROM insight_reports' in sql:
            assert "run_kind = 'live'" in sql
            rows = [r for r in self.store if r[1] == params[0] and r[7] == 'live']
            self._row = rows[-1] if rows else None
        else:
            raise AssertionError(f'unexpected SQL in an isolated API test: {sql[:80]}')

    def fetchone(self):
        return self._row

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Conn:
    def __init__(self, store: list):
        self.store = store

    def cursor(self):
        return _Cursor(self.store)

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


def _served_conservative(monkeypatch, client, snapshot, score: float) -> dict:
    """Run the real pipeline on a short at `score`, persist it with the real
    writer, and return the conservative plan GET /api/insights/report serves."""
    from lib.agents import orchestrator
    import gcp.insight_pipeline_job as job
    from api.routers import insights as insights_router

    _set_strat_score(monkeypatch, score)
    report = asyncio.run(orchestrator.run_insight_pipeline(
        TICKER, snapshot=snapshot, llm_factory=_mock_factory_ctor(_ShortMockLLM())))
    assert report.direction == 'short'

    store: list = []
    monkeypatch.delenv('INSIGHT_AS_OF', raising=False)        # a live run
    monkeypatch.setattr(job, 'connect', lambda: _Conn(store))
    monkeypatch.setattr(insights_router, 'connect', lambda: _Conn(store))
    assert job._upsert_report(report) is not None

    r = client.get(f'/api/insights/report/{TICKER}')
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['ticker'] == TICKER
    assert body['report']['direction'] == 'short'
    assert body['report']['strat_status']['ftfc_score'] == score
    plans = {p['persona']: p for p in body['report']['persona_plans']}
    return plans['conservative']


def test_conservative_short_served_by_the_api_follows_the_trade_direction(
        canned_bundle, seven_role_snapshot, client, monkeypatch, no_network):  # noqa: F811
    bullish = _served_conservative(monkeypatch, client, seven_role_snapshot, 0.6)
    bearish = _served_conservative(monkeypatch, client, seven_role_snapshot, -0.6)
    print(f"\nGET /api/insights/report/{TICKER}, conservative short at FTFC +0.60: "
          f"size={bullish['position_size_pct']!r} rationale={bullish['rationale']!r}")
    print(f"GET /api/insights/report/{TICKER}, conservative short at FTFC -0.60: "
          f"size={bearish['position_size_pct']!r} rationale={bearish['rationale']!r}")

    # A bullish reading is against a short: stand aside, and say why.
    assert bullish['position_size_pct'] == 0.0
    assert 'Stand aside: FTFC alignment +0.60 above -0.30 threshold.' in bullish['rationale']
    # A bearish reading is with the short: the plan sizes.
    assert bearish['position_size_pct'] > 0.0
    assert 'Stand aside' not in bearish['rationale']
