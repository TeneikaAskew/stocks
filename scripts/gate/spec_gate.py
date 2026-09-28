#!/usr/bin/env python3
"""Spec gate: refuses code changes that have no FEAT-ID, approved spec, and plan.

Usage:
  python3 scripts/gate/spec_gate.py --commit              # pre-commit hook: the staged tree
  python3 scripts/gate/spec_gate.py --pr [BASE [HEAD]]    # a PR's diff (default origin/main HEAD)
  python3 scripts/gate/spec_gate.py --check-spec <path>   # validate one spec file's frontmatter

Exit 0 = ok, 1 = blocked, 2 = usage. Prints what to do next.

Every changed file is gated except documentation: docs/**, *.md, *.drawio,
LICENSE*. A gated file needs a feature/<feat-id>-<slug> or
fix/<feat-id>-<slug> branch whose plan and approved spec validate, unless the
branch prefix allows that path:

  chore/             dependency manifests, lockfiles, and the gate's own files; in a
                     manifest only the dependency fields, never scripts or tool config
  bot/superpowers-   the vendored skills under .claude/skills/
  spike/             anything, for local commits only: a spike opens no PR

No branch is exempt by name. A pull request from a fork gets no prefix
allowance. A detached HEAD that stages gated files is blocked: name the branch
with SPEC_GATE_BRANCH=<branch> git commit ...

--commit reads the plan from the index, so it validates what is being
committed; the catalog row and the approved spec are read from HEAD (during a
merge, from MERGE_HEAD). --pr reads the plan from the PR head's git objects and
the catalog row and spec from the merge base, so a PR cannot add its own
capability or approve its own spec, and CI runs this script from the base
branch without checking the PR out. In CI the branch
comes from PR_HEAD_REF, fork detection from PR_HEAD_REPO and PR_BASE_REPO, and
PR_TITLE, PR_BODY, PR_NUMBER and PR_DRAFT drive the metadata and close-out
checks, and PR_BASE_REF must be main. Any harness (Claude Code, Codex, a human) hits the same check.
"""
from __future__ import annotations

import ast
import html
import json
import datetime
import os
import pathlib
import posixpath
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPECS = "docs/superpowers/specs"
PLANS = "docs/superpowers/plans"
CATALOG = "docs/product/02-FEATURE-CATALOG.md"
REQUIREMENTS = "docs/product/01-PRODUCT-REQUIREMENTS.md"
TRACEABILITY = "docs/product/12-PR-ISSUE-TRACEABILITY.md"
CANVASES = "docs/product/canvases.yml"
MAIN = "main"
# The product documents a feature change may touch, besides its own catalog row and record
# and its own traceability section: the machine-owned registry the exporter reads, and what
# it generates. Everything else under docs/product/ changes on its own docs/ branch.
PRODUCT_DOCS = "docs/product/"
REGISTRY_DOCS = ("docs/product/07-MODEL-REGISTRY.md", "docs/product/generated/model-registry.json")

FEAT_ROW = re.compile(r"^\|\s*\[?(FEAT-[A-Z]+-\d{3})\b", re.M)
FEAT_IDS = re.compile(r"\bFEAT-[A-Z]+-\d{3}\b")
BRANCH = re.compile(r"^(feature|fix)/(feat-[a-z]+-\d{3})(-[a-z0-9]+)+$")   # lowercase kebab-case: git refs are case-sensitive
REQ_SHAPE = re.compile(r"^REQ-[A-Z]+-\d{3}$")
REQ_DEFINITION = re.compile(r"\*\*(REQ-[A-Z]+-\d{3}):\*\*")
CHECKBOX = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.*\S)\s*$")
HEADING = re.compile(r"^(#{1,6})\s")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PR_REF = re.compile(r"^#?(\d+)$")
PR_MENTION = re.compile(r"#(\d+)(?![\w])")   # #123abc names nothing
CLOSE_OUT_FIELDS = ("Status", "Last reviewed")

MANIFEST = re.compile(
    r"(^|/)(package(-lock)?\.json|requirements[^/]*\.(txt|lock)|pyproject\.toml|poetry\.lock|uv\.lock"
    r"|yarn\.lock|pnpm-lock\.yaml|bun\.lock)$"
)
# A lockfile names where each package is fetched from; CI installs exactly that (round six: an attacker
# tarball with its own integrity hash passed as "a lockfile"). Only the public registries.
REGISTRY_HOSTS = ("registry.npmjs.org", "registry.yarnpkg.com", "files.pythonhosted.org", "pypi.org")


def lockfile_sources(name: str, text: str) -> list[str]:
    """Every location a lockfile fetches a package from, parsed as its installer parses it
    (round seven: `HTTPS://`, `https:\/\/` and `file:` slipped a text scan). Raises ValueError
    when the file cannot be parsed."""
    found: list[str] = []
    if name == "package-lock.json":
        def walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ("resolved", "link") and isinstance(v, (str, bool)):
                        found.append(str(v))
                    walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v)
        walk(json.loads(text))
    elif name in ("poetry.lock", "uv.lock"):
        for pkg in tomllib.loads(text).get("package", []):
            src = pkg.get("source")
            if isinstance(src, dict):
                if name == "uv.lock" and set(src) <= {"registry"}:
                    found.append(str(src.get("registry", "")))
                elif name == "uv.lock" and set(src) <= {"virtual", "workspace"}:
                    continue   # the project itself
                elif name == "poetry.lock" and src.get("type") == "legacy":
                    found.append(str(src.get("url", "")))
                else:
                    found.append("source:" + ",".join(sorted(src)))
    elif name == "yarn.lock":
        for m in re.finditer(r'(?m)^\s+(resolved|resolution)\s*:?\s*"?([^"\n]+)"?', text):
            value = m.group(2).strip()
            found.append(value if m.group(1) == "resolved" or "@npm:" not in value else "https://registry.yarnpkg.com/")
    elif name == "pnpm-lock.yaml":
        for m in re.finditer(r"(?m)^\s+(tarball|directory|repo|commit|path|type)\s*:\s*(.+)$|resolution:\s*\{([^}]*)\}", text):
            if m.group(3) is not None:
                for key, value in re.findall(r"([\w-]+)\s*:\s*([^,}]+)", m.group(3)):
                    found.append(value.strip() if key == "tarball" else ("https://registry.npmjs.org/" if key == "integrity" else "source:" + key))
            else:
                found.append(m.group(2).strip() if m.group(1) == "tarball" else "source:" + m.group(1))
    else:   # bun.lock: JSON with trailing commas
        walk_text = re.sub(r",\s*([}\]])", r"\1", text)
        found += [m.group(0) for m in re.finditer(r"(?i)\b(?:https?:|file:|link:|git\+|workspace:)[^\s\"']*", walk_text)]
    return found


def lockfile_offence(name: str, text: str) -> str | None:
    try:
        sources = lockfile_sources(name, text)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        return f"cannot be parsed ({str(e)[:60]}); the gate does not guess what an installer would fetch"
    for src in sources:
        if src.startswith("source:") or not (m := re.match(r"(?i)https://([^/\s\"']+)", src)) or m.group(1).lower() not in REGISTRY_HOSTS:
            return f"resolves a package from {src[:60]!r}; a chore/ branch installs from the public registries over https only"
    return None
HOOK = ".githooks/pre-commit"
GATE_SCRIPTS = ("scripts/gate/spec_gate.py", "scripts/gate/export_model_registry.py")
GATE_FILES = (
    "scripts/gate/",
    HOOK,   # the one hook, not the directory: any other executable there runs on every clone with core.hooksPath set
    ".github/workflows/spec-gate.yml",
    ".github/workflows/registry-check.yml",
    "tests/scripts/test_spec_gate.py",
    "tests/scripts/test_export_model_registry.py",
)
# Every branch a pull request may come from, in full: feature/ and fix/ carry a FEAT-ID
# (BRANCH), the rest a kebab-case slug. spike/ is refused before this in PR mode.
OTHER_BRANCH = re.compile(r"^((docs|chore)/[a-z0-9]+(-[a-z0-9]+)*|bot/superpowers-[a-z0-9]+(-[a-z0-9]+)*)$")
# What each gate workflow must still do after a change to it. The base's gate checks the
# head's copy for these, because registry-check.yml runs from the head and could otherwise
# be replaced by a no-op that keeps its job name green.
WORKFLOW_CONTRACTS = {
    ".github/workflows/registry-check.yml": {
        # The required check is `<workflow name> / <job name>`: both are the contract
        # (stocks#1205 r4121413674)
        "name": "registry-check",
        "jobs": {'python3 "$gate" --pr "$BASE_SHA" "$HEAD_SHA"': "registry"},
        "checkout": "head",   # runs the PR's files: a checkout pinned to the base would verify main instead
        "trigger": "pull_request",
        "types": {"opened", "synchronize", "reopened"},
        # A statement counts when it STARTS with the command (after wrappers), so a word that
        # merely carries the text as an argument (`python3 -c '' python3 "$gate" ...`) does not.
        # (the hook's mode is read by the gate itself from the head tree, not from a listed
        # `git ls-tree`: solyra#72 r4120913613)
        "run": ('python3 -m py_compile "$gate"', 'python3 "$gate" --pr "$BASE_SHA" "$HEAD_SHA"',
                "python3 -m pytest tests/scripts/test_spec_gate.py"),
        # required where the base or the head carries the script: solyra has no model registry to export
        "run_if_present": {
            "scripts/gate/export_model_registry.py": ('python3 scripts/gate/export_model_registry.py --check --rev "$HEAD_SHA" --base "$BASE_SHA"',),
        },
    },
    ".github/workflows/spec-gate.yml": {
        "name": "spec-gate",
        "jobs": {'python3 scripts/gate/spec_gate.py --pr "$BASE_SHA" "$HEAD_SHA"': "gate",
                 "python3 -m pytest tests/scripts/test_spec_gate.py": "base-suite"},
        "checkout": "base",   # pull_request_target: a head checkout would run PR-controlled code with its token
        "trigger": "pull_request_target",
        "types": {"opened", "synchronize", "reopened", "edited", "ready_for_review"},
        # The base's verdict first; then the base's own suite judges the proposed gate, which
        # replaces the base's copy only after the verdict (solyra#72 r4120337733)
        # (solyra#72 r4120913602: the fetch is what makes a fork's head sha reachable from
        # the base checkout; without it the verdict never runs)
        "run": ('python3 scripts/gate/spec_gate.py --pr "$BASE_SHA" "$HEAD_SHA"',
                'git show "$HEAD_SHA:scripts/gate/spec_gate.py" > "$RUNNER_TEMP/proposed/spec_gate.py"',
                "python3 -m pytest tests/scripts/test_spec_gate.py", 'git fetch --no-tags origin "$HEAD_SHA"'),
        # Where the exporter exists, the base's exporter suite judges the proposed exporter the
        # same way (stocks#1205 r4120913731: registry-check runs only the PR's --check)
        "run_if_present": {
            "scripts/gate/export_model_registry.py": (
                'git show "$HEAD_SHA:scripts/gate/export_model_registry.py" > "$RUNNER_TEMP/proposed/export_model_registry.py"',
                "python3 -m pytest tests/scripts/test_export_model_registry.py"),
        },
        # In this order: within one job by statement order, across jobs by `needs`
        # (solyra#72 r4120515772). GitHub runs jobs without `needs` concurrently. A command
        # the contract does not require here (run_if_present) is skipped.
        "order": ('git fetch --no-tags origin "$HEAD_SHA"',
                  'python3 scripts/gate/spec_gate.py --pr "$BASE_SHA" "$HEAD_SHA"',
                  'git show "$HEAD_SHA:scripts/gate/spec_gate.py" > "$RUNNER_TEMP/proposed/spec_gate.py"',
                  'git show "$HEAD_SHA:scripts/gate/export_model_registry.py" > "$RUNNER_TEMP/proposed/export_model_registry.py"',
                  "python3 -m pytest tests/scripts/test_spec_gate.py",
                  "python3 -m pytest tests/scripts/test_export_model_registry.py"),
        # The suites run PR-controlled Python: their job holds no checkout credentials and
        # never holds the verdict (stocks#1205 r4120528961)
        "isolated": ("python3 -m pytest tests/scripts/test_spec_gate.py", "python3 -m pytest tests/scripts/test_export_model_registry.py"),
        # The proposed files reach the suite's job as an artifact: uploaded after the export in
        # its job, downloaded into scripts/gate before the suite in its job, under one name
        # (solyra#72 r4120913592: without the handoff the base's suite tests the base's gate)
        "handoff": {"export": 'git show "$HEAD_SHA:scripts/gate/spec_gate.py" > "$RUNNER_TEMP/proposed/spec_gate.py"',
                    "suite": "python3 -m pytest tests/scripts/test_spec_gate.py",
                    "upload_path": "$RUNNER_TEMP/proposed", "download_path": "scripts/gate"},
        # The verdict reads its inputs from the event, bound on its own step: a rebound
        # PR_NUMBER skips the close-out for every later PR (solyra#72 r4120775915)
        "env": {
            "BASE_SHA": "${{ github.event.pull_request.base.sha }}",
            "HEAD_SHA": "${{ github.event.pull_request.head.sha }}",
            "PR_HEAD_REF": "${{ github.event.pull_request.head.ref }}",
            "PR_BASE_REF": "${{ github.event.pull_request.base.ref }}",
            "PR_HEAD_REPO": "${{ github.event.pull_request.head.repo.full_name }}",
            "PR_BASE_REPO": "${{ github.repository }}",
            "PR_NUMBER": "${{ github.event.pull_request.number }}",
            "PR_DRAFT": "${{ github.event.pull_request.draft }}",
            "PR_TITLE": "${{ github.event.pull_request.title }}",
            "PR_BODY": "${{ github.event.pull_request.body }}",
        },
    },
}

# The names the gate reads from its environment. A workflow or hook that assigns, exports,
# unsets or reads into one of them (a prefix assignment, a line of its own, a write to
# $GITHUB_ENV) runs the gate on inputs the PR chose (solyra#72 r4120775915).
GATE_INPUT = r"(PR_[A-Z_]+|BASE_SHA|HEAD_SHA|SPEC_GATE_[A-Z_]+)"
# What the shell and Python read before the gate runs: a fake python3 on PATH, a BASH_ENV
# that exits, PYTEST_ADDOPTS=--collect-only or a PYTHONPATH shadowing pytest turn the
# contract commands into no-ops while their text stays (solyra#72 r4121374618, r4121374639)
RUNTIME_ENV = (r"(PATH|HOME|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|CDPATH|IFS|TMPDIR|PYTHON\w*|PYTEST\w*|PIP_\w+|UV_\w+|VIRTUAL_ENV|CONDA\w*"
               r"|NODE_OPTIONS|NODE_PATH|NPM_\w+|GIT_\w+|LD_\w+|RUNNER_TEMP|GITHUB_ENV|GITHUB_WORKSPACE"
               # red-team round two: a proxy or CA bundle would route the verdict step's `pip install` elsewhere
               r"|HTTPS?_PROXY|https?_proxy|ALL_PROXY|all_proxy|NO_PROXY|no_proxy|SSL_CERT_\w+|REQUESTS_CA_BUNDLE|CURL_CA_BUNDLE)")
PROTECTED = rf"(?:{GATE_INPUT}|{RUNTIME_ENV})"
INPUT_OVERRIDE = re.compile(r"(?<![\w$.{-])" + PROTECTED + r"=|\b(export|unset|declare|typeset|local|readonly|read)\b[^;|&\n]*?(?<![\w$.{-])" + PROTECTED + r"\b|(?<![\w])(GITHUB_PATH)\b")
ENV_KEY = re.compile(r"^\s*(" + GATE_INPUT[1:-1] + "|" + RUNTIME_ENV[1:-1] + r"):", re.M)


def runtime_env_keys(body: str) -> list[str]:
    """The names of RUNTIME_ENV that any `env:` mapping of the workflow sets, at the workflow,
    a job or a step, in block or flow form."""
    lines, found = body.splitlines(), []
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)(-\s+)?env:\s*(.*)$", line)
        if not m:
            continue
        level = len(m.group(1)) + len(m.group(2) or "")
        inline = m.group(3).strip()
        text = inline if inline else "\n".join(lines[i + 1:block_end(lines, i, level)])
        for name in re.findall(r"(?:^|[{,\n])\s*['\"]?([A-Za-z_]\w*)['\"]?\s*:", text):   # stocks#1205 r4121602788: keys may be quoted
            if re.fullmatch(RUNTIME_ENV, name) and name not in found:
                found.append(name)
    return found


def input_overrides(text: str) -> list[str]:
    """The gate inputs a comment-stripped text assigns or unsets, in order of appearance."""
    found: list[str] = []
    for m in INPUT_OVERRIDE.finditer(text):
        name = next(g for g in m.groups() if g and g not in ("export", "unset", "declare", "typeset", "local", "readonly", "read"))
        if name not in found:
            found.append(name)
    return found


def end_of(lines: list[str], i: int) -> int:
    return block_end(lines, i, indent(lines[i]))


def step_envs(body: str, command: str) -> list[dict[str, str]]:
    """The `env:` mapping of every step whose run text invokes `command`, values with their
    whitespace removed so `${{ github.event.pull_request.number }}` compares by content."""
    lines, out = body.splitlines(), []
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)-(\s+\S|\s*$)", line)   # `- key:` or a dash on a line of its own (stocks#1205 r4122021105)
        if not m or (k := enclosing_key(lines, i, indent(line))) is None or lines[k].strip() != "steps:":
            continue
        end = block_end(lines, i, indent(line))
        key_indent = len(m.group(1)) + 2 if m.group(2).strip() else indent(lines[first_below(lines, i, end_of(lines, i))]) if i + 1 < end_of(lines, i) else len(m.group(1)) + 2
        item = [re.sub(r"^(\s*)-\s*", r"\1  ", lines[i])] + lines[i + 1:end]
        run, env, j = [], {}, 0
        while j < len(item):
            if (rm := re.match(r"^(\s*)run:\s*(.*)$", item[j])) and len(rm.group(1)) == key_indent:
                value = rm.group(2).strip()
                run = [value] if value and not value.startswith(("|", ">")) else []
                j += 1
                while j < len(item) and (not item[j].strip() or indent(item[j]) > key_indent):
                    run.append(item[j].strip())
                    j += 1
                continue
            if (em := re.match(r"^(\s*)env:\s*$", item[j])) and len(em.group(1)) == key_indent:
                j += 1
                while j < len(item) and (not item[j].strip() or indent(item[j]) > key_indent):
                    if (vm := re.match(r"^\s*['\"]?([\w-]+)['\"]?:\s*(.*)$", item[j])):
                        env[vm.group(1)] = re.sub(r"\s+", "", re.sub(r"\s+#.*$", "", vm.group(2)).strip().strip("'\""))
                    j += 1
                continue
            j += 1
        if any(invokes(st, command) for st in shell_statements("\n".join(run))):
            out.append(env)
    return out


def indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def enclosing_key(lines: list[str], i: int, below: int) -> int | None:
    """Index of the nearest line above `i` that is a mapping key indented less than `below`."""
    for j in range(i - 1, -1, -1):
        if lines[j].strip() and indent(lines[j]) < below and re.match(r"^\s*(-\s+)?[\w.-]+:", lines[j]):
            return j
    return None


def first_below(lines: list[str], start: int, end: int) -> int:
    """Index of the first non-blank line after `start` and before `end`, or `start + 1`: a blank
    line under a key is insignificant to YAML, so the block's indent comes from its first entry
    (red-team round three: a blank line after `jobs:` emptied the job list)."""
    return next((k for k in range(start + 1, end) if lines[k].strip()), start + 1)


def block_end(lines: list[str], start: int, level: int) -> int:
    """First line after `start` whose indentation is at most `level` (blank lines skipped)."""
    j = start + 1
    while j < len(lines) and (not lines[j].strip() or indent(lines[j]) > level):
        j += 1
    return j


def conditional(lines: list[str], start: int, end: int, level: int) -> bool:
    """Whether a block carries an `if:` or a `continue-on-error:` (other than false) among its
    keys at `level`: GitHub may then skip it or ignore its failure, so a command inside
    proves nothing (solyra#72 r4119837190, r4119957700)."""
    for j in range(start, end):
        # `- if: false` carries the key on the item's dash line (stocks#1205, this round)
        dash = re.match(r"^(\s*)(-\s+)", lines[j])
        if (len(dash.group(1)) + len(dash.group(2)) if dash else indent(lines[j])) != level:
            continue
        if re.match(r"^\s*(-\s+)?if:", lines[j]):
            return True
        if (m := re.match(r"^\s*(-\s+)?continue-on-error:\s*(.*)$", lines[j])) and m.group(2).split("#")[0].strip().strip("'\"") != "false":
            return True
    return False


def every_run_text(text: str) -> str:
    """The text of every `run:` value in a workflow, whatever its `if:`, `shell:`, block indicator or
    quoting: the scans for writes and inline code read this, since a step the contract may not count
    still executes (red-team round five)."""
    lines = [ln for ln in text.replace("\x00", "").splitlines() if not ln.lstrip().startswith("#")]
    out, i = [], 0
    while i < len(lines):
        m = re.match(r"^(\s*)(-\s+)?run\s*:\s*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        key_indent = len(m.group(1)) + len(m.group(2) or "")
        value = re.sub(r"\s+#.*$", "", m.group(3)).strip()
        i += 1
        block = re.match(r"^[|>][+-]?\d?[+-]?$", value)
        parts = [] if block else [value]
        while i < len(lines) and (not lines[i].strip() or indent(lines[i]) > key_indent) \
                and (block or not re.match(r"^(-(\s+|$)|[\w.-]+\s*:(\s|$))", lines[i].strip())):
            parts.append(lines[i].strip())
            i += 1
        out.append("\n".join(p for p in parts if p))
    return "\n".join(out)


def workflow_executes(text: str) -> tuple[str, str]:
    """(the text of every unconditional `run:` step, the whole file), both with comment lines
    removed, so a contract command counts only where the workflow executes it: not in a
    comment, not in an unused scalar, and not in a step or job an `if:` may skip."""
    lines = [ln for ln in text.replace("\x00", "").splitlines() if not ln.lstrip().startswith("#")]
    runs, i = [], 0
    while i < len(lines):
        m = re.match(r"^(\s*)(-\s+)?run:\s*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        key_indent = len(m.group(1)) + len(m.group(2) or "")
        value = m.group(3).strip()
        start = i
        i += 1
        step = [value] if value and not re.match(r"^[|>][+-]?\d?[+-]?$", value) else []   # `|2` is a block too (round five)
        if not step:
            while i < len(lines) and (not lines[i].strip() or indent(lines[i]) > key_indent):
                step.append(lines[i].strip())
                i += 1
            if value.startswith(">"):
                # a folded scalar is ONE line to the shell: `echo x` followed by the commands
                # runs an echo with arguments (stocks#1205 r4120660269)
                step = [" ".join(ln for ln in step if ln)]
        # The step is the list item holding this key; the job is the mapping holding `steps:`.
        item = next((j for j in range(start, -1, -1) if indent(lines[j]) <= key_indent and lines[j].lstrip().startswith("-")), start)
        item_level = indent(lines[item])
        # solyra#72 r4121374653: `env: {run: ...}` is a variable named run; a step's command is
        # the `run:` at the step's own key level, in an item of a `steps:` list
        steps_key = enclosing_key(lines, item, item_level)
        if key_indent != item_level + 2 or steps_key is None or lines[steps_key].strip() != "steps:":
            continue
        skipped = conditional(lines, item, block_end(lines, item, item_level), key_indent)
        # a step with its own `shell:` (`bash {0}` drops -e, `sh` is not bash) is not judged
        # (stocks#1205 r4120828215: `shell: echo {0}` prints the script's path and succeeds;
        # a `defaults: run: shell:` on the job or the workflow does the same for every step)
        shell = next((shell_value(sm.group(3)) for j in range(item, block_end(lines, item, item_level))
                      if (sm := re.match(r"^(\s*)(-\s+)?shell:\s*(.*)$", lines[j]))
                      and len(sm.group(1)) + len(sm.group(2) or "") == key_indent), None)
        steps_key = enclosing_key(lines, item, item_level)
        if steps_key is not None:
            job_level = indent(lines[steps_key])
            job_key = enclosing_key(lines, steps_key, job_level)
            if job_key is not None:
                job_end = block_end(lines, job_key, indent(lines[job_key]))
                skipped = skipped or conditional(lines, job_key, job_end, job_level)
                if shell is None:
                    shell = default_shell(lines, job_key + 1, job_end, job_level)
        if shell is None:
            shell = default_shell(lines, 0, len(lines), 0)
        skipped = skipped or (shell or "bash") != "bash"
        if not skipped:
            runs.extend(step + [STEP_BOUNDARY])   # each step is its own script: an exit ends only it
    return "\n".join(runs), "\n".join(lines)


STEP_BOUNDARY = "\x00STEP\x00"   # a NUL cannot be typed into YAML or a hook, so no run text collides with it
PLACEHOLDERS = re.compile(r"__SUB__|__VAR__|__STEP__|\x00")


def shell_value(raw: str) -> str:
    return re.sub(r"\s+#.*$", "", raw).strip().strip("'\"")


def default_shell(lines: list[str], start: int, end: int, level: int) -> str | None:
    """The `defaults: run: shell:` declared at `level` within lines[start:end], if any."""
    for j in range(start, end):
        if indent(lines[j]) == level and re.match(r"^\s*defaults:\s*$", lines[j]):
            for k in range(j + 1, block_end(lines, j, level)):
                if indent(lines[k]) == level + 2 and re.match(r"^\s*run:\s*$", lines[k]):
                    for n in range(k + 1, block_end(lines, k, level + 2)):
                        if (m := re.match(r"^\s*shell:\s*(.*)$", lines[n])):
                            return shell_value(m.group(1))
    return None


# First words that consume their arguments as text rather than running them.
NON_EXECUTING = {"echo", "printf", "cat", "tee", ":", "true", "false", "test", "[", "[[", "read", "export", "local",
                 "declare", "readonly", "grep", "sed", "awk", "exit", "return", "shift", "trap"}


def quoted_text(m: re.Match) -> str:
    """A quoted span with its shell structure removed: '...' becomes '', and inside "..."
    every newline, separator and reserved word becomes filler."""
    span = m.group(0)
    if span.startswith("'"):
        return "''"
    body = re.sub(r"[\n;|&{}]|\b(then|do|else|elif|fi|done|esac|case|if|while|until)\b", "_", span[1:-1])
    return '"' + body + '"'


def shell_statements(runs: str, errexit: bool = True) -> list[str]:
    """The statements of the collected run text that the shell executes unconditionally and
    whose failure propagates: heredoc bodies, single-quoted text, comments, statements led
    by a non-executing word (echo, printf, cat, test ...) or by an assignment of a literal,
    the body of an `if`/`while`/`case` construct, a statement after `&&` or `||`, and a
    statement followed by `||` are all dropped (stocks#1205 r4119966265, r4120166743)."""
    # stocks#1205 r4121216898: a quoted span is text to the shell however many lines it
    # covers, so the separators and newlines inside `"..."` or '...' are neutralised first,
    # keeping the words a contract quotes (`"$BASE_SHA"`) intact
    # (red-team, this PR): the parser's own placeholders typed into a run block would be read as
    # structure, so a text carrying one satisfies nothing
    if PLACEHOLDERS.search(runs.replace(STEP_BOUNDARY, "")):
        return []
    runs = re.sub(r"\$\{\{.*?\}\}", "__VAR__", runs, flags=re.S)
    runs = re.sub(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"", quoted_text, runs, flags=re.S)
    lines, out, i = runs.splitlines(), [], 0
    depth = 0          # inside then/do/else ... fi/done, or a { } body: GitHub may never reach it
    # GitHub runs bash -e, so `errexit` starts True there; a hook starts without it, and a
    # failure before its last line is lost until `set -e`. After `set +e` a failure no longer
    # fails the step either way.
    ended = False       # after an unconditional exit nothing else in this script runs
    while i < len(lines):
        line = lines[i]
        if line.strip() == STEP_BOUNDARY:
            depth, errexit, ended, i = 0, True, False, i + 1
            continue
        if ended:
            i += 1
            continue
        while line.rstrip().endswith("\\") and i + 1 < len(lines):   # continuation
            i += 1
            line = line.rstrip()[:-1] + " " + lines[i].lstrip()
        i += 1
        if (m := re.search(r"<<-?\s*['\"]?(\w+)['\"]?", line)):   # heredoc: skip its body
            while i < len(lines) and lines[i].strip() != m.group(1):
                i += 1
            i += 1
        line = re.sub(r"'[^']*'", "''", line)
        line = re.sub(r"(^|\s)#.*$", "", line)
        line = re.sub(r"\$\{\{.*?\}\}|\$\{[^}]*\}", "__VAR__", line)   # so the braces left are bodies
        # `out=$(cmd ...)` runs cmd: the substitution is a statement of its own, and the outer
        # statement keeps its shape (`python3 "__SUB__/scripts/gate/spec_gate.py" --commit`)
        # so the word the shell invokes is still the one judged
        inner: list[str] = []
        while (m := re.search(r"\$\(([^()]*)\)|`([^`]*)`", line)):
            inner.append(m.group(1) if m.group(1) is not None else m.group(2))
            line = line[:m.start()] + "__SUB__" + line[m.end():]
        # solyra#72 r4121374631: `echo "$(cmd)"` has echo's status; only `x=$(cmd)` has cmd's
        if inner and re.match(r"^\s*[A-Za-z_]\w*=['\"]?__SUB__", line):
            lines[i:i] = inner
        # Parentheses are not separators: `(exit $rc)` inside an echo is text, and a subshell
        # `( cmd )` reads as a statement starting with `(`, which no contract prefix matches
        # `cmd &` backgrounds cmd and drops its exit status (stocks#1205 r4120528946); `2>&1` is a redirection
        # `f() { ... }` and `|| { ... }` bodies are conditional like then/fi (stocks#1205 r4120660276)
        parts = re.split(r"(\|\||&&|(?<![<>&])&(?![&>])|;;|;|\||\{|\}|\bthen\b|\bdo\b|\belse\b|\belif\b|\bfi\b|\bdone\b|\besac\b|\bcase\b)", line)
        chained = False    # after && or ||: runs only on the previous statement's outcome
        condition = False  # an if/while condition: its failure is a branch, never the step's
        for k in range(0, len(parts), 2):
            stmt, op = parts[k].strip(), parts[k + 1] if k + 1 < len(parts) else ""
            # stocks#1205 r4120913720: `! cmd` is exempt from errexit, and a condition is judged,
            # not obeyed; neither statement's failure fails the step
            if re.match(r"^(if|elif|while|until)\s", stmt):
                condition = True
            negated = bool(re.match(r"^((if|elif|while|until)\s+)*!\s", stmt))
            stmt = re.sub(r"^((if|elif|while|until|!)\s+)+", "", stmt)
            stmt = re.sub(r"^[A-Za-z_]\w*=(?!['\"$])\S*\s*", "", stmt)   # `x=1 cmd` prefix assignment
            # `command echo ...`, `env FOO=1 echo ...`, `time ...`: the wrapper runs its argument,
            # so the word after it is the command judged (solyra#72 r4120167264)
            stmt = re.sub(r"^((command|builtin|env|time|nice|nohup|sudo|xargs)\s+(-\S+\s+|[A-Za-z_]\w*=\S*\s+)*)+", "", stmt)
            # stocks#1205 r4121602767: `exec cmd` replaces the shell, so cmd's status is the
            # step's and nothing after it runs; a bare `exec 2>&1` only redirects
            replaces = bool(re.match(r"^exec\s+(?!(\d*[<>]\S*\s*)+$)", stmt))
            if replaces:
                stmt = re.sub(r"^exec\s+", "", stmt)
            elif re.match(r"^exec\b", stmt):
                stmt = ""
            if stmt and re.match(r"^trap\b", stmt):
                # solyra#72 r4121572544: `trap 'exit 0' ERR` turns every later failure into success;
                # inside `{ }` or a `then` body it still runs in this shell (red-team, this PR)
                errexit = False
            if stmt and depth == 0 and not chained and not condition and re.match(r"^(exit|return)\b", stmt):
                ended = True   # stocks#1205 r4120381459: nothing after an unconditional exit runs
                break
            if stmt and (sm := re.match(r"^set\s+(.*)$", stmt)):
                # solyra#72 r4120633462: with errexit off a failing command does not fail the step;
                # `{ set +e; }` and `if true; then set +e; fi` act on this shell too, so the depth does
                # not matter for turning it off, while turning it back on counts only at the top level
                flags = sm.group(1)
                if re.search(r"(^|\s)-\w*n\w*(\s|$)|-o\s+noexec", flags):
                    # red-team round four: `set -n` parses the rest of the step and executes none of it,
                    # with exit 0; whatever follows never runs, at any depth
                    ended = True
                    break
                if re.search(r"(^|\s)\+\w*e|\+o\s+errexit", flags):
                    errexit = False
                elif depth == 0 and not chained and not condition and re.search(r"(^|\s)-\w*e|-o\s+errexit", flags):
                    errexit = True
            executed = (stmt and not re.match(r"^[A-Za-z_]\w*=", stmt)   # `x="..."`: a value, not a command
                        and stmt.split()[0] not in NON_EXECUTING and depth == 0 and not chained and errexit
                        and not negated and not condition
                        and op not in ("||", "&&", "&", "|"))   # `cmd | true`: the pipe's status is true's; `cmd &&:` is exempt from errexit like `cmd || true` (red-team round two)
            if executed:
                out.append(stmt)
            if replaces and depth == 0 and not chained and not condition:
                ended = True
                break
            if op in ("then", "do", "case", "{"):   # `else` continues the block `then` opened
                depth += 1
                condition = False
            elif op in ("fi", "done", "esac", "}"):
                depth = max(0, depth - 1)
            chained = op in ("&&", "||")
    return out


def workflow_triggers(body: str) -> set[str]:
    """The events under the top-level `on:` of a comment-stripped workflow: an inline scalar,
    an inline list, or the keys of the block below it (stocks#1205 r4120166751)."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^on:\s*(.*)$", line)
        if not m:
            continue
        value = re.sub(r"\s+#.*$", "", m.group(1)).strip()
        if value:
            return set(re.findall(r"[A-Za-z_]+", value))
        triggers: set[str] = set()
        end = block_end(lines, i, 0)
        for j in range(i + 1, end):
            if (k := re.match(r"^\s+(?:-\s+)?([A-Za-z_]+):?\s*$", lines[j])) and indent(lines[j]) == indent(lines[first_below(lines, i, end)]):
                triggers.add(k.group(1))
        return triggers
    return set()


SKIP_NAMES = {"skip", "skipif", "xfail", "importorskip", "pytestmark", "exit", "_exit"}


def suite_escape(source: str) -> str | None:
    """A skip marker, collection hook or exit in a suite: it leaves every test name and
    assertion in place while running none of them (stocks#1205 r4121777310)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in SKIP_NAMES:
            return node.attr
        if isinstance(node, ast.Name) and node.id in SKIP_NAMES:
            return node.id
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("pytest_"):
            return node.name
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            # stocks#1205 r4122021098: a `return` first thing leaves every assertion counted and unreached
            if any(isinstance(n, (ast.Return, ast.Raise)) for n in ast.walk(node)):
                return f"{node.name}: return or raise"
    return None


def test_assertions(source: str) -> dict[str, int]:
    """{test function: number of assert statements in it}, or {} for a file that does not
    parse (which the registry check then fails on its own)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    return {node.name: sum(isinstance(n, ast.Assert) for n in ast.walk(node))
            for node in tree.body if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")}


def checkout_steps(body: str) -> list[tuple[str, bool]]:
    """(ref, persists credentials) for every actions/checkout step in a comment-stripped
    workflow: "" for a step that takes the event's default ref, True unless the step says
    `persist-credentials: false`."""
    lines, found = body.splitlines(), []
    for i, line in enumerate(lines):
        if not re.match(r"^\s*(-\s+)?uses:\s*['\"]?actions/checkout", line):
            continue
        item = next((j for j in range(i, -1, -1) if lines[j].lstrip().startswith("-")), i)
        level = indent(lines[item])
        if conditional(lines, item, block_end(lines, item, level), level + 2):
            continue   # solyra#72 r4121374610: a checkout an `if:` may skip is no checkout
        ref, persists = "", True
        for j in range(item, block_end(lines, item, level)):
            if (m := re.match(r"^\s*ref:\s*(.*)$", lines[j])):
                ref = re.sub(r"\s+#.*$", "", m.group(1)).strip().strip("'\"")
            if (m := re.match(r"^\s*persist-credentials:\s*(.*)$", lines[j])):
                persists = re.sub(r"\s+#.*$", "", m.group(1)).strip().strip("'\"").lower() != "false"
        found.append((ref, persists, item))
    return found


def checkout_refs(body: str) -> list[str]:
    return [ref for ref, _, _ in checkout_steps(body)]


def workflow_jobs(body: str) -> list[dict]:
    """The jobs of a comment-stripped workflow: {name, needs, statements, checkouts}, each
    from its own block, so a contract can tell one job's steps from another's."""
    lines = body.splitlines()
    jobs_at = next((i for i, ln in enumerate(lines) if re.match(r"^jobs:\s*$", ln)), None)
    if jobs_at is None:
        return []
    out, end = [], block_end(lines, jobs_at, 0)
    keys = [i for i in range(jobs_at + 1, end) if lines[i].strip() and indent(lines[i]) == indent(lines[first_below(lines, jobs_at, end)])
            and re.match(r"^\s*[\w.-]+:\s*$", lines[i])]
    for n, start in enumerate(keys):
        stop = keys[n + 1] if n + 1 < len(keys) else end
        block = "\n".join(lines[start:stop])
        needs: set[str] = set()
        for ln in lines[start + 1:stop]:
            if indent(ln) == indent(lines[start]) + 2 and (m := re.match(r"^\s*needs:\s*(.*)$", ln)):
                needs = set(re.findall(r"[\w.-]+", re.sub(r"\s+#.*$", "", m.group(1))))
        runs = workflow_executes(block)[0]
        out.append({"name": lines[start].strip().rstrip(":"), "needs": needs, "runs": runs,
                    "statements": shell_statements(runs), "checkouts": checkout_steps(block),
                    "artifacts": artifact_steps(block), "lines": lines[start:stop]})
    return out


def artifact_steps(block: str) -> list[dict]:
    """Every unconditional actions/upload-artifact or download-artifact step of a job block:
    {kind, name, path, line} with `line` the step's offset in the block."""
    lines, found = block.splitlines(), []
    for i, line in enumerate(lines):
        m = re.match(r"^\s*(-\s+)?uses:\s*['\"]?actions/(upload|download)-artifact", line)
        if not m:
            continue
        item = next((j for j in range(i, -1, -1) if lines[j].lstrip().startswith("-")), i)
        level, end = indent(lines[item]), block_end(lines, item, indent(lines[item]))
        if conditional(lines, item, end, level + 2):
            continue
        name = path = ""
        for j in range(item, end):
            if (km := re.match(r"^\s*name:\s*(.*)$", lines[j])):
                name = shell_value(km.group(1))
            if (km := re.match(r"^\s*path:\s*(.*)$", lines[j])):
                path = shell_value(km.group(1))
        found.append({"kind": m.group(2), "name": name, "path": path, "line": item})
    return found


def line_of(job: dict, command: str) -> int:
    """Offset in the job block of the first line whose text starts with `command`, or -1."""
    return next((i for i, ln in enumerate(job["lines"]) if re.sub(r"^(-\s+)?run:\s*", "", ln.strip()).startswith(command)), -1)


# What may follow the suite command: nothing that keeps pytest from running the tests
# (solyra#72 r4120633474: `--collect-only` starts with the marker and executes nothing).
PYTEST_ARGS = {"-q", "-v", "-x", "-p", "no:cacheprovider", "--noconftest", "-rA", "-ra"}
DEFAULT_TYPES = {"opened", "synchronize", "reopened"}   # GitHub's default activity types for pull_request events


def invokes(statement: str, command: str) -> bool:
    """The statement invokes the contract command: it starts with it, and a pytest command
    carries only arguments that still run the tests."""
    if not statement.startswith(command):
        return False
    if command.startswith("python3 -m pytest"):
        tail = re.sub(r"\s\d*[<>]&?\S*", "", statement[len(command):])   # redirections do not change what runs
        return set(tail.split()) <= PYTEST_ARGS
    return True


def trigger_filters(body: str, event: str) -> list[str]:
    """The `paths`, `paths-ignore`, `branches` or `branches-ignore` filters declared under
    `on: <event>:` (solyra#72 r4121753959: a filter keeps the workflow from starting at all)."""
    lines, found = body.splitlines(), []
    for i, line in enumerate(lines):
        if not re.match(r"^(on|True|true):\s*$", line):
            continue
        for j in range(i + 1, block_end(lines, i, 0)):
            if re.match(rf"^\s+{re.escape(event)}:\s*$", lines[j]):
                level = indent(lines[j])
                for k in range(j + 1, block_end(lines, j, level)):
                    if (m := re.match(r"^\s+['\"]?(paths|paths-ignore|branches|branches-ignore|tags|tags-ignore)['\"]?:", lines[k])) and indent(lines[k]) == level + 2:
                        found.append(m.group(1))
    return found


def valid_yaml(text: str) -> str | None:
    """Why the text is not YAML, or None. PyYAML is required to judge a workflow change
    (solyra#72 r4121753972: a head that GitHub cannot load must not merge)."""
    try:
        import yaml
    except ImportError:
        return "PyYAML is not installed, so the workflow cannot be parsed; pip install pyyaml"

    class Strict(yaml.SafeLoader):
        """Duplicate keys are an error, as GitHub treats them (stocks#1205 r4121888782)."""

        def construct_mapping(self, node, deep=False):
            seen = set()
            for key_node, _ in node.value:
                key = self.construct_object(key_node, deep=deep)
                if key in seen:
                    raise yaml.YAMLError(f"duplicate key {key!r} at line {key_node.start_mark.line + 1}")
                seen.add(key)
            return super().construct_mapping(node, deep)

    try:
        loaded = yaml.load(text, Loader=Strict)
    except yaml.YAMLError as exc:
        return f"is not valid YAML ({str(exc).splitlines()[0]})"
    if not isinstance(loaded, dict):
        return "is not a YAML mapping"
    # The gate reads the file line by line; YAML written any other way than plain block keys
    # would be read one way by GitHub and another here (stocks#1205 r4121888791, r4121888805)
    stripped = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    if (m := re.search(r"^\s*(-\s+)?['\"][^'\"]*['\"]\s*:", stripped, re.M)):
        return f"quotes a mapping key ({m.group(0).strip()}); the gate's workflows use plain keys"
    if (m := re.search(r"(^|[\s:])[&*][A-Za-z_]|^\s*<<\s*:|(^|\s)!\w", stripped, re.M)):
        return f"uses a YAML anchor, alias, merge key or tag ({m.group(0).strip()}); the gate's workflows use none"
    if "\t" in stripped or "\r" in text:
        return "contains a tab or a carriage return; the gate's workflows use spaces and LF line endings"
    if where := continued_plain_scalar(stripped):
        # red-team round four: a plain scalar continued on a deeper line folds to one value for GitHub
        # (`run: cmd\n  || true`, `ref:\n  <head sha>`, `shell:\n  true {0}`) while the gate read line one
        return f"continues a plain scalar onto the next line ({where}); the gate's workflows keep each value on its line or in a `|` block"
    if (m := re.search(r"^\s*(-\s+)?[\w.-]+:[ \t]+#", stripped, re.M)):
        # round six: `permissions: # note` read as an inline value, so the block below it was never read
        return f"puts a comment where a value goes ({m.group(0).strip()}); the gate's workflows write the value or nothing"
    if (m := re.search(r"^\s*(-\s+)?\?(\s|$)|^\s*:(\s|$)", stripped, re.M)):
        return "uses YAML's explicit-key syntax (`? key`); the gate's workflows write `key:`"
    if re.search(r"^(True|true|On|ON):", stripped, re.M):
        return "spells the trigger key as a boolean; the gate's workflows write `on:`"
    if (m := re.search("[\u2028\u2029\x85\x0b\x0c\x1c\x1d\x1e\u200b-\u200f\u00ad\ufeff\u2060-\u2064\u202a-\u202e\u2066-\u2069]", text)):
        return f"carries U+{ord(m.group(0)):04X}, a line break or invisible character YAML parsers disagree on"
    if (m := re.search(r"^\s*(-\s+)?[\w.-]+[ \t]+:(\s|$)", stripped, re.M)):
        # round five: `run :` is the key `run` to YAML and no key at all to the line readers
        return f"puts whitespace before a key's colon ({m.group(0).strip()}); the gate's workflows write `key:`"
    if (m := re.search(r"""^\s*(-\s+)?[\w.-]+:\s+(?:'(?:[^']|'')*$|"(?:[^"\\]|\\.)*$)""", stripped, re.M)):
        # round five: a quoted scalar that runs on to later lines folds for YAML while the readers keep line one
        return f"opens a quoted value it does not close on the line ({m.group(0).strip()[:40]}); the gate's workflows keep each value on its line"
    lines = split_lines(stripped)
    for i, ln in enumerate(lines):
        if re.match(r"^defaults:\s*$", ln) and any(re.match(r"^\s+working-directory:", lines[k]) for k in range(i + 1, block_end(lines, i, 0))):
            # (round four: the job-level form was refused, the workflow-level one was not read)
            return "sets `working-directory` under a top-level `defaults:`; the gate's workflows run every step from the workspace root"
    return None


def continued_plain_scalar(text: str) -> str | None:
    """The first `key: value` whose plain value continues on a deeper-indented line."""
    lines = split_lines(text)
    is_entry = lambda ln: bool(re.match(r"^(-(\s+|$)|['\"]?[\w.-]+['\"]?\s*:(\s|$))", ln.strip()))
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)(-\s+)?['\"]?[\w.-]+['\"]?:\s*(.*)$", line)
        if not m:
            continue
        value = m.group(3).strip()
        if value and value[0] in "|>{[&*!'\"":
            continue   # a block scalar, a flow collection or a quoted value: read whole by both sides
        # (an empty value followed by a deeper non-entry line is a scalar that starts on the next line)
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines) and indent(lines[j]) > len(m.group(1)) + len(m.group(2) or "") and not is_entry(lines[j]):
            return f"`{line.strip()[:40]}` runs on to line {j + 1}"
    return None


def workflow_trigger_types(body: str, event: str) -> set[str]:
    """The activity types declared under `on: <event>:` (`types: [...]` inline or as a list),
    or GitHub's defaults when the event declares none."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if not re.match(r"^(on|True|true):\s*$", line):
            continue
        for j in range(i + 1, block_end(lines, i, 0)):
            if re.match(rf"^\s+{re.escape(event)}:\s*$", lines[j]):
                level = indent(lines[j])
                for k in range(j + 1, block_end(lines, j, level)):
                    if (m := re.match(r"^\s+types:\s*(.*)$", lines[k])):
                        value = re.sub(r"\s+#.*$", "", m.group(1)).strip()
                        if value:
                            return set(re.findall(r"[a-z_]+", value))
                        return {t for l in lines[k + 1:block_end(lines, k, indent(lines[k]))]
                                for t in re.findall(r"^\s*-\s*([a-z_]+)", l)}
                return set(DEFAULT_TYPES)
        return set(DEFAULT_TYPES)
    return set(DEFAULT_TYPES)


def job_of(jobs: list[dict], command: str) -> tuple[int, int]:
    """(job index, statement index) of the first statement invoking `command`, or (-1, -1)."""
    for j, job in enumerate(jobs):
        for k, st in enumerate(job["statements"]):
            if invokes(st, command):
                return j, k
    return -1, -1


def needs_transitively(jobs: list[dict], later: int, earlier: int) -> bool:
    seen, frontier = set(), {jobs[later]["name"]}
    while frontier:
        name = frontier.pop()
        if name == jobs[earlier]["name"]:
            return True
        if name in seen:
            continue
        seen.add(name)
        frontier |= next((j["needs"] for j in jobs if j["name"] == name), set())
    return False


def checkout_violation(body: str, side: str) -> str | None:
    """A checkout the contract forbids: for a head-run workflow, a ref that is not the PR head;
    for a base-run one, any ref naming the PR head (solyra#72 r4120071803)."""
    # round six: `github-server-url:` sends the token elsewhere; a checkout takes only the keys the contract knows
    for m in re.finditer(r"^\s*(-\s+)?uses:\s*['\"]?actions/checkout@", body, re.M):
        lines = body[m.start():].split("\n")
        for ln in lines[1:]:
            if not ln.strip() or re.match(r"^\s*-\s", ln) or indent(ln) < indent(lines[0].replace("- ", "  ", 1)):
                break   # the next step, or the end of this one
            if (km := re.match(r"^\s+([\w-]+):", ln)) and km.group(1) not in ("with", "ref", "fetch-depth", "persist-credentials", "repository", "name", "id"):
                return f"checkout step sets `{km.group(1)}`; the gate's checkouts set ref, fetch-depth and persist-credentials only"
    # stocks#1205 r4121602804: a `repository:` other than the event's runs another tree
    for m in re.finditer(r"^\s*repository:\s*(.*)$", body, re.M):
        if re.sub(r"\s+", "", shell_value(m.group(1))) != "${{github.repository}}":
            return f"checks out repository {shell_value(m.group(1))!r} instead of the event's own"
    for ref in checkout_refs(body):
        if side == "head" and ref and re.sub(r"\s+", "", ref) != "${{github.event.pull_request.head.sha}}":
            return f"checks out {ref!r} instead of the PR head sha"
        if side == "base" and ref and re.sub(r"\s+", "", ref) != "${{github.event.pull_request.base.sha}}":
            # solyra#72 r4120167273: the merge ref and merge_commit_sha carry the PR's code too
            return f"checks out {ref!r} instead of the event's base sha under pull_request_target"
    return None


EXECUTABLES = r"(python3?|python3\.\d+|git|pytest)"
SHADOW = re.compile(r"(?:^|[;&|{}(]\s*|\bfunction\s+)" + EXECUTABLES + r"\s*\(\s*\)|\bfunction\s+" + EXECUTABLES
                    + r"\b|\balias\s+" + EXECUTABLES + r"=|\bhash\s+-p\s+\S+\s+" + EXECUTABLES + r"\b", re.M)


# Every line the hook may contain, after its interpreter line: comments, `set -e`, the Python
# version check, the unstaged-gate check, their diagnostics, and the gate call.
HOOK_LINES = (
    r"#.*", r"set -e(u|o pipefail|uo pipefail)?",
    r"if ! python3 -c 'import sys; sys\.exit\(0 if sys\.version_info >= \(3, 11\) else 1\)' 2>/dev/null; then",
    r"if ! git diff --quiet -- scripts/gate/spec_gate\.py; then",
    r"echo \"spec gate: [^\"`$]*(\$\(python3 --version 2>&1 \|\| echo none\))?[^\"`$]*\" >&2",
    r"exit 1", r"fi",
    r"python3 \"\$\(git rev-parse --show-toplevel\)/scripts/gate/spec_gate\.py\" --commit",
    r"python3 (\./)?scripts/gate/spec_gate\.py --commit",
)
# (round five: bash reads `scripts//gate` and `scripts/./gate` as `scripts/gate`)
GATE_PATHS = r"(scripts/+(?:\./+)*gate\b|tests/+(?:\./+)*scripts\b|\.githooks\b|\.github/+(?:\./+)*workflows\b)"
# red-team round three: `rsync` copies without a redirect; `pip install --target` writes a directory
WRITERS = r"(cp|mv|install|ln|tee|rm|truncate|chmod|patch|dd|rsync|curl|wget|sed|perl|pip3?|python3?\s+-m\s+pip|git\s+(checkout|restore|apply|reset|clean|stash))"
# stocks#1205 r4122021088: `gate=scripts/gate/spec_gate.py` then `> "$gate"` is the same write; a
# destination held in a variable is refused unless it is under the runner's temp directory
# (red-team round three: `${RUNNER_TEMP}/../..` climbs out of it, so a temp path holding `/..` is not excused)
INDIRECT = r"['\"]?\$(?!(RUNNER_TEMP\b|\{RUNNER_TEMP\}|\{\{\s*runner\.temp\s*\}\})(?![^\s'\"]*/\.\.))"
# and a file named like a contract executable anywhere (`ln -s /bin/true /usr/local/bin/python3` shadows the
# interpreter ahead of /usr/bin on the runner's PATH: red-team round two)
EXECUTABLE_NAME = r"[^\s'\"]*/(python3?|python3\.\d+|git|pytest)\b"
# red-team round four: the writer sits anywhere on the line (`command cp`, `timeout 5 cp`, `find -exec cp`,
# `echo a b | xargs cp`, `((1)) && cp`), not only at its start after assignments
WRITES_GATE = re.compile(r"(?m)(?<![\w/.-])" + WRITERS + r"\b[^\n]*(" + GATE_PATHS + "|" + INDIRECT + "|" + EXECUTABLE_NAME + r")|[>]{1,2}\|?\s*(['\"]?[^\s'\"]*" + GATE_PATHS + "|" + INDIRECT + "|['\"]?" + EXECUTABLE_NAME + ")")


# Commands that only read what they are given: any other command handed a gate path may write it
# (round six: `ed`, `sponge`, `sort -o` were not on the writer list; the durable shape is an allow-list)
READ_ONLY = frozenset(("python3", "python", "git", "cat", "ls", "test", "[", "[[", "echo", "printf", "diff", "cmp", "sha256sum",
                       "sha1sum", "md5sum", "head", "tail", "wc", "grep", "stat", "file", "readlink", "realpath", "true", ":",
                       "for", "do", "done", "if", "then", "else", "elif", "fi", "while", "case", "esac", "!", "in"))


def writes_gate_file(runs: str) -> str | None:
    """The first executed run line that copies, moves, edits, deletes or redirects into a gate
    file's path (stocks#1205 r4121777299), or hands one to a command that is not known to only read."""
    m = WRITES_GATE.search(runs)
    if m:
        return runs[runs.rfind("\n", 0, m.start()) + 1:].split("\n")[0].strip()
    for line in runs.split("\n"):
        if re.search(GATE_PATHS, line):
            for stmt in re.split(r"\s*(?:;|&&|\|\||\|)\s*", line.strip()):
                stmt = re.sub(r"^((command|builtin|env|time|nice|nohup|sudo|timeout|exec)\s+(-\S+\s+|[A-Za-z_]\w*=\S*\s+)*)+|^[A-Za-z_]\w*=\$\(", "", stmt)
                stmt = re.sub(r"^([A-Za-z_]\w*=\S*\s+)+", "", stmt)
                if re.search(GATE_PATHS, stmt) and stmt.split() and stmt.split()[0] not in READ_ONLY and not re.match(r"^[A-Za-z_]\w*=", stmt):
                    return line.strip()
    return None


def shadowed_executable(text: str) -> str | None:
    """The first contract executable a comment-stripped text redefines as a function or alias."""
    m = SHADOW.search(text)
    return next((g for g in m.groups() if g), None) if m else None


def top_permissions(body: str) -> dict[str, str]:
    """The top-level `permissions:` mapping of a comment-stripped workflow, block or flow form,
    as {scope: level}; {} when the workflow declares none."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^['\"]?permissions['\"]?:\s*(.*)$", line)
        if not m:
            continue
        value = shell_value(m.group(1))
        if value.startswith("{"):
            j = i
            while "}" not in value and j + 1 < len(lines):
                j += 1
                value += " " + lines[j].strip()
            return dict(re.findall(r"([\w-]+)\s*:\s*['\"]?([\w-]+)", value))
        if value:
            return {"*": value}   # read-all / write-all
        return {km.group(1): shell_value(km.group(2)) for j in range(i + 1, block_end(lines, i, 0))
                if (km := re.match(r"^\s+['\"]?([\w-]+)['\"]?:\s*(.*)$", lines[j]))}
    return {}


def workflow_write_grant(body: str) -> str | None:
    """The first line of a comment-stripped workflow that grants a write permission, at any
    level: a job-level `permissions:` overrides the read-only top-level block a contract
    marker sees (solyra#72 r4119837212)."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^\s*(-\s+)?['\"]?permissions['\"]?:\s*(.*)$", line)   # solyra#72 r4121753989: keys may be quoted
        if not m:
            continue
        value = re.sub(r"\s+#.*$", "", m.group(2)).strip()   # `write-all  # why` is still write-all
        if value.startswith("{") and "}" not in value:
            # solyra#72 r4120337740: `permissions: {` ... `}` over several lines is one flow mapping
            for j in range(i + 1, len(lines)):
                value += " " + re.sub(r"\s+#.*$", "", lines[j]).strip()
                if "}" in lines[j]:
                    break
        if value:
            if value.strip("'\"") == "write-all" or (value.startswith("{") and re.search(r":\s*['\"]?write", value)):
                return line.strip()
            continue
        level = indent(line)
        for j in range(i + 1, block_end(lines, i, level)):
            if re.match(r"^\s*['\"]?[\w-]+['\"]?:\s*['\"]?write['\"]?\s*$", re.sub(r"\s+#.*$", "", lines[j])):   # `contents: write # why`
                return lines[j].strip()
    return None


# The documents the gate reads as policy: deleting one leaves every later change unjudgeable.
POLICY_DOCS = (CATALOG, REQUIREMENTS, TRACEABILITY, CANVASES)
# The capability that owns CI configuration; enforced where the catalog defines it.
WORKFLOW_FEAT = "FEAT-CICD-001"
# The capability that owns the deploy surface (red-team round three); enforced where the catalog defines it.
DEPLOY_FEAT = "FEAT-DEPLOY-001"
DEPLOY_FILE = re.compile(r"^((gcp|platform)/deploy\.sh|gcp/cloudbuild/[^/]+|cloudbuild[^/]*\.ya?ml|Dockerfile[^/]*|\.gcloudignore|\.dockerignore)$")
# The files that are the delivery process itself: CI configuration at any path under .github/, the gate's
# files and pinned copies, the hook, the agent instructions and the local skills (round six)
def is_process_file(path: str) -> bool:
    return ((path.startswith(".github/") and not is_documentation(path)) or is_gate_file(path) or path in PINNED.values()
            or path.startswith(LOCAL_SKILLS) or path.startswith((".claude/", ".githooks/"))
            or path.rsplit("/", 1)[-1] in ("CLAUDE.md", "AGENTS.md", "CLAUDE.local.md"))
# The files the gate runs from: no change may delete one, whatever its branch, or the
# base's copy judges the deletion green and every later PR runs without a gate.
SUITE = "tests/scripts/test_spec_gate.py"
# stocks#1205 r4121602817: the exporter's suite judges proposed exporters the same way
SUITES = (SUITE, "tests/scripts/test_export_model_registry.py")
# Red-team round five: after five rounds the shell and YAML models still leaked (`if: always()`
# steps hidden from the write scan, `run :`, `|2`, quoted continuations, git subcommands, `scripts//gate`).
# The workflows and the hook are therefore pinned byte for byte to copies under scripts/gate/pinned/,
# read from the BASE: a change to one of these files must equal the copy already on main. Changing
# the copy is its own reviewed PR (step one), the file follows in the next (step two); one PR
# changing both is refused, because the base's copy is what the head is measured against. The
# models below stay as a second line.
PINNED = {
    ".github/workflows/spec-gate.yml": "scripts/gate/pinned/spec-gate.yml",
    ".github/workflows/registry-check.yml": "scripts/gate/pinned/registry-check.yml",
    ".githooks/pre-commit": "scripts/gate/pinned/pre-commit",
}
GATE_ENTRYPOINTS = (
    "scripts/gate/spec_gate.py",
    HOOK,
    ".github/workflows/spec-gate.yml",
    ".github/workflows/registry-check.yml",
    SUITE,   # the suite CI runs on a proposed gate
    "scripts/gate/export_model_registry.py", "tests/scripts/test_export_model_registry.py",   # where they exist (round five)
    *PINNED.values(),   # the pinned copies: without one, the file it pins is judged by the models alone
)
# The manifest fields a chore/ branch may change. Anything else in package.json or
# pyproject.toml (scripts, build config, tool tables) is executable configuration that
# CI runs from the checkout, so it is a CHANGE.
NPM_DEPENDENCY_KEYS = frozenset((
    "dependencies", "devDependencies", "peerDependencies", "peerDependenciesMeta",
    "optionalDependencies", "bundledDependencies", "bundleDependencies", "overrides",
    "resolutions",
))
PYPROJECT_DEPENDENCY_PATHS = (
    ("project", "dependencies"), ("project", "optional-dependencies"), ("dependency-groups",),
    ("build-system", "requires"), ("tool", "poetry", "dependencies"), ("tool", "poetry", "group"),
    ("tool", "uv", "sources"), ("tool", "uv", "dev-dependencies"),
)
CANVAS_MARKERS = {"refresh": "Canvas refresh pending:", "report-only": "Canvas check pending (report-only):"}
# A ticked done_when line that defers the work is not done (CLAUDE.md rule 0 names these phrases).
DEFERRAL = re.compile(
    r"\b(future[- ]work|follow[- ]?up|non[- ]?blocking|for now|deferred|later PR|next PR|separate PR|TODO|TBD"
    r"|not (?:yet )?(?:run|done|implemented|verified|tested|complete|completed|finished|started|applied|merged|shipped)"
    r"|unfinished|incomplete|untested|unverified|outstanding|pending|skipped|still open|to be done"
    # red-team round three: ordinary deferral phrasing the list missed
    r"|postpone\w*|parked|park it|out of scope|descope\w*|tracked in|will be (?:addressed|done|fixed|added|run)"
    r"|after (?:the )?merge|phase \d|not in this PR|next (?:sprint|release|iteration)|to follow|later (?:change|release)|punt\w*"
    r"|follow[- ]?ups|defer\w*|backlog|(?:future|another|subsequent|follow[- ]on) PR)\b", re.I)
# Changing these is changing a workload; the PR body must then carry the rule 0 capacity numbers.
WORKLOAD_PREFIXES = ("gcp/", ".github/workflows/")
CAPACITY_LABELS = ("Volume", "Velocity", "Wall-clock", "30")
REQUIRED_SPEC_KEYS = ("feat_id", "req_ids", "done_when", "status")
REQUIRED_PLAN_KEYS = ("feat_id", "spec", "branch", "status")
SPEC_STATUSES = ("draft", "approved", "superseded")
PLAN_STATUSES = ("ready", "done")
WORKTREE = "worktree"


class GitFailed(Exception):
    """A git command the gate depends on failed. Never treated as an empty result."""


def git(*args: str) -> subprocess.CompletedProcess:
    # utf-8 regardless of locale: the specs carry curly quotes and emoji, and cp1252
    # (Windows) would raise on them and block every commit.
    # core.quotePath=false: a path with a non-ASCII byte is otherwise returned quoted and escaped, and
    # `"docs/r\303\251sum\303\251.md"` does not start with docs/ (red-team, this PR)
    return subprocess.run(["git", "-c", "core.quotePath=false", *args], capture_output=True, encoding="utf-8", errors="replace", cwd=ROOT)


def git_out(*args: str) -> str:
    """stdout of a git command that must succeed: a failed diff or listing is not an empty one."""
    r = git(*args)
    if r.returncode != 0:
        raise GitFailed(f"git {' '.join(args[:2])} failed ({r.returncode}): {r.stderr.strip() or 'no output'}; "
                        "refusing to pass on a diff the gate could not compute")
    return r.stdout


def catalog_ids(text: str | None) -> set[str]:
    """FEAT-IDs from the first cell of the catalog's table rows. A FEAT-ID mentioned
    anywhere else (prose, a link, a comment) is not a catalog entry."""
    return set(FEAT_ROW.findall(visible(text or "")))


LICENSE_FILE = re.compile(r"^(LICENSE|LICENCE|COPYING)(-[A-Za-z0-9]+)*(\.(md|txt|rst))?$")
WORKFLOWS = ".github/workflows/"


# Under docs/ these are code or archives an installer or a browser would run, not prose (red-team round four:
# `docs/pkg/setup.py` reached `pip install -r` through a requirements path line)
NOT_PROSE = re.compile(r"\.(py|pyc|pyw|sh|bash|zsh|ps1|bat|cmd|js|mjs|cjs|ts|tsx|jsx|html?|xhtml|svg|whl|egg|zip|tar|tgz|tar\.gz|tar\.xz|7z|rar"
                       r"|toml|cfg|ini|rb|pl|php|exe|dll|so|dylib|jar|class|wasm|ipynb)$", re.I)
NOT_PROSE_NAMES = frozenset(("setup.py", "setup.cfg", "pyproject.toml", "conftest.py", "package.json", "Makefile", "makefile", "Dockerfile"))
AGENT_DIRS = frozenset((".claude", ".codex", ".cursor", ".windsurf", ".aider", ".gemini", ".kiro", ".roo", ".clinerules", ".junie", ".trae", ".continue"))
AGENT_FILES = frozenset(("AGENTS.md", "CLAUDE.md", "CLAUDE.local.md", "GEMINI.md", "copilot-instructions.md", ".cursorrules", ".clinerules", ".windsurfrules"))


def is_documentation(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    parts = path.split("/")
    if path.startswith(".github/") and (not name.endswith(".md") or parts[1] in ("prompts", "instructions", "agents", "ISSUE_TEMPLATE")
                                        or name.lower() == "pull_request_template.md"):
        # a workflow is executable configuration whatever its name, and so is a prompt a workflow
        # feeds to a model (red-team round three: .github/prompts/), an instruction file an agent loads,
        # or the template that seeds every PR body the gate reads; a README there is prose
        return False
    if any(d in AGENT_DIRS for d in parts[:-1]) or name in AGENT_FILES:   # at any depth: agents load them all
        return False   # skills, agents and the root instructions are the process agents execute, not its description
    if NOT_PROSE.search(name) or name in NOT_PROSE_NAMES:
        return False
    return path.startswith("docs/") or path.endswith((".md", ".drawio")) or bool(LICENSE_FILE.match(name))


class Tree:
    """One revision's files: the index (rev None), the working tree, or a commit."""

    def __init__(self, rev: str | None):
        self.rev = rev

    def read(self, path: str) -> str | None:
        if self.rev == WORKTREE:
            p = ROOT / path
            return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
        r = git("show", f":{path}" if self.rev is None else f"{self.rev}:{path}")
        return r.stdout if r.returncode == 0 else None

    def raw(self, path: str) -> bytes | None:
        """The file's bytes, untranslated (round six: text mode folds CRLF, so the pin compares bytes)."""
        if self.rev == WORKTREE:
            p = ROOT / path
            return p.read_bytes() if p.is_file() else None
        r = subprocess.run(["git", "-c", "core.quotePath=false", "show", f":{path}" if self.rev is None else f"{self.rev}:{path}"],
                           capture_output=True, cwd=ROOT)
        return r.stdout if r.returncode == 0 else None

    def mode(self, path: str) -> str | None:
        """The file's git mode ("100755" for an executable) at this revision or in the index."""
        if self.rev == WORKTREE:
            p = ROOT / path
            return None if not p.is_file() else ("100755" if p.stat().st_mode & 0o111 else "100644")
        r = git("ls-files", "-s", "--", path) if self.rev is None else git("ls-tree", self.rev, "--", path)
        return r.stdout.split()[0] if r.returncode == 0 and r.stdout.strip() else None

    def list(self, folder: str) -> list[str]:
        if self.rev == WORKTREE:
            base = ROOT / folder
            found = [str(p.relative_to(ROOT)) for p in base.glob("*.md")] if base.is_dir() else []
        elif self.rev is None:
            found = git_out("ls-files", "--", folder).splitlines()
        else:
            r = git("ls-tree", "-r", "--name-only", self.rev, "--", folder)
            found = r.stdout.splitlines() if r.returncode == 0 else []   # a rev without the folder
        return sorted(p for p in found if p.endswith(".md"))


def frontmatter(text: str | None) -> dict:
    """Minimal YAML frontmatter reader: top-level `key: value` and `key:` + `  - item` lists."""
    if not text:
        return {}
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    fm: dict = {}
    current = None
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        if line.startswith("\t"):
            # round five: YAML refuses a tab-indented line; reading past it would read a document YAML does not
            fm["_tab_indented"] = True
            continue
        if line.startswith((" ", "\t")):
            item = line.strip()
            if item.startswith("- ") and current:
                fm.setdefault(current, [])
                if isinstance(fm[current], list):
                    fm[current].append(item[2:].strip().strip('"'))
            elif current and isinstance(fm.get(current), list) and fm[current]:
                # red-team round four: a list item continued on a deeper line is one value for YAML
                fm[current][-1] = (fm[current][-1] + " " + item.strip('"')).strip()
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if k in fm:   # red-team, this PR: `status: draft` then `status: approved` read as approved
                fm.setdefault("_duplicate_keys", []).append(k) if isinstance(fm.get("_duplicate_keys"), list) else fm.__setitem__("_duplicate_keys", [k])
            current = k
            if v == "":
                fm[k] = []
            elif v in ("null", "~"):
                fm[k] = None
            elif v.startswith("[") and v.endswith("]"):
                fm[k] = [x.strip().strip('"') for x in re.split(r",(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", v[1:-1]) if x.strip()]   # commas inside quotes stay (round five)
            else:
                fm[k] = v.strip('"')
    return fm


def requirement_definitions(text: str) -> set[str]:
    """The REQ-IDs a requirements registry defines as rendered: not in a fence, an indented
    block or inline code (solyra#72 r4121100680: `` `**REQ-X-001:**` `` is an example, not
    a definition)."""
    return set(REQ_DEFINITION.findall(re.sub(r"`[^`\n]*`", "", visible(text))))


def requirement_defs(tree: "Tree") -> set[str] | None:
    """The REQ-IDs the requirements registry defines; None where the repository has
    no registry (solyra), so req_ids are checked for shape only. A registry that
    exists but defines nothing fails closed rather than passing every ID."""
    text = tree.read(REQUIREMENTS)
    return None if text is None else requirement_definitions(text)


def validate_spec(fm: dict, name: str, catalog: set[str], req_defs: set[str] | None) -> list[str]:
    errs = [f"{name}: missing frontmatter key '{k}'" for k in REQUIRED_SPEC_KEYS if k not in fm]
    if fm.get("_duplicate_keys"):
        errs.append(f"{name}: frontmatter defines {', '.join(fm['_duplicate_keys'])} more than once; one value per key")
    if "feat_id" in fm and not isinstance(fm["feat_id"], str):
        errs.append(f"{name}: feat_id must be one FEAT-ID, not a list")
    elif "feat_id" in fm and fm["feat_id"] not in catalog:
        errs.append(f"{name}: feat_id {fm['feat_id']!r} is not in {CATALOG}")
    if fm.get("status") not in SPEC_STATUSES:
        errs.append(f"{name}: status must be draft | approved | superseded")
    done = fm.get("done_when")
    if "done_when" in fm and (not isinstance(done, list) or not done or not all(str(x).strip() for x in done)):
        errs.append(f"{name}: done_when must be a non-empty list of non-empty items; "
                    "a spec without verifiable done_when items cannot be closed")
    reqs = fm.get("req_ids")
    if "req_ids" in fm:
        if not isinstance(reqs, list) or not reqs:
            errs.append(f"{name}: req_ids must be a non-empty list of REQ-IDs")
        else:
            bad = [r for r in reqs if not REQ_SHAPE.match(r)]
            unknown = [r for r in reqs if REQ_SHAPE.match(r) and req_defs is not None and r not in req_defs]
            if bad:
                errs.append(f"{name}: req_ids not shaped REQ-XXX-000: {', '.join(bad)}")
            if req_defs is not None and not req_defs:
                errs.append(f"{name}: {REQUIREMENTS} defines no REQ-IDs (**REQ-XXX-000:** lines), "
                            "so req_ids cannot be checked; restore the registry")
            elif unknown:
                errs.append(f"{name}: req_ids not defined in {REQUIREMENTS}: {', '.join(unknown)}")
    for key in ("issues", "canvases"):
        if key in fm and fm[key] is not None and not isinstance(fm[key], list):
            errs.append(f"{name}: {key} must be a list")
    return errs


def check_supersedes(fm: dict, name: str, base: "Tree") -> list[str]:
    """`supersedes` is null or a spec on the base for the same FEAT (stocks#1205 r4121777354:
    a typo there leaves the old spec live and the lineage dangling)."""
    target = fm.get("supersedes")
    if target is None:
        return []
    if not isinstance(target, str) or target != posixpath.normpath(target) or not target.startswith(SPECS + "/") or (old := base.read(target)) is None:
        # (red-team, this PR: `./docs/...` resolves for git but never equals the path the plans and the
        # supersession scan compare as strings)
        return [f"{name}: supersedes {target!r}, which is not a spec on the base written as {SPECS}/<file>.md; "
                "name the spec it replaces or leave it null"]
    if frontmatter(old).get("feat_id") != fm.get("feat_id"):
        return [f"{name}: supersedes {target}, a spec for {frontmatter(old).get('feat_id')}, not {fm.get('feat_id')}"]
    return []


def plan_stays_bound(name: str, fm: dict, base_fm: dict, branch: str) -> list[str]:
    """A plan already on the base binds one branch and one PR for good: a change cannot
    re-point it at its own branch, swap its PR number, or reopen it once it is done."""
    if not base_fm:
        return []
    errs = []
    if base_fm.get("branch") != branch:
        errs.append(f"{name}: names branch '{base_fm.get('branch')}' on the base; a plan binds one branch, "
                    f"so '{branch}' needs its own plan")
    if base_fm.get("pr") is not None and str(fm.get("pr")) != str(base_fm.get("pr")):
        errs.append(f"{name}: records PR #{base_fm.get('pr')} on the base; a plan binds one PR")
    if base_fm.get("spec") is not None and fm.get("spec") != base_fm.get("spec"):
        # round five: re-pointing the plan at a weaker approved spec of the same FEAT swapped its contract
        errs.append(f"{name}: names spec {base_fm.get('spec')} on the base; a plan binds one spec")
    if base_fm.get("status") == "done":
        errs.append(f"{name}: is status: done on the base (its PR merged); further work needs a new plan")
    return errs


TASK_HEADING = re.compile(r"^#{2,3}\s+Task\b.*$", re.M)


def validate_plan_body(text: str | None, name: str) -> list[str]:
    """A plan has at least one task, and every task cites its spec section and carries a
    checklist item: frontmatter alone authorizes nothing (solyra#72 r4120633514)."""
    body = visible(text or "")
    starts = [m.start() for m in TASK_HEADING.finditer(body)]
    if not starts:
        return [f"{name}: no `## Task N:` section; a plan is its tasks, each citing the spec section it advances"]
    errs: list[str] = []
    for n, start in enumerate(starts):
        task = body[start:starts[n + 1] if n + 1 < len(starts) else len(body)]
        title = task.splitlines()[0].strip()
        if not re.search(r"^\s*Spec:", task, re.M):
            errs.append(f"{name}: {title!r} cites no spec section (a `Spec:` line)")
        if not re.search(r"^\s*[-*]\s+\[[ xX]\]", task, re.M):
            errs.append(f"{name}: {title!r} has no checklist item")
    return errs


def validate_plan(fm: dict, name: str, feat_id: str, tree: Tree) -> list[str]:
    errs = [f"{name}: missing frontmatter key '{k}'" for k in REQUIRED_PLAN_KEYS if k not in fm]
    if fm.get("_duplicate_keys"):
        errs.append(f"{name}: frontmatter defines {', '.join(fm['_duplicate_keys'])} more than once; one value per key")
    if isinstance(fm.get("spec"), str) and (fm["spec"] != posixpath.normpath(fm["spec"]) or not fm["spec"].startswith(SPECS + "/")):
        errs.append(f"{name}: spec {fm['spec']!r} is not a normalized path under {SPECS}/")
    if "feat_id" in fm and fm["feat_id"] != feat_id:
        errs.append(f"{name}: feat_id is {fm['feat_id']!r} but the branch serves {feat_id}")
    status = fm.get("status")
    if status not in PLAN_STATUSES:
        errs.append(f"{name}: status must be ready | done")
    elif status != "ready":
        errs.append(f"{name}: status is '{status}'; a plan authorizes implementation only while "
                    "status: ready (done means its PR merged)")
    pr = fm.get("pr")
    if pr is not None and not PR_REF.match(str(pr)):
        errs.append(f"{name}: pr must be null or a PR number, not '{pr}'")
    spec = fm.get("spec")
    if "spec" in fm and (not isinstance(spec, str) or not spec.strip()):
        errs.append(f"{name}: spec must name the approved spec's path, not '{spec}'")
    elif spec and not (spec.startswith(SPECS + "/") and spec.endswith(".md")):
        errs.append(f"{name}: spec must be a file under {SPECS}/, not {spec}")
    elif spec and tree.read(spec) is None:
        errs.append(f"{name}: spec path does not exist: {spec}")
    return errs


@dataclass
class Change:
    mode: str               # "commit" or "pr"
    branch: str
    changed: list[str]
    tree: Tree
    base: Tree              # policy: the catalog, specs and requirements are read here
    before: Tree            # the files as they were before the change: HEAD, or the merge base
    trusted: bool = True    # False for a PR from a fork: no prefix allowances


@dataclass
class Traced:
    feat_id: str
    spec_path: str
    spec_fm: dict
    plan_path: str
    plan_fm: dict


def _at(d, path: tuple[str, ...]):
    for key in path:
        d = d.get(key) if isinstance(d, dict) else None
    return d


def _without(d: dict, path: tuple[str, ...]) -> dict:
    """`d` with the nested key `path` removed, when present."""
    if len(path) == 1:
        return {k: v for k, v in d.items() if k != path[0]}
    inner = d.get(path[0])
    if not isinstance(inner, dict):
        return d
    return {**d, path[0]: _without(inner, path[1:])}


# A requirements line chore/ may carry: a distribution name, optional extras, a version specifier, an
# environment marker, or a `--hash=` continuation. Anything else (options, URLs, paths, `name @ url`)
# is something pip fetches or executes.
REQUIREMENT_LINE = re.compile(
    r"^([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?(?:\[[A-Za-z0-9._,\s-]*\])?\s*"
    r"(?:(?:===?|~=|!=|<=|>=|<|>)\s*[A-Za-z0-9._*+!-]+(?:\s*,\s*(?:===?|~=|!=|<=|>=|<|>)\s*[A-Za-z0-9._*+!-]+)*)?\s*(?:;[^/@:]*)?"
    r"|--hash=sha(?:256|384|512):[0-9a-fA-F]+)$")
NPM_RANGE = re.compile(r"^(?:(?:\^|~|>=?|<=?|=)?\d[\w.+-]*(?:\s*(?:\|\||-|\s)\s*(?:\^|~|>=?|<=?|=)?\d[\w.+-]*)*|latest|\*|)$")


def dependency_values(path: str, before, after) -> str | None:
    """Why a changed dependency value is more than a version: a URL, a git ref, a path, an alias or a
    source table sends the installer elsewhere (red-team round four)."""
    def leaves(obj, prefix=()):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield from leaves(v, prefix + (str(k),))
        elif isinstance(obj, list):
            for n, v in enumerate(obj):
                yield from leaves(v, prefix + (str(n),))
        else:
            yield prefix, obj
    was = dict(leaves(before))
    for key, value in leaves(after):
        if was.get(key) == value:
            continue
        shown = "/".join(key)
        if path.endswith("package.json"):
            if not isinstance(value, str) or not NPM_RANGE.match(value.strip()):
                return f"{path}: {shown} is {value!r}, not a version range; a chore/ branch pins versions and nothing else"
        else:
            if isinstance(value, str) and (re.search(r"\s@\s|@\s*(https?|file|git)|://|file:|git\+", value) or value.strip().startswith(("-", ".", "/"))):
                return f"{path}: {shown} is {value!r}, a URL, path or git reference; a chore/ branch pins versions and nothing else"
            if key[-1] in ("git", "url", "path", "index", "rev", "branch", "tag", "subdirectory", "develop"):
                return f"{path}: {shown} names a source; a chore/ branch pins versions and nothing else"
    return None


def non_dependency_edit(path: str, before: str | None, after: str | None) -> str | None:
    """Why this manifest edit is more than a dependency update, or None when it is not.
    Lockfiles and requirements files hold nothing but dependencies; package.json and
    pyproject.toml also carry scripts and tool configuration, which CI executes."""
    name = path.rsplit("/", 1)[-1]
    if name in ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "bun.lock"):
        if after is None:
            return None   # removing a lockfile installs nothing
        if why := lockfile_offence(name, after):
            return f"{path}: {why}"
        return None
    if re.match(r"requirements[^/]*\.(txt|lock)$", name):
        # red-team round three: a requirements file is executed by `pip install -r`, so an option line
        # (`--index-url`, `-e git+…`, `-r other`), a URL or a path is code CI runs, not a version bump
        if before is None:
            return f"{path}: a new requirements file is a new install surface, not a dependency update"
        if after is None:
            return f"{path}: removing a requirements file is not a dependency update"
        for ln in split_lines(after):
            ln = ln.split("#", 1)[0].strip().rstrip("\\").strip()
            if ln and not REQUIREMENT_LINE.match(ln):
                # (round four: a bare path such as `docs/pkg` or a wheel name is an install target too)
                return f"{path}: carries {ln[:60]!r}, an option, URL or path line; a chore/ branch pins versions and nothing else"
        return None
    if name not in ("package.json", "pyproject.toml"):
        return None
    if before is None:
        return f"{path}: a new manifest is a new project, not a dependency update"
    if after is None:
        return f"{path}: removing the manifest is not a dependency update"
    try:
        if name == "package.json":
            b, a = json.loads(before), json.loads(after)
            if not isinstance(b, dict) or not isinstance(a, dict):
                return f"{path}: is not a JSON object on both sides; that is not a dependency update"
            if bad := dependency_values(path, {k: v for k, v in b.items() if k in NPM_DEPENDENCY_KEYS},
                                        {k: v for k, v in a.items() if k in NPM_DEPENDENCY_KEYS}):
                return bad
            b = {k: v for k, v in b.items() if k not in NPM_DEPENDENCY_KEYS}
            a = {k: v for k, v in a.items() if k not in NPM_DEPENDENCY_KEYS}
        else:
            b, a = tomllib.loads(before), tomllib.loads(after)
            kept_b, kept_a = {}, {}
            for dep_path in PYPROJECT_DEPENDENCY_PATHS:
                kept_b[dep_path] = _at(b, dep_path)
                kept_a[dep_path] = _at(a, dep_path)
                b, a = _without(b, dep_path), _without(a, dep_path)
            if bad := dependency_values(path, kept_b, kept_a):
                return bad
    except (ValueError, tomllib.TOMLDecodeError) as e:
        return f"{path}: cannot be parsed ({e}); the gate does not guess what changed"
    changed = sorted(k for k in set(b) | set(a) if b.get(k) != a.get(k))
    if changed:
        return f"{path}: changes {', '.join(changed)}, not only dependencies; a scripts or config edit is a CHANGE"
    return None


def is_gate_file(path: str) -> bool:
    """A directory entry in GATE_FILES covers its contents; a file entry is that file
    exactly, so `.github/workflows/spec-gate.yml-else.yaml` is not the gate's workflow."""
    return any(path.startswith(g) if g.endswith("/") else path == g for g in GATE_FILES)


def chore_allows(path: str, ch: "Change") -> str | None:
    """None when chore/ may carry this file; otherwise why not ("" when it is simply not a
    manifest or gate file, a reason naming the file when it is a manifest edited beyond
    its dependency fields)."""
    if path.startswith("scripts/gate/") and path not in GATE_SCRIPTS and path not in PINNED.values() and ch.tree.read(path) is not None:
        # stocks#1205 r4121413687: a third module there (`subprocess.py`) would shadow an import of
        # the scripts that run from that directory, and the base's suite tests only the two it copies
        return f"{path}: scripts/gate/ holds {' and '.join(GATE_SCRIPTS)} and nothing else; a module beside them would shadow an import of the gate"
    if is_gate_file(path):
        return None
    if path == REGISTRY_DOCS[1] and "scripts/gate/export_model_registry.py" in ch.changed:
        return None   # the exporter's own output: a changed exporter regenerates it in the same change
    if not MANIFEST.search(path):
        return ""
    # Against the merge base, not the current base: a scripts edit main made after the
    # fork is main's, not this PR's, and must not fail an otherwise permitted bump.
    return non_dependency_edit(path, ch.before.read(path), ch.tree.read(path))


# Skills this repository owns: the weekly vendored-skills update never touches them.
LOCAL_SKILLS = (".claude/skills/product-delivery/", ".claude/skills/refresh-canvas/")

def shadows_local_skill(path: str, ch: "Change") -> bool:
    """A vendored skill directory or frontmatter name that reads as one of the local skills (round six)."""
    local = tuple(d.rstrip("/").rsplit("/", 1)[-1] for d in LOCAL_SKILLS)
    parts = path.lower().split("/")
    if any(part.startswith(local) for part in parts[2:-1]):
        return True
    text = ch.tree.read(path) or ""
    return path.endswith("SKILL.md") and any(re.search(rf"(?m)^name:\s*['\"]?{re.escape(n)}['\"]?\s*$", text, re.I) for n in local)


ALLOWANCES = (
    ("chore/", chore_allows),
    ("bot/superpowers-", lambda p, ch: None if p.startswith(".claude/skills/") and not p.startswith(LOCAL_SKILLS)
     and not shadows_local_skill(p, ch) else ""),
)


def summarize(paths: list[str]) -> str:
    shown = ", ".join(paths[:3])
    return shown + (f" and {len(paths) - 3} more" if len(paths) > 3 else "")


def check_changed_specs(ch: Change) -> list[str]:
    """validate_spec over every spec the change adds or edits, read at the head."""
    errs: list[str] = []
    catalog, req_defs = None, None
    for path in ch.changed:
        if not (path.startswith(SPECS + "/") and path.endswith(".md")):
            continue
        text = ch.tree.read(path)
        if text is None:
            status = frontmatter(ch.base.read(path)).get("status")
            if status == "approved":
                errs.append(f"{path}: an approved spec is not deleted; supersede it with a new spec and mark this one "
                            "superseded, so the plans that cite it keep a contract to point at")
            elif status == "superseded":
                # stocks#1205 r4119634437: a superseded spec is the record the done plans and the
                # replacing spec's `supersedes` point at; deleting it breaks that history.
                errs.append(f"{path}: a superseded spec is not deleted; it is the contract the plans that cite it "
                            "and the spec that replaced it still point at")
            continue
        if catalog is None:
            catalog, req_defs = catalog_ids(ch.base.read(CATALOG)), requirement_defs(ch.base)
        errs += validate_spec(frontmatter(text), path, catalog, req_defs) + check_supersedes(frontmatter(text), path, ch.base)
        # solyra#72 r4119957736: a canvas the spec names exists in the registry the head
        # carries, so the implementation's handoff is not the first place a typo shows
        modes = canvas_modes(ch.tree.read(CANVASES))
        for url in frontmatter(text).get("canvases") or []:
            if isinstance(url, str) and url not in modes:
                errs.append(f"{path}: lists canvas {url}, which is not in {CANVASES}; register it or fix the URL")
        base_text = ch.base.read(path)
        if base_text is not None and frontmatter(base_text).get("status") == "approved" and text != base_text:
            # The one edit an approved spec takes is its status moving to superseded when the
            # spec that replaces it lands; anything else is a new contract nobody approved.
            strip = lambda t: re.sub(r"^status:.*$", "", t, flags=re.M)
            if not (frontmatter(text).get("status") == "superseded" and strip(text) == strip(base_text)):
                errs.append(f"{path}: an approved spec does not change in place; write a new spec that names it in "
                            "`supersedes` and get that one approved, then mark this one superseded")
            elif not any((nfm := frontmatter(ch.tree.read(s))).get("supersedes") == path and nfm.get("status") == "approved"
                         and nfm.get("feat_id") == frontmatter(text).get("feat_id") for s in ch.tree.list(SPECS) if s != path):
                # solyra#72 r4119957714: superseded means replaced; without an approved spec
                # naming this one in `supersedes`, the plans that cite it have no contract left
                errs.append(f"{path}: marked superseded, but no approved spec for its FEAT names it in `supersedes`; "
                            "land and approve the replacement first")
        elif base_text is not None and frontmatter(base_text).get("status") == "superseded" and text != base_text:
            # solyra#72 r4119837230: a superseded spec is history the done plans and its
            # replacement point at; it changes as little as it is deleted.
            errs.append(f"{path}: a superseded spec does not change; it is the record the plans that cite it and "
                        "the spec that replaced it point at")
    return errs


def pr_recorded_on_base(ch: Change, fm: dict) -> bool:
    """Whether the base's traceability lineage or catalog row for the plan's FEAT names its PR."""
    m = PR_REF.match(str(fm.get("pr"))) if fm.get("pr") is not None else None
    feat = fm.get("feat_id") if isinstance(fm.get("feat_id"), str) else ""
    if not m or not feat:
        return False
    trace = ch.base.read(TRACEABILITY)
    mentioned = {n for e in lineage_refs(trace or "", feat) for n in PR_MENTION.findall(e)} if trace is not None else set()
    mentioned |= set(PR_MENTION.findall(row_fields(visible(ch.base.read(CATALOG) or ""), feat).get("PRs", "")))
    return m.group(1) in mentioned


def check_changed_plans(ch: Change) -> list[str]:
    """A plan changed by a branch that is not the plan's own: a new plan is validated for
    its own FEAT; an existing plan may only move from ready to done (the post-merge close),
    byte-identical otherwise; deleting one is refused. The plan's own branch is checked
    by the trace (plan_stays_bound) instead."""
    errs: list[str] = []
    for path in ch.changed:
        if not (path.startswith(PLANS + "/") and path.endswith(".md")):
            continue
        text, base_text = ch.tree.read(path), ch.base.read(path)
        if text is not None and frontmatter(text).get("branch") == ch.branch and BRANCH.match(ch.branch) \
                and (base_text is None or frontmatter(base_text).get("branch") == ch.branch):
            continue   # the plan's own branch, as the base already binds it: the trace judges it
            # (solyra#72 r4120071816: a plan rebound to the current branch is not its own)
        if text is None:
            if base_text is not None:
                errs.append(f"{path}: a plan is not deleted; a finished plan is marked status: done and stays as the record")
            continue
        fm = frontmatter(text)
        if base_text is None:
            feat = fm.get("feat_id") if isinstance(fm.get("feat_id"), str) else ""
            # solyra#72 r4119837259: a plan lands ready; only an existing plan closes to done,
            # after its PR is in the base's record
            errs += validate_plan(fm, path, feat, ch.tree) + validate_plan_body(text, path)
            # solyra#72 r4119957722: the plan binds to an approved spec for its FEAT, and the
            # FEAT is in the catalog, while the plan lands rather than when the work starts
            spec_on_base = ch.base.read(fm.get("spec")) if isinstance(fm.get("spec"), str) else None
            if isinstance(fm.get("spec"), str) and spec_on_base is None:
                # solyra#72 r4120633495: the approved spec lands and is reviewed first; a plan
                # arriving with its spec skips that review
                errs.append(f"{path}: its spec {fm.get('spec')} is not on the base; the approved spec lands first, "
                            "the plan in a later change")
            spec_fm = frontmatter(spec_on_base) if spec_on_base is not None else {}
            if spec_fm and spec_fm.get("status") != "approved":
                errs.append(f"{path}: its spec {fm.get('spec')} is status: {spec_fm.get('status')}, not approved")
            if spec_fm and spec_fm.get("feat_id") != feat:
                errs.append(f"{path}: its spec {fm.get('spec')} serves {spec_fm.get('feat_id')}, not {feat}")
            if feat and feat not in catalog_ids(ch.base.read(CATALOG)):
                errs.append(f"{path}: feat_id {feat} is not in {CATALOG}")
            if fm.get("pr") is not None:
                # solyra#72 r4120515785: the number is the implementation PR's to record once it
                # opens; a landing plan that carries one blocks that PR for good
                errs.append(f"{path}: pr is {fm.get('pr')} on a plan landing before its implementation; leave pr: null "
                            "for the implementation branch to record")
            # solyra#72 r4120167313: the branch is one an implementation can use, and it names
            # the plan's FEAT
            bm = BRANCH.match(str(fm.get("branch")))
            if not bm:
                errs.append(f"{path}: branch {fm.get('branch')!r} is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>; "
                            "no implementation branch could use this plan")
            elif feat and bm.group(2).upper() != feat:
                errs.append(f"{path}: branch {fm.get('branch')} serves {bm.group(2).upper()}, not the plan's {feat}")
            # solyra#72 r4120071823: one plan per branch, or the trace finds two and refuses
            # every commit for that branch while neither plan may be deleted
            taken = [p for p in ch.tree.list(PLANS) if p != path and frontmatter(ch.tree.read(p)).get("branch") == fm.get("branch")]
            if taken:
                errs.append(f"{path}: branch {fm.get('branch')} is already the branch of {taken[0]}; a branch has one plan")
            continue
        strip = lambda t: re.sub(r"^status:.*$", "", t, flags=re.M)
        if not (frontmatter(base_text).get("status") == "ready" and fm.get("status") == "done" and strip(text) == strip(base_text)):
            errs.append(f"{path}: only the plan's own branch edits it, except the close after merge, which sets "
                        "status: done and changes nothing else")
        elif not pr_recorded_on_base(ch, fm):
            errs.append(f"{path}: closes a plan whose PR #{fm.get('pr')} is not yet in the base's record for "
                        f"{fm.get('feat_id')}; the close follows the merge, so the lineage or the row names the PR first")
    return errs


def check(ch: Change) -> tuple[list[str], Traced | None]:
    if ch.mode == "pr" and ch.branch.startswith("spike/"):
        return [f"branch '{ch.branch}' is a spike: local investigation commits only, never a pull request. "
                "Re-cut the work on a feature/ or fix/ branch with a plan, or a docs/ branch for its write-up."], None
    for path in ch.changed:
        if ch.tree.read(path) is not None and (mode := ch.tree.mode(path)) in ("120000", "160000"):
            # red-team round five: a requirements file replaced by a symlink to a file docs/ may edit, a
            # gitlink under docs/: the gate reads text, so a link or a submodule is refused outright
            return [f"{path}: is a {'symlink' if mode == '120000' else 'submodule'} (mode {mode}); the gate reads files only"], None
    for path, pin in PINNED.items():
        if path in ch.changed and ch.tree.raw(path) is not None and (expected := ch.base.raw(pin)) is not None and ch.tree.raw(path) != expected:
            # (bytes, not text: a CRLF file would otherwise equal its LF copy: round six)
            return [f"{path}: differs from its pinned copy {pin} on the base; change the pinned copy in its own PR first, "
                    "then make the file equal to it. A gate workflow or hook is never edited freely"], None
        if pin in ch.changed and (raw := ch.tree.raw(pin)) is not None and b"\r" in raw:
            return [f"{pin}: carries a carriage return; the pinned copies use LF line endings"], None
    for path in ch.changed:
        if path.startswith(WORKFLOWS) and path not in WORKFLOW_CONTRACTS and (text := ch.tree.read(path)) is not None:
            # round six: a second workflow with a contract's `name:` or job key publishes a green check under
            # the required check's name
            stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
            for cpath, contract in WORKFLOW_CONTRACTS.items():
                declared = re.search(r"^name:\s*['\"]?([^'\"\n#]+)", text, re.M)
                if stem == cpath.rsplit("/", 1)[-1].rsplit(".", 1)[0] or (declared and declared.group(1).strip().lower() == contract["name"]) \
                        or any(re.search(rf"^  {re.escape(job)}:\s*$", text, re.M) for job in contract["jobs"].values()):
                    return [f"{path}: takes the name or a job key of {cpath} ({contract['name']}); a required check's name belongs to "
                            "the gate's workflow alone"], None
    for path, contract in WORKFLOW_CONTRACTS.items():
        # (round six: the pinned copy is the future workflow, so a changed copy is judged as that workflow at step one)
        for shown, text in ((p, ch.tree.read(p)) for p in (path, PINNED[path]) if p in ch.changed):
            if text is None:
                continue
            path = shown   # messages name the file judged: the workflow, or its pinned copy at step one
            if why := valid_yaml(text):
                return [f"{path}: {why}; GitHub would not load the workflow and every later PR would lose the gate"], None
            runs, body = workflow_executes(text)
            statements = shell_statements(runs)
            # (solyra#72 r4120775932: the PR that introduces the script is the first the
            # command must judge, so the head's tree counts as well as the base's)
            required = list(contract["run"]) + [m for script, ms in contract.get("run_if_present", {}).items()
                                                 if ch.base.read(script) is not None or ch.tree.read(script) is not None for m in ms]
            # solyra#72 r4120337725: the command is what the statement invokes, so the contract
            # text is the statement's prefix, never a later argument
            lost = [m for m in required if not any(invokes(st, m) for st in statements)]
            if lost:
                return [f"{path}: no longer executes {len(lost)} step(s) the gate depends on ({lost[0]!r}"
                        f"{' and more' if len(lost) > 1 else ''}); a command in a comment, an echo, an unused scalar "
                        "or a step an `if:` may skip does not count. The gate's workflows keep their checks"], None
            jobs = workflow_jobs(body)
            order = tuple(m for m in contract.get("order", ()) if m in required)
            for earlier, later in zip(order, order[1:]):
                (ja, ka), (jb, kb) = job_of(jobs, earlier), job_of(jobs, later)
                if not (ja == jb and ka < kb) and not (ja != jb and needs_transitively(jobs, jb, ja)):
                    return [f"{path}: {later!r} does not follow {earlier!r} (same job, later step, or a job that "
                            "`needs` it); the base's verdict comes before the proposed gate runs"], None
            for command in (m for m in contract.get("isolated", ()) if m in required):
                j, _ = job_of(jobs, command)
                if j >= 0 and (job_of(jobs, contract["run"][0])[0] == j or any(persists for _, persists, _ in jobs[j]["checkouts"])):
                    return [f"{path}: {command!r} runs PR-controlled code, so its job holds no checkout credentials "
                            "(persist-credentials: false) and never the base's verdict"], None
            if handoff := contract.get("handoff"):
                (je, _), (js, _) = job_of(jobs, handoff["export"]), job_of(jobs, handoff["suite"])
                # solyra#72 r4121374648: the exact directory the export writes, not a path containing it
                norm = lambda p: re.sub(r"\$\{\{\s*runner\.temp\s*\}\}|\$\{RUNNER_TEMP\}", "$RUNNER_TEMP", p.replace(" ", "")).rstrip("/")
                uploads = [a for a in jobs[je]["artifacts"] if a["kind"] == "upload" and a["line"] > line_of(jobs[je], handoff["export"])
                           and norm(a["path"]) == handoff["upload_path"]] if je >= 0 else []
                downloads = [a for a in jobs[js]["artifacts"] if a["kind"] == "download" and a["line"] < line_of(jobs[js], handoff["suite"])
                             and a["path"] == handoff["download_path"]] if js >= 0 else []
                if not any(u["name"] and u["name"] == d["name"] for u in uploads for d in downloads):
                    return [f"{path}: the proposed gate no longer reaches the suite's job (actions/upload-artifact of "
                            f"`{handoff['upload_path']}/` after the export, actions/download-artifact of the same name into "
                            f"`{handoff['download_path']}` before the suite, both unconditional); the base's suite must test the proposed gate"], None
            if overridden := input_overrides(body):
                return [f"{path}: assigns or unsets {overridden[0]}, an input the gate reads from the event; the "
                        "gate's workflows never set the gate's inputs from the shell"], None
            envs = step_envs(body, contract["run"][0])
            if contract.get("env") and any(invokes(st, contract["run"][0]) for st in statements) and not envs:
                return [f"{path}: the step running {contract['run'][0]!r} has no `env:` record the gate can read; "
                        "the verdict step binds its inputs in its own `env:`"], None
            for env in envs:
                for name, expression in contract.get("env", {}).items():
                    if env.get(name) != re.sub(r"\s+", "", expression):
                        return [f"{path}: the step running {contract['run'][0]!r} no longer binds {name} to "
                                f"`{expression}` in its own `env:`; the gate reads its inputs from the event"], None
            for job in jobs:
                # stocks#1205 r4120528978: a job that runs a contract command has the repository,
                # from an unconditional checkout before its first contract command
                first = min((line_of(job, m) for m in required if line_of(job, m) >= 0), default=-1)
                if first >= 0 and not any(line < first for _, _, line in job["checkouts"]):
                    return [f"{path}: job {job['name']} runs the gate's commands without an actions/checkout step that is unconditional and "
                            "before them; it would run in an empty workspace"], None
            if re.search(r"\$\{\{[^}]*\b(secrets\.|github\.token)", body):
                # solyra#72 r4121572517: the gate's workflows hold no secret; a job running
                # head-controlled Python with one would hand it to a fork
                return [f"{path}: reads a secret or the token in an expression; the gate's workflows use none"], None
            if names := runtime_env_keys(body):
                return [f"{path}: sets {names[0]} in an `env:` block; the gate's workflows leave the shell's and "
                        "Python's startup environment alone"], None
            declared = workflow_trigger_types(body, contract["trigger"])
            if contract["trigger"] in workflow_triggers(body) and not contract["types"] <= declared:
                # solyra#72 r4120633503: without `edited` and `ready_for_review` a draft's green run
                # survives the switch to ready and a title edit; the activity types are the contract
                return [f"{path}: `on: {contract['trigger']}` no longer fires on {', '.join(sorted(contract['types'] - declared))}; "
                        "the gate's workflows keep their activity types"], None
            if filters := trigger_filters(body, contract["trigger"]):
                return [f"{path}: `on: {contract['trigger']}` carries a `{filters[0]}` filter; the gate's workflows "
                        "run for every pull request"], None
            if contract["trigger"] not in workflow_triggers(body):
                return [f"{path}: no longer runs on {contract['trigger']} (its `on:` names "
                        f"{', '.join(sorted(workflow_triggers(body))) or 'nothing'}); the gate's workflows keep their trigger"], None
            if extra := sorted(workflow_triggers(body) - {contract["trigger"]}):
                # red-team round two: a second event (`push`, `workflow_dispatch`) runs the same head-controlled
                # steps outside the pull-request context the verdict step binds, with a required check's name
                return [f"{path}: declares triggers other than {contract['trigger']} ({', '.join(extra)}); a gate workflow "
                        "runs on exactly one event"], None
            if bad := checkout_violation(body, contract["checkout"]):
                return [f"{path}: {bad}; the gate's workflows check out the side the contract names"], None
            if grant := workflow_write_grant(body):
                return [f"{path}: grants a write permission ({grant}); the gate's workflows run head-controlled code "
                        "on a read-only token, at the top level and in every job"], None
            # stocks#1205 r4121413700: the read-only grant is a top-level mapping the workflow
            # declares, not text somewhere in the file
            if top_permissions(body).get("contents") != "read":
                return [f"{path}: has no top-level `permissions:` mapping granting `contents: read`; the gate's "
                        "workflows declare their read-only token at the top level"], None
            if (m := re.search(r"^name:\s*(.*)$", body, re.M)) is None or shell_value(m.group(1)) != contract["name"]:
                return [f"{path}: is no longer named `{contract['name']}`; the required check is "
                        f"`{contract['name']} / <job>` and keeps its name"], None
            # stocks#1205 r4121413657: `python3() { echo ok; }` or `alias git=true` makes every
            # later invocation a no-op with the contract's text intact
            # stocks#1205 r4121777299: a step that rewrites a gate file, or runs inline code
            # that could, before the contract command leaves the command intact and the gate gone
            everything = every_run_text(text)
            if wrote := writes_gate_file(everything):
                return [f"{path}: `{wrote}` writes to or replaces a gate file; the workflows read the gate's files, "
                        "never write them"], None
            if inline := re.search(r"(?m)^\s*(python3?|node|perl|ruby|sh|bash)\s+(-c\b|-e\b|-(?=\s|$|<)|/dev/stdin\b)|^\s*(python3?|node|perl|ruby|sh|bash)\b(\s+-\S*)*\s*<"
                                   # (round seven: an interpreter fed from stdin (`python3 <<EOF`, `python3 -<<EOF`, `/dev/stdin`) runs inline code;
                                   # `git --output=` truncates the file it names; pip installs the tree or from an index given as an argument)
                                   r"|\bgit\s+[^\n|;&]*--output[=\s]|\bpip3?\s+install\b[^\n|;&]*(\s-e\s|\s\.\s|\s\.$|--index-url|--extra-index-url|--find-links|-f\s|-i\s)"
                                   r"|(^|[;&|{(]\s*)(eval|source|\.|shopt)\s"
                                   r"|(^|[;&|{(]\s*)(tar|bsdtar|unzip|zip|7za?|unrar|cpio|pax|xargs)\s|python3?\s+-m\s+(?!pip\b|pytest\b|py_compile\b)\S+"
                                   # (round four: `{cp,a,b}` expands to a command; `$'cp'` spells one the model does not read)
                                   r"|\{[^\s{}$]*,[^\s{}]*\}|\$['\"]"
                                   # (round five: a git subcommand that writes the tree or the index rebuilds the head over the base)
                                   r"|(^|[;&|{(]\s*)git\s+(?:-c\s+\S+\s+)*(?!(?:fetch|show|ls-tree|rev-parse|diff|log|cat-file|merge-base|ls-files|rev-list|hash-object|describe)\b)[a-z-]+", everything):
                # (red-team round two: `eval "set +e"` and `shopt -uo errexit` turn errexit off out of the
                # model's sight; `source` runs a file the tree may carry; round three: an archive extractor
                # or a `python3 -m zipfile` replaces a gate file without naming it)
                return [f"{path}: runs inline code (`{inline.group(0).strip()}`); the gate's workflows run scripts "
                        "from the tree only, never eval, source or shopt, never extract archives, and run no "
                        "module but pip, pytest and py_compile; xargs builds a command from its input; git only reads, never "
                        "with --output; an interpreter never reads its program from stdin; pip installs named packages from the default index"], None
            if shadow := shadowed_executable(body):
                return [f"{path}: defines `{shadow}` as a shell function or alias; the gate's commands run the "
                        "real executables"], None
            if not any(invokes(st, m) for job in jobs for m in required for st in job["statements"]):
                # red-team round three: a job list the parser could not read skipped every job-level check
                return [f"{path}: no job of it carries the gate's commands as the parser reads the file; the gate's "
                        "workflows keep their commands in a job's steps"], None
            for job in jobs:
                if not any(invokes(st, m) for m in required for st in job["statements"]):
                    continue
                # (red-team, this PR): a job `name:` or a matrix renames the check context GitHub
                # publishes; a container runs every step inside an image the PR names
                level = indent(job["lines"][0]) + 2
                for ln in job["lines"][1:]:
                    if indent(ln) == level and (km := re.match(r"^\s+(name|strategy|container|services|environment|uses|concurrency|defaults):", ln)):
                        return [f"{path}: job {job['name']} declares `{km.group(1)}`; a contract job keeps its key as its check "
                                "context and runs its steps directly on the runner, from the workspace root"], None
                if any(re.match(r"^\s*(-\s+)?working-directory:", ln) for ln in job["lines"]):
                    # (red-team round three): a step run elsewhere finds other files under the contract's paths
                    return [f"{path}: job {job['name']} sets `working-directory`; the gate's steps run from the workspace root"], None
                runner = next((shell_value(rm.group(1)) for ln in job["lines"] if (rm := re.match(r"^\s+runs-on:\s*(.*)$", ln))), "")
                if not runner.startswith("ubuntu-"):
                    # stocks#1205 r4121777320: another runner's default shell is not bash
                    return [f"{path}: job {job['name']} runs on {runner or 'no declared runner'}; the gate's jobs run "
                            "on ubuntu-*, whose default shell is bash"], None
            jv, _ = job_of(jobs, contract["run"][0])
            if jv >= 0:
                verdict_at = next((i for i, ln in enumerate(jobs[jv]["lines"]) if contract["run"][0] in ln), len(jobs[jv]["lines"]))
                for i, ln in enumerate(jobs[jv]["lines"][:verdict_at]):
                    if (um := re.match(r"^\s*(-\s+)?uses:\s*(.*)$", ln)) and not shell_value(um.group(2)).startswith("actions/checkout@"):
                        return [f"{path}: `{shell_value(um.group(2))}` runs before the verdict in job {jobs[jv]['name']}; only "
                                "actions/checkout precedes the gate there"], None
            for command, job_name in contract.get("jobs", {}).items():
                j, _ = job_of(jobs, command)
                if j >= 0 and jobs[j]["name"] != job_name:
                    return [f"{path}: {command!r} runs in job `{jobs[j]['name']}`, not `{job_name}`; the required check "
                            f"`{contract['name']} / {job_name}` keeps its job name"], None
    for SUITE in SUITES:
      if SUITE in ch.changed and (head_suite := ch.tree.read(SUITE)) is not None and (base_suite := ch.base.read(SUITE)):
          # solyra#72 r4119957711: the head-run registry check executes the suite the PR ships,
          # so a suite reduced to one passing test would certify any gate; every test the base
          # has stays, by name, and a PR may only add to or amend them
          if escape := suite_escape(head_suite):
              return [f"{SUITE}: uses `{escape}`; the gate's suites carry no skip markers, collection hooks or exits"], None
          base_tests, head_tests = test_assertions(base_suite), test_assertions(head_suite)
          if dropped := sorted(set(base_tests) - set(head_tests)):
              return [f"{SUITE}: drops {len(dropped)} test(s) the base has ({dropped[0]}"
                      f"{' and more' if len(dropped) > 1 else ''}); the gate's suite only grows"], None
          # solyra#72 r4120167289: a kept name with an emptied body is a dropped test; each test
          # keeps at least the assertions the base gives it
          if weakened := sorted(n for n, count in base_tests.items() if head_tests[n] < count):
              n = weakened[0]
              return [f"{SUITE}: weakens {len(weakened)} test(s) the base has ({n}: {base_tests[n]} assertion(s), now "
                      f"{head_tests[n]}{'; and more' if len(weakened) > 1 else ''}); the gate's suite only grows"], None
    for hook_path in (HOOK, PINNED[HOOK]):   # (round six: the pinned copy is the future hook, judged at step one)
        if hook_path not in ch.changed or (hook := ch.tree.read(hook_path)) is None:
            continue
        # solyra#72 r4119837242: an executable hook that no longer runs the gate is the gate
        # switched off for every clone with core.hooksPath set
        # (solyra#72 r4120167299: an `echo` of the command is not an invocation; the same statement
        # rules as the workflow contracts apply)
        # (stocks#1205 r4120828221: git hands the file to its interpreter line, so `#!/bin/true`
        # never reaches the call below it; and without `set -e` a later line decides the status)
        if hook_path == HOOK and (mode := ch.tree.mode(HOOK)) != "100755":
            # solyra#72 r4120913613: git runs a configured hook only when it is executable, so a
            # mode change is the hook switched off; read from the tree, not from a workflow's echo
            return [f"{hook_path}: has mode {mode} in this change; the hook stays executable (100755): "
                    "git update-index --chmod=+x .githooks/pre-commit"], None
        first = hook.splitlines()[0] if hook.strip() else ""
        if not re.match(r"^#!\s*(/usr/bin/env\s+(bash|sh)|/bin/(bash|sh)|/usr/bin/(bash|sh))\s*$", first):
            return [f"{hook_path}: its interpreter line is {first!r}; the hook runs under bash or sh (`#!/usr/bin/env bash`) "
                    "so the gate call on the lines below executes"], None
        if shadow := shadowed_executable("\n".join(ln for ln in hook.splitlines() if not ln.lstrip().startswith("#"))):
            return [f"{hook_path}: defines `{shadow}` as a shell function or alias; the hook runs the real executables"], None
        if overridden := input_overrides("\n".join(ln for ln in hook.splitlines() if not ln.lstrip().startswith("#"))):
            return [f"{hook_path}: assigns or unsets {overridden[0]}, an input the gate reads; the hook never sets the gate's inputs"], None
        # stocks#1205 r4121602841: the canonical path, from the repository root or `git rev-parse --show-toplevel`
        # red-team, this PR: `git reset -q` before the call emptied the index the gate inspects, and a
        # `python3 docs/tools/prep.py` or `. docs/hooks/x.sh` before it ran anything a docs/ PR ships;
        # the hook is a fixed grammar, and any other line is refused
        for ln in hook.splitlines()[1:]:
            if ln.strip() and not any(re.fullmatch(shape, ln.strip()) for shape in HOOK_LINES):
                return [f"{hook_path}: line {ln.strip()!r} is not one the hook may carry; the hook checks the Python version, "
                        "refuses unstaged gate edits and calls the gate, nothing else"], None
        if not any(re.match(r"python3?\s+['\"]?(__SUB__/|\./)?scripts/gate/spec_gate\.py['\"]?\s+--commit(\s|$)", st) for st in shell_statements(hook, errexit=False)):
            return [f"{hook_path}: no longer runs `scripts/gate/spec_gate.py --commit` after `set -e`; the hook keeps the commit-time gate"], None
    # P1b: the policy inputs the gate reads are not deleted either
    removed = [f for f in ch.changed if f in GATE_ENTRYPOINTS + POLICY_DOCS
               and ch.tree.read(f) is None and (f in GATE_ENTRYPOINTS or ch.base.read(f) is not None)]
    if removed:
        return [f"{summarize(removed)}: the gate's entrypoints and policy documents cannot be removed by a change; "
                "retiring the gate is a decision taken on main, not in a branch"], None
    # A spec is documentation that becomes policy once merged, so every changed spec is
    # validated here, before the documentation-only return, against the base's catalog
    # and requirements; a malformed spec must not land and then block or mislead the
    # implementation that cites it.
    errs_specs = check_changed_specs(ch) + check_changed_plans(ch) + check_record_uniqueness(ch) + check_policy_structure(ch)
    # A chore/ or bot/ branch is limited to its allowance for every file it touches, so
    # documentation is not exempt there: `chore/deps` cannot rewrite the requirements.
    allowance_branch = ch.branch.startswith(tuple(prefix for prefix, _ in ALLOWANCES))
    gated = [f for f in ch.changed if allowance_branch or not is_documentation(f)]
    if not gated and not BRANCH.match(ch.branch):
        # (a feature/ or fix/ branch falls through: its catalog row and records are its
        # work, and that work needs the spec, the plan and the close-out like any other)
        if errs_specs:
            return errs_specs, None
        # Documentation alone is exempt from the trace, not from the branch rule: a PR
        # still comes from a delivery branch, so `main` or `typo` is not a way in.
        if ch.mode == "pr" and not (BRANCH.match(ch.branch) or OTHER_BRANCH.match(ch.branch)):
            return [f"branch '{ch.branch}' is not a delivery branch; a pull request comes from feature/<feat-id>-<slug>, "
                    "fix/<feat-id>-<slug>, docs/<slug>, chore/<slug> or bot/superpowers-<tag>, documentation included"], None
        if ch.mode == "commit" and not (BRANCH.match(ch.branch) or OTHER_BRANCH.match(ch.branch) or ch.branch.startswith("spike/")):
            # stocks#1205 r4120166762: a commit on main, `typo` or a detached HEAD is the commit
            # the branch convention exists to prevent, documentation included
            return [f"branch '{ch.branch}' is not a delivery branch; commit documentation on docs/<slug> (or a feature/, "
                    "fix/, chore/, spike/ or bot/superpowers- branch), never on main, an unnamed branch or a detached HEAD"], None
        return [], None
    if ch.mode == "commit" and ch.branch == "HEAD":
        return [
            f"detached HEAD with {len(gated)} staged gated file(s) ({summarize(gated)}): "
            "the gate cannot tell which branch this commit is for.",
            "Name it for this commit: SPEC_GATE_BRANCH=feature/<feat-id>-<slug> git commit ...",
        ], None
    if ch.mode == "commit" and ch.branch.startswith("spike/"):
        return [], None
    # An allowance needs the full branch shape (OTHER_BRANCH): `chore/` or `chore/a/b`
    # gets none, so a malformed name cannot carry a gate file through.
    allowed = (next((ok for prefix, ok in ALLOWANCES if ch.branch.startswith(prefix)), None)
               if ch.trusted and OTHER_BRANCH.match(ch.branch) else None)
    refused = {f: (allowed(f, ch) if allowed else "") for f in gated}
    remaining = [f for f, why in refused.items() if why is not None]
    if gated and not remaining:
        return [], None   # every gated file is covered by the branch's allowance
    m = BRANCH.match(ch.branch)
    if not m:
        why = " A pull request from a fork gets no prefix allowance." if not ch.trusted else ""
        return [
            f"branch '{ch.branch}' changes {len(remaining)} gated file(s) ({summarize(remaining)}) "
            "but is not feature/<feat-id>-<slug> or fix/<feat-id>-<slug>." + why,
            *[reason for reason in refused.values() if reason],
            "docs/ carries documentation only; chore/ covers dependency manifests (dependency fields only), "
            "lockfiles and the gate's own files; anything else needs a FEAT-ID branch with an approved spec and a plan.",
        ], None
    feat_id = m.group(2).upper()
    errs: list[str] = list(errs_specs)
    # The catalog row and the approved spec are read from the BASE (HEAD for a commit, the
    # merge base for a PR): a change cannot add its own capability or approve its own spec
    # in the same diff. Phase 2 commits the approved spec alone, before any code.
    where = "HEAD" if ch.mode == "commit" else "the base branch"
    catalog_text = ch.base.read(CATALOG)
    catalog = catalog_ids(catalog_text)
    if catalog_text is None:
        errs.append(f"{CATALOG} is missing at {where}")
    elif feat_id not in catalog:
        errs.append(f"{feat_id} is not a row in {CATALOG} at {where}; a capability is added before the work that uses it")
    plans = [p for p in ch.tree.list(PLANS) if frontmatter(ch.tree.read(p)).get("branch") == ch.branch]
    if not plans:
        errs.append(f"no plan in {PLANS} names branch '{ch.branch}'")
        return errs, None
    if len(plans) > 1:
        errs.append(f"{len(plans)} plans name branch '{ch.branch}' ({', '.join(plans)}); one plan = one branch")
        return errs, None
    plan_path = plans[0]
    plan_fm = frontmatter(ch.tree.read(plan_path))
    errs += validate_plan(plan_fm, plan_path, feat_id, ch.tree) + validate_plan_body(ch.tree.read(plan_path), plan_path)
    errs += plan_stays_bound(plan_path, plan_fm, frontmatter(ch.base.read(plan_path)), ch.branch)
    spec_path = plan_fm.get("spec") if isinstance(plan_fm.get("spec"), str) else None
    spec_text = ch.base.read(spec_path) if spec_path else None
    if spec_text is None:
        if spec_path and ch.tree.read(spec_path) is not None:
            errs.append(f"{spec_path} is new in this change; an approved spec lands alone first (Phase 2), "
                        f"then the code that implements it")
        return errs, None
    if ch.tree.read(spec_path) != spec_text:
        errs.append(f"{spec_path} at this change differs from the base's copy; a spec changes on its own docs/ "
                    f"branch, so merge the base or drop the edit")
    other_specs = [f for f in ch.changed if f.startswith(SPECS + "/") and f != spec_path]
    if other_specs:
        errs.append(f"spec(s) change alongside code ({summarize(other_specs)}); a spec lands alone on a docs/ branch, "
                    "never with an implementation")
    other_plans = [f for f in ch.changed if f.startswith(PLANS + "/") and f != plan_path]
    if other_plans:
        errs.append(f"other plan(s) change alongside code ({summarize(other_plans)}); a change edits only the plan "
                    "that names its branch")
    spec_fm = frontmatter(spec_text)
    if spec_fm.get("feat_id") != feat_id:
        errs.append(f"{spec_path}: the plan's spec serves {spec_fm.get('feat_id')}, not {feat_id}")
    if spec_fm.get("status") == "draft":
        errs.append(f"{spec_path} is still status: draft; get it approved first")
    elif spec_fm.get("status") == "superseded":
        errs.append(f"{spec_path} is status: superseded; point the plan at the spec that replaced it")
    # Supersession is policy too: a spec that replaced this one on the base branch after the
    # fork is what the change must be judged against, so the base's spec list is scanned.
    # Only an APPROVED spec for the SAME FEAT replaces this one: a draft, or another
    # feature's spec that names it by mistake, cannot block the capability.
    newer = [s for s in ch.base.list(SPECS) if s != spec_path
             and (nfm := frontmatter(ch.base.read(s))).get("supersedes") == spec_path
             and nfm.get("status") == "approved" and nfm.get("feat_id") == feat_id]
    if newer:
        errs.append(f"{spec_path} is superseded by {', '.join(newer)}; point the plan at the current spec")
    errs += validate_spec(spec_fm, spec_path, catalog, requirement_defs(ch.base))
    return errs, Traced(feat_id, spec_path, spec_fm, plan_path, plan_fm)


def norm(text: str) -> str:
    return " ".join(text.split())


def split_lines(text: str) -> list[str]:
    """Lines as GitHub renders them: LF, CRLF or CR, nothing else (str.splitlines() would also
    split on U+2028 and friends, which a page shows as one line: red-team round three)."""
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


INVISIBLE = re.compile("[\u200b-\u200f\u2028\u2029\u00ad\ufeff\x0b\x0c\x1c\x1d\x1e\x85\u2060-\u2064\u034f\u180e\u061c\u202a-\u202e\u2066-\u2069]")
CODE_SPAN = re.compile(r"(`+)(?:(?!\1)[\s\S])*?\1")
CONFUSABLE = str.maketrans("АВСЕНКМОРТХаеорсухΑΒΕΖΗΙΚΜΝΟΡΤΥΧ", "ABCEHKMOPTXaeopcyxABEZHIKMNOPTYX")


def fold_text(text: str) -> str:
    """Text as a reader sees it: entities decoded, invisible characters and variation selectors
    dropped, look-alike Cyrillic and Greek letters and non-ASCII spaces read as the ASCII ones
    (red-team round five: `fоllow-up` with a Cyrillic о, `foll\u2060ow-up`)."""
    text = html.unescape(text)
    text = INVISIBLE.sub("", re.sub("[\ufe00-\ufe0f]", "", text))
    text = re.sub("[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]", " ", text)
    return text.translate(CONFUSABLE)


def visible(body: str) -> str:
    """The PR body as it renders: HTML comments and fenced code blocks removed, so a
    checkbox inside the template's comments or a code example is not a checkbox."""
    # round five: a `<!--` inside a code span is code, `<!-->` is not a comment, a link or emphasis renders
    # its text, and a look-alike letter, an invisible character or a no-break space is the plain word
    body = fold_text(body)
    masked = CODE_SPAN.sub(lambda m: "`" * len(m.group(0)), body)   # a `<!--` inside a code span is code
    for m in reversed(list(re.finditer(r"<!--(?!>|->).*?-->|<!--(?!>|->).*\Z", masked, flags=re.S))):   # an unclosed comment runs to the end
        body = body[:m.start()] + body[m.end():]
    # red-team round four: `follow&#8209;up`, `non-<b></b>blocking` and a U+2011 render as the plain words
    body = re.sub(r"</?(b|i|em|strong|s|del|u|span|sub|sup|small|code|br|kbd|mark|abbr)(\s[^<>]*)?/?>", "", body, flags=re.I)
    body = re.sub("[\u2010-\u2015\u2212\ufe58\ufe63\uff0d]", "-", body)
    # A fence opens with 3+ backticks or tildes after up to three spaces and closes with a
    # fence of the same character at least as long; an unclosed fence runs to the end.
    # (`{3,} and ~{3,} separately: a closer mixing the two characters does not close a
    # fence for Markdown, so it must not close one here either)
    # ([ \t]*, not up to three spaces: a fence nested under a list item is indented by the
    # item's content offset and still renders as code)
    # (red-team round three: a closer indented four spaces or more past its opener is content, not a
    # closer, so the fence runs on and the boxes inside it stay code)
    body = re.sub(r"^([ \t]*)(`{3,})(?![^\n]*`).*?^\1 {0,3}\2`*[ \t]*$", "", body, flags=re.S | re.M)   # a backtick in the info string is not a fence (round five)
    body = re.sub(r"^([ \t]*)(~{3,}).*?^\1 {0,3}\2~*[ \t]*$", "", body, flags=re.S | re.M)
    body = re.sub(r"^[ \t]*(`{3,}(?![^\n]*`)|~{3,}).*\Z", "", body, flags=re.S | re.M)
    # An indented code block: lines indented four spaces or a tab after a blank line, until
    # the next unindented text. Those render as code, not as links or checkboxes.
    kept, in_code, prev_blank = [], False, True
    for line in split_lines(body):
        indented = line.startswith(("    ", "\t"))
        if in_code and (indented or not line.strip()):
            continue
        in_code = indented and prev_blank
        if not in_code:
            kept.append(line)
        prev_blank = not line.strip()
    return "\n".join(kept)


def checklist(body: str) -> list[tuple[bool, str]]:
    """Each rendered task-list item: its checkbox line plus the indented continuation
    lines that render as part of it, so a deferral written under the box still counts."""
    items: list[tuple[bool, str] | None] = []
    depth: list[int] = []
    # a link renders its text and emphasis its word: `[follow](url)-up`, `*follow*-up` (round five)
    lines = [re.sub(r"(?<!\w)[*_]{1,3}(?=\S)|(?<=\S)[*_]{1,3}(?!\w)", "", re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", ln))
             for ln in split_lines(visible(body))]
    for n, line in enumerate(lines):
        if (m := CHECKBOX.match(line)):
            box = (m.group(1) in "xX", norm(m.group(2)))
            if items and items[-1] is not None and indent(line) > depth[-1]:
                # red-team round three: an unticked or deferring child renders under its parent, so the
                # parent is not done; its words reach the parent's text
                ticked, text = items[-1]
                items[-1] = (ticked and box[0], norm(f"{text} {box[1]}"))
            else:
                items.append(box)
                depth.append(indent(line))
        elif items and items[-1] is not None and line.strip() and (
                not re.match(r"^\s*([-*+]\s|\d+[.)]\s|>|#{1,6}\s|\|)", line)
                or (re.match(r"^\s*([-*+]\s|\d+[.)]\s)", line) and indent(line) > depth[-1])):
            # an indented line, an unindented one that starts no other block (lazy continuation: red-team
            # round three) or a nested bullet (round four) renders inside the item
            ticked, text = items[-1]
            items[-1] = (ticked, norm(f"{text} {line}"))
        elif not line.strip() and items and items[-1] is not None and next_indented_past(lines, n, depth[-1]):
            continue   # a loose item: the blank line does not end it while what follows is indented past its marker (round five)
        else:
            items.append(None)   # a blank line or another block ends the item
            depth.append(0)
    return [i for i in items if i is not None]


def next_indented_past(lines: list[str], n: int, marker: int) -> bool:
    later = next((ln for ln in lines[n + 1:] if ln.strip()), None)
    return later is not None and indent(later) > marker


def done_items(t: Traced) -> list[str]:
    items = t.spec_fm.get("done_when")
    return [norm(str(i)) for i in items] if isinstance(items, list) else []


def matched_boxes(items: list[str], boxes: list[tuple[bool, str]]) -> dict[str, tuple[bool, str] | None]:
    """Each done_when item's own checkbox line, or None. A line serves one item, and the
    longest item claims first, so `run the tests` cannot also tick `run the tests on 3.12`."""
    free = list(boxes)
    out: dict[str, tuple[bool, str] | None] = {i: None for i in items}
    for item in sorted(items, key=len, reverse=True):
        hit = next((b for b in free if b[1].startswith(item)), None)
        if hit is not None:
            free.remove(hit)
        out[item] = hit
    return out


def canvas_modes(text: str | None) -> dict[str, str]:
    """canvases.yml as {url: "refresh" | "report-only"}. Read line by line: the gate has
    no YAML dependency, and the file is a list of `- name:` entries with flat fields."""
    modes: dict[str, str] = {}
    url = mode = None
    for line in (text or "").splitlines() + ["- name:"]:
        if re.match(r"^\s*-\s+name:", line):
            if url:
                modes[url] = mode or "refresh"
            url = mode = None
        elif (m := re.match(r"^\s+url:\s*(\S+)", line)):
            url = m.group(1)
        elif (m := re.match(r"^\s{4}mode:\s*(\S+)", line)):   # the entry's own field, not a board's (red-team, this PR)
            mode = m.group(1)
    return modes


def check_canvas_handoff(t: Traced, body: str, tree: Tree) -> list[str]:
    """A spec that lists canvases hands their refresh to Phase 5: the PR body carries
    `Canvas refresh pending: <url>`, or the report-only marker for a report-only canvas."""
    urls = t.spec_fm.get("canvases")
    if not isinstance(urls, list) or not urls:
        return []
    modes = canvas_modes(tree.read(CANVASES))
    lines = split_lines(visible(body))
    errs: list[str] = []
    for url in urls:
        mode = modes.get(url)
        if mode is None:
            errs.append(f"{t.spec_path} lists canvas {url}, which is not in {CANVASES}")
            continue
        marker = CANVAS_MARKERS.get(mode, CANVAS_MARKERS["refresh"])
        if not any(line.strip().startswith(marker) and url in line for line in lines):
            errs.append(f"PR body must carry '{marker} {url}': the spec lists that canvas, so its Phase 5 handoff is due")
    return errs


def links_path(shown: str, path: str) -> bool:
    """The path appears as a whole token: `expected.md.old` or `expected.md-v2` names another
    file. A preceding `/` is allowed so a link to the file on the forge still counts."""
    return re.search(rf"(?<![\w.-]){re.escape(path)}(?![\w.-])", shown) is not None


def check_pr_metadata(t: Traced, env: dict, tree: Tree) -> list[str]:
    """CI only: the PR title and body must name what the gate validated."""
    title, body = env.get("PR_TITLE"), env.get("PR_BODY")
    errs: list[str] = []
    if title is not None and not title.startswith(f"{t.feat_id}:"):
        errs.append(f"PR title must start with '{t.feat_id}:', the branch's FEAT-ID, e.g. '{t.feat_id}: <what changed>'")
    if body is not None:
        shown = visible(body)   # what the reviewer reads: no HTML comments, no code examples
        if not links_path(shown, t.spec_path):
            errs.append(f"PR body must link the spec the plan names: {t.spec_path}")
        if not links_path(shown, t.plan_path):
            errs.append(f"PR body must link the plan: {t.plan_path}")
        boxes = checklist(shown)
        matched = matched_boxes(done_items(t), boxes)
        missing = [i for i, box in matched.items() if box is None]
        items = done_items(t)
        own = lambda i: [b for b in boxes if b[1].startswith(i) and not any(len(j) > len(i) and b[1].startswith(j) for j in items)]
        if twice := [i for i in items if len(own(i)) > 1]:
            # red-team round three: a ticked copy above an honest unticked line claimed the item
            errs.append("PR body carries more than one checkbox line for: " + "; ".join(twice) + "; one line per item")
        if missing:
            errs.append("PR body must carry each done_when item as its own '- [ ]' line starting with its text; "
                        "missing: " + "; ".join(missing))
        # Scanned past the item's own words: a done_when that says "no pending jobs" is the
        # spec's wording, not a deferral; what the author wrote after it is.
        deferred = [box[1] for item, box in matched.items() if box and box[0] and DEFERRAL.search(box[1][len(item):])]
        if deferred:
            errs.append("a ticked done_when item defers its work, so it is not done: " + "; ".join(deferred))
        errs += check_canvas_handoff(t, body, tree)
    return errs


def section(body: str, title: str) -> str | None:
    """The text under the first heading containing `title` (case-insensitive), HTML comments removed."""
    lines = split_lines(body)
    for i, line in enumerate(lines):
        if (h := HEADING.match(line)) and title.lower() in line.lower():
            level = len(h.group(1))
            out = []
            for later in lines[i + 1:]:
                if (hh := HEADING.match(later)) and len(hh.group(1)) <= level:
                    break   # a nested heading (### Volume under ## Capacity) is part of the section
                out.append(later)
            return "\n".join(out)
    return None


def check_capacity(body: str | None, changed: list[str]) -> list[str]:
    """CI only: a change under gcp/ or the workflows is a workload change, and CLAUDE.md
    rule 0 wants its three numbers and cost in the PR body, or an `n/a` with the reason."""
    # Documentation under a workload prefix (a README beside the workflows or a job)
    # runs nothing, so a docs/ branch editing it needs no numbers.
    workloads = [f for f in changed if f.startswith(WORKLOAD_PREFIXES) and not is_documentation(f)]
    if body is None or not workloads:
        return []
    text = section(visible(body), "capacity")
    if text is None:
        return [f"PR body needs a Capacity section: the change touches a workload ({summarize(workloads)})"]
    labelled = [label for label in CAPACITY_LABELS if re.search(r"\b" + re.escape(label) + r"\**:", text)]
    if re.search(r"\bn/a\b[ \t]*[\u2014:-][ \t]*\w", text, re.I) and not labelled:
        return []   # (red-team, this PR: an `n/a` beside filled labels waived the unfilled ones)
    # [ \t]*, not \s*: a value is on the label's own line, so a blank `Volume:` followed by
    # `Velocity: 2/day` on the next line does not borrow the next label as its value.
    blank = [label for label in CAPACITY_LABELS
             if not re.search(r"\b" + re.escape(label) + r"\**:\**[ \t]*[^\s\u00b7|]", text)]
    if blank:
        return ["PR body's Capacity section leaves " + ", ".join(blank) + " blank; give the numbers, "
                "or write 'n/a: <why no workload runs differently>'"]
    # solyra#72 r4119837253: a value is a number, not `unknown`, `fast` or `TBD`. Each
    # label's value runs from its colon to the next label.
    marks = list(re.finditer(r"\b(" + "|".join(map(re.escape, CAPACITY_LABELS)) + r")\**:\**", text))
    # The value itself is the quantity (`3 tickers`, `~2 s`, `$0.01`, `<1 GB`), not prose
    # that happens to carry a digit (`unknown; see #1205`, `TBD for phase 2`).
    unnumbered = sorted({m.group(1) for k, m in enumerate(marks)
                         if not re.match(r"\s*[~\u2248<>\u2264\u2265]?\s*[$\u20ac\u00a3]?\s*\d",
                                         text[m.end():marks[k + 1].start() if k + 1 < len(marks) else len(text)])},
                        key=CAPACITY_LABELS.index)
    if unnumbered:
        return ["PR body's Capacity section gives no number for " + ", ".join(unnumbered) + "; each value starts "
                "with its figure (rows, calls, seconds, dollars), or the section says 'n/a: <why no workload runs differently>'"]
    if deferred := [m.group(1) for k, m in enumerate(marks)
                    if DEFERRAL.search(text[m.end():marks[k + 1].start() if k + 1 < len(marks) else len(text)])]:
        # round six: CLAUDE.md rule 0 forbids exactly these words in a perf context
        return ["PR body's Capacity section defers " + ", ".join(deferred) + " (rule 0: no 'future work', 'TBD' or "
                "'follow-up' on a workload's numbers); measure it or write 'n/a: <why>'"]
    return []


def changed_lines(merge_base: str, head: str, path: str) -> list[tuple[str, int, str]]:
    """("-", line in base, text) for every line the change removes from path and
    ("+", line in head, text) for every line it adds."""
    out, old, new = [], 0, 0
    for line in git_out("diff", "-U0", merge_base, head, "--", path).splitlines():
        hunk = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)", line)
        if hunk:
            old, new = int(hunk.group(1)), int(hunk.group(2))
        elif line.startswith("-") and not line.startswith("---"):
            out.append(("-", old, line[1:]))
            old += 1
        elif line.startswith("+") and not line.startswith("+++"):
            out.append(("+", new, line[1:]))
            new += 1
    return out


def feat_span(text: str, feat_id: str) -> set[int]:
    """1-based line numbers that belong to feat_id in a product document: its table rows,
    and every section whose heading names it, up to the next heading of that level or higher."""
    lines = text.splitlines()
    span: set[int] = set()
    level = None
    for n, line in enumerate(lines, 1):
        h = HEADING.match(line)
        if h:
            if level is not None and (len(h.group(1)) <= level or any(f != feat_id for f in FEAT_IDS.findall(line))):
                level = None   # a sibling capability's heading ends the span whatever its level
            if feat_id in FEAT_IDS.findall(line):
                level = len(h.group(1))
        if level is not None or (FEAT_ROW.match(line) and FEAT_ROW.match(line).group(1) == feat_id):
            span.add(n)
    return span


def heading_levels(text: str, feat_id: str) -> list[int]:
    """The levels of the headings naming the FEAT, in order."""
    return [len(h.group(1)) for line in text.splitlines() if (h := HEADING.match(line)) and feat_id in FEAT_IDS.findall(line)]


def feat_headings(text: str, feat_id: str) -> tuple[int, int]:
    """(headings naming the FEAT, table rows keyed by it): one record, one of each."""
    lines = text.splitlines()
    return (sum(1 for line in lines if HEADING.match(line) and feat_id in FEAT_IDS.findall(line)),
            sum(1 for line in lines if (m := FEAT_ROW.match(line)) and m.group(1) == feat_id))


def policy_ids(path: str, text: str) -> set[str]:
    """The IDs a policy document defines: FEAT rows in the catalog, REQ definitions in the
    requirements, FEAT-IDs in the traceability document, canvas URLs in the registry."""
    if path == CATALOG:
        return catalog_ids(text)
    if path == REQUIREMENTS:
        return requirement_definitions(text)
    if path == CANVASES:
        return set(canvas_modes(text))
    # the traceability document: a FEAT with a heading or a row, not one merely mentioned
    # (solyra#72 r4120167327)
    shown = visible(text)
    return {f for f in set(FEAT_IDS.findall(shown)) if any(feat_headings(shown, f))}


CANVAS_MODES = ("refresh", "report-only")


def validate_canvases(text: str) -> list[str]:
    """The shape the refresh skill and the gate read: one top-level `canvases:` list whose
    entries each carry exactly one `url` at the entry's level and, when present, a `mode`
    of refresh | report-only (solyra#72 r4120337747; stocks#1205 r4120828232: judged per
    entry, since canvas_modes() keeps one url per entry). Line-oriented like canvas_modes():
    the gate has no YAML dependency."""
    errs: list[str] = []
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    top = [ln for ln in lines if indent(ln) == 0]
    if [ln.rstrip() for ln in top] != ["canvases:"]:
        errs.append(f"{CANVASES}: the document is one top-level `canvases:` list, found "
                    f"{', '.join(repr(ln.rstrip()) for ln in top) or 'no top-level key'}")
    starts = [i for i, ln in enumerate(lines) if re.match(r"^\s*-\s+\w", ln) and indent(ln) == 2]
    if lines and not starts:
        errs.append(f"{CANVASES}: no `- name:` entries under canvases")
    for i, ln in enumerate(lines):
        if indent(ln) > 0 and i < (starts[0] if starts else len(lines)):
            errs.append(f"{CANVASES}: {ln.strip()!r} sits under canvases before its first `- name:` entry")
    urls: list[str] = []
    for n, start in enumerate(starts):
        entry = lines[start:starts[n + 1] if n + 1 < len(starts) else len(lines)]
        head = entry[0]
        if not re.match(r"^\s*-\s+name:", head):
            errs.append(f"{CANVASES}: an entry starts with `- name:`, not {head.strip()!r}")
        label = head.split(":", 1)[1].strip() or f"entry {n + 1}"
        fields = [re.sub(r"^\s*-\s+", "", head)] + entry[1:]
        entry_urls = [m.group(1) for ln in fields if (m := re.match(r"^\s{4}url:\s*(\S+)", ln))]
        if len(entry_urls) != 1 or sum("url:" in ln.split("#")[0] for ln in fields) != 1:
            errs.append(f"{CANVASES}: canvas {label!r} names {len(entry_urls)} url field(s) at its own level; "
                        "every canvas names its url, exactly one")
        urls += entry_urls
        for ln in fields:
            if (m := re.match(r"^\s{4}mode:\s*(\S+)", ln)) and m.group(1) not in CANVAS_MODES:
                errs.append(f"{CANVASES}: canvas {label!r}: mode {m.group(1)!r} is not one of {' | '.join(CANVAS_MODES)}")
    for url in sorted({u for u in urls if urls.count(u) > 1}):
        errs.append(f"{CANVASES}: {url} is listed twice; one entry per canvas (stocks#1205 r4120528971)")
    return errs


def check_policy_structure(ch: Change) -> list[str]:
    """A policy document is not emptied or pruned by a change: every ID it defines on the
    base is still defined at the head (stocks#1205 r4119966286). Retiring a capability, a
    requirement or a canvas is a decision taken on main; a blanked catalog would otherwise
    pass as documentation and then refuse every feature branch."""
    errs: list[str] = []
    if CANVASES in ch.changed and (canvases := ch.tree.read(CANVASES)) is not None:
        errs += validate_canvases(canvases)
    if CATALOG in ch.changed and (catalog := ch.tree.read(CATALOG)) is not None and (base_catalog := ch.base.read(CATALOG)):
        # solyra#72 r4121753981: the close-out reads Status and Last reviewed by name, from the
        # row or the record; a renamed header would fail every later feature PR
        for feat in sorted(catalog_ids(base_catalog)):
            before, after = feat_fields(base_catalog, feat), feat_fields(catalog, feat)
            if missing := [k for k in CLOSE_OUT_FIELDS if k in before and k not in after]:
                errs.append(f"{CATALOG}: {feat} no longer carries the {', '.join(missing)} field(s) the close-out reads; "
                            "the catalog's columns and record fields keep their names")
                break
            # red-team, this PR: promoting `### FEAT-X` to `##` swallows the next record into its section
            # and every later PR for FEAT-X reads two values and cannot demote it back
            if heading_levels(base_catalog, feat) and heading_levels(base_catalog, feat) != heading_levels(catalog, feat):
                errs.append(f"{CATALOG}: changes the level of the {feat} heading; a record's heading level is part of its shape")
                break
            if repeated := repeated_fields(catalog, feat):
                errs.append(f"{CATALOG}: the {feat} record would carry {', '.join(repeated)} more than once; each close-out field once")
                break
    if REQUIREMENTS in ch.changed and ch.base.read(REQUIREMENTS) is None and (reqs := ch.tree.read(REQUIREMENTS)) is not None:
        # solyra#72 r4120633485: a repository without a registry checks req_ids for shape; a new
        # registry that omits an ID the specs cite would refuse every spec citing it
        # (solyra#72 r4121100668: a spec arriving in the same change is checked against the
        # registry-less base, so its citations must be defined here too)
        defined = requirement_definitions(reqs)
        cited = {r for tree in (ch.base, ch.tree) for path in tree.list(SPECS)
                 for r in (frontmatter(tree.read(path)).get("req_ids") or []) if isinstance(r, str)}
        if not defined:
            errs.append(f"{REQUIREMENTS}: a new requirements registry defines no `**REQ-XXX-000:**`; a registry that "
                        "exists but is empty fails every spec")
        elif missing := sorted(cited - defined):
            errs.append(f"{REQUIREMENTS}: a new requirements registry omits {len(missing)} requirement(s) the specs "
                        f"cite ({missing[0]}{' and more' if len(missing) > 1 else ''}); define them all or land none")
    for path in POLICY_DOCS:
        if path not in ch.changed or (head := ch.tree.read(path)) is None or (base := ch.base.read(path)) is None:
            continue
        if dropped := sorted(policy_ids(path, base) - policy_ids(path, head)):
            errs.append(f"{path}: no longer defines {len(dropped)} ID(s) the base has ({dropped[0]}"
                        f"{' and more' if len(dropped) > 1 else ''}); a policy document is extended in a branch, "
                        "never emptied or pruned")
        if path == CATALOG:
            # solyra#72 r4120515790: the row's PRs cell is lineage too, and only grows
            for feat_id in sorted(policy_ids(path, base)):
                numbers = lambda text: set(PR_MENTION.findall(row_fields(visible(text), feat_id).get("PRs", "")))
                if lost := sorted(numbers(base) - numbers(head), key=int):
                    errs.append(f"{path}: the {feat_id} row no longer names PR #{lost[0]}"
                                f"{' and more' if len(lost) > 1 else ''} in its PRs; lineage is a record and only grows")
        if path == TRACEABILITY:
            # stocks#1205 r4120381513: the PR lineage only grows, whatever branch edits the document
            for feat_id in sorted(policy_ids(path, base)):
                mentions = lambda text: set(PR_MENTION.findall(" ".join(lineage_refs(text, feat_id))))
                if lost := sorted(mentions(base) - mentions(head), key=int):
                    errs.append(f"{path}: the {feat_id} lineage no longer names PR #{lost[0]}"
                                f"{' and more' if len(lost) > 1 else ''}; lineage is a record and only grows")
    return errs


def check_record_uniqueness(ch: Change) -> list[str]:
    """A FEAT-ID keeps one row and one heading in the catalog and the traceability document,
    whatever branch edits them: the close-out reads the first record, so a second one
    written from a docs/ branch would be silently ignored (solyra#72 r4119837221)."""
    errs: list[str] = []
    if REQUIREMENTS in ch.changed and (text := ch.tree.read(REQUIREMENTS)) is not None:
        # stocks#1205 r4120166765: one definition per REQ-ID, or a spec validates against two
        rendered = lambda t: re.sub(r"`[^`\n]*`", "", visible(t))
        defs, base_defs = REQ_DEFINITION.findall(rendered(text)), REQ_DEFINITION.findall(rendered(ch.base.read(REQUIREMENTS) or ""))
        for req in sorted({r for r in defs if defs.count(r) > 1 and defs.count(r) > base_defs.count(r)}):
            errs.append(f"{REQUIREMENTS}: {req} is defined {defs.count(req)} times; a requirement has one definition")
    for path in (CATALOG, TRACEABILITY):
        if path not in ch.changed or (text := ch.tree.read(path)) is None:
            continue
        base_text = ch.base.read(path) or ""
        for feat_id in sorted(set(FEAT_IDS.findall(text))):
            had, has = feat_headings(base_text, feat_id), feat_headings(text, feat_id)
            if any(after > 1 and after > before for before, after in zip(had, has)):
                errs.append(f"{path}: {feat_id} has more than one heading or row; a capability has one record, "
                            "so extend the existing one rather than opening another")
    return errs


def check_product_scope(feat_id: str, ch: Change, merge_base: str, head: str) -> list[str]:
    """CI only: a feature change edits its own catalog record and traceability section, and
    nothing else's. The requirements document changes on its own docs/ branch. Runs on a
    feature/ or fix/ PR whether or not it carries code, so a docs-only one is scoped too."""
    errs: list[str] = []
    for path in ch.changed:
        if path == REQUIREMENTS:
            errs.append(f"{path} changes in this feature change; requirements change on their own docs/ branch, "
                        "before the work that cites them")
        elif path in (CATALOG, TRACEABILITY):
            before_text, after_text = Tree(merge_base).read(path) or "", ch.tree.read(path) or ""
            had, has = feat_headings(before_text, feat_id), feat_headings(after_text, feat_id)
            if any(before and after > before for before, after in zip(had, has)):
                errs.append(f"{path}: adds a second heading or row for {feat_id}; a capability has one record, "
                            "so extend the existing one rather than opening another")
                continue
            if heading_levels(before_text, feat_id) and heading_levels(before_text, feat_id) != heading_levels(after_text, feat_id):
                errs.append(f"{path}: changes the level of the {feat_id} heading; a promoted heading would swallow the "
                            "capabilities below it, so the record keeps its level")
                continue
            spans = {"-": feat_span(before_text, feat_id), "+": feat_span(after_text, feat_id)}
            # A line is outside the FEAT's scope when it sits outside its span, or names
            # another FEAT-ID: an added heading naming this FEAT cannot widen the span
            # over another capability's row or record.
            outside = [f"{side}{n}" for side, n, text in changed_lines(merge_base, head, path)
                       if text.strip() and (n not in spans[side] or any(f != feat_id for f in FEAT_IDS.findall(text)))]
            if outside:
                errs.append(f"{path}: lines outside {feat_id}'s row and record change ({summarize(outside)}); "
                            "a feature change edits only its own record")
        elif path.startswith(PRODUCT_DOCS) and path not in REGISTRY_DOCS:
            errs.append(f"{path} changes in this feature change; under {PRODUCT_DOCS} only the FEAT's own catalog "
                        "and traceability records, the model registry and its generated files may change here")
    return errs


def check_registry_rows(t: Traced, ch: Change, merge_base: str, head: str) -> list[str]:
    """CI only: a feature change edits the registry rows of the models its spec names, and no
    other's (red-team round three; product-delivery SKILL "Never" 3)."""
    path = REGISTRY_DOCS[0]
    if path not in ch.changed:
        return []
    spec_text = ch.base.read(t.spec_path) or ch.tree.read(t.spec_path) or ""
    named = set(re.findall(r"\bMODEL-[A-Z0-9]+(?:-[A-Z0-9]+)*\b", spec_text))
    changed = [text for _, _, text in changed_lines(merge_base, head, path)]
    touched = {m for text in changed for m in re.findall(r"\bMODEL-[A-Z0-9]+(?:-[A-Z0-9]+)*\b", text)}   # (round six: any cell, not the first)
    if outside := sorted(touched - named):
        return [f"{path}: changes line(s) naming {', '.join(outside[:3])}, which {t.spec_path} never names; a feature "
                "change edits only the registry rows of the models its spec covers"]
    if any(re.match(r"^\s*\|?\s*(ID|Scheduler|Model)\s*\||^\s*\|?\s*:?-+:?\s*\|", text) for text in changed):
        return [f"{path}: changes a table header or delimiter; a feature change edits rows, it does not reshape a registry table"]
    return []


def check_plan_pr(t: Traced, env: dict, ready: bool) -> list[str]:
    """CI only: the plan records the PR it belongs to. A draft may still say null,
    because the number exists only once the PR is open; a ready PR may not."""
    n = env.get("PR_NUMBER")
    if not n:
        return []
    m = PR_REF.match(str(t.plan_fm.get("pr"))) if t.plan_fm.get("pr") is not None else None
    if m and m.group(1) != n:
        return [f"{t.plan_path}: names PR #{m.group(1)}, but this is PR #{n}"]
    if ready and not m:
        return [f"{t.plan_path}: set the plan's pr to {n} before marking the PR ready"]
    return []


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def row_fields(text: str, feat_id: str) -> dict[str, str]:
    """The FEAT's catalog row as {column header: cell}."""
    lines = text.splitlines()
    header = None
    for line in lines:
        if not line.startswith("|"):
            header = None
            continue
        row = cells(line)
        if header is None:
            header = row
        elif (m := FEAT_ROW.match(line)) and m.group(1) == feat_id:
            return dict(zip(header, row))
    return {}


def squeeze(text: str) -> str:
    """Blank lines and trailing spaces are not a change to a record (round six)."""
    return "\n".join(ln.rstrip() for ln in text.split("\n") if ln.strip())


def feat_record(text: str | None, feat_id: str) -> str:
    """The FEAT's catalog record as rendered: its section where the catalog has one
    (stocks) and its table rows (solyra); what a close-out must change."""
    shown = visible(text or "")
    lines = shown.splitlines()
    section = [lines[ln - 1] for ln in section_of(shown, feat_id) if ln <= len(lines)]
    rows = [line for line in lines if line.startswith("|") and feat_id in FEAT_IDS.findall(line)]
    return "\n".join(section + rows)


def repeated_fields(text: str | None, feat_id: str) -> list[str]:
    """Close-out fields that appear more than once in the FEAT's record table: the record
    would carry two values and the gate would read the last (stocks#1205 r4120381488)."""
    text = visible(text or "")
    lines = text.splitlines()
    seen: list[str] = []
    for ln in section_of(text, feat_id):
        row = cells(lines[ln - 1]) if lines[ln - 1].startswith("|") else []
        if len(row) == 2 and row[0] in CLOSE_OUT_FIELDS:
            seen.append(row[0])
    return sorted({f for f in seen if seen.count(f) > 1})


def feat_fields(text: str | None, feat_id: str) -> dict[str, str]:
    """The FEAT's Status and Last reviewed: from its record's field table where the
    record has one (stocks), otherwise from its catalog row's columns (solyra).
    Read as rendered: a row inside an HTML comment or a code block is not a field."""
    text = visible(text or "")
    lines = text.splitlines()
    fields = {}
    for ln in section_of(text, feat_id):
        row = cells(lines[ln - 1]) if lines[ln - 1].startswith("|") else []
        if len(row) == 2 and row[0] in CLOSE_OUT_FIELDS:
            fields[row[0]] = row[1]
    if fields:
        return fields
    return {h: v for h, v in row_fields(text, feat_id).items() if h in CLOSE_OUT_FIELDS}


def added_lines(merge_base: str, head: str, path: str) -> list[tuple[int, str]]:
    """(line number in head, text) for every line the PR adds to path."""
    out, lineno = [], 0
    for line in git_out("diff", "-U0", merge_base, head, "--", path).splitlines():
        hunk = re.match(r"^@@ -\S+ \+(\d+)", line)
        if hunk:
            lineno = int(hunk.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            out.append((lineno, line[1:]))
            lineno += 1
    return out


def section_of(text: str, feat_id: str) -> range:
    """Line numbers (1-based) of the section whose heading names feat_id."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        h = HEADING.match(line)
        if h and feat_id in FEAT_IDS.findall(line):
            level = len(h.group(1))
            end = next((j for j in range(i + 1, len(lines))
                        if (hh := HEADING.match(lines[j])) and len(hh.group(1)) <= level), len(lines))
            return range(i + 1, end + 1)
    return range(0)


def lineage_refs(text: str, feat_id: str) -> set[str]:
    """The PR entries in the FEAT's traceability section as rendered: each `**PR lineage:**`
    line or list item in the visible section, so a `<!-- #N -->` is not an entry."""
    shown = visible(text)
    lines = shown.splitlines()
    return {line.strip() for ln in section_of(shown, feat_id)
            if ln <= len(lines) and re.match(r"^\s*(\*\*PR lineage:\*\*|[-*]\s)", (line := lines[ln - 1]))}


def calendar_date(value: str) -> bool:
    """True for a real YYYY-MM-DD date: 2026-99-99 is shaped like one and is not one."""
    if not ISO_DATE.match(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def check_close_out(t: Traced, ch: Change, merge_base: str, head: str, env: dict) -> list[str]:
    """CI only, once the PR is ready for review: the Phase 5 records exist in this PR."""
    n = env["PR_NUMBER"]
    pr_ref = re.compile(rf"#{re.escape(n)}(?![\w])")
    errs: list[str] = []
    matched = matched_boxes(done_items(t), checklist(env.get("PR_BODY") or ""))
    unticked = [i for i, box in matched.items() if not (box and box[0])]
    if unticked:
        errs.append("ready for review with done_when item(s) not ticked: " + "; ".join(unticked))
    now = feat_fields(ch.tree.read(CATALOG), t.feat_id)
    before = feat_fields(Tree(merge_base).read(CATALOG), t.feat_id)
    if twice := repeated_fields(ch.tree.read(CATALOG), t.feat_id):
        errs.append(f"{CATALOG}: the {t.feat_id} record carries {', '.join(twice)} more than once; each close-out "
                    "field has one row")
    reviewed, status = now.get("Last reviewed", ""), fold_text(now.get("Status", "")).strip("* ")
    if re.search(r"~~|<(s|del|strike)\b", now.get("Status", ""), re.I):
        # round six: `~~Production~~` renders struck through and read as the plain word
        errs.append(f"{CATALOG}: the {t.feat_id} Status is struck through; set it or remove it")
    head_day = git_out("show", "-s", "--format=%cs", head).strip()
    author_day = git_out("show", "-s", "--format=%as", head).strip()   # (round six: GitHub shows the author date)
    # The head commit's date, exactly: any other date, past or future, is a false freshness record.
    if not calendar_date(reviewed) or reviewed not in (head_day, author_day):
        errs.append(f"{CATALOG}: set the {t.feat_id} Last reviewed to this PR's head commit date {head_day} in "
                    f"its row or record (it reads '{reviewed or 'nothing'}')")
    elif squeeze(feat_record(ch.tree.read(CATALOG), t.feat_id)) == squeeze(feat_record(Tree(merge_base).read(CATALOG), t.feat_id)):
        errs.append(f"{CATALOG}: the {t.feat_id} record is unchanged from the base although it already reads "
                    f"{head_day}; a second PR the same day still updates its record (its PRs, Status or notes)")
    if status.lower() in ("", "unknown", "tbd", "tbc", "n/a", "none", "pending", "-", "—", "–") or set(status) <= set("?"):
        errs.append(f"{CATALOG}: set the {t.feat_id} Status in its row or record (it reads '{status or 'nothing'}')")
    # Which record carries the lineage is policy, read at the base: a repository that
    # keeps it in the catalog row (solyra) cannot be moved off that check by a PR that
    # brings its own traceability document.
    if ch.base.read(TRACEABILITY) is not None:
        now_lineage = lineage_refs(ch.tree.read(TRACEABILITY) or "", t.feat_id)
        before_lineage = lineage_refs(Tree(merge_base).read(TRACEABILITY) or "", t.feat_id)
        if not any(pr_ref.search(entry) for entry in now_lineage - before_lineage):
            errs.append(f"{TRACEABILITY}: add this PR (#{n}) to the {t.feat_id} section's PR lineage "
                        "(a `**PR lineage:**` line or a list item; a comment or prose mention does not count)")
        # Every PR the lineage named before is still named: a `**PR lineage:**` line grows
        # in place, so entries are compared by the PRs they mention, not by their text.
        mentioned = lambda entries: {m for e in entries for m in PR_MENTION.findall(e)}
        lost = sorted(mentioned(before_lineage) - mentioned(now_lineage), key=int)
        if lost:
            errs.append(f"{TRACEABILITY}: the {t.feat_id} PR lineage loses earlier PR(s) "
                        f"#{', #'.join(lost)}; lineage only grows")
    else:
        prs = row_fields(visible(ch.tree.read(CATALOG) or ""), t.feat_id).get("PRs", "")
        if not pr_ref.search(prs):
            errs.append(f"{CATALOG}: add this PR (#{n}) to the {t.feat_id} row's PRs column (it reads '{prs or 'nothing'}')")
        before_prs = set(PR_MENTION.findall(row_fields(visible(Tree(merge_base).read(CATALOG) or ""), t.feat_id).get("PRs", "")))
        lost = sorted(before_prs - set(PR_MENTION.findall(prs)), key=int)
        if lost:
            errs.append(f"{CATALOG}: the {t.feat_id} row's PRs column loses earlier PR(s) "
                        f"#{', #'.join(lost)}; the column only grows")
    return errs


def merges_main() -> bool:
    """During a merge: is MERGE_HEAD a commit of main (origin/main, else main)?"""
    for main in ("origin/main", "main"):
        if resolve(main):
            return git("merge-base", "--is-ancestor", "MERGE_HEAD", main).returncode == 0
    return False


def resolve(rev: str) -> str | None:
    r = git("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    return r.stdout.strip() if r.returncode == 0 else None


def fail(errs: list[str]) -> int:
    print("SPEC GATE FAILED")
    for e in errs:
        print(" -", e)
    print("\nRun the product-delivery skill (Phase 1 to 3) before continuing.")
    return 1


def main(argv: list[str]) -> int:
    try:
        return run(argv)
    except GitFailed as e:
        return fail([str(e)])


def run(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--commit"
    env = os.environ
    if mode == "--check-spec":
        if len(argv) < 3:
            print(__doc__)
            return 2
        tree = Tree(WORKTREE)
        path = pathlib.Path(argv[2])
        fm = frontmatter(path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None)
        errs = validate_spec(fm, path.name, catalog_ids(tree.read(CATALOG)), requirement_defs(tree))
        print("\n".join(errs) if errs else "spec ok")
        return 1 if errs else 0
    if mode == "--commit":
        real = git_out("rev-parse", "--abbrev-ref", "HEAD").strip()
        override = env.get("SPEC_GATE_BRANCH")
        if override and real != "HEAD":
            return fail([f"SPEC_GATE_BRANCH={override} is set, but HEAD is on branch '{real}'; "
                         "the override names a detached commit only. Unset it, or check the branch out."])
        branch = override if real == "HEAD" and override else real
        # --no-renames: a rename is listed as its deleted source and its added destination,
        # so moving code out to a documentation path is still seen as a change to that code.
        # A merge in progress (MERGE_HEAD exists): merging main into the branch stages
        # everything main brings in, so the branch's own contribution is the index measured
        # against main's side. Merging anything else (another branch into this one) IS this
        # branch taking on that code, and is measured against HEAD like any commit. Nothing
        # merges into main locally: main takes pull requests.
        against = []
        if resolve("MERGE_HEAD"):
            if branch == "main":
                return fail(["a merge into main is committed locally; main takes pull requests, "
                             "not local merges. Abort it (git merge --abort) and open a PR."])
            if merges_main():
                against = ["MERGE_HEAD"]
        staged = git_out("diff", "--cached", "--name-only", "--no-renames", *against).splitlines()
        before = Tree(against[0] if against else "HEAD")
        ch = Change("commit", branch, staged, Tree(None), before, before)
        errs, _ = check(ch)
    elif mode == "--pr":
        env = dict(os.environ)
        if body := env.get("PR_BODY"):
            # GitHub delivers a web-authored body with CRLF; the checks read LF (red-team round three)
            env["PR_BODY"] = body.replace("\r\n", "\n").replace("\r", "\n")
            if m := INVISIBLE.search(env["PR_BODY"]):
                return fail([f"PR body carries an invisible character (U+{ord(m.group(0)):04X}); the gate reads the body as "
                             "the page shows it, so remove it"])
        base_arg = argv[2] if len(argv) > 2 else "origin/main"
        head_arg = argv[3] if len(argv) > 3 else "HEAD"
        base, head = resolve(base_arg), resolve(head_arg)
        missing = [r for r, sha in ((base_arg, base), (head_arg, head)) if sha is None]
        if missing:
            return fail([f"ref(s) {', '.join(missing)} do not exist in this checkout; cannot compute the diff. "
                         "Fetch them (git fetch origin main) or pass the right refs. Refusing to pass on an empty diff."])
        merge_base = git("merge-base", base, head).stdout.strip()
        if not merge_base:
            return fail([f"no merge base between {base_arg} and {head_arg} (shallow clone?). Use fetch-depth: 0."])
        branch = env.get("PR_HEAD_REF") or git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        head_repo, base_repo = env.get("PR_HEAD_REPO"), env.get("PR_BASE_REPO")
        trusted = not (base_repo and head_repo != base_repo)
        changed = git_out("diff", "--name-only", "--no-renames", merge_base, head).splitlines()
        # Policy (the catalog row, the approved spec, the requirements) is read at the PR's
        # CURRENT base, so a spec superseded on main after the branch forked is seen; the
        # diff is still measured from the merge base.
        # A PR targets the integration branch only: a stacked PR onto another branch would
        # be judged against that branch's catalog and specs as if they were policy.
        base_ref = env.get("PR_BASE_REF")
        if base_ref and base_ref != MAIN:
            return fail([f"this PR targets '{base_ref}'; pull requests here target {MAIN} only. Re-target it, "
                         "or wait for the branch it stacks on to merge."])
        ch = Change("pr", branch, changed, Tree(head), Tree(base), Tree(merge_base), trusted)
        errs, traced = check(ch)
        if (m := BRANCH.match(branch)):
            errs += check_product_scope(m.group(2).upper(), ch, merge_base, head)
        # The checks below read the traced plan and spec; without them the errors from
        # check() already say what is missing.
        if traced and (owned := [f for f in ch.changed if is_process_file(f)]) \
                and traced.feat_id != WORKFLOW_FEAT and WORKFLOW_FEAT in catalog_ids(ch.base.read(CATALOG)):
            errs.append(f"process change(s) ({summarize(owned)}) belong to {WORKFLOW_FEAT}, not {traced.feat_id}; "
                        "CI configuration, the gate and the agent instructions are that capability's work")
        if traced and any(DEPLOY_FILE.match(f) for f in ch.changed) \
                and traced.feat_id != DEPLOY_FEAT and DEPLOY_FEAT in catalog_ids(ch.base.read(CATALOG)):
            errs.append(f"deploy change(s) ({summarize([f for f in ch.changed if DEPLOY_FILE.match(f)])}) belong to {DEPLOY_FEAT}, "
                        f"not {traced.feat_id}; the deploy surface is that capability's work")
        if traced:
            errs += check_registry_rows(traced, ch, merge_base, head)
        # A workload change wants its numbers whatever the branch: a chore/ PR editing
        # the gate's workflows is untraced and still changes what CI runs.
        errs += check_capacity(env.get("PR_BODY"), ch.changed)
        if traced:
            errs += check_pr_metadata(traced, env, ch.tree)
            ready = env.get("PR_DRAFT") == "false"
            errs += check_plan_pr(traced, env, ready)
            if env.get("PR_NUMBER") and ready:
                errs += check_close_out(traced, ch, merge_base, head, env)
    else:
        print(__doc__)
        return 2
    if errs:
        return fail(errs)
    print(f"spec gate ok (branch={ch.branch}, {len(ch.changed)} changed file(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
