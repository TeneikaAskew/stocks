"""The doc-refresh prompts must carry the live counts as literals.

Run 22 of the monthly refresh (2026-09-07) regenerated
`docs/product/infrastructure/05-d-COST_ANALYSIS.md` with "24 Cloud Scheduler
jobs" against a live fleet of 65, and the run went red on that single verifier
finding. The prompt already instructed the model to use the live counts and
named `live.json` as the source, so the fix is not another sentence: the counts
are substituted into the prompt text before the model is called.

Two properties are pinned here, because either one alone is inert:

  * the renderer really substitutes, and refuses anything it cannot resolve, and
  * the workflow really reads the RENDERED prompt -- a future edit that goes
    back to `cat .github/prompts/<name>.md` puts the model back in charge of
    the numbers with every test still green.

The substitution values below are deliberately NOT the ones in the committed
snapshot, so a prompt that was never rendered cannot pass by carrying the
current fleet size somewhere in its prose. And the prose is not allowed to:
the verifier's own count patterns are run over every template below, because
a literal count in the text that tells the model never to carry a literal
count is the same defect one layer up, and it goes stale the same way.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

import pytest
import yaml

import scripts.maintenance.render_doc_prompts as rp

REPO = pathlib.Path(__file__).resolve().parents[2]
PROMPT_DIR = REPO / ".github/prompts"
WORKFLOW = REPO / ".github/workflows/refresh-architecture-docs.yml"
# README is deliberately absent: run 31 showed the model's entire contribution
# to it was three badge lines and a date, both now rendered, and run 32 showed
# the cost of asking anyway (a rewritten intro, four falsified map rows and an
# invented workflow filename). The call and its prompt are gone. (Run 32.)
PROMPTS = ("architecture", "data-dependencies", "cost-analysis")

# Distinct from every count in the committed fixture and from every number
# written into the prompt prose.
# db_tables is keyed by relation name, as doc_inventory writes it; 855 live,
# of which the 700 declared below plus 155 runtime-created.
LIVE = {
    "counts": {"jobs": 811, "schedulers": 822, "services": 5, "secrets": 844},
    "db_tables": {f"t{i}": {} for i in range(855)},
    # Keyed by service name, as doc_inventory's snapshot writes it. The NAMES
    # are substituted as well as the count: run 28 wrote `solyra-api` where the
    # live services are `solyra-api-prod` and `solyra-api-staging`, and the
    # refresh failed on a service that does not exist.
    #
    # Invented names, and FIVE of them rather than the real four, for the same
    # reason every count here is unreal: a prompt that was never rendered must
    # not be able to pass by carrying the true fleet in its prose. Unlike the
    # other counts this one has to equal `len(services)`, because the renderer
    # now cross-checks the name SETS across the two snapshots.
    "services": {f"svc-{n}": {} for n in ("alpha", "bravo", "charlie", "delta", "echo")},
    # The day the snapshot was taken, which the two live as-of labels in 05-a
    # carry. Not today's date, deliberately: a run that snapshots before UTC
    # midnight and calls the model after it has two different days, and this
    # value is the one `gate_stale_asof` compares those labels against.
    "read_at": "2019-03-04T05:06:07Z",
}
REPO_INVENTORY = {"repo": {
    "counts": {"jobs": 866, "schedulers": 877, "tables": 690},
    "tables": [{"name": f"t{i}"} for i in range(690)],
    "views": [{"name": f"t{i}"} for i in range(690, 695)],
    "materialized_views": [{"name": f"t{i}"} for i in range(695, 700)],
}}
# What `verify_docs_against_live.py --write-snapshot` writes: the populations
# it counts, from its own gcloud calls. It must agree with live.json, and the
# renderer refuses rather than hoping.
VERIFY_LIVE = {"run_jobs": ["j"] * 811, "schedulers": {f"s{i}": {} for i in range(822)},
               # The verifier stores service NAMES, and they must be the same
               # names live.json holds: a rename between the two snapshots
               # leaves the count equal and the sets different, which is what
               # the renderer now refuses.
               "services": [f"svc-{n}" for n in ("alpha", "bravo", "charlie", "delta", "echo")],
               "secrets": ["k"] * 844}


@pytest.fixture
def values() -> dict[str, str]:
    return rp.counts(LIVE, REPO_INVENTORY, VERIFY_LIVE)


def test_every_placeholder_in_every_committed_prompt_resolves(values):
    """An unknown name is caught here, not by the model reading raw braces."""
    for name in PROMPTS:
        src = (PROMPT_DIR / f"{name}.md").read_text()
        out = rp.render(src, values, name)
        assert "{{" not in out and "}}" not in out, name


def test_the_cost_prompt_states_the_scheduler_count_as_a_substituted_value(values):
    """The exact line run 22 got wrong."""
    out = rp.render((PROMPT_DIR / "cost-analysis.md").read_text(), values, "cost")
    assert "Cloud Scheduler jobs: **822**" in out
    assert "(822 entries, 3 free)" in out
    assert "all 811 jobs" in out
    # Declared is tables + views + materialized views (700), runtime is the
    # set difference (155): the gate's arithmetic, not the model's.
    assert "**855** live, **700** declared, **155** runtime-created" in out


def test_the_cost_prompt_names_every_live_service(values):
    """Run 28 wrote `solyra-api` for `solyra-api-prod`, twice, and the run went
    red on a service that does not exist. A count cannot prevent that -- the
    count was right. The names are substituted too, so the model copies them.

    Asserted as a SET so a renderer that drops, adds or shortens one fails:
    `solyra-api` is a substring of `solyra-api-prod`, so a substring check
    would pass on exactly the output that broke run 28.
    """
    out = rp.render((PROMPT_DIR / "cost-analysis.md").read_text(), values, "cost")
    line = next(ln for ln in out.split("\n") if ln.startswith("- Cloud Run Services:"))
    assert set(re.findall(r"`([^`]+)`", line)) == set(LIVE["services"])
    assert "**5**" in line


def test_a_rename_between_the_two_snapshots_refuses_to_render():
    """Equal counts do not mean equal names. The two snapshots are taken by
    two scripts from two sets of gcloud calls at different points in the run,
    so a service renamed between them leaves the fleet SIZE unchanged and the
    NAMES different. The verifier checks the finished document against ITS
    snapshot, so rendering a name only `live.json` has would fail the run on a
    name this pipeline supplied -- the exact failure the count cross-check
    exists to prevent, one field over. (Codex, PR #1062.)"""
    renamed = [n for n in VERIFY_LIVE["services"] if n != "svc-echo"] + ["svc-echo-v2"]
    assert len(renamed) == len(VERIFY_LIVE["services"]), "the count must stay equal"
    with pytest.raises(SystemExit) as e:
        rp.counts(LIVE, REPO_INVENTORY, {**VERIFY_LIVE, "services": renamed})
    assert "svc-echo" in str(e.value) and "svc-echo-v2" in str(e.value)


def test_a_service_snapshot_with_no_names_refuses_to_render():
    """Rule 3.7: an empty list is not a fleet, and handing the model one would
    invite it to derive the names it could not read."""
    with pytest.raises(SystemExit) as e:
        rp.counts({**LIVE, "services": {}}, REPO_INVENTORY, VERIFY_LIVE)
    assert "LIVE_SERVICE_NAMES" in str(e.value)


def test_the_service_names_are_a_placeholder_not_prose():
    """The same defect one layer up: a name written into the template goes
    stale on the next rename, and nothing fails."""
    src = (PROMPT_DIR / "cost-analysis.md").read_text()
    assert "{{LIVE_SERVICE_NAMES}}" in src
    rendered = rp.render(src, rp.counts(LIVE, REPO_INVENTORY, VERIFY_LIVE), "cost")
    for name in LIVE["services"]:
        assert name not in src, f"{name} is hardcoded in the template"
        assert name in rendered, name


def test_every_prompt_carries_the_authoritative_block(values):
    """A prompt that never states the counts cannot be expected to use them."""
    for name in PROMPTS:
        src = (PROMPT_DIR / f"{name}.md").read_text()
        assert "Live fleet counts" in src, name
        assert "{{LIVE_SCHEDULERS}}" in src, name


def test_an_unknown_placeholder_is_a_hard_error(values):
    with pytest.raises(SystemExit) as e:
        rp.render("uses {{LIVE_JOBS}} and {{TOTAL_NONSENSE}}", values, "probe.md")
    assert "TOTAL_NONSENSE" in str(e.value)


def test_a_malformed_placeholder_never_reaches_the_model(values):
    """`{{ LIVE_JOBS }}` does not match, and passing it through would put
    literal braces in the prompt."""
    with pytest.raises(SystemExit) as e:
        rp.render("count is {{ LIVE_JOBS }}", values, "probe.md")
    assert "survived rendering" in str(e.value)


# Derived from LIVE so each case is a complete snapshot broken in exactly one
# place. Spelling them out in full let an earlier version omit a key that was
# added later, so the case raised on the missing key and stopped exercising the
# guard it was written for.
@pytest.mark.parametrize("broken", [
    {**LIVE, "counts": {**LIVE["counts"], "jobs": 0}},
    {**LIVE, "db_tables": {}},
])
def test_an_empty_snapshot_refuses_to_render(broken):
    """Rule 3.7: a zero count is a broken dump, not a fact to hand the model."""
    with pytest.raises(SystemExit):
        rp.counts(broken, REPO_INVENTORY, VERIFY_LIVE)


def test_a_missing_count_raises_rather_than_defaulting():
    with pytest.raises(KeyError):
        rp.counts({"counts": {"jobs": 1, "schedulers": 2, "services": 3},
                   "db_tables": {"x": {}}}, REPO_INVENTORY, VERIFY_LIVE)


def test_the_cli_writes_one_rendered_prompt_per_template(tmp_path):
    live = tmp_path / "live.json"
    live.write_text(json.dumps(LIVE))
    inv = tmp_path / "repo_inventory.json"
    inv.write_text(json.dumps(REPO_INVENTORY))
    ver = tmp_path / "verify_live.json"
    ver.write_text(json.dumps(VERIFY_LIVE))
    out = tmp_path / "prompts"
    rc = subprocess.run(
        [sys.executable, "-m", "scripts.maintenance.render_doc_prompts",
         "--live", str(live), "--repo-inventory", str(inv),
         "--verify-live", str(ver),
         "--prompts", str(PROMPT_DIR), "--out", str(out)],
        cwd=REPO, capture_output=True, text=True)
    assert rc.returncode == 0, rc.stderr
    for name in PROMPTS:
        body = (out / f"{name}.md").read_text()
        assert "{{" not in body, name
        assert "**822**" in body, name


# ── the workflow must consume what the renderer produced ────────────────────

def _refresh_steps() -> list[dict]:
    wf = yaml.safe_load(WORKFLOW.read_text())
    return wf["jobs"]["refresh"]["steps"]


def test_the_workflow_renders_the_prompts_before_calling_gemini():
    steps = _refresh_steps()
    runs = [s.get("run", "") for s in steps]
    render_at = [i for i, r in enumerate(runs)
                 if "scripts.maintenance.render_doc_prompts" in r]
    assert len(render_at) == 1, "exactly one render step expected"
    gemini_at = [i for i, r in enumerate(runs) if "gemini --model" in r]
    assert gemini_at, "no gemini step found — this test is looking at the wrong file"
    assert render_at[0] < min(gemini_at), "prompts are rendered after the model ran"


def test_no_gemini_step_reads_an_unrendered_prompt():
    """The guard that keeps the fix alive.

    Reverting to `cat .github/prompts/cost-analysis.md` restores exactly the
    run-22 failure with every other assertion in this file still passing.
    """
    for step in _refresh_steps():
        run = step.get("run", "")
        if "gemini --model" not in run:
            continue
        assert ".github/prompts/" not in run, step.get("name")
        used = re.findall(r'--prompt "\$\(cat "\$RUNNER_TEMP/prompts/([a-z-]+)\.md"\)"', run)
        assert len(used) == 1, f"{step.get('name')}: {run!r}"
        assert used[0] in PROMPTS, used


def test_every_prompt_template_is_invoked_by_the_workflow():
    """A template nobody renders is dead weight; a name mismatch is a 404 at
    3am on the first of the month."""
    runs = " ".join(s.get("run", "") for s in _refresh_steps())
    on_disk = {p.stem for p in PROMPT_DIR.glob("*.md")}
    invoked = set(re.findall(r'\$RUNNER_TEMP/prompts/([a-z-]+)\.md', runs))
    assert on_disk == set(PROMPTS)
    assert on_disk <= invoked, on_disk - invoked


@pytest.mark.parametrize("key,label", [("run_jobs", "LIVE_JOBS"),
                                       ("schedulers", "LIVE_SCHEDULERS"),
                                       ("services", "LIVE_SERVICES"),
                                       ("secrets", "LIVE_SECRETS")])
def test_the_two_live_snapshots_must_agree(key, label):
    """`live.json` and `verify_live.json` are taken by different scripts from
    separate gcloud calls. Handing the model a number out of one that the
    other will then reject would fail a gate on a value the pipeline itself
    supplied, and the message would blame the document."""
    short = dict(VERIFY_LIVE)
    short[key] = (list(VERIFY_LIVE[key])[:-1] if not isinstance(VERIFY_LIVE[key], dict)
                  else dict(list(VERIFY_LIVE[key].items())[:-1]))
    with pytest.raises(SystemExit) as e:
        rp.counts(LIVE, REPO_INVENTORY, short)
    assert label in str(e.value) and "disagree" in str(e.value)


def test_the_verified_counts_are_the_ones_the_verifier_can_flag():
    """If verify_docs_against_live.py learns to check another population, the
    cross-check must learn it too, or that count goes back to being a guess."""
    import re as _re
    src = (REPO / "scripts/verify_docs_against_live.py").read_text()
    block = src[src.index("COUNT_CLAIMS"):src.index("def check_counts")]
    checked = set(_re.findall(r'^\s*"(run_jobs|services|schedulers|secrets|queues)"',
                              block, _re.M))
    assert checked == {k for _, k in rp.VERIFIED}, checked


def test_no_prompt_carries_a_fleet_count_of_its_own():
    """The prompts once said `wrote "24 Cloud Scheduler jobs" against a live
    fleet of 65`. Both numbers were true on 2026-09-07 and both go stale, in a
    paragraph whose whole point is that the model must not carry a stale
    count. Checked with the verifier's own COUNT_CLAIMS, so the vocabulary is
    the one that gates the documents, not a second one written here."""
    import importlib.util
    # Registered before exec, as tests/scripts/test_verify_docs_against_live.py
    # does: the module's dataclass resolves its own name through sys.modules.
    spec = importlib.util.spec_from_file_location(
        "verify_docs_against_live", REPO / "scripts/verify_docs_against_live.py")
    vd = sys.modules.get("verify_docs_against_live") or importlib.util.module_from_spec(spec)
    if "verify_docs_against_live" not in sys.modules:
        sys.modules["verify_docs_against_live"] = vd
        spec.loader.exec_module(vd)
    for name in PROMPTS:
        text = rp.PLACEHOLDER.sub("", (PROMPT_DIR / f"{name}.md").read_text())
        # `§6 Cloud Run Jobs` is a section reference, not a fleet size. The
        # verifier has no such exemption, which is why the documents write
        # "## 6. Cloud Run Jobs" -- the dot breaks the pattern -- and why a
        # doc that ever wrote "§6 Cloud Run Jobs" would go red. Here the
        # section number is dropped so the reference itself is not the claim.
        text = re.sub(r"§\d+", "§", text)
        for pattern, _key, label in vd.COUNT_CLAIMS:
            m = pattern.search(text)
            assert m is None, f"{name}.md carries a literal count claim: {m.group(0)!r} ({label})"


def test_the_runtime_relation_count_is_the_gates_own_arithmetic():
    """Run 24: three "runtime relations" findings, 26/28/30 against 27. The
    number now comes from check_generated_docs.relation_counts, which is the
    function that will judge it, and a zero is a legitimate value."""
    import scripts.maintenance.check_generated_docs as gate
    declared, runtime = gate.relation_counts(REPO_INVENTORY["repo"], LIVE)
    vals = rp.counts(LIVE, REPO_INVENTORY, VERIFY_LIVE)
    assert (vals["DECLARED_RELATIONS"], vals["RUNTIME_RELATIONS"]) == (str(declared), str(runtime)) == ("700", "155")
    nothing_extra = dict(LIVE, db_tables={f"t{i}": {} for i in range(700)})
    assert rp.counts(nothing_extra, REPO_INVENTORY, VERIFY_LIVE)["RUNTIME_RELATIONS"] == "0"
    for name in PROMPTS:
        assert "{{RUNTIME_RELATIONS}}" in (PROMPT_DIR / f"{name}.md").read_text(), name



def test_the_05c_prompt_reads_the_digest_not_the_raw_graph():
    """Runs 20, 21 and 25 (twice) died at the 05-c step and nowhere else. The
    prompt sent the model to repo_inventory.json (400 KB, table_refs 220 KB)
    to derive prose the workflow already renders, and to redraw the §7 graph.
    It now reads a digest (50 KB on the committed fixture) and names the prose
    it may edit; the graph is a rendered block."""
    src = (PROMPT_DIR / "data-dependencies.md").read_text()
    inputs = src.split("## Inputs", 1)[1].split("## What ", 1)[0]
    assert "`table_refs_digest.md`" in inputs
    assert "- `repo_inventory.json`" not in inputs and "- `live.json`" not in inputs
    assert "graph" in src and "you do not draw it" in src
    # And the workflow produces the digest before the prompts are rendered.
    import yaml
    steps = yaml.safe_load((REPO / ".github/workflows/refresh-architecture-docs.yml").read_text())["jobs"]["refresh"]["steps"]
    names = [s.get("name") for s in steps]
    digest_i = next(i for i, s in enumerate(steps) if "table_refs_digest.md" in (s.get("run") or ""))
    assert digest_i < names.index("Render prompts with the live counts substituted in")
    assert "--markdown refs_digest" in steps[digest_i]["run"]


def test_every_digest_section_the_05c_prompt_cites_exists_in_the_digest():
    """The prompt sends the model to named sections of `table_refs_digest.md`.
    A name that no longer matches a heading does not fail anything: the model
    hunts for it, which is what the 05-c step was doing for the 5m18s of
    silence before the connection dropped. Rendered from the committed
    fixture, so a renamed heading fails here rather than in production."""
    import scripts.maintenance.doc_inventory as inv
    live = json.loads((REPO / "tests/fixtures/live_gcp_snapshot_2026-09-07.json").read_text())
    digest = inv.render_markdown("refs_digest", inv.repo_inventory(), live)
    headings = [l.lstrip("# ").strip() for l in digest.splitlines() if l.startswith("## ")]
    src = (PROMPT_DIR / "data-dependencies.md").read_text()
    cited = set(re.findall(r"the digest's \*\*([^*]+)\*\* section", src))
    assert cited, "the prompt must name the digest sections it reads"
    for name in sorted(cited):
        assert any(h.startswith(name) for h in headings), \
            f"the 05-c prompt sends the model to a digest section '{name}' that is not a heading: {headings}"
    # The two live-only name sets the prose states come from here and nowhere
    # else, so they must both be among the sections it cites.
    assert {"Runtime-created relations", "Hand-created live jobs"} <= cited


def test_every_prompt_forbids_the_hand_maintained_folder():
    """docs/product/infrastructure/manual/ holds the hand-edited copies of
    the four refreshed documents; the workflow's write policy and stray-write
    scan already fail a change there, and the prompts say so up front."""
    for name in ("architecture.md", "data-dependencies.md", "cost-analysis.md"):
        text = (REPO / ".github/prompts" / name).read_text()
        assert "docs/product/infrastructure/manual/" in text, name
        assert "Never read or write anything under `docs/product/infrastructure/manual/`" in text, name


def test_no_manual_copy_claims_to_be_auto_refreshed():
    """A copied maintenance banner told an owner the monthly workflow rewrites
    the file and overwrites its marker blocks. Nothing automated writes to
    docs/product/infrastructure/manual/, so every copy says so up front and
    no line there claims otherwise for itself. (Codex, PR #1044.)"""
    manual = REPO / "docs/product/infrastructure/manual"
    for doc in ("05-a-ARCHITECTURE.md", "05-c-DATA_DEPENDENCIES.md", "05-d-COST_ANALYSIS.md", "ROOT-README.md"):
        text = (manual / doc).read_text()
        head = text.split("\n\n")[1] if "\n\n" in text else text
        assert "Hand-maintained snapshot — nothing automated writes to this file." in head, doc
        for line in text.splitlines():
            low = line.lower()
            if "monthly refresh" not in low and "refresh workflow" not in low:
                continue
            # every surviving mention must name the original, not this copy
            assert any(k in line for k in ("../05-", "../../../../README.md", "the original",
                                           "ORIGINAL", "docs/product/infrastructure/",
                                           "is not refreshed", "are frozen", "write policy")), (doc, line[:150])


def test_the_manual_readme_points_at_its_own_siblings():
    """The copy's core links left the snapshot for the auto-refreshed
    documents, so after a refresh it mixed frozen prose with fresh tables."""
    text = (REPO / "docs/product/infrastructure/manual/ROOT-README.md").read_text()
    for doc in ("05-a-ARCHITECTURE.md", "05-c-DATA_DEPENDENCIES.md", "05-d-COST_ANALYSIS.md"):
        assert f"]({doc}" in text, doc
        assert f"](../../../../docs/product/infrastructure/{doc}" not in text, doc
    # a document with no manual counterpart keeps its repo-relative link
    assert "](../../../../RUNBOOK.md)" in text


def test_a_manual_copy_links_to_its_siblings_not_to_the_refreshed_originals():
    """The three companion pointers (05-a -> 05-c/05-d, 05-c -> 05-a,
    05-d -> 05-a) still crossed into the auto-refreshed folder, so a reader in
    the frozen snapshot who followed one landed in a document the monthly
    workflow rewrites. A link to a refreshed document is allowed only on a
    line that says it is talking ABOUT the original. (Codex, PR #1044.)"""
    import re
    manual = REPO / "docs/product/infrastructure/manual"
    copied = {"05-a-ARCHITECTURE.md", "05-c-DATA_DEPENDENCIES.md",
              "05-d-COST_ANALYSIS.md", "../../../../README.md"}
    # a line may point at the refreshed original only while describing it
    describes_original = ("ORIGINAL", "the original", "taken on 2026", "regenerated monthly")
    offenders = []
    for f in sorted(manual.glob("*.md")):
        for i, line in enumerate(f.read_text().splitlines(), 1):
            for target in re.findall(r"\]\((\.\./[^)\s#`]+)", line):
                name = target.rsplit("/", 1)[-1]
                if name not in copied and target not in copied:
                    continue
                if any(k in line for k in describes_original):
                    continue
                offenders.append(f"{f.name}:{i} -> {target}")
    assert not offenders, offenders


def test_the_hand_maintained_copies_exist_and_link_correctly():
    manual = REPO / "docs/product/infrastructure/manual"
    for doc in ("05-a-ARCHITECTURE.md", "05-c-DATA_DEPENDENCIES.md", "05-d-COST_ANALYSIS.md", "ROOT-README.md", "README.md"):
        assert (manual / doc).exists(), doc
    import re
    for f in manual.glob("*.md"):
        for m in re.finditer(r"\]\(([^)\s#`]+)", f.read_text()):
            target = m.group(1)
            if target.startswith(("http", "mailto:")):
                continue
            assert (f.parent / target).resolve().exists(), (f.name, target)


def test_the_snapshot_date_is_substituted_not_called_today(values):
    """The two live as-of labels in 05-a describe the SNAPSHOT; the `Generated`
    stamp describes the run. They are the same day on almost every run and
    different on one that crosses UTC midnight between the two, and
    `gate_stale_asof` compares the labels against `read_at` — so a prompt that
    said "use today" would have the model write a date its own gate rejects.
    (Codex, PR #1062.)"""
    assert values["LIVE_READ_DATE"] == "2019-03-04"
    src = (PROMPT_DIR / "architecture.md").read_text()
    assert "{{LIVE_READ_DATE}}" in src
    out = rp.render(src, values, "architecture")
    assert "2019-03-04" in out


def test_a_snapshot_without_a_read_date_refuses_to_render():
    """`read_at` is what every live as-of label in the regenerated documents is
    checked against. A snapshot missing it, or carrying something that is not a
    date, cannot produce a document that passes its own gate."""
    for broken in ({**LIVE, "read_at": ""}, {**LIVE, "read_at": "yesterday"}):
        with pytest.raises(SystemExit) as e:
            rp.counts(broken, REPO_INVENTORY, VERIFY_LIVE)
        assert "LIVE_READ_DATE" in str(e.value)


def test_the_workflow_validates_exactly_the_prompts_that_exist():
    """Removing a prompt and leaving its name in the workflow's validation loop
    makes EVERY run exit there under `set -e`, before anything else happens.
    That is what deleting `.github/prompts/readme.md` did: the loop still ran
    `test -s "$RUNNER_TEMP/prompts/readme.md"`, so the refresh would have died
    at the render step on every dispatch. Both sides are derived here so they
    cannot drift apart again. (Codex, PR #1070.)"""
    import re
    wf = (REPO / ".github/workflows/refresh-architecture-docs.yml").read_text()
    loop = re.search(r"for P in ([a-z0-9\- ]+); do\n\s*test -s \"\$RUNNER_TEMP/prompts/\$\{P\}\.md\"",
                     wf)
    assert loop, "the prompt-validation loop is gone or reshaped; this test cannot see it"
    validated = set(loop.group(1).split())
    on_disk = {p.stem for p in (REPO / ".github/prompts").glob("*.md")}
    assert validated == on_disk, (
        f"the workflow validates {sorted(validated)} but {sorted(on_disk)} exist; "
        "a name here with no file fails every run at the render step")
    assert validated == set(PROMPTS), f"{sorted(validated)} != {sorted(PROMPTS)}"
