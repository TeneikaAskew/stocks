"""The model registry is only useful if its pointers are real.

On 2026-09-15 `docs/product/07-MODEL-REGISTRY.md` simultaneously: cited two
issues as blocking that had been closed the day before; listed a model's code
as `platform/src/lib/greeksCalculator.ts`, a file deleted months earlier and
recorded as deleted in this repo's own BRIEFING_DECK; said six model-bearing
jobs were scheduled while `gcp/deploy.sh:4410` declared a seventh; and filed
experiment E-20 under MODEL-CALIB-001, the per-ticker threshold writer, when
E-20 is LightGBM probability calibration and belongs to the TYPE and MAG
engines. Every one of those is a pointer that reads as authoritative and goes
nowhere. None was caught by a test, because nothing tests `docs/product/*.md`
— `check_generated_docs.py` gates only 05-a, 05-c, 05-d and the root README.

A second review round then found six holes in the first version of these
invariants -- an id check that reset per table, a scheduler parser that read
commented-out declarations, a both-engines check that passed when an experiment
was deleted from BOTH models, a range parser that took only the endpoints, a
silent skip on an experiment the ledger could not classify, and a published
contract the test explicitly permitted violating. All six are closed below, and
two invariants the first version lacked were added (§9). The lesson worth
keeping: a gate needs reading adversarially by someone other than its author.

A third round found three more, all of the same shape -- a check that verified
what was present and never asked what was absent: the scheduler-completeness
check matched model words in job names and so never saw `signal-monitor`, the
job that fires four registered models; the family check `continue`d past every
id in an allowlist of unparsed ledger sections; and total omission of a
single-engine experiment from both ownership tables was checked by nothing.
Closed in §8 and §9.

This pins the parts a machine can settle offline. Eleven invariants:

1. Every repo-rooted code path the registry cites exists.
2. Every relative markdown link in `docs/product/*.md` resolves.
3. Every `MODEL-*` id is unique, and the scheduler table agrees with
   `gcp/deploy.sh` — name, cron and target job, plus the claim about which
   jobs are unscheduled. This one alone would have caught the `gamma-levels-daily`
   error above.
4. Any "N Cloud Run Jobs" claim matches `doc_inventory.py`'s declared count,
   and is phrased so the daily `verify_docs_against_live.py` job will not read
   it as a live-fleet claim. That job runs `0 13 * * 1-5`, so without this the
   feedback arrives a day late, in CI, on main.
5. Status / Rec / Doc cells come from the vocabularies `docs/product/README.md`
   and this file declare, parsed from those files rather than retyped here.
6. Every `DOC-nn` a model cites exists in the concern register.
7. `Last reviewed` is no older than the newest date in the document's own body.
8. The experiment-to-model join agrees with the ledger — see section 8 below,
   which is where the three findings on PR #1111's second review landed.
9. Every experiment id the ledger declares is on a model's row or in the
   ownerless table, so a single-engine experiment cannot vanish silently.
10. Every scheduled model-bearing job is in the scheduler table, keyed by
    scheduler entry, including the ones whose job name carries no model
    word (`signal-monitor`).
11. `Rec` cells come from the declared vocabulary.

What it deliberately does NOT do:

* **It cannot check whether a cited GitHub issue is still open.** That is the
  defect that started this and it needs the network. The registry carries a
  prose caveat instead, and the nearest offline proxy — every issue cited in
  the registry also appears in 12-PR-ISSUE-TRACEABILITY.md — is asserted below.
* **It cannot tell whether a document's prose matches the code it describes.**
  This is the expensive limit. Six reference docs under `docs/models/` shipped
  misdescribing production -- a conjunction where the code scores a gate, a
  flag read as `false` that is `true`, a ranking that does not exist -- while
  every invariant here was green. A passing suite means the registry is
  internally consistent, not that it is true.
* **It does not use git dates for staleness.** This repo is a shallow clone:
  graft `4df291d` (2026-09-07) has no parent, so 187 of 220 docs report exactly
  one commit on that date whatever their real age. Worse, CI checks out with no
  `fetch-depth`, so there every file has one commit and a git-based check would
  pass forever while measuring nothing. The freshness invariant used instead is
  purely local: the header stamp must be at least as new as the newest date the
  document's own body mentions.

Pinned in two tiers, following tests/meta/test_http_status_classification.py:
the registry itself must be CLEAN, and the other product docs are a counted
backlog that may only shrink. They are pre-existing and belong to files this
work does not own, so per CLAUDE.md Rule 3.7 they are catalogued, not swept in.

Repo-level invariant, so it lives in tests/meta/ (two levels below root).
"""

from __future__ import annotations

import datetime as _dt
import sys
import re
import urllib.parse
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PRODUCT = REPO / "docs" / "product"
REGISTRY = PRODUCT / "07-MODEL-REGISTRY.md"
DEPLOY = REPO / "gcp" / "deploy.sh"

#: Prefixes that make a backticked token a repo-rooted path rather than a
#: module reference (`lib.gamma`), a glob, or a bare filename that resolves
#: against a directory named in the same table cell.
ROOTS = ("lib/", "gcp/", "scripts/", "platform/", "tests/", "docs/", ".github/")

#: The concern register's whole purpose is to name documentation and code that
#: is missing, so its own section is exempt from the path check. Without this,
#: recording a dead path would itself fail the test.
EXEMPT_SECTIONS = ("## Documentation coverage and freshness",)

#: Files this work owns. They must be clean.
OWNED = {"07-MODEL-REGISTRY.md": 0}

#: Paths the #957 frontend split moved to the TeneikaAskew/solyra repository.
#: These are NOT debt — `11-CODE-TRACEABILITY.md` carries a header note saying
#: every `platform/src/**` path "now lives at solyra `src/**`", and the docs cite
#: them deliberately. Counting them as dead paths made a documented convention
#: look like 57 rotting references and buried the handful that are real.
#:
#: The invariant that replaces the count: a doc citing one of these must say
#: where they went (see `test_docs_citing_solyra_paths_explain_the_split`).
SOLYRA_OWNED = ("platform/src", "platform/tests")


def _is_solyra_owned(path: str) -> bool:
    if path.startswith(SOLYRA_OWNED):
        return True
    # Frontend specs: a *.spec.ts without a tests/ or platform/api prefix, per
    # the split note's own wording. `tests/*.spec.ts` moved too.
    return path.endswith((".spec.ts", ".test.ts", ".test.tsx")) and not path.startswith(
        "platform/api/"
    )


#: Genuinely dead paths under docs/product/ — the file is gone and no relocation
#: exists in this repo or in solyra. Measured 2026-09-16 after repointing
#: `gcp/freshness_watchdog.py` (the job runs `scripts/audit_data_freshness.py`,
#: per `gcp/deploy.sh:2471`) and `lib/data_loader` -> `lib/data_loader.py`.
#: These may only go DOWN — the test asserts both directions, so fixing one
#: without lowering its number here also fails.
#: Now an EXCEPTIONS table, not the list of documents that get checked. It
#: used to be both, and naming seven of the sixteen product docs meant the
#: other nine had no dead-path gate at all -- including
#: `08-AI-AGENT-ARCHITECTURE.md`, which carried two dead pointers found only
#: because the parser rewrite happened to print them.
#:
#: Same shape as the scheduler tables in round 10: an allowlist answers "is
#: this entry clean", never "is every entry listed". The parametrisation below
#: now enumerates `docs/product/*.md` and defaults to zero, so a new document
#: is gated the day it lands rather than the day someone remembers to add it.
KNOWN_BACKLOG = {
    "14-WORK-BREAKDOWN.md": 2,
}


def _strip_exempt(text: str) -> str:
    """Drop sections whose job is to name things that do not exist."""
    for heading in EXEMPT_SECTIONS:
        if heading not in text:
            continue
        head, _, rest = text.partition(heading)
        # A section runs to the next heading of the same level.
        level = heading.split(" ", 1)[0]
        nxt = re.search(rf"^{re.escape(level)} ", rest, re.M)
        text = head + (rest[nxt.start():] if nxt else "")
    return text


#: Any backticked token with no whitespace. Deliberately permissive: what the
#: token MEANS is decided afterwards, by `_resolve_pointer`, not by a character
#: class.
#:
#: This has now been the wrong shape twice, the same way both times. The first
#: version's class had no `:`, so `gcp/signal_monitor.py:1107` matched NOTHING --
#: 7 registry pointers silently unchecked while the invariant table published
#: "every repo-rooted path cited here exists". Adding `:\d+` fixed those seven
#: and left FIVE other forms still matching nothing (DOC-45):
#:
#:     gcp/.../strat_walk_forward{,_adaptive}.py   brace expansion  -- 8 files
#:     gcp/research/_archive/p7*.py                glob             -- 9 files
#:     lib/gamma.py::compute_gamma_flip_bs         symbol qualifier -- lib/gamma.py
#:     lib/config.py:SignalConfig                  non-numeric ":"  -- lib/config.py
#:     lib/walk_forward.py:83-97,153-163           comma range      -- lib/walk_forward.py
#:
#: `lib/gamma.py` and `lib/walk_forward.py` were checked by nothing at all.
#: Encoding the accepted forms in the regex means every form it does not
#: anticipate is dropped in silence -- Rule 3.7's forbidden pattern wearing a
#: test's clothes: on input it cannot handle it returns empty and reports
#: success. So the class is now open and unresolvable tokens RAISE.
_POINTER_RE = re.compile(r"`([^`\s]+)`")

#: `:12`, `:12-34`, and the comma-separated form `:83-97,153-163`.
_LINE_SUFFIX_RE = re.compile(r":\d+(?:[-–]\d+)?(?:,\d+(?:[-–]\d+)?)*$")
#: `::symbol` -- e.g. `lib/gamma.py::compute_gamma_flip_bs`.
_SYMBOL_SUFFIX_RE = re.compile(r"::[A-Za-z_][A-Za-z0-9_.]*$")
#: `:Symbol` -- e.g. `lib/config.py:SignalConfig`.
_NAME_SUFFIX_RE = re.compile(r":[A-Za-z_][A-Za-z0-9_.]*$")

#: Characters that mean "this pointer stands for files I cannot enumerate".
#: A brace that survived expansion is unbalanced; an ellipsis is prose.
_UNRESOLVABLE = ("{", "}", "…", "...")

#: Glob metacharacters. `[1-7]` counts, so `phase[1-7]_*.py` resolves.
_GLOB_CHARS = ("*", "?", "[")


class UnresolvablePointer(ValueError):
    """A backticked token looks like a repo path but names no definite files."""


def _strip_suffixes(token: str) -> str:
    """Drop one trailing line-range / symbol qualifier, leaving the file part."""
    for rx in (_LINE_SUFFIX_RE, _SYMBOL_SUFFIX_RE, _NAME_SUFFIX_RE):
        stripped = rx.sub("", token)
        if stripped != token:
            return stripped
    return token


def _expand_braces(token: str) -> list[str]:
    """`a{,_b}.py` -> ['a.py', 'a_b.py']. Empty alternatives are the point."""
    m = re.search(r"\{([^{}]*)\}", token)
    if not m:
        return [token]
    out: list[str] = []
    for alt in m.group(1).split(","):
        out.extend(_expand_braces(token[: m.start()] + alt + token[m.end() :]))
    return out


def _resolve_pointer(raw: str) -> list[str]:
    """One backticked token -> the concrete repo-relative paths it names.

    Returns [] for tokens that are not repo-rooted paths (module references,
    bare filenames, API routes, SQL identifiers) -- those were never in scope.
    A glob that matches nothing returns the glob itself, so it surfaces through
    the normal dead-path assertion rather than vanishing.

    Raises UnresolvablePointer when a token IS repo-rooted but cannot be turned
    into a definite set of files. Silently returning [] there is exactly the
    bug this function was rewritten to fix.
    """
    out: list[str] = []
    for cand in _expand_braces(_strip_suffixes(raw)):
        if not (cand.startswith(ROOTS) and "/" in cand):
            continue
        if any(mark in cand for mark in _UNRESOLVABLE):
            raise UnresolvablePointer(raw)
        if any(ch in cand for ch in _GLOB_CHARS):
            hits = sorted(p.relative_to(REPO).as_posix() for p in REPO.glob(cand))
            out.extend(hits or [cand])
            continue
        out.append(cand)
    return out


def _cited_paths(text: str) -> set[str]:
    paths: set[str] = set()
    for m in _POINTER_RE.finditer(text):
        try:
            paths.update(_resolve_pointer(m.group(1)))
        except UnresolvablePointer:
            continue  # reported by test_doc_pointers_are_all_validatable
    return paths


def _unresolvable_pointers(md: Path) -> set[str]:
    """Repo-rooted tokens this parser refuses to guess at."""
    bad: set[str] = set()
    for m in _POINTER_RE.finditer(_strip_exempt(md.read_text())):
        try:
            _resolve_pointer(m.group(1))
        except UnresolvablePointer as exc:
            bad.add(str(exc))
    return bad


def _dead_paths(md: Path) -> set[str]:
    """Cited repo-rooted paths that do not exist AND are not solyra's."""
    return {
        p
        for p in _cited_paths(_strip_exempt(md.read_text()))
        if not (REPO / p).exists() and not _is_solyra_owned(p)
    }


# ---------------------------------------------------------------- 1. paths --

def test_registry_cites_no_dead_code_path():
    dead = _dead_paths(REGISTRY)
    assert dead == set(), (
        f"{REGISTRY.name} cites paths that do not exist: {sorted(dead)}. "
        "A registry pointing at deleted code is how MODEL-OPT-001 spent months "
        "naming platform/src/lib/greeksCalculator.ts."
    )


def test_model_reference_docs_cite_no_dead_code_path():
    """The eight `docs/models/` references were gated by nothing.

    They are the documents a reader reaches from the registry's `Doc` column,
    and they are the most pointer-dense things in the corpus -- every threshold
    quoted with its `file:line`. Until the path regex learned to strip a `:NN`
    suffix it could not have checked them meaningfully anyway: 16 of their
    pointers carry one, and the old character class had no `:`, so those 16
    matched nothing at all.

    Clean today. This is the gate, not a backlog.
    """
    docs = sorted((REPO / "docs" / "models").glob("MODEL-*.md"))
    assert len(docs) >= 8, f"only {len(docs)} model docs found -- did the folder move?"
    dead = {d.name: sorted(_dead_paths(d)) for d in docs if _dead_paths(d)}
    assert not dead, (
        f"model reference docs cite paths that do not exist: {dead}. These docs "
        "quote thresholds with a file:line; a stale pointer makes a quoted "
        "constant unverifiable."
    )


def test_doc_pointers_are_all_validatable():
    """No repo-rooted pointer may use shorthand the gate cannot resolve.

    The companion to the parser rewrite. Braces and globs are EXPANDED, so
    `strat_walk_forward{,_adaptive}.py` and `p7*.py` are fine and every file
    they name is checked. Anything left -- an unbalanced brace, an ellipsis
    standing in for a range -- is rejected with its pointer named, because the
    alternative is the behaviour that caused DOC-45: quietly checking nothing
    and reporting success.

    `scripts/analysis/phase1…phase7` was the only instance, and it is exactly
    the shape the rule is about: seven real files, named in prose, validated by
    nothing. It is now `scripts/analysis/phase[1-7]_*.py`, which resolves.
    """
    docs = sorted(PRODUCT.glob("*.md")) + sorted((REPO / "docs" / "models").glob("*.md"))
    bad = {md.name: sorted(_unresolvable_pointers(md)) for md in docs if _unresolvable_pointers(md)}
    assert not bad, (
        f"pointers the path gate cannot validate: {bad}. Rewrite each as a plain "
        "path, a brace group, or a glob -- any of which the parser expands and "
        "checks. A pointer no gate can read is a pointer no gate is checking."
    )


@pytest.mark.parametrize("name", sorted(p.name for p in PRODUCT.glob("*.md")))
def test_known_dead_path_backlog_only_shrinks(name):
    expected = KNOWN_BACKLOG.get(name, 0)
    actual = len(_dead_paths(PRODUCT / name))
    assert actual <= expected, (
        f"{name} gained dead paths ({actual} > {expected}). Fix the path, or if "
        "the file it names is genuinely gone, say so in the concern register."
    )
    assert actual == expected, (
        f"{name} now has {actual} dead paths, fewer than the pinned {expected}. "
        f"Lower KNOWN_BACKLOG['{name}'] to {actual} so the gain is locked in."
    )


# ---------------------------------------------------------------- 2. links --

def test_product_docs_have_no_dead_relative_links():
    """Both `docs/product/` and `docs/models/`.

    It globbed `docs/product/*.md` only, which left the directory the registry's
    `Doc` column sends every reader to with no link gate at all. That is how
    `MODEL-WEEK-001.md` shipped a link to `MODEL-IND-001.md`, a file that has
    never existed -- MODEL-IND-001 is a registry row, not a reference document.
    DOC-46.

    The gate was named for the directory it happened to check rather than the
    invariant it claims, which is the same reason it was never noticed.
    """
    roots = [PRODUCT, REPO / "docs" / "models"]
    broken = []
    for root in roots:
        for md in sorted(root.glob("*.md")):
            for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", md.read_text()):
                target = urllib.parse.unquote(m.group(2).split("#")[0])
                if not target or target.startswith(("http://", "https://", "mailto:")):
                    continue
                if not (md.parent / target).exists():
                    broken.append(f"{root.name}/{md.name} -> {target}")
    assert broken == [], f"dead relative links: {broken}"


def test_scheduler_enumeration_matches_the_canonical_parser():
    """All three scheduler parsers must agree, because they are now one.

    This PR ran four parsers of `gcp/deploy.sh` at various points, and they
    disagreed every time somebody checked:

        doc_inventory.deploy_schedulers   66   both declaration forms
        audit_scheduler_coverage          63   `_schedule*` helpers only
        this file's _declared_schedulers  63   `_schedule*` helpers only

    The two that agreed were agreeing about the same blind spot, which reads
    exactly like corroboration. Three schedulers were in neither registry
    table while both gates reported complete coverage -- and two of them run
    model-producing jobs (DOC-48).

    Both now delegate to `doc_inventory`. This gate is what stops a fourth
    from being written: reintroduce a hand-rolled parse anywhere and the sets
    stop matching here.
    """
    sys.path.insert(0, str(REPO / "scripts" / "maintenance"))
    sys.path.insert(0, str(REPO / "scripts"))
    from audit_scheduler_coverage import resolve_schedulers
    from doc_inventory import deploy_schedulers

    canonical = {d["name"] for d in deploy_schedulers(REPO)}
    mine = set(_declared_schedulers())
    audit = set(resolve_schedulers(DEPLOY.read_text()))

    assert mine == canonical, (
        f"this file's enumeration disagrees with doc_inventory. "
        f"missing here: {sorted(canonical - mine)}; extra here: {sorted(mine - canonical)}"
    )
    assert audit == canonical, (
        f"audit_scheduler_coverage disagrees with doc_inventory. "
        f"missing there: {sorted(canonical - audit)}; extra there: {sorted(audit - canonical)}"
    )
    assert len(canonical) >= 66, (
        f"only {len(canonical)} schedulers parsed — deploy.sh declared 66 on "
        "2026-09-22, so a sharp drop means a declaration form stopped matching"
    )


# ------------------------------------------------- 2b. test-coverage claims --
#
# This PR's own description said "what the suite cannot check is whether a
# document's prose matches the code it describes". That is true of prose about
# BEHAVIOUR. It is not true of claims about TEST COVERAGE, which are three
# mechanical questions: does the cited file exist, does it reference the module,
# and if the doc says no test exists, does a search agree. Round 14 found five
# wrong coverage claims across fifteen documents (DOC-44) under the shelter of
# that sentence. These two gates are what it was excusing.

MODELS = REPO / "docs" / "models"

#: The `**Code:**` field of a model reference doc's header, up to the next
#: `**Field:**` marker. The header wraps, so this cannot be line-anchored.
_CODE_FIELD_RE = re.compile(r"\*\*Code:\*\*(.*?)(?=\*\*[A-Z][A-Za-z ]*:\*\*)", re.S)

#: The exact sentence the wrong documents used. Matched literally rather than
#: fuzzily: a gate that guesses at prose is a gate nobody can predict.
_NO_TEST_CLAIM = "No test file targets this module"


def _model_code_paths(md: Path) -> list[str]:
    """Existing repo paths named in the document's `**Code:**` header field."""
    m = _CODE_FIELD_RE.search(md.read_text())
    if not m:
        return []
    return [
        t
        for t in (_strip_suffixes(x) for x in re.findall(r"`([^`\s]+)`", m.group(1)))
        if "/" in t and (REPO / t).exists()
    ]


def _tests_section(md: Path) -> str:
    text = md.read_text()
    if "## Tests" not in text:
        return ""
    return text.split("## Tests", 1)[1].split("\n## ", 1)[0]


def _claims_no_test(md: Path) -> bool:
    """Whether the doc ASSERTS that nothing tests its module.

    Blockquoted lines are excluded. Each corrected section now carries a
    `> Until 2026-09-22 this section read ...` note quoting the wrong claim
    verbatim, and a record of a retracted claim is not a claim. Scoping to the
    `## Tests` section body rather than the whole file also stops a passing
    mention elsewhere from tripping the gate.
    """
    return any(
        _NO_TEST_CLAIM in line
        for line in _tests_section(md).splitlines()
        if not line.lstrip().startswith(">")
    )


def _cited_test_files(md: Path) -> list[str]:
    """`tests/...` paths named in the doc's `## Tests` section.

    Honours the section's own shorthand, where a bare filename inherits the
    directory of the last full path: `tests/lib/test_a.py` · `test_b.py`.
    """
    # Blockquoted lines are history, not citation -- each corrected section
    # quotes the wrong file it used to name, and re-reading that as a live
    # citation would make the correction fail the gate it was made to satisfy.
    section = "\n".join(
        line for line in _tests_section(md).splitlines() if not line.lstrip().startswith(">")
    )
    out, last_dir = [], None
    for tok in re.findall(r"`([^`\s]+)`", section):
        tok = _strip_suffixes(tok)
        if "/" in tok:
            last_dir = tok.rsplit("/", 1)[0] + "/"
            cand = tok
        elif last_dir and tok.endswith(".py"):
            cand = last_dir + tok
        else:
            continue
        # `.py` guard: the section also names the directory in prose ("the only
        # file under `tests/`"), and a bare directory is not a citation.
        if cand.startswith("tests/") and cand.endswith(".py"):
            out.append(cand)
    return out


def _test_files_importing(module_path: str) -> list[str]:
    """Every file under tests/ that IMPORTS the given module.

    Import, not mention, is the discriminator, and the distinction is the whole
    gate. `MODEL-EWV-001` correctly says no test targets
    `gcp/fetchers/evaluate_ew_strikes.py` while the name appears in a docstring
    in `test_premarket_brief.py`; a content grep calls that document a liar. An
    import check agrees with it, and still catches `weekend_review` and
    `earnings_long_watchlist`, which are imported outright.
    """
    parts = Path(module_path).with_suffix("").parts
    dotted, pkg, name = ".".join(parts), ".".join(parts[:-1]), parts[-1]
    pats = [
        rf"^\s*from\s+{re.escape(dotted)}\b",
        rf"^\s*import\s+{re.escape(dotted)}\b",
        rf"^\s*from\s+{re.escape(pkg)}\s+import\s+[^\n]*\b{re.escape(name)}\b",
    ]
    return [
        t.relative_to(REPO).as_posix()
        for t in sorted((REPO / "tests").rglob("test_*.py"))
        if any(re.search(p, t.read_text(), re.M) for p in pats)
    ]


def test_cited_test_files_cover_the_model():
    """A cited test file must reference the model it is cited under.

    `MODEL-CALIB-001` and `MODEL-PLAY-001` both carried the identical sentence
    "`tests/scripts/test_scripts.py` covers the CLI surface." Neither model is
    mentioned in that file. Both live under `scripts/`, so a file named
    `test_scripts.py` was assumed to cover them and never opened -- the same
    move as citing a module docstring instead of reading the scoring function,
    which is what rounds 3 and 4 were about.

    Meanwhile the real suites -- 28 tests for the calibrator, 23 across two
    files for the playbook -- went uncredited, so the documents understated
    coverage and misdirected anyone looking for it in one stroke.
    """
    offenders = {}
    for md in sorted(MODELS.glob("MODEL-*.md")):
        stems = [Path(c).stem for c in _model_code_paths(md)]
        if not stems:
            continue
        for tf in _cited_test_files(md):
            path = REPO / tf
            if not path.exists():
                offenders[f"{md.name} -> {tf}"] = "file does not exist"
            elif not any(s in path.read_text() for s in stems):
                offenders[f"{md.name} -> {tf}"] = f"references none of {stems}"
    assert not offenders, (
        f"model docs cite test files that do not cover them: {offenders}. Name "
        "the suite that actually imports the module, or say plainly that none does."
    )


def test_every_model_doc_states_its_test_surface():
    """A `## Tests` section must name a file or say plainly that none exists.

    The third failure mode, and the quietest. `MODEL-QUAL-001` called the pure
    helpers "the stated unit-test surface" and named **no file**, while
    `tests/scripts/test_signal_quality_report.py` (50 tests, importing
    `CLEAN_THRESHOLD`, `NOISE_THRESHOLD` and `classify` by name) and
    `tests/scripts/test_signal_quality_alarm.py` (20 tests) both target it.

    Neither of the other two gates could see it: nothing was cited, so there was
    nothing to check, and no claim was made, so there was nothing to refute.
    Saying nothing is how a coverage claim avoids being wrong without becoming
    right.
    """
    silent = [
        md.name
        for md in sorted(MODELS.glob("MODEL-*.md"))
        if "## Tests" in md.read_text()
        and not _cited_test_files(md)
        and not _claims_no_test(md)
    ]
    assert not silent, (
        f"model docs whose Tests section names no file and makes no explicit "
        f"'{_NO_TEST_CLAIM}' claim: {silent}. An unstated test surface reads as "
        "'none' and is not checkable either way."
    )


def test_no_test_claims_are_true():
    """"No test file targets this module" must survive a search.

    `MODEL-WEEK-001` and `MODEL-WATCH-001` both said it; both were wrong. In
    each case the real test lives in a file whose NAME does not contain the
    module name -- `test_trade_logger_reads.py` and a `_freshness` suffix -- so
    a filename glob misses it and a content grep finds it at once. I evidently
    looked for the former.

    `MODEL-WATCH-001` went further and justified the absence: a test "would need
    a real or fixture database; none exists." The suite that exists monkeypatches
    `get_engine` and needs no database, so the reasoning was refuted by the file
    it was written to explain away.
    """
    offenders = {}
    for md in sorted(MODELS.glob("MODEL-*.md")):
        if not _claims_no_test(md):
            continue
        for code in _model_code_paths(md):
            importers = _test_files_importing(code)
            if importers:
                offenders[f"{md.name} ({code})"] = importers
    assert not offenders, (
        f"docs claim no test targets a module that tests import: {offenders}. "
        "Name the suite and narrow the claim to what is genuinely uncovered, as "
        "MODEL-EWV-001 does when it separates the consumer test from the derivation."
    )


_NUMBER_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
    8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
    14: "fourteen", 15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
    19: "nineteen", 20: "twenty",
}


def _registry_model_ids() -> list[str]:
    """Ids in the two non-LLM inventory tables.

    Anchored on the closing cell pipe with a LAZY capture. The shape used
    elsewhere in this file, `MODEL-[A-Z-]+(?:-[0-9X]+)?`, is only correct
    because its callers happen to follow it with ` \\|`: on its own the greedy
    `[A-Z-]+` swallows the hyphen and both `MODEL-EARN-001` and
    `MODEL-EARN-002` capture as `MODEL-EARN-`, collapsing to one id in a set.
    Found while writing the gate below, which counted 28 models instead of 29.
    """
    text = REGISTRY.read_text()
    ids: list[str] = []
    for table in ("## Deterministic and heuristic systems", "## Learned models"):
        body = text.split(table, 1)[1].split("\n##", 1)[0]
        ids += [m.group(1) for m in re.finditer(r"^\| \**(MODEL-[A-Z0-9X-]+?)\**\s*\|", body, re.M)]
    return ids


def test_open_decisions_coverage_row_matches_the_registry():
    """The model-documentation decision row must agree with what it links to.

    Every number in it was wrong (DOC-47). It claimed "a reference doc per
    model" against 29 models and 15 files; it said "seven models are absent
    from the master matrix" while **linking to DOC-11**, which says fourteen
    and records the 9 -> 14 recomputation that made it fourteen; and it called
    MODEL-EARN-001 the exception to the `UNKNOWN` rationale although that
    document records its `window_days + 5` as "not recorded anywhere".

    All of it sat beside a disclaimer reading *"No bare count is published
    here"*, added after DOC-28 for exactly this reason, in the same sentence as
    two bare counts. A warning is not a gate, which is why this is one.
    """
    decisions = PRODUCT / "15-OPEN-DECISIONS.md"
    row = next(
        line for line in decisions.read_text().splitlines()
        if line.startswith("| Model documentation ownership |")
    )
    models = set(_registry_model_ids())
    documented = {p.stem for p in MODELS.glob("MODEL-*.md")}
    undocumented = models - documented

    # Each claim is matched as its OWN clause, not as a substring of the row.
    # The first version of this gate searched the whole row, and two of its
    # three mutations passed: the row legitimately repeats "fourteen" and
    # "MODEL-STRAT-001" in the correction note, so deleting the real claim left
    # the search satisfied. A substring check over long prose is the vacuous
    # gate this round is about, caught here by mutations that refused to go red.
    assert re.search(
        rf"reference doc for \*\*{len(documented)} of the {len(models)}\*\* models", row
    ), (
        f"the row must state the measured coverage as '**{len(documented)} of the "
        f"{len(models)}** models'. Counting is what it got wrong four ways."
    )

    listed_here = re.search(rf"The {len(undocumented)} without one: (.+?)\.\s", row)
    assert listed_here, (
        f"the row must enumerate the {len(undocumented)} undocumented models as "
        f"'The {len(undocumented)} without one: ...'"
    )
    named = set(re.findall(r"MODEL-[A-Z0-9X-]+", listed_here.group(1)))
    assert named == undocumented, (
        f"the row's undocumented list disagrees with the filesystem. "
        f"missing from the row: {sorted(undocumented - named)}; "
        f"named but documented: {sorted(named - undocumented)}"
    )

    # DOC-11 owns the master-matrix number; this row cites DOC-11 as evidence,
    # so it may not disagree with it.
    doc11 = next(line for line in REGISTRY.read_text().splitlines() if line.startswith("| DOC-11 |"))
    # Only the bolded list. The rest of the row names further ids in its
    # recomputation note, and counting those gave 19 instead of 14.
    listed = re.search(r"Absent:\s*\*\*(.+?)\*\*", doc11)
    assert listed, "DOC-11 no longer carries a bolded 'Absent: **...**' list"
    absent = re.findall(r"MODEL-[A-Z0-9X-]+", listed.group(1))
    word = _NUMBER_WORDS[len(absent)]
    assert re.search(rf"\*\*{word}\*\* models are absent from the master matrix", row), (
        f"DOC-11 lists {len(absent)} models absent from the master matrix, so "
        f"this row must say '**{word}** models are absent from the master matrix'. "
        "It said seven while linking to DOC-11 as its own evidence."
    )


# ------------------------------------------------------- 3. ids + schedule --

def test_model_ids_are_globally_unique_across_the_inventory():
    """Aggregated, not per-table. Resetting the set for each table let the same
    id appear once under deterministic systems and once under learned models
    undetected — the exact cross-section ambiguity this gate exists to prevent.
    The LLM table is included; it was not examined at all before."""
    text = REGISTRY.read_text()
    ids: list[str] = []
    for table in ("## Deterministic and heuristic systems", "## Learned models", "## LLM nodes"):
        body = text.split(table, 1)[1].split("\n##", 1)[0]
        ids += re.findall(r"^\| (MODEL-[A-Z-]+(?:-[0-9X]+)?) \|", body, re.M)
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"ids appearing in more than one inventory table: {sorted(dupes)}"
    assert len(ids) >= 20, f"only {len(ids)} ids parsed — did a table's shape change?"


def _declared_schedulers() -> dict[str, tuple[str, str]]:
    """name -> (cron, target job or service), from the CANONICAL parser.

    This used to hand-roll the parse and was the SECOND of what became four
    parsers of `gcp/deploy.sh` in this PR. It recognised only `_schedule*`
    helpers, so three schedulers declared with a raw
    `gcloud scheduler jobs create http` were invisible to it --
    `reconcile-failure-notifier-hourly`, `strat-enrich-daily` and
    `backfill-indicators-weekly`. Two of those invoke model-producing jobs, and
    all three were in NEITHER registry table while
    `test_every_live_scheduler_is_classified` reported full coverage: a
    completeness check over an incomplete enumeration is a check over nothing.
    DOC-48.

    `scripts/maintenance/doc_inventory.py` already handled both declaration
    forms and reported 66 where this said 63. It is now the single source, as
    `scripts/audit_scheduler_coverage.py` also is, so a disagreement between
    the audit and this gate is no longer possible by construction.

    Commented-out declarations stay excluded -- `deploy.sh` carries a disabled
    `p7b-classifier-daily` -- which the canonical parser already handles by
    anchoring its match at line start.
    """
    sys.path.insert(0, str(REPO / "scripts" / "maintenance"))
    from doc_inventory import deploy_schedulers

    sys.path.insert(0, str(REPO / "scripts"))
    from audit_scheduler_coverage import _service_url_vars, _shell_vars

    text = DEPLOY.read_text()
    urls = _service_url_vars(text, _shell_vars(text))

    out: dict[str, tuple[str, str]] = {}
    for d in deploy_schedulers(REPO):
        target = d["target_job"] or d["target_service"]
        if not target and d["target_uri"]:
            var = re.match(r"\$\{?(\w+)\}?", d["target_uri"])
            target = urls.get(var.group(1), "") if var else ""
        assert target, (
            f"scheduler {d['name']!r} has no resolvable target "
            f"(uri={d['target_uri']!r}) -- teach the resolver, do not drop it"
        )
        out[d["name"]] = (d["cron"], target)
    return out
def _run_section() -> str:
    return REGISTRY.read_text().split("### Which of these actually run", 1)[1].split("\n###", 1)[0]


def test_scheduler_table_matches_deploy_sh():
    declared = _declared_schedulers()
    rows = re.findall(r"^\| `([a-z0-9-]+)` \| `([^`]+)` \| `([a-z0-9-]+)` \|", _run_section(), re.M)
    assert rows, "no scheduler rows parsed — did the table shape change?"
    for name, cron, job in rows:
        assert name in declared, f"{name} is not declared in gcp/deploy.sh"
        assert declared[name] == (cron, job), (
            f"{name}: registry says {(cron, job)}, deploy.sh says {declared[name]}"
        )


def test_jobs_claimed_unscheduled_really_are():
    section = _run_section()
    tail = section.split("are deployed but", 1)[0].rsplit("|", 1)[-1]
    claimed = set(re.findall(r"`([a-z0-9-]+)`", tail))
    targets = {job for _, job in _declared_schedulers().values()}
    wrong = claimed & targets
    assert not wrong, (
        f"claimed unscheduled but declared on a cron in gcp/deploy.sh: {sorted(wrong)}. "
        "This is the gamma-levels-daily error."
    )


def test_scheduler_table_has_no_count_to_drift():
    """The count sentence is deliberately gone; assert it stays gone.

    It was published as `eight`, corrected to `fourteen`, and was still wrong,
    because it was derived by hand from a rule that also catches every fetcher
    importing a `lib/` helper. Two wrong counts in two rounds: the list is the
    deliverable, and a number over it is a liability. The rows themselves are
    checked against deploy.sh by test_scheduler_table_matches_deploy_sh.
    """
    section = _run_section()
    stated = re.search(
        r"\b(six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|\d+)\s+"
        r"(?:model-bearing\s+jobs|scheduler entries)", section, re.I)
    assert not stated, (
        f"a count of scheduled jobs is back in the section: {stated.group(0)!r}. "
        "This number has been wrong twice; publish the list, not a total."
    )
    rows = re.findall(r"^\| `[a-z0-9-]+` \| `[^`]+` \| `[a-z0-9-]+` \|", section, re.M)
    assert len(rows) >= 10, f"only {len(rows)} scheduler rows parsed — did the table change?"


# ------------------------------------------------------- 4. count safety ----

def test_declared_job_count_is_accurate_and_daily_job_safe():
    """The count must be right AND phrased so verify_docs_against_live won't
    read it as a live-fleet claim. `declared` is that checker's own subset cue
    (SUBSET_AFTER); without it a correct declared count fails against live."""
    declared_jobs = len(
        set(re.findall(r"gcloud run jobs (?:deploy|create|update) ([a-z0-9-]+)", DEPLOY.read_text()))
        - {"leaves"}  # a word in a comment, not a job
    )
    for m in re.finditer(r"(\d+) Cloud Run Jobs(\s+\w+)?", REGISTRY.read_text()):
        assert int(m.group(1)) == declared_jobs, (
            f"registry claims {m.group(1)} Cloud Run Jobs; gcp/deploy.sh declares {declared_jobs}"
        )
        assert (m.group(2) or "").strip() == "declared", (
            "a bare 'N Cloud Run Jobs' is compared against the LIVE fleet by "
            "scripts/verify_docs_against_live.py and will fail its daily run. "
            "Write 'N Cloud Run Jobs declared in ...'."
        )


# --------------------------------------------------------- 5. vocabulary ----

def _vocab(pattern: str) -> set[str]:
    readme = (PRODUCT / "README.md").read_text()
    m = re.search(pattern, readme)
    assert m, f"governance contract no longer declares {pattern!r}"
    return {v.strip().strip("`") for v in m.group(1).split("·") if v.strip()}


#: Every table in the registry carrying `MODEL-*` rows, and which cell holds
#: Status. The LLM table is five columns wide, the other two are nine, which is
#: why a single index cannot cover them -- and why the first version simply left
#: the LLM table out and checked two thirds of the inventory while the registry
#: published one vocabulary for the whole of it.
STATUS_COLUMN = {
    "## Deterministic and heuristic systems": 6,
    "## Learned models": 6,
    # 6, not 5: the LLM table gained a Code column on 2026-09-18. Until then it
    # was the only MODEL-* table without one, which is why the completeness gate
    # could not see `insight-pipeline` -- its rule is "executes code cited in a
    # MODEL-* row", and no LLM row cited any code. The one pointer that existed,
    # `orchestrator.py:490-492`, sat in the Numeric authority prose.
    "## LLM nodes": 6,
}


def test_status_cells_use_the_declared_vocabulary():
    allowed = _vocab(r"\*\*Model status:\*\*([^\n]*(?:\n[^\n*]*)*?)\.")
    text = REGISTRY.read_text()
    bad, checked = [], 0
    for table, col in STATUS_COLUMN.items():
        assert table in text, f"registry no longer has the table {table!r}"
        for line in text.split(table, 1)[1].split("\n##", 1)[0].split("\n"):
            if not re.match(r"^\| MODEL-", line):
                continue
            cells = [c.strip() for c in line.split("|")]
            checked += 1
            status = cells[col].strip("* ").split(" — ")[0].strip("* ")
            if status not in allowed:
                bad.append(f"{cells[1]}: {status!r}")
    assert checked >= 29, (
        f"only {checked} model rows read across {len(STATUS_COLUMN)} tables -- a "
        "column index or a heading has drifted, and a status check that reads "
        "nothing passes."
    )
    assert not bad, f"status values outside the README vocabulary: {bad} (allowed: {sorted(allowed)})"


def _expand_doc_ranges(cell: str) -> set[str]:
    """`DOC-01…DOC-05` names five concerns, not two.

    Same defect as `_expand_experiment_ranges`, in a table written one commit
    later: `re.findall` keeps the endpoints, so DOC-02, DOC-03 and DOC-04 sat
    outside the disposition invariant the moment it was added. The data builder
    that feeds the design board expanded the range correctly; the test did not,
    which is the difference between a document that renders right and a contract
    that holds.
    """
    ids = re.findall(r"DOC-\d+", cell)
    if ids and ("…" in cell or "..." in cell):
        lo, hi = int(ids[0].split("-")[1]), int(ids[-1].split("-")[1])
        return {f"DOC-{n:02d}" for n in range(lo, hi + 1)}
    return set(ids)


def test_concern_ids_are_unique():
    """One DOC id, one finding.

    The merge of two parallel fixes renumbered one row onto an id the other
    side already used, so DOC-23 named both the earnings-archetype divergence
    and the mean-reversion duplicate, and two model docs cited the same id for
    different things. `test_every_non_current_doc_cell_names_a_finding` missed
    it because it collects ids into a SET -- a duplicate is invisible to
    membership. This PR exists because of E-24/E-25 collisions in the
    experiment ledger; committing one in its own register is the same defect.
    """
    text = REGISTRY.read_text()
    findings = text[text.index("### Findings"):text.index("### Disposition")]
    ids = re.findall(r"^\|\s*(DOC-\d+)", findings, re.M)
    assert len(ids) >= 20, f"only {len(ids)} findings parsed -- did the table change shape?"
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert not dupes, f"the same DOC id names more than one finding: {dupes}"


def test_every_disposition_row_is_inside_the_disposition_table():
    """A `DOC-nn` disposition below the paragraph that ends the table.

    This has now happened twice — DOC-35..37 on 2026-09-21 and DOC-38..41 on
    2026-09-22 — because appending "before the next heading" lands after the
    prose that closes the table, where a row renders as loose text. Both times
    it was caught by the design board's data builder refusing to find a
    disposition, never by this suite: `test_no_concern_carries_two_different_
    dispositions` and friends search the whole SECTION, so a row outside the
    table still reads as present.

    The fix is to check position, not presence: every `| DOC-nn |` line in the
    Disposition section must sit in the contiguous run of table rows.
    """
    text = REGISTRY.read_text()
    section = text.split("### Disposition", 1)[1].split("\n###", 1)[0]
    lines = section.split("\n")

    rows = [n for n, l in enumerate(lines) if re.match(r"^\| DOC-\d+ \|", l)]
    assert len(rows) >= 10, (
        f"only {len(rows)} disposition rows parsed -- the section shape has "
        "drifted and this test would check nothing."
    )
    # The table is the run starting at its header separator; anything after a
    # blank line that follows the last contiguous row is outside it.
    first = rows[0]
    contiguous = {first}
    for n in rows[1:]:
        if all(lines[k].startswith("|") for k in range(max(contiguous) + 1, n + 1)):
            contiguous.add(n)
    orphans = [lines[n].split("|")[1].strip() for n in rows if n not in contiguous]
    assert not orphans, (
        f"disposition rows sit outside the table, after the prose that ends it: "
        f"{orphans}. They render as loose text and the concern-data builder "
        "cannot find them. Insert after the last existing row, not before the "
        "next heading."
    )


def test_no_concern_carries_two_different_dispositions():
    """One DOC id, one verdict.

    The first version of `test_concern_ids_are_unique` stopped at the Findings
    table, so the same renumbering that produced the DOC-23 collision left
    DOC-24 with TWO disposition rows giving different verdicts -- "FIXED HERE
    in the doc, FLAGGED at source" and "FLAGGED -- needs a code fix" -- and the
    green suite said nothing. Gating half a table is how the first collision
    survived; this is the other half.

    Repeating an id across rows is allowed, because DOC-13 legitimately has a
    registry half labelled in place and a path half repointed. What is not
    allowed is two rows disagreeing about what was DONE, which is what a reader
    consumes the column for.
    """
    text = REGISTRY.read_text()
    disposition = text[text.index("### Disposition"):text.index("Merged-PR lineage")]
    verdicts: dict[str, set[str]] = {}
    for line in disposition.split("\n"):
        if not re.match(r"^\|\s*DOC-", line):
            continue
        cells = [c.strip() for c in line.split("|")]
        # leading bolded token of the Disposition cell, e.g. **FIXED HERE**
        head = re.match(r"\*\*(.+?)\*\*", cells[2])
        assert head, f"disposition cell does not open with a bolded verdict: {cells[2]!r}"
        for cid in _expand_doc_ranges(cells[1]):
            verdicts.setdefault(cid, set()).add(head.group(1).strip())
    assert len(verdicts) >= 25, f"only {len(verdicts)} ids parsed -- did the table change shape?"
    split = {k: sorted(v) for k, v in verdicts.items() if len(v) > 1}
    assert not split, f"the same DOC id carries conflicting dispositions: {split}"


def test_doc_health_cells_use_the_declared_vocabulary():
    allowed = {"CURRENT", "UNVERIFIED", "CONTRADICTED", "NONE"}
    text = REGISTRY.read_text()
    bad = []
    for table in ("## Deterministic and heuristic systems", "## Learned models"):
        for line in text.split(table, 1)[1].split("\n##", 1)[0].split("\n"):
            if not re.match(r"^\| MODEL-", line):
                continue
            cells = [c.strip() for c in line.split("|")]
            token = cells[8].split("·")[0].strip("* ")
            if token not in allowed:
                bad.append(f"{cells[1]}: {token!r}")
    assert not bad, f"Doc values outside the declared vocabulary: {bad}"


def test_every_non_current_doc_cell_names_a_finding():
    text = REGISTRY.read_text()
    register = set(re.findall(r"\| (DOC-\d+) \|", text))
    assert register, "the concern register has no findings — did the table shape change?"
    missing = []
    for table in ("## Deterministic and heuristic systems", "## Learned models"):
        for line in text.split(table, 1)[1].split("\n##", 1)[0].split("\n"):
            if not re.match(r"^\| MODEL-", line):
                continue
            cells = [c.strip() for c in line.split("|")]
            doc = cells[8]
            if doc.split("·")[0].strip("* ") == "CURRENT":
                continue
            cited = set(re.findall(r"(DOC-\d+)", doc))
            if not cited:
                continue  # UNVERIFIED without a specific finding is allowed
            unknown = cited - register
            if unknown:
                missing.append(f"{cells[1]} cites {sorted(unknown)}")
    assert not missing, f"Doc cells cite findings that are not in the register: {missing}"


# --------------------------------------------------------- 6. freshness -----

def test_last_reviewed_is_not_older_than_the_body():
    """Catches a doc edited without advancing its own stamp — the defect the
    first commit of this branch introduced. Purely local: no git, so it works
    in a shallow CI checkout where every file has exactly one commit."""
    text = REGISTRY.read_text()
    m = re.search(r"\*\*Last reviewed:\*\* (\d{4}-\d{2}-\d{2})", text)
    assert m, "the registry lost its Last reviewed stamp"
    stamp = _dt.date.fromisoformat(m.group(1))
    body = text[m.end():]
    dates = [_dt.date.fromisoformat(d) for d in re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", body)]
    future = [d for d in dates if d > stamp]
    assert not future, (
        f"Last reviewed is {stamp} but the body cites later dates {sorted(set(future))}. "
        "Advance the stamp when you edit the document."
    )


# ------------------------------------------------- 7. offline issue proxy ---

def test_cited_issues_also_appear_in_pr_issue_traceability():
    """Issue open/closed state needs the network. What IS checkable offline is
    that the registry has not drifted away from the reconciled issue map in 12,
    which is refreshed against GitHub on its own cadence."""
    def issues(p: Path) -> set[str]:
        return set(re.findall(r"/issues/(\d+)", p.read_text()))

    orphans = issues(REGISTRY) - issues(PRODUCT / "12-PR-ISSUE-TRACEABILITY.md")
    assert not orphans, (
        f"issues cited by the registry but absent from 12-PR-ISSUE-TRACEABILITY.md: "
        f"{sorted(orphans, key=int)}. 12 owns the issue map; either it needs a refresh "
        "or the registry is citing something that no longer belongs to a capability."
    )


# ------------------------------------------- 8. the experiment-to-model join --
#
# Three review findings on PR #1111 were all one defect class: an experiment's
# evidence attached to fewer models than the ledger says it covers, or artifacts
# cited for an experiment the ledger says was never committed. Specifically:
#
#   * E-23 tested MODEL-TYPE-001's own 0.55-confidence calls and returned 0/8
#     positive-expectancy folds, but was filed as belonging to no model — so the
#     TYPE row showed its prediction success and hid its execution failure.
#   * E-19 is `Engine/area: both (integrity)` and was on MAG only, so the
#     leakage audit underwriting the TYPE verdict was missing from TYPE.
#   * E-26/E-31/E-33 sat beside committed module paths although the ledger
#     records them as a scratch harness "not committed to the repo".
#
# The ledger states each experiment's scope in a fixed field, so the join is
# checkable rather than a matter of care. Writing these invariants found a
# fourth instance unprompted: E-20 is `both (calibration)` with artifacts in
# `strat_config.py` AND `mag_config.py`, and was on TYPE only.

LEDGER = REPO / "docs" / "EXPERIMENT_REGISTRY.md"

#: Ledger sections whose shape `_ledger_engine_area()` cannot parse because they
#: are session blocks or tables rather than `## E-nn` entries with an immediate
#: `- **Engine/area:**` line. The first version of this list was a frozenset
#: that `continue`d past every id in it -- so the allowlist replaced a silent
#: skip on unknown ids with a silent skip on every KNOWN exceptional id, and
#: adding E-34 to MODEL-TYPE-001 passed although the ledger describes E-34 as
#: direction and size work. Each id now carries the scope the ledger's prose
#: states, so it goes through the same family check as a parsed entry.
#:
#: Scopes are read from `docs/EXPERIMENT_REGISTRY.md`, not inferred:
#:   * E-24 (`:637`) is the strat_features column audit + gamma rename, fixes
#:     consumed by both engines and the gamma model -- cross-cutting.
#:   * E-26..E-31, E-33 are the 2026-07-06 session (`:1190`). Its table scores
#:     EXPLOSIVE-bucket precision (the magnitude target) for E-26, E-27, E-28,
#:     E-29, E-31 and E-33; E-30 is the single-bar call/put probe, which the
#:     reconciliation (`:1245`) says "re-tread[s] the direction program".
#:   * E-34 (`:1266`) is the direction program's Phase 2, whose baseline anchor
#:     scores TYPE, SIZE and DIRECTION; the registry cites its SIZE arm on MAG.
#: Values are SETS, not strings. A string scope was matched with `startswith`,
#: which made `both` an unrestricted wildcard -- E-34 satisfied the check on
#: MODEL-TYPE-001, an engine it does not name. A set makes the test membership,
#: and every engine named must own the experiment.
LEDGER_SCOPE_OVERRIDES: dict[str, set] = {
    "E-24": set(),                              # cross-cutting (data quality)
    "E-26": {"magnitude"},                      # vol-regime features
    "E-27": {"magnitude"},                      # time-of-day features
    "E-28": {"magnitude"},                      # forward-window range
    "E-29": {"magnitude"},                      # regression head
    "E-30": {"direction"},                      # single-bar excursion
    "E-31": {"magnitude"},                      # external-data joins
    "E-33": {"magnitude"},                      # feature-family ablation
    "E-34": {"direction", "magnitude"},         # Phase 2; SIZE arm cited on MAG
}

#: Which model owns each engine. A multi-engine experiment must appear on EVERY
#: owner, which is what makes a two-engine scope a requirement, not a wildcard.
ENGINE_OWNER = {
    "strat": "MODEL-TYPE-001",
    "magnitude": "MODEL-MAG-001",
    "direction": "MODEL-DIR-001",
}


def _engines(area) -> set:
    """An Engine/area value -> the set of engines it names.

    The engine is the LEADING token, before any parenthetical: a first pass
    scanned the whole string and read "magnitude (directional)" as two engines
    and "strat (direction / next-candle)" likewise. The parenthetical qualifies
    the work; it does not name a second owner.
    """
    if isinstance(area, (set, frozenset)):
        return set(area)
    head = re.split(r"[(/]", str(area).lower(), 1)[0].strip()
    if head.startswith("both"):
        return {"strat", "magnitude"}
    return {e for e in ENGINE_OWNER if head.startswith(e)}

#: An experiment id, and NOT the tail of a model id.
#:
#: `re.findall(r"E-\d+", "MODEL-AGREE-001")` returns `["E-001"]`. So does
#: MODEL-TYPE-001 and MODEL-STYLE-001. The ownerless table's E-23 row names
#: MODEL-TYPE-001 in its prose, so a phantom `E-001` was already sitting in the
#: parsed ownerless set -- invisible while the coverage assertion only ran
#: `ledger - owned - ownerless`, and a guaranteed false failure the moment that
#: assertion was made two-directional. The lookbehind is the whole fix, and it
#: belongs in one constant because six call sites had the bare pattern.
_EXP_PREFIX = r"(?<![A-Za-z])E-"
EXP_ID = _EXP_PREFIX + r"\d+"


def _expand_experiment_ranges(text: str) -> set[str]:
    """`E-26 ... E-31, E-33` means seven ids, not three.

    `re.findall(EXP_ID)` takes only the endpoints, so E-27..E-30 were never
    marked uncommitted and could have been attached to a model beside a code
    path without the reproducibility check firing.
    """
    found: set[str] = set()
    for m in re.finditer(
            rf"{_EXP_PREFIX}(\d+)\s*(?:\u2026|\.\.\.|--|\u2013|\u2014)\s*E-(\d+)", text):
        lo, hi = int(m.group(1)), int(m.group(2))
        found |= {f"E-{n:02d}" for n in range(lo, hi + 1)}
    found |= set(re.findall(EXP_ID, text))
    return found

#: Model row -> the engine token its experiments should carry. Only models whose
#: family the ledger names; the rest are not constrained by this invariant.
MODEL_ENGINE = {
    "MODEL-TYPE-001": "strat",
    "MODEL-MAG-001": "magnitude",
    "MODEL-DIR-001": "direction",
}

#: Experiments the ledger records as having no committed artifacts. Citing one
#: beside a code path implies a reproduction route that does not exist.
UNCOMMITTED_MARKER = "not committed to the repo"

#: (model, experiment) pairs where the model owns one ARM of an experiment the
#: ledger scopes elsewhere. Declared here, not inferred from the prose.
#:
#: The check this replaces accepted ANY parenthetical: `re.search(rf"{exp}\s*
#: \([^)]+\)", cell)` never read what was inside. So moving `E-23 (execution
#: test)` from MODEL-TYPE-001 to MODEL-MAG-001 passed every invariant, and the
#: gate written to stop evidence being attached to the wrong model would have
#: waved it through -- the failure DOC-15 records, re-enabled by its own fix.
#:
#: Exactly one pair needs this today. Every other qualified citation in the
#: registry satisfies the family check on its own; the parentheses there are
#: prose, not an override.
ARM_OWNERSHIP = {
    ("MODEL-TYPE-001", "E-23"): (
        "the shares-execution arm. The ledger scopes E-23 `cross-cutting "
        "(tradeability)`; its 0.55-confidence 2U/2D calls are MODEL-TYPE-001's "
        "own predictions, so its FAIL verdict belongs on that row."
    ),
}


def _ledger_engine_area() -> dict[str, str]:
    """E-nn -> its `Engine/area:` value, from the ledger's own fixed shape."""
    return {
        m.group(1): m.group(2).strip().lower()
        for m in re.finditer(
            r"^## (E-\d+)[^\n]*\n(?:>.*\n|\n)*- \*\*Engine/area:\*\* ([^·\n]+)",
            LEDGER.read_text(),
            re.M,
        )
    }


def _traceability_rows() -> dict[str, str]:
    """MODEL-* -> the raw Experiments cell of its traceability row."""
    body = REGISTRY.read_text().split("| Model | Experiments |", 1)[1].split("\n###", 1)[0]
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r"^\| (MODEL-[A-Z]+-[0-9X]+) \| ([^|]*) \|", body, re.M)
    }


def test_code_cell_experiments_appear_in_the_experiments_cell():
    """An experiment named in a row's CODE cell must be in its EXPERIMENTS cell.

    Measured 2026-09-18 on MODEL-FEAT-X: its Code cell read "E-34's families:
    gcp/research/direction_program/phase2_features.py" while its Experiments
    cell listed only E-08, E-26, E-31, E-33. E-34's Phase 2 ablation tested
    five feature families in isolation and full stack -- a result about feature
    families, which is all MODEL-FEAT-X is.

    Every existing ownership gate stayed green, because
    test_every_ledger_experiment_is_owned_or_explicitly_ownerless asks only
    whether SOMEONE owns each id, and DIR and MAG both cite E-34. An experiment
    can be fully owned and still missing from the model it is most about. This
    checks the one place the registry contradicts ITSELF, within a single row,
    which needs no judgement about what an experiment is "about".
    """
    body = REGISTRY.read_text().split("| Model | Experiments |", 1)[1].split("\n###", 1)[0]
    rows = re.findall(
        r"^\| (MODEL-[A-Z]+-[0-9X]+) \| ([^|]*) \| ([^|]*) \|", body, re.M)
    assert len(rows) >= 8, (
        f"only {len(rows)} traceability rows parsed -- the table shape has drifted "
        "and this test would compare nothing."
    )
    bad = []
    for model, experiments, code in rows:
        in_exp = set(re.findall(EXP_ID, experiments))
        for eid in set(re.findall(EXP_ID, code)):
            if eid not in in_exp:
                bad.append(f"{model}: Code cell names {eid}, Experiments cell omits it")
    assert not bad, (
        f"traceability rows contradict themselves: {bad}. Either the experiment "
        "belongs on the row -- add it to Experiments -- or the code pointer does "
        "not belong to this model."
    )


def test_experiments_spanning_both_engines_appear_on_both_models():
    """An experiment the ledger scopes to `both` must not be filed under one."""
    scopes = {e: _engines(a) for e, a in _ledger_engine_area().items()}
    scopes.update({e: _engines(a) for e, a in LEDGER_SCOPE_OVERRIDES.items()})
    cited = {model: set(re.findall(EXP_ID, cell))
             for model, cell in _traceability_rows().items()}

    multi = {e: s for e, s in scopes.items() if len(s) > 1}
    assert multi, "no experiment spans two engines — did the ledger's shape change?"
    missing = []
    for exp, engines in sorted(multi.items()):
        # UNCONDITIONAL, and per NAMED OWNER. The earlier version hardcoded
        # TYPE+MAG, so E-34 (direction + magnitude) was never checked against
        # MODEL-DIR-001 and could be deleted from it while MAG still owned it.
        for engine in sorted(engines):
            model = ENGINE_OWNER.get(engine)
            if model and exp not in cited.get(model, set()):
                missing.append(f"{exp} spans {sorted(engines)} but is not on {model}")
    assert not missing, (
        "experiments scoped to both engines are filed under only one: "
        f"{missing}. This is how E-19's STRAT half and E-20's magnitude half went missing."
    )


def _ledger_ids() -> set[str]:
    """Every experiment id the ledger declares: `## E-nn` headings plus the
    ids named in a session header such as
    `# 2026-07-06 SESSION ... (E-26 ... E-31, E-33 + P0.1)`, ranges expanded."""
    text = LEDGER.read_text()
    ids = set(re.findall(r"^## (E-\d+)", text, re.M))
    for m in re.finditer(r"^# [^\n]*\(([^)]*E-\d+[^)]*)\)", text, re.M):
        ids |= _expand_experiment_ranges(m.group(1))
    return ids


def _ownerless_rows() -> list[str]:
    """The raw Experiments cell of each row in the ownerless table."""
    body = REGISTRY.read_text().split("### Experiments with no `MODEL-*` owner", 1)[1]
    body = body.split("\n###", 1)[0]
    return [m.group(1) for m in re.finditer(r"^\| ([^|]*E-\d+[^|]*) \|", body, re.M)]


def test_every_ledger_experiment_is_owned_or_explicitly_ownerless():
    """Total omission of a single-engine experiment.

    The only omission check before this was built from experiments scoped
    `both`, so deleting E-01 from MODEL-TYPE-001 left every test green: the
    family check examines only ids that remain cited, and the ownerless table
    was never read for coverage. The registry's stated goal is that every
    experiment is attached to its owner or explicitly listed as ownerless;
    this asserts exactly that, with `E-09...E-15`-style ranges expanded."""
    ledger = _ledger_ids()
    assert len(ledger) >= 30, f"only {len(ledger)} ids parsed from the ledger — shape change?"
    owned: set[str] = set()
    for cell in _traceability_rows().values():
        owned |= _expand_experiment_ranges(cell)
    ownerless: set[str] = set()
    for cell in _ownerless_rows():
        ownerless |= _expand_experiment_ranges(cell)
    assert ownerless, "no ownerless rows parsed — did the table shape change?"
    missing = sorted(ledger - owned - ownerless, key=lambda e: int(e[2:]))
    assert not missing, (
        f"experiments in the ledger that no model owns and the ownerless table "
        f"does not list: {missing}. Attach each to its owner or record it as ownerless."
    )
    # And the other direction. Checking only `ledger - owned - ownerless` asks
    # "is every real experiment placed?" and never "is everything placed real?",
    # so a typo'd or invented id was citable as evidence. It survived the family
    # check too, because that check skips models whose engine the ledger does not
    # name -- which is most of them.
    invented = sorted((owned | ownerless) - ledger, key=lambda e: int(e[2:]))
    assert not invented, (
        f"the registry cites experiment ids the ledger does not declare: {invented}. "
        "An id that resolves to nothing is evidence that cannot be read."
    )


def test_experiment_ids_are_not_parsed_out_of_model_ids():
    """`E-\\d+` matches inside MODEL-AGREE-001, MODEL-TYPE-001, MODEL-STYLE-001.

    All three end in `E-001`. The ownerless table's E-23 row names
    MODEL-TYPE-001 in its prose, so the parsed ownerless set carried a phantom
    `E-001` -- harmless while coverage was asserted one way, and a guaranteed
    false failure the moment the reverse assertion was added. Pinned here rather
    than left to the caller, because six call sites had the bare pattern and the
    seventh would have had it too.
    """
    assert re.findall(EXP_ID, "MODEL-AGREE-001 MODEL-TYPE-001 MODEL-STYLE-001") == []
    assert re.findall(EXP_ID, "E-23 and E-8") == ["E-23", "E-8"]
    ownerless: set[str] = set()
    for cell in _ownerless_rows():
        ownerless |= _expand_experiment_ranges(cell)
    assert "E-001" not in ownerless, (
        f"phantom id parsed from a model id in the ownerless table: {sorted(ownerless)}"
    )


def test_cited_experiments_match_the_models_engine():
    """An experiment on a model's row should belong to that model's family, or
    be explicitly qualified in the cell (an arm, a cross-cutting test)."""
    area = _ledger_engine_area()
    wrong = []
    for model, cell in _traceability_rows().items():
        engine = MODEL_ENGINE.get(model)
        if engine is None:
            continue
        for exp in re.findall(EXP_ID, cell):
            # Do NOT skip. A silent `continue` here left E-24, E-34 and the
            # E-26..E-33 session outside the family check entirely, and would
            # accept a typo'd or nonexistent id as valid. Sections whose shape
            # the parser cannot read carry an explicit scope instead, and go
            # through the same check as everything else.
            a = area.get(exp) or LEDGER_SCOPE_OVERRIDES.get(exp)
            if a is None:
                # Do NOT skip. A silent `continue` here left E-24, E-34 and the
                # E-26..E-33 session outside the family check entirely, and would
                # accept a typo'd or nonexistent id as valid. Sections whose shape
                # the parser cannot read must be listed explicitly.
                a = LEDGER_SCOPE_OVERRIDES.get(exp)
                if a is None:
                    wrong.append(f"{model} cites {exp}, which has no Engine/area in the ledger")
                    continue
                # fall through: an exceptional section is checked like a parsed one.
            engines = _engines(a)
            if engine in engines:
                continue
            # Everything that is NOT a family match goes through one declaration.
            #
            # Two escapes used to sit here, and the wider one hid the narrower.
            # A `cross-cutting` or `precursor` scope passed unconditionally, on
            # any model -- so E-23 was citable anywhere, and an allowlist placed
            # after it would never have been consulted for the single case it
            # exists to govern. (Measured: exactly one citation reached this
            # branch, and it is the one ARM_OWNERSHIP declares.) The narrower
            # escape, "some parentheses are present", never read what was inside
            # them, so the same three words licensed the citation on any row.
            if (model, exp) not in ARM_OWNERSHIP:
                wrong.append(
                    f"{model} cites {exp} ('{a}'), which is not its family and is "
                    f"not declared in ARM_OWNERSHIP"
                )
                continue
            if not re.search(rf"{exp}\s*\([^)]+\)", cell):
                wrong.append(
                    f"{model} cites {exp} as a declared arm but the cell does not "
                    f"say which arm"
                )
    assert not wrong, (
        f"experiment/model family mismatches without a qualifying note: {wrong}. "
        "Either the experiment is on the wrong row, or the cell should say which arm applies."
    )


def test_uncommitted_experiments_are_not_presented_as_reproducible():
    """The ledger marks some results as never committed. A row citing one beside
    code paths claims a reproduction route that does not exist."""
    ledger = LEDGER.read_text()
    if UNCOMMITTED_MARKER not in ledger:
        pytest.skip("the ledger no longer records uncommitted experiments")

    # Experiments named in the paragraph carrying the marker.
    para = [p for p in ledger.split("\n\n") if UNCOMMITTED_MARKER in p]
    uncommitted = {e for p in para for e in re.findall(EXP_ID, p)}
    # The 2026-07-06 session's table rows name them; pick them up from its header too.
    session = re.search(r"# 2026-07-06 SESSION[^\n]*\(([^)]*)\)", ledger)
    if session:
        uncommitted |= _expand_experiment_ranges(session.group(1))

    bad = []
    for model, cell in _traceability_rows().items():
        row = REGISTRY.read_text().split(f"| {model} | {cell} |", 1)
        if len(row) < 2:
            continue
        code_cell = row[1].split("|")[0]
        for exp in re.findall(EXP_ID, cell) :
            if exp not in uncommitted:
                continue
            if "unavailable" in cell.lower() or "unavailable" in code_cell.lower():
                continue
            if "not committed" in cell.lower() or "not committed" in code_cell.lower():
                continue
            bad.append(f"{model} cites {exp} without marking its artifacts unavailable")
    assert not bad, (
        f"{bad}. The ledger records these as a scratch harness whose code was never "
        "committed, so no listed path reproduces them — say so in the row."
    )


# ------------------------------------------------- 9. doc <-> registry joins --
# Four findings in one review round were the same shape: a claim corrected in
# docs/models/ and left standing in the registry row or the concern register.
# Fixing the instance is not fixing the claim. These two gate that class.

def _gh_slug(heading: str) -> str:
    """GitHub's anchor slug: strip punctuation, then space -> '-' ONE FOR ONE.

    Collapsing whitespace runs is wrong and hides real breakage: every heading
    here contains an em-dash, which is stripped and leaves two spaces, so the
    real anchor carries a double hyphen. A collapsing slug reported 15 of the
    16 catalog links as fine when all 16 were dead.
    """
    s = re.sub(r"`", "", heading).strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    return s.replace(" ", "-")


def test_cross_document_anchors_resolve():
    """A heading rename must not leave its consumers pointing at nothing.

    `12-PR-ISSUE-TRACEABILITY.md`'s section headings carry their open-issue
    count, so every count change renames the anchor. `02-FEATURE-CATALOG.md`
    links to all sixteen, and nothing noticed when they broke -- the link
    checker validated files, not fragments.
    """
    dead, checked = [], 0
    for md in sorted(PRODUCT.glob("*.md")):
        for m in re.finditer(r"\]\(([A-Za-z0-9._-]+\.md)#([a-z0-9-]+)\)", md.read_text()):
            target = md.parent / m.group(1)
            if not target.exists():
                continue
            anchors = {_gh_slug(h) for h in re.findall(r"^#{1,6} (.+)$", target.read_text(), re.M)}
            checked += 1
            if m.group(2) not in anchors:
                dead.append(f"{md.name} -> {m.group(1)}#{m.group(2)}")
    assert checked >= 50, f"only {checked} cross-file anchors found -- did the docs change shape?"
    assert not dead, f"links pointing at headings that do not exist: {dead}"


def test_registry_code_column_names_the_live_implementation():
    """Every `.py` in a model doc's **Code:** header is in its registry Code cell.

    MODEL-MR-001's doc was corrected to say `lib.signals.evaluate_signal` is the
    production path while the registry row still listed only the class that
    production never calls -- so the governance inventory pointed at the wrong
    code for a live model, and nothing noticed.

    The first version keyed off the literal phrase "live implementation", which
    is how MODEL-MR-001 was caught and MODEL-STYLE-001 was not: STYLE's row named
    the HTTP endpoint and the results table and no implementation at all, and the
    gate had nothing to match on. A gate keyed to a phrase only covers documents
    that happen to use it. This one is total -- the header is the doc's own claim
    about what code the model is, so the row must carry it.
    """
    text = REGISTRY.read_text()
    code_cell = {}
    for table in ("## Deterministic and heuristic systems", "## Learned models"):
        for line in text.split(table, 1)[1].split("\n##", 1)[0].split("\n"):
            if re.match(r"^\| MODEL-", line):
                cells = [c.strip() for c in line.split("|")]
                code_cell[cells[1]] = cells[5]

    missing, found = [], 0
    for doc in sorted((REPO / "docs" / "models").glob("MODEL-*.md")):
        mid, body = doc.stem, doc.read_text()
        if mid not in code_cell or "**Code:**" not in body:
            continue
        header = body.split("**Code:**", 1)[1].split("**Registry:**")[0]
        for path in sorted(set(re.findall(r"`([A-Za-z0-9_./]+\.py)`", header))):
            found += 1
            if path.rsplit("/", 1)[-1] not in code_cell[mid]:
                missing.append(f"{mid}: doc header names {path}; registry Code cell omits it")
    assert found >= 8, (
        f"only {found} header paths parsed -- the parser matched almost nothing, "
        "so this test would pass no matter what the registry said."
    )
    assert not missing, (
        f"registry Code cells disagree with their model docs: {missing}. "
        "Correcting the doc and leaving the row is how MODEL-MR-001 kept pointing "
        "at a class production never calls."
    )


def test_no_model_doc_denies_an_issue_the_register_names():
    """A doc may not say "no issue tracks this" about a concern that has one.

    Four issues were filed for DOC-18/23/24/27 and the register's dispositions
    were repointed at them -- and not one of the eight `docs/models/*.md` was.
    Two still read "No issue tracks this", and MODEL-BRIEF-001's Known issues
    still said "None open." while the new issue named its stale header.

    That is DOC-22's class exactly (fix the instance, not the claim), committed
    in the commit whose message recorded DOC-22 as closed. The two invariants
    added for DOC-22 both run doc -> registry; neither runs doc -> register
    disposition, which is the direction that failed here.
    """
    text = REGISTRY.read_text()
    disposition = text[text.index("### Disposition"):text.index("Merged-PR lineage")]

    # DOC ids whose disposition names a GitHub issue.
    tracked: set[str] = set()
    for line in disposition.split("\n"):
        if not re.match(r"^\|\s*DOC-", line):
            continue
        cells = [c.strip() for c in line.split("|")]
        if re.search(r"/issues/\d+", cells[3]):
            tracked |= _expand_doc_ranges(cells[1])
    assert tracked, "no disposition names an issue -- did the table change shape?"

    denial = re.compile(r"[Nn]o issue (?:tracks|is filed)|None open", re.M)
    bad = []
    for doc in sorted((REPO / "docs" / "models").glob("MODEL-*.md")):
        body = doc.read_text()
        for cid in sorted(set(re.findall(r"DOC-\d+", body)) & tracked):
            for m in denial.finditer(body):
                # Only the sentence that also cites this id.
                window = body[max(0, m.start() - 400):m.start() + 400]
                if cid in window:
                    bad.append(f"{doc.name}: denies an issue for {cid} ({m.group(0)!r})")
    assert not bad, (
        f"model docs deny issues the register tracks: {sorted(set(bad))}. "
        "Filing an issue means repointing every document that said there was none."
    )


def test_register_makes_no_uniqueness_claim_about_recorded_rationale():
    """No disposition may claim one model is the only one with a derivation.

    That exact claim was wrong twice: written into MODEL-EARN-001, corrected
    there, and left standing in DOC-10's disposition. MODEL-MOM-001,
    MODEL-MR-001 and MODEL-STYLE-001 all record derivations, so any "only
    MODEL-X had a real one" phrasing is false by construction.
    """
    text = REGISTRY.read_text()
    register = text[text.index("### Findings"):text.index("## How this registry is kept honest")]
    bad = re.findall(
        r"[Oo]nly\s+(MODEL-[A-Z-]+(?:-\d+|X))\s+(?:had|has)\s+(?:a\s+)?real",
        register)
    assert not bad, (
        f"the concern register claims {bad} uniquely has a recorded derivation. "
        "MOM, MR and STYLE all record one; this claim was already removed from "
        "the earnings doc and must not survive here."
    )


def test_docs_citing_solyra_paths_explain_the_split():
    """A `platform/src/**` path resolves nowhere in this repo. That is fine —
    the #957 split moved the frontend — but only if the document says so.
    Otherwise a reader follows it and finds nothing, which is the same failure
    as a dead path with none of the visibility."""
    missing = []
    for md in sorted(PRODUCT.glob("*.md")):
        text = md.read_text()
        cited = {p for p in _cited_paths(_strip_exempt(text)) if _is_solyra_owned(p)}
        if not cited:
            continue
        if "solyra" not in text.lower():
            missing.append(f"{md.name} cites {len(cited)} solyra path(s) without naming solyra")
    assert not missing, (
        f"{missing}. Add the frontend-split note (11-CODE-TRACEABILITY.md has the "
        "canonical wording) or link to the doc that carries it."
    )


# ------------------------------------------- 9. the two gaps round 2 left --
#
# Round 2 added a scheduler check and shipped it as "un-repeatable". One round
# later the review found `audit-brief-bias-weekly` missing from the same table.
# The check verified that listed rows were CORRECT; it never asked whether the
# list was COMPLETE, which is the defect that actually recurred. Likewise the
# vocabulary check covered Status and Doc but not Rec, so MODEL-DIR-001 carried
# `REMOVE / archive` -- outside the declared set -- through a green suite.

#: Jobs whose name marks them as model-bearing: they train, score, or audit a
#: model. A scheduled job matching this and absent from the table is the
#: `audit-brief-bias-weekly` omission repeating.
#: A job is model-bearing when it PRODUCES A DECISION, A LABEL OR A VERDICT about
#: a trade, a signal or a position that REACHES A PERSON OR A SERVED SURFACE --
#: wherever its thresholds live. That is the rule published in the registry as of
#: 2026-09-18. This tuple is a cheaper PROXY for it ("executes code cited in a
#: MODEL-* row"), kept because it is the only rule expressible as a substring
#: match, and it is no longer what guarantees completeness:
#:
#:   - it missed `signal-monitor` until 2026-09-17 -- the job that evaluates MOM,
#:     MR, AGREE, EXIT and BRIEF every trading morning;
#:   - it structurally could not see `build-options-greeks` or `insight-pipeline`,
#:     because its rule needs a MODEL-* row to cite the code first;
#:   - it missed four more on 2026-09-18 that import no `lib/` code at all.
#:
#: Completeness is now test_every_live_scheduler_is_classified, which requires
#: every scheduler in deploy.sh to appear in one of the registry's two tables. A
#: substring list is only as complete as its author; that is why it is no longer
#: the thing being trusted.
MODEL_BEARING = ("magnitude", "strat-engine", "direction", "calibrate-thresholds",
                 "regime-combo", "audit-walkforward", "audit-brief-bias",
                 "p2-build-gamma-levels", "audit-magnitude-drift",
                 "signal-monitor", "build-realtime-gex", "refresh-earnings-views",
                 # Added 2026-09-18. Each runs a model and none carried a model
                 # word, so the completeness gate had never asked about them --
                 # the same mechanism DOC-20 records for `signal-monitor`, which
                 # is why a curated list needs re-deriving, not just extending.
                 "premarket-brief", "auto-refresh-top-n",
                 "build-options-daily-features", "historical-signals-watchlist",
                 "earnings-sweep",
                 # Added 2026-09-18, AFTER MODEL-FLOW-001 was registered. Review
                 # filed this as a whitelist omission; the whitelist was right --
                 # its rule is "executes code cited in a MODEL-* row", and
                 # lib/features/flow_direction.py was cited by none. Adding the
                 # job first would have made the gate demand a row that did not
                 # exist. The registry was short a model, not the list an entry.
                 "build-options-greeks",
                 # Added 2026-09-18 with MODEL-EARN-002 and the LLM table's new
                 # Code column. `insight-pipeline` runs all 14 registered LLM
                 # nodes on a weekday cron and was invisible to this gate for the
                 # same structural reason as build-options-greeks: the rule below
                 # needs a MODEL-* row to cite the code, and the LLM table had no
                 # Code column at all.
                 "earnings-reactions-brief", "insight-pipeline",
                 "insight-discord-push",
                 # Added 2026-09-18 by the round-10 systematic sweep. None of the
                 # four was findable by this list's rule ("executes code cited in
                 # a MODEL-* row"): `phase6-playbook` and `earnings-long-watchlist`
                 # have no `lib/` import at all, `evaluate-ew-strikes` writes only
                 # with UPDATE, and `weekend-review` reaches model code through one
                 # label helper. They were found by walking every scheduler in
                 # deploy.sh instead -- which is what
                 # test_every_live_scheduler_is_classified now requires, and why
                 # this tuple is no longer the completeness mechanism.
                 "phase6-playbook", "earnings-long-watchlist",
                 "evaluate-ew-strikes", "weekend-review",
                 # Added 2026-09-22. These two WERE in this tuple's blind spot in
                 # the opposite way: they import lib.strat, which the old proxy
                 # rule would have caught -- and the registry excluded them by
                 # hand anyway, on the false claim that they emit no decision.
                 # `fetch-market-data` writes the thresholded `strat_setup`;
                 # `backfill-daily-indicators` writes MODEL-STRAT-001's candle
                 # labels. Both are served. Neither substring collides with
                 # another declared job (checked).
                 "fetch-market-data", "backfill-daily-indicators")

def _scheduler_entrypoint_overrides() -> dict[str, str]:
    """scheduler -> the module its containerOverrides args actually run.

    A scheduler may target a job and then override which module that job runs.
    `strat-enrich-daily` targets `strat-engine` -- a model-bearing job -- but
    runs `gcp.research.strat_engine.strat_enrich_levels`, which writes ORB and
    historical-level feature columns and classifies nothing. Judging it by the
    job's name says "model-bearing"; judging it by the code it runs says
    "inputs only", and the code is what is true.

    So the job-name proxy below does not apply to an overridden scheduler, and
    `test_every_live_scheduler_is_classified` covers it instead -- by requiring
    it in one of the two tables with a written reason, which is the standard
    this PR replaced the proxy with in the first place.
    """
    sys.path.insert(0, str(REPO / "scripts" / "maintenance"))
    from doc_inventory import deploy_schedulers

    out = {}
    for d in deploy_schedulers(REPO):
        m = re.search(r"-m\s+([\w.]+)", d.get("args") or "")
        if m:
            out[d["name"]] = m.group(1)
    return out


def _is_model_bearing(job: str) -> bool:
    return any(k in job for k in MODEL_BEARING)


def test_every_scheduled_model_bearing_job_is_listed():
    """Completeness, not just correctness of the rows that are present.

    Keyed by SCHEDULER NAME, not by target job. Three schedulers target the
    `signal-monitor` job (`signal-monitor-daily` and the two ORB snapshots),
    so a job-keyed check let the `signal-monitor-daily` row be deleted while
    the ORB rows kept the job "listed" -- measured 2026-09-18: dropping that
    row and lowering the count to thirteen passed every invariant. The table's
    own inclusion rule is stated per scheduler entry, so this is too."""
    listed = {name for name, _, _ in re.findall(
        r"^\| `([a-z0-9-]+)` \| `([^`]+)` \| `([a-z0-9-]+)` \|", _run_section(), re.M)}
    missing = sorted(
        f"{name} -> {job}"
        for name, (_, job) in _declared_schedulers().items()
        if _is_model_bearing(job) and name not in listed
        and name not in _scheduler_entrypoint_overrides()
    )
    assert not missing, (
        f"model-bearing scheduler entries absent from the table: {missing}. "
        "This is how audit-brief-bias-weekly was missed one round after the "
        "gamma omission was 'gated', and how signal-monitor-daily -- the entry that "
        "fires the live strategies -- was missed the round after that."
    )


#: The registry's two scheduler tables. Together they must cover every scheduler
#: declared in gcp/deploy.sh -- that is the invariant that replaced MODEL_BEARING
#: as the completeness mechanism.
_LISTED_HEADER = "| Scheduler | Cron (`America/New_York`) | Job | Serves |"
_EXCLUDED_HEADER = "| Scheduler | Job | Why it is not model-bearing |"


def _table_schedulers(header: str) -> set[str]:
    """Scheduler names from a registry table's FIRST CELL only.

    First cell only, because schedulers differing solely by cron share a row
    ("`av-intraday-nightly` . `av-intraday-monthly`") and every backticked name
    there is a classification -- while a name appearing in a later cell is a job
    or a file, and counting those would mark a scheduler classified because some
    row happened to mention it.
    """
    text = REGISTRY.read_text()
    assert header in text, f"the registry no longer has the table {header!r}"
    body = text.split(header, 1)[1].split("\n\n", 1)[0]
    out: set[str] = set()
    for row in body.split("\n"):
        if not row.startswith("|"):
            continue
        out |= set(re.findall(r"`([\w-]+)`", row.split("|")[1]))
    return out


def test_every_live_scheduler_is_classified():
    """Completeness by ENUMERATION, not by keyword.

    Three consecutive review rounds on PR #1111 each found a scheduled decision
    system with no registry row, and every one was missed the same way: the gate
    asked "does this job name contain a model word", which is a proxy. This asks
    the only question that cannot be gamed by naming -- is every scheduler in
    deploy.sh written down somewhere, as model-bearing or as deliberately not.

    A new scheduler therefore fails the build until somebody classifies it. That
    is the point: an unrecorded exclusion is indistinguishable from an omission.
    """
    declared = set(_declared_schedulers())
    assert len(declared) >= 55, (
        f"only {len(declared)} schedulers parsed from gcp/deploy.sh -- the parser "
        "has drifted, and a completeness check that enumerates almost nothing passes."
    )
    listed = _table_schedulers(_LISTED_HEADER)
    excluded = _table_schedulers(_EXCLUDED_HEADER)
    assert excluded, (
        "the deliberate-exclusion table is empty. It is what makes this gate mean "
        "anything: without it, every scheduler could be classified by deleting the rule."
    )

    unclassified = sorted(declared - listed - excluded)
    assert not unclassified, (
        f"schedulers in gcp/deploy.sh classified in neither registry table: "
        f"{unclassified}. Add each to the scheduler table with the model it serves, "
        "or to the deliberate-exclusion table with the reason. Run "
        "`python3 scripts/audit_scheduler_coverage.py` for the write / Discord / "
        "import evidence behind the call."
    )

    both = sorted(listed & excluded)
    assert not both, f"schedulers classified as BOTH model-bearing and not: {both}"

    # The reverse direction. Review caught this as one-way on 2026-09-21: a
    # scheduler deleted or renamed in deploy.sh left its exclusion row standing,
    # `declared - listed - excluded` stayed empty, and the registry went on
    # publishing a scheduler that does not exist. The LISTED table already had
    # this check -- test_scheduler_table_matches_deploy_sh asserts `name in
    # declared` per row -- so only the exclusion table could rot, which is
    # exactly the table nobody reads closely.
    stale = sorted(excluded - declared)
    assert not stale, (
        f"the deliberate-exclusion table names schedulers that gcp/deploy.sh does "
        f"not declare: {stale}. Remove the row, or correct it if the scheduler was "
        "renamed -- an exclusion for a job that no longer exists is not a record, "
        "it is a claim about nothing."
    )


def test_status_summary_matches_the_tables_it_summarises():
    """The published per-status counts, recomputed from the rows.

    Measured 2026-09-21: merging `main` moved MODEL-MAG-001 `Invalidated` ->
    `Experimental` (#1117 landed as 164b262), and the Status summary went on
    publishing `Invalidated | 2 (MODEL-MAG-001, MODEL-SWEEP-001)` and
    `Experimental | 7`. The whole suite stayed green -- every invariant here
    checks rows against code or against other rows, and nothing checked the
    SUMMARY against the rows it summarises.

    That is the same defect this registry keeps recording about itself: a
    number derived by hand from a table, drifting the moment the table moves.
    The scheduler section's answer was to delete its count; a per-status
    breakdown is worth keeping, so it gets a gate instead.

    Names in a cell are checked too, not just the total: `2 (A, B)` is wrong
    in a way `2` cannot be when the membership changes but the size does not.
    """
    text = REGISTRY.read_text()
    actual: dict[str, set[str]] = {}
    for table, col in (("## Deterministic and heuristic systems", 6),
                       ("## Learned models", 6)):
        assert table in text, f"registry no longer has the table {table!r}"
        for line in text.split(table, 1)[1].split("\n##", 1)[0].split("\n"):
            if not line.startswith("| MODEL-"):
                continue
            cells = [c.strip() for c in line.split("|")]
            status = cells[col].strip("* ").split(" — ")[0].strip("* ")
            actual.setdefault(status, set()).add(cells[1])
    assert len(actual) >= 5 and sum(len(v) for v in actual.values()) >= 20, (
        "too few rows parsed for the summary check to mean anything -- a column "
        "index or heading has drifted."
    )

    summary = text.split("## Status summary", 1)[1].split("\n##", 1)[0]
    published, bad = set(), []
    for line in summary.split("\n"):
        m = re.match(r"^\| ([^|]+?) \| (\d+)([^|]*)\|", line)
        if not m:
            continue
        status = m.group(1).strip().strip("*")
        if status not in actual:
            bad.append(f"{status!r}: published, but no model row carries it")
            continue
        published.add(status)
        n, rest = int(m.group(2)), m.group(3)
        if n != len(actual[status]):
            bad.append(f"{status}: published {n}, table has {len(actual[status])} "
                       f"({sorted(actual[status])})")
        named = set(re.findall(r"MODEL-[A-Z]+-[0-9X]+", rest))
        if named and named != actual[status]:
            bad.append(f"{status}: names {sorted(named)}, table has {sorted(actual[status])}")

    for status in sorted(set(actual) - published):
        bad.append(f"{status}: {len(actual[status])} model(s) carry it, absent from the summary")
    assert not bad, "Status summary disagrees with the tables: " + "; ".join(bad)


def _audit_module():
    """`scripts/audit_scheduler_coverage.py`, loaded as a module.

    Reused rather than re-implemented: that script already resolves
    scheduler -> job -> entrypoint, including the `common_flags` array form and
    backslash continuations that two earlier hand-rolled parsers got wrong. A
    fourth parser of the same file is how the counts diverge.
    """
    import importlib.util
    path = REPO / "scripts" / "audit_scheduler_coverage.py"
    assert path.exists(), f"{path} is missing -- the scheduler gates depend on it"
    spec = importlib.util.spec_from_file_location("_audit_scheduler_coverage", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _model_cited_modules() -> set[str]:
    """Dotted module/package names appearing in any `MODEL-*` row's Code cell."""
    text = REGISTRY.read_text()
    out: set[str] = set()
    for table, col in (("## Deterministic and heuristic systems", 5),
                       ("## Learned models", 5),
                       ("## LLM nodes", 4)):
        if table not in text:
            continue
        for line in text.split(table, 1)[1].split("\n##", 1)[0].split("\n"):
            if not line.startswith("| MODEL-"):
                continue
            cell = line.split("|")[col]
            for path in re.findall(r"`([A-Za-z0-9_./-]+\.py)`", cell):
                out.add(path[:-3].replace("/", "."))
            for pkg in re.findall(r"`(lib/[a-z_/]+)`", cell):
                out.add(pkg.rstrip("/").replace("/", "."))
    return out


def test_excluded_jobs_importing_model_code_justify_it():
    """The old proxy, demoted from a rule to a tripwire.

    "Does the job import `lib/` code cited in a MODEL-* row" failed as an
    INCLUSION test -- it misses every job that hard-codes its own thresholds,
    which is why the registry's rule was replaced on 2026-09-18. It is well
    suited to the opposite job: a scheduler that imports model code and is
    nevertheless excluded is exactly the row that deserves a second look.

    Measured 2026-09-22, which is why this exists: `fetch-market-data-daily`
    and `backfill-indicators-daily` were excluded on the claim that they emit
    "model inputs ... No decision is emitted", while the first writes the
    thresholded `strat_setup` and the second writes MODEL-STRAT-001's candle
    labels, both served by `/api/dashboard`. The tripwire would have flagged
    both. The deeper failure is that the rule was replaced and the examples
    justifying the old one were never re-derived against the new one (DOC-43).

    So an exclusion that trips it must carry an explicit marker rather than
    bare prose -- a written argument, not an assumption.
    """
    declared = _declared_schedulers()
    cited = _model_cited_modules()
    assert len(cited) >= 15, (
        f"only {len(cited)} modules parsed from MODEL-* Code cells -- the column "
        "index has drifted and this tripwire would never fire."
    )

    text = REGISTRY.read_text()
    body = text.split(_EXCLUDED_HEADER, 1)[1].split("\n\n", 1)[0]
    reasons: dict[str, str] = {}
    for row in body.split("\n"):
        if not row.startswith("| `"):
            continue
        cells = row.split("|")
        if len(cells) < 4:
            continue
        for name in re.findall(r"`([\w-]+)`", cells[1]):
            reasons[name] = cells[3]

    audit = _audit_module()
    deploy = audit._uncommented((REPO / "gcp" / "deploy.sh").read_text())
    jobs = audit.resolve_jobs(deploy)
    jobs.update({k: v for k, v in audit.resolve_services(deploy).items() if k not in jobs})

    tripped, unjustified = 0, []
    for name, reason in sorted(reasons.items()):
        if name not in declared:
            continue
        j = jobs.get(declared[name][1])
        if not j or not j.get("entrypoint"):
            continue
        entry = audit.entry_path(j["entrypoint"], j["kind"])
        if entry is None or not entry.exists():
            continue
        src = entry.read_text()
        imports = set(re.findall(r"(?:from|import)\s+(lib\.[\w.]+)", src))
        hit = {i for i in imports
               if any(i == c or i.startswith(c + ".") or c.startswith(i + ".") for c in cited)}
        if not hit:
            continue
        tripped += 1
        if "Inputs only —" not in reason:
            unjustified.append(f"{name} imports {sorted(hit)}")

    assert not unjustified, (
        "excluded schedulers import code a MODEL-* row cites, without an explicit "
        f"justification: {unjustified}. Begin the reason with '**Inputs only —**' and "
        "say what makes it inputs rather than a decision -- ideally something a reader "
        "can re-run. The two jobs this test was written for failed exactly here."
    )


def test_exclusion_table_job_cells_match_deploy_sh():
    """The exclusion table's SECOND column, which nothing read.

    Measured 2026-09-22: 12 of 21 exclusion rows named a job that does not
    exist, because the names were derived by stripping the scheduler's suffix
    instead of reading deploy.sh -- `fred-rates` for `fetch-fred-rates`,
    `av-intraday` for `fetch-alphavantage-intraday`, and one row collapsing
    THREE distinct jobs into a single invented `news-sentiment`.

    Every gate stayed green because `_table_schedulers` and the audit script's
    `registry_tables()` parse only the FIRST cell. The listed table's Job cell is
    checked -- test_scheduler_table_matches_deploy_sh asserts
    `declared[name] == (cron, job)` per row -- so once again only the exclusion
    table could rot. That is the second consecutive round where the defect was
    "the other direction, or the other column, was never checked".
    """
    declared = _declared_schedulers()
    text = REGISTRY.read_text()
    assert _EXCLUDED_HEADER in text, "the deliberate-exclusion table is gone"
    body = text.split(_EXCLUDED_HEADER, 1)[1].split("\n\n", 1)[0]

    checked, bad = 0, []
    for row in body.split("\n"):
        if not row.startswith("| `"):
            continue
        cells = row.split("|")
        if len(cells) < 4:
            continue
        names = re.findall(r"`([\w-]+)`", cells[1])
        claimed = set(re.findall(r"`([\w-]+)`", cells[2]))
        real = {declared[n][1] for n in names if n in declared}
        if not real:
            continue
        checked += 1
        if real != claimed:
            bad.append(f"{', '.join(names)}: table says {sorted(claimed)}, "
                       f"deploy.sh says {sorted(real)}")
    assert checked >= 15, (
        f"only {checked} exclusion rows parsed -- the table shape has drifted and "
        "this test would compare nothing."
    )
    assert not bad, (
        "exclusion-table Job cells disagree with gcp/deploy.sh: " + "; ".join(bad) +
        ". Name the job deploy.sh declares, and list all of them when the "
        "schedulers on one row target different jobs."
    )


def test_scheduler_table_model_ids_have_registry_rows():
    """A `Serves` cell naming a model that does not exist.

    Measured 2026-09-18: four new scheduler rows were added citing MODEL-PLAY-001,
    MODEL-WATCH-001, MODEL-EWV-001 and MODEL-WEEK-001 before any of those rows
    existed, and the whole suite stayed green. Every other gate checks the model
    rows against the docs and the docs against the code; nothing checked that a
    scheduler pointing at a model pointed at a real one.
    """
    text = REGISTRY.read_text()
    defined = set(re.findall(r"^\| (MODEL-[A-Z0-9-]+) \|", text, re.M))
    assert len(defined) >= 20, (
        f"only {len(defined)} MODEL-* rows parsed -- the table format has drifted "
        "and this test would accept any id at all."
    )
    section = _run_section()
    cited = set(re.findall(r"(MODEL-[A-Z]+-[A-Z0-9]+)", section))
    dangling = sorted(cited - defined)
    assert not dangling, (
        f"the scheduler table serves models with no registry row: {dangling}. "
        "A job cannot serve a model that is not registered -- register it or "
        "correct the Serves cell."
    )


def test_the_live_signal_monitor_is_classified_model_bearing():
    """Pins the classification itself, so the exact-match set cannot be
    emptied without a failure. `signal-monitor` must be on a cron in
    deploy.sh (or the registry's whole premise about the live path is wrong)
    and must count as model-bearing."""
    scheduled = {job for _, job in _declared_schedulers().values()}
    assert "signal-monitor" in scheduled, "signal-monitor is no longer scheduled in gcp/deploy.sh"
    assert _is_model_bearing("signal-monitor")


def test_rec_cells_use_the_declared_vocabulary():
    """`Rec` was never checked. MODEL-DIR-001 read `REMOVE / archive`."""
    m = re.search(r"\*\*Rec\*\* = ([A-Z/ ]+);", REGISTRY.read_text())
    assert m, "the column contract no longer declares the Rec vocabulary"
    allowed = {v.strip() for v in m.group(1).split("/") if v.strip()}
    text = REGISTRY.read_text()
    bad = []
    for table in ("## Deterministic and heuristic systems", "## Learned models"):
        for line in text.split(table, 1)[1].split("\n##", 1)[0].split("\n"):
            if not re.match(r"^\| MODEL-", line):
                continue
            cells = [c.strip() for c in line.split("|")]
            if cells[7].strip("* ") not in allowed:
                bad.append(f"{cells[1]}: {cells[7]!r}")
    assert not bad, (
        f"Rec values outside {sorted(allowed)}: {bad}. Put any qualifier in prose, "
        "not in the column a machine reads."
    )
