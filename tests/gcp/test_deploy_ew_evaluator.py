"""FEAT-DEPLOY-001: the evaluate-ew-strikes deployment is retired from gcp/deploy.sh.

Spec: docs/superpowers/specs/2026-10-31-feat-deploy-001-retire-ew-evaluator.md.
EarningsWhispers is no longer a source (owner decision 2026-10-31), so the job
that scored its strike picks is no longer deployed, its 23:00 ET scheduler is
deleted by `deploy_schedulers` in the existing retired-schedule pattern, and
the dispatcher target fails loudly instead of deploying, in the shape of the
`p7b-classifier` stub. The module `gcp/fetchers/evaluate_ew_strikes.py` is
FEAT-DATA-001's and is not touched by this change.

Two kinds of test:

- **Hermetic**, with a recording `gcloud` stub on PATH: what the retired
  pieces do and do not issue. These run everywhere.
- **Differential**, against the fork point: every other `run jobs` and
  `scheduler jobs` argv is unchanged, and the three news-sentiment bodies
  (another change's) are byte-identical. A comparison with a merge base is
  evidence for the pull request that made the change, so these read the
  baseline from `DEPLOY_BASELINE_REV` and skip when it is unset: a permanent
  unconditional comparison would refuse every later legitimate deploy.sh
  change, and a shallow CI checkout has no merge base to read.

      DEPLOY_BASELINE_REV=<merge-base sha> pytest tests/gcp/test_deploy_ew_evaluator.py -q
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DEPLOY_SH = (REPO / "gcp/deploy.sh").read_text()

RETIRED_JOB = "evaluate-ew-strikes"
RETIRED_SCHEDULER = "evaluate-ew-strikes-daily"
RETIRED_FN = "deploy_evaluate_ew_strikes"
RETIRED_MARKERS = (RETIRED_JOB, "evaluate_ew_strikes")
NEWS_FNS = ("deploy_fetch_news_sentiment", "deploy_fetch_news_sentiment_topics",
            "deploy_fetch_news_sentiment_earnings")

IMAGE = "us-east1-docker.pkg.dev/proj/trading/trading-system"
IMAGE_REF = IMAGE + "@sha256:" + "1" * 64

_FN_RE = re.compile(r"^([a-z_][a-z0-9_]*)\(\)\s*\{", re.M)


def _code(text: str) -> str:
    """deploy.sh with comment lines removed: a comment quoting a retired name is not a call."""
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


def _functions(text: str) -> dict[str, str]:
    """name -> body (comment lines stripped) for every function in a deploy.sh text."""
    code = _code(text)
    out = {}
    for name in _FN_RE.findall(code):
        m = re.search(r"^" + re.escape(name) + r"\(\)\s*\{(.*?)^\}", code, re.M | re.S)
        assert m, f"could not delimit {name}"
        out[name] = m.group(1)
    return out


def _raw_body(text: str, name: str) -> str:
    """The function's body exactly as written, comments included, for byte comparison."""
    m = re.search(r"^" + re.escape(name) + r"\(\)\s*\{\n(.*?)^\}", text, re.M | re.S)
    assert m, f"{name} not found"
    return m.group(1)


def _closure(fns: dict[str, str], seed: set[str]) -> set[str]:
    reach, stack = set(), list(seed)
    while stack:
        f = stack.pop()
        if f in reach or f not in fns:
            continue
        reach.add(f)
        stack.extend(g for g in fns if g not in reach and re.search(r"\b" + re.escape(g) + r"\b", fns[f]))
    return reach


# A gcloud that records every argv and answers "exists" to every read, so a
# retired-schedule `_unschedule` goes on to its delete and a create never
# falls through to its update branch (the create is what the argv records).
_GCLOUD = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$OUT/calls"
exit 0
"""


def _env(tmp_path: Path) -> dict:
    binder = tmp_path / "bin"
    binder.mkdir(parents=True, exist_ok=True)
    g = binder / "gcloud"
    g.write_text(_GCLOUD)
    g.chmod(g.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ)
    env.update(PATH=f"{binder}:{env['PATH']}", OUT=str(tmp_path), PROJECT_ID="proj", REGION="us-east1")
    env.pop("DEPLOY_BASELINE_REV", None)
    return env


def _calls(tmp_path: Path) -> list[str]:
    p = tmp_path / "calls"
    return p.read_text().splitlines() if p.exists() else []


def _run_function(tmp_path: Path, text: str, entry: str) -> list[str]:
    """Run one deploy.sh function (with every function it reaches) against the stub; the argv list."""
    fns = _functions(text)
    assert entry in fns, f"{entry} not in this deploy.sh"
    defs = "\n".join(f"{n}() {{{fns[n]}}}" for n in sorted(_closure(fns, {entry})))
    script = f"""set -uo pipefail
PROJECT_ID=proj; REGION=us-east1; SA_EMAIL=sa@proj.iam.gserviceaccount.com
IMAGE={IMAGE}; IMAGE_REF={IMAGE_REF}
DB_SECRET_FLAG='--set-secrets DB_PASSWORD=db-pw:latest'
ENV_STRING='DB_NAME=trading'
pin_image_tags() {{ :; }}
{defs}
{entry}
echo "rc=$?"
"""
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                       env=_env(tmp_path), cwd=str(REPO), timeout=300)
    assert "rc=" in r.stdout, r.stdout + r.stderr
    return _calls(tmp_path)


def _names_retired(call: str) -> bool:
    return any(marker in call for marker in RETIRED_MARKERS)


def _mutations(calls: list[str]) -> list[str]:
    """The job and scheduler argv: what a deploy would create, update or delete."""
    return [c for c in calls if c.startswith(("run jobs", "run deploy", "scheduler jobs"))]


# ── hermetic: what the retired pieces issue ──────────────────────────────────

def test_deploy_fetchers_issues_no_call_naming_the_retired_job(tmp_path):
    calls = _run_function(tmp_path, DEPLOY_SH, "deploy_fetchers")
    assert any(c.startswith("run jobs create") for c in calls), calls[:5]
    assert not [c for c in calls if _names_retired(c)], [c for c in calls if _names_retired(c)]


def test_deploy_schedulers_deletes_the_retired_scheduler_and_creates_no_replacement(tmp_path):
    calls = _run_function(tmp_path, DEPLOY_SH, "deploy_schedulers")
    assert any(c.startswith("scheduler jobs create") for c in calls), calls[:5]
    retired = [c for c in calls if RETIRED_SCHEDULER in c]
    assert [c.split()[:3] for c in retired] == [["scheduler", "jobs", "describe"], ["scheduler", "jobs", "delete"]], retired
    assert all(f" {RETIRED_SCHEDULER} " in c for c in retired), retired
    assert not [c for c in calls if RETIRED_JOB in c and RETIRED_SCHEDULER not in c], \
        "a scheduler call still targets the retired job"


def test_the_dispatcher_target_is_a_retirement_stub(tmp_path):
    """`./gcp/deploy.sh evaluate-ew-strikes` fails loudly and runs no gcloud, like `p7b-classifier`."""
    r = subprocess.run(["bash", "gcp/deploy.sh", RETIRED_JOB], capture_output=True, text=True,
                       env=_env(tmp_path), cwd=str(REPO), timeout=120)
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
    assert "RETIRED" in r.stdout, r.stdout + r.stderr
    assert _calls(tmp_path) == [], _calls(tmp_path)


def test_help_names_no_retired_target(tmp_path):
    r = subprocess.run(["bash", "gcp/deploy.sh", "help"], capture_output=True, text=True,
                       env=_env(tmp_path), cwd=str(REPO), timeout=120)
    assert "Usage:" in r.stdout, r.stdout + r.stderr
    assert RETIRED_JOB not in r.stdout + r.stderr
    assert _calls(tmp_path) == [], _calls(tmp_path)


def _flag_exempt_targets(text: str) -> set[str]:
    """The dispatcher labels that skip resolving DB_SECRET_FLAG (tests/gcp/test_deploy_reachability.py)."""
    m = re.search(r"\ncase \"\$\{1:-\}\" in\n\s*([^)]+)\)\s*_NEEDS_DEPLOY_CREDS=0", _code(text))
    assert m, "the deploy-credentials case statement moved or changed shape"
    flat = m.group(1).replace("\\", " ").replace("\n", " ")
    return {lbl.strip().strip('"') for lbl in flat.split("|") if lbl.strip()}


def test_the_stub_reads_no_secret_so_it_is_exempt_from_the_credential_probe():
    """The stub resolves nothing, so it belongs in the `_NEEDS_DEPLOY_CREDS=0` list beside
    `p7b-classifier`; tests/gcp/test_deploy_reachability.py refuses a gated target that reads no secret."""
    exempt = _flag_exempt_targets(DEPLOY_SH)
    assert "p7b-classifier" in exempt, "the precedent stub left the list"
    assert RETIRED_JOB in exempt, sorted(exempt)


def test_no_function_deploys_the_retired_job():
    fns = _functions(DEPLOY_SH)
    assert RETIRED_FN not in fns, "deploy_evaluate_ew_strikes still defined"
    creators = [n for n, b in fns.items() if re.search(r"gcloud run jobs (create|update)\s+" + RETIRED_JOB + r"\b", b)]
    assert creators == [], creators
    schedulers = [n for n, b in fns.items() if re.search(r'_schedule\w*\s+"' + RETIRED_SCHEDULER + '"', b)]
    assert schedulers == [], schedulers


# ── differential: against the fork point named by DEPLOY_BASELINE_REV ───────

@pytest.fixture(scope="module")
def baseline() -> str:
    rev = os.environ.get("DEPLOY_BASELINE_REV")
    if not rev:
        pytest.skip("differential evidence for the retiring pull request: set DEPLOY_BASELINE_REV=<merge base>")
    r = subprocess.run(["git", "show", f"{rev}:gcp/deploy.sh"], capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_every_other_job_and_scheduler_argv_equals_the_baseline(tmp_path, baseline):
    """Baseline minus the calls naming the retired job and scheduler == working tree minus the
    retirement's own describe and delete; order included."""
    for entry in ("deploy_fetchers", "deploy_schedulers"):
        before = _mutations(_run_function(tmp_path / f"base-{entry}", baseline, entry))
        after = _mutations(_run_function(tmp_path / f"head-{entry}", DEPLOY_SH, entry))
        assert any(_names_retired(c) for c in before), f"{entry}: the baseline never deployed the retired job"
        kept_before = [c for c in before if not _names_retired(c)]
        kept_after = [c for c in after if not _names_retired(c)]
        assert kept_before == kept_after, f"{entry}: an argv other than the retirement changed"
        new = [c for c in after if _names_retired(c)]
        if entry == "deploy_schedulers":
            assert [c.split()[:4] for c in new] == [["scheduler", "jobs", "describe", RETIRED_SCHEDULER],
                                                    ["scheduler", "jobs", "delete", RETIRED_SCHEDULER]], new
        else:
            assert new == [], new


def test_news_sentiment_bodies_are_byte_identical_to_the_baseline(baseline):
    for name in NEWS_FNS:
        assert _raw_body(DEPLOY_SH, name) == _raw_body(baseline, name), f"{name} body changed"
