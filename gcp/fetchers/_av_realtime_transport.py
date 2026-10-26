"""Private CLI transport: bounded source I/O only, no retry or storage policy.

Algorithms retained from the accepted A10 source packet. Direct API workers do
not use this helper; SIGALRM requires exclusively owned main-thread execution.
"""
import json
import math
import signal
import threading
import time
import zlib
from contextlib import contextmanager
from time import monotonic as _source_clock

import requests
from urllib3.exceptions import ProtocolError, ReadTimeoutError

_SOURCE_PHASE_SECONDS=15.0
_SOURCE_BODY_MAX_BYTES=10*1024*1024
_ENDPOINT='https://www.alphavantage.co/query'
_CLEANUP_SECONDS=0.05


class SourceUnavailable(RuntimeError):
    def __init__(self,category='json_error'):
        if category not in ('transport_error','http_error','json_error','source_deadline','body_limit'):
            category='json_error'
        self.category=category
        super().__init__(category)


class SourceDeadline(SourceUnavailable):
    def __init__(self):super().__init__('source_deadline')


class SourceBodyLimit(SourceUnavailable):
    def __init__(self):super().__init__('body_limit')


class _NoSourceAuth(requests.auth.AuthBase):
    def __init__(self, response_hook):
        self._response_hook = response_hook

    def __call__(self, request):
        # A truthy explicit auth object prevents Requests from consulting netrc.
        # It adds no Authorization header or challenge-response retry hook.
        request.register_hook('response', self._response_hook)
        return request


def _source_now():
    try:
        observed = _source_clock()
        if type(observed) in (int, float) and math.isfinite(observed):
            return observed
    except Exception:
        pass
    raise SourceDeadline()


def deadline(deadline=None):
    if deadline is None:
        deadline = _source_now() + _SOURCE_PHASE_SECONDS
    remaining(deadline)
    return deadline


def remaining(deadline):
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise SourceDeadline()
    remaining = deadline - _source_now()
    if not math.isfinite(remaining) or remaining <= 0:
        raise SourceDeadline()
    return remaining


@contextmanager
def _interrupt_source(deadline):
    # SIGALRM is exclusively owned during one transport/body operation or pace.
    # Never overwrite another caller's timer or attempt signals from a worker.
    if (threading.current_thread() is not threading.main_thread()
            or not all(hasattr(signal, name) for name in
                       ('SIGALRM', 'ITIMER_REAL', 'setitimer', 'getitimer',
                        'pthread_sigmask', 'SIG_BLOCK'))):
        raise SourceDeadline()
    if signal.SIGALRM in signal.pthread_sigmask(signal.SIG_BLOCK, set()):
        raise SourceDeadline()
    if signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0):
        raise SourceDeadline()
    allowance = remaining(deadline)
    previous = signal.getsignal(signal.SIGALRM)

    def expired(signum, frame):
        raise SourceDeadline()

    signal.signal(signal.SIGALRM, expired)
    try:
        signal.setitimer(signal.ITIMER_REAL, allowance)
        yield
        remaining(deadline)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def pace(deadline, delay):
    if type(delay) not in (int,float) or not math.isfinite(delay) or delay<0:
        raise SourceDeadline()
    if delay >= remaining(deadline):
        raise SourceDeadline()
    with _interrupt_source(deadline):
        time.sleep(delay)


def _source_status(response):
    try:
        status = response.status_code
    except Exception:
        raise SourceUnavailable('http_error') from None
    if type(status) is not int or not 100 <= status <= 599:
        raise SourceUnavailable('http_error')
    return status


def _source_json(response, deadline):
    # Use the supported urllib3 encoded-read API, before any decoder can consume
    # arbitrarily large gzip headers or allocate a large decompressed buffer.
    try:
        raw = response.raw
        encoding = raw.headers.get('content-encoding', '')
        if type(encoding) is not str or len(encoding) > 32:
            raise ValueError
        encoding = encoding.strip().lower()
        if encoding not in ('', 'identity', 'gzip', 'deflate') or not callable(raw.read):
            raise ValueError
    except Exception:
        raise SourceUnavailable('json_error') from None

    decoder = None
    if encoding in ('gzip', 'deflate'):
        decoder = zlib.decompressobj(31 if encoding == 'gzip' else zlib.MAX_WBITS)
    body = bytearray()
    encoded_bytes = 0

    def append(decoded):
        if len(decoded) > _SOURCE_BODY_MAX_BYTES - len(body):
            raise SourceBodyLimit()
        body.extend(decoded)

    while True:
        remaining(deadline)
        chunk = raw.read(min(65536, _SOURCE_BODY_MAX_BYTES - encoded_bytes + 1),
                         decode_content=False)
        remaining(deadline)
        if type(chunk) is not bytes:
            raise SourceUnavailable('json_error')
        encoded_bytes += len(chunk)
        if encoded_bytes > _SOURCE_BODY_MAX_BYTES:
            raise SourceBodyLimit()
        if not chunk:
            break
        if decoder is None:
            append(chunk)
            continue
        pending = chunk
        while True:
            remaining(deadline)
            if decoder.eof:
                # Gzip permits concatenated members; deflate is one zlib stream.
                if encoding != 'gzip':
                    raise SourceUnavailable('json_error')
                decoder = zlib.decompressobj(31)
            limit = min(65536, _SOURCE_BODY_MAX_BYTES - len(body) + 1)
            decoded = decoder.decompress(pending, limit)
            append(decoded)
            if decoder.eof:
                pending = decoder.unused_data
                if pending:
                    continue
                break
            pending = decoder.unconsumed_tail
            # Drain bounded pending decoder output too. Never use flush(length):
            # its length is an allocation hint, not a maximum output size.
            if not pending and len(decoded) < limit:
                break
    if decoder is not None and not decoder.eof:
        raise SourceUnavailable('json_error')
    remaining(deadline)
    return json.loads(body)


def decoded_json(params, deadline, on_response):
    """Return decoded JSON without interpreting provider envelope semantics.

    Notify once at response admission, before status/body rejection; the caller
    owns safe telemetry projection. Never return/log a body or URL on failure.
    """
    response=None
    notified=False
    category='transport_error'
    completed=False
    # Reserve cleanup inside the caller's absolute allowance, never after it.
    allowance=remaining(deadline)
    operation_deadline=deadline-min(_CLEANUP_SECONDS,allowance/10)
    remaining(operation_deadline)

    def admit(observed, **kwargs):
        nonlocal response,notified,category
        response=observed
        category='http_error'
        if not notified:
            notified=True
            on_response(observed)
        status=_source_status(observed)
        # Refuse in the hook before Requests prepares a redirect (and netrc).
        if 300<=status<400:
            raise SourceUnavailable('http_error')
        return observed

    try:
        with _interrupt_source(operation_deadline):
            response=requests.get(_ENDPOINT,params=params,timeout=remaining(operation_deadline),
                stream=True,allow_redirects=False,auth=_NoSourceAuth(admit),
                headers={'Accept-Encoding':'gzip, deflate'})
            admit(response)
            response.raise_for_status()
            category='json_error'
            result=_source_json(response,operation_deadline)
            completed=True
            return result
    except SourceUnavailable:
        raise
    except (ReadTimeoutError, ProtocolError):
        raise SourceUnavailable('transport_error') from None
    except requests.RequestException as error:
        # Preserve transport/HTTP exception class without unsafe URL/body text.
        safe='http_error' if isinstance(error,requests.HTTPError) else 'transport_error'
        raise type(error)(safe) from None
    except Exception:
        raise SourceUnavailable(category) from None
    finally:
        if response is not None:
            try:
                # If scheduling consumed the reserve, do not start an unbounded
                # close. A failed cleanup never replaces the original error.
                with _interrupt_source(deadline):
                    response.close()
            except Exception:
                pass
        if completed:
            remaining(deadline)
