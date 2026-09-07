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
PROMPTS = ("architecture", "data-dependencies", "cost-analysis", "readme")

# Distinct from every count in the committed fixture and from every number
# written into the prompt prose.
LIVE = {
    "counts": {"jobs": 811, "schedulers": 822, "services": 833, "secrets": 844},
    "db_tables": [{"name": f"t{i}"} for i in range(855)],
}
REPO_INVENTORY = {"repo": {"counts": {"jobs": 866, "schedulers": 877, "tables": 888}}}
# What `verify_docs_against_live.py --write-snapshot` writes: the populations
# it counts, from its own gcloud calls. It must agree with live.json, and the
# renderer refuses rather than hoping.
VERIFY_LIVE = {"run_jobs": ["j"] * 811, "schedulers": {f"s{i}": {} for i in range(822)},
               "services": ["v"] * 833, "secrets": ["k"] * 844}


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


@pytest.mark.parametrize("broken", [
    {"counts": {"jobs": 0, "schedulers": 822, "services": 833, "secrets": 844},
     "db_tables": [1]},
    {"counts": {"jobs": 811, "schedulers": 822, "services": 833, "secrets": 844},
     "db_tables": []},
])
def test_an_empty_snapshot_refuses_to_render(broken):
    """Rule 3.7: a zero count is a broken dump, not a fact to hand the model."""
    with pytest.raises(SystemExit):
        rp.counts(broken, REPO_INVENTORY, VERIFY_LIVE)


def test_a_missing_count_raises_rather_than_defaulting():
    with pytest.raises(KeyError):
        rp.counts({"counts": {"jobs": 1, "schedulers": 2, "services": 3},
                   "db_tables": [1]}, REPO_INVENTORY, VERIFY_LIVE)


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
