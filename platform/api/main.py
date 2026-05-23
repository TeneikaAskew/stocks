"""
Trading Platform API - FastAPI backend
Thin wrapper around existing lib/ modules
"""
import logging
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import httpx
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Add project root to path so we can import lib/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.data_loader import DataLoader
from api.routers import live, options, playbook, backtest, signals, insights, journal, dashboard, catalysts, admin, analytics, config as config_router, health, glossary, grid

logger = logging.getLogger(__name__)

# ── Cloud SQL availability ───────────────────────────────────────────────────
_CLOUD_SQL = False
try:
    from gcp.database import is_cloud_sql_configured, query_to_dataframe
    _CLOUD_SQL = is_cloud_sql_configured()
except Exception:
    pass

app = FastAPI(title="Trading Platform API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_origin_regex=r"https://.*\.app\.github\.dev",  # GitHub Codespace tunnel URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Router includes ──────────────────────────────────────────────────────────
app.include_router(live.router, prefix="")
# `grid` MUST mount before `options` — `options` has a greedy
# `GET /api/options/{ticker}/{date_str}` that would otherwise shadow
# `/api/options/SPY/grid` and `/api/options/SPY/nodes` (matching
# `date_str="grid"` / `"nodes"` and 400ing in date validation).
# Regression test: tests/test_grid_router.py::TestRoutingOrder.
app.include_router(grid.router, prefix="")
app.include_router(options.router, prefix="")
app.include_router(playbook.router, prefix="")
app.include_router(backtest.router, prefix="")
app.include_router(signals.router, prefix="")
app.include_router(insights.router, prefix="")
app.include_router(journal.router, prefix="")
app.include_router(dashboard.router, prefix="")
app.include_router(catalysts.router, prefix="")
app.include_router(admin.router)
app.include_router(analytics.router, prefix="")
app.include_router(config_router.router, prefix="")
app.include_router(health.router, prefix="")
app.include_router(glossary.router, prefix="")

data_loader = DataLoader()

# ── AlphaVantage helper for reference levels ─────────────────────────────────
AV_API_KEY = os.environ.get("AV_API_KEY") or os.environ.get("ALPHA_VANTAGE_API_KEY", "")
AV_BASE = "https://www.alphavantage.co/query"
# Cloud SQL data older than this is considered stale and we prefer AV
MAX_CLOUD_SQL_STALENESS_DAYS = 3


def _fetch_av_daily_reference(ticker: str, before_date: str) -> Optional[dict]:
    """Fetch most recent daily OHLC from AlphaVantage strictly before before_date.

    Args:
        ticker: symbol (e.g. 'IWM')
        before_date: YYYY-MM-DD string; returns the trading day immediately before this

    Returns: {"date": "YYYYMMDD", "open": ..., "high": ..., "low": ..., "close": ...} or None
    """
    if not AV_API_KEY:
        return None
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.get(AV_BASE, params={
                "function": "TIME_SERIES_DAILY",
                "symbol": ticker,
                "outputsize": "compact",  # last 100 days is plenty
                "apikey": AV_API_KEY,
            })
            if r.status_code != 200:
                return None
            data = r.json()
            series = data.get("Time Series (Daily)", {})
            if not series:
                return None
            # Find most recent date strictly before before_date
            dates_sorted = sorted(series.keys(), reverse=True)
            for d in dates_sorted:
                if d < before_date:
                    bar = series[d]
                    return {
                        "date": d.replace("-", ""),
                        "open": float(bar["1. open"]),
                        "high": float(bar["2. high"]),
                        "low": float(bar["3. low"]),
                        "close": float(bar["4. close"]),
                    }
    except Exception as e:
        logger.warning("AV daily reference fetch failed: %s", e)
    return None

# ── App-level API routes ─────────────────────────────────────────────────────


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "project_root": str(PROJECT_ROOT),
        "cloud_sql": _CLOUD_SQL,
        "gcs_bucket": "adept-mountain-474619-d4-trading-data",
        "lib_dir_exists": (PROJECT_ROOT / "lib").is_dir(),
    }


@app.get("/api/me")
async def get_current_user(request: Request):
    """Return the current user's email from IAP headers.

    In production (behind IAP), returns the authenticated email.
    In local dev (no IAP), returns None.
    """
    email = _iap_user_email(request)
    return {"email": email}


# ── /dev — test-account info page (behind IAP in prod) ─────────────────────
# Shows the Playwright tester service account, IAP audience, and ready-to-run
# curl/gcloud snippets. Visible only to humans who already passed IAP, so the
# page itself is fine to expose publicly within the deployed service.

_DEV_ALLOWED_EMAIL = os.environ.get("DEV_ALLOWED_EMAIL", "teneika@bictech.org").lower()


def _iap_user_email(request: Request) -> Optional[str]:
    """Extract the authenticated user's email from the IAP-injected header.

    IAP sets `X-Goog-Authenticated-User-Email` as `accounts.google.com:user@domain`.
    Returns None when the header is absent (e.g. local dev without IAP).
    """
    raw = request.headers.get("x-goog-authenticated-user-email")
    if not raw:
        return None
    return raw.split(":", 1)[-1].strip().lower()


@app.get("/dev", include_in_schema=False)
async def dev_info(request: Request):
    from fastapi.responses import HTMLResponse, PlainTextResponse

    email = _iap_user_email(request)
    # Local dev (no IAP header) → allow. Cloud Run with IAP → require allow-list match.
    if email is not None and email != _DEV_ALLOWED_EMAIL:
        return PlainTextResponse("Forbidden", status_code=403)

    project_id = os.environ.get("GCP_PROJECT_ID", "adept-mountain-474619-d4")
    sa_email = os.environ.get(
        "PLAYWRIGHT_TESTER_SA",
        f"playwright-tester@{project_id}.iam.gserviceaccount.com",
    )
    iap_audience = os.environ.get("IAP_OAUTH_CLIENT_ID", "<unset — see notes>")
    revision = os.environ.get("K_REVISION", "local")
    service_url = str(request.base_url).rstrip("/")
    viewer = email or "(local dev — no IAP)"

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>/dev — test accounts</title>
<style>
  body {{ font-family: ui-monospace,Menlo,monospace; background:#111318; color:#e2e2e8;
         max-width: 880px; margin: 2rem auto; padding: 0 1.5rem; line-height: 1.5; }}
  h1 {{ color:#8bceff; margin-bottom: 0.25rem; }}
  h2 {{ color:#bdc8d2; margin-top: 2rem; border-bottom: 1px solid #282a2e; padding-bottom: .25rem; }}
  code, pre {{ background:#1a1c20; padding: 0.15rem 0.4rem; border-radius: 4px; }}
  pre {{ padding: .8rem 1rem; overflow-x:auto; white-space: pre-wrap; word-break: break-word; }}
  .k {{ color:#6e7781; }}
  .v {{ color:#e2e2e8; }}
  .warn {{ color:#ffb86b; }}
</style></head>
<body>
<h1>/dev — test accounts &amp; auth</h1>
<p class="k">Internal page. Visible only to authenticated IAP users.</p>

<h2>Environment</h2>
<pre><span class="k">viewer         </span><span class="v">{viewer}</span>
<span class="k">service_url    </span><span class="v">{service_url}</span>
<span class="k">revision       </span><span class="v">{revision}</span>
<span class="k">project_id     </span><span class="v">{project_id}</span>
<span class="k">cloud_sql      </span><span class="v">{_CLOUD_SQL}</span></pre>

<h2>Playwright tester service account</h2>
<pre><span class="k">email          </span><span class="v">{sa_email}</span>
<span class="k">iap_audience   </span><span class="v">{iap_audience}</span></pre>

<p class="warn">Note: programmatic auth against this IAP-on-Cloud-Run service
is currently broken (both for SA keys and gcloud user tokens). The legacy
OAuth-brand admin API was sunset in March 2026 and the auto-managed IAP
audience does not accept programmatically minted JWTs. Browser SSO is the
only working path right now; curl/CI flows return 401.</p>

<h2>Browser access (works today)</h2>
<pre># Sign into bictech.org in your browser, then open:
{service_url}/

# IAP redirects to Google OAuth, then routes you to the app.</pre>

<h2>If you need a local terminal session</h2>
<pre>gcloud run services proxy trading-platform --region us-east1
# then http://localhost:8080 — the proxy authenticates as your gcloud user.</pre>

<h2>Run Playwright locally</h2>
<pre>cd platform &amp;&amp; npm run test
# E2E tests target http://localhost:5173 (see playwright.config.ts).
# To probe the deployed Cloud Run instance use the gcloud token recipe above —
# the SA path will return 401 until OAuth-brand replacement ships.</pre>

</body></html>"""
    return HTMLResponse(html)


@app.get("/api/market/dates/{ticker}")
async def get_available_dates(ticker: str):
    """List available trading dates for a ticker (Cloud SQL → local fallback)."""
    ticker_upper = ticker.upper()
    ticker_lower = ticker.lower()

    # ── Cloud SQL primary ────────────────────────────────────────────────────
    if _CLOUD_SQL:
        try:
            df = query_to_dataframe(
                """
                SELECT DISTINCT DATE(ts) AS trade_date
                FROM market_data_intraday
                WHERE ticker = :ticker AND interval = '1min'
                ORDER BY trade_date DESC
                """,
                {"ticker": ticker_upper},
            )
            if not df.empty:
                dates = [d.strftime("%Y%m%d") for d in df["trade_date"]]
                # Derive months from the dates for month-level navigation
                months = sorted(set(d[:6] for d in dates), reverse=True)
                return {
                    "ticker": ticker_upper,
                    "source": "cloud_sql",
                    "dates": dates,
                    "months": months,
                }
        except Exception as e:
            logger.warning("Cloud SQL dates query failed, falling back to local: %s", e)

    # ── GCS fallback ─────────────────────────────────────────────────────────
    from api import gcs_reader
    dates: list[str] = []
    months: list[str] = []
    try:
        # Daily minute parquets
        minute_blobs = gcs_reader.list_matching_blobs(
            f"data/{ticker_lower}/minute/",
            rf"^{ticker_lower}_minute_(\d{{8}})\.parquet$",
        )
        for blob_name in minute_blobs:
            filename = blob_name.rsplit("/", 1)[-1]
            date_part = filename.rsplit("_", 1)[-1].replace(".parquet", "")
            if len(date_part) == 8 and date_part.isdigit():
                dates.append(date_part)
        # Monthly intraday parquets
        intraday_blobs = gcs_reader.list_matching_blobs(
            f"data/{ticker_lower}/intraday/",
            rf"^{ticker_lower}_av_1min_(\d{{6}})\.parquet$",
        )
        for blob_name in intraday_blobs:
            filename = blob_name.rsplit("/", 1)[-1]
            month_part = filename.rsplit("_", 1)[-1].replace(".parquet", "")
            if len(month_part) == 6 and month_part.isdigit():
                months.append(month_part)
    except Exception as e:
        logger.warning("GCS dates list failed for %s: %s", ticker_upper, e)

    return {
        "ticker": ticker_upper,
        "source": "gcs",
        "dates": sorted(set(dates), reverse=True),
        "months": sorted(set(months), reverse=True),
    }


@app.get("/api/market/data/{ticker}/{date}")
async def get_market_data(
    ticker: str,
    date: str,
    timeframe: int = Query(default=1, description="Timeframe in minutes: 1, 5, 15, 30, 60"),
    end_time: Optional[str] = Query(default=None, description="HH:MM (24h ET) cutoff; returns bars with open_time <= end_time"),
):
    """Load intraday OHLCV data for a specific ticker and date.

    date format: YYYYMMDD (e.g., 20260220) or YYYYMM (e.g., 202602)
    Returns candlestick + volume arrays ready for TradingView Lightweight Charts.
    If `end_time` is provided (HH:MM ET), only bars whose open-time is at or before
    that time are returned — used by historical review mode.
    """
    ticker_upper = ticker.upper()
    ticker_lower = ticker.lower()

    try:
        df = _load_date_data(ticker_lower, date)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {ticker_upper} on {date}")

    # Normalize column names
    col_map = {}
    for col in df.columns:
        lc = col.lower()
        if lc == 'open':
            col_map[col] = 'open'
        elif lc == 'high':
            col_map[col] = 'high'
        elif lc == 'low':
            col_map[col] = 'low'
        elif lc == 'close':
            col_map[col] = 'close'
        elif lc == 'volume':
            col_map[col] = 'volume'
    df = df.rename(columns=col_map)

    required = {'open', 'high', 'low', 'close', 'volume'}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(status_code=500, detail=f"Missing columns: {missing}")

    # Ensure index is datetime
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'Time' in df.columns:
            df.index = pd.to_datetime(df['Time'])
        elif 'time' in df.columns:
            df.index = pd.to_datetime(df['time'])
        elif 'timestamp' in df.columns:
            df.index = pd.to_datetime(df['timestamp'])
        elif 'Datetime' in df.columns:
            df.index = pd.to_datetime(df['Datetime'])

    # Strip timezone
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    df = df.sort_index()

    # Filter to requested date if YYYYMMDD
    if len(date) == 8:
        target = pd.Timestamp(f"{date[:4]}-{date[4:6]}-{date[6:8]}")
        df = df[df.index.date == target.date()]

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {ticker_upper} on {date}")

    # Aggregate timeframe if > 1 minute
    if timeframe > 1:
        df = _aggregate_timeframe(df, timeframe)

    # Apply end_time cutoff — bars with open-time at or before the target
    if end_time:
        try:
            parts = end_time.split(":")
            cutoff = datetime.strptime(f"{parts[0]}:{parts[1]}", "%H:%M").time()
            df = df[df.index.time <= cutoff]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid end_time format (expected HH:MM): {e}")

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {ticker_upper} on {date} at or before end_time={end_time}")

    # Convert to chart format
    # Timestamps as Unix seconds (naive ET — what the chart expects)
    times = (df.index.astype('int64') // 1_000_000_000).tolist()

    candlestick = []
    volume = []
    for i, (t, row) in enumerate(zip(times, df.itertuples())):
        o, h, l, c = float(row.open), float(row.high), float(row.low), float(row.close)
        v = float(row.volume) if pd.notna(row.volume) else 0
        candlestick.append({"time": t, "open": o, "high": h, "low": l, "close": c})
        color = "rgba(8, 153, 129, 0.5)" if c >= o else "rgba(242, 54, 69, 0.5)"
        volume.append({"time": t, "value": v, "color": color})

    return {
        "ticker": ticker_upper,
        "date": date,
        "timeframe": timeframe,
        "count": len(candlestick),
        "candlestick": candlestick,
        "volume": volume,
    }


def _fetch_week_range(ticker_upper: str, before_date: str) -> Optional[dict]:
    """Fetch the last 5 trading days BEFORE `before_date` and return the
    overall high/low/start/end across that window. Prefers Cloud SQL
    `market_data_daily`. Returns None on failure.

    `before_date` format: "YYYY-MM-DD" (exclusive upper bound).
    """
    if not _CLOUD_SQL:
        return None
    try:
        df = query_to_dataframe(
            """
            SELECT date, high, low, close, rsi_14
            FROM market_data_daily
            WHERE ticker = :ticker AND date < :dt
            ORDER BY date DESC LIMIT 5
            """,
            {"ticker": ticker_upper, "dt": before_date},
        )
        if df.empty or len(df) < 2:
            return None
        # Ensure ascending order for start/end date labels
        df = df.sort_values("date")
        start_raw = df["date"].iloc[0]
        end_raw = df["date"].iloc[-1]
        start_str = start_raw.strftime("%Y-%m-%d") if hasattr(start_raw, "strftime") else str(start_raw)
        end_str = end_raw.strftime("%Y-%m-%d") if hasattr(end_raw, "strftime") else str(end_raw)
        rsi_series = df["rsi_14"].dropna() if "rsi_14" in df.columns else None
        return {
            "high": float(df["high"].max()),
            "low": float(df["low"].min()),
            "avg_close": float(df["close"].mean()),
            "avg_rsi_14": float(rsi_series.mean()) if rsi_series is not None and not rsi_series.empty else None,
            "start_date": start_str,
            "end_date": end_str,
            "sessions": int(len(df)),
        }
    except Exception as e:
        logger.warning("Week range query failed for %s: %s", ticker_upper, e)
        return None


@app.get("/api/market/reference/{ticker}/{date}")
async def get_reference_levels(ticker: str, date: str):
    """Get previous day OHLC reference levels for support/resistance.

    Strategy:
      1. AlphaVantage TIME_SERIES_DAILY when requested date is within the last ~30 days
         (AV is always real-time; avoids stale Cloud SQL issues)
      2. Cloud SQL market_data_daily for historical requests (fast, has indicators)
      3. Local parquet fallback (minute bars aggregated)

    Returns the OHLC of the trading day immediately before the requested date,
    plus a `week` block containing the high/low across the previous 5 trading days.
    """
    ticker_upper = ticker.upper()
    ticker_lower = ticker.lower()
    date_str = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else date

    # Determine if request is "recent" (within last 30 days) — prefer AV for freshness
    try:
        requested_dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        days_ago = (datetime.now().date() - requested_dt).days
        is_recent = days_ago < 30
    except ValueError:
        is_recent = False

    # ── AlphaVantage primary for recent dates ────────────────────────────────
    if is_recent:
        av_result = _fetch_av_daily_reference(ticker_upper, date_str)
        if av_result:
            # Week range always comes from Cloud SQL (AV daily doesn't give us
            # a tidy 5-row window with one call). Best-effort — None if CSQL down.
            week = _fetch_week_range(ticker_upper, date_str)
            return {
                "ticker": ticker_upper,
                "source": "alphavantage",
                "week": week,
                **av_result,
            }
        logger.info("AV reference unavailable for %s, falling back to Cloud SQL", ticker_upper)

    # ── Cloud SQL for historical (or AV fallback) ────────────────────────────
    if _CLOUD_SQL:
        try:
            df = query_to_dataframe(
                """
                SELECT date, open, high, low, close
                FROM market_data_daily
                WHERE ticker = :ticker AND date < :dt
                ORDER BY date DESC LIMIT 1
                """,
                {"ticker": ticker_upper, "dt": date_str},
            )
            if not df.empty:
                row = df.iloc[0]
                ref_date = row["date"]
                ref_date_str = ref_date.strftime("%Y-%m-%d") if hasattr(ref_date, "strftime") else str(ref_date)
                # Check if Cloud SQL data is stale relative to the request
                try:
                    ref_dt = datetime.strptime(ref_date_str, "%Y-%m-%d").date()
                    staleness_days = (requested_dt - ref_dt).days if is_recent else 0
                except Exception:
                    staleness_days = 0

                return {
                    "ticker": ticker_upper,
                    "source": "cloud_sql",
                    "stale_days": staleness_days if staleness_days > MAX_CLOUD_SQL_STALENESS_DAYS else 0,
                    "date": ref_date_str.replace("-", ""),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "week": _fetch_week_range(ticker_upper, date_str),
                }
        except Exception as e:
            logger.warning("Cloud SQL reference query failed: %s", e)

    # ── GCS fallback ─────────────────────────────────────────────────────────
    from api import gcs_reader
    all_dates: list[str] = []
    try:
        minute_blobs = gcs_reader.list_matching_blobs(
            f"data/{ticker_lower}/minute/",
            rf"^{ticker_lower}_minute_(\d{{8}})\.parquet$",
        )
        for blob_name in minute_blobs:
            filename = blob_name.rsplit("/", 1)[-1]
            date_part = filename.rsplit("_", 1)[-1].replace(".parquet", "")
            if len(date_part) == 8 and date_part.isdigit():
                all_dates.append(date_part)
    except Exception as e:
        logger.warning("GCS minute list failed for %s: %s", ticker_upper, e)
    all_dates.sort()

    if date not in all_dates:
        raise HTTPException(status_code=404, detail=f"Date {date} not found for {ticker}")

    idx = all_dates.index(date)
    if idx == 0:
        raise HTTPException(status_code=404, detail="No previous day available")

    prev_date = all_dates[idx - 1]

    try:
        df = _load_date_data(ticker_lower, prev_date)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    col_map = {}
    for col in df.columns:
        lc = col.lower()
        if lc in ('open', 'high', 'low', 'close', 'volume'):
            col_map[col] = lc
    df = df.rename(columns=col_map)

    if not isinstance(df.index, pd.DatetimeIndex):
        for col_name in ('Time', 'time', 'timestamp', 'Datetime'):
            if col_name in df.columns:
                df.index = pd.to_datetime(df[col_name])
                break

    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    df = df.sort_index()

    target = pd.Timestamp(f"{prev_date[:4]}-{prev_date[4:6]}-{prev_date[6:8]}")
    df = df[df.index.date == target.date()]

    rth_mask = (df.index.hour * 60 + df.index.minute >= 570) & (df.index.hour * 60 + df.index.minute < 960)
    df = df[rth_mask]

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No RTH data for {ticker} on {prev_date}")

    return {
        "ticker": ticker_upper,
        "date": prev_date,
        "open": float(df['open'].iloc[0]),
        "high": float(df['high'].max()),
        "low": float(df['low'].min()),
        "close": float(df['close'].iloc[-1]),
        "week": _fetch_week_range(ticker_upper, date_str),
    }


# ── Internal helpers ─────────────────────────────────────────────────────────


def _load_date_data(ticker_lower: str, date: str) -> pd.DataFrame:
    """Load intraday data for a specific date or month.

    Priority: Cloud SQL → local parquet files.
    Returns a DataFrame with OHLCV columns and a DatetimeIndex.
    """
    ticker_upper = ticker_lower.upper()

    # ── Cloud SQL primary ────────────────────────────────────────────────────
    if _CLOUD_SQL:
        try:
            if len(date) == 8:
                # Specific date: YYYYMMDD
                date_str = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
                df = query_to_dataframe(
                    """
                    SELECT ts, open, high, low, close, volume, data_source
                    FROM market_data_intraday
                    WHERE ticker = :ticker AND interval = '1min'
                      AND DATE(ts) = :dt
                    ORDER BY ts
                    """,
                    {"ticker": ticker_upper, "dt": date_str},
                )
            elif len(date) == 6:
                # Month: YYYYMM
                year, month = int(date[:4]), int(date[4:6])
                start = f"{year}-{month:02d}-01"
                if month == 12:
                    end = f"{year + 1}-01-01"
                else:
                    end = f"{year}-{month + 1:02d}-01"
                df = query_to_dataframe(
                    """
                    SELECT ts, open, high, low, close, volume, data_source
                    FROM market_data_intraday
                    WHERE ticker = :ticker AND interval = '1min'
                      AND ts >= :start AND ts < :end
                    ORDER BY ts
                    """,
                    {"ticker": ticker_upper, "start": start, "end": end},
                )
            else:
                df = pd.DataFrame()

            if not df.empty:
                df.index = pd.to_datetime(df["ts"])
                # Normalize timezone based on data source:
                # - alphavantage: ET stored as UTC → just strip tz label
                # - yfinance: real UTC → convert to ET then strip
                is_yfinance = (
                    "data_source" in df.columns
                    and not df["data_source"].isna().all()
                    and df["data_source"].iloc[0] == "yfinance"
                )
                df = df.drop(columns=["ts", "data_source"], errors="ignore")
                if df.index.tz is not None:
                    if is_yfinance:
                        df.index = df.index.tz_convert("America/New_York").tz_localize(None)
                    else:
                        df.index = df.index.tz_localize(None)
                return df
        except Exception as e:
            logger.warning("Cloud SQL intraday load failed for %s/%s: %s", ticker_upper, date, e)

    # ── GCS fallback ─────────────────────────────────────────────────────────
    from api import gcs_reader

    def _try_gcs_download(blob_path_rel: str) -> pd.DataFrame | None:
        try:
            if gcs_reader.blob_exists(blob_path_rel):
                return gcs_reader.download_parquet(gcs_reader.BASE_PREFIX + blob_path_rel)
        except Exception as e:
            logger.warning("GCS download failed for %s: %s", blob_path_rel, e)
        return None

    if len(date) == 8:
        df = _try_gcs_download(f"data/{ticker_lower}/minute/{ticker_lower}_minute_{date}.parquet")
        if df is not None and not df.empty:
            return df

    month = date[:6] if len(date) >= 6 else date
    df = _try_gcs_download(f"data/{ticker_lower}/intraday/{ticker_lower}_av_1min_{month}.parquet")
    if df is not None and not df.empty:
        return df

    year = date[:4]
    df = _try_gcs_download(f"data/{ticker_lower}/{ticker_lower}_{year}.parquet")
    if df is not None and not df.empty:
        return df

    raise FileNotFoundError(f"No data found in Cloud SQL or GCS for {ticker_lower} date={date}")


def _aggregate_timeframe(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Aggregate 1-minute bars into higher timeframe."""
    rule = f"{minutes}min"
    agg = df.resample(rule).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    }).dropna(subset=['open'])
    return agg


# ── SPA static file serving (MUST be last — catch-all route) ─────────────────
# Production: npm run build → uvicorn api.main:app --host 0.0.0.0 --port 8000

_dist = Path(__file__).parent.parent / "dist"
if _dist.is_dir():
    from fastapi.responses import FileResponse

    _assets = _dist / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="static-assets")

    _index_html = _dist / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """SPA fallback — serve index.html for any non-API, non-asset route."""
        candidate = _dist / full_path
        if full_path and candidate.is_file() and ".." not in full_path:
            return FileResponse(candidate)
        return FileResponse(_index_html)
