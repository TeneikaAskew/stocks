"""Which HTTP status a failed request actually deserves.

CLAUDE.md Rule 3.7 splits every failure in two, and the split decides the
status code. Cloud SQL unreachable is EXTERNAL: the caller gets an explicit,
retryable 503. A `KeyError` on a row we shaped wrong is a defect: it must stay
a loud 500, because a 503 tells an operator to retry code that will never
succeed and hides the bug behind an outage that is not happening.

`except Exception: raise HTTPException(503)` conflates them. It reads as
fail-loud — it replaced a swallow, after all — but it is a smaller swallow
wearing the same clothes, and the tests written alongside such a handler
assert 503 and therefore stay green through the regression they were meant to
catch (measured on this repo twice: PR #999's four handlers, and the signals
router on #1022).

`lib.infra_errors` already knows how to tell the two apart, and the freshness
handler already asks it. This is the same question in the shape a router
wants: one guard line at the top of an `except` block, after which the
existing 503 (and any local-dev fallback beneath it) applies only to a real
outage.

    except Exception as exc:
        raise_unless_infrastructure(exc)     # a defect is never a fallback
        raise HTTPException(status_code=503, detail="… temporarily unavailable")

It lives beside `threadsafe_cache` and `gcs_reader` rather than in `lib/`
because it raises `fastapi.HTTPException`, and `lib/` is imported by the CLI
scripts and the agents too, which have no HTTP layer.
"""
from __future__ import annotations

from typing import NoReturn


def raise_unless_infrastructure(exc: BaseException) -> None:
    """Re-raise ``exc`` unless it is an infrastructure failure.

    Returns normally when the failure IS infrastructure, so the caller's own
    503 (and any fallback it guards) runs. Re-raises otherwise, keeping the
    exception's type and traceback so the defect surfaces as a 500 with its
    stack intact rather than as a retryable message.
    """
    from lib.infra_errors import is_infrastructure_error  # noqa: PLC0415

    if not is_infrastructure_error(exc):
        raise exc


def unavailable(detail: str, exc: BaseException) -> NoReturn:
    """Raise a 503 for ``exc``, or re-raise it when it is a defect.

    The one-call form of the guard above, for a handler whose only job is the
    503.
    """
    from fastapi import HTTPException  # noqa: PLC0415

    raise_unless_infrastructure(exc)
    raise HTTPException(status_code=503, detail=detail) from exc
