"""The committed OpenAPI snapshot must match the running app.

platform/api/openapi.json is the cross-repo contract that TeneikaAskew/solyra
vendors and validates its fixtures against (see scripts/export_openapi.py).
This test turns a stale snapshot into a red PR, so a route or response-model
change cannot merge without the contract file that advertises it.

Hermetic: the app is imported the same way test_platform_api.py imports it;
no database, no network.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_EXPORTER = PROJECT_ROOT / "scripts" / "export_openapi.py"


def _load_exporter():
    spec = importlib.util.spec_from_file_location("export_openapi", _EXPORTER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _operations(spec: dict) -> set[str]:
    return {f"{m.upper()} {p}" for p, ops in spec["paths"].items() for m in ops}


def test_committed_openapi_snapshot_matches_app():
    exporter = _load_exporter()
    assert exporter.SNAPSHOT.exists(), (
        "platform/api/openapi.json is missing — run: python scripts/export_openapi.py"
    )
    committed_text = exporter.SNAPSHOT.read_text(encoding="utf-8")
    live = exporter.generate_openapi()
    live_text = exporter.render(live)
    if live_text == committed_text:
        return

    committed = json.loads(committed_text)
    added = sorted(_operations(live) - _operations(committed))
    removed = sorted(_operations(committed) - _operations(live))
    raise AssertionError(
        "platform/api/openapi.json is stale — run: python scripts/export_openapi.py\n"
        f"  operations added:   {added}\n"
        f"  operations removed: {removed}\n"
        "  (both empty means a parameter, response model, or docstring changed;"
        " regenerate and review the diff)"
    )


def test_snapshot_is_canonical_json():
    """The file is what render() produces — sorted keys, trailing newline —
    so a hand edit or a differently-configured formatter cannot masquerade
    as a regeneration."""
    exporter = _load_exporter()
    text = exporter.SNAPSHOT.read_text(encoding="utf-8")
    assert text == exporter.render(json.loads(text))


def test_the_ping_description_does_not_name_the_retired_service():
    """solyra-api-prod was deleted on 2026-10-10 (#1366); the ping docstring
    is part of the contract solyra vendors, so it must not describe that
    service as the live one."""
    spec = json.loads(_load_exporter().SNAPSHOT.read_text(encoding="utf-8"))
    description = spec["paths"]["/api/earnings/health/ping"]["get"]["description"]
    assert "solyra-api-prod" not in description
    assert "sits behind IAP" not in description
    assert "kept for manual and in-cluster warm-up" in description


def test_replay_routes_document_their_error_responses():
    """The four replay routes answer a 404 or a 503 whose body is
    `{"detail": "<string>"}`, and solyra tells the cases apart by the start
    of `detail` (FEAT-REPLAY-001, Design 7). The contract says so: the two
    GET routes list 404 and 503, the two POST routes 503 only (there a
    missing day is a 200 with `unavailable`, never a 404)."""
    spec = json.loads(_load_exporter().SNAPSHOT.read_text(encoding="utf-8"))
    error_detail = {"$ref": "#/components/schemas/ErrorDetail"}

    def response_schema(path, method, code):
        response = spec["paths"][path][method]["responses"][code]
        return response["content"]["application/json"]["schema"]

    for path in ("/api/market/data/{ticker}/{date}",
                 "/api/market/reference/{ticker}/{date}"):
        assert response_schema(path, "get", "404") == error_detail, path
        assert response_schema(path, "get", "503") == error_detail, path

    for path in ("/api/backtest/replay-trades", "/api/style/mine-and-validate"):
        assert response_schema(path, "post", "503") == error_detail, path
        assert "404" not in spec["paths"][path]["post"]["responses"], path

    schema = spec["components"]["schemas"]["ErrorDetail"]
    assert schema["required"] == ["detail"]
    assert schema["properties"]["detail"]["type"] == "string"
