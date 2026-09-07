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
