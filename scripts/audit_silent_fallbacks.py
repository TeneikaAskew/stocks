#!/usr/bin/env python3
"""Inventory the `except: -> neutral value` sites CLAUDE.md Rule 3.7 forbids.

Why a script and not a list
---------------------------
`docs/audits/FALLBACK_AUDIT_2026-05-13.md` catalogued ~121 findings by hand.
Four months later nobody could say which were fixed without re-reading every
file, so the audit aged into a document about a tree that no longer existed.
This makes the inventory reproducible: run it, diff it against the last run,
and the delta is the answer.

What it flags
-------------
An exception handler that returns a value the caller cannot distinguish from
a legitimate result — `[]`, `{}`, `None`, `0`, `False`, `''`, an empty
DataFrame — and that does not re-raise anywhere in the handler.

That shape is not automatically a bug. CLAUDE.md's distinction is between a
**missing** input (which may legitimately be empty) and a **failed** one
(which must raise), and no static check can tell those apart. So this reports
sites and the two signals that predict severity, and a human classifies:

* ``broad``  — catches ``Exception`` or bare, so it swallows programming
  errors along with the vendor timeout it was written for.
* ``logs``   — whether the handler records anything at all. A swallow with no
  log leaves no trace that the failure happened.

Usage
-----
    python scripts/audit_silent_fallbacks.py                 # table
    python scripts/audit_silent_fallbacks.py --json          # machine-readable
    python scripts/audit_silent_fallbacks.py --path lib      # one subtree
    python scripts/audit_silent_fallbacks.py --worst         # broad AND silent

Exits 0 always: this is an inventory, not a gate. Failing CI on 255 known
sites would teach people to skip it.
"""
from __future__ import annotations

import argparse
import ast
import collections
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

# `tests/` legitimately returns canned data (CLAUDE.md exempts fixtures and
# mocks); `archive/` is retired code kept as a record; `docs/` is prose.
SKIP_DIRS = {".git", "node_modules", "__pycache__", "archive", "docs",
             "tests", ".venv", "venv"}

# "Surfaced" is broader than "logged": `gcp/audit_infra_drift.py` appends to a
# report object that is posted to Discord, which is a louder signal than a log
# line, and flagging it as silent would be wrong.
LOG_MARKERS = ("log.", "logger.", "logging.", "LOG.", "print(", "warn", "_log",
               "report.", "errors.append", "findings.append", "st.error")

# `None` is usually the RIGHT answer: it is what CLAUDE.md asks for in place of
# a coerced `0`, and a nullable contract renders it as an em-dash. A neutral
# CONTAINER or NUMBER is the shape the rule forbids, because the caller cannot
# tell it from a real empty result or a real zero.
FORBIDDEN_SHAPES = {"[]", "{}", "0", "0.0", "''", "False", "list()", "dict()",
                    # A dropped item is a neutral substitution: the
                    # collection comes back short and no caller can tell.
                    "continue",
                    # And so is an abandoned loop. This was left out on the
                    # argument that `break` after an error is often deliberate
                    # flow control; the two live sites say otherwise, and both
                    # are pagination loops:
                    #   gcp/fetchers/fetch_economic_events.py:315 returns the
                    #     pages it already has when a FRED request fails
                    #   scripts/fetch_catalyst_calendar.py:169 does the same
                    #     for Benzinga
                    # Each returns a partial collection as a complete one,
                    # which is the same lie `continue` tells one item at a
                    # time (Codex, PR #994).
                    "break",
                    "set()", "tuple()", "empty DataFrame", "tuple of neutrals"}


def _neutral(value: ast.expr | None) -> str | None:
    """Name the neutral value this `return` produces, or None if it isn't one."""
    if value is None:
        return "None (bare return)"
    if isinstance(value, ast.Constant):
        if value.value is None:
            return "None"
        if value.value in (0, 0.0, "", False):
            return repr(value.value)
        return None
    if isinstance(value, ast.List) and not value.elts:
        return "[]"
    if isinstance(value, ast.Dict) and not value.keys:
        return "{}"
    if isinstance(value, ast.Tuple) and value.elts and all(
            isinstance(e, ast.Constant) and e.value in (None, 0, 0.0, "", False)
            for e in value.elts):
        return "tuple of neutrals"
    if isinstance(value, ast.Call):
        f = value.func
        if isinstance(f, ast.Attribute) and f.attr == "DataFrame" and not value.args:
            return "empty DataFrame"
        if isinstance(f, ast.Name) and f.id in ("list", "dict", "set", "tuple") \
                and not value.args:
            return f"{f.id}()"
    return None


def _own_nodes(handler: ast.ExceptHandler):
    """Every node in THIS handler's body, not a nested handler's.

    `ast.walk` descends into nested `try`/`except`, so a neutral assignment in
    an inner handler was attributed to every enclosing handler as well --
    `platform/api/routers/dashboard.py` and `scripts/fetch_earnings_calendar.py`
    were each reported twice with identical assignments, although the outer
    handler retries an alternate import and only the inner one substitutes a
    neutral value (Codex, PR #994). An inventory that double-counts and
    misattributes cannot be diffed against anything.

    A nested try's protected body IS still visited: that is code running in
    this handler. Only the nested `except` bodies are skipped.
    """
    stack = list(handler.body)
    while stack:
        n = stack.pop()
        yield n
        for child in ast.iter_child_nodes(n):
            if isinstance(child, ast.ExceptHandler):
                continue
            stack.append(child)


def _handler_returns(node: ast.ExceptHandler) -> tuple[list[str], list[str]]:
    """Neutral values this handler substitutes. Empty if it re-raises.

    A `return` is only one way to swallow. Walking `Return` alone missed the
    two shapes that produce the worst live examples:

      except Exception:          # lib/signals.py -- malformed disabled-
          dc = []                # condition JSON becomes "nothing disabled",
                                 # which is HOW the C-04 incident happened
      except Exception:          # platform/api/main.py -- a failed date
          staleness_days = 0     # parse becomes "perfectly fresh"

      except Exception:          # and the plainest one of all
          pass

    An inventory that cannot see those cannot be diffed against the
    hand-written audit it replaces, which is the claim this script makes.
    """
    # An UNCONDITIONAL re-raise, and only that.
    #
    # This used to fire on a `Raise` ANYWHERE in the handler, which silenced
    # the shape that matters most -- one that raises on one branch and
    # substitutes on another:
    #
    #     except Exception:
    #         if owner != "local":
    #             raise HTTPException(status_code=503, ...)
    #         existing_keys = set()      # invisible to the inventory
    #
    # That is `platform/api/routers/journal.py` twice, and it is a real
    # swallow: a signed-out user's failed dedupe lookup becomes "no existing
    # entries", so an import re-adds trades it already holds (Codex, PR #994).
    #
    # Top-level is what makes a raise unconditional: everything after it in
    # the handler is dead, so an assignment above it never escapes either and
    # is not a substitution. A handler that raises on every branch through a
    # conditional still reports nothing, because there is no neutral value to
    # name -- the scan below only records substitutions.
    if any(isinstance(st, ast.Raise) for st in node.body):
        return [], []

    out: list[str] = []
    shapes: list[str] = []
    for n in _own_nodes(node):
        if isinstance(n, ast.Return):
            name = _neutral(n.value)
            if name:
                out.append(name)
                shapes.append(name)
        elif isinstance(n, ast.Assign):
            name = _neutral(n.value)
            if name:
                out.append(f"{_target_names(n.targets)} = {name}")
                # The SHAPE is tracked separately from the display string.
                # `forbidden_shape` intersected the display strings with
                # FORBIDDEN_SHAPES, so `dc = []` never matched `[]` and every
                # assignment fallback was classified as harmless -- dropping
                # exactly the handlers `--worst` exists to surface
                # (Codex, PR #994).
                shapes.append(name)
        elif isinstance(n, ast.AnnAssign) and n.value is not None:
            name = _neutral(n.value)
            if name:
                out.append(f"{_target_names([n.target])} = {name}")
                shapes.append(name)

    # Loop-control swallows. `except Exception: continue` drops the current
    # item and the collection silently comes back SHORT -- a neutral
    # substitution with no value to name, which is why walking returns and
    # assignments could not see it. `lib/data_loader.py` omits a timeframe
    # the caller asked for; `scripts/fetch_earnings_calendar.py` drops
    # earnings rows in three places, and those are ingestion handlers the
    # backlog is meant to track (Codex, PR #994).
    #
    # Recorded even when the handler logs first: `logs` is a separate column,
    # and `--worst` already filters on broad AND unlogged, so a logged
    # `continue` lands in the inventory without being ranked as a priority.
    for n in _own_nodes(node):
        if isinstance(n, ast.Continue):
            out.append("continue (item dropped)")
            shapes.append("continue")
            break
        if isinstance(n, ast.Break):
            out.append("break (loop abandoned)")
            shapes.append("break")
            break

    # A handler whose entire body is `pass` substitutes nothing and says
    # nothing -- the purest silent swallow, and previously invisible because
    # there is no value to classify.
    if not out and all(isinstance(st, ast.Pass) for st in node.body):
        out.append("pass (swallowed, no action)")
        shapes.append("pass")
    return sorted(set(out)), sorted(set(shapes))


def _target_names(targets: list[ast.expr]) -> str:
    names = []
    for t in targets:
        if isinstance(t, ast.Name):
            names.append(t.id)
        elif isinstance(t, ast.Attribute):
            names.append(t.attr)
        elif isinstance(t, (ast.Tuple, ast.List)):
            names.append(_target_names(list(t.elts)))
    return ", ".join(names) or "<target>"


def scan(root: pathlib.Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(REPO)
        if SKIP_DIRS & set(rel.parts):
            continue
        text = path.read_text(errors="replace")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        funcs = [(n.lineno, getattr(n, "end_lineno", n.lineno), n.name)
                 for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            returns, shapes = _handler_returns(node)
            if not returns:
                continue
            enclosing = min(
                (f for f in funcs if f[0] <= node.lineno <= f[1]),
                key=lambda f: f[1] - f[0], default=(0, 0, "<module>"))[2]
            # The handler's own source, exactly -- an earlier line-window
            # version over- and under-counted, and a scanner that miscounts is
            # worse than none.
            body = ast.get_source_segment(text, node) or ""
            exc = ast.unparse(node.type) if node.type else "bare except"
            rows.append({
                "file": str(rel),
                "line": node.lineno,
                "func": enclosing,
                "except": exc,
                "returns": returns,
                "broad": exc in ("Exception", "BaseException", "bare except")
                         or exc.startswith("(Exception"),
                "logs": any(m in body for m in LOG_MARKERS),
                # `None` alone is usually correct; a container or a zero is the
                # shape the rule is actually about.
                "forbidden_shape": bool(set(shapes) & FORBIDDEN_SHAPES),
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--path", default=".", help="subtree to scan (default: repo root)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    ap.add_argument("--worst", action="store_true",
                    help="broad, unlogged, AND returning a container or zero")
    args = ap.parse_args()

    rows = scan(REPO / args.path)
    if args.worst:
        rows = [r for r in rows
                if r["broad"] and not r["logs"] and r["forbidden_shape"]]

    if args.json:
        json.dump(rows, sys.stdout, indent=1)
        print()
        return 0

    by_file = collections.Counter(r["file"] for r in rows)
    shape = sum(1 for r in rows if r["forbidden_shape"])
    print(f"{len(rows)} swallowing handlers in {len(by_file)} files"
          f"{' (broad, unlogged, container-or-zero)' if args.worst else ''}; "
          f"{shape} return a container or a zero rather than None\n")
    for f, n in by_file.most_common():
        print(f"{n:4d}  {f}")
        for r in [x for x in rows if x["file"] == f]:
            flags = ("broad" if r["broad"] else "narrow") + \
                    ("" if r["logs"] else ", SILENT") + \
                    (", FORBIDDEN-SHAPE" if r["forbidden_shape"] else "")
            print(f"        :{r['line']:<5d} {r['func']}() "
                  f"except {r['except']} -> {', '.join(r['returns'])}  [{flags}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
