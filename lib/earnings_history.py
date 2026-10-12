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
          SELECT DISTINCT ON (fiscal_date_ending,horizon) *
          FROM av_earnings_estimates_observations
          WHERE ticker=:ticker AND known_at <= :as_of
          ORDER BY fiscal_date_ending,horizon,known_at DESC,observation_id DESC
        ) eligible ORDER BY fiscal_date_ending DESC,horizon LIMIT :limit
    """, {"ticker": ticker.upper(), "as_of": cutoff, "limit": limit}, timeout_s=timeout_s)
    return {"status": "ok" if not df.empty else "unavailable", "records": df.to_dict("records"),
            "cutoff": cutoff.isoformat(), **({"reason": "pre_observation_coverage_gap"} if df.empty else {})}
