"""Unit tests for `gcp/fetchers/_watchlist.py`.

Single source of truth: `watchlists` Cloud SQL table.

Tests verify:
    - Resolution order: Cloud SQL → INSIGHT_TICKERS env → []
    - The Cloud SQL path returns [] gracefully when DB is unreachable
    - `_dedupe_upper` order preservation + case normalization
    - `_surface_predicate` produces the correct SQL fragment per surface
    - 'signals' surface filter is supported (added in the refactor that
      removed the legacy alert_config.json watchlist fallback)
    - Discord fallback alert fires only when ALL layers are empty
    - Invalid surface raises ValueError (typo guard)
"""

from __future__ import annotations

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
# _surface_predicate — SQL fragment per surface
# ──────────────────────────────────────────────────────────────────────


def test_surface_predicate_all_returns_empty_string():
    from gcp.fetchers._watchlist import _surface_predicate

    assert _surface_predicate("all") == ""


def test_surface_predicate_brief_filters_in_brief():
    from gcp.fetchers._watchlist import _surface_predicate

    assert _surface_predicate("brief") == " AND in_brief = TRUE"


def test_surface_predicate_insight_filters_in_insight():
    from gcp.fetchers._watchlist import _surface_predicate

    assert _surface_predicate("insight") == " AND in_insight = TRUE"


def test_surface_predicate_signals_filters_signals_column():
    """The signals surface was added when the legacy alert_config.json
    watchlist fallback was removed — every consumer now reads from the
    watchlists table with a per-surface filter, signals being the live
    signal-monitor's filter."""
    from gcp.fetchers._watchlist import _surface_predicate

    assert _surface_predicate("signals") == " AND signals = TRUE"


def test_surface_predicate_invalid_raises_value_error():
    from gcp.fetchers._watchlist import _surface_predicate

    with pytest.raises(ValueError, match="surface must be one of"):
        _surface_predicate("garbage")


# ──────────────────────────────────────────────────────────────────────
# load_watchlist — resolution chain (no JSON fallback)
# ──────────────────────────────────────────────────────────────────────


def _stub_cloud_sql(monkeypatch, ret_value):
    """Replace _load_from_cloud_sql with a stub returning the given list."""
    from gcp.fetchers import _watchlist as wl_module
    monkeypatch.setattr(wl_module, "_load_from_cloud_sql", lambda **_kw: ret_value)


def _stub_alert(monkeypatch):
    """Stub the Discord fallback alert to capture invocations."""
    from gcp.fetchers import _watchlist as wl_module
    calls: list[str] = []
    monkeypatch.setattr(wl_module, "_post_fallback_alert", lambda reason: calls.append(reason))
    return calls


def test_load_watchlist_prefers_cloud_sql(monkeypatch):
    """When Cloud SQL has rows, env is ignored."""
    _stub_cloud_sql(monkeypatch, ["NVDA", "MSFT", "AVGO"])
    monkeypatch.setenv("INSIGHT_TICKERS", "FROM_ENV")

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == ["NVDA", "MSFT", "AVGO"]


def test_load_watchlist_falls_back_to_env_when_sql_empty(monkeypatch):
    """Cloud SQL empty → use INSIGHT_TICKERS env var."""
    _stub_cloud_sql(monkeypatch, [])
    monkeypatch.setenv("INSIGHT_TICKERS", "tsla,amzn,tsla")

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == ["TSLA", "AMZN"]


def test_load_watchlist_returns_empty_when_sql_and_env_empty(monkeypatch):
    """Both layers empty → fire alert and return []."""
    _stub_cloud_sql(monkeypatch, [])
    monkeypatch.delenv("INSIGHT_TICKERS", raising=False)
    alerts = _stub_alert(monkeypatch)

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == []
    # The all-empty path triggers an observability alert
    assert len(alerts) == 1
    assert "watchlists" in alerts[0].lower()


def test_load_watchlist_does_not_alert_when_any_layer_returns_data(monkeypatch):
    """The fallback alert is reserved for the all-empty case."""
    _stub_cloud_sql(monkeypatch, ["SPY"])
    monkeypatch.delenv("INSIGHT_TICKERS", raising=False)
    alerts = _stub_alert(monkeypatch)

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist() == ["SPY"]
    assert alerts == []


def test_load_watchlist_signals_surface_passes_filter_to_sql(monkeypatch):
    """The signals surface must propagate to the Cloud SQL loader so
    signal_monitor's startup query filters on signals = TRUE."""
    captured: dict = {}

    def _capture(**kwargs):
        captured.update(kwargs)
        return ["IWM", "QQQ", "SPY"]

    from gcp.fetchers import _watchlist as wl_module
    monkeypatch.setattr(wl_module, "_load_from_cloud_sql", _capture)

    from gcp.fetchers._watchlist import load_watchlist
    out = load_watchlist(surface="signals")
    assert out == ["IWM", "QQQ", "SPY"]
    assert captured.get("surface") == "signals"


def test_load_watchlist_invalid_surface_raises_value_error(monkeypatch):
    from gcp.fetchers._watchlist import load_watchlist

    with pytest.raises(ValueError, match="surface must be one of"):
        load_watchlist(surface="garbage")


def test_load_watchlist_alert_fallback_message_mentions_surface(monkeypatch):
    """The fallback alert should tell the operator WHICH surface failed —
    'signals' is empty has different remediation than 'brief' is empty."""
    _stub_cloud_sql(monkeypatch, [])
    monkeypatch.delenv("INSIGHT_TICKERS", raising=False)
    alerts = _stub_alert(monkeypatch)

    from gcp.fetchers._watchlist import load_watchlist
    load_watchlist(surface="signals")
    assert len(alerts) == 1
    assert "signals" in alerts[0]


# ──────────────────────────────────────────────────────────────────────
# _post_fallback_alert — Discord webhook plumbing
# ──────────────────────────────────────────────────────────────────────


def test_fallback_alert_no_op_when_webhook_unset(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    from gcp.fetchers._watchlist import _post_fallback_alert
    # Should not raise even with no webhook set
    _post_fallback_alert("test reason")


def test_fallback_alert_posts_to_webhook_when_configured(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")

    posted: list[dict] = []
    import requests
    def _fake_post(url, json, timeout):
        posted.append({"url": url, "json": json, "timeout": timeout})
        class _Resp: status_code = 204
        return _Resp()
    monkeypatch.setattr(requests, "post", _fake_post)

    from gcp.fetchers._watchlist import _post_fallback_alert
    _post_fallback_alert("test reason")
    assert len(posted) == 1
    assert "test reason" in posted[0]["json"]["content"]
