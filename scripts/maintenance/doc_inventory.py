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
import copy
import itertools
import datetime
import json
import os
import pathlib
import re
import subprocess
import tokenize
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


def _expand_helper_calls(body: str, funcs: dict) -> str:
    """Append the body of every `$(helper)` the function calls, when `helper`
    is a function defined in the same file.

    deploy.sh declares apply-schema-migrations' flags ONCE, in
    `_apply_schema_job_flags`, used by both its bootstrap create and the
    serialized in-build update (#1022); the flags must be read from there or
    the job renders with Cloud Run defaults. One level only.
    """
    extra = []
    for m in re.finditer(r"\$\(([A-Za-z_][A-Za-z0-9_]*)\)", body):
        helper = m.group(1)
        if helper in funcs:
            extra.append(funcs[helper][1])
    return body + "\n" + "\n".join(extra) if extra else body


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
        body = _expand_helper_calls(body, funcs)
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
                "env": _env_vars(body),
                "uses_secrets": "--set-secrets" in body or "DB_SECRET_FLAG" in body,
                "service_account": _flag(body, "service-account") or "",
                "timeout_defaulted": _flag(body, "task-timeout") is None,
                "retries_defaulted": _flag(body, "max-retries") is None,
            }
    return sorted(rows.values(), key=lambda r: r["name"])


def _expand_shell_locals(body: str) -> str:
    """Substitute `${NAME}` from a `NAME=<bare word>` assignment in the same
    body.

    `magnitude-engine` declares `MAG_PLAN=${plan_default}` two lines under
    `local plan_default=no_backfill`, so without this its plan reads as
    undeclared -- and the whole point of a declared environment is telling
    the job that HAS a plan from the job that does not. Only a bare word is
    substituted: a value carrying a space, a quote or another expansion is
    left alone rather than guessed at.
    """
    vals: dict[str, str] = {}
    for m in re.finditer(r"^\s*(?:local\s+)?([a-z_][a-z0-9_]*)=([A-Za-z0-9_.:/-]+)\s*$",
                         body, re.M):
        vals.setdefault(m.group(1), m.group(2))
    if not vals:
        return body
    return re.sub(r"\$\{([a-z_][a-z0-9_]*)\}",
                  lambda m: vals.get(m.group(1), m.group(0)), body)


def _env_vars(body: str) -> dict[str, str]:
    """`KEY=value` pairs a deploy function passes with --set-env-vars, whether
    inline or built up in a `non_secret_env="${non_secret_env},KEY=value"`
    chain. audit-walkforward's real workload is
    `AUDIT_SCRIPT_MODULE=scripts.analysis.per_factor_walkforward`, run by
    gcp/audit_job_runner.py in a subprocess. (Codex, PR #1044.)"""
    out: dict[str, str] = {}
    body = _expand_shell_locals(body)
    for m in re.finditer(r'(?:_env="\$\{[a-z_]+\},|_env="|--(?:set|update)-env-vars[ =]"?)([^"\n]*)', body):
        for pair in m.group(1).split(","):
            k, eq, v = pair.partition("=")
            if eq and re.fullmatch(r"[A-Z][A-Z0-9_]*", k.strip()) and "${" not in v:
                out.setdefault(k.strip(), v.strip())
    return out


def _configured_modules(root: pathlib.Path, job: dict[str, Any]) -> list[str]:
    """Repo modules a job names outside its entry command: env values and
    args of the form `gcp.a.b` / `scripts.a.b` / `lib.a` that resolve to a
    file. A wrapper such as gcp/audit_job_runner.py runs them in a
    subprocess, so they are roots of the job's reachable code."""
    text = " ".join([job.get("args", ""), *[str(v) for v in (job.get("env") or {}).values()]])
    out: list[str] = []
    for m in re.finditer(r"\b((?:gcp|lib|scripts)(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\b", text):
        f = _module_file(root, m.group(1).split("."))
        if f and f not in out and f != entry_module(job) and f != "gcp/database.py":
            out.append(f)
    return out


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
    declared = [x["name"] for x in schema["tables"]] \
        + [x["name"] for x in schema["materialized_views"]] \
        + [x["name"] for x in schema["views"]]
    # A declared relation can be named at run time too:
    # `market_data_intraday_iwm` is a schema partition and
    # scripts/analysis/per_ticker_calibration.py:202 builds the name from the
    # ticker. Scanning the dynamic forms only over the runtime-created set left
    # it reported as never named in code. (Codex, PR #1044.)
    refs = table_refs(root)
    for tname, v in table_refs_dynamic(root, declared).items():
        for kind in ("writes", "reads", "mentions"):
            seen = {(x["file"], x["line"]) for x in refs[tname][kind]}
            refs[tname][kind].extend(x for x in v[kind] if (x["file"], x["line"]) not in seen)
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
        "table_refs": refs,
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
    r"\.to_sql\(|TRUNCATE|REFRESH\s+MATERIALIZED\s+VIEW|CREATE\s+TABLE|ON\s+CONFLICT|(?<!\.)\bCOPY\b", re.I)
# `(?<!\.)` on JOIN: `'\\n'.join(lines)` is string code, not SQL, and with re.I
# it read as a JOIN and coloured the docstring below it as a read of `trades`
# (lib/backtest.py:326 -- Codex, PR #1044).
# What makes a multi-word string SQL rather than prose: an upper-case SQL
# keyword, or a lower-case statement head. "derives from x" has neither.
# `AND`, `OR` and `AS` are NOT in this list. They carry no SQL shape of their
# own, and lib/gamma_glossary.py:259-260 writes a display formula
# "|distance from spot| > 5% AND |GEX| growth > 30% ... economic_events row":
# the upper-case AND alone kept it off the diagnostic list, and READ_RE then
# read the prose "from" as a SQL FROM and published that glossary as a reader
# of economic_events. A real statement carrying AND carries a clause keyword
# too. (Codex, PR #1044.)
_SQL_HINT = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TRUNCATE|REFRESH|COPY|WHERE|JOIN|VALUES|INTO|"
    r"RETURNING|LIMIT|GROUP BY|ORDER BY|ON CONFLICT|WITH|FROM|SET)\b"
    r"|(?i:\bselect\b.*\bfrom\b|\binsert\s+into\b|\bdelete\s+from\b|\bcreate\s+(?:table|index|view)\b|\bupdate\s+\w+\s+set\b)")
# `from gcp.helpers import build` is a Python import, not a SQL FROM, and
# READ_RE is case-insensitive: an import line in the three-line context window
# classified the reference below it as a read. An import touches no table, so
# it is neither a match source nor context. (Codex, PR #1044.)
_IMPORT_LINE = re.compile(r"^\s*(?:from\s+[\w.]+\s+import\b|import\s+[\w.]+)")
READ_RE = re.compile(r"\bFROM\b|(?<!\.)\bJOIN\b|SELECT|query_to_dataframe|read_sql|row_exists|pd\.read_sql", re.I)


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


def _str_elems(node: ast.AST) -> set[str]:
    """The string literals a value expression is built from: a constant, a
    sequence of them, or either arm of a conditional
    (`'etf_options_snapshots' if source == 'etf' else 'earnings_...'`)."""
    if isinstance(node, ast.Constant):
        return {node.value} if isinstance(node.value, str) else set()
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        out: set[str] = set()
        for e in node.elts:
            out |= _str_elems(e)
        return out
    if isinstance(node, ast.IfExp):
        return _str_elems(node.body) | _str_elems(node.orelse)
    return set()


def _keyed_elems(node: ast.AST) -> dict[str | None, set[str]]:
    """The string literals a value holds, per subscript key.

    A flat sequence answers under `None` (`_WEEKLY_VIEWS` -> the two view
    names). A sequence of dicts answers per key, so
    `CHECKS = [{"name": "playbook_cards", ...}, ...]` says that `check["name"]`
    is a table name while `check["ts_column"]` is not. (Codex, PR #1044.)
    """
    out: dict[str | None, set[str]] = {}
    if isinstance(node, ast.Dict):
        for k, v in zip(node.keys, node.values):
            vals = _str_elems(v)
            if isinstance(k, ast.Constant) and isinstance(k.value, str) and vals:
                out.setdefault(k.value, set()).update(vals)
        return out
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        for e in node.elts:
            for k, vals in _keyed_elems(e).items():
                out.setdefault(k, set()).update(vals)
        return out
    vals = _str_elems(node)
    if vals:
        out[None] = vals
    return out


def _literal_assigns(tree: ast.Module) -> list[tuple[str, str | None, set[str], int, tuple[int, int] | None]]:
    """Every literal binding of a name: `(name, subscript key, values, line,
    line bounds)`. Bounds are None for an assignment and the function body for
    a parameter default.

    `_WEEKLY_VIEWS = ("earnings_event_outcomes", "earnings_ticker_lean")` is
    the same kind of binding as `TABLE = "options_daily_features"`; only the
    scalar form was followed, so both weekly views lost their writer. A
    parameter default (`table: str = "intraday_gex_15m"`) binds the name for
    the length of the function. (Codex, PR #1044.)
    """
    out: list[tuple[str, str | None, set[str], int, tuple[int, int] | None]] = []
    # Module-level `NAME = {"SPY": "market_data_intraday_spy", ...}`: a
    # subscript with a RUN-TIME key resolves to the union of the values, which
    # is what `INTRADAY_TABLE_BY_TICKER[ticker]` in
    # gcp/research/p2_outcomes_grid.py:179 needs to reach its three partition
    # reads at :183. (Codex, PR #1044.)
    const_dicts: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) \
                and node.value.values \
                and all(isinstance(v, ast.Constant) and isinstance(v.value, str)
                        for v in node.value.values):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    const_dicts[tgt.id] = {v.value for v in node.value.values}
    # A literal passed to a same-module function binds that function's
    # parameter: `_add_gex_block(df, ticker, engine, table="realtime_gex_15m")`
    # at lib/features/intraday_gex.py:291 is what makes the `FROM {table}` at
    # :231 a real read. Values are UNIONED over the call sites, so a helper
    # called with two different tables keeps both. (Codex, PR #1044.)
    defs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    seeded: dict[tuple[str, str], tuple[set[str], int, tuple[int, int]]] = {}
    # A parameter any call site supplies with something other than a string
    # literal is UNKNOWN, and a partial set of literals would resolve a
    # template to names the other call paths never produce. Same rule the
    # argument observer already applies: one non-literal reopens everything.
    opaque: set[tuple[str, str]] = set()

    def _str_defaults(fn: ast.AST) -> dict[str, str | None]:
        """Each parameter's literal string default, or None when it has no
        default or a non-literal one. An OMITTED optional parameter takes its
        default rather than becoming unknown: `load()` beside
        `load("market_data_intraday")` must keep both, and suppressing the
        explicit literal dropped the second relation entirely.
        (Codex, PR #1044.)"""
        a = fn.args
        pos = list(a.posonlyargs) + list(a.args)
        pairs = list(zip(pos[len(pos) - len(a.defaults):], a.defaults)) \
            + list(zip(a.kwonlyargs, a.kw_defaults))
        out_: dict[str, str | None] = {p.arg: None for p in pos + list(a.kwonlyargs)}
        for prm, dflt in pairs:
            if isinstance(dflt, ast.Constant) and isinstance(dflt.value, str):
                out_[prm.arg] = dflt.value
        return out_

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        fn = defs.get(node.func.id)
        if fn is None:
            continue
        params = [a.arg for a in list(fn.args.posonlyargs) + list(fn.args.args)]
        every = params + [a.arg for a in fn.args.kwonlyargs]
        bounds = (fn.lineno, getattr(fn, "end_lineno", None) or fn.lineno)
        # `f(*args)` / `f(**kw)` can supply anything, so the call is an
        # observation that reopens every parameter rather than one to skip;
        # skipping it let a sibling call's literal stand for every invocation.
        # (Codex, PR #1044.)
        if any(isinstance(a, ast.Starred) for a in node.args) \
                or any(k.arg is None for k in node.keywords):
            opaque.update((fn.name, p) for p in every)
            continue
        supplied: list[tuple[str, ast.AST]] = [
            (params[i], a) for i, a in enumerate(node.args) if i < len(params)]
        supplied += [(k.arg, k.value) for k in node.keywords]
        named = {p for p, _v in supplied}
        defaults = _str_defaults(fn)
        for pname in every:
            if pname in named:
                continue
            key = (fn.name, pname)
            if defaults.get(pname) is None:
                opaque.add(key)
            else:
                vals, _ln, _b = seeded.get(key, (set(), bounds[0], bounds))
                seeded[key] = (vals | {defaults[pname]}, bounds[0], bounds)
        for pname, val in supplied:
            key = (fn.name, pname)
            if not (isinstance(val, ast.Constant) and isinstance(val.value, str)):
                opaque.add(key)
                continue
            vals, _ln, _b = seeded.get(key, (set(), bounds[0], bounds))
            seeded[key] = (vals | {val.value}, bounds[0], bounds)
    for key, (vals, ln, bounds) in seeded.items():
        if key in opaque:
            continue
        out.append((key[1], None, vals, ln, bounds))

    def walk(node: ast.AST, bounds: tuple[int, int] | None) -> None:
        # a binding made inside a function holds only in that function; one at
        # module or class level holds for the file
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bounds = (node.lineno, getattr(node, "end_lineno", None) or node.lineno)
            a = node.args
            pos = list(a.posonlyargs) + list(a.args)
            pairs = list(zip(pos[len(pos) - len(a.defaults):], a.defaults)) \
                + [(p, d) for p, d in zip(a.kwonlyargs, a.kw_defaults) if d is not None]
            for prm, dflt in pairs:
                for key, vals in _keyed_elems(dflt).items():
                    out.append((prm.arg, key, vals, dflt.lineno, bounds))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name) \
                    and value.value.id in const_dicts \
                    and not isinstance(value.slice, ast.Constant):
                for tgt in targets:
                    if isinstance(tgt, ast.Name):
                        out.append((tgt.id, None, set(const_dicts[value.value.id]),
                                    value.lineno, bounds))
            if value is not None:
                for key, vals in _keyed_elems(value).items():
                    for tgt in targets:
                        if isinstance(tgt, ast.Name):
                            out.append((tgt.id, key, vals, value.lineno, bounds))
                            if tgt.lineno != value.lineno:
                                out.append((tgt.id, key, vals, tgt.lineno, bounds))
        for child in ast.iter_child_nodes(node):
            walk(child, bounds)

    walk(tree, None)
    return out


def _bind_value_lines(tree: ast.Module) -> dict[str, set[int]]:
    """name -> lines where it appears as a value in a dict literal.

    `conn.execute(text("SELECT ... FROM pg_class WHERE relname = :v"), {"v": view})`
    binds the view NAME as a parameter; the statement reads pg_class, not the
    view, so a followed name in that position is not a reference to its table.
    (Codex, PR #1044.)
    """
    out: dict[str, set[int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for v in node.values:
                if isinstance(v, ast.Name):
                    out.setdefault(v.id, set()).add(v.lineno)
    return out


def _derives_from(tree: ast.Module) -> dict[str, set[str]]:
    """name -> the names its value is derived from, transitively.

    Not a value flow (`_name_flow`): `s_table = strat_features_table(tf)` does
    NOT give `s_table` the value of `tf`. It records that whatever constrains
    `tf` also constrains `s_table`, which is what lets a job's declared
    `--tf=15m` narrow a template whose placeholder is a local in another
    module. (Codex, PR #1044.)
    """
    direct: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            srcs = {s.id for s in ast.walk(node.value) if isinstance(s, ast.Name)}
            direct.setdefault(node.targets[0].id, set()).update(srcs - {node.targets[0].id})
    out: dict[str, set[str]] = {}
    for name in direct:
        seen, stack = set(), [name]
        while stack:
            n = stack.pop()
            for s in direct.get(n, ()):
                if s not in seen and len(seen) < 32:
                    seen.add(s)
                    stack.append(s)
        out[name] = seen
    return out


def _name_flow(tree: ast.Module) -> dict[str, list[tuple[str, tuple[int, int] | None]]]:
    """name -> the names it can flow into, each with the line range in which
    that name holds the value (None = the whole module).

    Three edges, which together carry `_WEEKLY_VIEWS` to the
    `REFRESH MATERIALIZED VIEW {view}` f-string: a `for` over the name binds
    its target inside the loop; a call passing the name binds the matching
    parameter inside the callee; and `b = a` binds `b`. (Codex, PR #1044.)
    """
    out: dict[str, list[tuple[str, tuple[int, int] | None]]] = {}
    defs = {n.name: n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def span(node: ast.AST) -> tuple[int, int]:
        return (node.lineno, getattr(node, "end_lineno", None) or node.lineno)

    def edge(src: str, dst: str, bounds: tuple[int, int] | None) -> None:
        if src != dst or bounds is not None:
            out.setdefault(src, []).append((dst, bounds))

    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.iter, ast.Name):
            tgts = node.target.elts if isinstance(node.target, ast.Tuple) else [node.target]
            for tg in tgts:
                if isinstance(tg, ast.Name):
                    edge(node.iter.id, tg.id, span(node))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in defs:
            fn = defs[node.func.id]
            params = [a.arg for a in list(fn.args.posonlyargs) + list(fn.args.args)]
            for pos, a in enumerate(node.args):
                if isinstance(a, ast.Name) and pos < len(params):
                    edge(a.id, params[pos], span(fn))
            for kw in node.keywords:
                if kw.arg and isinstance(kw.value, ast.Name):
                    edge(kw.value.id, kw.arg, span(fn))
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    edge(node.value.id, tgt.id, None)
    return out


_VALUE_CAP = 64
_BOUNDS_CAP = 16


_ENCLOSING_CACHE: dict[Any, list[tuple[int, int, str]]] = {}


def _enclosing_funcs(root: pathlib.Path, rel: str, line: int) -> list[str]:
    """The functions containing `line` in `rel`, innermost first."""
    sig = _sig(root / rel)
    if sig is None:
        return []
    if sig not in _ENCLOSING_CACHE:
        tree = _parsed(root / rel)
        _ENCLOSING_CACHE[sig] = sorted(
            ((n.lineno, getattr(n, "end_lineno", None) or n.lineno, n.name)
             for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))),
            key=lambda s: s[1] - s[0]) if tree is not None else []
    return [nm for lo, hi, nm in _ENCLOSING_CACHE[sig] if lo <= line <= hi]


def _resolved_values(root: pathlib.Path, rel: str, want: set[str] | None = None,
                     _depth: int = 0) -> dict[str, list[tuple[set[str], tuple[int, int] | None]]]:
    """The names in a module that provably hold one of a known set of string
    values, with the line range each binding holds over.

    Literal bindings (`_literal_assigns`) propagated along the name flow
    (`_name_flow`) to a fixed point, plus constants imported from another
    repo module -- `for tf in TIMEFRAMES` in strat_enrich_levels.py resolves
    only because `TIMEFRAMES` lives in strat_config.py. A name bound from a
    CALL stays unresolved, which is the honest answer for
    `cells = _parse_cells(os.environ.get("INFERENCE_CELLS"))`.
    (Codex, PR #1044.)

    `want` is demand-driven and is what makes this affordable: only the names
    that can flow INTO one of them are resolved, and only the imports those
    names come from are followed. Resolving every name in every scanned module
    and its imports cost 30 s on this repo against 6 s for the whole scan.
    """
    tree = _parsed(root / rel)
    if tree is None:
        return {}
    sig = _sig(root / rel)
    key = (sig, _depth, frozenset(want) if want else None) if sig is not None else None
    if key is not None and key in _VALUES_CACHE:
        return _VALUES_CACHE[key]
    out: dict[str, list[tuple[set[str], tuple[int, int] | None]]] = {}
    flow = _name_flow(tree)
    need: set[str] | None = None
    if want:
        rev: dict[str, set[str]] = {}
        for src, edges in flow.items():
            for dst, _b in edges:
                rev.setdefault(dst, set()).add(src)
        need, stack = set(want), list(want)
        while stack:
            n = stack.pop()
            for s in rev.get(n, ()):
                if s not in need:
                    need.add(s)
                    stack.append(s)

    def add(name: str, vals: set[str], bounds: tuple[int, int] | None) -> bool:
        # Bounded: a name with a huge value set or bound in dozens of scopes
        # resolves nothing useful, and propagating it makes the fixed point
        # quadratic in a file's call graph.
        if (need is not None and name not in need) or len(vals) > _VALUE_CAP:
            return False
        for i, (have, b) in enumerate(out.get(name, [])):
            if b == bounds:
                if vals <= have:
                    return False
                merged = have | vals
                out[name][i] = (merged if len(merged) <= _VALUE_CAP else have, b)
                return len(merged) <= _VALUE_CAP
        if len(out.get(name, ())) >= _BOUNDS_CAP:
            return False
        out.setdefault(name, []).append((set(vals), bounds))
        return True

    for name, k, vals, _ln, bounds in _literal_assigns(tree):
        if k is None:
            add(name, vals, bounds)
    # constants this module imports by name from another repo module
    if _depth < 2:
        for local, targets in _bindings(root, rel).items():
            if need is not None and local not in need:
                continue
            for target, sym in targets:
                if sym and target != rel:
                    for vals, _b in _resolved_values(root, target, {sym}, _depth + 1).get(sym, []):
                        add(local, vals, None)
    for _ in range(4):
        changed = False
        for src, edges in flow.items():
            for vals, _b in list(out.get(src, [])):
                for dst, dbounds in edges:
                    changed |= add(dst, vals, dbounds)
        if not changed:
            break
    if key is not None:
        _VALUES_CACHE[key] = out
    return out


def _values_at(vals: dict[str, list[tuple[set[str], tuple[int, int] | None]]],
               name: str, line: int) -> set[str] | None:
    """The values `name` holds at `line`: the tightest binding covering it."""
    best: set[str] | None = None
    best_span = None
    for v, bounds in vals.get(name, []):
        if bounds is None:
            span = None
        elif bounds[0] <= line <= bounds[1]:
            span = bounds[1] - bounds[0]
        else:
            continue
        if best is None or (span is not None and (best_span is None or span < best_span)):
            best, best_span = v, span
    return best


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
    # The whole scan is a pure function of the file signatures and the table
    # list, and every render calls it. Without this the doc tests re-scanned
    # 400 files per test.
    ckey = (str(root), tuple(tables), tuple(_sig(f) for f in files))
    if ckey in _REFS_CACHE:
        return copy.deepcopy(_REFS_CACHE[ckey])
    pats = {t: re.compile(rf"(?<![\w.]){re.escape(t)}(?![\w])") for t in tables}
    out: dict[str, dict[str, list[dict[str, Any]]]] = {t: {"writes": [], "reads": [], "mentions": []} for t in tables}
    for f in files:
        rel = str(f.relative_to(root))
        try:
            lines = f.read_text().splitlines()
        except UnicodeDecodeError:
            continue
        lines = _strip_py_comments(lines)
        joined = "\n".join(lines)
        # Message text is not executed SQL, and it must not leak into the
        # context window of the lines after it either (Codex, PR #1009).
        # A diagnostic line (docstring, raise / log / print text) is neither a
        # match source nor context: it executes no SQL, and recording it as a
        # reference made lib/backtest.py's `"""Convert trades to a
        # DataFrame."""` a read of the trades table. (Codex, PR #1044.)
        diag = _diagnostic_lines(joined) | {n + 1 for n, ln in enumerate(lines) if _IMPORT_LINE.match(ln)}
        # A `#` comment executes nothing, so it is not context either. The
        # comment above `_WEEKLY_VIEWS` reads "earnings_ticker_lean is built
        # FROM earnings_event_outcomes", which made the tuple below it a READ
        # of both views. (Codex, PR #1044.)
        diag |= {n + 1 for n, ln in enumerate(lines) if ln.lstrip().startswith("#")}
        present = [(t, pat) for t, pat in pats.items() if t in joined]
        if not present:
            continue
        ctx_lines = ["" if n + 1 in diag else ln for n, ln in enumerate(lines)]
        # three AST walks, so only for a file that names at least one relation
        tree = _parsed(f)
        assigns = _literal_assigns(tree) if tree is not None else []
        flow = _name_flow(tree) if tree is not None else {}
        binds = _bind_value_lines(tree) if tree is not None else {}

        def classify(t: str, k: int, l2: str) -> None:
            # the followed line must itself carry the access; a context window
            # made `for view in _VIEWS:` a write of both views because the
            # REFRESH three lines above it was still in the window
            kind = "writes" if WRITE_RE.search(l2) else ("reads" if READ_RE.search(l2) else None)
            if kind is None:
                return
            hit = {"file": rel, "line": k + 1, "text": l2.strip()[:120]}
            if hit not in out[t][kind]:
                out[t][kind].append(hit)

        def use_pat(name: str, key: str | None) -> re.Pattern:
            if key is None:
                return re.compile(rf"\b{re.escape(name)}\b")
            return re.compile(rf"\b{re.escape(name)}\s*\[\s*(['\"]){re.escape(key)}\1\s*\]")

        def follow(t: str, name: str, key: str | None, bounds: tuple[int, int] | None,
                   skip: int, seen: set) -> None:
            """Every use of `name` (under `key`, when the value came from a
            keyed container) inside `bounds` is a use of table `t`, and the
            names `name` flows into are followed from there."""
            if (name, key, bounds) in seen or len(seen) > 64:
                return
            seen.add((name, key, bounds))
            pat = use_pat(name, key)
            lo, hi = bounds or (1, len(lines))
            for k in range(lo - 1, min(hi, len(lines))):
                l2 = lines[k]
                if k == skip or k + 1 in diag or not pat.search(l2):
                    continue
                # every occurrence on this line is a bind-parameter value
                if key is None and len(pat.findall(l2)) <= sum(1 for ln in binds.get(name, ()) if ln == k + 1):
                    continue
                classify(t, k, l2)
            for dst, dbounds in flow.get(name, []):
                follow(t, dst, key, dbounds, -1, seen)

        for t, pat in present:
            for i, line in enumerate(lines):
                if i + 1 in diag or not pat.search(line):
                    continue
                ctx = "\n".join(ctx_lines[max(0, i - 3): i + 1])
                kind = "writes" if WRITE_RE.search(ctx) else ("reads" if READ_RE.search(ctx) else "mentions")
                out[t][kind].append({"file": rel, "line": i + 1, "text": line.strip()[:120]})
            # `TABLE = "options_daily_features"` then `upsert_dataframe(df, TABLE, ...)`,
            # and `_WEEKLY_VIEWS = ("a", "b")` then `for view in _WEEKLY_VIEWS:
            # _refresh_one(view)`: follow the bound name to where it is used.
            for name, key, vals, ln, bounds in assigns:
                if t in vals and ln not in diag:
                    follow(t, name, key, bounds, ln - 1, set())
    _REFS_CACHE[ckey] = copy.deepcopy(out)
    return out


_PLACEHOLDER = r"[A-Za-z0-9]+"


def _accepts(fn: ast.AST, call: ast.Call) -> bool:
    """Whether `call`'s shape can be a call of `fn`.

    Branch-local imports bind different functions to one name
    (`walk_forward` in direction_program/baseline_runner.py is the magnitude
    one under `axis == "size"` and the strat one under `"type"`), and
    attributing every call to the first binding let a 3-argument call blank
    the 4-parameter function's constraints. (Codex, PR #1044.) Unknown
    shapes (a starred argument, `**kwargs`) count as accepted, so ambiguity
    loosens rather than prunes.
    """
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    a = fn.args
    if any(isinstance(x, ast.Starred) for x in call.args) or any(k.arg is None for k in call.keywords):
        return True
    pos = list(a.posonlyargs) + list(a.args)
    n_pos = len(call.args)
    if n_pos > len(pos) and a.vararg is None:
        return False
    names = {x.arg for x in pos} | {x.arg for x in a.kwonlyargs}
    kwargs = {k.arg for k in call.keywords}
    if a.kwarg is None and not kwargs <= names:
        return False
    if len(kwargs & {x.arg for x in pos[:n_pos]}) and a.kwarg is None:
        return False                      # a parameter filled twice
    n_required = len(pos) - len(a.defaults)
    for idx, prm in enumerate(pos[:n_required]):
        if idx >= n_pos and prm.arg not in kwargs:
            return False
    for prm, dflt in zip(a.kwonlyargs, a.kw_defaults):
        if dflt is None and prm.arg not in kwargs:
            return False
    return True


def _conditional_holes(tree: ast.Module, lineno: int) -> dict[str, set[str]]:
    """The literal values a conditional expression on `lineno` restricts a name
    to, keyed by that name.

    `scripts/analysis/per_ticker_calibration.py:202` builds a suffixed
    partition only for four tickers:

        partition = f"market_data_intraday_{t.lower()}" \
            if t.upper() in ("SPY", "IWM", "QQQ", "SPX") else "market_data_intraday"

    Matching the template against every declared name invented a read of
    `market_data_intraday_other`, a partition this branch cannot name.
    Only the `in`-a-tuple and `==` forms are read, and only when the tested
    expression is the bare name or one case transform of it; anything else
    leaves the template unfiltered. (Codex, PR #1044.)
    """
    out: dict[str, set[str]] = {}

    def base(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Call) and not node.args and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("lower", "upper") and isinstance(node.func.value, ast.Name):
            return node.func.value.id
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.IfExp):
            continue
        body = node.body
        if not (getattr(body, "lineno", 0) <= lineno <= getattr(body, "end_lineno", 0)):
            continue
        test = node.test
        if not (isinstance(test, ast.Compare) and len(test.ops) == 1):
            continue
        name = base(test.left)
        if name is None:
            continue
        right = test.comparators[0]
        if isinstance(test.ops[0], ast.In) and isinstance(right, (ast.Tuple, ast.List, ast.Set)) \
                and right.elts and all(isinstance(e, ast.Constant) and isinstance(e.value, str)
                                       for e in right.elts):
            out.setdefault(name, set()).update(e.value for e in right.elts)
        elif isinstance(test.ops[0], ast.Eq) and isinstance(right, ast.Constant) \
                and isinstance(right.value, str):
            out.setdefault(name, set()).add(right.value)
    return out


_HOLE_NAME = re.compile(r"^\s*([A-Za-z_]\w*)\s*(?:\.\s*(?:lower|upper)\s*\(\s*\))?\s*$")


def _conditional_ok(form: dict[str, Any], values: tuple[str, ...],
                    cond: dict[str, set[str]]) -> bool:
    """Whether a candidate name's placeholder values are ones the enclosing
    conditional allows. Case-insensitive, because the branch tests `t.upper()`
    while the template writes `t.lower()`."""
    if not cond:
        return True
    for j, hole in enumerate(form.get("exprs") or form["holes"]):
        if not hole or j >= len(values) or values[j] is None:
            continue
        m = _HOLE_NAME.match(hole)
        if not m or m.group(1) not in cond:
            continue
        if values[j].casefold() not in {v.casefold() for v in cond[m.group(1)]}:
            return False
    return True


def _dynamic_forms(line: str) -> list[dict[str, Any]]:
    """Every run-time-assembled table name a source line can produce.

    Each form carries the regex (every placeholder is ONE underscore-free
    segment, and the whole candidate name must match, so
    `f"strat_features_{tf_label}"` names `strat_features_15m` and never
    `strat_features_levels_15m`), the static parts, and the placeholder
    EXPRESSIONS. The expressions are what lets a caller resolve the form to
    the names it can really produce instead of to every live name that
    happens to match. (Codex, PR #1044.)
    """
    out: list[dict[str, Any]] = []

    def emit(parts: list[str], holes: list[str | None],
             pre: bool = False, post: bool = False,
             exprs: list[str] | None = None) -> None:
        static = "".join(parts)
        # `FROM {table}` has no static part at all, so as a pattern it matches
        # every relation; it is emitted anyway, marked `bare`, and used ONLY
        # where the placeholder resolves to literal values -- which is exactly
        # the `realtime_gex_15m` case this analyzer could not see before.
        # (Codex, PR #1044.)
        bare = (static == "" and parts == ["", ""] and not pre and not post
                # only a bare NAME can resolve, and only a line carrying a SQL
                # clause keyword can be a relation reference: without both,
                # every `{x}` in every f-string would enter the resolver
                and len(holes) == 1 and holes[0] is not None
                and _SQL_HINT.search(line) is not None)
        if any(ch in static for ch in " ()\\"):
            return
        if not bare and ("_" not in static or not any(len(x) >= 2 for x in parts)):
            return
        pat = _PLACEHOLDER.join(re.escape(x) for x in parts)
        pat = (_PLACEHOLDER if pre else "") + pat + (_PLACEHOLDER if post else "")
        cap = f"({_PLACEHOLDER})"
        cpat = cap.join(re.escape(x) for x in parts)
        cpat = (cap if pre else "") + cpat + (cap if post else "")
        if any(f["pat"] == pat for f in out):
            return
        out.append({"pat": pat, "cpat": cpat, "parts": parts, "holes": holes, "bare": bare,
                    # the placeholder's SOURCE text, kept beside `holes`
                    # because `holes` carries only bare names: `{t.lower()}`
                    # is not a name and reads as None there, which left the
                    # enclosing conditional unable to say which values it can
                    # take. (Codex, PR #1044.)
                    "exprs": list(exprs if exprs is not None else holes),
                    "pre": pre, "post": post,
                    "text": ("{?}" if pre else "")
                            + "".join(a + ("{" + (holes[i] or "?") + "}" if i < len(holes) else "")
                                      for i, a in enumerate(parts))
                            + ("{?}" if post else "")})

    for m in re.finditer(r"(?P<pre>\+\s*)?(?P<f>[fF]?)(?P<q>[\"'])(?P<body>(?:(?!(?P=q)).)*)(?P=q)(?P<post>\s*\+)?", line):
        body, is_f = m.group("body"), bool(m.group("f"))
        pre, post = bool(m.group("pre")), bool(m.group("post"))
        if is_f and "{" in body:
            hole = r"\{[^{}]*\}"
        elif "%s" in body or "%d" in body or re.search(r"%\(\w+\)[sd]", body):
            hole = r"%\(\w+\)[sd]|%[sd]"
        elif "{}" in body or re.search(r"\{\w+\}", body):
            hole = r"\{\w*\}"
        else:
            hole = ""
        if hole:
            # The name template is the whitespace-delimited token holding the
            # placeholder: `INSERT INTO strat_features_{tf} VALUES (1)` ->
            # `strat_features_{tf}`. Holes are masked before the split, because
            # a hole may itself contain a split character:
            # `f"market_data_intraday_{t.lower()}"` split on the parentheses
            # and the token no longer held a whole placeholder, so a declared
            # partition read looked like no reference at all. (Codex, PR #1044.)
            found: list[str] = []

            def _mask(m: re.Match) -> str:
                found.append(m.group(0))
                return f"\x00{len(found) - 1}\x00"

            masked = re.sub(hole, _mask, body)
            for token in re.split(r"[\s(),;=]+", masked):
                if "\x00" not in token:
                    continue
                parts, names, exprs = [], [], []
                pos = 0
                for m in re.finditer(r"\x00(\d+)\x00", token):
                    parts.append(token[pos:m.start()])
                    pos = m.end()
                    h = found[int(m.group(1))]
                    inner = h[1:-1].strip() if h.startswith("{") else ""
                    names.append(inner if re.fullmatch(r"[A-Za-z_]\w*", inner) else None)
                    exprs.append(inner)
                parts.append(token[pos:])
                emit(parts, names, exprs=exprs)
        elif pre or post:
            # `"INSERT INTO strat_features_levels_" + tf`: the name template is
            # the token adjacent to the `+`; the operand is not read back here.
            tokens = re.split(r"[\s(),;=]+", body.strip())
            if post and tokens:
                emit([tokens[-1]], [], False, True)
            if pre and tokens:
                emit([tokens[0]], [], True, False)
    return out


def _dynamic_templates(line: str) -> list[str]:
    """Regexes for the table names a source line can assemble at run time."""
    return [f["pat"] for f in _dynamic_forms(line)]


def _scan_files(root: pathlib.Path) -> list[str]:
    """Production .py files, repo-relative: the set table_refs scans."""
    out: list[str] = []
    for d in SCAN_DIRS:
        for f in (root / d).rglob("*.py"):
            rel = str(f.relative_to(root))
            if "/tests/" in rel or rel.startswith("tests/") or "/_archive/" in rel \
                    or "/__pycache__/" in rel or rel in DOC_TOOLING:
                continue
            out.append(rel)
    return sorted(out)


def table_refs_dynamic(root: pathlib.Path, tables: list[str]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """References to tables whose names are assembled at run time.

    `strat_features_1m` is written as `f"strat_features_{tf_label}"` and the
    literal scan cannot see it. Every string template on a non-diagnostic
    line (see _dynamic_templates) is matched in full against each live name;
    a hit is classified write / read / mention by the same context rule as
    table_refs. An assigned name is followed to its use sites, and a name
    RETURNED by a helper is followed to that helper's calls -- in the
    defining module and in every module that imports it, since
    `strat_config.strat_features_table()` is called from
    `mag_inference.py`. (Codex, PR #1044.)
    """
    scanned = _scan_files(root)
    ckey = (str(root), tuple(tables), tuple(_sig(root / r) for r in scanned))
    if ckey in _DYN_CACHE:
        return copy.deepcopy(_DYN_CACHE[ckey])
    out: dict[str, dict[str, list[dict[str, Any]]]] = {t: {"writes": [], "reads": [], "mentions": []} for t in tables}
    # every file once: its lines, its diagnostic line numbers, and the
    # context view with those lines blanked
    src: dict[str, tuple[list[str], set[int], list[str]]] = {}
    for rel in scanned:
        try:
            lines = (root / rel).read_text().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        diag = _diagnostic_lines("\n".join(lines)) | {n + 1 for n, ln in enumerate(lines) if _IMPORT_LINE.match(ln)}
        src[rel] = (lines, diag, ["" if n + 1 in diag else ln for n, ln in enumerate(lines)])
    # (defining file, symbol) -> [(importing file, local name)]
    importers: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for rel in src:
        for local, targets in _bindings(root, rel).items():
            for target, sym in targets:
                if sym:
                    importers.setdefault((target, sym), []).append((rel, local))
    seen: dict[tuple[str, str], set[int]] = {}
    _scopes: dict[str, list[tuple[int, int]]] = {}

    def _enclosing(rel: str, line: int) -> tuple[int, int] | None:
        """The innermost function containing `line`, as (first, last)."""
        if rel not in _scopes:
            tree = _parsed(root / rel)
            _scopes[rel] = sorted(
                ((n.lineno, getattr(n, "end_lineno", None) or n.lineno)
                 for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))),
                key=lambda s: s[1] - s[0]) if tree is not None else []
        for lo, hi in _scopes[rel]:
            if lo <= line <= hi:
                return (lo, hi)
        return None

    def record(t: str, rel: str, kind: str, k: int, text: str,
               form: dict[str, Any] | None = None) -> None:
        marks = seen.setdefault((t, rel), set())
        if k + 1 not in marks:
            marks.add(k + 1)
            hit = {"file": rel, "line": k + 1, "text": text.strip()[:120], "dynamic": True}
            if form is not None:
                hit["resolved"] = bool(form.get("resolved"))
                hit["template"] = form["text"]
                if form.get("origins"):
                    hit["origins"] = sorted(form["origins"])
                if form.get("vars", {}).get(t):
                    hit["vars"] = list(form["vars"][t])
            out[t][kind].append(hit)

    def follow(t: str, rel: str, name_re: re.Pattern, skip: int, depth: int = 0,
               form: dict[str, Any] | None = None,
               bounds: tuple[int, int] | None = None) -> None:
        """Every non-diagnostic line in `rel` using `name_re` is a use of the
        table; an assignment there is followed one level further, INSIDE the
        function that made it.

        Following a propagated name across the whole module let common locals
        (`table` -> `sql` -> `df` -> `out`) reach unrelated code: `out =
        df.copy()` in `_capitalize_ohlcv` was cited as a write of every
        `strat_features_*` relation. (Codex, PR #1044.)
        """
        if rel not in src:
            return
        lines, diag, ctx_lines = src[rel]
        lo, hi = bounds or (1, len(lines))
        for k in range(lo - 1, min(hi, len(lines))):
            l2 = lines[k]
            if k == skip or k + 1 in diag or not name_re.search(l2) or l2.lstrip().startswith("#"):
                continue
            ctx2 = "\n".join(ctx_lines[max(0, k - 3): k + 1])
            if WRITE_RE.search(ctx2):
                record(t, rel, "writes", k, l2, form)
            elif READ_RE.search(ctx2):
                record(t, rel, "reads", k, l2, form)
            else:
                record(t, rel, "mentions", k, l2, form)
            am = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*\w+)?\s*=\s*", l2)
            if am and depth < 2:
                follow(t, rel, re.compile(rf"\b{re.escape(am.group(1))}\b"), k, depth + 1,
                       form, _enclosing(rel, k + 1))

    for rel, (lines, diag, ctx_lines) in src.items():
        forms_at: dict[int, list[dict[str, Any]]] = {}
        for i, line in enumerate(lines):
            if i + 1 in diag or line.lstrip().startswith("#"):
                continue
            if "{" in line or "%" in line or "+" in line:
                fs = _dynamic_forms(line)
                if fs:
                    forms_at[i] = fs
        if not forms_at:
            continue
        # line -> the innermost function that returns on that line, for
        # `def levels_table(tf): return f"strat_features_levels_{tf}"`
        returning_func: dict[int, str] = {}
        tree = _parsed(root / rel)
        if tree is not None:
            for fn_node in ast.walk(tree):
                if isinstance(fn_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for r in ast.walk(fn_node):
                        if isinstance(r, ast.Return):
                            returning_func[r.lineno] = fn_node.name
        # resolving a module's literal values means parsing it and everything
        # it imports, so only do it where a template has a name to resolve
        holes = {h for fs in forms_at.values() for f in fs for h in f["holes"] if h}
        values = _resolved_values(root, rel, holes) if holes else {}
        derives = _derives_from(tree) if (tree is not None and holes) else {}
        for i, forms in forms_at.items():
            line = lines[i]
            # Resolve each form to the names its placeholders can really take;
            # only a form whose values are unknown falls back to "every live
            # name this pattern matches", and it is marked so the digest can
            # say the timeframe is chosen at run time rather than assert six
            # concrete reads. (Codex, PR #1044.)
            hits: list[tuple[str, dict[str, Any]]] = []
            tableset = set(tables)
            cond = _conditional_holes(tree, i + 1) if tree is not None else {}
            for form in forms:
                vs = None
                if form["holes"] and not form["pre"] and not form["post"] \
                        and all(h for h in form["holes"]):
                    vs = [_values_at(values, h, i + 1) for h in form["holes"]]
                    vs = None if any(v is None for v in vs) else vs
                if vs is not None:
                    form["resolved"] = True
                    # recorded even on the resolved path, because a copy of
                    # this form followed into an IMPORTING module is unresolved
                    # there (its caller may pass anything) and needs them
                    form["origins"] = {h for h in form["holes"] if h} | {
                        o for h in form["holes"] if h for o in derives.get(h, ())}
                    form.setdefault("vars", {})
                    for combo in itertools.product(*vs):
                        name = "".join(a + (combo[j] if j < len(combo) else "")
                                       for j, a in enumerate(form["parts"]))
                        if name in tableset and _conditional_ok(form, combo, cond):
                            form["vars"][name] = combo
                            hits.append((name, form))
                elif form.get("bare"):
                    continue        # a bare pattern matches every relation
                else:
                    form["resolved"] = False
                    # the names that constrain this placeholder, so a job's
                    # declared CLI value can narrow the family later
                    form["origins"] = {h for h in form["holes"] if h} | {
                        o for h in form["holes"] if h for o in derives.get(h, ())}
                    cpt = re.compile(form["cpat"])
                    form.setdefault("vars", {})
                    for tname in tables:
                        m = cpt.fullmatch(tname)
                        if m and _conditional_ok(form, m.groups(), cond):
                            form["vars"][tname] = m.groups()
                            hits.append((tname, form))
            if not hits:
                continue
            ctx = "\n".join(ctx_lines[max(0, i - 3): i + 1])
            kind = "writes" if WRITE_RE.search(ctx) else ("reads" if READ_RE.search(ctx) else "mentions")
            cm = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*\w+)?\s*=\s*", line)
            fn = returning_func.get(i + 1) if re.match(r"\s*return\b", line) else None
            for t, form in hits:
                record(t, rel, kind, i, line, form)
                # `table = f"strat_features_{tf_label}"` then `upsert_dataframe(feat, table, ...)`
                # further down: follow the name to where it is used, as table_refs does.
                if cm:
                    follow(t, rel, re.compile(rf"\b{re.escape(cm.group(1))}\b"), i, 0,
                           form, _enclosing(rel, i + 1))
                # `def levels_table(tf): return f"strat_features_levels_{tf}"` then
                # `bulk_copy_upsert(df, levels_table(tf))`: follow the helper's calls,
                # here and in every module that imports it.
                if fn:
                    follow(t, rel, re.compile(rf"(?<![\w.])(?<!def ){re.escape(fn)}\s*\("), i, 0, form)
                    for other, local in importers.get((rel, fn), []):
                        # the helper's values are the DEFINING module's; a
                        # caller elsewhere may pass anything
                        away = dict(form, resolved=False)
                        follow(t, other, re.compile(rf"(?<![\w.]){re.escape(local)}\s*\("), -1, 0, away)
    _DYN_CACHE[ckey] = copy.deepcopy(out)
    return out


def _strip_py_comments(lines: list[str]) -> list[str]:
    """`lines` with every `#` comment removed, using the tokenizer so a `#`
    inside a string literal survives.

    Blanking only lines that BEGIN with `#` left an inline comment searchable
    as executable code: `"hedge_nodes": [], # Phase D -- needs economic_events
    join` at platform/api/routers/grid.py:925 gave READ_RE a `join` beside the
    relation name and published that router as a reader of a table it never
    queries. A fully commented line becomes empty here, which subsumes the
    line-start rule. A file the tokenizer cannot read is returned unchanged.
    (Codex, PR #1044.)
    """
    cuts: dict[int, int] = {}
    it = iter([ln + "\n" for ln in lines])
    try:
        for tok in tokenize.generate_tokens(lambda: next(it, "")):
            if tok.type == tokenize.COMMENT:
                row, col = tok.start
                cuts[row] = min(cuts.get(row, col), col)
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        return list(lines)
    if not cuts:
        return list(lines)
    return [ln[: cuts[n + 1]].rstrip() if (n + 1) in cuts else ln
            for n, ln in enumerate(lines)]


def _diagnostic_lines(text: str) -> set[int]:
    """Line numbers whose content is a message, not executed SQL.

    `gcp/signal_monitor.py` raises a RuntimeError whose text tells the operator
    to run `UPDATE watchlists SET signals = TRUE ...`. The process only READS
    that table, but the string matched WRITE_RE, and the four-line context
    window then dragged the following log line in with it -- so the write graph
    cited two lines that execute nothing and the blast radius named
    signal-monitor a writer of watchlists. (Codex, PR #1009.)

    Covers string literals inside `raise ...`, logging calls, `print(...)`,
    `warnings.warn(...)`, module / class / function docstrings, and PROSE:
    any string of three or more words carrying no SQL keyword (a config
    value such as `"rationale": "VEX derives from gamma_levels_eod ..."` in
    scripts/audit_data_freshness.py made freshness-watchdog a reader of that
    table because the prose contains "from" -- Codex, PR #1044); and the
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

    # An f-string's literal fragments are not standalone strings: judge the
    # whole JoinedStr and skip its parts. `f"LEFT JOIN {l} l ON l.ticker =
    # s.ticker AND l.ts = s.ts "` carries JOIN, but its second fragment on its
    # own carries no clause keyword at all, so once AND stopped counting as
    # evidence every strat_features_levels_* read in the tree vanished.
    # (Codex, PR #1044.)
    in_fstring = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)
                  for v in n.values}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Constant, ast.JoinedStr)) and id(node) not in in_fstring:
            text = node.value if isinstance(node, ast.Constant) else "".join(
                v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
            if isinstance(text, str) and len(text.split()) >= 3 and not _SQL_HINT.search(text):
                out.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        if isinstance(node, ast.Raise):
            _mark(node)
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
            owner = (f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else "")
            if name in ("debug", "info", "warning", "warn", "error", "exception", "critical") \
                    or name == "print" or (owner == "warnings" and name == "warn"):
                _mark(node)
            # argparse documentation: `help='weekly = REFRESH MATERIALIZED
            # VIEW x 2; daily = rebuild earnings_upcoming_with_history'` quotes
            # SQL, so the prose rule does not reach it, and the second line was
            # a WRITE of that table. Nothing here executes. (Codex, PR #1044.)
            for kw in node.keywords:
                if kw.arg in ("help", "description", "epilog", "metavar"):
                    _mark(kw.value)
    return out


# Parsed trees and import bindings, keyed by path plus size and mtime so a
# file rewritten under the same path (tests do this) is re-read.
_AST_CACHE: dict[tuple[pathlib.Path, int, int], "ast.Module | None"] = {}
_BIND_CACHE: dict[tuple[pathlib.Path, int, int], dict[str, list[tuple[str, str | None]]]] = {}
# keyed by (file signature, recursion depth): a depth-2 result stops before
# resolving its own imports, so it must not be served to a depth-0 caller
_VALUES_CACHE: dict[Any, dict[str, list[tuple[set[str], tuple[int, int] | None]]]] = {}
# whole-scan results, keyed by root, table list and every scanned file's signature
_REFS_CACHE: dict[Any, dict[str, dict[str, list[dict[str, Any]]]]] = {}
_DYN_CACHE: dict[Any, dict[str, dict[str, list[dict[str, Any]]]]] = {}


def _sig(path: pathlib.Path) -> tuple[pathlib.Path, int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (path, st.st_size, st.st_mtime_ns)


def _parsed(path: pathlib.Path) -> "ast.Module | None":
    key = _sig(path)
    if key is None:
        return None
    if key not in _AST_CACHE:
        try:
            _AST_CACHE[key] = ast.parse(path.read_text())
        except (OSError, SyntaxError, UnicodeDecodeError):
            _AST_CACHE[key] = None
    return _AST_CACHE[key]


def _module_file(root: pathlib.Path, parts: list[str]) -> str | None:
    """Repo-relative file for a dotted module: `a/b.py`, else the package's
    `a/b/__init__.py`, else None (not repo code)."""
    if not parts or parts[0] not in ("gcp", "lib", "scripts"):
        return None
    for cand in (pathlib.Path(*parts).with_suffix(".py"), pathlib.Path(*parts) / "__init__.py"):
        if (root / cand).exists():
            return str(cand)
    return None


def _resolve_import(root: pathlib.Path, importer: str, module: str | None, level: int) -> list[str] | None:
    """Dotted parts of the module an `import` / `from ... import` names, with
    `from .x` / `from ..x` resolved against the importer's package. None when
    it points outside the repo."""
    if level:
        pkg = importer[:-3].split("/")[:-1]          # the importer's package directory
        if level > 1:
            pkg = pkg[: len(pkg) - (level - 1)]
        parts = pkg + (module.split(".") if module else [])
    else:
        parts = (module or "").split(".") if module else []
    return parts if parts and parts[0] in ("gcp", "lib", "scripts") else None


def _bind_from(root: pathlib.Path, rel: str, nodes: list[ast.AST]) -> dict[str, list[tuple[str, str | None]]]:
    """name bound by the import statements inside `nodes` (code in `rel`) ->
    every (repo file, symbol or None for a whole module) it can be bound to.
    A list, because branches import different functions under one local name
    (`walk_forward` in direction_program/baseline_runner.py is one of three,
    by axis) and the last one seen must not erase the others. (Codex, PR
    #1044.)

    `import gcp.a.b [as x]` binds `x` (or `gcp`, and the attribute chain is
    matched on use) to the module. `from gcp.a import n` binds `n` to the
    submodule `gcp/a/n.py` when one exists, else to the symbol `n` of
    `gcp/a.py` (or of the package's `__init__.py`). Relative forms resolve
    against the importer's package (Codex, PR #1044: `from .summarizers`
    in lib/agents/orchestrator.py was invisible and insight-pipeline lost
    every read behind it)."""
    out: dict[str, list[tuple[str, str | None]]] = {}

    def bind(name: str, target: tuple[str, str | None]) -> None:
        if target not in out.setdefault(name, []):
            out[name].append(target)

    for node in (sub for n in nodes for sub in ast.walk(n)):
        if isinstance(node, ast.Import):
            for a in node.names:
                parts = _resolve_import(root, rel, a.name, 0)
                f = _module_file(root, parts) if parts else None
                if f:
                    bind(a.asname or a.name, (f, None))
        elif isinstance(node, ast.ImportFrom):
            parts = _resolve_import(root, rel, node.module, node.level)
            if not parts:
                continue
            base = _module_file(root, parts)
            for a in node.names:
                if a.name == "*":
                    if base:
                        bind("*", (base, None))
                    continue
                sub = _module_file(root, parts + [a.name])
                if sub:
                    bind(a.asname or a.name, (sub, None))
                elif base:
                    bind(a.asname or a.name, (base, a.name))
    return out


def _bindings(root: pathlib.Path, rel: str) -> dict[str, list[tuple[str, str | None]]]:
    """Every import binding anywhere in `rel` (module-level and function-local)."""
    key = _sig(root / rel)
    if key is not None and key in _BIND_CACHE:
        return _BIND_CACHE[key]
    tree = _parsed(root / rel)
    out = _bind_from(root, rel, [tree]) if tree is not None else {}
    if key is not None:
        _BIND_CACHE[key] = out
    return out


_MODBIND_CACHE: dict[tuple[pathlib.Path, int, int], dict[str, list[tuple[str, str | None]]]] = {}


def _module_bindings(root: pathlib.Path, rel: str) -> dict[str, list[tuple[str, str | None]]]:
    """Bindings made by `rel`'s module-level statements only: the names any
    function in the module can see. A function-local import binds a name in
    that function alone and executes only when the function runs; treating
    every import in a file as module-wide made `StratClassifier` from
    lib/strat.py drag in the DataLoader imports of unrelated compute_strat_*
    functions, and backfill-daily-indicators read three tables it never
    touches. (Codex, PR #1044.)"""
    key = _sig(root / rel)
    if key is not None and key in _MODBIND_CACHE:
        return _MODBIND_CACHE[key]
    tree = _parsed(root / rel)
    top = [n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))] if tree else []
    out = _bind_from(root, rel, top)
    if key is not None:
        _MODBIND_CACHE[key] = out
    return out


def _local_imports(root: pathlib.Path, rel: str) -> set[str]:
    """Repo modules `rel` imports, as file paths (relative imports resolved)."""
    return {f for targets in _bindings(root, rel).values() for f, _sym in targets}


def _top_defs(tree: ast.Module) -> dict[str, ast.AST]:
    return {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _is_strlike(node: ast.AST) -> bool:
    """A value that is only text: a string constant, an f-string, string
    arithmetic, a container of those, or a method called on one
    (a triple-quoted DDL with `.format(x)` on it; `dedent(...)` is a Call on
    a Name and is NOT matched, so an executed module-level call keeps
    counting)."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp):
        return _is_strlike(node.left) and (_is_strlike(node.right) or isinstance(node.right, (ast.Tuple, ast.Dict, ast.Name)))
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return bool(node.elts) and all(_is_strlike(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return bool(node.values) and all(_is_strlike(v) for v in node.values)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return _is_strlike(node.func.value)
    return False


def _top_consts(tree: ast.Module) -> dict[str, ast.AST]:
    """Module-level `NAME = <text>` assignments. Building a string touches no
    table; the lines count only where a reached statement uses the name.
    (mag_walk_forward.py holds four DDL constants; magnitude-inference imports
    two, and the other two's CREATE TABLE text was attributed to it as a
    write -- Codex, PR #1044.)"""
    out: dict[str, ast.AST] = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and _is_strlike(n.value):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = n
        elif isinstance(n, ast.AnnAssign) and n.value is not None and _is_strlike(n.value) and isinstance(n.target, ast.Name):
            out[n.target.id] = n
    return out


def _lines_of(node: ast.AST) -> set[int]:
    return set(range(node.lineno, (getattr(node, "end_lineno", None) or node.lineno) + 1))


def _is_main_guard(node: ast.AST) -> bool:
    """`if __name__ == "__main__":` -- false while a module is imported."""
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    t = node.test
    names = [x for x in [t.left] + list(t.comparators) if isinstance(x, ast.Name) and x.id == "__name__"]
    consts = [x for x in [t.left] + list(t.comparators) if isinstance(x, ast.Constant) and x.value == "__main__"]
    return bool(names and consts)


def _dotted(node: ast.AST) -> str | None:
    """`a.b.c` for an Attribute chain rooted at a Name, else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _import_scope(root: pathlib.Path, mod_file: str,
                  argv: dict[str, set[str]] | None = None,
                  flag_sets: list[set[str]] | None = None,
                  out_args: dict[str, set[str] | None] | None = None,
                  env: tuple[dict[str, set[str]], set[str]] | None = None
                  ) -> dict[str, set[int] | None]:
    """The code a job can run, as {repo file: line numbers} (None = whole file).

    Symbol-level reachability rather than file membership: from the entry
    module (all of it) follow every imported NAME to its definition, then the
    names that definition uses, transitively, plus each reached module's
    module-level statements (they execute at import). A file-level closure
    attributed `build_materialized()`'s write of `options_daily_features` to
    the three magnitude jobs, which import only `add_options_features` from
    the same module and never call the writer. (Codex, PR #1044.)

    Rules: `import m` / `import m as x` reaches the attributes used on the
    alias, or all of `m` when the alias is used bare; `from m import *` reaches
    all of `m`; a reached class reaches its whole body; a name that is neither
    a definition nor an import in its module (a module-level assignment) is
    covered by the module-level lines; an imported module's
    `if __name__ == "__main__":` block is dormant and is not reached (it made
    earnings-reactions-brief a writer of every table premarket_brief.main()
    writes, through one imported helper -- Codex, PR #1044); every binding a
    name can have is followed. gcp/database.py writes job_runs for every job
    and is excluded at any depth.

    `flag_sets` is one set of flag names per way the job is invoked (its own
    args, then each scheduler override that replaces them) and `env` is the
    pair `declared_env` returns. Both scope the entry module: a value decides
    a branch only when EVERY invocation carries it, and a decided branch
    prunes the arm not taken plus, when the arm taken ends in a `return` or
    `raise`, everything after it.
    """
    scope: dict[str, set[int] | None] = {}
    seen_syms: set[tuple[str, str]] = set()
    seen_mods: set[str] = set()
    # Class methods are reached by NAME: a reached class contributes its
    # header, class-level statements and __init__; a method joins when its
    # name is used as an attribute anywhere in reached code (receiver types
    # are unknown, so the match is by name). A class reached only through a
    # type annotation contributed every method, and one `Optional[DataLoader]`
    # in lib/data_loader.py handed every DataLoader query to
    # earnings-reactions-brief. (Codex, PR #1044.)
    attr_names: set[str] = set()
    classes: dict[tuple[str, str], ast.ClassDef] = {}
    reached_methods: set[tuple[str, str, str]] = set()
    reached_consts: set[tuple[str, str]] = set()
    ALWAYS = {"__init__", "__new__", "__post_init__"}
    # Literal string arguments observed at every reached call of a function,
    # per parameter: a set of values, or None once any call passes something
    # else. A branch such as `if phase == "phase3":` inside the callee is
    # dormant when every observed value says so, and the code behind it is
    # not reached. feature_importance._load_axis() calls
    # load_magnitude_dataset(..., "phase0"), and the phase3-only
    # economic_events reader behind that gate had been attributed to
    # direction-importance. (Codex, PR #1044.)
    arg_lits: dict[tuple[str, str], dict[str, set[str] | None]] = {}
    walked_with: dict[tuple[str, str], str] = {}
    none_walking: set[tuple[str, str]] = set()
    managed_env_seen: dict[str, bool] = {}
    # The values the deployed job's CLI fixes, applied only inside the entry
    # module and only to names that hold a parsed argparse namespace. `main()`
    # is the whole file's root, so without this every mode of a multi-mode
    # entrypoint counted as reachable for every job configuration.
    # (Codex, PR #1044.)
    _entry_tree = _parsed(root / mod_file) if mod_file and (root / mod_file).exists() else None
    _ns_names, _dests, _bool_dests, _none_dests, _str_dests = _argparse_dests(_entry_tree) \
        if _entry_tree is not None else (set(), set(), {}, set(), {})
    _sets = flag_sets if flag_sets is not None else [set()]
    # An invocation that omits a scalar option sees its declared default, so
    # the default is one of the values the job runs with -- an OBSERVATION --
    # and it DECIDES a branch only when every invocation omits it, the same
    # split the passed values already use. `fetch-market-data` is deployed
    # without `--tickers` and declares default "ALL", so `args.tickers == 'ALL'`
    # is settled and the arm that splits a caller-supplied list is not code
    # that job runs; `signal-monitor` is scheduled twice with `--window` and
    # deployed once without, so "15m" joins its observed values and decides
    # nothing. (Codex, PR #1044.)
    _seen_default = {d: {v} for d, v in _str_dests.items()
                     if any(d not in fs for fs in _sets)} if _ns_names else {}
    _defaulted = {d: v for d, v in _seen_default.items()
                  if all(d not in fs for fs in _sets)}
    argv_cons = {k: v for k, v in (argv or {}).items() if k in _dests} if _ns_names else {}
    for _d, _v in _seen_default.items():
        argv_cons[_d] = argv_cons.get(_d, set()) | _v
    # Values for OBSERVATION are the union over every way the job is invoked;
    # values that DECIDE a branch must additionally be passed by every one of
    # them. `orb-15m` schedules `alpha` with `--window=15m` and the bare
    # deployment passes no `--window`, so `args.window == "15m"` is not a fact
    # about the job -- and once a decided branch also prunes what follows it,
    # reading it as one would delete the bare invocation's whole tail.
    argv_sure = {k: v for k, v in argv_cons.items()
                 if k in _defaulted or all(k in fs for fs in _sets)} if _ns_names else {}
    # A boolean switch the deployment does not pass takes its declared default.
    # `backtest-pipeline` is deployed with no args, so `--walk-forward` is
    # false and the walk-forward subprocess under `if run_wf:` cannot run;
    # excluding boolean dests entirely left that branch, and its
    # backtest_walk_forward_folds write, attributed to the base deployment.
    # (Codex, PR #1044.)
    bool_cons: dict[str, bool] = {}
    if _ns_names:
        for d, (on, off) in _bool_dests.items():
            seen = {on if d in fs else off for fs in _sets}
            if len(seen) == 1:
                bool_cons[d] = seen.pop()
        for d in _none_dests:
            if all(d not in fs for fs in _sets) and d not in (argv or {}):
                bool_cons.setdefault(d, False)

    # The environment the deployment fixes, read in the entry module only --
    # the same scoping as the declared command line, and for the same reason:
    # a value is a constraint on the code that was configured with it.
    env_cons, env_partial = (env or ({}, set()))
    env_managed = deployment_env_names(root)

    def argv_of(f: str) -> dict[str, set[str]]:
        return argv_cons if f == mod_file else {}

    def sure_of(f: str) -> dict[str, set[str]]:
        return argv_sure if f == mod_file else {}

    def bools_of(f: str) -> dict[str, bool]:
        return bool_cons if f == mod_file else {}

    def env_of(f: str) -> dict[str, set[str]]:
        return env_cons if f == mod_file else {}

    def reads_managed_env(f: str) -> bool:
        """Whether this module reads an environment variable the deploy script
        controls. A job that declares no environment of its own is still
        constrained by what it does NOT declare: `fetch-top-movers` reads
        `AV_API_KEY`, and the branch a job without `MAG_PLAN` cannot take is
        decided by the same absence."""
        if f in managed_env_seen:
            return managed_env_seen[f]
        tree = _parsed(root / f)
        here = env_of(f)
        managed_env_seen[f] = tree is not None and any(
            env_get(n, here) is not None for n in ast.walk(tree))
        return managed_env_seen[f]

    def env_get(node: ast.AST, env_here: dict[str, set[str]]) -> set[str] | None:
        """`os.environ.get(NAME, "<literal>")` / `os.getenv(...)` under the
        job's declared environment, or None when the value is not knowable.

        Only the two-argument form: `os.environ.get(NAME)` yields None rather
        than a string and `os.environ[NAME]` raises, and neither is worth
        guessing at.
        """
        if not isinstance(node, ast.Call) or len(node.args) != 2 or node.keywords:
            return None
        fn = node.func
        if not isinstance(fn, ast.Attribute):
            return None
        if not (fn.attr == "getenv"
                or (fn.attr == "get" and isinstance(fn.value, ast.Attribute)
                    and fn.value.attr == "environ")):
            return None
        name, dflt = node.args
        if not (isinstance(name, ast.Constant) and isinstance(name.value, str)):
            return None
        default = {dflt.value} if isinstance(dflt, ast.Constant) \
            and isinstance(dflt.value, str) else None
        if name.value in env_here:
            if name.value not in env_partial:
                return set(env_here[name.value])
            # set by some invocations only: the absent case is possible too
            return None if default is None else set(env_here[name.value]) | default
        if name.value in env_managed:
            return default
        return None

    def observe_call(target: tuple[str, str], call: ast.Call | None,
                     caller: dict[str, set[str] | None] | None = None,
                     argv_here: dict[str, set[str]] | None = None) -> bool:
        """Record the literal arguments of one call (None = a bare
        reference, everything unknown). True when the constraint set
        changed and the callee, if already walked, must be walked again."""
        tf, sym = target
        tree = _parsed(root / tf)
        fn = _top_defs(tree).get(sym) if tree is not None else None
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
        if call is not None and not _accepts(fn, call):
            return False
        params = [a.arg for a in fn.args.args]
        defaults = dict(zip(params[len(params) - len(fn.args.defaults):], fn.args.defaults))
        cons = arg_lits.setdefault(target, {})
        before = repr(sorted((k, sorted(v) if v else v) for k, v in cons.items()))
        caller = caller or {}
        if call is None or any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
            for pn in params:
                cons[pn] = None
        else:
            supplied: dict[str, ast.AST] = {}
            for pos, a in enumerate(call.args):
                if pos < len(params):
                    supplied[params[pos]] = a
            for kw in call.keywords:
                supplied[kw.arg] = kw.value
            for pn in params:
                val = supplied.get(pn, defaults.get(pn))
                # a literal, or a name the CALLER is itself constrained to:
                # walk_forward(engine, phase, ...) inside a function reached
                # only with phase="phase0" passes that constraint on, which
                # is what keeps the phase3-only reader out of the graph.
                # (Codex, PR #1044.)
                vals: set[str] | None = None
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    vals = {val.value}
                elif isinstance(val, ast.Name) and caller.get(val.id):
                    vals = set(caller[val.id])
                # `run_probe(engine, args.ticker, args.tf, ...)` in the entry
                # module, where the deployment fixes `--tf=15m`
                elif isinstance(val, ast.Attribute) and isinstance(val.value, ast.Name) \
                        and val.value.id in _ns_names and (argv_here or {}).get(val.attr):
                    vals = set(argv_here[val.attr])
                if vals is None:
                    cons[pn] = None
                elif cons.get(pn, set()) is not None:
                    cons.setdefault(pn, set()).update(vals)
        after = repr(sorted((k, sorted(v) if v else v) for k, v in cons.items()))
        return before != after

    def verdict(test: ast.AST, cons: dict[str, set[str] | None],
                argv_here: dict[str, set[str]] | None = None,
                bools_here: dict[str, bool] | None = None,
                env_here: dict[str, set[str]] | None = None,
                locals_here: dict[str, bool] | None = None) -> bool | None:
        """True / False when `cons`, the job's declared CLI values, its
        declared environment, or a boolean switch it does not pass decides the
        test, else None.

        `bools_here` is keyed by argparse dest and answers `args.<dest>` only;
        `locals_here` is keyed by local NAME. They are separate because a
        module may bind a local of the same name as a dest -- `plan =
        TASK_PLANS[args.plan]` -- and letting that unknown local erase the
        dest kept `if args.plan and ...` alive for a job that passes no
        `--plan`. (Codex, PR #1044.)
        """
        argv_here = argv_here or {}
        bools_here = bools_here or {}
        locals_here = locals_here or {}
        env_here = env_here if env_here is not None else {}
        ev = env_get(test, env_here)
        if ev is not None:
            truths = {bool(v) for v in ev}
            return truths.pop() if len(truths) == 1 else None
        if isinstance(test, ast.Attribute) and isinstance(test.value, ast.Name) \
                and test.value.id in _ns_names and test.attr in bools_here:
            return bools_here[test.attr]
        if isinstance(test, ast.Attribute) and isinstance(test.value, ast.Name) \
                and test.value.id in _ns_names and test.attr in argv_here:
            truths = {bool(v) for v in argv_here[test.attr]}
            return truths.pop() if len(truths) == 1 else None
        if isinstance(test, ast.Name) and test.id in locals_here:
            return locals_here[test.id]
        if isinstance(test, ast.Constant) and isinstance(test.value, bool):
            return test.value
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            v = verdict(test.operand, cons, argv_here, bools_here, env_here, locals_here)
            return None if v is None else not v
        if isinstance(test, ast.BoolOp):
            vs = [verdict(x, cons, argv_here, bools_here, env_here, locals_here)
                  for x in test.values]
            if isinstance(test.op, ast.And):
                return False if False in vs else (True if all(v is True for v in vs) else None)
            return True if True in vs else (False if all(v is False for v in vs) else None)
        if isinstance(test, ast.Compare) and len(test.ops) == 1:
            left, op, right = test.left, test.ops[0], test.comparators[0]
            if isinstance(right, (ast.Name, ast.Attribute)) and isinstance(left, (ast.Constant, ast.Tuple, ast.List, ast.Set)):
                left, right = right, left
            if isinstance(left, ast.Attribute) and isinstance(left.value, ast.Name) \
                    and left.value.id in _ns_names and left.attr in argv_here:
                values: set[str] | None = argv_here[left.attr]
            elif isinstance(left, ast.Name) and left.id in cons and cons[left.id] is not None:
                values = cons[left.id]
            elif env_get(left, env_here) is not None:
                values = env_get(left, env_here)
            else:
                return None
            if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(right, ast.Constant):  # noqa: E501
                hits = {v == right.value for v in values}
                if len(hits) != 1:
                    return None
                return hits.pop() if isinstance(op, ast.Eq) else not hits.pop()
            if isinstance(op, (ast.In, ast.NotIn)) and isinstance(right, (ast.Tuple, ast.List, ast.Set)) \
                    and all(isinstance(e, ast.Constant) for e in right.elts):
                pool = {e.value for e in right.elts}
                hits = {v in pool for v in values}
                if len(hits) != 1:
                    return None
                return hits.pop() if isinstance(op, ast.In) else not hits.pop()
        return None

    def _fold_locals(fn: ast.AST, cons: dict[str, set[str] | None],
                     argv_here: dict[str, set[str]], bools_here: dict[str, bool],
                     env_here: dict[str, set[str]] | None = None,
                     f: str = "") -> dict[str, bool]:
        """Locals assigned a boolean expression over the switches, in source
        order: `do_walk_forward = args.walk_forward or args.walk_forward_only`
        then `run_wf = do_walk_forward and not args.report_only` then
        `if run_wf:`.

        A local assigned the result of a same-module call whose every
        reachable `return` yields None is known-falsy too: `cell =
        _resolve_task()` then `if cell:`, where the resolver returns None
        because the job declares no plan.
        """
        known: dict[str, bool] = {}
        for node in ast.walk(fn):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            tgt = node.targets[0]
            if not isinstance(tgt, ast.Name):
                continue
            v = verdict(node.value, cons, argv_here, bools_here, env_here, known)
            if v is None and isinstance(node.value, ast.Call) \
                    and isinstance(node.value.func, ast.Name) \
                    and returns_none(f, node.value.func.id):
                v = False
            if v is None:
                known.pop(tgt.id, None)
            else:
                known[tgt.id] = v
        return known

    def _terminates(stmts: list[ast.stmt]) -> bool:
        """Every path through `stmts` leaves the block: a `return`, `raise`,
        `continue` or `break`, or an if/else whose both arms do."""
        for st in stmts:
            if isinstance(st, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
                return True
            if isinstance(st, ast.If) and st.body and st.orelse \
                    and _terminates(st.body) and _terminates(st.orelse):
                return True
        return False

    def dormant(fn: ast.AST, cons: dict[str, set[str] | None], f: str = "",
                block: list[ast.stmt] | None = None) -> set[int]:
        """ids of the statements behind branches `cons`, the job's declared
        CLI values, or its declared environment rule out -- and of the
        statements that follow a taken branch which cannot fall through.

        The second half is what makes an early return readable:
        `_resolve_task()` opens with `if not plan_name or ...: return None`,
        and with the test decided True everything after it is dead, so the
        function has exactly one reachable return. Without that, its two
        later returns keep the caller's `if cell:` alive and a dispatch the
        job cannot perform contributes an unknown phase to `walk_forward`,
        which erased the literal `--phase=phase0`. (Codex, PR #1044.)
        """
        out: set[int] = set()
        argv_here = sure_of(f)
        bools_here = bools_of(f)
        env_here = env_of(f)
        # `reads_managed_env` already folds `env_here` against what the module
        # reads, so a declared environment no module consults decides nothing
        # and must not change how the module is walked.
        managed = reads_managed_env(f)
        if not cons and not argv_here and not bools_here and not managed:
            return out
        # `is_phase3 = phase == "phase3"` then `if is_phase3:` is the same
        # branch as `if phase == "phase3":`, and the second was pruned while
        # the first was not, because locals were folded only when a boolean
        # switch or a managed env read existed. (Codex, PR #1044.)
        locals_here = _fold_locals(fn, cons, argv_here, bools_here, env_here, f) \
            if (cons or argv_here or bools_here or managed) else {}

        def scan(stmts: list[ast.stmt]) -> None:
            dead = False
            for st in stmts:
                if dead:
                    out.add(id(st))
                    continue
                taken: list[ast.stmt] | None = None
                if isinstance(st, ast.If):
                    v = verdict(st.test, cons, argv_here, bools_here, env_here, locals_here)
                    if v is True:
                        out.update(id(x) for x in st.orelse)
                        taken = st.body
                    elif v is False:
                        out.update(id(x) for x in st.body)
                        taken = st.orelse
                if taken is not None:
                    scan(taken)
                    if taken and _terminates(taken):
                        dead = True
                    continue
                for _name, val in ast.iter_fields(st):
                    if not isinstance(val, list) or not val:
                        continue
                    if isinstance(val[0], ast.stmt):
                        scan(val)
                    elif isinstance(val[0], ast.ExceptHandler):
                        for h in val:
                            scan(h.body)

        scan(block if block is not None
             else (fn.body if isinstance(getattr(fn, "body", None), list) else [fn]))
        return out

    def returns_none(f: str, sym: str) -> bool:
        """True when every reachable `return` of `f`'s top-level `sym` yields
        None, so `x = sym()` is known falsy.

        Generators are excluded (a generator object is truthy however the
        body returns) and so are decorated functions (the decorator decides
        what the call yields).
        """
        if not f:
            return False
        key = (f, sym)
        if key in none_walking:
            return False
        tree = _parsed(root / f)
        fn = _top_defs(tree).get(sym) if tree is not None else None
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or fn.decorator_list:
            return False
        none_walking.add(key)
        try:
            skip = dormant(fn, arg_lits.get(key, {}), f)
            stack: list[ast.AST] = list(fn.body)
            while stack:
                n = stack.pop()
                if id(n) in skip:
                    continue
                if isinstance(n, (ast.Yield, ast.YieldFrom)):
                    return False
                if isinstance(n, ast.Return) and n.value is not None \
                        and not (isinstance(n.value, ast.Constant) and n.value.value is None):
                    return False
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                    continue        # a nested definition's returns are its own
                stack.extend(ast.iter_child_nodes(n))
            return True
        finally:
            none_walking.discard(key)

    def live_nodes(nodes: list[ast.AST], skip: set[int]):
        """ast.walk over `nodes`, not descending into skipped statements."""
        stack = list(nodes)
        while stack:
            n = stack.pop()
            if id(n) in skip:
                continue
            yield n
            stack.extend(ast.iter_child_nodes(n))

    def live_lines(fn: ast.AST, skip: set[int]) -> set[int]:
        lines = _lines_of(fn)
        for node in ast.walk(fn):
            if id(node) in skip:
                lines -= _lines_of(node)
        return lines

    def reach_const(f: str, name: str, node: ast.AST) -> None:
        # the assignment names its own target, so guard before walking it
        if (f, name) in reached_consts:
            return
        reached_consts.add((f, name))
        add_lines(f, _lines_of(node))
        uses(f, [node])

    def add_lines(f: str, lines: set[int] | None) -> None:
        if f == "gcp/database.py":
            return
        if lines is None or scope.get(f, set()) is None:
            scope[f] = None
        else:
            scope.setdefault(f, set()).update(lines)

    def uses(f: str, nodes: list[ast.AST], skip: set[int] | None = None,
             cons: dict[str, set[str] | None] | None = None) -> None:
        """Follow every name and attribute chain used in `nodes` (code in `f`),
        not descending into the statements in `skip`. `cons` is the constraint
        map of the function being walked, so a parameter passed straight on
        carries its values to the callee."""
        skip = skip or set()
        cons = cons or {}
        tree = _parsed(root / f)
        if tree is None:
            return
        defs, consts = _top_defs(tree), _top_consts(tree)
        # names the reached code can see: the module's own top-level imports
        # plus the imports written inside the reached nodes themselves
        local = _bind_from(root, f, nodes)
        binds = {k: list(v) for k, v in _module_bindings(root, f).items()}
        for k, v in local.items():
            for t in v:
                if t not in binds.setdefault(k, []):
                    binds[k].append(t)
        names: set[str] = set()
        chains: set[str] = set()
        new_attrs: set[str] = set()
        call_funcs: set[int] = set()
        calls: list[ast.Call] = []
        for sub in live_nodes(nodes, skip):
            if isinstance(sub, ast.Call):
                calls.append(sub)
                call_funcs.add(id(sub.func))
        walked = list(live_nodes(nodes, skip))
        for sub in walked:
            if isinstance(sub, ast.Name):
                names.add(sub.id)
            elif isinstance(sub, ast.Attribute):
                if sub.attr not in attr_names:
                    new_attrs.add(sub.attr)
                d = _dotted(sub)
                if d:
                    chains.add(d)
        attr_names.update(new_attrs)

        # A name imported inside ONE branch binds only the calls in that
        # branch. `_run_wf` imports a different `walk_forward` under each
        # `axis`, and the 4-argument magnitude call also fits the 3-argument
        # strat signature, so merging the bindings put `ticker` into the strat
        # function's `tf` and blocked every narrowing behind it.
        # (Codex, PR #1044.)
        branch_bind: dict[int, dict[str, list[tuple[str, str | None]]]] = {}
        for blk_owner in walked:
            for attr in ("body", "orelse", "finalbody"):
                blk = getattr(blk_owner, attr, None)
                if not isinstance(blk, list) or isinstance(blk_owner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
                    continue
                b = _bind_from(root, f, blk)
                if not b:
                    continue
                for stmt in blk:
                    for c in ast.walk(stmt):
                        if isinstance(c, ast.Call):
                            for k, v in b.items():
                                branch_bind.setdefault(id(c), {}).setdefault(k, v)

        def resolve_callees(func: ast.AST, call: ast.Call | None = None) -> list[tuple[str, str]]:
            """EVERY function a call's name can reach, not just the first;
            a name imported in the call's own branch wins over the merge."""
            out: list[tuple[str, str]] = []
            if isinstance(func, ast.Name):
                if call is not None:
                    local_b = branch_bind.get(id(call), {}).get(func.id)
                    if local_b:
                        return [(tg, sym) for tg, sym in local_b if sym is not None]
                if func.id in defs:
                    out.append((f, func.id))
                out += [(target, sym) for target, sym in binds.get(func.id, []) if sym is not None]
                return out
            d = _dotted(func)
            if d and "." in d:
                alias, attr = d.rsplit(".", 1)
                out += [(target, attr) for target, sym in binds.get(alias, []) if sym is None]
            return out

        def callee_def(target: tuple[str, str]) -> ast.AST | None:
            tree2 = _parsed(root / target[0])
            node = _top_defs(tree2).get(target[1]) if tree2 is not None else None
            return node if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else None

        # literal arguments first, so a callee reached below is walked with them
        rewalk: set[tuple[str, str]] = set()
        for c in calls:
            cands = resolve_callees(c.func, c)
            fits = [t for t in cands if _accepts(callee_def(t), c)]
            # a call whose shape fits none of them stays ambiguous: observe it
            # against all, which can only loosen
            for target in (fits or cands):
                if observe_call(target, c, cons, argv_of(f)) and target in seen_syms:
                    rewalk.add(target)
        for sub in walked:
            if not isinstance(sub, ast.Name) or id(sub) in call_funcs:
                continue
            # a bare reference (a callback) is a call with anything
            refs = ([(f, sub.id)] if sub.id in defs else []) \
                + [(target, sym) for target, sym in binds.get(sub.id, []) if sym is not None]
            for target in refs:
                if observe_call(target, None) and target in seen_syms:
                    rewalk.add(target)
        for target in rewalk:
            seen_syms.discard(target)
            reach_symbol(*target)
        for (cf, cname), cls in list(classes.items()):
            for m in cls.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name in new_attrs:
                    reach_method(cf, cname, m)
        for name in names:
            if name in defs:
                reach_symbol(f, name)
            elif name in consts:
                reach_const(f, name, consts[name])
            elif name in binds:
                for target, sym in binds[name]:
                    if sym is not None:
                        reach_symbol(target, sym)
                    else:
                        attrs = {c.split(".")[1] for c in chains if c.startswith(name + ".") and c.count(".") >= 1}
                        if attrs:
                            for a in attrs:
                                reach_symbol(target, a)
                        else:
                            reach_module(target, whole=True)
        # `import gcp.a.b` (no alias) is bound under its dotted name; the use
        # is the chain `gcp.a.b.attr`.
        for alias, targets in binds.items():
            if "." not in alias:
                continue
            for target, sym in targets:
                if sym is not None:
                    continue
                attrs = {c[len(alias) + 1:].split(".")[0] for c in chains if c.startswith(alias + ".")}
                if attrs:
                    for a in attrs:
                        reach_symbol(target, a)
                elif alias in chains:
                    reach_module(target, whole=True)
        for target, _sym in binds.get("*", []):
            reach_module(target, whole=True)
        # An import statement inside the reached code executes the target's
        # module-level statements whether or not the bound name is ever used.
        # Only those: an import inside a function that is not reached does
        # not run.
        for targets in local.values():
            for target, _sym in targets:
                reach_module(target)
        # A subprocess the reached code launches runs its target in full.
        for target in spawn_targets(f, nodes, skip):
            reach_module(target, whole=True)

    def reach_module(f: str, whole: bool = False) -> None:
        if f == "gcp/database.py":
            return
        tree = _parsed(root / f)
        if tree is None:
            return
        if whole:
            if scope.get(f, set()) is None:
                return
            seen_mods.add(f)
            # A root module runs in full -- except for the branches the job's
            # own declared CLI values rule out. `refresh-earnings-views` fixes
            # `--mode=weekly` on its own invocation, so `main()`'s
            # `elif args.mode == 'daily'` body is not reachable through it.
            # (Codex, PR #1044.)
            skip: set[int] = set()
            constrained = bool(argv_of(f) or bools_of(f) or reads_managed_env(f))
            if constrained:
                skip |= dormant(tree, {}, f, block=tree.body)
            if not constrained:
                add_lines(f, None)
                uses(f, list(tree.body))
                return
            # Walking the whole module body at once observes every call with
            # NO caller context, which sets each callee's parameters to
            # unknown before the symbol walk can pass a value down: with the
            # module walked first, `run_baseline`'s `--tf=5m` never reached
            # `run_axis`. A constrained root is therefore always reached by
            # symbol, even when no branch is decidable. (Codex, PR #1044.)
            # Constrained root: its module-level statements and its
            # `__main__` guard run, and its own functions join only where live
            # code names them. Keeping every definition would leave
            # `refresh_daily`'s writes in scope after pruning the one call
            # that reaches it.
            top = [n for n in tree.body
                   if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            lines: set[int] = set()
            for node in top:
                lines |= live_lines(node, skip)
            add_lines(f, lines)
            uses(f, top, skip)
            # A subprocess launch is a whole-module fact: the `subprocess.run`
            # sits in one helper and the child's path in another, so it is
            # scanned over the module's live statements rather than per symbol.
            for target in spawn_targets(f, list(tree.body), skip):
                reach_module(target, whole=True)
            return
        if f in seen_mods:
            return
        seen_mods.add(f)
        inert = {id(n) for n in _top_consts(tree).values()}
        top = [n for n in tree.body
               if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
               and not _is_main_guard(n) and id(n) not in inert]
        lines: set[int] = set()
        for n in top:
            lines |= _lines_of(n)
        add_lines(f, lines)
        uses(f, top)

    def reach_symbol(f: str, sym: str) -> None:
        if f == "gcp/database.py" or (f, sym) in seen_syms:
            return
        seen_syms.add((f, sym))
        reach_module(f)
        tree = _parsed(root / f)
        if tree is None:
            return
        defs = _top_defs(tree)
        if sym in defs:
            node = defs[sym]
            if isinstance(node, ast.ClassDef):
                reach_class(f, node)
            else:
                cons = arg_lits.get((f, sym), {})
                skip = dormant(node, cons, f)
                add_lines(f, live_lines(node, skip))
                uses(f, [node], skip, cons)
            return
        consts = _top_consts(tree)
        if sym in consts:
            reach_const(f, sym, consts[sym])
            return
        for target, inner in _bindings(root, f).get(sym, []):   # re-export: `from .sub import sym` in __init__
            if inner is not None:
                reach_symbol(target, inner)
            else:
                reach_module(target, whole=True)

    _SPAWN = re.compile(r"\b(?:subprocess\.(?:run|call|check_call|check_output|Popen)|os\.system|os\.exec\w*|os\.spawn\w*|runpy\.run_(?:path|module))\b")

    def spawn_targets(f: str, nodes: list[ast.AST], skip: set[int] | None = None) -> list[str]:
        """Repo modules the reached code launches as a subprocess: a `.py`
        string that resolves against the file's own directory or the repo
        root (scripts/run_pipeline.py builds `SCRIPTS_DIR / "run_backtest.py"`),
        or a dotted module after `-m`. Only when the reached code calls
        subprocess / os.system / runpy at all. (Codex, PR #1044.)

        Statements in `skip` are not walked, so a child launched only from a
        branch the job's declared flags rule out is not a root:
        `scripts/run_pipeline.py` runs `run_walk_forward.py` under
        `if run_wf:`, and `backtest-pipeline` deploys with no args, so
        `--walk-forward` is false. (Codex, PR #1044.)
        """
        live = list(live_nodes(nodes, skip or set()))
        if not any(isinstance(n, ast.Call) and _SPAWN.search(_dotted(n.func) or "") for n in live):
            return []
        out: list[str] = []
        # source order matters: the `-m` form reads the NEXT string, and
        # live_nodes walks depth-first off a stack rather than in order
        strings = [n.value for n in sorted(
            (n for n in live if isinstance(n, ast.Constant) and isinstance(n.value, str)),
            key=lambda n: (n.lineno, n.col_offset))]
        here = pathlib.Path(f).parent
        for i, sv in enumerate(strings):
            cand: str | None = None
            if sv.endswith(".py") and "/" not in sv.strip("./") or sv.endswith(".py"):
                for rel in (str(here / pathlib.Path(sv).name), sv.lstrip("./")):
                    if (root / rel).exists() and rel.startswith(("gcp/", "lib/", "scripts/")):
                        cand = rel
                        break
            elif sv == "-m" and i + 1 < len(strings):
                cand = _module_file(root, strings[i + 1].split("."))
            if cand and cand != f and cand not in out:
                out.append(cand)
        return out

    def reach_class(f: str, cls: ast.ClassDef) -> None:
        classes[(f, cls.name)] = cls
        methods = [m for m in cls.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
        header = _lines_of(cls)
        for m in methods:
            header -= _lines_of(m)
        add_lines(f, header)
        uses(f, list(cls.bases) + list(cls.keywords) + list(cls.decorator_list)
             + [n for n in cls.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))])
        for m in methods:
            if m.name in ALWAYS or m.name in attr_names:
                reach_method(f, cls.name, m)

    def reach_method(f: str, cname: str, m: ast.AST) -> None:
        if (f, cname, m.name) in reached_methods:
            return
        reached_methods.add((f, cname, m.name))
        add_lines(f, _lines_of(m))
        uses(f, [m])

    if mod_file and (root / mod_file).exists():
        reach_module(mod_file, whole=True)
    if out_args is not None:
        # Per (file, function), NOT merged by parameter spelling. Flattening
        # let one unrelated callee with an unknown parameter named `tf` set the
        # shared entry to None and block every narrowing: `direction-baseline`
        # fixes `--tf=5m` and still rendered all six timeframes.
        # (Codex, PR #1044.)
        for key, cons in arg_lits.items():
            merged = out_args.setdefault(key, {})
            for prm, vals in cons.items():
                if vals is None or merged.get(prm, set()) is None:
                    merged[prm] = None
                else:
                    merged.setdefault(prm, set()).update(vals)
    return scope


def _scheduler_modules(root: pathlib.Path, job_name: str, schedulers: list[dict[str, Any]]) -> list[str]:
    """Repo modules a scheduler's args override selects when it targets this
    job: strat-enrich-daily targets strat-engine with
    `-m gcp.research.strat_engine.strat_enrich_levels`, so that module is a
    root of strat-engine's reachable code. (Codex, PR #1044.)"""
    return [f for f, _argv, _flags in _scheduler_roots(root, job_name, schedulers)]


def _scheduler_roots(root: pathlib.Path, job_name: str, schedulers: list[dict[str, Any]]
                     ) -> list[tuple[str, dict[str, set[str]], list[set[str]]]]:
    """Each module a scheduler override selects for this job, paired with the
    CLI values THAT scheduler passes.

    The pairing matters: `strat-enrich-daily` selects `strat_enrich_levels`
    with `--mode=backfill-all`, and applying that mode to `strat_data_builder`
    (the job's own entry module, which the scheduler does not run) would prune
    branches of a module the flag was never given to. (Codex, PR #1044.)
    """
    out: list[tuple[str, dict[str, set[str]], list[set[str]]]] = []
    for sch in schedulers:
        if sch.get("target_job") != job_name or not sch.get("args"):
            continue
        as_job = {"name": job_name, "command": "", "args": sch["args"]}
        argv, flags = declared_argv(as_job, None), [declared_flags(as_job, None)]
        for m in re.finditer(r"\b((?:gcp|lib|scripts)(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\b", sch["args"]):
            f = _module_file(root, m.group(1).split("."))
            if f and f != "gcp/database.py" and not any(f == g for g, _a, _fl in out):
                out.append((f, argv, flags))
    return out


# Only the `--flag=value` form. `--args "--tickers,SPY IWM QQQ SPX,--from-latest"`
# is ONE value containing spaces, and by the time deploy.sh's args reach here
# the comma boundaries are gone, so the space form cannot be read back
# faithfully and is not read at all. (Codex, PR #1044.)
_ARGV_FLAG = re.compile(r"--([A-Za-z][\w-]*)=([^\s,\"']+)")


def declared_argv(job: dict[str, Any], schedulers: list[dict[str, Any]] | None = None) -> dict[str, set[str]]:
    """The CLI values the deployed job can be invoked with, as
    `argparse` dest -> values, from its own command and args UNION every
    scheduler override that targets it.

    `refresh-earnings-views` is deployed with `--mode=weekly`, so its `main()`
    cannot reach the `--mode=daily` branch on that invocation -- but
    `gcp/deploy.sh:4270` schedules `refresh-earnings-views-daily` with an args
    override of `--mode=daily`, so the job as a whole reaches both. Taking the
    union is what keeps the daily branch's write in the graph while still
    pruning a flag no configuration ever varies (`direction-probe` fixes
    `--tf=15m`). A flag given with no value is a store_true and carries none.
    (Codex, PR #1044.)
    """
    out: dict[str, set[str]] = {}
    sources = [f"{job.get('command') or ''} {job.get('args') or ''}"]
    for sch in schedulers or []:
        if sch.get("target_job") == job["name"] and sch.get("args"):
            sources.append(sch["args"])
    for src in sources:
        for m in _ARGV_FLAG.finditer(src):
            out.setdefault(m.group(1).replace("-", "_"), set()).add(m.group(2))
    return out


_LIST_ACTIONS = {"append", "extend", "append_const", "count",
                 "store_true", "store_false", "store_const", "version", "help"}


_ARGV_ANY_FLAG = re.compile(r"--([A-Za-z][\w-]*)")


def declared_flags(job: dict[str, Any], schedulers: list[dict[str, Any]] | None = None) -> set[str]:
    """Every flag name the deployed job passes, in any form.

    `declared_argv` reads only `--flag=value`, since the space form's token
    boundaries are lost; a boolean flag carries no value, so its PRESENCE is
    the whole signal and this reads it. (Codex, PR #1044.)
    """
    out: set[str] = set()
    sources = [f"{job.get('command') or ''} {job.get('args') or ''}"]
    for sch in schedulers or []:
        if sch.get("target_job") == job["name"] and sch.get("args"):
            sources.append(sch["args"])
    for src in sources:
        out |= _flag_names(src)
    return out


def declared_env(job: dict[str, Any], schedulers: list[dict[str, Any]] | None = None
                 ) -> tuple[dict[str, set[str]], set[str]]:
    """The environment the deployed job runs with, and the names that only
    SOME of its invocations set.

    Values come from its own `--set-env-vars` unioned with every scheduler
    override that targets it, the same union rule as `declared_argv`. The
    second element is the names a scheduler adds that the job itself does
    not declare: `backfill-indicators-weekly` is scheduled twice, once plain
    and once with `BACKFILL_MODE=full`, so an absent `BACKFILL_MODE` is a
    real possibility too and the reader must fold in the call site's own
    default rather than assuming the value.
    """
    own = {k: {str(v)} for k, v in (job.get("env") or {}).items()}
    out: dict[str, set[str]] = {k: set(v) for k, v in own.items()}
    for sch in schedulers or []:
        if sch.get("target_job") != job.get("name"):
            continue
        for pair in (sch.get("args") or "").split():
            k, eq, v = pair.partition("=")
            if eq and re.fullmatch(r"[A-Z][A-Z0-9_]*", k):
                out.setdefault(k, set()).add(v)
    return out, {k for k in out if k not in own}


_ENVNAME_CACHE: dict[tuple[pathlib.Path, int, int] | None, frozenset[str]] = {}


def deployment_env_names(root: pathlib.Path = REPO) -> frozenset[str]:
    """Every environment variable `gcp/deploy.sh` sets, on any job or in any
    scheduler override.

    This is the set the deploy script CONTROLS, and it is what makes an
    absent variable readable as absent: `MAG_PLAN` is set on
    `magnitude-engine` and deliberately not on `magnitude-recal`, so the
    latter takes the `os.environ.get("MAG_PLAN", "")` default. A name the
    deploy script never mentions -- `CLOUD_RUN_TASK_INDEX`, which Cloud Run
    injects -- is NOT in this set and stays unknown.

    Limitation, stated rather than implied: an execute-time
    `--update-env-vars` is not modelled, exactly as an execute-time
    `--args` override is not. The attribution is of the DECLARED
    configuration.
    """
    key = _sig(root / "gcp/deploy.sh")
    if key in _ENVNAME_CACHE:
        return _ENVNAME_CACHE[key]
    names: set[str] = set()
    for j in deploy_jobs(root):
        names |= set((j.get("env") or {}).keys())
    for sch in deploy_schedulers(root):
        for pair in (sch.get("args") or "").split():
            k, eq, _v = pair.partition("=")
            if eq and re.fullmatch(r"[A-Z][A-Z0-9_]*", k):
                names.add(k)
    _ENVNAME_CACHE[key] = frozenset(names)
    return _ENVNAME_CACHE[key]


def declared_flag_sets(job: dict[str, Any], schedulers: list[dict[str, Any]] | None = None) -> list[set[str]]:
    """The flag names of EACH way the job is invoked, one set per
    configuration: its own deployed args, then every scheduler override.

    `declared_flags` unions them, which answers "is this flag ever passed"
    but not "is it always passed", and only the second question decides a
    branch. A scheduler override REPLACES the container args, so
    `fetch-top-movers` runs both with `--intraday-snapshot` (hourly) and
    without it (daily): the switch is unknown, not true, and reading it as
    true made the daily `top_movers_daily` write unreachable. (Codex,
    PR #1044.)
    """
    out = [_flag_names(f"{job.get('command') or ''} {job.get('args') or ''}")]
    for sch in schedulers or []:
        if sch.get("target_job") == job.get("name") and _overrides_argv(sch.get("args") or ""):
            out.append(_flag_names(sch["args"]))
    return out


def _overrides_argv(args: str) -> bool:
    """Whether a scheduler's override replaces the container's command line.

    `containerOverrides` carries `args` and `env` independently and the parser
    flattens both into one string, so a scheduler that only sets an env var
    (`alpha-weekly`'s `MODE=full`) leaves the deployed args in force and is
    not a second command-line configuration.
    """
    return any(tok.startswith("-") for tok in args.split())


def _flag_names(src: str) -> set[str]:
    return {m.group(1).replace("-", "_") for m in _ARGV_ANY_FLAG.finditer(src)}


def _argparse_dests(tree: ast.Module) -> tuple[set[str], set[str], dict[str, tuple[bool, bool]],
                                                set[str], dict[str, str]]:
    """(names bound from `parse_args()`, the SCALAR dests the module declares,
    the boolean switches, the dests that default to None, the literal string
    each remaining scalar dest defaults to).

    Only a module that declares `--mode` may have its `args.mode` constrained
    by a deployed `--mode=weekly`, and only through a name that actually holds
    a parsed namespace.

    Scalar only: `--tickers SPY IWM QQQ SPX` (declared `nargs="+"`) makes
    `args.tickers` a LIST, so no `==` against a string can be decided from it,
    and reading the first value as if it were the whole thing pruned real
    branches out of `fetch-av-options-backfill`. A flag with `nargs`, or an
    action that stores a bool / counter / list, is not constrained.
    (Codex, PR #1044.)
    """
    ns: set[str] = set()
    dests: set[str] = set()
    bools: dict[str, tuple[bool, bool]] = {}
    # A dest whose default is None is FALSY when the deployment does not pass
    # the flag, exactly as a store_true switch is False. `mag_walk_forward`
    # guards its local-debug dispatch with `if args.plan and ...`, and
    # `magnitude-recal` passes no `--plan`. Excluded: a `required=True` dest
    # (the job could not run without it) and any dest the module assigns back
    # onto the namespace (`args.tickers = DEFAULT` after an `is None` test),
    # where the None is a placeholder rather than the value the branch sees.
    nones: set[str] = set()
    reassigned: set[str] = {
        t.attr for n in ast.walk(tree) if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Attribute)
    } | {
        n.target.attr for n in ast.walk(tree)
        if isinstance(n, (ast.AugAssign, ast.AnnAssign)) and isinstance(n.target, ast.Attribute)
    }

    def _dest_of(node: ast.Call, kw: dict[str, ast.AST]) -> str | None:
        explicit = kw.get("dest")
        if isinstance(explicit, ast.Constant) and isinstance(explicit.value, str):
            return explicit.value
        for a in node.args:
            if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.startswith("--"):
                return a.value[2:].replace("-", "_")
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "parse_args":
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    ns.add(tgt.id)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "add_argument":
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            act = kw.get("action")
            # a boolean switch: (value when the flag IS passed, value when it is not)
            if isinstance(act, ast.Constant) and act.value in ("store_true", "store_false"):
                d = _dest_of(node, kw)
                dflt = kw.get("default")
                on = act.value == "store_true"
                off = (dflt.value if isinstance(dflt, ast.Constant) and isinstance(dflt.value, bool)
                       else not on)
                if d:
                    bools[d] = (on, off)
                continue
            if "nargs" in kw:
                continue
            # a declared type converts the string, so a `--horizon=15` literal
            # is the int 15 by the time `args.horizon` is compared
            ty = kw.get("type")
            if ty is not None and not (isinstance(ty, ast.Name) and ty.id == "str"):
                continue
            act = kw.get("action")
            if isinstance(act, ast.Constant) and act.value in _LIST_ACTIONS:
                continue
            if act is not None and not isinstance(act, ast.Constant):
                continue
            d = _dest_of(node, kw)
            if d:
                dests.add(d)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"):
            continue
        kw = {k.arg: k.value for k in node.keywords if k.arg}
        act = kw.get("action")
        if isinstance(act, ast.Constant) and act.value in ("store_true", "store_false"):
            continue
        req = kw.get("required")
        if isinstance(req, ast.Constant) and req.value is True:
            continue
        if "default" in kw and not (isinstance(kw["default"], ast.Constant)
                                    and kw["default"].value is None):
            continue
        d = _dest_of(node, kw)
        if d and d not in reassigned:
            nones.add(d)
    # A scalar option no invocation passes takes its declared default, exactly
    # as a `store_true` switch and a `None` default do. Without it
    # `add_argument("--mode", default="weekly")` left the daily arm reachable
    # for a job argparse always gives "weekly", so a table only that arm
    # touches was published for it. Same exclusions as the None case: a
    # `required=True` dest (argparse would refuse to run without it) and a dest
    # the module assigns back onto the namespace. (Codex, PR #1044.)
    str_defaults: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"):
            continue
        kw = {k.arg: k.value for k in node.keywords if k.arg}
        req = kw.get("required")
        if isinstance(req, ast.Constant) and req.value is True:
            continue
        dflt = kw.get("default")
        if not (isinstance(dflt, ast.Constant) and isinstance(dflt.value, str)):
            continue
        d = _dest_of(node, kw)
        if d and d in dests and d not in reassigned:
            str_defaults[d] = dflt.value
    return ns, dests, bools, nones, str_defaults


def _job_scope(root: pathlib.Path, job: dict[str, Any],
               schedulers: list[dict[str, Any]] | None = None,
               out_args: dict[str, set[str] | None] | None = None) -> dict[str, set[int] | None]:
    """The entry module's scope plus, in full, every module the job's env or
    args configure a wrapper to run (see _configured_modules) and every
    module a scheduler's args override selects for it."""
    sched_roots = _scheduler_roots(root, job["name"], schedulers or [])
    overridden = {f for f, _a, _fl in sched_roots}
    # The entry module runs under the job's own args plus the args of every
    # scheduler that does NOT redirect the job to a different module.
    plain = [s for s in (schedulers or [])
             if s.get("target_job") == job["name"] and s.get("args")
             and not any(_module_file(root, m.group(1).split(".")) in overridden
                         for m in re.finditer(r"\b((?:gcp|lib|scripts)(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\b", s["args"]))]
    entry_argv = declared_argv(job, plain)
    entry_flags = declared_flag_sets(job, plain)
    entry_env = declared_env(job, plain)
    roots: list[tuple[str, dict[str, set[str]], list[set[str]]]] = [
        (entry_module(job), entry_argv, entry_flags)]
    for m in _configured_modules(root, job):
        env_job = {"name": job["name"], "command": "",
                   "args": " ".join(str(v) for v in (job.get("env") or {}).values())}
        roots.append((m, declared_argv(env_job, None), [declared_flags(env_job, None)]))
    roots += sched_roots
    scope = _import_scope(root, roots[0][0], roots[0][1], roots[0][2], out_args, entry_env)
    for extra, extra_argv, extra_flags in roots[1:]:
        for f, lines in _import_scope(root, extra, extra_argv, extra_flags,
                                      out_args, entry_env).items():
            if lines is None or scope.get(f, set()) is None:
                scope[f] = None
            else:
                scope.setdefault(f, set()).update(lines)
    return scope


def _in_scope(scope: dict[str, set[int] | None], ref: dict[str, Any]) -> bool:
    lines = scope.get(ref["file"], set())
    return lines is None or ref["line"] in lines


def _module_of(path: str) -> str:
    return path[:-3].replace("/", ".") if path.endswith(".py") else path


def blast_radius(repo: dict[str, Any], refs: dict[str, dict[str, list[dict[str, Any]]]]) -> list[dict[str, Any]]:
    """Per job: tables the code reachable from its entrypoint writes, and who reads them."""
    readers: dict[str, set[str]] = {t: {r["file"] for r in v["reads"]} for t, v in refs.items()}
    out = []
    root = _repo_root(repo)
    for j in repo["jobs"]:
        mod_file = entry_module(j)
        scope = _job_scope(root, j, repo.get("schedulers"))
        written = sorted(t for t, v in refs.items() if any(_in_scope(scope, w) for w in v["writes"]))
        downstream = sorted({f for t in written for f in readers.get(t, set()) if f not in scope})
        out.append({"job": j["name"], "module": mod_file, "writes": written, "readers": downstream})
    return out


def job_table_edges(repo: dict[str, Any], refs: dict[str, dict[str, list[dict[str, Any]]]],
                    jobs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Per job: the tables the code reachable from its entry module (through
    the names it imports, transitively) writes and reads. The same attribution blast_radius uses,
    so the graph and the blast table cannot disagree about who writes what.

    Reads and writes are recorded independently: `backfill-daily-indicators`
    reads `market_data_daily` (`SELECT DISTINCT ticker FROM market_data_daily`)
    and writes it, and dropping the read because a write exists hid a real
    dependency from the graph and the digest. (Codex, PR #1044.)

    `jobs` defaults to the declared jobs; a caller may pass live job records
    (same `command` / `args` keys) to attribute hand-created jobs the same way.
    """
    root = _repo_root(repo)
    out = []
    for j in (repo["jobs"] if jobs is None else jobs):
        mod_file = entry_module(j)
        observed: dict[tuple[str, str], dict[str, set[str] | None]] = {}
        scope = _job_scope(root, j, repo.get("schedulers"), observed)

        def fits(x: dict[str, Any], _obs=observed) -> bool:
            """A run-time-assembled name whose placeholder this job fixes is
            not a whole family. `direction-probe` is deployed with `--tf=15m`
            and passes `args.tf` down to the loader, so the only
            `strat_features_{tf}` relations it can name are the 15m ones.

            The constraint is read from the function that ENCLOSES this
            reference, so an unrelated callee with a same-named parameter
            cannot widen or block it. (Codex, PR #1044.)
            """
            if x.get("resolved", True) or not x.get("vars") or not x.get("origins"):
                return True
            cons: dict[str, set[str] | None] = {}
            for fn in _enclosing_funcs(root, x["file"], x["line"]):
                got = _obs.get((x["file"], fn))
                if got:
                    cons = got
                    break
            known = [cons[o] for o in x["origins"] if cons.get(o)]
            if not known:
                return True
            allowed = set().union(*known)
            return any(v in allowed for v in x["vars"])

        cites: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for t, v in refs.items():
            hits = {k: [x for x in v[k] if _in_scope(scope, x) and fits(x)] for k in ("writes", "reads")}
            if hits["writes"] or hits["reads"]:
                cites[t] = hits
        w = sorted(t for t, v in cites.items() if v["writes"])
        r = sorted(t for t, v in cites.items() if v["reads"])
        # An edge every one of whose reached references is an UNRESOLVED
        # run-time template is not a claim about that concrete relation: the
        # evidence says only "one of this family". magnitude-inference picks
        # its timeframe from INFERENCE_CELLS / DEFAULT_CELLS at run time, so
        # naming all six strat_features_* as reads asserted five it may never
        # touch. (Codex, PR #1044.)
        unresolved: dict[str, dict[str, str]] = {}
        for tname, h in cites.items():
            for mode in ("writes", "reads"):
                if h[mode] and all(x.get("dynamic") and not x.get("resolved") for x in h[mode]):
                    tmpl = next((x.get("template") for x in h[mode] if x.get("template")), None)
                    if tmpl:
                        unresolved.setdefault(mode, {})[tname] = tmpl
        out.append({"job": j["name"], "module": mod_file, "writes": w, "reads": r,
                    "cites": cites, "unresolved": unresolved})
    return out


def _cite_cell(cites: dict[str, dict[str, list[dict[str, Any]]]]) -> str:
    """`table (writes file:line[,line]; reads file:line[,line])` per reached
    table, for a digest row. Cited per access mode, each capped separately,
    so a table read in many places and written in one keeps its write
    citation (etf-options-retention's single DELETE was truncated away
    behind four SELECTs -- Codex, PR #1044)."""
    parts = []
    for t in sorted(cites):
        modes = []
        for mode in ("writes", "reads"):
            by_file: dict[str, list[int]] = {}
            for x in cites[t][mode]:
                by_file.setdefault(x["file"], []).append(x["line"])
            if by_file:
                modes.append(f"{mode} " + ", ".join(
                    f"`{f}:{','.join(str(l) for l in sorted(set(ls))[:3])}`" for f, ls in sorted(by_file.items())[:2]))
        parts.append(f"`{t}` ({'; '.join(modes)})")
    return "; ".join(parts) or "—"


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
    # The rendered blocks name declared relations only. The digest also scans
    # the runtime-created names, so a job that writes one (p2-build-gamma-
    # levels -> gamma_levels_eod) shows it, marked. (Codex, PR #1044.)
    runtime = runtime_relations(repo, live) if live is not None else []
    refs_all = dict(refs)
    if runtime:
        refs_all.update(table_refs(root, tables=runtime))
        # ...and the references that build a runtime name at run time
        for t, v in table_refs_dynamic(root, runtime).items():
            for kind in ("writes", "reads", "mentions"):
                seen = {(x["file"], x["line"]) for x in refs_all[t][kind]}
                refs_all[t][kind].extend(x for x in v[kind] if (x["file"], x["line"]) not in seen)
    def mark(t: str) -> str:
        return f"`{t}`" + (" (runtime-created)" if t in runtime else "")

    def cell(e: dict[str, Any], mode: str) -> str:
        """The job's tables for one access mode. Names the analysis could not
        pin down are grouped under the template that produces them, so the row
        says "one of this family" once instead of asserting each member."""
        unres = e.get("unresolved", {}).get(mode, {})
        parts = [mark(t) for t in e[mode] if t not in unres]
        groups: dict[str, list[str]] = {}
        for t in e[mode]:
            if t in unres:
                groups.setdefault(unres[t], []).append(t)
        for tmpl, members in sorted(groups.items()):
            parts.append(f"one of `{tmpl}` (name assembled at run time): "
                         + ", ".join(f"`{m}`" for m in members))
        return ", ".join(parts) or "—"
    out = ["## Multi-writer tables", "", _render_multiwriter(refs, with_lines=True), "",
           "## Orphan tables", "", _render_orphans(refs, root, _partition_map(repo), with_lines=True), "",
           "## Tables per job (code reachable from the entry module through the names it imports)", ""]
    # Every declared job, including the ones with no static table edge: the
    # prompt promises each job is here, and a missing row reads as missing
    # inventory rather than as a job that touches no table. (Codex, PR #1044.)
    rows = [[f"`{e['job']}`", cell(e, "writes"), cell(e, "reads"), _cite_cell(e["cites"])]
            for e in job_table_edges(repo, refs_all)]
    out.append(_md_table(["Job", "Writes", "Reads", "Where (file:line)"], rows) if rows else "_none_")
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
        for e in hand_created_job_edges(repo, refs_all, live):
            mod = f"`{e['module']}`" if e["module"] else "—"
            if not e["in_repo"]:
                mod += " (not in this checkout)"
            rows.append([f"`{e['job']}`", mod, cell(e, "writes"), cell(e, "reads"),
                          _cite_cell(e["cites"])])
        out.append(_md_table(["Job", "Entry module", "Writes", "Reads", "Where (file:line)"], rows) if rows else "_none_")
        out += ["", "A relation marked (runtime-created) is in the previous section, not in"
                " gcp/schema.sql; the rendered blocks name declared relations only, so those"
                " edges appear here and nowhere else.",
                "", 'A group written "one of `template` (name assembled at run time)" is a'
                " family the job builds from a template whose placeholder the static read"
                " cannot pin down (`magnitude-inference` chooses its timeframe from"
                " INFERENCE_CELLS at run time). Every member is listed because any of them"
                " may be the one used; write prose about the family, never about a"
                " particular member."]
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


def _render_orphans(refs, root: pathlib.Path = REPO, partitions: dict[str, str] | None = None,
                    with_lines: bool = False) -> str:
    """Tables missing a writer or a reader. `with_lines` adds a column citing
    the writers or readers that DO exist as `file:line` (the digest form: the
    prompt forbids the raw reference graph and requires `file:line` for every
    claim, so a bare count left the model nothing to cite -- Codex, PR #1044)."""
    rows = []
    partitions = partitions or {}
    for t in sorted(refs):
        w = {x["file"] for x in refs[t]["writes"]}; r = {x["file"] for x in refs[t]["reads"]}
        if w and r:
            continue
        if t in partitions:
            named = w or r
            status = f"partition of `{partitions[t]}` — routed by Postgres" + \
                ("" if named else ", never named in code")
        elif not w and not r:
            status = "no writer and no reader in code"
        elif not r:
            status = "write-only (no reader in code)"
        else:
            status = "read-only (no writer names it in code)"
        dyn = _dynamic_hint(root, t) if not w else []
        if dyn:
            status += "; name built at runtime in " + ", ".join(f"`{f}`" for f in dyn[:4])
        row = [f"`{t}`", str(len(w)), str(len(r)), status]
        if with_lines:
            by_file: dict[str, list[int]] = {}
            for x in refs[t]["writes"] + refs[t]["reads"]:
                by_file.setdefault(x["file"], []).append(x["line"])
            row.append(", ".join(f"`{f}:{','.join(str(l) for l in sorted(set(ls))[:6])}`" for f, ls in sorted(by_file.items())) or "—")
        rows.append(row)
    headers = ["Table", "Writers", "Readers", "Status"] + (["Where (file:line)"] if with_lines else [])
    return _md_table(headers, rows) if rows else "_none_"


def _render_blast(repo, refs) -> str:
    rows = []
    for b in blast_radius(repo, refs):
        rows.append([f"`{b['job']}`", f"`{b['module']}`" if b["module"] else "—",
                     ", ".join(f"`{t}`" for t in b["writes"]) or "— (Discord / GCS / no Cloud SQL write found)",
                     ", ".join(f"`{f}`" for f in b["readers"][:12]) + (f" (+{len(b['readers'])-12})" if len(b["readers"]) > 12 else "") or "—"])
    return _md_table(["Job", "Entry module", "Tables written (code reachable from the entry module through the names it imports)", "Readers of those tables"], rows)


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
        # counts=False: this runs AFTER the model. Re-rendering the
        # runtime-relation count here would silently correct a number the model
        # got wrong, before the gate that exists to report exactly that, and
        # restoration is defined as affecting marker blocks only. The count is
        # rendered once, before the model, in insert_blocks. (Codex, PR #1058.)
        insert_blocks(doc_path, repo, live, root=root, counts=False)
    return names


# The one shape a runtime-relation count is written in, shared by the renderer
# below and by check_generated_docs' gate, so a number the render fixes cannot
# be re-flagged by a gate matching a different shape.
RUNTIME_RELATION_COUNT = re.compile(r"(\d+)( runtime[- ](?:created )?relations)")


# The three "as of" labels a human wrote into the prose, every one of which has
# to track the snapshot the run was taken from. Deliberately literal: a looser
# pattern would sweep up the historical dates beside them -- 05-a carries 33
# occurrences of `2026-09-07`, and all but these are records of when something
# was corrected, deleted or audited and must NOT move.
ASOF_LABELS = (re.compile(r"\bLive (\d{4}-\d{2}-\d{2})\b"),
               re.compile(r"read on \*\*(\d{4}-\d{2}-\d{2})\*\*"),
               # 05-a's closing line carries TWO dates: "Generated <date> ...
               # from the <date> live snapshot". The first is already required
               # to be today by the workflow's own step 1, which greps every
               # one of the four documents for `Generated ${TODAY}` before
               # this script runs; the second is checked nowhere else, and a
               # refresh that updated only one of the pair would leave the
               # line self-contradicting. Only the second is added here: the
               # committed 05-d legitimately carries `Generated 2026-09-02`
               # (the last run that regenerated it), so gating the first would
               # fail an honest tree outside the workflow. (Codex, PR #1062.)
               re.compile(r"from the (\d{4}-\d{2}-\d{2}) live snapshot"))


# README's badge block is inventory in a picture: a date and four counts. Run
# 32's model rewrote the block wholesale and pointed the workflow badge at
# `refresh-documentation.yml`, a file that does not exist, which the dead-link
# gate then failed the run on. The prompt already said to edit README in place
# with `replace` and never to regenerate it; the model regenerated it anyway
# (52% churn). Same conclusion as the as-of labels and the runtime-relation
# count: render what is inventory and stop asking. (Run 32.)
README_BADGE = re.compile(r"^!\[[^\]]*\]\((?:https://img\.shields\.io|https://github\.com/[^)]*badge\.svg)[^)]*\)$",
                          re.M)


def readme_badges(repo: dict[str, Any], live: dict[str, Any] | None, day: str) -> str:
    """The five badge lines, rendered from the same inventory as everything else."""
    lc = (live or {}).get("counts", {})
    # Computed here rather than imported: check_generated_docs imports THIS
    # module, so the dependency only runs one way. Same three keys its
    # `relation_counts` sums.
    declared_relations = (len(repo["tables"]) + len(repo["materialized_views"])
                          + len(repo["views"]))
    live_relations = len((live or {}).get("db_tables", []) or [])
    dash = day.replace("-", "--")
    return "\n".join([
        f"![Last audit](https://img.shields.io/badge/docs_verified-{dash}-blue)",
        f"![Cloud Run Jobs](https://img.shields.io/badge/cloud_run_jobs-"
        f"{lc.get('jobs', 0)}_live_%2F_{len(repo['jobs'])}_declared-blue)",
        f"![Cloud Scheduler](https://img.shields.io/badge/schedulers-{lc.get('schedulers', 0)}_live-blue)",
        f"![Cloud SQL tables](https://img.shields.io/badge/schema_tables-"
        f"{declared_relations}_declared_%2F_{live_relations}_live-blue)",
        "![Architecture refresh](https://github.com/TeneikaAskew/stocks/actions/"
        "workflows/refresh-architecture-docs.yml/badge.svg)",
    ])


# README's closing stamp. For the three model-written documents this line is a
# COMPLETION SIGNAL -- run 32 reported "05-c does not carry today's stamp, the
# model did not complete an update of it" -- so it is never rendered for them.
# README has no model call any more, so nothing else would move it.
README_STAMP = re.compile(r"^(Generated )\d{4}-\d{2}-\d{2}\b", re.M)


def insert_readme_badges(doc_path: pathlib.Path, repo: dict[str, Any],
                         live: dict[str, Any] | None, day: str) -> bool:
    """Replace README's badge block, and its closing date stamp, from inventory."""
    text = doc_path.read_text()
    spans = [m.span() for m in README_BADGE.finditer(text)]
    if not spans:
        raise ValueError(f"{doc_path}: no badge block found to render")
    # the first contiguous run: consecutive matches separated only by newlines
    end = spans[0][1]
    for start, stop in spans[1:]:
        if text[end:start].strip():
            break
        end = stop
    new = text[:spans[0][0]] + readme_badges(repo, live, day) + text[end:]
    stamped, n = README_STAMP.subn(lambda m: f"{m.group(1)}{day}", new)
    if not n:
        raise ValueError(f"{doc_path}: no 'Generated <date>' line found to stamp")
    new = stamped
    if new != text:
        doc_path.write_text(new)
        return True
    return False


def insert_blocks(doc_path: pathlib.Path, repo: dict[str, Any], live: dict[str, Any] | None,
                  root: pathlib.Path = REPO, counts: bool = True) -> bool:
    """Replace every marker block in doc_path with freshly rendered content,
    and, when `counts`, render the runtime-relation count in the prose beside
    them. `restore_blocks` passes counts=False: it runs after the model, where
    correcting that number would hide the edit the gate is there to report.

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
    # The runtime-relation count is inventory, not a figure the model should
    # derive. Runs 24 and 26 wrote 26, 28, 30 and again 26 against a true 27 --
    # the last by carrying the previous version's number forward, which the
    # prompt explicitly forbids and which no amount of prompt wording has
    # stopped across four attempts. Rendering it HERE, before the model runs,
    # means the document it edits already carries the right number and it has
    # no reason to touch the line; the gate still checks the number afterwards,
    # so a model that changes it anyway is still caught -- which is why
    # `restore_blocks` calls this with counts=False. It runs after the model,
    # and it reaches this function, so without that flag the substitution would
    # silently rewrite the model's wrong number before the gate saw it, and an
    # earlier revision of this comment claimed the restore path was exempt when
    # the call it makes was not. (Codex, PR #1058.)
    if counts and live and live.get("db_tables"):
        n = len(runtime_relations(repo, live))
        new = RUNTIME_RELATION_COUNT.sub(lambda m: f"{n}{m.group(2)}", new)
    # The as-of labels are inventory too, for exactly the same reason. Run 31
    # updated the header note and the closing line and left §3's table column
    # at the previous snapshot's date, failing the run on one stale label --
    # the same shape as run 28. The prompt already substitutes the date as a
    # literal and enumerates all three locations; that was not enough, because
    # the model still has to FIND three places and edit each one, and two out
    # of three is a failing run. Rendering them here removes the third
    # opportunity to miss one. The gate still checks afterwards, and
    # `restore_blocks` passes counts=False, so a model that edits a label
    # anyway is still reported rather than silently corrected. (Run 31.)
    if counts and live and live.get("read_at"):
        day = str(live["read_at"])[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            for pat in ASOF_LABELS:
                new = pat.sub(lambda m: m.group(0).replace(m.group(1), day), new)
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
    ap.add_argument("--readme-badges", metavar="README",
                    help="rewrite README's badge block from the inventory (date, counts, "
                         "workflow badge). The badges are inventory in a picture; run 32's "
                         "model rewrote them and invented a workflow filename.")
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
    if args.readme_badges:
        # `today`, not the snapshot's read_at: the badge says when the docs were
        # verified, which is this run. The three as-of labels in 05-a describe
        # the SNAPSHOT and are rendered from read_at instead -- two different
        # dates that coincide on almost every run and differ on one that
        # crosses UTC midnight.
        day = datetime.date.today().isoformat()
        changed = insert_readme_badges(root / args.readme_badges, repo, live, day)
        print(f"{args.readme_badges}: badges {'updated' if changed else 'unchanged'}",
              file=sys.stderr)
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
