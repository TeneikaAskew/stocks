"""Structural tests for .github/workflows/architecture-export.yml (FEAT-CICD-001).

Spec: docs/superpowers/specs/2026-11-10-feat-cicd-001-architecture-export.md,
done_when "On-demand workflow". The monthly refresh it replaces held write
permissions, a database secret and a model CLI, and pushed a branch and opened
PRs and issues. This workflow is a read-only exporter: these tests keep it one.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO / ".github/workflows/architecture-export.yml"
RAW = WORKFLOW_PATH.read_text()
DOC = yaml.safe_load(RAW)
# PyYAML reads the bare key `on` as the boolean True.
TRIGGERS = DOC.get("on", DOC.get(True))
STEPS = [s for job in DOC["jobs"].values() for s in job.get("steps", [])]
RUN_TEXT = "\n".join(s.get("run", "") for s in STEPS)


def _code_lines(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


def test_workflow_dispatch_is_the_only_trigger():
    assert TRIGGERS == {"workflow_dispatch": None} or list(TRIGGERS) == ["workflow_dispatch"], TRIGGERS
    assert not (TRIGGERS.get("workflow_dispatch") or {}).get("inputs"), "no inputs: there is nothing to choose"


def test_permissions_are_read_contents_and_mint_an_id_token_only():
    assert DOC["permissions"] == {"contents": "read", "id-token": "write"}
    for name, job in DOC["jobs"].items():
        assert "permissions" not in job, f"job {name} widens the workflow's permissions"


def test_a_ref_other_than_main_is_refused_before_authenticating():
    names = [s.get("name", "") for s in STEPS]
    refuse = next(i for i, s in enumerate(STEPS) if s.get("if") == "github.ref != 'refs/heads/main'")
    assert "exit 1" in STEPS[refuse]["run"]
    assert "${{" not in STEPS[refuse]["run"], "the ref goes through env, not into the script"
    auth = next(i for i, s in enumerate(STEPS) if str(s.get("uses", "")).startswith("google-github-actions/auth"))
    assert refuse < auth, names
    assert refuse == 0, "nothing should run before the refusal"


def test_no_database_secret_and_no_model_cli():
    secrets = set(re.findall(r"secrets\.([A-Z0-9_]+)", RAW))
    assert secrets == {"GCP_WIF_PROVIDER", "GCP_WIF_SA_EMAIL"}, secrets
    code = _code_lines(RAW).lower()
    for word in ("gemini", "claude", "openai", "codex", "npm install", "db_pass", "db_user",
                 "cloud_sql", "cloud-sql", "psql", "pg8000"):
        assert word not in code, f"workflow mentions {word!r} outside a comment"


def test_writes_nothing_back():
    code = _code_lines(RUN_TEXT)
    for pattern in (r"\bgit\s+push\b", r"\bgit\s+commit\b", r"\bgh\s+pr\b", r"\bgh\s+issue\b", r"\bgh\s+api\b"):
        assert not re.search(pattern, code), pattern
    assert not any("handle-workflow-failure" in str(j.get("uses", "")) for j in DOC["jobs"].values())


def test_runs_the_exporter_live_and_writes_the_job_summary():
    assert "python3 -m scripts.maintenance.architecture_export --live" in RUN_TEXT
    assert "--output architecture-export.json" in RUN_TEXT
    assert re.search(r'--summary (\S+)[\s\S]*cat \1 >> "\$GITHUB_STEP_SUMMARY"', RUN_TEXT), RUN_TEXT
    gcloud = next(s for s in STEPS if str(s.get("uses", "")).startswith("google-github-actions/setup-gcloud"))
    assert gcloud["with"]["install_components"] == "beta", "domain mappings need the beta surface"


def test_uploads_the_export_as_a_30_day_artifact():
    up = [s for s in STEPS if str(s.get("uses", "")).startswith("actions/upload-artifact")]
    assert len(up) == 1
    w = up[0]["with"]
    assert w["name"] == "architecture-export"
    assert w["path"] == "architecture-export.json"
    assert int(w["retention-days"]) == 30
    assert w.get("if-no-files-found") == "error"


def test_has_a_timeout():
    for job in DOC["jobs"].values():
        assert 0 < int(job["timeout-minutes"]) <= 30
