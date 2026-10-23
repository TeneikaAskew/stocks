#!/usr/bin/env python3
"""
Fetch news sentiment data from AlphaVantage NEWS_SENTIMENT endpoint.

Two query modes (can be combined in one invocation):

* **ticker mode** (`--tickers SPY,IWM,QQQ`) — pulls articles tagged with
  the given tickers. Use for the always-on watchlist.

* **topic mode** (`--topics mergers_and_acquisitions,technology,...`) —
  pulls articles by AV catalyst topic regardless of ticker. Use to
  capture single-name catalysts (e.g. an AVGO/Google deal) for tickers
  outside the watchlist.

For each article returned by AV, we persist **one row per ticker** in
the article's `ticker_sentiment` array (not just the queried ticker),
plus the article's `topics` and `overall_sentiment_*`. That way an
article about SPY that also mentions AAPL/AVGO/GOOGL produces a row
for each, surfacing the catalyst signal for every name involved.

Usage:
    python -m gcp.fetchers.fetch_news_sentiment --tickers SPY,IWM,QQQ
    python -m gcp.fetchers.fetch_news_sentiment --topics mergers_and_acquisitions,technology
    python -m gcp.fetchers.fetch_news_sentiment --tickers SPY --topics earnings --dry-run

Backfill:
    Pass `--time-from` / `--time-to` (AV format: YYYYMMDDTHHMM, e.g.
    `20260406T0000`) to pull historical news. The 1000-row default
    `--limit` matches AV's documented ceiling — keep it at 1000 for
    backfills covering multi-day windows or you'll silently under-
    sample high-volume catalysts (the 4/6–4/11 AVGO backfill ran
    with limit=200 originally and missed 134 of 151 articles AV had).
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import (
    upsert_dataframe, is_cloud_sql_configured, query_to_dataframe_strict as query_to_dataframe,
)
from lib.logging_config import setup_logging

logger = logging.getLogger(__name__)

DEFAULT_TICKERS = "SPY,IWM,QQQ"
# Five catalyst-rich topics — AV's hard cap per call. Names match
# https://www.alphavantage.co/documentation/#news-sentiment
DEFAULT_TOPICS = (
    "mergers_and_acquisitions,technology,financial_markets,earnings,life_sciences"
)
AV_BASE_URL = "https://www.alphavantage.co/query"

# Incremental-fetch tunables. The 30-min overlap catches edge articles
# whose timestamps got revised after first ingest (the upsert dedupes
# the overlap, so re-pulling is free). 48h cold-start window matches
# the brief's news lookback. 7d is the stale-ticker cap so a thinly-
# covered ticker doesn't trigger an unbounded historical pull.
SAFETY_OVERLAP_MINUTES = 30
COLD_START_LOOKBACK_HOURS = 48
MAX_INCREMENTAL_HOURS = 24 * 7


class CapturedFeed(list):
    def __init__(self,feed,capture,raw_uri):
        super().__init__(feed)
        self.capture=capture
        self.raw_uri=raw_uri


def _fetch(params,dry_run=False):
    from gcp.fetchers import _av_ingestion as av
    safe={k:v for k,v in params.items() if k not in {'function','apikey'}}
    capture=av.fetch_capture("NEWS_SENTIMENT",safe,params['apikey'],max_bytes=20*1024*1024)
    uri=av.archive_capture(capture,dry_run=dry_run)
    if len(capture.body)>2_000_000:
        raise av.SourceError("news_admitted_body_limit")
    data=capture.json()
    if not isinstance(data.get('feed'),list) or any(not isinstance(a,dict) for a in data['feed']):
        raise av.SourceError("news_schema")
    if len(data['feed'])>int(params.get('limit',1000)):
        raise av.SourceError('news_article_limit')
    return CapturedFeed(data['feed'],capture,uri)


def _article_to_rows(article: dict) -> list[dict]:
    """Explode one article into one row per ticker mentioned.

    AV returns each article with a `ticker_sentiment` array listing every
    ticker the article touches plus per-ticker relevance/sentiment. We
    persist one row per (article, ticker) so a single AVGO/GOOGL article
    feeds the catalyst signal for both names.
    """
    pub_ts = _parse_av_timestamp(article.get("time_published", ""))
    if pub_ts is None:
        return []

    title = (article.get("title") or "")[:500] or None
    url = (article.get("url") or "")[:1000] or None
    summary = (article.get("summary") or "")[:2000] or None
    source = (article.get("source") or "")[:100] or None

    overall_score = _safe_float(article.get("overall_sentiment_score"))
    overall_label = (article.get("overall_sentiment_label") or "")[:20] or None

    # AV topics are objects: [{"topic": "Technology", "relevance_score": "0.5"}, ...]
    topics = [
        t["topic"]
        for t in (article.get("topics") or [])
        if isinstance(t, dict) and t.get("topic")
    ]

    ticker_entries = article.get("ticker_sentiment") or []
    if not ticker_entries:
        return []

    rows = []
    for ts in ticker_entries:
        if len(rows)>=4000:
            from gcp.fetchers import _av_ingestion as av
            raise av.SourceError('news_expansion_limit')
        tk = (ts.get("ticker") or "").upper().strip()
        if not tk:
            continue
        # AV emits non-equity identifiers like CRYPTO:BTC / FOREX:USD in
        # ticker_sentiment. Drop them — downstream consumers only join on
        # equity tickers, and the colon-prefixed forms blow the
        # VARCHAR(10) ticker column (e.g. CRYPTO:DOGE = 11 chars).
        if ":" in tk or len(tk) > 10:
            continue
        rows.append(
            {
                "ticker": tk,
                "published_ts": pub_ts,
                "title": title,
                "url": url,
                "summary": summary,
                "sentiment_score": _safe_float(ts.get("ticker_sentiment_score")),
                "relevance_score": _safe_float(ts.get("relevance_score")),
                "overall_sentiment_score": overall_score,
                "overall_sentiment_label": overall_label,
                "topics": topics or None,
                "source": source,
            }
        )
    return rows


def _earnings_calendar_tickers(window_days: int) -> list[str]:
    """Tickers reporting earnings within ±``window_days`` of today.

    Mirrors ``fetch_insider_transactions._earnings_calendar_tickers`` so
    every catalyst-aware fetcher uses the same upcoming-reporter universe.
    Returns ``[]`` on DB error so the caller can fall back to the
    watchlist + DEFAULT_TICKERS chain rather than crashing.
    """
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
    except Exception:
        from gcp.fetchers._av_ingestion import SourceError
        raise SourceError("eligibility_query_failed") from None
    if df is None or df.empty:
        return []
    return [str(t).upper() for t in df["ticker"].tolist()]


def _last_published_ts(ticker: str) -> Optional[datetime]:
    """Most recent ``published_ts`` we have for this ticker, or ``None``
    on cold start / DB read failure.

    Used by the incremental fetch path so each scheduled run only asks
    AV for articles newer than what we already have. The DB query is
    a cheap MAX over the indexed (ticker, published_ts) tuple.

    Returns ``None`` (the cold-start signal) on any error so the caller
    falls back to the lookback-window default rather than crashing the
    fetch.
    """
    sql = "SELECT MAX(published_ts) AS max_ts FROM news_sentiment WHERE ticker = :tk"
    try:
        df = query_to_dataframe(sql, {"tk": ticker.upper()})
    except Exception:
        from gcp.fetchers._av_ingestion import SourceError
        raise SourceError("cursor_query_failed") from None
    if df.empty or df.iloc[0, 0] is None:
        return None
    val = df.iloc[0, 0]
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    try:
        return pd.to_datetime(val, utc=True).to_pydatetime()
    except Exception:
        from gcp.fetchers._av_ingestion import SourceError
        raise SourceError("cursor_query_failed") from None


_UNKNOWN_CURSOR=object()

def _resolve_incremental_time_from(
    ticker: str,
    now: datetime,
    *,
    last_ts: Optional[datetime] = _UNKNOWN_CURSOR,
) -> str:
    """Compute the AV ``time_from`` string for an incremental fetch.

    Three branches:

    1. **Cold start** — no rows for this ticker. Pull the last
       ``COLD_START_LOOKBACK_HOURS`` (48h, matches the brief's news
       window) instead of unlimited history. Prevents a new ticker
       addition from silently triggering a years-deep AV pull.

    2. **Stale ticker** — last article > ``MAX_INCREMENTAL_HOURS``
       (7d) ago. Cap at 7d so thinly-covered ETF/sector tickers
       don't ask AV for unbounded history every run.

    3. **Normal** — subtract ``SAFETY_OVERLAP_MINUTES`` from the
       last published_ts. The 30-min overlap catches edge articles
       whose timestamps got revised after first ingest; the upsert
       dedupes the overlap so re-pulling is free.

    Pass ``last_ts`` explicitly when a caller (or test) already has it
    cached, to skip the per-ticker DB read.
    """
    if last_ts is _UNKNOWN_CURSOR:
        last_ts = _last_published_ts(ticker)

    if last_ts is None:
        floor = now - timedelta(hours=COLD_START_LOOKBACK_HOURS)
        reason = "cold-start"
    elif (now - last_ts) > timedelta(hours=MAX_INCREMENTAL_HOURS):
        floor = now - timedelta(hours=MAX_INCREMENTAL_HOURS)
        reason = "stale-cap"
    else:
        floor = last_ts - timedelta(minutes=SAFETY_OVERLAP_MINUTES)
        reason = "incremental"

    av_str = floor.astimezone(timezone.utc).strftime("%Y%m%dT%H%M")
    logger.info("ticker %s incremental floor=%s (%s)", ticker, av_str, reason)
    return av_str


def fetch_by_tickers(
    tickers: list[str], api_key: str, limit: int,
    time_from: str | None = None, time_to: str | None = None,
    incremental: bool = False,
) -> pd.DataFrame:
    """Ticker-mode pull — one AV call per ticker, exploded across all
    tickers each article mentions.

    ``time_from`` / ``time_to`` accept AV's ``YYYYMMDDTHHMM`` format
    and let callers backfill historical news rather than only the
    most recent 50 articles.

    ``incremental=True`` resolves a per-ticker ``time_from`` from the
    last persisted ``published_ts`` (with a 30-min safety overlap)
    when the caller didn't pin a window. Cold-start tickers get a
    48h lookback; stale tickers cap at 7d. This makes the scheduled
    crons cheap enough to bump the cadence to hourly without burning
    AV quota on duplicate-pull bandwidth.
    """
    rows: list[dict] = []
    # Snap "now" once per batch so all tickers see the same clock.
    batch_now = datetime.now(timezone.utc) if incremental else None

    for tk in tickers:
        # Per-ticker time_from: explicit caller wins; otherwise resolve
        # incrementally if requested; otherwise leave unset (= "AV's latest").
        tk_time_from = time_from
        if incremental and not time_from and not time_to:
            tk_time_from = _resolve_incremental_time_from(tk, batch_now)

        params: dict[str, str | int] = {
            "function": "NEWS_SENTIMENT",
            "tickers": tk,
            "limit": limit,
            "apikey": api_key,
        }
        if tk_time_from:
            params["time_from"] = tk_time_from
        if time_to:
            params["time_to"] = time_to
        if tk_time_from or time_to:
            params["sort"] = "EARLIEST"
        feed = _fetch(params)
        if not feed:
            logger.info("no articles for ticker %s", tk)
            continue
        article_rows: list[dict] = []
        for article in feed:
            article_rows.extend(_article_to_rows(article))
        logger.info(
            "ticker %s: %d articles → %d (article, ticker) rows",
            tk,
            len(feed),
            len(article_rows),
        )
        rows.extend(article_rows)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def fetch_by_topics(topics: list[str], api_key: str, limit: int) -> pd.DataFrame:
    """Topic-mode pull — one AV call covering up to 5 topics, exploded
    across all tickers each article mentions."""
    if len(topics) > 5:
        logger.warning(
            "AV NEWS_SENTIMENT accepts max 5 topics; truncating %d → 5",
            len(topics),
        )
        topics = topics[:5]
    feed = _fetch(
        {
            "function": "NEWS_SENTIMENT",
            "topics": ",".join(topics),
            "limit": limit,
            "apikey": api_key,
        }
    )
    if not feed:
        logger.info("no articles for topics %s", topics)
        return pd.DataFrame()
    rows: list[dict] = []
    for article in feed:
        rows.extend(_article_to_rows(article))
    logger.info(
        "topics %s: %d articles → %d (article, ticker) rows",
        topics,
        len(feed),
        len(rows),
    )
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_av_timestamp(ts_str: str) -> datetime | None:
    """Parse AlphaVantage timestamp format '20250416T120000' to datetime."""
    if not ts_str:
        return None
    try:
        return datetime.strptime(ts_str, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
        except ValueError:
            logger.debug("unparseable timestamp: %s", ts_str)
            return None


def prepare_news_rows(frame):
    from gcp.fetchers._av_ingestion import prepare_identity_frame
    return prepare_identity_frame(frame,"news_sentiment")


def persist_to_cloud_sql(df):
    if df.empty:
        return 0
    from gcp.fetchers import _av_ingestion as av
    prepared=prepare_news_rows(df)
    return av.write_identity_group("news_sentiment",prepared.to_dict("records"),final=av.identity_state("news_sentiment"))


def build_parser():
    parser=argparse.ArgumentParser(description="Durable bounded AV news windows")
    parser.add_argument('--tickers',default=os.environ.get('NEWS_TICKERS',''))
    parser.add_argument('--topics',default=os.environ.get('NEWS_TOPICS',''))
    parser.add_argument('--limit',type=int,default=1000)
    parser.add_argument('--time-from')
    parser.add_argument('--time-to')
    parser.add_argument('--since-last',action='store_true')
    parser.add_argument('--earnings-window-days',type=int,default=int(os.environ.get('EARNINGS_WINDOW_DAYS','0')))
    parser.add_argument('--max-tickers',type=int,default=300)
    parser.add_argument('--max-requests',type=int,default=300)
    parser.add_argument('--dry-run',action='store_true')
    return parser


def news_window_scopes(tickers,topics,start,end):
    from gcp.fetchers import _av_ingestion as av
    scopes=[]
    for params in [{'tickers':t} for t in tickers]+([{'topics':','.join(sorted(topics))}] if topics else []):
        identity=av.digest(params)
        scopes.append({'query_identity':identity,'parameters':params,'window_start':start.isoformat(),'window_end':end.isoformat()})
    return scopes


def _write_news_group(rows,captures,outcomes,final,executor=None):
    from gcp.fetchers import _av_ingestion as av
    executor=executor or av.isolated_sql
    pieces=[]
    params={'rows':av.canonical(rows),'captures':av.canonical(captures),'outcomes':av.canonical(outcomes)}
    if captures:
        pieces.append('captured AS('+av.capture_sql(captures)+' RETURNING capture_id)')
    if rows:
        sql=av.identity_write_sql('news_sentiment',final)
        if sql.startswith('WITH '):
            pos=sql.index('\n      INSERT INTO ')
            pieces.append(sql[5:pos]);sql=sql[pos:]
        pieces.append('written AS('+sql+')')
    # Explicit dependency ensures source/row CTEs run before coverage advances.
    dependencies=' CROSS JOIN '.join('(SELECT count(*) FROM '+name+') '+name+'count' for name in ['captured','written'] if any(p.startswith(name+' AS') for p in pieces))
    terminal='SELECT av_complete_news_windows(CAST(:outcomes AS jsonb))'
    if dependencies:
        terminal+=' FROM '+dependencies
    sql=('WITH '+','.join(pieces)+' '+terminal) if pieces else terminal
    return executor(sql,params,timeout_s=8)


def run_news_windows(run,scopes,key,*,limit=1000,max_requests=300,dry_run=False,executor=None,fetcher=None,final=False):
    from gcp.fetchers import _av_ingestion as av
    executor=executor or av.isolated_sql
    fetcher=fetcher or _fetch
    begun=__import__('time').monotonic()
    limits={s['query_identity']:30 for s in scopes}
    if dry_run:
        windows=[dict(s,window_id=None,lease_owner=run.execution_name) for s in scopes]
    else:
        executor('SELECT av_seed_news_windows(CAST(:scopes AS jsonb))',{'scopes':av.canonical(scopes)},timeout_s=8)
    budget_exhausted=False
    while run.request_attempts<max_requests and __import__('time').monotonic()-begun<820:
        if not dry_run:
            windows=executor('SELECT * FROM av_claim_news_windows(CAST(:limits AS jsonb),:owner,:cap)',
                             {'limits':av.canonical(limits),'owner':run.execution_name,'cap':min(10,max_requests-run.request_attempts)},read=True,timeout_s=8)
        if not windows:
            break
        rows=[];captures=[];outcomes=[]
        group_start=len(run.groups)
        successes=0
        for window in windows[:10]:
            if __import__('time').monotonic()-begun>=820:
                budget_exhausted=True
                break
            if run.request_attempts>=max_requests:
                break
            qid=window['query_identity']
            if limits[qid]<=0:
                continue
            if run.request_attempts:
                __import__('time').sleep(.4)
            limits[qid]-=1;run.request_attempts+=1;run.attempted+=1
            start=pd.Timestamp(window['window_start']).to_pydatetime();end=pd.Timestamp(window['window_end']).to_pydatetime()
            params={'function':'NEWS_SENTIMENT',**window['parameters'],'limit':limit,'apikey':key,'sort':'EARLIEST',
                    'time_from':(start-timedelta(minutes=1)).strftime('%Y%m%dT%H%M'),'time_to':end.strftime('%Y%m%dT%H%M')}
            try:
                feed=fetcher(params,dry_run=dry_run)
                source_rows=[]
                if len(feed)>limit:
                    raise av.SourceError('news_article_limit')
                for article in feed:
                    published=_parse_av_timestamp(article.get('time_published',''))
                    if published is None:
                        raise av.SourceError('news_required_timestamp')
                    if start<=published<end:
                        source_rows.extend(_article_to_rows(article))
                        if len(source_rows)>4000:
                            raise av.SourceError('news_expansion_limit')
                if len(source_rows)>4000 or len(av.canonical(source_rows).encode())>4_800_000:
                    raise av.SourceError('news_expansion_limit')
                saturated=len(feed)>=limit
                if source_rows:
                    prepared=prepare_news_rows(pd.DataFrame(source_rows)).to_dict('records')
                    for row in prepared:
                        row['source_capture_id']=feed.capture.observation_id
                    rows.extend(prepared)
                if not dry_run:
                    captures.append(av.capture_record(feed.capture,feed.raw_uri,len(source_rows),source_count=len(feed)))
                    outcomes.append({'window_id':str(window['window_id']),'lease_owner':run.execution_name,
                                     'capture_id':feed.capture.observation_id,'status':'validated','saturated':saturated})
                run.groups.append({'query_identity':qid,'requested_source_window':[av.clock_string(start),av.clock_string(end)],
                  'source_capture_id':feed.capture.observation_id,'raw_uri':feed.raw_uri,'raw_sha256':feed.capture.body_sha256,
                  'source_retrieved_at':av.clock_string(feed.capture.retrieved_at),
                  'source_event_max':max((av.clock_string(r['published_ts']) for r in source_rows),default=None),
                  'complete_through':None if saturated else av.clock_string(end),'coverage_complete':not saturated,
                  'cursor_before':av.clock_string(start),'cursor_after':None if saturated else av.clock_string(end),
                  'saturated':saturated})
                successes+=1
            except Exception as exc:
                run.failed+=1
                if not dry_run:
                    outcomes.append({'window_id':str(window['window_id']),'lease_owner':run.execution_name,'status':'failed'})
                run.groups.append({'query_identity':qid,'coverage_complete':False,'error_class':str(exc) if isinstance(exc,av.SourceError) else type(exc).__name__})
        if rows:
            rows=prepare_news_rows(pd.DataFrame(rows)).to_dict('records')
        if len(rows)>40000 or len(av.canonical(rows).encode())>64*1024*1024:
            raise av.SourceError('news_group_limit')
        if not dry_run:
            try:
                _write_news_group(rows,captures,outcomes,final,executor)
            except Exception:
                # Proposed frontiers are not evidence of committed coverage.
                for note in run.groups[group_start:]:
                    note.update(coverage_complete=False,complete_through=None,cursor_after=None,
                                commit_outcome='unknown_or_failed')
                raise
            run.rows_written+=len(rows)
        run.processed+=successes
        if dry_run:
            run.pending=max(0,len(windows)-run.attempted)+sum(bool(g.get('saturated')) for g in run.groups)
            break
        if budget_exhausted:
            break
    if not dry_run:
        facts=executor("""SELECT query_identity,
          min(window_start) FILTER(WHERE status NOT IN ('complete','split')) AS first_gap,
          max(window_end) FILTER(WHERE status='complete') AS completed_end,
          count(*) FILTER(WHERE status NOT IN ('complete','split')) AS pending
          FROM av_catalyst_news_windows WHERE query_identity=ANY(CAST(:ids AS text[])) GROUP BY query_identity""",
          {'ids':list(limits)},read=True,timeout_s=8)
        run.pending=sum(f['pending'] for f in facts)
        for f in facts:
            through=f['first_gap'] or f['completed_end']
            run.groups.append({'query_identity':f['query_identity'],'complete_through':av.clock_string(through) if through is not None else None,
                               'coverage_complete':not f['pending'],'pending':f['pending']})
    return run


def main(argv=None):
    from gcp.fetchers import _av_ingestion as av
    args=build_parser().parse_args(argv)
    run=av.Run('fetch-news-sentiment','topics' if args.topics and not args.tickers else 'earnings' if args.earnings_window_days else 'tickers')
    try:
        key=os.environ.get('AV_API_KEY') or os.environ.get('ALPHA_VANTAGE_API_KEY')
        if not key:
            raise av.SourceError('credential_missing')
        tickers=[t.strip().upper() for t in args.tickers.split(',') if t.strip()]
        topics=[t.strip().lower() for t in args.topics.split(',') if t.strip()]
        if len(topics)>5 or not 1<=args.limit<=1000 or not 1<=args.max_requests<=300:
            raise av.SourceError('news_admission_limit')
        if not tickers and not topics:
            frame=av.read_dataframe("""SELECT DISTINCT ticker FROM (
              SELECT ticker FROM watchlists WHERE removed_at IS NULL UNION SELECT ticker FROM earnings_calendar
              WHERE :days>0 AND earnings_date BETWEEN (NOW() AT TIME ZONE 'America/New_York')::date-CAST(:days AS integer)
                AND (NOW() AT TIME ZONE 'America/New_York')::date+CAST(:days AS integer)
            ) scoped ORDER BY ticker""",{'days':args.earnings_window_days},timeout_s=5)
            tickers=frame['ticker'].str.upper().tolist() if not frame.empty else []
        if len(tickers)>min(300,args.max_tickers):
            raise av.SourceError('news_universe_requires_explicit_shards')
        now=datetime.now(timezone.utc).replace(second=0,microsecond=0)
        start=datetime.strptime(args.time_from,'%Y%m%dT%H%M').replace(tzinfo=timezone.utc) if args.time_from else now-timedelta(hours=48)
        end=datetime.strptime(args.time_to,'%Y%m%dT%H%M').replace(tzinfo=timezone.utc)+timedelta(minutes=1) if args.time_to else now
        if end<=start or end-start>timedelta(days=7):
            raise av.SourceError('news_window_admission_limit')
        scopes=news_window_scopes(tickers,topics,start,end);run.expected=len(scopes)
        final=False if args.dry_run else av.identity_state('news_sentiment')
        run_news_windows(run,scopes,key,limit=args.limit,max_requests=min(args.max_requests,30 if topics and not tickers else 300),dry_run=args.dry_run,final=final)
    except Exception as exc:
        run.failed+=1
        run.groups.append({'coverage_complete':False,'error_class':str(exc) if isinstance(exc,av.SourceError) else type(exc).__name__})
    try:
        return run.terminal(dry_run=args.dry_run)
    finally:
        av.close_sql_worker()


if __name__=='__main__':
    raise SystemExit(main())
