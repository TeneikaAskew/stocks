"""Tests for `lib.gamma_glossary` — the cross-framework term dictionary.

Enforces structural invariants so the contract stays uniform as terms
are added: every term has all five framework aliases populated, both
definitions present, and the public API correctly strips aliases.
"""
from __future__ import annotations

import pytest

from lib.gamma_glossary import (
    FRAMEWORKS,
    GAMMA_TERMS,
    GammaTerm,
    all_keys,
    get_term,
    public_glossary,
)


# ─── Structural invariants on the dict itself ───────────────────────────────


def test_all_terms_have_canonical_name():
    """Every term must have a non-empty canonical name."""
    for key, term in GAMMA_TERMS.items():
        assert term.canonical, f"Term {key!r} has empty canonical name"
        assert isinstance(term.canonical, str)


def test_all_terms_have_short_definition_under_200_chars():
    """short_definition lands in the UI hover tooltip — needs to be terse.

    200 chars is roughly two lines in the tooltip card design.
    """
    for key, term in GAMMA_TERMS.items():
        assert term.short_definition, f"Term {key!r} has empty short_definition"
        assert len(term.short_definition) <= 200, (
            f"Term {key!r} short_definition is {len(term.short_definition)} chars "
            "(max 200 for the tooltip — split content into long_definition)"
        )


def test_all_terms_have_long_definition():
    """long_definition feeds the HelpPage — must be present and richer
    than the short version."""
    for key, term in GAMMA_TERMS.items():
        assert term.long_definition, f"Term {key!r} has empty long_definition"
        assert len(term.long_definition) > len(term.short_definition), (
            f"Term {key!r} long_definition isn't longer than short — "
            "they should carry different information"
        )


def test_all_terms_have_every_framework_alias():
    """Every term must define an alias for each framework in FRAMEWORKS.

    Drift here breaks the design promise: an LLM prompt that asks
    'how does Stratalyst call this?' would get a KeyError or NoneType
    for some terms and a value for others. Uniform coverage > partial.
    """
    expected = set(FRAMEWORKS)
    for key, term in GAMMA_TERMS.items():
        actual = set(term.aliases.keys())
        missing = expected - actual
        extra = actual - expected
        assert not missing, (
            f"Term {key!r} missing alias for framework(s): {sorted(missing)}"
        )
        assert not extra, (
            f"Term {key!r} has alias for unknown framework(s): {sorted(extra)} — "
            f"add to FRAMEWORKS tuple or remove from this term"
        )
        for framework, alias in term.aliases.items():
            assert alias, f"Term {key!r} has empty alias for {framework!r}"


def test_term_keys_are_lowercase_snake_case():
    """Stable keys = stable refs across code, tests, frontend."""
    import re

    pattern = re.compile(r"^[a-z][a-z0-9_]*$")
    for key in GAMMA_TERMS:
        assert pattern.match(key), (
            f"Term key {key!r} is not lowercase snake_case — "
            "rename to keep <TermHover term='...'> references stable"
        )


def test_frameworks_constant_matches_alias_keys():
    """If a framework is added to FRAMEWORKS, every term must add the alias
    AND vice versa. This catches the case where someone adds a framework
    but forgets to update the terms (which test_all_terms_have_every_framework_alias
    would catch on its own, but we double-check)."""
    for key, term in GAMMA_TERMS.items():
        for framework in FRAMEWORKS:
            assert framework in term.aliases, (
                f"FRAMEWORKS includes {framework!r} but term {key!r} doesn't"
            )


# ─── Core taxonomy terms must be present ────────────────────────────────────


def test_canonical_taxonomy_terms_present():
    """The plan's design depends on these specific keys existing — the
    UI references them by name. Missing one is a breaking change."""
    required = {
        "king", "gate", "spot", "flip", "midpoint",
        "hedge_node", "opex_node",
        "gex", "vex",
        "positive_gamma_regime", "negative_gamma_regime",
    }
    actual = set(GAMMA_TERMS.keys())
    missing = required - actual
    assert not missing, f"Required taxonomy term(s) missing: {sorted(missing)}"


# ─── Public-facing strip: aliases must NOT leak ─────────────────────────────


def test_public_glossary_strips_aliases():
    """The /api/glossary/gamma endpoint serves the OUTPUT of this function.
    If aliases leak through, framework names land in the public UI — that's
    the entire bug §1.7.5 says we're preventing.
    """
    out = public_glossary()
    assert "terms" in out
    for key, term_dict in out["terms"].items():
        assert "aliases" not in term_dict, (
            f"Public glossary for term {key!r} CONTAINS the aliases field — "
            "this leaks internal framework mappings into the public UI. See "
            "lib/gamma_glossary.GammaTerm.to_public_dict() — aliases must be "
            "stripped before serialization."
        )


def test_public_glossary_contains_expected_fields():
    """Sanity: the public glossary entries have all the fields the UI
    expects."""
    out = public_glossary()
    expected_fields = {"canonical", "short_definition", "long_definition", "math"}
    for key, term_dict in out["terms"].items():
        actual_fields = set(term_dict.keys())
        assert actual_fields == expected_fields, (
            f"Public glossary entry for {key!r} has fields {actual_fields}, "
            f"expected exactly {expected_fields}"
        )


def test_public_glossary_has_version():
    """The version field is the cache-bust handle for the frontend's
    React Query cache. Must exist; only bump it when the *shape* changes."""
    out = public_glossary()
    assert "version" in out
    assert out["version"] == "1"


def test_public_glossary_includes_all_terms():
    """The strip helper shouldn't accidentally drop entries."""
    out = public_glossary()
    public_keys = set(out["terms"].keys())
    internal_keys = set(GAMMA_TERMS.keys())
    assert public_keys == internal_keys


# ─── Helpers ────────────────────────────────────────────────────────────────


def test_get_term_returns_full_object_with_aliases():
    """Internal callers (AI prompts, engineering tools) see the full
    dataclass including aliases."""
    term = get_term("king")
    assert isinstance(term, GammaTerm)
    assert term.canonical == "King"
    assert "stratalyst" in term.aliases
    assert "heatseeker" in term.aliases


def test_get_term_raises_on_unknown_key():
    with pytest.raises(KeyError):
        get_term("not_a_real_term")


def test_all_keys_returns_stable_ordered_list():
    keys = all_keys()
    assert isinstance(keys, list)
    assert len(keys) == len(GAMMA_TERMS)
    assert set(keys) == set(GAMMA_TERMS.keys())
    # Same call twice should return the same order (Python dict ordering
    # is insertion-order-stable; we depend on that for the frontend
    # TypeScript type generation downstream).
    assert all_keys() == keys


# ─── Spot-check specific terms read sensibly ────────────────────────────────


def test_king_aliases_match_design_doc():
    """The plan doc names specific aliases — keep this synced as the
    cross-reference. Catches drift between doc and code."""
    king = GAMMA_TERMS["king"]
    assert king.aliases["stratalyst"] == "Anchor Pivot"
    assert king.aliases["heatseeker"] == "King Node ★"
    assert king.aliases["squeezemetrics"] == "Gamma Wall"
    assert king.aliases["spotgamma"] == "Largest Gamma Strike"


def test_flip_aliases_match_design_doc():
    flip = GAMMA_TERMS["flip"]
    assert flip.aliases["stratalyst"] == "Regime Pivot"
    assert flip.aliases["squeezemetrics"] == "Gamma Flip"
    assert flip.aliases["spotgamma"] == "Zero Gamma"


def test_gate_aliases_match_design_doc():
    gate = GAMMA_TERMS["gate"]
    assert gate.aliases["stratalyst"] == "Trigger Pivot"
    assert gate.aliases["heatseeker"] == "Gatekeeper Node"


def test_dataclass_is_frozen():
    """GammaTerm is frozen so callers can't accidentally mutate a shared
    dict entry mid-request — terms are module-level constants."""
    king = GAMMA_TERMS["king"]
    with pytest.raises((TypeError, AttributeError)):
        king.canonical = "Whatever"  # type: ignore[misc]
