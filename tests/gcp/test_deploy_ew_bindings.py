"""FEAT-DEPLOY-001: the EarningsWhispers credentials are no longer bound to fetch-earnings-calendar.

Spec: docs/superpowers/specs/2026-11-09-feat-deploy-001-retire-ew-bindings-own-scope.md.
EarningsWhispers is no longer a source (owner decision 2026-10-31), so
`deploy_fetch_earnings_calendar` no longer reads `ew-user` / `ew-pass` from
Secret Manager and no longer appends `EW_USER` / `EW_PASS` to the job's env;
the job's `--set-env-vars` is exactly `${ENV_STRING}` like every other job.
A per-job dispatcher target `earnings-calendar` deploys that job alone, so
the operator step after merge does not run the thirty-job `fetchers` target.
The two secrets stay as Secret Manager resources; nothing here reads,
deletes or rotates them.

Two kinds of test, as in tests/gcp/test_deploy_ew_evaluator.py:

- **Hermetic**, with a recording `gcloud` stub on PATH whose secret reads
  answer sentinel values: what the calendar deploy issues and does not.
- **Differential**, against the fork point named by `DEPLOY_BASELINE_REV`
  (skipped when unset): every other calendar argument, the three
  news-sentiment bodies (another change's), the `fetchers)` arm,
  `deploy_fetchers`, `backfill_watchlist` and the credential-probe
  exemption list are unchanged.

      DEPLOY_BASELINE_REV=<merge-base sha> pytest tests/gcp/test_deploy_ew_bindings.py -q
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

JOB = "fetch-earnings-calendar"
FN = "deploy_fetch_earnings_calendar"
ARM = "earnings-calendar"
EW_SECRETS = ("ew-user", "ew-pass")
EW_NAMES = ("EW_USER", "EW_PASS")
SENTINELS = {"ew-user": "EWU_SENTINEL_7c1d", "ew-pass": "EWP_SENTINEL_9e2f"}
NEWS_FNS = ("deploy_fetch_news_sentiment", "deploy_fetch_news_sentiment_topics",
            "deploy_fetch_news_sentiment_earnings")
UNCHANGED_FNS = ("deploy_fetchers", "backfill_watchlist") + NEWS_FNS

IMAGE = "us-east1-docker.pkg.dev/proj/trading/trading-system"
IMAGE_REF = IMAGE + "@sha256:" + "1" * 64
ENV_STRING = "CLOUD_SQL_CONNECTION_NAME=proj:us-east1:db,DB_USER=trading-app,DB_NAME=trading"

_FN_RE = re.compile(r"^([a-z_][a-z0-9_]*)\(\)\s*\{", re.M)


def _code(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


def _functions(text: str) -> dict[str, str]:
    code = _code(text)
    out = {}
    for name in _FN_RE.findall(code):
        m = re.search(r"^" + re.escape(name) + r"\(\)\s*\{(.*?)^\}", code, re.M | re.S)
        assert m, f"could not delimit {name}"
        out[name] = m.group(1)
    return out


def _raw_body(text: str, name: str) -> str:
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


def _dispatch(text: str) -> str:
    code = _code(text)
    return code[code.index('case "${1:-help}" in'):]


def _dispatch_arms(text: str) -> dict[str, str]:
    """tests/gcp/test_deploy_reachability.py::_dispatch_arms, over a given deploy.sh text."""
    dispatch = _dispatch(text)
    body = dispatch[:dispatch.index("\nesac")]
    arms: dict[str, str] = {}
    for m in re.finditer(r"^\s{4}([a-z0-9|_\-\"]+)\)(.*?);;", body, re.S | re.M):
        for lbl in m.group(1).split("|"):
            arms[lbl.strip().strip('"')] = m.group(2)
    return arms


def _created_by(fns: dict[str, str], names: set[str]) -> set[str]:
    out = set()
    for f in names:
        out |= set(re.findall(r"gcloud run jobs create\s+([A-Za-z0-9\-]+)", fns[f]))
        out |= set(re.findall(r"gcloud run deploy\s+([A-Za-z0-9\-]+)", fns[f]))
    return out


def _flag_exempt_block(text: str) -> str:
    m = re.search(r"\ncase \"\$\{1:-\}\" in\n\s*([^)]+)\)\s*_NEEDS_DEPLOY_CREDS=0", _code(text))
    assert m, "the deploy-credentials case statement moved or changed shape"
    return m.group(1)


def _flag_exempt_targets(text: str) -> set[str]:
    flat = _flag_exempt_block(text).replace("\\", " ").replace("\n", " ")
    return {lbl.strip().strip('"') for lbl in flat.split("|") if lbl.strip()}


# The stub records every argv; secret reads answer the sentinels for the two
# EW secrets and a fixed value otherwise; `run jobs create` fails when
# FAIL_CREATE is set so the update branch is exercised too.
_GCLOUD = """#!/bin/bash
printf '%s\\n' "$*" >> "$OUT/calls"
case "$1 $2 $3" in
  "secrets versions access")
    for a in "$@"; do case "$a" in --secret=*) name=${a#--secret=} ;; esac; done
    case "$name" in
      ew-user) printf '%s' "$EWU" ;;
      ew-pass) printf '%s' "$EWP" ;;
      *) printf '%s' "other-secret-value" ;;
    esac
    exit 0 ;;
  "run jobs create") [ -z "${FAIL_CREATE:-}" ] || exit 1 ;;
esac
exit 0
"""


def _env(tmp_path: Path, fail_create: bool = False) -> dict:
    binder = tmp_path / "bin"
    binder.mkdir(parents=True, exist_ok=True)
    g = binder / "gcloud"
    g.write_text(_GCLOUD)
    g.chmod(g.stat().st_mode | stat.S_IEXEC)
    # Only audited local binaries needed by the calendar/_secret closure.
    # Never inherit SDK search paths, startup scripts, credentials or config.
    for name in ("bash", "mktemp", "head", "rm"):
        executable = Path("/usr/bin") / name
        assert executable.is_file() and os.access(executable, os.X_OK), executable
        target = binder / name
        if not target.exists():
            target.symlink_to(executable)
    home = tmp_path / "home"
    config = tmp_path / "cloud-config"
    home.mkdir(exist_ok=True)
    config.mkdir(exist_ok=True)
    env = dict(PATH=str(binder), HOME=str(home), CLOUDSDK_CONFIG=str(config),
               CLOUDSDK_AUTH_DISABLE_CREDENTIALS="true", LC_ALL="C",
               OUT=str(tmp_path), PROJECT_ID="proj", REGION="us-east1",
               EWU=SENTINELS["ew-user"], EWP=SENTINELS["ew-pass"])
    if fail_create:
        env["FAIL_CREATE"] = "1"
    return env


def _calls(tmp_path: Path) -> list[str]:
    p = tmp_path / "calls"
    return p.read_text().splitlines() if p.exists() else []


def _run_function(tmp_path: Path, text: str, entry: str, fail_create: bool = False) -> tuple[list[str], str]:
    """Run one deploy.sh function (with every function it reaches) against the stub: (argv list, stdout)."""
    fns = _functions(text)
    assert entry in fns, f"{entry} not in this deploy.sh"
    defs = "\n".join(f"{n}() {{{fns[n]}}}" for n in sorted(_closure(fns, {entry})))
    script = f"""set -uo pipefail
PROJECT_ID=proj; REGION=us-east1; SA_EMAIL=sa@proj.iam.gserviceaccount.com
IMAGE={IMAGE}; IMAGE_REF={IMAGE_REF}
DB_SECRET_FLAG='--set-secrets DB_PASSWORD=db-pw:latest'
ENV_STRING='{ENV_STRING}'
pin_image_tags() {{ :; }}
{defs}
{entry}
echo "rc=$?"
"""
    r = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-c", script], capture_output=True, text=True,
                       env=_env(tmp_path, fail_create), cwd=str(REPO), timeout=300)
    assert "rc=" in r.stdout, r.stdout + r.stderr
    return _calls(tmp_path), r.stdout + r.stderr


def _job_mutations(calls: list[str]) -> list[str]:
    return [c for c in calls if c.startswith(("run jobs create", "run jobs update"))]


def _env_arg(call: str) -> str:
    m = re.search(r"--set-env-vars (\S+)", call)
    assert m, call
    return m.group(1)


def _calendar_calls(tmp_path: Path, text: str) -> tuple[list[str], str]:
    """The create argv (stub create succeeds) and the update argv (stub create fails), with stdout."""
    create_calls, out1 = _run_function(tmp_path / "create", text, FN)
    update_calls, out2 = _run_function(tmp_path / "update", text, FN, fail_create=True)
    creates = [c for c in _job_mutations(create_calls) if c.startswith("run jobs create " + JOB)]
    updates = [c for c in _job_mutations(update_calls) if c.startswith("run jobs update " + JOB)]
    assert len(creates) == 1 and len(updates) == 1, (creates, updates)
    return [creates[0], updates[0]], out1 + out2 + "\n".join(create_calls + update_calls)


# ── hermetic ────────────────────────────────────────────────────────────────

def test_create_and_update_env_is_exactly_env_string(tmp_path):
    mutations, _ = _calendar_calls(tmp_path, DEPLOY_SH)
    for call in mutations:
        assert _env_arg(call) == ENV_STRING, call
        assert not any(name in call for name in EW_NAMES), call


def test_no_secret_read_names_an_ew_secret(tmp_path):
    for fail_create in (False, True):
        calls, _ = _run_function(tmp_path / str(fail_create), DEPLOY_SH, FN, fail_create)
        reads = [c for c in calls if c.startswith("secrets versions access")]
        assert not [c for c in reads if any(f"--secret={s}" in c for s in EW_SECRETS)], reads


def test_no_sentinel_appears_anywhere(tmp_path):
    _, everything = _calendar_calls(tmp_path, DEPLOY_SH)
    for value in SENTINELS.values():
        assert value not in everything


def test_earnings_calendar_target_deploys_only_the_calendar_job():
    """In the shape of tests/gcp/test_deploy_reachability.py::test_market_data_target_deploys_only_the_two_price_fetchers."""
    fns = _functions(DEPLOY_SH)
    arms = _dispatch_arms(DEPLOY_SH)
    assert ARM in arms, f"{ARM}) dispatcher target missing"
    called = {f for f in fns if re.search(r"\b" + f + r"\b", arms[ARM])}
    assert _created_by(fns, _closure(fns, called)) == {JOB}, called
    assert "backfill_watchlist" not in arms[ARM] and "deploy_fetchers" not in arms[ARM], arms[ARM]
    assert "build_image" in called, "the arm must build before it deploys (IMAGE_REF)"
    assert "_PIN_AFTER=0" not in arms[ARM], arms[ARM]
    assert ARM not in _flag_exempt_targets(DEPLOY_SH), "the arm reads DB_SECRET_FLAG and ENV_STRING; it is gated"


def test_help_names_the_calendar_target(tmp_path):
    r = subprocess.run(["/bin/bash", "--noprofile", "--norc", "gcp/deploy.sh", "help"], capture_output=True, text=True,
                       env=_env(tmp_path), cwd=str(REPO), timeout=120)
    assert "Usage:" in r.stdout, r.stdout + r.stderr
    assert re.search(r"^\s+" + ARM + r"\b", r.stdout, re.M), r.stdout
    assert _calls(tmp_path) == []


def test_local_env_rejects_ambient_startup_and_sdk_paths(tmp_path, monkeypatch):
    """Benign shell proof only: no deployment source or cloud command runs."""
    marker = tmp_path / "startup-ran"
    startup = tmp_path / "synthetic-startup.sh"
    startup.write_text('printf started > "' + str(marker) + '"\n'
                       'export PATH=/nonexistent-ew-synthetic-path\n'
                       'export CLOUDSDK_CONFIG=/nonexistent-ew-synthetic-config\n')
    monkeypatch.setenv("BASH_ENV", str(startup))
    monkeypatch.setenv("ENV", str(startup))
    monkeypatch.setenv("CLOUDSDK_AUTH_ACCESS_TOKEN", "synthetic-token")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/synthetic/credentials")
    env = _env(tmp_path / "isolated")
    assert set(env) == {"PATH", "HOME", "CLOUDSDK_CONFIG", "CLOUDSDK_AUTH_DISABLE_CREDENTIALS",
                        "LC_ALL", "OUT", "PROJECT_ID", "REGION", "EWU", "EWP"}
    binder = Path(env["PATH"])
    assert (binder / "gcloud").read_text() == _GCLOUD
    assert sorted(p.name for p in binder.iterdir()) == ["bash", "gcloud", "head", "mktemp", "rm"]
    assert not list(Path(env["CLOUDSDK_CONFIG"]).iterdir())
    result = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-c",
                             'printf "%s\\n" "$PATH" "$CLOUDSDK_CONFIG"; command -v gcloud; command -v bash'],
                            env=env, text=True, capture_output=True, timeout=5)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines() == [str(binder), env["CLOUDSDK_CONFIG"],
                                          str(binder / "gcloud"), str(binder / "bash")]
    assert not marker.exists()
    assert _calls(tmp_path / "isolated") == []


# ── differential: against the fork point named by DEPLOY_BASELINE_REV ───────

@pytest.fixture(scope="module")
def baseline() -> str:
    rev = os.environ.get("DEPLOY_BASELINE_REV")
    if not rev:
        pytest.skip("differential evidence for the retiring pull request: set DEPLOY_BASELINE_REV=<merge base>")
    r = subprocess.run(["git", "show", f"{rev}:gcp/deploy.sh"], capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_every_other_calendar_argument_equals_the_baseline(tmp_path, baseline):
    before, _ = _calendar_calls(tmp_path / "base", baseline)
    after, _ = _calendar_calls(tmp_path / "head", DEPLOY_SH)
    suffix = f",EW_USER={SENTINELS['ew-user']},EW_PASS={SENTINELS['ew-pass']}"
    for b, a in zip(before, after):
        assert suffix in b, f"the baseline did not bind the EW credentials: {b}"
        assert b.replace(suffix, "") == a, f"an argument other than the EW env changed:\n{b}\n{a}"


def test_unchanged_functions_and_arms_are_byte_identical_to_the_baseline(baseline):
    for name in UNCHANGED_FNS:
        assert _raw_body(DEPLOY_SH, name) == _raw_body(baseline, name), f"{name} body changed"
    assert _dispatch_arms(DEPLOY_SH)["fetchers"] == _dispatch_arms(baseline)["fetchers"]
    assert _flag_exempt_block(DEPLOY_SH) == _flag_exempt_block(baseline), "the exemption list changed"
    new_arms = set(_dispatch_arms(DEPLOY_SH)) - set(_dispatch_arms(baseline))
    assert new_arms == {ARM}, new_arms
