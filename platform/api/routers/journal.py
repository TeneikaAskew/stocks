"""
Journal router — Cloud SQL-backed trade journal with local fallback.

Endpoints:
  GET    /api/journal/trades/{ticker}  — list all journal entries for a ticker
  POST   /api/journal/trades           — create a new journal entry
  DELETE /api/journal/trades/{id}      — delete a journal entry by UUID
  POST   /api/journal/export/{ticker}  — write pipeline-compatible CSV to data/signals/
"""
import csv
import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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
    exit_date: str
    exit_time: str
    exit_price: float
    notes: Optional[str] = ""


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
            df = query_to_dataframe(
                """
                SELECT id::text, ticker, direction,
                       entry_ts AT TIME ZONE 'UTC' AS entry_ts,
                       exit_ts  AT TIME ZONE 'UTC' AS exit_ts,
                       entry_price, exit_price, return_pct, notes,
                       created_at AT TIME ZONE 'UTC' AS created_at
                FROM journal_entries
                WHERE ticker = :ticker AND user_email = :user_email
                ORDER BY entry_ts DESC
                """,
                {"ticker": ticker_upper, "user_email": owner},
            )
            if df.empty:
                trades = []
            else:
                for col in ("entry_ts", "exit_ts", "created_at"):
                    if col in df.columns:
                        df[col] = df[col].astype(str)
                trades = df.to_dict(orient="records")
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
    """Insert a journal entry for the signed-in user. Returns it with its id."""
    ticker_upper = trade.ticker.upper()
    direction = trade.direction.upper()
    entry_ts = f"{trade.entry_date}T{trade.entry_time}:00"
    exit_ts  = f"{trade.exit_date}T{trade.exit_time}:00"
    ret_pct  = _return_pct(direction, trade.entry_price, trade.exit_price)

    if _HAS_CLOUD_SQL:
        owner = _journal_owner(request)
        try:
            execute_sql(
                """
                INSERT INTO journal_entries
                    (ticker, direction, entry_ts, exit_ts,
                     entry_price, exit_price, return_pct, notes, user_email)
                VALUES
                    (:ticker, :direction, :entry_ts, :exit_ts,
                     :entry_price, :exit_price, :return_pct, :notes, :user_email)
                """,
                {
                    "ticker": ticker_upper,
                    "direction": direction,
                    "entry_ts": entry_ts,
                    "exit_ts": exit_ts,
                    "entry_price": trade.entry_price,
                    "exit_price": trade.exit_price,
                    "return_pct": round(ret_pct, 4),
                    "notes": trade.notes or "",
                    "user_email": owner,
                },
            )
            df = query_to_dataframe(
                """
                SELECT id::text FROM journal_entries
                WHERE ticker = :ticker AND entry_ts = :entry_ts AND user_email = :user_email
                ORDER BY created_at DESC LIMIT 1
                """,
                {"ticker": ticker_upper, "entry_ts": entry_ts, "user_email": owner},
            )
            new_id = str(df["id"].iloc[0]) if not df.empty else str(uuid.uuid4())
            return {"source": "cloud_sql", "id": new_id, "return_pct": round(ret_pct, 4)}
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
        "return_pct": round(ret_pct, 4),
        "notes": trade.notes or "",
        "created_at": datetime.utcnow().isoformat(),
    })
    _save_local(ticker_upper, entries)
    return {"source": "local", "id": new_id, "return_pct": round(ret_pct, 4)}


@router.delete("/api/journal/trades/{trade_id}")
async def delete_trade(trade_id: str, request: Request, ticker: str = ""):
    """Delete one of the signed-in user's journal entries by UUID."""
    if _HAS_CLOUD_SQL:
        owner = _journal_owner(request)
        try:
            execute_sql(
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
