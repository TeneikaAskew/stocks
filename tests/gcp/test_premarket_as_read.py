"""The premarket bars as each refresh run read them (FEAT-DATA-001).

docs/superpowers/specs/2026-11-16-feat-data-001-premarket-reads-as-read.md:
the vendor revises a session's one-minute bars after the close, so the
refresh job keeps, for SPY, QQQ and IWM, the bars it read, the request it
sent and the values it upserted, one object per ticker per run.

Hermetic: the vendor is a patched ``requests.get``; nothing here reaches a
network, a bucket or a database.
"""
from __future__ import annotations

from gcp.fetchers import fetch_market_data


class _Reply:
    """A vendor reply: ``json()`` returns the body given."""

    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def test_record_carries_the_request_as_sent(monkeypatch):
    """R2: the request the record stores is the request fetch_minute_bars
    sends, built by one function, without the key."""
    sent = []

    def fake_get(url, params=None, timeout=None):
        sent.append(dict(params))
        return _Reply({'Time Series (1min)': {
            '2026-11-16 04:00:00': {'1. open': '752.5', '2. high': '752.6',
                                    '3. low': '752.4', '4. close': '752.5',
                                    '5. volume': '500'}}})

    monkeypatch.setattr(fetch_market_data.requests, 'get', fake_get)
    bars, reason = fetch_market_data.fetch_minute_bars('SPY', '2026-11-16', 'TEST-KEY-not-real')
    assert reason == fetch_market_data.FETCH_OK and len(bars) == 1

    request = fetch_market_data.minute_bars_request('SPY', '2026-11')
    (params,) = sent
    assert params == {**request, 'apikey': 'TEST-KEY-not-real'}
    assert request['entitlement'] == 'realtime'
    assert request['adjusted'] == 'false'
    assert request['extended_hours'] == 'true'
    assert 'apikey' not in request
