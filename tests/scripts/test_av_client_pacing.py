"""Exercise actual research CLI parsers and loops with fake keys and no live I/O."""
import importlib.util
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import dotenv
import pytest
import requests
import lib.config as config_module
from lib.config import AlphaVantageConfig

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=['intraday','options'])
def client(request, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('live HTTP or dotenv access forbidden')
    monkeypatch.setattr(requests,'get',forbidden)
    monkeypatch.setattr(dotenv,'load_dotenv',lambda *a,**k:False)
    monkeypatch.setattr(AlphaVantageConfig,'get_api_keys',staticmethod(lambda:['fake-test-key']))
    def load(cfg=None):
        cfg = cfg or AlphaVantageConfig()
        monkeypatch.setattr(config_module,'AlphaVantageConfig',lambda:cfg)
        path = ROOT/f'scripts/fetch_alphavantage_{request.param}.py'
        spec = importlib.util.spec_from_file_location('isolated_av_'+request.param,path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return request.param,module
    return load


@pytest.mark.parametrize('delay',['0','-1','nan','inf','-inf','0.1','0.39'])
def test_actual_parser_rejects_invalid_or_faster_delay_before_work(client,monkeypatch,delay):
    _,mod = client()
    show = Mock(side_effect=AssertionError('invalid delay reached local work'))
    monkeypatch.setattr(mod,'show_parquet_data',show)
    # Use = so argparse receives -inf as the value, exercising our validation.
    monkeypatch.setattr(sys,'argv',['collector','--symbol','IWM','--show','--delay='+delay])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    show.assert_not_called()


@pytest.mark.parametrize('delay,expected',[(None,0.4),('0.4',0.4),('1',1.0),('60',60.0)])
def test_actual_parser_keeps_explicit_local_batch_for_default_or_slower_delay(client,monkeypatch,delay,expected):
    _,mod = client()
    show=Mock()
    monkeypatch.setattr(mod,'show_parquet_data',show)
    argv=['collector','--symbol','IWM','--show']
    if delay is not None:argv += ['--delay',delay]
    monkeypatch.setattr(sys,'argv',argv)
    mod.main()
    show.assert_called_once()
    assert mod.DELAY_BETWEEN_CALLS == pytest.approx(expected)
    assert mod.CALLS_PER_MINUTE == 150
    assert mod._av_cfg.rpm == 600


def test_actual_batch_loop_uses_local_allocation_not_account_ceiling(client,monkeypatch,tmp_path):
    kind,mod = client(AlphaVantageConfig(local_rpm=3))
    monkeypatch.chdir(tmp_path)
    sleeps=[];calls=[]
    monkeypatch.setattr(mod,'time',SimpleNamespace(time=lambda:0.0,sleep=sleeps.append))
    if kind=='intraday':
        monkeypatch.setattr(mod,'get_trading_months',lambda *a:['2026-01','2026-02','2026-03'])
        monkeypatch.setattr(mod,'fetch_intraday_month',lambda *a,**k:calls.append(a) or None)
        monkeypatch.setattr(mod,'is_month_all_non_trading_days',lambda *a:True)
        mod.fetch_historical_intraday('IWM',start_date='2026-01-01',end_date='2026-03-31')
    else:
        monkeypatch.setattr(mod,'get_trading_days',lambda *a,**k:[date(2026,1,2),date(2026,1,5),date(2026,1,6)])
        monkeypatch.setattr(mod,'fetch_options_chain',lambda *a,**k:calls.append(a) or None)
        monkeypatch.setattr(mod,'is_trading_day',lambda *a:False)
        mod.fetch_historical_options('IWM',start_date='2026-01-02',end_date='2026-01-06')
    assert len(calls)==3
    assert mod.CALLS_PER_MINUTE==3
    assert sleeps == [20.0,20.0,60.0]


@pytest.mark.parametrize('field,sleep,terminal', [('Error Message',[],False),('Note',[60],False),('Information',[],True)])
def test_existing_provider_error_backoff_and_exhaustion_decisions_unchanged(client,monkeypatch,field,sleep,terminal):
    kind,mod=client()
    sleeps=[];calls=[]
    monkeypatch.setattr(mod,'time',SimpleNamespace(sleep=sleeps.append))
    response=SimpleNamespace(raise_for_status=lambda:None,json=lambda:{field:'synthetic test notice'})
    monkeypatch.setattr(mod.requests,'get',lambda *a,**k:calls.append((a,k)) or response)
    fn=mod.fetch_intraday_month if kind=='intraday' else mod.fetch_options_chain
    if terminal:
        with pytest.raises(SystemExit) as exc:fn('IWM','2026-01')
        assert exc.value.code==1
    else:
        assert fn('IWM','2026-01') is None
    assert len(calls)==1
    assert sleeps==sleep
