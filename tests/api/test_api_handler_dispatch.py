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

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
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

    The exemption list is empty, and that is the point. It used to name two
    handlers whose exemptions were both wrong:

    * `refresh_insight_report` — "schedules FastAPI BackgroundTasks".
      Scheduling a background task says nothing about the request path, and
      this one synchronously committed a DB connection and called Cloud
      Tasks before returning. Now a plain `def`; BackgroundTasks is injected
      into those identically.
    * `insights_chat` — "returns a StreamingResponse". Streaming is only
      non-blocking if what is streamed is, and `_stream_gemini` was an async
      generator driving the SDK's SYNCHRONOUS iterator, so Gemini's whole
      response time was spent on the event loop. It is now a plain generator
      that Starlette iterates in a threadpool.

    Both exemptions described a decorator rather than the work behind it.
    Keep the list empty; if a handler needs to be added back, the reason has
    to be about what it actually does while the loop is held.
    """
    exempt: set[str] = set()
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


# Functions that block the calling thread. Named rather than inferred: the
# point is a list a reviewer can read and add to, not a heuristic.
BLOCKING_CALLS = {
    # gcp.database and its router-local wrappers
    "query_to_dataframe", "query_to_dataframe_strict", "execute_sql",
    "execute_returning_scalar", "get_engine",
    "_journal_query", "_journal_exec", "_journal_insert_returning_id",
    "_seed_query", "_coverage_query", "_dates_query", "_query_fn",
    # blocking HTTP and filesystem
    "urlopen", "read_text", "write_text", "read_bytes", "write_bytes",
    "sleep",
}


def _called_names(node: ast.AST) -> list[tuple[str, int]]:
    """(name, lineno) for every call in `node`, by bare or attribute name."""
    out = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        fn = sub.func
        if isinstance(fn, ast.Name):
            out.append((fn.id, sub.lineno))
        elif isinstance(fn, ast.Attribute):
            out.append((fn.attr, sub.lineno))
    return out


def _threadpooled(node: ast.AST) -> set[int]:
    """Line numbers of calls wrapped in `await run_in_threadpool(...)`."""
    safe = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and (
                (isinstance(sub.func, ast.Name) and sub.func.id == "run_in_threadpool")
                or (isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "run_in_threadpool")):
            for inner in ast.walk(sub):
                if isinstance(inner, ast.Call):
                    safe.add(inner.lineno)
    return safe


def test_no_async_route_performs_blocking_io():
    """An `await` somewhere is not proof the whole handler is non-blocking.

    The first version of this file only asked "does this async route contain
    an await?". `dashboard_brief` runs several synchronous DB queries BEFORE
    its await, and `get_avg_volume` can return without reaching its await at
    all — both passed that check while serialising every concurrent request
    behind a slow query. A mixed handler is the harder case precisely because
    it looks correct.

    The second version scanned only calls syntactically inside the route
    function, and that was still too shallow: `dashboard_brief` awaits
    `_apply_live_overlay`, which called `_query_fn` directly. Awaiting a
    helper does not move it off the event loop — the helper IS the event
    loop — so a query one frame down blocks exactly as hard as one in the
    handler body, and the guard reported the file clean. Awaited helpers
    defined in the same module are followed now, and the offender names the
    whole chain so the frame that has to change is obvious.

    A blocking call is acceptable inside `await run_in_threadpool(...)`,
    which is the whole point of that wrapper.
    """
    offenders = []
    for path, tree in _module_trees():
        async_defs = {n.name: n for n in ast.walk(tree)
                      if isinstance(n, ast.AsyncFunctionDef)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef) or not _is_route(node):
                continue
            offenders.extend(
                _blocking_in_chain(path, node, async_defs, chain=(node.name,)))
    assert not offenders, (
        "blocking calls reachable on the event loop from an async def route. "
        "Declare the handler `def` so FastAPI threadpools the whole thing, or "
        "wrap the call in `await run_in_threadpool(...)`:\n  "
        + "\n  ".join(sorted(set(offenders)))
    )


def _blocking_in_chain(path, node, async_defs, chain, seen=None):
    """Blocking calls in `node`, and in the async helpers it awaits.

    Recursion is bounded by `seen`, so mutual recursion between two helpers
    cannot hang the guard. Only helpers defined in the SAME module are
    followed: resolving across modules would need real import resolution, and
    a guard that silently half-resolves is worse than one whose limit is
    stated. That limit is why `BLOCKING_CALLS` stays a hand-maintained list of
    names rather than a heuristic — a wrapper in another module still gets
    caught by its name.
    """
    seen = seen or set()
    if node.name in seen:
        return []
    seen = seen | {node.name}

    where = " -> ".join(chain)
    out = []
    safe_lines = _threadpooled(node)
    for name, lineno in _called_names(node):
        if name in BLOCKING_CALLS and lineno not in safe_lines:
            out.append(f"{path.name}:{lineno} {where} calls {name}() "
                       f"synchronously on the event loop")
    for name in _awaited_names(node):
        helper = async_defs.get(name)
        if helper is not None:
            out.extend(_blocking_in_chain(
                path, helper, async_defs, chain + (name,), seen))
    return out


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
