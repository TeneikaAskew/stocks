"""Regression guards for the 2026-05-15 earnings-channel routing change.

The Earnings embed routes to a dedicated DISCORD_WEBHOOK_EARNINGS_URL so
company earnings don't drown out analytics. Overview + Ticker Analysis +
Playbook + Economic Calendar stay on the main DISCORD_WEBHOOK_URL.

Tests the ROUTING logic in isolation by mocking the individual
_build_*_embed() functions, so the assertions don't depend on the
internals of those builders.

Pins:
  1. format_discord_messages_routed returns (kind, payload) tuples.
  2. Earnings embed → 'earnings' channel.
  3. Overview + Ticker Analysis + Playbook + Calendar → 'main'.
  4. Empty earnings → no 'earnings' message produced.
  5. Backward compat: format_discord_messages still returns list[dict].
  6. main()'s no-Discord branch iterates `routed`, not a stale `messages`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _mock_embed(title, has_content=True):
    """An embed dict that looks 'real enough' for the truncation +
    non-empty checks the routing code does."""
    return {
        'title': title,
        'description': 'content' if has_content else '',
        'color': 0x000000,
    }


@pytest.fixture
def patched_builders(monkeypatch):
    """Monkeypatch every _build_*_embed + the ticker-fields helper so
    format_discord_messages_routed gets deterministic, controllable
    inputs without needing full brief content."""
    import gcp.premarket_brief as pb
    monkeypatch.setattr(pb, '_build_overview_embed',
                        lambda b: _mock_embed('Premarket Overview'))
    monkeypatch.setattr(pb, '_build_ticker_fields',
                        lambda b: [{'name': 'SPY', 'value': '~', 'inline': True}])
    monkeypatch.setattr(pb, '_build_calendar_embed',
                        lambda evts, mode='daily':
                            _mock_embed('Economic Calendar',
                                        has_content=bool(evts.get('today'))))
    monkeypatch.setattr(pb, '_build_earnings_embed',
                        lambda data:
                            _mock_embed('Earnings — Mon 05/18 — 1',
                                        has_content=bool(data.get('earnings'))))
    monkeypatch.setattr(pb, '_build_playbook_embed',
                        lambda b: {'title': 'Playbook',
                                   'fields': [{'name': 'SPY', 'value': 'pb',
                                               'inline': False}],
                                   'color': 0})
    yield pb


def _full_brief():
    return {
        'overview':  {},
        'tickers':   {'SPY': {}},
        'earnings':  {'mode': 'daily', 'earnings': [{'ticker': 'AVGO'}]},
        'events':    {'today': [{'name': 'CPI'}]},
    }


# ────────────────────────────────────────────────────────────────────────────
# Routing structure
# ────────────────────────────────────────────────────────────────────────────

def test_format_discord_messages_routed_returns_tuples(patched_builders):
    out = patched_builders.format_discord_messages_routed(_full_brief())
    assert isinstance(out, list)
    for entry in out:
        assert isinstance(entry, tuple) and len(entry) == 2
        kind, msg = entry
        assert kind in ('main', 'earnings')
        assert isinstance(msg, dict) and 'embeds' in msg


def test_earnings_routes_to_earnings_channel(patched_builders):
    out = patched_builders.format_discord_messages_routed(_full_brief())
    earnings_msgs = [msg for kind, msg in out if kind == 'earnings']
    assert len(earnings_msgs) == 1
    titles = [e['title'] for e in earnings_msgs[0]['embeds']]
    assert any('Earnings' in t for t in titles), f"Earnings embed missing: {titles}"


def test_overview_tickers_playbook_route_to_main(patched_builders):
    out = patched_builders.format_discord_messages_routed(_full_brief())
    main_msgs = [msg for kind, msg in out if kind == 'main']
    titles = [e['title'] for m in main_msgs for e in m['embeds']]
    assert 'Premarket Overview' in titles
    assert 'Ticker Analysis' in titles
    assert 'Playbook' in titles


def test_calendar_routes_to_main(patched_builders):
    out = patched_builders.format_discord_messages_routed(_full_brief())
    main_msgs = [msg for kind, msg in out if kind == 'main']
    titles = [e['title'] for m in main_msgs for e in m['embeds']]
    assert 'Economic Calendar' in titles, f"Calendar missing from main: {titles}"


def test_calendar_not_in_earnings_channel(patched_builders):
    """Macro calendar must NOT leak into the company-earnings feed."""
    out = patched_builders.format_discord_messages_routed(_full_brief())
    for kind, msg in out:
        if kind == 'earnings':
            for e in msg['embeds']:
                assert 'Economic Calendar' not in e['title']


def test_calendar_is_separate_message_from_analytics(patched_builders):
    """Calendar + Playbook are each their OWN main message, not appended
    to analytics — keeps each message's char budget bounded. Analytics
    (overview + ticker) historically blew the 6000-char cap and dropped
    the Strat Playbook every run; splitting them gives each its own
    budget so nothing gets silently truncated."""
    out = patched_builders.format_discord_messages_routed(_full_brief())
    main_msgs = [msg for kind, msg in out if kind == 'main']
    assert len(main_msgs) == 3, (
        f"Expected 3 'main' messages (analytics + playbook + calendar), "
        f"got {len(main_msgs)}"
    )


def test_playbook_is_its_own_main_message(patched_builders):
    """Strat Playbook must NOT share a message with overview/ticker —
    that historical pairing blew the 6000-char per-message cap and the
    playbook was the embed that got dropped. Pin: the playbook is in
    a separate ('main', {...}) tuple."""
    out = patched_builders.format_discord_messages_routed(_full_brief())
    titles_per_msg = [
        (kind, [e.get('title', '') for e in msg['embeds']])
        for kind, msg in out
    ]
    playbook_msgs = [
        (kind, titles) for kind, titles in titles_per_msg
        if any('Playbook' in (t or '') for t in titles)
    ]
    assert len(playbook_msgs) == 1, (
        f"Playbook should be in exactly one message, got {playbook_msgs}")
    kind, titles = playbook_msgs[0]
    assert kind == 'main'
    # Crucially: it must not share a message with the analytics embeds
    assert 'Premarket Overview' not in titles
    assert 'Ticker Analysis' not in titles


def test_no_playbook_message_when_playbook_empty(monkeypatch, patched_builders):
    """When `_build_playbook_embed` returns no fields (nothing to show),
    we don't emit an empty playbook message."""
    monkeypatch.setattr(
        patched_builders, '_build_playbook_embed',
        lambda b: {'title': 'Playbook', 'fields': [], 'color': 0},
    )
    out = patched_builders.format_discord_messages_routed(_full_brief())
    for kind, msg in out:
        for emb in msg['embeds']:
            assert 'Playbook' not in (emb.get('title') or ''), (
                f"Empty playbook should not be emitted, got: {emb}")


def test_no_earnings_message_when_no_earnings(patched_builders):
    brief = _full_brief()
    brief['earnings']['earnings'] = []
    out = patched_builders.format_discord_messages_routed(brief)
    earnings_msgs = [msg for kind, msg in out if kind == 'earnings']
    assert earnings_msgs == [], (
        f"Empty earnings should produce no earnings message; got {len(earnings_msgs)}"
    )


def test_legacy_single_payload_preserves_playbook(patched_builders):
    """format_discord_message (singular) must NOT silently lose the
    Strat Playbook when the routed function splits it into its own
    message — back-compat regression guard for PR #522. Pre-split the
    single payload was [overview, ticker, playbook]; after the split
    msgs[0] is just [overview, ticker] and a naive `msgs[0]` would
    drop the playbook for any legacy caller."""
    msg = patched_builders.format_discord_message(_full_brief())
    titles = [e.get('title', '') for e in msg['embeds']]
    assert 'Premarket Overview' in titles
    assert 'Ticker Analysis' in titles
    assert 'Playbook' in titles, (
        f"Playbook missing from legacy single-payload — got: {titles}")
    # Earnings + Calendar were never in the legacy single payload
    assert not any('Earnings' in t for t in titles)
    assert not any('Calendar' in t for t in titles)


# ────────────────────────────────────────────────────────────────────────────
# Backward compatibility
# ────────────────────────────────────────────────────────────────────────────

def test_legacy_format_discord_messages_returns_list_of_dicts(patched_builders):
    out = patched_builders.format_discord_messages(_full_brief())
    assert isinstance(out, list)
    for msg in out:
        assert isinstance(msg, dict) and 'embeds' in msg
        assert not isinstance(msg, tuple)


def test_routed_and_legacy_same_payloads(patched_builders):
    brief = _full_brief()
    routed = patched_builders.format_discord_messages_routed(brief)
    legacy = patched_builders.format_discord_messages(brief)
    assert len(routed) == len(legacy)
    for (_kind, routed_msg), legacy_msg in zip(routed, legacy):
        assert routed_msg == legacy_msg


# ────────────────────────────────────────────────────────────────────────────
# main() no-Discord branch — must iterate `routed`, not a stale `messages`
# ────────────────────────────────────────────────────────────────────────────

def test_no_discord_branch_does_not_NameError(monkeypatch, capsys, tmp_path):
    """Exercise main()'s no-Discord branch (BRIEF_AS_OF replay, --no-discord,
    or DISCORD_WEBHOOK_URL unset) and confirm it iterates `routed`."""
    import gcp.premarket_brief as pb

    monkeypatch.setattr(pb, 'load_config',
                        lambda: type('Cfg', (), {
                            'market': type('M', (), {'data_dir': str(tmp_path)})(),
                            'monitor': type('Mon', (), {'discord_timeout': 5})(),
                        })())
    monkeypatch.setattr(pb, 'generate_premarket_brief', lambda **kwargs: {})
    monkeypatch.setattr(pb, 'persist_to_cloud_sql', lambda *a, **kw: 0)
    monkeypatch.setattr(pb, '_resolve_run_kind_and_update',
                        lambda *a, **kw: (False, 'scheduled'))
    monkeypatch.setattr(pb, 'format_discord_messages_routed',
                        lambda b: [
                            ('main', {'embeds': [{'title': 'X'}]}),
                            ('earnings', {'embeds': [{'title': 'Y'}]}),
                        ])
    monkeypatch.delenv('DISCORD_WEBHOOK_URL', raising=False)
    monkeypatch.delenv('DISCORD_WEBHOOK_EARNINGS_URL', raising=False)
    monkeypatch.delenv('BRIEF_AS_OF', raising=False)
    monkeypatch.setattr(pb.sys, 'argv', ['premarket_brief', '--no-discord'])

    pb.main()

    out = capsys.readouterr().out
    assert 'channel=main' in out
    assert 'channel=earnings' in out
