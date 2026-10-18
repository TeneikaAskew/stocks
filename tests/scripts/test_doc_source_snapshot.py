"""Real committed-repository CLI controls for source documentation identity."""
from __future__ import annotations

import datetime
import hashlib
import importlib.util
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
SITE_SCOPES = "platform/api, platform/deploy.sh, platform/Dockerfile, gcp, lib, scripts, tests"


DESCENDANT_SUPERVISOR = r'''
# Test-only Linux adopter. The production CLI and its Git process group are
# unchanged. Orphaned fixture grandchildren remain owned and waitable here.
import ctypes, json, os, pathlib, signal, subprocess, sys, time
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(36, 1, 0, 0, 0) != 0:
    raise OSError(ctypes.get_errno(), "fixture subreaper unavailable")
child = subprocess.Popen(sys.argv[2:])
reaped = []
escaped = False
try:
    result = child.wait(timeout=8)
finally:
    if child.poll() is None:
        child.kill()
        child.wait()
    until = time.monotonic() + 0.5
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        if pid:
            reaped.append({"pid": pid, "status": status})
            continue
        if time.monotonic() >= until:
            escaped = True
            # Only this isolated adopter's own children are signalable here;
            # never PID1, another runner or an external process group.
            children = pathlib.Path(f"/proc/self/task/{os.getpid()}/children")
            for raw in children.read_text().split():
                try:
                    os.kill(int(raw), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        time.sleep(0.005)
    pathlib.Path(sys.argv[1]).write_text(json.dumps({"reaped": reaped, "escaped_live_child": escaped,
                                                   "remaining_children": []}))
if escaped:
    raise AssertionError("actual CLI left a live fixture descendant")
raise SystemExit(result)
'''


def run_descendant_fixture(args, report, *, require_adoption=True, **kwargs):
    """Contain deliberate kill-group fixtures without relying on runner PID1."""
    result = subprocess.run([sys.executable, "-B", "-c", DESCENDANT_SUPERVISOR, str(report), *args], **kwargs)
    reaping = json.loads(report.read_text())
    assert not reaping["escaped_live_child"]
    assert reaping["remaining_children"] == []
    if require_adoption:
        assert reaping["reaped"], "deliberately killed grandchildren must be collected"
    return result


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
        self.write("gcp/source_input.py", b"INPUT = 'native GCP source'\n")
        self.write("platform/api/source_input.py", b"INPUT = 'namespace API source'\n")
        self.write("platform/deploy.sh", b"#!/bin/sh\nexit 0\n")
        self.write("platform/Dockerfile", b"FROM scratch\n")
        self.write(SPEC, (ROOT / SPEC).read_bytes())
        self.write("docs/product/02-FEATURE-CATALOG.md", "# Catalog\n\n| ID | Area |\n|---|---|\n| FEAT-CICD-001 | CI |\n\n### FEAT-CICD-001\n\n| Field | Value |\n|---|---|\n| Status | Source identity tests |\n| Last reviewed | " + DAY + " |\n")
        self.write("docs/product/01-PRODUCT-REQUIREMENTS.md", "# Requirements\n\n**REQ-GOV-001:** Conversations resolve.\n\n**REQ-REVIEW-001:** Authentic CODE review.\n")
        self.write("docs/product/12-PR-ISSUE-TRACEABILITY.md", "# Traceability\n\n### FEAT-CICD-001\n\n**PR lineage:** #1\n")
        self.write(REGISTRY, "# Documentation registry\n\n## Registry\n\n| Class | Path glob | Declared code paths | Generated regions |\n|---|---|---|---|\n| D | " + SITE + " | " + SITE_SCOPES + " | |\n| C | docs/product/* | | |\n| C | docs/superpowers/** | | |\n| C | docs/DOC_REGISTRY.md | | |\n")
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
    unavailable = subprocess.run(["git", "cat-file", "-e", missing], cwd=partial, capture_output=True,
                                 env=dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="/"))
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
    env = {key: value for key, value in os.environ.items() if key not in ("GIT_NO_LAZY_FETCH", "GIT_NO_REPLACE_OBJECTS", "GIT_ALLOW_PROTOCOL")}
    # Failed ext transport also leaves Git's remote helper orphaned on runners
    # without a reaping PID1; retain the real lazy-fetch/sentinel control while
    # adopting its local transport descendants in the isolated test harness.
    detection = run_descendant_fixture(["git", "cat-file", "-p", missing],
                                      tmp_path / "promisor-descendant-reaping.json", cwd=partial,
                                      env=env, capture_output=True, timeout=10, require_adoption=False)
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
    assert subprocess.run(["git", "cat-file", "-e", feature], cwd=fresh, capture_output=True,
                          env=dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="/")).returncode != 0
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


@pytest.mark.parametrize("field", ["Last reviewed", "Last scanned"])
@pytest.mark.parametrize("date", ["2099-01-01", "2099-02-30"])
@pytest.mark.parametrize("stale_import_day", [False, True])
def test_actual_terminal_rejects_future_and_impossible_marker_dates(field, date, stale_import_day, monkeypatch, tmp_path):
    if stale_import_day:
        # Collection can precede midnight while the actual auditor stamps later.
        monkeypatch.setitem(globals(), "DAY", (datetime.date.today() - datetime.timedelta(days=1)).isoformat())
    repo = installed_repo(tmp_path / "repo")
    repo.git("checkout", "-q", "-b", "docs/source-closeout")
    repo.write(SITE, (repo.path / SITE).read_text() + "\nGenuine local main body close-out evidence.\n")
    repo.commit("docs: actual body publication before terminal marker")
    repo.produce_committed()
    repo.git("checkout", "-q", "main")
    repo.git("merge", "--squash", "docs/source-closeout")
    landed = repo.commit("docs: actual body-first squash")
    repo.git("update-ref", "refs/remotes/origin/main", landed)
    repo.git("checkout", "-q", "-b", "docs/source-terminal")
    stamp_before = datetime.date.today()
    stamped = repo.audit("--stamp", "--verify", SITE)
    stamp_after = datetime.date.today()
    assert stamped.returncode in (0, 1), stamped.stdout + stamped.stderr
    assert any(row["doc"] == SITE and row["action"] in ("updated", "unchanged") for row in json.loads(stamped.stdout)["stamped"])
    (repo.path / RECORD).unlink()
    repo.commit("docs: genuine terminal stamp and record retirement")
    accepted = repo.cli("verify")
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    assert json.loads(accepted.stdout)["eligible_route"] == "terminal-ordinary"
    body = (repo.path / SITE).read_text()
    marker = next(line for line in body.splitlines() if line.startswith("**Last reviewed:** "))
    prefix = f"**{field}:** "
    tokens = [token for token in marker.split(" · ") if token.startswith(prefix)]
    assert len(tokens) == 1
    needle = tokens[0]
    assert stamp_before <= datetime.date.fromisoformat(needle[len(prefix):]) <= stamp_after
    assert body.count(needle) == 1
    repo.write(SITE, body.replace(needle, f"**{field}:** {date}", 1))
    repo.commit("docs: record refused marker date")
    refused = repo.cli("verify")
    assert refused.returncode != 0, refused.stdout + refused.stderr
    assert json.loads(refused.stdout)["status"] == "unverified"
    report = json.loads(repo.audit().stdout)
    assert any(f["doc"] == SITE and f["check"] == "marker" and date in f["detail"] for f in report["findings"])
    assert any(f["doc"] == SITE and f["check"] == "source-provenance" for f in report["findings"])


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
    runner = run_descendant_fixture if failure == "slow" else subprocess.run
    extra = {"report": tmp_path / "descendant-reaping.json"} if failure == "slow" else {}
    result = runner(args, **extra, cwd=repo.path, env=env, capture_output=True, text=True, timeout=10)
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
    repo.write(REGISTRY, (repo.path / REGISTRY).read_text().replace("| D | " + SITE + " | " + SITE_SCOPES + " | |", "| C | " + SITE + " | | |"))
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


def normalization_oracle():
    spec = importlib.util.spec_from_file_location("_test_source_body_protocol", ROOT / MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
        audit = module.trusted_module("_test_source_body_original_audit", AUDIT)
    finally:
        sys.dont_write_bytecode = previous
    snapshot = module.Snapshot.__new__(module.Snapshot)
    snapshot.audit = audit
    return snapshot, audit


@pytest.mark.parametrize("shape", ["plain", "heading-code", "heading-html", "comment", "fence",
                                   "span", "quote", "setext", "extra-prose", "owner-markup",
                                   "duplicate", "late-marker", "crlf", "bom"])
def test_complete_body_normalization_equals_original_parser_at_visibility_boundaries(shape):
    snapshot, audit = normalization_oracle()
    marker = "**Last reviewed:** " + DAY + " · **Depth:** verified · **Against:** `12345678` · **Owner:** Source tests"
    prefix = "# Plain title\n\n" + marker + "\n\n## Body\n"
    if shape == "heading-code":
        prefix = prefix.replace("# Plain title", "# `title`")
    elif shape == "heading-html":
        prefix = prefix.replace("# Plain title", "# <span>title</span>")
    elif shape in ("comment", "fence", "span"):
        opener, closer = {"comment": ("<!--\n", "-->\n"), "fence": ("```markdown\n", "```\n"), "span": ("`\n", "`\n")}[shape]
        prefix = opener + prefix + closer
    elif shape == "quote":
        prefix = "\n".join("> " + line for line in prefix.split("\n"))
    elif shape == "setext":
        prefix = prefix.replace("# Plain title", "Plain title\n===========")
    elif shape == "extra-prose":
        prefix = prefix.replace(marker, marker + " · **Trust status:** preserve every word")
    elif shape == "owner-markup":
        prefix = prefix.replace("Source tests", "[Source tests](https://example.invalid)")
    elif shape == "duplicate":
        prefix = prefix.replace("\n\n## Body", "\n" + marker + "\n\n## Body")
    elif shape == "late-marker":
        prefix = prefix.replace("\n\n" + marker, "\n" * 41 + marker)
    elif shape == "crlf":
        prefix = prefix.replace("\n", "\r\n")
    elif shape == "bom":
        prefix = "\ufeff" + prefix
    # Later source/progress/metadata and unmatched suffix openers stay in full.
    suffix = "backend source; frontend progress 17%; café\n```python\nVALUE = 2\n```\n<div>\n" + marker + "\n</div>\n`unclosed suffix\n"
    text = prefix + suffix
    expected = audit._without_marker(text)
    assert snapshot.normalized_body(text) == expected
    changed = text.replace("progress 17%", "progress 18%")
    assert snapshot.normalized_body(changed) == audit._without_marker(changed)
    assert snapshot.normalized_body(changed) != expected


def test_actual_full_current_site_producer_hash_matches_complete_original_normalizer(tmp_path):
    _, audit = normalization_oracle()
    raw = (ROOT / SITE).read_bytes()
    expected = hashlib.sha256(audit._without_marker(raw.decode("utf-8")).encode("utf-8")).hexdigest()
    repo = Repo(tmp_path / "repo")
    repo.git("checkout", "-q", "main")
    repo.write(SITE, raw)
    repo.base = repo.commit("docs: complete actual current SITE body oracle input")
    repo.git("update-ref", "refs/remotes/origin/main", repo.base)
    repo.git("checkout", "-q", BRANCH)
    repo.git("reset", "--hard", repo.base)
    repo.write(MODULE, (ROOT / MODULE).read_bytes())
    repo.write(PLAN, (ROOT / PLAN).read_text().replace("pr: 1470", "pr: 7"))
    repo.commit("feat: exact bootstrap against complete actual SITE body")
    accepted = repo.cli("produce")
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    verdict = json.loads(accepted.stdout)
    assert verdict["document_body_sha256"] == expected
    assert verdict["counted_bytes"] >= len(raw) * 2


def complex_body_repo(path, line_count, existing=False):
    repo = Repo(path)
    if existing:
        repo.produce_committed()
    old = (repo.path / RECORD).read_bytes() if existing else None
    repo.git("checkout", "-q", "main")
    body = (repo.path / SITE).read_text().replace("# Site traceability", "# Site *traceability*", 1)
    body += "\n" + "Ordinary bounded document prose and a citation-free sentence.\n" * line_count
    repo.write(SITE, body)
    repo.base = repo.commit("docs: genuine complete complex-heading body")
    repo.git("update-ref", "refs/remotes/origin/main", repo.base)
    repo.git("checkout", "-q", BRANCH)
    repo.git("reset", "--hard", repo.base)
    repo.write(MODULE, (ROOT / MODULE).read_bytes())
    repo.write(PLAN, (ROOT / PLAN).read_text().replace("pr: 1470", "pr: 7"))
    repo.commit("feat: scoped verifier against unchanged complete complex body")
    if old is not None:
        repo.write(RECORD, old)
    return repo, body, old


@pytest.mark.parametrize("existing", [False, True])
def test_actual_fallback_parser_cpu_deadline_preserves_absent_or_valid_record(existing, tmp_path):
    repo, body, old = complex_body_repo(tmp_path / "repo", 40000, existing)
    refused = repo.cli("produce", "--max-seconds", "2")
    verdict = json.loads(refused.stdout)
    assert refused.returncode != 0, refused.stdout + refused.stderr
    assert verdict["status"] == "unverified"
    assert verdict["reason"] == "whole verification CPU deadline exceeded"
    assert verdict["source_identity_sha256"] is not None
    assert verdict["counted_bytes"] >= len(body.encode("utf-8"))
    assert verdict["counted_bytes"] <= 8388608
    # A lower-only two-second cap avoids relying on host throughput to make
    # this bounded complete parser input exceed the default five-second cap.
    # The alarm interrupts CPU work at two seconds; this measures only the
    # ensuing handler restoration and refusal serialization, not a larger cap.
    assert verdict["elapsed_seconds"] < 2.1
    if old is None:
        assert not (repo.path / RECORD).exists()
    else:
        assert (repo.path / RECORD).read_bytes() == old
    assert not list((repo.path / RECORD).parent.glob(".source-snapshot-*"))


def test_actual_nearby_complete_fallback_parser_produce_and_verify_accepted(tmp_path):
    repo, body, _ = complex_body_repo(tmp_path / "repo", 5000)
    produced = repo.produce_committed()
    assert produced["counted_bytes"] >= len(body.encode("utf-8")) * 2
    verified = repo.cli("verify")
    assert verified.returncode == 0, verified.stdout + verified.stderr
    verdict = json.loads(verified.stdout)
    assert verdict["source_identity_sha256"] == produced["source_identity_sha256"]
    assert verdict["document_body_sha256"] == produced["document_body_sha256"]
    assert verdict["elapsed_seconds"] < 5


CPU_CALLER = r'''
import importlib.util, json, pathlib, signal, sys, threading, time
spec = importlib.util.spec_from_file_location("actual_cpu_protocol", pathlib.Path.cwd() / "scripts/maintenance/doc_source_snapshot.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
mode = sys.argv[1]
def prior_handler(signum, frame):
    raise AssertionError("previous caller alarm must not execute")
signal.signal(signal.SIGALRM, prior_handler)
original_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
if mode == "blocked":
    signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
elif mode == "mask-accepted":
    signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGUSR1})
expected_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
if mode == "active":
    signal.setitimer(signal.ITIMER_REAL, 10, 3)
elif mode == "unsupported":
    del signal.setitimer
elif mode == "backup-cleanup":
    original_unlink = module.Path.unlink
    def unlink(self, *args, **kwargs):
        if self.name.startswith(".source-snapshot-backup-"):
            raise OSError("actual backup cleanup refusal")
        return original_unlink(self, *args, **kwargs)
    module.Path.unlink = unlink
elif mode.startswith("cleanup-"):
    original_unlink = module.Path.unlink
    def unlink(self, *args, **kwargs):
        if self.name.startswith(".source-snapshot-backup-"):
            pathlib.Path("cleanup-entered").write_text(mode)
            if mode in ("cleanup-after-delay", "cleanup-after-error"):
                original_unlink(self, *args, **kwargs)
                pathlib.Path("cleanup-physically-complete").write_text(mode)
            if mode.endswith("delay"):
                time.sleep(5.25 if mode == "cleanup-default-delay" else 1.3)
            elif mode.endswith("error"):
                raise OSError("actual cleanup boundary refusal")
            if mode in ("cleanup-after-delay", "cleanup-after-error"):
                return
        return original_unlink(self, *args, **kwargs)
    module.Path.unlink = unlink
elif mode in ("output-timeout", "post-output-refusal"):
    original_emit = module.emit
    original_remaining = module.Budget.remaining
    output_complete = False
    def remaining(self):
        if output_complete:
            raise module.Unavailable("actual final guard boundary refusal")
        return original_remaining(self)
    if mode == "post-output-refusal":
        module.Budget.remaining = remaining
    def emit(value, budget=None):
        global output_complete
        if value["status"] == "identity-matched":
            pathlib.Path("output-callback-entered").write_text("actual installed producer callback\n")
            if mode == "post-output-refusal":
                original_emit(value, budget)
                output_complete = True
                return
            while True:
                pass
        return original_emit(value, budget)
    module.emit = emit
args = ["verify"] if mode == "verify" else ["produce"]
if mode.startswith("cleanup-") and mode != "cleanup-default-delay":
    args += ["--max-seconds", "1"]
if mode == "thread":
    results = []
    worker = threading.Thread(target=lambda: results.append(module.main(args)))
    worker.start()
    worker.join()
    result = results[0]
else:
    result = module.main(args)
remaining, interval = signal.getitimer(signal.ITIMER_REAL)
restored = signal.getsignal(signal.SIGALRM) is prior_handler
mask_restored = signal.pthread_sigmask(signal.SIG_BLOCK, set()) == expected_mask
print(json.dumps({"handler_restored": restored, "mask_restored": mask_restored,
                  "remaining": remaining, "interval": interval}), file=sys.stderr)
if mode == "active":
    assert 0 < remaining <= 10 and interval == 3
    signal.setitimer(signal.ITIMER_REAL, 0)
else:
    assert remaining == interval == 0
assert restored
assert mask_restored
signal.pthread_sigmask(signal.SIG_SETMASK, original_mask)
raise SystemExit(result)
'''


def actual_cpu_caller(repo, mode):
    return subprocess.run([sys.executable, "-B", "-c", CPU_CALLER, mode], cwd=repo.path,
                          capture_output=True, text=True, timeout=10)


@pytest.mark.parametrize("mode", ["produce", "verify", "init-refusal", "active", "thread", "unsupported", "blocked", "mask-accepted"])
@pytest.mark.parametrize("existing", [False, True])
def test_actual_entrypoint_restores_or_preserves_caller_timer(mode, existing, tmp_path):
    repo = Repo(tmp_path / "repo")
    if existing or mode == "verify":
        repo.produce_committed()
    old = (repo.path / RECORD).read_bytes() if (repo.path / RECORD).exists() else None
    if mode == "init-refusal":
        repo.git("config", "remote.fixture.promisor", "true")
    result = actual_cpu_caller(repo, mode)
    verdict = json.loads(result.stdout)
    assert json.loads(result.stderr.splitlines()[-1])["handler_restored"] is True, result.stderr
    assert json.loads(result.stderr.splitlines()[-1])["mask_restored"] is True, result.stderr
    if mode in ("produce", "verify", "mask-accepted"):
        assert result.returncode == 0, result.stdout + result.stderr
        assert verdict["status"] == "identity-matched"
    else:
        assert result.returncode != 0
        assert verdict["status"] == "unverified"
        expected = {"init-refusal": "partial-clone or promisor", "active": "preexisting active CPU timer",
                    "thread": "POSIX main-thread caller", "unsupported": "POSIX main-thread caller",
                    "blocked": "preblocked SIGALRM"}[mode]
        assert expected in verdict["reason"]
        if old is None:
            assert not (repo.path / RECORD).exists()
        else:
            assert (repo.path / RECORD).read_bytes() == old


@pytest.mark.parametrize("existing", [False, True])
def test_actual_output_callback_cpu_timeout_rolls_back_and_restores_caller(existing, tmp_path):
    repo = Repo(tmp_path / "repo")
    if existing:
        repo.produce_committed()
    old = (repo.path / RECORD).read_bytes() if existing else None
    refused = actual_cpu_caller(repo, "output-timeout")
    assert refused.returncode != 0
    assert json.loads(refused.stdout)["reason"] == "whole verification CPU deadline exceeded"
    assert json.loads(refused.stderr.splitlines()[-1])["handler_restored"] is True
    assert (repo.path / "output-callback-entered").exists()
    if old is None:
        assert not (repo.path / RECORD).exists()
    else:
        assert (repo.path / RECORD).read_bytes() == old
    assert not list((repo.path / RECORD).parent.glob(".source-snapshot-*"))


@pytest.mark.parametrize("existing", [False, True])
def test_actual_final_guard_refusal_after_output_rolls_back_record(existing, tmp_path):
    repo = Repo(tmp_path / "repo")
    if existing:
        repo.produce_committed()
    old = (repo.path / RECORD).read_bytes() if existing else None
    refused = actual_cpu_caller(repo, "post-output-refusal")
    assert refused.returncode != 0
    # Bytes already written to a pipe cannot be retracted. A final guard
    # refusal must roll back, exit nonzero and never append contradictory JSON;
    # this cannot satisfy exit0 plus one complete final verdict acceptance.
    assert len(refused.stdout.splitlines()) == 1
    assert json.loads(refused.stdout)["status"] == "identity-matched"
    assert json.loads(refused.stderr.splitlines()[-1])["handler_restored"] is True
    assert (repo.path / "output-callback-entered").exists()
    if old is None:
        assert not (repo.path / RECORD).exists()
    else:
        assert (repo.path / RECORD).read_bytes() == old
    assert not list((repo.path / RECORD).parent.glob(".source-snapshot-*"))


def test_actual_backup_cleanup_failure_restores_valid_record(tmp_path):
    repo = Repo(tmp_path / "repo")
    repo.produce_committed()
    old = (repo.path / RECORD).read_bytes()
    refused = actual_cpu_caller(repo, "backup-cleanup")
    assert refused.returncode != 0
    verdict = json.loads(refused.stdout)
    assert verdict["status"] == "unverified"
    assert verdict["reason"] == "actual backup cleanup refusal"
    assert json.loads(refused.stderr.splitlines()[-1])["handler_restored"] is True
    assert (repo.path / RECORD).read_bytes() == old
    assert not list((repo.path / RECORD).parent.glob(".source-snapshot-*"))


@pytest.mark.parametrize("mode", ["cleanup-before-delay", "cleanup-after-delay", "cleanup-before-error", "cleanup-after-error", "cleanup-default-delay", "cleanup-accepted"])
def test_actual_cleanup_boundary_preserves_different_valid_record(mode, tmp_path):
    repo = Repo(tmp_path / "repo")
    repo.produce_committed()
    old = (repo.path / RECORD).read_bytes()
    repo.write(MODULE, (repo.path / MODULE).read_bytes() + b"\n# Genuine later bootstrap source.\n")
    repo.commit("feat: change eligible bootstrap source after old valid record")
    expected = repo.cli("produce")
    assert expected.returncode == 0, expected.stdout + expected.stderr
    new = (repo.path / RECORD).read_bytes()
    assert new != old
    (repo.path / RECORD).write_bytes(old)
    started = time.monotonic()
    attempted = actual_cpu_caller(repo, mode)
    elapsed = time.monotonic() - started
    assert (repo.path / "cleanup-entered").exists()
    assert json.loads(attempted.stderr.splitlines()[-1])["handler_restored"] is True
    assert json.loads(attempted.stderr.splitlines()[-1])["mask_restored"] is True
    if mode == "cleanup-accepted":
        assert attempted.returncode == 0, attempted.stdout + attempted.stderr
        verdict = json.loads(attempted.stdout)
        assert verdict["status"] == "identity-matched"
        assert (repo.path / RECORD).read_bytes() == new
        assert verdict["elapsed_seconds"] < 1
    else:
        assert attempted.returncode != 0, attempted.stdout + attempted.stderr
        verdict = json.loads(attempted.stdout)
        assert verdict["status"] == "unverified"
        assert (repo.path / RECORD).read_bytes() == old
        if mode.endswith("delay"):
            cap = 5 if mode == "cleanup-default-delay" else 1
            assert verdict["elapsed_seconds"] < cap + 0.15
            assert elapsed < cap + 0.5
        else:
            assert verdict["reason"] == "actual cleanup boundary refusal"
    if mode in ("cleanup-after-delay", "cleanup-after-error"):
        assert (repo.path / "cleanup-physically-complete").exists()
    assert not list((repo.path / RECORD).parent.glob(".source-snapshot-*"))


@pytest.mark.parametrize("entry", ["build", "verify", "terminal", "gate_note_scope"])
def test_actual_library_entrypoint_cpu_guard_and_nested_deadline(entry, tmp_path):
    repo = Repo(tmp_path / "repo")
    script = r'''
import importlib.util, json, pathlib, signal, sys, time
spec = importlib.util.spec_from_file_location("actual_cpu_library", pathlib.Path.cwd() / "scripts/maintenance/doc_source_snapshot.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
def prior_handler(signum, frame):
    raise AssertionError("prior caller timer executed")
signal.signal(signal.SIGALRM, prior_handler)
snapshot = module.Snapshot(pathlib.Path.cwd())
snapshot.budget.deadline = time.monotonic() + 0.05
# Exercise the real public library wrapper with CPU work at its first existing
# operation; no authored verdict or alternative successful parser is supplied.
def busy(*args, **kwargs):
    while True:
        pass
entry = sys.argv[1]
if entry == "gate_note_scope":
    snapshot.git.commit = busy
    args = ("origin/main", "origin/main", "HEAD", "FEAT-CICD-001", module.SPEC)
else:
    snapshot.dirty_site = busy
    args = ()
try:
    with snapshot.budget.cpu_guard():
        getattr(snapshot, entry)(*args)
except module.Unavailable as error:
    assert str(error) == "whole verification CPU deadline exceeded"
else:
    raise AssertionError("public library entrypoint completed beyond its deadline")
assert snapshot.budget.cpu_depth == 0
assert signal.getsignal(signal.SIGALRM) is prior_handler
assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
print(json.dumps({"refused": True, "handler_restored": True, "entry": entry}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, entry], cwd=repo.path,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {"refused": True, "handler_restored": True, "entry": entry}


@pytest.mark.parametrize("edge", ["handle", "selector", "selector-close", "reap"])
@pytest.mark.parametrize("existing", [False, True])
def test_actual_spawn_boundary_deadline_kills_and_reaps_git_group(edge, existing, tmp_path):
    repo = Repo(tmp_path / "repo")
    if existing:
        repo.produce_committed()
    old = (repo.path / RECORD).read_bytes() if existing else None
    wrapper = repo.path / "fixture-git-bin"
    wrapper.mkdir()
    git = shutil.which("git")
    child_sentinel = repo.path / "unreaped-git-child"
    launcher = wrapper / "git"
    launcher.write_text("#!/bin/sh\ncase \" $* \" in\n  *' config --get-regexp '*)\n"
                        + "    (sleep 2; printf orphan > " + shlex.quote(str(child_sentinel)) + ") &\n"
                        + "    sleep 3\n    ;;\nesac\nexec " + shlex.quote(git) + " \"$@\"\n")
    launcher.chmod(0o755)
    script = r'''
import importlib.util, json, os, pathlib, signal, sys, time
spec = importlib.util.spec_from_file_location("actual_spawn_boundary", pathlib.Path.cwd() / "scripts/maintenance/doc_source_snapshot.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
edge = sys.argv[1]
children = []
armed = False
def prior_handler(signum, frame):
    raise AssertionError("previous caller alarm executed")
signal.signal(signal.SIGALRM, prior_handler)
prior_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGUSR1})
expected_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
original_popen = module.subprocess.Popen
def popen(argv, *args, **kwargs):
    global armed
    child = original_popen(argv, *args, **kwargs)
    if "config" in argv and "--get-regexp" in argv:
        children.append(child)
        armed = True
        if edge == "handle":
            # Expire the actual one-second alarm while its acquisition mask is
            # blocked; delivery must occur after handle storage inside cleanup.
            until = time.monotonic() + 1.1
            while time.monotonic() < until:
                pass
    return child
module.subprocess.Popen = popen
original_selector = module.selectors.DefaultSelector
selected = False
def selector():
    global selected
    target = armed and not selected
    if target:
        selected = True
    if target and edge == "selector":
        while True:
            pass
    value = original_selector()
    if target and edge in ("selector-close", "reap"):
        original_close = value.close
        def close():
            if edge == "selector-close":
                while True:
                    pass
            original_close()
        value.close = close
        # Enter cleanup from a concrete setup error while the alarm is armed.
        def register(*args, **kwargs):
            raise OSError("actual selector setup refusal")
        value.register = register
    return value
module.selectors.DefaultSelector = selector
original_kill = module.os.killpg
kill_entered = False
def killpg(*args):
    global kill_entered
    if armed and edge == "reap" and not kill_entered:
        kill_entered = True
        while True:
            pass
    return original_kill(*args)
module.os.killpg = killpg
result = module.main(["produce", "--max-seconds", "1"])
assert result == 1 and children
for child in children:
    assert child.returncode is not None
    try:
        os.waitpid(child.pid, os.WNOHANG)
    except ChildProcessError:
        pass
    else:
        raise AssertionError("Git child was not reaped")
assert signal.getsignal(signal.SIGALRM) is prior_handler
assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
assert signal.pthread_sigmask(signal.SIG_BLOCK, set()) == expected_mask
signal.pthread_sigmask(signal.SIG_SETMASK, prior_mask)
print(json.dumps({"reaped": True, "handler_restored": True, "mask_restored": True}), file=sys.stderr)
raise SystemExit(result)
'''
    env = dict(os.environ, PATH=str(wrapper) + os.pathsep + os.environ["PATH"])
    refused = run_descendant_fixture([sys.executable, "-B", "-c", script, edge],
                                     tmp_path / "descendant-reaping.json", cwd=repo.path,
                                     env=env, capture_output=True, text=True, timeout=10)
    assert refused.returncode == 1, refused.stdout + refused.stderr
    assert len(refused.stdout.splitlines()) == 1
    verdict = json.loads(refused.stdout)
    assert verdict["status"] == "unverified"
    assert verdict["reason"] == "whole verification CPU deadline exceeded"
    assert json.loads(refused.stderr.splitlines()[-1]) == {"reaped": True, "handler_restored": True, "mask_restored": True}
    time.sleep(2.1)
    assert not child_sentinel.exists()
    if old is None:
        assert not (repo.path / RECORD).exists()
    else:
        assert (repo.path / RECORD).read_bytes() == old
    assert not list((repo.path / RECORD).parent.glob(".source-snapshot-*"))

@pytest.mark.parametrize('missing', SITE_SCOPES.split(', '))
def test_actual_prior_policy_cannot_remove_protected_site_root(missing, tmp_path):
    repo = Repo(tmp_path / 'repo')
    repo.git('checkout', '-q', 'main')
    policy = (repo.path / REGISTRY).read_text()
    reduced = ', '.join(p for p in SITE_SCOPES.split(', ') if p != missing)
    repo.write(REGISTRY, policy.replace(SITE_SCOPES, reduced))
    repo.base = repo.commit('docs: prior policy removes one actual SITE root')
    repo.git('update-ref', 'refs/remotes/origin/main', repo.base)
    repo.git('checkout', '-q', BRANCH)
    repo.git('merge', '-q', 'main')
    for action in ('produce', 'verify'):
        result = repo.cli(action)
        assert result.returncode != 0, result.stdout + result.stderr
        assert 'minimum' in json.loads(result.stdout)['reason'], result.stdout
    audited = repo.audit()
    assert audited.returncode == 2, audited.stdout + audited.stderr
    assert 'minimum' in audited.stderr


def test_actual_root_shadow_changes_are_not_absent_from_source_identity(tmp_path):
    repo = Repo(tmp_path / 'repo')
    repo.produce_committed()
    repo.write('json.py', "VALUE = 'unexecuted proposed input'\n")
    repo.commit('feat: root startup slot changes after production')
    result = repo.cli('verify')
    assert result.returncode != 0, result.stdout + result.stderr
    assert json.loads(result.stdout)['status'] == 'unverified'


def test_actual_complete_repository_runs_with_native_git243(tmp_path, monkeypatch):
    native = os.environ.get('SOURCE_REVIEW_GIT243', shutil.which('git'))
    shim = tmp_path / 'native-bin'
    shim.mkdir()
    (shim / 'git').symlink_to(native)
    monkeypatch.setenv('PATH', str(shim) + os.pathsep + os.environ['PATH'])
    if 'SOURCE_REVIEW_GIT243' in os.environ:
        monkeypatch.setenv('GIT_EXEC_PATH', str(Path(native).parent))
    repo = Repo(tmp_path / 'repo')
    repo.produce_committed()
    assert repo.cli('verify').returncode == 0


@pytest.mark.parametrize('key,value', [
    ('extensions.partialClone', 'fixture'), ('extensions.PARTIALCLONE', ''),
    ('remote.fixture.promisor', 'true'), ('remote.fixture.PROMISOR', 'false'),
    ('remote.fixture.promisor', '0'), ('remote.fixture.partialclonefilter', 'blob:none'),
    ('remote.fixture.PARTIALCLONEFILTER', ''),
])
def test_actual_promisor_configuration_refuses_before_object_reads(key, value, tmp_path, monkeypatch):
    repo = Repo(tmp_path / 'repo')
    repo.produce_committed()
    original = (repo.path / RECORD).read_bytes()
    repo.git('config', key, value)
    real_git = shutil.which('git')
    log = tmp_path / 'admission-commands.jsonl'
    wrappers = tmp_path / 'git-bin'
    wrappers.mkdir()
    wrapper = wrappers / 'git'
    wrapper.write_text('#!' + sys.executable + '\nimport json,os,sys\n'
                       + 'with open(' + repr(str(log)) + ',"a") as out: out.write(json.dumps(sys.argv[1:])+"\\n")\n'
                       + 'os.execv(' + repr(real_git) + ',[' + repr(real_git) + ']+sys.argv[1:])\n')
    wrapper.chmod(0o755)
    monkeypatch.setenv('PATH', str(wrappers) + os.pathsep + os.environ['PATH'])
    for action in ('produce', 'verify'):
        result = repo.cli(action)
        assert result.returncode != 0, result.stdout + result.stderr
        assert 'promisor' in json.loads(result.stdout)['reason']
        assert json.loads(result.stdout)['source_identity_sha256'] is None
        assert (repo.path / RECORD).read_bytes() == original
    audited = repo.audit()
    assert audited.returncode == 2, audited.stdout + audited.stderr
    assert 'promisor' in audited.stderr
    commands = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(commands) == 3
    assert all('config' in args and '--get-regexp' in args for args in commands), commands


@pytest.mark.parametrize('path', ['json.py', 'signal.py', 'json/__init__.py', 'json.pyc',
                                  'json.so', 'scripts.py', 'yaml.py', '_pytest/__init__.py'])
def test_actual_proposed_root_import_slot_is_manifested_without_execution(path, tmp_path):
    repo = bound_note_repo(tmp_path / 'repo')
    repo.write(path, "UNEXECUTED_SOURCE_INPUT = 1\n")
    repo.commit('feat: new committed startup input')
    refused = repo.cli('verify')
    assert refused.returncode != 0, refused.stdout + refused.stderr
    preflight = repo.cli('produce')
    assert preflight.returncode != 0
    identity = json.loads(preflight.stdout)['source_identity_sha256']
    assert identity
    old_record = json.loads((repo.path / RECORD).read_text())
    repo.write(SITE, (repo.path / SITE).read_text().replace(old_record['source_identity_sha256'], identity))
    repo.commit('docs: bind actual new startup source input')
    repo.produce_committed()
    record = json.loads((repo.path / RECORD).read_text())
    assert path in {row['path'] for row in record['source_entries']}
    assert repo.cli('verify').returncode == 0


def test_actual_minimum_preserves_additive_watchers(tmp_path):
    repo = installed_repo(tmp_path / 'repo')
    repo.git('checkout', '-q', 'main')
    repo.write(REGISTRY, (repo.path / REGISTRY).read_text().replace(SITE_SCOPES, SITE_SCOPES + ', extra_runtime'))
    repo.base = repo.commit('docs: add a genuine extra runtime watcher')
    repo.git('update-ref', 'refs/remotes/origin/main', repo.base)
    repo.git('checkout', '-q', BRANCH)
    repo.git('reset', '--hard', repo.base)
    repo.write(PLAN, (ROOT / PLAN).read_text().replace(SPEC, NOTE_SPEC).replace('pr: 1470', 'pr: 7'))
    repo.write('extra_runtime/new_input.py', 'EXTRA = 1\n')
    repo.commit('feat: added runtime root must remain watched')
    preflight = repo.cli('produce')
    assert preflight.returncode != 0, preflight.stdout
    identity = json.loads(preflight.stdout)['source_identity_sha256']
    assert identity
    append_note(repo, identity)
    repo.produce_committed()
    record = json.loads((repo.path / RECORD).read_text())
    assert 'extra_runtime' in record['policy']['watch_paths']
    assert 'extra_runtime/new_input.py' in {row['path'] for row in record['source_entries']}
    assert repo.cli('verify').returncode == 0


@pytest.mark.parametrize('replacement', ['scripts/narrow', 'scriptss', 'platform/apix'])
def test_actual_policy_minimum_rejects_descendants_and_false_prefixes(replacement, tmp_path):
    repo = Repo(tmp_path / 'repo')
    repo.produce_committed()
    original = (repo.path / RECORD).read_bytes()
    repo.git('checkout', '-q', 'main')
    dropped = 'platform/api' if replacement.startswith('platform') else 'scripts'
    narrowed = ', '.join(replacement if p == dropped else p for p in SITE_SCOPES.split(', '))
    repo.write(REGISTRY, (repo.path / REGISTRY).read_text().replace(SITE_SCOPES, narrowed))
    repo.base = repo.commit('docs: earlier narrowed current policy')
    repo.git('update-ref', 'refs/remotes/origin/main', repo.base)
    repo.git('checkout', '-q', BRANCH)
    repo.git('merge', '-q', 'main')
    for action in ('produce', 'verify'):
        result = repo.cli(action)
        assert result.returncode != 0, result.stdout + result.stderr
        assert 'minimum' in json.loads(result.stdout)['reason']
        assert (repo.path / RECORD).read_bytes() == original


def test_actual_policy_minimum_accepts_true_broader_platform_ancestor(tmp_path):
    repo = Repo(tmp_path / 'repo')
    repo.git('checkout', '-q', 'main')
    broader = 'platform, gcp, lib, scripts, tests'
    repo.write(REGISTRY, (repo.path / REGISTRY).read_text().replace(SITE_SCOPES, broader))
    repo.base = repo.commit('docs: true broader platform watcher')
    repo.git('update-ref', 'refs/remotes/origin/main', repo.base)
    repo.git('checkout', '-q', BRANCH)
    repo.git('merge', '-q', 'main')
    repo.produce_committed()
    assert repo.cli('verify').returncode == 0
