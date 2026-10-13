#!/usr/bin/env python3
"""
Cloud Run Job: Fetch insider transactions from AV INSIDER_TRANSACTIONS → Cloud SQL.

Form 4 filings: every officer/director/10%-owner buy or sell. AV
returns up to 1000 rows per ticker per call going back several years.

Used by the ranker to derive an "insider cluster" signal — 3+ insiders
buying within 30 days, or a single insider transacting >$1M, are
historically strong directional tells on single names.

Ticker source priority:
  1. CLI --tickers override
  2. earnings_calendar within ±N days (default 7) — the catalyst
     window where insider activity matters most.

Usage:
    python -m gcp.fetchers.fetch_insider_transactions
    python -m gcp.fetchers.fetch_insider_transactions --tickers AAPL,AVGO --dry-run
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

from gcp.database import upsert_dataframe, is_cloud_sql_configured
from gcp.fetchers import _av_ingestion as av
import math
from lib.config import AlphaVantageConfig
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

AV_BASE_URL = "https://www.alphavantage.co/query"
_av_cfg = AlphaVantageConfig()


def _safe_float(val) -> float | None:
    if val is None or val == "" or val == "None":
        return None
    try:
        f=float(val)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def fetch_for_ticker(ticker,api_key,*,dry_run=False):
    capture=av.fetch_capture('INSIDER_TRANSACTIONS',{'symbol':ticker.upper()},api_key)
    uri=av.archive_capture(capture,dry_run=dry_run)
    data=capture.json()
    if not isinstance(data.get('data'),list) or any(not isinstance(t,dict) for t in data['data']):
        raise av.SourceError('insider_schema')
    txns=data['data']
    if len(txns)>1000:
        raise av.SourceError('insider_row_limit')
    rows = []
    today = pd.Timestamp.utcnow().date()
    skipped_future = 0
    for t in txns:
        td = t.get("transaction_date")
        if not td:
            raise av.SourceError("insider_required_date")
        try:
            txn_date = pd.to_datetime(td).date()
        except Exception:
            raise av.SourceError("insider_date") from None
        # AV occasionally returns garbage future dates (e.g. 2031-01-29).
        # Insider transactions are by definition reported after they happen,
        # so anything more than a week in the future is almost certainly a
        # source data error.
        if (txn_date - today).days > 7:
            skipped_future += 1
            continue
        shares = _safe_float(t.get("shares"))
        price = _safe_float(t.get("share_price"))
        value = (shares * price) if (shares is not None and price is not None) else None
        rows.append(
            {
                "ticker": ticker.upper(),
                "transaction_date": txn_date,
                "executive": (t.get("executive") or "")[:200] or None,
                "title": (t.get("executive_title") or "")[:200] or None,
                "transaction_type": (t.get("acquisition_or_disposal") or "")[:20] or None,
                "shares": shares,
                "share_price": price,
                "transaction_value": value,
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        log.info("    %s: %d transactions", ticker, len(df))
    if skipped_future:
        log.warning("    %s: skipped %d rows with implausible future dates",
                    ticker, skipped_future)
    df.attrs.update(capture=capture,raw_uri=uri,skipped_future=skipped_future,source_count=len(txns))
    return df


def _earnings_calendar_tickers(window_days: int) -> list[str]:
    try:
        from gcp.database import query_to_dataframe_strict as query_to_dataframe
    except ImportError:
        return []
    sql = """
        SELECT DISTINCT ticker
        FROM earnings_calendar
        WHERE earnings_date BETWEEN
            CURRENT_DATE - (:w || ' days')::interval AND
            CURRENT_DATE + (:w || ' days')::interval
        ORDER BY ticker
    """
    try:
        df = query_to_dataframe(sql, {"w": window_days})
    except Exception as e:
        raise av.SourceError("eligibility_query_failed") from None
    if df is None or df.empty:
        return []
    return [str(t).upper() for t in df["ticker"].tolist()]


def run_insider(run,tickers,key,*,dry_run=False,fetcher=None,writer=None,final=False):
    fetcher=fetcher or fetch_for_ticker
    writer=writer or av.write_identity_group
    start=time_module.monotonic()
    rows=[];captures=[];outcomes=[]
    def flush():
        nonlocal rows,captures,outcomes
        if not outcomes:
            return
        if not dry_run:
            try:
                writer('insider_transactions',rows,captures=captures,final=final,outcomes=outcomes)
            except Exception:
                affected={o['ticker'] for o in outcomes}
                for note in run.groups:
                    if note.get('ticker') in affected:
                        note.update(coverage_complete=False,complete_through=None,cursor_after=None,
                                    commit_outcome='unknown_or_failed')
                raise
            run.rows_written+=len(rows)
        run.processed+=sum(o['success'] for o in outcomes)
        rows=[];captures=[];outcomes=[]
    for ticker in tickers:
        if time_module.monotonic()-start>=820:
            run.pending+=len(tickers)-run.attempted
            break
        if run.request_attempts:
            time_module.sleep(.4)
        run.attempted+=1;run.request_attempts+=1
        try:
            frame=fetcher(ticker,key,dry_run=dry_run)
            if len(frame)>1000 or len(av.canonical(frame.astype(object).where(frame.notna(),None).to_dict('records')).encode())>1_200_000:
                raise av.SourceError('insider_expansion_limit')
            capture=frame.attrs['capture']
            if not frame.empty:
                prepared=av.prepare_identity_frame(frame,'insider_transactions').to_dict('records')
                for row in prepared:
                    row['source_capture_id']=capture.observation_id
                rows.extend(prepared)
            if not dry_run:
                captures.append(av.capture_record(capture,frame.attrs['raw_uri'],len(frame),source_count=frame.attrs['source_count']))
            outcomes.append({'function':'INSIDER_TRANSACTIONS','ticker':ticker,'scope':'daily','lease_owner':run.execution_name,'success':True,'observed_at':capture.retrieved_at.isoformat()})
            run.groups.append({'ticker':ticker,'source_event_max':str(frame['transaction_date'].max()) if not frame.empty else None,
              'source_capture_id':capture.observation_id,'raw_uri':frame.attrs['raw_uri'],'raw_sha256':capture.body_sha256,
              'source_retrieved_at':av.clock_string(capture.retrieved_at),
              'requested_source_window':None,'complete_through':av.clock_string(capture.retrieved_at),'coverage_complete':True,
              'cursor_before':None,'cursor_after':av.clock_string(capture.retrieved_at),'excluded_future':frame.attrs.get('skipped_future',0)})
        except Exception as exc:
            run.failed+=1
            outcomes.append({'function':'INSIDER_TRANSACTIONS','ticker':ticker,'scope':'daily','lease_owner':run.execution_name,'success':False,'observed_at':None})
            run.groups.append({'ticker':ticker,'coverage_complete':False,'error_class':str(exc) if isinstance(exc,av.SourceError) else type(exc).__name__})
        if len(outcomes)==10:
            flush()
    flush()
    return run


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tickers')
    parser.add_argument('--earnings-window-days',type=int,default=7)
    parser.add_argument('--max-tickers',type=int,default=300)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv)
    run=av.Run('fetch-insider-transactions','daily')
    try:
        key=os.environ.get('AV_API_KEY') or os.environ.get('ALPHA_VANTAGE_API_KEY')
        if not key:
            raise av.SourceError('credential_missing')
        if not 1<=args.max_tickers<=300:
            raise av.SourceError('insider_admission_limit')
        if args.tickers:
            universe=sorted({t.strip().upper() for t in args.tickers.split(',') if t.strip()})
        else:
            frame=av.read_dataframe("""SELECT DISTINCT ticker FROM (
              SELECT ticker FROM watchlists WHERE removed_at IS NULL UNION SELECT ticker FROM earnings_calendar
              WHERE earnings_date BETWEEN (NOW() AT TIME ZONE 'America/New_York')::date-CAST(:days AS integer)
                AND (NOW() AT TIME ZONE 'America/New_York')::date+CAST(:days AS integer)) scoped ORDER BY ticker""",
              {'days':args.earnings_window_days},timeout_s=5)
            universe=frame['ticker'].str.upper().tolist() if not frame.empty else []
        run.expected=len(universe)
        if len(universe)>args.max_tickers:
            raise av.SourceError('insider_universe_requires_explicit_shards')
        selected=av.claim_work('INSIDER_TRANSACTIONS',universe,'daily',run.execution_name,limit=args.max_tickers,dry_run=args.dry_run)
        run.pending=len(universe)-len(selected)
        run_insider(run,selected,key,dry_run=args.dry_run,final=False if args.dry_run else av.identity_state('insider_transactions'))
    except Exception as exc:
        run.failed+=1
        run.groups.append({'coverage_complete':False,'error_class':str(exc) if isinstance(exc,av.SourceError) else type(exc).__name__})
    try:
        return run.terminal(dry_run=args.dry_run)
    finally:
        av.close_sql_worker()


if __name__=='__main__':
    raise SystemExit(main())
