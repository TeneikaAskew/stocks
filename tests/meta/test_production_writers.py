"""Only sanctioned code may create rows in signal_alerts / trades, and only
the production replay path may simulate a fire decision.

Why (audit 2026-08-27, #820 R3 and #821 R4): an earlier revision of
scripts/backfill_signals.py wrote 432 signal_alerts rows and 412 trades
rows into production on 2026-04-18 (bulk-inserted, run_kind='live',
total_score 3, strength 'weak', simulated 60-bar outcomes), indistinguishable
from live fires to every downstream aggregate. scripts/compare_tier_fires.py
re-implemented the fire decision with the strategies' private condition
checkers and its numbers gated PR #248, which is the CLAUDE.md §3.6 incident
shape a second time. Nothing enforced either rule, so this test does:

1. row-creating writes to ``signal_alerts`` / ``trades`` may appear only in
   the writers listed in SANCTIONED_ROW_WRITERS;
2. under ``scripts/`` only the production replay harness may call the
   strategy condition checkers or the monitor's per-bar evaluator.

Repo-level invariant, so it lives in tests/meta/ (two levels below root).
"""
from __future__ import annotations

import ast
import functools
import re
import warnings
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("gcp", "lib", "scripts", "platform")

# upsert_dataframe(df, 'signal_alerts', ...) / upsert_rows(conn, "trades", ...)
# / df.to_sql("trades", ...) / INSERT INTO signal_alerts (...) / COPY trades.
# UPDATE-only writers (the EOD resolver, the exit watcher) create no rows
# and are not in scope. The table name may sit a few arguments after the
# call (a `pd.DataFrame(rows)` argument carries its own parentheses), the
# match is case-insensitive and a `public.` prefix is allowed (internal
# review of #1022: the first version missed all four).
_ROW_WRITE = re.compile(
    r"""(?:upsert_dataframe|upsert_rows|bulk_insert_dataframe|bulk_copy_upsert|to_sql)\s*\(.{0,300}?['"](?:public\.)?(signal_alerts|trades)['"]"""
    r"""|INSERT\s+INTO\s+(?:public\.)?(signal_alerts|trades)\b"""
    r"""|\bCOPY\s+(?:public\.)?(signal_alerts|trades)\b""",
    re.S | re.I,
)

SANCTIONED_ROW_WRITERS = {
    "gcp/signal_monitor.py",              # live fires
    "gcp/trade_logger.py",                # trades closed by the monitor
    "gcp/migrate_to_gcp.py",              # one-shot parquet -> Cloud SQL migration
    "scripts/replay_signal_monitor.py",   # production replay, run_kind='replay' + replay_id
}

_FIRE_DECISION = re.compile(
    r"\b(_check_call_conditions|_check_put_conditions|_evaluate_strategies_for_bar)\b"
)

# scripts/ files allowed to call the strategy condition checkers directly.
SANCTIONED_FIRE_HARNESSES = {
    "scripts/replay_signal_monitor.py",
    # Read-only eligibility report (Track A G.P0.11.e). It writes a markdown
    # file, never a production table. Same §3.6 shape as compare_tier_fires
    # though, and is flagged on #821 for the same treatment.
    "scripts/analysis/momentum_eligibility.py",
}


def _py_files(roots):
    for root in roots:
        for p in (REPO / root).rglob("*.py"):
            if "_archive" in p.parts or "node_modules" in p.parts:
                continue
            yield p


def _rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


def test_only_sanctioned_code_creates_signal_alerts_or_trades_rows():
    offenders = {}
    for p in _py_files(SCAN_ROOTS):
        text = p.read_text(errors="ignore")
        hits = [m.group(0).split("\n")[0] for m in _ROW_WRITE.finditer(text)]
        if hits and _rel(p) not in SANCTIONED_ROW_WRITERS:
            offenders[_rel(p)] = hits
    assert not offenders, (
        "row-creating writes to signal_alerts/trades outside the sanctioned "
        f"writers (#820): {offenders}"
    )


def test_sanctioned_row_writers_still_exist():
    """Keep the allowlist honest: a renamed writer must be re-listed, not
    silently dropped from coverage."""
    for rel in SANCTIONED_ROW_WRITERS:
        assert (REPO / rel).exists(), rel


def test_backfill_signals_script_is_gone():
    assert not (REPO / "scripts/backfill_signals.py").exists(), (
        "scripts/backfill_signals.py wrote fabricated rows into production "
        "signal_alerts/trades (#820); use scripts/replay_signal_monitor.py"
    )


def test_only_the_production_replay_simulates_fire_decisions():
    offenders = {}
    for p in _py_files(("scripts",)):
        text = p.read_text(errors="ignore")
        hits = sorted({m.group(1) for m in _FIRE_DECISION.finditer(text)})
        if hits and _rel(p) not in SANCTIONED_FIRE_HARNESSES:
            offenders[_rel(p)] = hits
    assert not offenders, (
        "scripts simulating a fire decision outside the production replay "
        f"path (CLAUDE.md §3.6, #821): {offenders}"
    )


def test_compare_tier_fires_script_is_gone():
    assert not (REPO / "scripts/compare_tier_fires.py").exists(), (
        "scripts/compare_tier_fires.py was a throwaway fire-decision harness "
        "whose numbers gated PR #248 (#821)"
    )


# ── the writer regex must catch the obvious rewrites (internal review of
#    #1022, trade-reader round) ──────────────────────────────────────────

_BYPASSES = [
    'upsert_dataframe(pd.DataFrame(rows), "trades", ["ticker", "entry_time"])',
    'insert into signal_alerts (ticker) values (1)',
    'INSERT INTO public.trades (ticker) VALUES (1)',
    'df.to_sql("trades", engine, if_exists="append")',
    'cur.execute("COPY trades FROM STDIN", stream=buf)',
]


def test_the_writer_regex_catches_the_obvious_rewrites():
    """`[^)]*?` could not cross a `)` (so a `pd.DataFrame(rows)` argument
    hid the table name), there was no re.I, and to_sql / COPY were not
    matched at all. A guard that the guarded script's most obvious rewrite
    bypasses is not a guard. A table name held in a variable is beyond a
    regex; that gap is stated here rather than pretended away."""
    missed = [src for src in _BYPASSES if not _ROW_WRITE.search(src)]
    assert missed == [], missed


def test_the_writer_regex_ignores_reads():
    reads = [
        'query_to_dataframe("SELECT * FROM trades WHERE ticker = :t")',
        'upsert_dataframe(df, "market_data_daily", ["ticker", "date"])',
        'pd.read_sql("SELECT count(*) FROM signal_alerts", engine)',
    ]
    caught = [src for src in reads if _ROW_WRITE.search(src)]
    assert caught == [], caught


# ── every reader of signal_alerts says which run_kind it reads ──────────
# (internal review of #1022, trade-reader round: 23 replay-tagged rows sit
# in production and not one reader filtered them; the EOD resolver would
# resolve a replay alert and write its exit onto the live trades row)

_READ_SQL = re.compile(r"\b(?:FROM|JOIN|UPDATE)\s+signal_alerts\b", re.I)


def _sql_strings(path: Path):
    """Every string literal in the module: implicit concatenation is one
    Constant, and an f-string is yielded as the join of its constant parts
    (its parts are not yielded again on their own, or a predicate that
    sits in a later part would look missing)."""
    import ast
    tree = ast.parse(path.read_text(errors="ignore"))
    in_fstring: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            in_fstring.update(id(v) for v in node.values)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            yield "".join(v.value for v in node.values
                          if isinstance(v, ast.Constant) and isinstance(v.value, str))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in in_fstring:
            yield node.value


def test_every_signal_alerts_reader_filters_on_run_kind():
    offenders = {}
    for p in _py_files(SCAN_ROOTS):
        for text in _sql_strings(p):
            if _READ_SQL.search(text) and "run_kind" not in text:
                offenders.setdefault(_rel(p), []).append(" ".join(text.split())[:90])
    assert not offenders, (
        "signal_alerts read or updated without a run_kind predicate "
        f"(replay and backfill rows would be counted as live): {offenders}"
    )


def test_the_freshness_watchdog_measures_live_alerts():
    """scripts/audit_data_freshness.py builds its SQL from a config dict,
    so the AST scan above cannot see it; a replay of today would otherwise
    make signal_alerts look fresh."""
    src = (REPO / "scripts/audit_data_freshness.py").read_text()
    block = src[src.index('"name": "signal_alerts"'):]
    block = block[:block.index("},")]
    assert "\"where\": \"run_kind = 'live'\"" in block, block


def test_the_rvol_reconstruction_selects_live_rows_not_just_non_replay():
    """`run_kind IS DISTINCT FROM 'replay'` keeps 'backfill' rows, so once
    the 432 fabricated alerts are marked, this checked-in reconstruction
    would still mix them into the win-rate and return numbers that support
    the RVOL enforcement decision — and its cohort starts 2026-03-19,
    exactly where the contamination starts (Codex on #1022)."""
    from pathlib import Path as _P

    repo = _P(__file__).resolve().parents[2]
    sql = (repo / "gcp/queries/rvol_gate_analysis.sql").read_text()
    bad = [l for l in sql.splitlines()
           if "IS DISTINCT FROM 'replay'" in l and not l.lstrip().startswith("--")]
    assert bad == [], (
        "these predicates admit run_kind='backfill': %s" % bad)
    assert sql.count("run_kind = 'live'") >= 3, (
        "each cohort must select live rows explicitly")


# ── provenance on the other API-served tables (audit 2026-09-14) ──────────
#
# The #820 fix stopped at signal_alerts and trades. The same shape survived
# on every other table a router serves as ground truth: a backfill write and
# a live write landed identically, so no reader could choose. Measured in
# production 2026-09-14:
#
#   historical_signals  1,553,629 of 1,708,932 rows (90.9%) written >7 days
#                       after the signal they describe
#   insight_reports     70 of 807 reports generated >2 days after their as_of
#   premarket_analysis  no timestamp column at all, so unmeasurable
#
# These two tests pin the halves of the fix a regex can check: every writer
# of those tables sets run_kind, and the readers that must not serve a
# non-live row say so in their SQL.

PROVENANCE_TABLES = ("premarket_analysis", "insight_reports", "historical_signals")

# Writers allowed to create rows in those tables, and the kind each stamps.
SANCTIONED_PROVENANCE_WRITERS = {
    "gcp/premarket_brief.py",                  # 'replay' under BRIEF_AS_OF, else 'live'
    "gcp/insight_pipeline_job.py",             # 'replay' under INSIGHT_AS_OF, else 'live'
    "gcp/historical_signals.py",               # bulk_insert(run_kind=...)
    "scripts/generate_historical_report.py",   # always 'backfill'
    "scripts/backfill_history_tables.py",      # *_history tables, already 'backfill'
    "gcp/migrate_to_gcp.py",                   # one-shot parquet -> Cloud SQL migration
    # The on-demand endpoint generates a report now, for now, and stamps
    # 'live'. Found by this very test on the audit branch: it was writing
    # into insight_reports unlisted, so the row took the default.
    "platform/api/routers/insights.py",
}

_PROV_WRITE = re.compile(
    r"""(?:upsert_dataframe|upsert_rows|bulk_insert_dataframe|bulk_copy_upsert|to_sql)\s*\(.{0,300}?['"](?:public\.)?("""
    + "|".join(PROVENANCE_TABLES) + r""")['"]"""
    r"""|INSERT\s+INTO\s+(?:public\.)?(""" + "|".join(PROVENANCE_TABLES) + r""")\b"""
    r"""|\bCOPY\s+(?:public\.)?(""" + "|".join(PROVENANCE_TABLES) + r""")\b""",
    re.S | re.I,
)


def test_only_sanctioned_code_creates_rows_in_the_provenance_tables():
    offenders = {}
    for p in _py_files(SCAN_ROOTS):
        text = p.read_text(errors="ignore")
        hits = [m.group(0).split("\n")[0] for m in _PROV_WRITE.finditer(text)]
        if hits and _rel(p) not in SANCTIONED_PROVENANCE_WRITERS:
            offenders[_rel(p)] = hits
    assert not offenders, (
        "row-creating writes to premarket_analysis / insight_reports / "
        "historical_signals outside the sanctioned writers, so the row would "
        f"default to run_kind='live' with no one deciding that: {offenders}"
    )


def test_every_sanctioned_provenance_writer_sets_run_kind():
    """A writer on the allowlist that never mentions run_kind is writing rows
    that silently take the 'live' default, which is the defect this closes."""
    missing = [rel for rel in sorted(SANCTIONED_PROVENANCE_WRITERS)
               if (REPO / rel).exists()
               and "run_kind" not in (REPO / rel).read_text(errors="ignore")]
    assert not missing, f"sanctioned writers that never set run_kind: {missing}"


# Readers that must serve only live rows, and the table each reads.
# historical_signals is deliberately absent: it is the analytical corpus,
# not a publication record, and filtering it would discard 91% of the
# history its own statistics summarise. Its provenance is disclosed on the
# row instead (see routers/signals.py).
# Codex round 2 on #1098 found five more, and they are the worse half: the
# first pass filtered the DISPLAY while leaving the TRADING path unfiltered,
# so an INSIGHT_AS_OF / BRIEF_AS_OF replay for today was hidden from the
# dashboard and still drove live fire decisions. Filtering one side of a pair
# is worse than filtering neither, because the operator's view and the
# system's behaviour then disagree silently.
LIVE_ONLY_READERS = {
    "platform/api/routers/dashboard.py": "premarket_analysis",
    "platform/api/routers/insights.py": "insight_reports",
    # The live signal monitor's own adapters.
    "lib/strategies/insight_cache.py": "insight_reports",
    "lib/strategies/brief_bias.py": "premarket_analysis",
    # Annotates the live ladder from the session's published brief.
    "lib/movement_statement.py": "premarket_analysis",
    # A backfill row counting as today's cache would skip live generation
    # while the live-only API cannot serve it: no report at all that day.
    "gcp/auto_refresh_top_n.py": "insight_reports",
    # Publishes to Discord: a replayed report announced as today's is the
    # same misrepresentation as serving it from /api/insights.
    "gcp/insight_discord_push.py": "insight_reports",
}


def test_live_only_readers_filter_on_run_kind():
    unfiltered = {}
    for rel, table in LIVE_ONLY_READERS.items():
        text = (REPO / rel).read_text(errors="ignore")
        reads = len(re.findall(r"FROM\s+" + table + r"\b", text, re.I))
        filters = text.count("run_kind = 'live'")
        if reads and filters == 0:
            unfiltered[rel] = f"{reads} read(s) of {table}, 0 live filters"
    assert not unfiltered, (
        "readers that serve a table as current truth without excluding "
        f"replay/backfill rows: {unfiltered}"
    )


def test_freshness_checks_only_count_live_rows():
    """A replay generated for the expected trading day would otherwise make
    /api/health/freshness report the dataset healthy while the live pipeline
    had failed and every live-only reader had nothing (Codex on #1098).
    signal_alerts already carried this predicate from #820; the two tables
    this PR adds provenance to did not."""
    src = (REPO / "scripts/audit_data_freshness.py").read_text()
    for name in ("premarket_analysis", "insight_reports", "signal_alerts"):
        block = src[src.index(f'"name": "{name}"'):]
        block = block[:block.index("},")]
        assert "run_kind = 'live'" in block, (
            f"freshness check for {name} counts replay/backfill rows as fresh")


def test_every_insight_reports_upsert_carries_run_kind_through_the_conflict():
    """On conflict the SET list must move provenance too. All three writers
    hardcode or derive run_kind on INSERT, which does nothing on an UPDATE:
    a pre-existing 'live' row took backfill content and stayed live. I
    asserted on #1098 that one of these was fine because "EXCLUDED and the
    literal agree"; the literal only applies on INSERT (Codex, round 2)."""
    for rel in ("gcp/insight_pipeline_job.py",
                "platform/api/routers/insights.py",
                "scripts/generate_historical_report.py"):
        src = (REPO / rel).read_text()
        for m in re.finditer(r"ON CONFLICT\s*\([^)]*\)\s*DO UPDATE(.*?)RETURNING",
                             src, re.S | re.I):
            assert "run_kind = EXCLUDED.run_kind" in m.group(1), (
                f"{rel}: a conflict clause replaces the report but not its provenance")


# ── a replay reads bars from the table or says it cannot (FEAT-REPLAY-001) ──
#
# Owner's rule, 2026-11-13: every replay reads 1-minute bars only from
# market_data_intraday. No replay fetches bars from AlphaVantage or anywhere
# else, and none starts the job that does. Nothing listed the replay entry
# points, so no test would have noticed one that starts fetching. This
# section lists them (REPLAY_PATH) and reads their source with `ast`.
#
# What it does not see: a fetch reached through another file by a name it
# cannot resolve, a helper in another file that calls a holder without
# holding the request itself, a request built without a dict literal, the
# parquet and daily-bar fallbacks inside DataLoader for the jobs that read
# through it, a replay CLI whose only date flags are --start and --end, and
# a job started by hand.

REPLAY_ROOTS = ("gcp", "lib", "scripts", "platform/api")
_REPLAY_SKIP_DIRS = {"_archive", "archive", "node_modules", "__pycache__"}
DISCORD_MODULE = "gcp/discord_interactions/main.py"

# file -> the functions a replay enters it through; ("*",) is the whole file.
REPLAY_PATH: dict[str, tuple[str, ...]] = {
    DISCORD_MODULE: (
        "handle_replay", "handle_replay_signals", "handle_validate", "handle_backtest"),
    "platform/api/main.py": ("get_market_data", "get_reference_levels", "_load_date_data"),
    "platform/api/routers/backtest.py": ("replay_trades", "mine_and_validate"),
    "platform/api/routers/insights.py": ("refresh_insight_report",),
    # What the replay harness drives. The live poll (fetch_latest_bar) is outside.
    "gcp/signal_monitor.py": (
        "update_window", "calculate_indicators", "evaluate_ticker",
        "_evaluate_strategies_for_bar", "fire_alert", "refresh_level_map"),
    "scripts/backfill_and_replay.py": ("*",),
    "scripts/replay_signal_monitor.py": ("*",),
    "gcp/signal_replay.py": ("*",),
    "gcp/validate_brief_job.py": ("*",),
    "scripts/validation/validate_brief_accuracy.py": ("*",),
    "gcp/backtest_job.py": ("*",),
    "scripts/run_backtest.py": ("*",),
    "gcp/premarket_brief.py": ("*",),
    "gcp/insight_pipeline_job.py": ("*",),
    "gcp/insight_discord_push.py": ("*",),
    "gcp/earnings_reactions_brief.py": ("*",),
    "gcp/indicator_correlation_job.py": ("*",),
    "gcp/regime_combo_job.py": ("*",),
    "gcp/research/strat_engine/strat_pred_serve.py": ("*",),
    "scripts/analysis/per_ticker_calibration.py": ("*",),
    "scripts/analysis/phase6_playbook.py": ("*",),
    "scripts/calibrate_thresholds.py": ("*",),
    "lib/exec_backtest/cli.py": ("*",),
    "gcp/premarket_playbook_resolver.py": ("*",),
}

# (file, function) -> why a DataLoader use inside it is allowed for now.
REPLAY_EXEMPT: dict[tuple[str, str], str] = {
    ("platform/api/routers/backtest.py", "_style_history_bar_loader"): (
        "the walk-forward history read of mine-and-validate goes through "
        "lib.data_loader.DataLoader until the second spec (FEAT-DATA-001, the "
        "strict bar loader) changes the loader; that spec deletes this entry"),
}

# The jobs the Discord module may start, each with its registered module.
DISCORD_JOBS: dict[str, str] = {
    "premarket-brief": "gcp/premarket_brief.py",
    "insight-pipeline": "gcp/insight_pipeline_job.py",
    "insight-discord-push": "gcp/insight_discord_push.py",
    "signal-replay": "gcp/signal_replay.py",
    "validate-brief": "gcp/validate_brief_job.py",
    "backtest": "gcp/backtest_job.py",
}

LOCAL_DEV_FUNCS = ("_bars_from_gcs_local_dev", "_reference_from_gcs_local_dev")
BAR_LOADERS = ("_load_date_data", "_replay_bar_loader", "_style_history_bar_loader")
REPLAY_FLAG = re.compile(
    r"REPLAY|AS_OF|--as-of|--replay|BACKTEST_|VALIDATE_(?:TICKER|DATE)|PLAYBOOK_RESOLVE_DATE")

_FUNC = (ast.FunctionDef, ast.AsyncFunctionDef)


@functools.lru_cache(maxsize=None)
def _replay_sources() -> dict[str, str]:
    """Repo-relative path -> text of every .py under the four roots."""
    out: dict[str, str] = {}
    for root in REPLAY_ROOTS:
        for p in sorted((REPO / root).rglob("*.py")):
            if _REPLAY_SKIP_DIRS.isdisjoint(p.relative_to(REPO).parts):
                out[_rel(p)] = p.read_text(encoding="utf-8", errors="ignore")
    return out


@functools.lru_cache(maxsize=None)
def _replay_tree(src: str) -> ast.Module:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(src)


def _functions_by_name(tree: ast.AST) -> dict[str, list[ast.AST]]:
    """Every function in the file by name: nested functions and methods too."""
    out: dict[str, list[ast.AST]] = {}
    for n in ast.walk(tree):
        if isinstance(n, _FUNC):
            out.setdefault(n.name, []).append(n)
    return out


def _defined_functions(src: str) -> set[str]:
    return set(_functions_by_name(_replay_tree(src)))


def _outermost_function(tree: ast.AST) -> dict[int, str]:
    """id(node) -> name of its outermost enclosing function, or '<module>'.
    A nested function counts as the function it sits in."""
    owner: dict[int, str] = {}

    def visit(node: ast.AST, outer: str) -> None:
        for child in ast.iter_child_nodes(node):
            scope = child.name if outer == "<module>" and isinstance(child, _FUNC) else outer
            owner[id(child)] = scope
            visit(child, scope)

    visit(tree, "<module>")
    return owner


def _lexically_inside(tree: ast.AST, names) -> set[int]:
    """ids of every node inside a function with one of these names."""
    inside: set[int] = set()
    for n in ast.walk(tree):
        if isinstance(n, _FUNC) and n.name in names:
            inside.update(id(x) for x in ast.walk(n))
    return inside


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """A docstring is the first statement of a module, class or function."""
    ids: set[int] = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, *_FUNC)) and n.body:
            first = n.body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                ids.add(id(first.value))
    return ids


def _vendor_requests(node: ast.AST) -> list[ast.AST]:
    """The AlphaVantage bar requests in a node: a dict whose "function" value
    starts with TIME_SERIES_, or a string that holds function=TIME_SERIES_."""
    found: list[ast.AST] = []
    for n in ast.walk(node):
        if isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if (isinstance(k, ast.Constant) and k.value == "function"
                        and isinstance(v, ast.Constant) and isinstance(v.value, str)
                        and v.value.startswith("TIME_SERIES_")):
                    found.append(v)
        elif (isinstance(n, ast.Constant) and isinstance(n.value, str)
              and "function=TIME_SERIES_" in n.value):
            found.append(n)
    return found


def vendor_holders(sources: dict[str, str]) -> set[str]:
    """The name of every function whose own body holds a vendor request.
    Only those names. A function that only calls a holder is not added:
    inside a registered file the in-file reach already follows it, and
    matched by name across files it would flag every `run` and `main`."""
    names: set[str] = set()
    for src in sources.values():
        try:
            tree = _replay_tree(src)
        except SyntaxError:
            continue
        for name, nodes in _functions_by_name(tree).items():
            if any(_vendor_requests(nd) for nd in nodes):
                names.add(name)
    return names


def _call_name(call: ast.Call) -> str | None:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _reached(tree: ast.AST, entries: tuple[str, ...]) -> set[str]:
    """Names of the functions of this file reachable from the entries: a
    function is reached when its name appears, as a name or as an attribute,
    inside a reached function."""
    funcs = _functions_by_name(tree)
    seen: set[str] = set()
    todo = [e for e in entries if e in funcs]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        for nd in funcs[name]:
            for n in ast.walk(nd):
                ref = n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute) else None
                if ref in funcs and ref not in seen:
                    todo.append(ref)
    return seen


def replay_reach_offenders(rel: str, src: str, entries: tuple[str, ...],
                           holders: set[str], exempt: dict) -> list[str]:
    """What the replay path of one file must not hold, as
    '{rel}:{line} in {function}: {reason}', each line and reason once."""
    tree = _replay_tree(src)
    funcs = _functions_by_name(tree)
    owner = _outermost_function(tree)
    docstrings = _docstring_nodes(tree)
    in_local_dev = _lexically_inside(tree, LOCAL_DEV_FUNCS)
    in_exempt = _lexically_inside(tree, {fn for (f, fn) in exempt if f == rel})
    under_api = rel.startswith("platform/api/")

    found: dict[tuple[int, str], str] = {}

    def flag(node: ast.AST, reason: str) -> None:
        found.setdefault((node.lineno, reason), owner.get(id(node), "<module>"))

    if tuple(entries) == ("*",):
        scopes = [tree]
    else:
        scopes = [nd for name in sorted(_reached(tree, entries)) for nd in funcs[name]]

    for scope in scopes:
        for node in _vendor_requests(scope):
            flag(node, "holds an AlphaVantage TIME_SERIES request")
        for n in ast.walk(scope):
            if isinstance(n, ast.Call) and _call_name(n) in holders:
                flag(n, f"calls {_call_name(n)}, a function that holds an AlphaVantage TIME_SERIES request")
            if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                    and n.value.id == "gcs_reader" and id(n) not in in_local_dev):
                flag(n, f"reads the bucket through gcs_reader.{n.attr} outside the local-dev functions")
            if (isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and "backfill-ticker" in n.value and id(n) not in docstrings):
                flag(n, "names the backfill-ticker job in a string")
            if under_api and id(n) not in in_exempt and (
                    (isinstance(n, ast.Name) and n.id in ("DataLoader", "data_loader"))
                    or (isinstance(n, ast.Attribute) and n.attr == "DataLoader")):
                flag(n, "uses DataLoader outside REPLAY_EXEMPT")

    out = [f"{rel}:{line} in {fn}: {reason}" for (line, reason), fn in sorted(found.items())]
    out += [f"{rel}:0 in {e}: the registered entry function is not defined in the file"
            for e in entries if e != "*" and e not in funcs]
    return out


def local_dev_offenders(rel: str, src: str) -> list[str]:
    """Every call of a local-dev bucket function must sit in the body, not
    the else, of an `if` or `elif` whose test is exactly the name
    _CLOUD_SQL_UNCONFIGURED. `not _CLOUD_SQL` is also true after a failed
    import of gcp.database on a deployed revision, which is not local dev."""
    tree = _replay_tree(src)
    owner = _outermost_function(tree)
    guarded: set[int] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.If) and isinstance(n.test, ast.Name) and n.test.id == "_CLOUD_SQL_UNCONFIGURED":
            for stmt in n.body:
                guarded.update(id(x) for x in ast.walk(stmt))
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and _call_name(n) in LOCAL_DEV_FUNCS and id(n) not in guarded:
            out.add((n.lineno, f"{rel}:{n.lineno} in {owner.get(id(n), '<module>')}: "
                               f"{_call_name(n)} is called outside 'if _CLOUD_SQL_UNCONFIGURED:'"))
    return [text for _line, text in sorted(out)]


def _replay_flag_hits(tree: ast.AST) -> list[tuple[int, str]]:
    """(line, value) of each env var name read through os.environ.get,
    os.getenv or os.environ[...], and each add_argument string, that
    matches REPLAY_FLAG."""
    hits: list[tuple[int, str]] = []
    for n in ast.walk(tree):
        candidates: list[ast.AST] = []
        if isinstance(n, ast.Call):
            called = ast.unparse(n.func)
            if called.endswith("environ.get") or called.endswith("getenv"):
                candidates = list(n.args[:1])
            elif isinstance(n.func, ast.Attribute) and n.func.attr == "add_argument":
                candidates = list(n.args)
        elif isinstance(n, ast.Subscript) and ast.unparse(n.value).endswith("environ"):
            candidates = [n.slice]
        for a in candidates:
            if isinstance(a, ast.Constant) and isinstance(a.value, str) and REPLAY_FLAG.search(a.value):
                hits.append((a.lineno, a.value))
    return sorted(hits)


def replay_flag_files(sources: dict[str, str]) -> dict[str, list[tuple[int, str]]]:
    out: dict[str, list[tuple[int, str]]] = {}
    for rel, src in sources.items():
        try:
            hits = _replay_flag_hits(_replay_tree(src))
        except SyntaxError:
            continue
        if hits:
            out[rel] = hits
    return out


def registration_offenders(sources: dict[str, str], replay_path: dict, discord_jobs: dict) -> list[str]:
    """Replay entry points that nobody registered."""
    out: set[str] = set()

    # 1. who dispatches a job from Discord, and which job
    if DISCORD_MODULE not in sources:
        out.add(f"{DISCORD_MODULE}: the Discord module is not among the sources")
    else:
        tree = _replay_tree(sources[DISCORD_MODULE])
        owner = _outermost_function(tree)
        handlers = set(replay_path.get(DISCORD_MODULE, ()))
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and _call_name(n) == "execute_cloud_run_job"):
                continue
            where = f"{DISCORD_MODULE}:{n.lineno} in {owner.get(id(n), '<module>')}"
            if owner.get(id(n), "<module>") not in handlers:
                out.add(f"{where}: dispatches a job and is not a registered entry of REPLAY_PATH")
            job = n.args[0] if n.args else None
            if not (isinstance(job, ast.Constant) and isinstance(job.value, str)):
                out.add(f"{where}: the job name is not a string literal")
            elif job.value not in discord_jobs:
                out.add(f"{where}: the job {job.value!r} is not in DISCORD_JOBS")
    for job, module in discord_jobs.items():
        if module not in replay_path:
            out.add(f"DISCORD_JOBS[{job!r}]: {module} is not in REPLAY_PATH")

    # 2. a replay-shaped env var or flag in a file REPLAY_PATH does not list
    for rel, hits in replay_flag_files(sources).items():
        if rel not in replay_path:
            names = sorted({value for _line, value in hits})
            out.add(f"{rel}:{hits[0][0]}: reads or declares {names} and is not in REPLAY_PATH")

    # 3. under platform/api, who calls a bar loader or starts an as-of insight run
    for rel, src in sources.items():
        if not rel.startswith("platform/api/"):
            continue
        try:
            tree = _replay_tree(src)
        except SyntaxError:
            continue
        owner = _outermost_function(tree)
        reached = _reached(tree, replay_path[rel]) if rel in replay_path else set()
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            name = _call_name(n)
            if name in BAR_LOADERS:
                what = name
            elif name == "enqueue_insight_task" and any(k.arg == "as_of_iso" for k in n.keywords):
                what = "enqueue_insight_task(as_of_iso=...)"
            else:
                continue
            fn = owner.get(id(n), "<module>")
            if fn not in reached:
                out.add(f"{rel}:{n.lineno} in {fn}: calls {what} and is not reachable "
                        f"from a registered entry of REPLAY_PATH")
    return sorted(out)


# The guard's own tests. Each row below is a small source text checked as
# the named file, so the rules are pinned on rewrites and not only on
# today's tree: "flag" means at least one offender, "clean" means none.

_DISCORD_OK = '''
def execute_cloud_run_job(name, env): return True
def handle_replay(t, d):
    execute_cloud_run_job("premarket-brief", {})
    execute_cloud_run_job("insight-pipeline", {})
    execute_cloud_run_job("insight-discord-push", {})
def handle_replay_signals(): execute_cloud_run_job("signal-replay", {})
def handle_validate(): execute_cloud_run_job("validate-brief", {})
def handle_backtest(): execute_cloud_run_job("backtest", {})
'''
_DISCORD_NESTED = '''
def execute_cloud_run_job(name, env): return True
def handle_replay(t, d):
    def _go():
        execute_cloud_run_job("premarket-brief", {})
    _go()
def handle_replay_signals(): execute_cloud_run_job("signal-replay", {})
def handle_validate(): execute_cloud_run_job("validate-brief", {})
def handle_backtest(): execute_cloud_run_job("backtest", {})
'''
_API_MAIN = "platform/api/main.py"
_API_BACKTEST = "platform/api/routers/backtest.py"
_API_INSIGHTS = "platform/api/routers/insights.py"
_API_ENTRIES_OK = '''
def get_market_data(t, d): return _load_date_data(t, d)
def get_reference_levels(t, d): return 1
def _load_date_data(t, d): return 1
'''
_STYLE_ONLY = '''
def mine_and_validate(b): return _style_history_bar_loader("SPY")
def _style_history_bar_loader(t):
    from lib.data_loader import DataLoader
    return DataLoader().load_best_available(t, "a", "b")
'''


def _reg(extra=None, discord=_DISCORD_OK):
    sources = {"gcp/discord_interactions/main.py": discord, **(extra or {})}
    return registration_offenders(sources, REPLAY_PATH, DISCORD_JOBS)


def _reach(rel, src, entries, holders=frozenset({"fetch_month"}), exempt=None):
    return replay_reach_offenders(
        rel, src, entries, set(holders), REPLAY_EXEMPT if exempt is None else exempt)


def _new_job(line):
    return lambda: _reg({"gcp/new_job.py": f"import os, argparse\np = argparse.ArgumentParser()\n{line}\n"})


def _stray_loader(loader):
    return lambda: _reg({_API_MAIN: _API_ENTRIES_OK + f"def export_csv(t, d): return {loader}(t, d)\n"})


# (name, how to get the offenders, flag expected, text an offender must hold)
_REPLAY_REWRITES = [
    # registration: who may dispatch a job from Discord, and which job
    ("discord: four handlers, six jobs", lambda: _reg(), False, None),
    ("discord: a fifth handler dispatches",
     lambda: _reg(discord=_DISCORD_OK + 'def handle_earnings(): execute_cloud_run_job("backtest", {})\n'),
     True, "handle_earnings"),
    ("discord: an unregistered job name",
     lambda: _reg(discord=_DISCORD_OK.replace('"validate-brief"', '"backfill-ticker"')),
     True, "backfill-ticker"),
    ("discord: a job name in a variable",
     lambda: _reg(discord=_DISCORD_OK.replace('execute_cloud_run_job("backtest", {})',
                                              'execute_cloud_run_job(JOB, {})')),
     True, None),
    ("discord: a dispatch at module level",
     lambda: _reg(discord=_DISCORD_OK + 'execute_cloud_run_job("backtest", {})\n'),
     True, "<module>"),
    ("discord: a dispatch from a nested function of a handler",
     lambda: _reg(discord=_DISCORD_NESTED), False, None),
    # registration: a replay-shaped env var or flag in a file nobody listed
    ("new file: env MY_REPLAY_DAY", _new_job('x = os.environ.get("MY_REPLAY_DAY")'), True, "gcp/new_job.py"),
    ("new file: env NEWJOB_AS_OF", _new_job('x = os.getenv("NEWJOB_AS_OF")'), True, "gcp/new_job.py"),
    ("new file: flag --as-of", _new_job('p.add_argument("--as-of")'), True, "gcp/new_job.py"),
    ("new file: flag --replay-date", _new_job('p.add_argument("--replay-date")'), True, "gcp/new_job.py"),
    ("new file: env BACKTEST_WINDOW", _new_job('x = os.environ["BACKTEST_WINDOW"]'), True, "gcp/new_job.py"),
    ("new file: env VALIDATE_TICKER", _new_job('x = os.environ.get("VALIDATE_TICKER")'), True, "gcp/new_job.py"),
    ("new file: env VALIDATE_DATE", _new_job('x = os.environ.get("VALIDATE_DATE")'), True, "gcp/new_job.py"),
    ("new file: env PLAYBOOK_RESOLVE_DATE",
     _new_job('x = os.environ.get("PLAYBOOK_RESOLVE_DATE")'), True, "gcp/new_job.py"),
    ("new file: env DB_USER", _new_job('x = os.environ.get("DB_USER")'), False, None),
    # registration: who may call a bar loader under platform/api
    ("api: an unreached function calls _load_date_data", _stray_loader("_load_date_data"), True, "export_csv"),
    ("api: an unreached function calls _replay_bar_loader",
     _stray_loader("_replay_bar_loader"), True, "export_csv"),
    ("api: an unreached function calls _style_history_bar_loader",
     _stray_loader("_style_history_bar_loader"), True, "export_csv"),
    ("api: a bar loader called at module level",
     lambda: _reg({_API_MAIN: _API_ENTRIES_OK + 'WARM = _load_date_data("spy", "20260220")\n'}),
     True, "<module>"),
    ("api: a bar loader called from a nested function of an entry",
     lambda: _reg({_API_MAIN: '''
def get_market_data(t, d):
    def _inner():
        return _load_date_data(t, d)
    return _inner()
def get_reference_levels(t, d): return 1
def _load_date_data(t, d): return 1
'''}), False, None),
    ("api: the local-dev reference helper calls _load_date_data",
     lambda: _reg({_API_MAIN: '''
def get_market_data(t, d): return _load_date_data(t, d)
def get_reference_levels(t, d):
    if _CLOUD_SQL_UNCONFIGURED:
        return _reference_from_gcs_local_dev(t, d)
def _reference_from_gcs_local_dev(t, d): return _load_date_data(t, d)
def _load_date_data(t, d): return 1
'''}), False, None),
    ("api: a second function passes as_of_iso",
     lambda: _reg({_API_INSIGHTS: '''
def refresh_insight_report(t, as_of=None): enqueue_insight_task(1, t, as_of_iso=as_of)
def bulk_refresh(ts, as_of): return [enqueue_insight_task(1, t, as_of_iso=as_of) for t in ts]
'''}), True, "bulk_refresh"),
    ("api: a second function enqueues without as_of_iso",
     lambda: _reg({_API_INSIGHTS: '''
def refresh_insight_report(t, as_of=None): enqueue_insight_task(1, t, as_of_iso=as_of)
def nightly(ts): return [enqueue_insight_task(1, t) for t in ts]
'''}), False, None),
    # reach: a vendor request, or a call of a function that holds one
    ("reach: a TIME_SERIES_DAILY dict in a helper an entry calls",
     lambda: _reach(_API_MAIN, '''
def get_reference_levels(t, d): return _latest(t)
def _latest(t): return client.get(URL, params={"function": "TIME_SERIES_DAILY", "symbol": t})
''', ("get_reference_levels",)), True, "_latest"),
    ("reach: function=TIME_SERIES_ in a URL string",
     lambda: _reach(_API_MAIN, '''
def get_reference_levels(t, d): return get(f"https://x/query?function=TIME_SERIES_DAILY&symbol={t}")
''', ("get_reference_levels",)), True, None),
    ("reach: a call of a holder defined in another file",
     lambda: _reach("gcp/discord_interactions/main.py", '''
def handle_replay(t, d):
    from gcp.fetchers import fetch_alphavantage_intraday as f
    return f.fetch_month(t, d)
''', ("handle_replay",)), True, "fetch_month"),
    ("reach: a TIME_SERIES_INTRADAY dict no entry reaches",
     lambda: _reach(_API_MAIN, '''
def get_reference_levels(t, d): return 1
def live_quote(t): return client.get(URL, params={"function": "TIME_SERIES_INTRADAY"})
''', ("get_reference_levels",)), False, None),
    # reach: the bucket
    ("reach: gcs_reader in _load_date_data",
     lambda: _reach(_API_MAIN, '''
def _load_date_data(t, d):
    if gcs_reader.blob_exists(d):
        return 1
''', ("_load_date_data",)), True, "gcs_reader.blob_exists"),
    ("reach: gcs_reader inside a local-dev function",
     lambda: _reach(_API_MAIN, '''
def _load_date_data(t, d):
    if _CLOUD_SQL_UNCONFIGURED:
        return _bars_from_gcs_local_dev(t, d)
def _bars_from_gcs_local_dev(t, d):
    from api import gcs_reader
    return gcs_reader.download_parquet(d)
''', ("_load_date_data",)), False, None),
    # reach: DataLoader under platform/api
    ("reach: DataLoader in a second reached function",
     lambda: _reach(_API_BACKTEST, '''
def mine_and_validate(b): return _style_history_bar_loader("SPY"), _other("SPY")
def _style_history_bar_loader(t):
    from lib.data_loader import DataLoader
    return DataLoader().load_best_available(t, "a", "b")
def _other(t):
    from lib.data_loader import DataLoader
    return DataLoader().load_daily(t)
''', ("mine_and_validate",)), True, "_other"),
    ("reach: the module-level data_loader",
     lambda: _reach(_API_MAIN, '''
def get_market_data(t, d): return data_loader.load_intraday(t)
''', ("get_market_data",)), True, "get_market_data"),
    ("reach: only the exempt function holds DataLoader",
     lambda: _reach(_API_BACKTEST, _STYLE_ONLY, ("mine_and_validate",)), False, None),
    ("reach: the exempt function with the exemption emptied",
     lambda: _reach(_API_BACKTEST, _STYLE_ONLY, ("mine_and_validate",), exempt={}),
     True, "_style_history_bar_loader"),
    ("reach: DataLoader outside platform/api",
     lambda: _reach("gcp/backtest_job.py", '''
from lib.data_loader import DataLoader
def main(): return DataLoader().load_best_available("SPY", "a", "b")
''', ("*",)), False, None),
    # reach: the backfill job by name
    ("reach: the backfill job dispatched by the script",
     lambda: _reach("scripts/backfill_and_replay.py", '''
def main(): _execute_job('backfill-ticker', {})
''', ("*",)), True, "backfill-ticker"),
    ("reach: backfill-ticker in a log line",
     lambda: _reach("gcp/discord_interactions/main.py", '''
def handle_replay(t, d): logger.info("run backfill-ticker by hand for %s", t)
''', ("handle_replay",)), True, "backfill-ticker"),
    ("reach: backfill-ticker only in docstrings and a comment",
     lambda: _reach("scripts/backfill_and_replay.py", '''"""This script no longer runs backfill-ticker."""
def main():
    """Does not start backfill-ticker."""
    # backfill-ticker is gone
    return 0
''', ("*",)), False, None),
    ("reach: an entry the file does not define",
     lambda: _reach(_API_MAIN, "def other(): pass\n", ("get_market_data",)), True, "get_market_data"),
    # local dev: the bucket only behind the unconfigured flag
    ("local dev: under 'if not _CLOUD_SQL'",
     lambda: local_dev_offenders(_API_MAIN, '''
def _load_date_data(t, d):
    if not _CLOUD_SQL:
        return _bars_from_gcs_local_dev(t, d)
'''), True, "_bars_from_gcs_local_dev"),
    ("local dev: under no branch",
     lambda: local_dev_offenders(_API_MAIN, '''
def get_reference_levels(t, d):
    return _reference_from_gcs_local_dev(t, d)
'''), True, "_reference_from_gcs_local_dev"),
    ("local dev: in the else of the flag",
     lambda: local_dev_offenders(_API_MAIN, '''
def _load_date_data(t, d):
    if _CLOUD_SQL_UNCONFIGURED:
        pass
    else:
        return _bars_from_gcs_local_dev(t, d)
'''), True, None),
    ("local dev: under a compound test",
     lambda: local_dev_offenders(_API_MAIN, '''
def _load_date_data(t, d):
    if _CLOUD_SQL_UNCONFIGURED or FORCE:
        return _bars_from_gcs_local_dev(t, d)
'''), True, None),
    ("local dev: under if and elif of the flag",
     lambda: local_dev_offenders(_API_MAIN, '''
def _load_date_data(t, d):
    if _CLOUD_SQL:
        return 1
    elif _CLOUD_SQL_UNCONFIGURED:
        return _bars_from_gcs_local_dev(t, d)
def get_reference_levels(t, d):
    if _CLOUD_SQL_UNCONFIGURED:
        return _reference_from_gcs_local_dev(t, d)
'''), False, None),
]


@pytest.mark.parametrize(
    "offenders_of, flagged, names", [r[1:] for r in _REPLAY_REWRITES],
    ids=[r[0] for r in _REPLAY_REWRITES])
def test_the_replay_guard_catches_the_obvious_rewrites(offenders_of, flagged, names):
    """A guard that the guarded code's most obvious rewrite walks past is
    not a guard. What it cannot see is listed in the spec (Design 8): a
    fetch reached through another file by a name it cannot resolve, and a
    request built without a dict literal or the URL text."""
    offenders = offenders_of()
    assert bool(offenders) is flagged, offenders
    if names is not None:
        assert any(names in o for o in offenders), offenders


def test_every_replay_entry_point_is_registered():
    """Nothing listed the replay entry points, so nothing would notice one
    that starts fetching. A new Discord dispatcher, a new job name, a new
    replay-shaped env var or flag, or a new caller of a bar loader fails
    here until it is added to REPLAY_PATH, where the reach test reads it."""
    sources = _replay_sources()
    assert registration_offenders(sources, REPLAY_PATH, DISCORD_JOBS) == []

    for rel, entries in REPLAY_PATH.items():
        assert rel in sources, f"{rel} is registered and is not a file under the scanned roots"
        defined = _defined_functions(sources[rel])
        missing = [e for e in entries if e != "*" and e not in defined]
        assert missing == [], f"{rel} does not define {missing}"

    # an empty walk must not pass
    flag_files = replay_flag_files(sources)
    assert len(flag_files) >= 16, flag_files
    assert len(vendor_holders(sources)) >= 15, sorted(vendor_holders(sources))
    assert set(DISCORD_JOBS) == {
        "premarket-brief", "insight-pipeline", "insight-discord-push",
        "signal-replay", "validate-brief", "backtest",
    }


# The three tests that hold today's tree to the rule.

def test_replay_paths_reach_no_vendor_or_bucket_bar_fetch():
    """From every registered replay entry point, nothing reachable inside
    its file holds an AlphaVantage TIME_SERIES request, calls a function
    that holds one, reads the bucket outside the two local-dev functions,
    names the backfill-ticker job in a string, or (under platform/api) uses
    DataLoader outside REPLAY_EXEMPT.

    Before FEAT-REPLAY-001 this failed at eleven places: Discord /replay and
    scripts/backfill_and_replay.py dispatched backfill-ticker, the reference
    route called AlphaVantage and listed the bucket, and the bar loader fell
    through to bucket parquet."""
    sources = _replay_sources()
    holders = vendor_holders(sources)
    offenders = [
        o for rel, entries in REPLAY_PATH.items()
        for o in replay_reach_offenders(rel, sources[rel], entries, holders, REPLAY_EXEMPT)
    ]
    assert offenders == [], (
        "a replay path fetches bars, or can start the job that does:\n  "
        + "\n  ".join(offenders))


def test_local_dev_bucket_reads_sit_behind_the_unconfigured_check():
    """The bucket is read for bars only when Cloud SQL is known to be not
    configured. The API tests prove the same at run time."""
    sources = _replay_sources()
    api_files = {rel: src for rel, src in sources.items() if rel.startswith("platform/api/")}
    offenders = [o for rel, src in api_files.items() for o in local_dev_offenders(rel, src)]
    assert offenders == [], "\n  ".join(offenders)

    # A tree without the two functions, or without a call of them, must not pass.
    called = {
        _call_name(n)
        for src in api_files.values()
        for n in ast.walk(_replay_tree(src))
        if isinstance(n, ast.Call)
    }
    assert set(LOCAL_DEV_FUNCS) <= called, sorted(set(LOCAL_DEV_FUNCS) - called)
    defined = _defined_functions(sources["platform/api/main.py"])
    assert set(LOCAL_DEV_FUNCS) <= defined, sorted(set(LOCAL_DEV_FUNCS) - defined)


def test_the_only_replay_exemption_is_the_style_history_loader():
    """One exemption, pinned from every side, so it cannot grow and cannot
    outlive the call it is for: the second spec (the strict bar loader) has
    to delete the entry when it changes `_style_history_bar_loader`."""
    rel, fn = "platform/api/routers/backtest.py", "_style_history_bar_loader"
    assert list(REPLAY_EXEMPT) == [(rel, fn)]

    sources = _replay_sources()
    src = sources[rel]
    tree = _replay_tree(src)
    nodes = _functions_by_name(tree).get(fn)
    assert nodes, f"{rel} no longer defines {fn}: delete the exemption"

    # reached from mine_and_validate, and from no other registered entry
    assert fn in _reached(tree, ("mine_and_validate",))
    others = tuple(e for e in REPLAY_PATH[rel] if e != "mine_and_validate")
    assert others, "the file's other registered entries"
    assert fn not in _reached(tree, others)

    # it still holds the call the exemption is for
    assert any(isinstance(n, ast.Call) and _call_name(n) == "DataLoader"
               for nd in nodes for n in ast.walk(nd)), (
        f"{fn} no longer calls DataLoader: delete the exemption")

    # and with the exemption emptied the reach test fails, naming it alone
    exposed = replay_reach_offenders(rel, src, REPLAY_PATH[rel], vendor_holders(sources), {})
    assert exposed, "emptying REPLAY_EXEMPT changes nothing: the exemption is dead"
    assert all(f" in {fn}: " in o for o in exposed), exposed
