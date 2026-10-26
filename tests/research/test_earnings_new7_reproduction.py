"""Synthetic validation only; no market sample rerun or private input access."""
from decimal import Decimal as D
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]/'tools/research/earnings_new7'

def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def article(clock,score,url,title='Synthetic control'):
    return {'time_published':clock,'url':url,'title':title,
            'ticker_sentiment':[{'ticker':'SYNTH','ticker_sentiment_score':score}]}


def test_fixed_window_endpoints_target_mapping_and_deterministic_dedup():
    rules=module('frozen_news_rules')
    event={'ticker':'SYNTH','release_at':'2026-07-14T10:00:00+00:00'}
    feed=[article('20260712T100000','0.4','https://example.test/a?utm_source=x'),
          article('20260713T100000','0.9','https://example.test/a'),
          article('20260714T095959','-0.2','https://example.test/b','Another control'),
          article('20260714T100000','1','https://example.test/c','Released now')]
    result,_,clusters=rules.analyze_event(event,{'items':'4','feed':feed},'success')
    assert result['window_statistics']['full']['numeric_story_count']==2
    assert D(result['window_statistics']['full']['provider_recorded_exploratory_mean'])==D('.1')
    assert result['window_statistics']['older']['numeric_story_count']==1
    assert result['window_statistics']['recent']['numeric_story_count']==1
    assert any(c['cross_24h_boundary_duplicate'] for c in clusters)
    assert result['runtime_vintage_qualified'] is False
    assert result['window_statistics']['full']['independently_verified_primary_mean'] is None


def test_empty_failed_capped_and_missing_target_are_separate():
    r=module('frozen_news_rules');ev={'ticker':'SYNTH','release_at':'2026-07-14T10:00:00+00:00'}
    assert r.analyze_event(ev,{'feed':[]},'success')[0]['coverage']==['valid_empty_provider_window']
    assert r.analyze_event(ev,None,'failure')[0]['coverage']==['request_failed']
    a=article('20260714T090000','.5','https://example.test/x');a['ticker_sentiment'][0]['ticker']='OTHER'
    result,_,_=r.analyze_event(ev,{'items':'2','feed':[a]},'success')
    assert 'partial_or_capped' in result['coverage']
    assert result['window_statistics']['full']['numeric_story_count']==0
    assert result['window_statistics']['full']['provider_recorded_exploratory_mean'] is None


def test_spearman_ties_independently_hand_calculated_and_no_ten_sample_runner():
    r=module('frozen_rank_rules')
    assert r.average_ranks([D(2),D(1),D(1)])==[D(3),D('1.5'),D('1.5')]
    assert D(r.spearman([D(1),D(2),D(3)],[D(3),D(1),D(2)])['rho_decimal50'])==D('-.5')
    assert not hasattr(r,'run')


def test_adaptation_hashes_and_cli_need_explicit_private_inputs():
    identities=json.loads((ROOT/'source-identities.json').read_text())
    for item in identities['scripts']:
        assert hashlib.sha256((ROOT/item['file']).read_bytes()).hexdigest()==item['adapted_sha256']
    for name in ('analyze_news_once.py','join_and_describe_once.py','render_delivery.py'):
        run=subprocess.run([sys.executable,str(ROOT/name),'--help'],capture_output=True,text=True,timeout=20)
        assert run.returncode==0 and '--input-root' in run.stdout


def test_seven_ticker_guard_refuses_legacy_ten_before_inputs():
    import pytest
    rules=module('research_io')
    protocol=json.loads((ROOT/'protocol.json').read_text())
    assert rules.check_new7_protocol(protocol) is protocol
    with pytest.raises(ValueError):rules.check_new7_protocol({'order':['OLD']*10,'events':[]})
