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
        # An optional dependency absent from this image. `strat_pred_serve`
        # pulls lightgbm and scikit-learn, so an API image built without the ML
        # extras raises this before any model runs -- an unavailable predict
        # stack, not a crash.
        ImportError,
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
    try:                                    # SQLAlchemy wraps the above
        from sqlalchemy import exc as sa_exc     # noqa: PLC0415
        found += [sa_exc.OperationalError, sa_exc.InterfaceError,
                  sa_exc.DisconnectionError]
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
        if isinstance(cur, INFRASTRUCTURE_ERRORS):
            return True
        cur = cur.__cause__
    return False
