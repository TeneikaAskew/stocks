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


def test_load_watchlist_user_scoped_empty_does_not_use_global_fallback(monkeypatch):
    """A signed-in user's empty watchlist is a valid empty result — it must
    NOT fall through to the global INSIGHT_TICKERS list (per-user isolation).
    The env fallback / alert is reserved for the shared 'default' owner."""
    _stub_cloud_sql(monkeypatch, [])
    monkeypatch.setenv("INSIGHT_TICKERS", "tsla,amzn")  # set, but must be ignored
    alerts = _stub_alert(monkeypatch)

    from gcp.fetchers._watchlist import load_watchlist
    assert load_watchlist(user_id="alice@example.com") == []
    # No fallback alert for a normal empty personal watchlist.
    assert alerts == []


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


# ---------------------------------------------------------------------------
# As-of membership resolution (watchlist_history)
#
# The resolver's ANSWER is tested against a real Postgres in
# tests/integration/test_watchlist_history.py — it reads a table maintained
# by a database trigger, and a mocked connection would only prove the mock
# fired. What belongs here are the properties that are checkable without a
# database and that a local/CI run would otherwise pass over.
# ---------------------------------------------------------------------------


def test_membership_sql_uses_positional_placeholders():
    """Named placeholders would pass every local and CI test and fail only
    in production.

    `lib.agents.model_routing.connect()` returns psycopg2 locally and under
    CLOUD_SQL_URL, but pg8000 through the Cloud SQL Connector in production
    — and pg8000's paramstyle is `format`, not `pyformat`. `%(owner)s`
    raises there while working everywhere a test can reach. Measured
    2026-09-18: pg8000 1.31.5, `paramstyle == 'format'`.
    """
    from gcp.fetchers import _watchlist

    for name in ("_MEMBERSHIP_AT_SQL", "_HORIZON_SQL"):
        sql = getattr(_watchlist, name)
        assert "%(" not in sql, (
            f"{name} uses named placeholders; pg8000 cannot bind them and "
            "this is only reachable in production"
        )


def test_membership_resolution_does_not_swallow_database_errors():
    """`_load_from_cloud_sql` above returns [] on any error so callers can
    fall through to file/env. The as-of resolver must NOT copy that: a
    caller that cannot tell "nobody was watchlisted on that date" from "the
    query failed" computes analog statistics over the wrong universe and
    reports them as fact (CLAUDE.md Rule 3.7).
    """
    import datetime

    from gcp.fetchers import _watchlist

    class _Boom:
        def cursor(self):
            raise RuntimeError("connection reset by peer")

        def close(self):
            return None

    import lib.agents.model_routing as mr

    original = mr.connect
    mr.connect = lambda: _Boom()
    try:
        with pytest.raises(RuntimeError, match="connection reset"):
            _watchlist.resolve_membership_at(datetime.date(2026, 9, 15))
    finally:
        mr.connect = original


def test_an_aware_datetime_cutoff_resolves_instead_of_raising():
    """`parse_as_of` returns `Union[date, datetime]` — an aware datetime for
    the `YYYY-MM-DDTHH:MM:SSZ` form — and `summarize_backtest_metrics` passes
    its `cutoff` straight through. `datetime` is a subclass of `date`, so it
    satisfies the annotation and reaches the horizon comparison, where
    `aware_datetime < horizon.date()` raises
    `TypeError: can't compare datetime.datetime to datetime.date`.

    Production has seed rows and therefore a non-null horizon, so every
    timestamp-cutoff replay that needs cross-ticker expansion lost the whole
    backtest section (Codex P2 on `775a29f`). The resolver normalizes to the
    calendar date its own SQL already reads off the input.
    """
    import datetime as _dt

    from gcp.fetchers import _watchlist

    class _Cur:
        def __init__(self):
            self.n = 0

        def execute(self, sql, params=None):
            self.n += 1

        def fetchall(self):
            return [("AMD",), ("NVDA",)]

        def fetchone(self):
            return (_dt.datetime(2026, 4, 27, tzinfo=_dt.timezone.utc),)

    class _Conn:
        def cursor(self):
            return _Cur()

        def close(self):
            return None

    import lib.agents.model_routing as mr

    original = mr.connect
    mr.connect = lambda: _Conn()
    try:
        aware = _dt.datetime(2026, 9, 15, 14, 30, tzinfo=_dt.timezone.utc)
        resolved = _watchlist.resolve_membership_at(aware)
    finally:
        mr.connect = original

    assert resolved.tickers == ("AMD", "NVDA")
    # Normalized, not carried through as a datetime: the dataclass is what
    # the report records and a caller comparing it to a date must not blow up
    # for the same reason the horizon comparison did.
    assert resolved.as_of == _dt.date(2026, 9, 15)
    assert not isinstance(resolved.as_of, _dt.datetime)
    assert resolved.resolution == "exact"
