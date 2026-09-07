#!/usr/bin/env python3
"""
One-shot backfill: compute BSM Greeks for historical SPX (and other index)
options chains in ``etf_options_snapshots`` and write the results into the
``*_computed`` sidecar columns.

This is a Cloud Run Job entry point. It deliberately does NOT touch the
original AV ``delta``/``gamma``/``theta``/``vega``/``rho``/
``implied_volatility`` columns — those preserve the AV provenance (which
for SPX is "AV returned dashes, coerced to NaN").

The math lives in :mod:`lib.options_greeks`. This script is a thin loop
over distinct snapshot dates that calls
:func:`lib.options_greeks.enrich_av_chain_with_greeks` and persists the
resulting sidecar values via batched UPDATE statements keyed on ``id``.

Idempotent
----------
* Default mode skips any (ticker, snapshot_date) where ``gamma_computed`` is
  already finite (not NaN, not NULL).
* ``--force`` recomputes everything in the date range.
* The math itself is deterministic given inputs, so re-running a date
  produces the same sidecar values (modulo new FRED rate values).

Designed to run as a Cloud Run Job (12h timeout) so codespace
sleeps/rebuilds don't kill it. Same execution pattern as the AV historical
backfill job that landed the underlying chain data.

Usage
-----
    python -m scripts.maintenance.compute_spx_greeks --ticker SPX
    python -m scripts.maintenance.compute_spx_greeks \
        --ticker SPX --start-date 2024-01-01 --end-date 2024-12-31
    python -m scripts.maintenance.compute_spx_greeks --ticker SPX --force
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from gcp.database import get_engine, query_to_dataframe
from lib.logging_config import setup_logging
from lib.options_greeks import (
    COMPUTE_GREEKS_TICKERS,
    COMPUTED_COLS,
    enrich_av_chain_with_greeks,
)

setup_logging()
log = logging.getLogger(__name__)

UPDATE_BATCH_SIZE = 5000  # rows per UPDATE batch — tuned for db-g1-small


def list_dates_to_process(
    ticker: str,
    start: str | None,
    end: str | None,
    force: bool,
) -> list[date]:
    """Return the list of distinct snapshot_dates needing computation.

    Without ``--force``: a date is "needing computation" if at least one row
    has ``gamma_computed`` either NULL or NaN. With ``--force``: every date
    in the range is returned.

    Note: PostgreSQL stores NaN floats as real values that satisfy
    ``IS NOT NULL`` but not ``> -1e308``. We use the ``::text != 'NaN'``
    cast to filter NaN-as-stored from real finite values.
    """
    where = ["ticker = :t", "data_source = 'alphavantage'"]
    params: dict = {"t": ticker}
    if start:
        where.append("snapshot_date >= :start")
        params["start"] = start
    if end:
        where.append("snapshot_date <= :end")
        params["end"] = end

    if force:
        sql = (
            "SELECT DISTINCT snapshot_date FROM etf_options_snapshots "
            "WHERE " + " AND ".join(where) + " ORDER BY snapshot_date"
        )
    else:
        # A date is "needs work" if ANY row's gamma_computed is NULL/NaN.
        # EXISTS subquery is cheap because the index covers (ticker, snapshot_date).
        where_sub = list(where) + [
            "(gamma_computed IS NULL OR gamma_computed::text = 'NaN')",
        ]
        sql = (
            "SELECT DISTINCT snapshot_date FROM etf_options_snapshots "
            "WHERE " + " AND ".join(where_sub) + " ORDER BY snapshot_date"
        )

    df = query_to_dataframe(sql, params)
    if df.empty:
        return []
    return [d if isinstance(d, date) else pd.to_datetime(d).date()
            for d in df["snapshot_date"].tolist()]


def load_chain(ticker: str, snap: date) -> pd.DataFrame:
    """Load one date's chain from etf_options_snapshots, including row id."""
    sql = """
        SELECT id, contract_symbol, expiration, strike, option_type,
               bid, ask, mark, last_price, volume, open_interest,
               implied_volatility, delta, gamma, theta, vega, rho,
               implied_volatility_computed,
               delta_computed, gamma_computed, theta_computed,
               vega_computed, rho_computed
        FROM etf_options_snapshots
        WHERE ticker = :t
          AND snapshot_date = :d
          AND data_source = 'alphavantage'
    """
    return query_to_dataframe(sql, {"t": ticker, "d": snap})


def update_computed_columns(df: pd.DataFrame) -> int:
    """Bulk UPDATE the 6 *_computed columns on a chain DataFrame.

    Uses SQLAlchemy executemany batched at UPDATE_BATCH_SIZE rows. Only the
    sidecar columns are written — AV columns are explicitly excluded from
    the SET clause.
    """
    if df.empty or "id" not in df.columns:
        return 0

    needed = ["id", *COMPUTED_COLS]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        log.warning("update_computed_columns: missing columns %s", missing)
        return 0

    import sqlalchemy

    engine = get_engine()
    update_sql = sqlalchemy.text(
        "UPDATE etf_options_snapshots SET "
        "delta_computed = :delta_computed, "
        "gamma_computed = :gamma_computed, "
        "theta_computed = :theta_computed, "
        "vega_computed = :vega_computed, "
        "rho_computed = :rho_computed, "
        "implied_volatility_computed = :implied_volatility_computed "
        "WHERE id = :id"
    )

    # Convert NaN to None so pg8000 sends SQL NULL instead of the string 'NaN'.
    # Storing None keeps the audit query "with_gamma_av = 0" honest — only
    # values we actually solved end up non-null.
    def _scrub(rec: dict) -> dict:
        out: dict = {"id": int(rec["id"])}
        for c in COMPUTED_COLS:
            v = rec.get(c)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                out[c] = None
            else:
                out[c] = float(v)
        return out

    rows = [_scrub(r) for r in df[needed].to_dict(orient="records")]
    total = 0
    with engine.begin() as conn:
        for i in range(0, len(rows), UPDATE_BATCH_SIZE):
            batch = rows[i : i + UPDATE_BATCH_SIZE]
            conn.execute(update_sql, batch)
            total += len(batch)
    return total


class GreeksUnavailable(RuntimeError):
    """Enrichment produced no finite Greeks for a non-empty chain.

    Typed so the caller counts it as a failed date rather than a silent
    no-op: `main` exits non-zero, and the Cloud Run job's failure is visible
    to the failure-notifier instead of reading as a clean run.
    """


def _keep_solved(enriched: pd.DataFrame, prior: pd.DataFrame) -> pd.DataFrame:
    """Fill non-finite results from the values the table already held.

    A re-solve is not always an improvement: an underivable spot or a failed
    IV solve produces NaN for a contract whose Greeks are already stored and
    correct. Writing that back is data loss dressed as a backfill, so a new
    value replaces the old one only where the new value is finite.

    Merged on `id`, not on position: `enrich_av_chain_with_greeks` may drop
    rows, and aligning two frames of different lengths by index would shift
    every value after the first gap onto the wrong contract.
    """
    if prior.empty or "id" not in enriched.columns:
        return enriched
    carried = prior.set_index("id")
    out = enriched.set_index("id")
    for col in COMPUTED_COLS:
        if col not in carried.columns:
            continue
        old = pd.to_numeric(carried[col], errors="coerce").reindex(out.index)
        if col not in out.columns:
            out[col] = old
            continue
        new = pd.to_numeric(out[col], errors="coerce")
        out[col] = new.where(np.isfinite(new), old)
    return out.reset_index()


def _pending_gamma_ids(chain: pd.DataFrame) -> set | None:
    """The row ids this run was selected to fill, or None when rows have no id.

    `list_dates_to_process` selects a date when ANY row has a NULL gamma, so
    the work is those rows and not the whole chain. Without an `id` column the
    rows cannot be followed through enrichment (which may drop some), and the
    caller falls back to a whole-chain count.
    """
    if "id" not in chain.columns:
        return None
    if "gamma_computed" not in chain.columns:
        return set(chain["id"])
    g = pd.to_numeric(chain["gamma_computed"], errors="coerce")
    return set(chain.loc[~np.isfinite(g), "id"])


def _finite_gamma_ids(df: pd.DataFrame) -> set:
    """Row ids carrying a finite gamma in this frame."""
    if "id" not in df.columns or "gamma_computed" not in df.columns:
        return set()
    g = pd.to_numeric(df["gamma_computed"], errors="coerce")
    return set(df.loc[np.isfinite(g), "id"])


def process_one_date(ticker: str, snap: date) -> tuple[int, int]:
    """Load → enrich → UPDATE for one snapshot date.

    Returns (loaded_rows, updated_rows). updated_rows can be < loaded_rows
    only if the chain was empty after dropna in enrich.
    """
    chain = load_chain(ticker, snap)
    if chain.empty:
        log.warning("  %s %s: empty chain, skipping", ticker, snap)
        return 0, 0

    # Drop the sidecar columns before enriching.
    #
    # `enrich_av_chain_with_greeks` short-circuits the WHOLE chain when
    # `_has_existing_computed_greeks` finds ANY finite value, but
    # `list_dates_to_process` selects a date when ANY row is NULL/NaN. A
    # partially populated snapshot therefore satisfies both: it is selected as
    # needing work, then skipped wholesale, and the finite-count gate below
    # passes on the rows that were already there -- so the job exits 0 and the
    # missing rows stay missing on every retry (Codex, PR #994).
    #
    # Dropping them makes the early return unreachable here, so every row this
    # job was selected for is actually computed. The skip stays useful on the
    # request path, where re-solving a fully populated chain is wasted work;
    # this job's entire purpose is to fill the gaps.
    # Kept FIRST, because the drop below is otherwise destructive. `load_chain`
    # selects the sidecars, so this frame is the only copy of every value a
    # previous run already solved; `update_computed_columns` writes whatever
    # comes back for every row it is given. Dropping the columns and writing
    # the result therefore puts NULL over a valid Greek for any contract that
    # solved last week and fails today -- a fix for a silent fallback that
    # destroys data, which is worse than the fallback (Codex, PR #994).
    have = [c for c in COMPUTED_COLS if c in chain.columns]
    prior = (chain[["id", *have]].copy()
             if "id" in chain.columns and have else pd.DataFrame())

    pending_ids = _pending_gamma_ids(chain)
    pending_before = len(pending_ids) if pending_ids is not None else len(chain)
    chain = chain.drop(
        columns=[c for c in COMPUTED_COLS if c in chain.columns], errors="ignore")

    enriched = enrich_av_chain_with_greeks(chain, ticker, snap)

    # What THIS RUN solved. The gate below intersects it with the PENDING
    # rows, and that intersection is what makes the gate sound: a total finite
    # count over the frame counts rows earlier runs filled, so one
    # already-solved row on a date whose entire pending set failed cleared the
    # gate, rewrote the same values and exited 0 with the gaps intact -- the
    # no-op-reported-as-success this job was fixed for, reintroduced by the
    # fix for the round before it (Codex, PR #994).
    #
    # Read before the carry-forward rather than after. Today the two are
    # equivalent, because a pending row is one whose prior value was NaN and
    # the merge cannot restore it to finite. That equivalence is a property of
    # `_pending_gamma_ids`, not of this line, so this does not depend on it.
    solved_now = _finite_gamma_ids(enriched)

    enriched = _keep_solved(enriched, prior)

    # How many rows carry a finite gamma_computed after enrichment. This was
    # a log-line statistic and nothing else, which made the job unable to fail
    # for the reason it exists (Codex, PR #994):
    #
    #   * a failed rate lookup returns the chain UNTOUCHED, so the sidecars
    #     keep whatever they had — and `load_chain` already selects them, so
    #     they are the existing NULLs;
    #   * an underivable spot returns the sidecars present and entirely NaN.
    #
    # Either way `update_computed_columns` rewrites NULL over NULL and returns
    # the full row count, `process_one_date` raises nothing, `failures` stays
    # 0, and the Cloud Run job exits 0 reporting a backfill it did not
    # perform. `n_updated` counts rows touched, not Greeks computed.
    g = pd.to_numeric(enriched.get("gamma_computed"), errors="coerce")
    finite = int(np.isfinite(g).sum()) if g is not None else 0

    if pending_ids is None:
        # No `id` column, so the pending rows cannot be followed through
        # enrichment. Whole-chain gate, which is what this was before ids
        # were available to it.
        if finite == 0:
            raise GreeksUnavailable(
                f"{ticker} {snap}: {len(chain)} rows loaded and 0 finite "
                f"gamma_computed after enrichment — nothing was computed, so "
                f"this date is a failure rather than a no-op")
        still_missing = len(enriched) - finite
    else:
        filled = pending_ids & solved_now
        if pending_ids and not filled:
            raise GreeksUnavailable(
                f"{ticker} {snap}: {len(pending_ids)} rows were pending and 0 "
                f"of them were solved — nothing was computed for the rows this "
                f"date was selected for, so it is a failure rather than a "
                f"no-op, however many rows earlier runs already filled")
        still_missing = len(pending_ids - solved_now)

    n_updated = update_computed_columns(enriched)
    log.info(
        "  %s %s: loaded=%d pending=%d enriched_finite=%d still_missing=%d updated=%d",
        ticker, snap, len(chain), pending_before, finite, still_missing, n_updated,
    )
    if still_missing:
        # Not a failure -- a partially solved chain is real progress and the
        # rows that solved are worth writing. But it is not silence either:
        # the date will be selected again next run, and an operator seeing
        # this line repeat with the same count knows the remainder is not
        # merely un-attempted.
        log.warning("  %s %s: %d rows still have no computed gamma after this run",
                    ticker, snap, still_missing)
    return len(chain), n_updated


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Backfill *_computed Greeks columns for index option chains "
                    "(SPX, NDX, ...) using lib.options_greeks.",
    )
    ap.add_argument("--ticker", default="SPX",
                    help="Ticker to process (default SPX). Must be in "
                         "lib.options_greeks.COMPUTE_GREEKS_TICKERS.")
    ap.add_argument("--start-date", default=None,
                    help="Inclusive start (YYYY-MM-DD).")
    ap.add_argument("--end-date", default=None,
                    help="Inclusive end (YYYY-MM-DD).")
    ap.add_argument("--force", action="store_true",
                    help="Recompute even rows that already have gamma_computed.")
    ap.add_argument("--limit-dates", type=int, default=None,
                    help="Process at most N dates (smoke testing).")
    ap.add_argument("--sleep", type=float, default=0.0,
                    help="Pause N seconds between dates (gentle on Cloud SQL).")
    args = ap.parse_args()

    ticker = args.ticker.upper()
    if ticker not in COMPUTE_GREEKS_TICKERS:
        log.error("Ticker %s not in COMPUTE_GREEKS_TICKERS %s",
                  ticker, sorted(COMPUTE_GREEKS_TICKERS))
        return 2

    log.info("compute_spx_greeks: ticker=%s start=%s end=%s force=%s",
             ticker, args.start_date, args.end_date, args.force)

    dates = list_dates_to_process(
        ticker, args.start_date, args.end_date, force=args.force,
    )
    if args.limit_dates:
        dates = dates[: args.limit_dates]
    log.info("Found %d dates to process", len(dates))
    if not dates:
        log.info("Nothing to do.")
        return 0

    t0 = time.time()
    total_rows = total_updated = 0
    failures = 0
    for i, snap in enumerate(dates, 1):
        try:
            loaded, updated = process_one_date(ticker, snap)
            total_rows += loaded
            total_updated += updated
        except Exception as exc:
            failures += 1
            log.error("  %s %s: FAILED — %s", ticker, snap, exc)

        if args.sleep > 0:
            time.sleep(args.sleep)

        if i % 25 == 0 or i == len(dates):
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta_min = (len(dates) - i) / rate / 60.0 if rate > 0 else 0
            log.info("Progress: %d/%d dates (%.1f/s, ETA %.1f min, fails=%d)",
                     i, len(dates), rate, eta_min, failures)

    elapsed = time.time() - t0
    log.info(
        "Done. dates=%d loaded=%d updated=%d failures=%d elapsed=%.1fs",
        len(dates), total_rows, total_updated, failures, elapsed,
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
