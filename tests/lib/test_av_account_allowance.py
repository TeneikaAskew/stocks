"""Offline purchased-account/local-allocation regressions; never load API keys."""
import ast
from pathlib import Path

import pytest

from lib.config import AlphaVantageConfig

ROOT = Path(__file__).resolve().parents[2]
CONSUMERS = {
    'gcp/fetchers/evaluate_ew_strikes.py',
    'gcp/fetchers/fetch_alphavantage_intraday.py',
    'gcp/fetchers/fetch_av_earnings_options_backfill.py',
    'gcp/fetchers/fetch_av_historical_options.py',
    'gcp/fetchers/fetch_av_indicators.py',
    'gcp/fetchers/fetch_av_realtime_options.py',
    'gcp/fetchers/fetch_earnings_history.py',
    'gcp/fetchers/fetch_insider_transactions.py',
    'lib/ticker_info.py',
    'scripts/fetch_alphavantage_intraday.py',
    'scripts/fetch_alphavantage_options.py',
}


def test_purchased_account_and_conservative_local_allocation_are_distinct():
    cfg = AlphaVantageConfig()
    assert cfg.rpm == cfg.account_rpm == 600
    assert cfg.local_rpm == 150
    assert cfg.delay_between_calls == pytest.approx(0.4)
    assert cfg.batch_size == 150


@pytest.mark.parametrize('account,local,delay', [(600,600,0.1),(600,150,0.4),(300,100,0.6),(150,150,0.4),(1,1,60)])
def test_explicit_local_allocation_controls_delay_and_batch(account,local,delay):
    cfg = AlphaVantageConfig(rpm=account, local_rpm=local)
    assert cfg.account_rpm == account
    assert cfg.batch_size == local
    assert cfg.delay_between_calls == pytest.approx(delay)


@pytest.mark.parametrize('field,value', [
    (field,value) for field in ['rpm','local_rpm']
    for value in [True,False,0,-1,150.0,1.5,float('nan'),float('inf'),'150',None]
])
def test_invalid_allowances_are_refused_before_consumption(field,value):
    with pytest.raises(ValueError):
        AlphaVantageConfig(**{field:value})


@pytest.mark.parametrize('kwargs', [{'rpm':601},{'rpm':1200},{'local_rpm':601},{'rpm':100,'local_rpm':101}])
def test_unapproved_ceiling_or_unallocated_local_rate_is_refused(kwargs):
    with pytest.raises(ValueError):
        AlphaVantageConfig(**kwargs)


def test_direct_consumer_inventory_is_complete_and_does_not_load_consumers():
    actual = set()
    for folder in ['gcp','lib','scripts']:
        for path in (ROOT/folder).rglob('*.py'):
            tree = ast.parse(path.read_text())
            if any(isinstance(n,ast.ImportFrom) and n.module=='lib.config' and
                   any(a.name=='AlphaVantageConfig' for a in n.names) for n in ast.walk(tree)):
                actual.add(path.relative_to(ROOT).as_posix())
    assert actual == CONSUMERS


@pytest.mark.parametrize('tasks,expected', [(1,0.4),(4,1.6),(0,0.4)])
def test_intraday_task_partition_uses_local_delay_exactly_once(tasks,expected):
    path = ROOT/'gcp/fetchers/fetch_alphavantage_intraday.py'
    tree = ast.parse(path.read_text())
    expressions = [n.value for n in ast.walk(tree) if isinstance(n,ast.Assign)
                   and any(isinstance(t,ast.Name) and t.id=='pace' for t in n.targets)]
    assert len(expressions)==1
    code = compile(ast.Expression(expressions[0]),str(path),'eval')
    result = eval(code,{'__builtins__':{}},{'_av_cfg':AlphaVantageConfig(),'task_cnt':tasks,'max':max})
    assert result == pytest.approx(expected)
