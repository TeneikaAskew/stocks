"""Identifier isolation for the per-user watchlist tables.

`user_watchlists` and `watched_tickers` are read and written by exactly one
runtime path, the `/api/me/watchlist` router. No job, library module or
script may name them: the shared `watchlists` table stays the one source the
pipeline reads, so a user's private list can never leak into a fetcher or a
signal run.

The only other file the matching set may ever contain is the FEAT-DATA-001
ingest job, `gcp/fetchers/fetch_watched_tickers.py`. It does not exist yet,
so the assertion is a SUBSET check: that file can arrive without a test
edit, while any fourth path fails here.

Hermetic: reads source text only.
"""
from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]

_ROOTS = ("gcp", "lib", "scripts", "platform/api")
_SUFFIXES = {".py", ".sql", ".sh"}
_SKIP_DIRS = {"tests", "__pycache__"}
_IDENT = re.compile(r"\b(user_watchlists|watched_tickers)\b")

_KNOWN = {"gcp/schema.sql", "platform/api/routers/me_watchlist.py"}
_ALLOWED = _KNOWN | {"gcp/fetchers/fetch_watched_tickers.py"}


def _matching_paths() -> set[str]:
    found: set[str] = set()
    for root in _ROOTS:
        base = _REPO / root
        for path in base.rglob("*"):
            rel_parts = path.relative_to(base).parts
            if _SKIP_DIRS.intersection(rel_parts):
                continue
            if not path.is_file() or path.suffix not in _SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if _IDENT.search(text):
                found.add(path.relative_to(_REPO).as_posix())
    return found


def test_scan_finds_the_known_files():
    """Non-vacuity: an empty or mis-rooted walk must not pass silently."""
    found = _matching_paths()
    missing = _KNOWN - found
    assert not missing, f"scan did not find known files: {sorted(missing)}"


def test_only_allowed_files_name_the_watchlist_tables():
    found = _matching_paths()
    offenders = sorted(found - _ALLOWED)
    assert not offenders, (
        "user_watchlists / watched_tickers may only appear in "
        f"{sorted(_ALLOWED)}; also found in: {offenders}"
    )
