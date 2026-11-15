"""What the two bar recompute tools share (FEAT-DATA-001).

The end-of-day resolver's ``--re-resolve`` rewrites resolver-written exits of
``signal_alerts`` and ``trades``; the daily fetcher's ``--recompute-premarket``
rewrites the premarket columns of ``market_data_daily``. Both follow one
contract, and this module is that contract, so neither entry point holds a
copy the other could drift from:

- run identity and the code version a run records;
- proof before placement: a window of stored 1-minute bars is used only when
  every row in it is proven a true UTC instant;
- the write decision: which columns are compared, and when a row is written;
- the report (``rows.csv`` and ``summary.json``) and the exit code.

Spec: docs/superpowers/specs/2026-11-14-feat-data-001-recompute-after-bar-rewrite.md
(Design 2 and Design 7).

Nothing here returns an empty container or a default on failure (CLAUDE.md
3.7): a failed read, a failed upload and a value of an unknown kind all raise.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from lib.eastern_time import (
    as_utc_instant,
    localize_assuming_utc,
    proven_true_utc,
    utc_now,
)

ALLOWED_TICKERS = ("SPY", "QQQ", "IWM")

TARGET_EXITS = "signal-alert-exits"
TARGET_PREMARKET = "daily-premarket"

#: A row with one of these statuses was refused or left: the run exits 1.
REFUSED_STATUSES = (
    "unproven_rows",
    "no_bars",
    "bars_incomplete",
    "fired_after_close",
    "daily_incomplete",
    "changed_underneath",
    "trade_diverged",
)

#: Written into every image by gcp/deploy.sh (_stamp_build_info).
BUILD_INFO_PATH = Path(__file__).resolve().parent / "build_info.json"

REPORT_PREFIX = "bar-recompute/v1"

_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class Refusal(Exception):
    """The run is refused before any query or write. ``str(e)`` is the one-line
    reason; an entry point logs it and returns 2."""


class UnprovenRows(Exception):
    """A window of bars holds a row that is not proven a true UTC instant."""

    def __init__(self, unproven: int, rows: int):
        super().__init__(f"{unproven} of {rows} rows are not proven true UTC")
        self.unproven = unproven
        self.rows = rows


# ── run identity ──────────────────────────────────────────────────────


def run_id() -> str:
    """The Cloud Run execution name in a job, else ``local-<UTC timestamp>``.

    A retry of an execution keeps its name, so it keeps its run id and its
    report paths.
    """
    execution = os.environ.get("CLOUD_RUN_EXECUTION", "").strip()
    if execution:
        return execution
    return "local-" + utc_now().strftime("%Y%m%dT%H%M%SZ")


def code_version() -> dict:
    """The image's build stamp: git commit, dirty flag and build time.

    A run outside an image has no stamp and records three nulls. A stamp that
    exists and cannot be read raises.
    """
    if not BUILD_INFO_PATH.exists():
        return {"git_commit": None, "git_dirty": None, "built_at": None}
    stamp = json.loads(BUILD_INFO_PATH.read_text())
    return {
        "git_commit": stamp["git_commit"],
        "git_dirty": stamp["git_dirty"],
        "built_at": stamp["built_at"],
    }


# ── the window ────────────────────────────────────────────────────────


def _parse_day(text: str | None, flag: str) -> date:
    if not text:
        raise Refusal(f"{flag} is required (YYYY-MM-DD)")
    if not _ISO_DATE.fullmatch(text):
        raise Refusal(f"{flag} {text!r} is not a date as YYYY-MM-DD")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise Refusal(f"{flag} {text!r} is not a date: {exc}") from exc


def parse_window(tickers: str | None, first: str | None, last: str | None,
                 today: date) -> tuple[list[str], date, date]:
    """The tickers and the date window of a run, or a ``Refusal``.

    *tickers* is one space-separated value; ``None`` or ``ALL`` means SPY, QQQ
    and IWM, which is also the whole set allowed. The window is inclusive and
    must end before *today*, the exchange's date: today's rows belong to the
    scheduled path.
    """
    if tickers is None or tickers.strip().upper() == "ALL":
        chosen = list(ALLOWED_TICKERS)
    else:
        if "," in tickers:
            raise Refusal(
                f"--tickers {tickers!r} holds a comma; it is one space-separated value")
        chosen = []
        for name in tickers.upper().split():
            if name not in ALLOWED_TICKERS:
                raise Refusal(
                    f"--tickers names {name}; only {', '.join(ALLOWED_TICKERS)} "
                    "can be recomputed")
            if name not in chosen:
                chosen.append(name)
        if not chosen:
            raise Refusal("--tickers is empty")
    first_day = _parse_day(first, "--from")
    last_day = _parse_day(last, "--to")
    if first_day > last_day:
        raise Refusal(f"--from {first_day} is after --to {last_day}")
    if last_day >= today:
        raise Refusal(
            f"--to {last_day} reaches today's Eastern date {today}; "
            "today's rows belong to the scheduled path")
    return chosen, first_day, last_day


# ── proof before placement ────────────────────────────────────────────


def require_proven(ts, inserted_at) -> None:
    """Raise ``UnprovenRows`` unless every row is proven a true UTC instant.

    Proof is ``lib.eastern_time.proven_true_utc``: a fact about when the row
    was written. Nothing is inferred from the shape of the window, and there is
    no override.
    """
    proven = proven_true_utc(ts, inserted_at)
    unproven = int((~proven).sum())
    if unproven:
        raise UnprovenRows(unproven, len(proven))


def _is_null(value) -> bool:
    if value is None or value is pd.NaT or value is pd.NA:
        return True
    return isinstance(value, float) and math.isnan(value)


def _instant(value) -> datetime:
    """An aware UTC datetime for a stored time. A naive value is UTC."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if not isinstance(value, datetime):
        raise TypeError(f"not a time: {value!r}")
    if value.tzinfo is None:
        return localize_assuming_utc(value)
    return as_utc_instant(value)


def _time_text(value) -> str:
    return _instant(value).strftime(_TIME_FORMAT) + "+00:00"


def bars_basis(bars: pd.DataFrame) -> dict:
    """What a ledger row records about the bars a value rests on.

    The digest is over one line a row in ``ts`` order, joined by a newline,
    UTF-8: the instant to the microsecond, the ``repr`` of open, high, low and
    close, and the volume as an integer (empty when NULL).
    """
    ordered = bars.sort_values("ts", kind="stable")
    lines = []
    for row in ordered.itertuples(index=False):
        volume = "" if _is_null(row.volume) else str(int(row.volume))
        lines.append("|".join([
            _time_text(row.ts),
            repr(float(row.open)), repr(float(row.high)),
            repr(float(row.low)), repr(float(row.close)),
            volume,
        ]))
    inserted = [v for v in ordered["inserted_at"] if not _is_null(v)]
    return {
        "rows": len(ordered),
        "first_ts": _time_text(ordered["ts"].iloc[0]) if len(ordered) else None,
        "last_ts": _time_text(ordered["ts"].iloc[-1]) if len(ordered) else None,
        "inserted_min": _time_text(min(inserted)) if inserted else None,
        "inserted_max": _time_text(max(inserted)) if inserted else None,
        "sha256": hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest(),
    }


# ── values ────────────────────────────────────────────────────────────


def db_value(value, sqltype: str):
    """What is bound to a statement for a column of *sqltype*.

    A column that is NULL on one row and set on another comes back from pandas
    as ``NaN`` in a float column, an integer beside it as a float, and a time
    as ``NaT``: none of those can be sent as they are.
    """
    if _is_null(value):
        return None
    if sqltype in ("bigint", "integer"):
        number = float(value)
        if not number.is_integer():
            raise ValueError(f"{value!r} is not a whole number for {sqltype}")
        return int(number)
    if sqltype == "double precision":
        return float(value)
    if sqltype == "timestamptz":
        return _instant(value)
    if sqltype == "date":
        if isinstance(value, str):
            return date.fromisoformat(value)
        if isinstance(value, datetime):
            raise ValueError(f"{value!r} is a time, not a date")
        return value
    if sqltype == "jsonb":
        if isinstance(value, str):
            return value
        return json.dumps(value, sort_keys=True, allow_nan=False)
    if sqltype in ("varchar", "text"):
        return str(value)
    raise ValueError(f"no binding for SQL type {sqltype!r}")


def json_value(value):
    """What the ledger and the CSV hold for a value.

    A float stays a JSON number (``json.dumps`` writes the shortest text that
    reads back to the same float), a time is UTC text to the microsecond, a
    date is ISO, and a JSON document is its text with sorted keys.
    """
    if _is_null(value):
        return None
    if isinstance(value, (bool,)):
        return value
    if hasattr(value, "item") and not isinstance(value, (pd.Timestamp, datetime)):
        value = value.item()  # a numpy scalar
        if _is_null(value):
            return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (pd.Timestamp, datetime)):
        return _time_text(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, allow_nan=False)
    raise TypeError(f"no ledger form for {type(value).__name__}: {value!r}")


def _is_time(value) -> bool:
    return isinstance(value, (pd.Timestamp, datetime))


def same(a, b) -> bool:
    """Exact, NULL-safe equality. No tolerance.

    Two times compare as instants. Two JSON documents, one of them read from
    the database as text, compare after ``json.loads``.
    """
    if _is_null(a) or _is_null(b):
        return _is_null(a) and _is_null(b)
    if _is_time(a) or _is_time(b):
        return _instant(a) == _instant(b)
    if isinstance(a, (dict, list)) or isinstance(b, (dict, list)):
        left = json.loads(a) if isinstance(a, str) else a
        right = json.loads(b) if isinstance(b, str) else b
        return left == right
    if isinstance(a, str) or isinstance(b, str):
        return isinstance(a, str) and isinstance(b, str) and a == b
    if isinstance(a, date) or isinstance(b, date):
        return a == b
    return float(a) == float(b)


def decide(old: dict, new: dict, marker, compared: tuple[str, ...]) -> tuple[bool, bool]:
    """``(changed, write)`` for one row, by the write rule.

    ``changed``: a compared column differs. ``write``: it changed, or it did
    not and the marker is NULL (the run confirms the row against the new
    bars). Equal with a marker set is already current and is not written. A
    column that is overwritten but not compared, such as the time the bars
    were read, never makes a write on its own.
    """
    changed = any(not same(old[column], new[column]) for column in compared)
    return changed, changed or _is_null(marker)


# ── the report ────────────────────────────────────────────────────────


@dataclass
class ReportRow:
    """One selected row in ``rows.csv``."""

    ticker: str
    session_date: date
    row_key: str
    old: dict
    new: dict | None
    changed: bool | None
    status: str
    bars_rows: int | None
    bars_sha256: str | None
    written: bool = False


def _cell(value) -> str:
    value = json_value(value)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    return str(value)


def rows_csv(rows, columns: tuple[str, ...]) -> str:
    """``rows.csv``: one line a selected row, old and new value of each column."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(
        ["ticker", "session_date", "row_key"]
        + [f"old_{c}" for c in columns]
        + [f"new_{c}" for c in columns]
        + ["changed", "status", "bars_rows", "bars_sha256", "written"])
    for row in rows:
        new = row.new or {}
        writer.writerow(
            [row.ticker, _cell(row.session_date), row.row_key]
            + [_cell(row.old.get(c)) for c in columns]
            + [_cell(new.get(c)) for c in columns]
            + [_cell(row.changed), row.status, _cell(row.bars_rows),
               _cell(row.bars_sha256), _cell(bool(row.written))])
    return out.getvalue()


def require_report_destination(report_dir: str | None) -> None:
    """Refuse a run that has nowhere to write its report."""
    if not report_dir and not os.environ.get("GCS_BUCKET", "").strip():
        raise Refusal("no --report-dir and GCS_BUCKET is not set: the report has nowhere to go")


def save_report(target: str, run_id: str, csv_text: str, summary: dict,
                report_dir: str | None) -> str:
    """Write ``rows.csv`` and ``summary.json`` and return where they went.

    ``--report-dir`` wins over the bucket. An upload or a write that fails
    raises: nothing is written to the database after a failed report.
    """
    require_report_destination(report_dir)
    summary_text = json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n"
    prefix = f"{REPORT_PREFIX}/{target}/{run_id}"
    if report_dir:
        folder = Path(report_dir) / prefix
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "rows.csv").write_text(csv_text)
        (folder / "summary.json").write_text(summary_text)
        return str(folder)
    from gcp import gcs_utils  # noqa: PLC0415 - keeps this module import-light

    bucket = os.environ["GCS_BUCKET"].strip()
    gcs_utils.upload_text_to_gcs(bucket, f"{prefix}/rows.csv", csv_text, "text/csv")
    gcs_utils.upload_text_to_gcs(
        bucket, f"{prefix}/summary.json", summary_text, "application/json")
    return f"gs://{bucket}/{prefix}"


def exit_code(rows) -> int:
    """1 when a row was refused or left, else 0."""
    return 1 if any(row.status in REFUSED_STATUSES for row in rows) else 0


# ── the tables ────────────────────────────────────────────────────────

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
_SQL_TYPES = frozenset({
    "varchar", "text", "timestamptz", "date", "double precision", "bigint", "integer", "jsonb"})

#: pg8000 packs the parameter count of one statement into 16 bits.
_MAX_STATEMENT_PARAMS = 60000


@dataclass(frozen=True)
class TableSpec:
    """One table a recompute overwrites: its key, the columns it overwrites
    (name to SQL type, the marker apart), the marker column, and a fixed
    predicate every write carries. Identifiers and types are checked, because
    they are put into statement text."""

    table: str
    alias: str
    keys: dict
    columns: dict
    marker: str
    fixed: str = ""

    def __post_init__(self):
        names = [self.table, self.alias, self.marker, *self.keys, *self.columns]
        for name in names:
            if not _IDENTIFIER.fullmatch(name):
                raise ValueError(f"not an identifier: {name!r}")
        for sqltype in [*self.keys.values(), *self.columns.values()]:
            if sqltype not in _SQL_TYPES:
                raise ValueError(f"not a SQL type this module binds: {sqltype!r}")


ALERT_EXITS = TableSpec(
    table="signal_alerts",
    alias="a",
    keys={"ticker": "varchar", "alert_ts": "timestamptz"},
    columns={
        "exit_ts": "timestamptz",
        "exit_reason": "varchar",
        "exit_price": "double precision",
        "exit_return_pct": "double precision",
    },
    marker="exit_recompute_run",
    fixed="a.run_kind = 'live' AND a.is_open IS FALSE",
)

TRADE_EXITS = TableSpec(
    table="trades",
    alias="t",
    keys={"ticker": "varchar", "entry_time": "timestamptz"},
    columns={
        "exit_time": "timestamptz",
        "exit_price": "double precision",
        "exit_reason": "varchar",
        "return_pct": "double precision",
    },
    marker="exit_recompute_run",
    fixed="t.run_kind = 'live'",
)

DAILY_PREMARKET = TableSpec(
    table="market_data_daily",
    alias="d",
    keys={"ticker": "varchar", "date": "date"},
    columns={
        "pre_high": "double precision",
        "pre_low": "double precision",
        "pre_vwap": "double precision",
        "gap_pct": "double precision",
        "pre_range_atr": "double precision",
        "pre_volume": "bigint",
        "pre_fetched_at": "timestamptz",
        "pre_excluded_stale_prints": "integer",
        "pre_excluded_spikes": "integer",
        "pre_filter_status": "varchar",
        "pre_filter_params": "jsonb",
    },
    marker="pre_recompute_run",
)

#: The ten value columns. ``pre_fetched_at`` says when the bars were read, not
#: what a value is: it is overwritten with a write and never decides one.
PREMARKET_COMPARED = tuple(c for c in DAILY_PREMARKET.columns if c != "pre_fetched_at")

#: target -> (the table written first, the table that follows it or None).
TARGET_TABLES = {
    TARGET_EXITS: (ALERT_EXITS, TRADE_EXITS),
    TARGET_PREMARKET: (DAILY_PREMARKET, None),
}

LEDGER_TABLE = "bar_recompute_ledger"

_SCHEMA_SQL = """
    SELECT table_name, column_name
      FROM information_schema.columns
     WHERE table_schema = current_schema()
       AND (table_name = 'bar_recompute_ledger'
            OR (table_name = 'signal_alerts' AND column_name = 'exit_recompute_run')
            OR (table_name = 'trades' AND column_name = 'exit_recompute_run')
            OR (table_name = 'market_data_daily' AND column_name = 'pre_recompute_run'))
"""

_LEDGER_SQL = """
    SELECT run_id, ticker, session_date, row_key, action,
           old_values::text AS old_values, new_values::text AS new_values,
           changed, basis::text AS basis
      FROM bar_recompute_ledger
     WHERE run_id = :run_id AND target = :target
     ORDER BY id
"""


@dataclass
class TableWrite:
    """One row of one table: its key, what the run read (every overwritten
    column and the marker) and what it writes (every overwritten column)."""

    spec: TableSpec
    key: dict
    old: dict
    new: dict


@dataclass
class WriteUnit:
    """One selected row to write: the primary row, and the row of the table
    that follows it, written only when the primary was."""

    ticker: str
    session_date: date
    row_key: str
    primary: TableWrite
    follower: TableWrite | None
    changed: bool
    basis: dict


def schema_missing() -> list[str]:
    """Which of the ledger table and the three marker columns the database
    does not hold. One strict query; a failed read raises."""
    from gcp.database import query_to_dataframe_strict  # noqa: PLC0415

    frame = query_to_dataframe_strict(_SCHEMA_SQL)
    found = set(zip(frame["table_name"], frame["column_name"]))
    missing = []
    if LEDGER_TABLE not in {table for table, _column in found}:
        missing.append(LEDGER_TABLE)
    for spec in (ALERT_EXITS, TRADE_EXITS, DAILY_PREMARKET):
        if (spec.table, spec.marker) not in found:
            missing.append(f"{spec.table}.{spec.marker}")
    return missing


def compare_and_set_sql(spec: TableSpec, n: int) -> str:
    """The one statement that writes *n* rows of a table.

    A row is written only while every overwritten column and the marker still
    hold what the run read; the keys of the rows it wrote are returned. Every
    reference to the values list is cast to its column's type: the list is
    typed by its parameters, and a column of NULLs or of text is not the
    column's type.
    """
    if n < 1:
        raise ValueError("a statement needs at least one row")
    a = spec.alias
    names = (list(spec.keys) + [f"old_{c}" for c in spec.columns] + ["old_marker"]
             + [f"new_{c}" for c in spec.columns])
    if n * len(names) > _MAX_STATEMENT_PARAMS:
        raise ValueError(
            f"{n} rows of {spec.table} need {n * len(names)} parameters; "
            f"one statement holds {_MAX_STATEMENT_PARAMS}")
    tuples = ",\n               ".join(
        "(" + ", ".join(f":r{i}_{name}" for name in names) + ")" for i in range(n))
    assignments = ", ".join(
        [f"{c} = v.new_{c}::{t}" for c, t in spec.columns.items()]
        + [f"{spec.marker} = :run_id"])
    conditions = (
        [f"{a}.{k} = v.{k}::{t}" for k, t in spec.keys.items()]
        + [f"{a}.{c} IS NOT DISTINCT FROM v.old_{c}::{t}" for c, t in spec.columns.items()]
        + [f"{a}.{spec.marker} IS NOT DISTINCT FROM v.old_marker::text"])
    if spec.fixed:
        conditions.append(spec.fixed)
    returning = ", ".join(f"{a}.{k}" for k in spec.keys)
    return (
        f"UPDATE {spec.table} AS {a}\n"
        f"   SET {assignments}\n"
        f"  FROM (VALUES {tuples}) AS v({', '.join(names)})\n"
        f" WHERE " + "\n   AND ".join(conditions) + "\n"
        f"RETURNING {returning}"
    )


def _key_identity(spec: TableSpec, key: dict) -> tuple:
    """A key as it compares between what was bound and what came back."""
    return tuple(db_value(key[name], sqltype) for name, sqltype in spec.keys.items())


def _statement_params(writes: list[TableWrite], run_id: str) -> dict:
    params: dict = {"run_id": run_id}
    for i, write in enumerate(writes):
        spec = write.spec
        for name, sqltype in spec.keys.items():
            params[f"r{i}_{name}"] = db_value(write.key[name], sqltype)
        for name, sqltype in spec.columns.items():
            params[f"r{i}_old_{name}"] = db_value(write.old[name], sqltype)
            params[f"r{i}_new_{name}"] = db_value(write.new[name], sqltype)
        params[f"r{i}_old_marker"] = db_value(write.old[spec.marker], "text")
    return params


def _compare_and_set(conn, writes: list[TableWrite], run_id: str) -> set:
    """Run the statement for *writes* (one table) and return the identities of
    the keys it wrote."""
    import sqlalchemy  # noqa: PLC0415

    spec = writes[0].spec
    result = conn.execute(
        sqlalchemy.text(compare_and_set_sql(spec, len(writes))),
        _statement_params(writes, run_id))
    returned = set()
    for record in result.mappings():
        returned.add(_key_identity(spec, {name: record[name] for name in spec.keys}))
    return returned


def _ledger_object(write: TableWrite, run_id: str | None) -> dict:
    """A table's values as the ledger holds them: the run's old values with
    the old marker when *run_id* is None, else its new values with the run's
    id as the marker."""
    spec = write.spec
    if run_id is None:
        values = {c: json_value(write.old[c]) for c in spec.columns}
        values[spec.marker] = json_value(write.old[spec.marker])
    else:
        values = {c: json_value(write.new[c]) for c in spec.columns}
        values[spec.marker] = run_id
    return values


_LEDGER_ROW = (
    "(:run_id, :target, :action, :l{i}_ticker, :l{i}_session_date, :l{i}_row_key, "
    "CAST(:l{i}_old AS JSONB), CAST(:l{i}_new AS JSONB), :l{i}_changed, "
    "CAST(:l{i}_basis AS JSONB))")


def write_group(engine, *, target: str, action: str, run_id: str,
                units: list[WriteUnit]) -> dict[str, tuple[bool, bool | None]]:
    """Write one group in one transaction and return, a ``row_key``, whether
    its primary row was written and whether its follower was (``None`` when
    the unit has no follower).

    Three statements at most, one a table: the primaries; then the followers
    of the primaries that statement returned, so a follower never moves
    without its primary; then one ledger row a returned primary. A group whose
    first statement returns nothing runs one statement, and an empty group
    runs none. Any failure rolls the whole group back.
    """
    import sqlalchemy  # noqa: PLC0415

    if not units:
        return {}
    _primary_spec, follower_spec = TARGET_TABLES[target]
    outcome: dict[str, tuple[bool, bool | None]] = {}
    with engine.begin() as conn:
        wrote = _compare_and_set(conn, [u.primary for u in units], run_id)
        written = [u for u in units if _key_identity(u.primary.spec, u.primary.key) in wrote]
        followers = [u for u in written if u.follower is not None]
        followed: set = set()
        if followers:
            followed = _compare_and_set(conn, [u.follower for u in followers], run_id)

        for unit in units:
            primary_written = unit in written
            if unit.follower is None:
                outcome[unit.row_key] = (primary_written, None)
            else:
                outcome[unit.row_key] = (
                    primary_written,
                    primary_written
                    and _key_identity(unit.follower.spec, unit.follower.key) in followed)

        if written:
            params: dict = {"run_id": run_id, "target": target, "action": action}
            for i, unit in enumerate(written):
                old_values = {unit.primary.spec.table: _ledger_object(unit.primary, None)}
                new_values = {unit.primary.spec.table: _ledger_object(unit.primary, run_id)}
                if follower_spec is not None:
                    kept = outcome[unit.row_key][1]
                    old_values[follower_spec.table] = (
                        _ledger_object(unit.follower, None) if kept else None)
                    new_values[follower_spec.table] = (
                        _ledger_object(unit.follower, run_id) if kept else None)
                params.update({
                    f"l{i}_ticker": unit.ticker,
                    f"l{i}_session_date": db_value(unit.session_date, "date"),
                    f"l{i}_row_key": unit.row_key,
                    f"l{i}_old": json.dumps(old_values, sort_keys=True, allow_nan=False),
                    f"l{i}_new": json.dumps(new_values, sort_keys=True, allow_nan=False),
                    f"l{i}_changed": bool(unit.changed),
                    f"l{i}_basis": json.dumps(unit.basis, sort_keys=True, allow_nan=False),
                })
            conn.execute(sqlalchemy.text(
                "INSERT INTO bar_recompute_ledger (run_id, target, action, ticker, "
                "session_date, row_key, old_values, new_values, changed, basis)\n"
                "VALUES " + ",\n       ".join(
                    _LEDGER_ROW.format(i=i) for i in range(len(written)))), params)
    return outcome


def ledger_of_run(run_id: str, target: str) -> list[dict]:
    """The ledger rows of one run and target, in the order they were written.
    One strict read; a failed read raises."""
    from gcp.database import query_to_dataframe_strict  # noqa: PLC0415

    frame = query_to_dataframe_strict(_LEDGER_SQL, {"run_id": run_id, "target": target})
    held = []
    for record in frame.to_dict("records"):
        held.append({
            "run_id": record["run_id"],
            "ticker": record["ticker"],
            "session_date": record["session_date"],
            "row_key": record["row_key"],
            "action": record["action"],
            "old_values": json.loads(record["old_values"]),
            "new_values": json.loads(record["new_values"]),
            "changed": bool(record["changed"]),
            "basis": json.loads(record["basis"]),
        })
    return held


def _revert_write(spec: TableSpec, ticker: str, row_key: str,
                  was_new: dict, was_old: dict) -> TableWrite:
    key_names = list(spec.keys)
    key = {key_names[0]: ticker, key_names[1]: row_key}
    return TableWrite(
        spec=spec, key=key,
        old=dict(was_new),
        new={c: was_old[c] for c in spec.columns})


def revert_units(ledger_rows: list[dict], target: str) -> list[WriteUnit]:
    """The writes that undo a run, one a ledger row.

    The row must still hold what that run wrote (its ``new_values``, with the
    run's id as the marker) and is given back what the run found (its
    ``old_values``). A follower the run did not write is not reverted.
    """
    primary_spec, follower_spec = TARGET_TABLES[target]
    units = []
    for held in ledger_rows:
        primary = _revert_write(
            primary_spec, held["ticker"], held["row_key"],
            held["new_values"][primary_spec.table], held["old_values"][primary_spec.table])
        follower = None
        if follower_spec is not None and held["new_values"].get(follower_spec.table) is not None:
            follower = _revert_write(
                follower_spec, held["ticker"], held["row_key"],
                held["new_values"][follower_spec.table],
                held["old_values"][follower_spec.table])
        units.append(WriteUnit(
            ticker=held["ticker"],
            session_date=db_value(held["session_date"], "date"),
            row_key=held["row_key"],
            primary=primary, follower=follower, changed=bool(held["changed"]),
            basis={"revert_of": held["run_id"], "code": code_version()}))
    return units


# ── a run, from its computed rows to its exit code ────────────────────


def _status_counts(rows) -> dict:
    by_group: dict = {}
    totals: dict = {}
    for row in rows:
        day = _cell(row.session_date)
        statuses = by_group.setdefault(row.ticker, {}).setdefault(day, {})
        statuses[row.status] = statuses.get(row.status, 0) + 1
        totals[row.status] = totals.get(row.status, 0) + 1
    return {"counts": by_group, "totals": totals,
            "written": sum(1 for row in rows if row.written)}


def finish_run(*, target: str, run_id: str, commit: bool, action: str,
               rows: list[ReportRow], groups: list[tuple[str, list[WriteUnit]]],
               summary: dict, csv_columns: tuple[str, ...],
               report_dir: str | None, summarize=None) -> int:
    """Save the report, write the groups when *commit*, save the report again,
    and return the exit code.

    *rows* holds every selected row; *groups* the units to write, a group a
    transaction. A unit and its report row share ``(ticker, row_key)``.
    *summarize*, when given, maps the rows to more summary keys at each save.

    A committed run first reads the ledger rows of its own run id: a Cloud Run
    retry keeps the execution's name, so an earlier attempt may have written
    some rows already. For those the report row is the ledger's (old values,
    new values, changed, written) and the unit is dropped, so the report is
    the account of every attempt and the first save of a retry cannot replace
    the old values an earlier attempt recorded.

    A ledger row whose follower is null records a primary written without its
    follower: the follower was missing, or it was left. The ledger does not
    say which, and this attempt's own rows do. Such a row keeps the status
    this attempt gave it when that status was refused or left
    (``trade_diverged`` while the trade still disagrees with its alert), and
    is ``trade_diverged`` when this attempt would write a follower for it (a
    revert whose earlier attempt did not restore the trade). So a retry exits
    1 while a trade an earlier attempt left still disagrees.

    A dry run reads no ledger and opens no engine. A failed report raises
    before any write. A failed group raises; the groups before it stay
    committed.
    """
    primary_spec, follower_spec = TARGET_TABLES[target]
    if commit:
        held = {(h["ticker"], h["row_key"]): h for h in ledger_of_run(run_id, target)}
        if held:
            planned = {(u.ticker, u.row_key): u for _label, units in groups for u in units}
            for i, row in enumerate(rows):
                entry = held.get((row.ticker, row.row_key))
                if entry is None:
                    continue
                status = "reverted" if entry["action"] == "revert" else "recomputed"
                if (follower_spec is not None
                        and entry["new_values"].get(follower_spec.table) is None):
                    unit = planned.get((row.ticker, row.row_key))
                    if row.status in REFUSED_STATUSES:
                        status = row.status
                    elif unit is not None and unit.follower is not None:
                        status = "trade_diverged"
                bars = entry["basis"].get("bars") or {}
                rows[i] = ReportRow(
                    ticker=row.ticker, session_date=row.session_date, row_key=row.row_key,
                    old=entry["old_values"][primary_spec.table],
                    new=entry["new_values"][primary_spec.table],
                    changed=entry["changed"],
                    status=status,
                    bars_rows=bars.get("rows"), bars_sha256=bars.get("sha256"),
                    written=True)
            groups = [
                (label, [u for u in units if (u.ticker, u.row_key) not in held])
                for label, units in groups]

    def save() -> None:
        full = dict(summary)
        full.update(_status_counts(rows))
        if summarize is not None:
            full.update(summarize(rows))
        save_report(target, run_id, rows_csv(rows, csv_columns), full, report_dir)

    save()
    if not commit:
        return exit_code(rows)

    from gcp.database import get_engine  # noqa: PLC0415

    engine = get_engine()
    by_key = {(row.ticker, row.row_key): row for row in rows}
    for _label, units in groups:
        if not units:
            continue
        outcome = write_group(engine, target=target, action=action, run_id=run_id, units=units)
        for unit in units:
            row = by_key[(unit.ticker, unit.row_key)]
            primary_written, follower_written = outcome[unit.row_key]
            if not primary_written:
                row.status = "changed_underneath"
                continue
            row.written = True
            if follower_written is False:
                row.status = "trade_diverged"
    save()
    return exit_code(rows)
