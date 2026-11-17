"""FEAT-PLAYBOOK-001 B4 and B5: what the overview model is sent, and the check on what it says.

The tests read the pure functions; no model, network or database is called.
"""
import re

import pytest

from gcp import brief_explanations as be
from lib.config import StratConfig
from lib.strat import StratClassifier
from tests.gcp.test_strat_snapshot_parity import _brief, _daily, no_network  # noqa: F401


def _iwm(**over):
    """IWM as the 2026-11-16 brief stored it (spec Problem 2)."""
    d = {'price': 276.30, 'rsi': 44.0, 'ftfc_score': -0.30 / 0.40, 'ftfc_direction': 'bearish',
         'ftfc_labels': {'1d': '2D', '1w': '1', '1mo': '2U'}, 'macd_cross': 'Bullish'}
    d.update(over)
    return d


def _line(text, ticker):
    return next(line for line in text.split('\n') if line.startswith(f'{ticker}:'))


def test_user_text_holds_each_candle_with_its_meaning():
    line = _line(be.overview_user_text({'IWM': _iwm()}), 'IWM')
    assert 'daily 2D (down)' in line
    assert 'weekly 1 (inside and neutral)' in line
    assert 'monthly 2U (up)' in line
    assert 'MACD cross Bullish' in line
    assert 'TF bias -0.75 (bearish)' in line


def test_default_weights_are_read_not_typed(monkeypatch):
    prompt = be.overview_system_prompt(StratClassifier().ftfc_weights)
    assert 'daily 0.30' in prompt
    assert 'weekly 0.10' in prompt
    assert 'monthly none' in prompt
    # The number is not in the prompt's source: change the weight, the text follows.
    monkeypatch.setitem(StratClassifier.DEFAULT_WEIGHTS, '1d', 0.25)
    prompt = be.overview_system_prompt(StratClassifier().ftfc_weights)
    assert 'daily 0.25' in prompt
    assert 'daily 0.30' not in prompt


def test_configured_monthly_weight_is_named():
    weights = StratClassifier(strat_config=StratConfig(
        ftfc_weights={'1d': 0.30, '1w': 0.10, '1mo': 0.20})).ftfc_weights
    prompt = be.overview_system_prompt(weights)
    assert 'monthly 0.20' in prompt
    assert 'monthly none' not in prompt


def test_prompt_says_inside_and_outside_add_nothing():
    prompt = be.overview_system_prompt(StratClassifier().ftfc_weights)
    assert 'an inside (1) or outside (3) bar adds nothing to the score' in prompt
    assert "The score's sign is not a statement about any one timeframe" in prompt
    assert 'a weighted vote of daily and weekly candle types' not in prompt


def test_prompt_says_the_score_is_divided_by_the_weights():
    # calculate_ftfc divides by the summed weights (lib/strat.py:502): daily 2D
    # at 0.30 with weekly 1 at 0.10 is -0.30 / 0.40 = -0.75, not -0.30.
    prompt = be.overview_system_prompt(StratClassifier().ftfc_weights)
    assert ('The score is that sum divided by the total weight of every '
            'timeframe that has a weight, inside and outside bars included') in prompt
    assert "adds its timeframe's weight to the score" not in prompt


def test_missing_labels_are_unavailable():
    d = _iwm()
    del d['ftfc_labels']
    line = _line(be.overview_user_text({'IWM': d}), 'IWM')
    assert 'candles unavailable' in line
    for label in ('2U', '2D', 'inside', 'outside'):
        assert label not in line
    line = _line(be.overview_user_text({'IWM': _iwm(ftfc_labels={'1d': '2D'})}), 'IWM')
    assert 'daily 2D (down)' in line
    assert 'weekly unavailable' in line
    assert 'monthly unavailable' in line


def test_weights_unknown_is_said():
    prompt = be.overview_system_prompt(None)
    assert 'weights unavailable' in prompt
    # No weight is printed: the only digits left are candle names (2U, 2D, 1, 3).
    assert not re.search(r'\d\.\d', prompt)
    assert 'none' not in prompt


def test_user_text_is_none_when_no_ticker_has_data():
    assert be.overview_user_text({'IWM': {'status': 'NO DATA'}}) is None
    assert be.overview_user_text({}) is None


def test_weights_property_is_a_copy():
    classifier = StratClassifier()
    weights = classifier.ftfc_weights
    weights['1d'] = 9.0
    assert classifier.ftfc_weights['1d'] == StratClassifier.DEFAULT_WEIGHTS['1d']


def test_explain_overview_sends_the_prompt_built_from_the_weights(monkeypatch):
    import asyncio
    seen = []

    async def fake_call(system, user):
        seen.append((system, user))
        return 'Volume was light into the close.'
    monkeypatch.setattr(be, '_call', fake_call)
    weights = {'1d': 0.30, '1w': 0.10, '1mo': 0.20}
    asyncio.run(be.explain_overview_setup({'IWM': _iwm()}, weights))
    system, user = seen[0]
    assert system == be.overview_system_prompt(weights)
    assert be.overview_user_text({'IWM': _iwm()}) in user


def test_brief_carries_the_weights(monkeypatch, no_network):  # noqa: F811
    pb, cfg = _brief(monkeypatch, _daily())
    cfg.strat.ftfc_weights = {'1d': 0.30, '1w': 0.10, '1mo': 0.20}
    brief = pb.generate_premarket_brief(cfg=cfg)
    assert brief['ftfc_weights'] == StratClassifier(strat_config=cfg.strat).ftfc_weights
    assert brief['ftfc_weights'] == {'1d': 0.30, '1w': 0.10, '1mo': 0.20}


def _three(daily=('2D', '2D', '2D'), weekly=('1', '1', '1'), monthly=('2D', '2D', '2U')):
    """SPY, QQQ and IWM, in that order, with the labels given per timeframe."""
    return {name: _iwm(ftfc_labels={'1d': d, '1w': w, '1mo': m})
            for name, d, w, m in zip(('SPY', 'QQQ', 'IWM'), daily, weekly, monthly)}


BEARISH_BOTH = 'strong bearish alignment on the daily and weekly'


class TestOverviewCheck:
    """B5: a claim about a timeframe must hold for every ticker it describes."""

    def test_weekly_claim_against_inside_bars_is_a_conflict(self):
        conflicts = be.overview_conflicts(BEARISH_BOTH, _three())
        assert len(conflicts) == 1
        assert conflicts[0]['timeframe'] == 'weekly'
        assert conflicts[0]['claim'] == '2D'
        assert conflicts[0]['tickers'] == ['IWM', 'QQQ', 'SPY']
        assert conflicts[0]['clause'] == BEARISH_BOTH

    def test_the_same_sentence_with_every_weekly_down_is_none(self):
        assert be.overview_conflicts(BEARISH_BOTH, _three(weekly=('2D', '2D', '2D'))) == []

    def test_monthly_bullish_with_no_up_monthly_is_a_conflict(self):
        conflicts = be.overview_conflicts('the monthly is bullish',
                                          _three(monthly=('2D', '2D', '1')))
        assert [c['timeframe'] for c in conflicts] == ['monthly']
        assert conflicts[0]['claim'] == '2U'

    def test_text_naming_no_timeframe_is_none(self):
        assert be.overview_conflicts('Volume was light into the close.', _three()) == []

    def test_all_three_names_must_each_hold_the_claim(self):
        text = 'all three names are bearish on the weekly'
        conflicts = be.overview_conflicts(text, _three(weekly=('2D', '1', '1')))
        assert len(conflicts) == 1
        assert conflicts[0]['tickers'] == ['IWM', 'QQQ']
        assert be.overview_conflicts(text, _three(weekly=('2D', '2D', '2D'))) == []

    def test_named_tickers_are_the_ones_described(self):
        conflicts = be.overview_conflicts('SPY and QQQ are bearish on the daily',
                                          _three(daily=('2D', '2U', '2U')))
        assert len(conflicts) == 1
        assert conflicts[0]['tickers'] == ['QQQ']

    def test_one_of_needs_one(self):
        text = 'one of the three is bearish on the weekly'
        assert be.overview_conflicts(text, _three(weekly=('2D', '1', '1'))) == []
        conflicts = be.overview_conflicts(text, _three(weekly=('1', '1', '2U')))
        assert [c['timeframe'] for c in conflicts] == ['weekly']

    @pytest.mark.parametrize('text', ['SPY, QQQ and IWM are bearish on the weekly',
                                      'SPY, QQQ, and IWM are bearish on the weekly'])
    def test_a_comma_inside_a_ticker_list_is_not_a_boundary(self, text):
        conflicts = be.overview_conflicts(text, _three(weekly=('1', '2D', '2D')))
        assert len(conflicts) == 1
        assert conflicts[0]['tickers'] == ['SPY']
        assert be.overview_conflicts(text, _three(weekly=('2D', '2D', '2D'))) == []

    def test_a_comma_between_two_statements_is_still_a_boundary(self):
        text = 'SPY is bearish on the weekly, QQQ is bullish'
        assert be.overview_conflicts(text, _three(weekly=('2D', '2U', '1'))) == []

    @pytest.mark.parametrize('text', [
        'SPY is above its monthly open with bullish FTFC.',
        'IWM holds bullish continuity above the monthly open.',
        'QQQ trades below its weekly opens, a bearish FTFC state.',
    ])
    def test_a_price_versus_open_statement_is_not_a_candle_claim(self, text):
        # FTFC is price against the period opens, not the candle type: the
        # monthly candle can be inside (1) with price above the monthly open.
        tickers = _three(weekly=('1', '1', '1'), monthly=('1', '1', '1'))
        assert be.overview_conflicts(text, tickers) == []

    def test_a_candle_claim_beside_ftfc_words_is_still_checked(self):
        tickers = _three(monthly=('1', '1', '1'))
        found = be.overview_conflicts(
            'The monthly candle is bullish with bullish FTFC.', tickers)
        assert [c['timeframe'] for c in found] == ['monthly']

    @pytest.mark.parametrize('text', [
        'IWM has a down daily candle and an inside weekly bar.',
        'IWM shows an inside weekly candle alongside a bullish MACD cross.',
        'The weekly is inside while RSI turns higher.',
        'IWM is bearish on the daily with a neutral weekly.',
        'TF bias is bearish with the weekly inside.',
    ])
    def test_a_direction_word_is_bound_to_what_it_describes(self, text):
        # IWM: daily 2D, weekly 1, monthly 2U. Each sentence is accurate.
        assert be.overview_conflicts(text, {'IWM': _iwm()}) == []

    def test_a_bound_claim_is_still_checked(self):
        found = be.overview_conflicts(
            'IWM has an up daily candle and an inside weekly bar.', {'IWM': _iwm()})
        assert [(c['timeframe'], c['claim']) for c in found] == [('daily', '2U')]

    def test_candle_names_are_read_as_claims(self):
        tickers = {'IWM': _iwm()}
        assert be.overview_conflicts('IWM prints a daily 2D and a monthly 2U.', tickers) == []
        found = be.overview_conflicts('IWM prints a weekly 2D.', tickers)
        assert [(c['timeframe'], c['claim']) for c in found] == [('weekly', '2D')]

    @pytest.mark.parametrize('text', [
        "SPY's weekly candle is not bearish.",
        "The weekly isn't bullish for any of the three.",
        'No weekly candle is up.',
        'The weekly is neither bullish nor bearish.',
    ])
    def test_a_negated_direction_is_not_a_claim(self, text):
        assert be.overview_conflicts(text, _three(weekly=('1', '1', '1'))) == []

    def test_each_claim_is_held_to_the_ticker_it_describes(self):
        tickers = {
            'SPY': _iwm(ftfc_labels={'1d': '2D', '1w': '1', '1mo': '1'}),
            'QQQ': _iwm(ftfc_labels={'1d': '2U', '1w': '2U', '1mo': '1'}),
        }
        text = 'SPY has a down daily candle and QQQ has an up weekly candle.'
        assert be.overview_conflicts(text, tickers) == []
        found = be.overview_conflicts(
            'SPY has a down daily candle and QQQ has a down weekly candle.', tickers)
        assert [(c['timeframe'], c['claim'], c['tickers']) for c in found] == [
            ('weekly', '2D', ['QQQ'])]

    def test_a_claim_before_its_tickers_is_held_to_them(self):
        tickers = {
            'SPY': _iwm(ftfc_labels={'1d': '2D', '1w': '1', '1mo': '1'}),
            'QQQ': _iwm(ftfc_labels={'1d': '2U', '1w': '2U', '1mo': '1'}),
        }
        found = be.overview_conflicts('The daily is bearish for SPY and QQQ.', tickers)
        assert [(c['timeframe'], c['tickers']) for c in found] == [('daily', ['QQQ'])]

    def test_most_needs_a_strict_majority(self):
        text = 'most names are bearish on the weekly'
        conflicts = be.overview_conflicts(text, _three(weekly=('2D', '1', '1')))
        assert len(conflicts) == 1
        assert conflicts[0]['tickers'] == ['IWM', 'QQQ']
        assert be.overview_conflicts(text, _three(weekly=('2D', '2D', '1'))) == []
        # Half is not a majority: one of the two named.
        conflicts = be.overview_conflicts('most of SPY and QQQ are bearish on the daily',
                                          _three(daily=('2D', '2U', '2D')))
        assert len(conflicts) == 1
        assert conflicts[0]['timeframe'] == 'daily'

    def test_conflict_returns_the_deterministic_sentence(self, monkeypatch, caplog):
        import asyncio
        import logging
        calls = []

        async def fake_call(system, user):
            calls.append(user)
            return BEARISH_BOTH
        monkeypatch.setattr(be, '_call', fake_call)
        tickers = _three()
        with caplog.at_level(logging.WARNING, logger=be.logger.name):
            out = asyncio.run(be.explain_overview_setup(tickers))
        assert out == be.deterministic_overview(tickers)
        iwm = next(part for part in out.split('. ') if part.startswith('IWM:'))
        assert iwm.rstrip('.') + '.' == (
            'IWM: daily 2D (down), weekly 1 (inside), monthly 2U (up), TF bias -0.75.')
        assert out.endswith('IWM: daily 2D (down), weekly 1 (inside), monthly 2U (up), TF bias -0.75.')
        withheld = [r.getMessage() for r in caplog.records
                    if r.getMessage().startswith('overview withheld:')]
        assert len(withheld) == 1
        assert BEARISH_BOTH in withheld[0]
        assert len(calls) == 1

    @pytest.mark.parametrize('text, names', [
        ('Weekly candles are bearish', ['IWM', 'QQQ', 'SPY']),
        ('WEEKLY CANDLES ARE BEARISH', ['IWM', 'QQQ', 'SPY']),
        ("IWM's weekly is bearish", ['IWM']),
    ])
    def test_capitals_and_a_possessive_are_read(self, text, names):
        conflicts = be.overview_conflicts(text, _three())
        assert len(conflicts) == 1
        assert conflicts[0]['timeframe'] == 'weekly'
        assert conflicts[0]['tickers'] == names

    def test_a_model_reply_of_none_stays_none(self, monkeypatch):
        import asyncio

        async def fake_call(system, user):
            return None
        monkeypatch.setattr(be, '_call', fake_call)
        assert asyncio.run(be.explain_overview_setup(_three())) is None
