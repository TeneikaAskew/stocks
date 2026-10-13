"""Bounded source capture, immutable archives and catalyst run contracts.

This module has no vendor/database I/O at import time. Error messages contain
controlled classifications only; request URLs and vendor exception text never
cross a worker boundary or enter telemetry.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import math
import multiprocessing as mp
import os
import re
import subprocess
import threading
import time
import uuid
from functools import lru_cache
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Callable

UTC = timezone.utc
PIPELINE_VERSION = "av-catalyst/v1"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
_WORKER_PIPE = None
_SQL_SERVICE = None
_SQL_LOCK = threading.RLock()


class SourceError(RuntimeError):
    """A controlled source/availability classification with no raw exception."""


def canonical(value) -> str:
    def encode(v):
        if isinstance(v, (date, datetime)):
            return v.isoformat()
        if isinstance(v, (uuid.UUID, Decimal)):
            return str(v)
        if hasattr(v, "item"):
            return v.item()
        raise TypeError("unsupported_canonical_value")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=encode, allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_TERMINAL_BYTES = 64 * 1024


def manifest_bytes(value) -> bytes:
    """Strict scope/proof JSON; financial serialization remains separate."""
    def validate(item):
        if item is None or isinstance(item,bool):return
        if isinstance(item,int):
            if not -(2**63)<=item<2**63:raise SourceError('canonical_integer_range')
            return
        if isinstance(item,str):
            if any(0xD800<=ord(c)<=0xDFFF for c in item):raise SourceError('canonical_unicode')
            return
        if isinstance(item,list):
            for member in item:validate(member)
            return
        if isinstance(item,dict) and all(isinstance(k,str) for k in item):
            for key,member in item.items():validate(key);validate(member)
            return
        raise SourceError('canonical_projection_type_unavailable')
    validate(value)
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('utf-8')


def manifest_digest(value):
    return hashlib.sha256(manifest_bytes(value)).hexdigest()


def parse_manifest_json(raw):
    if not isinstance(raw,(str,bytes)) or len(raw.encode('utf-8') if isinstance(raw,str) else raw)>MAX_MANIFEST_BYTES:
        raise SourceError('manifest_json_byte_limit')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise SourceError('canonical_duplicate_key')
            result[key]=value
        return result
    try:result=json.loads(raw,object_pairs_hook=unique)
    except (ValueError,UnicodeError):raise SourceError('manifest_json_unavailable') from None
    manifest_bytes(result)
    return result


def clock_string(value):
    try:
        clock=datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) else value
        if not isinstance(clock,datetime) or clock.tzinfo is None or clock.utcoffset() is None:
            raise ValueError()
        return clock.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    except (ValueError,TypeError,OverflowError):raise SourceError('proof_clock_unavailable') from None


def symbol_scope(values):
    if not isinstance(values,(list,tuple)) or any(not isinstance(v,str) for v in values):
        raise SourceError('canonical_symbol_scope')
    symbols=sorted({v.strip().upper() for v in values})
    if any(not re.fullmatch(r'[A-Z0-9][A-Z0-9.-]{0,9}',v) for v in symbols):
        raise SourceError('canonical_symbol_scope')
    return symbols


def event_scope(values):
    result=[]
    for item in values:
        if set(item)!={'ticker','event_reported_date'}:raise SourceError('canonical_event_keys')
        day=item['event_reported_date']
        if isinstance(day,date) and not isinstance(day,datetime):day=day.isoformat()
        if not isinstance(day,str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',day):
            raise SourceError('canonical_event_date')
        try:date.fromisoformat(day)
        except ValueError:raise SourceError('canonical_event_date') from None
        result.append({'ticker':symbol_scope([item['ticker']])[0],'event_reported_date':day})
    return sorted(result,key=lambda item:(item['ticker'],item['event_reported_date']))


def safe_parameters(parameters: dict) -> dict:
    return {k: v for k, v in parameters.items()
            if k.lower() not in {"apikey", "api_key", "token", "password", "authorization"}}


@lru_cache(maxsize=1)
def _local_code_revision():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, timeout=2).strip()


def code_identity() -> dict:
    commit = os.environ.get("SOURCE_COMMIT")
    image = os.environ.get("SOURCE_IMAGE_DIGEST")
    if os.environ.get("CLOUD_RUN_JOB") and (not commit or not image):
        raise SourceError("code_identity_unavailable")
    if not commit:
        commit = _local_code_revision()
    return {"code_revision": commit, "image_digest": image, "pipeline_version": PIPELINE_VERSION}


def _child(pipe, serialized):
    global _WORKER_PIPE
    _WORKER_PIPE = pipe
    try:
        from joblib.externals import cloudpickle
        fn = cloudpickle.loads(serialized)
        pipe.send((True, fn()))
    except BaseException as exc:
        # Never transfer the raw exception, request or traceback.
        classification = str(exc) if isinstance(exc, SourceError) else type(exc).__name__
        pipe.send((False, classification))
    finally:
        pipe.close()


def emit_worker_event(event):
    if _WORKER_PIPE is not None:
        _WORKER_PIPE.send(("event", event))


def bounded_call(fn: Callable, timeout_s: float, *, error="operation_failed", on_event=None):
    """Supervise the actual operation, including import/acquisition/body reads.

    Spawn avoids inherited locks, credential-refresh threads and pooled
    connections. Children create their own DB engine/client. A committed
    write whose worker cannot acknowledge is an explicit unknown outcome;
    callers must reuse its immutable identity when reconciling, never backdate.
    """
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise SourceError("deadline_invalid")
    started = time.monotonic()
    from joblib.externals import cloudpickle
    serialized = cloudpickle.dumps(fn)
    recv, send = mp.get_context("spawn").Pipe(duplex=False)
    proc = mp.get_context("spawn").Process(target=_child, args=(send, serialized), daemon=True)
    proc.start()
    send.close()
    try:
        while True:
            remaining = max(0, timeout_s - (time.monotonic() - started))
            if not recv.poll(remaining):
                raise SourceError("deadline")
            try:
                ok, result = recv.recv()
            except EOFError:
                raise SourceError(error) from None
            if ok != "event":
                break
            if on_event:
                on_event(result)
        if not ok:
            raise SourceError(f"{error}:{result}") from None
        if time.monotonic() - started > timeout_s:
            raise SourceError("deadline_late_result")
        return result
    finally:
        recv.close()
        if proc.is_alive():
            proc.terminate()
        proc.join(timeout=.5)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=.5)
        if proc.is_alive():
            raise SourceError("worker_reap_failed")
        proc.close()


@dataclass(frozen=True)
class Capture:
    function: str
    parameters: dict
    body: bytes
    retrieved_at: datetime
    observation_id: str
    code: dict

    @classmethod
    def from_bytes(cls, function, parameters, body, *, retrieved_at=None, observation_id=None):
        if not isinstance(body, bytes):
            raise SourceError("source_bytes_missing")
        return cls(function, safe_parameters(parameters), body,
                   retrieved_at or datetime.now(UTC), observation_id or str(uuid.uuid4()), code_identity())

    @property
    def body_sha256(self):
        return hashlib.sha256(self.body).hexdigest()

    def metadata(self):
        return {"function": self.function, "safe_parameters": self.parameters,
                "query_sha256": digest(self.parameters), "retrieved_at": self.retrieved_at.isoformat(),
                "observation_id": self.observation_id, "body_sha256": self.body_sha256, **self.code}

    def json(self):
        try:
            value = json.loads(self.body)
        except (ValueError, UnicodeError):
            raise SourceError("malformed_json") from None
        if not isinstance(value, dict):
            raise SourceError("malformed_payload")
        if any(k in value for k in ("Information", "Note", "Error Message")):
            raise SourceError("vendor_error")
        return value


def _request_body(function,parameters,api_key,*,url="https://www.alphavantage.co/query",timeout_s=30,max_bytes=MAX_SOURCE_BYTES):
    import requests
    with requests.Session() as session:
        response=session.get(url,params={"function":function,**parameters,"apikey":api_key},
                             timeout=min(timeout_s,30),stream=True,allow_redirects=False)
        response.raise_for_status()
        if 300<=response.status_code<400:
            raise SourceError('unexpected_redirect')
        parts,count=[],0
        for piece in response.iter_content(chunk_size=65536):
            count+=len(piece)
            if count>max_bytes:raise SourceError('source_body_limit')
            parts.append(piece)
        return b''.join(parts),datetime.now(UTC)


def fetch_capture(function: str, parameters: dict, api_key: str, *, timeout_s=30, max_bytes=MAX_SOURCE_BYTES):
    # Parent supervisor bounds actual acquisition, streaming, parsing and cleanup.
    body,clock=bounded_call(lambda:_request_body(function,parameters,api_key,
                           timeout_s=timeout_s,max_bytes=max_bytes),timeout_s,error='transport_failed')
    return Capture.from_bytes(function, parameters, body, retrieved_at=clock)


def archive_capture(capture: Capture, *, bucket=None, client=None, dry_run=False, timeout_s=10):
    if dry_run:
        return None
    bucket = bucket if bucket is not None else os.environ.get("GCS_BUCKET", "")
    if not bucket:
        raise SourceError("archive_configuration")
    name = f"av/raw/{capture.function}/{capture.retrieved_at:%Y/%m/%d}/{capture.observation_id}.json.gz"
    envelope = {**capture.metadata(), "body_base64": base64.b64encode(capture.body).decode()}
    compressed = gzip.compress(canonical(envelope).encode(), mtime=0)
    def upload():
        nonlocal client
        if client is None:
            from google.cloud import storage
            client = storage.Client()
        blob = client.bucket(bucket).blob(name)
        try:
            blob.upload_from_string(compressed, content_type="application/gzip",
                                    if_generation_match=0, retry=None, timeout=timeout_s)
        except Exception as exc:
            from google.api_core.exceptions import PreconditionFailed
            if not isinstance(exc, PreconditionFailed):
                raise SourceError("archive_failed") from None
            existing = blob.download_as_bytes(retry=None, timeout=timeout_s)
            if existing != compressed:
                raise SourceError("archive_identity_collision")
        return f"gs://{bucket}/{name}"
    try:
        return bounded_call(upload, timeout_s, error="archive_failed")
    except Exception:
        raise SourceError("archive_failed") from None


def numeric_identity(value):
    if value is None:
        return None
    try:
        n = Decimal(str(value))
    except Exception:
        raise SourceError("malformed_numeric_identity") from None
    if not n.is_finite():
        return None
    return format(n.normalize(), "f")


def source_identity(table: str, row: dict) -> str:
    if table == "news_sentiment":
        ts = row["published_ts"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            raise SourceError("naive_news_identity")
        core = ["news/v1", row["ticker"].upper(), ts.astimezone(UTC).isoformat()]
        article = row.get("article_id") or row.get("url")
        core += ["article", article] if article else ["content", row.get("source"), row.get("title")]
    elif table == "insider_transactions":
        core = ["insider/v1", row["ticker"].upper(), str(row["transaction_date"]),
                row.get("executive"), row.get("transaction_type"),
                numeric_identity(row.get("shares")), numeric_identity(row.get("share_price"))]
    else:
        raise SourceError("unsupported_identity_table")
    return digest(core)


def prepare_identity_frame(frame, table):
    import pandas as pd
    result = frame.astype(object).where(pd.notna(frame), None).copy()
    result["source_identity_hash"] = [source_identity(table, r) for r in result.to_dict("records")]
    result["source_identity_quality"] = ["vendor_url" if table=="news_sentiment" and r.get("url")
                                          else "content_derived" if table=="news_sentiment" else "economic_key"
                                          for r in result.to_dict("records")]
    return result.drop_duplicates("source_identity_hash", keep="last")


def _sql_service(pipe):
    """One connection per invocation: no per-group engine/pool setup chatter."""
    connection = None
    try:
        from gcp.database import get_engine
        from sqlalchemy import text
        while True:
            request = pipe.recv()
            if request is None:
                return
            sql, params, read = request
            try:
                if connection is None:
                    connection = get_engine().connect().execution_options(isolation_level="AUTOCOMMIT")
                result = connection.execute(text(sql), params)
                answer = [dict(r) for r in result.mappings()] if read else result.rowcount
                pipe.send((True, answer))
            except Exception as exc:
                pipe.send((False, type(exc).__name__))
    except (EOFError, BrokenPipeError):
        pass
    finally:
        pipe.close()
        if connection is not None:
            connection.close()


def close_sql_worker():
    global _SQL_SERVICE
    if _SQL_SERVICE is None:
        return
    process, pipe = _SQL_SERVICE
    _SQL_SERVICE = None
    pipe.close()
    if process.is_alive():
        process.terminate()
    process.join(.5)
    if process.is_alive():
        process.kill(); process.join(.5)
    if process.is_alive():
        raise SourceError("database_worker_reap_failed")
    process.close()


def isolated_sql(sql, params=None, *, timeout_s=2, read=False):
    """Bound complete acquisition/statement/commit, not merely server execution.

    An uncertain commit remains unavailable. Immutable IDs permit safe explicit
    reconciliation; the producer never retries an uncertain write automatically.
    """
    global _SQL_SERVICE
    if not math.isfinite(timeout_s) or timeout_s<=0:
        raise SourceError("deadline_invalid")
    with _SQL_LOCK:
        started=time.monotonic()
        if _SQL_SERVICE is None:
            parent, child=mp.get_context("spawn").Pipe()
            process=mp.get_context("spawn").Process(target=_sql_service,args=(child,),daemon=True)
            process.start();child.close()
            _SQL_SERVICE=(process,parent)
        process, pipe=_SQL_SERVICE
        try:
            pipe.send((sql,params or {},read))
            if not pipe.poll(max(0,timeout_s-(time.monotonic()-started))):
                raise SourceError("database_outcome_unavailable:deadline")
            ok,result=pipe.recv()
            if not ok:
                raise SourceError(f"database_outcome_unavailable:{result}")
            if time.monotonic()-started>timeout_s:
                raise SourceError("database_outcome_unavailable:late_result")
            return result
        except (SourceError,EOFError,BrokenPipeError):
            close_sql_worker()
            raise SourceError("database_outcome_unavailable") from None


def read_dataframe(sql,params=None,*,timeout_s=5):
    """One supervised strict SELECT, including pool/connect and result receipt."""
    import pandas as pd
    return pd.DataFrame(isolated_sql(sql,params,read=True,timeout_s=timeout_s))


def capture_sql(captures):
    """One statement; caller combines this with its bounded row transaction."""
    return """
      INSERT INTO av_catalyst_source_captures(capture_id,function,ticker,
        source_retrieved_at,raw_uri,raw_sha256,metadata,validation_status,normalized_count)
      SELECT capture_id::uuid,function,ticker,source_retrieved_at::timestamptz,
        raw_uri,raw_sha256,metadata,validation_status,normalized_count
      FROM jsonb_to_recordset(CAST(:captures AS jsonb)) AS c(capture_id text,function text,ticker text,
        source_retrieved_at text,raw_uri text,raw_sha256 text,metadata jsonb,
        validation_status text,normalized_count integer)
      ON CONFLICT(capture_id) DO NOTHING
    """


def capture_record(capture, raw_uri, count, *, source_count=None):
    if not raw_uri:
        raise SourceError("archive_provenance_missing")
    return {"capture_id": capture.observation_id, "function": capture.function,
            "ticker": capture.parameters.get("symbol") or capture.parameters.get("tickers"),
            "source_retrieved_at": capture.retrieved_at.isoformat(), "raw_uri": raw_uri,
            "raw_sha256": capture.body_sha256, "metadata": capture.metadata(),
            "validation_status": "validated" if (count if source_count is None else source_count) else "validated_empty", "normalized_count": count}


IDENTITY_COLUMNS = {
    "news_sentiment": ["ticker", "published_ts", "title", "url", "summary", "sentiment_score",
                       "relevance_score", "overall_sentiment_score", "overall_sentiment_label", "topics", "source", "data_source", "match_method",
                       "source_identity_hash", "source_identity_quality", "source_capture_id"],
    "insider_transactions": ["ticker", "transaction_date", "executive", "title", "transaction_type", "shares",
                             "share_price", "transaction_value", "source_identity_hash", "source_identity_quality", "source_capture_id"]}


def identity_write_sql(table,final):
    if table not in IDENTITY_COLUMNS:
        raise SourceError('unsupported_identity_table')
    return f"SELECT av_write_identity_rows('{table}',CAST(:rows AS jsonb),{'true' if final else 'false'}) AS written_count"


def identity_state(table):
    rows = isolated_sql("SELECT phase FROM av_catalyst_identity_migrations WHERE table_name=:table", {"table": table}, read=True)
    if len(rows) != 1:
        raise SourceError("identity_migration_unknown")
    return rows[0]["phase"] == "final"


def backfill_identity_chunk(table, *, after_id=0, limit=5000, dry_run=False, executor=None):
    executor=executor or isolated_sql
    if table not in IDENTITY_COLUMNS or after_id<0 or not 1<=limit<=5000:
        raise SourceError('identity_backfill_admission')
    keys=['ticker','published_ts','url','source','title'] if table=='news_sentiment' else [
        'ticker','transaction_date','executive','transaction_type','shares','share_price']
    selected=executor(f"SELECT id,source_identity_hash,{','.join(keys)} FROM {table} WHERE id>:after ORDER BY id LIMIT :limit",
                      {'after':after_id,'limit':limit},read=True,timeout_s=8)
    updates=[]
    for row in selected:
        if row['source_identity_hash'] is None:
            updates.append({'id':row['id'],'identity':source_identity(table,row),'original':{k:row[k] for k in keys},
                            'quality':'content_derived' if table=='news_sentiment' and not row.get('url') else 'vendor_url' if table=='news_sentiment' else 'economic_key'})
    if updates and not dry_run:
        originals=','.join("'"+key+"',to_jsonb(t)->'"+key+"'" for key in keys)
        result=executor(f"""WITH changed AS(UPDATE {table} t SET source_identity_hash=d.identity,source_identity_quality=d.quality
          FROM jsonb_to_recordset(CAST(:updates AS jsonb)) d(id bigint,identity text,quality text,original jsonb)
          WHERE t.id=d.id AND t.source_identity_hash IS NULL AND jsonb_build_object({originals})=d.original RETURNING t.id)
          SELECT count(*) AS changed FROM changed""",{'updates':canonical(updates)},read=True,timeout_s=8)
        if result[0]['changed']!=len(updates):
            raise SourceError('identity_backfill_concurrent_change')
    return {'selected_count':len(selected),'changed_count':len(updates),
            'next_after_id':selected[-1]['id'] if selected else after_id,'complete':len(selected)<limit,'dry_run':dry_run}


def finalize_identity(table,writer_manifest,*,dry_run=False,executor=None):
    executor=executor or isolated_sql
    required={'gcp.fetchers.fetch_news_sentiment','gcp.backfill_ticker','gcp.fetchers.fetch_rss_news','scripts.backfill_news_sentiment'} if table=='news_sentiment' else {'gcp.fetchers.fetch_insider_transactions'}
    if table not in IDENTITY_COLUMNS or not writer_manifest.get('old_writers_drained') or not writer_manifest.get('verification_evidence_uri'):
        raise SourceError('identity_writer_checkpoint_unverified')
    facts=writer_manifest.get('writer_checks',{})
    if set(facts)!=required or any(not r.get('entrypoint_verified') or not r.get('inactive_old_commands_blocked')
        or r.get('identity_contract')!='av-source-identity/v1' or not r.get('source_commit') or not r.get('image_digest') for r in facts.values()):
        raise SourceError('identity_writer_checkpoint_unverified')
    problems=executor(f"""SELECT (SELECT count(*) FROM {table} WHERE source_identity_hash IS NULL) AS missing,
      (SELECT count(*) FROM(SELECT source_identity_hash FROM {table} GROUP BY source_identity_hash HAVING count(*)>1) duplicates) AS duplicated""",
      read=True,timeout_s=8)[0]
    if problems['missing'] or problems['duplicated']:
        raise SourceError('identity_duplicate_reconciliation_required')
    if dry_run:
        return {'table':table,'preflight':'verified','dry_run':True}
    index=f'av_{table}_identity_unique'
    existing=executor("SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE c.relname=:name AND i.indrelid=CAST(:table AS regclass)",{'name':index,'table':table},read=True,timeout_s=8)
    if existing and not existing[0]['indisvalid']:
        executor(f'DROP INDEX CONCURRENTLY {index}',timeout_s=30)
        existing=[]
    if not existing:
        executor(f'CREATE UNIQUE INDEX CONCURRENTLY {index} ON {table}(source_identity_hash)',timeout_s=30)
    # Only the acknowledged drain/preflight can authorize this final boundary.
    executor(f'ALTER TABLE {table} ALTER COLUMN source_identity_hash SET NOT NULL',timeout_s=30)
    executor("""UPDATE av_catalyst_identity_migrations SET phase='final',old_writers_drained=true,
      verified_writer_manifest=CAST(:manifest AS jsonb),checkpoint_at=clock_timestamp() WHERE table_name=:table""",
      {'manifest':canonical(writer_manifest),'table':table},timeout_s=8)
    return {'table':table,'phase':'final','index':index}


def claim_work(function, tickers, scope, owner, *, limit=100, force=False, dry_run=False, timeout_s=8):
    if not 1 <= limit <= 300 or len(tickers) > 10000:
        raise SourceError("work_admission_limit")
    tickers = sorted(set(t.upper() for t in tickers))
    if dry_run:
        return tickers[:limit]
    rows = isolated_sql("""SELECT ticker FROM av_claim_catalyst_work(:function,
      CAST(:tickers AS text[]),:scope,:owner,:limit,:force) ORDER BY ticker""", {"function": function, "tickers": tickers,
        "scope": scope, "owner": owner, "limit": limit, "force": force}, timeout_s=timeout_s, read=True)
    return [r["ticker"] for r in rows]


def finish_work(function, scope, outcomes, *, owner,timeout_s=8):
    if not outcomes:
        return
    isolated_sql("""UPDATE av_catalyst_work w SET lease_owner=NULL,lease_expires_at=NULL,
      failure_count=CASE WHEN o.success THEN 0 ELSE w.failure_count+1 END,
      next_retry_at=CASE WHEN o.success THEN NULL ELSE clock_timestamp()+
        LEAST(168,power(2,LEAST(w.failure_count,8))) * interval '1 hour' END,
      last_successful_observation_at=CASE WHEN o.success THEN o.observed_at ELSE w.last_successful_observation_at END
      FROM jsonb_to_recordset(CAST(:outcomes AS jsonb)) o(ticker text,success boolean,observed_at timestamptz)
      WHERE w.function=:function AND w.scope=:scope AND w.ticker=o.ticker AND w.lease_owner=:owner""",
      {"outcomes": canonical(outcomes), "function": function, "scope": scope,"owner":owner}, timeout_s=timeout_s)


def write_identity_group(table, rows, *, captures=(), final=False, outcomes=(), timeout_s=8):
    if len(rows) > (40000 if table == "news_sentiment" else 10000):
        raise SourceError("normalized_row_limit")
    payload = canonical(rows)
    if len(payload.encode()) > (64 if table == "news_sentiment" else 16)*1024*1024:
        raise SourceError("normalized_byte_limit")
    pieces=[]
    parameters={"rows":payload,"captures":canonical(list(captures)),"outcomes":canonical(list(outcomes))}
    if captures:
        pieces.append("captured AS("+capture_sql(captures)+" RETURNING capture_id)")
    if rows:
        write_sql=identity_write_sql(table,final)
        if write_sql.startswith("WITH "):
            insert_at=write_sql.index("\n      INSERT INTO ")
            pieces.append(write_sql[5:insert_at])
            write_sql=write_sql[insert_at:]
        pieces.append("written AS("+write_sql+")")
    if outcomes:
        pieces.append("""attempts AS(UPDATE av_catalyst_work w SET lease_owner=NULL,lease_expires_at=NULL,
          failure_count=CASE WHEN o.success THEN 0 ELSE w.failure_count+1 END,
          next_retry_at=CASE WHEN o.success THEN NULL ELSE clock_timestamp()+
            LEAST(168,power(2,LEAST(w.failure_count,8))) * interval '1 hour' END,
          last_successful_observation_at=CASE WHEN o.success THEN o.observed_at ELSE w.last_successful_observation_at END
          FROM jsonb_to_recordset(CAST(:outcomes AS jsonb)) o(function text,ticker text,scope text,success boolean,observed_at timestamptz,lease_owner text)
          WHERE w.function=o.function AND w.ticker=o.ticker AND w.scope=o.scope AND w.lease_owner=o.lease_owner RETURNING w.ticker)""")
    if pieces:
        # SELECT-based identity function is not a data-modifying CTE: it must
        # be referenced, otherwise PostgreSQL can discard the entire write.
        dependencies=' CROSS JOIN '.join('(SELECT count(*) FROM '+name+') '+name+'_count'
          for name in ['captured','written','attempts'] if any(piece.startswith(name+' AS') for piece in pieces))
        isolated_sql("WITH "+",".join(pieces)+" SELECT 1 FROM "+dependencies,parameters,timeout_s=timeout_s)
    return len(rows)


def publish_manifest(run, manifest, *, manifest_id=None, timeout_s=2):
    manifest_id = manifest_id or str(uuid.uuid4())
    body=dict(manifest)
    if run.groups and 'run_groups' not in body:body['run_groups']=run.groups
    encoded=manifest_bytes(body)
    if len(encoded)>MAX_MANIFEST_BYTES:raise SourceError('manifest_byte_limit')
    acknowledged=isolated_sql("""WITH inserted AS(
      INSERT INTO av_catalyst_source_manifests(manifest_id,job_name,variant,execution_name,manifest)
      VALUES(CAST(:id AS uuid),:job,:variant,:execution,CAST(:manifest AS jsonb)) ON CONFLICT DO NOTHING RETURNING manifest_id)
      SELECT manifest_id FROM inserted UNION ALL SELECT manifest_id FROM av_catalyst_source_manifests
      WHERE manifest_id=CAST(:id AS uuid) AND job_name=:job AND variant=:variant
        AND execution_name=:execution AND manifest=CAST(:manifest AS jsonb) LIMIT 1""",
      {"id": manifest_id, "job": run.job_name, "variant": run.mode, "execution": run.execution_name,
       "manifest": encoded.decode("utf-8")}, read=True,timeout_s=timeout_s)
    if len(acknowledged)!=1 or str(acknowledged[0]['manifest_id'])!=manifest_id:
        raise SourceError('manifest_identity_conflict_or_ack_unavailable')
    # This clock is captured only after the manifest/source transaction ACK.
    known = datetime.now(UTC)
    rows=isolated_sql("""WITH published AS(
      INSERT INTO av_catalyst_manifest_publications(manifest_id,known_at)
      VALUES(CAST(:id AS uuid),:known) ON CONFLICT DO NOTHING RETURNING known_at)
      SELECT known_at FROM published UNION ALL
      SELECT known_at FROM av_catalyst_manifest_publications WHERE manifest_id=CAST(:id AS uuid)
      LIMIT 1""", {"id": manifest_id, "known": known}, read=True,timeout_s=timeout_s)
    if len(rows)!=1:
        raise SourceError('manifest_publication_ack_unavailable')
    # Retry cannot replace the original availability clock with its new proposal.
    actual_known=rows[0]['known_at']
    # A retry must not adopt a future/naive pre-existing publication proposal.
    clock_string(actual_known)
    if actual_known>known:raise SourceError('manifest_publication_clock_unavailable')
    return {**body, "source_manifest_id": manifest_id, "source_manifest_known_at": actual_known.isoformat(),
            "manifest_sha256":hashlib.sha256(encoded).hexdigest(),"manifest_bytes":len(encoded),
            "manifest_schema_version":body.get("schema_version")}


@dataclass
class Run:
    job_name: str
    mode: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    execution_name: str = field(default_factory=lambda: os.environ.get("CLOUD_RUN_EXECUTION") or str(uuid.uuid4()))
    expected: int = 0
    attempted: int = 0
    processed: int = 0
    failed: int = 0
    pending: int = 0
    rows_written: int = 0
    request_attempts: int = 0
    application_retries: int = 0
    groups: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def status(self):
        if self.failed or self.pending:
            return "partial" if self.processed else "error"
        return "success" if self.rows_written else "no_data"

    def note(self):
        attempt = os.environ.get("CLOUD_RUN_TASK_ATTEMPT")
        return {"schema_version": "av_catalyst_run/v1", "execution_name": self.execution_name,
                "job_name": self.job_name, "mode": self.mode, "task_index": os.environ.get("CLOUD_RUN_TASK_INDEX"),
                "task_attempt": attempt, "task_attempt_unknown": attempt is None,
                "request_attempts": self.request_attempts, "application_retry_count": self.application_retries,
                "expected": self.expected, "attempted": self.attempted, "processed": self.processed,
                "failed": self.failed, "pending": self.pending, "rows_written": self.rows_written,
                "terminal_status": self.status, "groups": self.groups, "metrics": self.metrics,
                "pipeline_version":PIPELINE_VERSION,"code_revision":os.environ.get('SOURCE_COMMIT'),
                "image_digest":os.environ.get('SOURCE_IMAGE_DIGEST')}

    def terminal(self, *, dry_run=False, extra=None):
        import logging
        base=self.note()
        if extra and extra.get('source_manifest_id'):
            # Complete proof/group arrays are retained in the immutable SQL
            # body; the terminal log and TEXT note use identical references.
            base.pop('groups',None)
            base.update(groups_count=len(self.groups),details_omitted_count=len(self.groups))
            allowed={'schema_version','pipeline_scope','source_manifest_id','source_manifest_known_at',
              'manifest_sha256','manifest_bytes','manifest_schema_version','code_revision','image_digest','pipeline_version',
              'scope_hash','source_universe_scope_hash','selected_scope_hash','selected_count','universe_count',
              'requested_count','verified_count','excluded_count','pending_count','coverage_complete',
              'event_pending_count','source_universe_unknown_count','raw_refresh_pending','raw_refresh_status',
              'event_cohort_complete','full_current_cohort_status','source_scope_quality','source_window_start',
              'source_window_end','complete_through','history_source_manifest_id','predecessor_execution_name',
              'source_function','coverage_scope','native_csv_rows','source_all_coverage','business_subset_coverage'}
            note={**base,**{k:v for k,v in extra.items() if k in allowed}}
            reasons={}
            for group in self.groups:
                reason=group.get('error_class')
                if reason:reasons[str(reason)[:128]]=reasons.get(str(reason)[:128],0)+1
            note['error_summary']=[{'reason_class':key,'count':reasons[key]} for key in sorted(reasons)[:16]]
            note['error_classes_omitted']=max(0,len(reasons)-16)
        else:
            note={**base,**(extra or {})}
        encoded=canonical(note)
        if len(encoded.encode('utf-8'))>MAX_TERMINAL_BYTES:
            omitted=0
            for key in ('metrics','error_summary'):
                value=note.pop(key,None)
                if value:omitted+=len(value)
            note['optional_details_omitted_count']=omitted
            encoded=canonical(note)
        if len(encoded.encode('utf-8'))>MAX_TERMINAL_BYTES:
            self.failed+=1
            note={'schema_version':'av_catalyst_run/v1','job_name':self.job_name,'mode':self.mode,
              'execution_name':self.execution_name,'terminal_status':self.status,
              'error_class':'terminal_byte_limit','groups_count':len(self.groups),'details_omitted_count':len(self.groups)}
            # Failure notes retain exact ordinary identities; an oversized
            # required identity is explicitly replaced by its digest, never
            # truncated into a purported successfully certified identity.
            for key in ('job_name','mode','execution_name'):
                if len(note[key].encode('utf-8'))>512:
                    note[key+'_sha256']=hashlib.sha256(note.pop(key).encode('utf-8')).hexdigest()
                    note[key+'_omitted']=True
            encoded=canonical(note)
        logging.getLogger(__name__).info("%s", encoded)
        if not dry_run:
            try:
                finished=datetime.now(UTC)
                isolated_sql("""INSERT INTO job_runs(job_name,variant,execution_name,started_at,finished_at,duration_s,
                  status,items_total,items_processed,items_failed,rows_written,note)
                  VALUES(:job,:variant,:execution,:started,:finished,:duration,:status,:total,:processed,:failed,:rows,:note)""",
                  {'job':self.job_name,'variant':self.mode,'execution':self.execution_name,'started':self.started_at,
                   'finished':finished,'duration':(finished-self.started_at).total_seconds(),'status':self.status,
                   'total':self.expected,'processed':self.processed,'failed':self.failed+self.pending,
                   'rows':self.rows_written,'note':encoded},timeout_s=8)
                delivered=True
            except SourceError:
                delivered=False
            if not delivered:
                logging.getLogger(__name__).warning("terminal_delivery_unavailable")
                return 1
        return 0 if self.status in {"success", "no_data"} else 1


def main(argv=None):
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser(description='Staged catalyst identity migration; no financial evidence deletion')
    p.add_argument('--identity-table',choices=list(IDENTITY_COLUMNS),required=True)
    p.add_argument('--after-id',type=int,default=0)
    p.add_argument('--limit',type=int,default=5000)
    p.add_argument('--finalize-identities',action='store_true')
    p.add_argument('--writer-manifest')
    p.add_argument('--dry-run',action='store_true')
    args=p.parse_args(argv)
    try:
        if args.finalize_identities:
            if not args.writer_manifest:
                raise SourceError('identity_writer_checkpoint_unverified')
            result=finalize_identity(args.identity_table,json.loads(Path(args.writer_manifest).read_text()),dry_run=args.dry_run)
        else:
            result=backfill_identity_chunk(args.identity_table,after_id=args.after_id,limit=args.limit,dry_run=args.dry_run)
        print(canonical(result));return 0
    except SourceError as exc:
        print(canonical({'status':'unavailable','error_class':str(exc)}));return 1
    finally:
        close_sql_worker()


if __name__=='__main__':
    raise SystemExit(main())
