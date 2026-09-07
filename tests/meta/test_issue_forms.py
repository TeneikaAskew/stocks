"""The issue forms in .github/ISSUE_TEMPLATE/ stay valid and stay in budget.

Added 2026-09-07, on review round 23 of #1018, after the check this file
automates was run by hand, reported "0 problems", and then went stale.

Round 21 moved the date request out of the `reverification` field's `label`
(where `<date>` had been rendering literally and could not be filled in) into
its `description`. That added 46 characters to a field sitting at 198 of a
200 cap, taking it to 244. The validator was not re-run after that edit, so
the PR carried a quoted "0 problems" that had been true of an earlier version
of the file. That is the same failure the forms themselves are about: evidence
produced against one state and then carried forward as though it still held.

A hand-run check is only as good as the last time somebody remembered to run
it. This one runs in CI, so an over-budget edit fails the build instead of
shipping a form GitHub refuses to render.

On the numeric caps below: they are applied on ASYMMETRIC COST, NOT ON
EVIDENCE. Codex reported each of them; none appears in
json.schemastore.org/github-issue-forms.json (which declares `body` as
minItems: 1 with no maxItems, and no maxLength on `description` or `label`),
nor in GitHub's syntax docs, its common-validation-errors page, or its
template-chooser page. Four sources came back empty. If the caps are real,
an over-limit file is silently invisible in the issue chooser; if they are
not, shorter fields are better design either way. Do not read these numbers
as sourced limits, and do not raise one to make a field fit.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = REPO / ".github/ISSUE_TEMPLATE"

# Unsourced; see the module docstring before changing any of these.
MAX_DESCRIPTION = 200
MAX_LABEL = 50
MAX_BODY_ELEMENTS = 10
MAX_CONTACT_NAME = 30
MAX_CONTACT_ABOUT = 200
# A checkbox OPTION label is not an element label and is not bound by the 50
# above — these are full sentences. 160 is the figure Codex reported; like every
# other number here it is unsourced, and it is applied on asymmetric cost. When
# it was added, two options sat at 160 and 159 with no headroom at all, which is
# the exact condition that produced the 244-character description this file
# exists to prevent. Both were shortened; the longest is now 151.
MAX_OPTION_LABEL = 160

# github-issue-forms.json's permitted element types.
ELEMENT_TYPES = {"markdown", "textarea", "input", "dropdown", "checkboxes"}
# Every type except markdown carries a user-visible label and needs an id to
# be addressable; markdown is display only.
NEEDS_ID_AND_LABEL = ELEMENT_TYPES - {"markdown"}


def _form_paths() -> list[Path]:
    return sorted(p for p in TEMPLATE_DIR.glob("*.yml") if p.name != "config.yml")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_there_are_forms_to_check():
    """Guard the guard: a glob that matches nothing passes every test below."""
    assert _form_paths(), f"no issue forms found under {TEMPLATE_DIR}"


@pytest.mark.parametrize("path", _form_paths(), ids=lambda p: p.name)
def test_form_parses_and_declares_a_body(path: Path):
    doc = _load(path)
    assert isinstance(doc, dict), f"{path.name}: top level is not a mapping"
    assert doc.get("name"), f"{path.name}: missing `name`"
    assert doc.get("description"), f"{path.name}: missing `description`"
    assert isinstance(doc.get("body"), list) and doc["body"], (
        f"{path.name}: `body` must be a non-empty list"
    )


@pytest.mark.parametrize("path", _form_paths(), ids=lambda p: p.name)
def test_body_elements_are_well_formed_and_within_budget(path: Path):
    doc = _load(path)
    body = doc["body"]

    assert len(body) <= MAX_BODY_ELEMENTS, (
        f"{path.name}: {len(body)} body elements > {MAX_BODY_ELEMENTS}. "
        "Merge two fields rather than raising the cap."
    )

    for i, el in enumerate(body):
        where = f"{path.name} body[{i}]"
        etype = el.get("type")
        assert etype in ELEMENT_TYPES, f"{where}: unknown type {etype!r}"

        attrs = el.get("attributes") or {}
        if etype in NEEDS_ID_AND_LABEL:
            assert el.get("id"), f"{where}: {etype} needs an `id`"
            assert attrs.get("label"), f"{where}: {etype} needs a `label`"

        label = attrs.get("label")
        if label is not None:
            assert len(label) <= MAX_LABEL, (
                f"{where} label is {len(label)} chars > {MAX_LABEL}: {label!r}"
            )

        description = attrs.get("description")
        if description is not None:
            assert len(description) <= MAX_DESCRIPTION, (
                f"{where} ({el.get('id')}) description is {len(description)} "
                f"chars > {MAX_DESCRIPTION}. Measure the FOLDED value, not the "
                "source lines — a `>-` block joins its lines with spaces, so "
                "the string is longer than any line of it looks."
            )


@pytest.mark.parametrize("path", _form_paths(), ids=lambda p: p.name)
def test_every_checkbox_option_is_required(path: Path):
    """An optional attestation is not an attestation.

    Each form ends in a checkboxes element whose options are the claims the
    filer is making about their own evidence. An option without
    `required: true` can be left unticked and the issue still submits, which
    turns the attestation into decoration.
    """
    body = _load(path)["body"]

    # Guard the guard, the same way test_there_are_forms_to_check does for the
    # glob. The loop below is a no-op for a form with no checkboxes element at
    # all, so removing a form's whole attestation used to pass CI: the
    # body-budget test stayed green because the body only got SHORTER.
    # Measured on 04-follow-up.yml with the element deleted — 14 passed.
    # By ID, not "any checkboxes element". A form that grew an unrelated
    # checkbox group could otherwise lose `id: attestation` and still pass,
    # which is the invariant this test claims to enforce rather than the one
    # it would actually be checking.
    boxes = [el for el in body if el.get("type") == "checkboxes"]
    assert any(el.get("id") == "attestation" for el in boxes), (
        f"{path.name}: no `id: attestation` checkboxes element. Every form ends "
        "in an evidence attestation; a form without one collects no claim about "
        f"how the evidence was produced. Found: {[el.get('id') for el in boxes]}"
    )

    for el in boxes:
        options = (el.get("attributes") or {}).get("options") or []
        assert options, f"{path.name}: checkboxes `{el.get('id')}` has no options"
        for opt in options:
            assert opt.get("required") is True, (
                f"{path.name}: checkboxes `{el.get('id')}` option "
                f"{opt.get('label')!r} is not `required: true`"
            )
            label = opt.get("label") or ""
            assert len(label) <= MAX_OPTION_LABEL, (
                f"{path.name}: checkboxes `{el.get('id')}` option label is "
                f"{len(label)} chars > {MAX_OPTION_LABEL}. Measure the FOLDED "
                f"value: {label!r}"
            )


def test_config_contact_links_are_within_budget():
    config = TEMPLATE_DIR / "config.yml"
    assert config.exists(), "config.yml is what turns off blank issues"
    doc = _load(config)
    for link in doc.get("contact_links") or []:
        assert len(link["name"]) <= MAX_CONTACT_NAME, (
            f"contact_link name is {len(link['name'])} > {MAX_CONTACT_NAME}: "
            f"{link['name']!r}"
        )
        assert len(link["about"]) <= MAX_CONTACT_ABOUT, (
            f"contact_link about is {len(link['about'])} > {MAX_CONTACT_ABOUT}"
        )
