"""Permanent catalyst vintages: explicit aware cutoffs, never cache fallback."""
from datetime import date, datetime, time, timedelta, timezone
from lib.eastern_time import ET

from gcp.database import query_to_dataframe_strict


def aware_cutoff(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of must be an aware datetime")
    return value.astimezone(timezone.utc)


def exchange_date_cutoff(value: str):
    session = date.fromisoformat(value)
    return (datetime.combine(session + timedelta(days=1), time(), ET)
            - timedelta(microseconds=1)).astimezone(timezone.utc)


def read_earnings_asof(ticker, as_of, *, limit=100, timeout_s=5):
    cutoff = aware_cutoff(as_of)
    if not 1 <= limit <= 100:
        raise ValueError("limit must be in 1..100")
    df = query_to_dataframe_strict("""
        SELECT * FROM (
          SELECT DISTINCT ON (fiscal_date_ending)
            revision_id,ticker,fiscal_date_ending,known_at,availability_quality,
            payload,value_sha256,source_fetch_id,source_retrieved_at,raw_uri,
            raw_sha256,yahoo_timing_observation_id
          FROM earnings_history_revisions
          WHERE ticker=:ticker AND known_at <= :as_of
            AND (payload->>'reported_date')::date <= (:as_of AT TIME ZONE 'America/New_York')::date
          ORDER BY fiscal_date_ending,known_at DESC,revision_id DESC
        ) eligible ORDER BY fiscal_date_ending DESC LIMIT :limit
    """, {"ticker": ticker.upper(), "as_of": cutoff, "limit": limit}, timeout_s=timeout_s)
    if df.empty:
        return {"status": "unavailable", "reason": "pre_observation_coverage_gap",
                "records": [], "cutoff": cutoff.isoformat()}
    records = []
    for source in df.to_dict("records"):
        payload = source.pop("payload")
        records.append({**payload, **source})
    return {"status": "ok", "records": records, "cutoff": cutoff.isoformat(),
            "availability_quality": sorted({r["availability_quality"] for r in records})}


def read_estimates_asof(ticker, as_of, *, limit=100, timeout_s=5):
    cutoff = aware_cutoff(as_of)
    if not 1 <= limit <= 100:
        raise ValueError("limit must be in 1..100")
    df = query_to_dataframe_strict("""
        SELECT * FROM (
          SELECT DISTINCT ON (o.fiscal_date_ending,o.horizon)
            o.observation_id,o.fetch_id,o.ticker,o.fiscal_date_ending,o.horizon,
            o.known_at AS observation_known_at,o.source_retrieved_at,o.raw_uri,o.raw_sha256,o.payload,
            GREATEST(r.source_commit_acknowledged_at,p.known_at) AS known_at,
            r.source_commit_acknowledged_at,r.observation_count,
            m.manifest_id AS source_manifest_id,m.manifest AS source_manifest,
            p.known_at AS source_manifest_known_at,j.note AS terminal_note
          FROM av_earnings_estimates_observations o
          JOIN av_estimate_receipt_publications r ON r.fetch_id=o.fetch_id AND r.ticker=o.ticker
            AND r.validation_status='validated' AND r.source_commit_acknowledged_at<=:as_of
          JOIN av_catalyst_source_captures c ON c.capture_id=o.fetch_id
            AND c.function='EARNINGS_ESTIMATES' AND c.ticker=o.ticker
            AND c.validation_status=r.validation_status AND c.normalized_count=r.observation_count
            AND c.raw_uri=o.raw_uri AND c.raw_sha256=o.raw_sha256
            AND c.source_retrieved_at=o.source_retrieved_at AND c.source_retrieved_at<=r.source_commit_acknowledged_at
          JOIN av_catalyst_source_manifests m ON m.job_name='fetch-av-earnings-estimates'
            AND m.variant='daily' AND m.manifest->>'pipeline_scope'='estimates_daily'
            AND m.manifest->'captured_receipts' @> jsonb_build_array(jsonb_build_object('fetch_id',o.fetch_id::text))
          JOIN av_catalyst_manifest_publications p ON p.manifest_id=m.manifest_id
            AND p.known_at>=r.source_commit_acknowledged_at AND p.known_at<=:as_of
          JOIN job_runs j ON j.job_name=m.job_name AND j.variant=m.variant AND j.execution_name=m.execution_name
            AND j.finished_at<=:as_of AND j.status IN ('success','no_data','partial')
            AND j.note::jsonb->>'source_manifest_id'=m.manifest_id::text
          WHERE o.ticker=:ticker AND o.known_at<=r.source_commit_acknowledged_at
          ORDER BY o.fiscal_date_ending,o.horizon,r.source_commit_acknowledged_at DESC,
            p.known_at DESC,o.observation_id DESC
        ) eligible ORDER BY fiscal_date_ending DESC,horizon LIMIT :limit
    """, {"ticker": ticker.upper(), "as_of": cutoff, "limit": limit}, timeout_s=timeout_s)
    # Validate the exact stored body and receipt, rather than trusting an ID
    # appearing in a terminal note or treating a pre-transaction clock as ACK.
    from gcp.fetchers import _av_ingestion as av
    records=[]
    for row in df.to_dict('records'):
        manifest=row.pop('source_manifest')
        note=av.parse_manifest_json(row.pop('terminal_note'))
        receipt={'ticker':row['ticker'],'fetch_id':str(row['fetch_id']),'status':'validated',
            'source_retrieved_at':av.clock_string(row['source_retrieved_at']),
            'known_at':av.clock_string(row.pop('source_commit_acknowledged_at')),
            'raw_sha256':row['raw_sha256'],'raw_uri':row['raw_uri'],
            'observation_count':row.pop('observation_count')}
        if (note.get('manifest_sha256')!=av.manifest_digest(manifest)
            or note.get('manifest_bytes')!=len(av.manifest_bytes(manifest))
            or aware_cutoff(datetime.fromisoformat(note['source_manifest_known_at']))!=row['source_manifest_known_at']
            or receipt not in manifest.get('captured_receipts',[])):
            return {'status':'unavailable','reason':'publication_provenance_mismatch','records':[],
                    'cutoff':cutoff.isoformat()}
        row['source_manifest_id']=str(row['source_manifest_id'])
        records.append(row)
    return {"status": "ok" if records else "unavailable", "records": records,
            "cutoff": cutoff.isoformat(), **({"reason": "pre_observation_coverage_gap"} if df.empty else {})}
