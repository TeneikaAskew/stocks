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
