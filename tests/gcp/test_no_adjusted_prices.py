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
YF_PRICE_CALLS = ("download", "history")
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
            # yfinance's download and history adjust unless told not to, so a
            # price call that leaves auto_adjust out asks for adjusted prices.
            if (_root_name(node.func) in yf and isinstance(node.func, ast.Attribute)
                    and node.func.attr in YF_PRICE_CALLS
                    and not any(kw.arg in ("auto_adjust", None) for kw in node.keywords)):
                out.append((node.lineno, "yfinance_default_adjusts"))
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
    # yfinance adjusts unless told not to: a price call must name auto_adjust
    (_YF + "yf.download('SPY', period='1y')", "scripts/x.py", 1),
    (_YF + "t = yf.Ticker('SPY')\nt.history(period='1y')", "scripts/x.py", 1),
    (_YF + "t = yf.Ticker('SPY')\nt.history(period='1y', auto_adjust=False)", "scripts/x.py", 0),
    (_YF + "info = yf.Ticker('SPY').info", "scripts/x.py", 0),
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


# ─── Close-out steps 1 and 2: every deployed reader ──────────────────────────
#
# Until it is redeployed, a job or service on an older image still selects
# adjusted_close (DataLoader._load_daily_from_sql), and once the companion
# data spec drops the column that query fails. So the close-out deploys every
# Cloud Run job and service whose entrypoint reaches lib/data_loader.py,
# lib/strat.py or a module naming adjusted_close through its imports.

READER_TARGETS = ("lib/data_loader.py", "lib/strat.py")


def _resolve_module(root: Path, dotted: str, search: tuple[Path, ...]) -> Path | None:
    parts = dotted.split(".")
    for base in search:
        for candidate in (base.joinpath(*parts).with_suffix(".py"),
                          base.joinpath(*parts, "__init__.py")):
            if candidate.is_file():
                return candidate
    return None


def _package_inits(path: Path, base: Path) -> list[Path]:
    """The __init__.py files Python runs before `path`, under `base`."""
    out = []
    folder = path.parent
    while folder != base and base in folder.parents:
        init = folder / "__init__.py"
        if init.is_file():
            out.append(init)
        folder = folder.parent
    return out


def _imported_files(path: Path, root: Path, search: tuple[Path, ...]) -> set[Path]:
    """Files one module's imports load: absolute and relative, at any depth
    of the module (function-level imports included), and their packages."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    base = next((b for b in search if b in path.parents), root)
    package = ".".join(path.relative_to(base).with_suffix("").parts[:-1])
    if path.name == "__init__.py":
        package = ".".join(path.relative_to(base).parent.parts)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = package.split(".") if package else []
                anchor = anchor[:len(anchor) - (node.level - 1)] if node.level > 1 else anchor
                module = ".".join(anchor + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            if module:
                names.append(module)
            names.extend(f"{module}.{alias.name}" if module else alias.name
                         for alias in node.names if alias.name != "*")
    found: set[Path] = set()
    for name in names:
        parts = name.split(".")
        for i in range(1, len(parts) + 1):
            hit = _resolve_module(root, ".".join(parts[:i]), search)
            if hit is not None:
                found.add(hit)
    return found


def _reached(entry: Path, root: Path) -> set[Path]:
    search = (root, root / "platform")
    seen: set[Path] = set()
    stack = [entry, *_package_inits(entry, next((b for b in search if b in entry.parents), root))]
    while stack:
        path = stack.pop()
        if path in seen:
            continue
        seen.add(path)
        stack.extend(_imported_files(path, root, search) - seen)
    return seen


def _service_entry(root: Path, name: str, script: str) -> str:
    """Repo-relative entry module of a Cloud Run service: from its deploy
    command (`--command uvicorn --args a.b:app` or `--args=-m,a.b`), else
    from the image's CMD (platform/Dockerfile's `uvicorn api.main:app
    --app-dir /app/platform`)."""
    text = (root / script).read_text(encoding="utf-8")
    for block in re.split(r"\n(?=\s*gcloud run deploy\s)", text)[1:]:
        head = block.split("\n", 1)[0]
        if name not in head and "${" not in head:
            continue
        lines = []
        for line in block.splitlines():
            lines.append(line)
            if not line.rstrip().endswith("\\"):
                break
        command = " ".join(lines)
        if "${" in head and not re.search(rf'="?{re.escape(name)}"?\s*$', text, re.M):
            continue
        m = re.search(r'--args[= ]"?-m,([\w.]+)', command)
        if m:
            return m.group(1).replace(".", "/") + ".py"
        m = re.search(r'--args[= ]"?([\w.]+):app', command)
        if m:
            return m.group(1).replace(".", "/") + ".py"
    dockerfile = (root / Path(script).parent / "Dockerfile").read_text(encoding="utf-8")
    m = re.search(r"uvicorn\s+([\w.]+):app.*--app-dir\s+/app/(\w+)", dockerfile)
    if m:
        return f"{m.group(2)}/" + m.group(1).replace(".", "/") + ".py"
    raise ValueError(f"{script}: no entry module found for service {name}")


def _dispatch_arms(root: Path) -> dict[str, set[str]]:
    """`./gcp/deploy.sh <arm>` -> every shell function the arm's commands
    call, transitively through the functions deploy.sh defines."""
    from scripts.maintenance import doc_inventory as inventory

    text = inventory._strip_comments((root / "gcp/deploy.sh").read_text(encoding="utf-8"))
    funcs = inventory._functions(text)
    names = set(inventory.deploy_targets(root))
    dispatch = text[text.index('case "${1:-help}" in'):]
    arms: dict[str, set[str]] = {}
    for m in re.finditer(r"^\s{4}([a-z][a-z0-9-]*)\)(.*?);;", dispatch, re.M | re.S):
        if m.group(1) not in names:
            continue
        todo = [w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", m.group(2)) if w in funcs]
        closure: set[str] = set()
        while todo:
            fn = todo.pop()
            if fn in closure:
                continue
            closure.add(fn)
            todo.extend(w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", funcs[fn][1])
                        if w in funcs and w not in closure)
        arms[m.group(1)] = closure
    return arms


def _targets(arms: dict[str, set[str]], fn: str) -> str:
    named = sorted(arm for arm, closure in arms.items() if fn in closure and arm != "all")
    if named:
        return ", ".join(named)
    return "all" if fn in arms.get("all", set()) else ""


def adjusted_readers(root: Path) -> list[dict]:
    """One row per deployed Cloud Run job or service whose entrypoint reaches
    lib/data_loader.py, lib/strat.py or a module naming adjusted_close."""
    from scripts.maintenance import doc_inventory as inventory

    root = Path(root).resolve()
    arms = _dispatch_arms(root)
    text = inventory._strip_comments((root / "gcp/deploy.sh").read_text(encoding="utf-8"))
    funcs = inventory._functions(text)
    entries = [("job", job["name"], inventory.entry_module(job), _targets(arms, job["function"]))
               for job in inventory.deploy_jobs(root)]
    for service in inventory.deploy_services(root):
        if service["script"] == "platform/deploy.sh":
            target = "platform/deploy.sh"
        else:
            owner = next(fn for fn, (_, body) in funcs.items()
                         if re.search(rf"gcloud run deploy\s+(\"?\$\{{[A-Z_]+\}}\"?|{re.escape(service['name'])}\b)",
                                      body)
                         and (service["name"] in body or re.search(
                             rf'^\s*(?:readonly\s+|local\s+)?[A-Z_]+="?{re.escape(service["name"])}"?\s*$',
                             text, re.M)))
            target = _targets(arms, owner)
        entries.append(("service", service["name"],
                        _service_entry(root, service["name"], service["script"]), target))
    rows = []
    for kind, name, entry, target in entries:
        path = root / entry
        if not entry or not path.is_file():
            raise ValueError(f"{kind} {name}: entry module {entry!r} not found")
        reached = _reached(path, root)
        hits = sorted(p.relative_to(root).as_posix() for p in reached
                      if p.relative_to(root).as_posix() in READER_TARGETS
                      or "adjusted_close" in p.read_text(encoding="utf-8"))
        if hits:
            rows.append({"kind": kind, "name": name, "entry": entry,
                         "reaches": hits, "target": target})
    return sorted(rows, key=lambda r: (r["kind"], r["name"]))


def readers_table(rows: list[dict]) -> str:
    out = ["| Kind | Name | Entry | Reaches | Deploy target |", "|---|---|---|---|---|"]
    out += [f"| {r['kind']} | `{r['name']}` | `{r['entry']}` | "
            + ", ".join(f"`{h}`" for h in r["reaches"]) + f" | `{r['target']}` |"
            for r in rows]
    return "\n".join(out)


def test_reader_walk_finds_the_direct_importers():
    """The walk lists every entrypoint that imports the loader or strat
    directly, each with a deploy target. gcp/trade_logger.py imports
    neither, so it is listed only when another module it imports reaches
    one of them."""
    rows = adjusted_readers(REPO)
    entries = {r["entry"]: r for r in rows}
    for entry in ("gcp/signal_monitor.py", "gcp/signal_monitor_eod_resolver.py",
                  "gcp/premarket_brief.py", "gcp/regime_combo_job.py",
                  "gcp/indicator_correlation_job.py", "platform/api/main.py",
                  "gcp/fetchers/fetch_market_data.py",
                  "gcp/fetchers/backfill_daily_indicators.py", "gcp/backfill_ticker.py"):
        assert entry in entries, entry
    for row in rows:
        assert row["reaches"] and row["target"], row
    direct = {name for node in ast.walk(ast.parse((REPO / "gcp/trade_logger.py").read_text()))
              if isinstance(node, (ast.Import, ast.ImportFrom))
              for name in ([node.module or ""] if isinstance(node, ast.ImportFrom) else [])
              + [a.name for a in node.names]}
    assert not direct & {"lib.data_loader", "lib.strat", "data_loader", "strat"}
    if "gcp/trade_logger.py" in entries:
        reached = {p.relative_to(REPO).as_posix() for p in _reached(REPO / "gcp/trade_logger.py", REPO)}
        assert set(entries["gcp/trade_logger.py"]["reaches"]) <= reached


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3 or sys.argv[1] != "--readers":
        sys.exit("usage: python3 -m tests.gcp.test_no_adjusted_prices --readers <checkout>")
    print(readers_table(adjusted_readers(Path(sys.argv[2]))))
