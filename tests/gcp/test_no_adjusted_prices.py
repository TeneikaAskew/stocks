"""Nothing fetches, stores or reads an adjusted price (FEAT-DATA-001).

The owner's rule, 2026-11-16: "Nothing should be adjusted. It should be as it
was traded." Every daily request asks AlphaVantage TIME_SERIES_DAILY, which
returns the same open, high, low, close and volume as the adjusted endpoint
without the adjusted close (spec Problem 2), and no writer carries an
adjusted_close column into market_data_daily.

The replies below hold only the fields TIME_SERIES_DAILY returns, so a writer
that still reads the adjusted endpoint's '5. adjusted close' or '6. volume'
raises KeyError. Several writers swallow that (fetch_daily_from_av returns {}
and migrate_market_data_daily_av logs and goes on), so every case asserts the
values it wrote, not only what is absent.

Spec: docs/superpowers/specs/2026-11-16-feat-data-001-no-adjusted-prices-r2.md
"""
from __future__ import annotations

import ast
import datetime as dt
import re
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]

# A TIME_SERIES_DAILY reply for SPY: fields 1 to 5 only, '5. volume' the volume.
DAILY_REPLY = {
    "Meta Data": {"2. Symbol": "SPY"},
    "Time Series (Daily)": {
        "2026-11-13": {"1. open": "671.11", "2. high": "675.38", "3. low": "668.12",
                       "4. close": "673.27", "5. volume": "81234567"},
        "2026-11-12": {"1. open": "670.00", "2. high": "672.50", "3. low": "667.90",
                       "4. close": "671.80", "5. volume": "70111222"},
    },
}

# One 1-minute bar of the session, as TIME_SERIES_INTRADAY returns it.
INTRADAY_REPLY = {
    "Meta Data": {"2. Symbol": "SPY"},
    "Time Series (1min)": {
        "2026-11-13 09:30:00": {"1. open": "671.20", "2. high": "671.90", "3. low": "671.00",
                                "4. close": "671.50", "5. volume": "250000"},
    },
}

# The adjusted column names a writer could carry into a frame.
ADJ = {"adjusted_close", "Adj Close"}


class _Resp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _recording_get(answers: dict[str, dict]):
    """A requests.get that answers by params['function'] and records every
    params dict it was sent. A function with no answer gets an AlphaVantage
    error reply, so a request for the wrong endpoint yields no data."""
    sent: list[dict] = []

    def get(url, params=None, **kwargs):
        params = dict(params or {})
        sent.append(params)
        fn = params.get("function")
        if fn in answers:
            return _Resp(answers[fn])
        return _Resp({"Error Message": f"no stubbed answer for {fn}"})

    return get, sent


def _recording_upsert():
    """An upsert_dataframe stand-in recording (table, frame) pairs."""
    calls: list[tuple[str, pd.DataFrame]] = []

    def upsert(df, table, *args, **kwargs):
        calls.append((table, df.copy()))
        return len(df)

    return upsert, calls


def _daily_frames(calls):
    return [df for table, df in calls if table == "market_data_daily"]


# ─── Design 1: every daily writer requests TIME_SERIES_DAILY ────────────────


def _writer_fetch_daily_from_av(monkeypatch):
    from gcp.fetchers import fetch_market_data as fmd
    get, sent = _recording_get({"TIME_SERIES_DAILY": DAILY_REPLY})
    monkeypatch.setattr(fmd.requests, "get", get)

    out = fmd.fetch_daily_from_av("SPY", "2026-11-13", "k")

    assert len(sent) == 1
    assert sent[0]["function"] == "TIME_SERIES_DAILY"
    assert out == {"open": 671.11, "high": 675.38, "low": 668.12,
                   "close": 673.27, "volume": 81234567}


def _writer_av_get_full_daily_series(monkeypatch):
    from gcp.fetchers import fetch_market_data as fmd
    get, sent = _recording_get({"TIME_SERIES_DAILY": DAILY_REPLY})
    monkeypatch.setattr(fmd.requests, "get", get)

    frame = fmd._av_get_full_daily_series("SPY", "k", "full")

    assert len(sent) == 1
    assert sent[0]["function"] == "TIME_SERIES_DAILY"
    assert sent[0]["outputsize"] == "full"
    assert list(frame.columns) == ["ticker", "date", "open", "high", "low", "close", "volume"]
    assert frame.volume.tolist() == [70111222, 81234567]


def _writer_backfill_ticker(monkeypatch):
    import gcp.backfill_ticker as mod
    get, sent = _recording_get({"TIME_SERIES_DAILY": DAILY_REPLY})
    upsert, calls = _recording_upsert()
    monkeypatch.setattr(mod.requests, "get", get)
    monkeypatch.setattr("gcp.database.upsert_dataframe", upsert)
    monkeypatch.setattr(mod, "compute_indicators_for_full_range", lambda ticker: 0)
    monkeypatch.setattr(mod, "compute_indicators_for_dates", lambda ticker, dates: None)
    for name, value in (("BACKFILL_TICKER", "SPY"), ("ALPHA_VANTAGE_API_KEY", "k"),
                        ("BACKFILL_INCLUDE_NEWS", "false"),
                        ("BACKFILL_ADD_TO_WATCHLIST", "false"),
                        ("BACKFILL_DATES", "2026-11-13")):
        monkeypatch.setenv(name, value)

    daily = mod.av_daily_full("SPY", "k")
    assert [p["function"] for p in sent] == ["TIME_SERIES_DAILY"]
    assert not (set(daily.columns) & ADJ), sorted(daily.columns)
    assert daily["volume"].tolist() == [70111222, 81234567]

    sent.clear()
    assert mod.run() == 0
    assert [p["function"] for p in sent] == ["TIME_SERIES_DAILY"]
    frames = _daily_frames(calls)
    assert len(frames) == 1
    frame = frames[0]
    assert not (set(frame.columns) & ADJ), sorted(frame.columns)
    assert set(frame["data_source"]) == {"alphavantage"}
    row = frame[frame["date"] == dt.date(2026, 11, 13)].iloc[0]
    assert row["volume"] == 81234567


def _writer_migrate_to_gcp(monkeypatch):
    import gcp.migrate_to_gcp as mod
    get, sent = _recording_get({"TIME_SERIES_DAILY": DAILY_REPLY})
    upsert, calls = _recording_upsert()
    monkeypatch.setattr(mod, "AV_DAILY_SYMBOLS", {"spy": "SPY"})
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
    monkeypatch.setattr(mod.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(mod.requests, "get", get)
    monkeypatch.setattr("gcp.database.upsert_dataframe", upsert)

    mod.migrate_market_data_daily_av(Path("."), dry_run=False)

    assert [p["function"] for p in sent] == ["TIME_SERIES_DAILY"]
    # The function logs and goes on after any exception, so a missing frame
    # is how a writer still reading the adjusted endpoint's fields fails.
    frames = _daily_frames(calls)
    assert len(frames) == 1
    frame = frames[0]
    assert not (set(frame.columns) & ADJ), sorted(frame.columns)
    assert set(frame["data_source"]) == {"alphavantage_daily"}
    row = frame[frame["date"] == dt.date(2026, 11, 13)].iloc[0]
    assert row["volume"] == 81234567


def _writer_backfill_watchlist_data(monkeypatch):
    import requests

    import gcp.fetchers.fetch_market_data as fmd
    from scripts import backfill_watchlist_data as mod
    get, sent = _recording_get({"TIME_SERIES_DAILY": DAILY_REPLY})
    upsert, calls = _recording_upsert()
    monkeypatch.setenv("AV_API_KEY", "k")
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr("gcp.database.upsert_dataframe", upsert)
    monkeypatch.setattr(fmd, "compute_and_upsert_daily_indicators",
                        lambda ticker, fetch_date, **kw: None)
    monkeypatch.setattr(fmd, "read_level_params_for_run", lambda tickers, day: {})

    assert mod.backfill_daily("SPY") is True

    assert [p["function"] for p in sent] == ["TIME_SERIES_DAILY"]
    frames = _daily_frames(calls)
    assert len(frames) == 1
    frame = frames[0]
    assert not (set(frame.columns) & ADJ), sorted(frame.columns)
    row = frame[frame["date"] == dt.date(2026, 11, 13)].iloc[0]
    assert row["volume"] == 81234567


def _writer_scripts_fetch_market_data(monkeypatch):
    from scripts import fetch_market_data as mod
    get, sent = _recording_get({"TIME_SERIES_DAILY": DAILY_REPLY})
    monkeypatch.setattr(mod, "AV_API_KEY", "k")
    monkeypatch.setattr(mod.requests, "get", get)

    frame = mod.fetch_historical_daily_data("SPY", "2026-11-01", "2026-11-30")

    assert [p["function"] for p in sent] == ["TIME_SERIES_DAILY"]
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert frame["Volume"].tolist() == [70111222, 81234567]


WRITERS = {
    "fetch_daily_from_av": _writer_fetch_daily_from_av,
    "_av_get_full_daily_series": _writer_av_get_full_daily_series,
    "backfill_ticker": _writer_backfill_ticker,
    "migrate_to_gcp": _writer_migrate_to_gcp,
    "backfill_watchlist_data": _writer_backfill_watchlist_data,
    "scripts_fetch_market_data": _writer_scripts_fetch_market_data,
}


@pytest.mark.parametrize("writer", list(WRITERS))
def test_daily_writers_request_as_traded(writer, monkeypatch):
    """Each daily writer sends function TIME_SERIES_DAILY, reads volume from
    '5. volume', and returns or records no adjusted column."""
    WRITERS[writer](monkeypatch)


def test_no_writer_emits_adjusted_close(monkeypatch):
    """process_ticker over a 1-minute bar and a TIME_SERIES_DAILY reply, and
    the Yahoo ^VIX fetch, record market_data_daily frames with no adjusted
    column. On main the first carried adjusted_close through build_daily_row
    and the second set it equal to the close."""
    from gcp.fetchers import fetch_market_data as fmd

    get, sent = _recording_get({"TIME_SERIES_INTRADAY": INTRADAY_REPLY,
                                "TIME_SERIES_DAILY": DAILY_REPLY})
    upsert, calls = _recording_upsert()
    intraday_writes: list[str] = []
    indicator_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(fmd.requests, "get", get)
    monkeypatch.setattr(fmd, "upsert_dataframe", upsert)
    monkeypatch.setattr(fmd, "write_intraday_to_sql",
                        lambda ticker, df, fetch_date: intraday_writes.append(ticker))
    monkeypatch.setattr(fmd, "compute_and_upsert_daily_indicators",
                        lambda ticker, fetch_date, **kw: indicator_calls.append((ticker, fetch_date)))

    fmd.process_ticker("SPY", "2026-11-13", "k")

    assert intraday_writes == ["SPY"]
    assert [p["function"] for p in sent] == ["TIME_SERIES_INTRADAY", "TIME_SERIES_DAILY"]
    frames = _daily_frames(calls)
    assert frames, "process_ticker recorded no market_data_daily frame"
    for frame in frames:
        assert not (set(frame.columns) & ADJ), sorted(frame.columns)
    row = frames[0].iloc[0]
    assert row["data_source"] == "alphavantage_daily"
    assert row["volume"] == 81234567
    assert indicator_calls == [("SPY", "2026-11-13")]

    def epoch(day: str) -> int:
        return int(dt.datetime.strptime(day, "%Y-%m-%d")
                   .replace(tzinfo=dt.timezone.utc).timestamp())

    yahoo = {"chart": {"result": [{
        "timestamp": [epoch("2026-11-12"), epoch("2026-11-13")],
        "indicators": {"quote": [{"open": [18.0, 18.2], "high": [18.5, 19.0],
                                  "low": [17.8, 18.1], "close": [18.2, 18.7]}]},
    }]}}
    calls.clear()
    monkeypatch.setattr(fmd.requests, "get", lambda *a, **k: _Resp(yahoo))

    assert fmd.fetch_and_upsert_vix() == 2
    frames = _daily_frames(calls)
    assert len(frames) == 1
    assert not (set(frames[0].columns) & ADJ), sorted(frames[0].columns)


# ─── Designs 2 and 3: the two unused adjusted sources are retired ───────────


def test_retired_adjusted_sources_are_gone():
    """scripts/deep_backfill_ticker.py asked the adjusted endpoint and nothing
    ran it; gcp/fetchers/fetch_av_indicators.py fetched AlphaVantage
    indicators computed on adjusted closes (spec Problem 5)."""
    assert not (REPO / "scripts/deep_backfill_ticker.py").exists()
    assert not (REPO / "gcp/fetchers/fetch_av_indicators.py").exists()


# ─── Decision 7: the offline experiments read the as-traded export ──────────


def test_experiments_read_the_as_traded_export(tmp_path):
    """Both experiments read {T}_daily.csv, a TIME_SERIES_DAILY export, and
    refuse a file holding an adjusted column instead of silently using it."""
    from scripts.analysis import brief_rsi_band_experiment as brief
    from scripts.analysis import honest_scoring_experiment as honest

    path = tmp_path / "SPY_daily.csv"
    path.write_text("timestamp,open,high,low,close,volume\n"
                    "2026-11-12,670.00,672.50,667.90,671.80,70111222\n"
                    "2026-11-13,671.11,675.38,668.12,673.27,81234567\n")
    frame = brief.load_daily(str(tmp_path), "SPY")
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume", "Time"]
    assert frame["Close"].tolist() == [671.80, 673.27]

    path.write_text("timestamp,open,high,low,close,adjusted_close,volume\n"
                    "2026-11-13,671.11,675.38,668.12,673.27,671.00,81234567\n")
    with pytest.raises(ValueError, match="adjusted_close"):
        brief.load_daily(str(tmp_path), "SPY")
    bars = pd.DataFrame({"Time": pd.to_datetime([])})
    with pytest.raises(ValueError, match="adjusted_close"):
        honest.daily_bars("SPY", bars, daily_dir=str(tmp_path))


# ─── Design 7: the guard ─────────────────────────────────────────────────────
#
# Over every .py under gcp/, lib/, scripts/ and platform/ (tests and
# node_modules excluded), by ast, docstrings exempt:
#   - no string naming a vendor function that ends in _ADJUSTED;
#   - no string naming an adjusted close or an adjusted daily series, in any
#     spacing or case;
#   - no request parameter `adjusted` or `auto_adjust` whose value is not the
#     literal 'false' or False. A request parameter is a key of a dict literal
#     that also holds a 'function' key, or a keyword of a call to
#     requests.get/post/request, to anything reached through a yfinance
#     import, or to the 1-minute helpers fetch_minute_bars/fetch_minute_data.
#     The keys of a dict literal unpacked with ** into either count; unpacking
#     anything else into either is refused, since its keys cannot be read.
# One allowance: the module-level assignment ADJUSTED_CLOSE_COLUMNS in
# lib/data_loader.py, which holds the names only to refuse or drop them.
# Over every .sql under gcp/, by text: the same names only on the two lines
# of gcp/schema.sql that define market_data_daily.adjusted_close, which the
# companion data spec removes together with this allowance.

GUARDED_TREES = ("gcp", "lib", "scripts", "platform")
ADJUSTED_FUNCTION = re.compile(r"\b[A-Z0-9]+(?:_[A-Z0-9]+)*_ADJUSTED\b")
ADJUSTED_NAME = re.compile(
    r"adj(?:usted)?[\s_.\-]*close|adjclose|adjusted[\s_.\-]*daily|daily[\s_.\-]*adjusted",
    re.IGNORECASE)
REQUEST_FLAGS = ("adjusted", "auto_adjust")
MINUTE_HELPERS = ("fetch_minute_bars", "fetch_minute_data")
ALLOWANCE = ("lib/data_loader.py", "ADJUSTED_CLOSE_COLUMNS")
SQL_ALLOWANCE = ("gcp/schema.sql", (
    "-- Split/dividend-adjusted close from AlphaVantage TIME_SERIES_DAILY_ADJUSTED",
    "adjusted_close      DOUBLE PRECISION,",
))


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                ids.add(id(body[0].value))
    return ids


def _allowance_ids(tree: ast.Module, rel: str) -> set[int]:
    if rel != ALLOWANCE[0]:
        return set()
    ids = set()
    for stmt in tree.body:
        targets = (stmt.targets if isinstance(stmt, ast.Assign)
                   else [stmt.target] if isinstance(stmt, ast.AnnAssign) else [])
        if any(isinstance(t, ast.Name) and t.id == ALLOWANCE[1] for t in targets) and stmt.value:
            ids.update(id(n) for n in ast.walk(stmt.value) if isinstance(n, ast.Constant))
    return ids


def _root_name(node: ast.AST) -> str | None:
    while True:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, (ast.Attribute, ast.Subscript)):
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        else:
            return None


def _bindings(tree: ast.AST) -> tuple[set[str], set[str], set[str]]:
    """(names bound to the requests module, names bound to requests.get,
    post or request, names reached through a yfinance import)."""
    requests_mod, requests_fns, yf = set(), set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "requests":
                    requests_mod.add(alias.asname or "requests")
                if alias.name == "yfinance" or alias.name.startswith("yfinance."):
                    yf.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "requests":
                requests_fns.update(a.asname or a.name for a in node.names
                                    if a.name in ("get", "post", "request"))
            if node.module == "yfinance" or node.module.startswith("yfinance."):
                yf.update(a.asname or a.name for a in node.names)
    # A name assigned from something reached through yfinance (t = yf.Ticker(x))
    # is reached through it too.
    for _ in range(2):
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign) and _root_name(node.value) in yf):
                yf.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return requests_mod, requests_fns, yf


def _is_request_call(call: ast.Call, requests_mod, requests_fns, yf) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute):
        if (func.attr in ("get", "post", "request") and isinstance(func.value, ast.Name)
                and func.value.id in requests_mod):
            return True
        if func.attr in MINUTE_HELPERS:
            return True
    if isinstance(func, ast.Name) and (func.id in requests_fns or func.id in MINUTE_HELPERS):
        return True
    return _root_name(func) in yf


def _flag_violation(value: ast.AST) -> bool:
    """True unless the value is the literal 'false' or False."""
    return not (isinstance(value, ast.Constant)
                and (value.value is False or value.value == "false"))


def _key(node: ast.AST | None):
    """A dict key as the guard reads it: None for a ** unpacking, the
    constant for a literal key, and a marker for a computed one."""
    if node is None:
        return None
    return node.value if isinstance(node, ast.Constant) else "<expr>"


def _request_pairs(pairs, out: list[tuple[int, str]], line: int) -> None:
    """Check (key, value) pairs that are request parameters; a None key is a
    ** unpacking of `value`."""
    for key, value in pairs:
        if key is None:
            if isinstance(value, ast.Dict):
                _request_pairs([(_key(k), v) for k, v in zip(value.keys, value.values)],
                               out, value.lineno)
            else:
                out.append((getattr(value, "lineno", line), "request_unpacks_unreadable_keys"))
        elif key in REQUEST_FLAGS and _flag_violation(value):
            out.append((getattr(value, "lineno", line), "request_asks_adjusted"))


def adjusted_sites(src: str, rel: str) -> list[tuple[int, str]]:
    """(line, rule) for every violation in one .py text; `rel` is its path
    from the repo root, which only the allowance reads."""
    tree = ast.parse(src)
    exempt = _docstring_ids(tree) | _allowance_ids(tree, rel)
    requests_mod, requests_fns, yf = _bindings(tree)
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in exempt:
            if ADJUSTED_FUNCTION.search(node.value):
                out.append((node.lineno, "adjusted_vendor_function"))
            elif ADJUSTED_NAME.search(node.value):
                out.append((node.lineno, "adjusted_close_name"))
        elif isinstance(node, ast.Dict):
            keys = [_key(k) for k in node.keys]
            if "function" in keys:
                _request_pairs(list(zip(keys, node.values)), out, node.lineno)
        elif isinstance(node, ast.Call) and _is_request_call(node, requests_mod, requests_fns, yf):
            _request_pairs([(kw.arg, kw.value) for kw in node.keywords], out, node.lineno)
    return sorted(out)


def sql_adjusted_lines(text: str, rel: str) -> list[int]:
    """Line numbers of a .sql text naming an adjusted function or close,
    the two allowed lines of gcp/schema.sql excepted."""
    lines = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not (ADJUSTED_FUNCTION.search(line) or ADJUSTED_NAME.search(line)):
            continue
        if rel == SQL_ALLOWANCE[0] and line.strip() in SQL_ALLOWANCE[1]:
            continue
        lines.append(number)
    return lines


def _guarded_files(root: Path, suffix: str, trees=GUARDED_TREES):
    for tree in trees:
        for path in sorted((root / tree).rglob(f"*{suffix}")):
            rel = path.relative_to(root)
            if ("tests" in rel.parts or "node_modules" in rel.parts
                    or path.name.startswith("test_")):
                continue
            yield path, rel.as_posix()


def tree_sites(root: Path) -> list[tuple[str, int, str]]:
    """(path, line, rule) for every violation in a checkout's guarded .py files."""
    return [(rel, line, rule)
            for path, rel in _guarded_files(root, ".py")
            for line, rule in adjusted_sites(path.read_text(encoding="utf-8"), rel)]


def tree_sql_sites(root: Path) -> list[tuple[str, int]]:
    """(path, line) for every .sql line under gcp/ naming an adjusted price."""
    return [(rel, line)
            for path, rel in _guarded_files(root, ".sql", trees=("gcp",))
            for line in sql_adjusted_lines(path.read_text(encoding="utf-8"), rel)]


def test_nothing_in_the_repo_fetches_stores_or_reads_an_adjusted_price():
    """On main 4155a10f the same walk reported 31 lines in 12 .py files and
    the .sql scan one more, gcp/queries/nan_triage.sql:31. A site reported
    here is one an earlier change missed: fix it there, never widen the
    guard."""
    assert tree_sites(REPO) == []
    assert tree_sql_sites(REPO) == []
    # The allowance still covers exactly the two schema lines it names.
    schema = (REPO / "gcp/schema.sql").read_text(encoding="utf-8").splitlines()
    assert sorted(line.strip() for line in schema
                  if line.strip() in SQL_ALLOWANCE[1]) == sorted(SQL_ALLOWANCE[1])


_YF = "import yfinance as yf\n"


@pytest.mark.parametrize("src, rel, n", [
    # one violation per rule
    ("f = 'TIME_SERIES_WEEKLY_ADJUSTED'", "gcp/x.py", 1),
    ("c = 'Adj Close'", "gcp/x.py", 1),
    ("p = {'function': 'X', 'adjusted': 'true'}", "gcp/x.py", 1),
    (_YF + "yf.download('SPY', auto_adjust=True)", "scripts/x.py", 1),
    # what requests nothing, or asks as traded, is allowed
    ('counts = {"as_traded": 0, "inferred": 0, "adjusted": 0, "odd": 0}',
     "gcp/fetchers/export_intraday_bars.py", 0),
    ("p = {'function': 'TIME_SERIES_INTRADAY', 'adjusted': True}", "gcp/x.py", 1),
    ("p = {'function': 'TIME_SERIES_INTRADAY', 'adjusted': 'false', **{'adjusted': 'true'}}",
     "gcp/x.py", 1),
    ("p = {'function': 'TIME_SERIES_INTRADAY', **extra}", "gcp/x.py", 1),
    ("x.ewm(span=9, adjust=False)", "lib/x.py", 0),
    ("verdict = 'ADJUSTED'", "gcp/x.py", 0),
    ("p = {'function': 'TIME_SERIES_INTRADAY', 'adjusted': 'false'}", "gcp/x.py", 0),
    ('def f():\n    """Once asked TIME_SERIES_DAILY_ADJUSTED for the adjusted close."""\n',
     "gcp/x.py", 0),
    ("ADJUSTED_CLOSE_COLUMNS = ('Adj Close', 'adj_close', 'adjusted_close', 'adjclose')",
     "lib/data_loader.py", 0),
    ("ADJUSTED_CLOSE_COLUMNS = ('Adj Close', 'adj_close', 'adjusted_close', 'adjclose')",
     "lib/other.py", 4),
    ("df['Adj Close']", "lib/data_loader.py", 1),
    # the keyword rule reaches every request call it names
    ("import requests\nrequests.get(u, params=p, adjusted='true')", "gcp/x.py", 1),
    ("import requests\nrequests.get(u, **kw)", "gcp/x.py", 1),
    ("fetch_minute_bars('SPY', d, k, adjusted=adjusted)", "gcp/x.py", 1),
    ("fetch_minute_bars('SPY', d, k, adjusted=False)", "gcp/x.py", 0),
    (_YF + "t = yf.Ticker('SPY')\nt.history(period='1y', auto_adjust=True)", "scripts/x.py", 1),
    (_YF + "yf.download('SPY', auto_adjust=False)", "scripts/x.py", 0),
    ("f\"{d}/{t}_daily_adjusted.csv\"", "scripts/x.py", 1),
])
def test_the_guard_tells_adjusted_from_everything_else(src, rel, n):
    assert len(adjusted_sites(src, rel)) == n, adjusted_sites(src, rel)


@pytest.mark.parametrize("text, rel, n", [
    ("SELECT count(*) FILTER (WHERE \"adjusted_close\"='NaN') FROM t;", "gcp/queries/x.sql", 1),
    ("    -- Split/dividend-adjusted close from AlphaVantage TIME_SERIES_DAILY_ADJUSTED\n"
     "    adjusted_close      DOUBLE PRECISION,\n", "gcp/schema.sql", 0),
    ("    adjusted_close      DOUBLE PRECISION,\n", "gcp/other.sql", 1),
    ("    adj_close NUMERIC,\n", "gcp/schema.sql", 1),
])
def test_the_sql_scan_allows_only_the_schema_lines(text, rel, n):
    assert len(sql_adjusted_lines(text, rel)) == n
