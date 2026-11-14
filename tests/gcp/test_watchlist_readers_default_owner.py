"""Every production reader of ``watchlists`` reads the default owner (FEAT-INSIGHT-001 stage A).

The spec (docs/superpowers/specs/2026-11-13-feat-insight-001-watchlist-default-lock-a.md, section
Readers) records the contract that every stocks job reads only ``user_id = 'default'``. This module
turns that inventory into a source scan, in the shape of tests/gcp/test_signal_monitor_watchlist_source.py:
a reader added later that passes a caller's identity fails CI.

How a reader is classified. ``READERS`` lists every path of the inventory with the helper it calls:

* ``load_watchlist`` / ``resolve_membership_at`` (gcp/fetchers/_watchlist.py): every call is found by
  regex and its owner argument (``user_id=``, or the positional owner) takes one of three shapes: no
  owner, so the helper's ``DEFAULT_USER_ID`` applies (every job and script in the inventory); the literal
  ``"default"`` or ``DEFAULT_USER_ID``; or ``FORWARDING_SITE``, the one expression accepted without being
  resolved, because tests/agents/test_ranker.py proves the chain behind it. An aliased import of either
  helper hides the call from the regex, so it fails the scan.
* ``own-sql``: the file holds its own ``FROM watchlists`` query; ``OWN_SQL_PINS`` records the text that
  must still be there, and gcp/calibrate_level_params.py's binding of its owner is asserted piece by
  piece (it binds ``:user_id`` to ``WATCHLIST_OWNER = 'default'``, it does not inline the literal).
* ``brief_insight_watchlist_tickers``: reads through gcp/calibrate_level_params.py's strict helper.
* ``INSIGHT_UNIVERSE``: forwards a frozen as-of universe to a child job, no read of its own.

A file whose tag is not ``own-sql`` must hold no ``FROM watchlists`` of its own: a reader that grows a
query of its own has to be inventoried as such.

The one exclusion. platform/api/routers/insights.py's two web write routes still write and read back the
caller's own rows through ``_watchlist_owner`` until stage B
(docs/superpowers/specs/2026-11-13-feat-insight-001-watchlist-write-routes-410.md) turns them into 410
and deletes the helper; ``WRITE_ROUTE_EXCLUSION`` names that file, the aliased ``wl_load(user_id=owner)``
calls inside ``add_to_watchlist`` and ``remove_from_watchlist`` are the only reads allowed a non-default
owner, and ``test_write_routes_are_the_only_callers_of_watchlist_owner`` fails the moment anything else
calls the helper. Stage B removes the exclusion together with the routes.

Writers. ``WRITERS`` are the production files whose SQL text inserts into or updates ``watchlists``;
``MENTIONS_ONLY`` are the files whose only match is a log hint, a comment or a docstring, pinned to the
exact line, so a mention that turns into a statement fails the scan.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

LOAD = "load_watchlist"
RESOLVE = "resolve_membership_at"
OWN_SQL = "own-sql"
STRICT_HELPER = "brief_insight_watchlist_tickers"
UNIVERSE = "INSIGHT_UNIVERSE"

# Section Readers of the spec, gcp/signal_monitor.py through gcp/discord_interactions/main.py, plus the
# endpoint this stage adds (platform/api/routers/insights.py, GET /api/insights/watchlist/default).
READERS: dict[str, tuple[str, ...]] = {
    "gcp/signal_monitor.py": (LOAD,),
    "gcp/premarket_brief.py": (LOAD,),
    "gcp/insight_pipeline_job.py": (LOAD, RESOLVE),
    "lib/agents/summarizers.py": (RESOLVE,),
    "gcp/insight_tasks.py": (UNIVERSE,),
    "gcp/calibrate_level_params.py": (OWN_SQL,),
    "gcp/fetchers/fetch_alphavantage_intraday.py": (STRICT_HELPER,),
    "gcp/fetchers/fetch_market_data.py": (LOAD, OWN_SQL),
    "gcp/fetchers/fetch_earnings_history.py": (LOAD,),
    "gcp/fetchers/fetch_insider_transactions.py": (LOAD,),
    "gcp/fetchers/fetch_sec_filings.py": (LOAD,),
    "gcp/fetchers/fetch_news_sentiment.py": (LOAD,),
    "gcp/fetchers/fetch_premarket_refresh.py": (LOAD,),
    "gcp/fetchers/fetch_av_historical_options.py": (LOAD,),
    "gcp/fetchers/fetch_rss_news.py": (LOAD,),
    "scripts/run_historical_signals.py": (LOAD,),
    "lib/agents/ranker/candidates.py": (LOAD,),
    "lib/ticker_info.py": (LOAD,),
    "scripts/backfill_watchlist_data.py": (LOAD,),
    "scripts/validation/validate_brief_accuracy.py": (LOAD,),
    "scripts/analysis/per_ticker_calibration.py": (OWN_SQL,),
    "gcp/discord_interactions/main.py": (OWN_SQL,),
    "platform/api/routers/insights.py": (OWN_SQL,),
}

# The text an own-sql reader must still hold, after adjacent string literals are joined and whitespace
# collapsed (see _joined_source). Each pin records what the spec's inventory says about the reader.
OWN_SQL_PINS: dict[str, tuple[str, ...]] = {
    # The manual --backfill targets. Its owner and removal predicates are pinned by
    # tests/gcp/test_fetch_market_data_backfill_targets.py; this pin keeps the arm inventoried here.
    "gcp/fetchers/fetch_market_data.py": ("SELECT ticker FROM watchlists",),
    # --auto-tickers --from-db reads every owner's signals rows, by design; harmless while only
    # 'default' exists, and pinned so a change shows up here.
    "scripts/analysis/per_ticker_calibration.py": (
        '"SELECT DISTINCT ticker FROM watchlists WHERE signals=true AND removed_at IS NULL ORDER BY ticker"',
    ),
    # Autocomplete reads every owner's active rows (same remark); /watchlist list binds the default owner.
    "gcp/discord_interactions/main.py": (
        'WATCHLIST_USER_ID = "default"',
        '"SELECT DISTINCT ticker FROM watchlists WHERE removed_at IS NULL "',
        '"SELECT ticker, added_at, source FROM watchlists WHERE user_id = :u AND removed_at IS NULL ORDER BY ticker"',
        '{"u": WATCHLIST_USER_ID}',
    ),
    # GET /api/insights/watchlist/default names the owner in the SQL text itself.
    "platform/api/routers/insights.py": (
        "FROM watchlists WHERE user_id = 'default' AND removed_at IS NULL ORDER BY added_at, ticker",
    ),
}

WRITERS = {
    "gcp/discord_interactions/main.py",   # /watchlist add and remove
    "gcp/backfill_ticker.py",             # add_to_watchlist, source discord-replay
    "gcp/fetchers/_watchlist.py",         # the add and remove helpers
    "gcp/schema.sql",                     # the signals seed
}

MENTIONS_ONLY = {
    "gcp/signal_monitor.py": '"  UPDATE watchlists SET signals = TRUE WHERE ticker IN (...)"',
    "gcp/insight_pipeline_job.py": "# explicitly opt those in via UPDATE watchlists SET",
    "scripts/maintenance/doc_inventory.py":
        "to run `UPDATE watchlists SET signals = TRUE ...`. The process only READS",
}

# Removed by stage B, which turns the two web write routes into 410 and deletes _watchlist_owner.
WRITE_ROUTE_EXCLUSION = "platform/api/routers/insights.py"
WRITE_ROUTES = {"add_to_watchlist", "remove_from_watchlist"}

FORWARDING_SITE = (
    "lib/agents/ranker/candidates.py",
    "user_id=user_id if user_id is not None else DEFAULT_USER_ID",
)

RANK_TICKERS_CALLERS = {"platform/api/routers/insights.py", "gcp/auto_refresh_top_n.py"}

DEFAULT_OWNER_EXPRESSIONS = {'"default"', "'default'", "DEFAULT_USER_ID"}
HELPER_OWNER_POSITION = {LOAD: 0, RESOLVE: 1}   # load_watchlist(user_id, ...), resolve_membership_at(as_of, user_id)

SCANNED_TREES = ("gcp", "lib", "platform", "scripts")
SKIPPED_DIRS = {"tests", "__pycache__", "node_modules", ".git"}
WRITE_STATEMENT = re.compile(r"\b(?:INSERT\s+INTO|UPDATE)\s+watchlists\b", re.I)
HELPER_CALL = re.compile(r"\b(load_watchlist|resolve_membership_at)\(")
ALIASED_HELPER_IMPORT = re.compile(r"\b(load_watchlist|resolve_membership_at)\s+as\s+\w+")
OWN_QUERY = re.compile(r"\bFROM\s+watchlists\b")


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _joined_source(text: str) -> str:
    """The file with adjacent string literals joined and whitespace collapsed, so a SQL statement
    written as several literals, or as a triple-quoted block, reads as one line."""
    joined = re.sub(r'"\s*"', "", text)
    joined = re.sub(r"'\s*'", "", joined)
    return " ".join(joined.split())


def _balanced_arguments(text: str, start: int) -> tuple[str, int]:
    """The argument text of the call whose opening parenthesis is at ``start``, and the line it is on."""
    depth = 0
    quote = None
    for i in range(start, len(text)):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], text.count("\n", 0, start) + 1
    raise AssertionError(f"unbalanced call at offset {start}")


def _split_arguments(args: str) -> tuple[list[str], dict[str, str]]:
    """Top-level positional and keyword arguments of a call's argument text."""
    parts: list[str] = []
    depth = 0
    quote = None
    current = ""
    for ch in args:
        if quote:
            current += ch
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    positional: list[str] = []
    keywords: dict[str, str] = {}
    for part in parts:
        part = " ".join(part.split())
        if not part:
            continue
        m = re.match(r"^([A-Za-z_]\w*)\s*=(?!=)\s*(.*)$", part)
        if m:
            keywords[m.group(1)] = m.group(2).strip()
        else:
            positional.append(part)
    return positional, keywords


def _helper_calls(rel: str) -> list[tuple[str, int, list[str], dict[str, str]]]:
    """(helper, line, positional, keywords) for every load_watchlist( / resolve_membership_at( in a file."""
    text = _read(rel)
    out = []
    for m in HELPER_CALL.finditer(text):
        args, line = _balanced_arguments(text, m.end() - 1)
        positional, keywords = _split_arguments(args)
        out.append((m.group(1), line, positional, keywords))
    return out


def _owner_expression(helper: str, positional: list[str], keywords: dict[str, str]) -> str | None:
    """The expression a call passes as the owner, or None when the helper's default applies."""
    for arg in positional:
        if arg.startswith("*"):
            return arg          # *args / **kwargs cannot be resolved: fails the scan
    if "user_id" in keywords:
        return keywords["user_id"]
    position = HELPER_OWNER_POSITION[helper]
    if len(positional) > position:
        return positional[position]
    return None


def _production_files(suffix: str | None = None):
    for tree in SCANNED_TREES:
        for path in sorted((REPO / tree).rglob("*")):
            if not path.is_file() or SKIPPED_DIRS & set(path.relative_to(REPO).parts):
                continue
            if suffix and path.suffix != suffix:
                continue
            yield path


def _enclosing_functions(tree: ast.AST) -> dict[int, str]:
    """Map every call node id to the name of the function definition it sits in."""
    enclosing: dict[int, str] = {}

    def walk(node: ast.AST, current: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(child, child.name)
            else:
                if isinstance(child, ast.Call) and current is not None:
                    enclosing[id(child)] = current
                walk(child, current)

    walk(tree, None)
    return enclosing


def _call_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


# ── the inventory itself ─────────────────────────────────────────────────────


def test_every_inventory_path_exists():
    """The scan must fail loud, not pass vacuously, when a listed file is gone (Review Focus 4)."""
    listed = (set(READERS) | WRITERS | set(MENTIONS_ONLY) | set(OWN_SQL_PINS) | RANK_TICKERS_CALLERS
              | {WRITE_ROUTE_EXCLUSION, FORWARDING_SITE[0]})
    missing = sorted(rel for rel in listed if not (REPO / rel).is_file())
    assert missing == [], f"inventory paths missing from the tree: {missing}"
    assert set(OWN_SQL_PINS) <= {rel for rel, tags in READERS.items() if OWN_SQL in tags}


@pytest.mark.parametrize("rel", sorted(READERS))
def test_every_reader_calls_the_helper_it_is_inventoried_with(rel):
    """A renamed helper, or a reader that grew a query of its own, changes the inventory."""
    text = _read(rel)
    tags = READERS[rel]
    calls = {helper for helper, _, _, _ in _helper_calls(rel)}
    for tag in (LOAD, RESOLVE):
        assert (tag in tags) == (tag in calls), f"{rel}: inventoried {tags}, calls {sorted(calls)}"
    assert (OWN_SQL in tags) == bool(OWN_QUERY.search(text)), (
        f"{rel}: {'has' if OWN_QUERY.search(text) else 'has no'} FROM watchlists of its own, inventoried {tags}")
    if STRICT_HELPER in tags:
        assert f"from gcp.calibrate_level_params import {STRICT_HELPER}" in text, rel
    if UNIVERSE in tags:
        assert UNIVERSE in text and not calls, rel
    if rel != WRITE_ROUTE_EXCLUSION:
        assert not ALIASED_HELPER_IMPORT.search(text), (
            f"{rel}: an aliased import hides a helper call from the scan")


# ── readers ──────────────────────────────────────────────────────────────────


def test_no_reader_passes_a_non_default_user_id():
    offending: list[str] = []
    forwarding_sites: list[str] = []
    for rel, tags in READERS.items():
        if rel == WRITE_ROUTE_EXCLUSION:
            continue   # its aliased calls are read by ast in test_write_routes_read_back_their_own_rows
        for helper, line, positional, keywords in _helper_calls(rel):
            owner = _owner_expression(helper, positional, keywords)
            if owner is None or owner in DEFAULT_OWNER_EXPRESSIONS:
                continue
            if (rel, f"user_id={owner}") == FORWARDING_SITE:
                forwarding_sites.append(f"{rel}:{line}")
                continue
            offending.append(f"{rel}:{line} {helper}(... user_id={owner})")
    assert offending == [], "readers passing a non-default owner:\n  " + "\n  ".join(offending)
    assert len(forwarding_sites) == 1, (
        f"exactly one forwarding site is accepted, {FORWARDING_SITE}; found {forwarding_sites}")

    # The calibration reader binds its owner, it does not inline it (stocks#1887 review).
    calibration = _read("gcp/calibrate_level_params.py")
    sql_block = re.search(r"^WATCHLIST_SQL = \(\s*((?:\"[^\"]*\"\s*)+)\)", calibration, re.M)
    assert sql_block is not None, "WATCHLIST_SQL is no longer a parenthesised string constant"
    watchlist_sql = "".join(re.findall(r'"([^"]*)"', sql_block.group(1)))
    assert "user_id = :user_id" in watchlist_sql and "removed_at IS NULL" in watchlist_sql, watchlist_sql
    assert re.search(r"^WATCHLIST_OWNER = 'default'$", calibration, re.M), "WATCHLIST_OWNER is not 'default'"
    assert "query(WATCHLIST_SQL, {'user_id': WATCHLIST_OWNER})" in calibration, (
        "strict_watchlist no longer binds WATCHLIST_OWNER")


def test_own_sql_readers_keep_their_recorded_text():
    for rel, pins in OWN_SQL_PINS.items():
        source = _joined_source(_read(rel))
        for pin in pins:
            assert " ".join(pin.split()) in source, f"{rel}: pinned text not found: {pin}"


def test_write_routes_read_back_their_own_rows_and_nothing_else_does():
    """The exclusion, read precisely: in insights.py every helper call that passes a non-default owner
    is a ``load_watchlist`` read-back inside add_to_watchlist or remove_from_watchlist, with the owner
    ``owner`` that _watchlist_owner resolved. Stage B deletes both and this exclusion with them."""
    tree = ast.parse(_read(WRITE_ROUTE_EXCLUSION))
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "gcp.fetchers._watchlist":
            for alias in node.names:
                if alias.name in (LOAD, RESOLVE):
                    aliases[alias.asname or alias.name] = alias.name
    assert aliases, "the write routes no longer import the read helper: remove the exclusion"
    enclosing = _enclosing_functions(tree)
    excluded = 0
    offending: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node) not in aliases:
            continue
        helper = aliases[_call_name(node)]
        positional = [ast.unparse(a) for a in node.args]
        keywords = {k.arg or "**": ast.unparse(k.value) for k in node.keywords}
        owner = _owner_expression(helper, positional, keywords)
        if owner is None or owner in DEFAULT_OWNER_EXPRESSIONS:
            continue
        if helper == LOAD and owner == "owner" and enclosing.get(id(node)) in WRITE_ROUTES:
            excluded += 1
            continue
        offending.append(f"{WRITE_ROUTE_EXCLUSION}:{node.lineno} {helper}(user_id={owner})")
    assert offending == [], "\n  ".join(["non-default reads outside the write routes:"] + offending)
    assert excluded == 2, f"the two write routes each read back the caller's rows once; found {excluded}"


def test_rank_tickers_callers_pass_the_default_owner():
    """The static half of the forwarding chain: every production call of rank_tickers carries
    user_id="default" or no user_id at all (the behavioural half is tests/agents/test_ranker.py)."""
    callers: dict[str, list[str]] = {}
    for path in _production_files(".py"):
        text = path.read_text(encoding="utf-8")
        if "rank_tickers" not in text:
            continue
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Call) and _call_name(node) == "rank_tickers":
                callers.setdefault(rel, [])
                assert not node.args, f"{rel}:{node.lineno} rank_tickers takes keywords only"
                for kw in node.keywords:
                    if kw.arg == "user_id":
                        callers[rel].append(ast.unparse(kw.value))
                        assert isinstance(kw.value, ast.Constant) and kw.value.value == "default", (
                            f"{rel}:{node.lineno} rank_tickers(user_id={ast.unparse(kw.value)})")
    assert set(callers) == RANK_TICKERS_CALLERS, callers
    assert callers["platform/api/routers/insights.py"] == ['"default"'] or \
        callers["platform/api/routers/insights.py"] == ["'default'"], callers
    assert callers["gcp/auto_refresh_top_n.py"] == [], callers


# ── writers ──────────────────────────────────────────────────────────────────


def test_only_the_named_writers_insert_or_update_watchlists():
    matches: dict[str, list[str]] = {}
    for path in _production_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        hits = [line.strip() for line in lines if WRITE_STATEMENT.search(line)]
        if hits:
            matches[path.relative_to(REPO).as_posix()] = hits
    assert set(matches) == WRITERS | set(MENTIONS_ONLY), (
        f"files with INSERT INTO or UPDATE watchlists: {sorted(matches)}")
    for rel, recorded in MENTIONS_ONLY.items():
        assert matches[rel] == [recorded], f"{rel}: {matches[rel]} is not the recorded mention {recorded!r}"
    assert WRITE_ROUTE_EXCLUSION not in matches, "the write routes call the helpers, they hold no SQL text"


def test_write_routes_are_the_only_callers_of_watchlist_owner():
    tree = ast.parse(_read(WRITE_ROUTE_EXCLUSION))
    assert any(isinstance(n, ast.FunctionDef) and n.name == "_watchlist_owner" for n in ast.walk(tree)), (
        "_watchlist_owner is gone: stage B landed, remove the exclusion from this scan")
    enclosing = _enclosing_functions(tree)
    callers = sorted(
        f"{enclosing.get(id(node), '<module>')}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node) == "_watchlist_owner"
    )
    assert {c.split(":")[0] for c in callers} == WRITE_ROUTES, callers
    assert len(callers) == 2, callers
