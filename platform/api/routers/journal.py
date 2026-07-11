"""
Journal router — Cloud SQL-backed trade journal with local fallback.

Endpoints:
  GET    /api/journal/trades/{ticker}    — list all journal entries for a ticker
  POST   /api/journal/trades             — create a new journal entry (active or closed)
  PATCH  /api/journal/trades/{id}        — close an active trade (sets exit + return_pct/status)
  DELETE /api/journal/trades/{id}        — delete a journal entry by UUID
  GET    /api/journal/examples/{ticker}  — read-only admin teaching examples (journal_entries)
  GET    /api/journal/seed/{ticker}      — read-only admin seed from the pipeline `trades` table
  POST   /api/journal/export/{ticker}    — write pipeline-compatible CSV to data/signals/
  POST   /api/journal/import/preview     — parse+FIFO-pair an uploaded broker CSV (no writes)
  POST   /api/journal/import/commit      — insert caller-selected paired trades from a preview
"""
import csv
import io
import json
import logging
import math
import os
import sys
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Path setup ───────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SIGNALS_DIR = PROJECT_ROOT / "data" / "signals"
LOCAL_JOURNAL_DIR = PROJECT_ROOT / "data" / "journal"

# Task 3 (2026-07-11 journal one-stop-shop): broker CSV import cap. Import
# scale in practice is <= a few hundred rows (one brokerage account's trade
# history); this bounds the pathological case (a multi-year, multi-account
# export) so a single upload can't turn into thousands of per-trade INSERTs
# or an unbounded in-memory parse (CLAUDE.md Rule 0). Applies to BOTH the
# preview endpoint (CSV data-row count) and the commit endpoint (trades list
# length) — see import_preview / import_commit.
MAX_IMPORT_ROWS = 5000

# ── Cloud SQL availability check ─────────────────────────────────────────────
try:
    from gcp.database import is_cloud_sql_configured, query_to_dataframe, execute_sql
    _HAS_CLOUD_SQL: bool = is_cloud_sql_configured()
except Exception:
    _HAS_CLOUD_SQL = False

# Task 2 broker-import core (lib/broker_import.py) — pure parse/pairing, no
# I/O. This router owns duplicate detection and DB writes (see module
# docstring pt. 5 in lib/broker_import.py).
from lib.broker_import import detect_broker, pair_orders, parse_csv  # noqa: E402

# Server-verified identity for per-user scoping.
from api.auth import current_user_email

# Admin identity for the read-only "Examples" teaching layer (GET /api/journal/
# examples/{ticker}) — same env var / default the admin gate uses elsewhere
# (api/main.py:/api/me, api/routers/admin.py). Resolved once at import time
# (mirrors those call sites); tests override via monkeypatch.setattr on this
# module attribute rather than reload, same convention as api.auth.AUTH_MODE.
_ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "teneika@bictech.org").strip().lower()


# ── Query/exec indirections (testability) ────────────────────────────────────
# Every route calls through these instead of `query_to_dataframe`/`execute_sql`
# directly. They forward to the module-global name at CALL time (not at
# definition time), so tests can monkeypatch either this wrapper OR the
# underlying `journal.query_to_dataframe` / `journal.execute_sql` name — both
# take effect, which keeps the older test suites (that patch the plain names)
# working alongside new tests that patch the indirection directly.
def _journal_query(sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    return query_to_dataframe(sql, params)


def _journal_exec(sql: str, params: Optional[dict] = None) -> int:
    """Forwards to `execute_sql` and returns its rowcount (see there)."""
    return execute_sql(sql, params)


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
    # Derived if omitted. Constrained to the values `_derive_status` actually
    # produces (plus the "closed"-but-flat-return legacy value) so a typo'd
    # override can't persist a junk status the rest of the app can't render.
    status: Optional[Literal["active", "win", "loss", "breakeven", "closed"]] = None
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


class ImportCommitTrade(BaseModel):
    """One selected `PairedTrade` from a broker-import preview, ready to
    commit. Mirrors `lib.broker_import.PairedTrade`'s fields exactly — no
    `owner`/`user_email` field: owner is ALWAYS the authenticated caller,
    never client-supplied (see `import_commit`).

    `return_pct` here is the import pipeline's PREMIUM P&L percent
    (`(exit_price - entry_price) / entry_price * 100`, computed by
    `pair_orders` — entry/exit are option premiums, not underlying price, so
    it is NOT recomputed via `_return_pct`, which flips sign by direction for
    an underlying-price bet). `status` is accepted but re-derived server-side
    from `exit_ts`/`return_pct` via `_derive_status` — never trusted verbatim
    — so a client can't fabricate "win"/"loss" independent of the numbers.
    """
    ticker: str
    direction: str                       # CALL | PUT
    entry_ts: str                        # "YYYY-MM-DD HH:MM"
    entry_price: float
    exit_ts: Optional[str] = None
    exit_price: Optional[float] = None
    return_pct: Optional[float] = None   # premium P&L, TRUE PERCENT; None when active
    quantity: int = 1
    status: str = "active"               # "active" | "closed" — advisory, re-derived below


class ImportCommitRequest(BaseModel):
    broker: str
    trades: list[ImportCommitTrade]


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


def _insert_cloud_sql_trade(
    *, ticker: str, direction: str, entry_ts: str, exit_ts: Optional[str],
    entry_price: float, exit_price: Optional[float], return_pct: Optional[float],
    notes: str, owner: str, stop_loss: Optional[float],
    tp1: Optional[float], tp2: Optional[float], tp3: Optional[float],
    status: str, source: str, session_id: Optional[str],
) -> str:
    """Shared Cloud SQL insert path for one `journal_entries` row.

    Used by BOTH `POST /api/journal/trades` (manual entry) and
    `POST /api/journal/import/commit` (broker import) so the two write
    surfaces can never drift on columns or validation — exactly the same
    INSERT + id-lookup SQL either way. Raises on failure; the caller decides
    503 vs. local fallback (same convention as every other Cloud SQL branch
    in this router).
    """
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
            "ticker": ticker,
            "direction": direction,
            "entry_ts": entry_ts,
            "exit_ts": exit_ts,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "return_pct": return_pct,
            "notes": notes,
            "user_email": owner,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "status": status,
            "source": source,
            "session_id": session_id,
        },
    )
    df = _journal_query(
        """
        SELECT id::text FROM journal_entries
        WHERE ticker = :ticker AND entry_ts = :entry_ts AND user_email = :user_email
        ORDER BY created_at DESC LIMIT 1
        """,
        {"ticker": ticker, "entry_ts": entry_ts, "user_email": owner},
    )
    return str(df["id"].iloc[0]) if not df.empty else str(uuid.uuid4())


def _build_local_entry(
    ticker: str, direction: str, entry_ts: str, exit_ts: Optional[str],
    entry_price: float, exit_price: Optional[float], return_pct: Optional[float],
    notes: str, stop_loss: Optional[float], take_profits: list[float],
    status: str, source: str, session_id: Optional[str],
) -> dict:
    """Local-fallback (open-dev, no Cloud SQL) `journal_entries`-shaped dict.

    Shared by `POST /api/journal/trades` and `POST /api/journal/import/commit`
    so the local JSON shape never drifts between the two write paths (same
    reuse rationale as `_insert_cloud_sql_trade`).
    """
    return {
        "id": str(uuid.uuid4()),
        "ticker": ticker,
        "direction": direction,
        "entry_ts": entry_ts,
        "exit_ts": exit_ts,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "return_pct": return_pct,
        "notes": notes or "",
        "stop_loss": stop_loss,
        "take_profits": take_profits or [],
        "status": status,
        "source": source,
        "session_id": session_id,
        "created_at": datetime.utcnow().isoformat(),
    }


def _dedupe_key(ticker, direction, entry_ts, entry_price) -> tuple:
    """Duplicate-detection key per the brief: (ticker, entry_ts, entry_price,
    direction). `entry_ts` is normalized to 'YYYY-MM-DD HH:MM' (drop
    seconds/the 'T' separator) so an imported row (no seconds, space
    separator — `PairedTrade.entry_ts`) matches an existing DB/local row for
    the same fill (which carries seconds and, in Cloud SQL, a 'T' or space
    separator depending on the driver's timestamp rendering). `entry_price`
    is rounded to 4dp to absorb float/Decimal representation noise.
    """
    ts_norm = str(entry_ts).replace("T", " ")[:16]
    try:
        price_norm = round(float(entry_price), 4)
    except (TypeError, ValueError):
        price_norm = None
    return (str(ticker).strip().upper(), str(direction).strip().upper(), ts_norm, price_norm)


def _existing_entry_keys(owner: str, tickers: list[str]) -> set[tuple]:
    """Existing `journal_entries` dedupe keys for this owner, scoped to the
    given tickers.

    ONE batched SELECT (`ticker = ANY(:tickers)`) — never one query per
    trade — bounded by the number of DISTINCT tickers in the import, not
    the row count (CLAUDE.md Rule 0). Local/open-dev fallback mirrors this:
    one local-file read per distinct ticker, not per trade.

    Raises on a real Cloud SQL failure (mirrors `_journal_query`'s other
    call sites in this router) — the caller decides 503 vs. local fallback.
    """
    keys: set[tuple] = set()
    if not tickers:
        return keys

    if _HAS_CLOUD_SQL:
        df = _journal_query(
            """
            SELECT ticker, direction, entry_price,
                   entry_ts AT TIME ZONE 'UTC' AS entry_ts
            FROM journal_entries
            WHERE user_email = :user_email AND ticker = ANY(:tickers)
            """,
            {"user_email": owner, "tickers": tickers},
        )
        for _, row in df.iterrows():
            keys.add(_dedupe_key(row["ticker"], row["direction"], row["entry_ts"], row["entry_price"]))
        return keys

    for ticker in sorted({t.upper() for t in tickers}):
        for entry in _load_local(ticker):
            keys.add(_dedupe_key(
                entry.get("ticker", ticker), entry.get("direction", ""),
                entry.get("entry_ts", ""), entry.get("entry_price", 0),
            ))
    return keys


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


@router.get("/api/journal/examples/{ticker}")
async def get_examples(ticker: str):
    """Read-only teaching "Examples" — the admin's own journal trades for a ticker.

    Same JSON shape as GET /api/journal/trades/{ticker}: {ticker, source,
    count, trades}. Admin identity comes from the server-side `_ADMIN_EMAIL`
    constant, never the caller — every signed-in user sees the same
    admin-authored examples regardless of who's asking (the frontend gates
    auth via the normal middleware; this endpoint doesn't scope by caller
    identity at all). Excludes `source = 'replay'` rows (practice-mode noise
    isn't teaching material).

    Cloud-SQL only: unlike the per-user trades GET, there is no local-owner
    fallback here — "the admin's trades" has no meaning without Cloud SQL, so
    DB-unavailable (not configured, or a real query failure) mirrors
    get_trades' 503 envelope exactly rather than fabricating an empty success
    (CLAUDE.md Rule 3.7).
    """
    ticker_upper = ticker.upper()

    if not _HAS_CLOUD_SQL:
        raise HTTPException(status_code=503, detail="journal temporarily unavailable")

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
              AND source IS DISTINCT FROM 'replay'
            ORDER BY entry_ts DESC
            """,
            {"ticker": ticker_upper, "user_email": _ADMIN_EMAIL},
        )
    except Exception:
        # Mirrors get_trades' except path exactly (same 503 + same detail
        # string). No owner=="local" branch here (unlike get_trades) because
        # this endpoint always reads the admin's Cloud-SQL data, never a
        # per-request owner's — there is no local variant to fall back to.
        raise HTTPException(status_code=503, detail="journal temporarily unavailable")

    trades = [] if df.empty else _rows_to_trades(df)
    return {"ticker": ticker_upper, "source": "cloud_sql", "count": len(trades), "trades": trades}


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
            new_id = _insert_cloud_sql_trade(
                ticker=ticker_upper, direction=direction, entry_ts=entry_ts, exit_ts=exit_ts,
                entry_price=trade.entry_price, exit_price=trade.exit_price if has_exit else None,
                return_pct=ret_pct_rounded, notes=trade.notes or "", owner=owner,
                stop_loss=trade.stop_loss, tp1=tp1, tp2=tp2, tp3=tp3,
                status=status, source=trade.source, session_id=trade.session_id,
            )
            return {"source": "cloud_sql", "id": new_id, "return_pct": ret_pct_rounded, "status": status}
        except Exception:
            # Auth mode: never write to the shared owner-less local file (would
            # be visible to other users) — fail loud. Local fallback is open-dev
            # only. See get_trades for the full rationale.
            if owner != "local":
                raise HTTPException(status_code=503, detail="journal temporarily unavailable")

    # Local fallback
    entries = _load_local(ticker_upper)
    entry = _build_local_entry(
        ticker_upper, direction, entry_ts, exit_ts, trade.entry_price,
        trade.exit_price if has_exit else None, ret_pct_rounded, trade.notes or "",
        trade.stop_loss, take_profits, status, trade.source, trade.session_id,
    )
    new_id = entry["id"]
    entries.insert(0, entry)
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

            # `AND status = 'active'` closes the TOCTOU window between the
            # SELECT above and this UPDATE: if a concurrent PATCH already
            # closed the trade in between, this UPDATE matches zero rows
            # instead of clobbering the other request's exit. rowcount==0
            # means "lost the race" -> 409, never a fabricated 200 over a
            # no-op write.
            rowcount = _journal_exec(
                """
                UPDATE journal_entries
                SET exit_ts = :exit_ts, exit_price = :exit_price,
                    return_pct = :return_pct, status = :status
                WHERE id = :id AND user_email = :user_email AND status = 'active'
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
            if not rowcount:
                raise HTTPException(status_code=409, detail="trade already closed")
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

    # Validate BEFORE any query runs: a malformed `date` used to reach the
    # Postgres `date` cast in the WHERE clause and surface as a generic
    # "seed query failed" 503, masking a client input error as a server
    # outage. Reject it here as a 422 instead.
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="date must be in YYYY-MM-DD format")

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


@router.post("/api/journal/import/preview")
async def import_preview(
    request: Request,
    file: UploadFile = File(...),
    broker: Optional[str] = Form(None),
    mapping: Optional[str] = Form(None),
):
    """Parse an uploaded broker CSV export and FIFO-pair round trips.

    Pipeline: `detect_broker`/`parse_csv`/`pair_orders` (lib/broker_import.py,
    Task 2) — pure, no I/O. This endpoint adds duplicate-detection against the
    signed-in caller's existing journal_entries (ticker, entry_ts, entry_price,
    direction) and returns the result. It NEVER writes to the journal — commit
    is a separate, explicit step, and re-checks duplicates itself (this
    preview's "duplicate" flag is advisory, not authoritative, so a stale
    preview can never race a concurrent write into a bad commit).

    `broker` auto-detects from the CSV header row when omitted (exact
    required-column match, see `detect_broker`). `mapping` (a JSON-encoded
    column-name dict) is required only when `broker="generic"`.

    5,000-row cap -> 413 (see `MAX_IMPORT_ROWS`): bounds a pathological
    multi-year/multi-account export from turning into an unbounded parse or,
    downstream at commit time, thousands of per-trade INSERTs.
    """
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="file must be UTF-8 encoded CSV")

    lines = text.splitlines()
    if not lines:
        raise HTTPException(status_code=422, detail="empty CSV file")

    data_row_count = max(0, len(lines) - 1)  # exclude header
    if data_row_count > MAX_IMPORT_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"CSV has {data_row_count} rows, exceeds the {MAX_IMPORT_ROWS}-row import cap",
        )

    resolved_broker = (broker or "").strip().lower() or detect_broker(lines[0])
    if not resolved_broker:
        raise HTTPException(
            status_code=422,
            detail="could not detect broker from CSV header; specify broker + mapping",
        )

    mapping_dict: Optional[dict] = None
    if mapping:
        try:
            mapping_dict = json.loads(mapping)
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="mapping must be valid JSON")

    try:
        orders = parse_csv(text, resolved_broker, mapping=mapping_dict)
    except ValueError as e:
        # Caller-supplied broker/mapping is bad (unknown broker string, or a
        # generic mapping missing required keys) — a client input error, not
        # an internal failure. 422, not 500.
        raise HTTPException(status_code=422, detail=str(e))

    preview = pair_orders(orders)
    preview.broker = resolved_broker  # pair_orders never sets this — see lib/broker_import.py pt.5

    owner = _journal_owner(request)
    tickers = sorted({t.ticker for t in preview.trades})
    try:
        existing_keys = _existing_entry_keys(owner, tickers)
    except Exception:
        if owner != "local":
            raise HTTPException(status_code=503, detail="journal temporarily unavailable")
        existing_keys = set()

    trades_out = []
    for t in preview.trades:
        d = asdict(t)
        key = _dedupe_key(t.ticker, t.direction, t.entry_ts, t.entry_price)
        d["duplicate"] = key in existing_keys
        trades_out.append(d)

    return {"broker": resolved_broker, "trades": trades_out, "skipped": preview.skipped}


@router.post("/api/journal/import/commit")
async def import_commit(body: ImportCommitRequest, request: Request):
    """Insert the caller-selected `PairedTrade`s from a preview.

    Re-checks duplicates server-side (idempotent: committing the exact same
    preview twice imports zero new rows the second time) and reuses
    `_insert_cloud_sql_trade` / `_build_local_entry` — the SAME insert path
    `POST /api/journal/trades` uses — so the two write surfaces can never
    drift on columns or validation (CLAUDE.md project instructions: reuse the
    existing insert path, don't duplicate insert logic).

    `owner` is ALWAYS the authenticated caller (`_journal_owner(request)`) —
    never admin, never client-supplied; the request body carries no
    owner/user field at all. This endpoint never writes to Examples: Examples
    (GET /api/journal/examples) reads a server-side admin constant, and this
    endpoint always writes under the caller's own identity, so an import can
    never land in another user's — or the admin's — journal.

    `return_pct`/`status`: an active trade's null exit stays null (never a
    fabricated 0/closed) — `status` is re-derived from `exit_ts`/`return_pct`
    via `_derive_status`, the incoming `PairedTrade.status` field is never
    trusted verbatim (CLAUDE.md Rule 3.7 — no fabricated financial fields).
    """
    if len(body.trades) > MAX_IMPORT_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"commit has {len(body.trades)} trades, exceeds the {MAX_IMPORT_ROWS}-row import cap",
        )

    broker = body.broker.strip().lower()
    source = f"import:{broker}"
    owner = _journal_owner(request)
    tickers = sorted({t.ticker for t in body.trades})

    try:
        existing_keys = _existing_entry_keys(owner, tickers)
    except Exception:
        if owner != "local":
            raise HTTPException(status_code=503, detail="journal temporarily unavailable")
        existing_keys = set()

    imported = 0
    skipped_duplicates = 0

    for t in body.trades:
        ticker_upper = t.ticker.upper()
        direction = t.direction.upper()
        key = _dedupe_key(ticker_upper, direction, t.entry_ts, t.entry_price)
        if key in existing_keys:
            skipped_duplicates += 1
            continue

        has_exit = t.exit_ts is not None and t.exit_price is not None
        ret_pct = round(t.return_pct, 4) if (has_exit and t.return_pct is not None) else None
        status = _derive_status(has_exit, ret_pct)
        exit_ts = t.exit_ts if has_exit else None
        exit_price = t.exit_price if has_exit else None

        if _HAS_CLOUD_SQL:
            try:
                _insert_cloud_sql_trade(
                    ticker=ticker_upper, direction=direction,
                    entry_ts=t.entry_ts, exit_ts=exit_ts,
                    entry_price=t.entry_price, exit_price=exit_price,
                    return_pct=ret_pct, notes="", owner=owner,
                    stop_loss=None, tp1=None, tp2=None, tp3=None,
                    status=status, source=source, session_id=None,
                )
                imported += 1
                # Guard against duplicate rows WITHIN this same commit batch
                # (e.g. a caller re-submitting the same trade twice) without
                # a second round-trip to the DB.
                existing_keys.add(key)
                continue
            except Exception:
                # Auth mode: never fall back to the shared owner-less local
                # file for a real user — fail loud (same convention as
                # create_trade / delete_trade elsewhere in this router).
                if owner != "local":
                    raise HTTPException(status_code=503, detail="journal temporarily unavailable")
                # owner == "local": fall through to the local-file write below.

        entries = _load_local(ticker_upper)
        entry = _build_local_entry(
            ticker_upper, direction, t.entry_ts, exit_ts, t.entry_price, exit_price,
            ret_pct, notes="", stop_loss=None, take_profits=[],
            status=status, source=source, session_id=None,
        )
        entries.insert(0, entry)
        _save_local(ticker_upper, entries)
        imported += 1
        existing_keys.add(key)

    return {"imported": imported, "skipped_duplicates": skipped_duplicates}
