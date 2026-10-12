#!/usr/bin/env python3
"""
Cloud Run Job: Fetch historical quarterly earnings from AV EARNINGS → Cloud SQL.

This is the *backward-looking* counterpart to fetch_earnings_calendar
(which pulls forward-only upcoming earnings). The AV `EARNINGS` endpoint
returns quarterly EPS history per ticker — `reportedDate`, `reportedEPS`,
`estimatedEPS`, `surprise`, `surprisePercentage` — going back 10+ years.

Used by the upcoming ranker to compute historical post-earnings reaction
stats (avg T+1 move, direction consistency, beat/miss streaks).

Ticker source priority:
  1. CLI --tickers override
  2. Cloud SQL earnings_calendar table — anyone reporting in the next
     ``--lookahead-days`` (default 90). Captures every name we'd want
     to rank without us maintaining a separate watchlist.

Usage:
    python -m gcp.fetchers.fetch_earnings_history
    python -m gcp.fetchers.fetch_earnings_history --tickers AAPL,MSFT,AVGO
    python -m gcp.fetchers.fetch_earnings_history --lookahead-days 30 --dry-run
"""

import argparse
import logging
import os
import sys
import time as time_module
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from lib.eastern_time import ET_NAME

from gcp.database import upsert_dataframe, is_cloud_sql_configured
from gcp.fetchers import _av_ingestion as av
from datetime import datetime, timezone
import json
import uuid
import math
from lib.config import AlphaVantageConfig
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

AV_BASE_URL = "https://www.alphavantage.co/query"
_av_cfg = AlphaVantageConfig()


def _safe_float(val) -> float | None:
    if val is None or val == "None" or val == "":
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    # AV returns "NaN" or float('nan') for upcoming-but-not-reported quarters.
    # Storing NaN in NUMERIC columns leaks placeholder rows past the
    # `reported_eps IS NOT NULL` filter (NaN is a value, not NULL).
    if not math.isfinite(f):
        return None
    return f


def _safe_str(val) -> str | None:
    """Normalize AV string fields. Returns None for missing / 'None' / empty."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("none", "null", "nan"):
        return None
    return s


def _yahoo_timing_from_event_dt(event_dt) -> str | None:
    """Derive 'pre-market' | 'post-market' from a Yahoo earnings event datetime.

    Yahoo's get_earnings_dates() returns timestamps in America/New_York. An
    event at 16:00 ET or later is post-market (AMC); an event at
    09:30 ET or earlier is pre-market (BMO). Anything in between is
    intraday — rare for earnings, treat as None so AV reportTime
    fallback wins.

    Robust to tz-aware and tz-naive timestamps.
    """
    if event_dt is None or pd.isna(event_dt):
        return None
    try:
        ts = pd.Timestamp(event_dt)
    except (TypeError, ValueError):
        return None
    # Convert to America/New_York if tz-aware; assume already-ET if naive
    if ts.tzinfo is not None:
        try:
            ts = ts.tz_convert(ET_NAME)
        except Exception:
            ts = ts.tz_convert('UTC').tz_convert(ET_NAME)
    # Compare wall-clock time
    hr, mn = ts.hour, ts.minute
    minutes = hr * 60 + mn
    if minutes >= 16 * 60:           # 16:00 ET or later -> AMC
        return 'post-market'
    if minutes <= 9 * 60 + 30:       # 09:30 ET or earlier -> BMO
        return 'pre-market'
    return None  # intraday — let AV fallback decide


def _yahoo_provider_observation(ticker, limit=40):
    """Actual bounded curl adapter; rejects an unsupported installed library."""
    import yfinance as yf
    from curl_cffi.requests import Session
    from importlib.metadata import version
    class BoundedSession(Session):
        attempts = 0
        def request(self, *args, **kwargs):
            if self.attempts >= 4:
                raise av.SourceError("yahoo_request_limit")
            self.attempts += 1
            av.emit_worker_event({"provider": "yahoo", "request_attempt": self.attempts})
            pieces=[]
            total=0
            def accept(piece):
                nonlocal total
                total+=len(piece)
                if total>av.MAX_SOURCE_BYTES:
                    return 0  # curl aborts the transfer before parsing/buffering.
                pieces.append(piece)
                return len(piece)
            kwargs.update(timeout=2,allow_redirects=False,content_callback=accept)
            response = super().request(*args, **kwargs)
            response.content=b"".join(pieces)
            if response.status_code >= 300 or total > av.MAX_SOURCE_BYTES:
                raise av.SourceError("yahoo_response_limit")
            return response
    if version("yfinance") != "1.7.0":
        raise av.SourceError("yahoo_adapter_version_unavailable")
    with BoundedSession(impersonate="chrome") as session:
        frame = yf.Ticker(ticker,session=session).get_earnings_dates(limit=limit)
        if frame is None:
            raise av.SourceError("yahoo_observation_unavailable")
        if len(frame)>50:
            raise av.SourceError("yahoo_row_limit")
        rows = []
        for timestamp,row in frame.iterrows():
            stamp = pd.Timestamp(timestamp)
            if stamp.tzinfo is None:
                raise av.SourceError("yahoo_timezone_unknown")
            values = row.astype(object).where(row.notna(),None).to_dict()
            rows.append({"timestamp":stamp.isoformat(),"values":values})
        payload={"rows":rows,"index_timezone":str(frame.index.tz),"columns":list(frame.columns)}
        if len(av.canonical(payload).encode())>av.MAX_SOURCE_BYTES:
            raise av.SourceError("yahoo_observation_byte_limit")
        return {"observation_id":str(uuid.uuid4()),"ticker":ticker,
                "source_retrieved_at":datetime.now(timezone.utc).isoformat(),
                "library_version":version("yfinance"),"safe_parameters":{"symbol":ticker,"limit":limit},
                "content_sha256":av.digest(payload),"payload":payload,"request_attempts":session.attempts}


def fetch_yahoo_observation(ticker, *, provider=None, on_event=None):
    return av.bounded_call(lambda:(provider or _yahoo_provider_observation)(ticker),8,
                           error="yahoo_unavailable",on_event=on_event)


def fetch_yahoo_timing_for_ticker(ticker,limit=40):
    observation=fetch_yahoo_observation(ticker)
    return {pd.Timestamp(r["timestamp"]).tz_convert(ET_NAME).date():_yahoo_timing_from_event_dt(r["timestamp"])
            for r in observation["payload"]["rows"]}


def fetch_history_for_ticker(ticker,api_key,enrich_with_yahoo=True,*,dry_run=False,on_yahoo_event=None):
    capture=av.fetch_capture("EARNINGS",{"symbol":ticker.upper()},api_key)
    uri=av.archive_capture(capture,dry_run=dry_run)
    data=capture.json()
    if data.get("symbol","").upper()!=ticker.upper() or not isinstance(data.get("quarterlyEarnings"),list):
        raise av.SourceError("earnings_schema")
    quarters=data["quarterlyEarnings"]
    if len(quarters)>1000:
        raise av.SourceError("earnings_row_limit")
    observation=None
    yahoo_error=None
    if enrich_with_yahoo:
        try:
            observation=fetch_yahoo_observation(ticker.upper(),on_event=on_yahoo_event)
        except av.SourceError as exc:
            yahoo_error=str(exc)
    timing={pd.Timestamp(r["timestamp"]).tz_convert(ET_NAME).date():_yahoo_timing_from_event_dt(r["timestamp"])
            for r in observation["payload"]["rows"]} if observation else {}
    rows=[]
    for q in quarters:
        if not isinstance(q,dict):
            raise av.SourceError("earnings_record")
        try:
            fiscal=pd.Timestamp(q["fiscalDateEnding"]).date()
            reported=pd.Timestamp(q["reportedDate"]).date() if q.get("reportedDate") else None
        except (ValueError,TypeError,KeyError):
            raise av.SourceError("earnings_date") from None
        rows.append({"ticker":ticker.upper(),"fiscal_date_ending":fiscal,"reported_date":reported,
                     "reported_eps":_safe_float(q.get("reportedEPS")),"estimated_eps":_safe_float(q.get("estimatedEPS")),
                     "surprise":_safe_float(q.get("surprise")),"surprise_pct":_safe_float(q.get("surprisePercentage")),
                     "report_time":_safe_str(q.get("reportTime")),"yahoo_report_time":timing.get(reported)})
    frame=pd.DataFrame(rows)
    frame.attrs.update(capture=capture,raw_uri=uri,yahoo_observation=observation,yahoo_error=yahoo_error,
                       yahoo_mode="observed" if observation else "unavailable" if enrich_with_yahoo else "disabled")
    return frame


def _earnings_calendar_tickers(
    lookahead_days: int,
    require_options: bool = True,
) -> list[str]:
    """Resolve tickers reporting earnings in the next N days from Cloud SQL.

    With ``require_options=True`` (default), returns tickers whose
    earnings dates are confirmed by BOTH AlphaVantage AND Unusual
    Whales (the AV ∩ UW cut). UW's curated daily list (~25-37 names)
    is the natural gate for "options-tradeable on earnings"; AV
    cross-confirms the announcement date. EW is NOT used as a gate
    because it cuts out major institutional names (SONY, TCOM, JBS,
    EC, SKM, etc.) and dozens of high-OI small-caps that don't fit
    EW's strategy templates but are still tradeable.

    Typical 7d window: 3,400 reporters → ~115 AV ∩ UW tickers.
    """
    try:
        from gcp.database import query_to_dataframe_strict as query_to_dataframe
    except ImportError:
        return []

    sql = """
        SELECT ticker
        FROM earnings_calendar
        WHERE earnings_date BETWEEN CURRENT_DATE
            AND CURRENT_DATE + (:days || ' days')::interval
        GROUP BY ticker
    """
    if require_options:
        sql += (
            '        HAVING BOOL_OR(data_source = \'alphavantage\') = true\n'
            '            AND BOOL_OR(data_source = \'unusual_whales\') = true\n'
        )
    sql += "        ORDER BY ticker\n"
    try:
        df = query_to_dataframe(sql, {"days": lookahead_days})
    except Exception as e:
        raise av.SourceError("eligibility_query_failed") from None
    if df is None or df.empty:
        return []
    return [str(t).upper() for t in df["ticker"].tolist()]


def _tickers_reporting_in_window(window_days: int) -> set:
    """Tickers in earnings_calendar with earnings_date in [today, today+window_days].

    Daily scope: window_days=0 → today only (capture post-close eps_actual).
    Weekly scope: window_days=7 → today through next 7 days (full setup).
    """
    try:
        from gcp.database import query_to_dataframe_strict as query_to_dataframe
    except ImportError:
        return set()
    try:
        # Anchor the window in America/New_York, NOT the DB session timezone.
        # Cloud SQL Postgres is set to UTC (verified `SHOW timezone` returns
        # 'UTC') and these jobs are scheduled at 7:15/7:30 PM ET. During EST
        # (UTC-5, Nov–Mar) that's 00:15/00:30 UTC the NEXT day, so a bare
        # CURRENT_DATE returns tomorrow's reporters and the helper skips the
        # tickers we just want to refresh post-close. During EDT (UTC-4) the
        # bug is dormant — 19:30 ET = 23:30 UTC, same calendar day — but
        # anchoring in ET is correct year-round and removes the seasonal
        # failure mode.
        df = query_to_dataframe(
            """
            SELECT DISTINCT ticker
            FROM earnings_calendar
            WHERE earnings_date BETWEEN (NOW() AT TIME ZONE 'America/New_York')::date
                AND (NOW() AT TIME ZONE 'America/New_York')::date + (:days || ' days')::interval
            """,
            {"days": int(window_days)},
        )
    except Exception as e:
        raise av.SourceError("eligibility_query_failed") from None
    if df is None or df.empty:
        return set()
    return {str(t).upper() for t in df["ticker"].tolist()}


def _filter_already_have_history(
    tickers: list, force_set: set = None,
) -> tuple:
    """Skip tickers that have history rows — UNLESS they're in force_set.

    force_set: tickers we always re-fetch even if rows exist. Used to
    capture a newly-reported quarter (eps_actual) for tickers reporting
    in the current run's window.

    Past quarters never change, so a ticker with rows AND not reporting
    in the window stays skipped. Returns (tickers_needing_fetch, n_skipped).
    """
    if not tickers:
        return tickers, 0
    force_set = force_set or set()
    try:
        from gcp.database import query_to_dataframe_strict as query_to_dataframe
    except ImportError:
        return tickers, 0
    try:
        df = query_to_dataframe(
            "SELECT DISTINCT ticker FROM earnings_history WHERE ticker = ANY(:t)",
            {"t": tickers},
        )
    except Exception as e:
        raise av.SourceError("eligibility_query_failed") from None
    if df is None or df.empty:
        return tickers, 0
    already = {str(t).upper() for t in df["ticker"].tolist()}
    remaining = [t for t in tickers if t not in already or t in force_set]
    n_skipped = len(tickers) - len(remaining)
    return remaining, n_skipped


def _resolve_scope(cli_scope: str = None) -> str:
    """'weekly' on Sundays or when overridden; else 'daily'."""
    if cli_scope in ('daily', 'weekly'):
        return cli_scope
    env = os.environ.get('PIPELINE_SCOPE', '').strip().lower()
    if env in ('daily', 'weekly'):
        return env
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    return 'weekly' if _dt.now(ZoneInfo(ET_NAME)).weekday() == 6 else 'daily'


def _earnings_history_tickers() -> list[str]:
    """Self-heal source: every ticker we've ever pulled history for.

    earnings_calendar is now clamped to today-1..today+7 (PR #174 OOM
    fix) which means a ticker like MSFT can drift out of the
    ``_earnings_calendar_tickers`` view if it isn't in that 8-day
    window when this job runs (e.g. weekly Sunday cadence + ticker
    reports next Wednesday). Adding the historical-ticker source keeps
    every ticker we've ever touched on the refresh list so it stays
    current as new quarters drop.
    """
    try:
        from gcp.database import query_to_dataframe_strict as query_to_dataframe
    except ImportError:
        return []

    try:
        df = query_to_dataframe("SELECT DISTINCT ticker FROM earnings_history")
    except Exception as e:
        raise av.SourceError("eligibility_query_failed") from None
    if df is None or df.empty:
        return []
    return [str(t).upper() for t in df["ticker"].tolist()]


def resolve_refresh_universe(scope,lookback_days=30,force=False):
    from gcp.database import query_to_dataframe_strict
    if not 1<=lookback_days<=90:
        raise av.SourceError("lookback_limit")
    return query_to_dataframe_strict("""
      WITH universe AS(SELECT ticker FROM earnings_history UNION SELECT ticker FROM earnings_calendar
        WHERE earnings_date BETWEEN (NOW() AT TIME ZONE 'America/New_York')::date-CAST(:days AS integer)
          AND (NOW() AT TIME ZONE 'America/New_York')::date+14 UNION SELECT ticker FROM watchlists WHERE removed_at IS NULL)
      SELECT u.ticker,(:forced OR :scope='weekly' OR NOT EXISTS(SELECT 1 FROM earnings_history e WHERE e.ticker=u.ticker)
        OR EXISTS(SELECT 1 FROM earnings_history e WHERE e.ticker=u.ticker
          AND e.reported_date>=(NOW() AT TIME ZONE 'America/New_York')::date-CAST(:days AS integer)
          AND (e.reported_eps IS NULL OR e.source_fetch_id IS NULL))) AS needs_refresh
      FROM universe u ORDER BY u.ticker
    """,{"days":lookback_days,"forced":force,"scope":scope},timeout_s=5)


def persist_history(frame,*,executor=None):
    executor=executor or av.isolated_sql
    capture=frame.attrs["capture"]
    uri=frame.attrs["raw_uri"]
    observation=frame.attrs.get("yahoo_observation")
    if observation:
        # Separate provider observation, acknowledged before linking to AV EPS.
        known=datetime.now(timezone.utc)
        executor("""INSERT INTO earnings_timing_observations
          SELECT * FROM jsonb_populate_record(NULL::earnings_timing_observations,CAST(:row AS jsonb))
          ON CONFLICT(observation_id) DO NOTHING""",
          {"row":av.canonical({k:v for k,v in observation.items() if k!='request_attempts'} | {"known_at":known.isoformat()})},timeout_s=2)
    records=frame.astype(object).where(frame.notna(),None).to_dict("records")
    for r in records:
        r.update(source_fetch_id=capture.observation_id,source_retrieved_at=capture.retrieved_at.isoformat(),
                 raw_uri=uri,raw_sha256=capture.body_sha256,
                 yahoo_timing_observation_id=observation["observation_id"] if observation and any(
                   pd.Timestamp(t["timestamp"]).tz_convert(ET_NAME).date()==r["reported_date"]
                   for t in observation["payload"]["rows"]) else None)
    receipt=av.capture_record(capture,uri,len(records))
    # One network statement captures source + cache; AFTER trigger journals
    # versions in the same transaction. Existing Yahoo evidence is preserved
    # when this invocation has no completed independent provider observation.
    executor("""WITH captured AS(
      INSERT INTO av_catalyst_source_captures
      SELECT * FROM jsonb_populate_record(NULL::av_catalyst_source_captures,CAST(:receipt AS jsonb))
      ON CONFLICT(capture_id) DO NOTHING RETURNING capture_id
    ) INSERT INTO earnings_history(ticker,fiscal_date_ending,reported_date,reported_eps,
      estimated_eps,surprise,surprise_pct,report_time,yahoo_report_time,source_fetch_id,
      source_retrieved_at,raw_uri,raw_sha256,yahoo_timing_observation_id)
      SELECT ticker,fiscal_date_ending,reported_date,reported_eps,estimated_eps,surprise,surprise_pct,
        report_time,yahoo_report_time,source_fetch_id,source_retrieved_at,raw_uri,raw_sha256,yahoo_timing_observation_id
      FROM jsonb_populate_recordset(NULL::earnings_history,CAST(:rows AS jsonb))
      ON CONFLICT(ticker,fiscal_date_ending) DO UPDATE SET
        reported_date=excluded.reported_date,reported_eps=excluded.reported_eps,
        estimated_eps=excluded.estimated_eps,surprise=excluded.surprise,surprise_pct=excluded.surprise_pct,
        report_time=excluded.report_time,source_fetch_id=excluded.source_fetch_id,
        source_retrieved_at=excluded.source_retrieved_at,raw_uri=excluded.raw_uri,raw_sha256=excluded.raw_sha256,
        yahoo_report_time=CASE WHEN excluded.yahoo_timing_observation_id IS NOT NULL
          THEN excluded.yahoo_report_time ELSE earnings_history.yahoo_report_time END,
        yahoo_timing_observation_id=COALESCE(excluded.yahoo_timing_observation_id,earnings_history.yahoo_timing_observation_id)
    """,{"receipt":av.canonical(receipt),"rows":av.canonical(records)},timeout_s=2)
    return len(records)


def assess_history_manifest(run,universe,*,executor=None):
    executor=executor or av.isolated_sql
    facts=executor("""SELECT e.ticker,e.reported_date,r.revision_id,r.known_at,r.payload->>'reported_eps' AS reported_eps,
      av_earnings_values(to_jsonb(e))=r.payload AS coherent_cache,CASE WHEN proof.capture_id IS NOT NULL THEN 'source_verified' ELSE r.availability_quality END AS availability_quality,
      COALESCE(proof.yahoo_timing_observation_id,r.yahoo_timing_observation_id) AS yahoo_timing_observation_id FROM earnings_history e
      LEFT JOIN LATERAL(SELECT * FROM earnings_history_revisions v WHERE v.ticker=e.ticker
        AND v.fiscal_date_ending=e.fiscal_date_ending AND v.known_at<=:cutoff
        ORDER BY v.known_at DESC,v.revision_id DESC LIMIT 1) r ON true
      LEFT JOIN LATERAL(SELECT o.* FROM earnings_revision_observations o
        JOIN av_catalyst_source_captures c ON c.capture_id=o.capture_id AND c.validation_status='validated'
        WHERE o.revision_id=r.revision_id AND o.known_at<=:cutoff AND c.source_retrieved_at<=:cutoff
        ORDER BY o.known_at DESC,o.capture_id DESC LIMIT 1) proof ON true
      WHERE e.ticker=ANY(CAST(:universe AS text[])) AND e.reported_date BETWEEN
        (:cutoff AT TIME ZONE 'America/New_York')::date-30 AND (:cutoff AT TIME ZONE 'America/New_York')::date
      ORDER BY e.ticker,e.reported_date""",{"universe":universe,"cutoff":datetime.now(timezone.utc)},read=True,timeout_s=8)
    verified=[r for r in facts if r["availability_quality"]=='source_verified' and r["reported_eps"] is not None and r["coherent_cache"]]
    events=[{"ticker":r["ticker"],"event_reported_date":str(r["reported_date"])} for r in facts]
    manifest={"schema_version":"av_catalyst_run/v1","pipeline_scope":run.mode,"scope_hash":av.digest(events),
      "universe_count":len(universe),"configured_universe":universe,"expected_events":events,
      "source_window_start":(run.started_at.date()-pd.Timedelta(days=30)).isoformat(),
      "source_window_end":run.started_at.date().isoformat(),"complete_through":run.started_at.isoformat() if len(verified)==len(facts) and not run.failed else None,
      "coverage_complete":len(verified)==len(facts) and not run.failed,
      "requested_count":len(events),"verified_count":len(verified),"excluded_count":0,
      "pending_count":len(facts)-len(verified),"source_revision_ids":[r["revision_id"] for r in verified],
      "verified_events":[{"ticker":r["ticker"],"event_reported_date":str(r["reported_date"]),"revision_id":r["revision_id"]} for r in verified],
      "source_digest":av.digest(facts),"predecessor_execution_name":None,**av.code_identity()}
    return av.publish_manifest(run,manifest)


def main(argv=None):
    parser=argparse.ArgumentParser(description="Bounded AV earnings refresh")
    parser.add_argument("--tickers")
    parser.add_argument("--scope",choices=['daily','weekly'])
    parser.add_argument("--lookback-days",type=int,default=30)
    parser.add_argument("--lookahead-days",type=int,default=14)
    parser.add_argument("--max-tickers",type=int,default=100)
    parser.add_argument("--require-options",action='store_true')
    parser.add_argument("--force",action='store_true')
    parser.add_argument("--no-backfill",action='store_true')
    parser.add_argument("--no-yahoo",action='store_true')
    parser.add_argument("--dry-run",action='store_true')
    args=parser.parse_args(argv)
    scope=_resolve_scope(args.scope)
    run=av.Run("fetch-earnings-history",scope)
    start=time_module.monotonic()
    outcomes=[]; manifest=None
    try:
        if not args.no_backfill:
            raise av.SourceError("combined_manual_chain_not_admitted_use_no_backfill")
        if not 1<=args.max_tickers<=100:
            raise av.SourceError("earnings_admission_limit")
        api_key=os.environ.get('AV_API_KEY') or os.environ.get('ALPHA_VANTAGE_API_KEY')
        if not api_key:
            raise av.SourceError("credential_missing")
        if args.tickers:
            universe=sorted({t.strip().upper() for t in args.tickers.split(',') if t.strip()})
            eligible=universe
        else:
            resolved=resolve_refresh_universe(scope,args.lookback_days,args.force)
            universe=resolved['ticker'].str.upper().tolist() if not resolved.empty else []
            eligible=resolved.loc[resolved['needs_refresh'],'ticker'].str.upper().tolist() if not resolved.empty else []
        run.expected=len(eligible)
        selected=av.claim_work("EARNINGS",eligible,scope,run.execution_name,limit=args.max_tickers,
                               force=args.force,dry_run=args.dry_run)
        run.pending=len(eligible)-len(selected)
        for ticker in selected:
            if run.attempted:
                time_module.sleep(.4)
            if time_module.monotonic()-start>=5920:
                run.pending+=len(selected)-run.attempted
                break
            run.attempted+=1;run.request_attempts+=1
            try:
                frame=fetch_history_for_ticker(ticker,api_key,enrich_with_yahoo=not args.no_yahoo,dry_run=args.dry_run,
                    on_yahoo_event=lambda event:run.metrics.update(yahoo_http_attempts=run.metrics.get('yahoo_http_attempts',0)+1))
                written=len(frame) if args.dry_run else persist_history(frame)
                run.rows_written+=written;run.processed+=1
                outcomes.append({"ticker":ticker,"success":True,"observed_at":frame.attrs['capture'].retrieved_at.isoformat()})
                if frame.attrs.get('yahoo_error'):
                    run.failed+=1
                run.groups.append({"ticker":ticker,"requested_source_window":None,
                  "source_event_max":str(frame['reported_date'].max()) if not frame.empty else None,
                  "complete_through":frame.attrs['capture'].retrieved_at.isoformat(),"coverage_complete":True,
                  "cursor_before":None,"cursor_after":frame.attrs['capture'].retrieved_at.isoformat(),
                  "yahoo_mode":frame.attrs['yahoo_mode'],"yahoo_error_class":frame.attrs.get('yahoo_error')})
            except Exception as exc:
                run.failed+=1
                outcomes.append({"ticker":ticker,"success":False,"observed_at":None})
                run.groups.append({"ticker":ticker,"error_class":str(exc) if isinstance(exc,av.SourceError) else type(exc).__name__,"coverage_complete":False})
            if len(outcomes)>=10 and not args.dry_run:
                av.finish_work("EARNINGS",scope,outcomes);outcomes=[]
        if not args.dry_run:
            av.finish_work("EARNINGS",scope,outcomes)
            manifest=assess_history_manifest(run,universe)
    except Exception as exc:
        run.failed+=1
        run.groups.append({"error_class":str(exc) if isinstance(exc,av.SourceError) else type(exc).__name__,"coverage_complete":False})
    return run.terminal(dry_run=args.dry_run,extra=manifest)


if __name__=="__main__":
    raise SystemExit(main())
