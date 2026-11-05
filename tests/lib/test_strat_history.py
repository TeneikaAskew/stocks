"""Tests for the Strat history tape + 1-3-1 detection + upcoming setup.

Hermetic — synthetic OHLCV, no DB.
"""
import numpy as np
import pandas as pd
import pytest

from lib.strat import (
    StratClassifier, compute_strat_history, _upcoming_setup, _last_directional,
)


def _frame(bars):
    df = pd.DataFrame(bars, columns=['High', 'Low', 'Open', 'Close'])
    df['Volume'] = 1000
    return df


def _daily_frame(bars, start='2024-01-01'):
    df = _frame(bars)
    df.index = pd.date_range(start, periods=len(bars), freq='B')
    return df


class TestOneThreeOne:
    def test_131_detected(self):
        clf = StratClassifier()
        df = _frame([
            (100, 90, 95, 96),
            (99, 91, 95, 96),    # 1
            (100, 90, 95, 96),   # 3
            (99, 91, 95, 96),    # 1
        ])
        res = clf.detect_combos(df)
        assert res['strat_candle'].tolist() == ['X', '1', '3', '1']
        assert res['strat_combo'].iloc[3] == '131_setup'
        assert bool(res['strat_setup'].iloc[3]) is True
        assert bool(res['pending_setup'].iloc[3]) is True
        assert res['pattern_facts'].iloc[3] == ['131_setup']

    def test_131_requires_outside_middle(self):
        clf = StratClassifier()
        df = _frame([
            (100, 90, 95, 96), (99, 91, 95, 96), (98, 92, 95, 96), (97, 93, 95, 96),
        ])
        res = clf.detect_combos(df)
        assert res['strat_combo'].iloc[3] != '131_setup'
        assert 'inside_compression' in res['strat_combo'].iloc[3]


class TestUpcomingSetup:
    def test_unknown_breaks_directional_context(self):
        assert _last_directional(pd.Series(['X', '2U', 'X', '1'])) is None

    def test_invalid_latest_bar_is_explicitly_unavailable(self):
        df = _frame([(100, 90, 95, 96), (None, None, None, None)])
        clf = StratClassifier()
        labels = clf.classify_series(df)
        up = _upcoming_setup(df, labels, clf.detect_combos(df, labels))
        assert up['available'] is False
        assert up['reason'] == 'invalid latest OHLC'
        assert up['trigger_high'] is None and up['trigger_low'] is None

    def test_trigger_lines_and_mid(self):
        clf = StratClassifier()
        df = _frame([(100, 90, 95, 96), (102, 92, 95, 101)])
        labels = clf.classify_series(df)
        up = _upcoming_setup(df, labels, clf.detect_combos(df, labels))
        assert up['trigger_high'] == 102.0 and up['trigger_low'] == 92.0
        assert up['mid_trigger'] == pytest.approx(97.0)

    def test_direction_read_after_2d(self):
        assert _last_directional(pd.Series(['X', '2U', '2D'])) == '2D'
        df = _frame([(100, 90, 95, 96), (101, 91, 95, 100), (99, 88, 95, 89)])
        clf = StratClassifier()
        lab = clf.classify_series(df)
        up = _upcoming_setup(df, lab, clf.detect_combos(df, lab))
        assert up['break_up'] == '2U reversal'
        assert up['break_down'] == '2D continuation'


class TestComputeStratHistory:
    @pytest.mark.parametrize('bad_value', ['bad vendor value', np.inf])
    def test_invalid_history_price_is_null_and_cannot_be_upcoming_trigger(self, bad_value):
        df = _daily_frame([(100, 90, 95, 96), (101, 91, 95, 100)]).astype(object)
        df.loc[df.index[-1], 'High'] = bad_value
        block = compute_strat_history('TEST', df=df, timeframes=['1d'])['timeframes']['1d']
        assert block['current']['candle'] == 'X'
        assert block['current']['high'] is None
        assert block['upcoming']['available'] is False
        assert block['upcoming']['trigger_high'] is None

    def test_invalid_daily_row_does_not_bridge_directional_history(self):
        df = _daily_frame([(100, 90, 95, 96), (101, 91, 95, 100),
                           (np.nan, np.nan, np.nan, np.nan), (102, 92, 95, 101)])
        records = compute_strat_history('TEST', df=df, timeframes=['1d'])['timeframes']['1d']['history']
        assert len(records) == 4
        assert [record['candle'] for record in records] == ['X', '2U', 'X', 'X']
        assert records[-1]['combo'] == 'none'

    @pytest.fixture
    def daily(self):
        rng = np.random.default_rng(7)
        n = 260
        close = 100 + np.cumsum(rng.normal(0, 1, n))
        high = close + rng.uniform(0.5, 2.0, n)
        low = close - rng.uniform(0.5, 2.0, n)
        openp = close + rng.normal(0, 0.5, n)
        # This fixture exercises available history; keep its synthetic opens
        # inside H/L. Malformed vendor observations have dedicated cases above.
        high = np.maximum(high, openp)
        low = np.minimum(low, openp)
        return _daily_frame(list(zip(high, low, openp, close)))

    def test_structure_all_timeframes(self, daily):
        res = compute_strat_history('TEST', df=daily, lookback=10)
        assert res['available'] is True and res['ticker'] == 'TEST'
        for tf in ('1d', '1w', '1mo', '1q'):
            assert tf in res['timeframes']
            block = res['timeframes'][tf]
            assert block['available'] is True
            assert 1 <= len(block['history']) <= 10
            rec = block['history'][-1]
            for k in ('period', 'open', 'high', 'low', 'close', 'candle', 'combo',
                      'is_continuation', 'is_reversal', 'is_inside', 'is_setup',
                      'trigger_high', 'trigger_low'):
                assert k in rec
            assert rec['candle'] in ('1', '2U', '2D', '3', 'X')
            up = block['upcoming']
            assert up['trigger_high'] is not None and up['trigger_low'] is not None
            assert up['break_up'].startswith('2U') and up['break_down'].startswith('2D')
        assert res['timeframes']['1d']['current'] == res['timeframes']['1d']['history'][-1]

    def test_quarterly_fewer_than_daily(self, daily):
        res = compute_strat_history('TEST', df=daily, lookback=999)
        assert len(res['timeframes']['1q']['history']) < len(res['timeframes']['1d']['history'])

    def test_insufficient_data(self):
        res = compute_strat_history('TEST', df=_daily_frame([(1, 0, 0.5, 0.5)]))
        assert res['available'] is False

    def test_flags_consistent(self, daily):
        res = compute_strat_history('TEST', df=daily, lookback=999)
        for blk in res['timeframes'].values():
            for rec in blk['history']:
                assert rec['is_continuation'] == ('continuation' in rec['combo'])
                assert rec['is_reversal'] == ('reversal' in rec['combo'])
                assert rec['is_inside'] == (rec['candle'] == '1')


class TestHistoryObservationContract:
    @staticmethod
    def observed():
        df = _daily_frame([(100,90,95,96),(101,91,95,100),
                           (np.nan,np.nan,np.nan,np.nan),(102,92,95,101),
                           (1000,900,950,999)], start='2026-04-13')
        df.attrs.update(price_basis='synthetic_coherent',source_resolution='1d',
                        timestamp_semantics='session_label',session_policy='NYSE_regular')
        return df

    @staticmethod
    def contract(**overrides):
        return dict(as_of=pd.Timestamp('2026-04-16 17:00',tz='America/New_York'),
                    price_basis='synthetic_coherent',rule_version='strat-state-v2',
                    input_identity={'source_revision':'synthetic-v1','artifact_id':'synthetic-fixture',
                                    'input_sha256':None}, **overrides)

    def test_aware_cutoff_and_invalid_middle_survive_actual_history(self):
        result=compute_strat_history('TEST',df=self.observed(),timeframes=['1d','1w'],**self.contract())
        hist=result['timeframes']['1d']['history']
        assert [row['candle'] for row in hist] == ['X','2U','X','X']
        assert hist[-1]['combo'] == 'none'
        assert hist[-1]['trigger_high'] is None and hist[-1]['trigger_low'] is None
        assert result['timeframes']['1w']['available'] is False
        assert result['rule_version'] == 'strat-state-v2'
        assert result['observation_ts'] == '2026-04-16T17:00:00-04:00'
        assert result['identity']['price_basis'] == 'synthetic_coherent'
        assert len(result['identity']['input_sha256']) == 64
        assert result['source_acquisition_status'] == 'unknown'
        assert result['current_action_available'] is False

    def test_future_extrema_excluded_before_weekly_aggregation(self):
        df=self.observed().drop(index=self.observed().index[2])
        prior=df.copy();prior.index=prior.index-pd.Timedelta(weeks=1)
        frame=pd.concat([prior.iloc[:-1],df]);frame.attrs=df.attrs.copy()
        res=compute_strat_history('TEST',df=frame,timeframes=['1w'],**self.contract())
        assert res['timeframes']['1w']['current']['high'] == 102

    @pytest.mark.parametrize('override',[
        {'as_of':'2026-04-16'}, {'as_of':pd.Timestamp('2026-04-16 17:00')},
        {'rule_version':'unknown'}, {'price_basis':'mixed'}, {'input_identity':{}},
        {'input_identity':{'source_revision':'synthetic-v1','artifact_id':'fixture','price_basis':'raw'}},
    ])
    def test_bad_contract_refused_before_loader_construction(self,monkeypatch,override):
        from lib.data_loader import DataLoader
        def denied(*a,**kw):
            pytest.fail('invalid contract reached DataLoader')
        monkeypatch.setattr(DataLoader,'__init__',denied)
        args=self.contract();args.update(override)
        with pytest.raises(ValueError):
            compute_strat_history('TEST',df=self.observed(),**args)

    def test_actual_source_basis_unavailable_before_loader(self,monkeypatch):
        from lib.data_loader import DataLoader
        monkeypatch.setattr(DataLoader,'__init__',lambda *a,**k:pytest.fail('unqualified source load'))
        args=self.contract();args['price_basis']='av-adjusted-daily-v1'
        with pytest.raises(ValueError,match='basis.*unavailable'):
            compute_strat_history('TEST',**args)

    def test_no_contract_is_descriptive_and_never_comparable(self,monkeypatch):
        result=compute_strat_history('TEST',df=self.observed(),timeframes=['1d'])
        assert result['qualification'] == 'descriptive_unverified'
        assert result['comparison_available'] is False
        assert result['observation_ts'] is None and result['identity'] is None
        # The existing report/backtest CLIs keep loading source without a contract,
        # but their output stays unverified: no clock, identity or comparison.
        from lib.data_loader import DataLoader
        monkeypatch.setattr(DataLoader,'load_daily',lambda self,ticker,**k:self_frame)
        self_frame=self.observed()
        loaded=compute_strat_history('TEST',timeframes=['1d'])
        assert loaded['comparison_available'] is False and loaded['identity'] is None
        # One contract argument without the rest refuses before any loader exists.
        monkeypatch.setattr(DataLoader,'__init__',lambda *a,**k:pytest.fail('unadmitted source load'))
        with pytest.raises(ValueError):
            compute_strat_history('TEST',rule_version='strat-state-v2')

    def test_mixed_frame_basis_and_content_claim_refused(self):
        frame=self.observed();frame.attrs['price_basis']='raw'
        with pytest.raises(ValueError,match='basis'):
            compute_strat_history('TEST',df=frame,**self.contract())
        args=self.contract();args['input_identity']['input_sha256']='0'*64
        with pytest.raises(ValueError,match='input.*hash'):
            compute_strat_history('TEST',df=self.observed(),**args)

    def test_missing_session_cannot_bridge_history_trigger_or_pattern(self):
        frame=self.observed().drop(index=self.observed().index[2])
        result=compute_strat_history('TEST',df=frame,timeframes=['1d'],**self.contract())
        record=result['timeframes']['1d']['current']
        assert record['candle']=='X' and record['combo']=='none'
        assert record['trigger_high'] is None and record['trigger_low'] is None
        assert 'missing_previous_observation' in record['bar_validity']['reasons']

    def test_explicit_history_exposes_coverage_and_invalid_reasons(self):
        res=compute_strat_history('TEST',df=self.observed(),timeframes=['1d'],**self.contract())
        block=res['timeframes']['1d']
        assert block['history'][2]['bar_validity']['valid'] is False
        assert 'invalid_ohlc' in block['history'][2]['bar_validity']['reasons']
        assert block['history'][2]['pattern_facts']==[]
        assert 'coverage' in block
        assert res['data_as_of']=='2026-04-16T16:00:00-04:00'

    def test_live_none_resolves_one_aware_clock_and_matches_explicit(self,monkeypatch):
        import lib.strat as strat
        clock=pd.Timestamp('2026-04-16 17:00',tz='America/New_York');seen=[]
        def now():seen.append(1);return clock
        monkeypatch.setattr(strat,'eastern_now',now)
        args=self.contract();args['as_of']=None
        live=compute_strat_history('TEST',df=self.observed(),timeframes=['1d'],**args)
        assert seen==[1]
        replay=compute_strat_history('TEST',df=self.observed(),timeframes=['1d'],**self.contract())
        assert live==replay

    def test_plain_history_digest_keeps_pre_fix_literal(self):
        result=compute_strat_history('TEST',df=self.observed().iloc[:2].astype(int),timeframes=['1d'],**self.contract())
        assert result['identity']['input_sha256']=='c43ef9b5613e984971c166e3f1cb323a3ce70523133ca8a7c424fdf85780fdc5'

    @pytest.mark.parametrize('shape',['normalized','aware','python_datetime','date','numpy_datetime'])
    def test_timestamp_content_is_admitted_stable_and_verified(self,shape):
        from lib.data_loader import DataLoader
        frame=DataLoader().normalize_columns(self.observed().iloc[:2])
        if shape!='normalized':
            stamps=[pd.Timestamp('2026-04-13T09:30:00.123456789-04:00'),
                    pd.Timestamp('2026-04-14T09:30:00.123456789-04:00')]
            if shape=='python_datetime':stamps=[s.floor('us').to_pydatetime() for s in stamps]
            elif shape=='date':stamps=[s.date() for s in stamps]
            elif shape=='numpy_datetime':stamps=[np.datetime64('2026-04-13T09:30:00.123456789'),np.datetime64('2026-04-14T09:30:00.123456789')]
            frame['Time']=pd.Series(stamps,index=frame.index,dtype=object)
        def history(value,**overrides):
            args=self.contract();args.update(overrides)
            return compute_strat_history('TEST',df=value,timeframes=['1d'],**args)
        result=history(frame)
        assert result['available'] and result['timeframes']['1d']['current']['candle']=='2U'
        digest=result['identity']['input_sha256']
        assert digest==history(frame.copy())['identity']['input_sha256']
        assert digest!='c43ef9b5613e984971c166e3f1cb323a3ce70523133ca8a7c424fdf85780fdc5'
        # Time content participates independently of the daily session index.
        changed=frame.copy()
        changed.loc[changed.index[0],'Time']=frame['Time'].iloc[1]
        assert history(changed)['identity']['input_sha256']!=digest
        claim={'source_revision':'synthetic-v1','artifact_id':'synthetic-fixture','input_sha256':digest}
        assert history(frame,input_identity=claim)['identity']['input_sha256']==digest
        with pytest.raises(ValueError,match='input content hash'):
            history(changed,input_identity=claim)

    def test_timestamp_digest_preserves_naive_aware_offset_and_string_distinctions(self):
        frame=self.observed().iloc[:2].copy();digests=[]
        for value in [pd.Timestamp('2026-04-13T09:30:00'),
                      pd.Timestamp('2026-04-13T09:30:00-04:00'),
                      pd.Timestamp('2026-04-13T13:30:00+00:00'),
                      '2026-04-13T09:30:00']:
            frame['Time']=pd.Series([value,value],index=frame.index,dtype=object)
            result=compute_strat_history('TEST',df=frame,timeframes=['1d'],**self.contract())
            digests.append(result['identity']['input_sha256'])
        assert len(set(digests))==4

    def test_history_digest_rejects_arbitrary_objects_instead_of_repr(self):
        frame=self.observed().iloc[:2].copy()
        frame['unsupported']=[object(),object()]
        with pytest.raises(TypeError):
            compute_strat_history('TEST',df=frame,timeframes=['1d'],**self.contract())


class TestHistoryReportContinuation:
    """r4481033984 on #1714: an unknown (NULL-OHLC placeholder) successor is
    pending, not a failed continuation."""

    def test_unknown_successor_is_not_scored(self):
        from scripts.strat_history_report import _continuation
        hist = [{'candle': '1'}, {'candle': '2U'}, {'candle': 'X'}]
        assert _continuation(hist, 0) == (0, 0)

    def test_known_successors_are_scored(self):
        from scripts.strat_history_report import _continuation
        hist = [{'candle': '2U'}, {'candle': '2U'}, {'candle': '2D'}, {'candle': '1'}]
        assert _continuation(hist, 0) == (1, 3)
