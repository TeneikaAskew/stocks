"""Actual earnings readers through watchlist and persisted-report API responses."""
from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta

import pandas as pd

from lib.earnings_reactions import EARNINGS_NOT_RETIRED_SQL
from tests.fixtures import earnings_calendar_sources as source
from tests.agents.test_agent_orchestrator import (
    _MockLLM, _mock_factory_ctor,
    canned_bundle, seven_role_snapshot,  # noqa: F401
)
from tests.api.test_insight_report_conservative_short import (
    _Conn, client, no_network,  # noqa: F401
)

DAY = date(2026, 11, 11)
KEPT = {'SRC0', 'SRC1', 'SRC4', 'SRC5', 'SRC6', 'SRC7', 'AV', 'UW', 'YAHOO'}


def _rows():
    return [
        source.ew_only('MIX', DAY, earnings_time='postmarket'),
        source.av('MIX', DAY + timedelta(days=1), earnings_time='premarket'),
        *source.alias_control_rows('SRC', DAY),
        source.av('AV', DAY), source.uw('UW', DAY), source.yahoo('YAHOO', DAY),
        source.ew_only('EWONLY', DAY),
    ]


def _earnings_query(sql, params, *, main_shaped):
    # The negative control removes only the retirement predicate. All grouping,
    # ordering, limits and returned columns still come from the actual reader.
    if main_shaped:
        sql = sql.replace('AND ' + EARNINGS_NOT_RETIRED_SQL, '')
    sql = sql.replace("CURRENT_DATE + (:days || ' days')::interval",
                      "date(:__today, '+' || :days || ' days')")
    conn = source.make_db(_rows())
    try:
        return source.run_earnings_sql(conn, sql, params, today=DAY)
    finally:
        conn.close()


def test_watchlist_api_serves_actual_retirement_reader(client, monkeypatch, no_network):  # noqa: F811
    from lib.agents.ranker import candidates, signals
    import gcp.database as database

    main_shaped = False

    def query(sql, params=None):
        if 'FROM earnings_calendar' in sql:
            return _earnings_query(sql, params, main_shaped=main_shaped)
        return pd.DataFrame()

    # Real route -> rank_tickers -> gather_candidates -> earnings reader.
    # All replacements are I/O boundaries; ranking/selection/serialization run.
    monkeypatch.setattr(candidates, '_query', query)
    monkeypatch.setattr(signals, '_query', lambda *_a, **_k: pd.DataFrame())
    monkeypatch.setattr(database, 'query_to_dataframe', lambda *_a, **_k: pd.DataFrame())
    monkeypatch.setattr(database, 'execute_sql', lambda *_a, **_k: None)
    monkeypatch.setenv('INSIGHT_TICKERS', '')

    def served():
        response = client.get('/api/insights/watchlist?catalyst=earnings&expand=true&limit=50')
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['excluded_count'] == 0
        return {row['ticker']: row for row in body['ranked']}

    main_shaped = True
    baseline = served()
    assert baseline['MIX']['catalyst_metadata']['earnings'] == [
        {'date': '2026-11-11', 'timing': 'postmarket'}]
    assert {'SRC2', 'SRC3', 'EWONLY'} <= baseline.keys()
    main_shaped = False
    actual = served()
    assert actual['MIX']['catalyst_metadata']['earnings'] == [
        {'date': '2026-11-12', 'timing': 'premarket'}]
    assert actual.keys() == KEPT | {'MIX'}
    for ticker in KEPT:
        assert json.dumps(actual[ticker], sort_keys=True).encode() == \
            json.dumps(baseline[ticker], sort_keys=True).encode()


def test_generated_report_api_serves_actual_retirement_reader(
        canned_bundle, seven_role_snapshot, client, monkeypatch, no_network):  # noqa: F811
    from lib.agents import orchestrator, summarizers
    import gcp.insight_pipeline_job as job
    from api.routers import insights as insights_router

    other_query = summarizers._query
    main_shaped = False

    def query(sql, params=None):
        if 'FROM earnings_calendar' in sql:
            return _earnings_query(sql, params, main_shaped=main_shaped)
        return other_query(sql, params)

    monkeypatch.setattr(summarizers, '_query', query)
    store = []
    monkeypatch.delenv('INSIGHT_AS_OF', raising=False)
    monkeypatch.setattr(job, 'connect', lambda: _Conn(store))
    monkeypatch.setattr(insights_router, 'connect', lambda: _Conn(store))

    def served(ticker):
        # Earnings are not canned: the real bundle builder/summarizer reads the
        # adversarial SQL fixture, then the real pipeline and writer persist it.
        report = asyncio.run(orchestrator.run_insight_pipeline(
            ticker, as_of=DAY, snapshot=seven_role_snapshot,
            llm_factory=_mock_factory_ctor(_MockLLM())))
        assert job._upsert_report(report) is not None
        response = client.get(f'/api/insights/report/{ticker}')
        assert response.status_code == 200, response.text
        return [event for event in response.json()['report']['catalysts']
                if event['kind'] == 'earnings']

    tickers = sorted(KEPT | {'MIX', 'SRC2', 'SRC3', 'EWONLY'})
    main_shaped = True
    baseline = {ticker: served(ticker) for ticker in tickers}
    assert baseline['MIX'][0]['name'] == 'Earnings — Zz Corp'
    assert baseline['MIX'][0]['date'] == '2026-11-11'
    assert all(baseline[ticker] for ticker in ('SRC2', 'SRC3', 'EWONLY'))
    main_shaped = False
    actual = {ticker: served(ticker) for ticker in tickers}
    assert [(e['name'], e['date']) for e in actual['MIX']] == [
        ('Earnings — Acme', '2026-11-12')]
    assert {ticker for ticker, events in actual.items() if events} == KEPT | {'MIX'}
    for ticker in KEPT:
        assert json.dumps(actual[ticker], sort_keys=True).encode() == \
            json.dumps(baseline[ticker], sort_keys=True).encode()
