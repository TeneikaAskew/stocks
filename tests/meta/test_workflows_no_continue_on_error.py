"""No workflow sets ``continue-on-error`` to anything but an explicit ``false``.

A monthly fetch workflow once reported success with ``continue-on-error`` on
every fetch step, and its output was never stored: the sessions it should have
loaded went missing for a year (FEAT-DATA-001, Design D; CLAUDE.md Rule 3.7).
No workflow holds the key today. This test keeps it that way.

The rule is deliberately wider than "not on a fetch or validation step": a
test cannot tell a fetch step from a non-critical one. A workflow that needs
the key changes this test in the same PR, with the reason.

What it does not see: a duplicated key (YAML keeps the last one; GitHub refuses
the file), and anything outside ``.github/workflows``.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"
README = WORKFLOWS / "README.md"
KEY = "continue-on-error"
# A disabled file is scanned too: renaming it enables it.
SUFFIXES = (".yml", ".yaml", ".yml.disabled", ".yaml.disabled")


def continue_on_error_offenders(text: str) -> list[str]:
    """Every place *text* (one workflow file) sets ``continue-on-error`` to
    something other than the boolean false, as ``path = value`` strings.

    The document is loaded, not grepped: a value that arrives through a YAML
    merge key counts, and the words in a comment or inside a ``run`` script do
    not. A file that does not parse is one offender: it cannot be vouched for.
    """
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return [f"does not parse as YAML: {str(exc).splitlines()[0]}"]

    offenders: list[str] = []

    def walk(node, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                here = f"{path}.{key}" if path else str(key)
                if key == KEY and value is not False:
                    offenders.append(f"{here} = {value!r}")
                walk(value, here)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(document, "")
    return offenders


def _workflow_files() -> list[Path]:
    """Every workflow file under ``.github/workflows``, at any depth."""
    return sorted(p for p in WORKFLOWS.rglob("*")
                  if p.is_file() and p.name.endswith(SUFFIXES))


_STEP = """
jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - name: fetch
        run: python fetch.py
        continue-on-error: {value}
"""

_REJECTED = {
    "true-on-a-step": _STEP.format(value="true"),
    "true-on-a-job": """
jobs:
  fetch:
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - run: python fetch.py
""",
    "the-string-true": _STEP.format(value="'true'"),
    "yes": _STEP.format(value="yes"),
    "an-expression": _STEP.format(value="${{ matrix.experimental }}"),
    "through-a-merge-key": """
x-defaults: &defaults
  continue-on-error: true
jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - <<: *defaults
        run: python fetch.py
""",
    "does-not-parse": "jobs:\n  fetch: [unclosed\n",
}

_ACCEPTED = {
    "false": _STEP.format(value="false"),
    "no-key": """
jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - run: python fetch.py
""",
    "in-a-comment": """
jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      # continue-on-error: true would hide a failed fetch
      - run: python fetch.py
""",
    "inside-a-run-script": """
jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - run: |
          echo "continue-on-error: true"
          grep -r "continue-on-error: true" .github || true
""",
}


@pytest.mark.parametrize(
    "text,rejected",
    [(t, True) for t in _REJECTED.values()] + [(t, False) for t in _ACCEPTED.values()],
    ids=[f"rejects-{k}" for k in _REJECTED] + [f"accepts-{k}" for k in _ACCEPTED])
def test_the_check_rejects_and_accepts(text, rejected):
    offenders = continue_on_error_offenders(text)
    if rejected:
        assert offenders, "the check let this through"
    else:
        assert offenders == []


def test_a_merge_key_offender_names_the_step():
    offenders = continue_on_error_offenders(_REJECTED["through-a-merge-key"])
    assert "jobs.fetch.steps[0].continue-on-error = True" in offenders


@pytest.mark.parametrize("spelling", ["no", "off"])
def test_yaml_1_1_false_spellings_are_read_as_false(spelling):
    # PyYAML follows YAML 1.1, where `no` and `off` ARE the boolean false, so
    # the rule ("anything but the boolean false") accepts them. That is the
    # spec's rule as written; this test pins it so the gap is visible instead
    # of assumed. GitHub's own parser may read these words differently.
    assert yaml.safe_load(f"k: {spelling}") == {"k": False}
    assert continue_on_error_offenders(_STEP.format(value=spelling)) == []


def test_no_workflow_sets_continue_on_error():
    files = _workflow_files()
    names = {p.name for p in files}
    # An empty walk must not pass: the two gate workflows are always here.
    assert {"spec-gate.yml", "registry-check.yml"} <= names
    found = {
        str(p.relative_to(REPO)): offenders
        for p in files
        if (offenders := continue_on_error_offenders(p.read_text(encoding="utf-8")))
    }
    assert found == {}, "\n".join(
        f"{name}: {offender}" for name, offenders in found.items() for offender in offenders)


def test_the_readme_states_the_rule():
    text = README.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if KEY in line]
    assert len(lines) == 1
    assert "on any step or job" in lines[0]
    assert "tests/meta/test_workflows_no_continue_on_error.py" in lines[0]
    assert "on a fetch or validation step" not in text
