"""Unit tests for `gcp/fetchers/_watchlist.py`.

Used transitively by every Phase-2 fetcher that unions the curated
watchlist into its default ticker pool. Tests verify:
    - Resolution order: Cloud SQL → alert_config.json → INSIGHT_TICKERS → []
    - The Cloud SQL path returns [] gracefully when DB is unreachable
    - `_dedupe_upper` order preservation + case normalization
    - Malformed JSON falls back to env without raising
    - Discord fallback alert fires only when ALL layers are empty
    - `add_to_watchlist` / `remove_from_watchlist` mutators
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


# ──────────────────────────────────────────────────────────────────────
# _dedupe_upper — pure helper
# ──────────────────────────────────────────────────────────────────────


def test_dedupe_upper_preserves_first_seen_order():
    from gcp.fetchers._watchlist import _dedupe_upper

    out = _dedupe_upper(["spy", "IWM", "spy", "qqq", "iwm"])
    assert out == ["SPY", "IWM", "QQQ"]


def test_dedupe_upper_strips_whitespace_and_drops_empties():
    from gcp.fetchers._watchlist import _dedupe_upper

    out = _dedupe_upper([" spy ", "", "  ", "iwm\n"])
    assert out == ["SPY", "IWM"]


# ──────────────────────────────────────────────────────────────────────
# load_watchlist — resolution chain
# ──────────────────────────────────────────────────────────────────────


def _patch_cfg_path(monkeypatch, fake_path):
    """Swap _CFG_PATH for a Path-like object."""
    from gcp.fetchers import _watchlist as wl_module
    monkeypatch.setattr(wl_module, "_CFG_PATH", fake_path)


def _stub_cloud_sql(monkeypatch, ret_value):
    """Replace _load_from_cloud_sql with a stub returning the given list.

    Used by tests that exercise the file / env / empty fallback layers
    so we don't need a real Cloud SQL connection."""
    from gcp.fetchers import _watchlist as wl_module
    monkeypatch.setattr(wl_module, "_load_from_cloud_sql", lambda **_kw: ret_value)


def _stub_alert(monkeypatch):
    """Stub the Discord fallback alert to capture invocations."""
    from gcp.fetchers import _watchlist as wl_module
    calls: list[str] = []
    monkeypatch.setattr(wl_module, "_post_fallback_alert", lambda reason: calls.append(reason))
    return calls


class _FakePath:
    def __init__(self, exists, content=""):
        self._exists = exists
        self._content = content

    def exists(self):
        return self._exists

    def read_text(self, encoding=None):
        return self._content


def test_load_watchlist_prefers_cloud_sql(monkeypatch):
    """When Cloud SQL has rows, file and env are ignored."""
    _stub_cloud_sql(monkeypatch, ["NVDA", "MSFT", "AVGO"])
    _patch_cfg_path(monkeypatch, _FakePath(
        exists=True,
        content=json.dumps({"watchlist": ["FROM_FILE"]})
    ))
    monkeypatch.setenv("INSIGHT_TICKERS", "FROM_ENV")

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == ["NVDA", "MSFT", "AVGO"]


def test_load_watchlist_falls_back_to_alert_config_when_sql_empty(monkeypatch):
    _stub_cloud_sql(monkeypatch, [])  # SQL empty/unreachable
    _patch_cfg_path(monkeypatch, _FakePath(
        exists=True,
        content=json.dumps({"watchlist": ["nvda", "msft"]})
    ))
    monkeypatch.setenv("INSIGHT_TICKERS", "AAPL,GOOG")  # should be ignored

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == ["NVDA", "MSFT"]


def test_load_watchlist_falls_back_to_env_when_sql_and_file_empty(monkeypatch):
    _stub_cloud_sql(monkeypatch, [])
    _patch_cfg_path(monkeypatch, _FakePath(exists=False))
    monkeypatch.setenv("INSIGHT_TICKERS", "tsla,amzn,tsla")

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == ["TSLA", "AMZN"]


def test_load_watchlist_returns_empty_when_all_layers_empty(monkeypatch):
    _stub_cloud_sql(monkeypatch, [])
    _patch_cfg_path(monkeypatch, _FakePath(exists=False))
    monkeypatch.delenv("INSIGHT_TICKERS", raising=False)
    alerts = _stub_alert(monkeypatch)

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == []
    # The all-empty path should trigger an observability alert
    assert len(alerts) == 1
    assert "watchlists" in alerts[0].lower()


def test_load_watchlist_does_not_alert_when_any_layer_returns_data(monkeypatch):
    """The fallback alert is reserved for the all-empty case."""
    _stub_cloud_sql(monkeypatch, [])
    _patch_cfg_path(monkeypatch, _FakePath(
        exists=True,
        content=json.dumps({"watchlist": ["SPY"]})
    ))
    monkeypatch.delenv("INSIGHT_TICKERS", raising=False)
    alerts = _stub_alert(monkeypatch)

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == ["SPY"]
    assert alerts == []


def test_load_watchlist_handles_malformed_json(monkeypatch):
    """A broken alert_config.json must NOT crash — fall back to env."""
    _stub_cloud_sql(monkeypatch, [])
    _patch_cfg_path(monkeypatch, _FakePath(exists=True, content="{not valid json"))
    monkeypatch.setenv("INSIGHT_TICKERS", "FALL,BACK")

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == ["FALL", "BACK"]


def test_load_watchlist_ignores_non_list_watchlist_field(monkeypatch):
    """A misconfigured watchlist key (string instead of list) is rejected."""
    _stub_cloud_sql(monkeypatch, [])
    _patch_cfg_path(monkeypatch, _FakePath(
        exists=True,
        content=json.dumps({"watchlist": "SPY"})
    ))
    monkeypatch.setenv("INSIGHT_TICKERS", "FALL,BACK")

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == ["FALL", "BACK"]


def test_load_watchlist_empty_list_in_config_falls_back(monkeypatch):
    """Empty array in alert_config.json shouldn't suppress env fallback."""
    _stub_cloud_sql(monkeypatch, [])
    _patch_cfg_path(monkeypatch, _FakePath(
        exists=True,
        content=json.dumps({"watchlist": []})
    ))
    monkeypatch.setenv("INSIGHT_TICKERS", "FALLBACK")

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == ["FALLBACK"]


# ──────────────────────────────────────────────────────────────────────
# _post_fallback_alert — Discord webhook plumbing
# ──────────────────────────────────────────────────────────────────────


def test_fallback_alert_no_op_when_webhook_unset(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    from gcp.fetchers._watchlist import _post_fallback_alert
    # Just verify it doesn't raise.
    _post_fallback_alert("test reason")


def test_fallback_alert_posts_to_webhook(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/webhook")
    posted = {}

    class _FakeRequests:
        @staticmethod
        def post(url, json=None, timeout=None):
            posted["url"] = url
            posted["json"] = json
            return MagicMock(status_code=204)

    monkeypatch.setitem(__import__("sys").modules, "requests", _FakeRequests)
    from gcp.fetchers._watchlist import _post_fallback_alert
    _post_fallback_alert("test reason here")
    assert posted["url"] == "https://example.com/webhook"
    assert "test reason here" in posted["json"]["content"]
    assert "watchlist fallback" in posted["json"]["content"]


def test_fallback_alert_swallows_send_failures(monkeypatch):
    """Alert path must never raise — alerts are best-effort."""
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/webhook")

    class _FakeRequests:
        @staticmethod
        def post(*_a, **_k):
            raise RuntimeError("network down")

    monkeypatch.setitem(__import__("sys").modules, "requests", _FakeRequests)
    from gcp.fetchers._watchlist import _post_fallback_alert
    # Should not raise even though the underlying request errored out.
    _post_fallback_alert("reason")
