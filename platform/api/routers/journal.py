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
import json
import logging
import math
import os
import re
import sys
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
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

# Task-3-review Important-1 fix (2026-07-11): hard byte ceiling on the
# uploaded file, enforced via a chunked read BEFORE the whole upload is
# buffered in memory. 5 MiB is generous for a 5,000-row CSV (well under
# 1 KiB/row) but bounds the pathological case (a caller uploading an
# arbitrarily large file) so a single request can't turn into an unbounded
# in-memory buffer regardless of what MAX_IMPORT_ROWS's line-count check
# would eventually decide (CLAUDE.md Rule 0 — no unbounded reads before a
# capacity check).
MAX_IMPORT_BYTES = 5 * 1024 * 1024   # 5 MiB
_IMPORT_READ_CHUNK_SIZE = 1024 * 1024  # 1 MiB

# Task-3-review Minor-b fix: the broker allowlist `import_preview` already
# enforces implicitly (any other string 404s out of `parse_csv`'s dispatch
# with a ValueError -> 422). `import_commit` gets no free ride through
# `parse_csv` (it never calls it), so it must check explicitly against the
# SAME set to reject an unsupported broker before persisting `source =
# f"import:{broker}"` rows under a value nothing else recognizes.
_ALLOWED_BROKERS = {"robinhood", "webull", "generic"}

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

    `return_pct` is accepted for backward-compat with the preview response
    shape only — it is ADVISORY, NEVER trusted for persistence (Task-3-review
    Important-2 fix: a client could otherwise submit prices and a
    contradictory return_pct and have the fabricated number persisted
    verbatim). `import_commit` always recomputes it server-side from
    `entry_price`/`exit_price` via `_import_return_pct` — the same
    percent-change math `_return_pct` uses, but WITHOUT `_return_pct`'s
    CALL/PUT sign flip (entry/exit here are option premiums on a long-only
    round trip, not an underlying-price directional bet — see
    `_import_return_pct`'s docstring). `status` is likewise accepted but
    re-derived server-side from `exit_ts`/the recomputed `return_pct` via
    `_derive_status` — never trusted verbatim — so a client can't fabricate
    "win"/"loss" independent of the numbers.
    """
    ticker: str
    direction: str                       # CALL | PUT
    entry_ts: str                        # "YYYY-MM-DD HH:MM"
    entry_price: float
    exit_ts: Optional[str] = None
    exit_price: Optional[float] = None
    return_pct: Optional[float] = None   # ADVISORY ONLY — ignored at commit, see docstring
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


def _import_return_pct(entry: float, exit_: float) -> float:
    """Server-side return_pct for a broker-import round trip
    (`import_commit`) — Task-3-review Important-2 fix.

    Reuses `_return_pct`'s exact percent-change math but ALWAYS passes
    direction="CALL", i.e. NEVER applies the CALL/PUT sign flip.
    `_return_pct`'s flip assumes entry/exit are the UNDERLYING price of a
    directional bet (a PUT profits when the underlying falls). Broker-import
    entry/exit are the OPTION PREMIUM of a long-only round trip (BTO then
    STC — short legs are dropped by `lib/broker_import.py`, see its
    docstring pt. 1), where a rising premium is always a gain and a falling
    premium is always a loss, independent of CALL/PUT. Applying the flip
    here would silently invert every PUT's premium P&L sign.
    """
    return _return_pct("CALL", entry, exit_)


async def _read_bounded_upload(file: UploadFile, max_bytes: int) -> bytes:
    """Read `file` incrementally, capped at `max_bytes` — Task-3-review
    Important-1 fix.

    The prior code did `raw = await file.read()`, buffering the ENTIRE
    upload in memory before any size/row-count check ran (CLAUDE.md Rule 0
    — no unbounded reads before a capacity check). This reads in
    `_IMPORT_READ_CHUNK_SIZE` chunks and aborts with 413 the moment the
    running total exceeds `max_bytes`, so a pathologically large upload
    never gets fully buffered and the CSV parser never runs on it.
    """
    buf = bytearray()
    while True:
        chunk = await file.read(_IMPORT_READ_CHUNK_SIZE)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"file too large — max {max_bytes // (1024 * 1024)} MB",
            )
    return bytes(buf)


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


def _pipeline_rows_to_trades(df: pd.DataFrame, ticker_upper: str) -> list[dict]:
    """Pipeline `trades` rows (gcp/schema.sql:1065, the trading_analysis.py
    dataset) -> the journal trade JSON shape, for the UNION half of
    GET /api/journal/examples/{ticker} (task-examples-union, 2026-07-11 user
    decision).

    entry_ts/exit_ts here are ALREADY naive-ET wall-clock strings from the
    caller's `entry_time AT TIME ZONE 'America/New_York'` /
    `exit_time AT TIME ZONE 'America/New_York'` SELECT — deliberately NOT
    `'UTC'` like `_rows_to_trades`' journal_entries columns use. Verified
    empirically against production `trades` rows (2026-07-11, via
    scripts/db_query_cr.sh): `trades.entry_time`/`exit_time` store TRUE UTC
    instants (`datetime.now()` inside a UTC-clocked Cloud Run container in
    gcp/signal_monitor.py's `_persist_signal_alert`), UNLIKE
    `journal_entries.entry_ts` (a naive-ET literal written directly by this
    router's own `create_trade`, then mislabeled as UTC on insert — that's
    why `_rows_to_trades` uses `AT TIME ZONE 'UTC'` to strip the label back
    off without converting). Applying `AT TIME ZONE 'UTC'` to
    `trades.entry_time` would return the RAW UTC clock — 4-5 hours off from
    the market-hours wall clock the frontend's isoNaiveToEpoch expects —
    while `AT TIME ZONE 'America/New_York'` performs the real UTC->ET
    conversion needed to land on the same naive-ET wire convention. Spot
    check: production trade id 429, entry_time
    2026-04-13 13:34:00+00:00 -> 'America/New_York' gives 09:34:00 (matches
    the 09:30 ET session open); 'UTC' would have echoed 13:34:00 unchanged.

    Other mapping rules (see .superpowers/sdd/task-examples-union-brief.md):
      - id: 'pipe-<bigserial id>' — never collides with a journal_entries
        UUID.
      - return_pct: pipeline `trades.return_pct` is a RAW FRACTION (e.g.
        0.003 == 0.3%, same convention `seed_trades` documents/converts) —
        ×100 here to match the TRUE-PERCENT convention every other journal
        endpoint uses on the wire.
      - status: 'win' if return_pct > 0, else 'loss' if return_pct is not
        null (i.e. <= 0), else 'active' — the union spec's three-way split
        (no breakeven bucket, unlike `_derive_status`'s four-way split).
      - notes: exit_reason, strat_combo, level_broken, and "score <N.N>"
        (from total_score) — " · "-joined, each part omitted when absent,
        "" when none are present (never a fabricated placeholder).
      - source: always 'pipeline'.

    task-alerts-enrichment (2026-07-12 user decision): the caller's SQL now
    LEFT JOINs each `trades` row to its nearest `signal_alerts` row (same
    ticker + direction, closest `alert_ts` to `entry_time`, see
    `.superpowers/sdd/task-alerts-enrichment-brief.md` for the measured
    join-window verification — production `trades`/`signal_alerts` rows are
    written from the SAME `datetime.now()` call in
    `gcp/signal_monitor.py::_persist_signal_alert`, so every one of the 2,483
    production trades matched its originating alert at an EXACT 0-second
    diff; a small tolerance window is still used for robustness). This adds
    four OPTIONAL columns to `df` when a match was found (all NULL/absent
    when the LEFT JOIN found nothing within the window — an honest
    "unmatched" case, never fabricated):
      - target_price -> take_profits = [target_price] (a single value, so
        the CHART draws a real TP line and the table's TPs column renders
        it) — never converted/scaled, it's already a dollar price.
      - time_stop_minutes -> passed through AS-IS on the trade dict (a new
        `time_stop_minutes` key, never folded into `stop_loss` — there is no
        stop PRICE, only a time-based exit rule, so a fabricated R:R must
        never be computable from it; see JournalPage's Stop-cell render and
        TradeRailCard's SL segment, which render "<N>m time-stop" precisely
        because `stop_loss` stays null here).
      - level_broken / total_score -> appended to `notes` (level_broken
        verbatim; total_score as "score <N.N>") when present.
    stop_loss is UNCONDITONALLY None regardless of match — the signal engine
    never logs a stop PRICE, only a time-stop; fabricating one from
    target_price would violate CLAUDE.md Rule 3.7.
    """
    for col in ("entry_ts", "exit_ts"):
        if col in df.columns:
            df[col] = df[col].apply(lambda v: None if pd.isna(v) else str(v))

    def _clean(v):
        return None if v is None or _is_nan(v) else v

    trades: list[dict] = []
    for rec in df.to_dict(orient="records"):
        raw_return = _clean(rec.get("return_pct"))
        return_pct = None if raw_return is None else float(raw_return) * 100
        exit_reason = _clean(rec.get("exit_reason"))
        strat_combo = _clean(rec.get("strat_combo"))
        level_broken = _clean(rec.get("level_broken"))
        total_score = _clean(rec.get("total_score"))
        notes_parts = [exit_reason, strat_combo, level_broken]
        if total_score is not None:
            notes_parts.append(f"score {float(total_score):.1f}")
        notes = " · ".join(str(p) for p in notes_parts if p)
        status = (
            "win" if (return_pct is not None and return_pct > 0)
            else "loss" if return_pct is not None
            else "active"
        )

        # task-alerts-enrichment: per-row, never a fixed/hardcoded value —
        # each trade carries its OWN matched alert's target_price/
        # time_stop_minutes (or None when unmatched). USER REQUIREMENT
        # (verbatim, task-alerts-enrichment-brief.md): the Stop column must
        # render EACH row's OWN time_stop_minutes, never a fixed label.
        raw_target_price = _clean(rec.get("target_price"))
        take_profits = [float(raw_target_price)] if raw_target_price is not None else []
        raw_time_stop = _clean(rec.get("time_stop_minutes"))
        time_stop_minutes = None if raw_time_stop is None else int(raw_time_stop)

        trades.append({
            "id": f"pipe-{int(rec['id'])}",
            "ticker": ticker_upper,
            "direction": rec.get("direction"),
            "entry_ts": rec.get("entry_ts"),
            "exit_ts": rec.get("exit_ts"),
            "entry_price": _clean(rec.get("entry_price")),
            "exit_price": _clean(rec.get("exit_price")),
            "return_pct": return_pct,
            "notes": notes,
            "take_profits": take_profits,
            "stop_loss": None,
            "time_stop_minutes": time_stop_minutes,
            "status": status,
            "source": "pipeline",
            "session_id": None,
        })
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


_TS_NO_SECONDS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}$")


def _with_seconds(ts: Optional[str]) -> Optional[str]:
    """Append ':00' when `ts` is exactly 'YYYY-MM-DD HH:MM' (no seconds) --
    e.g. Robinhood-derived import timestamps (lib/broker_import.py's
    date-only ts). Local-fallback storage must persist a seconds component
    or the frontend's isoNaiveToEpoch (platform/src/hooks/
    useJournalChartTrades.ts, whose regex requires HH:MM:SS) returns NaN
    and chart marker times break on local dev. Only used by import_commit's
    local-fallback branch -- Cloud SQL parses/normalizes timestamps itself."""
    if ts is not None and _TS_NO_SECONDS_RE.match(ts):
        return f"{ts}:00"
    return ts


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
        "created_at": datetime.now(timezone.utc).isoformat(),
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
    """Read-only teaching "Examples" — the UNION of the admin's own journal
    trades AND every automated-pipeline `trades` row for a ticker
    (task-examples-union, 2026-07-11 user decision).

    Same envelope shape as GET /api/journal/trades/{ticker}: {ticker, source,
    count, trades}. Two sources, one SQL query each (never per-row):
      1. Admin identity comes from the server-side `_ADMIN_EMAIL` constant,
         never the caller — every signed-in user sees the same admin-authored
         examples regardless of who's asking. Excludes `source = 'replay'`
         rows (practice-mode noise isn't teaching material). Mapped via
         `_rows_to_trades` (unchanged from pre-union).
      2. Every `trades`-table row (gcp/schema.sql:1065, the
         trading_analysis.py pipeline dataset) for the ticker, RESTRICTED to
         regular trading hours — no per-caller/owner scoping, the pipeline
         table has no owner column. LEFT JOIN LATERALs each row to its
         nearest `signal_alerts` row (task-alerts-enrichment, 2026-07-12 user
         decision — see the query's in-line comment for the measured
         join-window verification) so real TP/time-stop data is available;
         an unmatched trade still returns the row with those fields null,
         never dropped. Mapped via `_pipeline_rows_to_trades` (see its
         docstring for the entry_ts/exit_ts timezone-conversion rationale
         and the return_pct/status/notes/take_profits/time_stop_minutes
         mapping rules), tagged `source: 'pipeline'`.

         USER DECISION (2026-07-11): `trades` contains 268 real but
         extended-hours rows (premarket/evening, from an old scanner) that
         clutter this teaching view; they stay in the DB for analysis, they
         just don't render as Examples. Hence the
         `(entry_time AT TIME ZONE 'America/New_York')::time BETWEEN
         TIME '09:30' AND TIME '16:00'` predicate below. Note this also
         excludes rows with a NULL `entry_time` (BETWEEN on NULL evaluates
         to NULL, not TRUE) — acceptable, an example without an entry time
         teaches nothing. Admin journal_entries rows are NOT filtered by
         this predicate (users log what they log) — only the pipeline half
         of the union is time-of-day scoped.
    Combined and sorted by entry_ts DESC across BOTH sources (not just within
    each) — a plain Python sort, since the two source tables can't be UNIONed
    in one SQL statement (different column sets/types).

    Capacity (CLAUDE.md Rule 0): one additional indexed SELECT
    (idx_trades_ticker_date's leading `ticker` column) per request. The
    pipeline table's largest single-ticker slice is in the low thousands of
    rows (~hundreds of KB of JSON) — acceptable for a read-only teaching
    view; not a workload requiring pagination at this scale.

    Cloud-SQL only: unlike the per-user trades GET, there is no local-owner
    fallback here — "the admin's trades" has no meaning without Cloud SQL, so
    DB-unavailable (not configured, or a real query failure on EITHER source)
    mirrors get_trades' 503 envelope exactly rather than fabricating an empty
    or partial success (CLAUDE.md Rule 3.7) — a pipeline-query failure fails
    the whole request loud, it never silently degrades to admin-only rows.
    """
    ticker_upper = ticker.upper()

    if not _HAS_CLOUD_SQL:
        raise HTTPException(status_code=503, detail="journal temporarily unavailable")

    try:
        df_admin = _journal_query(
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

    admin_trades = [] if df_admin.empty else _rows_to_trades(df_admin)

    try:
        # task-alerts-enrichment (2026-07-12 user decision): LEFT JOIN LATERAL
        # each `trades` row to its nearest `signal_alerts` row (same ticker +
        # direction, closest `alert_ts` to `entry_time`) so the Examples table
        # can surface real TP/time-stop data instead of the pre-enrichment
        # all-dashes risk columns. STILL ONE SELECT for the whole pipeline
        # half (never per-row) — the join runs entirely inside this single
        # statement. Window predicate (`alert_ts BETWEEN entry_time ± 5s`) is
        # a small tolerance around a measured production reality, not a
        # guess: a read-only join-window verification query
        # (gcp/queries/check_alert_trade_join_window.sql, run 2026-07-12 via
        # `./scripts/db_query_cr.sh -f ...`) found EVERY one of the 2,483
        # production `trades` rows matches its nearest same-ticker/direction
        # `signal_alerts` row at an EXACT 0-second diff (both columns are
        # TIMESTAMPTZ written from the SAME `datetime.now()` call in
        # `gcp/signal_monitor.py::_persist_signal_alert` — see
        # `.superpowers/sdd/p-alerts-enrichment-report.md` for the full
        # distribution). ±5s leaves headroom for any future writer that
        # doesn't share that exact code path without risking a false match
        # across two genuinely different signals.
        #
        # PR #728 review FIX 1: the nearest-match ORDER BY had no secondary
        # key, so two equidistant alerts (production DOES have identical-
        # microsecond refire duplicates) made the match nondeterministic --
        # Postgres is free to return either row for a tied ORDER BY. Appended
        # `, sa2.id` so ties resolve to the lower-id (earlier-inserted) alert
        # deterministically.
        df_pipeline = _journal_query(
            """
            SELECT t.id, t.direction,
                   t.entry_time AT TIME ZONE 'America/New_York' AS entry_ts,
                   t.exit_time  AT TIME ZONE 'America/New_York' AS exit_ts,
                   t.entry_price, t.exit_price, t.return_pct, t.exit_reason, t.strat_combo,
                   sa.target_price, sa.time_stop_minutes, sa.level_broken, sa.total_score
            FROM trades t
            LEFT JOIN LATERAL (
                SELECT sa2.target_price, sa2.time_stop_minutes, sa2.level_broken, sa2.total_score
                FROM signal_alerts sa2
                WHERE sa2.ticker = t.ticker AND sa2.direction = t.direction
                  AND sa2.alert_ts BETWEEN t.entry_time - INTERVAL '5 seconds'
                                        AND t.entry_time + INTERVAL '5 seconds'
                ORDER BY ABS(EXTRACT(EPOCH FROM (t.entry_time - sa2.alert_ts))), sa2.id
                LIMIT 1
            ) sa ON true
            WHERE t.ticker = :ticker
              AND (t.entry_time AT TIME ZONE 'America/New_York')::time BETWEEN TIME '09:30' AND TIME '16:00'
            ORDER BY t.entry_time DESC
            """,
            {"ticker": ticker_upper},
        )
    except Exception:
        # Same fail-loud stance as the admin query above — never a partial
        # admin-only success when the pipeline half is unreachable.
        raise HTTPException(status_code=503, detail="journal temporarily unavailable")

    pipeline_trades = [] if df_pipeline.empty else _pipeline_rows_to_trades(df_pipeline, ticker_upper)

    # Match-rate observability (brief: "log match-rate server-side at INFO;
    # UI unchanged for unmatched" — never surfaced in the response envelope,
    # never a fabricated per-row indicator beyond the honest null fields
    # _pipeline_rows_to_trades already produces).
    if not df_pipeline.empty:
        matched = int(df_pipeline["target_price"].notna().sum())
        logger.info(
            "examples pipeline alert-join ticker=%s matched=%d/%d",
            ticker_upper, matched, len(df_pipeline),
        )

    trades = admin_trades + pipeline_trades
    trades.sort(key=lambda t: t.get("entry_ts") or "", reverse=True)

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

    5 MiB byte cap -> 413 (see `MAX_IMPORT_BYTES`), enforced via a chunked
    read BEFORE any of the above runs: an oversized upload never gets fully
    buffered into memory or reaches `parse_csv` at all.
    """
    raw = await _read_bounded_upload(file, MAX_IMPORT_BYTES)
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
    fabricated 0/closed). `return_pct` is NEVER trusted from the client
    (Task-3-review Important-2 fix) — it is always recomputed server-side
    from `entry_price`/`exit_price` via `_import_return_pct`; `status` is
    re-derived from `exit_ts`/the recomputed `return_pct` via
    `_derive_status`. Neither the incoming `PairedTrade.return_pct` nor
    `.status` field is ever trusted verbatim (CLAUDE.md Rule 3.7 — no
    fabricated/client-trusted financial fields).

    `broker` must be one of `_ALLOWED_BROKERS` (Task-3-review Minor-b fix) —
    422 otherwise. `import_preview` enforces this implicitly (any other
    string fails to dispatch in `parse_csv` -> 422); `import_commit` never
    calls `parse_csv`, so it checks explicitly against the same set before
    persisting any row under `source = f"import:{broker}"`.
    """
    if len(body.trades) > MAX_IMPORT_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"commit has {len(body.trades)} trades, exceeds the {MAX_IMPORT_ROWS}-row import cap",
        )

    broker = body.broker.strip().lower()
    if broker not in _ALLOWED_BROKERS:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported broker {broker!r}; must be one of {sorted(_ALLOWED_BROKERS)}",
        )
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
        # `t.return_pct` (client-supplied, advisory only) is deliberately
        # NOT used here — see docstring / Task-3-review Important-2 fix.
        ret_pct = round(_import_return_pct(t.entry_price, t.exit_price), 4) if has_exit else None
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
            ticker_upper, direction, _with_seconds(t.entry_ts), _with_seconds(exit_ts),
            t.entry_price, exit_price,
            ret_pct, notes="", stop_loss=None, take_profits=[],
            status=status, source=source, session_id=None,
        )
        entries.insert(0, entry)
        _save_local(ticker_upper, entries)
        imported += 1
        existing_keys.add(key)

    return {"imported": imported, "skipped_duplicates": skipped_duplicates}
