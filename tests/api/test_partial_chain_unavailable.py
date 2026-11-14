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
