"""EW-only DEP contract controls against real committed repositories and CLIs.

The approved own-scope spec on the implementation base seeds disposable fixture
repositories. No deployment shell or cloud CLI executes.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = "docs/superpowers/specs/2026-11-09-feat-deploy-001-retire-ew-bindings-own-scope.md"
PLAN = "docs/superpowers/plans/2026-11-09-feat-deploy-001-ew-bindings-fixture.md"
BRANCH = "fix/feat-deploy-001-ew-bindings-fixture"
FEAT = "FEAT-DEPLOY-001"
SITE = "docs/product/03-SITE-TRACEABILITY.md"
RECORD = "docs/review-evidence/site-source-snapshot.json"
REGISTRY = "docs/DOC_REGISTRY.md"
MODULE = "scripts/maintenance/doc_source_snapshot.py"
GATE = "scripts/gate/spec_gate.py"


@pytest.fixture
def fixture_tools():
    spec = importlib.util.spec_from_file_location(
        "ew_identity_fixture_helpers", ROOT / "tests/scripts/test_doc_source_snapshot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ew_repo(tmp_path, fixture_tools):
    """Install actual policy then add exact DEP contract to fixture main."""
    repo = fixture_tools.installed_repo(tmp_path / "repo")
    repo.git("checkout", "-q", "main")
    spec_path = ROOT / SPEC
    raw = spec_path.read_text()
    assert "feat_id: FEAT-DEPLOY-001\n" in raw
    assert "site_source_notes: [SHARED-07]\n" in raw
    assert "status: approved\n" in raw
    repo.write(SPEC, raw)
    repo.write(SITE, (repo.path / SITE).read_text().replace("SHARED-01", "SHARED-07"))
    catalog = "docs/product/02-FEATURE-CATALOG.md"
    repo.write(catalog, (repo.path / catalog).read_text().replace("| FEAT-CICD-001 | CI |", "| FEAT-CICD-001 | CI |\n| FEAT-DEPLOY-001 | Deployment |") +
               "\n### FEAT-DEPLOY-001\n\n| Field | Value |\n|---|---|\n"
               "| Status | Fixture source review |\n| Last reviewed | " + fixture_tools.DAY + " |\n")
    requirements = "docs/product/01-PRODUCT-REQUIREMENTS.md"
    repo.write(requirements, (repo.path / requirements).read_text() +
               "\n**REQ-SECRET-001:** Retain secret resources.\n"
               "**REQ-DEPLOY-001:** Scoped deployment.\n"
               "**REQ-GOV-004:** Committed document identity.\n")
    repo.write("gcp/deploy.sh", "#!/bin/bash\n# Calendar fixture before EW binding retirement.\n")
    repo.base = repo.commit("docs: seed exact approved DEP contract on fixture main")
    repo.git("update-ref", "refs/remotes/origin/main", repo.base)
    repo.git("checkout", "-q", "-b", BRANCH)
    repo.write(PLAN, "---\nfeat_id: FEAT-DEPLOY-001\nspec: " + SPEC +
               "\nbranch: " + BRANCH + "\npr: 7\nstatus: ready\n---\n\n"
               "# Disposable EW fixture plan\n\n## Task 1: Own-note control\n"
               "Spec: Design, done_when item 8.\n"
               "- [ ] Exercise actual producer, verifier, audit and BASE gate.\n")
    repo.write("gcp/deploy.sh", "#!/bin/bash\n# Calendar fixture after EW binding retirement.\n")
    repo.commit("feat: change calendar fixture source without executing it")
    return repo


def gate(repo):
    """Use immutable BASE gate bytes, not the proposed working-tree gate."""
    script = repo.git("show", "origin/main:" + GATE).stdout
    trusted = repo.path / GATE
    assert trusted.read_text() == script, "fixture must execute unchanged trusted BASE gate bytes"
    spec = repo.git("show", "HEAD:" + SPEC).stdout
    contract = spec.split("done_when:\n", 1)[1].split("\nstatus:", 1)[0]
    items = [line[4:].strip().strip(chr(34)) for line in contract.splitlines() if line.startswith("  - ")]
    body = "Spec: " + SPEC + "\nPlan: " + PLAN + "\n" + "\n".join("- [ ] " + x for x in items)
    body += "\n\n## Capacity\nVolume: 0 rows\nVelocity: 0 requests/min\nWall-clock: 0 seconds\nCost: $0\n"
    env = dict(os.environ, PR_HEAD_REF=BRANCH, PR_BASE_REF="main", PR_DRAFT="true",
               PR_NUMBER="7", PR_TITLE="FEAT-DEPLOY-001: EW own-note fixture", PR_BODY=body)
    return subprocess.run([sys.executable, str(trusted), "--pr", "origin/main", "HEAD"],
                          cwd=repo.path, env=env, text=True, capture_output=True, timeout=30)


def append_note(repo):
    result = repo.cli("produce")
    assert result.returncode != 0, result.stdout + result.stderr
    identity = json.loads(result.stdout)["source_identity_sha256"]
    assert len(identity) == 64
    repo.write(SITE, (repo.path / SITE).read_text() +
               "\n## Implementation-source notes\n\n"
               "| FEAT | Component | Backend source and tests (implementation only; rollout pending) |\n"
               "|---|---|---|\n| FEAT-DEPLOY-001 | SHARED-07 | source_identity_sha256=" +
               identity + "; EW calendar binding source and local CLI tests; rollout pending |\n")
    repo.commit("docs: bind DEP SHARED-07 note to actual source")


@pytest.fixture
def bound(ew_repo):
    append_note(ew_repo)
    ew_repo.produce_committed()
    return ew_repo


def accepted(repo):
    verified = repo.cli("verify")
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert json.loads(verified.stdout)["eligible_route"] == "declared-note"
    audited = repo.audit()
    assert audited.returncode in (0, 1), audited.stdout + audited.stderr
    report = json.loads(audited.stdout)
    assert report["source_identities"][SITE]["eligible_route"] == "declared-note"
    assert not any(x["doc"] == SITE and x["check"] in ("source-provenance", "changed-since")
                   for x in report["findings"])


def refused(repo, *, require_gate=True, require_producer=True, registry_type=False):
    result = repo.cli("verify")
    assert result.returncode != 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "unverified"
    if require_producer:
        produced = repo.cli("produce")
        assert produced.returncode != 0, produced.stdout + produced.stderr
    audited = repo.audit()
    if registry_type:
        assert audited.returncode != 0, audited.stdout + audited.stderr
        assert "registry" in audited.stderr.lower(), audited.stderr
    else:
        report = json.loads(audited.stdout)
        assert any(x["doc"] == SITE and x["check"] == "source-provenance" for x in report["findings"])
    if require_gate:
        checked = gate(repo)
        assert checked.returncode != 0, checked.stdout + checked.stderr


def test_ordinary_own_note(bound):
    accepted(bound)
    result = gate(bound)
    assert result.returncode == 0, result.stdout + result.stderr


def squash(repo):
    repo.git("checkout", "-q", "main")
    repo.git("merge", "--squash", BRANCH)
    landed = repo.commit("feat: actual squash of DEP note and source")
    repo.git("update-ref", "refs/remotes/origin/main", landed)
    return landed


def test_squash(bound):
    squash(bound)
    accepted(bound)


def test_fresh_clone(bound, tmp_path):
    old_head = bound.git("rev-parse", "HEAD").stdout.strip()
    squash(bound)
    bound.git("branch", "-D", BRANCH)
    fresh = tmp_path / "fresh"
    subprocess.run(["git", "clone", "--no-local", "--single-branch", "--branch", "main",
                    str(bound.path), str(fresh)], check=True, capture_output=True)
    assert subprocess.run(["git", "cat-file", "-e", old_head], cwd=fresh,
                          capture_output=True).returncode != 0
    result = subprocess.run([sys.executable, MODULE, "verify"], cwd=fresh,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["eligible_route"] == "declared-note"


def test_terminal_current_trunk_without_sidecar(bound):
    squash(bound)
    bound.git("checkout", "-q", "-b", "docs/ew-terminal")
    stamped = bound.audit("--stamp", "--verify", SITE)
    assert stamped.returncode in (0, 1), stamped.stdout + stamped.stderr
    assert any(row["doc"] == SITE and row["action"] in ("updated", "unchanged")
               for row in json.loads(stamped.stdout)["stamped"])
    (bound.path / RECORD).unlink()
    bound.commit("docs: lawful terminal trunk stamp and sidecar retirement")
    result = bound.cli("verify")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["eligible_route"] == "terminal-ordinary"
    report = json.loads(bound.audit().stdout)
    assert SITE not in report["source_identities"]
    assert not any(x["doc"] == SITE and x["check"] in ("source-provenance", "changed-since")
                   for x in report["findings"])


def test_wrong_primary(bound):
    bound.git("checkout", "-q", "-b", "fix/feat-data-001-wrong-primary")
    plan = (bound.path / PLAN).read_text().replace(BRANCH, "fix/feat-data-001-wrong-primary")
    bound.write(PLAN, plan)
    bound.commit("feat: wrong primary")
    refused(bound)


def test_wrong_feat(bound):
    bound.write(PLAN, (bound.path / PLAN).read_text().replace("feat_id: FEAT-DEPLOY-001", "feat_id: FEAT-CICD-001"))
    bound.commit("feat: wrong FEAT")
    refused(bound)


def test_wrong_spec(bound):
    bound.write(SPEC, (bound.path / SPEC).read_text().replace("status: approved", "status: draft"))
    bound.commit("docs: source spec differs from approved policy")
    refused(bound)


def test_stale(bound):
    bound.git("checkout", "-q", "main")
    bound.write("gcp/new-main.py", "VALUE = 'new main'\n")
    head = bound.commit("feat: main advances independently")
    bound.git("update-ref", "refs/remotes/origin/main", head)
    bound.git("checkout", "-q", BRANCH)
    refused(bound, require_producer=False, require_gate=False)
    # PR gate uses the committed merge base; current-main freshness is verifier/audit-owned.
    assert gate(bound).returncode == 0


def test_dirty(bound):
    bound.write(SITE, (bound.path / SITE).read_text() + "\nDirty body.\n")
    refused(bound, require_gate=False)
    # PR-mode gate judges committed input; producer/verifier/audit reject dirty SITE.
    assert gate(bound).returncode == 0


def test_body(bound):
    bound.write(SITE, (bound.path / SITE).read_text().replace("API service", "Altered frontend evidence"))
    bound.commit("docs: altered non-owned body")
    refused(bound)


def test_source(bound):
    bound.write("gcp/deploy.sh", "#!/bin/bash\n# New source after record.\n")
    bound.commit("feat: stale source identity")
    refused(bound)


def test_missing_note(bound):
    bound.write(SITE, (bound.path / SITE).read_text().split("\n## Implementation-source notes")[0])
    bound.commit("docs: remove required note")
    refused(bound)


def test_unchanged_note(bound):
    landed = squash(bound)
    bound.git("checkout", "-q", BRANCH)
    bound.git("reset", "--hard", landed)
    bound.write("gcp/deploy.sh", "#!/bin/bash\n# New code without new note.\n")
    bound.commit("feat: unchanged note cannot authorize new source")
    refused(bound)


def test_wrong_source_note(bound):
    record = json.loads((bound.path / RECORD).read_text())
    bound.write(SITE, (bound.path / SITE).read_text().replace(record["source_identity_sha256"], "0" * 64))
    bound.commit("docs: wrong source identity in own note")
    refused(bound)


def test_bootstrap_reuse(ew_repo):
    # Installed verifier on fixture main forbids bootstrap even if the note is absent.
    refused(ew_repo)


def test_registry_blob(bound):
    bound.write(REGISTRY, (bound.path / REGISTRY).read_text() + "\nChanged registry bytes.\n")
    bound.commit("docs: source registry blob differs from policy")
    refused(bound)


def test_registry_mode(bound):
    (bound.path / REGISTRY).chmod(0o755)
    bound.commit("docs: source registry mode differs from policy")
    refused(bound)


def test_registry_type(bound):
    (bound.path / REGISTRY).unlink()
    (bound.path / REGISTRY).symlink_to("product/03-SITE-TRACEABILITY.md")
    bound.commit("docs: source registry type differs from policy")
    refused(bound, registry_type=True)


def test_code_masquerading_as_doc(bound):
    bound.git("checkout", "-q", "-b", "docs/ew-false-closeout")
    bound.write("gcp/deploy.sh", "#!/bin/bash\n# CODE in purported DOC closeout.\n")
    bound.commit("docs: CODE cannot become DOC closeout")
    refused(bound)


def test_premature_retirement(bound):
    (bound.path / RECORD).unlink()
    bound.commit("docs: remove record before main closeout")
    result = bound.cli("verify")
    assert result.returncode != 0, result.stdout + result.stderr
    report = json.loads(bound.audit().stdout)
    assert any(x["doc"] == SITE and x["check"] == "source-provenance" for x in report["findings"])
    # BASE scope gate does not replace committed-record verifier/audit acceptance.
    result = gate(bound)
    assert result.returncode == 0, result.stdout + result.stderr
