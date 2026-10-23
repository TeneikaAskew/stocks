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


def test_revision_installation_is_one_real_applier_transaction():
    from pathlib import Path
    from gcp.apply_schema import split_statement_groups
    sql=Path('gcp/schema.sql').read_text().split('-- BEGIN AV CATALYST REVISIONS')[1].split('-- END AV CATALYST REVISIONS')[0]
    units=split_statement_groups(sql)
    assert len(units)==1 and len(units[0])>10
    assert not any(statement.strip().upper() in {'BEGIN;','COMMIT;'} for statement in units[0])


def test_actual_trickling_http_and_blocked_archive_are_cancelled():
    import threading
    from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.end_headers()
            try:
                for _ in range(100):
                    self.wfile.write(b'x');self.wfile.flush();time.sleep(.05)
            except (BrokenPipeError,ConnectionResetError):pass
        def log_message(self,*a):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url='http://127.0.0.1:'+str(server.server_port)
    before={p.pid for p in multiprocessing.active_children()}
    started=time.monotonic()
    try:
        with pytest.raises(av.SourceError,match='deadline'):
            av.bounded_call(lambda:av._request_body('EARNINGS',{'symbol':'IWM'},'dummy',url=url,timeout_s=2),.6)
        assert time.monotonic()-started<1.7
        assert {p.pid for p in multiprocessing.active_children()}==before
        class Blob:
            def upload_from_string(self,*a,**kw):time.sleep(60)
        class Bucket:
            def blob(self,*a):return Blob()
        class Client:
            def bucket(self,*a):return Bucket()
        capture=av.Capture.from_bytes('EARNINGS',{'symbol':'IWM'},b'{}')
        started=time.monotonic()
        with pytest.raises(av.SourceError,match='archive_failed'):
            av.archive_capture(capture,bucket='dummy',client=Client(),timeout_s=.3)
        assert time.monotonic()-started<1.4
        assert {p.pid for p in multiprocessing.active_children()}==before
    finally:
        server.shutdown();server.server_close();thread.join(1)


def test_actual_blocked_database_acquisition_is_cancelled(monkeypatch):
    import socket,threading
    for selector in ['CLOUD_SQL_CONNECTION_NAME','CLOUD_SQL_URL','GOOGLE_APPLICATION_CREDENTIALS']:
        monkeypatch.delenv(selector,raising=False)
    server=socket.socket();server.bind(('127.0.0.1',0));server.listen()
    monkeypatch.setenv('DB_HOST','127.0.0.1');monkeypatch.setenv('DB_PORT',str(server.getsockname()[1]))
    monkeypatch.setenv('DB_NAME','av_catalysts');monkeypatch.setenv('DB_USER','trading_user');monkeypatch.setenv('DB_PASS','testpass')
    # This server accepts TCP and deliberately never completes PostgreSQL auth.
    peers=[]
    def accept():
        try:peers.append(server.accept()[0])
        except OSError:pass
    thread=threading.Thread(target=accept,daemon=True);thread.start()
    av.close_sql_worker();before={p.pid for p in multiprocessing.active_children()}
    started=time.monotonic()
    try:
        with pytest.raises(av.SourceError,match='database_outcome_unavailable'):
            av.isolated_sql('SELECT 1',read=True,timeout_s=1)
        assert time.monotonic()-started<2.1
        assert {p.pid for p in multiprocessing.active_children()}==before
    finally:
        av.close_sql_worker();server.close()
        for peer in peers:peer.close()
        thread.join(.1)
