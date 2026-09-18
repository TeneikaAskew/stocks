#!/usr/bin/env python3
"""Classify every Cloud Scheduler entry as model-bearing or not, with evidence.

WHY THIS EXISTS
---------------
The model registry spent three review rounds (PR #1111) discovering scheduled
jobs that produce decisions and had no registry row: MODEL-FLOW-001, then
MODEL-EARN-002, then three more. Each was found by a reviewer, one or two at a
time, because the registry's working test was "does the job import `lib/` code
cited in a MODEL-* row" -- a PROXY for "does it produce a decision", and one
that misses every job hard-coding its own thresholds.

`phase6-playbook-daily` is the worked example. It has no `from lib.` import, so
the proxy excluded it -- and the exclusion was written into the registry by
hand, in a sentence describing the markdown "decision cards" it writes. It also
passes `--write-db` and upserts `playbook_cards`, which `/api/playbook` serves.

The rule that replaces the proxy is:

    A scheduled job is MODEL-BEARING when it produces a decision that reaches a
    person or a served surface -- wherever its thresholds live.

WHAT THIS SCRIPT DOES *NOT* DO: decide that.
--------------------------------------------
Automated classification was attempted twice here and abandoned, and the numbers
are recorded so nobody retries it expecting a different result:

  attempt 1 -- "writes a served table OR posts to Discord OR imports lib/":
              53 of 58 schedulers came back model-bearing. No discriminating
              power at all; it had swapped one loose proxy for three.

  attempt 2 -- "(named threshold constants OR label constants OR ranking)
              AND (served write OR Discord)": 19 of 58, a plausible-looking
              list -- and wrong on the two jobs the review had just flagged.
              `phase6-playbook-daily` writes `playbook_cards`, which a router
              serves, but expresses its 12 setup masks as inline conditions
              rather than named constants, so it scored judges=False.
              `regime-combo-weekly` writes through a helper the write-regex
              does not see, so it scored reaches=False. Both FALSE NEGATIVES,
              both the exact cases that motivated the sweep.

Tuning further would mean fitting the heuristic to an answer already known,
which is how a gate ends up agreeing with its author instead of with the code.

So classification is a RECORDED HUMAN JUDGEMENT, kept in the two tables in
`docs/product/07-MODEL-REGISTRY.md` -- the scheduler table and the deliberate-
exclusion table. This script's contract is narrower and checkable:

  1. every scheduler in deploy.sh resolves to a real entrypoint file, and
  2. every one appears in exactly one of those two tables,

so a new scheduler fails the build until somebody classifies it. It prints the
evidence that makes that judgement cheap, and flags nothing as decided.

WHY IT IS A SCRIPT AND NOT A HAND-MAINTAINED TABLE
--------------------------------------------------
The first pass at this mapping was written as a one-off regex over deploy.sh and
was WRONG: jobs whose flags are built in a `common_flags` bash array rather than
inline are invisible to a naive `--command` search, and the regex then attributed
a NEIGHBOURING module to them. It reported `audit-infra-drift` running
`gcp.audit_magnitude_drift` and `freshness-watchdog` running
`gcp.audit_infra_drift`. Both false, both confident.

That is the defect class the whole PR is about, so the resolver here parses
shell FUNCTION BODIES and asserts that every scheduler resolves. An entry it
cannot resolve is a failure, never a skip.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEPLOY = REPO / "gcp" / "deploy.sh"
ROUTERS = REPO / "platform" / "api" / "routers"


def _uncommented(text: str) -> str:
    """Drop whole-line shell comments.

    Needed because a comment inside a `common_flags` array otherwise matches the
    `--args` search -- the first version of this parser read the comment
    "# CLAUDE.md Rule 0: --args=VALUE because value starts with -." as the
    freshness-watchdog job's arguments.
    """
    return "\n".join(l for l in text.split("\n") if not l.lstrip().startswith("#"))


def shell_functions(text: str) -> dict[str, str]:
    """name -> body, by brace depth. Job flags and the `gcloud run jobs` call
    that consumes them live in the same function, which is what makes the
    array form resolvable at all."""
    out, cur, buf, depth = {}, None, [], 0
    for line in text.split("\n"):
        m = re.match(r"^([A-Za-z_]\w*)\(\)\s*\{", line)
        if m and cur is None:
            cur, buf, depth = m.group(1), [], 1
            continue
        if cur is None:
            continue
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            out[cur], cur = "\n".join(buf), None
            continue
        buf.append(line)
    return out


def _expand_locals(value: str, body: str) -> str:
    """Substitute `${var}` / `$var` from `local var=...` in the same function."""
    def sub(m):
        name = m.group(1) or m.group(2)
        a = re.search(rf'^\s*(?:local\s+)?{re.escape(name)}=(?:"([^"]*)"|(\S+))', body, re.M)
        return (a.group(1) or a.group(2)) if a else m.group(0)
    return re.sub(r"\$\{(\w+)\}|\$(\w+)", sub, value)


def resolve_jobs(text: str) -> dict[str, dict]:
    """job name -> {entrypoint, args, kind}."""
    jobs: dict[str, dict] = {}
    for body in shell_functions(text).values():
        names = sorted(set(re.findall(r"gcloud run jobs (?:create|update) ([\w-]+)", body)))
        if not names:
            continue
        cmd = re.search(r"--command\s+\"([^\"]+)\"", body)
        arg = re.search(r"\"?--args=(?:\")?([^\"\n]+)", body) or \
              re.search(r"--args\s+\"([^\"]+)\"", body)
        entry, kind = None, None
        if cmd:
            parts = [p for p in cmd.group(1).split(",") if p and p != "python"]
            if parts and parts[0] == "-m":
                entry, kind = parts[1], "module"
            elif parts:
                entry, kind = parts[0], "script"
        if entry is None and arg:
            # `--args="${default_args}"` -- strat-engine puts the module in a
            # shell variable, so the literal value is useless. Resolve simple
            # local assignments in the same body rather than giving up; giving
            # up here is what left three schedulers "unresolved".
            raw = _expand_locals(arg.group(1), body)
            a = [p for p in raw.split(",") if p]
            if a and a[0] == "-m" and len(a) > 1:
                entry, kind = a[1], "module"
        for n in names:
            jobs.setdefault(n, {"entrypoint": entry, "kind": kind,
                                "args": arg.group(1).strip() if arg else None})
    return jobs


def resolve_services(text: str) -> dict[str, dict]:
    """Cloud Run SERVICES. `discord-warm-*` targets one to keep it warm, so a
    scheduler can legitimately point at something that is not a job at all --
    which the first version reported as an unresolved parse failure."""
    return {m.group(1): {"entrypoint": None, "kind": "service", "args": None}
            for m in re.finditer(r"gcloud run deploy ([\w-]+)", text)}


def resolve_schedulers(text: str) -> dict[str, tuple[str, str]]:
    """scheduler -> (cron, job). Same shape the registry's own gate parses."""
    out = {}
    for line in text.split("\n"):
        m = re.search(r'_schedule[a-z_]*\s+"([^"]+)"\s+\\?\s*"([^"]+)"\s+\\?\s*"([^"]+)"', line)
        if m:
            out[m.group(1)] = (m.group(2), m.group(3))
    return out


def entry_path(entry: str, kind: str) -> Path | None:
    if not entry:
        return None
    if kind == "script":
        p = REPO / entry
        return p if p.exists() else None
    p = REPO / (entry.replace(".", "/") + ".py")
    if p.exists():
        return p
    p = REPO / entry.replace(".", "/") / "__main__.py"
    return p if p.exists() else None


_WRITE_RE = re.compile(
    r"INSERT\s+INTO\s+([a-z_][\w]*)|upsert_dataframe\(\s*[^,]+,\s*['\"]([a-z_]\w*)['\"]",
    re.I)


def served_tables() -> set[str]:
    """Tables any FastAPI router reads. A write into one of these is a decision
    that reaches a person."""
    tables: set[str] = set()
    if not ROUTERS.exists():
        return tables
    for f in ROUTERS.rglob("*.py"):
        for m in re.finditer(r"FROM\s+([a-z_][\w]*)", f.read_text(), re.I):
            tables.add(m.group(1).lower())
    return tables


def evidence(path: Path, served: set[str]) -> dict:
    src = path.read_text()
    writes = {m.group(1) or m.group(2) for m in _WRITE_RE.finditer(src)}
    writes = {w.lower() for w in writes if w}
    return {
        "writes": sorted(writes),
        "writes_served": sorted(writes & served),
        "discord": bool(re.search(r"send_to_discord|DISCORD_WEBHOOK", src)),
        "lib_imports": sorted(set(re.findall(r"(?:from|import)\s+(lib\.[\w.]+)", src))),
    }


#: Registry tables that together must cover every scheduler.
LISTED_HEADER = "| Scheduler | Cron (`America/New_York`) | Job | Serves |"
EXCLUDED_HEADER = "| Scheduler | Job | Why it is not model-bearing |"


def registry_tables() -> tuple[set[str], set[str]]:
    """(listed, excluded) scheduler names from the registry's two tables."""
    text = (REPO / "docs" / "product" / "07-MODEL-REGISTRY.md").read_text()

    def names(header: str) -> set[str]:
        if header not in text:
            return set()
        body = text.split(header, 1)[1].split("\n\n", 1)[0]
        return {m.group(1) for m in re.finditer(r"^\|\s*`([\w-]+)`", body, re.M)}

    return names(LISTED_HEADER), names(EXCLUDED_HEADER)


def hints(ev: dict) -> str:
    """Evidence, not a verdict. Phrased so it reads as "look here", because
    both attempts at turning this into a verdict were wrong (see module docstring)."""
    bits = []
    if ev["writes_served"]:
        bits.append("writes " + ", ".join(ev["writes_served"]) + " (a router serves this)")
    elif ev["writes"]:
        bits.append("writes " + ", ".join(ev["writes"][:3]))
    if ev["discord"]:
        bits.append("posts to Discord")
    real = [l for l in ev["lib_imports"] if l not in INFRA_IMPORTS]
    if real:
        bits.append("imports " + ", ".join(real[:3]))
    return "; ".join(bits) or "no write, no Discord, no lib/ import found"


#: `lib/` modules that are plumbing, not model code. Counting these is what made
#: the original import proxy useless.
INFRA_IMPORTS = {"lib.logging_config", "lib.eastern_time", "lib.config"}


def main(argv: list[str]) -> int:
    text = _uncommented(DEPLOY.read_text())
    jobs, scheds, served = resolve_jobs(text), resolve_schedulers(text), served_tables()
    jobs.update({k: v for k, v in resolve_services(text).items() if k not in jobs})
    listed, excluded = registry_tables()

    unresolved, unclassified, rows = [], [], []
    for s, (cron, job) in sorted(scheds.items()):
        j = jobs.get(job)
        if j and j["kind"] == "service":
            rows.append({"scheduler": s, "cron": cron, "job": job, "entrypoint": f"(service {job})",
                         "args": None, "classified": ("listed" if s in listed else
                         "excluded" if s in excluded else None),
                         "evidence": "pings a Cloud Run service; runs no entrypoint of its own",
                         "writes": [], "writes_served": [], "discord": False, "lib_imports": []})
            if s not in listed and s not in excluded:
                unclassified.append((s, f"(service {job})", "warms a Cloud Run service"))
            continue
        p = entry_path(j["entrypoint"], j["kind"]) if j and j["entrypoint"] else None
        if p is None:
            unresolved.append(f"{s} -> {job} -> {(j or {}).get('entrypoint')}")
            continue
        ev = evidence(p, served)
        where = "listed" if s in listed else "excluded" if s in excluded else None
        if where is None:
            unclassified.append((s, j["entrypoint"], hints(ev)))
        rows.append({"scheduler": s, "cron": cron, "job": job,
                     "entrypoint": j["entrypoint"], "args": j["args"],
                     "classified": where, "evidence": hints(ev), **ev})

    if "--json" in argv:
        print(json.dumps(rows, indent=1))
    else:
        print(f"{len(scheds)} schedulers declared in deploy.sh, {len(rows)} resolved")
        print(f"{len(listed)} listed as model-bearing, {len(excluded)} deliberately excluded, "
              f"{len(unclassified)} UNCLASSIFIED\n")
        for s, e, h in unclassified:
            print(f"  UNCLASSIFIED  {s:36} {e:44} {h}")

    for u in unresolved:
        print(f"UNRESOLVED (parser failure, not an exclusion): {u}", file=sys.stderr)

    return 1 if (unresolved or unclassified) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
