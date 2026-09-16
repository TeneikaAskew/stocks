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

This pins the parts a machine can settle offline. Eight invariants:

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

What it deliberately does NOT do:

* **It cannot check whether a cited GitHub issue is still open.** That is the
  defect that started this and it needs the network. The registry carries a
  prose caveat instead, and the nearest offline proxy — every issue cited in
  the registry also appears in 12-PR-ISSUE-TRACEABILITY.md — is asserted below.
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

#: Pre-existing dead paths elsewhere under docs/product/. Measured 2026-09-15.
#: Mostly the solyra frontend split (platform/src/routes/*.tsx) and a test-tree
#: migration. These may only go DOWN — the test asserts both directions, so
#: fixing one without lowering its number here also fails.
KNOWN_BACKLOG = {
    "02-FEATURE-CATALOG.md": 16,
    "04-BACKEND-API.md": 3,
    "09-SECURITY-AUTH.md": 2,
    "11-CODE-TRACEABILITY.md": 18,
    "14-WORK-BREAKDOWN.md": 3,
    "16-CONSOLIDATION-AUDIT.md": 1,
    "README.md": 14,
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


def _cited_paths(text: str) -> set[str]:
    return {
        m.group(1)
        for m in re.finditer(r"`([A-Za-z0-9_./-]+)`", text)
        if m.group(1).startswith(ROOTS) and "/" in m.group(1)
    }


def _dead_paths(md: Path) -> set[str]:
    return {p for p in _cited_paths(_strip_exempt(md.read_text())) if not (REPO / p).exists()}


# ---------------------------------------------------------------- 1. paths --

def test_registry_cites_no_dead_code_path():
    dead = _dead_paths(REGISTRY)
    assert dead == set(), (
        f"{REGISTRY.name} cites paths that do not exist: {sorted(dead)}. "
        "A registry pointing at deleted code is how MODEL-OPT-001 spent months "
        "naming platform/src/lib/greeksCalculator.ts."
    )


@pytest.mark.parametrize("name,expected", sorted(KNOWN_BACKLOG.items()))
def test_known_dead_path_backlog_only_shrinks(name, expected):
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
    broken = []
    for md in sorted(PRODUCT.glob("*.md")):
        for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", md.read_text()):
            target = urllib.parse.unquote(m.group(2).split("#")[0])
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (md.parent / target).exists():
                broken.append(f"{md.name} -> {target}")
    assert broken == [], f"dead relative links: {broken}"


# ------------------------------------------------------- 3. ids + schedule --

def test_model_ids_are_unique_within_each_table():
    text = REGISTRY.read_text()
    for table in ("## Deterministic and heuristic systems", "## Learned models"):
        body = text.split(table, 1)[1].split("\n##", 1)[0]
        ids = re.findall(r"^\| (MODEL-[A-Z]+-[0-9X]+) \|", body, re.M)
        dupes = {i for i in ids if ids.count(i) > 1}
        assert not dupes, f"duplicate ids in {table}: {sorted(dupes)}"


def _declared_schedulers() -> dict[str, tuple[str, str]]:
    """name -> (cron, target job), parsed from gcp/deploy.sh."""
    return {
        m.group(1): (m.group(2), m.group(3))
        for m in re.finditer(
            r'_schedule(?:_with_args)?\s+"([^"]+)"\s+\\?\s*"([^"]+)"\s+\\?\s*"([^"]+)"',
            DEPLOY.read_text(),
        )
    }


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


def test_scheduled_count_prose_matches_the_table():
    section = _run_section()
    words = {"six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    m = re.search(r"\b(\w+) model-bearing jobs are on a Cloud Scheduler cron", section)
    assert m, "the scheduled-count sentence changed shape"
    stated = words.get(m.group(1).lower())
    assert stated is not None, f"unhandled number word: {m.group(1)}"
    rows = len(re.findall(r"^\| `[a-z0-9-]+` \| `[^`]+` \| `[a-z0-9-]+` \|", section, re.M))
    assert stated == rows, f"prose says {stated} scheduled jobs; the table lists {rows}"


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


def test_status_cells_use_the_declared_vocabulary():
    allowed = _vocab(r"\*\*Model status:\*\*([^\n]*(?:\n[^\n*]*)*?)\.")
    allowed |= {"Production but needs remediation", "Broken"}  # capability-status spellings in use
    text = REGISTRY.read_text()
    bad = []
    for table in ("## Deterministic and heuristic systems", "## Learned models"):
        for line in text.split(table, 1)[1].split("\n##", 1)[0].split("\n"):
            if not re.match(r"^\| MODEL-", line):
                continue
            cells = [c.strip() for c in line.split("|")]
            status = cells[6].strip("* ").split(" — ")[0].strip("* ")
            if status not in allowed:
                bad.append(f"{cells[1]}: {status!r}")
    assert not bad, f"status values outside the README vocabulary: {bad} (allowed: {sorted(allowed)})"


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


def test_experiments_spanning_both_engines_appear_on_both_models():
    """An experiment the ledger scopes to `both` must not be filed under one."""
    area = _ledger_engine_area()
    rows = _traceability_rows()
    cited = {model: set(re.findall(r"E-\d+", cell)) for model, cell in rows.items()}

    both = {e for e, a in area.items() if a.startswith("both")}
    missing = []
    for exp in sorted(both):
        on = {m for m, es in cited.items() if exp in es}
        # Only meaningful for the two engine models the ledger's "both" refers to.
        for model in ("MODEL-TYPE-001", "MODEL-MAG-001"):
            if on and model not in on:
                missing.append(f"{exp} is '{area[exp]}' but is not on {model}")
    assert not missing, (
        "experiments scoped to both engines are filed under only one: "
        f"{missing}. This is how E-19's STRAT half and E-20's magnitude half went missing."
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
        for exp in re.findall(r"E-\d+", cell):
            a = area.get(exp)
            if a is None:
                continue
            if engine in a or a.startswith(("both", "cross-cutting", "precursor")):
                continue
            # Anything else needs a parenthetical saying which arm applies.
            if not re.search(rf"{exp}\s*\([^)]+\)", cell):
                wrong.append(f"{model} cites {exp} ('{a}') unqualified")
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
    uncommitted = {e for p in para for e in re.findall(r"E-\d+", p)}
    # The 2026-07-06 session's table rows name them; pick them up from its header too.
    session = re.search(r"# 2026-07-06 SESSION[^\n]*\(([^)]*)\)", ledger)
    if session:
        uncommitted |= set(re.findall(r"E-\d+", session.group(1)))

    bad = []
    for model, cell in _traceability_rows().items():
        row = REGISTRY.read_text().split(f"| {model} | {cell} |", 1)
        if len(row) < 2:
            continue
        code_cell = row[1].split("|")[0]
        for exp in re.findall(r"E-\d+", cell) :
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
