"""Bounded, reproducible committed-source identity; never review authentication."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
SITE = "docs/product/03-SITE-TRACEABILITY.md"
REGISTRY = "docs/DOC_REGISTRY.md"
RECORD = "docs/review-evidence/site-source-snapshot.json"
SPEC = "docs/superpowers/specs/2026-10-13-feat-cicd-001-source-review-verifier.md"
MODULE = "scripts/maintenance/doc_source_snapshot.py"
MAX_SECONDS = 5.0
MAX_BYTES = 8388608
MAX_ENTRIES = 20000
INITIAL_FILES = frozenset((MODULE, "scripts/maintenance/docs_audit.py", "scripts/gate/spec_gate.py",
                          "tests/scripts/test_doc_source_snapshot.py", "tests/scripts/test_docs_audit.py",
                          "tests/scripts/test_spec_gate.py"))
CONTEXT = "implementation-source identity matched; external CODE review under existing rules; rollout pending"
NOTE_HEADING = "## Implementation-source notes"
NOTE_HEADER = "| FEAT | Component | Backend source and tests (implementation only; rollout pending) |"
NOTE_DELIMITER = "|---|---|---|"
FEAT_PATTERN = re.compile(r"FEAT-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d{3}")
COMPONENT_PATTERN = re.compile(r"[A-Z][A-Z0-9]*-\d{2}")
TOP_KEYS = frozenset(("version", "context", "object_format", "eligibility", "policy", "baseline",
                      "source_entries", "source_identity_sha256", "document_path", "document_body_sha256"))


class Unavailable(Exception):
    pass


def canonical(value) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                           allow_nan=False) + "\n").encode("utf-8", "strict")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise Unavailable("unsupported canonical JSON") from exc


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def text(value: bytes) -> str:
    try:
        return value.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise Unavailable("input is not strict UTF-8") from exc


def repo_path(path: str) -> bool:
    return (isinstance(path, str) and bool(path) and not path.startswith("/") and "\\" not in path
            and all(part not in ("", ".", "..") for part in path.split("/"))
            and not any(unicodedata.category(c) == "Cc" for c in path))


def chain_ids(body: str) -> set[str]:
    """Only existing Chain table selectors, never appended author declarations."""
    inside = False
    found = []
    for line in body.splitlines():
        if re.match(r"^#{1,6} ", line):
            inside = line == "### Chain"
        if inside and line.startswith("|"):
            cell = line.split("|", 2)[1].strip()
            if COMPONENT_PATTERN.fullmatch(cell):
                found.append(cell)
    if len(found) != len(set(found)):
        raise Unavailable("ambiguous duplicate Chain component")
    return set(found)


def declaration(fm: dict, body: str) -> list[str]:
    value = fm.get("site_source_notes", [])
    if (not isinstance(value, list) or any(not isinstance(x, str) or not COMPONENT_PATTERN.fullmatch(x) for x in value)
            or value != sorted(set(value)) or not set(value) <= chain_ids(body)):
        raise Unavailable("site_source_notes must be sorted unique existing Chain IDs")
    return value


def notes(body: str) -> tuple[str, dict]:
    """Exact appended area, with each foreign row retained byte for byte."""
    lines = body.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.rstrip("\n") == NOTE_HEADING]
    if not starts:
        if NOTE_HEADING in body:
            raise Unavailable("malformed implementation-source note heading")
        return body, {}
    if len(starts) != 1:
        raise Unavailable("duplicate implementation-source note heading")
    i = starts[0]
    if i < 1 or lines[i - 1] != "\n" or not body.endswith("\n"):
        raise Unavailable("notes must be a final appended section")
    tail = [line.rstrip("\n") for line in lines[i:]]
    if len(tail) < 5 or tail[:4] != [NOTE_HEADING, "", NOTE_HEADER, NOTE_DELIMITER]:
        raise Unavailable("invalid/empty implementation-source notes table")
    rows = {}
    order = []
    for line in tail[4:]:
        if not line.startswith("| ") or not line.endswith(" |") or line.count("|") != 4 or "\r" in line:
            raise Unavailable("notes must be single-line three-cell rows")
        feat, component, prose = [part.strip() for part in line.split("|")[1:-1]]
        key = (feat, component)
        if not FEAT_PATTERN.fullmatch(feat) or not COMPONENT_PATTERN.fullmatch(component) or not prose or key in rows:
            raise Unavailable("invalid or duplicate implementation-source row")
        rows[key] = (line + "\n", prose)
        order.append(key)
    if order != sorted(order):
        raise Unavailable("implementation-source rows are not ordered")
    return "".join(lines[:i - 1]), rows


def note_delta(before: str, after: str, feat: str, components: list[str], source_hash: str, *, require_updates=True):
    old_prefix, old = notes(before)
    new_prefix, new = notes(after)
    if old_prefix != new_prefix:
        raise Unavailable("SITE bytes outside implementation-source table changed")
    own = {(feat, component) for component in components}
    for key in set(old) | set(new):
        if key not in own and old.get(key) != new.get(key):
            raise Unavailable("undeclared/foreign implementation-source row changed")
    if require_updates:
        if not components:
            raise Unavailable("no declared source-bound note updates")
        for key in own:
            if key not in new or new[key] == old.get(key):
                raise Unavailable("each declared own note must be added or updated")
            prefix = "source_identity_sha256=" + source_hash + "; "
            if not new[key][1].startswith(prefix) or not new[key][1][len(prefix):].strip():
                raise Unavailable("note is not bound to current committed source identity")


def watched(path: str, scopes: list[str]) -> bool:
    return any(path == scope or path.startswith(scope + "/") for scope in scopes)


def trusted_module(name: str, file: str, budget=None):
    expected = ROOT / file
    if expected.is_symlink() or expected.resolve() != expected or not expected.is_file():
        raise Unavailable("trusted module path is not a regular local input")
    spec = importlib.util.spec_from_file_location(name, expected)
    if spec is None or spec.loader is None:
        raise Unavailable("trusted local module unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    # Parser loading is read-only; never leave new watched source artifacts.
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        if budget is None:
            spec.loader.exec_module(module)
        else:
            budget.admit_size(expected.stat().st_size)
            with expected.open("rb") as stream:
                code = stream.read(budget.max_bytes - budget.bytes + 1)
            budget.read(len(code))
            exec(compile(code, str(expected), "exec"), module.__dict__)
    finally:
        sys.dont_write_bytecode = previous
    if Path(module.__file__).resolve() != expected:
        raise Unavailable("trusted module identity differs")
    return module


class Budget:
    def __init__(self, seconds=MAX_SECONDS, max_bytes=MAX_BYTES, max_entries=MAX_ENTRIES):
        if (not math.isfinite(seconds) or not 0 < seconds <= MAX_SECONDS
                or type(max_bytes) is not int or not 0 < max_bytes <= MAX_BYTES
                or type(max_entries) is not int or not 0 < max_entries <= MAX_ENTRIES):
            raise Unavailable("fixed admission ceilings cannot be raised")
        self.start = time.monotonic()
        self.deadline = self.start + seconds
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self.bytes = 0
        self.entries = 0

    def remaining(self) -> float:
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise Unavailable("whole verification deadline exceeded")
        return left

    def read(self, count: int):
        self.remaining()
        self.bytes += count
        if self.bytes > self.max_bytes:
            raise Unavailable("combined input-byte ceiling exceeded")

    def admit_size(self, size: int):
        self.remaining()
        if size < 0 or size > self.max_bytes - self.bytes:
            raise Unavailable("object exceeds remaining input-byte allowance")


class Git:
    def __init__(self, repo: Path, budget: Budget):
        self.repo = repo
        self.budget = budget
        self.env = dict(os.environ, GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1")
        self.metadata = {}
        self.listings = {}
        self.contents = {}
        self.command(["--no-lazy-fetch", "--version"], guarded=False)
        for key in ("extensions.partialClone",):
            if self.command(["config", "--get", key], allowed=(0, 1)):
                raise Unavailable("partial-clone repository is unavailable")
        if self.command(["config", "--get-regexp", r"^remote\..*\.promisor$"], allowed=(0, 1)):
            raise Unavailable("promisor repository configuration is unavailable")
        pack = Path(text(self.command(["rev-parse", "--git-path", "objects/pack"])).strip())
        pack = pack if pack.is_absolute() else self.repo / pack
        if pack.exists():
            for entry in pack.iterdir():
                self.budget.remaining()
                if entry.name.endswith(".promisor"):
                    raise Unavailable("promisor object pack is unavailable")
        grafts = Path(text(self.command(["rev-parse", "--git-path", "info/grafts"])).strip())
        grafts = grafts if grafts.is_absolute() else self.repo / grafts
        if grafts.exists():
            raise Unavailable("history grafts are unavailable")
        if self.command(["for-each-ref", "--format=%(refname)", "refs/replace/"]):
            raise Unavailable("replacement refs are unavailable")
        if text(self.command(["rev-parse", "--is-shallow-repository"])).strip() != "false":
            raise Unavailable("unsupported shallow repository")
        self.object_format = text(self.command(["rev-parse", "--show-object-format"])).strip()
        if self.object_format not in ("sha1", "sha256"):
            raise Unavailable("unsupported Git object format")
        self.width = 40 if self.object_format == "sha1" else 64

    def command(self, args, *, data: bytes | None = None, allowed=(0,), guarded=True, return_code=False):
        self.budget.remaining()
        argv = ["git"] + (["--no-lazy-fetch", "-c", "core.quotePath=false"] if guarded else []) + list(args)
        proc = subprocess.Popen(argv, cwd=self.repo, env=self.env, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        sel = selectors.DefaultSelector()
        buffers = {"out": bytearray(), "err": bytearray()}
        sent = 0
        completed = False
        try:
            for pipe, label in ((proc.stdout, "out"), (proc.stderr, "err")):
                os.set_blocking(pipe.fileno(), False)
                sel.register(pipe, selectors.EVENT_READ, label)
            if data is not None:
                os.set_blocking(proc.stdin.fileno(), False)
                sel.register(proc.stdin, selectors.EVENT_WRITE, "in")
            while sel.get_map():
                for key, _ in sel.select(self.budget.remaining()):
                    if key.data == "in":
                        if sent < len(data):
                            sent += os.write(key.fd, data[sent:sent + 65536])
                        if sent == len(data):
                            sel.unregister(key.fileobj)
                            key.fileobj.close()
                        continue
                    value = os.read(key.fd, min(65536, self.budget.max_bytes - self.budget.bytes + 1))
                    if not value:
                        sel.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    self.budget.read(len(value))
                    buffers[key.data].extend(value)
            code = proc.wait(timeout=self.budget.remaining())
            if code not in allowed:
                raise Unavailable("local Git input could not be inspected")
            completed = True
            return (code, bytes(buffers["out"])) if return_code else bytes(buffers["out"])
        finally:
            sel.close()
            if not completed:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            proc.wait()
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()

    def oid(self, value: str):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{" + str(self.width) + r"}", value):
            raise Unavailable("invalid object identifier width or encoding")

    def commit(self, ref: str) -> str:
        value = text(self.command(["rev-parse", "--verify", "--end-of-options", ref + "^{commit}"])).strip()
        self.oid(value)
        return value

    def tree(self, ref: str) -> dict:
        if ref in self.listings:
            return self.listings[ref]
        rows = {}
        for raw in self.command(["ls-tree", "-r", "-z", "--full-tree", ref]).split(b"\0"):
            if not raw:
                continue
            try:
                fields, path = raw.split(b"\t", 1)
                mode, kind, oid = text(fields).split(" ")
                path = text(path)
            except (ValueError, UnicodeError) as exc:
                raise Unavailable("unsupported Git tree listing") from exc
            if not repo_path(path) or path in rows:
                raise Unavailable("unsupported or duplicate repository path")
            self.oid(oid)
            rows[path] = {"path": path, "mode": mode, "type": kind, "blob_oid": oid}
            self.budget.remaining()
        self.listings[ref] = rows
        return rows

    def sizes(self, oids):
        wanted = list(dict.fromkeys(oid for oid in oids if oid not in self.metadata))
        if wanted:
            raw = self.command(["cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
                               data=("\n".join(wanted) + "\n").encode("ascii"))
            lines = text(raw).splitlines()
            if len(lines) != len(wanted):
                raise Unavailable("incomplete Git object metadata")
            for oid, line in zip(wanted, lines):
                fields = line.split(" ")
                if len(fields) != 3 or fields[0] != oid or fields[1] != "blob" or not fields[2].isdigit():
                    raise Unavailable("missing or unsupported scoped object")
                self.metadata[oid] = int(fields[2])
        return self.metadata

    def blob(self, ref: str, path: str, *, optional=False) -> bytes | None:
        row = self.tree(ref).get(path)
        if row is None:
            if optional:
                return None
            raise Unavailable("required committed input is absent: " + path)
        if row["mode"] != "100644" or row["type"] != "blob":
            raise Unavailable("required input is not a regular mode100644 blob")
        size = self.sizes([row["blob_oid"]])[row["blob_oid"]]
        self.budget.admit_size(size)
        if row["blob_oid"] in self.contents:
            # Immutable-object reuse still debits every required logical read.
            self.budget.read(size)
            return self.contents[row["blob_oid"]]
        raw = self.command(["cat-file", "blob", row["blob_oid"]])
        if len(raw) != size:
            raise Unavailable("incomplete committed blob")
        self.contents[row["blob_oid"]] = raw
        return raw

    def blobs(self, ref: str, paths: list[str]) -> list[bytes]:
        """Complete bounded object batch; no authored subset or partial frames."""
        rows = [self.tree(ref).get(path) for path in paths]
        if any(row is None or row["mode"] != "100644" or row["type"] != "blob" for row in rows):
            raise Unavailable("required batch input is not a regular mode100644 blob")
        oids = [row["blob_oid"] for row in rows]
        sizes = self.sizes(oids)
        wanted = list(dict.fromkeys(oid for oid in oids if oid not in self.contents))
        # Include framing before materializing the batch and debit aliases/reuse.
        framing = sum(len(f"{oid} blob {sizes[oid]}\n".encode("ascii")) + 1 for oid in wanted)
        self.budget.admit_size(sum(sizes[oid] for oid in oids) + framing)
        if wanted:
            raw = self.command(["cat-file", "--batch"], data=("\n".join(wanted) + "\n").encode("ascii"))
            offset = 0
            pending = {}
            for oid in wanted:
                header = f"{oid} blob {sizes[oid]}\n".encode("ascii")
                end = offset + len(header)
                if raw[offset:end] != header:
                    raise Unavailable("incomplete or mismatched Git batch header")
                offset = end
                end = offset + sizes[oid]
                if end >= len(raw) or raw[end:end + 1] != b"\n":
                    raise Unavailable("incomplete Git batch content")
                pending[oid] = raw[offset:end]
                offset = end + 1
                self.budget.remaining()
            if offset != len(raw):
                raise Unavailable("unexpected trailing Git batch output")
            self.contents.update(pending)
        first = set(wanted)
        values = []
        for oid in oids:
            if oid in first:
                first.remove(oid)
            else:
                self.budget.read(sizes[oid])
            values.append(self.contents[oid])
        return values

    def manifest(self, ref: str, scopes: list[str]) -> list[dict]:
        rows = [row for path, row in self.tree(ref).items() if watched(path, scopes)]
        if len(rows) > self.budget.max_entries:
            raise Unavailable("manifest entry ceiling exceeded")
        if any(row["mode"] not in ("100644", "100755") or row["type"] != "blob" for row in rows):
            raise Unavailable("unsupported scoped entry mode or type")
        sizes = self.sizes([row["blob_oid"] for row in rows])
        return [{"path": row["path"], "mode": row["mode"], "blob_oid": row["blob_oid"],
                 "size_bytes": sizes[row["blob_oid"]]} for row in sorted(rows, key=lambda r: r["path"].encode("utf-8"))]


def json_record(raw: bytes, max_entries=MAX_ENTRIES) -> dict:
    if type(max_entries) is not int or not 0 < max_entries <= MAX_ENTRIES:
        raise Unavailable("record entry admission ceiling cannot be raised")
    entry_count = 0
    def pairs(items):
        nonlocal entry_count
        result = {}
        for key, value in items:
            if key in result:
                raise Unavailable("duplicate JSON record key")
            result[key] = value
        if set(result) == {"path", "mode", "blob_oid", "size_bytes"}:
            entry_count += 1
            if entry_count > max_entries:
                raise Unavailable("combined record entry ceiling exceeded")
        return result
    def floating(_):
        raise Unavailable("record floats/nonfinite numbers are unsupported")
    try:
        value = json.loads(text(raw), object_pairs_hook=pairs, parse_float=floating, parse_constant=floating)
    except (ValueError, RecursionError) as exc:
        raise Unavailable("malformed record JSON") from exc
    if not isinstance(value, dict) or set(value) != TOP_KEYS or type(value.get("version")) is not int or value["version"] != 1:
        raise Unavailable("unsupported record schema/version")
    if canonical(value) != raw:
        raise Unavailable("record bytes are not canonical")
    width = {"sha1": 40, "sha256": 64}.get(value["object_format"]) if isinstance(value["object_format"], str) else None
    if width is None or value["document_path"] != SITE:
        raise Unavailable("invalid format/document selector")
    def fields(obj, keys):
        if not isinstance(obj, dict) or set(obj) != set(keys):
            raise Unavailable("invalid nested record fields")
    def oid(obj):
        if not isinstance(obj, str) or not re.fullmatch("[0-9a-f]{" + str(width) + "}", obj):
            raise Unavailable("invalid nested OID")
    def sha(obj):
        if not isinstance(obj, str) or not re.fullmatch(r"[0-9a-f]{64}", obj):
            raise Unavailable("invalid SHA256 identity")
    def entries(items):
        if not isinstance(items, list) or len(items) > MAX_ENTRIES:
            raise Unavailable("invalid manifest array")
        paths = []
        for row in items:
            fields(row, ("path", "mode", "blob_oid", "size_bytes"))
            if (not repo_path(row["path"]) or row["mode"] not in ("100644", "100755")
                    or type(row["size_bytes"]) is not int or row["size_bytes"] < 0):
                raise Unavailable("invalid manifest entry")
            oid(row["blob_oid"])
            paths.append(row["path"])
        if paths != sorted(set(paths), key=lambda p: p.encode("utf-8")):
            raise Unavailable("manifest entries are duplicate or unordered")
    eligibility = value["eligibility"]
    fields(eligibility, ("kind", "feat_id", "spec_path", "spec_blob_oid", "component_ids"))
    if (eligibility["kind"] not in ("initial-bootstrap", "declared-note", "trunk-closeout-pending")
            or not isinstance(eligibility["feat_id"], str) or not FEAT_PATTERN.fullmatch(eligibility["feat_id"])
            or not repo_path(eligibility["spec_path"])):
        raise Unavailable("invalid eligibility selector")
    oid(eligibility["spec_blob_oid"])
    ids = eligibility["component_ids"]
    if not isinstance(ids, list) or any(not isinstance(x, str) or not COMPONENT_PATTERN.fullmatch(x) for x in ids) or ids != sorted(set(ids)):
        raise Unavailable("invalid component selectors")
    context = "implementation-source; trunk-closeout-pending" if eligibility["kind"] == "trunk-closeout-pending" else "implementation-source; rollout-pending"
    if value["context"] != context:
        raise Unavailable("invalid record context")
    policy = value["policy"]
    fields(policy, ("registry_path", "registry_blob_oid", "registry_mode", "registry_type", "document_path", "watch_paths", "policy_identity_sha256"))
    if (policy["registry_path"] != REGISTRY or policy["registry_mode"] != "100644" or policy["registry_type"] != "blob"
            or policy["document_path"] != SITE or not isinstance(policy["watch_paths"], list)
            or not policy["watch_paths"] or any(not repo_path(p) for p in policy["watch_paths"])
            or policy["watch_paths"] != sorted(set(policy["watch_paths"]), key=lambda p: p.encode("utf-8"))):
        raise Unavailable("invalid policy fields")
    oid(policy["registry_blob_oid"])
    sha(policy["policy_identity_sha256"])
    baseline = value["baseline"]
    fields(baseline, ("main_commit_oid", "source_entries", "source_identity_sha256", "document_body_sha256"))
    oid(baseline["main_commit_oid"])
    entries(baseline["source_entries"])
    entries(value["source_entries"])
    for obj in (baseline, value):
        sha(obj["source_identity_sha256"])
        sha(obj["document_body_sha256"])
    return value


class Snapshot:
    def __init__(self, repo=ROOT, *, seconds=MAX_SECONDS, max_bytes=MAX_BYTES, max_entries=MAX_ENTRIES):
        self.source_hash = None
        self.policy_hash = None
        self.body_hash = None
        self.route = None
        self.body_hashes = {}
        self.registries = {}
        self.budget = Budget(seconds, max_bytes, max_entries)
        self.git = Git(Path(repo), self.budget)
        self.audit = trusted_module("_source_snapshot_audit", "scripts/maintenance/docs_audit.py", self.budget)
        self.gate = trusted_module("_source_snapshot_gate", "scripts/gate/spec_gate.py", self.budget)

    def policy(self, policy_ref: str, source_ref: str, *, require_source_equal=True):
        raw = self.git.blob(policy_ref, REGISTRY)
        row = self.git.tree(policy_ref)[REGISTRY]
        source_row = self.git.tree(source_ref).get(REGISTRY)
        if require_source_equal and source_row != row:
            raise Unavailable("SOURCE registry blob/mode/type differs from trusted POLICY")
        registry = self.registry(row["blob_oid"], raw)
        if self.audit.classification_is_ambiguous(SITE, registry):
            raise Unavailable("ambiguous SITE watcher policy")
        cls, paths, _ = self.audit.classify(SITE, registry)
        if cls != "D" or not paths or any(not repo_path(p) for p in paths):
            raise Unavailable("unsupported SITE watcher policy")
        paths = sorted(set(paths), key=lambda p: p.encode("utf-8"))
        if watched(SITE, paths) or watched(RECORD, paths):
            raise Unavailable("SITE/sidecar cannot participate in the source hash")
        policy = {"registry_path": REGISTRY, "registry_blob_oid": row["blob_oid"],
                  "registry_mode": "100644", "registry_type": "blob", "document_path": SITE,
                  "watch_paths": paths}
        policy["policy_identity_sha256"] = digest(policy)
        self.policy_hash = policy["policy_identity_sha256"]
        return policy

    def registry(self, oid, raw):
        if oid not in self.registries:
            self.registries[oid] = self.audit.load_registry(text(raw))
        self.budget.remaining()
        return self.registries[oid]

    def body(self, ref: str) -> tuple[bytes, str]:
        raw = self.git.blob(ref, SITE)
        oid = self.git.tree(ref)[SITE]["blob_oid"]
        if oid not in self.body_hashes:
            normalized = self.audit._without_marker(text(raw)).encode("utf-8", "strict")
            self.body_hashes[oid] = hashlib.sha256(normalized).hexdigest()
        self.budget.remaining()
        return raw, self.body_hashes[oid]

    def source_identity(self, entries, policy):
        return digest({"object_format": self.git.object_format,
                       "policy_identity_sha256": policy["policy_identity_sha256"], "source_entries": entries})

    def admitted_manifests(self, source, baseline, scopes):
        self.budget.entries = sum(watched(path, scopes) for ref in (source, baseline) for path in self.git.tree(ref))
        if self.budget.entries > self.budget.max_entries:
            raise Unavailable("combined current/baseline entry ceiling exceeded")
        return self.git.manifest(source, scopes), self.git.manifest(baseline, scopes)

    def spec_binding(self, baseline, policy, source, path, feat):
        if not repo_path(path) or not path.startswith("docs/superpowers/specs/") or not path.endswith(".md"):
            raise Unavailable("unsupported approved spec path")
        rows = [self.git.tree(ref).get(path) for ref in (baseline, policy, source)]
        if any(row is None or row["mode"] != "100644" or row["type"] != "blob" for row in rows) or rows[0] != rows[1] or rows[0] != rows[2]:
            raise Unavailable("approved spec is unavailable or changed in baseline/POLICY/SOURCE")
        values = [self.git.blob(ref, path) for ref in (baseline, policy, source)]
        fm = self.gate.frontmatter(text(values[0]))
        if fm.get("status") != "approved" or fm.get("feat_id") != feat or fm.get("_duplicate_keys") or fm.get("_tab_indented"):
            raise Unavailable("approved immutable FEAT/spec binding failed")
        candidates = [candidate for candidate in self.git.tree(policy)
                      if candidate != path and candidate.startswith("docs/superpowers/specs/") and candidate.endswith(".md")]
        for raw in self.git.blobs(policy, candidates):
            newer = self.gate.frontmatter(text(raw))
            if newer.get("status") == "approved" and newer.get("feat_id") == feat and newer.get("supersedes") == path:
                raise Unavailable("bound approved spec has been superseded in trusted POLICY")
            self.budget.remaining()
        return rows[0]["blob_oid"], fm

    def gate_note_scope(self, baseline_ref, policy_ref, source_ref, feat, spec_path, *, only_changed_source=False):
        baseline, current, source = (self.git.commit(ref) for ref in (baseline_ref, policy_ref, source_ref))
        policy = self.policy(current, source)
        _, fm = self.spec_binding(baseline, current, source, spec_path, feat)
        old_raw, _ = self.body(baseline)
        new_raw, self.body_hash = self.body(source)
        ids = declaration(fm, text(old_raw))
        entries, baseline_entries = self.admitted_manifests(source, baseline, policy["watch_paths"])
        self.source_hash = self.source_identity(entries, policy)
        if only_changed_source and entries == baseline_entries:
            self.budget.remaining()
            return
        note_delta(text(old_raw), text(new_raw), feat, ids, self.source_hash)
        self.budget.remaining()

    def verify(self, policy_ref="origin/main", source_ref="HEAD"):
        if self.terminal(policy_ref, source_ref):
            return self.verdict()
        source = self.git.commit(source_ref)
        raw = self.git.blob(source, RECORD)
        record = json_record(raw, self.budget.max_entries)
        expected = self.build(policy_ref, source_ref, record)
        if expected != record:
            raise Unavailable("record differs from independently derived committed identity")
        self.budget.remaining()
        return self.verdict()

    def changes(self, baseline, source) -> list[str]:
        raw = self.git.command(["diff", "--no-ext-diff", "--name-only", "--no-renames", "-z", baseline, source])
        return [text(path) for path in raw.split(b"\0") if path]

    def dirty_site(self):
        for args in (["diff", "--no-ext-diff", "--quiet", "--", SITE],
                     ["diff", "--no-ext-diff", "--cached", "--quiet", "HEAD", "--", SITE]):
            code, _ = self.git.command(args, allowed=(0, 1), return_code=True)
            if code:
                raise Unavailable("dirty SITE index or worktree makes identity unavailable")

    def selected_binding(self, source):
        branch = text(self.git.command(["symbolic-ref", "--quiet", "--short", "HEAD"], allowed=(0, 1))).strip()
        matched = self.gate.BRANCH.fullmatch(branch)
        if matched is None or self.git.commit("HEAD") != source:
            raise Unavailable("ordinary production requires its actual named feature branch/source")
        feat = matched.group(2).upper()
        selected = []
        plans = [path for path in self.git.tree(source)
                 if path.startswith("docs/superpowers/plans/") and path.endswith(".md")]
        for value in self.git.blobs(source, plans):
            raw = text(value)
            fm = self.gate.frontmatter(raw)
            if fm.get("branch") == branch:
                selected.append((fm, raw))
            self.budget.remaining()
        if len(selected) != 1:
            raise Unavailable("one committed active plan must bind the actual branch")
        fm, raw = selected[0]
        if (fm.get("status") != "ready" or fm.get("feat_id") != feat or fm.get("_duplicate_keys")
                or fm.get("_tab_indented") or self.gate.validate_plan_body(raw, "selected plan")):
            raise Unavailable("selected committed plan is not a valid ready binding")
        return feat, fm.get("spec")

    def marker_bytes(self, raw):
        lines = text(raw).split("\n")
        return [self.audit._marker_body(lines, i) for i, _ in self.audit.find_markers(lines)]

    def terminal(self, policy_ref="origin/main", source_ref="HEAD") -> bool:
        """Original marker predicates and source/body drift; records have no role."""
        self.dirty_site()
        current, source = self.git.commit(policy_ref), self.git.commit(source_ref)
        policy = self.policy(current, source, require_source_equal=False)
        raw = self.git.blob(source, SITE)
        lines = text(raw).split("\n")
        markers = self.audit.find_markers(lines)
        if len(markers) != 1 or self.audit.check_marker_shape(SITE, lines):
            return False
        index, info = markers[0]
        if (info.get("legacy") or info.get("depth") != "verified" or not info.get("sha")
                or info.get("date") in (None, "unknown")
                or self.audit.check_marker_dates(SITE, info)
                or self.audit.check_marker_fields(SITE, info, self.audit._marker_body(lines, index))):
            return False
        try:
            against = self.git.commit(info["sha"])
        except Unavailable:
            return False
        code, _ = self.git.command(["merge-base", "--is-ancestor", against, current], allowed=(0, 1), return_code=True)
        if code or self.git.blob(against, SITE, optional=True) is None:
            return False
        registry = self.registry(self.git.tree(current)[REGISTRY]["blob_oid"], self.git.blob(current, REGISTRY))
        documents = frozenset(self.audit.document_set(set(self.git.tree(source)), registry))
        # The whole range keeps both sides of cross-directory pure renames.
        history = text(self.git.command(["log", "--no-ext-diff", "--format=%H%x09%s", "--name-status", "-M",
                                        "--diff-filter=AMDRT", f"{against}..{source}", "--"]))
        if self.audit.drift_commits(history, policy["watch_paths"], documents):
            return False
        # Source drift already refuses this conjunction. Normalize complete
        # bodies only when the original source question could be terminal.
        self.body_hash = self.body(source)[1]
        if self.body(against)[1] != self.body_hash:
            return False
        entries, old_entries = self.admitted_manifests(source, against, policy["watch_paths"])
        self.source_hash = self.source_identity(entries, policy)
        self.route = "terminal-ordinary"
        self.budget.remaining()
        return True

    def eligibility(self, baseline, current, source, policy, changed, old_body_raw, body_raw, record):
        scopes = policy["watch_paths"]
        scoped = {path for path in changed if watched(path, scopes)}
        before_tree, after_tree = self.git.tree(baseline), self.git.tree(source)
        bootstrap = (MODULE not in before_tree and MODULE in after_tree and scoped and scoped <= INITIAL_FILES
                     and body_raw == old_body_raw and (baseline != current or MODULE not in self.git.tree(current)))
        doc_pending = (not scoped and set(changed) and set(changed) <= {SITE, RECORD}
                       and self.marker_bytes(old_body_raw) == self.marker_bytes(body_raw))
        if doc_pending:
            for path in changed:
                row = after_tree.get(path)
                if row is None or row["mode"] != "100644" or row["type"] != "blob":
                    doc_pending = False
                prior = before_tree.get(path)
                if prior is not None and (prior["mode"] != "100644" or prior["type"] != "blob"):
                    doc_pending = False
            if self.git.manifest(source, scopes) != self.git.manifest(baseline, scopes):
                doc_pending = False
        if bootstrap:
            kind, feat, path = "initial-bootstrap", "FEAT-CICD-001", SPEC
        elif doc_pending:
            kind, feat, path = "trunk-closeout-pending", "FEAT-CICD-001", SPEC
        else:
            kind = "declared-note"
            if record is None:
                feat, path = self.selected_binding(source)
            else:
                feat, path = record["eligibility"]["feat_id"], record["eligibility"]["spec_path"]
                if baseline == current:
                    selected = self.selected_binding(source)
                    if selected != (feat, path):
                        raise Unavailable("record binding differs from actual active branch plan")
        spec_oid, fm = self.spec_binding(baseline, current, source, path, feat)
        components = declaration(fm, text(old_body_raw)) if kind == "declared-note" else []
        if kind == "declared-note":
            note_delta(text(old_body_raw), text(body_raw), feat, components, self.source_hash)
        if record is not None and record["eligibility"]["kind"] != kind:
            raise Unavailable("authored eligibility kind differs from independently measured route")
        return {"kind": kind, "feat_id": feat, "spec_path": path, "spec_blob_oid": spec_oid,
                "component_ids": components}

    def build(self, policy_ref="origin/main", source_ref="HEAD", record=None):
        self.dirty_site()
        current = self.git.commit(policy_ref)
        source = self.git.commit(source_ref)
        baseline = current if record is None else record.get("baseline", {}).get("main_commit_oid")
        self.git.oid(baseline)
        baseline = self.git.commit(baseline)
        ancestry, _ = self.git.command(["merge-base", "--is-ancestor", baseline, current], allowed=(0, 1), return_code=True)
        if ancestry != 0:
            raise Unavailable("baseline is not available on current trusted main ancestry")
        policy = self.policy(current, source)
        scopes = policy["watch_paths"]
        entries, old_entries = self.admitted_manifests(source, baseline, scopes)
        self.source_hash = self.source_identity(entries, policy)
        body_raw, self.body_hash = self.body(source)
        old_body_raw, old_body_hash = self.body(baseline)
        old_hash = self.source_identity(old_entries, policy)
        if baseline != current:
            if self.git.manifest(current, scopes) != entries or self.body(current)[1] != self.body_hash:
                raise Unavailable("historical record does not equal complete current MAIN source/body")
        changed = self.changes(baseline, source)
        eligibility = self.eligibility(baseline, current, source, policy, changed, old_body_raw, body_raw, record)
        self.route = eligibility["kind"]
        context = "implementation-source; trunk-closeout-pending" if self.route == "trunk-closeout-pending" else "implementation-source; rollout-pending"
        result = {"version": 1, "context": context,
                  "object_format": self.git.object_format, "eligibility": eligibility, "policy": policy,
                  "baseline": {"main_commit_oid": baseline, "source_entries": old_entries,
                               "source_identity_sha256": old_hash, "document_body_sha256": old_body_hash},
                  "source_entries": entries, "source_identity_sha256": self.source_hash,
                  "document_path": SITE, "document_body_sha256": self.body_hash}
        self.budget.remaining()
        return result

    def verdict(self, status="identity-matched", reason=None):
        context = CONTEXT.replace("rollout pending", "trunk documentation close-out pending") if self.route == "trunk-closeout-pending" else CONTEXT
        if self.route == "terminal-ordinary":
            context = "ordinary verified current-trunk marker; source and body drift zero"
        return {"status": status, "success": status == "identity-matched", "eligible_route": self.route if status == "identity-matched" else None,
                "entry_count": self.budget.entries, "counted_bytes": self.budget.bytes,
                "source_identity_sha256": self.source_hash, "policy_identity_sha256": self.policy_hash,
                "document_body_sha256": self.body_hash, "elapsed_seconds": time.monotonic() - self.budget.start,
                "context": context if status == "identity-matched" else "unverified", "reason": reason}


def emit(value, budget=None):
    """A verdict cannot block past the shared deadline on an unread pipe."""
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    fd = sys.stdout.fileno()
    previous = os.get_blocking(fd)
    selector = selectors.DefaultSelector()
    try:
        os.set_blocking(fd, False)
        sent = 0
        while sent < len(raw):
            if budget is not None:
                budget.remaining()
            try:
                sent += os.write(fd, raw[sent:])
            except BlockingIOError:
                if not selector.get_map():
                    selector.register(fd, selectors.EVENT_WRITE)
                if not selector.select(budget.remaining() if budget is not None else 0):
                    raise Unavailable("verdict output deadline exceeded")
        if budget is not None:
            budget.remaining()
    finally:
        selector.close()
        os.set_blocking(fd, previous)


def install(record: bytes, budget: Budget, complete):
    destination = ROOT / RECORD
    for path in (destination, destination.parent, destination.parent.parent):
        if path.is_symlink():
            raise Unavailable("sidecar installation path is a symlink")
    budget.admit_size(len(record))
    budget.read(len(record))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    backup = None
    installed = False
    try:
        if destination.exists():
            if not destination.is_file() or destination.stat().st_mode & 0o111:
                raise Unavailable("existing sidecar is not a regular mode100644 file")
            budget.admit_size(destination.stat().st_size)
            with destination.open("rb") as previous:
                old = previous.read(budget.max_bytes - budget.bytes + 1)
            budget.read(len(old))
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".source-snapshot-backup-", delete=False) as stream:
                backup = Path(stream.name)
                stream.write(old)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(backup, 0o644)
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".source-snapshot-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(record)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        budget.remaining()
        os.replace(temporary, destination)
        temporary = None
        installed = True
        complete()
    except BaseException:
        if installed:
            if backup is None:
                destination.unlink(missing_ok=True)
            else:
                os.replace(backup, destination)
                backup = None
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if backup is not None:
            backup.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("produce", "verify"))
    parser.add_argument("--policy-ref", default="origin/main")
    parser.add_argument("--source-ref", default="HEAD")
    parser.add_argument("--output", default=RECORD)
    parser.add_argument("--record", default=RECORD)
    parser.add_argument("--max-seconds", type=float, default=MAX_SECONDS)
    parser.add_argument("--max-input-bytes", type=int, default=MAX_BYTES)
    parser.add_argument("--max-entries", type=int, default=MAX_ENTRIES)
    args = parser.parse_args(argv)
    snapshot = None
    try:
        if args.output != RECORD or args.record != RECORD:
            raise Unavailable("only the fixed committed sidecar path is eligible")
        snapshot = Snapshot.__new__(Snapshot)
        snapshot.__init__(seconds=args.max_seconds, max_bytes=args.max_input_bytes, max_entries=args.max_entries)
        if args.action == "produce":
            value = snapshot.build(args.policy_ref, args.source_ref)
            serialized = canonical(value)
            json_record(serialized, snapshot.budget.max_entries)
            install(serialized, snapshot.budget, lambda: emit(snapshot.verdict(), snapshot.budget))
        else:
            snapshot.verify(args.policy_ref, args.source_ref)
            emit(snapshot.verdict(), snapshot.budget)
        return 0
    except (Unavailable, OSError, ValueError, subprocess.SubprocessError, UnicodeError, RecursionError) as exc:
        result = snapshot.verdict("unverified", str(exc)) if snapshot is not None and hasattr(snapshot, "budget") else {
            "status": "unverified", "success": False, "eligible_route": None, "entry_count": 0,
            "counted_bytes": 0, "source_identity_sha256": None, "policy_identity_sha256": None,
            "document_body_sha256": None, "elapsed_seconds": 0.0, "context": "unverified", "reason": str(exc)}
        try:
            emit(result)
        except (OSError, Unavailable):
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
