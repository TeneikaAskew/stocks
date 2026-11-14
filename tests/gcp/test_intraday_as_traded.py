"""Every AlphaVantage 1-min request asks for as-traded prices (FEAT-DATA-001,
docs/superpowers/specs/2026-11-13-feat-data-001-intraday-as-traded.md).

TIME_SERIES_INTRADAY returns dividend-adjusted prices unless the request says
adjusted=false, and the adjustment is computed as of the call. A writer that
leaves it out stores a bar below the price it traded at once an ex-dividend
date passes, and the nightly previous-month refetch then rewrites the month at
that basis (SPY 2026-08-31 15:59 ET: 765.053 stored, 766.95 as traded). There
is no exception: writers, the live checks and the local scripts all send
adjusted=false.
"""
from __future__ import annotations

import ast
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from gcp import backfill_ticker as bt
from gcp.fetchers import fetch_alphavantage_intraday as fai
from gcp.fetchers import fetch_market_data as fmd

REPO = Path(__file__).resolve().parents[2]
SCANNED = ("gcp", "scripts", "platform")


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _sent_params(module, call):
    """The params of the one requests.get ``call`` makes. The vendor answers
    with a rate-limit note, so no bars are parsed and nothing is written."""
    seen = []

    def fake_get(url, params=None, **kw):
        seen.append(params)
        return _Resp({"Note": "rate limit"})

    with patch.object(module.requests, "get", side_effect=fake_get):
        try:
            call()
        except RuntimeError:
            pass  # backfill_ticker raises on a vendor note, by design
    assert len(seen) == 1, seen
    return seen[0]


def test_nightly_and_backfill_month_fetch_requests_as_traded():
    p = _sent_params(fai, lambda: fai.fetch_month("SPY", 2025, 11, "key"))
    assert p["function"] == "TIME_SERIES_INTRADAY" and p["adjusted"] == "false"


def test_daily_fetcher_requests_as_traded_through_both_functions():
    """fetch_minute_data is what process_ticker and the premarket refresh call;
    a fix to fetch_minute_bars alone would leave them adjusted."""
    p = _sent_params(fmd, lambda: fmd.fetch_minute_bars("SPY", "2025-11-14", "key"))
    assert p["adjusted"] == "false"
    p = _sent_params(fmd, lambda: fmd.fetch_minute_data("SPY", "2025-11-14", "key"))
    assert p["adjusted"] == "false"
    p = _sent_params(fmd, lambda: fmd.fetch_minute_bars("SPY", "2025-11-14", "key", adjusted=False))
    assert p["adjusted"] == "false"


def test_asking_for_adjusted_minute_bars_is_refused():
    for fn in (fmd.fetch_minute_bars, fmd.fetch_minute_data):
        with patch.object(fmd.requests, "get") as get, pytest.raises(ValueError, match="as traded only"):
            fn("SPY", "2025-11-14", "key", adjusted=True)
        get.assert_not_called()


def test_backfill_ticker_month_fetch_requests_as_traded():
    p = _sent_params(bt, lambda: bt.av_intraday_month("SPY", "2025-11", "key"))
    assert p["function"] == "TIME_SERIES_INTRADAY" and p["adjusted"] == "false"


def intraday_requests(tree):
    """[(line, the dict's adjusted value nodes, in_a_request_dict)] for every
    use of the endpoint name in code: the bare string 'TIME_SERIES_INTRADAY'
    as a value, or any string that spells out a query
    ('function=TIME_SERIES_INTRADAY'). Prose in docstrings names the endpoint
    without 'function=' and is not matched; comments are not in the tree.

    What this cannot see: a key set on the dict after it is built
    (p['adjusted'] = ..., p.update(...)), a ``**extra`` merge, and a request
    assembled outside gcp/, scripts/ and platform/."""
    found, in_dict = [], set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if (isinstance(k, ast.Constant) and k.value == "function"
                        and isinstance(v, ast.Constant) and v.value == "TIME_SERIES_INTRADAY"):
                    adj = [val for key, val in zip(node.keys, node.values)
                           if isinstance(key, ast.Constant) and key.value == "adjusted"]
                    found.append((v.lineno, adj, True))
                    in_dict.add(id(v))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in in_dict
                and (node.value == "TIME_SERIES_INTRADAY" or "function=TIME_SERIES_INTRADAY" in node.value)):
            found.append((node.lineno, [], False))
    return found


def violations(tree):
    out = []
    for line, adj, in_dict in intraday_requests(tree):
        if not in_dict:
            out.append((line, "TIME_SERIES_INTRADAY used outside a request dict the guard can read"))
        elif not adj:
            out.append((line, "no adjusted key (AlphaVantage then adjusts)"))
        elif len(adj) > 1:
            out.append((line, "adjusted is set more than once (the last one wins)"))
        elif not (isinstance(adj[0], ast.Constant) and adj[0].value == "false"):
            out.append((line, "adjusted is not the literal 'false'"))
    return out


def test_every_intraday_request_in_the_repo_asks_for_as_traded():
    bad, sites = [], []
    for top in SCANNED:
        for path in sorted((REPO / top).rglob("*.py")):
            rel = path.relative_to(REPO).as_posix()
            if "/tests/" in f"/{rel}" or "/node_modules/" in rel:
                continue
            with warnings.catch_warnings():
                # Another file's invalid escape is not this test's business, and
                # under -W error it would fail the parse.
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(path.read_text(), filename=rel)
            sites += [(rel, line) for line, _, _ in intraday_requests(tree)]
            bad += [f"{rel}:{line} {why}" for line, why in violations(tree)]
    files = {f for f, _ in sites}
    assert {"gcp/fetchers/fetch_alphavantage_intraday.py", "gcp/fetchers/fetch_market_data.py", "gcp/backfill_ticker.py",
            "gcp/signal_monitor.py", "scripts/fetch_alphavantage_intraday.py", "scripts/fetch_market_data.py",
            "platform/api/routers/live.py"} <= files, sorted(files)
    assert len(sites) >= 8, sites                      # live.py holds two
    assert not bad, "TIME_SERIES_INTRADAY requests not on adjusted=false:\n  " + "\n  ".join(bad)


@pytest.mark.parametrize("src, n_bad", [
    ("p = {'function': 'TIME_SERIES_INTRADAY', 'adjusted': 'false'}", 0),
    ("p = {'function': 'TIME_SERIES_INTRADAY'}", 1),
    ("p = {'function': 'TIME_SERIES_INTRADAY', 'adjusted': 'true'}", 1),
    ("def f(adjusted=False):\n    p = {'function': 'TIME_SERIES_INTRADAY', 'adjusted': 'true' if adjusted else 'false'}", 1),
    ("url = BASE + '?function=' + 'TIME_SERIES_INTRADAY'", 1),
    ("url = f'https://x/query?function=TIME_SERIES_INTRADAY&symbol={s}&adjusted=false'", 1),
    ("p = {'function': 'TIME_SERIES_INTRADAY', 'adjusted': 'false', 'adjusted': 'true'}", 1),
    ('"""Docs mention TIME_SERIES_INTRADAY here."""\nx = 1  # TIME_SERIES_INTRADAY', 0),
    ("p = {'function': 'TIME_SERIES_DAILY_ADJUSTED'}", 0),
])
def test_the_guard_tells_as_traded_from_everything_else(src, n_bad):
    assert len(violations(ast.parse(src))) == n_bad
