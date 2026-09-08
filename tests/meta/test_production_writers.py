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

import re
from pathlib import Path

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
