"""Pins the SQLAlchemy engine config that protects Cloud SQL long-running jobs.

The 2026-05-14 fetch-market-data SSL failure (`ssl.SSLError: [SSL:
BAD_LENGTH]` at ~2h 45m into a 5-hour upsert run) was caused by Cloud
SQL's TLS session silently dying mid-job. SQLAlchemy's `pool_pre_ping`
issues a cheap SELECT 1 before handing a pooled connection back to the
caller; if it fails, the pool invalidates the dead connection and
makes a fresh one. Without it, the caller gets a corpse and the next
pg8000 send hits BAD_LENGTH.

PR #461 turned this into a recurring outage by changing the daily
fetch-market-data live writer to upsert all 250 enriched rows per
ticker (was iloc[-1] only). The daily run ballooned from minutes to
hours — long enough for the TLS session to drop reliably.

This test reads gcp/database.py's AST and fails if the keyword
`pool_pre_ping=True` is ever dropped from the `sqlalchemy.create_engine`
call. AST-based check stays valid even when the broader test
environment lacks sqlalchemy installed (the CI image has it; some
local envs don't).
"""
from __future__ import annotations

import ast
from pathlib import Path


def _find_create_engine_call() -> ast.Call:
    """Locate the sqlalchemy.create_engine(...) call in gcp/database.py."""
    src = Path("gcp/database.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Match `sqlalchemy.create_engine(...)` (Attribute) and
            # `create_engine(...)` (Name) since either form is valid.
            if (isinstance(func, ast.Attribute) and func.attr == "create_engine") or \
               (isinstance(func, ast.Name) and func.id == "create_engine"):
                return node
    raise AssertionError("could not find a create_engine(...) call in gcp/database.py")


def test_create_engine_passes_pool_pre_ping_true():
    """`sqlalchemy.create_engine` MUST be called with `pool_pre_ping=True`.

    Without it, Cloud SQL TLS drops during long jobs surface as
    'ssl.SSLError: [SSL: BAD_LENGTH]' on the next pg8000 send.
    """
    call = _find_create_engine_call()
    kw = {k.arg: k.value for k in call.keywords if k.arg is not None}
    assert "pool_pre_ping" in kw, (
        "create_engine missing pool_pre_ping kwarg. The Cloud SQL "
        "long-job failure mode (SSL BAD_LENGTH after a stale TLS "
        "session) requires pre-ping to stay reliable. See module "
        "docstring for the 2026-05-14 postmortem."
    )
    value = kw["pool_pre_ping"]
    # Accept ast.Constant(True) — anything else (False, dynamic expression)
    # means the protection is gone or conditionally disabled.
    assert isinstance(value, ast.Constant) and value.value is True, (
        f"pool_pre_ping must be the literal True (got {ast.dump(value)})."
    )


def test_create_engine_retains_existing_pool_args():
    """Sanity-pin the other pool args so future refactors don't silently
    drop pool_recycle / pool_size and reintroduce a different failure."""
    call = _find_create_engine_call()
    kw = {k.arg: k.value for k in call.keywords if k.arg is not None}
    for required in ("pool_recycle", "pool_size", "pool_timeout", "max_overflow"):
        assert required in kw, f"create_engine missing {required} kwarg"


def _function_body_source(name: str) -> str:
    """Return source code of the named function in gcp/database.py."""
    import inspect
    src = Path("gcp/database.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"function {name!r} not found in gcp/database.py")


def test_upsert_dataframe_checks_out_per_chunk():
    """`upsert_dataframe` MUST re-checkout the connection inside the
    chunk loop, not once at the top.

    Codex P1 on PR #483 (2026-05-14) caught that `pool_pre_ping` only
    fires at engine checkout, not on subsequent `conn.execute()` calls.
    For long bulk loops the original `with engine.begin() as conn:` at
    the top of the function defeated pre-ping for every chunk after
    the first — the dead TLS socket got reused and BAD_LENGTH happened
    anyway.

    AST shape check: the `with engine.begin()` (or `engine.connect()`)
    must appear INSIDE a `for` loop, not as a top-level wrapper.
    """
    src = _function_body_source("upsert_dataframe")
    fn = ast.parse(src).body[0]
    assert isinstance(fn, ast.FunctionDef)

    def _is_engine_with(node):
        if not isinstance(node, ast.With):
            return False
        for item in node.items:
            ce = item.context_expr
            if isinstance(ce, ast.Call) and isinstance(ce.func, ast.Attribute):
                if ce.func.attr in ("begin", "connect"):
                    return True
        return False

    # Find every `with engine.begin()/connect()` and every `for` loop;
    # at least one engine-with must be NESTED inside a for loop.
    nested_engine_with_in_for = False
    for node in ast.walk(fn):
        if isinstance(node, ast.For):
            for inner in ast.walk(node):
                if inner is node:
                    continue
                if _is_engine_with(inner):
                    nested_engine_with_in_for = True
                    break

    assert nested_engine_with_in_for, (
        "upsert_dataframe must re-checkout the SQLAlchemy connection per "
        "chunk so pool_pre_ping fires on each chunk's checkout. See PR "
        "#483 Codex P1 review — without per-chunk checkout, a stale TLS "
        "session mid-bulk surfaces as 'ssl.SSLError: [SSL: BAD_LENGTH]'."
    )


def test_bulk_insert_dataframe_checks_out_per_chunk():
    """Same per-chunk checkout requirement as upsert_dataframe."""
    src = _function_body_source("bulk_insert_dataframe")
    fn = ast.parse(src).body[0]

    def _is_engine_with(node):
        if not isinstance(node, ast.With):
            return False
        for item in node.items:
            ce = item.context_expr
            if isinstance(ce, ast.Call) and isinstance(ce.func, ast.Attribute):
                if ce.func.attr in ("begin", "connect"):
                    return True
        return False

    nested = False
    for node in ast.walk(fn):
        if isinstance(node, ast.For):
            for inner in ast.walk(node):
                if inner is node:
                    continue
                if _is_engine_with(inner):
                    nested = True
                    break

    assert nested, (
        "bulk_insert_dataframe must re-checkout the SQLAlchemy connection "
        "per chunk (same reason as upsert_dataframe — Codex P1 / PR #483)."
    )
