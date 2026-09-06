"""Route handlers must not put blocking I/O on the event loop.

The API's DB layer (`gcp.database.query_to_dataframe`) is synchronous. A
handler declared `async def` runs ON the event loop, so a blocking call inside
it stalls every other in-flight request. Production request logs before the
fix showed the cost plainly: `/api/health` peaked at 7.97s and `/api/me` at
17.20s over 14 days, both with a 0.00s median. Neither does real work; they
were queued behind a handler blocking the loop.

FastAPI dispatches a plain `def` handler to its threadpool instead, so the
correct declaration for a synchronous handler is `def`, not `async def`.

These are guard tests. They failed to exist when 69 handlers were converted,
and the conversion shipped a 500 on every `/levels` request that the whole
suite passed over: `get_gamma_levels` kept its `await get_options(...)` while
`get_options` became sync, so it raised
`TypeError: object dict can't be used in 'await' expression`.
"""
import ast
import inspect
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "platform"))

pytest.importorskip("fastapi")

API_DIR = REPO_ROOT / "platform" / "api"
SOURCES = sorted((API_DIR / "routers").glob("*.py")) + [API_DIR / "main.py"]


def _module_trees():
    for path in SOURCES:
        yield path, ast.parse(path.read_text(), filename=str(path))


def _is_route(node: ast.AST) -> bool:
    """True when the decorator list marks this as an HTTP route."""
    for dec in getattr(node, "decorator_list", []):
        call = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(call, ast.Attribute) and isinstance(call.value, ast.Name):
            if call.value.id in {"router", "app"} and call.attr in {
                "get", "post", "put", "patch", "delete", "head", "options",
            }:
                return True
    return False


def _awaited_names(node: ast.AST) -> set[str]:
    """Bare function names this node awaits, e.g. `await get_options(...)`."""
    names = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Await) and isinstance(sub.value, ast.Call):
            fn = sub.value.func
            if isinstance(fn, ast.Name):
                names.add(fn.id)
    return names


def test_no_async_route_handler_lacks_await():
    """An `async def` route with no `await` blocks the loop for nothing.

    Three handlers are exempt and each for a reason a syntactic scan cannot
    see, so they are named rather than pattern-matched.
    """
    exempt = {
        "refresh_insight_report",  # schedules FastAPI BackgroundTasks
        "insights_chat",           # returns a StreamingResponse
    }
    offenders = []
    for path, tree in _module_trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef) or not _is_route(node):
                continue
            if node.name in exempt:
                continue
            if not any(isinstance(s, ast.Await) for s in ast.walk(node)):
                offenders.append(f"{path.name}:{node.lineno} {node.name}")
    assert not offenders, (
        "async def route handlers with no await — these run blocking work on "
        "the event loop and serialise every concurrent request. Declare them "
        "`def` so FastAPI threadpools them:\n  " + "\n  ".join(offenders)
    )


def test_no_handler_awaits_a_synchronous_function():
    """Nothing may `await` a plain `def` in the API package.

    This is the check that would have caught the /levels 500. Converting a
    handler to `def` is only safe if nothing awaits it, and "does this
    function await?" does not answer "does anything await this function?".
    """
    sync_defs = {}
    for path, tree in _module_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                sync_defs[node.name] = f"{path.name}:{node.lineno}"

    offenders = []
    for path, tree in _module_trees():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for name in _awaited_names(node):
                if name in sync_defs:
                    offenders.append(
                        f"{path.name}:{node.lineno} {node.name}() awaits "
                        f"{name}(), which is a plain def at {sync_defs[name]}"
                    )
    assert not offenders, (
        "await on a synchronous function raises TypeError at request time:\n  "
        + "\n  ".join(offenders)
    )


def test_gamma_levels_and_its_chain_loader_agree():
    """The specific pairing that broke, pinned by identity rather than by scan."""
    from api.routers import options

    assert not inspect.iscoroutinefunction(options.get_options), (
        "get_options is synchronous; if it becomes async again, "
        "get_gamma_levels must await it."
    )
    assert not inspect.iscoroutinefunction(options.get_gamma_levels), (
        "get_gamma_levels calls get_options directly, so it must match it."
    )
