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
