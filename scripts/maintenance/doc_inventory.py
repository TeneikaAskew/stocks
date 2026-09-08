#!/usr/bin/env python3
"""Deterministic inventory of what the repo declares and what GCP runs.

Why this exists
---------------
The monthly architecture-doc refresh (`.github/workflows/refresh-architecture-docs.yml`)
asked an LLM to count Cloud Run Jobs, schedulers, tables and API routes by
reading `gcp/deploy.sh`, `gcp/schema.sql` and `platform/api` itself. The
2026-09-02 regeneration named 4 of the 67 jobs `deploy.sh` declares, and the
2026-05-16 hand-written deep-dive had drifted to 34 of 76 live jobs. Counting
is not a language-model task. This module does the counting once, from the
files and from `gcloud`, and renders the tables the docs embed between
`<!-- inventory:<name>:start -->` / `<!-- inventory:<name>:end -->` markers.

Three sources, kept separate on purpose:

* **repo** — parsed from `gcp/deploy.sh`, `gcp/schema.sql`, `platform/api`,
  `.github/workflows`, `gcp/cloudbuild`, `scripts/discord/register_commands.py`.
* **live** — read from `gcloud` (see `live_snapshot`). Never cached silently:
  a failed read raises (CLAUDE.md Rule 3.7).
* **reconcile** — the delta between the two, which is what an operator needs
  to see: jobs that exist live but no `deploy_*` function creates, schedulers
  in `deploy.sh` that were never applied, targets that fire into nothing.

Usage
-----
    python -m scripts.maintenance.doc_inventory --json                 # repo only
    python -m scripts.maintenance.doc_inventory --live --json          # repo + live + reconcile
    python -m scripts.maintenance.doc_inventory --live --write-snapshot refresh-inputs/live.json
    python -m scripts.maintenance.doc_inventory --snapshot live.json --markdown jobs
    python -m scripts.maintenance.doc_inventory --markdown tables

Sections for --markdown: jobs, schedulers, tables, routes, services, reconcile.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import pathlib
import re
import subprocess
import sys
from typing import Any

REGION = "us-east1"
PROJECT = "adept-mountain-474619-d4"
REPO = pathlib.Path(__file__).resolve().parents[2]

# Cloud Run Job defaults when a flag is absent from the deploy function.
CLOUD_RUN_DEFAULT_TASK_TIMEOUT = "600"
CLOUD_RUN_DEFAULT_MAX_RETRIES = "3"
CLOUD_RUN_DEFAULT_MEMORY = "512Mi"
CLOUD_RUN_DEFAULT_CPU = "1"

# gcp/cloudbuild/*.yaml files that do not carry a `# Trigger:` header.
CLOUDBUILD_TRIGGER_NAMES = {
    "apply-schema-cloudbuild.yaml": "apply-schema-on-change",
}

MARKER_START = "<!-- inventory:{name}:start -->"
MARKER_END = "<!-- inventory:{name}:end -->"


# ─────────────────────────────────────────────────────────────────────────────
# repo: gcp/deploy.sh
# ─────────────────────────────────────────────────────────────────────────────

def _strip_comments(text: str) -> str:
    """Drop whole-line comments. A word in a comment is not a job name.

    docs/product/05 recorded the failure mode: the word `leaves` in the prose
    comment `gcloud run jobs update leaves omitted flags untouched` was
    counted as the 68th job.
    """
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


def _functions(text: str) -> dict[str, tuple[int, str]]:
    """Map bash function name -> (1-based start line, body text).

    The body runs from the `name() {` line to the first line that is exactly
    `}` at column 0, which is how every function in deploy.sh is closed.
    """
    lines = text.splitlines()
    out: dict[str, tuple[int, str]] = {}
    i = 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\(\)\s*\{", lines[i])
        if m:
            start = i
            j = i + 1
            while j < len(lines) and lines[j] != "}":
                j += 1
            out[m.group(1)] = (start + 1, "\n".join(lines[start : j + 1]))
            i = j + 1
        else:
            i += 1
    return out


def _flag(body: str, name: str) -> str | None:
    """First value of `--name VALUE` / `--name=VALUE` / `--name "VALUE"` in body."""
    m = re.search(rf"--{name}(?:[= ]+)(\"[^\"]*\"|'[^']*'|[^\s\\]+)", body)
    if not m:
        return None
    return m.group(1).strip("\"'")


def _resolve_locals(body: str, value: str) -> str:
    """Substitute `${var}` / `$var` with the function's own `local var="..."`.

    One level only, which is what deploy.sh uses (`local research_image=
    "${IMAGE}:research"`, `local default_args="-m,..."`). `${IMAGE}` and the
    other globals are left as-is so the reader sees the placeholder.
    """
    for m in re.finditer(r'local (\w+)="([^"]*)"', body):
        var, val = m.group(1), m.group(2)
        value = value.replace("${" + var + "}", val).replace("$" + var, val)
    return value


def deploy_jobs(root: pathlib.Path = REPO) -> list[dict[str, Any]]:
    """Every Cloud Run Job `gcp/deploy.sh` creates, with its config.

    One row per distinct job name. Config is read from the enclosing
    `deploy_*` function body (so flags built into a `common_flags=(...)` bash
    array are seen too), first occurrence wins (the `create` branch).
    """
    raw = (root / "gcp/deploy.sh").read_text()
    text = _strip_comments(raw)
    raw_lines = raw.splitlines()
    funcs = _functions(text)
    # Map job name -> function via the create/deploy line.
    rows: dict[str, dict[str, Any]] = {}
    for fname, (start, body) in funcs.items():
        for m in re.finditer(r"gcloud run jobs (?:create|deploy) ([a-z0-9][a-z0-9-]*)", body):
            job = m.group(1)
            if job in rows:
                continue
            image = _resolve_locals(body, _flag(body, "image") or "")
            image_tag = "main"
            if ":" in image.split("/")[-1]:
                image_tag = image.split(":", 1)[1].strip("}\"")
            command = _resolve_locals(body, _flag(body, "command") or "")
            args = _resolve_locals(body, _flag(body, "args") or "")
            # locate the create line in the ORIGINAL file for a stable file:line
            line_no = next(
                (i + 1 for i, l in enumerate(raw_lines)
                 if re.search(rf"gcloud run jobs (?:create|deploy) {re.escape(job)}\b", l)
                 and not l.lstrip().startswith("#")),
                start,
            )
            rows[job] = {
                "name": job,
                "function": fname,
                "line": line_no,
                "memory": _flag(body, "memory") or CLOUD_RUN_DEFAULT_MEMORY,
                "cpu": _flag(body, "cpu") or CLOUD_RUN_DEFAULT_CPU,
                "task_timeout": _flag(body, "task-timeout") or CLOUD_RUN_DEFAULT_TASK_TIMEOUT,
                "max_retries": _flag(body, "max-retries") or CLOUD_RUN_DEFAULT_MAX_RETRIES,
                "tasks": _flag(body, "tasks") or "1",
                "image": image_tag,
                "command": command.replace(",", " "),
                "args": args.replace(",", " "),
                "uses_secrets": "--set-secrets" in body or "DB_SECRET_FLAG" in body,
                "service_account": _flag(body, "service-account") or "",
                "timeout_defaulted": _flag(body, "task-timeout") is None,
                "retries_defaulted": _flag(body, "max-retries") is None,
            }
    return sorted(rows.values(), key=lambda r: r["name"])


def _expand_loop_vars(text: str) -> str:
    """Expand `for X in a b c; do ... done` loops that contain _schedule calls.

    deploy.sh writes the hourly news loops as
        for h in 08 09 ...; do _schedule "news-sentiment-${h}00" "0 ${h} * * 1-5" "..."; done
    and the doc must list every entry the loop creates.
    """
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        m = re.match(r"^\s*for (\w+) in ([^;]+); do\s*$", lines[i])
        if m and i + 1 < len(lines):
            var, values = m.group(1), m.group(2).split()
            j = i + 1
            block: list[str] = []
            while j < len(lines) and not re.match(r"^\s*done\b", lines[j]):
                block.append(lines[j])
                j += 1
            if any("_schedule" in b for b in block):
                for v in values:
                    for b in block:
                        out.append(b.replace("${" + var + "}", v).replace("$" + var, v))
            else:
                out.extend(block)
            i = j + 1
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)


def _service_of(uri: str) -> str:
    """The Cloud Run service a scheduler URI addresses, or "" for job / other URIs."""
    m = re.search(r"/services/([^?/:]+)", uri or "")
    return m.group(1) if m else ""


def deploy_schedulers(root: pathlib.Path = REPO) -> list[dict[str, Any]]:
    """Every Cloud Scheduler entry `gcp/deploy.sh` creates.

    Covers the `_schedule*` helpers (name, cron, target job, extra args) and
    raw `gcloud scheduler jobs create http "<name>"` calls (the failure-notifier
    reconciler, which targets a service URL rather than a job).
    """
    raw = (root / "gcp/deploy.sh").read_text()
    # Join backslash-continued lines first: `_schedule_with_args "orb-15m-alert" ... \`
    # carries its extra args on the next line.
    text = _expand_loop_vars(_strip_comments(raw)).replace("\\\n", " ")
    rows: dict[str, dict[str, Any]] = {}
    # `if _schedule_verified "name" "cron" "job"; then` (the consolidated
    # sec-filings / news entries, #1004) is a declaration too.
    helper = re.compile(
        r'^\s*(?:if\s+!?\s*)?(_schedule\w*)\s+"([^"]+)"\s+"([^"]+)"\s+"([^"]+)"(.*)$', re.M
    )
    for m in helper.finditer(text):
        name = m.group(2)
        extra = m.group(5).strip()
        args = " ".join(re.findall(r'"([^"]*)"', extra)) if extra else ""
        row = {
            "name": name, "cron": m.group(3), "target_job": m.group(4),
            "target_service": "", "target_uri": "",
            "helper": m.group(1), "args": args, "time_zone": "America/New_York",
        }
        if m.group(1) == "_schedule_min_instances":
            # `_schedule_min_instances NAME CRON SERVICE COUNT` PATCHes a Cloud Run
            # *service*'s minInstanceCount (the discord-interactions warm window,
            # #1004); the third argument is a service, not a job.
            count = re.match(r"(\d+)", extra)
            row.update({
                "target_job": "", "target_service": m.group(4),
                "target_uri": (f"https://run.googleapis.com/v2/projects/${{PROJECT_ID}}/locations/${{REGION}}"
                               f"/services/{m.group(4)}?updateMask=template.scaling.minInstanceCount"),
                "args": f"minInstanceCount={count.group(1)}" if count else "minInstanceCount",
            })
        rows.setdefault(name, row)
    # A block ends at its own `--quiet`, a blank line, or the next create,
    # whichever comes first: strat-enrich-daily keeps its flags (and its --quiet) in a bash array
    # ABOVE the create line, so an unbounded `[\s\S]*?--quiet` swallowed the
    # next declaration (backfill-indicators-weekly) and its cron.
    raw_create = re.compile(
        r'gcloud scheduler jobs create http "([^"]+)"'
        r'((?:(?!gcloud scheduler jobs create http)[\s\S])*?)'
        r'(?:--quiet|\n[ \t]*\n|(?=gcloud scheduler jobs create http))'
    )
    for m in raw_create.finditer(text):
        name = m.group(1)
        if name in rows or "$" in name:  # "${NAME}" inside a helper definition
            continue
        block = m.group(2)
        # Flags may live in a bash array declared just above the create line
        # (strat-enrich-daily uses `_enrich_common=(...)`), so fall back to the
        # preceding 40 lines when the block itself carries no --schedule.
        before = "\n".join(text[: m.start()].splitlines()[-40:])
        scope = block if "--schedule" in block else before + "\n" + block
        crons = [c for c in re.findall(r'--schedule "([^"]+)"', scope) if "$" not in c]
        cron = crons[-1] if crons else ""
        jobs_ = [j for j in re.findall(r'_job_uri "([^"]+)"', scope) if "$" not in j]
        jm = jobs_[-1] if jobs_ else ""
        uris = [u for u in re.findall(r'--uri "([^"]+)"', scope) if "_job_uri" not in u]
        uri = "" if jm else (uris[-1] if uris else "")
        # Overrides come from the block's own --message-body; a `${_BODY}`
        # reference is resolved from the single-quoted `local _BODY='{...}'`
        # above it. Scanning `before` wholesale picked up the previous
        # declaration's body for any create that carried none of its own.
        body_scope = scope
        for var in re.findall(r'"\$\{(\w+)\}"', scope):
            for d in re.findall(r"local %s='([^']*)'" % re.escape(var), before):
                body_scope += "\n" + d
        env = re.findall(r'\{"name":"([A-Z_]+)","value":"([^"]*)"\}', body_scope)
        arr = re.findall(r'"args":\[([^\]]*)\]', body_scope)
        args = " ".join(f"{k}={v}" for k, v in env)
        if arr:
            args = (args + " " + " ".join(a.strip('"') for a in arr[-1].split(","))).strip()
        rows[name] = {
            "name": name, "cron": cron, "target_job": jm, "target_service": _service_of(uri),
            "target_uri": uri, "helper": "raw", "args": args, "time_zone": "America/New_York",
        }
    return sorted(rows.values(), key=lambda r: r["name"])


def deploy_targets(root: pathlib.Path = REPO) -> list[str]:
    """The `./gcp/deploy.sh <target>` dispatch names (the `case` at the end)."""
    raw = (root / "gcp/deploy.sh").read_text()
    names = re.findall(r"^\s{4}([a-z][a-z0-9-]*)\)\s", raw, re.M)
    return sorted(set(names))


# ─────────────────────────────────────────────────────────────────────────────
# repo: gcp/schema.sql
# ─────────────────────────────────────────────────────────────────────────────

def schema_tables(root: pathlib.Path = REPO) -> dict[str, list[dict[str, Any]]]:
    """Tables, materialized views and views `gcp/schema.sql` creates.

    The table regex is byte-for-byte the one the refresh workflow's gate uses
    (`grep -oE '^CREATE TABLE( IF NOT EXISTS)? [a-zA-Z0-9_]+'`), so the two
    can never disagree on the count.
    """
    text = (root / "gcp/schema.sql").read_text()
    lines = text.splitlines()
    tables: dict[str, dict[str, Any]] = {}
    for i, l in enumerate(lines):
        m = re.match(r"^CREATE TABLE(?: IF NOT EXISTS)? ([a-zA-Z0-9_]+)", l)
        if m and m.group(1) not in tables:
            # partition child?  "... PARTITION OF parent"
            window = "\n".join(lines[i : i + 3])
            pm = re.search(r"PARTITION OF ([a-zA-Z0-9_]+)", window)
            tables[m.group(1)] = {
                "name": m.group(1), "line": i + 1,
                "partition_of": pm.group(1) if pm else "",
            }
    mviews = [
        {"name": m.group(1), "line": i + 1}
        for i, l in enumerate(lines)
        for m in [re.match(r"^CREATE MATERIALIZED VIEW(?: IF NOT EXISTS)? ([a-zA-Z0-9_]+)", l)]
        if m
    ]
    views = [
        {"name": m.group(1), "line": i + 1}
        for i, l in enumerate(lines)
        for m in [re.match(r"^CREATE (?:OR REPLACE )?VIEW(?: IF NOT EXISTS)? ([a-zA-Z0-9_]+)", l)]
        if m
    ]
    return {
        "tables": sorted(tables.values(), key=lambda r: r["name"]),
        "materialized_views": sorted(mviews, key=lambda r: r["name"]),
        "views": sorted(views, key=lambda r: r["name"]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# repo: platform/api
# ─────────────────────────────────────────────────────────────────────────────

_HTTP = {"get", "post", "put", "delete", "patch"}


def _conditionally_registered(tree: ast.AST) -> set[str]:
    """Handlers defined under a `dist`-existence guard.

    The SPA fallback is mounted only when platform/dist is present, which the
    production image never contains, so it is not part of the live surface.
    """
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        src = ast.dump(node.test)
        if "dist" not in src.lower():
            continue
        for sub in ast.walk(node):
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.add(sub.name)
    return out


def _router_prefix(tree: ast.Module) -> str:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "APIRouter":
            for kw in node.keywords:
                if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                    return str(kw.value.value)
    return ""


def api_routes(root: pathlib.Path = REPO) -> list[dict[str, Any]]:
    """Every HTTP route in `platform/api/main.py` and `platform/api/routers/*.py`.

    AST-based so decorators whose path sits on a later line are seen. The
    `main.py` catch-all `/{full_path:path}` is included and tagged so a doc
    can explain it is dead since the SPA moved out (#957).
    """
    api = root / "platform/api"
    files = [api / "main.py"] + sorted((api / "routers").glob("*.py"))
    rows: list[dict[str, Any]] = []
    for f in files:
        if f.name == "__init__.py":
            continue
        tree = ast.parse(f.read_text())
        prefix = _router_prefix(tree) if f.name != "main.py" else ""
        # Routes registered inside `if _dist.is_dir():` are the SPA fallback,
        # and platform/Dockerfile says plainly that no dist/ is copied into the
        # production image -- so walking the whole AST published a route that
        # never registers. (Codex, PR #1009.)
        inactive = _conditionally_registered(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name in inactive:
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                    continue
                if dec.func.attr not in _HTTP:
                    continue
                owner = getattr(dec.func.value, "id", "")
                if owner not in ("router", "app"):
                    continue
                path = dec.args[0].value if dec.args and isinstance(dec.args[0], ast.Constant) else ""
                doc = ast.get_docstring(node) or ""
                rows.append({
                    "method": dec.func.attr.upper(),
                    "path": prefix + str(path),
                    "file": str(f.relative_to(root)),
                    "line": dec.lineno,
                    "handler": node.name,
                    "summary": doc.strip().splitlines()[0] if doc.strip() else "",
                    "router": f.stem if f.name != "main.py" else "main",
                })
    return sorted(rows, key=lambda r: (r["path"], r["method"]))


# ─────────────────────────────────────────────────────────────────────────────
# repo: workflows, cloud build, discord
# ─────────────────────────────────────────────────────────────────────────────

def workflows(root: pathlib.Path = REPO) -> list[dict[str, Any]]:
    out = []
    for f in sorted((root / ".github/workflows").glob("*.yml*")):
        text = f.read_text()
        name = re.search(r"^name:\s*(.+)$", text, re.M)
        triggers = []
        on = re.search(r"^on:\s*\n((?:[ \t]+.*\n)+)", text, re.M)
        if on:
            triggers = re.findall(r"^\s{2}([a-z_]+):", on.group(1), re.M)
        elif re.search(r"^on:\s*\[?([a-z_, ]+)", text, re.M):
            triggers = [t.strip() for t in re.search(r"^on:\s*\[?([a-z_, ]+)", text, re.M).group(1).split(",")]
        out.append({
            "file": f.name,
            "name": name.group(1).strip() if name else f.name,
            "disabled": f.name.endswith(".disabled"),
            "triggers": triggers,
        })
    return out


def cloudbuild_triggers(root: pathlib.Path = REPO) -> list[dict[str, Any]]:
    out = []
    for f in sorted((root / "gcp/cloudbuild").glob("*.yaml")):
        text = f.read_text()
        m = re.search(r"^#\s*Trigger:\s*([a-z0-9-]+)", text, re.M)
        out.append({
            "file": f.name,
            "trigger": m.group(1) if m else CLOUDBUILD_TRIGGER_NAMES.get(f.name, ""),
        })
    return out


def discord_commands(root: pathlib.Path = REPO) -> list[dict[str, Any]]:
    """Slash commands `scripts/discord/register_commands.py` registers."""
    src = (root / "scripts/discord/register_commands.py").read_text()
    tree = ast.parse(src)
    sub_cmd = 1
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "SUB_COMMAND":
            if isinstance(node.value, ast.Constant):
                sub_cmd = node.value.value
    consts: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if isinstance(node.value, ast.Constant):
                consts[node.targets[0].id] = node.value.value

    class _Resolve(ast.NodeTransformer):
        def visit_Name(self, node: ast.Name) -> ast.AST:
            if node.id in consts:
                return ast.copy_location(ast.Constant(consts[node.id]), node)
            return node

    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.List):
            for elt in node.value.elts:
                if not isinstance(elt, ast.Dict):
                    continue
                try:
                    d = ast.literal_eval(ast.fix_missing_locations(_Resolve().visit(elt)))
                except Exception:  # a dict with non-literal values is not a command
                    continue
                if "name" in d and "description" in d:
                    subs = [o["name"] for o in d.get("options", []) if o.get("type") == sub_cmd]
                    out.append({"name": d["name"], "description": d["description"], "subcommands": subs})
    return sorted(out, key=lambda r: r["name"])


def repo_inventory(root: pathlib.Path = REPO) -> dict[str, Any]:
    jobs = deploy_jobs(root)
    sched = deploy_schedulers(root)
    schema = schema_tables(root)
    routes = api_routes(root)
    return {
        # The root this inventory was read from. Every consumer that walks the
        # tree again (import scopes, dynamic-name hints) must walk THIS root,
        # not the module-level default: `--root` selected a different tree and
        # job_table_edges was still importing from the checkout the script
        # lives in. (Codex, PR #1044.)
        "root": str(root),
        "jobs": jobs,
        "schedulers": sched,
        "deploy_targets": deploy_targets(root),
        "tables": schema["tables"],
        "materialized_views": schema["materialized_views"],
        "views": schema["views"],
        "routes": routes,
        "routers": sorted({r["router"] for r in routes if r["router"] != "main"}),
        "workflows": workflows(root),
        "cloudbuild_triggers": cloudbuild_triggers(root),
        "discord_commands": discord_commands(root),
        "modules": python_modules(root, jobs),
        "table_refs": table_refs(root),
        "counts": {
            "jobs": len(jobs),
            "schedulers": len(sched),
            "tables": len(schema["tables"]),
            "routes": len(routes),
            "routers": len({r["router"] for r in routes if r["router"] != "main"}),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# repo: code modules and table references
# ─────────────────────────────────────────────────────────────────────────────

# Production roots, walked RECURSIVELY. The previous form was a hand-listed
# set of directories globbed non-recursively, so every subpackage nobody
# remembered to add was silently absent from the "production module catalog"
# in ARCHITECTURE.md §16 -- lib/features/, lib/agents/ranker/ and
# gcp/research/direction_program/ among them. (Codex, PR #1009.)
MODULE_ROOTS = ("gcp", "lib", "platform/api")
# Not production code: archived trees, caches, tests, and vendored deps.
MODULE_EXCLUDE_PARTS = frozenset({"__pycache__", "_archive", "archive", "tests", "test",
                                  "node_modules", ".venv", "venv", "migrations"})
SCAN_DIRS = ("gcp", "lib", "scripts", "platform/api")
# Documentation tooling names tables in its own strings; it neither writes nor reads them.
DOC_TOOLING = frozenset({
    "scripts/maintenance/doc_inventory.py",
    "scripts/maintenance/check_generated_docs.py",
    "scripts/maintenance/refresh_architecture_drawio.py",
    "scripts/verify_docs_against_live.py",
})
WRITE_RE = re.compile(
    r"upsert|bulk_insert|INSERT\s+INTO|UPDATE\s+\w|DELETE\s+FROM|"
    r"\.to_sql\(|TRUNCATE|REFRESH\s+MATERIALIZED\s+VIEW|CREATE\s+TABLE|ON\s+CONFLICT|\bCOPY\b", re.I)
READ_RE = re.compile(r"\bFROM\b|\bJOIN\b|SELECT|query_to_dataframe|read_sql|row_exists|pd\.read_sql", re.I)


def _first_doc_line(path: pathlib.Path) -> str:
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return ""
    doc = ast.get_docstring(tree) or ""
    for line in doc.strip().splitlines():
        line = line.strip()
        if line and not line.startswith(("=", "-", "#")):
            return line[:140]
    return ""


def _repo_root(repo: dict[str, Any]) -> pathlib.Path:
    """The tree an inventory was read from (see repo_inventory)."""
    return pathlib.Path(repo["root"]) if repo.get("root") else REPO


def declared_relation_names(repo: dict[str, Any]) -> set[str]:
    """Tables, views AND materialized views declared in gcp/schema.sql."""
    return ({t["name"] for t in repo["tables"]}
            | {v["name"] for v in repo["materialized_views"]}
            | {v["name"] for v in repo["views"]})


def runtime_relations(repo: dict[str, Any], live: dict[str, Any]) -> list[str]:
    """Live relations gcp/schema.sql does not declare: a set difference, the
    way check_generated_docs counts them and the §1b block labels them."""
    return sorted(set(live["db_tables"]) - declared_relation_names(repo))


def entry_module(job: dict[str, Any]) -> str:
    """Repo-relative .py path of a job's entrypoint (`-m a.b.c` or `python a/b.py`)."""
    cmd = job["command"] + " " + job["args"]
    m = re.search(r"-m\s+([\w.]+)", cmd)
    if m:
        return m.group(1).replace(".", "/") + ".py"
    m = re.search(r"python3?\s+([\w/.-]+\.py)", cmd)
    return m.group(1) if m else ""


def python_modules(root: pathlib.Path = REPO, jobs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Every production Python module with its first docstring line and the
    Cloud Run Jobs whose entrypoint is that module."""
    jobs = jobs if jobs is not None else deploy_jobs(root)
    by_module: dict[str, list[str]] = {}
    for j in jobs:
        ep = entry_module(j)
        if ep:
            by_module.setdefault(ep, []).append(j["name"])
    out = []
    for d in MODULE_ROOTS:
        for f in sorted((root / d).rglob("*.py")):
            if f.name.startswith("__") or f.name.startswith("test_") or f.name.endswith("_test.py"):
                continue
            if MODULE_EXCLUDE_PARTS & set(f.relative_to(root).parts):
                continue
            rel = str(f.relative_to(root))
            dotted = rel[:-3].replace("/", ".")
            if dotted.startswith("platform."):
                dotted = dotted[len("platform."):]
            out.append({
                "path": rel,
                "module": dotted,
                "summary": _first_doc_line(f),
                "jobs": sorted(by_module.get(rel, [])),
            })
    return out


def table_refs(root: pathlib.Path = REPO, tables: list[str] | None = None) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """For every table, the code locations that write it and read it.

    Grep-based, whole-word, over gcp/ lib/ scripts/ platform/api (tests and
    archive excluded). A line is a write when it, or one of the two lines
    above it, carries a write keyword; a read when it carries a read keyword;
    otherwise a bare mention (usually a column list, a comment, or a config).
    Cited as file:line so an operator can open the exact statement.
    """
    if tables is None:
        sc = schema_tables(root)
        tables = [t["name"] for t in sc["tables"]] + [v["name"] for v in sc["materialized_views"]] + [v["name"] for v in sc["views"]]
    files: list[pathlib.Path] = []
    for d in SCAN_DIRS:
        for f in (root / d).rglob("*.py"):
            rel = str(f.relative_to(root))
            if "/tests/" in rel or rel.startswith("tests/") or "/_archive/" in rel or "/__pycache__/" in rel:
                continue
            if rel in DOC_TOOLING:  # these files quote table names in their own strings
                continue
            files.append(f)
    files.sort()
    pats = {t: re.compile(rf"(?<![\w.]){re.escape(t)}(?![\w])") for t in tables}
    out: dict[str, dict[str, list[dict[str, Any]]]] = {t: {"writes": [], "reads": [], "mentions": []} for t in tables}
    for f in files:
        rel = str(f.relative_to(root))
        try:
            lines = f.read_text().splitlines()
        except UnicodeDecodeError:
            continue
        joined = "\n".join(lines)
        # Message text is not executed SQL, and it must not leak into the
        # context window of the lines after it either (Codex, PR #1009).
        diag = _diagnostic_lines(joined)
        ctx_lines = ["" if n + 1 in diag else ln for n, ln in enumerate(lines)]
        for t, pat in pats.items():
            if t not in joined:
                continue
            for i, line in enumerate(lines):
                if not pat.search(line):
                    continue
                if line.lstrip().startswith("#"):
                    continue
                ctx = "\n".join(ctx_lines[max(0, i - 3): i + 1])
                kind = "writes" if WRITE_RE.search(ctx) else ("reads" if READ_RE.search(ctx) else "mentions")
                out[t][kind].append({"file": rel, "line": i + 1, "text": line.strip()[:120]})
                # `TABLE = "options_daily_features"` then `upsert_dataframe(df, TABLE, ...)`
                # further down: follow the constant to where it is used.
                cm = re.match(rf"\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*\w+)?\s*=\s*[\"']{re.escape(t)}[\"']", line)
                if cm:
                    const = re.compile(rf"\b{re.escape(cm.group(1))}\b")
                    for k, l2 in enumerate(lines):
                        if k == i or not const.search(l2) or l2.lstrip().startswith("#"):
                            continue
                        ctx2 = "\n".join(ctx_lines[max(0, k - 3): k + 1])
                        if WRITE_RE.search(ctx2):
                            out[t]["writes"].append({"file": rel, "line": k + 1, "text": l2.strip()[:120]})
                        elif READ_RE.search(ctx2):
                            out[t]["reads"].append({"file": rel, "line": k + 1, "text": l2.strip()[:120]})
    return out


def _diagnostic_lines(text: str) -> set[int]:
    """Line numbers whose content is a message, not executed SQL.

    `gcp/signal_monitor.py` raises a RuntimeError whose text tells the operator
    to run `UPDATE watchlists SET signals = TRUE ...`. The process only READS
    that table, but the string matched WRITE_RE, and the four-line context
    window then dragged the following log line in with it -- so the write graph
    cited two lines that execute nothing and the blast radius named
    signal-monitor a writer of watchlists. (Codex, PR #1009.)

    Covers string literals inside `raise ...`, logging calls, `print(...)`,
    `warnings.warn(...)`, and module / class / function docstrings: the
    `db-query` job's module docstring shows an operator
    `DB_QUERY_SQL=SELECT count(*) FROM trades` example, and that one line
    made the job a static reader of `trades` in the §7 graph and the digest.
    SQL that reaches a driver is never in one of those. (Codex, PR #1044.)
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    out: set[int] = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.body and isinstance(node.body[0], ast.Expr) \
                and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
            doc = node.body[0].value
            out.update(range(doc.lineno, (doc.end_lineno or doc.lineno) + 1))

    def _mark(node: ast.AST) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                out.update(range(sub.lineno, (sub.end_lineno or sub.lineno) + 1))
            elif isinstance(sub, ast.JoinedStr):
                out.update(range(sub.lineno, (sub.end_lineno or sub.lineno) + 1))

    for node in ast.walk(tree):
        if isinstance(node, ast.Raise):
            _mark(node)
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
            owner = (f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else "")
            if name in ("debug", "info", "warning", "warn", "error", "exception", "critical") \
                    or name == "print" or (owner == "warnings" and name == "warn"):
                _mark(node)
    return out


def _local_imports(root: pathlib.Path, rel: str) -> set[str]:
    """Repo modules (gcp.*, lib.*, scripts.*) a module imports, as file paths."""
    f = root / rel
    if not f.exists():
        return set()
    try:
        tree = ast.parse(f.read_text())
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module] + [node.module + "." + a.name for a in node.names]
        for n in names:
            if n.split(".")[0] in ("gcp", "lib", "scripts"):
                cand = root / (n.replace(".", "/") + ".py")
                if cand.exists():
                    out.add(str(cand.relative_to(root)))
    return out


def _module_of(path: str) -> str:
    return path[:-3].replace("/", ".") if path.endswith(".py") else path


def blast_radius(repo: dict[str, Any], refs: dict[str, dict[str, list[dict[str, Any]]]]) -> list[dict[str, Any]]:
    """Per job: tables its entrypoint module writes, and who reads them."""
    readers: dict[str, set[str]] = {t: {r["file"] for r in v["reads"]} for t, v in refs.items()}
    writers: dict[str, set[str]] = {t: {w["file"] for w in v["writes"]} for t, v in refs.items()}
    out = []
    root = _repo_root(repo)
    for j in repo["jobs"]:
        mod_file = entry_module(j)
        # entry module plus the repo modules it imports directly (one level)
        scope = {mod_file} | (_local_imports(root, mod_file) if mod_file else set())
        # gcp/database.py writes job_runs for every job; attributing it to each
        # entrypoint would drown the real blast radius in one row per job.
        scope.discard("gcp/database.py")
        written = sorted(t for t, ws in writers.items() if ws & scope)
        downstream = sorted({f for t in written for f in readers.get(t, set()) if f not in scope})
        out.append({"job": j["name"], "module": mod_file, "writes": written, "readers": downstream})
    return out


def job_table_edges(repo: dict[str, Any], refs: dict[str, dict[str, list[dict[str, Any]]]],
                    jobs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Per job: the tables its entry module (plus direct repo imports) writes
    and reads. The same attribution blast_radius uses, so the graph and the
    blast table cannot disagree about who writes what.

    Reads and writes are recorded independently: `backfill-daily-indicators`
    reads `market_data_daily` (`SELECT DISTINCT ticker FROM market_data_daily`)
    and writes it, and dropping the read because a write exists hid a real
    dependency from the graph and the digest. (Codex, PR #1044.)

    `jobs` defaults to the declared jobs; a caller may pass live job records
    (same `command` / `args` keys) to attribute hand-created jobs the same way.
    """
    root = _repo_root(repo)
    readers = {t: {r["file"] for r in v["reads"]} for t, v in refs.items()}
    writers = {t: {w["file"] for w in v["writes"]} for t, v in refs.items()}
    out = []
    for j in (repo["jobs"] if jobs is None else jobs):
        mod_file = entry_module(j)
        scope = {mod_file} | (_local_imports(root, mod_file) if mod_file else set())
        scope.discard("gcp/database.py")
        w = sorted(t for t, fs in writers.items() if fs & scope)
        r = sorted(t for t, fs in readers.items() if fs & scope)
        out.append({"job": j["name"], "module": mod_file, "writes": w, "reads": r})
    return out


def hand_created_job_edges(repo: dict[str, Any], refs: dict[str, dict[str, list[dict[str, Any]]]],
                           live: dict[str, Any]) -> list[dict[str, Any]]:
    """Live jobs with no `deploy_*` function, attributed by the entry module
    their live command names, with the same scope rule as job_table_edges.
    `in_repo` is False when that module does not exist in the checkout."""
    root = _repo_root(repo)
    declared = {j["name"] for j in repo["jobs"]}
    jobs = [dict(live["jobs"][n], name=n) for n in sorted(live["jobs"]) if n not in declared]
    out = job_table_edges(repo, refs, jobs)
    for e in out:
        e["in_repo"] = bool(e["module"]) and (root / e["module"]).exists()
    return out


def _partition_map(repo: dict[str, Any]) -> dict[str, str]:
    """child partition -> parent, from schema.sql."""
    return {t["name"]: t["partition_of"] for t in repo["tables"] if t["partition_of"]}


def _mermaid_id(prefix: str, name: str) -> str:
    return prefix + "_" + re.sub(r"[^A-Za-z0-9_]", "_", name)


def _render_graph(repo: dict[str, Any], refs: dict[str, dict[str, list[dict[str, Any]]]]) -> str:
    """The job/table write-and-read graph as Mermaid, rendered from table_refs.

    This was prose the model redrew every month from the raw 220 KB reference
    graph, and 05-c was the one step that kept dying inside the CLI's idle
    timeout while writing ~10 KB of text. Rendered here it is exact, costs the
    model nothing, and the marker gate keeps it that way.

    Only jobs with at least one edge and only tables with at least one edge
    appear; thick edges are writes, thin edges are reads.
    """
    edges = [e for e in job_table_edges(repo, refs) if e["writes"] or e["reads"]]
    tables = sorted({t for e in edges for t in e["writes"] + e["reads"]})
    lines = ["```mermaid", "flowchart LR", "    subgraph JOBS [Cloud Run Jobs]", "        direction TB"]
    lines += [f"        {_mermaid_id('J', e['job'])}[{e['job']}]" for e in edges]
    lines += ["    end", "    subgraph TABLES [Cloud SQL tables]", "        direction TB"]
    lines += [f"        {_mermaid_id('T', t)}[({t})]" for t in tables]
    lines += ["    end", ""]
    for e in edges:
        lines += [f"    {_mermaid_id('J', e['job'])} ==> {_mermaid_id('T', t)}" for t in e["writes"]]
    lines.append("")
    for e in edges:
        lines += [f"    {_mermaid_id('T', t)} --> {_mermaid_id('J', e['job'])}" for t in e["reads"]]
    lines += ["", "    classDef job fill:#3B82F6,stroke:#1E40AF,color:#fff",
              "    classDef tbl fill:#10B981,stroke:#065F46,color:#fff"]
    if edges:
        lines.append("    class " + ",".join(_mermaid_id("J", e["job"]) for e in edges) + " job")
    if tables:
        lines.append("    class " + ",".join(_mermaid_id("T", t) for t in tables) + " tbl")
    lines.append("```")
    return "\n".join(lines)


def _render_refs_digest(repo: dict[str, Any], refs: dict[str, dict[str, list[dict[str, Any]]]],
                        live: dict[str, Any] | None = None) -> str:
    """What the 05-c prompt is handed instead of the raw table_refs graph: the
    multi-writer tables with their writers cited `file:line`, the orphans with
    the same partition-aware status the §5 block carries, each job's written
    and read tables, and -- when a live snapshot is given -- the two name sets
    the prose states that exist only live: the runtime-created relations and
    the hand-created jobs. `live.json` and the §1b block are off-limits to the
    model, so those names have to travel here. (Codex, PR #1044.) A few KB,
    from the same data the rendered blocks come from, so the prose agrees
    with the blocks."""
    root = _repo_root(repo)
    out = ["## Multi-writer tables", "", _render_multiwriter(refs, with_lines=True), "",
           "## Orphan tables", "", _render_orphans(refs, root, _partition_map(repo)), "",
           "## Tables per job (entry module plus its direct repo imports)", ""]
    rows = [[f"`{e['job']}`", ", ".join(f"`{t}`" for t in e["writes"]) or "—",
             ", ".join(f"`{t}`" for t in e["reads"]) or "—"]
            for e in job_table_edges(repo, refs) if e["writes"] or e["reads"]]
    out.append(_md_table(["Job", "Writes", "Reads"], rows) if rows else "_none_")
    out += ["", "## Runtime-created relations (live, not declared in gcp/schema.sql)", ""]
    if live is None:
        out.append("_no live snapshot supplied; not computable_")
    else:
        rt = runtime_relations(repo, live)
        # Same rendering as the §1b block: a view has no row estimate and
        # shows "—"; a missing count is never rendered as 0.
        rows = []
        for t in rt:
            d = live["db_tables"][t]
            n = d.get("rows")
            rows.append([f"`{t}`", d.get("kind") or "—", "—" if n is None else f"{n:,}", d["size"]])
        out.append(_md_table(["Relation", "Kind", "Rows", "Size"], rows) if rows else "_none_")
    out += ["", "## Hand-created live jobs (not in gcp/deploy.sh)", ""]
    if live is None:
        out.append("_no live snapshot supplied; not computable_")
    else:
        rows = []
        for e in hand_created_job_edges(repo, refs, live):
            mod = f"`{e['module']}`" if e["module"] else "—"
            if not e["in_repo"]:
                mod += " (not in this checkout)"
            rows.append([f"`{e['job']}`", mod,
                         ", ".join(f"`{t}`" for t in e["writes"]) or "—",
                         ", ".join(f"`{t}`" for t in e["reads"]) or "—"])
        out.append(_md_table(["Job", "Entry module", "Writes", "Reads"], rows) if rows else "_none_")
        out += ["", "Writes and reads name declared relations only, as in every block above: a"
                " runtime-created relation one of these jobs writes is listed in the previous"
                " section and has no edge here."]
    return "\n".join(out)


def _render_modules(mods: list[dict[str, Any]]) -> str:
    rows = [[f"[`{m['path']}`]({m['path']})", m["summary"] or "—", ", ".join(f"`{j}`" for j in m["jobs"]) or "—"] for m in mods]
    return _md_table(["Module", "Purpose (first docstring line)", "Cloud Run Job(s)"], rows)


def _cite(r: dict[str, Any]) -> str:
    return f"[`{r['file']}:{r['line']}`]({r['file']}#L{r['line']})"


def _render_refs(refs: dict[str, dict[str, list[dict[str, Any]]]], kind: str) -> str:
    out = []
    for t in sorted(refs):
        items = refs[t][kind]
        out.append(f"### `{t}`")
        if not items:
            out.append(f"- _no {kind[:-1]}r found in gcp/, lib/, scripts/, platform/api_")
        else:
            by_file: dict[str, list[int]] = {}
            for r in items:
                by_file.setdefault(r["file"], []).append(r["line"])
            for f, ls in sorted(by_file.items()):
                cites = ", ".join(f"[{l}]({f}#L{l})" for l in ls[:8]) + (f" (+{len(ls)-8} more)" if len(ls) > 8 else "")
                out.append(f"- [`{f}`]({f}) — line {cites}")
        out.append("")
    return "\n".join(out).rstrip()


def _render_multiwriter(refs, with_lines: bool = False) -> str:
    """Tables with two or more writing files. `with_lines` cites each writer
    as `file:line[,line...]` (the digest form, so the prose can cite
    `file:line` as the prompt requires); the §4 block lists files only."""
    rows = []
    for t in sorted(refs):
        by_file: dict[str, list[int]] = {}
        for w in refs[t]["writes"]:
            by_file.setdefault(w["file"], []).append(w["line"])
        if len(by_file) >= 2:
            if with_lines:
                cites = ", ".join(f"`{f}:{','.join(str(l) for l in sorted(set(ls)))}`" for f, ls in sorted(by_file.items()))
            else:
                cites = ", ".join(f"`{f}`" for f in sorted(by_file))
            rows.append([f"`{t}`", str(len(by_file)), cites])
    return _md_table(["Table", "Writers", "Files"], rows) if rows else "_none_"


def _dynamic_hint(root: pathlib.Path, table: str) -> list[str]:
    """Files that build this table's name at runtime (`f"realtime_gex_{tf}"`).

    A grep for the literal name cannot see those writers; naming the files
    that assemble the prefix is the honest alternative to reporting "no writer".
    """
    if "_" not in table:
        return []
    prefix = table.rsplit("_", 1)[0]
    pat = re.compile(rf"{re.escape(prefix)}_(\{{|%s|\"\s*\+|'\s*\+|\$)")
    hits: list[str] = []
    for d in SCAN_DIRS:
        for f in sorted((root / d).rglob("*.py")):
            rel = str(f.relative_to(root))
            if "/tests/" in rel or rel.startswith("tests/") or "/_archive/" in rel or rel in DOC_TOOLING:
                continue
            try:
                if pat.search(f.read_text()):
                    hits.append(rel)
            except UnicodeDecodeError:
                continue
    return hits


def _render_orphans(refs, root: pathlib.Path = REPO, partitions: dict[str, str] | None = None) -> str:
    rows = []
    partitions = partitions or {}
    for t in sorted(refs):
        w = {x["file"] for x in refs[t]["writes"]}; r = {x["file"] for x in refs[t]["reads"]}
        if w and r:
            continue
        if t in partitions:
            status = f"partition of `{partitions[t]}` — routed by Postgres, never named in code"
        elif not w and not r:
            status = "no writer and no reader in code"
        elif not r:
            status = "write-only (no reader in code)"
        else:
            status = "read-only (no writer names it in code)"
        dyn = _dynamic_hint(root, t) if not w else []
        if dyn:
            status += "; name built at runtime in " + ", ".join(f"`{f}`" for f in dyn[:4])
        rows.append([f"`{t}`", str(len(w)), str(len(r)), status])
    return _md_table(["Table", "Writers", "Readers", "Status"], rows) if rows else "_none_"


def _render_blast(repo, refs) -> str:
    rows = []
    for b in blast_radius(repo, refs):
        rows.append([f"`{b['job']}`", f"`{b['module']}`" if b["module"] else "—",
                     ", ".join(f"`{t}`" for t in b["writes"]) or "— (Discord / GCS / no Cloud SQL write found)",
                     ", ".join(f"`{f}`" for f in b["readers"][:12]) + (f" (+{len(b['readers'])-12})" if len(b["readers"]) > 12 else "") or "—"])
    return _md_table(["Job", "Entry module", "Tables written (entry module + its direct repo imports)", "Readers of those tables"], rows)


# ─────────────────────────────────────────────────────────────────────────────
# live: gcloud
# ─────────────────────────────────────────────────────────────────────────────

def _gcloud(*args: str) -> str:
    """Run gcloud and return stdout. Raises on any failure: an inventory read
    that quietly returned an empty collection produced plausible, incomplete
    docs (Codex, PR #1009), so no read is optional.

    No silent fallback to a cached snapshot (Rule 3.7): a doc "verified" against
    stale state is worse than no doc.
    """
    proc = subprocess.run(("gcloud",) + args, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"gcloud {' '.join(args)} failed: {proc.stderr.strip()[:400]}")
    return proc.stdout


def _gjson(*args: str) -> Any:
    out = _gcloud(*args, "--format=json")
    return json.loads(out) if out.strip() else []


def live_snapshot(project: str = PROJECT, region: str = REGION,
                  ) -> dict[str, Any]:
    """Read the live GCP state the docs describe. Every read raises on failure."""
    p = f"--project={project}"
    jobs_raw = _gjson("run", "jobs", "list", f"--region={region}", p)
    jobs = {}
    for j in jobs_raw:
        tmpl = j["spec"]["template"]["spec"]
        c = tmpl["template"]["spec"]["containers"][0]
        res = (c.get("resources") or {}).get("limits") or {}
        jobs[j["metadata"]["name"]] = {
            "image": c.get("image", ""),
            "command": " ".join(c.get("command") or []),
            "args": " ".join(c.get("args") or []),
            "memory": res.get("memory", ""),
            "cpu": res.get("cpu", ""),
            "task_timeout": tmpl["template"]["spec"].get("timeoutSeconds", ""),
            "max_retries": tmpl["template"]["spec"].get("maxRetries", ""),
            "tasks": tmpl.get("taskCount", 1),
            "service_account": tmpl["template"]["spec"].get("serviceAccountName", ""),
            "created": j["metadata"].get("creationTimestamp", ""),
        }
    # Each job's own `status.latestCreatedExecution` (name, timestamps,
    # completionStatus) comes back in the jobs list, so the latest run of a
    # weekly job is never crowded out by a five-minute one the way a shared
    # `executions list --limit N` did (Codex, PR #1009).
    for j in jobs_raw:
        name = j["metadata"]["name"]
        lce = (j.get("status") or {}).get("latestCreatedExecution") or {}
        if not lce:
            jobs[name]["last_execution"] = {"time": "", "result": "never"}
            continue
        status = lce.get("completionStatus", "")
        result = {"EXECUTION_SUCCEEDED": "ok", "EXECUTION_FAILED": "failed",
                  "EXECUTION_CANCELLED": "cancelled"}.get(status, "running" if not lce.get("completionTimestamp") else status.lower())
        jobs[name]["last_execution"] = {
            "time": lce.get("completionTimestamp") or lce.get("creationTimestamp", ""),
            "result": result, "name": lce.get("name", ""),
        }

    svc_raw = _gjson("run", "services", "list", f"--region={region}", p)
    services = {}
    for s in svc_raw:
        m = s["metadata"]; t = s["spec"]["template"]; c = t["spec"]["containers"][0]
        ann = m.get("annotations") or {}; tann = t["metadata"].get("annotations") or {}
        name = m["name"]
        policy = _gjson("run", "services", "get-iam-policy", name, f"--region={region}", p,
                       )
        invokers = [x for b in (policy.get("bindings") or []) if isinstance(policy, dict)
                    for x in b.get("members", []) if b.get("role") == "roles/run.invoker"]
        env = {e["name"]: (e.get("value") if "value" in e else "<secret>") for e in c.get("env", [])}
        services[name] = {
            "url": (s.get("status") or {}).get("url", ""),
            "image": c.get("image", ""),
            "service_account": t["spec"].get("serviceAccountName", ""),
            "ingress": ann.get("run.googleapis.com/ingress", ""),
            "iap": ann.get("run.googleapis.com/iap-enabled", "false"),
            "min_instances": tann.get("autoscaling.knative.dev/minScale", "0"),
            "max_instances": tann.get("autoscaling.knative.dev/maxScale", ""),
            "cpu_throttling": tann.get("run.googleapis.com/cpu-throttling", "true"),
            "auth_mode": env.get("AUTH_MODE", ""),
            "open_signup": env.get("AUTH_OPEN_SIGNUP", ""),
            "invokers": invokers,
            "latest_revision": (s.get("status") or {}).get("latestReadyRevisionName", ""),
            "created": m.get("creationTimestamp", ""),
        }

    sched_raw = _gjson("scheduler", "jobs", "list", f"--location={region}", p)
    schedulers = {}
    for s in sched_raw:
        name = s["name"].rsplit("/", 1)[-1]
        uri = (s.get("httpTarget") or {}).get("uri", "")
        m = re.search(r"/jobs/([^:/]+):run", uri)
        schedulers[name] = {
            "cron": s.get("schedule", ""), "time_zone": s.get("timeZone", ""),
            "state": s.get("state", ""), "target_job": m.group(1) if m else "",
            "target_service": "" if m else _service_of(uri),
            "target_uri": "" if m else uri,
            "last_attempt": s.get("lastAttemptTime", ""),
            "last_status": ((s.get("status") or {}).get("code", 0)),
        }

    triggers = [{"name": t.get("name", ""),
                 "branch": ((t.get("github") or {}).get("push") or {}).get("branch", "")
                           or (t.get("triggerTemplate") or {}).get("branchName", ""),
                 "disabled": t.get("disabled", False)}
                for t in _gjson("builds", "triggers", "list", "--region=global", p)]
    domains = [{"domain": d["metadata"]["name"], "service": d["spec"].get("routeName", "")}
               for d in _gjson("beta", "run", "domain-mappings", "list", f"--region={region}", p,
                              )]
    sql = _gjson("sql", "instances", "describe", "trading-db", p)
    sql_settings = (sql.get("settings") or {}) if isinstance(sql, dict) else {}
    backups = _gjson("sql", "backups", "list", "--instance=trading-db", "--limit=3", p)
    dumps = _gcloud("storage", "ls", "-l", f"gs://{project}-trading-data/sql-dumps/")
    dump_lines = [l.split() for l in dumps.splitlines() if l.strip().startswith(("1", "2", "3", "4", "5", "6", "7", "8", "9"))]
    secrets = sorted(x["name"].rsplit("/", 1)[-1] for x in _gjson("secrets", "list", p))
    topics = sorted(t["name"].rsplit("/", 1)[-1] for t in _gjson("pubsub", "topics", "list", p))
    subs = [{"name": s["name"].rsplit("/", 1)[-1],
             "push_endpoint": (s.get("pushConfig") or {}).get("pushEndpoint", "")}
            for s in _gjson("pubsub", "subscriptions", "list", p)]
    sinks = [{"name": s["name"], "destination": s.get("destination", ""), "filter": s.get("filter", "")}
             for s in _gjson("logging", "sinks", "list", p)
             if not s["name"].startswith("_")]
    queue = _gjson("tasks", "queues", "describe", "insight-pipeline-queue", f"--location={region}", p,
                  )
    sas = sorted(s["email"] for s in _gjson("iam", "service-accounts", "list", p))
    tags = _gcloud("artifacts", "docker", "tags", "list",
                   f"{region}-docker.pkg.dev/{project}/trading/trading-system", p,
                   "--format=value(tag)").split()
    gcr = _gcloud("container", "images", "list", f"--repository=gcr.io/{project}",
                  "--format=value(name)").split()

    return {
        "read_at": _now_iso(),
        "project": project, "region": region,
        "jobs": jobs, "services": services, "schedulers": schedulers,
        "cloudbuild_triggers": triggers, "domain_mappings": domains,
        "sql": {
            "version": sql.get("databaseVersion", "") if isinstance(sql, dict) else "",
            "tier": sql_settings.get("tier", ""),
            "disk_gb": sql_settings.get("dataDiskSizeGb", ""),
            "ipv4_enabled": (sql_settings.get("ipConfiguration") or {}).get("ipv4Enabled", ""),
            "authorized_networks": len((sql_settings.get("ipConfiguration") or {}).get("authorizedNetworks") or []),
            "ssl_mode": (sql_settings.get("ipConfiguration") or {}).get("sslMode", ""),
            "pitr": (sql_settings.get("backupConfiguration") or {}).get("pointInTimeRecoveryEnabled", ""),
            "backup_start": (sql_settings.get("backupConfiguration") or {}).get("startTime", ""),
            "retained_backups": ((sql_settings.get("backupConfiguration") or {}).get("backupRetentionSettings") or {}).get("retainedBackups", ""),
            "deletion_protection": sql_settings.get("deletionProtectionEnabled", ""),
            "maintenance": sql_settings.get("maintenanceWindow", {}),
            "latest_backups": [{"start": b.get("startTime", ""), "status": b.get("status", "")} for b in backups] if isinstance(backups, list) else [],
        },
        "sql_dumps": [{"bytes": l[0], "time": l[1], "path": l[2]} for l in dump_lines if len(l) >= 3],
        "secrets": secrets,
        "pubsub": {"topics": topics, "subscriptions": subs},
        "log_sinks": sinks,
        "tasks_queue": {
            "name": queue.get("name", "").rsplit("/", 1)[-1] if isinstance(queue, dict) else "",
            "max_concurrent": ((queue.get("rateLimits") or {}).get("maxConcurrentDispatches", "") if isinstance(queue, dict) else ""),
            "max_attempts": ((queue.get("retryConfig") or {}).get("maxAttempts", "") if isinstance(queue, dict) else ""),
            "state": queue.get("state", "") if isinstance(queue, dict) else "",
        },
        "service_accounts": sas,
        "image_tags": tags,
        "gcr_images": gcr,
        "counts": {
            "jobs": len(jobs), "services": len(services), "schedulers": len(schedulers),
            "secrets": len(secrets), "paused_schedulers": sum(1 for s in schedulers.values() if s["state"] != "ENABLED"),
        },
    }


def db_tables_snapshot() -> dict[str, dict[str, Any]]:
    """Live relations with row estimates and sizes, via gcp.database.get_engine().

    Needs the Cloud SQL env (CLOUD_SQL_CONNECTION_NAME, DB_USER, DB_PASS, DB_NAME),
    which the refresh workflow already injects for the calibration step. From a
    sandbox without port 5432, run the same SQL through scripts/db_query_cr.sh
    and pass the CSV with --db-tables instead.
    """
    from sqlalchemy import text  # local import: optional dependency
    from gcp.database import get_engine

    with get_engine().connect() as conn:
        rows = conn.execute(text(DB_TABLES_SQL)).fetchall()
    return {r[0]: _db_row(r[1], r[2], r[3]) for r in rows}


# pg_stat_user_tables has no ordinary views, so a plain `v_*` view read as
# "absent live" (Codex, PR #1009). pg_class carries every relation kind; row
# estimates exist only for tables and materialized views, so a view's rows
# are NULL, never 0.
DB_TABLES_SQL = (
    "SELECT c.relname, s.n_live_tup, pg_size_pretty(pg_total_relation_size(c.oid)) AS size, c.relkind "
    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid "
    "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'm', 'v') ORDER BY c.relname"
)
RELKIND = {"r": "table", "p": "partitioned table", "m": "materialized view", "v": "view"}


def _db_row(n_live_tup: Any, size: str, relkind: str) -> dict[str, Any]:
    rows = None if n_live_tup in (None, "") else int(float(n_live_tup))
    return {"rows": rows, "size": size, "kind": RELKIND.get(relkind, relkind)}


def db_tables_from_csv(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    import csv
    with path.open() as fh:
        return {r["relname"]: _db_row(r.get("n_live_tup"), r["size"], r.get("relkind", "r"))
                for r in csv.DictReader(fh)}


def _render_dbtables(repo: dict[str, Any], live: dict[str, Any] | None) -> str:
    db = (live or {}).get("db_tables") or {}
    if not db:
        return "_live table snapshot required (`--db-tables` or the workflow's Cloud SQL step)_"
    declared = {t["name"] for t in repo["tables"]} | {v["name"] for v in repo["materialized_views"]} | {v["name"] for v in repo["views"]}
    rows = []
    for name in sorted(db):
        where = "`gcp/schema.sql`" if name in declared else "**runtime-created** (not in schema.sql)"
        n = db[name].get("rows")
        rows.append([f"`{name}`", "—" if n is None else f"{n:,}", db[name]["size"],
                     where + (f" ({db[name]['kind']})" if db[name].get("kind") not in (None, "table") else "")])
    missing = sorted(declared - set(db))
    out = _md_table(["Relation (live)", "Rows (estimate; — for views)", "Size", "Declared in"], rows)
    if missing:
        out += "\n\nDeclared in `gcp/schema.sql` but absent live: " + ", ".join(f"`{m}`" for m in missing)
    return out


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─────────────────────────────────────────────────────────────────────────────
# reconcile
# ─────────────────────────────────────────────────────────────────────────────

# Fields rendered from deploy.sh in the job table. The live values were read
# but used only for execution status, so a job running at 2 GiB against a 1 GiB
# declaration was documented as 1 GiB and reconciled clean -- and a rebuild
# would silently move it. (Codex, PR #1009.)
# `task_timeout` is what BOTH sides actually store. The first version of this
# said "timeout", so that entry compared None with None on every job and the
# check was dead for the field -- missing compute-earnings-reactions at 1800
# declared against 5400 live. command/args were omitted entirely, hiding an
# entrypoint change. (Codex, PR #1009.)
JOB_CONFIG_FIELDS = ("memory", "cpu", "task_timeout", "max_retries", "tasks")


def _norm_cfg(v: Any) -> str | None:
    """Comparable form, or None when the value is not comparable.

    A deploy-time variable (`--tasks ${n}`) is not drift: the repo cannot state
    the number, exactly as with a templated scheduler URI.
    """
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        v = " ".join(str(x) for x in v)
    s = str(v).strip()
    if "${" in s or not s:
        return None
    return s.rstrip("i") if s[:-1].isdigit() or s[:-2].isdigit() else s


def jobs_config_drift(repo: dict[str, Any], live: dict[str, Any]) -> list[str]:
    by = {j["name"]: j for j in repo["jobs"]}
    out = []
    for name, l in sorted((live.get("jobs") or {}).items()):
        r = by.get(name)
        if not r:
            continue
        for f in JOB_CONFIG_FIELDS:
            rv, lv = _norm_cfg(r.get(f)), _norm_cfg(l.get(f))
            if rv is None or lv is None or rv == lv:
                continue
            out.append(f"{name}.{f}: repo `{r.get(f)}` live `{l.get(f)}`")
        # command and args are ONE fact: the live record splits `python` from
        # `-m gcp.x` while deploy.sh puts the whole invocation in command, so
        # comparing the fields separately reports four jobs as drifted purely
        # on representation. Joined, only a real entrypoint change shows.
        rv, lv = _entrypoint(r), _entrypoint(l)
        if rv and lv and rv != lv:
            out.append(f"{name}.entrypoint: repo `{rv[:70]}` live `{lv[:70]}`")
    return out


def _entrypoint(j: dict[str, Any]) -> str | None:
    parts = [_norm_cfg(j.get("command")), _norm_cfg(j.get("args"))]
    joined = " ".join(p for p in parts if p)
    return joined or None


def _sched_target(s: dict[str, Any]) -> str:
    """A scheduler's target as `kind:name`, so a job and a service of the same
    name are different targets and a conversion between the two is drift."""
    if s.get("target_job"):
        return f"job:{s['target_job']}"
    if s.get("target_service"):
        return f"service:{s['target_service']}"
    if s.get("target_uri"):
        # Discarding the host entirely made a redirect to ANY other host with
        # the same path invisible. The repo does know the intended identity --
        # deploy.sh sets NOTIFIER_SERVICE and derives ${service_url} from it --
        # so the variable name is kept as the service, and a live URL is
        # matched back to its service by hostname. (Codex, PR #1009.)
        uri = s["target_uri"]
        if "${" in uri:
            var = re.search(r"\$\{([a-z_]*service[a-z_]*)\}", uri, re.I)
            svc = s.get("target_service") or (_SERVICE_VAR.get(var.group(1)) if var else None)
            path = uri.split("}", 1)[-1]
            return f"service:{svc}{path}" if svc else f"uri:{path or '/'}"
        host = re.match(r"https?://([^/]+)", uri)
        path = re.sub(r"^https?://[^/]+", "", uri)
        if host:
            # Cloud Run hostnames start with the service name.
            svc = host.group(1).split(".")[0].rsplit("-", 2)[0]
            return f"service:{svc}{path or '/'}"
        return f"uri:{path or '/'}"
    return ""


# `${service_url}` in deploy.sh is derived from NOTIFIER_SERVICE; keeping the
# mapping here means a templated target still names the service it points at.
_SERVICE_VAR = {"service_url": "failure-notifier"}


def reconcile(repo: dict[str, Any], live: dict[str, Any]) -> dict[str, Any]:
    repo_jobs = {j["name"] for j in repo["jobs"]}
    live_jobs = set(live["jobs"])
    repo_sched = {s["name"]: s for s in repo["schedulers"]}
    live_sched = live["schedulers"]
    return {
        "jobs_live_only": sorted(live_jobs - repo_jobs),
        "jobs_repo_only": sorted(repo_jobs - live_jobs),
        "schedulers_live_only": sorted(set(live_sched) - set(repo_sched)),
        "schedulers_repo_only": sorted(set(repo_sched) - set(live_sched)),
        "schedulers_paused": sorted(n for n, s in live_sched.items() if s["state"] != "ENABLED"),
        "schedulers_targeting_missing_job": sorted(
            n for n, s in live_sched.items() if s.get("target_job") and s["target_job"] not in live_jobs),
        "schedulers_repo_target_not_in_deploy": sorted(
            n for n, s in repo_sched.items() if s.get("target_job") and s["target_job"] not in repo_jobs),
        "schedulers_cron_drift": sorted(
            f"{n}: repo `{repo_sched[n]['cron']}` live `{live_sched[n]['cron']}`"
            for n in set(repo_sched) & set(live_sched)
            if repo_sched[n]["cron"] != live_sched[n]["cron"]),
        # Cron alone said the fleets matched while a scheduler could be
        # redirected to a different EXISTING job, or moved to another zone --
        # both pass the missing-target check and neither changes the cron, so
        # production fired the wrong job, or the right one at the wrong
        # wall-clock time, under a reconciliation that read clean.
        # (Codex, PR #1009.)
        # Compared as a normalised job-or-service target, not two job names:
        # `discord-warm-open` / `-close` target the discord-interactions
        # SERVICE, so requiring both target_job fields to be non-empty skipped
        # them entirely -- and a job scheduler converted into a service request
        # (or the reverse) also passed. (Codex, PR #1009.)
        "schedulers_target_drift": sorted(
            f"{n}: repo `{_sched_target(repo_sched[n])}` live `{_sched_target(live_sched[n])}`"
            for n in set(repo_sched) & set(live_sched)
            if _sched_target(repo_sched[n]) and _sched_target(live_sched[n])
            and _sched_target(repo_sched[n]) != _sched_target(live_sched[n])),
        "schedulers_tz_drift": sorted(
            f"{n}: repo `{repo_sched[n].get('time_zone')}` live `{live_sched[n].get('time_zone')}`"
            for n in set(repo_sched) & set(live_sched)
            if repo_sched[n].get("time_zone") and live_sched[n].get("time_zone")
            and repo_sched[n]["time_zone"] != live_sched[n]["time_zone"]),
        "jobs_config_drift": jobs_config_drift(repo, live),
        "jobs_never_executed_in_window": sorted(
            n for n, j in live["jobs"].items() if j["last_execution"]["result"] == "never"),
        "jobs_last_failed": sorted(
            n for n, j in live["jobs"].items() if j["last_execution"]["result"] == "failed"),
        "counts": {
            "jobs_repo": len(repo_jobs), "jobs_live": len(live_jobs),
            "schedulers_repo": len(repo_sched), "schedulers_live": len(live_sched),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# markdown rendering (the marker-block contents)
# ─────────────────────────────────────────────────────────────────────────────

def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _fmt_time(t: str) -> str:
    """Date only. A rendered HH:MM next to a job name reads as a schedule
    claim to scripts/verify_docs_against_live.py and is flagged as drift."""
    return t[:10] if t else ""


def render_markdown(section: str, repo: dict[str, Any], live: dict[str, Any] | None = None) -> str:
    rec = reconcile(repo, live) if live else None
    if section == "jobs":
        live_jobs = (live or {}).get("jobs", {})
        rows = []
        names = sorted({j["name"] for j in repo["jobs"]} | set(live_jobs))
        by_name = {j["name"]: j for j in repo["jobs"]}
        for n in names:
            r = by_name.get(n); l = live_jobs.get(n)
            if r:
                src = f"[`gcp/deploy.sh:{r['line']}`](gcp/deploy.sh#L{r['line']})"
                entry = (r["command"] + (" " + r["args"] if r["args"] else "")).strip() or "(image default)"
                cfg = f"{r['memory']} / {r['cpu']} CPU / {r['task_timeout']}s / retries {r['max_retries']}" + (f" / tasks {r['tasks']}" if r['tasks'] != '1' else "")
                if r["timeout_defaulted"] or r["retries_defaulted"]:
                    cfg += " (defaults)"
                img = r["image"]
            else:
                src = "**not in deploy.sh** (hand-created)"
                entry = ((l or {}).get("command", "") + " " + (l or {}).get("args", "")).strip()
                cfg = f"{(l or {}).get('memory','')} / {(l or {}).get('cpu','')} CPU / {(l or {}).get('task_timeout','')}s / retries {(l or {}).get('max_retries','')}"
                img = (l or {}).get("image", "").split("/")[-1]
            if live is not None:
                if l:
                    le = l["last_execution"]
                    status = f"{_fmt_time(le['time'])} {le['result']}".strip()
                else:
                    status = "**not deployed**"
                rows.append([f"`{n}`", src, entry, cfg, img, status])
            else:
                rows.append([f"`{n}`", src, entry, cfg, img])
        headers = ["Job", "Declared", "Entrypoint", "Memory / CPU / timeout / retries", "Image"]
        if live is not None:
            headers.append(f"Last execution (live {live['read_at'][:10]})")
        return _md_table(headers, rows)
    if section == "schedulers":
        live_s = (live or {}).get("schedulers", {})
        by_name = {s["name"]: s for s in repo["schedulers"]}
        names = sorted(set(by_name) | set(live_s))
        rows = []
        for n in names:
            r = by_name.get(n); l = live_s.get(n)
            cron = (l or r or {}).get("cron", "")
            src = l or r or {}
            target = src.get("target_job", "") or src.get("target_uri", "")
            svc = src.get("target_service") or _service_of(src.get("target_uri", ""))
            if not src.get("target_job") and svc:
                # a service-scaling PATCH, not a job run; name the service so the
                # row reads like the rest of the table
                target = f"{svc} (service, minInstanceCount patch)"
            if live is not None:
                if r and l:
                    state = l["state"] + ("" if r["cron"] == l["cron"] else f" (repo cron `{r['cron']}`)")
                elif l:
                    state = l["state"] + " — **not in deploy.sh**"
                else:
                    state = "**not live** (declared in deploy.sh)"
                # scripts/verify_docs_against_live.py flags any line naming a job
                # that has a PAUSED scheduler; say so on the sibling's row.
                paused_siblings = [m for m, x in live_s.items() if m != n and x.get("state") != "ENABLED"
                                   and x.get("target_job") and x.get("target_job") == (l or r or {}).get("target_job")]
                note = (f" <!-- verify-docs-ok: sibling scheduler {', '.join(paused_siblings)} is paused; this entry fires -->"
                        if paused_siblings and l and l["state"] == "ENABLED" else "")
                rows.append([f"`{n}`", f"`{cron}`", f"`{target}`", (r or {}).get("args", ""), state + note, _fmt_time((l or {}).get("last_attempt", ""))])
            else:
                rows.append([f"`{n}`", f"`{cron}`", f"`{target}`", (r or {}).get("args", "")])
        headers = ["Scheduler", "Cron (America/New_York)", "Target", "Args override"]
        if live is not None:
            headers += ["State (live)", "Last attempt"]
        return _md_table(headers, rows)
    if section == "tables":
        rows = []
        for t in repo["tables"]:
            kind = f"partition of `{t['partition_of']}`" if t["partition_of"] else "table"
            rows.append([f"`{t['name']}`", kind, f"[`gcp/schema.sql:{t['line']}`](gcp/schema.sql#L{t['line']})"])
        for v in repo["materialized_views"]:
            rows.append([f"`{v['name']}`", "materialized view", f"[`gcp/schema.sql:{v['line']}`](gcp/schema.sql#L{v['line']})"])
        for v in repo["views"]:
            rows.append([f"`{v['name']}`", "view", f"[`gcp/schema.sql:{v['line']}`](gcp/schema.sql#L{v['line']})"])
        return _md_table(["Relation", "Kind", "Defined"], rows)
    if section == "routes":
        rows = [[f"`{r['method']}`", f"`{r['path']}`", f"[`{r['file']}:{r['line']}`]({r['file']}#L{r['line']})", r["summary"]]
                for r in repo["routes"]]
        return _md_table(["Method", "Path", "Defined", "Purpose"], rows)
    if section == "routers":
        by_file: dict[str, list[dict[str, Any]]] = {}
        for r in repo["routes"]:
            by_file.setdefault(r["file"], []).append(r)
        rows = []
        for f, rs in sorted(by_file.items()):
            methods = ", ".join(sorted({r["method"] for r in rs}))
            prefixes = sorted({"/".join(r["path"].split("/")[:3]) for r in rs})
            rows.append([f"[`{f.rsplit('/', 1)[-1]}`]({f})", str(len(rs)), methods, ", ".join(f"`{x}`" for x in prefixes[:4]) + (" …" if len(prefixes) > 4 else "")])
        rows.append(["**Total**", str(len(repo["routes"])), "", f"{len(by_file)} routers"])
        return _md_table(["Router", "Routes", "Methods", "Path families"], rows)
    if section == "services":
        if not live:
            return "_live snapshot required_"
        rows = []
        for n, s in sorted(live["services"].items()):
            auth = s["auth_mode"] or "-"
            if s["iap"] == "true":
                auth += " (IAP)"
            if "allUsers" in s["invokers"]:
                auth += ", public invoker"
            if s["open_signup"]:
                auth += f", open_signup={s['open_signup']}"
            rows.append([f"`{n}`", s["url"], auth, s["image"].split("/")[-1], f"{s['min_instances']}–{s['max_instances']}", s["service_account"].split("@")[0] + "@", _fmt_time(s["created"])])
        return _md_table(["Service", "URL", "Auth", "Image", "Instances", "SA", "Created"], rows)
    if section == "reconcile":
        if not rec:
            return "_live snapshot required_"
        lines = [f"Live read {live['read_at']}. Repo declares {rec['counts']['jobs_repo']} jobs / {rec['counts']['schedulers_repo']} schedulers; live has {rec['counts']['jobs_live']} / {rec['counts']['schedulers_live']}. <!-- verify-docs-ok: repo-declared and live counts side by side -->", ""]
        def block(title, items):
            lines.append(f"**{title}** ({len(items)}): " + (", ".join(f"`{i}`" for i in items) if items else "none"))
        block("Jobs live but not in deploy.sh", rec["jobs_live_only"])
        block("Jobs in deploy.sh but not live", rec["jobs_repo_only"])
        block("Schedulers live but not in deploy.sh", rec["schedulers_live_only"])
        block("Schedulers in deploy.sh but not live", rec["schedulers_repo_only"])
        block("Schedulers paused", rec["schedulers_paused"])
        block("Live schedulers targeting a missing job", rec["schedulers_targeting_missing_job"])
        block("deploy.sh schedulers targeting a job deploy.sh never creates", rec["schedulers_repo_target_not_in_deploy"])
        block("Cron drift (same name, different cron)", rec["schedulers_cron_drift"])
        block("Target drift (same name, different job)", rec["schedulers_target_drift"])
        block("Time-zone drift (same name, different zone)", rec["schedulers_tz_drift"])
        block("Job config drift (declared vs live)", rec["jobs_config_drift"])
        block("Jobs whose last execution failed", rec["jobs_last_failed"])
        block("Jobs that have never executed", rec["jobs_never_executed_in_window"])
        return "\n".join(lines)
    if section == "modules":
        return _render_modules(repo["modules"])
    if section in ("writes", "reads"):
        return _render_refs(repo["table_refs"], section)
    if section == "multiwriter":
        return _render_multiwriter(repo["table_refs"])
    if section == "orphans":
        return _render_orphans(repo["table_refs"], _repo_root(repo), _partition_map(repo))
    if section == "blast":
        return _render_blast(repo, repo["table_refs"])
    if section == "graph":
        return _render_graph(repo, repo["table_refs"])
    if section == "refs_digest":
        return _render_refs_digest(repo, repo["table_refs"], live)
    if section == "dbtables":
        return _render_dbtables(repo, live)
    raise ValueError(f"unknown section {section!r}")


SECTIONS = ("jobs", "schedulers", "tables", "routes", "routers", "services", "reconcile",
            "modules", "writes", "reads", "multiwriter", "orphans", "blast", "dbtables",
            "graph", "refs_digest")


def _rebase_links(body: str, depth: int) -> str:
    """Rendered links are repo-root-relative; a doc under docs/ needs `../`."""
    if depth <= 0:
        return body
    prefix = "../" * depth
    return re.sub(r"\]\((?!https?://|#|\.\./|/)", "](" + prefix, body)


def _block_bodies(doc_path: pathlib.Path, repo: dict[str, Any], live: dict[str, Any] | None,
                  root: pathlib.Path) -> list[tuple[str, str, str, re.Pattern]]:
    """(name, current body, fresh body, block pattern) for every block present.

    Raises ValueError on a start marker without its end, as insert_blocks
    does: that block cannot be located, so it cannot be compared or restored.
    """
    text = doc_path.read_text()
    try:
        depth = len(doc_path.resolve().relative_to(root.resolve()).parents) - 1
    except ValueError:
        depth = 0
    out = []
    for name in SECTIONS:
        start, end = MARKER_START.format(name=name), MARKER_END.format(name=name)
        if start not in text:
            continue
        if end not in text:
            raise ValueError(f"{doc_path}: {start} without {end}")
        pattern = re.compile(re.escape(start) + r"\n(.*?)\n" + re.escape(end), re.S)
        m = pattern.search(text)
        current = m.group(1) if m else ""
        fresh = _rebase_links(render_markdown(name, repo, live), depth)
        out.append((name, current, fresh, pattern))
    return out


def differing_blocks(doc_path: pathlib.Path, repo: dict[str, Any], live: dict[str, Any] | None,
                     root: pathlib.Path = REPO) -> list[tuple[str, str]]:
    """Blocks whose current body differs from a fresh render, with the first
    differing line of each, as `name` and `-old / +new`."""
    out = []
    for name, current, fresh, _pattern in _block_bodies(doc_path, repo, live, root):
        if current != fresh:
            cur_lines, new_lines = current.splitlines(), fresh.splitlines()
            for i in range(max(len(cur_lines), len(new_lines))):
                a = cur_lines[i] if i < len(cur_lines) else "<missing>"
                b = new_lines[i] if i < len(new_lines) else "<missing>"
                if a != b:
                    out.append((name, f"line {i + 1}: -{a[:120]!r} +{b[:120]!r}"))
                    break
    return out


def restore_blocks(doc_path: pathlib.Path, repo: dict[str, Any], live: dict[str, Any] | None,
                   root: pathlib.Path = REPO) -> list[str]:
    """Rewrite every block that differs from a fresh render; return their names.

    The blocks are the workflow's, rendered from the frozen snapshot before the
    model runs and told to the model as off-limits. A model edit inside one is
    overwritten with the authoritative render and REPORTED by name, rather than
    failing the whole refresh: the correct bytes are known exactly, and the
    prose around the block still goes through every gate. A start marker
    without its end is not restorable and raises, as insert_blocks does.
    """
    names = [name for name, _first_diff in differing_blocks(doc_path, repo, live, root)]
    if names:
        insert_blocks(doc_path, repo, live, root=root)
    return names


def insert_blocks(doc_path: pathlib.Path, repo: dict[str, Any], live: dict[str, Any] | None,
                  root: pathlib.Path = REPO) -> bool:
    """Replace every marker block in doc_path with freshly rendered content.

    Returns True when the file changed. Idempotent: rendering the same inputs
    twice yields the same bytes. Links inside the blocks are rebased to the
    document's directory (docs/product/infrastructure/05-e-API.md links to ../../../platform/...).
    """
    text = doc_path.read_text()
    new = text
    try:
        depth = len(doc_path.resolve().relative_to(root.resolve()).parents) - 1
    except ValueError:
        depth = 0
    for name in SECTIONS:
        start, end = MARKER_START.format(name=name), MARKER_END.format(name=name)
        if start not in new:
            continue
        if end not in new:
            raise ValueError(f"{doc_path}: {start} without {end}")
        body = _rebase_links(render_markdown(name, repo, live), depth)
        pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
        new = pattern.sub(lambda _m: f"{start}\n{body}\n{end}", new, count=1)
    if new != text:
        doc_path.write_text(new)
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--live", action="store_true", help="read live GCP state via gcloud")
    ap.add_argument("--snapshot", help="use a saved live snapshot instead of gcloud")
    ap.add_argument("--write-snapshot", help="write the live snapshot to this path")
    ap.add_argument("--db-tables", help="CSV of relname,n_live_tup,size (from scripts/db_query_cr.sh) to merge as live db_tables")
    ap.add_argument("--db-live", action="store_true", help="read live table stats via gcp.database (needs Cloud SQL env)")
    ap.add_argument("--json", action="store_true", help="print the combined inventory as JSON")
    ap.add_argument("--markdown", choices=SECTIONS, help="print one rendered section")
    ap.add_argument("--insert", nargs="*", help="rewrite marker blocks in these docs")
    ap.add_argument("--restore", nargs="*", help="rewrite only the marker blocks that differ from a fresh render, and name each one")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root)
    repo = repo_inventory(root)
    live = None
    if args.snapshot:
        live = json.loads(pathlib.Path(args.snapshot).read_text())
    elif args.live or args.write_snapshot:
        live = live_snapshot()
    if live is not None and args.db_tables:
        live["db_tables"] = db_tables_from_csv(pathlib.Path(args.db_tables))
    if live is not None and args.db_live:
        live["db_tables"] = db_tables_snapshot()
    if args.write_snapshot:
        pathlib.Path(args.write_snapshot).write_text(json.dumps(live, indent=1, sort_keys=True))
        print(f"wrote {args.write_snapshot}: {live['counts']}", file=sys.stderr)
    if args.markdown:
        print(render_markdown(args.markdown, repo, live))
    if args.restore is not None:
        default_docs = ["docs/product/infrastructure/05-a-ARCHITECTURE.md",
                        "docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md"]
        for doc in (args.restore or default_docs):
            for name in restore_blocks(root / doc, repo, live, root=root):
                print(f"restored inventory:{name} in {doc}")
    if args.insert is not None:
        default_docs = ["docs/product/infrastructure/05-a-ARCHITECTURE.md",
                        "docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md"]
        for doc in (args.insert or default_docs):
            changed = insert_blocks(root / doc, repo, live, root=root)
            print(f"{doc}: {'updated' if changed else 'unchanged'}", file=sys.stderr)
    if args.json:
        out = {"repo": repo}
        if live:
            out["live"] = live
            out["reconcile"] = reconcile(repo, live)
        print(json.dumps(out, indent=1, sort_keys=True, default=str))
    # `--restore` prints ONLY the names of the blocks it rewrote: the workflow
    # captures its stdout and turns every line into a `::warning::`, so the
    # summary below on that path would have flagged a rendered-block edit on
    # every run, touched or not.
    if not (args.markdown or args.json or args.insert is not None or args.restore is not None
            or args.write_snapshot):
        c = repo["counts"]
        print(f"repo: {c['jobs']} jobs, {c['schedulers']} schedulers, {c['tables']} tables, {c['routes']} routes in {c['routers']} routers")
        if live:
            print(f"live: {live['counts']}")
            print(json.dumps(reconcile(repo, live), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
