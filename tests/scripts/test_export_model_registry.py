"""export_model_registry.py turns the model registry's tables into the JSON the canvas refresh reads.

Every test RUNS the exporter in a throwaway git repository holding a small
registry and experiment ledger shaped like the real ones: the same table
headers per tier and the same ID notations (ranges, lists, decorated IDs).
Nothing is stubbed.

One test per Codex finding on stocks#1205, named in its docstring. Each was
run against the exporter at 71a9bbce first and failed there for the reason
its finding gives.
"""
from __future__ import annotations

import json
import re
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
EXPORTER = REPO / "scripts/gate/export_model_registry.py"
WORKFLOW = REPO / ".github/workflows/registry-check.yml"
CANVASES = REPO / "docs/product/canvases.yml"
REGISTRY = "docs/product/07-MODEL-REGISTRY.md"
EXPERIMENTS = "docs/EXPERIMENT_REGISTRY.md"
OUT = "docs/product/generated/model-registry.json"

REGISTRY_TEXT = """\
# Model and Algorithm Registry

**Last reviewed:** 2026-09-20 · **Owner:** TBD

Every row names the decision its model produces.

## Deterministic and heuristic systems

| ID | Name | Type | Decision produced | Code | Status | Rec | Doc | Blocking issues |
|---|---|---|---|---|---|---|---|---|
| MODEL-GAMMA-001 | Gamma levels | Deterministic | King and Gate strikes | `lib/gamma.py` | Production | Keep | DOC-01 | [#942](https://github.com/TeneikaAskew/stocks/issues/942) |

## Learned models

| ID | Name | Type | Decision produced | Code / artifact | Status | Rec | Doc | Evidence |
|---|---|---|---|---|---|---|---|---|
| MODEL-MAG-001 | Magnitude | Gradient boosting | Expected move size | `lib/magnitude.py` | Invalidated | Retrain | DOC-02 | [#813](https://github.com/TeneikaAskew/stocks/issues/813) |

## LLM nodes

| ID | Nodes | Count | Code | Numeric authority | Status |
|---|---|---|---|---|---|
| MODEL-LLM-001 | Insight writer | 3 | `lib/agents/insight.py` | none | Experimental |
| MODEL-SUM-001 | summarizers | — | `lib/agents/summarizers.py` | preserve supplied values | Experimental |

## Scheduled surfaces

| Scheduler | Cron (`America/New_York`) | Job | Serves |
|---|---|---|---|
| `gamma-levels-daily` | `30 22 * * 1-5` | `p2-build-gamma-levels` | MODEL-GAMMA-001 |
| `gamma-levels-sunday` | `0 21 * * 0` | `p2-build-gamma-levels` | the same job, weekend refresh |
| `insight-pipeline-daily` | `45 8 * * 1-5` | `insight-pipeline` | **all 4 LLM nodes** — `run_insight_pipeline` |
| `regime-combo-weekly` | `0 5 * * 0` | `regime-combo` | combo mining (E-22) — owned by the ledger, not by a `MODEL-*` row |

## Experiment traceability

| Model | Experiments | Primary code | Deep doc | Recorded verdict |
|---|---|---|---|---|
| MODEL-MAG-001 | E-01 | `lib/magnitude.py` | MODEL_RETHINK_PLANS §RESULTS | PARTIAL |

## Documentation coverage and freshness

### Findings

| ID | Doc | Claim → actual | Kind | Sev | Models |
|---|---|---|---|---|---|
| DOC-01 | a.md | 3 levels → 4 | stale | P2 | MODEL-GAMMA-001 |
| DOC-02 | b.md | trained → invalidated | wrong | P1 | MODEL-MAG-001 |
| DOC-03 | c.md | weekly → daily | stale | P3 | MODEL-MAG-001 |
| DOC-09 | d.md | open PR → merged | stale | P3 | MODEL-GAMMA-001 |
| DOC-15 | e.md | 7 nodes → 3 | stale | P3 | MODEL-LLM-001 |
| DOC-16 | f.md | cron → queue | stale | P3 | MODEL-LLM-001 |
| DOC-17 | g.md | GPT → Claude | stale | P3 | MODEL-LLM-001 |

### Disposition

| ID | Disposition | Why |
|---|---|---|
| DOC-01…DOC-03 | Fixed | one pass over the three docs |
| DOC-02 | Deferred | waits for the retrain |
| DOC-09 (#1118) | Fixed | the citation names the merged PR |
| DOC-15, DOC-16, DOC-17 | Won't fix | the pages are retired |
"""

EXPERIMENTS_TEXT = """\
# Experiment Registry

Next free ID is **E-36**. An `E-26` in prose is a reference, not an entry.

## E-01 · STRAT-TYPE

Superseded by E-35 in a later session.

## E-02 · STRAT-TYPE variants

# 2026-07-06 SESSION (E-26 … E-31, E-33 + P0.1)
"""


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def write(repo: Path, path: str, text: str) -> None:
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    """The exporter, a registry and an experiment ledger, committed on `main`."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    write(tmp_path, "scripts/gate/export_model_registry.py", EXPORTER.read_text(encoding="utf-8"))
    write(tmp_path, REGISTRY, REGISTRY_TEXT)
    write(tmp_path, EXPERIMENTS, EXPERIMENTS_TEXT)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "registry")
    return tmp_path


def export(repo: Path, *args: str) -> subprocess.CompletedProcess:
    inherited = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run([sys.executable, "scripts/gate/export_model_registry.py", *args], cwd=repo,
                          env=inherited, capture_output=True, text=True)


def exported(repo: Path) -> dict:
    r = export(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads((repo / OUT).read_text(encoding="utf-8"))


def test_provenance_is_the_blob_id_of_each_source(repo):
    """stocks#1205 r4116983563 (export_model_registry.py:92).

    The old exporter recorded `git rev-parse HEAD`: the commit BEFORE the one
    that carries a registry edit and its regenerated JSON together, and not an
    ancestor of main at all after a squash merge. It now records each source's
    git blob id, which every commit holding that content shares. --check
    compares it, so an edit that parses to the same tables still reads stale.
    """
    write(repo, REGISTRY, REGISTRY_TEXT.replace("Every row names", "Each row names"))
    data = exported(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "edit the registry and regenerate its JSON")
    assert data["sources"] == {REGISTRY: _git(repo, "rev-parse", f"HEAD:{REGISTRY}"),
                               EXPERIMENTS: _git(repo, "rev-parse", f"HEAD:{EXPERIMENTS}"),
                               "scripts/gate/export_model_registry.py": _git(repo, "rev-parse", "HEAD:scripts/gate/export_model_registry.py")}
    assert export(repo, "--check").returncode == 0
    write(repo, REGISTRY, REGISTRY_TEXT + "\nA note that changes no table.\n")
    r = export(repo, "--check")
    assert r.returncode == 1 and "is stale" in r.stdout, r.stdout


def test_grouped_and_decorated_disposition_ids_reach_their_findings(repo):
    """stocks#1205 r4116983572 (export_model_registry.py:122).

    Disposition rows name findings as a range (DOC-01…DOC-03), a list
    (DOC-15, DOC-16, DOC-17) or a decorated ID (DOC-09 (#1118)). The old
    exporter keyed each row by its raw first cell, so those findings had no
    disposition. A finding's own row wins over a group that also names it.
    """
    data = exported(repo)
    assert sorted(f["id"] for f in data["findings"]) == sorted(data["dispositions"])
    disposition = {fid: rec["disposition"] for fid, rec in data["dispositions"].items()}
    assert disposition == {"DOC-01": "Fixed", "DOC-02": "Deferred", "DOC-03": "Fixed", "DOC-09": "Fixed",
                           "DOC-15": "Won't fix", "DOC-16": "Won't fix", "DOC-17": "Won't fix"}


def test_a_registry_without_model_rows_fails_closed(repo):
    """stocks#1205 r4119048059 (export_model_registry.py:240).

    A registry whose model tables no longer parse (an `ID` header renamed, a
    section dropped) exported an empty models object and --check called it
    current. Zero parsed models is a malformed source and fails both.
    """
    exported(repo)
    before = (repo / OUT).read_text(encoding="utf-8")
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| ID | Name | Type |", "| Identifier | Name | Type |"))
    r = export(repo)
    out = r.stdout + r.stderr
    assert r.returncode != 0 and ("MODEL-GAMMA-001 under" in out or "no model rows under" in out), out
    assert (repo / OUT).read_text(encoding="utf-8") == before
    r = export(repo, "--check")
    out = r.stdout + r.stderr
    assert r.returncode != 0 and ("does not recognize" in out or "no model rows under" in out), out


def test_scheduler_models_come_from_the_serves_column(repo):
    """stocks#1205 r4119162194 (export_model_registry.py:258).

    Model IDs were read from the last cell, so a column added after Serves would
    empty every scheduler's model list and --check would call the result current.
    """
    plain = exported(repo)["schedulers"]
    lines, in_schedulers = [], False
    for line in REGISTRY_TEXT.splitlines():
        if line.startswith("## "):
            in_schedulers = line.startswith("## Scheduled surfaces")
        if in_schedulers and line.startswith("| Scheduler |"):
            line += " Notes |"
        elif in_schedulers and line.startswith("|---|"):
            line += "---|"
        elif in_schedulers and line.startswith("| `"):
            line += " a note |"
        lines.append(line)
    write(repo, REGISTRY, "\n".join(lines) + "\n")
    with_notes = exported(repo)["schedulers"]
    assert [s["models"] for s in with_notes] == [s["models"] for s in plain], with_notes
    assert any(s["models"] for s in with_notes)


def test_a_traceability_row_names_a_registered_model(repo):
    """stocks#1205 r4119162216 (export_model_registry.py:241).

    A misspelled model ID in the experiment-traceability table exported as an
    orphan row that canvases.yml never looks up, so the real model's card lost
    its experiment data silently. Generation and --check fail on it.
    """
    exported(repo)
    before = (repo / OUT).read_text(encoding="utf-8")
    write(repo, REGISTRY, REGISTRY_TEXT + "\n## Experiment traceability\n\n| Model | Experiments | Primary code | Deep doc | Recorded verdict |\n|---|---|---|---|---|\n| MODEL-MAG-010 | E-01 | `x.py` | d | ok |\n")
    r = export(repo)
    assert r.returncode != 0 and "MODEL-MAG-010" in r.stdout + r.stderr, r.stdout + r.stderr
    assert (repo / OUT).read_text(encoding="utf-8") == before


def test_hidden_tables_are_not_exported(repo):
    """stocks#1205 r4119299894 (export_model_registry.py:145).

    A table retired inside an HTML comment or a fence was still parsed and its
    models exported, so the canvas kept publishing records the rendered registry
    no longer shows. Tables are discovered in the rendered document only.
    """
    plain = exported(repo)
    hidden = REGISTRY_TEXT + ("\n<!--\n## Retired\n\n| ID | Name | Type |\n|---|---|---|\n| MODEL-OLD-001 | Old | x |\n-->\n"
                              "\n```\n| ID | Name | Type |\n|---|---|---|\n| MODEL-OLD-002 | Older | x |\n```\n")
    write(repo, REGISTRY, hidden)
    assert set(exported(repo)["models"]) == set(plain["models"])


def test_a_malformed_row_fails_the_export(repo):
    """stocks#1205 r4119299907, r4119299901 (export_model_registry.py:154, :239).

    A row narrower than its header shifted later cells into the wrong fields and
    a duplicate model ID silently overwrote the earlier record; --check called
    both current. Either now fails generation with the row named.
    """
    exported(repo)
    before = (repo / OUT).read_text(encoding="utf-8")
    narrow = REGISTRY_TEXT.replace("| MODEL-GAMMA-001 | Gamma levels | Deterministic |", "| MODEL-GAMMA-001 | Gamma levels |")
    write(repo, REGISTRY, narrow)
    r = export(repo)
    assert r.returncode != 0 and "MODEL-GAMMA-001" in r.stdout + r.stderr and "cell(s)" in r.stdout + r.stderr, r.stdout + r.stderr
    twice = REGISTRY_TEXT.replace("| MODEL-MAG-001 | Magnitude |", "| MODEL-GAMMA-001 | Magnitude |")
    write(repo, REGISTRY, twice)
    r = export(repo)
    assert r.returncode != 0 and "appears twice" in r.stdout + r.stderr, r.stdout + r.stderr
    assert (repo / OUT).read_text(encoding="utf-8") == before


def test_a_deleted_tier_table_fails_the_export(repo):
    """stocks#1205 r4119416452 (export_model_registry.py:304).

    Deleting the whole LLM-nodes table left models elsewhere, so the export
    succeeded and --check called the loss current. Each tier keeps a table.
    """
    start, end = REGISTRY_TEXT.index("## LLM nodes"), REGISTRY_TEXT.index("## Scheduled surfaces")
    write(repo, REGISTRY, REGISTRY_TEXT[:start] + REGISTRY_TEXT[end:])
    r = export(repo)
    assert r.returncode != 0 and "LLM nodes" in r.stdout + r.stderr, r.stdout + r.stderr


def test_schedulers_and_traceability_name_registered_models_once(repo):
    """stocks#1205 r4119416479, r4119416461 (export_model_registry.py:280, :261).

    A misspelled ID in a Serves cell exported a scheduler that matched no card,
    and a second traceability row for a model overwrote the first; both passed
    --check. Both fail generation now.
    """
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| `p2-build-gamma-levels` | MODEL-GAMMA-001 |", "| `p2-build-gamma-levels` | MODEL-NOTREAL-999 |"))
    r = export(repo)
    assert r.returncode != 0 and "MODEL-NOTREAL-999" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, REGISTRY_TEXT + "\n## Experiment traceability\n\n| Model | Experiments | Primary code | Deep doc | Recorded verdict |\n|---|---|---|---|---|\n| MODEL-MAG-001 | E-01 | `x.py` | d | ok |\n| MODEL-MAG-001 | E-02 | `x.py` | d | ok |\n")
    r = export(repo)
    assert r.returncode != 0 and "two experiment-traceability rows" in r.stdout + r.stderr, r.stdout + r.stderr


def test_findings_and_dispositions_cover_the_same_ids(repo):
    """stocks#1205 r4119509860 (export_model_registry.py:295).

    A finding without a disposition, or a disposition whose finding was removed,
    exported and passed --check; the Concerns board then showed a card with no
    verdict or dropped the orphan. Either mismatch fails generation.
    """
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| DOC-03 | c.md |", "| DOC-04 | c.md |", 1))
    r = export(repo)
    assert r.returncode != 0 and "DOC-04" in r.stdout + r.stderr and "DOC-03" in r.stdout + r.stderr, r.stdout + r.stderr


def test_hidden_comments_do_not_reach_exported_cells(repo):
    """stocks#1205 r4118890024 (export_model_registry.py:94).

    clean() kept HTML comments, so DOC-66's `<!-- verify-docs-ok ... -->` audit
    directive sat in dispositions.DOC-66.why, which canvases.yml maps straight onto
    a Concerns card. Comments are stripped before the cell is normalized.
    """
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| MODEL-GAMMA-001 | Gamma levels |",
                                                "| MODEL-GAMMA-001 | Gamma levels <!-- verify-docs-ok: audit note --> |"))
    data = exported(repo)
    gamma = data["models"]["MODEL-GAMMA-001"]
    assert gamma["name"] == "Gamma levels"
    assert "verify-docs-ok" not in json.dumps(data)


def test_every_model_card_path_resolves_on_every_tier(repo):
    """stocks#1205 r4116983568 (canvases.yml:29).

    The tiers' tables differ: learned models say `Code / artifact` and
    `Evidence`, LLM nodes have no name, type or decision columns. canvases.yml
    maps one set of `models.<id>.<field>` paths, so every model now carries
    every one of those fields, null where its tier has no such column, with
    `code_artifact_paths` aliased to `code_paths`.
    """
    boards = yaml.safe_load(CANVASES.read_text(encoding="utf-8"))["canvases"][0]["boards"]
    paths = [p for b in boards for p in b["repo_fields"].values() if isinstance(p, str)]
    fields = [p.split(".", 2)[2] for p in paths if p.startswith("models.<id>.")]
    assert fields, paths
    models = exported(repo)["models"]
    missing = {mid: [f for f in fields if f not in rec] for mid, rec in models.items()}
    assert not any(missing.values()), missing
    assert models["MODEL-MAG-001"]["code_paths"] == ["lib/magnitude.py"]
    assert models["MODEL-LLM-001"]["name"] is None


def test_ci_checks_the_pr_head_commit(repo):
    """stocks#1205 r4116983574 (spec-gate.yml:28).

    Nothing in CI ran the freshness check, so a registry edit without its
    regenerated JSON merged green. The spec-gate workflow runs
    `--check --rev <head sha>`, which reads the sources and the committed JSON
    from that commit, because CI checks out the base, not the PR.
    """
    exported(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "regenerate")
    fresh = _git(repo, "rev-parse", "HEAD")
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| Production | Keep |", "| Retired | Drop |"))
    _git(repo, "commit", "-qam", "edit the registry, forget the JSON")
    stale = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", fresh)
    r = export(repo, "--check", "--rev", stale)
    assert r.returncode == 1 and "is stale" in r.stdout, r.stdout
    assert export(repo, "--check", "--rev", fresh).returncode == 0

    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    # The exporter the PR ships judges the JSON it ships, so this runs in its own
    # unprivileged pull_request workflow checked out at the head, not in the gate job.
    assert list(workflow.get("on", workflow.get(True))) == ["pull_request"]
    assert list(jobs) == ["registry"]
    checkout = next(s for s in jobs["registry"]["steps"] if s.get("uses", "").startswith("actions/checkout"))
    assert "ref" not in checkout.get("with", {})
    steps = jobs["registry"]["steps"]
    check = next(s for s in steps if 'export_model_registry.py --check --rev "$HEAD_SHA" --base "$BASE_SHA"' in s.get("run", ""))
    # stocks#1205 r4118661311, r4120166743: not `if: hashFiles(...)`, which reads the head
    # checkout and would skip the only check when a PR deletes the exporter, and not a
    # presence test either: the command runs unconditionally, so a deleted exporter fails here
    assert "if" not in check
    assert check["run"].strip() == 'python3 scripts/gate/export_model_registry.py --check --rev "$HEAD_SHA" --base "$BASE_SHA"'
    # solyra#72 r4118878759 (spec-gate.yml:28, P1): spec-gate.yml judges with the BASE's gate,
    # so nothing executed the gate a PR proposes; a syntax error would merge and break every
    # later PR. The head checkout compiles it and runs it to a verdict first.
    proposed = next(s for s in steps if "py_compile" in s.get("run", ""))
    assert steps.index(proposed) < steps.index(check)
    assert 'python3 "$gate" --pr "$BASE_SHA" "$HEAD_SHA"' in proposed["run"]
    # solyra#72 r4118997592 (P1): the workflows and the hook are gate files a chore/ PR may
    # touch, so their presence at the head is checked too, or a PR could delete the gate's
    # own workflow and merge green
    for required in (".github/workflows/spec-gate.yml", ".github/workflows/registry-check.yml", ".githooks/pre-commit"):
        assert required in proposed["run"], required
    # solyra#72 r4119296005 (P1): a verdict on a chore PR never reaches the traced paths, so the
    # head's gate must also pass its own suite before it can become the gate
    suite = next(s for s in steps if "python3 -m pytest tests/scripts/test_spec_gate.py" in s.get("run", ""))
    assert steps.index(proposed) < steps.index(suite) < steps.index(check)
    # solyra#72 r4119408310 (P1), r4119408312: the suite cannot be deleted by a PR, and the hook
    # must stay executable or git silently stops running it
    assert 'git cat-file -e "$BASE_SHA:$suite"' in suite["run"] and "exit 1" in suite["run"]
    assert "if [ -f" not in suite["run"], "the suite runs unconditionally; it is a gate entrypoint the PR cannot remove"
    assert 'git ls-tree "$HEAD_SHA" .githooks/pre-commit' in proposed["run"] and "100755" in proposed["run"]
    # solyra#72 r4119837242: and still call the gate; an executable `exit 0` is not a hook
    assert 'git show "$HEAD_SHA:.githooks/pre-commit"' in proposed["run"] and 'spec_gate\\.py"?[[:space:]]+--commit' in proposed["run"] and "(#|echo |printf |: )" in proposed["run"]
    assert "spec gate ok|SPEC GATE FAILED" in proposed["run"] and "exit 1" in proposed["run"]
    assert {"PR_HEAD_REF", "PR_BASE_REF", "PR_HEAD_REPO", "PR_BASE_REPO"} <= set(proposed["env"])


def test_a_stale_main_fails_only_the_pr_that_made_it_stale(repo):
    """Adversarial review of #1205, B1 (spec-gate.yml:45, export_model_registry.py:226).

    The PR head contains main, so one registry edit that reaches main without
    its JSON (a direct-to-main typo fix, which CLAUDE.md allows) turned every
    later PR red, docs-only PRs included. With --base, a stale head fails only
    when the PR itself touches a source or the JSON, or when the base was
    fresh and the head made it stale; otherwise it names main and passes.
    """
    exported(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "regenerate")
    fresh_main = _git(repo, "rev-parse", "HEAD")
    write(repo, REGISTRY, REGISTRY_TEXT.replace("Every row names", "Each row names"))
    _git(repo, "commit", "-qam", "typo fix straight to main, JSON not regenerated")
    stale_main = _git(repo, "rev-parse", "HEAD")

    # An unrelated docs PR cut from the stale main: not this PR's fault.
    _git(repo, "checkout", "-qb", "docs/unrelated")
    write(repo, "docs/README.md", "unrelated\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "docs")
    r = export(repo, "--check", "--rev", "HEAD", "--base", stale_main)
    assert r.returncode == 0 and "main" in r.stdout and "regenerate" in r.stdout, r.stdout
    assert export(repo, "--check", "--rev", "HEAD").returncode == 1

    # A PR from the same stale main that edits the registry owns the staleness.
    _git(repo, "checkout", "-qb", "docs/edits-registry", stale_main)
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| Production | Keep |", "| Retired | Drop |"))
    _git(repo, "commit", "-qam", "edit the registry, forget the JSON")
    r = export(repo, "--check", "--rev", "HEAD", "--base", stale_main)
    assert r.returncode == 1 and "is stale" in r.stdout, r.stdout

    # A PR from a FRESH main that makes it stale fails, and passes once regenerated.
    _git(repo, "checkout", "-qb", "docs/from-fresh", fresh_main)
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| Production | Keep |", "| Retired | Drop |"))
    _git(repo, "commit", "-qam", "edit the registry, forget the JSON")
    r = export(repo, "--check", "--rev", "HEAD", "--base", fresh_main)
    assert r.returncode == 1 and "is stale" in r.stdout, r.stdout
    exported(repo)
    _git(repo, "commit", "-qam", "regenerate")
    assert export(repo, "--check", "--rev", "HEAD", "--base", fresh_main).returncode == 0


def test_experiment_ids_come_from_entry_headings(repo):
    """stocks#1205 r4117591699 (export_model_registry.py:130).

    The old exporter took every E-NN anywhere in the ledger, so "Next free ID
    is E-36" exported a phantom E-36. IDs come from headings only, with a
    heading's range (E-26 … E-31) expanded, as grouped entries are headed.
    """
    assert exported(repo)["experiment_ids"] == [
        "E-01", "E-02", "E-26", "E-27", "E-28", "E-29", "E-30", "E-31", "E-33"]


def test_scheduler_models_expand_llm_group_and_same_job_rows(repo):
    """stocks#1205 r4118289666 (export_model_registry.py:206).

    Scheduler membership came only from literal MODEL-* tokens in Serves, so
    `insight-pipeline-daily` ("all 14 LLM nodes") and `premarket-brief-sunday`
    ("the same job") exported empty `models` and fell off every LLM card. A
    row naming the LLM node group now expands to every id in the LLM nodes
    tier, a row running another row's Job inherits its models, and prose that
    matches neither keeps `models` empty with a `models_note` carrying the
    Serves text.
    """
    by_name = {s["scheduler"]: s for s in exported(repo)["schedulers"]}
    assert by_name["`gamma-levels-daily`"]["models"] == ["MODEL-GAMMA-001"]
    assert by_name["`gamma-levels-sunday`"]["models"] == ["MODEL-GAMMA-001"]
    assert by_name["`insight-pipeline-daily`"]["models"] == ["MODEL-LLM-001", "MODEL-SUM-001"]
    assert by_name["`regime-combo-weekly`"]["models"] == []
    assert "owned by the ledger" in by_name["`regime-combo-weekly`"]["models_note"]
    assert not any("models_note" in s for n, s in by_name.items() if n != "`regime-combo-weekly`")


def test_a_missing_source_fails_generation_and_the_check(repo):
    """stocks#1205 r4118420401 (export_model_registry.py:252).

    The ledger was optional: with docs/EXPERIMENT_REGISTRY.md deleted the
    exporter exited 0, wrote a null blob for it under `sources`, left out
    `experiment_ids`, and once that JSON was committed --check passed. Both
    canonical sources must exist at the rev being read; a missing one fails
    generation and --check alike, naming the path, and the JSON on disk is
    left as it was rather than rewritten with a null source blob.
    """
    before = json.dumps(exported(repo), sort_keys=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "regenerate")
    fresh = _git(repo, "rev-parse", "HEAD")

    _git(repo, "rm", "-q", EXPERIMENTS)
    r = export(repo)
    assert r.returncode != 0 and EXPERIMENTS in r.stdout + r.stderr, r.stdout + r.stderr
    assert json.dumps(json.loads((repo / OUT).read_text(encoding="utf-8")), sort_keys=True) == before
    r = export(repo, "--check")
    assert r.returncode != 0 and EXPERIMENTS in r.stdout + r.stderr, r.stdout + r.stderr
    _git(repo, "commit", "-qm", "delete the ledger, keep the JSON")
    r = export(repo, "--check", "--rev", "HEAD")
    assert r.returncode != 0 and EXPERIMENTS in r.stdout + r.stderr, r.stdout + r.stderr
    assert export(repo, "--check", "--rev", fresh).returncode == 0

    _git(repo, "checkout", "-q", fresh)
    _git(repo, "rm", "-q", REGISTRY)
    r = export(repo)
    assert r.returncode != 0 and REGISTRY in r.stdout + r.stderr, r.stdout + r.stderr


def test_an_exporter_change_counts_as_touching_the_registry(repo):
    """stocks#1205 r4118475506 (export_model_registry.py:274).

    With a stale base, a PR that changed only the exporter reported no touched
    registry path, so the stale-base waiver let a behaviour change merge with
    the old JSON. The exporter is one of the paths the waiver looks at.
    """
    exported(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "regenerate")
    write(repo, REGISTRY, REGISTRY_TEXT + "\nA prose edit, JSON not regenerated.\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "stale main")
    stale_main = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "chore/exporter", stale_main)
    exporter = repo / "scripts/gate/export_model_registry.py"
    exporter.write_text(exporter.read_text(encoding="utf-8") + "\n# a behaviour change\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "change the exporter only")
    r = export(repo, "--check", "--rev", "HEAD", "--base", stale_main)
    assert r.returncode == 1 and "is stale" in r.stdout, r.stdout


def test_duplicate_finding_ids_fail_the_export(repo):
    """stocks#1205 r4119634446 (export_model_registry.py:278).

    Two concern rows sharing a DOC-* ID both exported; the ID-set comparison
    collapsed them, so --check passed while the Concerns board, keyed by id,
    could show only one. A repeated finding ID fails generation.
    """
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| DOC-03 | c.md |", "| DOC-01 | c.md |", 1))
    r = export(repo)
    assert r.returncode != 0 and "finding DOC-01 appears twice" in r.stdout + r.stderr, r.stdout + r.stderr


def test_traceability_experiments_exist_in_the_ledger(repo):
    """stocks#1205 r4119634454 (export_model_registry.py:332).

    A traceability row citing E-99 exported its text unchanged while the ledger
    IDs were computed separately, so a card could claim evidence from an
    experiment that does not exist. An E-nn the ledger lacks fails generation.
    """
    write(repo, REGISTRY, REGISTRY_TEXT + "\n## Experiment traceability\n\n| Model | Experiments | Primary code | Deep doc | Recorded verdict |\n|---|---|---|---|---|\n| MODEL-GAMMA-001 | E-01, E-99 | `x.py` | d | ok |\n")
    r = export(repo)
    assert r.returncode != 0 and "MODEL-GAMMA-001 traceability cites experiment(s) not in the ledger: E-99" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, REGISTRY_TEXT + "\n## Experiment traceability\n\n| Model | Experiments | Primary code | Deep doc | Recorded verdict |\n|---|---|---|---|---|\n| MODEL-GAMMA-001 | E-01, E-02 | `x.py` | d | ok |\n")
    assert export(repo).returncode == 0
    assert exported(repo)["experiment_traceability"]["MODEL-GAMMA-001"]["experiments"] == "E-01, E-02"


def test_a_registry_without_routed_schedulers_fails_closed(repo):
    """stocks#1205 r4119634461 (export_model_registry.py:293).

    A renamed Serves header sent every scheduler row to excluded_schedulers,
    so the export carried no scheduled surface for any card and --check called
    it current. Zero routed scheduler rows is a malformed source.
    """
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| Scheduler | Cron (`America/New_York`) | Job | Serves |",
                                                "| Scheduler | Cron (`America/New_York`) | Job | Models |"))
    r = export(repo)
    assert r.returncode != 0 and "no scheduler row routes to a model" in r.stdout + r.stderr, r.stdout + r.stderr


def test_duplicate_headers_and_disposition_rows_fail_the_export(repo):
    """stocks#1205 r4119966296, r4119966278 (export_model_registry.py:169, :285).

    Two header cells normalizing to one key let the later cell overwrite the earlier
    field, and a second single-ID disposition row for a finding was silently dropped;
    both exported and passed --check. Both are malformed rows now.
    """
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| ID | Name | Type | Decision produced | Code | Status | Rec | Doc | Blocking issues |",
                                                "| ID | Name | Type | Decision produced | Code | Status | Status | Doc | Blocking issues |"))
    r = export(repo)
    assert r.returncode != 0 and "two columns keyed status" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| DOC-02 | Deferred | waits for the retrain |\n",
                                                "| DOC-02 | Deferred | waits for the retrain |\n| DOC-02 | Fixed | retrained |\n"))
    r = export(repo)
    assert r.returncode != 0 and "DOC-02 has two disposition rows" in r.stdout + r.stderr, r.stdout + r.stderr


def test_a_registry_without_concern_tables_fails_closed(repo):
    """stocks#1205 r4120166753 (export_model_registry.py:336).

    With both concern tables deleted the finding and disposition ID sets were equal
    (empty), so the export published an empty Concerns board as current. Zero findings
    is a deleted table.
    """
    start = REGISTRY_TEXT.index("### Findings")
    write(repo, REGISTRY, REGISTRY_TEXT[:start])
    r = export(repo)
    assert r.returncode != 0 and "no finding rows parsed" in r.stdout + r.stderr, r.stdout + r.stderr


def test_cards_keep_their_columns_stamp_and_single_verdicts(repo):
    """stocks#1205 r4120381495, r4120381528, r4120381475 (export_model_registry.py:291, :244, :303).

    A Findings table without its Sev column exported cards with no sev path; a commented
    earlier `**Last reviewed:**` supplied the registry stamp; two grouped disposition rows
    naming one finding kept the first verdict silently. Each fails generation.
    """
    narrow = REGISTRY_TEXT.replace("| ID | Doc | Claim → actual | Kind | Sev | Models |\n|---|---|---|---|---|---|",
                                   "| ID | Doc | Claim → actual | Kind | Models |\n|---|---|---|---|---|")
    for sev in (" | P2 |", " | P1 |", " | P3 |"):
        narrow = narrow.replace(sev, " |")
    r = export(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    write(repo, REGISTRY, narrow)
    r = export(repo)
    assert r.returncode != 0 and "lacks the sev column(s)" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, REGISTRY_TEXT.replace("# Model and Algorithm Registry\n", "# Model and Algorithm Registry\n\n<!-- **Last reviewed:** 2025-01-01 -->\n"))
    assert export(repo).returncode == 0
    assert exported(repo)["registry_last_reviewed"] == "2026-09-20"
    write(repo, REGISTRY, REGISTRY_TEXT.replace("**Last reviewed:** 2026-09-20", "**Last reviewed:** soon"))
    r = export(repo)
    assert r.returncode != 0 and "stamp reads 'soon'" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| DOC-15, DOC-16, DOC-17 | Won't fix | the pages are retired |\n",
                                                "| DOC-15, DOC-16, DOC-17 | Won't fix | the pages are retired |\n| DOC-16, DOC-17 | Fixed | rewritten |\n"))
    r = export(repo)
    assert r.returncode != 0 and "DOC-16 is named by two grouped disposition rows" in r.stdout + r.stderr, r.stdout + r.stderr


def test_fenced_experiment_headings_and_a_missing_traceability_table_are_refused(repo):
    """stocks#1205 r4120660287, r4120660295 (export_model_registry.py:225, :397).

    A `## E-99` inside a fenced example joined the ledger, so a traceability row citing
    E-99 exported; a deleted traceability table left every card without experiments while
    --check passed. Both fail now.
    """
    write(repo, EXPERIMENTS, EXPERIMENTS_TEXT + "\n```\n## E-99 · an example heading\n```\n")
    write(repo, REGISTRY, REGISTRY_TEXT + "\n## Experiment traceability\n\n| Model | Experiments | Primary code | Deep doc | Recorded verdict |\n|---|---|---|---|---|\n| MODEL-GAMMA-001 | E-99 | `x.py` | d | ok |\n")
    r = export(repo)
    assert r.returncode != 0 and "not in the ledger: E-99" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, EXPERIMENTS, EXPERIMENTS_TEXT)
    start, end = REGISTRY_TEXT.index("## Experiment traceability"), REGISTRY_TEXT.index("## Documentation coverage")
    write(repo, REGISTRY, REGISTRY_TEXT[:start] + REGISTRY_TEXT[end:])
    r = export(repo)
    assert r.returncode != 0 and "no experiment-traceability rows parsed" in r.stdout + r.stderr, r.stdout + r.stderr


def test_a_finding_row_names_exactly_one_id(repo):
    """stocks#1205 r4120913740 (export_model_registry.py:318): a finding cell `DOC-01, DOC-99`
    kept DOC-01, dropped DOC-99 and passed the parity check, so a concern vanished from the
    cards without a word. The row is refused; grouping belongs to disposition rows alone."""
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| DOC-03 | c.md |", "| DOC-03, DOC-99 | c.md |", 1))
    r = export(repo)
    assert r.returncode != 0 and "names 2 IDs; one finding per row" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, REGISTRY_TEXT)
    assert export(repo).returncode == 0, export(repo).stdout


def test_indented_table_rows_are_rows(repo):
    """stocks#1205 r4121216904 (export_model_registry.py:181): a row indented by one space
    still renders in the table, but ended it here, so a model card vanished from the JSON
    and `--check` passed on the truncated output. Up to three leading spaces are a row."""
    write(repo, REGISTRY, REGISTRY_TEXT.replace("\n| MODEL-MAG-001 |", "\n | MODEL-MAG-001 |", 1))
    r = export(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "MODEL-MAG-001" in exported(repo)["models"]


def test_issue_numbers_accumulate_across_columns(repo):
    """stocks#1205 r4121413706 (export_model_registry.py:209): a row with `#123` under Evidence
    and `#456` under Blocking issues exported only the last column's numbers. They are unioned."""
    write(repo, REGISTRY, REGISTRY_TEXT.replace(
        "| ID | Name | Type | Decision produced | Code | Status | Rec | Doc | Blocking issues |\n|---|---|---|---|---|---|---|---|---|\n",
        "| ID | Name | Type | Decision produced | Code | Status | Rec | Doc | Blocking issues | Evidence |\n|---|---|---|---|---|---|---|---|---|---|\n", 1)
        .replace("| DOC-01 | [#942](https://github.com/TeneikaAskew/stocks/issues/942) |", "| DOC-01 | [#942](https://github.com/TeneikaAskew/stocks/issues/942) | #123 |", 1))
    assert export(repo).returncode == 0
    assert exported(repo)["models"]["MODEL-GAMMA-001"]["issue_numbers"] == [123, 942]


def test_indented_experiment_headings_are_entries(repo):
    """stocks#1205 r4121602828 (export_model_registry.py:227): an experiment heading indented by
    one to three spaces still renders as a heading, but its ID left the ledger and every
    traceability row citing it failed. Up to three spaces are a heading."""
    exp = (repo / EXPERIMENTS).read_text(encoding="utf-8") if (repo / EXPERIMENTS).exists() else None
    assert exp is not None
    write(repo, EXPERIMENTS, re.sub(r"(?m)^(## E-)", r"  \1", exp, count=1))
    assert export(repo).returncode == 0, export(repo).stdout + export(repo).stderr


def test_typo_rows_bare_delimiters_and_duplicate_experiments_are_refused(repo):
    """stocks#1205 r4121777330, r4121777339, r4121777347 (export_model_registry.py:292, :178, :227):
    `MODLE-OPT-001` in a model table vanished as prose, a delimiter of bare spaces still routed
    the rows GFM no longer renders, and two headings for one experiment ID collapsed into one.
    Each fails generation."""
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| MODEL-MAG-001 |", "| MODLE-MAG-001 |", 1))
    r = export(repo)
    assert r.returncode != 0 and "is not a MODEL- or DOC- ID" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, REGISTRY_TEXT.replace("|---|---|---|---|---|---|---|---|---|\n", "| | | | | | | | | |\n", 1))
    r = export(repo)
    assert r.returncode != 0, r.stdout + r.stderr
    exp = (repo / EXPERIMENTS).read_text(encoding="utf-8")
    first = re.search(r"(?m)^## (E-\d+)", exp).group(1)
    write(repo, REGISTRY, REGISTRY_TEXT)
    write(repo, EXPERIMENTS, exp + f"\n## {first} again\n\ntext\n")
    r = export(repo)
    assert r.returncode != 0 and "is defined by more than one heading" in r.stdout + r.stderr, r.stdout + r.stderr


def test_every_model_has_a_traceability_entry_and_malformed_refs_are_refused(repo):
    """stocks#1205 r4121888831, r4121888814 (export_model_registry.py:370; canvases.yml:34): a
    model without a traceability row had no entry, so the canvas paths under it resolved to
    nothing rather than to null; `E-3S` cited nothing and was published verbatim."""
    assert export(repo).returncode == 0
    data = exported(repo)
    assert set(data["experiment_traceability"]) == set(data["models"])
    unsourced = [m for m, rec in data["experiment_traceability"].items() if rec.get("unsourced")]
    assert unsourced and all(data["experiment_traceability"][m]["experiments"] is None for m in unsourced)
    assert data["traceability_rows"] == len(data["models"]) - len(unsourced)
    reg = REGISTRY_TEXT
    row = next(ln for ln in reg.splitlines() if ln.startswith("| MODEL-MAG-001 | E-01 |"))
    write(repo, REGISTRY, reg.replace(row, row.replace("E-01", "E-0S", 1), 1))
    r = export(repo)
    assert r.returncode != 0 and "not shaped E-NN" in r.stdout + r.stderr, r.stdout + r.stderr


def test_rows_render_as_gfm_renders_them(repo):
    """Red-team of this PR (export_model_registry.py:106, :178, :292, :141, :229, :46): a row without its
    leading pipe ended the table and vanished; a delimiter with trailing spaces was not a table; a
    header wider than its delimiter exported a table GFM does not render; a decorated ID keyed the
    card under `MODEL-X (legacy)`; the LLM tier's typo guard never fired; a finding could name a
    model that does not exist; a scheduler could appear twice; a heading mentioning an experiment
    defined it; `#123456` was truncated. Each is exported faithfully or refused."""
    assert export(repo).returncode == 0
    row = "| `gamma-levels-sunday` | `0 21 * * 0` | `p2-build-gamma-levels` | the same job, weekend refresh |"
    write(repo, REGISTRY, REGISTRY_TEXT.replace(row, row[2:], 1))   # no leading pipe: still a row
    assert export(repo).returncode == 0 and len(exported(repo)["schedulers"]) == len(exported(repo)["schedulers"]) and any("gamma-levels-sunday" in str(r) for r in exported(repo)["schedulers"])
    write(repo, REGISTRY, REGISTRY_TEXT.replace("|---|---|---|---|\n| `gamma-levels-daily`", "|---|---|---|---| \n| `gamma-levels-daily`", 1))
    assert export(repo).returncode == 0 and any("gamma-levels-daily" in str(r) for r in exported(repo)["schedulers"])
    r = export(repo) if not write(repo, REGISTRY, REGISTRY_TEXT.replace("|---|---|---|---|---|---|\n| MODEL-LLM-001", "|---|---|---|---|---|\n| MODEL-LLM-001", 1)) else None
    assert r.returncode != 0 and "delimiter row of 5" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| MODEL-SUM-001 |", "| MODEL-SUM-001 (legacy) |", 1))
    r = export(repo)
    assert r.returncode != 0 and "not a bare model ID" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| MODEL-SUM-001 |", "| MODLE-SUM-001 |", 1))
    r = export(repo)
    assert r.returncode != 0 and "is not a MODEL- or DOC- ID" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, REGISTRY_TEXT.replace("| DOC-01 | a.md | 3 levels → 4 | stale | P2 | MODEL-GAMMA-001 |", "| DOC-01 | a.md | 3 levels → 4 | stale | P2 | MODEL-GAMA-001 |", 1))
    r = export(repo)
    assert r.returncode != 0 and "finding DOC-01 names model(s) not in the registry" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, REGISTRY_TEXT.replace(row, row + "\n| `gamma-levels-daily` | `0 1 * * *` | `other` | MODEL-MAG-001 |", 1))
    r = export(repo)
    assert r.returncode != 0 and "scheduler gamma-levels-daily appears twice" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, REGISTRY_TEXT)
    exp = (repo / EXPERIMENTS).read_text(encoding="utf-8")
    write(repo, EXPERIMENTS, exp + "\n## Why E-99 was never run\n\ntext\n")
    assert export(repo).returncode == 0 and "E-99" not in exported(repo)["experiment_ids"]
    write(repo, EXPERIMENTS, exp + "\n# 2026-09-28 SESSION (E-98 … E-99)\n\ntext\n")
    assert export(repo).returncode == 0 and "E-99" in exported(repo)["experiment_ids"]
    write(repo, EXPERIMENTS, exp)
    write(repo, REGISTRY, REGISTRY_TEXT.replace("[#942](https://github.com/TeneikaAskew/stocks/issues/942)", "#123456", 1))
    assert export(repo).returncode == 0 and exported(repo)["models"]["MODEL-GAMMA-001"]["issue_numbers"] == [123456]


def test_nested_and_ragged_tables_render_as_gfm_renders_them(repo):
    """Red-team round two (export_model_registry.py:194, :168, :136, :123, :389, :319, :381, :213): a
    pipe-less line under a table is a row of it in GFM and ended the table here; a table inside a
    blockquote or list item rendered but was never parsed; `<!--` inside a fence hid everything
    after the fence; `E-99…E-01` cited nothing; `x` and x were two schedulers; `~~MODEL-X~~`
    exported as live; `model-gamma-001` vanished as prose; a `Tier` column collided with the
    derived key. Each is exported faithfully or refused."""
    assert export(repo).returncode == 0
    reg = REGISTRY_TEXT
    write(repo, REGISTRY, reg.replace("| MODEL-SUM-001 |", "see note\n| MODEL-SUM-001 |", 1))
    r = export(repo)
    assert r.returncode != 0 and "has no pipe; GFM renders it as a row" in r.stdout + r.stderr, r.stdout + r.stderr
    bullet = reg.replace("| MODEL-SUM-001 | summarizers | — | `lib/agents/summarizers.py` | preserve supplied values | Experimental |\n",
                         "| MODEL-SUM-001 | summarizers | — | `lib/agents/summarizers.py` | preserve supplied values | Experimental |\n- a note | with a pipe\n", 1)
    write(repo, REGISTRY, bullet)
    assert export(repo).returncode == 0 and "MODEL-SUM-001" in exported(repo)["models"], "a list item ends the table, it is not a row"
    quoted = "> | ID | Nodes | Count | Code | Numeric authority | Status |\n> |---|---|---|---|---|---|\n> | MODEL-HID-001 | hidden | 1 | `x.py` | none | Experimental |\n\n"
    write(repo, REGISTRY, reg.replace("## Scheduled surfaces\n", quoted + "## Scheduled surfaces\n", 1))
    r = export(repo)
    assert r.returncode != 0 and "inside a blockquote, list item or indented block" in r.stdout + r.stderr, r.stdout + r.stderr
    listed = "- note\n\n    | ID | Nodes | Count | Code | Numeric authority | Status |\n    |---|---|---|---|---|---|\n    | MODEL-HID-002 | hidden | 1 | `x.py` | none | Experimental |\n\n"
    write(repo, REGISTRY, reg.replace("## Scheduled surfaces\n", listed + "## Scheduled surfaces\n", 1))
    r = export(repo)
    assert r.returncode != 0 and "inside a blockquote, list item or indented block" in r.stdout + r.stderr, r.stdout + r.stderr
    fenced = reg.replace("## Learned models\n", "```\n<!--\n```\n\n## Learned models\n", 1)
    write(repo, REGISTRY, fenced)
    assert export(repo).returncode == 0 and "MODEL-MAG-001" in exported(repo)["models"], "a `<!--` inside a fence is code"
    write(repo, REGISTRY, reg.replace("## Learned models\n", "<!-- ``` -->\n\n## Learned models\n", 1))
    assert export(repo).returncode == 0 and "MODEL-MAG-001" in exported(repo)["models"], "a fence opener inside a comment is commentary"
    write(repo, REGISTRY, reg.replace("| DOC-01…DOC-03 | Fixed |", "| DOC-03…DOC-01 | Fixed |", 1))
    r = export(repo)
    assert r.returncode != 0 and "runs backwards" in r.stdout + r.stderr, r.stdout + r.stderr
    row = "| `gamma-levels-sunday` | `0 21 * * 0` | `p2-build-gamma-levels` | the same job, weekend refresh |"
    write(repo, REGISTRY, reg.replace(row, row + "\n| gamma-levels-sunday | `0 1 * * *` | `other` | MODEL-MAG-001 |", 1))
    r = export(repo)
    assert r.returncode != 0 and "scheduler gamma-levels-sunday appears twice" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, reg)
    exp = (repo / EXPERIMENTS).read_text(encoding="utf-8")
    write(repo, EXPERIMENTS, exp + "\nE-97 · setext entry\n-------------------\n\ntext\n")
    assert export(repo).returncode == 0 and "E-97" in exported(repo)["experiment_ids"], "a setext heading defines an experiment"
    write(repo, EXPERIMENTS, exp)
    write(repo, REGISTRY, reg.replace("| MODEL-SUM-001 |", "| ~~MODEL-SUM-001~~ |", 1))
    r = export(repo)
    assert r.returncode != 0 and "struck-through" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, reg.replace("| MODEL-SUM-001 |", "| model-sum-001 |", 1))
    r = export(repo)
    assert r.returncode != 0 and "lower-case ID" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, reg.replace("| `p2-build-gamma-levels` | MODEL-GAMMA-001 |", "| `p2-build-gamma-levels` | model-gamma-001 |", 1))
    r = export(repo)
    assert r.returncode != 0 and "in lower case" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, reg.replace("| DOC-01 | a.md | 3 levels → 4 | stale | P2 | MODEL-GAMMA-001 |", "| DOC-01 | a.md | 3 levels → 4 | stale | P2 | model-gamma-001 |", 1))
    r = export(repo)
    assert r.returncode != 0 and "in lower case" in r.stdout + r.stderr, r.stdout + r.stderr
    write(repo, REGISTRY, reg.replace("| ID | Nodes | Count | Code | Numeric authority | Status |\n|---|---|---|---|---|---|\n| MODEL-LLM-001 | Insight writer | 3 |",
                                      "| ID | Nodes | Tier | Code | Numeric authority | Status |\n|---|---|---|---|---|---|\n| MODEL-LLM-001 | Insight writer | 3 |", 1))
    r = export(repo)
    assert r.returncode != 0 and "a field the exporter derives" in r.stdout + r.stderr, r.stdout + r.stderr
