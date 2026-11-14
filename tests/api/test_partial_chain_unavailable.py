"""Partial-chain / chain-unavailable contract for the options routes
(FEAT-OPTION-001). Schema tests first; route tests are added alongside."""
import copy
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic")

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "platform"))
sys.path.insert(0, str(REPO / "platform" / "api"))

from api import schemas  # noqa: E402
from tests.api.test_options_router import (  # noqa: E402,F401  (fixtures imported by name)
    _chain_frame, chain_client, chain_clock, _install_chain_query,
)
from tests.api.test_options_live import (  # noqa: E402,F401
    client, _FAKE_AV_OK, _FakeResponse, _patch_av,
)

BASELINE = json.loads(
    (REPO / "tests" / "fixtures" / "options_routes_baseline_960a9090.json").read_text()
)


def _minimal(model):
    """Smallest valid payload for `model`: the pre-change route output plus
    the new required fields."""
    if model is schemas.OptionsChainMetadata:
        return {**BASELINE["chain"]["metadata"], "sides_present": "both"}
    if model is schemas.OptionsChainResponse:
        payload = copy.deepcopy(BASELINE["chain"])
        payload["metadata"]["sides_present"] = "both"
        payload["chain_state"] = "available"
        return payload
    if model is schemas.OptionsMetrics:
        return copy.deepcopy(BASELINE["greeks"]["metrics"])
    if model is schemas.GammaLevelsResponse:
        return copy.deepcopy(BASELINE["levels"])
    if model is schemas.GammaGridResponse:
        return copy.deepcopy(BASELINE["grid_live"])
    if model is schemas.GammaNodesResponse:
        return copy.deepcopy(BASELINE["nodes_live"])
    raise KeyError(model)


def test_chain_fields_have_no_server_default():
    assert schemas.OptionsChainMetadata.model_fields["sides_present"].is_required()
    assert schemas.OptionsChainResponse.model_fields["chain_state"].is_required()
    assert schemas.OptionsChainResponse.model_fields["reason"].default is None


def test_metrics_and_totals_are_nullable_but_required():
    for model, field in ((schemas.OptionsMetrics, "total_gex"), (schemas.OptionsMetrics, "total_vex"),
                         (schemas.OptionsMetrics, "put_call_ratio"), (schemas.GammaLevelsResponse, "total_gex"),
                         (schemas.GammaGridResponse, "total_gex"), (schemas.GammaGridResponse, "total_vex"),
                         (schemas.GammaNodesResponse, "total_gex"), (schemas.GammaNodesResponse, "total_vex")):
        info = model.model_fields[field]
        assert info.is_required(), (model, field)
        assert model.model_validate({**_minimal(model), field: None}).model_dump()[field] is None


def _without(d, *keys):
    return {k: v for k, v in d.items() if k not in keys}


def _canon(d):
    return json.dumps(d, sort_keys=True)


class TestChainRoute:
    def test_both_sided_chain_byte_identical_plus_new_fields(self, chain_client, chain_clock, monkeypatch):
        _install_chain_query(monkeypatch, _chain_frame())
        data = chain_client.get("/api/options/SPY/2026-06-01").json()
        assert _canon({**_without(data, "chain_state"), "metadata": _without(data["metadata"], "sides_present")}) == _canon(BASELINE["chain"])
        assert data["metadata"]["sides_present"] == "both" and data["chain_state"] == "available" and "reason" not in data

    def test_calls_only_chain_keeps_rows_and_is_unavailable(self, chain_client, chain_clock, monkeypatch):
        df = _chain_frame()
        _install_chain_query(monkeypatch, df[df["option_type"] == "calls"])
        data = chain_client.get("/api/options/SPY/2026-06-01").json()
        assert data["metadata"]["sides_present"] == "calls_only" and data["chain_state"] == "unavailable"
        assert data["reason"] == "puts_missing" and len(data["options"]) == 3 and data["metadata"]["row_count"] == 3

    def test_puts_only_chain_reason_names_calls(self, chain_client, chain_clock, monkeypatch):
        df = _chain_frame()
        _install_chain_query(monkeypatch, df[df["option_type"] == "puts"])
        data = chain_client.get("/api/options/SPY/2026-06-01").json()
        assert data["metadata"]["sides_present"] == "puts_only" and data["chain_state"] == "unavailable"
        assert data["reason"] == "calls_missing" and len(data["options"]) == 3

    def test_warm_hit_carries_the_same_state(self, chain_client, chain_clock, monkeypatch):
        df = _chain_frame()
        calls = _install_chain_query(monkeypatch, df[df["option_type"] == "puts"])
        first = chain_client.get("/api/options/SPY/2026-06-01").json()
        second = chain_client.get("/api/options/SPY/2026-06-01").json()
        assert len(calls) == 1 and _without(first, "cached") == _without(second, "cached") and second["cached"] is True

    def test_unrecognised_option_type_rows_answer_404(self, chain_client, chain_clock, monkeypatch):
        df = _chain_frame()
        df["option_type"] = "junk"
        import pandas as pd
        from tests.api.test_options_router import options_router

        def fake_query(sql, params=None):  # the 404 path also asks for the nearest date
            return pd.DataFrame({"nearest": [None]}) if "AS nearest" in sql else df

        monkeypatch.setattr(options_router, "query_to_dataframe", fake_query)
        r = chain_client.get("/api/options/SPY/2026-06-01")
        assert r.status_code == 404 and "No AlphaVantage options data" in r.json()["detail"]


class TestLiveChainRoute:
    def test_both_sided_live_byte_identical_plus_new_fields(self, client, monkeypatch):
        _patch_av(monkeypatch, _FakeResponse(200, _FAKE_AV_OK))
        data = client.get("/api/options/live/SPY/2025-01-17").json()
        assert "snapshot_timestamp" in data
        assert _canon({**_without(data, "chain_state", "snapshot_timestamp"), "metadata": _without(data["metadata"], "sides_present")}) == _canon(_without(BASELINE["live_chain"], "snapshot_timestamp"))
        assert data["metadata"]["sides_present"] == "both" and data["chain_state"] == "available"

    def test_calls_only_live_is_unavailable(self, client, monkeypatch):
        body = {**_FAKE_AV_OK, "data": [r for r in _FAKE_AV_OK["data"] if r["type"] == "call"]}
        _patch_av(monkeypatch, _FakeResponse(200, body))
        data = client.get("/api/options/live/SPY/2025-01-17").json()
        assert data["metadata"]["sides_present"] == "calls_only" and data["chain_state"] == "unavailable"
        assert data["reason"] == "puts_missing" and len(data["options"]) == 1


def _baseline_option_records():
    """The six `_chain_frame()` contracts as the plain records Task 0 posted."""
    return [
        {"type": "call" if r["option_type"] == "calls" else "put",
         "strike": float(r["strike"]), "open_interest": int(r["open_interest"]),
         "gamma": float(r["gamma"]), "vega": float(r["vega"]),
         "delta": float(r["delta"]), "volume": int(r["volume"])}
        for r in _chain_frame().to_dict("records")
    ]


class TestGreeksRoute:
    def test_both_sided_byte_identical(self, chain_client):
        r = chain_client.post("/api/options/greeks", json={"spot_price": 100.05, "options": _baseline_option_records()})
        assert _canon(r.json()) == _canon(BASELINE["greeks"]) and "reason" not in r.json()

    @pytest.mark.parametrize("side,reason", [("call", "puts_missing"), ("put", "calls_missing")])
    def test_one_sided_chain_null_metrics_with_reason(self, chain_client, side, reason):
        recs = [o for o in _baseline_option_records() if o["type"] == side]
        data = chain_client.post("/api/options/greeks", json={"spot_price": 100.05, "options": recs}).json()
        assert data["metrics"] == {"total_gex": None, "total_vex": None, "zero_gamma": None, "max_pain": None, "implied_move": None, "put_call_ratio": None}
        assert data["reason"] == reason and data["aggregated"] == [] and data["gex_by_strike"] == [] and data["nodes"]["kingNode"] is None

    def test_empty_chain_reason(self, chain_client):
        assert chain_client.post("/api/options/greeks", json={"spot_price": 100.05, "options": []}).json()["reason"] == "empty_chain"

    def test_non_positive_spot_reason(self, chain_client):
        data = chain_client.post("/api/options/greeks", json={"spot_price": 0.0, "options": _baseline_option_records()}).json()
        assert data["reason"] == "spot_unavailable" and data["metrics"]["total_gex"] is None and data["metrics"]["put_call_ratio"] is None
