"""#1171: every Cloud Run job is deployed by the digest its own build produced.

Cloud Run re-resolves a job's image TAG at each execution. A job whose spec
names `trading/trading-system` (tag-less, so `:latest`) runs whatever `:latest`
is when the execution starts. Measured 2026-09-25:
- `fetch-av-options-realtime` and `premarket-brief` ran a new digest the
  morning after `./gcp/deploy.sh signal-quality` built one.
- Their generations were unchanged: neither job had been touched.

A build for one narrow target therefore rolled out to the 50 of 76 jobs whose
spec floated. `gcp/deploy.sh:107-110` said the opposite ("every later execution
runs that exact digest"), and that comment was what the #1169 deploy was
reasoned from.

These tests pin the fix in both directions:

- **Statically:** no job or service is deployed by a tag. Every `--image`
  names either `${IMAGE_REF}`, the digest `build_image` read back from its own
  build, or a research ref resolved to a digest. Every dispatcher target that
  deploys the main image builds it first, so `${IMAGE_REF:?}` can never fire
  on a legitimate path.
- **Executably, with a stub gcloud on PATH:**
  - `build_image` takes the digest from the build record, never from the tag
    afterwards, which a concurrent build can move.
  - It waits for a build still running and fails on a failed one.
  - A deploy names that digest.
  - A deploy with no build aborts before any `gcloud run jobs` mutation.
  - A misspelt target exits 2.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEPLOY_SH = (REPO / "gcp/deploy.sh").read_text()
# Comment lines would otherwise count: the header comments quote the old form.
CODE = "\n".join(l for l in DEPLOY_SH.splitlines() if not l.lstrip().startswith("#"))

_FN_RE = re.compile(r"^([a-z_][a-z0-9_]*)\(\)\s*\{", re.M)


def _fn(name: str) -> str:
    m = re.search(r"^" + name + r"\(\)\s*\{(.*?)^\}", CODE, re.M | re.S)
    assert m, f"{name} not found in deploy.sh"
    return m.group(1)


FNS = {name: _fn(name) for name in _FN_RE.findall(CODE)}
DISPATCH = CODE[CODE.index('case "${1:-help}" in'):]

IMAGE = "us-east1-docker.pkg.dev/proj/trading/trading-system"
BUILT = "sha256:" + "1" * 64
RESEARCH_BUILT = "sha256:" + "2" * 64
RESOLVED = "sha256:" + "3" * 64


# ── static: nothing is deployed by a tag ───────────────────────────────────

def _image_args() -> list[tuple[str, str]]:
    """(function, --image argument) for every --image in a function body."""
    out = []
    for name, body in FNS.items():
        for m in re.finditer(r"--image[= ](\"[^\"]*\"|\S+)", body):
            out.append((name, m.group(1)))
    return out


def test_every_image_argument_is_a_digest_ref_not_a_tag():
    """The class guard: an --image argument is `${IMAGE_REF:?...}` or the
    research ref. A bare `${IMAGE}` or a `:research` tag is how a job floats."""
    args = _image_args()
    assert len(args) > 100, f"found only {len(args)} --image sites; the parser broke"
    # apply_schema_via_build writes a Cloud Build config whose --image is its
    # own `digest`, which is IMAGE_REF or a :latest lookup resolved to a digest
    # (checked below), so it is a digest ref too.
    floating = [(f, a) for f, a in args
                if not (a.startswith('"${IMAGE_REF:?') or a == '"${research_image}"'
                        or (f == "apply_schema_via_build" and a == "${digest}"))]
    assert not floating, f"--image passed something other than a digest ref: {floating[:10]}"


def test_the_schema_apply_build_prefers_the_digest_this_run_built():
    """apply_schema_via_build runs right after build_image in `apply-schema`.
    It used to re-read :latest, which a concurrent build can move."""
    body = FNS["apply_schema_via_build"]
    assert "digest=${IMAGE_REF:-}" in body
    assert body.index("digest=${IMAGE_REF:-}") < body.index("images describe")


def test_research_refs_are_resolved_to_a_digest():
    """research_image is assigned from _research_image_ref only, never from
    the literal tag."""
    assigned = {n for n, b in FNS.items() if re.search(r"\bresearch_image=", b)}
    literal = {n for n in assigned if '"${IMAGE}:research"' in FNS[n]}
    assert not literal, f"research image assigned as a floating tag in {sorted(literal)}"
    for n in assigned:
        assert "research_image=$(_research_image_ref) || return 1" in FNS[n], n
    users = {n for n, a in _image_args() if a == '"${research_image}"'}
    assert users <= assigned, f"use without assignment: {sorted(users - assigned)}"


def _closure(seed: set[str]) -> set[str]:
    reach, stack = set(), list(seed)
    while stack:
        f = stack.pop()
        if f in reach or f not in FNS:
            continue
        reach.add(f)
        stack.extend(g for g in FNS if re.search(r"\b" + re.escape(g) + r"\b", FNS[f]))
    return reach


def test_every_target_that_deploys_the_main_image_builds_it_first():
    """`${IMAGE_REF:?}` aborts a deploy that has not built. That is only safe
    if every target reaching such a deploy runs build_image before it, which
    is true today (2026-09-26) and pinned here so a new target cannot
    silently lose it."""
    uses_ref = {n for n, b in FNS.items() if "${IMAGE_REF:?" in b}
    assert uses_ref, "no function uses IMAGE_REF"
    arms = re.findall(r"^\s+([a-z0-9|-]+)\)\s*(.*?);;", DISPATCH, re.M | re.S)
    offenders = []
    for label, body in arms:
        called = [t for t in re.findall(r"\b([a-z_][a-z0-9_]*)\b", body) if t in FNS]
        needs = [c for c in called if _closure({c}) & uses_ref]
        if not needs:
            continue
        builds_at = min((i for i, c in enumerate(called) if "build_image" in _closure({c})),
                        default=None)
        first_need = called.index(needs[0])
        if builds_at is None or builds_at > first_need:
            offenders.append(label)
    assert not offenders, f"these targets deploy the main image without building it first: {offenders}"


# ── executable: stub gcloud on PATH ────────────────────────────────────────

# Records every call. Builds: submit prints an id; describe answers from
# $OUT/statuses (one line per call, the last line repeating), with the
# results.images digests of a real build (untagged and tagged, one digest).
_GCLOUD = r"""
    echo "$*" >> "$OUT/calls"
    case "$1 $2" in
      "builds submit")
        case "$*" in *--async*) ;; *) echo "stub: builds submit without --async" >&2; exit 9 ;; esac
        tag=""; prev=""
        for a in "$@"; do [ "$prev" = "--tag" ] && tag=$a; prev=$a; done
        echo "$tag" > "$OUT/submitted_tag"
        echo "build-123"; exit 0 ;;
      "builds log") echo "Step 1/9 : FROM python"; exit 0 ;;
      "builds describe")
        n=$(cat "$OUT/describe_n" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "$OUT/describe_n"
        status=$(sed -n "${n}p" "$OUT/statuses"); [ -n "$status" ] || status=$(tail -n1 "$OUT/statuses")
        tag=$(cat "$OUT/submitted_tag")
        printf '%s\t%s;%s\n' "$status" "${BUILD_DIGEST}" "${BUILD_DIGEST}"
        exit 0 ;;
      "artifacts docker")
        echo "${RESOLVE_DIGEST}"; exit 0 ;;
      "run jobs") exit 0 ;;
      "run deploy") exit 0 ;;
    esac
    exit 0
"""


def _env(tmp_path, statuses=("SUCCESS",), build_digest=BUILT, resolve_digest=RESOLVED) -> dict:
    binder = tmp_path / "bin"
    binder.mkdir(exist_ok=True)
    g = binder / "gcloud"
    g.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(_GCLOUD))
    g.chmod(g.stat().st_mode | stat.S_IEXEC)
    (tmp_path / "statuses").write_text("\n".join(statuses) + "\n")
    env = dict(os.environ)
    env.update(PATH=f"{binder}:{env['PATH']}", OUT=str(tmp_path),
               BUILD_DIGEST=build_digest, RESOLVE_DIGEST=resolve_digest,
               BUILD_POLL_SECONDS="0")
    return env


def _run(tmp_path, env, fns: tuple[str, ...], call: str, pre: str = "") -> subprocess.CompletedProcess:
    defs = "\n".join(f"{n}() {{{_fn(n)}}}" for n in fns)
    script = f"""set -uo pipefail
PROJECT_ID=proj; REGION=us-east1; SA_EMAIL=sa@proj.iam.gserviceaccount.com
IMAGE={IMAGE}; DB_SECRET_FLAG='--set-secrets DB_PASSWORD=db-pw:latest'
ENV_STRING='DB_NAME=trading'
pin_image_tags() {{ echo PINNED >> "$OUT/calls"; }}
{defs}
{pre}
cd {REPO}
{call}
echo "rc=$?"
"""
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                          env=env, cwd=str(REPO), timeout=120)


def _calls(tmp_path) -> list[str]:
    p = tmp_path / "calls"
    return p.read_text().splitlines() if p.exists() else []


_BUILD_FNS = ("_split_tsv", "_pkgdev_path", "_resolve_image_ref", "_submit_build",
              "build_image", "build_research_image", "_research_image_ref")


def test_build_image_exports_the_digest_its_own_build_pushed(tmp_path):
    env = _env(tmp_path)
    r = _run(tmp_path, env, _BUILD_FNS, 'build_image && echo "IMAGE_REF=${IMAGE_REF}"')
    assert f"IMAGE_REF={IMAGE}@{BUILT}" in r.stdout, r.stdout + r.stderr
    calls = _calls(tmp_path)
    assert any(c.startswith("builds submit") and "--async" in c for c in calls), calls
    # From the build record, never from the tag: another build can move the
    # tag between this build finishing and anyone reading it.
    assert not any(c.startswith("artifacts docker images describe") for c in calls), calls


def test_build_image_waits_for_a_build_that_is_still_running(tmp_path):
    env = _env(tmp_path, statuses=("QUEUED", "WORKING", "WORKING", "SUCCESS"))
    r = _run(tmp_path, env, _BUILD_FNS, 'build_image && echo "IMAGE_REF=${IMAGE_REF}"')
    assert f"IMAGE_REF={IMAGE}@{BUILT}" in r.stdout, r.stdout + r.stderr
    assert sum(c.startswith("builds describe") for c in _calls(tmp_path)) == 4


def test_a_failed_build_fails_and_exports_nothing(tmp_path):
    env = _env(tmp_path, statuses=("FAILURE",))
    r = _run(tmp_path, env, _BUILD_FNS,
             'if build_image; then echo BUILT; else echo "FAILED ref=${IMAGE_REF:-<unset>}"; fi')
    assert "FAILED ref=<unset>" in r.stdout, r.stdout + r.stderr


def test_a_build_with_two_different_digests_is_refused(tmp_path):
    """A build record naming two digests is not one image; refuse rather than
    pick one."""
    env = _env(tmp_path)
    env["BUILD_DIGEST"] = BUILT + ";" + RESEARCH_BUILT
    r = _run(tmp_path, env, _BUILD_FNS,
             'if build_image; then echo "BUILT ${IMAGE_REF}"; else echo FAILED; fi')
    assert "FAILED" in r.stdout, r.stdout + r.stderr


def test_the_research_build_exports_its_own_digest(tmp_path):
    env = _env(tmp_path, build_digest=RESEARCH_BUILT)
    r = _run(tmp_path, env, _BUILD_FNS,
             'build_research_image && echo "R=${RESEARCH_IMAGE_REF}" && echo "REF=$(_research_image_ref)"')
    assert f"R={IMAGE}@{RESEARCH_BUILT}" in r.stdout, r.stdout + r.stderr
    assert f"REF={IMAGE}@{RESEARCH_BUILT}" in r.stdout
    assert (tmp_path / "submitted_tag").read_text().strip() == f"{IMAGE}:research"
    assert not any(c.startswith("artifacts docker images describe") for c in _calls(tmp_path))


def test_a_research_deploy_without_a_research_build_pins_the_current_digest(tmp_path):
    """Research targets do not build (`build-research` is separate), so they
    resolve `:research` once, to a digest, and deploy that."""
    env = _env(tmp_path)
    fns = _BUILD_FNS + ("deploy_direction_probe",)
    r = _run(tmp_path, env, fns, "deploy_direction_probe")
    assert "rc=0" in r.stdout, r.stdout + r.stderr
    jobs = [c for c in _calls(tmp_path) if c.startswith("run jobs")]
    assert jobs and all(f"--image {IMAGE}@{RESOLVED}" in c for c in jobs), jobs


def test_a_deploy_names_the_built_digest(tmp_path):
    env = _env(tmp_path)
    fns = _BUILD_FNS + ("deploy_evaluate_ew_strikes",)
    r = _run(tmp_path, env, fns, "build_image && deploy_evaluate_ew_strikes")
    assert "rc=0" in r.stdout, r.stdout + r.stderr
    jobs = [c for c in _calls(tmp_path) if c.startswith("run jobs")]
    assert jobs, _calls(tmp_path)
    assert all(f"--image {IMAGE}@{BUILT}" in c for c in jobs), jobs


def test_a_deploy_without_a_build_mutates_nothing(tmp_path):
    """`${IMAGE_REF:?}` exits the shell before gcloud runs. A failed $(...)
    inside an argument would not: gcloud would run with an empty --image."""
    env = _env(tmp_path)
    r = _run(tmp_path, env, ("deploy_evaluate_ew_strikes",), "deploy_evaluate_ew_strikes")
    assert "rc=0" not in r.stdout
    assert r.returncode != 0
    assert "IMAGE_REF" in r.stderr, r.stderr
    assert not any(c.startswith("run jobs") for c in _calls(tmp_path)), _calls(tmp_path)


# ── the dispatcher: a misspelt target is a failure ─────────────────────────

def _run_target(tmp_path, target: str) -> tuple[subprocess.CompletedProcess, list[str]]:
    env = _env(tmp_path)
    env["PROJECT_ID"] = "proj"
    proc = subprocess.run(["bash", str(REPO / "gcp/deploy.sh"), target], cwd=REPO,
                          env=env, capture_output=True, text=True, timeout=120)
    return proc, _calls(tmp_path)


def test_a_misspelt_target_exits_2(tmp_path):
    """Before #1171 `deploy.sh evalute-ew-strikes` printed the usage and
    exited 0, so a caller trusting the status read a typo as a deploy."""
    proc, calls = _run_target(tmp_path, "evalute-ew-strikes")
    assert proc.returncode == 2, (proc.returncode, proc.stderr[-400:])
    assert "unknown target" in proc.stderr and "Usage:" in proc.stderr
    assert not any(c.startswith(("run jobs", "builds submit")) for c in calls), calls


def test_help_still_exits_0(tmp_path):
    proc, _ = _run_target(tmp_path, "help")
    assert proc.returncode == 0, proc.stderr[-400:]
    assert "Usage:" in proc.stdout
