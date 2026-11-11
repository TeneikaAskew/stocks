"""Direct execution FTFC goldens: bucket grid, completed shift and legacy weights."""
import numpy as np
import pandas as pd
import pytest
from lib.exec_backtest.ftfc import build_ftfc_lookup, ftfc_score_at, ftfc_scores_for_setups, _classify


class TestLegacyFtfcGolden:
    @staticmethod
    def tape():
        index = pd.date_range('2026-01-05 14:00', periods=601, freq='min', tz='UTC')
        values = 100 + np.arange(len(index)) / 100
        return pd.DataFrame({'Open':values,'High':values+.02,'Low':values-.02,
                             'Close':values+.01}, index=index)

    @pytest.mark.parametrize('tf,first,second', [
        ('5m','14:05','14:10'), ('15m','14:15','14:30'),
        ('30m','14:30','15:00'), ('60m','15:00','16:00'), ('4h','16:00','20:00')])
    def test_each_configured_frame_retains_literal_completed_shift(self, tf, first, second):
        lookup = build_ftfc_lookup(self.tape(), (tf,))
        first = pd.Timestamp('2026-01-05 '+first, tz='UTC')
        second = pd.Timestamp('2026-01-05 '+second, tz='UTC')
        assert np.isnan(lookup.iloc[0][tf])
        assert lookup.loc[first,tf] == 0.
        assert lookup.loc[second-pd.Timedelta(minutes=1),tf] == 0.
        assert lookup.loc[second,tf] == 1.

    def test_hour_alias_and_exact_weight_keys(self):
        lookup = pd.DataFrame({'60m':[1.], '1h':[-1.], '15m':[-1.], '30m':[0.], '4h':[1.]},
                              index=pd.to_datetime(['2026-01-05 20:00Z']))
        assert ftfc_score_at(lookup,lookup.index[0]) == pytest.approx(-0.058823529411764705)
        assert ftfc_score_at(lookup,lookup.index[0], {'60m':.3,'1h':.1}) == pytest.approx(.5)

    def test_nan_missing_denominator_and_between_bar_lookup(self):
        lookup = pd.DataFrame({'15m':[np.nan,1.,-1.], '30m':[np.nan,0.,1.],
                               '60m':[np.nan,np.nan,1.]},
                              index=pd.date_range('2026-01-05 15:00',periods=3,freq='min',tz='UTC'))
        times = pd.to_datetime(['2026-01-05 14:59Z','2026-01-05 15:00Z',
                                '2026-01-05 15:01:30Z','2026-01-05 15:02Z'], format='mixed')
        expected = [np.nan,np.nan,.5,.2]
        np.testing.assert_allclose([ftfc_score_at(lookup,t) for t in times],expected,equal_nan=True)
        np.testing.assert_allclose(ftfc_scores_for_setups(lookup,times),expected,equal_nan=True)
        assert np.isnan(ftfc_score_at(lookup,times[-1], {}))

    def test_changes_in_unfinished_bar_do_not_change_earlier_lookup(self):
        tape = self.tape()
        before = build_ftfc_lookup(tape, ('15m',))
        tape.loc['2026-01-05 14:40Z', ['Open','High','Low','Close']] = [300,301,299,300]
        after = build_ftfc_lookup(tape, ('15m',))
        pd.testing.assert_frame_equal(before.loc[:'2026-01-05 14:44Z'],after.loc[:'2026-01-05 14:44Z'])


class TestSharedFtfcClassification:
    def test_invalid_bar_and_next_comparison_stay_unknown(self):
        values = pd.DataFrame({'Open':[95,200,97,98], 'High':[100,101,102,103],
                               'Low':[90,91,92,93], 'Close':[96,97,98,99]})
        result = _classify(values.Open,values.High,values.Low,values.Close)
        np.testing.assert_allclose(result,[0,np.nan,np.nan,1],equal_nan=True)

    def test_lookup_declares_legacy_grid_and_shared_validity_version(self):
        result = build_ftfc_lookup(TestLegacyFtfcGolden.tape())
        assert result.attrs['aggregation_policy'] == 'legacy_v1'
        assert result.attrs['classification_version'] == 'shared-valid-bars-v2'
        assert result.attrs['alignment_version'] == 'legacy-candle-v1'

    def test_invalid_constituent_cannot_be_hidden_by_aggregate_extrema(self):
        tape = TestLegacyFtfcGolden.tape()
        # Invalid source O is interior to the aggregated range; raw max/min
        # alone would conceal the invalid observation and produce a bullish vote.
        tape.loc['2026-01-05 14:17Z','Open'] = 100.25
        result = build_ftfc_lookup(tape, ('15m',))
        assert np.isnan(result.loc['2026-01-05 14:30Z','15m'])
        assert np.isnan(result.loc['2026-01-05 14:45Z','15m'])
        assert result.loc['2026-01-05 15:00Z','15m'] == 1.

    @pytest.mark.parametrize('bars,expected', [
        ([(100,90,95,96),(101,91,95,96),(101,90,95,96),(102,89,95,96)], [0,1,-1,0]),
        ([(100,90,95,96),(99,91,95,96),(99,90,95,96),(99,90,95,96)], [0,0,-1,0]),
    ])
    def test_shared_classifier_retains_valid_literal_votes(self,bars,expected):
        frame = pd.DataFrame(bars,columns=['High','Low','Open','Close'])
        np.testing.assert_allclose(_classify(frame.Open,frame.High,frame.Low,frame.Close),expected)

    def test_overnight_empty_legacy_bins_keep_literal_prior_completed_vote(self):
        first = TestLegacyFtfcGolden.tape().iloc[:31]
        second = first.copy()
        second.index += pd.Timedelta(days=1)
        second += 1
        tape = pd.concat([first,second])
        result = build_ftfc_lookup(tape, ('15m',))
        np.testing.assert_allclose(result.iloc[[0,15,30,31,46,61],0],
                                   [np.nan,0,1,1,1,1],equal_nan=True)
