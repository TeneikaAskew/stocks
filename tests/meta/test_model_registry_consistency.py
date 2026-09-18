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
KNOWN_BACKLOG = {
    "02-FEATURE-CATALOG.md": 0,
    "04-BACKEND-API.md": 0,
    "09-SECURITY-AUTH.md": 0,
    "11-CODE-TRACEABILITY.md": 0,
    "14-WORK-BREAKDOWN.md": 2,
    "16-CONSOLIDATION-AUDIT.md": 0,
    "README.md": 0,
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
    """name -> (cron, target job), parsed from gcp/deploy.sh.

    COMMENTED-OUT declarations are excluded. `deploy.sh:4488` carries a
    disabled `p7b-classifier-daily` whose surrounding comment says to
    uncomment it only once a profitable cell is found; a parser that reads it
    would let an inactive scheduler be added to the registry table and still
    pass. `tests/gcp/test_deploy_reachability.py:89` independently asserts
    that commented schedule lines are ignored, so this matches that contract.
    """
    out: dict[str, tuple[str, str]] = {}
    pending = ""
    for raw in DEPLOY.read_text().split("\n"):
        line = raw.strip()
        if line.startswith("#"):
            pending = ""
            continue
        joined = (pending + " " + line).strip() if pending else line
        pending = joined if joined.endswith("\\") else ""
        m = re.search(
            # EVERY scheduler helper, not just two. deploy.sh declares entries
            # through _schedule, _schedule_args, _schedule_with_args,
            # _schedule_brief, _schedule_insight, _schedule_verified,
            # _schedule_with_args_verified and _schedule_min_instances; all share
            # the same "name" "cron" "job" prefix. Parsing only the first two made
            # refresh-earnings-views-daily invisible to the completeness gate.
            r'_schedule[a-z_]*\s+"([^"]+)"\s+\\?\s*"([^"]+)"\s+\\?\s*"([^"]+)"',
            joined.replace("\\", " "),
        )
        if m:
            out[m.group(1)] = (m.group(2), m.group(3))
            pending = ""
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


def test_status_cells_use_the_declared_vocabulary():
    allowed = _vocab(r"\*\*Model status:\*\*([^\n]*(?:\n[^\n*]*)*?)\.")
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

def _expand_experiment_ranges(text: str) -> set[str]:
    """`E-26 ... E-31, E-33` means seven ids, not three.

    `re.findall(r"E-\\d+")` takes only the endpoints, so E-27..E-30 were never
    marked uncommitted and could have been attached to a model beside a code
    path without the reproducibility check firing.
    """
    found: set[str] = set()
    for m in re.finditer(r"E-(\d+)\s*(?:\u2026|\.\.\.|--|\u2013|\u2014)\s*E-(\d+)", text):
        lo, hi = int(m.group(1)), int(m.group(2))
        found |= {f"E-{n:02d}" for n in range(lo, hi + 1)}
    found |= set(re.findall(r"E-\d+", text))
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
    scopes = {e: _engines(a) for e, a in _ledger_engine_area().items()}
    scopes.update({e: _engines(a) for e, a in LEDGER_SCOPE_OVERRIDES.items()})
    cited = {model: set(re.findall(r"E-\d+", cell))
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
            if engine in engines or (not engines and
                                     str(a).startswith(("cross-cutting", "precursor"))):
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
        uncommitted |= _expand_experiment_ranges(session.group(1))

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
    """A doc that names a live implementation must have it in the registry's Code cell.

    MODEL-MR-001's doc was corrected to say `lib.signals.evaluate_signal` is the
    production path while the registry row still listed only the class that
    production never calls -- so the governance inventory pointed at the wrong
    code for a live model, and nothing noticed.
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
        # The doc may name the live path as a file (`lib/signals.py`) or as a
        # dotted symbol (`lib.signals.evaluate_signal`). A first version of this
        # test only matched the file form, matched NOTHING, and passed -- the
        # vacuous-green failure this suite keeps re-learning. Hence `found`.
        for m in re.finditer(
                r"`([A-Za-z0-9_./]+)`[^\n]{0,90}?\*\*(?:The )?[Ll]ive implementation", body):
            raw = m.group(1)
            if raw.endswith(".py"):
                path = raw
            else:                      # lib.signals.evaluate_signal -> lib/signals.py
                parts = raw.split(".")
                path = None
                for cut in range(len(parts), 1, -1):
                    cand = "/".join(parts[:cut]) + ".py"
                    if (REPO / cand).exists():
                        path = cand
                        break
                if path is None:
                    continue
            found += 1
            if mid in code_cell and path.rsplit("/", 1)[-1] not in code_cell[mid]:
                missing.append(f"{mid}: doc names {path} as live; registry Code cell omits it")
    assert found, (
        "no model doc names a live implementation -- the parser matched nothing, "
        "so this test would pass no matter what the registry said."
    )
    assert not missing, (
        f"registry Code cells disagree with their model docs: {missing}. "
        "Correcting the doc and leaving the row is how MODEL-MR-001 kept pointing "
        "at a class production never calls."
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
#: A job is model-bearing when it executes code cited in a MODEL-* row. The live
#: fire path was missing from this tuple until 2026-09-17, so the completeness
#: check reported green while the registry omitted `signal-monitor` -- the job that
#: evaluates MOM, MR, AGREE, EXIT and BRIEF every trading morning. A substring list
#: is only as complete as its author; that is the standing weakness here.
MODEL_BEARING = ("magnitude", "strat-engine", "direction", "calibrate-thresholds",
                 "regime-combo", "audit-walkforward", "audit-brief-bias",
                 "p2-build-gamma-levels", "audit-magnitude-drift",
                 "signal-monitor", "build-realtime-gex", "refresh-earnings-views")

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
    )
    assert not missing, (
        f"model-bearing scheduler entries absent from the table: {missing}. "
        "This is how audit-brief-bias-weekly was missed one round after the "
        "gamma omission was 'gated', and how signal-monitor-daily -- the entry that "
        "fires the live strategies -- was missed the round after that."
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
