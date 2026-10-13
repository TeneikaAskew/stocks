"""Real committed-repository CLI controls for source documentation identity."""
from __future__ import annotations

import datetime
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = "scripts/maintenance/doc_source_snapshot.py"
AUDIT = "scripts/maintenance/docs_audit.py"
GATE = "scripts/gate/spec_gate.py"
SITE = "docs/product/03-SITE-TRACEABILITY.md"
REGISTRY = "docs/DOC_REGISTRY.md"
RECORD = "docs/review-evidence/site-source-snapshot.json"
SPEC = "docs/superpowers/specs/2026-10-13-feat-cicd-001-source-review-verifier.md"
PLAN = "docs/superpowers/plans/2026-10-13-feat-cicd-001-source-review-verifier.md"
BRANCH = "feature/feat-cicd-001-source-review-verifier"
DAY = datetime.date.today().isoformat()


class Repo:
    def __init__(self, path: Path, object_format: str = "sha1"):
        self.path = path
        self.path.mkdir()
        self.git("init", "-q", "-b", "main", f"--object-format={object_format}")
        self.git("config", "user.name", "Source identity tests")
        self.git("config", "user.email", "source-tests@example.invalid")
        for file in (AUDIT, GATE):
            self.write(file, (ROOT / file).read_bytes())
        self.write("scripts/__init__.py", b"")
        self.write("scripts/maintenance/__init__.py", b"")
        self.write("lib/input.py", b"VALUE = 1\n")
        self.write("tests/source_input.py", b"INPUT = 'native'\n")
        self.write(SPEC, (ROOT / SPEC).read_bytes())
        self.write("docs/product/02-FEATURE-CATALOG.md", "# Catalog\n\n| ID | Area |\n|---|---|\n| FEAT-CICD-001 | CI |\n\n### FEAT-CICD-001\n\n| Field | Value |\n|---|---|\n| Status | Source identity tests |\n| Last reviewed | " + DAY + " |\n")
        self.write("docs/product/01-PRODUCT-REQUIREMENTS.md", "# Requirements\n\n**REQ-GOV-001:** Conversations resolve.\n\n**REQ-REVIEW-001:** Authentic CODE review.\n")
        self.write("docs/product/12-PR-ISSUE-TRACEABILITY.md", "# Traceability\n\n### FEAT-CICD-001\n\n**PR lineage:** #1\n")
        self.write(REGISTRY, "# Documentation registry\n\n## Registry\n\n| Class | Path glob | Declared code paths | Generated regions |\n|---|---|---|---|\n| D | " + SITE + " | lib, scripts, tests | |\n| C | docs/product/* | | |\n| C | docs/superpowers/** | | |\n| C | docs/DOC_REGISTRY.md | | |\n")
        self.body = "# Site traceability\n\n### Chain\n\n| Element | Backend source | Evidence |\n|---|---|---|\n| SHARED-01 | API service | Local source tests |\n"
        self.write(SITE, self.body)
        seed = self.commit("docs: seed genuine trunk source and body")
        marker = f"**Last reviewed:** {DAY} · **Depth:** verified · **Against:** `{seed[:12]}` · **Last scanned:** {DAY} · **Owner:** Source tests\n"
        self.write(SITE, self.body.replace("\n\n", "\n\n" + marker + "\n", 1))
        self.base = self.commit("docs: record actual trunk marker")
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        self.git("checkout", "-q", "-b", BRANCH)
        plan = (ROOT / PLAN).read_text().replace("pr: 1470", "pr: 7")
        self.write(PLAN, plan)
        if (ROOT / MODULE).exists():
            self.write(MODULE, (ROOT / MODULE).read_bytes())
        self.commit("feat: introduce scoped verifier source")

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=self.path, capture_output=True,
                              text=True, check=check)

    def write(self, path: str, value: bytes | str):
        file = self.path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(value.encode("utf-8") if isinstance(value, str) else value)

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD").stdout.strip()

    def cli(self, action: str, *extra: str) -> subprocess.CompletedProcess:
        args = [sys.executable, MODULE, action, "--policy-ref", "origin/main", "--source-ref", "HEAD"]
        args += ["--output", RECORD] if action == "produce" else ["--record", RECORD]
        return subprocess.run(args + list(extra), cwd=self.path, capture_output=True,
                              text=True, timeout=10)

    def produce_committed(self) -> dict:
        result = self.cli("produce")
        assert result.returncode == 0, result.stdout + result.stderr
        value = json.loads(result.stdout)
        assert value["status"] == "identity-matched"
        self.commit("docs: bind actual committed source identity")
        return value

    def audit(self, *extra):
        snapshot = self.path / "issue-state.json"
        snapshot.write_text(json.dumps({"capturedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                        "stocks": {"1": {"state": "open", "kind": "PR"}},
                                        "solyra": {"1": {"state": "open", "kind": "PR"}}}))
        return subprocess.run([sys.executable, AUDIT, "--json", "--no-owning-job-check", "--issues-snapshot", str(snapshot), *extra],
                              cwd=self.path, capture_output=True, text=True, timeout=20)

    def gate(self, head="HEAD"):
        fm_text = self.git("show", head + ":" + PLAN).stdout
        spec_path = next(line.split(": ", 1)[1] for line in fm_text.splitlines() if line.startswith("spec: "))
        spec_text = self.git("show", head + ":" + spec_path).stdout
        done = []
        collecting = False
        for line in spec_text.splitlines():
            if line == "done_when:":
                collecting = True
            elif collecting and line.startswith("  - "):
                done.append(json.loads(line[4:]))
            elif collecting:
                break
        body = f"Spec: {spec_path}\nPlan: {PLAN}\n\n" + "\n".join("- [ ] " + item for item in done)
        env = dict(os.environ, PR_HEAD_REF=BRANCH, PR_BASE_REF="main", PR_DRAFT="true", PR_NUMBER="7",
                   PR_TITLE="FEAT-CICD-001: actual source note controls", PR_BODY=body)
        return subprocess.run([sys.executable, GATE, "--pr", "origin/main", head], cwd=self.path,
                              env=env, capture_output=True, text=True, timeout=20)


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_actual_bootstrap_producer_and_committed_verifier(object_format, tmp_path):
    """Missing production CLI or an unchecked authored verdict fails this control."""
    repo = Repo(tmp_path / "repo", object_format)
    produced = repo.produce_committed()
    record = json.loads((repo.path / RECORD).read_text())
    assert record["object_format"] == object_format
    assert record["eligibility"]["kind"] == "initial-bootstrap"
    assert record["baseline"]["main_commit_oid"] == repo.base
    verified = repo.cli("verify")
    assert verified.returncode == 0, verified.stdout + verified.stderr
    verdict = json.loads(verified.stdout)
    assert verdict["status"] == "identity-matched"
    assert verdict["source_identity_sha256"] == produced["source_identity_sha256"]
    assert verdict["entry_count"] > 0
    assert verdict["counted_bytes"] > 0
    assert verdict["elapsed_seconds"] < 5
    assert "authenticated" not in verdict.get("context", "")
    assert "rollout pending" in verdict["context"]


def test_actual_committed_source_mutation_refuses_old_record(tmp_path):
    repo = Repo(tmp_path / "repo")
    repo.produce_committed()
    repo.write("lib/input.py", "VALUE = 2\n")
    repo.commit("feat: change watched source after production")
    result = repo.cli("verify")
    assert result.returncode != 0
    assert json.loads(result.stdout)["status"] == "unverified"


@pytest.mark.parametrize("mutation", ["baseline-list", "bool-size", "unknown-nested", "duplicate", "escape", "wrong-width", "version", "float", "extra-json"])
@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_actual_record_schema_corruption_is_explicit_unverified(mutation, object_format, tmp_path):
    repo = Repo(tmp_path / "repo", object_format)
    repo.produce_committed()
    record = json.loads((repo.path / RECORD).read_text())
    if mutation == "baseline-list":
        record["baseline"] = []
    elif mutation == "bool-size":
        record["source_entries"][0]["size_bytes"] = True
    elif mutation == "unknown-nested":
        record["eligibility"]["approved"] = True
    elif mutation == "wrong-width":
        record["baseline"]["main_commit_oid"] = "a" * (64 if object_format == "sha1" else 40)
    elif mutation == "version":
        record["version"] = 2
    elif mutation == "float":
        record["source_entries"][0]["size_bytes"] = 0.5
    raw = (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if mutation == "duplicate":
        raw = raw.replace(b'{"baseline":', b'{"version":1,"baseline":', 1)
    elif mutation == "escape":
        raw = raw.replace(b"docs/", b"docs\\/", 1)
    elif mutation == "extra-json":
        raw += b"{}\n"
    repo.write(RECORD, raw)
    repo.commit("docs: corrupt authored record")
    result = repo.cli("verify")
    assert result.returncode != 0
    assert json.loads(result.stdout)["status"] == "unverified", result.stderr
    assert "Traceback" not in result.stderr
    if mutation in ("version", "float", "extra-json"):
        report = json.loads(repo.audit().stdout)
        assert SITE not in report["source_identities"]
        assert any(f["doc"] == SITE and f["check"] == "source-provenance" for f in report["findings"])
        assert any(f["doc"] == SITE and f["check"] == "changed-since" for f in report["findings"])


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("limit", [("--max-input-bytes", "100"), ("--max-seconds", "0.00001"), ("--max-entries", "1"), ("--max-seconds", "6")])
def test_actual_failed_production_preserves_absent_or_valid_output(existing, limit, tmp_path):
    repo = Repo(tmp_path / "repo")
    if existing:
        repo.produce_committed()
    original = (repo.path / RECORD).read_bytes() if existing else None
    result = repo.cli("produce", *limit)
    assert result.returncode != 0
    assert json.loads(result.stdout)["status"] == "unverified"
    if existing:
        assert (repo.path / RECORD).read_bytes() == original
    else:
        assert not (repo.path / RECORD).exists()


NOTE_SPEC = "docs/superpowers/specs/2026-10-13-feat-cicd-001-test-source-notes.md"


def installed_repo(path, object_format="sha1", declaration="[SHARED-01]", unicode_path=False, unrelated_finding=False):
    repo = Repo(path, object_format)
    repo.git("checkout", "-q", "main")
    repo.write(MODULE, (ROOT / MODULE).read_bytes())
    spec = (ROOT / SPEC).read_text().replace("status: approved", "site_source_notes: " + declaration + "\nstatus: approved")
    repo.write(NOTE_SPEC, spec)
    if unicode_path:
        repo.write("scripts/café.py", "LOCAL = 'literal UTF-8'\n")
    if unrelated_finding:
        repo.write(SITE, (repo.path / SITE).read_text() + "\n[An existing broken citation](../../absent.py)\n")
    repo.base = repo.commit("feat: establish genuine installed verifier and approved note spec")
    repo.git("update-ref", "refs/remotes/origin/main", repo.base)
    repo.git("checkout", "-q", BRANCH)
    repo.git("reset", "--hard", repo.base)
    return repo


def bound_note_repo(path, **kwargs):
    repo = installed_repo(path, **kwargs)
    repo.write(PLAN, (ROOT / PLAN).read_text().replace(SPEC, NOTE_SPEC).replace("pr: 1470", "pr: 7"))
    repo.write("lib/input.py", "VALUE = 2\n")
    repo.commit("feat: change declared backend source")
    preflight = repo.cli("produce")
    assert preflight.returncode != 0
    append_note(repo, json.loads(preflight.stdout)["source_identity_sha256"])
    repo.produce_committed()
    return repo


def append_note(repo, source_hash):
    body = (repo.path / SITE).read_text()
    repo.write(SITE, body + "\n## Implementation-source notes\n\n| FEAT | Component | Backend source and tests (implementation only; rollout pending) |\n|---|---|---|\n| FEAT-CICD-001 | SHARED-01 | source_identity_sha256=" + source_hash + "; local backend source and tests |\n")
    repo.commit("docs: append own actual source-bound note")


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_actual_declared_note_preflight_then_bound_record(object_format, tmp_path):
    repo = installed_repo(tmp_path / "repo", object_format)
    plan = (ROOT / PLAN).read_text().replace(SPEC, NOTE_SPEC).replace("pr: 1470", "pr: 7")
    repo.write(PLAN, plan)
    repo.write("lib/input.py", "VALUE = 2\n")
    repo.commit("feat: change declared local backend source")
    preflight = repo.cli("produce")
    assert preflight.returncode != 0
    identity = json.loads(preflight.stdout)["source_identity_sha256"]
    assert len(identity) == 64
    assert not (repo.path / RECORD).exists()
    append_note(repo, identity)
    repo.produce_committed()
    verified = repo.cli("verify")
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert json.loads(verified.stdout)["eligible_route"] == "declared-note"
    audit = repo.audit()
    assert audit.returncode in (0, 1), audit.stdout + audit.stderr
    audited = json.loads(audit.stdout)
    assert audited["source_identities"][SITE]["eligible_route"] == "declared-note"
    assert not any(f["doc"] == SITE and f["check"] in ("changed-since", "source-provenance") for f in audited["findings"])
    gated = repo.gate()
    assert gated.returncode == 0, gated.stdout + gated.stderr


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_actual_doc_body_closeout_refuses_code_masquerade(object_format, tmp_path):
    repo = installed_repo(tmp_path / "repo", object_format)
    repo.git("checkout", "-q", "-b", "docs/source-closeout")
    repo.write(SITE, (repo.path / SITE).read_text() + "\nGenuine local main body close-out evidence.\n")
    repo.commit("docs: publish body while historical marker stays fixed")
    repo.produce_committed()
    accepted = repo.cli("verify")
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    verdict = json.loads(accepted.stdout)
    assert verdict["eligible_route"] == "trunk-closeout-pending"
    assert "trunk documentation close-out pending" in verdict["context"]
    repo.write("lib/input.py", "VALUE = 3\n")
    repo.commit("feat: attempt code change on purported DOC close-out")
    refused = repo.cli("verify")
    assert refused.returncode != 0
    assert json.loads(refused.stdout)["status"] == "unverified"


@pytest.mark.parametrize("dirty", ["unstaged", "index", "index-restored"])
def test_actual_audit_dirty_site_never_identity_matches(dirty, tmp_path):
    repo = Repo(tmp_path / "repo")
    repo.produce_committed()
    clean = repo.audit()
    assert clean.returncode in (0, 1), clean.stdout + clean.stderr
    assert json.loads(clean.stdout)["source_identities"][SITE]["eligible_route"] == "initial-bootstrap"
    original = (repo.path / SITE).read_bytes()
    repo.write(SITE, original + b"\nUncommitted body drift.\n")
    if dirty != "unstaged":
        repo.git("add", SITE)
    if dirty == "index-restored":
        repo.write(SITE, original)
    result = repo.audit()
    assert result.returncode in (0, 1), result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert SITE not in report["source_identities"]
    assert any(f["doc"] == SITE and f["check"] == "source-provenance" and "dirty SITE" in f["detail"] for f in report["findings"])


def test_actual_missing_promisor_blob_refuses_before_sensitive_local_remote(tmp_path):
    complete = Repo(tmp_path / "complete")
    complete.produce_committed()
    assert complete.cli("verify").returncode == 0
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(complete.path), str(bare)], check=True)
    subprocess.run(["git", "--git-dir", str(bare), "config", "uploadpack.allowFilter", "true"], check=True)
    partial = tmp_path / "partial"
    subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", bare.as_uri(), str(partial)], check=True)
    missing = complete.git("rev-parse", "HEAD:lib/input.py").stdout.strip()
    unavailable = subprocess.run(["git", "--no-lazy-fetch", "cat-file", "-e", missing], cwd=partial, capture_output=True)
    assert unavailable.returncode != 0
    sentinel = tmp_path / "remote-access"
    helper = tmp_path / "local-promisor-helper"
    helper.write_text("#!/usr/bin/env python3\nfrom pathlib import Path\nPath(" + repr(str(sentinel)) + ").write_text('accessed')\nraise SystemExit(55)\n")
    helper.chmod(0o755)
    for args in (("config", "remote.origin.url", "ext::" + str(helper)), ("config", "protocol.ext.allow", "always")):
        subprocess.run(["git", *args], cwd=partial, check=True)
    for path in (MODULE, AUDIT, GATE, SITE):
        destination = partial / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((complete.path / path).read_bytes())
    for command in ([sys.executable, MODULE, "produce"], [sys.executable, MODULE, "verify"],
                    [sys.executable, AUDIT, "--json", "--no-owning-job-check"]):
        result = subprocess.run(command, cwd=partial, capture_output=True, text=True, timeout=10)
        assert result.returncode != 0, result.stdout + result.stderr
        assert "promisor" in result.stdout + result.stderr or "partial-clone" in result.stdout + result.stderr
        assert not sentinel.exists()
    env = {key: value for key, value in os.environ.items() if key not in ("GIT_NO_LAZY_FETCH", "GIT_NO_REPLACE_OBJECTS")}
    detection = subprocess.run(["git", "cat-file", "-p", missing], cwd=partial, env=env, capture_output=True, timeout=10)
    assert detection.returncode != 0
    assert sentinel.read_text() == "accessed", detection.stderr


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_actual_bootstrap_squash_fresh_clone_and_reuse_refusal(object_format, tmp_path):
    repo = Repo(tmp_path / "repo", object_format)
    repo.produce_committed()
    feature = repo.git("rev-parse", "HEAD").stdout.strip()
    repo.git("checkout", "-q", "main")
    repo.git("merge", "--squash", BRANCH)
    landed = repo.commit("feat: actual squash publication of bootstrap")
    repo.git("update-ref", "refs/remotes/origin/main", landed)
    repo.git("branch", "-D", BRANCH)
    fresh = tmp_path / "fresh"
    subprocess.run(["git", "clone", "-q", "--single-branch", "--branch", "main", "--no-local", str(repo.path), str(fresh)], check=True)
    assert subprocess.run(["git", "--no-lazy-fetch", "cat-file", "-e", feature], cwd=fresh, capture_output=True).returncode != 0
    verified = subprocess.run([sys.executable, MODULE, "verify"], cwd=fresh, capture_output=True, text=True, timeout=10)
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert json.loads(verified.stdout)["eligible_route"] == "initial-bootstrap"
    subprocess.run(["git", "checkout", "-q", "-b", BRANCH], cwd=fresh, check=True)
    subprocess.run(["git", "config", "user.name", "Source tests"], cwd=fresh, check=True)
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=fresh, check=True)
    (fresh / "lib/input.py").write_text("VALUE = 99\n")
    subprocess.run(["git", "add", "lib/input.py"], cwd=fresh, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat: future source cannot reuse bootstrap"], cwd=fresh, check=True)
    refused = subprocess.run([sys.executable, MODULE, "verify"], cwd=fresh, capture_output=True, text=True, timeout=10)
    assert refused.returncode != 0
    assert json.loads(refused.stdout)["status"] == "unverified"


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_actual_doc_body_squash_then_trunk_stamp_and_retirement(object_format, tmp_path):
    repo = installed_repo(tmp_path / "repo", object_format)
    repo.git("checkout", "-q", "-b", "docs/source-closeout")
    repo.write(SITE, (repo.path / SITE).read_text() + "\nGenuine local main body close-out evidence.\n")
    repo.commit("docs: commit body containing genuine main evidence")
    repo.produce_committed()
    repo.git("checkout", "-q", "main")
    repo.git("merge", "--squash", "docs/source-closeout")
    landed = repo.commit("docs: squash actual body-first close-out")
    repo.git("update-ref", "refs/remotes/origin/main", landed)
    accepted = repo.cli("verify")
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert json.loads(accepted.stdout)["eligible_route"] == "trunk-closeout-pending"
    repo.git("checkout", "-q", "-b", "docs/source-terminal")
    # Existing ordinary trunk-only stamp, no protocol flag or marker fabrication.
    stamped = repo.audit("--stamp", "--verify", SITE)
    assert stamped.returncode in (0, 1), stamped.stdout + stamped.stderr
    assert any(row["doc"] == SITE and row["action"] in ("updated", "unchanged") for row in json.loads(stamped.stdout)["stamped"])
    (repo.path / RECORD).unlink()
    repo.commit("docs: genuine current-trunk marker and sidecar retirement")
    terminal = repo.cli("verify")
    assert terminal.returncode == 0, terminal.stdout + terminal.stderr
    assert json.loads(terminal.stdout)["eligible_route"] == "terminal-ordinary"
    report = json.loads(repo.audit().stdout)
    assert SITE not in report["source_identities"]
    assert not any(f["doc"] == SITE and f["check"] in ("changed-since", "source-provenance") for f in report["findings"])
    repo.write(SITE, (repo.path / SITE).read_text() + "\nBody drift after retirement.\n")
    repo.commit("docs: change body after stamp")
    broken = repo.audit()
    assert any(f["doc"] == SITE and f["check"] == "source-provenance" for f in json.loads(broken.stdout)["findings"])


@pytest.mark.parametrize("mutation", ["foreign-row", "frontend", "marker", "header", "duplicate-heading", "duplicate-row", "undeclared", "wrong-hash", "unchanged", "remove-only"])
def test_actual_producer_and_gate_refuse_note_boundary_mutations(mutation, tmp_path):
    repo = bound_note_repo(tmp_path / "repo")
    assert repo.cli("verify").returncode == 0
    assert repo.gate().returncode == 0
    body = (repo.path / SITE).read_text()
    own_row = body.splitlines()[-1]
    if mutation == "foreign-row":
        body += "| FEAT-DATA-001 | SHARED-01 | foreign backend claim |\n"
    elif mutation == "frontend":
        body = body.replace("API service", "Deployed frontend changed")
    elif mutation == "marker":
        body = body.replace("**Owner:** Source tests", "**Owner:** altered")
    elif mutation == "header":
        body = body.replace("Backend source and tests", "Verified deployment")
    elif mutation == "duplicate-heading":
        body += "\n## Implementation-source notes\n"
    elif mutation == "duplicate-row":
        body += own_row + "\n"
    elif mutation == "undeclared":
        body = body.replace("| FEAT-CICD-001 | SHARED-01 | source_", "| FEAT-CICD-001 | SHARED-99 | source_")
    elif mutation == "wrong-hash":
        record = json.loads((repo.path / RECORD).read_text())
        body = body.replace(record["source_identity_sha256"], "0" * 64)
    elif mutation == "unchanged":
        repo.git("checkout", "-q", "main")
        repo.git("merge", "--squash", BRANCH)
        repo.base = repo.commit("feat: actual land of note before future change")
        repo.git("update-ref", "refs/remotes/origin/main", repo.base)
        repo.git("checkout", "-q", BRANCH)
        repo.git("reset", "--hard", repo.base)
        repo.write("lib/input.py", "VALUE = 3\n")
    else:
        body = body[:body.index("\n## Implementation-source notes")]
    repo.write(SITE, body)
    repo.commit("feat: committed refused note boundary")
    result = repo.cli("produce")
    assert result.returncode != 0
    assert json.loads(result.stdout)["status"] == "unverified"
    gated = repo.gate()
    assert gated.returncode != 0, gated.stdout + gated.stderr


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_actual_literal_utf8_manifest_and_alternative_escape_refusal(object_format, tmp_path):
    repo = bound_note_repo(tmp_path / "repo", object_format=object_format, unicode_path=True)
    raw = (repo.path / RECORD).read_bytes()
    assert "scripts/café.py".encode() in raw
    assert repo.cli("verify").returncode == 0
    repo.write(RECORD, raw.replace("café".encode(), b"caf\\u00e9"))
    repo.commit("docs: alternate Unicode escape is not canonical")
    refused = repo.cli("verify")
    assert refused.returncode != 0
    assert "canonical" in json.loads(refused.stdout)["reason"]


def test_actual_base_gate_does_not_import_benign_source_initializer(tmp_path):
    repo = bound_note_repo(tmp_path / "repo")
    sentinel = tmp_path / "initializer-ran"
    repo.write("scripts/__init__.py", "from pathlib import Path\nPath(" + repr(str(sentinel)) + ").write_text('executed')\n")
    repo.commit("feat: benign initializer belongs only to proposed tree")
    identity = json.loads(repo.cli("produce").stdout)["source_identity_sha256"]
    body = (repo.path / SITE).read_text()
    old = json.loads((repo.path / RECORD).read_text())["source_identity_sha256"]
    repo.write(SITE, body.replace(old, identity))
    repo.commit("docs: bind changed initializer identity without executing it")
    repo.produce_committed()
    head = repo.git("rev-parse", "HEAD").stdout.strip()
    repo.git("checkout", "-q", "main")
    result = repo.gate(head)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not sentinel.exists()


def test_actual_identity_keeps_unrelated_audit_finding(tmp_path):
    repo = bound_note_repo(tmp_path / "repo", unrelated_finding=True)
    report = json.loads(repo.audit().stdout)
    assert report["source_identities"][SITE]["eligible_route"] == "declared-note"
    assert "external CODE review under existing rules" in report["source_identities"][SITE]["context"]
    assert any(f["doc"] == SITE and f["check"] == "dead-link" for f in report["findings"])


@pytest.mark.parametrize("kind", ["new-path", "delete", "rename", "executable", "symlink", "missing-blob", "registry-content", "registry-mode", "registry-symlink", "registry-delete", "replace", "graft", "shallow", "bad-source-ref", "bad-policy-ref"])
def test_actual_tree_policy_and_git_state_mutations_refuse(kind, tmp_path):
    repo = Repo(tmp_path / "repo")
    repo.produce_committed()
    if kind == "new-path":
        repo.write("lib/new-descendant/input.py", "NEW = 1\n")
    elif kind == "delete":
        (repo.path / "lib/input.py").unlink()
    elif kind == "rename":
        repo.git("mv", "lib/input.py", "lib/renamed.py")
    elif kind == "executable":
        (repo.path / "lib/input.py").chmod(0o755)
    elif kind == "symlink":
        (repo.path / "lib/input.py").unlink()
        (repo.path / "lib/input.py").symlink_to("../tests/source_input.py")
    elif kind == "missing-blob":
        oid = repo.git("rev-parse", "HEAD:lib/input.py").stdout.strip()
        (repo.path / ".git/objects" / oid[:2] / oid[2:]).unlink()
    elif kind == "registry-content":
        repo.write(REGISTRY, (repo.path / REGISTRY).read_text().replace("lib, scripts, tests", "scripts, tests"))
    elif kind == "registry-mode":
        (repo.path / REGISTRY).chmod(0o755)
    elif kind == "registry-symlink":
        (repo.path / REGISTRY).unlink()
        (repo.path / REGISTRY).symlink_to("product/03-SITE-TRACEABILITY.md")
    elif kind == "registry-delete":
        (repo.path / REGISTRY).unlink()
    elif kind == "replace":
        repo.git("replace", "HEAD", repo.base)
    elif kind == "graft":
        repo.write(".git/info/grafts", repo.base + "\n")
    elif kind == "shallow":
        repo.write(".git/shallow", repo.git("rev-parse", "HEAD").stdout)
    if kind in {"new-path", "delete", "rename", "executable", "symlink", "registry-content", "registry-mode", "registry-symlink", "registry-delete"}:
        repo.commit("feat: committed refused source or policy mutation")
    extra = ("--source-ref", "missing-source") if kind == "bad-source-ref" else ("--policy-ref", "missing-policy") if kind == "bad-policy-ref" else ()
    result = repo.cli("verify", *extra)
    assert result.returncode != 0
    value = json.loads(result.stdout)
    assert value["status"] == "unverified"
    assert value["eligible_route"] is None


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure", ["nonzero", "partial", "slow"])
def test_actual_git_failure_and_timeout_preserve_output_and_reap_children(existing, failure, tmp_path):
    repo = Repo(tmp_path / "repo")
    if existing:
        repo.produce_committed()
    old = (repo.path / RECORD).read_bytes() if existing else None
    real_git = shutil.which("git")
    wrappers = tmp_path / "wrappers"
    wrappers.mkdir()
    sentinel = tmp_path / "late-child-effect"
    wrapper = wrappers / "git"
    if failure == "slow":
        code = "import subprocess, time\nsubprocess.Popen([sys.executable, '-c', " + repr("import time; from pathlib import Path; time.sleep(0.4); Path(" + repr(str(sentinel)) + ").write_text('survived')") + "])\ntime.sleep(60)\n"
    else:
        code = "if 'ls-tree' in sys.argv:\n    " + ("print('100644 blob incomplete\\tlib/input.py', flush=True)\n    " if failure == "partial" else "") + "raise SystemExit(77)\n"
    wrapper.write_text("#!/usr/bin/env python3\nimport os,sys\n" + code + "os.execv(" + repr(real_git) + ", [" + repr(real_git) + "] + sys.argv[1:])\n")
    wrapper.chmod(0o755)
    env = dict(os.environ, PATH=str(wrappers) + os.pathsep + os.environ["PATH"])
    args = [sys.executable, MODULE, "produce"] + (["--max-seconds", "0.1"] if failure == "slow" else [])
    result = subprocess.run(args, cwd=repo.path, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert json.loads(result.stdout)["status"] == "unverified"
    if existing:
        assert (repo.path / RECORD).read_bytes() == old
    else:
        assert not (repo.path / RECORD).exists()
    if failure == "slow":
        time.sleep(0.5)
        assert not sentinel.exists()


@pytest.mark.parametrize("declaration", ["[]", "null", "[SHARED-99]", "[SHARED-01, SHARED-01]"])
def test_actual_no_or_malformed_declaration_cannot_clear_code_drift(declaration, tmp_path):
    repo = installed_repo(tmp_path / "repo", declaration=declaration)
    repo.write(PLAN, (ROOT / PLAN).read_text().replace(SPEC, NOTE_SPEC).replace("pr: 1470", "pr: 7"))
    repo.write("lib/input.py", "VALUE = 4\n")
    repo.commit("feat: code with no eligible own declaration")
    result = repo.cli("produce")
    assert result.returncode != 0
    assert not (repo.path / RECORD).exists()
    report = json.loads(repo.audit().stdout)
    assert SITE not in report["source_identities"]
    assert any(f["doc"] == SITE and f["check"] == "changed-since" for f in report["findings"])
    assert any(f["doc"] == SITE and f["check"] == "source-provenance" for f in report["findings"])


def test_actual_premature_record_retirement_keeps_original_drift(tmp_path):
    repo = Repo(tmp_path / "repo")
    repo.produce_committed()
    (repo.path / RECORD).unlink()
    repo.commit("docs: premature removal without actual trunk stamp")
    refused = repo.cli("verify")
    assert refused.returncode != 0
    report = json.loads(repo.audit().stdout)
    assert SITE not in report["source_identities"]
    assert any(f["doc"] == SITE and f["check"] == "changed-since" for f in report["findings"])
    assert any(f["doc"] == SITE and f["check"] == "source-provenance" for f in report["findings"])


@pytest.mark.parametrize("input_path", [REGISTRY, SPEC])
def test_actual_oversized_trusted_policy_inputs_refuse_before_content_read(input_path, tmp_path):
    repo = Repo(tmp_path / "repo")
    repo.git("checkout", "-q", "main")
    repo.write(input_path, (repo.path / input_path).read_bytes() + b"\n<!-- " + b"x" * 8388608 + b" -->\n")
    repo.base = repo.commit("docs: real oversized trusted policy fixture")
    repo.git("update-ref", "refs/remotes/origin/main", repo.base)
    repo.git("checkout", "-q", BRANCH)
    repo.git("reset", "--hard", repo.base)
    repo.write(MODULE, (ROOT / MODULE).read_bytes())
    repo.write(PLAN, (ROOT / PLAN).read_text().replace("pr: 1470", "pr: 7"))
    repo.commit("feat: exact bootstrap against oversized real policy")
    result = repo.cli("produce")
    assert result.returncode != 0
    verdict = json.loads(result.stdout)
    assert "remaining input-byte" in verdict["reason"]
    assert verdict["counted_bytes"] < 8388608
    assert not (repo.path / RECORD).exists()


def test_actual_oversized_selected_plan_and_record_refuse(tmp_path):
    repo = bound_note_repo(tmp_path / "repo")
    old = (repo.path / RECORD).read_bytes()
    repo.write(PLAN, (repo.path / PLAN).read_bytes() + b"\n<!-- " + b"x" * 8388608 + b" -->\n")
    repo.commit("docs: actual oversized selected committed plan")
    refused = repo.cli("produce")
    assert refused.returncode != 0
    assert "remaining input-byte" in json.loads(refused.stdout)["reason"]
    assert (repo.path / RECORD).read_bytes() == old
    repo.write(RECORD, old + b" " * 8388608)
    repo.commit("docs: actual oversized committed record")
    refused = repo.cli("verify")
    assert refused.returncode != 0
    assert "remaining input-byte" in json.loads(refused.stdout)["reason"]


def test_actual_repeated_baseline_policy_source_spec_bytes_all_count(tmp_path):
    repo = Repo(tmp_path / "repo")
    repo.git("checkout", "-q", "main")
    repo.write(SPEC, (repo.path / SPEC).read_bytes() + b"\n<!-- " + b"x" * (2 * 1024 * 1024) + b" -->\n")
    repo.base = repo.commit("docs: admitted large immutable approved spec")
    repo.git("update-ref", "refs/remotes/origin/main", repo.base)
    repo.git("checkout", "-q", BRANCH)
    repo.git("reset", "--hard", repo.base)
    repo.write(MODULE, (ROOT / MODULE).read_bytes())
    repo.write(PLAN, (ROOT / PLAN).read_text().replace("pr: 1470", "pr: 7"))
    repo.commit("feat: exact bootstrap with admitted immutable large spec")
    accepted = repo.cli("produce")
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert json.loads(accepted.stdout)["counted_bytes"] > 6 * 1024 * 1024
    original = (repo.path / RECORD).read_bytes()
    # Each lower ceiling separately stops before one of the three repeated content reads.
    for ceiling in (2 * 1024 * 1024, 4 * 1024 * 1024, 6 * 1024 * 1024):
        refused = repo.cli("produce", "--max-input-bytes", str(ceiling))
        assert refused.returncode != 0
        assert "remaining input-byte" in json.loads(refused.stdout)["reason"]
        assert (repo.path / RECORD).read_bytes() == original


@pytest.mark.parametrize("change", ["committed", "unstaged"])
def test_actual_source_registry_cannot_reclassify_site_out_of_runtime_checks(change, tmp_path):
    repo = Repo(tmp_path / "repo")
    repo.produce_committed()
    repo.write(REGISTRY, (repo.path / REGISTRY).read_text().replace("| D | " + SITE + " | lib, scripts, tests | |", "| C | " + SITE + " | | |"))
    if change == "committed":
        repo.commit("docs: attempt unsupported SITE reclassification")
    report = json.loads(repo.audit().stdout)
    assert SITE not in report["source_identities"]
    assert any(f["doc"] == SITE and f["check"] == "source-provenance" for f in report["findings"])
    assert any(f["doc"] == SITE and f["check"] == "changed-since" for f in report["findings"])


@pytest.mark.parametrize("existing", [False, True])
def test_actual_closed_verdict_pipe_preserves_installed_or_absent_output(existing, tmp_path):
    repo = Repo(tmp_path / "repo")
    if existing:
        repo.produce_committed()
    old = (repo.path / RECORD).read_bytes() if existing else None
    read_fd, write_fd = os.pipe()
    os.close(read_fd)
    try:
        result = subprocess.run([sys.executable, MODULE, "produce"], cwd=repo.path, stdout=write_fd,
                                stderr=subprocess.PIPE, timeout=10)
    finally:
        os.close(write_fd)
    assert result.returncode != 0
    if existing:
        assert (repo.path / RECORD).read_bytes() == old
    else:
        assert not (repo.path / RECORD).exists()
    assert not list((repo.path / RECORD).parent.glob(".source-snapshot-*"))


def test_actual_manifest_reads_committed_code_not_dirty_worktree(tmp_path):
    repo = Repo(tmp_path / "repo")
    produced = repo.produce_committed()
    repo.write("lib/input.py", "VALUE = 999\n")
    verified = repo.cli("verify")
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert json.loads(verified.stdout)["source_identity_sha256"] == produced["source_identity_sha256"]


def test_actual_well_formed_forged_identity_refused_by_verifier_and_audit(tmp_path):
    repo = Repo(tmp_path / "repo")
    repo.produce_committed()
    record = json.loads((repo.path / RECORD).read_text())
    record["source_identity_sha256"] = "0" * 64
    repo.write(RECORD, json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    repo.commit("docs: canonical but false authored identity")
    refused = repo.cli("verify")
    assert refused.returncode != 0
    assert "independently derived committed identity" in json.loads(refused.stdout)["reason"]
    report = json.loads(repo.audit().stdout)
    assert SITE not in report["source_identities"]
    assert any(f["doc"] == SITE and f["check"] == "source-provenance" for f in report["findings"])
    assert any(f["doc"] == SITE and f["check"] == "changed-since" for f in report["findings"])


def policy_batch_repo(path, content="---\nstatus: draft\nfeat_id: FEAT-CICD-001\n---\n\n# Batch candidate\n"):
    repo = Repo(path)
    repo.git("checkout", "-q", "main")
    repo.write("docs/superpowers/specs/2026-10-13-batch-candidate.md", content)
    repo.base = repo.commit("docs: seed complete policy batch candidate")
    repo.git("update-ref", "refs/remotes/origin/main", repo.base)
    repo.git("checkout", "-q", BRANCH)
    repo.git("reset", "--hard", repo.base)
    repo.write(MODULE, (ROOT / MODULE).read_bytes())
    repo.write(PLAN, (ROOT / PLAN).read_text().replace("pr: 1470", "pr: 7"))
    repo.commit("feat: introduce exact bootstrap against batch policy")
    return repo


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure", ["partial", "trailing", "wrong-header", "nonzero"])
def test_actual_git_object_batch_failure_preserves_absent_or_valid_record(existing, failure, tmp_path):
    repo = policy_batch_repo(tmp_path / "repo")
    if existing:
        repo.produce_committed()
    old = (repo.path / RECORD).read_bytes() if existing else None
    real_git = shutil.which("git")
    wrappers = tmp_path / "wrappers"
    wrappers.mkdir()
    sentinel = tmp_path / "actual-batch-observed"
    change = {"partial": "raw = raw[:-1]", "trailing": "raw += b'unexpected'",
              "wrong-header": "raw = (b'0' if raw[:1] != b'0' else b'1') + raw[1:]", "nonzero": "pass"}[failure]
    code = ("#!/usr/bin/env python3\nimport os,sys,subprocess\nfrom pathlib import Path\n"
            "if '--batch' in sys.argv:\n"
            "    Path(" + repr(str(sentinel)) + ").write_text('actual Git batch')\n"
            "    result = subprocess.run([" + repr(real_git) + "] + sys.argv[1:], input=sys.stdin.buffer.read(), capture_output=True)\n"
            "    raw = result.stdout\n    " + change + "\n"
            "    sys.stdout.buffer.write(raw)\n    raise SystemExit(" + ("77" if failure == "nonzero" else "result.returncode") + ")\n"
            "os.execv(" + repr(real_git) + ", [" + repr(real_git) + "] + sys.argv[1:])\n")
    wrapper = wrappers / "git"
    handler = wrappers / "batch-handler.py"
    handler.write_text(code)
    wrapper.write_text("#!/bin/sh\nfor option do\n"
                       "    if [ \"$option\" = --batch ]; then exec " + shlex.quote(sys.executable) + " " + shlex.quote(str(handler)) + " \"$@\"; fi\n"
                       "done\nexec " + shlex.quote(real_git) + " \"$@\"\n")
    wrapper.chmod(0o755)
    env = dict(os.environ, PATH=str(wrappers) + os.pathsep + os.environ["PATH"])
    refused = subprocess.run([sys.executable, MODULE, "produce"], cwd=repo.path,
                             env=env, capture_output=True, text=True, timeout=10)
    assert sentinel.exists(), refused.stdout + refused.stderr
    assert refused.returncode != 0
    assert json.loads(refused.stdout)["status"] == "unverified"
    if existing:
        assert (repo.path / RECORD).read_bytes() == old
    else:
        assert not (repo.path / RECORD).exists()


def test_actual_policy_batch_oversize_refuses_before_materialization(tmp_path):
    repo = policy_batch_repo(tmp_path / "repo", "# Oversized candidate\n" + "x" * 8388608)
    real_git = shutil.which("git")
    wrappers = tmp_path / "wrappers"
    wrappers.mkdir()
    sentinel = tmp_path / "content-batch-must-not-start"
    wrapper = wrappers / "git"
    wrapper.write_text("#!/usr/bin/env python3\nimport os,sys\nfrom pathlib import Path\n"
                       "if '--batch' in sys.argv: Path(" + repr(str(sentinel)) + ").write_text('buffered')\n"
                       "os.execv(" + repr(real_git) + ", [" + repr(real_git) + "] + sys.argv[1:])\n")
    wrapper.chmod(0o755)
    env = dict(os.environ, PATH=str(wrappers) + os.pathsep + os.environ["PATH"])
    refused = subprocess.run([sys.executable, MODULE, "produce"], cwd=repo.path,
                             env=env, capture_output=True, text=True, timeout=10)
    assert refused.returncode != 0
    assert "remaining input-byte" in json.loads(refused.stdout)["reason"]
    assert not sentinel.exists()
    assert not (repo.path / RECORD).exists()


def test_actual_policy_batch_checks_superseding_candidate(tmp_path):
    repo = policy_batch_repo(tmp_path / "repo", "---\nstatus: approved\nfeat_id: FEAT-CICD-001\nsupersedes: " + SPEC + "\n---\n")
    refused = repo.cli("produce")
    assert refused.returncode != 0
    assert "superseded" in json.loads(refused.stdout)["reason"]
    assert not (repo.path / RECORD).exists()
