"""
Journal router — Cloud SQL-backed trade journal with local fallback.

Endpoints:
  GET    /api/journal/trades/{ticker}  — list all journal entries for a ticker
  POST   /api/journal/trades           — create a new journal entry (active or closed)
  PATCH  /api/journal/trades/{id}      — close an active trade (sets exit + return_pct/status)
  DELETE /api/journal/trades/{id}      — delete a journal entry by UUID
  GET    /api/journal/seed/{ticker}    — read-only admin seed from the pipeline `trades` table
  POST   /api/journal/export/{ticker}  — write pipeline-compatible CSV to data/signals/
"""
import csv
import json
import logging
import math
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Path setup ───────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SIGNALS_DIR = PROJECT_ROOT / "data" / "signals"
LOCAL_JOURNAL_DIR = PROJECT_ROOT / "data" / "journal"

# ── Cloud SQL availability check ─────────────────────────────────────────────
try:
    from gcp.database import is_cloud_sql_configured, query_to_dataframe, execute_sql
    _HAS_CLOUD_SQL: bool = is_cloud_sql_configured()
except Exception:
    _HAS_CLOUD_SQL = False

# Server-verified identity for per-user scoping.
from api.auth import current_user_email


# ── Query/exec indirections (testability) ────────────────────────────────────
# Every route calls through these instead of `query_to_dataframe`/`execute_sql`
# directly. They forward to the module-global name at CALL time (not at
# definition time), so tests can monkeypatch either this wrapper OR the
# underlying `journal.query_to_dataframe` / `journal.execute_sql` name — both
# take effect, which keeps the older test suites (that patch the plain names)
# working alongside new tests that patch the indirection directly.
def _journal_query(sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    return query_to_dataframe(sql, params)


def _journal_exec(sql: str, params: Optional[dict] = None) -> None:
    execute_sql(sql, params)


def _seed_query(sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    """Seed-layer query — RAISES on failure (unlike `_journal_query`).

    Mirrors `platform/api/main.py`'s `_coverage_query`: the seed endpoint has
    no fallback data source, so a real DB error must surface as a 503, never
    a silently-empty "no trades for this ticker/day" result (CLAUDE.md Rule
    3.7). Deferred import for the same reason as `_coverage_query`.
    """
    from gcp.database import query_to_dataframe_strict
    return query_to_dataframe_strict(sql, params)


def _journal_owner(request: Request) -> str:
    """Owner key the journal is scoped by.

    In firebase/iap mode (deployed) the middleware/IAP guarantees a verified
    identity on every gated /api/journal request, so this is the user's email
    and one user can never see another's trades. In open/local dev there is no
    auth, so all entries share the "local" owner — the journal keeps working
    offline and existing local data isn't stranded.
    """
    return current_user_email(request) or "local"


# ── Pydantic models ───────────────────────────────────────────────────────────

class JournalTradeCreate(BaseModel):
    ticker: str
    direction: str          # CALL | PUT
    entry_date: str         # YYYY-MM-DD
    entry_time: str         # HH:MM
    entry_price: float
    # Phase 2 (2026-07): exit_* become optional — an omitted exit means the
    # trade is still ACTIVE (unexited). return_pct/status are derived, never
    # fabricated (CLAUDE.md Rule 3.7 — missing exit stays NULL, not 0).
    exit_date: Optional[str] = None
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profits: Optional[list[float]] = None   # up to 3 levels -> tp1..tp3
    status: Optional[str] = None                 # derived if omitted
    source: str = "manual"                        # manual | chart | replay, etc.
    session_id: Optional[str] = None              # replay-trainer session grouping
    notes: Optional[str] = ""

    @field_validator("take_profits")
    @classmethod
    def _cap_take_profits(cls, v: Optional[list[float]]) -> Optional[list[float]]:
        if v is not None and len(v) > 3:
            raise ValueError("take_profits accepts at most 3 levels (tp1..tp3)")
        return v


class JournalTradeClose(BaseModel):
    """PATCH body to close an ACTIVE trade."""
    exit_date: str
    exit_time: str
    exit_price: float


class JournalTradeExportItem(BaseModel):
    id: str
    ticker: str
    direction: str
    entry_date: str
    entry_time: str
    entry_price: float
    exit_date: str
    exit_time: str
    exit_price: float
    notes: Optional[str] = ""


class ExportRequest(BaseModel):
    trades: list[JournalTradeExportItem]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _return_pct(direction: str, entry: float, exit_: float) -> float:
    if entry == 0:
        return 0.0
    pct = (exit_ - entry) / entry * 100
    return pct if direction.upper() == "CALL" else -pct


def _derive_status(has_exit: bool, return_pct: Optional[float]) -> str:
    """No exit yet -> active. Otherwise win/loss/breakeven by sign of return_pct."""
    if not has_exit:
        return "active"
    if return_pct is None:
        return "closed"
    if return_pct > 0:
        return "win"
    if return_pct < 0:
        return "loss"
    return "breakeven"


def _is_nan(v) -> bool:
    return isinstance(v, float) and math.isnan(v)


def _rows_to_trades(df: pd.DataFrame) -> list[dict]:
    """Cloud SQL rows -> JSON-safe trade dicts.

    Two things this fixes vs. the naive `.astype(str)` + `to_dict()` path:
      1. NaT/NaN become real ``None`` (never the literal string "NaT" that
         `.astype(str)` produces on a NaT — the 2.1 handoff bug: an active
         trade's NULL exit_ts must reach the client as JSON null).
      2. tp1/tp2/tp3 columns compact into a single `take_profits: [...]` list,
         dropping any NULL levels.
    """
    for col in ("entry_ts", "exit_ts", "created_at"):
        if col in df.columns:
            df[col] = df[col].apply(lambda v: None if pd.isna(v) else str(v))

    tp_cols = [c for c in ("tp1", "tp2", "tp3") if c in df.columns]
    trades: list[dict] = []
    for rec in df.to_dict(orient="records"):
        if tp_cols:
            tps = [rec.pop(c) for c in tp_cols]
            rec["take_profits"] = [tp for tp in tps if tp is not None and not _is_nan(tp)]
        for k, v in list(rec.items()):
            if _is_nan(v):
                rec[k] = None
        trades.append(rec)
    return trades


def _local_path(ticker: str) -> Path:
    LOCAL_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    return LOCAL_JOURNAL_DIR / f"{ticker.lower()}_journal.json"


def _load_local(ticker: str) -> list[dict]:
    p = _local_path(ticker)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text())
    except Exception:
        return []


def _save_local(ticker: str, entries: list[dict]) -> None:
    _local_path(ticker).write_text(json.dumps(entries, indent=2, default=str))


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/api/journal/trades/{ticker}")
async def get_trades(ticker: str, request: Request):
    """Return the signed-in user's journal entries for the ticker, newest first."""
    ticker_upper = ticker.upper()

    if _HAS_CLOUD_SQL:
        owner = _journal_owner(request)
        try:
            df = _journal_query(
                """
                SELECT id::text, ticker, direction,
                       entry_ts AT TIME ZONE 'UTC' AS entry_ts,
                       exit_ts  AT TIME ZONE 'UTC' AS exit_ts,
                       entry_price, exit_price, return_pct, notes,
                       stop_loss, tp1, tp2, tp3, status, source,
                       session_id::text AS session_id,
                       created_at AT TIME ZONE 'UTC' AS created_at
                FROM journal_entries
                WHERE ticker = :ticker AND user_email = :user_email
                ORDER BY entry_ts DESC
                """,
                {"ticker": ticker_upper, "user_email": owner},
            )
            trades = [] if df.empty else _rows_to_trades(df)
            return {"ticker": ticker_upper, "source": "cloud_sql", "count": len(trades), "trades": trades}
        except Exception:
            # Authenticated deployment (real owner): a Cloud SQL failure must NOT
            # fall back to the shared, owner-less local JSON file — that would
            # return another user's trades and silently serve stale data
            # (Rule 3.7). Fail loud. Only open/local dev (owner == "local", no
            # auth) uses the local fallback.
            if owner != "local":
                raise HTTPException(status_code=503, detail="journal temporarily unavailable")

    # Local fallback
    entries = _load_local(ticker_upper)
    entries.sort(key=lambda e: e.get("entry_ts", ""), reverse=True)
    return {"ticker": ticker_upper, "source": "local", "count": len(entries), "trades": entries}


@router.post("/api/journal/trades")
async def create_trade(trade: JournalTradeCreate, request: Request):
    """Insert a journal entry for the signed-in user. Returns it with its id.

    exit_date/exit_time/exit_price are optional — an omitted exit creates an
    ACTIVE trade (no return_pct/exit fields yet). status is derived from the
    exit outcome unless the caller supplies an explicit override.
    """
    ticker_upper = trade.ticker.upper()
    direction = trade.direction.upper()
    entry_ts = f"{trade.entry_date}T{trade.entry_time}:00"

    has_exit = trade.exit_date is not None and trade.exit_time is not None and trade.exit_price is not None
    exit_ts = f"{trade.exit_date}T{trade.exit_time}:00" if has_exit else None
    ret_pct = _return_pct(direction, trade.entry_price, trade.exit_price) if has_exit else None
    status = trade.status or _derive_status(has_exit, ret_pct)
    ret_pct_rounded = round(ret_pct, 4) if ret_pct is not None else None

    take_profits = trade.take_profits or []
    tp1 = take_profits[0] if len(take_profits) > 0 else None
    tp2 = take_profits[1] if len(take_profits) > 1 else None
    tp3 = take_profits[2] if len(take_profits) > 2 else None

    if _HAS_CLOUD_SQL:
        owner = _journal_owner(request)
        try:
            _journal_exec(
                """
                INSERT INTO journal_entries
                    (ticker, direction, entry_ts, exit_ts,
                     entry_price, exit_price, return_pct, notes, user_email,
                     stop_loss, tp1, tp2, tp3, status, source, session_id)
                VALUES
                    (:ticker, :direction, :entry_ts, :exit_ts,
                     :entry_price, :exit_price, :return_pct, :notes, :user_email,
                     :stop_loss, :tp1, :tp2, :tp3, :status, :source, :session_id)
                """,
                {
                    "ticker": ticker_upper,
                    "direction": direction,
                    "entry_ts": entry_ts,
                    "exit_ts": exit_ts,
                    "entry_price": trade.entry_price,
                    "exit_price": trade.exit_price,
                    "return_pct": ret_pct_rounded,
                    "notes": trade.notes or "",
                    "user_email": owner,
                    "stop_loss": trade.stop_loss,
                    "tp1": tp1,
                    "tp2": tp2,
                    "tp3": tp3,
                    "status": status,
                    "source": trade.source,
                    "session_id": trade.session_id,
                },
            )
            df = _journal_query(
                """
                SELECT id::text FROM journal_entries
                WHERE ticker = :ticker AND entry_ts = :entry_ts AND user_email = :user_email
                ORDER BY created_at DESC LIMIT 1
                """,
                {"ticker": ticker_upper, "entry_ts": entry_ts, "user_email": owner},
            )
            new_id = str(df["id"].iloc[0]) if not df.empty else str(uuid.uuid4())
            return {"source": "cloud_sql", "id": new_id, "return_pct": ret_pct_rounded, "status": status}
        except Exception:
            # Auth mode: never write to the shared owner-less local file (would
            # be visible to other users) — fail loud. Local fallback is open-dev
            # only. See get_trades for the full rationale.
            if owner != "local":
                raise HTTPException(status_code=503, detail="journal temporarily unavailable")

    # Local fallback
    entries = _load_local(ticker_upper)
    new_id = str(uuid.uuid4())
    entries.insert(0, {
        "id": new_id,
        "ticker": ticker_upper,
        "direction": direction,
        "entry_ts": entry_ts,
        "exit_ts": exit_ts,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "return_pct": ret_pct_rounded,
        "notes": trade.notes or "",
        "stop_loss": trade.stop_loss,
        "take_profits": take_profits,
        "status": status,
        "source": trade.source,
        "session_id": trade.session_id,
        "created_at": datetime.utcnow().isoformat(),
    })
    _save_local(ticker_upper, entries)
    return {"source": "local", "id": new_id, "return_pct": ret_pct_rounded, "status": status}


def _find_local_entry(trade_id: str) -> tuple[Optional[str], Optional[list[dict]], Optional[dict]]:
    """Scan every ticker's local journal file for `trade_id`.

    Returns (ticker, entries, entry) or (None, None, None) if not found.
    Mirrors the same all-files scan `delete_trade`'s local fallback already
    uses when no ticker is supplied.
    """
    LOCAL_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    for p in LOCAL_JOURNAL_DIR.glob("*_journal.json"):
        try:
            entries = json.loads(p.read_text())
        except Exception:
            continue
        for entry in entries:
            if entry.get("id") == trade_id:
                ticker = p.stem[: -len("_journal")].upper()
                return ticker, entries, entry
    return None, None, None


@router.patch("/api/journal/trades/{trade_id}")
async def close_trade(trade_id: str, body: JournalTradeClose, request: Request):
    """Close an ACTIVE trade: sets exit_ts/exit_price, computes return_pct
    (percent, via the existing `_return_pct`) and status win/loss/breakeven.

    404 if the trade doesn't exist (or isn't this owner's in Cloud SQL mode);
    409 if it's already closed.
    """
    exit_ts = f"{body.exit_date}T{body.exit_time}:00"

    if _HAS_CLOUD_SQL:
        owner = _journal_owner(request)
        try:
            df = _journal_query(
                """
                SELECT direction, entry_price, status
                FROM journal_entries
                WHERE id = :id AND user_email = :user_email
                """,
                {"id": trade_id, "user_email": owner},
            )
            if df.empty:
                raise HTTPException(status_code=404, detail="trade not found")
            row = df.iloc[0]
            if row["status"] != "active":
                raise HTTPException(status_code=409, detail="trade already closed")

            ret_pct = _return_pct(row["direction"], float(row["entry_price"]), body.exit_price)
            new_status = _derive_status(True, ret_pct)
            ret_pct_out = ret_pct

            _journal_exec(
                """
                UPDATE journal_entries
                SET exit_ts = :exit_ts, exit_price = :exit_price,
                    return_pct = :return_pct, status = :status
                WHERE id = :id AND user_email = :user_email
                """,
                {
                    "exit_ts": exit_ts,
                    "exit_price": body.exit_price,
                    "return_pct": ret_pct_out,
                    "status": new_status,
                    "id": trade_id,
                    "user_email": owner,
                },
            )
            return {"source": "cloud_sql", "id": trade_id, "return_pct": ret_pct_out, "status": new_status}
        except HTTPException:
            raise
        except Exception:
            # Auth mode: don't fall back to the cross-user local file. Fail loud.
            if owner != "local":
                raise HTTPException(status_code=503, detail="journal temporarily unavailable")

    # Local fallback: PATCH updates the JSON row directly.
    ticker, entries, entry = _find_local_entry(trade_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="trade not found")
    if entry.get("status") != "active":
        raise HTTPException(status_code=409, detail="trade already closed")

    ret_pct = _return_pct(entry["direction"], float(entry["entry_price"]), body.exit_price)
    new_status = _derive_status(True, ret_pct)
    ret_pct_out = ret_pct

    entry["exit_ts"] = exit_ts
    entry["exit_price"] = body.exit_price
    entry["return_pct"] = ret_pct_out
    entry["status"] = new_status
    _save_local(ticker, entries)
    return {"source": "local", "id": trade_id, "return_pct": ret_pct_out, "status": new_status}


@router.delete("/api/journal/trades/{trade_id}")
async def delete_trade(trade_id: str, request: Request, ticker: str = ""):
    """Delete one of the signed-in user's journal entries by UUID."""
    if _HAS_CLOUD_SQL:
        owner = _journal_owner(request)
        try:
            _journal_exec(
                "DELETE FROM journal_entries WHERE id = :id AND user_email = :user_email",
                {"id": trade_id, "user_email": owner},
            )
            return {"source": "cloud_sql", "deleted": trade_id}
        except Exception:
            # Auth mode: don't fall back to the cross-user local file. Fail loud.
            if owner != "local":
                raise HTTPException(status_code=503, detail="journal temporarily unavailable")

    # Local fallback
    if ticker:
        entries = _load_local(ticker.upper())
        updated = [e for e in entries if e.get("id") != trade_id]
        _save_local(ticker.upper(), updated)
    else:
        LOCAL_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        for p in LOCAL_JOURNAL_DIR.glob("*_journal.json"):
            try:
                entries = json.loads(p.read_text())
                updated = [e for e in entries if e.get("id") != trade_id]
                if len(updated) != len(entries):
                    p.write_text(json.dumps(updated, indent=2, default=str))
                    break
            except Exception:
                continue
    return {"source": "local", "deleted": trade_id}


@router.get("/api/journal/seed/{ticker}")
async def seed_trades(ticker: str, date: str):
    """Read-only admin seed pull from the automated pipeline `trades` table.

    Lets a user pre-populate the manual journal from what the signal engine
    already logged for a ticker/day. Cloud-SQL only — open/local dev returns
    an honest "unavailable" envelope rather than fabricating rows (Rule 3.7).
    A real Cloud SQL failure (as opposed to "not configured at all") surfaces
    as a 503, never a silently-empty trade list.
    """
    ticker_upper = ticker.upper()
    if not _HAS_CLOUD_SQL:
        return {"status": "unavailable", "reason": "seed layer requires Cloud SQL"}

    # no _CLOUD_SQL gate needed beyond the check above: get_engine() would
    # raise here too, caught below -> 503 (mirrors main.py's _coverage_query /
    # market_coverage pattern).
    try:
        df = _seed_query(
            """
            SELECT id, direction, entry_time, entry_price, exit_time, exit_price,
                   return_pct, strat_combo, exit_reason
            FROM trades
            WHERE ticker = :ticker AND trade_date = :date
            ORDER BY entry_time
            """,
            {"ticker": ticker_upper, "date": date},
        )
    except Exception as e:
        logger.error("journal seed query failed: %s", e)
        raise HTTPException(status_code=503, detail=f"seed query failed: {type(e).__name__}")

    trades: list[dict] = []
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            raw_return = row.get("return_pct")
            trades.append({
                "id": str(row["id"]),
                "direction": row.get("direction"),
                "entry_time": None if pd.isna(row.get("entry_time")) else str(row.get("entry_time")),
                "entry_price": None if pd.isna(row.get("entry_price")) else float(row.get("entry_price")),
                "exit_time": None if pd.isna(row.get("exit_time")) else str(row.get("exit_time")),
                "exit_price": None if pd.isna(row.get("exit_price")) else float(row.get("exit_price")),
                # pipeline `trades.return_pct` is a RAW FRACTION (e.g. 0.003 ==
                # 0.3%); the journal's own return_pct is TRUE PERCENT
                # everywhere else in this API, so convert here (×100) to keep
                # the seed response in the same units as the rest of the
                # journal endpoints.
                "return_pct": None if pd.isna(raw_return) else float(raw_return) * 100,
                "strat_combo": row.get("strat_combo"),
                "exit_reason": row.get("exit_reason"),
            })

    return {"ticker": ticker_upper, "date": date, "count": len(trades), "trades": trades}


@router.post("/api/journal/export/{ticker}")
async def export_trades(ticker: str, request: ExportRequest):
    """Write journal trades to {ticker}_trade_tracker.csv in data/signals/."""
    ticker_lower = ticker.lower()
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = SIGNALS_DIR / f"{ticker_lower}_trade_tracker.csv"

    fieldnames = ["ID", "Time", "Trade_Type", "Exit_Time", "Stop_Loss_Time", "Runner_Time"]
    rows = []
    for i, trade in enumerate(request.trades, start=1):
        rows.append({
            "ID": i,
            "Time": f"{trade.entry_date} {trade.entry_time}:00",
            "Trade_Type": trade.direction.upper(),
            "Exit_Time": f"{trade.exit_date} {trade.exit_time}:00",
            "Stop_Loss_Time": "",
            "Runner_Time": "",
        })

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {
        "success": True,
        "trades_exported": len(rows),
        "output_path": str(output_path),
        "filename": output_path.name,
    }
