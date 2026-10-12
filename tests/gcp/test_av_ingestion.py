import base64
import gzip
import hashlib
import json
import multiprocessing
import time
from datetime import datetime, timezone

import pytest

from gcp.fetchers import _av_ingestion as av


def test_exact_archive_and_failure_contract(monkeypatch):
    body = b'{ "quarterlyEarnings": [], "symbol": "AAPL" }\n'
    capture = av.Capture.from_bytes("EARNINGS", {"symbol": "AAPL", "apikey": "SENTINEL"}, body)
    stored = {}

    class Blob:
        def upload_from_string(self, payload, **kw):
            assert kw["if_generation_match"] == 0
            assert kw["retry"] is None
            stored["payload"] = payload

    class Bucket:
        def blob(self, name):
            assert name.startswith("av/raw/")
            return Blob()

    class Client:
        def bucket(self, name):
            assert name == "test-bucket"
            return Bucket()

    monkeypatch.setattr(av, "bounded_call", lambda fn, timeout_s, **kw: fn())
    uri = av.archive_capture(capture, bucket="test-bucket", client=Client())
    envelope = json.loads(gzip.decompress(stored["payload"]))
    assert base64.b64decode(envelope["body_base64"]) == body
    assert envelope["body_sha256"] == hashlib.sha256(body).hexdigest()
    assert "SENTINEL" not in json.dumps(envelope)
    assert uri.startswith("gs://test-bucket/av/raw/")
    assert av.archive_capture(capture, dry_run=True, client=Client()) is None
    with pytest.raises(av.SourceError, match="archive_configuration"):
        av.archive_capture(capture, bucket="")
    class BadClient:
        def bucket(self, _):
            raise RuntimeError("https://vendor/?apikey=SENTINEL")
    with pytest.raises(av.SourceError, match="archive_failed") as e:
        av.archive_capture(capture, bucket="b", client=BadClient())
    assert "SENTINEL" not in str(e.value)


def test_actual_process_deadline_cancels_and_reaps():
    before = {p.pid for p in multiprocessing.active_children()}
    started = time.monotonic()
    with pytest.raises(av.SourceError, match="deadline"):
        av.bounded_call(lambda: time.sleep(60), 0.1)
    assert time.monotonic() - started < 1.3
    assert {p.pid for p in multiprocessing.active_children()} == before


def test_source_identity_preserves_null_and_normalizes_numbers():
    a = {"ticker": "AAPL", "transaction_date": "2026-10-09", "executive": None,
         "transaction_type": "A", "shares": 10, "share_price": "1.00"}
    b = dict(a, shares="10.0", share_price=1)
    assert av.source_identity("insider_transactions", a) == av.source_identity("insider_transactions", b)
    assert av.source_identity("insider_transactions", a) != av.source_identity("insider_transactions", dict(a, executive=""))
    article = {"ticker": "IWM", "published_ts": datetime(2026, 10, 9, tzinfo=timezone.utc),
               "url": None, "title": "Article", "source": "wire", "sentiment_score": None}
    assert av.source_identity("news_sentiment", article) == av.source_identity("news_sentiment", dict(article, sentiment_score=.5))
