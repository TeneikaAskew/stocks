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

It lives in `lib` rather than beside the routers because the library's own
read helpers consult it too: a per-source UNAVAILABLE envelope is the right
answer to a corrupt artifact and the wrong answer to Cloud SQL being down,
and only this module can tell the two apart (Codex P1 on #999). See
`is_backend_outage`.
"""

from __future__ import annotations

import errno
import http.client
import logging
import socket
import ssl

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
        # a `FileNotFoundError` on a path we chose is our bug. The network
        # being GONE -- unreachable, down, unresolvable -- is a plain OSError
        # too, and is decided by errno in `_network_unreachable` below.
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
    # psycopg2, the direct-DSN driver, is NOT registered by class either.
    # `OperationalError` is the base of every server error in SQLSTATE classes
    # 08, 28, 53, 57 and 58 alike, so registering it read `InvalidPassword`
    # (28P01) -- a permanently wrong credential -- as a retryable outage
    # (Codex P2 on #999). `_psycopg2_operational_outage` decides it by
    # SQLSTATE; a code-less `OperationalError` is the driver's own connection
    # failure. `InterfaceError` is decided by message in
    # `_psycopg2_transport_failure`: psycopg2 raises it for a closed
    # connection AND for "cursor already closed", a range or hstore value it
    # cannot parse, and every "cannot be used while ..." misuse of the API
    # (Codex P1 on #999). `DatabaseError` is out: ProgrammingError and
    # IntegrityError are its subclasses and both mean our SQL is wrong.
    # pg8000, the PRODUCTION Cloud SQL driver, is deliberately NOT registered
    # by class. `lib/agents/model_routing.py` and `gcp/database.py` both reach
    # Cloud SQL through `connector.connect(..., "pg8000")`, and the routing
    # path hands back a bare pg8000 connection with no SQLAlchemy wrapper, so
    # its failures arrive raw and often without a `__cause__` (Codex P1 on
    # #999). But each of its two classes mixes outages with defects, so both
    # are decided by PREDICATE instead: `_pg8000_transport_failure` and
    # `_pg8000_server_gone` below.
    # The Cloud SQL connector's control plane is decided by predicate too:
    # `_connector_transport_failure` and `_retryable_http_response` below.
    try:                                    # SQLAlchemy wraps the above
        from sqlalchemy import exc as sa_exc     # noqa: PLC0415
        # `sa_exc.TimeoutError` is the pool saying every configured connection
        # is checked out past `pool_timeout` -- a genuine capacity outage. It
        # is NOT a subclass of the builtin `TimeoutError` listed above, so the
        # guards were re-raising it as a bare 500 (Codex P2 on #999).
        # `DisconnectionError` is SQLAlchemy's own, raised by pre-ping when the
        # pooled connection is found dead. Both are SQLAlchemy's OWN
        # exceptions, which is why they are the only ones registered.
        #
        # `sa_exc.InterfaceError` and `sa_exc.OperationalError` are
        # deliberately NOT here. SQLAlchemy raises its wrapper FROM the
        # driver's exception and keeps it as `.orig`, and the wrapper's class
        # only echoes the driver's class name -- so registering them accepted
        # pg8000's `InterfaceError("Cursor closed")` and psycopg2's
        # `InvalidPassword` wholesale, straight past the driver rules below
        # (Codex P1 and P2 on #999). A wrapper is decided by what it wraps:
        # `is_infrastructure_error` walks `.orig` as well as `__cause__`, and
        # the driver rules apply to what it finds there.
        found += [sa_exc.DisconnectionError, sa_exc.TimeoutError]
    except Exception:                       # pragma: no cover
        logger.debug("sqlalchemy not importable; its errors are not classified")
    try:                                    # GCS and the rest of google-cloud
        from google.api_core import exceptions as gapi  # noqa: PLC0415
        found += [gapi.ServiceUnavailable, gapi.DeadlineExceeded,
                  gapi.TooManyRequests, gapi.InternalServerError,
                  # BadGateway (502) is a sibling of the 500/503/504 classes,
                  # not a subclass, so it was not covered -- a transient GCS
                  # 502 while loading a model still swallowed to None and
                  # answered 200 (Codex P1 on #999).
                  gapi.BadGateway, gapi.GatewayTimeout]
    except Exception:                       # pragma: no cover
        logger.debug("google.api_core not importable; not classified")
    try:
        from google.auth import exceptions as gauth     # noqa: PLC0415
        # `DefaultCredentialsError` (no credentials at all) is always
        # infrastructure. `TransportError` is NOT registered wholesale:
        # `google.auth.transport.requests.Request` wraps EVERY
        # `requests.exceptions.RequestException` in it, including a
        # certificate-verification `SSLError`, and a bad CA chain during the
        # connector's credential refresh must stay loud like the raw ssl and
        # aiohttp certificate cases (Codex P2 on #999). `_auth_transport_outage`
        # reads its cause.
        found += [gauth.DefaultCredentialsError]
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

    Matched on the EXACT `exc.name`, which the interpreter sets to the module
    it could not find. An absent package gives the package name, `lightgbm`,
    even from `import lightgbm.sklearn`; a package that IS installed with a
    submodule that is not gives `sklearn.nonexistent`. Matching the top-level
    segment read the second -- a typo, a stale reference after a refactor --
    as an unavailable feature and answered a retryable 503 for it
    indefinitely (Codex P1 on #999; verified: `import sklearn.nonexistent_zzz`
    raises with `name='sklearn.nonexistent_zzz'`). `ImportError` for a symbol
    that does not exist (`cannot import name ...`) is a plain `ImportError`,
    not a `ModuleNotFoundError`, and is never an outage.
    """
    if not isinstance(exc, ModuleNotFoundError) or not exc.name:
        return False
    return exc.name in OPTIONAL_DEPENDENCIES


#: The errnos of a socket that could not be opened because the NETWORK is
#: gone, as distinct from refused or reset (already `ConnectionError`
#: subclasses) and timed out (`TimeoutError`). The Cloud SQL connector opens
#: its data-plane socket with `socket.create_connection` before handing it to
#: pg8000, so a VPC or routing outage surfaces as a plain `OSError` carrying
#: one of these, and a DNS failure as `socket.gaierror` -- neither a
#: `ConnectionError` (Codex P1 on #999). And the socket that could not be
#: ALLOCATED: EMFILE and ENFILE (the process's or the host's descriptors are
#: exhausted) and ENOBUFS (no socket buffers) are capacity outages of the
#: same kind as too_many_connections (Codex P2 on #999). `OSError` itself
#: stays out: a `FileNotFoundError` on a path we chose is our bug.
_NETWORK_ERRNOS: frozenset[int] = frozenset(
    {errno.ENETUNREACH, errno.EHOSTUNREACH, errno.ENETDOWN, errno.ENETRESET,
     errno.EHOSTDOWN, errno.EMFILE, errno.ENFILE, errno.ENOBUFS,
     # EADDRNOTAVAIL: the local ephemeral-port range is exhausted, so
     # `socket.create_connection` cannot bind a source port -- a capacity
     # outage, and the one the libpq text classifier already reads as
     # "Cannot assign requested address" (Codex P2 on #999).
     errno.EADDRNOTAVAIL})


def _network_unreachable(exc: BaseException) -> bool:
    """A socket that failed because the network, the name, or the descriptors are gone."""
    if isinstance(exc, (socket.gaierror, socket.herror)):
        return True
    return isinstance(exc, OSError) and exc.errno in _NETWORK_ERRNOS


try:                                        # pragma: no cover - image without it
    import psycopg2 as _psycopg2
except Exception:                           # pragma: no cover
    _psycopg2 = None
try:                                        # pragma: no cover - image without it
    import pg8000.exceptions as _pg8000_exc
except Exception:                           # pragma: no cover
    _pg8000_exc = None
try:                                        # pragma: no cover - image without it
    import aiohttp as _aiohttp
except Exception:                           # pragma: no cover
    _aiohttp = None
try:                                        # pragma: no cover - image without it
    from google.auth import exceptions as _gauth_exc
except Exception:                           # pragma: no cover
    _gauth_exc = None
try:                                        # pragma: no cover - image without it
    from requests import exceptions as _requests_exc
except Exception:                           # pragma: no cover
    _requests_exc = None
try:                                        # pragma: no cover - image without it
    from urllib3 import exceptions as _urllib3_exc
except Exception:                           # pragma: no cover
    _urllib3_exc = None
try:                                        # pragma: no cover - image without it
    from google.api_core import exceptions as _gapi_exc
except Exception:                           # pragma: no cover
    _gapi_exc = None


def _connector_transport_failure(exc: BaseException) -> bool:
    """The Cloud SQL connector could not reach the SQL Admin API.

    `Connector.connect()` fetches instance metadata and an ephemeral
    certificate from the SQL Admin API over aiohttp before any socket to the
    database is opened, and the lazy refresh both callers use logs and
    re-raises whatever that fetch raised. A network failure there is
    `aiohttp.ClientConnectionError` -- neither the builtin `ConnectionError`
    nor any google.api_core class -- so a cold connection or a certificate
    refresh during an Admin API outage was a bare 500 in every guard
    (Codex P1 on #999). EXCEPT a certificate the endpoint presented that did
    not verify: `ClientConnectorCertificateError` is a bad trust chain, a
    hostname mismatch or an intercepted endpoint, none of which a retry
    resolves, and it stays loud (Codex P2 on #999).
    """
    if _aiohttp is None or not isinstance(exc, _aiohttp.ClientConnectionError):
        return False
    return not isinstance(exc, _aiohttp.ClientConnectorCertificateError)

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


#: psycopg2's `InterfaceError` has the same two faces. These two messages,
#: verbatim from the C extension (2.9.12), are the connection being gone;
#: "cursor already closed", "failed to parse range", "can't parse type", the
#: hstore parser and the "cannot be used while ..." family are the caller's
#: (Codex P1 on #999).
_PSYCOPG2_TRANSPORT_MESSAGES: frozenset[str] = frozenset(
    {"connection already closed", "asynchronous connection failed"})


def _psycopg2_transport_failure(exc: BaseException) -> bool:
    """A psycopg2 `InterfaceError` that means the connection, not the caller."""
    if _psycopg2 is None or not isinstance(exc, _psycopg2.InterfaceError):
        return False
    return bool(exc.args) and exc.args[0] in _PSYCOPG2_TRANSPORT_MESSAGES


def _psycopg2_sqlstates() -> dict:
    """`{exception class: SQLSTATE}` for every server error psycopg2 names.

    psycopg2 raises a class per SQLSTATE (`InvalidPassword` for 28P01,
    `AdminShutdown` for 57P01) and sets `pgcode` from the server's response,
    but an instance built by hand carries no `pgcode` and the classes do not
    record their code. `psycopg2.errorcodes` names every code and
    `psycopg2.errors.lookup` maps a code to its class, so the map is derived
    from the driver rather than copied from it.
    """
    if _psycopg2 is None:
        return {}
    import psycopg2.errorcodes as codes        # noqa: PLC0415
    import psycopg2.errors as errors           # noqa: PLC0415
    out: dict = {}
    for name, code in vars(codes).items():
        if not (name.isupper() and isinstance(code, str) and len(code) == 5):
            continue
        try:
            out.setdefault(errors.lookup(code), code)
        except KeyError:
            continue
    return out


_PSYCOPG2_SQLSTATE_OF: dict = _psycopg2_sqlstates()

#: How libpq 14+ reports each failed connection ATTEMPT, one line per
#: address it tried, verbatim from fe-connect.c (`emitHostIdentifier`);
#: older releases spelled it `could not connect to server: `. What follows
#: the wrapper is the failure itself, and that is where an outage and a
#: broken deployment part ways. Captured live through psycopg2 2.9.12 /
#: libpq 17 against Postgres 16, all under this one wrapper and all with
#: `pgcode` None: `Connection refused` and `FATAL:  too many connections
#: for role "app"` are outages; `fe_sendauth: no password supplied`,
#: `FATAL:  password authentication failed for user "x"`, `FATAL:
#: database "x" does not exist` and `server does not support SSL, but SSL
#: was required` are deployments -- and the first is exactly what
#: `model_routing.connect()` raises with `DB_PASS` unset, so matching the
#: wrapper alone answered a retryable 503 for a missing secret
#: indefinitely (Codex P2 on #999).
_LIBPQ_ATTEMPT_WRAPPERS: tuple[str, ...] = (
    "connection to server at ",         # TCP: `at "host" (ip), port N failed: `
    "connection to server on socket ",  # Unix socket: `on socket "path" failed: `
    "could not connect to server: ",    # libpq < 14
)

#: The failures libpq itself reports -- inside an attempt wrapper or, once
#: connected, bare -- that are outages: the operating system's socket
#: errors as libpq renders `strerror()` (glibc and BSD spellings), the
#: resource exhaustion `_NETWORK_ERRNOS` already accepts, and libpq 17's
#: own transport messages: `timeout expired` and `server closed the
#: connection unexpectedly` (fe-misc.c), `could not receive/send data`
#: (fe-secure.c), the two SSL texts (fe-secure-openssl.c) and the DNS one
#: (fe-connect.c), which classifies here as `socket.gaierror` does in
#: `_network_unreachable`. Not here: `No such file or directory` on a
#: socket path, which is either the proxy not running or the wrong path
#: and the text cannot say which; `server does not support SSL, but SSL
#: was required`, `received invalid response to SSL negotiation` and
#: `expected authentication request from server`, which are talking to the
#: wrong endpoint; `SSL error: certificate verify failed`, which
#: `_tls_transport_failure` keeps loud for the same reason; and every
#: `fe_sendauth:` line, which is the client failing to authenticate.
_LIBPQ_TRANSPORT_FAILURES: tuple[str, ...] = (
    "Connection refused",
    "Connection timed out",
    "Operation timed out",
    "Connection reset by peer",
    "Software caused connection abort",
    "Broken pipe",
    "No route to host",
    "Network is unreachable",
    "Network is down",
    "Host is down",
    "Too many open files",
    "No buffer space available",
    "Cannot assign requested address",
    "timeout expired",
    "could not translate host name",
    "server closed the connection unexpectedly",
    "could not receive data from server",
    "could not send data to server",
    "SSL SYSCALL error",
    "SSL connection has been closed unexpectedly",
)

#: A server FATAL libpq relays inside a failed attempt as `FATAL:  <text>`,
#: without the SQLSTATE the server sent because a failed connect carries
#: none across to the driver. These are the texts PostgreSQL 17 raises
#: under the codes `_server_gone` accepts and no others: 57P03
#: cannot_connect_now (backend_startup.c), 53300 too_many_connections
#: (postinit.c, miscinit.c, proc.c), 53200 out_of_memory (mcxt.c), 57P01
#: admin_shutdown, 57P02 crash_shutdown and 57P05 idle_session_timeout
#: (postgres.c). `password authentication failed`, `no pg_hba.conf entry`
#: and `role "x" does not exist` (class 28) and `database "x" does not
#: exist` (3D000) are not among them, so they stay loud here exactly as
#: they do when the SQLSTATE arrives.
_LIBPQ_SERVER_GONE_FATALS: tuple[str, ...] = (
    "the database system is starting up",
    "the database system is not yet accepting connections",
    "the database system is not accepting connections",
    "the database system is shutting down",
    "the database system is in recovery mode",
    "sorry, too many clients already",
    "remaining connection slots are reserved",
    "too many connections for role",
    "too many connections for database",
    "number of requested standby connections exceeds",
    "out of memory",
    "terminating connection due to administrator command",
    "terminating connection due to immediate shutdown command",
    "terminating connection because of unexpected SIGQUIT signal",
    "terminating connection because of crash of another server process",
    "terminating connection due to idle-session timeout",
)


def _libpq_failure_is_outage(failure: str) -> bool:
    """One libpq failure text, any attempt wrapper already removed."""
    if failure.startswith("FATAL:"):
        return failure[len("FATAL:"):].lstrip().startswith(_LIBPQ_SERVER_GONE_FATALS)
    return failure.startswith(_LIBPQ_TRANSPORT_FAILURES)


def _libpq_reports_outage(message: str) -> bool:
    """Read a code-less libpq message: is every failure it names an outage?

    A host with several addresses yields one wrapped attempt per address,
    each followed by an indented hint line; a message with no wrapper is
    the driver reporting a transport failure on an open connection. Every
    attempt must be an outage: an address that answered and refused the
    credential is not retried away by the one before it being unreachable.
    A message that names no failure at all is not an outage either.
    """
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return False
    attempts = [line for line in lines if line.startswith(_LIBPQ_ATTEMPT_WRAPPERS)]
    if not attempts:
        return _libpq_failure_is_outage(lines[0])
    outcomes = []
    for line in attempts:
        marker = " failed: " if line.startswith("connection to server") else ": "
        _wrapper, found, failure = line.partition(marker)
        outcomes.append(bool(found) and _libpq_failure_is_outage(failure))
    return all(outcomes)


def _psycopg2_server_gone(exc: BaseException) -> bool:
    """A psycopg2 server error whose SQLSTATE says the server is gone.

    `OperationalError` is the DB-API base of every server error in SQLSTATE
    classes 08, 28, 53, 57 and 58 alike, so registering it read
    `InvalidPassword` (28P01) -- a permanently wrong credential -- as a
    retryable outage (Codex P2 on #999). And the server's own failures, class
    XX, arrive under `InternalError` rather than `OperationalError`, so a
    predicate gated on the latter never consulted their code and answered a
    bare 500 for `XX000` where the pg8000 path answered 503 (Codex P2 on
    #999). So every `DatabaseError` subclass is decided by SQLSTATE, from
    `pgcode` when the server set it and from the class otherwise, through the
    same code sets pg8000 uses. A code-less plain `OperationalError` is the
    driver's own report, and libpq wraps a refused port, a missing password
    and a wrong one identically (Codex P2 on #999, twice), so the failure it
    names decides through `_libpq_reports_outage`; a connection OPTION libpq
    could not read names no failure and stays loud, as does any other
    code-less error.
    """
    if _psycopg2 is None or not isinstance(exc, _psycopg2.DatabaseError):
        return False
    code = getattr(exc, "pgcode", None) or _PSYCOPG2_SQLSTATE_OF.get(type(exc))
    if code is None:
        # The driver's own, with no SQLSTATE behind it: the failure libpq
        # names decides, and only a named outage counts.
        return (type(exc) is _psycopg2.OperationalError
                and _libpq_reports_outage(str(exc)))
    return _server_gone(code)


def _tls_transport_failure(exc: BaseException) -> bool:
    """The TLS handshake or record layer failed: an `ssl.SSLError`.

    The Cloud SQL connector wraps its data-plane socket with
    `SSLContext.wrap_socket` before pg8000 sees it, and a proxy restart or a
    certificate rotation aborts that handshake with a raw `ssl.SSLError` --
    an `OSError` whose errno is the SSL library's, so neither the
    `ConnectionError` classes nor `_NETWORK_ERRNOS` saw it (Codex P1 on
    #999). No filesystem error is an `SSLError`, so the class is TLS and
    nothing else -- EXCEPT `SSLCertVerificationError`, which is the endpoint
    presenting a certificate we do not trust: a bad trust chain, a hostname
    mismatch or an intercepted endpoint, none of which a retry resolves. I
    first classified it as an outage on the strength of certificate rotation;
    that was wrong, because the connector fetches the instance's own CA with
    every refresh and verifies against it, so a verification failure that
    persists is a configuration or a security failure and stays loud
    (Codex P2 on #999).
    """
    return (isinstance(exc, ssl.SSLError)
            and not isinstance(exc, ssl.SSLCertVerificationError))


#: PostgreSQL SQLSTATEs that mean the SERVER is gone or exhausted, not that
#: our SQL is wrong, shared by both drivers. Class 08 is "connection
#: exception"; 53 is "insufficient resources" (disk full, out of memory, too
#: many connections -- capacity outages of the same kind as the pool's
#: `TimeoutError`); 58 is "system error" (I/O); XX is "internal error", the
#: server's own. Class 57, "operator intervention", is taken by code rather
#: than as a class: 57P01, 57P02 and 57P03 are what a Cloud SQL restart or
#: failover sends every open session -- administrator shutdown, crash
#: shutdown, cannot connect now; 57P04 is database_dropped and 57P05 is
#: idle_session_timeout, both of which the server sends as it terminates the
#: session (Codex P2 on #999); 57014 is query_canceled, a statement timeout
#: on a query of OURS, and 57000 is the bare class code, and neither is an
#: outage. Class 28 (a bad credential), 3D (no such database), F0 (the
#: server's config file) and 55 (an object in the wrong state) are permanent
#: and stay loud.
_SERVER_GONE_SQLSTATE_CLASSES: frozenset[str] = frozenset({"08", "53", "58", "XX"})
_SERVER_GONE_SQLSTATES: frozenset[str] = frozenset(
    {"57P01", "57P02", "57P03", "57P04", "57P05"})


def _server_gone(sqlstate) -> bool:
    return (isinstance(sqlstate, str) and len(sqlstate) == 5
            and (sqlstate[:2] in _SERVER_GONE_SQLSTATE_CLASSES
                 or sqlstate in _SERVER_GONE_SQLSTATES))


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
    return _server_gone(payload.get("C"))


def _retryable_http_response(exc: BaseException) -> bool:
    """The SQL Admin API answered the connector 429 or 5xx after its retries."""
    if _aiohttp is None or not isinstance(exc, _aiohttp.ClientResponseError):
        return False
    return exc.status == 429 or exc.status >= 500


#: What cannot be decided by class alone. Each reads the one exception it is
#: about and answers False for everything else.
#: How OpenSSL and requests spell a certificate-verification failure in the
#: text of the exception google-auth wraps.
_CERT_FAILURE_TEXT = ("certificate verify failed", "certificate_verify_failed",
                      "self-signed certificate", "self signed certificate",
                      "unable to get local issuer certificate",
                      "hostname mismatch", "certificate is not valid")


def _is_certificate_failure(exc: BaseException) -> bool:
    """A TLS certificate-verification failure, however it is wrapped."""
    if isinstance(exc, ssl.SSLCertVerificationError):
        return True
    return any(t in str(exc).lower() for t in _CERT_FAILURE_TEXT)


def _auth_transport_outage(exc: BaseException) -> bool:
    """google-auth's `TransportError`, unless it wraps a certificate failure.

    `google.auth.transport.requests.Request` catches every
    `requests.exceptions.RequestException` -- a reset connection AND a
    certificate-verification `SSLError` alike -- and re-raises it as a
    `TransportError`. Registering the class wholesale answered a retryable
    503 for a bad CA chain, even though the raw `ssl` and aiohttp certificate
    failures are deliberately kept loud (Codex P2 on #999). So a transport
    error is an outage unless its own message or its cause chain names a
    certificate-verification failure.
    """
    if _gauth_exc is None or not isinstance(exc, _gauth_exc.TransportError):
        return False
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if _is_certificate_failure(cur):
            return False
        cur = cur.__cause__ or cur.__context__
    return True


def _storage_transport_types() -> tuple[type[BaseException], ...]:
    """The requests / urllib3 / http.client transport wrappers that
    google-cloud-storage's DEFAULT_RETRY treats as retryable
    (`google.cloud.storage.retry._RETRYABLE_TYPES`), minus the ones already
    classified elsewhere: the builtin `ConnectionError` and the google.api_core
    5xx classes. Built defensively so an image without `requests` still
    classifies the `http.client` protocol errors.
    """
    types: list[type[BaseException]] = [
        http.client.BadStatusLine, http.client.IncompleteRead,
        http.client.ResponseNotReady,
    ]
    if _requests_exc is not None:
        types += [_requests_exc.ConnectionError,
                  _requests_exc.ChunkedEncodingError, _requests_exc.Timeout]
    if _urllib3_exc is not None:
        types += [_urllib3_exc.PoolError, _urllib3_exc.ProtocolError,
                  _urllib3_exc.SSLError, _urllib3_exc.TimeoutError]
    return tuple(types)


#: Evaluated once at import, like the driver tuple: the installed HTTP stack
#: does not change while the process runs.
_STORAGE_TRANSPORT_TYPES = _storage_transport_types()


def _storage_transport_outage(exc: BaseException) -> bool:
    """A GCS request-layer transport failure google-cloud-storage would have
    retried, unless it is a certificate-verification failure.

    `google.cloud.storage.retry._RETRYABLE_TYPES` treats
    `requests.exceptions.ConnectionError` / `ChunkedEncodingError` / `Timeout`,
    the `http.client` protocol errors, and urllib3's `PoolError` /
    `ProtocolError` / `SSLError` / `TimeoutError` as retryable. When
    `blob.exists()` or `download_as_bytes()` exhausts DEFAULT_RETRY after a
    reset, read timeout, or truncated response it raises one of these, and none
    subclasses the builtin `ConnectionError`, the google.api_core 5xx classes,
    or google-auth's `TransportError` -- so a real storage outage swallowed to
    None and answered 200 instead of 503 (Codex P1 on #999). A
    certificate-verification failure stays loud like the raw ssl, aiohttp, and
    auth-transport cases: `requests`/`urllib3` `SSLError` is in the retryable
    set, but a bad trust chain is a deployment fault, not an outage.
    """
    if not isinstance(exc, _STORAGE_TRANSPORT_TYPES):
        return False
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if _is_certificate_failure(cur):
            return False
        cur = cur.__cause__ or cur.__context__
    return True


def _storage_response_types() -> tuple[type[BaseException], ...]:
    """google-cloud-storage's `InvalidResponse` and the `google.resumable_media`
    base it subclasses. Imported defensively: a router image without the
    storage extra still classifies the generic API errors.
    """
    types: list[type[BaseException]] = []
    for mod, name in (("google.cloud.storage.exceptions", "InvalidResponse"),
                      ("google.resumable_media", "InvalidResponse")):
        try:                                    # pragma: no cover - image without it
            module = __import__(mod, fromlist=[name])
            types.append(getattr(module, name))
        except Exception:                       # pragma: no cover
            pass
    return tuple(types)


_STORAGE_RESPONSE_TYPES = _storage_response_types()

#: The HTTP statuses google-cloud-storage's DEFAULT_RETRY retries
#: (`google.cloud.storage.retry._RETRYABLE_STATUS_CODES`). 429/500/502/503/504
#: already arrive as their own registered `google.api_core` classes, but 408
#: has no dedicated class -- it is a bare `GoogleAPICallError` with `code == 408`
#: -- so the whole set is matched by CODE here to close it, and to cover a
#: response that reaches us as a storage `InvalidResponse` rather than a raised
#: API class.
_RETRYABLE_STORAGE_STATUS: frozenset[int] = frozenset(
    {408, 429, 500, 502, 503, 504})


def _retryable_storage_status(exc: BaseException) -> bool:
    """A GCS response carrying a retryable HTTP status that exhausted retries.

    `_should_retry` in `google.cloud.storage.retry` retries a
    `GoogleAPICallError` (or a storage `InvalidResponse`) whose status is in
    `_RETRYABLE_STATUS_CODES` = {408, 429, 500, 502, 503, 504}. HTTP 408 alone
    has no dedicated `google.api_core` class, so it arrived as a bare
    `GoogleAPICallError` and fell through the registered-class checks, and when
    retries expired `_gcs_load_bytes` swallowed the outage to None and answered
    200 (Codex P1 on #999). 404/403/400 stay loud: a missing artifact or a
    denied/ malformed request is not a retryable outage.
    """
    if _gapi_exc is not None and isinstance(exc, _gapi_exc.GoogleAPICallError):
        if getattr(exc, "code", None) in _RETRYABLE_STORAGE_STATUS:
            return True
    if _STORAGE_RESPONSE_TYPES and isinstance(exc, _STORAGE_RESPONSE_TYPES):
        response = getattr(exc, "response", None)
        return getattr(response, "status_code", None) in _RETRYABLE_STORAGE_STATUS
    return False


def _retryable_auth_refresh(exc: BaseException) -> bool:
    """google-auth's `RefreshError`, when google-auth itself marked it retryable.

    The Cloud SQL connector refreshes ADC credentials before it opens a
    connection, and when the OAuth token endpoint keeps answering 5xx (or
    `server_error` / `temporarily_unavailable`) through google-auth's own
    retries, the library raises `RefreshError(..., retryable=True)`
    (`google.oauth2._client._handle_error_response`, decided by
    `_can_retry`). That is a control-plane outage, and the class subclasses
    neither `TransportError` nor `DefaultCredentialsError`, so it fell
    through the registrations above as a bare 500 (Codex P1 on #999). A
    `RefreshError` google-auth did NOT mark retryable -- `invalid_grant`, a
    revoked or malformed credential -- is a deployment problem and stays
    loud, as does one built without the flag at all.
    """
    return (_gauth_exc is not None and isinstance(exc, _gauth_exc.RefreshError)
            and bool(getattr(exc, "retryable", False)))


_INFRASTRUCTURE_PREDICATES = (_optional_dependency_missing,
                              _network_unreachable,
                              _tls_transport_failure,
                              _pg8000_transport_failure,
                              _pg8000_server_gone,
                              _psycopg2_transport_failure,
                              _psycopg2_server_gone,
                              _connector_transport_failure,
                              _retryable_http_response,
                              _auth_transport_outage,
                              _storage_transport_outage,
                              _retryable_storage_status,
                              _retryable_auth_refresh)

#: The same rules minus "a feature this image cannot serve": what a library
#: read helper re-raises rather than folding into a per-source envelope.
_OUTAGE_PREDICATES = tuple(p for p in _INFRASTRUCTURE_PREDICATES
                           if p is not _optional_dependency_missing)

#: Evaluated once at import. The set of installed drivers does not change
#: while the process runs, and rebuilding it per request would put a dozen
#: imports on every error path.
INFRASTRUCTURE_ERRORS: tuple[type[BaseException], ...] = _driver_errors()


def is_infrastructure_error(exc: BaseException) -> bool:
    """Is this an outage we should report as 503, rather than a bug?

    The `__cause__` chain is followed, because a driver error is routinely
    re-raised inside a helper's own wrapper (`raise RuntimeError(...) from
    exc`) and the outage is no less real for having been wrapped. So is
    `.orig`, where SQLAlchemy's `DBAPIError` keeps the driver's exception,
    because the wrapper's class says only which driver class was wrapped and
    the driver rules above need the exception itself (Codex P1 on #999). The
    walk keeps a seen-set rather than a depth cap, the same way the guard
    file's resolvers do, because a chain has no natural length and what it
    cannot do is revisit an exception.
    """
    return _classified(exc, _INFRASTRUCTURE_PREDICATES)


def is_backend_outage(exc: BaseException) -> bool:
    """`is_infrastructure_error`, minus an optional dependency this image lacks.

    For a library read helper deciding whether a failure is ITS source's --
    fold it into that source's UNAVAILABLE envelope -- or the backend's --
    re-raise it, so the route answers 503 for the whole call. A missing
    research package is an unavailable feature, not an outage: the block
    that needs it stays an envelope and the rest of the statement still
    assembles (Codex P1 on #999).
    """
    return _classified(exc, _OUTAGE_PREDICATES)


def _classified(exc: BaseException, predicates) -> bool:
    seen: set[int] = set()
    pending: list[BaseException] = [exc]
    while pending:
        cur = pending.pop()
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        if (isinstance(cur, INFRASTRUCTURE_ERRORS)
                or any(decide(cur) for decide in predicates)):
            return True
        for nxt in (cur.__cause__, getattr(cur, "orig", None)):
            if isinstance(nxt, BaseException):
                pending.append(nxt)
    return False
