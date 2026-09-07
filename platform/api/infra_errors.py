"""What counts as an INFRASTRUCTURE failure, in one place.

CLAUDE.md Rule 3.7 splits every failure into two kinds, and the whole point of
the split is that they get different answers:

* **EXTERNAL** — Cloud SQL is unreachable, GCS is down, a driver cannot open a
  socket, an optional dependency is absent from this image. We cannot prevent
  it; we can name it. The caller gets an explicit **503** and can retry.
* **INTERNAL** — a `KeyError` on a row we shaped wrong, a `TypeError` from a
  response schema that drifted, an `AttributeError` from a refactor. There is
  a bug. It must **fail loudly**, as a 500, because a 503 tells an operator to
  retry something that will never succeed and hides the defect behind an
  outage that is not happening.

`except Exception -> 503` conflates them, and PR #999 shipped four handlers
that did exactly that. The 503s were added to fix real bare-500s, and each one
also swallowed every internal defect in the same call — including in the
coverage tests written alongside them, which assert 503 and would therefore
stay green through a schema regression (Codex P1 on #999).

So the guards ask this module instead. Nothing here is a fallback: an
infrastructure failure still surfaces as an explicit, renderable 503, and
everything else is re-raised untouched.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _driver_errors() -> tuple[type[BaseException], ...]:
    """The exception types a real outage raises, from whatever is installed.

    Imported defensively and once: this module is imported by routers that run
    in images built without the heavy extras, and a missing driver must not
    turn error CLASSIFICATION into an import error of its own.
    """
    found: list[type[BaseException]] = [
        # A refused or dropped socket, and a timeout waiting on one. Both are
        # OSError subclasses; OSError itself is deliberately NOT here, because
        # a `FileNotFoundError` on a path we chose is our bug.
        ConnectionError,
        TimeoutError,
        # `ImportError` is deliberately NOT here any more. Classifying every
        # one as an outage also caught a renamed symbol in `strat_pred_serve`
        # or a typo in one of our own module paths, and both prediction guards
        # wrap their lazy import -- so such a deployment answered a retryable
        # 503 indefinitely, indistinguishable from a missing optional package
        # (Codex P1 on #999). The optional-dependency case is decided by NAME
        # in `_optional_dependency_missing` instead.
    ]
    try:                                    # psycopg2, the Cloud SQL driver
        import psycopg2                     # noqa: PLC0415
        # OperationalError: cannot connect / connection lost.
        # InterfaceError: the connection object is already closed.
        # DatabaseError is NOT included: ProgrammingError and IntegrityError
        # are its subclasses and both mean our SQL is wrong.
        found += [psycopg2.OperationalError, psycopg2.InterfaceError]
    except Exception:                       # pragma: no cover - image without it
        logger.debug("psycopg2 not importable; its errors are not classified")
    # pg8000, the PRODUCTION Cloud SQL driver, is deliberately NOT registered
    # by class. `lib/agents/model_routing.py` and `gcp/database.py` both reach
    # Cloud SQL through `connector.connect(..., "pg8000")`, and the routing
    # path hands back a bare pg8000 connection with no SQLAlchemy wrapper, so
    # its failures arrive raw and often without a `__cause__` (Codex P1 on
    # #999). But each of its two classes mixes outages with defects, so both
    # are decided by PREDICATE instead: `_pg8000_transport_failure` and
    # `_pg8000_server_gone` below.
    try:                                    # the Cloud SQL connector's control plane
        import aiohttp                      # noqa: PLC0415
        # `Connector.connect()` fetches instance metadata and an ephemeral
        # certificate from the SQL Admin API over aiohttp before any socket
        # to the database is opened, and the lazy refresh both callers use
        # logs and re-raises whatever that fetch raised. A network failure
        # there is `aiohttp.ClientConnectionError` -- neither the builtin
        # `ConnectionError` nor any google.api_core class -- so a cold
        # connection or a certificate refresh during an Admin API outage was
        # a bare 500 in every guard (Codex P1 on #999). A response the
        # connector gave up on after its own 5xx retries is
        # `ClientResponseError`, decided by STATUS in
        # `_retryable_http_response`: 429 and 5xx are the service; a 4xx is
        # our credentials or configuration and stays loud.
        found += [aiohttp.ClientConnectionError]
    except Exception:                       # pragma: no cover - image without it
        logger.debug("aiohttp not importable; connector transport errors are "
                     "not classified")
    try:                                    # SQLAlchemy wraps the above
        from sqlalchemy import exc as sa_exc     # noqa: PLC0415
        # `sa_exc.TimeoutError` is the pool saying every configured connection
        # is checked out past `pool_timeout` -- a genuine capacity outage. It
        # is NOT a subclass of the builtin `TimeoutError` listed above, so the
        # guards were re-raising it as a bare 500 (Codex P2 on #999).
        found += [sa_exc.OperationalError, sa_exc.InterfaceError,
                  sa_exc.DisconnectionError, sa_exc.TimeoutError]
    except Exception:                       # pragma: no cover
        logger.debug("sqlalchemy not importable; its errors are not classified")
    try:                                    # GCS and the rest of google-cloud
        from google.api_core import exceptions as gapi  # noqa: PLC0415
        found += [gapi.ServiceUnavailable, gapi.DeadlineExceeded,
                  gapi.TooManyRequests, gapi.InternalServerError,
                  gapi.GatewayTimeout]
    except Exception:                       # pragma: no cover
        logger.debug("google.api_core not importable; not classified")
    try:
        from google.auth import exceptions as gauth     # noqa: PLC0415
        found += [gauth.DefaultCredentialsError, gauth.TransportError]
    except Exception:                       # pragma: no cover
        logger.debug("google.auth not importable; not classified")
    return tuple(found)


#: The packages this API image may legitimately lack. `requirements-research.txt`
#: is the heavy ML stack an API build can skip (`strat_pred_serve` pulls
#: lightgbm and scikit-learn, and lightgbm pulls scipy), and `firebase_admin`
#: is imported lazily behind its own 503 guard. A `ModuleNotFoundError` naming
#: one of THESE is an unavailable feature; one naming anything else -- our own
#: package, a typo -- is a bug and stays loud.
OPTIONAL_DEPENDENCIES: frozenset[str] = frozenset(
    {"lightgbm", "sklearn", "scipy", "firebase_admin"})


def _optional_dependency_missing(exc: BaseException) -> bool:
    """A `ModuleNotFoundError` for a package this image is allowed not to have.

    Matched on the top-level package of `exc.name`, which the interpreter sets
    on every module-not-found it raises. `ImportError` for a symbol that does
    not exist (`cannot import name ...`) is a plain `ImportError`, not a
    `ModuleNotFoundError`, and is never an outage.
    """
    if not isinstance(exc, ModuleNotFoundError) or not exc.name:
        return False
    return exc.name.split(".")[0] in OPTIONAL_DEPENDENCIES


try:                                        # pragma: no cover - image without it
    import pg8000.exceptions as _pg8000_exc
except Exception:                           # pragma: no cover
    _pg8000_exc = None
try:                                        # pragma: no cover - image without it
    import aiohttp as _aiohttp
except Exception:                           # pragma: no cover
    _aiohttp = None

#: pg8000 raises `InterfaceError` for two unrelated things. The socket failing
#: or the connection already being gone -- these three messages, verbatim from
#: `pg8000.core` at 1.31.5 -- is an outage. Everything else it raises under the
#: same class is the application misusing the driver: "Cursor closed", an
#: identifier of the wrong type, a parameter it cannot encode, "Server refuses
#: SSL". Registering the whole class read a lifecycle or argument regression
#: inside one of the guarded helpers as a retryable 503 (Codex P1 on #999).
_PG8000_TRANSPORT_MESSAGES: frozenset[str] = frozenset(
    {"network error", "communication error", "connection is closed"})


def _pg8000_transport_failure(exc: BaseException) -> bool:
    """A pg8000 `InterfaceError` that means the transport, not the caller."""
    if _pg8000_exc is None or not isinstance(exc, _pg8000_exc.InterfaceError):
        return False
    return bool(exc.args) and exc.args[0] in _PG8000_TRANSPORT_MESSAGES


#: PostgreSQL SQLSTATEs that mean the SERVER went away, not that our SQL is
#: wrong. Class 08 is "connection exception". 57P01, 57P02 and 57P03 are what
#: a Cloud SQL restart or failover sends every open session -- administrator
#: shutdown, crash shutdown, cannot connect now. 53300 is too_many_connections,
#: a capacity outage of the same kind as the pool's `TimeoutError` above.
_SERVER_GONE_SQLSTATES: frozenset[str] = frozenset(
    {"57P01", "57P02", "57P03", "53300"})


def _pg8000_server_gone(exc: BaseException) -> bool:
    """A pg8000 `DatabaseError` carrying a connection or shutdown SQLSTATE.

    pg8000 delivers every PostgreSQL error response as `DatabaseError`, with
    the protocol fields in a dict and the SQLSTATE under `C` -- so a
    failover's `57P01` and a syntax error's `42601` are the same class and
    differ only in that payload (Codex P1 on #999). Reading the code keeps the
    class out, as before, and lets the outage in. SQLAlchemy wraps the same
    response as `sqlalchemy.exc.DatabaseError` raised FROM the driver's, which
    the `__cause__` walk reaches.
    """
    if _pg8000_exc is None or not isinstance(exc, _pg8000_exc.DatabaseError):
        return False
    payload = exc.args[0] if exc.args else None
    if not isinstance(payload, dict):
        return False
    code = payload.get("C")
    return isinstance(code, str) and (
        code.startswith("08") or code in _SERVER_GONE_SQLSTATES)


def _retryable_http_response(exc: BaseException) -> bool:
    """The SQL Admin API answered the connector 429 or 5xx after its retries."""
    if _aiohttp is None or not isinstance(exc, _aiohttp.ClientResponseError):
        return False
    return exc.status == 429 or exc.status >= 500


#: What cannot be decided by class alone. Each reads the one exception it is
#: about and answers False for everything else.
_INFRASTRUCTURE_PREDICATES = (_optional_dependency_missing,
                              _pg8000_transport_failure,
                              _pg8000_server_gone,
                              _retryable_http_response)

#: Evaluated once at import. The set of installed drivers does not change
#: while the process runs, and rebuilding it per request would put a dozen
#: imports on every error path.
INFRASTRUCTURE_ERRORS: tuple[type[BaseException], ...] = _driver_errors()


def is_infrastructure_error(exc: BaseException) -> bool:
    """Is this an outage we should report as 503, rather than a bug?

    The `__cause__` chain is followed, because a driver error is routinely
    re-raised inside a helper's own wrapper (`raise RuntimeError(...) from
    exc`) and the outage is no less real for having been wrapped. The chain is
    walked with a seen-set rather than a depth cap, the same way the guard
    file's resolvers do, because a chain has no natural length and what it
    cannot do is revisit an exception.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if (isinstance(cur, INFRASTRUCTURE_ERRORS)
                or any(decide(cur) for decide in _INFRASTRUCTURE_PREDICATES)):
            return True
        cur = cur.__cause__
    return False
