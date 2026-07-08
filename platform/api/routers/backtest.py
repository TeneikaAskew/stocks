"""
Backtest router — reads directly from GCS with in-memory TTL caching.

Endpoints
---------
GET /api/backtest/results/{ticker}
    Return trades from the most recent backtest CSV for the given ticker.

GET /api/backtest/equity/{ticker}
    Return equity curve from the most recent equity CSV for the given ticker.

GET /api/backtest/all/{ticker}
    List all backtest runs for a ticker, sorted newest first, with summary metrics.

Data source
-----------
All reads come from gs://adept-mountain-474619-d4-trading-data/raw/data/backtest_results/
via `api.gcs_reader`. No local filesystem reads. TTLCache layers keep repeat
requests fast — first request per (ticker, variant) pays the GCS download cost,
subsequent requests in the TTL window are in-memory.

Cache TTLs:
  * `/results/{ticker}`  — 1h (backtest runs rarely; data is immutable once written)
  * `/equity/{ticker}`   — 1h
  * `/all/{ticker}`      — 10m (listing can change as new runs land)

Units
-----
The BacktestEngine writes `return_pct` as a raw fraction (0.003 = 0.3%).
Every `*_pct` field this router emits — `avg_return_pct`, `avg_win_pct`,
`avg_loss_pct`, `total_return_pct`, per-trade `return_pct` — is converted
to TRUE PERCENT units (fraction * 100) so the frontend can render
`${v.toFixed(2)}%` without unit knowledge. `win_rate` is the only
exception: it stays a 0-1 fraction (the UI multiplies by 100 itself).
"""
import json
import logging
import math
import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

# Project root so we can import from sibling packages
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import the shared GCS reader. The `api` package is platform/api/.
from api import gcs_reader  # noqa: E402

# Single source of truth for the labeled-trade replay math (Task 3.2) — the
# router only loads data and shapes the HTTP contract; all scoring/benchmark
# math lives in lib/backtest.py (CLAUDE.md: "lib/ is the shared backend spine").
from lib.backtest import replay_labeled_trades  # noqa: E402

# Task 4.2/4.3 — style mining + labeled walk-forward. Same "lib/ is the
# shared backend spine" rule: the router only loads data, filters to closed
# trades, and shapes the HTTP contract; all mining/scoring math lives in
# lib/style_miner.py and lib/walk_forward.py.
from lib.style_miner import mine_style  # noqa: E402
from lib.walk_forward import WalkForwardValidator  # noqa: E402
from lib.config import load_config  # noqa: E402

# Owner scoping — the SAME per-user Cloud SQL scoping journal_entries reads
# use elsewhere (platform/api/routers/journal.py). Imported rather than
# duplicated so the two routers can never drift on what "owner" means.
from .journal import _journal_owner  # noqa: E402

try:
    from gcp.database import is_cloud_sql_configured, query_to_dataframe, execute_sql
    _HAS_CLOUD_SQL: bool = is_cloud_sql_configured()
except Exception:
    _HAS_CLOUD_SQL = False
    query_to_dataframe = None  # type: ignore[assignment]
    execute_sql = None  # type: ignore[assignment]

log = logging.getLogger(__name__)
router = APIRouter()

# GCS prefix (relative to the `raw/` BASE_PREFIX in gcs_reader)
GCS_PREFIX = "data/backtest_results/"

# Filename patterns — anchored and escaped
def _backtest_pattern(ticker_upper: str, run: str | None = None) -> str:
    if run:
        return rf"^backtest_{re.escape(ticker_upper)}_{re.escape(run)}\.csv$"
    return rf"^backtest_{re.escape(ticker_upper)}_\d{{8}}_\d{{6}}\.csv$"

def _equity_pattern(ticker_upper: str, run: str | None = None) -> str:
    if run:
        return rf"^equity_{re.escape(ticker_upper)}_{re.escape(run)}\.csv$"
    return rf"^equity_{re.escape(ticker_upper)}_\d{{8}}_\d{{6}}\.csv$"

# ── Caches ──────────────────────────────────────────────────────────────────
_RESULTS_CACHE: TTLCache = TTLCache(maxsize=32, ttl=3600)   # 1h
_EQUITY_CACHE: TTLCache = TTLCache(maxsize=32, ttl=3600)    # 1h
_ALL_RUNS_CACHE: TTLCache = TTLCache(maxsize=16, ttl=600)   # 10m


# ── Helpers ─────────────────────────────────────────────────────────────────

def _timestamp_from_name(basename: str) -> str:
    """Extract YYYYMMDD_HHMMSS from backtest_TICKER_YYYYMMDD_HHMMSS.csv."""
    stem = basename.rsplit(".", 1)[0]  # drop .csv
    parts = stem.split("_")
    return "_".join(parts[2:]) if len(parts) >= 4 else ""


def _dataframe_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to list[dict], replacing NaN with None and numerics → float."""
    df = df.where(pd.notna(df), other=None)
    for col in df.select_dtypes(include="number").columns:
        df[col] = df[col].apply(lambda x: float(x) if x is not None else None)
    return df.to_dict(orient="records")


def _summarize_returns(df: pd.DataFrame) -> dict:
    """Summary stats. UNITS: the engine writes return_pct as a raw fraction
    (0.003 = 0.3%). Every *_pct field emitted here is converted to TRUE
    PERCENT; win_rate stays a 0-1 fraction (UI renders *100)."""
    summary: dict = {}
    if "return_pct" not in df.columns:
        return summary
    returns = df["return_pct"].dropna().astype(float) * 100.0  # fraction -> percent
    if len(returns) == 0:
        return summary
    wins = returns[returns > 0]
    losses = returns[returns <= 0]
    summary = {
        "total_trades": len(returns),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(len(wins) / len(returns), 4),
        "avg_return_pct": round(returns.mean(), 4),
        "avg_win_pct": round(wins.mean(), 4) if len(wins) else None,
        "avg_loss_pct": round(losses.mean(), 4) if len(losses) else None,
        "total_return_pct": round(returns.sum(), 4),
    }
    return summary


def _trades_to_percent_records(df: pd.DataFrame) -> list[dict]:
    """Per-trade records with return_pct converted fraction -> percent."""
    df = df.copy()
    if "return_pct" in df.columns:
        df["return_pct"] = df["return_pct"].astype(float) * 100.0
    return _dataframe_to_records(df)


# ── Endpoints ───────────────────────────────────────────────────────────────

def _validate_run(run: str | None) -> None:
    if run and not re.fullmatch(r"\d{8}_\d{6}", run):
        raise HTTPException(status_code=422, detail="run must be YYYYMMDD_HHMMSS")


@router.get("/api/backtest/results/{ticker}")
async def get_backtest_results(ticker: str, run: str | None = None):
    """Return trades from the most recent backtest CSV for the given ticker,
    or from a specific run if `run=YYYYMMDD_HHMMSS` is provided."""
    ticker_upper = ticker.upper()
    _validate_run(run)
    cache_key = f"{ticker_upper}:{run or 'latest'}"

    if cache_key in _RESULTS_CACHE:
        return _RESULTS_CACHE[cache_key]

    blobs = gcs_reader.list_matching_blobs(GCS_PREFIX, _backtest_pattern(ticker_upper, run))
    if not blobs:
        raise HTTPException(
            status_code=404,
            detail=f"No backtest results found in GCS for ticker '{ticker_upper}'",
        )

    blob_name = blobs[0]
    filename = blob_name.rsplit("/", 1)[-1]
    try:
        df = gcs_reader.download_csv(blob_name)
    except Exception as exc:
        log.error("Failed to download %s: %s", blob_name, exc)
        raise HTTPException(status_code=502, detail=f"Failed to download backtest CSV from GCS: {exc}")

    if df.empty:
        resp = {
            "ticker": ticker_upper,
            "filename": filename,
            "trade_count": 0,
            "summary": {},
            "trades": [],
        }
        _RESULTS_CACHE[cache_key] = resp
        return resp

    summary = _summarize_returns(df)
    trades = _trades_to_percent_records(df)
    resp = {
        "ticker": ticker_upper,
        "filename": filename,
        "trade_count": len(trades),
        "summary": summary,
        "trades": trades,
    }
    _RESULTS_CACHE[cache_key] = resp
    return resp


@router.get("/api/backtest/equity/{ticker}")
async def get_equity_curve(ticker: str, run: str | None = None):
    """Return equity curve from the most recent equity CSV for the given ticker,
    or from a specific run if `run=YYYYMMDD_HHMMSS` is provided."""
    ticker_upper = ticker.upper()
    _validate_run(run)
    cache_key = f"{ticker_upper}:{run or 'latest'}"

    if cache_key in _EQUITY_CACHE:
        return _EQUITY_CACHE[cache_key]

    blobs = gcs_reader.list_matching_blobs(GCS_PREFIX, _equity_pattern(ticker_upper, run))
    if not blobs:
        raise HTTPException(
            status_code=404,
            detail=f"No equity curve found in GCS for ticker '{ticker_upper}'",
        )

    blob_name = blobs[0]
    filename = blob_name.rsplit("/", 1)[-1]
    try:
        df = gcs_reader.download_csv(blob_name)
    except Exception as exc:
        log.error("Failed to download %s: %s", blob_name, exc)
        raise HTTPException(status_code=502, detail=f"Failed to download equity CSV from GCS: {exc}")

    if df.empty:
        resp = {"ticker": ticker_upper, "filename": filename, "summary": {}, "dates": [], "values": []}
        _EQUITY_CACHE[cache_key] = resp
        return resp

    # Equity CSVs have: "Unnamed: 0" (date index) and "0" (equity value)
    date_col = None
    value_col = None
    for col in df.columns:
        if col in ("Unnamed: 0", "date", "Date", "index"):
            date_col = col
        elif col in ("0", "equity", "Equity", "value", "Value"):
            value_col = col

    # Fallback: first col = date, second col = value
    if date_col is None and len(df.columns) >= 1:
        date_col = df.columns[0]
    if value_col is None and len(df.columns) >= 2:
        value_col = df.columns[1]

    dates = df[date_col].astype(str).tolist() if date_col else []
    values = [float(v) if pd.notna(v) else None for v in df[value_col]] if value_col else []

    # Summary stats
    clean_values = [v for v in values if v is not None]
    summary: dict = {}
    if clean_values:
        start_val = clean_values[0]
        end_val = clean_values[-1]
        peak = max(clean_values)
        trough_after_peak = min(clean_values[clean_values.index(peak):])
        max_drawdown = (trough_after_peak - peak) / peak if peak != 0 else 0.0
        total_return = (end_val - start_val) / start_val if start_val != 0 else 0.0
        summary = {
            "start_value": round(start_val, 4),
            "end_value": round(end_val, 4),
            "peak_value": round(peak, 4),
            "total_return_pct": round(total_return * 100, 4),
            "max_drawdown_pct": round(max_drawdown * 100, 4),
            "data_points": len(clean_values),
        }

    resp = {
        "ticker": ticker_upper,
        "filename": filename,
        "summary": summary,
        "dates": dates,
        "values": values,
    }
    _EQUITY_CACHE[cache_key] = resp
    return resp


@router.get("/api/backtest/all/{ticker}")
async def list_all_backtests(ticker: str):
    """List all backtest runs for a ticker, sorted by timestamp descending."""
    ticker_upper = ticker.upper()

    if ticker_upper in _ALL_RUNS_CACHE:
        return _ALL_RUNS_CACHE[ticker_upper]

    backtest_blobs = gcs_reader.list_matching_blobs(GCS_PREFIX, _backtest_pattern(ticker_upper))
    if not backtest_blobs:
        raise HTTPException(
            status_code=404,
            detail=f"No backtest files found in GCS for ticker '{ticker_upper}'",
        )

    # Pre-fetch equity blob list so we can check existence without another LIST call per file
    equity_blobs = set(gcs_reader.list_matching_blobs(GCS_PREFIX, _equity_pattern(ticker_upper)))

    runs = []
    for blob_name in backtest_blobs:
        filename = blob_name.rsplit("/", 1)[-1]
        timestamp = _timestamp_from_name(filename)

        info = {
            "filename": filename,
            "path": f"gs://{gcs_reader.BUCKET}/{blob_name}",
            "timestamp": timestamp,
            # modified/size_bytes are not available without extra metadata fetches;
            # frontend doesn't use them as sort keys since we already sort by timestamp
            "modified": None,
            "size_bytes": None,
            "row_count": None,
        }

        # Does an equity curve exist for this run?
        equity_blob = f"{gcs_reader.BASE_PREFIX}{GCS_PREFIX}equity_{ticker_upper}_{timestamp}.csv"
        info["has_equity_curve"] = equity_blob in equity_blobs

        # Load minimal stats: just return_pct column
        try:
            df = gcs_reader.download_csv(blob_name)
            if "return_pct" in df.columns:
                returns = df["return_pct"].dropna().astype(float)
                wins = returns[returns > 0]
                info["trade_count"] = len(returns)
                info["row_count"] = len(returns)
                info["win_rate"] = round(len(wins) / len(returns), 4) if len(returns) else None
                info["avg_return_pct"] = round(returns.mean() * 100.0, 4) if len(returns) else None
            else:
                info["trade_count"] = len(df)
                info["row_count"] = len(df)
                info["win_rate"] = None
                info["avg_return_pct"] = None
        except Exception as exc:
            log.warning("Failed to load stats for %s: %s", blob_name, exc)
            info["trade_count"] = None
            info["win_rate"] = None
            info["avg_return_pct"] = None

        runs.append(info)

    resp = {
        "ticker": ticker_upper,
        "total_runs": len(runs),
        "runs": runs,
    }
    _ALL_RUNS_CACHE[ticker_upper] = resp
    return resp


# ── POST /api/backtest/replay-trades (Task 3.2) ──────────────────────────────
#
# Scores the caller's own labeled journal trades against actual bars and
# benchmarks them against BacktestEngine.simulate_exit (Task 3.1). Capacity
# (CLAUDE.md Rule 0): per-request pandas over <= trades x 390 bars; one SELECT
# for the matched journal rows + one SELECT per distinct entry date for bars
# (via main.py's _load_date_data — Cloud SQL primary, GCS fallback); no DB
# writes. All scoring math lives in lib.backtest.replay_labeled_trades.


class ReplayTradesRequest(BaseModel):
    ticker: str
    trade_ids: Optional[list[str]] = None
    session_id: Optional[str] = None


def _replay_bar_loader(ticker_lower: str, date: str) -> pd.DataFrame:
    """Indirection over main.py's `_load_date_data` (Cloud SQL primary, GCS
    fallback — the same loader /api/market/data uses) so tests can
    monkeypatch bar loading without touching the network. Deferred import
    avoids a circular import: main.py imports this router at app startup."""
    from api.main import _load_date_data
    return _load_date_data(ticker_lower, date)


def _replay_journal_query(sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    """Indirection over the Cloud SQL query helper, mirroring journal.py's
    `_journal_query` pattern (forwards to the module-global name at CALL
    time so tests can monkeypatch this wrapper directly)."""
    return query_to_dataframe(sql, params)


def _normalize_bars_for_replay(df: pd.DataFrame) -> pd.DataFrame:
    """`_load_date_data` returns lowercase open/high/low/close/volume columns
    with a DatetimeIndex (no 'Time' column) — main.py's /api/market/data
    endpoint does its own column normalization inline for the chart;
    lib.backtest / lib.signals need the same uppercase OHLCV columns PLUS a
    'Time' column (VWAP session grouping, entry-bar minute matching) with a
    plain positional (0..n-1) index so `entry_idx` from the minute-match
    lookup is a valid `.iloc` position."""
    out = df.copy()
    col_map = {c: c.capitalize() for c in out.columns
               if c.lower() in ("open", "high", "low", "close", "volume")}
    out = out.rename(columns=col_map)
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index)
    out = out.sort_index()
    out["Time"] = out.index.astype(str)
    return out.reset_index(drop=True)


@router.post("/api/backtest/replay-trades")
async def replay_trades(body: ReplayTradesRequest, request: Request):
    """Score the signed-in user's labeled journal trades against actual bars
    and benchmark them against the system (Task 3.2). 422 if neither
    `trade_ids` nor `session_id` is given; 404 if nothing matches; strict
    fail-loud (uncaught exception -> 500) on any Cloud SQL error loading the
    journal rows or the bars — never a silent empty/zero-filled result
    (CLAUDE.md Rule 3.7)."""
    if not body.trade_ids and not body.session_id:
        raise HTTPException(status_code=422, detail="trade_ids or session_id is required")

    if not _HAS_CLOUD_SQL:
        raise HTTPException(status_code=503, detail="journal database not configured")

    ticker_upper = body.ticker.upper()
    owner = _journal_owner(request)

    conditions = []
    params: dict = {"ticker": ticker_upper, "user_email": owner}
    if body.trade_ids:
        conditions.append("id::text = ANY(:trade_ids)")
        params["trade_ids"] = list(body.trade_ids)
    if body.session_id:
        conditions.append("session_id::text = :session_id")
        params["session_id"] = body.session_id
    where_clause = " OR ".join(conditions)

    df = _replay_journal_query(
        f"""
        SELECT id::text, direction,
               entry_ts AT TIME ZONE 'UTC' AS entry_ts,
               exit_ts  AT TIME ZONE 'UTC' AS exit_ts,
               entry_price, exit_price
        FROM journal_entries
        WHERE ticker = :ticker AND user_email = :user_email AND ({where_clause})
        ORDER BY entry_ts
        """,
        params,
    )

    if df.empty:
        raise HTTPException(status_code=404, detail="no matching trades found")

    for col in ("entry_ts", "exit_ts"):
        df[col] = df[col].apply(lambda v: None if pd.isna(v) else str(v))

    labeled: list[dict] = []
    for rec in df.to_dict(orient="records"):
        exit_price = rec.get("exit_price")
        if isinstance(exit_price, float) and math.isnan(exit_price):
            exit_price = None
        labeled.append({
            "id": rec["id"],
            "direction": rec["direction"],
            "entry_ts": rec["entry_ts"],
            "entry_price": rec["entry_price"],
            "exit_ts": rec["exit_ts"],
            "exit_price": exit_price,
        })

    # Load bars for every distinct entry date. A date with genuinely no data
    # (FileNotFoundError from _load_date_data) is NOT a DB failure — it's
    # left out of bars_by_date so replay_labeled_trades marks that date's
    # trades "unavailable" / "no bars for date" (never zero-filled). Any
    # OTHER exception (real Cloud SQL/GCS failure) propagates — fail loud.
    ticker_lower = ticker_upper.lower()
    distinct_dates = sorted({
        pd.to_datetime(t["entry_ts"]).strftime("%Y-%m-%d")
        for t in labeled if t["entry_ts"]
    })

    bars_by_date: dict[str, pd.DataFrame] = {}
    for date_key in distinct_dates:
        try:
            raw_df = _replay_bar_loader(ticker_lower, date_key.replace("-", ""))
        except FileNotFoundError:
            log.info("replay-trades: no bars for %s on %s", ticker_upper, date_key)
            continue
        if raw_df is None or raw_df.empty:
            continue
        bars_by_date[date_key] = _normalize_bars_for_replay(raw_df)

    return replay_labeled_trades(labeled, bars_by_date, ticker=ticker_upper)


# ── POST /api/style/mine-and-validate (Task 4.3) ─────────────────────────────
#
# Mines the caller's own closed chart/manual journal trades into a condition
# profile (lib.style_miner, Task 4.2), walk-forward validates the top profile
# against the ticker's own recent bar history (lib.walk_forward.
# WalkForwardValidator.run_profile, Task 4.3), and stages the result: one
# archival row in `user_style_results` + one upserted candidate card in
# `playbook_cards_staging`. Runs synchronously per request; see
# `_style_history_bar_loader` for the 6-month scope that keeps wall-clock
# inside Cloud Run's request budget (measured wall-clock reported in the PR
# description per the Task 4.3 capacity note).
#
# Playbook staging seam (spec §8 / schema.sql comment on
# playbook_cards_staging): candidates land in the STAGING table only. The
# admin-facing playbook UI reads `playbook_cards`, never `playbook_cards_staging`
# — flipping that is a later program's decision, gated by this flag.
PLAYBOOK_USER_CARDS = False


class MineAndValidateRequest(BaseModel):
    ticker: str


def _style_history_bar_loader(ticker_upper: str) -> pd.DataFrame:
    """Bar history for the walk-forward validation step of Task 4.3.

    Reuses `lib.data_loader.DataLoader.load_best_available` — the SAME
    loader `scripts/run_backtest.py`'s `--walk-forward` CLI path uses
    (`scripts/run_backtest.py:129`; Cloud SQL `market_data_intraday`
    primary, local-parquet fallback via `DataLoader.load_intraday` ->
    `load_daily`). Scoped to the last 6 months (Task 4.3 capacity note: a
    synchronous per-request endpoint can't afford a full-history
    walk-forward within Cloud Run's request budget) — module-level
    indirection so tests can monkeypatch bar loading without touching Cloud
    SQL, mirroring `_replay_bar_loader` (Task 3.2).
    """
    from lib.data_loader import DataLoader
    end = pd.Timestamp.utcnow().normalize()
    start = end - pd.DateOffset(months=6)
    return DataLoader().load_best_available(
        ticker_upper, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"),
    )


def _style_exec(sql: str, params: Optional[dict] = None) -> None:
    """Indirection over `gcp.database.execute_sql` for the
    `user_style_results` / `playbook_cards_staging` writes, mirroring
    journal.py's `_journal_exec` — lets tests monkeypatch persistence
    without touching Cloud SQL. Forwards to the module-global
    `execute_sql` name at CALL time (not definition time)."""
    execute_sql(sql, params)


def _is_closed_journal_entry(row: dict) -> bool:
    """CLOSED = status in {win, loss, breakeven} AND exit_ts is present.

    Applied in PYTHON, independent of any SQL-layer filtering, per Task 4.3's
    hard seam: `lib.style_miner.mine_style` trusts its caller completely —
    it does NOT re-derive "closed" from exit fields (see its module
    docstring). An 'active' row slipping through here would poison the
    mined profile with a trade that never resolved. Never zero-filled or
    assumed-closed on a NULL status (CLAUDE.md Rule 3.7): a missing/unknown
    status is treated as NOT closed.
    """
    status = str(row.get("status") or "").lower()
    return status in ("win", "loss", "breakeven") and bool(row.get("exit_ts"))


def _select_top_style_profile(profiles: list):
    """Highest support fraction wins; ties broken by MORE conditions (a
    richer, more specific condition set beats a sparser one at equal support)
    — Task 4.3 spec: 'walk-forwards the TOP profile (highest support
    fraction; tie -> more conditions)'."""
    return max(
        profiles,
        key=lambda p: (p.support / p.total if p.total else 0.0, len(p.conditions)),
    )


def _walk_forward_metrics_to_percent(agg: dict) -> dict:
    """Convert every `_aggregate_metrics` key ending in `_pct` from the
    engine's raw-fraction convention to TRUE PERCENT (fraction * 100) — the
    same convention this router's `_summarize_returns` / module docstring
    document. Win-rate-derived keys (e.g. `avg_win_rate`) are already a 0-1
    fraction and are left untouched; only keys literally ending in `_pct`
    are converted."""
    out = dict(agg)
    for k, v in agg.items():
        if k.endswith("_pct") and isinstance(v, (int, float)):
            out[k] = v * 100.0
    return out


@router.post("/api/style/mine-and-validate")
async def mine_and_validate(body: MineAndValidateRequest, request: Request):
    """Mine the caller's closed journal trades into a condition profile,
    walk-forward validate the top one, and stage the result (Task 4.3).

    200 `{"status": "unavailable", "reason": ...}` (never a 4xx/5xx) for
    every "not enough signal yet" case — too few closed trades, or mining
    produced no profile for either direction — since these are expected,
    recoverable states for a user early in their journal history, not
    errors. A genuine Cloud SQL failure still propagates as a 5xx (Rule
    3.7 — INTERNAL failures fail loud, never a fabricated empty result).
    """
    if not _HAS_CLOUD_SQL:
        raise HTTPException(status_code=503, detail="journal database not configured")

    ticker_upper = body.ticker.upper()
    owner = _journal_owner(request)

    # Chart/manual only (spec: "closed chart/manual journal trades") —
    # replay-trainer sessions are simulated practice, not the user's actual
    # trading style, so they're excluded from the mining input.
    df = _replay_journal_query(
        """
        SELECT id::text, direction, status, source,
               entry_ts AT TIME ZONE 'UTC' AS entry_ts,
               exit_ts  AT TIME ZONE 'UTC' AS exit_ts,
               entry_price, exit_price
        FROM journal_entries
        WHERE ticker = :ticker AND user_email = :user_email
          AND source IN ('manual', 'chart')
        ORDER BY entry_ts
        """,
        {"ticker": ticker_upper, "user_email": owner},
    )

    records: list[dict] = [] if df.empty else df.to_dict(orient="records")
    for rec in records:
        for col in ("entry_ts", "exit_ts"):
            rec[col] = None if pd.isna(rec.get(col)) else str(rec[col])

    closed_entries = [r for r in records if _is_closed_journal_entry(r)]

    if len(closed_entries) < 10:
        return {
            "status": "unavailable",
            "reason": f"need >= 10 closed trades, have {len(closed_entries)}",
        }

    # Snapshot indicator/condition state at each closed entry's bar via the
    # existing Task 3.2 intraday-bar-loading pattern (same loader + reshape
    # `/api/backtest/replay-trades` uses — see `_replay_bar_loader` /
    # `_normalize_bars_for_replay` above).
    ticker_lower = ticker_upper.lower()
    distinct_dates = sorted({
        pd.to_datetime(e["entry_ts"]).strftime("%Y-%m-%d")
        for e in closed_entries if e["entry_ts"]
    })

    bars_by_date: dict[str, pd.DataFrame] = {}
    for date_key in distinct_dates:
        try:
            raw_df = _replay_bar_loader(ticker_lower, date_key.replace("-", ""))
        except FileNotFoundError:
            log.info("mine-and-validate: no bars for %s on %s", ticker_upper, date_key)
            continue
        if raw_df is None or raw_df.empty:
            continue
        bars_by_date[date_key] = _normalize_bars_for_replay(raw_df)

    profiles = mine_style(closed_entries, bars_by_date)
    if not profiles:
        return {
            "status": "unavailable",
            "reason": "no condition profile cleared the mining threshold for either direction",
        }

    top_profile = _select_top_style_profile(profiles)

    # Ticker's own calibrated risk/exit/strat/indicator config (same config
    # `scripts/run_backtest.py` loads) so validation reflects the real
    # targets/stops a live trade would experience. The SIGNAL config is the
    # one exception — `WalkForwardValidator.run_profile` always overrides it
    # via `profile_to_signal_config`'s fresh `SignalConfig()` base (hard seam
    # #2: the miner mined at defaults, so validating against a per-ticker
    # signal override would score the profile against a vocabulary it was
    # never mined against). See `lib.walk_forward.profile_to_signal_config`.
    cfg = load_config(ticker=ticker_upper)

    bars_df = _style_history_bar_loader(ticker_upper)
    if bars_df is None or bars_df.empty:
        return {
            "status": "unavailable",
            "reason": f"no market data available for {ticker_upper}",
        }
    close_col = "Close" if "Close" in bars_df.columns else "Last"

    # train_months=3/test_months=1 (rather than WalkForwardConfig's 6/1
    # default): the endpoint scopes bar history to the last 6 months (see
    # `_style_history_bar_loader`), and a 6-month train window would consume
    # the ENTIRE scoped window as training, leaving zero out-of-sample test
    # folds. 3/1 guarantees multiple folds within the 6-month scope.
    validator = WalkForwardValidator(
        risk_config=cfg.risk,
        exit_config=cfg.exit,
        strat_config=cfg.strat,
        backtest_config=cfg.backtest,
        indicator_config=cfg.indicator,
        walk_forward_config=cfg.walk_forward,
        train_months=3,
        test_months=1,
    )
    wf_result = validator.run_profile(bars_df, top_profile, close_col=close_col)

    agg_percent = _walk_forward_metrics_to_percent(wf_result.aggregate_metrics)
    total_folds = int(agg_percent.get("total_folds", 0))
    if total_folds == 0:
        # Empty fold_results (e.g. the ticker's scoped 6-month bar history
        # is too short for even one 3mo-train/1mo-test fold) means NO
        # validation actually ran — persisting a "staged: true" candidate
        # off zero folds would be a fabricated result (CLAUDE.md Rule 3.7).
        return {
            "status": "unavailable",
            "reason": (
                f"insufficient bar history for {ticker_upper} to "
                "walk-forward validate the mined profile"
            ),
        }
    avg_expectancy_pct = agg_percent.get("avg_expectancy_pct")
    avg_win_rate = agg_percent.get("avg_win_rate")
    total_trades = int(agg_percent.get("total_trades_all_folds", 0))

    profile_dict = {
        "direction": top_profile.direction,
        "conditions": top_profile.conditions,
        "support": top_profile.support,
        "total": top_profile.total,
    }

    # One archival row per mine-and-validate run — an append-only history of
    # what was mined/validated over time (idx_user_style_results_user is
    # ordered `created_at DESC`), so this is a plain INSERT, not an upsert.
    _style_exec(
        """
        INSERT INTO user_style_results
            (user_email, ticker, profile, trained_on_trades,
             avg_expectancy_pct, avg_win_rate, stability_score,
             total_folds, total_trades)
        VALUES
            (:user_email, :ticker, :profile::jsonb, :trained_on_trades,
             :avg_expectancy_pct, :avg_win_rate, :stability_score,
             :total_folds, :total_trades)
        """,
        {
            "user_email": owner,
            "ticker": ticker_upper,
            "profile": json.dumps(profile_dict),
            "trained_on_trades": len(closed_entries),
            "avg_expectancy_pct": avg_expectancy_pct,
            "avg_win_rate": avg_win_rate,
            "stability_score": wf_result.stability_score,
            "total_folds": total_folds,
            "total_trades": total_trades,
        },
    )

    # Candidate playbook card — conflict-safe upsert keyed on
    # (user_email, ticker, name) so re-running mine-and-validate for the same
    # ticker/direction updates the existing candidate in place rather than
    # accumulating stale duplicates. `name` is deterministic per direction so
    # a user has at most one staged candidate per (ticker, direction).
    card_name = f"Mined {top_profile.direction} Style"
    _style_exec(
        """
        INSERT INTO playbook_cards_staging
            (user_email, ticker, name, direction, conditions,
             win_rate, avg_return_bps, sample_n, status, generated_at)
        VALUES
            (:user_email, :ticker, :name, :direction, :conditions::jsonb,
             :win_rate, :avg_return_bps, :sample_n, 'candidate', NOW())
        ON CONFLICT (user_email, ticker, name) DO UPDATE SET
            direction      = EXCLUDED.direction,
            conditions     = EXCLUDED.conditions,
            win_rate       = EXCLUDED.win_rate,
            avg_return_bps = EXCLUDED.avg_return_bps,
            sample_n       = EXCLUDED.sample_n,
            status         = 'candidate',
            generated_at   = NOW()
        """,
        {
            "user_email": owner,
            "ticker": ticker_upper,
            "name": card_name,
            "direction": top_profile.direction,
            "conditions": json.dumps(top_profile.conditions),
            "win_rate": avg_win_rate,
            # percent -> bps: 1% == 100 bps, and avg_expectancy_pct is
            # already TRUE PERCENT (converted above), so *100 again.
            "avg_return_bps": (avg_expectancy_pct * 100.0
                                if avg_expectancy_pct is not None else None),
            "sample_n": total_trades,
        },
    )

    return {
        "profile": profile_dict,
        "aggregate_metrics": agg_percent,
        "stability_score": wf_result.stability_score,
        "staged": True,
    }
