"""
Backtest router.
GET /api/backtest/results/{ticker} - Return most recent backtest CSV for ticker as JSON
GET /api/backtest/equity/{ticker} - Return most recent equity curve CSV for ticker as JSON
GET /api/backtest/all/{ticker} - List all backtest runs for ticker with summary metrics
"""
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, HTTPException

router = APIRouter()

# 4 levels up: routers/ -> api/ -> platform/ -> stocks/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BACKTEST_DIR = PROJECT_ROOT / "data" / "backtest_results"

# Columns present in backtest CSVs (from actual data)
BACKTEST_COLUMNS = [
    "entry_time", "exit_time", "direction", "entry_price", "exit_price",
    "exit_reason", "base_score", "strat_bonus", "total_score",
    "position_size", "return_pct", "mae", "mfe", "ftfc_score",
    "orb_trend", "conditions",
]


def _most_recent_file(pattern: str) -> Path | None:
    """Return the most recently modified file matching a glob pattern, or None."""
    if not BACKTEST_DIR.is_dir():
        return None
    files = sorted(BACKTEST_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _file_summary(path: Path) -> dict:
    """Return lightweight metadata for a backtest CSV without loading the full frame."""
    try:
        df = pd.read_csv(path, nrows=0)  # header only for column check
        # Count rows efficiently
        with open(path) as f:
            row_count = sum(1 for _ in f) - 1  # subtract header
        return {
            "filename": path.name,
            "path": str(path),
            "modified": pd.Timestamp(path.stat().st_mtime, unit="s").isoformat(),
            "size_bytes": path.stat().st_size,
            "row_count": max(row_count, 0),
        }
    except Exception:
        return {
            "filename": path.name,
            "path": str(path),
            "modified": None,
            "size_bytes": path.stat().st_size,
            "row_count": None,
        }


@router.get("/api/backtest/results/{ticker}")
async def get_backtest_results(ticker: str):
    """Return trades from the most recent backtest CSV for the given ticker."""
    ticker_upper = ticker.upper()

    if not BACKTEST_DIR.is_dir():
        raise HTTPException(status_code=404, detail="Backtest results directory not found")

    csv_path = _most_recent_file(f"backtest_{ticker_upper}_*.csv")
    if csv_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"No backtest results found for ticker '{ticker_upper}'",
        )

    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read backtest CSV: {exc}")

    if df.empty:
        return {
            "ticker": ticker_upper,
            "filename": csv_path.name,
            "trade_count": 0,
            "trades": [],
        }

    # Replace NaN with None so JSON serialises cleanly
    df = df.where(pd.notna(df), other=None)

    # Convert numeric columns to native Python types
    for col in df.select_dtypes(include="number").columns:
        df[col] = df[col].apply(lambda x: float(x) if x is not None else None)

    trades = df.to_dict(orient="records")

    # Compute quick summary stats from return_pct if available
    summary: dict = {}
    if "return_pct" in df.columns:
        returns = df["return_pct"].dropna().astype(float)
        if len(returns) > 0:
            wins = returns[returns > 0]
            losses = returns[returns <= 0]
            summary = {
                "total_trades": len(returns),
                "win_count": len(wins),
                "loss_count": len(losses),
                "win_rate": round(len(wins) / len(returns), 4) if len(returns) else None,
                "avg_return_pct": round(returns.mean(), 4),
                "avg_win_pct": round(wins.mean(), 4) if len(wins) else None,
                "avg_loss_pct": round(losses.mean(), 4) if len(losses) else None,
                "total_return_pct": round(returns.sum(), 4),
            }

    return {
        "ticker": ticker_upper,
        "filename": csv_path.name,
        "trade_count": len(trades),
        "summary": summary,
        "trades": trades,
    }


@router.get("/api/backtest/equity/{ticker}")
async def get_equity_curve(ticker: str):
    """Return equity curve from the most recent equity CSV for the given ticker."""
    ticker_upper = ticker.upper()

    if not BACKTEST_DIR.is_dir():
        raise HTTPException(status_code=404, detail="Backtest results directory not found")

    csv_path = _most_recent_file(f"equity_{ticker_upper}_*.csv")
    if csv_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"No equity curve found for ticker '{ticker_upper}'",
        )

    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read equity CSV: {exc}")

    if df.empty:
        return {"ticker": ticker_upper, "filename": csv_path.name, "dates": [], "values": []}

    # Equity CSVs have: "Unnamed: 0" (date index) and "0" (equity value)
    date_col = None
    value_col = None

    for col in df.columns:
        if col in ("Unnamed: 0", "date", "Date", "index"):
            date_col = col
        elif col in ("0", "equity", "Equity", "value", "Value"):
            value_col = col

    # Fallback: first column = date, second column = value
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

    return {
        "ticker": ticker_upper,
        "filename": csv_path.name,
        "summary": summary,
        "dates": dates,
        "values": values,
    }


@router.get("/api/backtest/all/{ticker}")
async def list_all_backtests(ticker: str):
    """List all backtest runs for a ticker, sorted by date descending."""
    ticker_upper = ticker.upper()

    if not BACKTEST_DIR.is_dir():
        raise HTTPException(status_code=404, detail="Backtest results directory not found")

    backtest_files = sorted(
        BACKTEST_DIR.glob(f"backtest_{ticker_upper}_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not backtest_files:
        raise HTTPException(
            status_code=404,
            detail=f"No backtest files found for ticker '{ticker_upper}'",
        )

    runs = []
    for bp in backtest_files:
        # Extract timestamp token from filename: backtest_{TICKER}_{TIMESTAMP}.csv
        stem = bp.stem  # e.g. "backtest_IWM_20260221_161724"
        parts = stem.split("_")
        # Timestamp is everything after "backtest_{TICKER}_"
        timestamp = "_".join(parts[2:]) if len(parts) > 2 else ""

        info = _file_summary(bp)
        info["timestamp"] = timestamp

        # Check for matching equity file
        equity_path = BACKTEST_DIR / f"equity_{ticker_upper}_{timestamp}.csv"
        info["has_equity_curve"] = equity_path.exists()

        # Load minimal stats: just return_pct column
        try:
            returns_df = pd.read_csv(bp, usecols=lambda c: c in ("return_pct",))
            if "return_pct" in returns_df.columns:
                returns = returns_df["return_pct"].dropna().astype(float)
                wins = returns[returns > 0]
                info["trade_count"] = len(returns)
                info["win_rate"] = round(len(wins) / len(returns), 4) if len(returns) else None
                info["avg_return_pct"] = round(returns.mean(), 4) if len(returns) else None
            else:
                info["trade_count"] = info.get("row_count")
                info["win_rate"] = None
                info["avg_return_pct"] = None
        except Exception:
            info["trade_count"] = info.get("row_count")
            info["win_rate"] = None
            info["avg_return_pct"] = None

        runs.append(info)

    return {
        "ticker": ticker_upper,
        "total_runs": len(runs),
        "runs": runs,
    }
