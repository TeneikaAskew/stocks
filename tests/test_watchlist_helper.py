"""Unit tests for `gcp/fetchers/_watchlist.py`.

Used transitively by every Phase-2 fetcher that unions the curated
watchlist into its default ticker pool. Tests verify:
    - Resolution order: alert_config.json → INSIGHT_TICKERS → []
    - `_dedupe_upper` order preservation + case normalization
    - Malformed JSON falls back to env without raising
"""

from __future__ import annotations

import json

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


class _FakePath:
    def __init__(self, exists, content=""):
        self._exists = exists
        self._content = content

    def exists(self):
        return self._exists

    def read_text(self):
        return self._content


def test_load_watchlist_prefers_alert_config(monkeypatch):
    _patch_cfg_path(monkeypatch, _FakePath(
        exists=True,
        content=json.dumps({"watchlist": ["nvda", "msft"]})
    ))
    monkeypatch.setenv("INSIGHT_TICKERS", "AAPL,GOOG")  # should be ignored

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == ["NVDA", "MSFT"]


def test_load_watchlist_falls_back_to_env_when_no_config(monkeypatch):
    _patch_cfg_path(monkeypatch, _FakePath(exists=False))
    monkeypatch.setenv("INSIGHT_TICKERS", "tsla,amzn,tsla")

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == ["TSLA", "AMZN"]


def test_load_watchlist_returns_empty_when_no_config_no_env(monkeypatch):
    _patch_cfg_path(monkeypatch, _FakePath(exists=False))
    monkeypatch.delenv("INSIGHT_TICKERS", raising=False)

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == []


def test_load_watchlist_handles_malformed_json(monkeypatch):
    """A broken alert_config.json must NOT crash the ranker — fall back
    to env. Logged as warning."""
    _patch_cfg_path(monkeypatch, _FakePath(exists=True, content="{not valid json"))
    monkeypatch.setenv("INSIGHT_TICKERS", "FALL,BACK")

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == ["FALL", "BACK"]


def test_load_watchlist_ignores_non_list_watchlist_field(monkeypatch):
    """A misconfigured watchlist key (e.g. string instead of list) is
    rejected — fall back rather than treat the string as iterable."""
    _patch_cfg_path(monkeypatch, _FakePath(
        exists=True,
        content=json.dumps({"watchlist": "SPY"})  # string, not list
    ))
    monkeypatch.setenv("INSIGHT_TICKERS", "FALL,BACK")

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == ["FALL", "BACK"]


def test_load_watchlist_empty_list_in_config_falls_back(monkeypatch):
    """Empty array in alert_config.json shouldn't suppress env fallback —
    treats absent and empty the same. (The `wl or []` guard handles this.)"""
    _patch_cfg_path(monkeypatch, _FakePath(
        exists=True,
        content=json.dumps({"watchlist": []})
    ))
    monkeypatch.setenv("INSIGHT_TICKERS", "FALLBACK")

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == ["FALLBACK"]
