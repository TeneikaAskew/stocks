#!/usr/bin/env python3
"""Export the FastAPI OpenAPI document to platform/api/openapi.json.

The committed snapshot is the machine-readable API contract that the
frontend repo (TeneikaAskew/solyra) validates against in its own CI: solyra
vendors this file from `main`, fails its build when the vendored copy is
stale, and checks its mock payloads against the response schemas here.
Before this file existed nothing tied the two repos together — a renamed
field passed CI on both sides and broke the app at runtime (solyra
CLAUDE.md Rule 6).

tests/api/test_openapi_snapshot.py fails whenever the committed file does
not match the running app, so a PR that changes a route or a response model
cannot merge without regenerating it:

    python scripts/export_openapi.py

``--check`` exits 1 instead of writing when the file is stale.

Determinism: ``app.openapi()`` is a pure function of the route table and the
Pydantic models, rendered with sorted keys. A FastAPI or Pydantic upgrade
that changes how schemas are emitted will show up as a stale snapshot; that
is a real contract change and the fix is to regenerate and review the diff.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLATFORM_DIR = REPO_ROOT / "platform"
SNAPSHOT = PLATFORM_DIR / "api" / "openapi.json"


def generate_openapi() -> dict:
    """Import the app the way tests/api does (cwd and sys.path on platform/)."""
    original_cwd = os.getcwd()
    if str(PLATFORM_DIR) not in sys.path:
        sys.path.insert(0, str(PLATFORM_DIR))
    os.chdir(PLATFORM_DIR)
    try:
        from api.main import app  # deferred: needs platform/ on sys.path

        return app.openapi()
    finally:
        os.chdir(original_cwd)


def render(spec: dict) -> str:
    """Canonical text: sorted keys, 2-space indent, UTF-8 kept readable."""
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the committed snapshot is stale; never write",
    )
    args = parser.parse_args(argv)

    text = render(generate_openapi())
    rel = SNAPSHOT.relative_to(REPO_ROOT)
    current = SNAPSHOT.read_text(encoding="utf-8") if SNAPSHOT.exists() else None
    if args.check:
        if current == text:
            print(f"{rel} is up to date")
            return 0
        print(f"{rel} is stale — run: python scripts/export_openapi.py", file=sys.stderr)
        return 1
    SNAPSHOT.write_text(text, encoding="utf-8")
    print(f"wrote {rel} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
