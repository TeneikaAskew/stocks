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
