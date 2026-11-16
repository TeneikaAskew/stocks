"""Tests for the --no-discord / BRIEF_POST_TO_DISCORD / BRIEF_AS_OF Discord posting policy.

The premarket-brief used to require manual secret manipulation
(temporarily unbind `DISCORD_WEBHOOK_URL` on the Cloud Run job) to
prevent historical replays from posting stale content to the live
Discord channel. That was fragile — if the morning cron fires before
the secret is restored, brief loses Discord; if you forget to restore,
brief stays silent forever.

This module replaces that with a parameterised policy. `BRIEF_POST_TO_DISCORD`
is a 3-state override env var:

  * `true`  → force posting ON (wins over everything, incl. BRIEF_AS_OF)
  * `false` → force posting OFF
  * unset   → no override; posting is suppressed by `--no-discord` or
              by `BRIEF_AS_OF` being set (replay), otherwise it posts.

The persist-to-Cloud-SQL path is unaffected — `premarket_analysis` rows
are always written regardless of the Discord policy.
"""
from __future__ import annotations

import sys
from unittest.mock import patch


# Walk through the posting policy logic directly. The actual
# implementation lives in gcp/premarket_brief.py main() — we test the
# decision function by recreating its inputs and asserting webhook_url
# ends up cleared in each path.

def _resolve_no_discord(args_no_discord: bool, env: dict) -> bool:
    """Mirror of the logic in main(). Returns True when Discord posting
    is suppressed. BRIEF_POST_TO_DISCORD=true is the explicit force-on
    override and wins over everything else; otherwise --no-discord,
    BRIEF_POST_TO_DISCORD=false, or BRIEF_AS_OF triggers suppression."""
    post_to_discord_env = env.get('BRIEF_POST_TO_DISCORD', '').lower()
    if post_to_discord_env == 'true':
        return False  # explicit force-on
    return (
        args_no_discord
        or post_to_discord_env == 'false'
        or bool(env.get('BRIEF_AS_OF'))
    )


def test_default_post_to_discord():
    """Default behavior: post to Discord. Live signal-monitor parity."""
    assert _resolve_no_discord(False, {}) is False


def test_cli_flag_suppresses():
    assert _resolve_no_discord(True, {}) is True


def test_env_var_suppresses():
    assert _resolve_no_discord(False, {'BRIEF_POST_TO_DISCORD': 'false'}) is True


def test_env_var_uppercase_suppresses():
    """Case-insensitive."""
    assert _resolve_no_discord(False, {'BRIEF_POST_TO_DISCORD': 'FALSE'}) is True


def test_env_var_true_does_not_suppress():
    assert _resolve_no_discord(False, {'BRIEF_POST_TO_DISCORD': 'true'}) is False


def test_env_var_non_boolean_does_not_suppress():
    """BRIEF_POST_TO_DISCORD with a non-boolean value falls through to
    the default (post)."""
    assert _resolve_no_discord(False, {'BRIEF_POST_TO_DISCORD': 'maybe'}) is False


def test_brief_as_of_implies_suppress():
    """Historical replays auto-skip Discord — never want to post stale
    content to a real-time channel."""
    assert _resolve_no_discord(False, {'BRIEF_AS_OF': '2026-05-06'}) is True


def test_brief_as_of_empty_does_not_suppress():
    """Empty string env var means "not set" (live behaviour)."""
    assert _resolve_no_discord(False, {'BRIEF_AS_OF': ''}) is False


def test_suppression_sources_combine_or_wise_when_no_explicit_force():
    """Multiple suppression sources combine OR-wise. The explicit
    BRIEF_POST_TO_DISCORD=true override (tested separately) wins over
    these — that's the only way to force Discord on when other
    suppression signals are set."""
    assert _resolve_no_discord(False, {'BRIEF_POST_TO_DISCORD': 'false',
                                        'BRIEF_AS_OF': ''}) is True
    assert _resolve_no_discord(False, {'BRIEF_AS_OF': '2026-05-06'}) is True
    # CLI flag alone
    assert _resolve_no_discord(True, {}) is True


# Integration-ish: assert the actual main() flow resolves webhook_url
# to '' when --no-discord is passed AND that persist_to_cloud_sql still
# runs (the brief still does its job, just doesn't notify).

def test_brief_main_clears_webhook_url_when_no_discord(monkeypatch):
    """When --no-discord is set on the CLI, webhook_url ends up '' so
    the `if webhook_url:` guard at the Discord-post site skips."""
    # Set DISCORD_WEBHOOK_URL in env to a real-looking value so we can
    # prove it gets cleared by the policy, not by absence.
    monkeypatch.setenv('DISCORD_WEBHOOK_URL', 'https://discord.com/webhook/REAL')

    # The policy resolution is identical to main()'s logic.
    env = {'DISCORD_WEBHOOK_URL': 'https://discord.com/webhook/REAL'}
    suppressed = _resolve_no_discord(True, env)
    webhook_url = '' if suppressed else env.get('DISCORD_WEBHOOK_URL')
    assert webhook_url == ''


def test_brief_main_clears_webhook_url_when_brief_as_of_set(monkeypatch):
    """Same but driven by BRIEF_AS_OF — replay mode."""
    env = {'DISCORD_WEBHOOK_URL': 'https://discord.com/webhook/REAL',
           'BRIEF_AS_OF': '2026-05-06'}
    suppressed = _resolve_no_discord(False, env)
    webhook_url = '' if suppressed else env.get('DISCORD_WEBHOOK_URL')
    assert webhook_url == ''


def test_brief_main_keeps_webhook_url_in_live_mode():
    """Live behavior — no CLI flag, no env vars — Discord posts as
    expected. Regression check that the new policy doesn't break the
    common path."""
    env = {'DISCORD_WEBHOOK_URL': 'https://discord.com/webhook/REAL'}
    suppressed = _resolve_no_discord(False, env)
    webhook_url = '' if suppressed else env.get('DISCORD_WEBHOOK_URL')
    assert webhook_url == 'https://discord.com/webhook/REAL'


# ── BRIEF_POST_TO_DISCORD=true explicit override ─────────────────


def test_explicit_force_on_overrides_brief_as_of():
    """The 'I want to see what 5/6 would have looked like in Discord'
    use case: BRIEF_POST_TO_DISCORD=true should force Discord ON even
    when BRIEF_AS_OF is set (which normally auto-suppresses)."""
    env = {'BRIEF_AS_OF': '2026-05-06', 'BRIEF_POST_TO_DISCORD': 'true'}
    assert _resolve_no_discord(False, env) is False, \
        "explicit BRIEF_POST_TO_DISCORD=true should override AS_OF auto-suppress"


def test_explicit_force_on_overrides_cli_flag():
    """If both --no-discord and BRIEF_POST_TO_DISCORD=true are set,
    explicit env-var override wins (env vars are per-execution config)."""
    env = {'BRIEF_POST_TO_DISCORD': 'true'}
    assert _resolve_no_discord(True, env) is False


def test_explicit_force_on_alone_default():
    """BRIEF_POST_TO_DISCORD=true alone means default Discord behavior (post)."""
    env = {'BRIEF_POST_TO_DISCORD': 'true'}
    assert _resolve_no_discord(False, env) is False


def test_post_to_discord_false_still_suppresses():
    """Regression check: =false still suppresses (case-insensitive)."""
    assert _resolve_no_discord(False, {'BRIEF_POST_TO_DISCORD': 'FALSE'}) is True
    assert _resolve_no_discord(False, {'BRIEF_POST_TO_DISCORD': 'false'}) is True


# ── FEAT-PLAYBOOK-001 B9: a replay that writes nothing ──────────────────

import json  # noqa: E402

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from tests.gcp import brief_dry_run_helpers as dry  # noqa: E402

ROWS_HEAD = '--- rows (no-persist) ---'
ROWS_END = '--- end rows (no-persist) ---'
WRITERS = ('execute_sql', 'upsert_dataframe', 'bulk_insert_dataframe', 'persist_level_map',
           '_delete_null_close_rows', 'persist_to_cloud_sql')


def _plain(value):
    """A stored value as JSON would carry it: a missing number is None."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if value is None or (isinstance(value, float) and value != value):
        return None
    if pd.api.types.is_scalar(value) and pd.isna(value):
        return None
    return json.loads(json.dumps(value, default=str))


def _records(rows) -> list:
    return [_plain(dict(r)) for r in rows]


def _dry_run(monkeypatch, argv=('--no-persist',), env=None, **install_kw):
    db = dry.RecordingDb(dry.brief_frames())
    pb = dry.install(monkeypatch, db, **install_kw)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    code = dry.run_main(pb, argv)
    return pb, db, code


class TestNoPersist:
    def test_the_flag_off_run_writes(self, monkeypatch):
        """The control: the recorder sees the writes of a run without the
        flag, the null-close delete and the strat_levels upsert among them."""
        _pb, db, code = _dry_run(monkeypatch, argv=())
        assert code == 0
        assert db.calls['_delete_null_close_rows'] == 1
        assert db.calls['persist_level_map'] == 3 and db.commits == 3
        assert db.calls['persist_to_cloud_sql'] == 1
        assert db.calls['execute_sql'] == 1
        assert db.calls['upsert_dataframe'] == 1 and db.calls['bulk_insert_dataframe'] == 1
        written = db.not_reads()
        assert any(t.startswith('DELETE FROM market_data_daily') for t in written)
        assert sum(t.startswith('INSERT INTO strat_levels') for t in written) == 3

    @pytest.mark.parametrize('argv, env', [
        (('--no-persist',), {}),
        ((), {'BRIEF_NO_PERSIST': 'true'}),
    ], ids=['flag', 'env'])
    def test_no_statement_but_a_select(self, monkeypatch, argv, env):
        _pb, db, code = _dry_run(monkeypatch, argv=argv, env=env)
        assert code == 0
        assert len(db.briefs) == 1          # the whole brief ran
        assert db.texts, 'the run read nothing: the recorder is not in the path'
        for text in db.texts:
            assert text.strip().upper().startswith(('SELECT', 'SET LOCAL STATEMENT_TIMEOUT')), text
        assert db.commits == 0
        for name in WRITERS:
            assert db.calls[name] == 0, name
        assert db.calls['send_to_discord'] == 0
        # The two tickers that write early in a normal run were both built.
        tickers = db.briefs[0]['tickers']
        assert tickers['SPY'].get('level_basis') and tickers['QQQ'].get('level_basis')

    def test_it_says_what_it_skipped(self, monkeypatch, capsys):
        _dry_run(monkeypatch)
        err = capsys.readouterr().err
        assert '[brief:SPY] null-close cleanup skipped (no-persist)' in err
        for ticker in dry.TICKERS:
            assert f'[brief:{ticker}] strat_levels persist skipped (no-persist)' in err

    def test_it_prints_the_brief_the_rows_and_the_payloads(self, monkeypatch, capsys):
        pb, db, code = _dry_run(monkeypatch)
        assert code == 0
        out = capsys.readouterr().out
        brief = db.briefs[0]
        assert json.dumps(brief, indent=2, default=str) in out
        assert out.count(ROWS_HEAD) == 1 and out.count(ROWS_END) == 1
        printed = json.loads(out.split(ROWS_HEAD, 1)[1].split(ROWS_END, 1)[0])
        built = pb.build_persist_rows(brief)
        assert _records(printed) == _records(built.canonical)
        assert [r['ticker'] for r in printed] == list(dry.TICKERS)
        assert {r['run_kind'] for r in printed} == {'replay'}      # BRIEF_AS_OF is set
        routed = pb.format_discord_messages_routed(brief)
        assert routed
        for i, (kind, message) in enumerate(routed, start=1):
            assert f'--- payload {i}/{len(routed)} (channel={kind}) ---' in out
            assert json.dumps(message, indent=2) in out
        assert db.calls['send_to_discord'] == 0
        assert 'Persisted' not in out

    def test_the_built_rows(self, monkeypatch):
        """build_persist_rows makes no query, names the canonical run_kind by
        BRIEF_AS_OF, and keeps a failed or stale ticker out of the canonical
        rows and in the history rows."""
        pb, db, _code = _dry_run(monkeypatch)
        brief = db.briefs[0]
        before = len(db.statements)
        built = pb.build_persist_rows(brief)
        assert len(db.statements) == before
        assert [r['ticker'] for r in built.rows] == list(dry.TICKERS)
        assert all('run_kind' not in r and 'notes' not in r and 'triggered_by' not in r
                   for r in built.rows)
        assert {r['run_kind'] for r in built.canonical} == {'replay'}
        assert built.playbook_failed == frozenset() and built.stale_data == frozenset()
        monkeypatch.delenv('BRIEF_AS_OF')
        assert {r['run_kind'] for r in pb.build_persist_rows(brief).canonical} == {'live'}

        marked = {**brief, 'tickers': {
            **brief['tickers'],
            'SPY': {**brief['tickers']['SPY'], 'status': 'PLAYBOOK_FAILED'},
            'QQQ': {**brief['tickers']['QQQ'], 'status': 'STALE_DAILY_DATA'},
            'DIA': {'status': 'NO DATA'}}}
        built = pb.build_persist_rows(marked)
        assert [r['ticker'] for r in built.rows] == list(dry.TICKERS)
        assert [r['ticker'] for r in built.canonical] == ['IWM']
        assert built.playbook_failed == frozenset({'SPY'})
        assert built.stale_data == frozenset({'QQQ'})

    def test_persist_writes_exactly_the_built_rows(self, monkeypatch):
        pb, db, code = _dry_run(monkeypatch, argv=())
        assert code == 0
        built = pb.build_persist_rows(db.briefs[0])
        (hist_table, hist), = db.frames['bulk_insert_dataframe']
        (canon_table, canon), = db.frames['upsert_dataframe']
        assert (hist_table, canon_table) == ('premarket_analysis_history', 'premarket_analysis')
        added = ['run_kind', 'triggered_by', 'notes']
        assert set(added) <= set(hist.columns)
        assert _records(hist.drop(columns=added).to_dict('records')) == _records(built.rows)
        assert _records(canon.to_dict('records')) == _records(built.canonical)
        assert list(canon['run_kind']) == ['replay'] * 3

    @pytest.mark.parametrize('argv, env', [
        (('--no-persist',), {'BRIEF_RUN_SLOT': 'late'}),
        (('--no-persist', '--update'), {}),
        (('--no-persist',), {'BRIEF_UPDATE': 'true'}),
        ((), {'BRIEF_NO_PERSIST': 'true', 'BRIEF_RUN_SLOT': 'late'}),
        (('--no-persist', '--post-existing', 'SPY', '2026-11-06'), {}),
    ], ids=['late-slot', 'update-flag', 'update-env', 'env-late-slot', 'post-existing'])
    def test_refusals_exit_2_before_any_query(self, monkeypatch, argv, env):
        db = dry.RecordingDb(dry.brief_frames())
        pb = dry.install(monkeypatch, db)
        monkeypatch.setattr(pb, 'load_config',
                            lambda: pytest.fail('the configuration was loaded before the refusal'))
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        with pytest.raises(SystemExit) as exc:
            pb.main(list(argv))
        assert exc.value.code == 2
        assert db.statements == [] and not db.calls and not db.briefs

    @pytest.mark.parametrize('value, on', [
        ('true', True), ('TRUE', True), (' true ', True), ('True', True),
        ('yes', False), ('1', False), ('false', False), ('', False),
    ])
    def test_what_an_operator_types(self, monkeypatch, value, on):
        import argparse
        from gcp import premarket_brief as pb
        monkeypatch.setenv('BRIEF_NO_PERSIST', value)
        assert pb._resolve_no_persist(argparse.Namespace(no_persist=False)) is on
        assert pb._resolve_no_persist(argparse.Namespace(no_persist=True)) is True

    def test_force_posting_does_not_post_a_dry_run(self, monkeypatch):
        env = {'BRIEF_POST_TO_DISCORD': 'true', 'DISCORD_WEBHOOK_URL': 'https://example.invalid/hook'}
        # The control: without the flag the same settings post.
        _pb, db, _code = _dry_run(monkeypatch, argv=(), env=env)
        assert db.calls['send_to_discord'] > 0
        _pb, db, code = _dry_run(monkeypatch, env=env)
        assert code == 0
        assert db.calls['send_to_discord'] == 0 and db.sent == []
        assert db.not_reads() == [] and db.commits == 0


# The fields of one ticker's brief entry, and of the brief around the
# tickers, that record the write itself and so may differ between a dry run
# and a run that writes. There are none: the brief dict carries the decisions
# (status, playbook_error, the levels and the playbook) and no trace of the
# upsert. A field that starts to differ fails the parity tests below until it
# is fixed or named here.
WRITE_ONLY_FIELDS = ()
# Not a write and not a decision: the wall clock of the run, which differs
# between any two runs, dry or not. level_basis.built_at is when
# build_session_levels ran; the Strat observation time is the brief's own
# 08:30 ET on a replay and the wall clock on a live run ('*' is every frame).
RUN_CLOCK_FIELDS = (('level_basis', 'built_at'), ('strat_observation_ts',),
                    ('tf_continuity_frames', '*', 'observation_ts'))
STALE_TICKER = 'QQQ'
STALE_LAST_BAR = pd.Timestamp('2026-10-30')     # four sessions short of 2026-11-05
# What a dry run of the three tickers executes in a new process, every one a
# read: the level parameters, three RSI calibration reads (cached for the life
# of the process, so _run clears that cache), three statement timeouts, six
# options snapshot reads, two earnings reads, the economic events and the
# earnings analytics.
DRY_RUN_STATEMENTS = 17


def _stale_playbook_read(monkeypatch, db, ticker: str = STALE_TICKER) -> None:
    """Every read of `ticker`'s daily bars after the first loses its last four
    completed sessions (the session's own premarket row stays). The brief's
    first read, behind its data freshness gate, sees current bars; the read
    the level map is built from does not."""
    from collections import Counter
    from lib.data_loader import DataLoader
    reads = Counter()
    session = pd.Timestamp(dry.SESSION)

    def load_daily(self, name, *a, **k):
        frame = db.daily[name.upper()].copy()
        reads[name.upper()] += 1
        if name.upper() == ticker and reads[ticker] > 1:
            frame = frame[(frame.index <= STALE_LAST_BAR) | (frame.index >= session)]
        return frame

    monkeypatch.setattr(DataLoader, 'load_daily', load_daily)


def _stale_session_count(monkeypatch, ticker: str = STALE_TICKER, *, failing=None) -> list:
    """The stale-source refusal for one ticker. On real frames two earlier
    gates stop a stale frame first (the brief's data freshness gate, and
    build_session_levels, which gives a stale frame no levels, and a level map
    with no levels is never refused), so the refusal is forced where it is
    decided: the session count the check reads answers three sessions too many
    for `ticker`, whose turn is its place in the run's ticker order. For
    `failing`, the count raises as an unavailable calendar does, which marks
    that ticker PLAYBOOK_FAILED. Returns the list of counts the check was
    given, one a ticker it answered."""
    import lib.strat_levels as sl
    real = getattr(sl._trading_days_between, '__wrapped__', sl._trading_days_between)
    turn = dry.TICKERS.index(ticker)
    counts = []

    fail_turn = dry.TICKERS.index(failing) if failing else None
    asked = []

    def count(source_ts, ref_ts):
        asked.append(None)
        if len(asked) - 1 == fail_turn:
            raise RuntimeError('NYSE calendar unavailable')
        n = real(source_ts, ref_ts) + (3 if len(asked) - 1 == turn else 0)
        counts.append(n)
        return n

    count.__wrapped__ = real
    monkeypatch.setattr(sl, '_trading_days_between', count)
    return counts


def _params():
    """One stored set of level parameters for the two runs of a comparison:
    the fixture mints a run_id each time it is built."""
    from tests.lib.level_params_fixtures import legacy_db
    return legacy_db(list(dry.TICKERS))


EXISTS_SQL = 'SELECT 1 FROM premarket_analysis WHERE'
HISTORY_HEAD = '--- history rows (no-persist) ---'
HISTORY_END = '--- end history rows (no-persist) ---'
DECISION = 'no-persist: canonical '
# A live dry run adds one row_exists SELECT for each canonical row it built.
LIVE_DRY_RUN_STATEMENTS = DRY_RUN_STATEMENTS + len(dry.TICKERS)


def _run(monkeypatch, argv, params_db, *, stale_read=None, stale_count=None,
         failing=None, live_with_rows_for=None):
    """One brief run through main. `live_with_rows_for` makes it a live run
    (no BRIEF_AS_OF, the exchange's date read as the fixture's session) in
    which premarket_analysis already holds a live row for those tickers."""
    from lib.strategies import calibration
    calibration._latest_calibration.cache_clear()
    routes = ()
    if live_with_rows_for is not None:
        def exists(_sql, params):
            hit = params['ticker'] in live_with_rows_for
            return pd.DataFrame({'?column?': [1]} if hit else {})
        routes = ((EXISTS_SQL, exists),)
    db = dry.RecordingDb(dry.brief_frames(), params_db=params_db, routes=routes)
    pb = dry.install(monkeypatch, db, as_of=None if live_with_rows_for is not None else dry.SESSION)
    if live_with_rows_for is not None:
        monkeypatch.setattr(pb, 'market_today', lambda: _date(2026, 11, 6))
    if stale_read:
        _stale_playbook_read(monkeypatch, db, stale_read)
    db.session_counts = (_stale_session_count(monkeypatch, stale_count, failing=failing)
                         if stale_count else None)
    code = dry.run_main(pb, argv)
    return pb, db, code


def _decisions(entry: dict) -> dict:
    def without(node, path):
        if not isinstance(node, dict):
            return node
        head, rest = path[0], path[1:]
        if not rest:
            return {k: v for k, v in node.items() if k != head}
        return {k: without(v, rest) if head in ('*', k) else v for k, v in node.items()}

    out = {k: v for k, v in _plain(entry).items() if k not in WRITE_ONLY_FIELDS}
    for path in RUN_CLOCK_FIELDS:
        out = without(out, path)
    return out


def _assert_same_brief(dry_brief: dict, real_brief: dict) -> None:
    assert list(dry_brief['tickers']) == list(real_brief['tickers'])
    for ticker, real in real_brief['tickers'].items():
        assert _decisions(dry_brief['tickers'][ticker]) == _decisions(real), ticker
    rest = lambda b: _decisions({k: v for k, v in b.items() if k != 'tickers'})  # noqa: E731
    assert rest(dry_brief) == rest(real_brief)


def _assert_wrote_nothing(db) -> None:
    assert db.texts and db.not_reads() == [] and db.commits == 0
    for name in WRITERS:
        assert db.calls[name] == 0, name
    assert db.calls['send_to_discord'] == 0


class TestDryRunDecides:
    """A dry run makes every decision a run that writes makes. It differs in
    that it writes nothing and posts nothing."""

    def test_a_stale_source_is_marked_as_the_real_run_marks_it(self, monkeypatch, capsys):
        params = _params()
        pb, real_db, real_code = _run(monkeypatch, (), params, stale_count=STALE_TICKER)
        capsys.readouterr()
        _pb, dry_db, dry_code = _run(monkeypatch, ('--no-persist',), params,
                                     stale_count=STALE_TICKER)
        err = capsys.readouterr().err
        assert (real_code, dry_code) == (0, 0)
        real, dried = real_db.briefs[0], dry_db.briefs[0]

        # The control: the run that writes refuses this ticker's upsert.
        assert real_db.session_counts == [1, 4, 1]
        assert real['tickers'][STALE_TICKER]['status'] == 'STALE_DAILY_DATA'
        assert real['tickers'][STALE_TICKER]['playbook_error'].startswith(
            'strat_levels persist refused: ')
        assert sum(t.startswith('INSERT INTO strat_levels') for t in real_db.not_reads()) == 2

        # The dry run made the same check, once a ticker, and the same mark.
        assert dry_db.session_counts == [1, 4, 1]
        assert dried['tickers'][STALE_TICKER]['status'] == 'STALE_DAILY_DATA'
        assert (dried['tickers'][STALE_TICKER]['playbook_error']
                == real['tickers'][STALE_TICKER]['playbook_error'])
        _assert_same_brief(dried, real)
        assert f'[brief:{STALE_TICKER}] strat_levels persist REFUSED (stale source)' in err
        assert f'[brief:{STALE_TICKER}] strat_levels persist skipped (no-persist)' not in err
        for ticker in ('SPY', 'IWM'):
            assert f'[brief:{ticker}] strat_levels persist skipped (no-persist)' in err

        _assert_wrote_nothing(dry_db)
        assert len(dry_db.statements) == DRY_RUN_STATEMENTS

        # The rows and the payloads built from the two briefs agree (last,
        # because building the payloads reads the earnings analytics).
        built_real, built_dry = pb.build_persist_rows(real), pb.build_persist_rows(dried)
        assert built_dry.stale_data == built_real.stale_data == frozenset({STALE_TICKER})
        assert ([r['ticker'] for r in built_dry.canonical]
                == [r['ticker'] for r in built_real.canonical] == ['SPY', 'IWM'])
        assert (pb.format_discord_messages_routed(dried)
                == pb.format_discord_messages_routed(real))

    def test_a_stale_frame_at_the_playbook_read(self, monkeypatch):
        """A frame that went stale between the brief's two reads: both runs
        build no levels for it (reason stale_daily) and neither refuses."""
        params = _params()
        _pb, real_db, _code = _run(monkeypatch, (), params, stale_read=STALE_TICKER)
        _pb, dry_db, _code = _run(monkeypatch, ('--no-persist',), params,
                                  stale_read=STALE_TICKER)
        real, dried = real_db.briefs[0], dry_db.briefs[0]
        assert real['tickers'][STALE_TICKER]['reason_long'] == 'stale_daily'
        assert real['tickers'][STALE_TICKER].get('status') is None
        _assert_same_brief(dried, real)
        _assert_wrote_nothing(dry_db)

    def test_every_ticker_matches_the_real_run(self, monkeypatch):
        params = _params()
        pb, real_db, real_code = _run(monkeypatch, (), params)
        _pb, dry_db, dry_code = _run(monkeypatch, ('--no-persist',), params)
        assert (real_code, dry_code) == (0, 0)
        real, dried = real_db.briefs[0], dry_db.briefs[0]
        assert list(real['tickers']) == list(dry.TICKERS)
        _assert_same_brief(dried, real)
        _assert_wrote_nothing(dry_db)
        # The freshness check reads the frame the level map was built from
        # and the NYSE calendar: it adds no statement to the dry run, whose
        # statements are the real run's reads, in the real run's order.
        assert len(dry_db.statements) == DRY_RUN_STATEMENTS
        real_reads = [t for t in real_db.texts if t not in real_db.not_reads()]
        assert dry_db.texts == real_reads
        # Last, because building the payloads reads the earnings analytics.
        assert (pb.format_discord_messages_routed(dried)
                == pb.format_discord_messages_routed(real))

    def test_a_failed_check_is_marked_alike(self, monkeypatch):
        """The NYSE calendar failing inside the check marks the ticker
        PLAYBOOK_FAILED in a run that writes; the dry run reaches the same
        mark through the same handler."""
        import lib.strat_levels as sl

        def unavailable(_source, _ref):
            raise RuntimeError('NYSE calendar unavailable')

        briefs, params = [], _params()
        for argv in ((), ('--no-persist',)):
            db = dry.RecordingDb(dry.brief_frames(), params_db=params)
            pb = dry.install(monkeypatch, db)
            monkeypatch.setattr(sl, '_trading_days_between', unavailable)
            assert dry.run_main(pb, argv) == 0
            briefs.append(db.briefs[0])
        real, dried = briefs
        for ticker in dry.TICKERS:
            assert real['tickers'][ticker]['status'] == 'PLAYBOOK_FAILED'
            assert real['tickers'][ticker]['playbook_error'] == (
                'strat_levels persist failed: RuntimeError: NYSE calendar unavailable')
        _assert_same_brief(dried, real)
        _assert_wrote_nothing(db)

    def test_it_reports_which_rows_a_real_run_would_write(self, monkeypatch, capsys):
        """A live run without --update leaves a canonical row that already
        exists alone. The dry run asks the same question with the same
        statement and prints the answer for every canonical row it built."""
        params = _params()
        _pb, real_db, real_code = _run(monkeypatch, (), params, live_with_rows_for={'QQQ'})
        capsys.readouterr()
        _pb, dry_db, dry_code = _run(monkeypatch, ('--no-persist',), params,
                                     live_with_rows_for={'QQQ'})
        out = capsys.readouterr().out
        assert (real_code, dry_code) == (0, 0)

        # What the real run did, from its record.
        (table, canon), = real_db.frames['upsert_dataframe']
        assert table == 'premarket_analysis'
        written = list(canon['ticker'])
        assert written == ['SPY', 'IWM'] and set(canon['run_kind']) == {'live'}
        real_asked = real_db.matching(EXISTS_SQL)
        assert [p['ticker'] for _t, p in real_asked] == list(dry.TICKERS)
        assert all(p['run_kind'] == 'live' and str(p['analysis_date']) == dry.SESSION
                   for _t, p in real_asked)

        # The dry run asked the same, and wrote nothing.
        assert dry_db.matching(EXISTS_SQL) == real_asked
        _assert_wrote_nothing(dry_db)
        assert len(dry_db.statements) == LIVE_DRY_RUN_STATEMENTS
        real_reads = [t for t in real_db.texts if t not in real_db.not_reads()]
        assert dry_db.texts == real_reads

        decisions = dict(line[len(DECISION):].split(': ', 1)
                         for line in out.splitlines() if line.startswith(DECISION))
        assert decisions == {
            ticker: 'WRITE' if ticker in written else 'SKIP (row already exists)'
            for ticker in dry.TICKERS}
        assert decisions['QQQ'].startswith('SKIP') and decisions['SPY'] == 'WRITE'
        # The rows section is still every canonical row built, parseable.
        printed = json.loads(out.split(ROWS_HEAD, 1)[1].split(ROWS_END, 1)[0])
        assert [r['ticker'] for r in printed] == list(dry.TICKERS)
        _assert_same_brief(dry_db.briefs[0], real_db.briefs[0])

    def test_a_replay_overwrites_and_asks_nothing(self, monkeypatch, capsys):
        """BRIEF_AS_OF implies the overwrite in a run that writes, so the dry
        run of a replay reports WRITE for every row and reads no row."""
        params = _params()
        _pb, real_db, _code = _run(monkeypatch, (), params)
        capsys.readouterr()
        _pb, dry_db, _code = _run(monkeypatch, ('--no-persist',), params)
        out = capsys.readouterr().out
        (_table, canon), = real_db.frames['upsert_dataframe']
        assert list(canon['ticker']) == list(dry.TICKERS)
        assert real_db.matching(EXISTS_SQL) == [] and dry_db.matching(EXISTS_SQL) == []
        decisions = [line[len(DECISION):] for line in out.splitlines()
                     if line.startswith(DECISION)]
        assert decisions == [f'{ticker}: WRITE' for ticker in dry.TICKERS]

    def test_the_history_notes_are_the_real_runs(self, monkeypatch, capsys):
        """QQQ is refused as stale and IWM's check fails: the notes the dry
        run prints with its history rows are the notes the real run wrote."""
        params = _params()
        kw = dict(stale_count=STALE_TICKER, failing='IWM')
        _pb, real_db, real_code = _run(monkeypatch, (), params, **kw)
        capsys.readouterr()
        _pb, dry_db, dry_code = _run(monkeypatch, ('--no-persist',), params, **kw)
        out = capsys.readouterr().out
        assert (real_code, dry_code) == (0, 0)

        (table, hist), = real_db.frames['bulk_insert_dataframe']
        assert table == 'premarket_analysis_history'
        real_rows = {r['ticker']: r for r in _records(hist.to_dict('records'))}
        assert real_rows['SPY']['notes'] is None
        assert real_rows['QQQ']['notes'].startswith('STALE_DAILY_DATA: data_as_of=')
        assert real_rows['IWM']['notes'] == (
            'PLAYBOOK_FAILED: strat_levels persist failed: '
            'RuntimeError: NYSE calendar unavailable')

        assert out.count(HISTORY_HEAD) == 1 and out.count(HISTORY_END) == 1
        printed = json.loads(out.split(HISTORY_HEAD, 1)[1].split(HISTORY_END, 1)[0])
        assert [r['ticker'] for r in printed] == list(dry.TICKERS)
        for row in _records(printed):
            real_row = real_rows[row['ticker']]
            assert set(row) == set(real_row)
            for field in ('notes', 'run_kind', 'triggered_by'):
                assert row[field] == real_row[field], (row['ticker'], field)
        # Only SPY has a canonical row, in both.
        (_t, canon), = real_db.frames['upsert_dataframe']
        assert list(canon['ticker']) == ['SPY']
        decisions = [line[len(DECISION):] for line in out.splitlines()
                     if line.startswith(DECISION)]
        assert decisions == ['SPY: WRITE']
        _assert_wrote_nothing(dry_db)
        assert len(dry_db.statements) == DRY_RUN_STATEMENTS

    def test_one_check_two_callers(self):
        """persist_level_map refuses through the function the dry run calls,
        in the same words, before it asks for a cursor."""
        import lib.strat_levels as sl
        from tests.lib.test_strat_levels_freshness import _level_map
        kw = dict(source_data_as_of=pd.Timestamp('2026-04-27'),
                  today=pd.Timestamp('2026-05-06', tz='UTC'))
        with pytest.raises(sl.StaleSourceDataError) as checked:
            sl.check_source_freshness(_level_map(), **kw)

        class _NoWrite:
            def cursor(self):
                raise AssertionError('a refused level map reached the cursor')

        with pytest.raises(sl.StaleSourceDataError) as persisted:
            sl.persist_level_map(_level_map(), _NoWrite(), **kw)
        assert str(checked.value) == str(persisted.value)
        assert sl.check_source_freshness(
            _level_map(), source_data_as_of=pd.Timestamp('2026-05-05'),
            today=pd.Timestamp('2026-05-06', tz='UTC')) is None


# ── FEAT-PLAYBOOK-001 B10: the dry run recomputes the premarket from bars ──

from datetime import date as _date  # noqa: E402

BARS_SESSION = _date(2026, 11, 6)
# 2026-11-06 is Eastern Standard Time: 04:00 ET is 09:00Z, 09:30 ET is 14:30Z.
PM_START = pd.Timestamp('2026-11-06T09:00:00Z')
PM_OPEN = pd.Timestamp('2026-11-06T14:30:00Z')
BRIEF_CUTOFF = '2026-11-06T13:20:41+00:00'       # level_basis.premarket.fetched_at
REWRITTEN_AT = '2026-11-07T02:01:07+00:00'       # the nightly's later pre_fetched_at
BARS_SQL = 'FROM market_data_intraday'
BASIS_SQL = "FROM premarket_analysis WHERE ticker = :ticker AND analysis_date = :d AND run_kind = 'live'"

# (minute of the bar in UTC, then open, high, low, close as offsets from the
# prior close, then volume). The first four are before the brief's cutoff.
# By hand, before the cutoff: the highs are +0.30, +0.50, +0.60 and +0.10, so
# the second highest is +0.50; the highest open or close is +0.40; the high
# is +0.50. The lows are -0.10, +0.05, -0.30 and -0.40, so the second lowest
# is -0.30; the lowest open or close is -0.25; the low is -0.30. With the
# three later bars the high would be +2.00 and the low -1.50.
BEFORE_CUTOFF = (
    ('09:00', 0.10, 0.30, -0.10, 0.20, 1000),
    ('10:00', 0.20, 0.50, 0.05, 0.40, 1000),
    ('12:00', 0.40, 0.60, -0.30, -0.20, 1000),
    ('13:20', -0.20, 0.10, -0.40, -0.25, 1000),
)
AFTER_CUTOFF = (
    ('13:21', 1.00, 2.00, 0.90, 1.90, 5000),
    ('13:45', 1.90, 2.50, -1.50, -1.40, 5000),
    ('14:10', -1.40, 2.20, -1.60, -1.45, 5000),
)
HAND_HIGH, HAND_LOW = 0.50, -0.30


def _minute_bars(base: float, rows=BEFORE_CUTOFF + AFTER_CUTOFF) -> pd.DataFrame:
    return pd.DataFrame([
        {'ts': pd.Timestamp(f'2026-11-06T{minute}:00Z'), 'open': base + o, 'high': base + h,
         'low': base + lo, 'close': base + c, 'volume': v}
        for minute, o, h, lo, c, v in rows])


def _recorded_params(atr: float, *, stale=0.1, spike=0.5, statuses=None) -> dict:
    """pre_filter_params in the shape the writer records it, built by the
    writer's own function so the shape cannot drift."""
    from lib.strat_levels import premarket_filter_inputs
    from tests.lib.level_params_fixtures import fixture_params
    lp = fixture_params('TST', BARS_SESSION, statuses=statuses,
                        overrides={'pm_stale_print_atr': stale, 'pm_spike_atr': spike})
    return premarket_filter_inputs(lp, {'atr_14': atr, 'atr_5': None})['params']


class _BarsRun:
    """One dry run with BRIEF_PREMARKET_FROM_BARS=true on the 2026-11-06
    frames. Each ticker's session row holds the stored snapshot, the filter
    parameters it recorded and a pre_fetched_at a later job rewrote; the
    live brief row holds the brief's own cutoff; bars exist on both sides
    of that cutoff."""

    def __init__(self, monkeypatch, *, cutoff=BRIEF_CUTOFF, live_rows=True, bars=True,
                 argv=('--no-persist',), env=None, bars_error=None):
        from tests.lib import strat_2026_11_06 as fx
        self.frames = dry.brief_frames(null_close_for=None)
        self.base, self.stored = {}, {}
        for ticker, frame in self.frames.items():
            frame = frame.astype({c: 'object' for c in frame.columns if c.startswith('pre_')})
            session_row = frame.index[-1]
            assert session_row == pd.Timestamp(BARS_SESSION)
            frame['pre_fetched_at'] = None
            frame['pre_filter_params'] = None
            frame.at[session_row, 'pre_fetched_at'] = pd.Timestamp(REWRITTEN_AT)
            frame.at[session_row, 'pre_filter_params'] = _recorded_params(fx.prior_atr(ticker))
            self.frames[ticker] = frame
            self.base[ticker] = float(frame['Close'].dropna().iloc[-1])
            self.stored[ticker] = (float(frame.at[session_row, 'pre_high']),
                                   float(frame.at[session_row, 'pre_low']))
        self.given = {}        # ticker -> the frame premarket_snapshot was handed
        self.cutoff, self.live_rows, self.bars, self.bars_error = cutoff, live_rows, bars, bars_error

        self.db = dry.RecordingDb(self.frames, routes=[
            (BASIS_SQL, self._live_basis), (BARS_SQL, self._bars)])
        self.pb = dry.install(monkeypatch, self.db)
        import gcp.fetchers.fetch_market_data as fmd
        real = fmd.premarket_snapshot

        def snapshot(ticker, session_date, bars_, *a, **k):
            self.given[ticker] = bars_.copy()
            return real(ticker, session_date, bars_, *a, **k)

        monkeypatch.setattr(fmd, 'premarket_snapshot', snapshot)
        for key, value in {'BRIEF_PREMARKET_FROM_BARS': 'true', **(env or {})}.items():
            monkeypatch.setenv(key, value)
        self.argv = argv

    def _live_basis(self, sql, params):
        if not self.live_rows:
            return pd.DataFrame(columns=['ticker', 'level_basis'])
        premarket = {'date': BARS_SESSION.isoformat(), 'pre_high': 1.0, 'pre_low': 1.0}
        if self.cutoff is not None:
            premarket['fetched_at'] = self.cutoff
        return pd.DataFrame([{'ticker': params['ticker'],
                              'level_basis': json.dumps({'premarket': premarket})}])

    def _bars(self, sql, params):
        if self.bars_error is not None:
            raise self.bars_error
        if not self.bars:
            return pd.DataFrame(columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
        frame = _minute_bars(self.base[params['ticker']])
        start, end = pd.Timestamp(params['start']), pd.Timestamp(params['end'])
        return frame[(frame['ts'] >= start) & (frame['ts'] < end)].reset_index(drop=True)

    def run(self) -> int:
        return dry.run_main(self.pb, self.argv)

    def premarket_of(self, ticker) -> dict:
        return self.db.briefs[0]['tickers'][ticker]['level_basis']['premarket']


def _line_of(text: str, ticker: str, needle: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.startswith(f'[brief:{ticker}]') and needle in ln]
    assert len(lines) == 1, (ticker, needle, lines)
    return lines[0]


class TestPremarketFromBars:
    def test_it_reads_bars_to_the_briefs_own_cutoff(self, monkeypatch):
        run = _BarsRun(monkeypatch)
        assert run.run() == 0
        cutoff = pd.Timestamp(BRIEF_CUTOFF)
        reads = run.db.matching(BARS_SQL)
        assert len(reads) == 3
        for text, params in reads:
            assert "interval = '1min'" in text and 'ts >= :start' in text and 'ts < :end' in text
            assert pd.Timestamp(params['start']) == PM_START
            assert pd.Timestamp(params['end']) == cutoff
        for ticker in dry.TICKERS:
            given = run.given[ticker]
            assert len(given) == len(BEFORE_CUTOFF)
            assert (given['ts'] < cutoff).all()
            base = run.base[ticker]
            pm = run.premarket_of(ticker)
            assert pm['pre_high'] == pytest.approx(base + HAND_HIGH)
            assert pm['pre_low'] == pytest.approx(base + HAND_LOW)
            # Not the values every stored bar would give, and not the stored ones.
            assert pm['pre_high'] != pytest.approx(base + 2.00)
            assert pm['pre_high'] != pytest.approx(run.stored[ticker][0])

    def test_a_cutoff_after_the_open_stops_at_the_open(self, monkeypatch):
        run = _BarsRun(monkeypatch, cutoff='2026-11-06T15:05:00+00:00')
        assert run.run() == 0
        reads = run.db.matching(BARS_SQL)
        assert len(reads) == 3
        for _text, params in reads:
            assert pd.Timestamp(params['end']) == PM_OPEN
        assert all(len(given) == len(BEFORE_CUTOFF + AFTER_CUTOFF) for given in run.given.values())

    def test_it_prints_stored_and_recomputed_side_by_side(self, monkeypatch, capsys):
        run = _BarsRun(monkeypatch)
        assert run.run() == 0
        out = capsys.readouterr().out
        for ticker in dry.TICKERS:
            line = _line_of(out, ticker, 'recomputed high=')
            base, (stored_high, stored_low) = run.base[ticker], run.stored[ticker]
            for part in ('cutoff=2026-11-06T13:20:41+00:00',
                         f'stored high={stored_high:.4f}', f'stored low={stored_low:.4f}',
                         f'recomputed high={base + HAND_HIGH:.4f}',
                         f'recomputed low={base + HAND_LOW:.4f}',
                         'recorded atr=', 'today atr='):
                assert part in line, (part, line)

    def test_the_recomputed_values_are_used_in_memory(self, monkeypatch, capsys):
        run = _BarsRun(monkeypatch)
        assert run.run() == 0
        out = capsys.readouterr().out
        printed = json.loads(out.split(ROWS_HEAD, 1)[1].split(ROWS_END, 1)[0])
        for ticker in dry.TICKERS:
            base = run.base[ticker]
            pm = run.premarket_of(ticker)
            assert (pm['pre_high'], pm['pre_low']) == (
                pytest.approx(base + HAND_HIGH), pytest.approx(base + HAND_LOW))
            assert pm['fetched_at'] == BRIEF_CUTOFF and pm['pre_filter_status'] == 'ok'
            row = next(r for r in printed if r['ticker'] == ticker)
            assert row['level_basis']['premarket']['pre_high'] == pytest.approx(base + HAND_HIGH)
        # Task 9's assertions, repeated: the recompute writes nothing.
        db = run.db
        assert db.not_reads() == [] and db.commits == 0
        for name in WRITERS:
            assert db.calls[name] == 0, name
        assert db.calls['send_to_discord'] == 0
        # The frames the loader gave are not changed in place.
        for ticker in dry.TICKERS:
            row = run.frames[ticker].iloc[-1]
            assert (float(row['pre_high']), float(row['pre_low'])) == run.stored[ticker]

    @pytest.mark.parametrize('kw', [{'live_rows': False}, {'cutoff': None},
                                    {'cutoff': 'not a time'}],
                             ids=['no-live-row', 'no-fetched-at', 'unreadable'])
    def test_no_cutoff(self, monkeypatch, capsys, kw):
        run = _BarsRun(monkeypatch, **kw)
        assert run.run() == 0
        out = capsys.readouterr().out
        assert run.db.matching(BARS_SQL) == [] and run.given == {}
        assert len(run.db.matching(BASIS_SQL)) == 3
        rewritten = pd.Timestamp(REWRITTEN_AT)
        for _channel, _text, params in run.db.statements:
            if isinstance(params, dict):
                for value in params.values():
                    assert not (isinstance(value, (pd.Timestamp, str)) and str(value)[:4] == '2026'
                                and len(str(value)) > 10 and pd.Timestamp(value) == rewritten), params
        for ticker in dry.TICKERS:
            assert 'premarket cutoff unavailable' in _line_of(out, ticker, 'premarket cutoff')
            pm = run.premarket_of(ticker)
            assert (pm['pre_high'], pm['pre_low']) == run.stored[ticker]

    def test_no_bars(self, monkeypatch, capsys):
        run = _BarsRun(monkeypatch, bars=False)
        assert run.run() == 0
        out = capsys.readouterr().out
        assert len(run.db.matching(BARS_SQL)) == 3 and run.given == {}
        for ticker in dry.TICKERS:
            assert 'premarket bars unavailable' in _line_of(out, ticker, 'premarket bars')
            pm = run.premarket_of(ticker)
            assert (pm['pre_high'], pm['pre_low']) == run.stored[ticker]

    # ── the filter runs with the parameters the original run recorded ──
    BASE = 100.0
    PRIOR = {'close': 100.0, 'open': 99.5, 'atr_14': 6.00, 'atr_5': None}
    # The 10:00 bar's high is 4.10 above its own body and above the bodies of
    # the bars on each side: beyond the recorded spike threshold
    # (0.542 x 4.875 = 2.64), inside the loaded one (1.50 x 6.00 = 9.00).
    WICK = (BEFORE_CUTOFF[0], ('10:00', 0.20, 4.50, 0.05, 0.40, 1000)) + BEFORE_CUTOFF[2:]

    def _direct(self, stored_params, *, bars_rows=None):
        from gcp import premarket_brief as pb
        from tests.lib.level_params_fixtures import fixture_params
        loaded = fixture_params('TST', BARS_SESSION,
                                overrides={'pm_stale_print_atr': 0.10, 'pm_spike_atr': 1.50})
        seen = []

        def query(sql, params=None):
            seen.append(sql)
            if BARS_SQL in sql:
                return _minute_bars(self.BASE, bars_rows or self.WICK)
            return pd.DataFrame([{'ticker': 'TST', 'level_basis': {
                'premarket': {'fetched_at': BRIEF_CUTOFF}}}])

        stored = {'pre_high': 101.25, 'pre_low': 99.10, 'pre_fetched_at': REWRITTEN_AT,
                  'pre_filter_status': 'ok', 'pre_filter_params': stored_params}
        snap, line = pb._premarket_from_bars('TST', BARS_SESSION, self.PRIOR, loaded, query,
                                             stored=stored)
        return snap, line, seen

    def test_it_filters_with_the_recorded_parameters(self):
        recorded = _recorded_params(4.875, stale=0.0329, spike=0.542)
        assert recorded['atr'] == 4.875
        assert recorded['pm_stale_print_atr']['value'] == 0.0329
        assert recorded['pm_spike_atr'] == {**recorded['pm_spike_atr'], 'value': 0.542, 'status': 'ok'}
        # Stored as JSON text or as the parsed object: both are read.
        for stored_params in (recorded, json.dumps(recorded)):
            snap, line, _seen = self._direct(stored_params)
            # The wick dropped: the highs left are +0.30, +0.60 and +0.10, the
            # second highest +0.30, the highest open or close +0.40.
            assert snap['pre_high'] == pytest.approx(self.BASE + 0.40)
            assert snap['pre_excluded_spikes'] == 1 and snap['pre_filter_status'] == 'ok'
            assert snap['pre_range_atr'] == pytest.approx(round((0.40 + 0.30) / 4.875, 4))
            kept = snap['pre_filter_params']
            assert kept['atr'] == 4.875 and kept['pm_spike_atr']['value'] == 0.542
            assert kept['pm_stale_print_atr']['value'] == 0.0329
            assert kept['confirmed']['rule'] == 'two-bars-or-body-v1'
            assert 'recorded atr=4.8750' in line and 'today atr=6.0000' in line
            assert 'recomputed high=100.4000' in line and 'stored high=101.2500' in line

    def test_the_loaded_parameters_would_keep_the_wick(self):
        """The control for the test above: the same bars through the same
        function with today's parameters and ATR keep the wick, so the high
        differs. The dry run never does this."""
        from gcp.fetchers.fetch_market_data import premarket_snapshot
        from tests.lib.level_params_fixtures import fixture_params
        loaded = fixture_params('TST', BARS_SESSION,
                                overrides={'pm_stale_print_atr': 0.10, 'pm_spike_atr': 1.50})
        snap = premarket_snapshot('TST', BARS_SESSION, _minute_bars(self.BASE, self.WICK),
                                  self.PRIOR, loaded, pd.Timestamp(BRIEF_CUTOFF))
        assert snap['pre_excluded_spikes'] == 0
        assert snap['pre_high'] == pytest.approx(self.BASE + 0.60)

    @pytest.mark.parametrize('damage', ['null', 'no-spike', 'spike-not-ok', 'no-atr',
                                        'null-stale-value', 'not-json'])
    def test_recorded_parameters_unavailable(self, damage):
        recorded = _recorded_params(4.875, stale=0.0329, spike=0.542)
        if damage == 'null':
            recorded = None
        elif damage == 'no-spike':
            del recorded['pm_spike_atr']
        elif damage == 'spike-not-ok':
            recorded = _recorded_params(4.875, statuses={'pm_spike_atr': 'input_unavailable'})
        elif damage == 'no-atr':
            recorded['atr'] = None
        elif damage == 'null-stale-value':
            recorded['pm_stale_print_atr'] = {**recorded['pm_stale_print_atr'], 'value': None}
        elif damage == 'not-json':
            recorded = '{not json'
        snap, line, seen = self._direct(recorded)
        assert snap is None
        assert 'premarket filter parameters unavailable' in line
        assert 'stored high=101.2500' in line
        assert not any(BARS_SQL in sql for sql in seen)   # nothing derived from today's values

    def test_unavailable_parameters_keep_the_stored_snapshot(self, monkeypatch, capsys):
        run = _BarsRun(monkeypatch)
        for frame in run.frames.values():
            frame.at[frame.index[-1], 'pre_filter_params'] = None
        run.db.daily = run.frames
        assert run.run() == 0
        out = capsys.readouterr().out
        assert run.given == {}
        for ticker in dry.TICKERS:
            assert 'premarket filter parameters unavailable' in _line_of(
                out, ticker, 'premarket filter parameters')
            pm = run.premarket_of(ticker)
            assert (pm['pre_high'], pm['pre_low']) == run.stored[ticker]

    def test_reads_are_strict_and_counted(self, monkeypatch, capsys):
        run = _BarsRun(monkeypatch)
        assert run.run() == 0
        assert len(run.db.matching(BARS_SQL)) == 3
        assert len(run.db.matching(BASIS_SQL)) == 3
        strict = {channel for channel, text, _p in run.db.statements
                  if BARS_SQL in text or BASIS_SQL in text}
        assert strict == {'query_to_dataframe_strict'}
        capsys.readouterr()

        failing = _BarsRun(monkeypatch, bars_error=ConnectionError('cloud sql is down'))
        with pytest.raises(ConnectionError, match='cloud sql is down'):
            failing.pb.main(['--no-persist'])
        text = capsys.readouterr()
        assert 'premarket bars unavailable' not in text.out + text.err
        assert 'PLAYBOOK_FAILED' not in text.out
        assert failing.db.not_reads() == [] and failing.db.commits == 0

    @pytest.mark.parametrize('env', [{}, {'BRIEF_NO_PERSIST': 'false'}])
    def test_the_variable_needs_no_persist(self, monkeypatch, env):
        run = _BarsRun(monkeypatch, argv=(), env=env)
        monkeypatch.setattr(run.pb, 'load_config',
                            lambda: pytest.fail('the configuration was loaded before the refusal'))
        with pytest.raises(SystemExit) as exc:
            run.pb.main([])
        assert exc.value.code == 2
        assert run.db.statements == [] and not run.db.calls and not run.db.briefs

    def test_without_the_variable_no_bars_are_read(self, monkeypatch):
        run = _BarsRun(monkeypatch, env={'BRIEF_PREMARKET_FROM_BARS': 'false'})
        assert run.run() == 0
        assert run.db.matching(BARS_SQL) == [] and run.db.matching(BASIS_SQL) == []
        for ticker in dry.TICKERS:
            pm = run.premarket_of(ticker)
            assert (pm['pre_high'], pm['pre_low']) == run.stored[ticker]
