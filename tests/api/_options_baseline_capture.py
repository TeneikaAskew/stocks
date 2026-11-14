"""Capture the options routes' JSON payloads for fixed both-sided fixtures.

Run against a checkout of the commit to pin (a git worktree), never against
the working branch:

    python3 tests/api/_options_baseline_capture.py --repo <worktree> --out <file>

The repo root comes from --repo, not from this file's location. The leading
underscore keeps pytest from collecting it.
"""
import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

FIXED_NOW = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
CHAIN_DATE = "2026-06-01"


class _Patcher:
    """Stand-in for pytest's monkeypatch: only setattr, as _patch_av needs."""

    def setattr(self, obj, name, value):
        setattr(obj, name, value)


def capture(repo_root: Path) -> dict:
    repo_root = Path(repo_root).resolve()
    for sub in ("tests/api", "platform/api", "platform", ""):
        sys.path.insert(0, str(repo_root / sub) if sub else str(repo_root))

    import gcp.database
    gcp.database.is_cloud_sql_configured = lambda: True
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import grid, options
    import test_grid_router
    import test_options_live
    import test_options_router

    for mod in (grid, options):
        mod._now_utc = lambda: FIXED_NOW
    options._require_cloud_sql = lambda: None
    options._AV_API_KEY = "test-key"

    class _FrozenDatetime(datetime):
        # the live route stamps snapshot_timestamp with datetime.utcnow()
        @classmethod
        def utcnow(cls):
            return FIXED_NOW.replace(tzinfo=None)

    options.datetime = _FrozenDatetime

    frame = test_options_router._chain_frame()
    grid_frame = test_grid_router._chain_df(date(2026, 6, 1), "REALTIME", tz="UTC")
    state = {"realtime": None, "eod": None, "default": frame}

    def fake_query(sql, params=None):
        import pandas as pd
        if "market_session = 'REALTIME'" in sql and state["realtime"] is not None:
            return state["realtime"]
        if "market_session = 'EOD'" in sql and state["eod"] is not None:
            return state["eod"]
        if state["realtime"] is None and state["eod"] is None:
            return state["default"]
        return pd.DataFrame()

    gcp.database.query_to_dataframe = fake_query
    options.query_to_dataframe = fake_query

    app = FastAPI()
    app.include_router(grid.router)
    app.include_router(options.router)
    client = TestClient(app)

    def get(url):
        r = client.get(url)
        assert r.status_code == 200, (url, r.status_code, r.text)
        return r.json()

    out = {}
    out["chain"] = get(f"/api/options/SPY/{CHAIN_DATE}")
    out["levels"] = get(f"/api/options/SPY/{CHAIN_DATE}/levels")

    test_options_live._patch_av(
        _Patcher(), test_options_live._FakeResponse(200, test_options_live._FAKE_AV_OK))
    out["live_chain"] = get("/api/options/live/SPY/2025-01-17")

    opts = [
        {"type": "call" if r["option_type"] == "calls" else "put",
         "strike": float(r["strike"]), "open_interest": int(r["open_interest"]),
         "gamma": float(r["gamma"]), "vega": float(r["vega"]),
         "delta": float(r["delta"]), "volume": int(r["volume"])}
        for r in frame.to_dict("records")
    ]
    r = client.post("/api/options/greeks", json={"spot_price": 100.05, "options": opts})
    assert r.status_code == 200, r.text
    out["greeks"] = r.json()

    state.update(realtime=grid_frame, eod=None, default=None)
    out["grid_live"] = get("/api/options/SPY/grid")
    out["nodes_live"] = get("/api/options/SPY/nodes")
    state.update(realtime=None, eod=grid_frame, default=None)
    out["grid_dated"] = get(f"/api/options/SPY/{CHAIN_DATE}/grid")
    out["nodes_dated"] = get(f"/api/options/SPY/{CHAIN_DATE}/nodes")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    payload = capture(args.repo)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
