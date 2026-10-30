"""Clocked thirty-minute opening projection; no acquisition or client math.

ORB-only extraction of the qualified compute_observed_intraday_levels source
(fac3ad1fb86235b8321254c65d5f836242253b250629e02bec350282683dce08).
Completeness precedes reduction; completed start-labelled minutes only.
"""
from datetime import datetime, timedelta
import hashlib
import json
import math
import re
import threading
from collections import OrderedDict
import pandas_market_calendars as mcal
from lib.eastern_time import as_utc_instant, localize_assuming_eastern, market_date

MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 50_000
MAX_COMPARISON_AGE = 120

class OpeningUnavailable(ValueError):
    """Fixed safe reason only; never include provider bodies or credentials."""

# One builder across router/evaluator; cache hits never wait behind a cold build.
_SCHEDULE_CACHE = OrderedDict()
_SCHEDULE_LOCK = threading.Lock()
_CALENDAR_BUILD_LOCK = threading.Lock()

def _schedule(day):
    with _SCHEDULE_LOCK:
        if day in _SCHEDULE_CACHE:
            _SCHEDULE_CACHE.move_to_end(day)
            return _SCHEDULE_CACHE[day]
    if not _CALENDAR_BUILD_LOCK.acquire(blocking=False):
        raise OpeningUnavailable('calendar_in_progress')
    try:
        with _SCHEDULE_LOCK:
            if day in _SCHEDULE_CACHE:
                return _SCHEDULE_CACHE[day]
        frame=mcal.get_calendar('NYSE').schedule(start_date=day,end_date=day)
        result=None
        if not frame.empty:
            row=frame.iloc[0]
            result={'label':day.isoformat(),'open':row.market_open.to_pydatetime(),'close':row.market_close.to_pydatetime(),'calendar':'NYSE','calendar_version':mcal.__version__}
        with _SCHEDULE_LOCK:
            _SCHEDULE_CACHE[day]=result
            if len(_SCHEDULE_CACHE)>8:
                _SCHEDULE_CACHE.popitem(last=False)
        return result
    finally:
        _CALENDAR_BUILD_LOCK.release()

def session_for(now):
    try:
        return _schedule(market_date(as_utc_instant(now)))
    except (ValueError,TypeError,OverflowError) as exc:
        if isinstance(exc,OpeningUnavailable):raise
        raise OpeningUnavailable('invalid_session_timestamp') from None

def vendor_time(value):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}',value):
        raise OpeningUnavailable('invalid_timestamp')
    try:
        t=datetime.strptime(value,'%Y-%m-%d %H:%M:%S')
        return as_utc_instant(localize_assuming_eastern(t))
    except (ValueError,TypeError,OverflowError):raise OpeningUnavailable('invalid_timestamp') from None

def compute_observed_opening_range(bars, *, now, session):
    try:
        return _compute_observed_opening_range(bars, now=now, session=session)
    except OverflowError:
        raise OpeningUnavailable('invalid_timestamp') from None

def _compute_observed_opening_range(bars, *, now, session):
    now=as_utc_instant(now)
    if session is None:raise OpeningUnavailable('no_session')
    opening,closing=session['open'],session['close']
    end=opening+timedelta(minutes=30)
    if now<end:raise OpeningUnavailable('opening_in_progress')
    if closing<end:raise OpeningUnavailable('short_session')
    if market_date(now).isoformat()!=session['label']:raise OpeningUnavailable('wrong_session')
    expected={opening+timedelta(minutes=i) for i in range(30)}
    selected=[b for b in bars if opening<=b['instant']<end]
    times=[b['instant'] for b in selected]
    if len(times)!=len(set(times)):raise OpeningUnavailable('duplicate_opening_minutes')
    if set(times)-expected:raise OpeningUnavailable('off_grid_opening_minutes')
    if expected-set(times):raise OpeningUnavailable('missing_opening_minutes')
    # Full window is complete before extrema, never a partial prefix.
    return max(b['high'] for b in selected),min(b['low'] for b in selected)

def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise OpeningUnavailable('duplicate_json_key')
        result[key]=value
    return result

def parse_acquisition(body, ticker, now, session):
    try:
        return _parse_acquisition(body, ticker, now, session)
    except OverflowError:
        raise OpeningUnavailable('invalid_timestamp') from None

def _parse_acquisition(body, ticker, now, session):
    now=as_utc_instant(now)
    if len(body)>MAX_BYTES:raise OpeningUnavailable('body_limit')
    try:data=json.loads(body,object_pairs_hook=_pairs,parse_constant=lambda _: (_ for _ in ()).throw(OpeningUnavailable('nonfinite_json')))
    except (ValueError,UnicodeError,RecursionError) as e:
        if isinstance(e,OpeningUnavailable):raise
        raise OpeningUnavailable('invalid_json') from None
    if not isinstance(data,dict):raise OpeningUnavailable('invalid_envelope')
    if any(k in data for k in ('Note','Information','Error Message')):raise OpeningUnavailable('provider_error')
    meta=data.get('Meta Data');series=data.get('Time Series (1min)')
    if not isinstance(meta,dict) or meta.get('2. Symbol')!=ticker or meta.get('4. Interval')!='1min' or meta.get('6. Time Zone') not in ('US/Eastern','America/New_York'):
        raise OpeningUnavailable('source_identity')
    refreshed=vendor_time(meta.get('3. Last Refreshed'))
    if refreshed>now:raise OpeningUnavailable('future_source')
    if not isinstance(series,dict) or not series:raise OpeningUnavailable('empty_or_invalid_series')
    if len(series)>MAX_ROWS:raise OpeningUnavailable('row_limit')
    if session is None:raise OpeningUnavailable('no_session')
    bars=[]
    instants=set()
    for stamp,values in series.items():
        ts=vendor_time(stamp)
        if ts in instants:raise OpeningUnavailable('duplicate_bar_instant')
        instants.add(ts)
        if ts.second or ts.microsecond:raise OpeningUnavailable('off_grid_bar')
        if ts>now or ts>refreshed:raise OpeningUnavailable('future_bar')
        try:
            if not isinstance(values,dict):raise ValueError()
            prices=[float(values[k]) for k in ('1. open','2. high','3. low','4. close')]
            volume=float(values['5. volume'])
            if any(isinstance(values[k],bool) for k in ('1. open','2. high','3. low','4. close','5. volume')):raise ValueError()
            o,h,l,c=prices
            if not all(math.isfinite(v) and v>0 for v in prices) or not math.isfinite(volume) or volume<0 or not volume.is_integer() or not l<=min(o,c)<=max(o,c)<=h:raise ValueError()
        except (ValueError,TypeError,KeyError,OverflowError):raise OpeningUnavailable('invalid_price_or_volume') from None
        if session['open']<=ts<session['close'] and ts+timedelta(minutes=1)<=now:
            bars.append({'instant':ts,'time':stamp,'open':o,'high':h,'low':l,'close':c,'volume':int(volume)})
    bars.sort(key=lambda b:b['instant'])
    high,low=compute_observed_opening_range(bars,now=now,session=session)
    comparison=bars[-1];comparison_end=comparison['instant']+timedelta(minutes=1)
    age=(now-comparison_end).total_seconds()
    if not 0<=age<=MAX_COMPARISON_AGE:raise OpeningUnavailable('stale_comparison')
    projection={'status':'available','reason':None,'ticker':ticker,'session':session['label'],'window_minutes':30,'window_start':session['open'].isoformat(),'window_end':(session['open']+timedelta(minutes=30)).isoformat(),'high':high,'low':low,'comparison_price':comparison['close'],'comparison_as_of':comparison_end.isoformat(),'comparison_age_seconds':age,'price_basis':'as_traded_requested','source':'alphavantage','fetched_at':now.isoformat(),'source_last_refreshed':refreshed.isoformat(),'body_sha256':hashlib.sha256(body).hexdigest(),'calendar_version':session['calendar_version']}
    if len(json.dumps(projection).encode())>4096:raise OpeningUnavailable('projection_limit')
    return {'ticker':ticker,'interval':'1min','count':min(len(bars),100),'market_session':'regular' if session['open']<=now<session['close'] else 'closed','market_open':session['open']<=now<session['close'],'bars':[{k:v for k,v in b.items() if k!='instant'} for b in bars[-100:]],'opening':projection}
