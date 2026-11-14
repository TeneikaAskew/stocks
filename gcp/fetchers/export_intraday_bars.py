"""A durable bucket file of the SPY, QQQ and IWM 1-min bars, one Parquet
object per ticker-month with a manifest beside it (FEAT-DATA-001, Design E).

    gs://<GCS_BUCKET>/intraday-bars/v1/1min/<TICKER>/<YYYY-MM>.parquet
    gs://<GCS_BUCKET>/intraday-bars/v1/1min/<TICKER>/manifest.json

This module only READS market_data_intraday and market_data_daily. It is for
an analysis session that cannot reach Cloud SQL: the session downloads a
ticker's folder and calls ``read_bars``.

The bucket files are never a source for the tree (CLAUDE.md 3.7.1). No job,
replay, backtest or route reads them, and nothing falls back to them when the
database fails: Cloud SQL is the system of record. tests/gcp/
test_export_intraday_bars.py holds that line.

Top-level imports are the standard library and pandas, so ``read_bars`` runs
where the database layer and the time helpers cannot be imported. Everything
else is imported inside the function that needs it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import date, datetime, timedelta
from typing import Optional, Sequence

import pandas as pd

log = logging.getLogger(__name__)

PREFIX = "intraday-bars/v1/1min"
EXPORT_TICKERS = ("SPY", "QQQ", "IWM")
COLUMNS = ("ts", "open", "high", "low", "close", "volume", "data_source")

# One strict read per ticker-month, bounded by the month window. The interval
# is in the text, not a bound value.
BARS_SQL = """
    SELECT ts, open, high, low, close, volume, data_source, inserted_at
      FROM market_data_intraday
     WHERE ticker = :t AND interval = '1min' AND ts >= :start AND ts < :end
     ORDER BY ts
"""
# One strict read per ticker for the run's months: the basis check's query.
DAILY_SQL = """
    SELECT date, high, low, data_source
      FROM market_data_daily
     WHERE ticker = :t AND date >= :first AND date <= :last
"""
_QUERY_TIMEOUT_S = 120

MANIFEST_VERSION = 1
# Writes of one manifest after the first attempt, each on a fresh read.
MANIFEST_RETRIES = 5


def object_name(ticker: str, year: int, month: int) -> str:
    """The object a ticker-month's file is stored under."""
    return f"{PREFIX}/{ticker}/{year:04d}-{month:02d}.parquet"


def manifest_name(ticker: str) -> str:
    """The object a ticker's manifest is stored under."""
    return f"{PREFIX}/{ticker}/manifest.json"


class GenerationMismatch(Exception):
    """A write named the generation it expected and the object has another."""


class GcsBucket:
    """The bucket, reduced to the two calls the export makes.

    ``read`` tells an absent object from a failed read: absent is ``None``,
    and every other failure raises. A helper that turned a failed read into
    "absent" would make the next write start a fresh manifest over a real one,
    so the two are never the same value (CLAUDE.md 3.7.1).
    """

    def __init__(self, bucket: str):
        from google.cloud import storage  # noqa: PLC0415

        self.name = bucket
        self._bucket = storage.Client().bucket(bucket)

    def read(self, name: str) -> Optional[tuple[bytes, int]]:
        """The object's bytes and its generation, or None when it is absent."""
        from google.api_core.exceptions import NotFound  # noqa: PLC0415

        blob = self._bucket.blob(name)
        try:
            data = blob.download_as_bytes()
        except NotFound:
            return None
        return data, self._generation(blob, name)

    def write(self, name: str, data: bytes,
              if_generation_match: Optional[int] = None) -> int:
        """Store *data* whole and return the new generation.

        With *if_generation_match* the write happens only while the object is
        at that generation (0: only while it does not exist); otherwise
        ``GenerationMismatch`` is raised and nothing is stored.
        """
        from google.api_core.exceptions import PreconditionFailed  # noqa: PLC0415

        blob = self._bucket.blob(name)
        try:
            blob.upload_from_string(data, if_generation_match=if_generation_match)
        except PreconditionFailed as exc:
            raise GenerationMismatch(
                f"{name}: the write expected generation {if_generation_match}") from exc
        return self._generation(blob, name)

    @staticmethod
    def _generation(blob, name: str) -> int:
        if blob.generation is None:
            # The next manifest write would carry no precondition: refuse.
            raise RuntimeError(f"{name}: the bucket reported no generation")
        return int(blob.generation)


def bucket_from_env() -> GcsBucket:
    """The bucket named by ``GCS_BUCKET`` (a leading ``gs://`` is dropped).

    Unset or empty raises: the export does not guess a bucket.
    """
    value = os.environ.get("GCS_BUCKET", "").strip()
    if value.startswith("gs://"):
        value = value[len("gs://"):]
    if not value:
        raise RuntimeError(
            "GCS_BUCKET is not set: the bar export has no bucket to write to")
    return GcsBucket(value)


def _month_table(kept: pd.DataFrame):
    """The kept rows as an Arrow table with the file's explicit schema.

    A NULL in the table stays null in the file: nothing is filled in.
    """
    import pyarrow as pa  # noqa: PLC0415

    def prices(name: str):
        values = pd.to_numeric(kept[name], errors="raise").astype("float64")
        return pa.array(values, type=pa.float64(), from_pandas=True)

    volume = pd.to_numeric(kept["volume"], errors="raise").astype("Int64")
    schema = pa.schema([
        ("ts", pa.timestamp("us", tz="UTC")),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("volume", pa.int64()),
        ("data_source", pa.string()),
    ])
    return pa.Table.from_arrays([
        pa.array(pd.DatetimeIndex(kept["ts"]), type=pa.timestamp("us", tz="UTC")),
        prices("open"), prices("high"), prices("low"), prices("close"),
        pa.array(volume, type=pa.int64(), from_pandas=True),
        pa.array(kept["data_source"], type=pa.string(), from_pandas=True),
    ], schema=schema)


def _month_last_day(year: int, month: int) -> date:
    first_of_next = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return first_of_next - timedelta(days=1)


# A session that is not counted as traded, inferred or adjusted is listed
# under not_measured with why. UNMEASURED carries its own reason.
_NOT_MEASURED = {"INCOMPLETE": "incomplete", "ODD": "odd"}
_COUNTED = {"AS-TRADED": "as_traded", "INFERRED": "inferred", "ADJUSTED": "adjusted"}


def _sessions_and_basis(rows: pd.DataFrame, daily: pd.DataFrame, year: int,
                        month: int, now_utc: datetime) -> tuple[dict, dict]:
    """How whole the month is and on what basis, as the checks of the fetch
    module read it: the session readings and the basis verdicts, counted.

    The manifest never says more than the basis check does: the state is
    ``as_traded`` only when every closed session is AS-TRADED from proven rows.
    The state takes the first that applies of ``adjusted`` (an ADJUSTED
    session), ``inferred`` (an as-traded verdict that rests on a row that is
    not proven), ``unmeasured`` (no session counted at all; both factors
    null), ``as_traded`` (nothing under ``not_measured``), ``partial``.

    ``factor_min`` and ``factor_max`` range over the sessions counted as
    traded, inferred or adjusted. An ODD session is under ``not_measured``
    and outside the range.
    """
    from gcp.fetchers.fetch_alphavantage_intraday import (  # noqa: PLC0415
        session_basis_verdicts,
    )
    from lib.eastern_time import session_schedule  # noqa: PLC0415

    schedule = session_schedule(date(year, month, 1), _month_last_day(year, month))
    # A session still trading, or not yet open, is not read at all.
    schedule = schedule[schedule["market_close"] <= now_utc]
    records = session_basis_verdicts(rows, daily, schedule)

    sessions = {"expected": len(records), "ok": 0, "thin": 0, "missing": 0,
                "undetermined": 0}
    counts = {"as_traded": 0, "inferred": 0, "adjusted": 0, "odd": 0}
    not_measured: dict = {}
    factors: list = []
    for record in records:
        # An unknown status or verdict is a KeyError: never counted as fine.
        sessions[record["status"].lower()] += 1
        verdict = record["verdict"]
        day = record["session"].isoformat()
        if verdict in _COUNTED:
            counts[_COUNTED[verdict]] += 1
            factors.append(record["factor"])
        elif verdict == "UNMEASURED":
            not_measured[day] = record["reason"]
        else:
            not_measured[day] = _NOT_MEASURED[verdict]
            if verdict == "ODD":
                counts["odd"] += 1

    if counts["adjusted"]:
        state = "adjusted"
    elif counts["inferred"]:
        state = "inferred"
    elif not factors:
        state = "unmeasured"
    elif not not_measured:
        state = "as_traded"
    else:
        state = "partial"
    basis = {
        "state": state,
        "factor_min": min(factors) if factors else None,
        "factor_max": max(factors) if factors else None,
        **counts,
        "not_measured": not_measured,
    }
    return sessions, basis


def build_month(rows: pd.DataFrame, daily: pd.DataFrame, ticker: str, year: int,
                month: int, now_utc: datetime) -> tuple[Optional[bytes], dict]:
    """The month's Parquet bytes (None when *rows* is empty) and its manifest
    entry. Pure: nothing is read or written here.

    *rows* is what ``BARS_SQL`` returned for the month window, whole: each
    row's instant is the one ``lib.eastern_time.place_stored_rows`` gives it,
    which must see each date entire. A proven row is written at its stored
    instant; a row that is not proven is written where the resolver puts it
    and counted in ``inferred_rows``. When two stored rows land on one minute
    one is written and the other is counted in ``dropped_rows``.

    Limit, by construction (Design F): a whole session stored under both
    conventions with flat volume can be written on the wrong minutes. Nothing
    in the file marks those rows; ``inferred_rows`` above 0 is the only flag.

    The entry's ``sessions`` and ``basis`` are over the calendar's sessions of
    the month whose close has passed at *now_utc* (:func:`_sessions_and_basis`).
    A month with no row gets its entry through the same code: no file, every
    closed session missing, state ``unmeasured``.
    """
    import pyarrow as pa  # noqa: PLC0415
    import pyarrow.parquet as pq  # noqa: PLC0415

    from lib.eastern_time import place_stored_rows  # noqa: PLC0415

    sessions, basis = _sessions_and_basis(rows, daily, year, month, now_utc)
    entry: dict = {
        "file": None,
        "rows": 0,
        "stored_rows": int(len(rows)),
        "dropped_rows": 0,
        "inferred_rows": 0,
        "first_ts": None,
        "last_ts": None,
        "sha256": None,
        "exported_at": now_utc.isoformat(),
        "sessions": sessions,
        "basis": basis,
    }
    if rows.empty:
        return None, entry

    instants, keep, proven = place_stored_rows(
        rows["ts"], rows["volume"], rows["inserted_at"])
    kept = rows.loc[keep, list(COLUMNS[1:])].reset_index(drop=True)
    kept.insert(0, "ts", instants[keep])
    kept = kept.sort_values("ts", kind="stable").reset_index(drop=True)

    sink = pa.BufferOutputStream()
    pq.write_table(_month_table(kept), sink, compression="zstd")
    data = sink.getvalue().to_pybytes()

    entry.update({
        "file": object_name(ticker, year, month),
        "rows": int(len(kept)),
        "dropped_rows": int(len(rows) - len(kept)),
        "inferred_rows": int((keep & ~proven).sum()),
        "first_ts": kept["ts"].iloc[0].isoformat(),
        "last_ts": kept["ts"].iloc[-1].isoformat(),
        "sha256": hashlib.sha256(data).hexdigest(),
    })
    return data, entry


def export_month(bucket, ticker: str, year: int, month: int, daily: pd.DataFrame,
                 now_utc: datetime) -> dict:
    """Read one ticker-month, upload its file whole, return its manifest entry.

    One strict read over the month window; a failed read or upload raises.
    The manifest is not touched here: the caller writes the entry only after
    this returns, so a failure leaves the manifest as it was for the month.
    A month with no row uploads nothing.
    """
    from gcp.database import query_to_dataframe_strict  # noqa: PLC0415
    from lib.eastern_time import intraday_month_window  # noqa: PLC0415

    start, end = intraday_month_window(year, month)
    rows = query_to_dataframe_strict(
        BARS_SQL, {"t": ticker, "start": start, "end": end}, timeout_s=_QUERY_TIMEOUT_S)
    data, entry = build_month(rows, daily, ticker, year, month, now_utc)
    del rows
    if data is not None:
        bucket.write(object_name(ticker, year, month), data)
    return entry


# -- the manifest ---------------------------------------------------------------


def _parse_manifest(data: bytes, ticker: str, name: str) -> dict:
    """The manifest document, or ValueError: it is never guessed at.

    A manifest that does not parse, has another version or names another
    ticker is refused, and the caller never replaces it with a fresh one.
    """
    try:
        doc = json.loads(data)
    except ValueError as exc:
        raise ValueError(f"{name}: the manifest does not parse: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("months"), dict):
        raise ValueError(f"{name}: the manifest is not an object with months")
    # True == 1 in Python: compare the type too.
    version = doc.get("version")
    if type(version) is not int or version != MANIFEST_VERSION:
        raise ValueError(
            f"{name}: manifest version is {version!r}, this code reads {MANIFEST_VERSION}")
    if doc.get("ticker") != ticker:
        raise ValueError(f"{name}: the manifest is for {doc.get('ticker')!r}, not {ticker}")
    return doc


def _manifest_bytes(doc: dict) -> bytes:
    return (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode("utf-8")


def read_manifest(bucket, ticker: str) -> tuple[dict, int]:
    """The ticker's manifest and its generation.

    An absent object is the empty manifest at generation 0, which a write
    then creates only if it is still absent. Any failed read propagates, and
    a manifest that is not a version 1 manifest of this ticker raises
    ValueError: neither is ever read as "absent".
    """
    name = manifest_name(ticker)
    found = bucket.read(name)
    if found is None:
        return {"version": MANIFEST_VERSION, "ticker": ticker, "months": {}}, 0
    data, generation = found
    return _parse_manifest(data, ticker, name), generation


def write_month_entry(bucket, ticker: str, month_key: str, entry: dict, doc: dict,
                      generation: int) -> tuple[dict, int]:
    """Put one month's entry into the manifest and store it; return the
    document and generation now stored.

    The write names the generation *doc* was read at (0: the object must not
    exist yet). When another run wrote in between, the manifest is read
    again, this month's entry is put into that fresh document and the write is
    retried, at most MANIFEST_RETRIES times; then GenerationMismatch is let
    out. An entry another run wrote for another month is never lost.
    """
    name = manifest_name(ticker)
    for attempt in range(MANIFEST_RETRIES + 1):
        doc["months"][month_key] = entry
        try:
            return doc, bucket.write(name, _manifest_bytes(doc),
                                     if_generation_match=generation)
        except GenerationMismatch:
            if attempt == MANIFEST_RETRIES:
                raise
        doc, generation = read_manifest(bucket, ticker)
    raise AssertionError("unreachable")  # pragma: no cover


# -- a run ----------------------------------------------------------------------


def months_between(first: tuple[int, int], last: tuple[int, int]) -> list[tuple[int, int]]:
    """Every (year, month) from *first* to *last*, both included; empty when
    *first* is after *last*."""
    out = []
    year, month = first
    while (year, month) <= tuple(last):
        out.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def nightly_months(today: date) -> list[tuple[int, int]]:
    """The month before *today*'s and *today*'s. *today* is the exchange's
    date (lib.eastern_time.market_today), not the container's."""
    previous = date(today.year, today.month, 1) - timedelta(days=1)
    return [(previous.year, previous.month), (today.year, today.month)]


def export_window(tickers: Sequence[str], months: Sequence[tuple[int, int]], *,
                  bucket=None, now_utc: Optional[datetime] = None) -> dict:
    """Write *months* of each of *tickers* to the bucket; return
    ``{"months", "rows", "seconds"}``.

    Per ticker: one daily read over the span of *months*, one manifest read,
    then per month, in order: the bars read, the file's upload, the manifest
    write with that month's entry, one progress line. The manifest is written
    after each month's file, each write naming the generation the one before
    it returned, so a failed upload leaves every earlier month's file and
    entry matching, and a rerun converges.

    Nothing is caught: a failed read, upload or manifest write ends the run
    with its own exception, and the manifest is untouched for the month it
    failed on. One ticker-month's rows are in memory at a time.
    """
    from gcp.database import query_to_dataframe_strict  # noqa: PLC0415
    from lib.eastern_time import utc_now  # noqa: PLC0415

    started = time.monotonic()
    tickers, months = list(tickers), [tuple(m) for m in months]
    if bucket is None:
        bucket = bucket_from_env()
    if now_utc is None:
        now_utc = utc_now()

    total = len(tickers) * len(months)
    done = rows_written = 0
    if months:
        (first_year, first_month), (last_year, last_month) = min(months), max(months)
    for ticker in tickers:
        if not months:
            break
        daily = query_to_dataframe_strict(
            DAILY_SQL,
            {"t": ticker, "first": date(first_year, first_month, 1),
             "last": _month_last_day(last_year, last_month)},
            timeout_s=_QUERY_TIMEOUT_S)
        doc, generation = read_manifest(bucket, ticker)
        for year, month in months:
            entry = export_month(bucket, ticker, year, month, daily, now_utc)
            month_key = f"{year:04d}-{month:02d}"
            doc, generation = write_month_entry(
                bucket, ticker, month_key, entry, doc, generation)
            done += 1
            rows_written += entry["rows"]
            log.info(
                "bars month: %s %s rows=%d stored=%d dropped=%d inferred=%d state=%s (%d/%d)",
                ticker, month_key, entry["rows"], entry["stored_rows"],
                entry["dropped_rows"], entry["inferred_rows"],
                entry["basis"]["state"], done, total)
    return {"months": done, "rows": rows_written,
            "seconds": time.monotonic() - started}
