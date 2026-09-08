"""Pin the timestamp basis of migrate_to_gcp's trade-time normalization.

The trade parquets are written by TradeLogger with ``entry_time =
datetime.now()`` — a NAIVE UTC instant on Cloud Run (the producer's own
comment in gcp/signal_monitor.py calls it "the same naive UTC value
written to the DB row"). The identical value is the ``trades`` table's
(ticker, entry_time) conflict key, so a parquet restore must reproduce
it exactly: naive → relabel as UTC.

History, so this doesn't regress in either direction again:
  - The original ``pd.to_datetime(..., utc=True)`` was CORRECT for this
    producer.
  - PR #764's first cut localized naive values as America/New_York
    (mis-generalizing from the intraday path, whose parquets are ET-naive
    but come from a different producer) — a 4-5h shift that would land
    every restored row under a different conflict key and duplicate it.
    Codex P1 on #764 caught it; these tests pin the corrected contract.
"""
from __future__ import annotations

import pandas as pd

from gcp.migrate_to_gcp import _trade_times_to_utc


def test_naive_series_is_relabeled_as_utc_not_eastern():
    """THE #764 regression guard: a naive 14:05 producer stamp is 14:05
    UTC — the same instant the DB conflict key carries. ET localization
    would turn it into 18:05 UTC and duplicate the row on restore."""
    out = _trade_times_to_utc(pd.Series(["2026-07-15 14:05:00"]))
    assert str(out.dt.tz) == "UTC"
    assert out.iloc[0] == pd.Timestamp("2026-07-15 14:05:00", tz="UTC")


def test_naive_winter_value_unchanged_too():
    """No DST dependence — naive means UTC year-round for this producer."""
    out = _trade_times_to_utc(pd.Series(["2026-01-15 15:05:00"]))
    assert out.iloc[0] == pd.Timestamp("2026-01-15 15:05:00", tz="UTC")


def test_aware_utc_series_passes_through():
    src = pd.Series([pd.Timestamp("2026-07-15 14:05:00", tz="UTC")])
    out = _trade_times_to_utc(src)
    assert out.iloc[0] == src.iloc[0]


def test_aware_eastern_series_converts_to_utc():
    """A future tz-aware writer stays correct: aware values convert,
    never relabel."""
    src = pd.Series([pd.Timestamp("2026-07-15 10:05:00", tz="America/New_York")])
    out = _trade_times_to_utc(src)
    assert out.iloc[0] == pd.Timestamp("2026-07-15 14:05:00", tz="UTC")


def test_idempotent_across_reruns():
    """Round-tripping the helper's own output is a fixed point — the
    convergence property the (ticker, entry_time) upsert key depends on."""
    first = _trade_times_to_utc(pd.Series(["2026-07-15 14:05:00"]))
    second = _trade_times_to_utc(first)
    assert (first == second).all()


def test_matches_db_writer_interpretation():
    """End-to-end parity: the DB writer hands Postgres the naive value,
    which lands as that instant in UTC. The parquet-restore path must
    produce the identical aware instant, or ON CONFLICT never matches."""
    naive = "2026-08-25 13:25:04"
    restored = _trade_times_to_utc(pd.Series([naive])).iloc[0]
    db_instant = pd.Timestamp(naive, tz="UTC")
    assert restored == db_instant


def test_unparseable_becomes_nat_not_crash():
    out = _trade_times_to_utc(pd.Series(["not-a-time"]))
    assert out.isna().all()


# ── migrate_trades and the run_kind stamp (internal review of #1022) ─────

def _trades_dir(tmp_path, rows):
    d = tmp_path / "trades"
    d.mkdir()
    pd.DataFrame(rows).to_parquet(d / "2026-09-07.parquet", index=False)
    return tmp_path


def test_migrate_trades_stamps_pre_stamp_rows_as_live(tmp_path, monkeypatch, caplog):
    """A Parquet file written today holds pre-stamp rows with a null
    run_kind; upsert_dataframe binds every column, so the NOT NULL column
    rejected the whole file and the per-file warning swallowed it: a day
    of trades silently missing from a restore. The files have one writer,
    the live monitor (see TradeLogger._filter_run_kind), so a null is
    recorded as live, and the count is logged."""
    import logging
    from gcp import migrate_to_gcp
    seen: list = []
    monkeypatch.setattr("gcp.database.upsert_dataframe",
                        lambda df, table, keys: seen.append(df.copy()) or len(df))
    data_dir = _trades_dir(tmp_path, [
        {"ticker": "SPY", "entry_time": "2026-09-07 14:31:00", "run_kind": None},
        {"ticker": "SPY", "entry_time": "2026-09-07 14:32:00", "run_kind": "replay"},
    ])
    with caplog.at_level(logging.INFO, logger="gcp.migrate_to_gcp"):
        migrate_to_gcp.migrate_trades(data_dir, dry_run=False)
    assert len(seen) == 1
    assert list(seen[0]["run_kind"]) == ["live", "replay"]
    assert "1 row(s) predate the run_kind stamp" in caplog.text


def test_migrate_trades_stamps_a_file_with_no_run_kind_column(tmp_path, monkeypatch):
    from gcp import migrate_to_gcp
    seen: list = []
    monkeypatch.setattr("gcp.database.upsert_dataframe",
                        lambda df, table, keys: seen.append(df.copy()) or len(df))
    data_dir = _trades_dir(tmp_path, [{"ticker": "SPY", "entry_time": "2026-09-07 14:31:00"}])
    migrate_to_gcp.migrate_trades(data_dir, dry_run=False)
    assert list(seen[0]["run_kind"]) == ["live"]


def test_migrate_trades_raises_instead_of_warning_on_a_failed_file(tmp_path, monkeypatch):
    import pytest
    from gcp import migrate_to_gcp

    def _boom(df, table, keys):
        raise RuntimeError("null value in column run_kind")

    monkeypatch.setattr("gcp.database.upsert_dataframe", _boom)
    data_dir = _trades_dir(tmp_path, [{"ticker": "SPY", "entry_time": "2026-09-07 14:31:00", "run_kind": "live"}])
    with pytest.raises(RuntimeError, match="run_kind"):
        migrate_to_gcp.migrate_trades(data_dir, dry_run=False)
