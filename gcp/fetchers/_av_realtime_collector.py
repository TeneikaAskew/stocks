#!/usr/bin/env python3
"""
Cloud Run Job: Fetch intraday AV REALTIME_OPTIONS and write to Cloud SQL.

Companion to fetch_av_historical_options.py. The historical job runs nightly
and writes one EOD snapshot per ticker per day (market_session='EOD'). This
job runs every 5 minutes during actual NYSE regular sessions and writes one
intraday snapshot per ticker per fire (market_session='REALTIME'). Both
coexist in etf_options_snapshots via the unique key
(ticker, snapshot_ts, option_type, expiration, strike).

Why this exists:
    Added 2026-05-22 after AV subscription upgrade to the $199.99/mo,
    600 req/min, realtime-options tier. Prior to this, the entire repo
    only had EOD options data — see
    docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md for the multi-track
    plan this fetcher unlocks:
      Track 1 — premarket brief gamma section (realtime-primary)
      Track 2 — 0DTE theta replacement (observed > empirical curve)
      Track 3 — signal monitor "approaching the King" alerts
      Track 4 — OptionsFlowPage freshness badge
      Track 5 — AI insights gamma integration

Usage:
    python -m gcp.fetchers.fetch_av_realtime_options [--tickers "SPY IWM QQQ"]
"""

import argparse
import json
import logging
import math
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import upsert_dataframe, is_cloud_sql_configured
from gcp.fetchers import _av_realtime_transport as _cli_transport
from lib.config import AlphaVantageConfig

from lib.logging_config import setup_logging
setup_logging()
log = logging.getLogger(__name__)

AV_BASE_URL = 'https://www.alphavantage.co/query'
DEFAULT_TICKERS = ['SPY', 'IWM', 'QQQ']
_av_cfg = AlphaVantageConfig()

# Sentinel contractID prefix AV returns when the subscription tier does NOT
# include REALTIME_OPTIONS — we explicitly detect and reject this so a
# silently-downgraded plan doesn't poison etf_options_snapshots with fake
# rows like contractID=XXYYZZ999999C00020000.
_SAMPLE_CONTRACT_PREFIX = 'XXYYZZ'


from gcp.fetchers.fetch_av_realtime_options import RealtimeOptionsUnavailable


from gcp.fetchers.fetch_av_realtime_options import RealtimeOptionsEmpty


# In-run retries for RealtimeOptionsEmpty only. 2 retries x ~1 pacing delay
# adds at most ~2 extra API calls and a few seconds of wall-clock on the
# rare empty fire — trivial against the 600 req/min tier and the job
# timeout — and converts the sporadic vendor blip (a few per hundred
# 5-minute fires, each paging Discord + appending to a gcp-job-failure
# issue) into a green run. A ticker still empty after all attempts keeps
# the Rule 3.7 hard-fail: no data is fabricated, the job exits non-zero.
EMPTY_RETRY_ATTEMPTS = 2


_ATTEMPT_EVENT_MAX_BYTES = 2048
_NO_RESPONSE_PAYLOAD = object()
_LOG_TICKER_PREVIEW_LIMIT = 16
_REQUEST_ID_HEADERS = ('x-request-id', 'request-id')
_UUID_RE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
_HTTP_DATE_RE = re.compile(
    r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun), [0-9]{2} '
    r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) '
    r'[0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2} GMT'
)


def _safe_ticker(ticker):
    # This projection never changes the symbol accepted by source transport.
    if type(ticker) is str and len(ticker) == 3:
        candidate = ticker.upper()
        if candidate in DEFAULT_TICKERS:
            return candidate
    return 'unavailable'


def _monotonic():
    try:
        value = time.monotonic()
        if type(value) in (int, float) and math.isfinite(value):
            return value
    except Exception:
        pass
    return None


def _safe_header(response, name, max_length):
    try:
        value = response.headers.get(name)
        if type(value) is str and len(value) <= max_length:
            return value
    except Exception:
        pass
    return None


def _safe_retry_after(response):
    value = _safe_header(response, 'retry-after', 29)
    if value is None:
        return None
    if re.fullmatch(r'0|[1-9][0-9]{0,4}', value):
        seconds = int(value)
        return seconds if seconds <= 86400 else None
    if _HTTP_DATE_RE.fullmatch(value):
        try:
            parsed = parsedate_to_datetime(value)
            if format_datetime(parsed, usegmt=True) == value:
                return value
        except (ValueError, TypeError, OverflowError):
            pass
    return None


def _response_schema(payload=_NO_RESPONSE_PAYLOAD):
    """Fixed schema enums only: no provider values or arbitrary key names.

    Inspect a constant number of known fields; never walk records or copy
    body/header/error text. This is diagnostic and never changes admission.
    """
    if payload is _NO_RESPONSE_PAYLOAD:
        return {'body': 'unavailable'}
    if type(payload) is not dict:
        return {'body': 'nonobject'}

    def label(key, expected):
        if key not in payload:
            return 'missing'
        value = payload[key]
        if value is None:
            return 'null'
        return 'expected' if type(value) is str and value == expected else 'other'

    if 'data' not in payload:
        records = 'missing'
    else:
        value = payload['data']
        if value is None:
            records = 'null'
        elif type(value) is list:
            records = 'array_nonempty' if value else 'array_empty'
        else:
            records = {dict: 'object', str: 'string', int: 'number',
                       float: 'number', bool: 'boolean'}.get(type(value), 'other')
    return {
        'body': 'object',
        'present': [key for key in ('data', 'endpoint', 'message', 'Information',
                                   'Error Message', 'Note') if key in payload],
        'endpoint': label('endpoint', 'Realtime Options'),
        'message': label('message', 'success'),
        'records': records,
    }


def _emit_attempt_event(ticker, attempt, response, started, error_class,
                        response_payload=_NO_RESPONSE_PAYLOAD):
    """Fixed source projection: never copy credentials/params/body/errors.

    Only two 36-character UUIDs and a 29-character Retry-After can enter
    from headers. No header iteration or parsing of oversized values.
    """
    status = None
    try:
        observed = response.status_code
        if type(observed) is int and 100 <= observed <= 599:
            status = observed
    except Exception:
        pass
    finished = _monotonic()
    elapsed = 0.0
    if started is not None and finished is not None:
        delta = finished - started
        if math.isfinite(delta) and delta >= 0:
            elapsed = round(delta, 6)
    request_ids = {}
    for name in _REQUEST_ID_HEADERS:
        value = _safe_header(response, name, 36)
        if value is not None and _UUID_RE.fullmatch(value):
            request_ids[name] = value
    event = {
        'event': 'av_realtime_options_attempt',
        'attempt': attempt if type(attempt) is int and 1 <= attempt <= 3 else 1,
        'function': 'REALTIME_OPTIONS',
        'require_greeks': 'true',
        'datatype': 'json',
        'ticker': _safe_ticker(ticker),
        'http_status': status,
        'elapsed_s': elapsed,
        'error_class': error_class,
        'request_ids': request_ids,
        'retry_after': _safe_retry_after(response),
        'response_schema': _response_schema(response_payload),
    }
    message = json.dumps(event, separators=(',', ':'), allow_nan=False)
    # The fixed fields and individual caps fit well below this ceiling.
    # Keep an explicit whole-event bound if the projection changes later.
    if len(message.encode('utf-8')) > _ATTEMPT_EVENT_MAX_BYTES:
        event['request_ids'] = {}
        event['retry_after'] = None
        message = json.dumps(event, separators=(',', ':'), allow_nan=False)
    log.info('%s', message)


class _SourceBudget:
    """One shared, cumulative source budget for the scheduled ticker loop.

    Spec docs/superpowers/specs/2026-10-31-feat-option-001-source-budget-
    excludes-persistence.md, rules 1 to 10. Every source operation spends it;
    only the elapsed time of each upsert_dataframe invocation is excluded
    (pause/resume). It never resets, extends or revives, and an exhausted
    budget presents the unchanged transport with an invalid deadline.

    Covered readings are exactly: creation, source-admission checkpoints,
    post-call checkpoints, pause and resume. Each must be a valid transport
    clock reading at or above the last trusted reading; anything else
    exhausts the budget. Telemetry and transport-internal readings are not
    covered (rule 9).
    """

    @staticmethod
    def _clock(point):
        # point names the covered reading; it is a seam for tests only.
        return _cli_transport._source_now()

    def __init__(self):
        try:
            reading = self._clock('create')
        except Exception:
            raise _cli_transport.SourceDeadline() from None
        if type(reading) not in (int, float) or not math.isfinite(reading):
            raise _cli_transport.SourceDeadline()
        deadline = reading + _cli_transport._SOURCE_PHASE_SECONDS
        if not math.isfinite(deadline) or not deadline > reading:
            raise _cli_transport.SourceDeadline()
        self._last = reading
        self._deadline = deadline
        self._exhausted = False
        self._paused = False
        self._held = None

    @property
    def exhausted(self):
        return self._exhausted

    def _read(self, point):
        """Return a trusted reading, or exhaust the budget and return None."""
        if self._exhausted:
            return None
        try:
            reading = self._clock(point)
            if (type(reading) in (int, float) and math.isfinite(reading)
                    and reading >= self._last):
                self._last = reading
                return reading
        except Exception:
            pass
        self._exhausted = True
        return None

    def deadline(self):
        """The current absolute deadline, or NaN once exhausted (rule 8)."""
        return math.nan if self._exhausted else self._deadline

    def checkpoint(self):
        """Source-admission checkpoint: refuse before dispatch (rule 3)."""
        if self._read('admit') is None:
            raise _cli_transport.SourceDeadline()
        return self._deadline

    def post_call(self):
        """Post-call checkpoint after decoded_json returns or raises."""
        try:
            self._read('post_call')
        except Exception:
            self._exhausted = True

    def pause(self):
        """Immediately before the single upsert_dataframe invocation (rule 5)."""
        try:
            if self._paused:
                self._exhausted = True  # second pause before a resume (rule 7)
                return
            self._paused = True
            self._held = None
            reading = self._read('pause')
            if reading is None:
                return
            held = self._deadline - reading
            if not math.isfinite(held) or held <= 0:
                self._exhausted = True
                return
            self._held = held
        except Exception:
            self._exhausted = True

    def resume(self):
        """Immediately after the invocation returns or raises (rule 6)."""
        try:
            if not self._paused:
                self._exhausted = True  # resume without a pause (rule 7)
                return
            self._paused = False
            held, self._held = self._held, None
            reading = self._read('resume')
            if reading is None or held is None:
                self._exhausted = True
                return
            deadline = reading + held
            # Never restore more than the held remainder: round down.
            for _ in range(4):
                if not (math.isfinite(deadline) and deadline - reading > held):
                    break
                deadline = math.nextafter(deadline, -math.inf)
            restored = deadline - reading
            if not (math.isfinite(deadline) and math.isfinite(restored)
                    and 0 < restored <= held):
                self._exhausted = True
                return
            self._deadline = deadline
        except Exception:
            self._exhausted = True


def fetch_av_realtime_options(ticker: str, api_key: str,
                              snapshot_ts: datetime, *, _attempt: int = 1,
                              _source_deadline=None,
                              _source_budget=None) -> pd.DataFrame:
    """
    Fetch the current intraday options chain from AV REALTIME_OPTIONS.

    Args:
        ticker:       symbol (e.g. 'SPY')
        api_key:      AV API key with realtime-options entitlement
        snapshot_ts:  the wall-clock timestamp to stamp this snapshot with.
                      Passed in so every ticker in a single run shares
                      the same snapshot_ts (multi-ticker queries don't
                      drift across ticker iteration time).

    Returns:
        Normalized DataFrame ready for etf_options_snapshots.

    Raises:
        RealtimeOptionsUnavailable: AV returned sample data or an error
            response — never returns an empty DataFrame to a caller that
            might write it (Rule 3.7).
        requests.exceptions.HTTPError: HTTP-layer failures bubble up.
    """
    params = {
        'function':       'REALTIME_OPTIONS',
        'symbol':         ticker,
        'require_greeks': 'true',
        'apikey':         api_key,
        'datatype':       'json',
    }

    response = None
    response_payload = _NO_RESPONSE_PAYLOAD
    started = _monotonic()
    error_class = 'transport_error'
    try:
        if _source_deadline is None:
            # API workers retain their existing path: no main-thread signals.
            response = requests.get(AV_BASE_URL, params=params, timeout=60)
            error_class = 'http_error'
            response.raise_for_status()
            error_class = 'json_error'
            try:
                data = response.json()
            except Exception:
                raise RealtimeOptionsUnavailable('AV REALTIME_OPTIONS JSON error') from None
        else:
            def observed_response(observed):
                nonlocal response, error_class
                response = observed
                error_class = 'http_error'
            try:
                try:
                    data = _cli_transport.decoded_json(params, _source_deadline, observed_response)
                finally:
                    if _source_budget is not None:
                        _source_budget.post_call()
            except _cli_transport.SourceUnavailable as error:
                category = error.category
                error_class = category if category in (
                    'transport_error', 'http_error', 'json_error', 'source_deadline', 'body_limit'
                ) else 'transport_error'
                raise RealtimeOptionsUnavailable('AV REALTIME_OPTIONS source unavailable') from None
            except requests.RequestException as error:
                error_class = 'http_error' if isinstance(error, requests.HTTPError) else 'transport_error'
                raise
        response_payload = data

        error_class = 'parse_error'
        try:
            # Classifications and exception reasons are fixed; provider text
            # (including endpoint/message/contract IDs) is never reflected.
            if 'Information' in data and 'data' not in data:
                error_class = 'provider_info'
                raise RealtimeOptionsUnavailable('AV REALTIME_OPTIONS rate-limit / info response')
            if 'Error Message' in data:
                error_class = 'provider_error'
                raise RealtimeOptionsUnavailable('AV REALTIME_OPTIONS provider error')

            records = data.get('data')
            if type(records) is list and records:
                first_contract = str(records[0].get('contractID', ''))
                if first_contract.startswith(_SAMPLE_CONTRACT_PREFIX):
                    error_class = 'sample'
                    raise RealtimeOptionsUnavailable('AV REALTIME_OPTIONS returned sample/illustration data')

            if data.get('endpoint') != 'Realtime Options' or data.get('message') != 'success':
                error_class = 'unexpected_response'
                raise RealtimeOptionsUnavailable('AV REALTIME_OPTIONS unexpected response')

            # Retry only the documented literal empty-array shape. Missing,
            # null or other JSON types do not establish an empty chain.
            if 'data' not in data:
                error_class = 'data_missing'
                raise RealtimeOptionsUnavailable('AV REALTIME_OPTIONS data missing')
            if records is None:
                error_class = 'data_null'
                raise RealtimeOptionsUnavailable('AV REALTIME_OPTIONS data null')
            if type(records) is not list:
                error_class = 'data_type'
                raise RealtimeOptionsUnavailable('AV REALTIME_OPTIONS data type unavailable')
            if not records:
                error_class = 'empty'
                raise RealtimeOptionsEmpty('AV REALTIME_OPTIONS returned 0 contracts')

            df = _normalize_av_response(pd.DataFrame(records), ticker, snapshot_ts)
        except RealtimeOptionsUnavailable:
            raise
        except Exception:
            raise RealtimeOptionsUnavailable('AV REALTIME_OPTIONS parsing error') from None
        error_class = None
        return df
    finally:
        try:
            _emit_attempt_event(ticker, _attempt, response, started, error_class,
                                response_payload)
        except Exception:
            # A failed telemetry sink must not replace the source outcome.
            # Even its exception can contain unsafe data; never reflect it.
            try:
                log.warning('AV REALTIME_OPTIONS attempt telemetry unavailable')
            except Exception:
                pass


from gcp.fetchers.fetch_av_realtime_options import _normalize_av_response


def process_ticker(ticker: str, api_key: str, snapshot_ts: datetime, *,
                   _source_deadline=None, _source_budget=None) -> int:
    """Fetch one ticker and return its complete acknowledged upsert count."""
    import time

    _require_persistence()

    log.info("  Fetching %s realtime options at %s...",
             _safe_ticker(ticker), snapshot_ts.isoformat())

    # Retry ONLY the transient-empty shape; all other Unavailable causes
    # propagate immediately (see RealtimeOptionsEmpty docstring).
    for attempt in range(EMPTY_RETRY_ATTEMPTS + 1):
        try:
            source_kwargs = {'_attempt': attempt + 1}
            if _source_budget is not None:
                source_kwargs['_source_deadline'] = _source_budget.deadline()
                source_kwargs['_source_budget'] = _source_budget
            elif _source_deadline is not None:
                source_kwargs['_source_deadline'] = _source_deadline
            df = fetch_av_realtime_options(ticker, api_key, snapshot_ts, **source_kwargs)
            break
        except RealtimeOptionsEmpty:
            if attempt == EMPTY_RETRY_ATTEMPTS:
                raise RealtimeOptionsEmpty(
                    "AV REALTIME_OPTIONS returned 0 contracts "
                    f"on {EMPTY_RETRY_ATTEMPTS + 1} attempts — off-hours "
                    "fire or vendor outage"
                )
            log.warning(
                "    %s returned 0 contracts (attempt %d/%d) — retrying",
                _safe_ticker(ticker), attempt + 1, EMPTY_RETRY_ATTEMPTS + 1,
            )
            if _source_budget is not None:
                try:
                    _cli_transport.pace(_source_budget.checkpoint(),
                                        _av_cfg.delay_between_calls)
                except _cli_transport.SourceUnavailable:
                    raise RealtimeOptionsUnavailable('AV REALTIME_OPTIONS source pacing unavailable') from None
            elif _source_deadline is None:
                time.sleep(_av_cfg.delay_between_calls)
            else:
                try:
                    _cli_transport.pace(_source_deadline, _av_cfg.delay_between_calls)
                except _cli_transport.SourceUnavailable:
                    raise RealtimeOptionsUnavailable('AV REALTIME_OPTIONS source pacing unavailable') from None
    log.info("    %d contracts received", len(df))

    # Dedupe defensively — AV occasionally returns duplicate contract rows
    # within a single response.
    conflict_cols = ['ticker', 'snapshot_ts', 'option_type', 'expiration', 'strike']
    before = len(df)
    df = df.drop_duplicates(subset=conflict_cols, keep='last')
    if len(df) < before:
        log.info("    deduped %d → %d rows", before, len(df))

    # Persistence elapsed time is excluded from the source budget: pause
    # immediately before the one invocation, resume immediately after it
    # returns or raises. Neither can prevent, repeat or alter the write.
    if _source_budget is not None:
        _source_budget.pause()
    try:
        try:
            acknowledged = upsert_dataframe(df, 'etf_options_snapshots', conflict_cols)
        finally:
            if _source_budget is not None:
                _source_budget.resume()
    except Exception:
        # The helper commits per chunk. An exception cannot prove zero writes.
        log.error("    write outcome uncertain; partial chunks may have committed")
        raise
    if type(acknowledged) is not int or acknowledged <= 0 or acknowledged != len(df):
        # Never format an untrusted helper result into diagnostics.
        raise RealtimeOptionsUnavailable("AV REALTIME_OPTIONS write acknowledgement unavailable")
    log.info("    ✓ upserted %d acknowledged rows to Cloud SQL", acknowledged)

    return acknowledged


def _require_persistence():
    """Pure configuration preflight; never initializes an engine."""
    try:
        configured = is_cloud_sql_configured()
    except Exception:
        configured = False
    if configured is not True:
        raise RealtimeOptionsUnavailable("AV REALTIME_OPTIONS persistence unavailable")


def _regular_session_due(snapshot_ts):
    """Admit only a proven actual NYSE [open, close) on the Eastern date."""
    try:
        from gcp.fetchers.evaluate_ew_strikes import nyse_sessions
        from lib.eastern_time import ET

        if not isinstance(snapshot_ts, date):
            raise ValueError
        now = pd.Timestamp(snapshot_ts)
        if pd.isna(now) or now.tzinfo is None:
            raise ValueError
        session_date = now.tz_convert(ET).date()
        sessions = nyse_sessions(session_date, session_date)
        if (not isinstance(sessions, pd.DataFrame)
                or not {'market_open', 'market_close'}.issubset(sessions.columns)
                or not sessions.columns.is_unique
                or not isinstance(sessions.index, pd.DatetimeIndex)
                or len(sessions) > 1):
            raise ValueError
        if sessions.empty:
            return False
        if sessions.index[0] != pd.Timestamp(session_date):
            raise ValueError
        opened = pd.Timestamp(sessions.iloc[0]['market_open'])
        closed = pd.Timestamp(sessions.iloc[0]['market_close'])
        if (pd.isna(opened) or pd.isna(closed)
                or opened.tzinfo is None or closed.tzinfo is None
                or opened.tz_convert(ET).date() != session_date
                or closed.tz_convert(ET).date() != session_date
                or opened >= closed):
            raise ValueError
        return opened <= now < closed
    except Exception:
        raise RealtimeOptionsUnavailable("AV REALTIME_OPTIONS NYSE calendar unavailable") from None


def main():
    import time

    parser = argparse.ArgumentParser(
        description='Fetch intraday AV REALTIME_OPTIONS to Cloud SQL'
    )
    parser.add_argument(
        '--tickers',
        default=' '.join(DEFAULT_TICKERS),
        help='Space-separated tickers (default: "SPY IWM QQQ"). '
             'SPX/NDX excluded — AV returns "-" for index-option Greeks; '
             'the BSM solver in lib/options_greeks.py only runs in the '
             'EOD pipeline today.',
    )
    args = parser.parse_args()

    tickers = args.tickers.upper().split()
    if not tickers:
        log.error("AV REALTIME_OPTIONS ticker scope unavailable")
        sys.exit(1)
    # Admission precedes source calls and persistence, including engine creation.
    # One snapshot clock aligns every ticker in this batch.
    try:
        snapshot_ts = datetime.now(timezone.utc)
        due = _regular_session_due(snapshot_ts)
    except Exception:
        log.error("AV REALTIME_OPTIONS NYSE calendar unavailable")
        sys.exit(1)
    if not due:
        log.info("AV REALTIME_OPTIONS not_due: outside actual NYSE regular session")
        return
    try:
        _require_persistence()
    except RealtimeOptionsUnavailable:
        log.error("AV REALTIME_OPTIONS persistence unavailable")
        sys.exit(1)

    api_key = (os.environ.get('AV_API_KEY')
               or os.environ.get('ALPHA_VANTAGE_API_KEY', ''))
    if not api_key:
        log.error("AV_API_KEY not set — cannot fetch realtime options")
        sys.exit(1)

    log.info("Fetch AV Realtime Options Job")
    log.info("  Tickers (first %d): %s", _LOG_TICKER_PREVIEW_LIMIT,
             [_safe_ticker(ticker) for ticker in tickers[:_LOG_TICKER_PREVIEW_LIMIT]])
    log.info("  Snapshot_ts : %s", snapshot_ts.isoformat())
    log.info("  SQL         : configured")

    try:
        source_budget = _SourceBudget()
    except _cli_transport.SourceUnavailable:
        log.error("AV REALTIME_OPTIONS source deadline unavailable")
        sys.exit(1)
    errors = []
    total_rows = 0
    for i, ticker in enumerate(tickers):
        try:
            admitted = source_budget.checkpoint()
            if i > 0:
                _cli_transport.pace(admitted, _av_cfg.delay_between_calls)
            total_rows += process_ticker(ticker, api_key, snapshot_ts,
                                         _source_budget=source_budget)
        except (RealtimeOptionsUnavailable, _cli_transport.SourceUnavailable):
            # Track which tickers were unavailable; we still try the rest.
            # Job exits non-zero at the end if any ticker failed, which lets
            # Cloud Run/Scheduler surface the failure without spamming
            # one-ticker-failed emails when the other two succeeded.
            log.error("  ✗ %s realtime UNAVAILABLE", _safe_ticker(ticker))
            errors.append(f"{_safe_ticker(ticker)}: unavailable")
        except Exception:
            log.error("  ✗ %s failed", _safe_ticker(ticker))
            errors.append(f"{_safe_ticker(ticker)}: failed")

    log.info(
        "Done. %d tickers, %d acknowledged contracts written, %d errors. "
        "Failed write outcomes may be partial or uncertain; no independent SQL verification.",
        len(tickers), total_rows, len(errors),
    )

    if errors:
        log.error("Failed (%d): %s", len(errors), errors[:_LOG_TICKER_PREVIEW_LIMIT])
        sys.exit(1)


if __name__ == '__main__':
    main()
