#!/usr/bin/env python3
"""On-demand architecture export: one JSON file of what the repo declares and
what GCP runs, for the backend architecture diagram.

Spec: docs/superpowers/specs/2026-11-10-feat-cicd-001-architecture-export.md

Every fact comes from `scripts/maintenance/doc_inventory.py`, the same
functions that render the inventory blocks of 05-a and 05-c, so the export and
those blocks cannot disagree. This module parses nothing itself: it shapes the
inventory into names-only records (no `file:line`, so an unrelated edit never
changes the export), records which main commit it was built from, and refuses
a dirty tree so that record is true.

Usage
-----
    python3 -m scripts.maintenance.architecture_export --output export.json             # repo only
    python3 -m scripts.maintenance.architecture_export --live --output export.json      # + live GCP (read-only)
    python3 -m scripts.maintenance.architecture_export --snapshot live.json --output export.json
    ... --summary summary.md    # counts and drift as Markdown (the workflow's job summary)

Live mode makes the `gcloud` reads `doc_inventory.live_snapshot` makes and
raises on any failed read (CLAUDE.md Rule 3.7). It reads no database and no
deployed route list, so the live table and route counts are null ("not read"),
never a copied or zero count.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from typing import Any

from scripts.maintenance import doc_inventory as inv

SCHEMA = "architecture-export/1"

# Paths whose state the export describes. A change under any of them that is
# not committed would make `sources.commit` a false claim, so the run refuses.
WATCHED_PATHS = ("gcp", "lib", "scripts", "platform/api", "platform/deploy.sh")

# The files the export's facts are read from, recorded by git object id.
SOURCE_BLOBS = ("gcp/deploy.sh", "platform/deploy.sh", "gcp/schema.sql")
SOURCE_TREES = ("platform/api",)

DRIFT_KEYS = ("declared_not_live", "live_not_declared", "paused_schedulers")
COUNT_KEYS = ("jobs", "services", "schedulers", "tables", "routes")
LIVE_MAPS = ("jobs", "services", "schedulers")   # what a live snapshot must have read


class DirtyTree(RuntimeError):
    """The working tree differs from HEAD under a watched path."""


# ─────────────────────────────────────────────────────────────────────────────
# provenance
# ─────────────────────────────────────────────────────────────────────────────

def _git(root: pathlib.Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(root), *args], check=True,
                         capture_output=True, text=True)
    return out.stdout.strip()


def provenance(root: pathlib.Path) -> dict[str, Any]:
    """The commit and source object ids this export describes.

    Raises DirtyTree when any watched path has an uncommitted or untracked
    change, because the export would then describe a tree no commit holds.
    """
    dirty = _git(root, "status", "--porcelain", "--untracked-files=all", "--", *WATCHED_PATHS)
    if dirty:
        raise DirtyTree("uncommitted changes under " + ", ".join(WATCHED_PATHS) + ":\n" + dirty)
    files = {p: _git(root, "rev-parse", f"HEAD:{p}") for p in SOURCE_BLOBS + SOURCE_TREES}
    return {"commit": _git(root, "rev-parse", "HEAD"), "files": files}


# ─────────────────────────────────────────────────────────────────────────────
# shaping the inventory
# ─────────────────────────────────────────────────────────────────────────────

def _target(s: dict[str, Any]) -> dict[str, Any] | None:
    """A scheduler's destination as {kind, name, uri}.

    Built from `doc_inventory._sched_target`, the same normalisation
    `reconcile` uses, so a service-targeting scheduler (`discord-warm-open`
    PATCHes discord-interactions; the hourly reconciler POSTs to
    `${service_url}`, which deploy.sh derives from the failure-notifier) keeps
    its destination instead of reading as targetless.
    """
    t = inv._sched_target(s)
    if not t:
        return None
    kind, rest = t.split(":", 1)
    uri = s.get("target_uri") or None
    if kind == "job":
        return {"kind": "job", "name": rest, "uri": None}
    if kind == "service":
        return {"kind": "service", "name": rest.split("/", 1)[0], "uri": uri}
    return {"kind": "uri", "name": None, "uri": uri}


def _auth(s: dict[str, Any]) -> str:
    """The same auth summary the services block renders."""
    auth = s.get("auth_mode") or "-"
    if str(s.get("iap")) == "true":
        auth += " (IAP)"
    if "allUsers" in (s.get("invokers") or []):
        auth += ", public invoker"
    return auth


def _module(job: dict[str, Any]) -> str | None:
    path = inv.entry_module(job)
    return path[:-3].replace("/", ".") if path.endswith(".py") else None


def _edge_lists(edge: dict[str, Any] | None, mode: str) -> tuple[list[str], dict[str, str]]:
    """(confirmed, possible) tables for one access mode.

    `job_table_edges` lists every candidate of a run-time template in
    `reads`/`writes` and names the unresolved ones in `unresolved`; a candidate
    whose only evidence is an unresolved template is possible, not asserted.
    """
    if not edge:
        return [], {}
    unres = dict(edge.get("unresolved", {}).get(mode, {}))
    return sorted(t for t in edge[mode] if t not in unres), dict(sorted(unres.items()))


def build_export(repo: dict[str, Any], live: dict[str, Any] | None,
                 sources: dict[str, Any]) -> dict[str, Any]:
    """The export document, from a `doc_inventory.repo_inventory` result and an
    optional live snapshot. Pure: no file, git or gcloud access."""
    if live is not None:
        # A snapshot without one of these maps did not read that part of the
        # fleet; treating it as an empty fleet would report every declared
        # resource as gone (CLAUDE.md Rule 3.7). (Codex, PR #1773.)
        missing = [k for k in LIVE_MAPS if not isinstance(live.get(k), dict)]
        if missing:
            raise ValueError("live snapshot has no " + ", ".join(missing) + " map; refusing to export it as empty")
    edges = {e["job"]: e for e in inv.job_table_edges(repo, repo["table_refs"])}
    # Live-only jobs are attributed by the module their live command names,
    # exactly as the inventory's digest does. One whose module is not in this
    # checkout has unknown edges, exported as null rather than as no tables.
    # (Codex, PR #1773.)
    unknown_edges: set[str] = set()
    if live is not None:
        for e in inv.hand_created_job_edges(repo, repo["table_refs"], live):
            edges[e["job"]] = e
            if not e["in_repo"]:
                unknown_edges.add(e["job"])
    live_jobs = live["jobs"] if live is not None else None
    live_services = live["services"] if live is not None else None
    live_sched = live["schedulers"] if live is not None else None

    declared_jobs = {j["name"]: j for j in repo["jobs"]}
    sched_by_job: dict[str, list[dict[str, Any]]] = {}
    for s in repo["schedulers"]:
        if s.get("target_job"):
            sched_by_job.setdefault(s["target_job"], []).append(
                {"name": s["name"], "cron": s["cron"], "time_zone": s.get("time_zone") or None,
                 "args": s.get("args") or None})

    jobs = []
    for name in sorted(set(declared_jobs) | set(live_jobs or {})):
        j = declared_jobs.get(name)
        lj = (live_jobs or {}).get(name)
        src = j or lj
        if name in unknown_edges:
            reads = writes = possible_reads = possible_writes = None
        else:
            reads, possible_reads = _edge_lists(edges.get(name), "reads")
            writes, possible_writes = _edge_lists(edges.get(name), "writes")
        module = _module(src) if src and "command" in src else None
        jobs.append({
            "name": name,
            "declared": j is not None,
            "kind": "fetcher" if module and module.startswith("gcp.fetchers.") else "compute",
            "module": module,
            "deploy_function": j["function"] if j else None,
            "resources": ({"memory": j["memory"], "cpu": j["cpu"], "timeout": j["task_timeout"],
                           "retries": j["max_retries"]} if j else None),
            "schedules": sorted(sched_by_job.get(name, []), key=lambda x: x["name"]),
            "reads": reads, "writes": writes,
            "possible_reads": possible_reads, "possible_writes": possible_writes,
            "live": (None if live_jobs is None else
                     {"exists": lj is not None,
                      "last_execution": ({"time": lj["last_execution"].get("time") or None,
                                          "result": lj["last_execution"].get("result")}
                                         if lj and lj.get("last_execution") else None)}),
        })

    declared_services = {s["name"] for s in repo["services"]}
    services = []
    for name in sorted(declared_services | set(live_services or {})):
        ls = (live_services or {}).get(name)
        services.append({
            "name": name,
            "declared": name in declared_services,
            "live": (None if ls is None else
                     {"auth": _auth(ls), "min_instances": ls.get("min_instances"),
                      "max_instances": ls.get("max_instances") or None,
                      "created": ls.get("created") or None}),
        })

    declared_sched = {s["name"]: s for s in repo["schedulers"]}
    schedulers = []
    for name in sorted(set(declared_sched) | set(live_sched or {})):
        s = declared_sched.get(name)
        ls = (live_sched or {}).get(name)
        src = s or ls
        schedulers.append({
            "name": name,
            "declared": s is not None,
            "cron": src["cron"],
            "time_zone": src.get("time_zone") or None,
            "target": _target(src),
            "args": (s.get("args") or None) if s else None,
            "live": None if ls is None else {"state": ls.get("state")},
        })

    readers: dict[str, set[str]] = {}
    writers: dict[str, set[str]] = {}
    possible_readers: dict[str, set[str]] = {}
    possible_writers: dict[str, set[str]] = {}
    for j in jobs:
        if j["reads"] is None:
            continue
        for t in j["reads"]:
            readers.setdefault(t, set()).add(j["name"])
        for t in j["writes"]:
            writers.setdefault(t, set()).add(j["name"])
        for t in j["possible_reads"]:
            possible_readers.setdefault(t, set()).add(j["name"])
        for t in j["possible_writes"]:
            possible_writers.setdefault(t, set()).add(j["name"])
    kinds = ([(t["name"], "table") for t in repo["tables"]]
             + [(v["name"], "materialized view") for v in repo["materialized_views"]]
             + [(v["name"], "view") for v in repo["views"]])
    tables = [{
        "name": name, "kind": kind,
        "writers": sorted(writers.get(name, ())), "readers": sorted(readers.get(name, ())),
        "possible_writers": sorted(possible_writers.get(name, ())),
        "possible_readers": sorted(possible_readers.get(name, ())),
    } for name, kind in sorted(kinds)]

    declared_counts = {
        "jobs": repo["counts"]["jobs"], "services": repo["counts"]["services"],
        "schedulers": repo["counts"]["schedulers"], "tables": repo["counts"]["tables"],
        "routes": repo["counts"]["routes"],
    }
    # live_snapshot reads no database relation and no deployed route list, so
    # those two counts are unread, not zero and not the declared figure.
    live_counts = {k: None for k in COUNT_KEYS}
    drift: dict[str, list[str]] = {k: [] for k in DRIFT_KEYS}
    if live is not None:
        live_counts.update(jobs=len(live_jobs), services=len(live_services),
                           schedulers=len(live_sched))
        # Jobs, services and schedulers, as doc_inventory.reconcile compares
        # them: one missing and one extra scheduler cancel out in the counts,
        # so only the names show the difference. (Codex, PR #1773.)
        drift["declared_not_live"] = sorted((set(declared_jobs) - set(live_jobs))
                                            | (declared_services - set(live_services))
                                            | (set(declared_sched) - set(live_sched)))
        drift["live_not_declared"] = sorted((set(live_jobs) - set(declared_jobs))
                                            | (set(live_services) - declared_services)
                                            | (set(live_sched) - set(declared_sched)))
        drift["paused_schedulers"] = sorted(n for n, s in live_sched.items()
                                            if s.get("state") != "ENABLED")

    return {
        "schema": SCHEMA,
        "sources": {
            "commit": sources["commit"],
            "files": dict(sorted(sources["files"].items())),
            "live": (None if live is None else
                     {"read_at": live.get("read_at"), "project": live.get("project"),
                      "region": live.get("region")}),
        },
        "jobs": jobs,
        "services": services,
        "schedulers": schedulers,
        "tables": tables,
        "counts": {"declared": declared_counts, "live": live_counts},
        "drift": drift,
    }


def dumps(export: dict[str, Any]) -> str:
    """The one serialisation: sorted keys, two-space indent, trailing newline."""
    return json.dumps(export, indent=2, sort_keys=True) + "\n"


def summary_markdown(export: dict[str, Any]) -> str:
    """Counts and drift for a workflow job summary. A null count reads `not read`."""
    def cell(v: Any) -> str:
        return "not read" if v is None else str(v)
    c = export["counts"]
    live = export["sources"]["live"]
    lines = ["## Architecture export", "",
             f"Commit `{export['sources']['commit']}`. "
             + (f"Live state read {live['read_at']} from {live['project']}." if live
                else "Repo only: no live state read."),
             "", "| | Declared | Live |", "| --- | --- | --- |"]
    for k in COUNT_KEYS:
        lines.append(f"| {k} | {cell(c['declared'][k])} | {cell(c['live'][k])} |")
    titles = {"declared_not_live": "Declared but not live",
              "live_not_declared": "Live but not declared",
              "paused_schedulers": "Paused schedulers"}
    lines.append("")
    for k in DRIFT_KEYS:
        names = export["drift"][k]
        if live is None:
            lines.append(f"- **{titles[k]}**: not read")
        else:
            lines.append(f"- **{titles[k]}** ({len(names)}): "
                         + (", ".join(f"`{n}`" for n in names) if names else "none"))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(inv.REPO))
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="read live GCP state via gcloud (read-only)")
    mode.add_argument("--snapshot", help="use a saved live snapshot instead of gcloud")
    ap.add_argument("--output", required=True, help="where to write the export JSON")
    ap.add_argument("--summary", help="also write counts and drift as Markdown here")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root).resolve()
    try:
        sources = provenance(root)
    except DirtyTree as e:
        print(f"refusing to export: {e}", file=sys.stderr)
        return 2
    repo = inv.repo_inventory(root)
    live = None
    if args.snapshot:
        live = json.loads(pathlib.Path(args.snapshot).read_text())
    elif args.live:
        live = inv.live_snapshot()
    try:
        export = build_export(repo, live, sources)
    except ValueError as e:
        print(f"refusing to export: {e}", file=sys.stderr)
        return 3
    pathlib.Path(args.output).write_text(dumps(export))
    if args.summary:
        pathlib.Path(args.summary).write_text(summary_markdown(export))
    c = export["counts"]
    print(f"wrote {args.output}: declared {c['declared']}, live {c['live']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
