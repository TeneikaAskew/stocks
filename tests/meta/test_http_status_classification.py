"""A 503 is a claim that retrying will help. Only an outage may make it.

CLAUDE.md Rule 3.7 splits every failure in two, and the split decides the
status code. Cloud SQL unreachable is EXTERNAL: an explicit, retryable 503.
A `KeyError` on a row we shaped wrong is a defect, and a 503 for it tells an
operator to retry code that will never succeed while hiding the bug behind an
outage that is not happening.

`except Exception: raise HTTPException(503)` conflates them. It is easy to
miss because it reads as fail-loud — it usually replaced a swallow — and
because the coverage test written beside such a handler asserts 503 and
therefore stays green through the very regression it was meant to catch.
That has happened twice here: PR #999's four handlers, and the signals router
on #1022, whose two tests raised a bare `RuntimeError` and passed only while
everything answered 503.

This test walks the AST rather than grepping, because a handler nested inside
an `if` is invisible to a line-anchored pattern and one was.

Two things are pinned:

1. The routers this PR owns classify. Any NEW broad handler in them that
   answers 503 without asking `lib.infra_errors` fails this test.
2. The rest are a KNOWN, counted backlog. They are pre-existing and live in
   files this PR does not touch, so per CLAUDE.md 3.7 ("when you find an
   existing fallback") they are catalogued rather than swept in with an
   unrelated change. The count may only go DOWN.

Repo-level invariant, so it lives in tests/meta/ (two levels below root).
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
API = REPO / "platform" / "api"

#: Names that answer "is this failure infrastructure?" — directly, or through
#: the router-side guard in platform/api/http_errors.py.
CLASSIFIERS = (
    "is_infrastructure_error", "is_backend_outage",
    "raise_unless_infrastructure", "unavailable",
)

#: Files whose 503 handlers are this change's responsibility: it created them,
#: or it made them reachable by switching the router to the strict query.
OWNED = {
    "routers/analytics.py",
    "routers/journal.py",
    "routers/signals.py",
    "routers/health.py",
}

#: Pre-existing unclassified handlers, per file, in files this change does not
#: touch. Tracked so the backlog is a number rather than a promise. Lower this
#: as they are fixed; it may never rise.
KNOWN_BACKLOG = {
    "main.py": 6,
    "routers/admin.py": 8,
    "routers/earnings.py": 1,
    "routers/grid.py": 1,
    "routers/insights.py": 2,
    "routers/preferences.py": 2,
    "routers/profile.py": 2,
    "routers/waitlist.py": 1,
}


def _raises_503(handler: ast.ExceptHandler) -> bool:
    for n in ast.walk(handler):
        if not (isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call)):
            continue
        f = n.exc.func
        if (getattr(f, "id", None) or getattr(f, "attr", None)) != "HTTPException":
            continue
        for kw in n.exc.keywords:
            if kw.arg == "status_code" and isinstance(kw.value, ast.Constant) \
                    and kw.value.value == 503:
                return True
        if any(isinstance(a, ast.Constant) and a.value == 503 for a in n.exc.args):
            return True
    return False


def _classifies(handler: ast.ExceptHandler) -> bool:
    for n in ast.walk(handler):
        if isinstance(n, ast.Name) and n.id in CLASSIFIERS:
            return True
        if isinstance(n, ast.Attribute) and n.attr in CLASSIFIERS:
            return True
    return False


def _is_broad(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    types = (handler.type.elts if isinstance(handler.type, ast.Tuple)
             else [handler.type])
    return any(ast.unparse(t) in ("Exception", "BaseException") for t in types)


def _unclassified() -> dict[str, list[int]]:
    """{relative path: [line of each broad, unclassified 503 handler]}."""
    found: dict[str, list[int]] = {}
    for path in sorted(API.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for n in ast.walk(tree):
            if isinstance(n, ast.ExceptHandler) and _is_broad(n) \
                    and _raises_503(n) and not _classifies(n):
                rel = path.relative_to(API).as_posix()
                found.setdefault(rel, []).append(n.lineno)
    return found


def test_the_routers_this_change_owns_classify_before_answering_503():
    found = _unclassified()
    offenders = {f: lines for f, lines in found.items() if f in OWNED}
    assert not offenders, (
        "these handlers answer 503 for every failure, so a defect is reported "
        "as a retryable outage. Ask lib.infra_errors, or use the guard in "
        "platform/api/http_errors.py: %s" % offenders
    )


def test_the_pre_existing_backlog_only_shrinks():
    found = _unclassified()
    counts = {f: len(lines) for f, lines in found.items() if f not in OWNED}

    grown = {f: (n, KNOWN_BACKLOG.get(f, 0))
             for f, n in counts.items() if n > KNOWN_BACKLOG.get(f, 0)}
    assert not grown, (
        "new unclassified 503 handlers, as {file: (now, allowed)}: %s. A 503 "
        "for a defect tells an operator to retry code that will never "
        "succeed; use platform/api/http_errors.raise_unless_infrastructure."
        % grown
    )

    # Fixing one is welcome — but lower the number here so the next addition
    # is still caught.
    shrunk = {f: (counts.get(f, 0), allowed)
              for f, allowed in KNOWN_BACKLOG.items()
              if counts.get(f, 0) < allowed}
    assert not shrunk, (
        "these are now better than KNOWN_BACKLOG records, as {file: (now, "
        "recorded)}: %s. Lower the recorded number so it keeps its grip." % shrunk
    )
